# Redline research: existing products for drawing extraction and code checking

Researched 2026-11-06 (second pass: key pages opened with WebFetch, thin topics re-searched in extended mode). Legend: [V] = opened and confirmed on the vendor page; [S] = from a search summary only, not opened; [U] = could not verify. Most accuracy numbers are vendor claims.

## 1. Drawing and takeoff tools

**Bluebeam Revu [V].** Official pricing page [1]: Basics $260, Core $330, Complete $440, Max $590 (introductory), per user per year, billed annually, tiers can be mixed. Core: advanced measurement (perimeter, count, angle, volume), overlay/comparison, CAD plug-ins. Complete: Dynamic Fill, Quantity Link with Excel, advanced markup reporting, batch hyperlink and slip sheet automation, scripting commands. Max: AI drawing reviews, AI drawing comparisons, MCP integration, multi-view stitching [1]. Structured export is via the Markups List (CSV summary per third-party guides [S][2]; BAX XML in older help [S]). It does not turn schedule tables into data. Note Bluebeam now sells "AI drawing review" at the top tier, so reviewers will expect AI assistance.

**CountFire [S].** Electrical symbol counting across multi-PDF sets from one example; reuses counts for revised drawings; overlay compare; reviews say recognition is "not always accurate" [3]. Price not found.

**Togal.AI [V].** Homepage claims "98% accuracy on floor plans" and "up to 98%", with no method or independent verification; no prices on the page; the page does not say whether it detects symbols [4]. Blog price of $299/user/month is [U].

**Kreo [V].** Pricing page: Essential (no AI) $100/user/mo, Pro (AI takeoff, 1-4 users) $175, Business $250 (5-20 users, 5 seats included), Enterprise custom; 7-day trials [5]. No quantified accuracy claim on the page; the earlier "95%" and "$35/$70" figures from a blog are [U] and are likely wrong or outdated [5].

**Procore Drawings OCR [S, support articles].** OCR fills sheet number, title and discipline (discipline inferred from number prefix) at upload; titles on revisions are carried from the prior revision; corrections re-tune detection for the remaining sheets. Procore advises labelled title block fields and a simple sans-serif font; OCR only knows English/Spanish/French/German dictionaries. Callout auto-linking works far better on vector PDFs; raster files misread characters (S vs 5); callouts drawn as lines are not detected; there is no way to confirm a sheet was fully processed, so Procore says to test a few samples first [6]. Lesson: vector PDF in, test sample, admit unprocessed content.

**ACC Model Coordination [S].** Clash detection across uploaded RVT/DWG/NWC/IFC models, per model-set version; clashes grouped by system, object type or layer; reviewer marks each "issue" or "not an issue" and converts to assigned issues with due dates [7]. AutoSpecs (spec book parsing) was not found in results; [U]. Lesson: the triage workflow (group, classify, assign) is what reviewers expect.

**ETAP, EasyPower, SKM [S].** Calculation engines fed by manual model entry. ETAP panel systems: NEC and user-defined load factors, customizable panel schedule reports [8]. EasyPower: spreadsheet panel schedules, NEC equipment sizing, summary of connected/demand/design load [9].

## 2. Electrical CAD / BIM built-ins

**AutoCAD Electrical [S, Autodesk help].** Two tools on the Reports tab. Electrical Audit finds wire ends connected to nothing, missing or duplicate wire numbers, and components with no catalog value; Export Tab / Export All writes a text file, and ignored errors stay in the export marked in a Status column. Drawing Audit (command AEAUDITDWG) finds wire gaps, bogus wire-number pointers and zero-length wires, and shows a report with jump-to-location; export behaviour varies by version [10]. These are drawing-integrity checks, not electrical code checks. Lesson: "ignored" status that persists in the export is a useful audit trail.

**Revit MEP panel schedules [S, Autodesk help and forums].** Workflow: define load classifications and demand factors, assign classifications to family connectors, format panel schedule templates, then generate. Demand can be computed by threshold and percentage; "Spare" is a fixed built-in classification; loads must be on circuits to appear; classifications missing from a template and "Not Computed" cells are common user complaints [11]. I found no built-in code-compliance or breaker-vs-conductor check, and no overload warning in these results ([U]). So Revit panel schedules are the likeliest inputs and also where data gaps will occur.

## 3. AI plan review and permitting

**UpCodes [V].** Copilot FAQ says 93% weighted accuracy across major code families and "more than 2x the accuracy of generic AI", from an "independent study of 43 real-world code questions" graded by subject matter experts; the page also says "57% more accurate" which does not reconcile with 2x, names no competing tools, no method and no date. Also self-run practice-exam scores (88-97%). The PDF study could not be read (binary), so the 93% is confirmed as a claim only [12]. Copilot is in the Professional plan, no dollar amounts. Plan Review is early access; 1,300+ plan sets and 180,000+ flagged issues reported [S][13], no precision figure.

