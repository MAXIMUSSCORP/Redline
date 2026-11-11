from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import sys
from collections.abc import Callable
from pathlib import Path

from redline import __version__
from redline.config import CONFIG_FILES, Config, ConfigError, load_config
from redline.engine import run
from redline.model import (
    MAX_INT,
    Confidence,
    CoverageEntry,
    Method,
    Panel,
    Project,
    RunInfo,
    Source,
    Unparsed,
    project_from_dict,
)
from redline.parsers import exits
from redline.parsers.csv_xlsx import SUFFIXES, InputError, parse_file
from redline.parsers.tabular import Parsed
from redline.registry import RULES
from redline.report.csv_out import write_findings_csv
from redline.report.html import render_html


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="redline")
    sub = ap.add_subparsers(dest="command", required=True)
    chk = sub.add_parser("check", help="screen a project and write the report")
    chk.add_argument("inputs", nargs="*", metavar="INPUT", help="files or folders to read")
    chk.add_argument("--demo-project", metavar="PATH", help="a project in the demo JSON shape")
    chk.add_argument("--config", metavar="DIR", default="config")
    chk.add_argument("--out", metavar="PATH", default="report.html")
    chk.add_argument("--skip-rule", metavar="ID", action="append", default=[])
    xc = sub.add_parser("xcheck", help="compare what the two DWG extractors read from a drawing")
    xc.add_argument("files", nargs="+", metavar="FILE", help="DWG or DXF files")
    xc.add_argument("--config", metavar="DIR", default="config")
    return ap


def _fail(msg: str) -> int:
    print(f"redline: {msg}", file=sys.stderr)
    return 2


def _no_constant(name: str) -> None:
    raise ValueError(f"{name} is not allowed in JSON")


def _finite(text: str) -> float:
    x = float(text)
    if not math.isfinite(x):
        raise ValueError(f"{text} is not a finite number")
    return x


def _int(text: str) -> int:
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


