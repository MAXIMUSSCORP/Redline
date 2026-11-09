import copy
import time
from dataclasses import replace

import pytest

from redline.model import Confidence, Method, is_mlo
from redline.parsers.tabular import normalize_header, rows_to_panels

# A fixed copy of the first alias map, so these tests hold when the shipped map grows.
M0_SCHEDULE = {
    "panel_name": ["panel", "panel name", "panel id", "pnl"],
    "circuit_number": ["ckt", "cct", "circuit", "circuit no", "circuit #"],
    "poles": ["poles", "pole", "p"],
    "breaker_a": ["breaker", "bkr", "trip", "amps", "ocpd"],
    "conductor_size": ["wire", "wire size", "conductor", "cable"],
    "conductor_material": ["material", "cu/al"],
    "insulation_temp_c": ["insulation", "temp rating", "wire temp"],
    "length_m": ["length", "run length", "distance"],
    "load_va": ["load", "load va", "connected load", "va"],
    "load_kva": ["kva", "load kva"],
    "load_type": ["load type", "type", "continuous"],
    "description": ["description", "load description", "served", "desc"],
    "phase": ["phase", "ph"],
}


def cfg_with(cfg, schedule=None, detect=None):
    maps = copy.deepcopy(cfg.column_maps)
    maps["csv_panel_schedule"] = copy.deepcopy(schedule or M0_SCHEDULE)
    if detect is not None:
        maps["two_column_layout"]["detect_when_headers_repeat"] = detect
    return replace(cfg, column_maps=maps)


def parse(rows, cfg, **kw):
    return rows_to_panels(
        rows, cfg, file="t.csv", method=Method.CSV, locate=lambda i: f"row={i + 1}", **kw
    )


HEAD = ["Panel", "Ckt", "Description", "Load VA", "Breaker", "Wire", "Poles"]


@pytest.fixture
def cfg(test_cfg):
    return cfg_with(test_cfg)


def cell(cfg, header, text):
    """One circuit whose only unknown is the cell under test."""
    rows = [["Panel", "Ckt", "Description", header], ["LP-1", "1", "d", text]]
    parsed = parse(rows, cfg)
    return parsed, parsed.panels[0].circuits[0]


def test_normalize_header_lowers_and_collapses():
    assert normalize_header("  Wire\tSz. ") == "wire sz"
    assert normalize_header("Load (VA)") == "load va"
    assert normalize_header("Circuit #") == "circuit"


def test_exact_alias_is_high(cfg):
    _, c = cell(cfg, "Breaker", "20")
    assert c.breaker_a.value == 20.0
    assert c.breaker_a.confidence is Confidence.HIGH
    assert c.source.confidence is Confidence.HIGH


def test_token_set_unique_is_medium(cfg):
    _, c = cell(cfg, "Breaker Rating", "20")
    assert c.breaker_a.value == 20.0
    assert c.breaker_a.confidence is Confidence.MEDIUM
    assert "'breaker'" in c.breaker_a.source.note


def test_token_set_ambiguous_unparsed(cfg):
    parsed, c = cell(cfg, "Wire Load", "12 AWG")
    (col,) = [u for u in parsed.unparsed if u.kind == "column"]
    assert col.raw == "Wire Load"
    assert "more than one field" in col.reason
    assert c.conductor_size.source is None
    assert c.load_va.source is None


def test_two_columns_one_field_take_neither(test_cfg):
    rows = [
        ["Panel", "Ckt", "Description", "Breaker", "Bkr"],
        ["LP-1", "1", "d", "20", "15"],
    ]
    for detect in (False, True):
        parsed = parse(rows, cfg_with(test_cfg, detect=detect))
        cols = {u.raw: u.reason for u in parsed.unparsed if u.kind == "column"}
        assert set(cols) == {"Breaker", "Bkr"}
        assert all("'Breaker' and 'Bkr'" in r for r in cols.values())
        assert parsed.panels[0].circuits[0].breaker_a.source is None


def test_load_va_wins_over_kva_column(cfg):
    rows = [
        ["Panel", "Ckt", "Description", "Load VA", "kVA"],
        ["LP-1", "1", "d", "1500", "9"],
    ]
    parsed = parse(rows, cfg)
    assert parsed.panels[0].circuits[0].load_va.value == 1500.0
    (col,) = [u for u in parsed.unparsed if u.kind == "column"]
    assert (col.raw, col.reason) == ("kVA", "load already read from Load VA")


def test_unknown_key_unparsed(test_cfg):
    cfg = cfg_with(test_cfg, schedule={**M0_SCHEDULE, "bogus": ["zeta"]})
    parsed, _ = cell(cfg, "Zeta", "5")
    (col,) = [u for u in parsed.unparsed if u.kind == "column"]
    assert col.raw == "Zeta"
    assert "key bogus is not a known field" in col.reason


def test_bad_number_is_low(cfg):
    _, c = cell(cfg, "Breaker", "abc")
    assert c.breaker_a.value is None
    assert c.breaker_a.confidence is Confidence.LOW
    assert c.breaker_a.raw == "abc"
    _, c = cell(cfg, "Breaker", "1,80")
    assert c.breaker_a.confidence is Confidence.LOW
    assert "thousands" in c.breaker_a.source.note


def test_placeholder_is_low(cfg):
    _, c = cell(cfg, "Load VA", "tbd")
    assert (c.load_va.value, c.load_va.confidence) == (None, Confidence.LOW)
    assert c.load_va.source.note == "placeholder text"
    assert c.load_va.raw == "tbd"


def test_blank_cell_is_missing(cfg):
    _, c = cell(cfg, "Breaker", "")
    assert c.breaker_a.value is None
    assert c.breaker_a.confidence is Confidence.MISSING
    assert c.breaker_a.source.note == "blank cell"
    assert c.breaker_a.raw == ""
    assert c.breaker_a.source.locator == "row=2; col=Breaker"


def test_unit_suffix_read(cfg):
    assert cell(cfg, "Breaker", "20 A")[1].breaker_a.value == 20.0
    assert cell(cfg, "Breaker", "20a")[1].breaker_a.value == 20.0
    assert cell(cfg, "Length", "30 m")[1].length_m.value == 30.0
    assert cell(cfg, "Insulation", "75 C")[1].insulation_temp_c.value == 75
    assert cell(cfg, "Insulation", "75°C")[1].insulation_temp_c.value == 75
    assert cell(cfg, "Load VA", "1800 VA")[1].load_va.value == 1800.0


def test_wrong_unit_is_low(cfg):
    _, c = cell(cfg, "Length", "30 ft")
    assert (c.length_m.value, c.length_m.confidence) == (None, Confidence.LOW)
    assert c.length_m.source.note == "unit ft not read"
    assert c.length_m.raw == "30 ft"


def test_thousands_separator(cfg):
    _, c = cell(cfg, "Load VA", "1,800")
    assert (c.load_va.value, c.load_va.confidence) == (1800.0, Confidence.HIGH)
    assert cell(cfg, "Load VA", "12,34")[1].load_va.confidence is Confidence.LOW


def test_kva_is_derived(cfg):
    _, c = cell(cfg, "Load VA", "1.8 kVA")
    assert c.load_va.value == 1800.0
    assert c.load_va.source.method is Method.DERIVED
    assert c.load_va.raw == "1.8 kVA"
    _, c = cell(cfg, "kVA", "2.5")
    assert (c.load_va.value, c.load_va.source.method) == (2500.0, Method.DERIVED)


def test_kw_needs_power_factor(cfg, cfg_set):
    _, c = cell(cfg, "Load VA", "2 kW")
    assert c.load_va.value == 2000.0
    assert c.load_va.source.method is Method.DERIVED
    assert c.load_va.confidence is Confidence.MEDIUM
    no_pf = cfg_set(cfg, ("defaults", "power_factor"), None)
    _, c = cell(no_pf, "Load VA", "2 kW")
    assert (c.load_va.value, c.load_va.confidence) == (None, Confidence.LOW)
    assert "power factor" in c.load_va.source.note
    assert c.load_va.raw == "2 kW"


def test_slash_voltage(test_cfg):
    cfg = cfg_with(test_cfg, schedule={**M0_SCHEDULE, "voltage_v": ["voltage"]})
    rows = [
        ["Panel", "LP-3"],
        ["Voltage", "120/208"],
        ["Ckt", "Description", "Breaker"],
        ["1", "a", "20"],
    ]
    (panel,) = parse(rows, cfg).panels
    assert panel.voltage_v.value == 208.0
    assert panel.voltage_v.confidence is Confidence.MEDIUM
    assert panel.voltage_v.source.note == "line-to-line from a/b"
    assert cell(cfg, "Voltage", "120 V")[1].voltage_v.value == 120.0


def test_mlo_main_breaker(cfg):
    rows = [["Panel", "LP-3"], ["Main", "MLO"], ["Ckt", "Description", "Breaker"], ["1", "a", "20"]]
    (panel,) = parse(rows, cfg).panels
    assert is_mlo(panel)
    assert panel.main_breaker_a.raw == "MLO"
    rows[1] = ["Main", "100 A"]
    (panel,) = parse(rows, cfg).panels
    assert (panel.main_breaker_a.value, is_mlo(panel)) == (100.0, False)


def test_check_value_applied(cfg):
    _, c = cell(cfg, "Poles", "5")
    assert (c.poles.value, c.poles.confidence) == (5, Confidence.LOW)
    assert "poles not 1, 2 or 3" in c.poles.source.note
    _, c = cell(cfg, "Load Type", "Widget")
    assert c.load_type.value == "widget"
    assert c.load_type.confidence is Confidence.LOW
    assert cell(cfg, "Load Type", "Continuous")[1].load_type.confidence is Confidence.HIGH


