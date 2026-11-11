import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from redline.config import (
    CONFIG_FILES,
    FIRE_ALARM_LIMITS,
    FIRE_ALARM_TABLE,
    TEST_EDITION_LABEL,
    TEST_SOURCE_LABEL,
    ConfigError,
    apply_verification_gate,
    default_value,
    device_classes,
    fire_alarm_limit,
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
    assert lookup(test_cfg, "conductor_ampacity", "values", "copper", "12 AWG", "75") == 23.3
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
    assert v.value == 25
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


def test_config_recursive_anchor_raises_config_error(tmp_path):
    def edit(d):
        t = d["tables"]["phase_balance"]
        t["loop"] = t

    with pytest.raises(ConfigError):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", edit))


@pytest.mark.parametrize("key", ["defaults", "rule_refs"])
def test_config_defaults_and_rule_refs_must_be_mappings(tmp_path, key):
    with pytest.raises(ConfigError, match=key):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", lambda d: d.update({key: ["x"]})))


def test_demand_tier_non_list_unverifies(test_cfg, cfg_set):
    tiers = test_cfg.cec["tables"]["demand_factors"]["by_load_type"]
    bad = {**tiers, "continuous": "x", "motor": [{"up_to_va": None, "factor": None}, {}]}
    cfg = cfg_set(test_cfg, ("tables", "demand_factors", "by_load_type"), bad)
    assert not table_verified(cfg, "demand_factors")


def test_config_deep_nesting_raises_config_error(tmp_path):
    cfg_dir = _copy_edit(tmp_path, "cec_tables.yaml", lambda d: None)
    p = cfg_dir / "cec_tables.yaml"
    p.write_text(p.read_text(encoding="utf-8") + "deep: " + "[" * 1200 + "]" * 1200 + "\n")
    with pytest.raises(ConfigError):
        load_config(cfg_dir)


def _bomb(depth=8):
    out = "b0: &b0 [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]\n"
    for i in range(1, depth + 1):
        out += f"b{i}: &b{i} [{', '.join([f'*b{i - 1}'] * 10)}]\n"
    return out


def test_config_alias_bomb_bounded(tmp_path):
    cfg_dir = _copy_edit(tmp_path, "cec_tables.yaml", lambda d: None)
    p = cfg_dir / "cec_tables.yaml"
    body = "".join(f"    {x}\n" for x in _bomb().splitlines())
    bomb = "    verified: true\n    source: x\n" + body
    text = p.read_text(encoding="utf-8").replace("\ntables:\n", "\ntables:\n  bomb:\n" + bomb, 1)
    p.write_text(text, encoding="utf-8")
    cfg = load_config(cfg_dir)  # bounded work, and a table nothing reads is left alone
    assert table_verified(cfg, "bomb")


def test_config_alias_bomb_in_text_field_raises(tmp_path):
    cfg_dir = _copy_edit(tmp_path, "cec_tables.yaml", lambda d: None)
    p = cfg_dir / "cec_tables.yaml"
    text = p.read_text(encoding="utf-8")
    text = text.replace("  ampacity: TEST Rule AMP-1", "  ampacity: *b8", 1)
    p.write_text(_bomb() + text, encoding="utf-8")
    with pytest.raises(ConfigError, match="rule_refs"):
        load_config(cfg_dir)


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d.pop("completeness"),
        lambda d: d["completeness"].pop("severity"),
        lambda d: d["completeness"].update(severity="bogus"),
        lambda d: d["completeness"].update(severity="violation"),
        lambda d: d["completeness"].update(severity=5),
    ],
)
def test_config_completeness_block_validated(tmp_path, edit):
    with pytest.raises(ConfigError):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", edit))


def test_config_non_utf8_raises_config_error(tmp_path):
    cfg_dir = _copy_edit(tmp_path, "ai.yaml", lambda d: None)
    (cfg_dir / "ai.yaml").write_bytes(b"enabled: false\ntier: \xff\xfe\n")
    with pytest.raises(ConfigError, match="ai.yaml"):
        load_config(cfg_dir)


