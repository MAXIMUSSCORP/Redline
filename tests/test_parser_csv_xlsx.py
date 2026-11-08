import copy
import re
import zipfile
from pathlib import Path

import openpyxl
import pytest
from test_parser_tabular import M0_SCHEDULE, cfg_with

from redline.model import Confidence
from redline.parsers.csv_xlsx import MAX_SHEETS, SUFFIXES, InputError, parse_file

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "csv"
HEADER = [
    "Panel",
    "Ckt",
    "Description",
    "Load (VA)",
    "Load Type",
    "Poles",
    "Phase",
    "Breaker",
    "Wire Sz.",
    "Material",
    "Insulation",
    "Conductors in Raceway",
    "Length",
    "Voltage",
    "Notes",
]


@pytest.fixture
def cfg(test_cfg):
    return cfg_with(test_cfg)


def write(tmp_path, name, content, encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(content.encode(encoding) if isinstance(content, str) else content)
    return path


def workbook(tmp_path, sheets, name="book.xlsx"):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    path = tmp_path / name
    wb.save(path)
    return path


def test_suffixes():
    assert SUFFIXES == (".csv", ".txt", ".xlsx")


def test_two_panels_counts(test_cfg):
    parsed = parse_file(SAMPLES / "two_panels.csv", test_cfg)
    assert [(p.name, len(p.circuits)) for p in parsed.panels] == [("LP-1", 20), ("LP-2", 20)]
    (total,) = [u for u in parsed.unparsed if u.kind == "row"]
    assert "TOTAL" in total.raw
    assert total.reason == "no circuit number"
    assert total.source.locator == "row=42"
    assert [c.unit for c in parsed.coverage] == ["LP-1", "LP-2"]
    assert all("encoding utf-8" in c.what_read for c in parsed.coverage)
    lp1 = {c.number: c for c in parsed.panels[0].circuits}
    assert lp1["3"].description.confidence is Confidence.MISSING
    assert lp1["5"].load_va.confidence is Confidence.LOW
    assert lp1["7"].conductor_size.confidence is Confidence.LOW
    assert lp1["19"].is_spare and lp1["19"].load_va.confidence is Confidence.MISSING
    assert lp1["20"].is_spare and lp1["20"].load_va.value == 1200.0
    lp2 = {c.number: c for c in parsed.panels[1].circuits}
    assert lp2["4"].length_m.confidence is Confidence.LOW
    assert lp2["20"].is_spare


def test_odd_header_medium_or_unparsed(test_cfg):
    path = SAMPLES / "two_panels.csv"
    # The shipped map may gain aliases, so this checks the lowest confidence it can give.
    sizes = [c.conductor_size for c in parse_file(path, test_cfg).panels[0].circuits]
    assert all(v.confidence >= Confidence.MEDIUM or v.raw in ("12", "") for v in sizes)
    cfg = cfg_with(test_cfg)
    sizes = [c.conductor_size for c in parse_file(path, cfg).panels[0].circuits]
    ok = [v for v in sizes if v.value is not None]
    assert ok and all(v.confidence is Confidence.MEDIUM for v in ok)
    assert "'wire'" in ok[0].source.note
    no_wire = copy.deepcopy(M0_SCHEDULE)
    no_wire["conductor_size"].remove("wire")
    parsed = parse_file(path, cfg_with(test_cfg, schedule=no_wire))
    (col,) = [u for u in parsed.unparsed if u.raw == "Wire Sz."]
    assert col.kind == "column" and col.reason
    assert parsed.panels[0].circuits[0].conductor_size.source is None


def test_unknown_columns_never_dropped(test_cfg):
    parsed = parse_file(SAMPLES / "two_panels.csv", test_cfg)
    unparsed = [u.raw for u in parsed.unparsed if u.kind == "column"]
    assert len(unparsed) == len(set(unparsed))
    assert "Notes" in unparsed
    mapped = 0
    for text in HEADER:
        hits = unparsed.count(text)
        assert hits <= 1
        mapped += 1 - hits
    # Mapped and unparsed columns together are all 15 header cells.
    assert mapped + len(unparsed) == 15
    assert f"{mapped} of 15 columns mapped" in parsed.coverage[0].what_read


def test_txt_tab_delimited_file(tmp_path, cfg):
    path = write(tmp_path, "export.txt", "Ckt\tDescription\tBreaker\n1\tLights\t20\n")
    parsed = parse_file(path, cfg)
    # No panel name anywhere, so the row is listed and not guessed.
    assert parsed.panels == []
    assert [u.reason for u in parsed.unparsed] == ["no panel name"]
    path = write(tmp_path, "export2.txt", "Panel\tCkt\tDescription\tBreaker\nLP-1\t1\tLights\t20\n")
    (panel,) = parse_file(path, cfg).panels
    assert panel.circuits[0].breaker_a.value == 20.0


def test_semicolon_delimited_file(tmp_path, cfg):
    path = write(tmp_path, "s.csv", "Panel;Ckt;Description;Breaker\nLP-1;1;Lights, east;20\n")
    (panel,) = parse_file(path, cfg).panels
    assert panel.circuits[0].description.value == "Lights, east"
    assert panel.circuits[0].breaker_a.value == 20.0


def test_utf8_bom_file(tmp_path, cfg):
    path = write(tmp_path, "b.csv", "﻿Panel,Ckt,Description\nLP-1,1,Lights\n")
    parsed = parse_file(path, cfg)
    (panel,) = parsed.panels
    assert panel.circuits[0].number == "1"
    assert "encoding utf-8 with BOM" in parsed.coverage[0].what_read


def test_utf16_bom_file(tmp_path, cfg):
    path = write(tmp_path, "w.csv", "Panel,Ckt,Description\r\nLP-1,1,Lights\r\n", "utf-16")
    parsed = parse_file(path, cfg)
    assert parsed.panels[0].circuits[0].description.value == "Lights"
    assert "encoding utf-16" in parsed.coverage[0].what_read


def test_cp1252_named_in_coverage(tmp_path, cfg):
    path = write(tmp_path, "c.csv", "Panel,Ckt,Description\nLP-1,1,Café lights\n", "cp1252")
    parsed = parse_file(path, cfg)
    assert parsed.panels[0].circuits[0].description.value == "Café lights"
    assert "encoding cp1252" in parsed.coverage[0].what_read


def test_revit_style_sample_reads_eight_circuits(test_cfg):
    sched = copy.deepcopy(M0_SCHEDULE)
    sched.update(
        circuit_number=["circuit number"],
        description=["load name"],
        breaker_a=["rating"],
        poles=["number of poles"],
        voltage_v=["voltage"],
        load_type=["load classification"],
        load_va=["apparent power"],
        phase=["ph"],
    )
    parsed = parse_file(SAMPLES / "revit_style_circuits.txt", cfg_with(test_cfg, schedule=sched))
    (panel,) = parsed.panels
    assert (panel.name, len(panel.circuits)) == ("PP-1", 8)
    two_pole = next(c for c in panel.circuits if c.number == "2,4")
    assert (two_pole.breaker_a.value, two_pole.voltage_v.value, two_pole.load_va.value) == (
        30.0,
        208.0,
        4200.0,
    )
    assert two_pole.load_type.confidence is Confidence.LOW  # "power" is not a known load type
    spare = next(c for c in panel.circuits if c.description.value == "SPARE")
    assert spare.is_spare and spare.load_va.confidence is Confidence.MISSING
    assert [u.raw for u in parsed.unparsed] == ["Phase Label", "Electrical Circuits Schedule"]


def test_xlsx_sheet_per_panel(tmp_path, cfg):
    head = ["Ckt", "Description", "Breaker"]
    path = workbook(
        tmp_path,
        {
            "Sheet A": [["Panel", "LP-A"], head, [1, "Lights", 20.0], [2, "Plugs", 15]],
            "Sheet B": [["Panel:", "LP-B"], head, [1, "Pump", "30 A"]],
        },
    )
    parsed = parse_file(path, cfg)
    assert [(p.name, len(p.circuits)) for p in parsed.panels] == [("LP-A", 2), ("LP-B", 1)]
    first = parsed.panels[0].circuits[0]
    assert first.number == "1"
    assert first.breaker_a.value == 20.0
    assert first.source.locator == "sheet=Sheet A; row=3"
    assert parsed.panels[1].circuits[0].breaker_a.value == 30.0
    assert parsed.panels[0].source.confidence is Confidence.HIGH
    assert parsed.unparsed == []


def test_xlsx_sheet_name_fallback_medium(tmp_path, cfg):
    path = workbook(tmp_path, {"LP-7": [["Ckt", "Description", "Breaker"], [1, "Lights", 20]]})
    (panel,) = parse_file(path, cfg).panels
    assert panel.name == "LP-7"
    assert panel.source.confidence is Confidence.MEDIUM
    assert panel.source.note == "panel name from sheet name"
    assert panel.source.locator == "sheet=LP-7; row=1"


def test_xlsx_sheet_without_header(tmp_path, cfg):
    path = workbook(
        tmp_path,
        {
            "Notes": [["Remember to check", "the loads"], ["x", "y"]],
            "Empty": [],
            "LP-1": [["Ckt", "Description", "Breaker"], [1, "Lights", 20]],
        },
    )
    parsed = parse_file(path, cfg)
    assert [p.name for p in parsed.panels] == ["LP-1"]
    sheets = [(u.kind, u.raw) for u in parsed.unparsed if u.kind == "sheet"]
    assert sheets == [("sheet", "Notes"), ("sheet", "Empty")]
    cols = [u.raw for u in parsed.unparsed if u.kind == "column"]
    assert cols == ["Remember to check", "the loads"]


def test_unreadable_file_raises_input_error(tmp_path, cfg):
    with pytest.raises(InputError, match="cannot open the workbook"):
        parse_file(write(tmp_path, "bad.xlsx", b"this is not a zip"), cfg)
    with pytest.raises(InputError, match="NUL bytes"):
        parse_file(write(tmp_path, "nul.csv", b"Panel,Ckt\nLP-1,\x001\n"), cfg)
    with pytest.raises(InputError, match="cannot split the file into rows"):
        parse_file(write(tmp_path, "big.csv", "Panel,Ckt\nLP-1," + "x" * 200_000 + "\n"), cfg)
    with pytest.raises(InputError, match="cannot decode the file"):
        parse_file(write(tmp_path, "undecodable.csv", b"Panel,Ckt\nLP-1,\x81\n"), cfg)
    with pytest.raises(InputError, match="cannot read the file"):
        parse_file(tmp_path / "missing.csv", cfg)
    with pytest.raises(InputError, match="unsupported file type"):
        parse_file(write(tmp_path, "other.pdf", b"%PDF"), cfg)


def test_aecad_export_all_columns_unparsed(tmp_path, cfg):
    heads = ["ITEM", "TAGNAME", "CNT", "UNITS", "MFG", "CAT", "DESC1", "DESC2", "DESC3"]
    heads += ["LOC", "INST", "RATING1", "RATING2"]
    text = ",".join(heads) + "\n1,MCB1,1,EA,ACME,X-100,Breaker,,,PNL1,A,20,\n"
    parsed = parse_file(write(tmp_path, "components.csv", text), cfg)
    assert cfg.column_maps["aecad_export"]["headers"] == {}
    assert parsed.panels == []
    assert [u.raw for u in parsed.unparsed if u.kind == "column"] == heads
    assert [u.kind for u in parsed.unparsed if u.kind != "column"] == ["table"]
    (entry,) = parsed.coverage
    assert (entry.unit, entry.what_read) == ("file", "no panel read")


def test_empty_file_gives_no_panel_coverage(tmp_path, cfg):
    parsed = parse_file(write(tmp_path, "empty.csv", b""), cfg)
    assert parsed.panels == []
    assert [u.reason for u in parsed.unparsed] == ["no rows"]
    assert parsed.coverage[0].what_read == "no panel read"


def test_source_file_is_name_only(tmp_path, cfg):
    folder = tmp_path / "deep" / "folder"
    folder.mkdir(parents=True)
    path = write(folder, "x.csv", "Panel,Ckt,Description,Breaker\nLP-1,1,Lights,20\nLP-1,,TOTAL,\n")
    parsed = parse_file(path, cfg)
    sources = [parsed.panels[0].source, parsed.panels[0].circuits[0].source]
    sources += [v.source for v in (parsed.panels[0].circuits[0].breaker_a,)]
    sources += [u.source for u in parsed.unparsed]
    assert len(sources) >= 4
    assert {s.file for s in sources} == {"x.csv"}
    assert {c.file for c in parsed.coverage} == {"x.csv"}
    xlsx = workbook(folder, {"LP-1": [["Ckt", "Description", "Breaker"], [1, "a", 20]]}, "y.xlsx")
    sheet = parse_file(xlsx, cfg)
    assert sheet.panels[0].source.file == "y.xlsx"


def test_shipped_config_reads_the_sample(skeleton_cfg):
    parsed = parse_file(SAMPLES / "two_panels.csv", skeleton_cfg)
    assert [len(p.circuits) for p in parsed.panels] == [20, 20]


def _inflate_dimension(path):
    import re
    import shutil
    import zipfile

    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                xml = data.decode("utf-8")
                xml = re.sub(r'<dimension ref="[^"]*"', '<dimension ref="A1:XFD1048576"', xml)
                xml = xml.replace('<row r="2"', '<row r="1048576"')
                xml = re.sub(r'<c r="([A-Z]+)2"', r'<c r="\g<1>1048576"', xml)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)


