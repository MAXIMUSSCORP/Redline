"""Compares what the two DWG extractors read from the same drawing, as a loss table.

`diff` and `format_table` are pure. `run` takes the extractor functions as an argument,
and by default imports the two real ones when they are first called, so importing this
module needs no CAD software.
"""

from __future__ import annotations

import importlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from redline.config import Config

Extractor = Callable[[Path, Config], dict]
_NOT_RUN = "not run"


@dataclass(frozen=True)
class LossRow:
    file: str
    item: str
    primary: int | None  # None when that extractor did not run
    fallback: int | None


def _list(x: Any) -> list:
    return x if isinstance(x, list) else []


def _tables(d: dict) -> dict[str, dict]:
    out = {}
    for e in _list(d.get("entities")):
        t = e.get("table") if isinstance(e, dict) else None
        if isinstance(t, dict) and e.get("handle") is not None:
            out[str(e["handle"])] = t
    return out


def _cells(t: dict) -> dict[tuple, dict]:
    return {(c.get("r"), c.get("c")): c for c in _list(t.get("cells")) if isinstance(c, dict)}


def _counts(d: dict) -> dict[str, int]:
    ents = [e for e in _list(d.get("entities")) if isinstance(e, dict)]
    n: Counter[str] = Counter(str(e.get("type")) for e in ents)
    tabs = list(_tables(d).values())
    cells = [c for t in tabs for c in _list(t.get("cells")) if isinstance(c, dict)]
    n.update(
        {
            "tables": len(tabs),
            "cells": len(cells),
            "cells evaluated": sum(1 for c in cells if c.get("evaluated") is True),
            "attributes": sum(len(_list(e.get("attributes"))) for e in ents),
        }
    )
    return dict(n)


def _text_differences(a: dict, b: dict) -> int:
    ta, tb = _tables(a), _tables(b)
    n = 0
    for h in ta.keys() & tb.keys():
        if (ta[h].get("rows"), ta[h].get("cols")) != (tb[h].get("rows"), tb[h].get("cols")):
            continue
        ca, cb = _cells(ta[h]), _cells(tb[h])
        n += sum(1 for k in ca.keys() & cb.keys() if ca[k].get("text") != cb[k].get("text"))
    return n


def diff(file: str, primary: dict | None, fallback: dict | None) -> list[LossRow]:
    a = _counts(primary) if primary is not None else None
    b = _counts(fallback) if fallback is not None else None
    items = sorted(
        {*(a or {}), *(b or {})} - {"tables", "cells", "cells evaluated", "attributes"}
    ) + ["tables", "cells", "cells evaluated", "attributes"]
    rows = [
        LossRow(
            file, i, a.get(i, 0) if a is not None else None, b.get(i, 0) if b is not None else None
        )
        for i in items
    ]
    if primary is not None and fallback is not None:
        n = _text_differences(primary, fallback)
        rows.append(LossRow(file, "cell text differs", n, n))
    return rows


def format_table(rows: list[LossRow], names: tuple[str, str] = ("primary", "fallback")) -> str:
    def cell(x: int | None) -> str:
        return _NOT_RUN if x is None else str(x)

    body = [(r.file, r.item, cell(r.primary), cell(r.fallback)) for r in rows]
    head = ("file", "item", names[0], names[1])
    w = [max(len(r[i]) for r in [head, *body]) for i in range(4)]
    lines = [
        "  ".join(v.ljust(w[i]) if i < 2 else v.rjust(w[i]) for i, v in enumerate(r)).rstrip()
        for r in [head, *body]
    ]
    return "\n".join(lines)


def _default_extractors() -> dict[str, Extractor]:
    def lazy(module: str) -> Extractor:
        return lambda p, cfg: importlib.import_module(module).extract(p, cfg)

    return {
        "acad_plugin": lazy("redline.extract.acad_console"),
        "oda_ezdxf": lazy("redline.extract.oda_ezdxf"),
    }


def run(
    paths: list[Path], cfg: Config, extractors: dict[str, Extractor] | None = None
) -> tuple[str, int]:
    """Returns (text, exit code). Exit 2 only when no extractor read any file."""
    fns = extractors if extractors is not None else _default_extractors()
    names = list(fns)[:2]
    if len(names) != 2:
        raise ValueError("xcheck needs exactly two extractors")
    rows: list[LossRow] = []
    reasons: list[str] = []
    read = 0
    for path in paths:
        path = Path(path)
        got: list[dict | None] = []
        for name in names:
            try:
                d = fns[name](path, cfg)
                if not isinstance(d, dict):
                    raise TypeError("the extractor returned no RawDrawing")
            except Exception as e:  # noqa: BLE001 - any failure is reported, never hidden
                got.append(None)
                reasons.append(f"{path.name}: {name} read nothing: {type(e).__name__}: {e}")
            else:
                got.append(d)
                read += 1
        rows += diff(path.name, got[0], got[1])
    text = format_table(rows, (names[0], names[1]))
    if reasons:
        text += "\n\n" + "\n".join(reasons)
    return text, (0 if read else 2)
