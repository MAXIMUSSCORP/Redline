"""Reads RawDrawing JSON into panels. Tables, *T blocks and loose text go through rows_to_panels."""

from __future__ import annotations

import statistics
from bisect import bisect_left
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from redline import rawdrawing
from redline.config import Config
from redline.model import (
    Confidence,
    CoverageEntry,
    Method,
    Panel,
    Source,
    Unparsed,
    Value,
    clip,
)
from redline.parsers.csv_xlsx import InputError
from redline.parsers.tabular import Parsed, rows_to_panels

SUFFIXES = (".dwg", ".dxf")
JSON_SUFFIX = ".rawdrawing.json"
STALE_NOTE = "field cell not evaluated; the cached text may be stale"
LOOSE_NOTE = "read from loose text"
# Text turned this far from 0 or 180 degrees is a label on a symbol, not a table row.
ROTATION_TOLERANCE_DEG = 1.0
_NO_COUNTS = "table has no row and column counts, so its cells cannot be placed"
_WD_UNMAPPED = "WD_M attribute not mapped (aecad_project.wd_m_attribute_map)"
# Most read tables one text of a *T group may be found in, on average. A group over it is not
# matched, so its text stays listed and is never skipped; the work stays linear in the texts.
_STAR_T_TABLES_PER_TEXT = 64
_NO_SUMMARY = "HIGH 0, MEDIUM 0, LOW 0, MISSING 0"


def accepts(path: Path) -> bool:
    name = Path(path).name.lower()
    return name.endswith(JSON_SUFFIX) or name.endswith(SUFFIXES)


def provenance(data: dict) -> str:
    return (
        f"{data['extractor']} {data['extractor_version']}, host {data['host_version']}, "
        f"SHA-256 {data['source_sha256']}"
    )


def parse_file(path: Path, cfg: Config) -> Parsed:
    path = Path(path)
    name = path.name.lower()
    try:
        if name.endswith(JSON_SUFFIX):
            data = rawdrawing.read(path)
        elif name.endswith(SUFFIXES):
            from redline.extract import ExtractError, extract

            try:
                data = extract(path, cfg)
            except ExtractError as e:
                raise InputError(str(e)) from e
        else:
            raise InputError(f"unsupported file type: {path.suffix or 'none'}")
    except ValueError as e:  # json.JSONDecodeError is a ValueError
        raise InputError(f"{path.name} cannot be read as a RawDrawing: {e}") from e
    except (OSError, ImportError) as e:
        raise InputError(f"{path.name} cannot be read: {type(e).__name__}") from e
    result = rawdrawing.validate(data)
    if not result.ok:
        shown = "; ".join(result.errors[:3])
        raise InputError(f"{path.name} is not a valid RawDrawing: {shown}")
    out = parse_rawdrawing(data, cfg)
    out.provenance = {path.name: provenance(data)}
    return out


# ---- source walking: extractor stamp and confidence caps ----


def _apply(panel: Panel, fn: Callable[[Source], Source]) -> None:
    """Replace every Source under a panel with fn(Source)."""
    panel.source = fn(panel.source)
    for unit in (panel, *panel.circuits):
        if unit is not panel:
            unit.source = fn(unit.source)
        for f in fields(unit):
            v = getattr(unit, f.name)
            if isinstance(v, Value) and v.source is not None:
                setattr(unit, f.name, replace(v, source=fn(v.source)))


def _cap_medium(src: Source) -> Source:
    if src.confidence <= Confidence.MEDIUM:
        return src
    note = f"{src.note}; {LOOSE_NOTE}" if src.note else LOOSE_NOTE
    return replace(src, confidence=Confidence.MEDIUM, note=note)


def _summary(panel: Panel) -> str:
    """Confidence counts of the panel and circuit values, as the tabular parser counts them."""
    n: Counter = Counter(
        v.confidence
        for u in (panel, *panel.circuits)
        for f in fields(u)
        if isinstance((v := getattr(u, f.name)), Value) and v.source is not None
    )
    return ", ".join(f"{c.name} {n[c]}" for c in sorted(Confidence, reverse=True))


