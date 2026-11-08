"""Reads CSV, TXT and XLSX files into rows, then hands the rows to tabular.rows_to_panels."""

from __future__ import annotations

import codecs
import csv
import io
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from redline.config import Config
from redline.model import Confidence, CoverageEntry, Method, Source, Unparsed
from redline.parsers.tabular import Parsed, rows_to_panels

if TYPE_CHECKING:
    from openpyxl.worksheet._read_only import ReadOnlyWorksheet

SUFFIXES = (".csv", ".txt", ".xlsx")
MAX_ROWS = 20_000
MAX_COLS = 200
# A real panel schedule is tens of KB of sheet XML. Total unpacked sheet and shared-string
# bytes per workbook, and total rows read across all sheets, bound memory and time.
MAX_XLSX_BYTES = 8 * 2**20
MAX_TOTAL_ROWS = 50_000
# A real workbook has a handful of sheets; Excel itself rarely goes past a few dozen.
MAX_SHEETS = 255
_ORDER = "sheet {} has cells or rows out of order, so it is not read"


class InputError(Exception):
    """The file cannot be opened, decoded or split into rows."""


def _decode(data: bytes) -> tuple[str, str]:
    try:
        if data.startswith(codecs.BOM_UTF8):
            return data.decode("utf-8-sig"), "utf-8 with BOM"
        if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return data.decode("utf-16"), "utf-16"
        try:
            return data.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            return data.decode("cp1252"), "cp1252"
    except UnicodeDecodeError as e:
        raise InputError(f"cannot decode the file: {e.reason}") from e


def _delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:8192], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def _text_rows(path: Path) -> tuple[list[list[str]], str]:
    try:
        data = path.read_bytes()
    except OSError as e:
        raise InputError(f"cannot read the file: {e.strerror or type(e).__name__}") from e
    text, encoding = _decode(data)
    if "\x00" in text:
        raise InputError("the file holds NUL bytes, so it is not a text table")
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text)))
    except csv.Error as e:
        raise InputError(f"cannot split the file into rows: {e}") from e
    return rows, encoding


def _sheet_rows(ws: ReadOnlyWorksheet, name: str) -> tuple[list[list[str]], str | None, int]:
    """Rows of one sheet, a reason it is refused instead of being cut, and the rows charged."""
    # The sheet XML is parsed cell by cell, so a cell at any column is seen with its
    # real column number and no padded row is built for it. The declared dimension is
    # never used.
    from openpyxl.worksheet._reader import WorkSheetParser

    rows: list[list[str]] = []
    parsed = 0  # every row index parsed, charged even when the sheet is then refused
    last_idx = 0
    refused: str | None = None
    try:
        with ws._get_source() as src:
            parser = WorkSheetParser(
                src,
                ws._shared_strings,
                data_only=ws.parent.data_only,
                epoch=ws.parent.epoch,
                date_formats=ws.parent._date_formats,
                timedelta_formats=ws.parent._timedelta_formats,
            )
            for idx, cells in parser.parse():
                parsed += 1
                if idx > MAX_ROWS:
                    refused = f"sheet {name} has more than {MAX_ROWS} rows, so it is not read"
                    break
                # Position comes from the r attributes. A repeated or backward row or
                # cell would land in the wrong place, so the sheet is refused, not moved.
                if idx <= last_idx:
                    refused = _ORDER.format(name)
                    break
                last_idx = idx
                values: list[str] = []
                for cell in cells:
                    v = cell["value"]
                    text = "" if v is None else str(v)
                    if not text.strip():
                        continue
                    col = cell["column"]
                    if col > MAX_COLS:
                        refused = (
                            f"sheet {name} has more than {MAX_COLS} columns, so it is not read"
                        )
                        break
                    if col <= len(values):
                        refused = _ORDER.format(name)
                        break
                    values.extend([""] * (col - len(values) - 1))
                    values.append(text)
                if refused:
                    break
                rows.extend([] for _ in range(idx - 1 - len(rows)))
                rows.append(values)
    except Exception as e:
        raise InputError(f"cannot read the workbook: {type(e).__name__}") from e
    if refused:
        return [], refused, parsed
    return rows, None, max(parsed, len(rows))


