import copy

from redline.rawdrawing import validate


def _valid() -> dict:
    return {
        "schema_version": "1.0",
        "extractor": "acad_plugin",
        "extractor_version": "0.1.0",
        "host_version": "test host",
        "source_file": "E-101.dwg",
        "source_sha256": "abc",
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
