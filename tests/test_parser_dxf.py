import copy
import csv
import json
import sys
import time
import types
from dataclasses import fields, replace
from pathlib import Path

import pytest

from redline.model import Circuit, Confidence, Value
from redline.parsers import csv_xlsx, dxf

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "samples" / "dwg" / "panel_sheet.acad_plugin.rawdrawing.json"
FALLBACK = ROOT / "samples" / "dwg" / "panel_sheet.oda_ezdxf.rawdrawing.json"
HEADER = ["Ckt", "Description", "Load (VA)", "Breaker", "Poles", "Wire Sz."]
ROWS = [
    ["1", "Corridor lighting", "1350", "20 A", "1", "12 AWG"],
    ["2", "Office lighting east", "1500", "15", "1", "12 AWG"],
    ["4", "Office receptacles", "1800", "15", "1", "12 AWG"],
]


def load(path: Path = PLUGIN) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def drawing(entities=(), xrefs=(), **top) -> dict:
    d = {
        "schema_version": "1.0",
        "extractor": "acad_plugin",
        "extractor_version": "0.1.0",
        "host_version": "AutoCAD 2026",
        "source_file": "t.dwg",
        "source_sha256": "ab" * 32,
        "extracted_at": "2026-11-09T00:00:00Z",
        "document": {"units": "mm", "layouts": ["E-1"], "xrefs": list(xrefs), "warnings": []},
        "entities": list(entities),
    }
    d.update(top)
    return d


def table(grid, handle="A1", layout="E-1", evaluated=True, counts=True, **extra) -> dict:
    cells = [
        {"r": r, "c": c, "text": t, "evaluated": evaluated}
        for r, row in enumerate(grid)
        for c, t in enumerate(row)
    ]
    n = len(grid), max(len(r) for r in grid)
    t = {"rows": n[0] if counts else None, "cols": n[1] if counts else None, "cells": cells}
    return {
        "id": f"e{handle}",
        "type": "ACAD_TABLE",
        "layout": layout,
        "handle": handle,
        "table": t,
    } | extra


def schedule(name="LP-9", rows=ROWS) -> list[list[str]]:
    return [["Panel", name, "", "", "", ""], HEADER, *rows]


_n = iter(range(1_000_000))


def text(s, x, y, layout="E-1", h=2.5, rot=0, kind="TEXT", **extra) -> dict:
    n = next(_n)
    e = {"id": f"t{n}", "type": kind, "layout": layout, "handle": f"{n:X}", "text": s}
    e |= {"text_height": h, "rotation_deg": rot, "insertion_point": [x, y]}
    return e | extra


def loose(name="LP-9", rows=ROWS, layout="E-1", x0=0.0, y0=100.0, **kw) -> list[dict]:
    xs = [0, 20, 90, 130, 170, 200]
    out = [text(f"Panel {name}", x0, y0, layout, **kw)]
    for i, row in enumerate([HEADER, *rows], 1):
        out += [text(t, x0 + x, y0 - 8 * i, layout, **kw) for x, t in zip(xs, row, strict=True)]
    return out


def values(unit) -> dict[str, Value]:
    return {
        f.name: getattr(unit, f.name) for f in fields(unit) if f.default_factory is Value.missing
    }


def all_sources(parsed):
    for p in parsed.panels:
        yield p.source
        yield from (v.source for v in values(p).values() if v.source)
        for c in p.circuits:
            yield c.source
            yield from (v.source for v in values(c).values() if v.source)
    yield from (u.source for u in parsed.unparsed)


# ---- tables ----


