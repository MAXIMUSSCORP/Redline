import csv
import json
import shutil
from pathlib import Path

import pytest

from redline.cli import main
from redline.registry import RULES

ROOT = Path(__file__).resolve().parent.parent
DEMO = str(ROOT / "tests" / "golden" / "demo_project.json")
TEST_CFG = str(ROOT / "tests" / "test_config")


def test_cli_exit_0_on_completed_run(tmp_path):
    out = tmp_path / "report.html"
    assert main(["check", "--demo-project", DEMO, "--config", TEST_CFG, "--out", str(out)]) == 0
    assert out.exists()
    assert (tmp_path / "findings.csv").exists()


def test_cli_exit_2_on_bad_config(tmp_path, capsys):
    argv = [
        "check",
        "--demo-project",
        DEMO,
        "--config",
        str(tmp_path),
        "--out",
        str(tmp_path / "r.html"),
    ]
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "Traceback" not in err


def test_cli_exit_2_on_missing_demo_project(tmp_path, capsys):
    missing = str(tmp_path / "nope.json")
    assert main(["check", "--demo-project", missing, "--config", TEST_CFG]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_cli_exit_2_on_invalid_json_and_no_input(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main(["check", "--demo-project", str(bad), "--config", TEST_CFG]) == 2
    bad.write_text(json.dumps({"panels": []}), encoding="utf-8")
    assert main(["check", "--demo-project", str(bad), "--config", TEST_CFG]) == 2
    assert main(["check", "--config", TEST_CFG]) == 2


def test_cli_skip_rule_is_reported_not_run(tmp_path):
    out = tmp_path / "r.html"
    argv = ["check", "--demo-project", DEMO, "--config", TEST_CFG, "--out", str(out)]
    assert main([*argv, "--skip-rule", "ampacity"]) == 0
    assert "skipped by request" in (tmp_path / "findings.csv").read_text(encoding="utf-8")


def test_registry_lists_eight_rules():
    assert [r.id for r in RULES] == [
        "ampacity",
        "continuous_load",
        "voltage_drop",
        "bonding",
        "phase_balance",
        "panel_demand",
        "completeness",
        "fire_alarm",
    ]


def _run(tmp_path, text, capsys, out=None):
    f = tmp_path / "p.json"
    f.write_text(text, encoding="utf-8")
    argv = ["check", "--demo-project", str(f), "--config", TEST_CFG]
    argv += ["--out", str(out or tmp_path / "r.html")]
    rc = main(argv)
    return rc, capsys.readouterr().err


def _demo_text(edit):
    d = json.loads(Path(DEMO).read_text(encoding="utf-8"))
    edit(d)
    return json.dumps(d)


def test_demo_project_nan_exits_2(tmp_path, capsys):
    text = _demo_text(lambda d: d["panels"][0]["voltage_v"].update(value=1))
    text = text.replace('"value": 1,', '"value": NaN,', 1)
    rc, err = _run(tmp_path, text, capsys)
    assert rc == 2 and "Traceback" not in err


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        '{"name": "x", "panels": [5]}',
        "[" * 100000,
        '{"name": "x", "panels": []}'.replace("[]", "5"),
    ],
)
def test_demo_project_wrong_shape_exits_2(tmp_path, capsys, text):
    rc, err = _run(tmp_path, text, capsys)
    assert rc == 2 and "Traceback" not in err


def test_demo_project_bare_int_field_exits_2(tmp_path, capsys):
    text = _demo_text(lambda d: d["panels"][0].update(bus_rating_a=100))
    rc, err = _run(tmp_path, text, capsys)
    assert rc == 2 and "Traceback" not in err


def test_demo_project_unknown_key_exits_2(tmp_path, capsys):
    text = _demo_text(lambda d: d["panels"][0]["circuits"][0].update(breaker_amps=20))
    rc, err = _run(tmp_path, text, capsys)
    assert rc == 2 and "breaker_amps" in err and "Traceback" not in err


