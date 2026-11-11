import copy
import csv
import os
import subprocess
import sys
from pathlib import Path

from redline.config import load_config
from redline.rawdrawing import read
from redline.tools import xcheck
from redline.tools.xcheck import run_batch

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples" / "dwg"
PLUGIN = read(SAMPLES / "panel_sheet.acad_plugin.rawdrawing.json")
FALLBACK = read(SAMPLES / "panel_sheet.oda_ezdxf.rawdrawing.json")
CFG = load_config(ROOT / "tests" / "test_config")


def touch(folder, *names):
    folder.mkdir(exist_ok=True)
    for n in names:
        (folder / n).write_bytes(b"x")
    return folder


def pair(a=PLUGIN, b=FALLBACK, seen=None):
    def mk(d):
        def f(path, cfg):
            if seen is not None:
                seen.append(path.name)
            if d is None:
                raise RuntimeError("no tool\nhere")
            return d

        return f

    return {"acad_plugin": mk(a), "oda_ezdxf": mk(b)}


def rows_of(out):
    with (out / "xcheck.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def test_batch_folder_without_subfolders(tmp_path):
    d = touch(tmp_path / "in", "a.dwg", "notes.txt", "b.json")
    touch(d / "sub", "deep.dwg")
    seen = []
    run_batch([d], CFG, tmp_path / "o", pair(seen=seen))
    assert set(seen) == {"a.dwg"}


def test_batch_dwg_and_dxf_in_name_order(tmp_path):
    # Case-sensitive order puts B.dwg first; NTFS lists a.dwg first, so sorted() is what decides.
    d = touch(tmp_path / "in", "a.dwg", "B.dwg", "c.dwg")
    seen = []
    run_batch([d], CFG, tmp_path / "o", pair(seen=seen))
    assert seen[::2] == ["B.dwg", "a.dwg", "c.dwg"]


def test_batch_csv_columns(tmp_path):
    d = touch(tmp_path / "in", "a.dwg")
    run_batch([d], CFG, tmp_path / "o", pair(b=None))
    r = rows_of(tmp_path / "o")
    assert r[0] == ["file", "item", "primary", "fallback"]
    tables = next(x for x in r if x[1] == "tables")
    assert tables == ["a.dwg", "tables", "3", "not run"]


def test_batch_fallback_loss_summary(tmp_path):
    d = touch(tmp_path / "in", "a.dwg", "b.dwg")
    text, code = run_batch([d], CFG, tmp_path / "o", pair())
    line = next(ln.split() for ln in text.splitlines() if ln.startswith("cells evaluated"))
    assert line[-3:] == ["710", "0", "2"]
    assert code == 0


def test_batch_one_failure_does_not_stop(tmp_path):
    d = touch(tmp_path / "in", "a.dwg", "b.dwg")

    def flaky(path, cfg):
        if path.name == "a.dwg":
            raise ValueError("bad file")
        return PLUGIN

    text, code = run_batch(
        [d], CFG, tmp_path / "o", {"acad_plugin": flaky, "oda_ezdxf": pair()["oda_ezdxf"]}
    )
    assert code == 0
    assert "a.dwg: acad_plugin read nothing: ValueError: bad file" in text
    assert any(x[0] == "b.dwg" for x in rows_of(tmp_path / "o"))


def test_batch_exit_2_when_nothing_read(tmp_path):
    d = touch(tmp_path / "in", "a.dwg")
    text, code = run_batch([d], CFG, tmp_path / "o", pair(None, None))
    assert code == 2
    assert "No extractor read any file" in text
    assert (tmp_path / "o" / "xcheck.csv").exists()


def test_batch_text_difference_files_listed(tmp_path):
    d = touch(tmp_path / "in", "a.dwg")
    changed = copy.deepcopy(FALLBACK)
    next(e for e in changed["entities"] if e.get("text") == "LP-11")["table"]["cells"][5][
        "text"
    ] = "z"
    text, _ = run_batch([d], CFG, tmp_path / "o", pair(b=changed))
    assert "Files with cell text differences: a.dwg." in text
    text, _ = run_batch([d], CFG, tmp_path / "o2", pair())
    assert "Files with cell text differences: none." in text


def test_batch_unread_reason_listed(tmp_path):
    d = touch(tmp_path / "in", "a.dwg")
    text, _ = run_batch([d], CFG, tmp_path / "o", pair(b=None))
    assert "a.dwg: oda_ezdxf read nothing: RuntimeError: no tool here" in text
    assert "acad_plugin read nothing" not in text


def test_batch_csv_guarded(tmp_path):
    d = touch(tmp_path / "in", "=cmd.dwg")
    run_batch([d], CFG, tmp_path / "o", pair())
    assert {x[0] for x in rows_of(tmp_path / "o")[1:]} == {"'=cmd.dwg"}


def test_batch_csv_repeats_byte_identical(tmp_path):
    d = touch(tmp_path / "in", "a.dwg", "b.dxf")
    run_batch([d], CFG, tmp_path / "o1", pair())
    run_batch([d], CFG, tmp_path / "o2", pair())
    assert (tmp_path / "o1" / "xcheck.csv").read_bytes() == (
        tmp_path / "o2" / "xcheck.csv"
    ).read_bytes()


def test_batch_unwritable_output_refused_before_reads(tmp_path, monkeypatch):
    d = touch(tmp_path / "in", "a.dwg")
    real = open

    def locked(file, mode="r", *a, **k):
        if str(file).endswith("xcheck.csv"):
            raise PermissionError(13, "in use")
        return real(file, mode, *a, **k)

    monkeypatch.setattr("builtins.open", locked)
    seen = []
    text, code = run_batch([d], CFG, tmp_path / "o", pair(seen=seen))
    assert code == 2
    assert text.startswith("redline: cannot write ")
    assert seen == []


def test_batch_csv_not_written_still_prints_summary(tmp_path, monkeypatch):
    d = touch(tmp_path / "in", "a.dwg")

    def boom(path, rows):
        raise PermissionError(13, "in use")

    monkeypatch.setattr(xcheck, "_write_csv", boom)
    text, code = run_batch([d], CFG, tmp_path / "o", pair())
    assert code == 0
    assert "xcheck batch: 1 files" in text
    assert "xcheck.csv was not written" in text


def test_batch_same_name_files_in_two_folders(tmp_path):
    a = touch(tmp_path / "a", "panel.dwg")
    b = touch(tmp_path / "b", "panel.dwg")
    changed = copy.deepcopy(FALLBACK)
    next(e for e in changed["entities"] if e.get("text") == "LP-11")["table"]["cells"][5][
        "text"
    ] = "z"

    def f(path, cfg):
        return PLUGIN

    def g(path, cfg):
        return changed if path.parent.name == "b" else FALLBACK

    text, _ = run_batch([a, b], CFG, tmp_path / "o", {"acad_plugin": f, "oda_ezdxf": g})
    assert {x[0] for x in rows_of(tmp_path / "o")[1:]} == {"a/panel.dwg", "b/panel.dwg"}
    assert "Files with cell text differences: b/panel.dwg." in text


def test_batch_skips_listed(tmp_path):
    d = touch(tmp_path / "in", "a.dwg", "notes.txt")
    touch(d / "sub", "deep.dwg")
    text, code = run_batch([d], CFG, tmp_path / "o", pair())
    assert code == 0
    assert "Not read:" in text
    assert "in/sub: subfolders are not read" in text
    assert "in/notes.txt: not a .dwg or .dxf file" in text


def test_batch_unreadable_folder_listed(tmp_path, monkeypatch):
    d = touch(tmp_path / "in", "a.dwg")
    ok = touch(tmp_path / "ok", "b.dwg")
    real = Path.iterdir

    def iterdir(self):
        if self.name == "in":
            raise PermissionError(13, "denied")
        return real(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    text, code = run_batch([d, ok], CFG, tmp_path / "o", pair())
    assert code == 0
    assert "in: folder cannot be read: PermissionError" in text


def test_batch_symlink_inputs_listed(tmp_path, monkeypatch):
    d = touch(tmp_path / "in", "a.dwg", "link.dwg")
    real = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "link.dwg" or real(self))
    seen = []
    text, _ = run_batch([d], CFG, tmp_path / "o", pair(seen=seen))
    assert set(seen) == {"a.dwg"}
    assert "in/link.dwg: symlinks are not read" in text


def test_batch_symlink_csv_refused(tmp_path, monkeypatch):
    d = touch(tmp_path / "in", "a.dwg")
    real = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "xcheck.csv" or real(self))
    seen = []
    text, code = run_batch([d], CFG, tmp_path / "o", pair(seen=seen))
    assert code == 2
    assert "symlink" in text
    assert seen == []


_HASHSEED_CODE = """
import sys
from pathlib import Path
from redline.config import load_config
from redline.rawdrawing import read
from redline.tools.xcheck import run_batch
s = Path(sys.argv[1])
a = read(s / "panel_sheet.acad_plugin.rawdrawing.json")
b = read(s / "panel_sheet.oda_ezdxf.rawdrawing.json")
run_batch([Path(sys.argv[2])], load_config(sys.argv[3]), Path(sys.argv[4]),
          {"acad_plugin": lambda p, c: a, "oda_ezdxf": lambda p, c: b})
"""


def test_batch_csv_identical_across_hash_seeds(tmp_path):
    d = touch(tmp_path / "in", "a.dwg", "b.dxf")
    outs = []
    for seed in ("1", "2"):
        out = tmp_path / f"o{seed}"
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONHASHSEED": seed}
        args = [str(SAMPLES), str(d), str(ROOT / "tests" / "test_config"), str(out)]
        p = subprocess.run(
            [sys.executable, "-c", _HASHSEED_CODE, *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert p.returncode == 0, p.stderr
        outs.append((out / "xcheck.csv").read_bytes())
    assert outs[0] == outs[1]
