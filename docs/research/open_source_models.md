# Open-Source / Open-Weights Stack for Redline (local-only AI layer)

Access date for every URL below: 2026-11-06. Companion to `ai_vision.md`. Marker meanings: **VERIFIED** = read on the primary page this session; **SECONDARY** = blog, aggregator or search summary only; **UNVERIFIED** = from memory or inference, check before relying on it. Model names move fast (PaddleOCR-VL is already at 1.6, PP-OCRv6 exists), so re-check versions before building.

Headline: no open model has been shown reliable on electrical panel schedules, and the only direct evidence on drawings says open VLMs trail frontier cloud models. A local stack is feasible for Redline only as "OCR/table-structure engine plus VLM as second reader plus hard validators", never as a single-pass oracle.

## 1. Open-weights vision-language models

### 1.1 Qwen3-VL (primary VLM candidate)
- Code/weights: Apache-2.0 (VERIFIED). Dense 2B/4B/8B/32B, MoE 30B-A3B and 235B-A22B, each with Instruct and Thinking variants. 4B/8B released 2025-10-15, 2B/32B 2025-10-21, tech report 2025-11-27. Runs via vLLM (>=0.11.0), SGLang, Transformers. The repo gives no VRAM figures. https://github.com/QwenLM/Qwen3-VL
- Ollama: tags `qwen3-vl:2b` 1.9 GB, `4b` 3.3 GB, `8b` 6.2 GB, `32b` 21 GB; 256K context; needs Ollama >= 0.12.7 (VERIFIED). https://ollama.com/library/qwen3-vl
- llama.cpp: Qwen3-VL merged with official GGUF weights from 2B to 235B (SECONDARY); vision needs a GGUF plus a separate `mmproj` file, `llama-server -m model.gguf --mmproj file.gguf` (VERIFIED pattern in docs). https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md , https://toolnavs.com/en/article/662-qwen-annonce-qwen3-vl-est-d%C3%A9sormais-disponible-sur-llamacpp-avec-des-poids-gguf
- Benchmarks: the repo shows numbers only as images. Third-party blogs quote 8B Instruct DocVQA about 96, OCRBench about 896 (SECONDARY, unreliable): https://codersera.com/blog/qwen3-vl-4b-vs-qwen3-vl-8b-benchmarks-vram-guide/ . On OmniDocBench v1.5, the 235B model scores 89.15 overall / table TEDS 86.21 in the PaddleOCR-VL-1.5 paper (independently run), so even the biggest generalist trails 0.9B specialists on document parsing (VERIFIED as reported by that paper): https://arxiv.org/html/2601.21957v1
- VRAM, Q4 8B: sources disagree: about 6 GB weights only, 8 GB minimum, 12-16 GB comfortable once image tokens and KV cache are counted (SECONDARY): https://codersera.com/blog/qwen3-vl-4b-vs-qwen3-vl-8b-benchmarks-vram-guide/ . Plan 12 GB+ for dense-sheet crops.
- JSON: llama.cpp and Ollama support JSON-schema constrained output for text; I did not verify it works together with image input for Qwen3-VL (UNVERIFIED, test early). vLLM has guided decoding (general knowledge, UNVERIFIED for VLM path).

### 1.2 Other generalist VLMs
| Model | Code / weights licence | Notes | Status |
|---|---|---|---|
| Qwen2.5-VL (3B/7B/32B/72B) | Apache-2.0 for most sizes (3B/72B carry the Qwen licence; UNVERIFIED) | Older; OmniDocBench table TEDS 82.15 for 72B | tech report https://arxiv.org/pdf/2502.13923 |
| InternVL3 / 3.5 | Conflicting: repo says MIT, a 2026 guide says Apache-2.0 | Check model card per size. Unverified | https://github.com/opengvlab/internvl , https://vdf.ai/blog/best-local-vision-models/ |
| MiniCPM-V 4.5 | Apache-2.0 code and weights (card); older V2.6 used a custom MiniCPM licence | Small, phone-class VLM | https://huggingface.co/openbmb/MiniCPM-V-4_5 |
| GLM-4.5V / 4.1V / 4.6V | MIT for GLM-4.6V seen in search; 4.5V not confirmed | GLM-4.6V was in AECV-Bench | UNVERIFIED for 4.5V |
| Gemma 3 (4B/12B/27B) | Google Gemma Terms of Use, not Apache; commercial allowed with use restrictions | Tech report DocVQA 4B/12B 86.1/89.0 and ChartQA 79.8/83.5 in one table, other tables differ | https://ai.google.dev/gemma/terms , https://arxiv.org/pdf/2503.19786 |
| Llama 3.2 Vision (11B/90B) | Llama community licence; multimodal rights not granted to EU-domiciled entities | Redline is Canadian, so the EU clause is not binding, but the licence has an AUP, 700M MAU clause and naming rules | https://developer.meta.com/ai/faq/ , https://huggingface.co/blog/llama32 |
| Pixtral 12B | Apache-2.0 (from memory, UNVERIFIED) | Not retrieved | |
| Florence-2 | MIT (from memory, UNVERIFIED) | 0.23B/0.77B; OCR, captioning, grounding; fine-tunable. Fine-tuned for GD&T in https://arxiv.org/pdf/2411.03707 | |

