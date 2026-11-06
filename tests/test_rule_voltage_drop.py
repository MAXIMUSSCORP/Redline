from redline import engine
from redline.model import Circuit, Confidence, Feeder, Method, Panel, Project, Source
from redline.rules.voltage_drop import SPEC

SRC = Source("test.csv", "row 7", Method.CSV, Confidence.HIGH)
VD = ("tables", "voltage_drop")


def _cfg(cfg, cfg_set, show_passing=False):
    # k_factor chosen so a 10 A load over L metres drops L volts on a 100 V circuit
    for path, v in {
        ("method",): "k_factor",
        ("current_basis",): "load",
        ("show_passing",): show_passing,
        ("branch_max_pct",): 2,
        ("feeder_max_pct",): 2,
        ("total_max_pct",): 2.5,
        ("k_factor", "constant_by_material", "copper"): 1,
        ("k_factor", "area_by_size", "12 AWG"): 10,
        ("k_factor", "phase_multiplier", "single"): 1,
    }.items():
        cfg = cfg_set(cfg, (*VD, *path), v)
    return cfg


def _circuit(val, length, **over):
    fields = {
        "length_m": val(length),
        "conductor_size": val("12 AWG"),
        "conductor_material": val("Cu"),
        "poles": val(1),
        "load_va": val(1000),
    }
    return Circuit(panel="LP-1", number="7", source=SRC, **{**fields, **over})


def _project(val, length=1.5, feeder_length=None, **over):
    panel = Panel("LP-1", SRC, voltage_v=val(100), circuits=[_circuit(val, length, **over)])
    feeders = []
    if feeder_length is not None:
        panel.fed_from = val("MDP")
        feeders = [
            Feeder(
                "F-1",
                SRC,
                from_panel=val("MDP"),
                to_panel=val("LP-1"),
                length_m=val(feeder_length),
                conductor_size=val("12 AWG"),
                conductor_material=val("Cu"),
                voltage_v=val(100),
                phases=val(1),
                load_va=val(1000),
                sets_in_parallel=val(1),
            )
        ]
    return Project("t", panels=[panel], feeders=feeders)


def test_rule_voltage_drop_trigger(test_cfg, cfg_set, val):
    (f,) = engine.run(_project(val, 5), _cfg(test_cfg, cfg_set), [SPEC]).findings
    assert (f.rule_id, f.severity.value) == ("voltage_drop", "VIOLATION")
    assert f.rule_ref == "TEST Rule VD-1"
    assert f.source.locator == "row 7"
    assert f.suggested_fix
    assert "LP-1 ckt 7" in f.message and f.rule_ref in f.message
    assert "5.00%" in f.message


def test_rule_voltage_drop_pass(test_cfg, cfg_set, val):
    assert engine.run(_project(val), _cfg(test_cfg, cfg_set), [SPEC]).findings == ()


def test_rule_voltage_drop_show_passing(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set, show_passing=True)
    (f,) = engine.run(_project(val), cfg, [SPEC]).findings
    assert f.severity.value == "INFO"


def test_rule_voltage_drop_impedance_method(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set)
    for path, v in {
        ("method",): "impedance",
        ("impedance", "power_factor"): 1,
        ("impedance", "phase_multiplier", "single"): 1,
        ("impedance", "per_size", "copper", "12 AWG", "r"): 1,
        ("impedance", "per_size", "copper", "12 AWG", "x"): 0,
    }.items():
        cfg = cfg_set(cfg, (*VD, *path), v)
    (f,) = engine.run(_project(val, 5), cfg, [SPEC]).findings
    assert f.severity.value == "VIOLATION" and "50.00%" in f.message


def test_rule_voltage_drop_low_input(test_cfg, cfg_set, val):
    low = val(1.5, Confidence.LOW, locator="cell F9")
    (f,) = engine.run(_project(val, length_m=low), _cfg(test_cfg, cfg_set), [SPEC]).findings
    assert f.severity.value == "NEEDS_REVIEW"
    assert "length_m" in f.message and "cell F9" in f.message
    assert "LP-1 ckt 7" in f.message


def test_rule_voltage_drop_unverified_table(test_cfg, cfg_set, cfg_unverify, val):
    cfg = cfg_unverify(_cfg(test_cfg, cfg_set), "voltage_drop")
    (f,) = engine.run(_project(val, 5), cfg, [SPEC]).findings
    assert f.severity.value == "NEEDS_REVIEW"
    assert "not verified" in f.message


def test_rule_voltage_drop_null_table_entry(test_cfg, cfg_set, val):
    cfg = cfg_set(_cfg(test_cfg, cfg_set), (*VD, "k_factor", "area_by_size", "12 AWG"), None)
    (f,) = engine.run(_project(val, 5), cfg, [SPEC]).findings
    assert f.severity.value == "NEEDS_REVIEW"
    assert "table entry missing" in f.message.lower()


def test_total_fails_while_parts_pass(test_cfg, cfg_set, val):
    result = engine.run(_project(val, 1.5, feeder_length=1.5), _cfg(test_cfg, cfg_set), [SPEC])
    (f,) = result.findings
    assert f.severity.value == "VIOLATION"
    assert "total voltage drop 3.00%" in f.message
    assert "LP-1 ckt 7" in f.message


def test_rule_voltage_drop_broken_chain_not_checked(test_cfg, cfg_set, val):
    project = _project(val, 1.5, feeder_length=1.5)
    project.feeders = []
    (f,) = engine.run(project, _cfg(test_cfg, cfg_set), [SPEC]).findings
    assert f.severity.value == "NOT_CHECKED"
    assert "no feeder shown into LP-1" in f.message
