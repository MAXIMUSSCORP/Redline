import importlib.metadata as md
import re
import tomllib
from pathlib import Path

import redline

NAME = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _name(req: str) -> str:
    """The project name of a requirement line, in canonical form."""
    m = NAME.match(req)
    assert m, req
    return re.sub(r"[-_.]+", "-", m.group(1)).lower()


def _evaluates(req: str) -> bool:
    """False for a requirement that only an extra pulls in; other markers are kept."""
    marker = req.partition(";")[2]
    return "extra" not in marker


ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
PROJECT = PYPROJECT["project"]
EXTRAS = PROJECT["optional-dependencies"]


def test_version_single_source():
    assert "version" not in PROJECT
    assert "version" in PROJECT["dynamic"]
    assert PYPROJECT["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "redline.__version__"}
    assert redline.__version__ == "0.1.0"


def test_base_requirements_have_upper_bounds():
    assert len(PROJECT["dependencies"]) >= 3
    for line in PROJECT["dependencies"]:
        assert "<" in line, line


def test_dev_extra_has_dxf():
    names = {_name(x) for x in EXTRAS["dev"]}
    assert "ezdxf" in names


def test_no_ai_or_detect_extra():
    assert set(EXTRAS) == {"dev", "dxf", "pdf"}


def _closure(tops: list[str]) -> set[str]:
    seen: set[str] = set()
    todo = [_name(r) for r in tops]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        for line in md.requires(name) or []:
            if _evaluates(line):
                todo.append(_name(line))
    return seen


def test_constraints_pin_runtime_closure():
    lines = (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines()
    pins = [x.strip() for x in lines if x.strip() and not x.lstrip().startswith("#")]
    assert all("==" in x for x in pins), pins
    pinned = {_name(n): v for n, v in (x.split("==") for x in pins)}
    tops = PROJECT["dependencies"] + EXTRAS["dxf"] + EXTRAS["pdf"]
    closure = _closure(tops)
    assert len(closure) >= 5
    assert closure <= set(pinned), sorted(closure - set(pinned))
    assert {n for n in pinned if md.version(n) != pinned[n]} == set()
