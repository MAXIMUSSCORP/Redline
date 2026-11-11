import copy
import csv
import io
import json
import re
import subprocess
import sys
from dataclasses import replace
from importlib import metadata
from pathlib import Path

import pytest

from redline import rawdrawing
from redline.extract import ExtractError, acad_console, sha256_of
from redline.tools import doctor

ROOT = Path(__file__).resolve().parent.parent
TEST_CFG = ROOT / "tests" / "test_config"
FIXTURE = ROOT / "samples" / "dwg" / "panel_sheet.acad_plugin.rawdrawing.json"
LINE = re.compile(r"^(PASS|WARN|FAIL|NOT CHECKED)  (\S+)  \S")


def lines(text):
    return text.splitlines()[:-1]


def find(text, name):
    return [x for x in lines(text) if LINE.match(x).group(2) == name]


class Env:
    pass


@pytest.fixture
def tools(tmp_path, monkeypatch, test_cfg):
    """A config whose tool paths exist, a fake console that ends at once, and a drawing."""
    e = Env()
    e.exe = tmp_path / "bin" / "accoreconsole.exe"
    e.dll = tmp_path / "bin" / "RedlinePlugin.dll"
    e.oda = tmp_path / "bin" / "ODAFileConverter.exe"
    e.exe.parent.mkdir()
    for p in (e.exe, e.dll, e.oda):
        p.write_bytes(b"x")
    e.drawing = tmp_path / "my drawing.dwg"
    e.drawing.write_bytes(b"drawing bytes")
    e.maps = copy.deepcopy(test_cfg.column_maps)
    e.maps["parsing"].update(
        accoreconsole_path=str(e.exe), acad_plugin_dll=str(e.dll), odafc_path=str(e.oda)
    )
    e.cfg = replace(test_cfg, column_maps=e.maps)
    monkeypatch.setattr(doctor, "load_config", lambda d: e.cfg)
    e.calls = []

    def run_tool(name, args, timeout, cwd):
        e.calls.append((args, Path(args[args.index("/s") + 1]).read_text(encoding="utf-8")))

    monkeypatch.setattr(doctor, "run_tool", run_tool)
    return e


def doc(drawing=None, licences=False):
    return doctor.run(TEST_CFG, drawing, licences)


def fake_dump(monkeypatch, version="1.1", write=True):
    def run_tool(name, args, timeout, cwd):
        if not write:
            return
        script = Path(args[args.index("/s") + 1]).read_text(encoding="utf-8").splitlines()
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["schema_version"] = version
        data["source_sha256"] = sha256_of(Path(args[args.index("/i") + 1]))
        Path(script[-1]).write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(acad_console, "run_tool", run_tool)


# output and exit


def test_lines_use_four_status_words(tools):
    text, code = doc()
    assert code == 0
    for x in lines(text):
        assert LINE.match(x), x


def test_last_line_counts(tools):
    text, _ = doc()
    st = [LINE.match(x).group(1) for x in lines(text)]
    want = ", ".join(f"{w} {st.count(w)}" for w in ("PASS", "WARN", "FAIL", "NOT CHECKED"))
    assert text.splitlines()[-1] == want


def test_fail_line_keeps_exit_0(tools):
    tools.maps["parsing"]["odafc_path"] = str(tools.oda.parent / "none.exe")
    text, code = doc()
    assert find(text, "oda")[0].startswith("FAIL")
    assert code == 0


def test_config_failure_exits_2_after_free_checks(monkeypatch):
    def bad(d):
        raise doctor.ConfigError("cec_tables.yaml: broken")

    monkeypatch.setattr(doctor, "load_config", bad)
    text, code = doc()
    assert code == 2
    assert find(text, "python") and find(text, "config")[0].startswith("FAIL  config  ")
    assert not find(text, "console")


def test_ai_line_not_checked(tools):
    text, _ = doc()
    assert find(text, "ai") == [f"NOT CHECKED  ai  {doctor.AI_LINE}"]


def test_ai_enabled_is_fail(tools):
    tools.cfg.ai["enabled"] = True
    text, _ = doc()
    assert find(text, "ai")[0].startswith("FAIL  ai  ai.yaml enables AI")


# python and packages


def test_python_below_requirement_fails(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 9, 0, "final", 0))
    assert doctor._check_python()[0][0] == "FAIL"


def test_venv_in_onedrive_warns(monkeypatch):
    monkeypatch.setattr(sys, "prefix", "C:/Users/x/OneDrive/Documents/venv")
    assert doctor._check_python()[0][0] == "WARN"


def _missing(monkeypatch, pkg):
    real = metadata.version

    def version(name):
        if name == pkg:
            raise metadata.PackageNotFoundError(name)
        return real(name)

    monkeypatch.setattr(doctor.metadata, "version", version)


def test_base_package_missing_fails(monkeypatch):
    _missing(monkeypatch, "PyYAML")
    line = doctor._check_packages()[0]
    assert line[:2] == ("FAIL", "packages") and "PyYAML" in line[2]


