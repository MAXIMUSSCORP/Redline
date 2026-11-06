from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from redline.findings import Finding

CSV_COLUMNS = (
    "rule_id",
    "severity",
    "rule_ref",
    "file",
    "locator",
    "message",
    "suggested_fix",
    "inputs_used",
)


def format_inputs(f: Finding) -> str:
    return "; ".join(
        f"{i.field}={i.value} @ {i.locator}"
        + (f" ({i.confidence.name})" if i.confidence is not None else "")
        for i in f.inputs_used
    )


def _safe(cell: object) -> str:
    # Spreadsheet formula injection. A lone "-" is a plain dash, not a formula.
    # Leading whitespace (incl. no-break space) is skipped when finding the trigger character.
    text = str(cell)
    if (
        text
        and text != "-"
        and (text[:1] in "=+-@\t\r" or text.lstrip()[:1] in ("=", "+", "-", "@"))
    ):
        return "'" + text
    return text


def write_findings_csv(findings: Iterable[Finding], path: Path) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for f in findings:
            row = (
                f.rule_id,
                f.severity.value,
                f.rule_ref,
                f.source.file if f.source else "",
                f.source.locator if f.source else "",
                f.message,
                f.suggested_fix,
                format_inputs(f),
            )
            w.writerow([_safe(c) for c in row])
