from redline.engine import run
from redline.findings import Severity
from redline.model import Circuit, Confidence, Method, Panel, Project, Source
from redline.rules.phase_balance import SPEC

SRC = Source("t.csv", "row 1", Method.CSV, Confidence.HIGH)


def _panel(val, loads, by_column=True, phase_count=3):
    cs = []
    for i, (load, ph) in enumerate(zip(loads, "ABC" * 9, strict=False), 1):
        c = Circuit("LP-1", str(i), SRC, load_va=val(load, locator=f"row {i} load"))
        if by_column:
            c.phases_used = val(ph)
        else:
            c.poles = val(1)
        cs.append(c)
    return Panel("LP-1", SRC, phases=val(phase_count), circuits=cs)


def _run(panel, cfg):
    return list(run(Project("p", panels=[panel]), cfg, [SPEC]).findings)


def test_rule_phase_balance_trigger(val, test_cfg):
    info, f = _run(_panel(val, [3000, 1000, 1000]), test_cfg)
    assert info.severity == Severity.INFO and "A 3000 VA" in info.message
    assert f.severity == Severity.NEEDS_REVIEW
    assert f.rule_id == "phase_balance"
    assert f.rule_ref == "TEST practice PB-1"
    assert f.source.locator == "row 1"
    assert "LP-1 ckt 1" in f.suggested_fix


def test_rule_phase_balance_never_above_needs_review(val, test_cfg):
    out = _run(_panel(val, [9000, 1, 1]), test_cfg)
    assert {f.severity for f in out} == {Severity.INFO, Severity.NEEDS_REVIEW}


def test_rule_phase_balance_pass(val, test_cfg):
    (info,) = _run(_panel(val, [1000, 1000, 1000]), test_cfg)
    assert info.severity == Severity.INFO


def test_rule_phase_balance_low_input(val, test_cfg):
    p = _panel(val, [1000, 1000, 1000])
    p.circuits[1].load_va = val(1000, Confidence.LOW, locator="row 2 load")
    (f,) = _run(p, test_cfg)
    assert f.severity == Severity.NEEDS_REVIEW
    assert "ckt 2 load_va" in f.message and "row 2 load" in f.message


def test_rule_phase_balance_unverified_table(val, test_cfg, cfg_unverify):
    cfg = cfg_unverify(test_cfg, "phase_balance")
    out = _run(_panel(val, [3000, 1000, 1000]), cfg)
    assert [f.severity for f in out] == [Severity.INFO, Severity.NEEDS_REVIEW]


def test_rule_phase_balance_position_is_medium(val, test_cfg):
    (info,) = _run(_panel(val, [1000] * 6, by_column=False), test_cfg)
    assert "placed by position" in info.message
    phase_inputs = [i for i in info.inputs_used if i.field.endswith("phase")]
    assert {i.confidence for i in phase_inputs} == {Confidence.MEDIUM}


def test_rule_phase_balance_single_phase_panel_not_checked(val, test_cfg):
    (f,) = _run(_panel(val, [3000, 1000, 1000], phase_count=1), test_cfg)
    assert f.severity == Severity.NOT_CHECKED
    assert "LP-1" in f.message and "single-phase" in f.message
    assert f.suggested_fix and "move" not in f.suggested_fix.lower()


def test_rule_phase_balance_duplicate_label_low_load_gated(val, test_cfg):
    p = _panel(val, [1000, 1000, 1000])
    p.circuits[1].number = "1"
    p.circuits[0].load_va = val(1000, Confidence.LOW, locator="row 1 load")
    (f,) = _run(p, test_cfg)
    assert f.severity == Severity.NEEDS_REVIEW
    assert "row 1 load" in f.message


def test_rule_phase_balance_phase_shown_without_tuple(val, test_cfg):
    info, _ = _run(_panel(val, [3000, 1000, 1000]), test_cfg)
    assert "(" not in "".join(i.value for i in info.inputs_used if i.field.endswith("phase"))


def test_rule_phase_balance_too_few_circuits_not_checked(val, test_cfg):
    (f,) = _run(_panel(val, [3000, 1000]), test_cfg)
    assert f.severity == Severity.NOT_CHECKED and "Fewer than" in f.message
    assert f.suggested_fix and "move" not in f.suggested_fix.lower()
