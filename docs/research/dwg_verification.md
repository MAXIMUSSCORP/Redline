# DWG extractor verification on the dev PC

Leaf L2.0, written 2026-11-09 on the Windows 11 dev PC, from a shell inside the MSIX-packaged Claude app. Rev 3 re-run (PLAN row 42). Every figure below was measured here. Anything not measured is marked UNVERIFIED or BLOCKED with its reason.

Headline: the AutoCAD 2026 `accoreconsole.exe` crashes in `AcPal.dll` (history, row 41, kept below). The AutoCAD 2027 `accoreconsole.exe` runs: both smoke tests exit 0 in about 2 s with no licence dialog. ODA File Converter 27.10.0 converts DWG to DXF and ezdxf reads the result. The 2026 results are history only.

## 1. Find the exe (M2.3 task 1)

- Path: `D:/Autodesk/AutoCAD 2026/accoreconsole.exe`, 504152 bytes, dated 2025-10-24.
- File version 25.1.122.0.0, product name `AcCoreConsole`. The banner reads "AutoCAD Core Engine Console - Copyright 2025 Autodesk, Inc. (W.122.0.0)".
- Search: `find "C:/Program Files/Autodesk" "D:/Autodesk" -maxdepth 4 -iname accoreconsole.exe` returned only the D: path. `C:/Program Files/Autodesk` does not exist on this PC.
- `D:/Autodesk` holds AutoCAD 2026 and several Revit 2026 items. No AutoCAD Electrical folder exists, which matches CLAUDE.md section 9.

### Rev 3 (2027): the core console now used

- Path: `C:/Program Files/Autodesk/AutoCAD 2027/accoreconsole.exe`. Core console version 26.0.60 (as given in the contract).
- It replaces the 2026 exe above, which crashes on this PC. The 2026 text above is kept as history.

## 2. Smoke test, in place or copy, MSIX probe (M2.3 task 2)

### Originals

| Role | Original (read only) | Bytes | SHA-256 before | SHA-256 after |
|---|---|---|---|---|
| Plain | `gold/dwg/etsu_entc2160_m04/Tiny Electrical Plan.dwg` | 555671 | `fab65f216b13e69195b5dd7c70ad400e9d2827db6564a6e760e6dd2b46bf68e6` | `fab65f216b13e69195b5dd7c70ad400e9d2827db6564a6e760e6dd2b46bf68e6` |
| AutoCAD Electrical sample | `gold/dwg/ace_sample_projects/x/aceSampleProjects-master/Demo/DEMO01.DWG` | 155048 | `25580d3aa2f27ad3aadda2ab12a1962859cd6bf7fd9fca836f37bd4d97fd7db2` | `25580d3aa2f27ad3aadda2ab12a1962859cd6bf7fd9fca836f37bd4d97fd7db2` |

Both originals are unchanged after the 2027 runs and the earlier 2026 runs. The DEMO01 header reads `AC1024` (DWG 2010). DEMO01 holds one `WD_M` block (section 7).

### Command (AutoCAD 2027, rev 3)

