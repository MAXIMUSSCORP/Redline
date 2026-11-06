from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from redline.findings import Finding, Severity
from redline.model import Confidence, Method, Source, Value

TEST_EDITION_LABEL = "TEST EDITION, NOT CEC"
TEST_SOURCE_LABEL = "TEST ONLY, NOT CEC VALUES"
CONFIG_FILES = ("cec_tables.yaml", "column_maps.yaml", "ai.yaml", "fire_alarm.yaml")
RF_DETR_SIZES = ("nano", "small", "medium", "large")
_RF_DETR = "rf-detr-"
_REF_MISSING = "rule_ref missing in config [VERIFY]"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    dir: Path
    cec: dict[str, Any]
    column_maps: dict[str, Any]
    ai: dict[str, Any]
    fire_alarm: dict[str, Any]
    hashes: dict[str, str]


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"{path.name}: cannot read config file ({type(e).__name__})") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: expected a mapping at the top level")
    return data


def _check_cec(cec: dict[str, Any]) -> None:
    tables = cec.get("tables")
    if not isinstance(tables, dict):
        raise ConfigError("cec_tables.yaml: tables must be a mapping")
    for name, t in tables.items():
        if not isinstance(t, dict) or not isinstance(t.get("verified"), bool):
            raise ConfigError(f"cec_tables.yaml: table {name} needs a verified true or false")
        if not isinstance(t.get("source"), str):
            raise ConfigError(f"cec_tables.yaml: table {name} needs a source string")
    sev = (cec.get("completeness") or {}).get("severity")
    if str(sev).upper() == Severity.VIOLATION:
        raise ConfigError("cec_tables.yaml: completeness severity cannot be VIOLATION")


def _check_ai(ai: dict[str, Any]) -> None:
    models = ai.get("models") or {}
    roles = ai.get("roles") or {}
    role_names = {n for r in roles.values() for names in r.values() for n in names}
    for name in sorted(set(models) | role_names):
        if name.startswith(_RF_DETR) and name[len(_RF_DETR) :] not in RF_DETR_SIZES:
            raise ConfigError(f"ai.yaml: {name} is not an allowed RF-DETR size")
    if ai.get("enabled") is not True:
        return
    tier = ai.get("tier")
    for role, by_tier in roles.items():
        for name in by_tier.get(tier, []):
            if not (models.get(name) or {}).get("weights_sha256"):
                raise ConfigError(
                    f"ai.yaml: AI cannot be enabled, {name} (role {role}) has no weights hash"
                )


def load_config(config_dir: str | Path) -> Config:
    d = Path(config_dir)
    docs = {f: _read(d / f) for f in CONFIG_FILES}
    _check_cec(docs["cec_tables.yaml"])
    _check_ai(docs["ai.yaml"])
    return Config(
        dir=d,
        cec=docs["cec_tables.yaml"],
        column_maps=docs["column_maps.yaml"],
        ai=docs["ai.yaml"],
        fire_alarm=docs["fire_alarm.yaml"],
        hashes={f: sha256_file(d / f) for f in CONFIG_FILES},
    )


def is_test_config(cfg: Config) -> bool:
    if cfg.cec.get("code_edition") == TEST_EDITION_LABEL:
        return True
    return any(t.get("source") == TEST_SOURCE_LABEL for t in cfg.cec["tables"].values())


def _has_null(node: Any) -> bool:
    if node is None:
        return True
    if isinstance(node, dict):
        return any(_has_null(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_null(v) for v in node)
    return False


def table_verified(cfg: Config, name: str) -> bool:
    t = cfg.cec["tables"].get(name)
    return (
        isinstance(t, dict)
        and t.get("verified") is True
        and bool(str(t.get("source") or "").strip())
        and not _has_null(t)
    )


def unverified_tables(cfg: Config, names: Iterable[str]) -> tuple[str, ...]:
    return tuple(n for n in names if not table_verified(cfg, n))


def lookup(cfg: Config, table: str, *keys: str) -> Any | None:
    node: Any = cfg.cec["tables"].get(table)
    for k in keys:
        if isinstance(node, dict):
            node = node.get(k)
        elif isinstance(node, list) and str(k).isdigit() and int(k) < len(node):
            node = node[int(k)]
        else:
            return None
        if node is None:
            return None
    return node


def default_value(cfg: Config, key: str) -> Value:
    v = (cfg.cec.get("defaults") or {}).get(key)
    if v is None:
        return Value.missing()
    src = Source(
        "cec_tables.yaml", f"defaults.{key}", Method.DERIVED, Confidence.MEDIUM, "config default"
    )
    return Value(v, src, str(v))


def rule_ref(cfg: Config, key: str) -> str:
    return (cfg.cec.get("rule_refs") or {}).get(key) or _REF_MISSING


def apply_verification_gate(
    findings: list[Finding], tables_used: tuple[str, ...], cfg: Config
) -> list[Finding]:
    bad = unverified_tables(cfg, tables_used)
    edition_bad = cfg.cec.get("code_edition_verified") is not True
    if not bad and not edition_bad:
        return findings
    why = []
    if bad:
        why.append("tables " + ", ".join(bad))
    if edition_bad:
        why.append("the code edition")
    note = f"Downgraded from VIOLATION because config is not verified: {'; '.join(why)}."
    return [
        replace(f, severity=Severity.NEEDS_REVIEW, message=f"{f.message} {note}")
        if f.severity == Severity.VIOLATION
        else f
        for f in findings
    ]
