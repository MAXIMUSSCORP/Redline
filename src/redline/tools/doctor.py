"""redline doctor: report what this machine can and cannot read (M6 D2, D8).

One line per check: STATUS, check name, detail. Doctor exits 0 when it ran to the end and 2 only when
the config cannot be loaded. It writes nothing outside a temp folder of its own, opens no socket,
imports no model library and no extra, and changes no AutoCAD setting.
"""

from __future__ import annotations

import csv
import io
import os
import re
import shutil
import sys
import tempfile
from importlib import metadata
from pathlib import Path
from typing import Any

from redline import rawdrawing
from redline.config import (
    CONFIG_FILES,
    FIRE_ALARM_TABLE,
    Config,
    ConfigError,
    is_test_config,
    load_config,
    table_verified,
)
from redline.extract import ExtractError, Unavailable, acad_console, run_tool, sha256_of

AI_LINE = "AI is off in ai.yaml and this build has no AI module (PLAN row 47)"
NO_REFUSAL_TEXT = (
    "the smoke run cannot show whether NETLOAD was refused without a drawing; "
    "run redline doctor --drawing FILE"
)
STATUSES = ("PASS", "WARN", "FAIL", "NOT CHECKED")
Line = tuple[str, str, str]


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _vtuple(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text.split("+")[0])[:4])


def _in_range(version: str, spec: str) -> bool:
    have = _vtuple(version)
    for op, want in re.findall(r"(>=|<=|==|!=|>|<)\s*([\w.]+)", spec):
        w = _vtuple(want)
        n = max(len(have), len(w))
        a, b = have + (0,) * (n - len(have)), w + (0,) * (n - len(w))
        if not {
            ">=": a >= b,
            "<=": a <= b,
            "==": a == b,
            "!=": a != b,
            ">": a > b,
            "<": a < b,
        }[op]:
            return False
    return True


def _requirements() -> list[tuple[str, str, str]]:
    """(name, specifier, extra) for each requirement of redline; extra is empty for the base."""
    out = []
    for raw in metadata.requires("redline") or []:
        req, _, marker = raw.partition(";")
        m = re.match(r"\s*([A-Za-z0-9_.-]+)\s*(?:\[[^\]]*\])?\s*(.*)", req)
        if not m:
            continue
        e = re.search(r"extra\s*==\s*[\"']([\w.-]+)[\"']", marker)
        out.append(
            (m.group(1), m.group(2).replace("(", "").replace(")", ""), e.group(1) if e else "")
        )
    return out


def _check_python() -> list[Line]:
    try:
        need = metadata.metadata("redline").get("Requires-Python") or ""
    except metadata.PackageNotFoundError:
        need = ""
    have = ".".join(str(x) for x in sys.version_info[:3])
    if need and not _in_range(have, need):
        return [("FAIL", "python", f"Python {have} is below the requirement {need}")]
    if "onedrive" in sys.prefix.lower():
        return [
            (
                "WARN",
                "python",
                (
                    f"Python {have}; the venv at {sys.prefix} is inside a OneDrive folder, "
                    "move it under LOCALAPPDATA"
                ),
            )
        ]
    return [("PASS", "python", f"Python {have}" + (f" meets {need}" if need else ""))]


def _check_packages() -> list[Line]:
    reqs = _requirements()
    if not reqs:
        return [("NOT CHECKED", "packages", "the redline package metadata is not installed")]
    out: list[Line] = []
    for name, group in (("packages", ""), ("dxf", "dxf"), ("pdf", "pdf")):
        bad, ok, missing = [], [], []
        for pkg, spec, extra in reqs:
            if extra != group:
                continue
            try:
                v = metadata.version(pkg)
            except metadata.PackageNotFoundError:
                missing.append(pkg)
                continue
            (ok if _in_range(v, spec) else bad).append(
                f"{pkg} {v}" + ("" if _in_range(v, spec) else f" is outside {spec}")
            )
        if bad:
            out.append(("FAIL", name, "; ".join(bad)))
        elif missing and group:
            out.append(
                ("WARN", name, f"{', '.join(missing)} not installed; pip install redline[{group}]")
            )
        elif missing:
            out.append(("FAIL", name, f"{', '.join(missing)} not installed"))
        elif ok:
            out.append(("PASS", name, ", ".join(ok)))
    return out


def _check_config(cfg: Config) -> Line:
    hashes = ", ".join(f"{f} {cfg.hashes[f][:12]}" for f in CONFIG_FILES)
    if is_test_config(cfg):
        return ("WARN", "config", f"TEST config in use; {hashes}")
    return ("PASS", "config", hashes)


