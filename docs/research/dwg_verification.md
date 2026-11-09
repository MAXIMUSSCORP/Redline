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

## 8. xcheck corpus run

Placeholder. Leaf L2.7 fills this section.
