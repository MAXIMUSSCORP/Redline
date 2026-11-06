from __future__ import annotations

from redline.config import Config, rule_ref
from redline.engine import RuleSpec
from redline.findings import Finding, Severity, inputs_used
from redline.model import Circuit, Project, Value, label

ID = "completeness"
FIX = "Add the load description and connected load, or mark the circuit SPARE."
FIELDS = (
    ("description", "require_description"),
    ("load_va", "require_load"),
    ("breaker_a", "require_breaker"),
    ("conductor_size", "require_conductor_size"),
)


def _issue(name: str, v: Value, placeholders: set[str]) -> str | None:
    if v.source is None:
        return f"{name} (missing)"
    shown = str(v.value if v.value is not None else v.raw or "").strip()
    if v.value is None or not shown or shown.upper() in placeholders:
        return f'{name} (not usable, shown as "{shown}")' if shown else f"{name} (blank)"
    if not v.usable:
        return f"{name} ({v.confidence.name}, at {v.source.locator})"
    return None


def _circuit(c: Circuit, block: dict, placeholders: set[str], sev: Severity, ref: str):
    used = {n: getattr(c, n) for n, flag in FIELDS if block.get(flag)}
    issues = [i for n, v in used.items() if (i := _issue(n, v, placeholders))]
    if not issues:
        return None
    msg = f"{label(c)}: incomplete. {'; '.join(issues)}."
    return Finding(ID, sev, msg, ref, c.source, inputs_used(used), FIX)


def check(project: Project, cfg: Config) -> list[Finding]:
    block = cfg.cec["completeness"]
    s = str(block.get("severity"))
    sev = Severity.NEEDS_REVIEW if s == "VIOLATION" else Severity(s)
    placeholders = {str(t).upper() for t in block.get("placeholder_texts") or []}
    ref = rule_ref(cfg, ID)
    found = (
        _circuit(c, block, placeholders, sev, ref)
        for p in project.panels
        for c in p.circuits
        if not c.is_spare
    )
    return [f for f in found if f]


SPEC = RuleSpec(ID, "Completeness", check)
