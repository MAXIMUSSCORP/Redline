"""Run the Redline plugin in the AutoCAD Core Console on a copy of the drawing."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from redline.config import Config
from redline.extract import (
    ExtractError,
    Unavailable,
    add_warning,
    check_unchanged,
    read_output,
    run_tool,
    sha256_of,
)

NAME = "AutoCAD Core Console"


def _tool(parsing: dict[str, Any], key: str, what: str) -> str:
    raw = parsing.get(key)
    if not raw:
        raise Unavailable(f"{key} is not set in the parsing config, so {what} cannot run")
    return os.path.abspath(os.path.expandvars(raw))


def extract(path: Path, cfg: Config) -> dict[str, Any]:
    parsing = cfg.column_maps["parsing"]
    exe = _tool(parsing, "accoreconsole_path", "AutoCAD Core Console")
    dll = _tool(parsing, "acad_plugin_dll", "the Redline plugin")
    if re.search(r"\s", dll):
        raise Unavailable(f"acad_plugin_dll path holds a space, so NETLOAD cannot take it: {dll}")
    if not os.path.isfile(exe):
        raise Unavailable(f"accoreconsole_path does not exist: {exe}")
    if not os.path.isfile(dll):
        raise Unavailable(f"acad_plugin_dll does not exist: {dll}")
    if not path.is_file():
        raise ExtractError(f"{path.name} was not found")
    timeout = parsing["dxf_extractor_timeout_s"]

    before = sha256_of(path)
    tmp = Path(tempfile.mkdtemp(prefix="redline-acad-", dir=tempfile.gettempdir()))
    try:
        # On a copy: /readonly was accepted (exit 0, saved nothing), but a lock file during the run is not ruled out.
        src = tmp / "in" / path.name
        out = tmp / "out.json"
        script = tmp / "run.scr"
        if not str(out).isascii():
            raise Unavailable(
                f"the temp folder path is not ASCII, so AutoCAD may misread it: {out.parent}"
            )
        try:
            src.parent.mkdir()
            shutil.copyfile(path, src)
            lines = ["FILEDIA", "0", "NETLOAD", dll.replace("\\", "/"), "REDLINE_DUMP"]
            lines.append(str(out).replace("\\", "/"))
            script.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as e:
            raise ExtractError(f"{path.name} could not be copied to a temp folder") from e
        run_tool(NAME, [exe, "/i", str(src), "/s", str(script), "/l", "en-US"], timeout, tmp)
        data = read_output(NAME, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if data["source_sha256"] != before:
        add_warning(data, "the hash the plugin reported differs from the input file")
    check_unchanged(data, path, before)
    return data
