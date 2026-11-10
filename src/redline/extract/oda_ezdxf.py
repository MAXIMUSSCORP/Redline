"""Fallback extractor: ODA File Converter (DWG to DXF) and ezdxf. ezdxf is imported lazily."""

from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any

from redline import rawdrawing
from redline.config import Config
from redline.extract import (
    ExtractError,
    Unavailable,
    check_unchanged,
    run_tool,
    sha256_of,
    validated,
)

VERSION = "0.1.0"
ODA = "ODA File Converter"
_AUDIT_LIMIT = 20
_FIELD_VISITS = 64  # FIELD handles read per cell
_FLD_IDX = re.compile(r"%<\\_FldIdx (\d+)>%")


def _num(x: Any) -> float | None:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _pos(x: Any) -> float | None:
    x = _num(x)
    return x if x is not None and x > 0 else None


def _pt(v: Any) -> list[float] | None:
    try:
        p = [_num(v[i]) for i in range(min(len(v), 3))]
    except (TypeError, IndexError):
        return None
    return p if len(p) >= 2 and None not in p else None


def _cut(text: Any, what: str, notes: list[str]) -> str:
    text = "" if text is None else str(text)
    if len(text) > rawdrawing.MAX_TEXT:
        notes.append(f"text of {what} was cut at MAX_TEXT ({rawdrawing.MAX_TEXT} characters)")
        return text[: rawdrawing.MAX_TEXT]
    return text


def _probe(fn: Any) -> Any:
    # Optional ezdxf internals differ by entity class and file version. A miss means "not read".
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


def _table_counts(e: Any) -> tuple[int, int] | None:
    sub = _probe(lambda: e.xtags.get_subclass("AcDbTable"))
    if sub is None:
        return None
    rows, cols = sub.get_first_value(91, 0), sub.get_first_value(92, 0)
    return (rows, cols) if rows > 0 and cols > 0 else None


def _field_text(
    db: Any, handle: Any, seen: list[Any], notes: list[str], what: str, path: tuple = ()
) -> str:
    """Cached text of a FIELD: its own value (code 301), else its field code (codes 2 and 3)
    with each child's text (code 360) put in at its FldIdx place. A handle on the current path
    is a cycle. A cell reads at most _FIELD_VISITS handles in all (seen counts visits)."""
    if handle in path:
        return ""
    if len(seen) >= _FIELD_VISITS:
        note = f"{what}: FIELD reading stopped after {_FIELD_VISITS} fields"
        if note not in notes:
            notes.append(note)
        return ""
    seen.append(handle)
    f = db.get(handle)
    if f is None or f.dxftype() != "FIELD":
        return ""
    tags = [t for sub in f.xtags.subclasses for t in sub]
    own = "".join(str(t.value) for t in tags if t.code == 301)
    if own:
        return own
    kids = [
        _field_text(db, t.value, seen, notes, what, (*path, handle)) for t in tags if t.code == 360
    ]
    code = "".join(str(t.value) for t in tags if t.code in (2, 3))
    if not _FLD_IDX.search(code):
        if len(kids) > 1:
            notes.append(
                f"{what}: FIELD has several child fields and no place for them in its code"
            )
            return ""
        return "".join(kids)
    if any(int(i) >= len(kids) for i in _FLD_IDX.findall(code)):
        notes.append(
            f"{what}: FIELD code names a child field that is not there, so no text was read"
        )
        return ""
    return _FLD_IDX.sub(lambda m: kids[int(m.group(1))], code)


def _cell_texts(
    e: Any, cols: int, what: str, notes: list[str]
) -> tuple[dict[tuple[int, int], str], dict[tuple[int, int], str]]:
    """Per cell of the AcDbTable tags (each cell opens with 171): FIELD cached text (code 344)
    and plain code 1 text. Long text comes as code 3 chunks, then code 1 last."""
    tags = _probe(lambda: list(e.xtags.get_subclass("AcDbTable")))
    if not tags or cols <= 0:
        return {}, {}
    fields: dict[tuple[int, int], str] = {}
    plain: dict[tuple[int, int], str] = {}
    n, chunks = -1, ""
    for t in tags:
        if t.code == 171:
            n, chunks = n + 1, ""
        elif n < 0:
            continue
        elif t.code == 344:
            pos = divmod(n, cols)
            txt = _field_text(
                e.doc.entitydb, t.value, [], notes, f"table {what} cell ({pos[0]}, {pos[1]})"
            )
            if txt:  # an empty field result must not hide the cell's own text
                fields[pos] = txt
        elif t.code == 3:
            chunks += str(t.value)
        elif t.code == 1:
            plain[divmod(n, cols)] = chunks + str(t.value)
            chunks = ""
    return fields, plain


