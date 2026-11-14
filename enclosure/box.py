"""Quick enclosures: a box from a size and a few choices, no board needed.

`enclosure box` makes a base and a lid as STEP files (they open in Onshape and SolidWorks as
solid bodies you can edit with direct-edit tools) plus STL for printing, and saves the settings
as `box.json`, so changing a number and running again rebuilds it. `--format onshape` writes an
Onshape custom feature instead (or as well), which rebuilds inside Onshape from its own dialog.

Frame: Z up (the lid comes off upward), millimetres, the base's outside centred on X and Y with
its bottom at z = 0. Standoff and cutout positions are measured from the centre of the inside.

Lid types:
  screw     a flat lid screwed down into corner posts (with a locating lip inside the walls)
  friction  a lid with a lip that presses into the opening
  snap      as friction, with a rib on the lip that clicks into a groove in the walls
  slide     a panel that slides in along grooves in the long walls, through an open end
  none      an open-topped box

Screw holes:
  tap       a pilot hole for a thread-forming screw straight into plastic
  insert    a hole for a heat-set brass insert
  clearance a through hole for a machine screw and nut
Insert sizes vary by brand: check yours (`--insert-hole`, `--insert-depth`).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from build123d import (Plane, RegularPolygon, Shape, Align, Axis, Box, Compound, Cone, Cylinder, Location, Polygon, Pos, Rot, Text,
                       chamfer, export_step, export_stl, extrude, fillet)

from .presets import FANS, GLANDS, PRESETS, expand, resolve

# Per metric screw: (clearance hole, pilot for thread-forming in plastic, heat-set insert hole,
# insert depth, head diameter). Clearance is ISO 273 medium; pilot and insert holes are common
# 3D-printing figures (insert brands differ: override them).
SCREWS = {
    "M2": (2.4, 1.7, 3.2, 4.0, 3.8),
    "M2.5": (2.9, 2.1, 3.6, 4.5, 4.5),
    "M3": (3.4, 2.5, 4.0, 5.7, 5.5),
    "M4": (4.5, 3.4, 5.6, 8.1, 7.0),
}
LIDS = ("screw", "friction", "snap", "hinge", "living", "slide", "none", "clamshell")
TOP_LIDS = ("screw", "friction", "snap", "hinge", "living", "clamshell")  # a lid across the top
PLATE_LIDS = ("screw", "friction", "snap", "hinge", "living")  # a plate on top of the walls, maybe with a lip
PIN_HOLE = {"M2": 2.2, "M2.5": 2.7, "M3": 3.2, "M4": 4.3}  # the board hole a pin goes through
# Cells: (diameter, length) with a little room; AA and AAA are IEC 60086-2 maximums, 18650 and 21700
# their names (18 x 65, 21 x 70 mm) plus room for protected cells. Check your cells.
CELLS = {"AAA": (10.5, 44.5), "AA": (14.5, 50.5), "18650": (18.6, 67.5), "21700": (21.6, 70.5)}
CONTACT_ROOM = 7.0  # both ends' spring and button contacts (Keystone-style), mm
DENSITY = {"PETG": 1.27, "PLA": 1.24, "ABS": 1.04, "ASA": 1.07}  # g/cm3
FACES = ("-X", "+X", "-Y", "+Y", "lid", "floor")
WALLS = ("-X", "+X", "-Y", "+Y")
# Plain names for the walls (a leading "-" reads as a flag on the command line).
ALIASES = {"left": "-X", "right": "+X", "front": "-Y", "back": "+Y", "top": "lid", "bottom": "floor"}
# TS35 x 7.5 DIN rail (EN 60715): 35 mm wide, 1 mm steel.
RAIL_W, RAIL_T = 35.0, 1.0


def face_name(text: str) -> str:
    return ALIASES.get(text.lower(), text)


@dataclass
class Cutout:
    """A hole through one face. On a wall, `at` is (along the wall from its centre, height above
    the inside floor); on the lid or floor, (x, y) from the centre. `preset` names a part
    (`presets.PRESETS`) whose hole size is used."""

    face: str
    shape: str = "round"  # rect or round
    size: list[float] = field(default_factory=list)  # [width, height] for rect, [diameter] for round
    at: list[float] = field(default_factory=lambda: [0.0, 0.0])
    radius: float = 0.0  # corner radius of a rect
    preset: str | None = None
    source: str | None = None

    @staticmethod
    def parse(text: str) -> "Cutout":
        """`left:rect:9.5x3.8@0,8`, `lid:round:12@20,0`, `back:rect:20x10r2@0,15`, or a preset:
        `left:usb-c@0,8`, `back:pg9@0,20` (faces also -X +X -Y +Y)."""
        try:
            head, at_text = text.rsplit("@", 1)
            at = [float(v) for v in at_text.split(",")]
            parts = head.split(":")
            face = face_name(parts[0])
            if len(parts) == 2:
                c = Cutout(**resolve({"face": face, "preset": parts[1].lower(), "at": at}))
            else:
                _, shape, size_text = parts
                radius = 0.0
                if "r" in size_text:
                    size_text, r = size_text.split("r")
                    radius = float(r)
                c = Cutout(face, shape, [float(v) for v in size_text.split("x")], at, radius)
        except ValueError as e:
            if "preset" in str(e):
                raise
            raise ValueError(f"cutout {text!r}: write FACE:rect:WxH@a,b, FACE:round:D@a,b or "
                             f"FACE:PRESET@a,b") from None
        c.check()
        return c

    def check(self):
        if self.face not in FACES:
            raise ValueError(f"cutout face {self.face!r}: one of {', '.join(FACES)}")
        if self.preset:
            resolve({"preset": self.preset})
        if self.shape not in ("rect", "round") or len(self.size) != (2 if self.shape == "rect" else 1):
            raise ValueError("cutout shape: rect WxH or round D")
        if len(self.at) != 2:
            raise ValueError("cutout position: two numbers")


@dataclass
class BoxSpec:
    size: list[float] = field(default_factory=lambda: [100.0, 60.0, 40.0])  # L x W x H
    size_is: str = "inner"  # inner (the space inside) or outer
    wall: float = 2.0
    floor: float = 2.0
    corner_radius: float = 3.0  # outside vertical corners; 0 for square
    lid: str = "screw"
    lid_thickness: float = 2.0
    lid_screw: str = "M3"
    lid_screw_hole: str = "insert"  # into the corner posts: tap, insert or clearance
    lip: float = 3.0  # depth of the lid's lip (friction, snap, screw locating lip; 0 for none)
    fit_clearance: float = 0.2  # gap between mating printed parts, per side
    standoffs: list[list[float]] = field(default_factory=list)  # [x, y] from the inside centre
    standoff_height: float = 5.0
    standoff_screw: str = "M3"
    standoff_hole: str = "insert"
    standoff_ribs: bool = True  # gussets at the standoffs' feet
    insert_hole: float | None = None  # override the insert hole diameter
    insert_depth: float | None = None
    cutouts: list[dict] = field(default_factory=list)
    flange: float = 0.0  # mounting ears outside the base this far, 0 for none
    flange_screw: str = "M4"
    # Printing
    teardrop: bool = True  # round wall holes over 5 mm get 45° sides with a flat top, to print without support
    bottom_chamfer: float = 0.4  # against the first layer's squish; 0 for none
    # Weather
    gasket: float = 0.0  # O-ring cord diameter for a sealed screw lid, 0 for none
    # More
    vents: list[dict] = field(default_factory=list)  # {face, size [w, h], at, slot, pitch}
    feet: float = 0.0  # rubber foot diameter: four locating recesses under the floor
    feet_depth: float = 0.6
    keyholes: str | None = None  # a screw (M3, M4) to hang the box from, through the floor
    keyhole_spacing: float = 0.0  # 0: 60% of the length
    din_rail: bool = False  # a TS35 rail clip under the floor, the rail along X
    labels: list[dict] = field(default_factory=list)  # {face, text, size, at, depth}
    # Holding the board
    board_thickness: float = 1.6  # for pin standoffs and card guides
    card_slots: list[float] = field(default_factory=list)  # X of each board standing in guides on the ±Y walls
    # Windows: a through opening with a recess behind it for a clear panel or display
    windows: list[dict] = field(default_factory=list)  # {face, size [w, h], at, panel [w, h], panel_t}
    # Posts under the lid for a display or button board behind it: [x, y] from the centre
    lid_standoffs: list[list[float]] = field(default_factory=list)
    lid_standoff_height: float = 4.0  # down from the lid's underside
    board_screw_length: float | None = None  # the board screws' length; None picks a stock length
    lid_screw_length: float | None = None
    lid_standoff_screw: str = "M2.5"
    # Batteries: a cradle on the floor: {cell, count, at [x, y], axis x|y}
    batteries: list[dict] = field(default_factory=list)
    # Cables: zip-tie anchors on the floor [[x, y]], and notches in the top of a wall {face, at, d}
    tie_points: list[list[float]] = field(default_factory=list)
    cable_notches: list[dict] = field(default_factory=list)
    material: str = "PETG"  # for the weight estimate: PETG, PLA, ABS, ASA
    # Clamshell: the box splits at this fraction of the inside height (from the floor) into two shells
    split: float = 0.6
    # Light pipes: tubes from the lid down to LEDs on the board: [{at: [x, y], d}]
    light_pipes: list[dict] = field(default_factory=list)
    power_w: float = 0.0  # heat the electronics give off, for the temperature estimate
    # A battery door in the floor: {size [w, l] of the opening, at [x, y], screw}; the door is its own part
    battery_door: dict | None = None
    # Cable strain relief: a clamp inside behind a cable hole: [{face, d (cable), at [along, height]}]
    strain_reliefs: list[dict] = field(default_factory=list)
    # Dividers: walls splitting the inside into sections: [{axis: x (a wall across at X = at) or y,
    # at, thickness, height (blank: up to under the lid), span [from, to] along it, removable, notch (a cable gap)}]
    dividers: list[dict] = field(default_factory=list)
    icons: bool = False  # symbols beside panel holes (USB, power, antenna...), from each cutout's preset
    icon_style: str = "engraved"  # engraved or raised
    two_color: bool = False  # labels and icons as separate bodies for a second filament (AMS)
    fan_flow_cfm: float = 0.0  # a fan's airflow through the box, for the temperature estimate
    lanyard: bool = False
    belt_clip: bool = False
    handle: bool = False  # (older) a bar handle on the lid; handles below is the full set
    # Handles: [{face (lid, or a wall), type: bar, knob, grip (a recessed finger pocket), strap (loops for a
    # webbing strap), length, at [a, b]}]
    handles: list[dict] = field(default_factory=list)
    # Artwork: [{face, data (the SVG or DXF's text), kind svg|dxf, width, at [a, b], rotate, depth, line, name}]
    art: list[dict] = field(default_factory=list)
    ground_lug: list[float] | None = None  # [x, y]: an M3 insert boss for a ground terminal
    shielding: bool = False  # notes on copper-tape shielding
    wall_bracket: bool = False  # a French-cleat rail on the floor and a bracket for the wall (its own part)
    stacking: bool = False  # pins on the lid and sockets under the floor so boxes stack in line
    # Magnets: round pockets for disc magnets: [{face (lid, floor or a wall), at [a, b], d, t, side outside|inside,
    # fit press|glue, hidden (sealed in, dropped in at a print pause: floor and lid only)}]
    magnets: list[dict] = field(default_factory=list)
    # A lid held shut by magnets: {d, t}: pockets in corner posts and matching ones under the lid
    magnet_lid: dict | None = None

    # The box's dimensions
    @property
    def inner(self):
        L, W, H = self.size
        if self.size_is == "outer":
            return (L - 2 * self.wall, W - 2 * self.wall, H - self.floor - self._lid_height())
        return (L, W, H)

    @property
    def outer(self):
        L, W, H = self.inner
        return (L + 2 * self.wall, W + 2 * self.wall, H + self.floor + self._lid_height())

    def base_height(self):
        """The base's walls, floor up: the inside height, plus the lid's thickness for a slide lid
        (whose panel sits inside the walls)."""
        h = self.floor + self.inner[2]
        return h + (self.lid_thickness + 1.0 if self.lid == "slide" else 0.0)

    def _lid_height(self):
        """What the lid adds above the inside height: its thickness on top, or for a slide lid
        the panel and the 1 mm of wall over it."""
        if self.lid == "none":
            return 0.0
        return self.lid_thickness + 1.0 if self.lid == "slide" else self.lid_thickness

    def check(self):
        self.cutouts = expand(self.cutouts)
        if len(self.size) != 3 or min(self.size) <= 0:
            raise ValueError("size: three numbers above 0, L x W x H")
        if self.size_is not in ("inner", "outer"):
            raise ValueError("size_is: inner or outer")
        if self.lid not in LIDS:
            raise ValueError(f"lid: one of {', '.join(LIDS)}")
        for name in ("lid_screw", "standoff_screw", "flange_screw"):
            if getattr(self, name) not in SCREWS:
                raise ValueError(f"{name}: one of {', '.join(SCREWS)}")
        if self.keyholes is not None and self.keyholes not in SCREWS:
            raise ValueError(f"keyholes: a screw, one of {', '.join(SCREWS)}")
        if self.lid_screw_hole not in ("tap", "insert", "clearance"):
            raise ValueError("lid_screw_hole: tap, insert or clearance")
        if self.standoff_hole not in ("tap", "insert", "clearance", "pin"):
            raise ValueError("standoff_hole: tap, insert, clearance or pin (a snap-in peg)")
        L_in, W_in, _ = self.inner
        if self.lid_standoffs and self.lid not in TOP_LIDS:
            raise ValueError("lid standoffs need a lid on top")
        if self.lid_standoff_screw not in SCREWS:
            raise ValueError(f"lid_standoff_screw: one of {', '.join(SCREWS)}")
        for bt in self.batteries:
            if bt.get("cell") not in CELLS:
                raise ValueError(f"battery cell: one of {', '.join(CELLS)}")
            if bt.get("axis", "x") not in ("x", "y") or not 1 <= int(bt.get("count", 1)) <= 8:
                raise ValueError("battery: axis x or y, 1 to 8 cells")
        for n in self.cable_notches:
            if face_name(n.get("face", "")) not in WALLS or not 2 <= n.get("d", 0) <= 30:
                raise ValueError("cable notch: on a wall, 2 to 30 mm wide")
        if self.lid == "clamshell" and not 0.2 <= self.split <= 0.8:
            raise ValueError("split: where the clamshell parts, 0.2 to 0.8 of the inside height")
        if self.light_pipes and self.lid not in TOP_LIDS:
            raise ValueError("light pipes hang from a lid on top")
        for lp in self.light_pipes:
            if not 1.0 <= lp.get("d", 3.0) <= 10.0:
                raise ValueError("light pipe: d, the pipe's diameter, 1 to 10 mm")
        if not 0 <= self.power_w <= 200:
            raise ValueError("power_w: the electronics' heat, 0 to 200 W")
        if self.material not in DENSITY:
            raise ValueError(f"material: one of {', '.join(DENSITY)}")
        for x in self.card_slots:
            if abs(x) > L_in / 2 - 4:
                raise ValueError(f"card slot at X {x:g}: keep it 4 mm or more from the end walls")
        for wdw in self.windows:
            f = face_name(wdw.get("face", ""))
            if f not in ("lid", *WALLS):
                raise ValueError("window: on the lid or a wall")
            if f == "lid" and self.lid not in TOP_LIDS:
                raise ValueError("a lid window needs a lid on top")
            w, h = wdw.get("size", [0, 0])
            pw, ph = wdw.get("panel", [w + 4, h + 4])
            if w <= 0 or h <= 0 or pw < w + 1 or ph < h + 1:
                raise ValueError("window: the panel must be at least 0.5 mm bigger than the opening on each side")
            thick = self.lid_thickness if f == "lid" else self.wall
            if thick - wdw.get("panel_t", 1.0) < 0.8:
                raise ValueError(f"window on {f}: a {wdw.get('panel_t', 1.0):g} mm panel leaves under 0.8 mm of a "
                                 f"{thick:g} mm {'lid' if f == 'lid' else 'wall'}; make it thicker or the panel thinner")
        if min(self.inner) <= 0:
            raise ValueError("the walls, floor and lid leave no room inside: make the box bigger")
        if self.wall < 1.0 or self.floor < 1.0:
            raise ValueError("wall and floor: at least 1 mm")
        if self.gasket and self.lid != "screw":
            raise ValueError("a gasket needs a screw lid to press it")
        if self.gasket and not 1.0 <= self.gasket <= 5.0:
            raise ValueError("gasket: the cord's diameter, 1 to 5 mm")
        if self.feet and self.floor < self.feet_depth + 0.8:
            raise ValueError(f"feet: the floor needs {self.feet_depth + 0.8:g} mm for {self.feet_depth:g} mm recesses")
        if self.din_rail and self.inner[1] + 2 * self.wall < RAIL_W + 8:
            raise ValueError(f"din_rail: the box must be at least {RAIL_W + 8:g} mm wide outside")
        for dv in self.dividers:
            if dv.get("axis") not in ("x", "y"):
                raise ValueError("divider axis: x (a wall across the box at X = at) or y (at Y = at)")
            half = (L_in if dv["axis"] == "x" else W_in) / 2
            if abs(float(dv.get("at", 0))) > half - 2:
                raise ValueError(f"divider at {dv.get('at')}: keep it inside the walls (±{half - 2:g} mm)")
            if not 0.8 <= float(dv.get("thickness") or self.wall) <= 10:
                raise ValueError("divider thickness: 0.8 to 10 mm")
        for c in self.cutouts:
            Cutout(**resolve(c)).check()
        for v in self.vents:
            if face_name(v.get("face", "")) not in FACES or len(v.get("size", [])) != 2:
                raise ValueError("vent: {face, size: [w, h], at: [a, b]}")
        for t in self.labels:
            if face_name(t.get("face", "")) not in ("lid", *WALLS) or not t.get("text"):
                raise ValueError("label: {face: lid or a wall, text, size, at, depth}")
            if t.get("face") == "lid" and self.lid not in TOP_LIDS:
                raise ValueError("a lid label needs a lid on top")

    def hole(self, screw: str, kind: str) -> tuple[float, float | None]:
        """(diameter, depth) of a screw hole of this kind; depth None for through. For a pin, the
        peg's diameter (the board's hole for that screw, less a little)."""
        clearance, pilot, insert, depth, _ = SCREWS[screw]
        if kind == "pin":
            return PIN_HOLE[screw] - 0.25, 0.0
        if kind == "tap":
            return pilot, None
        if kind == "insert":
            return self.insert_hole or insert, (self.insert_depth or depth) + 0.5
        return clearance, None


def _rounded_box(L, W, H, r, z0=0.0):
    b = Box(L, W, H).locate(Location((0, 0, z0 + H / 2)))
    if r > 0.05:
        b = fillet(b.edges().filter_by(Axis.Z), min(r, L / 2 - 0.01, W / 2 - 0.01))
    return b


def _post_boss(spec: BoxSpec, d_hole: float) -> float:
    return max(2.2 * d_hole, d_hole + 2 * 1.6)


TEARDROP_MIN = 5.0  # mm: smaller round holes print fine as circles


def _profile(shape: str, size, radius: float, depth: float, teardrop: bool = False):
    """A cutting tool along Z, centred: a rect (corner radius) or a round hole, its local +Y up.
    A teardrop adds 45° sides above a round hole so it prints without support, cut off flat at the
    circle's top: the hole stays its own height, and the flat (0.41 x the diameter) bridges easily.
    Holes 5 mm and under stay round: printers bridge those as they are."""
    if shape == "round":
        r = size[0] / 2
        tool = Cylinder(r, depth)
        if teardrop and size[0] > TEARDROP_MIN:
            k = r * math.sqrt(0.5)
            f = r * (math.sqrt(2) - 1)  # half the flat, where the 45° sides meet the circle's top
            cap = extrude(Polygon((-k, k), (k, k), (f, r), (-f, r), align=None), amount=depth / 2, both=True)
            tool = tool + cap
        return tool
    tool = Box(size[0], size[1], depth)
    if radius > 0:
        tool = fillet(tool.edges().filter_by(Axis.Z), min(radius, min(size) / 2 - 0.01))
    return tool


def _honeycomb(w: float, h: float, cell: float, web: float) -> list[tuple[float, float]]:
    """Centres of hexagons (cell mm across the flats, flats up and down) filling a w x h area, web apart."""
    pitch_x = cell + web
    pitch_y = (cell + web) * math.sqrt(3) / 2
    r = cell / math.sqrt(3)  # corner radius
    out = []
    rows = int((h - cell) // pitch_y) + 1 if h >= cell else 0
    for j in range(rows):
        y = -h / 2 + cell / 2 + j * pitch_y
        off = pitch_x / 2 if j % 2 else 0.0
        x = -w / 2 + r + off
        while x + r <= w / 2 + 1e-6:
            out.append((x, y))
            x += pitch_x
    # Centre the pattern.
    if out:
        xs, ys = [p[0] for p in out], [p[1] for p in out]
        dx, dy = -(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2
        out = [(x + dx, y + dy) for x, y in out]
    return out


def _hex_area(cell: float) -> float:
    return math.sqrt(3) / 2 * cell ** 2


def _on_wall(tool, face: str, along: float, z: float, oL: float, oW: float):
    """Put a tool built along Z (local +Y up) through a wall, centred `along` it at height z."""
    sign = -1 if face.startswith("-") else 1
    if face in ("-X", "+X"):
        return Pos(sign * oL / 2, along, z) * (Rot(0, 90, 0) * Rot(0, 0, 90) * tool)
    return Pos(along, sign * oW / 2, z) * (Rot(90, 0, 0) * tool)


PIN_D = 1.75  # a length of 3D printer filament is the hinge pin


def hinge_axis(spec: "BoxSpec") -> tuple[float, float, float]:
    """(y, z, knuckle radius) of a hinge lid's pin, which runs along X outside the +Y wall."""
    L, W, H = spec.inner
    oW = W + 2 * spec.wall
    top = spec.floor + H
    rk = max(2.6, PIN_D / 2 + 0.35 + 1.4, spec.lid_thickness / 2 + 0.6)
    return oW / 2 + spec.fit_clearance + rk, top + spec.lid_thickness - rk, rk