def test_out_same_as_csv_exits_2(tmp_path, capsys):
    rc, _ = _run(
        tmp_path, Path(DEMO).read_text(encoding="utf-8"), capsys, tmp_path / "findings.csv"
    )
    assert rc == 2 and not (tmp_path / "findings.csv").exists()


def test_out_is_directory_exits_2(tmp_path, capsys):
    d = tmp_path / "outdir"
    d.mkdir()
    rc, err = _run(tmp_path, Path(DEMO).read_text(encoding="utf-8"), capsys, d)
    assert rc == 2 and "Traceback" not in err and not (tmp_path / "findings.csv").exists()


def _demo_edit(tmp_path, capsys, edit):
    rc, err = _run(tmp_path, _demo_text(edit), capsys)
    assert "Traceback" not in err
    return rc, err


def test_demo_project_source_text_fields_must_be_str(tmp_path, capsys):
    def edit(d):
        d["panels"][0]["voltage_v"]["source"]["model"] = ["x"]

    assert _demo_edit(tmp_path, capsys, edit)[0] == 2


def test_demo_project_unknown_value_or_source_key_exits_2(tmp_path, capsys):
    rc, err = _demo_edit(tmp_path, capsys, lambda d: d["panels"][0]["voltage_v"].update(unit="V"))
    assert rc == 2 and "unit" in err
    rc, err = _demo_edit(
        tmp_path, capsys, lambda d: d["panels"][0]["voltage_v"]["source"].update(page=3)
    )
    assert rc == 2 and "page" in err


@pytest.mark.parametrize("bad", [0, [], "x", 5])
def test_demo_project_value_not_object_exits_2(tmp_path, capsys, bad):
    rc, _ = _demo_edit(tmp_path, capsys, lambda d: d["panels"][0].update(voltage_v=bad))
    assert rc == 2


def test_value_bool_number_exits_2(tmp_path, capsys):
    def edit(d):
        d["panels"][0]["circuits"][0]["breaker_a"]["value"] = True

    assert _demo_edit(tmp_path, capsys, edit)[0] == 2


@pytest.mark.parametrize("bad", ["no", 0, None])
def test_is_spare_must_be_bool_exits_2(tmp_path, capsys, bad):
    rc, _ = _demo_edit(
        tmp_path, capsys, lambda d: d["panels"][0]["circuits"][0].update(is_spare=bad)
    )
    assert rc == 2


def test_demo_project_overflow_float_exits_2(tmp_path, capsys):
    text = _demo_text(lambda d: d["panels"][0]["voltage_v"].update(value=1))
    text = text.replace('"value": 1,', '"value": 1e999,', 1)
    rc, err = _run(tmp_path, text, capsys)
    assert rc == 2 and "Traceback" not in err


def test_out_unwritable_exits_2(tmp_path, capsys):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    rc, err = _run(
        tmp_path, Path(DEMO).read_text(encoding="utf-8"), capsys, blocker / "sub" / "r.html"
    )
    assert rc == 2 and "Traceback" not in err


def _demo_dict():
    return json.loads(Path(DEMO).read_text(encoding="utf-8"))


def test_demo_project_duplicate_ids_exit_2(tmp_path, capsys):
    def feeder(d):
        d["feeders"].append(dict(d["feeders"][0]))

    def panel(d):
        d["panels"].append(dict(d["panels"][0]))

    for edit, name in ((feeder, "F-1"), (panel, "DP-1")):
        rc, err = _demo_edit(tmp_path, capsys, edit)
        assert rc == 2 and name in err and "repeated" in err


@pytest.mark.parametrize("bad", ["x", [], {}])
def test_value_non_number_exits_2(tmp_path, capsys, bad):
    def edit(d):
        d["panels"][0]["circuits"][0]["breaker_a"]["value"] = bad

    assert _demo_edit(tmp_path, capsys, edit)[0] == 2


def test_demo_project_huge_int_exits_2(tmp_path, capsys):
    text = _demo_text(lambda d: d["panels"][0]["voltage_v"].update(value=1))
    text = text.replace('"value": 1,', '"value": 1' + "0" * 400 + ",", 1)
    rc, err = _run(tmp_path, text, capsys)
    assert rc == 2 and "Traceback" not in err


