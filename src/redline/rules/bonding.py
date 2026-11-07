from __future__ import annotations

from redline.config import Config, lookup, rule_ref
from redline.engine import RuleSpec
from redline.findings import Finding, Severity, checked, input_gate, inputs_used
from redline.model import Project, Source, Value, label
from redline.units import MATERIAL_TABLE_KEY

ID = "bonding"
FIX_SHOW = "Show the bonding conductor size on the drawing, or confirm it with the designer."
FIX_SIZE = "Increase the bonding conductor to the table size, or show the size. Reviewer to confirm [VERIFY]."


def _review(cfg: Config, unit: str, source: Source | None, msg: str, used: dict) -> Finding:
    return Finding(
        ID,
        Severity.NEEDS_REVIEW,
        f"{unit}: not checked. {msg}",
        rule_ref(cfg, ID),
        source,
        inputs_used(used),
        FIX_SIZE,
    )


def _check_one(
    cfg: Config, unit: str, source: Source, ocpd: Value, material: Value, bonding: Value
) -> Finding | None:
    ref = rule_ref(cfg, ID)
    req = {"ocpd_a": ocpd, "conductor_material": material, "bonding_size": bonding}
    if gate := input_gate(ID, ref, unit, source, req, FIX_SIZE):
        return gate
    rows = lookup(cfg, "bonding_conductor_size", "values")
    order = lookup(cfg, "conductor_size_order", "values")
    key = MATERIAL_TABLE_KEY.get(material.value, "") + "_size"
    if not rows or not order:
        return _review(cfg, unit, source, "Table entry missing.", req)
    row = None
    for r in rows:
        if r.get("max_ocpd_a") is None:  # a null limit is a missing entry, not zero
            return _review(cfg, unit, source, "Table entry missing for this rating or size.", req)
        if r["max_ocpd_a"] >= ocpd.value:
            row = r
            break
    need = row.get(key) if row else None
    if need not in order or bonding.value not in order:
        return _review(cfg, unit, source, "Table entry missing for this rating or size.", req)
    if order.index(bonding.value) >= order.index(need):
        return None
    return Finding(
        ID,
        Severity.VIOLATION,
        f"{unit}: bonding conductor {bonding.value} is below the table size {need} "
        f"for {ocpd.value:g} A. {ref}",
        ref,
        source,
        inputs_used(req),
        FIX_SIZE,
    )


def _omitted(cfg: Config, unit: str, source: Source, names: list[str], what: str) -> Finding:
    return Finding(
        ID,
        Severity.NEEDS_REVIEW,
        f"{unit}: bonding conductor not shown on {what}: {', '.join(names)}. Not checked.",
        rule_ref(cfg, ID),
        source,
        (),
        FIX_SHOW,
    )


def check(project: Project, cfg: Config) -> list[Finding]:
    out: list[Finding] = []
    for p in project.panels:
        shown = []
        for c in p.circuits:
            if c.is_spare:
                continue
            if c.bonding_size.source is None:
                shown.append(label(c))
            else:
                out += checked(
                    ID,
                    rule_ref(cfg, ID),
                    label(c),
                    c.source,
                    lambda c=c: _check_one(
                        cfg, label(c), c.source, c.breaker_a, c.conductor_material, c.bonding_size
                    ),
                )
        if shown:
            out.append(_omitted(cfg, label(p), p.source, shown, "circuits"))
    gone = [f for f in project.feeders if f.bonding_size.source is None]
    for f in project.feeders:
        if f.bonding_size.source is not None:
            out += checked(
                ID,
                rule_ref(cfg, ID),
                label(f),
                f.source,
                lambda f=f: _check_one(
                    cfg, label(f), f.source, f.ocpd_a, f.conductor_material, f.bonding_size
                ),
            )
    if gone:
        out.append(_omitted(cfg, "Feeders", gone[0].source, [label(f) for f in gone], "feeders"))
    return out


SPEC = RuleSpec(ID, "Bonding", check, ("bonding_conductor_size", "conductor_size_order"))
