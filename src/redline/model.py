from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, fields, replace
from enum import IntEnum, StrEnum
from typing import Any


class Confidence(IntEnum):
    MISSING = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Method(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    DXF_TABLE = "dxf_table"
    DXF_ATTRIB = "dxf_attrib"
    DXF_TEXT = "dxf_text"
    DXF_BLOCK = "dxf_block"
    PDF_TEXT = "pdf_text"
    PDF_ANNOT = "pdf_annot"
    OCR = "ocr"
    VLM = "vlm"
    DETECTOR = "detector"
    DERIVED = "derived"


DETECTIONS = ("list", "block", "paper", "nested", "unused", "detector")
LOAD_TYPES = ("continuous", "noncontinuous", "motor", "receptacle", "spare", "unknown")
UNPARSED_KINDS = ("column", "row", "table", "page", "sheet", "xref", "layout", "block")


@dataclass(frozen=True)
class Source:
    file: str
    locator: str
    method: Method
    confidence: Confidence
    note: str = ""
    crop_path: str | None = None
    model: str | None = None
    extractor: str | None = None


@dataclass(frozen=True)
class Value[T]:
    value: T | None
    source: Source | None
    raw: str | None = None

    @property
    def confidence(self) -> Confidence:
        return Confidence.MISSING if self.source is None else self.source.confidence

    @property
    def usable(self) -> bool:
        if isinstance(self.value, float) and not math.isfinite(self.value):
            return False
        return self.confidence >= Confidence.MEDIUM and self.value is not None

    @staticmethod
    def missing() -> Value:
        return Value(None, None)


def derived(value: Any, inputs: Sequence[Value], file: str, locator: str, note: str = "") -> Value:
    low = min((i.confidence for i in inputs), default=Confidence.HIGH)
    if low == Confidence.MISSING:
        return Value.missing()
    return Value(value, Source(file, locator, Method.DERIVED, low, note))


def _v() -> Any:
    return field(default_factory=Value.missing)


@dataclass
class Circuit:
    panel: str
    number: str
    source: Source
    poles: Value[int] = _v()
    phases_used: Value[str] = _v()
    breaker_a: Value[float] = _v()
    conductor_size: Value[str] = _v()
    conductor_material: Value[str] = _v()
    insulation_temp_c: Value[int] = _v()
    conductors_in_raceway: Value[int] = _v()
    ambient_c: Value[float] = _v()
    length_m: Value[float] = _v()
    load_va: Value[float] = _v()
    load_type: Value[str] = _v()
    description: Value[str] = _v()
    bonding_size: Value[str] = _v()
    voltage_v: Value[float] = _v()
    is_spare: bool = False


@dataclass
class Panel:
    name: str
    source: Source
    voltage_v: Value[float] = _v()
    phases: Value[int] = _v()
    wires: Value[int] = _v()
    bus_rating_a: Value[float] = _v()
    main_breaker_a: Value[float] = _v()
    fed_from: Value[str] = _v()
    location: Value[str] = _v()
    demand_va_supplied: Value[float] = _v()
    circuits: list[Circuit] = field(default_factory=list)


@dataclass
class Feeder:
    id: str
    source: Source
    from_panel: Value[str] = _v()
    to_panel: Value[str] = _v()
    ocpd_a: Value[float] = _v()
    conductor_size: Value[str] = _v()
    conductor_material: Value[str] = _v()
    insulation_temp_c: Value[int] = _v()
    sets_in_parallel: Value[int] = _v()
    conductors_in_raceway: Value[int] = _v()
    ambient_c: Value[float] = _v()
    length_m: Value[float] = _v()
    voltage_v: Value[float] = _v()
    phases: Value[int] = _v()
    bonding_size: Value[str] = _v()
    load_va: Value[float] = _v()


@dataclass
class Device:
    type: str
    source: Source
    tag: Value[str] = _v()
    location: Value[str] = _v()
    sheet: Value[str] = _v()
    circuit: Value[str] = _v()
    x: Value[float] = _v()
    y: Value[float] = _v()
    detection: str = "list"


@dataclass
class EgressPath:
    name: str
    sheet: str
    source: Source  # HIGH from paths.csv; LOW when a vertex is bad
    points: list[tuple[float, float]] = field(default_factory=list)  # drawing units, seq order


@dataclass
class Unparsed:
    kind: str
    raw: str
    reason: str
    source: Source


@dataclass
class CoverageEntry:
    file: str
    unit: str
    what_read: str
    method: str
    confidence_summary: str


@dataclass
class RunInfo:
    tool_version: str
    config_hashes: dict[str, str] = field(default_factory=dict)
    extractor_versions: dict[str, str] = field(default_factory=dict)
    model_ids_versions_hashes: list[str] = field(default_factory=list)
    seeds: dict[str, int] = field(default_factory=dict)
    input_tool_version: str = ""  # set by the CLI from the input's tool_version
    input_config_hashes: dict[str, str] = field(default_factory=dict)  # set by the CLI


@dataclass
class Project:
    name: str
    code_edition: str = ""
    inputs: list[str] = field(default_factory=list)
    panels: list[Panel] = field(default_factory=list)
    feeders: list[Feeder] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)
    paths: list[EgressPath] = field(default_factory=list)
    sheet_units: dict[str, Value] = field(
        default_factory=dict
    )  # sheet -> mm, cm, m, in, ft or None
    unparsed: list[Unparsed] = field(default_factory=list)
    coverage: list[CoverageEntry] = field(default_factory=list)
    run_info: RunInfo | None = None


