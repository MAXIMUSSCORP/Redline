import copy
from dataclasses import replace

from redline.config import rule_ref
from redline.engine import run
from redline.findings import Severity
from redline.model import Confidence, Device, EgressPath, Method, Project, Source, Value
from redline.rules.fire_alarm import SPEC

S = "sheet_a.dxf"
ES_A = "(Exit signs at exits)"
ES_B = "(Exit sign spacing along paths)"
PS = "(Fire alarm pull stations)"
EL = "(Emergency lighting)"
NO_PLAN = (
    "Exit signs: not checked. No exit or egress path was read from a plan sheet, exits.csv or paths.csv.",
    "Fire alarm pull stations: not checked. No exit was read from a plan sheet or exits.csv.",
    "Emergency lighting: not checked. No egress path was read from paths.csv.",
)
SECTIONS = ("exit_signs", "pull_stations", "emergency_lighting")
LINE = [(0.0, 0.0), (30.0, 0.0)]


def _src(conf=Confidence.HIGH, method=Method.DXF_BLOCK):
    return Source(S, "h1", method, conf)


def _dev(cls, x, y, det="block", conf=Confidence.HIGH, method=Method.DXF_BLOCK, tag="E1"):
    s = _src(conf, method)
    return Device(
        cls,
        s,
        tag=Value(tag, s),
        sheet=Value(S, s),
        x=Value(x, s) if x is not None else Value.missing(),
        y=Value(y, s) if y is not None else Value.missing(),
        detection=det,
    )


def _path(points, name="P1", conf=Confidence.HIGH, method=Method.CSV):
    return EgressPath(name, S, Source("paths.csv", "rows 2-3", method, conf), points)


def _units(word="m", note="declared in the drawing header", conf=Confidence.MEDIUM):
    return {S: Value(word, Source(S, "document.units", Method.DXF_BLOCK, conf, note))}


def _proj(devices=(), paths=(), units=None):
    units = _units() if units is None else units
    return Project("p", devices=list(devices), paths=list(paths), sheet_units=units)


def _cfg(cfg, section=None, key=None, value=None, **top):
    fa = copy.deepcopy(cfg.fire_alarm)
    if section:
        fa[section][key] = value
    fa.update(top)
    return replace(cfg, fire_alarm=fa)


def _got(project, cfg, label=None, text=None):
    out = run(project, cfg, [SPEC]).findings
    keep = [label, text]
    return [f for f in out if all(k in f.message for k in keep if k)]


def _one(project, cfg, label=None, text=None):
    out = _got(project, cfg, label, text)
    assert len(out) == 1, [f.message for f in out]
    return out[0]


def _exit(x=0.0, y=0.0, tag="E1", **kw):
    return _dev("exit_door", x, y, tag=tag, **kw)


def _lights(*xs):
    return [_dev("emergency_light", x, 0.0, tag=f"L{x}") for x in xs]


# exit signs at exits


def test_exit_signs_trigger(test_cfg):
    f = _one(_proj([_exit(), _dev("exit_sign", 3.0, 0.0)]), test_cfg, ES_A)
    assert f.severity == Severity.VIOLATION
    assert "3.0 m" in f.message and "2 m limit" in f.message and "exit E1" in f.message
    assert f.message.endswith(rule_ref(test_cfg, "exit_signs"))


def test_exit_signs_pass(test_cfg):
    assert not _got(_proj([_exit(), _dev("exit_sign", 1.0, 0.0)]), test_cfg, ES_A)


def test_exit_signs_missing_input(test_cfg):
    f = _one(_proj([_exit(x=None)]), test_cfg, ES_A)
    assert f.severity == Severity.NEEDS_REVIEW and "Input not usable" in f.message


