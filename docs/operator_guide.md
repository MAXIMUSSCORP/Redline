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

## Exit codes

- 0 (the run exits 0): the run completed. Findings do not change the code, because Redline screens and does not gate.
- 2 (the run exits 2): a config failure, an unreadable or invalid demo project, no input given, no input file that could be read, or an `--out` that would overwrite an input. One line on stderr says which.

A file that was read but held no panel still exits 0. The report is written and lists the file as "no panel read".

## The TEST banner

A report that opens with "TEST EDITION, NOT CEC" was run on the test config. Its numbers are made up
for testing and are not Canadian Electrical Code values. Do not use such a report for review.