def test_xlsx_inflated_dimension_parses_quickly(tmp_path, cfg):
    import time

    path = workbook(tmp_path, {"LP-1": [["Ckt", "Description", "Breaker"], [1, "Lights", 20]]})
    _inflate_dimension(path)
    start = time.monotonic()
    try:
        parse_file(path, cfg)
    except InputError:
        pass
    assert time.monotonic() - start < 5


def test_xlsx_parser_bug_is_not_reported_as_unreadable_workbook(tmp_path, cfg, monkeypatch):
    import redline.parsers.csv_xlsx as mod

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "rows_to_panels", boom)
    path = workbook(tmp_path, {"LP-1": [["Ckt", "Breaker"], [1, 20]]})
    with pytest.raises(RuntimeError, match="boom"):
        parse_file(path, cfg)


def _refused(parsed, name):
    return [u for u in parsed.unparsed if u.kind == "sheet" and u.raw == name]


def test_xlsx_wide_sheet_listed_not_cut(tmp_path, cfg):
    from redline.parsers.csv_xlsx import MAX_COLS

    wide = ["Ckt", "Description", "Breaker"] + [""] * (MAX_COLS - 3) + ["SECRET"]
    path = workbook(
        tmp_path,
        {
            "Wide": [wide, [1, "Lights", 20]],
            "LP-2": [["Ckt", "Description", "Breaker"], [1, "A", 15]],
        },
    )
    parsed = parse_file(path, cfg)
    (entry,) = _refused(parsed, "Wide")
    assert f"more than {MAX_COLS} columns" in entry.reason
    assert [p.name for p in parsed.panels] == ["LP-2"]