def test_extra_missing_warns_with_pip_line(monkeypatch):
    _missing(monkeypatch, "ezdxf")
    line = next(x for x in doctor._check_packages() if x[1] == "dxf")
    assert line[0] == "WARN" and "pip install redline[dxf]" in line[2]


def test_extra_out_of_range_fails(monkeypatch):
    real = metadata.version
    monkeypatch.setattr(
        doctor.metadata, "version", lambda n: "0.1" if n == "pdfplumber" else real(n)
    )
    line = next(x for x in doctor._check_packages() if x[1] == "pdf")
    assert line[0] == "FAIL" and "outside" in line[2]


def test_version_range():
    assert doctor._in_range("6.0.2", "<7,>=6.0")
    assert not doctor._in_range("7.0", "<7,>=6.0")
    assert doctor._in_range("3.12.1", ">=3.12")


# config and tables


def test_test_config_warns(tools):
    text, code = doc()
    assert code == 0 and find(text, "config")[0].startswith("WARN  config  TEST config")


def test_unverified_table_warns_per_table(tools, cfg_unverify, monkeypatch):
    name, other = list(tools.cfg.cec["tables"])[:2]
    cfg = cfg_unverify(cfg_unverify(tools.cfg, name), other)
    monkeypatch.setattr(doctor, "load_config", lambda d: cfg)
    got = find(doc()[0], "tables")
    assert len(got) == 2 and all(x.startswith("WARN") for x in got)
    assert name in got[0]


# tools


def test_oda_unset_warns(tools):
    tools.maps["parsing"]["odafc_path"] = None
    assert find(doc()[0], "oda")[0].startswith("WARN")


def test_oda_missing_fails(tools):
    tools.oda.unlink()
    assert find(doc()[0], "oda")[0].startswith("FAIL")


def test_console_unset_warns(tools):
    tools.maps["parsing"]["accoreconsole_path"] = None
    text, _ = doc()
    assert find(text, "console")[0].startswith("WARN")
    assert find(text, "plugin")[0].startswith("NOT CHECKED")
    assert not tools.calls


def test_console_missing_fails(tools):
    tools.exe.unlink()
    assert find(doc()[0], "console")[0].startswith("FAIL")
    assert not tools.calls


def test_console_smoke_passes_and_loads_plugin(tools):
    text, _ = doc()
    assert find(text, "console")[0].startswith("PASS  console  ")
    script = tools.calls[0][1].splitlines()
    assert script[:4] == ["FILEDIA", "0", "NETLOAD", tools.dll.as_posix()]
    assert find(text, "plugin") == [f"NOT CHECKED  plugin  {doctor.NO_REFUSAL_TEXT}"]
    assert str(tools.dll) in find(text, "plugin_file")[0]


def test_console_smoke_crash_fails(tools, monkeypatch):
    def boom(*a):
        raise ExtractError("AutoCAD Core Console could not start (OSError)")

    monkeypatch.setattr(doctor, "run_tool", boom)
    text, code = doc()
    assert code == 0 and find(text, "console")[0].startswith("FAIL  console  ")
    assert find(text, "plugin")[0].startswith("NOT CHECKED")


def test_console_smoke_timeout_fails(tools, monkeypatch):
    def slow(*a):
        raise ExtractError("AutoCAD Core Console timed out after 120 s")

    monkeypatch.setattr(doctor, "run_tool", slow)
    assert "timed out" in find(doc()[0], "console")[0]


def test_plugin_path_with_space_fails(tools):
    spaced = tools.dll.parent / "a b" / "p.dll"
    spaced.parent.mkdir()
    spaced.write_bytes(b"x")
    tools.maps["parsing"]["acad_plugin_dll"] = str(spaced)
    assert "holds a space" in find(doc()[0], "plugin")[0]
    assert "NETLOAD" not in tools.calls[0][1]


def test_plugin_missing_fails(tools):
    tools.dll.unlink()
    assert find(doc()[0], "plugin")[0].startswith("FAIL  plugin  ")


def test_plugin_refused_fails(tools, monkeypatch):
    fake_dump(monkeypatch, write=False)
    text, code = doc(tools.drawing)
    line = find(text, "plugin")[0]
    assert code == 0 and line.startswith("FAIL  plugin  ") and "TRUSTEDPATHS" in line
    assert "owner" in line


def test_plugin_refusal_unreadable_not_checked(tools):
    assert find(doc()[0], "plugin")[0].startswith("NOT CHECKED  plugin  the smoke run cannot")


def test_plugin_old_schema_warns(tools, monkeypatch):
    fake_dump(monkeypatch, version="1.0")
    line = find(doc(tools.drawing)[0], "plugin")[0]
    assert line.startswith("WARN  plugin  ") and "schema_version 1.0" in line


def test_plugin_current_schema_passes(tools, monkeypatch):
    fake_dump(monkeypatch)
    text, _ = doc(tools.drawing)
    line = find(text, "plugin")[0]
    assert line.startswith("PASS  plugin  loaded")
    assert f"schema_version {rawdrawing.SCHEMA_VERSION}" in line
    assert sha256_of(tools.dll) in text


