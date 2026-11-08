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


def _sheet_rows(ws: ReadOnlyWorksheet, name: str) -> tuple[list[list[str]], str | None]:
    """Rows of one sheet, or a reason the sheet is refused instead of being cut."""
    # The sheet XML is parsed cell by cell, so a cell at any column is seen with its
    # real column number and no padded row is built for it. The declared dimension is
    # never used.
    from openpyxl.worksheet._reader import WorkSheetParser

    rows: list[list[str]] = []
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
                if idx > MAX_ROWS:
                    return [], f"sheet {name} has more than {MAX_ROWS} rows, so it is not read"
                values: list[str] = []
                for cell in cells:
                    v = cell["value"]
                    text = "" if v is None else str(v)
                    if not text.strip():
                        continue
                    col = cell["column"]
                    if col > MAX_COLS:
                        return (
                            [],
                            f"sheet {name} has more than {MAX_COLS} columns, so it is not read",
                        )
                    values.extend([""] * (col - len(values) - 1))
                    values.append(text)
                rows.extend([] for _ in range(idx - 1 - len(rows)))
                rows.append(values)
    except Exception as e:
        raise InputError(f"cannot read the workbook: {type(e).__name__}") from e
    return rows, None


def _check_size(path: Path) -> None:
    """Refuse a workbook whose sheets would inflate past the cap, before openpyxl parses it."""
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
    except Exception as e:
        raise InputError(f"cannot open the workbook: {type(e).__name__}") from e
    total = sum(
        i.file_size
        for i in infos
        if i.filename.startswith("xl/worksheets/") or i.filename == "xl/sharedStrings.xml"
    )
    if total > MAX_XLSX_BYTES:
        raise InputError(
            f"the workbook holds more than {MAX_XLSX_BYTES // 2**20} MB of sheet data "
            "once unpacked, so it is not read"
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
                rows, refused = _sheet_rows(ws, name)
                budget -= len(rows)
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