MAX_SHOWN = 80


def clip(text: object, limit: int = MAX_SHOWN) -> str:
    """Display only: cap the text a finding quotes. Never use it for identity or lookups."""
    s = str(text)
    return s if len(s) <= limit else s[:limit] + "…"


def label(unit: Panel | Circuit | Feeder) -> str:
    if isinstance(unit, Panel):
        return clip(unit.name)
    if isinstance(unit, Circuit):
        return f"{clip(unit.panel)} ckt {clip(unit.number, 20)}"
    return f"Feeder {clip(unit.id)}"


def effective_voltage(c: Circuit, p: Panel) -> Value:
    # A voltage the circuit showed stays its own, even when it did not parse.
    if c.voltage_v.value is not None or c.voltage_v.raw:
        return c.voltage_v
    # Panel voltage is line to line. Only a circuit of 2 or more poles sees it.
    if c.poles.usable and isinstance(c.poles.value, int | float) and c.poles.value >= 2:
        return p.voltage_v
    return Value.missing()


def is_mlo(p: Panel) -> bool:
    m = p.main_breaker_a
    return m.value is None and m.source is not None and m.source.note == "MLO"


_AI_METHODS = (Method.OCR, Method.VLM, Method.DETECTOR)


def _dict(d: Any, what: str) -> dict:
    if not isinstance(d, dict):
        raise TypeError(f"{what} must be an object")
    return d


_SOURCE_KEYS = {f.name for f in fields(Source)}
_VALUE_KEYS = {"value", "source", "raw"}
# Numeric fields that may be negative. Every other number must be zero or more.
_SIGNED = {"ambient_c", "x", "y"}
# The inner type of every Value field, read from the dataclass hints so a new field is covered.
_VTYPE = {
    f.name: f.type[6:-1]
    for cls in (Panel, Circuit, Feeder, Device)
    for f in fields(cls)
    if f.type.startswith("Value[")
}
# Ratings and divisors: zero is not a reading.
_NONZERO = {
    "breaker_a",
    "ocpd_a",
    "voltage_v",
    "sets_in_parallel",
    "bus_rating_a",
    "main_breaker_a",
    "demand_va_supplied",
}
MAX_INT = 2**53
MAX_CKT_DIGITS = 6  # a circuit number longer than this is not a position


def check_value(name: str, v: Value) -> Value:
    """The one semantic check on a Value: wrong type raises, a bad reading becomes LOW.

    The JSON loader calls it for every Value. M1 parsers must call it too.
    """
    val, kind = v.value, _VTYPE.get(name)
    why = ""
    if val is not None and kind == "str":
        if not isinstance(val, str):
            raise TypeError(f"{name} must be a string")
    elif val is not None and kind in ("int", "float"):
        if isinstance(val, bool) or not isinstance(val, int | float):
            raise TypeError(f"{name} must be a number")
        if isinstance(val, int) and abs(val) > MAX_INT:
            raise TypeError(f"{name} is too large a number")
        if not math.isfinite(val):
            why = "not a finite number"
        elif abs(val) > MAX_INT:
            why = "too large a number"
        elif kind == "int" and val != int(val):
            why = "not a whole number"
        elif val < 0 and name not in _SIGNED:
            why = "negative quantity"
        elif val == 0 and name in _NONZERO:
            why = "zero"
        elif name == "poles" and val not in (1, 2, 3):
            why = "poles not 1, 2 or 3"
        elif name == "phases" and val not in (1, 3):
            why = "phases not 1 or 3"
    if kind == "str" and name == "load_type" and val is not None and val not in LOAD_TYPES:
        why = "not a known load type"
    if not why or v.source is None:
        return v
    note = f"{v.source.note}; {why}" if v.source.note else why
    low = replace(v.source, confidence=min(v.source.confidence, Confidence.LOW), note=note)
    return replace(v, source=low)


def _text(v: Any, what: str, required: bool = False) -> Any:
    if not (isinstance(v, str) or (v is None and not required)):
        raise TypeError(f"{what} must be a string")
    return v


def _check_keys(d: dict, allowed: set[str], what: str) -> None:
    if unknown := sorted(set(d) - allowed):
        raise ValueError(f"unknown key in {what}: {', '.join(unknown)}")


def _source(d: Any) -> Source:
    d = _dict(d, "source")
    _check_keys(d, _SOURCE_KEYS, "source")
    method = Method(d["method"])
    conf = Confidence[d["confidence"]]
    # A source that names a model is AI-derived, whatever its method says.
    if method in _AI_METHODS or d.get("model") is not None:
        conf = min(conf, Confidence.LOW)
    return Source(
        file=_text(d["file"], "source file", True),
        locator=_text(d["locator"], "source locator", True),
        method=method,
        confidence=conf,
        note=_text(d.get("note", ""), "source note") or "",
        crop_path=_text(d.get("crop_path"), "source crop_path"),
        model=_text(d.get("model"), "source model"),
        extractor=_text(d.get("extractor"), "source extractor"),
    )


