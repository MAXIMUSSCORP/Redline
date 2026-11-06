# Redline research report

Date: 2026-11-06. Synthesis of the research files, no new research. Bracketed numbers point to Sources. The markers UNVERIFIED, SECONDARY, inference, est. and hypothesis are kept from the source files and mean what they say. Owner decisions in force: full end-to-end build, best DWG option, and a local open-weights AI layer only.

## 1. Summary

- Full-project recommendation for DWG: a C# plugin run under `accoreconsole.exe` (AutoCAD Core Console) when an AutoCAD seat exists [85][86]. Fallback when there is no seat or the console fails: ODA File Converter plus ezdxf [1][3]. Both write one `RawDrawing` JSON, and the rules read only that JSON.
- PDF: pdfplumber first, with custom geometry clustering and a "not machine-readable" stop for SHX-as-strokes pages [24][30][31]. CSV/XLSX from AutoCAD Electrical or DATAEXTRACTION stays a side input [11][14][18].
- AI layer: local open-source or open-weights models only. Hosted APIs (Claude, GPT, Gemini) are out by owner decision. Three hardware tiers: CPU, consumer GPU (12-24 GB), workstation GPU [103][104]. The VLM is a second reader beside OCR and hard validators, never a single-pass oracle.
- Symbol detection: Apache-licensed detectors, RF-DETR N/S/M/L or D-FINE [120]. Ultralytics is excluded because AGPL covers trained weights [60][120].
- A deterministic CEC rule engine with editable code tables sits on top. Fail loudly. Unreadable pages become "not checked / manual review", never a pass [70][84].
- Biggest risk: SHX fonts plotted as geometry, and schedules that exist only as loose text, lines or exploded blocks. A PDF can look perfect and hold no text [24][25][4].
- No open-source schedule extractor and no AI CEC checker exist. Redline builds both [22][83][84]. No open model has been shown reliable on electrical panel schedules [47][51].

## 2. Key facts that shape the design

**Parsing**
- ezdxf is MIT, release 1.4.5 (Oct 2026) [2]. `read_acad_table_content()` returns rows of strings, and all content lands in row one if row and column counts are missing [5][3]. It cannot create or edit ACAD_TABLE [3].
- ODA File Converter is a free closed-source binary that ezdxf wraps. Redistribution terms are UNVERIFIED [1][91].
- A table cell holding a FIELD stores only the field object ID [4]. Inference: field cells may come back empty or stale in ezdxf. Not tested.
- A linked (DATALINK) schedule has cached cell text. Inference: the source XLSX is more reliable, but its path may not ship with the DWG [17].
- AutoCAD Electrical report headings are user-configurable [12]. I found no native panel-schedule object (absence of evidence) [15][16]. Redline needs a header-mapping layer.
- AutoCAD plots SHX text as strokes, not searchable in PDF, unlike TrueType [24][25][26]. `PDFSHX` can add the strings as comments or hidden text, but sources differ on the values (UNVERIFIED) [28][29].
- PyMuPDF is AGPL-3.0 or Artifex Commercial, and the docs are silent on internal use (UNVERIFIED) [33]. pdfplumber and Camelot 2.0 are MIT [30][34].

**Core Console, NETLOAD, fields**
- Core Console (`accoreconsole.exe`) is a console build of AutoCAD with no graphics window, introduced in AutoCAD 2013 [85]. A vendor guide says it ships with every AutoCAD since 2013 [86]. I found no primary Autodesk page naming the 2025 or 2026 path. A 2025 forum tip shows it running on AutoCAD 2025, which is indirect evidence [87].
- Core Console licensing is UNVERIFIED. The vendor guide says both "no extra license" and "requires a local AutoCAD license", and that Autodesk does not officially support it [86]. An old forum thread shows a network-license error [94] (search summary). Whether a headless run consumes a concurrent seat is unknown. Ask Autodesk in writing.
- Only commands implemented in `accore.dll` work. `-PLOT` reportedly fails in the 2021 console [96] (search summary). `vla-*` ActiveX LISP does not run [86]. Speed figures come from a vendor blog with no method, so they are UNVERIFIED [86].
- NETLOAD on .NET 8 is a risk. AutoCAD 2025 moved to .NET 8, which has no AppDomain isolation. A community tip reports the console crashing when a plugin brought its own `System.Data.OleDb` (search summary, page returned 403) [87]. Rule: reference only Autodesk assemblies plus `System.Text.Json`. Whether NETLOAD works on 2025 and later is UNVERIFIED.
- Evaluation differs for FIELD and DATALINK content. Real AutoCAD evaluates fields, so a plugin may return computed text where ezdxf returns a cached string or a bare object ID [4]. The exact .NET table member and whether it returns evaluated text are UNVERIFIED. Test with a FIELD table and a DATALINK table [100].
- `ezdxf.xref` silently ignores ACAD_TABLE and proxy entities, so do not merge xrefs with it when tables matter [90].

**Open-model evidence**
- DrawingVQA (92 questions, 33 structural drawings): Qwen3-VL-32B 58.7 and Qwen3-VL-8B 53.3, against Gemini-3-pro 77.2 and Gemini-2.5-Pro 71.7. Human average 68.4, professionals 94.9 [47].
- AECV-Bench: OCR and text QA reach up to 0.95, but symbol counting is often 0.40-0.55 for all models tested. Abstract read only. Per-model scores not read. Raster only [126].
- OmniDocBench table TEDS is printed documents, not CAD, and partly self-reported. Versions differ: PaddleOCR-VL 90.89 in [48], 92.76 for v1.5 and 94.76 for v1.6 elsewhere [108][110]. Engineering manuals: Token F1 only 0.03-0.18 [51].
- No published number exists for dense electrical-schedule transcription by open VLMs, nor for open-vocabulary detectors on electrical symbols [126][122].
- Stock Tesseract: 14.65% correct cell words on engineering-chart tables [53]. SkeySpot symbols: mAP50 81.12% and mAP50-95 48.24% on 13 UK plans. Its abstract says 82.5%, which the table does not match [59].
- LLM self-reported confidence is poorly calibrated [44]. Use agreement between independent reads and hard validators [64].

**Licence gotchas**
- Ultralytics YOLO is AGPL-3.0 or paid. Trained weights are derivatives, so AGPL obligations attach to a distributed or hosted product [60][120].
- RF-DETR is Apache-2.0 only for detection N/S/M/L and the Seg sizes. XL, 2XL and Atto, Femto, Pico fall under Roboflow PML 1.0 [120].
- YOLO-NAS weights are research and non-commercial only [121]. FloorPlanCAD annotations are CC BY-NC 4.0, so research use only [124].
- Surya and Marker: code Apache-2.0, weights modified OpenRAIL-M, free below $5M revenue or funding [62][110].
- MinerU: Apache-2.0 plus extra conditions. The 100M MAU or $20M monthly revenue thresholds are SECONDARY (docsumo). Read LICENSE.md [111][109].
- Gemma 3 uses the Gemma Terms with flow-down prohibited-use terms. Llama 3.2 Vision has an AUP, a 700M MAU clause, naming rules and an EU-entity restriction [118][119].
- Vendor claims on floor-plan areas (Togal 98%, Kreo 95% UNVERIFIED, UpCodes 93% on 43 questions, internally inconsistent) say nothing about schedules [68][69][75].

## 3. Options by topic

Each option lists how it works, pros, cons, accuracy, cost, licensing, effort and local or cloud. n/f means not found.

### 3.1 DWG and DXF (Part 1 options)