def test_xlsx_long_sheet_listed_other_sheets_read(tmp_path, cfg, monkeypatch):
    import redline.parsers.csv_xlsx as mod

    monkeypatch.setattr(mod, "MAX_ROWS", 3)
    rows = [["Ckt", "Description", "Breaker"]] + [[i, "L", 20] for i in range(1, 6)]
    path = workbook(
        tmp_path,
        {"Long": rows, "LP-2": [["Ckt", "Description", "Breaker"], [1, "A", 15]]},
    )
    parsed = parse_file(path, cfg)
    (entry,) = _refused(parsed, "Long")
    assert "more than 3 rows" in entry.reason
    assert [p.name for p in parsed.panels] == ["LP-2"]


def test_xlsx_cell_past_column_limit_listed_not_cut(tmp_path, cfg):
    from openpyxl.utils import get_column_letter

    from redline.parsers.csv_xlsx import MAX_COLS

    for col in (MAX_COLS + 1, MAX_COLS + 2, 250, 16384):
        wb = openpyxl.Workbook()
        wb.active.title = "Far"
        wb["Far"].append(["Ckt", "Description", "Breaker"])
        wb["Far"].append([1, "Lights", 20])
        wb["Far"][f"{get_column_letter(col)}1"] = "Load VA"
        wb["Far"][f"{get_column_letter(col)}2"] = 9000
        ok = wb.create_sheet("LP-2")
        ok.append(["Ckt", "Description", "Breaker"])
        ok.append([1, "A", 15])
        path = tmp_path / f"far{col}.xlsx"
        wb.save(path)
        parsed = parse_file(path, cfg)
        (entry,) = _refused(parsed, "Far")
        assert f"more than {MAX_COLS} columns" in entry.reason
        assert [p.name for p in parsed.panels] == ["LP-2"]


