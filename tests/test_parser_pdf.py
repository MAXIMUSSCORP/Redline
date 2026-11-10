import copy
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import fields, replace
from pathlib import Path

import make_pdf_samples as gen
import pytest

from redline.model import Confidence, Method, Value, clip
from redline.parsers import csv_xlsx, pdf

ROOT = Path(__file__).resolve().parent.parent
PDFS = ROOT / "samples" / "pdf"
ACAD = PDFS / "acad"
MEDIUM = Confidence.MEDIUM


# ---- dumps built in the test, so most tests need no PDF ----


def grid_words(rows, x0=30.0, top=60.0, rowh=11.0, h=7.0, gap=20.0, cw=4.0):
    """One word per cell, laid out in columns that are far apart."""
    ncols = max(len(r) for r in rows)
    xs, x = [], x0
    for c in range(ncols):
        xs.append(x)
        x += max((len(r[c]) for r in rows if c < len(r)), default=0) * cw + gap
    out = []
    for i, row in enumerate(rows):
        for c, text in enumerate(row):
            if text:
                t = top + i * rowh
                out.append(word(text, xs[c], t, xs[c] + len(text) * cw, t + h))
    return out


def word(text, x0, top, x1, bottom, upright=True):
    return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": bottom, "upright": upright}


def grid_annots(rows, subtype="Text", x0=40.0, top=60.0, rowh=18.0, cw=5.0, gap=30.0):
    ncols = max(len(r) for r in rows)
    xs, x = [], x0
    for c in range(ncols):
        xs.append(x)
        x += max((len(r[c]) for r in rows if c < len(r)), default=0) * cw + gap
    out = []
    for i, row in enumerate(rows):
        for c, text in enumerate(row):
            t = top + i * rowh
            out.append(annot(text, xs[c], t, xs[c] + len(text) * cw, t + 12, subtype))
    return out


def annot(text, x0, top, x1, bottom, subtype="Text"):
    return {"subtype": subtype, "contents": text, "x0": x0, "x1": x1, "top": top, "bottom": bottom}


def title_words(sheet="E-501", rev="2"):
    return grid_words([["SHEET NO.", sheet], ["REV", rev]], x0=960.0, top=700.0, rowh=20.0, h=8.0)


def page(n=1, *, words=(), tables=(), annots=(), chars=None, paths=0, image=0.0, **extra):
    words = list(words)
    if chars is None:
        chars = max(300, sum(len(str(w)) for w in words))
    return {
        "n": n,
        "width": 1224.0,
        "height": 792.0,
        "rotation": 0,
        "chars": chars,
        "paths": paths,
        "image_area_fraction": image,
        "words": words,
        "tables": list(tables),
        "annots": list(annots),
    } | extra


def dump(*pages):
    return {
        "pdfplumber": "0.11.10",
        "pdfminer": "20260107",
        "sha256": "ab" * 32,
        "pages_total": len(pages),
        "pages": list(pages),
    }


def parse(cfg, *pages):
    return pdf.parse_pages(dump(*pages), cfg, "t.pdf")


def table(rows, bbox=(30.0, 330.0, 330.0, 450.0)):
    return {"bbox": list(bbox), "rows": rows}


def entry(parsed, n=1):
    return next(c for c in parsed.coverage if c.unit == f"page {n}")


def values(unit) -> dict[str, Value]:
    return {
        f.name: getattr(unit, f.name) for f in fields(unit) if f.default_factory is Value.missing
    }


def every_value(parsed):
    for p in parsed.panels:
        yield from values(p).values()
        for c in p.circuits:
            yield from values(c).values()


def with_parsing(cfg, **kw):
    maps = copy.deepcopy(cfg.column_maps)
    maps["parsing"].update(kw)
    return replace(cfg, column_maps=maps)


def csv_panel(cfg, tmp_path, rows):
    path = tmp_path / "equivalent.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return csv_xlsx.parse_file(path, cfg)


def compare_to_csv(got, want, *, cap=None):
    """Every circuit value equals the CSV value; confidence equals the CSV, or its cap."""
    assert (got.name, len(got.circuits)) == (want.name, len(want.circuits))
    seen = set()
    for g, w in [(got, want), *zip(got.circuits, want.circuits, strict=True)]:
        for k, wv in values(w).items():
            gv = values(g)[k]
            conf = wv.confidence if cap is None else min(wv.confidence, cap)
            assert (gv.value, gv.confidence) == (wv.value, conf), (g, k)
            seen.add(gv.confidence)
    return seen


LP21 = [["Panel", "LP-21"], *gen.LP21_CELLS]


# ---- the plan-named tests ----