def test_bare_wire_size_is_low(cfg):
    assert cell(cfg, "Wire", "12")[1].conductor_size.confidence is Confidence.LOW
    _, c = cell(cfg, "Wire", "#12")
    assert (c.conductor_size.value, c.conductor_size.confidence) == ("12 AWG", Confidence.HIGH)


def test_material_and_phase_text_fields(cfg):
    assert cell(cfg, "Material", "copper")[1].conductor_material.value == "Cu"
    assert cell(cfg, "Material", "Aluminium")[1].conductor_material.value == "Al"
    assert cell(cfg, "Material", "steel")[1].conductor_material.confidence is Confidence.LOW
    assert cell(cfg, "Phase", "A-B")[1].phases_used.value == "AB"
    assert cell(cfg, "Phase", "X")[1].phases_used.confidence is Confidence.LOW


def test_integer_field_refuses_a_fraction(cfg):
    _, c = cell(cfg, "Poles", "2.5")
    assert (c.poles.value, c.poles.confidence) == (None, Confidence.LOW)
    assert cell(cfg, "Poles", "2.0")[1].poles.value == 2


def test_spare_keyword_whole_cell(cfg):
    rows = [HEAD] + [
        ["LP-1", str(i), d, "", "", "", ""]
        for i, d in enumerate(["SPARE", "space", "Spare room lights", "  Spare  "], 1)
    ]
    flags = [c.is_spare for c in parse(rows, cfg).panels[0].circuits]
    assert flags == [True, True, False, True]


def test_spare_load_type(cfg):
    rows = [["Panel", "Ckt", "Description", "Load Type"], ["LP-1", "1", "unused", "spare"]]
    assert parse(rows, cfg).panels[0].circuits[0].is_spare is True
    rows[1][3] = "motor"
    assert parse(rows, cfg).panels[0].circuits[0].is_spare is False


def test_header_block_names_panel(cfg):
    rows = [
        ["Panel", "LP-3"],
        ["Voltage", "120/208"],
        ["Phases", "3"],
        [],
        ["Ckt", "Description", "Breaker"],
        ["1", "a", "20"],
    ]
    parsed = parse(rows, cfg)
    (panel,) = parsed.panels
    assert panel.name == "LP-3"
    assert panel.source.confidence is Confidence.HIGH
    assert panel.source.locator == "row=1"
    assert (panel.voltage_v.value, panel.phases.value) == (208.0, 3)
    assert panel.circuits[0].panel == "LP-3"
    assert parsed.unparsed == []


def test_header_block_colon_pair(cfg):
    rows = [["Panel: LP-9"], ["Ckt", "Description", "Breaker"], ["1", "a", "20"]]
    assert parse(rows, cfg).panels[0].name == "LP-9"


def test_fallback_panel_is_medium(cfg):
    rows = [["Ckt", "Description", "Breaker"], ["1", "a", "20"]]
    (panel,) = parse(rows, cfg, fallback_panel="Sheet A").panels
    assert panel.name == "Sheet A"
    assert panel.source.confidence is Confidence.MEDIUM
    assert panel.source.note == "panel name from sheet name"


def test_no_panel_name_rows_unparsed(cfg):
    rows = [["Ckt", "Description", "Breaker"], ["1", "a", "20"], ["2", "b", "20"]]
    parsed = parse(rows, cfg)
    assert parsed.panels == []
    assert [(u.kind, u.reason) for u in parsed.unparsed] == [("row", "no panel name")] * 2


def test_multi_panel_split(cfg):
    rows = [
        HEAD,
        ["LP-2", "1", "a", "", "", "", ""],
        ["LP-1", "1", "b", "", "", "", ""],
        ["LP-2", "2", "c", "", "", "", ""],
        ["", "3", "d", "", "", "", ""],
    ]
    parsed = parse(rows, cfg)
    assert [(p.name, [c.number for c in p.circuits]) for p in parsed.panels] == [
        ("LP-2", ["1", "2"]),
        ("LP-1", ["1"]),
    ]
    (row,) = [u for u in parsed.unparsed if u.kind == "row"]
    assert row.reason == "no panel name"
    assert row.source.locator == "row=5"


def test_stacked_tables_split(cfg):
    head = ["Ckt", "Description", "Breaker"]
    rows = [
        ["Panel", "LP-A"],
        head,
        ["1", "a", "20"],
        ["2", "b", "20"],
        [""],
        ["Panel", "LP-B"],
        head,
        ["1", "c", "15"],
    ]
    parsed = parse(rows, cfg)
    assert [(p.name, [c.number for c in p.circuits]) for p in parsed.panels] == [
        ("LP-A", ["1", "2"]),
        ("LP-B", ["1"]),
    ]
    assert parsed.panels[1].circuits[0].breaker_a.value == 15.0
    assert parsed.unparsed == []


def test_row_without_circuit_number_unparsed(cfg):
    rows = [HEAD, ["LP-1", "1", "a", "", "", "", ""], ["LP-1", "", "TOTAL", "5000", "", "", ""]]
    parsed = parse(rows, cfg)
    assert len(parsed.panels[0].circuits) == 1
    (row,) = [u for u in parsed.unparsed if u.kind == "row"]
    assert (row.reason, row.source.locator) == ("no circuit number", "row=3")
    assert "TOTAL" in row.raw


def test_title_rows_unparsed(cfg):
    rows = [["Electrical Circuits Schedule"], [""], HEAD, ["LP-1", "1", "a", "", "", "", ""]]
    parsed = parse(rows, cfg)
    (row,) = [u for u in parsed.unparsed if u.kind == "row"]
    assert (row.raw, row.source.locator) == ("Electrical Circuits Schedule", "row=1")
    assert len(parsed.panels[0].circuits) == 1


def test_repeated_header_row(cfg):
    rows = [
        HEAD,
        ["LP-1", "1", "a", "", "", "", ""],
        ["LP-1", "2", "b", "", "", "", ""],
        HEAD,
        ["LP-1", "3", "c", "", "", "", ""],
    ]
    parsed = parse(rows, cfg)
    assert [[c.number for c in p.circuits] for p in parsed.panels] == [["1", "2"], ["3"]]
    assert parsed.unparsed == []


def test_coverage_entry_per_panel(cfg):
    rows = [
        HEAD,
        ["LP-1", "1", "a", "100", "20", "12 AWG", "1"],
        ["LP-1", "2", "b", "", "20", "12", "1"],
        ["LP-2", "1", "c", "100", "20", "12 AWG", "1"],
    ]
    parsed = parse(rows, cfg)
    assert [c.unit for c in parsed.coverage] == ["LP-1", "LP-2"]
    first = parsed.coverage[0]
    assert first.file == "t.csv"
    assert first.method == "csv"
    assert first.what_read.startswith("2 circuits read; 7 of 7 columns mapped")
    assert first.confidence_summary == "HIGH 8, MEDIUM 0, LOW 1, MISSING 1"


def test_no_header_row_gives_table_and_columns(cfg):
    parsed = parse([[], ["alpha", "", "beta"], ["1", "2", "3"]], cfg)
    assert parsed.panels == []
    kinds = [(u.kind, u.raw) for u in parsed.unparsed]
    assert kinds == [("table", "alpha, beta"), ("column", "alpha"), ("column", "beta")]


def test_blank_header_over_data_is_unparsed(cfg):
    rows = [["Panel", "Ckt", "Description", "", ""], ["LP-1", "1", "a", "x", ""]]
    parsed = parse(rows, cfg)
    (col,) = [u for u in parsed.unparsed if u.kind == "column"]
    assert (col.raw, col.source.locator) == ("", "row=1; col=#4")


def test_ragged_and_none_cells_do_not_raise(cfg):
    rows = [["Panel", "Ckt", "Description", "Breaker"], ["LP-1", "1"], ["LP-1", "2", None, 20]]
    circuits = parse(rows, cfg).panels[0].circuits
    assert circuits[0].breaker_a.confidence is Confidence.MISSING
    assert circuits[1].breaker_a.value == 20.0


def _hdr_cell(cfg, header, text):
    return cell(cfg, header, text)[1]


def test_header_unit_kw_not_read_as_va(cfg):
    c = _hdr_cell(cfg, "Load (kW)", "2.3")
    assert c.load_va.value is None
    assert c.load_va.confidence == Confidence.LOW
    assert "header unit KW not read" in c.load_va.source.note
    ok = _hdr_cell(cfg, "Load (kVA)", "2.3")
    assert ok.load_va.value == pytest.approx(2300.0)


def test_header_unit_ft_not_read_as_m(cfg):
    for header, fld in (("Length (ft)", "length_m"), ("Ambient (F)", "ambient_c")):
        sched = {**M0_SCHEDULE, "ambient_c": ["ambient"]}
        rows = [["Panel", "Ckt", "Description", header], ["LP-1", "1", "d", "30"]]
        v = getattr(parse(rows, cfg_with(cfg, sched)).panels[0].circuits[0], fld)
        assert v.value is None and v.confidence == Confidence.LOW
        assert "not read" in v.source.note


def test_data_row_with_alias_words_is_not_a_header(cfg):
    rows = [
        HEAD,
        ["LP-1", "1", "Lights", "1000", "20", "12", "1"],
        ["LP-1", "2", "Load bank", "1000", "continuous", "20", "breaker locked"],
        ["LP-1", "3", "Pump", "1000", "20", "12", "1"],
    ]
    parsed = parse(rows, cfg)
    nums = [c.number for p in parsed.panels for c in p.circuits]
    assert nums == ["1", "2", "3"]