def test_native_table_matches_csv(test_cfg, tmp_path):
    lp11 = next(e for e in load()["entities"] if e["handle"] == "2F01")["table"]
    grid = [[""] * lp11["cols"] for _ in range(lp11["rows"])]
    for c in lp11["cells"]:
        grid[c["r"]][c["c"]] = c["text"]
    path = tmp_path / "lp11.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(grid)
    want = csv_xlsx.parse_file(path, test_cfg).panels[0]
    got = dxf.parse_rawdrawing(load(), test_cfg, list_blocks=False).panels[0]
    assert (got.name, len(got.circuits)) == (want.name, 20)
    seen = set()
    for g, w in [(got, want), *zip(got.circuits, want.circuits, strict=True)]:
        for k, wv in values(w).items():
            gv = values(g)[k]
            assert (gv.value, gv.confidence) == (wv.value, wv.confidence), (g, k)
            seen.add(gv.confidence)
        if isinstance(g, Circuit):
            assert (g.number, g.is_spare) == (w.number, w.is_spare)
    assert Confidence.HIGH in seen


def test_no_row_count_is_low_unparsed(test_cfg):
    d = drawing([table(schedule(), handle="B7", counts=False)])
    out = dxf.parse_rawdrawing(d, test_cfg, list_blocks=False)
    assert out.panels == []
    [u] = [u for u in out.unparsed if u.kind == "table"]
    assert u.source.confidence == Confidence.LOW
    assert "handle=B7" in u.source.locator and "layout=E-1" in u.source.locator
    assert "no row and column counts" in u.reason


def test_unevaluated_field_is_low(test_cfg):
    t = table(schedule())
    for c in t["table"]["cells"]:
        if c["c"] == 2 and c["r"] >= 2:
            c["evaluated"] = False
    [p] = dxf.parse_rawdrawing(drawing([t]), test_cfg, list_blocks=False).panels
    for c in p.circuits:
        assert c.load_va.confidence == Confidence.LOW
        assert c.load_va.value is not None
        assert "may be stale" in c.load_va.source.note
        assert c.breaker_a.confidence == Confidence.HIGH


def test_field_table_plugin_vs_fallback(test_cfg):
    a = dxf.parse_rawdrawing(load(PLUGIN), test_cfg, list_blocks=False).panels[1]
    b = dxf.parse_rawdrawing(load(FALLBACK), test_cfg, list_blocks=False).panels[1]
    assert a.name == b.name == "LP-12"
    for ca, cb in zip(a.circuits, b.circuits, strict=True):
        for k, va in values(ca).items():
            vb = values(cb)[k]
            assert (va.value, va.raw) == (vb.value, vb.raw)
            if k == "load_va":  # field cell: both extractors write evaluated false
                assert va.confidence == vb.confidence == Confidence.LOW
                assert "may be stale" in va.source.note and "may be stale" in vb.source.note
            elif va.source:
                assert va.confidence > Confidence.LOW
                assert vb.confidence == Confidence.LOW  # D4: every fallback cell is not evaluated


def test_dwg_fixture_counts(test_cfg):
    for path in (PLUGIN, FALLBACK):
        out = dxf.parse_rawdrawing(load(path), test_cfg, list_blocks=False)
        assert [(p.name, len(p.circuits)) for p in out.panels] == [
            ("LP-11", 20),
            ("LP-12", 6),
            ("LP-13", 6),
        ]
        assert sum(u.kind == "xref" for u in out.unparsed) == 1
        no_count = [u for u in out.unparsed if u.kind == "table" and "counts" in u.reason]
        assert len(no_count) == 1


def test_small_table_listed(test_cfg):
    out = dxf.parse_rawdrawing(
        drawing([table([["Panel", "LP-1"], ["x", ""]])]), test_cfg, list_blocks=False
    )
    assert out.panels == []
    [u] = [u for u in out.unparsed if u.kind == "table"]
    assert u.reason == "too few cells to be a schedule"


def test_oversized_table_listed_not_allocated(test_cfg):
    t = table([["a", "b", "c", "d"]])
    t["table"]["rows"], t["table"]["cols"] = 10**9, 10**9
    out = dxf.parse_rawdrawing(drawing([t]), test_cfg, list_blocks=False)
    assert [u.kind for u in out.unparsed] == ["table"] and "cell cap" in out.unparsed[0].reason