def test_exit_signs_unfilled_limit(test_cfg):
    cfg = _cfg(test_cfg, "exit_signs", "max_distance_from_exit_m", None)
    f = _one(_proj([_exit()]), cfg, text="Exit signs: not checked")
    assert f.severity == Severity.NOT_CHECKED
    assert "exit_signs.max_distance_from_exit_m" in f.message and "[VERIFY]" in f.message
    assert not _got(_proj([_exit()]), cfg, ES_A)


# pull stations


def test_pull_stations_trigger(test_cfg):
    f = _one(_proj([_exit(), _dev("pull_station", 6.0, 0.0)]), test_cfg, PS)
    assert f.severity == Severity.VIOLATION and "6.0 m" in f.message and "5 m limit" in f.message


def test_pull_stations_pass(test_cfg):
    assert not _got(_proj([_exit(), _dev("pull_station", 4.0, 0.0)]), test_cfg, PS)


def test_pull_stations_missing_input(test_cfg):
    f = _one(_proj([_exit(y=None)]), test_cfg, PS)
    assert f.severity == Severity.NEEDS_REVIEW and "Input not usable" in f.message


def test_pull_stations_unfilled_limit(test_cfg):
    cfg = _cfg(test_cfg, "pull_stations", "max_distance_from_exit_m", None)
    f = _one(_proj([_exit()]), cfg, text="Fire alarm pull stations: not checked")
    assert f.severity == Severity.NOT_CHECKED
    assert "pull_stations.max_distance_from_exit_m" in f.message
    assert not _got(_proj([_exit()]), cfg, PS)


# emergency lighting


def test_emergency_lighting_trigger(test_cfg):
    f = _one(_proj(_lights(5.0, 25.0), [_path(LINE)]), test_cfg, EL)
    assert f.severity == Severity.VIOLATION
    assert "10.0 m" in f.message and "2 m gap limit" in f.message and "path P1" in f.message


def test_emergency_lighting_pass(test_cfg):
    assert not _got(_proj(_lights(5.0, 15.0, 25.0), [_path(LINE)]), test_cfg, EL)


def test_emergency_lighting_missing_input(test_cfg):
    f = _one(_proj(_lights(5.0), [_path(LINE, conf=Confidence.LOW)]), test_cfg, EL)
    assert f.severity == Severity.NEEDS_REVIEW and "Input not usable" in f.message


def test_emergency_lighting_unfilled_limit(test_cfg):
    cfg = _cfg(test_cfg, "emergency_lighting", "coverage_radius_m", None)
    f = _one(_proj(_lights(5.0), [_path(LINE)]), cfg, text="Emergency lighting: not checked")
    assert f.severity == Severity.NOT_CHECKED
    assert "emergency_lighting.coverage_radius_m" in f.message
    assert not _got(_proj(_lights(5.0), [_path(LINE)]), cfg, EL)


# rule behaviours


def test_sign_spacing_gap_triggers(test_cfg):
    path = [(0.0, 0.0), (40.0, 0.0)]
    f = _one(_proj([_dev("exit_sign", 10.0, 0.0)], [_path(path)]), test_cfg, ES_B)
    assert f.severity == Severity.VIOLATION and "20.0 m" in f.message and "10 m of any" in f.message


def test_sign_spacing_no_path_says_so(test_cfg):
    f = _one(_proj([_exit()]), test_cfg, text="Exit sign spacing along paths not checked")
    assert f.severity == Severity.NOT_CHECKED
    assert "No egress path was read for this sheet" in f.message


def test_touching_coverage_is_not_a_gap(test_cfg):
    path = [(0.0, 0.0), (40.0, 0.0)]
    signs = [_dev("exit_sign", 10.0, 0.0, tag="A"), _dev("exit_sign", 30.0, 0.0, tag="B")]
    assert not _got(_proj(signs, [_path(path)]), test_cfg, ES_B)


def test_sign_at_exit_not_required_not_checked(test_cfg):
    cfg = _cfg(test_cfg, "exit_signs", "require_at_each_exit", False)
    f = _one(_proj([_exit()]), cfg, text="Exit signs: not checked")
    assert "exit_signs.require_at_each_exit is false" in f.message
    assert not _got(_proj([_exit()]), cfg, ES_A)


