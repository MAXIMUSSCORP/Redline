import pytest

from redline.units import MATERIAL_TABLE_KEY, normalize_size


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#12", "12 AWG"),
        ("12AWG", "12 AWG"),
        ("12 AWG", "12 AWG"),
        ("2/0", "2/0 AWG"),
        ("#2/0", "2/0 AWG"),
        ("2/0 AWG", "2/0 AWG"),
        ("250 MCM", "250 kcmil"),
        ("250MCM", "250 kcmil"),
        ("250kcmil", "250 kcmil"),
        ("250 kcmil", "250 kcmil"),
        ("4mm2", "4 mm2"),
        ("4 mm²", "4 mm2"),
        ("  #10  ", "10 AWG"),
    ],
)
def test_size_spellings(text, expected):
    assert normalize_size(text) == expected


@pytest.mark.parametrize(
    "text", ["", "wire", "12", "250", "5/0", "0/0", "12 mm", "#", "250/0 MCM", "1.5 AWG", "abc AWG"]
)
def test_unknown_size_returns_none(text):
    assert normalize_size(text) is None


def test_material_table_key():
    assert MATERIAL_TABLE_KEY == {"Cu": "copper", "Al": "aluminum"}