def _check_tables(cfg: Config) -> list[Line]:
    out: list[Line] = []
    if cfg.cec.get("code_edition_verified") is not True:
        out.append(("WARN", "tables", "code_edition_verified is false in cec_tables.yaml"))
    for name in cfg.cec["tables"]:
        if not table_verified(cfg, name):
            out.append(("WARN", "tables", f"table {name} is not verified"))
    if not table_verified(cfg, FIRE_ALARM_TABLE):
        out.append(("WARN", "tables", "fire_alarm.yaml is not verified"))
    return out or [("PASS", "tables", "every table and the edition flag are verified")]


def _path(parsing: dict[str, Any], key: str) -> str | None:
    raw = parsing.get(key)
    return os.path.abspath(os.path.expandvars(raw)) if raw else None


def _check_oda(parsing: dict[str, Any]) -> Line:
    p = _path(parsing, "odafc_path")
    if p is None:
        return ("WARN", "oda", "odafc_path is not set")
    if not os.path.isfile(p):
        return ("FAIL", "oda", f"odafc_path does not exist: {p}")
    return ("PASS", "oda", f"{p}; not started, its version is not read")


def _smoke(exe: str, dll: str | None, timeout: float) -> Line:
    tmp = Path(tempfile.mkdtemp(prefix="redline-doctor-"))
    try:
        lines = ["FILEDIA", "0"] + (["NETLOAD", dll.replace("\\", "/")] if dll else []) + ["QUIT"]
        script = tmp / "smoke.scr"
        script.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            run_tool("AutoCAD Core Console", [exe, "/s", str(script), "/l", "en-US"], timeout, tmp)
        except ExtractError as e:
            return ("FAIL", "console", f"{exe}: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return (
        "PASS",
        "console",
        f"{exe}; the smoke run ended, its version and exit code are not read",
    )


def _check_plugin(exe_ok: bool, dll: str | None, cfg: Config, drawing: Path | None) -> list[Line]:
    if dll is None:
        return [("WARN", "plugin", "acad_plugin_dll is not set")]
    if re.search(r"\s", dll):
        return [
            (
                "FAIL",
                "plugin",
                f"acad_plugin_dll path holds a space, so NETLOAD cannot take it: {dll}",
            )
        ]
    if not os.path.isfile(dll):
        return [("FAIL", "plugin", f"acad_plugin_dll does not exist: {dll}")]
    sha = ("PASS", "plugin_file", f"{dll} SHA-256 {sha256_of(Path(dll))}")
    if not exe_ok:
        return [
            sha,
            ("NOT CHECKED", "plugin", "the core console did not run, so the plugin was not loaded"),
        ]
    if drawing is None:
        return [sha, ("NOT CHECKED", "plugin", NO_REFUSAL_TEXT)]
    try:
        data = acad_console.extract(drawing, cfg)
    except Unavailable as e:
        return [sha, ("NOT CHECKED", "plugin", str(e))]
    except ExtractError as e:
        if "wrote no output file" in str(e):
            return [
                sha,
                (
                    "FAIL",
                    "plugin",
                    (
                        f"no dump was written, so NETLOAD may have been refused for {dll}; "
                        "the owner adds its folder to TRUSTEDPATHS, doctor never does"
                    ),
                ),
            ]
        return [sha, ("FAIL", "plugin", str(e))]
    ver = data["schema_version"]
    seen = f"schema_version {ver}, plugin {data['extractor_version']}, host {data['host_version']}"
    if _vtuple(ver) < _vtuple(rawdrawing.SCHEMA_VERSION):
        return [
            sha,
            (
                "WARN",
                "plugin",
                f"dump ran; {seen}, below {rawdrawing.SCHEMA_VERSION}, so an old plugin build is deployed",
            ),
        ]
    return [sha, ("PASS", "plugin", f"loaded; dump ran; {seen}")]


def _check_ai(cfg: Config) -> Line:
    if cfg.ai.get("enabled") is True:
        return ("FAIL", "ai", "ai.yaml enables AI but this build has no AI module")
    return ("NOT CHECKED", "ai", AI_LINE)


def _format(lines: list[Line]) -> str:
    counts = [sum(1 for s, _, _ in lines if s == w) for w in STATUSES]
    tail = ", ".join(f"{w} {n}" for w, n in zip(STATUSES, counts, strict=True))
    return "\n".join([f"{s}  {n}  {d}" for s, n, d in lines] + [tail])


