"""Device block counting and drawing units in the DXF parser (D1, D7)."""

import dataclasses
from collections import Counter
from pathlib import Path

import pytest

from redline.model import Confidence
from redline.parsers import dxf

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "samples" / "plans"
LAYOUTS = ["Model", "FA-1", "FA-2"]
_n = iter(range(1, 1_000_000))


def ins(name, layout="Model", at=(0.0, 0.0), **extra) -> dict:
    n = next(_n)
    e = {"id": f"i{n}", "type": "INSERT", "layout": layout, "handle": f"{n:X}", "block_name": name}
    e |= {"attributes": []}
    if at is not None:
        e["insertion_point"] = list(at)
    return e | extra


def sheet(entities, units="mm", layouts=LAYOUTS) -> dict:
    return {
        "schema_version": "1.0",
        "extractor": "oda_ezdxf",
        "extractor_version": "0.1.0",
        "host_version": "ezdxf test",
        "source_file": "s.dxf",
        "source_sha256": "ab" * 32,
        "extracted_at": "2026-11-10T00:00:00Z",
        "document": {"units": units, "layouts": layouts, "xrefs": [], "warnings": []},
        "entities": list(entities),
    }


def parse(entities, cfg, **kw):
    return dxf.parse_rawdrawing(sheet(entities, **kw), cfg, list_blocks=True)


def tally(out) -> Counter:
    return Counter((d.type, d.detection) for d in out.devices)


# ---- the synthetic sheets (D4) ----


def test_block_counts_equal_known_counts(test_cfg):
    out = dxf.parse_file(PLANS / "sheet_fa101.dxf", test_cfg)
    got = Counter(d.type for d in out.devices if d.detection == "block")
    assert got == {
        "exit_sign": 3,
        "pull_station": 3,
        "emergency_light": 5,
        "exit_door": 3,
        "smoke_detector": 4,
    }
    placed = [d for d in out.devices if d.detection != "nested"]
    assert all(d.source.confidence == Confidence.HIGH for d in placed)


def test_plan_sample_counts(test_cfg):
    a = dxf.parse_file(PLANS / "sheet_fa101.dxf", test_cfg)
    assert tally(a) == {
        ("exit_sign", "block"): 3,
        ("pull_station", "block"): 3,
        ("emergency_light", "block"): 5,
        ("exit_door", "block"): 3,
        ("smoke_detector", "block"): 4,
        ("pull_station", "paper"): 1,
        ("horn_strobe", "nested"): 1,
    }
    (paper,) = [d for d in a.devices if d.detection == "paper"]
    assert paper.location.value == "FA-101"
    unmatched = {u.raw: u.reason for u in a.unparsed if u.kind == "block"}
    assert set(unmatched) == {"CHAIR", "FA_CLUSTER"}
    assert "2 placed" in unmatched["CHAIR"] and "1 placed" in unmatched["FA_CLUSTER"]
    v = a.sheet_units["sheet_fa101.dxf"]
    assert (v.value, v.confidence) == ("mm", Confidence.MEDIUM)

    b = dxf.parse_file(PLANS / "sheet_fa102.dxf", test_cfg)
    assert tally(b) == {
        ("exit_door", "block"): 2,
        ("exit_sign", "block"): 2,
        ("pull_station", "block"): 1,
        ("emergency_light", "block"): 1,
    }
    assert not b.sheet_units["sheet_fa102.dxf"].usable


def test_plan_samples_reproducible_counts(tmp_path, test_cfg):
    import make_plan_samples

    from redline.extract.oda_ezdxf import extract_inprocess

    make_plan_samples.main(tmp_path)

    def inserts(path):
        data = extract_inprocess(path, test_cfg)
        return sorted(
            (e["layout"], e["block_name"], tuple(e.get("insertion_point") or ()))
            for e in data["entities"]
            if e["type"] == "INSERT"
        )

    for name in ("sheet_fa101.dxf", "sheet_fa102.dxf"):
        assert inserts(tmp_path / name) == inserts(PLANS / name)


# ---- matching (D1) ----


def test_name_match_trimmed_casefold(test_cfg):
    out = parse([ins(" test_exit "), ins("Test_Exit"), ins("TEST_EXIT")], test_cfg)
    assert tally(out) == {("exit_sign", "block"): 3}
    assert out.unparsed == []


def test_dynamic_source_name_counted(test_cfg):
    # The extractors write the source name; an unresolved *U name matches nothing and is listed.
    out = parse([ins("TEST_EMLT"), ins("*U12")], test_cfg)
    assert tally(out) == {("emergency_light", "block"): 1}
    assert [u.raw for u in out.unparsed if u.kind == "block"] == ["*U12"]


