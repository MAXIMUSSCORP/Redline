import copy
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import ezdxf
import pytest
from ezdxf import recover

import redline.extract as extract_pkg
from redline import rawdrawing
from redline.config import load_config
from redline.extract import ExtractError, Unavailable, acad_console, oda_ezdxf, sha256_of

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "samples" / "dwg" / "panel_sheet.acad_plugin.rawdrawing.json"


def with_parsing(cfg, **kw):
    maps = copy.deepcopy(cfg.column_maps)
    maps["parsing"].update(kw)
    return replace(cfg, column_maps=maps)


def save(doc, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    return path


def new_doc():
    return ezdxf.new("R2018")


class FakeEntity:
    """Stands in for an ACAD_TABLE, which ezdxf cannot write."""

    def __init__(self, rows, cols):
        sub = SimpleNamespace(
            get_first_value=lambda code, default=None: {91: rows, 92: cols}.get(code, default)
        )
        self.xtags = SimpleNamespace(get_subclass=lambda name: sub)
        self.dxf = SimpleNamespace(
            get=lambda key, default=None: {"handle": "2F01", "layer": "E-PANEL"}.get(key, default)
        )

    def dxftype(self):
        return "ACAD_TABLE"


def fake_acad_table(values):
    return SimpleNamespace(read_acad_table_content=lambda e: values)


def wrap(entities):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["entities"] = [{"id": f"e{i + 1:04d}", **e} for i, e in enumerate(entities)]
    return data


def test_oda_dxf_text_mtext_insert_read(tmp_path, test_cfg):
    doc = new_doc()
    blk = doc.blocks.new("PNL")
    blk.add_attdef("NAME", (0, 0))
    msp = doc.modelspace()
    msp.add_text("HELLO", height=2.5, dxfattribs={"insert": (1, 2), "layer": "E-TEXT"})
    msp.add_mtext("line one\\Pline two", dxfattribs={"char_height": 3.0, "insert": (4, 5)})
    msp.add_blockref("PNL", (3, 3)).add_auto_attribs({"NAME": "LP-1"})
    msp.add_line((0, 5), (10, 1))
    msp.add_circle((0, 0), 1)
    path = save(doc, tmp_path / "plan.dxf")
    data = oda_ezdxf.extract(path, test_cfg)
    by_type = {e["type"]: e for e in data["entities"]}
    assert by_type["TEXT"]["text"] == "HELLO"
    assert by_type["TEXT"]["text_height"] == 2.5
    assert by_type["TEXT"]["layer"] == "E-TEXT"
    assert by_type["TEXT"]["insertion_point"][:2] == [1.0, 2.0]
    assert by_type["MTEXT"]["text"] == "line one\nline two"
    assert by_type["INSERT"]["block_name"] == "PNL"
    assert by_type["INSERT"]["attributes"] == [{"tag": "NAME", "value": "LP-1"}]
    assert by_type["LINE"]["bbox"] == [0.0, 1.0, 10.0, 5.0]
    assert "Model" in data["document"]["layouts"]
    assert any("CIRCLE x1" in w for w in data["document"]["warnings"])
    assert data["extractor"] == "oda_ezdxf"
    assert "ezdxf" in data["host_version"]


def test_oda_table_cells_not_evaluated():
    notes = []
    values = [["Panel", "LP-1"], ["Ckt", "1"]]
    item = oda_ezdxf.convert(FakeEntity(2, 2), "E-101", None, notes, fake_acad_table(values))
    table = item["table"]
    assert (table["rows"], table["cols"]) == (2, 2)
    assert len(table["cells"]) == 4
    assert all(c["evaluated"] is False for c in table["cells"])
    assert [(c["r"], c["c"]) for c in table["cells"]] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert rawdrawing.validate(wrap([item])).ok


def _field(code_values, children=()):
    tags = [SimpleNamespace(code=c, value=v) for c, v in code_values]
    tags += [SimpleNamespace(code=360, value=h) for h in children]
    return SimpleNamespace(dxftype=lambda: "FIELD", xtags=SimpleNamespace(subclasses=[tags]))


def test_oda_field_cell_reads_cached_child_text_and_keeps_failed_value():
    db = {
        "A": _field([(1, "_text"), (301, "")], ["B"]),
        "B": _field([(1, "AcExpr"), (301, "1350")]),
        "C": _field([(1, "_text"), (301, "")], ["D"]),
        "D": _field([(1, "AcDiesel"), (301, "####")]),
    }
    ent = FakeEntity(2, 2)
    ent.doc = SimpleNamespace(entitydb=SimpleNamespace(get=db.get))
    tags = [SimpleNamespace(code=c, value=v) for c, v in [(171, 1), (171, 1), (171, 1), (344, "A")]]
    tags += [SimpleNamespace(code=171, value=1), (SimpleNamespace(code=344, value="C"))]

    class Sub(list):
        get_first_value = staticmethod(lambda code, default=None: {91: 2, 92: 2}.get(code, default))

    ent.xtags = SimpleNamespace(get_subclass=lambda name: Sub(tags))
    values = [["", ""], ["", ""]]
    item = oda_ezdxf.convert(ent, "E-101", None, [], fake_acad_table(values))
    cells = {(c["r"], c["c"]): c for c in item["table"]["cells"]}
    assert cells[(1, 0)]["text"] == "1350"
    assert cells[(1, 1)]["text"] == "####"
    assert cells[(0, 0)]["text"] == ""
    assert {c["evaluated"] for c in cells.values()} == {False}


def _tag_table(tag_pairs, values):
    ent = FakeEntity(2, 2)
    ent.doc = SimpleNamespace(entitydb=SimpleNamespace(get=lambda h: None))
    tags = [SimpleNamespace(code=c, value=v) for c, v in tag_pairs]

    class Sub(list):
        get_first_value = staticmethod(lambda code, default=None: {91: 2, 92: 2}.get(code, default))

    ent.xtags = SimpleNamespace(get_subclass=lambda name: Sub(tags))
    item = oda_ezdxf.convert(ent, "E-101", None, [], fake_acad_table(values))
    return {(c["r"], c["c"]): c for c in item["table"]["cells"]}


def test_oda_cell_text_from_code_1_when_302_is_empty():
    pairs = [(171, 1), (1, "K12"), (302, ""), (171, 1), (302, "own"), (1, "other")]
    pairs += [(171, 1), (3, "long "), (3, "text "), (1, "end"), (302, "")]
    cells = _tag_table(pairs, [["", "own"], ["", ""]])
    assert cells[(0, 0)]["text"] == "K12"
    assert cells[(0, 1)]["text"] == "own"
    assert cells[(1, 0)]["text"] == "long text end"
    assert cells[(1, 1)]["text"] == ""
    assert {c["evaluated"] for c in cells.values()} == {False}


def test_oda_cell_mtext_codes_become_plain_text():
    pairs = [(171, 1), (1, r"LOAD\PVA"), (171, 1), (1, r"{\fArial|b1;Bold} x")]
    cells = _tag_table(pairs, [["", ""], ["", ""]])
    assert cells[(0, 0)]["text"] == "LOAD VA"
    assert cells[(0, 1)]["text"] == "Bold x"
    assert "\\" not in cells[(0, 0)]["text"]


def test_oda_table_without_counts_emits_null():
    values = [["a", "b", "c"]]
    item = oda_ezdxf.convert(FakeEntity(0, 0), "E-101", None, [], fake_acad_table(values))
    table = item["table"]
    assert table["rows"] is None and table["cols"] is None
    assert [(c["r"], c["c"]) for c in table["cells"]] == [(0, 0), (0, 1), (0, 2)]
    assert all(c["evaluated"] is False for c in table["cells"])
    assert rawdrawing.validate(wrap([item])).ok


def test_oda_table_over_cap_raises_extract_error(monkeypatch):
    monkeypatch.setattr(rawdrawing, "MAX_TABLE_CELLS", 2)
    with pytest.raises(ExtractError, match="MAX_TABLE_CELLS"):
        oda_ezdxf.convert(FakeEntity(1, 3), "L", None, [], fake_acad_table([["a", "b", "c"]]))


def test_oda_unresolved_xref_listed(tmp_path, test_cfg):
    doc = new_doc()
    doc.add_xref_def("missing.dxf", "MISSING")
    doc.modelspace().add_text("host")
    data = oda_ezdxf.extract(save(doc, tmp_path / "host.dxf"), test_cfg)
    assert data["document"]["xrefs"] == [
        {"name": "MISSING", "path": "missing.dxf", "resolved": False}
    ]
    assert [e["text"] for e in data["entities"]] == ["host"]


def test_oda_xref_inside_folder_is_read_and_a_cycle_ends(tmp_path, test_cfg):
    base = new_doc()
    base.modelspace().add_text("from base")
    base.add_xref_def("../host.dxf", "HOST")  # points back at the host
    save(base, tmp_path / "xr" / "base.dxf")
    doc = new_doc()
    doc.add_xref_def("xr/base.dxf", "BASE")
    doc.modelspace().add_text("host")
    data = oda_ezdxf.extract(save(doc, tmp_path / "host.dxf"), test_cfg)
    got = {x["name"]: x["resolved"] for x in data["document"]["xrefs"]}
    assert got == {"BASE": True, "HOST": True}
    xr = [e for e in data["entities"] if e.get("xref_path")]
    assert [(e["text"], e["layout"], e["xref_path"]) for e in xr] == [
        ("from base", "block:BASE", "xr/base.dxf")
    ]


def test_oda_xref_outside_folder_not_read(tmp_path, test_cfg, monkeypatch):
    save(new_doc(), tmp_path / "outside.dxf")
    save(new_doc(), tmp_path / "other" / "far.dxf")
    doc = new_doc()
    doc.add_xref_def("../outside.dxf", "UP")
    doc.add_xref_def(str(tmp_path / "other" / "far.dxf"), "ABS")
    path = save(doc, tmp_path / "proj" / "host.dxf")
    read = []
    real = recover.readfile
    monkeypatch.setattr(recover, "readfile", lambda f, *a, **k: read.append(f) or real(f, *a, **k))
    data = oda_ezdxf.extract(path, test_cfg)
    assert read == [str(path)]
    assert {x["name"]: x["resolved"] for x in data["document"]["xrefs"]} == {
        "UP": False,
        "ABS": False,
    }


def test_oda_output_validates(tmp_path, test_cfg):
    doc = new_doc()
    doc.modelspace().add_text("x" * 20)
    path = save(doc, tmp_path / "a.dxf")
    data = oda_ezdxf.extract(path, test_cfg)
    assert rawdrawing.validate(data).ok
    assert data["source_sha256"] == sha256_of(path)
    assert data["entities"][0]["id"] == "e0001"


def test_oda_source_file_holds_name_only(tmp_path, test_cfg):
    data = oda_ezdxf.extract(save(new_doc(), tmp_path / "deep" / "er" / "a b.dxf"), test_cfg)
    assert data["source_file"] == "a b.dxf"


def test_oda_long_text_is_cut_and_noted(tmp_path, test_cfg, monkeypatch):
    monkeypatch.setattr(rawdrawing, "MAX_TEXT", 40)
    doc = new_doc()
    doc.modelspace().add_text("0123456789" * 5)
    data = oda_ezdxf.extract(save(doc, tmp_path / "a.dxf"), test_cfg)
    assert data["entities"][0]["text"] == "0123456789" * 4
    assert any("cut at MAX_TEXT" in w for w in data["document"]["warnings"])


def test_oda_entity_cap_gives_extract_error(tmp_path, test_cfg, monkeypatch):
    monkeypatch.setattr(rawdrawing, "MAX_ENTITIES", 1)
    doc = new_doc()
    doc.modelspace().add_text("a")
    doc.modelspace().add_text("b")
    with pytest.raises(ExtractError, match="MAX_ENTITIES"):
        oda_ezdxf.extract(save(doc, tmp_path / "a.dxf"), test_cfg)


def test_oda_unreadable_dxf_gives_extract_error(tmp_path, test_cfg):
    bad = tmp_path / "bad.dxf"
    bad.write_text("this is not a drawing", encoding="utf-8")
    with pytest.raises(ExtractError) as err:
        oda_ezdxf.extract(bad, test_cfg)
    assert not isinstance(err.value, Unavailable)


def test_oda_missing_odafc_is_unavailable_with_reason(tmp_path, test_cfg):
    dwg = tmp_path / "a.dwg"
    dwg.write_bytes(b"x")
    with pytest.raises(Unavailable, match="odafc_path is not set"):
        oda_ezdxf.extract(dwg, test_cfg)
    cfg = with_parsing(test_cfg, odafc_path=str(tmp_path / "nope" / "ODAFileConverter.exe"))
    with pytest.raises(Unavailable, match="odafc_path does not exist"):
        oda_ezdxf.extract(dwg, cfg)


def test_oda_ezdxf_missing_is_unavailable(tmp_path, test_cfg, monkeypatch):
    monkeypatch.setitem(sys.modules, "ezdxf", None)
    with pytest.raises(Unavailable, match="ezdxf not installed: pip install redline"):
        oda_ezdxf.extract(tmp_path / "a.dxf", test_cfg)


def fake_converter(monkeypatch, make, *, hang=False):
    """Replace Popen. make(indir, outdir, name) writes the converted DXF."""
    st = SimpleNamespace(args=None, kw=None, killed=False)

    class Proc:
        pid = 7

        def __init__(self, args, **kw):
            st.args, st.kw = args, kw
            if not hang:
                make(Path(args[1]), Path(args[2]), args[7])

        def wait(self, timeout=None):
            if hang:
                raise subprocess.TimeoutExpired(st.args, timeout)
            return 1

        def kill(self):
            st.killed = True

    monkeypatch.setattr(subprocess, "Popen", Proc)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    return st


def test_oda_dwg_goes_through_converter_and_is_read(tmp_path, test_cfg, monkeypatch):
    exe = tmp_path / "oda" / "ODAFileConverter.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"x")
    dwg = tmp_path / "work" / "plan.dwg"
    dwg.parent.mkdir()
    dwg.write_bytes(b"dwg bytes")

    def make(indir, outdir, name):
        assert (indir / name).is_file()
        doc = new_doc()
        doc.modelspace().add_text("converted")
        doc.saveas(outdir / "plan.dxf")

    st = fake_converter(monkeypatch, make)
    cfg = with_parsing(test_cfg, odafc_path=str(exe))
    data = oda_ezdxf.extract(dwg, cfg)
    a = st.args
    assert a[0] == str(exe) and a[3:7] == ["ACAD2018", "DXF", "0", "1"] and a[7] == "plan.dwg"
    assert st.kw["shell"] is False
    assert data["entities"][0]["text"] == "converted"
    assert data["source_file"] == "plan.dwg"
    assert data["source_sha256"] == sha256_of(dwg)
    assert data["host_version"].startswith("ODA File Converter")


def test_oda_converter_timeout_gives_extract_error_and_cleans_up(tmp_path, test_cfg, monkeypatch):
    exe = tmp_path / "ODAFileConverter.exe"
    exe.write_bytes(b"x")
    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"x")
    root = tmp_path / "tmproot"
    root.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(root))
    st = fake_converter(monkeypatch, None, hang=True)
    cfg = with_parsing(test_cfg, odafc_path=str(exe), dxf_extractor_timeout_s=3)
    with pytest.raises(ExtractError, match="ODA File Converter timed out after 3 s"):
        oda_ezdxf.extract(dwg, cfg)
    assert st.killed
    assert list(root.iterdir()) == []


