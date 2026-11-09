# Redline AutoCAD plugin

A thin dumper. It adds one command, `REDLINE_DUMP`, to the AutoCAD Core Console. The command reads the open drawing and writes RawDrawing 1.0 JSON (`.claude/plans/M2.md` section 4.10). It holds no business logic: it reads, it does not judge, rename, map or drop anything. Interpretation lives in the Python parsers.

Licensing: this plugin runs on the owner's workstation only (PLAN row 38). It is never shipped to a client.

## Build

```
dotnet build extractors/acad_plugin/RedlinePlugin.csproj -c Release -p:AcadDir="D:/Autodesk/AutoCAD 2026" -p:AcadVersion=2026
```

Output goes to `bin/<AcadVersion>/RedlinePlugin.dll`. The build fails with a plain message when `AcadDir` is empty. The project references `AcCoreMgd.dll` and `AcDbMgd.dll` with `Private=false`, so no Autodesk assembly is copied. There is no `AcMgd.dll` and no package reference; `System.Text.Json` comes from the .NET 8 shared framework.

## Versions

| AutoCAD | Status |
|---|---|
| 2026 | built (D7) |
| 2025 and earlier | not built |
| 2027 and later | not built |

Which versions the firm runs is UNVERIFIED. Another version is one build command with its own `AcadDir` and `AcadVersion`.

## Script quirks

- Use forward slashes in every path.
- `NETLOAD` takes an unquoted path, so the DLL must sit at a path with no space.
- Set `FILEDIA` to 0 first.
- Run on a copy of the drawing in a temp folder, never the original.
- `REDLINE_DUMP` asks for the output path, with spaces allowed. A failure writes no file and prints one line, `REDLINE_DUMP failed: <exception type>`. Check the output file, never the exit code.

Script:

```
FILEDIA
0
NETLOAD
<dll path>
REDLINE_DUMP
<output json path>
```

## Evaluated FIELD text

The plugin reads each table cell with `Table.TextString(row, col, FormatOption.IgnoreMtextFormat)` and sets `evaluated` true when that call succeeds, false when it throws. Whether this member returns the evaluated FIELD value, not a stale cached string, is UNVERIFIED until L2.7 checks it on the owner's FIELD table.

## Load test

Date: 2026-11-09. AutoCAD 2026 (accoreconsole 25.1, build W.122.0.0). A command built against `AcCoreMgd.dll` and `AcDbMgd.dll` (about 20 lines, in a temp folder, not in this repo), run on a temp copy of `gold/dwg/etsu_entc2160_m04/Tiny Electrical Plan.dwg`.

Script lines:

```
FILEDIA
0
NETLOAD
C:/Users/Zaidz/AppData/Local/Temp/redline-m2/L2.1-load/proj/out/LoadTest.dll
LOADTEST_PING
```

Outcome: NOT REACHED. `accoreconsole.exe` itself crashes at startup with exception 0xc0000005 in `AcPal.dll`, before it reads any script line. It crashes the same way with no arguments, with `/i` only, and with a script holding only `FILEDIA 0`, so the plugin is not the cause. Seen from a subprocess with stdin closed, from PowerShell `Start-Process`, and hidden-window. Raised to the lead as an environment blocker; no SECURELOAD prompt appeared, and no AutoCAD setting was changed. NETLOAD on .NET 8 remains UNVERIFIED, and the live gates G1.7 to G1.9 could not run.
