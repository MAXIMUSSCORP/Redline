# DWG extractor verification on the dev PC

Leaf L2.0, written 2026-11-09 on the Windows 11 dev PC, from a shell inside an MSIX-packaged app. Rev 3 re-run (PLAN row 42). Section 8 was refreshed at 3bff5d7. Every figure below was measured here. Anything not measured is marked UNVERIFIED or BLOCKED with its reason.

Headline: the AutoCAD 2026 `accoreconsole.exe` crashes in `AcPal.dll` (history, row 41, kept below). The AutoCAD 2027 `accoreconsole.exe` runs: both smoke tests exit 0 in about 2 s with no licence dialog. ODA File Converter 27.10.0 converts DWG to DXF and ezdxf reads the result. The 2026 results are history only. The Redline plugin now loads in the 2027 console (section 4), and section 8 compares both extractors on 14 real drawings.

## 1. Find the exe (M2.3 task 1)

- Path: `D:/Autodesk/AutoCAD 2026/accoreconsole.exe`, 504152 bytes, dated 2025-10-24.
- File version 25.1.122.0.0, product name `AcCoreConsole`. The banner reads "AutoCAD Core Engine Console - Copyright 2025 Autodesk, Inc. (W.122.0.0)".
- Search: `find "C:/Program Files/Autodesk" "D:/Autodesk" -maxdepth 4 -iname accoreconsole.exe` returned only the D: path. `C:/Program Files/Autodesk` does not exist on this PC.
- `D:/Autodesk` holds AutoCAD 2026 and several Revit 2026 items. No AutoCAD Electrical folder exists, which matches the machine notes.

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

`<temp>` is `C:\Users\<user>\AppData\Local\Temp\redline-m2\L2.0`.

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

A 2027 core console script ran `(open "C:/Users/<user>/AppData/Local/redline/l20_acc_probe.txt" "w")`, `write-line`, `close`, then `_QUIT` (exit 0).

- Path written: `C:/Users/<user>/AppData/Local/redline/l20_acc_probe.txt`.
- The redline venv python saw it at that path: `os.path.exists` True, content read back.
- The same file was also visible at a path under `AppData/Local/Packages/<app package>/LocalCache/Local/redline/l20_acc_probe.txt`, and that folder lists the same entries as the plain path (`venv`, `wt`). Inside the packaged shell the two paths show one folder.
- Where the bytes physically sit, and whether a process outside the app sees the plain path, is UNVERIFIED (every process here runs under the packaged app). The probe file was deleted afterwards.

History, 2026 era: the probe could not run through the core console; PowerShell and the venv python showed the same one-folder behaviour. For the plugin DLL path see `extractors/acad_plugin/README.md` (leaf L2.1).

## 3. Core Console licensing (M2.3 task 3)

Resolved, SECURELOAD: the plugin DLL was refused at first because SECURELOAD is 1 and TRUSTEDPATHS was empty. The owner added `C:/Users/<user>/redline/plugin` to TRUSTEDPATHS in AutoCAD 2027 (D10). SECURELOAD stays 1. The plugin loads from that folder (section 4).

Owner line, licensing: the owner asks the reseller in writing whether headless Core Console use on a shared machine is allowed, and checks seat use in the Autodesk account. The answer is quoted here when given. No answer yet. Until then, run only on the named user's own workstation.

Run-with-AutoCAD-closed versus open: UNVERIFIED, not measured in the 2027 re-run. The 2026 crash decision is moot under rev 3 (the 2027 core console runs).

## 4. NETLOAD on 2025 and later (M2.3 task 4)

Owned by leaf L2.1. See `extractors/acad_plugin/README.md`, section "Load test". Outcome there: LOADED in the 2027 Core Console from the trusted folder `C:/Users/<user>/redline/plugin`. A copy of the DLL anywhere else is refused. The 2026 Core Console crashed before any command ran (section 2).

## 5. FIELD and DATALINK evaluation (M2.3 task 5)

FIELD: shown, on the owner's FIELD table (LP-12 in `samples/dwg/panel_sheet.dwg`, rebuilt at c380a9e; measurements in section 8). In column 2, rows 2 to 7, the plugin gives the evaluated text 1350, 1500, 1800, 2100, 2400, 2700 with `evaluated: true`. The fallback gives the same text read from the FIELD's cached result through its 344 handle, with `evaluated: false`. Text and `evaluated` both match each extractor's fixture (356 cells, 0 differences).