def _table(e: Any, what: str, notes: list[str], acad_table: Any) -> dict[str, Any]:
    from ezdxf.tools.text import plain_mtext

    counts = _table_counts(e)
    if counts and counts[0] * counts[1] > rawdrawing.MAX_TABLE_CELLS:
        raise ExtractError(
            f"table {what} has more cells than MAX_TABLE_CELLS ({rawdrawing.MAX_TABLE_CELLS})"
        )
    values = acad_table.read_acad_table_content(e)
    # ezdxf reads a FIELD cell's own text, which is empty. The drawing shows the cached value.
    fields, plain = _cell_texts(e, counts[1], what, notes) if counts else ({}, {})
    cells = []
    for r, row in enumerate(values):
        for c, text in enumerate(row):
            # Every fallback cell is not evaluated until the FIELD tag check is shown right (D4).
            # Code 1 holds the text of many cells while code 302, which ezdxf reads, is empty.
            text = fields.get((r, c)) or text or plain.get((r, c), "")
            text = plain_mtext(text, split=False).replace(chr(10), " ")
            cells.append({"r": r, "c": c, "text": _cut(text, what, notes), "evaluated": False})
    if len(cells) > rawdrawing.MAX_TABLE_CELLS:
        raise ExtractError(
            f"table {what} has more cells than MAX_TABLE_CELLS ({rawdrawing.MAX_TABLE_CELLS})"
        )
    rows, cols = counts if counts else (None, None)
    return {"rows": rows, "cols": cols, "cells": cells}


def _mleader_attribs(e: Any) -> list[dict[str, str]]:
    return [
        {
            "tag": str(_probe(lambda a=a: e.doc.entitydb.get(a.handle).dxf.tag) or ""),
            "value": str(a.text),
        }
        for a in getattr(e, "block_attribs", None) or []
    ]


def convert(
    e: Any, layout: str, xref_path: str | None, notes: list[str], acad_table: Any
) -> dict[str, Any] | None:
    """One ezdxf entity to a RawDrawing entity without id, or None for a type not read."""
    kind = e.dxftype()
    g = e.dxf.get
    handle = str(g("handle") or "0")
    out: dict[str, Any] = {
        "type": kind,
        "layout": layout,
        "layer": _cut(g("layer") or "0", handle, notes),
        "handle": handle,
        "bbox": None,
    }
    if xref_path is not None:
        out["xref_path"] = xref_path
    if kind == "TEXT":
        out["text"] = _cut(g("text", ""), handle, notes)
        out["text_height"] = _pos(g("height"))
        out["insertion_point"] = _pt(g("insert") or ())
        out["rotation_deg"] = _num(g("rotation", 0))
    elif kind == "MTEXT":
        out["text"] = _cut(e.plain_text(), handle, notes)
        out["text_height"] = _pos(g("char_height"))
        out["insertion_point"] = _pt(g("insert") or ())
        out["rotation_deg"] = _num(g("rotation", 0))
    elif kind == "INSERT":
        out["block_name"] = _cut(g("name", ""), handle, notes)
        out["attributes"] = [
            {
                "tag": _cut(a.dxf.get("tag", ""), handle, notes),
                "value": _cut(a.dxf.get("text", ""), handle, notes),
            }
            for a in e.attribs
        ]
        out["insertion_point"] = _pt(g("insert") or ())
        out["rotation_deg"] = _num(g("rotation", 0))
    elif kind == "ACAD_TABLE":
        out["table"] = _table(e, handle, notes, acad_table)
        ref = _probe(lambda: e.xtags.get_subclass("AcDbBlockReference").get_first_value(10, None))
        out["insertion_point"] = _pt(ref or ())
    elif kind == "MLEADER":
        out["text"] = _cut(_probe(e.get_mtext_content) or "", handle, notes)
        out["attributes"] = _mleader_attribs(e)
        out["insertion_point"] = _pt(_probe(lambda: e.context.mtext.insert) or ())
        out["text_height"] = _pos(_probe(lambda: e.context.char_height))
    elif kind == "LINE":
        a, b = _pt(g("start") or ()), _pt(g("end") or ())
        out["insertion_point"] = a
        if a and b:
            out["bbox"] = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
    elif kind == "LWPOLYLINE":
        out["type"] = "POLYLINE"
        pts = _probe(lambda: list(e.get_points("xy"))) or []
        out["insertion_point"] = _pt(pts[0]) if pts else None
    elif kind == "POLYLINE":
        first = _probe(lambda: e.vertices[0].dxf.location)
        out["insertion_point"] = _pt(first) if first is not None else None
    else:
        return None
    return {k: v for k, v in out.items() if v is not None or k == "bbox"}


