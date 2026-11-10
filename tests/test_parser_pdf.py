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
    # a crop table without a schedule header is the title block: no panel, counted, not listed
    inside = table([["SHEET", "E-501"], ["REV", "2"]], (940.0, 650.0, 1200.0, 780.0))
    out = parse(test_cfg, page(tables=[inside]))
    assert out.panels == [] and out.unparsed == []
    assert "0 ruled tables read, 0 listed" in entry(out).what_read
    assert "1 tables in the title block area not read" in entry(out).what_read
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
    # the one planted disagreement is listed as well as marked LOW (RV8)
    assert (p.name, len(p.circuits), [u.kind for u in out.unparsed]) == ("LP-23", 6, ["cell"])
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


def annots_pdf(n: int, where: str = "indirect") -> bytes:
    """One page whose /Annots holds n references: an indirect array (6), inline in the page, or
    inside an object stream (7) found through an xref stream."""
    arr = b"[" + b"5 0 R " * n + b"]"
    annot = b"<< /Type /Annot /Subtype /Text /Rect [10 10 20 20] /Contents (x) >>"
    page = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Annots %s >>"
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        5: annot,
    }
    if where == "inline":
        return raw_pdf({**objs, 3: page % arr})
    if where == "indirect":
        return raw_pdf({**objs, 3: page % b"6 0 R", 6: arr})
    import struct
    import zlib

    out, offs = bytearray(b"%PDF-1.5\n"), {}
    for num, body in {**objs, 3: page % b"6 0 R"}.items():
        offs[num] = len(out)
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    z = zlib.compress(b"6 0 " + arr)
    offs[7] = len(out)
    out += b"7 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode /Length %d >>\n" % len(z)
    out += b"stream\n" + z + b"\nendstream\nendobj\n"
    start = len(out)
    rows = b""
    for num in range(9):
        if num == 6:
            rows += struct.pack(">BIH", 2, 7, 0)
        elif num == 8:
            rows += struct.pack(">BIH", 1, start, 0)
        else:
            rows += struct.pack(">BIH", 1 if num in offs else 0, offs.get(num, 0), 0)
    out += b"8 0 obj\n<< /Type /XRef /Size 9 /W [1 4 2] /Root 1 0 R /Length %d >>\n" % len(rows)
    out += b"stream\n" + rows + b"\nendstream\nendobj\nstartxref\n%d\n%%%%EOF\n" % start
    return bytes(out)


def test_annots_cap_before_resolve(test_cfg, tmp_path, monkeypatch):
    import time

    import pdfminer.pdfparser
    import pdfplumber.page

    def resolved(self):
        raise AssertionError("annotations were resolved on an over-cap page")

    monkeypatch.setattr(pdfplumber.page.Page, "annots", property(resolved))
    push = pdfminer.pdfparser.PDFParser.push
    path = tmp_path / "annots.pdf"
    path.write_bytes(annots_pdf(1_000_000))
    start = time.monotonic()
    d = pdf.read_pages(path, test_cfg, isolated=False)
    assert time.monotonic() - start < 3
    assert "page /Annots holds more than" in d["pages"][0]["skipped"]
    assert "over MAX_ANNOTS_PER_PAGE" in d["pages"][0]["skipped"]
    assert pdfminer.pdfparser.PDFParser.push is push  # the bound is lifted after the read


