r"""End-to-end run of samples/pdf against the golden findings file.

The golden file is made only by this manual command, never by a test. Run it from the repo root
after a deliberate change to the samples, the parser or a rule, read the CSV by eye, then commit it:

    RL check samples/pdf --config tests/test_config/ --out %TEMP%\redline-golden-pdf\report.html
    copy %TEMP%\redline-golden-pdf\findings.csv tests\golden\pdf\findings.csv
"""

import csv
from pathlib import Path

from redline.cli import main
from redline.report.html import SECTION_IDS

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples" / "pdf"
TEST_CFG = ROOT / "tests" / "test_config"
GOLDEN = ROOT / "tests" / "golden" / "pdf" / "findings.csv"


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _run(cfg: Path, tmp_path: Path) -> Path:
    argv = ["check", str(SAMPLES), "--config", str(cfg), "--out", str(tmp_path / "r.html")]
    assert main(argv) == 0
    return tmp_path


def test_pdf_findings_match_golden(tmp_path):
    assert _rows(_run(TEST_CFG, tmp_path) / "findings.csv") == _rows(GOLDEN)


def test_pdf_report_has_every_section(tmp_path):
    html = (_run(TEST_CFG, tmp_path) / "r.html").read_text(encoding="utf-8")
    for section in SECTION_IDS:
        assert f'id="{section}"' in html, section


def test_pdf_skeleton_config_gives_no_violation(tmp_path):
    rows = _rows(_run(ROOT / "config", tmp_path) / "findings.csv")
    assert rows and all(r["severity"] != "VIOLATION" for r in rows)


def test_pdf_test_config_violation_is_planted(tmp_path):
    rows = _rows(_run(TEST_CFG, tmp_path) / "findings.csv")
    found = [r for r in rows if r["severity"] == "VIOLATION"]
    assert [(r["rule_id"], r["message"].split(":")[0]) for r in found] == [
        ("ampacity", "LP-21 ckt 9")
    ]
    assert "(MEDIUM)" in found[0]["inputs_used"]
    assert "(HIGH)" not in found[0]["inputs_used"]