def test_demo_project_duplicate_json_key_exits_2(tmp_path, capsys):
    text = Path(DEMO).read_text(encoding="utf-8").replace("{", '{"name": "again", ', 1)
    rc, err = _run(tmp_path, text, capsys)
    assert rc == 2 and "name" in err and "Traceback" not in err


def test_demo_project_circuit_panel_mismatch_exits_2(tmp_path, capsys):
    def edit(d):
        d["panels"][0]["circuits"][0]["panel"] = "ELSEWHERE"

    rc, err = _demo_edit(tmp_path, capsys, edit)
    assert rc == 2 and "ELSEWHERE" in err


def test_out_windows_alias_of_csv_exits_2(tmp_path, capsys):
    text = Path(DEMO).read_text(encoding="utf-8")
    for tail in ("findings.csv.", "findings.csv ", "findings.csv::$DATA", "FINDINGS.CSV."):
        rc, _ = _run(tmp_path, text, capsys, f"{tmp_path}\\{tail}")
        assert rc == 2, tail
        assert not (tmp_path / "findings.csv").exists() and not (tmp_path / "r.html").exists()


def test_demo_project_empty_circuit_panel_exits_2(tmp_path, capsys):
    def edit(d):
        d["panels"][0]["circuits"][0]["panel"] = ""

    rc, err = _demo_edit(tmp_path, capsys, edit)
    assert rc == 2 and "Traceback" not in err


def test_demo_project_no_panels_exits_2(tmp_path, capsys):
    rc, err = _run(tmp_path, '{"name": "x", "panels": []}', capsys)
    assert rc == 2 and "no panels" in err and not (tmp_path / "r.html").exists()


def test_out_csv_unwritable_names_csv(tmp_path, capsys):
    (tmp_path / "findings.csv").mkdir()
    rc, err = _run(tmp_path, Path(DEMO).read_text(encoding="utf-8"), capsys)
    assert rc == 2 and "findings.csv" in err and not (tmp_path / "r.html").exists()


_SRC = {"file": "f.csv", "locator": "r1", "method": "csv", "confidence": "HIGH"}


def _set(path, bad):
    def edit(d):
        node = d
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = bad

    return edit


@pytest.mark.parametrize(
    "edit",
    [
        _set(("name",), 5),
        _set(("panels", 0, "name"), 5),
        _set(("panels", 0, "circuits", 0, "panel"), []),
        _set(("panels", 0, "circuits", 0, "number"), 7),
        _set(("panels", 1, "fed_from", "value"), 5),
        _set(("panels", 0, "circuits", 0, "conductor_size", "value"), 12),
        _set(("panels", 0, "circuits", 0, "load_type", "value"), ["continuous"]),
        _set(("panels", 0, "circuits", 0, "description", "value"), {"a": 1}),
        _set(("feeders", 0, "id"), 1),
        _set(("feeders", 0, "from_panel", "value"), 3),
        _set(("feeders", 0, "bonding_size", "value"), 3),
        _set(("unparsed",), [{"kind": "row", "raw": "x", "reason": 5, "source": _SRC}]),
        _set(("devices",), [{"type": 5, "source": _SRC}]),
        _set(("coverage",), [{"file": 1, "unit": "u", "what_read": "w", "method": "m"}]),
    ],
)
def test_demo_project_text_field_wrong_type_exits_2(tmp_path, capsys, edit):
    rc, err = _demo_edit(tmp_path, capsys, edit)
    assert rc == 2 and "Traceback" not in err
    assert not (tmp_path / "r.html").exists() and not (tmp_path / "findings.csv").exists()


def test_demo_project_lone_surrogate_exits_2(tmp_path, capsys):
    for edit in (
        _set(("panels", 0, "circuits", 0, "description", "raw"), "\ud800"),
        _set(("panels", 0, "circuits", 0, "description", "value"), "x\udc00"),
        _set(("name",), "a\ud800b"),
    ):
        rc, err = _demo_edit(tmp_path, capsys, edit)
        assert rc == 2 and "Traceback" not in err
        assert not (tmp_path / "r.html").exists() and not (tmp_path / "findings.csv").exists()