def test_annots_array_above_array_cap_counted(test_cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(pdf, "MAX_ARRAY_ITEMS", 50_000)
    path = tmp_path / "annots.pdf"
    path.write_bytes(annots_pdf(30_000))
    d = pdf.read_pages(path, test_cfg, isolated=False)
    assert "page has 30000 annotations, over MAX_ANNOTS_PER_PAGE" in d["pages"][0]["skipped"]


def test_annots_cap_in_object_stream(test_cfg, tmp_path):
    import time

    path = tmp_path / "objstm.pdf"
    path.write_bytes(annots_pdf(1_000_000, "objstm"))
    start = time.monotonic()
    d = pdf.read_pages(path, test_cfg, isolated=False)
    assert time.monotonic() - start < 3
    assert "page /Annots holds more than" in d["pages"][0]["skipped"]
    small = tmp_path / "small.pdf"
    small.write_bytes(annots_pdf(2, "objstm"))
    assert len(pdf.read_pages(small, test_cfg, isolated=False)["pages"][0]["annots"]) == 2


def test_annots_inline_array_ends_the_read_listed(test_cfg, tmp_path):
    import time

    path = tmp_path / "inline.pdf"
    path.write_bytes(annots_pdf(1_000_000, "inline"))
    start = time.monotonic()
    with pytest.raises(csv_xlsx.InputError, match=r"inline\.pdf has an array of more than 200000"):
        pdf.read_pages(path, test_cfg, isolated=False)
    assert time.monotonic() - start < 3


def test_annots_array_shared_by_pages_parsed_once(test_cfg, tmp_path):
    import time

    arr = b"[" + b"5 0 R " * 1_000_000 + b"]"
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids ["
        + b" ".join(b"%d 0 R" % (10 + i) for i in range(20))
        + b"] >>",
        5: b"<< /Type /Annot /Subtype /Text /Rect [10 10 20 20] /Contents (x) >>",
        6: arr,
    }
    for i in range(20):
        objs[10 + i] = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 9 9] /Annots 6 0 R >>"
    path = tmp_path / "shared.pdf"
    path.write_bytes(raw_pdf(dict(sorted(objs.items()))))
    start = time.monotonic()
    d = pdf.read_pages(path, test_cfg, isolated=False)
    assert time.monotonic() - start < 3
    assert all("holds more than" in p["skipped"] for p in d["pages"])


def test_page_count_too_large_ignored(test_cfg, tmp_path):
    n = pdf.MAX_PAGES + 1
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>"}
    for i in range(n):
        objs[3 + i] = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 9 9] >>"
    kids = b" ".join(b"%d 0 R" % (3 + i) for i in range(n))
    objs[2] = b"<< /Type /Pages /Kids [" + kids + b"] /Count 100000000000000000 >>"
    path = tmp_path / "count.pdf"
    path.write_bytes(raw_pdf(dict(sorted(objs.items()))))
    d = pdf.read_pages(path, test_cfg)  # the child and the parent's strict JSON read
    assert len(d["pages"]) == pdf.MAX_PAGES + 1
    assert d["pages_total"] == pdf.MAX_PAGES + 1
    assert "more than 1000 pages" in d["pages"][-1]["skipped"]


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
        assert not out.panels
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


# ---- M3 review fixes (RV7 to RV12) ----


def band_page(**kw):
    rows = gen.LP22_CELLS[1:]
    bbox = (30.0, 330.0, 330.0, 450.0)
    band = grid_words([["Panel", "LP-24"], ["Bus", "225"]], x0=34.0, top=330.0 - 2.4 * 7, rowh=8.4)
    return page(tables=[table(rows, bbox)], words=band, **kw)


def test_band_header_values_capped_medium(test_cfg):
    out = parse(test_cfg, band_page())
    [p] = out.panels
    assert p.name == "LP-24"
    assert p.bus_rating_a.value == 225
    assert p.bus_rating_a.confidence is MEDIUM
    assert pdf.WORDS_NOTE in p.bus_rating_a.source.note
    assert re.search(r"; r=-\d+", p.bus_rating_a.source.locator)
    # the ruled rows keep their confidence: only the loose band words are capped
    assert Confidence.HIGH in {v.confidence for c in p.circuits for v in values(c).values()}
    assert "HIGH 0" not in out.coverage[0].confidence_summary


def test_used_band_words_not_listed(test_cfg):
    out = parse(test_cfg, band_page())
    assert not any("words are not read" in u.reason for u in out.unparsed)
    assert "0 word clusters read, 0 listed" in entry(out).what_read


def disagree(test_cfg, annotation, page_text):
    notes = lp23_annots()
    t = next(a for a in notes if a["contents"] == annotation)
    w = word(page_text, t["x0"], t["top"] + 2, t["x1"], t["top"] + 9)
    return parse(test_cfg, page(chars=10, annots=notes, words=[w]))


def test_disagreement_on_circuit_number_is_listed(test_cfg):
    out = disagree(test_cfg, "4", "5")
    [u] = [u for u in out.unparsed if u.kind == "cell"]
    assert "'4'" in u.reason and "'5'" in u.reason and "; col=" in u.source.locator
    text = entry(out).what_read
    assert "1 cells where annotation text and page text disagree, listed" in text
    assert "0 values marked LOW" in text