def _hinge(spec, lid, base, top, oL, oW, notes, checks):
    """Knuckles along the +Y edge: three on the base (on 45 degree wedges, so the base prints
    upright without support), two on the lid, flush with its top so it prints top down; a
    1.75 mm filament pin through them all. The lid's snap rib on -Y is the latch."""
    c = spec.fit_clearance
    ay, az, rk = hinge_axis(spec)
    t = spec.lid_thickness
    span = 0.8 * oL - 2 * spec.corner_radius
    if span < 20:
        raise ValueError("a hinge lid needs the box at least about 35 mm long")
    n = 5
    seg = (span - (n - 1) * c) / n
    hole = PIN_D + 0.35
    for i in range(n):
        x0 = -span / 2 + i * (seg + c)
        xc = x0 + seg / 2
        knuckle = Cylinder(rk, seg, rotation=(0, 90, 0)).locate(Location((xc, ay, az)))
        if i % 2 == 0:  # base: knuckle on a wedge sloping back into the wall
            reach = ay - oW / 2 + 0.01
            wedge = extrude(Plane.YZ * Polygon((oW / 2 - 0.01, top - reach), (oW / 2 - 0.01, top), (ay, top), (ay, az), align=None),
                            amount=seg)
            base += Pos(x0 + seg, 0, 0) * wedge + knuckle  # Plane.YZ extrudes toward -X
        else:  # lid: a bridge from the lid's edge to the knuckle
            lid += Box(seg, ay - oW / 2 + 0.01, t).locate(Location((xc, (oW / 2 - 0.01 + ay) / 2, top + t / 2))) + knuckle
    pin = Cylinder(hole / 2, span + 2, rotation=(0, 90, 0)).locate(Location((0, ay, az)))
    base -= pin
    lid -= pin
    notes.append(f"hinge lid: 5 knuckles along the +Y edge, Ø{2 * rk:.1f} mm; push a {span + 6:.0f} mm piece of {PIN_D:g} mm "
                 f"filament through the Ø{hole:.2f} hole and melt the ends; the snap rib on -Y holds it shut")
    if spec.lip <= 0:
        checks.append("hinge lid with no lip: there is nothing to latch it shut; give it a lip")
    for raw in spec.cutouts:
        if face_name(raw.get("face", "")) == "+Y":
            checks.append("a cutout on +Y sits under the hinge: check it clears the knuckles and wedges")
            break
    return lid, base


# Screw lengths in stock (ISO 4762 / 7380 preferred lengths, mm).
STOCK_LENGTHS = (3, 4, 5, 6, 8, 10, 12, 14, 16, 20, 25, 30, 35, 40)
NUT_HEIGHT = {"M2": 1.6, "M2.5": 2.0, "M3": 2.4, "M4": 3.2}  # ISO 4032


def _stock_length(need: float) -> int:
    return next((n for n in STOCK_LENGTHS if n >= need - 0.25), STOCK_LENGTHS[-1])


def screw_plan(spec: "BoxSpec") -> dict:
    """The board and lid screws: the length (yours, or the stock length that suits), what it clamps,
    how deep its hole is, how much thread it gets, and checks for one that bottoms out or barely bites."""
    plan, checks = {}, []

    def judge(role, m, kind, clamp, hole_depth, chosen, auto_need, nut=0.0):
        d = float(m[1:])
        want = (0.75 * SCREWS[m][3]) if kind == "insert" else 1.5 * d
        if chosen:
            length = chosen
        elif kind == "clearance":
            length = _stock_length(auto_need)
        else:  # the longest stock screw that neither bottoms out nor runs past the insert (or 2.5 x d in plastic)
            reach = min(hole_depth, SCREWS[m][3] if kind == "insert" else 2.5 * d)
            length = max([n for n in STOCK_LENGTHS if n <= clamp + reach + 0.05] or [STOCK_LENGTHS[0]])
        into = length - clamp
        row = {"screw": m, "length": length, "clamp": round(clamp, 2), "hole_depth": round(hole_depth, 2), "kind": kind,
               "engaged": round(min(into, hole_depth), 2)}
        if kind == "clearance":  # through, into a nut underneath
            row["engaged"] = round(max(into - hole_depth, 0.0), 2)
            if into < hole_depth + nut:
                checks.append(f"{role} screws {m}x{length:g}: {into:.1f} mm past the {role.split()[0]} but the nut sits "
                              f"{hole_depth:.1f} mm down and is {nut:g} mm thick; use {_stock_length(clamp + hole_depth + nut + 0.5)} mm")
        else:
            if into > hole_depth + 0.05:
                checks.append(f"{role} screws {m}x{length:g}: {into:.1f} mm below the {('board' if role.startswith('board') else 'lid')} "
                              f"but the hole is {hole_depth:.1f} mm deep: it will bottom out. Use "
                              f"{max([n for n in STOCK_LENGTHS if n <= clamp + hole_depth] or [STOCK_LENGTHS[0]])} mm")
            if into < want - 0.05:
                checks.append(f"{role} screws {m}x{length:g}: only {max(into, 0):.1f} mm of thread {'in the insert' if kind == 'insert' else 'in the plastic'}; "
                              f"{want:.1f} mm or more holds well")
        plan[role.replace(" ", "_")] = row

    if spec.standoffs and spec.standoff_hole != "pin":
        m = spec.standoff_screw
        d_hole, depth = spec.hole(m, spec.standoff_hole)
        h = spec.standoff_height
        bt = spec.board_thickness
        if spec.standoff_hole == "insert":
            hole_depth = min(depth, h + spec.floor - 0.6)
            need = bt + SCREWS[m][3] * 0.9
        elif spec.standoff_hole == "tap":
            hole_depth = h
            need = bt + min(h, 2.5 * float(m[1:]))
        else:
            hole_depth = h + spec.floor
            need = bt + hole_depth + NUT_HEIGHT.get(m, 2.4) + 0.5
        judge("board", m, spec.standoff_hole, bt, hole_depth, spec.board_screw_length, need, NUT_HEIGHT.get(m, 2.4))
    if spec.lid == "screw":
        m = spec.lid_screw
        d_hole, depth = spec.hole(m, spec.lid_screw_hole)
        post_h = spec.base_height() - spec.floor
        clamp = spec.lid_thickness / 2  # the heads sit in a counterbore half the lid deep
        hole_depth = depth if depth else post_h - 1.0
        need = clamp + (SCREWS[m][3] * 0.9 if spec.lid_screw_hole == "insert" else min(hole_depth, 2.5 * float(m[1:])))
        if spec.lid_screw_hole == "clearance":
            checks.append("lid screws in clearance holes have nothing to bite: use tap or insert for the corner posts")
        else:
            judge("lid", m, spec.lid_screw_hole, clamp, hole_depth, spec.lid_screw_length, need)
    return {**plan, "checks": checks}


def _sections(spec: "BoxSpec") -> list[tuple[float, float]]:
    """The sections' inside sizes when the dividers run wall to wall (a grid); [] when any is partial."""
    L, W, _ = spec.inner
    xs, ys = [-L / 2, L / 2], [-W / 2, W / 2]
    for dv in spec.dividers:
        if dv.get("span"):
            return []
        (xs if dv["axis"] == "x" else ys).append(float(dv["at"]))
    xs.sort()
    ys.sort()
    t = {dv["axis"]: float(dv.get("thickness") or spec.wall) for dv in spec.dividers}
    out = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            w = xs[i + 1] - xs[i] - (t.get("x", 0) / 2 if i > 0 else 0) - (t.get("x", 0) / 2 if i < len(xs) - 2 else 0)
            d = ys[j + 1] - ys[j] - (t.get("y", 0) / 2 if j > 0 else 0) - (t.get("y", 0) / 2 if j < len(ys) - 2 else 0)
            out.append((w, d))
    return out


