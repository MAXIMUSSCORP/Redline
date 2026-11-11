r"""End-to-end run of the plan samples against the golden findings file.

The golden file is made only by this manual command, never by a test. Run it from the repo root
after a deliberate change to the samples, the parser or a rule, read the CSV by eye, then commit it
(RL is the redline command):

    RL check samples/plans --config tests/test_config/ --out %TEMP%\redline-golden-plans\report.html
    copy %TEMP%\redline-golden-plans\findings.csv tests\golden\plans\findings.csv
"""

import csv
from pathlib import Path

from redline.cli import main
from redline.extract import Unavailable, acad_console
from redline.report.html import SECTION_IDS

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "samples" / "plans"
TEST_CFG = ROOT / "tests" / "test_config"
GOLDEN = ROOT / "tests" / "golden" / "plans" / "findings.csv"


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _run(cfg: Path, tmp_path: Path) -> Path:
    argv = ["check", str(PLANS), "--config", str(cfg), "--out", str(tmp_path / "r.html")]
    assert main(argv) == 0
    return tmp_path


def test_plans_findings_match_golden(tmp_path):
    assert _rows(_run(TEST_CFG, tmp_path) / "findings.csv") == _rows(GOLDEN)


def test_plans_report_has_every_section(tmp_path):
    html = (_run(TEST_CFG, tmp_path) / "r.html").read_text(encoding="utf-8")
    for section in SECTION_IDS:
        assert f'id="{section}"' in html, section
    assert "CHAIR" in html and "FA_CLUSTER" in html


def test_plans_skeleton_config_gives_no_violation(tmp_path, monkeypatch):
    def refuse(*a, **k):
        raise Unavailable("the AutoCAD plugin is not started by the test suite")

    monkeypatch.setattr(acad_console, "extract", refuse)
    rows = _rows(_run(ROOT / "config", tmp_path) / "findings.csv")
    assert rows and all(r["severity"] != "VIOLATION" for r in rows)


def test_plans_test_config_violations_are_planted(tmp_path):
    rows = _rows(_run(TEST_CFG, tmp_path) / "findings.csv")
    found = [
        (r["file"], r["locator"], r["message"].split(" (")[0])
        for r in rows
        if r["severity"] == "VIOLATION"
    ]
    assert found == [
        ("exits.csv", "row 4", "sheet_fa101.dxf exit E3"),
        ("exits.csv", "row 3", "sheet_fa101.dxf exit E2"),
        ("paths.csv", "path P1", "sheet_fa101.dxf path P1"),
    ]
    assert not any(r["severity"] == "VIOLATION" and "fa102" in r["message"] for r in rows)
    fa102 = [r["severity"] for r in rows if r["message"].startswith("sheet_fa102.dxf")]
    assert fa102 and set(fa102) == {"NOT_CHECKED"}
