# Redline build plan

Status: plan only. No code yet. Revised 2026-11-06 from the research files in `docs/research/`. Redline is planned as a full end-to-end project delivered in milestones.

Reading rule for implementers: every CEC number, factor, table value and rule number in this plan is a placeholder marked `[VERIFY]`. The owner fills them from the code book. Never fill them from memory.

Marker rule: `UNVERIFIED` means the research could not confirm a claim from a primary source. Each such marker is kept where the claim is cited. Test it on the owner's machine before relying on it.

## 0. How this project is built

`DEV-PLAYBOOK.md` at the repository root is the authoritative process document. This section is its Redline-specific application. If the two disagree, the playbook wins and this section is updated.

### 0.1 The cycle

Every milestone runs the same seven stages. Each stage runs in a fresh session. Only files carry between stages: `PLAN.md`, `PROGRESS.md`, `docs/handoffs/`, `.unlazy/M<N>/` and `.claude/plans/`.

| Stage | Who | Command | Done when |
|---|---|---|---|
| 1 Prepare | Owner | None. Answer the milestone's `OWNER_DECISION` rows, branch `m<N>` | Owner says start |
| 2 Plan | ECC plan, architect, unlazy | `/ecc:plan "Milestone M<N> of PLAN.md: plan the work table into leaves with file ownership. Have the ecc:architect agent read the plan, then write it to .claude/plans/M<N>.md. No code."` then `/unlazy tree 3 write .unlazy/M<N>/PLAN.md and per leaf gates from the M<N> section and the plan, no code` | Ledgers lint, owner has read the contract and said go, no source file changed |
| 3 Build | Agent team, one worker per leaf, own worktree | `Use the ecc:team-agent-orchestration skill with an agent team of 4 workers, each in its own worktree: "Execute .unlazy/M<N>/PLAN.md. Claim a leaf, own only its OWNS globs, meet its gates, release."` | Every leaf verified, tests green |
| 4 Verify | unlazy | `/unlazy reverify every ledger under .unlazy/M<N>`, then for anything unmet `/unlazy "Close the unmet gates ... Do not stop until it is done."` | ALL MET, or every unmet gate has an `ABANDON:` reason the owner has read |
| 5 Review | `ecc:code-reviewer`, `ecc:security-reviewer`, `ecc:python-reviewer`, plus `ecc:csharp-reviewer` at M2 | Run over the diff against the base branch and against `CLAUDE.md`. Also `/security-review`. Findings become gates, then get fixed | Review ledger ALL MET |
| 6 Document | `ecc:doc-updater` | Write `docs/handoffs/M<N>.md` from the template, update `PROGRESS.md` and project docs | Every handoff claim points at a gate id or commit. PROGRESS names the next command |
| 7 Close | Owner | `/ecc:checkpoint create M<N>` | PR merged, tagged |

Stages 4 and 5 loop back into 3 for fixes, always in a fresh session with the ledger as the brief.

### 0.2 Model routing

- The lead model (Opus, or whatever the session runs) coordinates and integrates. It never writes code.
- Sonnet writes code and tests. Sonnet agents also do research and page reading, to save lead-model tokens. This is an owner instruction.
- Haiku does small exact edits and wording passes.
- Review passes (`ecc:code-reviewer`, `ecc:security-reviewer`) run on Opus in a different context from the writer.
- Set `model` on every Agent call. A coding agent never inherits Opus by default. Parallel agents work on disjoint files only.

### 0.3 Standing rules

1. Coding goes through ECC. Work directly only on trivial operations.
2. Plan first with `/ecc:plan`, then wait for the owner's go.
3. Verify an outcome by running it before claiming it.
4. The writer never approves its own change. A fresh `ecc:code-reviewer` run does.
5. A TODO, `test.skip`, `.only` or stub test means not done.
6. This project's `CLAUDE.md` wins over the global one.
7. No Claude attribution on any commit, PR or remote.
8. Input, file, subprocess and secret handling gets `/ecc:security-scan` and `ecc:security-reviewer`.
9. Gates are written before code. An unmeetable gate is abandoned with a reason, never deleted or reworded.
10. A new dependency needs a decision-log row. If thirty lines do the job, write them.
11. Never fill a CEC value from memory. The owner fills every table from the code book.
12. Every `[VERIFY]` placeholder blocks VIOLATION severity, not building. Rules downgrade to NEEDS_REVIEW until the table is verified.
13. No hosted model API and no vendor SDK for one, anywhere.
14. The C# plugin is the only non-Python code.

### 0.4 Session hygiene

- One workflow per session: plan, build, verify or review, never two.
- Start by reading `PROGRESS.md`, the last handoff, the milestone section of this plan and its ledger. State goal and acceptance, one sentence each, in `.claude/notepad.md`.
- Write decisions to `.claude/notepad.md` as they are taken.
- At about 60 percent context, run `/ecc:save-session` and close. Resume fresh with `/ecc:resume-session`.
- The owner is asked at stage 1 and stage 7 only. Anything else becomes an `OWNER_DECISION` row and the stage ends.

### 0.5 Team layout for build stages

- One worktree per worker, one branch per task. Three to five workers.
- The central files `model.py`, `config.py`, `engine.py`, `findings.py` and `rawdrawing.py` go to one worker. Others take parsers, rules, report, tests and docs.
- A worker that needs a file it does not own writes the request in its ledger and stops that leaf. It does not edit the file.

### 0.6 Git

- Branch `m<N>` per milestone.
- No Claude attribution in commit messages.
- No global git user is set. Commit with `git -c user.name="Zaid" -c user.email="zaid.zk467@gmail.com" commit ...`.
- `.gitignore`: `.claude/plans/`, `.claude/notepad.md`, `.claude/checkpoints.log`, `.unlazy/*/dispatch.json`, `gold/`, `.venv/`, model caches. Commit the rest of `.unlazy/`, since the ledgers are the evidence.

### 0.7 Files the cycle expects

`CLAUDE.md` (shape in playbook section 9), `PROGRESS.md` (one line per milestone, next command on top), `docs/handoffs/TEMPLATE.md` (five sections: what changed, what was done, what was decided, what was found, what is next) and `.unlazy/M<N>/PLAN.md` ledgers. The first three exist at the repository root and under `docs/handoffs/` as of 2026-11-06. Each ledger is created at stage 2 of its milestone.

## 1. Goal and positioning

Redline reads building electrical design packages and flags possible Canadian Electrical Code (CEC) gaps before a senior reviewer opens the package.

It is pre-review screening for a qualified reviewer. It is not a design approval, a stamp, or a compliance certificate. Every report names the code edition and the rules covered, and says which rules ran and which did not. Anything the tool cannot read reliably goes under "needs manual check". It never guesses.

### 1.1 Principles

1. **Full project.** Built end to end in milestones, each with scope, deliverables, acceptance criteria, a demo, an effort range and dependencies.
2. **One internal model.** Every input ends in one model: project, panels, circuits, feeders, devices. Rules never see the source format.
3. **Local only.** Every AI component is an open-source or open-weights model run on the owner's hardware. No drawing data leaves the machine. No hosted model API of any vendor is used, and no vendor SDK for one is a dependency. Weights download once, then everything runs offline.
4. **Deterministic first.** Exact text from DXF, DWG and vector PDF is read directly. Models run only on what that could not read.
5. **Config owns the code.** Code tables and limits live in editable YAML. The tool never supplies a CEC value.
6. **Honest confidence.** Every field carries a confidence level and a source. Rules compute only on reliable inputs.
7. **Simple and testable.** Python. One sample input per format. One test per rule.

### 1.2 Inputs, checks, output

Inputs: Excel and CSV panel schedules and circuit data (including AutoCAD Electrical exports); DWG and DXF; PDF, vector or scanned; AutoCAD Electrical `.wdp`, `.mdb`, `.accdb` as side inputs.

Checks (section 5): ampacity versus breaker with temperature and conductor-count corrections; continuous loads; voltage drop; bonding conductor size; phase balance; panel bus and main versus demand; missing descriptions or loads. Then fire alarm and egress (M5).

Output: an HTML or PDF report. Each issue shows the rule reference, the source (file, sheet or panel, circuit) and a suggested fix.

## 2. Repository layout

```
Redline/
  pyproject.toml              # Python 3.12, pytest; extras [dxf] [pdf] [ai] [detect]
  config/                     # cec_tables.yaml column_maps.yaml ai.yaml fire_alarm.yaml
  extractors/acad_plugin/     # C# .NET plugin, the only non-Python component (under 500 lines)
  src/redline/
    model.py units.py config.py findings.py engine.py cli.py rawdrawing.py
    extract/                  # acad_console.py (accoreconsole by subprocess), oda_ezdxf.py
    parsers/                  # csv_xlsx.py dxf.py aecad_side.py pdf.py pdf_ai.py
    ai/                       # serving.py ocr.py table_structure.py vlm.py detect.py
    rules/                    # ampacity continuous_load voltage_drop bonding phase_balance
                              # panel_demand completeness fire_alarm
    report/                   # html.py template.html.j2 csv_out.py pdf_out.py
  tools/                      # xcheck.py doctor.py gold_eval.py (also CLI subcommands)
  samples/                    # csv/ dwg/ pdf/ plans/ (synthetic or anonymized only)
  gold/                       # owner's gold sets, git-ignored
  tests/                      # one test file per parser and per rule; test_config/ (TEST ONLY); golden/
  docs/                       # PLAN.md research/ operator_guide.md
```

The C# plugin sits outside `src/` on purpose. The whole pipeline stays Python. The plugin is a thin dumper that writes JSON and holds no logic.

## 3. Data model

All in `model.py`, stdlib `dataclasses`, no pydantic. Units are fixed so rules never convert: volts (line-to-line for 3-phase, `_v`), amps (`_a`), VA (`_va`), metres (`_m`), degrees C (`_c`), conductor size as a canonical string (`_size`: `"12 AWG"`, `"2/0 AWG"`, `"250 kcmil"`, `"4 mm2"`). Parsers convert kVA to VA. kW converts only with a power factor from config, else it stays raw and is flagged.

### 3.1 Confidence, Source, Value

```
Confidence (ordered): HIGH     # structured source, exact alias, evaluated cell with exact header
                      MEDIUM   # heuristic mapping, cluster, or AI value promoted under policy 8.8
                      LOW      # OCR, VLM, detector, stale field cell, failed numeric parse
                      MISSING  # nothing found
Method: csv, xlsx, dxf_table, dxf_attrib, dxf_text, pdf_text, pdf_annot, ocr, vlm, detector, derived

Source(frozen):  file, locator, method, confidence, note = ""
                 # locator examples: "sheet=LP-1; row=14; col=Breaker"
                 #   "layout=E-101; handle=2F3A; r=5 c=3"   "page=4; bbox=..."
                 crop_path: str | None     # AI-derived values
                 model: str | None         # "qwen3-vl:8b@<version>#<hash>"
                 extractor: str | None     # "acad_plugin@<ver>" or "oda_ezdxf@<ver>"

Value[T](frozen): value: T | None, source: Source | None (None only when MISSING),
                  raw: str | None          # text exactly as read
                  .confidence, .usable (HIGH or MEDIUM, and value not None), Value.missing()
```

- Every extracted field is a `Value[...]`. Identity fields (panel name, circuit number) are plain strings, since a row without them goes to `unparsed`.
- Parsers always set `raw`. If parsing `raw` fails, value is `None`, confidence is LOW, and the note says why.
- `derived` values take the lowest confidence of their inputs.

### 3.2 Dataclasses (optional fields are `Value[...]` and may be MISSING)

```
Project:  name, code_edition, inputs, panels, feeders, devices,
          unparsed: list[Unparsed], coverage: list[CoverageEntry], run_info: RunInfo
Panel:    name (required), source, voltage_v, phases (1|3), wires, bus_rating_a,
          main_breaker_a (MLO = None + note), fed_from, location, demand_va_supplied, circuits
Circuit:  panel, number ("1", "7-9"), source   # required
          poles, phases_used ("A","AB","ABC"), breaker_a, conductor_size, conductor_material (Cu|Al),
          insulation_temp_c, conductors_in_raceway, ambient_c, length_m, load_va,
          load_type (continuous|noncontinuous|motor|receptacle|spare|unknown), description,
          bonding_size, voltage_v (falls back to panel), is_spare
Feeder:   id, source   # required
          from_panel, to_panel, ocpd_a, conductor_size, conductor_material, insulation_temp_c,
          sets_in_parallel, conductors_in_raceway, ambient_c, length_m, voltage_v, phases,
          bonding_size, load_va
Device:   type (exit_sign, pull_station, emergency_light, exit_door, ...), source   # required
          tag, location, sheet, circuit, x, y, detection ("block" | "detector" | "list")
Unparsed:      kind (column|row|table|page|sheet|xref|layout), raw, reason, source
CoverageEntry: file, unit, what_read, method, confidence_summary
RunInfo:       tool_version, config_hashes, extractor_versions, model_ids_versions_hashes, seeds
```

