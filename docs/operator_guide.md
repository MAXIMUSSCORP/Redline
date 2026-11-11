# Operator guide

## Setup

The venv lives outside OneDrive, at `%LOCALAPPDATA%\redline\venv`. Python 3.12 or later is needed. These are the steps a new machine follows, from the repo folder (the tracked files, for example a `git archive` export):

1. Make the venv: `python -m venv %LOCALAPPDATA%\redline\venv`
2. Install Redline, not editable, with the tested versions:

        %LOCALAPPDATA%\redline\venv\Scripts\python.exe -m pip install . -c constraints.txt

   `constraints.txt` lists the exact versions of the tested set. The base install is PyYAML, Jinja2 and openpyxl. It reads CSV, TXT and XLSX schedules and runs the demo, `redline doctor` and `redline gold eval` on CSV sources. Build needs `setuptools>=64`, which pip fetches; `constraints.txt` does not pin it.
3. Add the extras you need. Each is an extra of the same package:
   - `[dxf]` adds ezdxf, for the DXF and ODA route: `pip install ".[dxf]" -c constraints.txt`
   - `[pdf]` adds pdfplumber, for PDF sheets: `pip install ".[pdf]" -c constraints.txt`
   - `[dev]` adds pytest, ruff and both extras above, for developers.
4. Check the machine:

        redline doctor --config config/
        redline check samples/csv --config tests/test_config/ --out report.html

5. When AutoCAD and the plugin are set up (see "Check a drawing"), run the smoke run on a drawing:

        redline doctor --drawing samples/dwg/panel_sheet.dwg --config config/

Developers install editable instead: `pip install -e ".[dev]"`.

### A machine with no internet

On a machine that can reach PyPI, download the wheels once: `pip download . -c constraints.txt -d wheels` (add `".[dxf]"` and `".[pdf]"` as needed). Copy the `wheels` folder over. Then install with `pip install . -c constraints.txt --no-index --find-links wheels`. The `setuptools` wheel must be in the folder too, because the build needs it.

### Clean machine tiers

Tier A is what an agent can run. It exports the tracked files with `git archive` into a new folder, makes a new venv, runs the install line above, then `redline doctor` and the CSV check line. It proves the tracked files and this guide are enough for the Python side. It does not prove a new PC.
Tier B is the owner's. On a second Windows PC, or in a new Windows user account on this PC, follow only this guide: Python, the venv, the extras, ODA File Converter, AutoCAD's first launch, the plugin folder and TRUSTEDPATHS. Then run `redline doctor --drawing samples/dwg/panel_sheet.dwg` and report its output. Redline never changes TRUSTEDPATHS or SECURELOAD, and `redline doctor` never starts AutoCAD's window.

## Check the machine: redline doctor

    redline doctor --config config/

Doctor prints one line per check: a status word, the check name, then the detail. It ends with a count line, for example `PASS 8, WARN 14, FAIL 0, NOT CHECKED 2`. It writes no file, opens no socket and imports no model library.

- PASS: the check held.
- WARN: a choice or a gap, such as an extra not installed, a tool path not set, or a config table not verified. The skeleton config ships unverified, so every table shows WARN.
- FAIL: a fault, such as a path that is set and points at nothing, or a version outside its range.
- NOT CHECKED: doctor could not tell. The line gives the reason. The AI line reads NOT CHECKED while the AI module is not built.

"Passes doctor" means the output has no FAIL line. Doctor exits 0 whenever it ran to the end, with FAIL lines or not. It exits 2 only when the config folder cannot be loaded. Checks that need no config print first.

Flags:

- `--config DIR`: the config folder, default `config`.
- `--drawing FILE`: a drawing for the plugin smoke run. Doctor copies it to a temp folder, runs the dump on the copy, and reads the plugin and host versions from the dump. Setup uses `--drawing samples/dwg/panel_sheet.dwg`. Without it the plugin line is NOT CHECKED, because NETLOAD refusal cannot be seen without a drawing.
- `--licences`: print the licence table as CSV and nothing else (see `docs/release_checklist.md`). The release commits it as `docs/licences.csv`.

