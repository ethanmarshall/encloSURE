"""A sample enclosure, lid and board for trying EncloSURE and for its tests.

The base is 100 x 60 x 30 mm with 2 mm walls, four Ø6 standoffs with Ø2.5 pilot holes and a
USB-C opening in the -X wall; the lid has a Ø6 button hole. The board deliberately misfits in
four ways a fit check must catch: one mounting hole 0.8 mm off its standoff, the USB-C
receptacle 1.5 mm off the opening's centre, a capacitor too tall for the lid, and a part
touching the +Y wall.
"""

from __future__ import annotations

import os
from pathlib import Path

from build123d import Box, Compound, Cylinder, Location, Pos, export_step

BASE = dict(length=100.0, width=60.0, height=30.0, wall=2.0, floor=2.0)
BOSS_XY = [(-40.0, -20.0), (40.0, -20.0), (-40.0, 20.0), (40.0, 20.0)]
BOSS_D, BOSS_HOLE, BOSS_H = 6.0, 2.5, 5.0
PCB_T = 1.6
USB_W, USB_H = 9.5, 3.8  # the opening
USB_BODY = (7.35, 8.94, 3.26)  # receptacle: depth (X), width (Y), height (Z)
LID_T = 2.0
BUTTON = (20.0, 0.0, 6.0)  # lid hole x, y, diameter


def base():
    L, W, H, t, f = BASE["length"], BASE["width"], BASE["height"], BASE["wall"], BASE["floor"]
    shell = Box(L, W, H).locate(Location((0, 0, H / 2)))
    shell -= Box(L - 2 * t, W - 2 * t, H).locate(Location((0, 0, f + H / 2)))
    top = f + BOSS_H
    for x, y in BOSS_XY:
        shell += Cylinder(BOSS_D / 2, BOSS_H).locate(Location((x, y, f + BOSS_H / 2)))
        shell -= Cylinder(BOSS_HOLE / 2, BOSS_H).locate(Location((x, y, f + BOSS_H / 2 + 0.5)))
    usb_z = top + PCB_T + USB_BODY[2] / 2
    shell -= Box(4 * t, USB_W, USB_H).locate(Location((-L / 2, 0, usb_z)))
    return shell


def lid():
    L, W, H = BASE["length"], BASE["width"], BASE["height"]
    plate = Box(L, W, LID_T).locate(Location((0, 0, H + LID_T / 2)))
    x, y, d = BUTTON
    plate -= Cylinder(d / 2, 3 * LID_T).locate(Location((x, y, H + LID_T / 2)))
    return plate


def board(frame=(150.0, 100.0)):
    """The board as KiCad would export it: its own frame (here offset by *frame*), PCB from
    z = 0 to 1.6, parts above, each solid named by its reference."""
    ox, oy = frame
    L = BASE["length"] - 2 * BASE["wall"] - 2.0  # 94: 1 mm clear of each wall
    W = BASE["width"] - 2 * BASE["wall"] - 2.0  # 54
    pcb = Box(L, W, PCB_T).locate(Location((ox, oy, PCB_T / 2)))
    holes = list(BOSS_XY)
    holes[3] = (holes[3][0] + 0.8, holes[3][1])  # misfit 1: one hole 0.8 mm off
    for x, y in holes:
        pcb -= Cylinder(3.2 / 2, 3 * PCB_T).locate(Location((ox + x, oy + y, PCB_T / 2)))
    pcb.label = "PCB"
    parts = []

    def part(name, shape):
        shape.label = name
        parts.append(shape)

    dx, dy, dz = USB_BODY
    # misfit 2: the receptacle 1.5 mm off the opening's centre; its front 0.6 mm past the edge
    part("J1", Box(dx, dy, dz).locate(Location((ox - L / 2 + dx / 2 - 0.6, oy + 1.5, PCB_T + dz / 2))))
    part("U1", Box(10, 10, 1.2).locate(Location((ox, oy, PCB_T + 0.6))))
    # misfit 3: a capacitor taller than the lid allows
    part("C1", Cylinder(4.0, 24.0).locate(Location((ox + 25, oy + 10, PCB_T + 12.0))))
    part("SW1", Box(6, 6, 5).locate(Location((ox + BUTTON[0], oy + BUTTON[1], PCB_T + 2.5))))
    # misfit 4: a connector hanging over the +Y edge into the wall
    part("J2", Box(8, 6, 6).locate(Location((ox - 10, oy + W / 2 - 1.0, PCB_T + 3.0))))
    return Compound(children=[pcb, *parts])


def write(folder: str | Path) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = {"base": folder / "sample_base.step", "lid": folder / "sample_lid.step",
             "board": folder / "sample_board.step"}
    export_step(base(), str(paths["base"]))
    export_step(lid(), str(paths["lid"]))
    export_step(board(), str(paths["board"]))
    return {k: str(v) for k, v in paths.items()}