### 1.3 Document-specialist VLMs (small, built for page/table transcription)
| Model | Size | Licence (code / weights) | OmniDocBench | Runs on | Source |
|---|---|---|---|---|---|
| PaddleOCR-VL-1.6 | 0.9B | Apache-2.0 | v1.6 overall 96.34, table TEDS 94.76 (leaderboard); v1.5 model: 94.50 / 92.76 | NVIDIA GPU with vLLM for full pages; also Intel CPU supported per README; Windows supported for PP-OCR toolkit | https://github.com/PaddlePaddle/PaddleOCR , https://arxiv.org/html/2601.21957v1 , https://www.docsumo.com/blog/best-ocr-models |
| MinerU2.5 / 2.5-Pro | 1.2B | Apache-2.0 weights; toolkit "MinerU Open Source License" = Apache-2.0 plus additional conditions (docsumo: commercial licence needed above 100M MAU or $20M monthly revenue, SECONDARY) | v1.5: 90.67 overall, TEDS 88.22; Pro 95.75 / 93.42 | ONNX CPU path (about 2 GB RAM basic tier), llama.cpp, vLLM; Windows supported | https://github.com/opendatalab/MinerU |
| dots.ocr / dots.mocr | 3B | MIT in sidebar plus a separate "dots.ocr LICENSE AGREEMENT" file (relationship unclear, read it) | v1.5 overall 88.41 (dots.ocr), table TEDS 86.78; authors note complex tables remain hard | vLLM recommended (integrated since 0.11.0), Transformers slower; no Windows guidance | https://github.com/rednote-hilab/dots.ocr |
| DeepSeek-OCR (and 2) | about 3B | MIT (DeepSeek-OCR repo VERIFIED); docsumo lists DeepSeek-OCR 2 as Apache-2.0 | v1.5: 87.01 / TEDS 84.97; Real5 (photographed pages) overall 73.99 | CUDA 11.8, flash-attn, vLLM; Linux-oriented, no Windows notes | https://github.com/deepseek-ai/DeepSeek-OCR |
| olmOCR / olmOCR 2 | 7B | Apache-2.0; card limits intended use to research/education (SECONDARY) | v1.5 overall 81.79, TEDS 68.92 | NVIDIA GPU >= 12 GB | https://www.docsumo.com/blog/best-ocr-models |
| Nanonets-OCR, GOT-OCR2 | n/a | Not retrieved (UNVERIFIED; both believed Apache-2.0) | not retrieved | | |

Caveat on all OmniDocBench numbers: they are printed documents (papers, reports, textbooks), not CAD sheets; versions v1.5/v1.6 differ; figures partly self-reported by PaddlePaddle; different pages give different values for the same model. Treat as ranking evidence for "can read a ruled table", not as expected Redline accuracy. Cross-check: https://github.com/opendatalab/OmniDocBench