def test_vector_schedule_matches_csv_medium(test_cfg, tmp_path):
    want = csv_panel(test_cfg, tmp_path, LP21).panels[0]
    got = parse(test_cfg, page(words=grid_words(LP21))).panels
    assert [p.name for p in got] == ["LP-21"] and len(got[0].circuits) == 20
    seen = compare_to_csv(got[0], want, cap=MEDIUM)
    assert Confidence.HIGH in {
        v.confidence for v in every_value(csv_panel(test_cfg, tmp_path, LP21))
    }
    assert Confidence.HIGH not in seen and MEDIUM in seen
    assert got[0].circuits[0].load_va.source.method is Method.PDF_TEXT
    assert pdf.WORDS_NOTE in got[0].circuits[0].load_va.source.note


def test_shx_page_routed_not_parsed(test_cfg):
    out = parse(test_cfg, page(chars=0, paths=3000))
    assert out.panels == []
    [u] = out.unparsed
    assert (u.kind, u.reason) == ("page", pdf.SHX_NOTE)
    assert "re-plot with TrueType substitution" in u.reason
    assert u.source.locator == "page=1; class=VECTOR_NO_TEXT; chars=0; paths=3000; image=0.00"
    assert u.source.confidence is Confidence.LOW


def test_scanned_page_unparsed_kind_page(test_cfg):
    out = parse(test_cfg, page(chars=0, image=1.0))
    assert out.panels == []
    [u] = out.unparsed
    assert (u.kind, u.reason) == ("page", pdf.SCANNED_NOTE)
    assert "class=SCANNED" in u.source.locator


def test_route_reason_under_report_clip(test_cfg):
    long_skip = "x" * 900
    out = parse(
        test_cfg,
        page(1, chars=0, image=1.0),
        page(2, image=1.0, words=[word("OCR", 1, 1, 9, 8)]),
        page(3, chars=0, paths=10),
        page(4, skipped=long_skip),
    )
    assert len(out.unparsed) == 4
    for u in out.unparsed:
        assert clip(u.reason, 200) == u.reason, u.reason
    for note in (pdf.SCANNED_NOTE, pdf.OCR_LAYER_NOTE, pdf.SHX_NOTE):
        assert len(note) <= 200


# ---- ruled tables and HIGH (D3) ----


def test_ruled_schedule_matches_csv(test_cfg, tmp_path):
    want = csv_panel(test_cfg, tmp_path, gen.LP22_CELLS).panels[0]
    out = parse(test_cfg, page(tables=[table(gen.LP22_CELLS)]))
    [got] = out.panels
    seen = compare_to_csv(got, want)
    assert Confidence.HIGH in seen
    assert got.circuits[0].load_va.source.locator.startswith("page=1; table=0; r=")
    assert "1 ruled tables read, 0 listed" in entry(out).what_read


def test_unruled_exact_header_capped_medium(test_cfg):
    unruled = parse(test_cfg, page(words=grid_words(gen.LP22_CELLS))).panels
    ruled = parse(test_cfg, page(tables=[table(gen.LP22_CELLS)])).panels
    assert len(unruled) == len(ruled) == 1
    assert Confidence.HIGH in {v.confidence for p in ruled for v in values(p.circuits[0]).values()}
    for v in every_value(parse(test_cfg, page(words=grid_words(gen.LP22_CELLS)))):
        assert v.confidence <= MEDIUM


# ---- classification (deliverable 1, D4) ----


def test_classify_text_page(test_cfg):
    parsing = test_cfg.column_maps["parsing"]
    n = parsing["pdf_text_page_min_chars"]
    assert pdf.classify({"chars": n, "image_area_fraction": 0}, parsing) == pdf.TEXT
    assert pdf.classify({"chars": n * 5, "paths": 9000}, parsing) == pdf.TEXT


def test_classify_scanned_page(test_cfg):
    parsing = test_cfg.column_maps["parsing"]
    f = parsing["pdf_scanned_image_area_fraction"]
    assert pdf.classify({"chars": 0, "image_area_fraction": f}, parsing) == pdf.SCANNED
    assert pdf.classify({"chars": 0, "image_area_fraction": 1.0}, parsing) == pdf.SCANNED


def test_classify_vector_no_text_page(test_cfg):
    parsing = test_cfg.column_maps["parsing"]
    n = parsing["pdf_text_page_min_chars"]
    assert pdf.classify({"chars": 0, "paths": 3000}, parsing) == pdf.VECTOR_NO_TEXT
    assert pdf.classify({"chars": n - 1, "image_area_fraction": 0.1}, parsing) == pdf.VECTOR_NO_TEXT
    assert pdf.classify({}, parsing) == pdf.VECTOR_NO_TEXT


def test_image_page_with_text_layer_is_scanned(test_cfg):
    words = grid_words(gen.LP22_CELLS)
    out = parse(test_cfg, page(words=words, image=0.95, chars=5000))
    assert out.panels == []
    [u] = out.unparsed
    assert (u.kind, u.reason) == ("page", pdf.OCR_LAYER_NOTE)
    assert "chars=5000" in u.source.locator and "likely OCR" in u.reason
    assert "not read" in entry(out).what_read or "nothing read" in entry(out).what_read


