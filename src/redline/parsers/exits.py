"""Owner-supplied exits.csv and paths.csv. Read after every drawing, since they name sheets."""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

from redline.config import Config
from redline.model import (
    Confidence,
    CoverageEntry,
    Device,
    EgressPath,
    Method,
    Project,
    Source,
    Unparsed,
    Value,
    clip,
)
from redline.parsers.csv_xlsx import MAX_ROWS, InputError, _text_rows
from redline.units import length_unit

NAMES = ("exits.csv", "paths.csv")
EXIT_COLUMNS = ("sheet", "x", "y", "label")  # plus optional "units"
PATH_COLUMNS = ("sheet", "path", "seq", "x", "y")
OWNER_UNITS = ("mm", "cm", "m", "in", "ft")
_UNITS_UNKNOWN = "exits.csv units are unknown or disagree"
REPEATED_SHEET_NOTE = "sheet read more than once"
_WIDE = "row has more cells than the header"


def _num(text: str) -> float | None:
    try:
        x = float(text.strip())
    except ValueError:
        return None
    return x if math.isfinite(x) else None


class _File:
    """One CSV read as dicts by header; keeps what it lists."""

    def __init__(self, path: Path, required: tuple[str, ...], optional: tuple[str, ...], project):
        self.name = path.name
        self.project = project
        self.rows: list[tuple[int, dict[str, str], list[str]]] = []  # line number, cells, raw
        self.listed = 0
        self.cut = False
        self.wide: set[int] = set()  # lines with a non-blank cell beyond the header
        self.ok = False
        low = Source(self.name, "file", Method.CSV, Confidence.LOW)
        try:
            raw, _ = _text_rows(path)
        except (InputError, ValueError) as e:
            self.list("table", self.name, f"file not used: {' '.join(str(e).split())}", low)
            return
        raw = [r for r in raw if any(c.strip() for c in r)]
        if not raw:
            self.list("table", self.name, "file not used: no header row", low)
            return
        head = [c.strip().casefold() for c in raw[0]]
        if missing := [c for c in required if c not in head]:
            why = f"file not used: missing column {', '.join(missing)}"
            self.list("table", self.name, why, low)
            return
        extra, seen = [], set()
        for c, h in zip(raw[0], head, strict=True):
            if h in seen or h not in (*required, *optional):
                extra.append(c.strip())
            seen.add(h)
        if extra:
            why = f"column not read: {', '.join(clip(c) for c in extra)}"
            self.list("column", clip(", ".join(extra)), why, low)
        body = raw[1:]
        if len(body) > MAX_ROWS:
            why = f"file has more than {MAX_ROWS} rows; the rest are not read"
            self.list("table", self.name, why, low)
            body = body[:MAX_ROWS]
            self.cut = True
        for n, r in enumerate(body, 2):
            cells = {}
            for h, c in zip(head, r, strict=False):
                cells.setdefault(h, c.strip())
            self.rows.append((n, cells, r))
            if any(c.strip() for c in r[len(head) :]):
                self.wide.add(n)
                self.bad_row(n, r, _WIDE)
        self.ok = True

    def src(self, n: int, conf: Confidence = Confidence.HIGH, note: str = "") -> Source:
        return Source(self.name, f"row {n}", Method.CSV, conf, note)

    def list(self, kind: str, raw: str, why: str, src: Source) -> None:
        self.listed += 1
        self.project.unparsed.append(Unparsed(kind, raw, why, src))

    def bad_row(self, n: int, raw: list[str], why: str) -> None:
        self.list("row", clip(",".join(raw)), why, self.src(n, Confidence.LOW))


def _sheet_of(f: _File, n: int, cells: dict, raw: list[str], sheets: dict[str, str]) -> str | None:
    sheet = sheets.get(cells.get("sheet", "").casefold())
    if sheet is None:
        f.bad_row(n, raw, "names no DWG or DXF sheet that was read; not used")
    return sheet


