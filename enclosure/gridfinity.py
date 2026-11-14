"""Gridfinity: the 42 mm modular storage grid (Zack Freedman's open spec), so a box or a bin sits in a
Gridfinity baseplate, and the baseplates and bins themselves.

The numbers: a grid unit is 42 x 42 mm and a height unit 7 mm. A bin is 0.5 mm smaller than its grid
(41.5 mm a unit) with 3.75 mm corners. Each unit has a foot 4.75 mm tall: from the bottom a 0.8 mm 45°
chamfer, 1.8 mm straight, then a 2.15 mm 45° chamfer out to the full size. The baseplate pocket is the
same shape 4.65 mm deep (0.7 / 1.8 / 2.15) with 4 mm outside corners. Magnets are 6 x 2 mm in 6.5 x 2.4 mm
holes, screws M3, both 13 mm each way from a foot's centre. The stacking lip on a bin's top is 4.4 mm:
0.7 mm 45°, 1.8 mm straight, 1.9 mm 45°."""

from __future__ import annotations

import math

from build123d import (Align, Box, Cylinder, Pos, RectangleRounded, Solid, loft)

GRID = 42.0
HEIGHT_UNIT = 7.0
GAP = 0.5               # a bin is this much smaller than its grid
BIN_R = 3.75            # a bin's corner radius
PLATE_R = 4.0           # a baseplate's outside corner radius
FOOT_H = 4.75
FOOT = ((0.0, 2.95), (0.8, 2.15), (2.6, 2.15), (4.75, 0.0))   # (z from the bottom, inset from 41.5)
POCKET = ((0.0, 2.85), (0.7, 2.15), (2.5, 2.15), (4.65, 0.0))  # (z from the bottom, inset from 42)
LIP = ((0.0, 2.6), (1.9, 0.7), (3.7, 0.7), (4.4, 0.0))         # (z from the lip's bottom, inset from the bin's outside)
MAGNET = (6.5, 2.4)     # hole for a 6 x 2 mm magnet
SCREW = (3.0, 6.0)      # hole for an M3 screw
HOLE_AT = 13.0          # magnet and screw holes this far each way from a foot's centre


def units(mm: float) -> int:
    """How many grid units a footprint of `mm` needs."""
    return max(1, math.ceil((mm + GAP - 0.01) / GRID))


def _section(w: float, l: float, r: float, z: float):
    r = max(0.2, min(r, w / 2 - 0.01, l / 2 - 0.01))
    return Pos(0, 0, z) * RectangleRounded(w, l, r).face()


def _stack(size_w: float, size_l: float, r_top: float, profile, z0: float = 0.0, grow: bool = True):
    """A solid lofted through `profile` [(z, inset)], each section the size less twice the inset, with
    the corner radius shrinking with the inset."""
    parts = []
    for (za, ia), (zb, ib) in zip(profile, profile[1:]):
        secs = [_section(size_w - 2 * i, size_l - 2 * i, r_top - i, z0 + z) for z, i in ((za, ia), (zb, ib))]
        parts.append(loft(secs))
    out = parts[0]
    for p in parts[1:]:
        out = out.fuse(p)
    return out.clean()


def foot():
    """One unit's foot, its bottom at z = 0 and its top (41.5 mm square) at z = 4.75."""
    s = GRID - GAP
    return _stack(s, s, BIN_R, FOOT)


def feet(nx: int, ny: int, magnets: bool = False, screws: bool = False):
    """The feet for an nx x ny footprint centred on the origin, bottoms at z = 0, with magnet and screw
    holes if asked."""
    one = foot()
    holes = []
    for dx in (-HOLE_AT, HOLE_AT):
        for dy in (-HOLE_AT, HOLE_AT):
            if magnets:
                holes.append(Pos(dx, dy, -0.01) * Cylinder(MAGNET[0] / 2, MAGNET[1] + 0.01,
                                                          align=(Align.CENTER, Align.CENTER, Align.MIN)))
            if screws:
                holes.append(Pos(dx, dy, -0.01) * Cylinder(SCREW[0] / 2, SCREW[1] + 0.01,
                                                          align=(Align.CENTER, Align.CENTER, Align.MIN)))
    for h in holes:
        one = one - h
    out = None
    for i in range(nx):
        for j in range(ny):
            f = Pos((i - (nx - 1) / 2) * GRID, (j - (ny - 1) / 2) * GRID, 0) * one
            out = f if out is None else out.fuse(f)
    return out


