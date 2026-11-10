# PDF reading verification on the dev PC

Leaf L3.0, written 2026-11-10 on the Windows 11 dev PC, from a Python subprocess outside the AutoCAD GUI. Every figure below was measured here. Anything not measured is marked UNVERIFIED or BLOCKED with its reason.

Headline: the AutoCAD 2027 core console plots `samples/dwg/panel_sheet.dwg` to PDF with `-PLOT` and `DWG To PDF.pc3`. Three plots are committed under `samples/pdf/acad/`. With a TrueType font the page has a real text layer. With an SHX font and `PDFSHX 0` the page has no text layer at all: every glyph is a stroke. With an SHX font and `PDFSHX 1` the strokes are the same and each text string also sits in a `/Square` annotation named `AutoCAD SHX Text`. The three plots hold no user name and no path.

## 1. pdfplumber

Installed in the shared venv, read from package metadata on 2026-11-10.

| Package | Version | Licence stated by its metadata | Why it is here |
|---|---|---|---|
| pdfplumber | 0.11.10 | MIT (classifier `License :: OSI Approved :: MIT License`) | the reader |
| pdfminer.six | 20260107 | MIT (`License-Expression`) | required by pdfplumber (`pdfminer.six==20260107`) |
| Pillow | 13.0.0 | MIT-CMU (`License-Expression`) | required by pdfplumber (`Pillow>=12.2.0`) |
| pypdfium2 | 5.15.2 | BSD-3-Clause, Apache-2.0, dependency licenses (`License` field) | required by pdfplumber (`pypdfium2>=5.9.0`) |

`importlib.metadata.requires('pdfplumber')` returns exactly three lines: `pdfminer.six==20260107`, `Pillow>=12.2.0`, `pypdfium2>=5.9.0`. pdfplumber 0.11.10 asks for Python 3.8 or later.

Second level, from `requires('pdfminer.six')` (extras left out):

| Package | Version | Licence stated by its metadata |
|---|---|---|
| charset-normalizer | 3.5.2 | MIT |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| cffi (required by cryptography) | 2.1.1 | MIT-0 |
| pycparser (required by cffi) | 3.12 | BSD-3-Clause |

Every licence above is permissive. pypdfium2 ships a PDFium binary that M3 never calls. Not checked here: pdfminer.six security advisories (stage 5 owns that).

## 2. Plot path

Result: the 2027 core console plots to PDF. D6's GUI fallback was not needed.

- Exe: `C:\Program Files\Autodesk\AutoCAD 2027\accoreconsole.exe` (the 2026 one crashes on this PC, PLAN row 41). Core console banner version X.60.0.0.
- Profile: `<<Unnamed Profile>>`. The console opens the drawing from `acadiso.dwt` settings.
- Launch: a small Python script starts the exe with `subprocess.Popen`, `stdin=DEVNULL`, stdout and stderr captured, a timeout of 120 s, and on timeout `taskkill /F /T /PID <that child>`. Command line: `accoreconsole.exe /i "<copy>.dwg" /s "<script>.scr" /l en-US`.
- Launch problem: started from Git Bash with `</dev/null`, the exe did not exit in 60 s even with a one-line `_QUIT` script, and a LISP script hung the same way. Cause not found, UNVERIFIED. From the Python subprocess the same script exits in about 3 s. One hung process was stopped by its own PID. No other `accoreconsole.exe` was left.
- Console output cannot be read for sysvar prompts, because it echoes only the `Command:` prompt. Values were therefore written to a text file with LISP (`open`, `write-line`, `getvar`), which works in the core console.
- Working copies: each plot ran from a fresh copy of the sample in its own folder under `%TEMP%\redline-m3\L3.0\`. The original `samples/dwg/panel_sheet.dwg` was only read.
- Layout plotted: `E-101`, which holds the panel schedules. The `Model` space is not the sheet. A first try on `Model` made a 1372 byte PDF with nothing useful.

Plot command (the line after the prompt is the answer given, in order):

```
-PLOT  Y  E-101  "DWG To PDF.pc3"  "ANSI B (17.00 x 11.00 Inches)"  Inches  Landscape  N
       Extents  Fit  Center  Y  .  Y  N  N  N  <output .pdf>  N  Y