def test_table_in_xref_names_its_path(test_cfg):
    out = dxf.parse_rawdrawing(
        drawing([table(schedule(), xref_path="X.dwg")]), test_cfg, list_blocks=False
    )
    assert "xref=X.dwg" in out.panels[0].circuits[0].source.locator


# ---- loose text, *T blocks, xrefs, inserts ----


def test_loose_text_schedule_medium(test_cfg):
    out = dxf.parse_rawdrawing(drawing(loose()), test_cfg, list_blocks=False)
    [p] = out.panels
    assert (p.name, len(p.circuits)) == ("LP-9", 3)
    confs = {v.confidence for c in p.circuits for v in values(c).values() if v.source}
    assert confs == {Confidence.MEDIUM}
    assert p.source.confidence <= Confidence.MEDIUM
    assert "read from loose text" in p.circuits[0].load_va.source.note
    assert p.circuits[0].load_va.source.method.value == "dxf_text"
    assert "layout=E-1; y=" in p.circuits[0].source.locator


def test_loose_coverage_summary_matches_values(test_cfg):
    out = dxf.parse_rawdrawing(drawing(loose()), test_cfg, list_blocks=False)
    entry = next(c for c in out.coverage if c.unit == "LP-9")
    assert "HIGH 0" in entry.confidence_summary and "MEDIUM 0" not in entry.confidence_summary


def test_loose_title_line_split(test_cfg):
    [p] = dxf.parse_rawdrawing(drawing(loose("RP-4")), test_cfg, list_blocks=False).panels
    assert p.name == "RP-4"


def test_anonymous_t_block_medium(test_cfg):
    out = dxf.parse_rawdrawing(drawing(loose(layout="block:*T3")), test_cfg, list_blocks=False)
    [p] = out.panels
    assert len(p.circuits) == 3
    top = max(v.confidence for c in p.circuits for v in values(c).values() if v.source)
    assert top == Confidence.MEDIUM
    assert "layout=block:*T3" in p.circuits[0].source.locator


def test_named_block_text_is_counted_not_read(test_cfg):
    out = dxf.parse_rawdrawing(drawing(loose(layout="block:SYM")), test_cfg, list_blocks=False)
    assert out.panels == []
    assert "texts in other block definitions not read" in out.coverage[-1].what_read


def test_rotated_text_not_clustered(test_cfg):
    out = dxf.parse_rawdrawing(drawing(loose(rot=90)), test_cfg, list_blocks=False)
    assert out.panels == [] and out.unparsed == []
    assert "25 texts not clustered" in out.coverage[-1].what_read
    upside = dxf.parse_rawdrawing(drawing(loose(rot=180)), test_cfg, list_blocks=False)
    assert len(upside.panels) == 1


def test_loose_text_without_header_is_one_item(test_cfg):
    notes = [text(s, 0, 50 - 5 * i) for i, s in enumerate(["NOTES", "a b", "c d", "e f"])]
    out = dxf.parse_rawdrawing(drawing(notes), test_cfg, list_blocks=False)
    assert out.panels == []
    [u] = out.unparsed
    assert u.kind == "table" and "no panel schedule header" in u.reason


def test_unresolved_xref_unparsed(test_cfg):
    xr = [
        {"name": "A-BASE", "path": "..\\A-BASE.dwg", "resolved": False},
        {"name": "B", "path": "B.dwg", "resolved": True},
    ]
    out = dxf.parse_rawdrawing(drawing(xrefs=xr), test_cfg, list_blocks=False)
    [u] = out.unparsed
    assert (u.kind, u.raw) == ("xref", "A-BASE")
    assert "A-BASE.dwg" in u.reason and u.source.confidence == Confidence.LOW