def _doctor(config_dir: Path, drawing: Path | None) -> tuple[str, int]:
    lines: list[Line] = _check_python() + _check_packages()
    try:
        cfg = load_config(config_dir)
    except (ConfigError, OSError) as e:
        lines.append(("FAIL", "config", " ".join(str(e).split())))
        return _format(lines), 2
    lines.append(_check_config(cfg))
    lines += _check_tables(cfg)
    parsing = cfg.column_maps["parsing"]
    lines.append(_check_oda(parsing))
    exe, dll = _path(parsing, "accoreconsole_path"), _path(parsing, "acad_plugin_dll")
    exe_ok = False
    if exe is None:
        lines.append(("WARN", "console", "accoreconsole_path is not set"))
    elif not os.path.isfile(exe):
        lines.append(("FAIL", "console", f"accoreconsole_path does not exist: {exe}"))
    else:
        loadable = dll and not re.search(r"\s", dll) and os.path.isfile(dll)
        line = _smoke(exe, dll if loadable else None, parsing["dxf_extractor_timeout_s"])
        exe_ok = line[0] == "PASS"
        lines.append(line)
    if drawing is not None and not drawing.is_file():
        lines.append(("FAIL", "drawing", f"{drawing.name} was not found"))
        drawing = None
    lines += _check_plugin(exe_ok, dll, cfg, drawing)
    lines.append(_check_ai(cfg))
    return _format(lines), 0


# D8: a licence is "listed" only when every name in it is on this short permissive list.
_PERMISSIVE = {
    "MIT", "MIT-0", "MIT-CMU", "BSD", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC",
    "PSF-2.0", "0BSD", "Zlib", "CC0-1.0",
}  # fmt: skip
_CLASSIFIER = {
    "MIT License": "MIT",
    "BSD License": "BSD",
    "Apache Software License": "Apache-2.0",
    "ISC License (ISCL)": "ISC",
    "Python Software Foundation License": "PSF-2.0",
}
_GROUPS = ("base", "dxf", "pdf", "dev")
_HEADER = ["package", "version", "licence", "read_from", "licence_files", "group", "status"]


def _licence(md: Any) -> tuple[str, str]:
    expr = (md.get("License-Expression") or "").strip()
    if expr:
        return expr, "License-Expression"
    lic = " ".join((md.get("License") or "").split())
    if lic and lic.upper() != "UNKNOWN":
        return lic[:120], "License"
    names = [
        c.split("::")[-1].strip()
        for c in md.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    if names:
        return " OR ".join(_CLASSIFIER.get(n, n) for n in names), "classifier"
    return "", ""


def _closure() -> dict[str, tuple[str, str]]:
    """Canonical name to (distribution name, group), the installed closure of redline's requirements."""
    found: dict[str, tuple[str, str]] = {}

    def walk(name: str, group: str) -> None:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            return
        if _canon(name) in found:
            return
        found[_canon(name)] = (dist.metadata["Name"], group)
        for raw in dist.requires or []:
            req, _, marker = raw.partition(";")
            if "extra" in marker:
                continue
            # ponytail: markers other than extra are not evaluated; an installed package is kept
            m = re.match(r"\s*([A-Za-z0-9_.-]+)", req)
            if m:
                walk(m.group(1), group)

    roots = _requirements()
    for group in _GROUPS:
        for pkg, _spec, extra in roots:
            if (extra or "base") == group:
                walk(pkg, group)
    return found


def _licences() -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(_HEADER)
    rows = sorted(_closure().values(), key=lambda t: (_GROUPS.index(t[1]), t[0].casefold()))
    for name, group in rows:
        md = metadata.metadata(name)
        text, src = _licence(md)
        tokens = [t for t in re.split(r"\s+(?:AND|OR|WITH)\s+|[()]", text) if t.strip()]
        listed = bool(tokens) and all(t.strip() in _PERMISSIVE for t in tokens)
        files = len(md.get_all("License-File") or [])
        w.writerow(
            [
                name,
                metadata.version(name),
                text,
                src,
                files,
                group,
                "listed" if listed else "REVIEW",
            ]
        )
    return out.getvalue().rstrip("\n")


def run(config_dir: Path, drawing: Path | None, licences: bool) -> tuple[str, int]:
    """Return the text to print and the exit code."""
    if licences:
        return _licences(), 0
    return _doctor(Path(config_dir), drawing)
