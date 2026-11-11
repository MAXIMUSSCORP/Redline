# M1 real-file research: AutoCAD Electrical and Revit exports

Date: 2026-11-07, M1 research. Three searches gathered this, two on the web and one on the dev PC. No code was written. VERIFIED means the claim was read on the cited page. UNVERIFIED means it came from a search snippet or an inference. Decision: PLAN.md row 33.

## 1. AutoCAD Electrical

- No public per-circuit panel schedule export was found. AutoCAD Electrical reports are component lists, wire lists, BOMs and connector lists. None has a phase or load type column. VERIFIED:
  - Component fields: https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-D90536AC-6035-4B87-B138-1069F8728251.htm (ITEM, TAGNAME, CNT, UNITS, MFG, CAT, DESC1-3, LOC, INST, RATING1-12, ...).
  - Wire list fields: https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-E40F691A-2ED0-4D6F-A342-FE9366E5B271.htm (WIRENO, PIN, TAGNAME, ... ; the catalog field is CATALOG here and CAT in the component list).
- Report output types: ASCII, CSV, XLS, MDB and XML. The fields chosen are saved in `.set` format files. Export to Spreadsheet (AEEXPORT2SS) writes one sheet per data category. https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-89F4039D-2864-45E8-9B87-B98ED6F00B65.htm. VERIFIED.
- AutoCAD Electrical cannot produce an MEP or Revit-style panel schedule. UNVERIFIED: a forum thread summary only (https://forums.autodesk.com/t5/autocad-electrical-forum/electrical-one-line-diagrams/m-p/5636602), and the page returned 403.
- Block attributes named CKT, DESC or LOAD: not found on any Autodesk page. Do not assume them.
- Dev PC: AutoCAD Electrical is not installed. `D:\Autodesk` has AutoCAD 2026 and Revit 2026 only. No `.wdp`, `.set`, WDDEMO or panel template exists on C: or D:.
- Consequence: `aecad_export.headers` stays empty, and every AutoCAD Electrical column goes to `unparsed`.

## 2. AutoCAD MEP (a different product, for reference only)

AutoCAD MEP panel schedule table-style circuit fields: Circuit Name, Circuit Description, Circuit Total Load, Circuit Rating, Circuit Voltage, Circuit Number of Poles, Circuit Phase, Circuit Load Category, Circuit Load Phase A/B/C, Circuit Amps. https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-MEP/files/GUID-FB5180B1-B103-4C84-9DFD-6D5AC729668D.htm. VERIFIED as field codes, not as an exported header row.

## 3. Revit 2026, the M1 real-file source

- No Autodesk page documents a native export of a panel schedule view (2024 to 2026). The panel schedule overview and the create page never mention export. VERIFIED: https://help.autodesk.com/cloudhelp/2026/ENU/Revit-DocumentPresent/files/GUID-3D2D0E77-ED17-4FBF-AAE4-CB9185A3F779.htm
- File > Export > Reports > Schedule writes delimited text from a regular schedule. Its options:
  - Delimiter: tab, space, comma or semicolon.
  - Text qualifier.
  - Header rows: "One row" or "Multiple rows, as formatted".
  - Group headers, footers and blank lines: on or off.
  VERIFIED: https://help.autodesk.com/cloudhelp/2026/ENU/Revit-DocumentPresent/files/GUID-B2CCAC4F-1D38-4D5D-B4D1-95619D1B7EBE.htm. Forum snippets say the command is greyed out on a panel schedule view (UNVERIFIED for 2026).
- Circuit parameters, VERIFIED (https://help.autodesk.com/cloudhelp/2026/ENU/Revit-MEPEng/files/GUID-BDD3D7A7-0558-42E2-8B32-D87520891969.htm): Circuit Number, Panel, Load Name, Rating, Number of Poles, Voltage, Frame, Load Classification, Apparent Power, Phase Label, Cable Type.
  - Load type: **Load Classification**.
  - Phase: no circuit field named Phase. **Phase Label** labels circuits together with the Way parameter. In a panel schedule view, phase shows as per-phase load columns (A, B, C).
- Panel schedule templates can be "Two Columns" or "Circuits Across", and firms edit the column labels. VERIFIED: https://help.autodesk.com/cloudhelp/2023/ENU/Revit-DocumentPresent/files/GUID-9522EA21-AC96-409A-86E8-4B99826E191B.htm

### Second search, M1 stage 4 (2026-11-07)

Three searches ran again: two on the web, one on the dev PC (read-only). Nothing was downloaded or opened.

- No public file holds a real Revit-written circuit schedule export. GitHub code search, the Autodesk, Dynamo and Reddit forums and add-in docs gave only parameter lists, API code and screenshots. VERIFIED as searched. A schedule's columns are whatever fields its author picks, so no standard header row exists to find.
  - Two old threads may carry an attached export, but both returned 403: https://forums.augi.com/showthread.php?128633-Extracting-circuits-data-from-model and https://www.revitforum.org/forum/revit-mechanical-electrical-plumbing-forum-mep/mep-general/31517-electrical-panel-schedule-export-to-excel-revit-2016. UNVERIFIED.
- Sample models are already on the dev PC under `D:\Autodesk\Revit 2026\Samples\`. VERIFIED by listing:
  - `Snowdon Towers Sample Electrical.rvt`, 41.6 MB. Best candidate.
  - `BIM_Projekt_Golden_Nugget-Gebaeudetechnik.rvt`, 96.5 MB (German MEP). Second project.
  - `サンプル設備.rvt`, 92.8 MB (Japanese MEP).
  - Whether they hold panels and circuits is UNVERIFIED. The Autodesk sample page says only "Electrical fixtures, equipment and conduits are all featured": https://help.autodesk.com/cloudhelp/2026/ENU/Revit-GetStarted/files/GUID-61EF2F22-3A1F-4317-B925-1E85F138BE88.htm
- The rme_basic and rme_advanced MEP samples are listed for 2026 on that page but are not installed here. VERIFIED as listed.
- Electrical and Systems project templates (.rte) are under `D:\Autodesk\RVT 2026\Templates\`. They hold schedule definitions but no circuits.
- No Autodesk page states terms of use for the samples or for exports made from them. Until the owner decides, treat such exports as client files (row 34 D2): `gold/revit/`, not committed.
- An export from an Autodesk sample meets L1.6 G6.1 only if the owner adopts it as theirs.

### Steps for the owner

1. Open a panel schedule view, then File > Export > Reports > Schedule. If that works, keep the file. It shows the real panel layout.
2. If the command is greyed out, create View > Schedules > Schedule/Quantities, category Electrical Circuits. Add these fields: Panel, Circuit Number, Load Name, Rating, Number of Poles, Voltage, Load Classification, Apparent Power, Phase Label. Sort by Panel, then by Circuit Number.
3. With that schedule open, run File > Export > Reports > Schedule with these settings:
   - Comma delimiter and double-quote qualifier.
   - "One row" headers.
   - No group headers, footers or blank lines.
4. Export 2 to 3 projects. Panel header data (voltage, phases, mains, fed from) is not in a circuits schedule. An Electrical Equipment schedule export can carry it.
5. Put the files in `samples/revit/`. If they are client files, say so, and they go in a gitignored folder instead.

## 4. Points for the stage 2 plan

- Revit writes `.txt`, not `.csv`. The plan decides whether the parser accepts `.txt` delimited files or the owner renames them.
- Revit's text encoding is not documented. Read with an explicit encoding and a fallback.
- A circuits-schedule export has no phase column. Phase comes from Phase Label, from a template with per-phase columns, or stays MISSING, which makes phase balance NEEDS_REVIEW.
- The plan still carries PLAN.md row 31 (NEEDS_REVIEW for a spare circuit with a load) as a gate.