def _stuff(path, member, extra):
    import shutil
    import zipfile

    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item)
            if item.filename == member:
                data = extra(data.decode("utf-8")).encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)


def test_xlsx_uncompressed_size_over_cap_refused(tmp_path, cfg, monkeypatch):
    import redline.parsers.csv_xlsx as mod

    path = workbook(tmp_path, {"LP-1": [["Ckt", "Breaker"], [1, 20]]})
    monkeypatch.setattr(mod, "MAX_XLSX_BYTES", 100_000)
    _stuff(path, "xl/worksheets/sheet1.xml", lambda x: x + " " * 200_000)
    with pytest.raises(InputError, match="once unpacked"):
        parse_file(path, cfg)


def test_xlsx_far_cells_every_row_quick(tmp_path, cfg):
    import time

    rows = 15_000
    xml_rows = "".join(
        f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>x</t></is></c>'
        f'<c r="XFD{i}"><v>1</v></c></row>'
        for i in range(1, rows + 1)
    )
    path = workbook(tmp_path, {"Far": [["Ckt"]]})

    def swap(x):
        start = x.index("<sheetData>") + len("<sheetData>")
        return x[:start] + xml_rows + x[x.index("</sheetData>") :]

    _stuff(path, "xl/worksheets/sheet1.xml", swap)
    start = time.monotonic()
    parsed = parse_file(path, cfg)
    assert time.monotonic() - start < 5
    (entry,) = _refused(parsed, "Far")
    assert "more than" in entry.reason and "columns" in entry.reason


