import re
from dataclasses import replace

from redline.engine import RunResult
from redline.model import (
    Confidence,
    Device,
    EgressPath,
    Method,
    Project,
    RunInfo,
    Source,
    Unparsed,
    Value,
)
from redline.report.html import SECTION_IDS, render_html

SHEET = "sheet_fa101.dxf"


def _src(conf=Confidence.HIGH, **kw):
    return Source(SHEET, "blocks", Method.DXF_BLOCK, conf, **kw)


def _dev(cls, detection="block", sheet=SHEET, location="Model", conf=Confidence.HIGH):
    s = _src(conf)
    return Device(
        cls,
        s,
        sheet=Value(sheet, s),
        location=Value(location, s),
        x=Value(1.0, s),
        y=Value(2.0, s),
        detection=detection,
    )


def _block(name, placed=1, nested=0, file=SHEET):
    why = (
        "block name matches no device class in fire_alarm.yaml device_blocks: "
        f"{placed} placed, {nested} inside block definitions or xrefs"
    )
    return Unparsed("block", name, why, Source(file, "blocks", Method.DXF_BLOCK, Confidence.LOW))


def _project(**kw):
    return Project(
        name="Plans",
        run_info=RunInfo("0.0.1"),
        **kw,
    )


def _html(project, cfg):
    return render_html(project, RunResult((), (), (), {}), cfg)


def _section(html, sid):
    start = html.index(f'id="{sid}"')
    m = re.search(r'<section id="', html[start + 1 :])
    return html[start : start + 1 + m.start()] if m else html[start:]


def _plan():
    mm = Value("mm", Source(SHEET, "document.units", Method.DXF_BLOCK, Confidence.MEDIUM), raw="mm")
    devs = [
        _dev("exit_sign"),
        _dev("exit_sign"),
        _dev("pull_station", "paper", location="FA-101"),
        _dev("horn_strobe", "nested", location="FA_CLUSTER", conf=Confidence.LOW),
        _dev("exit_door", "list"),
        _dev("exit_door", "unused"),
    ]
    low = Source("paths.csv", "path P2", Method.CSV, Confidence.LOW)
    paths = [
        EgressPath("P1", SHEET, Source("paths.csv", "path P1", Method.CSV, Confidence.HIGH)),
        EgressPath("P2", SHEET, low),
    ]
    return _project(
        devices=devs,
        paths=paths,
        sheet_units={SHEET: mm},
        unparsed=[_block("CHAIR", 2), _block("FA_CLUSTER", 1)],
    )


def test_report_devices_section(test_cfg):
    html = _html(_plan(), test_cfg)
    assert SECTION_IDS.index("devices") == SECTION_IDS.index("manual-check") + 1
    assert 'id="devices"' in html
    assert "Devices and exits" in _section(html, "devices")
    assert (
        html.index('id="manual-check"') < html.index('id="devices"') < html.index('id="coverage"')
    )


def test_devices_section_counts_per_class(test_cfg):
    sec = _section(_html(_plan(), test_cfg), "devices")
    rows = {
        m.group(1): re.findall(r"<td>(.*?)</td>", m.group(2))
        for m in re.finditer(r'<tr class="cls"><td>(\w+)</td>(.*?)</tr>', sec)
    }
    # block, list, unused, nested, paper, detector
    assert rows["exit_sign"] == ["2", "0", "0", "0", "0", "0"]
    assert rows["exit_door"] == ["0", "1", "1", "0", "0", "0"]
    assert rows["horn_strobe"] == ["0", "0", "0", "1", "0", "0"]
    assert rows["pull_station"] == ["0", "0", "0", "0", "1 in FA-101", "0"]
    assert set(rows) >= {"emergency_light", "smoke_detector"}
    assert rows["smoke_detector"] == ["0"] * 6


def test_devices_section_unmatched_names_with_counts(test_cfg):
    sec = _section(_html(_plan(), test_cfg), "devices")
    assert re.search(r"<td>CHAIR</td><td>sheet_fa101.dxf</td><td>2</td><td>0</td>", sec)
    assert re.search(r"<td>FA_CLUSTER</td><td>sheet_fa101.dxf</td><td>1</td><td>0</td>", sec)


