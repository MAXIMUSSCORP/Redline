import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BLOCKED = (
    "torch",
    "onnxruntime",
    "transformers",
    "ollama",
    "paddleocr",
    "rapidocr_onnxruntime",
    "rfdetr",
    "ezdxf",
    "pdfplumber",
    "pdfminer",
    "pypdfium2",
    "socket",
    "ssl",
    "urllib.request",
    "http.client",
    "requests",
    "httpx",
)

_CODE = """
import json, sys
from redline.cli import main
code = main(["check", "--demo-project", sys.argv[1], "--config", sys.argv[2], "--out", sys.argv[3]])
print(json.dumps({"code": code, "seen": [m for m in json.loads(sys.argv[4]) if m in sys.modules]}))
"""


def _seen(tmp_path, blocked):
    """Run the demo check in a fresh interpreter. Return (exit code, blocked modules imported)."""
    args = [
        str(ROOT / "tests/golden/demo_project.json"),
        str(ROOT / "tests/test_config"),
        str(tmp_path / "r.html"),
        json.dumps(list(blocked)),
    ]
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")}
    p = subprocess.run(
        [sys.executable, "-c", _CODE, *args], capture_output=True, text=True, env=env, check=True
    )
    out = json.loads(p.stdout.strip().splitlines()[-1])
    return out["code"], out["seen"]


def test_no_model_import_without_flag(tmp_path):
    code, seen = _seen(tmp_path, BLOCKED)
    assert code == 0
    assert seen == []


def test_no_model_import_guard_detects_import(tmp_path):
    code, seen = _seen(tmp_path, ("yaml",))
    assert code == 0
    assert "yaml" in seen


_CSV_CODE = """
import json, sys
from redline.cli import main
code = main(["check", sys.argv[1], "--config", sys.argv[2], "--out", sys.argv[3]])
print(json.dumps({"code": code, "seen": [m for m in json.loads(sys.argv[4]) if m in sys.modules]}))
"""


def test_csv_run_imports_no_model(tmp_path):
    args = [
        str(ROOT / "samples/csv"),
        str(ROOT / "tests/test_config"),
        str(tmp_path / "r.html"),
        json.dumps(list(BLOCKED)),
    ]
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")}
    p = subprocess.run(
        [sys.executable, "-c", _CSV_CODE, *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out == {"code": 0, "seen": []}


def test_dwg_json_run_imports_no_model(tmp_path):
    args = [
        str(ROOT / "samples/dwg/panel_sheet.acad_plugin.rawdrawing.json"),
        str(ROOT / "tests/test_config"),
        str(tmp_path / "r.html"),
        json.dumps(list(BLOCKED)),
    ]
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")}
    p = subprocess.run(
        [sys.executable, "-c", _CSV_CODE, *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out == {"code": 0, "seen": []}


def test_pdf_run_imports_no_model(tmp_path):
    # the PDF reader runs in a child process, so the parent imports none of the PDF libraries
    args = [
        str(ROOT / "samples/pdf"),
        str(ROOT / "tests/test_config"),
        str(tmp_path / "r.html"),
        json.dumps(list(BLOCKED)),
    ]
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")}
    p = subprocess.run(
        [sys.executable, "-c", _CSV_CODE, *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out == {"code": 0, "seen": []}


def test_plans_run_imports_no_model(tmp_path):
    # The parent checks ezdxf with find_spec (C20), so nothing in BLOCKED loads.
    blocked = list(BLOCKED)
    args = [
        str(ROOT / "samples/plans"),
        str(ROOT / "tests/test_config"),
        str(tmp_path / "r.html"),
        json.dumps(blocked),
    ]
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")}
    p = subprocess.run(
        [sys.executable, "-c", _CSV_CODE, *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out == {"code": 0, "seen": []}