def test_units_not_stated_not_checked(test_cfg):
    gone = {S: Value(None, Source(S, "u", Method.DXF_BLOCK, Confidence.LOW))}
    f = _one(_proj([_exit()], units=gone), test_cfg, text="Exit signs at exits not checked")
    assert f.severity == Severity.NOT_CHECKED and "Drawing units not stated" in f.message


def test_owner_units_named_with_drawing_units(test_cfg):
    units = _units("ft", "the drawing states mm", Confidence.HIGH)
    f = _one(_proj([_exit(), _dev("exit_sign", 10.0, 0.0)], units=units), test_cfg, ES_A)
    assert f.severity == Severity.VIOLATION and "3.0 m" in f.message
    assert "units ft" in f.message and "the drawing states mm" in f.message


def test_contradicted_units_rest_on_medium(test_cfg):
    units = _units("ft", "the drawing states mm", Confidence.MEDIUM)
    f = _one(_proj([_exit(), _dev("exit_sign", 10.0, 0.0)], units=units), test_cfg, ES_A)
    assert f.severity == Severity.VIOLATION
    assert "units ft" in f.message and "the drawing states mm" in f.message
    (u,) = [i for i in f.inputs_used if i.field == "units"]
    assert u.value == "ft" and u.confidence == Confidence.MEDIUM


def test_nested_device_gives_review_not_violation(test_cfg):
    nested = _dev("exit_sign", None, None, det="nested", conf=Confidence.LOW)
    f = _one(_proj([_exit(), nested]), test_cfg, ES_A)
    assert f.severity == Severity.NEEDS_REVIEW and "nested or detector-derived" in f.message


def test_paper_space_device_not_used(test_cfg):
    f = _one(_proj([_exit(), _dev("exit_sign", 1.0, 0.0, det="paper")]), test_cfg, ES_A)
    assert (
        f.severity == Severity.NEEDS_REVIEW
        and "no exit sign block placed in model space was matched" in f.message
    )


def test_unused_exit_doors_not_checked(test_cfg):
    f = _one(
        _proj([_exit(det="unused"), _dev("exit_sign", 1.0, 0.0)]),
        test_cfg,
        text="Exit signs at exits not checked",
    )
    assert f.severity == Severity.NOT_CHECKED and "No exit was read for this sheet" in f.message


def test_rule_refs_from_fire_alarm_yaml(test_cfg):
    cfg = test_cfg
    for sec in SECTIONS:
        cfg = _cfg(cfg, sec, "rule_ref", f"REF-{sec}")
    out = run(_proj([_exit()], [_path(LINE)]), cfg, [SPEC]).findings
    viol = [f for f in out if f.severity == Severity.NEEDS_REVIEW]
    assert {f.rule_ref for f in viol} == {f"REF-{s}" for s in SECTIONS}
    assert all(f.message.endswith(f.rule_ref) for f in viol)


def test_unverified_fire_alarm_gives_review(test_cfg):
    cfg = _cfg(test_cfg, verified=False)
    f = _one(_proj([_exit(), _dev("exit_sign", 3.0, 0.0)]), cfg, ES_A)
    assert f.severity == Severity.NEEDS_REVIEW and "Downgraded from VIOLATION" in f.message


def test_one_bad_exit_does_not_stop_others(test_cfg):
    devs = [_exit(x="abc", tag="BAD"), _exit(x=50.0, tag="GOOD"), _dev("exit_sign", 100.0, 0.0)]
    out = _got(_proj(devs), test_cfg)
    by_tag = {
        k: f
        for f in out
        for k in ("BAD", "GOOD")
        if k in f.message and "Fire alarm" not in f.message
    }
    assert "could not be checked" in by_tag["BAD"].message
    assert by_tag["GOOD"].severity == Severity.VIOLATION


