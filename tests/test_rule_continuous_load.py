from redline import engine
from redline.model import Circuit, Confidence, Method, Panel, Project, Source
from redline.rules.continuous_load import SPEC

SRC = Source("test.csv", "row 7", Method.CSV, Confidence.HIGH)


def _cfg(cfg, cfg_set):
    return cfg_set(cfg, ("tables", "continuous_load", "max_fraction_of_breaker"), 0.5)


def _project(val, va=1500, **over):
    fields = {
        "load_type": val("continuous"),
        "breaker_a": val(20),
        "load_va": val(va),
        "poles": val(2),
    }
    c = Circuit(panel="LP-1", number="7", source=SRC, **{**fields, **over})
    return Project("t", panels=[Panel("LP-1", SRC, voltage_v=val(100), circuits=[c])])


def test_rule_continuous_load_trigger(test_cfg, cfg_set, val):
    (f,) = engine.run(_project(val), _cfg(test_cfg, cfg_set), [SPEC]).findings
    assert (f.rule_id, f.severity.value) == ("continuous_load", "VIOLATION")
    assert f.rule_ref == "TEST Rule CON-1"
    assert f.source.locator == "row 7"
    assert f.suggested_fix
    assert "LP-1 ckt 7" in f.message and f.rule_ref in f.message
    assert "15.0 A" in f.message and "10.0 A" in f.message


def test_rule_continuous_load_pass(test_cfg, cfg_set, val):
    assert engine.run(_project(val, 800), _cfg(test_cfg, cfg_set), [SPEC]).findings == ()


def test_rule_continuous_load_three_pole(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set)
    assert engine.run(_project(val, poles=val(3)), cfg, [SPEC]).findings == ()
    (f,) = engine.run(_project(val, 3000, poles=val(3)), cfg, [SPEC]).findings
    assert f.severity.value == "VIOLATION"


def test_rule_continuous_load_noncontinuous_not_checked(test_cfg, cfg_set, val):
    project = _project(val, load_type=val("noncontinuous"))
    assert engine.run(project, _cfg(test_cfg, cfg_set), [SPEC]).findings == ()


def test_rule_continuous_load_unknown_type_needs_review(test_cfg, cfg_set, val):
    project = _project(val, load_type=val("unknown"))
    (f,) = engine.run(project, _cfg(test_cfg, cfg_set), [SPEC]).findings
    assert f.severity.value == "NEEDS_REVIEW"
    assert "LP-1 ckt 7" in f.message and "continuous" in f.message
    assert f.suggested_fix


def test_rule_continuous_load_low_input(test_cfg, cfg_set, val):
    low = val(1500, Confidence.LOW, locator="cell D9")
    (f,) = engine.run(_project(val, load_va=low), _cfg(test_cfg, cfg_set), [SPEC]).findings
    assert f.severity.value == "NEEDS_REVIEW"
    assert "load_va" in f.message and "cell D9" in f.message


def test_rule_continuous_load_unverified_table(test_cfg, cfg_set, cfg_unverify, val):
    cfg = cfg_unverify(_cfg(test_cfg, cfg_set), "continuous_load")
    (f,) = engine.run(_project(val), cfg, [SPEC]).findings
    assert f.severity.value == "NEEDS_REVIEW"
    assert "not verified" in f.message


def test_rule_continuous_load_null_table_entry(test_cfg, cfg_set, val):
    cfg = cfg_set(test_cfg, ("tables", "continuous_load", "max_fraction_of_breaker"), None)
    (f,) = engine.run(_project(val), cfg, [SPEC]).findings
    assert f.severity.value == "NEEDS_REVIEW"
    assert "table entry missing" in f.message.lower()
