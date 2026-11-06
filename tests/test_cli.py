import json
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


def test_demo_project_no_panels_exits_2(tmp_path, capsys):
    rc, err = _run(tmp_path, '{"name": "x", "panels": []}', capsys)
    assert rc == 2 and "no panels" in err and not (tmp_path / "r.html").exists()


def test_out_csv_unwritable_names_csv(tmp_path, capsys):
    (tmp_path / "findings.csv").mkdir()
    rc, err = _run(tmp_path, Path(DEMO).read_text(encoding="utf-8"), capsys)
    assert rc == 2 and "findings.csv" in err and not (tmp_path / "r.html").exists()