def grid_dividers(spec: "BoxSpec", nx: int, ny: int, **kw) -> list[dict]:
    """Dividers for an even grid of nx by ny sections."""
    L, W, _ = spec.inner
    out = [{"axis": "x", "at": round(-L / 2 + L * i / nx, 3), **kw} for i in range(1, nx)]
    out += [{"axis": "y", "at": round(-W / 2 + W * j / ny, 3), **kw} for j in range(1, ny)]
    return out


LIVING_T = 0.5  # the living hinge strip's thickness, mm


def living_turn(spec: "BoxSpec"):
    """The move that opens a living-hinge lid 90 degrees to stand on the back wall (its print position)."""
    L, W, H = spec.inner
    oW = W + 2 * spec.wall
    top = spec.floor + H
    pivot = (0, oW / 2, top + spec.lid_thickness)
    return lambda shape: shape.rotate(Axis((0, pivot[1], pivot[2]), (1, 0, 0)), -90)


def living_print_body(spec: "BoxSpec", base, lid):
    """The box in one piece as it prints: the base upright, the lid standing on the back wall's top,
    joined along the outside by a thin strip that bends when it shuts."""
    L, W, H = spec.inner
    oL, oW = L + 2 * spec.wall, W + 2 * spec.wall
    top = spec.floor + H
    t = spec.lid_thickness
    turn = living_turn(spec)
    opened = turn(lid)
    strip_len = oL - 2 * spec.corner_radius - 2.0
    strip = Box(strip_len, LIVING_T, t + 0.02, align=(Align.CENTER, Align.MAX, Align.MIN)).locate(Location((0, oW / 2, top - 0.01)))
    return base + strip + opened, turn


HANDLE_TYPES = ("bar", "knob", "grip", "strap")


MAGNET_SKIN = 0.6  # plastic left behind a blind magnet pocket
MAGNET_FIT = {"press": 0.15, "glue": 0.3}  # added to the magnet's diameter


def _magnet_hole(m: dict) -> tuple[float, float, float]:
    """(magnet d, t, pocket diameter) from a magnet row, checked."""
    d, t = float(m.get("d", 6.0)), float(m.get("t", 2.0))
    if not 1 <= d <= 40 or not 0.5 <= t <= 20:
        raise ValueError("magnet: diameter 1 to 40 mm, thickness 0.5 to 20 mm")
    fit = m.get("fit", "press")
    if fit not in MAGNET_FIT:
        raise ValueError("magnet fit: press or glue")
    return d, t, d + MAGNET_FIT[fit]


