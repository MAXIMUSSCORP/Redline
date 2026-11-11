"""exits.csv and paths.csv: the owner's exit list and egress paths (D5, D8)."""

import csv
import io
import json
from collections import Counter
from pathlib import Path

from redline import cli
from redline.model import Confidence, Device, Method, Project, Source, Value
from redline.parsers import exits
from redline.parsers.tabular import Parsed

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "samples" / "plans"
SHEET = "sheet_fa101.dxf"
HEAD = "sheet,x,y,label"


def units_value(word="mm") -> Value:
    src = Source(SHEET, "document.units", Method.DXF_BLOCK, Confidence.MEDIUM)
    return Value(word, src, raw=word)


def block(sheet=SHEET, detection="block", kind="exit_door") -> Device:
    src = Source(sheet, "layout=Model", Method.DXF_BLOCK, Confidence.HIGH)
    return Device(kind, src, sheet=Value(sheet, src), detection=detection)


def project(*sheets, devices=()) -> Project:
    p = Project(name="t")
    for s in sheets or (SHEET,):
        p.sheet_units[s] = units_value()
    p.devices += devices
    return p


def write(tmp_path, name, text) -> Path:
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return f


def run(tmp_path, cfg, text, name="exits.csv", proj=None) -> Project:
    proj = proj or project()
    exits.apply([write(tmp_path, name, text)], proj, cfg)
    return proj


def listed(proj, kind="row") -> list:
    return [u for u in proj.unparsed if u.kind == kind]


def rows(*lines) -> str:
    return "\n".join(lines) + "\n"


# ---- exits.csv ----


def test_exits_csv_wins_over_detection(tmp_path, test_cfg):
    other = "b.dxf"
    p = project(SHEET, other, devices=[block(), block(), block(), block(other)])
    run(tmp_path, test_cfg, rows(HEAD, f"{SHEET},0,0,E1", f"{SHEET},500,0,E2"), proj=p)
    got = Counter((d.sheet.value, d.detection) for d in p.devices)
    assert got == {(SHEET, "unused"): 3, (other, "block"): 1, (SHEET, "list"): 2}
    exit_rows = [d for d in p.devices if d.detection == "list"]
    assert [d.tag.value for d in exit_rows] == ["E1", "E2"]
    assert all(d.source.confidence == Confidence.HIGH for d in exit_rows)
    assert any("3 exit_door blocks not used" in c.what_read for c in p.coverage)


def test_sheet_without_rows_keeps_its_blocks(tmp_path, test_cfg):
    p = project(SHEET, "b.dxf", devices=[block("b.dxf")])
    run(tmp_path, test_cfg, rows(HEAD, f"{SHEET},0,0,E1"), proj=p)
    assert [d.detection for d in p.devices if d.sheet.value == "b.dxf"] == ["block"]


def test_bad_number_row_listed_and_low(tmp_path, test_cfg):
    p = run(
        tmp_path, test_cfg, rows(HEAD, f"{SHEET},abc,0,E1", f"{SHEET},nan,1,E2", f"{SHEET},1,2,E3")
    )
    bad = [d for d in p.devices if d.tag.value in ("E1", "E2")]
    assert len(bad) == 2 and all(not d.x.usable or not d.y.usable for d in bad)
    assert bad[0].x.confidence == Confidence.LOW and bad[0].x.raw == "abc"
    assert len(listed(p)) == 2
    good = next(d for d in p.devices if d.tag.value == "E3")
    assert good.x.usable and good.y.usable


def test_unknown_sheet_row_listed(tmp_path, test_cfg):
    p = run(tmp_path, test_cfg, rows(HEAD, "nope.dxf,0,0,E1", "SHEET_FA101.DXF,0,0,E2"))
    (u,) = listed(p)
    assert "names no DWG or DXF sheet that was read" in u.reason
    (d,) = p.devices
    assert d.tag.value == "E2" and d.sheet.value == SHEET  # canonical spelling kept


def test_unknown_unit_word_listed(tmp_path, test_cfg):
    p = run(tmp_path, test_cfg, rows(HEAD + ",units", f"{SHEET},0,0,E1,furlongs"))
    v = p.sheet_units[SHEET]
    assert v.value is None and v.confidence == Confidence.LOW and not v.usable
    assert "unknown or disagree" in v.source.note
    assert len(listed(p)) == 1


