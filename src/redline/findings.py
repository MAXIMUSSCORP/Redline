from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from redline.model import Confidence, Source, Value


class Severity(StrEnum):
    VIOLATION = "VIOLATION"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INFO = "INFO"
    NOT_CHECKED = "NOT_CHECKED"


@dataclass(frozen=True)
class InputUsed:
    field: str
    value: str
    locator: str  # "config default" for config.default_value inputs
    confidence: Confidence | None
    model: str | None = None


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    message: str
    rule_ref: str
    source: Source | None
    inputs_used: tuple[InputUsed, ...] = ()
    suggested_fix: str = ""


def _locator(v: Value) -> str:
    if v.source is None:
        return ""
    return "config default" if v.source.note == "config default" else v.source.locator


def inputs_used(fields: Mapping[str, Value]) -> tuple[InputUsed, ...]:
    out = []
    for name, v in fields.items():
        model = v.source.model if v.source else None
        if v.value is None and v.raw:
            # No confidence word: a parse failure must not read as a good value.
            shown = f'shown as "{v.raw}" (not parsed)'
            out.append(InputUsed(name, shown, _locator(v), None, model))
            continue
        val = v.value
        text = ", ".join(map(str, val)) if isinstance(val, tuple | list) else str(val)
        out.append(InputUsed(name, "" if val is None else text, _locator(v), v.confidence, model))
    return tuple(out)


def _bad_part(n: str, v: Value) -> str:
    if v.source is None:
        return f"{n} (missing)"
    if v.value is None and v.raw:
        return f'{n} shown as "{v.raw}" (not parsed, at {v.source.locator})'
    note = f", {v.source.note}" if v.source.note else ""
    return f"{n} ({v.confidence.name}{note}, at {v.source.locator})"


def input_gate(
    rule_id: str,
    rule_ref: str,
    unit: str,
    source: Source | None,
    required: Mapping[str, Value],
    fix: str,
) -> Finding | None:
    bad = [(n, v) for n, v in required.items() if not v.usable]
    if not bad:
        return None
    parts = [_bad_part(n, v) for n, v in bad]
    return Finding(
        rule_id,
        Severity.NEEDS_REVIEW,
        f"{unit}: not checked. Input not usable: {'; '.join(parts)}.",
        rule_ref,
        source,
        inputs_used(required),
        fix,
    )
