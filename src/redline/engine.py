from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from redline.config import Config, apply_verification_gate, unverified_tables
from redline.findings import Finding, Severity
from redline.model import Project

RuleFn = Callable[[Project, Config], list[Finding]]


@dataclass(frozen=True)
class RuleSpec:
    id: str
    name: str
    fn: RuleFn
    tables_used: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunResult:
    findings: tuple[Finding, ...]
    ran: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...]  # (rule_id, reason)
    unverified: dict[str, tuple[str, ...]]  # only rules that use an unverified table


def _not_run(spec: RuleSpec, reason: str) -> Finding:
    return Finding(spec.id, Severity.NOT_CHECKED, f"{spec.name} did not run: {reason}.", "", None)


def run(
    project: Project, cfg: Config, rules: Sequence[RuleSpec], skip: Collection[str] = ()
) -> RunResult:
    findings: list[Finding] = []
    ran: list[str] = []
    skipped: list[tuple[str, str]] = []
    unverified: dict[str, tuple[str, ...]] = {}
    for spec in rules:
        if spec.id in skip:
            reason = "skipped by request"
        else:
            try:
                out = spec.fn(project, cfg)
            except Exception as e:  # noqa: BLE001 - any rule failure must be reported, not raised
                reason = f"{type(e).__name__}: {e}"
            else:
                findings += apply_verification_gate(out, spec.tables_used, cfg)
                ran.append(spec.id)
                if bad := unverified_tables(cfg, spec.tables_used):
                    unverified[spec.id] = bad
                continue
        skipped.append((spec.id, reason))
        findings.append(_not_run(spec, reason))
    return RunResult(tuple(findings), tuple(ran), tuple(skipped), unverified)
