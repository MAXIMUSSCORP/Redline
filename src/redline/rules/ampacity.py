from __future__ import annotations

import math
from collections.abc import Mapping

from redline.config import Config, default_value, lookup, rule_ref
from redline.engine import RuleSpec
from redline.findings import Finding, Severity, input_gate, inputs_used
from redline.model import Circuit, Feeder, Project, Value, label
from redline.units import MATERIAL_TABLE_KEY

ID = "ampacity"
TABLES = (
    "conductor_ampacity",
    "ambient_temp_correction",
    "conductor_count_correction",
    "standard_breaker_ratings",
    "allow_next_standard_size",
)
GATE_FIX = "Show the listed input on the schedule or drawing, or check this unit by hand."
TABLE_FIX = "Reviewer to supply the missing table entry in the config and re-run [VERIFY]."
FIX = (
    "Increase conductor size, reduce breaker rating, or reduce conductors per raceway. "
    "Reviewer to confirm correction factors [VERIFY]."
)


def _factor(rows: list | None, x: float) -> float | None:
    return next((f for bound, f in rows or () if x <= bound), None)


def _missing(
    name: str, ref: str, u: Circuit | Feeder, fields: Mapping[str, Value], what: str
) -> Finding:
    return Finding(
        ID,
        Severity.NEEDS_REVIEW,
        f"{name}: not checked. Table entry missing: {what}.",
        ref,
        u.source,
        inputs_used(fields),
        TABLE_FIX,
    )


def _unit(
    cfg: Config, ref: str, name: str, u: Circuit | Feeder, ocpd: Value, sets: Value | None
) -> Finding | None:
    fields = {
        "breaker_a": ocpd,
        "conductor_size": u.conductor_size,
        "conductor_material": u.conductor_material,
        "insulation_temp_c": u.insulation_temp_c,
        "termination_temp_c": default_value(cfg, "termination_temp_c"),
        # a missing value falls back to the config default; a LOW one goes to the gate
        "conductors_in_raceway": u.conductors_in_raceway
        if u.conductors_in_raceway.source
        else default_value(cfg, "conductors_in_raceway"),
        "ambient_c": u.ambient_c if u.ambient_c.source else default_value(cfg, "ambient_c"),
    }
    if sets is not None:
        fields["sets_in_parallel"] = sets
    if gate := input_gate(ID, ref, name, u.source, fields, GATE_FIX):
        return gate
    temp = int(fields["insulation_temp_c"].value)
    column = str(int(min(temp, fields["termination_temp_c"].value)))
    material = fields["conductor_material"].value
    size = fields["conductor_size"].value
    found = {
        "conductor ampacity": lookup(
            cfg,
            "conductor_ampacity",
            "values",
            MATERIAL_TABLE_KEY.get(material, material),
            size,
            column,
        ),
        "ambient correction": _factor(
            lookup(cfg, "ambient_temp_correction", "values", str(temp)), fields["ambient_c"].value
        ),
        "conductor count correction": _factor(
            lookup(cfg, "conductor_count_correction", "values"),
            fields["conductors_in_raceway"].value,
        ),
    }
    if missing := [n for n, v in found.items() if v is None]:
        return _missing(name, ref, u, fields, ", ".join(missing))
    base, ambient, count = found.values()
    corrected = base * ambient * count * (fields["sets_in_parallel"].value if sets else 1)
    breaker = fields["breaker_a"].value
    if corrected >= breaker or math.isclose(corrected, breaker):
        return None
    if lookup(cfg, "allow_next_standard_size", "enabled") is True:
        ratings = lookup(cfg, "standard_breaker_ratings", "values_a")
        if ratings is None:
            return _missing(name, ref, u, fields, "standard breaker ratings")
        nxt = min((r for r in ratings if r >= corrected), default=None)
        if nxt is not None and nxt >= breaker:
            return None
    return Finding(
        ID,
        Severity.VIOLATION,
        f"{name}: {size} {material} at {temp} C, corrected ampacity {corrected:g} A "
        f"is below the {breaker:g} A breaker. {ref}",
        ref,
        u.source,
        inputs_used(fields),
        FIX,
    )


def check(project: Project, cfg: Config) -> list[Finding]:
    ref = rule_ref(cfg, ID)
    out = [
        _unit(cfg, ref, label(c), c, c.breaker_a, None)
        for p in project.panels
        for c in p.circuits
        if not c.is_spare
    ]
    out += [_unit(cfg, ref, label(f), f, f.ocpd_a, f.sets_in_parallel) for f in project.feeders]
    return [f for f in out if f]


SPEC = RuleSpec(ID, "Ampacity", check, TABLES)
