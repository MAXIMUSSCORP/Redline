# Operator guide

## Setup

The venv lives outside OneDrive, at `%LOCALAPPDATA%\redline\venv`. Install from the repo root:

    %LOCALAPPDATA%\redline\venv\Scripts\python.exe -m pip install -e ".[dev]"

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
- `acad_plugin_dll`: the built plugin. The path must hold no space. Build it with `dotnet build extractors/acad_plugin/RedlinePlugin.csproj -c Release -p:AcadDir="D:/Autodesk/AutoCAD 2026" -p:AcadVersion=2026`.
- `odafc_path`: `ODAFileConverter.exe`. Redline does not bundle the ODA File Converter. Install it yourself.

Xrefs and untrusted drawings. On the plugin path, Redline reads no xref content and lists every xref as not read. AutoCAD itself may still try to open an xref path stored in the drawing when it opens the drawing. That path can be a network path. To keep a drawing from an untrusted source fully offline, block outbound file sharing (SMB) for `accoreconsole.exe`, or set `dxf_prefer_extractor` to `"oda_ezdxf"`.

The plugin runs on the owner's workstation only, until the reseller answers on Core Console licensing (PLAN row 38). The ODA route needs the `[dxf]` extra: `pip install -e ".[dxf]"` (it adds ezdxf). Without it, a `.dxf` or `.dwg` that needs ODA is listed as not read.

## Compare the two extractors

    redline xcheck plan.dwg --config config/

`xcheck` runs both extractors on each file and prints a table of what each one found (entity counts, tables, cells, evaluated cells, attributes, cells whose text differs). A file that one extractor could not read shows its reason under the table. It exits 2 only when no extractor read any file.

## AutoCAD Electrical project files

A `.wdp` project file is read as a list of the drawings it names. The drawings themselves are not opened, and no path inside the file is followed. `.mdb` and `.accdb` project databases are listed as "not read: unsupported file type".

## Exit codes

- 0 (the run exits 0): the run completed. Findings do not change the code, because Redline screens and does not gate.
- 2 (the run exits 2): a config failure, an unreadable or invalid demo project, no input given, no input file that could be read, or an `--out` that would overwrite an input. One line on stderr says which.

A file that was read but held no panel still exits 0. The report is written and lists the file as "no panel read".

## The TEST banner

A report that opens with "TEST EDITION, NOT CEC" was run on the test config. Its numbers are made up
for testing and are not Canadian Electrical Code values. Do not use such a report for review.
