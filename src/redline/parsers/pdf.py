"""Reads a PDF into panels. Text pages go to the table finder, SHX pages with annotation text to
the annotation path, and scanned, stroke-only and skipped pages are listed, never guessed.

pdfplumber is imported only inside the child dump function, so importing this module loads no
PDF library."""

from __future__ import annotations

import json
import math
import re
import shutil
import statistics
import sys
import tempfile
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from itertools import islice
from pathlib import Path
from typing import Any

import redline as redline_pkg
from redline import rawdrawing
from redline.config import Config
from redline.extract import ExtractError, run_tool, sha256_of
from redline.model import Confidence, CoverageEntry, Method, Source, Unparsed, Value, clip
from redline.parsers.csv_xlsx import InputError
from redline.parsers.dxf import (
    TextItem,
    apply_to_sources,
    confidence_summary,
    medium_cap,
    text_grid,
)
from redline.parsers.tabular import Parsed, normalize_header, rows_to_panels

SUFFIXES = (".pdf",)
# Design limits, not code values.
MAX_PDF_BYTES = 256 * 2**20
MAX_PAGES = 1000
MAX_WORDS_PER_PAGE = 100_000
MAX_ANNOTS_PER_PAGE = 10_000
MAX_CHARS_PER_PAGE = 1_000_000
# Longest array or dictionary pdfminer may parse in the file, whether in the file body, the page
# tree or an object stream. A page tree of 100000 pages is under it.
MAX_ARRAY_ITEMS = 200_000
# Per-process ceiling on the child. A large E-size sheet needs well under 1 GB.
MAX_CHILD_MEMORY_MB = 4096
_CAPS = (
    "MAX_PDF_BYTES",
    "MAX_PAGES",
    "MAX_WORDS_PER_PAGE",
    "MAX_ANNOTS_PER_PAGE",
    "MAX_CHARS_PER_PAGE",
    "MAX_CHILD_MEMORY_MB",
)
_MAX_WORD_TEXT = 1000
_MAX_WARNINGS = 20

TEXT, VECTOR_NO_TEXT, SCANNED = "TEXT", "VECTOR_NO_TEXT", "SCANNED"
SCANNED_NOTE = "scanned page (a full-page image), needs OCR or vision"
OCR_LAYER_NOTE = (
    "scanned page with a text layer that is likely OCR; the text is not trusted, "
    "needs OCR or vision"
)
SHX_NOTE = (
    "scanned or SHX page with no text layer, needs OCR or vision; "
    "or re-plot with TrueType substitution"
)
FEW_CHARS_NOTE = (
    "page has too little text to read as a text page, needs OCR or vision; "
    "or re-plot with TrueType substitution"
)
ANNOT_NOTE = "read from PDF annotation text"
WORDS_NOTE = "read from PDF words, no drawn grid"
DISAGREE_NOTE = "annotation text and page text disagree"
_NO_SUMMARY = "HIGH 0, MEDIUM 0, LOW 0, MISSING 0"
_REASON_LIMIT = 199  # clip() keeps limit + 1 characters, so a reason is at most 200
MAX_LISTED_PER_PAGE = 50  # annotation disagreements listed per page; the rest are only counted
_TITLE_SHOWN = 3  # values named in the "more than one value" text
_TITLE_LABELS = {"sheet_number": ("sheet", "sheet number"), "revision": ("revision", "revision")}


# ---- numbers and shapes of a dump that is not trusted ----


def _num(x: Any, default: float = 0.0) -> float:
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x):
        return default
    return float(x)


def _str(x: Any) -> str:
    return " ".join(x.split()) if isinstance(x, str) else ""


def _list(x: Any) -> list:
    return x if isinstance(x, list) else []


def _reason(text: str) -> str:
    return clip(text, _REASON_LIMIT)


# ---- the child: the only place a PDF library is named ----


def _text_of(x: Any, decode) -> str:
    if isinstance(x, bytes):
        try:
            x = decode(x)
        except Exception:  # noqa: BLE001
            return ""
    return x.replace("﻿", "") if isinstance(x, str) else ""


class _ArrayTooLong(InputError):
    """A PDF array or dictionary is longer than MAX_ARRAY_ITEMS. Raised while it is parsed, so the
    rest of it is never tokenised."""


class _BoundedArrays:
    """Stop pdfminer's file parser at MAX_ARRAY_ITEMS entries in one array. This is the only way to
    bound an /Annots array before pdfminer builds it: it is parsed when the page, its /Annots object
    or the object stream holding either is first read. Content streams use another parser and are
    not touched. An object or object stream that failed is remembered, since pdfminer caches only
    what it parsed, and a thousand pages may name the same one. These are pdfminer internals: a
    release that renames one makes the read fail loudly, and the annotation tests fail with it."""

    def __init__(self, name: str) -> None:
        self.message = (
            f"{name} has an array of more than {MAX_ARRAY_ITEMS} entries in the file or its page "
            "tree, so it is not read"
        )

    def __enter__(self) -> None:
        try:
            from pdfminer.pdfdocument import PDFDocument
            from pdfminer.pdfparser import PDFParser
        except ImportError as e:
            raise InputError("pdfplumber not installed: pip install redline[pdf]") from e
        self.saved = [
            (cls, name, getattr(cls, name))
            for cls, name in [
                (PDFParser, "push"),
                (PDFDocument, "_getobj_parse"),
                (PDFDocument, "_getobj_objstm"),
            ]
        ]
        failed: set = set()
        message = self.message  # a fresh exception per raise: a shared one grows its traceback
        push = PDFParser.push

        def bounded_push(parser, *objs):
            push(parser, *objs)
            if len(parser.curstack) > MAX_ARRAY_ITEMS:
                raise _ArrayTooLong(message)

        def remembered(method, key):
            def wrapper(doc, *args):
                k = (method.__name__, key(*args))
                if k in failed:
                    raise _ArrayTooLong(message)
                try:
                    return method(doc, *args)
                except _ArrayTooLong:
                    failed.add(k)
                    raise

            return wrapper

        PDFParser.push = bounded_push
        PDFDocument._getobj_parse = remembered(PDFDocument._getobj_parse, lambda pos, objid: pos)
        PDFDocument._getobj_objstm = remembered(
            PDFDocument._getobj_objstm, lambda stream, index, objid: stream.objid
        )

    def __exit__(self, *exc) -> None:
        for cls, name, original in self.saved:
            setattr(cls, name, original)