def _unexpected(path: Path, e: Exception) -> str:
    return f"ezdxf failed while reading {path.name} ({type(e).__name__})"


def _odafc(parsing: dict[str, Any]) -> str:
    raw = parsing.get("odafc_path")
    if not raw:
        raise Unavailable(f"odafc_path is not set in the parsing config, so {ODA} cannot run")
    exe = os.path.abspath(os.path.expandvars(raw))
    if not os.path.isfile(exe):
        raise Unavailable(f"odafc_path does not exist: {exe}")
    return exe


def _to_dxf(odafc: str, src: Path, tmp: Path, n: int, timeout: float) -> Path:
    indir, outdir = tmp / f"in{n}", tmp / f"out{n}"
    try:
        indir.mkdir()
        outdir.mkdir()
        shutil.copyfile(src, indir / src.name)
    except OSError as e:
        raise ExtractError(f"{src.name} could not be copied to a temp folder") from e
    args = [odafc, str(indir), str(outdir), "ACAD2018", "DXF", "0", "1", src.name]
    run_tool(ODA, args, timeout, tmp)
    out = outdir / (src.stem + ".dxf")
    if not out.is_file():
        raise ExtractError(f"{ODA} wrote no DXF for {src.name}")
    return out


def _inside(raw: str, base: Path, root: Path) -> Path | None:
    """The xref's file when it sits inside the host drawing's folder tree, else None."""
    # Judged from the text: resolving a UNC or drive path would make Windows open it.
    win = PureWindowsPath(raw)
    if not raw or win.is_absolute() or win.drive or win.root:
        return None
    try:
        p = (base / raw).resolve()
        p.relative_to(root)
    except (OSError, ValueError):
        return None
    return p