def test_device_inserts_counted(test_cfg):
    ins = [
        {
            "id": f"i{i}",
            "type": "INSERT",
            "layout": "E-1",
            "handle": f"F{i}",
            "block_name": "RECEPT",
            "attributes": [{"tag": "CKT", "value": "1"}],
        }
        for i in range(3)
    ]
    ins.append(dict(ins[0], id="plain", handle="FF", attributes=[]))
    out = dxf.parse_rawdrawing(drawing(ins), test_cfg, list_blocks=False)
    assert out.unparsed == []
    assert "3 block references with attributes not read as schedules" in out.coverage[-1].what_read


# ---- WD_M ----


def wd_drawing() -> dict:
    wd = {
        "id": "w",
        "type": "INSERT",
        "layout": "E-1",
        "handle": "9A",
        "block_name": "wd_m",
        "attributes": [{"tag": "SHEET", "value": "E-101"}, {"tag": "DWGDESC", "value": "Lighting"}],
    }
    return drawing([wd])


def test_wd_m_empty_map_lists_attributes(test_cfg):
    out = dxf.parse_rawdrawing(wd_drawing(), test_cfg, list_blocks=False)
    assert [(u.kind, u.raw) for u in out.unparsed] == [
        ("column", "SHEET=E-101"),
        ("column", "DWGDESC=Lighting"),
    ]
    assert "aecad_project.wd_m_attribute_map" in out.unparsed[0].reason
    assert "attrib=SHEET" in out.unparsed[0].source.locator
    assert "WD_M values" not in out.coverage[-1].what_read


def test_wd_m_map_reads_sheet(test_cfg):
    maps = copy.deepcopy(test_cfg.column_maps)
    maps["aecad_project"]["wd_m_attribute_map"] = {"sheet": ["sheet"]}
    out = dxf.parse_rawdrawing(wd_drawing(), replace(test_cfg, column_maps=maps), list_blocks=False)
    assert "WD_M values sheet E-101" in out.coverage[-1].what_read
    assert [u.raw for u in out.unparsed] == ["DWGDESC=Lighting"]


# ---- provenance ----


def test_source_extractor_stamped(test_cfg):
    out = dxf.parse_rawdrawing(load(), test_cfg, list_blocks=False)
    srcs = list(all_sources(out))
    assert len(srcs) > 100
    assert {s.extractor for s in srcs} == {"acad_plugin@0.1.0"}


def test_provenance_string(test_cfg):
    d = drawing()
    want = "acad_plugin 0.1.0, host AutoCAD 2026, SHA-256 " + "ab" * 32
    assert dxf.provenance(d) == want
    assert dxf.parse_rawdrawing(d, test_cfg, list_blocks=False).provenance == {"t.dwg": want}


def test_drawing_coverage_entry(test_cfg):
    empty = dxf.parse_rawdrawing(drawing(), test_cfg, list_blocks=False)
    [e] = [c for c in empty.coverage if c.unit == "drawing"]
    assert e.file == "t.dwg" and "acad_plugin 0.1.0" in e.what_read
    full = dxf.parse_rawdrawing(load(), test_cfg, list_blocks=False)
    assert [c.unit for c in full.coverage].count("drawing") == 1
    assert "2 tables read, 1 listed" in full.coverage[-1].what_read
    assert "1 loose-text clusters read" in full.coverage[-1].what_read


def test_layout_and_handle_in_locator(test_cfg):
    out = dxf.parse_rawdrawing(load(), test_cfg, list_blocks=False)
    c = out.panels[0].circuits[0]
    assert c.source.locator == "layout=E-101; handle=2F01; r=2"
    assert c.load_va.source.locator.startswith("layout=E-101; handle=2F01; r=2; col=")


# ---- file entry ----


def test_parse_file_json_fixture(test_cfg):
    out = dxf.parse_file(PLUGIN, test_cfg)
    assert [p.name for p in out.panels] == ["LP-11", "LP-12", "LP-13"]
    assert list(out.provenance) == [PLUGIN.name]
    assert out.provenance[PLUGIN.name].startswith("acad_plugin 0.1.0, host ")


