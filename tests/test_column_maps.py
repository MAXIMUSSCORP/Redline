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