Limit of the plugin result: `evaluated: true` only means that `Table.TextString(row, col, FormatOption.IgnoreMtextFormat)` (`extractors/acad_plugin/Dump.cs:235`) did not throw. It does not prove the field was regenerated, so a stale cache could pass. Listed follow-up: have the plugin force a field update before it reads, or compare against a regenerated value, then re-run this check.

DATALINK: UNVERIFIED. No DATALINK table exists in `samples/dwg/panel_sheet.dwg` or in any drawing in the corpus, so nothing was tested. It needs a DWG with a DATALINK table, authored by the owner.

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

Drawing: `gold/dwg/ace_sample_projects/x/aceSampleProjects-master/Demo/DEMO01.DWG` (the first Demo drawing tried; a temp copy converted with ODA 27.10.0 to R2018 DXF, read with ezdxf 1.4.5). Its model space holds 1 `WD_M` INSERT. Attribute tags, TAGS ONLY, count 77. No attribute value was written here:

`ALT_XREFFMT`, `ARROW_STYLE`, `CDESC_LAY`, `CHAR_H`, `CHAR_V`, `COMP_LAY`, `CXREF_LAY`, `DATUMX`, `DATUMY`, `DESC_LAY`, `DISTH`, `DISTV`, `DLADW`, `DRWRUNG`, `FAN_INOUT_LAYS`, `FAN_INOUT_STYLE`, `FEATURE_SCL`, `GAP_STYLE`, `HORIZ_FIRST`, `IEC_INST`, `IEC_LOC`, `IEC_PROJ`, `LINK_LAY`, `LOCBOX_LAY`, `LOC_LAY`, `MISC_DATA`, `MISC_FLAGS`, `MISC_LAY`, `PH3SPACE`, `PLC_STYLE`, `POS_LAY`, `REFNUMS`, `RUNGDIST`, `RUNGHORV`, `RUNGINC`, `SHEET`, `SHEETDWGNAME`, `SORTMODE`, `TAG-RSUF`, `TAG-START`, `TAGFIXED_LAY`, `TAGFMT`, `TAGMODE`, `TAG_LAY`, `TERM_LAY`, `UNIT_SCL`, `WINC`, `WIRE-RSUF`, `WIRE-START`, `WIRECOPY_LAY`, `WIREFIXED_LAY`, `WIREFMT`, `WIRELAYS`, `WIREMODE`, `WIRENO_LAY`, `WIREREF_LAY`, `WLEADERS`, `WNUM_FLAGS`, `WNUM_GAP`, `WNUM_OFFSET`, `XREFFMT`, `XREF_CONTACTMAP`, `XREF_FILLWITH`, `XREF_FLAGS`, `XREF_GRAPHIC`, `XREF_GRAPHICSTYLE`, `XREF_LAY`, `XREF_SORT`, `XREF_STYLE`, `XREF_TBLCOLJUST`, `XREF_TBLFLDNAMS`, `XREF_TBLINDEX`, `XREF_TBLSTYLE`, `XREF_TBLTITLE`, `XREF_TXTBTWN`, `XREF_UNUSEDSTYLE`, `XY_DELIM`

Other Demo drawings were not tried, since the first one has the block.

### Staff questions

The questions on staff AutoCAD versions and how schedules are made go to the owner (C10). No answers yet.

## 8. xcheck corpus run and real-file checks

Leaf L2.7, first run 2026-11-09 at df9fea8, refreshed 2026-11-09 at 3bff5d7 on the dev PC, main checkout, branch m2. Every figure below was measured in the refresh. The `acad_plugin` extractor now loads (the owner added `C:/Users/<user>/redline/plugin` to AutoCAD 2027 TRUSTEDPATHS; SECURELOAD stays 1, D10), so `redline xcheck` runs both extractors on every drawing. No AutoCAD setting was changed. Gates G7.1 and G7.3 are no longer blocked.

### History

What the first run (df9fea8) said, and what changed since:

- Then the plugin could not load (SECURELOAD 1, TRUSTEDPATHS empty), so the plugin columns were empty. Now the owner has trusted the plugin folder and both columns hold counts.
- Then `samples/dwg/panel_sheet.dwg` was an off-spec drawing. It was rebuilt to spec at c380a9e: LP-12 FIELD cells evaluate to 1350 to 2700, LP-11 has no FIELDs.
- Then the fallback returned empty text for FIELD cells. It now reads the cached text through the cell's 344 handle (2aca9c7) and code 1 cell text with plain MTEXT (822c744, merged at 3bff5d7).
- Then the fallback fixture marked plain cells `evaluated: true`. Every fallback cell is now false, per D4 (6fa336a, 822173b).
- Then each table was seen twice, once as ACAD_TABLE and once as its `*T` render block. The `*T` text is now skipped only when it belongs to a table that was read (91c9238, merged at 6e22c4b).
- Then the WD_M map and the timeout were proposals. The owner has answered both (below).
- The first run also said no table or cell was read in any drawing. That was wrong for the three drawings with tables (S244_HQ037_1.dwg, DEMO01.DWG, DEMO08.DWG). It is removed.

### panel_sheet.dwg against both fixtures (G7.3, G7.4)

Run 2026-11-09: both extractors on a temp copy of `samples/dwg/panel_sheet.dwg` (rebuilt at c380a9e), each compared with its fixture, `samples/dwg/panel_sheet.acad_plugin.rawdrawing.json` and `samples/dwg/panel_sheet.oda_ezdxf.rawdrawing.json`. Tables are matched by size, since fixture handles are invented. The original was unchanged after both runs (SHA-256 equal).

| Item | acad_plugin | oda_ezdxf |
|---|---|---|
| Tables in the drawing | 2: LP-11 (22 x 14, 308 cells) and LP-12 (8 x 6, 48 cells) | the same 2 |
| Cells compared | 356 | 356 |
| Cell text differences from the fixture | 0 | 0 |
| `evaluated` differences from the fixture | 0 | 0 |
| `evaluated` in the live dump | true in 356 | false in 356 |

- The fixture also holds a legend table with no row or column count (fixture handle 2F2E, 5 cells). It is absent from the drawing, because AutoCAD cannot draw a table without a count. Known difference, not a defect.
- LP-12 FIELD cells, rows 2 to 7 of column 2: both extractors give 1350, 1500, 1800, 2100, 2400, 2700. The plugin marks them `evaluated: true`; the fallback gives the cached text and `evaluated: false`.
- LP-11 has no FIELDs. Its column 2, rows 2 to 7, are plain text: 1350, 1500, 1650, 1800, TBD, 2100, in both extractors.
- What ezdxf gives for a FIELD cell: the cell value is empty. The cell holds a handle (code 344) to a FIELD object. The fallback follows that handle to the child FIELD's cached text.

### Comparison of both extractors over 14 real drawings (G7.7)