def test_panel_name_like_block_key_keeps_table_rows(cfg):
    head = ["Panel", "Ckt", "Description", "Load VA", "Breaker"]
    rows = [
        head,
        ["Panel A", "1", "a", "100", "20"],
        ["Panel A", "3", "c", "100", "20"],
        head,
        ["Panel A", "2", "b", "100", "20"],
    ]
    parsed = parse(rows, cfg)
    nums = sorted(c.number for p in parsed.panels for c in p.circuits)
    assert nums == ["1", "2", "3"]


def test_ab_voltage_one_pole_circuit_not_line_to_line(cfg):
    sched = {**M0_SCHEDULE, "voltage_v": ["voltage", "volts"]}
    rows = [["Panel", "Ckt", "Description", "Voltage"], ["LP-1", "1", "d", "120/208"]]
    v = parse(rows, cfg_with(cfg, sched)).panels[0].circuits[0].voltage_v
    assert v.value is None and v.confidence == Confidence.LOW
    assert "a/b voltage" in v.source.note


def test_block_panel_name_with_panel_column_listed(cfg):
    rows = [
        ["Panel", "LP-9"],
        ["Voltage", "208"],
        ["Panel", "Ckt", "Description", "Load VA"],
        ["LP-1", "1", "d", "100"],
    ]
    parsed = parse(rows, cfg)
    assert any("panel name in header block not used" in u.reason for u in parsed.unparsed)
    assert [p.name for p in parsed.panels] == ["LP-1"]


def test_unicode_digits_are_low(cfg):
    assert _hdr_cell(cfg, "Load VA", "١٢").load_va.value is None
    assert _hdr_cell(cfg, "Load VA", "١٢").load_va.confidence == Confidence.LOW
    c = _hdr_cell(cfg, "Poles", "１")
    assert c.poles.value is None and c.poles.confidence == Confidence.LOW


def test_tabular_wide_row_stays_linear(cfg):
    import time

    rows = [["panel", "ckt", "breaker", "load va", "description"]]
    rows.append(["LP-1", "0", "20", "100", "x"] + [""] * 99995 + ["wide"])
    rows += [["LP-1", str(i), "20", "100", "d"] for i in range(1, 4001)]
    t0 = time.perf_counter()
    parsed = parse(rows, cfg)
    assert time.perf_counter() - t0 < 5
    assert len(parsed.panels[0].circuits) == 4001


def test_later_table_without_circuit_column_stays_separate(cfg):
    rows = [
        ["Panel", "Ckt", "Description", "Load VA", "Breaker"],
        ["LP-1", "1", "Lights", "1000", "20"],
        [],
        ["Panel", "Description", "Load VA", "Breaker"],
        ["LP-2", "Heater", "3000", "30"],
    ]
    parsed = parse(rows, cfg)
    assert [p.name for p in parsed.panels] == ["LP-1"]
    circuits = parsed.panels[0].circuits
    assert [c.number for c in circuits] == ["1"]
    assert circuits[0].load_va.value == 1000.0 and circuits[0].breaker_a.value == 20.0
    assert any("Heater" in u.raw for u in parsed.unparsed)


def test_header_unit_amps_not_read_as_va(cfg):
    sched = {**M0_SCHEDULE, "voltage_v": ["voltage"]}
    for header, fld in (
        ("Load (A)", "load_va"),
        ("Load (MVA)", "load_va"),
        ("Breaker (kA)", "breaker_a"),
        ("Voltage (kV)", "voltage_v"),
    ):
        rows = [["Panel", "Ckt", "Description", header], ["LP-1", "1", "d", "22"]]
        v = getattr(parse(rows, cfg_with(cfg, sched)).panels[0].circuits[0], fld)
        assert v.value is None and v.confidence == Confidence.LOW, header
        assert "header unit" in v.source.note, header


def test_header_unit_own_unit_still_read(cfg):
    sched = {
        **M0_SCHEDULE,
        "voltage_v": ["voltage"],
        "ambient_c": ["ambient"],
    }
    for header, fld, text, want in (
        ("Breaker (A)", "breaker_a", "20", 20.0),
        ("Voltage (V)", "voltage_v", "208", 208.0),
        ("Length (m)", "length_m", "30", 30.0),
        ("Ambient (C)", "ambient_c", "30", 30),
        ("Load (VA)", "load_va", "1000", 1000.0),
        ("Load (kVA)", "load_va", "1.5", 1500.0),
    ):
        rows = [["Panel", "Ckt", "Description", header], ["LP-1", "1", "d", text]]
        v = getattr(parse(rows, cfg_with(cfg, sched)).panels[0].circuits[0], fld)
        assert v.value == pytest.approx(want), header
        assert v.confidence != Confidence.LOW, header


def test_word_matched_block_line_not_a_circuit(cfg):
    head = ["Panel", "Ckt", "Description", "Load VA", "Breaker"]
    rows = [
        head,
        ["LP-1", "1", "a", "100", "20"],
        ["Bus Rating (A)", "225"],
        head,
        ["LP-2", "1", "b", "100", "20"],
    ]
    parsed = parse(rows, cfg)
    assert sorted(p.name for p in parsed.panels) == ["LP-1", "LP-2"]
    assert all(c.number == "1" for p in parsed.panels for c in p.circuits)


def test_word_matched_description_last_row_stays_circuit(cfg):
    head = ["Description", "Ckt", "Breaker", "Poles"]
    for desc, tail in (("Panel LP-2 feeder", "3"), ("Main lobby lights", "3")):
        rows = [
            ["Panel", "LP-1"],
            head,
            ["Lights", "1", "20", "1"],
            [desc, tail],
            [],
            ["Panel", "LP-2"],
            head,
            ["Recep", "1", "20", "1"],
        ]
        by = {p.name: p for p in parse(rows, cfg).panels}
        assert sorted(by) == ["LP-1", "LP-2"], desc
        assert [c.number for c in by["LP-1"].circuits] == ["1", "3"], desc
        assert [c.number for c in by["LP-2"].circuits] == ["1"], desc
        assert by["LP-2"].main_breaker_a.value is None, desc


_DESC_FIRST = ["Description", "Ckt", "Breaker", "Poles"]


@pytest.mark.parametrize("line", [["Main Bkr (A)", "100"], ["Bus Rating (A)", "225"]])
def test_word_matched_block_line_after_exact_panel_line_desc_first(cfg, line):
    h = _DESC_FIRST
    rows = [
        ["Panel", "LP-1"],
        h,
        ["Lights", "1", "20", "1"],
        [],
        ["Panel", "LP-2"],
        line,
        h,
        ["Recep", "1", "20", "1"],
    ]
    parsed = parse(rows, cfg)
    by = {p.name: p for p in parsed.panels}
    assert [c.number for c in by["LP-1"].circuits] == ["1"]
    assert [c.number for c in by["LP-2"].circuits] == ["1"]
    p2 = by["LP-2"]
    assert 100 in (p2.main_breaker_a.value, p2.bus_rating_a.value) or 225 in (
        p2.main_breaker_a.value,
        p2.bus_rating_a.value,
    )
    assert not [u for u in parsed.unparsed if "no panel name" in u.reason]


def test_csv_wide_header_with_many_rows_parses_in_linear_time(cfg):
    import time

    wide = ["Ckt", "Description", "Breaker"] + [""] * 99997 + ["wide"]
    for body in (["x", "y", "z"], ["1", "d", "20"]):
        rows = [wide] + [list(body) for _ in range(5000)] + [wide]
        t0 = time.perf_counter()
        parse(rows, cfg)
        assert time.perf_counter() - t0 < 5