@pytest.mark.parametrize("tier", [["cpu"], 5, {"a": 1}, None])
@pytest.mark.parametrize("enabled", [True, False])
def test_config_ai_tier_must_be_str(tmp_path, tier, enabled):
    def edit(d):
        d["tier"], d["enabled"] = tier, enabled

    with pytest.raises(ConfigError, match="tier"):
        load_config(_copy_edit(tmp_path, "ai.yaml", edit))


def _put(path, value):
    def edit(d):
        node = d
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value

    return edit


_NAN, _INF = float("nan"), float("inf")
_T = "tables"
_AMP = (_T, "conductor_ampacity", "values", "copper", "12 AWG", "75")
_VD = (_T, "voltage_drop")
_DF = (_T, "demand_factors")
_LEAF_CASES = [
    *[(_AMP, v) for v in ("23", [1], True, _NAN, _INF, {"a": 1}, 10**20)],
    ((_T, "conductor_ampacity", "values", "copper", "12 AWG"), 5),
    ((_T, "conductor_ampacity", "values", "copper"), [1]),
    ((_T, "ambient_temp_correction", "values", "75"), "x"),
    ((_T, "ambient_temp_correction", "values", "75"), [[25, "x"]]),
    ((_T, "ambient_temp_correction", "values", "75"), [[25, 1.0, 3]]),
    ((_T, "ambient_temp_correction", "values", "75"), [[25, True]]),
    ((_T, "conductor_count_correction", "values"), [[4, _NAN]]),
    ((_T, "conductor_count_correction", "values"), {"a": 1}),
    *[((_T, "continuous_load", "max_fraction_of_breaker"), v) for v in (_NAN, True, "0.5", [1])],
    ((_T, "standard_breaker_ratings", "values_a"), "7"),
    ((_T, "standard_breaker_ratings", "values_a"), [7, "13"]),
    ((_T, "allow_next_standard_size", "enabled"), 1),
    ((_T, "allow_next_standard_size", "enabled"), "yes"),
    ((_T, "bonding_conductor_size", "values"), [{"max_ocpd_a": "x", "copper_size": "6 AWG"}]),
    ((_T, "bonding_conductor_size", "values"), [{"max_ocpd_a": 5, "copper_size": 6}]),
    ((_T, "bonding_conductor_size", "values"), ["x"]),
    ((_T, "conductor_size_order", "values"), [1, 2]),
    ((_T, "conductor_size_order", "values"), "14 AWG"),
    ((*_VD, "branch_max_pct"), "2"),
    ((*_VD, "total_max_pct"), _INF),
    ((*_VD, "show_passing"), "no"),
    ((*_VD, "method"), 5),
    ((*_VD, "current_basis"), ["load"]),
    ((*_VD, "k_factor", "constant_by_material", "copper"), "x"),
    ((*_VD, "k_factor", "area_by_size", "12 AWG"), True),
    ((*_VD, "k_factor", "phase_multiplier", "single"), []),
    ((*_VD, "impedance", "power_factor"), _NAN),
    ((*_VD, "impedance", "per_size", "copper", "12 AWG", "r"), "2"),
    ((*_DF, "by_load_type", "continuous"), [{"up_to_va": "x", "factor": 1}]),
    ((*_DF, "by_load_type", "continuous"), "x"),
    ((*_DF, "by_load_type", "continuous"), [5]),
    ((*_DF, "bus_loading_limit_fraction"), _NAN),
    ((*_DF, "main_loading_limit_fraction"), "0.5"),
    ((*_DF, "supplied_vs_computed_tolerance_pct"), True),
    ((_T, "phase_balance", "max_deviation_pct"), "10"),
    ((_T, "phase_balance", "min_circuits_to_check"), True),
    ((_T, "phase_layout", "three_phase_pattern"), [1]),
    (("defaults", "ambient_c"), "25"),
    (("defaults", "termination_temp_c"), True),
    (("defaults", "conductors_in_raceway"), _NAN),
]


@pytest.mark.parametrize(("path", "bad"), _LEAF_CASES)
def test_config_table_leaf_types_validated(tmp_path, path, bad):
    with pytest.raises(ConfigError):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", _put(path, bad)))


@pytest.mark.parametrize(
    "path", [p for p, _ in _LEAF_CASES[:1]] + [(_T, "phase_balance", "max_deviation_pct")]
)
def test_config_null_leaf_still_loads_unverified(tmp_path, path):
    cfg = load_config(_copy_edit(tmp_path, "cec_tables.yaml", _put(path, None)))
    assert not table_verified(cfg, path[1])