def test_oda_converter_without_output_gives_extract_error(tmp_path, test_cfg, monkeypatch):
    exe = tmp_path / "ODAFileConverter.exe"
    exe.write_bytes(b"x")
    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"x")
    fake_converter(monkeypatch, lambda *a: None)
    with pytest.raises(ExtractError, match="wrote no DXF"):
        oda_ezdxf.extract(dwg, with_parsing(test_cfg, odafc_path=str(exe)))


def stub(monkeypatch, module, calls, name, outcome):
    def run(path, cfg):
        calls.append(name)
        if isinstance(outcome, Exception):
            raise outcome
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["extractor"] = name
        return data

    monkeypatch.setattr(module, "extract", run)


def test_extract_prefer_order_and_fallback(tmp_path, test_cfg, monkeypatch):
    path = tmp_path / "a.dwg"
    calls = []
    for prefer, first, second in (
        ("acad_plugin", "acad_plugin", "oda_ezdxf"),
        ("oda_ezdxf", "oda_ezdxf", "acad_plugin"),
    ):
        cfg = with_parsing(test_cfg, dxf_prefer_extractor=prefer)
        mods = {"acad_plugin": acad_console, "oda_ezdxf": oda_ezdxf}
        calls.clear()
        stub(monkeypatch, mods[first], calls, first, None)
        stub(monkeypatch, mods[second], calls, second, None)
        assert extract_pkg.extract(path, cfg)["extractor"] == first
        assert calls == [first]

        calls.clear()  # a failure falls back and the warning names the one that failed
        stub(monkeypatch, mods[first], calls, first, ExtractError("timed out after 5 s"))
        data = extract_pkg.extract(path, cfg)
        assert calls == [first, second] and data["extractor"] == second
        assert (
            f"{first} failed on this drawing, so {second} was used" in data["document"]["warnings"]
        )

        calls.clear()  # a missing tool falls back with no failure warning
        stub(monkeypatch, mods[first], calls, first, Unavailable("tool missing"))
        data = extract_pkg.extract(path, cfg)
        assert calls == [first, second]
        assert not any("failed on this drawing" in w for w in data["document"]["warnings"])