def baseplate(nx: int = 3, ny: int = 2, magnets: bool = False):
    """A plain (open-bottom) baseplate nx x ny units, its bottom at z = 0. With `magnets` it gets a
    floor under the pockets with magnet holes (6.4 mm thick in all)."""
    W, L = nx * GRID, ny * GRID
    floor = 1.75 + MAGNET[1] if magnets else 0.0  # under the pocket, room for the magnet and a skin
    H = POCKET[-1][0] + floor
    plate = Box(W, L, H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    try:
        from build123d import fillet, Axis
        plate = fillet(plate.edges().filter_by(Axis.Z), PLATE_R)
    except Exception:
        pass
    pocket = _stack(GRID, GRID, PLATE_R, POCKET, z0=floor)
    if not magnets:
        # Through: the pocket's bottom opens down through the plate.
        s = GRID - 2 * POCKET[0][1]
        pocket = pocket.fuse(Pos(0, 0, -1) * Box(s, s, 1.02 + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    else:
        for dx in (-HOLE_AT, HOLE_AT):
            for dy in (-HOLE_AT, HOLE_AT):
                pocket = pocket.fuse(Pos(dx, dy, floor - MAGNET[1]) * Cylinder(MAGNET[0] / 2, MAGNET[1] + 0.02,
                                                                                align=(Align.CENTER, Align.CENTER, Align.MIN)))
    # The pocket's top is the full 42 mm: lift it a hair so neighbouring cells cut clean.
    for i in range(nx):
        for j in range(ny):
            plate = plate - Pos((i - (nx - 1) / 2) * GRID, (j - (ny - 1) / 2) * GRID, 0.001) * pocket
    return plate


def bin_(nx: int = 1, ny: int = 1, height: int = 3, wall: float = 1.2, div_x: int = 0, div_y: int = 0,
         lip: bool = True, magnets: bool = False, screws: bool = False, label: bool = False):
    """A Gridfinity bin nx x ny units and `height` units (7 mm each) tall, not counting the stacking lip,
    its bottom at z = 0. Dividers split it into (div_x + 1) x (div_y + 1) pockets; `label` adds a 45°
    tab along the back wall for a label."""
    W, L = nx * GRID - GAP, ny * GRID - GAP
    H = height * HEIGHT_UNIT
    floor_top = HEIGHT_UNIT  # the inside floor is one height unit up
    body = Pos(0, 0, FOOT_H) * _prism(W, L, BIN_R, H - FOOT_H)
    body = body.fuse(feet(nx, ny, magnets, screws))
    # Hollow it, then add back the dividers.
    iw, il = W - 2 * wall, L - 2 * wall
    cavity = Pos(0, 0, floor_top) * _prism(iw, il, BIN_R - wall, H - floor_top + 10)
    body = body - cavity
    for k in range(1, div_x + 1):
        x = -iw / 2 + k * iw / (div_x + 1)
        body = body.fuse(Pos(x, 0, floor_top) * Box(wall, il + 0.02, H - floor_top, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    for k in range(1, div_y + 1):
        y = -il / 2 + k * il / (div_y + 1)
        body = body.fuse(Pos(0, y, floor_top) * Box(iw + 0.02, wall, H - floor_top, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    if label:
        tab = 12.0
        from build123d import Polygon, Plane, extrude
        prof = Polygon((il / 2, H), (il / 2 - tab, H), (il / 2, H - tab), align=None)
        body = body.fuse(extrude(Plane.YZ * prof, amount=iw / 2 + 0.01, both=True))
    if lip:
        ring = Pos(0, 0, H) * _prism(W, L, BIN_R, LIP[-1][0])
        inner = _stack(W, L, BIN_R, LIP, z0=H)
        inner = inner.fuse(Pos(0, 0, H + LIP[-1][0] - 0.01) * _prism(W, L, BIN_R, 1))
        # Under the lip, a 45° shelf back out to the wall so it prints without support.
        shelf = loft([_section(iw, il, BIN_R - wall, H - (2.6 - wall)),
                      _section(W - 2 * 2.6, L - 2 * 2.6, BIN_R - 2.6, H)])
        body = body - shelf  # clear any divider or tab inside the shelf's reach first
        body = body.fuse(ring.fuse(Pos(0, 0, H - (2.6 - wall)) * _prism(W, L, BIN_R, 2.6 - wall)) - inner - shelf)
    return body.clean()


def _prism(w: float, l: float, r: float, h: float):
    from build123d import extrude
    return extrude(_section(w, l, r, 0), amount=h)


def box_base(outer_l: float, outer_w: float, magnets: bool = False, screws: bool = False):
    """For a box: Gridfinity feet with a slab over them as big as the grid, to put under a box whose
    outside is outer_l x outer_w. Returns (shape with its top at z = 0, (nx, ny), slab thickness, notes)."""
    nx, ny = units(outer_l), units(outer_w)
    W, L = nx * GRID - GAP, ny * GRID - GAP
    slab = 1.2
    f = feet(nx, ny, magnets, screws)
    s = Pos(0, 0, FOOT_H) * _prism(W, L, BIN_R, slab)
    shape = Pos(0, 0, -(FOOT_H + slab)) * f.fuse(s)
    notes = [f"Gridfinity base: {nx} x {ny} units ({W:g} x {L:g} mm), feet {FOOT_H:g} mm and a {slab:g} mm slab under the "
             f"floor ({FOOT_H + slab:g} mm added to the height)"
             + (", 6 x 2 mm magnet holes under each foot" if magnets else "") + (", M3 screw holes" if screws else "")]
    spare_l, spare_w = W - outer_l, L - outer_w
    if spare_l > 6 or spare_w > 6:
        notes.append(f"the grid is {spare_l:.1f} x {spare_w:.1f} mm bigger than the box: make it outside "
                     f"{W:g} x {L:g} mm to use the whole footprint")
    return shape, (nx, ny), FOOT_H + slab, notes
