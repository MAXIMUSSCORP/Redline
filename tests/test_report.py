import csv
import re

from redline.engine import RunResult
from redline.findings import Finding, InputUsed, Severity
from redline.model import (
    Confidence,
    CoverageEntry,
    Method,
    Project,
    RunInfo,
    Source,
    Unparsed,
)
from redline.report.csv_out import CSV_COLUMNS, format_inputs, write_findings_csv
from redline.report.html import LIABILITY_SENTENCE, SECTION_IDS, render_html


def _src(conf=Confidence.HIGH, **kw):
    return Source("panels.csv", "row 7", Method.CSV, conf, **kw)


def _project(**kw):
    return Project(
        name="Sample",
        unparsed=[Unparsed("column", "Foo", "Column not mapped.", _src())],
        coverage=[CoverageEntry("panels.csv", "LP-1", "20 circuits", "csv", "HIGH 20")],
        run_info=RunInfo("0.0.1", extractor_versions={}, model_ids_versions_hashes=[]),
        **kw,
    )


def _findings():
    mid = InputUsed("length_m", "30", "row 7", Confidence.MEDIUM, "model-x")
    return (
        Finding(
            "ampacity", Severity.VIOLATION, "LP-1 ckt 7: too small.", "R1", _src(), (mid,), "Fix."
        ),
        Finding("ampacity", Severity.NEEDS_REVIEW, "LP-1 ckt 8: input low.", "R1", _src(), (), ""),
        Finding("bonding", Severity.INFO, "LP-1: noted.", "R2", None),
        Finding("voltage_drop", Severity.NOT_CHECKED, "Voltage drop did not run: boom.", "", None),
    )


def _result(findings=None, unverified=None):
    return RunResult(
        tuple(findings if findings is not None else _findings()),
        ("ampacity", "bonding"),
        (("voltage_drop", "boom"),),
        unverified or {},
    )


def _section(html, sid):
    start = html.index(f'id="{sid}"')
    m = re.search(r'<section id="', html[start:])
    return html[start : start + m.start()] if m else html[start:]


def test_report_has_manual_check_and_coverage(test_cfg):
    html = render_html(_project(), _result(), test_cfg)
    ids = [s for s in SECTION_IDS if f'id="{s}"' in html]
    assert ids == list(SECTION_IDS)
    manual = _section(html, "manual-check")
    assert "Foo" in manual and "LP-1 ckt 8" in manual and "did not run" in manual
    cov = _section(html, "coverage")
    assert "<table>" in cov and "20 circuits" in cov


def test_report_footer_liability_sentence(test_cfg):
    html = render_html(_project(), _result(), test_cfg)
    assert LIABILITY_SENTENCE in _section(html, "footer")
    assert html.rstrip().endswith("</html>")
    assert "never counted as passing" in _section(html, "footer")


def test_report_test_config_banner(test_cfg, skeleton_cfg):
    assert "TEST EDITION, NOT CEC" in _section(
        render_html(_project(), _result(), test_cfg), "banner"
    )
    assert 'id="banner"' not in render_html(_project(), _result(), skeleton_cfg)


def test_report_warns_unverified_tables(skeleton_cfg, test_cfg, cfg_unverify):
    html = render_html(
        _project(), _result(unverified={"ampacity": ("conductor_ampacity",)}), skeleton_cfg
    )
    rules = _section(html, "rules")
    assert "Unverified tables:" in rules and "conductor_ampacity" in rules
    assert "NOT VERIFIED" in _section(html, "config-tables")
    cfg = cfg_unverify(test_cfg, "conductor_ampacity")
    assert "NOT VERIFIED" in _section(render_html(_project(), _result(), cfg), "config-tables")
    assert "Unverified tables:" not in _section(
        render_html(_project(), _result(), test_cfg), "rules"
    )


def test_report_self_contained(test_cfg):
    html = render_html(_project(), _result(), test_cfg).lower()
    for bad in ("<script", "<link", "http://", "https://"):
        assert bad not in html