# Layout corpus (RV36). Every table shape a review round found, pinned to its expected panels,
# circuits, header-block values and unparsed rows. A change to the header or block-line
# heuristic that breaks an earlier shape fails here. "residual" ids pin an accepted limit.
_D = "Description,Ckt,Breaker,Poles"
_P = "Panel,Ckt,Description,Breaker"
_H = "Ckt,Description,Breaker,Poles"
_H = "Ckt,Description,Breaker,Poles"
_AMB = "panel row or header block line; not read"
LAYOUTS = [
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "Panel LP-2 feeder,3",
            "",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [],
        id="two_csv_description_last_row_block_words",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "Main lobby lights,3",
            "",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [],
        id="two_b_csv_main_lobby_lights_last_row",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "",
            "Panel,LP-2",
            "Bus Rating (A),225",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {"bus": 225.0})],
        [],
        id="A_panel_then_word_bus_line",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "",
            "Bus Rating (A),225",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1", "225"], {}), ("LP-2", ["1"], {})],
        [],
        id="B_residual_word_bus_line_above_panel_reads_as_circuit",
    ),
    pytest.param(
        ["Panel,LP-1", _D, "Lights,1,20,1", "", "Panel,LP-2", "Bus Rating,225", _D, "Recep,1,20,1"],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {"bus": 225.0})],
        [],
        id="C_exact_bus_line_after_panel",
    ),
    pytest.param(
        ["Panel,LP-1", _D, "Lights,1,20,1", "Main: 100", "Panel,LP-2", _D, "Recep,1,20,1"],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {"main": 100.0})],
        [],
        id="D_main_colon_between",
    ),
    pytest.param(
        ["Panel,LP-1", _D, "Lights,1,20,1", "Panel,LP-2", "Main Bkr (A),100", _D, "Recep,1,20,1"],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {"main": 100.0})],
        [],
        id="E_main_bkr_word_after_panel_no_gap",
    ),
    pytest.param(
        [_P, "LP-1,1,a,20", "Bus Rating (A),225,A", _P, "LP-2,1,b,20"],
        [("LP-1", ["1"], {}), ("Bus Rating (A)", ["225"], {}), ("LP-2", ["1"], {})],
        [],
        id="F_residual_three_cell_block_line_makes_panel",
    ),
    pytest.param(
        [_P, "Panel A,1,a,20", "Panel A,2", _P, "Panel B,1,b,20"],
        [("Panel A", ["1"], {}), ("Panel B", ["1"], {})],
        [("2", "panel name in header block not used; table has a panel column")],
        id="G_residual_panel_column_word_name_short_last_row_unparsed",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Ckt,Description,Breaker,Poles",
            "1,Lights,20,1",
            "3,Panel LP-2 feeder",
            "",
            "Panel,LP-2",
            "Ckt,Description,Breaker,Poles",
            "1,x,20,1",
        ],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [],
        id="H_ckt_first_last_row_block_words",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            ",,,,Bus Rating (A),225",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {"bus": 225.0})],
        [],
        id="I_block_words_beyond_header_first_cell",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "Main lobby: lights,3",
            "Recep,5,20,1",
            "",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1", "3", "5"], {}), ("LP-2", ["1"], {})],
        [],
        id="J_colon_description_mid_table_two_cells",
    ),
    pytest.param(
        ["Panel,LP-1", _D, "Lights,1,20,1", "Main lobby: lights,3", "Recep,5,20,1"],
        [("LP-1", ["1", "3", "5"], {})],
        [],
        id="J0_colon_description_single_table",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "Room 101: recep,3",
            "Recep,5,20,1",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1", "3", "5"], {}), ("LP-2", ["1"], {})],
        [],
        id="K_room_colon_mid_table",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "Note: spare,3",
            "Recep,5,20,1",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1", "3", "5"], {}), ("LP-2", ["1"], {})],
        [],
        id="L_note_colon_mid_table",
    ),
    pytest.param(
        [_P, "MAIN,1,a,20", "MAIN,2", "MAIN,3,c,20", _P, "LP-2,1,b,20"],
        [("MAIN", ["1", "2", "3"], {}), ("LP-2", ["1"], {})],
        [],
        id="M_panel_column_MAIN_short_row",
    ),
    pytest.param(
        ["Panel,LP-1", _D, "Lights,1,20,1", "Recep,3,20,1", _D, "Fan,5,20,1"],
        [("LP-1", ["1", "3"], {}), ("LP-1", ["5"], {})],
        [],
        id="N_repeated_header_page_break_without_panel_column",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "Location,3",
            "Recep,5,20,1",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1", "3", "5"], {}), ("LP-2", ["1"], {})],
        [],
        id="O_exact_key_description_mid_table",
    ),
    pytest.param(
        [_P, "MAIN,1,a,20", "MAIN,3,c,20", _P, "LP-2,1,b,20"],
        [("MAIN", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [],
        id="M2_panel_column_MAIN_no_short_row",
    ),
    pytest.param(
        [_P, "LP-2,1,b,20", _P, "MAIN,1,a,20", "MAIN,3,c,20"],
        [("LP-2", ["1"], {}), ("MAIN", ["1", "3"], {})],
        [],
        id="M3_panel_column_MAIN_second_table",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Voltage,208",
            "Phases,3",
            "Bus Rating,100",
            "Main Breaker,100",
            "Description,Ckt,Breaker,Poles,Load VA",
            "Lights,1,20,1,1200",
            "Room 101: recep,3",
            "Heater A,5,40,2,9000",
            "Heater B,7,40,2,9000",
            "",
            "Panel,LP-2",
            "Description,Ckt,Breaker,Poles,Load VA",
            "Fan,1,20,1,500",
        ],
        [
            ("LP-1", ["1", "3", "5", "7"], {"bus": 100.0, "main": 100.0, "voltage": 208.0}),
            ("LP-2", ["1"], {}),
        ],
        [],
        id="j2_block_then_colon_row_then_next_panel",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "",
            "Panel,LP-2",
            "Main Breaker,100",
            "Bus Rating,225",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {"bus": 225.0, "main": 100.0})],
        [],
        id="RV25_block_values_stay_with_second_panel",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "",
            "Panel,LP-2",
            "Main Bkr (A),100",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {"main": 100.0})],
        [],
        id="RV31_word_main_after_panel_line",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "",
            "Panel,LP-2",
            "Bus Rating (A),225",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {"bus": 225.0})],
        [],
        id="RV31_word_bus_after_panel_line",
    ),
    pytest.param(
        [_P, "Panel A,1,a,20", "Panel A,3,c,20", _P, "Panel A,2,b,20"],
        [("Panel A", ["1", "3"], {}), ("Panel A", ["2"], {})],
        [],
        id="RV3_panel_A_name_keeps_rows_across_repeated_header",
    ),
    pytest.param(
        [
            "Panel,LP-3",
            "Voltage,208",
            "Bus Rating,225",
            "Main Breaker,MLO",
            "",
            "Ckt,Description,Breaker",
            "1,a,20",
            "3,b,20",
        ],
        [("LP-3", ["1", "3"], {"bus": 225.0, "voltage": 208.0})],
        [],
        id="header_block_schedule",
    ),
    pytest.param(
        [_P, "LP-1,1,Lights,20", "", "Panel,Description,Breaker", "LP-2,Heater,30"],
        [("LP-1", ["1"], {})],
        [("LP-2, Heater, 30", "no circuit number column")],
        id="later_table_without_circuit_column",
    ),
    pytest.param(
        [
            "Panel,Ckt,Description,Load VA,Breaker,Wire,Poles",
            "LP-1,1,Lights,1000,20,12,1",
            "LP-1,2,Load bank,1000,continuous,20,breaker locked",
            "LP-1,3,Pump,1000,20,12,1",
        ],
        [("LP-1", ["1", "2", "3"], {})],
        [],
        id="alias_word_data_row_not_a_header",
    ),
    pytest.param(
        [
            "Panel,LP-3",
            "Ckt,Description,Breaker,Ckt,Description,Breaker",
            "1,a,20,2,b,20",
            "3,c,20,4,d,20",
        ],
        [("LP-3", ["1", "2", "3", "4"], {})],
        [],
        id="two_column_layout",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Voltage,208",
            "",
            "Ckt,Description,Breaker",
            "1,a,20",
            "",
            "Panel,LP-2",
            "Voltage,120",
            "",
            "Ckt,Description,Breaker",
            "1,b,20",
        ],
        [("LP-1", ["1"], {"voltage": 208.0}), ("LP-2", ["1"], {"voltage": 120.0})],
        [],
        id="two_panels_samples_style_block",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "Room 101: recep,3",
            "Recep,5,20,1",
            "",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1", "3", "5"], {}), ("LP-2", ["1"], {})],
        [],
        id="RV34_room_colon_mid_table_keeps_following_rows",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "Main lobby: lights,3",
            "Recep,5,20,1",
            "",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1", "3", "5"], {}), ("LP-2", ["1"], {})],
        [],
        id="RV34_main_lobby_colon_keeps_following_rows",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            _D,
            "Lights,1,20,1",
            "Location,3",
            "Recep,5,20,1",
            "",
            "Panel,LP-2",
            _D,
            "Recep,1,20,1",
        ],
        [("LP-1", ["1", "3", "5"], {}), ("LP-2", ["1"], {})],
        [],
        id="RV34_exact_location_row_keeps_following_rows",
    ),
    pytest.param(
        [_P, "MAIN,1,a,20", "MAIN,3,c,20", _P, "LP-2,1,b,20"],
        [("MAIN", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [],
        id="RV35_panel_named_MAIN_not_block_key",
    ),
    pytest.param(
        [
            _P,
            "LP-1,1,x,20",
            "LP-1,3,y,20",
            "",
            "Bus Rating,225,A",
            "Panel,LP-2",
            "Ckt,Description,Breaker,Poles",
            "1,z,20,1",
        ],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [("Bus Rating, 225, A", _AMB)],
        id="RV40_bus_rating_three_cells_after_panel_column_table",
    ),
    pytest.param(
        [
            _P,
            "LP-1,1,x,20",
            "LP-1,3,y,20",
            "Panel,LP-2,120/208V",
            "Ckt,Description,Breaker,Poles",
            "1,z,20,1",
        ],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [("120/208V", "extra cells on a header block line")],
        id="RV40_panel_line_with_voltage_after_panel_column_table",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            "Voltage,208",
            "Ckt,Description,Breaker,Poles",
            "1,Heat,20,1",
            "",
            _P,
            "LP-2,1,x,20",
            "",
            "Ckt,Description,Breaker,Poles",
            "9,misc,20,1",
        ],
        [("LP-1", ["1"], {"bus": 100.0, "voltage": 208.0}), ("LP-2", ["1"], {})],
        [("9, misc, 20, 1", "no panel name")],
        id="RV41_no_inherit_past_panel_column_table",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            "Ckt,Description,Breaker,Poles",
            "1,Heat,20,1",
            "",
            "Bus Rating,225",
            "Ckt,Description,Breaker,Poles",
            "5,misc,20,1",
        ],
        [("LP-1", ["1"], {"bus": 100.0})],
        [("Bus Rating, 225", "no panel name"), ("5, misc, 20, 1", "no panel name")],
        id="RV41_own_block_without_panel_line_does_not_inherit",
    ),
    pytest.param(
        [
            _P,
            "LP-1,1,x,20",
            "MAIN,1,feeder,400",
            "",
            "Panel,LP-2",
            "Ckt,Description,Breaker,Poles",
            "1,z,20,1",
        ],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {})],
        [("MAIN, 1, feeder, 400", _AMB)],
        id="RV45_single_row_block_key_panel_at_end_then_block_table",
    ),
    pytest.param(
        [
            _P,
            "LP-1,1,x,20",
            "MAIN,1,feeder,400",
            "Panel,LP-2",
            "Ckt,Description,Breaker,Poles",
            "1,z,20,1",
        ],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {})],
        [("MAIN, 1, feeder, 400", _AMB)],
        id="RV45_single_row_block_key_panel_no_blank_line",
    ),
    pytest.param(
        [_P, "LP-1,1,x,20", "MAIN,1,feeder,400", "", _P, "LP-2,1,z,20"],
        [("LP-1", ["1"], {}), ("LP-2", ["1"], {})],
        [("MAIN, 1, feeder, 400", _AMB)],
        id="RV45_single_row_block_key_panel_then_panel_column_table",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            "Ckt,Description,Breaker,Poles",
            "1,a,20,1",
            "3,b,20,1",
            "Panel LP-1 (continued)",
            "Ckt,Description,Breaker,Poles",
            "5,c,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0}), ("LP-1", ["5"], {})],
        [("Panel LP-1 (continued)", "header block key panel_name has no value")],
        id="RV46_continued_title_line_keeps_inheritance",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            "Ckt,Description,Breaker,Poles",
            "1,a,20,1",
            "",
            "LP-1 continued",
            "",
            "Ckt,Description,Breaker,Poles",
            "5,c,20,1",
        ],
        [("LP-1", ["1"], {"bus": 100.0}), ("LP-1", ["5"], {})],
        [("LP-1 continued", "not a header block key: no alias matches")],
        id="RV46_continued_line_after_blank_keeps_inheritance",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,a,20,1",
            "3,b,20,1",
            "",
            "(continued)",
            _H,
            "5,c,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0}), ("LP-1", ["5"], {})],
        [("(continued)", "not a header block key: no alias matches")],
        id="RV56_bare_paren_title_keeps_inheritance",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,a,20,1",
            "3,b,20,1",
            "",
            "Continued",
            _H,
            "5,c,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0}), ("LP-1", ["5"], {})],
        [("Continued", "not a header block key: no alias matches")],
        id="RV56_bare_word_title_keeps_inheritance",
    ),
    pytest.param(
        ["Panel,LP-1", "Bus Rating,100", _H, "1,a,20,1", "3,b,20,1", "", "cont'd", _H, "5,c,20,1"],
        [("LP-1", ["1", "3"], {"bus": 100.0}), ("LP-1", ["5"], {})],
        [("cont'd", "not a header block key: no alias matches")],
        id="RV56_bare_contd_title_keeps_inheritance",
    ),
    pytest.param(
        ["Panel,LP-1", "Bus Rating,100", _D, "Lights,1,20,1", "", _D, "Fan,5,20,1"],
        [("LP-1", ["1"], {"bus": 100.0}), ("LP-1", ["5"], {})],
        [],
        id="RV39_page_break_part_one_keeps_block_values_part_two_has_none",
    ),
    pytest.param(
        [_P, "LP-1,1,x,20", "LP-1,3,y,20", "", "Panel,LP-2,120/208V,3PH", _H, "1,z,20,1"],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [("120/208V, 3PH", "extra cells on a header block line")],
        id="RV50_panel_line_four_cells_after_panel_column_table",
    ),
    pytest.param(
        [_P, "LP-1,1,x,20", "LP-1,3,y,20", "", "Bus Rating,225,A,Cu", "Panel,LP-2", _H, "1,z,20,1"],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [("Bus Rating, 225, A, Cu", _AMB)],
        id="RV50_bus_rating_four_cells_above_panel_line",
    ),
    pytest.param(
        [
            _P,
            "LP-1,1,x,20",
            "LP-1,3,y,20",
            "",
            "Voltage,120/208,3PH,4W",
            "Panel,LP-2",
            _H,
            "1,z,20,1",
        ],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [("Voltage, 120/208, 3PH, 4W", _AMB)],
        id="RV50_voltage_four_cells_above_panel_line",
    ),
    pytest.param(
        [_P, "LP-1,1,x,20", "LP-1,3,y,20", "", "Panel: LP-2,208V,3PH,rev 3", _H, "1,z,20,1"],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {})],
        [("208V, 3PH, rev 3", "extra cells on a header block line")],
        id="RV50_colon_panel_line_four_cells_after_panel_column_table",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Voltage,120",
            "Phases,1",
            "Bus Rating,100",
            "Main Breaker,100",
            _H,
            "1,Heat,4000,1",
            "",
            "LP-2 Lighting Panel",
            _H,
            "1,Lights,500,1",
        ],
        [("LP-1", ["1"], {"bus": 100.0, "main": 100.0, "voltage": 120.0, "incomplete": True})],
        [
            ("LP-2 Lighting Panel", "header block key panel_name has no value"),
            ("1, Lights, 500, 1", "no panel name"),
        ],
        id="RV51_title_naming_other_panel_ends_inheritance",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "",
            "LP-10 Lighting",
            _H,
            "1,Lights,20,1",
        ],
        [("LP-1", ["1"], {"bus": 100.0, "incomplete": True})],
        [
            ("LP-10 Lighting", "not a header block key: no alias matches"),
            ("1, Lights, 20, 1", "no panel name"),
        ],
        id="RV51_title_naming_LP_10_is_not_LP_1",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "Panel LP-1 (continued) - Page 2 of 2",
            _H,
            "5,Fan,20,1",
        ],
        [("LP-1", ["1"], {"bus": 100.0}), ("LP-1", ["5"], {})],
        [("Panel LP-1 (continued) - Page 2 of 2", "header block key panel_name has no value")],
        id="RV62_continued_title_with_page_number_keeps_inheritance",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "",
            "Continued - Page 2 of 3",
            _H,
            "5,Fan,20,1",
        ],
        [("LP-1", ["1"], {"bus": 100.0, "incomplete": True})],
        [
            ("Continued - Page 2 of 3", "not a header block key: no alias matches"),
            ("5, Fan, 20, 1", "no panel name"),
        ],
        id="RV62_page_title_without_panel_name_rows_unplaced",
    ),
    pytest.param(
        [
            _P,
            "LP-1,1,x,20",
            "LP-1,3,y,20",
            "",
            "Panel,LP-2",
            "Bus,225,A",
            "Voltage,120/208,3PH",
            _H,
            "1,z,20,1",
        ],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {"bus": 225.0, "voltage": 208.0})],
        [
            ("A", "extra cells on a header block line"),
            ("3PH", "extra cells on a header block line"),
        ],
        id="RV63_block_lines_after_panel_line_read",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "3,Lights,20,1",
            "",
            "LP-2",
            _H,
            "5,Fan,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0, "incomplete": True})],
        [("LP-2", "not a header block key: no alias matches"), ("5, Fan, 20, 1", "no panel name")],
        id="RV66_short_title_LP_2",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "3,Lights,20,1",
            "",
            "Panel LP-2",
            _H,
            "5,Fan,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0, "incomplete": True})],
        [
            ("Panel LP-2", "header block key panel_name has no value"),
            ("5, Fan, 20, 1", "no panel name"),
        ],
        id="RV66_short_title_Panel_LP_2",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "3,Lights,20,1",
            "",
            "LP-2 A wing",
            _H,
            "5,Fan,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0, "incomplete": True})],
        [
            ("LP-2 A wing", "not a header block key: no alias matches"),
            ("5, Fan, 20, 1", "no panel name"),
        ],
        id="RV66_short_title_LP_2_A_wing",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "3,Lights,20,1",
            "",
            "SUB LP-1 FEEDER TO LP-2",
            _H,
            "5,Fan,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0, "incomplete": True})],
        [
            ("SUB LP-1 FEEDER TO LP-2", "not a header block key: no alias matches"),
            ("5, Fan, 20, 1", "no panel name"),
        ],
        id="RV66_sub_feeder_title",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "3,Lights,20,1",
            "",
            "LP-1A",
            _H,
            "5,Fan,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0, "incomplete": True})],
        [("LP-1A", "not a header block key: no alias matches"), ("5, Fan, 20, 1", "no panel name")],
        id="RV66_LP_1A_title_ends_inheritance",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "3,Lights,20,1",
            "",
            "Panel LP-1A (continued)",
            _H,
            "5,Fan,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0, "incomplete": True})],
        [
            ("Panel LP-1A (continued)", "header block key panel_name has no value"),
            ("5, Fan, 20, 1", "no panel name"),
        ],
        id="RV66_Panel_LP_1A_continued_ends_inheritance",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "3,Lights,20,1",
            "",
            "Panel LP-2 fed from LP-1",
            _H,
            "5,Fan,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0, "incomplete": True})],
        [
            (
                "Panel LP-2 fed from LP-1",
                "not a header block key: matches more than one field: fed_from, panel_name",
            ),
            ("5, Fan, 20, 1", "no panel name"),
        ],
        id="RV66_title_naming_two_panels",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus Rating,100",
            _H,
            "1,Heat,20,1",
            "3,Lights,20,1",
            "",
            "Page 2",
            _H,
            "5,Fan,20,1",
        ],
        [("LP-1", ["1", "3"], {"bus": 100.0, "incomplete": True})],
        [
            ("Page 2", "not a header block key: no alias matches"),
            ("5, Fan, 20, 1", "no panel name"),
        ],
        id="RV66_bare_page_title_is_listed_not_a_circuit",
    ),
    pytest.param(
        [
            _P,
            "LP-1,1,x,20",
            "LP-1,3,y,20",
            "",
            "Panel Schedules",
            "Main,100,A",
            "Panel,LP-2",
            "Bus,100",
            _H,
            "1,z,20,1",
        ],
        [("LP-1", ["1", "3"], {}), ("LP-2", ["1"], {"bus": 100.0})],
        [
            ("Panel Schedules", "header block key panel_name has no value"),
            ("Main, 100, A", "panel row or header block line; not read"),
        ],
        id="RV64_ambiguous_line_below_panel_word_title_listed",
    ),
    pytest.param(
        [_P, "LP-1,1,x,20", ",3,y,20", ",5,z,20"],
        [("LP-1", ["1"], {"incomplete": True})],
        [("3, y, 20", "no panel name"), ("5, z, 20", "no panel name")],
        id="RV67_blank_panel_cells_mark_table_panels",
    ),
    pytest.param(
        ["Panel,MDP-1", "Bus,100", _H, "1,a,20,1", "", "LP-1 FED FROM MDP-1", _H, "1,b,20,1"],
        [("MDP-1", ["1"], {"bus": 100.0, "incomplete": True})],
        [
            ("LP-1 FED FROM MDP-1", "header block key fed_from has no value"),
            ("1, b, 20, 1", "no panel name"),
        ],
        id="RV68_fed_from_other_prefix_ends_inheritance",
    ),
    pytest.param(
        ["Panel,LP-1", "Bus,100", _H, "1,a,20,1", "", "LP-1 continued from sheet E-401", _H]
        + ["3,b,20,1"],
        [("LP-1", ["1"], {"bus": 100.0}), ("LP-1", ["3"], {})],
        [("LP-1 continued from sheet E-401", "not a header block key: no alias matches")],
        id="RV68_sheet_reference_keeps_inheritance",
    ),
    pytest.param(
        [_P, "LP-1,1,a,20", "LP-3,1,b,20", _P, ",3,c,20"],
        [("LP-1", ["1"], {}), ("LP-3", ["1"], {"incomplete": True})],
        [("3, c, 20", "no panel name")],
        id="RV69_blank_rows_after_page_break_mark_panel_above",
    ),
    pytest.param(
        ["Panel,LP-1", "Bus,100", _H, "1,a,20,1", "7A"],
        [("LP-1", ["1", "7A"], {"bus": 100.0})],
        [],
        id="RV70_lone_letter_suffixed_circuit_stays_circuit",
    ),
    pytest.param(
        [
            "Panel,LP-1",
            "Bus,100",
            _H,
            "1,a,20,1",
            "Schedule of LP-2 (fed from LP-1)",
            _H,
            "3,b,20,1",
        ],
        [("LP-1", ["1"], {"bus": 100.0, "incomplete": True})],
        [
            ("Schedule of LP-2 (fed from LP-1)", "header block key fed_from has no value"),
            ("3, b, 20, 1", "no panel name"),
        ],
        id="RV71_of_before_designation_ends_inheritance",
    ),
    pytest.param(
        ["Panel,LP-1", "Bus,100", _H, "1,a,20,1", "100A MLO", _H, "3,b,20,1"],
        [("LP-1", ["1"], {"bus": 100.0, "incomplete": True})],
        [
            ("100A MLO", "not a header block key: no alias matches"),
            ("3, b, 20, 1", "no panel name"),
        ],
        id="RV72_lone_digit_led_title_not_a_circuit",
    ),
    pytest.param(
        [_P, "LP-1,1,a,20", "LP-2,1,b,20", "LP-1,3,c,20", _P, ",5,d,20"],
        [("LP-1", ["1", "3"], {"incomplete": True}), ("LP-2", ["1"], {})],
        [("5, d, 20", "no panel name")],
        id="RV73_pcol_blank_rows_mark_panel_of_last_row",
    ),
    pytest.param(
        ["Panel,LP-1", "Bus,100", _H, "1,a,20,1", "3,b,20,1", "TOTAL,,40,"],
        [("LP-1", ["1", "3"], {"bus": 100.0})],
        [("TOTAL, 40", "no circuit number")],
        id="RV74_total_row_below_last_table_not_a_circuit",
    ),
    pytest.param(
        ["Panel,LP-1", "Bus,100", _H, "1,a,20,1", "3,b,20,1", "", "Page 2 of 2"],
        [("LP-1", ["1", "3"], {"bus": 100.0})],
        [("Page 2 of 2", "no circuit number")],
        id="RV74_page_footer_below_last_table_not_a_circuit",
    ),
    pytest.param(
        ["Panel,LP-1", "Bus,100", _H, "1,a,20,1", "3,b,20,1", "", "Notes:", "1,Provide GFCI,,"],
        [("LP-1", ["1", "3"], {"bus": 100.0, "incomplete": True})],
        [("Notes:", "no circuit number"), ("1, Provide GFCI", "no circuit number")],
        id="RV74_notes_below_last_table_not_circuits",
    ),
    pytest.param(
        ["Panel,LP-1", "Bus,100", _H, "1,a,20,1", "3,b,20,1", "", "Receptacles", "5,c,20,1"],
        [("LP-1", ["1", "3"], {"bus": 100.0, "incomplete": True})],
        [("Receptacles", "no circuit number"), ("5, c, 20, 1", "no circuit number")],
        id="RV76_section_heading_in_last_table_marks_panel",
    ),
    pytest.param(
        ["Panel,LP-1", "Bus,100", _H, "1,a,20,1", "", "LP-2", "225A", _H, "1,b,20,1", "3,c,20,1"],
        [("LP-1", ["1"], {"bus": 100.0, "incomplete": True})],
        [
            ("LP-2", "not a header block key: no alias matches"),
            ("225A", "not a header block key: no alias matches"),
            ("1, b, 20, 1", "no panel name"),
            ("3, c, 20, 1", "no panel name"),
        ],
        id="RV75_lone_rating_under_title_not_a_circuit",
    ),
]