def _magnet_lid(spec, m, base, lid, posts, top, notes, checks):
    """A pocket in the top of each corner post, and one under the lid over it, for a pair of magnets.
    A hinged lid only gets them at the front (the side away from the hinge)."""
    d, t, hole = _magnet_hole(m)
    depth = t + 0.1  # sit the magnet a hair under the surface so the lid closes flat
    use = [(x, y) for x, y in posts if spec.lid not in ("hinge", "living") or y < 0]
    pad = max(0.0, depth + MAGNET_SKIN - spec.lid_thickness)
    lid_top = top + spec.lid_thickness
    for x, y in use:
        base -= Pos(x, y, top - depth) * Cylinder(hole / 2, depth + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if pad:
            lid += Pos(x, y, lid_top) * Cylinder(hole / 2 + 1.6, pad, align=(Align.CENTER, Align.CENTER, Align.MIN))
        lid -= Pos(x, y, top - 0.01) * Cylinder(hole / 2, depth + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    notes.append(f"magnet lid: {2 * len(use)} magnets Ø{d:g} x {t:g} mm, one in the top of each of {len(use)} corner "
                 f"posts and one under the lid above it (pockets Ø{hole:g} x {depth:g} mm); check the poles attract before "
                 "gluing the second set")
    if pad:
        notes.append(f"the lid is thinner than the magnets: a {pad:.1f} mm round pad on top over each one")
    if d > 12:
        checks.append("big magnets in the corner posts make them wide: they may crowd the board")
    return base, lid


def _magnet(spec, m, i, base, lid, top, oL, oW, notes, checks):
    """A pocket for a disc magnet in the lid, floor or a wall, open to the outside or the inside, or sealed
    in (hidden) for dropping in at a print pause. Where the panel is too thin, a round boss inside backs it."""
    face = face_name(m.get("face", "floor"))
    d, t, hole = _magnet_hole(m)
    side = m.get("side", "outside")
    if side not in ("outside", "inside"):
        raise ValueError("magnet side: outside or inside")
    hidden = bool(m.get("hidden"))
    a, b = (list(m.get("at") or [0, 0]) + [0])[:2]
    a, b = float(a or 0), float(b or 0)
    if face == "lid" and lid is None:
        raise ValueError("a magnet in the lid needs a lid")
    if face not in ("lid", "floor") + WALLS:
        raise ValueError("magnets go in the lid, the floor or a wall")
    if hidden and face not in ("lid", "floor"):
        raise ValueError("hidden magnets go in the floor or lid (a print pause drops them into a flat pocket)")
    depth = t + 0.1
    # How thick the panel must be, and how thick it is.
    need = depth + (2 * MAGNET_SKIN if hidden else MAGNET_SKIN)
    have = spec.lid_thickness if face == "lid" else spec.floor if face == "floor" else spec.wall
    boss = max(0.0, need - have)
    bd = hole + 2 * 1.6
    # Work in a frame where z = 0 is the outside face and +z points into the box, then place it.
    shape_boss = Pos(0, 0, have) * Cylinder(bd / 2, boss, align=(Align.CENTER, Align.CENTER, Align.MIN)) if boss else None
    if hidden:
        z0 = MAGNET_SKIN
    elif side == "outside":
        z0 = -0.01
    else:
        z0 = have + boss - depth
    pocket = Pos(0, 0, z0) * Cylinder(hole / 2, depth + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))

    if face == "floor":
        def place(s):
            return Pos(a, b, 0) * s
    elif face == "lid":
        lid_top = top + spec.lid_thickness

        def place(s):
            return Pos(a, b, lid_top) * (Rot(180, 0, 0) * s)
    else:
        out = {"-Y": (0, -1), "+Y": (0, 1), "-X": (-1, 0), "+X": (1, 0)}[face]
        half = (oL / 2) if face in ("-X", "+X") else (oW / 2)
        along = (1, 0) if face in ("-Y", "+Y") else (0, 1)
        rot = {"-Y": Rot(-90, 0, 0), "+Y": Rot(90, 0, 0), "-X": Rot(0, 90, 0), "+X": Rot(0, -90, 0)}[face]
        x, y = out[0] * half + along[0] * a, out[1] * half + along[1] * a

        def place(s):
            return Pos(x, y, spec.floor + b) * (rot * s)
    host_is_lid = face == "lid"
    if shape_boss is not None:
        if host_is_lid:
            lid += place(shape_boss)
        else:
            base += place(shape_boss)
    if host_is_lid:
        lid -= place(pocket)
    else:
        base -= place(pocket)
    where = {"lid": "lid", "floor": "floor"}.get(face, f"{face} wall")
    how = ("sealed inside" if hidden else f"open to the {side}")
    note = f"magnet {i + 1}: Ø{d:g} x {t:g} mm in the {where}, {how}, pocket Ø{hole:g} x {depth:g} mm"
    if boss:
        note += f", a Ø{bd:g} mm boss {boss:.1f} mm thick inside behind it"
    if hidden:
        # The floor prints bottom down; the lid prints top down: either way the pocket's top is this high.
        note += f"; pause the print at {MAGNET_SKIN + depth:.2f} mm (the layer that closes over it) and drop the magnet in"
    elif m.get("fit", "press") == "press":
        note += "; press it in (a drop of CA glue if it's loose)"
    else:
        note += "; glue it in (CA or epoxy)"
    notes.append(note)
    return base, lid


def _handle(spec, hd, i, base, lid, top, oL, oW, base_h, checks):
    """One handle: a part to screw on (bar, knob), a finger pocket in a wall (grip), or loops for a
    strap (strap). Returns (extra parts, notes, base, lid, mounted), mounted being the screw-on parts placed where
    they go on the box (for the preview), each with the body it rides on."""
    face = face_name(hd.get("face", "lid"))
    kind = hd.get("type", "bar")
    if kind not in HANDLE_TYPES:
        raise ValueError(f"handle type: one of {', '.join(HANDLE_TYPES)}")
    L, W, H = spec.inner
    m = "M3"
    clear, pilot = SCREWS[m][0], SCREWS[m][1]
    extras, notes = [], []
    a, b = (list(hd.get("at") or [0, None]) + [None])[:2]
    a = float(a or 0)
    b = (0.0 if face == "lid" else H * 0.7) if b is None else float(b)
    on_lid = face == "lid"
    if on_lid and lid is None:
        raise ValueError("a handle on the lid needs a lid")
    if not on_lid and face not in WALLS:
        raise ValueError("handles go on the lid or a wall")
    span = (oW if face in ("-X", "+X") else oL)
    length = float(hd.get("length") or (min((oL if on_lid else span) * 0.6, 120.0) if kind == "bar" else 60.0))
    name = f"handle_{i + 1}"
    mounted = []
    lid_top = top + spec.lid_thickness

    # Where things go on a wall: a point on its outside face, and the outward direction.
    def wall_point(u, z):
        out = {"-Y": (0, -1), "+Y": (0, 1), "-X": (-1, 0), "+X": (1, 0)}[face]
        half = (oL / 2) if face in ("-X", "+X") else (oW / 2)
        along = (1, 0) if face in ("-Y", "+Y") else (0, 1)
        return (out[0] * half + along[0] * u, out[1] * half + along[1] * u, spec.floor + z), out

    def turn_to_wall(shape):
        """A shape built standing on z = 0 pointing up (+Z = out of the wall), turned to point out of this wall."""
        rot = {"-Y": Rot(90, 0, 0), "+Y": Rot(-90, 0, 0), "-X": Rot(0, -90, 0), "+X": Rot(0, 90, 0)}[face]
        if face in ("-X", "+X"):
            shape = Rot(0, 0, 90) * shape  # its length along the wall (Y)
        return rot * shape

    if kind == "bar":
        hl = length
        bar = Box(hl, 12, 4, align=(Align.CENTER, Align.CENTER, Align.MIN)).locate(Location((0, 0, 22)))
        for sx in (-1, 1):
            bar += Box(10, 12, 26, align=(Align.CENTER, Align.CENTER, Align.MIN)).locate(Location((sx * (hl / 2 - 5), 0, 0)))
            bar -= Pos(sx * (hl / 2 - 5), 0, 0) * Cylinder(pilot / 2, 16, align=(Align.CENTER, Align.CENTER, Align.MIN))
        holes = [-(hl / 2 - 5), hl / 2 - 5]
        if on_lid:
            for u in holes:
                lid -= Pos(a + u, b, top) * Cylinder(clear / 2, 40)
        else:
            for u in holes:
                (x, y, z), out = wall_point(a + u, b)
                tool = Cylinder(clear / 2, spec.wall * 6, rotation=(90, 0, 0) if face in ("-Y", "+Y") else (0, 90, 0))
                base -= Pos(x, y, z) * tool
        extras.append((name, Rot(90, 0, 0) * bar))
        if on_lid:
            mounted.append((name, Pos(a, b, lid_top) * bar, "lid"))
        else:
            (x, y, z), _ = wall_point(a, b)
            mounted.append((name, Pos(x, y, z) * turn_to_wall(bar), "base"))
        _span_check(spec, f"bar handle on {face}", face, a, b, hl, 6.0, checks)
        notes.append(f"bar handle on {face}: its own part, two M3 screws through the {'lid' if on_lid else 'wall'} into it, "
                     f"{hl - 10:g} mm apart; print it on its side")
    elif kind == "knob":
        knob = Cylinder(9, 4, align=(Align.CENTER, Align.CENTER, Align.MIN)) + Pos(0, 0, 4) * Cylinder(5, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
        knob += Pos(0, 0, 14) * Cylinder(10, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))
        knob -= Cylinder(pilot / 2, 12, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if on_lid:
            lid -= Pos(a, b, top) * Cylinder(clear / 2, 40)
        else:
            (x, y, z), out = wall_point(a, b)
            base -= Pos(x, y, z) * Cylinder(clear / 2, spec.wall * 6, rotation=(90, 0, 0) if face in ("-Y", "+Y") else (0, 90, 0))
        extras.append((name, Rot(180, 0, 0) * knob))
        if on_lid:
            mounted.append((name, Pos(a, b, lid_top) * knob, "lid"))
        else:
            (x, y, z), _ = wall_point(a, b)
            mounted.append((name, Pos(x, y, z) * turn_to_wall(knob), "base"))
        _span_check(spec, f"knob on {face}", face, a, b, 6.0, 6.0, checks)
        notes.append(f"pull knob on {face}: its own part, one M3 screw through the {'lid' if on_lid else 'wall'} into it; print it top down")
    elif kind == "grip":
        # A finger pocket: the wall thickened inside behind it, the pocket cut from outside.
        if on_lid:
            raise ValueError("a grip pocket goes in a wall (use a bar or knob on the lid)")
        gl, gh, depth = length, 18.0, 7.0
        (x, y, z), out = wall_point(a, b)
        back = Box(gl + 6, depth + 1.2 - spec.wall + 0.01, gh + 6) if face in ("-Y", "+Y") else Box(depth + 1.2 - spec.wall + 0.01, gl + 6, gh + 6)
        inner = depth + 1.2 - spec.wall
        bx = x - out[0] * (spec.wall + inner / 2)
        by = y - out[1] * (spec.wall + inner / 2)
        base += Pos(bx, by, z) * back
        pocket = Box(gl, depth * 2, gh) if face in ("-Y", "+Y") else Box(depth * 2, gl, gh)
        base -= Pos(x, y, z) * pocket
        notes.append(f"finger grip in the {face} wall: a {gl:g} x {gh:g} mm pocket {depth:g} mm deep, the wall thickened inside "
                     f"behind it ({inner:.1f} mm into the box)")
        checks.append(f"the grip on {face} takes {inner:.1f} mm of the inside behind it: check the board clears it")
        _span_check(spec, f"grip on {face}", face, a, b, gl + 6, gh + 6, checks)
    else:  # strap loops, a pair on this wall
        sw = float(hd.get("strap_width", 25.0))
        slot_t = 3.5
        for su in (-1, 1):
            u = a + su * (length / 2)
            (x, y, z), out = wall_point(u, b)
            loop_w, loop_d, loop_h = sw + 7, slot_t + 4, 12.0
            if face in ("-Y", "+Y"):
                blk, slot = Box(loop_w, loop_d, loop_h), Box(sw + 1, slot_t, loop_h * 3)
            else:
                blk, slot = Box(loop_d, loop_w, loop_h), Box(slot_t, sw + 1, loop_h * 3)
            cx_ = x + out[0] * (loop_d / 2 - 0.01)
            cy_ = y + out[1] * (loop_d / 2 - 0.01)
            base += Pos(cx_, cy_, z) * blk
            base -= Pos(x + out[0] * (1.5 + slot_t / 2), y + out[1] * (1.5 + slot_t / 2), z) * slot  # 1.5 mm of block on the wall side
        _span_check(spec, f"strap loops on {face}", face, a, b, length + sw + 7, 12.0, checks, through=False)
        if length < sw + 9:
            checks.append(f"strap loops on {face}: {length:g} mm apart is less than their width; space them further")
        notes.append(f"strap loops on {face}: two, {length:g} mm apart, each with a {sw + 1:g} x {slot_t:g} mm slot standing up for a "
                     f"{sw:g} mm strap (thread it down through both)")
    return extras, notes, base, lid, mounted


def _span_check(spec, what: str, face: str, a: float, b: float, w: float, h: float, checks: list, through: bool = True) -> None:
    """Flag a feature `w` wide and `h` tall, centred `a` along a wall and `b` up from the inside floor (or at
    (a, b) on the lid or floor), that runs past the floor, the top or the wall's ends."""
    L, W, H = spec.inner
    if face in ("lid", "floor"):
        for v, half, ax in ((a, L / 2, "X"), (b, W / 2, "Y")):
            ext = (w if ax == "X" else h) / 2
            if abs(v) + ext > half + 0.01:
                checks.append(f"{what}: it runs {abs(v) + ext - half:.1f} mm past the inside edge in {ax} (keep its centre within "
                              f"±{max(half - ext, 0):g} mm)")
        return
    half = (W if face in ("-X", "+X") else L) / 2
    # Anything through the wall must stay under the lid's lip; something only on the outside, under the lid.
    top_room = H - (spec.lip + 0.5 if through and spec.lid in PLATE_LIDS and spec.lip else 0.0)
    lo, hi = b - h / 2, b + h / 2
    if lo < -0.01:
        checks.append(f"{what}: 'up from floor' is its centre, so at {b:g} mm its bottom edge is {-lo:.1f} mm below the inside "
                      f"floor; set it to at least {h / 2:g} mm")
    if hi > top_room + 0.01:
        why = "into the lid's lip" if top_room < H else "above the top of the wall"
        checks.append(f"{what}: its top edge is {hi - top_room:.1f} mm {why}; set 'up from floor' to at most {max(top_room - h / 2, 0):g} mm")
    if abs(a) + w / 2 > half + 0.01:
        checks.append(f"{what}: it runs {abs(a) + w / 2 - half:.1f} mm past the end of the wall (keep 'along wall' within "
                      f"±{max(half - w / 2, 0):g} mm{', or shorten it' if w / 2 >= half else ''})")


def build(spec: BoxSpec) -> dict:
    """The base and lid as solids, notes on what was made, and checks worth a look."""
    spec.check()
    if spec.lid == "clamshell":
        return _clamshell(spec)
    L, W, H = spec.inner
    oL, oW = L + 2 * spec.wall, W + 2 * spec.wall
    base_h = spec.base_height()
    r_out = spec.corner_radius
    r_in = max(r_out - spec.wall, 0.0)
    notes, checks = [], []
    keep_out = []  # (x, y, r) inside the floor taken by posts and standoffs

    base = _rounded_box(oL, oW, base_h, r_out)
    if spec.bottom_chamfer > 0:
        try:
            base = chamfer(base.edges().group_by(Axis.Z)[0], spec.bottom_chamfer)
        except Exception:  # a corner too tight for it: leave it square
            checks.append("bottom chamfer skipped: the corners are too tight for it")
    base -= _rounded_box(L, W, base_h, r_in, z0=spec.floor)
    top = base_h

    # Corner posts for the lid screws, tucked into the inside corners.
    posts, post_holes = [], []
    post_boss = 0.0
    mag_lid = spec.magnet_lid if spec.magnet_lid and spec.lid in PLATE_LIDS and spec.lid != "screw" else None
    if spec.magnet_lid and not mag_lid:
        raise ValueError("a magnet lid needs a friction, snap, hinge or living-hinge lid (a screw lid has its screws)")
    if spec.lid == "screw" or mag_lid:
        d, depth = spec.hole(spec.lid_screw, spec.lid_screw_hole)
        post_boss = boss = _post_boss(spec, d)
        if mag_lid:
            post_boss = boss = max(boss, float(mag_lid.get("d", 6.0)) + 0.3 + 2 * 1.6)
        inset = boss / 2
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = sx * (L / 2 - inset), sy * (W / 2 - inset)
                h = top - spec.floor
                post = Cylinder(boss / 2, h).locate(Location((x, y, spec.floor + h / 2)))
                post += Box(boss / 2, boss / 2, h).locate(Location((x + sx * boss / 4, y + sy * boss / 4, spec.floor + h / 2)))
                base += post
                if not mag_lid:
                    hole_depth = depth or (h - 1.0)
                    post_holes.append(Cylinder(d / 2, hole_depth).locate(Location((x, y, top - hole_depth / 2))))
                posts.append((x, y))
                keep_out.append((x, y, boss / 2))
        if not mag_lid:
            notes.append(f"lid: {spec.lid_screw} screws into {len(posts)} corner posts ({spec.lid_screw_hole} holes Ø{d:g})")

    # Board standoffs on the floor, with gussets at their feet.
    if spec.standoffs:
        d, depth = spec.hole(spec.standoff_screw, spec.standoff_hole)
        boss = _post_boss(spec, d)
        h = spec.standoff_height
        for x, y in spec.standoffs:
            if abs(x) + boss / 2 > L / 2 + 1e-6 or abs(y) + boss / 2 > W / 2 + 1e-6:
                raise ValueError(f"standoff at ({x:g}, {y:g}) does not fit inside the walls")
            base += Cylinder(boss / 2, h + 0.01).locate(Location((x, y, spec.floor + h / 2 - 0.005)))
            if spec.standoff_ribs and h >= 3:
                reach, rh = boss / 2 + 2.5, 0.6 * h
                fin = extrude(Polygon((0, 0), (reach, 0), (0, rh), align=None), amount=0.6, both=True)
                fin = Rot(90, 0, 0) * fin  # the triangle stands up in XZ
                for a in (45, 135, 225, 315):
                    base += Pos(x, y, spec.floor) * (Rot(0, 0, a) * fin)
            if spec.standoff_hole == "pin":
                # A split peg through the board's hole with a barb on top: the board snaps down.
                bt, rp = spec.board_thickness, d / 2
                z0 = spec.floor + h
                peg = Cylinder(rp, bt + 0.3).locate(Location((x, y, z0 + (bt + 0.3) / 2)))
                barb = Cone(rp + 0.35, rp - 0.15, 1.0).locate(Location((x, y, z0 + bt + 0.3 + 0.5)))
                peg = peg + barb
                peg -= Box(0.8, d + 2, bt + 2).locate(Location((x, y, z0 + 0.6 + (bt + 2) / 2)))
                base += peg
                keep_out.append((x, y, boss / 2))
                continue
            hole_depth = depth or h
            if spec.standoff_hole == "clearance":
                hole_depth = h + spec.floor  # through the floor, for a nut underneath
            elif depth and depth > h + spec.floor - 0.6:
                checks.append(f"standoff at ({x:g}, {y:g}): the {depth - 0.5:g} mm insert is longer than "
                              f"the standoff and floor allow; make standoffs at least {depth - spec.floor + 0.1:.1f} mm tall")
                hole_depth = h + spec.floor - 0.6
            base -= Cylinder(d / 2, hole_depth).locate(Location((x, y, spec.floor + h - hole_depth / 2)))
            keep_out.append((x, y, boss / 2))
        if spec.standoff_hole == "pin":
            notes.append(f"{len(spec.standoffs)} standoffs, {h:g} mm tall, with split pins Ø{d:g} for {PIN_HOLE[spec.standoff_screw]:g} mm "
                         f"board holes and a {spec.board_thickness:g} mm board: it snaps down over the barbs (print them solid)")
        else:
            notes.append(f"{len(spec.standoffs)} standoffs, {h:g} mm tall, {spec.standoff_screw} "
                         f"{spec.standoff_hole} holes Ø{d:g}" + (", with gussets" if spec.standoff_ribs and h >= 3 else ""))

    # Card guides: pairs of rails on the ±Y walls, a board standing between them across the box.
    if spec.card_slots:
        gap = spec.board_thickness + 2 * spec.fit_clearance
        rail_t, rail_d = 1.6, 2.5
        stop = top - (spec.lip + spec.fit_clearance + 0.5 if spec.lid in PLATE_LIDS else 0.0)
        rh = stop - spec.floor
        for x in spec.card_slots:
            for sy in (-1, 1):
                for sx in (-1, 1):
                    rail = Box(rail_t, rail_d, rh).locate(Location((x + sx * (gap / 2 + rail_t / 2), sy * (W / 2 - rail_d / 2), spec.floor + rh / 2)))
                    base += rail
            keep_out.append((x, 0, 0))
        notes.append(f"card guides at X {', '.join(f'{x:g}' for x in spec.card_slots)}: {gap:.2f} mm slots on the ±Y walls for a "
                     f"{spec.board_thickness:g} mm board {W - 2 * rail_d + 1.0:.1f} to {W - 0.6:.1f} mm wide (across Y), up to {rh:.1f} mm tall")
        for x in spec.card_slots:
            hits = [f"({kx:g}, {ky:g})" for kx, ky, kr in keep_out if kr > 0 and abs(kx - x) < kr + gap / 2 + 0.5]
            if hits:
                checks.append(f"a board in the card slot at X {x:g} would run into the standoffs or posts at {', '.join(hits)}")

    # Mounting ears.
    if spec.flange > 0:
        c, _, _, _, head = SCREWS[spec.flange_screw]
        ear_w = max(2.5 * c + 4, head + 6)
        for sx in (-1, 1):
            ear = Box(spec.flange + r_out, ear_w, spec.floor).locate(
                Location((sx * (oL / 2 + spec.flange / 2 - r_out / 2), 0, spec.floor / 2)))
            ear = fillet(ear.edges().filter_by(Axis.Z), min(ear_w / 2 - 0.01, 3))
            base += ear
            base -= Cylinder(c / 2, spec.floor * 3).locate(Location((sx * (oL / 2 + spec.flange / 2), 0, spec.floor / 2)))
        notes.append(f"mounting ears {spec.flange:g} mm out, {spec.flange_screw} clearance holes")

    # Gasket: a ledge inside the top of the walls for the cord to press on, the groove in the lid,
    # running inside the corner posts so the lid screws stay outside the seal.
    groove = None
    if spec.gasket:
        cd = spec.gasket
        gw, gd = round(1.4 * cd, 2), round(0.75 * cd, 2)  # face seal, about 25% squeeze
        off = post_boss + 0.6 + gw / 2  # groove centreline in from the inner walls
        ledge = off + gw / 2 + 1.5
        lh = max(gd + 3.0, 4.0)
        band = _rounded_box(L, W, lh, r_in, z0=top - lh)
        band -= _rounded_box(L - 2 * ledge, W - 2 * ledge, lh, max(r_in - ledge, 0.0), z0=top - lh)
        try:  # slope the ledge's underside so it prints without support
            low = band.edges().group_by(Axis.Z)[0]
            inner = [e for e in low if abs(e.center().X) < L / 2 - ledge + 0.05 and abs(e.center().Y) < W / 2 - ledge + 0.05]
            band = chamfer(inner, min(ledge, lh) - 0.6)
        except Exception:
            checks.append("gasket ledge: its underside is flat (print it with support, or upside down)")
        base += band
        cr = max(3 * cd, 2.0)  # cord bend radius
        gL, gW = L - 2 * off, W - 2 * off
        groove = (_rounded_box(gL + gw, gW + gw, gd, cr + gw / 2, z0=top)
                  - _rounded_box(gL - gw, gW - gw, gd, max(cr - gw / 2, 0.1), z0=top))
        notes.append(f"gasket: Ø{cd:g} mm cord in a {gw:g} x {gd:g} mm groove in the lid, pressing on a "
                     f"{ledge:.1f} mm ledge inside the walls; the lid screws sit outside the seal")
        # The ledge narrows the way in: a board has to pass it.
        gap_x, gap_y = L - 2 * ledge, W - 2 * ledge
        checks.append(f"gasket ledge: the opening past it is {gap_x:.1f} x {gap_y:.1f} mm, so a board and parts "
                      f"must fit through that")
        under = [f"({x:g}, {y:g})" for x, y in spec.standoffs if abs(x) > gap_x / 2 or abs(y) > gap_y / 2]
        if under:
            checks.append(f"standoffs at {', '.join(under)} are under the gasket ledge, which reaches {ledge:.1f} mm in "
                          f"from the walls: a board on them could not go in. Keep standoffs within "
                          f"±{gap_x / 2:.1f} x ±{gap_y / 2:.1f} mm, or make the box bigger")

    for hole in post_holes:  # after the gasket ledge, which covers the posts' tops
        base -= hole

    lid = None
    lip_c = spec.fit_clearance
    if spec.lid in PLATE_LIDS:
        lid = _rounded_box(oL, oW, spec.lid_thickness, r_out, z0=top)
        if spec.lip > 0 and not spec.gasket:
            lip = _rounded_box(L - 2 * lip_c, W - 2 * lip_c, spec.lip, max(r_in - lip_c, 0), z0=top - spec.lip)
            lip -= _rounded_box(L - 2 * lip_c - 2 * 1.6, W - 2 * lip_c - 2 * 1.6, spec.lip, max(r_in - lip_c - 1.6, 0),
                                z0=top - spec.lip)
            for x, y in posts:  # clear the corner posts
                lip -= Cylinder(post_boss / 2 + lip_c + 0.3, spec.lip * 2).locate(Location((x, y, top - spec.lip / 2)))
                lip -= Box(post_boss + 2 * lip_c, post_boss + 2 * lip_c, spec.lip * 2).locate(
                    Location((x + math.copysign(post_boss / 4, x), y + math.copysign(post_boss / 4, y), top - spec.lip / 2)))
            lid += lip
        if groove is not None:
            lid -= groove
        if spec.lid == "screw":
            c, _, _, _, head = SCREWS[spec.lid_screw]
            for x, y in posts:
                lid -= Cylinder(c / 2, spec.lid_thickness * 3).locate(Location((x, y, top + spec.lid_thickness / 2)))
                cb = spec.lid_thickness / 2  # counterbore the heads half the lid's thickness
                lid -= Cylinder(head / 2 + 0.3, cb).locate(Location((x, y, top + spec.lid_thickness - cb / 2)))
        if spec.lid in ("snap", "hinge", "living") and spec.lip > 0:
            rib, z_rib = 0.5, top - spec.lip + 1.0
            for sy in ((-1, 1) if spec.lid == "snap" else (-1,)):
                lid += Box(L * 0.6, rib * 2, 1.0).locate(Location((0, sy * (W / 2 - lip_c), z_rib)))
                base -= Box(L * 0.6 + 2, (rib + lip_c) * 2, 1.0 + 2 * lip_c).locate(Location((0, sy * W / 2, z_rib)))
            if spec.lid == "snap":
                notes.append("snap lid: a 0.5 mm rib on each long side clicks into a groove in the wall")
        if spec.lid == "hinge":
            lid, base = _hinge(spec, lid, base, top, oL, oW, notes, checks)
        notes.append(f"{spec.lid} lid, {spec.lid_thickness:g} mm"
                     + (f", {spec.lip:g} mm lip" if spec.lip and not spec.gasket else ""))
    elif spec.lid == "slide":
        t = spec.lid_thickness
        g = min(spec.wall / 2, 1.2)  # groove depth into each long wall
        z0 = base_h - 1.0 - t  # the panel's underside; 1 mm of wall above it
        for sy in (-1, 1):
            base -= Box(L + spec.wall + 1, 2 * g, t + 2 * lip_c).locate(Location((spec.wall / 2 + 0.5, sy * W / 2, z0 + t / 2)))
        base -= Box(2 * spec.wall + 2, W + 2 * g, base_h - z0 + lip_c + 1).locate(
            Location((oL / 2, 0, z0 - lip_c + (base_h - z0 + lip_c + 1) / 2)))
        lid = Box(L + spec.wall - lip_c, W + 2 * g - 2 * lip_c, t).locate(Location((spec.wall / 2 - lip_c / 2, 0, z0 + t / 2)))
        notes.append(f"slide lid: {t:g} mm panel in {g:g} mm grooves, slides in from the +X end")

    lid_top = (top + spec.lid_thickness) if spec.lid in PLATE_LIDS else None

    def cut(target, tool):
        nonlocal base, lid
        if target == "lid":
            if lid is None:
                raise ValueError("a lid cutout, vent or label needs a lid")
            lid = lid - tool
        else:
            base = base - tool

    # Dividers: walls across the inside, fixed or sliding into rails on the walls.
    divider_parts = []
    if spec.dividers:
        if spec.lid in PLATE_LIDS and spec.lip > 0 and not spec.gasket:
            full = top - spec.lip - spec.fit_clearance - 0.3  # clear of the lid's lip
        elif spec.lid == "slide":
            full = base_h - 1.0 - spec.lid_thickness - spec.fit_clearance  # under the sliding panel
        elif spec.gasket:
            full = top - max(0.75 * spec.gasket + 3.0, 4.0) - 0.3  # under the gasket ledge
        else:
            full = top - 0.3
        c = spec.fit_clearance
        # Where dividers cross: a removable plate passes a fixed wall through a slot in it; two
        # removable plates cross egg-crate style, each notched halfway.
        info = []
        for dv in spec.dividers:
            ax_, run_ = dv["axis"], (W if dv["axis"] == "x" else L)
            s0, s1 = (dv.get("span") or [-run_ / 2, run_ / 2])
            info.append((ax_, float(dv.get("at", 0)), float(dv.get("thickness") or spec.wall),
                         max(float(s0), -run_ / 2), min(float(s1), run_ / 2), bool(dv.get("removable"))))
        crossings = [(i, j) for i, a in enumerate(info) for j, b in enumerate(info)
                     if i < j and a[0] != b[0] and a[3] < b[1] < a[4] and b[3] < a[1] < b[4]]
        slots = []
        for i, j in crossings:
            for r, f in ((i, j), (j, i)):
                if info[r][5] and not info[f][5]:
                    slots.append((r, f))
        for i, dv in enumerate(spec.dividers):
            axis, at = dv["axis"], float(dv.get("at", 0))
            t = float(dv.get("thickness") or spec.wall)
            h_top = min(spec.floor + float(dv["height"]), full) if dv.get("height") else full
            run = W if axis == "x" else L  # the length it spans, wall to wall
            a0, a1 = (dv.get("span") or [-run / 2, run / 2])
            a0, a1 = max(float(a0), -run / 2), min(float(a1), run / 2)
            if a1 - a0 < 3:
                raise ValueError(f"divider {i + 1}: its span is under 3 mm")
            h = h_top - spec.floor
            mid = (a0 + a1) / 2
            notch = float(dv.get("notch") or 0)
            if dv.get("removable"):
                # Two rails on each wall it meets (only where the span reaches a wall), the plate its own part.
                gap, rail_t, rail_d = t + 2 * c, 1.6, 2.5
                ends = [e for e in (-1, 1) if abs((a1 if e > 0 else a0) - e * run / 2) < 1e-6]
                for e in ends:
                    for side in (-1, 1):
                        off = side * (gap / 2 + rail_t / 2)
                        if axis == "x":
                            r = Box(rail_t, rail_d, h).locate(Location((at + off, e * (W / 2 - rail_d / 2), spec.floor + h / 2)))
                        else:
                            r = Box(rail_d, rail_t, h).locate(Location((e * (L / 2 - rail_d / 2), at + off, spec.floor + h / 2)))
                        base += r
                plate_len = (a1 - a0) - 2 * c
                plate = Box(plate_len, t, h - c, align=(Align.CENTER, Align.CENTER, Align.MIN))
                if notch:
                    plate -= Pos(0, 0, h - c) * Cylinder(notch / 2, t * 4, rotation=(90, 0, 0))
                for a_, b_ in crossings:
                    if i not in (a_, b_):
                        continue
                    other = b_ if a_ == i else a_
                    if not info[other][5]:
                        continue
                    u = info[other][1] - mid  # where the other plate crosses, along this one
                    w_ = info[other][2] + 2 * c
                    z_ = (h - c) / 2
                    from_top = i == min(a_, b_)
                    plate -= Pos(u, 0, z_ if from_top else 0) * Box(w_, t * 3, (h - c) / 2 + 0.01 + (0.01 if from_top else 0),
                                                                     align=(Align.CENTER, Align.CENTER, Align.MIN))
                if (a1 - a0) > 30 and not notch:  # a finger hole to lift it out
                    plate -= Pos(plate_len / 4, 0, h - c - 6) * Cylinder(4.0, t * 4, rotation=(90, 0, 0))
                divider_parts.append((f"divider_{i + 1}", Rot(90, 0, 0) * plate))  # lying flat to print
                notes.append(f"divider {i + 1} (removable): a {t:g} mm plate {plate_len:.1f} x {h - c:.1f} mm sliding into rails "
                             f"at {axis.upper()} {at:g}" + (f", Ø{notch:g} mm cable gap on top" if notch else "") + "; print it flat")
            else:
                if axis == "x":
                    wall = Box(t, a1 - a0, h + 0.01).locate(Location((at, mid, spec.floor + h / 2 - 0.005)))
                else:
                    wall = Box(a1 - a0, t, h + 0.01).locate(Location((mid, at, spec.floor + h / 2 - 0.005)))
                if notch:
                    if axis == "x":
                        wall -= Pos(at, mid, h_top) * Cylinder(notch / 2, t * 4, rotation=(0, 90, 0))
                    else:
                        wall -= Pos(mid, at, h_top) * Cylinder(notch / 2, t * 4, rotation=(90, 0, 0))
                base += wall
                notes.append(f"divider {i + 1}: a {t:g} mm wall at {axis.upper()} {at:g}, {h:.1f} mm tall"
                             + (f", from {a0:g} to {a1:g}" if (a0, a1) != (-run / 2, run / 2) else "")
                             + (f", Ø{notch:g} mm cable gap on top" if notch else ""))
            # Anything it runs through: posts, standoffs.
            for kx, ky, kr in keep_out:
                d_ = abs((kx if axis == "x" else ky) - at)
                u = ky if axis == "x" else kx
                if kr > 0 and d_ < kr + t / 2 and a0 - kr < u < a1 + kr:
                    checks.append(f"divider {i + 1} runs through the post or standoff at ({kx:g}, {ky:g}): move it or shorten its span")
        for r, f in slots:  # a removable plate passes a fixed wall through a slot in it
            ax_r, at_r, t_r = info[r][0], info[r][1], info[r][2]
            at_f, t_f = info[f][1], info[f][2]
            hgt = full - spec.floor + 1
            if ax_r == "x":
                base -= Box(t_r + 2 * c, t_f + 0.4, hgt).locate(Location((at_r, at_f, spec.floor + hgt / 2 + 0.01)))
            else:
                base -= Box(t_f + 0.4, t_r + 2 * c, hgt).locate(Location((at_f, at_r, spec.floor + hgt / 2 + 0.01)))
            notes.append(f"divider {f + 1} has a slot where removable divider {r + 1} passes through it")
        if any(info[a][5] and info[b][5] for a, b in crossings):
            notes.append("crossing removable dividers are notched halfway, egg-crate style: the one notched from the top goes in first")
        sections = _sections(spec)
        if sections:
            notes.append("sections: " + ", ".join(f"{w:.1f} x {d:.1f} mm" for w, d in sections))

    # Cutouts.
    for raw in spec.cutouts:
        c = Cutout(**resolve(raw))
        if c.face in ("lid", "floor"):
            z = top if c.face == "lid" else 0.0
            cut("lid" if c.face == "lid" else "base",
                Pos(c.at[0], c.at[1], z) * _profile(c.shape, c.size, c.radius, 50.0))
        else:
            along, height = c.at
            cw = c.size[0]
            chh = c.size[1] if len(c.size) > 1 and c.shape != "round" else c.size[0]
            _span_check(spec, f"{c.preset or c.shape} hole on {c.face}", c.face, along, height, cw, chh, checks)
            tool = _profile(c.shape, c.size, c.radius, spec.wall * 4, spec.teardrop and c.shape == "round")
            cut("base", _on_wall(tool, c.face, along, spec.floor + height, oL, oW))
            if c.preset in GLANDS:
                # A gland's locknut needs room inside: about 1.5 x the hole across its corners.
                nut_r = 0.75 * c.size[0]
                wx = {"-X": -L / 2, "+X": L / 2}.get(c.face)
                wy = {"-Y": -W / 2, "+Y": W / 2}.get(c.face)
                px, py = (wx, along) if wx is not None else (along, wy)
                for kx, ky, kr in keep_out:
                    if math.hypot(kx - px, ky - py) < nut_r + kr + 2 and spec.floor + height - nut_r < spec.floor + spec.standoff_height + 1:
                        checks.append(f"{c.preset} on {c.face}: its locknut (about Ø{2 * nut_r:.0f}) may hit the post or standoff at ({kx:g}, {ky:g})")
                if height - nut_r < 0 or height + nut_r > H:
                    checks.append(f"{c.preset} on {c.face}: its locknut (about Ø{2 * nut_r:.0f}) runs into the floor or lid")
        if c.preset == "iec-c14" and not 1.0 <= spec.wall <= 3.0 and c.face not in ("lid", "floor"):
            checks.append(f"iec-c14 on {c.face}: snap-in inlets are made for 1 to 3 mm panels; this wall is {spec.wall:g} mm "
                          f"(use a screw-mount inlet, or thin the wall there)")
        if c.preset in FANS:
            notes.append(f"{c.preset} on {c.face}: fan the right way round (air direction is moulded on its frame); "
                         f"screw holes Ø{FANS[c.preset][1]:g} for the fan's screws")
        label = c.preset or f"{c.shape} {'x'.join(f'{v:g}' for v in c.size)}"
        notes.append(f"cutout {c.face} {label} at {c.at}" + (f" ({c.source})" if c.source else ""))

    # Windows: an opening, and behind it a recess for a clear panel or display, glued in from inside.
    for wdw in spec.windows:
        face = face_name(wdw["face"])
        (w, h), (a, b) = wdw["size"], wdw.get("at", [0, 0])
        pw, ph = wdw.get("panel", [w + 4, h + 4])
        pt = wdw.get("panel_t", 1.0)
        r = wdw.get("radius", 1.0)
        if face == "lid":
            cut("lid", Pos(a, b, top) * _profile("rect", [w, h], r, 50.0))
            # The recess from the lid's underside (the lip, if any, is cut away inside it too).
            cut("lid", Pos(a, b, top - 25 + pt) * _profile("rect", [pw, ph], min(r + 1, 2), 50.0))
        else:
            cut("base", _on_wall(_profile("rect", [w, h], r, spec.wall * 4), face, a, spec.floor + b, oL, oW))
            inward = {"-X": (1, 0), "+X": (-1, 0), "-Y": (0, 1), "+Y": (0, -1)}[face]
            pocket = _on_wall(_profile("rect", [pw, ph], min(r + 1, 2), 2 * spec.wall), face, a, spec.floor + b, oL, oW)
            pocket = Pos(inward[0] * (spec.wall + (spec.wall - pt)), inward[1] * (spec.wall + (spec.wall - pt)), 0) * pocket
            cut("base", pocket)
        notes.append(f"window on {face}: {w:g} x {h:g} mm opening, {pw:g} x {ph:g} x {pt:g} mm recess behind it for the panel")
        if wdw.get("print_panel"):
            c_ = spec.fit_clearance
            divider_parts.append((f"window_panel_{len([1 for n, _ in divider_parts if n.startswith('window')]) + 1}",
                                  Box(pw - 2 * c_, ph - 2 * c_, pt, align=(Align.CENTER, Align.CENTER, Align.MIN))))
            notes.append("   its panel prints as its own part: use clear PETG or PC, 100% infill, and glue it in from inside")

    # Vents: slots filling an area, upright on walls, along Y on the lid or floor.
    for v in spec.vents:
        face = face_name(v["face"])
        (w, h), (a, b) = v["size"], v.get("at", [0, 0])
        if v.get("pattern") == "honeycomb":
            cells = _honeycomb(w, h, v.get("cell", 4.0), v.get("web", 1.2))
            _span_check(spec, f"vent on {face}", face, a, b, w, h, checks)
            thick = 50.0 if face in ("lid", "floor") else spec.wall * 4
            hexagon = extrude(RegularPolygon(v.get("cell", 4.0) / 2, 6, major_radius=False), amount=thick / 2, both=True)
            tools = [Pos(a + cx, b + cy, 0) * hexagon for cx, cy in cells]
            if not tools:
                raise ValueError("honeycomb vent: the area is smaller than one cell")
            tool = tools[0].fuse(*tools[1:]) if len(tools) > 1 else tools[0]
            if face in ("lid", "floor"):
                cut("lid" if face == "lid" else "base", Pos(0, 0, top if face == "lid" else 0.0) * tool)
            else:
                # Built in the wall's own (along, up) plane, then turned onto the wall.
                tool = Pos(-a, -b, 0) * tool
                cut("base", _on_wall(tool, face, a, spec.floor + b, oL, oW))
            notes.append(f"honeycomb vent on {face}: {len(cells)} hexagons {v.get('cell', 4.0):g} mm across the flats, "
                         f"{v.get('web', 1.2):g} mm between them, {_hex_area(v.get('cell', 4.0)) * len(cells):.0f} mm² open")
            continue
        slot, pitch = v.get("slot", 2.0), v.get("pitch", 4.0)
        _span_check(spec, f"vent on {face}", face, a, b, w, h, checks)
        n = max(1, int((w - slot) // pitch) + 1)
        start = a - (n - 1) * pitch / 2
        for i in range(n):
            u = start + i * pitch
            tool = _profile("rect", [slot, h], slot / 2 - 0.01, 50.0 if face in ("lid", "floor") else spec.wall * 4)
            if face in ("lid", "floor"):
                cut("lid" if face == "lid" else "base", Pos(u, b, top if face == "lid" else 0.0) * tool)
            else:
                cut("base", _on_wall(tool, face, u, spec.floor + b, oL, oW))
        notes.append(f"vent on {face}: {n} slots {slot:g} x {h:g} mm, {pitch:g} mm apart")

    # Feet: locating recesses for stick-on rubber feet.
    if spec.feet:
        r = spec.feet / 2
        ix, iy = oL / 2 - r - 3, oW / 2 - r - 3
        for sx in (-1, 1):
            for sy in (-1, 1):
                base -= Cylinder(r + 0.3, spec.feet_depth * 2).locate(Location((sx * ix, sy * iy, 0)))
        notes.append(f"4 recesses {spec.feet_depth:g} mm deep for Ø{spec.feet:g} rubber feet")

    # Keyholes: hang the box on two screws through the floor; the slots run toward +Y (up on the wall).
    if spec.keyholes:
        c, _, _, _, head = SCREWS[spec.keyholes]
        span = spec.keyhole_spacing or 0.6 * L
        big, slot_len = head + 1.0, head + 1.0
        for sx in (-1, 1):
            x = sx * span / 2
            base -= Cylinder(big / 2, spec.floor * 3).locate(Location((x, 0, spec.floor / 2)))
            base -= Box(c + 0.4, slot_len, spec.floor * 3).locate(Location((x, slot_len / 2, spec.floor / 2)))
            base -= Cylinder((c + 0.4) / 2, spec.floor * 3).locate(Location((x, slot_len, spec.floor / 2)))
            for kx, ky, kr in keep_out:
                if abs(kx - x) < kr + big / 2 + 1 and -big / 2 - kr - 1 < ky < slot_len + kr + 1:
                    checks.append(f"keyhole at x={x:g} runs under the post or standoff at ({kx:g}, {ky:g})")
        notes.append(f"2 keyholes for {spec.keyholes} screws {span:g} mm apart; hang with the floor to the wall, +Y up")

    # DIN rail clip under the floor: a fixed hook on +Y and a sprung latch on -Y.
    if spec.din_rail:
        base += din_clip(oL)
        notes.append("DIN rail clip (TS35, rail along X): hook on +Y, sprung latch on -Y; print a test first")

    # Labels and icons: raised (depth > 0) or recessed (depth < 0). With two_color, each becomes its own
    # body (an inlay filling the recess, or the raised mark) for a second filament.
    inlays = []

    def mark(body, face, a, b, depth, name, host_for_lid=True):
        nonlocal base, lid
        if face == "lid":
            z = lid_top if depth > 0 else lid_top - abs(depth)
            placed = Pos(a, b, z) * body
            if depth > 0:
                lid = lid + placed if not spec.two_color else lid
            else:
                lid = lid - placed
            host = "lid"
        else:
            # Upright on the wall, reading from outside; the extrusion points out of the wall.
            turn = {"-Y": 0, "+Y": 180, "-X": -90, "+X": 90}[face]
            out = {"-Y": (0, -1), "+Y": (0, 1), "-X": (-1, 0), "+X": (1, 0)}[face]
            right = {"-Y": (1, 0), "+Y": (-1, 0), "-X": (0, -1), "+X": (0, 1)}[face]
            half = (oL / 2) if face in ("-X", "+X") else (oW / 2)
            inset = 0.0 if depth > 0 else -abs(depth)  # recessed marks start inside the wall
            x = out[0] * (half + inset) + right[0] * a
            y = out[1] * (half + inset) + right[1] * a
            placed = Pos(x, y, spec.floor + b) * (Rot(0, 0, turn) * (Rot(90, 0, 0) * body))
            if depth > 0:
                base = base + placed if not spec.two_color else base
            else:
                base = base - placed
            host = "base"
        if spec.two_color:
            inlays.append((name, placed, host))

    for i, t in enumerate(spec.labels):
        face = face_name(t["face"])
        size, depth = t.get("size", 6.0), t.get("depth", -0.6)
        a, b = t.get("at", [0, 0])
        from build123d import FontStyle
        txt = Text(t["text"], size, align=(Align.CENTER, Align.CENTER),
                   font_style=FontStyle.BOLD if t.get("bold") else FontStyle.REGULAR)
        body = extrude(txt, amount=abs(depth))
        if t.get("rotate"):
            body = Rot(0, 0, float(t["rotate"])) * body
        mark(body, face, a, b, depth, f"label_{i + 1}")
        notes.append(f"label {t['text']!r} on {face}, {'raised' if depth > 0 else 'recessed'} {abs(depth):g} mm"
                     + (f", turned {float(t['rotate']):g}°" if t.get("rotate") else ""))

    for i, g in enumerate(spec.art):
        from .art import solid as art_solid
        face = face_name(g["face"])
        depth = float(g.get("depth", -0.6))
        width = float(g.get("width", 30.0))
        body, (w_, h_) = art_solid(g["data"], g.get("kind", "svg"), width, abs(depth), float(g.get("line", 0.8)))
        if g.get("rotate"):
            body = Rot(0, 0, float(g["rotate"])) * body
        a, b = g.get("at", [0, 0])
        mark(body, face, a, b, depth, f"art_{i + 1}")
        notes.append(f"artwork {g.get('name') or i + 1} on {face}: {w_:.1f} x {h_:.1f} mm, {'raised' if depth > 0 else 'engraved'} "
                     f"{abs(depth):g} mm" + (f", turned {float(g['rotate']):g}°" if g.get("rotate") else ""))
        if min(w_, h_) < 4:
            checks.append(f"artwork {g.get('name') or i + 1} is under 4 mm one way: fine details under about 0.8 mm won't print")

    if spec.icons:
        from .icons import icon_for, icon_shape
        n_icons = 0
        for raw in spec.cutouts:
            c = Cutout(**resolve(raw))
            name = raw.get("icon") or icon_for(c.preset)
            if not name or name == "none":
                continue
            size = 6.0
            depth = -0.6 if spec.icon_style == "engraved" else 0.6
            hole_h = c.size[1] if c.shape == "rect" else c.size[0]
            if c.face in ("lid", "floor"):
                if c.face == "floor":
                    continue
                a, b = c.at[0], c.at[1] + hole_h / 2 + size / 2 + 2.5
            else:
                along, height = c.at
                b = height + hole_h / 2 + size / 2 + 2.5
                if spec.floor + b + size / 2 > base_h - (spec.lip if spec.lid in PLATE_LIDS else 0) - 1:
                    b = height - hole_h / 2 - size / 2 - 2.5  # no room above: below it
                a = along * {"-Y": 1, "+Y": -1, "-X": -1, "+X": 1}[c.face]
            mark(extrude(icon_shape(name, size), amount=abs(depth)), c.face, a, b, depth, f"icon_{name}_{n_icons + 1}")
            n_icons += 1
        if n_icons:
            notes.append(f"{n_icons} icon{'s' if n_icons > 1 else ''} beside the holes, {spec.icon_style} 0.6 mm")
    if spec.two_color and inlays:
        notes.append(f"two colours: {len(inlays)} label/icon bod{'ies' if len(inlays) != 1 else 'y'} {'are' if len(inlays) != 1 else 'is'} separate in the 3MF; give them the second filament "
                     "(in Bambu Studio, select them and pick the filament)")

    # Posts under the lid, for a display or button board mounted behind it.
    if spec.lid_standoffs and lid is not None:
        d, depth = spec.hole(spec.lid_standoff_screw, "tap")
        boss = _post_boss(spec, d)
        hgt = spec.lid_standoff_height
        for x, y in spec.lid_standoffs:
            if abs(x) + boss / 2 > L / 2 - spec.fit_clearance - 1.6 or abs(y) + boss / 2 > W / 2 - spec.fit_clearance - 1.6:
                checks.append(f"lid standoff at ({x:g}, {y:g}) runs into the lid's lip or the walls")
            lid += Cylinder(boss / 2, hgt + 0.01).locate(Location((x, y, top - hgt / 2 + 0.005)))
            lid -= Cylinder(d / 2, hgt + spec.lid_thickness - 0.8).locate(Location((x, y, top - hgt + (hgt + spec.lid_thickness - 0.8) / 2)))
        notes.append(f"{len(spec.lid_standoffs)} posts {hgt:g} mm down from the lid, tapped for {spec.lid_standoff_screw} "
                     f"(Ø{d:g}), for a board behind the lid")
        room = (top - hgt) - (spec.floor + spec.standoff_height + 1.6) if spec.standoffs else None
        if room is not None and room < 8:
            checks.append(f"only {room:.1f} mm between the main board's top and the lid posts' ends: little room for "
                          f"parts on either board")

    # Battery cradles on the floor: low walls round the cells, low ribs between them.
    for bt in spec.batteries:
        dia, length = CELLS[bt["cell"]]
        n, (bx, by), axis = int(bt.get("count", 1)), bt.get("at", [0, 0]), bt.get("axis", "x")
        inner_len, inner_w = length + CONTACT_ROOM, n * (dia + 0.4)
        wall_h, t_w = round(0.6 * dia, 1), 1.6
        ox, oy = (inner_len, inner_w) if axis == "x" else (inner_w, inner_len)
        if abs(bx) + ox / 2 + t_w > L / 2 or abs(by) + oy / 2 + t_w > W / 2:
            raise ValueError(f"the {n} x {bt['cell']} cradle at ({bx:g}, {by:g}) does not fit inside the walls")
        ring = Box(ox + 2 * t_w, oy + 2 * t_w, wall_h).locate(Location((bx, by, spec.floor + wall_h / 2)))
        ring -= Box(ox, oy, wall_h + 1).locate(Location((bx, by, spec.floor + wall_h / 2)))
        rib_h = round(0.35 * dia, 1)
        for i in range(1, n):
            off = -inner_w / 2 + i * (dia + 0.4)
            rib = Box(inner_len - 2 * CONTACT_ROOM, 1.0, rib_h) if axis == "x" else Box(1.0, inner_len - 2 * CONTACT_ROOM, rib_h)
            ring += rib.locate(Location((bx + (0 if axis == "x" else off), by + (off if axis == "x" else 0), spec.floor + rib_h / 2)))
        base += ring
        hits = sorted({f"({kx:g}, {ky:g})" for kx, ky, kr in keep_out
                       if kr > 0 and abs(kx - bx) < ox / 2 + t_w + kr and abs(ky - by) < oy / 2 + t_w + kr})
        if hits:
            checks.append(f"the {bt['cell']} cradle at ({bx:g}, {by:g}) runs into the standoffs or posts at {', '.join(hits)}")
        notes.append(f"cradle for {n} x {bt['cell']} ({dia:g} x {length:g} mm cells) at ({bx:g}, {by:g}) along {axis.upper()}, "
                     f"{inner_len:g} mm long inside with {CONTACT_ROOM:g} mm for the contacts: add your spring contacts")

    # Zip-tie anchors: a bridge on the floor a tie threads under (for ties up to 4.8 mm wide).
    for tx, ty in spec.tie_points:
        span, gap_h, post = 5.2, 2.2, 2.0
        bridge = Box(span + 2 * post, 3.0, gap_h + 1.6).locate(Location((tx, ty, spec.floor + (gap_h + 1.6) / 2)))
        bridge -= Box(span, 4.0, gap_h).locate(Location((tx, ty, spec.floor + gap_h / 2)))
        base += bridge
    if spec.tie_points:
        notes.append(f"{len(spec.tie_points)} zip-tie anchors (ties up to 4.8 mm wide)")

    # Cable notches: a U in the top of a wall, closed by the lid; fit a grommet or seal with the cable.
    for cn in spec.cable_notches:
        face = face_name(cn["face"])
        d, a = cn["d"], cn.get("at", 0.0)
        depth = cn.get("depth", d)
        tool = Box(d, depth + 1, spec.wall * 4)
        tool = tool + Cylinder(d / 2, spec.wall * 4).locate(Location((0, -(depth + 1) / 2, 0)))
        cut("base", _on_wall(Pos(0, (depth + 1) / 2 - (depth + 1) / 2, 0) * tool, face, a, top - (depth + 1) / 2 + 0.5, oL, oW))
        notes.append(f"cable notch {d:g} mm wide in the top of the {face} wall at {a:g}")

    # Light pipes: a tube from the lid down to just above each LED, the pipe or a clear rod inside.
    if spec.light_pipes and lid is not None:
        board_top = spec.floor + spec.standoff_height + spec.board_thickness
        for lp in spec.light_pipes:
            (x, y), d = lp.get("at", [0, 0]), lp.get("d", 3.0)
            gap = lp.get("gap", 1.0)
            length = top - (board_top + gap)
            if length < 1.0:
                checks.append(f"light pipe at ({x:g}, {y:g}): no room between the board and the lid")
                continue
            lid += Cylinder(d / 2 + 1.2, length).locate(Location((x, y, top - length / 2)))
            lid -= Cylinder(d / 2 + 0.1, length + spec.lid_thickness + 2).locate(Location((x, y, top + spec.lid_thickness / 2 - length / 2)))
            for kx, ky, kr in keep_out:
                if math.hypot(kx - x, ky - y) < kr + d / 2 + 1.2:
                    checks.append(f"light pipe at ({x:g}, {y:g}) is over the standoff or post at ({kx:g}, {ky:g})")
        notes.append(f"{len(spec.light_pipes)} light pipe tubes from the lid to {spec.light_pipes[0].get('gap', 1.0):g} mm "
                     f"above the board (a {spec.board_thickness:g} mm board on {spec.standoff_height:g} mm standoffs): "
                     f"fit a light pipe or clear rod of the pipe's diameter")

    # What will print badly.
    for name, v in (("wall", spec.wall), ("floor", spec.floor), ("lid", spec.lid_thickness if lid is not None else 9)):
        if v < 1.2:
            checks.append(f"{name} {v:g} mm: under three 0.4 mm lines, it will be weak and may leak light")
    flat = []
    for raw in spec.cutouts:
        c = Cutout(**resolve(raw))
        if c.face in WALLS and c.shape == "rect" and c.size[0] > 10:
            flat.append(f"{c.face} {c.size[0]:g} mm")
        if c.face in WALLS and c.shape == "round" and not spec.teardrop and c.size[0] > 8:
            flat.append(f"{c.face} Ø{c.size[0]:g} hole")
    for wdw in spec.windows:
        if face_name(wdw["face"]) in WALLS and wdw["size"][0] > 10:
            flat.append(f"{face_name(wdw['face'])} window {wdw['size'][0]:g} mm")
    if flat:
        checks.append("printing upright, these openings have flat tops to bridge or support: " + ", ".join(flat))
    for t in spec.labels:
        if t.get("depth", -0.6) > 0 and t.get("size", 6.0) < 4:
            checks.append(f"raised text {t['text']!r} under 4 mm tall may not print cleanly")

    # Support enforcers: the flat-topped wall openings, as blocks a slicer can use to force support there.
    supports = []
    for raw in spec.cutouts:
        c = Cutout(**resolve(raw))
        if c.face in WALLS and ((c.shape == "rect" and c.size[0] > 10) or (c.shape == "round" and not spec.teardrop and c.size[0] > 8)):
            w = c.size[0]
            h = c.size[1] if c.shape == "rect" else c.size[0]
            supports.append(_on_wall(Box(w - 0.4, h - 0.4, spec.wall), c.face, c.at[0], spec.floor + c.at[1], oL, oW))
    for wdw in spec.windows:
        face = face_name(wdw["face"])
        if face in WALLS and wdw["size"][0] > 10:
            (w, h), (a, b) = wdw["size"], wdw.get("at", [0, 0])
            supports.append(_on_wall(Box(w - 0.4, h - 0.4, spec.wall), face, a, spec.floor + b, oL, oW))
    # Shift each block inward by half a wall so it sits in the wall, not outside it.
    placed = []
    for blk in supports:
        bb = blk.bounding_box()
        cx, cy = (bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2
        dx = -math.copysign(spec.wall / 2, cx) if abs(abs(cx) - oL / 2) < 0.01 else 0.0
        dy = -math.copysign(spec.wall / 2, cy) if abs(abs(cy) - oW / 2) < 0.01 else 0.0
        placed.append(Pos(dx, dy, 0) * blk)
    print_plan = {
        "base": "opening up, as modelled" + ("; support the flat-topped wall openings (support_enforcers.stl marks them)" if placed else ", no supports"),
        "lid": None if lid is None else (
            "top face down (the STL is flipped that way)" + ("; raised text on top would be on the bed: recess it, or print top up with supports"
                                                              if any(t.get("depth", -0.6) > 0 and face_name(t.get("face", "")) == "lid" for t in spec.labels) else "")),
    }
    if spec.lid == "slide":
        print_plan["lid"] = "flat on the bed"

    # Temperature rise, roughly: still air round a plastic box, plus air through the vents by chimney effect.
    thermal = None
    if spec.power_w > 0:
        oH = base_h + (spec.lid_thickness if lid is not None else 0)
        area = 2 * (oL * oW + oL * oH + oW * oH) / 1e6  # m2
        hcoef = 6.0  # W/m2K: natural convection and radiation, a rough figure for a plastic box in still air
        vent_area, zs = 0.0, []
        for v in spec.vents:
            (w, h), slot, pitch = v["size"], v.get("slot", 2.0), v.get("pitch", 4.0)
            if v.get("pattern") == "honeycomb":
                vent_area += len(_honeycomb(w, h, v.get("cell", 4.0), v.get("web", 1.2))) * _hex_area(v.get("cell", 4.0)) / 1e6
            else:
                n = max(1, int((w - slot) // pitch) + 1)
                vent_area += n * slot * h / 1e6
            zs.append(v.get("at", [0, 0])[1] if face_name(v["face"]) in WALLS else (base_h if face_name(v["face"]) == "lid" else 0.0))
        stack = max((max(zs) - min(zs)) / 1000, base_h / 2000) if zs else 0.0
        fans = [c for c in spec.cutouts if str(c.get("preset", "")).startswith("fan-")]
        forced = spec.fan_flow_cfm * 0.000471947 if fans and spec.fan_flow_cfm > 0 else 0.0  # m3/s

        def removed(dt):
            air = 0.0
            if forced:
                return hcoef * area * dt + 1.2 * 1005 * forced * dt
            if vent_area > 0:
                q = 0.6 * (vent_area / 2) * math.sqrt(max(2 * 9.81 * stack * dt / 300.0, 0.0))
                air = 1.2 * 1005 * q * dt
            return hcoef * area * dt + air
        lo, hi = 0.0, 500.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if removed(mid) < spec.power_w else (lo, mid)
        dt = round(hi, 1)
        sealed = round(spec.power_w / (hcoef * area), 1)
        thermal = {"power_w": spec.power_w, "rise_c": dt, "sealed_rise_c": sealed, "vent_area_mm2": round(vent_area * 1e6),
                   "note": "rough: still air, even heat; a hot part runs hotter than the air inside"}
        notes.append(f"{spec.power_w:g} W inside: the air inside runs about {dt:g} °C above the room"
                     + (f" with the fan moving {spec.fan_flow_cfm:g} CFM" if forced else "")
                     + (f" ({sealed:g} °C if it were sealed)" if vent_area or forced else " (no vents)"))
        thermal["fan_cfm"] = spec.fan_flow_cfm if forced else 0
        if dt > 15:
            checks.append(f"about {dt:g} °C above the room with {spec.power_w:g} W: add vents low and high (a chimney), "
                          f"make the box bigger, or move heat out through a metal panel")

    # Fan layout: air should come in on one side and leave across the box, not short-circuit.
    fans = [c for c in spec.cutouts if str(c.get("preset", "")).startswith("fan-")]
    if fans:
        opposite = {"-X": "+X", "+X": "-X", "-Y": "+Y", "+Y": "-Y", "lid": "floor", "floor": "lid"}
        outlets = [face_name(v["face"]) for v in spec.vents] + [face_name(c["face"]) for c in spec.cutouts
                                                                  if not str(c.get("preset", "")).startswith("fan-")
                                                                  and "screw hole" not in str(c.get("source", ""))]
        for f_ in fans:
            fa = face_name(f_["face"])
            if not outlets:
                checks.append(f"the fan on {fa} has nowhere for the air to go: add vents, ideally on {opposite[fa]}")
            elif opposite[fa] not in outlets:
                checks.append(f"the fan on {fa} has no vents across from it ({opposite[fa]}): the air takes the short way out and "
                              "misses most of the board")
            else:
                notes.append(f"fan on {fa}, vents on {opposite[fa]}: air crosses the box")
        if spec.power_w > 0 and spec.fan_flow_cfm <= 0:
            checks.append("give the fan's airflow (fan_flow_cfm, from its datasheet; about a third of it is realistic "
                          "against vents and a board) to count it in the temperature estimate")

    extras = list(divider_parts)  # other printed parts: dividers, a battery door, clamp bars, a wall bracket

    # Handheld: a lanyard loop on the -X wall near the top, a belt clip and a handle (their own parts).
    if spec.lanyard:
        lz = base_h - 8.0
        # Near a corner of the -X wall, else the +X wall: where the wall behind it is whole.
        for sx, yy in ((-1, W / 2 - 8), (-1, -W / 2 + 8), (1, W / 2 - 8), (1, -W / 2 + 8)):
            tab = Box(6.4, 10.0, 9.0).locate(Location((sx * (oL / 2 + 3.0 - 0.2), yy, lz)))
            tab -= Pos(sx * (oL / 2 + 3.0), yy, lz) * Cylinder(1.75, 12, rotation=(90, 0, 0))
            trial = base + tab
            if len(trial.solids()) == len(base.solids()):
                base = trial
                notes.append(f"lanyard loop on the {'+' if sx > 0 else '-'}X wall: a Ø3.5 mm hole for the cord")
                break
        else:
            checks.append("lanyard loop: no solid wall near the top corners to put it on")
    if spec.belt_clip:
        cw, cl = min(30.0, W * 0.6), min(60.0, L * 0.8)
        m_ = "M3"
        for sx in (-1, 1):
            base -= Pos(sx * cl / 4, 0, 0) * Cylinder(SCREWS[m_][0] / 2, spec.floor * 3)
        clip = Box(cl, cw, 2.5, align=(Align.CENTER, Align.CENTER, Align.MIN))  # the pad on the floor
        for sx in (-1, 1):
            clip -= Pos(sx * cl / 4, 0, 0) * Cylinder(SCREWS[m_][0] / 2, 10)
        tongue_l = cl * 0.9
        clip += Pos(-cl / 2 + 6, 0, 0) * Box(6, cw, 6.5, align=(Align.MAX, Align.CENTER, Align.MIN))  # the spine
        clip += Pos(-cl / 2, 0, 4.5) * Box(tongue_l, cw, 2.2, align=(Align.MIN, Align.CENTER, Align.MIN))  # the tongue
        clip += Pos(-cl / 2 + tongue_l - 3, 0, 4.5) * Box(3, cw, 1.2, align=(Align.MIN, Align.CENTER, Align.MAX))  # a bump
        extras.append(("belt_clip", clip))
        notes.append(f"belt clip: its own part, two M3 screws through the floor {cl / 2:g} mm apart (nuts inside); print it on its side")
    handles = list(spec.handles) + ([{"face": "lid", "type": "bar"}] if spec.handle else [])
    mounted = []  # screw-on parts where they go, for the preview
    for i, hd in enumerate(handles):
        extras_h, notes_h, base, lid, mounted_h = _handle(spec, hd, i, base, lid, top, oL, oW, base_h, checks)
        mounted += mounted_h
        extras += extras_h
        notes += notes_h

    # Magnets: a lid held shut by them, and pockets wherever asked.
    if mag_lid:
        base, lid = _magnet_lid(spec, mag_lid, base, lid, posts, top, notes, checks)
    for i, mg in enumerate(spec.magnets):
        base, lid = _magnet(spec, mg, i, base, lid, top, oL, oW, notes, checks)

    # Grounding: a boss for a ground lug, and where copper tape would shield the inside.
    if spec.ground_lug:
        gx, gy = spec.ground_lug
        m_ = "M3"
        d_ins, dep = spec.hole(m_, "insert")
        base += Pos(gx, gy, spec.floor) * Cylinder(d_ins / 2 + 2.2, 6.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        base -= Pos(gx, gy, spec.floor + 6.0 - dep) * Cylinder(d_ins / 2, dep + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
        notes.append(f"ground lug boss at ({gx:g}, {gy:g}): an M3 insert for a ring terminal with a star washer; run the "
                     "earth and any shield tape to it")
    if spec.shielding:
        inside = 2 * (L + W) * H + L * W + (L * W if lid is not None else 0)
        notes.append(f"shielding: about {inside / 100:.0f} cm² of inside surface to cover with copper tape (conductive adhesive), "
                     "overlapped 5 mm at the seams; carry it over the lid's lip or use gasket fingers so the lid touches it; "
                     "bond it to the ground lug. Holes bigger than about 1/20 of the wavelength you care about leak "
                     "(15 mm at 1 GHz)")


    # Battery door: an opening in the floor, a rebate round it for a flush door, two screw bosses inside.
    if spec.battery_door:
        bd = spec.battery_door
        (w, l), (x, y) = bd["size"], bd.get("at", [0, 0])
        m = bd.get("screw", "M2")
        ledge, dt = 4.0, spec.floor - 0.8
        pilot = SCREWS[m][1]
        base -= Pos(x, y, 0) * Box(w, l, spec.floor * 3)
        base -= Pos(x, y, 0) * Box(w + 2 * ledge, l + 2 * ledge, 2 * dt)
        bosses = [(x - w / 2 - ledge / 2, y), (x + w / 2 + ledge / 2, y)]
        for bx, by in bosses:
            base += Pos(bx, by, spec.floor) * Cylinder(pilot / 2 + 1.6, 5.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
            base -= Pos(bx, by, dt) * Cylinder(pilot / 2, 5.0 + spec.floor, align=(Align.CENTER, Align.CENTER, Align.MIN))
        c = spec.fit_clearance
        door = Box(w + 2 * ledge - 2 * c, l + 2 * ledge - 2 * c, dt, align=(Align.CENTER, Align.CENTER, Align.MIN))
        for bx, by in bosses:
            door -= Pos(bx - x, by - y, 0) * Cylinder(SCREWS[m][0] / 2, dt * 3)
        door -= Pos(0, (l + 2 * ledge) / 2 - 3, 0) * Box(8, 1.2, 0.8, align=(Align.CENTER, Align.CENTER, Align.MIN))  # a fingernail slot
        extras.append(("battery_door", door))
        if dt < 1.0:
            checks.append(f"battery door: a {spec.floor:g} mm floor leaves a {dt:.1f} mm door; make the floor 2 mm or more")
        if abs(x) + w / 2 + ledge + 3 > L / 2 or abs(y) + l / 2 + ledge > W / 2:
            checks.append("battery door: the opening and its ledge run into the walls")
        notes.append(f"battery door: {w:g} x {l:g} mm opening in the floor, a {dt:.1f} mm door flush in a {ledge:g} mm rebate, "
                     f"two {m} screws into bosses inside (print the door flat)")

    # Strain relief: the cable passes a hole in the wall and is clamped under a bar on two posts.
    for i, sr in enumerate(spec.strain_reliefs):
        face, d = face_name(sr["face"]), float(sr.get("d", 6.0))
        along, height = sr.get("at", [0, d / 2 + 2])
        if face not in WALLS:
            raise ValueError("strain relief: on a wall")
        cut("base", _on_wall(_profile("round", [d + 0.8], 0, spec.wall * 4, spec.teardrop), face, along, spec.floor + height, oL, oW))
        inward = {"-X": (1, 0), "+X": (-1, 0), "-Y": (0, 1), "+Y": (0, -1)}[face]
        across = (abs(inward[1]), abs(inward[0]))  # along the wall
        wall_pos = {"-X": -L / 2, "+X": L / 2, "-Y": -W / 2, "+Y": W / 2}[face]
        depth_in = 10.0
        cx = (wall_pos + inward[0] * depth_in) if face in ("-X", "+X") else along
        cy = (wall_pos + inward[1] * depth_in) if face in ("-Y", "+Y") else along
        span = d / 2 + 4.0
        post_top = height + d / 2 - 0.2 * d  # the bar's underside: it pinches a fifth of the cable
        m = "M3"
        posts = [(cx + across[0] * s * span, cy + across[1] * s * span) for s in (-1, 1)]
        for px, py in posts:
            base += Pos(px, py, spec.floor) * Cylinder(3.5, post_top, align=(Align.CENTER, Align.CENTER, Align.MIN))
            base -= Pos(px, py, spec.floor + post_top - 6) * Cylinder(SCREWS[m][1] / 2, 7, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if height - d / 2 > 0.6:  # a saddle under the cable
            saddle = Box(6 if face in ("-Y", "+Y") else 6, 6, height - d / 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
            base += Pos(cx, cy, spec.floor) * saddle
        bar_len = 2 * span + 7
        bar = Box(bar_len, 7, 3, align=(Align.CENTER, Align.CENTER, Align.MIN))
        for s_ in (-1, 1):
            bar -= Pos(s_ * span, 0, 0) * Cylinder(SCREWS[m][0] / 2, 10)
        extras.append((f"cable_clamp_{i + 1}", bar))
        keep_out += [(px, py, 3.5) for px, py in posts]
        notes.append(f"strain relief on {face}: a Ø{d + 0.8:g} mm hole for a Ø{d:g} mm cable, clamped {depth_in:g} mm inside "
                     f"under a bar on two posts (M3 self-tapping); the bar is its own part")

    # Wall bracket: a French cleat. The rail under the floor (along X) hooks over the bracket's lip.
    if spec.wall_bracket:
        rail_h, rail_w = 5.0, 10.0
        y_rail = W / 4
        # Its underside slopes down toward the wall at 45°, so it hooks behind the bracket's bevelled lip.
        prof = Polygon((0, 0), (rail_w, 0), (rail_w, -rail_h), (-rail_h, -rail_h), align=None)
        rail = extrude(Plane.YZ * prof, amount=L * 0.7)
        rb = rail.bounding_box()  # the extrusion's direction follows the profile's winding: centre it on X
        base += Pos(-(rb.min.X + rb.max.X) / 2, y_rail - rail_w / 2, 0) * rail
        bw = L * 0.7
        bracket = Box(bw, rail_w + 25, 3, align=(Align.CENTER, Align.CENTER, Align.MIN))
        lip = extrude(Plane.YZ * Polygon((0, 0), (rail_h, 0), (rail_h + rail_h, rail_h), (0, rail_h), align=None), amount=bw)
        lb = lip.bounding_box()
        bracket += Pos(-(lb.min.X + lb.max.X) / 2, -(rail_w + 25) / 2, 3 - 0.01) * lip
        for s_ in (-1, 1):
            bracket -= Pos(s_ * bw / 3, 4, 0) * Cylinder(2.25, 20)
            bracket -= Pos(s_ * bw / 3, 4, 3 - 1.5) * Cone(2.25, 4.5, 1.5, align=(Align.CENTER, Align.CENTER, Align.MIN))
        extras.append(("wall_bracket", bracket))
        notes.append("wall bracket: screw it to the wall (two #8 / M4 countersunk screws), lip up; the cleat rail under the "
                     "floor drops over it and holds the box with its floor to the wall, +Y up")

    # Stacking: pins on the lid, sockets under the floor, inset from the corners.
    if spec.stacking:
        if lid is None or spec.lid not in PLATE_LIDS:
            raise ValueError("stacking needs a lid on top")
        if spec.floor < 2.5:
            checks.append("stacking: the sockets need a floor of 2.5 mm or more")
        ix, iy = oL / 2 - 9, oW / 2 - 9
        for sx in (-1, 1):
            for sy in (-1, 1):
                lid += Pos(sx * ix, sy * iy, top + spec.lid_thickness) * Cone(3.0, 2.2, 1.5, align=(Align.CENTER, Align.CENTER, Align.MIN))
                base -= Pos(sx * ix, sy * iy, 0) * Cone(3.0 + spec.fit_clearance, 2.2 + spec.fit_clearance, 1.7,
                                                       align=(Align.CENTER, Align.CENTER, Align.MIN))
        notes.append(f"stacking: four pins on the lid and sockets under the floor, {2 * ix:g} x {2 * iy:g} mm apart, so the same "
                     "boxes stack in line")

    # Weight and print time, roughly.
    vol = base.volume + (lid.volume if lid is not None else 0.0) + sum(e.volume for _, e in extras)
    grams = vol / 1000 * DENSITY[spec.material]
    hours = vol / 8.0 / 3600  # about 8 mm3/s, a typical 0.4 mm nozzle at moderate speed
    estimate = {"material": spec.material, "grams": round(grams, 1), "hours": round(hours, 1),
                "volume_cm3": round(vol / 1000, 1)}
    notes.append(f"about {grams:.0f} g of {spec.material} and {hours:.1f} h to print (solid; rough, a slicer knows better)")

    print_body = None
    if spec.lid == "living":
        print_body, lid_turn = living_print_body(spec, base, lid)
        notes.append(f"living hinge: the lid is printed standing up off the back wall, joined by a {LIVING_T:g} mm strip "
                     f"along the +Y edge; print in PETG or PP, and flex it open and shut a few times while it is still warm. "
                     "The snap rib on -Y holds it shut")
        if spec.material == "PLA":
            checks.append("living hinge in PLA: PLA cracks after a few bends; use PETG, PP or nylon")
    screws = screw_plan(spec)
    checks += screws.pop("checks")
    for role, row in screws.items():
        notes.append(f"{role} screws: {row['screw']}x{row['length']:g} ({'your length' if getattr(spec, role + '_screw_length') else 'stock length'}), "
                     f"{row['engaged']:g} mm of thread {'in the nut' if row['kind'] == 'clearance' else 'in the ' + ('insert' if row['kind'] == 'insert' else 'plastic')}")
    return {"base": base, "lid": lid, "print_body": print_body, "extras": extras, "mounted": mounted, "inlays": inlays, "notes": notes, "checks": checks, "estimate": estimate, "screws": screws,
            "supports": placed, "print_plan": print_plan, "thermal": thermal,
            "inner": [round(v, 3) for v in spec.inner], "outer": [round(v, 3) for v in spec.outer]}


def din_clip(length: float):
    """A TS35 rail clip hanging below z = 0, the rail along X: a fixed hook on +Y and a sprung
    latch beam on -Y whose ramped lip snaps over the rail's edge. *length* is what it hangs from."""
    gap = 0.2
    hook_y = RAIL_W / 2 + gap
    drop = RAIL_T + gap + 1.2  # below the floor: the rail's lip, clearance, the hook's lip
    hook = Box(length * 0.5, 2.0, drop).locate(Location((0, hook_y + 1.0, -drop / 2)))
    hook += Box(length * 0.5, 2.0 + 1.0, 1.2).locate(Location((0, hook_y + 1.0 - 0.5, -drop + 0.6)))
    # The latch: a beam along X, free at one end, its lip ramped so it snaps on.
    beam_len, bt = min(0.4 * length, 30.0), 1.6
    ly = -(RAIL_W / 2 + gap + bt / 2)
    pad = Box(6.0, bt + 4.0, drop).locate(Location((-beam_len / 2 - 3.0, ly - 1.0, -drop / 2)))
    beam = Box(beam_len, bt, drop).locate(Location((0, ly, -drop / 2)))
    lip = extrude(Polygon((0, 0), (1.2, 0), (0, 2.4), align=None), amount=4.0, both=True)
    lip = Pos(beam_len / 2 - 4.0, ly + bt / 2, -drop) * (Rot(0, 0, 90) * (Rot(90, 0, 0) * lip))
    return hook + pad + beam + lip


def _clamshell(spec: BoxSpec) -> dict:
    """Two shells: the whole box built closed (a screw lid, no lip), then parted at `split` of the
    inside height. The lower shell keeps the corner posts' inserts at the parting line and a tongue
    round the wall; the upper shell (with the top) gets clearance holes down the posts and the
    matching groove. Screws go in from the top."""
    import copy
    work = copy.deepcopy(spec)
    work.lid, work.lip, work.gasket = "screw", 0.0, 0.0
    made = build(work)
    base, top_part = made["base"], made["lid"]
    L, W, H = spec.inner
    oL, oW = L + 2 * spec.wall, W + 2 * spec.wall
    z_s = spec.floor + spec.split * H
    big = max(oL, oW) * 3
    below = Box(big, big, z_s + 50).locate(Location((0, 0, (z_s - 50) / 2)))
    lower = base & below
    upper = (base - below) + top_part
    lower = lower if isinstance(lower, Shape) else Compound(children=list(lower))
    # Corner posts: inserts (or pilots) in the lower half, clearance down the upper half.
    d, depth = spec.hole(spec.lid_screw, spec.lid_screw_hole)
    clear, *_ = SCREWS[spec.lid_screw]
    boss = _post_boss(spec, d)
    top = spec.base_height()
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (L / 2 - boss / 2), sy * (W / 2 - boss / 2)
            hd = depth or 8.0
            lower -= Cylinder(d / 2, hd).locate(Location((x, y, z_s - hd / 2 + 0.01)))
            upper -= Cylinder(clear / 2, top - z_s + 1).locate(Location((x, y, (z_s + top) / 2)))
    # Tongue and groove round the wall's middle.
    c = spec.fit_clearance
    tw, th = spec.wall / 2, 1.5
    r_out = spec.corner_radius
    def ring(w_out, w_in, h, z0):
        return (_rounded_box(oL - 2 * w_out, oW - 2 * w_out, h, max(r_out - w_out, 0.0), z0=z0)
                - _rounded_box(oL - 2 * w_in, oW - 2 * w_in, h, max(r_out - w_in, 0.0), z0=z0))
    lower += ring(spec.wall / 4, spec.wall * 3 / 4, th, z_s)
    upper -= ring(spec.wall / 4 - c, spec.wall * 3 / 4 + c, th + 0.3, z_s - 0.01)
    notes = [n for n in made["notes"] if not n.startswith(("lid:", "screw lid"))]
    notes.insert(0, f"clamshell: parts {spec.split * H:.1f} mm above the floor; {spec.lid_screw} screws from the top through "
                    f"the upper shell into {spec.lid_screw_hole} holes in the lower posts; a {tw:g} x {th:g} mm tongue in a groove")
    checks = list(made["checks"])
    if spec.cutouts or spec.vents:
        for raw in spec.cutouts:
            cfa = face_name(raw.get("face", ""))
            if cfa in WALLS:
                h = Cutout(**resolve(raw))
                hh = h.size[1] if h.shape == "rect" else h.size[0]
                zc = spec.floor + h.at[1]
                if zc - hh / 2 < z_s + th + 0.5 and zc + hh / 2 > z_s - 0.5:
                    checks.append(f"{cfa} opening at {h.at} crosses the parting line: move it, or the split")
    return {**made, "base": lower, "lid": upper, "notes": notes, "checks": checks}


def write(spec: BoxSpec, folder: str | Path, stl: bool = True, formats=("step",)) -> dict:
    """Write the box: `step` (base, lid, assembly STEP, and STL unless stl=False) and/or
    `onshape` (a FeatureScript custom feature with these settings as its defaults)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    made = build(spec)
    if "step" in formats:
        export_step(made["base"], str(folder / "base.step"))
        files["base"] = str(folder / "base.step")
        for name, part in made.get("extras") or []:
            export_step(part, str(folder / f"{name}.step"))
            files[name] = str(folder / f"{name}.step")
        if made["lid"] is not None:
            export_step(made["lid"], str(folder / "lid.step"))
            files["lid"] = str(folder / "lid.step")
            a, b = made["base"], made["lid"]
            a.label, b.label = "base", "lid"
            export_step(Compound(children=[a, b]), str(folder / "assembly.step"))
            files["assembly"] = str(folder / "assembly.step")
        if stl:
            export_stl(made["base"], str(folder / "base.stl"))
            files["base_stl"] = str(folder / "base.stl")
            if made["lid"] is not None:
                lid = made["lid"]  # for printing, the lid lies on its top face
                top = lid.bounding_box().max.Z
                flipped = Rot(180, 0, 0) * lid
                export_stl(Pos(0, 0, -flipped.bounding_box().min.Z) * flipped, str(folder / "lid.stl"))
                files["lid_stl"] = str(folder / "lid.stl")
            if made.get("print_body") is not None:
                export_stl(made["print_body"], str(folder / "box_one_piece.stl"))
                files["one_piece_stl"] = str(folder / "box_one_piece.stl")
            if made.get("inlays"):
                export_stl(Compound(children=[sh for _, sh, _ in made["inlays"]]), str(folder / "second_colour.stl"))
                files["second_colour_stl"] = str(folder / "second_colour.stl")
            for name, part in made.get("extras") or []:
                export_stl(part, str(folder / f"{name}.stl"))
                files[f"{name}_stl"] = str(folder / f"{name}.stl")
            if made.get("supports"):
                export_stl(Compound(children=made["supports"]), str(folder / "support_enforcers.stl"))
                files["support_enforcers"] = str(folder / "support_enforcers.stl")
    if "solidworks" in formats:
        from .solidworks import macro
        text, sw_skipped = macro(spec)
        (folder / "enclosure_box.swb").write_text(text)
        files["solidworks"] = str(folder / "enclosure_box.swb")
        if sw_skipped:
            made["checks"].append("not in the SolidWorks macro (STEP has them): " + ", ".join(sw_skipped))
    if "onshape" in formats:
        from .onshape import feature_studio
        text, skipped = feature_studio(spec)
        (folder / "enclosure_box.fs").write_text(text)
        files["onshape"] = str(folder / "enclosure_box.fs")
        if skipped:
            made["checks"].append("not in the Onshape feature yet (STEP has them): " + ", ".join(skipped))
    (folder / "box.json").write_text(json.dumps(asdict(spec), indent=2) + "\n")
    files["settings"] = str(folder / "box.json")
    return {"files": files, "inner": made["inner"], "outer": made["outer"], "notes": made["notes"],
            "checks": made["checks"], "estimate": made.get("estimate"), "print_plan": made.get("print_plan"),
            "thermal": made.get("thermal")}


def load(path: str | Path) -> BoxSpec:
    d = json.loads(Path(path).read_text())
    unknown = set(d) - set(BoxSpec.__dataclass_fields__)
    if unknown:
        raise ValueError(f"{path}: unknown settings {sorted(unknown)}")
    spec = BoxSpec(**d)
    spec.check()
    return spec


def standoff_pattern(text: str) -> list[list[float]]:
    """`rect:80x50` (four at the corners of an 80 x 50 rectangle, centred), or `x,y;x,y;...`."""
    if text.startswith("rect:"):
        a, b = (float(v) for v in text[5:].split("x"))
        return [[sx * a / 2, sy * b / 2] for sy in (-1, 1) for sx in (-1, 1)]
    try:
        return [[float(v) for v in p.split(",")] for p in text.split(";") if p.strip()]
    except ValueError:
        raise ValueError("standoffs: rect:AxB, or x,y;x,y;...") from None


def parse_vent(text: str) -> dict:
    """`left:30x20@0,15` (slots 2 mm wide, 4 mm apart), or `lid:40x30@0,0:3:6` (slot, pitch)."""
    try:
        head, rest = text.split("@", 1)
        face, size = head.split(":")
        at_part, *more = rest.split(":")
        v = {"face": face_name(face), "size": [float(s) for s in size.split("x")],
             "at": [float(s) for s in at_part.split(",")]}
        if more:
            v["slot"] = float(more[0])
        if len(more) > 1:
            v["pitch"] = float(more[1])
        return v
    except ValueError:
        raise ValueError(f"vent {text!r}: FACE:WxH@a,b[:slot[:pitch]]") from None


def parse_label(text: str) -> dict:
    """`lid:SUMP ALARM@0,0` (6 mm text recessed 0.6 mm), `front:v1.2@0,10:4:+0.6` (size, depth)."""
    try:
        face, rest = text.split(":", 1)
        words, where = rest.rsplit("@", 1)
        at_part, *more = where.split(":")
        t = {"face": face_name(face), "text": words, "at": [float(s) for s in at_part.split(",")]}
        if more:
            t["size"] = float(more[0])
        if len(more) > 1:
            t["depth"] = float(more[1])
        return t
    except ValueError:
        raise ValueError(f"label {text!r}: FACE:TEXT@a,b[:size[:depth]]") from None