### 1.4 Windows runtime summary
- **Ollama:** native Windows installer, easiest path, Qwen3-VL 2B-32B available (VERIFIED above). Good for prototyping and a single-user tool.
- **llama.cpp / LM Studio:** native Windows builds and GGUF + mmproj; LM Studio mmproj handling not verified (UNVERIFIED).
- **vLLM:** no official Windows support; WSL2 is the usual route; community native builds exist (aivrar, vLLM 0.19.0, single GPU, SystemPanic claims 0.20.0, unverified; self-reported 64.5 tok/s on RTX 3090). https://github.com/aivrar/vllm-windows-build/wiki , https://fazm.ai/t/vllm-windows-support-2026 (SECONDARY). Dots.ocr, DeepSeek-OCR and PaddleOCR-VL page-level mode all lean on vLLM, so for them expect WSL2 or Docker.
- **Transformers:** works on Windows with CUDA PyTorch; slowest per page.

## 2. Open-source OCR and layout engines

| Engine | Licence | Tables | Per-word/cell confidence | Rotated/vertical text | CPU / Windows | Source |
|---|---|---|---|---|---|---|
| PaddleOCR 3.x (PP-OCRv5; v6 now released: 1.5M/7.7M/34.5M tiers) | Apache-2.0 | PP-StructureV3 returns Markdown/JSON with table cell and text coordinates | Line-level rec scores exist in the API (general knowledge, README silent; UNVERIFIED) | Angle classifier exists (README silent; UNVERIFIED for 90-degree CAD text) | CPU yes, Windows yes, RTX 50-series on Windows supported | https://github.com/PaddlePaddle/PaddleOCR |
| RapidOCR (ONNX of PaddleOCR models) | Apache-2.0 (VERIFIED) | No table model | not documented on page | not documented | `pip install rapidocr onnxruntime`, CPU, Windows badge; lightest install | https://github.com/RapidAI/RapidOCR |
| docTR | Apache-2.0 (VERIFIED) | No | Word objects exist; page text did not state confidence (UNVERIFIED, I believe `Word.confidence` exists) | Option `assume_straight_pages=False` returns rotated boxes (VERIFIED) | PyTorch; CPU fine | https://github.com/mindee/doctr |
| Tesseract 5 | Apache-2.0 | No | per-word 0-100 | weak at 90-degree and text near linework; need OSD/rotation | Windows installer | see ai_vision.md |
| EasyOCR | Apache-2.0 | No | per-line confidence (general knowledge) | decent rotation support (UNVERIFIED) | torch | https://github.com/JaidedAI/EasyOCR |
| Surya / Marker | Code Apache-2.0; weights modified AI Pubs Open RAIL-M (free below $5M revenue/funding, research, personal) | Yes (layout, table rec) | line level | handles rotation (UNVERIFIED) | torch | https://github.com/datalab-to/surya |
| Docling (IBM) | MIT code; per-model licences vary ("refer to the model licenses") | TableFormer (not named on the page I read) | not stated | n/a | pip, Windows/macOS/Linux x86/arm; Granite-Docling VLM selectable | https://github.com/docling-project/docling |
| MinerU | see 1.3 | TableStructureRec credited | n/a | n/a | ONNX CPU, 2 GB RAM basic tier, Windows | https://github.com/opendatalab/MinerU |
| Unstructured | Apache-2.0 (general knowledge, UNVERIFIED) | via hi_res/Detectron | n/a | n/a | heavy deps | not retrieved |

Practical point for CAD: for DXF/vector PDF Redline already has exact text with coordinates; OCR only matters for scanned sheets. Rotated text should be handled by detecting orientation per text region, rotating the crop, then recognising; test each engine on a vertical-text crop in the gold set rather than trusting feature lists.

## 3. Symbol detectors

