from __future__ import annotations

import itertools
import math

from redline.config import (
    FIRE_ALARM_LIMITS,
    FIRE_ALARM_TABLE,
    MAX_FIRE_ALARM_PAIRS,
    MAX_FIRE_ALARM_RUN_PAIRS,
    Config,
    device_classes,
    fire_alarm_limit,
    rule_ref,
)
from redline.engine import RuleSpec
from redline.findings import Finding, Severity, checked, input_gate, inputs_used
from redline.model import Device, EgressPath, Method, Project, Value
from redline.units import LENGTH_TOLERANCE_M, METRES_PER_UNIT

ID = "fire_alarm"
FIX_HAND = "Check this item by hand against the drawings."
FIX_REVIEW = "Reviewer to check this item against the drawings and the configured limits [VERIFY]."
FIX_FIX = (
    "Add the device, move it, or confirm the plan with the designer. Reviewer to confirm [VERIFY]."
)

# section, name, text when no plan input exists at all
CHECKS = (
    (
        "exit_signs",
        "Exit signs",
        "No exit or egress path was read from a plan sheet, exits.csv or paths.csv.",
    ),
    (
        "pull_stations",
        "Fire alarm pull stations",
        "No exit was read from a plan sheet or exits.csv.",
    ),
    ("emergency_lighting", "Emergency lighting", "No egress path was read from paths.csv."),
)
# part label, input kind, device class, radius or distance key, allowed gap key (paths only)
PARTS = {
    "exit_signs": (
        ("Exit signs at exits", "exit", "exit_sign", "max_distance_from_exit_m", None),
        (
            "Exit sign spacing along paths",
            "path",
            "exit_sign",
            "max_distance_from_path_to_sign_m",
            None,
        ),
    ),
    "pull_stations": (
        ("Fire alarm pull stations", "exit", "pull_station", "max_distance_from_exit_m", None),
    ),
    "emergency_lighting": (
        (
            "Emergency lighting",
            "path",
            "emergency_light",
            "coverage_radius_m",
            "max_gap_along_path_m",
        ),
    ),
}


def _nc(ref: str, msg: str) -> Finding:
    return Finding(ID, Severity.NOT_CHECKED, msg, ref, None, (), FIX_HAND)


def _is_detector(d: Device) -> bool:
    return d.source.method == Method.DETECTOR


def _by_sheet(project: Project) -> dict[str, dict]:
    """Plan sheets (any exit, path or device) keyed by name without case, in first-seen order."""
    sheets: dict[str, dict] = {}

    def slot(name: str) -> dict:
        return sheets.setdefault(name.casefold(), {"name": name, "exit": [], "path": [], "dev": []})

    for d in project.devices:
        kinds = ("list", "block", "detector")
        is_exit = d.type == "exit_door" and (d.detection in kinds or _is_detector(d))
        slot(d.sheet.value or "(sheet not named)")["exit" if is_exit else "dev"].append(d)
    for p in project.paths:
        slot(p.sheet or "(sheet not named)")["path"].append(p)
    return sheets


def _split(devs: list[Device], cls: str) -> tuple[list[Device], list[Device]]:
    """Certain devices of a class, and uncertain ones (nested, detector, or no usable point)."""
    sure: list[Device] = []
    unsure: list[Device] = []
    for d in devs:
        if d.type != cls or d.detection in ("paper", "unused"):
            continue
        if d.detection == "block" and d.x.usable and d.y.usable and not _is_detector(d):
            sure.append(d)
        elif d.detection in ("nested", "detector", "block") or _is_detector(d):
            unsure.append(d)
    return sure, unsure


def _gaps(
    points: list[tuple[float, float]],
    devs: list[tuple[float, float]],
    radius: float,
    allowed: float,
) -> list[tuple[float, float]]:
    """Stretches (metres along the path) out of reach of every device, longer than allowed."""
    cum = 0.0
    reach = 0.0
    gaps: list[tuple[float, float]] = []
    tol = LENGTH_TOLERANCE_M
    for (ax, ay), (bx, by) in itertools.pairwise(points):
        seg = math.hypot(bx - ax, by - ay)
        if seg > 0:
            spans: list[tuple[float, float]] = []
            ux, uy = (bx - ax) / seg, (by - ay) / seg
            for qx, qy in devs:
                along = (qx - ax) * ux + (qy - ay) * uy
                off = abs((qx - ax) * uy - (qy - ay) * ux)
                if off <= radius:
                    half = math.sqrt(radius * radius - off * off)
                    lo, hi = max(along - half, 0.0), min(along + half, seg)
                    if lo <= hi:
                        spans.append((cum + lo, cum + hi))
            spans.sort()
            for lo, hi in spans:
                if lo - reach > allowed + tol:
                    gaps.append((reach, lo))
                reach = max(reach, hi)
        cum += seg
    if cum - reach > allowed + tol:
        gaps.append((reach, cum))
    return gaps


