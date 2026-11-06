from redline.engine import run
from redline.findings import Severity
from redline.model import Circuit, Confidence, Method, Panel, Project, Source, Value
from redline.rules.completeness import SPEC

SRC = Source("t.csv", "row 5", Method.CSV, Confidence.HIGH)


def _full(val, number, **over):
    kw = {
        "description": val("Lights"),
        "load_va": val(1000),
        "breaker_a": val(20),
        "conductor_size": val("12 AWG"),
    }
    return Circuit("LP-1", number, SRC, **{**kw, **over})


def _run(circuits, cfg):
    project = Project("p", panels=[Panel("LP-1", SRC, circuits=circuits)])
    return list(run(project, cfg, [SPEC]).findings)


def test_rule_completeness_trigger(val, test_cfg):
    blank = _full(val, "1", description=val(""))
    tbd = _full(val, "2", load_va=Value(None, SRC, "TBD"))
    f1, f2 = _run([blank, tbd], test_cfg)
    assert f1.severity == f2.severity == Severity.NEEDS_REVIEW
    assert f1.rule_ref == "TEST drawing standard CMP-1"
    assert f1.source.locator == "row 5"
    assert "LP-1 ckt 1" in f1.message and "description" in f1.message
    assert "load_va" in f2.message and '"TBD"' in f2.message
    assert f1.suggested_fix


def test_rule_completeness_pass(val, test_cfg):
    assert _run([_full(val, "1")], test_cfg) == []


def test_rule_completeness_spare_has_no_finding(val, test_cfg):
    spare = Circuit("LP-1", "3", SRC, description=val("SPARE"), is_spare=True)
    assert _run([spare], test_cfg) == []


def test_rule_completeness_low_input(val, test_cfg):
    c = _full(val, "1", breaker_a=val(20, Confidence.LOW, locator="row 5 breaker"))
    (f,) = _run([c], test_cfg)
    assert f.severity == Severity.NEEDS_REVIEW
    assert "breaker_a" in f.message and "row 5 breaker" in f.message


def test_rule_completeness_unverified_table(val, test_cfg, cfg_unverify):
    circuits = [_full(val, "1", description=val("")), _full(val, "2")]
    base = _run(circuits, test_cfg)
    cfg = test_cfg
    for t in cfg.cec["tables"]:
        cfg = cfg_unverify(cfg, t)
    assert _run(circuits, cfg) == base


def test_rule_completeness_severity_from_config(val, test_cfg, cfg_set):
    cfg = cfg_set(test_cfg, ("completeness", "severity"), "INFO")
    (f,) = _run([_full(val, "1", description=val(""))], cfg)
    assert f.severity == Severity.INFO


def test_rule_completeness_severity_case_insensitive(val, test_cfg, cfg_set):
    cfg = cfg_set(test_cfg, ("completeness", "severity"), "needs_review")
    (f,) = _run([_full(val, "1", description=val(""))], cfg)
    assert f.severity == Severity.NEEDS_REVIEW