def test_extract_both_unavailable_names_both(tmp_path, test_cfg, monkeypatch):
    calls = []
    stub(
        monkeypatch,
        acad_console,
        calls,
        "acad_plugin",
        Unavailable("accoreconsole_path is not set"),
    )
    stub(monkeypatch, oda_ezdxf, calls, "oda_ezdxf", Unavailable("ezdxf not installed"))
    with pytest.raises(Unavailable) as err:
        extract_pkg.extract(tmp_path / "a.dwg", test_cfg)
    assert "accoreconsole_path is not set" in str(err.value)
    assert "ezdxf not installed" in str(err.value)

    stub(monkeypatch, acad_console, calls, "acad_plugin", ExtractError("timed out after 5 s"))
    with pytest.raises(ExtractError) as err:
        extract_pkg.extract(tmp_path / "a.dwg", test_cfg)
    assert not isinstance(err.value, Unavailable)
    assert "timed out after 5 s" in str(err.value) and "ezdxf not installed" in str(err.value)


@pytest.mark.live
def test_live_oda_ezdxf_dumps_sample():
    cfg = load_config(ROOT / "config")
    sample = ROOT / "gold" / "dwg" / "etsu_entc2160_m04" / "Tiny Electrical Plan.dwg"
    try:
        data = oda_ezdxf.extract(sample, cfg)
    except Unavailable as e:
        pytest.skip(str(e))
    except ExtractError:
        if not sample.is_file():
            pytest.skip(f"ODA sample drawing not found: {sample}")
        raise
    assert data["extractor"] == "oda_ezdxf"
    assert data["entities"]