def test_xlsx_size_cap_counts_parts_at_any_path(tmp_path, cfg, monkeypatch):
    import zipfile

    import redline.parsers.csv_xlsx as mod

    monkeypatch.setattr(mod, "MAX_XLSX_BYTES", 100_000)
    base = workbook(tmp_path, {"LP-1": [["Ckt", "Description", "Breaker"], [1, "A", 20]]})
    # A normal small workbook is under the cap and still reads.
    assert [p.name for p in parse_file(base, cfg).panels] == ["LP-1"]
    # A sheet or shared strings at another path, and a big styles part, each count.
    for i, member in enumerate(("xl/data/sheet1.xml", "xl/strings/ss.xml", "xl/styles.xml")):
        path = tmp_path / f"big{i}.xlsx"
        with zipfile.ZipFile(base) as zin, zipfile.ZipFile(path, "w") as zout:
            for item in zin.infolist():
                data = zin.read(item)
                if item.filename == member:
                    data += b" " * 200_000
                zout.writestr(item, data)
            if member not in zin.namelist():
                zout.writestr(member, b" " * 200_000)
        with pytest.raises(InputError, match="once unpacked"):
            parse_file(path, cfg)


def _swap_sheet_data(path, xml_rows, sheet="xl/worksheets/sheet1.xml"):
    def swap(x):
        start = x.index("<sheetData>") + len("<sheetData>")
        return x[:start] + xml_rows + x[x.index("</sheetData>") :]

    _stuff(path, sheet, swap)


def _cell(ref, v):
    return f'<c r="{ref}" t="inlineStr"><is><t>{v}</t></is></c>'