Script `q.scr` holds one line, `_QUIT`. Each run used a copy in its own empty folder under `%TEMP%\redline-m2\L2.0\`, stdin from DEVNULL, a 240 s timeout, current directory the temp folder. Exact command:

```
"C:\Program Files\Autodesk\AutoCAD 2027\accoreconsole.exe" /i "<temp>\s27_etsu\etsu.dwg" /s "<temp>\q.scr" /l en-US
```

`<temp>` is `C:\Users\Zaidz\AppData\Local\Temp\redline-m2\L2.0`.

### Result (2027): both runs complete

| Drawing (source file) | Exit code | Wall time | Licence dialog or prompt |
|---|---|---|---|
| ETSU copy (`Tiny Electrical Plan.dwg`) | 0 | 2.72 s | none |
| DEMO01 copy (`DEMO01.DWG`) | 0 | 2.21 s | none |

The output (UTF-16 text) shows "Regenerating model", one "System Variable Changed" notice (1 monitored variable differs from the preferred value, SYSVARMONITOR), "AutoCAD menu utilities loaded", the echoed `_QUIT`, and "LogFilePath has been restored". No sign-in or licence prompt appeared. No `accoreconsole.exe` process remained afterwards (process count 0). No setting, SECURELOAD or TRUSTEDPATHS was changed.

### History: AutoCAD 2026 result (row 41), crash

The 2026 exe `D:/Autodesk/AutoCAD 2026/accoreconsole.exe` (script `t.scr` with `_QSAVE`, 240 s limit, stdin closed) crashed every time:

| Drawing | Exit code | Wall time | Licence dialog or prompt |
|---|---|---|---|
| ETSU copy | -1073741819 (0xC0000005) | 1.84 s | none seen |
| DEMO01 copy | -1073741819 (0xC0000005) | 1.38 s | none seen |

Tried with the same crash: Git Bash with stdin from `/dev/null`, .NET `Process`, `cmd /c` with `< nul`, no script or drawing (`/?`), and the user's own Terminal panel. Windows Application log event 1000: faulting module `AcPal.dll` 25.1.122.0, exception 0xc0000005, offset 0x1feda, identical every time. Candidate cause, UNVERIFIED: AutoCAD 2026 never started on this PC.

### Run in place or on a copy

Measured with the 2027 core console, on copies of ETSU in empty folders (one folder per run):

| Script | Switch | Files in folder after | Hash of the .dwg |
|---|---|---|---|
| `_QUIT` (also the DEMO01 run) | none | `.dwg` only | equal |
| `_QUIT` | `/readonly` | `.dwg` only | equal |
| `_QSAVE` | none | `.bak` and `.dwg` | changed |
| `_QSAVE` | `/readonly` | `.dwg` only | equal |

- Files seen beside the drawing before the run: the copied `.dwg` only. After a `_QUIT` run: the same, no `.dwl`, `.dwl2` or `.bak`. A lock file during the run was not looked for (UNVERIFIED).
- Hash result: unchanged for `_QUIT` and for `/readonly`. A save writes a `.bak` and changes the file.
- `/readonly`: accepted. Exit 0 with `_QUIT` and with `_QSAVE`. With `_QSAVE` it saved nothing (no `.bak`, same hash). Whether it also stops lock files being created during the run is UNVERIFIED.
- Decision: **on a copy**. A quit-only run writes nothing after exit, but the extractor script is not a quit-only script, a lock file during the run is not ruled out, and a copy keeps the client drawing out of any write path. Unresolved xrefs are then listed, never dropped. `/readonly` is accepted and may be passed on the copy as well.

### MSIX probe

A 2027 core console script ran `(open "C:/Users/Zaidz/AppData/Local/redline/l20_acc_probe.txt" "w")`, `write-line`, `close`, then `_QUIT` (exit 0).

- Path written: `C:/Users/Zaidz/AppData/Local/redline/l20_acc_probe.txt`.
- The redline venv python saw it at that path: `os.path.exists` True, content read back.
- The same file was also visible at `C:/Users/Zaidz/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/redline/l20_acc_probe.txt`, and that folder lists the same entries as the plain path (`venv`, `wt`). Inside the Claude app shell the two paths show one folder.
- Where the bytes physically sit, and whether a process outside the app sees the plain path, is UNVERIFIED (every process here runs under the app). The probe file was deleted afterwards.

History, 2026 era: the probe could not run through the core console; PowerShell and the venv python showed the same one-folder behaviour. For the plugin DLL path see `extractors/acad_plugin/README.md` (leaf L2.1).

## 3. Core Console licensing (M2.3 task 3)

BLOCKED: owner. The owner asks the reseller in writing whether headless Core Console use on a shared machine is allowed, and checks seat use in the Autodesk account. The answer is quoted here when given (D10). Until then, run only on the named user's own workstation.

Run-with-AutoCAD-closed versus open: UNVERIFIED, not measured in the 2027 re-run. The 2026 crash decision is moot under rev 3 (the 2027 core console runs).

## 4. NETLOAD on 2025 and later (M2.3 task 4)

Owned by leaf L2.1. See `extractors/acad_plugin/README.md`, section "Load test". Note for L2.1: the 2026 Core Console crashed before any command ran (section 2); the 2027 one runs, so the NETLOAD test can start there (rev 3).

## 5. FIELD and DATALINK evaluation (M2.3 task 5)

BLOCKED: owner. It needs a DWG with a plain table, a FIELD table and a DATALINK table, authored by the owner. Leaf L2.7 runs the comparison once that file exists.

## 6. ODA File Converter (M2.3 task 6)

- Path: `C:/Program Files/ODA/ODAFileConverter 27.10.0/ODAFileConverter.exe`. Version 27.10.0 (file version 27.10.0.0).
- ezdxf 1.4.5. Before the option was set, `ezdxf.addons.odafc.is_installed()` returned `False` (the default path has no version folder). Then `ezdxf.options.set("odafc-addon", "win_exec_path", <that path>)` was set, and `is_installed()` returned `True`.
- Conversion of the ETSU copy to DXF (`odafc.convert`, version R2018, no audit): 0.40 s, output 2692566 bytes.
- History: the first run of this leaf found ODA not installed (row 38).

## 7. Electrical project folder (M2.3 task 7)

Counts under `gold/dwg`, measured with `find` on 2026-11-09:

- `.wdp` count: 20 (.wdp files).
- `.mdb`: 3 (`H-S244test/H-S244test_cat.mdb`, `MEE-AE0010_PLC-Modules/.../ace_plc.mdb`, `.../PLC_Modules_NFPA_update.mdb`).
- `.accdb`: 0.
- `WD.ENV`: 0.
- `.dxf`: 0.

Database tables and columns were not listed, since no reader is approved (D1).

### WD_M attribute tags

Drawing: `DEMO01.DWG` (the first Demo drawing tried; a temp copy converted with ODA 27.10.0 to R2018 DXF, read with ezdxf 1.4.5). Its model space holds 1 `WD_M` INSERT. Attribute tags, TAGS ONLY, count 77. No attribute value was written here:

`ALT_XREFFMT`, `ARROW_STYLE`, `CDESC_LAY`, `CHAR_H`, `CHAR_V`, `COMP_LAY`, `CXREF_LAY`, `DATUMX`, `DATUMY`, `DESC_LAY`, `DISTH`, `DISTV`, `DLADW`, `DRWRUNG`, `FAN_INOUT_LAYS`, `FAN_INOUT_STYLE`, `FEATURE_SCL`, `GAP_STYLE`, `HORIZ_FIRST`, `IEC_INST`, `IEC_LOC`, `IEC_PROJ`, `LINK_LAY`, `LOCBOX_LAY`, `LOC_LAY`, `MISC_DATA`, `MISC_FLAGS`, `MISC_LAY`, `PH3SPACE`, `PLC_STYLE`, `POS_LAY`, `REFNUMS`, `RUNGDIST`, `RUNGHORV`, `RUNGINC`, `SHEET`, `SHEETDWGNAME`, `SORTMODE`, `TAG-RSUF`, `TAG-START`, `TAGFIXED_LAY`, `TAGFMT`, `TAGMODE`, `TAG_LAY`, `TERM_LAY`, `UNIT_SCL`, `WINC`, `WIRE-RSUF`, `WIRE-START`, `WIRECOPY_LAY`, `WIREFIXED_LAY`, `WIREFMT`, `WIRELAYS`, `WIREMODE`, `WIRENO_LAY`, `WIREREF_LAY`, `WLEADERS`, `WNUM_FLAGS`, `WNUM_GAP`, `WNUM_OFFSET`, `XREFFMT`, `XREF_CONTACTMAP`, `XREF_FILLWITH`, `XREF_FLAGS`, `XREF_GRAPHIC`, `XREF_GRAPHICSTYLE`, `XREF_LAY`, `XREF_SORT`, `XREF_STYLE`, `XREF_TBLCOLJUST`, `XREF_TBLFLDNAMS`, `XREF_TBLINDEX`, `XREF_TBLSTYLE`, `XREF_TBLTITLE`, `XREF_TXTBTWN`, `XREF_UNUSEDSTYLE`, `XY_DELIM`

Other Demo drawings were not tried, since the first one has the block.

### Staff questions

The questions on staff AutoCAD versions and how schedules are made go to the owner (C10). No answers yet.

## 8. xcheck corpus run and real-file checks

Leaf L2.7, run 2026-11-09 on the dev PC, main checkout, branch m2. Every figure was measured here. The `acad_plugin` extractor cannot load yet (AutoCAD 2027 SECURELOAD is 1 and TRUSTEDPATHS is empty, D10), so every `acad_plugin` column below reads `not run` and `oda_ezdxf` is the extractor that read each drawing. Gates G7.1 and G7.3 are BLOCKED on D10 and were not worked around. No AutoCAD setting was changed.

### panel_sheet.dwg, fallback against its fixture (G7.4)

Run 2026-11-09: `oda_ezdxf` on a temp copy of `samples/dwg/panel_sheet.dwg` (1.18 s), compared with `samples/dwg/panel_sheet.oda_ezdxf.rawdrawing.json`. Tables are matched by size, since the fixture handles are invented.

| Item | Live dump | Fixture |
|---|---|---|
| Tables | 2: LP-11 (22 x 14, 308 cells, handle 2EB) and LP-12 (8 x 6, 48 cells, handle 429) | 3: the same two (handles 2F01, 2F02) and a legend table (5 cells, no row or column count) |
| Cells compared | 356 (308 + 48), same (r, c) keys | 356 of 361 |
| `evaluated` | false in all 356 | true in 350, false in the 6 LP-12 cells |
| Cell text | identical in 344 of 356 | see below |

Differences:

1. Six cells in column 2, rows 2 to 7, of both LP-11 and LP-12 (12 cells) read as empty text. The fixture holds a number in each (and `TBD` in one LP-11 cell). The numbers in the fixture also differ from the field expressions in the real drawing (LP-11 fixture 1350, 1500, 1650, 1800, TBD, 2100; the real field expressions are 1350, 1500, 1800, 2100, 2400, 2700).
2. `evaluated` is false for every live cell. The fixture marks the plain cells true. The live value follows `oda_ezdxf.py` (every fallback cell is false until the FIELD check is shown right, D4), so the fixture and the extractor disagree on 350 cells.
3. The legend table with no row or column count (fixture handle 2F2E) is absent. AutoCAD cannot draw a table without a count. Known difference, not a defect.
4. The live dump also holds the anonymous table blocks `*T2` and `*T3` as extra layouts: 317 MTEXT and 56 LINE entities that repeat the table text. The fixture has 1 LINE and no MTEXT. The ACAD_TABLE entities are also present in E-101, so each table is seen twice, and `redline check` reports "panel name LP-11 is read 2 times" and the same for LP-12. Live entity types: TEXT 43, MTEXT 317, LINE 57, INSERT 3 (WD_M, RECEPT, A-BASE), ACAD_TABLE 2, POLYLINE 1.

What ezdxf gives for the FIELD cells: the cell value is empty. The cell tag holds only a handle (code 344) to a FIELD object whose own text is the placeholder `%<\_FldIdx 0>%`. The evaluated result is cached on a child FIELD object, and `read_acad_table_content` never follows the handle. Cached results in this drawing: LP-11 uses AcExpr fields and the cache holds 1350, 1500, 1800, 2100, 2400, 2700. LP-12 uses AcDiesel fields and the cache holds `####` in all six (the field did not evaluate in the file). So a reader that follows 344 to the child's cache gets numbers for LP-11 and `####` for LP-12. The six cells in each table stay `evaluated: false` and LOW, which is correct, but the text is lost.

