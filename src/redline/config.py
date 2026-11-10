from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from redline.findings import Finding, Severity
from redline.model import MAX_INT, Confidence, Method, Source, Value

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
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError) as e:
        raise ConfigError(f"{path.name}: cannot read config file ({type(e).__name__})") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: expected a mapping at the top level")
    return data


_NUM, _STR, _BOOL = "a finite number", "a string", "true or false"
_SCALAR = "a string or number"
_POS = "a number above zero"  # a divisor
_NONNEG = "a number of zero or more"
_FRAC = "a number above zero and at most one"
_PHASE = "A, B or C"
_ROW = (_NUM, _NUM)  # a tuple is a list of exactly that shape, "*" in a dict is any key
_VD_PHASE = {"single": _POS, "three": _POS}
# Expected type of every config leaf a rule reads. A null is allowed anywhere: it makes the
# table unverified. Keys not named here are not read by any rule and are left alone.
_SHAPE = {
    "defaults": {
        "*": _SCALAR,
        "conductors_in_raceway": _NUM,
        "ambient_c": _NUM,
        "termination_temp_c": _NUM,
    },
    "completeness": {
        "placeholder_texts": [_STR],
        "spare_keywords": [_STR],
        **{f"require_{k}": _BOOL for k in ("description", "load", "breaker", "conductor_size")},
    },
    "tables": {
        "conductor_ampacity": {"values": {"*": {"*": {"*": _NUM}}}},
        "ambient_temp_correction": {"values": {"*": [_ROW]}},
        "conductor_count_correction": {"values": [_ROW]},
        "continuous_load": {"max_fraction_of_breaker": _NUM},
        "standard_breaker_ratings": {"values_a": [_NUM]},
        "allow_next_standard_size": {"enabled": _BOOL},
        "bonding_conductor_size": {
            "values": [{"max_ocpd_a": _NUM, "copper_size": _STR, "aluminum_size": _STR}]
        },
        "conductor_size_order": {"values": [_STR]},
        "voltage_drop": {
            "method": _STR,
            "current_basis": _STR,
            "show_passing": _BOOL,
            **{k: _NUM for k in ("branch_max_pct", "feeder_max_pct", "total_max_pct")},
            "k_factor": {
                "constant_by_material": {"*": _POS},
                "area_by_size": {"*": _POS},
                "phase_multiplier": _VD_PHASE,
            },
            "impedance": {
                "power_factor": _FRAC,
                "phase_multiplier": _VD_PHASE,
                "per_size": {"*": {"*": {"r": _POS, "x": _NONNEG}}},
            },
        },
        "demand_factors": {
            "by_load_type": {"*": [{"up_to_va": _NUM, "factor": _POS}]},
            **{
                k: _NUM
                for k in (
                    "bus_loading_limit_fraction",
                    "main_loading_limit_fraction",
                    "supplied_vs_computed_tolerance_pct",
                )
            },
        },
        "phase_balance": {"max_deviation_pct": _NUM, "min_circuits_to_check": _NUM},
        "phase_layout": {"three_phase_pattern": [_PHASE]},
    },
}


_LEAF = {
    _NUM: lambda x: isinstance(x, int | float) and not isinstance(x, bool),
    _STR: lambda x: isinstance(x, str),
    _BOOL: lambda x: isinstance(x, bool),
    _SCALAR: lambda x: isinstance(x, str | int | float) and not isinstance(x, bool),
    _POS: lambda x: isinstance(x, int | float) and not isinstance(x, bool) and x > 0,
    _FRAC: lambda x: isinstance(x, int | float) and not isinstance(x, bool) and 0 < x <= 1,
    _NONNEG: lambda x: isinstance(x, int | float) and not isinstance(x, bool) and x >= 0,
    _PHASE: lambda x: x in ("A", "B", "C"),
}


