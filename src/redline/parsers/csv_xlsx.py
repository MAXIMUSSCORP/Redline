"""Reads CSV, TXT and XLSX files into rows, then hands the rows to tabular.rows_to_panels."""

from __future__ import annotations

import codecs
import csv
import io
from dataclasses import replace
from pathlib import Path

from redline.config import Config
from redline.model import Confidence, CoverageEntry, Method, Source, Unparsed
from redline.parsers.tabular import Parsed, rows_to_panels

SUFFIXES = (".csv", ".txt", ".xlsx")
MAX_ROWS = 20_000
MAX_COLS = 200


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


def _sheet_rows(ws, name: str) -> tuple[list[list[str]], str | None]:
    """Rows of one sheet, or a reason the sheet is refused instead of being cut."""
    # The declared dimension is untrusted, so drop it and bound what is read.
    ws.reset_dimensions()
    rows = []
    try:
        for n, values in enumerate(ws.iter_rows(values_only=True, max_col=MAX_COLS + 1), 1):
            if n > MAX_ROWS:
                return [], f"sheet {name} has more than {MAX_ROWS} rows, so it is not read"
            end = len(values)
            while end and (values[end - 1] is None or not str(values[end - 1]).strip()):
                end -= 1
            if end > MAX_COLS:
                return [], f"sheet {name} has more than {MAX_COLS} columns, so it is not read"
            rows.append(["" if v is None else str(v) for v in values[:end]])
    except Exception as e:
        raise InputError(f"cannot read the workbook: {type(e).__name__}") from e
    return rows, None


def _xlsx(path: Path, cfg: Config) -> Parsed:
    import openpyxl

    out = Parsed()
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        raise InputError(f"cannot open the workbook: {type(e).__name__}") from e
    try:
        for ws in wb.worksheets:
            name = ws.title
            rows, refused = _sheet_rows(ws, name)
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
