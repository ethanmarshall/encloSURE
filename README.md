# encloSURE

Make a PCB and its enclosure fit each other.

Give EncloSURE the enclosure you modelled (a STEP from Onshape, SolidWorks or any CAD) and it:

1. **Reads the enclosure**: the inside cavity, the floor, the lid's underside, each standoff (and
   the screw its hole takes), and every opening in the walls, floor and lid.
2. **Starts the board for you in KiCad**: the board outline that fits the cavity, a mounting hole
   on every standoff sized for its screw with a keepout for the screw head, the tallest part
   allowed on top and underneath, and a marker where each wall or lid opening lands on the board.
3. **Checks the finished board**: drop in KiCad's 3D STEP export and it seats the board on its
   standoffs (by matching mounting holes), then reports every collision, part too tall for the
   lid, connector off its opening (or an opening too small for it), mounting hole off its
   standoff, and edge too close to a wall. Each problem comes with the fix, and a move in KiCad
   coordinates where a move fixes it. You get a punch list and a 3D view with the problem parts
   in red.

It is built to sit beside [Backplane](https://github.com/i2cjak/Backplane): `skills/enclosure-fit`
is a skill an agent there can follow to run the check, apply the KiCad moves, and re-check.

![3D view of the sample](docs/sample_view.png)

## Just a box

Not every project needs the board side. `enclosure box` makes an enclosure from a size and a
few choices, as STEP files you open and keep editing in Onshape or SolidWorks (they import as
solid bodies, ready for direct edits or new features), plus STL files to print:

```
enclosure box --size 120x80x45 --lid screw --standoffs rect:100x60 --standoff-screw M2.5 \
    --cutout left:rect:9.5x3.8r1@0,9 --cutout lid:round:12@30,0 --flange 10 -o my_box
```

![A screw-lid box with standoffs, a USB-C cutout and mounting ears](docs/box_screw_lid.png)

This writes `base.step`, `lid.step`, `assembly.step` (the lid in place), `base.stl`, `lid.stl` (lid
flipped for printing) and `box.json`, the settings. `enclosure box --from my_box/box.json --lid
snap -o my_box_v2` rebuilds it with one thing changed.

| Choice | Flags | Default |
|---|---|---|
| Size | `--size LxWxH` (the space inside), `--outer` to give the outside instead | 100x60x40 |
| Walls | `--wall`, `--floor`, `--radius` (outside corners, 0 for square) | 2, 2, 3 mm |
| Lid | `--lid screw` (corner posts), `friction` (press-in lip), `snap` (lip with a rib that clicks into a groove), `slide` (panel in grooves, open end), `none` | screw |
| Lid details | `--lid-thickness`, `--lip` (0 for none), `--clearance` (gap between mating parts per side) | 2, 3, 0.2 mm |
| Lid screws | `--lid-screw M2..M4`, `--lid-screw-hole tap` (thread-forming pilot), `insert` (heat-set), `clearance` (through, for a nut) | M3 insert |
| Board standoffs | `--standoffs rect:AxB` or `x,y;x,y`, `--standoff-height`, `--standoff-screw`, `--standoff-hole` | none |
| Inserts | `--insert-hole`, `--insert-depth`: check your insert's datasheet, brands differ | per screw |
| Cutouts | `--cutout FACE:rect:WxH[rR]@a,b` or `FACE:round:D@a,b`; FACE is `left right front back lid floor` (or -X +X -Y +Y); on a wall, a is along the wall from its centre and b the height above the inside floor | none |
| Mounting ears | `--flange` (how far out), `--flange-screw` | none |

Positions are from the centre of the inside, Z up. A box made this way reads straight back into
`enclosure read`, `limits` and `fit`, so a board can be designed into it later.

## Install

Python 3.10 or later, and KiCad 7 or later for writing boards (it uses KiCad's own `pcbnew`
module) and exporting them to STEP.

```
pip install -e .            # installs build123d (OpenCascade) and the `enclosure` command
```

## Use

```
enclosure sample -o sample                         # a sample enclosure, lid and board
enclosure read   sample/sample_base.step --lid sample/sample_lid.step
enclosure limits sample/sample_base.step --lid sample/sample_lid.step -o board/board.kicad_pcb
kicad-cli pcb export step -o board.step board/board.kicad_pcb     # once you have designed it
enclosure fit    sample/sample_base.step board.step --lid sample/sample_lid.step -o fit
```

`fit` writes `fit/report.json`, `fit/punch_list.md` and `fit/view.html` (open it in any browser;
it loads three.js from a CDN). It exits 0 when the board fits and 1 when it does not.

The sample board has four planted problems, and `fit` finds them all:

| Problem | What EncloSURE says |
|---|---|
| A mounting hole 0.8 mm off its standoff | move it X -0.80 mm |
| The USB-C receptacle 1.5 mm off its opening | move J1 Y +1.50 mm in KiCad |
| A capacitor 2.6 mm too tall for the lid | a part at most 21.40 mm tall |
| A connector pushed into the +Y wall | collision, and no opening in front of it |

### Conventions

- Z is up: the direction the lid comes off. Millimetres. The base and lid are in one frame.
- The base is an open-topped shell; standoffs are round, rising from the floor.
- The board STEP is KiCad's export: KiCad names each part's instance by its reference (J1), which
  EncloSURE reads. A part without a 3D model is not in the export, so it cannot be checked.
- KiCad's Y axis points down the page, so KiCad moves have Y flipped from the enclosure's.

### Settings

`fit --clearance 0.5` (part and board edge to the enclosure), `--opening-margin 0.25` (an
opening clear of a connector's face on each side), `--max-setback 2.0` (a connector's face back
from the outside of the wall before the plug may not reach; check your plug's datasheet),
`--place x,y,z,rotation` (put the board somewhere other than on its standoffs).

## Real parts: datasheets, DigiKey and Mouser

A project's `parts.json` holds what the fit check should know about each part, by reference:

```json
{"parts": {
  "J1": {"mpn": "USB4105-GF-A", "manufacturer": "GCT", "datasheet": "https://...",
         "body": [8.94, 7.35, 3.31], "height": 3.31,
         "cutout": {"width": 9.8, "height": 4.0, "max_setback": 1.0},
         "source": {"height": "DigiKey: Height - Seated (Max)", "cutout": "datasheet p.2"}}}}
```

- `body` (length × width × height above the board, mm) lets `fit` check a part **with no 3D model**:
  it stands in a block of that size where the footprint sits on the board (`fit --pcb`).
  Without it, such a part is reported as not checked.
- `height` is checked against the part's 3D model, which is sometimes the wrong variant.
- `cutout` is the connector datasheet's recommended panel opening and how far back the
  receptacle may sit: `fit` holds the enclosure's opening to it instead of a generic margin.

`enclosure parts` builds the file and fills it from the distributors:

```
export DIGIKEY_CLIENT_ID=... DIGIKEY_CLIENT_SECRET=...   # developer.digikey.com, Product Information v4
export MOUSER_API_KEY=...                                # mouser.com Search API
enclosure parts --pcb board.kicad_pcb                    # MPNs from each footprint's MPN field
enclosure parts --set J1=USB4105-GF-A --set SW1=B3U-1000P
enclosure fit base.step board.step --lid lid.step --pcb board.kicad_pcb --parts parts.json
```

It asks DigiKey first, then Mouser, for each MPN: manufacturer, description, datasheet link (the
PDF is saved in `datasheets/`), and the seated height and size where the distributor lists
them, each with the parameter it came from. Values already in the file are kept: a reading from
the datasheet beats a listing. What only the datasheet drawing gives (a connector's panel
cutout, a body the distributor does not list) is written in from the PDF with its page in
`source`; the command lists the parts still missing a body and the connectors missing a cutout.
Keys are read from the environment and never stored.

Symbols, footprints and 3D models still come from KiCad's libraries or a model site
(SnapMagic, Ultra Librarian, Mouser's ECAD downloads); check each against the datasheet.

## What is not done yet

- Describing a board in words and having EncloSURE propose the layout, and writing enclosure
  changes back (an Onshape custom feature that cuts the openings and moves standoffs).
- Keepouts from datasheets (an antenna's clear zone) are not used yet.
- Reading the datasheet PDF itself is left to you or an agent: distributor listings give heights
  and sizes, but cutouts live in drawings.
- Non-rectangular cavities: the board outline is the cavity's box at board height, so a rounded
  or drafted cavity is approximated by its box. Standoffs must be round.
- Checking the board goes in: tilting it past walls and clips during assembly.

## Tests

```
pip install -e .[test] && pytest -q
```
