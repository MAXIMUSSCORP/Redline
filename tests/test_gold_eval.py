import csv
import json
from pathlib import Path

from redline.tools import gold_eval
from redline.tools.gold_eval import distance, norm, run

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "samples" / "gold" / "tables"
HEAD = "Panel,Ckt,Description,Load (VA),Breaker,Poles,Wire Sz.\n"
TRUTH = "circuit,description,breaker_a,poles,wire,load_va\n"
MANIFEST = "table_id,source_file,page_or_layout,panel,kind,tags,transcribed_by,checked_by,notes\n"


def make(tmp_path, source, truth, panel="T-1", kind="csv", tags="", check=None):
    """One table in a gold folder: source CSV text, truth rows, optional check rows."""
    d = tmp_path / "gold"
    (d / "truth").mkdir(parents=True, exist_ok=True)
    (d / "src.csv").write_text(HEAD + source, encoding="utf-8")
    (d / "truth" / "t1.csv").write_text(TRUTH + truth, encoding="utf-8")
    (d / "manifest.csv").write_text(
        MANIFEST + f"t1,src.csv,,{panel},{kind},{tags},x,,\n", encoding="utf-8"
    )
    if check is not None:
        (d / "check").mkdir(exist_ok=True)
        (d / "check" / "t1.csv").write_text(TRUTH + check, encoding="utf-8")
    return d


def results(out):
    with (out / "results.csv").open(encoding="utf-8", newline="") as f:
        return {
            (r["scope"], r["table_id"], r["column"], r["measure"]): (
                int(r["numerator"]),
                int(r["denominator"]),
            )
            for r in csv.DictReader(f)
        }


def lines(text):
    return dict(x.split(": ", 1) for x in text.splitlines())


SOURCE = "T-1,1,Lighting,1350,20 A,1,12 AWG\nT-1,2,Receptacles,1500,15,1,12 AWG\n"
GOOD = "1,Lighting,20 A,1,12 AWG,1350\n2,Receptacles,15,1,12 AWG,1500\n"


def test_silent_wrong_pass_counted(tmp_path, test_cfg):
    src = (ROOT / "samples" / "csv" / "two_panels.csv").read_text(encoding="utf-8")
    for old, new in (
        (
            "1,A,20 A,12 AWG,Cu,75,3,0.005,120,\nLP-1,2,",
            "1,A,25 A,12 AWG,Cu,75,3,0.005,120,\nLP-1,2,",
        ),
        ("15,12 AWG,Cu,75,3,0.005,120,\nLP-1,3,", "15,10 AWG,Cu,75,3,0.005,120,\nLP-1,3,"),
        ("Office receptacles,1800", "Office receptacles,1900"),
    ):
        assert old in src
        src = src.replace(old, new, 1)
    d = tmp_path / "gold"
    (d / "truth").mkdir(parents=True)
    (d / "planted.csv").write_text(src, encoding="utf-8")
    truth = (GOLD / "truth" / "csv_lp1.csv").read_text(encoding="utf-8")
    (d / "truth" / "lp1.csv").write_text(truth, encoding="utf-8")
    (d / "manifest.csv").write_text(MANIFEST + "lp1,planted.csv,,LP-1,csv,,x,,\n", encoding="utf-8")
    text, code = run(d, test_cfg, tmp_path / "o")
    assert code == 0
    assert lines(text)["silent wrong passes"] == "3"
    r = results(tmp_path / "o")
    for col in ("breaker_a", "wire", "load_va"):
        assert r[("table", "lp1", col, "silent_wrong_pass")][0] == 1
    cells = (tmp_path / "o" / "cells.csv").read_text(encoding="utf-8")
    assert ",breaker_a,20 A,25.0,HIGH,wrong" in cells
    assert ",wire,12 AWG,10 AWG,MEDIUM,wrong" in cells


def test_silent_missing_row_counted(tmp_path, test_cfg):
    d = make(tmp_path, "T-1,1,Lighting,1350,20 A,1,12 AWG\n", GOOD)
    text, _ = run(d, test_cfg, tmp_path / "o")
    assert lines(text)["silent missing rows"] == "1"
    assert results(tmp_path / "o")[("table", "t1", "rows", "row_recall")] == (1, 2)
    d = make(tmp_path / "b", SOURCE, GOOD, panel="NOPE")
    text, _ = run(d, test_cfg, tmp_path / "o2")
    assert lines(text)["silent missing rows"] == "2"
    assert text.startswith("tables: 1 in manifest, 0 read, 0 listed")