Doctor never starts `ODAFileConverter.exe`. It checks that the file exists. The core console smoke run is on by default.

## Run the demo

    redline check --demo-project tests/golden/demo_project.json --config tests/test_config/ --out report.html

This writes `report.html` and, beside it, `findings.csv`. Add `--skip-rule ID` to leave a rule out; it is listed in the report as not run.
Use `--config config/` for the real skeleton config. Every VIOLATION is then shown as NEEDS_REVIEW, because no table is verified.

## Check a folder of schedules

    redline check samples/csv --config tests/test_config/ --out report.html

Give one or more files or folders. A folder is read without going into sub-folders, files in name order. Redline reads `.csv`, `.txt` and `.xlsx` panel schedules. Revit exports are not supported yet; Revit is coming soon.
Any other file is listed in the coverage table as "not read: unsupported file type". A file that cannot be read is listed with the reason, and the other files are still read.
Do not combine inputs with `--demo-project`. Do not write `--out` inside an input folder, because the next run would read `findings.csv` as input.

Text files are read as UTF-8, with a byte order mark if present, and as cp1252 when the bytes are not valid UTF-8. The encoding used is named in the coverage table.

### What is read and what is listed

A line is read as a circuit only when its circuit cell has circuit shape, such as `7`, `7A` or `CB1`. Any other line is listed in the report as not read, and the panel next to it is marked as possibly incomplete. Panel-level checks then show NEEDS_REVIEW, not a result.
A CSV has no row limit, and memory use grows with the number of circuits.
An XLSX sheet is listed as not read when its name is longer than 31 characters, or when it has more than 20000 rows or 200 columns. A workbook is refused when its parts unpack past 8 MiB, or when it holds more than 50000 rows in total. The 8 MiB count includes embedded media.

## Check a drawing

    redline check samples/dwg/panel_sheet.acad_plugin.rawdrawing.json --config tests/test_config/ --out report.html
    redline check plan.dwg --config config/ --out report.html

Redline reads `.dwg` and `.dxf` drawings and `.rawdrawing.json` files. A `.rawdrawing.json` is the dump an extractor wrote; it needs no CAD software, so a dump can be checked on any PC. A `.dwg` or `.dxf` is dumped first, by one of two extractors, then read the same way. A drawing that no extractor can read, or that times out, is listed in the report with the reason. The other files are still read.
Panel tables are read as tables. Text that only sits in rows is read as loose text, and its values are never above MEDIUM. A table cell that is not a stored value (a field that was not evaluated) is LOW. Xrefs that were not resolved, and tables without row and column counts, are listed as not read.
The report footer names each drawing's extractor, its version, the host version and the full SHA-256 of the drawing.

Extractor setup. All three path keys are under `parsing:` in `config/column_maps.yaml`, and each is `null` until set:

- `accoreconsole_path`: AutoCAD Core Console, `accoreconsole.exe`. Used with the plugin.
- `acad_plugin_dll`: the built plugin. The path must hold no space. Build it with `dotnet build extractors/acad_plugin/RedlinePlugin.csproj -c Release -p:AcadDir="C:/Program Files/Autodesk/AutoCAD 2027" -p:AcadVersion=2027`. Only AutoCAD 2027 is built, with the .NET 10 SDK.
- `odafc_path`: `ODAFileConverter.exe`. Redline does not bundle the ODA File Converter. Install it yourself.

Xrefs and untrusted drawings. On the plugin path, Redline reads no xref content and lists every xref as not read. AutoCAD itself may still try to open an xref path stored in the drawing when it opens the drawing. That path can be a network path. To keep a drawing from an untrusted source fully offline, block outbound file sharing (SMB) for `accoreconsole.exe`, or set `dxf_prefer_extractor` to `"oda_ezdxf"`.

