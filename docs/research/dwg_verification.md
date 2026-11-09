# DWG extractor verification on the dev PC

Leaf L2.0, written 2026-11-09 on the Windows 11 dev PC, from a shell inside the MSIX-packaged Claude app. Every figure below was measured here. Anything not measured is marked UNVERIFIED or BLOCKED with its reason.

Headline: `accoreconsole.exe` 25.1.122.0 starts, prints its banner, then crashes with an access violation in `AcPal.dll`. No script ever ran. Sections 2 (timings, in-place test, probe), 4 and 7 (tags) are BLOCKED by this. Nothing here may be read as "the Core Console works on this PC".

## 1. Find the exe (M2.3 task 1)

- Path: `D:/Autodesk/AutoCAD 2026/accoreconsole.exe`, 504152 bytes, dated 2025-10-24.
- File version 25.1.122.0.0, product name `AcCoreConsole`. The banner reads "AutoCAD Core Engine Console - Copyright 2025 Autodesk, Inc. (W.122.0.0)".
- Search: `find "C:/Program Files/Autodesk" "D:/Autodesk" -maxdepth 4 -iname accoreconsole.exe` returned only the D: path. `C:/Program Files/Autodesk` does not exist on this PC.
- `D:/Autodesk` holds AutoCAD 2026 and several Revit 2026 items. No AutoCAD Electrical folder exists, which matches CLAUDE.md section 9.

## 2. Smoke test, in place or copy, MSIX probe (M2.3 task 2)

### Originals

| Role | Original (read only) | Bytes | SHA-256 before | SHA-256 after |
|---|---|---|---|---|
| Plain | `gold/dwg/etsu_entc2160_m04/Tiny Electrical Plan.dwg` | 555671 | `fab65f216b13e69195b5dd7c70ad400e9d2827db6564a6e760e6dd2b46bf68e6` | `fab65f216b13e69195b5dd7c70ad400e9d2827db6564a6e760e6dd2b46bf68e6` |
| AutoCAD Electrical sample | `gold/dwg/ace_sample_projects/x/aceSampleProjects-master/Demo/DEMO01.DWG` | 155048 | `25580d3aa2f27ad3aadda2ab12a1962859cd6bf7fd9fca836f37bd4d97fd7db2` | `25580d3aa2f27ad3aadda2ab12a1962859cd6bf7fd9fca836f37bd4d97fd7db2` |

Both originals are unchanged. The DEMO01 header reads `AC1024` (DWG 2010). Whether DEMO01 holds `WD_M` blocks is UNVERIFIED (see section 7). The two copies, `%TEMP%/redline-m2/L2.0/smoke_etsu/etsu.dwg` and `smoke_ace/demo01.dwg`, kept the same hashes after the runs.

### Command

Script `t.scr` holds one line, `_QSAVE`. Exact command, run with a 240 s limit and stdin closed:

```
"D:\Autodesk\AutoCAD 2026\accoreconsole.exe" /i "<temp>\smoke_etsu\etsu.dwg" /s "<temp>\t.scr" /l en-US
```

`<temp>` is `C:\Users\Zaidz\AppData\Local\Temp\redline-m2\L2.0`.

### Result: crash, no timing for a completed run

| Drawing | Exit code | Wall time | Licence dialog or prompt |
|---|---|---|---|
| ETSU copy | -1073741819 (0xC0000005) | 1.84 s | none seen; output stops after the banner and the "Current Directory" line |
| DEMO01 copy | -1073741819 (0xC0000005) | 1.38 s | none seen; same output |

The wall times are the time to crash, not the time to run. G0.3 is BLOCKED: no drawing was ever opened.

What was tried, each with the same crash:

- Git Bash with stdin from `/dev/null` (exit 139, a segmentation fault as Git Bash reports it).
- .NET `Process` with stdin redirected and closed, from the temp folder.
- `cmd /c` with `< nul`, current directory `D:/Autodesk/AutoCAD 2026`.
- No script or drawing at all: `accoreconsole.exe /?` crashes the same way.
- The user's own Terminal panel (a normal PowerShell outside the agent shell): the banner printed, the prompt returned, and Windows logged a new crash at 15:26:38. So the agent shell is not the cause.

Windows Application log, event 1000, for every run: faulting module `AcPal.dll` 25.1.122.0, exception 0xc0000005, fault offset 0x000000000001feda. The offset is identical in all runs, so the fault is deterministic.