**Archistar / CivCheck (Clariti) [S].** Austin adopted Archistar in October 2024 after a three-month pilot, residential only [14]. Honolulu's CivCheck: city says it does not replace official review or guarantee approval; review time reported 60-90 minutes down to 15-30 minutes; sources conflict on launch date [15][16]. Clariti says staff approve every AI interpretation and the tool shows the "why" [17]. Archistar says people keep final authority [18].

**Blitz AI (blitzpermits.ai) [S].** Government-side: screens applications for completeness and checks plans against IRC/IBC and local amendments, output is a marked-up plan and report, final decision stays with reviewers [19].

**PermitFlow [S].** Contractor-side permit management: code database, AI-assisted application prep, submission and tracking; reported $91M Series B (Dec 2025, secondary source) [20]. **Symbium [S].** Checks permit eligibility against building, zoning and energy codes; residential, participating jurisdictions [20]. **Verifi3D, CodeComply.AI:** nothing found [U].

**Singapore CORENET X [S].** Mandatory BIM submission as IFC+SG from 1 October 2025 for projects 30,000 sqm GFA and above, all new projects from 1 October 2026. The Model Checker runs a schema check, a quality check for missing mandatory properties and a regulatory check on selected rules, intended for self-check before submission [21]. No published accuracy figures. A vendor notes its validator checks parameter existence, not value correctness or design compliance [21]. Lesson: staged self-check, and a published list of which rules are automated.

## 4. Canadian and open-source

**CEC tools [S].** No ESA-published calculator or CEC checker found. Third-party tools exist: loadcalculator.ca, offsetnotes ampacity calculator (temperature and conductor-count derating), buildersontario (explicitly "simplified values, not official tables"), CSA's Mobile Calculator for the 2018 CEC, and App Store apps claiming CEC 2024 [22][23]. The 2024 Ontario Electrical Safety Code is in force from 1 May 2025 [22]. Large conductor ampacity (1/0 and up) refers to Tables D8A-D11B [22]. Lesson: commodity single calculators exist with weak caveats; nobody checks a whole package, and the CEC is a real gap.

**pigtail [V].** Repo: github.com/alexandreamat/pigtail, MIT licence, 2 commits at fetch time (very early project), NEC 2023, YAML input. Warn-only checks each citing an NEC section: ampacity (310.15, 240.4), continuous loads at 125% (210.19(A)), voltage drop over 3%, EGC size (Table 250.122), box fill, conduit fill, AFCI, shared neutrals and more. Items needing unrecorded data are reported as "not checked" rather than guessed; it states it is a modelling aid, not a substitute for a licensed review [24]. This is the closest design model for Redline.

## (a) Comparison table

| Product | Category | Extraction | Accuracy claim | Price | Lesson |
|---|---|---|---|---|---|
| Bluebeam Revu | PDF markup | vector/OCR, manual; CSV export | none; AI review in Max | $260/330/440/590 per user-yr [V] | Reviewers work here; export PDF markup + CSV |
| CountFire | Electrical takeoff | ML symbol match | marketing only | n/f | Revision reuse |
| Togal.AI | AI takeoff | ML on drawings | 98% on floor plans, no method [V] | n/f | Undefined % is noise |
| Kreo | AI takeoff | ML | none on page [V] | $100/$175/$250 per user-mo [V] | Beware blog figures |
| Procore | Doc mgmt | title-block and callout OCR | none | in platform | Vector in, sample test, admit gaps |
| ACC Model Coord | BIM clash | model geometry | n/a | in ACC | Group, classify, assign |
| AutoCAD Electrical | CAD | native objects | n/a | n/f | Audit export with ignored status |
| Revit | BIM | native schedules | n/a | n/f | Messy inputs; no code checks |
| ETAP/EasyPower | Calc | manual model | n/a | n/f | Editable factors |
| UpCodes | Code search/review | LLM + corpus | 93% Q&A, internally inconsistent [V] | Pro, n/f | Cite text; no review precision |
| Archistar/CivCheck/Blitz | Municipal review | ML + human approval | 98%+ vendor | contracts | Human approves each item; show why |
| CORENET X | National BIM check | IFC+SG | none | govt | Self-check first; list automated rules |
| pigtail | OSS NEC | YAML | none | free (MIT) | Warn-only, cited, "not checked" |
| CEC calculators | Calculators | manual | none | free-low | Disclaimers; no package check |

## (b) Lessons for Redline's MVP

