"""A hinged case with snap-on latch tabs, the kind sold as a parts organiser: a tray, a lid that snaps
onto ball-and-socket hinges along the back, and separate closure tabs that pivot on the lid and click
onto the tray at the front. Nothing to buy: every joint is a printed ball in a printed socket.

How it goes together (z up, the front at -Y, the hinges at +Y):

- The tray's wall has a shoulder with a lip inside it; the lid's wall sits on the shoulder and has a
  rebate that drops over the lip, so the lid locates and dust stays out.
- Each hinge is a pair of cheeks on the tray with sockets facing each other, and a lug on the lid with
  a ball each side that snaps between them. The axis is at the parting line, outside the wall, so the
  lid opens right over to lie flat.
- Each latch is a pair of cheeks on the lid with sockets, a tab that snaps between them on two balls
  and swings, and a pair of posts on the tray below. The tab's lower balls are on thin sprung arms and
  click into sockets in the posts; they sit a little high of the sockets so the lid is pulled down.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from build123d import Align, Box, Cylinder, Polygon, Plane, Pos, Rot, RectangleRounded, Sphere, chamfer, extrude, Axis

LIP_H = 2.4        # the lip stands this far above the shoulder
LIP_GAP = 0.25     # between the lip and the lid's rebate, each side
CHEEK_W = 6.4      # every cheek and post is this wide
SIDE = 0.3         # sideways clearance between a lug or tab and its cheeks, each side
HINGE_E = 4.4      # the hinge axis is this far outside the wall
HINGE_R = 4.2      # radius of the hinge's round ends
HINGE_GAP = 13.2   # between a hinge's two cheeks
HINGE_BALL = (4.5, 1.2)   # (sphere radius, how far it stands out of the lug)
TAB_W = 25.0       # the latch tab's width
TAB_T = 6.0        # and thickness
TAB_E = 3.4        # the tab's pivot is this far outside the wall, and below the lid's top
POST_D = 8.0       # how far the latch's cheeks and posts stand out of the wall
PIVOT_BALL = (5.0, 1.1)
CATCH_BALL = (7.0, 0.8)
SOCKET_EXTRA = 0.15       # a socket's radius over its ball's
CATCH_MIN = 13.0   # pivot to catch, at least
TAIL = 10.0        # the tab runs this far past the catch (the sprung arms' roots and the finger lip)
PRELOAD = 0.45     # the catch sockets sit this far low, so the latch pulls the lid down
RIB = 1.2          # dividers and lid ribs


GRID = 42.0          # a Gridfinity unit
GRID_EDGE = 0.3      # room between the grid and the tray's wall, each side
GRID_ROOM = 0.6      # between the top of the bins and the lid


@dataclass
class Case:
    size: tuple = (160.0, 100.0, 30.0)  # inside length (X), width (Y) and height, floor to the lid's underside
    lid_depth: float = 6.0     # how much of the inside height is in the lid
    wall: float = 3.2
    floor: float = 2.4         # the tray's floor and the lid's top
    corner_radius: float = 3.0
    hinges: int = 0            # 0 picks by length
    latches: int = 0           # 0 picks by length
    dividers_x: int = 0        # walls across the tray, splitting its length
    dividers_y: int = 0        # walls along the tray, splitting its width
    lid_ribs: bool = True      # ribs under the lid over the dividers, so small parts stay in their pockets
    # Loose bins that lift out, on a grid of cells inside the tray (instead of fixed dividers).
    insert_cols: int = 0       # cells along the length; 0 for no inserts
    insert_rows: int = 0       # cells across the width
    insert_bins: str = ""      # bigger bins as "cells along x cells across: how many", e.g. "2x1:2, 2x2:1"
    insert_fill: bool = True   # fill what's left with one-cell bins
    insert_layers: int = 1     # 2 stacks two half-height layers
    insert_wall: float = 1.2
    insert_scoop: bool = False  # a rounded front inside each bin, to slide small parts out
    insert_label: bool = False  # a label tab along the back of each bin
    # Or one lift-out tray with a pocket for each thing: "round 12:6, rect 40x25:2, slot 80x12" (size : how many)
    # Gridfinity inside: a baseplate built into the tray's floor and standard bins to drop into it.
    grid_cols: int = 0         # 42 mm units along the length; 0 for none. The grid sets the inside length and width
    grid_rows: int = 0
    grid_bins: str = ""        # bigger bins as "units along x units across: how many"; the rest are 1 x 1
    grid_fill: bool = True
    grid_height: int = 0       # bin height in 7 mm units; 0 for as tall as the case allows
    # Sections: different things side by side along the length, walled off from each other. A list of
    #   {"kind": "space", "name", "x", "y", "z", "turn": "auto" | "as typed" | "turned", "fit"}   a thing dropped in
    #   {"kind": "holes", "name", "count", "d", "depth", "slot_l", "slot_w", "slot_d"}            a block of holes, and a slot
    #   {"kind": "cells", "name", "count", "x", "y"}                                              compartments
    # The sections set the inside length and width, and the height if something is taller.
    sections: list | None = None
    section_wall: float = RIB  # the walls between sections and compartments
    sections_front: bool = False   # the first row along the front by the latches, not the back by the hinges
    insert_pockets: str = ""
    pocket_depth: float = 0.0   # 0: as deep as the case allows, up to 15 mm

    def check(self) -> None:
        L, W, H = self.size
        if not (45 <= L <= 400 and 30 <= W <= 400):
            raise ValueError("case: inside length 45 to 400 mm, width 30 to 400 mm")
        if not 2.4 <= self.wall <= 6:
            raise ValueError("case wall: 2.4 to 6 mm (it carries a lip and a rebate)")
        if not 1.2 <= self.floor <= 6:
            raise ValueError("case floor: 1.2 to 6 mm")
        if self.lid_depth < LIP_H + 0.6:
            raise ValueError(f"the lid's depth must be at least {LIP_H + 0.6:g} mm (it drops over a {LIP_H:g} mm lip)")
        if self.lid_depth > H - 6:
            raise ValueError("the lid's depth takes nearly all the inside height: leave the tray at least 6 mm")
        for n, what in ((self.hinges, "hinges"), (self.latches, "latches")):
            if not 0 <= int(n) <= 6:
                raise ValueError(f"{what}: 0 (automatic) to 6")
        if not (0 <= int(self.dividers_x) <= 12 and 0 <= int(self.dividers_y) <= 12):
            raise ValueError("dividers: 0 to 12 each way")
        if self.sections:
            if (int(self.grid_cols) or int(self.grid_rows) or int(self.insert_cols) or int(self.insert_rows) or int(self.dividers_x) or int(self.dividers_y)
                    or str(self.insert_pockets or "").strip()):
                raise ValueError("sections, Gridfinity bins, lift-out bins, a pocket tray, or fixed dividers: pick one and clear the others")
        gc, gr = int(self.grid_cols), int(self.grid_rows)
        if (gc > 0) != (gr > 0):
            raise ValueError("Gridfinity: set the units both ways (along the length and across the width), or neither")
        if gc:
            if not (1 <= gc <= 9 and 1 <= gr <= 9):
                raise ValueError("Gridfinity: 1 to 9 units each way (a unit is 42 mm)")
            if int(self.insert_cols) or int(self.insert_rows) or int(self.dividers_x) or int(self.dividers_y) or str(self.insert_pockets or "").strip():
                raise ValueError("Gridfinity bins, lift-out bins, a pocket tray, or fixed dividers: pick one and clear the others")
            top = int((H - GRID_ROOM) // 7)
            if top < 2:
                raise ValueError(f"Gridfinity bins need an inside height of at least {14 + GRID_ROOM:g} mm (the shortest bin is 14 mm)")
            if not 0 <= int(self.grid_height) <= top or int(self.grid_height) == 1:
                raise ValueError(f"Gridfinity bin height: 2 to {top} units in this case (7 mm each), or 0 for the tallest that fits")
        ic, ir = int(self.insert_cols), int(self.insert_rows)
        if (ic > 0) != (ir > 0):
            raise ValueError("inserts: set the cells both ways (along the length and across the width), or neither")
        if str(self.insert_pockets or "").strip() and (ic or int(self.dividers_x) or int(self.dividers_y)):
            raise ValueError("a pocket tray, a grid of bins, or fixed dividers: pick one and clear the others")
        if ic:
            if not (1 <= ic <= 12 and 1 <= ir <= 12):
                raise ValueError("inserts: 1 to 12 cells each way")
            if int(self.dividers_x) or int(self.dividers_y):
                raise ValueError("fixed dividers or lift-out inserts, not both: set the dividers to 0")
            if int(self.insert_layers) not in (1, 2, 3):
                raise ValueError("insert layers: 1, 2 or 3")
            if not 0.8 <= float(self.insert_wall) <= 3:
                raise ValueError("insert wall: 0.8 to 3 mm")


def _spread(n: int, span: float, unit: float, margin: float) -> list[float]:
    """Centres for n units `unit` wide across `span`, the outer ones `margin` in from the ends."""
    if n == 1:
        return [0.0]
    end = span / 2 - margin - unit / 2
    return [-end + 2 * end * i / (n - 1) for i in range(n)]


def _prism_yz(points, x0: float, x1: float):
    """A solid from a (y, z) outline, between x0 and x1."""
    return Pos(x0, 0, 0) * extrude(Plane.YZ * Polygon(*points, align=None), amount=x1 - x0, dir=(1, 0, 0))


def _block(sign: int, yw: float, depth: float, z0: float, z1: float, c: float, x0: float, x1: float, at: str):
    """A cheek or post standing `depth` out of the wall at y = sign * yw, from z0 to z1, rooted 0.2 mm inside
    the wall, with the box's own chamfer `c` on its outer edge at the bottom or the top."""
    yi, yo = yw - 0.2, yw + depth   # its root follows the chamfer, 0.2 mm inside the wall's face
    if at == "bottom":
        pts = [(yi - c, z0), (yo - c, z0), (yo, z0 + c), (yo, z1), (yi, z1), (yi, z0 + c)]
    else:
        pts = [(yi, z0), (yo, z0), (yo, z1 - c), (yo - c, z1), (yi - c, z1), (yi, z1 - c)]
    return _prism_yz([(sign * y, z) for y, z in pts], x0, x1)