### 3.1 Trained detectors
| Detector | Code licence | Weights licence | Note |
|---|---|---|---|
| Ultralytics YOLOv8/11 | AGPL-3.0 or paid Enterprise licence | same as code; trained weights you produce are derivatives, so AGPL obligations (offer source to network users) attach to a distributed or hosted product | Redline gotcha: fine for internal use, a problem if sold as closed software. https://github.com/ultralytics/ultralytics |
| RF-DETR | Apache-2.0 for detection Nano/Small/Medium/Large and all Seg sizes; PML 1.0 for Atto/Femto/Pico/XL/2XL and NAS models (VERIFIED) | same | COCO AP50:95 on T4/TensorRT: Nano 48.4, Small 53.0, Medium 54.7, Large 56.5. Easy fine-tuning, DINOv2 backbone. https://github.com/roboflow/rf-detr |
| D-FINE, DEIM, DEIMv2, RT-DETRv2 | Apache-2.0 (SECONDARY) | Apache-2.0 | COCO AP: DEIMv2-X 57.8, DEIM-X 56.5, D-FINE-X 55.8, RT-DETRv2-X 54.3. https://arxiv.org/pdf/2509.20787 , https://blog.roboflow.com/rf-detr-vs-alternatives/ |
| YOLOX | Apache-2.0 (SECONDARY) | Apache-2.0 | Old but proven, MIT-friendly. |
| YOLO-NAS | Apache-2.0 super-gradients code | Deci licence: research/non-commercial only (VERIFIED in forum quote and HF licence copy); library unmaintained | Avoid. https://forums.developer.nvidia.com/t/licensing-and-usage-terms-for-yolo-nas-model/326342 |
| Detectron2 / MMDetection / PaddleDetection | Apache-2.0 (general knowledge, UNVERIFIED this session) | Model zoo weights vary | Heavier toolchains, Windows installs are painful. |

Windows install note: RF-DETR page says only `pip install rfdetr`, no Windows guidance (VERIFIED).

No source I found benchmarks any of these on electrical symbols except YOLOv8/Faster R-CNN in SkeySpot (below). DETR-family claims on line-art symbols are inference from COCO numbers. UNVERIFIED for drawings.

### 3.2 Zero-shot / open-vocabulary
- Grounding DINO: 52.5 AP COCO zero-shot, 26.1 mean AP on ODinW; one prompt per object class works better than combined prompts (SECONDARY). https://arxiv.org/pdf/2303.05499 , https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/open-vocabulary-detection-grounding-dino-florence-2-rtdetr-rfdetr
- OWLv2: weaker than Grounding DINO on COCO in one comparison (SECONDARY). https://roboflow.com/compare/grounding-dino-vs-owlv2
- Licences: Grounding DINO and OWLv2 Apache-2.0, Florence-2 MIT, all from memory (UNVERIFIED).
- **No study found evaluating any open-vocabulary detector on floor plans or electrical symbols.** Expect failure on thin line-art glyphs (e.g. a circle with an X) since pretraining is on photos. Use these only to pre-label candidates for human review, then train a supervised detector. Not a way to skip labeling.
- AECV-Bench: symbol-centric understanding (door/window counting) was weak for all models tested, often 0.40-0.55 accuracy (VERIFIED from abstract; open model names in the benchmark include Qwen3-VL 8B Instruct, GLM-4.6V, Nemotron Nano 12B V2 VL; per-model scores not read). https://arxiv.org/abs/2601.04819 , https://github.com/AECFoundry/AECV-Bench

### 3.3 Datasets and labeling tools
| Dataset | Content | Licence | Use for Redline |
|---|---|---|---|
| SkeySpot / DELP | 45 UK electrical layout plans, 34 classes (sockets, switches, consumer unit, smoke detector, etc.). YOLOv8 mAP50 81.12, mAP75 46.86, mAP50-95 48.24; Faster R-CNN 48.62/25.54/26.13 on 13-plan test, 5-fold mean | Not stated in paper; check repo https://github.com/HAIx-Lab/Skeyspot | Closest analogue; UK symbols, not CEC/Canadian. https://arxiv.org/html/2508.10449v1 |
| FloorPlanCAD | 15,000+ CAD floor plans (SVG), panoptic symbol spotting | CC BY-NC 4.0 on annotations; authors do not own drawing copyright | Non-commercial: research and benchmarking only. https://floorplancad.github.io |
| CubiCasa5K | Residential floor plans | not verified (UNVERIFIED; believed CC BY-NC) | Rooms/walls rather than electrical symbols |
| Digitize-PID | 500 synthetic P&IDs, YOLO format | check original (arXiv 2109.03794); HF copies are not by the author | Useful to test detector pipeline only. https://huggingface.co/datasets/SherifAhmed/digitize-pid-yolo |
| Roboflow Universe P&ID sets | tens to few hundred images, CC BY 4.0 on one | per project | Toy scale. https://universe.roboflow.com/pid-yolo/p-id-nddv7/model/2 |