The plugin runs on the owner's workstation only, until the reseller answers on Core Console licensing (PLAN row 38). The ODA route needs the `[dxf]` extra: `pip install -e ".[dxf]"` (it adds ezdxf). Without it, a `.dxf` or `.dwg` that needs ODA is listed as not read.

### The fallback's child process

The fallback extractor reads a drawing with ezdxf. That read runs in a child Python process, not in the Redline process. A crafted drawing can make ezdxf itself run for a very long time, and a child can be stopped.
For a `.dwg`, ODA File Converter first writes a `.dxf` in a temp folder, in its own process. The child then opens that `.dxf` (or the `.dxf` you gave), reads the layouts, tables, texts and xrefs, and writes a RawDrawing JSON file back to the temp folder. The parent validates that file.
The child has the time set by `dxf_extractor_timeout_s` under `parsing:` in `config/column_maps.yaml`, 120 seconds in the shipped config. On timeout Redline stops the child and its sub processes. The extractor then fails with "ezdxf timed out after 120 s". If the other extractor can read the drawing, that one is used, and the report notes that the first one failed. If neither can, the file is listed in "Needs manual check" with the reason. When it is the only input, the run exits 2.
For a `.dwg` the ODA step and the child each get the full time, so one drawing can take up to twice the setting.
Each drawing pays the cost of starting a child process. It was about 1.5 seconds per drawing over a corpus of 616 gold drawings (review-M2 round 6).
The child needs ezdxf in the same venv as Redline. ezdxf that sits only in a user site folder or on `PYTHONPATH` is not seen.

## Check a PDF

    redline check samples/pdf --config tests/test_config/ --out report.html

Redline reads `.pdf` sheets and schedules. No real owner sheet has been run through the PDF reader yet, and every `pdf_*` value under `parsing:` in `config/column_maps.yaml` is a starting value to tune on real sheets.

### Install

The reader needs the `[pdf]` extra: `pip install -e ".[pdf]"`. It installs `pdfplumber>=0.11.9,<0.12` and, through it, pdfminer.six at 20251230 or later. The `[dev]` extra carries the same line. On a machine with no internet, download the wheels for pdfplumber and its dependencies on another machine, then install with `pip install --no-index --find-links <wheel folder> "pdfplumber>=0.11.9,<0.12"`.
Without the extra, a PDF is listed in "Needs manual check" with "pip install redline[pdf]", and the other files are still read. A password protected PDF is listed as not read.

### The three page classes

Each page is put in one class, shown in the page's coverage entry. The thresholds are `pdf_text_page_min_chars` (1 to 10000) and `pdf_scanned_image_area_fraction`.

- TEXT: the page has a text layer. Redline reads the title block, then ruled tables, then text laid out as a table. A table ruled by drawn lines is read like a CSV, so an exact header can be HIGH. Text laid out with no drawn grid is MEDIUM at most, and the note says "no drawn grid". A ruled table that sits in the title block corner is read too. Annotations on a TEXT page are counted, not read.
- VECTOR_NO_TEXT: the page has no text layer, only strokes. This is how AutoCAD plots SHX fonts. If the page has annotation text, Redline reads a table from the annotations (see "SHX annotation text"). A page with annotations that gives no circuit, or a page with no annotations, is listed in "Needs manual check" with a note to re-plot with TrueType substitution, or to use OCR or vision. A page with some text but under `pdf_text_page_min_chars` is listed as having too little text.
- SCANNED: a full-page image covers the page. The page is listed as needing OCR or vision. A scan that carries an OCR text layer is classed the same way and its text is not read, because an OCR layer is not a stored value.

Ask for TrueType re-plots of SHX sheets. In AutoCAD, plot with TrueType substitution so the text stays text in the PDF. A page listed as VECTOR_NO_TEXT or SCANNED is never read as empty; it is listed as not checked.
A PDF that opens counts as read, even when every page is listed. The run still exits 0.

