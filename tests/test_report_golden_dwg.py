r"""End-to-end run of the plugin RawDrawing fixture against the golden findings file.

The golden file is made only by this manual command, never by a test. Run it from the repo root
after a deliberate change to the fixtures, the parser or a rule, read the CSV by eye, then commit it:

    RL check samples/dwg/panel_sheet.acad_plugin.rawdrawing.json --config tests/test_config/ --out %TEMP%\redline-golden-dwg\report.html
    copy %TEMP%\redline-golden-dwg\findings.csv tests\golden\dwg\findings.csv
"""

import csv
import json
from pathlib import Path

from redline.cli import main
from redline.report.html import SECTION_IDS

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "samples" / "dwg" / "panel_sheet.acad_plugin.rawdrawing.json"
TEST_CFG = ROOT / "tests" / "test_config"
GOLDEN = ROOT / "tests" / "golden" / "dwg" / "findings.csv"


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _run(cfg: Path, tmp_path: Path, src: Path = FIXTURE) -> Path:
    argv = ["check", str(src), "--config", str(cfg), "--out", str(tmp_path / "r.html")]
    assert main(argv) == 0
    return tmp_path


def test_dwg_findings_match_golden(tmp_path):
    assert _rows(_run(TEST_CFG, tmp_path) / "findings.csv") == _rows(GOLDEN)


def test_dwg_report_has_every_section(tmp_path):
    html = (_run(TEST_CFG, tmp_path) / "r.html").read_text(encoding="utf-8")
    for section in SECTION_IDS:
        assert f'id="{section}"' in html, section


def test_dwg_skeleton_config_gives_no_violation(tmp_path):
    rows = _rows(_run(ROOT / "config", tmp_path) / "findings.csv")
    assert rows and all(r["severity"] != "VIOLATION" for r in rows)


def test_dwg_test_config_violation_is_planted(tmp_path):
    rows = _rows(_run(TEST_CFG, tmp_path) / "findings.csv")
    found = [
        (r["rule_id"], r["message"].split(":")[0]) for r in rows if r["severity"] == "VIOLATION"
    ]
    assert found == [("ampacity", "LP-11 ckt 9")]


def test_footer_extractor_provenance(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["source_sha256"] = "ab12" * 16
    data["host_version"] = (
        "AutoCAD 2026 " + "x" * 60
    )  # the whole line is past the old 80 character cut
    src = tmp_path / "in" / "long_host.rawdrawing.json"
    src.parent.mkdir()
    src.write_text(json.dumps(data), encoding="utf-8")
    html = (_run(TEST_CFG, tmp_path / "out", src) / "r.html").read_text(encoding="utf-8")
    want = f"acad_plugin 0.1.0, host {data['host_version']}, SHA-256 {'ab12' * 16}"
    assert f"long_host.rawdrawing.json {want}" in html