def _conform(node: Any, shape: Any, path: str, seen: set | None = None) -> None:
    """Raise ConfigError where a leaf is not the type the rules read."""
    seen = set() if seen is None else seen
    if node is None or (id(node), id(shape)) in seen:  # a shared alias is checked once
        return
    seen.add((id(node), id(shape)))
    if isinstance(shape, str):
        ok, want = _LEAF[shape](node), shape
        if isinstance(node, float) and not math.isfinite(node):
            ok = False
        if isinstance(node, int) and abs(node) > MAX_INT:
            ok = False
    elif isinstance(shape, dict):
        ok, want = isinstance(node, dict), "a mapping"
    else:
        ok, want = isinstance(node, list), "a list"
        if isinstance(shape, tuple) and ok and len(node) != len(shape):
            ok = False
    if not ok:
        raise ConfigError(f"cec_tables.yaml: {path} must be {want}")
    if isinstance(shape, dict):
        for k, v in node.items():
            if sub := shape.get(k, shape.get("*")):
                _conform(v, sub, f"{path}.{k}", seen)
    elif not isinstance(shape, str):
        for i, v in enumerate(node):
            # A null cell of a row is a null leaf. A null row or list element is not a table.
            if v is None and not isinstance(shape, tuple):
                raise ConfigError(f"cec_tables.yaml: {path}[{i}] must not be empty")
            _conform(v, shape[i] if isinstance(shape, tuple) else shape[0], f"{path}[{i}]", seen)


def _check_cec(cec: dict[str, Any]) -> None:
    tables = cec.get("tables")
    if not isinstance(tables, dict):
        raise ConfigError("cec_tables.yaml: tables must be a mapping")
    for name, t in tables.items():
        if not isinstance(t, dict) or not isinstance(t.get("verified"), bool):
            raise ConfigError(f"cec_tables.yaml: table {name} needs a verified true or false")
        if not isinstance(t.get("source"), str):
            raise ConfigError(f"cec_tables.yaml: table {name} needs a source string")
        _has_bad_null(name, t)
    for key in ("defaults", "rule_refs"):
        if cec.get(key) is not None and not isinstance(cec[key], dict):
            raise ConfigError(f"cec_tables.yaml: {key} must be a mapping")
    if not isinstance(cec.get("code_edition_verified"), bool):
        raise ConfigError("cec_tables.yaml: code_edition_verified needs true or false")
    comp = cec.get("completeness")
    if not isinstance(comp, dict):
        raise ConfigError("cec_tables.yaml: completeness must be a mapping")
    for key in (f"require_{k}" for k in ("description", "load", "breaker", "conductor_size")):
        if not isinstance(comp.get(key), bool):
            raise ConfigError(f"cec_tables.yaml: completeness {key} must be true or false")
    for key in ("code_edition", "config_version"):
        if not isinstance(cec.get(key), str):
            raise ConfigError(f"cec_tables.yaml: {key} must be a string")
    if not all(isinstance(v, str) for v in (cec.get("rule_refs") or {}).values()):
        raise ConfigError("cec_tables.yaml: every rule_refs value must be a string")
    _conform(cec, _SHAPE, "cec_tables.yaml")
    sev = str(comp.get("severity")).upper()
    if sev not in Severity.__members__ or sev == Severity.VIOLATION:
        raise ConfigError(
            "cec_tables.yaml: completeness severity must be a Severity, not VIOLATION"
        )


def _check_ai(ai: dict[str, Any]) -> None:
    models = ai.get("models") or {}
    roles = ai.get("roles") or {}
    bad = "ai.yaml: models and roles must be mappings of the expected shape"
    if not isinstance(models, dict) or not isinstance(roles, dict):
        raise ConfigError(bad)
    if not all(isinstance(k, str) and isinstance(v, dict) for k, v in models.items()):
        raise ConfigError(bad)
    for r in roles.values():
        if not isinstance(r, dict) or not all(
            isinstance(names, list) and all(isinstance(n, str) for n in names)
            for names in r.values()
        ):
            raise ConfigError(bad)
    role_names = {n for r in roles.values() for names in r.values() for n in names}
    for name in sorted(set(models) | role_names):
        if name.startswith(_RF_DETR) and name[len(_RF_DETR) :] not in RF_DETR_SIZES:
            raise ConfigError(f"ai.yaml: {name} is not an allowed RF-DETR size")
    tier = ai.get("tier")
    if not isinstance(tier, str):
        raise ConfigError("ai.yaml: tier must be a string")
    if ai.get("enabled") is not True:
        return
    for role, by_tier in roles.items():
        for name in by_tier.get(tier) or []:
            if not (models.get(name) or {}).get("weights_sha256"):
                raise ConfigError(
                    f"ai.yaml: AI cannot be enabled, {name} (role {role}) has no weights hash"
                )


