import builtins
from dataclasses import replace
from pathlib import Path

import pytest

from redline.parsers.aecad_side import SUFFIXES, parse_file
from redline.parsers.csv_xlsx import InputError

PROJECT = """\
*[1]Made-up project title
*[2]Made-up customer
?[5]%S%N
+[1]C:/made-up/libs/;C:/made-up/more/
===Floor one
===lighting
=====SUB=SCHEMATIC
plan_01.dwg
=X
===Roof
plan_02
"""


def write(tmp_path, text, name="made_up.wdp"):
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    return path


def drawings(parsed):
    return [c for c in parsed.coverage if c.unit == "drawing list"]


def test_suffixes():
    assert SUFFIXES == (".wdp",)


def test_wdp_drawing_list_in_coverage(tmp_path, test_cfg):
    parsed = parse_file(write(tmp_path, PROJECT), test_cfg)
    assert [c.what_read.split(" listed")[0] for c in drawings(parsed)] == ["plan_01.dwg", "plan_02"]
    first = drawings(parsed)[0]
    assert first.file == "made_up.wdp" and first.method == "wdp"
    assert "listed in project made_up.wdp; not read from this file" in first.what_read
    assert "format not verified" in first.what_read
    assert parsed.panels == []


def test_wdp_verified_drops_the_note(tmp_path, test_cfg):
    cm = {**test_cfg.column_maps, "aecad_project": {"wdp_verified": True}}
    parsed = parse_file(write(tmp_path, PROJECT), replace(test_cfg, column_maps=cm))
    assert all("not verified" not in c.what_read for c in parsed.coverage)


def test_wdp_unknown_line_listed(tmp_path, test_cfg):
    parsed = parse_file(write(tmp_path, "plan_01.dwg\n*oops\n====\n[1]x\n=toolong\n"), test_cfg)
    assert [u.raw for u in parsed.unparsed] == ["*oops", "====", "[1]x", "=toolong"]
    assert {u.reason for u in parsed.unparsed} == {"line shape not known"}
    assert [u.source.locator for u in parsed.unparsed] == ["line=2", "line=3", "line=4", "line=5"]
    assert len(drawings(parsed)) == 1


def test_wdp_description_lines_listed_not_read(tmp_path, test_cfg):
    parsed = parse_file(write(tmp_path, PROJECT), test_cfg)
    assert {u.kind for u in parsed.unparsed} == {"row"}
    assert {u.reason for u in parsed.unparsed} == {"project file line, not read"}
    raws = [u.raw for u in parsed.unparsed]
    assert len(raws) == 9
    assert raws[0] == "*[1]Made-up project title" and "=X" in raws
    assert not any("plan_0" in r for r in raws)


def test_wdp_paths_never_opened(tmp_path, test_cfg, monkeypatch):
    target = tmp_path / "secret.txt"
    target.write_text("x")
    wdp = write(tmp_path, f"+[1]{target}\n{target}\nplan.dwg\n")
    opened = []
    real_open, real_read = builtins.open, Path.read_bytes
    monkeypatch.setattr(
        builtins, "open", lambda f, *a, **k: opened.append(str(f)) or real_open(f, *a, **k)
    )
    monkeypatch.setattr(
        Path, "read_bytes", lambda self: opened.append(str(self)) or real_read(self)
    )
    parse_file(wdp, test_cfg)
    assert opened == [str(wdp)]


def test_wdp_unreadable_is_input_error(tmp_path, test_cfg):
    for data in (b"plan.dwg\n\x00\x00\n", b"\xff\xfe\x00\x00", b"plan\x81.dwg\n"):
        with pytest.raises(InputError):
            parse_file(write(tmp_path, data), test_cfg)
    with pytest.raises(InputError):
        parse_file(tmp_path / "missing.wdp", test_cfg)


def test_wdp_encoding(tmp_path, test_cfg):
    def read(data):
        parsed = parse_file(write(tmp_path, data), test_cfg)
        return parsed.coverage[-1].what_read, drawings(parsed)

    assert "encoding utf-8;" in read(b"*[1]caf\xc3\xa9\nplan.dwg\n")[0] + ";"
    assert "encoding utf-8 with BOM" in read(b"\xef\xbb\xbfplan.dwg\n")[0]
    what, listed = read(b"*[1]caf\xe9\r\nplan.dwg\r\n")
    assert "encoding cp1252" in what and len(listed) == 1


def test_wdp_name_only(tmp_path, test_cfg):
    sub = tmp_path / "deep" / "dir"
    sub.mkdir(parents=True)
    parsed = parse_file(write(sub, PROJECT), test_cfg)
    files = {c.file for c in parsed.coverage} | {u.source.file for u in parsed.unparsed}
    assert files == {"made_up.wdp"}


def test_blank_lines_and_line_ends_are_skipped(tmp_path, test_cfg):
    parsed = parse_file(write(tmp_path, "a.dwg\r\r\n\r\nb.dwg\rc.dwg\n\n"), test_cfg)
    assert len(drawings(parsed)) == 3 and parsed.unparsed == []
    assert parsed.coverage[-1].unit == "file"


def test_empty_file_is_read_and_lists_nothing(tmp_path, test_cfg):
    parsed = parse_file(write(tmp_path, ""), test_cfg)
    assert drawings(parsed) == [] and "0 drawings listed" in parsed.coverage[-1].what_read
