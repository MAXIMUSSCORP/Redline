import copy
import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from redline import rawdrawing
from redline.config import load_config
from redline.extract import ExtractError, Unavailable, acad_console, sha256_of

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "samples" / "dwg" / "panel_sheet.acad_plugin.rawdrawing.json"


@pytest.fixture
def env(tmp_path, test_cfg):
    """A config whose tool paths exist, and a drawing."""
    exe = tmp_path / "bin" / "accoreconsole.exe"
    dll = tmp_path / "bin" / "RedlinePlugin.dll"
    exe.parent.mkdir()
    exe.write_bytes(b"x")
    dll.write_bytes(b"x")
    drawing = tmp_path / "work" / "my drawing.dwg"
    drawing.parent.mkdir()
    drawing.write_bytes(b"drawing bytes")
    maps = copy.deepcopy(test_cfg.column_maps)
    maps["parsing"].update(
        accoreconsole_path=str(exe), acad_plugin_dll=str(dll), dxf_extractor_timeout_s=5
    )
    return SimpleNamespace(
        cfg=replace(test_cfg, column_maps=maps),
        exe=str(exe),
        dll=str(dll),
        drawing=drawing,
        tmp=tmp_path,
    )


def fake_console(monkeypatch, write=None, *, code=0, timeout=False):
    """Replace Popen. write(st) may create the output file. Returns what the call saw."""
    st = SimpleNamespace(args=None, kw=None, script=None, killed=False, runs=[], calls=0)

    class Proc:
        pid = 4242

        def __init__(self, args, **kw):
            st.calls += 1
            st.args, st.kw = args, kw
            script = Path(args[args.index("/s") + 1])
            st.script = script.read_text(encoding="utf-8")
            st.out = Path(st.script.splitlines()[-1])
            st.copy = Path(args[args.index("/i") + 1])
            st.cwd = Path(kw["cwd"])
            st.input_hash = sha256_of(st.copy)
            if write:
                write(st)

        def wait(self, timeout=None):
            if hang:
                raise subprocess.TimeoutExpired(st.args, timeout)
            return code

        def kill(self):
            st.killed = True

    hang = timeout
    monkeypatch.setattr(subprocess, "Popen", Proc)
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: st.runs.append(args))
    return st


def write_valid(st):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["source_sha256"] = st.input_hash
    st.out.write_text(json.dumps(data), encoding="utf-8")


def test_acad_missing_accoreconsole_is_unavailable_with_reason(env):
    env.cfg.column_maps["parsing"]["accoreconsole_path"] = None
    with pytest.raises(Unavailable, match="accoreconsole_path is not set"):
        acad_console.extract(env.drawing, env.cfg)
    env.cfg.column_maps["parsing"]["accoreconsole_path"] = str(env.tmp / "nope" / "a.exe")
    with pytest.raises(Unavailable, match="accoreconsole_path does not exist"):
        acad_console.extract(env.drawing, env.cfg)


def test_acad_missing_plugin_dll_is_unavailable_with_reason(env):
    env.cfg.column_maps["parsing"]["acad_plugin_dll"] = None
    with pytest.raises(Unavailable, match="acad_plugin_dll is not set"):
        acad_console.extract(env.drawing, env.cfg)
    env.cfg.column_maps["parsing"]["acad_plugin_dll"] = str(env.tmp / "nope" / "p.dll")
    with pytest.raises(Unavailable, match="acad_plugin_dll does not exist"):
        acad_console.extract(env.drawing, env.cfg)


def test_acad_dll_path_with_space_is_unavailable(env):
    spaced = env.tmp / "a b" / "RedlinePlugin.dll"
    spaced.parent.mkdir()
    spaced.write_bytes(b"x")
    env.cfg.column_maps["parsing"]["acad_plugin_dll"] = str(spaced)
    with pytest.raises(Unavailable, match="acad_plugin_dll path holds a space"):
        acad_console.extract(env.drawing, env.cfg)


def test_acad_timeout_raises_extract_error(env, monkeypatch):
    fake_console(monkeypatch, timeout=True)
    with pytest.raises(ExtractError, match="timed out after 5 s") as err:
        acad_console.extract(env.drawing, env.cfg)
    assert not isinstance(err.value, Unavailable)


def test_acad_timeout_kills_process(env, monkeypatch):
    st = fake_console(monkeypatch, timeout=True)
    with pytest.raises(ExtractError):
        acad_console.extract(env.drawing, env.cfg)
    assert st.killed
    if sys.platform == "win32":
        assert st.runs == [["taskkill", "/T", "/F", "/PID", "4242"]]


def test_acad_no_output_json_raises_extract_error(env, monkeypatch):
    fake_console(monkeypatch)
    with pytest.raises(ExtractError, match="wrote no output file"):
        acad_console.extract(env.drawing, env.cfg)


def test_acad_invalid_output_raises_extract_error(env, monkeypatch):
    def write(st):
        st.out.write_text("{not json", encoding="utf-8")

    fake_console(monkeypatch, write)
    with pytest.raises(ExtractError, match="cannot be read"):
        acad_console.extract(env.drawing, env.cfg)

    def write_wrong(st):
        st.out.write_text('{"schema_version": "1.0"}', encoding="utf-8")

    fake_console(monkeypatch, write_wrong)
    with pytest.raises(ExtractError, match="not valid RawDrawing: missing required field"):
        acad_console.extract(env.drawing, env.cfg)