def test_out_cannot_overwrite_inputs_exits_2(tmp_path):
    demo = tmp_path / "p.json"
    demo.write_text(Path(DEMO).read_text(encoding="utf-8"), encoding="utf-8")
    cfg = tmp_path / "cfg"
    shutil.copytree(TEST_CFG, cfg)
    before = (demo.read_bytes(), (cfg / "ai.yaml").read_bytes())
    for target in (demo, cfg / "ai.yaml", tmp_path / "sub" / ".." / "p.json"):
        argv = ["check", "--demo-project", str(demo), "--config", str(cfg), "--out", str(target)]
        assert main(argv) == 2
    assert before == (demo.read_bytes(), (cfg / "ai.yaml").read_bytes())
    assert not (tmp_path / "findings.csv").exists()


def test_out_short_name_alias_refused(tmp_path, capsys):
    text = Path(DEMO).read_text(encoding="utf-8")
    rc, err = _run(tmp_path, text, capsys, tmp_path / "FINDIN~1.CSV")
    assert rc == 2 and "Traceback" not in err
    assert not (tmp_path / "findings.csv").exists() and not (tmp_path / "FINDIN~1.CSV").exists()


def test_csv_path_cannot_overwrite_inputs_exits_2(tmp_path, capsys):
    proj = tmp_path / "findings.csv"
    shutil.copy(DEMO, proj)
    before = proj.read_bytes()
    argv = ["check", "--demo-project", str(proj), "--config", TEST_CFG]
    assert main([*argv, "--out", str(tmp_path / "report.html")]) == 2
    assert proj.read_bytes() == before and not (tmp_path / "report.html").exists()
    assert "Traceback" not in capsys.readouterr().err
    cfg = tmp_path / "cfg"
    shutil.copytree(TEST_CFG, cfg)
    (cfg / "findings.csv").write_text("x", encoding="utf-8")
    assert (
        main(["check", "--demo-project", DEMO, "--config", str(cfg), "--out", str(cfg / "r.html")])
        == 0
    )


def _provenance(tmp_path, edition):
    data = json.loads(Path(DEMO).read_text(encoding="utf-8"))
    data["code_edition"] = edition
    data["run_info"] = {
        "tool_version": "9.9",
        "extractor_versions": {"acad_dump": "3.1-made-up"},
        "model_ids_versions_hashes": ["detector-x 2.0 sha256:abc123"],
    }
    f = tmp_path / "p.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "r.html"
    assert main(["check", "--demo-project", str(f), "--config", TEST_CFG, "--out", str(out)]) == 0
    return out.read_text(encoding="utf-8")


def test_input_provenance_reported(tmp_path):
    html = _provenance(tmp_path, "TEST EDITION, NOT CEC")
    assert "detector-x 2.0 sha256:abc123" in html and "acad_dump 3.1-made-up" in html
    assert "Models: none" not in html and "none in this run" not in html


def test_project_edition_mismatch_stated(tmp_path):
    same = _provenance(tmp_path, "TEST EDITION, NOT CEC")
    assert "Project code edition: TEST EDITION, NOT CEC" in same
    assert "different code edition" not in same
    other = _provenance(tmp_path, "Some Other Edition")
    assert "Project code edition: Some Other Edition" in other
    assert "different code edition" in other


def test_output_bounded_for_long_ids_and_many_circuits(tmp_path):
    d = _demo_dict()
    feeder_id = "F" * 200000
    d["feeders"][0]["id"] = feeder_id
    panel = next(p for p in d["panels"] if p["name"] == d["feeders"][0]["to_panel"]["value"])
    base = panel["circuits"][2]
    panel["circuits"] = [dict(base, number=str(n)) for n in range(1, 201)]
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    argv = [
        "check",
        "--demo-project",
        str(f),
        "--config",
        TEST_CFG,
        "--out",
        str(tmp_path / "r.html"),
    ]
    assert main(argv) == 0
    assert (tmp_path / "findings.csv").stat().st_size < 5_000_000