# ---- loose text ----


@dataclass
class _Item:
    x: float
    y: float
    h: float
    text: str
    x_end: float | None


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def _items(entities: list[dict]) -> tuple[list[_Item], int]:
    """Placed text, and how many non-empty texts cannot be placed in a row."""
    items, skipped = [], 0
    for e in entities:
        text = _clean(e.get("text"))
        if not text:
            continue
        p, h = e.get("insertion_point"), e.get("text_height")
        rot = (e.get("rotation_deg") or 0) % 180
        if p is None or h is None or min(rot, 180 - rot) > ROTATION_TOLERANCE_DEG:
            skipped += 1
            continue
        bbox = e.get("bbox")
        items.append(_Item(p[0], p[1], h, text, bbox[2] if bbox else None))
    return items, skipped


def _nearest(xs: list[float], x: float) -> int:
    """Index of the closest of ascending xs; ties and equal xs go to the lowest index."""
    i = bisect_left(xs, x)
    near = [j for j in (i - 1, i) if 0 <= j < len(xs)]
    best = min(near, key=lambda j: abs(xs[j] - x))
    return bisect_left(xs, xs[best])


def _grid(
    items: list[_Item], row_tol: float, gap: float
) -> tuple[list[list[str]], list[float], int] | None:
    """Rows by y, cells by x, columns aligned to the header row. Returns grid, y per row, and the
    number of cells that shared a column with another cell of their row. None when the grid
    would be over the cell cap."""
    med = statistics.median(i.h for i in items)
    rows: list[list[_Item]] = []
    total = 0.0  # running sum of y in the current row
    for it in sorted(items, key=lambda i: (-i.y, i.x)):
        if rows and abs(it.y - total / len(rows[-1])) <= row_tol * med:
            rows[-1].append(it)
            total += it.y
        else:
            rows.append([it])
            total = it.y
    cells: list[list[_Item]] = []
    for r in rows:
        merged: list[_Item] = []
        parts: list[list[str]] = []
        for it in sorted(r, key=lambda i: i.x):
            prev = merged[-1] if merged else None
            if prev and prev.x_end is not None and it.x - prev.x_end <= gap * med:
                parts[-1].append(it.text)
                merged[-1] = replace(prev, x_end=it.x_end)
            else:
                merged.append(it)
                parts.append([it.text])
        cells.append([replace(m, text=" ".join(ps)) for m, ps in zip(merged, parts, strict=True)])
    header = max(cells, key=len)  # max keeps the first of equals: the topmost row
    xs = [c.x for c in header]
    if len(cells) * len(xs) > rawdrawing.MAX_TABLE_CELLS:
        return None
    grid, shared = [], 0
    top = cells.index(header)
    for n, r in enumerate(cells):
        line = [""] * len(xs)
        for c in r:
            k = _nearest(xs, c.x)
            shared += bool(line[k])
            line[k] = f"{line[k]} {c.text}".strip()
        text = line[0]
        if n < top and len(r) == 1 and len(xs) > 1 and text == r[0].text and ":" not in text:
            # A lone title line above the header ("Panel LP-13") holds a key and its value. The
            # value must hold a digit, so a title like "LIGHTING PANEL SCHEDULE" is not split.
            key, _, value = text.rpartition(" ")
            if key and any(ch.isdigit() for ch in value):
                line[0], line[1] = key, value
        grid.append(line)
    return grid, [statistics.fmean(i.y for i in r) for r in rows], shared


# ---- the parser ----


