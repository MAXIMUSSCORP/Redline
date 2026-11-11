# Design philosophy

Taken from Datum (field data capture for upstream oil and gas): its
project rules file, `DATUM.md`, `src/styles.css`, and the M4r UI rework plan
(`docs/ui-rework/DESIGN.md`, 2026-10-11). Written so a new project can adopt
the same way of thinking about design, words and honesty, with Datum's own
choices kept as worked examples.

Last updated 2026-10-26.

---

## 1. The premise comes first

Every product gets one sentence that every change must serve. Datum's:

> **Nothing is typed that can be chosen.**

Every facility, disposition point and well is chosen from the live register
through a picker, never typed. Free text never becomes a key, so one battery
cannot end up as seven strings. Search text only narrows a list; it never
becomes the value.

The premise is not a slogan. It decides real questions: a new kind of record
gets a picker, not a text box; typed text in a picker shows a `REJECTED`
panel; a search with no match says `NO MATCH`. When a design choice is
unclear, ask which option serves the premise.

**For a new project:** write the premise before the first screen. It should
be short enough to quote in a code review and strong enough to say no to a
feature.

---

## 2. Five rules for every screen

From the M4r rework. Every one of 177 audit findings resolved to one of these.

1. **Every screen says what to do next, and the next step is one click away.**
2. **The reason sits beside the thing it is about**, never behind a scroll, a hover or a fold.
3. **One word means one state, everywhere.**
4. **The person's place is the thing they are standing at or fixing**; the screen narrows to it.
5. **Nothing typed is lost** to a tap, a key, a rotation or a dead zone.

---

## 3. Design for the real people, from sources

Datum's rework started by describing its two users from primary sources
(regulator manuals, fee tables, competitor pages), each claim cited: the
production accountant closing a month against a moving deadline, and the
field operator on a route of batteries, offline, possibly in gloves.

What that produced:

- **Use the domain's own words.** Petrinex says balanced, out of balance, missing, pending, amendment. It has no word "held" and no word "closed", so Datum defines its own carefully and never borrows a word that means something else to the user.
- **Never hard-code what the domain leaves variable.** The filing deadline falls between the 18th and 22nd, so the due date is a setting per period, not a constant.
- **Offline is a given, not a feature.** Every incumbent tool syncs on its own with nothing to press.
- **Touch targets come from standards.** 44 px (Apple, WCAG 2.5.5) to 48 px (Material). No glove figure is citable, so the user chose 48 px for comfort density.

**For a new project:** write a short "the people" section with sources before designing screens. Where there is no source, say so and let the user decide.

---

## 4. Visual system: monochrome, quiet, exact

### No hue anywhere

A 12-step gray scale, used only through semantic aliases. Dark mode is the
same scale inverted, under both `prefers-color-scheme` and a `data-theme`
attribute.

| Steps | Role |
|---|---|
| 1 to 2 | ground |
| 3 to 5 | element fills |
| 6 | static border |
| 7 | interactive border |
| 8 | strong border and focus |
| 9 to 10 | solid |
| 11 | low text |
| 12 | high text |

```css
:root{
  --g1:#FCFCFC;--g2:#F8F8F8;--g3:#F1F1F1;--g4:#E9E9E9;--g5:#E1E1E1;--g6:#D8D8D8;
  --g7:#CBCBCB;--g8:#B4B4B4;--g9:#8C8C8C;--g10:#7A7A7A;--g11:#606060;--g12:#1B1B1B;
  --inv-bg:#000;--inv-fg:#FFF;
}
:root{
  --app:var(--g1);--surface:var(--g2);--el:var(--g3);--el-hi:var(--g4);--el-on:var(--g5);
  --line:var(--g6);--line-int:var(--g7);--line-strong:var(--g8);
  --text:var(--g12);--text-low:var(--g11);--text-dim:var(--g9);
}
/* dark: --g1:#0A0A0A ... --g12:#EFEFEF, --inv-bg:#FFF, --inv-fg:#000 */
```

Every inversion (a selected nav item, a flagged figure, an offline badge)
uses `--inv-bg` / `--inv-fg`, pure black and white.