# A KiCad sample board, for "a box from a board" and its tests: real STEP models for each part, a
# .kicad_pcb that places them, and KiCad's own STEP export of the board (needs kicad-cli).
BOARD = {"x0": 100.0, "y0": 100.0, "w": 80.0, "h": 50.0, "t": 1.6}
# ref: (footprint, (x, y) on the page, rotation, model box (x0, x1, y0, y1, height) in the footprint frame)
BOARD_PARTS = {
    "J1": ("Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal", (103.0, 125.0), 0,
           (-3.6, 3.75, -4.47, 4.47, 3.26)),  # its face 0.6 mm past the -X edge
    "J2": ("TerminalBlock:TerminalBlock_bornier-2_P5.08mm", (175.5, 118.0), 0,
           (-4.0, 5.1, -5.1, 5.1, 10.0)),  # wire entry at the +X edge
    "C1": ("Capacitor_THT:CP_Radial_D8.0mm_P3.50mm", (140.0, 125.0), 0, None),  # Ø8 x 11.5 can
    "SW1": ("Button_Switch_SMD:SW_SPST_TL3342", (150.0, 140.0), 0, (-3.0, 3.0, -3.0, 3.0, 5.0)),
}
BOARD_HOLES = [(104.0, 104.0), (176.0, 104.0), (104.0, 146.0), (176.0, 146.0)]


def kicad_board(folder) -> dict:
    """Write the sample KiCad board and its part models; export the board's STEP with kicad-cli
    when KiCad is installed. Returns the paths."""
    import shutil
    import subprocess
    import uuid
    from build123d import Align, Box, Cylinder, Pos, export_step

    folder = Path(folder)
    (folder / "models").mkdir(parents=True, exist_ok=True)
    b = BOARD
    x1, y1 = b["x0"] + b["w"], b["y0"] + b["h"]
    items = []
    for (ax, ay), (bx, by) in [((b["x0"], b["y0"]), (x1, b["y0"])), ((x1, b["y0"]), (x1, y1)),
                               ((x1, y1), (b["x0"], y1)), ((b["x0"], y1), (b["x0"], b["y0"]))]:
        items.append(f'  (gr_line (start {ax} {ay}) (end {bx} {by}) (stroke (width 0.1) (type default)) '
                     f'(layer "Edge.Cuts") (tstamp {uuid.uuid4()}))')
    for i, (x, y) in enumerate(BOARD_HOLES, 1):
        items.append(f'  (footprint "MountingHole:MountingHole_3.2mm_M3" (layer "F.Cu") (tstamp {uuid.uuid4()}) (at {x} {y})\n'
                     f'    (fp_text reference "H{i}" (at 0 -3) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))\n'
                     f'    (fp_text value "MountingHole_3.2mm_M3" (at 0 3) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))\n'
                     f'    (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "F&B.Cu" "*.Mask")))')
    for ref, (fp, (x, y), rot, body) in BOARD_PARTS.items():
        model = folder / "models" / f"{ref}.step"
        if body is None:  # a round can
            shape = Pos(1.75, 0, 0) * Cylinder(4.0, 11.5, align=(Align.CENTER, Align.CENTER, Align.MIN))
            crt = (-2.5, 6.0, -4.25, 4.25)
        else:
            mx0, mx1, my0, my1, hh = body
            shape = Pos((mx0 + mx1) / 2, (my0 + my1) / 2, 0) * Box(mx1 - mx0, my1 - my0, hh, align=(Align.CENTER, Align.CENTER, Align.MIN))
            crt = (mx0 - 0.25, mx1 + 0.25, my0 - 0.25, my1 + 0.25)
        export_step(shape, str(model))
        cx0, cx1, cy0, cy1 = crt
        court = "\n".join(f'    (fp_line (start {a} {c}) (end {bb} {d}) (stroke (width 0.05) (type default)) (layer "F.CrtYd"))'
                          for a, c, bb, d in [(cx0, cy0, cx1, cy0), (cx1, cy0, cx1, cy1), (cx1, cy1, cx0, cy1), (cx0, cy1, cx0, cy0)])
        items.append(f'  (footprint "{fp}" (layer "F.Cu") (tstamp {uuid.uuid4()}) (at {x} {y} {rot})\n'
                     f'    (fp_text reference "{ref}" (at 0 -6) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))\n'
                     f'    (fp_text value "{ref}" (at 0 6) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))\n'
                     f'{court}\n'
                     f'    (model "{model.resolve()}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))')
    from .kicad import LAYERS, VERSION, _q
    layers = "\n".join("    (" + " ".join([str(n)] + [_q(v) if i != 1 else v for i, v in enumerate(rest)]) + ")" for n, *rest in LAYERS)
    text = (f'(kicad_pcb (version {VERSION}) (generator "enclosure")\n  (general (thickness {b["t"]}))\n  (paper "A4")\n'
            f'  (layers\n{layers}\n  )\n  (setup (pad_to_mask_clearance 0))\n  (net 0 "")\n' + "\n".join(items) + "\n)\n")
    pcb = folder / "board.kicad_pcb"
    pcb.write_text(text)
    out = {"pcb": str(pcb), "models": str(folder / "models")}
    cli = shutil.which("kicad-cli") or os.environ.get("BACKPLANE_KICAD_CLI")
    if cli:
        step = folder / "board.step"
        subprocess.run([cli, "pcb", "export", "step", "--subst-models", "-f", "-o", str(step), str(pcb)],
                       check=True, capture_output=True)
        out["step"] = str(step)
    return out
