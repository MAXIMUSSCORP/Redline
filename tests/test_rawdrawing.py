import copy
import json
from pathlib import Path

import pytest

from redline import rawdrawing
from redline.rawdrawing import read, validate

FIXTURES = Path(__file__).resolve().parent.parent / "samples" / "dwg"


def _valid() -> dict:
    return {
        "schema_version": "1.0",
        "extractor": "acad_plugin",
        "extractor_version": "0.1.0",
        "host_version": "test host",
        "source_file": "E-101.dwg",
        "source_sha256": "ab" * 32,
        "extracted_at": "2026-11-06T12:00:00Z",
        "document": {
            "units": "mm",
            "layouts": ["Model", "E-101"],
            "xrefs": [{"name": "A-BASE", "path": "A-BASE.dwg", "resolved": True}],
            "warnings": [],
        },
        "entities": [
            {
                "id": "e000123",
                "type": "ACAD_TABLE",
                "layout": "E-101",
                "handle": "2F3A",
                "bbox": [1200.0, 650.0, 1300.0, 700.0],
                "table": {
                    "rows": 2,
                    "cols": 2,
                    "cells": [{"r": 0, "c": 0, "text": "CKT", "evaluated": True}],
                },
            },
            {"id": "e2", "type": "TEXT", "layout": "E-101", "handle": "2F3B", "text": "LP-1"},
        ],
    }


def test_valid_fixture_passes():
    v = validate(_valid())
    assert v.ok
    assert v.errors == ()
    assert v.warnings == ()


def test_missing_field_fails():
    d = _valid()
    del d["extractor"]
    v = validate(d)
    assert not v.ok
    assert any("extractor" in e for e in v.errors)


def test_missing_entity_handle_fails():
    d = _valid()
    del d["entities"][1]["handle"]
    assert any("handle" in e for e in validate(d).errors)


def test_unknown_entity_type_fails():
    d = _valid()
    d["entities"][1]["type"] = "SPLINE"
    assert not validate(d).ok


def test_higher_major_refused():
    d = _valid()
    d["schema_version"] = "2.0"
    v = validate(d)
    assert not v.ok
    assert any("major" in e for e in v.errors)


def test_higher_minor_warns():
    d = _valid()
    d["schema_version"] = "1.1"
    v = validate(d)
    assert v.ok
    assert any("minor" in w for w in v.warnings)


def test_bad_bbox_fails():
    for bad in ([5, 0, 1, 1], [0, 5, 1, 1], [1, 2, 3], ["a", 0, 1, 1]):
        d = copy.deepcopy(_valid())
        d["entities"][0]["bbox"] = bad
        v = validate(d)
        assert not v.ok, bad
        assert any("bbox" in e for e in v.errors)


def test_bad_table_cell_fails():
    d = _valid()
    d["entities"][0]["table"]["cells"][0]["r"] = 9
    assert any("table.cells[0]" in e for e in validate(d).errors)
    d = _valid()
    d["entities"][0]["table"]["cells"][0]["evaluated"] = "yes"
    assert not validate(d).ok


def test_document_missing_key_fails():
    d = _valid()
    del d["document"]["xrefs"]
    assert any("xrefs" in e for e in validate(d).errors)


def test_not_an_object_fails():
    assert not validate([]).ok


def _errors(d: dict) -> str:
    return " | ".join(validate(d).errors)


def test_table_without_counts_validates():
    d = _valid()
    t = d["entities"][0]["table"]
    t["rows"] = t["cols"] = None
    t["cells"] = [{"r": 40, "c": 9, "text": "x", "evaluated": True}]
    assert validate(d).ok
    t["cells"][0]["r"] = -1
    assert "table.cells[0]" in _errors(d)
    t["cells"][0].update(r=0, c=1.5)
    assert not validate(d).ok
    t["cells"][0]["c"] = 1
    t["rows"], t["cols"] = 2, None
    assert "both integers or both null" in _errors(d)
    t["rows"], t["cols"] = True, 2
    assert not validate(d).ok


def test_attributes_shape_checked():
    d = _valid()
    e = d["entities"][1]
    e["attributes"] = [{"tag": "SHEET", "value": "E-101"}, {"tag": "A", "value": ""}]
    assert validate(d).ok
    for bad in ("x", [1], [{"tag": "A"}], [{"tag": 1, "value": "v"}], [{"tag": "A", "value": 2}]):
        e["attributes"] = bad
        assert "attributes" in _errors(d), bad
    e["attributes"] = None
    assert validate(d).ok


