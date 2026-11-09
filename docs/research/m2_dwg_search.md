# M2 real DWG search, 2026-11-09

Three Sonnet agents searched the web for real DWG or DXF drawings with electrical panel schedules, at M2 stage 1. Nothing was downloaded. No usable, redistributable real panel-schedule DWG was found, so M2 uses synthetic fixtures (PLAN.md row 38). The one public real ACAD_TABLE file is the ezdxf integration test file `acad_table_with_blk_ref.dxf` (MIT); whether it holds electrical content is UNVERIFIED.

## Scope: vendor


Nothing was downloaded. Based on web search plus page fetches. No candidate was verified as a native ACAD_TABLE.

## Bottom line
Official and vendor channels give almost nothing usable. Autodesk publishes no downloadable sample panel-schedule DWG (AutoCAD MEP help describes built-in table styles only). Square D and Eaton host CAD for panelboard enclosures and interiors, not filled schedules. The only filled schedules found are on paid or terms-restricted aggregator sites, and none can be redistributed.

## Filled schedules (candidates)
1. DesignsCAD, residence electrical installation. https://designscad.com/downloads/residence-electrical-installation-dwg-block-for-autocad/
   - DWG, version and size not stated.
   - Page text lists a symbol legend plus several sub-distribution board schedules and a main distribution board, with breaker ratings, wire sizes, circuit descriptions and kVA loads.
   - Table type UNVERIFIED. Region and wire-size system UNVERIFIED (the page mentions kVA).
   - $3.87 premium, or $7/month. Account likely needed. No licence stated; general T&C only. Treat as private use only.
2. CADBull, electrical layout with panel schedule (metric 4mm/6mm cable, MCB ratings). https://cadbull.com/amp/272323/electrical-layout-dwg-panel-schedule-cable-4mm-6mm-load-plan
   - WebFetch returned 403, so contents UNVERIFIED beyond the search snippet.
   - Metric, so not AWG/NEC-style. Licence and login UNVERIFIED. Likely registration required and personal use only.
3. CADBull, electrical panel wiring with load schedule. https://cadbull.com/detail/3873/ELECT'L-20
   - Contents and format UNVERIFIED (403 risk as above). Licence UNVERIFIED.
4. DesignsCAD, residential electrical plan (lighting and power plans, load schedule). https://designscad.com/downloads/residential-electrical-plan-dwg/
   - Described in search results as free in one case. UNVERIFIED. Not fetched.
5. DesignsCAD, complete electric plan for classrooms and schools. https://designscad.com/downloads/complete-electric-plan-ideal-for-classrooms-and-schools-dwg-full-project-for-autocad/
   - Schedule presence UNVERIFIED. Not fetched.

## Templates / blocks only (no filled schedule)
- Autodesk AutoCAD MEP help, default panel schedule table styles (1-phase and 3-phase branch circuit, switchboard). https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-MEP/files/GUID-2F354B01-0E37-49B2-B247-60E6D8F7B7CF.htm
  Documentation only, no download. Styles ship inside the MEP install (Autodesk EULA, no redistribution assumed).
- ArcSite electrical panel CAD block. https://www.arcsite.com/blocks/electrical-panel-cad-block
  DWG/DXF/PNG/PDF. Exterior enclosure elevation, no schedule. No licence stated. Form or app account probably needed.