def _check_size(path: Path) -> None:
    """Refuse a workbook whose sheets would inflate past the cap, before openpyxl parses it."""
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
    except Exception as e:
        raise InputError(f"cannot open the workbook: {type(e).__name__}") from e
    # Every member counts, duplicates each time: openpyxl finds sheets and shared strings
    # through the rels and content types, not by path, and parses styles and the rest.
    total = sum(i.file_size for i in infos)
    if total > MAX_XLSX_BYTES:
        raise InputError(
            f"the workbook holds more than {MAX_XLSX_BYTES // 2**20} MB of data "
            "once unpacked, so it is not read"
        )
    _check_sheet_entries(path)


def _check_sheet_entries(path: Path) -> None:
    """Refuse a workbook that lists one sheet part twice or lists too many sheets."""
    # openpyxl sizes every sheet entry on load, so N entries naming one part cost N scans of
    # it before any row budget applies. Targets are resolved by openpyxl's own reader (content
    # types, workbook rels, joined paths, normpath), so no respelling of a target gets past
    # this check. The pre-pass parses only the manifest, workbook.xml and its rels, never a
    # sheet.
    from openpyxl.reader.excel import ExcelReader

    try:
        reader = ExcelReader(path, read_only=True, keep_links=False)
        try:
            reader.read_manifest()
            reader.read_workbook()
            if len(reader.parser.sheets) > MAX_SHEETS:
                raise InputError(
                    f"the workbook lists more than {MAX_SHEETS} sheets, so it is not read"
                )
            targets = [rel.target for _, rel in reader.parser.find_sheets()]
        finally:
            reader.archive.close()
    except InputError:
        raise
    except Exception as e:
        raise InputError(f"cannot open the workbook: {type(e).__name__}") from e
    if len(targets) != len(set(targets)):
        raise InputError(
            "the workbook lists one sheet part under more than one sheet, so it is not read"
        )


def _xlsx(path: Path, cfg: Config) -> Parsed:
    import openpyxl

    out = Parsed()
    _check_size(path)
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        raise InputError(f"cannot open the workbook: {type(e).__name__}") from e
    try:
        budget = MAX_TOTAL_ROWS
        for ws in wb.worksheets:
            name = ws.title
            if budget <= 0:
                rows, refused = (
                    [],
                    f"the workbook has more than {MAX_TOTAL_ROWS} rows, so sheet {name} is not read",
                )
            else:
                rows, refused, charged = _sheet_rows(ws, name)
                budget -= charged
            if refused:
                src = Source(path.name, f"sheet={name}", Method.XLSX, Confidence.LOW)
                out.unparsed.append(Unparsed("sheet", name, refused, src))
                continue
            part = rows_to_panels(
                rows,
                cfg,
                file=path.name,
                method=Method.XLSX,
                locate=lambda i, name=name: f"sheet={name}; row={i + 1}",
                fallback_panel=name,
            )
            for u in part.unparsed:
                if u.kind == "table":
                    u = replace(u, kind="sheet", raw=name)
                out.unparsed.append(u)
            out.panels += part.panels
            out.coverage += part.coverage
    finally:
        wb.close()
    return out


def parse_file(path: Path, cfg: Config) -> Parsed:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        parsed, method = _xlsx(path, cfg), Method.XLSX
    elif suffix in (".csv", ".txt"):
        rows, encoding = _text_rows(path)
        parsed = rows_to_panels(
            rows,
            cfg,
            file=path.name,
            method=Method.CSV,
            locate=lambda i: f"row={i + 1}",
        )
        parsed.coverage = [
            replace(c, what_read=f"{c.what_read}; encoding {encoding}") for c in parsed.coverage
        ]
        method = Method.CSV
    else:
        raise InputError(f"unsupported file type: {suffix or 'none'}")
    if not parsed.panels:
        empty = "HIGH 0, MEDIUM 0, LOW 0, MISSING 0"
        parsed.coverage.append(
            CoverageEntry(path.name, "file", "no panel read", method.value, empty)
        )
    return parsed