def test_disagreement_on_panel_name_is_listed(test_cfg):
    out = disagree(test_cfg, "LP-23", "LP-28")
    [u] = [u for u in out.unparsed if u.kind == "cell"]
    assert "'LP-23'" in u.reason and "'LP-28'" in u.reason and "; y=" in u.source.locator
    assert "LP-28" in u.reason


def test_vector_page_free_words_listed(test_cfg):
    text = "NOTE: CKT 4 BREAKER CHANGED TO 30 A PER RFI 12"
    note = grid_words([[text]], x0=600.0, top=400.0)
    out = parse(test_cfg, page(chars=45, annots=lp23_annots(), words=note))
    assert [p.name for p in out.panels] == ["LP-23"]
    [u] = [u for u in out.unparsed if u.kind == "text"]
    assert u.raw.startswith("NOTE: CKT 4") and u.source.locator.startswith("page=1")
    assert "1 page words outside the annotations not read" in entry(out).what_read


def test_vector_page_with_some_text_note(test_cfg):
    out = parse(test_cfg, page(words=grid_words(gen.LP22_CELLS), chars=150))
    [u] = out.unparsed
    assert u.reason.startswith("page has too little text")
    assert "no text layer" not in u.reason
    bare = parse(test_cfg, page(chars=0, paths=900))
    assert "no text layer" in bare.unparsed[0].reason


def test_title_label_beside_label_not_value(test_cfg):
    tb = grid_words([["SHEET NO.", "REV"], ["E-501", "2"]], x0=960.0, top=700.0, rowh=20.0, h=8.0)
    text = entry(parse(test_cfg, page(words=grid_words(gen.LP22_CELLS) + tb))).what_read
    assert "sheet E-501, revision 2, from the title block" in text


def test_revision_table_header_not_value(test_cfg):
    rev = grid_words(
        [["REV", "DATE", "DESCRIPTION"], ["2", "2026-11-01", "ISSUED"]],
        x0=960.0,
        top=700.0,
        rowh=20.0,
        h=8.0,
    )
    text = entry(parse(test_cfg, page(words=rev))).what_read
    assert "revision 2" in text and "DATE" not in text


def test_word_cluster_shared_column_count(test_cfg):
    ws = grid_words(gen.LP22_CELLS)
    b = next(w for w in ws if w["text"] == gen.LP22_CELLS[2][3] and abs(w["top"] - 82) < 0.1)
    extra = word("15", b["x1"] + 4, b["top"], b["x1"] + 12, b["bottom"])
    assert "shared a column" not in entry(parse(test_cfg, page(words=ws))).what_read
    # one word less in the row, so the header row stays the widest
    ws = [w for w in ws if not (w["text"] == "12 AWG" and w["top"] == b["top"])]
    text = entry(parse(test_cfg, page(words=[*ws, extra]))).what_read
    assert "1 word-cluster cells shared a column with another cell" in text


def scaled_band_page(k):
    rows = gen.LP22_CELLS[1:]
    bbox = tuple(v * k for v in (30.0, 330.0, 330.0, 450.0))
    # The label line ends 0.5 pt (at 1x) inside the table top: within an absolute 1 pt edge at 1x,
    # beyond it at 4x, and always under 0.6 text heights.
    h, bottom = 7.0 * k, 330.5 * k
    band = [
        word("Panel", 34.0 * k, bottom - h, 52.0 * k, bottom),
        word("LP-24", 80.0 * k, bottom - h, 98.0 * k, bottom),
    ]
    return page(tables=[table(rows, bbox)], words=band, width=1224.0 * k, height=792.0 * k)


def test_band_rows_scale_with_text_height(test_cfg):
    got = []
    for k in (1, 4):
        out = parse(test_cfg, scaled_band_page(k))
        got.append([(p.name, len(p.circuits)) for p in out.panels])
        assert [u.reason for u in out.unparsed] == []
    assert got[0] == got[1] == [("LP-24", 6)]


def test_title_block_corner_table_is_read(test_cfg):
    rows = [["Panel", "LP-9"], gen.LP22_CELLS[1], *gen.LP22_CELLS[2:5]]
    far = parse(test_cfg, page(tables=[table(rows, (30.0, 330.0, 330.0, 450.0))]))
    corner = parse(test_cfg, page(tables=[table(rows, (930.0, 650.0, 1200.0, 780.0))]))
    assert [(p.name, len(p.circuits)) for p in far.panels] == [("LP-9", 3)]
    assert [(p.name, len(p.circuits)) for p in corner.panels] == [("LP-9", 3)]
    assert "1 ruled tables read, 0 listed" in entry(corner).what_read
    assert "title block area not read" not in entry(corner).what_read


