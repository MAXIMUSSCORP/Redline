from __future__ import annotations

import re

MATERIAL_TABLE_KEY: dict[str, str] = {"Cu": "copper", "Al": "aluminum"}

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
