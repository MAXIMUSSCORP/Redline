import copy
import csv
from pathlib import Path

from redline.config import load_config
from redline.rawdrawing import read
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
    return list(csv.reader((out / "xcheck.csv").open(encoding="utf-8", newline="")))


def test_batch_folder_without_subfolders(tmp_path):
    d = touch(tmp_path / "in", "a.dwg", "notes.txt", "b.json")
    touch(d / "sub", "deep.dwg")
    seen = []
    run_batch([d], CFG, tmp_path / "o", pair(seen=seen))
    assert set(seen) == {"a.dwg"}


def test_batch_dwg_and_dxf_in_name_order(tmp_path):
    d = touch(tmp_path / "in", "c.dwg", "A.dxf", "b.DWG")
    seen = []
    run_batch([d], CFG, tmp_path / "o", pair(seen=seen))
    assert seen[::2] == ["A.dxf", "b.DWG", "c.dwg"]


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