def test_number_columns_normalized():
    assert norm("breaker_a", "20 A") == norm("breaker_a", "20.0") == norm("breaker_a", " 20a ")
    assert norm("load_va", "1,350") == norm("load_va", "1350 VA") == norm("load_va", "1.35 kVA")
    assert norm("poles", "2P") == norm("poles", "2")
    assert norm("load_va", "TBD") == "t:tbd" and norm("load_va", "TBD") != norm("load_va", "0")
    assert norm("breaker_a", "20") != norm("breaker_a", "25")


def test_wire_normalized_with_units():
    assert norm("wire", "#12") == norm("wire", "12 AWG") == norm("wire", "12 awg")
    assert norm("wire", "12") == "t:12" != norm("wire", "12 AWG")
    assert norm("wire", "500 MCM") == norm("wire", "500 kcmil")


def test_description_distance_reported_apart(tmp_path, test_cfg):
    src = "T-1,1,Lightin,1350,20 A,1,12 AWG\nT-1,2,receptacles  ,1500,15,1,12 AWG\n"
    d = make(tmp_path, src, GOOD)
    run(d, test_cfg, tmp_path / "o")
    r = results(tmp_path / "o")
    assert r[("table", "t1", "description", "cell_correct")] == (1, 2)
    assert r[("table", "t1", "description", "cell_wrong")] == (1, 2)
    assert r[("table", "t1", "description", "distance_le_1")] == (2, 2)
    assert distance("abc", "abd") == 1 and distance("", "ab") == 2


def test_rows_pair_on_circuit():
    gold = [["1"], ["2"], ["2"], [" 3"], ["[unreadable]"]]
    paired, extra = gold_eval._pair(gold, ["3", "2", "2", "9"])
    assert paired == [None, 1, 2, 0, None]
    assert extra == [3]
    assert gold_eval._pair([["A 1"]], ["a  1"])[0] == [0]


def test_unreadable_gold_cell_not_scored(tmp_path, test_cfg):
    truth = "1,Lighting,[unreadable],1,12 AWG,1350\n2,Receptacles,15,1,12 AWG,1500\n"
    src = "T-1,1,Lighting,1350,99 A,1,12 AWG\nT-1,2,Receptacles,1500,15,1,12 AWG\n"
    d = make(tmp_path, src, truth)
    text, _ = run(d, test_cfg, tmp_path / "o")
    r = results(tmp_path / "o")
    assert r[("table", "t1", "breaker_a", "cell_wrong")] == (0, 1)
    assert lines(text)["silent wrong passes"] == "0"


def test_low_cell_surfaced(tmp_path, test_cfg):
    src = "T-1,1,Lighting,1350,20 A,1,12\nT-1,2,Receptacles,1500,15,1,12 AWG\n"
    truth = "1,Lighting,20 A,1,12,1350\n2,Receptacles,15,1,12 AWG,1500\n"
    d = make(tmp_path, src, truth)
    run(d, test_cfg, tmp_path / "o")
    r = results(tmp_path / "o")
    assert r[("table", "t1", "wire", "surfaced")] == (1, 2)
    assert r[("table", "t1", "wire", "cell_not_read")] == (1, 2)
    assert r[("table", "t1", "wire", "silent_wrong_pass")] == (0, 2)


def test_wrong_cells_by_confidence(tmp_path, test_cfg):
    src = "T-1,1,Lighting,1350,25 A,1,10 AWG\nT-1,2,Receptacles,1500,15,1,12 AWG\n"
    d = make(tmp_path, src, GOOD)
    run(d, test_cfg, tmp_path / "o")
    r = results(tmp_path / "o")
    assert r[("table", "t1", "breaker_a", "wrong_high")][0] == 1
    assert r[("table", "t1", "wire", "wrong_medium")][0] == 1
    assert r[("table", "t1", "all", "wrong_low")][0] == 0
    assert r[("table", "t1", "all", "cell_wrong")][0] == 2


