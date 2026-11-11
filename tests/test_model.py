import pytest

from redline.findings import Severity, input_gate, inputs_used
from redline.model import (
    MAX_INT,
    Circuit,
    Confidence,
    Device,
    EgressPath,
    Method,
    Panel,
    Project,
    Source,
    Value,
    check_value,
    derived,
    effective_voltage,
    is_mlo,
    label,
    project_from_dict,
)


def _src(locator="r1", note="") -> Source:
    return Source("t.csv", locator, Method.CSV, Confidence.HIGH, note)


def test_confidence_is_ordered():
    assert Confidence.MISSING < Confidence.LOW < Confidence.MEDIUM < Confidence.HIGH
    assert min(Confidence.HIGH, Confidence.LOW) == Confidence.LOW


def test_value_confidence_and_usable(val):
    assert Value.missing().confidence == Confidence.MISSING
    assert not Value.missing().usable
    assert val(5, Confidence.HIGH).usable
    assert val(5, Confidence.MEDIUM).usable
    assert not val(5, Confidence.LOW).usable
    assert not val(None, Confidence.HIGH).usable


def test_derived_takes_lowest_confidence(val):
    d = derived(10, [val(1, Confidence.HIGH), val(2, Confidence.MEDIUM)], "t.csv", "x")
    assert d.value == 10
    assert d.confidence == Confidence.MEDIUM
    assert d.source.method == Method.DERIVED
    assert derived(10, [val(1), Value.missing()], "t.csv", "x").value is None
    assert derived(10, [val(1), Value.missing()], "t.csv", "x").confidence == Confidence.MISSING


def test_defaults_are_missing_and_not_shared():
    a = Circuit("LP-1", "1", _src())
    b = Circuit("LP-1", "2", _src())
    assert a.load_va.confidence == Confidence.MISSING
    assert a.is_spare is False
    p1, p2 = Panel("A", _src()), Panel("B", _src())
    p1.circuits.append(a)
    assert p2.circuits == []
    assert b.number == "2"


def test_label():
    c = Circuit("LP-1", "7", _src())
    assert label(c) == "LP-1 ckt 7"
    assert label(Panel("LP-1", _src())) == "LP-1"


def test_effective_voltage_single_pole_needs_own_voltage(val):
    p = Panel("LP-1", _src(), voltage_v=val(208))
    c = Circuit("LP-1", "1", _src(), poles=val(1))
    assert effective_voltage(c, p).confidence == Confidence.MISSING
    c.poles = Value.missing()
    assert not effective_voltage(c, p).usable
    c.voltage_v = val(277)
    assert effective_voltage(c, p).value == 277


def test_effective_voltage_multi_pole_uses_panel_voltage(val):
    p = Panel("LP-1", _src(), voltage_v=val(208))
    c = Circuit("LP-1", "1", _src(), poles=val(2))
    assert effective_voltage(c, p).value == 208
    c.voltage_v = val(240)
    assert effective_voltage(c, p).value == 240


def test_value_non_finite_not_usable(val):
    for bad in (float("nan"), float("inf"), float("-inf")):
        assert not val(bad, Confidence.HIGH).usable
    assert val(1.5, Confidence.HIGH).usable


def test_demo_project_ai_method_capped_low():
    src = {"file": "a.pdf", "locator": "p1", "method": "csv", "confidence": "HIGH"}
    data = {
        "name": "d",
        "panels": [
            {
                "name": "P",
                "source": src,
                "voltage_v": {"value": 120, "source": {**src, "method": "vlm"}},
                "phases": {"value": 1, "source": {**src, "method": "ocr"}},
                "wires": {"value": 3, "source": {**src, "method": "detector"}},
                "bus_rating_a": {"value": 100, "source": src},
            }
        ],
    }
    p = project_from_dict(data).panels[0]
    assert p.voltage_v.confidence == Confidence.LOW
    assert p.phases.confidence == Confidence.LOW
    assert p.wires.confidence == Confidence.LOW
    assert p.bus_rating_a.confidence == Confidence.HIGH


def test_is_mlo():
    mlo = Panel("A", _src(), main_breaker_a=Value(None, _src(note="MLO")))
    assert is_mlo(mlo)
    assert not is_mlo(Panel("B", _src()))
    assert not is_mlo(Panel("C", _src(), main_breaker_a=Value(100, _src())))