@pytest.mark.parametrize(
    "edit",
    [
        _put(("rule_refs", "ampacity"), ["x"]),
        _put(("rule_refs", "ampacity"), 5),
        _put(("rule_refs", "ampacity"), None),
        _put(("code_edition",), 5),
        _put(("code_edition",), ["TEST"]),
        _put(("config_version",), 1.5),
        _put(("config_version",), {"a": 1}),
        _put(("defaults", "conductor_material"), ["Cu"]),
        _put(("defaults", "voltage_v"), {"a": 1}),
        _put(("defaults", "power_factor"), True),
        _put(("defaults", "extra"), [1]),
    ],
)
def test_config_text_fields_must_be_str(tmp_path, edit):
    with pytest.raises(ConfigError):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", edit))


@pytest.mark.parametrize(
    "edit",
    [
        _put(("completeness", "placeholder_texts"), "TBD"),
        _put(("completeness", "placeholder_texts"), ["TBD", 5]),
        _put(("completeness", "spare_keywords"), "SPARE"),
        _put(("completeness", "spare_keywords"), [["SPARE"]]),
        _put(("completeness", "require_load"), "yes"),
        _put(("completeness", "require_description"), 1),
        _put(("completeness", "require_breaker"), [True]),
        _put(("completeness", "require_conductor_size"), "false"),
    ],
)
def test_config_completeness_lists_and_flags_validated(tmp_path, edit):
    with pytest.raises(ConfigError):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", edit))


_ROW_CASES = [
    ((_T, "ambient_temp_correction", "values", "75"), [None]),
    ((_T, "conductor_count_correction", "values"), [[4, 1.0], None]),
    ((_T, "standard_breaker_ratings", "values_a"), [7, None]),
    ((_T, "bonding_conductor_size", "values"), [None]),
    ((_T, "conductor_size_order", "values"), [None]),
    ((*_DF, "by_load_type", "continuous"), [None]),
    ((*_VD, "k_factor", "area_by_size", "12 AWG"), 0),
    ((*_VD, "k_factor", "area_by_size", "12 AWG"), -4),
    *[((_T, "phase_layout", "three_phase_pattern"), [x]) for x in (None, "a", "", "D", "AB")],
]


@pytest.mark.parametrize(("path", "bad"), _ROW_CASES)
def test_config_table_rows_and_pattern_validated(tmp_path, path, bad):
    with pytest.raises(ConfigError):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", _put(path, bad)))


def test_config_table_null_cells_of_a_row_still_load(tmp_path):
    edit = _put((_T, "conductor_count_correction", "values"), [[None, None]])
    assert load_config(_copy_edit(tmp_path, "cec_tables.yaml", edit))


@pytest.mark.parametrize("key", ["description", "load", "breaker", "conductor_size"])
def test_config_completeness_flag_null_raises(tmp_path, key):
    for bad in (None, "true", 1):
        edit = _put(("completeness", f"require_{key}"), bad)
        with pytest.raises(ConfigError):
            load_config(_copy_edit(tmp_path, "cec_tables.yaml", edit))


def test_skeleton_config_partial_fill_never_stops_a_rule(skeleton_cfg, cfg_set, val):
    from redline.engine import run
    from redline.model import Circuit, Confidence, Method, Panel, Project, Source
    from redline.registry import RULES

    src = Source("t.csv", "row 1", Method.CSV, Confidence.HIGH)
    c = Circuit("LP-1", "1", src, breaker_a=val(20), conductor_size=val("12 AWG"))
    c.conductor_material, c.insulation_temp_c = val("Cu"), val(75)
    c.conductors_in_raceway, c.ambient_c = val(3), val(25)
    cfg = cfg_set(skeleton_cfg, ("defaults", "termination_temp_c"), 75)  # only defaults filled
    out = run(Project("p", panels=[Panel("LP-1", src, circuits=[c])]), cfg, RULES)
    assert not out.skipped
    amp = [f for f in out.findings if f.rule_id == "ampacity"]
    assert amp and "Table entry missing" in amp[0].message


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        ((*_VD, "k_factor", "constant_by_material", "copper"), 0),
        ((*_VD, "k_factor", "phase_multiplier", "single"), 0),
        ((*_VD, "k_factor", "phase_multiplier", "three"), -1),
        ((*_VD, "impedance", "phase_multiplier", "three"), 0),
        ((*_VD, "impedance", "per_size", "copper", "12 AWG", "r"), -0.5),
        ((*_VD, "impedance", "per_size", "copper", "12 AWG", "x"), -1),
        ((*_DF, "by_load_type", "continuous"), [{"up_to_va": 5, "factor": 0}]),
    ],
)
def test_config_multipliers_must_be_positive(tmp_path, path, bad):
    with pytest.raises(ConfigError):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", _put(path, bad)))