def test_invalid_json_is_input_error(test_cfg, tmp_path):
    bad = tmp_path / "x.rawdrawing.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(csv_xlsx.InputError):
        dxf.parse_file(bad, test_cfg)
    bad.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
    with pytest.raises(csv_xlsx.InputError, match="not a valid RawDrawing"):
        dxf.parse_file(bad, test_cfg)
    with pytest.raises(csv_xlsx.InputError):
        dxf.parse_file(tmp_path / "missing.rawdrawing.json", test_cfg)


def fake_extract(monkeypatch, make):
    class ExtractError(Exception):
        pass

    mod = types.ModuleType("redline.extract")
    mod.ExtractError, mod.extract = ExtractError, make(ExtractError)
    monkeypatch.setitem(sys.modules, "redline.extract", mod)


def test_extract_error_is_input_error(test_cfg, tmp_path, monkeypatch):
    def make(err):
        def extract(path, cfg):
            raise err("ODA File Converter is not installed")

        return extract

    fake_extract(monkeypatch, make)
    f = tmp_path / "a.dwg"
    f.write_bytes(b"")
    with pytest.raises(csv_xlsx.InputError, match="ODA File Converter is not installed"):
        dxf.parse_file(f, test_cfg)


def test_dwg_suffix_goes_through_extract(test_cfg, tmp_path, monkeypatch):
    fake_extract(monkeypatch, lambda err: lambda path, cfg: load())
    f = tmp_path / "Plan.DWG"
    f.write_bytes(b"")
    out = dxf.parse_file(f, test_cfg)
    assert len(out.panels) == 3 and list(out.provenance) == ["Plan.DWG"]


def test_accepts_suffixes():
    for name in ("a.dwg", "A.DWG", "b.Dxf", "c.rawdrawing.json", "C.RawDrawing.JSON"):
        assert dxf.accepts(Path(name)), name
    for name in ("a.json", "a.csv", "a.dwg.bak", "rawdrawing.json.txt"):
        assert not dxf.accepts(Path(name)), name


# ---- odd content ----


def bare(kind, **extra) -> dict:
    return {"id": "x", "type": kind, "layout": "E-1", "handle": "1"} | extra


def test_parse_never_raises_on_odd_content(test_cfg):
    empty_table = table(schedule()) | {"table": {"rows": 0, "cols": 0, "cells": []}}
    outside = table(schedule()) | {"table": {"rows": 2, "cols": 2, "cells": [{"r": 9, "c": 9}]}}
    odd = [
        drawing([table([[""]])]),
        drawing([empty_table]),
        drawing([outside]),
        drawing([text("", 0, 0), text("x", 1e300, -1e300), text("y", 0, 0, h=1e-300)]),
        drawing([text(s, 0, 0) for s in ["a", "b", "c", "d", "e"]]),
        drawing([text("a", 0, 0, rot=1e30), text("b", 0, 0, rot=-1e30)]),
        drawing([bare("TEXT", text=None)]),
        drawing([bare("INSERT", attributes=None)]),
        drawing([bare("INSERT", block_name="WD_M")]),
        drawing([bare("MLEADER")]),
        drawing(loose(rows=[]) + loose(rows=[["1"] * 6, ["1"] * 6])),
        drawing(loose(layout="block:*T1", rot=45) + [table(schedule(), layout="block:*T1")]),
        drawing(xrefs=[{"name": "", "path": "", "resolved": False}]),
    ]
    for d in odd:
        out = dxf.parse_rawdrawing(d, test_cfg, list_blocks=False)
        assert out.coverage[-1].unit == "drawing"


