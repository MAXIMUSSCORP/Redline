"""Write the four synthetic PDF samples (stdlib only, byte-reproducible).

Run: python tests/make_pdf_samples.py samples/pdf
Rows come from samples/csv/two_panels.csv. No date, id or author is written.
"""

import csv
import sys
import zlib
from itertools import pairwise
from pathlib import Path

W, H = 1224, 792
CSV = Path(__file__).resolve().parent.parent / "samples" / "csv" / "two_panels.csv"

HEADER14 = [
    "Ckt", "Description", "Load (VA)", "Load Type", "Poles", "Phase", "Breaker",
    "Wire Sz.", "Material", "Insulation", "Conductors in Raceway", "Length",
    "Voltage", "Notes",
]  # fmt: skip
HEADER6 = ["Ckt", "Description", "Load (VA)", "Breaker", "Poles", "Wire Size"]
SHORT_CKTS = ("1", "2", "4", "6", "8", "10")


def lp1_rows() -> list[dict[str, str]]:
    with CSV.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["Panel"] == "LP-1"]


def full_rows() -> list[list[str]]:
    return [[r[h] for h in HEADER14] for r in lp1_rows()]


def short_rows() -> list[list[str]]:
    src = {r["Ckt"]: dict(r, **{"Wire Size": r["Wire Sz."]}) for r in lp1_rows()}
    return [[src[c][h] for h in HEADER6] for c in SHORT_CKTS]


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class Page:
    """Content stream builder; y is measured from the top edge."""

    def __init__(self) -> None:
        self.ops: list[str] = []

    def text(self, x, top, s, size=7.0, rot=False) -> None:
        m = f"0 1 -1 0 {x:g} {H - top:g}" if rot else f"1 0 0 1 {x:g} {H - top:g}"
        self.ops.append(f"BT /F1 {size:g} Tf {m} Tm ({esc(s)}) Tj ET")

    def line(self, x1, t1, x2, t2) -> None:
        self.ops.append(f"{x1:g} {H - t1:g} m {x2:g} {H - t2:g} l S")

    def rect(self, x, top, w, h) -> None:
        self.ops.append(f"{x:g} {H - top - h:g} {w:g} {h:g} re S")

    def strokes(self, x, top, s, size=7.0) -> None:
        # ponytail: pseudo-glyphs (3 segments in a 2x3 anchor grid), enough to be strokes
        gw, gh = size * 0.5, size * 0.7
        pts = [(i * gw, j * gh / 2) for j in range(3) for i in range(2)]
        for k, ch in enumerate(s):
            if ch == " ":
                continue
            ox = x + k * size * 0.62
            seq = [pts[(ord(ch) * (i + 3) + i * 7) % 6] for i in range(4)]
            for (ax, ay), (bx, by) in pairwise(seq):
                if (ax, ay) != (bx, by):
                    self.line(ox + ax, top - ay, ox + bx, top - by)

    def data(self) -> bytes:
        return ("0.5 w\n" + "\n".join(self.ops) + "\n").encode("latin-1")


def col_xs(rows, x0, size, gap):
    """Left edge of each column, plus the right edge of the last."""
    xs, x = [], x0
    for c in range(len(rows[0])):
        xs.append(x)
        x += max(len(r[c]) for r in rows) * size * 0.6 + gap
    return xs, x


def put_table(put, rows, x0, top, size, rowh, gap):
    xs, _ = col_xs(rows, x0, size, gap)
    for i, row in enumerate(rows):
        for x, cell in zip(xs, row):
            if cell:
                put(x, top + i * rowh + size, cell, size)
    return xs


def ruled_grid(p, rows, x0, top, size, rowh, pad):
    xs, end = col_xs(rows[1:], x0 + pad, size, 2 * pad)
    xs = [x - pad for x in xs] + [end - pad]
    for i, row in enumerate(rows):
        for c, s in enumerate(row):
            p.rect(xs[c], top + i * rowh, xs[c + 1] - xs[c], rowh)
            if s:
                p.text(xs[c] + pad, top + i * rowh + size + 3, s, size)


def title_block(p, sheet, rev, put=None):
    rows = [["SHEET NO.", sheet], ["REV", rev], ["PROJECT", "SAMPLE ONLY"]]
    for i, cells in enumerate(rows):
        for x, w, s in ((960, 90, cells[0]), (1050, 150, cells[1])):
            p.rect(x, 700 + i * 20, w, 20)
            (put or p.text)(x + 6, 700 + i * 20 + 14, s, 8)


