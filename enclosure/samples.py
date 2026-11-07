"""A sample enclosure, lid and board for trying EncloSURE and for its tests.

The base is 100 x 60 x 30 mm with 2 mm walls, four Ø6 standoffs with Ø2.5 pilot holes and a
USB-C opening in the -X wall; the lid has a Ø6 button hole. The board deliberately misfits in
four ways a fit check must catch: one mounting hole 0.8 mm off its standoff, the USB-C
receptacle 1.5 mm off the opening's centre, a capacitor too tall for the lid, and a part
touching the +Y wall.
"""

from __future__ import annotations

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
