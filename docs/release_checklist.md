# Release checklist

The evidence on this page comes from commands and scripts. The owner reads it and signs. Unsigned means not released.
Nothing here states a licence for Redline. Nothing here is a CEC value.

## Licence audit

Source of the table:

- `redline doctor --licences` prints one CSV row per installed requirement of `redline` and its extras. It reads `License-Expression`, then `License`, then the licence classifiers, with `importlib.metadata`.
- `docs/licences.csv` is that output, committed. It was written on 2026-11-11 in the shared dev venv with `--config tests/test_config/`. It holds 25 packages. Run the command again at every release, with whatever is installed then.
- `constraints.txt` lists the tested versions. Check that the versions in `docs/licences.csv` equal it.
- Status `listed` means the licence text is on the short list of permissive licences found in the table. Status `REVIEW` means it is anything else or empty. The owner reads the licence file of every REVIEW row.

REVIEW rows in `docs/licences.csv` on 2026-11-11:

| Package | Declared licence | Licence files | Read by owner |
|---|---|---|---|
| pypdfium2 5.15.2 | free text naming BSD-3-Clause, Apache-2.0 and dependency licenses | 37 | not yet |

Four packages declare a licence only by classifier (Jinja2, ezdxf, pdfplumber and colorama). A tool that read one field would miss them.

Rows the tool cannot produce, kept by hand. State each as found; a licence not confirmed stays "not confirmed".

| Item | Where it comes from | Shipped in a release | Licence |
|---|---|---|---|
| PDFium binary inside pypdfium2, and its `BUILD_LICENSES` folder | the pypdfium2 wheel, installed by the `[pdf]` extra | yes, as part of the wheel the user installs | not confirmed; owner reads the 37 licence files |
| .NET 10 SDK | Microsoft, installed by the owner, builds `extractors/acad_plugin/` | no, build only | not confirmed |
| setuptools | fetched by pip at build time (`setuptools>=64`) | no, build only; `constraints.txt` does not pin it | not confirmed |
| pip | the Python install | no | not confirmed |
| Python 3.12 | the owner's install | no | not confirmed |
| ODA File Converter 27.10.0 | installed by the owner, never bundled | no | owner reads the current terms; see Owner-blocked items |
| accoreconsole | AutoCAD 2027 core console, owner's seat | no | Autodesk terms; reseller answer open (row 38) |
| Autodesk assemblies the plugin references | AutoCAD install, referenced and not copied | no | Autodesk terms, as above |
| Fonts | none ship; the report uses system font stacks | none | not applicable |
| Weight files (model weight files) | none ship; `config/ai.yaml` lists models with empty hashes and `verified: false` | none | not applicable until M4; this line stays so the M4 release cannot miss it |
| Sample data origins | `samples/` | yes, in the repo | see the client-data audit |

The plugin DLL SHA-256 is recorded here at release. `redline doctor` printed `0877c3b3a5a9c668c86508be15f4b58add55136f2ec9e0e97e5945b8f0d021d8` on the dev PC on 2026-11-11 for the deployed DLL. That is an observation, not the hash of a release build. Rewrite it at release.

## Sample client-data audit

Scope: every tracked file under `samples/`, `tests/`, `config/`, `docs/` and `extractors/`, and the contents of the built wheel.

Checks and what the scan found on 2026-11-11 (checks 3 and 5 only; checks 1, 2 and 4 are not run):

| Check | Result |
|---|---|
| 1. Each sample has a recorded origin | not run |
| 2. Embedded metadata holds no person, firm or path (PDF info, DWG and DXF header, XLSX properties, RawDrawing path fields) | not run |
| 3. Search of tracked files for the Windows user name | 3 tracked files hold it (`git grep -l -i` on the user name). None is under `samples/`. They are listed below. The user name in the two documentation files is generalised to `<user>`. |
| 4. No file name or title block text from `gold/` appears in a tracked file | not run |
| 5. `git ls-files` and `git log --all` show nothing under `gold/`, `.playwright-mcp/` or `ErrorReports/` | nothing found in either |

Tracked files that hold the Windows user name, by path or folder:

- `config/column_maps.yaml`: the three machine paths under `parsing:` (`accoreconsole_path`, `acad_plugin_dll`, `odafc_path`) as found; the user name sits in `acad_plugin_dll`. Found, left as is on purpose: `acad_plugin_dll` is a working machine path. Set the three paths to `null` in any copy that leaves this PC.
- `extractors/acad_plugin/README.md`: the load test path, now `C:/Users/<user>/...` (documentation only).
- `docs/research/dwg_verification.md`: the temp, probe and trusted-folder paths, now `C:/Users/<user>/...` (documentation only).

A scan finds strings. It cannot know a client's project name. The owner opens each sample before signing.

## Owner-blocked items

Not done, not worked around. Each stays open until the owner acts.

1. Redline's own licence. There is no licence file and no licence field. The owner states the terms. Redline's own licence is not stated here.
2. The reseller's answer on Core Console licensing (PLAN row 38) is open. Until it is recorded, the prebuilt plugin DLL does not leave the owner's workstation.
3. ODA File Converter terms. ODA's site says the free converter is for non-commercial use by non-members and that ODA does not grant redistribution. The owner reads the current terms and decides whether the fallback path may be used on paid work [VERIFY]. This agent did not read the agreement in full.
4. Clean machine tier B (`docs/operator_guide.md`): the owner's run of `redline doctor --drawing samples/dwg/panel_sheet.dwg` on a second PC or a new Windows account.
5. The 20 to 30 transcribed schedules for the real `gold eval` run.
6. The plugin DLL redeploy.
7. The release version number.

## Sign-off

Unsigned lines mean not released.

- Licence audit read, with the licence file of every REVIEW row. Signed: ______________________ Date: ____________
- Sample client-data audit read, after opening each sample. Signed: ______________________ Date: ____________
- Owner items 1 to 3 above settled. Signed: ______________________ Date: ____________
