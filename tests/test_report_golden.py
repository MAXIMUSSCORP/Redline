r"""End-to-end run of the synthetic demo project against the golden findings file.

The golden file is made only by this manual command, never by a test. Run it from the repo root
after a deliberate change to the demo project or a rule, read the CSV by eye, then commit it:

    redline check --demo-project tests/golden/demo_project.json --config tests/test_config/ --out %TEMP%
edline-golden\report.html
    copy %TEMP%
edline-golden\findings.csv tests\golden\findings.csv
"""

import csv
from pathlib import Path

from redline.cli import main
from redline.registry import RULES
from redline.report.html import SECTION_IDS

ROOT = Path(__file__).resolve().parent.parent
DEMO = str(ROOT / "tests" / "golden" / "demo_project.json")
GOLDEN = ROOT / "tests" / "golden" / "findings.csv"


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _run(cfg: str, tmp_path: Path) -> Path:
    assert (
        main(["check", "--demo-project", DEMO, "--config", cfg, "--out", str(tmp_path / "r.html")])
        == 0
    )
    return tmp_path


def test_findings_match_golden(tmp_path):
    out = _run(str(ROOT / "tests" / "test_config"), tmp_path)
    rows = _rows(out / "findings.csv")
    assert rows == _rows(GOLDEN)
    assert {r["rule_id"] for r in rows} == {r.id for r in RULES}
    assert any(r["severity"] == "VIOLATION" for r in rows)


def test_report_has_every_section(tmp_path):
    out = _run(str(ROOT / "tests" / "test_config"), tmp_path)
    html = (out / "r.html").read_text(encoding="utf-8")
    for section in SECTION_IDS:
        assert f'id="{section}"' in html, section


def test_skeleton_config_gives_no_violation(tmp_path):
    out = _run(str(ROOT / "config"), tmp_path)
    assert all(r["severity"] != "VIOLATION" for r in _rows(out / "findings.csv"))
