import copy
import io
import os
import subprocess
import sys
from pathlib import Path

from redline.rawdrawing import read
from redline.tools import xcheck
from redline.tools.xcheck import LossRow, diff, format_table, run

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "dwg"
PLUGIN = read(SAMPLES / "panel_sheet.acad_plugin.rawdrawing.json")
FALLBACK = read(SAMPLES / "panel_sheet.oda_ezdxf.rawdrawing.json")


def rows_by_item(rows):
    return {r.item: r for r in rows}


def evaluated_loads(d):
    lp12 = next(e for e in d["entities"] if e.get("text") == "LP-12")
    return [c["evaluated"] for c in lp12["table"]["cells"] if c["c"] == 2 and c["r"] >= 2]


def fake(d):
    return lambda path, cfg: d


def broken(message):
    def f(path, cfg):
        raise RuntimeError(message)

    return f


def test_diff_counts_by_type():
    rows = rows_by_item(diff("panel_sheet.dwg", PLUGIN, FALLBACK))
    assert (rows["TEXT"].primary, rows["TEXT"].fallback) == (43, 43)
    assert (rows["ACAD_TABLE"].primary, rows["ACAD_TABLE"].fallback) == (3, 3)
    assert (rows["INSERT"].primary, rows["INSERT"].fallback) == (2, 2)
    assert rows["attributes"].primary == 5
    assert rows["cells"].primary == rows["cells"].fallback


def test_diff_field_cells_evaluated_loss():
    rows = rows_by_item(diff("panel_sheet.dwg", PLUGIN, FALLBACK))
    lost = rows["cells evaluated"]
    assert (lost.primary, lost.fallback) == (361, 0)
    assert [evaluated_loads(PLUGIN).count(v) for v in (True, False)] == [6, 0]
    assert [evaluated_loads(FALLBACK).count(v) for v in (True, False)] == [0, 6]


def test_diff_cell_text_differences():
    changed = copy.deepcopy(FALLBACK)
    table = next(e for e in changed["entities"] if e.get("text") == "LP-11")["table"]
    table["cells"][5]["text"] = "changed"
    table["cells"][6]["text"] = "changed too"
    assert rows_by_item(diff("f", PLUGIN, FALLBACK))["cell text differs"].primary == 0
    assert rows_by_item(diff("f", PLUGIN, changed))["cell text differs"].primary == 2
    resized = copy.deepcopy(changed)
    next(e for e in resized["entities"] if e.get("text") == "LP-11")["table"]["rows"] = 99
    assert rows_by_item(diff("f", PLUGIN, resized))["cell text differs"].primary == 0


def test_loss_table_text():
    rows = diff("panel_sheet.dwg", PLUGIN, None)
    text = format_table(rows, ("acad_plugin", "oda_ezdxf"))
    lines = text.splitlines()
    assert lines[0].split() == ["file", "item", "acad_plugin", "oda_ezdxf"]
    assert any(ln.split()[:2] == ["panel_sheet.dwg", "ACAD_TABLE"] for ln in lines)
    assert all(ln.endswith("not run") for ln in lines[1:])
    assert format_table([LossRow("a", "TEXT", 1, 2)]).splitlines()[1].split() == [
        "a",
        "TEXT",
        "1",
        "2",
    ]


def test_run_one_extractor_unavailable_named(test_cfg):
    fns = {"acad_plugin": fake(PLUGIN), "oda_ezdxf": broken("converter missing")}
    text, code = run([Path("panel_sheet.dwg")], test_cfg, fns)
    assert code == 0
    assert "panel_sheet.dwg: oda_ezdxf read nothing: RuntimeError: converter missing" in text
    assert "cell text differs" not in text


def test_run_both_unavailable_raises(test_cfg):
    fns = {"acad_plugin": broken("no host"), "oda_ezdxf": broken("no converter")}
    text, code = run([Path("a.dwg"), Path("b.dwg")], test_cfg, fns)
    assert code == 2
    assert "acad_plugin read nothing" in text and "oda_ezdxf read nothing" in text
    assert run([], test_cfg, fns)[1] == 2


def test_run_two_readable_files(test_cfg):
    fns = {"acad_plugin": fake(PLUGIN), "oda_ezdxf": fake(FALLBACK)}
    text, code = run([Path("one.dwg"), Path("two.dwg")], test_cfg, fns)
    assert code == 0
    assert "one.dwg" in text and "two.dwg" in text


def test_run_default_extractors_are_lazy(test_cfg):
    assert set(xcheck._default_extractors()) == {"acad_plugin", "oda_ezdxf"}
    text, code = run([Path("a.dwg")], test_cfg)
    assert code == 2 and "read nothing" in text


def test_diff_survives_odd_shapes():
    odd = {"entities": [{"type": "ACAD_TABLE", "handle": "1", "table": {"cells": None}}, 5]}
    rows = rows_by_item(diff("f", odd, {"entities": "x"}))
    assert rows["ACAD_TABLE"].primary == 1 and rows["ACAD_TABLE"].fallback == 0


def test_import_loads_no_extractor():
    code = (
        "import sys; import redline.tools.xcheck;"
        "assert not {'ezdxf', 'redline.extract'} & set(sys.modules)"
    )
    env = {**os.environ, "PYTHONPATH": str(SAMPLES.parent.parent / "src")}
    subprocess.run([sys.executable, "-c", code], check=True, env=env)


def _tab(handle, xref, text):
    cells = [{"r": 0, "c": 0, "text": text, "evaluated": True}]
    e = {"type": "ACAD_TABLE", "handle": handle, "table": {"rows": 1, "cols": 1, "cells": cells}}
    return {**e, "xref_path": xref} if xref else e


def test_same_handle_host_and_xref_counted_apart():
    both = {"entities": [_tab("2A", None, "x"), _tab("2A", "A.dwg", "y")]}
    host = {"entities": [_tab("2A", None, "x")]}
    rows = rows_by_item(diff("f", both, host))
    assert (rows["tables"].primary, rows["tables"].fallback) == (2, 1)
    assert rows["cell text differs"].primary == 0


def test_table_size_mismatch_is_named():
    a = {"entities": [_tab("2A", None, "x")]}
    b = copy.deepcopy(a)
    b["entities"][0]["table"]["rows"] = 3
    rows = diff("f.dwg", a, b)
    assert rows_by_item(rows)["cell text differs"].primary == 0
    assert any("size differs" in r.item and "2A" in r.item for r in rows)


def test_xcheck_prints_non_cp1252_name(monkeypatch, test_cfg):
    from redline.cli import main

    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    monkeypatch.setattr(xcheck, "_default_extractors", lambda: {"a": broken("x"), "b": broken("y")})
    rc = main(["xcheck", "ф.dwg", "--config", str(SAMPLES.parent.parent / "tests" / "test_config")])
    sys.stdout.flush()
    assert rc == 2 and b"read nothing" in raw.getvalue()