def test_title_block_unused_words_counted(test_cfg):
    extra = grid_words([["DRAWN", "JD"]], x0=960.0, top=740.0, h=8.0)
    out = parse(test_cfg, page(words=[*title_words(), *extra]))
    text = entry(out).what_read
    assert "sheet E-501, revision 2, from the title block" in text
    assert "2 words in the title block area not read" in text
    assert (
        "words in the title block area"
        not in entry(parse(test_cfg, page(words=title_words()))).what_read
    )


def test_dump_warnings_are_listed(test_cfg):
    d = dump(page(1, words=grid_words(gen.LP22_CELLS)))
    assert pdf.parse_pages(d, test_cfg, "t.pdf").unparsed == []
    got = pdf.parse_pages(d | {"warnings": ["memory ceiling not set", 5, None]}, test_cfg, "t.pdf")
    [u] = got.unparsed
    assert u.kind == "file" and "memory ceiling not set" in u.reason and u.source.file == "t.pdf"
    assert [p.name for p in got.panels] == ["LP-22"]
    assert pdf.parse_pages({"warnings": "x"}, test_cfg, "t.pdf").unparsed[0].kind == "page"


def test_title_block_table_words_not_counted_as_unread(test_cfg):
    rows = [["Panel", "LP-9"], gen.LP22_CELLS[1], *gen.LP22_CELLS[2:5]]
    bbox = (930.0, 650.0, 1224.0, 712.0)
    inside = grid_words(rows, x0=935.0, top=655.0, cw=2.5, gap=8.0)
    loose = grid_words([["DRAWN", "JD"]], x0=960.0, top=772.0, h=8.0)
    label = grid_words(
        [["SHEET NO.", "E-501"], ["REV", "2"]], x0=960.0, top=730.0, rowh=20.0, h=8.0
    )
    out = parse(test_cfg, page(tables=[table(rows, bbox)], words=[*inside, *loose, *label]))
    assert [(p.name, len(p.circuits)) for p in out.panels] == [("LP-9", 3)]
    assert "2 words in the title block area not read" in entry(out).what_read
    # a duplicate of a used text elsewhere in the crop is still unread
    dup = grid_words([["E-501", "JD"]], x0=960.0, top=768.0, h=8.0)
    out = parse(test_cfg, page(words=[*title_words(), *dup]))
    assert "2 words in the title block area not read" in entry(out).what_read


# ---- review round 2: RV25 to RV29, RV31 ----


def test_many_equal_annotations_linear(test_cfg):
    import time

    n = 2000
    notes = [annot("X", 10.0 + i * 20.0, 100.0, 15.0 + i * 20.0, 110.0) for i in range(n)]
    glyph = word("Y", 0.0, 100.0, 50000.0, 110.0)
    pg = page(chars=1, paths=900, annots=notes, words=[glyph])
    start = time.perf_counter()
    out = parse(test_cfg, pg)
    assert time.perf_counter() - start < 2.0
    cells = [u for u in out.unparsed if u.kind == "cell"]
    assert 0 < len(cells) <= n
    assert len({u.source.locator for u in cells}) == len(cells)


def test_disagreement_marks_only_overlapping_cell(test_cfg):
    notes = grid_annots([["Breaker", "Load", "Breaker"], ["20", "5", "20"]])
    left = next(a for a in notes if a["contents"] == "20")
    w = word("30", left["x0"], left["top"] + 2, left["x1"], left["top"] + 9)
    out = parse(test_cfg, page(chars=10, annots=notes, words=[w]))
    [u] = [u for u in out.unparsed if u.kind == "cell"]
    assert u.source.locator.endswith("col=0")
    assert "1 cells where annotation text and page text disagree" in entry(out).what_read


