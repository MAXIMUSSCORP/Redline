import json
import shutil
from pathlib import Path

import pytest

from redline.cli import main
from redline.extract import ExtractError, Unavailable, acad_console, oda_ezdxf
from redline.tools import xcheck

ROOT = Path(__file__).resolve().parent.parent
CFG = str(ROOT / "tests" / "test_config")
PLUGIN = ROOT / "samples" / "dwg" / "panel_sheet.acad_plugin.rawdrawing.json"
ODA = ROOT / "samples" / "dwg" / "panel_sheet.oda_ezdxf.rawdrawing.json"
CSV = ROOT / "samples" / "csv" / "two_panels.csv"


def _check(tmp_path, *inputs):
    out = tmp_path / "out" / "report.html"
    rc = main(["check", *map(str, inputs), "--config", CFG, "--out", str(out)])
    return rc, (out.read_text(encoding="utf-8") if out.exists() else "")


def _no_extractor(monkeypatch):
    def gone(path, cfg):
        raise Unavailable("not installed here")

    monkeypatch.setattr(acad_console, "extract", gone)
    monkeypatch.setattr(oda_ezdxf, "extract", gone)


def _dwg(tmp_path, name="panel_sheet.dwg"):
    f = tmp_path / "in" / name
    f.parent.mkdir(exist_ok=True)
    f.write_bytes(b"AC1032 not a real drawing")
    return f


def test_dwg_json_input_read(tmp_path):
    rc, html = _check(tmp_path, PLUGIN)
    assert rc == 0 and "LP-11" in html and "LP-13" in html
    assert (tmp_path / "out" / "findings.csv").exists()


def test_dwg_json_provenance_is_keyed_by_the_file_name(tmp_path):
    rc, html = _check(tmp_path, PLUGIN)
    want = f"{PLUGIN.name} acad_plugin 0.1.0, host synthetic fixture, no host, SHA-256 {'0' * 64}"
    assert rc == 0 and want in html


def test_dwg_without_extractor_listed(tmp_path, monkeypatch):
    _no_extractor(monkeypatch)
    dwg = _dwg(tmp_path)
    rc, html = _check(tmp_path, dwg, CSV)
    assert rc == 0 and "panel_sheet.dwg" in html and "not installed here" in html
    assert "file not read" in html
    rc, _ = _check(tmp_path / "alone", dwg)
    assert rc == 2


def test_folder_with_dwg_and_csv(tmp_path, monkeypatch):
    data = json.loads(PLUGIN.read_text(encoding="utf-8"))
    monkeypatch.setattr(acad_console, "extract", lambda path, cfg: data)
    dwg = _dwg(tmp_path)
    shutil.copy(CSV, dwg.parent / CSV.name)
    rc, html = _check(tmp_path, dwg.parent)
    assert rc == 0 and "LP-11" in html and "LP-1" in html and "LP-2" in html
    assert "panel_sheet.dwg acad_plugin 0.1.0" in html


def test_wdp_input_read(tmp_path):
    wdp = tmp_path / "made_up.wdp"
    wdp.write_text("===Floor one\nplan_01.dwg\n", encoding="utf-8")
    rc, html = _check(tmp_path, wdp)
    assert rc == 0 and "plan_01.dwg listed in project made_up.wdp" in html


def test_mdb_listed_not_read(tmp_path):
    mdb = tmp_path / "project.mdb"
    mdb.write_bytes(b"\x00\x01\x00\x00Standard Jet DB")
    rc, html = _check(tmp_path, mdb, CSV)
    assert rc == 0 and "project.mdb" in html and "unsupported file type" in html
    rc, _ = _check(tmp_path / "alone", mdb)
    assert rc == 2


def test_timeout_becomes_unparsed(tmp_path, monkeypatch):
    def slow(path, cfg):
        raise ExtractError("acad_plugin timed out after 120 s")

    monkeypatch.setattr(acad_console, "extract", slow)
    monkeypatch.setattr(oda_ezdxf, "extract", slow)
    dwg = _dwg(tmp_path)
    rc, html = _check(tmp_path, dwg, CSV)
    assert rc == 0 and "panel_sheet.dwg" in html and "timed out" in html
    rc, _ = _check(tmp_path / "alone", dwg)
    assert rc == 2


def test_invalid_rawdrawing_json_listed(tmp_path):
    bad = tmp_path / "bad.rawdrawing.json"
    bad.write_text('{"schema_version": "1.0"}', encoding="utf-8")
    rc, html = _check(tmp_path, bad, CSV)
    assert rc == 0 and "bad.rawdrawing.json" in html and "not a valid RawDrawing" in html


def test_xcheck_subcommand_prints_table(monkeypatch, capsys):
    a, b = (json.loads(p.read_text(encoding="utf-8")) for p in (PLUGIN, ODA))
    monkeypatch.setattr(
        xcheck,
        "_default_extractors",
        lambda: {"acad_plugin": lambda p, c: a, "oda_ezdxf": lambda p, c: b},
    )
    assert main(["xcheck", "panel_sheet.dwg", "--config", CFG]) == 0
    out = capsys.readouterr().out
    assert "acad_plugin" in out and "oda_ezdxf" in out and "cells evaluated" in out


def test_xcheck_no_extractor_exits_2(tmp_path, monkeypatch, capsys):
    _no_extractor(monkeypatch)
    assert main(["xcheck", str(_dwg(tmp_path)), "--config", CFG]) == 2
    assert "not installed here" in capsys.readouterr().out


def test_xcheck_config_failure_exits_2(tmp_path, capsys):
    assert main(["xcheck", "x.dwg", "--config", str(tmp_path)]) == 2
    assert "config error" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["PANEL.DWG", "Plan.Dxf"])
def test_dwg_suffix_case_is_routed(tmp_path, monkeypatch, name):
    _no_extractor(monkeypatch)
    rc, html = _check(tmp_path, _dwg(tmp_path, name), CSV)
    assert rc == 0 and "file not read" in html and "unsupported file type" not in html
