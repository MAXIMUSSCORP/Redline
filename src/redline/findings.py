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
    confidence: Confidence
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
        text = str(v.value) if v.value is not None else (v.raw or "")
        out.append(
            InputUsed(name, text, _locator(v), v.confidence, v.source.model if v.source else None)
        )
    return tuple(out)


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
    parts = [
        f"{n} (missing)"
        if v.source is None
        else f"{n} ({v.confidence.name}, at {v.source.locator})"
        for n, v in bad
    ]
    return Finding(
        rule_id,
        Severity.NEEDS_REVIEW,
        f"{unit}: not checked. Input not usable: {'; '.join(parts)}.",
        rule_ref,
        source,
        inputs_used(required),
        fix,
    )