def _ball(R: float):
    """A sphere with its seam turned to the side, away from the faces the balls and sockets are cut on."""
    return Rot(0, 0, 90) * Sphere(R)


def _cap(x_face: float, out: int, y: float, z: float, ball):
    """A ball standing out of a face at x = x_face (out = +1 or -1 is the way it points)."""
    R, p = ball
    s = Pos(x_face - out * (R - p), y, z) * _ball(R)
    keep = Pos(x_face + out * R, y, z) * Box(2 * R, 4 * R, 4 * R)
    return s & keep


def _socket(x_face: float, into: int, y: float, z: float, ball):
    """The hollow for that ball, in a face at x = x_face that is SIDE away from the ball's own face
    (into = +1 or -1 is the way it goes in)."""
    R, p = ball
    # The ball's face is SIDE back from this one; its sphere's centre is R - p behind that.
    return Pos(x_face - into * (SIDE + R - p), y, z) * _ball(R + SOCKET_EXTRA)


INSERT_EDGE = 0.15   # play between the outer bins and the tray's wall
INSERT_GAP = 0.3     # between one bin and the next


def parse_bins(text: str) -> list[tuple[int, int, int]]:
    """'2x1:2, 2x2' -> [(2, 1, 2), (2, 2, 1)]: cells along the length x cells across the width, and how many."""
    out = []
    for part in str(text or "").replace(";", ",").split(","):
        part = part.strip().lower().replace("×", "x").replace(" ", "")
        if not part:
            continue
        size, _, count = part.partition(":")
        a, _, b = size.partition("x")
        try:
            cw, ch, n = int(a), int(b), int(count) if count else 1
        except ValueError:
            raise ValueError(f"bins: write each as cells x cells : how many, like 2x1:2 (got '{part}')")
        if cw < 1 or ch < 1 or not 1 <= n <= 144:
            raise ValueError(f"bins: '{part}' needs at least 1 cell each way and a count of 1 or more")
        out.append((cw, ch, n))
    return out


def lay_out(cols: int, rows: int, bins: list[tuple[int, int, int]], fill: bool = True) -> list[tuple[int, int, int, int]]:
    """Place the bins on the grid, biggest first, turning one where that makes it fit. Returns
    [(cells along, cells across, column, row)]; with `fill`, one-cell bins take what's left."""
    used = [[False] * cols for _ in range(rows)]
    placed = []

    def fits(cw, ch, c0, r0):
        return c0 + cw <= cols and r0 + ch <= rows and not any(used[r][c] for r in range(r0, r0 + ch) for c in range(c0, c0 + cw))

    todo = sorted(((cw, ch) for cw, ch, n in bins for _ in range(n)), key=lambda b: (-b[0] * b[1], -max(b)))
    for cw, ch in todo:
        spot = next(((a, b, c0, r0) for r0 in range(rows) for c0 in range(cols) for a, b in ((cw, ch), (ch, cw)) if fits(a, b, c0, r0)), None)
        if spot is None:
            raise ValueError(f"the bins don't fit a {cols} x {rows} grid: no room left for a {cw}x{ch} "
                             f"({sum(a * b for a, b in todo)} cells asked for, {cols * rows} in the grid)")
        a, b, c0, r0 = spot
        for r in range(r0, r0 + b):
            for c in range(c0, c0 + a):
                used[r][c] = True
        placed.append((a, b, c0, r0))
    if fill:
        placed += [(1, 1, c, r) for r in range(rows) for c in range(cols) if not used[r][c]]
    return placed


def insert_bin(w: float, d: float, h: float, wall: float = 1.2, scoop: bool = False, label: bool = False):
    """A lift-out bin w x d x h, centred on the origin, standing on z = 0: thin walls, a 1 mm floor,
    its front (-Y) rounded inside for scooping parts out, and a label tab along the back, if asked."""
    floor = 1.0
    r = min(1.5, w / 4, d / 4)
    body = extrude(RectangleRounded(w, d, r), amount=h)
    body = chamfer(body.edges().group_by(Axis.Z)[0], 0.5)
    iw, idp = w - 2 * wall, d - 2 * wall
    if iw < 3 or idp < 3:
        raise ValueError(f"a bin {w:.1f} x {d:.1f} mm is too small for {wall:g} mm walls: fewer cells, or thinner walls")
    body -= Pos(0, 0, floor) * extrude(RectangleRounded(iw, idp, max(0.3, r - wall)), amount=h)
    if scoop:
        R = min(0.6 * (h - floor), 0.45 * idp, 14.0)
        if R >= 2:
            fill_ = Pos(0, -idp / 2 + R / 2, floor + R / 2) * Box(iw + 0.02, R, R)
            fill_ -= Pos(0, -idp / 2 + R, floor + R) * Cylinder(R, iw + 2, rotation=(0, 90, 0))
            body += fill_
    if label:
        tabd = min(9.0, 0.35 * idp)
        if tabd >= 3 and h - floor > tabd + 3:
            body += _prism_yz([(idp / 2 + 0.01, h), (idp / 2 - tabd, h), (idp / 2 + 0.01, h - tabd)], -iw / 2 - 0.01, iw / 2 + 0.01)
    return body.clean()


POCKET_SHAPES = ("round", "rect", "slot")