def test_no_plan_input_three_rows(test_cfg):
    out = run(Project("p"), test_cfg, [SPEC]).findings
    assert tuple(f.message for f in out) == NO_PLAN


def test_rule_fire_alarm_three_not_checked(test_cfg):
    out = run(Project("empty"), test_cfg, [SPEC]).findings
    assert [f.severity for f in out] == [Severity.NOT_CHECKED] * 3
    assert [f.rule_ref for f in out] == [rule_ref(test_cfg, s) for s in SECTIONS]
    assert all(f.suggested_fix and f.rule_id == "fire_alarm" for f in out)


def test_detector_inputs_never_violation(test_cfg):
    det, mid = Method.DETECTOR, Confidence.MEDIUM
    devs = [
        _exit(det="detector", method=det, conf=mid),
        _exit(tag="E2"),
        _dev("exit_sign", 50.0, 0.0, det="detector", method=det, conf=mid),
        _dev("pull_station", 50.0, 0.0, method=det, conf=mid),
        _dev("emergency_light", 50.0, 0.0, method=det, conf=mid),
    ]
    paths = [_path(LINE, method=det, conf=mid), _path(LINE, name="P2")]
    out = run(_proj(devs, paths), test_cfg, [SPEC]).findings
    assert not [f for f in out if f.severity == Severity.VIOLATION], [f.message for f in out]
    assert [f for f in out if f.severity == Severity.NEEDS_REVIEW]


def test_rule_fire_alarm_low_input(test_cfg):
    low = Confidence.LOW
    devs = [
        _exit(conf=low),
        _dev("exit_sign", 0.0, 0.0, conf=low),
        _dev("pull_station", 0.0, 0.0, conf=low),
    ]
    out = run(_proj(devs, [_path(LINE, conf=low)]), test_cfg, [SPEC]).findings
    assert not [f for f in out if f.severity == Severity.VIOLATION]
    reviews = [f.message for f in out if f.severity == Severity.NEEDS_REVIEW]
    assert any("exit E1" in m and "Input not usable" in m for m in reviews)
    assert any("path P1" in m and "Input not usable" in m for m in reviews)


def test_empty_device_class_not_checked(test_cfg):
    fa = copy.deepcopy(test_cfg.fire_alarm)
    fa["device_blocks"]["pull_station"] = []
    cfg = replace(test_cfg, fire_alarm=fa)
    f = _one(_proj([_exit()]), cfg, text="Fire alarm pull stations: not checked")
    assert f.severity == Severity.NOT_CHECKED
    assert "device_blocks" in f.message and "pull_station" in f.message
    assert not _got(_proj([_exit()]), cfg, PS + " no")
    assert len(_got(_proj([_exit()]), cfg, "Fire alarm pull stations")) == 1


def test_no_matched_device_is_review(test_cfg):
    f = _one(_proj([_exit()]), test_cfg, ES_A)
    assert f.severity == Severity.NEEDS_REVIEW and "placed in model space was matched" in f.message
    path = [(0.0, 0.0), (40.0, 0.0)]
    f = _one(_proj([], [_path(path)]), test_cfg, EL)
    assert f.severity == Severity.NEEDS_REVIEW and "No emergency light block" in f.message


def test_matched_device_over_limit_still_violation(test_cfg):
    f = _one(_proj([_exit(), _dev("exit_sign", 9.0, 0.0)]), test_cfg, ES_A)
    assert f.severity == Severity.VIOLATION
    f = _one(
        _proj([_dev("emergency_light", 1.0, 0.0)], [_path([(0.0, 0.0), (40.0, 0.0)])]), test_cfg, EL
    )
    assert f.severity == Severity.VIOLATION


def test_distance_at_limit_passes(test_cfg):
    units = _units("mm")
    p = _proj([_exit(), _dev("exit_sign", 2300.0, 0.0)], units=units)
    cfg = _cfg(test_cfg, "exit_signs", "max_distance_from_exit_m", 2.3)
    assert not _got(p, cfg, ES_A)


