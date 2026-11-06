from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from redline.config import Config, lookup, rule_ref
from redline.engine import RuleSpec
from redline.findings import Finding, Severity, input_gate, inputs_used
from redline.model import (
    Circuit,
    Feeder,
    Panel,
    Project,
    Source,
    Value,
    effective_voltage,
    label,
)
from redline.units import MATERIAL_TABLE_KEY

ID = "voltage_drop"
TABLES = ("voltage_drop",)
GATE_FIX = "Show the listed input on the schedule or drawing, or check this unit by hand."
TABLE_FIX = "Reviewer to supply the missing table entry in the config and re-run [VERIFY]."
FIX = "Increase conductor size or shorten the run. Reviewer to confirm length and load current."


def _vd(cfg: Config, *keys: str) -> Any:
    return lookup(cfg, "voltage_drop", *keys)


def _pct(
    cfg: Config, size: str, mat: str, length: float, volts: float, three: bool, amps: float
) -> tuple[float | None, list[str]]:
    """Percent drop, or the config paths that were missing."""
    phase = "three" if three else "single"
    m = MATERIAL_TABLE_KEY.get(mat, mat)
    method = _vd(cfg, "method")
    if method == "k_factor":
        paths = {
            "k": ("k_factor", "constant_by_material", m),
            "area": ("k_factor", "area_by_size", size),
            "mult": ("k_factor", "phase_multiplier", phase),
        }
    elif method == "impedance":
        paths = {
            "pf": ("impedance", "power_factor"),
            "r": ("impedance", "per_size", m, size, "r"),
            "x": ("impedance", "per_size", m, size, "x"),
            "mult": ("impedance", "phase_multiplier", phase),
        }
    else:
        return None, ["method"]
    got = {n: _vd(cfg, *p) for n, p in paths.items()}
    if missing := [".".join(paths[n]) for n, v in got.items() if v is None]:
        return None, missing
    if method == "k_factor":
        drop = got["k"] * amps * length / got["area"] * got["mult"]
    else:
        sine = math.sqrt(max(0, 1 - got["pf"] * got["pf"]))
        drop = amps * length * (got["r"] * got["pf"] + got["x"] * sine) * got["mult"]
    return drop / volts * 100, []


def _unit(
    cfg: Config, ref: str, name: str, src: Source, req: Mapping[str, Value], basis: str
) -> tuple[float | None, Finding | None]:
    """(percent, None) when computed, else (None, the finding that says why not)."""
    if gate := input_gate(ID, ref, name, src, req, GATE_FIX):
        return None, gate
    length, size, mat, volts, phase, cur, *sets = (v.value for v in req.values())
    three = phase == 3
    amps = cur if basis == "breaker" else cur / (volts * (math.sqrt(3) if three else 1))
    if sets:
        amps /= sets[0]
    pct, missing = _pct(cfg, size, mat, length, volts, three, amps)
    if missing:
        msg = f"{name}: not checked. Table entry missing: {', '.join(missing)}."
        return None, Finding(ID, Severity.NEEDS_REVIEW, msg, ref, src, inputs_used(req), TABLE_FIX)
    return pct, None


def _judge(
    cfg: Config,
    ref: str,
    name: str,
    src: Source,
    req: Mapping[str, Value],
    pct: float,
    limit_key: str,
    what: str,
    extra: str = "",
) -> Finding | None:
    limit = _vd(cfg, limit_key)
    if limit is None:
        msg = f"{name}: not checked. Table entry missing: {limit_key}."
        return Finding(ID, Severity.NEEDS_REVIEW, msg, ref, src, inputs_used(req), TABLE_FIX)
    if pct > limit and not math.isclose(pct, limit):
        sev, rel, fix = Severity.VIOLATION, "above", FIX
    elif _vd(cfg, "show_passing") is True:
        sev, rel, fix = Severity.INFO, "within", "No change needed from this rule."
    else:
        return None
    msg = f"{name}: {what} voltage drop {pct:.2f}% is {rel} the {limit:g}% limit.{extra} {ref}"
    return Finding(ID, sev, msg, ref, src, inputs_used(req), fix)


