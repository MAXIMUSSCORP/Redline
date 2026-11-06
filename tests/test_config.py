import shutil
from pathlib import Path

import pytest
import yaml

from redline.config import (
    CONFIG_FILES,
    TEST_EDITION_LABEL,
    TEST_SOURCE_LABEL,
    ConfigError,
    apply_verification_gate,
    default_value,
    is_test_config,
    load_config,
    lookup,
    rule_ref,
    table_verified,
    unverified_tables,
)
from redline.findings import Finding, Severity
from redline.model import Confidence, Method

ROOT = Path(__file__).resolve().parent.parent


def _violation() -> Finding:
    return Finding("r", Severity.VIOLATION, "ckt 1 is over.", "ref", None)


def _copy_edit(tmp_path, name, edit):
    """Copy the TEST config to tmp_path and apply edit(dict) to one file."""
    for f in CONFIG_FILES:
        shutil.copy(ROOT / "tests" / "test_config" / f, tmp_path / f)
    p = tmp_path / name
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    edit(data)
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return tmp_path


def _numeric_leaves(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from _numeric_leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from _numeric_leaves(v)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        yield node


def _null_leaves(node):
    if node is None:
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _null_leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from _null_leaves(v)


def test_unverified_table_downgrades_violation(test_cfg, cfg_unverify):
    used = ("continuous_load", "voltage_drop")
    assert apply_verification_gate([_violation()], used, test_cfg)[0].severity == Severity.VIOLATION
    cfg = cfg_unverify(test_cfg, "voltage_drop")
    out = apply_verification_gate([_violation()], used, cfg)
    assert out[0].severity == Severity.NEEDS_REVIEW
    assert "voltage_drop" in out[0].message
    assert "continuous_load" not in out[0].message
    info = Finding("r", Severity.INFO, "x", "ref", None)
    assert apply_verification_gate([info], used, cfg) == [info]


def test_unverified_edition_downgrades_violation(test_cfg, cfg_set):
    cfg = cfg_set(test_cfg, ("code_edition_verified",), False)
    out = apply_verification_gate([_violation()], (), cfg)
    assert out[0].severity == Severity.NEEDS_REVIEW
    assert "code edition" in out[0].message


def test_skeleton_downgrades_violation(skeleton_cfg):
    out = apply_verification_gate([_violation()], ("ampacity",), skeleton_cfg)
    assert out[0].severity == Severity.NEEDS_REVIEW
    out = apply_verification_gate([_violation()], (), skeleton_cfg)
    assert out[0].severity == Severity.NEEDS_REVIEW


def test_hash_changes_with_file(tmp_path):
    cfg_dir = _copy_edit(tmp_path, "cec_tables.yaml", lambda d: None)
    before = load_config(cfg_dir)
    p = cfg_dir / "cec_tables.yaml"
    p.write_text(p.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    after = load_config(cfg_dir)
    assert before.hashes["cec_tables.yaml"] != after.hashes["cec_tables.yaml"]
    assert before.hashes["ai.yaml"] == after.hashes["ai.yaml"]
    assert set(after.hashes) == set(CONFIG_FILES)
    assert len(after.hashes["ai.yaml"]) == 64


def test_empty_weights_hash_cannot_enable(tmp_path):
    def enable(d):
        d["enabled"] = True

    with pytest.raises(ConfigError, match="weights hash"):
        load_config(_copy_edit(tmp_path, "ai.yaml", enable))


def test_enabled_with_hashes_loads(tmp_path):
    def enable(d):
        d["enabled"] = True
        for m in d["models"].values():
            m["weights_sha256"] = "0" * 64

    assert load_config(_copy_edit(tmp_path, "ai.yaml", enable)).ai["enabled"] is True


def test_rf_detr_size_rejected_by_config(tmp_path):
    def add(d):
        d["models"]["rf-detr-xl"] = {"version": "<pin>", "weights_sha256": ""}

    with pytest.raises(ConfigError, match="RF-DETR"):
        load_config(_copy_edit(tmp_path, "ai.yaml", add))


def test_skeleton_holds_no_values(skeleton_cfg):
    assert skeleton_cfg.cec["code_edition_verified"] is False
    assert not any(v is not None for v in skeleton_cfg.cec["defaults"].values())
    for name, t in skeleton_cfg.cec["tables"].items():
        assert t["verified"] is False, name
        assert not list(_numeric_leaves(t)), name
    assert list(_null_leaves(skeleton_cfg.cec["tables"]))
    assert not any(table_verified(skeleton_cfg, n) for n in skeleton_cfg.cec["tables"])
    assert not is_test_config(skeleton_cfg)
    assert skeleton_cfg.ai["enabled"] is False


def test_test_config_labelled(test_cfg):
    assert test_cfg.cec["code_edition"] == TEST_EDITION_LABEL
    assert test_cfg.cec["code_edition_verified"] is True
    assert is_test_config(test_cfg)
    for name, t in test_cfg.cec["tables"].items():
        assert t["verified"] is True, name
        assert t["source"] == TEST_SOURCE_LABEL, name
        assert table_verified(test_cfg, name), name
    assert not list(_null_leaves(test_cfg.cec["tables"]))
    # conductors_in_raceway stays null on purpose: the rule then reports it as missing.
    defaults = {k: v for k, v in test_cfg.cec["defaults"].items() if k != "conductors_in_raceway"}
    assert not list(_null_leaves(defaults))
    assert not unverified_tables(test_cfg, test_cfg.cec["tables"])


def test_completeness_severity_violation_rejected(tmp_path):
    def bad(d):
        d["completeness"]["severity"] = "VIOLATION"

    with pytest.raises(ConfigError, match="completeness"):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", bad))


def test_table_without_verified_flag_rejected(tmp_path):
    def bad(d):
        del d["tables"]["phase_balance"]["verified"]

    with pytest.raises(ConfigError, match="phase_balance"):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", bad))


def test_missing_file_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_lookup_null_returns_none(test_cfg, skeleton_cfg, cfg_set):
    assert lookup(test_cfg, "conductor_ampacity", "values", "copper", "12 AWG", "75") == 20
    assert lookup(skeleton_cfg, "conductor_ampacity", "values", "copper", "12 AWG", "75") is None
    assert lookup(test_cfg, "conductor_ampacity", "values", "copper", "99 AWG", "75") is None
    assert lookup(test_cfg, "no_such_table", "values") is None
    assert lookup(test_cfg, "conductor_count_correction", "values", "0", "1") == 1.0
    cfg = cfg_set(test_cfg, ("tables", "continuous_load", "max_fraction_of_breaker"), None)
    assert lookup(cfg, "continuous_load", "max_fraction_of_breaker") is None


def test_table_verified_rejects_null_and_blank_source(test_cfg, cfg_set):
    cfg = cfg_set(test_cfg, ("tables", "continuous_load", "max_fraction_of_breaker"), None)
    assert not table_verified(cfg, "continuous_load")
    cfg = cfg_set(test_cfg, ("tables", "continuous_load", "source"), "  ")
    assert not table_verified(cfg, "continuous_load")
    assert not table_verified(test_cfg, "no_such_table")


def test_default_value(test_cfg, skeleton_cfg):
    v = default_value(test_cfg, "ambient_c")
    assert v.value == 30
    assert v.confidence == Confidence.MEDIUM
    assert v.usable
    assert v.source.note == "config default"
    assert v.source.method == Method.DERIVED
    assert v.source.locator == "defaults.ambient_c"
    assert default_value(skeleton_cfg, "ambient_c").confidence == Confidence.MISSING


def test_rule_ref(test_cfg, skeleton_cfg):
    assert rule_ref(test_cfg, "ampacity") == "TEST Rule AMP-1"
    assert rule_ref(test_cfg, "nope") == "rule_ref missing in config [VERIFY]"
    assert "[VERIFY]" in rule_ref(skeleton_cfg, "ampacity")


@pytest.mark.parametrize("bad", ["false", 1, None])
def test_code_edition_verified_must_be_bool(tmp_path, bad):
    def edit(d):
        d["code_edition_verified"] = bad

    with pytest.raises(ConfigError, match="code_edition_verified"):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", edit))


@pytest.mark.parametrize(
    ("name", "edit"),
    [
        ("ai.yaml", lambda d: d.update(roles={"ocr": 5})),
        ("ai.yaml", lambda d: d.update(models={1: {}})),
        ("ai.yaml", lambda d: d.update(roles={"r": {"t1": None}})),
        ("cec_tables.yaml", lambda d: d.update(completeness=["x"])),
        ("cec_tables.yaml", lambda d: d.update(completeness="x")),
    ],
)
def test_config_wrong_types_raise_config_error(tmp_path, name, edit):
    with pytest.raises(ConfigError):
        load_config(_copy_edit(tmp_path, name, edit))


def test_unbounded_last_tier_can_be_verified(test_cfg, cfg_set):
    tiers = test_cfg.cec["tables"]["demand_factors"]["by_load_type"]["continuous"]
    cfg = cfg_set(
        test_cfg,
        ("tables", "demand_factors", "by_load_type", "continuous"),
        [*tiers[:-1], {**tiers[-1], "up_to_va": None}],
    )
    assert table_verified(cfg, "demand_factors")
    first = [{**tiers[0], "up_to_va": None}, *tiers[1:]]
    if len(tiers) > 1:
        cfg = cfg_set(test_cfg, ("tables", "demand_factors", "by_load_type", "continuous"), first)
        assert not table_verified(cfg, "demand_factors")
    cfg = cfg_set(test_cfg, ("tables", "demand_factors", "bus_loading_limit_fraction"), None)
    assert not table_verified(cfg, "demand_factors")


def test_unused_vd_method_block_does_not_unverify(test_cfg, cfg_set):
    vd = test_cfg.cec["tables"]["voltage_drop"]
    unused = "impedance" if vd["method"] == "k_factor" else "k_factor"
    used = "k_factor" if unused == "impedance" else "impedance"
    cfg = cfg_set(test_cfg, ("tables", "voltage_drop", unused), {"x": None})
    assert table_verified(cfg, "voltage_drop")
    cfg = cfg_set(test_cfg, ("tables", "voltage_drop", used), {"x": None})
    assert not table_verified(cfg, "voltage_drop")