def test_rows_disagree_on_units(tmp_path, test_cfg):
    text = rows(HEAD + ",units", f"{SHEET},0,0,E1,mm", f"{SHEET},1,0,E2,m", f"{SHEET},2,0,E3,")
    p = run(tmp_path, test_cfg, text)
    assert not p.sheet_units[SHEET].usable
    assert len(listed(p)) == 3
    assert len([d for d in p.devices if d.detection == "list"]) == 3  # exits are still kept


def test_extra_column_listed(tmp_path, test_cfg):
    p = run(tmp_path, test_cfg, rows(HEAD + ",colour", f"{SHEET},0,0,E1,red"))
    (u,) = listed(p, "column")
    assert "colour" in u.raw and "not read" in u.reason
    assert len(p.devices) == 1


def test_missing_column_file_listed(tmp_path, test_cfg):
    p = run(tmp_path, test_cfg, rows("sheet,x,label", f"{SHEET},0,E1"))
    (u,) = listed(p, "table")
    assert "missing column y" in u.reason
    assert p.devices == []


def test_owner_units_win_and_drawing_named(tmp_path, test_cfg):
    p = run(tmp_path, test_cfg, rows(HEAD + ",units", f"{SHEET},0,0,E1,M", f"{SHEET},1,0,E2,m"))
    v = p.sheet_units[SHEET]
    assert (v.value, v.confidence, v.source.method) == ("m", Confidence.HIGH, Method.CSV)
    assert "the drawing states mm" in v.source.note
    q = run(tmp_path, test_cfg, rows(HEAD + ",units", f"{SHEET},0,0,E1,mm"))
    assert "the drawing states the same" in q.sheet_units[SHEET].source.note
    r = run(tmp_path, test_cfg, rows(HEAD + ",units", f"{SHEET},0,0,E1,"))
    assert r.sheet_units[SHEET].value == "mm" and r.sheet_units[SHEET].raw == "mm"


def test_blank_label_is_named_by_row(tmp_path, test_cfg):
    p = run(tmp_path, test_cfg, rows(HEAD, f"{SHEET},0,0,"))
    assert p.devices[0].tag.value == "row 2"


# ---- paths.csv ----

PHEAD = "sheet,path,seq,x,y"


def test_path_rows_in_seq_order(tmp_path, test_cfg):
    text = rows(PHEAD, f"{SHEET},P1,3,30,0", f"{SHEET},P1,1,0,0", f"{SHEET},P1,2,10,0")
    p = run(tmp_path, test_cfg, text, "paths.csv")
    (path,) = p.paths
    assert path.points == [(0, 0), (10, 0), (30, 0)] and path.sheet == SHEET
    assert path.source.confidence == Confidence.HIGH and listed(p) == []


def test_bad_path_row_makes_path_low(tmp_path, test_cfg):
    for bad in (f"{SHEET},P1,2,x,0", f"{SHEET},P1,two,5,0", f"{SHEET},P1,1,5,0"):
        p = run(
            tmp_path,
            test_cfg,
            rows(PHEAD, f"{SHEET},P1,1,0,0", bad, f"{SHEET},P1,3,9,0"),
            "paths.csv",
        )
        (path,) = p.paths
        assert path.source.confidence == Confidence.LOW and path.source.note
        assert len(listed(p)) == 1
    p = run(tmp_path, test_cfg, rows(PHEAD, f"{SHEET},P2,1,0,0"), "paths.csv")
    assert p.paths[0].source.confidence == Confidence.LOW
    assert "fewer than two" in p.paths[0].source.note


def test_path_unknown_sheet_listed(tmp_path, test_cfg):
    p = run(tmp_path, test_cfg, rows(PHEAD, "z.dxf,P1,1,0,0"), "paths.csv")
    assert p.paths == [] and len(listed(p)) == 1


# ---- routing through the CLI ----


def test_exits_csv_not_read_as_schedule(tmp_path, test_cfg):
    write(tmp_path, "exits.csv", rows(HEAD, f"{SHEET},0,0,E1"))
    proj, read, tried, _ = cli._load_inputs([str(tmp_path)], test_cfg)
    assert read == 1 and proj.panels == [] and [f.name for f in tried] == ["exits.csv"]
    assert [u.kind for u in proj.unparsed] == ["row"]  # no sheet was read; nothing else


