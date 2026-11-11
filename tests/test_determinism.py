"""Repeat runs give the same bytes (M6 D5). Same input, config, tool version, dependency versions
and machine. Not claimed: equal bytes across operating systems."""

import datetime
import getpass
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "tests" / "test_config"
SAMPLES = ROOT / "samples"
DWG = SAMPLES / "dwg"

_CODE = """
import sys
from redline.cli import main
sys.exit(main(sys.argv[1:]))
"""

INPUTS = {
    "csv": ["check", str(SAMPLES / "csv")],
    "plans": ["check", str(SAMPLES / "plans")],
    "pdf": [
        "check",
        str(SAMPLES / "pdf" / "panel_text.pdf"),
        str(SAMPLES / "pdf" / "scanned_panel.pdf"),
    ],
    "dwg_plugin": ["check", str(DWG / "panel_sheet.acad_plugin.rawdrawing.json")],
    "dwg_oda": ["check", str(DWG / "panel_sheet.oda_ezdxf.rawdrawing.json")],
    "demo": ["check", "--demo-project", str(ROOT / "tests" / "golden" / "demo_project.json")],
}


def _run(work: Path, inputs: list[str], seed: str, config: Path = CFG) -> Path:
    """One `redline check` in a fresh interpreter, so each run has its own hash seed."""
    work.mkdir(parents=True)
    out = work / "out"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONHASHSEED": seed}
    argv = [*inputs, "--config", str(config), "--out", str(out / "report.html")]
    p = subprocess.run(
        [sys.executable, "-c", _CODE, *argv],
        capture_output=True,
        text=True,
        env=env,
        cwd=work,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    return out


@pytest.mark.parametrize("name", list(INPUTS))
def test_repeat_runs_byte_identical(name, tmp_path):
    a = _run(tmp_path / "a", INPUTS[name], "1")
    b = _run(tmp_path / "b", INPUTS[name], "2")
    for f in ("findings.csv", "report.html"):
        assert (a / f).read_bytes() == (b / f).read_bytes(), f


def test_outputs_hold_no_time_user_or_path(tmp_path):
    out = _run(tmp_path / "w", INPUTS["csv"], "1")
    banned = {
        "user name": getpass.getuser(),
        "repo path": str(ROOT),
        "temp path": tempfile.gettempdir(),
        "today": datetime.date.today().isoformat(),
    }
    for f in ("findings.csv", "report.html"):
        text = (out / f).read_text(encoding="utf-8").lower()
        for what, value in banned.items():
            assert value.lower() not in text, (f, what)
            assert value.lower().replace("\\", "/") not in text, (f, what)


@pytest.mark.live
def test_live_repeat_dwg_findings_identical():
    """The drawing goes through a real extractor twice, on copies in the temp folder."""
    work = Path(tempfile.mkdtemp(prefix="redline-m6-live-"))
    try:
        cfg = work / "config"
        shutil.copytree(ROOT / "config", cfg)
        dwg = work / "in" / "panel_sheet.dwg"
        dwg.parent.mkdir()
        shutil.copy(DWG / "panel_sheet.dwg", dwg)
        outs = []
        for n, seed in enumerate("12"):
            outs.append(_run(work / f"run{n}", ["check", str(dwg)], seed, cfg))
        assert (outs[0] / "findings.csv").read_bytes() == (outs[1] / "findings.csv").read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)