### 3.3 How `unparsed` works

A parser never drops data silently. An unmapped column, a row with no circuit number, an unclassified table region, a page with no text or an unresolved xref becomes one `Unparsed` item, listed under "Needs manual check" with file, locator and reason. A mapped cell that fails parsing (`"TBD"` in a load column) is kept as `Value(None, raw="TBD", LOW)` and reported by the completeness rule instead.

### 3.4 Conductor size normalizer

Accepts `#12`, `12AWG`, `2/0`, `#2/0`, `250 MCM`, `250kcmil`, `4mm2`, `4 mm²`. Returns the canonical string or `None` (the caller then sets LOW). `MCM` and `kcmil` share one form. No AWG to mm2 conversion.

## 4. Config files

Four files in `config/`, edited by the owner. `config.py` enforces:

1. Every table has `verified: false` and a `source:` string until the owner edits both.
2. Each rule declares `tables_used`. If any is unverified or holds `null`, VIOLATION findings downgrade to NEEDS_REVIEW and the report warns.
3. `null` at the exact key a calculation needs makes that unit NEEDS_REVIEW ("table entry missing").
4. `rule_ref` strings come from config. Python holds no rule numbers.
5. A config version and SHA-256 of every config file appear in the report footer.
6. A model in `ai.yaml` with an empty `weights_sha256`, or an RF-DETR size outside N, S, M, L, cannot be enabled.

### 4.1 `config/cec_tables.yaml` skeleton

Comments restating 80, 3 and 5 percent are the owner's requirements, to be entered and verified by the owner.

```yaml
config_version: "0.2-skeleton"
code_edition: "TODO: CEC <edition> plus provincial amendments"
code_edition_verified: false

defaults: { ambient_c: null, voltage_v: null, power_factor: null, conductor_material: null, termination_temp_c: null }

rule_refs:
  ampacity: "CEC <edition> Rule <fill> [VERIFY]"
  continuous_load: "CEC <edition> Rule <fill> [VERIFY]"
  voltage_drop: "CEC <edition> Rule <fill> [VERIFY]"
  bonding: "CEC <edition> Rule <fill> [VERIFY]"
  panel_demand: "CEC <edition> Rule <fill> [VERIFY]"
  phase_balance: "Project practice, not a CEC rule [VERIFY]"
  completeness: "Drawing standard, not a CEC rule"
  fire_alarm_exit_signs: "TODO [VERIFY]"
  fire_alarm_pull_stations: "TODO [VERIFY]"
  emergency_lighting: "TODO [VERIFY]"

tables:                       # every table: verified: false, source: "<fill from CEC book>"
  conductor_ampacity:         # material -> size -> insulation temp C -> amps
    verified: false
    source: "<fill from CEC book, Table N>"
    values: { copper: { "12 AWG": { "60": null, "75": null, "90": null } }, aluminum: { "12 AWG": { "60": null, "75": null, "90": null } } }
  ambient_temp_correction:    # insulation temp C -> [[ambient_upper_bound_c, factor], ...]
    verified: false
    source: "<fill>"
    values: { "75": [[null, null]], "90": [[null, null]] }
  conductor_count_correction: # [[max_conductor_count, factor], ...]
    verified: false
    source: "<fill>"
    values: [[null, null]]
  continuous_load:
    verified: false
    source: "<fill>"
    max_fraction_of_breaker: null    # owner requirement: 80 percent
  standard_breaker_ratings: { verified: false, source: "<fill>", values_a: [] }
  allow_next_standard_size: { verified: false, source: "<fill>", enabled: false }
  bonding_conductor_size:     # ascending by max_ocpd_a
    verified: false
    source: "<fill>"
    values: [{ max_ocpd_a: null, copper_size: null, aluminum_size: null }]
  conductor_size_order: { verified: false, source: "<fill>", values: [] }   # smallest to largest
  voltage_drop:
    verified: false
    source: "<project standard or CEC book>"
    method: "k_factor"               # or "impedance"
    branch_max_pct: null             # owner requirement: 3 percent
    feeder_max_pct: null             # owner requirement: 3 percent
    total_max_pct: null              # owner requirement: 5 percent
    current_basis: "load"            # or "breaker"
    show_passing: false
    k_factor: { constant_by_material: { copper: null, aluminum: null }, area_by_size: { "12 AWG": null }, length_unit_note: "TODO", phase_multiplier: { single: null, three: null } }
    impedance: { power_factor: null, phase_multiplier: { single: null, three: null }, per_size: { copper: { "12 AWG": { r: null, x: null } } } }
  demand_factors:
    verified: false
    source: "<fill>"
    default_method: "computed"       # or "user_supplied"
    supplied_vs_computed_tolerance_pct: null
    by_load_type: { continuous: [{ up_to_va: null, factor: null }], noncontinuous: [], receptacle: [], motor: [], unknown: [] }   # tiers; last up_to_va null = unbounded
    bus_loading_limit_fraction: null
    main_loading_limit_fraction: null
  phase_balance: { verified: false, source: "<project practice>", max_deviation_pct: null, min_circuits_to_check: null }
  phase_layout: { verified: false, source: "<project standard>", three_phase_pattern: [], single_phase_pattern: [] }

completeness: { require_description: true, require_load: true, require_breaker: true, require_conductor_size: true, spare_keywords: ["SPARE", "SPACE"], placeholder_texts: ["TBD", "-", "N/A"], severity: "NEEDS_REVIEW" }
```

### 4.2 `config/column_maps.yaml` skeleton

```yaml
config_version: "0.2-skeleton"
# Lower-case, strip punctuation. Exact alias = HIGH. Unique token-set match = MEDIUM. Else unparsed.

csv_panel_schedule:           # one circuit per row; owner adds aliases from real files
  panel_name:        ["panel", "panel name", "panel id", "pnl"]
  circuit_number:    ["ckt", "cct", "circuit", "circuit no", "circuit #"]
  poles:             ["poles", "pole", "p"]
  breaker_a:         ["breaker", "bkr", "trip", "amps", "ocpd"]
  conductor_size:    ["wire", "wire size", "conductor", "cable"]
  conductor_material: ["material", "cu/al"]
  insulation_temp_c: ["insulation", "temp rating", "wire temp"]
  length_m:          ["length", "run length", "distance"]
  load_va:           ["load", "load va", "connected load", "va"]
  load_kva:          ["kva", "load kva"]
  load_type:         ["load type", "type", "continuous"]
  description:       ["description", "load description", "served", "desc"]
  phase:             ["phase", "ph"]

panel_header_block:           # key/value lines above the table
  panel_name:     ["panel", "panel name", "designation"]
  voltage_v:      ["voltage", "volts", "supply"]
  phases:         ["phase", "phases", "ph"]
  bus_rating_a:   ["bus", "bus rating", "bus amps"]
  main_breaker_a: ["main", "main breaker", "main bkr", "mcb"]
  fed_from:       ["fed from", "supplied from", "source"]
  location:       ["location", "room"]

two_column_layout: { detect_when_headers_repeat: true, odd_circuits_on: "left" }   # TODO confirm per project
aecad_export: { headers: {}, verified: false, source: "<fill from a real export>" }   # empty: every column goes to unparsed
aecad_project: { wdp_verified: false, mdb_tables_verified: false, wd_m_attribute_map: {} }   # filled from real files in M2

parsing:                      # lengths relative to text height, never absolute units
  row_tolerance_text_heights: 0.6
  column_gap_fraction: 0.5
  min_header_alias_matches: 3
  dxf_table_min_cells: 4
  dxf_stale_field_policy: "low"        # cells with evaluated=false are LOW
  dxf_prefer_extractor: "acad_plugin"  # or "oda_ezdxf"
  dxf_extractor_timeout_s: 120         # placeholder until measured
  pdf_text_page_min_chars: 200         # below this: VECTOR_NO_TEXT or SCANNED (tune on real sheets)
  pdf_scanned_image_area_fraction: 0.8
  render_dpi: 250
  crop_long_edge_px: 2500
  tile_overlap_fraction: 0.10
```

### 4.3 `config/ai.yaml` skeleton

One file selects the hardware tier. A model registry holds each model's pinned version and weights hash. Each role names a primary and a fallback per tier. The owner fills versions and hashes with `redline models fetch`. A licence flagged `verified: false` stays that way until the owner reads the model card.

```yaml
ai_version: "0.1-skeleton"
enabled: false                      # off until the owner turns it on
tier: cpu                           # cpu | gpu | workstation
offline: true                       # network refused at runtime; downloads only via `redline models fetch`
model_cache_dir: "%LOCALAPPDATA%\\redline\\models"
seed: 0
temperature: 0.0
allow_promotion_to_medium: false    # policy 8.8

serving:
  ollama: { host: "http://127.0.0.1:11434", min_version: "0.12.7" }
  vllm:   { enabled: false, host: "http://127.0.0.1:8000" }   # optional, WSL2 or Docker only

models:                             # name -> pinned identity. Empty hash = cannot be enabled
  rapidocr-onnx:       { version: "<pin>", weights_sha256: "" }
  tesseract:           { version: "<pin>", weights_sha256: "" }
  paddleocr-ppocrv5:   { version: "<pin>", weights_sha256: "" }
  pp-structurev3:      { version: "<pin>", weights_sha256: "" }
  docling-tableformer: { version: "<pin>", weights_sha256: "" }      # code MIT, model licence to verify
  qwen3-vl:2b:         { version: "<digest>", weights_sha256: "", runtime: ollama, quant: Q4 }
  qwen3-vl:4b:         { version: "<digest>", weights_sha256: "", runtime: ollama, quant: Q4 }
  qwen3-vl:8b:         { version: "<digest>", weights_sha256: "", runtime: ollama, quant: Q4 }
  qwen3-vl:32b:        { version: "<digest>", weights_sha256: "", runtime: ollama, quant: Q4 }
  paddleocr-vl:        { version: "<pin>", weights_sha256: "" }
  rf-detr-small:       { version: "<pin>", weights_sha256: "" }      # also -nano, -medium, -large; N/S/M/L only
  d-fine-m:            { version: "<pin>", weights_sha256: "" }
  grounding-dino:      { version: "<pin>", weights_sha256: "" }      # licence to verify
  owlv2:               { version: "<pin>", weights_sha256: "" }      # licence to verify
# every entry also carries licence and verified: false until the owner reads the model card.
# Expected licences: Qwen3-VL, PaddleOCR family, RapidOCR, Tesseract: Apache-2.0. RF-DETR N/S/M/L: Apache-2.0.

roles:                              # [primary, fallback] per tier; tesseract is the last-resort OCR
  ocr:               { cpu: [rapidocr-onnx, tesseract], gpu: [paddleocr-ppocrv5, rapidocr-onnx], workstation: [paddleocr-ppocrv5, rapidocr-onnx] }
  table_structure:   { cpu: [docling-tableformer, pp-structurev3], gpu: [pp-structurev3, docling-tableformer], workstation: [pp-structurev3, docling-tableformer] }
  table_vlm:         { cpu: [qwen3-vl:4b, qwen3-vl:2b], gpu: [qwen3-vl:8b, paddleocr-vl], workstation: [qwen3-vl:32b, paddleocr-vl] }
  symbol_detector:   { cpu: [rf-detr-small, d-fine-m], gpu: [rf-detr-medium, d-fine-m], workstation: [rf-detr-large, d-fine-m] }   # YOLO excluded (AGPL)
  zero_shot_prelabel: { cpu: [], gpu: [grounding-dino, owlv2], workstation: [grounding-dino, owlv2] }   # gold-set pre-labeling only

detector_thresholds: { confidence_min: null, nms_iou: null }   # set from the gold set in M5
```

## 5. Rules

Shared contract. Signature `rule(project, config) -> list[Finding]`, registered in `engine.RULES` as `RuleSpec(id, name, fn, tables_used)`. `Finding(rule_id, severity, message, rule_ref, source, inputs_used, suggested_fix)`. Severity: `VIOLATION, NEEDS_REVIEW, INFO, NOT_CHECKED`. `inputs_used` lists each field with value and source locator. Input gate: if a required `Value` is not usable (LOW or MISSING), emit one NEEDS_REVIEW naming fields and locators, and compute nothing. A finding resting on an AI-promoted MEDIUM value says so and names the model. Every rule has trigger, pass, LOW-input and unverified-table tests.

