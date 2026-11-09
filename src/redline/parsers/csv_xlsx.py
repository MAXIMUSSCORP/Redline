"""Reads CSV, TXT and XLSX files into rows, then hands the rows to tabular.rows_to_panels."""

from __future__ import annotations

import codecs
import csv
import io
import warnings
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from redline.config import Config
from redline.model import Confidence, CoverageEntry, Method, Source, Unparsed
from redline.parsers.tabular import Parsed, rows_to_panels

if TYPE_CHECKING:
    from openpyxl.reader.excel import ExcelReader

SUFFIXES = (".csv", ".txt", ".xlsx")
MAX_ROWS = 20_000
MAX_COLS = 200
# A real panel schedule is tens of KB of sheet XML. Total unpacked sheet and shared-string
# bytes per workbook, and total rows read across all sheets, bound memory and time.
MAX_XLSX_BYTES = 8 * 2**20
MAX_TOTAL_ROWS = 50_000
# A real workbook has a handful of sheets; Excel itself rarely goes past a few dozen.
MAX_SHEETS = 255
# Excel's own limit on a sheet title. A longer title is copied into every locator, so such
# a sheet is not read.
MAX_TITLE = 31
# Characters of cell text kept per workbook. One shared string used by many cells is
# copied once per cell downstream, so the text is charged here, not just the bytes.
MAX_TEXT_CHARS = MAX_XLSX_BYTES
# Excel's limit on a number format code; a longer one is treated as a date format.
_MAX_FORMAT = 255
_BUILTIN_DATE_IDS = frozenset([*range(14, 23), 45, 46, 47])
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


def _format_kind(code: str) -> str:
    """'' for a plain number format, 'date', or 'delta' for [h], [m], [s] elapsed time.

    One linear scan: quoted text and escaped characters are skipped, and a bracketed
    section is dropped (a locale or colour tag), except an elapsed-time tag.
    """
    if len(code) > _MAX_FORMAT:
        return "date"
    kind = ""
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        if c == '"':
            i = code.find('"', i + 1)
            i = n if i < 0 else i + 1
        elif c == "[":
            j = code.find("]", i + 1)
            j = n if j < 0 else j
            if code[i + 1 : j].lower() in ("h", "hh", "m", "mm", "s", "ss"):
                return "delta"
            i = j + 1
        elif c in "\\_*":
            i += 2
        else:
            if c in "dDmMyYhHsS":
                kind = "date"
            i += 1
    return kind


def _date_styles(reader: ExcelReader, dtd: set[str]) -> tuple[set[int], set[int]]:
    """Cell style indexes whose number format is a date or time, and an elapsed time.

    A linear pass over styles.xml that reads numFmts and cellXfs only. openpyxl's
    stylesheet is never built: it costs time out of proportion to its bytes.
    """
    from openpyxl.xml.constants import ARC_STYLE
    from openpyxl.xml.functions import iterparse

    _refuse_dtd(dtd, ARC_STYLE)
    try:
        src = reader.archive.open(ARC_STYLE)
    except KeyError:
        return set(), set()
    custom: dict[int, str] = {}
    xfs: list[int] = []
    in_xfs = in_fmts = False
    with src:
        for event, el in iterparse(src, events=("start", "end")):
            tag = el.tag.rpartition("}")[2]
            if tag == "cellXfs":
                in_xfs = event == "start"
            elif tag == "numFmts":
                in_fmts = event == "start"
            elif event == "end" and tag == "numFmt" and in_fmts:
                custom[int(el.get("numFmtId", -1))] = el.get("formatCode", "")
                el.clear()
            elif event == "end" and tag == "xf" and in_xfs:
                xfs.append(int(el.get("numFmtId", 0)))
                el.clear()
    dates: set[int] = set()
    deltas: set[int] = set()
    # One classification per format id, not per xf: many xfs may share one long code.
    custom_kind = {fmt: _format_kind(code) for fmt, code in custom.items()}
    for idx, fmt in enumerate(xfs):
        if fmt in custom_kind:
            kind = custom_kind[fmt]
        else:
            kind = "delta" if fmt == 46 else "date" if fmt in _BUILTIN_DATE_IDS else ""
        if kind:
            dates.add(idx)
        if kind == "delta":
            deltas.add(idx)
    return dates, deltas