@pytest.mark.parametrize(("lines", "panels", "unparsed"), LAYOUTS)
def test_layout_corpus(cfg, lines, panels, unparsed):
    # Panels are compared by position: (name, circuit numbers, block values) per panel part,
    # so a page-break continuation cannot hide the block values of its first part.
    parsed = parse([line.split(",") for line in lines], cfg)
    got = []
    for p in parsed.panels:
        vals = {
            "bus": p.bus_rating_a.value,
            "main": p.main_breaker_a.value,
            "voltage": p.voltage_v.value,
        }
        got_vals = {k: v for k, v in vals.items() if v is not None}
        if "could not be placed" in (
            p.bus_rating_a.source.note or "" if p.bus_rating_a.source else ""
        ):
            got_vals["incomplete"] = True  # bus LOW: the panel-level checks are NEEDS_REVIEW
        got.append((p.name, [c.number for c in p.circuits], got_vals))
    assert got == panels
    assert [(u.raw, u.reason) for u in parsed.unparsed if u.kind != "column"] == unparsed


@pytest.mark.parametrize(
    "mid", [["Room 101: recep", "3"], ["Main lobby: lights", "3"], ["Location", "3"]]
)
def test_short_block_word_circuit_row_mid_table_keeps_following_rows(cfg, mid):
    h = _DESC_FIRST
    rows = [
        ["Panel", "LP-1"],
        h,
        ["Lights", "1", "20", "1"],
        mid,
        ["Recep", "5", "20", "1"],
        [],
        ["Panel", "LP-2"],
        h,
        ["Recep", "1", "20", "1"],
    ]
    by = {p.name: p for p in parse(rows, cfg).panels}
    assert [c.number for c in by["LP-1"].circuits] == ["1", "3", "5"]
    assert [c.number for c in by["LP-2"].circuits] == ["1"]