def _is_memory(e: BaseException | None) -> bool:
    """pdfplumber wraps a MemoryError from pdfminer in its own exception."""
    while e is not None:
        if isinstance(e, MemoryError) or any(isinstance(a, MemoryError) for a in e.args):
            return True
        e = e.__cause__ or e.__context__
    return False


def _dump_page(page: Any, caps: dict, decode, resolve1) -> dict:
    w, h = _num(page.width), _num(page.height)
    found: list[dict] = []  # drawn tables, filled below
    nchars = len(page.chars)
    d: dict[str, Any] = {
        "n": int(page.page_number),
        "width": round(w, 2),
        "height": round(h, 2),
        "rotation": int(page.rotation or 0),
        "chars": nchars,
        "paths": len(page.lines) + len(page.rects) + len(page.curves),
        "words": [],
        "tables": found,
        "annots": [],
    }
    area = 0.0
    for im in page.images:
        iw = min(_num(im.get("x1")), w) - max(_num(im.get("x0")), 0.0)
        ih = min(_num(im.get("bottom")), h) - max(_num(im.get("top")), 0.0)
        area += max(iw, 0.0) * max(ih, 0.0)
    d["image_area_fraction"] = round(min(area / (w * h), 1.0), 4) if w * h > 0 else 0.0
    try:
        raw_annots = resolve1(page.page_obj.annots)  # the raw array, before any entry is resolved
    except _ArrayTooLong:
        d["skipped"] = (
            f"page /Annots holds more than {MAX_ARRAY_ITEMS} entries, over MAX_ANNOTS_PER_PAGE "
            f"({caps['MAX_ANNOTS_PER_PAGE']}), so it is not read"
        )
        return d
    n_annots = len(raw_annots) if isinstance(raw_annots, list) else 0
    if n_annots > caps["MAX_ANNOTS_PER_PAGE"]:
        d["skipped"] = (
            f"page has {n_annots} annotations, over MAX_ANNOTS_PER_PAGE "
            f"({caps['MAX_ANNOTS_PER_PAGE']}), so it is not read"
        )
        return d
    if nchars > caps["MAX_CHARS_PER_PAGE"]:
        d["skipped"] = (
            f"page has {nchars} characters, over MAX_CHARS_PER_PAGE "
            f"({caps['MAX_CHARS_PER_PAGE']}), so it is not read"
        )
        return d
    annots = page.annots
    words = page.extract_words()
    if len(words) > caps["MAX_WORDS_PER_PAGE"]:
        d["skipped"] = (
            f"page has {len(words)} words, over MAX_WORDS_PER_PAGE "
            f"({caps['MAX_WORDS_PER_PAGE']}), so it is not read"
        )
        return d
    d["words"] = [
        {
            "text": str(w["text"])[:_MAX_WORD_TEXT],
            "x0": round(w["x0"], 2),
            "x1": round(w["x1"], 2),
            "top": round(w["top"], 2),
            "bottom": round(w["bottom"], 2),
            "upright": bool(w.get("upright", True)),
        }
        for w in words
    ]
    for a in annots:
        sub = (a.get("data") or {}).get("Subtype")
        d["annots"].append(
            {
                "subtype": getattr(sub, "name", None),
                "contents": _text_of((a.get("data") or {}).get("Contents"), decode)[
                    :_MAX_WORD_TEXT
                ],
                "x0": round(a["x0"], 2),
                "x1": round(a["x1"], 2),
                "top": round(a["top"], 2),
                "bottom": round(a["bottom"], 2),
            }
        )
    if d["chars"]:  # a page with no text layer has no drawn table of words to find
        for t in page.find_tables():
            found.append(
                {"bbox": [round(v, 2) for v in t.bbox], "rows": t.extract()},
            )
    return d


def _dump(job: dict) -> dict:
    """Open the PDF and dump every page. Raises InputError with a plain reason."""
    with _BoundedArrays(Path(job["path"]).name):
        return _read(job)