def test_config_zero_reactance_still_loads(tmp_path):
    path = (*_VD, "impedance", "per_size", "copper", "12 AWG", "x")
    load_config(_copy_edit(tmp_path, "cec_tables.yaml", _put(path, 0)))


@pytest.mark.parametrize(
    "path, bad",
    [
        ((*_VD, "impedance", "per_size", "copper", "12 AWG", "r"), 0),
        ((*_VD, "impedance", "power_factor"), 0),
        ((*_VD, "impedance", "power_factor"), 1.5),
    ],
)
def test_config_impedance_r_and_pf_bounded(tmp_path, path, bad):
    with pytest.raises(ConfigError):
        load_config(_copy_edit(tmp_path, "cec_tables.yaml", _put(path, bad)))


def _cm(tmp_path, edit):
    return _copy_edit(tmp_path, "column_maps.yaml", edit)


def _rejects(tmp_path, edit, match):
    with pytest.raises(ConfigError, match=match):
        load_config(_cm(tmp_path, edit))


def test_column_maps_alias_list_required(tmp_path):
    for section in ("csv_panel_schedule", "panel_header_block"):
        for bad in ("ckt", ["ckt", ""], ["ckt", 3], [" "], None, {"a": "b"}):
            _rejects(
                tmp_path, lambda c, s=section, b=bad: c[s].update({"circuit_number": b}), section
            )
    _rejects(tmp_path, lambda c: c.update({"csv_panel_schedule": ["ckt"]}), "csv_panel_schedule")


def test_column_maps_extra_keys_and_shared_alias_load(tmp_path):
    def edit(c):
        c["csv_panel_schedule"]["brand_new_field"] = ["zzz"]
        c["csv_panel_schedule"]["other_field"] = c["csv_panel_schedule"]["phase"]

    assert load_config(_cm(tmp_path, edit)).column_maps["csv_panel_schedule"]["brand_new_field"]


def test_column_maps_min_header_matches_checked(tmp_path):
    for bad in (0, -1, "3", True, None, 2.5):
        _rejects(
            tmp_path,
            lambda c, b=bad: c["parsing"].update({"min_header_alias_matches": b}),
            "min_header_alias_matches",
        )


def test_column_maps_two_column_flag_bool(tmp_path):
    for bad in ("true", 1, None):
        _rejects(
            tmp_path,
            lambda c, b=bad: c["two_column_layout"].update({"detect_when_headers_repeat": b}),
            "detect_when_headers_repeat",
        )


def test_real_and_test_configs_load():
    for d in (ROOT / "config", ROOT / "tests" / "test_config"):
        assert load_config(d).column_maps["parsing"]["min_header_alias_matches"] >= 1


def _parsing(**kw):
    return lambda c: c["parsing"].update(kw)


def test_dxf_parsing_keys_checked(tmp_path):
    for key in ("dxf_extractor_timeout_s", "row_tolerance_text_heights", "column_gap_fraction"):
        for bad in (0, -1, True, "3", None, float("inf"), float("nan")):
            _rejects(tmp_path, _parsing(**{key: bad}), key)
    for bad in (0, -1, True, 2.5, "4", None):
        _rejects(tmp_path, _parsing(dxf_table_min_cells=bad), "dxf_table_min_cells")
    d = _cm(tmp_path, _parsing(dxf_table_min_cells=1, dxf_extractor_timeout_s=0.5))
    assert load_config(d).column_maps["parsing"]["dxf_table_min_cells"] == 1


