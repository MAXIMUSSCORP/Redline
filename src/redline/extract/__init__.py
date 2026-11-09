"""Turn a .dwg or .dxf into RawDrawing JSON, with one extractor and one fallback."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

from redline import rawdrawing
from redline.config import Config


class ExtractError(Exception):
    """The message is the listing reason, in plain words."""


class Unavailable(ExtractError):
    """A tool is not installed or not configured."""


_ORDER = {"acad_plugin": "acad_console", "oda_ezdxf": "oda_ezdxf"}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError as e:
        raise ExtractError(f"{path.name} cannot be read ({type(e).__name__})") from e
    return h.hexdigest()


def add_warning(data: dict[str, Any], text: str) -> None:
    data["document"]["warnings"].append(text)


def check_unchanged(data: dict[str, Any], path: Path, before: str) -> None:
    try:
        same = sha256_of(path) == before
    except ExtractError:
        same = False
    if not same:
        add_warning(data, "the drawing changed while it was read")


def _kill_tree(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def run_tool(name: str, args: list[str], timeout: float, cwd: Path) -> None:
    """Run a child with no shell. The exit code is ignored: the output file is the signal.

    Output streams go to DEVNULL so a surviving grandchild cannot hold a pipe open.
    """
    try:
        proc = subprocess.Popen(
            args,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=cwd,
        )
    except OSError as e:
        raise ExtractError(f"{name} could not start ({type(e).__name__})") from e
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        raise ExtractError(f"{name} timed out after {timeout:g} s") from None


def read_output(name: str, out: Path) -> dict[str, Any]:
    if not out.is_file():
        raise ExtractError(f"{name} wrote no output file")
    try:
        data = rawdrawing.read(out)
    except (ValueError, OSError) as e:
        raise ExtractError(f"{name} output cannot be read: {e}") from e
    return validated(name, data)


def validated(name: str, data: Any) -> dict[str, Any]:
    v = rawdrawing.validate(data)
    if not v.ok:
        raise ExtractError(f"{name} output is not valid RawDrawing: " + "; ".join(v.errors[:3]))
    return data


def extract(path: Path, cfg: Config) -> dict[str, Any]:
    from redline.extract import acad_console, oda_ezdxf

    modules = {"acad_plugin": acad_console, "oda_ezdxf": oda_ezdxf}
    first = cfg.column_maps["parsing"]["dxf_prefer_extractor"]
    names = [first] + [n for n in _ORDER if n != first]
    reasons: list[str] = []
    failed: list[str] = []
    for name in names:
        try:
            data = modules[name].extract(path, cfg)
        except Unavailable as e:
            reasons.append(f"{name}: {e}")
        except ExtractError as e:
            reasons.append(f"{name}: {e}")
            failed.append(name)
        else:
            for f in failed:
                add_warning(data, f"{f} failed on this drawing, so {name} was used")
            return data
    cls = ExtractError if failed else Unavailable
    raise cls("; ".join(reasons))