| Rule | Inputs | Method | Gaps and severity | Fix text |
|---|---|---|---|---|
| **5.1 Ampacity** (`ampacity.py`) | breaker or feeder OCPD, conductor size, material, insulation temp, conductor count, ambient | Base ampacity by material, size and temperature column (lower of conductor and termination rating), times ambient factor, times conductor-count factor. Flag if corrected ampacity is below the breaker. Next-standard-size allowance is a config switch, off by default | Missing count or ambient is never "no correction": use config default or NEEDS_REVIEW. VIOLATION on failed comparison with HIGH or MEDIUM inputs and verified tables | "Increase conductor size, reduce breaker rating, or reduce conductors per raceway. Reviewer to confirm correction factors." |
| **5.2 Continuous load** (`continuous_load.py`) | breaker, load VA, load type, voltage, poles | Load current = VA / voltage (three-phase relation for 3-pole). A continuous load must not exceed breaker times the config fraction | `unknown` load type gives NEEDS_REVIEW ("continuous or not?"). VIOLATION when over | "Reduce load, increase breaker and conductor, or confirm the load is not continuous." |
| **5.3 Voltage drop** (`voltage_drop.py`) | length, size, material, current basis (load or breaker), voltage, phases; feeder chain via `fed_from` for the total | `k_factor`: material constant x current x length / area x phase multiplier. `impedance`: current x length x (R x power factor + X x sine of the angle) x phase multiplier. Percent of circuit voltage versus branch, feeder and total limits | Missing length gives NEEDS_REVIEW, never an assumed length. Total check needs every link usable, else NOT_CHECKED naming the broken link. VIOLATION over a limit. INFO for passing only if `show_passing` | "Increase conductor size or shorten the run. Reviewer to confirm length and load current." |
| **5.4 Bonding** (`bonding.py`) | bonding size, breaker or OCPD, material | First table row whose `max_ocpd_a` is at or above the rating. Drawn size must be at least the table size, compared with `conductor_size_order` | Often omitted: one grouped NEEDS_REVIEW per panel ("bonding conductor not shown"). VIOLATION when below | "Increase the bonding conductor to the table size, or show the size." |
| **5.5 Phase balance** (`phase_balance.py`) | 3-phase panels; per-circuit load, poles, phase (column = HIGH, or position via `phase_layout` = MEDIUM at best) | VA per phase, multi-pole split evenly. Max deviation from mean, in percent, versus `max_deviation_pct` | Any non-spare circuit without usable load or phase makes the panel NEEDS_REVIEW. Over threshold is NEEDS_REVIEW (project practice). INFO shows the per-phase table | "Move circuits from the heaviest phase to the lightest. Candidates: <list>." |
| **5.6 Panel demand** (`panel_demand.py`) | bus, main, circuits, load types, optional supplied demand | Demand source reported per panel: `user_supplied`, or `computed` through `demand_factors` tiers, else NEEDS_REVIEW. Both present and differing beyond tolerance: INFO with both. Demand current versus bus and main times config fractions | MLO checks the bus only and says so. Missing bus rating is NEEDS_REVIEW. VIOLATION over a limit with verified tables and non-LOW demand | "Increase bus and main, split the panel, or reduce connected load. Reviewer to confirm demand factors." |
| **5.7 Completeness** (`completeness.py`) | every non-spare circuit | Empty or placeholder description, empty or non-numeric load, empty breaker, empty conductor size. One finding per circuit listing the missing fields | Severity from `completeness.severity`, default NEEDS_REVIEW, never VIOLATION | "Add the load description and connected load, or mark the circuit SPARE." |
| **5.8 Fire alarm and egress** (`fire_alarm.py`) | devices, exits, paths (M5) | Section 6, M5. Until M5 lands: three NOT_CHECKED findings every run, asserted by a test | | |

Example message, placeholders only: `LP-1 ckt 7: 12 AWG Cu at 75 C, corrected ampacity <X> A is below 20 A breaker. CEC <edition> Rule <fill> [VERIFY].` Fixtures per rule: one trigger case and one pass case. Voltage drop adds a case where feeder and branch each pass alone but the total fails. Demand adds a supplied value that overrides computed and is named. Completeness uses a blank description, load text "TBD" with raw shown, and a SPARE with no load.

## 6. Milestones

One developer. Effort is a range in weeks. Every milestone ends with a working demo and a green test suite. The owner supplies real sample files at the start of each milestone. Real-file tuning is the main source of variance, and the ranges include it.

### M0. Foundation

**Scope.** Everything that does not depend on an input format.

**Deliverables.** Project skeleton with a venv outside the synced tree. `model.py`, `units.py`, `config.py` (verification gate, hashes) and the four skeleton YAML files. `findings.py` and `engine.py` with ran/skipped bookkeeping. All seven rules from 5.1 to 5.7 on a `Project` built in Python, with the TEST config, plus the fire alarm stub. Report: Jinja2 template with all sections, `findings.csv`, coverage table, "needs manual check" section, footer with hashes and the liability sentence, loud banner for a TEST config. `cli.py` with `redline check`. `rawdrawing.py` schema and validator, written early so the M2 plugin has a fixed target.

**Work table.**

| Leaf | Owns (globs) | Depends on | Gates (acceptance, one line each) |
|---|---|---|---|
| OWNER_DECISION | none | none | Owner confirms Python 3.12, venv path under `%LOCALAPPDATA%`, and the code edition label for the TEST config |
| L0.1 core | `src/redline/model.py`, `units.py`, `config.py`, `findings.py`, `engine.py`, `rawdrawing.py`, `config/*.yaml`, `tests/test_config/**`, `tests/test_units.py`, `tests/test_config.py`, `tests/test_rawdrawing.py` | none | `pytest tests/test_units.py tests/test_config.py tests/test_rawdrawing.py` green; `test_skeleton_downgrades_violation` and `test_hash_changes_with_file` pass; `test_empty_weights_hash_cannot_enable` passes |
| L0.2 rules-a | `rules/ampacity.py`, `continuous_load.py`, `voltage_drop.py`, `tests/test_rule_ampacity.py`, `test_rule_continuous_load.py`, `test_rule_voltage_drop.py` | L0.1 | Each of the three test files green with 4 cases (trigger, pass, LOW input, unverified table); voltage drop adds `test_total_fails_while_parts_pass` |
| L0.3 rules-b | `rules/bonding.py`, `phase_balance.py`, `panel_demand.py`, `completeness.py`, `fire_alarm.py`, matching `tests/test_rule_*.py` | L0.1 | Each test file green with 4 cases; `pytest tests/test_rule_fire_alarm.py` asserts 3 NOT_CHECKED findings every run; `test_supplied_demand_overrides_computed` passes |
| L0.4 report-cli | `report/**`, `cli.py`, `tests/test_report_golden.py`, `tests/golden/**` | L0.1, L0.2, L0.3 | `pytest tests/test_report_golden.py` green; the demo command in this section exits 0 and the HTML holds every section; TEST config banner present |
| L0.5 scaffold | `pyproject.toml`, `.gitignore`, `CLAUDE.md`, `PROGRESS.md`, `docs/handoffs/TEMPLATE.md`, `docs/operator_guide.md` | none | `pip install -e .` succeeds in the venv; `pytest -q` collects without error; `git check-ignore gold/ .venv/` lists both |

**Acceptance.** Every rule passes its four tests. The skeleton config loads and downgrades every VIOLATION. A hand-built project renders every report section. Config hashes change when a file changes.

**Demo.**
```
pytest -q
redline check --demo-project tests/golden/demo_project.json --config tests/test_config/ --out report.html
```

**Effort.** 2 to 3 weeks. **Dependencies.** None.

### M1. CSV and XLSX

**Scope.** Spreadsheet panel schedules and circuit data, including AutoCAD Electrical report exports. Libraries: stdlib `csv`, `openpyxl`, `pyyaml`, `jinja2`.

**Deliverables.** `parsers/csv_xlsx.py`:
- Multi-panel files split on a `panel` column. Sheet-per-panel workbooks: the header block names the panel, the sheet name is the MEDIUM fallback.
- Two-column (odd and even) layouts: detect repeated headers, split left and right, take circuit numbers from the number columns, never row order.
- Spare rows set `is_spare`. kVA converts to VA as `derived`.
- Alias mapping: exact alias HIGH, unique token-set match MEDIUM, else `unparsed` kind `column`. The circuit header is the first row with at least `min_header_alias_matches` matches.
- AutoCAD Electrical exports. Autodesk does not publish most headings, so the owner supplies real exports. Until then `aecad_export.headers` is empty and every column lands in `unparsed`. The first job with a real file is to build its alias map. Do not assume the format.
- Shared `rows_to_panel(headers, rows, source_factory)` reused by M2 and M3.

**Work table.**

| Leaf | Owns (globs) | Depends on | Gates (acceptance, one line each) |
|---|---|---|---|
| OWNER_DECISION | none | none | Owner supplies 2 to 3 real AutoCAD Electrical exports and says which column holds phase and load type. Answered 2026-11-07, row 33: Revit 2026 panel schedule exports stand in; findings in `docs/research/m1_exports.md` |
| L1.1 central | `src/redline/model.py`, `config.py`, `engine.py`, `cli.py` | none | `pytest tests/test_config.py` still green; `redline check samples/csv --config tests/test_config/` exits 0 after wiring directory input |
| L1.2 parser | `parsers/csv_xlsx.py`, `tests/test_parser_csv_xlsx.py` | L1.1 | `pytest tests/test_parser_csv_xlsx.py` green; `test_two_panels_counts` finds 2 panels with correct circuit counts; `test_odd_header_medium_or_unparsed` and `test_unknown_columns_never_dropped` pass |
| L1.3 aliases-samples | `config/column_maps.yaml`, `samples/csv/**`, `tests/golden/csv/**` | none | `python -c "import yaml; yaml.safe_load(open('config/column_maps.yaml'))"` exits 0; `samples/csv/two_panels.csv` has 2 panels and planted gaps; real-export alias map lists every unmapped column |
| L1.4 layouts | `tests/test_parser_two_column.py`, `samples/csv/two_column.csv` | L1.2 | `pytest tests/test_parser_two_column.py` green; circuit numbers come from number columns, asserted in `test_circuit_numbers_not_row_order` |
| L1.5 report | `tests/test_report_golden_csv.py` | L1.2, L1.3 | `pytest tests/test_report_golden_csv.py` green; `findings.csv` matches the golden file |

**Acceptance.**
- `samples/csv/two_panels.csv` (2 panels, about 20 circuits each, planted gaps) gives 2 panels with correct circuit counts.
- An odd header ("Wire Sz.") lands as MEDIUM or in `unparsed` with a reason. Unknown columns never vanish.
- The owner's real export parses through an owner-built alias map, with every unmapped column listed.

**Demo.**
```
redline check samples/csv --config config/ --out report.html
```

**Effort.** 2 to 3 weeks. **Dependencies.** M0. Real exports from the owner.

### M2. DWG and DXF

**Scope.** Read panel schedules, tables, blocks and attributes from DWG and DXF through one JSON contract, plus AutoCAD Electrical side inputs.

#### M2.1 Architecture decision

The best option from the research is chosen, not the cheapest. The primary extractor runs the real AutoCAD engine. It is the only local route that returns ACAD_TABLE cells, evaluated FIELDs, DATALINK tables, dynamic blocks, xrefs and AutoCAD Electrical attributes the way AutoCAD sees them. A fallback covers machines with no seat.

| Role | Component | Notes |
|---|---|---|
| Contract | `RawDrawing` JSON, versioned | Every extractor writes it. `parsers/dxf.py` reads only this. Rules never touch DXF or DWG |
| Primary | C# .NET plugin loaded with `NETLOAD`, driven by `accoreconsole.exe /i <dwg> /s <script>` from Python by subprocess | Highest fidelity, no extra cost with a seat, unattended by design subject to the licensing check |
| Fallback | ODA File Converter, then `ezdxf`, writing the same JSON | No seat needed. Medium fidelity: field cells may be stale |
| Side inputs | AutoCAD Electrical report exports, project `.mdb` or `.accdb`, `.wdp` | Tags, wire numbers, drawing lists. Not panel schedules |
| Measurement | `redline xcheck` | Both extractors on one file, diff counts |

The C# plugin is the one non-Python component. It is a thin dumper, well under 500 lines, in `extractors/acad_plugin/` with its own README. It reads database objects and writes JSON, with no business logic. Python builds the script, runs the subprocess with a per-file timeout, validates the JSON, and does all parsing and checking. The whole pipeline stays Python.