def test_loose_title_without_digit_is_not_split(test_cfg):
    d = drawing(loose("RP-4"))
    d["entities"][0]["text"] = "LIGHTING PANEL SCHEDULE"
    out = dxf.parse_rawdrawing(d, test_cfg, list_blocks=False)
    assert out.panels == [] or all(p.name != "SCHEDULE" for p in out.panels)
    assert any(u.raw == "LIGHTING PANEL SCHEDULE" for u in out.unparsed)


def test_table_render_block_text_is_not_read_again(test_cfg):
    d = drawing(loose(layout="block:*T2") + [table(schedule())])
    out = dxf.parse_rawdrawing(d, test_cfg, list_blocks=False)
    assert not any("block:*T" in c.source.locator for p in out.panels for c in p.circuits)
    assert "texts in table render blocks not read twice" in out.coverage[-1].what_read


def _lp(out):
    return [p.name for p in out.panels]


def test_orphan_table_render_block_is_still_read(test_cfg):
    other = [
        ["7", "Boiler room", "900", "30 A", "2", "10 AWG"],
        ["8", "Boiler fan", "700", "25", "2", "10 AWG"],
        ["9", "Pump", "600", "20", "2", "10 AWG"],
    ]
    d = drawing(loose(name="LP-9", layout="block:*T2") + [table(schedule("LP-7", other))])
    names = _lp(dxf.parse_rawdrawing(d, test_cfg, list_blocks=False))
    assert names.count("LP-9") == 1 and names.count("LP-7") == 1


def test_unread_table_render_block_is_still_read(test_cfg):
    blank = table([[""] * 6 for _ in range(3)])
    d = drawing(loose(layout="block:*T2") + [blank])
    out = dxf.parse_rawdrawing(d, test_cfg, list_blocks=False)
    assert _lp(out).count("LP-9") == 1
    assert "not read twice" not in out.coverage[-1].what_read


def _seconds(d, cfg) -> float:
    t0 = time.perf_counter()
    dxf.parse_rawdrawing(d, cfg, list_blocks=False)
    return time.perf_counter() - t0


def test_loose_text_one_long_line_is_linear(test_cfg):
    d = drawing([text(str(i), float(i), 50.0) for i in range(8000)])
    assert _seconds(d, test_cfg) < 1.0


def test_many_layouts_is_linear(test_cfg):
    d = drawing([text("x", 0.0, 0.0, layout=f"L{i}") for i in range(20000)])
    assert _seconds(d, test_cfg) < 1.0


def test_loose_text_summary_counts_capped_values(test_cfg):
    out = dxf.parse_rawdrawing(drawing(loose()), test_cfg, list_blocks=False)
    [p] = out.panels
    n = sum(1 for c in p.circuits for v in values(c).values() if v.source)
    entry = next(c for c in out.coverage if c.unit == "LP-9")
    summary = dict(s.rsplit(" ", 1) for s in entry.confidence_summary.split(", "))
    assert summary["HIGH"] == "0" and int(summary["MEDIUM"]) >= n - int(summary["LOW"]) - int(
        summary["MISSING"]
    )
    assert all(int(v) >= 0 for v in summary.values())


def test_loose_text_summary_error_keeps_cluster(test_cfg, monkeypatch):
    real = dxf.rows_to_panels

    def bad(*a, **k):
        part = real(*a, **k)
        part.coverage = [replace(c, confidence_summary="garbage") for c in part.coverage]
        return part

    monkeypatch.setattr(dxf, "rows_to_panels", bad)
    out = dxf.parse_rawdrawing(drawing(loose()), test_cfg, list_blocks=False)
    assert [p.name for p in out.panels] == ["LP-9"]


def test_xref_text_not_reported_as_block_definition_text(test_cfg):
    ents = loose(layout="block:SYM", xref_path="x/plan.dwg")
    what = dxf.parse_rawdrawing(drawing(ents), test_cfg, list_blocks=False).coverage[-1].what_read
    assert "texts in other block definitions not read" not in what
    assert "texts in xref x/plan.dwg not read" in what