### SHX annotation text

When AutoCAD plots an SHX font with `PDFSHX` set to 1, each text string is also stored as a `/Square` annotation named `AutoCAD SHX Text`. With `PDFSHX` set to 0 the PDF holds no text at all (`docs/research/pdf_verification.md`, sections 3 and 4). Redline reads the annotation text as a source. Annotation values are MEDIUM at most.
Where annotation text and the page's own text disagree, the cell is LOW and one item is listed with both texts and the cell locator. Page words outside the title block that no annotation covers are listed. The annotation count is a count of strings, not of cells.
The plot `samples/pdf/acad/acad_pdfshx.pdf`, made by AutoCAD 2027 with `PDFSHX` 1, reads panel LP-11 with no circuits and the "needs OCR or vision" note. Its side-by-side panels merge in one grid.

### The title block

The title block is read from a crop at the bottom right of each page. The crop size is `pdf_title_block_width_fraction` and `pdf_title_block_height_fraction` under `parsing:`. A page that is rotated is not read for a title block and says so.
The keys are the aliases under `title_block:` in the same file: `sheet_number`, `revision` and `other_labels`. A label that is not an alias is not read. `other_labels` lists title box labels such as date, scale and drawn by; a label there is never taken as a value. Add the labels your sheets use.
A value must have the shape of its key. A revision is one token of at most `pdf_title_revision_max_chars` characters. A sheet number with no digit is one token of at most `pdf_title_sheet_max_chars_without_digit` characters. A cell that fails is not a value, and the coverage says "not found". A revision column that holds more than one value is named as such, not read as its first value.
A short token directly under the REV cell of a bottom-header revision table can still be read as the revision. Crop words the title reader did not use are counted in the page's coverage, not dropped.
The report footer names each PDF's reader, its pdfplumber and pdfminer.six versions and the full SHA-256 of the file.

### What is listed, not read

Each of these is listed with the file and page, never dropped: a page in the SCANNED or VECTOR_NO_TEXT class that gives no table, rotated words not clustered, ruled tables that are not a panel, word regions with no header, cells where annotation and page text disagree, and warnings the reader wrote. At most 50 items are listed per page. The page's coverage line gives the full count.
A page past a cap is listed and not read: more than 100000 words, 10000 annotations or 1000000 characters on one page. A PDF over 256 MiB is not read. Pages past 1000 are listed with their total.

### The child process

The reader runs in a child process, as the DXF fallback does, so a crafted PDF can be stopped. The child has `pdf_timeout_s` seconds under `parsing:`, 300 in the shipped config, a placeholder until measured on real sheets. On timeout the file is listed with the reason. The config check rejects `pdf_timeout_s` and `dxf_extractor_timeout_s` above 86400.
On Windows the child also runs under a Job Object with a memory ceiling of 4096 MB (`MAX_CHILD_MEMORY_MB` in `src/redline/parsers/pdf.py`). A PDF that needs more is listed as not read. On another platform there is no ceiling, and the report lists a warning saying so. pdfminer is stopped at 200000 entries in one array or dictionary.
The child needs pdfplumber in the same venv as Redline. The child is started with `-I`, so a package that sits only in a user site folder or on `PYTHONPATH` is not seen.
The `samples/pdf/acad/` sub-folder holds real AutoCAD plots for developers. A folder run lists a sub-folder and does not read it.

### Tests that time the reader

Some tests in `tests/test_parser_pdf.py` assert that a crafted PDF is read within 1 or 2 seconds. They fail when the PC is on battery in Silent mode, and pass on mains power. Run `pytest -q` on mains power.

## Check fire alarm devices and exits

    redline check samples/plans --config config/ --out report.html

A folder of `.dxf` or `.dwg` plan sheets is read for device blocks. Redline counts blocks by name; it does not read symbols from a picture, and PDF sheets give no devices until the detector (L5.3) is built.