@dataclass
class _Tally:
    tables_read: int = 0
    tables_listed: int = 0
    clusters_read: int = 0
    clusters_listed: int = 0
    wd_read: list[str] = field(default_factory=list)
    attr_blocks: int = 0
    unplaced_text: int = 0
    shared_columns: int = 0
    other_block_text: int = 0
    xref_text: Counter = field(default_factory=Counter)
    table_render_text: int = 0
    read_tables: list[set[str]] = field(default_factory=list)
    mleaders: int = 0
    declared: int = 0


def _where(e: dict) -> str:
    xp = e.get("xref_path")
    return f"layout={e.get('layout')}" + (f"; xref={xp}" if xp else "")


def parse_rawdrawing(data: dict, cfg: Config) -> Parsed:
    parsing = cfg.column_maps.get("parsing") or {}
    file = data["source_file"]
    stamp = f"{data['extractor']}@{data['extractor_version']}"
    out = Parsed(provenance={file: provenance(data)})
    tally = _Tally()
    entities = [e for e in data.get("entities") or [] if isinstance(e, dict)]

    def unp(kind: str, raw: str, reason: str, locator: str, method: Method) -> None:
        out.unparsed.append(
            Unparsed(kind, raw, reason, Source(file, locator, method, Confidence.LOW))
        )

    for x in (data.get("document") or {}).get("xrefs") or []:
        if x.get("resolved") is False:
            why = f"xref {clip(x.get('name'))} is not resolved (path {clip(x.get('path'))}), so its content is not read"
            unp("xref", str(x.get("name")), why, f"xref={x.get('name')}", Method.DXF_TABLE)

    def add(part: Parsed, loose: bool) -> None:
        if loose:
            for p in part.panels:
                _apply(p, _cap_medium)
            if len(part.coverage) == len(part.panels):  # one entry per panel, in panel order
                part.coverage = [
                    replace(c, confidence_summary=_summary(p))
                    for c, p in zip(part.coverage, part.panels, strict=True)
                ]
        out.panels += part.panels
        out.unparsed += part.unparsed
        out.coverage += part.coverage

    for w in (data.get("document") or {}).get("warnings") or []:
        unp(
            "layout",
            clip(str(w)),
            f"extractor note: {clip(str(w))}",
            "document.warnings",
            Method.DXF_TABLE,
        )

    min_cells = parsing.get("dxf_table_min_cells", 1)
    for e in entities:
        if e.get("type") == "ACAD_TABLE":
            _table(e, cfg, file, min_cells, out, tally, add, unp)

    texts: dict[tuple[str, str | None], list[dict]] = {}
    for e in entities:
        t, layout = e.get("type"), str(e.get("layout"))
        if t == "INSERT":
            _insert(e, cfg, file, out, tally, unp)
        elif t == "MLEADER":
            tally.mleaders += 1
        elif t in ("TEXT", "MTEXT"):
            texts.setdefault((layout, e.get("xref_path")), []).append(e)
    star_t = [k for k in texts if k[0].upper().startswith("BLOCK:*T")]
    skipped_t = set()
    # Identical tables collapse to one set, and a text index finds the tables a group can match.
    uniq = list({frozenset(c) for c in tally.read_tables})
    index: dict[str, list[int]] = {}
    for i, cells in enumerate(uniq):
        for c in cells:
            index.setdefault(c, []).append(i)
    memo: dict[tuple[str, ...], bool] = {}
    for k in star_t:
        # The RawDrawing does not link a table to its *T block, so match by content: a *T group
        # is a table's rendering when over half of its texts are cell texts of one table read.
        cleaned = [c for c in (_clean(e.get("text")) for e in texts[k]) if c]
        key = tuple(sorted(cleaned))
        if key not in memo:
            hits: Counter = Counter()
            if sum(len(index.get(c, ())) for c in cleaned) <= _STAR_T_TABLES_PER_TEXT * len(
                cleaned
            ):
                for c in cleaned:
                    hits.update(index.get(c, ()))
            memo[key] = any(2 * n > len(cleaned) for n in hits.values())
        if cleaned and memo[key]:
            tally.table_render_text += len(cleaned)
            skipped_t.add(k)
    star_t = [k for k in star_t if k not in skipped_t]
    loose = [k for k in texts if not k[0].upper().startswith("BLOCK:")]
    read_keys = {*star_t, *loose, *skipped_t}
    for k, group in texts.items():
        if k not in read_keys:
            n = sum(1 for e in group if _clean(e.get("text")))
            if k[1]:
                tally.xref_text[k[1]] += n
            else:
                tally.other_block_text += n
    for k in star_t + loose:
        try:
            _cluster(texts[k], k, cfg, parsing, file, out, tally, add, unp)
        except Exception as ex:  # noqa: BLE001 - an odd drawing is listed, the rest is still read
            reason = f"loose text could not be read ({type(ex).__name__})"
            unp("table", "", reason, _where(texts[k][0]), Method.DXF_TEXT)

    for p in out.panels:
        _apply(p, lambda s: replace(s, extractor=stamp))
    out.unparsed = [replace(u, source=replace(u.source, extractor=stamp)) for u in out.unparsed]
    out.coverage.append(_drawing_entry(data, file, tally, out))
    return out