def test_gap_at_limit_passes(test_cfg):
    from redline.rules.fire_alarm import _gaps

    # 2300 mm is 2300 * 0.001 m, which is 2.3000000000000003 m in floats
    assert not _gaps([(0.0, 0.0), (2300 * 0.001, 0.0)], [], 0.0, 2.3)


def test_nested_only_message_names_model_space(test_cfg):
    nested = _dev("exit_sign", None, None, det="nested", conf=Confidence.LOW)
    f = _one(_proj([_exit(), nested]), test_cfg, ES_A)
    assert f.severity == Severity.NEEDS_REVIEW and "placed in model space" in f.message


def test_pair_cap_not_checked(test_cfg):
    import time

    devs = [_dev("exit_sign", float(i), 1.0, tag=f"D{i}") for i in range(20000)]
    path = _path([(float(i), 0.0) for i in range(2000)])
    t = time.perf_counter()
    out = _got(_proj(devs, [path]), test_cfg, text="Exit sign spacing along paths")
    assert time.perf_counter() - t < 5
    assert len(out) == 1 and out[0].severity == Severity.NOT_CHECKED
    assert "design cap" in out[0].message


def test_gaps_memory_per_segment():
    import tracemalloc

    from redline.rules.fire_alarm import _gaps

    pts = [(float(i), 0.0) for i in range(1001)]
    devs = [(500.0, 0.0)] * 1000
    tracemalloc.start()
    _gaps(pts, devs, 2000.0, 1.0)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert peak < 10_000_000


def _two_sheets():
    """Two sheets, each one exit and one sign: 1 x 1 pair for each exit check."""
    out = []
    for name in ("sheet_a.dxf", "sheet_b.dxf"):
        s = Source(name, "h1", Method.DXF_BLOCK, Confidence.HIGH)
        for cls, tag in (("exit_door", "E1"), ("exit_sign", "D1")):
            out.append(
                Device(
                    cls,
                    s,
                    tag=Value(tag, s),
                    sheet=Value(name, s),
                    x=Value(0.0, s),
                    y=Value(0.0, s),
                    detection="block",
                )
            )
    units = {
        n: Value("m", Source(n, "document.units", Method.DXF_BLOCK, Confidence.MEDIUM))
        for n in ("sheet_a.dxf", "sheet_b.dxf")
    }
    return Project("p", devices=out, sheet_units=units)


RUN_REASON = "would pass the run's limit of pair comparisons; check by hand"


def test_run_wide_pair_limit_not_checked(test_cfg, monkeypatch):
    import redline.rules.fire_alarm as fa

    monkeypatch.setattr(fa, "MAX_FIRE_ALARM_RUN_PAIRS", 1)
    out = _got(_two_sheets(), test_cfg, text="Exit signs at exits")
    late = [f for f in out if RUN_REASON in f.message]
    assert [f.severity for f in late] == [Severity.NOT_CHECKED]
    assert "sheet_b.dxf" in late[0].message
    assert not any(RUN_REASON in f.message for f in out if "sheet_a.dxf" in f.message)


def test_run_wide_limit_same_on_repeat(test_cfg, monkeypatch):
    import redline.rules.fire_alarm as fa

    monkeypatch.setattr(fa, "MAX_FIRE_ALARM_RUN_PAIRS", 1)
    first = [f.message for f in _got(_two_sheets(), test_cfg)]
    assert [f.message for f in _got(_two_sheets(), test_cfg)] == first
    assert any(RUN_REASON in m for m in first)


def test_run_limit_is_ten_part_caps():
    from redline.config import MAX_FIRE_ALARM_PAIRS, MAX_FIRE_ALARM_RUN_PAIRS

    assert MAX_FIRE_ALARM_RUN_PAIRS == 10 * MAX_FIRE_ALARM_PAIRS