def _sheet_rows(
    reader: ExcelReader,
    target: str,
    styles: tuple[set[int], set[int]],
    text_left: int,
    name: str,
) -> tuple[list[list[str]], str | None, int, int]:
    """Rows of one sheet, a reason it is refused instead of being cut, rows and text charged."""
    # The sheet XML is parsed cell by cell, so a cell at any column is seen with its
    # real column number and no padded row is built for it. The declared dimension is
    # never used. The part is opened straight from the archive: nothing but worksheet
    # parts is ever parsed.
    from openpyxl.worksheet._reader import WorkSheetParser

    rows: list[list[str]] = []
    parsed = 0  # every row index parsed, charged even when the sheet is then refused
    last_idx = 0
    chars = 0
    refused: str | None = None
    try:
        # openpyxl warns once per out-of-range date cell; a hostile sheet makes MBs of it.
        with (
            warnings.catch_warnings(),
            reader.archive.open(target) as src,
        ):
            warnings.simplefilter("ignore", UserWarning)
            parser = WorkSheetParser(
                src,
                reader.shared_strings,
                data_only=True,
                epoch=reader.wb.epoch,
                date_formats=styles[0],
                timedelta_formats=styles[1],
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
                    chars += len(text)
                    if chars > text_left:
                        refused = (
                            f"sheet {name} holds more than {MAX_TEXT_CHARS} characters "
                            "of cell text, so it is not read"
                        )
                        break
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
        return [], refused, parsed, chars
    return rows, None, max(parsed, len(rows)), chars


# A DOCTYPE lets a few bytes of entity declarations expand to gigabytes in the stdlib XML
# parser. Real Excel files never hold one in a part the reader parses. expat also accepts
# UTF-16 by BOM. A DOCTYPE in a part never parsed (an SVG image) is harmless and ignored.
_DOCTYPES = tuple("<!DOCTYPE".encode(enc) for enc in ("ascii", "utf-16-le", "utf-16-be"))
_CHUNK = 1 << 16
_DOCTYPE_MSG = "the workbook holds a DOCTYPE declaration, so it is not read"


def _refuse_dtd(dtd: set[str], member: str) -> None:
    if member.lstrip("/") in dtd:
        raise InputError(_DOCTYPE_MSG)


def _unpack(path: Path) -> tuple[io.BytesIO, set[str]]:
    """Read every member once, in bounded chunks, into an in-memory stored archive.

    Excel writes only stored and deflate members. zipfile unpacks other methods without a
    per-read limit, so they are refused before any member is opened. Each member is read
    up to its declared size and the running total is held to MAX_XLSX_BYTES; openpyxl then
    parses this copy, never the file. Returns the copy and the names of members that hold
    a DTD declaration.
    """
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if any(
                i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) for i in infos
            ):
                raise InputError(
                    "the workbook uses a compression method Excel does not write, so it is not read"
                )
            # Every member counts, duplicates each time: openpyxl finds sheets and shared
            # strings through the rels and content types, not by path, and parses the rest.
            if sum(i.file_size for i in infos) > MAX_XLSX_BYTES:
                raise _too_big()
            keep = max(map(len, _DOCTYPES)) - 1
            left = MAX_XLSX_BYTES
            dtd: set[str] = set()
            out = io.BytesIO()
            with warnings.catch_warnings(), zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as w:
                warnings.simplefilter("ignore", UserWarning)  # duplicate member names are kept
                for info in infos:
                    data = bytearray()
                    has_dtd = False
                    tail = b""
                    with z.open(info) as f:
                        while chunk := f.read(_CHUNK):
                            left -= len(chunk)
                            if left < 0:
                                raise _too_big()
                            buf = tail + chunk
                            if any(d in buf for d in _DOCTYPES):
                                has_dtd = True
                            tail = buf[-keep:]
                            data += chunk
                    if has_dtd:
                        dtd.add(info.filename)
                    # A member with a DTD is stored empty, so no spelling of its name (a
                    # doubled slash, a dropped first letter) can bring the DTD to a parser.
                    w.writestr(info.filename, b"" if has_dtd else bytes(data))
            out.seek(0)
            return out, dtd
    except InputError:
        raise
    except Exception as e:
        raise InputError(f"cannot open the workbook: {type(e).__name__}") from e