Plugin rules from the research. Reference only Autodesk assemblies plus `System.Text.Json`, and never copy locally anything AutoCAD ships (AutoCAD 2025 and later is .NET 8, and a plugin that brought its own `System.Data.OleDb` was reported to crash the console; UNVERIFIED). Build per AutoCAD major version; which versions the firm runs is UNVERIFIED. Use the managed API, since `vla-*` Visual LISP functions do not run in Core Console (UNVERIFIED). Open drawings `/readonly` and log the file hash, because fields and Excel links can refresh on open. Script quirks: forward slashes, an unquoted NETLOAD path, `FILEDIA` at 0. Check the output JSON, never the exit code.

#### M2.2 `RawDrawing` schema (flat, versioned)

```json
{
  "schema_version": "1.0",
  "extractor": "acad_plugin",
  "extractor_version": "0.1.0",
  "host_version": "AutoCAD <year> | ODA <ver> + ezdxf <ver>",
  "source_file": "E-101.dwg",
  "source_sha256": "<hash>",
  "extracted_at": "2026-11-06T12:00:00Z",
  "document": {
    "units": "mm",
    "layouts": ["Model", "E-101"],
    "xrefs": [{ "name": "A-BASE", "path": "..\\arch\\A-BASE.dwg", "resolved": true }],
    "warnings": []
  },
  "entities": [
    {
      "id": "e000123",
      "type": "TEXT | MTEXT | INSERT | ATTRIB | ACAD_TABLE | MLEADER | LINE | POLYLINE",
      "layout": "E-101",
      "layer": "E-PNL-TXT",
      "handle": "2F3A",
      "insertion_point": [1234.5, 678.9, 0.0],
      "rotation_deg": 0.0,
      "text_height": 2.5,
      "text": "plain text, formatting codes stripped",
      "block_name": "WD_M",
      "attributes": [{ "tag": "TAG1", "value": "LP-1" }],
      "table": { "rows": 24, "cols": 8, "cells": [{ "r": 0, "c": 0, "text": "CKT", "evaluated": true }] },
      "xref_path": null,
      "bbox": [1200.0, 650.0, 1300.0, 700.0]
    }
  ]
}
```

- **Flat.** One `entities` array. Layout, layer and block are fields, not nesting. Block definitions appear as entities whose `layout` is the block name prefixed `block:`. Fields that do not apply to a type are `null` or omitted.
- **`evaluated`.** `true` when the extractor read an evaluated value from the real engine. `false` for a cached string that may be stale or empty. The fallback sets `false` for any cell that carries a FIELD. `dxf_stale_field_policy` maps `false` to LOW.
- **Provenance.** `extractor`, `extractor_version`, `host_version`, `source_sha256` and per-entity `handle` are mandatory. They flow into `Source.locator` and the report.
- **Versioning and validation.** Major.minor. `rawdrawing.py` refuses a higher major, warns on a higher minor, and validates required fields, types and bbox before any parser runs. A failure becomes an `Unparsed` item kind `layout`, not a crash.

#### M2.3 Entry tasks: verify on the owner's machine in week 1

These come first. Nothing in the primary path is trusted until they pass. The owner records results in `docs/research/dwg_verification.md`.

1. **Find the exe.** Search `C:\Program Files\Autodesk` for `accoreconsole.exe`. Record the AutoCAD version and whether AutoCAD Electrical has its own folder. The 2025 and 2026 paths are UNVERIFIED.
2. **Smoke test.** A script containing `_QSAVE`, run as `accoreconsole.exe /i <sample.dwg> /s <t.scr> /l en-US`, on a plain and an Electrical DWG. Time it. Watch for licence dialogs.
3. **Core Console licensing.** Run with AutoCAD closed, then open. Check seat use in the Autodesk account. Ask the reseller in writing whether headless use on a shared machine is allowed. Sources disagree and Autodesk does not officially support the tool (UNVERIFIED). Until answered, run it only on the named user's own workstation.
4. **NETLOAD on 2025 and later.** A 20-line C# command built against `AcCoreMgd.dll` and `AcDbMgd.dll`, loaded with forward slashes. If it crashes on .NET 8, reference only AutoCAD's shipped assemblies (UNVERIFIED workaround).
5. **FIELD and DATALINK evaluation.** A DWG with a plain table, a FIELD table and a DATALINK table. Dump with the plugin and with `ezdxf` `read_acad_table_content`, and compare. The .NET member that returns evaluated field text is UNVERIFIED.
6. **ODA File Converter.** Check `odafc.is_installed()`. Compare INSERT and ATTRIB counts against the plugin. Redistribution terms are UNVERIFIED, so it is a user install, never bundled.
7. **Electrical project folder.** Look for `*.wdp`, `*.mdb` or `*.accdb`, `WD.ENV`. Open one drawing's `WD_M` attributes. List database tables and columns from a copy, never the live file. Also ask which AutoCAD versions staff run and how schedules are made (native table, Excel link, exploded text, Revit export), and gather about 10 real drawings.

Outcome rule: if step 3 or 4 fails, the fallback is the only extractor until resolved. The plan does not change, because the contract is identical.

#### M2.4 Deliverables

- `extractors/acad_plugin/`: `REDLINE_DUMP` command. Walks model space, every layout and block definitions. Emits TEXT, MTEXT (plain), INSERT with attributes and dynamic block properties, ACAD_TABLE cells, MLEADER, layer, handle, bbox, xref names and paths. Recurses into resolved xrefs. A build script per AutoCAD major version.
- `extract/acad_console.py` builds the `.scr`, runs the subprocess with the configured timeout and validates the JSON. `extract/oda_ezdxf.py` runs ODA File Converter, then `ezdxf` (`recover.readfile` for damaged files). Each xref is converted and read as its own document, then linked by block name, because `ezdxf.xref` silently ignores ACAD_TABLE and proxy entities.
- `parsers/dxf.py`, consuming `RawDrawing` only:
  1. Scan every layout and block. An unresolved xref becomes `unparsed` kind `xref` with its path.
  2. ACAD_TABLE cells to rows. Missing row and column counts put everything in row 1: mark the table LOW and send it to `unparsed`. Cells with `evaluated: false` are LOW.
  3. Anonymous `*T` blocks are table candidates built from their TEXT and MTEXT.
  4. Block attributes. `WD_M` attributes are read per `wd_m_attribute_map`.
  5. Loose-text clustering by y into rows (tolerance a fraction of median text height), header row by alias match, cells assigned by x-range. MEDIUM at best.
  6. Build the model with the shared `rows_to_panel`.
- `parsers/aecad_side.py`: `.wdp` text parser (confirm format on a real file), project database reader (`pyodbc` with the Microsoft Access ODBC driver, on a copy), report exports from M1. Column names are UNVERIFIED until read from a real file.
- `redline xcheck` (`tools/xcheck.py`): runs both extractors on one file and diffs entity, table, cell and attribute counts, plus per-cell table text. It prints what the fallback loses.
- `samples/dwg/`: synthetic fixtures with expected `RawDrawing` JSON, so parser tests need no CAD software.

#### M2.4a Work table

**Work table.**

| Leaf | Owns (globs) | Depends on | Gates (acceptance, one line each) |
|---|---|---|---|
| OWNER_DECISION | `docs/research/dwg_verification.md` | none | Owner records the Core Console licensing answer in writing, the AutoCAD versions in use, and about 10 real drawings; until then the plugin runs on the named user's workstation only |
| L2.1 plugin | `extractors/acad_plugin/**` | none | `dotnet build extractors/acad_plugin` succeeds per target version; `REDLINE_DUMP` on a fixture DWG writes JSON that `rawdrawing.py` validates; source under 500 lines (`wc -l`) |
| L2.2 extract | `src/redline/extract/**`, `tests/test_extract_acad_console.py`, `tests/test_extract_oda_ezdxf.py` | L2.5 | `pytest tests/test_extract_*.py` green or skipped with a stated reason when AutoCAD or ODA is missing; `test_timeout_becomes_unparsed` passes |
| L2.3 dxf-parser | `parsers/dxf.py`, `samples/dwg/**`, `tests/test_parser_dxf.py` | L2.5 | `pytest tests/test_parser_dxf.py` green; `test_native_table_matches_csv` is HIGH for exact headers; `test_no_row_count_is_low_unparsed` and `test_unevaluated_field_is_low` pass |
| L2.4 side-xcheck | `parsers/aecad_side.py`, `tools/xcheck.py`, `tests/test_aecad_side.py`, `tests/test_xcheck.py` | L2.2, L2.3 | `pytest tests/test_aecad_side.py tests/test_xcheck.py` green; `redline xcheck samples/dwg/panel_sheet.dwg` prints a per-file loss table |
| L2.5 central | `src/redline/rawdrawing.py`, `model.py`, `config.py`, `cli.py`, `config/column_maps.yaml` | none | `pytest tests/test_rawdrawing.py` green with a higher-major refusal case; footer prints extractor, version, host version and file hash (`test_footer_extractor_provenance`) |

#### M2.5 Acceptance

- A native ACAD_TABLE schedule gives the same `Panel` as the CSV equivalent, HIGH for exact headers. A table with no row count is LOW and in `unparsed`.
- A FIELD table: the plugin returns evaluated cells. The fallback returns the same cells with `evaluated: false` and LOW.
- `redline xcheck` on the corpus prints a per-file loss table, recorded in `docs/research/dwg_verification.md`.
- The report footer prints extractor name, version, host version and file hash. Extractor tests skip with a clear reason when AutoCAD or ODA is missing.

#### M2.6 Deferred options

- **APS Design Automation.** Highest fidelity, but client drawings would leave the building, which breaks the local-only principle, and Electrical support is UNVERIFIED. Revisit only for seat-less server ingest.
- **ODA Drawings SDK.** Paid per year, and the commercial tier does not permit web or SaaS use. Revisit for hosted or shipped use.

**Demo.**
```
redline check samples/dwg/panel_sheet.dwg samples/csv/ --config config/ --out report.html
redline xcheck samples/dwg/panel_sheet.dwg
```

**Effort.** 4 to 6 weeks. Plugin with per-version builds about 1.5 weeks (research estimate 5 to 8 days). Fallback and `parsers/dxf.py` about 2 weeks. Side inputs and xcheck about 1 week. Real-file tuning the rest. **Dependencies.** M1. An AutoCAD seat and about 10 real drawings.

### M3. PDF

**Scope.** Vector and scanned PDF, deterministic parsing only. Scanned and SHX pages are classified and routed for M4.

Library: `pdfplumber` (MIT). PyMuPDF only after the AGPL question is settled (section 10). All PDF access stays in `parsers/pdf.py`.

**Deliverables.**
1. **Per-page text-layer detection.** Count chars, vector paths, images. TEXT: many chars. VECTOR_NO_TEXT: few chars, many paths (likely SHX strokes). SCANNED: full-page image, no chars. Thresholds in `parsing:`.
2. **SHX annotation text.** `PDFSHX` can store SHX text as PDF comments or hidden text. Read `/Annots` `/Contents` as an extra source (`pdf_annot`), MEDIUM at best. Where annotation text and chars disagree, mark LOW. Behaviour across versions is UNVERIFIED.
3. **Title block** (bottom-right crop by default) for sheet number and revision.
4. **Table finding.** Cluster `words` by y and x with tolerances relative to median word height. Anchor on header keywords. Take rows until a blank gap, a second header or the region edge. Use drawn `lines` as a hint. Reuse `rows_to_panel`.
5. **Routing.** TEXT pages go to the table finder. VECTOR_NO_TEXT pages with annotations go to the annotation path. SCANNED pages, and VECTOR_NO_TEXT pages without annotations, become `unparsed` kind `page`: "scanned or SHX, needs OCR or vision". M4 consumes exactly these items.

**Work table.**

| Leaf | Owns (globs) | Depends on | Gates (acceptance, one line each) |
|---|---|---|---|
| OWNER_DECISION | none | none | Owner supplies 5 to 10 real sheets (one scanned) and says whether TrueType re-plots can be requested |
| L3.1 central | `src/redline/model.py`, `config.py`, `config/column_maps.yaml` (`parsing:` keys only) | none | `pytest tests/test_config.py` green with the new `pdf_*` keys; no hard-coded threshold in `parsers/pdf.py` (`grep -n "200" src/redline/parsers/pdf.py` finds none) |
| L3.2 pdf-parser | `parsers/pdf.py`, `tests/test_parser_pdf.py` | L3.1 | `pytest tests/test_parser_pdf.py` green; `test_vector_schedule_matches_csv_medium` and `test_shx_page_routed_not_parsed` pass; `test_scanned_page_unparsed_kind_page` passes |
| L3.3 samples | `samples/pdf/**`, `tests/golden/pdf/**` | none | Samples hold one text-layer PDF, one SHX-stroke PDF and one scanned PDF; `git grep -il "client" samples/pdf` finds nothing |
| L3.4 report-routing | `report/**`, `tests/test_report_pdf_routing.py` | L3.2 | `pytest tests/test_report_pdf_routing.py` green; routed pages appear under "Needs manual check" with the re-plot note |