def test_title_label_words_never_values(test_cfg):
    def read(rows):
        words = grid_words(rows, x0=960.0, top=640.0, rowh=20.0, h=8.0)
        return entry(parse(test_cfg, page(words=words))).what_read

    text = read([["DRAWING NO.", "REVISION", "SCALE"], ["E-501", "C", "AS NOTED"]])
    assert "sheet E-501, revision C, from the title block" in text
    text = read([["REV", "DATE", "BY"], ["B", "2026-11-01", "JD"]])
    assert "revision B, from the title block" in text
    text = read([["B", "2026-11-01", "JD"], ["REV", "DATE", "BY"]])
    assert "revision not found" in text and "revision DATE" not in text


def test_revision_column_with_several_values_named(test_cfg):
    rows = [
        ["REV", "DESCRIPTION", "DATE", "BY"],
        ["0", "ISSUED FOR PERMIT", "2026-01-05", "JD"],
        ["1", "REVISED PER RFI", "2026-02-09", "JD"],
    ]
    words = grid_words(rows, x0=960.0, top=640.0, rowh=20.0, h=8.0)
    text = entry(parse(test_cfg, page(words=words))).what_read
    assert "revision has more than one value (0, 1), so none is taken" in text
    assert "revision 0" not in text


def test_corner_table_band_name_in_crop(test_cfg):
    rows = [gen.LP22_CELLS[1], *gen.LP22_CELLS[2:5]]
    band = grid_words([["Panel", "LP-9"]], x0=935.0, top=650.0 - 12, h=7.0)
    pg = page(tables=[table(rows, (930.0, 660.0, 1220.0, 780.0))], words=band)
    out = parse(test_cfg, pg)
    assert [(p.name, len(p.circuits)) for p in out.panels] == [("LP-9", 3)]
    assert "words in the title block area not read" not in entry(out).what_read


def test_title_block_many_label_pairs_linear(test_cfg):
    import time

    # about 10 pt apart, wider than the column gap, so every word is its own cell and labels match
    words = []
    for i in range(2000):
        x = 640.0 + i * 40.0
        words += [
            word("SHEET", x, 700.0, x + 10.0, 708.0),
            word("E1", x + 20.0, 700.0, x + 28.0, 708.0),
        ]
    start = time.perf_counter()
    out = entry(parse(test_cfg, page(words=words)))
    assert time.perf_counter() - start < 2.0
    assert "sheet E1" in out.what_read  # the labels matched, so this is the slow path


def test_title_block_many_values_clipped(test_cfg):
    rows = [["SHEET", f"E-{i}"] for i in range(20000)]
    words = grid_words(rows, x0=960.0, top=640.0, rowh=20.0, h=8.0)
    text = entry(parse(test_cfg, page(words=words))).what_read
    assert "sheet number has more than one value" in text
    assert len(text) < 1000


def title_text(cfg, rows):
    words = grid_words(rows, x0=940.0, top=640.0, rowh=14.0, h=8.0)
    return entry(parse(cfg, page(words=words))).what_read


def test_title_header_row_values_below(test_cfg):
    shapes = [
        ([["SHEET NO.", "PROJECT NO."], ["E-501", "2026-104"]], ["sheet E-501"]),
        ([["DWG NO.", "JOB NO.", "REV"], ["E1.01", "24-118", "C"]], ["sheet E1.01", "revision C"]),
        ([["REV", "ISSUE DATE"], ["3", "2026-11-01"]], ["revision 3"]),
        ([["SHEET NUMBER", "SHEET TITLE"], ["E-501", "POWER PLAN"]], ["sheet E-501"]),
        ([["SHEET NO.", "CLIENT NAME"], ["E-501", "ACME 2"]], ["sheet E-501"]),  # label not listed
    ]
    for rows, expect in shapes:
        text = title_text(test_cfg, rows)
        for part in expect:
            assert part in text, f"{rows[0]}: {part!r} missing from {text!r}"
        for label in ("PROJECT NO.", "JOB NO.", "ISSUE DATE", "SHEET TITLE", "CLIENT NAME"):
            assert f"sheet {label}" not in text, f"{rows[0]}: label read as sheet"
            assert f"revision {label}" not in text, f"{rows[0]}: label read as revision"


def test_title_stacked_values_beside(test_cfg):
    assert "sheet ES" in title_text(test_cfg, [["SHEET", "ES"]])
    assert "revision C" in title_text(test_cfg, [["REV", "C"]])
    assert "sheet E-501" in title_text(test_cfg, [["SHEET NO.", "E-501"]])
    both = title_text(test_cfg, [["SHEET", "ES"], ["REV", "C"]])
    assert "sheet ES, revision C" in both
    assert "sheet E-501" in title_text(test_cfg, [["SHEET", "E-501", "OF", "12"]])