def test_acad_output_over_cap_raises(env, monkeypatch):
    fake_console(monkeypatch, write_valid)
    monkeypatch.setattr(rawdrawing, "MAX_JSON_BYTES", 50)
    with pytest.raises(ExtractError, match="MAX_JSON_BYTES"):
        acad_console.extract(env.drawing, env.cfg)


def test_acad_exit_code_ignored(env, monkeypatch):
    fake_console(monkeypatch, write_valid, code=-1073741819)
    assert acad_console.extract(env.drawing, env.cfg)["extractor"] == "acad_plugin"
    fake_console(monkeypatch, code=0)  # a clean exit does not make a missing file good
    with pytest.raises(ExtractError):
        acad_console.extract(env.drawing, env.cfg)


def test_acad_args_list_no_shell(env, monkeypatch):
    st = fake_console(monkeypatch, write_valid)
    acad_console.extract(env.drawing, env.cfg)
    a = st.args
    assert isinstance(a, list)
    assert a[0] == str(Path(env.exe))
    assert a[1] == "/i" and a[3] == "/s" and a[5:] == ["/l", "en-US"]
    assert "/readonly" not in a
    assert st.kw["shell"] is False
    assert st.kw["stdin"] == subprocess.DEVNULL
    assert st.cwd.parent == Path(tempfile.gettempdir())


def test_acad_script_lines_pinned(env, monkeypatch):
    st = fake_console(monkeypatch, write_valid)
    acad_console.extract(env.drawing, env.cfg)
    out = str(st.cwd / "out.json").replace("\\", "/")
    dll = str(Path(env.dll)).replace("\\", "/")
    assert st.script.splitlines() == ["FILEDIA", "0", "NETLOAD", dll, "REDLINE_DUMP", out]
    assert "\\" not in st.script


def test_acad_input_path_not_in_script(env, monkeypatch):
    st = fake_console(monkeypatch, write_valid)
    acad_console.extract(env.drawing, env.cfg)
    assert "my drawing" not in st.script
    assert str(env.drawing.parent) not in st.script
    assert st.copy.name == "my drawing.dwg"  # argv holds the copy, never the original
    assert st.copy != env.drawing


def test_acad_temp_dir_removed(env, monkeypatch):
    root = env.tmp / "tmproot"
    root.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(root))
    st = fake_console(monkeypatch, write_valid)
    acad_console.extract(env.drawing, env.cfg)
    assert st.cwd.parent == root
    assert list(root.iterdir()) == []
    fake_console(monkeypatch, timeout=True)
    with pytest.raises(ExtractError):
        acad_console.extract(env.drawing, env.cfg)
    assert list(root.iterdir()) == []


def test_acad_input_hash_unchanged_checked(env, monkeypatch):
    fake_console(monkeypatch, write_valid)
    data = acad_console.extract(env.drawing, env.cfg)
    assert "the drawing changed while it was read" not in data["document"]["warnings"]

    def write_and_touch(st):
        write_valid(st)
        env.drawing.write_bytes(b"changed")

    fake_console(monkeypatch, write_and_touch)
    data = acad_console.extract(env.drawing, env.cfg)
    assert "the drawing changed while it was read" in data["document"]["warnings"]


def test_acad_result_validates_and_reported_hash_is_compared(env, monkeypatch):
    fake_console(monkeypatch, write_valid)
    data = acad_console.extract(env.drawing, env.cfg)
    assert rawdrawing.validate(data).ok
    assert data["source_sha256"] == sha256_of(env.drawing)

    def write_other_hash(st):
        write_valid(st)
        d = json.loads(st.out.read_text(encoding="utf-8"))
        d["source_sha256"] = "0" * 64
        st.out.write_text(json.dumps(d), encoding="utf-8")

    fake_console(monkeypatch, write_other_hash)
    warnings = acad_console.extract(env.drawing, env.cfg)["document"]["warnings"]
    assert "the hash the plugin reported differs from the input file" in warnings


def test_acad_input_file_absent_raises_extract_error(env, monkeypatch):
    st = fake_console(monkeypatch, write_valid)
    with pytest.raises(ExtractError, match="was not found"):
        acad_console.extract(env.tmp / "gone.dwg", env.cfg)
    assert st.calls == 0


@pytest.mark.live
def test_live_acad_console_dumps_sample():
    cfg = load_config(ROOT / "config")
    sample = ROOT / "gold" / "dwg" / "etsu_entc2160_m04" / "Tiny Electrical Plan.dwg"
    try:
        data = acad_console.extract(sample, cfg)
    except Unavailable as e:
        pytest.skip(str(e))
    except ExtractError:
        if not sample.is_file():
            pytest.skip(f"AutoCAD sample drawing not found: {sample}")
        raise
    assert data["extractor"] == "acad_plugin"
    assert data["entities"]


def test_non_ascii_temp_path_is_unavailable(env, monkeypatch):
    root = env.tmp / "tmp_\u00e9\u00e8"
    root.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(root))
    st = fake_console(monkeypatch, write_valid)
    with pytest.raises(Unavailable, match="ASCII"):
        acad_console.extract(env.drawing, env.cfg)
    assert st.calls == 0 and list(root.iterdir()) == []