def test_stale_field_policy_only_low(tmp_path):
    for bad in ("high", "Low", "medium", None, True, ""):
        _rejects(tmp_path, _parsing(dxf_stale_field_policy=bad), "dxf_stale_field_policy")
    _rejects(tmp_path, lambda c: c["parsing"].pop("dxf_stale_field_policy"), "stale_field")


def test_prefer_extractor_checked(tmp_path):
    for bad in ("acad", "ACAD_PLUGIN", None, 1, ""):
        _rejects(tmp_path, _parsing(dxf_prefer_extractor=bad), "dxf_prefer_extractor")
    d = _cm(tmp_path, _parsing(dxf_prefer_extractor="oda_ezdxf"))
    assert load_config(d).column_maps["parsing"]["dxf_prefer_extractor"] == "oda_ezdxf"


def test_extractor_paths_null_or_text(tmp_path):
    for key in ("accoreconsole_path", "acad_plugin_dll", "odafc_path"):
        for bad in ("", "  ", 3, True, ["a"]):
            _rejects(tmp_path, _parsing(**{key: bad}), key)
        _rejects(tmp_path, lambda c, k=key: c["parsing"].pop(k), key)
        d = _cm(tmp_path, _parsing(**{key: "C:/tools/x.exe"}))
        assert load_config(d).column_maps["parsing"][key] == "C:/tools/x.exe"
        assert (
            load_config(_cm(tmp_path, _parsing(**{key: None}))).column_maps["parsing"][key] is None
        )


def test_wd_m_map_shape_checked(tmp_path):
    def put(v):
        return lambda c: c["aecad_project"].update({"wd_m_attribute_map": v})

    for bad in (None, [], "x", {"a": "b"}, {"a": [""]}, {"a": [1]}, {1: ["a"]}, {"a": None}):
        _rejects(tmp_path, put(bad), "wd_m_attribute_map")
    _rejects(tmp_path, lambda c: c.pop("aecad_project"), "wd_m_attribute_map")
    assert load_config(_cm(tmp_path, put({}))).column_maps["aecad_project"]
    ok = {"sheet_number": ["SHEET", "SHEETNUM"]}
    assert (
        load_config(_cm(tmp_path, put(ok))).column_maps["aecad_project"]["wd_m_attribute_map"] == ok
    )


_PDF_POSITIVE = (
    "pdf_row_tolerance_word_heights",
    "pdf_column_gap_fraction",
    "pdf_region_gap_word_heights",
    "pdf_timeout_s",
)
_PDF_FRACTIONS = (
    "pdf_scanned_image_area_fraction",
    "pdf_title_block_width_fraction",
    "pdf_title_block_height_fraction",
)


def test_pdf_parsing_keys_checked(tmp_path):
    for key in _PDF_POSITIVE:
        for bad in (0, -1, True, "3", None, float("inf"), float("nan")):
            _rejects(tmp_path, _parsing(**{key: bad}), key)
        _rejects(tmp_path, lambda c, k=key: c["parsing"].pop(k), key)
    for key in _PDF_FRACTIONS + ("pdf_text_page_min_chars",):
        _rejects(tmp_path, lambda c, k=key: c["parsing"].pop(k), key)
    d = _cm(tmp_path, _parsing(pdf_timeout_s=0.5, pdf_column_gap_fraction=2))
    assert load_config(d).column_maps["parsing"]["pdf_timeout_s"] == 0.5


def test_pdf_fractions_in_range(tmp_path):
    for key in _PDF_FRACTIONS:
        for bad in (0, -0.1, 1.01, True, "0.5", None, float("inf"), float("nan")):
            _rejects(tmp_path, _parsing(**{key: bad}), key)
        for ok in (0.01, 1):
            d = _cm(tmp_path, _parsing(**{key: ok}))
            assert load_config(d).column_maps["parsing"][key] == ok


def test_pdf_min_chars_integer(tmp_path):
    for bad in (0, -1, 2.5, True, "200", None):
        _rejects(tmp_path, _parsing(pdf_text_page_min_chars=bad), "pdf_text_page_min_chars")
    d = _cm(tmp_path, _parsing(pdf_text_page_min_chars=1))
    assert load_config(d).column_maps["parsing"]["pdf_text_page_min_chars"] == 1