def test_panel_column_exact_block_key_name_keeps_table_rows(cfg):
    head = ["Panel", "Ckt", "Description", "Breaker"]
    rows = [
        head,
        ["MAIN", "1", "a", "20"],
        ["MAIN", "3", "c", "20"],
        head,
        ["LP-2", "1", "b", "20"],
    ]
    by = {p.name: p for p in parse(rows, cfg).panels}
    assert [c.number for c in by["MAIN"].circuits] == ["1", "3"]
    assert [c.number for c in by["LP-2"].circuits] == ["1"]
    assert by["LP-2"].main_breaker_a.confidence is Confidence.MISSING


def test_wide_circuit_header_with_blank_lines_is_linear(cfg):
    import time

    head = ["ckt"] * 6000 + ["load", "breaker"]
    rows = [head] + [[""]] * 100000 + [["ckt", "load", "breaker"]]
    t0 = time.perf_counter()
    parse(rows, cfg)
    assert time.perf_counter() - t0 < 5


@pytest.mark.parametrize(
    "lines",
    [
        ["Panel,LP-1", _D, "Lights,1,20,1", "Recep,3,20,1", _D, "Fan,5,20,1"],
        [
            "Panel,LP-1",
            "Ckt,Description,Breaker,Poles",
            "1,Lights,20,1",
            "3,Recep,20,1",
            "Ckt,Description,Breaker,Poles",
            "5,Fan,20,1",
        ],
    ],
)
def test_page_break_header_keeps_block_panel_name(cfg, lines):
    parsed = parse([line.split(",") for line in lines], cfg)
    got = [(p.name, [c.number for c in p.circuits]) for p in parsed.panels]
    assert got == [("LP-1", ["1", "3"]), ("LP-1", ["5"])]
    assert [u for u in parsed.unparsed if u.kind != "column"] == []


@pytest.mark.parametrize(
    "line",
    [["Bus Rating", "225", "A"], ["Panel", "LP-2", "120/208V"], ["Panel: LP-2", "208V", "rev 3"]],
)
def test_exact_key_three_cell_block_line_after_panel_column_table_stays_block(cfg, line):
    head = ["Panel", "Ckt", "Description", "Breaker"]
    rows = [
        head,
        ["LP-1", "1", "x", "20"],
        ["LP-1", "3", "y", "20"],
        [],
        line,
        *([["Panel", "LP-2"]] if line[0] == "Bus Rating" else []),
        ["Ckt", "Description", "Breaker", "Poles"],
        ["1", "z", "20", "1"],
    ]
    got = {p.name: [c.number for c in p.circuits] for p in parse(rows, cfg).panels}
    assert got == {"LP-1": ["1", "3"], "LP-2": ["1"]}