**ODA File Converter + ezdxf** [1][2][3][5]
- How: ODAFC converts DWG to DXF. ezdxf reads `plain_text()` for MTEXT, `insert.attribs`, `block_attribs` for MULTILEADER, and `read_acad_table_content()` for tables.
- Pros: free, local, no AutoCAD seat, all Python. Cons: closed freeware with unconfirmed redistribution terms, R12 to R2018 only [1]. Proxy objects from AutoCAD Electrical may be dropped (UNVERIFIED). Schedule parsing is your own code.
- Accuracy: good for TEXT, MTEXT, ATTRIB. Tables and fields are the risk. Cost $0. Licence: MIT plus freeware. Effort 1-3 days. Local.

**LibreDWG** [6]: CLIs and SWIG bindings, reads all DWG versions. GPL-3, so a separate CLI process usually sidesteps copyleft (get legal advice). Some R2010+ objects are skipped, a silent-data-loss risk. Bindings unverified on Windows. Accuracy medium on 2018+ files. Effort 1-2 days. Local. Cross-check only.

**APS Model Derivative** [7]: translates DWG to SVF/SVF2, then queries properties. Nothing found on what a 2D DWG yields. Cloud, credits, 2-3 days. Weak fit.

**APS Design Automation for AutoCAD** [8][9][10]
- How: runs AutoLISP or .NET in cloud AutoCAD and returns JSON. Billed by processing time. Pros: real AutoCAD engine. Cons: heavy setup, latency, client drawings leave the building, residency and Electrical support unverified.
- Cost: sources conflict (12 minutes per token in a 2020 post, 2.0 Flex tokens per hour in a summary, about $1 per credit UNVERIFIED) [8][9][10]. Effort 3-5 days. Cloud.

**AutoCAD Electrical reports, spreadsheet export, project database** [11][12][13][14][15]
- Reports export to ASCII, Excel, Access, XML or CSV [11]. Column labels come from user-editable `.set` files [12]. Only the Panel BOM column set is documented [13]. The project database is an Access file with 14 documented tables. Edit a copy only [15].
- Pros: clean schematic data. Cons: needs a seat and a human. Building panel schedules are usually plain tables, Excel or Revit exports, which these reports do not cover [15][16]. Accuracy high where applicable. Effort hours. Local, user-side. Offer as "bring your own export".

**DATAEXTRACTION, ATTOUT, LISP** [18][19][20]: `DATAEXTRACTION` writes CSV, TXT, XLS or MDB. `ATTOUT` skips dynamic block properties [19]. A forum title suggests tables are not extracted (UNVERIFIED, title only) [20]. Needs a seat. Effort 2-4 days. Local.

**Open-source schedule extractors** [22][23]: none found. The parser is a differentiator Redline builds.

### 3.1b DWG, full-project options

**AutoCAD Core Console alone** [85][86]
- How: `accoreconsole.exe /i <dwg> /s <script> /l en-US`. Other switches: `/product`, `/isolate`, `/readonly`, `/p`, `/loadmodule` [85]. Scripts take one command per line. A hyphen forces the command-line form. `FILEDIA` is forced to 0. `/isolate` keeps system variables out of the user profile [86].
- Pros: real AutoCAD engine, unattended by design, near-zero marginal cost with an existing seat. Cons: no official documentation or compatibility guarantee [86]. Dialog-driven commands fail. The `DATAEXTRACTION` wizard is probably unavailable (UNVERIFIED) [95]. Whether it loads the Electrical object enabler is UNVERIFIED [102]. Electrical symbols and the WD_M settings block are ordinary blocks with attributes, so they read without the vertical [97].
- Accuracy: highest expected, unmeasured. Cost $0 extra with a seat. Licence: Autodesk subscription, seat use UNVERIFIED. Local. Run it on the named user's workstation or a machine explicitly licensed for it.

