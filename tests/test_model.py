from redline.findings import Severity, input_gate, inputs_used
from redline.model import (
    Circuit,
    Confidence,
    Method,
    Panel,
    Source,
    Value,
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


def test_effective_voltage_falls_back_to_panel(val):
    p = Panel("LP-1", _src(), voltage_v=val(120))
    c = Circuit("LP-1", "1", _src())
    assert effective_voltage(c, p).value == 120
    c.voltage_v = val(277)
    assert effective_voltage(c, p).value == 277


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