**Acceptance.**
- A vector PDF with real text and a ruled schedule gives the same `Panel` as the CSV equivalent at MEDIUM. HIGH only for an exact header match plus a drawn grid.
- An SHX-stroke PDF gives zero panels and one `unparsed` page item with a "re-plot with TrueType substitution" note, until M4. A scanned page is routed, never parsed.
- Tuned on 5 to 10 real owner sheets.

**Demo.**
```
redline check samples/pdf --config config/ --out report.html
```

**Effort.** 3 to 4 weeks. **Dependencies.** M1. Real sheets.

### M4. Local AI: OCR, table structure, table VLM

**Scope.** Read the pages and table regions M3 could not, with open-weights models run locally. No network at run time, no hosted API.

Premise from the research: no open model has been shown reliable on electrical panel schedules, and the only direct drawing evidence says open VLMs trail frontier hosted models (DrawingVQA: Qwen3-VL-32B 58.7, 8B 53.3; small, and question answering rather than extraction). The design is OCR and table-structure engines, plus a VLM as second reader, plus hard validators. Never a single-pass oracle.

#### M4.1 Models by role (details in `config/ai.yaml`)

| Role | CPU tier | GPU tier | Workstation tier |
|---|---|---|---|
| OCR | RapidOCR (ONNX) | PaddleOCR PP-OCRv5 | PaddleOCR PP-OCRv5, may run two engines |
| Table structure | Docling TableFormer | PP-StructureV3 | PP-StructureV3 |
| Table VLM | Qwen3-VL-4B Q4 | Qwen3-VL-8B Q4 | Qwen3-VL-32B Q4 |

Fallbacks: RapidOCR for PaddleOCR, PP-StructureV3 and TableFormer for each other, Qwen3-VL-2B on the CPU tier and PaddleOCR-VL on the GPU and workstation tiers. Tesseract is the last-resort OCR on every tier, since the research finds it weak on CAD text, rotation and linework. MinerU2.5 is a gold-set candidate in M6, not in the stack, because its licence adds conditions (SECONDARY).

#### M4.2 Hardware needs by tier

Rules of thumb from the research, not measurements. Measure on the owner's machine in the first two weeks.

- **`cpu`** (no GPU). ONNX paths need about 2 GB RAM (VERIFIED for MinerU basic). The 4B VLM is a 3.3 GB download; its RAM need is UNVERIFIED, so plan 16 GB. Expect tens of seconds to minutes per crop (UNVERIFIED). VLM on flagged cells only.
- **`gpu`** (NVIDIA, 12 to 24 GB VRAM). The 8B Q4 model is a 6.2 GB download. 8 GB VRAM is the minimum and 12 to 16 GB is comfortable (SECONDARY). A few seconds per crop (UNVERIFIED).
- **`workstation`** (NVIDIA, 24 to 48 GB or more). The 32B Q4 model is a 21 GB download. vLLM only via WSL2 or Docker.

#### M4.3 Serving, cache, offline

- **Ollama on Windows** is the default VLM server (0.12.7 or later for Qwen3-VL), on localhost only. **vLLM is optional**, under WSL2 or Docker, for batch runs. Community Windows vLLM builds are not used.
- **JSON output.** Constrained JSON-schema output with image input is UNVERIFIED for Qwen3-VL. The first M4 task tests it. If it fails, `vlm.py` uses a plain JSON prompt, a strict parser and one retry. A parse failure leaves the cell LOW or MISSING.
- **Offline.** Weights download once with `redline models fetch`, the only command allowed network access. At run time `serving.py` refuses non-localhost hosts and sets the offline flags of the libraries it wraps.
- **Cache and pinning.** Weights live in `ai.model_cache_dir` (default `%LOCALAPPDATA%\redline\models`, outside OneDrive). `serving.py` checks each digest against `ai.yaml` and refuses a mismatch. Temperature 0, fixed seed where supported, pinned prompt versions. The report prints every model name, version and hash used.

#### M4.4 Pipeline (`parsers/pdf_ai.py`)

1. **Entry.** The `unparsed` page items from M3, plus table regions where validators failed (breaker not in standard ratings, circuit numbers with gaps or duplicates, VA column not summing to a printed total, too few circuits, required columns missing). `--ai-pages 4,7` forces pages.
2. **Render and crop.** Page at `render_dpi`. One table crop per call: bbox from the parser, else tiles with `tile_overlap_fraction` overlap, long edge at most `crop_long_edge_px`. Detect orientation per text region and rotate before recognising. Test rotated text on a vertical-text gold crop.
3. **Read one.** Table-structure model gives cell boxes. OCR fills the cells.
4. **Read two.** The VLM reads the same crop to structured JSON. Prompt core: transcribe exactly as printed, never infer or correct, null and `unreadable: true` for anything illegible, never compute totals. Schema: `{panel_name, voltage, phases, rows:[{circuit, breaker_a, poles, wire, load_va, description, cell_flags}], notes}`.
5. **Compare** cell by cell after trimming and unit normalisation. Disagreeing cells become MISSING with both reads and the crop in the note.
6. **Validate.** Breaker in `standard_breaker_ratings`, circuit numbers sequential, VA column sums to a printed total when present, numeric ranges.
7. **Output.** A `Panel` of AI-derived values (`method` `ocr` or `vlm`, `model` filled), the crop, and a NEEDS_REVIEW finding showing the transcription beside the crop.

Self-reported VLM confidence and OCR word confidence may be stored. They are never the gate.

#### M4.5 Deliverables and acceptance

Deliverables: `ai/serving.py`, `ocr.py`, `table_structure.py`, `vlm.py`; `parsers/pdf_ai.py`; `redline models fetch|list|verify`; the `--ai` flag (off by default); crops beside the report; a report section "AI-derived values"; a recorded-response test mode so tests run without a GPU.

**Work table.**

| Leaf | Owns (globs) | Depends on | Gates (acceptance, one line each) |
|---|---|---|---|
| OWNER_DECISION | `config/ai.yaml` (`tier:` only) | none | Owner states GPU model and VRAM and picks `cpu`, `gpu` or `workstation` before L4.2 starts |
| L4.1 central | `src/redline/ai/serving.py`, `model.py`, `config.py`, `cli.py`, `config/ai.yaml` | none | `pytest tests/test_ai_serving.py` green; `test_non_localhost_refused`, `test_digest_mismatch_refused` pass; `redline models list` exits 0 |
| L4.2 ocr-structure | `ai/ocr.py`, `ai/table_structure.py`, `tests/test_ai_ocr.py`, `tests/test_ai_table_structure.py` | L4.1 | Both test files green on recorded responses; `test_rotated_text_gold_crop` passes |
| L4.3 vlm | `ai/vlm.py`, `tests/test_ai_vlm.py`, `tests/recordings/**` | L4.1 | `pytest tests/test_ai_vlm.py` green; `test_json_schema_fallback` and `test_parse_failure_leaves_low_or_missing` pass |
| L4.4 pipeline | `parsers/pdf_ai.py`, `tests/test_ai_pipeline.py`, `tests/test_ai_promotion.py` | L4.2, L4.3 | `pytest tests/test_ai_pipeline.py tests/test_ai_promotion.py` green; each of the three promotion conditions fails alone in its own test; `test_high_unreachable` passes |
| L4.5 report-guard | `report/**`, `tests/test_ai_no_import.py`, `tests/test_ai_no_network.py` | L4.4 | `pytest tests/test_ai_no_import.py tests/test_ai_no_network.py` green; "AI-derived values" section lists crops, models and hashes |

Acceptance:
- Without `--ai`: no model call and no model library import (test with imports blocked). Network access is refused at run time (blocked-socket test).
- With `--ai` and recorded responses, a scanned sample gives a LOW panel and a NEEDS_REVIEW finding with the crop.
- With defaults (`allow_promotion_to_medium: false`) no AI value is above LOW and no VIOLATION comes from AI data. With promotion enabled, a cell is MEDIUM only when all three conditions of 8.8 hold; a test covers each failing alone.
- A first gold set of 10 to 20 owner sheets gives a measured cell-agreement and validator-failure rate, recorded in the README. The full protocol is M6.

**Demo.**
```
redline models fetch --tier gpu
redline check samples/pdf/scanned_panel.pdf --config config/ --out report.html --ai
```

**Effort.** 5 to 7 weeks. **Dependencies.** M3. A machine for the chosen tier. Owner scanned and SHX sheets.

### M5. Symbol detection, fire alarm and egress

**Scope.** Detect devices and exits on plan sheets and run three config-driven checks. Every limit is a `[VERIFY]` placeholder the owner fills.

#### M5.1 Device detection

1. **Block counting (preferred, deterministic).** When the DWG has device blocks, `parsers/dxf.py` reads INSERTs of the block names the owner lists in `fire_alarm.yaml`, with layout, handle and coordinates. HIGH for an exact block-name match.
2. **Symbol detector (PDF or raster only).** RF-DETR on rasterized pages, sizes N, S, M, L only (Apache-2.0). D-FINE is the fallback. Ultralytics YOLO is excluded: it is AGPL-3.0 and the licence applies to trained weights, which attaches obligations to a distributed or hosted product. Detections are method `detector`, LOW, shown as candidates with crops. Sheets are tiled at about 1024 px with 20 percent overlap and merged with NMS. The threshold comes from `detector_thresholds`.

The zero-shot detectors (Grounding DINO, OWLv2) only pre-label candidates for human review while building the gold set. No study evaluates them on floor plans or electrical symbols, and failure on thin line-art glyphs is expected. Licences are to verify. They never run in a report run.

#### M5.2 Exit locations

From the architectural plan (door symbols as blocks in DWG, or detections in PDF) or an owner-supplied `exits.csv` (sheet, x, y, label). The list always wins over detection. Egress paths are owner-supplied polylines or room-to-exit links. The tool does not compute egress routes.

#### M5.3 Checks

Driven by `config/fire_alarm.yaml`. An unfilled limit gives NOT_CHECKED, never a guess.

```yaml
config_version: "0.1-skeleton"
verified: false
source: "<fill from the code and standard the owner applies>"
device_blocks: { exit_sign: [], pull_station: [], emergency_light: [], exit_door: [] }
exit_signs:         { rule_ref: "TODO [VERIFY]", require_at_each_exit: null, max_spacing_along_path_m: null }
pull_stations:      { rule_ref: "TODO [VERIFY]", max_distance_from_exit_m: null }
emergency_lighting: { rule_ref: "TODO [VERIFY]", coverage_radius_m: null, max_gap_along_path_m: null }
```

- **Exit signs.** A sign exists at each exit, and along each path no point lies farther than the configured spacing from a sign. No paths: check exits only and say so.
- **Pull stations.** Each exit has a pull station within the configured distance.
- **Emergency lighting.** Each path is covered by the configured radius, with no gap beyond the limit. No paths: NOT_CHECKED.

Distances need a scale, taken from `document.units` in `RawDrawing` or an owner value per sheet. A PDF sheet with no stated scale gives NOT_CHECKED on every distance check. VIOLATION only when devices and exits are HIGH or MEDIUM (block-derived or owner-listed) and limits are verified. Detector-derived inputs give NEEDS_REVIEW with crops.

#### M5.4 Gold set and labeling plan

- **Tools.** Self-hosted Label Studio (Apache-2.0) or CVAT (MIT). Drawings are client-confidential, so no hosted labeling service.
- **Starting dataset.** SkeySpot: 45 UK electrical plans, 34 classes, YOLOv8 mAP50 81.12 and mAP50-95 48.24 on 13 test plans. Its licence is not stated in the paper and must be read in its repository (UNVERIFIED). Symbols are UK, not CEC, so it is a pipeline starting point only.
- **Excluded.** FloorPlanCAD is CC BY-NC 4.0 and is excluded from any commercial use and from any weights that ship.
- **Own labels.** 300 to 500 instances per class across at least 30 plans from at least 3 firms or styles. Classes: exit sign, pull station, emergency light, horn or strobe, smoke detector, exit door, plus the owner's additions. Split by plan and by firm, never by tile. The zero-shot detector pre-labels, a human accepts, fixes or rejects, and its own metrics on the test plans are reported.
- **Metrics.** mAP50 and mAP50-95 per class, precision and recall at the deployed threshold, and count error per plan, since Redline cares about counts. VLM symbol counting sits at 0.40 to 0.55 accuracy in AECV-Bench (abstract VERIFIED), so a VLM is not the counter. Legend-crop few-shot prompting to verify detections is tested and recorded.

