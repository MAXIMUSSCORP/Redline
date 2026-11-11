from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from itertools import islice

from jinja2 import Environment, PackageLoader, StrictUndefined

from redline.config import FIRE_ALARM_TABLE, Config, is_test_config, table_verified
from redline.engine import RunResult
from redline.findings import Finding, Severity
from redline.model import Confidence, Project, Unparsed, Value, clip
from redline.report.csv_out import format_inputs

LIABILITY_SENTENCE = (
    "Redline is pre-review screening for a qualified reviewer. "
    "It is not a design approval, a stamp, or a compliance certificate."
)
SECTION_IDS = (
    "banner",
    "summary",
    "rules",
    "findings",
    "manual-check",
    "devices",
    "coverage",
    "config-tables",
    "footer",
)
EMPTY = "—"
BLOCK_LIMIT = 500  # unmatched block names shown per file; its own limit, not MAX_ROWS (D12)
DETECTION_COLUMNS = ("block", "list", "unused", "nested", "paper", "detector")
_ORDER = {s: i for i, s in enumerate(Severity)}

_env = Environment(
    loader=PackageLoader("redline", "report"),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _or_empty(text: object) -> str:
    return str(text) if text not in (None, "") else EMPTY


MAX_ROWS = 50


def _pairs(
    items: Iterable[tuple[object, object]], total: int, noun: str
) -> list[tuple[str, str | None]]:
    """Display pairs, clipped one by one so equal-looking keys stay separate rows."""
    out = [(clip(k), clip(v, 200)) for k, v in islice(items, MAX_ROWS)]
    if total > MAX_ROWS:
        out.append((f"and {total - MAX_ROWS} more {noun}", None))
    return out


def _text(items: Iterable[object], total: int, noun: str, limit: int = 200) -> str:
    out = [clip(x, limit) for x in islice(items, MAX_ROWS)]
    if total > MAX_ROWS:
        out.append(f"and {total - MAX_ROWS} more {noun}")
    return "; ".join(out)


_PLACED = re.compile(r"(\d+) placed, (\d+) inside")


def _units_text(v: Value | None) -> str:
    if v is None:
        return "not stated"
    s = v.source
    where = f"{s.file} {s.locator}" + (f"; {s.note}" if s.note else "") if s else EMPTY
    said = f"drawing states {clip(v.raw)}" if v.raw not in (None, "", v.value) else ""
    extra = "; ".join(x for x in (where, said) if x)
    return f"{clip(v.value) if v.value is not None else 'not usable'} (source: {extra})"


def _devices(project: Project, cfg: Config) -> dict:
    """The Devices and exits section: counts per sheet and class, and the unmatched block names."""
    names: dict[str, str] = {}  # casefold -> first spelling, in order of appearance

    def note(sheet: object) -> None:
        s = str(sheet or "").strip()
        names.setdefault(s.casefold(), s or "sheet not stated")

    for s in project.sheet_units:
        note(s)
    for d in project.devices:
        note(d.sheet.value)
    for p in project.paths:
        note(p.sheet)
    units = {k.casefold(): v for k, v in project.sheet_units.items()}
    classes = list(cfg.fire_alarm["device_blocks"])
    classes += sorted({d.type for d in project.devices} - set(classes))
    sheets = []
    for key, name in names.items():
        mine = [d for d in project.devices if str(d.sheet.value or "").strip().casefold() == key]
        count: Counter = Counter((d.type, d.detection) for d in mine)
        rows = []
        for cls in classes:
            cells = [str(count[(cls, c)]) for c in DETECTION_COLUMNS]
            layouts = sorted(
                {clip(d.location.value) for d in mine if d.type == cls and d.detection == "paper"}
            )
            if layouts:
                cells[DETECTION_COLUMNS.index("paper")] += " in " + ", ".join(layouts)
            rows.append({"cls": clip(cls), "cells": cells})
        paths = [p for p in project.paths if p.sheet.strip().casefold() == key]
        low = [clip(p.name) for p in paths if p.source.confidence < Confidence.HIGH]
        sheets.append(
            {
                "name": clip(name, 260),
                "units": _units_text(units.get(key)),
                "exits": sum(1 for d in mine if d.type == "exit_door" and d.detection == "list"),
                "paths": len(paths),
                "low": ", ".join(low) or "none",
                "rows": rows,
            }
        )
    by_file: dict[str, list[Unparsed]] = {}
    for u in project.unparsed:
        if u.kind == "block":
            by_file.setdefault(u.source.file, []).append(u)
    unmatched = []
    for file, items in by_file.items():
        items.sort(key=lambda u: u.raw.casefold())
        rows = []
        for u in items[:BLOCK_LIMIT]:
            m = _PLACED.search(u.reason)
            rows.append(
                {
                    "name": clip(u.raw, 200),
                    "placed": m.group(1) if m else EMPTY,
                    "nested": m.group(2) if m else EMPTY,
                }
            )
        hidden = max(0, len(items) - BLOCK_LIMIT)
        unmatched.append(
            {
                "file": _or_empty(clip(file, 260)),
                "rows": rows,
                "total": len(items),
                "hidden": hidden,
                "more": f"and {hidden} more block names in {clip(file, 260)}" if hidden else "",
            }
        )
    return {
        "sheets": sheets,
        "columns": DETECTION_COLUMNS,
        "unmatched": unmatched,
        "none": not sheets and not unmatched,
    }


def _medium_note(f: Finding) -> str:
    mid = [i for i in f.inputs_used if i.confidence == Confidence.MEDIUM]
    if not mid:
        return ""
    models = sorted({i.model for i in mid if i.model})
    tail = f" Model: {', '.join(models)}." if models else ""
    return f"Rests on MEDIUM input: {', '.join(i.field for i in mid)}.{tail}"


def render_html(project: Project, result: RunResult, cfg: Config) -> str:
    sev_counts = Counter(f.severity for f in result.findings)
    rule_ids = (*result.ran, *(r for r, _ in result.skipped))
    per_rule = {
        rid: {
            s.value: sum(1 for f in result.findings if f.rule_id == rid and f.severity == s)
            for s in Severity
        }
        for rid in rule_ids
    }
    findings = [
        {
            "f": f,
            "sev": f.severity.value,
            "ref": _or_empty(f.rule_ref),
            "file": _or_empty(clip(f.source.file, 260) if f.source else ""),
            "loc": _or_empty(clip(f.source.locator) if f.source else ""),
            "fix": _or_empty(f.suggested_fix),
            "inputs": format_inputs(f),
            "medium": _medium_note(f),
        }
        for f in sorted(result.findings, key=lambda f: _ORDER[f.severity])
    ]
    ri = project.run_info
    return _env.get_template("template.html.j2").render(
        project=project,
        project_name=clip(project.name, 200),
        unparsed=[
            {
                "kind": clip(u.kind, 40),
                "raw": _or_empty(clip(u.raw, 200)),
                "file": _or_empty(clip(u.source.file, 260)),
                "loc": _or_empty(clip(u.source.locator)),
                "reason": _or_empty(clip(u.reason, 200)),
            }
            for u in project.unparsed
            if u.kind != "block"
        ],
        devices=_devices(project, cfg),
        coverage=[
            {
                "file": _or_empty(clip(c.file, 260)),
                "unit": _or_empty(clip(c.unit)),
                "what": _or_empty(clip(c.what_read, 200)),
                "method": _or_empty(clip(c.method, 40)),
                "conf": _or_empty(clip(c.confidence_summary, 200)),
            }
            for c in project.coverage
        ],
        result=result,
        findings=findings,
        manual=[
            x for x in findings if x["f"].severity in (Severity.NEEDS_REVIEW, Severity.NOT_CHECKED)
        ],
        sev_counts={s.value: sev_counts.get(s, 0) for s in Severity},
        per_rule=per_rule,
        is_test=is_test_config(cfg),
        test_label=clip(cfg.cec.get("code_edition")),
        edition=_or_empty(clip(cfg.cec.get("code_edition"))),
        project_edition=_or_empty(clip(project.code_edition.strip())),
        edition_differs=bool(project.code_edition.strip())
        and project.code_edition.strip() != str(cfg.cec.get("code_edition")).strip(),
        edition_verified=cfg.cec.get("code_edition_verified") is True,
        config_version=_or_empty(clip(cfg.cec.get("config_version"))),
        hashes=_pairs(cfg.hashes.items(), len(cfg.hashes), "config hashes"),
        tables=[
            {
                "name": clip(name),
                "verified": table_verified(cfg, name),
                "source": _or_empty(clip(t.get("source"), 200)),
            }
            for name, t in cfg.cec["tables"].items()
        ]
        + [
            {
                "name": FIRE_ALARM_TABLE,
                "verified": table_verified(cfg, FIRE_ALARM_TABLE),
                "source": _or_empty(clip(cfg.fire_alarm.get("source"), 200)),
            }
        ],
        tool_version=_or_empty(clip(ri.tool_version) if ri else ""),
        input_tool_version=_or_empty(clip(ri.input_tool_version) if ri else ""),
        input_hashes=_pairs(
            ri.input_config_hashes.items() if ri else (),
            len(ri.input_config_hashes) if ri else 0,
            "input hashes",
        ),
        input_files=clip("; ".join(islice(project.inputs, 1000)), 2000),
        seeds=_text(
            (f"{clip(k)} {v}" for k, v in (ri.seeds if ri else {}).items()),
            len(ri.seeds) if ri else 0,
            "seeds",
        ),
        extractors=_text(
            (f"{clip(k)} {clip(v, 200)}" for k, v in (ri.extractor_versions if ri else {}).items()),
            len(ri.extractor_versions) if ri else 0,
            "extractors",
            limit=300,  # key (80) + space + value (200) must not be cut again
        ),
        models=_text(
            ri.model_ids_versions_hashes if ri else (),
            len(ri.model_ids_versions_hashes) if ri else 0,
            "models",
        ),
        liability=LIABILITY_SENTENCE,
        empty=EMPTY,
        sev_order=[s.value for s in Severity],
    )