def test_loose_text_oversize_grid_listed_not_built(test_cfg):
    m = 6000
    ents = [text("h", float(i), 0.0) for i in range(m)]
    ents += [text("r", 0.0, -10.0 * (i + 1)) for i in range(m)]
    t0 = time.perf_counter()
    out = dxf.parse_rawdrawing(drawing(ents), test_cfg, list_blocks=False)
    assert time.perf_counter() - t0 < 1.0
    assert out.panels == []
    assert any("over the cell cap" in u.reason for u in out.unparsed)


def test_loose_text_repeated_panel_coverage_counts_own_panel(test_cfg):
    two = loose("LP-9", ROWS[:1]) + loose("LP-9", ROWS, y0=-200.0)
    out = dxf.parse_rawdrawing(drawing(two), test_cfg, list_blocks=False)
    ps = [p for p in out.panels if p.name == "LP-9"]
    cov = [c for c in out.coverage if c.unit == "LP-9"]
    assert len(ps) == len(cov) == 2

    def n(p):
        return sum(
            1
            for u in (p, *p.circuits)
            for f in fields(u)
            if isinstance((v := getattr(u, f.name)), Value) and v.source
        )

    for p, c in zip(ps, cov, strict=True):
        got = dict(s.rsplit(" ", 1) for s in c.confidence_summary.split(", "))
        assert sum(int(v) for v in got.values()) == n(p)
    assert cov[0].confidence_summary != cov[1].confidence_summary


def test_declared_cells_capped_per_drawing_parse(test_cfg):
    def big(i):
        cells = [{"r": r, "c": 0, "text": "x", "evaluated": True} for r in range(4)]
        t = {"rows": 100_000, "cols": 1, "cells": cells}
        return {
            "id": f"b{i}",
            "type": "ACAD_TABLE",
            "layout": "E-1",
            "handle": f"{i:X}",
            "table": t,
        }

    t0 = time.perf_counter()
    out = dxf.parse_rawdrawing(drawing([big(i) for i in range(100)]), test_cfg, list_blocks=False)
    assert time.perf_counter() - t0 < 3.0
    capped = [u for u in out.unparsed if "cell cap" in u.reason and "drawing" in u.reason]
    assert len(capped) >= 90


def test_document_warnings_listed_in_unparsed(test_cfg):
    d = drawing()
    d["document"]["warnings"] = ["table A1 not read: size invalid", "skipped 2 VIEWPORT"]
    out = dxf.parse_rawdrawing(d, test_cfg, list_blocks=False)
    reasons = [u.reason for u in out.unparsed]
    for w in d["document"]["warnings"]:
        assert any(w in r and "t.dwg" in u.source.file for r, u in zip(reasons, out.unparsed))


def test_star_t_matching_is_near_linear(test_cfg):
    n = 6000
    grid = [
        ["Panel", "LP-9"],
        ["Ckt", "Breaker", "Poles", "Wire Sz."],
        ["1", "20 A", "1", "12 AWG"],
    ]
    tables = [table(grid, handle=f"{i:X}") for i in range(n)]
    stars = [text("1", 0.0, 0.0, layout=f"block:*T{j}") for j in range(n)]
    base = _seconds(drawing(tables), test_cfg)  # reading the tables is linear and not under test
    assert _seconds(drawing(tables + stars), test_cfg) - base < 2.0


def test_loose_text_merge_is_linear(test_cfg):
    ents = [
        text("x" * 1000, i * 1.0, 0.0, h=2.5, bbox=[i * 1.0, 0, i * 1.0 + 1.0, 2.5])
        for i in range(20000)
    ]
    t0 = time.perf_counter()
    dxf.parse_rawdrawing(drawing(ents), test_cfg, list_blocks=False)
    assert time.perf_counter() - t0 < 5.0


