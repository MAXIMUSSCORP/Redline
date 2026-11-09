"""Fallback extractor: ODA File Converter (DWG to DXF) and ezdxf. ezdxf is imported lazily."""

from __future__ import annotations

import math
import os
import shutil
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
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


def _table(e: Any, what: str, notes: list[str], acad_table: Any) -> dict[str, Any]:
    values = acad_table.read_acad_table_content(e)
    counts = _table_counts(e)
    cells = []
    for r, row in enumerate(values):
        for c, text in enumerate(row):
            # Every fallback cell is not evaluated until the FIELD tag check is shown right (D4).
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
        "layer": str(g("layer") or "0"),
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
    if not raw:
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
    runs = 0

    tmp = Path(tempfile.mkdtemp(prefix="redline-oda-", dir=tempfile.gettempdir()))

    def load(src: Path) -> Any:
        nonlocal runs
        dxf = src
        if src.suffix.lower() == ".dwg":
            runs += 1
            dxf = _to_dxf(odafc, src, tmp, runs, timeout)
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
        tag = f"block:{xname}" if xname else None
        for lay in doc.layouts:
            for e in lay:
                add(e, tag or lay.name, xpath)
        for blk in doc.blocks:
            if blk.is_any_layout:
                continue
            if blk.block_record.is_xref:
                follow(blk, origin)
                continue
            for e in blk:
                add(e, tag or f"block:{blk.name}", xpath)

    def follow(blk: Any, origin: Path) -> None:
        name, raw = blk.name, str(blk.block.dxf.get("xref_path") or "")
        target = _inside(raw, origin, root)
        done = False
        if target is not None and target in visited:
            done = True  # read already, or a cycle
        elif target is not None and target.suffix.lower() in (".dwg", ".dxf") and target.is_file():
            if target.suffix.lower() == ".dwg" and odafc is None:
                notes.append(f"xref {name} is a DWG and odafc_path is not set, so it was not read")
            else:
                visited.add(target)
                try:
                    walk(load(target), target.parent, name, raw)
                    done = True
                except ExtractError as e:
                    notes.append(f"xref {name} was not read: {e}")
        xrefs.append({"name": name, "path": raw, "resolved": done})

    try:
        doc = load(path)
        walk(doc, root, None, None)
        units = ezunits.decode(doc.units) if doc.units else "unitless"
        layouts = list(doc.layouts.names_in_taborder())
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
