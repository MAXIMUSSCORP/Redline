from redline.config import rule_ref
from redline.engine import run
from redline.findings import Severity
from redline.model import Confidence, Device, Method, Project, Source
from redline.rules.fire_alarm import SPEC

KEYS = ("fire_alarm_exit_signs", "fire_alarm_pull_stations", "emergency_lighting")


def _check(project, cfg):
    findings = run(project, cfg, [SPEC]).findings
    assert len(findings) == 3
    assert all(f.severity == Severity.NOT_CHECKED for f in findings)
    assert [f.rule_ref for f in findings] == [rule_ref(cfg, k) for k in KEYS]
    assert all(f.suggested_fix and f.rule_id == "fire_alarm" for f in findings)


def test_rule_fire_alarm_three_not_checked(test_cfg):
    _check(Project("empty"), test_cfg)


def test_rule_fire_alarm_low_input(val, test_cfg):
    src = Source("t.csv", "row 2", Method.CSV, Confidence.LOW)
    dev = Device("exit_sign", src, tag=val("EX-1", Confidence.LOW))
    _check(Project("p", devices=[dev]), test_cfg)