def test_pdf_timeout_upper_bound(tmp_path):
    d = _cm(tmp_path, _parsing(pdf_timeout_s=86400))
    assert load_config(d).column_maps["parsing"]["pdf_timeout_s"] == 86400
    for bad in (86401, 1e300):
        _rejects(tmp_path, _parsing(pdf_timeout_s=bad), "pdf_timeout_s")


def test_dxf_timeout_upper_bound(tmp_path):
    d = _cm(tmp_path, _parsing(dxf_extractor_timeout_s=86400))
    assert load_config(d).column_maps["parsing"]["dxf_extractor_timeout_s"] == 86400
    for bad in (86401, 1e300):
        _rejects(tmp_path, _parsing(dxf_extractor_timeout_s=bad), "dxf_extractor_timeout_s")


def test_pdf_text_page_min_chars_upper_bound(tmp_path):
    d = _cm(tmp_path, _parsing(pdf_text_page_min_chars=10000))
    assert load_config(d).column_maps["parsing"]["pdf_text_page_min_chars"] == 10000
    _rejects(tmp_path, _parsing(pdf_text_page_min_chars=10001), "pdf_text_page_min_chars")


def test_title_block_map_shape_checked(tmp_path):
    def put(v):
        return lambda c: c.update({"title_block": v})

    for bad in (None, [], "x", {"a": "b"}, {"a": [""]}, {"a": [1]}, {1: ["a"]}, {"a": None}):
        _rejects(tmp_path, put(bad), "title_block")
    _rejects(tmp_path, lambda c: c.pop("title_block"), "title_block")
    assert load_config(_cm(tmp_path, put({}))).column_maps["title_block"] == {}
    ok = {"sheet_number": ["sheet"]}
    assert load_config(_cm(tmp_path, put(ok))).column_maps["title_block"] == ok


def test_pdf_title_shape_keys_validated(tmp_path):
    for key in ("pdf_title_revision_max_chars", "pdf_title_sheet_max_chars_without_digit"):
        for bad in (True, 0, -1, 2.5, 65, "4", None):
            _rejects(tmp_path, _parsing(**{key: bad}), key)
        _rejects(tmp_path, lambda c, k=key: c["parsing"].pop(k), key)
        for ok in (1, 4, 64):
            d = _cm(tmp_path, _parsing(**{key: ok}))
            assert load_config(d).column_maps["parsing"][key] == ok


def _fa(**kw):
    return lambda c: c.update(kw)


def test_fire_alarm_shape_checked(tmp_path):
    def sec(s, **kw):
        return lambda c: c[s].update(kw)

    edits = [
        _fa(verified="yes"),
        _fa(source=None),
        _fa(config_version=1),
        _fa(device_blocks=["x"]),
        lambda c: c["device_blocks"].update(exit_sign=["TEST_EXIT", ""]),
        lambda c: c["device_blocks"].update(exit_sign="TEST_EXIT"),
        lambda c: c["device_blocks"].pop("exit_door"),
        _fa(exit_signs=None),
        sec("exit_signs", rule_ref=None),
        lambda c: c["pull_stations"].pop("max_distance_from_exit_m"),
        sec("exit_signs", require_at_each_exit="yes"),
        sec("exit_signs", max_distance_from_path_to_sign_m=0),
        sec("exit_signs", max_distance_from_path_to_sign_m=-1),
        sec("exit_signs", max_distance_from_path_to_sign_m=True),
        sec("exit_signs", max_distance_from_path_to_sign_m="10"),
        sec("exit_signs", max_distance_from_path_to_sign_m=float("inf")),
        sec("emergency_lighting", coverage_radius_m=float("nan")),
    ]
    for i, edit in enumerate(edits):
        d = tmp_path / str(i)
        d.mkdir()
        with pytest.raises(ConfigError, match="fire_alarm.yaml"):
            load_config(_copy_edit(d, "fire_alarm.yaml", edit))


def test_old_exit_sign_spacing_key_is_config_error(tmp_path):
    def edit(c):
        s = c["exit_signs"]
        s["max_spacing_along_path_m"] = s.pop("max_distance_from_path_to_sign_m")

    with pytest.raises(ConfigError, match="max_distance_from_path_to_sign_m"):
        load_config(_copy_edit(tmp_path, "fire_alarm.yaml", edit))


