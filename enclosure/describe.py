"""A first box from a few words: "ESP32 board 60x40, USB-C, two buttons, OLED, wall-mounted,
splash-proof".

It reads keywords, not meaning: a known board or a size like 80x50, connectors and controls by
name and count, a display, batteries, and words for where the box lives. Everything it assumed is
listed, so you can correct it in the form. It also writes the KiCad board to start the design in:
the outline, a mounting hole on each standoff and a marker where each opening lands.
"""

from __future__ import annotations

import re

from . import box as boxmod

NUMBERS = {"a": 1, "an": 1, "one": 1, "single": 1, "two": 2, "pair": 2, "three": 3, "four": 4, "five": 5, "six": 6}

# Known boards: (length, width, mounting holes as (x, y) from the board's lower-left corner, screw).
# Raspberry Pi: the published mechanical drawings (holes 3.5 mm in, 58 x 49 apart); Arduino Uno: the
# Rev3 reference design (holes at 550,100 / 600,2000 / 2600,300 / 2600,1400 mil).
BOARDS = {
    "raspberry pi zero": (65.0, 30.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 26.5), (61.5, 26.5)], "M2.5"),
    "pi zero": (65.0, 30.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 26.5), (61.5, 26.5)], "M2.5"),
    "raspberry pi": (85.0, 56.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)], "M2.5"),
    "arduino uno": (68.58, 53.34, [(13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)], "M3"),
    "arduino mega": (101.6, 53.34, [(13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56), (90.17, 50.8), (96.52, 2.54)], "M3"),
}

# Things on the walls or lid: keywords -> (cutout as box.py takes it, where, what was assumed).
THINGS = [
    (r"usb[\s-]?c", {"preset": "usb-c"}, "wall", "a USB-C receptacle at the board's edge"),
    (r"micro[\s-]?usb", {"shape": "rect", "size": [8.5, 3.6], "radius": 0.8}, "wall", "a micro-USB receptacle (7.5 x 2.6 mm face plus 0.5 mm a side)"),
    (r"(rj45|ethernet)", {"preset": "keystone"}, "wall", "Ethernet as a keystone jack"),
    (r"(barrel|dc jack|power jack)", {"preset": "dc-barrel-snap"}, "wall", "a snap-in 5.5 x 2.1 mm barrel jack"),
    (r"(sma|antenna)", {"preset": "sma-bulkhead"}, "wall", "an SMA bulkhead for the antenna"),
    (r"bnc", {"preset": "bnc-bulkhead"}, "wall", "a BNC bulkhead"),
    (r"toggle", {"preset": "toggle-1/4"}, "lid", "a toggle switch with a 1/4\" bushing"),
    (r"(22\s?mm|pilot light|e-?stop|emergency stop)", {"preset": "pushbutton-22"}, "lid", "22 mm pushbuttons or pilot lights"),
    (r"(gland|cable entry|cable in)", {"preset": "pg9"}, "wall", "PG9 cable glands"),
    (r"buttons?", {"shape": "round", "size": [12.0]}, "lid", "panel buttons in 12 mm holes (set the size from your button)"),
    (r"leds?", {"shape": "round", "size": [5.2]}, "lid", "5 mm LEDs (or light pipes) in 5.2 mm holes"),
]
DISPLAYS = [
    (r"(1\.3|1\.30)\s?(\"|in|inch)?\s?oled", (30.0, 16.0), "a 1.3\" OLED: 30 x 16 mm window (typical; set it from your module)"),
    (r"oled", (22.0, 11.5), "a 0.96\" OLED: 22 x 11.5 mm window (typical; set it from your module)"),
    (r"(16x2|1602|character lcd)", (64.5, 14.5), "a 16x2 character LCD: 64.5 x 14.5 mm window (typical; set it from your module)"),
    (r"(2\.8|3\.2)\s?(\"|in|inch)?\s?(tft|lcd|display|screen)", (58.0, 44.0), "a 2.8\" TFT: 58 x 44 mm window (typical; set it from your module)"),
    (r"(display|screen|lcd|tft)", (40.0, 25.0), "a display: 40 x 25 mm window (a guess; set it from your module)"),
]