def test_thresholds_come_from_config(test_cfg):
    base = test_cfg.column_maps["parsing"]
    lo = {"chars": 100, "image_area_fraction": 0.5}
    assert pdf.classify(lo, base) == pdf.VECTOR_NO_TEXT
    assert pdf.classify(lo, {**base, "pdf_text_page_min_chars": 100}) == pdf.TEXT
    assert pdf.classify(lo, {**base, "pdf_text_page_min_chars": 101}) == pdf.VECTOR_NO_TEXT
    assert pdf.classify(lo, {**base, "pdf_scanned_image_area_fraction": 0.5}) == pdf.SCANNED
    assert pdf.classify(lo, {**base, "pdf_scanned_image_area_fraction": 0.51}) != pdf.SCANNED
    # through parse_pages: the same page routes differently under another config
    pg = page(words=grid_words(gen.LP22_CELLS) + title_words(), chars=100)
    assert parse(test_cfg, pg).panels == []
    low = with_parsing(test_cfg, pdf_text_page_min_chars=100)
    assert [p.name for p in parse(low, pg).panels] == ["LP-22"]
    # the title block crop follows its two fractions
    tb = page(words=title_words())
    assert "sheet E-501" in entry(parse(test_cfg, tb)).what_read
    narrow = with_parsing(test_cfg, pdf_title_block_width_fraction=0.1)
    assert "sheet number not found" in entry(parse(narrow, tb)).what_read
    short = with_parsing(test_cfg, pdf_title_block_height_fraction=0.05)
    assert "sheet number not found" in entry(parse(short, tb)).what_read


# ---- annotation path (deliverable 2) ----


def lp23_annots(**kw):
    return grid_annots(gen.LP23_CELLS, **kw)


def test_annot_page_reads_medium(test_cfg):
    out = parse(test_cfg, page(chars=0, paths=900, annots=lp23_annots()))
    [p] = out.panels
    assert (p.name, len(p.circuits)) == ("LP-23", 6)
    assert out.unparsed == []
    assert every_value(out)
    for v in every_value(out):
        assert v.confidence <= MEDIUM
    brk = p.circuits[0].breaker_a
    assert brk.source.method is Method.PDF_ANNOT and pdf.ANNOT_NOTE in brk.source.note
    assert "annots" in brk.source.locator
    assert "44 annotations read (Text 44)" in entry(out).what_read
    assert entry(out).method == "pdf_annot"


def test_annot_disagrees_with_chars_low(test_cfg):
    notes = lp23_annots()
    row4 = 60.0 + 4 * 18.0  # the ckt 4 row of LP23_CELLS
    target = next(a for a in notes if a["top"] == row4 and a["contents"] == "15")
    assert target["contents"] == gen.LP23_DISAGREEMENT["annotation"]
    agree = word(
        gen.LP23_DISAGREEMENT["annotation"],
        target["x0"],
        target["top"] + 2,
        target["x1"],
        target["top"] + 9,
    )
    clean = parse(test_cfg, page(chars=10, annots=notes, words=[agree]))
    assert Confidence.LOW not in {v.confidence for v in every_value(clean)}
    odd = dict(agree, text=gen.LP23_DISAGREEMENT["word"])
    out = parse(test_cfg, page(chars=10, annots=notes, words=[odd]))
    [p] = out.panels
    lows = [
        (c.number, k)
        for c in p.circuits
        for k, v in values(c).items()
        if v.confidence is Confidence.LOW
    ]
    assert lows == [(gen.LP23_DISAGREEMENT["ckt"], "breaker_a")]
    low = next(c for c in p.circuits if c.number == "4").breaker_a
    assert pdf.DISAGREE_NOTE in low.source.note
    assert "1 cells where annotation text and page text disagree" in entry(out).what_read


def test_annots_on_text_page_counted_not_read(test_cfg):
    out = parse(test_cfg, page(chars=500, annots=lp23_annots(subtype="Square")))
    assert out.panels == []
    assert "44 annotations not read" in entry(out).what_read


def test_annot_without_contents_ignored(test_cfg):
    empty = [annot("", 10 + i, 700, 20 + i, 712) for i in range(3)] + [annot("  ", 5, 5, 9, 9)]
    only = parse(test_cfg, page(chars=0, paths=5, annots=empty))
    assert only.panels == [] and [u.reason for u in only.unparsed] == [pdf.SHX_NOTE]
    assert "annotations read" not in entry(only).what_read
    mixed = parse(test_cfg, page(chars=0, paths=5, annots=[*lp23_annots(), *empty]))
    assert [p.name for p in mixed.panels] == ["LP-23"] and mixed.unparsed == []