### State without colour

Because there is no red or green, state is carried by shape, weight and
inversion:

- A blocked row gets a **2 px inset edge** (`tr.bad`).
- A hot count or flagged cell **inverts** (`.bcell.flag`, `.nav.on`, `.pcount.hot`).
- Row state is **a dot plus a mono uppercase word** (`.st ok | blk | pos | q`).
- An empty cell is told from a value **by its word** ("required", "choose well", "enter"), not by a fainter gray.
- Every count follows one rule: **inverted means "needs you", dim means "how many"**.

This is also an accessibility win: nothing depends on telling colours apart.

### Type

- **Sans (Inter)** for prose.
- **Mono (JetBrains Mono) for every identifier, number, label and table cell**, with tabular numerals, so columns of figures line up.
- **Labels** (`.lbl`): mono, 10 px, uppercase, letter spacing .14em, `--text-dim`.
- A small fixed type scale: 10, 12, 13.5, 15, 19, 25, 31 px. Radii 3, 5, 8 px.
- Fonts are **bundled files**, not fetched from Google at first paint, so the app opens offline.

### Density

One mechanism, three settings, through tokens rather than per-component sizes:

| Density | Row | Control |
|---|---|---|
| compact | 30 px | 26 px |
| default | 38 px | 30 px |
| comfort | 48 px | 48 px (a gloved thumb) |

A touch device with no stored choice starts in comfort.

### What is never allowed

- No colour.
- No icon fonts. Unicode glyphs are fine (▦ ▼ ■ ◇ △ ◫ %).
- No chart library. The sparkline is about 30 lines of SVG.
- No component library.
- No basemap on the map. It is a projection of the land survey grid, and that is deliberate.

---

## 5. Layout: the same skeleton on every screen

- **The app is three rows:** a 48 px top bar, the body, a 28 px status bar.
- **The body is three columns:** a 218 px rail (navigation), the main column, a 304 px inspector (detail of what is selected).
- **The main column always runs in the same order:** a KPI band of figures, then the view head (title, mono subline, actions), then the scrolling content, then a note.
- **Empty states** are a ring glyph and a sentence. **Popovers** carry their key hints in a footer.
- **The rail is in the order work happens**, grouped (Capture, Month end, Reference, Organisation), not alphabetically or by data type.
- **Tablet (1240 px and below):** the rail becomes a 40 px strip of the same buttons under the top bar, and the inspector becomes a drawer opened from the top bar. The top bar must fit 390 px.
- **One inspector:** with a row selected, the row's state and its errors come first, then its context. Nothing selected says so.

Consistency is the point: once someone has learned one screen, they know where
everything is on the others.

---

## 6. Voice: the words are part of the design

### Every view ends in a note that makes the product's argument

Not a caption. The map's note says "No basemap, and that is deliberate", then
why. A note argues for the design and says what to do next.

### Toasts carry the argument too

One reason, then the argument after a middle dot:

> Posted 9 rows · keys match Petrinex, no mapping required

A toast carrying a refusal stays until dismissed and names the row.

### Errors name the bad value and the valid range

> LSD must be 1 to 16. A section holds sixteen legal subdivisions. Got 18.

Never "invalid input". Plain sentences. No exclamation marks.

### Punctuation rules

- `—` appears only as the **empty value placeholder**, never in prose.
- No exclamation marks.
- No developer words on user screens (no file paths, no shell commands).

### One word, one meaning (the glossary)

Datum keeps a table of state words and tests the screen against it
(`test/words.test.js` refuses retired words). A sample:

| Word | Means, and only means |
|---|---|
| blocked | an entry with at least one field error |
| held | the file cannot go until something is fixed; always with its cause after a middle dot |
| queued | on this device, will sync on its own |
| not saved | a change on screen only |
| draft | a new row that has not passed its checks |
| warning | shown, holds nothing |
| filed | closed, stored and locked |

Hold sentences name the thing, the missing input, and where to fix it, using
the rail's own label: "Enter it on {rail label}".

**For a new project:** start the glossary on day one. Every new state gets
one word, written down before it reaches the screen.

