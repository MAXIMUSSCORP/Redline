# AI, OCR and Vision for Reading Electrical Drawing Sheets (Redline research)

Research date: 2026-11-06. Role in Redline: fallback only, for what deterministic DXF/PDF-text parsing misses, and for scanned PDFs. Where I could not verify a claim from a primary source I say so. Costs marked "est." are my arithmetic, not vendor quotes.

## 1. Multimodal LLMs

### Claude (Anthropic)
- **How:** send a page as an image or a PDF `document` block, force JSON via structured outputs (`output_config.format`) or `strict` tool use. The vendor's published pricing (cached 2026-10-06) lists: Opus 5.5 `claude-opus-5-5` $4/$20 per MTok, Sonnet 5.5 `claude-sonnet-5-5` $2/$10, Haiku 5.5 `claude-haiku-5-5` $0.10/$0.50 (prompts up to 100K), all 1M context. Batch API runs at 50% cost. PDF: 32 MB request, up to 600 pages, citations available. Note: Sonnet/Opus 5.5 return 400 on forced `tool_choice`, so use structured outputs. Source: the vendor's published pricing (cached 2026-10-06), https://platform.claude.com/docs/en/build-with-claude/vision
- **Image limits:** JPEG/PNG/GIF/WebP; images cost ceil(w/28) x ceil(h/28) visual tokens; Opus 4.7 and later accept up to 2576 px long edge (about 4784 visual tokens), larger images are downscaled; more than 20 images per request drops the cap to 2000x2000. Source: https://platform.claude.com/docs/en/build-with-claude/vision
- **Est. per page cost:** one full-resolution sheet is about 4.8K input tokens plus about 1.5K output tokens. Sonnet 5.5: about $0.025/page, about $0.012 on Batch. Haiku 5.5: about $0.002/page. Tiling a sheet into 6 crops: about $0.06 (Sonnet 5.5) or $0.03 (Batch).
- **Pros:** best schema-following and instruction handling, cheap per page for a fallback, no training. **Cons:** a D-size sheet downscaled to about 2.5K px loses small schedule text, hence tiling; hallucination risk on dense tables; non-deterministic; cloud only (drawing data leaves the machine).

**Verified 2026-11-06 against official pages (second pass):** Sonnet 5.5 $2/$10 per MTok, Opus 5.5 $4/$20, Haiku 5.5 $0.10/$0.50 (up to 100K prompt; $0.50/$2.50 above), Batch API 50% off input and output (Sonnet 5.5 batch $1/$5). https://platform.claude.com/docs/en/about-claude/pricing . Vision: 28x28 patches, tokens = ceil(w/28) x ceil(h/28); max 8000x8000 px per image; up to 600 images per request (100 for 200K-context models); 128 MB request limit on the first-party API; 5 MB per image on Bedrock/Vertex. Example from the table: a 3840x2160 image is downscaled to 1456x819 (1,560 tokens) on older models and 2576x1449 (4,784 tokens) on Opus 4.7+ high-res models. https://platform.claude.com/docs/en/build-with-claude/vision . I did not re-verify the PDF-specific limits (32 MB / 600 pages) from the PDF docs page; they come from the claude-api skill reference.