def test_annot_page_without_schedule_routed(test_cfg):
    notes = [annot(t, 40, 60 + 18 * i, 90, 72 + 18 * i) for i, t in enumerate("abc")]
    out = parse(test_cfg, page(chars=0, paths=5, annots=notes))
    assert out.panels == []
    kinds = Counter(u.kind for u in out.unparsed)
    assert kinds["page"] == 1 and kinds["table"] == 1
    assert next(u for u in out.unparsed if u.kind == "page").reason == pdf.SHX_NOTE
    assert "3 annotations read" in entry(out).what_read


# ---- title block (deliverable 3) ----


def test_title_block_sheet_and_revision(test_cfg):
    words = grid_words(gen.LP22_CELLS) + title_words("E-501", "2")
    out = parse(test_cfg, page(words=words))
    assert "sheet E-501, revision 2, from the title block" in entry(out).what_read
    [p] = out.panels
    assert p.circuits[0].load_va.source.locator.startswith("page=1; sheet=E-501; ")


def test_title_block_not_found_listed(test_cfg):
    out = parse(test_cfg, page(words=grid_words(gen.LP22_CELLS)))
    text = entry(out).what_read
    assert "sheet number not found in the title block" in text
    assert "revision not found in the title block" in text
    assert "sheet=" not in out.panels[0].source.locator
    mixed = grid_words([["SHEET NO.", "E-9"]], x0=960.0, top=700.0, h=8.0)
    text = entry(parse(test_cfg, page(words=mixed))).what_read
    assert "sheet E-9, from the title block" in text and "revision not found" in text


def test_title_block_value_below_label_and_conflict(test_cfg):
    below = grid_words([["SHEET NO."], ["E-7"]], x0=960.0, top=700.0, rowh=20.0, h=8.0)
    assert "sheet E-7" in entry(parse(test_cfg, page(words=below))).what_read
    twice = title_words("E-1", "A") + grid_words([["SHEET", "E-2"]], x0=960.0, top=740.0, h=8.0)
    text = entry(parse(test_cfg, page(words=twice))).what_read
    assert "E-1" in text and "E-2" in text and "none is taken" in text
    assert "revision A, from the title block" in text


def test_title_block_words_not_in_table(test_cfg):
    out = parse(test_cfg, page(words=title_words()))
    assert out.unparsed == [] and out.panels == []
    assert "0 word clusters read, 0 listed" in entry(out).what_read
    both = parse(test_cfg, page(words=grid_words(gen.LP22_CELLS) + title_words()))
    assert both.unparsed == []


def test_rotated_page_title_block_not_read(test_cfg):
    pg = page(words=grid_words(gen.LP22_CELLS) + title_words(), rotation=90)
    out = parse(test_cfg, pg)
    assert "page is rotated 90 degrees; title block not read" in entry(out).what_read
    assert "sheet=" not in out.panels[0].source.locator
    assert "sheet E-501" not in entry(out).what_read


# ---- table finding (deliverable 4) ----


def test_no_header_text_listed_once(test_cfg):
    notes = grid_words([[gen.NOTES_CELLS[0]], [gen.NOTES_CELLS[1]], ["2. SECOND NOTE"]])
    out = parse(test_cfg, page(words=notes))
    assert out.panels == []
    [u] = out.unparsed
    assert u.kind == "table" and "no panel schedule header" in u.reason
    assert "0 word clusters read, 1 listed" in entry(out).what_read


def test_blank_gap_splits_regions(test_cfg):
    a = grid_words([["Panel", "LP-31"], *gen.LP22_CELLS[1:]], top=60.0)
    b = grid_words([["Panel", "LP-32"], *gen.LP22_CELLS[1:]], top=400.0)
    out = parse(test_cfg, page(words=a + b))
    assert [p.name for p in out.panels] == ["LP-31", "LP-32"]
    assert "2 word clusters read, 0 listed" in entry(out).what_read


def test_rotated_words_counted(test_cfg):
    side = [
        word("NORTH", 1190, 160, 1199, 200, upright=False),
        word("EAST", 1190, 220, 1199, 250, False),
    ]
    out = parse(test_cfg, page(words=grid_words(gen.LP22_CELLS) + side))
    assert [p.name for p in out.panels] == ["LP-22"]
    assert "2 rotated words not clustered" in entry(out).what_read
    assert not any("NORTH" in u.raw for u in out.unparsed)


def test_panel_name_above_ruled_table(test_cfg):
    rows = gen.LP22_CELLS[1:]
    bbox = (30.0, 330.0, 330.0, 450.0)
    label = grid_words([["Panel LP-24"]], x0=34.0, top=312.0)
    out = parse(test_cfg, page(tables=[table(rows, bbox)], words=label))
    assert [(p.name, len(p.circuits)) for p in out.panels] == [("LP-24", 6)]
    far = grid_words([["Panel LP-24"]], x0=34.0, top=100.0)
    none = parse(test_cfg, page(tables=[table(rows, bbox)], words=far))
    assert none.panels == []
    assert any(u.reason == "no panel name" for u in none.unparsed)