Labeling tools (general knowledge, UNVERIFIED this session): Label Studio (Apache-2.0, self-host), CVAT (MIT, self-host), Roboflow free tier (public-workspace data on the free plan; confirm terms before uploading client drawings). Because project drawings are client-confidential, self-host Label Studio or CVAT.

## 4. Local serving and hardware

Assumptions: Windows 11, NVIDIA GPU. Numbers below are rules of thumb from the sources above, not measurements on Redline pages.

| Quantity | Value | Source |
|---|---|---|
| Qwen3-VL-8B Q4 GGUF download | 6.2 GB (Ollama) | VERIFIED |
| Qwen3-VL-4B / 2B / 32B | 3.3 / 1.9 / 21 GB | VERIFIED |
| 8B practical VRAM | 8 GB minimum, 12-16 GB comfortable | SECONDARY |
| MinerU basic ONNX | about 0.8 GB download, 2 GB RAM, CPU | VERIFIED |
| MinerU standard (ONNX + llama.cpp) | about 2 GB, 8 GB RAM, CPU works, Vulkan recommended | VERIFIED |
| MinerU `full` with vLLM | 16 GB RAM, 8 GB+ VRAM, Volta or newer | VERIFIED |
| olmOCR | >= 12 GB GPU | SECONDARY |
| dots.ocr via vLLM on A100-40G (DeepSeek-OCR figure) | about 2,500 tok/s DeepSeek-OCR | VERIFIED; not a Windows figure |

Speed per page: I found no credible per-page timings on consumer GPUs or CPUs. UNVERIFIED. Expect crop-level calls of a few seconds on a 12-16 GB GPU for 4-8B models and tens of seconds to minutes on CPU for a 4B VLM; measure on the owner's machine. The 0.9B PaddleOCR-VL and MinerU ONNX path are the realistic CPU-capable "VLM-like" options.

Server choice: Ollama (simplest, Windows-native) for dev and one-user tool; llama.cpp server when you want mmproj/grammar control; vLLM only via WSL2 or Docker when batching many pages; avoid community Windows vLLM forks in a product.

Tiering:
- **CPU tier:** ONNX OCR plus structure (RapidOCR or MinerU basic/ONNX, Docling TableFormer) plus Qwen3-VL-2B/4B Q4 only for flagged cells. Slow, no detector training.
- **Consumer GPU (12-24 GB):** Ollama/llama.cpp Qwen3-VL-8B Q4 or PaddleOCR-VL-1.6; RF-DETR Small/Medium for symbols.
- **Workstation (24-48 GB+):** Qwen3-VL-32B (21 GB Q4) or vLLM-served MinerU2.5/PaddleOCR-VL at batch; RF-DETR Large or D-FINE-L.

## 5. Evidence on drawings (open models specifically)

| Evidence | Finding | Strength |
|---|---|---|
| DrawingVQA (arXiv 2607.15418), 92 questions on 33 structural drawings | Qwen3-VL-32B 58.7, Qwen3-VL-8B 53.3, vs Gemini-3-pro 77.2, Gemini-2.5-Pro 71.7; humans 68.4 average | VERIFIED via ai_vision.md; small, QA not extraction. https://arxiv.org/html/2607.15418v1 |
| AECV-Bench (arXiv 2601.04819) | OCR and text-centric QA best (up to 0.95); spatial moderate; symbol counting often 0.40-0.55; open models in set: Qwen3-VL 8B, GLM-4.6V, Nemotron Nano 12B V2 VL | Abstract VERIFIED; per-model scores NOT read (PDF would not parse). Raster only, no DWG/vector. https://arxiv.org/abs/2601.04819 |
| Enginuity (arXiv 2606.03410) | Frontier VLMs find components (recall 0.61-0.87) but token F1 0.03-0.18 | from ai_vision.md; included Qwen3-VL |
| Blueprint2CAD (arXiv 2611.02433) | Six zero-shot VLMs 0.52-0.67 on drawing-to-render verification | SECONDARY. https://arxiv.org/abs/2611.02433 |
| GD&T extraction (arXiv 2411.03707) | fine-tuned Florence-2 vs GPT-4o / Claude 3.5 zero-shot | numbers unverified |
| MeasureBench (arXiv 2510.26865) | VLMs weak at reading instrument dials | tangential |
| P&ID digitization with Qwen-VL | Search returned nothing usable | gap |
| Dense electrical-schedule transcription with open VLMs | No published number found | gap; build own gold set |

