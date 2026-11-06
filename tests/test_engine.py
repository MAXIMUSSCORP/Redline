from redline.engine import RuleSpec, run
from redline.findings import Finding, Severity
from redline.model import Project


def _violating(project, cfg):
    return [Finding("v", Severity.VIOLATION, "over.", "ref", None)]


def _boom(project, cfg):
    raise ValueError("bad input")


def _quiet(project, cfg):
    return []


def test_rule_error_becomes_not_checked(test_cfg):
    result = run(
        Project("p"), test_cfg, [RuleSpec("boom", "Boom", _boom), RuleSpec("q", "Q", _quiet)]
    )
    assert result.ran == ("q",)
    assert result.skipped[0][0] == "boom"
    assert "ValueError" in result.skipped[0][1]
    (f,) = [f for f in result.findings if f.rule_id == "boom"]
    assert f.severity == Severity.NOT_CHECKED
    assert "ValueError" in f.message and "bad input" in f.message


def test_skip_records_not_checked(test_cfg):
    result = run(Project("p"), test_cfg, [RuleSpec("q", "Q", _quiet)], skip={"q"})
    assert result.ran == ()
    assert result.skipped == (("q", "skipped by request"),)
    assert "did not run: skipped by request" in result.findings[0].message
    assert result.findings[0].severity == Severity.NOT_CHECKED


def test_gate_applies_to_every_rule(test_cfg, cfg_unverify):
    spec = RuleSpec("v", "V", _violating, tables_used=("voltage_drop",))
    assert run(Project("p"), test_cfg, [spec]).findings[0].severity == Severity.VIOLATION
    result = run(Project("p"), cfg_unverify(test_cfg, "voltage_drop"), [spec])
    assert result.findings[0].severity == Severity.NEEDS_REVIEW
    assert result.unverified == {"v": ("voltage_drop",)}


def test_skeleton_downgrades_all(skeleton_cfg):
    spec = RuleSpec("v", "V", _violating, tables_used=("ampacity",))
    result = run(Project("p"), skeleton_cfg, [spec])
    assert all(f.severity != Severity.VIOLATION for f in result.findings)


def test_order_and_ran(test_cfg):
    specs = [RuleSpec("b", "B", _quiet), RuleSpec("a", "A", _quiet)]
    result = run(Project("p"), test_cfg, specs)
    assert result.ran == ("b", "a")
    assert result.unverified == {}