---

## 7. Honesty: never show an invented number

Where a number is not real, the screen says so, and nothing invented sits
beside it:

- The sparkline reads **"Illustrative until volumetric history is ingested"**.
- The SCADA panel says **"not configured"**.
- An estimated figure is italic with a title (`.est`).
- A choice the product made on the user's behalf is labelled **"Datum's choice"**.

These labels are never removed. Honesty includes the wording: the offline
label was changed from "capture continues" to "tickets and tests are queued on
this device" because the first was not true for every kind of entry.

**The arithmetic is done once.** All calculations live server side; the
browser only renders them. A number on screen and the same number in the
filing were computed once, in one place.

---

## 8. Nothing is lost

- Editors **save on Enter, Tab or a tap away**; **Escape is the only discard**.
- Enter saves and opens the same field on the next row; Tab saves and opens the next field.
- A new row is a **draft** until it passes its checks, so a half-finished row never counts.
- Delete **asks once**, by turning the ✕ into "delete?".
- Leaving a month with unsaved work **asks first**.
- **The offline queue is real.** Work done without coverage is held on the device and syncs on its own; the server re-validates every item. A refused item stays on the device with its sentence until it is fixed or discarded.
- A **service worker** of about thirty lines caches the app (never the API), so it opens in a dead zone. When a new build is cached, the status bar offers "A new version is ready · reload".

---

## 9. Accessibility, built into the system

- Focus ring uses `--text` (full contrast), 2 px.
- Placeholders and empty-cell words use `--text-low` (6.1 to 1), since `--text-dim` fails WCAG 1.4.3's 4.5 to 1.
- `prefers-reduced-motion` turns off all transitions and animation.
- Touch targets reach 48 px in comfort density.
- State never depends on colour (section 4).
- Every command reachable from the keyboard: a command palette (`⌘K` / `Ctrl K`), arrow keys between cells, a digit opens the editor.
- A **Focus mode**: one item at a time, with targets you can hit wearing gloves.

---

## 10. Dependencies are a design decision

Datum's runtime dependencies are three: react, react-dom, pg. A fourth is a
decision to argue, and the argument must show that the thirty-line local
version is worse. The fonts are files, the service worker is thirty lines,
the sparkline is thirty lines of SVG, the map is a projection.

Small surface means the whole product stays readable: all state in one file,
every route a key in one object, every rule in one spec file shared by
browser and server so they cannot drift.

---

## 11. How the philosophy is kept, not just written

- **A reference prototype.** Datum kept its original prototype read only as the reference for design, voice and code style. "When in doubt, open the matching file there and follow it."
- **Decisions that look like bugs are written down.** Deliberate behaviours are listed in the project rules, dated, with who chose them, and "do not fix without asking".
- **Original copy is pinned.** A check script (`pinned-check.mjs`) compares the original texts, and each approved rewording is recorded by name.
- **Voice is checked by code.** `voice-check.mjs` reads string literals and refuses em dashes and exclamation marks in prose.
- **Words are tested.** `words.test.js` reads every text the screen can show and refuses retired words.
- **Redesigns are audits first.** The M4r rework ran eight audit lanes (shell, capture, records, month end, reference, copy, system and tablet, research), cited every finding to a file and line, then put thirteen decisions to the user before any code. "Keep the design the same, just make it intuitive": the palette, type and layout were fixed; placement, order, next steps and words changed.
- **A hallway test** with a real person closes a UI milestone.

---

## 12. Starting a new project with this

1. Write the **premise** (section 1).
2. Describe **the people** from sources (section 3).
3. Copy the **gray scale, aliases, type and density tokens** (section 4) into one stylesheet; adjust the steps only if the product needs it, keep "no hue" unless there is an argument.
4. Fix the **skeleton**: top bar, rail, main, inspector, status bar; band, head, scroll, note (section 5).
5. Start the **glossary** and the **voice rules** (section 6), and a check script for them.
6. List what is **not real yet** and label it on screen (section 7).
7. Write the **five rules** (section 2) into the project's rules, under its Design system and Voice headings.