# ---- review M2 RV1-RV9 ----


def _field_db(fields):
    return SimpleNamespace(get=fields.get)


def test_field_self_reference_fanout_is_bounded():
    import time

    db = {"S": _field([(1, "_text"), (301, "")], ["S"] * 30)}
    notes = []
    start = time.monotonic()
    got = oda_ezdxf._field_text(
        _field_db(db), "S", oda_ezdxf._budget(), notes, "table 2F01 cell (0, 0)"
    )
    assert got == "" and time.monotonic() - start < 1
    # many distinct children hit the visit cap and say so
    db = {f"K{i}": _field([(1, "_text"), (301, "")], [f"K{i + 1}"]) for i in range(500)}
    seen = oda_ezdxf._budget()
    oda_ezdxf._field_text(_field_db(db), "K0", oda_ezdxf._budget(), notes, "table 2F01 cell (0, 0)")
    assert seen["n"] <= 64
    assert any("2F01" in n and "(0, 0)" in n for n in notes)


def test_field_multi_child_fills_parent_code():
    db = {
        "P": _field([(1, "_text"), (2, r"%<\_FldIdx 0>%/%<\_FldIdx 1>%"), (301, "")], ["A", "B"]),
        "A": _field([(1, "AcVar"), (301, "120")]),
        "B": _field([(1, "AcVar"), (301, "208")]),
        "Q": _field([(1, "_text"), (2, r"LP-%<\_FldIdx 0>%"), (301, "")], ["C"]),
        "C": _field([(1, "AcVar"), (301, "12")]),
    }
    d = _field_db(db)
    assert oda_ezdxf._field_text(d, "P", oda_ezdxf._budget(), [], "w") == "120/208"
    assert oda_ezdxf._field_text(d, "Q", oda_ezdxf._budget(), [], "w") == "LP-12"


