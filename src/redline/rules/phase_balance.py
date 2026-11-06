from __future__ import annotations

from redline.config import Config, lookup, rule_ref
from redline.engine import RuleSpec
from redline.findings import Finding, Severity, input_gate, inputs_used
from redline.model import Circuit, Confidence, Method, Panel, Project, Source, Value, label

ID = "phase_balance"
FIX = "Move circuits from the heaviest phase to the lightest. Reviewer to confirm [VERIFY]."


def _phases(c: Circuit, pattern: list | None) -> tuple[Value, bool]:
    """Phase letters for a circuit: the column when shown, else its position (MEDIUM at best)."""
    col = c.phases_used
    if col.source is not None:
        ok = col.value and set(col.value) <= set("ABC")
        return Value(tuple(col.value) if ok else None, col.source, col.raw), False
    num = c.number.strip()
    if not (pattern and num.isdigit() and c.poles.usable):
        return Value.missing(), False
    n, size = int(num) - 1, len(pattern)
    letters = tuple(pattern[(n + 2 * k) % size] for k in range(int(c.poles.value)))
    low = min(Confidence.MEDIUM, c.source.confidence)
    src = Source(c.source.file, c.source.locator, Method.DERIVED, low, "phase from position")
    return Value(letters, src, num), True


def _panel(p: Panel, cfg: Config, ref: str) -> list[Finding]:
    unit = label(p)
    if gate := input_gate(ID, ref, unit, p.source, {"phases": p.phases}, FIX):
        return [gate]
    if p.phases.value != 3:
        return []
    limit = lookup(cfg, "phase_balance", "max_deviation_pct")
    least = lookup(cfg, "phase_balance", "min_circuits_to_check")
    pattern = lookup(cfg, "phase_layout", "three_phase_pattern")
    live = [c for c in p.circuits if not c.is_spare]
    if limit is None or least is None:
        msg = f"{unit}: not checked. Table entry missing."
        return [Finding(ID, Severity.NEEDS_REVIEW, msg, ref, p.source, (), FIX)]
    if len(live) < least:
        msg = f"{unit}: not checked. Fewer than {least} circuits to compare."
        return [Finding(ID, Severity.NOT_CHECKED, msg, ref, p.source, (), FIX)]
    req: dict[str, Value] = {}
    placed: dict[str, tuple[str, ...]] = {}
    by_position = 0
    for c in live:
        ph, pos = _phases(c, pattern)
        by_position += pos
        req[f"{label(c)} load_va"] = c.load_va
        req[f"{label(c)} phase"] = ph
        if ph.usable:
            placed[label(c)] = ph.value
    if gate := input_gate(ID, ref, unit, p.source, req, FIX):
        return [gate]
    totals = dict.fromkeys("ABC", 0)
    for c in live:
        letters = placed[label(c)]
        for ph in letters:
            totals[ph] += c.load_va.value / len(letters)
    mean = sum(totals.values()) / len(totals)
    table = ", ".join(f"{k} {v:.0f} VA" for k, v in totals.items())
    note = f" {by_position} circuits placed by position, MEDIUM at best." if by_position else ""
    info = f"{unit}: load per phase: {table}.{note}"
    out = [Finding(ID, Severity.INFO, info, ref, p.source, inputs_used(req), "")]
    worst = max(totals, key=lambda k: abs(totals[k] - mean))
    dev = abs(totals[worst] - mean) * 100 / mean if mean else 0
    if dev > limit:
        heavy = max(totals, key=totals.get)
        cands = [k for k, v in placed.items() if v == (heavy,)]
        msg = (
            f"{unit}: phase {worst} is {dev:.1f} percent from the mean, above the limit of "
            f"{limit:g} percent. This is project practice, not a code rule."
        )
        fix = f"{FIX} Candidates on phase {heavy}: {', '.join(cands) or 'none'}."
        out.append(Finding(ID, Severity.NEEDS_REVIEW, msg, ref, p.source, inputs_used(req), fix))
    return out


def check(project: Project, cfg: Config) -> list[Finding]:
    ref = rule_ref(cfg, ID)
    return [f for p in project.panels for f in _panel(p, cfg, ref)]


SPEC = RuleSpec(ID, "Phase balance", check, ("phase_balance", "phase_layout"))