def _table(e, cfg, file, min_cells, out, tally, add, unp) -> None:
    loc = f"{_where(e)}; handle={e.get('handle')}"
    try:
        t = e.get("table") or {}
        cells = [c for c in t.get("cells") or [] if isinstance(c, dict)]

        def text(c: dict) -> str:
            return str(c.get("text") or "")

        filled = [text(c) for c in cells if text(c).strip()]
        rows, cols = t.get("rows"), t.get("cols")
        if rows is None or cols is None:
            tally.tables_listed += 1
            unp(
                "table",
                clip(", ".join(s.strip() for s in filled)),
                _NO_COUNTS,
                loc,
                Method.DXF_TABLE,
            )
            return
        if rows * cols > rawdrawing.MAX_TABLE_CELLS:
            tally.tables_listed += 1
            why = f"table is {rows} rows by {cols} columns, over the cell cap, so it is not read"
            unp("table", clip(", ".join(s.strip() for s in filled)), why, loc, Method.DXF_TABLE)
            return
        if tally.declared + rows * cols > rawdrawing.MAX_DRAWING_CELLS:
            tally.tables_listed += 1
            why = "declared table sizes of this drawing are over the drawing cell cap, so this table is not read"
            unp("table", clip(", ".join(s.strip() for s in filled)), why, loc, Method.DXF_TABLE)
            return
        tally.declared += rows * cols
        if len(filled) < min_cells:
            tally.tables_listed += 1
            unp(
                "table",
                clip(", ".join(s.strip() for s in filled)),
                "too few cells to be a schedule",
                loc,
                Method.DXF_TABLE,
            )
            return
        grid = [[""] * cols for _ in range(rows)]
        low = set()
        for c in cells:
            r, k = c.get("r"), c.get("c")
            if isinstance(r, int) and isinstance(k, int) and 0 <= r < rows and 0 <= k < cols:
                grid[r][k] = text(c)
                if c.get("evaluated") is False:
                    low.add((r, k))
        part = rows_to_panels(
            grid,
            cfg,
            file=file,
            method=Method.DXF_TABLE,
            locate=lambda i: f"{loc}; r={i}",
            low_cells=low,
            low_note=STALE_NOTE,
        )
        tally.tables_read += bool(part.panels)
        if part.panels:
            tally.read_tables.append({_clean(c) for c in filled})
        tally.tables_listed += not part.panels
        add(part, False)
    except Exception as ex:  # noqa: BLE001 - an odd drawing is listed, the rest is still read
        tally.tables_listed += 1
        unp("table", "", f"table could not be read ({type(ex).__name__})", loc, Method.DXF_TABLE)