def _units_text(u: Value) -> str:
    src = u.source
    return f"units {u.value}, {src.note or src.locator}" if src else f"units {u.value}"


def _sev(unsure: list[Device], used: dict[str, Value]) -> Severity:
    det = any(v.source is not None and v.source.method == Method.DETECTOR for v in used.values())
    return Severity.NEEDS_REVIEW if unsure or det else Severity.VIOLATION


def _uncertain_note(unsure: list[Device], cls: str) -> str:
    if not unsure:
        return ""
    return (
        f" {len(unsure)} {cls.replace('_', ' ')} device(s) on this sheet are nested or "
        "detector-derived, so the count is uncertain."
    )


def _exit_unit(
    e: Device,
    sheet: str,
    label: str,
    cls: str,
    limit: float,
    mpu: float,
    units: Value,
    sure: list[Device],
    unsure: list[Device],
    ref: str,
) -> Finding | None:
    unit = f"{sheet} exit {e.tag.value or e.source.locator} ({label})"
    req = {"exit x": e.x, "exit y": e.y, "units": units}
    if gate := input_gate(ID, ref, unit, e.source, req, FIX_REVIEW):
        return gate
    if e.detection == "detector" or _is_detector(e):
        msg = (
            f"{unit}: not checked. The exit was found by a detector, not read from a list or block."
        )
        return Finding(ID, Severity.NEEDS_REVIEW, msg, ref, e.source, inputs_used(req), FIX_REVIEW)
    word = cls.replace("_", " ")
    best = min(
        sure,
        key=lambda d: math.hypot(d.x.value - e.x.value, d.y.value - e.y.value),
        default=None,
    )
    if best is None:
        msg = (
            f"{unit}: no {word} block placed in model space was matched on this sheet, limit {limit:g} m in "
            f"fire_alarm.yaml ({_units_text(units)}).{_uncertain_note(unsure, cls)} {ref}"
        )
        return Finding(ID, Severity.NEEDS_REVIEW, msg, ref, e.source, inputs_used(req), FIX_REVIEW)
    else:
        dist = math.hypot(best.x.value - e.x.value, best.y.value - e.y.value) * mpu
        if dist <= limit + LENGTH_TOLERANCE_M:
            return None
        req = {**req, "nearest x": best.x, "nearest y": best.y}
        what = f"nearest {word} is {dist:.1f} m away, over the {limit:g} m limit"
    note = _uncertain_note(unsure, cls)
    msg = f"{unit}: {what} in fire_alarm.yaml ({_units_text(units)}).{note} {ref}"
    return Finding(ID, _sev(unsure, req), msg, ref, e.source, inputs_used(req), FIX_FIX)


def _path_unit(
    p: EgressPath,
    sheet: str,
    label: str,
    cls: str,
    radius: float,
    allowed: float | None,
    mpu: float,
    units: Value,
    sure: list[Device],
    unsure: list[Device],
    ref: str,
) -> Finding | None:
    unit = f"{sheet} path {p.name} ({label})"
    req = {"path": Value(p.points if len(p.points) > 1 else None, p.source), "units": units}
    if gate := input_gate(ID, ref, unit, p.source, req, FIX_REVIEW):
        return gate
    if p.source.method == Method.DETECTOR:
        msg = f"{unit}: not checked. The path was found by a detector, not read from paths.csv."
        return Finding(ID, Severity.NEEDS_REVIEW, msg, ref, p.source, inputs_used(req), FIX_REVIEW)
    points = [(x * mpu, y * mpu) for x, y in p.points]
    devs = [(d.x.value * mpu, d.y.value * mpu) for d in sure]
    gaps = _gaps(points, devs, radius, LENGTH_TOLERANCE_M if allowed is None else allowed)
    if not gaps:
        return None
    lo, hi = max(gaps, key=lambda g: g[1] - g[0])
    word = cls.replace("_", " ")
    over = "" if allowed is None else f", over the {allowed:g} m gap limit"
    msg = (
        f"{unit}: {len(gaps)} stretch(es) of the path are beyond {radius:g} m of any {word}, "
        f"longest {hi - lo:.1f} m from {lo:.1f} m to {hi:.1f} m along the path{over}, "
        f"limits in fire_alarm.yaml ({_units_text(units)}).{_uncertain_note(unsure, cls)} {ref}"
    )
    if not sure:
        msg = f"No {word} block placed in model space was matched on this sheet. {msg}"
        return Finding(ID, Severity.NEEDS_REVIEW, msg, ref, p.source, inputs_used(req), FIX_REVIEW)
    return Finding(ID, _sev(unsure, req), msg, ref, p.source, inputs_used(req), FIX_FIX)


