import copy
from pathlib import Path

import openpyxl
import pytest
from test_parser_tabular import M0_SCHEDULE, cfg_with

from redline.model import Confidence
from redline.parsers.csv_xlsx import SUFFIXES, InputError, parse_file

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
    with pytest.raises(InputError):
        parse_file(write(tmp_path, "bad.xlsx", b"this is not a zip"), cfg)
    with pytest.raises(InputError):
        parse_file(write(tmp_path, "nul.csv", b"Panel,Ckt\nLP-1,\x001\n"), cfg)
    with pytest.raises(InputError):
        parse_file(write(tmp_path, "big.csv", "Panel,Ckt\nLP-1," + "x" * 200_000 + "\n"), cfg)
    with pytest.raises(InputError):
        parse_file(write(tmp_path, "undecodable.csv", b"Panel,Ckt\nLP-1,\x81\n"), cfg)
    with pytest.raises(InputError):
        parse_file(tmp_path / "missing.csv", cfg)
    with pytest.raises(InputError):
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