def _insert(e, cfg, file, out, tally, unp) -> None:
    attrs = [a for a in e.get("attributes") or [] if isinstance(a, dict)]
    if str(e.get("block_name") or "").upper() != "WD_M":
        tally.attr_blocks += bool(attrs)
        return
    wd_map = (cfg.column_maps.get("aecad_project") or {}).get("wd_m_attribute_map") or {}
    by_tag = {a.strip().upper(): k for k, v in wd_map.items() for a in v}
    for a in attrs:
        tag, value = str(a.get("tag") or ""), str(a.get("value") or "")
        key = by_tag.get(tag.strip().upper())
        if key is not None:
            tally.wd_read.append(f"{key} {clip(value)}")
        else:
            loc = f"{_where(e)}; handle={e.get('handle')}; attrib={tag}"
            unp("column", clip(f"{tag}={value}"), _WD_UNMAPPED, loc, Method.DXF_ATTRIB)


def _cluster(group, key, cfg, parsing, file, out, tally, add, unp) -> None:
    items, skipped = _items(group)
    tally.unplaced_text += skipped
    layout, xref = key
    where = f"layout={layout}" + (f"; xref={xref}" if xref else "")
    if len(items) < parsing.get("dxf_table_min_cells", 1):
        tally.unplaced_text += len(items)
        return
    built = _grid(items, parsing["row_tolerance_text_heights"], parsing["column_gap_fraction"])
    if built is None:
        why = f"loose text of {len(items)} texts would make a grid over the cell cap, so it is not read"
        out.unparsed.append(
            Unparsed("table", "", why, Source(file, where, Method.DXF_TEXT, Confidence.LOW))
        )
        tally.clusters_listed += 1
        return
    grid, ys, shared = built
    tally.shared_columns += shared
    part = rows_to_panels(
        grid,
        cfg,
        file=file,
        method=Method.DXF_TEXT,
        locate=lambda i: f"{where}; y={ys[i]:g}",
    )
    if not part.panels and all(u.kind in ("table", "column") for u in part.unparsed):
        # No schedule header: loose annotation, listed once instead of cell by cell.
        first = next((r for r in grid if any(r)), [])
        why = f"loose text has no panel schedule header, so its {len(items)} texts are not read"
        out.unparsed.append(
            Unparsed(
                "table",
                clip(", ".join(c for c in first if c)),
                why,
                Source(file, f"{where}; y={ys[0]:g}", Method.DXF_TEXT, Confidence.LOW),
            )
        )
        tally.clusters_listed += 1
        return
    tally.clusters_read += 1
    add(part, True)


def _drawing_entry(data: dict, file: str, t: _Tally, out: Parsed) -> CoverageEntry:
    parts = [
        f"extractor {data['extractor']} {data['extractor_version']}",
        f"{t.tables_read} tables read, {t.tables_listed} listed",
        f"{t.clusters_read} loose-text clusters read, {t.clusters_listed} listed",
    ]
    if t.wd_read:
        parts.append("WD_M values " + ", ".join(t.wd_read))
    if t.attr_blocks:
        parts.append(f"{t.attr_blocks} block references with attributes not read as schedules")
    if t.unplaced_text:
        parts.append(f"{t.unplaced_text} texts not clustered (rotated, unplaced or too few)")
    if t.shared_columns:
        parts.append(f"{t.shared_columns} loose-text cells shared a column with another cell")
    if t.other_block_text:
        parts.append(f"{t.other_block_text} texts in other block definitions not read")
    for xp, n in t.xref_text.items():
        if n:
            parts.append(f"{n} texts in xref {clip(xp)} not read")
    if t.table_render_text:
        parts.append(f"{t.table_render_text} texts in table render blocks not read twice")
    if t.mleaders:
        parts.append(f"{t.mleaders} multileaders not read")
    return CoverageEntry(file, "drawing", "; ".join(parts), Method.DXF_TABLE.value, _NO_SUMMARY)


__all__ = ["JSON_SUFFIX", "SUFFIXES", "accepts", "parse_file", "parse_rawdrawing", "provenance"]
