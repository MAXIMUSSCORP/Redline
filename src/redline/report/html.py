from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from itertools import islice

from jinja2 import Environment, PackageLoader, StrictUndefined

from redline.config import Config, is_test_config, table_verified
from redline.engine import RunResult
from redline.findings import Finding, Severity
from redline.model import Confidence, Project, clip
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
    "coverage",
    "config-tables",
    "footer",
)
EMPTY = "—"
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


def _pairs(items: Iterable[tuple[object, object]], total: int) -> list[tuple[str, str]]:
    """Display pairs, clipped one by one so equal-looking keys stay separate rows."""
    out = [(clip(k), clip(v, 200)) for k, v in islice(items, MAX_ROWS)]
    if total > MAX_ROWS:
        out.append((f"and {total - MAX_ROWS} more", ""))
    return out


def _text(items: Iterable[object], total: int) -> str:
    out = [clip(x, 200) for x in islice(items, MAX_ROWS)]
    if total > MAX_ROWS:
        out.append(f"and {total - MAX_ROWS} more")
    return "; ".join(out)


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
        ],
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
        hashes=_pairs(cfg.hashes.items(), len(cfg.hashes)),
        tables=[
            {
                "name": clip(name),
                "verified": table_verified(cfg, name),
                "source": _or_empty(clip(t.get("source"), 200)),
            }
            for name, t in cfg.cec["tables"].items()
        ],
        tool_version=_or_empty(clip(ri.tool_version) if ri else ""),
        input_tool_version=_or_empty(clip(ri.input_tool_version) if ri else ""),
        input_hashes=_pairs(
            ri.input_config_hashes.items() if ri else (), len(ri.input_config_hashes) if ri else 0
        ),
        input_files=clip("; ".join(islice(project.inputs, 1000)), 2000),
        seeds=_text(
            (f"{clip(k)} {v}" for k, v in (ri.seeds if ri else {}).items()),
            len(ri.seeds) if ri else 0,
        ),
        extractors=_text(
            (f"{clip(k)} {clip(v)}" for k, v in (ri.extractor_versions if ri else {}).items()),
            len(ri.extractor_versions) if ri else 0,
        ),
        models=_text(
            ri.model_ids_versions_hashes if ri else (),
            len(ri.model_ids_versions_hashes) if ri else 0,
        ),
        liability=LIABILITY_SENTENCE,
        empty=EMPTY,
        sev_order=[s.value for s in Severity],
    )