def _case_b_tail(extra):
    return [
        ["Panel", "LP-1"],
        ["Bus Rating", "100"],
        ["Ckt", "Description", "Breaker", "Poles"],
        ["1", "Heat", "20", "1"],
        [],
        *extra,
    ]


def test_block_name_not_inherited_past_panel_column_table(cfg):
    rows = _case_b_tail(
        [
            ["Panel", "Ckt", "Description", "Breaker"],
            ["LP-2", "1", "x", "20"],
            [],
            ["Ckt", "Description", "Breaker", "Poles"],
            ["9", "misc", "20", "1"],
        ]
    )
    parsed = parse(rows, cfg)
    assert [(p.name, [c.number for c in p.circuits]) for p in parsed.panels] == [
        ("LP-1", ["1"]),
        ("LP-2", ["1"]),
    ]


def test_block_without_panel_line_does_not_inherit_name(cfg):
    rows = _case_b_tail(
        [["Bus Rating", "225"], ["Ckt", "Description", "Breaker", "Poles"], ["5", "m", "20", "1"]]
    )
    parsed = parse(rows, cfg)
    assert [(p.name, [c.number for c in p.circuits]) for p in parsed.panels] == [("LP-1", ["1"])]
    assert parsed.panels[0].bus_rating_a.value == 100


def test_page_break_with_continued_line_keeps_block_panel_name(cfg):
    sub = ["Ckt", "Description", "Breaker", "Poles"]
    rows = [
        ["Panel", "LP-1"],
        ["Bus Rating", "100"],
        sub,
        ["1", "a", "20", "1"],
        ["3", "b", "20", "1"],
        ["Panel LP-1 (continued)"],
        sub,
        ["5", "c", "20", "1"],
        ["7", "d", "20", "1"],
        ["9", "e", "20", "1"],
    ]
    parsed = parse(rows, cfg)
    got = [(p.name, [c.number for c in p.circuits]) for p in parsed.panels]
    assert got == [("LP-1", ["1", "3"]), ("LP-1", ["5", "7", "9"])]
    assert not [u for u in parsed.unparsed if u.reason == "no panel name"]


_AMB_LINES = [
    ["MAIN", "1", "Feeder", "1000", "noncontinuous", "1", "20"],
    ["MAIN", "1", "Feeder to LP-2", "TBD", "3", "30000", "other"],
    ["MAIN", "1", "feeder", "-", "3"],
    ["MAIN", "1", "feeder", "3P", "400AT"],
    ["Bus Rating", "225", "A"],
    ["Bus Rating", "225", "A", "Cu"],
    ["Voltage", "120/208", "3PH", "4W"],
]


def _two_blocks(line):
    return [
        ["Panel", "Ckt", "Description", "Breaker"],
        ["LP-1", "1", "x", "20"],
        ["LP-1", "3", "y", "20"],
        line,
        ["Panel", "LP-2"],
        ["Ckt", "Description", "Breaker", "Poles"],
        ["1", "z", "20", "1"],
        ["3", "w", "20", "1"],
    ]


@pytest.mark.parametrize("line", _AMB_LINES, ids=lambda x: ",".join(x))
def test_ambiguous_key_line_listed_not_read(cfg, line):
    parsed = parse(_two_blocks(line), cfg)
    assert [(p.name, [c.number for c in p.circuits]) for p in parsed.panels] == [
        ("LP-1", ["1", "3"]),
        ("LP-2", ["1", "3"]),
    ]
    raw = ", ".join(line)
    assert [(u.raw, u.reason) for u in parsed.unparsed if u.raw == raw] == [
        (raw, "panel row or header block line; not read")
    ]
    lp2 = parsed.panels[1]
    assert lp2.main_breaker_a.value is None
    assert lp2.bus_rating_a.value is None
    assert lp2.voltage_v.value is None


@pytest.mark.parametrize(
    "line",
    [
        ["Panel", "LP-2", "120/208V"],
        ["Panel", "LP-2", "120/208V", "3PH"],
        ["Panel: LP-2", "208V", "rev 3"],
        ["Panel: LP-2", "208V", "3PH", "rev 3"],
    ],
)
def test_panel_key_line_with_extra_cells_stays_block(cfg, line):
    rows = [
        ["Panel", "Ckt", "Description", "Breaker"],
        ["LP-1", "1", "x", "20"],
        ["LP-1", "3", "y", "20"],
        [],
        line,
        ["Ckt", "Description", "Breaker", "Poles"],
        ["1", "z", "20", "1"],
    ]
    parsed = parse(rows, cfg)
    assert [(p.name, [c.number for c in p.circuits]) for p in parsed.panels] == [
        ("LP-1", ["1", "3"]),
        ("LP-2", ["1"]),
    ]


def test_bare_continued_title_keeps_inheritance(cfg):
    sub = ["Ckt", "Description", "Breaker", "Poles"]
    for word in ["(continued)", "Continued", "cont'd"]:
        rows = [
            ["Panel", "LP-1"],
            ["Bus", "100"],
            sub,
            ["1", "Heat", "20", "1"],
            ["3", "Heat", "20", "1"],
            [],
            [word],
            sub,
            ["5", "Heat", "20", "1"],
            ["7", "Heat", "20", "1"],
            ["9", "Heat", "20", "1"],
        ]
        parsed = parse(rows, cfg)
        assert [(p.name, [c.number for c in p.circuits]) for p in parsed.panels] == [
            ("LP-1", ["1", "3"]),
            ("LP-1", ["5", "7", "9"]),
        ]
        assert not [u for u in parsed.unparsed if u.reason == "no panel name"]


def test_names_only_long_name_linear():
    from redline.parsers.tabular import _names_only

    name = "a " * 65000 + "b"
    title = ["a " * 65000 + "a"] * 8
    t0 = time.perf_counter()
    assert _names_only([title], name)
    assert time.perf_counter() - t0 < 2


def test_title_naming_other_panel_ends_inheritance(cfg):
    sub = ["Ckt", "Description", "Breaker", "Poles"]
    titles = {
        "LP-2 Lighting Panel": False,
        "LP-10 Lighting": False,
        "Panel LP-1 (continued)": True,
        "lp-1 CONTINUED": True,
    }
    for title, kept in titles.items():
        rows = [
            ["Panel", "LP-1"],
            ["Bus Rating", "100"],
            sub,
            ["1", "Heat", "4000", "1"],
            [],
            [title],
            sub,
            ["1", "Lights", "500", "1"],
        ]
        parsed = parse(rows, cfg)
        got = [(p.name, [c.number for c in p.circuits]) for p in parsed.panels]
        assert got == ([("LP-1", ["1"])] * (2 if kept else 1)), title
        assert any(u.reason == "no panel name" for u in parsed.unparsed) is not kept, title


def test_continued_title_with_page_or_sheet_number_keeps_block_panel_name(cfg):
    sub = ["Ckt", "Description", "Breaker", "Poles"]
    titles = [
        ["Panel LP-1 (continued) - Page 2 of 2"],
        ["LP-1 continued from sheet E-401"],
        ["Panel LP-1 208Y/120V (cont.)"],
        ["LP-1 cont'd 3PH 4W"],
        ["LP-1 (continued)", "Rev 2"],
    ]
    for title in titles:
        rows = [
            ["Panel", "LP-1"],
            ["Bus", "100"],
            sub,
            ["1", "a", "20", "1"],
            ["3", "b", "20", "1"],
            title,
            sub,
            ["5", "c", "20", "1"],
            ["7", "d", "20", "1"],
        ]
        parsed = parse(rows, cfg)
        got = [(p.name, [c.number for c in p.circuits]) for p in parsed.panels]
        assert got == [("LP-1", ["1", "3"]), ("LP-1", ["5", "7"])], title
        assert not [u for u in parsed.unparsed if u.reason == "no panel name"], title


def test_block_lines_after_panel_line_read(cfg):
    rows = [
        ["Panel", "Ckt", "Description", "Breaker"],
        ["LP-1", "1", "x", "20"],
        ["LP-1", "3", "y", "20"],
        [],
        ["Panel", "LP-2"],
        ["Bus", "225", "A"],
        ["Voltage", "120/208", "3PH"],
        ["Ckt", "Description", "Breaker", "Poles"],
        ["1", "z", "20", "1"],
    ]
    parsed = parse(rows, cfg)
    lp2 = parsed.panels[1]
    assert lp2.name == "LP-2"
    assert lp2.bus_rating_a.value == 225
    assert lp2.voltage_v.value == 208
    assert not [
        u for u in parsed.unparsed if u.reason == "panel row or header block line; not read"
    ]


def _marked(panel):
    return panel.bus_rating_a.confidence == Confidence.LOW


def test_ambiguous_key_line_below_panel_word_title_listed(cfg):
    for line in (["MAIN", "1", "Feeder", "1000"], ["Main", "100", "A"]):
        rows = [
            ["Panel", "Ckt", "Description", "Breaker"],
            ["LP-1", "1", "x", "20"],
            ["LP-1", "3", "y", "20"],
            [],
            ["Panel Schedules"],
            line,
            ["Panel", "LP-2"],
            ["Voltage", "120"],
            ["Ckt", "Description", "Breaker", "Poles"],
            ["1", "z", "20", "1"],
        ]
        parsed = parse(rows, cfg)
        lp2 = parsed.panels[1]
        assert lp2.name == "LP-2", line
        assert lp2.main_breaker_a.value is None, line
        assert lp2.voltage_v.value == 120, line
        reason = "panel row or header block line; not read"
        assert any(u.reason == reason for u in parsed.unparsed), line


