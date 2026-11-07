r"""End-to-end run of samples/csv against the golden findings file.

The golden file is made only by this manual command, never by a test. Run it from the repo root
after a deliberate change to the samples, the parser or a rule, read the CSV by eye, then commit it:

    RL check samples/csv --config tests/test_config/ --out %TEMP%\redline-golden-csv\report.html
    copy %TEMP%\redline-golden-csv\findings.csv tests\golden\csv\findings.csv
"""

import csv
from pathlib import Path

from redline.cli import main
from redline.config import load_config
from redline.model import Confidence
from redline.parsers.csv_xlsx import parse_file
from redline.report.html import SECTION_IDS

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = str(ROOT / "samples" / "csv")
TEST_CFG = ROOT / "tests" / "test_config"
GOLDEN = ROOT / "tests" / "golden" / "csv" / "findings.csv"


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _run(cfg: Path, tmp_path: Path) -> Path:
    argv = ["check", SAMPLES, "--config", str(cfg), "--out", str(tmp_path / "r.html")]
    assert main(argv) == 0
    return tmp_path


def test_csv_findings_match_golden(tmp_path):
    assert _rows(_run(TEST_CFG, tmp_path) / "findings.csv") == _rows(GOLDEN)


def test_csv_report_has_every_section(tmp_path):
    html = (_run(TEST_CFG, tmp_path) / "r.html").read_text(encoding="utf-8")
    for section in SECTION_IDS:
        assert f'id="{section}"' in html, section


def test_csv_skeleton_config_gives_no_violation(tmp_path):
    rows = _rows(_run(ROOT / "config", tmp_path) / "findings.csv")
    assert rows and all(r["severity"] != "VIOLATION" for r in rows)


def test_csv_spare_with_load_reported(tmp_path):
    rows = _rows(_run(TEST_CFG, tmp_path) / "findings.csv")
    hit = [r for r in rows if "marked spare but shows a load" in r["message"]]
    assert len(hit) == 1
    assert hit[0]["message"].startswith("LP-1 ckt 20:") and hit[0]["severity"] == "NEEDS_REVIEW"


def test_revit_style_headers_map_high():
    parsed = parse_file(Path(SAMPLES) / "revit_style_circuits.txt", load_config(TEST_CFG))
    (panel,) = parsed.panels
    assert panel.name == "PP-1" and len(panel.circuits) == 8
    for c in (c for c in panel.circuits if not c.is_spare):  # the spare row is mostly blank
        for fld in ("poles", "breaker_a", "load_va", "voltage_v", "description"):
            v = getattr(c, fld)
            assert v.value is not None and v.source.confidence is Confidence.HIGH, (c.number, fld)
    assert any(u.raw == "Phase Label" for u in parsed.unparsed)


def test_csv_test_config_has_violation(tmp_path):
    rows = _rows(_run(TEST_CFG, tmp_path) / "findings.csv")
    assert any(r["severity"] == "VIOLATION" for r in rows)