```

The answers mean: detailed configuration yes, layout, device, paper, units, orientation, not upside down, plot area Extents, scale Fit, offset Center, plot styles yes with none, lineweights yes, scale lineweights no, paper space first no, hide paperspace no, file name, save page setup no, proceed yes. With plot area `Layout` the offset prompt takes no `Center` and the script derailed, so `Extents` is used.

Times from the Python wrapper: 3.5 s (TrueType), 2.9 s (PDFSHX 0), 3.1 s (PDFSHX 1). All exit code 0. A `plot.log` is written beside each working copy. It holds a user name, so it stays under `%TEMP%` and is not committed.

## 3. Three plots, each from its own copy

### Text style fonts, as drawn

Read from the drawing with `tblnext "STYLE"` before any change:

| Style | Font file | Big font |
|---|---|---|
| Standard | arial.ttf | none |
| Annotative | arial.ttf | none |

Only these two styles exist. Text inline overrides were not inspected. Both styles are TrueType, so the as-drawn plot has a text layer (section 4).

### Settings that were read, set and restored

| Setting | Before | Action | After |
|---|---|---|---|
| PDFSHX | 1 (read `getvar "PDFSHX"`, 2026-11-10) | the TrueType plot left it alone; the SHX plot set it to 0 and then to 1; the PDFSHX plot set it to 1 and then to 1 | 1 (read again in each run, and in a fresh console process after the last plot, 2026-11-10) |
| SECURELOAD | 1 | not touched, only read | 1 |
| TRUSTEDPATHS | not touched, only read | not touched | unchanged |

Commands, all in the console script:

- Read: `(getvar "PDFSHX")` written to `pre.txt` at the start and `post.txt` at the end of each run.
- Set: the command `PDFSHX` followed by the value on the next script line (`0`, then `1`).
- Restore: `PDFSHX` then `1`, the value read before, after the `-PLOT` finished.
- After the last plot a new console process on a fresh copy read PDFSHX again. It returned 1, the same as before the first plot.
- The registry key `HKCU\Software\Autodesk\AutoCAD\R26.0` holds no `PDFSHX` value before or after (searched with `reg query /s /v PDFSHX`). The core console profile is unnamed, so a value set in one process did not carry to the next. Whether a named profile or the GUI would persist it is UNVERIFIED and was not tried.

### The three plots

| File | Made from | Style fonts at plot time | PDFSHX at plot time | Bytes |
|---|---|---|---|---|
| `samples/pdf/acad/acad_truetype.pdf` | copy of the sample, as drawn | arial.ttf, arial.ttf | 1 (unchanged) | 105804 |
| `samples/pdf/acad/acad_shx.pdf` | copy, `-STYLE` Standard and Annotative set to `txt.shx` | txt.shx, txt.shx | 0 | 43389 |
| `samples/pdf/acad/acad_pdfshx.pdf` | copy, the same style change | txt.shx, txt.shx | 1 | 107370 |

`-STYLE <name> txt.shx` was followed by six empty lines, one for each remaining prompt (height, width factor, oblique angle, backwards, upside down, vertical), so each other style value stayed as it was. The style read-back after the change shows `txt.shx` for both styles.

SHA-256:

- `acad_truetype.pdf` `ba4975bfb7bc052cf6b3aec1ac1032edfef5976419814d8a2ba48b5630ef94af`
- `acad_shx.pdf` `b18effb543a666fa5c842b2e33f5d396046931546006bd00bdcf565c5b961d90`
- `acad_pdfshx.pdf` `8da57fd5910b0660b0193591665b78fc47ef8175715eb9d8afc4f0d53361caad`

## 4. What pdfplumber sees

pdfplumber 0.11.10, page 1 of each plot, read on 2026-11-10. Page size is 1224 by 792 points (ANSI B landscape) in all three.

| Measure | acad_truetype | acad_shx (PDFSHX 0) | acad_pdfshx (PDFSHX 1) |
|---|---|---|---|
| Pages | 1 | 1 | 1 |
| /Rotate | 0 | 0 | 0 |
| Media box | 0, 0, 1224, 792 | 0, 0, 1224, 792 | 0, 0, 1224, 792 |
| Chars | 1808 | 0 | 0 |
| Words (`extract_words`) | 1062 | 0 | 0 |
| Lines | 50 | 980 | 980 |
| Rects | 1 | 8 | 8 |
| Curves | 3 | 1679 | 1679 |
| Images | 0 | 0 | 0 |
| Image area fraction of the page | 0.0 | 0.0 | 0.0 |
| Annotations | 0 | 0 | 366 |
| Annotation subtypes | none | none | `/Square` only (366) |
| Font names on chars | ArialMT | none | none |
| `extract_text()` | text | empty string | empty string |

### What PDFSHX 0 and 1 wrote

- PDFSHX 0: every glyph of the SHX text is a stroked path. The page has no chars, no words and no annotations. The text exists only as the shapes of lines and curves (980 lines, 1679 curves, against 50 and 3 in the TrueType plot). A parser sees no text.
- PDFSHX 1: the strokes are the same as with PDFSHX 0 (same line, rect and curve counts). In addition there are 366 annotations. All are `/Subtype /Square`, title `/T (AutoCAD SHX Text)`, flags `/F 64` (read only), border width 0, and `/Contents` holds the string as UTF-16BE with a byte order mark. Every one of the 366 has a non-empty contents. The first ones read `Panel`, `LP-11`, `Ckt`, `Description`, `Load (VA)`, `Load Type`, `Poles`, `Phase`. Each rect is 6 to 32 points wide and 7 to 38 points high.
- The annotation count is a count of strings. It is not a count of words or cells.

### Hidden text under SHX strokes

No, on both SHX plots. There are no chars, so no text layer sits under the strokes. With PDFSHX 1 the text is in annotation contents, not in the page content stream. The annotation text is not hidden under the strokes in the sense of a character layer. Whether each rect lies over its own strokes was not checked.

### find_tables() on the TrueType plot

`page.find_tables()` with default settings found 2 tables.

| Table | Bbox (x0, top, x1, bottom) | Rows |
|---|---|---|
| 1 | 305.7, 48.6, 967.2, 744.0 | 23 |
| 2 | 503.1, 523.3, 601.9, 592.6 | 8 |

Table 1 spans several panel blocks. Its first row holds one cell with the text of several columns run together, so it is a merge of more than one schedule. Its next rows read as `Panel, LP-11` and a header row (`Ckt, Descri ption, Load (VA), Load Type, Poles, Phase, Breaker, Wire Sz., Material, Insulation, Conductors in Raceway, Length, Voltage, Notes`) with cells wrapped at the cell edge. Table 2 reads as the panel LP-12 block: `Panel, LP-12`, then `Ckt, Description, Load (VA), Breaker, Poles, Wire Sz.`. The drawn grid is real, but the default settings do not give one table per panel. The words inside narrow cells wrap, so `extract_text()` of the whole page also breaks long words (for example `Corrid or lightin g`). Tuning is L3.2 and L3.5 work.

## 5. Metadata

Info dictionary of each plot (pdfplumber `metadata`, and the raw `/Info` strings in the file):

| Key | acad_truetype | acad_shx | acad_pdfshx |
|---|---|---|---|
| Creator | `AutoCAD 2027 - English 2027 (26.0)` | same | same |
| Title | `E-101` | `E-101` | `E-101` |
| Producer | `pdfplot18.hdi 18.00.060.00000` | same | same |
| CreationDate, ModDate | `D:20261110141344` (both) | `D:20261110141353` (both) | `D:20261110141357` (both) |
| Author, Subject, Keywords | not present | not present | not present |

- XMP: none in any of the three. There is no `/Metadata` entry and no `<x:xmpmeta` in the bytes.
- Gate G0.4 pattern, run on the raw bytes of each plot, ignoring case: the user name, `onedrive` and the backslash `users` backslash path fragment. All three plots hold none of these. The bare word `users` is also absent.
- The title is the layout name. The file name given at plot time is not stored in the PDF. The working copy was named `panel_sheet.dwg` and sat under `%TEMP%`; no path reached the PDF. The only place the user name was written is the `plot.log` beside the working copy, which is not committed.
- The creation dates move on every plot, so re-plotting changes the bytes. The committed hashes in section 3 belong to these three files only.

## 6. Owner sheets

Left empty for L3.5. Real owner PDFs are owed (owner decision D7).
