# Getting structured data out of DWG/DXF for Redline

Research date: 2026-11-06. Source dates are noted where known; several vendor pages are undated. Claims marked UNVERIFIED came from a single secondary source or from general knowledge.

## 1. ODA File Converter + ezdxf (local)

**How it works.** ODA File Converter (ODAFC, free binary) turns DWG into DXF. ezdxf reads the DXF and walks the entities. ezdxf's `odafc` add-on wraps the converter: `readfile()` converts DWG/DXB/DXF to a temporary DXF and loads it, `convert()` and `export_dwg()` go the other direction. The converter must be installed separately, and the Windows default path is `C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe`. The GUI is suppressed on Windows. ACAD9/ACAD10 are not supported; R12 through R2018 are [1].

**What ezdxf reads.**
- Current release is 1.4.5 (Oct 2026), MIT license. PyPI lists Python >=3.10 in one place and 3.11 in another, so check [2].
- Inline MTEXT formatting is stripped with `mtext.plain_text()`. Block attributes come from `insert.attribs` (`attrib.dxf.tag`, `attrib.dxf.text`). MULTILEADER attributes come from `mleader.block_attribs` [3].
- AutoCAD tables are read with `read_acad_table_content()` from `ezdxf.entities.acad_table` (verified in the module source on master: `def read_acad_table_content(table: DXFTagStorage) -> list[list[str]]`, listed in `__all__`; if row/column counts are missing, all content lands in the first row) [34][3]. It returns rows of strings. There is no support for creating or modifying ACAD_TABLE [3].
- The DXF reference says table cells are either text-type or block-type (group 171). Text strings sit in groups 1/3 or 302/303, split into 250-character chunks. If a cell holds a FIELD, the string is ignored and only the FIELD object ID is saved [4]. Field-driven cells may therefore come back empty or stale. This is an inference from [4]. I did not test it.
- Layers, model/paper space and block definitions are all available. I did not verify xref handling, so test it.

**Pros.** Free, local, scriptable, no AutoCAD seat, fast (seconds per file), and the whole stack is Python. ezdxf is not a CAD kernel and offers no high-level construction features, so schedule parsing is your own code [5].

