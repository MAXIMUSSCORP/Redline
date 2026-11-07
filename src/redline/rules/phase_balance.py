from __future__ import annotations

import math
from dataclasses import replace

from redline.config import Config, lookup, rule_ref
from redline.engine import RuleSpec
from redline.findings import Finding, Severity, checked, input_gate, inputs_used, unique_tag
from redline.model import (
    MAX_CKT_DIGITS,
    Circuit,
    Confidence,
    Method,
    Panel,
    Project,
    Source,
    Value,
    label,
)

ID = "phase_balance"
FIX = "Move circuits from the heaviest phase to the lightest. Reviewer to confirm [VERIFY]."
NOT_RUN_FIX = "Reviewer to screen phase balance for this panel by hand."


def _phases(c: Circuit, pattern: list | None) -> tuple[Value, bool]:
    """Phase letters for a circuit: the column when shown, else its position (MEDIUM at best)."""
    col = c.phases_used
    if col.source is not None:
        why = ""
        if col.value and not set(col.value) <= set("ABC"):
            why = "phase letters not A, B or C"
        # Letters that disagree with a usable pole count cannot both be right.
        elif col.value and c.poles.usable and len(col.value) != c.poles.value:
            why = "phases shown disagree with poles"
        if why:
            note = f"{col.source.note}; {why}" if col.source.note else why
            low = replace(col.source, confidence=Confidence.LOW, note=note)
            return Value(", ".join(col.value), low, col.raw), False
        return Value(", ".join(col.value) if col.value else None, col.source, col.raw), False
    num = c.number.strip()
    if not (pattern and num.isdigit() and c.poles.usable):
        return Value.missing(), False
    if not (
        num.isascii() and len(num) <= MAX_CKT_DIGITS
    ):  # isdigit also passes "²" and 5000 digits
        low = replace(
            c.source, confidence=Confidence.LOW, note="circuit number not usable for position"
        )
        return Value(None, low), False
    n, size = int(num) - 1, len(pattern)
    letters = tuple(pattern[(n + 2 * k) % size] for k in range(int(c.poles.value)))
    low = min(Confidence.MEDIUM, c.source.confidence)
    src = Source(c.source.file, c.source.locator, Method.DERIVED, low, "phase from position")
    return Value(", ".join(letters), src, num), True


def _panel(p: Panel, cfg: Config, ref: str) -> list[Finding]:
    unit = label(p)
    base = {"phases": p.phases}
    if gate := input_gate(ID, ref, unit, p.source, base, FIX):
        return [gate]
    if p.phases.value != 3:
        msg = f"{unit}: single-phase panel, phase balance not screened."
        return [
            Finding(ID, Severity.NOT_CHECKED, msg, ref, p.source, inputs_used(base), NOT_RUN_FIX)
        ]
    limit = lookup(cfg, "phase_balance", "max_deviation_pct")
    least = lookup(cfg, "phase_balance", "min_circuits_to_check")
    pattern = lookup(cfg, "phase_layout", "three_phase_pattern")
    live = [c for c in p.circuits if not c.is_spare]
    if limit is None or least is None:
        msg = f"{unit}: not checked. Table entry missing."
        return [Finding(ID, Severity.NEEDS_REVIEW, msg, ref, p.source, (), FIX)]
    if len(live) < least:
        msg = f"{unit}: not checked. Fewer than {least} circuits to compare."
        return [Finding(ID, Severity.NOT_CHECKED, msg, ref, p.source, (), NOT_RUN_FIX)]
    req: dict[str, Value] = {}
    nexts: dict[str, int] = {}
    placed: list[tuple[Circuit, list[str]]] = []
    by_position = 0
    for c in live:
        ph, pos = _phases(c, pattern)
        by_position += pos
        tag = unique_tag(req, label(c), ("load_va", "phase"), nexts)
        req[f"{tag} load_va"] = c.load_va
        req[f"{tag} phase"] = ph
        if ph.usable:
            placed.append((c, ph.value.split(", ")))
    if gate := input_gate(ID, ref, unit, p.source, req, FIX):
        return [gate]
    totals = dict.fromkeys("ABC", 0)
    for c, letters in placed:
        for ph in letters:
            totals[ph] += c.load_va.value / len(letters)
    mean = sum(totals.values()) / len(totals)
    worst = max(totals, key=lambda k: abs(totals[k] - mean))
    dev = abs(totals[worst] - mean) * 100 / mean if mean else 0
    if not all(math.isfinite(x) for x in (*totals.values(), mean, dev)):
        msg = f"{unit}: not checked. Phase balance could not be computed."
        return [
            Finding(ID, Severity.NEEDS_REVIEW, msg, ref, p.source, inputs_used(req), NOT_RUN_FIX)
        ]
    table = ", ".join(f"{k} {v:.0f} VA" for k, v in totals.items())
    note = f" {by_position} circuits placed by position, MEDIUM at best." if by_position else ""
    info = f"{unit}: load per phase: {table}.{note}"
    out = [Finding(ID, Severity.INFO, info, ref, p.source, inputs_used(req), "")]
    if dev > limit:
        heavy = max(totals, key=totals.get)
        cands = [label(c) for c, v in placed if v == [heavy]]
        msg = (
            f"{unit}: phase {worst} is {dev:.1f} percent from the mean, above the limit of "
            f"{limit:g} percent. This is project practice, not a code rule."
        )
        fix = f"{FIX} Candidates on phase {heavy}: {', '.join(cands) or 'none'}."
        out.append(Finding(ID, Severity.NEEDS_REVIEW, msg, ref, p.source, inputs_used(req), fix))
    return out


def check(project: Project, cfg: Config) -> list[Finding]:
    ref = rule_ref(cfg, ID)
    return [
        f
        for p in project.panels
        for f in checked(ID, ref, label(p), p.source, lambda p=p: _panel(p, cfg, ref))
    ]


SPEC = RuleSpec(ID, "Phase balance", check, ("phase_balance", "phase_layout"))