def test_drawing_not_found(tools, tmp_path):
    text, code = doc(tmp_path / "none.dwg")
    assert code == 0 and find(text, "drawing")[0].startswith("FAIL")


def test_drawing_original_unchanged(tools, monkeypatch):
    fake_dump(monkeypatch)
    before = sha256_of(tools.drawing)
    doc(tools.drawing)
    assert sha256_of(tools.drawing) == before


# safety


def test_smoke_script_touches_no_setting(tools):
    doc()
    script = tools.calls[0][1].upper()
    assert "TRUSTEDPATHS" not in script and "SETVAR" not in script
    assert "SECURELOAD" not in script


def test_doctor_writes_no_file(tools, tmp_path, monkeypatch):
    t = tmp_path / "tmp"
    t.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(t))
    fake_dump(monkeypatch)
    before = set(tools.drawing.parent.iterdir())
    doc(tools.drawing)
    assert list(t.iterdir()) == []
    assert set(tools.drawing.parent.iterdir()) == before


def test_doctor_imports_no_model_or_extra():
    bad = [
        "torch",
        "onnxruntime",
        "transformers",
        "ollama",
        "ezdxf",
        "pdfplumber",
        "urllib.request",
    ]
    code = (
        "import sys,pathlib;from redline.tools import doctor;"
        f"doctor.run(pathlib.Path(r'{TEST_CFG}'),None,False);"
        f"print([m for m in {bad!r} if m in sys.modules])"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert r.stdout.strip() == "[]"


# licences


def rows():
    text, code = doc(licences=True)
    assert code == 0
    return text, list(csv.DictReader(io.StringIO(text)))


def test_licences_csv_columns():
    text, _ = rows()
    assert text.splitlines()[0] == "package,version,licence,read_from,licence_files,group,status"


def test_licences_every_requirement_listed():
    _, r = rows()
    names = {x["package"].lower() for x in r}
    assert {"pyyaml", "jinja2", "openpyxl", "markupsafe"} <= names
    assert all(x["group"] in ("base", "dxf", "pdf", "dev") for x in r)


class _Md(dict):
    def get_all(self, k):
        return self.get(k)


def test_licences_read_order():
    md = _Md(
        {
            "License-Expression": "MIT",
            "License": "BSD",
            "Classifier": ["License :: BSD License"],
        }
    )
    assert doctor._licence(md) == ("MIT", "License-Expression")
    md.pop("License-Expression")
    assert doctor._licence(md) == ("BSD", "License")
    md.pop("License")
    assert doctor._licence(md) == ("BSD", "classifier")
    assert doctor._licence(_Md()) == ("", "")


def test_licences_review_status():
    _, r = rows()
    for x in r:
        if not x["licence"]:
            assert x["status"] == "REVIEW"
    by = {x["package"].lower(): x for x in r}
    assert by["pyyaml"]["licence"] == "MIT"
    assert by["pyyaml"]["status"] == "listed"
    assert {x["status"] for x in r} <= {"listed", "REVIEW"}


def test_licence_with_exception_is_review():
    assert doctor._listed("Apache-2.0")
    assert not doctor._listed("Apache-2.0 WITH LLVM-exception")
    assert not doctor._listed("")


def test_licences_without_distribution(monkeypatch):
    def gone(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(doctor.metadata, "requires", gone)
    text, code = doc(licences=True)
    assert code == 0 and text == ",".join(doctor._HEADER)


# review R5.1


def test_console_smoke_nonzero_exit_fails(tools, monkeypatch):
    monkeypatch.setattr(doctor, "run_tool", lambda *a: 3221225477)
    text, code = doc()
    line = find(text, "console")[0]
    assert code == 0 and line.startswith("FAIL  console  ")
    assert "0xc0000005" in line and "PASS  console" not in text


def test_console_nonzero_exit_plugin_not_checked(tools, monkeypatch):
    monkeypatch.setattr(doctor, "run_tool", lambda *a: 1)
    text, _ = doc(tools.drawing)
    assert find(text, "plugin")[0].startswith("NOT CHECKED  plugin  the core console did not run")


def test_packages_not_installed_not_checked(monkeypatch):
    def gone(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(doctor.metadata, "requires", gone)
    assert doctor._requirements() == []
    assert doctor._check_packages()[0][0] == "NOT CHECKED"


def test_plugin_unreadable_fails(tools, monkeypatch):
    def locked(path):
        raise ExtractError("RedlinePlugin.dll could not be read")

    monkeypatch.setattr(doctor, "sha256_of", locked)
    text, code = doc()
    assert code == 0 and find(text, "plugin_file")[0].startswith("FAIL  plugin_file  ")


def test_in_range_unknown_operator():
    assert not doctor._in_range("2.0", "~=3.1")
    assert not doctor._in_range("2.0", ">=1.0,===2.0")
    assert doctor._in_range("2.0", ">=1.0,<3")
    assert doctor._in_range("2.0", "")


def test_in_range_unparseable_version():
    assert not doctor._in_range("0.11.9rc1", ">=0.11.9,<0.12")
    assert not doctor._in_range("dev", ">=1")
    assert doctor._in_range("1.4.2+local", ">=1.4,<2")