Anecdotal/vendor items to ignore for decisions: Roboflow "RF-DETR vs alternatives" blog speed tables, aggregator blogs on VRAM, third-party leaderboards (Nanonets, benchmarklist) which disagree with the official one.

## 6. Licence summary

| Component | Code | Weights | Commercial OK? | Gotchas |
|---|---|---|---|---|
| Qwen3-VL | Apache-2.0 | Apache-2.0 | Yes | Verify the Qwen2.5-VL 3B/72B exceptions if used |
| PaddleOCR / PP-OCRv5 / PP-StructureV3 / PaddleOCR-VL | Apache-2.0 | Apache-2.0 | Yes | Fast-moving versions |
| RapidOCR | Apache-2.0 | derived from PaddleOCR (Apache-2.0) | Yes | check MODEL_LICENSES.md |
| docTR, Tesseract, EasyOCR | Apache-2.0 | Apache-2.0 | Yes | |
| Docling | MIT | Granite-Docling Apache-2.0; other models "see each package" | Yes | Docling's Surya plugin has different terms (UNVERIFIED) |
| MinerU | "MinerU Open Source License" (Apache-2.0 + conditions) | Apache-2.0 per docsumo | Yes below scale thresholds (SECONDARY) | Read LICENSE.md, thresholds reported as 100M MAU or $20M monthly revenue |
| Surya / Marker | Apache-2.0 | modified OpenRAIL-M | Free <$5M revenue/funding; otherwise paid | Startup threshold |
| dots.ocr | MIT | MIT plus a separate agreement file | Likely, read the agreement | unclear relationship |
| DeepSeek-OCR | MIT | MIT | Yes | Linux-first |
| olmOCR | Apache-2.0 | Apache-2.0, card narrows to research/education | Check | contradictory |
| Gemma 3 | Gemma Terms | Gemma Terms | Yes, with prohibited-use terms that flow down | Not OSI open source |
| Llama 3.2 Vision | Llama licence | Llama licence | Yes outside the EU entity restriction | Naming, AUP, 700M MAU |
| InternVL3.5 | MIT or Apache | verify card | Probably | sources conflict |
| MiniCPM-V 4.5 | Apache-2.0 | Apache-2.0 | Yes | older versions had custom licence |
| Ultralytics YOLO | AGPL-3.0 | AGPL-3.0 | Only if you comply with AGPL or buy Enterprise | Network-use clause |
| RF-DETR | Apache-2.0 (N/S/M/L, Seg) | same | Yes for those sizes | XL/2XL/small variants under PML 1.0, self-hosting commercial needs Enterprise add-on |
| D-FINE / DEIM / RT-DETRv2 / YOLOX | Apache-2.0 | Apache-2.0 | Yes | SECONDARY |
| YOLO-NAS | Apache-2.0 | Deci non-commercial | No | Avoid |
| Grounding DINO / OWLv2 / Florence-2 | Apache/Apache/MIT (UNVERIFIED) | same | Likely | verify |
| FloorPlanCAD | n/a | CC BY-NC 4.0 data | No | Research benchmark only |

## (a) Comparison across tools