#### M5.5 Deliverables and acceptance

Deliverables: `rules/fire_alarm.py` with three checks; `config/fire_alarm.yaml`; `ai/detect.py` (RF-DETR and D-FINE wrappers, tiling, NMS, pre-labeler); block counting in `parsers/dxf.py`; `exits.csv` reader; report section "Devices and exits"; `gold_eval.py` symbol mode; a labeling guide under `docs/`.

**Work table.**

| Leaf | Owns (globs) | Depends on | Gates (acceptance, one line each) |
|---|---|---|---|
| OWNER_DECISION | `config/fire_alarm.yaml` (`device_blocks`, limits, `source`) | none | Owner supplies device block names, device legends, and the code and standard that sets the fire alarm limits; unfilled limits stay NOT_CHECKED |
| L5.1 central | `src/redline/model.py`, `config.py`, `findings.py`, `engine.py` | none | `pytest tests/test_config.py` green with `fire_alarm.yaml` loaded; `test_unfilled_limit_not_checked` passes |
| L5.2 rule | `rules/fire_alarm.py`, `tests/test_rule_fire_alarm.py` | L5.1 | `pytest tests/test_rule_fire_alarm.py` green with trigger, pass, missing-input and unfilled-limit cases per check (12 cases); `test_detector_inputs_never_violation` passes |
| L5.3 detector | `ai/detect.py`, `tools/gold_eval.py` (symbol mode), `tests/test_ai_detect.py` | L5.1 | `pytest tests/test_ai_detect.py` green; `test_rf_detr_size_rejected` passes for a non-N/S/M/L size; `redline gold eval gold/symbols` prints per-class mAP |
| L5.4 blocks-exits | `parsers/dxf.py` (block counting), `src/redline/parsers/exits.py`, `samples/plans/**`, `tests/test_parser_blocks.py`, `tests/test_parser_exits.py` | L5.1 | Both test files green; `test_block_counts_equal_known_counts` is HIGH; `test_exits_csv_wins_over_detection` passes |
| L5.5 report-docs | `report/**`, `docs/labeling_guide.md` | L5.2 | Report holds a "Devices and exits" section (`test_report_devices_section` green); labeling guide names the six classes |

Acceptance:
- On a DWG fixture with device blocks, counts equal the known counts at HIGH.
- On a PDF fixture with the detector on, devices appear as LOW candidates with crops, and the checks emit NEEDS_REVIEW, not VIOLATION.
- Each check has trigger, pass, missing-input and unfilled-limit tests using TEST-only limits.
- The first gold evaluation is recorded: per-class mAP and per-plan count error.

**Demo.**
```
redline check samples/plans/sheet_fa101.dwg --config config/ --out report.html
redline check samples/plans/sheet_fa101.pdf --config config/ --out report.html --ai --detect
```

**Effort.** 5 to 8 weeks, mostly labeling and detector tuning. **Dependencies.** M2 (blocks), M3, M4 (rendering, serving). Owner plan sheets and device legends.

### M6. Hardening

**Scope.** Prove accuracy, make runs repeatable, package, document.

**Deliverables.**

1. **Gold-set protocol for table cells.**
   - 20 to 30 real schedules: DWG-derived vector PDFs, flattened vector PDFs, scans at 150 and 300 DPI, at least 3 with vertical text and 3 with dense small type. One person transcribes to CSV. A second checks 20 percent to measure human disagreement.
   - Cell match: normalized string equality for typed columns (circuit number, breaker A, poles, wire, load VA). Edit distance of 1 or less for descriptions, reported apart.
   - Per model and config: cell accuracy by column type, row recall, row hallucination rate, unreadable-flag rate, structure score, time per table, and the fraction of wrong cells that carried high confidence. Slice by DPI, rotation and density.
   - Bar on breaker, wire and load: every unresolved disagreement surfaces as needs manual check, and silent wrong passes are counted. The target at default config is zero. Re-run on every model or prompt change. Run each config twice for variance.
2. **Gold-set protocol for symbols.** As in M5.4, with final per-class and per-plan numbers on unseen plans.
3. **`redline xcheck`** finalised: batch mode, CSV output, fallback-loss summary.
4. **Deterministic re-runs.** Pinned model versions, hashes, seeds and prompt versions in `RunInfo`. A test runs one input twice on recorded responses and compares findings byte for byte. A live job reports any difference.
5. **Packaging.** Pip-installable. Extras `[dxf]` (ezdxf), `[pdf]` (pdfplumber), `[ai]` (OCR, table and VLM libraries), `[detect]` (detector libraries). The base install runs CSV. The plugin ships as a build recipe plus a prebuilt DLL per AutoCAD major version.
6. **`redline doctor`** prints pass, warn or fail for: Python and extras; ODA File Converter; `accoreconsole.exe`, its version and a smoke script; plugin DLL for the detected AutoCAD; Ollama version and configured models; GPU and VRAM versus `ai.tier`; model cache, disk and hashes versus `ai.yaml`; which config tables are unverified.
7. **Operator guide** (`docs/operator_guide.md`, short) and a release checklist: licence audit of every dependency and weight file, samples audited for client data.

**Work table.**

| Leaf | Owns (globs) | Depends on | Gates (acceptance, one line each) |
|---|---|---|---|
| OWNER_DECISION | `gold/**` | none | Owner delivers 20 to 30 transcribed table schedules and the symbol labels, with the second-person check on 20 percent |
| L6.1 central | `src/redline/engine.py`, `findings.py`, `model.py`, `config.py`, `pyproject.toml` | none | `pytest tests/test_determinism.py` green (two runs, byte-identical findings); `pip install .` then `redline check samples/csv --config tests/test_config/` exits 0 |
| L6.2 gold-eval | `tools/gold_eval.py`, `tests/test_gold_eval.py` | L6.1 | `redline gold eval gold/tables --config config/` writes results with config and model hashes; `test_silent_wrong_pass_counted` passes |
| L6.3 xcheck-batch | `tools/xcheck.py`, `tests/test_xcheck_batch.py` | L6.1 | `redline xcheck samples/dwg --batch` writes CSV and a fallback-loss summary; `pytest tests/test_xcheck_batch.py` green |
| L6.4 doctor | `tools/doctor.py`, `tests/test_doctor.py` | L6.1 | `redline doctor` prints pass, warn or fail for each listed check; `pytest tests/test_doctor.py` green with monkeypatched missing tools |
| L6.5 docs-release | `docs/operator_guide.md`, `docs/release_checklist.md`, `README.md` | L6.2, L6.4 | A clean machine passes `redline doctor` following only the operator guide; the checklist lists the licence audit and the sample client-data audit |

**Acceptance.**
- Gold-set results come from one command and are stored with the config and model hashes that produced them.
- Repeat runs match.
- A clean machine passes `redline doctor` after following the operator guide.
- `pip install` gives a working CSV demo. Each extra adds its milestone and no more.

**Demo.**
```
redline doctor
redline gold eval gold/tables --config config/
redline xcheck samples/dwg --batch
```

**Effort.** 3 to 4 weeks. **Dependencies.** M2 to M5. Owner labeling time, which runs in parallel from M3.

## 7. Testing strategy

`pytest` only, with `monkeypatch` as the only mocking tool.

- `test_units.py`, `test_config.py`: size spellings; skeleton loads; unverified table downgrades VIOLATION; null key gives NEEDS_REVIEW; hash changes with the file; a model with an empty hash cannot be enabled.
- `test_rawdrawing.py`: valid fixtures pass; missing fields, a higher major version and a bad bbox fail clearly.
- `test_parser_*.py`: each sample gives expected panels, circuits, per-field confidence and `unparsed` items with reasons. Unknown columns are never dropped. DXF parser tests run from `RawDrawing` fixtures. Extractor tests skip with a reason when AutoCAD or ODA is missing.
- `test_ai_*.py`: recorded model responses; no model call and no network call without `--ai`. A separate `-m live` suite runs real models. Promotion tests: off by default, each of the three conditions failing alone blocks it, HIGH unreachable.
- `test_rule_<name>.py`, one per rule: trigger case (rule_id, severity, rule_ref, source, fix), pass case, LOW or missing input case, unverified-table case.
- `test_report_golden.py`: runs `samples/csv/` with the TEST config, compares `findings.csv` to the golden file, checks the HTML sections, counts, hashes, model list and liability sentence.

Fixtures are synthetic or anonymized, never real client files. Rule tests build a `Project` in Python and use the TEST config in `tests/test_config/` (made-up numbers, `verified: true`, every `source` reading `TEST ONLY, NOT CEC VALUES`). Golden files change only by a manual command.

## 8. Confidence and "needs manual check" policy

The contract between parsers, rules and the report.

1. **Four levels:** HIGH, MEDIUM, LOW, MISSING. Every field carries its own level and Source. Only parsers assign levels. Rules never raise them. Derived values take the minimum of their inputs.
2. **Meaning.** HIGH: structured source and exact alias, including an evaluated table cell from the real AutoCAD engine. MEDIUM: heuristic header, loose-text or word cluster, annotation text, or an AI value promoted under 8.8. LOW: OCR, VLM, detector, stale field cell, ambiguous cell, failed numeric parse. MISSING: nothing found.
3. **Rules compute only on HIGH and MEDIUM.** A LOW or MISSING input gives NEEDS_REVIEW for that unit and no computation. A rule never fills a gap, except with `defaults:` from config, named in `inputs_used` as "config default".
4. **VIOLATION requires** HIGH or MEDIUM inputs, verified tables and a failed comparison. A violation resting on MEDIUM input says so, and names the model if the value came from AI.
5. **No pass by silence.** "Checked, no issue" and "not checked" are counted apart. A skipped unit is never a pass.
6. **"Needs manual check" lists** every `unparsed` item, NEEDS_REVIEW finding, NOT_CHECKED check and LOW value a rule needed, each with file, locator, reason and (AI-derived) the crop.
7. **Parsers never guess.** Two cells matching one header: take neither, report both. Unknown unit: keep raw text, LOW.
8. **AI confidence policy.**
   1. OCR word confidence, VLM self-reported confidence and double-read agreement are inputs, never the gate.
   2. A VLM-transcribed or OCR-only cell starts LOW.
   3. A cell may be promoted from LOW to MEDIUM only when all three hold: (a) two independent reads agree (VLM read versus OCR read, or two VLM reads at different crops or temperatures); (b) the hard validators pass (breaker in standard ratings, circuit numbers sequential, VA column sums to a printed total when one is present); (c) the owner has set `ai.allow_promotion_to_medium: true` in `config/ai.yaml`. The default is false.
   4. HIGH is never reachable from AI.
   5. Disagreeing reads become MISSING with both reads and the crop in the note.
   6. Promotion is recorded in `Source.note` with both reads, the validators that passed and the config flag. The report lists promoted cells apart.
9. **Detector outputs** are LOW candidates shown with crops. A check that depends on a detector count reports NEEDS_REVIEW, never VIOLATION, unless the owner supplies the device list.
10. **Every report prints** the code edition, per-table verification status with its `source`, config hashes, tool version, extractor and version for drawings, every AI model name, version and weights hash, and the liability sentence from section 1.
11. **Exit code:** 0 for any completed run (a screening tool, not a gate). 2 only for a config failure or when no input could be read.

## 9. Roadmap

One developer. Total about 24 to 35 weeks. Owner gold-set labeling runs in parallel from M3 and is not counted.

| Milestone | Weeks | Key risk | Demo |
|---|---|---|---|
| M0 Foundation | 2 to 3 | Config design that rules cannot bypass | `pytest -q`, report from a hand-built project |
| M1 CSV and XLSX | 2 to 3 | AutoCAD Electrical export headings are unpublished | `redline check samples/csv` |
| M2 DWG and DXF | 4 to 6 | Core Console licensing and NETLOAD on 2025 and later are unverified | `redline check panel_sheet.dwg`, `redline xcheck` |
| M3 PDF | 3 to 4 | SHX-stroke PDFs with no usable text | `redline check samples/pdf` |
| M4 Local AI | 5 to 7 | Open VLM accuracy on dense schedules is unproven; GPU availability | `redline check scanned_panel.pdf --ai` |
| M5 Symbols, fire alarm, egress | 5 to 8 | Labeling effort; detector accuracy on firm-specific symbols | `redline check sheet_fa101.dwg`, PDF run with `--detect` |
| M6 Hardening | 3 to 4 | Gold sets not ready; model drift | `redline doctor`, `redline gold eval`, `redline xcheck --batch` |

