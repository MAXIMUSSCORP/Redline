from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from redline.model import MAX_INT

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
_NAMED = ("extractor", "extractor_version", "host_version", "extracted_at")
_SHA = re.compile(r"[0-9a-f]{64}")

# Design limits, not code values.
MAX_JSON_BYTES = 256 * 2**20
MAX_ENTITIES = 500_000
MAX_TABLE_CELLS = 100_000  # per table
MAX_DRAWING_CELLS = 500_000  # declared rows x cols summed over one drawing
MAX_TEXT = 10_000  # characters per text, cell, tag or value


@dataclass(frozen=True)
class Validation:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _finite(x: Any) -> bool:
    return _num(x) and math.isfinite(x)


def _int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _version(text: Any) -> tuple[int, int] | None:
    try:
        major, minor = str(text).split(".")
        return int(major), int(minor)
    except ValueError:
        return None


def _no_constant(name: str) -> None:
    raise ValueError(f"{name} is not allowed in JSON")


def _float(text: str) -> float:
    x = float(text)
    if not math.isfinite(x):
        raise ValueError(f"{text} is not a finite number")
    return x


def _big_int(text: str) -> int:
    n = int(text)
    if abs(n) > MAX_INT:
        raise ValueError(f"{text[:20]} is too large a number")
    return n


def _no_repeat(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"repeated key {k}")
        out[k] = v
    return out


def read(path: Path) -> Any:
    """Read a RawDrawing file as strict JSON. Raises ValueError."""
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"{path.name} is over MAX_JSON_BYTES ({MAX_JSON_BYTES} bytes)")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_no_constant,
            parse_float=_float,
            parse_int=_big_int,
            object_pairs_hook=_no_repeat,
        )
    except (UnicodeError, RecursionError) as e:
        raise ValueError(f"{path.name} cannot be read as JSON ({type(e).__name__})") from e


def _str(where: str, x: Any, errors: list[str], *, empty: bool = True) -> None:
    if not isinstance(x, str) or not (empty or x):
        errors.append(f"{where} must be {'a string' if empty else 'a non-empty string'}")
    elif len(x) > MAX_TEXT:
        errors.append(f"{where} is over MAX_TEXT ({MAX_TEXT} characters)")


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
    counted = _int(rows) and _int(cols) and rows >= 0 and cols >= 0
    if not counted and not (rows is None and cols is None):
        errors.append(f"{where}.table rows and cols must be both integers or both null")
        return
    cells = table.get("cells")
    if not isinstance(cells, list):
        errors.append(f"{where}.table.cells must be a list")
        return
    if len(cells) > MAX_TABLE_CELLS:
        errors.append(f"{where}.table has more cells than MAX_TABLE_CELLS ({MAX_TABLE_CELLS})")
        return
    for j, cell in enumerate(cells):
        w = f"{where}.table.cells[{j}]"
        if not isinstance(cell, dict):
            errors.append(f"{w} must be an object")
            continue
        r, c = cell.get("r"), cell.get("c")
        ok = _int(r) and _int(c) and r >= 0 and c >= 0
        if ok and counted:
            ok = r < rows and c < cols
        if not ok:
            limit = "within the table size" if counted else "that are not negative"
            errors.append(f"{w} needs integer r and c {limit}")
        _str(f"{w}.text", cell.get("text"), errors)
        if not isinstance(cell.get("evaluated"), bool):
            errors.append(f"{w}.evaluated must be true or false")


def _entity_fields(w: str, e: dict[str, Any], errors: list[str]) -> None:
    for k in ("text", "layer", "block_name", "xref_path"):
        if e.get(k) is not None:
            _str(f"{w}.{k}", e[k], errors)
    h = e.get("text_height")
    if h is not None and not (_finite(h) and h > 0):
        errors.append(f"{w}.text_height must be a number above zero")
    p = e.get("insertion_point")
    if p is not None and not (isinstance(p, list) and len(p) in (2, 3) and all(map(_finite, p))):
        errors.append(f"{w}.insertion_point must be 2 or 3 finite numbers")
    if e.get("rotation_deg") is not None and not _finite(e["rotation_deg"]):
        errors.append(f"{w}.rotation_deg must be a finite number")
    attrs = e.get("attributes")
    if attrs is None:
        return
    if not isinstance(attrs, list):
        errors.append(f"{w}.attributes must be a list")
        return
    for j, a in enumerate(attrs):
        if not isinstance(a, dict):
            errors.append(f"{w}.attributes[{j}] must be an object")
            continue
        _str(f"{w}.attributes[{j}].tag", a.get("tag"), errors)
        _str(f"{w}.attributes[{j}].value", a.get("value"), errors)


def _top_fields(data: dict[str, Any], errors: list[str]) -> None:
    for k in _NAMED:
        if k in data:
            _str(k, data[k], errors, empty=False)
    sha = data.get("source_sha256")
    if "source_sha256" in data and not (isinstance(sha, str) and _SHA.fullmatch(sha)):
        errors.append("source_sha256 must be 64 lower-case hex characters")
    f = data.get("source_file")
    if "source_file" in data and not (isinstance(f, str) and f and not set(f) & set("/\\:")):
        errors.append("source_file must be a file name only, with no slash, backslash or colon")


def _doc_fields(doc: dict[str, Any], errors: list[str]) -> None:
    if "units" in doc:
        _str("document.units", doc["units"], errors)
    for k in ("layouts", "warnings"):
        v = doc.get(k)
        if k in doc and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            errors.append(f"document.{k} must be a list of strings")
        elif k in doc and len(v) > MAX_ENTITIES:
            errors.append(f"document.{k} has more items than MAX_ENTITIES ({MAX_ENTITIES})")
    if "xrefs" not in doc:
        return
    xr = doc["xrefs"]
    if not isinstance(xr, list):
        errors.append("document.xrefs must be a list")
        return
    for i, x in enumerate(xr):
        ok = (
            isinstance(x, dict)
            and isinstance(x.get("name"), str)
            and isinstance(x.get("path"), str)
            and isinstance(x.get("resolved"), bool)
        )
        if not ok:
            errors.append(f"document.xrefs[{i}] needs name, path and resolved (true or false)")
        else:
            for k in ("name", "path"):
                _str(f"document.xrefs[{i}].{k}", x[k], errors)


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
    _top_fields(data, errors)
    doc = data.get("document")
    if "document" in data:
        if not isinstance(doc, dict):
            errors.append("document must be an object")
        else:
            errors += [f"document is missing {k}" for k in _DOC if k not in doc]
            _doc_fields(doc, errors)
    entities = data.get("entities")
    if "entities" in data and not isinstance(entities, list):
        errors.append("entities must be a list")
        entities = []
    if len(entities or []) > MAX_ENTITIES:
        errors.append(f"entities has more items than MAX_ENTITIES ({MAX_ENTITIES})")
        entities = []
    for i, e in enumerate(entities or []):
        w = f"entities[{i}]"
        if not isinstance(e, dict):
            errors.append(f"{w} must be an object")
            continue
        for k in ("id", "layout", "handle"):
            _str(f"{w}.{k}", e.get(k), errors, empty=False)
        if e.get("type") not in ENTITY_TYPES:
            errors.append(f"{w}.type {e.get('type')!r} is not a known entity type")
        _entity_fields(w, e, errors)
        if e.get("bbox") is not None:
            _bbox(w, e["bbox"], errors)
        if e.get("table") is not None:
            _table(w, e["table"], errors)
    return Validation(tuple(errors), tuple(warnings))
