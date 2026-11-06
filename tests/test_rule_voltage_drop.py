from dataclasses import replace

from redline import engine
from redline.model import Circuit, Confidence, Feeder, Method, Panel, Project, Source, Value
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


def _run(project, cfg):
    """Findings without the per-panel note that a panel's own feed is not shown."""
    out = engine.run(project, cfg, [SPEC]).findings
    return tuple(f for f in out if "Supply above" not in f.message)


def _circuit(val, length, **over):
    fields = {
        "length_m": val(length),
        "conductor_size": val("12 AWG"),
        "conductor_material": val("Cu"),
        "poles": val(2),
        "load_va": val(1000),
    }
    return Circuit(panel="LP-1", number="7", source=SRC, **{**fields, **over})


def _project(val, length=1.5, feeder_length=None, **over):
    panel = Panel("LP-1", SRC, voltage_v=val(100), circuits=[_circuit(val, length, **over)])
    feeders = []
    mdp = Panel("MDP", SRC)
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
    return Project("t", panels=[panel, mdp] if feeders else [panel], feeders=feeders)


def test_rule_voltage_drop_trigger(test_cfg, cfg_set, val):
    (f,) = _run(_project(val, 5), _cfg(test_cfg, cfg_set))
    assert (f.rule_id, f.severity.value) == ("voltage_drop", "VIOLATION")
    assert f.rule_ref == "TEST Rule VD-1"
    assert f.source.locator == "row 7"
    assert f.suggested_fix
    assert "LP-1 ckt 7" in f.message and f.rule_ref in f.message
    assert "5.00%" in f.message


def test_rule_voltage_drop_pass(test_cfg, cfg_set, val):
    assert _run(_project(val), _cfg(test_cfg, cfg_set)) == ()


def test_rule_voltage_drop_show_passing(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set, show_passing=True)
    (f,) = _run(_project(val), cfg)
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
    (f,) = _run(_project(val, 5), cfg)
    assert f.severity.value == "VIOLATION" and "50.00%" in f.message


def test_rule_voltage_drop_low_input(test_cfg, cfg_set, val):
    low = val(1.5, Confidence.LOW, locator="cell F9")
    (f,) = _run(_project(val, length_m=low), _cfg(test_cfg, cfg_set))
    assert f.severity.value == "NEEDS_REVIEW"
    assert "length_m" in f.message and "cell F9" in f.message
    assert "LP-1 ckt 7" in f.message


def test_rule_voltage_drop_unverified_table(test_cfg, cfg_set, cfg_unverify, val):
    cfg = cfg_unverify(_cfg(test_cfg, cfg_set), "voltage_drop")
    (f,) = _run(_project(val, 5), cfg)
    assert f.severity.value == "NEEDS_REVIEW"
    assert "not verified" in f.message


def test_rule_voltage_drop_null_table_entry(test_cfg, cfg_set, val):
    cfg = cfg_set(_cfg(test_cfg, cfg_set), (*VD, "k_factor", "area_by_size", "12 AWG"), None)
    (f,) = _run(_project(val, 5), cfg)
    assert f.severity.value == "NEEDS_REVIEW"
    assert "table entry missing" in f.message.lower()


def test_total_fails_while_parts_pass(test_cfg, cfg_set, val):
    result = _run(_project(val, 1.5, feeder_length=1.5), _cfg(test_cfg, cfg_set))
    (f,) = result
    assert f.severity.value == "VIOLATION"
    assert "total voltage drop at least 3.00%" in f.message
    assert "LP-1 ckt 7" in f.message


def test_rule_voltage_drop_broken_chain_not_checked(test_cfg, cfg_set, val):
    project = _project(val, 1.5, feeder_length=1.5)
    project.feeders = []
    (f,) = _run(project, _cfg(test_cfg, cfg_set))
    assert f.severity.value == "NOT_CHECKED"
    assert "no feeder shown into LP-1" in f.message


def _chain_project(val, **kw):
    return _project(val, 1.5, feeder_length=1.5, **kw)


def _raw(project, cfg):
    return engine.run(project, cfg, [SPEC]).findings