**Cons.** ODAFC is a closed-source freeware binary. I could not confirm its redistribution terms. Verify them on opendesign.com before bundling it in a product. Proxy and custom objects (from AutoCAD Electrical's own object enabler) may be dropped or kept as opaque data. Unverified: test on real AutoCAD Electrical files.

**Accuracy.** Good for plain TEXT/MTEXT/ATTRIB. Table and field handling is the main risk.
**Cost.** $0. **Effort.** Weekend for text/attribute/table dump plus a row/column clusterer for tables built from loose text. **Local.**

## 2. LibreDWG (GPL-3.0)

The decoder reads all DWG versions, but some very advanced R2010+ objects fail to read and are skipped. The writer is incomplete: R2010-R2018 writing still produces CRC errors [6]. Python and Perl bindings are generated with SWIG and need a build. Windows is supported via MinGW, clang-cl or VS2019+ with CMake, and nightly Windows binaries are on the releases page [6]. The last version I saw was 0.13.3 (spec dated Feb 2024) [7]. I did not verify that the Python bindings work on Windows.

**Pros.** Free, no external converter, `dwg2dxf` and `dwgread` CLIs.
**Cons.** GPL-3 means a copyleft problem if Redline is distributed closed-source. Running it as a separate CLI process usually sidesteps this, but get legal advice. Skipped objects on recent DWGs are a silent-data-loss risk. Python bindings are awkward.
**Accuracy.** Medium on 2018+ files, unknown on AutoCAD Electrical ones. **Cost.** $0. **Effort.** 1-2 days, mostly build and test pain. **Local.** Fine as a fallback or cross-check, not as the primary path.

## 3. Autodesk Platform Services (cloud)

**Model Derivative.** Translates DWG to SVF/SVF2. Properties can only be queried after translation. The result is a flat list keyed by `objectid`, which is not stable across re-translation, so use `externalId` for persistence [8]. I found nothing on what a 2D DWG yields (whether block attributes and table text appear as properties). Treat it as unproven for this use case.

**Design Automation for AutoCAD.** Runs your script, AutoLISP or a .NET plugin, in cloud AutoCAD (accoreconsole). It can run `DATAEXTRACTION` or custom code and return JSON. It is billed by processing time, measured from `timeDownloadStarted` to `timeUploadEnded`. A 2020 post gives 12 minutes of processing per token, with a note that token consumption changed on 8 Dec 2025 [9]. I could not verify the change: the rate sheet and the APS pricing page (redirects to autodesk.com, returns 403 to my fetcher) were not readable. A search summary of the APS pricing page says 2.0 Flex tokens per processing hour [35], matching a community answer of 2 credits per hour [10]. The Dec 2025 figure is therefore unconfirmed. Open the rate sheet in a browser. Flex tokens expire 365 days after purchase [11]. Cloud credits cost roughly $1 each at resellers (UNVERIFIED) [10].

**Auth and residency.** OAuth2 app registration at aps.autodesk.com, and files are uploaded to Autodesk storage. I did not verify data-residency options. For client electrical drawings, confirm region and confidentiality terms first.

**Pros.** Real AutoCAD engine, so proxy objects and tables are handled natively. No local seat.
**Cons.** Most setup work (app registration, AppBundle, Activity, WorkItems), latency of seconds to minutes per job, and cloud upload of client drawings. **Effort.** 3-5 days. **Cost.** Low per job (minutes of time) plus an APS account. **Cloud.**

## 4. AutoCAD Electrical native reports and project database

- The Project Manager can export component details and wiring (Connections tab) to CSV or XLS [12].
- The Reports dialog covers every report type (From/To, wire labels, BOM, etc.), with output to ASCII, Excel, Access, XML or CSV [13].
- BOM and wire reports export through a default spreadsheet template, `wd_template.xls` (forum anecdote) [14].
- The project database is an Access file regenerated from the drawing set if missing. Edit a copy, not the live file [15]. Related `.MDB` files are catalog and update lookups [16]. Drawing-properties data lives in a hidden `WD_M` block at 0,0 of each drawing, not in the database [16].

**Pros.** Cleanest, most structured data (tags, wire numbers, from/to), authored by the tool that created it. Autodesk-supported.
**Cons.** Needs an AutoCAD Electrical seat and a human to run it. Only works for drawings that are actually AutoCAD Electrical schematics. Building-style panel schedules are usually plain AutoCAD tables or Revit exports, and Electrical's reports do not cover them. **Accuracy.** High where applicable. **Cost.** Seat license (not priced here). **Effort.** Hours to parse the CSV/XLS, but dependent on the user's workflow. **Local.** Offer it as a "bring your own export" input, not the main path.

## 4a. AutoCAD Electrical export formats (added; first input format for Redline)

**Verification status.** Autodesk's help pages describe report types and options but do not publish default column headings for most reports. Only the Panel BOM field codes were found. Everything marked "SAMPLE" below is NOT from a source. Get real exports from a user (see Redline action at the end).

**Report types** [25]
- Schematic reports: Bill of Material variants, Component, Wire From/To, Component Wire List, Connector Plug, PLC reports, Terminal Numbers, Terminal Plan, Connector Summary/Detail, Cable Summary and From/To, Wire Label.
- Panel reports: Bill of Material variants, Component, Nameplate, Wire Connection, plus Component/Terminal/Wire Annotation Exception reports.
- Terminal Plan is a schematic report, not a panel report (the coordinator's list grouped it with panel reports).

**Output options.** The Report Generator's Save to File sets file type and whether to include title lines, time, date and column labels [25][26]. The help pages do not enumerate file types. An Autodesk course says every report can go to ASCII, Excel, Access, XML or CSV [13], so CSV/XLS/MDB/XML is supported per that course, not per the dialog pages. Column set, order and labels are defined by a `.set` format file (AEFORMATFILE / "Change Report Format"), so headings are user-configurable and vary per company [26]. A report can also be inserted as a drawing table (Put on Drawing). Expect headings to differ between users; Redline needs a header-mapping layer.

**Panel BOM field codes** (the only documented set) [27]: ITEM, QTY, SUB, CATALOG, MFG, ASSYCODE, DESCRIPTION, DESC, QUERY2, QUERY3, MISC1-2, USER1-3, TABNAM, TAGS/TAG, DESC1-3, INST, LOC, UM, HDL, DWGIX, REF, SH, Source. Fields added via User Attributes also appear. SAMPLE header row: `ITEM,QTY,CATALOG,MFG,DESCRIPTION,TAG,INST,LOC,SH`.

**Nameplate, Wire Connection, Terminal Plan, Wire From/To.** No default headings found in help. SAMPLE guesses only (unverified): Wire Connection `WIRENO,FROM_TAG,FROM_PIN,TO_TAG,TO_PIN`; Nameplate `TAG,DESC1,DESC2,DESC3,INST,LOC`.

**Project Manager "Export to Spreadsheet" / "Update from Spreadsheet"** [28][29]
- Import/Export > Export > To Spreadsheet. Choose a category; "General" exports the starred categories each to its own sheet (Excel) or table (database). Tab- and comma-delimited formats are not available for multi-category exports, so single-category CSV/TXT or multi-sheet XLS only.
- Scope: current drawing or whole project; filter by location code (All/Blank/Named with wildcards).
- Template: `wd_xls_all_template.xlt` in `...\AutoCAD <ver>\Acade\Support\<lang>`; user-defined attributes appear automatically (for General/Excel, add them to the template worksheets).
- Columns: not fully enumerated in help. Documented: HDL and DWGNAME (do not edit; link edits to the drawing and block insert), attribute-named columns such as TAG1, DESC1-3, CAT, MFG [30]. Re-import all fields as text to avoid number conversion. Update cannot insert new items into drawings.

**Project database** [31]. Microsoft Access format, auto-regenerated from the drawing set, refreshed in the background by the Project Database Service on save. The help does not name the extension (.mdb vs .accdb) or location; the .wdp file sits in the project folder. Documented tables (14): COMP, TERMS, WNUM, PINLIST, COMPPINS, PLCIO, POSLIST, SIG, FILETIME, PNLCOMP, PNLTERM, PNLWDLEV, CONDUIT, USER. Edit a copy, not the live file [15].

**Is there a native "panel schedule"?** I found no AutoCAD Electrical object holding circuit/breaker/load/phase. The documented panel features are panel layout footprints and BOM, not circuit schedules. Panel schedules with breaker, load and phase appear in AutoCAD MEP (export to .csv text, one-way, not linked to Excel) [32], or in practice are plain AutoCAD tables, Excel pasted or linked as OLE, or Excel data links. This is an absence-of-evidence finding, so confirm with the user.

**DATALINK path** [33]. DATALINK creates an Excel link (whole sheet, named range or cell range) and TABLE "From a data link" places it as a table. DATALINKUPDATE syncs in either direction. Requires Excel installed. Implication: a linked schedule is an ACAD_TABLE in the DWG whose cell text is a cached copy, so reading the source XLSX is more reliable than reading the table. The XLSX path may be absolute and not shipped with the DWG.

**Implication for Redline's first input.** Treat the spreadsheet as the primary format: header-mapping layer, tolerate user-defined columns, import everything as text, preserve HDL/DWGNAME for traceability, and accept both single-category CSV and multi-sheet XLS(X). Ask the first customer for a real export of each report type to replace the SAMPLE rows above.

## 5. AutoLISP / .NET / COM extraction

- `DATAEXTRACTION` wizard writes CSV, TXT, XLS or MDB, and saves a reusable `.dxe/.dxex` settings file [17]. `ATTOUT/ATTIN` (Express Tools, not in LT) exports attribute data to CSV keyed by handle, but does not support dynamic block properties [18].
- The forum thread "extract data from a table using data extraction" suggests tables are not extracted directly [19]. Treat this as UNVERIFIED because I only saw the title.
- I found no sources on `pyautocad`, `win32com` or headless `accoreconsole`. From general knowledge: COM drives a running AutoCAD through `win32com`, and `accoreconsole.exe` runs scripts headless on a licensed machine. Neither was verified here.

**Pros.** Native fidelity for tables, fields, and dynamic blocks. **Cons.** Requires an AutoCAD seat (Windows), COM is slow and fragile, and it is not shippable to users without AutoCAD. **Effort.** 2-4 days. **Cost.** Seat license. **Local.**

## 6. ODA Drawings SDK (Teigha), commercial

Membership tiers (USD): Commercial $3,000 first year / $2,250 renewal, "limited commercial use"; Sustaining $7,500 / $4,500, unlimited commercial use and SaaS; Founding $37,500 / $18,000 with source. Non-commercial is $375 / $150 [20][21]. Termination ends the right to distribute ODA-based products [20].

It gives a C++/.NET (and some Java) API with full object-enabler fidelity, direct DWG read without conversion, and rendering. Python is not first-class (you'd wrap C++ or .NET). **Pros.** Most complete DWG reader outside Autodesk. **Cons.** Cost, a C++/.NET learning curve, and overkill for an MVP. **Effort.** 1-2 weeks. **Local.** Revisit only if ODAFC+ezdxf shows real data loss.

## 7. Open-source projects

I found no GitHub project that extracts electrical panel schedules from DXF/DWG. Closest finds:
- `jparedesds/extract-data-dxf`: ezdxf script that identifies entities, general-purpose, outputs DXF not CSV [22].
- `ezdwg` (PyPI): DWG reader with an ezdxf-like API, converts DWG to DXF, supports nested INSERTs and single-line ATTRIB. Maturity unknown, so test it before relying on it [23].
- A paid Apify actor extracts title-block `TAG: value` pairs to JSON/CSV [24]. Not open source.

So Redline would be building the schedule parser itself. That parser is also a differentiator.

## (a) Comparison table

| Option | Local/Cloud | Cost | License | Effort (solo) | Fidelity | Notes |
|---|---|---|---|---|---|---|
| ODAFC + ezdxf | Local | $0 | MIT + ODAFC freeware (terms unverified) | 1-3 days | Good; table/field risk | Best MVP |
| LibreDWG | Local | $0 | GPL-3 | 1-2 days | Medium (skips objects) | Fallback |
| APS Model Derivative | Cloud | Credits | Autodesk ToS | 2-3 days | Unproven for 2D props | Weak fit |
| APS Design Automation | Cloud | ~minutes/job | Autodesk ToS | 3-5 days | High (real AutoCAD) | Later, if cloud is OK |
| ACAD Electrical reports | Local (user) | Seat | Autodesk | Hours | Highest, schematic only | Optional import |
| LISP/.NET/COM | Local (seat) | Seat | n/a | 2-4 days | High | Needs AutoCAD |
| ODA SDK | Local | $3k-7.5k/yr | Commercial | 1-2 weeks | Very high | Overkill now |
| Open-source schedule parsers | n/a | n/a | n/a | n/a | None found | Build it |

## (b) Recommendation

**Weekend MVP.** ODAFC + ezdxf. Convert DWG to DXF, then dump ACAD_TABLE (via `read_acad_table_content`), MTEXT (via `plain_text()`), and all INSERT/ATTRIB per layer into a JSON intermediate model. Add a coordinate-based row/column clusterer for schedules drawn as loose text and lines. Also accept CSV/XLSX exports from AutoCAD Electrical or DATAEXTRACTION as a parallel input, since it costs almost nothing. Build a "raw extraction" JSON first so Redline's rules never touch DXF directly.

**Later.** Add Design Automation (or a user-side DATAEXTRACTION script) for files where ezdxf loses table or field content, once real customer drawings show the failure rate. Evaluate the ODA SDK only if data loss is proven and revenue justifies $3-7.5k/yr.

## (c) Gotchas

1. **Tables can be ACAD_TABLE or exploded geometry.** Some files carry the table only as an anonymous `*T` block or as loose lines and text. Handle both, and expect empty or stale cells when a cell is a FIELD [4].
2. **MTEXT formatting codes** (`\P`, `{\fArial;...}`, `\~`) pollute strings. Always use `plain_text()` [3].
3. **Attributes in nested and dynamic blocks.** Iterate `insert.attribs` recursively and watch for ATTDEF vs ATTRIB (a default value is not the real value). ATTOUT also skips dynamic-block properties [3][18].
4. **Model vs paper space and layouts.** Panel schedules often live in a layout (paper space) or an xref, so scan all layouts and block definitions, not just `msp`.
5. **Units, scale and DXF version.** `$INSUNITS` and viewport scale affect any geometric clustering. Row tolerances should be relative to text height, not absolute. ODAFC output version (R2018 max) also matters. Also run `odafc.is_installed()` at startup, because the converter path is configurable and runs an external executable [1].

## Sources
1. https://ezdxf.readthedocs.io/en/stable/addons/odafc.html
2. https://pypi.org/project/ezdxf/
3. https://ezdxf.readthedocs.io/en/stable/tasks/get_entity_content.html
4. https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-DXF/files/GUID-D8CCD2F0-18A3-42BB-A64D-539114A07DA0.htm
5. https://github.com/aka863/ezdxf (mirror; project description)
6. https://github.com/LibreDWG/libredwg
7. https://github.com/fr-an-k/libredwg/blob/master/libredwg.spec
8. https://aps.autodesk.com/en/docs/model-derivative/v2/reference/http/urn-metadata-guid-properties-GET
9. https://blog.autodesk.io/estimate-design-automation-costs/
10. https://coderapp.vercel.app/answer/79448282
11. https://www.autodesk.com/ca-en/benefits/flex/flex-rate-sheet
12. https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-Electrical/files/GUID-4BAA248D-9507-48F2-AED3-5B6272D2D927.htm
13. https://autodesk.com/learn/ondemand/course/electrical-engineering-for-manufacturing/unit/17IdjUIMoBGHtsC15JSsuh
14. https://forums.autodesk.com/t5/autocad-electrical-forum/bom-template-for-excel/m-p/5865325
15. https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-8DF798D6-F71A-413E-AD1B-ABBE8A6ACB81.htm
16. https://forums.autodesk.com/t5/autocad-electrical-forum/edit-drawing-properties-in-database/m-p/3211122/highlight/true and https://emea.support.arkance.world/hc/cs/articles/36469667866514-AutoCAD-Electrical-2021-Project-Related-Files
17. https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Core/files/GUID-BA68DD22-A3CD-4538-90A9-6101C33BC963.htm
18. https://forums.autodesk.com/t5/community-blog-general-english/manage-autocad-block-attributes-in-excel-using-attout/ba-p/13299112
19. https://forums.autodesk.com/t5/autocad-forum/can-i-extract-data-from-a-table-using-the-data-extraction/m-p/14085686
20. https://www.opendesign.com/pricing.md
21. https://www.opendesign.com/files/2025-05/Open%20Design%20Alliance%202025.pdf
22. https://awesome.ecosyste.ms/projects/github.com%2Fjparedesds%2Fextract-data-dxf
23. https://pypi.org/project/ezdwg/0.17.0/
24. https://apify.com/bossless/dwg-dxf-extractor.md
25. https://help.autodesk.com/cloudhelp/2017/ENU/AutoCAD-Electrical/files/GUID-7D6AD76C-FEC8-46DB-B610-64FC50C2F3B3.htm
26. https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-65DA310C-7B78-457F-A8E1-20CCCA1CD93C.htm
27. https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-Electrical/files/GUID-3A3BCEB5-C781-4E41-B0E5-C7B00F5EF7A2.htm
28. https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-Electrical/files/GUID-81DA5039-F987-43B7-8E10-BF4A68E42D1C.htm
29. https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-5287AAF9-E530-4F2F-BE02-64BA5BEEACB4.htm
30. https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-Electrical/files/GUID-A42DA038-B1AB-4401-BD71-BC7A683D8DF7.htm
31. https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-8DF798D6-F71A-413E-AD1B-ABBE8A6ACB81.htm
32. https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-MEP/files/GUID-5B68FCF5-0A15-418B-9EE6-F9B909FBE5EF.htm
33. https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-LT-MAC/files/GUID-E6AD1DCE-6A0A-4714-808E-FA4D895C2E7B.htm and https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-LT-MAC/files/GUID-5E118F6D-D19C-4B59-8E54-53016B4F8AB8.htm
34. https://github.com/mozman/ezdxf/blob/master/src/ezdxf/entities/acad_table.py
35. https://aps.autodesk.com/pricing (via search summary only)
36. https://www.cadforum.cz/cadforum_en/running-autocad-without-the-graphics-window-tip8552 (accessed 2026-11-06)
37. https://fdestech.com/resources/accoreconsole-guide-headless-cad-automation/ (vendor blog; performance and licensing claims unsourced; accessed 2026-11-06)
38. https://forums.autodesk.com/t5/autodesk-community-tips-adnopun/autocad-2025noaccoreconsole-exe-desystem-data/ta-p/13418763 (2025 .NET 8 / System.Data.OleDb crash; via search summary, page returned 403; accessed 2026-11-06)
39. https://forums.autodesk.com/t5/net-forum/netloading-dll-from-a-script-file-for-batch-processing/m-p/5947184 (via search summary; accessed 2026-11-06)
40. https://aps.autodesk.com/developer/overview/autocad-electrical-api (accessed 2026-11-06)
41. https://ezdxf.readthedocs.io/en/stable/xref.html (accessed 2026-11-06)
42. https://www.opendesign.com/oda-membership.md (accessed 2026-11-06)
43. https://pypi.org/project/cad-pyrx/ (accessed 2026-11-06)
44. https://pypi.org/project/pyautocad/ (via search summary: 0.2.0, 2015-12-21; accessed 2026-11-06)
45. https://forums.autodesk.com/t5/vba-forum/accoreconsole-exe-license-error/m-p/6849875 (via search summary; accessed 2026-11-06)
46. https://www.cadforum.cz/en/command.asp?Core= (commands unavailable in Core Console; via search summary; accessed 2026-11-06)
47. https://forums.autodesk.com/t5/visual-lisp-autolisp-and-general/plot-does-not-work-in-core-console-2021-accoreconsole-exe/td-p/10133791 (via search summary; accessed 2026-11-06)
48. https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Electrical/files/GUID-75AEBC13-2F09-4B9E-B349-C7B202D52119.htm (WD_M block; accessed 2026-11-06)
49. https://help.autodesk.com/cloudhelp/2023/ENU/DWGTrueView/files/GUID-E123319D-D1E2-43BE-94E2-CE39CF04F0C9.htm (TrueView batch conversion, .BCL; via search summary; accessed 2026-11-06)
50. https://www.capterra.com/p/159378/BricsCAD/pricing/ and https://novedge.com/collections/bricscad-september-savings-promo (BricsCAD Lite pricing, via search summary; accessed 2026-11-06)
51. https://developer.bricsys.com/bricscad/help/en_US/V25/DevRef/source/html/f2e21714-2c8f-af07-05b8-2944e42ea96c.htm (BricsCAD .NET table GetTextString; accessed 2026-11-06 via search summary)
52. https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-Electrical/files/GUID-FD3F36A0-01B7-44D2-8B73-81721934A6BD.htm (.wdp file; via search summary; accessed 2026-11-06)
53. https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-LT-MAC/files/GUID-E9E1FDCC-6724-4AD4-9BD7-D726F22158E9.htm (custom and proxy objects; accessed 2026-11-06 via search summary)
54. https://www.opendesign.com/pricing.md (re-fetched 2026-11-06; same as [20])
55. https://pypi.org/project/ezdxf/ (re-fetched 2026-11-06; same as [2])

## Part 2: Full-project DWG decision (added 2026-11-06)

All URLs accessed 2026-11-06; numbers refer to the Sources list above. Many Autodesk forum pages returned 403 to my fetcher, so those claims rest on search-result summaries and are tagged. UNVERIFIED means "not confirmed by a primary source; test on the owner's machine." Nothing here was run on a real AutoCAD install.

### 1. AutoCAD Core Console (`accoreconsole.exe`)

**Exists and is old.** It was introduced in AutoCAD 2013 as an EXE in the AutoCAD folder, a console build with no graphics window [36]. A 2026 vendor guide says it ships with every AutoCAD since 2013 [37]. I did not find a primary Autodesk page naming the 2025 or 2026 install path, and the Autodesk 2025 developer-help link I tried returned "page not found." A 2025 forum tip shows it running on AutoCAD 2025 (and being affected by the .NET 8 move), which is indirect evidence it is present there [38]. Verify the file on disk (see section (c)).

**Invocation.** Switches are `/i <dwg>`, `/s <script>`, `/l <lang>`, `/product`, `/isolate <userid> <dir>`, `/readonly`, `/p <profile>`, `/loadmodule` [36]. Typical call: `accoreconsole.exe /i "C:\in\a.dwg" /s "C:\work\run.scr" /l en-US`. Scripts are one command per line; a hyphen prefix forces the command-line form of a command; `FILEDIA` is forced to 0 [37]. `/isolate` keeps system-variable changes from leaking into the user's normal AutoCAD profile [37].

**.NET and LISP.** A plugin built against `AcCoreMgd.dll` loads from the script with `NETLOAD <path>` followed by the registered command name [37][39]. Forum guidance is to use forward slashes and no quotes in the DLL path inside a script (secondary, via search summary) [39]. Network-share DLLs need extra .NET security setup [37]. Core AutoLISP works, but `vla-*` and `vlax-*` ActiveX functions do not [37] (a forum thread said the same; UNVERIFIED). Practical consequence: write the extractor in C# against the managed API, not in Visual LISP.

**2025+ risk.** AutoCAD 2025 moved to .NET 8, which has no AppDomain isolation. A Japanese Autodesk community tip reports accoreconsole crashing when a plugin pulled in its own `System.Data.OleDb`, with the workaround of referencing the copy shipped in the AutoCAD folder [38] (via search summary). Rule: reference only Autodesk's assemblies plus `System.Text.Json`, and never copy-local anything Autodesk already ships.

**Commands that do not work.** Only commands implemented in `accore.dll` work, and dialog-driven commands fail. Autodesk's developer help reportedly says Core Console supports many but not all commands (search summary; the page itself did not load, UNVERIFIED) [46]. `-PLOT` reportedly fails in the 2021 Core Console [47]. The `DATAEXTRACTION` wizard is dialog-based, so assume it is not available (UNVERIFIED). It does not matter if you extract in C#.

**AutoCAD Electrical drawings and proxies.** Electrical symbols are ordinary blocks with attributes, and the WD_M settings block is also a block with attributes [48]. Any Electrical custom objects would load as proxy objects when the enabler is absent [53]. Whether Core Console loads the Electrical object enabler, or whether Electrical's own LISP commands exist in it, is UNVERIFIED. A vendor guide says vertical-product commands "may not be available" without evidence [37]. For Redline this mostly does not matter: block references, attributes, text and tables are core database objects that read fine without the vertical.

**Licensing.** Sources disagree. The vendor guide says "no extra license" but also "requires a local AutoCAD license" and that Autodesk does not officially support it [37]. An older forum thread shows a network-license error when an app launched accoreconsole [45] (via search summary). I found no Autodesk statement on whether a headless run consumes a concurrent seat, or whether a server install is allowed under a named-user subscription. UNVERIFIED, and a real compliance question: ask Autodesk or the reseller in writing. The safe pattern is to run it on the named user's own workstation, or on a machine explicitly licensed for it.

**Speed.** The only numbers I saw (under 1 s startup, 145 drawings in 11 min vs 58 min) come from a vendor blog with no methodology [37]. UNVERIFIED. Measure it; expect seconds per file.

**Verdict.** Highest-fidelity local option, near-zero marginal cost with an existing seat, unattended by design (subject to the licensing question).

### 2. AutoCAD .NET API extraction plugin (C#)

**What the plugin iterates.** This is design intent from general knowledge of the managed API, not re-verified here. Open the `Database`, walk `BlockTable`, and for each `BlockTableRecord` (model space, every layout's paper space, and block definitions) enumerate entities. Relevant types: `BlockReference` (its `AttributeCollection`, `DynamicBlockReferencePropertyCollection`), `Table` (cells via the cell API), `MText` (use `.Text`, which strips formatting; `.Contents` is raw), `DBText`, `MLeader`. Xrefs: `BlockTableRecord.IsFromExternalReference` plus `PathName`, then `Database.ReadDwgFile` and recurse, or `ResolveXrefs`.

**Tables and fields.** The AutoCAD ActiveX reference documents `GetTextString(row, col, contentIndex)` for reading a cell value (search summary); BricsCAD's .NET table class mirrors it [51]. The exact AutoCAD .NET member and whether it returns evaluated field text are UNVERIFIED. The point: because real AutoCAD evaluates fields, this is the only local route that may return computed field values rather than the cached string or a bare field object ID (contrast Part 1 [4]). Test with a table holding a FIELD and a DATALINK table.

**AutoCAD Electrical data.** Autodesk lists the Electrical API as reachable from AutoLISP, VB.NET, C#, C++/ARX, VBA or script files [40]. I could not retrieve the function reference. So do not depend on `c:wd_*` or `ace_*` calls: read tags, wire numbers and `WD_*` attributes as plain block attributes, and treat the project database as a separate input (section 6).

**Driving it.** Yes. Write a `[CommandMethod("REDLINE_DUMP")]`, `NETLOAD` it from a script, and have it write `<dwg>.redline.json`. Core Console takes no easy arguments, so generate a per-run `.scr` and pass the output path through an environment variable or sidecar file. Python calls `subprocess.run([accoreconsole, "/i", dwg, "/s", scr], timeout=...)` and reads the JSON.

**Effort.** 3 to 5 days for a plugin that dumps layouts, inserts with attributes, tables, MTEXT and xref names, plus 2 to 3 days for testing and packaging across the firm's AutoCAD versions (2025+ is .NET 8; older seats are .NET Framework, so one build may not cover both; which versions the firm runs is UNVERIFIED).

### 3. COM automation from Python

`pyautocad` is stale: PyPI shows 0.2.0 from 2015-12-21 [44] (via search summary). It is a thin wrapper over `win32com`/`comtypes`. A newer option is `cad-pyrx` (LGPLv3, Windows, AutoCAD 2022-2027 plus BricsCAD, ZWCAD, GstarCAD, release 2026-11-01, Python 3.14 only), which exposes ObjectARX and ActiveX and is loaded inside the CAD app via `APPLOAD` [43]. It does not mention accoreconsole, so whether it can run there is UNVERIFIED. COM needs the GUI process, is slow per property access and prone to modal-dialog hangs (general knowledge, UNVERIFIED here). Electrical's COM/VBA object model: VBA is listed [40], but I could not verify it. Verdict: prototyping or a "send current drawing" button only. Not for unattended ingest. 2-3 days.

### 4. ODA File Converter + ezdxf (additions to Part 1)

- **Release and speed.** ezdxf 1.4.5, 2026-10-16, MIT; PyPI metadata disagrees on Python 3.10 vs 3.11; optional C extensions ship in binary wheels; no published benchmarks [2][55]. `iterdxf` streams DXF files too large for memory [55]. Measure on real drawings.
- **Xref.** `ezdxf.xref` (added in 1.1) has `attach`, `define`, `detach`, `embed`, `load_modelspace`, `load_paperspace`, `write_block`. It does not support ACAD_TABLE or preserved proxy entities; they are silently ignored [41]. So do not use `embed` or `load_*` to merge xrefs if tables matter. Convert each referenced DWG separately with ODAFC and read it as its own document, then link by block name. Non-absolute xref paths resolve relative to the host file and `search_path`; paperspace loading does not bring modelspace content seen through viewports [41].
- **Recover.** `ezdxf.recover.readfile()` is the tolerant loader for damaged DXF and returns a tuple with the document first (per the xref tutorial pattern) [41]. Use it as a fallback when `ezdxf.readfile` raises.
- **Proxy entities.** Unknown objects are kept as opaque data, so any Electrical custom objects are invisible to extraction. The data Redline needs lives in blocks and attributes, which are ordinary entities (consistent with [48]). Confirm on real files.
- **Unattended.** `odafc.readfile` runs an external exe and suppresses the GUI on Windows [1]. ODAFC redistribution terms stay UNVERIFIED (the membership page does not mention it) [42].
- **Community.** ezdxf released 1.4.5 in Oct 2026 [2]; pyautocad is dormant since 2015 [44].

### 5. ODA SDK pricing and Python

2026 tiers match 2025: Commercial $3,000 / $2,250 renewal (limited commercial use, up to 100 copies), Sustaining $7,500 / $4,500 (unlimited, SaaS allowed), Founding $37,500 / $18,000 (with source) [20][54][42]. Commercial membership does not permit Web/SaaS use [42]. A Python wrapper exists but only for the Drawings SDK, at the Core Package and Core Package+ levels [42]; I did not find the price of those packages. Non-commercial $375 / $150 per Part 1 [21] (the 2026 price PDF came back garbled). If Redline is ever offered hosted and built on ODA tech, Sustaining ($7,500 first year) is the floor. Direct DWG reading without conversion is the benefit, and it is not needed for internal use while AutoCAD seats exist.

### 6. AutoCAD Electrical specifics

- **`.wdp`** stores project properties as numbered bracketed entries, many mirrored on WD_M [52] (via search summary). It is a text file, so Python can parse it directly. Confirm the drawing-list format on a real file.
- **`WD_M`** is an invisible block that must exist in each drawing and carries drawing-wide settings as attributes (sheet, tagging, wire-number format, layer names, cross-reference format, referencing, and so on) [48]. ezdxf reads it as a normal INSERT.
- **Project database.** Part 1 [31]: Access format, 14 documented tables (COMP, TERMS, WNUM, PINLIST, COMPPINS, PLCIO, POSLIST, SIG, FILETIME, PNLCOMP, PNLTERM, PNLWDLEV, CONDUIT, USER). I could not find the extension or column names. Reading from Python needs the Microsoft Access ODBC driver with `pyodbc` on Windows (general knowledge). Edit a copy, not the live file [15].
- **Scripted reports.** I could not confirm a documented single command that exports all reports headlessly. `WD.ENV` has `WD_OPEN_DWG`, which runs a LISP program on drawing open, so hooks exist, but headless use is UNVERIFIED (search summary of Autodesk help pages). Plan on reports run by a human, or the plugin reading blocks directly.

### 7. Other paths

| Option | Facts | Verdict |
|---|---|---|
| DWG TrueView | Free; batch conversion through the GUI and `.BCL` lists; no command-line scripting found [49] | DWG conversion only; ODAFC does this better |
| BricsCAD Lite | About $293 to $350 per year, perpetual about $590, network perpetual needs 5 seats [50]. BRX/.NET/LISP exist and its .NET table class has `GetTextString` [51]. Headless mode and Lite's API limits not verified | Possible cheaper server seat, but needs its own plugin; not worth it while AutoCAD is on hand |
| LibreDWG | Part 1 | Cross-check only |
| nanoCAD, QCAD, LibreCAD, FreeCAD, ODA Drawings Explorer | Not researched this pass; LibreCAD is DXF only and FreeCAD DWG import uses the ODA converter (general knowledge, UNVERIFIED) | Skip |

### (a) Decision matrix

| Option | Local/Cloud | Unattended | Table and field fidelity | Electrical drawings | Cost with existing seat | Effort (days) | Licensing risk |
|---|---|---|---|---|---|---|---|
| accoreconsole + C# plugin | Local | Yes | Highest (real AutoCAD) | Blocks/attributes fine; vertical commands unverified | $0 extra | 5-8 | Seat use on a server unclear |
| COM from Python | Local | No (GUI) | High | Fine | $0 | 2-3 | Seat held by GUI session |
| ODAFC + ezdxf | Local | Yes | Medium (field cells may be stale) | Fine for blocks/attributes | $0 | 2-3 | ODAFC redistribution unverified |
| APS Design Automation | Cloud | Yes | Highest | Electrical support unverified | Flex tokens | 4-6 | Client data leaves the building |
| ODA SDK (Python wrapper) | Local | Yes | High | Unknown | $3,000 to $7,500 per year | 7-10 | ODA terms; SaaS needs Sustaining |
| BricsCAD plugin | Local | Probably | Unknown | Unknown | $300 to $600 | 8-12 | Unknown |
| LibreDWG | Local | Yes | Low to medium | Unknown | $0 | 1-2 | GPL-3 |
| Electrical reports / `.mdb` / `.wdp` | Local | Partial | Highest for tags and wires | Schematic data only; no panel schedule | Seat | 1-2 | None |

### (b) Recommended architecture

**Contract.** Every extractor emits one `RawDrawing` JSON: layouts, blocks, attributes, tables as 2D string arrays, positioned text, xref list, plus provenance (extractor name and version, AutoCAD version, source file hash, per-item handle). Redline rules read only this JSON, never DXF or DWG.

1. **Primary (seat present): C# plugin via accoreconsole.** It is the only path that may evaluate fields and handle tables and proxies the way AutoCAD does, it runs unattended, and it costs nothing extra. A Python wrapper builds the `.scr`, runs the subprocess with a per-file timeout, and validates the JSON.
2. **Fallback (no seat, or accoreconsole fails): ODAFC + ezdxf**, same schema. `recover.readfile` on damaged files, xrefs converted separately, Part 1's loose-text row/column clusterer.
3. **Side inputs:** Electrical report CSV/XLSX, `.mdb` and `.wdp` parsers, and DATALINK source XLSX when reachable.
4. **Cross-check job:** run both extractors on the same file and diff table, INSERT and ATTRIB counts. This yields a measured data-loss rate for the fallback.
5. **Defer:** APS Design Automation and the ODA SDK, until the owner needs seat-less server ingest or hosted SaaS.

Why: only the plugin needs a seat, and it sits behind a JSON contract, so losing the seat does not break the product.

### (c) First-week checks on the owner's machine

1. Find the exe: `Get-ChildItem "C:\Program Files\Autodesk" -Recurse -Filter accoreconsole.exe -ErrorAction SilentlyContinue`. Note the AutoCAD version, and whether AutoCAD Electrical is its own product folder with its own copy.
2. Smoke test: a `t.scr` containing `_QSAVE`, then `& $exe /i C:\test\sample.dwg /s C:\test\t.scr /l en-US`. Time it, on both a plain DWG and an Electrical DWG. Watch for license dialogs or network-license errors [45].
3. Licensing: run it with AutoCAD closed, then with AutoCAD open under the same user, and check the Autodesk Account for seat use. Email the reseller asking if headless use on a shared machine is allowed. This resolves the biggest UNVERIFIED.
4. NETLOAD test: a 20-line C# command built against `AcCoreMgd.dll`/`AcDbMgd.dll`, loaded from the `.scr` with forward slashes. If it crashes on 2025+, try the [38] workaround.
5. Table test: a DWG with a plain table, a table with a FIELD, and a DATALINK table. Dump cell text with the plugin and with `read_acad_table_content` and compare.
6. ODAFC: check `C:\Program Files\ODA\ODAFileConverter\` and run `python -c "from ezdxf.addons import odafc; print(odafc.is_installed())"`. Compare INSERT/ATTRIB counts against the plugin.
7. In a real Electrical project folder look for `*.wdp`, `*.mdb` or `*.accdb`, `WD.ENV`, `wd_xls_all_template.xlt`; open one drawing's `WD_M` attributes; list the `.mdb` copy's tables and columns with Access or `pyodbc`.
8. Ask which AutoCAD versions staff run, how panel schedules are made (native table, Excel link, exploded text, Revit export), and gather about 10 real drawings as a test corpus.

### (d) Gotchas

- Accoreconsole has no official Autodesk documentation or compatibility guarantee [37]. Pin the AutoCAD version per extractor release and write it into the JSON.
- AutoCAD 2025+ is .NET 8, so plugins build per major version; keep dependencies tiny [38].
- Script quirks: forward slashes, unquoted NETLOAD path, `FILEDIA` 0 [37][39]. Check the output JSON, not the exit code.
- Proxy-based entities may be opaque in ezdxf yet readable in AutoCAD with the enabler [53]; the cross-check job will show it.
- `vla-*` LISP does not run in Core Console [37]; prototype in C#.
- `ezdxf.xref` drops tables and proxies [41]; unresolved xref paths are common in client packages, so log which were missing.
- Fields and Excel links may refresh on open and change values. Open with `/readonly` [36] and log the file hash.
- Cloud paths (APS) upload client drawings; confirm contract and region first.
- Electrical reports are not panel schedules (Part 1 section 4a); the building panel schedule is probably a plain table or loose text.