def _read(job: dict) -> dict:
    name = Path(job["path"]).name
    import itertools

    try:
        import pdfminer
        import pdfplumber
        from pdfminer.pdfdocument import PDFPasswordIncorrect
        from pdfminer.pdfpage import PDFPage
        from pdfminer.pdftypes import resolve1
        from pdfminer.utils import decode_text
        from pdfplumber.page import Page
    except ImportError as e:
        raise InputError("pdfplumber not installed: pip install redline[pdf]") from e
    caps = job["caps"]
    cap = caps["MAX_PAGES"]
    no_memory = InputError(
        f"{name} needs more memory than MAX_CHILD_MEMORY_MB ({caps['MAX_CHILD_MEMORY_MB']} MB), "
        "so it is not read"
    )
    try:
        pdf = pdfplumber.open(job["path"])
    except InputError:
        raise
    except PDFPasswordIncorrect as e:
        raise InputError(f"{name} is password protected, so it is not read") from e
    except Exception as e:
        if _is_memory(e):
            raise no_memory from e
        raise InputError(f"{name} cannot be read as a PDF ({type(e).__name__})") from e
    pages: list[dict] = []
    try:
        # pdf.close() would build every page object, so only the stream is closed. Only the first
        # MAX_PAGES page objects are built: a file with a million pages costs as much as MAX_PAGES.
        with pdf.stream:
            it = PDFPage.create_pages(pdf.doc)
            for i, raw in enumerate(itertools.islice(it, cap), 1):
                page = Page(pdf, raw, page_number=i)
                try:
                    pg = _dump_page(page, caps, decode_text, resolve1)
                    try:
                        json.dumps(pg, allow_nan=False)
                    except ValueError:
                        pg = {
                            "n": i,
                            "skipped": "page has a coordinate that is not finite, so it is not read",
                        }
                    pages.append(pg)
                except Exception as e:
                    if _is_memory(e):
                        raise MemoryError from e
                    pages.append({"n": i, "skipped": f"page cannot be read ({type(e).__name__})"})
                finally:
                    page.close()
            more = sum(1 for _ in itertools.islice(it, 1))
            count = resolve1((resolve1(pdf.doc.catalog.get("Pages")) or {}).get("Count"))
    except InputError:
        raise
    except Exception as e:
        if _is_memory(e):
            raise no_memory from e
        raise InputError(f"{name} cannot be read as a PDF ({type(e).__name__})") from e
    read = len(pages)
    total = read
    if more:
        # /Count is the file's own claim, so it is used only when it fits what was read and what
        # the parent's JSON read accepts (above 2**53 it is not an exact number).
        total = count if isinstance(count, int) and read < count <= 2**53 else 0
        skipped = (
            f"{total - read} pages past MAX_PAGES ({cap}) are not read"
            if total
            else f"more than {read} pages, the pages past MAX_PAGES ({cap}) are not read"
        )
        total = total or read + 1
        pages.append({"n": read + 1, "skipped": skipped})
    return {
        "pdfplumber": str(pdfplumber.__version__),
        "pdfminer": str(pdfminer.__version__),
        "sha256": job["sha256"],
        "pages_total": total,
        "pages": pages,
    }


# The child imports the parent's own redline package, not whatever an editable install points at.
_CHILD = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "from redline.parsers.pdf import child_main; child_main(sys.argv[2])"
)


def _limit_memory(mb: int) -> str | None:
    """Put this process under a Windows Job Object with a per-process memory limit. Returns
    why it could not, or None. It is set here, in the reading process itself: sys.executable
    can be a launcher that starts the real python, which a job set from the parent can miss."""
    if sys.platform != "win32":
        return "no memory ceiling on this platform, so a hostile PDF is not bounded in memory"
    import ctypes
    from ctypes import wintypes

    class _Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class _Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _Basic),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    job = k32.CreateJobObjectW(None, None)
    info = _Extended()
    info.BasicLimitInformation.LimitFlags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.ProcessMemoryLimit = mb * 2**20
    ok = job and k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
    ok = ok and k32.AssignProcessToJobObject(job, k32.GetCurrentProcess())
    if not ok:
        return f"the memory ceiling could not be set (Windows error {ctypes.get_last_error()})"
    return None