Order: M0, M1, M2, M3, M4. M5 needs M2 and M4. M6 needs M2 to M5. M5 block counting can start once M2 is done.

### First two weeks

In order. The owner's verify-on-machine checks come first, because the DWG architecture rests on them. M0 has no dependency on them and runs in parallel.

Days 1 to 3, owner checks (the seven tasks of M2.3):
1. Find `accoreconsole.exe`, run the `_QSAVE` smoke script on a plain and an Electrical DWG, and time both.
2. Test Core Console licensing with AutoCAD closed and open. Send the licensing question to the reseller.
3. Build and NETLOAD the 20-line test command. Dump the table test DWG (plain, FIELD, DATALINK).
4. Check ODA File Converter. List `.wdp`, `.mdb` and `.accdb` files and database tables from a copy of a real Electrical project.
5. Hand over about 10 real drawings, 5 to 10 real PDF sheets (one scanned) and 2 to 3 real AutoCAD Electrical exports. Record the GPU model and VRAM.

Days 1 to 10, build (M0):
6. Skeleton, `model.py`, `units.py`, `config.py`, the four YAML files, `findings.py`, `engine.py`, the seven rules, report, `cli.py` and `rawdrawing.py`, each with tests.
7. AI baseline on the owner's machine: install Ollama, pull the tier's Qwen3-VL model, run one test crop, record seconds and VRAM, and test JSON-schema output with image input.

End of week 2: the M0 demo passes, verification results are written down, the tier in `ai.yaml` is set, and M1 sample files are in hand.

## 10. Risks and open questions

| # | Risk or question | Mitigation |
|---|---|---|
| 1 | **SHX fonts in PDFs.** A plot can have no real text. `PDFSHX` annotation behaviour is UNVERIFIED. | Page classifier. Annotations MEDIUM at best. Text-less pages go to M4, LOW only. Ask for TrueType plots. |
| 2 | **Loose-text tables, or stale field cells on the fallback path.** | Primary extractor evaluates fields. Fallback marks `evaluated: false` LOW. `xcheck` measures loss. |
| 3 | **PyMuPDF is AGPL or Artifex commercial.** No authoritative guidance found. | pdfplumber (MIT). PyMuPDF only after legal advice. PDF access in one module. |
| 4 | **AutoCAD Electrical headings are unpublished.** | Owner supplies real exports in week 1. |
| 5 | **ODA File Converter** is closed freeware. Redistribution terms UNVERIFIED. | Never bundle. User install. `doctor` reports it. |
| 6 | **Open-model accuracy on panel schedules is unproven.** Published numbers are on printed documents and partly self-reported. | Gold sets in M4 and M6. AI cells start LOW. Promotion needs agreement, validators and owner opt-in. Never HIGH. Silent passes tracked, target zero. |
| 7 | **Project folder is inside OneDrive.** Venv, weights and samples cause sync churn. | Venv and model cache under `%LOCALAPPDATA%`. `gold/` excluded from sync. |
| 8 | **Core Console licensing is unverified.** Sources disagree on seat use. Autodesk does not officially support the tool. | M2.3 step 3. Written reseller answer. Named user's workstation only until answered. Fallback keeps the product working. |
| 9 | **NETLOAD on .NET 8 (AutoCAD 2025 and later)** may crash if a plugin brings an assembly AutoCAD ships. UNVERIFIED. | Autodesk assemblies plus `System.Text.Json` only. One build per major version. |
| 10 | **RF-DETR licence boundary by size.** N, S, M, L and Seg sizes are Apache-2.0. Atto, Femto, Pico, XL, 2XL and NAS fall under PML 1.0. | `config.py` rejects other sizes. Re-read the licence at each upgrade. |
| 11 | **Model drift.** A silent update changes results. | Pin version and `weights_sha256`. Refuse a mismatch. Print in every report. Re-run gold sets on any change. |
| 12 | **GPU availability.** 8 GB VRAM is the minimum for the 8B VLM, 12 to 16 GB is comfortable (SECONDARY). | Tiered config. `doctor` reports the supported tier. Fix the tier before M4. |
| 13 | **AGPL exclusion.** Ultralytics YOLO code and trained weights are AGPL-3.0 or paid. YOLO-NAS weights are non-commercial. | Excluded. D-FINE is the fallback (SECONDARY). |
| 14 | **Dataset licences.** FloorPlanCAD is CC BY-NC 4.0. SkeySpot's licence is unstated in its paper. | FloorPlanCAD excluded from shipped weights. Read SkeySpot's repository licence first. |
| 15 | **M5 labeling effort** is the largest schedule variable. Reports may also read as approval. | Pre-labeling, self-hosted tool, block counting for DWG. Liability sentence in footer and README. |
| 16 | **Process drift.** Section 0 and `DEV-PLAYBOOK.md` can diverge. | `DEV-PLAYBOOK.md` at the repository root is the authoritative process document. Section 0 is its Redline application. On disagreement the playbook wins and section 0 is updated. |

## 11. Out of scope

- Hosted model APIs of any vendor, and any SDK for one. All AI runs locally on open-weights models.
- SaaS, a hosted service, web UI, user accounts, multi-user history.
- Approval, stamping or any compliance statement.
- Code table values supplied by the tool. The owner supplies all of them.
- Short-circuit, arc-flash and coordination studies. Conduit fill, box fill, AFCI and GFCI checks.
- Revit, IFC and BIM ingest, for now. Revit exports are deferred too (row 35): sources are AutoCAD (DWG, DXF and CSV or XLSX reports) and PDF.
- Single-line diagram connectivity tracing, and egress route computation.
- Writing Bluebeam markups or editing source drawings (only `findings.csv` is produced).
- AWG to mm2 conversion and units beyond metres, amps, volts and VA.
- Cloud drawing conversion and the ODA Drawings SDK (M2.6). Training or fine-tuning a VLM.

## 12. Design decisions (log)

| # | Date | Decision | Why | Alternatives rejected | Revisit when |
|---|---|---|---|---|---|
| 1 | 2026-11-06 | Build the full project in milestones M0 to M6 | The owner wants the end-to-end tool, and each milestone ends in a demo | A reduced first version that drops DWG, AI and fire alarm | Scope is cut by the owner |
| 2 | 2026-11-06 | Stdlib `dataclasses` for the model | No dependency, frozen values, simple tests | pydantic | Validation needs outgrow hand checks |
| 3 | 2026-11-06 | `config/` owns every CEC value. The tool never supplies one | A wrong remembered number is worse than a gap | Built-in default tables | Never without the owner's written sign-off |
| 4 | 2026-11-06 | Four confidence levels. Rules compute only on HIGH and MEDIUM | A LOW input must not produce a confident finding | Boolean trusted flag; numeric scores as the gate | Gold sets show levels do not separate error rates |
| 5 | 2026-11-06 | `accoreconsole` plus C# plugin is the primary DWG extractor. ODA File Converter plus `ezdxf` is the fallback. One `RawDrawing` JSON contract | Only the real engine returns evaluated fields, DATALINK tables and Electrical attributes | `ezdxf` alone; LibreDWG | M2.3 steps 3 or 4 fail, or `xcheck` shows no loss |
| 6 | 2026-11-06 | APS Design Automation and the ODA Drawings SDK are deferred | APS sends drawings off the machine. The SDK commercial tier bars hosted use | Adopting either now | Seat-less server ingest or a hosted product is wanted |
| 7 | 2026-11-06 | `pdfplumber` (MIT) over PyMuPDF (AGPL) | AGPL obligations are unresolved | PyMuPDF | Legal advice settles the AGPL question |
| 8 | 2026-11-06 | Local open-weights AI only. No hosted API or vendor SDK | Client drawings are confidential | Hosted VLM APIs | Never for client data |
| 9 | 2026-11-06 | Ollama is the Windows VLM server. vLLM is optional in WSL2 or Docker | Simple local install, localhost only | Community Windows vLLM builds | Batch throughput needs vLLM |
| 10 | 2026-11-06 | Qwen3-VL by tier: 4B (cpu), 8B (gpu), 32B (workstation), Q4 | Fits each hardware class | One model for all tiers | M4 measurements or a newer open VLM |
| 11 | 2026-11-06 | OCR order: PaddleOCR PP-OCRv5, then RapidOCR, then Tesseract last | Tesseract is weak on CAD text and rotation | Tesseract first | Gold set ranks them differently |
| 12 | 2026-11-06 | PP-StructureV3 and Docling TableFormer for table structure | Open, local, cell-level boxes | VLM-only table reading | Gold set favours another engine |
| 13 | 2026-11-06 | RF-DETR sizes N, S, M, L (Apache-2.0) with D-FINE fallback. Ultralytics excluded | AGPL attaches to trained weights | Ultralytics YOLO; YOLO-NAS | Licence terms change |
| 14 | 2026-11-06 | AI values start LOW. Promotion to MEDIUM needs two agreeing reads, passing validators and owner opt-in. HIGH is unreachable | Open VLM accuracy on schedules is unproven | Trusting VLM self-confidence; auto-promotion | M6 gold sets show zero silent wrong passes at scale |
| 15 | 2026-11-06 | FloorPlanCAD is excluded | CC BY-NC 4.0 bars commercial use | Training on it | Licence changes |
| 16 | 2026-11-06 | SkeySpot is read for licence before use | Its paper states no licence | Assuming it is permissive | The repository licence is read |
| 17 | 2026-11-06 | Block counting is preferred over detection for devices | Deterministic and HIGH | Detector counts as the primary source | DWG blocks are absent on most real plans |
| 18 | 2026-11-06 | Exit code 0 for any completed run. 2 only for config failure or no readable input | A screening tool is not a gate | Non-zero on findings | CI gating is requested |
| 19 | 2026-11-06 | Phase balance and completeness are never VIOLATION | They are project practice, not code rules | Treating them as violations | The owner cites a code rule |
| 20 | 2026-11-06 | Venv and model cache live outside OneDrive | Sync churn and corrupt caches | Venv in the repo | Project leaves OneDrive |
| 21 | 2026-11-06 | The C# plugin is the only non-Python component | Keeps the pipeline testable in Python | A second language for parsers | Never without a new row |
| 22 | 2026-11-06 | Jinja2 single-file HTML report plus `findings.csv` | Portable, no server | PDF-first output; web UI | Reviewers ask for a PDF as the primary |
| 23 | 2026-11-06 | `pytest` only, with `monkeypatch` as the only mocking tool | Few moving parts | `unittest.mock`, other plugins | A test cannot be written without more |
| 24 | 2026-11-06 | `DEV-PLAYBOOK.md` governs the process. Section 0 applies it | One source of process truth | Duplicating the process here | The owner revises the playbook |

| 25 | 2026-11-06 | M0 owner decisions: Python 3.12.10, venv at `%LOCALAPPDATA%\redline\venv`, TEST config edition label `TEST EDITION, NOT CEC` | Stage 1 answers for M0 | Naming a real edition in the TEST config | The venv path is unreachable outside the Claude app (MSIX redirect to `AppData\Local\Packages\Claude_*\LocalCache`) |
| 26 | 2026-11-06 | The HTML report follows `DESIGN.md` sections 4, 6 and 7, with system fonts | The owner added `DESIGN.md` as the design philosophy; the report is the only visual surface | A plain unstyled report; voice rules only | Reviewers need colour for print workflows |