def test_field_missing_child_is_not_joined():
    db = {
        "P": _field([(1, "_text"), (2, r"%<\_FldIdx 0>%/%<\_FldIdx 1>%"), (301, "")], ["A"]),
        "A": _field([(1, "AcVar"), (301, "120")]),
    }
    notes = []
    assert (
        oda_ezdxf._field_text(_field_db(db), "P", oda_ezdxf._budget(), notes, "table T cell (1, 1)")
        == ""
    )
    assert any("T cell (1, 1)" in n for n in notes)


def test_field_empty_result_keeps_cell_text():
    db = {"A": _field([(1, "_text"), (301, "")])}
    pairs = [(171, 1), (344, "A"), (1, "K12"), (302, "")]
    ent = FakeEntity(1, 1)
    ent.doc = SimpleNamespace(entitydb=SimpleNamespace(get=db.get))
    tags = [SimpleNamespace(code=c, value=v) for c, v in pairs]

    class Sub(list):
        get_first_value = staticmethod(lambda code, default=None: {91: 1, 92: 1}.get(code, default))

    ent.xtags = SimpleNamespace(get_subclass=lambda name: Sub(tags))
    item = oda_ezdxf.convert(ent, "L", None, [], fake_acad_table([["from ezdxf"]]))
    assert item["table"]["cells"][0]["text"] == "from ezdxf"
    item = oda_ezdxf.convert(ent, "L", None, [], fake_acad_table([[""]]))
    assert item["table"]["cells"][0]["text"] == "K12"


