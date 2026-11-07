from __future__ import annotations

import math

from redline.config import Config, lookup, rule_ref
from redline.engine import RuleSpec
from redline.findings import Finding, Severity, checked, input_gate, inputs_used
from redline.model import LOAD_TYPES, Circuit, Panel, Project, effective_voltage, label

ID = "continuous_load"
TABLES = ("continuous_load",)
GATE_FIX = "Show the listed input on the schedule or drawing, or check this unit by hand."
TABLE_FIX = "Reviewer to supply the missing table entry in the config and re-run [VERIFY]."
FIX = "Reduce load, increase breaker and conductor, or confirm the load is not continuous."


def _circuit(c: Circuit, p: Panel, cfg: Config, ref: str) -> Finding | None:
    name = label(c)
    kind = {"load_type": c.load_type}
    if gate := input_gate(ID, ref, name, c.source, kind, GATE_FIX):
        return gate
    if c.load_type.value == "unknown" or c.load_type.value not in LOAD_TYPES:
        msg = (
            f"{name}: not checked. Load type is unknown, "
            "so it is not clear whether the load is continuous."
        )
        fix = "Confirm whether the load is continuous and record the load type."
        return Finding(ID, Severity.NEEDS_REVIEW, msg, ref, c.source, inputs_used(kind), fix)
    if c.load_type.value != "continuous":
        return None
    fields = {
        **kind,
        "breaker_a": c.breaker_a,
        "load_va": c.load_va,
        "voltage_v": effective_voltage(c, p),
        "poles": c.poles,
    }
    if gate := input_gate(ID, ref, name, c.source, fields, GATE_FIX):
        return gate
    fraction = lookup(cfg, "continuous_load", "max_fraction_of_breaker")
    if fraction is None:
        msg = f"{name}: not checked. Table entry missing: max fraction of breaker."
        return Finding(
            ID, Severity.NEEDS_REVIEW, msg, ref, c.source, inputs_used(fields), TABLE_FIX
        )
    three = math.sqrt(3) if fields["poles"].value == 3 else 1
    current = fields["load_va"].value / (fields["voltage_v"].value * three)
    if not math.isfinite(current):
        msg = f"{name}: not checked. Current could not be computed."
        fix = "Reviewer to check this unit by hand."
        return Finding(ID, Severity.NEEDS_REVIEW, msg, ref, c.source, inputs_used(fields), fix)
    breaker = fields["breaker_a"].value
    limit = breaker * fraction
    if current > limit and not math.isclose(current, limit):
        msg = (
            f"{name}: continuous load draws {current:.1f} A, above the {limit:.1f} A "
            f"allowed on a {breaker:g} A breaker. {ref}"
        )
        return Finding(ID, Severity.VIOLATION, msg, ref, c.source, inputs_used(fields), FIX)
    return None


def check(project: Project, cfg: Config) -> list[Finding]:
    ref = rule_ref(cfg, ID)
    return [
        f
        for p in project.panels
        for c in p.circuits
        if not c.is_spare
        for f in checked(ID, ref, label(c), c.source, lambda c=c, p=p: _circuit(c, p, cfg, ref))
    ]


SPEC = RuleSpec(ID, "Continuous load", check, TABLES)