def _value(d: Any, name: str = "") -> Value:
    if d is None:
        return Value.missing()
    d = _dict(d, "value")
    _check_keys(d, _VALUE_KEYS, "value")
    val = d.get("value")
    if isinstance(val, bool):
        raise TypeError("value must not be true or false")
    src = d.get("source")
    out = Value(val, None if src is None else _source(src), _text(d.get("raw"), "value raw"))
    return check_value(name, out)


def _build(cls: type, d: Any, extra: tuple[str, ...] = ()) -> Any:
    d = _dict(d, cls.__name__)
    names = {f.name for f in fields(cls)}
    if unknown := sorted(set(d) - names - set(extra)):
        raise ValueError(f"unknown key in {cls.__name__}: {', '.join(unknown)}")
    kw: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in d:
            continue
        raw = d[f.name]
        if f.name == "source":
            kw[f.name] = _source(raw)
        elif f.default_factory == Value.missing:
            kw[f.name] = _value(raw, f.name)
        elif f.type == "bool":
            if not isinstance(raw, bool):
                raise TypeError(f"{f.name} must be true or false")
            kw[f.name] = raw
        else:
            kw[f.name] = _text(raw, f.name, True)
    return cls(**kw)


def _list(d: dict, key: str) -> list:
    v = d.get(key, [])
    if not isinstance(v, list):
        raise TypeError(f"{key} must be a list")
    return v


def _run_info(ri: Any) -> RunInfo:
    ri = _dict(ri, "run_info")
    _check_keys(ri, {f.name for f in fields(RunInfo)}, "run_info")
    for k in ("input_tool_version", "input_config_hashes"):
        if k in ri:
            raise ValueError(f"unknown key in run_info: {k}")
    out = RunInfo(**ri)
    maps = (out.config_hashes, out.extractor_versions, out.seeds)
    if not (
        isinstance(out.tool_version, str)
        and all(isinstance(m, dict) and all(isinstance(k, str) for k in m) for m in maps)
        and all(isinstance(v, str) for m in maps[:2] for v in m.values())
        and all(isinstance(v, int) and not isinstance(v, bool) for v in out.seeds.values())
        and isinstance(out.model_ids_versions_hashes, list)
        and all(isinstance(m, str) for m in out.model_ids_versions_hashes)
    ):
        raise TypeError("run_info has a value of the wrong type")
    texts = [out.tool_version, *out.model_ids_versions_hashes]
    for m in maps:
        texts += [*m, *(v for v in m.values() if isinstance(v, str))]
    if not all(t.strip() for t in texts):
        raise ValueError("run_info has an empty text")
    return out


_PROJECT_KEYS = {f.name for f in fields(Project)}


def project_from_dict(data: Any) -> Project:
    data = _dict(data, "project")
    # A lone surrogate cannot be written out as UTF-8. Refuse it here, wherever it sits.
    json.dumps(data, ensure_ascii=False).encode("utf-8")
    if refused := sorted({"paths", "sheet_units"} & set(data)):
        raise ValueError(f"{', '.join(refused)} not read from a demo project")
    if unknown := sorted(set(data) - _PROJECT_KEYS):
        raise ValueError(f"unknown key in project: {', '.join(unknown)}")
    panels = []
    for pd in _list(data, "panels"):
        p = _build(Panel, {k: v for k, v in _dict(pd, "Panel").items() if k != "circuits"})
        p.circuits = [_build(Circuit, c) for c in _list(pd, "circuits")]
        if (bad := next((c.panel for c in p.circuits if c.panel != p.name), None)) is not None:
            raise ValueError(f"circuit names panel {bad} but sits under panel {p.name}")
        panels.append(p)
    feeders = [_build(Feeder, f) for f in _list(data, "feeders")]
    for kind, names in (
        ("panel name", [p.name for p in panels]),
        ("feeder id", [f.id for f in feeders]),
    ):
        if dup := next((n for n, k in Counter(names).items() if k > 1), None):
            raise ValueError(f"repeated {kind}: {dup}")
    devices = [_build(Device, x) for x in _list(data, "devices")]
    if bad := next((d.detection for d in devices if d.detection not in DETECTIONS), None):
        raise ValueError(f"unknown detection: {bad}")
    ri = data.get("run_info")
    return Project(
        name=_text(data["name"], "project name", True),
        code_edition=_text(data.get("code_edition", ""), "code_edition", True),
        inputs=[_text(i, "input", True) for i in _list(data, "inputs")],
        panels=panels,
        feeders=feeders,
        devices=devices,
        unparsed=[_build(Unparsed, u) for u in _list(data, "unparsed")],
        coverage=[_build(CoverageEntry, c) for c in _list(data, "coverage")],
        run_info=_run_info(ri) if ri is not None else None,
    )