def test_repeated_failed_xref_both_unresolved(tmp_path, test_cfg):
    (tmp_path / "bad.dxf").write_text("not a drawing", encoding="utf-8")
    doc = new_doc()
    doc.add_xref_def("bad.dxf", "ONE")
    doc.add_xref_def("bad.dxf", "TWO")
    data = oda_ezdxf.extract(save(doc, tmp_path / "host.dxf"), test_cfg)
    assert {x["name"]: x["resolved"] for x in data["document"]["xrefs"]} == {
        "ONE": False,
        "TWO": False,
    }
    notes = data["document"]["warnings"]
    assert any("ONE was not read" in n for n in notes) and any(
        "TWO was not read" in n for n in notes
    )


def test_failed_xref_keeps_no_partial_entities(tmp_path, test_cfg, monkeypatch):
    child = new_doc()
    for i in range(5):
        child.modelspace().add_text(f"XREF{i}")
    save(child, tmp_path / "child.dxf")
    host = new_doc()
    host.modelspace().add_text("HOST")
    host.add_xref_def("child.dxf", "CHILD")
    monkeypatch.setattr(rawdrawing, "MAX_ENTITIES", 4)
    data = oda_ezdxf.extract(save(host, tmp_path / "host.dxf"), test_cfg)
    assert [e["text"] for e in data["entities"]] == ["HOST"]
    assert data["document"]["xrefs"] == [{"name": "CHILD", "path": "child.dxf", "resolved": False}]