def test_project_from_dict():
    src = {"file": "a.csv", "locator": "row=1", "method": "csv", "confidence": "HIGH"}
    data = {
        "name": "demo",
        "code_edition": "x",
        "panels": [
            {
                "name": "LP-1",
                "source": src,
                "voltage_v": {"value": 120, "raw": "120", "source": src},
                "main_breaker_a": {"value": None, "source": {**src, "note": "MLO"}},
                "circuits": [
                    {
                        "panel": "LP-1",
                        "number": "7",
                        "source": src,
                        "breaker_a": {"value": 20, "source": {**src, "confidence": "LOW"}},
                        "is_spare": True,
                    }
                ],
            }
        ],
        "devices": [{"type": "exit_sign", "source": src, "detection": "block"}],
        "unparsed": [{"kind": "column", "raw": "Foo", "reason": "no alias", "source": src}],
        "coverage": [
            {
                "file": "a.csv",
                "unit": "sheet",
                "what_read": "rows",
                "method": "csv",
                "confidence_summary": "all HIGH",
            }
        ],
        "run_info": {"tool_version": "0.1.0"},
    }
    proj = project_from_dict(data)
    p = proj.panels[0]
    assert p.voltage_v.value == 120 and p.voltage_v.confidence == Confidence.HIGH
    assert is_mlo(p)
    c = p.circuits[0]
    assert c.breaker_a.confidence == Confidence.LOW and not c.breaker_a.usable
    assert c.load_va.confidence == Confidence.MISSING
    assert c.is_spare is True
    assert proj.devices[0].detection == "block"
    assert proj.unparsed[0].source.method == Method.CSV
    assert proj.coverage[0].unit == "sheet"
    assert proj.run_info.tool_version == "0.1.0"


def test_inputs_used_and_input_gate(val):
    ok, low = val(20, locator="row=3"), val(5, Confidence.LOW, locator="row=4")
    used = inputs_used({"breaker_a": ok, "length_m": Value.missing()})
    assert used[0].field == "breaker_a" and used[0].locator == "row=3"
    assert used[1].confidence == Confidence.MISSING
    assert input_gate("r", "ref", "LP-1 ckt 1", None, {"breaker_a": ok}, "fix") is None
    f = input_gate("r", "ref", "LP-1 ckt 1", None, {"a": ok, "b": low, "c": Value.missing()}, "fix")
    assert f.severity == Severity.NEEDS_REVIEW
    assert "b (LOW, at row=4)" in f.message and "c (missing)" in f.message
    assert "a (" not in f.message
    assert f.suggested_fix == "fix" and f.rule_ref == "ref"


def _one_circuit(**cells):
    src = {"file": "t.csv", "locator": "r1", "method": "csv", "confidence": "HIGH"}
    circuit = {"panel": "P", "number": "1", "source": src}
    circuit.update({k: {"value": v, "source": src} for k, v in cells.items()})
    panel = {"name": "P", "source": src, "circuits": [circuit]}
    return project_from_dict({"name": "x", "panels": [panel]}).panels[0].circuits[0]


def test_negative_quantity_not_usable():
    c = _one_circuit(breaker_a=-20, load_va=-5, ambient_c=-10, length_m=3)
    assert not c.breaker_a.usable and not c.load_va.usable
    assert c.ambient_c.usable and c.length_m.usable
    assert not _one_circuit(breaker_a=0).breaker_a.usable


def test_demo_project_model_set_capped_low():
    src = {"file": "t.csv", "locator": "r1", "method": "csv", "confidence": "HIGH", "model": "m"}
    p = {"name": "x", "panels": [{"name": "P", "source": src}]}
    assert project_from_dict(p).panels[0].source.confidence == Confidence.LOW


def test_effective_voltage_unparsed_own_voltage_not_replaced(val):
    p = Panel("LP-1", _src(), voltage_v=val(208))
    own = Value(None, _src(), "abc")
    c = Circuit("LP-1", "1", _src(), poles=val(2), voltage_v=own)
    assert effective_voltage(c, p) is own
    assert effective_voltage(Circuit("LP-1", "2", _src(), poles=val(2)), p).value == 208


def test_unlisted_load_type_not_usable():
    for bad in ("Continuous", " continuous", "bogus"):
        lt = _one_circuit(load_type=bad).load_type
        assert not lt.usable and lt.source.note == "not a known load type"
    assert _one_circuit(load_type="continuous").load_type.usable