### GPT and Gemini
- GPT-4o: a vendor blog on 20 door/window schedules from 18 architectural drawings found Gemini best and GPT "significantly behind"; higher resolution and prompt tuning did not help. Vendor write-up, not peer reviewed. https://dev.to/businessware/benchmark-how-well-ai-models-handle-table-processing-29kl
- Gemini pricing, official page (ai.google.dev redirects to https://aistudio.google.com/docs/pricing, read 2026-11-06): Batch API is 50% lower; Gemini 3.1 Pro Preview $2/$12 per MTok (up to 200K prompt); Gemini 3.1 Flash-Lite $0.25/$1.50; Gemini 3.5 Flash-Lite $0.30/$2.50; a Gemini 3.8 Flash at $0.75/$3.75 (rising to $1.50/$7.50 on 2027-01-01) and a flagship listed at $2/$10 (rising to $4/$20 on 2026-12-01). Gemini 2.5 Pro/Flash requests auto-route to newer models on 2026-12-01, so 2.5 pricing is moot. Prices change often; recheck before building. Per-page PDF/image token counts were not in the part of the page I read (the last ~3.5K characters were not read). Older third-party figures (2.5 Pro $1.25/$10) are superseded.
- Gemini ingests PDFs natively with long context.

### Evidence on accuracy
- **DrawingVQA (arXiv 2607.15418, 2026):** 92 questions on 33 structural construction drawings. Overall accuracy: Gemini-3-pro-preview 77.2, Gemini-2.5-Pro 71.7, Gemini-2.5-Flash 66.3, o3 58.7, Qwen3-VL-32B 58.7, Claude-4.5-Sonnet 57.6, Claude-4.5-Haiku 54.3, GPT-4o 48.9, Qwen3-VL-8B 53.3; human average 68.4 (professionals 94.9). Small benchmark and question answering, not table transcription, but it shows frontier models are near non-expert human level at best on real drawings, and Gemini leads. https://arxiv.org/html/2607.15418v1
- **OmniDocBench v1.5 end-to-end table TEDS (generic documents, not drawings):** PaddleOCR-VL 90.89, MinerU2.5 88.44, Gemini-2.5 Pro 85.71, Qwen2.5-VL-72B 82.15, GPT-4o 67.07 (as summarised by a search result of the official repo; PaddlePaddle self-reported figures are partly vendor numbers, not re-opened). https://github.com/opendatalab/OmniDocBench/tree/v1_5 , https://arxiv.org/pdf/2510.14528
- **GD&T extraction from 2D drawings (arXiv 2411.03707):** Florence-2 fine-tuned vs zero-shot GPT-4o and Claude-3.5-Sonnet; a secondary summary reports Claude-3.5-Sonnet 74% feature-quantity accuracy and GPT-4o 8% hallucination rate (not verified in the paper itself). https://arxiv.org/pdf/2411.03707
- XLLM 2025 (Nunes et al.): on table images, CV methods still slightly better for structure, MLLMs far better for cell text content (GPT-4o, Phi-3 Vision, Granite Vision). https://aclanthology.org/2025.xllm-1.2
- Enginuity (arXiv 2606.03410, June 2026), engineering manuals, tested GPT-5.2, Claude Opus 4.7, Qwen3-VL: Recall@all 0.61-0.87 but Token F1 only 0.03-0.18, i.e. they find parts but describe them poorly. https://arxiv.org/html/2606.03410v1
- I found no published benchmark of any LLM on electrical panel schedules specifically. Redline must build its own small gold set (10-20 real sheets).
- **Strategies that work in practice:** tile or crop to one table per call; ask per table, not per sheet; give the parsed text neighbourhood as context; narrow comparison prompts beat broad ones (https://dbia.org/blog/the-pre-con-sandbox-a-practical-guide-to-prompting-ai-for-design-build-drawing-reviews/, practitioner guide); require the model to return "unreadable" instead of guessing; run twice and diff.

## 2. OCR engines

| Engine | Notes |
|---|---|
| Tesseract | Apache-2.0, local, CPU. Weak on drawings: stock model got 14.65% correct cell words on engineering-chart tables, 58% after retraining, 100% only with domain post-rules on a narrow test set (https://ir.lib.ncu.edu.tw/handle/987654321/92872). Struggles with 90-degree rotated text and text near linework (https://groups.google.com/g/tesseract-ocr/c/F7Gu4o7hBKk). Mitigate: tile at high DPI, binarize, rotate detection (https://www.geosurge.ai/corpus/gen-4384/engineering-drawing/ocr-for-engineering-drawings.html). Gives per-word confidence (used as a quality gate, avg <80 = low quality: https://openaccess.cms-conferences.org/publications/book/978-1-964867-75-5/article/978-1-964867-75-5_221). Windows: installer plus `pytesseract`, easy. |
| PaddleOCR (PP-OCRv5, PP-StructureV3) | Apache-2.0, local. `pip install paddleocr[doc-parser]` plus PaddlePaddle; GPU needs driver >=452.39 on Windows and RTX 50-series needs special wheels (https://www.paddleocr.ai/latest/version3.x/installation.html). Has angle classification and table recognition; CPU works but slow. More install pain than Tesseract. I did not verify accuracy on CAD fonts. |
| EasyOCR | Verified: Apache-2.0, 80+ languages, GPU optional (`gpu=False` for CPU; on Windows install torch first). https://github.com/JaidedAI/EasyOCR . No table model; text-line recognition only. Skip for Redline. |
| Azure Document Intelligence | Cloud. Official page re-fetched: prices render as "$-" placeholders, so still unverified. Secondary sources only: Read about $1.50/1000 pages, Layout/prebuilt about $10/1000, custom extraction $30-50/1000. Returns per-word and per-cell confidence. https://azure.microsoft.com/en-ca/pricing/details/ai-document-intelligence/ , https://erpresearch.com/erp-add-ons/ocr/azure-document-intelligence/pricing |
| AWS Textract | Cloud. Official page verified (US West Oregon, first 1M pages): Detect Document Text $0.0015/page, Tables $0.015, Forms $0.05, Queries $0.015; Layout free when used with Tables. Per-block confidence. https://aws.amazon.com/textract/pricing/ |
| Google Document AI | Cloud. Offers Enterprise Document OCR, Layout Parser, Form Parser, priced per 1,000 pages; the pricing page fetched without figures, so prices unverified. https://cloud.google.com/document-ai/pricing . Same business-document training caveat as Azure/Textract. |

Cloud OCR is trained on business documents (invoices, forms), not CAD sheets with rotated, dense text; no benchmark found for drawings.

## 3. Symbol detection (YOLO-style)
- **SkeySpot (arXiv 2508.10449, Aug 2025):** DELP dataset of 45 scanned UK electrical layout plans, 2,450 instances, 34 symbol classes; open-source toolkit. **Correction after reading the paper's HTML (Table II, test set of 13 plans, 5-fold mean):** YOLOv8 mAP50 81.12%, mAP75 46.86%, mAP50-95 48.24%; Faster R-CNN 48.62 / 25.54 / 26.13. The abstract says "mAP of 82.5%", which does not match Table II; my earlier "82.5% mAP@50, 81.1% mAP@[50:95]" was wrong. Use about 81% mAP50 and about 48% mAP50-95. Tiny dataset (45 plans), so expect lower on Canadian drawings. https://arxiv.org/html/2508.10449v1
- YOLOv8m fine-tuned on FloorPlanCAD (architectural symbols): mAP50 0.877 (search summary, original source not opened). Tile-based training helps small symbols on large plans.
- Effort: labeling hundreds of instances per class, Canadian symbol conventions differ from UK, per-firm symbol libraries vary. Realistic: 1-2 weeks to label and train a 10-class model; Ultralytics is dual-licensed AGPL-3.0 or a paid Enterprise License for products/services (verified on the repo page; AGPL obligations themselves not re-read): https://github.com/ultralytics/ultralytics . Roboflow hosted training exists; I did not verify pricing.
- **Verdict for Redline:** the project reads schedules, circuits and feeders, not device counts from plans. Symbol detection is a later add-on for plan-vs-schedule cross-checks, not a fallback for tables.

## 4. Document-understanding models
- **Docling (IBM):** MIT code; Granite-Docling-258M Apache-2.0. Local, tables via TableFormer, handles scanned PDFs through OCR plugins. Best permissive option for generic PDFs. https://arxiv.org/html/2408.09869v5 , https://ibm.com/new/announcements/granite-docling-end-to-end-document-conversion
- **Marker / Surya (correction):** my first-pass "GPL" claim came from third-party pages and is wrong per the repos. Both repos: code Apache-2.0; model weights under a modified AI Pubs Open RAIL-M licence, free for research, personal use and startups under $5M funding/revenue, otherwise paid via Datalab. https://github.com/datalab-to/marker , https://github.com/datalab-to/surya . Read MODEL_LICENSE before commercial use. (Docling's Surya plugin is flagged GPL in Docling docs, a separate matter, unverified.)
- **Qwen3-VL (open weights, local):** Apache-2.0; dense 2B/4B/8B/32B and MoE 30B-A3B/235B-A22B; the repo gives no VRAM figures (rule of thumb, unverified: 8B needs a 16-24 GB GPU). Vendor claims 32-language OCR and long-document parsing. https://github.com/QwenLM/Qwen3-VL . On DrawingVQA: 32B 58.7, 8B 53.3 vs Gemini-2.5-Pro 71.7, so local VLMs trail frontier cloud models on drawings.
- **Florence-2:** fine-tuned for GD&T extraction from drawings in arXiv 2411.03707 (compared with GPT-4o/Claude-3.5); needs labeled drawing data. Licence not verified (believed MIT).
- **Nougat, LayoutLM/LayoutLMv3, Donut, table-transformer:** not researched in this pass; trained on papers/forms/business docs; some weights are reportedly non-commercial licensed (unverified). Skip.

## 5. Hybrid approaches
- Parse vector text first, route only gaps to vision. Verifier pattern: second pass checks extracted table vs the rendered region, re-rendering suspect regions (https://arxiv.org/pdf/2604.12282, spreadsheets, not drawings). LLM auditing of parsed tables against source PDF is also used in https://arxiv.org/pdf/2510.22087.
- Header normalisation (messy header to schema column) is a text-only task: cheap, safe with Haiku-class model, and testable on parsed text without images.
- I found no open repo doing this for electrical construction docs. Vendor material (e.g. https://nomic.ai/glossary/ai-for-schedule-drawings) claims CV plus LLM hybrids; treat as marketing.

## 6. Confidence reporting
- **Tesseract:** per-word 0-100. **Azure/Textract:** per-word, per-cell confidence in the response. Useful but not calibrated to Redline's rules.
- **LLM self-reported confidence:** generally poorly calibrated and overconfident (well-known; I did not find a drawing-specific source, so this is general knowledge). Do not use as the main signal.
- **Better proxy: agreement.** Two independent reads (vector text vs vision; or two LLM runs; or LLM vs OCR) agreeing on a cell = high; disagreement = flag. Also hard validators: breaker sizes in standard sizes, voltage values valid, phase balance sums, numeric ranges, circuit numbers contiguous.

## (a) Comparison table

| Option | Local/Cloud | Cost | Accuracy on schedules | Licence | Build effort |
|---|---|---|---|---|---|
| Claude vision (Sonnet 5.5/Haiku 5.5) | Cloud | ~$0.01-0.06/page (est.) | Good on cell text, unproven on dense sheets | Commercial API | 1 day |
| Gemini / GPT vision | Cloud | Similar | Gemini reportedly better than GPT-4o on schedules (vendor blog) | Commercial | 1 day |
| Tesseract | Local CPU | Free | Poor on stock, rotation issues | Apache-2.0 | 1-2 days plus tuning |
| PaddleOCR / PP-Structure | Local (GPU helps) | Free | Unverified on CAD | Apache-2.0 | 2-4 days |
| Azure DI / Textract | Cloud | $1.5-15 /1000 pages | Good on forms, unverified on drawings | Commercial | 2 days |
| Docling | Local | Free | Fine for scanned text PDFs, not drawings | MIT | 1-2 days |
| YOLO symbol detector | Local | Free + labeling | ~81% mAP50, ~48% mAP50-95 on UK plans (13-plan test) | AGPL or paid (Ultralytics) | 1-2 weeks |
| Qwen3-VL local | Local GPU | Free | 53-59% on DrawingVQA vs 72% Gemini-2.5-Pro | Apache-2.0 | 2-4 days |

## (b) Recommendation
- **Weekend MVP:** build none of it. Deterministic parsing only, and emit explicit "sheet not parseable, manual check" findings for scanned or unparsed sheets. If there is time, add Claude vision as an opt-in flag (`--vision`), nothing more.
- **v2:** Claude vision fallback (below), a 10-20 sheet gold set, agreement/validator confidence, LLM header normalisation. **v3:** local OCR (Tesseract or PaddleOCR) as a cheap second read for agreement checks; Azure Layout if scanned PDFs are common; YOLO symbol detection only if plan-vs-schedule checks become a goal.

## (c) Proposed vision-fallback design
**Triggers (per page or per table region):**
1. Page has no usable text layer (scanned) or text layer is below a character-count threshold.
2. Parser finds a panel header but fewer than N circuits, or required columns (breaker, wire, load, description) missing.
3. Parsed table fails validators (non-standard breaker size, non-numeric load, gaps in circuit numbers).
4. User forces it for a sheet.

**Procedure:**
- Render the page at 200-300 DPI; crop the table region (from parser bounding box, else tile with 10% overlap). Keep crops under about 2500 px long edge.
- Call Sonnet 5.5 (Haiku 5.5 for header normalisation) with structured output, one table per call, optional parsed text attached as hint. Use Batch API for non-interactive runs.
- Prompt core: "Transcribe this electrical panel schedule exactly. Copy values as printed; never infer or correct. Use null and `unreadable: true` for any cell you cannot read. Do not compute totals." Schema: `{panel_name, voltage, phases, rows:[{circuit, breaker_a, poles, wire, load_va, description, cell_flags:{field: "ok"|"unclear"|"unreadable"}}], notes}`.
- Run twice (or once vs parsed text/OCR) and diff cell by cell.

**Tagging:** every vision-derived field gets `source: "vision"`, `confidence: "low"` by default. Promote to `medium` only when two reads agree or the value matches parsed text; never "high". Any finding that depends on a low-confidence or disagreeing cell is reported as `NEEDS MANUAL CHECK` with the crop image path and page number, never as a pass or confirmed code violation. Log model id, prompt version and cost per page. Self-reported LLM confidence may be stored but is not used for gating.