def test_folder_merges_devices_and_units(test_cfg):
    proj, read, _, _ = cli._load_inputs([str(PLANS)], test_cfg)
    assert read == 4
    assert set(proj.sheet_units) == {"sheet_fa101.dxf", "sheet_fa102.dxf"}
    assert proj.sheet_units["sheet_fa101.dxf"].usable
    assert not proj.sheet_units["sheet_fa102.dxf"].usable
    fa101 = Counter((d.type, d.detection) for d in proj.devices if d.sheet.value == SHEET)
    assert fa101[("exit_door", "list")] == 3 and fa101[("exit_door", "unused")] == 3
    assert fa101[("exit_door", "block")] == 0
    fa102 = Counter(
        (d.type, d.detection) for d in proj.devices if d.sheet.value == "sheet_fa102.dxf"
    )
    assert fa102[("exit_door", "block")] == 2
    (path,) = proj.paths
    assert (path.name, path.sheet, path.source.confidence) == ("P1", SHEET, Confidence.HIGH)
    assert path.points == [(0, 0), (40000, 0)]
    assert not [u for u in proj.unparsed if u.kind in ("row", "table")]


def test_repeated_sheet_units_not_usable():
    proj = Project(name="t")
    part = Parsed(sheet_units={SHEET: units_value()})
    cli._merge_units(proj, part)
    assert proj.sheet_units[SHEET].usable
    cli._merge_units(proj, Parsed(sheet_units={SHEET.upper(): units_value()}))
    v = proj.sheet_units[SHEET]
    assert v.value is None and v.confidence == Confidence.LOW and not v.usable
    assert "more than once" in v.source.note
    (u,) = proj.unparsed
    assert u.kind == "sheet"


# ---- end to end: a list or path file that is not fully used ----


def _drawing(name, inserts, units="mm") -> dict:
    ents = [
        {
            "id": f"e{i}",
            "type": "INSERT",
            "layout": "Model",
            "handle": f"{i:X}",
            "block_name": blk,
            "insertion_point": [x, y],
        }
        for i, (blk, x, y) in enumerate(inserts)
    ]
    return {
        "schema_version": "1.1",
        "extractor": "oda_ezdxf",
        "extractor_version": "0.1.0",
        "host_version": "synthetic",
        "source_file": name,
        "source_sha256": "0" * 64,
        "extracted_at": "2026-11-11T00:00:00Z",
        "document": {"units": units, "layouts": ["Model"], "xrefs": [], "warnings": []},
        "entities": ents,
    }


DOORS = [("TEST_DOOR", 0, 0), ("TEST_EXIT", 500, 0), ("TEST_PULL", 500, 0)]


def _check(tmp_path, files, name="in", inserts=DOORS) -> list[dict]:
    folder = tmp_path / name
    folder.mkdir()
    (folder / "sheet.rawdrawing.json").write_text(json.dumps(_drawing("fa.dxf", inserts)))
    for fname, text in files.items():
        (folder / fname).write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
    out = tmp_path / f"{name}_out" / "report.html"
    out.parent.mkdir()
    argv = ["check", str(folder), "--config", "tests/test_config/", "--out", str(out)]
    assert cli.main(argv) == 0
    text = (out.parent / "findings.csv").read_text(encoding="utf-8")
    return [r for r in csv.DictReader(io.StringIO(text)) if r["rule_id"] == "fire_alarm"]


def _exit_rows(rows) -> list[dict]:
    return [r for r in rows if "exit" in r["message"].casefold()]


EXIT_OK = "sheet,x,y,label\nfa.dxf,0,0,E1\nfa.dxf,40000,0,E2\n"


def test_unusable_exits_csv_lowers_door_blocks(tmp_path):
    bad = {
        "header": "sheet name,x,y,label\nfa.dxf,0,0,E1\nfa.dxf,40000,0,E2\n",
        "byte": EXIT_OK.encode() + b"fa.dxf,1,1,caf\x81\n",
        "field": EXIT_OK + "fa.dxf,1,1," + "A" * 140000 + "\n",
    }
    for tag, text in bad.items():
        rows = _check(tmp_path, {"exits.csv": text}, tag)
        got = _exit_rows(rows)
        assert got, tag
        assert not [r for r in rows if r["severity"] == "VIOLATION"], tag
        assert any(r["severity"] == "NEEDS_REVIEW" for r in got), tag


def located(sheet=SHEET) -> Device:
    d = block(sheet)
    d.x = d.y = Value(1.0, d.source)
    return d