`redline xcheck <copy> --config config/` was run on a temp copy of each drawing, one folder per copy, under `%TEMP%\redline-m2\FX5\`. Exit code 0 in all 14. Each extractor was also timed on its own with a wall clock. The SHA-256 of the original, the copy and the original again were equal after every run.

The three drawings with tables are S244_HQ037_1.dwg (3 tables, 92 cells), DEMO01.DWG (2 tables, 294 cells) and DEMO08.DWG (1 table, 40 cells). The other 11 hold no ACAD_TABLE.

Counts, plugin / fallback. "Entities" is the sum of all entity-type rows in the loss table.

| Path under `gold/dwg` | DWG | Bytes | Entities plugin / fallback | Tables | Cells | Cells evaluated | Attributes | Cell text differs |
|---|---|---|---|---|---|---|---|---|
| `etsu_entc2160_m04/Tiny Electrical Plan.dwg` | AC1032 | 555671 | 949 / 944 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 |
| `etsu_entc2160_m04/Electric Symbols.dwg` | AC1032 | 550639 | 289 / 284 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 |
| `arjunb3hl_p003b/final_drawing_P003-B.dwg` | AC1032 | 92498 | 1329 / 1395 | 0 / 0 | 0 / 0 | 0 / 0 | 162 / 162 | 0 |
| `ace_sample_projects/x/aceSampleProjects-master/perf_2340/2340-000-EA-007.dwg` | AC1015 | 59349 | 141 / 37 | 0 / 0 | 0 / 0 | 0 / 0 | 162 / 162 | 0 |
| `ace_sample_projects/x/aceSampleProjects-master/H-S244test/S244_HQ037_1.dwg` | AC1021 | 289248 | 2508 / 2236 | 3 / 3 | 92 / 92 | 92 / 0 | 1063 / 1063 | 0 |
| `ace_sample_projects/x/aceSampleProjects-master/Demo/DEMO01.DWG` | AC1024 | 155048 | 616 / 801 | 2 / 2 | 294 / 294 | 294 / 0 | 347 / 347 | 0 |
| `ace_sample_projects/x/aceSampleProjects-master/NfpaDemo/DEMO08.DWG` | AC1024 | 115108 | 402 / 281 | 1 / 1 | 40 / 40 | 40 / 0 | 251 / 251 | 7 |
| `ace_sample_projects/x/aceSampleProjects-master/IeeeDemo/019.dwg` | AC1024 | 139826 | 831 / 307 | 0 / 0 | 0 / 0 | 0 / 0 | 834 / 834 | 0 |
| `ace_sample_projects/x/aceSampleProjects-master/JisDemo/025.dwg` | AC1024 | 246712 | 1499 / 961 | 0 / 0 | 0 / 0 | 0 / 0 | 2690 / 2690 | 0 |
| `ace_sample_projects/x/aceSampleProjects-master/GbDemo/Tabular TermLay/T04.dwg` | AC1024 | 109002 | 459 / 264 | 0 / 0 | 0 / 0 | 0 / 0 | 344 / 344 | 0 |
| `autodesk_learn_ee_mfg/x/MEE-AE0002_Project-Basics/Project Basics/Project_Basics_NFPA_05.dwg` | AC1027 | 93052 | 709 / 314 | 0 / 0 | 0 / 0 | 0 / 0 | 774 / 774 | 0 |
| `autodesk_learn_ee_mfg/x/MEE-AE0010_PLC-Modules/PLC Modules/PLC_Module_NFPA_05.dwg` | AC1027 | 85425 | 578 / 256 | 0 / 0 | 0 / 0 | 0 / 0 | 690 / 690 | 0 |
| `autodesk_learn_ee_mfg/x/MEE-AE0010_PLC-Modules/PLC Modules/AU_2019_NFPA_05.dwg` | AC1032 | 84615 | 578 / 256 | 0 / 0 | 0 / 0 | 0 / 0 | 690 / 690 | 0 |
| `autodesk_learn_ee_mfg/x/MEE-AE0008_Custom-Components/Custom Components/HDV1_IconMenu.dwg` | AC1021 | 56096 | 14 / 1 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 |


Findings from the table above:

- Tables, cells and attributes agree between the two extractors in all 14 drawings.
- Cells evaluated: the plugin marks every cell of the three tables true (92, 294, 40). The fallback marks all of them false (D4). `evaluated: true` from the plugin has a limit, stated in section 5.
- Cell text differs: 0 in 13 drawings, 7 in `NfpaDemo/DEMO08.DWG`. The 7 are the cells in column 4, rows 1 to 7. The plugin returns multi-line cell text with its line breaks (`\r\n\n` between the lines). The fallback joins the same words with single spaces. The words are the same; the whitespace differs. A parser that compares text must collapse whitespace first.
- Per-type entity counts differ in places, for example TEXT and MTEXT (DEMO01.DWG: plugin TEXT 196, MTEXT 0; fallback TEXT 26, MTEXT 245) and LINE (final_drawing_P003-B.dwg: plugin 232, fallback 292). Cause UNVERIFIED. The total entity count differs too (see the table). No attempt was made here to reconcile them.
- The double reading of a table is gone. `redline check` on a temp copy of `panel_sheet.dwg` (exit 0, extractor `acad_plugin` 1.0.0) reads LP-11 and LP-12 once each, and the report holds no repeated-panel-name notice.

Times, wall seconds (the `redline xcheck` total includes Python start-up and both extractors):

| Drawing | acad_plugin time | oda_ezdxf time | `redline xcheck` total wall | Original SHA-256 unchanged |
|---|---|---|---|---|
| Tiny Electrical Plan.dwg | 2.06 s | 1.32 s | 3.9 s | yes |
| Electric Symbols.dwg | 2.07 s | 0.67 s | 3.67 s | yes |
| final_drawing_P003-B.dwg | 2.08 s | 0.49 s | 3.56 s | yes |
| 2340-000-EA-007.dwg | 1.98 s | 0.4 s | 3.5 s | yes |
| S244_HQ037_1.dwg | 2.17 s | 0.88 s | 3.87 s | yes |
| DEMO01.DWG | 2.01 s | 0.64 s | 3.59 s | yes |
| DEMO08.DWG | 1.99 s | 0.48 s | 3.45 s | yes |
| 019.dwg | 1.94 s | 0.57 s | 3.54 s | yes |
| 025.dwg | 1.97 s | 0.91 s | 4.12 s | yes |
| T04.dwg | 2.03 s | 0.49 s | 3.49 s | yes |
| Project_Basics_NFPA_05.dwg | 2.06 s | 0.52 s | 3.5 s | yes |
| PLC_Module_NFPA_05.dwg | 2.06 s | 0.5 s | 3.59 s | yes |
| AU_2019_NFPA_05.dwg | 1.98 s | 0.49 s | 3.52 s | yes |
| HDV1_IconMenu.dwg | 2.03 s | 0.36 s | 3.35 s | yes |

Loss tables as `redline xcheck` printed them, one block per drawing. The file names are not unique across the corpus; the drawings are `gold/dwg/ace_sample_projects/x/aceSampleProjects-master/IeeeDemo/019.dwg` (139826 bytes), `.../JisDemo/025.dwg` (246712 bytes), `.../GbDemo/Tabular TermLay/T04.dwg` (109002 bytes), `.../NfpaDemo/DEMO08.DWG` (115108 bytes) and `.../Demo/DEMO01.DWG` (155048 bytes). Other projects hold files with the same names and different sizes. Versions covered: AC1015, AC1021, AC1024, AC1027, AC1032.

```
file                      item               acad_plugin  oda_ezdxf
Tiny Electrical Plan.dwg  INSERT                      34         34
Tiny Electrical Plan.dwg  LINE                       875        875
Tiny Electrical Plan.dwg  MTEXT                       30         30
Tiny Electrical Plan.dwg  POLYLINE                     5          5
Tiny Electrical Plan.dwg  TEXT                         5          0
Tiny Electrical Plan.dwg  tables                       0          0
Tiny Electrical Plan.dwg  cells                        0          0
Tiny Electrical Plan.dwg  cells evaluated              0          0
Tiny Electrical Plan.dwg  attributes                   0          0
Tiny Electrical Plan.dwg  cell text differs            0          0
```

```
file                  item               acad_plugin  oda_ezdxf
Electric Symbols.dwg  LINE                       197        197
Electric Symbols.dwg  MTEXT                       45         45
Electric Symbols.dwg  POLYLINE                    42         42
Electric Symbols.dwg  TEXT                         5          0
Electric Symbols.dwg  tables                       0          0
Electric Symbols.dwg  cells                        0          0
Electric Symbols.dwg  cells evaluated              0          0
Electric Symbols.dwg  attributes                   0          0
Electric Symbols.dwg  cell text differs            0          0
```

```
file                      item               acad_plugin  oda_ezdxf
final_drawing_P003-B.dwg  INSERT                      81         81
final_drawing_P003-B.dwg  LINE                       232        292
final_drawing_P003-B.dwg  MTEXT                        0         12
final_drawing_P003-B.dwg  POLYLINE                   191        191
final_drawing_P003-B.dwg  TEXT                       825        819
final_drawing_P003-B.dwg  tables                       0          0
final_drawing_P003-B.dwg  cells                        0          0
final_drawing_P003-B.dwg  cells evaluated              0          0
final_drawing_P003-B.dwg  attributes                 162        162
final_drawing_P003-B.dwg  cell text differs            0          0
```

```
file                 item               acad_plugin  oda_ezdxf
2340-000-EA-007.dwg  INSERT                       3          3
2340-000-EA-007.dwg  LINE                        13         13
2340-000-EA-007.dwg  MTEXT                        2          2
2340-000-EA-007.dwg  POLYLINE                     1          1
2340-000-EA-007.dwg  TEXT                       122         18
2340-000-EA-007.dwg  tables                       0          0
2340-000-EA-007.dwg  cells                        0          0
2340-000-EA-007.dwg  cells evaluated              0          0
2340-000-EA-007.dwg  attributes                 162        162
2340-000-EA-007.dwg  cell text differs            0          0
```

```
file              item               acad_plugin  oda_ezdxf
S244_HQ037_1.dwg  ACAD_TABLE                   3          3
S244_HQ037_1.dwg  INSERT                     100        100
S244_HQ037_1.dwg  LINE                      1929       1973
S244_HQ037_1.dwg  MTEXT                        3         75
S244_HQ037_1.dwg  POLYLINE                    33         33
S244_HQ037_1.dwg  TEXT                       440         52
S244_HQ037_1.dwg  tables                       3          3
S244_HQ037_1.dwg  cells                       92         92
S244_HQ037_1.dwg  cells evaluated             92          0
S244_HQ037_1.dwg  attributes                1063       1063
S244_HQ037_1.dwg  cell text differs            0          0
```

```
file        item               acad_plugin  oda_ezdxf
DEMO01.DWG  ACAD_TABLE                   2          2
DEMO01.DWG  INSERT                      27         27
DEMO01.DWG  LINE                       304        414
DEMO01.DWG  MTEXT                        0        245
DEMO01.DWG  POLYLINE                    87         87
DEMO01.DWG  TEXT                       196         26
DEMO01.DWG  tables                       2          2
DEMO01.DWG  cells                      294        294
DEMO01.DWG  cells evaluated            294          0
DEMO01.DWG  attributes                 347        347
DEMO01.DWG  cell text differs            0          0
```

```
file        item               acad_plugin  oda_ezdxf
DEMO08.DWG  ACAD_TABLE                   1          1
DEMO08.DWG  INSERT                      46         46
DEMO08.DWG  LINE                       120        136
DEMO08.DWG  MTEXT                        0         40
DEMO08.DWG  POLYLINE                    40         40
DEMO08.DWG  TEXT                       195         18
DEMO08.DWG  tables                       1          1
DEMO08.DWG  cells                       40         40
DEMO08.DWG  cells evaluated             40          0
DEMO08.DWG  attributes                 251        251
DEMO08.DWG  cell text differs            7          7
```

```
file     item               acad_plugin  oda_ezdxf
019.dwg  INSERT                      51         51
019.dwg  LINE                       189        189
019.dwg  POLYLINE                    39         39
019.dwg  TEXT                       552         28
019.dwg  tables                       0          0
019.dwg  cells                        0          0
019.dwg  cells evaluated              0          0
019.dwg  attributes                 834        834
019.dwg  cell text differs            0          0
```

```
file     item               acad_plugin  oda_ezdxf
025.dwg  INSERT                     153        153
025.dwg  LINE                       597        597
025.dwg  POLYLINE                   137        137
025.dwg  TEXT                       612         74
025.dwg  tables                       0          0
025.dwg  cells                        0          0
025.dwg  cells evaluated              0          0
025.dwg  attributes                2690       2690
025.dwg  cell text differs            0          0
```

```
file     item               acad_plugin  oda_ezdxf
T04.dwg  INSERT                      17         17
T04.dwg  LINE                       161        161
T04.dwg  MTEXT                        1          1
T04.dwg  POLYLINE                     1          1
T04.dwg  TEXT                       279         84
T04.dwg  tables                       0          0
T04.dwg  cells                        0          0
T04.dwg  cells evaluated              0          0
T04.dwg  attributes                 344        344
T04.dwg  cell text differs            0          0
```

```
file                        item               acad_plugin  oda_ezdxf
Project_Basics_NFPA_05.dwg  INSERT                      49         49
Project_Basics_NFPA_05.dwg  LINE                       204        204
Project_Basics_NFPA_05.dwg  POLYLINE                    30         30
Project_Basics_NFPA_05.dwg  TEXT                       426         31
Project_Basics_NFPA_05.dwg  tables                       0          0
Project_Basics_NFPA_05.dwg  cells                        0          0
Project_Basics_NFPA_05.dwg  cells evaluated              0          0
Project_Basics_NFPA_05.dwg  attributes                 774        774
Project_Basics_NFPA_05.dwg  cell text differs            0          0
```

```
file                    item               acad_plugin  oda_ezdxf
PLC_Module_NFPA_05.dwg  INSERT                      58         58
PLC_Module_NFPA_05.dwg  LINE                       137        137
PLC_Module_NFPA_05.dwg  POLYLINE                    30         30
PLC_Module_NFPA_05.dwg  TEXT                       353         31
PLC_Module_NFPA_05.dwg  tables                       0          0
PLC_Module_NFPA_05.dwg  cells                        0          0
PLC_Module_NFPA_05.dwg  cells evaluated              0          0
PLC_Module_NFPA_05.dwg  attributes                 690        690
PLC_Module_NFPA_05.dwg  cell text differs            0          0
```

```
file                 item               acad_plugin  oda_ezdxf
AU_2019_NFPA_05.dwg  INSERT                      58         58
AU_2019_NFPA_05.dwg  LINE                       137        137
AU_2019_NFPA_05.dwg  POLYLINE                    30         30
AU_2019_NFPA_05.dwg  TEXT                       353         31
AU_2019_NFPA_05.dwg  tables                       0          0
AU_2019_NFPA_05.dwg  cells                        0          0
AU_2019_NFPA_05.dwg  cells evaluated              0          0
AU_2019_NFPA_05.dwg  attributes                 690        690
AU_2019_NFPA_05.dwg  cell text differs            0          0
```

```
file               item               acad_plugin  oda_ezdxf
HDV1_IconMenu.dwg  POLYLINE                     1          1
HDV1_IconMenu.dwg  TEXT                        13          0
HDV1_IconMenu.dwg  tables                       0          0
HDV1_IconMenu.dwg  cells                        0          0
HDV1_IconMenu.dwg  cells evaluated              0          0
HDV1_IconMenu.dwg  attributes                   0          0
HDV1_IconMenu.dwg  cell text differs            0          0
```

### final_drawing_P003-B.dwg, panel P1 (G7.8)

Run 2026-11-09: `redline check` on a temp copy of `gold/dwg/arjunb3hl_p003b/final_drawing_P003-B.dwg` with the real config (exit 0, extractor `acad_plugin` 1.0.0, host AutoCAD 2027). The first run used `oda_ezdxf`; the answers are the same.

1. Was panel P1 read: no. The report holds no panel. The extractor read 0 tables and 3 loose-text clusters (3 listed as not read), and 81 block references with attributes were not read as schedules.
2. Confidence: none. The coverage line reads HIGH 0, MEDIUM 0, LOW 0, MISSING 0. No value was read, so there is nothing to grade.
3. Circuit count: 0 read against 19 in `model_P003-B.json` (1 panel, 19 circuits). The E-201 schedule has 30 slots; each row is listed with a reason (mostly "no circuit number").

Why, unchanged since the first run: in the E-201 header, `SLOT`, `I A` and `CHECK` have no alias in `csv_panel_schedule`, and two pairs map to one field (`PH` and `PER-PHASE TOTALS`; `DEV LOAD W` and `LOAD VA`). Proposal for `config/column_maps.yaml` (not edited here): an alias `slot` for `circuit_number` once the owner confirms SLOT is the circuit position, and aliases for current, length and voltage drop only if those fields exist in the model. The side-by-side totals block on the same row also needs a rule for the duplicate-column case. Owner decision.

### WD_M tags (G7.9)

Tags only, no values. Re-read 2026-11-09 with both extractors from temp copies of 10 AutoCAD Electrical drawings: `Demo/DEMO01.DWG`, `NfpaDemo/DEMO08.DWG`, `IeeeDemo/019.dwg`, `JisDemo/025.dwg`, `GbDemo/Tabular TermLay/T04.dwg`, `perf_2340/2340-000-EA-007.dwg`, `H-S244test/S244_HQ037_1.dwg`, and `Project_Basics_NFPA_05.dwg`, `PLC_Module_NFPA_05.dwg`, `AU_2019_NFPA_05.dwg` from the Autodesk Learn courses. Both extractors gave the same tag lists. Each drawing has one `WD_M` insert, except `2340-000-EA-007.dwg` and `S244_HQ037_1.dwg` (two each). Nine drawings carry the same 77 tags as the list in section 7. The AC1015 drawing (`2340-000-EA-007.dwg`) carries 58 on each insert: it lacks the 19 tags LOCBOX_LAY, SORTMODE, WNUM_FLAGS, WNUM_GAP, WNUM_OFFSET, XREF_CONTACTMAP, XREF_FILLWITH, XREF_FLAGS, XREF_GRAPHIC, XREF_GRAPHICSTYLE, XREF_SORT, XREF_STYLE, XREF_TBLCOLJUST, XREF_TBLFLDNAMS, XREF_TBLINDEX, XREF_TBLSTYLE, XREF_TBLTITLE, XREF_TXTBTWN, XREF_UNUSEDSTYLE.

Every tag is a drawing format setting (layers, numbering formats, cross-reference styles). None names a panel, circuit, breaker or load.

| Group | Tags | Decision |
|---|---|---|
| Layer names (*_LAY, WIRELAYS, FAN_INOUT_LAYS) | 19 | leave listed |
| Cross-reference settings (XREF*, ALT_XREFFMT, REFNUMS) | 18 | leave listed |
| Wire and tag numbering (TAG*, WIRE*, WNUM_*, WINC, WLEADERS, SORTMODE) | 21 | leave listed |
| Other drawing format settings | 25 | leave listed |
| SHEET, SHEETDWGNAME | 2 | leave listed |

Owner answer, 2026-11-09: "Accept both". All 77 tags are left listed, and `wd_m_attribute_map` stays empty (`config/column_maps.yaml` holds `wd_m_attribute_map: {}`). No config change.

### .wdp check on the 20 gold files (G7.10)

Run 2026-11-09: `redline check` on a temp copy of each of the 20 `.wdp` files under `gold/dwg`, and `aecad_side.parse_file` on each for the unknown-line count. Same result as the first run.

- Files run: 20.
- Exit 0: 19. Exit 2: 1.
- InputError: 1. `JisDemo/Jisdemo.wdp`: "cannot decode the file: character maps to <undefined>". The bytes are not accepted by cp1252, as the `aecad_side.py` docstring says for an East Asian code page. `redline check` on it alone exits 2 ("no input file could be read"), which fits the exit code rule (2 only when no input could be read).
- Lines listed as unknown shape ("line shape not known"): 0 in all 19 readable files.
- `Project_Drawing_List_NFPA.wdp` lists 0 drawings (settings only, 115 lines not read), as the docstring says for one sample.
- Drawings listed per file: wddemo 9, Extra Library Demo 3, Gbdemo 29, H-S244test 156, Iec60617Demo 29, iecdemo 29, Ieeedemo 29, Jisdemo unread, Nfpademo 9, perf_2340 147, Project_Basics_NFPA 13, Project_Drawing_List_NFPA 0, then 10 each for Schematic_Wiring, Schematic_Components, Schematic_Editing, Schematic_Reports, Panel_Layouts, Custom_Components, Custom_Data, PLC_Modules.
- `Gbdemo.wdp` (GB) decodes under cp1252 with wrong characters; no line read was affected, because only unread lines carry them.

### Extraction times and timeout (G7.11)

Measured 2026-11-09 on the 14 drawings above (56 KB to 556 KB, the largest in `gold/dwg`), table above: `oda_ezdxf` 0.36 s to 1.32 s (mean 0.62 s; the 1.32 s run was the first, cold one). `acad_plugin` 1.94 s to 2.17 s (mean 2.03 s). The full `redline xcheck` call takes 3.35 s to 4.12 s.

`parsing.dxf_extractor_timeout_s` is 120. That is about 55 times the slowest plugin run, and client drawings may be larger than any file in the gold set (all under 560 KB). Owner answer, 2026-11-09: "Accept both". 120 s is kept. The comment beside the value in `config/column_maps.yaml` still says "placeholder until measured"; it was not edited here.