def test_title_round_two_shapes_unchanged(test_cfg):
    a = title_text(test_cfg, [["DRAWING NO.", "REVISION", "SCALE"], ["E-501", "C", "AS NOTED"]])
    assert "sheet E-501, revision C" in a
    assert "revision B" in title_text(test_cfg, [["REV", "DATE", "BY"], ["B", "2026-11-01", "JD"]])
    bottom = title_text(
        test_cfg, [["B", "IFC", "2026-02-09", "JD"], ["REV", "DESCRIPTION", "DATE"]]
    )
    assert "revision DATE" not in bottom and "revision not found" in bottom
    assert "sheet E-501, revision C" in title_text(test_cfg, [["SHEET NO.", "REV"], ["E-501", "C"]])


def test_title_single_value_below_not_walked(test_cfg):
    a = title_text(test_cfg, [["REV"], ["2"], ["ISSUED FOR CONSTRUCTION"]])
    assert "revision 2" in a and "more than one" not in a
    rows = [["SHEET NO.", "REV"], ["E-501", "2"], ["COPYRIGHT 2026 ACME ENGINEERING"]]
    b = title_text(test_cfg, rows)
    assert "sheet E-501, revision 2" in b and "more than one" not in b
    c = title_text(test_cfg, [["SHEET NO."], ["E-501"], ["ELECTRICAL PLAN"]])
    assert "sheet E-501" in c and "more than one" not in c


def array_objstm_pdf(pages: int, n: int) -> bytes:
    """pages pages, each /Annots an n-entry array in its own object stream (found by xref stream)."""
    import struct
    import zlib

    arr = b"[" + b"5 0 R " * n + b"]"
    kids = b" ".join(b"%d 0 R" % (10 + i) for i in range(pages))
    direct = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % pages,
        5: b"<< /Type /Annot /Subtype /Text /Rect [10 10 20 20] /Contents (x) >>",
    }
    for i in range(pages):
        direct[10 + i] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Annots %d 0 R >>" % (100 + i)
        )
    out, offs, packed = bytearray(b"%PDF-1.5\n"), {}, {}
    for num, body in direct.items():
        offs[num] = len(out)
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    for i in range(pages):
        head = b"%d 0 " % (100 + i)
        z = zlib.compress(head + arr)
        offs[200 + i] = len(out)
        dic = b"<< /Type /ObjStm /N 1 /First %d /Filter /FlateDecode /Length %d >>" % (
            len(head),
            len(z),
        )
        out += b"%d 0 obj\n" % (200 + i) + dic + b"\nstream\n" + z + b"\nendstream\nendobj\n"
        packed[100 + i] = 200 + i
    xref = 300
    start, size = len(out), xref + 1
    rows = b""
    for num in range(size):
        if num in packed:
            rows += struct.pack(">BIH", 2, packed[num], 0)
        elif num == xref:
            rows += struct.pack(">BIH", 1, start, 0)
        else:
            rows += struct.pack(">BIH", 1 if num in offs else 0, offs.get(num, 0), 0)
    dic = b"<< /Type /XRef /Size %d /W [1 4 2] /Root 1 0 R /Length %d >>" % (size, len(rows))
    out += b"%d 0 obj\n" % xref + dic + b"\nstream\n" + rows + b"\nendstream\nendobj\n"
    out += b"startxref\n%d\n%%%%EOF\n" % start
    return bytes(out)


def test_array_too_long_fresh_each_page(test_cfg, tmp_path, monkeypatch):
    made = []

    class Recorded(pdf._ArrayTooLong):
        def __init__(self, *a):
            super().__init__(*a)
            made.append(self)

    monkeypatch.setattr(pdf, "MAX_ARRAY_ITEMS", 1000)
    monkeypatch.setattr(pdf, "_ArrayTooLong", Recorded)
    path = tmp_path / "many_objstm.pdf"
    path.write_bytes(array_objstm_pdf(50, 1001))
    d = pdf.read_pages(path, test_cfg, isolated=False)
    assert len(d["pages"]) == 50
    assert all("holds more than" in p["skipped"] for p in d["pages"])

    def depth(e):
        n, tb = 0, e.__traceback__
        while tb:
            n, tb = n + 1, tb.tb_next
        return n

    assert len(made) >= 50  # one raise per page, none shared
    assert depth(made[-1]) <= depth(made[0])


