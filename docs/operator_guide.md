# Operator guide

## Setup

The venv lives outside OneDrive, at `%LOCALAPPDATA%\redline\venv`. Install from the repo root:

    %LOCALAPPDATA%\redline\venv\Scripts\python.exe -m pip install -e ".[dev]"

## Run the demo

    redline check --demo-project tests/golden/demo_project.json --config tests/test_config/ --out report.html

This writes `report.html` and, beside it, `findings.csv`. Add `--skip-rule ID` to leave a rule out; it is listed in the report as not run.
Use `--config config/` for the real skeleton config. Every VIOLATION is then shown as NEEDS_REVIEW, because no table is verified.

## Exit codes

- 0: the run completed. Findings do not change the code, because Redline screens and does not gate.
- 2: a config failure, an unreadable or invalid demo project, or no input. One line on stderr says which.

## The TEST banner

A report that opens with "TEST EDITION, NOT CEC" was run on the test config. Its numbers are made up
for testing and are not Canadian Electrical Code values. Do not use such a report for review.