def parse_pockets(text: str) -> list[tuple[str, float, float, int]]:
    """'round 12:6, rect 40x25:2, slot 80x12' -> [(shape, a, b, how many)], sizes in mm. A round has one
    size, its diameter; a rect and a slot (a rect with round ends) have length x width."""
    out = []
    for part in str(text or "").replace(";", ",").split(","):
        part = part.strip().lower().replace("×", "x")
        if not part:
            continue
        body, _, count = part.partition(":")
        words = body.split()
        try:
            shape = {"round": "round", "circle": "round", "hole": "round", "rect": "rect", "rectangle": "rect", "square": "rect",
                     "slot": "slot"}[words[0]]
            dims = [float(v) for v in "".join(words[1:]).split("x")]
            n = int(count) if count.strip() else 1
            a, b = (dims[0], dims[0]) if len(dims) == 1 else (dims[0], dims[1])
        except (KeyError, ValueError, IndexError):
            raise ValueError(f"pockets: write each as a shape and a size, like 'round 12:6' or 'rect 40x25:2' or 'slot 80x12' (got '{part}')") from None
        if not (2 <= min(a, b) and max(a, b) <= 400 and 1 <= n <= 60):
            raise ValueError(f"pockets: '{part}' needs sizes of 2 mm or more and a count of 1 to 60")
        out.append((shape, max(a, b), min(a, b), n))
    return out