def test_nested_insert_not_counted(test_cfg):
    out = parse([ins("TEST_HORN", layout="block:FA_CLUSTER")], test_cfg)
    (d,) = out.devices
    assert d.detection == "nested" and d.source.confidence == Confidence.LOW
    assert "FA_CLUSTER" in d.source.note and "not counted" in d.source.note
    assert d.x.value is None and d.y.value is None


def test_xref_insert_not_counted(test_cfg):
    out = parse(
        [
            ins("TEST_PULL", layout="block:XR", xref_path="xr.dwg"),
            ins("TEST_PULL", xref_path="xr.dwg"),
        ],
        test_cfg,
    )
    assert tally(out) == {("pull_station", "nested"): 2}
    assert all("xref" in d.source.note for d in out.devices)


def test_paper_space_counted_per_layout(test_cfg):
    out = parse([ins("TEST_PULL"), ins("TEST_PULL", "FA-1"), ins("TEST_PULL", "FA-2")], test_cfg)
    got = {(d.detection, d.location.value) for d in out.devices}
    assert got == {("block", "Model"), ("paper", "FA-1"), ("paper", "FA-2")}


def test_model_space_name_without_case(test_cfg):
    out = parse([ins("TEST_PULL", layout="MODEL")], test_cfg, layouts=["MODEL"])
    assert tally(out) == {("pull_station", "block"): 1}


def test_missing_point_leaves_position_missing(test_cfg):
    out = parse([ins("TEST_PULL", at=None)], test_cfg)
    (d,) = out.devices
    assert d.x.value is None and d.y.value is None and d.detection == "block"


def test_unmatched_names_listed_with_counts(test_cfg):
    out = parse(
        [
            ins("CHAIR"),
            ins("chair", "FA-1"),
            ins("CHAIR", layout="block:PARENT"),
            ins("DESK"),
        ],
        test_cfg,
    )
    got = {u.raw.casefold(): u for u in out.unparsed if u.kind == "block"}
    assert list(got) == ["chair", "desk"]
    assert "2 placed, 1 inside block definitions or xrefs" in got["chair"].reason
    assert got["desk"].source.confidence == Confidence.LOW
    assert out.devices == []


def test_wd_m_not_listed_as_unmatched(test_cfg):
    out = parse([ins("WD_M"), ins("wd_m")], test_cfg)
    assert not [u for u in out.unparsed if u.kind == "block"]


def test_empty_config_lists_every_name(test_cfg):
    empty = {k: [] for k in test_cfg.fire_alarm["device_blocks"]}
    cfg = dataclasses.replace(test_cfg, fire_alarm={**test_cfg.fire_alarm, "device_blocks": empty})
    out = parse([ins("TEST_EXIT"), ins("TEST_PULL"), ins("CHAIR")], cfg)
    assert out.devices == []
    names = sorted(u.raw for u in out.unparsed if u.kind == "block")
    assert names == ["CHAIR", "TEST_EXIT", "TEST_PULL"]


def test_blocks_not_listed_by_plain_parse(test_cfg):
    out = dxf.parse_rawdrawing(sheet([ins("CHAIR")]), test_cfg, list_blocks=False)
    assert out.unparsed == []


# ---- units (D7) ----


@pytest.mark.parametrize(
    ("word", "unit"),
    [
        ("mm", "mm"),
        ("millimeters", "mm"),
        ("Feet", "ft"),
        ("ft", "ft"),
        ("inches", "in"),
        ("cm", "cm"),
        ("centimeters", "cm"),
        ("m", "m"),
        ("meters", "m"),
    ],
)
def test_drawing_units_both_spellings(test_cfg, word, unit):
    out = parse([], test_cfg, units=word)
    v = out.sheet_units["s.dxf"]
    assert (v.value, v.raw, v.confidence) == (unit, word, Confidence.MEDIUM)
    assert v.usable and "declared in the drawing header" in v.source.note


@pytest.mark.parametrize("word", ["unitless", "undefined", "", "parsecs", None])
def test_unitless_sheet_units_not_usable(test_cfg, word):
    data = sheet([], units=word)
    if word is None:
        del data["document"]["units"]
    out = dxf.parse_rawdrawing(data, test_cfg, list_blocks=False)
    v = out.sheet_units["s.dxf"]
    assert v.value is None and not v.usable
    assert v.confidence == Confidence.LOW and "not stated" in v.source.note