def test_xlsx_out_of_order_cells_refused_not_moved(tmp_path, cfg):
    head = (
        f'<row r="1">{_cell("A1", "Ckt")}{_cell("B1", "Breaker")}{_cell("C1", "Description")}</row>'
    )
    cases = {
        # duplicate A2: the later value must not win
        "dup": f'<row r="2">{_cell("A2", 2)}{_cell("A2", 5)}{_cell("B2", 20)}{_cell("C2", 1)}</row>',
        # B2 before A2
        "order": f'<row r="2">{_cell("B2", 20)}{_cell("A2", 3)}{_cell("C2", 1)}</row>',
        # row 3 then row 2
        "rows": f'<row r="3">{_cell("A3", 1)}</row><row r="2">{_cell("A2", 2)}</row>',
        # repeated row index
        "repeat": f'<row r="2">{_cell("A2", 1)}</row><row r="2">{_cell("A2", 2)}</row>',
        # many cells all claiming A2
        "many": '<row r="2">' + "".join(_cell("A2", i) for i in range(300)) + "</row>",
    }
    for key, body in cases.items():
        path = workbook(
            tmp_path,
            {
                "Bad": [["Ckt"]],
                "LP-2": [["Ckt", "Description", "Breaker"], [1, "A", 15]],
            },
            name=f"{key}.xlsx",
        )
        _swap_sheet_data(path, head + body)
        parsed = parse_file(path, cfg)
        (entry,) = _refused(parsed, "Bad")
        assert "out of order" in entry.reason, key
        assert [p.name for p in parsed.panels] == ["LP-2"], key
    # Cells with no r attribute keep their sequential positions and still read.
    path = workbook(tmp_path, {"LP-3": [["Ckt", "Breaker"]]}, name="norefs.xlsx")
    bare = "".join(
        f"<row>{''.join(f'<c t="inlineStr"><is><t>{v}</t></is></c>' for v in r)}</row>"
        for r in (["Ckt", "Description", "Breaker"], [1, "A", 15])
    )
    _swap_sheet_data(path, bare)
    parsed = parse_file(path, cfg)
    assert not _refused(parsed, "LP-3")
    assert [p.name for p in parsed.panels] == ["LP-3"]


def test_xlsx_refused_sheets_charge_row_budget(tmp_path, cfg, monkeypatch):
    import redline.parsers.csv_xlsx as mod

    monkeypatch.setattr(mod, "MAX_ROWS", 3)
    monkeypatch.setattr(mod, "MAX_TOTAL_ROWS", 9)
    long = [["Ckt", "Description", "Breaker"]] + [[i, "L", 20] for i in range(1, 8)]
    sheets = {f"Long{i}": long for i in range(1, 6)}
    sheets["LP-2"] = [["Ckt", "Description", "Breaker"], [1, "A", 15]]
    path = workbook(tmp_path, sheets)
    calls = []
    real = mod._sheet_rows
    monkeypatch.setattr(mod, "_sheet_rows", lambda *a: calls.append(a[-1]) or real(*a))
    parsed = parse_file(path, cfg)
    # Each refused sheet parses 4 row indexes (3 allowed plus the one over), so the
    # 9-row budget is spent after three sheets and nothing later is parsed.
    assert calls == ["Long1", "Long2", "Long3"]
    for name in ("Long4", "Long5", "LP-2"):
        (entry,) = _refused(parsed, name)
        assert "more than 9 rows" in entry.reason
    assert parsed.panels == []


def test_xlsx_one_sheet_part_under_two_sheets_refused(tmp_path, cfg):
    path = workbook(
        tmp_path,
        {"A": [["Ckt", "Breaker"], [1, 20]], "B": [["Ckt", "Breaker"], [1, 20]]},
    )
    _stuff(path, "xl/_rels/workbook.xml.rels", lambda x: x.replace("sheet2.xml", "sheet1.xml"))
    with pytest.raises(InputError, match="more than one sheet"):
        parse_file(path, cfg)


def _two_sheets(tmp_path):
    return workbook(
        tmp_path,
        {"A": [["Ckt", "Breaker"], [1, 20]], "B": [["Ckt", "Breaker"], [1, 20]]},
    )


def _point_sheet2_at_sheet1(spelling):
    # The writer gives absolute targets; sheet 2 is re-pointed at sheet 1 with this spelling.
    return lambda x: x.replace("/xl/worksheets/sheet2.xml", spelling)


def test_xlsx_shared_rid_sheet_entries_refused(tmp_path, cfg):
    # Two <sheet> entries with one r:id: the rels list a single part, the sheets name it twice.
    path = _two_sheets(tmp_path)
    _stuff(path, "xl/workbook.xml", lambda x: x.replace('r:id="rId2"', 'r:id="rId1"'))
    with pytest.raises(InputError, match="more than one sheet"):
        parse_file(path, cfg)