def test_title_wide_label_row_linear(test_cfg):
    import time

    # a gap wider than the column gap, so each word is a cell of the one row
    words = [word("SHEET", 930.0 + i * 20.0, 700.0, 938.0 + i * 20.0, 708.0) for i in range(99_999)]
    start = time.perf_counter()
    entry(parse(test_cfg, page(n=1, words=words)))
    assert time.perf_counter() - start < 2.0


def test_disagreement_listing_capped_per_page(test_cfg, monkeypatch):
    monkeypatch.setattr(pdf, "MAX_LISTED_PER_PAGE", 20)

    def case(n):
        rows = [
            gen.LP22_CELLS[1],
            *[[str(2 * i + 1), "Load", "20", "1", "2", "1.0"] for i in range(n)],
        ]
        notes = grid_annots(rows)
        words = [word("zz", a["x0"], a["top"] + 2, a["x1"], a["top"] + 9) for a in notes]
        out = parse(test_cfg, page(chars=10, annots=notes, words=words))
        return out, [u for u in out.unparsed if "disagree" in u.reason], entry(out).what_read

    _, listed, text = case(12)
    assert len(listed) == 20
    assert "78 cells where annotation text and page text disagree, 20 listed" in text
    _, listed, text = case(2)
    assert len(listed) == 18
    assert "18 cells where annotation text and page text disagree, listed" in text


# (rows, what_read must hold, what_read must not hold); the shape named first in each row
SHAPES = [
    ("A3", [["REV", "STATUS"], ["C", "IFC"]], ["revision C"], ["revision STATUS"]),
    ("A5", [["SHEET", "DISCIPLINE"], ["ES", "ELECTRICAL"]], ["sheet ES"], ["sheet DISCIPLINE"]),
    (
        "A7",
        [["REV", "PROJECT TITLE"], ["C", "MAIN ST TOWER"]],
        ["revision C"],
        ["revision PROJECT"],
    ),
    (
        "C4 firm",
        [["B", "IFC", "2026-02-09"], ["REV", "DESCRIPTION", "DATE"], ["ACME ENGINEERING"]],
        ["revision not found"],
        ["ACME"],
    ),
    (
        "C5 title",
        [["1", "IFC", "2026-02-09"], ["REV", "DESCRIPTION", "DATE"], ["LIGHTING"]],
        ["revision not found"],
        ["LIGHTING"],
    ),
    (
        "C6",
        [["REV", "REMARKS", "DATE"], ["A", "ISSUED FOR PERMIT", "2026-01-05"]],
        ["revision A"],
        ["revision REMARKS"],
    ),
    (
        "C7",
        [["REV", "REVISION DESCRIPTION", "DATE"], ["A", "ISSUED FOR PERMIT", "2026-01-05"]],
        ["revision A"],
        ["revision REVISION"],
    ),
    ("E2 firm beside", [["REV", "ACME ENGINEERING"], ["C"]], ["revision C"], ["ACME"]),
    (
        "F1",
        [["NO.", "REVISION", "DATE"], ["1", "ISSUED FOR PERMIT", "2026-01-05"]],
        ["revision not found"],
        ["ISSUED"],
    ),
    (
        "F2",
        [["NO.", "DATE", "REVISION", "BY"], ["1", "2026-01-05", "ISSUED FOR CONSTRUCTION", "JD"]],
        ["revision not found"],
        ["ISSUED"],
    ),
    (
        "F3 owner",
        [
            ["2", "IFC", "2026-02-09"],
            ["REV", "DESCRIPTION", "DATE"],
            ["OWNER"],
            ["CITY OF CALGARY"],
        ],
        ["revision not found"],
        ["CITY", "revision OWNER"],
    ),
    (
        "F4 key plan",
        [["2", "IFC", "2026-02-09"], ["REV", "DESCRIPTION", "DATE"], ["KEY PLAN"]],
        ["revision not found"],
        ["KEY"],
    ),
    (
        "F5 project",
        [["2", "IFC", "2026-02-09"], ["REV", "DESCRIPTION", "DATE"], ["PROJECT"], ["MAIN ST"]],
        ["revision not found"],
        ["MAIN"],
    ),
    (
        "F6 firm",
        [
            ["C", "IFC", "2026-03-09", "JD"],
            ["REV.", "DESCRIPTION", "DATE", "BY"],
            ["ACME ENGINEERING LTD."],
        ],
        ["revision not found"],
        ["ACME"],
    ),
    (
        "F7 seal",
        [
            ["0", "IFC", "2026-02-09", "JD"],
            ["REV", "DESCRIPTION", "DATE", "BY"],
            ["PERMIT TO PRACTICE"],
        ],
        ["revision not found"],
        ["PERMIT"],
    ),
    (
        "sheet no value",
        [["SHEET NO."], ["ELECTRICAL PLAN"]],
        ["sheet number not found"],
        ["ELECTRICAL"],
    ),
    (
        "sheet beside title",
        [["SHEET NO.", "ELECTRICAL PLAN"]],
        ["sheet number not found"],
        ["ELECTRICAL"],
    ),
    # controls: right shapes still read
    ("E-501", [["SHEET NO.", "E-501"]], ["sheet E-501"], []),
    ("E1.01", [["SHEET", "E1.01"]], ["sheet E1.01"], []),
    ("E-1", [["SHEET", "E-1"]], ["sheet E-1"], []),
    ("ES", [["SHEET", "ES"]], ["sheet ES"], []),
    ("E0.00", [["SHEET", "REV"], ["E0.00", "0"]], ["sheet E0.00, revision 0"], []),
    ("E-501 OF 12", [["SHEET"], ["E-501 OF 12"]], ["sheet E-501 OF 12"], []),
    ("rev C", [["REV", "C"]], ["revision C"], []),
    ("rev 2", [["REV", "2"]], ["revision 2"], []),
    ("rev 10", [["REV", "10"]], ["revision 10"], []),
    ("rev P1", [["REV", "P1"]], ["revision P1"], []),
]


