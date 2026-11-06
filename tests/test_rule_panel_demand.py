from redline.engine import run
from redline.findings import Severity
from redline.model import Circuit, Confidence, Method, Panel, Project, Source, Value
from redline.rules.panel_demand import SPEC

SRC = Source("t.csv", "row 1", Method.CSV, Confidence.HIGH)
MLO = Value(None, Source("t.csv", "row 1", Method.CSV, Confidence.HIGH, note="MLO"))


def _panel(val, loads, main=100, supplied=None):
    cs = [
        Circuit("LP-1", str(i), SRC, load_va=val(v), load_type=val("continuous"))
        for i, v in enumerate(loads, 1)
    ]
    p = Panel(
        "LP-1",
        SRC,
        voltage_v=val(100),
        phases=val(1),
        bus_rating_a=val(100, locator="row 1 bus"),
        main_breaker_a=main if isinstance(main, Value) else val(main),
        circuits=cs,
    )
    if supplied is not None:
        p.demand_va_supplied = val(supplied)
    return p


def _run(panel, cfg):
    return list(run(Project("p", panels=[panel]), cfg, [SPEC]).findings)


def test_rule_panel_demand_trigger(val, test_cfg):
    out = _run(_panel(val, [10000, 10000]), test_cfg)
    info, *bad = out
    assert info.severity == Severity.INFO and "source computed" in info.message
    assert len(bad) == 2 and all(f.severity == Severity.VIOLATION for f in bad)
    assert bad[0].rule_ref == "TEST Rule DEM-1"
    assert bad[0].source.locator == "row 1"
    assert bad[0].suggested_fix


def test_rule_panel_demand_pass(val, test_cfg):
    (info,) = _run(_panel(val, [4000]), test_cfg)
    assert info.severity == Severity.INFO and "source computed" in info.message


def test_rule_panel_demand_low_input(val, test_cfg):
    p = _panel(val, [4000])
    p.bus_rating_a = val(100, Confidence.LOW, locator="row 1 bus")
    (f,) = _run(p, test_cfg)
    assert f.severity == Severity.NEEDS_REVIEW
    assert "bus_rating_a" in f.message and "row 1 bus" in f.message


def test_rule_panel_demand_unverified_table(val, test_cfg, cfg_unverify):
    out = _run(_panel(val, [10000, 10000]), cfg_unverify(test_cfg, "demand_factors"))
    assert Severity.VIOLATION not in {f.severity for f in out}
    assert "not verified" in out[1].message


def test_supplied_demand_overrides_computed(val, test_cfg):
    info, diff = _run(_panel(val, [5000], main=200, supplied=8000), test_cfg)
    assert "8000 VA, source user_supplied" in info.message
    assert "5000 VA" in diff.message and "supplied" in diff.message
    assert diff.severity == Severity.INFO


def test_rule_panel_demand_mlo_checks_bus_only(val, test_cfg, cfg_set):
    cfg = cfg_set(test_cfg, ("tables", "demand_factors", "main_loading_limit_fraction"), 0.01)
    (info,) = _run(_panel(val, [4000], main=MLO), cfg)
    assert "MLO panel, bus checked only" in info.message


def test_rule_panel_demand_null_table_entry(val, test_cfg, cfg_set):
    cfg = cfg_set(test_cfg, ("tables", "demand_factors", "by_load_type", "continuous"), None)
    (f,) = _run(_panel(val, [4000]), cfg)
    assert f.severity == Severity.NEEDS_REVIEW and "Table entry missing" in f.message


def test_rule_panel_demand_duplicate_label_low_load_gated(val, test_cfg):
    p = _panel(val, [4000, 4000])
    p.circuits[1].number = "1"
    p.circuits[0].load_va = val(4000, Confidence.LOW, locator="row 1 load")
    (f,) = _run(p, test_cfg)
    assert f.severity == Severity.NEEDS_REVIEW
    assert "row 1 load" in f.message


def test_rule_panel_demand_violation_wording(val, test_cfg):
    _, bus, _ = _run(_panel(val, [10000, 10000]), test_cfg)
    assert "of the" not in bus.message and bus.rule_ref in bus.message


def test_rule_panel_demand_non_finite_result_needs_review(val, test_cfg):
    out = _run(_panel(val, [1e308, 1e308, 1e308]), test_cfg)
    assert [f.severity for f in out] == [Severity.NEEDS_REVIEW]
    assert "could not be computed" in out[0].message and "LP-1" in out[0].message
    panel = _panel(val, [100], supplied=1e308)
    panel.voltage_v = val(0.001)
    out = _run(panel, test_cfg)
    assert [f.severity for f in out] == [Severity.NEEDS_REVIEW]
    assert "could not be computed" in out[0].message
