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

## Use

    redline check samples/csv --config tests/test_config/ --out report.html

This writes `report.html` and `findings.csv`. Setup, exit codes and options are in `docs/operator_guide.md`. The plan is `docs/PLAN.md`.