def test_title_value_shape_gates(test_cfg):
    for name, rows, want, forbid in SHAPES:
        text = title_text(test_cfg, rows)
        for part in want:
            assert part in text, f"{name}: {part!r} missing from {text!r}"
        for part in forbid:
            assert part not in text, f"{name}: {part!r} read from {text!r}"


def test_title_shape_keys_from_config(test_cfg):
    assert "revision 10" in title_text(test_cfg, [["REV", "10"]])
    short = with_parsing(test_cfg, pdf_title_revision_max_chars=1)
    assert "revision not found" in title_text(short, [["REV", "10"]])
    assert "revision C" in title_text(short, [["REV", "C"]])
    long = with_parsing(test_cfg, pdf_title_sheet_max_chars_without_digit=10)
    assert "sheet number not found" in title_text(test_cfg, [["SHEET", "ELECTRICAL"]])
    assert "sheet ELECTRICAL" in title_text(long, [["SHEET", "ELECTRICAL"]])


def test_all_page_listings_capped(test_cfg):
    rows = [gen.LP22_CELLS[1], *[["", "Load", "20", "1", "2", "1.0"] for _ in range(500)]]
    ann = grid_words(rows, top=40.0, rowh=11.0)
    lone = [
        word(f"zq{i}", 700.0, 20000.0 + i * 100.0, 710.0, 20007.0 + i * 100.0) for i in range(500)
    ]
    out = parse(test_cfg, page(words=ann + lone, height=100000.0))
    text = entry(out).what_read
    assert len(out.unparsed) <= pdf.MAX_LISTED_PER_PAGE, text
    assert "500" in text and "first 50 shown" in text, text
    small = parse(test_cfg, page(words=grid_words(gen.LP22_CELLS)))
    assert "shown" not in entry(small).what_read


def test_title_staircase_linear(test_cfg):
    import time

    def w(t, col, row):
        return word(
            t, 10000.0 + 4.0 * col, 9000.0 + 2.0 * row, 10001.0 + 4.0 * col, 9000.5 + 2.0 * row
        )

    rows, words = 223, []
    for r in range(rows):  # row r: values under every earlier header's columns, then two labels
        words += [w("1", c, r) for c in range(2 * r)] + [
            w("SHEET", 2 * r, r),
            w("REV", 2 * r + 1, r),
        ]
    pg = page(words=words, width=12000.0, height=10000.0)
    start = time.perf_counter()
    entry(parse(test_cfg, pg))
    assert time.perf_counter() - start < 1.0