def extract(path: Path, cfg: Config) -> dict[str, Any]:
    try:
        import ezdxf
        from ezdxf import recover
        from ezdxf import units as ezunits
        from ezdxf.entities import acad_table
    except ImportError as e:
        raise Unavailable("ezdxf not installed: pip install redline[dxf]") from e
    parsing = cfg.column_maps["parsing"]
    suffix = path.suffix.lower()
    if suffix not in (".dwg", ".dxf"):
        raise ExtractError(f"{path.name} is not a .dwg or .dxf file")
    odafc = _odafc(parsing) if suffix == ".dwg" else None
    if not path.is_file():
        raise ExtractError(f"{path.name} was not found")
    timeout = parsing["dxf_extractor_timeout_s"]
    before = sha256_of(path)

    entities: list[dict[str, Any]] = []
    xrefs: list[dict[str, Any]] = []
    notes: list[str] = []
    skipped: Counter[str] = Counter()
    root = path.resolve().parent
    visited = {path.resolve()}
    failed: dict[Path, str] = {}
    runs = 0

    tmp = Path(tempfile.mkdtemp(prefix="redline-oda-", dir=tempfile.gettempdir()))

    def load(src: Path) -> Any:
        nonlocal runs
        dxf = src
        if src.suffix.lower() == ".dwg":
            runs += 1
            dxf = _to_dxf(odafc, src, tmp, runs, timeout)
        try:
            size = dxf.stat().st_size
        except OSError as e:
            raise ExtractError(f"{dxf.name} could not be read ({type(e).__name__})") from e
        if size > rawdrawing.MAX_JSON_BYTES:
            raise ExtractError(
                f"{src.name} is over MAX_JSON_BYTES ({rawdrawing.MAX_JSON_BYTES} bytes)"
            )
        try:
            doc, auditor = recover.readfile(str(dxf))
        except Exception as e:
            raise ExtractError(f"ezdxf could not read {src.name} ({type(e).__name__})") from e
        errs = [str(x.message) for x in auditor.errors]
        notes.extend(f"audit of {src.name}: {m}" for m in errs[:_AUDIT_LIMIT])
        if len(errs) > _AUDIT_LIMIT:
            notes.append(f"audit of {src.name}: {len(errs) - _AUDIT_LIMIT} more not listed")
        return doc

    def add(e: Any, layout: str, xref_path: str | None) -> None:
        item = convert(e, layout, xref_path, notes, acad_table)
        if item is None:
            skipped[e.dxftype()] += 1
            return
        if len(entities) >= rawdrawing.MAX_ENTITIES:
            raise ExtractError(f"more entities than MAX_ENTITIES ({rawdrawing.MAX_ENTITIES})")
        entities.append({"id": f"e{len(entities) + 1:04d}", **item})

    def walk(doc: Any, origin: Path, xname: str | None, xpath: str | None) -> None:
        tag = _cut(f"block:{xname}", "layout name", notes) if xname else None
        for lay in doc.layouts:
            for e in lay:
                add(e, tag or _cut(lay.name, "layout name", notes), xpath)
        for blk in doc.blocks:
            if blk.is_any_layout:
                continue
            if blk.block_record.is_xref:
                follow(blk, origin)
                continue
            for e in blk:
                add(e, tag or _cut(f"block:{blk.name}", "layout name", notes), xpath)

    def follow(blk: Any, origin: Path) -> None:
        name, raw = blk.name, str(blk.block.dxf.get("xref_path") or "")
        target = _inside(raw, origin, root)
        done = False
        if target is not None and target in failed:
            notes.append(f"xref {name} was not read: {failed[target]}")
        elif target is not None and target in visited:
            done = True  # read already, or a cycle
        elif target is not None and target.suffix.lower() in (".dwg", ".dxf") and target.is_file():
            if target.suffix.lower() == ".dwg" and odafc is None:
                notes.append(f"xref {name} is a DWG and odafc_path is not set, so it was not read")
            else:
                visited.add(target)
                before = set(visited)
                kept, kept_skipped = len(entities), Counter(skipped)
                kept_xrefs = len(xrefs)
                try:
                    walk(load(target), target.parent, name, raw)
                    done = True
                except Exception as e:  # noqa: BLE001
                    reason = str(e) if isinstance(e, ExtractError) else _unexpected(target, e)
                    del entities[kept:]  # an xref is read whole or not at all
                    skipped.clear()
                    skipped.update(kept_skipped)
                    for t in visited - before | {target}:  # also xrefs read inside this one
                        failed[t] = reason
                    visited.difference_update(failed)
                    for x in xrefs[kept_xrefs:]:
                        if x["resolved"]:
                            x["resolved"] = False
                            notes.append(f"xref {x['name']} was not read: {reason}")
                    notes.append(f"xref {name} was not read: {reason}")
        xrefs.append({"name": name, "path": raw, "resolved": done})

    try:
        doc = load(path)
        walk(doc, root, None, None)
        units = ezunits.decode(doc.units) if doc.units else "unitless"
        layouts = [_cut(n, "layout name", notes) for n in doc.layouts.names_in_taborder()]
    except ExtractError:
        raise
    except Exception as e:
        raise ExtractError(_unexpected(path, e)) from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    host = (
        f"{ODA} version not read + ezdxf {ezdxf.__version__}"
        if odafc
        else f"ezdxf {ezdxf.__version__} (DXF read directly)"
    )
    if skipped:
        listing = ", ".join(f"{k} x{n}" for k, n in sorted(skipped.items()))
        notes.append(f"entity types not read: {listing}")
    data: dict[str, Any] = {
        "schema_version": rawdrawing.SCHEMA_VERSION,
        "extractor": "oda_ezdxf",
        "extractor_version": VERSION,
        "host_version": host,
        "source_file": path.name,
        "source_sha256": before,
        "extracted_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "document": {"units": units, "layouts": layouts, "xrefs": xrefs, "warnings": notes},
        "entities": entities,
    }
    validated("ezdxf", data)
    check_unchanged(data, path, before)
    return data