def child_main(job_file: str) -> None:
    """Entry point of the child process: write the dump, or the plain reason it failed."""
    job = json.loads(Path(job_file).read_text(encoding="utf-8"))
    tmp = Path(job["tmp"])
    try:
        warning = _limit_memory(job["caps"]["MAX_CHILD_MEMORY_MB"])
        dump = _dump(job)
        if warning:
            dump["warnings"] = [warning]
        (tmp / "out.json").write_text(json.dumps(dump, allow_nan=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        msg = str(e) if isinstance(e, InputError) else f"PDF reader failed ({type(e).__name__})"
        if _is_memory(e):
            msg = "PDF reader needs more memory than MAX_CHILD_MEMORY_MB, so the file is not read"
        (tmp / "err.txt").write_text(msg, encoding="utf-8")


def read_pages(path: Path, cfg: Config, *, isolated: bool = True) -> dict:
    """The page dump. Raises InputError only. The read runs in a child process under
    pdf_timeout_s, since pdfminer parses untrusted input in pure Python."""
    path = Path(path)
    if not path.is_file():
        raise InputError(f"{path.name} was not found")
    try:
        size = path.stat().st_size
    except OSError as e:
        raise InputError(f"{path.name} cannot be read ({type(e).__name__})") from e
    if size > MAX_PDF_BYTES:
        raise InputError(f"{path.name} is over MAX_PDF_BYTES ({MAX_PDF_BYTES} bytes)")
    try:
        sha = sha256_of(path)
    except ExtractError as e:
        raise InputError(str(e)) from e
    job: dict[str, Any] = {
        "path": str(path.absolute()),
        "sha256": sha,
        "caps": {k: globals()[k] for k in _CAPS},
    }
    if not isolated:
        return _dump(job)
    timeout = cfg.column_maps["parsing"]["pdf_timeout_s"]
    tmp = Path(tempfile.mkdtemp(prefix="redline-pdf-", dir=tempfile.gettempdir()))
    try:
        job["tmp"] = str(tmp)
        (tmp / "job.json").write_text(json.dumps(job), encoding="utf-8")
        pkg = str(Path(redline_pkg.__file__).resolve().parents[1])
        try:
            run_tool(path.name, [sys.executable, "-I", "-c", _CHILD, pkg, str(tmp / "job.json")],
                     timeout, tmp)  # fmt: skip
        except ExtractError as e:
            raise InputError(str(e)) from e
        if (tmp / "err.txt").is_file():
            raise InputError((tmp / "err.txt").read_text(encoding="utf-8", errors="replace")[:2000])
        if not (tmp / "out.json").is_file():
            raise InputError(f"{path.name} was not read: the PDF reader wrote no output")
        try:
            dump = rawdrawing.read(tmp / "out.json")
        except (ValueError, OSError) as e:
            raise InputError(f"{path.name} was not read: the PDF reader output is bad ({e})") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not isinstance(dump, dict):
        raise InputError(f"{path.name} was not read: the PDF reader output is bad")
    return dump


# ---- classification ----


def classify(page: dict, parsing: dict) -> str:
    """An image that fills the page wins over a text layer, which is then likely OCR (D4)."""
    if _num(page.get("image_area_fraction")) >= parsing["pdf_scanned_image_area_fraction"]:
        return SCANNED
    if _num(page.get("chars")) >= parsing["pdf_text_page_min_chars"]:
        return TEXT
    return VECTOR_NO_TEXT


def provenance(dump: dict) -> str:
    return (
        f"pdfplumber {_str(dump.get('pdfplumber'))}, pdfminer.six {_str(dump.get('pdfminer'))}, "
        f"SHA-256 {_str(dump.get('sha256'))}"
    )


# ---- one page ----


@dataclass(frozen=True)
class _Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    upright: bool

    @property
    def h(self) -> float:
        return self.bottom - self.top

    def centre(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2, (self.top + self.bottom) / 2

    def item(self) -> TextItem:
        return TextItem(self.x0, -self.top, self.h, self.text, self.x1)


@dataclass(frozen=True)
class _Annot:
    subtype: str
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    def centre(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2, (self.top + self.bottom) / 2


def _box(d: dict) -> tuple[float, float, float, float] | None:
    x0, x1, top, bottom = (_num(d.get(k), math.nan) for k in ("x0", "x1", "top", "bottom"))
    if math.isnan(x0 + x1 + top + bottom) or x1 < x0 or bottom < top:
        return None
    return x0, x1, top, bottom


def _words(raw: Any) -> tuple[list[_Word], int]:
    """Words with a usable box, and how many words have none."""
    out, bad = [], 0
    for w in _list(raw):
        if not isinstance(w, dict) or not _str(w.get("text")):
            continue
        b = _box(w)
        if b is None or b[3] <= b[2]:
            bad += 1
            continue
        out.append(_Word(_str(w["text"]), b[0], b[1], b[2], b[3], w.get("upright") is not False))
    return out, bad


def _annots(raw: Any) -> tuple[list[_Annot], int]:
    """Annotations with text and a usable box, and how many have text but no box."""
    out, bad = [], 0
    for a in _list(raw):
        if not isinstance(a, dict) or not _str(a.get("contents")):
            continue
        b = _box(a)
        if b is None or b[3] <= b[2]:
            bad += 1
            continue
        sub = a.get("subtype")
        out.append(
            _Annot(sub if isinstance(sub, str) and sub else "unknown", _str(a["contents"]), *b)
        )
    return out, bad


class _Crop:
    """The title block corner, from the configured fractions; None when the page is rotated."""

    def __init__(self, page: dict, parsing: dict) -> None:
        w, h = _num(page.get("width")), _num(page.get("height"))
        self.rotation = int(_num(page.get("rotation")))
        self.usable = self.rotation == 0 and w > 0 and h > 0
        self.x = w * (1 - parsing["pdf_title_block_width_fraction"])
        self.y = h * (1 - parsing["pdf_title_block_height_fraction"])

    def holds(self, centre: tuple[float, float]) -> bool:
        return self.usable and centre[0] >= self.x and centre[1] >= self.y


def _fold(s: str) -> str:
    return " ".join(s.split()).casefold()


def _read_title(
    words: list[_Word], parsing: dict, aliases: dict
) -> tuple[dict, str, str, list[_Word]]:
    """Value per key (None when missing or ambiguous), the sheet number, the coverage text, and
    the words that were not used as a label or a value."""
    grid: list[list[str]] = []
    ys: list[float] = []
    if words:
        built = text_grid(
            [w.item() for w in words],
            parsing["pdf_row_tolerance_word_heights"],
            parsing["pdf_column_gap_fraction"],
        )
        grid, ys = (built[0], built[1]) if built else ([], [])
    keys = [k for k in aliases if k != "other_labels"]
    wanted = {normalize_header(a): k for k in keys for a in _list(aliases[k])}
    wanted.pop("", None)
    # Every alias is a label, never a value: the sheet and revision ones and the others.
    labels = set(wanted) | {normalize_header(a) for a in _list(aliases.get("other_labels"))}
    labels.discard("")
    found: dict[str, list[str]] = {k: [] for k in keys}
    used: set[tuple[int, int]] = set()
    # One pass over the grid: which cells are labels, so no loop below normalises a cell twice.
    is_label = [[normalize_header(x) in labels for x in row] for row in grid]

    def cell(i: int, c: int) -> str:
        return grid[i][c].strip() if i < len(grid) and c < len(grid[i]) else ""

    def value(i: int, c: int) -> str:
        x = cell(i, c)
        return "" if x and is_label[i][c] else x

    def has_digit(x: str) -> bool:
        return any(ch.isdigit() for ch in x)

    header = [sum(flags) >= 2 for flags in is_label]  # two or more labels: a block header
    full: dict[tuple[int, int], bool] = {}

    def full_row(h: int, i: int) -> bool:
        """Row i has a value under at least two of the label columns of header row h."""
        if (h, i) not in full:
            hits = 0
            for c, x in enumerate(grid[i]):
                if x.strip() and not is_label[i][c] and c < len(is_label[h]) and is_label[h][c]:
                    hits += 1
            full[h, i] = hits >= 2
        return full[h, i]

    for r, row in enumerate(grid):
        for c, text in enumerate(row):
            key = wanted.get(normalize_header(text))
            if key is None:
                continue
            j = c + 1
            while j < len(row) and not row[j].strip():
                j += 1
            beside = row[j].strip() if j < len(row) else ""
            below = cell(r + 1, c)
            # Beside is a value unless it is a label, or a word with no digit over a value
            # (a header row of boxes whose label is missing from the aliases).
            if (
                beside
                and not is_label[r][j]
                and (has_digit(beside) or not has_digit(below) or is_label[r + 1][c])
            ):
                found[key].append(beside)
                used |= {(r, c), (r, j)}
                continue
            # Otherwise the value is in the column below. Several values only in a revision table:
            # the label's row is a header of a block and the rows below are full rows of it.
            first = value(r + 1, c)
            if not first:
                continue
            got_below = [(r + 1, first)]
            if header[r]:
                i = r + 2
                while i < len(grid) and full_row(r, i) and value(i, c):
                    got_below.append((i, value(i, c)))
                    i += 1
            used.add((r, c))
            used |= {(i, c) for i, _ in got_below}
            found[key] += [x for _, x in got_below]
    values, got, missing = {}, [], []
    for key, vs in found.items():
        short, long = _TITLE_LABELS.get(key, (key.replace("_", " "),) * 2)
        distinct = sorted(set(vs))
        values[key] = distinct[0] if len(distinct) == 1 else None
        if len(distinct) == 1:
            got.append(f"{short} {distinct[0]}")
        elif distinct:
            shown = ", ".join(clip(v, 40) for v in distinct[:_TITLE_SHOWN])
            more = (
                f" and {len(distinct) - _TITLE_SHOWN} more" if len(distinct) > _TITLE_SHOWN else ""
            )
            missing.append(f"{long} has more than one value ({shown}{more}), so none is taken")
        else:
            missing.append(f"{long} not found in the title block")
    parts = [", ".join(got) + ", from the title block"] if got else []
    text = "; ".join(parts + missing) or "no title block labels are configured"
    # A used cell takes the words of its own row, so a duplicate text elsewhere is not used.
    # Words are sorted once and each looks only at the rows within the tolerance of its top.
    tol = parsing["pdf_row_tolerance_word_heights"] * _median_h(words)
    tops = [-y for y in ys]
    need: dict[int, Counter] = {}
    for r, c in used:
        need.setdefault(r, Counter()).update(grid[r][c].split())
    taken: set[int] = set()
    for w in sorted(words, key=lambda w: w.x0):
        parts = w.text.split()
        if not parts:
            continue
        for r in range(bisect_left(tops, w.top - tol), bisect_right(tops, w.top + tol)):
            n = need.get(r)
            if n and all(n[t] > 0 for t in parts):
                n.subtract(parts)
                taken.add(id(w))
                break
    unused = [w for w in words if id(w) not in taken]
    return values, _str(values.get("sheet_number")), text, unused


def _median_h(words: list[_Word]) -> float:
    return statistics.median(w.h for w in words) if words else 0.0


def _regions(words: list[_Word], gap_h: float) -> list[list[_Word]]:
    """Split words where the blank gap between lines is taller than gap_h word heights."""
    limit = gap_h * _median_h(words)
    regions: list[list[_Word]] = []
    bottom = 0.0
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        if regions and w.top - bottom <= limit:
            regions[-1].append(w)
            bottom = max(bottom, w.bottom)
        else:
            regions.append([w])
            bottom = w.bottom
    return regions


class _Page:
    """Everything one page adds to the result."""

    def __init__(self, raw: dict, cfg: Config, file: str) -> None:
        self.cfg, self.file, self.out = cfg, file, Parsed()
        self.parsing = cfg.column_maps["parsing"]
        self.n = int(_num(raw.get("n")))
        self.raw = raw
        self.parts: list[str] = []  # coverage text
        self.pg = f"page={self.n}"
        self.method = Method.PDF_TEXT
        self.unread_at = 0  # where the title block "not read" count goes in the coverage text

    def unread(self, words: list[_Word]) -> None:
        if words:
            self.parts.insert(
                self.unread_at, f"{len(words)} words in the title block area not read"
            )

    def unp(self, kind: str, raw: str, reason: str, locator: str, method: Method | None = None):
        src = Source(self.file, locator, method or self.method, Confidence.LOW)
        self.out.unparsed.append(Unparsed(kind, clip(raw), _reason(reason), src))

    def take(self, part: Parsed, cap: Callable[[Source], Source] | None) -> None:
        """Add a table result, capping the sources `cap` selects at MEDIUM."""
        if cap:
            for p in part.panels:
                apply_to_sources(p, cap)
            if len(part.coverage) == len(part.panels):  # one entry per panel, in panel order
                part.coverage = [
                    replace(c, confidence_summary=confidence_summary(p))
                    for c, p in zip(part.coverage, part.panels, strict=True)
                ]
        self.out.panels += part.panels
        self.out.unparsed += part.unparsed
        self.out.coverage += part.coverage

    def entry(self) -> CoverageEntry:
        text = f"page {self.n}: " + "; ".join(self.parts)
        return CoverageEntry(self.file, f"page {self.n}", text, self.method.value, _NO_SUMMARY)


_WORDS_CAP = medium_cap(WORDS_NOTE)


def _band_cap(src: Source) -> Source:
    """Words above a ruled table have no drawn grid: their locator row is below 0."""
    return _WORDS_CAP(src) if re.search(r"; r=-\d+(;|$)", src.locator) else src


def _lead(words: list[_Word]) -> str:
    return " ".join(w.text for w in words[:12])


def _route(pg: _Page, cls: str, chars: float, words: list[_Word], note: str) -> None:
    """One page item for a page that is listed and not read. M4 takes these by class."""
    p, img = pg.raw.get("paths"), _num(pg.raw.get("image_area_fraction"))
    loc = f"page={pg.n}; class={cls}; chars={int(chars)}; paths={int(_num(p))}; image={img:.2f}"
    pg.unp("page", _lead(words), note, loc)


def _in_box(w: _Word, b: tuple[float, float, float, float]) -> bool:
    cx, cy = w.centre()
    return b[0] <= cx <= b[2] and b[1] <= cy <= b[3]


def _crop_boxes(raw: dict, crop: _Crop) -> list[tuple[float, float, float, float]]:
    """Boxes of the ruled tables centred in the title block area: their words are theirs."""
    out = []
    for t in _list(raw.get("tables")):
        bbox = [_num(v) for v in _list(t.get("bbox"))] if isinstance(t, dict) else []
        if len(bbox) == 4 and crop.holds(((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)):
            out.append((bbox[0], bbox[1], bbox[2], bbox[3]))
    return out


def _title(
    pg: _Page, words: list[_Word], crop: _Crop, aliases: dict, boxes: list
) -> tuple[list[_Word], list[_Word]]:
    """Read the title block. Returns the words left for the table finder, and the crop words the
    reader did not use and that sit in no crop table."""
    if not crop.usable:
        why = (
            f"page is rotated {crop.rotation} degrees"
            if crop.rotation
            else "page size is not usable"
        )
        pg.parts.append(f"{why}; title block not read")
        return words, []
    inside = [w for w in words if crop.holds(w.centre())]
    _, sheet, text, unused = _read_title(inside, pg.parsing, aliases)
    pg.parts.append(text)
    left = [w for w in unused if not any(_in_box(w, b) for b in boxes)]
    pg.unread_at = len(pg.parts)
    if sheet:
        pg.pg += f"; sheet={sheet}"
    gone = {id(w) for w in inside}
    return [w for w in words if id(w) not in gone], left


def _band_rows(
    pg: _Page, bbox: list[float], free: list[_Word]
) -> tuple[list[list[str]], list[_Word]]:
    """Rows of the words just above a ruled table, which may hold its panel name."""
    x0, top, x1 = bbox[0], bbox[1], bbox[2]
    reach = pg.parsing["pdf_region_gap_word_heights"] * _median_h(free)
    edge = pg.parsing["pdf_row_tolerance_word_heights"]
    band = [
        w
        for w in free
        if w.upright
        and x0 <= w.centre()[0] <= x1
        and top - reach <= w.bottom  # the blank gap under the line, as for regions
        and w.bottom <= top + edge * w.h
    ]
    if not band:
        return [], []
    built = text_grid(
        [w.item() for w in band],
        pg.parsing["pdf_row_tolerance_word_heights"],
        pg.parsing["pdf_column_gap_fraction"],
    )
    rows = []
    for row in built[0] if built else []:
        # A lone title line ("Panel LP-24") holds a key and its value.
        cells = [c for c in row if c]
        if len(cells) == 1 and " " in cells[0] and any(ch.isdigit() for ch in cells[0]):
            key, _, value = cells[0].rpartition(" ")
            cells = [key, value]
        rows.append(cells)
    return rows, band


def _ruled(
    pg: _Page, tables: list[tuple[int, dict]], free: list[_Word]
) -> tuple[int, int, set[int]]:
    """Tables read and listed, and the ids of the band words a panel came from."""
    read = listed = 0
    used: set[int] = set()
    for k, t in tables:
        rows = [[_str(c) for c in r] for r in _list(t.get("rows")) if isinstance(r, list)]
        loc = f"{pg.pg}; table={k}"
        if sum(len(r) for r in rows) > rawdrawing.MAX_TABLE_CELLS:
            pg.unp("table", "", "ruled table is over the cell cap, so it is not read", loc)
            listed += 1
            continue
        cap = None
        part = rows_to_panels(
            rows,
            pg.cfg,
            file=pg.file,
            method=Method.PDF_TEXT,
            locate=lambda i, loc=loc: f"{loc}; r={i}",
        )
        if not part.panels and any(u.reason == "no panel name" for u in part.unparsed):
            bbox = [_num(v) for v in _list(t.get("bbox"))]
            above, band = _band_rows(pg, bbox, free) if len(bbox) == 4 else ([], [])
            if above:
                width = max(len(r) for r in rows) if rows else 0
                head = [[*r, *[""] * (width - len(r))] for r in above]
                shift = len(head)
                part = rows_to_panels(
                    [*head, *rows],
                    pg.cfg,
                    file=pg.file,
                    method=Method.PDF_TEXT,
                    locate=lambda i, loc=loc, shift=shift: f"{loc}; r={i - shift}",
                )
                if part.panels:
                    used |= {id(w) for w in band}
                    cap = _band_cap
        if part.panels:
            read += 1
        else:
            listed += 1
        pg.take(part, cap)
    return read, listed, used


def _no_header(part: Parsed) -> bool:
    return not part.panels and all(u.kind in ("table", "column") for u in part.unparsed)


def _clusters(pg: _Page, free: list[_Word]) -> tuple[int, int, int]:
    read = listed = shared_cells = 0
    for k, region in enumerate(_regions(free, pg.parsing["pdf_region_gap_word_heights"])):
        loc = f"{pg.pg}; region={k}"
        built = text_grid(
            [w.item() for w in region],
            pg.parsing["pdf_row_tolerance_word_heights"],
            pg.parsing["pdf_column_gap_fraction"],
        )
        if built is None:
            pg.unp(
                "table",
                "",
                f"words of {len(region)} texts would make a grid over the cell cap, so they are not read",
                loc,
            )
            listed += 1
            continue
        grid, ys, shared = built
        shared_cells += shared
        part = rows_to_panels(
            grid,
            pg.cfg,
            file=pg.file,
            method=Method.PDF_TEXT,
            locate=lambda i, loc=loc, ys=ys: f"{loc}; y={-ys[i]:g}",
        )
        if _no_header(part):
            first = next((r for r in grid if any(r)), [])
            why = f"text has no panel schedule header, so its {len(region)} words are not read"
            pg.unp("table", ", ".join(c for c in first if c), why, f"{loc}; y={-ys[0]:g}")
            listed += 1
            continue
        read += 1
        pg.take(part, _WORDS_CAP)
    return read, listed, shared_cells


def _overlap(w: _Word, a: _Annot) -> bool:
    return w.x0 < a.x1 and a.x0 < w.x1 and w.top < a.bottom and a.top < w.bottom


def _annotation_path(pg: _Page, annots: list[_Annot], words: list[_Word]) -> bool:
    """Read annotation text as a table. Returns True when it gave a panel."""
    pg.method = Method.PDF_ANNOT
    items = [TextItem(a.x0, -a.top, a.bottom - a.top, a.text, a.x1) for a in annots]
    loc = f"{pg.pg}; annots"
    built = text_grid(
        items, pg.parsing["pdf_row_tolerance_word_heights"], pg.parsing["pdf_column_gap_fraction"]
    )
    if built is None:
        why = f"annotation text of {len(items)} texts would make a grid over the cell cap, so it is not read"
        pg.unp("table", "", why, loc)
        pg.parts.append(f"annotation table listed, not read ({len(items)} texts)")
        return False
    grid, ys, _ = built
    # The same grid built from annotation numbers tells which cell each annotation landed in.
    where: dict[int, tuple[int, int]] = {}
    marked = text_grid(
        [TextItem(a.x0, -a.top, a.bottom - a.top, str(i), a.x1) for i, a in enumerate(annots)],
        pg.parsing["pdf_row_tolerance_word_heights"],
        pg.parsing["pdf_column_gap_fraction"],
    )
    for r, row in enumerate(marked[0] if marked else []):
        for c, cell in enumerate(row):
            where |= {int(i): (r, c) for i in cell.split() if i.isdigit()}
    low, unplaced, clash = set(), 0, {}
    for i, a in enumerate(annots):
        near = [w for w in words if _overlap(w, a)]
        shown = " ".join(w.text for w in sorted(near, key=lambda w: (round(w.top), w.x0)))
        if not near or _fold(shown) == _fold(a.text):
            continue
        r, c = where.get(i, (-1, -1))
        if r >= 0 and _fold(a.text) in _fold(grid[r][c]):  # the cell holding it, equal or not
            low.add((r, c))
            clash.setdefault((r, c), (a.text, shown))
        else:
            unplaced += 1
    part = rows_to_panels(
        grid,
        pg.cfg,
        file=pg.file,
        method=Method.PDF_ANNOT,
        locate=lambda i: f"{loc}; y={-ys[i]:g}",
        low_cells=low,
        low_note=DISAGREE_NOTE,
    )
    # tabular caps only the cells it reads as values; a circuit number or panel name stays as read
    capped = sum(
        DISAGREE_NOTE in v.source.note
        for p in part.panels
        for u in (p, *p.circuits)
        for f in fields(u)
        if isinstance((v := getattr(u, f.name)), Value) and v.source is not None
    )
    for (r, c), (text, seen) in islice(clash.items(), MAX_LISTED_PER_PAGE):
        why = f"annotation text {text!r} and page text {seen!r} disagree"
        pg.unp("cell", text, why, f"{loc}; y={-ys[r]:g}; col={c}")
    if clash:
        pg.parts.append(
            f"{len(clash)} cells where annotation text and page text disagree, "
            f"{'listed' if len(clash) <= MAX_LISTED_PER_PAGE else f'{MAX_LISTED_PER_PAGE} listed'}; "
            f"{capped} values marked LOW"
        )
    if unplaced:
        pg.parts.append(
            f"{unplaced} annotations disagree with page text and are not placed in a cell"
        )
    if _no_header(part):
        first = next((r for r in grid if any(r)), [])
        why = (
            f"annotation text has no panel schedule header, so its {len(items)} texts are not read"
        )
        pg.unp("table", ", ".join(c for c in first if c), why, f"{loc}; y={-ys[0]:g}")
        return False
    pg.take(part, medium_cap(ANNOT_NOTE))
    return any(p.circuits for p in part.panels)


def _read_page(raw: dict, cfg: Config, file: str) -> Parsed:
    pg = _Page(raw, cfg, file)
    parsing = pg.parsing
    if raw.get("skipped"):
        why = _str(raw.get("skipped"))
        pg.unp("page", "", why, pg.pg)
        pg.parts.append(f"not read: {why}")
        pg.out.coverage.append(pg.entry())
        return pg.out
    cls = classify(raw, parsing)
    chars = _num(raw.get("chars"))
    words, bad = _words(raw.get("words"))
    annots, bad_annots = _annots(raw.get("annots"))
    pg.parts.append(f"class {cls}, {int(chars)} chars, {int(_num(raw.get('paths')))} paths")
    if cls == SCANNED:
        _route(pg, cls, chars, words, OCR_LAYER_NOTE if chars > 0 else SCANNED_NOTE)
        pg.parts.append("routed to manual check, nothing read")
        pg.out.coverage.append(pg.entry())
        return pg.out
    crop = _Crop(raw, parsing)
    aliases = cfg.column_maps["title_block"]
    free, left = _title(pg, words, crop, aliases, _crop_boxes(raw, crop))
    if cls == TEXT:
        _text_page(pg, raw, crop, free, left, annots, bad, bad_annots)
    else:
        pg.unread(left)
        _vector_page(pg, cls, crop, words, free, annots, bad_annots)
    pg.out.coverage.append(pg.entry())
    return pg.out


def _has_schedule_header(pg: _Page, t: dict) -> bool:
    rows = [[_str(c) for c in r] for r in _list(t.get("rows")) if isinstance(r, list)]
    if sum(len(r) for r in rows) > rawdrawing.MAX_TABLE_CELLS:
        return True  # _ruled lists it as over the cap
    part = rows_to_panels(
        rows, pg.cfg, file=pg.file, method=Method.PDF_TEXT, locate=lambda i: f"r={i}"
    )
    return not _no_header(part)


def _text_page(pg, raw, crop, free, left, annots, bad, bad_annots) -> None:
    tables = [
        (k, t)
        for k, t in enumerate(_list(raw.get("tables")))
        if isinstance(t, dict) and len(_list(t.get("bbox"))) == 4
    ]
    kept, centres, crop_tables = [], [], 0
    for k, t in tables:
        x0, top, x1, bottom = (_num(v) for v in t["bbox"])
        c = ((x0 + x1) / 2, (top + bottom) / 2)
        # A table in the title block corner is read when it has a schedule header; otherwise it
        # is almost always the title block itself, and it is counted, not listed.
        if not crop.holds(c) or _has_schedule_header(pg, t):
            kept.append((k, t))
            centres.append((x0, top, x1, bottom))
        else:
            crop_tables += 1
    outside = [
        w
        for w in free
        if not any(
            x0 <= w.centre()[0] <= x1 and t <= w.centre()[1] <= b for x0, t, x1, b in centres
        )
    ]
    # A table read as a schedule may take its panel name line from the crop words nobody used.
    read_t, listed_t, used = _ruled(pg, kept, [*outside, *left])
    outside = [w for w in outside if id(w) not in used]
    pg.unread([w for w in left if id(w) not in used])
    upright = [w for w in outside if w.upright]
    read_c, listed_c, shared = _clusters(pg, upright) if upright else (0, 0, 0)
    pg.parts.append(f"{read_t} ruled tables read, {listed_t} listed")
    if crop_tables:
        pg.parts.append(f"{crop_tables} tables in the title block area not read")
    pg.parts.append(f"{read_c} word clusters read, {listed_c} listed")
    if shared:
        pg.parts.append(f"{shared} word-cluster cells shared a column with another cell")
    if n := len(outside) - len(upright):
        pg.parts.append(f"{n} rotated words not clustered")
    if bad:
        pg.parts.append(f"{bad} words with no usable position not read")
    if annots or bad_annots:
        pg.parts.append(f"{len(annots) + bad_annots} annotations not read")


def _vector_page(pg, cls, crop, words, free, annots, bad_annots) -> None:
    usable = [a for a in annots if not crop.holds(a.centre())]
    in_crop = len(annots) - len(usable)
    if usable:
        subs: dict[str, int] = {}
        for a in usable:
            subs[a.subtype] = subs.get(a.subtype, 0) + 1
        pg.parts.append(
            f"{len(usable)} annotations read ("
            + ", ".join(f"{k} {v}" for k, v in sorted(subs.items()))
            + ")"
        )
        read = _annotation_path(pg, usable, words)
    else:
        read = False
        pg.parts.append("no annotation text on the page")
    if in_crop:
        pg.parts.append(f"{in_crop} annotations in the title block area not read")
    if bad_annots:
        pg.parts.append(f"{bad_annots} annotations with no usable position not read")
    if read:
        left = [w for w in free if not any(_overlap(w, a) for a in usable)]
        if left:
            why = f"{len(left)} page words outside the annotations are not read"
            pg.unp("text", _lead(sorted(left, key=lambda w: (w.top, w.x0))), why, f"{pg.pg}; words")
            pg.parts.append(f"{len(left)} page words outside the annotations not read")
    else:
        pg.method = Method.PDF_TEXT
        chars = _num(pg.raw.get("chars"))
        _route(pg, cls, chars, words, FEW_CHARS_NOTE if chars > 0 else SHX_NOTE)


def parse_pages(dump: dict, cfg: Config, file: str) -> Parsed:
    """Never raises on content. A page that fails is listed, and adds nothing else."""
    out = Parsed()
    pages = _list(dump.get("pages")) if isinstance(dump, dict) else []
    for w in _list(dump.get("warnings") if isinstance(dump, dict) else None)[:_MAX_WARNINGS]:
        if text := _str(w):
            src = Source(file, "file", Method.PDF_TEXT, Confidence.LOW)
            out.unparsed.append(Unparsed("file", clip(text), _reason(f"reader note: {text}"), src))
    if not pages:
        src = Source(file, "page=0", Method.PDF_TEXT, Confidence.LOW)
        out.unparsed.append(Unparsed("page", "", "the PDF holds no readable pages", src))
        return out
    for i, raw in enumerate(pages, 1):
        raw = raw if isinstance(raw, dict) else {}
        try:
            part = _read_page(raw, cfg, file)
        except Exception as e:  # noqa: BLE001  a hostile dump must not stop the run; the page is listed
            n = int(_num(raw.get("n"), i))
            src = Source(file, f"page={n}", Method.PDF_TEXT, Confidence.LOW)
            why = _reason(f"page could not be read ({type(e).__name__})")
            part = Parsed(unparsed=[Unparsed("page", "", why, src)])
            part.coverage.append(
                CoverageEntry(
                    file, f"page {n}", f"page {n}: not read: {why}", "pdf_text", _NO_SUMMARY
                )
            )
        out.panels += part.panels
        out.unparsed += part.unparsed
        out.coverage += part.coverage
    return out


def parse_file(path: Path, cfg: Config) -> Parsed:
    path = Path(path)
    dump = read_pages(path, cfg)
    out = parse_pages(dump, cfg, path.name)
    out.provenance = {path.name: provenance(dump)}
    return out


__all__ = [
    "SUFFIXES",
    "child_main",
    "classify",
    "parse_file",
    "parse_pages",
    "provenance",
    "read_pages",
]