def _provenance_with(tmp_path, run_info):
    data = _demo_dict()
    data["run_info"] = run_info
    f = tmp_path / "p.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "r.html"
    argv = ["check", "--demo-project", str(f), "--config", TEST_CFG, "--out", str(out)]
    return main(argv), out


def test_input_provenance_all_fields_reported(tmp_path):
    rc, out = _provenance_with(tmp_path, {"tool_version": "9.9-input", "seeds": {"detector": 42}})
    html = out.read_text(encoding="utf-8")
    assert rc == 0 and "9.9-input" in html and "detector 42" in html
    rc, out = _provenance_with(tmp_path, {"tool_version": "1"})
    assert rc == 0 and "<td>Seeds</td><td>—</td>" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "run_info",
    [
        {"tool_version": ""},
        {"tool_version": "1", "extractor_versions": {"": "1"}},
        {"tool_version": "1", "extractor_versions": {"a": ""}},
        {"tool_version": "1", "model_ids_versions_hashes": [""]},
        {"tool_version": "1", "seeds": {"": 1}},
        {"tool_version": "1", "config_hashes": {"a": ""}},
    ],
)
def test_input_provenance_empty_strings_refused(tmp_path, run_info):
    rc, _ = _provenance_with(tmp_path, run_info)
    assert rc == 2


@pytest.mark.parametrize("bad", [[], False, 0, ""])
def test_demo_project_run_info_not_object_exits_2(tmp_path, capsys, bad):
    rc, err = _demo_edit(tmp_path, capsys, lambda d: d.update(run_info=bad))
    assert rc == 2 and "Traceback" not in err


def _chain_dict(n):
    d = _demo_dict()
    lp, top = d["panels"][1], d["panels"][0]
    f0 = d["feeders"][0]
    panels = []
    for i in range(n):
        p = json.loads(json.dumps(lp))
        p["name"] = f"P{i}"
        for c in p["circuits"]:
            c["panel"] = f"P{i}"
        p["fed_from"] = {
            "value": f"P{i + 1}" if i < n - 1 else None,
            "raw": None,
            "source": top["voltage_v"]["source"],
        }
        panels.append(p)
    d["panels"] = panels
    base = lp["circuits"][0]
    panels[0]["circuits"] = [dict(base, number=str(i), panel="P0") for i in range(300)]
    d["feeders"] = [
        dict(
            f0,
            id=f"F{i}",
            from_panel=dict(f0["from_panel"], value=f"P{i + 1}"),
            to_panel=dict(f0["to_panel"], value=f"P{i}"),
        )
        for i in range(n - 1)
    ]
    return d


def _adv_big_note():
    d = _demo_dict()
    big = d["panels"][1]
    big["voltage_v"]["source"]["note"] = "N" * 100_000
    big["voltage_v"]["source"]["confidence"] = "LOW"
    base = dict(big["circuits"][2], voltage_v={"value": None, "raw": None, "source": None})
    big["circuits"] = [
        dict(base, number=str(i), poles=dict(base["poles"], value=2)) for i in range(300)
    ]
    return d


def _adv_locator():
    d = _demo_dict()
    d["panels"][1]["source"]["locator"] = "L" * 4_000_000
    return d


@pytest.mark.parametrize(
    "build",
    [_adv_big_note, _adv_locator, lambda: _chain_dict(300)],
    ids=["note", "locator", "chain"],
)
def test_output_bounded_adversarial(tmp_path, build):
    d = build()
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    out = tmp_path / "r.html"
    assert main(["check", "--demo-project", str(f), "--config", TEST_CFG, "--out", str(out)]) == 0
    assert out.stat().st_size + (tmp_path / "findings.csv").stat().st_size < 10_000_000


def test_input_files_and_config_hashes_reported(tmp_path):
    rc, out = _provenance_with(
        tmp_path, {"tool_version": "1", "config_hashes": {"cec_tables.yaml": "feedface-input"}}
    )
    html = out.read_text(encoding="utf-8")
    assert rc == 0
    assert "demo_panels.csv; demo_feeders.csv" in html
    assert "feedface-input" in html and "Input cec_tables.yaml SHA-256" in html