def _no_filesystem(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("filesystem touched")

    for name in ("resolve", "stat", "is_file", "exists", "open"):
        monkeypatch.setattr(Path, name, boom)
    monkeypatch.setattr(os.path, "realpath", boom)
    monkeypatch.setattr(os, "stat", boom)


def test_unc_xref_rejected_before_any_filesystem_call(tmp_path, test_cfg, monkeypatch):
    base = tmp_path.resolve()
    for raw in (r"\\host\share\x.dwg", "//host/share/x.dwg"):
        with monkeypatch.context() as m:
            _no_filesystem(m)
            assert oda_ezdxf._inside(raw, base, base) is None
    doc = new_doc()
    doc.add_xref_def(r"\\127.0.0.1\share\x.dwg", "UNC")
    data = oda_ezdxf.extract(save(doc, tmp_path / "host.dxf"), test_cfg)
    assert data["document"]["xrefs"][0]["resolved"] is False


def test_drive_xref_rejected_before_any_filesystem_call(tmp_path, monkeypatch):
    base = tmp_path.resolve()
    for raw in (r"C:\x\a.dwg", "C:a.dwg", "/abs/a.dwg", r"\abs\a.dwg"):
        with monkeypatch.context() as m:
            _no_filesystem(m)
            assert oda_ezdxf._inside(raw, base, base) is None


def test_declared_table_size_refused_before_read():
    import time

    def boom(e):
        raise AssertionError("content built")

    start = time.monotonic()
    with pytest.raises(ExtractError, match="MAX_TABLE_CELLS"):
        oda_ezdxf.convert(
            FakeEntity(10_000_000, 1),
            "L",
            None,
            [],
            SimpleNamespace(read_acad_table_content=boom),
        )
    assert time.monotonic() - start < 1


def test_dxf_over_size_cap_refused(tmp_path, test_cfg, monkeypatch):
    path = save(new_doc(), tmp_path / "a.dxf")
    monkeypatch.setattr(rawdrawing, "MAX_JSON_BYTES", 10)

    def boom(*a, **k):
        raise AssertionError("file read")

    monkeypatch.setattr(recover, "readfile", boom)
    with pytest.raises(ExtractError, match="MAX_JSON_BYTES"):
        oda_ezdxf.extract(path, test_cfg)


def test_ezdxf_unexpected_error_becomes_extract_error(tmp_path, test_cfg, monkeypatch):
    doc = new_doc()
    doc.modelspace().add_text("a")

    def odd(*a, **k):
        raise AttributeError("odd entity")

    monkeypatch.setattr(oda_ezdxf, "convert", odd)
    with pytest.raises(ExtractError, match="AttributeError"):
        oda_ezdxf.extract(save(doc, tmp_path / "a.dxf"), test_cfg)


def test_long_layer_and_block_names_are_cut(tmp_path, test_cfg):
    long = "L" * 20000
    doc = new_doc()
    doc.layers.add(long)
    doc.modelspace().add_text("a", dxfattribs={"layer": long})
    doc.blocks.new("B" * 20000).add_text("in block")
    data = oda_ezdxf.extract(save(doc, tmp_path / "a.dxf"), test_cfg)
    assert all(len(e["layer"]) <= rawdrawing.MAX_TEXT for e in data["entities"])
    assert all(len(e["layout"]) <= rawdrawing.MAX_TEXT for e in data["entities"])
    assert any(e["layout"].startswith("block:BBB") for e in data["entities"])
    assert rawdrawing.validate(data).ok


def test_field_same_child_twice_reads_both():
    code = r"%<\_FldIdx 0>%/%<\_FldIdx 1>%"
    db = {
        "P": _field([(1, "_text"), (2, code), (301, "")], ["A", "A"]),
        "A": _field([(1, "AcVar"), (301, "120")]),
    }
    assert oda_ezdxf._field_text(_field_db(db), "P", oda_ezdxf._budget(), [], "w") == "120/120"


def test_field_children_without_code_not_joined():
    db = {
        "P": _field([(1, "_text"), (301, "")], ["A", "B"]),
        "Q": _field([(1, "_text"), (301, "")], ["A"]),
        "A": _field([(1, "AcVar"), (301, "120")]),
        "B": _field([(1, "AcVar"), (301, "208")]),
    }
    notes = []
    assert (
        oda_ezdxf._field_text(_field_db(db), "P", oda_ezdxf._budget(), notes, "table T cell (0, 0)")
        == ""
    )
    assert any("T cell (0, 0)" in n for n in notes)
    assert oda_ezdxf._field_text(_field_db(db), "Q", oda_ezdxf._budget(), [], "w") == "120"


def test_nested_xref_rolled_back_is_unresolved(tmp_path, test_cfg, monkeypatch):
    inner = new_doc()
    inner.modelspace().add_text("INNER")
    save(inner, tmp_path / "inner.dxf")
    outer = new_doc()
    outer.add_xref_def("inner.dxf", "INNER")
    big = outer.blocks.new("BIG")  # walked after the inner xref is read
    for i in range(5):
        big.add_text(f"OUT{i}")
    save(outer, tmp_path / "outer.dxf")
    host = new_doc()
    host.modelspace().add_text("HOST")
    host.add_xref_def("outer.dxf", "OUTER")
    monkeypatch.setattr(rawdrawing, "MAX_ENTITIES", 4)
    data = oda_ezdxf.extract(save(host, tmp_path / "host.dxf"), test_cfg)
    assert [e["text"] for e in data["entities"]] == ["HOST"]
    got = {x["name"]: x["resolved"] for x in data["document"]["xrefs"]}
    assert got == {"INNER": False, "OUTER": False}
    assert any("INNER was not read" in n for n in data["document"]["warnings"])


def _table_with_tags(db, pairs, rows=1, cols=1):
    ent = FakeEntity(rows, cols)
    ent.doc = SimpleNamespace(entitydb=SimpleNamespace(get=db.get))
    tags = [SimpleNamespace(code=c, value=v) for c, v in pairs]

    class Sub(list):
        get_first_value = staticmethod(
            lambda code, default=None: {91: rows, 92: cols}.get(code, default)
        )

    ent.xtags = SimpleNamespace(get_subclass=lambda name: Sub(tags))
    return ent


def test_field_budget_is_per_table():
    import time

    db = {"P": _field([(1, "_text"), (301, "")], [f"K{i}" for i in range(2000)])}
    db.update({f"K{i}": _field([(1, "AcVar"), (301, "1")]) for i in range(2000)})
    ent = _table_with_tags(db, [(171, 1), (344, "P")] * 6400)
    notes = []
    start = time.monotonic()
    item = oda_ezdxf.convert(ent, "L", None, notes, fake_acad_table([[""]]))
    assert time.monotonic() - start < 1
    assert item["table"]["cells"][0]["text"] == ""
    assert len(notes) < 10


def test_field_cut_child_gives_no_partial_text():
    code = r"%<\_FldIdx 0>%/%<\_FldIdx 1>%"
    db = {
        "P": _field([(1, "_text"), (2, code), (301, "")], ["A", "S"]),
        "A": _field([(1, "AcVar"), (301, "120")]),
        "S": _field([(1, "_text"), (301, "")], ["S"]),
    }
    notes = []
    got = oda_ezdxf._field_text(_field_db(db), "P", oda_ezdxf._budget(), notes, "w")
    assert got == ""
    ent = _table_with_tags(db, [(171, 1), (344, "P"), (1, "K12")])
    item = oda_ezdxf.convert(ent, "L", None, notes, fake_acad_table([["K12"]]))
    assert item["table"]["cells"][0]["text"] == ""
    assert any("cell (0, 0)" in n for n in notes)


def test_long_xref_name_and_path_are_cut(tmp_path, test_cfg):
    doc = new_doc()
    doc.add_xref_def("p" * 20000 + ".dxf", "N" * 20000)
    data = oda_ezdxf.extract(save(doc, tmp_path / "host.dxf"), test_cfg)
    x = data["document"]["xrefs"][0]
    assert len(x["name"]) <= rawdrawing.MAX_TEXT and len(x["path"]) <= rawdrawing.MAX_TEXT
    assert x["resolved"] is False
    assert rawdrawing.validate(data).ok


def test_field_read_once_per_drawing():
    import time

    f = _field([(2, "x")] * 20000)
    f.xtags.subclasses[0].append(SimpleNamespace(code=1, value="_text"))
    reads = []
    real = f.xtags.subclasses[0]

    class Counted(list):
        def __iter__(self):
            reads.append(1)
            return super().__iter__()

    f.xtags.subclasses[0] = Counted(real)
    ctx = {}
    notes = []
    start = time.monotonic()
    entitydb = SimpleNamespace(get={"F": f}.get)  # one per drawing
    for i in range(100):
        ent = _table_with_tags({"F": f}, [(171, 1), (344, "F")] * 64, rows=64, cols=1)
        ent.doc = SimpleNamespace(entitydb=entitydb)
        oda_ezdxf.convert(ent, "L", None, notes, fake_acad_table([[""]] * 64), ctx)
    assert time.monotonic() - start < 2
    assert len(reads) == 1


def test_declared_cells_capped_per_drawing_extract(tmp_path, test_cfg, monkeypatch):
    import time

    from ezdxf.entities import acad_table

    doc = new_doc()
    for i in range(300):
        doc.modelspace().add_text(f"T{i}")
    path = save(doc, tmp_path / "a.dxf")
    real = oda_ezdxf.convert
    read = []

    def as_table(e, layout, xref, notes, acad, ctx=None):
        ent = FakeEntity(100_000, 1)
        ent.dxf = SimpleNamespace(
            get=lambda k, d=None: {"handle": e.dxf.handle, "layer": "L"}.get(k, d)
        )
        return real(ent, layout, xref, notes, acad, ctx)

    monkeypatch.setattr(oda_ezdxf, "convert", as_table)
    monkeypatch.setattr(
        acad_table, "read_acad_table_content", lambda e: read.append(1) or [["a"], ["b"]]
    )
    start = time.monotonic()
    data = oda_ezdxf.extract(path, test_cfg)
    assert time.monotonic() - start < 3
    fits = rawdrawing.MAX_DRAWING_CELLS // 100_000
    assert len(read) == fits == len(data["entities"])
    warnings = data["document"]["warnings"]
    assert sum("MAX_DRAWING_CELLS" in w for w in warnings) == 300 - fits


def test_cut_field_cached_with_outcome():
    import time

    f = _field([(2, "x")] * 50000 + [(1, "_text")], ["F"])
    entitydb = SimpleNamespace(get={"F": f}.get)
    ctx = {}
    start = time.monotonic()
    for i in range(300):
        notes = []
        ent = _table_with_tags({}, [(171, 1), (344, "F"), (1, "K12")] * 64, rows=64, cols=1)
        ent.doc = SimpleNamespace(entitydb=entitydb)
        item = oda_ezdxf.convert(ent, "L", None, notes, fake_acad_table([["K12"]] * 64), ctx)
        assert {c["text"] for c in item["table"]["cells"]} == {""}
        assert any("cut short" in n for n in notes)
    assert time.monotonic() - start < 2


def test_negative_or_half_zero_table_size_not_read():
    import time

    def boom(e):
        raise AssertionError("content built")

    for rows, cols in ((10_000_000, -1), (-1, 5), (0, 5), (5, 0)):
        notes = []
        start = time.monotonic()
        item = oda_ezdxf.convert(
            FakeEntity(rows, cols),
            "L",
            None,
            notes,
            SimpleNamespace(read_acad_table_content=boom),
        )
        assert item is None and time.monotonic() - start < 1
        assert any("was not read" in n for n in notes)