def test_xlsx_unplaced_page_break_rows_mark_panel_incomplete(cfg):
    rows = [
        ["Panel", "LP-1"],
        ["Bus Rating", "100"],
        ["Ckt", "Description", "Breaker", "Poles"],
        ["1", "a", "20", "1"],
        [],
        ["Continued - Page 2 of 3"],
        ["Ckt", "Description", "Breaker", "Poles"],
        ["5", "b", "20", "1"],
    ]
    first, second = parse(rows, cfg, fallback_panel="E-601").panels
    assert (first.name, second.name) == ("LP-1", "E-601")
    assert _marked(first)
    assert not _marked(second)


def test_block_without_panel_line_keeps_panel_above_violation(cfg):
    rows = [
        ["Panel", "LP-1"],
        ["Bus Rating", "100"],
        ["Ckt", "Description", "Breaker", "Poles"],
        ["1", "a", "20", "1"],
        [],
        ["Bus", "225"],
        ["Voltage", "120"],
        ["Ckt", "Description", "Breaker", "Poles"],
        ["5", "b", "20", "1"],
    ]
    parsed = parse(rows, cfg)
    assert [c.number for c in parsed.panels[0].circuits] == ["1"]
    assert not _marked(parsed.panels[0])
    assert any(u.reason == "no panel name" for u in parsed.unparsed)


def test_title_naming_two_panels_or_short_title_does_not_join_panel_above(cfg):
    sub = ["Ckt", "Description", "Breaker", "Poles"]
    titles = [
        "Panel LP-2 fed from LP-1",
        "SUB LP-1 FEEDER TO LP-2",
        "LP-2",
        "Panel LP-2",
        "LP-2 A wing",
        "LP-1A",
        "Panel LP-1A (continued)",
    ]
    for title in titles:
        rows = [
            ["Panel", "LP-1"],
            ["Bus Rating", "100"],
            sub,
            ["1", "a", "20", "1"],
            ["3", "b", "20", "1"],
            [title],
            sub,
            ["5", "c", "20", "1"],
        ]
        parsed = parse(rows, cfg)
        got = [(p.name, [c.number for c in p.circuits]) for p in parsed.panels]
        assert got == [("LP-1", ["1", "3"])], title
        assert _marked(parsed.panels[0]), title
        assert any(u.reason == "no panel name" for u in parsed.unparsed), title


def test_blank_panel_cell_rows_mark_table_panels_incomplete(cfg):
    rows = [
        ["Panel", "Ckt", "Description", "Load VA", "Breaker"],
        ["LP-1", "1", "a", "1000", "20"],
        ["", "3", "b", "8000", "20"],
        ["LP-2", "1", "c", "500", "20"],
    ]
    parsed = parse(rows, cfg)
    assert [p.name for p in parsed.panels] == ["LP-1", "LP-2"]
    assert all(_marked(p) for p in parsed.panels)
    assert [u.reason for u in parsed.unparsed if u.kind == "row"] == ["no panel name"]


def test_rule_title_other_prefix_feeder_ends_inheritance(cfg):
    sub = ["Ckt", "Description", "Breaker", "Poles"]
    ends = [
        ("MDP-1", "LP-1 FED FROM MDP-1"),
        ("LP-1", "SUB LP-1 FEEDER TO LP-2"),
        ("LP-1", "LP-1A"),
        ("LP-1", "Panel LP-1 fed from E-401"),
    ]
    keeps = [
        "LP-1 continued from sheet E-401",
        "Panel LP-1 (continued) - Page 2 of 2",
        "Panel LP-1 208Y/120V (cont.)",
        "LP-1 cont'd 3PH 4W",
        "LP-1 (cont.) see dwg E-401 rev 3",
    ]
    cases = [(n, t, False) for n, t in ends] + [("LP-1", t, True) for t in keeps]
    for name, title, kept in cases:
        rows = [["Panel", name], ["Bus Rating", "100"], sub, ["1", "a", "20", "1"], [title], sub]
        parsed = parse(rows + [["5", "c", "20", "1"]], cfg)
        got = [(p.name, [c.number for c in p.circuits]) for p in parsed.panels]
        if kept:
            assert got == [(name, ["1"]), (name, ["5"])], title
        else:
            assert got == [(name, ["1"])], title
            assert _marked(parsed.panels[0]), title
            assert any(u.reason == "no panel name" for u in parsed.unparsed), title


def test_pcol_blank_rows_after_page_break_mark_panel_above(cfg):
    rows = [
        ["Panel", "Ckt", "Description", "Load VA", "Breaker"],
        ["LP-3", "1", "a", "1000", "20"],
        ["Panel", "Ckt", "Description", "Load VA", "Breaker"],
        ["", "3", "b", "8000", "20"],
    ]
    parsed = parse(rows, cfg)
    assert [p.name for p in parsed.panels] == ["LP-3"]
    assert _marked(parsed.panels[0])
    assert [u.reason for u in parsed.unparsed if u.kind == "row"] == ["no panel name"]
    assert "blank panel cell" in parsed.panels[0].bus_rating_a.source.note


def test_lone_letter_suffixed_circuit_number_stays_circuit(cfg):
    sub = ["Ckt", "Description", "Breaker", "Poles"]
    for lone, circuit in (("7A", True), ("1A", True), ("LP-2", False), ("Page 2", False)):
        rows = [
            ["Panel", "LP-1"],
            ["Bus Rating", "100"],
            sub,
            ["1", "a", "20", "1"],
            [lone],
            sub,
            ["9", "z", "20", "1"],
        ]
        parsed = parse(rows, cfg)
        nums = [c.number for c in parsed.panels[0].circuits]
        assert (lone in nums) is circuit, lone


def test_rows_below_last_table_not_circuits(cfg):
    head = ["Panel,LP-1", "Voltage,120", "Bus,100", _H, "1,a,20,1", "3,b,20,1"]
    for tail in (["TOTAL,,40,"], ["", "Page 2 of 2"], ["", "Notes:", "1,Provide GFCI,,"]):
        parsed = parse([line.split(",") for line in head + tail], cfg)
        assert [c.number for c in parsed.panels[0].circuits] == ["1", "3"], tail
        listed = [u.raw for u in parsed.unparsed if u.reason == "no circuit number"]
        assert listed, tail
        assert all(
            x not in [c.number for c in parsed.panels[0].circuits] for x in ("TOTAL", "Notes:")
        )


def test_section_heading_in_last_table_marks_panel(cfg):
    rows = [
        ["Panel", "LP-1"],
        ["Bus", "100"],
        ["Main", "100"],
        _H.split(","),
        ["1", "a", "20", "1"],
        ["3", "b", "20", "1"],
        [],
        ["Receptacles"],
        ["5", "c", "20", "1"],
        ["7", "d", "20", "1"],
        ["9", "e", "20", "1"],
    ]
    parsed = parse(rows, cfg)
    panel = parsed.panels[0]
    assert [c.number for c in panel.circuits] == ["1", "3"]
    assert panel.bus_rating_a.confidence == Confidence.LOW
    assert "rows below the table could not be placed" in panel.bus_rating_a.source.note
    listed = {u.raw for u in parsed.unparsed if u.reason == "no circuit number"}
    assert {"Receptacles", "5, c, 20, 1", "7, d, 20, 1", "9, e, 20, 1"} <= listed


def test_lone_rating_under_title_does_not_join_panel_above(cfg):
    rows = [
        ["Panel", "LP-1"],
        ["Bus", "100"],
        _H.split(","),
        ["1", "a", "20", "1"],
        [],
        ["LP-2"],
        ["225A"],
        _H.split(","),
        ["1", "b", "20", "1"],
        ["3", "c", "20", "1"],
    ]
    parsed = parse(rows, cfg)
    assert [(p.name, [c.number for c in p.circuits]) for p in parsed.panels] == [("LP-1", ["1"])]
    assert {"LP-2", "225A"} <= {u.raw for u in parsed.unparsed}


def test_rule_title_designation_after_of_ends_inheritance(cfg):
    sub = ["Ckt", "Description", "Breaker", "Poles"]
    for title, kept in (
        ("Schedule of LP-2 (fed from LP-1)", False),
        ("Part of LP-2 (fed from LP-1)", False),
        ("Panel LP-1 (continued) - Page 2 of 2", True),
    ):
        rows = [["Panel", "LP-1"], ["Bus Rating", "100"], sub, ["1", "a", "20", "1"], [title], sub]
        parsed = parse(rows + [["5", "c", "20", "1"]], cfg)
        got = [(p.name, [c.number for c in p.circuits]) for p in parsed.panels]
        if kept:
            assert got == [("LP-1", ["1"]), ("LP-1", ["5"])], title
        else:
            assert got == [("LP-1", ["1"])], title
            assert _marked(parsed.panels[0]), title
            assert any(u.reason == "no panel name" for u in parsed.unparsed), title


def test_lone_digit_led_title_not_a_circuit(cfg):
    sub = ["Ckt", "Description", "Breaker", "Poles"]
    for lone in ("100A MLO", "120/208V", "2 of 2", "3PH 4W"):
        rows = [["Panel", "LP-1"], ["Bus Rating", "100"], sub, ["1", "a", "20", "1"], [lone], sub]
        parsed = parse(rows + [["9", "z", "20", "1"]], cfg)
        assert all(lone not in [c.number for c in p.circuits] for p in parsed.panels), lone
        assert [c.number for c in parsed.panels[0].circuits] == ["1"], lone


def test_pcol_blank_rows_mark_panel_of_last_row(cfg):
    hdr = ["Panel", "Ckt", "Description", "Breaker"]
    rows = [hdr, ["LP-1", "1", "a", "20"], ["LP-2", "1", "b", "20"], ["LP-1", "3", "c", "20"]]
    parsed = parse(rows + [hdr, ["", "5", "d", "20"]], cfg)
    marked = {p.name: _marked(p) for p in parsed.panels}
    assert marked == {"LP-1": True, "LP-2": False}
