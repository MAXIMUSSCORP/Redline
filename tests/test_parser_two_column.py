from pathlib import Path

import pytest
from test_parser_tabular import cfg_with

from redline.model import Confidence, Method, is_mlo
from redline.parsers.csv_xlsx import parse_file
from redline.parsers.tabular import rows_to_panels

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "csv" / "two_column.csv"


@pytest.fixture
def cfg(test_cfg):
    return cfg_with(test_cfg)


def test_circuit_numbers_not_row_order(cfg):
    (panel,) = parse_file(SAMPLE, cfg).panels
    by_text = {c.description.value: c.number for c in panel.circuits}
    # Left numbers run 1, 3, 5, 9, 7, 11 down the page, so row order would give 7 to "Heater".
    assert by_text["Heater"] == "9"
    assert by_text["Receptacles zone 2"] == "7"
    assert by_text["Lighting zone 4"] == "8"
    assert sorted(int(c.number) for c in panel.circuits) == list(range(1, 12))


def test_two_column_split_mirrored(cfg):
    parsed = parse_file(SAMPLE, cfg)
    (panel,) = parsed.panels
    assert panel.name == "LP-3"
    assert len(panel.circuits) == 11
    assert (panel.voltage_v.value, panel.phases.value, is_mlo(panel)) == (208.0, 3, True)
    left = next(c for c in panel.circuits if c.number == "1")
    right = next(c for c in panel.circuits if c.number == "2")
    assert (left.description.value, left.breaker_a.value, left.load_va.value) == (
        "Lighting zone 1",
        20.0,
        1500.0,
    )
    assert (right.description.value, right.breaker_a.value, right.load_va.value) == (
        "Lighting zone 3",
        15.0,
        1100.0,
    )
    assert left.breaker_a.source.locator.endswith("col=Breaker (left)")
    assert right.breaker_a.source.locator.endswith("col=Breaker (right)")
    assert left.source.locator == right.source.locator
    assert parsed.unparsed == []


def test_two_column_split_fails_take_neither(cfg):
    rows = [
        ["Ckt", "Description", "Load VA", "Breaker", "Description", "Load VA"],
        ["1", "a", "100", "20", "b", "200"],
    ]
    parsed = rows_to_panels(
        rows,
        cfg,
        file="t.csv",
        method=Method.CSV,
        locate=lambda i: f"row={i + 1}",
        fallback_panel="LP-1",
    )
    (c,) = parsed.panels[0].circuits
    assert c.breaker_a.value == 20.0
    assert c.description.source is None
    assert c.load_va.source is None
    cols = [u.raw for u in parsed.unparsed if u.kind == "column"]
    assert sorted(cols) == ["Description", "Description", "Load VA", "Load VA"]


def test_two_column_blank_side_skipped(cfg):
    parsed = parse_file(SAMPLE, cfg)
    assert len(parsed.panels[0].circuits) == 11
    assert not [u for u in parsed.unparsed if u.kind == "row"]
    rows = [
        ["Ckt", "Description", "Breaker", "Ckt", "Description", "Breaker"],
        ["1", "a", "20", "2", "", ""],
        ["3", "", "", "", "stray text", ""],
    ]
    out = rows_to_panels(
        rows,
        cfg,
        file="t.csv",
        method=Method.CSV,
        locate=lambda i: f"row={i + 1}",
        fallback_panel="LP-1",
    )
    assert [c.number for c in out.panels[0].circuits] == ["1", "2", "3"]
    (row,) = [u for u in out.unparsed if u.kind == "row"]
    assert (row.raw, row.reason) == ("stray text", "no circuit number")


def test_two_column_detect_off_take_neither(test_cfg):
    cfg = cfg_with(test_cfg, detect=False)
    parsed = parse_file(SAMPLE, cfg)
    (panel,) = parsed.panels
    assert panel.circuits == []
    cols = [u.raw for u in parsed.unparsed if u.kind == "column"]
    assert sorted(cols) == sorted(
        ["Ckt", "Description", "Load (VA)", "Wire", "Breaker", "Poles"] * 2
    )
    rows = [u for u in parsed.unparsed if u.kind == "row"]
    assert len(rows) == 6
    assert all(u.reason == "no circuit number column" for u in rows)
    assert panel.voltage_v.confidence is Confidence.MEDIUM


def test_word_matched_circuit_column_no_two_column_split(cfg):
    rows = [
        ["Panel", "Ckt", "Description", "Circuit Notes", "Load (VA)", "Breaker"],
        ["LP-1", "2", "Pump", "see E-101", "1500", "20"],
    ]
    parsed = rows_to_panels(
        rows, cfg, file="t.csv", method=Method.CSV, locate=lambda i: f"row={i + 1}"
    )
    nums = [c.number for p in parsed.panels for c in p.circuits]
    assert "see E-101" not in nums