1. Take structured input (schedules, circuits, feeders) and skip drawing-AI accuracy claims; the market's numbers are undefined (Togal 98% with no method, UpCodes figures internally inconsistent) [4][12].
2. Every finding cites the rule, CEC edition, inputs and computed values (pigtail model) [24].
3. Add a "not checked" status for rules lacking data. This beats guessing and mirrors pigtail and Procore's "no way to confirm it was processed" gap [6][24].
4. Three severities: violation, needs-review, info. No invented confidence percentages.
5. Link each finding to its source cell, row or page.
6. Reviewer disposition per finding (accept, dismiss, comment) that persists into the export, like Electrical Audit's ignored status and ACC's issue/not-an-issue triage [7][10].
7. Table-stakes checks: ampacity vs breaker, 125% continuous load, feeder and demand sizing, voltage drop (8-102), neutral/ground sizing, panel bus and breaker ratings.
8. Code tables as editable, versioned data files (CEC 2024 / Ontario 2024 edition), with user overrides like ETAP load factors [8][22].
9. Report which rules ran, which were skipped, and what was unparsed; scope narrowly like Austin's residential-first pilot [14][21].
10. Outputs: HTML/PDF plus CSV, since Bluebeam export is limited [1][2]. Accept clean vector PDF or CSV/Excel, and warn on raster input [6].
11. Revision diff between package versions (Bluebeam, CountFire) [1][3].
12. Avoid: calling output "compliant", LLM as rule engine, full power-system studies, and mixing in AHJ-specific amendments before the base CEC works.

## (c) Liability and positioning language

Used in the market: "augment, not replace" [17]; "does not replace official review or guarantee approval" [15]; "people retain final authority" [18]; "final decision stays with your reviewers" [19]; "modelling aid, not a substitute for the Code, local authorities, or a licensed electrician" [24]; calculators: "simplified values, verify against official tables" [22]. Suggested Redline wording: "Pre-review screening that flags potential CEC gaps for a qualified reviewer. Not a design approval, stamp or compliance certificate." Name the edition and rules covered in every report.

## Sources

1. https://www.bluebeam.com/pricing [V, fetched 2026-11-06]
2. https://novedge.com/blogs/design-news/bluebeam-tip-export-revu-markups-list-to-csv-for-excel-and-power-bi (third party)
3. https://www.countfire.com/product/takeoff-software ; https://softwareconnect.com/reviews/countfire/
4. https://www.togal.ai/ [V]
5. https://www.kreo.net/pricing [V]
6. https://support.procore.com/faq/how-can-i-improve-the-accuracy-of-ocr-on-my-drawings ; https://support.procore.com/products/online/user-guide/project-level/drawings/tutorials/automatic-drawing-sheet-linking ; https://support.procore.com/faq/which-fields-can-procore-automatically-populate-when-uploading-drawings
7. https://construction.autodesk.com/tools/clash-detection/ ; https://aps.autodesk.com/en/docs/acc/v1/overview/field-guide/model-coordination/mcfg-clash
8. https://etap.com/product/panel-systems-software
9. https://www.easypower.com/products/features/mcc-and-panel-schedules
10. https://help.autodesk.com/view/ACAD_E/2024/ENU/?guid=GUID-28F7243A-59DB-4A53-BB83-9729E7F590E2 ; https://help.autodesk.com/view/ACAD_E/2023/ENU/?guid=GUID-7CA879C4-035D-4475-9BD9-2299F1A11F98
11. https://help.autodesk.com/cloudhelp/2025/ENU/Revit-MEPEng/files/GUID-9316D4CB-C244-4691-90B2-8D74A502445B.htm ; https://forums.autodesk.com/t5/revit-mep-forum/panel-schedule-load-summary-automatic-and-some-questions-about/td-p/12454405
12. https://cms-v2.up.codes/features/copilot [V] ; study PDF https://marketing.up.codes/hubfs/Whitepapers/UpCodes-Copilot-Accuracy-Study.pdf [U, unreadable]
13. https://runtimewire.com/article/upcodes-ai-plan-review-1300-plan-sets
14. https://www.smartcitiesdive.com/news/ai-building-permits-austin-honolulu-los-angeles/751159/ (2025) ; https://cities-today.com/?p=69557
15. https://spectrumlocalnews.com/us/snplus/news/2025/12/09/new-ai-software-tool--civcheck--comes-to-dpp
16. https://www.route-fifty.com/artificial-intelligence/2025/05/how-tech-sped-honolulus-housing-permits/405065/
17. https://www.claritisoftware.com/products/civcheck-ai-plan-review-software ; https://secure.businesswire.com/news/home/20251008364671/en/Clariti-Acquires-CivCheck-to-Accelerate-Permit-Approvals-with-AI
18. https://www.archistar.ai/aiprecheck/ai-plan-review/
19. https://blitzpermits.ai/product-code-compliance-review
20. https://www.teardown.ai/companies/permitflow ; https://scoutcities.com/blog/ai-tools-simplifying-permitting-processes
21. https://info.corenet.gov.sg/overview/about-corenet-x/overview-of-corenet-x ; https://newhamtech.com/guides/corenet-x-mep-bim-submission ; https://www.bim.com.sg/blog/corenetx-bimeco-validator/
22. https://offsetnotes.com/cec/ampacity-calculator ; https://buildersontario.com/electrical-load-wire-size-calculator/ ; https://loadcalculator.ca/electrical ; https://www.omorealelectric.com/code-lookup
23. https://www.csagroup.org/store/product/2426142 ; https://apps.apple.com/app/id6760935722
24. https://github.com/alexandreamat/pigtail [V] ; https://pypi.org/project/pigtail/