def test_text_fields_typed():
    d = _valid()
    e = d["entities"][1]
    e.update(layer="E", block_name=None, xref_path="x.dwg", text_height=2.5, rotation_deg=-90)
    e["insertion_point"] = [1.0, 2.0]
    assert validate(d).ok
    e["insertion_point"] = [1, 2, 3]
    assert validate(d).ok
    for key, bad in (
        ("text", 5),
        ("layer", 5),
        ("block_name", ["a"]),
        ("xref_path", 1.5),
        ("text_height", 0),
        ("text_height", -1),
        ("text_height", True),
        ("text_height", "2.5"),
        ("text_height", float("inf")),
        ("insertion_point", [1]),
        ("insertion_point", [1, 2, 3, 4]),
        ("insertion_point", [1, "2"]),
        ("insertion_point", [1, float("nan")]),
        ("rotation_deg", "90"),
        ("rotation_deg", float("inf")),
    ):
        d2 = copy.deepcopy(d)
        d2["entities"][1][key] = bad
        assert key in _errors(d2), (key, bad)


def test_source_sha256_hex():
    d = _valid()
    for bad in ("abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65, 7, None):
        d["source_sha256"] = bad
        assert "source_sha256" in _errors(d), bad
    d["source_sha256"] = "0123456789abcdef" * 4
    assert validate(d).ok


def test_source_file_name_only():
    d = _valid()
    for bad in ("a/b.dwg", "a\\b.dwg", "C:b.dwg", "", 5):
        d["source_file"] = bad
        assert "source_file" in _errors(d), bad
    for key in ("extractor", "extractor_version", "host_version", "extracted_at"):
        d2 = _valid()
        for bad in ("", 3, None):
            d2[key] = bad
            assert key in _errors(d2), (key, bad)


def test_xref_entries_checked():
    d = _valid()
    doc = d["document"]
    for bad in ("x", [1], [{"name": "A", "path": "p"}], [{"name": "A", "path": 1, "resolved": 1}]):
        doc["xrefs"] = bad
        assert "xrefs" in _errors(d), bad
    doc["xrefs"] = [{"name": "A", "path": "p", "resolved": "yes"}]
    assert not validate(d).ok
    doc["xrefs"] = []
    assert validate(d).ok
    doc["units"] = 1
    assert "units" in _errors(d)
    doc.update(units="mm", layouts=["Model", 2])
    assert "layouts" in _errors(d)
    doc.update(layouts=[], warnings="none")
    assert "warnings" in _errors(d)


def test_caps_refused(monkeypatch):
    d = _valid()
    assert validate(d).ok
    monkeypatch.setattr(rawdrawing, "MAX_ENTITIES", 1)
    assert "MAX_ENTITIES" in _errors(d)
    monkeypatch.setattr(rawdrawing, "MAX_ENTITIES", 10)
    monkeypatch.setattr(rawdrawing, "MAX_TABLE_CELLS", 0)
    assert "MAX_TABLE_CELLS" in _errors(d)
    monkeypatch.setattr(rawdrawing, "MAX_TABLE_CELLS", 10)
    assert validate(d).ok
    monkeypatch.setattr(rawdrawing, "MAX_TEXT", 3)
    assert "MAX_TEXT" in _errors(d)
    monkeypatch.setattr(rawdrawing, "MAX_TEXT", 10)
    d["entities"][1]["attributes"] = [{"tag": "T", "value": "v" * 11}]
    assert "attributes[0].value" in _errors(d)


def _write(tmp_path, text: str) -> Path:
    p = tmp_path / "a.rawdrawing.json"
    p.write_bytes(text.encode("utf-8"))
    return p


def test_read_refuses_constants_and_repeats(tmp_path):
    assert read(_write(tmp_path, json.dumps(_valid())))["extractor"] == "acad_plugin"
    for bad in (
        '{"a": NaN}',
        '{"a": Infinity}',
        '{"a": -Infinity}',
        '{"a": 1e999}',
        '{"a": 1, "a": 2}',
        '{"a": ' + "9" * 40 + "}",
        "[" * 100_000,
        "{not json",
    ):
        with pytest.raises(ValueError):
            read(_write(tmp_path, bad))
    p = tmp_path / "latin.json"
    p.write_bytes(b'{"a": "\xe9"}')
    with pytest.raises(ValueError):
        read(p)


def test_read_size_cap(tmp_path, monkeypatch):
    p = _write(tmp_path, json.dumps(_valid()))
    monkeypatch.setattr(rawdrawing, "MAX_JSON_BYTES", p.stat().st_size)
    assert read(p)
    monkeypatch.setattr(rawdrawing, "MAX_JSON_BYTES", p.stat().st_size - 1)
    with pytest.raises(ValueError, match="MAX_JSON_BYTES"):
        read(p)


def _fixtures() -> dict[str, dict]:
    files = sorted(FIXTURES.glob("*.rawdrawing.json"))
    assert [f.name for f in files] == [
        "panel_sheet.acad_plugin.rawdrawing.json",
        "panel_sheet.oda_ezdxf.rawdrawing.json",
    ]
    return {f.name.split(".")[1]: read(f) for f in files}


def test_dwg_fixtures_validate():
    for name, data in _fixtures().items():
        v = validate(data)
        assert v.ok, (name, v.errors)
        assert v.warnings == ()


def _cell_texts(d: dict) -> list[list[str]]:
    return [
        [c["text"] for c in e["table"]["cells"]] for e in d["entities"] if e["type"] == "ACAD_TABLE"
    ]


def test_dwg_fixtures_shape():
    for name, d in _fixtures().items():
        assert d["extractor"] == name
        assert d["extractor_version"] == "0.1.0"
        assert d["host_version"] == "synthetic fixture, no host"
        assert d["source_file"] == "panel_sheet.dwg"
        assert d["source_sha256"] == "0" * 64
        assert d["document"]["units"] == "mm"
        assert d["document"]["layouts"] == ["Model", "E-101"]
        assert d["document"]["xrefs"] == [
            {"name": "A-BASE", "path": "A-BASE.dwg", "resolved": False}
        ]
        ents = d["entities"]
        assert len({e["handle"] for e in ents}) == len(ents)
        assert len({e["id"] for e in ents}) == len(ents)
        assert all(int(e["handle"], 16) for e in ents)
        assert {e["layout"] for e in ents} == {"E-101"}
        tables = [e for e in ents if e["type"] == "ACAD_TABLE"]
        sized = {e["text"]: e["table"] for e in tables if e["table"]["rows"] is not None}
        assert {k: (t["rows"], t["cols"]) for k, t in sized.items()} == {
            "LP-11": (22, 14),
            "LP-12": (8, 6),
        }
        assert all(len(t["cells"]) == t["rows"] * t["cols"] for t in sized.values())
        (nocount,) = [e["table"] for e in tables if e["table"]["rows"] is None]
        assert nocount["cols"] is None
        assert len(nocount["cells"]) == 5 and {c["r"] for c in nocount["cells"]} == {0}
        for t in sized.values():
            stale = [c for c in t["cells"] if not c["evaluated"]]
            assert len(stale) == (0 if name == "acad_plugin" else len(t["cells"]))
        loose = [e for e in ents if e["type"] == "TEXT"]
        assert all(e["text_height"] == 2.5 and e["rotation_deg"] == 0 for e in loose)
        assert any(e["text"] == "Panel LP-13" for e in loose)
        blocks = {e["block_name"]: e for e in ents if e["type"] == "INSERT"}
        assert [a["tag"] for a in blocks["WD_M"]["attributes"]] == ["SHEET", "DWGDESC", "PROJ"]
        assert len(blocks["RECEPT"]["attributes"]) == 2
        assert {"LINE", "POLYLINE"} <= {e["type"] for e in ents}
    a, b = _fixtures().values()
    assert _cell_texts(a) == _cell_texts(b)


def test_validate_caps_names_and_lists():
    over = "x" * (rawdrawing.MAX_TEXT + 1)
    assert not validate(_valid()).errors
    for edit in (
        lambda d: d["entities"][0].update(id=over),
        lambda d: d["entities"][0].update(layout=over),
        lambda d: d["entities"][0].update(handle=over),
        lambda d: d["document"]["xrefs"][0].update(name=over),
        lambda d: d["document"]["xrefs"][0].update(path=over),
    ):
        d = _valid()
        edit(d)
        assert validate(d).errors
    for k in ("layouts", "warnings"):
        d = _valid()
        d["document"][k] = [""] * (rawdrawing.MAX_ENTITIES + 1)
        assert validate(d).errors