def _too_big() -> InputError:
    return InputError(
        f"the workbook holds more than {MAX_XLSX_BYTES // 2**20} MB of data "
        "once unpacked, so it is not read"
    )


def _open_reader(
    path: Path,
) -> tuple[ExcelReader, list[tuple[str, str | None]], tuple[set[int], set[int]]]:
    """Unpack the package once; return the reader, (title, part) per sheet entry and date styles.

    The part is None for a chartsheet.

    openpyxl.load_workbook is never called: it parses every external link, chartsheet
    drawing and sheet entry per entry, so a small file can cost unbounded time. Only the
    manifest, shared strings and workbook are read here, each once. Targets
    are resolved by openpyxl's own reader (content types, workbook rels, joined paths), so
    no respelling of a target gets past the duplicate check.
    """
    from openpyxl.reader.excel import ExcelReader, _find_workbook_part
    from openpyxl.xml.constants import ARC_CONTENT_TYPES, SHARED_STRINGS

    archive, dtd = _unpack(path)
    reader = None
    try:
        # The manifest and every rels part are parsed first, so they are checked first.
        for name in dtd:
            if name == ARC_CONTENT_TYPES or name.endswith(".rels"):
                raise InputError(_DOCTYPE_MSG)
        reader = ExcelReader(archive, read_only=True, data_only=True, keep_links=False)
        reader.read_manifest()
        ct = reader.package.find(SHARED_STRINGS)
        if ct is not None:
            _refuse_dtd(dtd, ct.PartName)
        reader.read_strings()
        _refuse_dtd(dtd, _find_workbook_part(reader.package).PartName)
        reader.read_workbook()
        if len(reader.parser.sheets) > MAX_SHEETS:
            raise InputError(f"the workbook lists more than {MAX_SHEETS} sheets, so it is not read")
        found = [(s, rel) for s, rel in reader.parser.find_sheets()]
        targets = [rel.target for _, rel in found]
        if len(targets) != len(set(targets)):
            raise InputError(
                "the workbook lists one sheet part under more than one sheet, so it is not read"
            )
        entries: list[tuple[str, str | None]] = []
        for sheet, rel in found:
            if rel.target not in reader.valid_files:
                continue
            if "chartsheet" not in rel.Type:
                _refuse_dtd(dtd, rel.target)
            entries.append((sheet.name, None if "chartsheet" in rel.Type else rel.target))
        return reader, entries, _date_styles(reader, dtd)
    except InputError:
        if reader is not None:
            reader.archive.close()
        raise
    except Exception as e:
        if reader is not None:
            reader.archive.close()
        raise InputError(f"cannot open the workbook: {type(e).__name__}") from e


def _xlsx(path: Path, cfg: Config) -> Parsed:
    out = Parsed()
    reader, entries, styles = _open_reader(path)
    try:
        budget = MAX_TOTAL_ROWS
        text_left = MAX_TEXT_CHARS
        for name, target in entries:
            if len(name) > MAX_TITLE:
                short = f"{name[:MAX_TITLE]}..."
                src = Source(path.name, f"sheet={short}", Method.XLSX, Confidence.LOW)
                why = (
                    f"sheet title {short} is longer than {MAX_TITLE} characters, so it is not read"
                )
                out.unparsed.append(Unparsed("sheet", short, why, src))
                continue
            if target is None:
                src = Source(path.name, f"sheet={name}", Method.XLSX, Confidence.LOW)
                out.unparsed.append(Unparsed("sheet", name, f"chartsheet {name} is not read", src))
                continue
            if budget <= 0 or text_left <= 0:
                rows = []
                refused = (
                    f"the workbook has more than {MAX_TOTAL_ROWS} rows or {MAX_TEXT_CHARS} "
                    f"characters of cell text, so sheet {name} is not read"
                )
            else:
                rows, refused, charged, used = _sheet_rows(reader, target, styles, text_left, name)
                budget -= charged
                text_left -= used
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
        reader.archive.close()
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