def _chain(
    project: Project, panel: Panel, drops: dict[str, float | None]
) -> tuple[float | None, list[Feeder], str]:
    """Feeder drops summed up the fed_from chain: (percent, feeders used, broken link)."""
    total, used, cur, seen = 0.0, [], panel, set()
    while cur.fed_from.value:
        if cur.name in seen:
            return None, used, f"{label(cur)} feeds itself"
        seen.add(cur.name)
        if not cur.fed_from.usable:
            return None, used, f"the feed source of {label(cur)} is not usable"
        feeder = next((f for f in project.feeders if f.to_panel.value == cur.name), None)
        if feeder is None:
            return None, used, f"no feeder shown into {label(cur)}"
        if not feeder.to_panel.usable:
            return None, used, f"{label(feeder)} feeder to_panel is LOW"
        if drops.get(feeder.id) is None:
            return None, used, f"{label(feeder)} voltage drop was not computed"
        total += drops[feeder.id]
        used.append(feeder)
        src = cur.fed_from.value
        cur = next((q for q in project.panels if q.name == src), None)
        if cur is None:
            return None, used, f"source panel {src} not in project"
    if not used:
        return None, used, f"feed source not shown for {label(panel)}"
    return total, used, ""


def _req(
    u: Circuit | Feeder,
    phase_name: str,
    phase: Value,
    volts: Value,
    rating: tuple[str, Value],
    basis: str,
) -> dict[str, Value]:
    current = {rating[0]: rating[1]} if basis == "breaker" else {"load_va": u.load_va}
    return {
        "length_m": u.length_m,
        "conductor_size": u.conductor_size,
        "conductor_material": u.conductor_material,
        "voltage_v": volts,
        phase_name: phase,
        **current,
    }


def check(project: Project, cfg: Config) -> list[Finding]:
    ref = rule_ref(cfg, ID)
    basis = _vd(cfg, "current_basis")
    if basis not in ("load", "breaker"):
        msg = "Voltage drop not checked. Table entry missing: current_basis."
        return [Finding(ID, Severity.NEEDS_REVIEW, msg, ref, None, (), TABLE_FIX)]
    out: list[Finding] = []
    drops: dict[str, float | None] = {}
    freqs: dict[str, dict[str, Value]] = {}
    for f in project.feeders:
        req = _req(f, "phases", f.phases, f.voltage_v, ("ocpd_a", f.ocpd_a), basis)
        req["sets_in_parallel"] = f.sets_in_parallel
        freqs[f.id] = req
        pct, bad = _unit(cfg, ref, label(f), f.source, req, basis)
        drops[f.id] = pct
        found = bad or _judge(cfg, ref, label(f), f.source, req, pct, "feeder_max_pct", "feeder")
        out += [found] if found else []
    for p in project.panels:
        chain, used, why = _chain(project, p, drops)
        if why and any(not c.is_spare for c in p.circuits):
            msg = f"{label(p)}: total voltage drop not checked. Broken link: {why}."
            fix = "Show the missing link or correct the feeder, then re-run."
            out.append(Finding(ID, Severity.NOT_CHECKED, msg, ref, p.source, (), fix))
        for c in p.circuits:
            if c.is_spare:
                continue
            req = _req(
                c, "poles", c.poles, effective_voltage(c, p), ("breaker_a", c.breaker_a), basis
            )
            pct, bad = _unit(cfg, ref, label(c), c.source, req, basis)
            if bad:
                out.append(bad)
                continue
            found = [_judge(cfg, ref, label(c), c.source, req, pct, "branch_max_pct", "branch")]
            if chain is not None:
                extra = f" Branch part {pct:.2f}%, feeder part {chain:.2f}%."
                fused = {f"{label(fd)} {k}": v for fd in used for k, v in freqs[fd.id].items()}
                found.append(
                    _judge(
                        cfg,
                        ref,
                        label(c),
                        c.source,
                        {**req, **fused},
                        pct + chain,
                        "total_max_pct",
                        "total",
                        extra,
                    )
                )
            out += [f for f in found if f]
    return out


SPEC = RuleSpec(ID, "Voltage drop", check, TABLES)
