import re
from pathlib import Path

from redline.cli import main
from redline.config import load_config
from redline.parsers import pdf

ROOT = Path(__file__).resolve().parent.parent
PDFS = ROOT / "samples" / "pdf"
CFG = ROOT / "tests" / "test_config"


def _check(tmp_path, *inputs):
    out = tmp_path / "out" / "r.html"
    code = main(["check", *map(str, inputs), "--config", str(CFG), "--out", str(out)])
    html = out.read_text(encoding="utf-8") if out.exists() else ""
    return code, html


def _section(html, name):
    m = re.search(rf'<section[^>]*id="{name}".*?(?=<section|</body>)', html, re.DOTALL)
    assert m, name
    return m.group(0)


def test_pdf_input_read_by_cli(tmp_path):
    code, html = _check(tmp_path, PDFS / "panel_text.pdf")
    assert code == 0
    assert "LP-21 ckt 9" in html
    assert "not read: unsupported file type" not in html


def test_folder_with_pdf_and_csv(tmp_path):
    code, html = _check(tmp_path, ROOT / "samples" / "csv", PDFS / "panel_text.pdf")
    assert code == 0
    assert "panel_text.pdf" in html and "two_panels.csv" in html


def test_unreadable_pdf_listed(tmp_path):
    bad = tmp_path / "in" / "broken.pdf"
    bad.parent.mkdir()
    bad.write_bytes(b"this is not a pdf")
    code, html = _check(tmp_path, bad, PDFS / "panel_text.pdf")
    assert code == 0
    assert "broken.pdf" in _section(html, "manual-check")
    assert "file not read" in html


def test_pdf_only_unreadable_exits_2(tmp_path, capsys):
    bad = tmp_path / "in" / "broken.pdf"
    bad.parent.mkdir()
    bad.write_bytes(b"this is not a pdf")
    code, _ = _check(tmp_path, bad)
    assert code == 2
    assert "no input file could be read" in capsys.readouterr().err


def test_scanned_only_run_exits_0(tmp_path):
    # a PDF that opens is read, even when every page is routed (CLAUDE.md 6)
    code, html = _check(tmp_path, PDFS / "scanned_panel.pdf")
    assert code == 0
    assert "scanned_panel.pdf" in _section(html, "manual-check")


def test_routed_pages_in_manual_check_with_replot_note(tmp_path):
    code, html = _check(tmp_path, PDFS / "shx_strokes.pdf", PDFS / "scanned_panel.pdf")
    assert code == 0
    sec = _section(html, "manual-check")
    assert "shx_strokes.pdf" in sec and "re-plot with TrueType substitution" in sec
    assert "scanned_panel.pdf" in sec and "needs OCR or vision" in sec


def test_pdf_reader_missing_listed(tmp_path, monkeypatch):
    # the child cannot import the reader: the file is listed with the install hint
    child = "import sys; sys.modules['pdfplumber'] = None; " + pdf._CHILD
    monkeypatch.setattr(pdf, "_CHILD", child)
    assert _check(tmp_path, PDFS / "panel_text.pdf")[0] == 2
    code, html = _check(tmp_path, PDFS / "panel_text.pdf", ROOT / "samples" / "csv")
    assert code == 0
    assert "pip install redline[pdf]" in html
    assert "LP-21 ckt 9" not in html


def test_pdf_provenance_in_footer(tmp_path):
    code, html = _check(tmp_path, PDFS / "panel_text.pdf")
    assert code == 0
    footer = _section(html, "footer")
    assert "panel_text.pdf pdfplumber " in footer and "pdfminer.six " in footer
    sha = pdf.read_pages(PDFS / "panel_text.pdf", load_config(CFG))["sha256"]
    assert f"SHA-256 {sha}" in footer


def test_acad_subfolder_listed_not_read(tmp_path):
    code, html = _check(tmp_path, PDFS)
    assert code == 0
    cov = _section(html, "coverage")
    assert "acad" in cov and "not read: subfolders are not read" in cov
    assert "acad_truetype.pdf" not in html