def test_title_block_table_not_read_as_schedule(test_cfg):
    inside = table(gen.LP22_CELLS, (940.0, 650.0, 1200.0, 780.0))
    out = parse(test_cfg, page(tables=[inside]))
    assert out.panels == [] and out.unparsed == []
    assert "0 ruled tables read, 0 listed" in entry(out).what_read
    elsewhere = table(gen.LP22_CELLS, (100.0, 100.0, 400.0, 300.0))
    assert [p.name for p in parse(test_cfg, page(tables=[elsewhere])).panels] == ["LP-22"]


# ---- the four samples (CLAUDE.md 8) ----


def read_sample(cfg, path):
    return pdf.parse_pages(pdf.read_pages(path, cfg, isolated=False), cfg, path.name)


def test_pdf_sample_counts(test_cfg, tmp_path):
    out = read_sample(test_cfg, PDFS / "panel_text.pdf")
    assert [(p.name, len(p.circuits)) for p in out.panels] == [("LP-22", 6), ("LP-21", 20)]
    assert Counter(u.kind for u in out.unparsed) == {"column": 1, "table": 1}
    notes = [u for u in out.unparsed if u.kind == "table"]
    assert gen.NOTES_CELLS[0] in notes[0].raw
    text = entry(out).what_read
    assert "1 rotated words not clustered" in text
    assert "sheet E-501, revision 2, from the title block" in text
    assert "1 ruled tables read, 0 listed" in text and "1 word clusters read, 1 listed" in text
    # the unruled panel is the CSV panel at MEDIUM, the ruled one is the CSV panel
    want = csv_panel(test_cfg, tmp_path, LP21).panels[0]
    compare_to_csv(next(p for p in out.panels if p.name == "LP-21"), want, cap=MEDIUM)
    want = csv_panel(test_cfg, tmp_path, gen.LP22_CELLS).panels[0]
    compare_to_csv(next(p for p in out.panels if p.name == "LP-22"), want)

    out = read_sample(test_cfg, PDFS / "shx_annot.pdf")
    [p] = out.panels
    assert (p.name, len(p.circuits), len(out.unparsed)) == ("LP-23", 6, 0)
    confs = Counter(v.confidence for v in every_value(out))
    assert max(confs) <= MEDIUM and confs[Confidence.LOW] == 1
    text = entry(out).what_read
    assert "sheet E-503, revision 1, from the title block" in text
    assert "44 annotations read" in text

    for name, cls in (("shx_strokes.pdf", "VECTOR_NO_TEXT"), ("scanned_panel.pdf", "SCANNED")):
        out = read_sample(test_cfg, PDFS / name)
        assert out.panels == [] and [u.kind for u in out.unparsed] == ["page"]
        assert f"class={cls}" in out.unparsed[0].source.locator


# ---- the file entry ----


def test_not_a_pdf_is_input_error(test_cfg, tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"this is not a pdf")
    with pytest.raises(csv_xlsx.InputError, match="cannot be read as a PDF"):
        pdf.read_pages(junk, test_cfg, isolated=False)
    with pytest.raises(csv_xlsx.InputError, match="was not found"):
        pdf.parse_file(tmp_path / "missing.pdf", test_cfg)
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(csv_xlsx.InputError):
        pdf.parse_file(empty, test_cfg)


def test_password_pdf_is_input_error(test_cfg, monkeypatch):
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    def locked(*a, **k):
        raise PDFPasswordIncorrect

    monkeypatch.setattr(pdfplumber, "open", locked)
    with pytest.raises(csv_xlsx.InputError, match="password protected"):
        pdf.read_pages(PDFS / "panel_text.pdf", test_cfg, isolated=False)


def test_file_size_cap(test_cfg, monkeypatch):
    monkeypatch.setattr(pdf, "MAX_PDF_BYTES", 100)
    with pytest.raises(csv_xlsx.InputError, match="MAX_PDF_BYTES"):
        pdf.parse_file(PDFS / "panel_text.pdf", test_cfg)


def three_pages() -> bytes:
    content = b"BT /F1 9 Tf 1 0 0 1 30 700 Tm (page) Tj ET\n"
    return gen.build_pdf([{"content": content}] * 3)


def test_page_cap_listed(test_cfg, tmp_path, monkeypatch):
    path = tmp_path / "three.pdf"
    path.write_bytes(three_pages())
    assert pdf.read_pages(path, test_cfg, isolated=False)["pages_total"] == 3
    monkeypatch.setattr(pdf, "MAX_PAGES", 2)
    d = pdf.read_pages(path, test_cfg, isolated=False)
    assert d["pages_total"] == 3 and [p["n"] for p in d["pages"]] == [1, 2, 3]
    out = pdf.parse_pages(d, test_cfg, path.name)
    skipped = [u for u in out.unparsed if "MAX_PAGES" in u.reason]
    assert len(skipped) == 1 and skipped[0].kind == "page" and "1 pages" in skipped[0].reason