def test_rule_voltage_drop_total_low_feeder_link_not_checked(test_cfg, cfg_set, val):
    project = _chain_project(val)
    project.feeders[0].to_panel = val("LP-1", Confidence.LOW, locator="cell B2")
    (f,) = _run(project, _cfg(test_cfg, cfg_set))
    assert f.severity.value == "NOT_CHECKED"
    assert "feeder to_panel is LOW" in f.message


def test_rule_voltage_drop_total_unknown_source_panel_not_checked(test_cfg, cfg_set, val):
    project = _chain_project(val)
    project.panels = [project.panels[0]]
    (f,) = _run(project, _cfg(test_cfg, cfg_set))
    assert f.severity.value == "NOT_CHECKED"
    assert "source panel MDP not in project" in f.message


def test_rule_voltage_drop_total_missing_fed_from_not_checked(test_cfg, cfg_set, val):
    (f,) = _raw(_project(val), _cfg(test_cfg, cfg_set))
    assert f.severity.value == "NOT_CHECKED"
    assert "LP-1" in f.message and "Supply above LP-1 is not shown" in f.message


def test_rule_voltage_drop_total_cites_feeder_inputs(test_cfg, cfg_set, val):
    (f,) = _run(_chain_project(val), _cfg(test_cfg, cfg_set))
    assert f.severity.value == "VIOLATION"
    assert any(i.field.startswith("Feeder F-1") for i in f.inputs_used)


def test_rule_voltage_drop_total_within_limit_open_chain_not_checked(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set, show_passing=True)
    cfg = cfg_set(cfg, (*VD, "total_max_pct"), 50)
    out = _raw(_chain_project(val), cfg)
    note = [f for f in out if f.severity.value == "NOT_CHECKED"]
    assert len(note) == 1 and "Supply above MDP is not shown" in note[0].message
    assert not any("total voltage drop" in f.message and f.severity.value == "INFO" for f in out)


def test_rule_voltage_drop_total_over_limit_open_chain_violation(test_cfg, cfg_set, val):
    out = _raw(_chain_project(val), _cfg(test_cfg, cfg_set))
    (v,) = [f for f in out if f.severity.value == "VIOLATION"]
    assert "at least 3.00%" in v.message
    assert any(f.severity.value == "NOT_CHECKED" for f in out)


def test_rule_voltage_drop_non_finite_result_needs_review(test_cfg, cfg_set, val):
    (f,) = _run(_project(val, 1e308), _cfg(test_cfg, cfg_set))
    assert f.severity.value == "NEEDS_REVIEW"
    assert "could not be computed" in f.message and "LP-1 ckt 7" in f.message


def test_rule_voltage_drop_open_chain_wording(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set)
    (f,) = [f for f in _raw(_chain_project(val), cfg) if f.severity.value == "NOT_CHECKED"]
    assert "Supply above MDP is not shown" in f.message and "lower bound" in f.message
    assert "Broken link" not in f.message and "above MDP" in f.suggested_fix
    project = _chain_project(val)
    project.panels = [project.panels[0]]
    (g,) = _run(project, cfg)
    assert "Broken link" in g.message and "Show the missing link" in g.suggested_fix


def test_rule_voltage_drop_unparsed_fed_from_broken_link(test_cfg, cfg_set, val):
    project = _chain_project(val)
    project.panels[0].fed_from = Value(None, SRC, "TBD")
    (f,) = _run(project, _cfg(test_cfg, cfg_set))
    assert f.severity.value == "NOT_CHECKED"
    assert "Broken link" in f.message and "LP-1" in f.message


def test_rule_voltage_drop_ambiguous_feeder_broken_link(test_cfg, cfg_set, val):
    cfg = _cfg(test_cfg, cfg_set)
    twice = _chain_project(val)
    twice.feeders.append(replace(twice.feeders[0], id="F-2", length_m=val(0.1)))
    (f,) = _run(twice, cfg)
    assert f.severity.value == "NOT_CHECKED"
    assert "Broken link" in f.message and "2 feeders feed LP-1" in f.message
    wrong = _chain_project(val)
    wrong.feeders[0].from_panel = val("ELSEWHERE")
    (g,) = _run(wrong, cfg)
    assert g.severity.value == "NOT_CHECKED"
    assert "Broken link" in g.message and "from_panel disagrees" in g.message