def test_device_name_under_two_classes(tmp_path):
    def edit(c):
        c["device_blocks"]["pull_station"] = ["SHARED"]
        c["device_blocks"]["exit_sign"] = ["SHARED"]

    with pytest.raises(ConfigError, match="two classes.*exit_sign.*pull_station"):
        load_config(_copy_edit(tmp_path, "fire_alarm.yaml", edit))


def test_device_names_trimmed_casefold(tmp_path, test_cfg):
    assert device_classes(test_cfg)["test_exit"] == "exit_sign"

    def edit(c):
        c["device_blocks"]["pull_station"] = ["Door "]
        c["device_blocks"]["exit_door"] = [" DOOR"]

    with pytest.raises(ConfigError, match="two classes"):
        load_config(_copy_edit(tmp_path, "fire_alarm.yaml", edit))


def test_fire_alarm_rule_ref_from_yaml(test_cfg, skeleton_cfg):
    cfg = replace(test_cfg, fire_alarm={**test_cfg.fire_alarm, "exit_signs": {"rule_ref": "R-X"}})
    assert rule_ref(cfg, "exit_signs") == "R-X"
    assert rule_ref(cfg, "pull_stations") == "TODO [VERIFY]"
    assert rule_ref(skeleton_cfg, "emergency_lighting") == "TODO [VERIFY]"
    gone = replace(test_cfg, fire_alarm={})
    assert rule_ref(gone, "exit_signs") == "rule_ref missing in config [VERIFY]"
    assert rule_ref(test_cfg, "ampacity") == "TEST Rule AMP-1"


def test_unverified_fire_alarm_downgrades_violation(test_cfg, skeleton_cfg):
    used = (FIRE_ALARM_TABLE,)
    assert table_verified(test_cfg, FIRE_ALARM_TABLE)
    assert apply_verification_gate([_violation()], used, test_cfg)[0].severity == Severity.VIOLATION
    for cfg in (
        skeleton_cfg,
        replace(test_cfg, fire_alarm={**test_cfg.fire_alarm, "verified": False}),
        replace(test_cfg, fire_alarm={**test_cfg.fire_alarm, "source": " "}),
    ):
        assert not table_verified(cfg, FIRE_ALARM_TABLE)
        out = apply_verification_gate([_violation()], used, cfg)
        assert out[0].severity == Severity.NEEDS_REVIEW
        assert FIRE_ALARM_TABLE in out[0].message
    # a null limit does not unverify the file: the check reports NOT_CHECKED instead
    pull = {"rule_ref": "r", "max_distance_from_exit_m": None}
    nulled = {**test_cfg.fire_alarm, "pull_stations": pull}
    assert table_verified(replace(test_cfg, fire_alarm=nulled), FIRE_ALARM_TABLE)


def test_unfilled_limit_not_checked(test_cfg, skeleton_cfg):
    for sec, keys in FIRE_ALARM_LIMITS.items():
        for k in keys:
            assert fire_alarm_limit(skeleton_cfg, sec, k) is None, (sec, k)
            assert fire_alarm_limit(test_cfg, sec, k) is not None, (sec, k)
    assert fire_alarm_limit(test_cfg, "nope", "x") is None


def test_exit_sign_distance_key_present(skeleton_cfg, test_cfg, tmp_path):
    assert "max_distance_from_exit_m" in skeleton_cfg.fire_alarm["exit_signs"]
    assert test_cfg.fire_alarm["exit_signs"]["max_distance_from_exit_m"] == 2
    with pytest.raises(ConfigError, match="exit_signs.max_distance_from_exit_m"):
        load_config(
            _copy_edit(
                tmp_path,
                "fire_alarm.yaml",
                lambda c: c["exit_signs"].pop("max_distance_from_exit_m"),
            )
        )


def test_skeleton_fire_alarm_empty_and_null(skeleton_cfg):
    fa = skeleton_cfg.fire_alarm
    assert fa["verified"] is False and fa["source"].endswith("[VERIFY]")
    assert len(fa["device_blocks"]) == 6 and not any(fa["device_blocks"].values())
    for sec, keys in FIRE_ALARM_LIMITS.items():
        assert fa[sec]["rule_ref"] == "TODO [VERIFY]"
        assert all(fa[sec][k] is None for k in keys)
    assert not table_verified(skeleton_cfg, FIRE_ALARM_TABLE)
