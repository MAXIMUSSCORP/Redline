# Redline

Redline screens building electrical design packages for a qualified reviewer. It never approves a package, never guesses, and never supplies a CEC value. Every code value comes from the owner's config.

## Inputs

| Source | Status |
|---|---|
| CSV, TXT and XLSX panel schedules | Built (M1) |
| AutoCAD DWG and DXF | Built (M2) |
| PDF drawing sets | Built (M3, real sheets not yet tested) |
| Plan sheets (DXF and DWG): device blocks, `exits.csv`, `paths.csv`, fire alarm checks | Built (M5, synthetic sheets only, no limit supplied) |
| Revit | Coming soon |

Revit exports are not supported yet. Revit support is coming soon (`docs/PLAN.md` row 35).

## Install

    python -m venv %LOCALAPPDATA%\redline\venv
    %LOCALAPPDATA%\redline\venv\Scripts\python.exe -m pip install . -c constraints.txt

Add `".[dxf]"` for DXF and ODA drawings and `".[pdf]"` for PDF sheets. Steps for a new machine are in `docs/operator_guide.md`.

## Use

    redline check samples/csv --config tests/test_config/ --out report.html

This writes `report.html` and `findings.csv`. Three more commands:

    redline doctor --config config/
    redline gold eval samples/gold/tables --config tests/test_config/
    redline xcheck --batch drawings/ --config config/ --out xcheck-out

`doctor` checks the machine and prints PASS, WARN, FAIL or NOT CHECKED per line. `gold eval` counts how many cells the readers get right against a transcribed set. `xcheck --batch` compares the two DWG extractors over many drawings. Setup, exit codes and options are in `docs/operator_guide.md`. The release checklist is `docs/release_checklist.md`. The plan is `docs/PLAN.md`.