def test_dropped_exit_rows_lower_door_blocks(tmp_path, monkeypatch):
    text = "sheet,x,y,label\nfa.dfx,40000,0,E2\n"
    got = _check(tmp_path, {"exits.csv": text}, "typo")
    assert not [r for r in got if r["severity"] == "VIOLATION"]
    assert any(r["severity"] == "NEEDS_REVIEW" for r in _exit_rows(got))
    proj = project(devices=[located(), located()])
    run(tmp_path, None, rows(HEAD, "nope.dxf,0,0,E1"), proj=proj)
    assert all(not d.x.usable for d in proj.devices)
    other = project(SHEET, "b.dxf", devices=[located("b.dxf")])
    run(tmp_path, None, rows(HEAD, f"{SHEET},0,0,E1", "nope.dxf,0,0,E2"), proj=other)
    assert not other.devices[0].x.usable and other.devices[0].x.source.note
    monkeypatch.setattr(exits, "MAX_ROWS", 1)
    cut = project(SHEET, "b.dxf", devices=[located("b.dxf")])
    run(tmp_path, None, rows(HEAD, f"{SHEET},0,0,E1", f"{SHEET},1,0,E2"), proj=cut)
    assert not cut.devices[0].x.usable and cut.devices[0].x.source.note


# ---- paths.csv rows not used ----


def _paths(tmp_path, text, name, monkeypatch=None) -> list[dict]:
    files = {"exits.csv": EXIT_OK, "paths.csv": text}
    return _check(tmp_path, files, name, inserts=[])


def _p1(rows) -> list[dict]:
    return [r for r in rows if "P1" in r["message"]]


def test_path_row_with_bad_sheet_lowers_path(tmp_path):
    text = "sheet,path,seq,x,y\nfa.dxf,P1,1,0,0\nfa.dxf,P1,2,8000,0\nfa.dfx,P1,3,40000,0\n"
    got = _p1(_paths(tmp_path, text, "pbad"))
    assert got and all(r["severity"] == "NEEDS_REVIEW" for r in got)
    p = run(tmp_path, None, text.replace("fa.dfx", "z.dxf").replace("fa.dxf", SHEET), "paths.csv")
    (path,) = p.paths
    assert path.source.confidence == Confidence.LOW and "row 4" in path.source.note


def test_paths_row_cap_lowers_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(exits, "MAX_ROWS", 2)
    text = rows(PHEAD, f"{SHEET},P1,1,0,0", f"{SHEET},P1,2,10,0", f"{SHEET},P1,3,20,0")
    p = run(tmp_path, None, text, "paths.csv")
    (path,) = p.paths
    assert path.source.confidence == Confidence.LOW and "not read" in path.source.note


# ---- units on a sheet read twice ----


def test_owner_units_keep_repeated_sheet_unusable(tmp_path):
    for n in ("a", "b"):
        d = tmp_path / n
        d.mkdir()
        (d / "sheet_fa101.dxf.rawdrawing.json").write_text(
            json.dumps(_drawing("sheet_fa101.dxf", DOORS))
        )
    (tmp_path / "a" / "exits.csv").write_text(
        "sheet,x,y,label,units\nsheet_fa101.dxf,0,0,E1,mm\n", encoding="utf-8"
    )
    out = tmp_path / "o" / "report.html"
    out.parent.mkdir()
    argv = ["check", str(tmp_path / "a"), str(tmp_path / "b"), "--config", "tests/test_config/"]
    assert cli.main([*argv, "--out", str(out)]) == 0
    text = (out.parent / "findings.csv").read_text(encoding="utf-8")
    fire = [r for r in csv.DictReader(io.StringIO(text)) if r["rule_id"] == "fire_alarm"]
    assert any("units not stated" in r["message"].casefold() for r in fire)
    assert all(r["severity"] != "VIOLATION" for r in fire)


# ---- shape of the file ----


def test_row_wider_than_header_listed(tmp_path, test_cfg):
    p = run(tmp_path, test_cfg, rows(HEAD, f"{SHEET},1,000,0,E1"))
    assert any("more cells" in u.reason for u in listed(p))
    (d,) = p.devices
    assert d.x.confidence == Confidence.LOW and not d.x.usable
    q = run(
        tmp_path,
        test_cfg,
        rows(PHEAD, f"{SHEET},P1,1,0,0", f"{SHEET},P1,2,1,500,0"),
        "paths.csv",
    )
    (path,) = q.paths
    assert path.source.confidence == Confidence.LOW


def test_repeated_header_listed(tmp_path, test_cfg):
    p = run(tmp_path, test_cfg, rows("sheet,x,y,label,x", f"{SHEET},0,0,E1,9"))
    (u,) = listed(p, "column")
    assert "not read" in u.reason and u.raw == "x"
