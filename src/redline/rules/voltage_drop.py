from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from redline.config import Config, lookup, rule_ref
from redline.engine import RuleSpec
from redline.findings import Finding, InputUsed, Severity, checked, input_gate, inputs_used
from redline.model import (
    Circuit,
    Feeder,
    Panel,
    Project,
    Source,
    Value,
    clip,
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
    if not math.isfinite(pct):
        msg = f"{name}: not checked. Voltage drop could not be computed."
        fix = "Reviewer to check this unit by hand."
        return None, Finding(ID, Severity.NEEDS_REVIEW, msg, ref, src, inputs_used(req), fix)
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
    at_least: bool = False,
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
    floor = "at least " if at_least else ""
    msg = (
        f"{name}: {what} voltage drop {floor}{pct:.2f}% is {rel} the {limit:g}% limit.{extra} {ref}"
    )
    return Finding(ID, sev, msg, ref, src, inputs_used(req), fix)


class _Index:
    """Feeders by to_panel and panels by name, built once so a long chain stays linear."""

    def __init__(self, project: Project) -> None:
        self.into: dict[str, list[Feeder]] = {}
        self.unparsed: list[Feeder] = []  # to_panel not read or not shown: could feed any panel
        self.panels: dict[str, Panel] = {}
        for f in project.feeders:
            if f.to_panel.usable:
                self.into.setdefault(f.to_panel.value, []).append(f)
            else:
                self.unparsed.append(f)
        for q in project.panels:
            self.panels.setdefault(q.name, q)


def _chain(
    idx: _Index, panel: Panel, drops: dict[str, float | None]
) -> tuple[float | None, list[Feeder], str, str]:
    """Feeder drops summed up the fed_from chain.

    Returns (percent, feeders used, why it stopped, top panel). The top panel is set only
    when the chain ends cleanly where no feed source is shown, not at a real break.
    """
    total, used, cur, seen = 0.0, [], panel, set()
    while True:
        matched = idx.into.get(cur.name, [])
        if not (cur.fed_from.value or cur.fed_from.raw):
            if matched:  # a feeder lands here, so a blank source is a gap, not a top
                why = f"{label(matched[0])} feeds {label(cur)}, which shows no feed source"
                return None, used, why, ""
            break
        into = matched
        if cur.name in seen:
            return None, used, f"{label(cur)} feeds itself", ""
        seen.add(cur.name)
        if not cur.fed_from.usable:
            return None, used, f"the feed source of {label(cur)} is not usable", ""
        if not into:
            return None, used, f"no feeder shown into {label(cur)}", ""
        if len(into) > 1:
            return None, used, f"{len(into)} feeders feed {label(cur)}", ""
        if idx.unparsed:  # a feeder whose to_panel is unread could also feed this panel
            u = idx.unparsed[0]
            raw = clip(u.to_panel.raw or "")
            if u.to_panel.value is not None:
                lead = f'{label(u)} to_panel "{clip(u.to_panel.value)}" is not usable (LOW)'
            elif raw:
                lead = f'{label(u)} to_panel shown as "{raw}" is not parsed'
            else:
                lead = f"{label(u)} has no to_panel shown"
            return None, used, f"{lead}, so it may also feed {label(cur)}", ""
        feeder = into[0]
        fp = feeder.from_panel
        if (fp.value is not None or fp.raw) and not fp.usable:
            return None, used, f"{label(feeder)} from_panel is not usable", ""
        if fp.usable and fp.value != cur.fed_from.value:
            return (
                None,
                used,
                f"{label(feeder)} from_panel disagrees with {label(cur)} fed_from",
                "",
            )
        if drops.get(feeder.id) is None:
            return None, used, f"{label(feeder)} voltage drop was not computed", ""
        total += drops[feeder.id]
        used.append(feeder)
        src = cur.fed_from.value
        cur = idx.panels.get(src)
        if cur is None:
            return None, used, f"source panel {clip(src)} not in project", ""
    # The chain ends where no feed source is shown. The drops only add, so the partial sum
    # is a lower bound: over the limit it is still a violation, within it nothing is proven.
    return (total if used else None), used, f"feed source not shown for {label(cur)}", cur.name


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


def _feeder(
    cfg: Config, ref: str, f: Feeder, req: dict[str, Value], basis: str, drops: dict
) -> Finding | None:
    pct, bad = _unit(cfg, ref, label(f), f.source, req, basis)
    drops[f.id] = pct
    return bad or _judge(cfg, ref, label(f), f.source, req, pct, "feeder_max_pct", "feeder")


def _circuit(
    cfg: Config,
    ref: str,
    basis: str,
    p: Panel,
    c: Circuit,
    chain: float | None,
    why: str,
    cites: tuple[InputUsed, ...],
) -> list[Finding]:
    req = _req(c, "poles", c.poles, effective_voltage(c, p), ("breaker_a", c.breaker_a), basis)
    pct, bad = _unit(cfg, ref, label(c), c.source, req, basis)
    if bad:
        return [bad]
    found = [_judge(cfg, ref, label(c), c.source, req, pct, "branch_max_pct", "branch")]
    if chain is not None:
        extra = f" Branch part {pct:.2f}%, feeder part {chain:.2f}%."
        if why:
            extra += (
                " Feeder part is partial: the chain stops at a panel with no feed source shown."
            )
        total = _judge(
            cfg,
            ref,
            label(c),
            c.source,
            req,
            pct + chain,
            "total_max_pct",
            "total",
            extra,
            at_least=bool(why),
        )
        if total:  # one compact entry per feeder, not a copy of every feeder input
            total = replace(total, inputs_used=(*total.inputs_used, *cites))
        found.append(total)
        # An open chain proves nothing when within the limit. The panel note says so.
        if why and total and total.severity == Severity.INFO:
            found.pop()
    return [f for f in found if f]


def _cites(all_: list[InputUsed]) -> tuple[InputUsed, ...]:
    """The nearest and the farthest feeder, then a count, so a long chain stays small."""
    if len(all_) <= 2:
        return tuple(all_)
    rest = all_[1:-1]
    low = min(c.confidence for c in rest if c.confidence is not None)
    return (all_[0], InputUsed(f"and {len(rest)} more feeders", "", "see feeders", low), all_[-1])


def check(project: Project, cfg: Config) -> list[Finding]:
    ref = rule_ref(cfg, ID)
    basis = _vd(cfg, "current_basis")
    if basis not in ("load", "breaker"):
        msg = "Voltage drop not checked. Table entry missing: current_basis."
        return [Finding(ID, Severity.NEEDS_REVIEW, msg, ref, None, (), TABLE_FIX)]
    out: list[Finding] = []
    drops: dict[str, float | None] = {}
    idx = _Index(project)
    cited: dict[str, InputUsed] = {}
    for f in project.feeders:
        req = _req(f, "phases", f.phases, f.voltage_v, ("ocpd_a", f.ocpd_a), basis)
        req["sets_in_parallel"] = f.sets_in_parallel
        drops[f.id] = None
        out += checked(
            ID,
            ref,
            label(f),
            f.source,
            lambda f=f, req=req: _feeder(cfg, ref, f, req, basis, drops),
        )
        if drops[f.id] is not None:
            low = min(v.confidence for v in req.values())
            cited[f.id] = InputUsed(
                f"{label(f)} drop", f"{drops[f.id]:.2f}%", clip(f.source.locator), low
            )
    for p in project.panels:
        chain, used, why, top = _chain(idx, p, drops)
        if why and any(not c.is_spare for c in p.circuits):
            if top:
                lower = ", so the feeder part is a lower bound" if used else ""
                msg = (
                    f"{label(p)}: total voltage drop within the limit is not confirmed. "
                    f"Supply above {clip(top)} is not shown{lower}."
                )
                fix = f"Reviewer to add the supply conductor drop above {clip(top)} by hand."
            else:
                msg = f"{label(p)}: total voltage drop not checked. Broken link: {why}."
                fix = "Show the missing link or correct the feeder, then re-run."
            out.append(Finding(ID, Severity.NOT_CHECKED, msg, ref, p.source, (), fix))
        cites = _cites([cited[fd.id] for fd in used])
        for c in p.circuits:
            if not c.is_spare:
                out += checked(
                    ID,
                    ref,
                    label(c),
                    c.source,
                    lambda c=c, p=p, ch=chain, w=why, ct=cites: _circuit(
                        cfg, ref, basis, p, c, ch, w, ct
                    ),
                )
    return out


SPEC = RuleSpec(ID, "Voltage drop", check, TABLES)
