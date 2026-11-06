import json
from pathlib import Path

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