| Tool | Role | Best evidence | Tables | Confidence | CPU feasible | Windows | Licence risk |
|---|---|---|---|---|---|---|---|
| Qwen3-VL 2/4/8/32B | VLM | DrawingVQA 8B 53.3, 32B 58.7 | via prompt | none (use agreement) | 2B-4B slow | Ollama native | Low |
| PaddleOCR-VL-1.6 | doc VLM | OmniDocBench TEDS 94.76 (self-reported) | strong | none | Intel CPU per README, slow | toolkit yes, vLLM path no | Low |
| MinerU2.5 | doc VLM + pipeline | TEDS 88-93 | strong | none | ONNX CPU | yes | Medium, read licence |
| dots.ocr | doc VLM | v1.5 TEDS 86.78 | complex tables hard | none | no | no guidance | Medium |
| DeepSeek-OCR | doc VLM | TEDS 84.97 | ok | none | no | Linux-first | Low |
| olmOCR | doc VLM | TEDS 68.92 | weak | none | no | no | Medium |
| PP-StructureV3 | layout/table | coordinates for cells | yes | rec score (UNVERIFIED) | yes | yes | Low |
| Docling | layout/table | TableFormer | yes | n/a | likely | yes | Low |
| RapidOCR | OCR | none published | no | n/a | yes | yes | Low |
| Tesseract / docTR / EasyOCR | OCR | weak on CAD (see ai_vision.md) | no | word conf | yes | yes | Low |
| Surya/Marker | OCR/layout | not retrieved | yes | line | no | yes | Weights licence |
| RF-DETR S/M/L | symbols | SkeySpot-like data not tested; COCO 53.0-56.5 | n/a | box score | slow | pip | Low |
| YOLOv8 (Ultralytics) | symbols | SkeySpot 81.12 mAP50, 48.24 mAP50-95 | n/a | box score | OK | pip | AGPL |
| D-FINE / DEIM | symbols | COCO 55.8-57.8 | n/a | box score | slow | pip | Low |
| Grounding DINO / OWLv2 | zero-shot | none on drawings | n/a | score | slow | pip | Low |

## (b) Recommended stack by tier

Rule for all tiers: deterministic DXF/vector-PDF parsing first, models only on gaps; every model-derived cell tagged `source=ocr|vlm` with confidence `low`, promoted only by agreement between two independent readers or a hard validator (breaker sizes, phase balance, circuit numbering).

| Role | CPU-only | Consumer GPU (12-24 GB) | Workstation GPU |
|---|---|---|---|
| Table transcription VLM | Primary: Qwen3-VL-4B Q4 via Ollama (flagged cells only). Fallback: Qwen3-VL-2B | Primary: Qwen3-VL-8B Q4. Fallback: PaddleOCR-VL-1.6 (table to Markdown/JSON) | Primary: Qwen3-VL-32B Q4 (21 GB) or Instruct at higher precision. Fallback: MinerU2.5-Pro or PaddleOCR-VL-1.6 on vLLM (WSL2/Docker) |
| OCR | Primary: RapidOCR (ONNX, Apache). Fallback: Tesseract 5 | Primary: PaddleOCR PP-OCRv5/v6 (GPU). Fallback: docTR with rotated boxes | Same as consumer; run two engines for agreement |
| Layout / table structure | Primary: Docling TableFormer. Fallback: MinerU ONNX basic | Primary: PP-StructureV3. Fallback: Docling | Primary: MinerU2.5-Pro. Fallback: PP-StructureV3 |
| Symbol detector | Primary: RF-DETR Nano/Small (CPU inference, Apache). Fallback: YOLOX-s | Primary: RF-DETR Medium. Fallback: D-FINE-M / DEIM | Primary: RF-DETR Large. Fallback: D-FINE-L |
| Zero-shot detector (pre-labeling only) | Fallback only: skip | Primary: Grounding DINO (Apache, verify). Fallback: OWLv2 | Same; Florence-2 grounding as fallback |

Notes: choose RF-DETR sizes that are Apache-2.0 (N/S/M/L); avoid XL/2XL/Atto-Pico. Avoid Ultralytics unless Redline is kept internal or an Enterprise licence is bought. Do not adopt YOLO-NAS or FloorPlanCAD-derived weights for commercial use. These are paper-and-licence picks; none has been run on Redline data (UNVERIFIED on drawings).

## (c) How to measure it before trusting it

**Gold set for table cells.**
1. Collect 20-30 real panel schedules/circuit tables (mix of DWG-derived vector PDFs, flattened vector PDFs and scans at 150 and 300 DPI, plus at least 3 with vertical text and 3 with dense small type). Have one person transcribe cell by cell into CSV; a second checks 20% to measure human disagreement.
2. Define a cell match: normalized string equality after trimming and unit normalization for the typed columns (circuit no., breaker A, poles, wire, load VA); fuzzy match (e.g. edit distance <= 1) reported separately for descriptions.
3. Report per model/config: cell accuracy by column type, row recall, row hallucination rate (rows emitted that do not exist), unreadable-flag rate, structure score (TEDS or row/column count match), time per table, and the fraction of wrong cells that carried high confidence (calibration). Slice by scan DPI, rotation and density.
4. Acceptance idea: set the bar on the safety-relevant columns (breaker size, wire, load). Any cell with an unresolved disagreement must surface as `NEEDS MANUAL CHECK`; track how many wrong values pass silently. Re-run each time a model or prompt changes (pin model digests).
5. Run twice per config to measure run-to-run variance (temperature 0, fixed seed where supported).

