from redline.engine import run
from redline.findings import Severity
from redline.model import Circuit, Confidence, Method, Panel, Project, Source
from redline.rules.bonding import SPEC

SRC = Source("t.csv", "row 5", Method.CSV, Confidence.HIGH)


def _project(val, number="1", breaker=20, material="Cu", bonding="14 AWG", conf=Confidence.HIGH):
    c = Circuit("LP-1", number, SRC, breaker_a=val(breaker), conductor_material=val(material))
    if bonding is not None:
        c.bonding_size = val(bonding, conf, locator="row 5 bond")
    return Project("p", panels=[Panel("LP-1", SRC, circuits=[c])])


def _run(project, cfg):
    return list(run(project, cfg, [SPEC]).findings)


def _rows(cfg, cfg_set, copper):
    row = {"max_ocpd_a": 20, "copper_size": copper, "aluminum_size": "10 AWG"}
    return cfg_set(cfg, ("tables", "bonding_conductor_size", "values"), [row])


def test_rule_bonding_trigger(val, test_cfg, cfg_set):
    cfg = _rows(test_cfg, cfg_set, "12 AWG")
    (f,) = _run(_project(val, bonding="14 AWG"), cfg)
    assert f.severity == Severity.VIOLATION
    assert f.rule_id == "bonding"
    assert f.rule_ref == "TEST Rule BOND-1"
    assert f.source.locator == "row 5"
    assert "LP-1 ckt 1" in f.message and "12 AWG" in f.message
    assert f.suggested_fix


def test_rule_bonding_pass(val, test_cfg, cfg_set):
    cfg = _rows(test_cfg, cfg_set, "14 AWG")
    assert _run(_project(val, bonding="10 AWG"), cfg) == []
    assert _run(_project(val, bonding="14 AWG"), cfg) == []


def test_rule_bonding_low_input(val, test_cfg):
    (f,) = _run(_project(val, conf=Confidence.LOW), test_cfg)
    assert f.severity == Severity.NEEDS_REVIEW
    assert "bonding_size" in f.message and "row 5 bond" in f.message


def test_rule_bonding_unverified_table(val, test_cfg, cfg_set, cfg_unverify):
    cfg = cfg_unverify(_rows(test_cfg, cfg_set, "12 AWG"), "bonding_conductor_size")
    (f,) = _run(_project(val), cfg)
    assert f.severity == Severity.NEEDS_REVIEW
    assert "not verified" in f.message


def test_rule_bonding_omitted_groups_per_panel(val, test_cfg):
    p = _project(val, "1", bonding=None)
    p.panels[0].circuits.append(Circuit("LP-1", "3", SRC, breaker_a=val(20)))
    p.panels[0].circuits.append(Circuit("LP-1", "5", SRC, is_spare=True))
    (f,) = _run(p, test_cfg)
    assert f.severity == Severity.NEEDS_REVIEW
    assert "not shown" in f.message and "ckt 1" in f.message and "ckt 3" in f.message
    assert "ckt 5" not in f.message


def test_rule_bonding_null_table_entry(val, test_cfg, cfg_set):
    (f,) = _run(_project(val), _rows(test_cfg, cfg_set, None))
    assert f.severity == Severity.NEEDS_REVIEW
    assert "Table entry missing" in f.message