One candidate cause, UNVERIFIED: AutoCAD 2026 has never been started on this PC. `HKCU:\Software\Autodesk\AutoCAD` does not exist and `%APPDATA%\Autodesk` holds only `Revit` and `WebServices`. A first launch of `acad.exe` would create the profile, but it needs a licence sign-in and changes the user's AutoCAD settings. This leaf did not do that. The owner decides (see section 3). No setting, SECURELOAD, TRUSTEDPATHS or registry value was changed.

No `accoreconsole.exe` process was left running after the runs (process count 0).

### Run in place or on a copy

- Files beside the drawing before and after: the folders held only the copied `.dwg` both times. No `.dwl`, `.dwl2` or `.bak` appeared. This is weak evidence, because the process crashed before it opened the drawing.
- Hash result: equal, as in the table.
- `/readonly`: UNVERIFIED. Not tried, since even `/?` crashes. BLOCKED.
- Decision: **on a copy**. The in-place rule in the plan needs a measured run that writes nothing. None exists, so the default holds. L2.2 runs on a `%TEMP%` copy in its own empty folder. Unresolved xrefs are then listed, never dropped. Revisit when a run completes.

### MSIX probe

The planned probe needs a core console script (AutoLISP `open` and `write-line`) and cannot run (crash). BLOCKED for that part.

What was measured instead, from the agent shell, without the Core Console:

- PowerShell wrote `C:\Users\Zaidz\AppData\Local\redline\l20_probe.txt`.
- The redline venv python (`C:/Users/Zaidz/AppData/Local/redline/venv/Scripts/python.exe`) saw it at that same path: `os.path.exists` returned True.
- The listing of `C:\Users\Zaidz\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\redline` showed the same entries as the plain path (`venv`, `wt`), and the probe file was visible there too. So both paths show one folder here.
- The probe file was deleted afterwards.

Whether a child process started by the Core Console sees the same folder is UNVERIFIED. For the plugin DLL path, see the plugin README at `extractors/acad_plugin/README.md` (written by leaf L2.1).

## 3. Core Console licensing (M2.3 task 3)

BLOCKED: owner. The owner asks the reseller in writing whether headless Core Console use on a shared machine is allowed, and checks seat use in the Autodesk account. The answer is quoted here when given (D10). Until then, run only on the named user's own workstation.

Run-with-AutoCAD-closed versus open was not measured, because the Core Console does not complete a run (section 2). The crash in section 2 also needs an owner decision: start AutoCAD 2026 once to create its profile, or leave the Core Console out.

## 4. NETLOAD on 2025 and later (M2.3 task 4)

Owned by leaf L2.1. See `extractors/acad_plugin/README.md`, section "Load test". Note for L2.1: the Core Console crashes before any command runs (section 2), so a NETLOAD test cannot start until that is fixed.

## 5. FIELD and DATALINK evaluation (M2.3 task 5)

BLOCKED: owner. It needs a DWG with a plain table, a FIELD table and a DATALINK table, authored by the owner. Leaf L2.7 runs the comparison once that file exists.

## 6. ODA File Converter (M2.3 task 6)

BLOCKED: owner install (row 38).

- Not installed. `C:/Program Files/ODA` and `C:/Program Files (x86)/ODA` do not exist, and `HKLM\SOFTWARE\ODA` is absent.
- ezdxf 1.4.5. The default exe path in its options is `C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe`.
- `ezdxf.addons.odafc.is_installed()` returned `False`.
- Version: not available. Conversion time for the ETSU copy: not measured.

## 7. Electrical project folder (M2.3 task 7)

Counts under `gold/dwg`, measured with `find` on 2026-11-09:

- `.wdp` count: 20 (.wdp files).
- `.mdb`: 3 (`H-S244test/H-S244test_cat.mdb`, `MEE-AE0010_PLC-Modules/.../ace_plc.mdb`, `.../PLC_Modules_NFPA_update.mdb`).
- `.accdb`: 0.
- `WD.ENV`: 0.
- `.dxf`: 0.

Database tables and columns were not listed, since no reader is approved (D1).

### WD_M attribute tags

BLOCKED. No tag list and no drawing name. Routes tried or ruled out:

- Core Console `_DXFOUT` to a temp path, then ezdxf: cannot run, the Core Console crashes (section 2).
- ODA File Converter: not installed (section 6).
- ezdxf 1.4.5 does not read DWG, and the gold folder holds no DXF.

No attribute value was read. The route resumes when either the Core Console or ODA works.

### Staff questions

The questions on staff AutoCAD versions and how schedules are made go to the owner (C10). No answers yet.

## 8. xcheck corpus run

Placeholder. Leaf L2.7 fills this section.