def test_word_cap_listed(test_cfg, monkeypatch):
    monkeypatch.setattr(pdf, "MAX_WORDS_PER_PAGE", 3)
    out = read_sample(test_cfg, PDFS / "panel_text.pdf")
    assert out.panels == [] and [u.kind for u in out.unparsed] == ["page"]
    assert "MAX_WORDS_PER_PAGE" in out.unparsed[0].reason
    monkeypatch.setattr(pdf, "MAX_WORDS_PER_PAGE", 100_000)
    monkeypatch.setattr(pdf, "MAX_ANNOTS_PER_PAGE", 5)
    out = read_sample(test_cfg, PDFS / "shx_annot.pdf")
    assert out.panels == [] and "MAX_ANNOTS_PER_PAGE" in out.unparsed[0].reason


def test_timeout_is_input_error(test_cfg):
    cfg = with_parsing(test_cfg, pdf_timeout_s=0.001)
    with pytest.raises(csv_xlsx.InputError, match=r"panel_text\.pdf timed out after 0\.001 s"):
        pdf.parse_file(PDFS / "panel_text.pdf", cfg)


def raw_pdf(objs: dict[int, bytes]) -> bytes:
    """A PDF from numbered objects, with a correct xref. Object 1 is the catalog."""
    out, offs = bytearray(b"%PDF-1.4\n"), {}
    for num, body in objs.items():
        offs[num] = len(out)
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    top, start = max(objs) + 1, len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % top
    for num in range(1, top):
        out += (b"%010d 00000 n \n" % offs[num]) if num in offs else b"0000000000 65535 f \n"
    return bytes(
        out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (top, start)
    )


def bomb_pdf(pages: int, mb: int) -> bytes:
    import zlib

    z = zlib.compress(b" " * (mb * 2**20), 1)
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>"}
    for i in range(pages):
        objs[10 + 2 * i] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Contents %d 0 R >>"
            % (11 + 2 * i)
        )
        objs[11 + 2 * i] = (
            b"<< /Filter /FlateDecode /Length %d >>\nstream\n" % len(z) + z + b"\nendstream"
        )
    kids = b" ".join(b"%d 0 R" % (10 + 2 * i) for i in range(pages))
    objs[2] = b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % pages
    return raw_pdf(dict(sorted(objs.items())))


def test_child_memory_ceiling_ends_stream_bomb(test_cfg, tmp_path, monkeypatch):
    path = tmp_path / "bomb.pdf"
    path.write_bytes(bomb_pdf(8, 128))
    monkeypatch.setattr(pdf, "MAX_CHILD_MEMORY_MB", 400)
    import time

    start = time.monotonic()
    with pytest.raises(csv_xlsx.InputError, match="memory"):
        pdf.read_pages(path, test_cfg)
    assert time.monotonic() - start < 20


def test_child_memory_ceiling_keeps_normal_pdf(test_cfg):
    assert pdf.MAX_CHILD_MEMORY_MB >= 1024
    out = pdf.parse_file(PDFS / "panel_text.pdf", test_cfg)
    assert "LP-22" in [p.name for p in out.panels]


def test_page_cap_before_page_objects(test_cfg, tmp_path):
    n = 100_000
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>"}
    kids = []
    for i in range(n):
        objs[3 + i] = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>"
        kids.append(b"%d 0 R" % (3 + i))
    objs[2] = b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count %d >>" % n
    path = tmp_path / "many.pdf"
    path.write_bytes(raw_pdf(dict(sorted(objs.items()))))
    import time

    start = time.monotonic()
    d = pdf.read_pages(path, test_cfg, isolated=False)
    assert time.monotonic() - start < 3
    assert d["pages_total"] == n and len(d["pages"]) == pdf.MAX_PAGES + 1
    assert f"{n - pdf.MAX_PAGES} pages past MAX_PAGES" in d["pages"][-1]["skipped"]


def test_annots_cap_before_resolve(test_cfg, tmp_path, monkeypatch):
    import pdfplumber.page

    def resolved(self):
        raise AssertionError("annotations were resolved on an over-cap page")

    monkeypatch.setattr(pdfplumber.page.Page, "annots", property(resolved))
    n = 300_000
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Annots 6 0 R >>",
        5: b"<< /Type /Annot /Subtype /Text /Rect [10 10 20 20] /Contents (x) >>",
        6: b"[" + b"5 0 R " * n + b"]",
    }
    path = tmp_path / "annots.pdf"
    path.write_bytes(raw_pdf(objs))
    import time

    start = time.monotonic()
    d = pdf.read_pages(path, test_cfg, isolated=False)
    assert time.monotonic() - start < 10
    assert f"page has {n} annotations, over MAX_ANNOTS_PER_PAGE" in d["pages"][0]["skipped"]


