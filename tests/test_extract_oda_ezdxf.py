import copy
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
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


def test_insert_point_is_wcs(tmp_path, test_cfg):
    doc = new_doc()
    doc.blocks.new("PNL")
    msp = doc.modelspace()
    msp.add_blockref("PNL", (6000, 0), dxfattribs={"extrusion": (0, 0, -1)})
    msp.add_blockref("PNL", (7, 8))
    data = oda_ezdxf.extract(save(doc, tmp_path / "w.dxf"), test_cfg)
    pts = [e["insertion_point"] for e in data["entities"] if e["type"] == "INSERT"]
    assert [p[:2] for p in pts] == [[-6000.0, 0.0], [7.0, 8.0]]


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
    data = oda_ezdxf.extract_inprocess(path, test_cfg)
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
    data = oda_ezdxf.extract_inprocess(dwg, cfg)
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
        oda_ezdxf.extract_inprocess(dwg, cfg)
    assert st.killed
    assert list(root.iterdir()) == []


def test_oda_converter_without_output_gives_extract_error(tmp_path, test_cfg, monkeypatch):
    exe = tmp_path / "ODAFileConverter.exe"
    exe.write_bytes(b"x")
    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"x")
    fake_converter(monkeypatch, lambda *a: None)
    with pytest.raises(ExtractError, match="wrote no DXF"):
        oda_ezdxf.extract_inprocess(dwg, with_parsing(test_cfg, odafc_path=str(exe)))


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


def _with_field(e):
    e.new_extension_dict().add_dictionary("ACAD_FIELD")
    return e


def _by_handle(data):
    return {e["handle"]: e for e in data["entities"]}


def test_oda_text_field_not_evaluated(tmp_path, test_cfg):
    doc = new_doc()
    msp = doc.modelspace()
    t = _with_field(msp.add_text("FIELD TEXT", dxfattribs={"insert": (0, 0)}))
    m = _with_field(msp.add_mtext("FIELD MTEXT", dxfattribs={"insert": (0, 5)}))
    data = oda_ezdxf.extract(save(doc, tmp_path / "f.dxf"), test_cfg)
    ents = _by_handle(data)
    assert ents[t.dxf.handle]["evaluated"] is False
    assert ents[m.dxf.handle]["evaluated"] is False
    assert rawdrawing.validate(data).ok


def test_oda_attribute_field_not_evaluated(tmp_path, test_cfg):
    doc = new_doc()
    doc.blocks.new("PNL").add_attdef("NAME", (0, 0))
    doc.blocks.get("PNL").add_attdef("PLAIN", (0, 1))
    ref = (
        doc.modelspace()
        .add_blockref("PNL", (3, 3))
        .add_auto_attribs({"NAME": "LP-1", "PLAIN": "x"})
    )
    _with_field(next(a for a in ref.attribs if a.dxf.tag == "NAME"))
    data = oda_ezdxf.extract(save(doc, tmp_path / "a.dxf"), test_cfg)
    (insert,) = [e for e in data["entities"] if e["type"] == "INSERT"]
    got = {a["tag"]: a.get("evaluated") for a in insert["attributes"]}
    assert got == {"NAME": False, "PLAIN": None}
    assert rawdrawing.validate(data).ok


def test_oda_text_without_field_has_no_flag(tmp_path, test_cfg):
    doc = new_doc()
    msp = doc.modelspace()
    msp.add_text("PLAIN", dxfattribs={"insert": (0, 0)})
    msp.add_mtext("PLAIN TOO", dxfattribs={"insert": (0, 5)})
    # An extension dictionary without ACAD_FIELD is not a field.
    other = msp.add_text("DICT ONLY", dxfattribs={"insert": (0, 9)})
    other.new_extension_dict().add_dictionary("ACAD_OTHER")
    data = oda_ezdxf.extract(save(doc, tmp_path / "p.dxf"), test_cfg)
    texts = [e for e in data["entities"] if e["type"] in ("TEXT", "MTEXT")]
    assert len(texts) == 3 and all("evaluated" not in e for e in texts)


def _dynamic_doc(*, point_at_source=True):
    doc = new_doc()
    doc.blocks.new("DOOR")
    doc.appids.add("AcDbBlockRepBTag")
    anon = doc.blocks.new("*U1")
    if point_at_source:
        src = doc.block_records.get("DOOR")
        anon.block_record.set_xdata("AcDbBlockRepBTag", [(1005, src.dxf.handle)])
    doc.modelspace().add_blockref("*U1", (0, 0))
    return doc


def test_oda_dynamic_block_source_name(tmp_path, test_cfg):
    data = oda_ezdxf.extract(save(_dynamic_doc(), tmp_path / "d.dxf"), test_cfg)
    (insert,) = [e for e in data["entities"] if e["type"] == "INSERT"]
    assert insert["block_name"] == "DOOR"