def test_human_disagreement_counted(tmp_path, test_cfg):
    check = "1,Lighting,25 A,1,12 AWG,1350\n3,Extra,15,1,12 AWG,1\n"
    d = make(tmp_path, SOURCE, GOOD, check=check)
    run(d, test_cfg, tmp_path / "o")
    r = results(tmp_path / "o")
    assert r[("table", "t1", "breaker_a", "human_disagreement")] == (1, 1)
    assert r[("table", "t1", "wire", "human_disagreement")] == (0, 1)
    assert r[("table", "t1", "rows", "check_rows_in_one_file")] == (2, 3)


def test_repeat_read_difference_named(tmp_path, test_cfg, monkeypatch):
    d = make(tmp_path, SOURCE, GOOD)
    real, calls = gold_eval._load_inputs, []

    def flaky(paths, cfg):
        out = real(paths, cfg)
        calls.append(1)
        if len(calls) % 2 == 0:
            out[0].panels[0].circuits.pop()
        return out

    monkeypatch.setattr(gold_eval, "_load_inputs", flaky)
    text, code = run(d, test_cfg, tmp_path / "o")
    assert code == 0 and lines(text)["repeat run differs"] == "t1"
    assert results(tmp_path / "o")[("table", "t1", "table", "repeat_run_differs")] == (1, 1)
    monkeypatch.setattr(gold_eval, "_load_inputs", real)
    text, _ = run(d, test_cfg, tmp_path / "o2")
    assert "repeat run differs" not in text


def test_slices_by_kind_and_tag(tmp_path, test_cfg):
    d = make(tmp_path, SOURCE, GOOD, kind="csv", tags="dense; vertical_text")
    run(d, test_cfg, tmp_path / "o")
    r = results(tmp_path / "o")
    for scope in ("kind:csv", "tag:dense", "tag:vertical_text", "total"):
        assert r[(scope, "", "rows", "row_recall")] == (2, 2)
    assert ("tag:other", "", "rows", "row_recall") not in r


def test_results_csv_repeats_byte_identical(tmp_path, test_cfg):
    run(GOLD, test_cfg, tmp_path / "a")
    run(GOLD, test_cfg, tmp_path / "b")
    for name in ("results.csv", "cells.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    head = (tmp_path / "a" / "results.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "table_id" in head and "column" in head
    assert "time" not in head and "second" not in head
    assert (tmp_path / "a" / "timing.csv").is_file()


def test_run_json_keys_and_empty_models(tmp_path, test_cfg):
    run(GOLD, test_cfg, tmp_path / "o")
    j = json.loads((tmp_path / "o" / "run.json").read_text(encoding="utf-8"))
    keys = ["tool_version", "config_hashes", "extractor_versions", "manifest_sha256"]
    assert sorted(j) == sorted([*keys, "sources", "models"])
    assert j["models"] == [] and j["config_hashes"] == test_cfg.hashes
    assert len(j["sources"]) == 5


def test_no_manifest_exits_2(tmp_path, test_cfg):
    text, code = run(tmp_path, test_cfg, None)
    assert code == 2 and "manifest.csv" in text
    assert not (tmp_path / "results").exists()
    (tmp_path / "manifest.csv").write_text("table_id,panel\nt1,P\n", encoding="utf-8")
    assert run(tmp_path, test_cfg, None)[1] == 2


def test_synthetic_gold_layout():
    with (GOLD / "manifest.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    ids = sorted(r["table_id"] for r in rows)
    assert len(ids) == 11 and len(set(ids)) == 11 and all(" " not in i for i in ids)
    assert {Path(r["source_file"]).name for r in rows} == {
        "two_panels.csv",
        "panel_sheet.acad_plugin.rawdrawing.json",
        "panel_sheet.oda_ezdxf.rawdrawing.json",
        "panel_text.pdf",
        "scanned_panel.pdf",
    }
    assert all((GOLD / r["source_file"]).resolve().is_file() for r in rows)
    for i in ids:
        with (GOLD / "truth" / f"{i}.csv").open(encoding="utf-8", newline="") as f:
            assert next(csv.reader(f)) == gold_eval.TRUTH_HEADER
    assert sorted(p.stem for p in (GOLD / "check").glob("*.csv")) == [ids[0], ids[5], ids[10]]