def _project_with(panel_cells, feeder_cells):
    src = {"file": "t.csv", "locator": "r1", "method": "csv", "confidence": "HIGH"}

    def cells(d):
        return {k: {"value": v, "source": src} for k, v in d.items()}

    panel = {"name": "P", "source": src, **cells(panel_cells)}
    feeder = {"id": "F", "source": src, **cells(feeder_cells)}
    return project_from_dict({"name": "x", "panels": [panel], "feeders": [feeder]})


def test_zero_rating_or_divisor_not_usable():
    c = _one_circuit(breaker_a=0, voltage_v=0, load_va=0, length_m=0)
    assert not c.breaker_a.usable and not c.voltage_v.usable
    assert c.breaker_a.source.note == "zero"
    assert c.load_va.usable and c.length_m.usable
    pr = _project_with(
        {"bus_rating_a": 0, "main_breaker_a": 0, "voltage_v": 0},
        {"ocpd_a": 0, "sets_in_parallel": 0, "voltage_v": 0},
    )
    p, f = pr.panels[0], pr.feeders[0]
    assert not any(v.usable for v in (p.bus_rating_a, p.main_breaker_a, p.voltage_v))
    assert not any(v.usable for v in (f.ocpd_a, f.sets_in_parallel, f.voltage_v))


def test_negative_insulation_temp_not_usable():
    assert not _one_circuit(insulation_temp_c=-5).insulation_temp_c.usable
    assert _one_circuit(ambient_c=-5).ambient_c.usable


def test_effective_voltage_blank_own_voltage_uses_panel(val):
    p = Panel("LP-1", _src(), voltage_v=val(208))
    for blank in (Value(None, _src(), None), Value(None, _src(), "")):
        c = Circuit("LP-1", "1", _src(), poles=val(2), voltage_v=blank)
        assert effective_voltage(c, p).value == 208


@pytest.mark.parametrize("poles", [0, 4, 2.5, -1, 10_000_000, float("nan")])
def test_poles_out_of_range_not_usable(poles):
    v = check_value("poles", Value(poles, _src()))
    assert not v.usable and v.confidence == Confidence.LOW and v.source.note
    assert check_value("poles", Value(3, _src())).usable


def test_demand_va_supplied_zero_not_usable():
    v = check_value("demand_va_supplied", Value(0, _src()))
    assert not v.usable and "zero" in v.source.note


def test_check_value_huge_int_raises_type_error():
    with pytest.raises(TypeError):
        check_value("breaker_a", Value(MAX_INT + 1, _src()))
    with pytest.raises(TypeError):
        check_value("conductor_size", Value(5, _src()))
    assert check_value("breaker_a", Value(MAX_INT, _src())).usable


@pytest.mark.parametrize(
    "name",
    ["poles", "phases", "wires", "sets_in_parallel", "conductors_in_raceway", "insulation_temp_c"],
)
def test_int_field_fraction_not_usable(name, val):
    v = check_value(name, val(2.5))
    assert not v.usable and "not a whole number" in v.source.note
    assert check_value(name, val(3.0)).usable


@pytest.mark.parametrize("n", [0, 2, 4, 3.5])
def test_phases_not_one_or_three_not_usable(n, val):
    v = check_value("phases", val(n))
    assert not v.usable and v.confidence == Confidence.LOW
    assert check_value("phases", val(1)).usable and check_value("phases", val(3)).usable
    assert check_value("phases", val(1.0)).usable


@pytest.mark.parametrize("key", ["paths", "sheet_units"])
def test_project_json_refuses_paths_and_sheet_units(key):
    with pytest.raises(ValueError, match=f"{key}.*not read from a demo project"):
        project_from_dict({"name": "demo", key: []})


def test_device_detection_checked():
    src = {"file": "a.csv", "locator": "r", "method": "csv", "confidence": "HIGH"}

    def proj(detection):
        dev = {"type": "x", "source": src, "detection": detection}
        return project_from_dict({"name": "d", "devices": [dev]})

    for d in ("list", "block", "paper", "nested", "unused", "detector"):
        assert proj(d).devices[0].detection == d
    with pytest.raises(ValueError, match="unknown detection: guess"):
        proj("guess")


def test_egress_path_defaults():
    s = _src()
    a, b = EgressPath("P1", "E-101", s), EgressPath("P2", "E-101", s)
    assert a.points == [] and a.points is not b.points
    p = Project("demo")
    assert p.paths == [] and p.sheet_units == {}
    assert Device("exit_sign", s).detection == "list"