def test_devices_section_units_named(test_cfg):
    sec = _section(_html(_plan(), test_cfg), "devices")
    assert "Units: mm" in sec
    assert "document.units" in sec
    # exits listed and paths, with the LOW path named
    assert "Exits listed in exits.csv: 1" in sec
    assert "Paths: 2" in sec
    assert "LOW: P2" in sec


def test_devices_section_units_differ_names_both(test_cfg):
    src = Source("exits.csv", "units", Method.CSV, Confidence.HIGH, "the drawing states unitless")
    p = _plan()
    p.sheet_units[SHEET] = Value("m", src, raw="m")
    sec = _section(_html(p, test_cfg), "devices")
    assert "Units: m" in sec
    assert "the drawing states unitless" in sec


def test_devices_section_units_not_usable(test_cfg):
    p = _plan()
    p.sheet_units[SHEET] = Value(
        None, Source(SHEET, "document.units", Method.DXF_BLOCK, Confidence.LOW), raw="unitless"
    )
    sec = _section(_html(p, test_cfg), "devices")
    assert "Units: not usable" in sec
    assert "unitless" in sec


def test_devices_section_no_plan_input_line(test_cfg):
    sec = _section(_html(_project(), test_cfg), "devices")
    assert "No plan sheet, exits.csv or paths.csv was read." in sec
    assert "No plan sheet, exits.csv or paths.csv was read." not in _section(
        _html(_plan(), test_cfg), "devices"
    )


def test_manual_check_points_to_unmatched_names(test_cfg):
    p = _plan()
    p.unparsed.append(Unparsed("column", "Foo", "Column not mapped.", _src()))
    man = _section(_html(p, test_cfg), "manual-check")
    assert "2 block names match no device class; listed under Devices and exits" in man
    assert "CHAIR" not in man
    assert "column: Foo" in man


def test_devices_unmatched_names_cut_per_file(test_cfg):
    names = [f"N{i:04d}" for i in range(520)]
    other = [_block("OTHERFILE", 1, 0, file="sheet_fa102.dxf")]
    p = _project(unparsed=[_block(n) for n in names] + other)
    html = _html(p, test_cfg)
    sec = _section(html, "devices")
    assert "<td>N0499</td>" in sec
    assert "<td>N0500</td>" not in sec
    assert "and 20 more block names in sheet_fa101.dxf" in sec
    assert "<td>OTHERFILE</td>" in sec
    man = _section(html, "manual-check")
    assert (
        "520 block names match no device class; listed under Devices and exits (20 not shown)"
        in man
    )
    assert "1 block names match no device class; listed under Devices and exits" in man


def test_fire_alarm_yaml_in_config_tables(test_cfg, skeleton_cfg):
    ok = _section(_html(_project(), test_cfg), "config-tables")
    assert re.search(r"<td>fire_alarm.yaml</td><td>VERIFIED</td><td>TEST ONLY", ok)
    bad = _section(_html(_project(), skeleton_cfg), "config-tables")
    assert re.search(r"<td>fire_alarm.yaml</td><td>NOT VERIFIED</td>", bad)


def test_devices_html_escapes_block_name(test_cfg):
    sec = _section(_html(_project(unparsed=[_block("<b>x</b>")]), test_cfg), "devices")
    assert "<b>x</b>" not in sec
    assert "&lt;b&gt;x&lt;/b&gt;" in sec


def test_devices_section_missing_sheet_value_kept(test_cfg):
    d = replace(_dev("exit_sign"), sheet=Value.missing())
    sec = _section(_html(_project(devices=[d]), test_cfg), "devices")
    assert "No plan sheet, exits.csv or paths.csv was read." not in sec


def test_exits_label_names_the_list(test_cfg):
    html = _html(_plan(), test_cfg)
    assert "Exits listed in exits.csv: 1" in _section(html, "devices")
    assert "Exits checked" not in html


def test_block_counts_round_trip():
    from redline.parsers import dxf

    assert dxf.read_block_counts(dxf.block_counts_text(7, 3)) == (7, 3)
    assert dxf.read_block_counts("x " + dxf.block_counts_text(0, 12) + " y") == (0, 12)
    assert dxf.read_block_counts("block name matches no device class") is None