def test_chars_cap_before_extract_words(test_cfg, monkeypatch):
    import pdfplumber.page

    def fail(*a, **k):
        raise AssertionError("extract_words ran on an over-cap page")

    monkeypatch.setattr(pdf, "MAX_CHARS_PER_PAGE", 10)
    monkeypatch.setattr(pdfplumber.page.Page, "extract_words", fail)
    d = pdf.read_pages(PDFS / "panel_text.pdf", test_cfg, isolated=False)
    assert "over MAX_CHARS_PER_PAGE (10)" in d["pages"][0]["skipped"]


def test_infinite_coordinate_costs_only_its_page(test_cfg, tmp_path):
    p = gen.Page()
    p.text(30, 40, "GENERAL NOTES " + "SAMPLE ONLY NOT FOR CONSTRUCTION " * 8, 8)
    gen.ruled_grid(p, [["Panel", "LP-9"], gen.HEADER6, *gen.short_rows()[:3]], 30, 330, 7, 15, 6)
    big = "1" + "0" * 308 + ".0"
    bad = f"BT /F1 9 Tf {big} 0 0 1 {big} 10 Tm (X) Tj ET\n".encode()
    path = tmp_path / "inf.pdf"
    path.write_bytes(gen.build_pdf([{"content": p.data()}, {"content": bad}]))
    out = pdf.parse_file(path, test_cfg)
    assert [p.name for p in out.panels] == ["LP-9"]
    assert any("not finite" in u.reason and u.source.locator == "page=2" for u in out.unparsed)


def test_annotation_pdfdocencoding_decoded(test_cfg, tmp_path):
    rect = b"/Rect [100 700 200 712] /Subtype /Text /Type /Annot /Contents "
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1224 792] /Annots [4 0 R 5 0 R] >>",
        4: b"<< " + rect + b"(120/208V 3\330 4W) >>",
        5: b"<< " + rect + b"<FEFF004C0050002D0031> >>",
    }
    path = tmp_path / "enc.pdf"
    path.write_bytes(raw_pdf(objs))
    d = pdf.read_pages(path, test_cfg, isolated=False)
    assert [a["contents"] for a in d["pages"][0]["annots"]] == ["120/208V 3\u00d8 4W", "LP-1"]


