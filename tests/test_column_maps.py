from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "config" / "column_maps.yaml"
TEST = ROOT / "tests" / "test_config" / "column_maps.yaml"

REVIT = {
    "circuit number": "circuit_number",
    "load name": "description",
    "rating": "breaker_a",
    "number of poles": "poles",
    "load classification": "load_type",
    "apparent power": "load_va",
    "panel": "panel_name",
    "voltage": "voltage_v",
}


def _csv(path: Path) -> dict[str, list[str]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["csv_panel_schedule"]


def test_test_and_real_maps_match():
    assert _csv(TEST) == _csv(REAL)


def test_revit_documented_names_are_aliases():
    for alias, key in REVIT.items():
        assert alias in _csv(REAL)[key], alias
        assert alias in _csv(TEST)[key], alias


def test_no_alias_under_two_keys():
    for path in (REAL, TEST):
        seen: dict[str, str] = {}
        for key, aliases in _csv(path).items():
            for alias in aliases:
                assert alias == alias.lower()
                assert seen.setdefault(alias, key) == key, alias


def test_wire_sz_not_an_alias():
    for path in (REAL, TEST):
        for aliases in _csv(path).values():
            assert "wire sz" not in aliases
            assert "sz" not in aliases


def test_notes_not_an_alias():
    for path in (REAL, TEST):
        for aliases in _csv(path).values():
            assert "notes" not in aliases


def test_phase_label_not_mapped():
    for path in (REAL, TEST):
        homes = [k for k, v in _csv(path).items() if "phase label" in v]
        assert homes == ["not_mapped"]


def test_dxf_parsing_keys_match():
    keys = (
        "dxf_table_min_cells",
        "dxf_stale_field_policy",
        "dxf_prefer_extractor",
        "dxf_extractor_timeout_s",
        "row_tolerance_text_heights",
        "column_gap_fraction",
        "accoreconsole_path",
        "acad_plugin_dll",
        "odafc_path",
    )
    real, test = (yaml.safe_load(p.read_text(encoding="utf-8"))["parsing"] for p in (REAL, TEST))
    for key in keys:
        assert key in real and key in test, key
    for key in keys[:6]:
        assert real[key] == test[key], key
    assert all(test[k] is None for k in keys[6:])


def test_pdf_parsing_keys_match():
    keys = (
        "pdf_text_page_min_chars",
        "pdf_scanned_image_area_fraction",
        "pdf_row_tolerance_word_heights",
        "pdf_column_gap_fraction",
        "pdf_region_gap_word_heights",
        "pdf_title_block_width_fraction",
        "pdf_title_block_height_fraction",
        "pdf_timeout_s",
    )
    real, test = (yaml.safe_load(p.read_text(encoding="utf-8")) for p in (REAL, TEST))
    for key in keys:
        assert key in real["parsing"] and key in test["parsing"], key
        assert real["parsing"][key] == test["parsing"][key], key
    assert real["title_block"] == test["title_block"]