def test_oda_unresolved_dynamic_keeps_u_name(tmp_path, test_cfg):
    data = oda_ezdxf.extract(
        save(_dynamic_doc(point_at_source=False), tmp_path / "u.dxf"), test_cfg
    )
    (insert,) = [e for e in data["entities"] if e["type"] == "INSERT"]
    assert insert["block_name"] == "*U1"


def _flags(data):
    """Text and attribute flags of the host layouts, matched by content: the fixtures use
    synthetic handles. Table render blocks (block:*) are left out."""
    out = Counter()
    for e in data["entities"]:
        if e["layout"].startswith("block:"):
            continue
        if e["type"] in ("TEXT", "MTEXT"):
            out[(e["type"], e["text"], e.get("evaluated"))] += 1
        for a in e.get("attributes") or []:
            out[(e["block_name"], a["tag"], a["value"], a.get("evaluated"))] += 1
    return out


@pytest.mark.live
def test_live_oda_ezdxf_text_flags():
    cfg = load_config(ROOT / "config")
    sample = ROOT / "samples" / "dwg" / "panel_sheet.dwg"
    try:
        data = oda_ezdxf.extract(sample, cfg)
    except Unavailable as e:
        pytest.skip(str(e))
    assert data["schema_version"] == "1.1"
    want = json.loads(FIXTURE.with_name("panel_sheet.oda_ezdxf.rawdrawing.json").read_text("utf-8"))
    assert _flags(data) == _flags(want)
    # The LP-12 FIELD cells leave their render text in table blocks, flagged not evaluated.
    assert any(e.get("evaluated") is False for e in data["entities"])


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


# ---- review fixes ----


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
        oda_ezdxf.extract_inprocess(path, test_cfg)


def test_ezdxf_unexpected_error_becomes_extract_error(tmp_path, test_cfg, monkeypatch):
    doc = new_doc()
    doc.modelspace().add_text("a")

    def odd(*a, **k):
        raise AttributeError("odd entity")

    monkeypatch.setattr(oda_ezdxf, "convert", odd)
    with pytest.raises(ExtractError, match="AttributeError"):
        oda_ezdxf.extract_inprocess(save(doc, tmp_path / "a.dxf"), test_cfg)


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
    data = oda_ezdxf.extract_inprocess(path, test_cfg)
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


def test_fallback_read_times_out_in_child(tmp_path, test_cfg):
    import time

    levels = 23
    doc = new_doc()
    for i in range(levels, -1, -1):
        for a in "XY":
            b = doc.blocks.new(f"{a}{i}")
            if i < levels:
                b.add_blockref(f"X{i + 1}", (0, 0))
                b.add_blockref(f"Y{i + 1}", (0, 0))
            else:
                b.add_text("leaf")
    doc.modelspace().add_blockref("X0", (0, 0))
    path = save(doc, tmp_path / "dag.dxf")
    start = time.monotonic()
    with pytest.raises(ExtractError, match="timed out"):
        oda_ezdxf.extract(path, with_parsing(test_cfg, dxf_extractor_timeout_s=2))
    assert time.monotonic() - start < 10


def test_child_wiring_uses_this_package_and_passes_caps(tmp_path, test_cfg, monkeypatch):
    monkeypatch.setattr(rawdrawing, "MAX_TEXT", 40)
    doc = new_doc()
    doc.modelspace().add_text("0123456789" * 5)
    data = oda_ezdxf.extract(save(doc, tmp_path / "a.dxf"), test_cfg)
    assert data["entities"][0]["text"] == "0123456789" * 4  # the child saw the parent's cap
    with pytest.raises(ExtractError, match="MAX_ENTITIES"):
        monkeypatch.setattr(rawdrawing, "MAX_ENTITIES", 0)
        oda_ezdxf.extract(tmp_path / "a.dxf", test_cfg)


def test_field_expansion_capped_before_substitution():
    import time
    import tracemalloc

    code = r"%<\_FldIdx 0>%" * 2
    db = {"F1": _field([(1, "AcVar"), (301, "x")])}
    for i in range(2, 31):
        db[f"F{i}"] = _field([(1, "AcVar"), (2, code)], [f"F{i - 1}"])
    ent = _table_with_tags(db, [(171, 1), (344, "F30"), (1, "K12")])
    notes = []
    tracemalloc.start()
    start = time.monotonic()
    item = oda_ezdxf.convert(ent, "L", None, notes, fake_acad_table([[""]]))
    took = time.monotonic() - start
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert took < 1 and peak < 100 * 2**20
    assert item["table"]["cells"][0]["text"] == ""
    assert any("cell (0, 0)" in n for n in notes)


def test_mtext_strip_is_linear():
    import time

    text = ("\\A1;") * 50000
    ent = SimpleNamespace(
        dxftype=lambda: "MTEXT",
        text=text,
        plain_text=lambda: (_ for _ in ()).throw(AssertionError("ezdxf strip used")),
        dxf=SimpleNamespace(get=lambda k, d=None: {"handle": "A1", "layer": "0"}.get(k, d)),
    )
    start = time.monotonic()
    item = oda_ezdxf.convert(ent, "L", None, [], fake_acad_table([]))
    assert time.monotonic() - start < 1
    assert item["text"] == ""


