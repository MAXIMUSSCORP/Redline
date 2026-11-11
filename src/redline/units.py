from __future__ import annotations

import re

MATERIAL_TABLE_KEY: dict[str, str] = {"Cu": "copper", "Al": "aluminum"}

METRES_PER_UNIT = {
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "in": 0.0254,
    "ft": 0.3048,
}  # unit definitions
# AutoCAD UnitsValue names (lower case) and the short words ezdxf writes. UNVERIFIED until live dumps.
_ALIASES = {"millimeters": "mm", "centimeters": "cm", "meters": "m", "inches": "in", "feet": "ft"}
LENGTH_TOLERANCE_M = 1e-9  # float noise when two coverage stretches touch; not a code value

_SIZE = re.compile(r"(\d+(?:\.\d+)?(?:/0)?)\s*(awg|mcm|kcmil|mm2)?")


def normalize_size(text: str) -> str | None:
    """Canonical conductor size, or None. A bare integer is not guessed."""
    t = text.strip().lower().replace("²", "2")
    hashed = t.startswith("#")
    m = _SIZE.fullmatch(t.lstrip("#").strip())
    if not m:
        return None
    num, unit = m.groups()
    if unit in ("mcm", "kcmil"):
        return f"{num} kcmil" if num.isdigit() and int(num) > 0 else None
    if unit == "mm2":
        return f"{num} mm2" if "/" not in num and float(num) > 0 else None
    if num.endswith("/0"):
        return f"{num} AWG" if num[:-2] in ("1", "2", "3", "4") else None
    if unit is None and not hashed:
        return None
    return f"{num} AWG" if num.isdigit() and 1 <= int(num) <= 40 else None


def length_unit(word: str | None) -> str | None:
    """A short length unit (mm, cm, m, in, ft), or None. Unitless and unknown words are not guessed."""
    if word is None:
        return None
    w = word.strip().casefold()
    w = _ALIASES.get(w, w)
    return w if w in METRES_PER_UNIT else None