**.NET plugin (C#) under Core Console** [85][86][87][88]
- How (design intent from general knowledge of the managed API, not re-verified): open the `Database`, walk `BlockTable`, and read every layout and block definition. Types: `BlockReference` with attributes and dynamic properties, `Table`, `MText` (`.Text` strips formatting), `DBText`, `MLeader`. Xrefs via `IsFromExternalReference` and `PathName`. A `[CommandMethod("REDLINE_DUMP")]` loads with `NETLOAD`, ideally with forward slashes and no quotes in the path [88] (search summary), and writes `<dwg>.redline.json`. Python builds a per-run `.scr` and calls `subprocess.run` with a timeout.
- Pros: may evaluate fields and handle tables and proxies as AutoCAD does [100]. Cons: .NET 8 on 2025+, older seats on .NET Framework, so one build may not cover both. Which versions the firm runs is UNVERIFIED [87]. Do not depend on `c:wd_*` or `ace_*` Electrical calls, since the function reference was not retrieved [89].
- Accuracy highest expected. Cost $0 extra. Effort 3-5 days for the plugin plus 2-3 days for testing and packaging (5-8 days in the matrix). Local.

**COM automation from Python** [92][93]
- `pyautocad` is stale: 0.2.0 from 2015 (search summary) [93]. `cad-pyrx` (LGPLv3, Windows, AutoCAD 2022-2027 plus BricsCAD, ZWCAD, GstarCAD, Python 3.14 only) loads inside the CAD app, and whether it runs in the console is UNVERIFIED [92].
- COM needs the GUI process, is slow and prone to modal hangs (general knowledge, UNVERIFIED). Use for prototyping or a "send current drawing" button only. Effort 2-3 days. Local.

**ODA File Converter + ezdxf recap** [1][2][90]
- ezdxf 1.4.5, 2026-10-16, MIT. No published speed benchmarks. `iterdxf` streams very large DXF. `ezdxf.recover.readfile()` loads damaged files as a fallback [2][90].
- Xrefs: convert each referenced DWG separately with ODAFC and link by block name. Unknown proxy objects stay opaque [90]. The data Redline needs lives in blocks and attributes, which are ordinary entities [97]. Confirm on real files.
- Effort 2-3 days in the matrix. ODAFC redistribution stays UNVERIFIED [91].

**ODA Drawings SDK pricing** [21][91]
- 2026 tiers match 2025: Commercial $3,000 first year and $2,250 renewal (limited commercial use, up to 100 copies), Sustaining $7,500 and $4,500 (unlimited, SaaS allowed), Founding $37,500 and $18,000 (with source). Non-commercial $375 and $150 per Part 1 (the 2026 price PDF came back garbled).
- Commercial membership does not permit Web or SaaS use [91]. A Python wrapper exists only for the Drawings SDK at Core Package and Core Package+ levels. I did not find those prices. Hosted Redline on ODA tech needs Sustaining at the least. Effort 7-10 days. Local. Defer.

**BricsCAD and other paths** [98][99][100]
- BricsCAD Lite: about $293 to $350 per year, perpetual about $590, network perpetual needs 5 seats (search summary). BRX, .NET and LISP exist, and its .NET table class has `GetTextString`. Headless mode and Lite's API limits not verified. Needs its own plugin. Effort 8-12 days. Not worth it while AutoCAD is on hand.
- DWG TrueView: free, batch conversion through the GUI and `.BCL` lists, no command-line scripting found. ODAFC does this better [98].
- nanoCAD, QCAD, LibreCAD, FreeCAD: not researched. LibreCAD is DXF only. FreeCAD DWG import uses the ODA converter (general knowledge, UNVERIFIED).

**Electrical side inputs** [15][97][101]: `.wdp` is a text file of numbered bracketed project properties (search summary). `WD_M` is an invisible block with drawing-wide settings, readable as an INSERT. The `.mdb` project database needs the Access ODBC driver with `pyodbc` on Windows (general knowledge). Headless report export is UNVERIFIED. Plan on human-run reports or the plugin reading blocks.

### 3.2 PDF

**First fork: is there real text?** [24][25][26][27][28][29]
- SHX text is plotted as strokes. `PDFSHX` (`EPDFSHX` in 2016 SP1) reportedly gives 1 comments, 2 hidden text, 0 nothing, but sources differ (UNVERIFIED) [28]. Inference: with 1 the strings are PDF annotations, readable through annotation APIs, maybe position-approximate.
- Mitigation: plot with "Substitute TrueType fonts for SHX fonts". Big Fonts are not substituted [27]. No table library fixes this. Redline detects it per page and routes to OCR or flags the page.

**pdfplumber** [30][31]: `chars`, `words`, `lines`, `rects`, `extract_tables()`, `crop(bbox)`. MIT, 0.11.10. Pros: easy to debug, a mixed strategy fits CAD tables with column rules but no row rules (inference). Cons: slow on dense large sheets (inference), tolerance-sensitive. Accuracy 80-95% after per-template tuning is a hypothesis. Free. Effort 1-2 days. Local.

**PyMuPDF** [32][33]: fast, words plus drawings plus rasterizing. AGPL or paid Artifex licence. Internal-only use is generally lower risk than distribution (inference). Selling, hosting or shipping it needs a commercial licence. Get legal advice. Similar to pdfplumber on ruled tables [34]. 1-2 days. Local.

**Camelot 2.0** [34]: MIT, 2.0.0 (2026-06-04), pdfium backend, per-table confidence. Table-only, and its docs are vendor-authored. ICDAR-2013 F1 0.778 is not CAD. 0.5-1 day. Second opinion only.

**Tabula-py** [35]: Java 8+, MIT, last release 2024-10-17. Skip. **pypdf, poppler, pdf2image** [36][37][38]: pypdf reads `/Annots` (inference for SHX comments). poppler `pdftotext -bbox` is a cross-check (licence UNVERIFIED, commonly GPL). Prefer PyMuPDF or pypdfium2 to rasterize.

**Custom vector geometry reconstruction**: merge collinear segments, intersect lines into cells, assign words by center point. Without a grid, cluster words by `top` and anchor columns on header words such as CKT, DESCRIPTION, VA, BKR, POLES, WIRE. Inference: the most reliable approach for template-like panel schedules. 1-3 days. Local.

### 3.3 Hosted AI, OCR and vision (excluded by owner decision)

The owner ruled out hosted models, so these are kept only as records. Claude vision [42][43][44], Gemini and GPT [45][46], Azure Document Intelligence, AWS Textract and Google Document AI [56][57][58] are cloud, send drawings off the machine, and are Excluded. Facts kept for reference: Textract text $0.0015 per page and Tables $0.015 (verified, US West) [57]. Azure and Google prices are UNVERIFIED [56][58]. The pattern that survives is "parse vector text first, route only gaps to a reader, verify with a second pass" [64][65]. It applies unchanged to local models.

**Tesseract** [53] is Apache-2.0 and local. It is weak on drawings and on 90-degree text and text near linework, and gives per-word confidence. 1-2 days plus tuning. EasyOCR has no table model [55].

### 3.4 Commercial products

None supply Redline's core need.

- **Bluebeam Revu** [66]: $260 to $590 per user per year, no schedule extraction. Where reviewers work.
- **CountFire, Togal.AI, Kreo** [67][68][69]: cloud takeoff. Togal claims 98% on floor plans with no method. Kreo $100, $175, $250 per user per month.
- **Procore OCR, ACC** [70][71]: title-block OCR, cannot confirm a sheet was fully processed.
- **ETAP, EasyPower, AutoCAD Electrical audit, Revit** [72][73][74]: calculators with editable factors, integrity audits. No Revit code check found (UNVERIFIED).
- **UpCodes, Archistar, CivCheck, Blitz** [75][77][78][79][80]: code Q&A and municipal review with human approval. UpCodes' 93% is internally inconsistent.
- **CORENET X** [82]: staged self-check, no accuracy published. **CEC calculators** [83]: single-item with "simplified values" caveats.
- **pigtail** [84]: MIT, NEC 2023, YAML, warn-only, cites sections, reports "not checked", 2 commits. Closest design model.

### 3.5 Open-source models

Rule for all: deterministic DXF or vector-PDF parsing first, models only on gaps. Every model-derived cell is tagged `source=ocr|vlm` with confidence `low`, promoted only by agreement between two independent readers or a hard validator (breaker sizes, phase balance, circuit numbering). No model below has been run on Redline data. All are UNVERIFIED on drawings.

**Vision-language models**

*Qwen3-VL* (primary VLM) [63][103][105][104]
- How: dense 2B, 4B, 8B, 32B and MoE 30B-A3B and 235B-A22B, Instruct and Thinking. Runs on vLLM (0.11.0 or later), SGLang, Transformers, Ollama 0.12.7 or later, and llama.cpp with a GGUF plus separate `mmproj` file [63][103][105].
- Pros: Apache-2.0, native Windows path via Ollama. Ollama downloads: 2B 1.9 GB, 4B 3.3 GB, 8B 6.2 GB, 32B 21 GB, with 256K context [103]. Cons: VRAM sources disagree for 8B Q4: about 6 GB weights only, 8 GB minimum, 12-16 GB comfortable (SECONDARY). Plan 12 GB or more for dense crops [104]. JSON-schema output together with image input is UNVERIFIED, test early.
- Accuracy: 53.3 (8B) and 58.7 (32B) on DrawingVQA [47]. Even the 235B trails 0.9B specialists on OmniDocBench parsing (as reported by [108]). Blog figures such as DocVQA about 96 are SECONDARY and unreliable [104]. Cost $0. Licence Apache-2.0. Effort 2-4 days. Local.

*Other generalists* [107][117][118][119]: Qwen2.5-VL is Apache-2.0 for most sizes, with 3B and 72B exceptions UNVERIFIED. InternVL3 and 3.5 licences conflict (MIT or Apache-2.0). MiniCPM-V 4.5 is Apache-2.0, older versions custom. GLM-4.6V is MIT in search, 4.5V unconfirmed. Gemma 3 and Llama 3.2 Vision carry custom licences (see section 2). Pixtral 12B (Apache-2.0) and Florence-2 (MIT) are from memory, UNVERIFIED. Secondary candidates only.

**Document-specialist VLMs and OCR or layout engines**

*PaddleOCR-VL 1.6* [108][110]: 0.9B, Apache-2.0. OmniDocBench table TEDS 94.76 on the leaderboard and 92.76 for v1.5, self-reported by PaddlePaddle. NVIDIA GPU with vLLM for full pages. Intel CPU supported per README, and the PP-OCR toolkit runs on Windows. Local, $0.

*MinerU2.5 and 2.5-Pro* [111][109]: 1.2B, Apache-2.0 weights, toolkit licence has extra conditions (SECONDARY thresholds). TEDS 88.22 (v1.5), 93.42 (Pro). ONNX CPU path needs about 2 GB RAM, `full` mode with vLLM needs 16 GB RAM and 8 GB or more VRAM. Windows supported.

*Others* [112][113][109]: dots.ocr (3B, MIT plus a separate agreement of unclear scope, TEDS 86.78, complex tables hard, vLLM and Linux-leaning). DeepSeek-OCR (about 3B, MIT, TEDS 84.97, Linux-first). olmOCR (7B, TEDS 68.92, card narrows use to research and education, SECONDARY, 12 GB or more GPU). Skip these three.

*PaddleOCR PP-OCRv5 and PP-StructureV3* [110]: Apache-2.0. PP-StructureV3 returns Markdown or JSON with table cell and text coordinates. CPU and Windows work. Per-word confidence and 90-degree angle handling are UNVERIFIED (README silent).

*RapidOCR* [115]: ONNX of PaddleOCR models, Apache-2.0, no table model, lightest install, CPU and Windows. *docTR* [116]: Apache-2.0, `assume_straight_pages=False` returns rotated boxes, confidence UNVERIFIED. *Docling* [114]: MIT code, per-model licences vary, TableFormer for tables, Windows ok. The Surya plugin has different terms (UNVERIFIED). Earlier blogs rated it a poor fit for 36x24 in sheets (inference) [39][41]. Use it as the CPU-tier structure option and test it. *Surya and Marker* [62]: see licence gotchas. *Tesseract and EasyOCR*: section 3.3.

For CAD, exact text with coordinates already exists in DXF and vector PDF. OCR matters for scans only. Handle rotated text by detecting orientation per region, rotating the crop, then recognising. Test each engine on a vertical-text crop.

**Symbol detectors** [120][60][121][122][123]

| Detector | Licence | Note |
|---|---|---|
| RF-DETR N/S/M/L | Apache-2.0 | COCO AP50:95 48.4, 53.0, 54.7, 56.5 (T4, TensorRT). `pip install rfdetr`, no Windows guidance |
| D-FINE, DEIM, RT-DETRv2 | Apache-2.0 (SECONDARY) | COCO AP 55.8 to 57.8 for the X sizes |
| YOLOX | Apache-2.0 (SECONDARY) | Old but proven |
| Ultralytics YOLOv8/11 | AGPL-3.0 or paid | Excluded |
| YOLO-NAS | Non-commercial weights | Excluded |
| Grounding DINO, OWLv2 | Apache-2.0 (UNVERIFIED) | Zero-shot. Pre-labeling only |

- Pros: Apache detectors are free and local. Cons: no source benchmarks any DETR-family model on electrical symbols. The claim from COCO to line-art is inference. Open-vocabulary detectors are trained on photos and are expected to fail on thin glyphs, so they only pre-label for human review [122]. Detectron2, MMDetection, PaddleDetection are heavier with painful Windows installs (UNVERIFIED).
- Accuracy: only SkeySpot is measured. YOLOv8 got 81.12 mAP50 and 48.24 mAP50-95 on 13 UK plans, Faster R-CNN 48.62 and 26.13 [59]. AECV-Bench symbol counting 0.40-0.55 shows VLMs are not a substitute [126]. Cost $0 plus labeling. Effort about 1-2 weeks for 10 classes (est., from Part 1). Local.

**Datasets and labeling** [59][123][124][125]: SkeySpot has 45 UK plans and 34 classes, licence not stated in the paper, check the repo. FloorPlanCAD is CC BY-NC, benchmarking only. CubiCasa5K is UNVERIFIED (believed CC BY-NC). Digitize-PID (500 synthetic P&IDs) and Roboflow Universe P&ID sets are toy scale. Self-host Label Studio or CVAT because client drawings are confidential (licences from general knowledge, UNVERIFIED). Confirm Roboflow free-tier terms before uploading anything.

**Serving and hardware tiers** [103][111][129]

- Ollama: native Windows, easiest, for dev and a single user. llama.cpp or LM Studio: GGUF plus mmproj, grammar control. LM Studio mmproj handling UNVERIFIED. vLLM: no official Windows support, so WSL2 or Docker. Community Windows forks exist (SECONDARY, self-reported 64.5 tok/s on an RTX 3090). Avoid them in a product [129]. Transformers works on Windows and is slowest.
- Per-page speed: no credible timings found, UNVERIFIED. Rules of thumb: a few seconds per crop on a 12-16 GB GPU for 4-8B models, tens of seconds to minutes on CPU for a 4B VLM. Measure on the owner's machine.
- CPU tier: RapidOCR or MinerU ONNX, Docling TableFormer, Qwen3-VL-4B Q4 on flagged cells only (2B fallback), RF-DETR Nano or Small. Slow, no detector training.
- Consumer GPU tier (12-24 GB): Qwen3-VL-8B Q4 or PaddleOCR-VL 1.6, PaddleOCR PP-OCRv5 plus PP-StructureV3, RF-DETR Medium (D-FINE-M or DEIM fallback).
- Workstation tier (24-48 GB or more): Qwen3-VL-32B Q4 (21 GB), MinerU2.5-Pro or PaddleOCR-VL on vLLM via WSL2 or Docker, two OCR engines for agreement, RF-DETR Large (D-FINE-L fallback).
- Grounding DINO pre-labels on the two GPU tiers only.

## 4. Master comparison table

Reliability is for CAD schedules. Effort is solo developer. n/f means not found. Verdicts: Primary, Fallback, Deferred, Excluded.

| Option | Topic | Local/Cloud | Cost | Licence | Effort | Reliability | Verdict |
|---|---|---|---|---|---|---|---|
| Core Console + .NET plugin [85][86] | DWG | Local | $0 extra with seat | Autodesk (seat use UNVERIFIED) | 5-8 d | Highest expected, unmeasured | Primary |
| ODAFC + ezdxf [1][3] | DWG/DXF | Local | $0 | MIT + freeware (UNVERIFIED terms) | 1-3 d | Good on text, risk on tables/fields | Fallback |
| COM automation (pyautocad, cad-pyrx) [92][93] | DWG | Local (GUI) | Seat | LGPLv3 / stale | 2-3 d | High, hangs on dialogs | Deferred |
| BricsCAD plugin [99][100] | DWG | Local | $300-600/yr | Commercial | 8-12 d | Unknown | Deferred |
| LibreDWG [6] | DWG/DXF | Local | $0 | GPL-3 | 1-2 d | Medium, skips objects | Deferred |
| APS Model Derivative [7] | DWG/DXF | Cloud | Credits | Autodesk | 2-3 d | Unproven for 2D | Excluded |
| APS Design Automation [8][9] | DWG/DXF | Cloud | Per processing time | Autodesk | 3-5 d | High (real AutoCAD) | Deferred |
| AutoCAD Electrical export [11][14] | DWG/DXF | Local (user) | Seat | Autodesk | Hours | High, schematics only | Primary (import) |
| DATAEXTRACTION/ATTOUT [18][19] | DWG/DXF | Local (seat) | Seat | n/a | 2-4 d | High, tables unproven | Fallback |
| ODA Drawings SDK [21][91] | DWG/DXF | Local | $3,000-7,500+/yr | Commercial | 7-10 d | High | Deferred |
| DWG TrueView [98] | DWG | Local | Free | Autodesk | n/f | Conversion only | Excluded |
| Open-source schedule parsers [22] | DWG/DXF | n/a | n/a | n/a | n/a | None exist | Excluded |
| pdfplumber [30][31] | PDF | Local | $0 | MIT | 1-2 d | Good with real text; 80-95% is a hypothesis | Primary |
| Custom geometry clustering | PDF | Local | $0 | n/a | 1-3 d | Best for templates (inference) | Primary |
| PyMuPDF [32][33] | PDF | Local | $0 or quote | AGPL / Artifex | 1-2 d | Similar to pdfplumber | Deferred |
| Camelot 2.0 [34] | PDF | Local | $0 | MIT | 0.5-1 d | None measured | Fallback |
| Tabula-py [35] | PDF | Local (Java) | $0 | MIT | 0.5 d | None measured | Excluded |
| pypdf, poppler, pdf2image [36][37][38] | PDF | Local | $0 | BSD / GPL (verify) / MIT | Hours | Not for tables | Fallback |
| Qwen3-VL 2B/4B/8B [63][103] | AI | Local | $0 | Apache-2.0 | 2-4 d | 53.3 (8B) DrawingVQA | Primary (second reader) |
| Qwen3-VL 32B [47][103] | AI | Local, 24 GB+ | $0 | Apache-2.0 | 2-4 d | 58.7 DrawingVQA | Primary (workstation) |
| PaddleOCR-VL 1.6 [108] | AI | Local | $0 | Apache-2.0 | n/f | TEDS 94.76, self-reported, not CAD | Fallback |
| MinerU2.5 [111][109] | AI | Local | $0 | Apache-2.0 + conditions (SECONDARY) | n/f | TEDS 88-93, not CAD | Fallback |
| PaddleOCR PP-OCRv5 [54][110] | AI | Local | $0 | Apache-2.0 | 2-4 d | Unverified on CAD | Primary (OCR) |
| RapidOCR [115] | AI | Local, CPU | $0 | Apache-2.0 | n/f | None published | Primary (CPU tier) |
| docTR [116] | AI | Local | $0 | Apache-2.0 | n/f | Weak on CAD per Tesseract analogue (inference) | Fallback |
| Docling [114][39] | AI | Local | $0 | MIT + per-model | 1-3 d | Poor fit for large sheets (inference) | Fallback (CPU tier) |
| PP-StructureV3 [110] | AI | Local | $0 | Apache-2.0 | n/f | Cell coordinates, unverified on CAD | Primary (GPU tier) |
| Tesseract [53] | AI | Local | $0 | Apache-2.0 | 1-2 d+ | Poor stock | Fallback |
| EasyOCR [55] | AI | Local | $0 | Apache-2.0 | n/a | No table model | Excluded |
| dots.ocr, DeepSeek-OCR, olmOCR [112][113][109] | AI | Local | $0 | MIT+agreement / MIT / Apache (narrowed) | n/f | TEDS 68.9-87.0 | Excluded |
| Surya / Marker [62] | AI | Local | $0 | OpenRAIL-M weights, $5M cap | n/f | Not retrieved | Excluded |
| RF-DETR N/S/M/L [120] | Symbols | Local | $0 + labeling | Apache-2.0 | 1-2 wk (est.) | COCO 48.4-56.5, none on symbols | Primary |
| D-FINE / DEIM [120] | Symbols | Local | $0 + labeling | Apache-2.0 (SECONDARY) | 1-2 wk (est.) | COCO 55.8-57.8, none on symbols | Fallback |
| YOLOX [120] | Symbols | Local | $0 + labeling | Apache-2.0 (SECONDARY) | n/f | None on symbols | Fallback |
| Ultralytics YOLO [59][60] | Symbols | Local | $0 or paid | AGPL-3.0 | 1-2 wk | 81.12 mAP50, UK test | Excluded |
| Grounding DINO [122] | Symbols | Local | $0 | Apache-2.0 (UNVERIFIED) | n/f | None on drawings | Deferred (pre-label only) |
| OWLv2 [122] | Symbols | Local | $0 | Apache-2.0 (UNVERIFIED) | n/f | None on drawings | Deferred (pre-label only) |
| Ollama [103] | Serving | Local | $0 | n/f in files | Hours | n/a | Primary (dev, single user) |
| vLLM [129] | Serving | Local (WSL2/Docker) | $0 | n/f in files | n/f | n/a | Fallback (batching) |
| Claude / Gemini / GPT vision [42][43][45][46] | AI | Cloud | Per token | Commercial | 1 d | Good cells, dense sheets unproven | Excluded |
| Azure DI / Textract / Google [56][57][58] | AI | Cloud | $1.5-50/1000 pp | Commercial | 2 d | Unverified on drawings | Excluded |
| Bluebeam Revu [66] | Product | Desktop | $260-590/user-yr | Commercial | n/a | No schedule extraction | Excluded |
| Togal/Kreo/CountFire [67][68][69] | Product | Cloud | Kreo $100-250/user-mo | Commercial | n/a | Floor-plan claims only | Excluded |
| Procore, ETAP, UpCodes, Archistar, CORENET X, CEC calculators [70][72][75][77][82][83] | Product | Mixed | Varies | Commercial | n/a | None check CEC schedules | Excluded |
| pigtail [84] | Product | Local | $0 | MIT | n/a | NEC, early | Primary (design pattern) |

## 5. Recommendation

Milestones M0 to M6. Effort figures are only those in the source files. Nothing here has been run on the owner's machine.

### M0. Foundation

- Define the `RawDrawing` JSON: layouts, blocks, attributes, tables as 2D string arrays, positioned text, xref list, and provenance (extractor name and version, AutoCAD version, source file hash, per-item handle, page or layer, bounding box, parse status) [3][85]. Rules never touch DXF, DWG or PDF directly.
- Build the rule engine skeleton: versioned editable code tables (CEC 2024, Ontario 2024, user overrides). Severities violation, needs-review, info, plus "not checked". Each finding cites rule, edition, inputs and computed values [83][84].
- Build: all of it. Nobody sells or publishes it [22][83]. Buy: nothing. Avoid: confidence percentages and "compliant" wording (see section 6).

### M1. CSV and XLSX import

- Import AutoCAD Electrical and DATAEXTRACTION exports with a header-mapping layer, text-only import, and HDL/DWGNAME kept for traceability. Ask the first customer for a real export of each report type to replace SAMPLE headings [12][14][18]. Optional parsers for `.wdp` and a copy of the `.mdb` [101][15].
- Build the mapper. Buy: nothing. Avoid: treating Electrical reports as panel schedules. They are not [15][16].

### M2. DWG and DXF

- Week-one checks on the owner's machine [85][94]: find `accoreconsole.exe`, run a `_QSAVE` smoke test on a plain and an Electrical DWG and time both, test with AutoCAD closed and open and check seat use, email the reseller about headless use, NETLOAD a 20-line C# command (try the [87] workaround if 2025+ crashes), dump a plain, FIELD and DATALINK table with the plugin and with `read_acad_table_content`, compare INSERT and ATTRIB counts against ODAFC, collect about 10 real drawings, and ask which AutoCAD versions and schedule styles the firm uses.
- Primary: the C# plugin under Core Console, with a Python wrapper that writes the `.scr`, runs the subprocess with a timeout, and validates the JSON. Check the JSON, not the exit code. Open with `/readonly` and log the file hash [85][86][88].
- Fallback: ODAFC plus ezdxf, same schema, `recover.readfile` on damaged files, xrefs converted separately, plus the loose-text row and column clusterer [1][90].
- Cross-check job: run both on the same file and diff table, INSERT and ATTRIB counts. This gives a measured data-loss rate for the fallback.
- Build: plugin, wrapper, clusterer. Buy: nothing now. Defer APS Design Automation and the ODA SDK until seat-less server ingest or hosted SaaS is needed. Sustaining ($7,500 first year) is the floor for SaaS [91]. Avoid: `ezdxf.xref` merging, COM for unattended ingest, `vla-*` LISP in the console, copy-local DLLs that Autodesk ships, and bundling ODAFC before its terms are confirmed [87][90][1]. Pin the AutoCAD version per extractor release.

### M3. PDF

- pdfplumber per page: chars versus paths, expected keywords (CKT, BKR, PANEL), header row, crop, cluster rows and columns on header x-positions, forward-fill merged cells, validate circuit numbers and VA sums [30][31]. Thresholds in the sources are guesses, so calibrate on 5-10 real sheets. SHX-as-paths or scanned pages emit "page not machine-readable" and hand over to M4 [24][25].
- Add `/Annots` reading for PDFSHX=1 files and cross-check against OCR (inference, test first) [28][36]. Camelot 2.0 as a second opinion [34]. PyMuPDF only after AGPL is resolved: buy an Artifex licence or use pypdfium2 [33][34].
- Build: clustering. Avoid: PyMuPDF before the licence is settled, Tabula-py, and trusting any table library on SHX pages. Tell users to plot with TrueType fonts [27].

### M4. Local AI

- Triggers: no text layer, too few chars, a panel header found but too few circuits or missing columns, validator failures, or a user forcing it.
- Build a 20-30 sheet gold set first, since no schedule benchmark exists [47][51]. Mix vector PDFs, flattened PDFs and scans at 150 and 300 DPI, with at least 3 vertical-text and 3 dense sheets. Match typed columns by normalized equality. Report cell accuracy by column, row recall, row hallucination rate, unreadable rate, structure score, time, and the share of wrong cells that carried high confidence. Run twice for variance. Pin model digests. Any unresolved disagreement on breaker size, wire or load surfaces as NEEDS MANUAL CHECK.
- Use the tier stack from section 3.5. Qwen3-VL as the second reader on crops, one table per call, with PP-OCRv5, RapidOCR or Tesseract as the independent first read. Prompt: transcribe exactly, return null and `unreadable: true` for unclear cells, never compute totals. Every model field is `source` vlm or ocr with `confidence: low`, promoted to `medium` only on agreement or a validator match. Never `high`. Test JSON-schema output with images first.
- Serve with Ollama for dev and a single user. Add llama.cpp for grammar control. Use vLLM via WSL2 or Docker only for batching.
- Buy: a GPU if the tier needs it. Avoid: model self-reported confidence as a gate, olmOCR, dots.ocr, DeepSeek-OCR, Surya and Marker, community Windows vLLM forks [44][62][129].

### M5. Symbol detection, fire alarm and egress

- For DXF, count blocks by name first, which needs no ML (inference) [3]. Use the plugin's JSON for this.
- For PDF and scans, train RF-DETR (N/S/M/L only) or D-FINE. Label 300-500 instances per class across 30 or more plans from 3 or more firms, split by plan and firm, tile at about 1024 px with 20% overlap, merge with NMS. Report mAP50, mAP50-95, precision and recall at the deployed threshold, and per-plan count error. SkeySpot's 81.12 and 48.24 are a UK reference only [59]. Pre-label with Grounding DINO if useful, then train supervised. Self-host CVAT or Label Studio.
- Scope: plan-versus-schedule cross-checks for fire alarm devices and exit signs, not a table fallback. Check the SkeySpot repo licence before using its data [123].
- Build: labels and models. Avoid: Ultralytics, RF-DETR XL/2XL/Atto-Pico, YOLO-NAS, FloorPlanCAD-derived weights, and VLM symbol counting (0.40-0.55) [126][124][121].

### M6. Hardening

- Pin and record every model, extractor and AutoCAD version in each report. Re-run gold sets when anything changes.
- Resolve the open licence items below before any distribution: ODAFC, Core Console seat use, MinerU, PyMuPDF, ODA tier. Get legal advice on LibreDWG and AGPL.
- Add revision diff and persistent reviewer disposition [66][71][73]. Output HTML or PDF plus CSV listing rules run, skipped and unparsed. Name the CEC edition in every report.
- Measure per-page speed on each hardware tier.

### Excluded by owner decision

Claude, GPT and Gemini vision, Azure Document Intelligence, AWS Textract, Google Document AI, and cloud takeoff or code-review products [42][45][56][57][58][67][75]. Reason: hosted, off-machine inference is not allowed. Cloud APS stays Deferred for a separate reason: it uploads client drawings and its Electrical support and residency are unverified [8].

## 6. Lessons from commercial products

1. Take structured input and skip drawing-AI accuracy claims. Market numbers are undefined [68][75].
2. Every finding cites rule, CEC edition, inputs and computed values [84].
3. Add a "not checked" status for rules lacking data. Procore cannot confirm a sheet was fully processed [70][84].
4. Three severities (violation, needs-review, info). No invented confidence percentages [84].
5. Link each finding to its source cell, row or page.
6. Persist reviewer disposition (accept, dismiss, comment) into the export, like Electrical Audit's "ignored" status and ACC triage [71][73].
7. Cover table-stakes checks: ampacity versus breaker, 125% continuous load, feeder and demand sizing, voltage drop, neutral and ground sizing, bus and breaker ratings [84].
8. Keep code tables as editable, versioned data with user overrides, like ETAP load factors [72][83].
9. Report rules run, skipped and unparsed. Scope narrowly, as Austin did with residential first [77][82].
10. Output HTML or PDF plus CSV. Accept clean vector PDF or CSV/Excel and warn on raster [66][70].
11. Provide revision diff between package versions [66][67].
12. Avoid "compliant" wording, an LLM as rule engine, power-system studies, and AHJ amendments before the base CEC works [84].

Suggested wording, from market practice [78][79][84]: "Pre-review screening that flags potential CEC gaps for a qualified reviewer. Not a design approval, stamp or compliance certificate." Name the edition and rules covered in every report.

## 7. Open questions to verify by hand

**DWG and DXF**
- Core Console seat consumption, server install under a named-user subscription, and the 2025 or 2026 install path: https://fdestech.com/resources/accoreconsole-guide-headless-cad-automation/ and https://forums.autodesk.com/t5/vba-forum/accoreconsole-exe-license-error/m-p/6849875 [86][94]. Ask Autodesk in writing.
- NETLOAD on AutoCAD 2025 and later (.NET 8, `System.Data.OleDb` crash and workaround): https://forums.autodesk.com/t5/autodesk-community-tips-adnopun/autocad-2025noaccoreconsole-exe-desystem-data/ta-p/13418763 [87]
- Which commands fail in Core Console, and `DATAEXTRACTION` availability: https://www.cadforum.cz/en/command.asp?Core= [95]
- Whether Core Console loads the Electrical object enabler, and proxy handling: https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-LT-MAC/files/GUID-E9E1FDCC-6724-4AD4-9BD7-D726F22158E9.htm [102]
- The .NET table member that returns evaluated FIELD text: https://developer.bricsys.com/bricscad/help/en_US/V25/DevRef/source/html/f2e21714-2c8f-af07-05b8-2944e42ea96c.htm [100]
- Electrical API function reference: https://aps.autodesk.com/developer/overview/autocad-electrical-api [89]
- `cad-pyrx` inside Core Console: https://pypi.org/project/cad-pyrx/ [92]
- ODA SDK tier pricing, Python wrapper price, 2026 price PDF: https://www.opendesign.com/oda-membership.md [91]
- ODAFC redistribution terms: https://www.opendesign.com [1][21]
- ezdxf Python minimum (3.10 or 3.11): https://pypi.org/project/ezdxf/
- FIELD-driven table cells, xref handling and Electrical proxy objects in ezdxf: https://ezdxf.readthedocs.io/en/stable/tasks/get_entity_content.html
- LibreDWG bindings on Windows: https://github.com/LibreDWG/libredwg
- Design Automation token rate, the 8 Dec 2025 change, about $1 per credit, residency: https://www.autodesk.com/ca-en/benefits/flex/flex-rate-sheet
- Model Derivative output for 2D attributes and tables: https://aps.autodesk.com/en/docs/model-derivative/v2/reference/http/urn-metadata-guid-properties-GET
- Does `DATAEXTRACTION` read tables: https://forums.autodesk.com/t5/autocad-forum/can-i-extract-data-from-a-table-using-the-data-extraction/m-p/14085686
- AutoCAD Electrical default headings, `.wdp` format, `WD.ENV` headless hooks, project database extension and columns: https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-8DF798D6-F71A-413E-AD1B-ABBE8A6ACB81.htm and https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-Electrical/files/GUID-FD3F36A0-01B7-44D2-8B73-81721934A6BD.htm [101]
- BricsCAD Lite headless mode and API limits: https://www.capterra.com/p/159378/BricsCAD/pricing/ [99]

**PDF**
- `PDFSHX` values and whether strings read as annotations or hidden text: https://www.cadforum.cz/en/variable.asp?cmd=PDFSHX
- PyMuPDF AGPL for internal use: https://pymupdf.readthedocs.io/en/latest/about.html (ask Artifex)
- pdfplumber 80-95%, tolerances, and text-layer thresholds (`n_chars < ~50`, `img_ratio > ~0.8`). Test on 5-10 real sheets. https://github.com/jsvine/pdfplumber
- OCG hidden-layer handling: https://pymupdf.readthedocs.io/en/latest/page.html
- poppler licence, pypdfium2 as permissive rasterizer: https://pypi.org/project/camelot-py/

**Local AI**
- MinerU licence conditions (100M MAU, $20M monthly revenue, SECONDARY): https://github.com/opendatalab/MinerU and https://www.docsumo.com/blog/best-ocr-models [111][109]
- Pixtral 12B licence (Apache-2.0 from memory): not retrieved, no URL in the source files
- Florence-2 licence (MIT from memory) and GD&T figures (secondary): https://arxiv.org/pdf/2411.03707 [49]
- Grounding DINO and OWLv2 licences (from memory): https://arxiv.org/pdf/2303.05499 and https://roboflow.com/compare/grounding-dino-vs-owlv2 [122]
- Label Studio, CVAT and Roboflow free-tier terms: not retrieved, no URL in the source files
- Per-page speeds on CPU and consumer GPU: none found, measure locally
- Qwen3-VL VRAM and JSON-schema output with images: https://github.com/QwenLM/Qwen3-VL and https://codersera.com/blog/qwen3-vl-4b-vs-qwen3-vl-8b-benchmarks-vram-guide/ [63][104]
- PaddleOCR rotation, angle classifier and confidence on CAD fonts: https://github.com/PaddlePaddle/PaddleOCR [110]
- InternVL, MiniCPM and GLM licences: https://github.com/opengvlab/internvl and https://huggingface.co/openbmb/MiniCPM-V-4_5 [117]
- Qwen2.5-VL 3B and 72B licence exceptions: https://arxiv.org/pdf/2502.13923 [107]
- dots.ocr agreement scope: https://github.com/rednote-hilab/dots.ocr [112]
- Docling Surya plugin terms: https://github.com/docling-project/docling [114]
- SkeySpot data licence and CubiCasa5K licence: https://github.com/HAIx-Lab/Skeyspot [123]
- Windows vLLM builds: https://github.com/aivrar/vllm-windows-build/wiki [129]

**Products**
- Togal $299 per user per month: https://www.togal.ai/
- Kreo "95%" and "$35/$70": https://www.kreo.net/pricing
- UpCodes study (unreadable PDF): https://marketing.up.codes/hubfs/Whitepapers/UpCodes-Copilot-Accuracy-Study.pdf
- CountFire price, ACC AutoSpecs, Revit overload warnings: https://www.countfire.com/product/takeoff-software and https://construction.autodesk.com/tools/clash-detection/

## 8. Sources

Accessed 2026-11-06. Some were read only as search summaries, as flagged. Numbers 1-84 are unchanged. Numbers 85-129 are new.

DWG/DXF
1. https://ezdxf.readthedocs.io/en/stable/addons/odafc.html
2. https://pypi.org/project/ezdxf/
3. https://ezdxf.readthedocs.io/en/stable/tasks/get_entity_content.html
4. https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-DXF/files/GUID-D8CCD2F0-18A3-42BB-A64D-539114A07DA0.htm
5. https://github.com/mozman/ezdxf/blob/master/src/ezdxf/entities/acad_table.py
6. https://github.com/LibreDWG/libredwg
7. https://aps.autodesk.com/en/docs/model-derivative/v2/reference/http/urn-metadata-guid-properties-GET
8. https://blog.autodesk.io/estimate-design-automation-costs/
9. https://aps.autodesk.com/pricing (search summary only); https://coderapp.vercel.app/answer/79448282
10. https://www.autodesk.com/ca-en/benefits/flex/flex-rate-sheet
11. https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-Electrical/files/GUID-4BAA248D-9507-48F2-AED3-5B6272D2D927.htm; https://autodesk.com/learn/ondemand/course/electrical-engineering-for-manufacturing/unit/17IdjUIMoBGHtsC15JSsuh
12. https://help.autodesk.com/cloudhelp/2017/ENU/AutoCAD-Electrical/files/GUID-7D6AD76C-FEC8-46DB-B610-64FC50C2F3B3.htm; https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-65DA310C-7B78-457F-A8E1-20CCCA1CD93C.htm
13. https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-Electrical/files/GUID-3A3BCEB5-C781-4E41-B0E5-C7B00F5EF7A2.htm
14. https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-5287AAF9-E530-4F2F-BE02-64BA5BEEACB4.htm; https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-Electrical/files/GUID-81DA5039-F987-43B7-8E10-BF4A68E42D1C.htm
15. https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-8DF798D6-F71A-413E-AD1B-ABBE8A6ACB81.htm
16. https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-MEP/files/GUID-5B68FCF5-0A15-418B-9EE6-F9B909FBE5EF.htm
17. https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-LT-MAC/files/GUID-5E118F6D-D19C-4B59-8E54-53016B4F8AB8.htm
18. https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Core/files/GUID-BA68DD22-A3CD-4538-90A9-6101C33BC963.htm
19. https://forums.autodesk.com/t5/community-blog-general-english/manage-autocad-block-attributes-in-excel-using-attout/ba-p/13299112
20. https://forums.autodesk.com/t5/autocad-forum/can-i-extract-data-from-a-table-using-the-data-extraction/m-p/14085686
21. https://www.opendesign.com/pricing.md; https://www.opendesign.com/files/2025-05/Open%20Design%20Alliance%202025.pdf
22. https://pypi.org/project/ezdwg/0.17.0/; https://awesome.ecosyste.ms/projects/github.com%2Fjparedesds%2Fextract-data-dxf
23. https://apify.com/bossless/dwg-dxf-extractor.md

PDF
24. https://support.bluebeam.com/articles/autocad-pdfs-dont-contain-searchable-text
25. https://forums.autodesk.com/t5/autocad-forum/searchable-pdfs-from-shx-fonts/td-p/6621435
26. https://help.aconex.com/handover/standardize-the-pdf-output-of-drawings/
27. https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-Electrical/files/GUID-3C7C25AD-43BE-4C09-A577-37EB2BF51D39.htm
28. https://help.autodesk.com/view/ACD/2024/ENU/?guid=GUID-56EA988C-A1DA-4E85-8765-B3F31A01AB02 (search summary); https://www.cadforum.cz/en/variable.asp?cmd=PDFSHX
29. https://forums.autodesk.com/t5/autocad-electrical-forum/pdf-s-are-jerky-and-contain-quot-autocad-shx-text-quot/td-p/6835299; https://kbpdfstudio.qoppa.com/pdf-created-by-autocad-shows-sticky-note-bubbles-on-document/
30. https://pypi.org/project/pdfplumber/
31. https://github.com/jsvine/pdfplumber
32. https://pymupdf.readthedocs.io/en/latest/page.html
33. https://pypi.org/project/PyMuPDF/; https://pymupdf.readthedocs.io/en/latest/about.html
34. https://pypi.org/project/camelot-py/; https://camelot-py.readthedocs.io/en/latest/user/comparison.html
35. https://pypi.org/project/tabula-py/
36. https://pypdf.readthedocs.io/en/stable/user/extract-text.html
37. https://manpages.debian.org/testing/poppler-utils/pdftotext.1.en.html
38. https://pypi.org/project/pdf2image/
39. https://www.ertas.ai/blog/pdf-parsing-accuracy-benchmark-docling-unstructured
40. https://arxiv.org/html/2410.09871v1
41. https://github.com/docling-project/docling/issues/2756 (also #2134, #1803, discussion #201); https://github.com/vamseeachanta/workspace-hub/issues/1447

AI, OCR, vision
42. https://platform.claude.com/docs/en/build-with-claude/vision
43. https://platform.claude.com/docs/en/about-claude/pricing
44. Claude API skill reference bundled with the tooling (cached 2026-10-06), no URL
45. https://dev.to/businessware/benchmark-how-well-ai-models-handle-table-processing-29kl
46. https://aistudio.google.com/docs/pricing
47. https://arxiv.org/html/2607.15418v1
48. https://github.com/opendatalab/OmniDocBench/tree/v1_5; https://arxiv.org/pdf/2510.14528
49. https://arxiv.org/pdf/2411.03707
50. https://aclanthology.org/2025.xllm-1.2
51. https://arxiv.org/html/2606.03410v1
52. https://dbia.org/blog/the-pre-con-sandbox-a-practical-guide-to-prompting-ai-for-design-build-drawing-reviews/
53. https://ir.lib.ncu.edu.tw/handle/987654321/92872
54. https://www.paddleocr.ai/latest/version3.x/installation.html
55. https://github.com/JaidedAI/EasyOCR
56. https://azure.microsoft.com/en-ca/pricing/details/ai-document-intelligence/; https://erpresearch.com/erp-add-ons/ocr/azure-document-intelligence/pricing
57. https://aws.amazon.com/textract/pricing/
58. https://cloud.google.com/document-ai/pricing
59. https://arxiv.org/html/2508.10449v1
60. https://github.com/ultralytics/ultralytics
61. https://arxiv.org/html/2408.09869v5; https://ibm.com/new/announcements/granite-docling-end-to-end-document-conversion
62. https://github.com/datalab-to/marker; https://github.com/datalab-to/surya
63. https://github.com/QwenLM/Qwen3-VL
64. https://arxiv.org/pdf/2604.12282; https://arxiv.org/pdf/2510.22087
65. https://nomic.ai/glossary/ai-for-schedule-drawings

Products
66. https://www.bluebeam.com/pricing
67. https://www.countfire.com/product/takeoff-software
68. https://www.togal.ai/
69. https://www.kreo.net/pricing
70. https://support.procore.com/faq/how-can-i-improve-the-accuracy-of-ocr-on-my-drawings
71. https://construction.autodesk.com/tools/clash-detection/
72. https://etap.com/product/panel-systems-software; https://www.easypower.com/products/features/mcc-and-panel-schedules
73. https://help.autodesk.com/view/ACAD_E/2024/ENU/?guid=GUID-28F7243A-59DB-4A53-BB83-9729E7F590E2; https://help.autodesk.com/view/ACAD_E/2023/ENU/?guid=GUID-7CA879C4-035D-4475-9BD9-2299F1A11F98
74. https://help.autodesk.com/cloudhelp/2025/ENU/Revit-MEPEng/files/GUID-9316D4CB-C244-4691-90B2-8D74A502445B.htm
75. https://cms-v2.up.codes/features/copilot; https://marketing.up.codes/hubfs/Whitepapers/UpCodes-Copilot-Accuracy-Study.pdf (unreadable)
76. https://runtimewire.com/article/upcodes-ai-plan-review-1300-plan-sets
77. https://www.smartcitiesdive.com/news/ai-building-permits-austin-honolulu-los-angeles/751159/; https://cities-today.com/?p=69557
78. https://spectrumlocalnews.com/us/snplus/news/2025/12/09/new-ai-software-tool--civcheck--comes-to-dpp
79. https://www.archistar.ai/aiprecheck/ai-plan-review/
80. https://blitzpermits.ai/product-code-compliance-review
81. https://www.teardown.ai/companies/permitflow; https://scoutcities.com/blog/ai-tools-simplifying-permitting-processes
82. https://info.corenet.gov.sg/overview/about-corenet-x/overview-of-corenet-x
83. https://offsetnotes.com/cec/ampacity-calculator
84. https://github.com/alexandreamat/pigtail; https://pypi.org/project/pigtail/

New: DWG full-project (from dwg_dxf.md Part 2, its sources 36-53)
85. https://www.cadforum.cz/cadforum_en/running-autocad-without-the-graphics-window-tip8552
86. https://fdestech.com/resources/accoreconsole-guide-headless-cad-automation/ (vendor blog; performance and licensing claims unsourced)
87. https://forums.autodesk.com/t5/autodesk-community-tips-adnopun/autocad-2025noaccoreconsole-exe-desystem-data/ta-p/13418763 (search summary, page returned 403)
88. https://forums.autodesk.com/t5/net-forum/netloading-dll-from-a-script-file-for-batch-processing/m-p/5947184 (search summary)
89. https://aps.autodesk.com/developer/overview/autocad-electrical-api
90. https://ezdxf.readthedocs.io/en/stable/xref.html
91. https://www.opendesign.com/oda-membership.md
92. https://pypi.org/project/cad-pyrx/
93. https://pypi.org/project/pyautocad/ (search summary)
94. https://forums.autodesk.com/t5/vba-forum/accoreconsole-exe-license-error/m-p/6849875 (search summary)
95. https://www.cadforum.cz/en/command.asp?Core= (search summary)
96. https://forums.autodesk.com/t5/visual-lisp-autolisp-and-general/plot-does-not-work-in-core-console-2021-accoreconsole-exe/td-p/10133791 (search summary)
97. https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Electrical/files/GUID-75AEBC13-2F09-4B9E-B349-C7B202D52119.htm
98. https://help.autodesk.com/cloudhelp/2023/ENU/DWGTrueView/files/GUID-E123319D-D1E2-43BE-94E2-CE39CF04F0C9.htm (search summary)
99. https://www.capterra.com/p/159378/BricsCAD/pricing/; https://novedge.com/collections/bricscad-september-savings-promo (search summary)
100. https://developer.bricsys.com/bricscad/help/en_US/V25/DevRef/source/html/f2e21714-2c8f-af07-05b8-2944e42ea96c.htm (search summary)
101. https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-Electrical/files/GUID-FD3F36A0-01B7-44D2-8B73-81721934A6BD.htm (search summary)
102. https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-LT-MAC/files/GUID-E9E1FDCC-6724-4AD4-9BD7-D726F22158E9.htm (search summary)

New: open-source models (from open_source_models.md)
103. https://ollama.com/library/qwen3-vl
104. https://codersera.com/blog/qwen3-vl-4b-vs-qwen3-vl-8b-benchmarks-vram-guide/ (SECONDARY)
105. https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md; https://toolnavs.com/en/article/662-qwen-annonce-qwen3-vl-est-d%C3%A9sormais-disponible-sur-llamacpp-avec-des-poids-gguf (SECONDARY)
107. https://arxiv.org/pdf/2502.13923
108. https://arxiv.org/html/2601.21957v1
109. https://www.docsumo.com/blog/best-ocr-models (SECONDARY)
110. https://github.com/PaddlePaddle/PaddleOCR
111. https://github.com/opendatalab/MinerU
112. https://github.com/rednote-hilab/dots.ocr
113. https://github.com/deepseek-ai/DeepSeek-OCR
114. https://github.com/docling-project/docling
115. https://github.com/RapidAI/RapidOCR
116. https://github.com/mindee/doctr
117. https://github.com/opengvlab/internvl; https://vdf.ai/blog/best-local-vision-models/; https://huggingface.co/openbmb/MiniCPM-V-4_5
118. https://ai.google.dev/gemma/terms; https://arxiv.org/pdf/2503.19786
119. https://developer.meta.com/ai/faq/; https://huggingface.co/blog/llama32
120. https://github.com/roboflow/rf-detr; https://blog.roboflow.com/rf-detr-vs-alternatives/; https://arxiv.org/pdf/2509.20787
121. https://forums.developer.nvidia.com/t/licensing-and-usage-terms-for-yolo-nas-model/326342
122. https://arxiv.org/pdf/2303.05499; https://roboflow.com/compare/grounding-dino-vs-owlv2; https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/open-vocabulary-detection-grounding-dino-florence-2-rtdetr-rfdetr (SECONDARY)
123. https://github.com/HAIx-Lab/Skeyspot
124. https://floorplancad.github.io
125. https://huggingface.co/datasets/SherifAhmed/digitize-pid-yolo; https://universe.roboflow.com/pid-yolo/p-id-nddv7/model/2
126. https://arxiv.org/abs/2601.04819; https://github.com/AECFoundry/AECV-Bench
127. https://arxiv.org/abs/2611.02433 (SECONDARY)
128. https://arxiv.org/pdf/2510.26865
129. https://github.com/aivrar/vllm-windows-build/wiki; https://fazm.ai/t/vllm-windows-support-2026 (SECONDARY)