BIG = "&" * 2_000_000


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d.update(name=BIG),
        lambda d: d.update(code_edition=BIG),
        lambda d: d["unparsed"].append(
            {"kind": "column", "raw": BIG, "reason": "r", "source": d["panels"][0]["source"]}
        ),
        lambda d: d["coverage"].append(
            {"file": "f", "unit": "u", "what_read": BIG, "method": "csv", "confidence_summary": "c"}
        ),
        lambda d: d["run_info"].update(tool_version=BIG),
        lambda d: d["run_info"]["extractor_versions"].update({BIG: BIG}),
        lambda d: d["run_info"]["seeds"].update({BIG: 1}),
    ],
    ids=[
        "name",
        "code_edition",
        "unparsed_raw",
        "what_read",
        "tool_version",
        "extractor",
        "seed_key",
    ],
)
def test_report_fields_clipped(tmp_path, edit):
    d = json.loads(Path(DEMO).read_text(encoding="utf-8"))
    d.setdefault("unparsed", [])
    d.setdefault("coverage", [])
    d.setdefault("run_info", {"tool_version": "0"})
    d["run_info"].setdefault("extractor_versions", {})
    d["run_info"].setdefault("seeds", {})
    edit(d)
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    out = tmp_path / "report.html"
    assert main(["check", "--demo-project", str(f), "--config", TEST_CFG, "--out", str(out)]) == 0
    assert out.stat().st_size < 10_000_000
    assert (tmp_path / "findings.csv").stat().st_size < 10_000_000


def _hash_report(tmp_path, hashes):
    d = json.loads(Path(DEMO).read_text(encoding="utf-8"))
    d.setdefault("run_info", {"tool_version": "0"})
    d["run_info"]["config_hashes"] = hashes
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    out = tmp_path / "report.html"
    assert main(["check", "--demo-project", str(f), "--config", TEST_CFG, "--out", str(out)]) == 0
    return out


def test_input_hash_rows_not_merged(tmp_path):
    a, b = "h" * 80 + "-one", "h" * 80 + "-two"
    html = _hash_report(tmp_path, {a: "aa", b: "bb"}).read_text(encoding="utf-8")
    assert html.count("Input " + "h" * 80) == 2
    assert "aa" in html and "bb" in html
    many = {f"n{i}": "x" for i in range(300_000)}
    out = _hash_report(tmp_path, many)
    assert out.stat().st_size < 10_000_000
    assert "and 299950 more" in out.read_text(encoding="utf-8")


SAMPLES = ROOT / "samples" / "csv"


def _csv_run(tmp_path, *inputs, extra=()):
    out = tmp_path / "out" / "report.html"
    argv = ["check", *map(str, inputs), "--config", TEST_CFG, "--out", str(out), *extra]
    return main(argv), out


