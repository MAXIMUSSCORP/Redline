from __future__ import annotations

from collections import Counter

from jinja2 import Environment, PackageLoader, StrictUndefined

from redline.config import Config, is_test_config, table_verified
from redline.engine import RunResult
from redline.findings import Finding, Severity
from redline.model import Confidence, Project
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
            "file": _or_empty(f.source.file if f.source else ""),
            "loc": _or_empty(f.source.locator if f.source else ""),
            "fix": _or_empty(f.suggested_fix),
            "inputs": format_inputs(f),
            "medium": _medium_note(f),
        }
        for f in sorted(result.findings, key=lambda f: _ORDER[f.severity])
    ]
    ri = project.run_info
    return _env.get_template("template.html.j2").render(
        project=project,
        result=result,
        findings=findings,
        manual=[
            x for x in findings if x["f"].severity in (Severity.NEEDS_REVIEW, Severity.NOT_CHECKED)
        ],
        sev_counts={s.value: sev_counts.get(s, 0) for s in Severity},
        per_rule=per_rule,
        is_test=is_test_config(cfg),
        test_label=cfg.cec.get("code_edition"),
        edition=_or_empty(cfg.cec.get("code_edition")),
        edition_verified=bool(cfg.cec.get("code_edition_verified")),
        config_version=_or_empty(cfg.cec.get("config_version")),
        hashes=cfg.hashes,
        tables=[
            {
                "name": name,
                "verified": table_verified(cfg, name),
                "source": _or_empty(t.get("source")),
            }
            for name, t in cfg.cec["tables"].items()
        ],
        tool_version=_or_empty(ri.tool_version if ri else ""),
        extractors=ri.extractor_versions if ri else {},
        models=ri.model_ids_versions_hashes if ri else [],
        liability=LIABILITY_SENTENCE,
        empty=EMPTY,
        sev_order=[s.value for s in Severity],
    )
