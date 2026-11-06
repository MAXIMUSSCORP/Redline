from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
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
    PDF_TEXT = "pdf_text"
    PDF_ANNOT = "pdf_annot"
    OCR = "ocr"
    VLM = "vlm"
    DETECTOR = "detector"
    DERIVED = "derived"


LOAD_TYPES = ("continuous", "noncontinuous", "motor", "receptacle", "spare", "unknown")
UNPARSED_KINDS = ("column", "row", "table", "page", "sheet", "xref", "layout")


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


@dataclass
class Project:
    name: str
    code_edition: str = ""
    inputs: list[str] = field(default_factory=list)
    panels: list[Panel] = field(default_factory=list)
    feeders: list[Feeder] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)
    unparsed: list[Unparsed] = field(default_factory=list)
    coverage: list[CoverageEntry] = field(default_factory=list)
    run_info: RunInfo | None = None


def label(unit: Panel | Circuit | Feeder) -> str:
    if isinstance(unit, Panel):
        return unit.name
    if isinstance(unit, Circuit):
        return f"{unit.panel} ckt {unit.number}"
    return f"Feeder {unit.id}"


def effective_voltage(c: Circuit, p: Panel) -> Value:
    if c.voltage_v.value is not None:
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


def _source(d: Any) -> Source:
    d = _dict(d, "source")
    method = Method(d["method"])
    conf = Confidence[d["confidence"]]
    if method in _AI_METHODS:
        conf = min(conf, Confidence.LOW)
    return Source(
        file=d["file"],
        locator=d["locator"],
        method=method,
        confidence=conf,
        note=d.get("note", ""),
        crop_path=d.get("crop_path"),
        model=d.get("model"),
        extractor=d.get("extractor"),
    )


def _value(d: Any) -> Value:
    if not d:
        return Value.missing()
    d = _dict(d, "value")
    src = d.get("source")
    return Value(d.get("value"), _source(src) if src else None, d.get("raw"))


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
            kw[f.name] = _value(raw)
        else:
            kw[f.name] = raw
    return cls(**kw)


def _list(d: dict, key: str) -> list:
    v = d.get(key, [])
    if not isinstance(v, list):
        raise TypeError(f"{key} must be a list")
    return v


_PROJECT_KEYS = {f.name for f in fields(Project)}


def project_from_dict(data: Any) -> Project:
    data = _dict(data, "project")
    if unknown := sorted(set(data) - _PROJECT_KEYS):
        raise ValueError(f"unknown key in project: {', '.join(unknown)}")
    panels = []
    for pd in _list(data, "panels"):
        p = _build(Panel, {k: v for k, v in _dict(pd, "Panel").items() if k != "circuits"})
        p.circuits = [_build(Circuit, c) for c in _list(pd, "circuits")]
        panels.append(p)
    ri = data.get("run_info")
    return Project(
        name=data["name"],
        code_edition=data.get("code_edition", ""),
        inputs=list(_list(data, "inputs")),
        panels=panels,
        feeders=[_build(Feeder, f) for f in _list(data, "feeders")],
        devices=[_build(Device, x) for x in _list(data, "devices")],
        unparsed=[_build(Unparsed, u) for u in _list(data, "unparsed")],
        coverage=[CoverageEntry(**_dict(c, "coverage")) for c in _list(data, "coverage")],
        run_info=RunInfo(**_dict(ri, "run_info")) if ri else None,
    )
