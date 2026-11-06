from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from redline import __version__
from redline.config import ConfigError, load_config
from redline.engine import run
from redline.model import RunInfo, project_from_dict
from redline.registry import RULES
from redline.report.csv_out import write_findings_csv
from redline.report.html import render_html


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="redline")
    sub = ap.add_subparsers(dest="command", required=True)
    chk = sub.add_parser("check", help="screen a project and write the report")
    chk.add_argument("--demo-project", metavar="PATH", help="a project in the demo JSON shape")
    chk.add_argument("--config", metavar="DIR", default="config")
    chk.add_argument("--out", metavar="PATH", default="report.html")
    chk.add_argument("--skip-rule", metavar="ID", action="append", default=[])
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
    if abs(n) > 2**53:
        raise ValueError(f"{text[:20]} is too large a number")
    return n


def _no_repeat(pairs: list[tuple[str, object]]) -> dict:
    out: dict = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"repeated key {k}")
        out[k] = v
    return out


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.demo_project:
        return _fail("no input given. Use --demo-project PATH.")
    known = {r.id for r in RULES}
    if bad := [s for s in args.skip_rule if s not in known]:
        return _fail(f"unknown rule id: {', '.join(bad)}.")
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        return _fail(f"config error: {' '.join(str(e).split())}")
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
    out = Path(args.out)
    try:
        # Windows drops trailing dots and spaces, and ':' opens a stream of the same file.
        alias = ":" in out.name or out.name.rstrip(" .").lower() == "findings.csv"
        if alias or out.is_dir() or out.resolve() == (out.parent / "findings.csv").resolve():
            return _fail(
                f"--out {args.out} must be a new report file, not a directory or findings.csv."
            )
        project.run_info = RunInfo(tool_version=__version__, config_hashes=dict(cfg.hashes))
        result = run(project, cfg, RULES, args.skip_rule)
        html = render_html(project, result, cfg)
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return _fail(f"cannot write {args.out}: {type(e).__name__}.")
    # The CSV goes first, so a report is never left without its findings.
    for path, write in (
        (out.parent / "findings.csv", lambda p: write_findings_csv(result.findings, p)),
        (out, lambda p: p.write_text(html, encoding="utf-8")),
    ):
        try:
            write(path)
        except OSError as e:
            return _fail(f"cannot write {path}: {type(e).__name__}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