Fix or fixture requests: (a) L2.2, read the cached FIELD result through the cell's 344 handle, keep `evaluated` false, and record `####` as a failed field, instead of returning empty text; (b) L2.5, the fixture should show empty text for the FIELD cells and `evaluated: false` for every fallback cell, to match the extractor; (c) L2.3, skip the `*T` block text of a table whose ACAD_TABLE entity has a row and column count, so a panel is not read twice.

### Loss table over 14 real drawings (G7.7)

`redline xcheck` works on a temp copy: both extractors copy the drawing into their own temp folder, and the SHA-256 of each original was equal before and after every run. The call was `xcheck.run` (the code path behind `redline xcheck`) with a timer around each extractor. Time is wall seconds. The `acad_plugin` time is the failed attempt (the console starts, then the plugin does not load).

| Drawing | DWG version | Bytes | Extractor used | oda_ezdxf time | acad_plugin attempt | Original unchanged |
|---|---|---|---|---|---|---|
| Tiny Electrical Plan.dwg | AC1032 | 555671 | oda_ezdxf (acad_plugin not run) | 1.39 s | 2.52 s | yes |
| Electric Symbols.dwg | AC1032 | 550639 | oda_ezdxf (acad_plugin not run) | 0.67 s | 2.02 s | yes |
| final_drawing_P003-B.dwg | AC1032 | 92498 | oda_ezdxf (acad_plugin not run) | 0.48 s | 2.03 s | yes |
| 2340-000-EA-007.dwg | AC1015 | 59349 | oda_ezdxf (acad_plugin not run) | 0.4 s | 2.0 s | yes |
| S244_HQ037_1.dwg | AC1021 | 289248 | oda_ezdxf (acad_plugin not run) | 0.95 s | 2.03 s | yes |
| DEMO01.DWG | AC1024 | 155048 | oda_ezdxf (acad_plugin not run) | 0.65 s | 2.03 s | yes |
| DEMO08.DWG | AC1024 | 115108 | oda_ezdxf (acad_plugin not run) | 0.53 s | 2.0 s | yes |
| 019.dwg | AC1024 | 139826 | oda_ezdxf (acad_plugin not run) | 0.57 s | 1.99 s | yes |
| 025.dwg | AC1024 | 246712 | oda_ezdxf (acad_plugin not run) | 0.95 s | 2.03 s | yes |
| T04.dwg | AC1024 | 109002 | oda_ezdxf (acad_plugin not run) | 0.51 s | 1.99 s | yes |
| Project_Basics_NFPA_05.dwg | AC1027 | 93052 | oda_ezdxf (acad_plugin not run) | 0.61 s | 2.01 s | yes |
| PLC_Module_NFPA_05.dwg | AC1027 | 85425 | oda_ezdxf (acad_plugin not run) | 0.57 s | 1.99 s | yes |
| AU_2019_NFPA_05.dwg | AC1032 | 84615 | oda_ezdxf (acad_plugin not run) | 0.54 s | 2.0 s | yes |
| HDV1_IconMenu.dwg | AC1021 | 56096 | oda_ezdxf (acad_plugin not run) | 0.36 s | 1.87 s | yes |

