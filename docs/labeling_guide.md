# Labeling guide

This guide says what counts as a device on a plan sheet and how a block name becomes a device class. The detector that finds symbols in a picture (L5.3) waits for M4 and is not built. There is no hosted labeling service. Everything here is a local file you edit.

## The six classes

| Class key | What it is |
|---|---|
| `exit_sign` | exit sign |
| `pull_station` | manual pull station |
| `emergency_light` | emergency light |
| `horn_strobe` | horn or strobe |
| `smoke_detector` | smoke detector |
| `exit_door` | exit door |

The owner may add further classes in `fire_alarm.yaml`. A class that no rule uses is counted and shown in the report, and nothing is checked on it.

## Where the names go

Under `device_blocks` in `config/fire_alarm.yaml`, each class key holds a list of block names:

    device_blocks:
      exit_sign: ["EXIT-SIGN-A"]
      pull_station: []

- A name matches a block exactly, ignoring case and spaces at either end. There is no prefix match and no wildcard.
- One name under two classes is a config error, and the run exits 2.
- An empty list means that class is never found from blocks. The report shows a count of 0 for it. That is not a statement that the sheet has none.
- Every block name that matches no class is listed in the report under "Devices and exits", with the number of times it is placed. Fill `device_blocks` from that list, then run again.

## Where a block is counted

- Model space: counted as `block`, with HIGH confidence.
- A paper space layout: counted as `paper`, and not used in any distance. A paper layout often holds a legend instance, and a legend is not a device on the plan.
- Inside another block definition or an xref: counted as `nested`, LOW confidence, with no position. It is shown and never measured.
- A dynamic block whose placed name is anonymous is resolved to its base name when the drawing says which one it is. An anonymous block with no base name stays unmatched.
- An exit door block is `unused` for a sheet whose exits are listed in `exits.csv`. The list wins for that sheet.

## Revit exports

A Revit export puts an element id at the end of each block name, so each placement has its own name and an exact match finds nothing. The report lists every such name. Until a prefix rule is chosen, add each name you want read, or list the exits by hand in `exits.csv`. Do not guess a name.

## The legend

A legend sheet names each symbol and its class. It is the input for the symbol detector, which is deferred with M4 as leaf L5.3. Until then a legend sheet is read like any other sheet: its blocks are counted if they match `device_blocks`, and a legend that sits in a paper layout is not used in distances. PDF sheets give no devices until L5.3.
