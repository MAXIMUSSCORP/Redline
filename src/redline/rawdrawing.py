from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "1.0"
ENTITY_TYPES = frozenset(
    {"TEXT", "MTEXT", "INSERT", "ATTRIB", "ACAD_TABLE", "MLEADER", "LINE", "POLYLINE"}
)
_TOP = (
    "schema_version",
    "extractor",
    "extractor_version",
    "host_version",
    "source_file",
    "source_sha256",
    "extracted_at",
    "document",
    "entities",
)
_DOC = ("units", "layouts", "xrefs", "warnings")


@dataclass(frozen=True)
class Validation:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _version(text: Any) -> tuple[int, int] | None:
    try:
        major, minor = str(text).split(".")
        return int(major), int(minor)
    except ValueError:
        return None


def _bbox(where: str, bbox: Any, errors: list[str]) -> None:
    if not (isinstance(bbox, list) and len(bbox) == 4 and all(_num(n) for n in bbox)):
        errors.append(f"{where}.bbox must be 4 numbers")
    elif bbox[0] > bbox[2] or bbox[1] > bbox[3]:
        errors.append(f"{where}.bbox must have x1 <= x2 and y1 <= y2")


def _table(where: str, table: Any, errors: list[str]) -> None:
    if not isinstance(table, dict):
        errors.append(f"{where}.table must be an object")
        return
    rows, cols = table.get("rows"), table.get("cols")
    if not (_int(rows) and _int(cols)):
        errors.append(f"{where}.table rows and cols must be integers")
        return
    cells = table.get("cells")
    if not isinstance(cells, list):
        errors.append(f"{where}.table.cells must be a list")
        return
    for j, cell in enumerate(cells):
        w = f"{where}.table.cells[{j}]"
        if not isinstance(cell, dict):
            errors.append(f"{w} must be an object")
            continue
        r, c = cell.get("r"), cell.get("c")
        if not (_int(r) and _int(c) and 0 <= r < rows and 0 <= c < cols):
            errors.append(f"{w} needs integer r and c within the table size")
        if not isinstance(cell.get("text"), str):
            errors.append(f"{w}.text must be a string")
        if not isinstance(cell.get("evaluated"), bool):
            errors.append(f"{w}.evaluated must be true or false")


def validate(data: Any) -> Validation:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return Validation(("RawDrawing must be a JSON object",), ())
    for k in _TOP:
        if k not in data:
            errors.append(f"missing required field {k}")
    got = _version(data.get("schema_version"))
    want = _version(SCHEMA_VERSION)
    if "schema_version" in data:
        if got is None or want is None:
            errors.append("schema_version must look like 1.0")
        elif got[0] > want[0]:
            errors.append(
                f"schema_version {data['schema_version']} has a higher major than {SCHEMA_VERSION}"
            )
            return Validation(tuple(errors), ())
        elif got[0] == want[0] and got[1] > want[1]:
            warnings.append(
                f"schema_version {data['schema_version']} has a higher minor than {SCHEMA_VERSION}"
            )
    doc = data.get("document")
    if "document" in data:
        if not isinstance(doc, dict):
            errors.append("document must be an object")
        else:
            errors += [f"document is missing {k}" for k in _DOC if k not in doc]
    entities = data.get("entities")
    if "entities" in data and not isinstance(entities, list):
        errors.append("entities must be a list")
        entities = []
    for i, e in enumerate(entities or []):
        w = f"entities[{i}]"
        if not isinstance(e, dict):
            errors.append(f"{w} must be an object")
            continue
        for k in ("id", "layout", "handle"):
            if not isinstance(e.get(k), str) or not e[k]:
                errors.append(f"{w}.{k} must be a non-empty string")
        if e.get("type") not in ENTITY_TYPES:
            errors.append(f"{w}.type {e.get('type')!r} is not a known entity type")
        if e.get("bbox") is not None:
            _bbox(w, e["bbox"], errors)
        if e.get("table") is not None:
            _table(w, e["table"], errors)
    return Validation(tuple(errors), tuple(warnings))