def _check_dxf_parsing(parsing: dict[str, Any]) -> None:
    if parsing.get("dxf_stale_field_policy") != "low":
        raise ConfigError('column_maps.yaml: parsing.dxf_stale_field_policy must be "low"')
    if parsing.get("dxf_prefer_extractor") not in ("acad_plugin", "oda_ezdxf"):
        raise ConfigError(
            'column_maps.yaml: parsing.dxf_prefer_extractor must be "acad_plugin" or "oda_ezdxf"'
        )
    for key in ("dxf_extractor_timeout_s", "row_tolerance_text_heights", "column_gap_fraction"):
        x = parsing.get(key)
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not 0 < x < math.inf:
            raise ConfigError(f"column_maps.yaml: parsing.{key} must be a number above zero")
    n = parsing.get("dxf_table_min_cells")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ConfigError(
            "column_maps.yaml: parsing.dxf_table_min_cells must be an integer of 1 or more"
        )
    for key in ("accoreconsole_path", "acad_plugin_dll", "odafc_path"):
        if key not in parsing or not (
            parsing[key] is None or (isinstance(parsing[key], str) and parsing[key].strip())
        ):
            raise ConfigError(f"column_maps.yaml: parsing.{key} must be null or a non-empty string")


def _check_column_maps(cm: dict[str, Any]) -> None:
    for key in ("csv_panel_schedule", "panel_header_block"):
        m = cm.get(key)
        if not isinstance(m, dict) or not all(
            isinstance(k, str)
            and isinstance(v, list)
            and all(isinstance(a, str) and a.strip() for a in v)
            for k, v in m.items()
        ):
            raise ConfigError(
                f"column_maps.yaml: {key} must map names to lists of non-empty strings"
            )
    two = cm.get("two_column_layout")
    if not isinstance(two, dict) or not isinstance(two.get("detect_when_headers_repeat"), bool):
        raise ConfigError(
            "column_maps.yaml: two_column_layout.detect_when_headers_repeat must be true or false"
        )
    parsing = cm.get("parsing")
    n = parsing.get("min_header_alias_matches") if isinstance(parsing, dict) else None
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ConfigError(
            "column_maps.yaml: parsing.min_header_alias_matches must be an integer of 1 or more"
        )
    _check_dxf_parsing(parsing)
    wd = (cm.get("aecad_project") or {}).get("wd_m_attribute_map")
    if not isinstance(wd, dict) or not all(
        isinstance(k, str)
        and isinstance(v, list)
        and all(isinstance(a, str) and a.strip() for a in v)
        for k, v in wd.items()
    ):
        raise ConfigError(
            "column_maps.yaml: aecad_project.wd_m_attribute_map must map names to lists"
            " of non-empty strings"
        )


def load_config(config_dir: str | Path) -> Config:
    d = Path(config_dir)
    docs = {f: _read(d / f) for f in CONFIG_FILES}
    _check_cec(docs["cec_tables.yaml"])
    _check_ai(docs["ai.yaml"])
    _check_column_maps(docs["column_maps.yaml"])
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


_MAX_DEPTH = 100


def _has_null(node: Any, depth: int = 0, seen: set[int] | None = None) -> bool:
    if depth > _MAX_DEPTH:
        raise ConfigError("cec_tables.yaml: nested too deep, or a recursive anchor")
    if node is None:
        return True
    if not isinstance(node, dict | list):
        return False
    seen = set() if seen is None else seen
    if id(node) in seen:  # a shared alias already walked to the end
        return False
    kids = node.values() if isinstance(node, dict) else node
    found = any(_has_null(v, depth + 1, seen) for v in kids)
    seen.add(id(node))  # added after the walk, so a loop still reaches the depth limit
    return found


def _has_bad_null(name: str, t: dict) -> bool:
    if name == "demand_factors":
        t = dict(t)
        tiers = t.pop("by_load_type", None)
        if _has_null(t):
            return True
        if not isinstance(tiers, dict):
            return True
        for tier in tiers.values():
            if not isinstance(tier, list):
                return True
            for i, row in enumerate(tier):
                if isinstance(row, dict) and i == len(tier) - 1:
                    row = {k: v for k, v in row.items() if k != "up_to_va"}
                if _has_null(row):
                    return True
        return False
    if name == "voltage_drop":
        method = t.get("method")
        t = {k: v for k, v in t.items() if k not in ("k_factor", "impedance") or k == method}
    return _has_null(t)


def table_verified(cfg: Config, name: str) -> bool:
    t = cfg.cec["tables"].get(name)
    return (
        isinstance(t, dict)
        and t.get("verified") is True
        and bool(str(t.get("source") or "").strip())
        and not _has_bad_null(name, t)
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