- CADforum.cz panelboard blocks (e.g. https://www.cadforum.cz/catalog/block.asp?blk=13850). Panelboard symbol DWG blocks, no schedule. Site says personal or company use only.
- draftsperson.net electrical symbols. https://blocks.draftsperson.net/download-category/electrical-symbols  Symbol libraries, no schedule.
- DesignsCAD electrical distribution panel block, $3.87. https://designscad.com/downloads/electrical-distribution-panel-dwg-block-autocad/  Block only.
- Clemson sample panel schedule is .docx, not CAD: https://cufacilities.sites.clemson.edu/documents/capital/Sample%20Electrical%20Panel%20Schedule.docx

## Vendors
- Schneider/Square D: CAD per catalog number via se.com product pages, and zoro.com listings show "CAD Viewer & Download Files". Enclosure/interior geometry; no filled schedule. Download may need login or T&C acceptance. UNVERIFIED.
- Eaton Pow-R-Line pages (e.g. https://www.eaton.com/us/en-us/catalog/low-voltage-power-distribution-controls-systems/pow-r-line-1x-lighting-and-appliance-panelboards.html) have a "Download Links" panel; file types not visible. Likely submittal or enclosure drawings. UNVERIFIED.
- Siemens, ABB: not searched in depth.
- ARCAT (https://www.arcat.com/content-type/cad/26) hosts manufacturer CAD; free with registration, device or enclosure drawings. UNVERIFIED.

## Not found
- No Autodesk Knowledge Network or Autodesk University dataset with panel schedules.
- No AutoCAD Electrical sample project located by search (AutoCAD Electrical ships sample projects in its install, not installed on the user's PC).
- No file confirmed as ACAD_TABLE.

## Suggestion
Official and vendor sources are a poor fit. Better leads: public-agency or university "CAD standards" pages, GitHub repos of DXF test files, and municipal permit sample sets. Another agent presumably covers these.

## Scope: public


Result: weak. Public tenders overwhelmingly publish electrical drawings as PDF. No confirmed filled-panel-schedule DWG found. Only 0 confirmed, 3 partial leads.

## Leads (all UNVERIFIED for content)

1. UBC Technical Guidelines, Standard Drawings (Canadian, public page, no login seen)
   - Page: https://technicalguidelines.ubc.ca/technical/standard_drawings.html
   - DWG files at relative path files/Div26/ (e.g. E10-2.dwg "Standard Transformer and Panel Identification", E1-4.dwg typical electrical room layout, E1-1/E1-2 single-line). Resolved URL likely https://technicalguidelines.ubc.ca/technical/files/Div26/E10-2.dwg (UNVERIFIED, relative path).
   - Format: DWG, version not stated. Size not shown.
   - Panel schedule: none listed by title; these are standard details, not filled schedules. E10-2 may have panel identification tables (UNVERIFIED).
   - Licence: none stated on page; footer "Terms of Use" not read. Treat as private use only until read.

2. University of Toronto Electrical Design Standard Rev 02 (Canadian)
   - https://www.fs.utoronto.ca/wp-content/uploads/2024/04/Electrical-Design-Standard-Revision-02.pdf
   - Lists 3-phase, 24-circuit and 42-circuit panel schedule templates (per search snippet). The PDF is a PDF; whether DWG templates are offered is UNVERIFIED. Likely request from facilities.

3. University of Calgary Drawing Standard 8.1 (Canadian)
   - https://live-ucalgary.ucalgary.ca/sites/default/files/teams/223/Design%20Standards/8.1%20Drawing%20Standard.pdf
   - Says to show panel schedule on power plan. Contact cad.bimadmin@ucalgary.ca for templates. No DWG link seen. UNVERIFIED.

## Checked, not useful
- Winnipeg tenders (legacy.winnipeg.ca/finance/findata/matmgt/...): real filled panel schedules (e.g. Tender 447-2024 PNL-Y7020, 954-2023B E6.11) but PDF only. Title blocks show .dwg source names. DWGs not published. Drawings typically carry engineer copyright / no-reproduction notice. Could ask City of Winnipeg Materials Management or the consultant for CAD (likely under agreement).
- Other Canadian PDF-only tenders: Muskoka Lakes T-2024-12, Morden 25F148, CanadaBuys 2016 addendum_1_elect_ske001.
- US PDF-only: Maine BGS 3159 addenda, Hanford RFP 390982 Attach 1a, NM Tech Review Set, Shelby County TN.
- GSA / NAVFAC / VA / PSPC CAD standards: title-block, layer and template ZIPs only (GSA Great Lakes and Mid-Atlantic ZIPs, NAVFAC on wbdg.org). No panel schedule DWG seen. Public/federal, so licensing likely permissive, but nothing relevant.
  - https://gsa.gov/cad ; https://www.wbdg.org/navy/cad ; https://www.canada.ca/en/public-services-procurement/services/infrastructure-buildings/computer-aided-design-drafting-standards.html
- LANL engstandards (403 on fetch), LBL facilities (404 on fetch). LBL reportedly lists panel schedules by building (format unknown, UNVERIFIED): https://facilities.lbl.gov/resource/documents/engineering/for-project-managers/
- Yale, UCSD, Duke, UH, Rutgers, ASU, UAF CAD standards: PDFs describing layers/submittals, no sample electrical DWG found.
- GitHub / open-source building projects with DWG electrical sets: none found.

## Non-public-sector fallback (commercial, NOT for redistribution, outside my scope)
- DesignsCAD free items, e.g. https://designscad.com/downloads/school-electrical-installation-dwg-plans-schedules/ (MDB/SDB schedules, load calcs; non-Canadian, likely often not CEC). Cadbull panel schedule layout https://cadbull.com/amp/272323/electrical-layout-dwg-panel-schedule-cable-4mm-6mm-load-plan . Terms restrict redistribution (UNVERIFIED; both usually require registration/login to download).

## Recommendation
Public portals will not deliver 10 real DWGs. Realistic route: email requests to Winnipeg Materials Management (CAD for specific tenders), U of T / UBC / Calgary facilities CAD admins for sample sets, and ask a consultant for permission-granted files. Confirm redistribution rights in writing before putting any in a public repo.

## Scope: corpora


## Part 1: AutoCAD Electrical sample projects
- Tutorial/demo projects (wddemo.wdp, Basic_Workflow_NFPA.wdp, PLC_Modules_NFPA.wdp) ship INSTALLED with the product:
  Users\{user}\Documents\Acade {ver}\Aedata\Tutorial\Aegs\{tutorial}  (source: https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Electrical/files/GUID-278B5C59-687D-43E8-BC2C-8FDE467D8167.htm)
- No standalone public download found. NFPADEMO: no hit at all. WDDEMO: only as LinkedIn Learning/Lynda course exercise files (subscription, https://www.lynda.com/AutoCAD-Electrical-tutorials/Use-exercise-files/789012/5003579-4.html), licence = course terms, NOT committable.
- Autodesk Learn on-demand PLC module references PLC_Modules_NFPA.wdp (https://www.autodesk.com/learn/ondemand/module/autocad-electrical-essentials-10-plc-modules/unit/4FGkA00vdcA1KCOUfhfKGY); whether exercise files are downloadable there: UNVERIFIED.
- Any such files: Autodesk EULA, not redistributable in a public repo.
- CADforum content packs (https://www.cadforum.cz/en/download.asp?file=ACADE): symbol libraries only, not projects.
- Verdict: no AutoCAD Electrical sample project obtainable without a seat (trial install would be the route; still not committable).

## Part 2: open corpora
1. ezdxf integration_tests/data, MIT (https://github.com/mozman/ezdxf/blob/master/LICENSE), committable with notice.
   Listing: https://sources.debian.org/src/ezdxf/1.4.3-1/integration_tests/data (39 files; repo path mozman/ezdxf/integration_tests/data)
   - acad_table_with_blk_ref.dxf, 156,603 bytes: ONLY confirmed ACAD_TABLE file; used by integration_tests/test_acad_table.py and examples/entities/read_acad_table.py. Contents beyond "table with block ref": UNVERIFIED (likely not electrical).
   - custom_blocks.dxf 163,907 B (blocks/attribs likely, UNVERIFIED), dynblks.zip 56,494 B, groups.dxf, mtext_*.dxf, bin_dxf_r*.dxf, recover01/02.dxf (broken-file recovery).
   - No FIELD or DATALINK sample files found.
   - ezdxf man page says some stress/audit DXF files are not published (rights).
2. LibreDWG test/test-data, GPL-3.0 (UNVERIFIED per-file; repo GPL means committing to a public repo carries GPL obligations; use as local-only fixture).
   https://github.com/LibreDWG/libredwg/tree/master/test/test-data
   - top level: example_2000/2004/2007/2010/2013/2018/r13/r14 (.dwg/.dxf), sample_2000/2018 .dwg, sample_*.dxf, example_*.dxfb; subfolders 2000..2018, r1.4..r14 (contents not inspected). Sizes not shown. No file named for table/field/attrib.
   - GNU manual says TABLE only works pre-2010; manual asks for extended example_2018.dwg with all types, so table coverage is thin (UNVERIFIED).
   - Mirror of old samples: https://libreplanet.org/wiki/Group:LibreDWG/DWG_files (UNVERIFIED licence).
3. Autodesk AutoCAD sample files page https://autodesk.com/autocad-samples (HTTP 403 to fetcher; search snippet lists "Blocks and Tables (Metric)" dwg). Autodesk terms, not redistributable; UNVERIFIED electrical content. Also https://autodesk.com/autocadlt-samples.
4. Others (leads only, UNVERIFIED): https://github.com/codelibs/libdxfrw "test files" section; https://www.cadforum.cz/en/download.asp?file=Test (404 to fetcher); https://sourceforge.net/projects/libdwg-testsuite/ (GPLv3); https://people.math.sc.edu/Burkardt/data/dxf/dxf.html (LGPL-ish, UNVERIFIED, mostly geometry).
- Not found: any GitHub repo with real electrical panel-schedule DWGs. ODA/Teigha sample files: no public sample set found.