def test_star_t_matching_budget_distinct_tables(test_cfg):
    n = 6000
    head = ["Ckt", "Breaker", "Poles", "Wire Sz."]
    tables = [
        table([["Panel", f"LP-{i}"], head, ["1", "20 A", "1", "12 AWG"]], handle=f"{i:X}")
        for i in range(n)
    ]
    shared = ["1", "20 A", *head]
    stars = [
        text(s, 0.0, 0.0, layout=f"block:*T{j}", rot=90)
        for j in range(n)
        for s in (*shared, f"q{j}")
    ]
    d = drawing(tables + stars)
    base = min(_seconds(drawing(tables), test_cfg) for _ in range(2))  # best of two, against noise
    with_stars = min(_seconds(d, test_cfg) for _ in range(2))
    assert with_stars - base < 1.0
    out = dxf.parse_rawdrawing(d, test_cfg, list_blocks=False)
    assert "table render blocks not read twice" not in out.coverage[-1].what_read


def test_star_t_budget_keeps_real_render_block_matched(test_cfg):
    rows = [[str(i), "Lighting", "1350", "20 A", "1", "12 AWG"] for i in range(1, 50)]
    tables = [table(schedule(f"LP-{k}", rows), handle=f"{k:X}") for k in range(20)]
    render = loose("LP-0", rows, layout="block:*T1")
    out = dxf.parse_rawdrawing(drawing(tables + render), test_cfg, list_blocks=False)
    assert [p.name for p in out.panels].count("LP-0") == 1
    assert "texts in table render blocks not read twice" in out.coverage[-1].what_read


def test_star_t_many_similar_schedules_not_doubled(test_cfg):
    rows = [[str(i), "Lighting", "1350", "20 A", "1", "12 AWG"] for i in range(1, 43)]
    ents = []
    for k in range(100):
        grid = schedule(f"LP-{k}", rows)
        ents.append(table(grid, handle=f"{k:X}"))
        ents += [
            text(t, 20.0 * c, -8.0 * r, layout=f"block:*T{k}")
            for r, row in enumerate(grid)
            for c, t in enumerate(row)
            if t
        ]
    out = dxf.parse_rawdrawing(drawing(ents), test_cfg, list_blocks=False)
    names = [p.name for p in out.panels]
    assert len(names) == 100 and len(set(names)) == 100
    assert "texts in table render blocks not read twice" in out.coverage[-1].what_read


# ---- the field flag (D6) ----


def _flagged(flag) -> dict:
    ents = loose()
    stale = next(e for e in ents if e["text"] == "1350")
    if flag is not None:
        stale["evaluated"] = flag
    return drawing(ents)


def _load_value(out):
    return out.panels[0].circuits[0].load_va


def test_unevaluated_text_is_low(test_cfg):
    out = dxf.parse_rawdrawing(_flagged(False), test_cfg, list_blocks=False)
    v = _load_value(out)
    assert v.confidence == Confidence.LOW and dxf.STALE_NOTE in v.source.note
    assert out.panels[0].circuits[1].load_va.confidence == Confidence.MEDIUM


def test_unevaluated_attribute_noted(test_cfg):
    d = wd_drawing()
    d["entities"][0]["attributes"][0]["evaluated"] = False
    out = dxf.parse_rawdrawing(d, test_cfg, list_blocks=False)
    assert "WD_M value SHEET from a field, may be stale" in out.coverage[-1].what_read


def test_absent_flag_keeps_medium(test_cfg):
    for flag in (None, True):
        v = _load_value(dxf.parse_rawdrawing(_flagged(flag), test_cfg, list_blocks=False))
        assert v.confidence == Confidence.MEDIUM


def test_list_blocks_keyword_required(test_cfg):
    import pytest

    parse = dxf.parse_rawdrawing  # a bare name, so a call without the keyword stays visible here
    with pytest.raises(TypeError):
        parse(drawing(), test_cfg)
    with pytest.raises(TypeError):
        parse(drawing(), test_cfg, False)
