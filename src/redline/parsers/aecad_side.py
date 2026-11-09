"""Reads an AutoCAD Electrical project file (`.wdp`) as a list of the drawings it names.

The file is plain text, one entry per line. Line shapes found in the 20 sample `.wdp`
files:

- Project description line: `*` then a number in square brackets, then free text. These
  hold titles, customer and job fields. Listed as not read.
- Project setting line: `?` then a number in square brackets, then a value. These hold
  wire numbering, tag format, attribute names and similar options. Listed as not read.
- Path and option line: `+` then a number in square brackets, then a value. Some hold
  folder lists or menu file names, some hold flags. A path here is never opened. Listed
  as not read.
- Drawing description line: three equals signs then free text. A drawing can have
  several in a row. Listed as not read.
- Section marker: five equals signs, `SUB=`, then a kind word (the samples use
  schematic, schematics and panel). Listed as not read.
- Short group marker: one equals sign then a one-letter code. Seen in one sample, placed
  between drawing names. Listed as not read.
- Drawing line: a bare file name. The name carries a `.dwg` extension in most samples
  and none in one sample. It follows its description lines and section marker. This is
  the only shape that is read, and only as a name.
- Blank line: skipped, in some samples between every pair of lines.
- A file with settings and no drawing line (one sample): lists no drawing.
- Any other line: listed as an unknown shape.

Seen in the samples and handled: CRLF line ends, a file with the old Windows code page
and no BOM, and two files in East Asian code pages. The reader decodes with BOM, then
utf-8, then cp1252, as `csv_xlsx` does. It cannot tell an East Asian code page from
cp1252: a file whose bytes cp1252 accepts is read with the wrong characters, which only
affects lines that are not read, and a file whose bytes cp1252 refuses is an InputError.
The encoding used is named in coverage.

No path in the file is opened. The project database (`.mdb`, `.accdb`) is not read.
"""

from __future__ import annotations

import re
from pathlib import Path

from redline.config import Config
from redline.model import Confidence, CoverageEntry, Method, Source, Unparsed
from redline.parsers.csv_xlsx import InputError, _decode
from redline.parsers.tabular import Parsed

SUFFIXES = (".wdp",)
MAX_LINE = 260  # a longer line is not a file name
_NOT_READ = "project file line, not read"
_SETTING = re.compile(r"[*?+]\[\d+\]")
_MARKER = re.compile(r"===(?!=)|=====SUB=|=[^=\s]{1,4}$")
_RAW = 200


def _is_drawing(line: str) -> bool:
    return (
        len(line) <= MAX_LINE and line[0] not in "*?+=" and line.isprintable() and "[" not in line
    )


def parse_file(path: Path, cfg: Config) -> Parsed:
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as e:
        raise InputError(f"cannot read the file: {e.strerror or type(e).__name__}") from e
    text, encoding = _decode(data)
    if "\x00" in text:
        raise InputError("the file holds NUL bytes, so it is not a text project file")
    verified = (cfg.column_maps.get("aecad_project") or {}).get("wdp_verified") is True
    suffix = "" if verified else "; format not verified"
    out = Parsed()
    for n, line in enumerate(re.split(r"\r\n|\r|\n", text), 1):
        line = line.strip()
        if not line:
            continue
        if _SETTING.match(line) or _MARKER.match(line):
            reason = _NOT_READ
        elif _is_drawing(line):
            what = f"{line} listed in project {path.name}; not read from this file{suffix}"
            out.coverage.append(CoverageEntry(path.name, "drawing list", what, "wdp", ""))
            continue
        else:
            reason = "line shape not known"
        src = Source(path.name, f"line={n}", Method.CSV, Confidence.LOW)
        out.unparsed.append(Unparsed("row", line[:_RAW], reason, src))
    listed = len(out.coverage)
    out.coverage.append(
        CoverageEntry(
            path.name,
            "file",
            f"{listed} drawings listed, {len(out.unparsed)} lines not read; "
            f"no panel read; encoding {encoding}{suffix}",
            "wdp",
            "",
        )
    )
    return out