Versions covered: AC1015, AC1021, AC1024, AC1027, AC1032. Projects: ETSU, P003-B, perf_2340, H-S244test, Demo, NfpaDemo, IeeeDemo, JisDemo, GbDemo, and three Autodesk Learn courses. No table or cell was read by `oda_ezdxf` in any of the 14 drawings (tables 0, cells 0), as expected for AutoCAD Electrical schematics and plans.

Loss tables, one block per drawing:

```
file                      item             acad_plugin  oda_ezdxf
Tiny Electrical Plan.dwg  INSERT               not run         34
Tiny Electrical Plan.dwg  LINE                 not run        875
Tiny Electrical Plan.dwg  MTEXT                not run         30
Tiny Electrical Plan.dwg  POLYLINE             not run          5
Tiny Electrical Plan.dwg  tables               not run          0
Tiny Electrical Plan.dwg  cells                not run          0
Tiny Electrical Plan.dwg  cells evaluated      not run          0
Tiny Electrical Plan.dwg  attributes           not run          0

Tiny Electrical Plan.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file                  item             acad_plugin  oda_ezdxf
Electric Symbols.dwg  LINE                 not run        197
Electric Symbols.dwg  MTEXT                not run         45
Electric Symbols.dwg  POLYLINE             not run         42
Electric Symbols.dwg  tables               not run          0
Electric Symbols.dwg  cells                not run          0
Electric Symbols.dwg  cells evaluated      not run          0
Electric Symbols.dwg  attributes           not run          0

Electric Symbols.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file                      item             acad_plugin  oda_ezdxf
final_drawing_P003-B.dwg  INSERT               not run         81
final_drawing_P003-B.dwg  LINE                 not run        292
final_drawing_P003-B.dwg  MTEXT                not run         12
final_drawing_P003-B.dwg  POLYLINE             not run        191
final_drawing_P003-B.dwg  TEXT                 not run        819
final_drawing_P003-B.dwg  tables               not run          0
final_drawing_P003-B.dwg  cells                not run          0
final_drawing_P003-B.dwg  cells evaluated      not run          0
final_drawing_P003-B.dwg  attributes           not run        162

final_drawing_P003-B.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file                 item             acad_plugin  oda_ezdxf
2340-000-EA-007.dwg  INSERT               not run          3
2340-000-EA-007.dwg  LINE                 not run         13
2340-000-EA-007.dwg  MTEXT                not run          2
2340-000-EA-007.dwg  POLYLINE             not run          1
2340-000-EA-007.dwg  TEXT                 not run         18
2340-000-EA-007.dwg  tables               not run          0
2340-000-EA-007.dwg  cells                not run          0
2340-000-EA-007.dwg  cells evaluated      not run          0
2340-000-EA-007.dwg  attributes           not run        162

2340-000-EA-007.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file              item             acad_plugin  oda_ezdxf
S244_HQ037_1.dwg  ACAD_TABLE           not run          3
S244_HQ037_1.dwg  INSERT               not run        100
S244_HQ037_1.dwg  LINE                 not run       1973
S244_HQ037_1.dwg  MTEXT                not run         75
S244_HQ037_1.dwg  POLYLINE             not run         33
S244_HQ037_1.dwg  TEXT                 not run         52
S244_HQ037_1.dwg  tables               not run          3
S244_HQ037_1.dwg  cells                not run         92
S244_HQ037_1.dwg  cells evaluated      not run          0
S244_HQ037_1.dwg  attributes           not run       1063

S244_HQ037_1.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file        item             acad_plugin  oda_ezdxf
DEMO01.DWG  ACAD_TABLE           not run          2
DEMO01.DWG  INSERT               not run         27
DEMO01.DWG  LINE                 not run        414
DEMO01.DWG  MTEXT                not run        245
DEMO01.DWG  POLYLINE             not run         87
DEMO01.DWG  TEXT                 not run         26
DEMO01.DWG  tables               not run          2
DEMO01.DWG  cells                not run        294
DEMO01.DWG  cells evaluated      not run          0
DEMO01.DWG  attributes           not run        347

DEMO01.DWG: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file        item             acad_plugin  oda_ezdxf
DEMO08.DWG  ACAD_TABLE           not run          1
DEMO08.DWG  INSERT               not run         46
DEMO08.DWG  LINE                 not run        136
DEMO08.DWG  MTEXT                not run         40
DEMO08.DWG  POLYLINE             not run         40
DEMO08.DWG  TEXT                 not run         18
DEMO08.DWG  tables               not run          1
DEMO08.DWG  cells                not run         40
DEMO08.DWG  cells evaluated      not run          0
DEMO08.DWG  attributes           not run        251

DEMO08.DWG: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file     item             acad_plugin  oda_ezdxf
019.dwg  INSERT               not run         51
019.dwg  LINE                 not run        189
019.dwg  POLYLINE             not run         39
019.dwg  TEXT                 not run         28
019.dwg  tables               not run          0
019.dwg  cells                not run          0
019.dwg  cells evaluated      not run          0
019.dwg  attributes           not run        834

019.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file     item             acad_plugin  oda_ezdxf
025.dwg  INSERT               not run        153
025.dwg  LINE                 not run        597
025.dwg  POLYLINE             not run        137
025.dwg  TEXT                 not run         74
025.dwg  tables               not run          0
025.dwg  cells                not run          0
025.dwg  cells evaluated      not run          0
025.dwg  attributes           not run       2690

025.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file     item             acad_plugin  oda_ezdxf
T04.dwg  INSERT               not run         17
T04.dwg  LINE                 not run        161
T04.dwg  MTEXT                not run          1
T04.dwg  POLYLINE             not run          1
T04.dwg  TEXT                 not run         84
T04.dwg  tables               not run          0
T04.dwg  cells                not run          0
T04.dwg  cells evaluated      not run          0
T04.dwg  attributes           not run        344

T04.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file                        item             acad_plugin  oda_ezdxf
Project_Basics_NFPA_05.dwg  INSERT               not run         49
Project_Basics_NFPA_05.dwg  LINE                 not run        204
Project_Basics_NFPA_05.dwg  POLYLINE             not run         30
Project_Basics_NFPA_05.dwg  TEXT                 not run         31
Project_Basics_NFPA_05.dwg  tables               not run          0
Project_Basics_NFPA_05.dwg  cells                not run          0
Project_Basics_NFPA_05.dwg  cells evaluated      not run          0
Project_Basics_NFPA_05.dwg  attributes           not run        774

Project_Basics_NFPA_05.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file                    item             acad_plugin  oda_ezdxf
PLC_Module_NFPA_05.dwg  INSERT               not run         58
PLC_Module_NFPA_05.dwg  LINE                 not run        137
PLC_Module_NFPA_05.dwg  POLYLINE             not run         30
PLC_Module_NFPA_05.dwg  TEXT                 not run         31
PLC_Module_NFPA_05.dwg  tables               not run          0
PLC_Module_NFPA_05.dwg  cells                not run          0
PLC_Module_NFPA_05.dwg  cells evaluated      not run          0
PLC_Module_NFPA_05.dwg  attributes           not run        690

PLC_Module_NFPA_05.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file                 item             acad_plugin  oda_ezdxf
AU_2019_NFPA_05.dwg  INSERT               not run         58
AU_2019_NFPA_05.dwg  LINE                 not run        137
AU_2019_NFPA_05.dwg  POLYLINE             not run         30
AU_2019_NFPA_05.dwg  TEXT                 not run         31
AU_2019_NFPA_05.dwg  tables               not run          0
AU_2019_NFPA_05.dwg  cells                not run          0
AU_2019_NFPA_05.dwg  cells evaluated      not run          0
AU_2019_NFPA_05.dwg  attributes           not run        690

AU_2019_NFPA_05.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

```
file               item             acad_plugin  oda_ezdxf
HDV1_IconMenu.dwg  POLYLINE             not run          1
HDV1_IconMenu.dwg  tables               not run          0
HDV1_IconMenu.dwg  cells                not run          0
HDV1_IconMenu.dwg  cells evaluated      not run          0
HDV1_IconMenu.dwg  attributes           not run          0