def build_pdf(content: bytes, annots=(), image=None) -> bytes:
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        4: b"<< /Length %d >>\nstream\n" % len(content) + content + b"endstream",
        5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    res = "/Font << /F1 5 0 R >>"
    n = 6
    if image is not None:
        objs[n] = (
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode "
            b"/Length %d >>\nstream\n" % (W, H, len(image)) + image + b"\nendstream"
        )
        res += f" /XObject << /Im0 {n} 0 R >>"
        n += 1
    refs = []
    for x, top, w, h, s in annots:
        objs[n] = (
            f"<< /Type /Annot /Subtype /Text /Rect [{x:g} {H - top - h:g} "
            f"{x + w:g} {H - top:g}] /Contents ({esc(s)}) /F 28 >>"
        ).encode("latin-1")
        refs.append(f"{n} 0 R")
        n += 1
    ann = f" /Annots [{' '.join(refs)}]" if refs else ""
    objs[3] = (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Contents 4 0 R "
        f"/Resources << {res} >>{ann} >>"
    ).encode("latin-1")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\x00\n")  # NUL keeps git from text-converting
    offs = {}
    for k in sorted(objs):
        offs[k] = len(out)
        out += b"%d 0 obj\n" % k + objs[k] + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % n
    for k in range(1, n):
        out += b"%010d 00000 n \n" % offs[k]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (n, xref)
    return bytes(out)


def lp21(put):
    """LP-21: a panel line and the unruled 14-column table."""
    put(30, 40, "Panel LP-21", 9)
    return put_table(put, [HEADER14, *full_rows()], 30, 52, 6.5, 11, 14)


def panel_text() -> bytes:
    p = Page()
    lp21(lambda x, t, s, z=7: p.text(x, t, s, z))
    ruled_grid(p, [["Panel", "LP-22"], HEADER6, *short_rows()], 30, 330, 7, 15, 6)
    p.text(30, 500, "GENERAL NOTES", 9)
    p.text(30, 514, "1. SAMPLE ONLY, NOT FOR CONSTRUCTION.", 8)
    p.text(1190, 200, "NORTH", 9, rot=True)
    title_block(p, "E-501", "2")
    return build_pdf(p.data())


def shx_strokes() -> bytes:
    p = Page()
    xs = lp21(lambda x, t, s, z=7: p.strokes(x, t, s, z))
    bottom = 52 + 21 * 11
    for i in range(22):
        p.line(24, 52 + i * 11, xs[-1] + 80, 52 + i * 11)
    for x in xs:
        p.line(x - 6, 52, x - 6, bottom)
    title_block(p, "E-501", "2", put=lambda x, t, s, z: p.strokes(x, t, s, z))
    return build_pdf(p.data())


def shx_annot() -> bytes:
    p = Page()
    rows = [["Panel", "LP-23"], HEADER6, *short_rows()]
    xs, end = col_xs(rows[1:], 40, 7, 30)
    xs = xs + [end]
    top, rowh = 60, 18
    notes = []
    for i, row in enumerate(rows):
        t = top + i * rowh
        for j, s in enumerate(row):
            w = xs[j + 1] - xs[j]
            p.rect(xs[j] - 4, t, w, rowh)
            notes.append((xs[j], t + 3, w - 8, rowh - 6, s))
    # planted disagreement: a Helvetica word over the ckt 4 Breaker annotation
    p.text(xs[3], top + 4 * rowh + 12, "20", 7)
    title_block(p, "E-503", "1")
    return build_pdf(p.data(), annots=notes)


def scanned_panel() -> bytes:
    cols, rows_n, x0, y0, cw, rh = 8, 22, 60, 60, 140, 30
    raw = bytearray()
    for y in range(H):
        row = bytearray(b"\xff" * W)
        r, inside = divmod(y - y0, rh)
        if 0 <= y - y0 <= rows_n * rh:
            if inside == 0:
                row[x0 : x0 + cols * cw + 1] = b"\x00" * (cols * cw + 1)
            else:
                for c in range(cols + 1):
                    row[x0 + c * cw] = 0
                if 10 <= inside <= 18:
                    for c in range(cols):
                        s, n = x0 + c * cw + 12, 30 + (r * 7 + c * 11) % 50
                        row[s : s + n] = b"\x00" * n
        raw += row
    return build_pdf(b"q 1224 0 0 792 0 0 cm /Im0 Do Q\n", image=zlib.compress(bytes(raw), 9))


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in (
        ("panel_text.pdf", panel_text),
        ("shx_strokes.pdf", shx_strokes),
        ("shx_annot.pdf", shx_annot),
        ("scanned_panel.pdf", scanned_panel),
    ):
        (out / name).write_bytes(fn())


if __name__ == "__main__":
    main(sys.argv[1])