def test_xlsx_dot_relative_duplicate_target_refused(tmp_path, cfg):
    path = _two_sheets(tmp_path)
    _stuff(path, "xl/_rels/workbook.xml.rels", _point_sheet2_at_sheet1("./worksheets/sheet1.xml"))
    with pytest.raises(InputError, match="more than one sheet"):
        parse_file(path, cfg)


def _move_workbook_part(path):
    # openpyxl finds the workbook part through the content types, so moving it leaves
    # xl/workbook.xml absent while the file still opens.
    src = path.with_suffix(".src")
    path.rename(src)
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(path, "w") as zo:
        for it in zi.infolist():
            d = zi.read(it.filename)
            name = {
                "xl/workbook.xml": "xl/wb/book.xml",
                "xl/_rels/workbook.xml.rels": "xl/wb/_rels/book.xml.rels",
            }.get(it.filename, it.filename)
            if name == "[Content_Types].xml":
                d = d.replace(b"/xl/workbook.xml", b"/xl/wb/book.xml")
            zo.writestr(name, d)
    src.unlink()


def test_xlsx_sheet_part_named_by_respelled_or_untyped_targets_refused(tmp_path, cfg):
    rels = "xl/_rels/workbook.xml.rels"
    cases = {
        "double_slash": lambda p: _stuff(
            p, rels, _point_sheet2_at_sheet1("worksheets//sheet1.xml")
        ),
        "dot_segments": lambda p: _stuff(
            p, rels, _point_sheet2_at_sheet1("worksheets/././sheet1.xml")
        ),
        "relative_beside_absolute": lambda p: _stuff(
            p, rels, _point_sheet2_at_sheet1("worksheets/sheet1.xml")
        ),
        "untyped": lambda p: _stuff(
            p,
            rels,
            lambda x: _point_sheet2_at_sheet1("/xl/worksheets/sheet1.xml")(x).replace(
                '/worksheet"', '/other"'
            ),
        ),
        "single_quoted": lambda p: _stuff(
            p,
            rels,
            lambda x: _point_sheet2_at_sheet1("/xl/worksheets/sheet1.xml")(x).replace('"', "'"),
        ),
        "moved_workbook_part": lambda p: (
            # Relative targets now resolve from xl/wb/, so ../ is what names sheet 1 again.
            _stuff(p, rels, _point_sheet2_at_sheet1("../worksheets//sheet1.xml")),
            _move_workbook_part(p),
        ),
    }
    for label, mutate in cases.items():
        d = tmp_path / label
        d.mkdir()
        path = _two_sheets(d)
        mutate(path)
        with pytest.raises(InputError, match="more than one sheet"):
            parse_file(path, cfg)


def test_xlsx_too_many_sheet_entries_refused(tmp_path, cfg):
    path = _two_sheets(tmp_path)

    def many(x):
        m = re.search(r"<sheet [^>]*/>", x).group(0)
        return x.replace(m, m * (MAX_SHEETS + 1))

    _stuff(path, "xl/workbook.xml", many)
    with pytest.raises(InputError, match="more than 255 sheets"):
        parse_file(path, cfg)