HDV1_IconMenu.dwg: acad_plugin read nothing: ExtractError: AutoCAD Core Console wrote no output file
```

### final_drawing_P003-B.dwg, panel P1 (G7.8)

Run 2026-11-09: `redline check` on a temp copy of `gold/dwg/arjunb3hl_p003b/final_drawing_P003-B.dwg` with the real config (exit 0, extractor `oda_ezdxf` 0.1.0).

1. Was panel P1 read: no. The report holds 0 panels. The extractor read 0 tables and 3 loose-text clusters (layouts E-201, E-301, E-401, plus text in Model), and listed them as not read.
2. Confidence: none. The coverage line reads HIGH 0, MEDIUM 0, LOW 0, MISSING 0. No value was read, so there is nothing to grade.
3. Circuit count: 0 read against 19 in `model_P003-B.json` (1 panel, 19 circuits). The E-201 schedule has 30 slots; each row was listed with the reason "no circuit number".

Why: in the E-201 header, `SLOT`, `I A`, `L M`, `VD %` and `CHECK` have no alias in `csv_panel_schedule`, one header has no text, and two pairs map to one field (`PH` and `PER-PHASE TOTALS`; `DEV LOAD W` and `LOAD VA`). Proposal for `config/column_maps.yaml` (not edited here): an alias `slot` for `circuit_number` once the owner confirms SLOT is the circuit position, and aliases for current, length and voltage drop only if those fields exist in the model. The side-by-side totals block on the same row also needs a rule for the duplicate-column case. Owner decision.

### WD_M tags (G7.9, answer open)

Tags only, no values. 10 AutoCAD Electrical drawings were read: DEMO01.DWG, DEMO08.DWG, 019.dwg, 025.dwg, T04.dwg, 2340-000-EA-007.dwg, S244_HQ037_1.dwg, Project_Basics_NFPA_05.dwg, AU_2019_NFPA_05.dwg, PLC_Module_NFPA_05.dwg. Each has one `WD_M` insert, except 2340-000-EA-007.dwg and S244_HQ037_1.dwg (two). Nine drawings carry the same 77 tags as the list in section 7. The AC1015 drawing (2340-000-EA-007.dwg) carries 58: it lacks the 19 tags LOCBOX_LAY, SORTMODE, WNUM_FLAGS, WNUM_GAP, WNUM_OFFSET, XREF_CONTACTMAP, XREF_FILLWITH, XREF_FLAGS, XREF_GRAPHIC, XREF_GRAPHICSTYLE, XREF_SORT, XREF_STYLE, XREF_TBLCOLJUST, XREF_TBLFLDNAMS, XREF_TBLINDEX, XREF_TBLSTYLE, XREF_TBLTITLE, XREF_TXTBTWN, XREF_UNUSEDSTYLE.

Proposed `wd_m_attribute_map`: every tag is a drawing format setting (layers, numbering formats, cross-reference styles). None names a panel, circuit, breaker or load. Proposal: leave all 77 listed.

| Group | Tags | Proposal |
|---|---|---|
| Layer names (*_LAY, WIRELAYS, FAN_INOUT_LAYS) | 19 | leave listed |
| Cross-reference settings (XREF*, ALT_XREFFMT, REFNUMS) | 18 | leave listed |
| Wire and tag numbering (TAG*, WIRE*, WNUM_*, WINC, WLEADERS, SORTMODE) | 21 | leave listed |
| Other drawing format settings | 25 | leave listed |
| SHEET, SHEETDWGNAME | 2 | leave listed (a `sheet` locator key only if the owner wants the sheet in locators) |

### .wdp check on the 20 gold files (G7.10)

Run 2026-11-09: `redline check` on a temp copy of each of the 20 `.wdp` files under `gold/dwg`, and `aecad_side.parse_file` on each for the unknown-line count.

- Files run: 20.
- Exit 0: 19. Exit 2: 1.
- InputError: 1. `Jisdemo.wdp` (JisDemo): "cannot decode the file: character maps to <undefined>". The bytes are not accepted by cp1252, as the `aecad_side.py` docstring says for an East Asian code page. `redline check` on it alone exits 2 ("no input file could be read"), which fits CLAUDE.md section 6.
- Lines listed as unknown shape ("line shape not known"): 0 in all 19 readable files.
- `Project_Drawing_List_NFPA.wdp` lists 0 drawings (settings only, 115 lines not read), as the docstring says for one sample.
- Drawings listed per file, in this order: wddemo 9, Extra Library Demo 3, Gbdemo 29, H-S244test 156, Iec60617Demo 29, iecdemo 29, Ieeedemo 29, Jisdemo unread, Nfpademo 9, perf_2340 147, Project_Basics_NFPA 13, Project_Drawing_List_NFPA 0, then 10 each for Schematic_Wiring, Schematic_Components, Schematic_Editing, Schematic_Reports, Panel_Layouts, Custom_Components, Custom_Data, PLC_Modules.
- `Gbdemo.wdp` (GB) decodes under cp1252 with wrong characters; no line read was affected, because only unread lines carry them.

### Extraction times and timeout (G7.11, answer open)

Measured 2026-11-09 on the 14 drawings above (56 KB to 556 KB, the largest in `gold/dwg`): `oda_ezdxf` 0.36 s to 1.39 s (mean 0.66 s; the 1.39 s run was the first, cold one). The failed `acad_plugin` attempt takes 1.87 s to 2.52 s. The plugin dump itself is unmeasured (D10).

Proposal for `parsing.dxf_extractor_timeout_s`: keep 120. It is about 85 times the slowest measured run, and client drawings may be larger than any file in the gold set (all under 560 KB). Owner decision; nothing in the config was edited.
