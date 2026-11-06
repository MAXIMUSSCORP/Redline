from redline import engine
from redline.model import Circuit, Confidence, Method, Panel, Project, Source
from redline.rules.ampacity import SPEC

SRC = Source("test.csv", "row 7", Method.CSV, Confidence.HIGH)
CELL = ("tables", "conductor_ampacity", "values", "copper", "12 AWG")


def _cfg(cfg, cfg_set, base, temp="75"):
    cfg = cfg_set(cfg, (*CELL, temp), base)
    for t in ("60", "75", "90"):
        cfg = cfg_set(cfg, ("tables", "ambient_temp_correction", "values", t), [[100, 1.0]])
    return cfg_set(cfg, ("tables", "conductor_count_correction", "values"), [[100, 1.0]])


def _project(val, temp=75, **over):
    fields = {
        "breaker_a": val(20),
        "conductor_size": val("12 AWG"),
        "conductor_material": val("Cu"),
        "insulation_temp_c": val(temp),
        "conductors_in_raceway": val(3),
        "ambient_c": val(30),
    }
    c = Circuit(panel="LP-1", number="7", source=SRC, **{**fields, **over})
    return Project("t", panels=[Panel("LP-1", SRC, circuits=[c])])


def test_rule_ampacity_trigger(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set, 15)
    (f,) = engine.run(_project(val), cfg, [SPEC]).findings
    assert (f.rule_id, f.severity.value) == ("ampacity", "VIOLATION")
    assert f.rule_ref == "TEST Rule AMP-1"
    assert f.source.locator == "row 7"
    assert f.suggested_fix
    assert "LP-1 ckt 7" in f.message
    assert f.rule_ref in f.message
    assert "compliant" not in f.message.lower()


def test_rule_ampacity_pass(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set, 25)
    assert engine.run(_project(val), cfg, [SPEC]).findings == ()


def test_rule_ampacity_factors_applied(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set, 40)
    cfg = cfg_set(cfg, ("tables", "ambient_temp_correction", "values", "75"), [[100, 0.5]])
    assert engine.run(_project(val), cfg, [SPEC]).findings == ()
    cfg = cfg_set(cfg, ("tables", "conductor_count_correction", "values"), [[100, 0.5]])
    (f,) = engine.run(_project(val), cfg, [SPEC]).findings
    assert f.severity.value == "VIOLATION"
    assert "corrected ampacity 10 A" in f.message


def test_rule_ampacity_termination_limits_column(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set, 15)
    cfg = cfg_set(cfg, (*CELL, "90"), 100)
    (f,) = engine.run(_project(val, temp=90), cfg, [SPEC]).findings
    assert f.severity.value == "VIOLATION"


def test_rule_ampacity_next_standard_size(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set, 15)
    cfg = cfg_set(cfg, ("tables", "standard_breaker_ratings", "values_a"), [10, 20, 30])
    cfg = cfg_set(cfg, ("tables", "allow_next_standard_size", "enabled"), True)
    assert engine.run(_project(val), cfg, [SPEC]).findings == ()
    cfg = cfg_set(cfg, ("tables", "standard_breaker_ratings", "values_a"), [10, 12])
    assert engine.run(_project(val), cfg, [SPEC]).findings[0].severity.value == "VIOLATION"


def test_rule_ampacity_low_input(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set, 15)
    low = val(20, Confidence.LOW, locator="cell B9")
    (f,) = engine.run(_project(val, breaker_a=low), cfg, [SPEC]).findings
    assert f.severity.value == "NEEDS_REVIEW"
    assert "breaker_a" in f.message and "cell B9" in f.message
    assert "LP-1 ckt 7" in f.message


def test_rule_ampacity_unverified_table(test_cfg, cfg_set, cfg_unverify, val):
    cfg = cfg_unverify(_cfg(test_cfg, cfg_set, 15), "conductor_ampacity")
    (f,) = engine.run(_project(val), cfg, [SPEC]).findings
    assert f.severity.value == "NEEDS_REVIEW"
    assert "not verified" in f.message


def test_rule_ampacity_null_table_entry(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set, 15)
    cfg = cfg_set(cfg, ("tables", "ambient_temp_correction", "values", "75"), None)
    (f,) = engine.run(_project(val), cfg, [SPEC]).findings
    assert f.severity.value == "NEEDS_REVIEW"
    assert "table entry missing" in f.message.lower()