_NS = (
    'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_PKG = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'
_CT = (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    "</Types>"
)
_SHEET = (
    f'<worksheet {_NS}><sheetData><row r="1">{_cell("A1", "Ckt")}{_cell("B1", "Load")}'
    f"{_cell('C1', 'Breaker')}</row></sheetData></worksheet>"
)


def _raw_book(tmp_path, wb_xml, wb_rels, parts):
    path = tmp_path / "raw.xlsx"
    root = f'<Relationships {_PKG}><Relationship Id="rId1" Type="{_REL}officeDocument" Target="xl/workbook.xml"/></Relationships>'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", root)
        z.writestr("xl/workbook.xml", wb_xml)
        z.writestr("xl/_rels/workbook.xml.rels", f"<Relationships {_PKG}>{wb_rels}</Relationships>")
        z.writestr("xl/worksheets/sheet1.xml", _SHEET)
        for name, data in parts.items():
            z.writestr(name, data)
    return path


def test_xlsx_repeated_external_reference_not_parsed_per_entry(tmp_path, cfg, monkeypatch):
    import time

    import openpyxl.reader.workbook as rw

    def boom(*a, **k):
        raise AssertionError("an external link part was parsed")

    monkeypatch.setattr(rw, "read_external_link", boom)
    n = 100
    wb = (
        f'<workbook {_NS}><sheets><sheet name="S0" sheetId="1" r:id="rId1"/></sheets>'
        "<externalReferences>"
        + '<externalReference r:id="rId2"/>' * n
        + "</externalReferences></workbook>"
    )
    rels = (
        f'<Relationship Id="rId1" Type="{_REL}worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{_REL}externalLink" Target="externalLinks/externalLink1.xml"/>'
    )
    cell = '<cell r="A1"><v>1</v></cell>'
    ext = (
        f'<externalLink {_NS}><externalBook r:id="rId1"><sheetDataSet><sheetData sheetId="0">'
        f'<row r="1">{cell * (2**20 // len(cell))}</row></sheetData></sheetDataSet></externalBook></externalLink>'
    )
    path = _raw_book(tmp_path, wb, rels, {"xl/externalLinks/externalLink1.xml": ext})
    start = time.monotonic()
    parsed = parse_file(path, cfg)
    assert time.monotonic() - start < 5
    assert [p.name for p in parsed.panels] == ["S0"] and not _refused(parsed, "S0")


def test_xlsx_chartsheet_drawing_rels_not_parsed(tmp_path, cfg, monkeypatch):
    import time

    import openpyxl.reader.drawings as rd

    def boom(*a, **k):
        raise AssertionError("a drawing part was parsed")

    monkeypatch.setattr(rd, "find_images", boom)
    n = 100
    wb = (
        f'<workbook {_NS}><sheets><sheet name="LP-1" sheetId="1" r:id="rId1"/>'
        '<sheet name="C0" sheetId="2" r:id="rId2"/></sheets></workbook>'
    )
    rels = (
        f'<Relationship Id="rId1" Type="{_REL}worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{_REL}chartsheet" Target="chartsheets/sheet1.xml"/>'
    )
    csrels = (
        f"<Relationships {_PKG}>"
        + "".join(
            f'<Relationship Id="rId{i + 1}" Type="{_REL}drawing" Target="../drawings/drawing1.xml"/>'
            for i in range(n)
        )
        + "</Relationships>"
    )
    anchor = '<xdr:absoluteAnchor><xdr:pos x="0" y="0"/><xdr:ext cx="1" cy="1"/><xdr:clientData/></xdr:absoluteAnchor>'
    drawing = (
        '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing">'
        + anchor * (2**20 // len(anchor))
        + "</xdr:wsDr>"
    )
    path = _raw_book(
        tmp_path,
        wb,
        rels,
        {
            "xl/chartsheets/sheet1.xml": f'<chartsheet {_NS}><drawing r:id="rId1"/></chartsheet>',
            "xl/chartsheets/_rels/sheet1.xml.rels": csrels,
            "xl/drawings/drawing1.xml": drawing,
        },
    )
    start = time.monotonic()
    parsed = parse_file(path, cfg)
    assert time.monotonic() - start < 5
    (entry,) = _refused(parsed, "C0")
    assert "chartsheet C0 is not read" in entry.reason
    # LP-1 is a normal worksheet and was read (its header-only table yields no panel).
    assert not _refused(parsed, "LP-1")


def test_xlsx_reader_never_calls_load_workbook(tmp_path, cfg, monkeypatch):
    import datetime

    import openpyxl.reader.excel as rx

    def boom(*a, **k):
        raise AssertionError("load_workbook was called")

    path = workbook(
        tmp_path,
        {
            "LP-1": [
                ["Ckt", "Description", "Breaker", "Load (VA)", "Notes"],
                [1, "Lights", 20, "=A2*2", datetime.date(2026, 1, 2)],
                [2, "Plugs", 15, 300, True],
            ],
            "LP-2": [["Ckt", "Description", "Breaker"], [1, "Pumps", 30]],
        },
    )
    want = parse_file(path, cfg)
    monkeypatch.setattr(openpyxl, "load_workbook", boom)
    monkeypatch.setattr(rx, "load_workbook", boom)
    got = parse_file(path, cfg)
    assert [p.name for p in got.panels] == ["LP-1", "LP-2"]
    assert got == want