def _count(text: str, at: int) -> int:
    before = text[max(0, at - 14):at].split()
    if before:
        w = before[-1].strip(",.;:x×")
        if w.isdigit():
            return max(1, min(int(w), 8))
        if w in NUMBERS:
            return NUMBERS[w]
    return 1


def design(text: str) -> tuple[boxmod.BoxSpec, list[str]]:
    t = " " + text.lower().replace("×", "x") + " "
    notes = []
    # The board.
    board = None
    for name, (bl, bw, holes, screw) in BOARDS.items():
        if name in t:
            board = (bl, bw, holes, screw, name)
            notes.append(f"board: {name.title()}, {bl:g} x {bw:g} mm, its {len(holes)} mounting holes, {screw} screws")
            break
    if board is None:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*x\s*(\d+(?:\.\d+)?)\s*(?:mm)?", t)
        if m:
            bl, bw = float(m.group(1)), float(m.group(2))
            holes = [(3.5, 3.5), (bl - 3.5, 3.5), (3.5, bw - 3.5), (bl - 3.5, bw - 3.5)]
            board = (bl, bw, holes, "M3", "board")
            notes.append(f"board: {bl:g} x {bw:g} mm with an M3 hole 3.5 mm in from each corner (move them to yours)")
        else:
            board = (60.0, 40.0, [(3.5, 3.5), (56.5, 3.5), (3.5, 36.5), (56.5, 36.5)], "M3", "board")
            notes.append("board: no size given, so 60 x 40 mm with an M3 hole in each corner; say e.g. \"80x50 board\"")
    bl, bw, holes, screw, _ = board

    # Where it lives.
    wet = re.search(r"(water|splash|outdoor|outside|ip6|weather|rain|damp)", t)
    lid = "screw"
    if re.search(r"(snap|tool-?less)", t):
        lid = "snap"
    elif re.search(r"(press|friction)", t):
        lid = "friction"
    if wet and lid != "screw":
        notes.append("a sealed box needs a screw lid: using one")
        lid = "screw"
    tall = re.search(r"(\d+(?:\.\d+)?)\s*mm\s*(tall|high)", t)
    part_h = float(tall.group(1)) if tall else 15.0
    if not tall:
        notes.append("tallest part on the board: 15 mm (say e.g. \"25 mm tall\")")

    # The box: the board plus room each side; a screw lid's posts need its corners clear.
    margin = 3.0 + (9.0 if lid == "screw" else 0.0)
    L, W = bl + 2 * margin, bw + 2 * 3.0
    if wet:
        L, W = L + 28, W + 28  # the gasket ledge reaches about 14 mm in
    so_h = 5.0
    H = so_h + 1.6 + part_h + 2.0 + 3.0
    cx, cy = bl / 2, bw / 2
    spec = boxmod.BoxSpec(size=[round(L, 1), round(W, 1), round(H, 1)], lid=lid, standoff_screw=screw,
                          standoffs=[[round(x - cx, 2), round(y - cy, 2)] for x, y in holes], teardrop=False)
    if wet:
        spec.gasket = 2.0
        notes.append("splash-proof: an O-ring gasket under the screw lid, and glands for cables")

    # Openings.
    walls = ["-X", "+X", "-Y", "+Y"]
    wall_load = {w: [] for w in walls}
    lid_items = []
    up = so_h + 1.6 + 2.0  # just above the board's top
    seen = set()
    for pattern, cut, where, said in THINGS:
        for m in re.finditer(r"\b" + pattern + r"\b", t):
            if (m.start(), m.end()) in seen or any(a <= m.start() < b for a, b in seen):
                continue
            seen.add((m.start(), m.end()))
            n = _count(t, m.start())
            notes.append(f"{n} x {said}" if n > 1 else said)
            for _ in range(n):
                if where == "lid":
                    lid_items.append(cut)
                else:
                    w = min(walls, key=lambda k: len(wall_load[k]))
                    wall_load[w].append(cut)
            break
    if wet and not any(c.get("preset", "").startswith("pg") for v in wall_load.values() for c in v):
        wall_load["-Y"].append({"preset": "pg9"})
    cutouts = []
    if any(wall_load.values()):
        notes.append("wall openings are spread round the walls to start: move each to where its connector is")
    for w, items in wall_load.items():
        span = (L if w in ("-Y", "+Y") else W) - 16
        for i, c in enumerate(items):
            along = -span / 2 + span * (i + 1) / (len(items) + 1)
            size = boxmod.Cutout(**{"face": w, **__import__("enclosure.presets", fromlist=["x"]).resolve({"face": w, **c})}).size
            if c.get("preset", "").startswith(("pg", "m1", "m2")):
                # A gland's locknut (about 1.5 x its hole) needs room above the floor and below the lid's lip.
                nut_r = 0.75 * size[0]
                height = nut_r + 1.0
                spec.size[2] = round(max(spec.size[2], height + nut_r + 1.0 + spec.lip + 1.0), 1)
            else:
                height = max(up + size[-1] / 2 - 1, size[-1] / 2 + 1.5)
            cutouts.append({"face": w, **c, "at": [round(along, 1), round(height, 1)]})
    # The display goes on the lid, centred; buttons and LEDs in a row below it.
    window = None
    for pattern, (dw, dh), said in DISPLAYS:
        if re.search(pattern, t):
            window = {"face": "lid", "size": [dw, dh], "at": [0, round(W / 6, 1)], "panel": [dw + 6, dh + 6], "panel_t": 1.0}
            spec.windows = [window]
            notes.append(said + "; a recess behind it for its glass")
            break
    row_y = -W / 4 if window else 0.0
    for i, c in enumerate(lid_items):
        x = -(len(lid_items) - 1) * 9 + i * 18
        cutouts.append({"face": "lid", **c, "at": [round(x, 1), round(row_y, 1)]})
    spec.cutouts = cutouts

    # Power, mounting, air.
    bat = re.search(r"(\d+|two|three|four|a|an)?\s*x?\s*(18650|21700|aaa|aa)\b", t)
    if bat:
        cell = bat.group(2).upper() if bat.group(2) in ("aa", "aaa") else bat.group(2)
        n = int(bat.group(1)) if (bat.group(1) or "").isdigit() else NUMBERS.get(bat.group(1) or "", 1)
        dia, length = boxmod.CELLS[cell]
        spec.batteries = [{"cell": cell, "count": n, "axis": "x", "at": [0, 0]}]
        # The cells go beside the board: grow the box along Y to fit them.
        extra = n * (dia + 0.4) + 3.2 + 4
        spec.size[1] = round(spec.size[1] + extra, 1)
        spec.standoffs = [[x, y + extra / 2] for x, y in spec.standoffs]
        spec.batteries[0]["at"] = [0, round(-spec.size[1] / 2 + extra / 2 + 0.5, 1)]
        spec.size[0] = round(max(spec.size[0], length + boxmod.CONTACT_ROOM + 8), 1)
        notes.append(f"{n} x {cell} cells in a cradle beside the board (add spring contacts)")
    if re.search(r"wall[\s-]?mount|on a wall|hang", t):
        spec.keyholes = "M4"
        notes.append("wall-mounted: two keyholes for M4 screws")
    if re.search(r"\bdin\b", t):
        spec.din_rail = True
        notes.append("a DIN rail clip")
    if re.search(r"(desk|bench|table|feet)", t):
        spec.feet = 10.0
        notes.append("rubber feet recesses")
    if re.search(r"(vent|hot|heat|warm|fan|airflow)", t) and not wet:
        spec.vents = [{"face": "+X", "size": [min(30, W - 16), 15], "at": [0, round(H * 0.55, 1)], "slot": 2.0, "pitch": 4.0},
                      {"face": "-X", "size": [min(30, W - 16), 15], "at": [0, round(H * 0.55, 1)], "slot": 2.0, "pitch": 4.0}]
        notes.append("vents on both ends")
    spec.check()
    return spec, notes


def make(text: str, out_pcb=None) -> dict:
    """The box, its notes, and the starting KiCad board (as text)."""
    import tempfile
    from pathlib import Path
    from . import kicad, shell
    spec, notes = design(text)
    made = boxmod.build(spec)
    enc, _ = shell.read(made["base"], made["lid"])
    with tempfile.TemporaryDirectory() as d:
        p = Path(out_pcb) if out_pcb else Path(d) / "board.kicad_pcb"
        lim = kicad.limits(enc, p)
        pcb = p.read_text()
    return {"spec": spec, "notes": notes, "made": made, "limits": lim, "kicad_pcb": pcb}