def test_relative_path_reads_like_absolute(tmp_path, test_cfg, monkeypatch):
    child = new_doc()
    child.modelspace().add_text("from child")
    save(child, tmp_path / "child.dxf")
    host = new_doc()
    host.modelspace().add_text("host")
    host.add_xref_def("child.dxf", "CHILD")
    save(host, tmp_path / "host.dxf")
    monkeypatch.chdir(tmp_path)
    rel = oda_ezdxf.extract(Path("host.dxf"), test_cfg)
    ab = oda_ezdxf.extract(tmp_path / "host.dxf", test_cfg)
    assert rel["document"]["xrefs"] == [{"name": "CHILD", "path": "child.dxf", "resolved": True}]
    rel.pop("extracted_at")
    ab.pop("extracted_at")
    assert rel == ab


def test_field_table_over_64_fields_reads_every_cell():
    db = {}
    pairs = []
    for i in range(84):
        db[f"F{i}"] = _field([(1, "_text"), (301, "")], [f"K{i}"])
        db[f"K{i}"] = _field([(1, "AcVar"), (301, f"v{i}")])
        pairs += [(171, 1), (344, f"F{i}")]
    ent = _table_with_tags(db, pairs, rows=42, cols=2)
    notes = []
    item = oda_ezdxf.convert(ent, "L", None, notes, fake_acad_table([["", ""]] * 42))
    assert [c["text"] for c in item["table"]["cells"]] == [f"v{i}" for i in range(84)]
    assert not notes


def test_child_output_total_capped(monkeypatch):
    monkeypatch.setattr(rawdrawing, "MAX_JSON_BYTES", 1000)
    rows = [["x" * 200] * 4] * 5
    ent = FakeEntity(5, 4)
    ctx = {}
    with pytest.raises(ExtractError, match="MAX_JSON_BYTES"):
        oda_ezdxf.convert(ent, "L", None, [], fake_acad_table(rows), ctx)
    text = SimpleNamespace(
        dxftype=lambda: "TEXT",
        dxf=SimpleNamespace(get=lambda k, d=None: {"handle": "A", "text": "y" * 600}.get(k, d)),
    )
    ctx = {}
    oda_ezdxf.convert(text, "L", None, [], fake_acad_table([]), ctx)
    with pytest.raises(ExtractError, match="MAX_JSON_BYTES"):
        oda_ezdxf.convert(text, "L", None, [], fake_acad_table([]), ctx)


def test_budget_exhausted_handle_not_cached_as_cut():
    idx = lambda i: r"%<\_FldIdx " + str(i) + ">%"
    db = {}
    for i in range(70):
        db[f"L{i}"] = _field([(1, "AcVar"), (301, "x")])
    db["M"] = _field([(1, "_text"), (2, idx(0) + idx(1) + idx(2)), (301, "")], ["A", "B", "C"])
    for h in "ABC":
        db[h] = _field([(1, "AcVar"), (301, h)])
    db["R"] = _field(
        [(1, "_text"), (2, "".join(idx(i) for i in range(63))), (301, "")],
        [f"L{i}" for i in range(62)] + ["M"],
    )
    ent = _table_with_tags(db, [(171, 1), (344, "R"), (171, 1), (344, "M")], rows=2, cols=1)
    item = oda_ezdxf.convert(ent, "L", None, [], fake_acad_table([[""], [""]]))
    assert [c["text"] for c in item["table"]["cells"]] == ["", "ABC"]


def test_field_own_text_cut_before_strip(monkeypatch):
    monkeypatch.setattr(rawdrawing, "MAX_TEXT", 100)
    db = {"F": _field([(1, "AcVar"), (301, "^I" * 500)])}
    notes = []
    got = oda_ezdxf._field_text(_field_db(db), "F", oda_ezdxf._budget(), notes, "w")
    assert len(got) == 100
    assert any("MAX_TEXT" in n for n in notes)


def test_oda_entity_at_origin_keeps_its_point(tmp_path, test_cfg):
    doc = new_doc()
    doc.blocks.new("DOOR")
    msp = doc.modelspace()
    msp.add_blockref("DOOR", (0, 0))
    msp.add_text("T", height=1, dxfattribs={"insert": (0, 0)})
    msp.add_line((0, 0), (3, 4))
    data = oda_ezdxf.extract(save(doc, tmp_path / "origin.dxf"), test_cfg)
    by_type = {e["type"]: e for e in data["entities"]}
    for kind in ("INSERT", "TEXT", "LINE"):
        assert by_type[kind]["insertion_point"][:2] == [0.0, 0.0], kind
    assert by_type["LINE"]["bbox"] == [0.0, 0.0, 3.0, 4.0]