**Gold set for symbols.**
1. Label 300-500 instances per class across at least 30 plans from at least 3 different firms/styles (CVAT or Label Studio self-hosted). Split by plan and by firm, never by tile, so test plans are unseen.
2. Tile large sheets at training and inference (about 1024 px with 20% overlap) and merge with NMS.
3. Report mAP50 and mAP50-95 per class and overall, plus precision/recall at the deployed confidence threshold, and count error per plan (predicted vs true number of exit signs, pull stations, etc.), since Redline cares about counts. For reference, SkeySpot reports mAP50 81.12 / mAP50-95 48.24 on 13 unseen plans (https://arxiv.org/html/2508.10449v1); AECV-Bench shows VLM symbol counting at 0.40-0.55 (https://arxiv.org/abs/2601.04819).
4. For the zero-shot detector, run on the same test plans without training and report the same metrics; the expectation is poor, and the number justifies or kills its use as a pre-labeler.
5. Keep a running error log by symbol variant (firm legends differ); when a legend page is present, test whether legend-crop few-shot prompting helps a VLM verify detections.

## Sources (all accessed 2026-11-06)
- https://github.com/QwenLM/Qwen3-VL
- https://ollama.com/library/qwen3-vl
- https://codersera.com/blog/qwen3-vl-4b-vs-qwen3-vl-8b-benchmarks-vram-guide/
- https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md
- https://toolnavs.com/en/article/662-qwen-annonce-qwen3-vl-est-d%C3%A9sormais-disponible-sur-llamacpp-avec-des-poids-gguf
- https://arxiv.org/pdf/2502.13923 (Qwen2.5-VL)
- https://arxiv.org/html/2601.21957v1 (PaddleOCR-VL-1.5, OmniDocBench v1.5 table)
- https://www.docsumo.com/blog/best-ocr-models
- https://github.com/opendatalab/OmniDocBench
- https://github.com/PaddlePaddle/PaddleOCR
- https://github.com/opendatalab/MinerU
- https://github.com/rednote-hilab/dots.ocr
- https://github.com/deepseek-ai/DeepSeek-OCR
- https://github.com/docling-project/docling
- https://github.com/RapidAI/RapidOCR
- https://github.com/mindee/doctr
- https://github.com/datalab-to/surya
- https://github.com/opengvlab/internvl , https://vdf.ai/blog/best-local-vision-models/ , https://huggingface.co/openbmb/MiniCPM-V-4_5
- https://ai.google.dev/gemma/terms , https://arxiv.org/pdf/2503.19786
- https://developer.meta.com/ai/faq/ , https://huggingface.co/blog/llama32
- https://github.com/roboflow/rf-detr , https://blog.roboflow.com/rf-detr-vs-alternatives/ , https://arxiv.org/pdf/2509.20787
- https://github.com/ultralytics/ultralytics
- https://forums.developer.nvidia.com/t/licensing-and-usage-terms-for-yolo-nas-model/326342
- https://arxiv.org/pdf/2303.05499 , https://roboflow.com/compare/grounding-dino-vs-owlv2 , https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/open-vocabulary-detection-grounding-dino-florence-2-rtdetr-rfdetr
- https://arxiv.org/html/2508.10449v1 , https://github.com/HAIx-Lab/Skeyspot
- https://floorplancad.github.io
- https://huggingface.co/datasets/SherifAhmed/digitize-pid-yolo , https://universe.roboflow.com/pid-yolo/p-id-nddv7/model/2
- https://arxiv.org/abs/2601.04819 , https://github.com/AECFoundry/AECV-Bench
- https://arxiv.org/html/2607.15418v1 , https://arxiv.org/pdf/2606.03410 , https://arxiv.org/abs/2611.02433 , https://arxiv.org/pdf/2411.03707 , https://arxiv.org/pdf/2510.26865
- https://github.com/aivrar/vllm-windows-build/wiki , https://fazm.ai/t/vllm-windows-support-2026