def _lower_blocks(project: Project, why: str, keep: set[str] = frozenset()) -> None:
    """Door-block exits are not trusted when exits.csv is not fully used, except on `keep` sheets."""
    note = f"exits.csv {why}; this block exit is not checked"
    for d in project.devices:
        if d.type != "exit_door" or d.detection != "block":
            continue
        if (d.sheet.value or "").casefold() in keep:
            continue
        for key in ("x", "y"):
            v = getattr(d, key)
            if v.source is not None:
                low = dataclasses.replace(v.source, confidence=Confidence.LOW, note=note)
                setattr(d, key, dataclasses.replace(v, source=low))


def _exits(path: Path, project: Project, sheets: dict[str, str]) -> None:
    f = _File(path, EXIT_COLUMNS, ("units",), project)
    if not f.ok:
        _lower_blocks(project, "was not used")
        return
    by_sheet: dict[str, list[tuple[int, dict, list[str]]]] = {}
    for n, cells, raw in f.rows:
        if (sheet := _sheet_of(f, n, cells, raw, sheets)) is not None:
            by_sheet.setdefault(sheet, []).append((n, cells, raw))
    for sheet, rows in by_sheet.items():
        for n, cells, raw in rows:
            xy, bad = [], n in f.wide
            for key in ("x", "y"):
                v = _num(cells.get(key, ""))
                bad |= v is None
                if v is not None and n not in f.wide:
                    src = f.src(n)
                else:
                    why = _WIDE if n in f.wide else f"{key} is not a finite number"
                    src = f.src(n, Confidence.LOW, why)
                xy.append(Value(v, src, raw=cells.get(key, "")))
            if bad and n not in f.wide:
                f.bad_row(n, raw, "x or y is not a finite number; this exit gets no distance check")
            src = f.src(n)
            project.devices.append(
                Device(
                    "exit_door",
                    src,
                    tag=Value(cells.get("label") or f"row {n}", src),
                    sheet=Value(sheet, src),
                    x=xy[0],
                    y=xy[1],
                    detection="list",
                )
            )
        _owner_units(f, project, sheet, rows)
        moved = 0
        for d in project.devices:
            if (
                d.type == "exit_door"
                and d.detection != "list"
                and (d.sheet.value or "").casefold() == sheet.casefold()
            ):
                d.detection = "unused"
                moved += 1
        if moved:
            what = f"{moved} exit_door blocks not used: exits.csv lists the exits of this sheet"
            project.coverage.append(CoverageEntry(sheet, "exit_door blocks", what, "dxf_block", ""))
    if f.cut or len(f.rows) > sum(len(r) for r in by_sheet.values()):
        keep = {s.casefold() for s in by_sheet}
        _lower_blocks(project, "has rows that are not used", keep)
    listed_rows = f.listed
    what = f"{len(f.rows)} rows, {len(by_sheet)} sheets with exits, {listed_rows} listed"
    project.coverage.append(CoverageEntry(f.name, "table", what, Method.CSV.value, ""))


def _owner_units(f: _File, project: Project, sheet: str, rows: list) -> None:
    words = [cells.get("units", "").casefold() for _, cells, _ in rows]
    if not any(words):
        return
    old = project.sheet_units.get(sheet)
    if old is not None and old.source is not None and old.source.note == REPEATED_SHEET_NOTE:
        return
    if len(set(words)) == 1 and words[0] in OWNER_UNITS:
        word = words[0]
        said = "unitless" if old is None or old.raw in (None, "") else old.raw
        differs = old is None or old.value != length_unit(word)
        note = f"the drawing states {said}" if differs else "the drawing states the same"
        contested = differs and old is not None and old.usable
        conf = Confidence.MEDIUM if contested else Confidence.HIGH
        src = Source(f.name, "units", Method.CSV, conf, note)
        project.sheet_units[sheet] = Value(word, src, raw=word)
        if contested:
            why = (
                f"exits.csv states units {word}. The drawing header states {old.raw}."
                f" Distances on this sheet use {word}. Reviewer to confirm the unit [VERIFY]."
            )
            f.list("sheet", sheet, why, Source(f.name, "units", Method.CSV, Confidence.MEDIUM))
        return
    src = Source(f.name, "units", Method.CSV, Confidence.LOW, _UNITS_UNKNOWN)
    project.sheet_units[sheet] = Value(None, src, raw=", ".join(sorted(set(words))))
    for n, cells, raw in rows:
        f.bad_row(n, raw, f"units {clip(cells.get('units') or 'blank')}: {_UNITS_UNKNOWN}")