1. Run once. The report section "Devices and exits" lists every block name that matches no device class, with the number of placements. A long list is cut at 500 names per file, and "Needs manual check" says how many are not shown.
2. Put the names you want read under `device_blocks` in `config/fire_alarm.yaml`, one list per class. See `docs/labeling_guide.md`. Run again.
3. Give the exits and egress paths in two files next to the sheets:
   - `exits.csv`, columns `sheet,x,y,label`, and an optional `units` column. One row per exit, in drawing units.
   - `paths.csv`, columns `sheet,path,seq,x,y`. One path is its rows in `seq` order.
   A file in the folder named `exits.csv` or `paths.csv` is read after the drawings. A row that cannot be read is listed and that exit or path gets no check.
4. Exits: when `exits.csv` has rows for a sheet, that list wins for the sheet and the exit door blocks of that sheet are shown as `unused`.
5. Units: the drawing header gives the length unit. A sheet with no usable unit gives NOT_CHECKED for every distance. The owner can state the unit in the `units` column of `exits.csv` (`mm`, `cm`, `m`, `in` or `ft`); that overrides the header, and the report names both. When the header states a different unit, the sheet is listed under "Needs manual check" with both units and the unit used, and the unit is then a MEDIUM input.
6. Limits: each limit in `fire_alarm.yaml` that is `null` gives NOT_CHECKED for that check. Nothing is passed by silence.
7. `exit_signs.max_distance_from_path_to_sign_m` is read as the farthest a point of an egress path may lie from an exit sign. A point within that distance of a sign is covered, so signs up to twice the value apart pass. The old name `max_spacing_along_path_m` is a config error. The reviewer confirms this meaning [VERIFY].
8. `fire_alarm.yaml` carries `verified: false` until a qualified reviewer fills and verifies it. While it is false, every VIOLATION from the fire alarm rule is shown as NEEDS_REVIEW, and the Config tables row for `fire_alarm.yaml` reads NOT VERIFIED.

Devices read from blocks are never worse than their confidence: a block inside another block or an xref is LOW and is not measured.

## Compare the two extractors

    redline xcheck plan.dwg --config config/
    redline xcheck --batch drawings/ --config config/ --out xcheck-out

`xcheck` runs both extractors on each file and prints a table of what each one found (entity counts, tables, cells, evaluated cells, attributes, cells whose text differs). A file that one extractor could not read shows its reason under the table. It exits 2 only when no extractor read any file.
With `--batch`, give files or folders. Redline reads many drawings, prints a summary, and writes `xcheck.csv` (columns `file`, `item`, `primary`, `fallback`) into the `--out` folder, the current folder when `--out` is not given. Without `--batch` nothing is written.

## Measure the readers: redline gold eval

    redline gold eval samples/gold/tables --config tests/test_config/ --out results

`gold eval` reads `manifest.csv` in the folder you give, parses each source with the reader `redline check` uses, and compares the cells with a transcribed truth file. It prints the table counts, the silent wrong passes and the silent missing rows, then the results folder. It exits 0 when it completes and 2 on a config failure or when no manifest can be read. `--out` defaults to `results` inside the gold folder.
The committed set `samples/gold/tables/` is synthetic and tests the tool. The owner's real set goes in `gold/tables/`, which git ignores and which is never committed, because the results quote client text.

### The layout

    gold/tables/
      manifest.csv
      sources/<source file>
      truth/<table_id>.csv
      check/<table_id>.csv
      results/            (written by the tool)

`manifest.csv` is UTF-8, one row per table, with nine columns:

- `table_id`: a short id with no spaces. It names the truth file.
- `source_file`: the path under the manifest's folder.
- `page_or_layout`: the PDF page number or the DWG layout name. Blank for a CSV.
- `panel`: the panel name as drawn.
- `kind`: `csv`, `dwg`, `dwg_pdf`, `flat_pdf`, `scan_150` or `scan_300`.
- `tags`: optional, separated by `;`, such as `vertical_text` or `dense`.
- `transcribed_by` and `checked_by`: initials. `checked_by` is blank when the table was not checked.
- `notes`: free text.

`truth/<table_id>.csv` has a header row and one row per circuit row in drawn order, spares and spaces included. The columns are `circuit`, `description`, `breaker_a`, `poles`, `wire` and `load_va`. Type each cell as drawn. Leave a cell empty when the sheet is empty there. Write `[unreadable]` for a cell you cannot read. Do not convert units and do not fix a drawing error.
The second check: a second person transcribes about one table in five again, from the source alone, without seeing the truth file. The tables at positions 1, 6, 11 and so on in `table_id` order are used. The result goes in `check/<table_id>.csv`, in the same format. The tool reports the cells that differ between the two files and the rows present in one only. The owner settles each difference in the truth file.

### The outputs

The results folder holds four files:

- `results.csv`: counts and ratios per table and column. It holds no time, so it repeats byte for byte.
- `cells.csv`: every cell that is not correct, with table, circuit, column, gold, predicted, confidence and outcome.
- `run.json`: the tool version, config hashes, extractor versions, and the SHA-256 of the manifest and each source.
- `timing.csv`: seconds to parse each source.

Each ratio is written beside its two counts. The metrics are cell accuracy by column, row recall, row hallucination rate (extra rows over predicted rows), the unreadable-flag rate, wrong cells by confidence, and human disagreement when check files exist. A table whose two reads differ is named "repeat run differs".
A silent wrong pass is a wrong cell in `breaker_a`, `wire` or `load_va` whose confidence is HIGH or MEDIUM, so a rule would compute on it. A silent missing row is a missed row the run did not list. The target for both is zero. A count above zero is a measured fault in a reader, not a pass.
Numbers are normalized before comparing: case and spacing for text, units and thousands commas for numbers, the size normalizer for wire.

## Repeat runs

The same input bytes, config bytes, Redline version, dependency versions and machine give the same bytes in `findings.csv` and `report.html`. `tests/test_determinism.py` checks this by running `redline check` twice in separate interpreters with different hash seeds, folders and `--out` folders.
This is not claimed across operating systems (the report is written with platform newlines) or across dependency versions. The RawDrawing dump holds an extraction time and is not compared. The report and `findings.csv` carry no clock time, run id, user name or absolute path.

## Limits on fire alarm checks

Two limits bound the pair comparisons in the fire alarm rule: 2000000 pairs per sheet part, and 20000000 over the whole run. When the run limit is spent, each later check is NOT_CHECKED with the reason "the run's limit of pair comparisons was reached; check by hand". Sheets are taken in a fixed order, so repeat runs match.
Type numbers in `exits.csv` and `paths.csv` with no thousands separator, or quote the cell. An unquoted comma inside a number shifts the cells, and the shifted row can still be read at HIGH when it fits the header. Redline does not guess what was meant. Excel quotes such cells, so only hand-typed files are exposed.

## AutoCAD Electrical project files

A `.wdp` project file is read as a list of the drawings it names. The drawings themselves are not opened, and no path inside the file is followed. `.mdb` and `.accdb` project databases are listed as "not read: unsupported file type".

## Exit codes

- 0 (the run exits 0): the run completed. Findings do not change the code, because Redline screens and does not gate.
- 2 (the run exits 2): a config failure, an unreadable or invalid demo project, no input given, no input file that could be read, or an `--out` that would overwrite an input. One line on stderr says which.

A file that was read but held no panel still exits 0. The report is written and lists the file as "no panel read".

## The TEST banner

A report that opens with "TEST EDITION, NOT CEC" was run on the test config. Its numbers are made up
for testing and are not Canadian Electrical Code values. Do not use such a report for review.