def test_report_escapes_input_text(test_cfg):
    evil = Finding("ampacity", Severity.INFO, "<script>alert(1)</script>", "R", _src())
    html = render_html(_project(), _result([evil]), test_cfg)
    assert "<script" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_report_voice(test_cfg, skeleton_cfg):
    for cfg in (test_cfg, skeleton_cfg):
        html = render_html(_project(), _result(), cfg)
        assert "!" not in html.replace("<!doctype html>", "")
        assert not re.search(r"\b(compliant|approved)\b", html, re.IGNORECASE)
        assert "%" not in html.split("</style>")[1]
        for f in _findings():
            row = next(r for r in html.split("<tr") if f.message in r)
            assert f.severity.value in row
    html = render_html(_project(), _result(), test_cfg)
    assert "Rests on MEDIUM input: length_m. Model: model-x." in html
    assert "—" in html


def test_report_edition_verified_only_when_true(test_cfg, cfg_set):
    ok = _section(render_html(_project(), _result(), test_cfg), "config-tables")
    assert "NOT VERIFIED" not in ok
    for bad in ("false", 1):
        cfg = cfg_set(test_cfg, ("code_edition_verified",), bad)
        html = render_html(_project(), _result(), cfg)
        assert "Code edition: TEST EDITION, NOT CEC · NOT VERIFIED" in html, bad
        assert "The code edition is also unverified" in html, bad


def test_csv_non_string_cell_written(tmp_path):
    f = Finding("r", Severity.INFO, "m", 7, Source(5, "row 1", Method.CSV, Confidence.HIGH))
    out = tmp_path / "f.csv"
    write_findings_csv([f], out)
    row = list(csv.reader(out.open(newline="", encoding="utf-8")))[1]
    assert row[2] == "7" and row[3] == "5"


def test_csv_formula_guard_leading_whitespace(tmp_path):
    cells = [" =HYPERLINK(1)", "\xa0=2+3", "\n=1+1", "  -1", "ok =x"]
    fs = [Finding("r", Severity.INFO, c, "", None) for c in cells]
    out = tmp_path / "f.csv"
    write_findings_csv(fs, out)
    got = [r[5] for r in list(csv.reader(out.open(newline="", encoding="utf-8")))[1:]]
    assert got == ["'" + c for c in cells[:4]] + ["ok =x"]


def test_csv_formula_cells_escaped(tmp_path):
    cells = ["=1+1", "+1", "-1", "@x", "\tx", "\rx", "-", "plain"]
    fs = [Finding("r", Severity.INFO, c, "", None, suggested_fix=c) for c in cells]
    fs.append(
        Finding(
            "r", Severity.INFO, "m", "", _src(), (InputUsed("a", "1", "row 7", Confidence.LOW),)
        )
    )
    out = tmp_path / "f.csv"
    write_findings_csv(fs, out)
    rows = list(csv.reader(out.open(newline="", encoding="utf-8")))
    assert tuple(rows[0]) == CSV_COLUMNS
    got = [r[5] for r in rows[1:-1]]
    assert got == ["'=1+1", "'+1", "'-1", "'@x", "'\tx", "'\rx", "-", "plain"]
    assert rows[-1][7] == "a=1 @ row 7 (LOW)"
    assert rows[-1][3:5] == ["panels.csv", "row 7"]


def test_csv_empty_cell_written_empty(tmp_path):
    f = Finding("r", Severity.INFO, "m", "", None)
    out = tmp_path / "f.csv"
    write_findings_csv([f], out)
    row = list(csv.reader(out.open(newline="", encoding="utf-8")))[1]
    assert row[2] == "" and row[3] == "" and row[4] == ""


def test_inputs_used_text_shows_missing():
    f = Finding(
        "r", Severity.NEEDS_REVIEW, "m", "R", None, (InputUsed("x", "1", "l", Confidence.MISSING),)
    )
    assert "(MISSING)" in format_inputs(f)
