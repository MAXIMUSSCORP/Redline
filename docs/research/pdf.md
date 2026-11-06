# Redline research: extracting structured data from PDF drawing sets

Date: 2026-11-06. Scope: CAD-plotted (vector) and scanned PDFs; panel schedules, feeder schedules, SLD text, title block, device tags.

Evidence note: searches (standard mode) returned little CAD- or electrical-specific material. Claims about CAD behaviour are mostly reasoned from library docs and are marked "(inference)". Treat accuracy estimates as hypotheses to test on 5-10 real sheets, not measured figures.

## 1. Key finding: the first fork is "is there real text?"

AutoCAD SHX fonts are plotted as pen strokes (vector geometry), not text. Autodesk and Aconex documentation say SHX text is not searchable in PDF output; TrueType text is. AutoCAD Electrical's Publish dialog has a "Substitute TrueType fonts for SHX fonts" option. Bluebeam's AutoCAD plugin can add OCR data to make SHX text searchable ([Bluebeam](https://support.bluebeam.com/articles/autocad-pdfs-dont-contain-searchable-text), [Autodesk forum](https://forums.autodesk.com/t5/autocad-forum/searchable-pdfs-from-shx-fonts/td-p/6621435), [Aconex](https://help.aconex.com/handover/standardize-the-pdf-output-of-drawings/), [Autodesk Electrical help](https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-Electrical/files/GUID-3C7C25AD-43BE-4C09-A577-37EB2BF51D39.htm)). AutoCAD's `PDFSHX` system variable (named `EPDFSHX` in 2016 SP1) controls this: Autodesk says SHX text is not supported in PDF, so exported drawings can carry it as comments or hidden text labelled "AutoCAD SHX Text". Values: 1 (default) = comments, 2 = hidden text, 0 = nothing, geometry only ([search summary of Autodesk help](https://help.autodesk.com/view/ACD/2024/ENU/?guid=GUID-56EA988C-A1DA-4E85-8765-B3F31A01AB02), [CADforum](https://www.cadforum.cz/en/variable.asp?cmd=PDFSHX), [cadplotting.com](https://cadplotting.com/pdf-shx-text-pdfshx-autocad/)). I could not open the Autodesk help page body directly, so the value list is from secondary pages and the search snippet; the 0/1/2 meanings differ slightly between sources (unverified). Forum users report comment-based SHX text is only searchable if the viewer searches comments, and one Autodesk answer says there is no way to make SHX searchable at plot time other than OCR in a third-party editor ([Autodesk forum](https://forums.autodesk.com/t5/autocad-forum/searchable-pdfs-from-shx-fonts/td-p/6621435), [Autodesk Electrical forum](https://forums.autodesk.com/t5/autocad-electrical-forum/pdf-s-are-jerky-and-contain-quot-autocad-shx-text-quot/td-p/6835299), [Qoppa](https://kbpdfstudio.qoppa.com/pdf-created-by-autocad-shows-sticky-note-bubbles-on-document/)).

Extraction implications (inference, test on real files): with PDFSHX=1 the SHX strings are likely PDF Text annotations ("sticky notes"), invisible to pdfplumber `chars`/`words` and PyMuPDF `get_text`, but readable via annotation APIs (PyMuPDF `page.annots()`, pypdf `/Annots`) with the `/Contents` string and a rect near the geometry. These may be position-approximate and may be one comment per string. PDFSHX=2 (hidden text) may appear as normal invisible chars. So Redline should (a) read annotations as an extra text source, (b) not trust them blindly, and (c) cross-check against OCR. Tell the design team to plot with TrueType substitution ("Substitute TrueType fonts for SHX fonts" in Publish; [Autodesk Electrical help](https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-Electrical/files/GUID-3C7C25AD-43BE-4C09-A577-37EB2BF51D39.htm)) or to change text styles to TrueType; Autodesk's page notes the substitution affects only the PDF and Big Fonts are not substituted (from search summary). I did not find a standalone Autodesk TrueType plotting guide beyond this.

Consequence: a vector PDF from a consultant may have zero extractable text for the schedule, yet look perfect on screen. No table library fixes this; OCR or a vision model is needed. Redline must detect this case per page and route accordingly.

## 2. Options

### pdfplumber
- How: built on pdfminer.six. Exposes `chars`, `words` (x0, top, x1, bottom), `lines`, `rects`, `curves`; `extract_tables()` with `vertical_strategy`/`horizontal_strategy` of `lines`, `lines_strict`, `text`, `explicit`; tolerances (snap, join, text_x/y). `Page.crop(bbox)` isolates a region, useful for a title block or a single panel ([docs summary](https://tessl.io/registry/tessl/pypi-pdfplumber/files/docs/table-extraction.md), [discussion #1344](https://github.com/jsvine/pdfplumber/discussions/1344), [Nutrient guide](https://www.nutrient.io/blog/pdfplumber-python-guide/)).
- Version/license: 0.11.10, 2026-06-15, MIT ([PyPI](https://pypi.org/project/pdfplumber/)).
- Pros: MIT, pure Python, great low-level access to words and geometry, easy to debug visually. Mixed strategy (lines vertically, text horizontally) fits CAD tables with column rules but no row rules (inference).
- Cons: pure Python so slow on dense large-format sheets (inference; benchmark on your sheets). Text strategy is tolerance-sensitive. Rotated text and multiple tables per sheet need manual cropping.
- Accuracy on CAD schedules: good when text is real and a grid is drawn; poor on text-only layouts without tuning. Expect 80-95% cell accuracy after per-template tuning (hypothesis).
- Cost: free. Effort: 1-2 days for a robust row/column clusterer. Local.

### PyMuPDF (fitz)
- How: `get_text("words"/"dict")` gives positions, fonts, rotation; `page.find_tables()` (added 1.23.0) with `lines`, `lines_strict`, `text` strategies, `clip`, `add_lines`, and `paths` to reuse `get_drawings()` output; tables export to markdown/pandas ([docs](https://pymupdf.readthedocs.io/en/latest/page.html)). `get_drawings()` returns vector paths; `get_pixmap()` rasterizes for OCR (those two not verified on the docs page I could read).
- Version/license (verified 2026-11-06): PyPI lists 2.1 (released 2026-11-02), "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License" ([PyPI](https://pypi.org/project/PyMuPDF/)); the official docs say they cover PyMuPDF 2.1, offer AGPL or commercial terms, tell users who cannot meet AGPL to contact Artifex (exclusive commercial agent), and ship AS-IS ([docs](https://pymupdf.readthedocs.io/en/latest/about.html)). Neither says anything about "internal company use"; that question needs a lawyer or Artifex (unverified).
- Pros: C-backed, fast; best single library for words + drawings + rasterization; its page-level word/drawing access is the most convenient for symbol detection.
- Cons: AGPL. Internal-only use inside one company is generally lower risk than distribution, but if Redline is ever sold, hosted as a service for others, or shipped to clients, you need an Artifex commercial license or must open source. Get legal advice before relying on this; I did not find authoritative guidance on "internal use" in the sources.
- Accuracy: similar to pdfplumber on ruled tables; Camelot's docs describe PyMuPDF's finder as geometry-only ([Camelot comparison](https://camelot-py.readthedocs.io/en/latest/user/comparison.html)).
- Cost: free (AGPL) or commercial (quote). Effort: 1-2 days. Local.

### Camelot (2.0.0)
- How: `lattice` (ruled), `stream` (whitespace), and `network`/`hybrid` (added in 1.0); optional ML flavor using Table Transformer. 2.0.0 released 2026-06-04, MIT, Python 3.10+; default backend is pdfium; Ghostscript and poppler are optional extras; OpenCV is used by the `combined` engine ([PyPI](https://pypi.org/project/camelot-py/), [comparison](https://camelot-py.readthedocs.io/en/latest/user/comparison.html)). This overturns old advice that Ghostscript is mandatory.
- Pros: actively maintained, confidence score per table, better merged-cell and multi-row-header handling than pdfplumber per its own docs (vendor-authored; treat cautiously). Vector-only engine ~9x faster than combined with similar quality per its docs.
- Cons: table-centric; no help with free text, title blocks, or SLD. Lattice on CAD output depends on lines being real lines (not many tiny segments); tune `line_scale` (inference). Whole-sheet scans of E-size pages may be slow.
- Cost free, MIT. Effort: 0.5-1 day to try. Local.

### Tabula / tabula-py
- Java-based; tabula-py 2.10.0 (2024-10-17), MIT, needs Java 8+ ([PyPI](https://pypi.org/project/tabula-py/)). Lattice/stream. Camelot's docs say Tabula's stream auto-detection is generally stronger on borderless tables. Last release is a year old; Java dependency is a deployment burden. Not recommended over Camelot/pdfplumber.

### pdfminer.six, pypdf, poppler pdftotext, pdf2image
- pdfminer.six: the engine under pdfplumber (per [pdfplumber PyPI](https://pypi.org/project/pdfplumber/)); no separate source fetched, use pdfplumber instead.
- pypdf: `extract_text(extraction_mode="layout")` gives fixed-width text; `visitor_text` callbacks give per-fragment text matrix/position; rotated text is excluded by default; docs warn positions can be wrong in complicated documents, whole-stream parsing can use lots of RAM, and it is not OCR ([pypdf docs](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)). Verdict: page splitting/metadata only.
- poppler `pdftotext`: `-layout` preserves physical layout; `-bbox` / `-bbox-layout` emit XHTML with word/line/block bounding boxes ([man page](https://manpages.debian.org/testing/poppler-utils/pdftotext.1.en.html)). Useful as a fast CLI cross-check. License not stated on that page (poppler is commonly GPL; unverified).
- pdf2image 1.17.0 (2024-01-07, MIT): wrapper over poppler `pdftoppm`/`pdftocairo`; on Windows you must download a poppler build and set PATH or `poppler_path` ([PyPI](https://pypi.org/project/pdf2image/)). That install friction is a reason to prefer PyMuPDF/pypdfium2 for rasterizing.

### Layout/ML pipelines: Docling, Marker, unstructured, Nougat
- One 2025-26 comparison puts Docling (MIT) ahead on table accuracy, Marker GPL and GPU-hungry, Unstructured emits typed elements with coordinates; the benchmark is vendor-affiliated and complex tables with merged cells still fail ([Ertas](https://www.ertas.ai/blog/pdf-parsing-accuracy-benchmark-docling-unstructured), [CodeCut](https://newsletter.codecut.ai/p/pdf-table-extraction-docling-vs-marker), [Macmyths](https://macmyths.com/docling-alternatives-for-extracting-structured-data-from-documents/)).
- These are tuned for reports and papers, not 36x24 in engineering sheets (inference). Heavy installs, model downloads, GPU wanted. Defer; possibly useful as the OCR/table-structure step later.

### Vector geometry reconstruction (DIY)
- Collect `lines`/`rects` (pdfplumber) or `get_drawings()` (PyMuPDF); snap and merge collinear segments; intersect horizontals and verticals to build cell boxes; assign words to cells by center point. Where no grid exists, cluster words by `top` into rows (tolerance ~ half font height) and by x0 into columns using header-word positions as anchors. PyMuPDF `find_tables(add_lines=...)` and pdfplumber `explicit_*_lines` accept this geometry directly. Effort: 1-3 days. This is the most reliable approach for template-like panel schedules because header words ("CKT", "DESCRIPTION", "VA", "BKR", "POLES", "WIRE") anchor the columns.

### Existing GitHub projects
- Second pass (extended searches on "panel schedule", "electrical schedule", "MEP schedule", "construction drawing" with pdfplumber, plus Docling/Marker trackers): still no repo for panel/MEP schedule extraction. Docling issues that resemble schedule problems (dense columns, merged cells, dropped empty columns, lost minus signs) are [#2756](https://github.com/docling-project/docling/issues/2756), [#2134](https://github.com/docling-project/docling/issues/2134), [discussion #201](https://github.com/docling-project/docling/discussions/201), [#1803](https://github.com/docling-project/docling/issues/1803); none concern engineering drawings. Dropped empty columns and lost signs are bad for schedules. A third-party issue proposes Marker next to Docling for engineering documents ([workspace-hub #1447](https://github.com/vamseeachanta/workspace-hub/issues/1447)) with no table results. Earlier generic results: a pdfplumber schedule-header filter recipe ([playbooks](https://playbooks.com/skills/openclaw/skills/pdf-to-structured)) and an EasyOCR/pypdfium2/OpenCV schedule OCR with deskew and keyword header detection ([HF repo](https://huggingface.co/JoselinMaria/medical-schedule-ocr)). Redline would likely be first-of-kind here; low reuse.

### pdfplumber text-strategy settings (verified from the [README](https://github.com/jsvine/pdfplumber))
Defaults: `snap_tolerance` 3, `join_tolerance` 3, `edge_min_length` 3, `intersection_tolerance` 3, `min_words_vertical` 3, `min_words_horizontal` 1, `text_x_tolerance` 3, `text_y_tolerance` 3 (each has `_x`/`_y` variants). Only `min_words_*` and `text_*` tolerances are specific to the text strategy; the rest apply to line edges. For CAD tables (inference): raise `snap_tolerance`/`join_tolerance` to ~4-6 pt if plotted lines are fragmented; raise `min_words_vertical` to 4-5 so stray labels do not create phantom columns; lower `text_x_tolerance` (1-2) if narrow columns like "P" (poles) fuse into neighbours; a user thread shows snap/join/text_y values of 1-3 for misaligned borderless columns ([#1344](https://github.com/jsvine/pdfplumber/discussions/1344)); another shows `snap_x_tolerance` fixing column alignment ([#1006](https://github.com/jsvine/pdfplumber/discussions/1006)). Units are PDF points, so sheet scale matters; large-format sheets may need different values than letter pages.

### Measured/anecdotal accuracy
No source found measuring any of these tools on CAD-plotted tables. Closest evidence: an arXiv study comparing parsers across document categories found table extraction quality of rule-based tools (Camelot, Tabula, etc.) significantly lower than for other elements, rankings changed by category, and PyMuPDF had the most consistent recall among rule-based tools ([arXiv 2410.09871](https://arxiv.org/html/2410.09871v1), measured but not CAD). Anecdotal, vendor/blog-level: Camelot wins on real ruled grids; its accuracy score is optimistic and misses wrong column assignment ([invoicedataextraction.com](https://invoicedataextraction.com/blog/python-pdf-table-extraction-invoices), [theneuralbase](https://theneuralbase.com/pdf-processing/learn/beginner/camelot-for-complex-tables/), summarized via search snippet, not opened). Camelot's own docs give ICDAR-2013 F1 0.778 for combined lattice (not CAD). The 80-95% figure above stays an unverified hypothesis.

## 3. Known failure modes

| Failure | Symptom | Detection / mitigation |
|---|---|---|
| SHX text plotted as paths | page has few/no chars but many curves/lines | char count vs path count; fall back to OCR |
| Page has "text" but is junk (e.g. PDFSHX comments, hidden OCR layer) | words in wrong places or odd encoding | check overlap of text bbox with rendered ink; check for (cid:N) strings |
| Scanned/raster page | image covers page, no chars | image area ratio; OCR |
| Rotated sheet (/Rotate 90) or rotated text | words with rotated matrices, reversed order | read `page.rotation`; PyMuPDF word/dict gives direction; derotate before clustering |
| Multiple tables per sheet | merged detection | segment by header-keyword anchors, `clip` per panel |
| Merged cells (e.g. 3-pole breaker spanning 3 rows) | blank cells | forward-fill rules specific to panel layout |
| Text in layered OCGs | hidden layer text extracted, or visible text missing | check OCGs via PyMuPDF `layer_ui_configs`/`get_ocgs`; drop hidden-layer chars (not verified in sources) |
| Huge coordinate spaces, tiny line segments | slow or fragmented lines | crop first, merge collinear segments, set tolerances |

## 4. Comparison table

| Option | Text+pos | Table finder | Vector geom | Scan help | License | Speed | Effort (solo) | Local |
|---|---|---|---|---|---|---|---|---|
| pdfplumber | yes | lines/text/explicit | lines/rects/curves | no | MIT | slow-medium | 1-2 d | yes |
| PyMuPDF | yes | find_tables | get_drawings | rasterize, partial OCR | AGPL / commercial | fast | 1-2 d | yes |
| Camelot 2.0 | via backend | lattice/stream/network/hybrid/ML | internal | ML flavor w/ OCR | MIT | medium | 0.5-1 d | yes |
| tabula-py | no | lattice/stream | no | no | MIT | medium (JVM) | 0.5 d | yes (Java) |
| pdfminer/pypdf/poppler | basic | none | no | no | MIT/BSD/GPL (poppler is GPL, verify) | fast | n/a | yes |
| Docling/Marker/unstructured | yes | ML | no | yes | MIT / GPL / verify | slow, GPU | 1-3 d | yes (heavy) |
| Custom geometry clustering | built on above | yours | yes | no | n/a | fast | 1-3 d | yes |

## 5. Recommendation

Weekend MVP: pdfplumber only (MIT, no license question). Steps: per-page text check, find the panel header row by keywords, crop, cluster words into rows/columns anchored on header x-positions, optionally `extract_tables` with mixed strategies as a cross-check. Fail loudly (flag "page not machine-readable") on SHX/scanned pages rather than guess. Skip Camelot, Tabula, ML pipelines.

Later: add PyMuPDF for rasterization and drawings only after resolving AGPL (or use pypdfium2, which Camelot 2.0 also uses by default, to rasterize under a permissive license; not verified in my sources beyond Camelot's note). Add Camelot as a second opinion with confidence scores. Add OCR/vision fallback (covered by another agent) and, if volume justifies, Docling for table structure on raster pages.

## 6. Proposed pipeline for a CAD-plotted panel schedule page

1. Open page (pdfplumber). Record size, `/Rotate`; derotate if needed.
2. Text-layer test: `n_chars = len(page.chars)`; `n_paths = len(lines)+len(rects)+len(curves)`; `img_ratio` from `page.images` area. Classes:
   - `n_chars` high and sane (contains expected keywords like CKT, BKR, PANEL) -> vector text path.
   - `n_chars < ~50` while `n_paths` is in the thousands -> SHX-as-paths. Also flag when `n_chars` is high but expected keywords are absent (junk layer).
   - `img_ratio > ~0.8`, no chars -> scanned.
   Thresholds are guesses; calibrate on real sheets.
3. Non-text classes: rasterize (pdfplumber `page.to_image(resolution=300)` or PyMuPDF/pypdfium2) and hand off to OCR/vision; keep line geometry from step 1 to guide cell splitting (inference: grid lines are still available as vector paths in the SHX case).
4. Locate tables: find header keyword words; derive each panel's bbox by extending to the nearest enclosing rect or to the next header; `page.crop(bbox)` per panel.
5. Build grid: if `lines`/`rects` exist in the crop, snap/merge and use `explicit_*_lines`; else cluster words by y (row tolerance ~0.5x font height) and x anchored at header word x0/x1.
6. Extract cells, forward-fill merged cells (poles/breaker), parse numerics (VA, A, poles, wire size) with regexes; keep per-cell bbox and page number for traceability in Redline findings.
7. Title block: crop bottom-right region (or the rect containing "SHEET"/"REV"), read sheet number and revision by keyword proximity.
8. Validate: circuit numbers sequential, odd/even sides, sum of VA vs panel total; failures lower confidence rather than silently pass.
9. Optional second opinion: Camelot lattice/hybrid on the same crop; diff cells.

## Sources
- https://github.com/jsvine/pdfplumber/discussions/1344
- https://tessl.io/registry/tessl/pypi-pdfplumber/files/docs/table-extraction.md
- https://www.nutrient.io/blog/pdfplumber-python-guide/
- https://pypi.org/project/pdfplumber/
- https://pymupdf.readthedocs.io/en/latest/page.html
- https://pypi.org/project/PyMuPDF/
- https://pymupdftest.readthedocs.io/en/stable/intro.html
- https://pypi.org/project/camelot-py/
- https://camelot-py.readthedocs.io/en/latest/user/comparison.html
- https://pypi.org/project/tabula-py/
- https://www.ertas.ai/blog/pdf-parsing-accuracy-benchmark-docling-unstructured
- https://newsletter.codecut.ai/p/pdf-table-extraction-docling-vs-marker
- https://macmyths.com/docling-alternatives-for-extracting-structured-data-from-documents/
- https://support.bluebeam.com/articles/autocad-pdfs-dont-contain-searchable-text
- https://forums.autodesk.com/t5/autocad-forum/searchable-pdfs-from-shx-fonts/td-p/6621435
- https://help.aconex.com/handover/standardize-the-pdf-output-of-drawings/
- https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-Electrical/files/GUID-3C7C25AD-43BE-4C09-A577-37EB2BF51D39.htm
- https://playbooks.com/skills/openclaw/skills/pdf-to-structured
- https://huggingface.co/JoselinMaria/medical-schedule-ocr