def test_vanished_file_is_input_error(test_cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(pdf.Path, "is_file", lambda self: True)
    with pytest.raises(csv_xlsx.InputError, match="gone.pdf cannot be read"):
        pdf.read_pages(tmp_path / "gone.pdf", test_cfg)


def test_pdfplumber_missing_is_input_error(test_cfg, monkeypatch):
    monkeypatch.setitem(sys.modules, "pdfplumber", None)
    with pytest.raises(csv_xlsx.InputError, match="pdfplumber not installed: pip install"):
        pdf.read_pages(PDFS / "panel_text.pdf", test_cfg, isolated=False)


def test_child_reads_sample(test_cfg):
    path = PDFS / "panel_text.pdf"
    d = pdf.read_pages(path, test_cfg)
    assert d == json.loads(json.dumps(pdf.read_pages(path, test_cfg, isolated=False)))
    assert d["pages_total"] == 1 and d["pages"][0]["chars"] > 1000
    with pytest.raises(csv_xlsx.InputError, match="cannot be read as a PDF"):
        pdf.read_pages(ROOT / "pyproject.toml", test_cfg)


def test_provenance_names_reader_and_hash(test_cfg):
    path = PDFS / "shx_annot.pdf"
    out = pdf.parse_file(path, test_cfg)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    [text] = out.provenance.values()
    assert list(out.provenance) == [path.name]
    assert re.fullmatch(r"pdfplumber \S+, pdfminer\.six \S+, SHA-256 [0-9a-f]{64}", text)
    assert text.endswith(sha)
    assert pdf.provenance({}) == "pdfplumber , pdfminer.six , SHA-256 "


# ---- an odd dump never raises ----


def test_parse_never_raises_on_odd_dump(test_cfg, monkeypatch):
    nan, inf = float("nan"), float("inf")
    odd_pages = [
        None,
        5,
        "page",
        [],
        {},
        {"n": "x", "chars": "many", "words": None, "tables": None, "annots": None},
        page(words=[None, 3, {"text": None}, {"text": "a"}, word("b", nan, 0, 1, 1)]),
        page(words=[word("a", 1e300, -1e300, 1e301, 1e300), word("b", 5, 5, 4, 4)]),
        page(words=[word(s, 0, 0, 0, 0) for s in "abcde"]),
        page(words=[word("x", 0, 0, 5, inf), word("y", 0, 0, 5, 7, upright="no")]),
        page(tables=[None, {}, {"bbox": [1, 2], "rows": []}, {"bbox": [0, 0, 9, 9], "rows": None}]),
        page(tables=[table([None, [None, 3, "x"], "row", []])]),
        page(tables=[table([[None] * 4] * 3, ("a", 0, 1, 1))]),
        page(annots=[None, {}, {"contents": 5}, {"contents": "x"}, annot("y", nan, 0, 1, 1)]),
        page(chars=0, annots=[annot("a", 0, 0, 5, 5)] * 4),
        page(chars=0, annots=[annot("a", 1e300, 0, 1e301, 5), annot("b", 0, 0, 0, 0)]),
        page(rotation="x", words=title_words()),
        page(rotation=1e30, words=title_words()),
        page(chars=0, image=nan, paths="x"),
        page(chars=-5, image=-1.0),
        page(skipped=5),
        page(skipped=["a"]),
        page(width=0.0, height=-1.0, words=title_words()),
    ]
    for p in odd_pages:
        out = parse(test_cfg, p)
        assert out.coverage or out.unparsed
    for d in (None, [], "x", {}, {"pages": None}, {"pages": "p"}, dump(*odd_pages)):
        out = pdf.parse_pages(d, test_cfg, "t.pdf")
        assert out.unparsed or out.coverage
    # a failure inside a page is listed as that page, and the other pages still read
    real = pdf._read_page

    def boom(raw, cfg, file):
        if raw.get("n") == 2:
            raise KeyError("x")
        return real(raw, cfg, file)

    monkeypatch.setattr(pdf, "_read_page", boom)
    out = parse(test_cfg, page(1, words=grid_words(gen.LP22_CELLS)), page(2))
    assert [p.name for p in out.panels] == ["LP-22"]
    [u] = out.unparsed
    assert u.kind == "page" and "KeyError" in u.reason and u.source.locator == "page=2"


# ---- the real AutoCAD plots (docs/research/pdf_verification.md sections 4 and 5) ----


def test_acad_truetype_plot_is_text_page(test_cfg):
    d = pdf.read_pages(ACAD / "acad_truetype.pdf", test_cfg, isolated=False)
    [pg] = d["pages"]
    assert (pg["chars"], len(pg["tables"]), pg["annots"]) == (1808, 2, [])
    assert pdf.classify(pg, test_cfg.column_maps["parsing"]) == pdf.TEXT
    out = pdf.parse_pages(d, test_cfg, "acad_truetype.pdf")
    assert {"LP-11", "LP-12"} <= {p.name for p in out.panels}
    assert "class TEXT, 1808 chars" in entry(out).what_read
    assert "2 ruled tables read" in entry(out).what_read
    assert not any(u.kind == "page" for u in out.unparsed)


def test_acad_shx_plot_is_routed(test_cfg):
    d = pdf.read_pages(ACAD / "acad_shx.pdf", test_cfg, isolated=False)
    [pg] = d["pages"]
    assert (pg["chars"], pg["words"], pg["annots"]) == (0, [], [])
    out = pdf.parse_pages(d, test_cfg, "acad_shx.pdf")
    assert out.panels == []
    [u] = out.unparsed
    assert (u.kind, u.reason) == ("page", pdf.SHX_NOTE)
    assert "class=VECTOR_NO_TEXT" in u.source.locator


def test_acad_pdfshx_plot_annotation_page(test_cfg):
    d = pdf.read_pages(ACAD / "acad_pdfshx.pdf", test_cfg, isolated=False)
    [pg] = d["pages"]
    assert pg["chars"] == 0 and len(pg["annots"]) == 366
    assert {a["subtype"] for a in pg["annots"]} == {"Square"}
    texts = [a["contents"] for a in pg["annots"]]
    assert texts[:2] == ["Panel", "LP-11"]
    assert all(t == t.strip() and t.isprintable() and "﻿" not in t for t in texts)
    assert not any("\xfe\xff" in t or "\x00" in t for t in texts)
    assert pdf.classify(pg, test_cfg.column_maps["parsing"]) == pdf.VECTOR_NO_TEXT
    out = pdf.parse_pages(d, test_cfg, "acad_pdfshx.pdf")
    assert "LP-11" in {p.name for p in out.panels}
    assert "366 annotations read (Square 366)" in entry(out).what_read
    assert {v.confidence for v in every_value(out)} <= {MEDIUM, Confidence.LOW, Confidence.MISSING}
    assert all(p.source.method is Method.PDF_ANNOT for p in out.panels)
    assert sum(len(p.circuits) for p in out.panels) == 0
    pages = [u for u in out.unparsed if u.kind == "page"]
    assert [u.reason for u in pages] == [pdf.SHX_NOTE]
