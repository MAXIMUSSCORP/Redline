"""Scores the table readers against a transcribed gold set (M6 D3, D4).

`run` reads DIR/manifest.csv, reads each source twice with the reader `redline check` uses,
pairs rows on the circuit number, and writes counts. Every metric is a measured count over
the gold set and its ratio, never a confidence on a finding.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from redline import __version__
from redline.cli import _load_inputs
from redline.config import Config
from redline.model import Confidence, Panel, Project
from redline.report.csv_out import _safe
from redline.units import normalize_size

TRUTH_HEADER = ["circuit", "description", "breaker_a", "poles", "wire", "load_va"]
COLS = TRUTH_HEADER[1:]  # circuit is the pairing key, so it is not scored
ATTR = {
    "description": "description",
    "breaker_a": "breaker_a",
    "poles": "poles",
    "wire": "conductor_size",
    "load_va": "load_va",
}
UNIT = {"breaker_a": "a", "poles": "p", "load_va": "va"}
SILENT_COLS = ("breaker_a", "wire", "load_va")
UNREADABLE = "[unreadable]"
SAFE_ID = re.compile(r"[A-Za-z0-9_.-]+")
REQUIRED = ("table_id", "source_file", "panel")
RESULT_HEADER = ["scope", "table_id", "column", "measure", "numerator", "denominator", "ratio"]
CELL_HEADER = ["table", "circuit", "column", "gold", "predicted", "confidence", "outcome"]


# --- normalization (D4), the scorer's own functions ---


def _text(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", s).casefold().split())


def _unreadable(s: str) -> bool:
    return s.strip().casefold() == UNREADABLE


def _number(s: str, unit: str) -> str:
    t = s.strip().casefold().replace(",", "").replace(" ", "")
    scale = Decimal(1)
    if unit == "va" and t.endswith("kva"):
        t, scale = t[:-3], Decimal(1000)
    elif t.endswith(unit):
        t = t[: -len(unit)]
    try:
        d = Decimal(t) * scale
    except InvalidOperation:
        return "t:" + _text(s)
    if not d.is_finite():
        return "t:" + _text(s)
    return "n:" + format(d.normalize(), "f")


def norm(col: str, s: str) -> str:
    if col == "circuit":
        return _text(s)
    if col == "description":
        return _text(s)
    if col == "wire":
        size = normalize_size(s)
        return "w:" + size if size else "t:" + _text(s)
    return _number(s, UNIT[col])


def distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def near(a: str, b: str) -> bool:
    """True when the strings are at most 1 edit apart. Lengths more than 1 apart skip the work."""
    return abs(len(a) - len(b)) <= 1 and distance(a, b) <= 1


# --- reading ---


@dataclass
class Table:
    id: str
    source: str
    panel: str
    kind: str
    tags: list[str]
    rows: list[list[str]] | None = None  # truth rows, None when not readable
    check: list[list[str]] | None = None
    bad_id: bool = False


@dataclass
class Read:
    reads: list[Project]
    seconds: float


def _rows(path: Path) -> list[list[str]] | None:
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            data = list(csv.reader(f))
    except (OSError, UnicodeDecodeError):
        return None
    if not data or [h.strip() for h in data[0]] != TRUTH_HEADER:
        return None
    return [r + [""] * (6 - len(r)) for r in data[1:] if any(c.strip() for c in r)]


def _manifest(folder: Path) -> tuple[list[Table] | None, str]:
    path = folder / "manifest.csv"
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f)
            head = [h.strip() for h in rd.fieldnames or []]
            data = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in rd]
    except (OSError, UnicodeDecodeError) as e:
        return None, f"cannot read {path}: {type(e).__name__}"
    miss = [c for c in REQUIRED if c not in head]
    if miss:
        return None, f"{path} has no column {', '.join(miss)}"
    if not data:
        return None, f"{path} has no table rows"
    ids = [r["table_id"] for r in data]
    if "" in ids or len(set(ids)) != len(ids):
        return None, f"{path} has a blank or repeated table_id"
    tables = []
    for r in sorted(data, key=lambda r: r["table_id"]):
        tags = [t.strip() for t in r.get("tags", "").split(";") if t.strip()]
        t = Table(r["table_id"], r["source_file"], r["panel"], r.get("kind", ""), tags)
        if not SAFE_ID.fullmatch(t.id) or ".." in t.id:
            t.bad_id = True  # the id names a file under truth/ and check/, so it stays inside them
            tables.append(t)
            continue
        t.rows = _rows(folder / "truth" / f"{t.id}.csv")
        ck = folder / "check" / f"{t.id}.csv"
        t.check = _rows(ck) if ck.is_file() else None
        tables.append(t)
    return tables, ""


def _read_source(path: Path, cfg: Config) -> Read:
    t0 = time.perf_counter()
    first = _load_inputs([str(path)], cfg)[0]
    seconds = time.perf_counter() - t0
    return Read([first, _load_inputs([str(path)], cfg)[0]], seconds)


def _find(project: Project, name: str) -> Panel | None:
    want = name.strip().casefold()
    return next((p for p in project.panels if p.name.strip().casefold() == want), None)


def _lists(project: Project, name: str, row: bool) -> bool:
    """True when the run lists the panel or file. ponytail: matches on the panel name and on
    whole-page, sheet and file failures only; a finer test of 'possibly incomplete' waits
    for real gold to show what it must catch."""
    n = name.strip().casefold()
    for u in project.unparsed:
        text = u.raw.casefold()  # the name is in raw; reason is free text such as "be a schedule"
        named = re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text) is not None
        if row:
            hit = u.kind == "row" and named
        else:
            hit = u.kind in ("page", "sheet") or u.reason.startswith("file not read") or named
        if hit:
            return True
    return False


# --- scoring ---


@dataclass
class Scored:
    meas: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    cells: list[list[str]] = field(default_factory=list)
    read: bool = False
    listed: bool = False
    differs: bool = False
    silent_wrong: int = 0
    silent_missing: int = 0
    not_pairable: int = 0

    def add(self, col: str, measure: str, num: int, den: int) -> None:
        m = self.meas.setdefault((col, measure), [0, 0])
        m[0] += num
        m[1] += den


def _pair(gold: list[list[str]], pred: list[str]) -> tuple[list[int | None], list[int]]:
    """Index of the paired predicted row for each gold row (None when missed), and the
    predicted rows nobody paired. Repeated numbers pair in order of appearance."""
    free: dict[str, list[int]] = defaultdict(list)
    for i, n in enumerate(pred):
        free[_text(n)].append(i)
    out: list[int | None] = []
    for g in gold:
        key = _text(g[0])
        out.append(None if _unreadable(g[0]) or not free[key] else free[key].pop(0))
    return out, sorted(i for v in free.values() for i in v)


def _score(t: Table, rd: Read) -> Scored:
    s = Scored()
    gold = t.rows or []
    a, b = rd.reads
    pa, pb = _find(a, t.panel), _find(b, t.panel)
    s.differs = (
        repr(pa) != repr(pb)
        if pa is not None or pb is not None
        else repr(a.unparsed) != repr(b.unparsed)
    )
    s.read = pa is not None
    circuits = pa.circuits if pa else []
    paired, extra = _pair(gold, [c.number for c in circuits])
    s.listed = not s.read and _lists(a, t.panel, False)
    row_listed = s.listed if not s.read else _lists(a, t.panel, True)
    # D14: an unkeyed gold row and a leftover predicted row may be one row; the scorer cannot say
    unkeyed = sum(1 for g in gold if _unreadable(g[0]))
    n = min(unkeyed, len(extra))
    s.not_pairable = n
    keyed_missed = sum(
        1 for g, p in zip(gold, paired, strict=True) if p is None and not _unreadable(g[0])
    )
    missed = keyed_missed + unkeyed - n
    s.silent_missing = 0 if row_listed else missed
    s.add("rows", "row_recall", len(gold) - n - missed, len(gold) - n)
    s.add("rows", "row_hallucination", len(extra) - n, len(circuits) - n)
    s.add("rows", "silent_missing_row", s.silent_missing, len(gold) - n)
    s.add("rows", "gold_row_not_pairable", n, len(gold))
    for g, p in zip(gold, paired, strict=True):
        if _unreadable(g[0]):
            continue
        c = circuits[p] if p is not None else None
        for col in COLS:
            gt = g[TRUTH_HEADER.index(col)]
            if _unreadable(gt):
                continue
            v = getattr(c, ATTR[col]) if c else None
            has = v is not None and v.value is not None and str(v.value).strip() != ""
            conf = v.confidence if v is not None else None
            shown = str(v.value) if has else ((v.raw or "") if v is not None else "")
            if c is None:
                out = "not read"
            elif not has:
                out = "correct" if gt.strip() == "" else "not read"
            elif norm(col, gt) == norm(col, str(v.value)) and gt.strip() != "":
                out = "correct"
            else:
                out = "wrong"
            surfaced = (
                row_listed
                if c is None
                else conf is not None and conf <= Confidence.LOW  # LOW or MISSING
            )
            wrong_at = conf.name.lower() if out == "wrong" else ""
            hits = {
                "cell_correct": out == "correct",
                "cell_wrong": out == "wrong",
                "cell_not_read": out == "not read",
                "surfaced": surfaced,
                **{f"wrong_{n.name.lower()}": wrong_at == n.name.lower() for n in Confidence},
            }
            if col in SILENT_COLS:
                silent = out == "wrong" and conf >= Confidence.MEDIUM
                hits["silent_wrong_pass"] = silent
                s.silent_wrong += silent
            for m, h in hits.items():
                s.add(col, m, int(h), 1)
                s.add("all", m, int(h), 1)
            if col == "description":
                near_cell = has and near(norm(col, gt), norm(col, str(v.value)))
                s.add(col, "distance_le_1", int(near_cell), 1)
            if out != "correct":
                cn = conf.name if conf is not None else ""
                s.cells.append([t.id, g[0], col, gt, shown, cn, out])
    for g in gold:
        if _unreadable(g[0]):
            s.cells.append(
                [t.id, g[0], "(row)", "circuit unreadable", "", "", "circuit unreadable"]
            )
    label = "unpaired row" if unkeyed else "extra row"
    for i in extra:
        c = circuits[i]
        s.cells.append([t.id, c.number, "(row)", "", label, c.source.confidence.name, label])
    if t.check is not None:
        _disagree(s, gold, t.check)
    return s


def _disagree(s: Scored, truth: list[list[str]], check: list[list[str]]) -> None:
    paired, extra = _pair(truth, [r[0] for r in check])
    unkeyed = sum(1 for g in truth if _unreadable(g[0]))
    n = min(unkeyed, len(extra))
    keyed_missed = sum(
        1 for g, p in zip(truth, paired, strict=True) if p is None and not _unreadable(g[0])
    )
    s.add(
        "rows",
        "check_rows_in_one_file",
        keyed_missed + unkeyed - n + len(extra) - n,
        len(truth) + len(extra) - 2 * n,
    )
    s.add("rows", "check_row_not_pairable", n, len(truth))
    for g, p in zip(truth, paired, strict=True):
        if p is None:
            continue
        for col in COLS:
            i = TRUTH_HEADER.index(col)
            if _unreadable(g[i]) or _unreadable(check[p][i]):
                continue
            s.add(col, "human_disagreement", int(norm(col, g[i]) != norm(col, check[p][i])), 1)


# --- output ---


def _ratio(num: int, den: int) -> str:
    return f"{num / den:.4f}" if den else ""


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _write_csv(path: Path, header: list[str], rows: list[list[str | int]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows([[_safe(c) for c in r] for r in rows])


OUTPUTS = ("results.csv", "cells.csv", "timing.csv", "run.json")


def _writable(out: Path) -> str:
    """Empty when the folder can be made and every output file opened for writing."""
    try:
        out.mkdir(parents=True, exist_ok=True)
        for name in OUTPUTS:
            f = out / name
            new = not f.exists()
            f.open("ab").close()
            if new:
                f.unlink()
    except OSError as e:
        return f"cannot write results to {out}: {type(e).__name__}. Nothing was parsed."
    return ""


def run(manifest_dir: Path, cfg: Config, out_dir: Path | None) -> tuple[str, int]:
    folder = Path(manifest_dir)
    tables, why = _manifest(folder)
    if tables is None:
        return f"gold eval: {why}", 2
    if all(t.rows is None for t in tables):
        ids = ", ".join(t.id for t in tables)
        return f"gold eval: no truth file could be read: {ids}. No results written.", 2
    out = Path(out_dir) if out_dir is not None else folder / "results"
    if why := _writable(out):
        return f"gold eval: {why}", 2

    reads: dict[str, Read] = {}
    scored: dict[str, Scored] = {}
    for t in tables:
        if t.rows is None:
            continue
        src = (folder / t.source).resolve()
        key = str(src)
        if key not in reads:
            reads[key] = _read_source(src, cfg)
        scored[t.id] = _score(t, reads[key])

    result: dict[tuple[str, str, str, str], list[int]] = defaultdict(lambda: [0, 0])

    def put(scope: str, tid: str, col: str, measure: str, num: int, den: int) -> None:
        m = result[(scope, tid, col, measure)]
        m[0] += num
        m[1] += den

    for t in tables:
        s = scored.get(t.id)
        scopes = [("table", t.id), ("total", ""), *[(f"kind:{t.kind}", "")] * bool(t.kind)]
        scopes += [(f"tag:{g}", "") for g in t.tags]
        for scope, tid in scopes:
            put(scope, tid, "table", "truth_read", int(s is not None), 1)
        if s is None:
            continue
        flags = {"table_read": s.read, "table_listed": s.listed, "repeat_run_differs": s.differs}
        for scope, tid in scopes:
            for (col, measure), (num, den) in s.meas.items():
                put(scope, tid, col, measure, num, den)
            for measure, on in flags.items():
                put(scope, tid, "table", measure, int(on), 1)
    order = {"table": 0, "kind": 1, "tag": 2, "total": 3}
    rows = [
        [scope, tid, col, measure, n, d, _ratio(n, d)]
        for (scope, tid, col, measure), (n, d) in sorted(
            result.items(), key=lambda kv: (order[kv[0][0].split(":")[0]], *kv[0])
        )
    ]
    failed: list[str] = []

    def write(name: str, make: Callable[[Path], object]) -> None:
        try:
            make(out / name)
        except OSError:
            failed.append(name)

    write("results.csv", lambda f: _write_csv(f, RESULT_HEADER, rows))
    write(
        "cells.csv",
        lambda f: _write_csv(
            f, CELL_HEADER, [c for t in tables if t.id in scored for c in scored[t.id].cells]
        ),
    )
    write(
        "timing.csv",
        lambda f: _write_csv(
            f,
            ["source_file", "seconds"],
            [[Path(k).name, f"{r.seconds:.4f}"] for k, r in sorted(reads.items())],
        ),
    )
    versions = {}
    for t in tables:
        key = str((folder / t.source).resolve())
        ri = reads[key].reads[0].run_info if key in reads else None
        if ri and ri.extractor_versions:
            versions[t.source] = dict(ri.extractor_versions)
    info = {
        "tool_version": __version__,
        "config_hashes": dict(cfg.hashes),
        "extractor_versions": versions,
        "manifest_sha256": _sha(folder / "manifest.csv"),
        "sources": {s: _sha(folder / s) for s in sorted({t.source for t in tables})},
        "models": [],
    }
    write(
        "run.json",
        lambda f: f.write_text(json.dumps(info, indent=2, sort_keys=True), encoding="utf-8"),
    )

    n_read = sum(s.read for s in scored.values())
    n_listed = sum(s.listed for s in scored.values())
    lines = [
        f"tables: {len(tables)} in manifest, {n_read} read, {n_listed} listed",
        f"silent wrong passes: {sum(s.silent_wrong for s in scored.values())}",
        f"silent missing rows: {sum(s.silent_missing for s in scored.values())}",
        f"results: {out}",
    ]
    if pairless := sum(s.not_pairable for s in scored.values()):
        lines.append(f"gold rows not pairable: {pairless}")
    if ids := [t.id for t in tables if t.bad_id]:
        lines.append("table_id not allowed, not read: " + ", ".join(ids))
    if ids := [t.id for t in tables if t.rows is None and not t.bad_id]:
        lines.append("truth file not read: " + ", ".join(ids))
    if ids := [i for i, s in scored.items() if s.differs]:
        lines.append("repeat run differs: " + ", ".join(ids))
    if failed:
        lines.append("not written: " + ", ".join(failed))
    return "\n".join(lines), 0
