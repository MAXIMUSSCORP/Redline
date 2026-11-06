import sys
from pathlib import Path

from redline.cli import main

BLOCKED = (
    "torch",
    "onnxruntime",
    "transformers",
    "ollama",
    "paddleocr",
    "rapidocr_onnxruntime",
    "rfdetr",
    "ezdxf",
)


def test_no_model_import_without_flag(monkeypatch, tmp_path):
    for name in BLOCKED:
        monkeypatch.setitem(sys.modules, name, None)  # any import now raises ImportError
    root = Path(__file__).resolve().parent.parent
    demo = str(root / "tests/golden/demo_project.json")
    cfg = str(root / "tests/test_config")
    assert (
        main(["check", "--demo-project", demo, "--config", cfg, "--out", str(tmp_path / "r.html")])
        == 0
    )
