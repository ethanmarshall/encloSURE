---
name: enclosure-fit
description: Fit a KiCad board to its enclosure with EncloSURE. Use when the user gives an enclosure STEP and wants a board outline to design in, or wants to know whether a board fits its enclosure (standoffs, openings, headroom, collisions), and to fix what does not.
---

# Fitting a board to its enclosure

EncloSURE (`enclosure` on the command line) reads an enclosure STEP (an open-topped base, and
optionally its lid, in one frame with Z up), and works in millimetres.

Use the KiCad that Backplane has selected: call plain `kicad-cli` (or `$BACKPLANE_KICAD_CLI`),
never another install's path. EncloSURE writes and reads `.kicad_pcb` files itself, so it does not
need KiCad's Python; only exporting the board to STEP needs `kicad-cli`.

## Start a board from the enclosure

```
enclosure read base.step --lid lid.step            # cavity, standoffs, openings, ceiling
enclosure limits base.step --lid lid.step -o board.kicad_pcb
```

`limits` writes the board outline (the cavity inset by 0.5 mm), a mounting hole on each standoff
sized for its screw with a copper keepout for the head, the tallest part allowed on top and
underneath (User.1), and a marker at the board edge for each wall opening and over the board for
each lid opening (User.2), with the opening's height above the board top. Place connectors on
those markers and keep parts under the heights. Do not move the outline or the holes: they are
the enclosure's.

## Real parts

Before checking, build `parts.json` (next to the board):

1. `enclosure parts --pcb board.kicad_pcb` (MPNs from footprint fields) or `--set REF=MPN`.
   With DigiKey or Mouser keys in the environment it fills manufacturer, datasheet (saved to
   `datasheets/`), height and size, and lists what is still missing.
2. For each part in `need_body_from_datasheet` that has no 3D model, and each connector in
   `connectors_without_cutout`, open its datasheet PDF and read the mechanical drawing: write
   `body` [length, width, height above board] and, for a connector, `cutout` {width, height,
   max_setback} (the recommended panel opening). Put the page in `source`, e.g.
   `"cutout": "datasheet p.2, recommended panel cutout"`. If the drawing does not give a value,
   leave it out; never estimate one.
3. Pass `--parts parts.json --pcb board.kicad_pcb` to `fit`.

## Check the finished board

1. Export the board with its 3D models: `kicad-cli pcb export step -o board.step board.kicad_pcb`.
   Parts without a 3D model are not in the STEP and cannot be checked; say which.
2. `enclosure fit base.step board.step --lid lid.step --pcb board.kicad_pcb --parts parts.json -o fit/`
   (exit 0 fits, 1 does not).
3. Read `fit/report.json`. Each finding has `severity`, `code`, `subject` (a reference, J1), a
   `message`, a `fix`, and where a move fixes it, `kicad_move` [dx, dy] in mm on the KiCad board.

## Fixing it for you

`enclosure autofit base.step board.kicad_pcb --lid lid.step --parts parts.json -o autofit` does the
loop below on its own: export the STEP with `kicad-cli`, check, move what the check asks to move,
and repeat until the board fits or a round asks for no moves. The user's board is never changed: the
result is `autofit/board_fixed.kicad_pcb`. Tell the user what moved (autofit.json lists each round)
and what is left, then, if they agree, open the fixed board in KiCad in place of the original.

To start a box from a finished board instead: `enclosure frompcb board.step -o box` (the board's STEP
export); it designs the box, checks the board in it, and writes `box/box.json` to adjust.

## Fixing by hand

- `opening_misaligned`, `hole_off_standoff`, `board_edge_clearance`: apply `kicad_move` to the
  footprint (or the hole), then check again.
- `collision` with the lid, `too_tall`: the part is too tall; the fix names the height allowed.
  Find a lower part or ask the user; do not change the enclosure without asking.
- `collision` with the base, `tight`: move the part clear of the wall or standoff.
- `unchecked_part`: add its 3D model in KiCad, or its `body` from the datasheet.
- `model_height_differs`: the 3D model may be the wrong variant; tell the user.
- `opening_too_small`, `opening_below_datasheet`, `connector_setback`, `connector_no_opening`: the enclosure needs a change;
  report the numbers to the user (they edit the enclosure in their CAD).
- Re-export and re-run `fit` after each round until `fits` is true or only enclosure changes
  are left. Show the user `fit/view.html` and `fit/punch_list.md`.
