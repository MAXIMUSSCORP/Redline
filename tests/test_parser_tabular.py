import copy
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


def test_slash_voltage_one_pole_circuit_not_line_to_line(cfg):
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