| 27 | 2026-11-06 | PyYAML for the config files, `yaml.safe_load` only | The config is YAML (rows 3, 4) | A hand-written YAML parser; TOML | Never without a new row |
| 28 | 2026-11-06 | ruff (dev only) and setuptools (build backend) | CLAUDE.md section 5 names ruff; `pyproject.toml` needs a backend. Neither ships at runtime | black plus flake8; hatchling | A tooling change |
| 29 | 2026-11-06 | `code_edition_verified: false` downgrades every VIOLATION to NEEDS_REVIEW, like an unverified table | A table checked against an unconfirmed edition is not verified | Per-table verification alone | Never without the owner's sign-off |
| 30 | 2026-11-06 | A value from `defaults:` is MEDIUM, named "config default" in `inputs_used`; a VIOLATION resting on it says so | Rules can compute while the reviewer sees the assumption | LOW, so rules never compute on a default | Gold sets show defaults hide real errors |
| 31 | 2026-11-07 | A spare circuit that carries a load stays skipped by the rules but gets one NEEDS_REVIEW finding saying it was not checked. Built in M1 as a gate | CLAUDE.md section 4: a unit not checked is reported as not checked, never passed by silence | Run every rule on it; skip it silently (the M0 behaviour) | The owner rules spare-with-load is never a reviewer concern |
| 32 | 2026-11-07 | openpyxl for reading `.xlsx` panel schedules, read-only mode, values not formulas | M1 reads XLSX and the stdlib has no XLSX reader. Pure Python, MIT licence. Approved by the owner at M1 stage 1 | CSV only, deferring XLSX; pandas | Never without a new row |
| 33 | 2026-11-07 | M1's real-file gate uses 2 to 3 Revit 2026 panel schedule exports from the owner. `aecad_export.headers` stays empty, so AutoCAD Electrical columns still go to `unparsed` | AutoCAD Electrical is not installed on the dev PC, and no public AutoCAD Electrical per-circuit panel schedule export was found (`docs/research/m1_exports.md`). Revit 2026 is installed, and section 11 already accepts Revit exports through M1 | Deferring the gate with synthetic samples only; guessing AutoCAD Electrical headings | An AutoCAD Electrical seat or real export becomes available |
| 34 | 2026-11-07 | M1 stage 2 owner decisions, all as recommended in `.claude/plans/M1.md` 9.1: D1 a file read with no panel exits 0 with the report written; D2 synthetic or anonymized Revit exports in `samples/revit/` with a committed test, client files in `gold/revit/`; D3 the documented Revit parameter names are exact aliases; D4 no Load Classification mapping in M1; D5 the spare-with-load finding (row 31) lives in the completeness rule, always NEEDS_REVIEW; D6 cp1252 fallback for text with no BOM that fails utf-8, named in coverage; D7 bare wire sizes stay LOW. Conflicts C1 to C15 confirmed as written | Stage 2 contract read; the owner accepted every recommendation | Exit 2 for a read file with no panel; mapping Revit classes to load types; guessing AWG for bare sizes | Real Revit exports at L1.6 show otherwise |
| 35 | 2026-11-08 | Revit is deferred. Sources are AutoCAD (DWG, DXF and CSV or XLSX reports) and PDF. Reverses row 33 and the Revit parts of row 34 (D2) and section 11. M1 has no real-file gate: the L1.6 gates are abandoned with the owner's reason, and node gate N2 no longer names leaf-L1.6. The Revit names pre-added as aliases (D3) stay, since they are harmless and tested. The README says Revit is coming soon | The owner has no way to get Revit exports, and the 2026-11-08 attempt to export from the Revit sample on the dev PC did not finish. Owner words: "for now 86 the revit use, make it DWG/PDF/Autocad Only" | Keep waiting on Revit exports; remove the Revit aliases | The owner supplies Revit exports, or a Revit seat works on the dev PC |
| 36 | 2026-11-09 | M1 close: the 8 open items in `docs/handoffs/M1.md` section 5 keep the current behaviour and are recorded as design limits. No CSV row cap. XLSX sheet titles over 31 characters stay listed, not read. The 8 MiB XLSX cap counts every archive member. No defusedxml; the DOCTYPE scan stays. A title between tables keeps the panel above at NEEDS_REVIEW (RV62). RV83 stays abandoned. The section 4 residuals are accepted. The M0 and M1 worktrees and task branches are removed at close | Owner at M2 stage 1: "Close M1 now", as recommended | A CSV row cap; reading long sheet titles cut to 31 characters; counting only read XLSX parts; defusedxml; reading on past a title; gating RV83 | A real file hits one of these limits |
| 37 | 2026-11-09 | ezdxf for the fallback DWG and DXF path (`extract/oda_ezdxf.py`), reading the DXF that ODA File Converter writes | M2.1 names ezdxf as the fallback reader; the stdlib has no DXF reader. Pure Python, MIT licence. Approved by the owner at M2 stage 1 | A hand-written DXF reader; LibreDWG (GPL) | Never without a new row |
| 38 | 2026-11-09 | M2 stage 1 owner decisions: the .NET 8 SDK (8.0.427, winget) is installed on the dev PC to build the plugin, a build tool only, never shipped; the owner installs ODA File Converter, never bundled; M2 fixtures are synthetic, because a three-agent web search found no usable, redistributable real panel-schedule DWG (`docs/research/m2_dwg_search.md`); the plugin runs only on the owner's workstation until the reseller answers on Core Console licensing (M2.3 task 3) | Owner answers at M2 stage 1. AutoCAD 2026 `accoreconsole.exe` and its managed assemblies are under `D:\Autodesk\AutoCAD 2026` | Fallback only with no plugin; real drawings bought from aggregator sites | The owner supplies real drawings, or the reseller answers |
| 39 | 2026-11-09 | Real drawings for M2 are in `gold/dwg/` (git-ignored): 20 real AutoCAD Electrical projects (`.wdp`, about 613 DWG, one project `.mdb`) from the GitHub ACE sample set and an Autodesk Learn course, one hypothetical panel-P1 sheet set with JSON ground truth, and 2 ETSU plan DWGs (CC BY 4.0, the only ones that may be committed). The AutoCAD Electrical side inputs (`.wdp`, project database, `WD_M` attributes) stay in M2 scope against these files. Panel schedule fixtures stay synthetic. Adds to row 38 | Owner: "DO the research I said"; a second three-agent search found these, and the owner approved the four downloads (`docs/research/m2_dwg_search.md` round 2) | Deferring the Electrical side inputs like Revit; synthetic `.wdp` and `.mdb` files | Their licences bar even private use, or the M2.3 dumps show they hold no usable attributes |
| 40 | 2026-11-09 | M2 stage 2 owner decisions, all as recommended in `.claude/plans/M2.md` 12.1: D1 no project database reader in M2, `.mdb` and `.accdb` are listed as not read, no `pyodbc`; D2 the owner authors `samples/dwg/panel_sheet.dwg` in AutoCAD 2026 to the M2.md 4.9 spec, synthetic and committed; D3 a `live` pytest marker, deselected by default, with a run-time skip only inside live tests; D4 every fallback cell is `evaluated: false` until the FIELD check is shown right on the owner's FIELD table; D5 with an empty `wd_m_attribute_map` each WD_M attribute is listed; D6 machine paths go in `config/column_maps.yaml` `parsing:` (core console `D:/Autodesk/AutoCAD 2026/accoreconsole.exe`; the plugin DLL path, with no spaces, and the ODA File Converter path are still to be given by the owner); D7 the plugin is built for AutoCAD 2026 only, and the owner names the firm's versions later; D8 agents may run `accoreconsole.exe` on this PC in stages 3 and 4; D9 WD_M and `.wdp` work proceeds without an AutoCAD Electrical seat, and the owner updates CLAUDE.md 9 at stage 6; D10 the owner asks the reseller about licensing in writing, and no script changes SECURELOAD or TRUSTEDPATHS without the owner's written say | Stage 2 contract read; the owner accepted every recommendation in chat ("Accept all D1-D10") | A `pyodbc` reader with no real project database; agent-authored FIELD tables; a skip marker on extractor tests; trusting fallback cells as evaluated | L2.7 real-file results or the reseller's answer show otherwise |
| 41 | 2026-11-09 | M2 stage 3 owner decisions: AutoCAD 2026 `accoreconsole.exe` crashes on every run on the dev PC (exit 0xC0000005, faulting module `AcPal.dll`, even with `/?` alone; no `HKCU\Software\Autodesk\AutoCAD` key), so the owner launches AutoCAD 2026 once and signs in to create its profile, then the lead re-runs the L2.0 and L2.1 live gates; agents never sign in or change AutoCAD settings. L2.2 starts in wave 2 on L2.0's partial result (run on a copy; unit tests monkeypatch subprocess; live gates stay BLOCKED) | Owner answers at M2 stage 3, after workers W2 and W3 and the lead each reproduced the crash | Dropping the core console path now; holding L2.2 until L2.0 is fully verified | The core console still crashes after a first AutoCAD launch, or ODA stays uninstalled |
| 42 | 2026-11-09 | Replaces D7 of row 40 and the AutoCAD 2026 host of rows 38 and 41: the plugin is built for AutoCAD 2027 only (`C:\Program Files\Autodesk\AutoCAD 2027`, core console 26.0.60, .NET 10), target `net10.0-windows`; every other version is not built. The owner installs the .NET 10 SDK (a build tool only, never shipped). `accoreconsole_path` becomes the 2027 core console. ODA File Converter is installed at `C:\Program Files\ODA\ODAFileConverter 27.10.0\ODAFileConverter.exe`. The leaf-L2.1 gates and the L2.0 smoke test move to the 2027 paths by contract amendment. The owner draws `samples/dwg/panel_sheet.dwg` in AutoCAD 2027 and saves it as AutoCAD 2018 DWG | The owner's first launch was AutoCAD 2027 (profile R26.0). The lead ran the 2027 core console on a temp copy of the ETSU drawing: exit 0 in 3.0 s, script ran, nothing written beside the copy, original hash unchanged, no process left. AutoCAD 2026 still exits 0xC0000005 with no R25.1 profile | Keeping 2026 (needs a 2026 first launch); building both | The firm names the AutoCAD versions it runs |
| 43 | 2026-11-10 | M2 close: the open residuals in `docs/handoffs/M2.md` section 4 keep the current behaviour and are recorded as design limits (RV27 residuals, the review-M2 "not taken" lists of rounds 2, 3, 6 and 7, the header not taken items, and AutoCAD reaching a network xref path on the plugin path, SR4). RV45, G5.14, G5.17 and N2 stay abandoned. The missing evaluated flag for TEXT, MTEXT and attribute fields carries to M3 planning. The M2 worktrees and task branches are removed at close | Owner after M2 stage 6: "Close it off" | Another review round before merge; gating the merge on RV45 | A real drawing hits one of these limits |
| 44 | 2026-11-10 | pdfplumber for the PDF path (`src/redline/parsers/pdf.py`), `pdfplumber>=0.11,<0.12` as the `[pdf]` extra. It brings pdfminer.six, Pillow and pypdfium2, plus charset-normalizer and cryptography through pdfminer.six; leaf L3.0 records the installed versions and licences. pypdfium2 ships a PDFium binary that M3 never calls. Stage 5 checks pdfminer.six advisories and may set a version floor | Row 7 chose pdfplumber over PyMuPDF; this row is the dependency approval in the shape of rows 32 and 37. MIT licence. Approved by the owner at the M3 stage 2 read (D1) | PyMuPDF (AGPL, section 10); a hand-written PDF reader | Never without a new row |
| 45 | 2026-11-10 | M3 stage 1 and stage 2 owner decisions, all as recommended in `.claude/plans/M3.md` 12.1: D1 pdfplumber approved (row 44); D2 the pdfplumber read runs in a child process under `parsing.pdf_timeout_s`, reusing `redline.extract.run_tool`; D3 tables with no drawn grid are MEDIUM at most, tables ruled by drawn lines are read as CSV, so exact headers are HIGH; D4 a page with a full-page image and a text layer is SCANNED, its text is not read, and the reason says it is likely OCR; D5 the PDF clustering keys are separate from the DXF keys; D6 agents plot `%TEMP%` copies of `samples/dwg/panel_sheet.dwg` with the AutoCAD 2027 core console, set PDFSHX for the run and restore it, the lead plots in the GUI by computer control if the core console cannot plot, plots are committed only with clean metadata, and SECURELOAD and TRUSTEDPATHS are not touched; D7 the owner supplies 5 to 10 real sheets (one scanned) in `gold/pdf/` with panel and circuit counts per page, the title block position and the TrueType re-plot answer, and L3.5 stays BLOCKED until then; D8 the row 43 carry-in (evaluated flag for TEXT, MTEXT and attribute fields) is not in M3 and goes to M5, or to a small DWG patch if the owner names one, and loose text stays MEDIUM at most meanwhile; D9 stage 1 closes with the sheets still owed, the lead creates `m3` from tag `M2`, and M3 builds on synthetic samples. Conflicts C1 to C25 confirmed as written | Stage 2 contract read; the owner accepted every recommendation in chat ("Accept all, start") | Holding M3 until the sheets arrive; one confidence cap for every PDF table; reading OCR text layers; shared PDF and DXF clustering keys | The owner's sheets at L3.5 show otherwise |

New dependencies and any reversal of a row above get a new row, never an edit of the old one.
