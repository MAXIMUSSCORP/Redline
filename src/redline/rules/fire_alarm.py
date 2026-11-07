from __future__ import annotations

from redline.config import Config, rule_ref
from redline.engine import RuleSpec
from redline.findings import Finding, Severity
from redline.model import Project

ID = "fire_alarm"
ITEMS = (
    ("fire_alarm_exit_signs", "Exit signs"),
    ("fire_alarm_pull_stations", "Fire alarm pull stations"),
    ("emergency_lighting", "Emergency lighting"),
)


def check(project: Project, cfg: Config) -> list[Finding]:
    return [
        Finding(
            ID,
            Severity.NOT_CHECKED,
            f"{name}: not checked. This check is not built yet.",
            rule_ref(cfg, key),
            None,
            (),
            "Check this item by hand against the drawings.",
        )
        for key, name in ITEMS
    ]


SPEC = RuleSpec(ID, "Fire alarm and egress", check)