def _same(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve() or (a.exists() and b.exists() and os.path.samefile(a, b))


def _flag_repeated_panels(project: Project) -> None:
    """A repeated panel name stays as separate panels (never merged). Demand and phase balance
    need the whole panel, so their panel-level inputs are made LOW and the repeat is listed."""
    seen: dict[str, list[Panel]] = {}
    for p in project.panels:
        seen.setdefault(p.name.strip().casefold(), []).append(p)
    for group in seen.values():
        if len(group) < 2:
            continue
        where = "; ".join(f"{p.source.file} {p.source.locator}" for p in group)
        why = (
            f"panel name {group[0].name} is read {len(group)} times, so the panel-level "
            f"demand and phase balance checks need the whole panel and were not run on a part. "
            f"Read from: {where}"
        )
        # one note per name, shared by every part, so the name is not copied per panel
        note = "panel name repeats; the panel-level check needs the whole panel"
        for p in group:
            for attr in ("bus_rating_a", "phases"):
                v = getattr(p, attr)
                base = v.source or p.source
                low = dataclasses.replace(base, confidence=Confidence.LOW, note=note)
                setattr(p, attr, dataclasses.replace(v, source=low))
        project.unparsed.append(Unparsed("panel", group[0].name, why, group[0].source))


def _merge_units(project: Project, parsed: Parsed) -> None:
    """Add the sheet units of one drawing. A sheet read twice has its devices counted twice, so
    its units are made not usable and the repeat is listed."""
    have = {k.casefold(): k for k in project.sheet_units}
    for sheet, v in parsed.sheet_units.items():
        if (old := have.get(sheet.casefold())) is None:
            project.sheet_units[sheet] = v
            continue
        why = f"sheet {sheet} is read more than once, so its devices are counted twice"
        note = exits.REPEATED_SHEET_NOTE
        base = v.source or project.sheet_units[old].source
        low = dataclasses.replace(base, confidence=Confidence.LOW, note=note)
        project.sheet_units[old] = dataclasses.replace(
            project.sheet_units[old], value=None, source=low
        )
        project.unparsed.append(Unparsed("sheet", sheet, why, low))


def _reader(f: Path) -> Callable[[Path, Config], Parsed] | None:
    """The parse function for a file, or None when no reader takes the file type. The DWG, WDP
    and PDF readers are imported only when a file may need them."""
    if f.name.lower().endswith((".json", ".dwg", ".dxf", ".wdp")):
        from redline.parsers import aecad_side, dxf

        if dxf.accepts(f):
            return dxf.parse_file
        if f.suffix.lower() in aecad_side.SUFFIXES:
            return aecad_side.parse_file
    if f.suffix.lower() == ".pdf":
        from redline.parsers import pdf

        return pdf.parse_file
    return parse_file if f.suffix.lower() in SUFFIXES else None


def _load_inputs(paths: list[str], cfg: Config) -> tuple[Project, int, list[Path], list[Path]]:
    """Read files and folders. Returns the project, the count of files read, the files
    tried and the input folders. A failing file is listed and the rest are still read."""
    project = Project(name=Path(paths[0]).resolve().name)
    read, tried, folders = 0, [], []
    side: list[Path] = []  # exits.csv and paths.csv, read after every drawing
    versions: dict[str, str] = {}
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            folders.append(p)
            try:
                entries = list(p.iterdir())
            except OSError as e:
                why = f"folder not read: {e.strerror or type(e).__name__}"
                src = Source(p.name, "folder", Method.CSV, Confidence.LOW)
                project.unparsed.append(Unparsed("table", p.name, why, src))
                continue
            for d in sorted((f for f in entries if f.is_dir()), key=lambda f: f.name):
                project.coverage.append(
                    CoverageEntry(d.name, "folder", "not read: subfolders are not read", "none", "")
                )
            files = sorted((f for f in entries if f.is_file()), key=lambda f: f.name)
        else:
            files = [p]
        for f in files:
            tried.append(f)
            project.inputs.append(f.name)
            if f.name.lower() in exits.NAMES and f.is_file():
                side.append(f)
                read += 1
                continue
            parse = _reader(f)
            if parse is None and f.exists():
                project.coverage.append(
                    CoverageEntry(f.name, "file", "not read: unsupported file type", "none", "")
                )
                continue
            try:
                parsed = (parse or parse_file)(f, cfg)
            except Exception as e:  # noqa: BLE001 - a bad file must not stop the others
                src = Source(f.name, "file", Method.CSV, Confidence.LOW)
                detail = " ".join(str(e).split()) if isinstance(e, InputError) else type(e).__name__
                why = f"file not read: {detail}"
                project.unparsed.append(Unparsed("table", f.name, why, src))
                continue
            read += 1
            project.panels += parsed.panels
            project.unparsed += parsed.unparsed
            project.coverage += parsed.coverage
            project.devices += parsed.devices
            _merge_units(project, parsed)
            for key, text in parsed.provenance.items():
                n = 1
                while (name := key if n == 1 else f"{key} #{n}") in versions:
                    n += 1
                versions[name] = text
    exits.apply(side, project, cfg)
    if versions:
        project.run_info = RunInfo(tool_version="", extractor_versions=versions)
    _flag_repeated_panels(project)
    return project, read, tried, folders


def _xcheck(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        return _fail(f"config error: {' '.join(str(e).split())}")
    from redline.tools import xcheck

    text, code = xcheck.run([Path(f) for f in args.files], cfg)
    print(text)
    return code


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # a file name may not fit the console code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = _parser().parse_args(argv)
    if args.command == "xcheck":
        return _xcheck(args)
    if args.demo_project and args.inputs:
        return _fail("give input files or --demo-project, not both.")
    if not args.demo_project and not args.inputs:
        return _fail("no input given. Give a file or folder, or use --demo-project PATH.")
    known = {r.id for r in RULES}
    if bad := [s for s in args.skip_rule if s not in known]:
        return _fail(f"unknown rule id: {', '.join(bad)}.")
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        return _fail(f"config error: {' '.join(str(e).split())}")
    folders: list[Path] = []
    if args.demo_project:
        try:
            text = Path(args.demo_project).read_text(encoding="utf-8")
            data = json.loads(
                text,
                parse_constant=_no_constant,
                parse_float=_finite,
                parse_int=_int,
                object_pairs_hook=_no_repeat,
            )
            project = project_from_dict(data)
        except (OSError, ValueError, KeyError, TypeError, RecursionError) as e:
            why = " ".join(str(e).split()) if isinstance(e, ValueError) else type(e).__name__
            return _fail(f"cannot read demo project {args.demo_project}: {why}.")
        if not project.panels:
            return _fail(f"cannot read demo project {args.demo_project}: no panels read.")
        files = [Path(args.demo_project)]
    else:
        project, read, files, folders = _load_inputs(args.inputs, cfg)
        if not read:
            return _fail("no input file could be read.")
    out = Path(args.out)
    try:
        # Windows drops trailing dots and spaces, and ':' opens a stream of the same file.
        # A '~' may be an 8.3 short name of another file.
        alias = ":" in out.name or "~" in out.name
        alias = alias or out.name.rstrip(" .").lower() == "findings.csv"
        inputs = [*files, *(cfg.dir / f for f in CONFIG_FILES)]
        if (
            alias
            or out.is_dir()
            or any(_same(out.parent, d) for d in folders)
            or any(_same(out, p) for p in (out.parent / "findings.csv", *inputs))
            or any(_same(out.parent / "findings.csv", p) for p in inputs)
        ):
            return _fail(
                f"--out {args.out} must be a new report file, not a directory, an input, "
                "inside an input folder or findings.csv, and findings.csv beside it must not be an input."
            )
        given = project.run_info or RunInfo(tool_version="")
        project.run_info = RunInfo(
            tool_version=__version__,
            config_hashes=dict(cfg.hashes),
            extractor_versions=dict(given.extractor_versions),
            model_ids_versions_hashes=list(given.model_ids_versions_hashes),
            seeds=dict(given.seeds),
            input_tool_version=given.tool_version,
            input_config_hashes=dict(given.config_hashes),
        )
        result = run(project, cfg, RULES, args.skip_rule)
        html = render_html(project, result, cfg)
        html.encode("utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, UnicodeError) as e:
        return _fail(f"cannot write {args.out}: {type(e).__name__}.")
    # The CSV goes first, so a report is never left without its findings.
    for path, write in (
        (out.parent / "findings.csv", lambda p: write_findings_csv(result.findings, p)),
        (out, lambda p: p.write_text(html, encoding="utf-8")),
    ):
        try:
            write(path)
            if path != out and out.exists() and os.path.samefile(path, out):
                raise OSError("same file as the CSV")
        except (OSError, UnicodeError) as e:
            if isinstance(e, UnicodeError):
                path.unlink(missing_ok=True)
            return _fail(f"cannot write {path}: {type(e).__name__}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
