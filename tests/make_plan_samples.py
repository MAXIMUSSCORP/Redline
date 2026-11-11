"""Writes the synthetic fire alarm plan sheets under samples/plans (TEST_* block names only).

Run: python tests/make_plan_samples.py [out_dir]. exits.csv and paths.csv are written by hand.
ezdxf writes time stamps and GUIDs, so tests compare INSERT lists, never bytes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import ezdxf

MM, UNITLESS = 4, 0  # $INSUNITS


def _doc(units: int, names: list[str]):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = units
    doc.appids.add("AcDbBlockRepBTag")
    for n in names:
        doc.blocks.new(n).add_line((0, 0), (100, 0))
    return doc


def _place(msp, name: str, points: list[tuple[float, float]]) -> None:
    for p in points:
        msp.add_blockref(name, p)


def sheet_fa101() -> ezdxf.document.Drawing:
    names = ["TEST_DOOR", "TEST_EXIT", "TEST_PULL", "TEST_EMLT", "TEST_SMOKE", "CHAIR", "TEST_HORN"]
    doc = _doc(MM, names)
    msp = doc.modelspace()
    _place(msp, "TEST_DOOR", [(0, 0), (20000, 0), (40000, 0)])
    _place(msp, "TEST_EXIT", [(500, 0), (20500, 0)])
    _place(msp, "test_exit", [(35000, 0)])  # written in lower case
    _place(msp, "TEST_PULL", [(1000, 0), (27000, 0), (41000, 0)])
    _place(msp, "TEST_EMLT", [(2000, 0), (18000, 0), (31000, 0), (38000, 0)])
    # A dynamic block insert is written against an anonymous *U block that names its source.
    anon = doc.blocks.new_anonymous_block("U")
    anon.add_line((0, 0), (100, 0))
    source = doc.block_records.get("TEST_EMLT")
    anon.block_record.set_xdata("AcDbBlockRepBTag", [(1005, source.dxf.handle)])
    msp.add_blockref(anon.name, (10000, 0))
    _place(msp, "TEST_SMOKE", [(5000, 3000), (15000, 3000), (25000, 3000), (35000, 3000)])
    _place(msp, "CHAIR", [(8000, -2000), (9000, -2000)])
    doc.blocks.new("FA_CLUSTER").add_blockref("TEST_HORN", (0, 0))
    msp.add_blockref("FA_CLUSTER", (12000, 4000))
    # A legend instance in a paper layout is counted per layout and never used in a distance.
    doc.layouts.new("FA-101").add_blockref("TEST_PULL", (20000, 1000))
    return doc


def sheet_fa102() -> ezdxf.document.Drawing:
    doc = _doc(UNITLESS, ["TEST_DOOR", "TEST_EXIT", "TEST_PULL", "TEST_EMLT"])
    msp = doc.modelspace()
    _place(msp, "TEST_DOOR", [(0, 0), (10000, 0)])
    _place(msp, "TEST_EXIT", [(500, 0), (10500, 0)])
    _place(msp, "TEST_PULL", [(1000, 0)])
    _place(msp, "TEST_EMLT", [(5000, 0)])
    return doc


def main(out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sheet_fa101().saveas(out / "sheet_fa101.dxf")
    sheet_fa102().saveas(out / "sheet_fa102.dxf")


if __name__ == "__main__":
    main(
        sys.argv[1]
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent / "samples" / "plans"
    )