def _input_dir(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    shutil.copy(SAMPLES / "two_panels.csv", d / "two_panels.csv")
    return d


def test_directory_input_exit_0(tmp_path):
    rc, out = _csv_run(tmp_path, SAMPLES)
    assert rc == 0 and out.exists() and (out.parent / "findings.csv").exists()
    html = out.read_text(encoding="utf-8")
    for name in ("two_panels.csv", "two_column.csv", "revit_style_circuits.txt"):
        assert name in html


def test_file_input_exit_0(tmp_path):
    rc, out = _csv_run(tmp_path, SAMPLES / "two_panels.csv")
    assert rc == 0 and "LP-1" in out.read_text(encoding="utf-8")


def test_demo_and_inputs_exclusive(tmp_path, capsys):
    rc, _ = _csv_run(tmp_path, SAMPLES / "two_panels.csv", extra=("--demo-project", DEMO))
    assert rc == 2 and "not both" in capsys.readouterr().err


def test_unsupported_file_listed(tmp_path):
    d = _input_dir(tmp_path)
    (d / "notes.docx").write_bytes(b"%PDF")
    rc, out = _csv_run(tmp_path, d)
    html = out.read_text(encoding="utf-8")
    assert rc == 0 and "notes.docx" in html and "not read: unsupported file type" in html


def test_no_readable_input_exits_2(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _csv_run(tmp_path, empty)[0] == 2
    assert _csv_run(tmp_path, tmp_path / "missing.csv")[0] == 2
    bad = tmp_path / "bad.csv"
    bad.write_bytes(b"a,b\x00\n")
    assert _csv_run(tmp_path, bad)[0] == 2
    assert "Traceback" not in capsys.readouterr().err


def test_read_file_no_panels_exits_0(tmp_path):
    f = tmp_path / "plain.csv"
    f.write_text("hello,world\n1,2\n", encoding="utf-8")
    rc, out = _csv_run(tmp_path, f)
    assert rc == 0 and out.exists() and "plain.csv" in out.read_text(encoding="utf-8")


def test_unreadable_file_listed_others_read(tmp_path):
    d = _input_dir(tmp_path)
    (d / "broken.csv").write_bytes(b"a,b\x00\n")
    rc, out = _csv_run(tmp_path, d)
    html = out.read_text(encoding="utf-8")
    assert rc == 0 and "broken.csv" in html and "LP-2" in html


def test_parser_error_listed_not_raised(tmp_path, monkeypatch):
    from redline import cli

    real = cli.parse_file

    def flaky(path, cfg):
        if Path(path).name == "two_column.csv":
            raise RuntimeError("boom")
        return real(path, cfg)

    monkeypatch.setattr(cli, "parse_file", flaky)
    rc, out = _csv_run(tmp_path, SAMPLES)
    html = out.read_text(encoding="utf-8")
    assert rc == 0 and "RuntimeError" in html and "LP-1" in html


def test_out_inside_input_dir_exits_2(tmp_path):
    d = _input_dir(tmp_path)
    argv = ["check", str(d), "--config", TEST_CFG, "--out", str(d / "report.html")]
    assert main(argv) == 2
    assert not (d / "report.html").exists() and not (d / "findings.csv").exists()


def test_out_cannot_overwrite_input_file_exits_2(tmp_path):
    f = _input_dir(tmp_path) / "two_panels.csv"
    before = f.read_bytes()
    assert main(["check", str(f), "--config", TEST_CFG, "--out", str(f)]) == 2
    assert f.read_bytes() == before


BLOCK = (
    "Panel,LP-1\nVoltage,208\nPhases,1\nBus,100\nMain,MLO\n"
    "Ckt,Description,Load (VA),Load Type,Poles,Breaker\n"
)
MOTOR = "{n},Motor,12000,motor,2,60\n"


def _rows(out, rule):
    with (out.parent / "findings.csv").open(encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r["rule_id"] == rule]


def _two_blocks(tmp_path):
    f = tmp_path / "two.csv"
    f.write_text(BLOCK + MOTOR.format(n=1) + "\n" + BLOCK + MOTOR.format(n=3), encoding="utf-8")
    return f


def test_repeated_panel_name_not_split_across_tables(tmp_path):
    rc, out = _csv_run(tmp_path, _two_blocks(tmp_path))
    assert rc == 0
    rows = [r for r in _rows(out, "panel_demand") if "LP-1" in r["message"]]
    assert rows and all(r["severity"] in ("NEEDS_REVIEW", "NOT_CHECKED") for r in rows)
    assert not any("demand 12000 VA" in r["message"] for r in rows)
    one = tmp_path / "one.csv"
    one.write_text(BLOCK + MOTOR.format(n=1) + MOTOR.format(n=3), encoding="utf-8")
    (tmp_path / "ctl").mkdir()
    rc, out1 = _csv_run(tmp_path / "ctl", one)
    sev = {r["severity"] for r in _rows(out1, "panel_demand")}
    assert rc == 0 and "VIOLATION" in sev


def test_repeated_panel_name_listed_in_unparsed(tmp_path):
    rc, out = _csv_run(tmp_path, _two_blocks(tmp_path))
    html = out.read_text(encoding="utf-8")
    assert rc == 0 and "is read 2 times" in html and html.count("two.csv") >= 2


def test_subfolder_listed_in_coverage(tmp_path):
    d = _input_dir(tmp_path)
    (d / "sub").mkdir()
    (d / "sub" / "b.csv").write_text("x\n", encoding="utf-8")
    rc, out = _csv_run(tmp_path, d)
    html = out.read_text(encoding="utf-8")
    assert rc == 0 and "sub" in html and "not read: subfolders are not read" in html


def test_unlistable_input_folder_no_traceback(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "locked"
    bad.mkdir()
    real = Path.iterdir

    def fake(self):
        if self.name == "locked":
            raise PermissionError(13, "Permission denied")
        return real(self)

    monkeypatch.setattr(Path, "iterdir", fake)
    rc, out = _csv_run(tmp_path, bad, SAMPLES / "two_panels.csv")
    html = out.read_text(encoding="utf-8")
    assert rc == 0 and "Traceback" not in capsys.readouterr().err
    assert "LP-2" in html and "locked" in html and "folder not read: Permission denied" in html


def test_repeated_inherited_panel_name_memory_linear():
    import tracemalloc

    from redline.cli import _flag_repeated_panels
    from redline.model import Confidence, Method, Panel, Project, Source

    name = "A" * 100_000
    project = Project(name="p")
    for i in range(2000):
        src = Source("f.csv", f"row {i}", Method.CSV, Confidence.MEDIUM)
        project.panels.append(Panel(name=name, source=src))
    tracemalloc.start()
    _flag_repeated_panels(project)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 20_000_000
    assert len(project.unparsed) == 1 and "row 1999" in project.unparsed[0].reason


def test_unplaced_page_break_rows_mark_panel_incomplete(tmp_path):
    head = ["Ckt,Description,Load (VA),Load Type,Poles,Breaker"]
    row = "{n},Heater,{va},noncontinuous,1,20"
    lines = ["Panel,LP-1", "Voltage,120", "Phases,1", "Bus,100", "Main,100", *head]
    lines += [row.format(n=n, va=1000) for n in (1, 3)]
    lines += ["Continued - Page 2 of 3", *head]
    lines += [row.format(n=n, va=4000) for n in (5, 7, 9)]
    f = tmp_path / "pb.csv"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rc, out = _csv_run(tmp_path, f)
    assert rc == 0
    rows = [r for r in _rows(out, "panel_demand") if "LP-1" in r["message"]]
    assert rows and {r["severity"] for r in rows} == {"NEEDS_REVIEW"}
    html = out.read_text(encoding="utf-8")
    assert "5, Heater, 4000, noncontinuous, 1, 20" in html and "no panel name" in html


def test_cut_footer_and_page2_rows_keep_panel_demand_needs_review(tmp_path):
    head = "Ckt,Description,Load VA,Load Type,Phase,Breaker,Poles"
    top = ["Panel,LP-1", "Bus,100", "Voltage,120/208", "Phases,3", head]
    body = ["1,Lights,800,noncontinuous,A,20,1", "3,Recepts,900,receptacle,B,20,1"]
    shapes = {
        "page2": [
            *body,
            "",
            "Page 2 of 2",
            head,
            "",
            "Kitchen",
            "7,Oven,9000,noncontinuous,A,40,2",
        ],
        "notes": [*body, "TOTAL,,1700,,,,", "NOTES:", "1,Provide GFCI breaker,,,,,"],
    }
    for name, tail in shapes.items():
        d = tmp_path / name
        d.mkdir()
        (d / "lp1.csv").write_text("\n".join([*top, *tail]) + "\n", encoding="utf-8")
        rc, out = _csv_run(d, d / "lp1.csv")
        assert rc == 0, name
        rows = [r for r in _rows(out, "panel_demand") if "LP-1" in r["message"]]
        assert rows and {r["severity"] for r in rows} == {"NEEDS_REVIEW"}, name
