import copy
import json
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