def _paths(path: Path, project: Project, sheets: dict[str, str]) -> None:
    f = _File(path, PATH_COLUMNS, (), project)
    if not f.ok:
        return
    groups: dict[tuple[str, str], list] = {}
    dropped: dict[str, list[int]] = {}
    for n, cells, raw in f.rows:
        if (sheet := _sheet_of(f, n, cells, raw, sheets)) is not None:
            groups.setdefault((sheet, cells.get("path", "")), []).append((n, cells, raw))
        else:
            dropped.setdefault(cells.get("path", ""), []).append(n)
    stubs: dict[str, set[str]] = {}  # a lone row may be a vertex whose path name has a typo
    for (sheet, name), rows in groups.items():
        if len(rows) < 2:
            stubs.setdefault(sheet, set()).add(name)
    for (sheet, name), rows in groups.items():
        points, seen = [], set()
        notes = [f"row {n}: names no sheet that was read" for n in dropped.get(name, [])]
        others = len(stubs.get(sheet, ())) - (name in stubs.get(sheet, ()))
        if others:
            notes.append(f"{others} other path(s) on this sheet have fewer than two vertex rows")
        if f.cut:
            notes.append(f"rows past {MAX_ROWS} are not read")
        for n, cells, raw in rows:
            seq = cells.get("seq", "")
            x, y = _num(cells.get("x", "")), _num(cells.get("y", ""))
            try:
                k = int(seq)
            except ValueError:
                k = None
            why = None
            if n in f.wide:
                why = _WIDE
            elif k is None:
                why = "seq is not a whole number"
            elif k in seen:
                why = "seq repeats within the path"
            elif x is None or y is None:
                why = "x or y is not a finite number"
            if why:
                if n not in f.wide:
                    f.bad_row(n, raw, f"path {clip(name)}: {why}; this vertex is not used")
                notes.append(f"row {n}: {why}")
                if k is not None:
                    seen.add(k)
                continue
            seen.add(k)
            points.append((k, x, y))
        points.sort()
        if len(points) < 2 and not notes:
            notes.append("fewer than two vertices")
            f.bad_row(rows[0][0], rows[0][2], f"path {clip(name)} has fewer than two vertices")
        elif len(points) < 2:
            notes.append("fewer than two usable vertices")
        conf = Confidence.LOW if notes else Confidence.HIGH
        src = Source(f.name, f"path {clip(name)}", Method.CSV, conf, "; ".join(notes))
        project.paths.append(EgressPath(name, sheet, src, [(x, y) for _, x, y in points]))
    what = f"{len(f.rows)} rows, {len(groups)} paths, {f.listed} listed"
    project.coverage.append(CoverageEntry(f.name, "table", what, Method.CSV.value, ""))


def apply(files: list[Path], project: Project, cfg: Config) -> None:
    """Read each file and add exits, units and paths to the project. Never raises on content."""
    sheets = {s.casefold(): s for s in project.sheet_units}
    # exits first, so a path file read before it cannot change what the exits see
    for path in sorted(files, key=lambda p: p.name.casefold() != "exits.csv"):
        read = _exits if path.name.casefold() == "exits.csv" else _paths
        try:
            read(path, project, sheets)
        except Exception as ex:  # noqa: BLE001 - an odd file is listed, the rest is still read
            src = Source(path.name, "file", Method.CSV, Confidence.LOW)
            why = f"file could not be read ({type(ex).__name__})"
            if read is _exits:
                _lower_blocks(project, "could not be read")
            project.unparsed.append(Unparsed("table", path.name, why, src))


__all__ = ["EXIT_COLUMNS", "NAMES", "OWNER_UNITS", "PATH_COLUMNS", "apply"]
