# Redline AutoCAD plugin

A thin dumper. It adds one command, `REDLINE_DUMP`, to the AutoCAD Core Console. The command reads the open drawing and writes RawDrawing 1.1 JSON. It holds no business logic: it reads, it does not judge, rename, map or drop anything. Interpretation lives in the Python parsers.

Licensing: this plugin runs on the owner's workstation only (PLAN row 38). It is never shipped to a client.

## Build

```
dotnet build extractors/acad_plugin/RedlinePlugin.csproj -c Release -p:AcadDir="C:/Program Files/Autodesk/AutoCAD 2027" -p:AcadVersion=2027
```

Output goes to `bin/<AcadVersion>/RedlinePlugin.dll`. The build fails with a plain message when `AcadDir` is empty. The project references `AcCoreMgd.dll` and `AcDbMgd.dll` with `Private=false`, so no Autodesk assembly is copied. There is no `AcMgd.dll` and no package reference; `System.Text.Json` comes from the .NET 10 shared framework.

## Versions

| AutoCAD | Status |
|---|---|
| 2027 | built (PLAN row 42) |
| 2026 | not built |
| 2025 and earlier | not built |
| 2028 and later | not built |

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

A cell is `evaluated: true` only when `Table.TextString(row, col, FormatOption.IgnoreMtextFormat)` succeeds and the cell holds no field (`GetFieldId`), formula (`HasFormula`) or data link (`GetDataLink`). A cell with any of these, or whose read or check throws, is `evaluated: false`; a failed read also adds a warning naming table handle, row, column and exception type. Whether `TextString` returns the evaluated FIELD value is UNVERIFIED until L2.7.

## Field flag (schema 1.1)

TEXT, MTEXT and each attribute carry `evaluated`, the opposite of `DBObject.HasFields`: `false` when the object holds a FIELD, so its text may be a cached value. A constant attribute takes the flag from its `AttributeDefinition`. Built against AutoCAD 2027 on 2026-11-10, so the member exists. What `HasFields` returns on a drawing with a real FIELD is UNVERIFIED until the redeployed plugin is run on the D13 evidence drawing.


## Load test

Date: 2026-11-09. AutoCAD 2027 (accoreconsole X.60.0.0, core console 26.0.60, .NET 10), run on a temp copy of `gold/dwg/etsu_entc2160_m04/Tiny Electrical Plan.dwg`, started by subprocess with stdin closed and absolute paths.

Script lines:

```
FILEDIA
0
NETLOAD
C:/Users/<user>/redline/plugin/RedlinePlugin.dll
REDLINE_DUMP
<output json path>
```

Outcome: LOADED. The first run on 2026-11-09 was refused: NETLOAD printed `Unable to load <path> assembly.` because `SECURELOAD` is 1 and `TRUSTEDPATHS` was empty (a one-line .lsp loaded from the same kind of folder gave `File load canceled`). The owner then added `C:/Users/<user>/redline/plugin` to TRUSTEDPATHS in AutoCAD 2027 (D10); SECURELOAD stays 1. Loaded from that folder, `REDLINE_DUMP` wrote 949 entities from the ETSU copy, and the dumps of the ETSU copy and of DEMO01.DWG validate (leaf-L2.1 G1.7 to G1.9). Install the DLL in the trusted folder; a copy anywhere else is refused.
## Xrefs

The plugin reads no xref content. Every xref is listed in `document.xrefs` with `resolved: false`, and a document warning names it.
