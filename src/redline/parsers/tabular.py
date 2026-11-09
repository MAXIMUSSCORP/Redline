"""Rows of text cells to panels. Shared by the CSV, TXT and XLSX reader and later parsers."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, fields, replace
from functools import lru_cache
from itertools import takewhile

from redline.config import Config, default_value
from redline.model import (
    MAX_INT,
    Circuit,
    Confidence,
    CoverageEntry,
    Method,
    Panel,
    Source,
    Unparsed,
    Value,
    check_value,
    derived,
)
from redline.units import normalize_size

Locate = Callable[[int], str]


@dataclass
class Parsed:
    panels: list[Panel] = field(default_factory=list)
    unparsed: list[Unparsed] = field(default_factory=list)
    coverage: list[CoverageEntry] = field(default_factory=list)


def normalize_header(text: str) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in text.lower()).split())


def _value_fields(cls: type) -> set[str]:
    return {f.name for f in fields(cls) if f.default_factory == Value.missing}


SCHEDULE_KEYS = _value_fields(Circuit) | {"panel_name", "circuit_number", "load_kva", "phase"}
BLOCK_KEYS = _value_fields(Panel) | {"panel_name"}
_FIELD_OF = {"load_kva": "load_va", "phase": "phases_used"}
_INT_FIELDS = {"poles", "insulation_temp_c", "conductors_in_raceway", "phases", "wires"}
_TEMP = {"C": 1, "°C": 1}
_UNITS: dict[str, dict[str, int]] = {
    "breaker_a": {"A": 1},
    "bus_rating_a": {"A": 1},
    "main_breaker_a": {"A": 1},
    "voltage_v": {"V": 1},
    "length_m": {"M": 1},
    "insulation_temp_c": _TEMP,
    "ambient_c": _TEMP,
}
_LOADS = ("load_va", "demand_va_supplied")
_SIZES = ("conductor_size", "bonding_size")
_TEXTS = (
    *_SIZES,
    "conductor_material",
    "phases_used",
    "load_type",
    "description",
    "fed_from",
    "location",
)
_NUM_TOKEN = re.compile(r"-?[0-9,]*(?:\.[0-9]+)?")
_THOUSANDS = re.compile(r"-?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?")
_SLASH_V = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*/\s*([0-9]+(?:\.[0-9]+)?)\s*v?", re.IGNORECASE)
# Unit words a header may carry after its alias; any not read by the field is refused.
_UNIT_WORDS = {
    "va",
    "kva",
    "kw",
    "w",
    "mw",
    "hp",
    "ft",
    "feet",
    "in",
    "mm",
    "cm",
    "f",
    "k",
    "a",
    "ka",
    "v",
    "kv",
    "mva",
    "m",
    "km",
    "c",
}
_PHASES = re.compile(r"[ABC]([\s,/&+-]*[ABC])*", re.IGNORECASE)


@dataclass(frozen=True)
class _At:
    """Where a cell came from, and how far its header can be trusted."""

    file: str
    locator: str
    method: Method
    conf: Confidence
    note: str = ""
    unit: str = ""  # unit word left in the header after the alias match
    in_block: bool = False

    def source(self, conf: Confidence | None = None, note: str | None = None) -> Source:
        return Source(
            self.file,
            self.locator,
            self.method,
            self.conf if conf is None else conf,
            self.note if note is None else note,
        )


def _low(at: _At, text: str, why: str) -> Value:
    return Value(None, at.source(Confidence.LOW, why), text)


def _split_number(t: str) -> tuple[float, str] | str:
    tok = _NUM_TOKEN.match(t).group()  # the pattern matches the empty string, so never None
    if not any(c in "0123456789" for c in tok):
        return "not a number"
    if "," in tok and not _THOUSANDS.fullmatch(tok):
        return "comma is not a thousands separator"
    num = float(tok.replace(",", ""))
    if not math.isfinite(num) or abs(num) > MAX_INT:
        return "too large a number"
    return num, t[len(tok) :].strip()


def _numeric(fld: str, key: str, t: str, cfg: Config, at: _At) -> Value:
    if fld == "voltage_v" and (m := _SLASH_V.fullmatch(t)):
        if not at.in_block:
            return _low(at, t, "a/b voltage on a circuit")
        # a/b voltage: b is taken as line to line. That is a pick, so MEDIUM at most.
        conf = min(at.conf, Confidence.MEDIUM)
        return Value(float(m[2]), at.source(conf, "line-to-line from a/b"), t)
    parsed = _split_number(t)
    if isinstance(parsed, str):
        return _low(at, t, parsed)
    num, rest = parsed
    unit = rest.replace(" ", "").upper()
    cell = Value(num, at.source(), t)
    read_units = ("VA", "KVA") if fld in _LOADS else _UNITS.get(fld, {})
    if not unit and at.unit and at.unit not in read_units:
        return _low(at, t, f"header unit {at.unit} not read")
    if fld in _LOADS:
        unit = unit or at.unit or ("KVA" if key == "load_kva" else "VA")
        if unit == "VA":
            return cell
        if unit == "KVA":
            kva = derived(round(num * 1000, 6), [cell], at.file, at.locator, "kVA x 1000")
            return replace(kva, raw=t)
        if unit in ("W", "KW"):
            pf = default_value(cfg, "power_factor")
            if not (isinstance(pf.value, int | float) and pf.value > 0):
                return _low(at, t, f"unit {rest} needs a power factor")
            watts = num * (1000 if unit == "KW" else 1)
            note = f"{rest} divided by the default power factor"
            va = derived(round(watts / pf.value, 6), [cell, pf], at.file, at.locator, note)
            return replace(va, raw=t)
        return _low(at, t, f"unit {rest} not read")
    if unit and unit not in _UNITS.get(fld, {}):
        return _low(at, t, f"unit {rest} not read")
    if fld in _INT_FIELDS:
        if num != int(num):
            return _low(at, t, "not a whole number")
        return replace(cell, value=int(num))
    return cell


_MATERIALS = {"cu": "Cu", "copper": "Cu", "al": "Al", "aluminum": "Al", "aluminium": "Al"}


def _text_value(fld: str, t: str, at: _At) -> Value:
    if fld in _SIZES:
        size = normalize_size(t)
        return Value(size, at.source(), t) if size else _low(at, t, "size not read")
    if fld == "conductor_material":
        mat = _MATERIALS.get(t.lower())
        return Value(mat, at.source(), t) if mat else _low(at, t, "material not read")
    if fld == "phases_used":
        letters = "".join(c for c in t.upper() if c in "ABC")
        if _PHASES.fullmatch(t) and len(set(letters)) == len(letters):
            return Value(letters, at.source(), t)
        return _low(at, t, "phase letters not read")
    return Value(t.lower() if fld == "load_type" else t, at.source(), t)


def _read(fld: str, key: str, text: str, cfg: Config, at: _At, ph: set[str]) -> Value:
    t = text.strip()
    if not t:
        return Value(None, at.source(Confidence.MISSING, "blank cell"), "")
    if t.upper() in ph:
        v = _low(at, t, "placeholder text")
    elif fld == "main_breaker_a" and t.upper() == "MLO":
        v = Value(None, at.source(note="MLO"), t)
    elif fld in _TEXTS:
        v = _text_value(fld, t, at)
    else:
        v = _numeric(fld, key, t, cfg, at)
    return check_value(fld, v)


@dataclass(frozen=True)
class _Hit:
    key: str | None
    conf: Confidence = Confidence.MISSING
    note: str = ""
    reason: str = ""
    unit: str = ""


def _matcher(mapping: dict[str, object] | None, known: set[str]) -> Callable[[str], _Hit]:
    aliases = {
        k: [a for a in (normalize_header(x) for x in v if isinstance(x, str)) if a]
        for k, v in (mapping or {}).items()
        if isinstance(v, list)
    }
    cache: dict[str, _Hit] = {}

    def settle(keys: dict[str, str], conf: Confidence, how: str) -> _Hit:
        if len(keys) > 1:
            return _Hit(None, reason=f"matches more than one field: {', '.join(sorted(keys))}")
        ((key, alias),) = keys.items()
        if key not in known:
            return _Hit(None, reason=f"key {key} is not a known field")
        note = "" if conf == Confidence.HIGH else f"header matched alias '{alias}' {how}"
        return _Hit(key, conf, note)

    def match(text: str) -> _Hit:
        if text in cache:
            return cache[text]
        n = normalize_header(text)
        if not n:
            hit = _Hit(None, reason="header has no text")
        elif exact := {k: n for k, al in aliases.items() if n in al}:
            hit = settle(exact, Confidence.HIGH, "")
        else:
            words = set(n.split())
            part = {k: a for k, al in aliases.items() for a in al if set(a.split()) <= words}
            if part:
                hit = settle(part, Confidence.MEDIUM, "by words")
                if hit.key:
                    left = words - set(part[hit.key].split())
                    hit = replace(hit, unit="".join(sorted(left & _UNIT_WORDS)).upper())
            else:
                hit = _Hit(None, reason="no alias matches")
        cache[text] = hit
        return hit

    return match


@dataclass
class _Col:
    i: int
    text: str
    hit: _Hit

    @property
    def label(self) -> str:
        return self.text or f"#{self.i + 1}"


@dataclass
class _Half:
    cols: dict[str, _Col]  # field name -> column
    lo: int
    hi: int
    side: str


@dataclass
class _Ctx:
    cfg: Config
    file: str
    method: Method
    locate: Locate
    fallback: str | None
    match: Callable[[str], _Hit]
    block_match: Callable[[str], _Hit]
    ph: set[str]
    spare: set[str]
    detect_two_column: bool
    out: Parsed
    last_name: tuple[str, Source] | None = None  # nearest header block panel name above
    last_panel: Panel | None = None  # the panel built from last_name, for the page-break flag
    pcol_panel: Panel | None = None  # last panel of the previous panel-column table
    ambiguous: set[int] = field(default_factory=set)  # lines listed, read neither way

    def unp(self, kind: str, raw: str, reason: str, locator: str) -> None:
        src = Source(self.file, locator, self.method, Confidence.LOW)
        self.out.unparsed.append(Unparsed(kind, raw, reason, src))


def _field(col: _Col) -> str:
    return _FIELD_OF.get(col.hit.key or "", col.hit.key or "")


def _resolve(cols: list[_Col], ctx: _Ctx, h: int, lo: int, hi: int, side: str) -> _Half:
    """One column per field. Two columns for one field are both left unread."""
    groups: dict[str, list[_Col]] = {}
    for c in cols:
        groups.setdefault(_field(c), []).append(c)
    kept: dict[str, _Col] = {}
    for fld, group in groups.items():
        if len(group) == 1:
            kept[fld] = group[0]
            continue
        va = [c for c in group if c.hit.key == "load_va"]
        if fld == "load_va" and len(va) == 1:
            kept[fld] = va[0]
            why = f"load already read from {va[0].label}"
            skipped = [c for c in group if c is not va[0]]
        else:
            names = " and ".join(f"'{c.label}'" for c in group)
            why = f"two columns for one field: {names}"
            skipped = group
        for c in skipped:
            ctx.unp("column", c.text, why, f"{ctx.locate(h)}; col={c.label}{side}")
    return _Half(kept, lo, hi, side)


def _plan(
    cols: list[_Col], data: list[list[str]], ctx: _Ctx, h: int, width: int
) -> tuple[list[_Half], _Col | None, int, int]:
    before = len(ctx.out.unparsed)
    used = {i for r in data for i, c in enumerate(r) if c.strip()}
    for c in cols:
        # A blank header over a blank column holds nothing to report.
        if c.hit.key is None and (c.text or c.i in used):
            ctx.unp("column", c.text, c.hit.reason, f"{ctx.locate(h)}; col={c.label}")
    keyed = [c for c in cols if c.hit.key]
    halves: list[_Half] | None = None
    seen: set[str] = set()
    for c in keyed:
        if _field(c) in seen and ctx.detect_two_column:
            left = [k for k in keyed if k.i < c.i]
            right = [k for k in keyed if k.i >= c.i]
            ckts = [k for k in keyed if _field(k) == "circuit_number"]
            exact = all(k.hit.conf == Confidence.HIGH for k in ckts)
            if exact and all(
                len(half) > 1 and sum(_field(k) == "circuit_number" for k in half) == 1
                for half in (left, right)
            ):
                halves = [
                    _resolve(left, ctx, h, 0, c.i, " (left)"),
                    _resolve(right, ctx, h, c.i, width, " (right)"),
                ]
            break
        seen.add(_field(c))
    if halves is None:
        halves = [_resolve(keyed, ctx, h, 0, width, "")]
    mapped = sum(len(x.cols) for x in halves)
    named = [x.cols["panel_name"] for x in halves if "panel_name" in x.cols]
    shared = named[0] if len(named) == 1 and len(halves) == 2 else None
    return halves, shared, mapped, mapped + len(ctx.out.unparsed) - before


@dataclass
class _Block:
    name: tuple[str, Source] | None = None
    values: dict[str, Value] = field(default_factory=dict)
    read_rows: list[tuple[int, str]] = field(default_factory=list)


def _header_block(ctx: _Ctx, rows: list[list[str]], start: int, h: int) -> _Block:
    block = _Block()
    for r in range(start, h):
        nz = [c.strip() for c in rows[r] if c.strip()]
        if not nz:
            continue
        loc = ctx.locate(r)
        raw = ", ".join(nz)
        if r in ctx.ambiguous:
            ctx.unp("row", raw, "panel row or header block line; not read", loc)
            continue
        key_text, colon, after = nz[0].partition(":")
        if colon and after.strip():
            val, extra = after.strip(), nz[1:]
        else:
            rest = nz[1:]
            val, extra = (rest[0], rest[1:]) if rest else ("", [])
        hit = ctx.block_match(key_text)
        if val and hit.key == "panel_name" and hit.conf != Confidence.HIGH:
            # "Panel LP-2,225A": a designation in the key cell is the name; the next cell is not.
            word = [t for t in key_text.split() if ctx.block_match(t).key != "panel_name"]
            if word and _DESIGNATION.search(key_text):
                extra, val = [val, *extra], " ".join(word)
                hit = replace(hit, note="panel name read from the key cell, after the word Panel")
        if hit.key is None:
            ctx.unp("row", raw, f"not a header block key: {hit.reason}", loc)
            continue
        if not val:
            ctx.unp("row", raw, f"header block key {hit.key} has no value", loc)
            continue
        at = _At(ctx.file, loc, ctx.method, hit.conf, hit.note, hit.unit, True)
        if hit.key == "panel_name":
            if block.name is not None:
                ctx.unp("row", raw, "a second panel name in the header block", loc)
                continue
            block.name = (val, at.source())
        elif hit.key in block.values:
            ctx.unp("row", raw, f"header block key {hit.key} repeated", loc)
            continue
        else:
            block.values[hit.key] = _read(hit.key, hit.key, val, ctx.cfg, at, ctx.ph)
            block.read_rows.append((r, raw))
        if extra:
            ctx.unp("row", ", ".join(extra), "extra cells on a header block line", loc)
    return block


_PAGE_NOTE = (
    "rows after a page break could not be placed; the panel-level check needs the whole panel"
)
_BLANK_NOTE = (
    "rows with a blank panel cell could not be placed; the panel-level check needs the whole panel"
)
_BELOW_NOTE = (
    "rows below the table could not be placed; the panel-level check needs the whole panel"
)


def _mark_incomplete(panel: Panel, note: str = _PAGE_NOTE) -> None:
    """Some rows could not be placed: demand and phase balance need the whole panel, so their
    inputs are LOW and those rules report NEEDS_REVIEW (as for a repeated name)."""
    for attr in ("bus_rating_a", "phases"):
        v = getattr(panel, attr)
        low = replace(v.source or panel.source, confidence=Confidence.LOW, note=note)
        setattr(panel, attr, replace(v, source=low))


def _cell(row: list[str], i: int) -> str:
    return row[i].strip() if i < len(row) else ""


def _summary(counts: Counter) -> str:
    return ", ".join(f"{c.name} {counts[c]}" for c in sorted(Confidence, reverse=True))


def _count(counts: Counter, values: Iterable[Value]) -> None:
    for v in values:
        if v.source is not None:
            counts[v.confidence] += 1


def _table(
    ctx: _Ctx, rows: list[list[str]], h: int, cols: list[_Col], start: int, end: int
) -> None:
    data = rows[h + 1 : end]
    used = max((i + 1 for r in data for i, c in enumerate(r) if c.strip()), default=0)
    width = max(len(cols), used)
    cols = cols + [_Col(i, "", ctx.match("")) for i in range(len(cols), width)]
    halves, shared, mapped, total = _plan(cols, data, ctx, h, width)
    block = _header_block(ctx, rows, start, h)
    has_panel_col = shared is not None or any("panel_name" in x.cols for x in halves)
    table_name: tuple[str, Source] | None = None
    if has_panel_col and block.name:
        name, src = block.name
        reason = "panel name in header block not used; table has a panel column"
        ctx.unp("row", name, reason, src.locator)
    if has_panel_col:
        ctx.last_name = None
    else:
        # Only a header repeated directly under the table above continues its panel.
        # A title line naming another panel ends it too ("Panel LP-1 (continued)" does not).
        # After a panel-column table the rows may belong to its last placed panel.
        above = ctx.last_panel or ctx.pcol_panel
        if block.read_rows or (ctx.last_name and not _names_only(rows[start:h], ctx.last_name[0])):
            ctx.last_name = None
        if block.name:
            table_name = ctx.last_name = block.name
        elif ctx.last_name:
            # A repeated header with no block of its own continues the panel above it.
            name, src = ctx.last_name
            note = "panel name from the header block above"
            table_name = (name, replace(src, confidence=Confidence.MEDIUM, note=note))
        else:
            if ctx.fallback:
                note = "panel name from sheet name"
                src = Source(ctx.file, ctx.locate(h), ctx.method, Confidence.MEDIUM, note)
                table_name = (ctx.fallback, src)
            else:
                for r, raw in block.read_rows:
                    ctx.unp("row", raw, "no panel name", ctx.locate(r))
            # A header-only table whose rows are not in the panel above may be its rest; a table
            # with block lines of its own is another panel.
            rest = not block.read_rows and any(c.strip() for r in rows[h + 1 : end] for c in r)
            if above and rest:
                _mark_incomplete(above)
    panels: dict[str, Panel] = {}
    stats: dict[str, Counter] = {}

    def get(name: str, src: Source) -> Panel:
        if name not in panels:
            panels[name] = Panel(name, src, **block.values)
            stats[name] = Counter()
            _count(stats[name], block.values.values())
        return panels[name]

    if table_name:
        get(*table_name)
    circuit_missing = not any("circuit_number" in x.cols for x in halves)
    blank_panel = lead_blank = placed = False
    last_placed: Panel | None = None
    for r in range(h + 1, end):
        cells = rows[r]
        if not any(c.strip() for c in cells):
            continue
        loc = ctx.locate(r)
        if circuit_missing:
            text = ", ".join(c.strip() for c in cells if c.strip())
            ctx.unp("row", text, "no circuit number column", loc)
            continue
        made = False
        for half in halves:
            ccol = half.cols.get("circuit_number")
            if ccol is None:
                continue
            pcol = half.cols.get("panel_name") or shared
            number = _cell(cells, ccol.i)
            span = [
                cells[i].strip()
                for i in range(half.lo, min(half.hi, len(cells)))
                if not (shared and i == shared.i)
            ]
            text = ", ".join(c for c in span if c)
            if not number:
                if len(halves) > 1 and not any(span):
                    continue
                total = bool(span) and any(_TOTAL_ROW.fullmatch(c) for c in span[:2])
                ctx.unp(
                    "row", text, "total row, not a circuit" if total else "no circuit number", loc
                )
                made = True
                continue
            if pcol:
                pname = _cell(cells, pcol.i)
                psrc = Source(ctx.file, ctx.locate(h), ctx.method, pcol.hit.conf, pcol.hit.note)
                panel = get(pname, psrc) if pname else None
            else:
                panel = get(*table_name) if table_name else None
            made = True
            if panel is None:
                ctx.unp("row", text, "no panel name", loc)
                blank_panel = blank_panel or bool(pcol)
                lead_blank = lead_blank or (bool(pcol) and not placed)
                continue
            placed = True
            last_placed = panel
            vals: dict[str, Value] = {}
            for fld, col in half.cols.items():
                if fld in ("panel_name", "circuit_number"):
                    continue
                at = _At(
                    ctx.file,
                    f"{loc}; col={col.label}{half.side}",
                    ctx.method,
                    col.hit.conf,
                    col.hit.note,
                    col.hit.unit,
                )
                vals[fld] = _read(fld, col.hit.key or fld, _cell(cells, col.i), ctx.cfg, at, ctx.ph)
            desc = half.cols.get("description")
            spare = desc is not None and _cell(cells, desc.i).upper() in ctx.spare
            spare = spare or vals.get("load_type", Value.missing()).value == "spare"
            src = Source(ctx.file, loc, ctx.method, ccol.hit.conf, ccol.hit.note)
            panel.circuits.append(Circuit(panel.name, number, src, is_spare=spare, **vals))
            _count(stats[panel.name], vals.values())
        if not made:
            text = ", ".join(c.strip() for c in cells if c.strip())
            ctx.unp("row", text, "no circuit number", loc)
    if blank_panel:
        # A row listed with no panel name may belong to any panel of this table.
        for panel in panels.values():
            _mark_incomplete(panel, _BLANK_NOTE)
    if lead_blank and ctx.pcol_panel:
        # Page 2 starts with rows that continue the last panel of page 1.
        _mark_incomplete(ctx.pcol_panel, _BLANK_NOTE)
    ctx.pcol_panel = last_placed if has_panel_col else None
    ctx.last_panel = panels.get(ctx.last_name[0]) if ctx.last_name else None
    for name, panel in panels.items():
        ctx.out.panels.append(panel)
        read = f"{len(panel.circuits)} circuits read; {mapped} of {total} columns mapped"
        entry = CoverageEntry(ctx.file, name, read, ctx.method.value, _summary(stats[name]))
        ctx.out.coverage.append(entry)


_CKT_TEXT_MAX = 12
# Possessive and anchored, so a long letter run is scanned once, not once per start.
_DESIGNATION = re.compile(r"(?<![A-Za-z])[A-Za-z]{2,}+-?\d")
_TOTAL_ROW = re.compile(r"(sub[\s-]*)?totals?(\s+(load|va|connected|demand))*:?", re.IGNORECASE)


def _ckt_cols(keys: list[str | None]) -> list[int]:
    return [j for j, k in enumerate(keys) if k == "circuit_number"]


def _is_circuit_row(
    ctx: _Ctx,
    row: list[str],
    keys: list[str | None],
    ckt: list[int],
    near: tuple[list[str], list[str]] = ([], []),
    any_len: bool = False,
) -> bool:
    """A number-like circuit cell, on a line that is not an exact header block key.

    any_len drops the length limit on the circuit cell (an Excel date, "2,4,6 (3 pole)"), for
    deciding whether a row cut from a table may have been a circuit.

    keys is the field key of each column of the table above, ckt its circuit column indexes
    (computed once per header so a wide header costs nothing per row), near the rows just
    above and below this one.
    """
    texts = (row[i].strip() for i in takewhile(lambda i: i < len(row), ckt))  # ckt is sorted
    ok = [
        t
        for t in texts
        if (any_len or len(t) <= _CKT_TEXT_MAX) and any(ch in "0123456789" for ch in t)
    ]
    if not ok:
        return False
    short = sum(1 for c in row if c.strip()) <= 2
    if not any_len and short and all(t[:1].isalpha() and _DESIGNATION.search(t) for t in ok):
        # "LP-2" in the circuit cell of a short line is a panel title ("LP-2,225A"). A longer
        # line ("CB1,a,800,20,1") is a circuit, and a cut one still counts for the mark.
        return False
    at = next(j for j, c in enumerate(row) if c.strip())
    first = row[at].strip()
    lone = sum(1 for c in row if c.strip()) == 1
    if lone and any(ch.isalpha() for ch in first) and not re.fullmatch(r"\d+[A-Za-z]", first):
        return False  # a lone cell with letters ("LP-2", "100A MLO", "2 of 2") is a title
    hit = ctx.block_match(first.partition(":")[0])
    if hit.key is None:
        return True
    if hit.conf == Confidence.HIGH:
        # A panel named like an exact key ("MAIN") is data only in the panel column of a row
        # with more than a key and a value whose neighbour repeats it (a panel's rows are
        # grouped). Any other such line is a block line, or _ambiguous_key_line.
        grouped = ":" not in first and any(_cell(n_, at) == first for n_ in near)
        return (
            at < len(keys)
            and keys[at] == "panel_name"
            and sum(1 for c in row if c.strip()) > 2
            and grouped
        )
    # A word match excludes only a key/value shaped line: a panel named "Panel A" is a circuit.
    if ":" in first:
        return False
    if sum(1 for c in row if c.strip()) > 2:
        return True
    # A short line is a block line only under the panel column or an unmapped one; under
    # description or another mapped field it is a circuit whose text holds a block word.
    at = next(j for j, c in enumerate(row) if c.strip())
    return at < len(keys) and keys[at] not in (None, "panel_name")


def _ambiguous_key_line(
    ctx: _Ctx, row: list[str], keys: list[str | None], near: tuple[list[str], list[str]]
) -> bool:
    """A lone exact non-panel key line under a panel column: one-circuit panel or header line."""
    cells = [c.strip() for c in row if c.strip()]
    if len(cells) < 3 or ":" in cells[0]:
        return False
    hit = ctx.block_match(cells[0])
    at = next(j for j, c in enumerate(row) if c.strip())
    return (
        hit.conf == Confidence.HIGH
        and hit.key not in (None, "panel_name")
        and at < len(keys)
        and keys[at] == "panel_name"
        and not any(_cell(n_, at) == cells[0] for n_ in near)
    )


_TOKEN_SPLIT = re.compile(r"[^\w-]+")


def _prefix(tok: str) -> str:
    return tok[: next((i for i, ch in enumerate(tok) if ch.isdigit()), len(tok))]


_REF_WORDS = frozenset({"sheet", "sht", "dwg", "drawing", "page", "pg", "rev", "revision"})


@lru_cache(maxsize=4)
def _name_tokens(name: str) -> tuple[frozenset[str], str]:
    toks = [t for t in _TOKEN_SPLIT.split(name.lower()) if t]
    return frozenset(toks), f" {' '.join(toks)} " if toks else ""


def _names_only(lines: list[list[str]], name: str) -> bool:
    """Every line between two tables either holds the panel name or no other designation.

    A line holding the name as a run of tokens ("Panel LP-1 (continued) - Page 2 of 2") keeps
    the panel unless it also holds another panel designation, a token with a letter prefix and
    a digit, whatever its letters ("LP-1 fed from MDP-1"). A designation right after a sheet
    or drawing word ("from sheet E-401") is a reference, not a panel. Any other line with a
    token holding a digit but the name ("LP-2 Lighting Panel") ends it. Linear in the size of
    the lines and the name; the name is tokenised once.
    """
    named, phrase = _name_tokens(name)
    for r in lines:
        toks = [t for c in r for t in _TOKEN_SPLIT.split(c.lower()) if t]
        other = [(k, t) for k, t in enumerate(toks) if t not in named and any(map(str.isdigit, t))]
        if not other:
            continue
        # A bare digit or a unit ("2", "208y") has no letter prefix: not a panel designation.
        desig = any(_prefix(t) and (k == 0 or toks[k - 1] not in _REF_WORDS) for k, t in other)
        if phrase and phrase in f" {' '.join(toks)} " and not desig:
            continue
        return False
    return True


def _near(grid: list[list[str]], i: int) -> tuple[list[str], list[str]]:
    return (grid[i - 1] if i else [], grid[i + 1] if i + 1 < len(grid) else [])


def _is_panel_line(ctx: _Ctx, row: list[str]) -> bool:
    """An explicit panel-name line: an exact panel key with a value, or a colon line with one."""
    cells = [c.strip() for c in row if c.strip()]
    if not cells:
        return False
    key, colon, after = cells[0].partition(":")
    hit = ctx.block_match(key)
    if hit.key != "panel_name":
        return False
    return bool(after.strip()) if colon else hit.conf == Confidence.HIGH and len(cells) > 1


def _is_short_block_line(ctx: _Ctx, row: list[str]) -> bool:
    cells = [c.strip() for c in row if c.strip()]
    if not cells or len(cells) > 2:
        return False
    hit = ctx.block_match(cells[0].partition(":")[0])
    # Only a panel line starts the next table; another key or a colon line may be a circuit.
    return hit.key == "panel_name" and (hit.conf == Confidence.HIGH or ":" in cells[0])


def _last_row(
    ctx: _Ctx,
    grid: list[list[str]],
    head: int,
    k: int,
    keys: list[str | None],
    titled: bool = False,
) -> int:
    """Index of the last row of the table whose header is at head, searching up from k.

    A table ends at its last row that looks like a circuit, and no lower than its first short
    block line (an exact key or a "key: value" line). A lone cell counts as a circuit only
    directly under the header or a circuit line, so a lone rating under a title ("225A") is
    not one. titled (the last table of a grid) also ends at a TOTAL row or a footer title.
    """
    ckt = _ckt_cols(keys)
    memo: dict[int, bool] = {}
    for j in range(head + 1, k + 1):
        if _is_short_block_line(ctx, grid[j]) or (
            titled and _ends_last_table(ctx, grid, head, j, k, keys, ckt, memo)
        ):
            return _walk_up(ctx, grid, head, j - 1, keys, ckt)
    return _walk_up(ctx, grid, head, k, keys, ckt)


def _total_ends(
    ctx: _Ctx,
    grid: list[list[str]],
    j: int,
    k: int,
    keys: list[str | None],
    ckt: list[int],
    memo: dict[int, bool],
) -> bool:
    """A TOTAL row ends the last table unless a circuit row follows it before any other text
    (a subtotal per panel in a combined schedule). Runs of TOTAL rows share one answer."""
    seen, ends = [j], True
    for n in range(j + 1, k + 1):
        if n in memo:
            ends = memo[n]
            break
        cells = [c.strip() for c in grid[n] if c.strip()]
        if not cells:
            continue
        if _is_circuit_row(ctx, grid[n], keys, ckt, _near(grid, n)):
            ends = False
            break
        if not _TOTAL_ROW.fullmatch(cells[0]):
            break
        seen.append(n)
    memo.update(dict.fromkeys(seen, ends))
    return ends


def _ends_last_table(
    ctx: _Ctx,
    grid: list[list[str]],
    head: int,
    j: int,
    k: int,
    keys: list[str | None],
    ckt: list[int],
    memo: dict[int, bool],
) -> bool:
    """A TOTAL row, or a lone text cell ("Notes:", "Page 2 of 2") that follows a blank line or a
    non-circuit line, or ends in a colon, below the last table."""
    cells = [c.strip() for c in grid[j] if c.strip()]
    if cells and _TOTAL_ROW.fullmatch(cells[0]):
        return _total_ends(ctx, grid, j, k, keys, ckt, memo)
    if not (
        len(cells) == 1
        and any(ch.isalpha() for ch in cells[0])
        and not re.fullmatch(r"\d+[A-Za-z]", cells[0])
    ):
        return False
    above = grid[j - 1]
    return (
        cells[0].endswith(":")
        or not any(c.strip() for c in above)
        or (j - 1 > head and not _is_circuit_row(ctx, above, keys, ckt, _near(grid, j - 1)))
    )


def _walk_up(
    ctx: _Ctx, grid: list[list[str]], head: int, k: int, keys: list[str | None], ckt: list[int]
) -> int:
    while k > head:
        row = grid[k]
        if _is_circuit_row(ctx, row, keys, ckt, _near(grid, k)):
            lone = sum(1 for c in row if c.strip()) == 1
            above = grid[k - 1]
            if (
                not lone
                or k - 1 == head
                or _is_circuit_row(ctx, above, keys, ckt, _near(grid, k - 1))
            ):
                return k
        k -= 1
    return k


def rows_to_panels(
    rows: Sequence[Sequence[str]],
    cfg: Config,
    *,
    file: str,
    method: Method,
    locate: Locate,
    fallback_panel: str | None = None,
) -> Parsed:
    grid = [["" if c is None else str(c) for c in r] for r in rows]
    maps = cfg.column_maps
    comp = cfg.cec.get("completeness") or {}
    out = Parsed()
    ctx = _Ctx(
        cfg=cfg,
        file=file,
        method=method,
        locate=locate,
        fallback=fallback_panel,
        match=_matcher(maps.get("csv_panel_schedule"), SCHEDULE_KEYS),
        block_match=_matcher(maps.get("panel_header_block"), BLOCK_KEYS),
        ph={str(p).strip().upper() for p in comp.get("placeholder_texts") or []},
        spare={str(p).strip().upper() for p in comp.get("spare_keywords") or []},
        detect_two_column=bool(
            (maps.get("two_column_layout") or {}).get("detect_when_headers_repeat")
        ),
        out=out,
    )
    need = (maps.get("parsing") or {}).get("min_header_alias_matches", 3)
    heads: list[int] = []
    prev: list[str | None] = []
    prev_ckt: list[int] = []
    for i, r in enumerate(grid):
        keys = {m.key for c in r if (m := ctx.match(c)).key}
        if len(keys) < need:
            continue
        if prev and _is_circuit_row(ctx, r, prev, prev_ckt, _near(grid, i)):
            continue  # under the table above, this line has a circuit number: it is data
        heads.append(i)
        prev = [ctx.match(c).key for c in r]
        prev_ckt = _ckt_cols(prev)
    if not heads:
        first = next((i for i, r in enumerate(grid) if any(c.strip() for c in r)), None)
        if first is None:
            ctx.unp("table", "", "no rows", locate(0))
            return out
        raw = ", ".join(c.strip() for c in grid[first] if c.strip())
        ctx.unp("table", raw, "no header row found", locate(first))
        for c in grid[first]:
            if c.strip():
                ctx.unp(
                    "column", c.strip(), "no header row found", f"{locate(first)}; col={c.strip()}"
                )
        return out
    cols = [[_Col(i, c.strip(), ctx.match(c)) for i, c in enumerate(grid[h])] for h in heads]
    starts, ends = [0], []
    gap_cut: set[int] = set()
    for n in range(1, len(heads)):
        keys = [c.hit.key for c in cols[n - 1]]
        k = _last_row(ctx, grid, heads[n - 1], heads[n] - 1, keys)
        starts.append(k + 1)
        ends.append(k + 1)
        # Only lines above the next block's panel-name line; below it they are its values.
        named_at = next(
            (j for j in range(k + 1, heads[n]) if _is_panel_line(ctx, grid[j])), heads[n]
        )
        ctx.ambiguous |= {
            j
            for j in range(k + 1, named_at)
            if _ambiguous_key_line(ctx, grid[j], keys, _near(grid, j))
        }
        ckt_k = _ckt_cols(keys)
        # A circuit-like row cut above the next block (a long or date circuit cell) is listed
        # by that block; the table above is not whole.
        if any(
            j not in ctx.ambiguous
            and _is_circuit_row(ctx, grid[j], keys, ckt_k, _near(grid, j), any_len=True)
            and sum(1 for c in grid[j] if c.strip()) > 1
            for j in range(k + 1, named_at)
        ):
            gap_cut.add(n - 1)
    keys = [c.hit.key for c in cols[-1]]
    # With no circuit column nothing can be told from a circuit row: the table keeps every row.
    last = len(grid) - 1
    if _ckt_cols(keys):
        last = _last_row(ctx, grid, heads[-1], last, keys, titled=True)
    ends.append(last + 1)
    for n, h in enumerate(heads):
        above, before = ctx.last_panel or ctx.pcol_panel, len(out.panels)
        _table(ctx, grid, h, cols[n], starts[n], ends[n])
        if n in gap_cut:
            for panel in out.panels[before:] or [above]:
                if panel:
                    _mark_incomplete(panel, _BELOW_NOTE)
    ckt = _ckt_cols(keys)
    cut_circuit = cut_any = False
    for j in range(last + 1, len(grid)):
        if text := ", ".join(c.strip() for c in grid[j] if c.strip()):
            ctx.unp("row", text, "no circuit number", locate(j))
            cut_any = True
            cut_circuit |= _is_circuit_row(ctx, grid[j], keys, ckt, _near(grid, j), any_len=True)
    # A cut row that looks like a circuit may belong to the panel: it is not whole. A last
    # table cut back to its header makes no panel, and its rows may continue the one above.
    made = out.panels[before:]
    if made and cut_circuit:
        for panel in made:
            _mark_incomplete(panel, _BELOW_NOTE)
    elif not made and cut_any and above:
        _mark_incomplete(above, _BELOW_NOTE)
    return out