def pocket_tray(L: float, W: float, height: float, pockets: list, depth: float):
    """One tray L x W x height with the pockets cut `depth` into its top, laid out in rows. Returns
    (the tray, how many pockets, a note on any that got a finger notch)."""
    fit, gap, edge = 0.4, 3.0, 3.0
    items = sorted(((s, a + fit, b + fit) for s, a, b, n in pockets for _ in range(n)), key=lambda it: (-it[2], -it[1]))
    body = extrude(RectangleRounded(L, W, 1.5), amount=height)
    body = chamfer(body.edges().group_by(Axis.Z)[0], 0.5)
    x, y, row_h = -L / 2 + edge, W / 2 - edge, 0.0
    z = height - depth
    notches = 0
    for shape, a, b in items:
        if a > L - 2 * edge:
            raise ValueError(f"a {a - fit:g} mm pocket is longer than the tray's {L - 2 * edge:.0f} mm of room")
        if x + a > L / 2 - edge + 0.01:                     # the row is full: start the next one
            x, y, row_h = -L / 2 + edge, y - row_h - gap, 0.0
        if y - b < -W / 2 + edge - 0.01:
            raise ValueError("the pockets don't all fit this case: fewer or smaller pockets, or a bigger case")
        cx, cy = x + a / 2, y - b / 2
        if shape == "round":
            cut = Cylinder(a / 2, depth + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
        elif shape == "slot":
            cut = extrude(RectangleRounded(a, b, b / 2 - 0.01), amount=depth + 1)
        else:
            cut = extrude(RectangleRounded(a, b, min(1.0, b / 4)), amount=depth + 1)
        body -= Pos(cx, cy, z) * cut
        if shape != "round" and a >= 24 and b <= 30:        # a finger notch across a long, narrow pocket
            body -= Pos(cx, cy, z + depth * 0.2) * Cylinder(min(9.0, a / 3), depth + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
            notches += 1
        x += a + gap
        row_h = max(row_h, b)
    return body.clean(), len(items), notches


def tab(catch: float = CATCH_MIN):
    """A latch tab lying flat, as it prints: its outside face on z = 0, the pivot along X through
    (y = 0, z = TAB_T / 2), its length along +Y to the free end."""
    hw, t = TAB_W / 2, TAB_T
    end = catch + TAIL
    body = Pos(0, end / 2, 0) * Box(TAB_W, end, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body += Pos(0, 0, t / 2) * Cylinder(t / 2, TAB_W, rotation=(0, 90, 0))  # the round nose it turns on
    # The arch between the two pivot lobes, so they can spring in.
    arch = extrude(RectangleRounded(16.0, 20.0, 3.5), amount=t * 3)
    body -= Pos(0, 3.7 - 10.0, -t) * arch
    # A notch each side makes a neck for each lobe to bend at.
    for s in (-1, 1):
        notch = extrude(Polygon((s * (hw + 0.1), 3.7), (s * (hw - 3.0), 6.7), (s * (hw + 0.1), 9.7), align=None), amount=t * 3)
        body -= Pos(0, 0, -t) * notch
    # The sprung arms that carry the catch balls: rooted near the free end, free toward the pivot.
    arm_w, slot = 2.4, 1.0
    free, root = catch - 2.6, catch + TAIL - 2.5
    for s in (-1, 1):
        x_in = hw - arm_w - slot
        body -= Pos(s * (x_in + slot / 2), (free - slot + root) / 2, -t) * Box(slot, root - free + slot, t * 3,
                                                                              align=(Align.CENTER, Align.CENTER, Align.MIN))
        body -= Pos(s * (x_in + slot / 2), root, -t) * Cylinder(slot / 2, t * 3, align=(Align.CENTER, Align.CENTER, Align.MIN))
        body -= Pos(s * (x_in + (arm_w + slot + 0.2) / 2), free - slot / 2, -t) * Box(arm_w + slot + 0.2, slot, t * 3,
                                                                                    align=(Align.CENTER, Align.CENTER, Align.MIN))
    # The finger lip: the wall side of the free end slopes away so a fingertip gets behind it.
    body -= _prism_yz([(end - 5.0, t + 0.1), (end + 0.1, t + 0.1), (end + 0.1, 1.2)], -TAB_W, TAB_W)
    # The balls, trimmed to the tab's thickness.
    slab = Pos(0, 0, t / 2) * Box(TAB_W + 10, 400, t)
    for s in (-1, 1):
        body += _cap(s * hw, s, 0.0, t / 2, PIVOT_BALL) & slab
        body += _cap(s * hw, s, catch, t / 2, CATCH_BALL) & slab
    return body.clean()


SECTION_KINDS = ("space", "holes", "cells")


def _num(d: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(d.get(key) if d.get(key) not in (None, "") else default)
    except (TypeError, ValueError):
        raise ValueError(f"sections: '{key}' should be a number") from None


def plan_sections(sections: list, wall: float = RIB) -> dict:  # noqa: C901
    """Lay the sections side by side along the length. Each gets the full width; the widest thing
    sets the width. A space for a thing is turned whichever way makes the case most nearly square
    (unless told), since that is what fits a printer's bed. Returns the inside length and width,
    the height the tallest thing needs, and each section's place and make-up."""
    import itertools
    if not isinstance(sections, list) or not sections:
        raise ValueError("sections: a list of the things that go inside")
    if len(sections) > 16:
        raise ValueError("sections: up to 16 in one case, row breaks included")
    secs = []
    banded = any(isinstance(r, dict) and (r.get("kind") in ("break", "open") or r.get("len") or r.get("dep")) for r in sections)
    for i, raw in enumerate(sections):
        if isinstance(raw, dict) and raw.get("kind") in ("break", "open"):
            d = {"kind": raw["kind"], "name": str(raw.get("name") or "").strip()[:40] or "open space", "len": _num(raw, "len"), "dep": _num(raw, "dep")}
            secs.append(d)
            continue
        if not isinstance(raw, dict) or raw.get("kind") not in SECTION_KINDS:
            raise ValueError(f"section {i + 1}: its kind is one of {', '.join(SECTION_KINDS)}")
        d = dict(raw)
        d["name"] = str(d.get("name") or "").strip()[:40] or {"space": "space", "holes": "holes", "cells": "compartments"}[d["kind"]]
        if d["kind"] == "space":
            d["x"], d["y"], d["z"], d["fit"] = _num(d, "x"), _num(d, "y"), _num(d, "z"), _num(d, "fit", 1.0)
            if not (5 <= d["x"] <= 400 and 5 <= d["y"] <= 400 and 0 <= d["z"] <= 200 and 0 <= d["fit"] <= 10):
                raise ValueError(f"section {i + 1} ({d['name']}): a thing 5 to 400 mm long and wide, up to 200 mm tall")
            if d.get("turn") not in (None, "", "auto", "as typed", "turned"):
                raise ValueError(f"section {i + 1}: turn is auto, as typed or turned")
        elif d["kind"] == "holes":
            d["count"], d["d"], d["depth"] = int(_num(d, "count", 1)), _num(d, "d", 8.0), _num(d, "depth", 15.0)
            # Holes of different sizes: a list of diameters, one a hole, in the order they stand. It sets the count.
            ds = d.get("ds")
            if isinstance(ds, str):
                from . import sizes as _sz
                ds = [mm for mm, _ in _sz.parse_list(ds, f"section {i + 1} hole sizes")]
            if ds:
                try:
                    ds = [float(v) for v in ds]
                except (TypeError, ValueError):
                    raise ValueError(f"section {i + 1} ({d['name']}): hole sizes are numbers with commas between") from None
                if len(ds) > 60 or not all(2 <= v <= 60 for v in ds):
                    raise ValueError(f"section {i + 1} ({d['name']}): up to 60 holes, each 2 to 60 mm across")
                d["ds"], d["count"], d["d"] = ds, len(ds), max(ds)
            else:
                d["ds"] = None
            d["slot_l"], d["slot_w"] = _num(d, "slot_l"), _num(d, "slot_w")
            if not (0 <= d["count"] <= 60 and 2 <= d["d"] <= 60 and 3 <= d["depth"] <= 100):
                raise ValueError(f"section {i + 1} ({d['name']}): up to 60 holes, 2 to 60 mm across, 3 to 100 mm deep")
            if d["slot_l"] > 0 and d["slot_w"] <= 0:
                raise ValueError(f"section {i + 1} ({d['name']}): the slot is {d['slot_l']:g} mm long but has no width. Give it a width, or set its length to 0 for no slot")
            if d["slot_w"] > 0 and d["slot_l"] <= 0:
                raise ValueError(f"section {i + 1} ({d['name']}): the slot is {d['slot_w']:g} mm wide but has no length. Give it a length, or set its width to 0 for no slot")
            if d["slot_l"] > 400 or d["slot_w"] > 100:
                raise ValueError(f"section {i + 1} ({d['name']}): a slot up to 400 mm long and 100 mm wide (yours is {d['slot_l']:g} x {d['slot_w']:g} mm)")
            if d["slot_l"] and d["slot_w"] < 1:
                raise ValueError(f"section {i + 1} ({d['name']}): the slot is only {d['slot_w']:g} mm wide ({d['slot_w'] / 25.4:.3f} in); 1 mm at least")
            if d["slot_l"] and d["slot_w"] > d["slot_l"]:
                d["slot_l"], d["slot_w"] = d["slot_w"], d["slot_l"]       # the longer of the two is its length
            d["slot_d"] = _num(d, "slot_d") or d["slot_w"]
            if not d["count"] and not d["slot_l"]:
                raise ValueError(f"section {i + 1} ({d['name']}): some holes, a slot, or both")
        else:
            d["count"], d["x"], d["y"] = int(_num(d, "count", 1)), _num(d, "x", 25.4), _num(d, "y", 25.4)
            if not (1 <= d["count"] <= 80 and 8 <= d["x"] <= 300 and 8 <= d["y"] <= 300):
                raise ValueError(f"section {i + 1} ({d['name']}): 1 to 80 compartments, each 8 to 300 mm")
        d["len"], d["dep"] = _num(d, "len"), _num(d, "dep")
        if not (0 <= d["len"] <= 400 and 0 <= d["dep"] <= 400):
            raise ValueError(f"section {i + 1} ({d['name']}): a section up to 400 mm long and deep")
        secs.append(d)

    def lay(turns: tuple, wider: float = 0.0) -> dict:
        t = iter(turns)
        need = []
        for d in secs:                                # the width each needs at least
            if d["kind"] == "space":
                d["_turned"] = next(t)
                need.append((d["x"] if d["_turned"] else d["y"]) + d["fit"])
            elif d["kind"] == "holes":
                need.append(max(d["d"] + 6.0 if d["count"] else 0.0, d["slot_l"] + 6.0 if d["slot_l"] else 0.0))
            else:
                need.append(min(d["x"], d["y"]))
        W = max(max(need), wider)
        out, x0 = [], 0.0
        for d in secs:
            e = {k: v for k, v in d.items() if not k.startswith("_")}
            if d["kind"] == "space":
                e["turned"] = d["_turned"]
                e["len"] = (d["y"] if d["_turned"] else d["x"]) + d["fit"]
                e["across"] = (d["x"] if d["_turned"] else d["y"]) + d["fit"]
            elif d["kind"] == "holes":
                pitch = d["d"] + max(4.0, d["d"] * 0.35)
                per_row = max(1, int((W - 6.0 + pitch - d["d"]) // pitch)) if d["count"] else 0
                rows = -(-d["count"] // per_row) if d["count"] else 0
                e.update(pitch=pitch, per_row=min(per_row, d["count"]), rows=rows)
                e["len"] = (rows * pitch + 2.0 if rows else 0.0) + (d["slot_w"] + 4.0 if d["slot_l"] else 0.0) + (2.0 if not rows else 0.0)
            else:
                # Compartments run across the width in rows; the cell's two sizes go whichever way packs more in.
                best = None
                for cx, cy in {(d["x"], d["y"]), (d["y"], d["x"])}:
                    per_row = max(1, int((W + wall) // (cy + wall)))
                    per_row = min(per_row, d["count"])
                    rows = -(-d["count"] // per_row)
                    per_row = -(-d["count"] // rows)          # even rows: 15 in three rows is 5, 5, 5, not 7, 7, 1
                    length = rows * cx + (rows - 1) * wall
                    if best is None or length < best[0]:
                        best = (length, cx, per_row, rows)
                e["len"], e["cell_len"], e["per_row"], e["rows"] = best
            e["x0"] = x0
            x0 += e["len"] + wall
            out.append(e)
        return {"L": x0 - wall, "W": W, "sections": out}

    if banded:
        return _plan_bands(secs, wall)
    autos = [d for d in secs if d["kind"] == "space"]
    choices = [((False, True) if d.get("turn") in (None, "", "auto") else ((True,) if d.get("turn") == "turned" else (False,))) for d in autos]
    plans = [lay(t) for t in itertools.product(*choices)]
    if not autos:                                 # nothing fixes the width: try wider cases and keep the most nearly square
        narrow = plans[0]["W"]
        plans += [lay((), narrow + k * 2.0) for k in range(1, 140) if narrow + k * 2.0 <= 300]
    for q in plans:
        for e in q["sections"]:                   # each takes the full width
            e["y0"], e["dep"] = 0.0, q["W"]
        q["wall"] = wall
    # Or in two rows: the list split at each point, the second row in front of the first.
    if len(secs) > 1:
        for k in range(1, len(secs)):
            for turns in itertools.product(*choices):
                t = iter(turns)
                copy = [dict(d, turn=("turned" if next(t) else "as typed")) if d["kind"] == "space" else dict(d) for d in secs]
                try:
                    plans.append(_plan_bands(copy[:k] + [{"kind": "break"}] + copy[k:], wall))
                except ValueError:
                    continue
    # The best is the most compact; a case longer than it is deep has its hinges on a long side, and
    # one that comes out deeper than long is turned a quarter turn so that it does too.
    for q in plans:
        q["swap"] = q["W"] > q["L"] + 0.01
    plan = min(plans, key=lambda q: (max(q["L"], q["W"]), q["L"] * q["W"], q.get("bands", 1), q["swap"]))
    plan["H"] = max([d["z"] + 1.5 for d in secs if d["kind"] == "space"] + [0.0])
    return plan


def _plan_bands(secs: list, wall: float) -> dict:
    """Sections in rows: the first row along the back by the hinges, each "break" starting a new row
    nearer the latches. A row's sections sit side by side along the length. Whatever has a set size
    keeps it; compartments take as many columns as the case's length allows, in even rows; an open
    space takes what is left of its row."""
    bands, cur = [], []
    for d in secs:
        if d["kind"] == "break":
            if cur:
                bands.append(cur)
            cur = []
        else:
            cur.append(d)
    if cur:
        bands.append(cur)
    if not bands:
        raise ValueError("sections: nothing but row breaks")

    def rigid(d) -> float | None:
        if d["kind"] == "space":
            return (d["y"] if d.get("turn") == "turned" else d["x"]) + d["fit"]
        return d["len"] if d.get("len") else None

    def least(d) -> float:
        if d["kind"] == "cells":
            return min(d["x"], d["y"]) if not d.get("len") else d["len"]
        if d["kind"] == "holes":
            return (d["d"] + 6.0 if d["count"] else 0.0) + (d["slot_w"] + 4.0 if d["slot_l"] else 0.0)
        return 0.0                                # open space

    L = max(sum(rigid(d) if rigid(d) is not None else least(d) for d in b) + (len(b) - 1) * wall for b in bands)
    out, y0 = [], 0.0
    for bi, b in enumerate(bands):
        fixed = sum(rigid(d) for d in b if rigid(d) is not None)
        free = L - fixed - (len(b) - 1) * wall
        flex = [d for d in b if rigid(d) is None]
        opens = [d for d in flex if d["kind"] == "open"]
        lens = {}
        # Holes first take what they need, then compartments their columns, then open space the rest.
        deps = [((d["x"] if d.get("turn") == "turned" else d["y"]) + d["fit"]) for d in b if d["kind"] == "space"] + [d["dep"] for d in b if d.get("dep")]
        for d in flex:
            if d["kind"] == "holes":
                lens[id(d)] = least(d)
                free -= lens[id(d)]
        cells = [d for d in flex if d["kind"] == "cells"]
        share = max(0.0, free) / max(1, len(cells)) if cells else 0.0
        for d in cells:
            cx, cy = d["x"], d["y"]
            most = max(1, int((share + wall) // (cx + wall)))
            across = -(-d["count"] // min(most, d["count"]))          # rows across the depth
            if deps:                                                 # the row's depth is already set: use it
                fit_across = max(1, int((max(deps) + wall) // (cy + wall)))
                across = max(across, min(fit_across, -(-d["count"] // 1))) if across > fit_across else across
            cols = -(-d["count"] // across)
            d["_cols"], d["_across"] = cols, across
            lens[id(d)] = cols * cx + (cols - 1) * wall
            free -= lens[id(d)]
            deps.append(across * cy + (across - 1) * wall)
        if free < -0.01:
            raise ValueError(f"sections: row {bi + 1} needs {-free:.1f} mm more length than the case has")
        if opens:
            for d in opens:
                lens[id(d)] = free / len(opens)
            free = 0.0
        elif free > 0.01 and cells:                                  # no open space to take the slack: the compartments stretch
            d = cells[-1]
            lens[id(d)] += free
            free = 0.0
        D = max(deps + [d["d"] + 6.0 for d in b if d["kind"] == "holes" and d["count"]] + [d["slot_l"] + 6.0 for d in b if d["kind"] == "holes" and d["slot_l"]] + [10.0])
        x0 = 0.0
        for d in b:
            e = {k: v for k, v in d.items() if not k.startswith("_")}
            e["len"] = rigid(d) if rigid(d) is not None else lens[id(d)]
            e["x0"], e["y0"], e["dep"], e["band"] = x0, y0, D, bi
            if d["kind"] == "space":
                e["turned"] = d.get("turn") == "turned"
                e["across"] = (d["x"] if e["turned"] else d["y"]) + d["fit"]
            elif d["kind"] == "holes":
                pitch = d["d"] + max(4.0, d["d"] * 0.35)
                per_row = max(1, int((D - 6.0 + pitch - d["d"]) // pitch)) if d["count"] else 0
                # Tighter in a row if that is what it takes to fit the section's length.
                room_rows = max(1, int((e["len"] - (d["slot_w"] + 4.0 if d["slot_l"] else 0.0) - 2.0) // pitch)) if d["count"] else 0
                if d["count"] and -(-d["count"] // per_row) > room_rows:
                    per_row = -(-d["count"] // room_rows)
                    if (D - 4.0) / per_row < d["d"] + 1.2:
                        raise ValueError(f"{d['name']}: {d['count']} holes of {d['d']:g} mm don't fit a section {e['len']:g} x {D:g} mm")
                rows = -(-d["count"] // per_row) if d["count"] else 0
                e.update(pitch=pitch, per_row=min(per_row, d["count"]), rows=rows)
            elif d["kind"] == "cells":
                e["rows"], e["per_row"] = d["_cols"], d["_across"]
                e["cell_len"] = (e["len"] - (d["_cols"] - 1) * wall) / d["_cols"]
            x0 += e["len"] + wall
            out.append(e)
        if free > 0.01:
            out.append({"kind": "open", "name": "open space", "len": free - wall if free > wall else free, "x0": x0, "y0": y0, "dep": D, "band": bi, "spare": True})
        y0 += D + wall
    return {"L": L, "W": y0 - wall, "sections": out, "wall": wall, "bands": len(bands),
            "H": max([d["z"] + 1.5 for d in secs if d["kind"] == "space"] + [0.0])}


def grid_size(cols: int, rows: int) -> tuple[float, float]:
    """The inside length and width that hold a Gridfinity grid, with a little room round it."""
    return cols * GRID + 2 * GRID_EDGE, rows * GRID + 2 * GRID_EDGE


def build(c: Case) -> dict:
    gc, gr = int(c.grid_cols), int(c.grid_rows)
    asked = tuple(float(v) for v in c.size[:2])
    H0 = float(c.size[2])
    if gc and gr:                                 # the grid decides the inside length and width
        from dataclasses import replace
        c = replace(c, size=(*grid_size(gc, gr), c.size[2]))
    plan = None
    if c.sections:                                # and so do sections, and the height if something is tall
        from dataclasses import replace
        if not 0.8 <= float(c.section_wall) <= 6:
            raise ValueError("section walls: 0.8 to 6 mm thick")
        plan = plan_sections(c.sections, float(c.section_wall))
        tall = max(float(c.size[2]), float(math.ceil(plan["H"])))
        along, deep_ = (plan["W"], plan["L"]) if plan.get("swap") else (plan["L"], plan["W"])
        c = replace(c, size=(max(45.0, round(along, 2)), max(30.0, round(deep_, 2)), tall))     # no smaller than the smallest case
    c.check()
    L, W, H = (float(v) for v in c.size)
    w, fl = float(c.wall), float(c.floor)
    oL, oW = L + 2 * w, W + 2 * w
    r = max(0.6, min(float(c.corner_radius), min(oL, oW) / 2 - 1))
    ch = max(0.4, min(2.0, w - 0.8, fl - 0.4))   # the chamfer on the bottom and top edges
    shoulder = max(1.05, 0.4 * w)                 # the step the lid's wall sits on
    lip_t = w - shoulder
    Hs = fl + H - c.lid_depth                     # the shoulder's height: the parting line
    T = fl + c.lid_depth                          # the lid, top to rim
    top = Hs + T
    yw = oW / 2
    notes, checks = [], []

    def rect(dl: float, dr: float):
        return RectangleRounded(L + 2 * dl, W + 2 * dl, max(0.5, r - dr))

    # ----- The tray -----
    tray = extrude(rect(w, 0), amount=Hs)
    tray = chamfer(tray.edges().group_by(Axis.Z)[0], ch)
    lip = Pos(0, 0, Hs - 0.01) * extrude(rect(lip_t, shoulder), amount=LIP_H + 0.01)
    lip = chamfer(lip.edges().group_by(Axis.Z)[-1], min(0.6, lip_t * 0.4))
    tray += lip
    tray -= Pos(0, 0, fl) * extrude(rect(0, w), amount=H + 10)

    # ----- The lid, where it sits when shut -----
    lid = Pos(0, 0, Hs) * extrude(rect(w, 0), amount=T)
    lid = chamfer(lid.edges().group_by(Axis.Z)[-1], ch)
    lid -= Pos(0, 0, Hs - 0.01) * extrude(rect(0, w), amount=c.lid_depth + 0.01)
    lid -= Pos(0, 0, Hs - 0.01) * extrude(rect(lip_t + LIP_GAP, shoulder - LIP_GAP), amount=LIP_H + 0.35)

    # ----- Dividers, and ribs under the lid over them -----
    nx, ny = int(c.dividers_x), int(c.dividers_y)
    div_top = Hs + LIP_H - 0.5
    rib_h = c.lid_depth - LIP_H - 0.3
    for k in range(1, nx + 1):
        x = -L / 2 + k * L / (nx + 1)
        tray += Pos(x, 0, fl - 0.01) * Box(RIB, W + 0.02, div_top - fl, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if c.lid_ribs and rib_h >= 1:
            lid += Pos(x, 0, top - fl - rib_h) * Box(RIB, W + 0.02, rib_h + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for k in range(1, ny + 1):
        y = -W / 2 + k * W / (ny + 1)
        tray += Pos(0, y, fl - 0.01) * Box(L + 0.02, RIB, div_top - fl, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if c.lid_ribs and rib_h >= 1:
            lid += Pos(0, y, top - fl - rib_h) * Box(L + 0.02, RIB, rib_h + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    if nx or ny:
        notes.append(f"{(nx + 1) * (ny + 1)} pockets, each about {(L - nx * RIB) / (nx + 1):.1f} x {(W - ny * RIB) / (ny + 1):.1f} mm; "
                     f"dividers {RIB:g} mm" + (f", ribs under the lid {rib_h:.1f} mm deep over them" if c.lid_ribs and rib_h >= 1 else ""))

    margin = max(6.0, r)
    # ----- Hinges along the back -----
    h_unit = HINGE_GAP + 2 * CHEEK_W
    room_h = int((oL - 2 * margin + 4) // (h_unit + 4))
    n_h = int(c.hinges) or (2 if oL < 120 else 3 if oL < 280 else 4)
    if n_h > room_h:
        if c.hinges:
            raise ValueError(f"{n_h} hinges don't fit along {oL:g} mm: {room_h} at most")
        n_h = room_h
    if n_h < 1:
        raise ValueError("the case is too short for a hinge")
    ya = yw + HINGE_E            # the hinge axis
    lug_w = HINGE_GAP - 2 * SIDE
    # The cheeks spring apart to let the balls in: short cheeks are stiff, so they get a shallower ball
    # (about 2% strain at the cheek's root).
    grab = max(0.45, min(HINGE_BALL[1] - SIDE, Hs * Hs / 480.0))
    hinge_ball = (HINGE_BALL[0], round(grab + SIDE, 2))
    for xc in _spread(n_h, oL, h_unit, margin):
        for s in (-1, 1):
            x_in = xc + s * HINGE_GAP / 2          # the cheek's inner face
            x0, x1 = sorted((x_in, x_in + s * CHEEK_W))
            cheek = _block(1, yw, HINGE_E + HINGE_R, 0.0, Hs, ch, x0, x1, "bottom")
            cheek += Pos((x0 + x1) / 2, ya, Hs) * Cylinder(HINGE_R, CHEEK_W, rotation=(0, 90, 0))
            cheek -= _socket(x_in, s, ya, Hs, hinge_ball)
            tray += cheek
        lug = _block(1, yw, HINGE_E + HINGE_R, Hs, top, ch, xc - lug_w / 2, xc + lug_w / 2, "top")
        lug += Pos(xc, ya, Hs) * Cylinder(HINGE_R, lug_w, rotation=(0, 90, 0))
        for s in (-1, 1):
            lug += _cap(xc + s * lug_w / 2, s, ya, Hs, hinge_ball) & (Pos(xc, ya, Hs) * Cylinder(HINGE_R, lug_w + 10, rotation=(0, 90, 0)))
        lid += lug
    notes.append(f"{n_h} snap hinges along the back: a lug on the lid with a ball each side ({grab:.2g} mm into "
                 f"its socket) between two cheeks on the tray; the lid opens right over")

    # ----- Latches along the front -----
    l_unit = TAB_W + 2 * SIDE + 2 * CHEEK_W
    room_l = int((oL - 2 * margin + 4) // (l_unit + 4))
    n_l = int(c.latches) or (1 if oL < 100 else 2 if oL < 280 else 3)
    if n_l > room_l:
        if c.latches:
            raise ValueError(f"{n_l} latches don't fit along {oL:g} mm: {room_l} at most")
        n_l = room_l
    if n_l < 1:
        raise ValueError(f"the case is too short for a latch: at least {l_unit + 2 * margin - 2 * w:.0f} mm inside")
    if T < 2 * TAB_E + 0.4:
        raise ValueError(f"the lid is too shallow for the latch's pivot: a lid depth of at least {2 * TAB_E + 0.4 - fl:.1f} mm")
    zp = top - TAB_E                         # the tab's pivot
    catch = max(CATCH_MIN, T - TAB_E + 4.5)  # pivot to catch: the catch must be well under the parting line
    need = catch + TAIL - (T - TAB_E) + 1.5  # the tray's height the tab hangs down over
    if Hs < need:
        raise ValueError(f"the tray is too shallow for the latch tab: it needs {need:.1f} mm from the floor's underside to "
                         f"the parting line and has {Hs:.1f} mm. Make the inside {need - Hs:.1f} mm taller")
    yp = -(yw + TAB_E)
    gap = TAB_W + 2 * SIDE
    one = tab(catch)
    mounted = []
    for xc in _spread(n_l, oL, l_unit, margin):
        for s in (-1, 1):
            x_in = xc + s * gap / 2
            x0, x1 = sorted((x_in, x_in + s * CHEEK_W))
            cheek = _block(-1, yw, POST_D, Hs, top, ch, x0, x1, "top")
            cheek -= _socket(x_in, s, yp, zp, PIVOT_BALL)
            lid += cheek
            post = _block(-1, yw, POST_D, 0.0, Hs, ch, x0, x1, "bottom")
            post -= _socket(x_in, s, yp, zp - catch - PRELOAD, CATCH_BALL)
            tray += post
        mounted.append(Pos(xc, -(yw + TAB_E + TAB_T / 2), zp) * (Rot(-90, 0, 0) * one))
    notes.append(f"{n_l} latch tab{'s' if n_l > 1 else ''} {TAB_W:g} x {catch + TAIL + TAB_T / 2:g} x {TAB_T:g} mm: each snaps "
                 f"between two cheeks on the lid and clicks onto two posts on the tray ({CATCH_BALL[1] - SIDE:g} mm catch on "
                 f"sprung arms, set {PRELOAD:g} mm tight so it pulls the lid down)")

    # ----- Lift-out bins on a grid -----
    inserts, insert_placed = [], []
    ic, ir = int(c.insert_cols), int(c.insert_rows)
    if ic and ir:
        layers = int(c.insert_layers)
        px, py = (L - 2 * INSERT_EDGE) / ic, (W - 2 * INSERT_EDGE) / ir
        bh = round((H - 0.8) / layers, 2)
        spots = lay_out(ic, ir, parse_bins(c.insert_bins), bool(c.insert_fill))
        shapes: dict = {}
        count: dict = {}
        for a, b, c0, r0 in spots:
            key = (a, b)
            if key not in shapes:
                shapes[key] = insert_bin(a * px - INSERT_GAP, b * py - INSERT_GAP, bh, float(c.insert_wall), bool(c.insert_scoop), bool(c.insert_label))
            count[key] = count.get(key, 0) + layers
            x = -L / 2 + INSERT_EDGE + (c0 + a / 2) * px
            y = -W / 2 + INSERT_EDGE + (r0 + b / 2) * py
            for k in range(layers):
                insert_placed.append(Pos(x, y, fl + 0.1 + k * bh) * shapes[key])
        for (a, b), sh in sorted(shapes.items()):
            inserts.append({"name": f"bin_{a}x{b}", "shape": sh, "count": count[(a, b)],
                            "size": [round(a * px - INSERT_GAP, 2), round(b * py - INSERT_GAP, 2), bh]})
        empty = ic * ir - sum(a * b for a, b, _, _ in spots)
        notes.append(f"lift-out bins on a {ic} x {ir} grid of {px:.1f} x {py:.1f} mm cells"
                     + (f", in {layers} layers" if layers > 1 else "") + f", each {bh:g} mm tall (the lid holds them down): "
                     + ", ".join(f"{i['count']} x {i['name'][4:]} ({i['size'][0]:g} x {i['size'][1]:g} mm)" for i in inserts)
                     + f"; walls {float(c.insert_wall):g} mm"
                     + (", rounded fronts for scooping" if c.insert_scoop else "") + (", label tabs" if c.insert_label else ""))
        if empty:
            notes.append(f"{empty} cell{'s' if empty > 1 else ''} of the grid left empty")
        if bh < 8:
            checks.append(f"the bins are only {bh:g} mm tall: fewer layers, or a taller case")

    # ----- Or sections: different things side by side (and in rows), each walled off -----
    if plan:
        wall_h = div_top - fl
        tw = plan["wall"]
        said = []
        CM = (Align.CENTER, Align.CENTER, Align.MIN)

        swap = bool(plan.get("swap"))
        front = bool(c.sections_front)
        PL, PD = (W, L) if swap else (L, W)        # the room the plan has: along its rows, and across them

        def pt(px, py):
            """Where a point of the plan is in the tray. The plan's x runs along a row from the left end,
            its y from the first row back; turned a quarter turn, rows run front to back instead."""
            X, Y = (-L / 2 + py, W / 2 - px) if swap else (-L / 2 + px, W / 2 - py)
            return (X, -Y) if front else (X, Y)

        def slab(x_lo, x_hi, y_lo, y_hi, hgt=None):
            """A wall or block over this patch of the plan."""
            X, Y = pt((x_lo + x_hi) / 2, (y_lo + y_hi) / 2)
            dx, dy = x_hi - x_lo + 0.02, y_hi - y_lo + 0.02
            return Pos(X, Y, fl - 0.01) * Box(dy if swap else dx, dx if swap else dy, hgt or wall_h, align=CM)

        dims = lambda a, b: f"{b:g} x {a:g}" if swap else f"{a:g} x {b:g}"   # noqa: E731  along the case's length first
        seen_band, last_end = set(), {}
        for e in plan["sections"]:
            xa, xb, ya, yb = e["x0"], e["x0"] + e["len"], e["y0"], e["y0"] + e["dep"]
            band = e.get("band", 0)
            if band not in seen_band:
                seen_band.add(band)
                if ya > 0.01:                     # the wall between this row and the one behind it
                    tray += slab(0, PL, ya - tw, ya)
            elif xa > 0.01:                       # the wall between this section and the last in its row
                tray += slab(xa - tw, xa, ya, min(yb, PD))
            yb = min(yb, PD)
            xm = (xa + xb) / 2
            if e["kind"] == "space":
                if e["dep"] - e["across"] > 3:    # shallower than its row: a wall in front keeps the thing from sliding
                    tray += slab(xa, xb, ya + e["across"], ya + e["across"] + tw)
                a, b = (e["y"], e["x"]) if e["turned"] else (e["x"], e["y"])
                said.append(f"{e['name']}: a space {dims(round(e['len'], 2), round(e['across'], 2))} mm" + (f" for a thing {a:g} x {b:g} mm" if e["fit"] else "")
                            + (f", {e['z']:g} mm tall" if e["z"] else "") + "")
            elif e["kind"] == "open":
                if e["len"] > 0.5:
                    said.append(f"{e['name']}: {dims(round(e['len'], 1), round(e['dep'], 1))} mm left open" + (" at the end of its row" if e.get("spare") else ""))
            elif e["kind"] == "holes":
                bh = wall_h                       # the block fills its section to the top of the tray; the holes go down from its top
                block = slab(xa, xb, ya, yb, bh)
                top_z = fl - 0.01 + bh
                yc = (ya + yb) / 2
                deep = min(e["depth"], bh - 1.0)
                used = (e["rows"] * e["pitch"] if e["count"] else 0.0) + (e["slot_w"] + (3.0 if e["count"] else 0.0) if e["slot_l"] else 0.0)
                x_at = xa + max(1.0, (e["len"] - used) / 2)                   # the holes and the slot sit in the middle of the block
                if e["count"]:
                    left, hole_no = e["count"], 0
                    for r_ in range(e["rows"]):
                        n_here = min(e["per_row"], left)
                        left -= n_here
                        step = min(e["pitch"] * 1.6, (e["dep"] - 4.0) / max(1, n_here))
                        for k in range(n_here):
                            X, Y = pt(x_at + e["pitch"] / 2 + r_ * e["pitch"], yc + ((k - (n_here - 1) / 2) * step if n_here > 1 else 0.0))
                            dia = e["ds"][hole_no] if e.get("ds") else e["d"]
                            hole_no += 1
                            block -= Pos(X, Y, top_z - deep) * Cylinder(dia / 2, deep + 1, align=CM)
                    x_at += e["rows"] * e["pitch"] + 3.0
                slot_deep = 0.0
                if e["slot_l"]:
                    slot_deep = min(e["slot_d"], bh - 1.0)
                    X, Y = pt(x_at + e["slot_w"] / 2 - (1.5 if e["count"] else 0.0), yc)
                    sw_, sl_ = e["slot_w"], min(e["slot_l"], e["dep"] - 3.0)
                    block -= Pos(X, Y, top_z - slot_deep) * Box(sl_ if swap else sw_, sw_ if swap else sl_, slot_deep + 1, align=CM)
                tray += block
                said.append(f"{e['name']}: a solid block {dims(round(e['len'], 2), round(e['dep'], 2))} mm, level with the top of the tray ({bh:g} mm)"
                            + (f", with {e['count']} holes " + ("of " + ", ".join(f"Ø{v:g} mm" for v in e["ds"]) if e.get("ds") and len(set(e["ds"])) > 1 else f"Ø{e['d']:g} mm") + f" going {deep:g} mm down from its top" + (f" in {e['rows']} rows" if e["rows"] > 1 else " in a row") if e["count"] else "")
                            + (f"{' and' if e['count'] else ', with'} a slot {min(e['slot_l'], e['dep'] - 3.0):g} x {e['slot_w']:g} mm cut {slot_deep:g} mm down into its top, for something lying down" if e["slot_l"] else ""))
                if e["count"] and deep < e["depth"] - 0.01:
                    checks.append(f"{e['name']}: the holes are {deep:g} mm deep, not {e['depth']:g}: the tray is only {wall_h:g} mm deep. A taller case gives deeper holes")
            else:
                # Columns along the length, each split across the depth.
                left, cols = e["count"], e["rows"]
                sizes_ = []
                for r_ in range(cols):
                    n_here = min(e["per_row"], left)
                    left -= n_here
                    xr = xa + r_ * (e["cell_len"] + tw)
                    if r_:
                        tray += slab(xr - tw, xr, ya, yb)
                    cw = (e["dep"] - (n_here - 1) * tw) / n_here
                    for k in range(1, n_here):
                        yk = ya + k * (cw + tw)
                        tray += slab(xr, xr + e["cell_len"], yk - tw, yk)
                    sizes_.append((n_here, cw))
                same = len({round(cw, 1) for _, cw in sizes_}) == 1
                a_, b_ = (e["per_row"], cols) if swap else (cols, e["per_row"])
                said.append(f"{e['name']}: {e['count']} compartments, {a_} along the length by {b_} across, each {dims(round(e['cell_len'], 1), round(sizes_[0][1], 1))} mm"
                            + ("" if same else f" (the last column has {sizes_[-1][0]}, each {sizes_[-1][1]:.1f} mm)") + f" and {wall_h:g} mm deep")
            last_end[band] = xb
        spare = PL - plan["L"]
        if spare > 3:
            tray += slab(plan["L"], plan["L"] + tw, 0, PD)
            said.append(f"and {spare - tw:g} mm of open space at the end, since a case is at least 45 mm long")
        first, last = ("front by the latches", "hinges") if front else ("back by the hinges", "latches")
        if swap:
            rows_say = (f" in {plan['bands']} rows running front to back" if plan.get("bands", 1) > 1 else " one behind the other, front to back") \
                + ", the first at the " + ("front" if front else "back") + ": laid out that way so the hinges are on a long side"
        else:
            rows_say = f" in {plan['bands']} rows, the first along the {first} and the last by the {last}" if plan.get("bands", 1) > 1 else " side by side along the length"
        n_sec = len([e for e in plan["sections"] if e["kind"] != "open" or e["len"] > 0.5])
        notes.append(f"{n_sec} section{'s' if n_sec != 1 else ''}{rows_say}, with {tw:g} mm walls between; "
                     f"they set the inside to {L:g} x {W:g} mm:")
        notes.extend("  " + t for t in said)
        if plan["H"] > H0 + 0.01:
            notes.append(f"the inside height went up to {H:g} mm so the tallest thing fits with the lid shut")
        if max(L, W) + 2 * w + 20 > 256:
            checks.append(f"the tray is about {L + 2 * w:.0f} x {W + 2 * w + 16:.0f} mm with its hinges and latches: check it against your printer's bed "
                          "(256 mm on many; a 300 mm class bed takes more)")

    # ----- Or Gridfinity: a baseplate in the floor and standard bins -----
    if gc and gr:
        from . import gridfinity as gf
        plate = Pos(0, 0, fl - 0.01) * gf.baseplate(gc, gr)
        tray += plate
        units = int(c.grid_height) or int((H - GRID_ROOM) // 7)
        spots = lay_out(gc, gr, parse_bins(c.grid_bins), bool(c.grid_fill))
        shapes, count = {}, {}
        for a, b, c0, r0 in spots:
            key = (a, b)
            if key not in shapes:
                shapes[key] = gf.bin_(a, b, units, wall=float(c.insert_wall), lip=False, label=bool(c.insert_label))
            count[key] = count.get(key, 0) + 1
            insert_placed.append(Pos((c0 + a / 2 - gc / 2) * GRID, (r0 + b / 2 - gr / 2) * GRID, fl) * shapes[key])
        for (a, b), sh in sorted(shapes.items()):
            inserts.append({"name": f"gridfinity_bin_{a}x{b}x{units}", "shape": sh, "count": count[(a, b)],
                            "size": [a * GRID - 0.5, b * GRID - 0.5, units * 7.0]})
        empty = gc * gr - sum(a * b for a, b, _, _ in spots)
        notes.append(f"Gridfinity inside: a {gc} x {gr} baseplate is part of the tray's floor (42 mm units), so the inside is {L:g} x {W:g} mm"
                     + (f" (you asked for {asked[0]:g} x {asked[1]:g}; the grid sets it)" if abs(asked[0] - L) > 0.5 or abs(asked[1] - W) > 0.5 else "")
                     + f". Bins {units} units ({units * 7:g} mm) tall, without the stacking lip so the lid shuts on them: "
                     + ", ".join(f"{i['count']} x {i['name'][15:].rsplit('x', 1)[0]}" for i in inserts)
                     + ". Any standard Gridfinity bin that height or shorter fits too")
        if empty:
            notes.append(f"{empty} unit{'s' if empty > 1 else ''} of the grid left empty for bins you already have")
        gap = H - units * 7
        if gap > 4:
            checks.append(f"there are {gap:g} mm between the bins and the lid: small parts can jump bins if the case is tipped. A case {gap - GRID_ROOM:g} mm shorter, or taller bins")

    # ----- Or one lift-out tray with a pocket for each thing -----
    if str(c.insert_pockets or "").strip():
        pk = parse_pockets(c.insert_pockets)
        room = H - 0.8
        depth = float(c.pocket_depth) or min(15.0, room - 1.2)
        if not 2 <= depth <= room - 1.0:
            raise ValueError(f"pocket depth: 2 to {room - 1.0:.1f} mm in this case (it is {H:g} mm inside, and the tray needs a 1 mm floor)")
        th = round(min(room, depth + 1.2), 2)
        tray_, count_, notches = pocket_tray(L - 2 * INSERT_EDGE, W - 2 * INSERT_EDGE, th, pk, depth)
        inserts.append({"name": "pocket_tray", "shape": tray_, "count": 1, "size": [round(L - 2 * INSERT_EDGE, 2), round(W - 2 * INSERT_EDGE, 2), th]})
        insert_placed.append(Pos(0, 0, fl + 0.1) * tray_)
        notes.append(f"a lift-out tray {L - 2 * INSERT_EDGE:.1f} x {W - 2 * INSERT_EDGE:.1f} x {th:g} mm with {count_} pockets {depth:g} mm deep, each 0.4 mm "
                     "bigger than its size: " + ", ".join(f"{n} x {s} {a:g}" + ("" if s == "round" else f" x {b:g}") for s, a, b, n in pk)
                     + (f"; {notches} of them have a finger notch" if notches else ""))
        if room - th > 3:
            notes.append(f"things may stand up to {room - th + depth:.1f} mm tall before they touch the lid; the tray leaves {room - th:.1f} mm above it")

    out_h = top
    notes.insert(0, f"hinged case: inside {L:g} x {W:g} x {H:g} mm ({H - c.lid_depth:g} in the tray to the parting line, "
                    f"{c.lid_depth:g} in the lid), outside {oL:g} x {oW + HINGE_E + HINGE_R + POST_D:.1f} x {out_h:g} mm with "
                    f"the hinges and latches; walls {w:g} mm, a {LIP_H:g} mm lip inside the lid's rim")
    notes.append("print the tray as it stands, the lid top down, the tabs flat on their outside face: no supports. "
                 "PETG is kinder to the snap joints than PLA")
    notes.append("to put it together: press each tab's rounded end between its two cheeks on the lid until both balls click "
                 "in, then press the lid's lugs down between the hinge cheeks, one hinge at a time")
    if Hs < 20:
        checks.append("a shallow tray makes short, stiff hinge cheeks: the lid will be hard to snap on. Print in PETG, or "
                      "make the tray deeper")
    checks.append("the snap joints are modelled on a printed case that works, but this one hasn't been printed: print one "
                  "tab and try it on the lid before printing a set")
    return {"base": tray.clean(), "lid": lid.clean(), "tab": one, "tabs": mounted, "n_tabs": n_l, "n_hinges": n_h, "notes": notes,
            "inserts": inserts, "insert_placed": insert_placed,
            "checks": checks, "inner": [L, W, H], "outer": [round(oL, 2), round(oW + HINGE_E + HINGE_R + POST_D, 2), round(out_h, 2)],
            "parting": Hs, "top": top}


def write(c: Case, folder) -> dict:
    from build123d import export_step, export_stl
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    m = build(c)
    export_step(m["base"], str(folder / "case_tray.step"))
    export_step(m["lid"], str(folder / "case_lid.step"))
    export_step(m["tab"], str(folder / "case_latch_tab.step"))
    export_stl(m["base"], str(folder / "case_tray.stl"))
    export_stl(Pos(0, 0, m["top"]) * (Rot(180, 0, 0) * m["lid"]), str(folder / "case_lid.stl"))  # top down, on the bed
    export_stl(m["tab"], str(folder / "case_latch_tab.stl"))
    for i in m["inserts"]:
        export_stl(i["shape"], str(folder / f"case_{i['name']}.stl"))
        export_step(i["shape"], str(folder / f"case_{i['name']}.step"))
    from build123d import Compound
    export_step(Compound(children=[m["base"], m["lid"], *m["tabs"], *m["insert_placed"]]), str(folder / "case_assembly.step"))
    text = "# Hinged case\n\n" + "\n".join(f"- {n}" for n in m["notes"]) + \
           f"\n\nPrint {m['n_tabs']} of case_latch_tab.stl." + \
           "".join(f"\nPrint {i['count']} of case_{i['name']}.stl." for i in m["inserts"]) + "\n\n## Check\n\n" + "\n".join(f"- {n}" for n in m["checks"]) + "\n"
    (folder / "notes.md").write_text(text, encoding="utf-8")
    return m