def _run_part(
    part: tuple, lims: dict, ref: str, data: dict, units: Value, used: list[int]
) -> list[Finding]:
    label, kind, cls, rkey, gkey = part
    sheet = data["name"]
    items = data[kind]
    if not items:
        what = "exit" if kind == "exit" else "egress path"
        return [_nc(ref, f"{sheet}: {label} not checked. No {what} was read for this sheet.")]
    mpu = METRES_PER_UNIT.get(units.value) if units.usable else None
    if mpu is None:
        return [_nc(ref, f"{sheet}: {label} not checked. Drawing units not stated.")]
    sure, unsure = _split(data["dev"], cls)
    segs = len(items) if kind == "exit" else sum(max(len(p.points) - 1, 0) for p in items)
    if segs * len(sure) > MAX_FIRE_ALARM_PAIRS:
        msg = (
            f"{sheet}: {label} not checked. {segs} x {len(sure)} pairs is over the design cap "
            f"of {MAX_FIRE_ALARM_PAIRS}; check by hand."
        )
        return [_nc(ref, msg)]
    if used[0] + segs * len(sure) > MAX_FIRE_ALARM_RUN_PAIRS:
        msg = (
            f"{sheet}: {label} not checked. Reason: the run's limit of pair comparisons "
            "was reached; check by hand."
        )
        return [_nc(ref, msg)]
    used[0] += segs * len(sure)
    out: list[Finding] = []
    for it in items:
        if kind == "exit":
            name = f"{sheet} exit {it.tag.value or it.source.locator}"

            def run(it=it):
                return _exit_unit(it, sheet, label, cls, lims[rkey], mpu, units, sure, unsure, ref)
        else:
            name = f"{sheet} path {it.name}"
            allowed = lims[gkey] if gkey else None

            def run(it=it, allowed=allowed):
                return _path_unit(
                    it, sheet, label, cls, lims[rkey], allowed, mpu, units, sure, unsure, ref
                )

        out += checked(ID, ref, name, it.source, run)
    return out


def check(project: Project, cfg: Config) -> list[Finding]:
    out: list[Finding] = []
    sheets = _by_sheet(project)
    used = [0]  # pair comparisons spent so far, over all sheets, parts and sections
    unit_of = {k.casefold(): v for k, v in project.sheet_units.items()}
    for section, name, none_read in CHECKS:
        ref = rule_ref(cfg, section)
        lims = {k: fire_alarm_limit(cfg, section, k) for k in FIRE_ALARM_LIMITS[section]}
        gone = [f"{section}.{k}" for k, v in lims.items() if v is None]
        if gone:
            msg = f"{name}: not checked. Limits not filled in fire_alarm.yaml: {', '.join(gone)} [VERIFY]."
            out.append(_nc(ref, msg))
        elif lims.get("require_at_each_exit") is False:
            msg = (
                f"{name}: not checked. {section}.require_at_each_exit is false in fire_alarm.yaml."
            )
            out.append(_nc(ref, msg))
        elif not sheets:
            out.append(_nc(ref, f"{name}: not checked. {none_read}"))
        else:
            have = set(device_classes(cfg).values())
            for part in PARTS[section]:
                if part[2] not in have:
                    msg = (
                        f"{part[0]}: not checked. No block name is configured for {part[2]} "
                        "in fire_alarm.yaml device_blocks [VERIFY]."
                    )
                    out.append(_nc(ref, msg))
                    continue
                for key, data in sheets.items():
                    units = unit_of.get(key, Value.missing())
                    out += _run_part(part, lims, ref, data, units, used)
    return out


SPEC = RuleSpec(ID, "Fire alarm and egress", check, (FIRE_ALARM_TABLE,))
