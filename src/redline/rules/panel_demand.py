from __future__ import annotations

import math

from redline.config import Config, lookup, rule_ref
from redline.engine import RuleSpec
from redline.findings import Finding, Severity, input_gate, inputs_used
from redline.model import Panel, Project, Value, derived, is_mlo, label

ID = "panel_demand"
FIX = (
    "Increase bus and main, split the panel, or reduce connected load. "
    "Reviewer to confirm demand factors [VERIFY]."
)


def _tiered(tiers: list, total: float) -> float | None:
    out = prev = 0
    for t in tiers:
        up, factor = t.get("up_to_va"), t.get("factor")  # a null bound is unbounded
        if factor is None:
            return None
        top = total if up is None or total <= up else up
        out += (top - prev) * factor
        if top == total:
            return out
        prev = up
    return None


def _nr(cfg: Config, p: Panel, msg: str, used: dict | None = None) -> Finding:
    text = f"{label(p)}: not checked. {msg}"
    return Finding(
        ID, Severity.NEEDS_REVIEW, text, rule_ref(cfg, ID), p.source, inputs_used(used or {}), FIX
    )


def _computed(p: Panel, cfg: Config) -> Value | Finding:
    live = [c for c in p.circuits if not c.is_spare]
    req = {}
    for c in live:
        req[f"{label(c)} load_va"] = c.load_va
        req[f"{label(c)} load_type"] = c.load_type
    if gate := input_gate(ID, rule_ref(cfg, ID), label(p), p.source, req, FIX):
        return gate
    sums: dict[str, float] = {}
    for c in live:
        sums[c.load_type.value] = sums.get(c.load_type.value, 0) + c.load_va.value
    total = 0
    for kind, va in sums.items():
        tiers = lookup(cfg, "demand_factors", "by_load_type", kind)
        d = _tiered(tiers, va) if tiers else None
        if d is None:
            return _nr(cfg, p, f"Table entry missing for load type {kind}.", req)
        total += d
    note = "computed through demand_factors tiers"
    return derived(total, list(req.values()), p.source.file, f"{label(p)} demand", note)


def _panel(p: Panel, cfg: Config) -> list[Finding]:
    ref, unit = rule_ref(cfg, ID), label(p)
    base = {"bus_rating_a": p.bus_rating_a, "voltage_v": p.voltage_v, "phases": p.phases}
    if gate := input_gate(ID, ref, unit, p.source, base, FIX):
        return [gate]
    sup = p.demand_va_supplied
    if sup.source is not None and not sup.usable:
        return [input_gate(ID, ref, unit, p.source, {"demand_va_supplied": sup}, FIX)]
    comp = _computed(p, cfg)
    if sup.usable:
        demand, how = sup, "user_supplied"
    elif isinstance(comp, Finding):
        return [comp]
    else:
        demand, how = comp, "computed"
    va = demand.value
    amps = va / (p.voltage_v.value * (math.sqrt(3) if p.phases.value == 3 else 1))
    bus = p.bus_rating_a.value
    bus_f = lookup(cfg, "demand_factors", "bus_loading_limit_fraction")
    main_f = lookup(cfg, "demand_factors", "main_loading_limit_fraction")
    tol = lookup(cfg, "demand_factors", "supplied_vs_computed_tolerance_pct")
    used = inputs_used({**base, "demand_va": demand})
    msg = f"{unit}: demand {va:.0f} VA, source {how}. Demand current {amps:.1f} A, bus {bus:g} A."
    if is_mlo(p):
        msg += " MLO panel, bus checked only."
    out = [Finding(ID, Severity.INFO, msg, ref, p.source, used, "")]
    if bus_f is None:
        return out + [_nr(cfg, p, "Table entry missing for the bus loading limit.", base)]
    if amps > bus * bus_f:
        over = f"{unit}: demand current {amps:.1f} A is above {bus_f:g} of the {bus:g} A bus."
        out.append(Finding(ID, Severity.VIOLATION, over, ref, p.source, used, FIX))
    main = p.main_breaker_a
    if not is_mlo(p):
        if g := input_gate(ID, ref, unit, p.source, {"main_breaker_a": main}, FIX):
            out.append(g)
        elif main_f is None:
            out.append(_nr(cfg, p, "Table entry missing for the main loading limit."))
        elif amps > main.value * main_f:
            over = f"{unit}: demand current {amps:.1f} A is above {main_f:g} of the {main.value:g} A main."
            out.append(Finding(ID, Severity.VIOLATION, over, ref, p.source, used, FIX))
    if how == "user_supplied" and isinstance(comp, Value):
        if tol is None:
            out.append(
                _nr(cfg, p, "Table entry missing for the supplied versus computed tolerance.")
            )
        elif abs(va - comp.value) * 100 > tol * comp.value:
            diff = (
                f"{unit}: supplied demand {va:.0f} VA and computed demand {comp.value:.0f} VA "
                f"differ by more than {tol:g} percent. The supplied value is used."
            )
            out.append(Finding(ID, Severity.INFO, diff, ref, p.source, used, ""))
    return out


def check(project: Project, cfg: Config) -> list[Finding]:
    return [f for p in project.panels for f in _panel(p, cfg)]


SPEC = RuleSpec(ID, "Panel demand", check, ("demand_factors",))
