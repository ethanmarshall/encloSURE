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

from build123d import (Align, Axis, Box, Compound, Cylinder, Location, Polygon, Pos, Rot, Text,
                       chamfer, export_step, export_stl, extrude, fillet)

from .presets import GLANDS, PRESETS, resolve

# Per metric screw: (clearance hole, pilot for thread-forming in plastic, heat-set insert hole,
# insert depth, head diameter). Clearance is ISO 273 medium; pilot and insert holes are common
# 3D-printing figures (insert brands differ: override them).
SCREWS = {
    "M2": (2.4, 1.7, 3.2, 4.0, 3.8),
    "M2.5": (2.9, 2.1, 3.6, 4.5, 4.5),
    "M3": (3.4, 2.5, 4.0, 5.7, 5.5),
    "M4": (4.5, 3.4, 5.6, 8.1, 7.0),
}
LIDS = ("screw", "friction", "snap", "slide", "none")
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
    teardrop: bool = True  # round holes in walls get a 45° peak, to print without support
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
        for name in ("lid_screw_hole", "standoff_hole"):
            if getattr(self, name) not in ("tap", "insert", "clearance"):
                raise ValueError(f"{name}: tap, insert or clearance")
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
        for c in self.cutouts:
            Cutout(**resolve(c)).check()
        for v in self.vents:
            if face_name(v.get("face", "")) not in FACES or len(v.get("size", [])) != 2:
                raise ValueError("vent: {face, size: [w, h], at: [a, b]}")
        for t in self.labels:
            if face_name(t.get("face", "")) not in ("lid", *WALLS) or not t.get("text"):
                raise ValueError("label: {face: lid or a wall, text, size, at, depth}")
            if t.get("face") == "lid" and self.lid not in ("screw", "friction", "snap"):
                raise ValueError("a lid label needs a lid on top")

    def hole(self, screw: str, kind: str) -> tuple[float, float | None]:
        """(diameter, depth) of a screw hole of this kind; depth None for through."""
        clearance, pilot, insert, depth, _ = SCREWS[screw]
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


def _profile(shape: str, size, radius: float, depth: float, teardrop: bool = False):
    """A cutting tool along Z, centred: a rect (corner radius) or a round hole, its local +Y up.
    A teardrop adds a 45° peak above a round hole so it prints without support."""
    if shape == "round":
        r = size[0] / 2
        tool = Cylinder(r, depth)
        if teardrop:
            k = r * math.sqrt(0.5)
            peak = extrude(Polygon((-k, k), (k, k), (0, r * math.sqrt(2)), align=None), amount=depth / 2, both=True)
            tool = tool + peak
        return tool
    tool = Box(size[0], size[1], depth)
    if radius > 0:
        tool = fillet(tool.edges().filter_by(Axis.Z), min(radius, min(size) / 2 - 0.01))
    return tool


def _on_wall(tool, face: str, along: float, z: float, oL: float, oW: float):
    """Put a tool built along Z (local +Y up) through a wall, centred `along` it at height z."""
    sign = -1 if face.startswith("-") else 1
    if face in ("-X", "+X"):
        return Pos(sign * oL / 2, along, z) * (Rot(0, 90, 0) * Rot(0, 0, 90) * tool)
    return Pos(along, sign * oW / 2, z) * (Rot(90, 0, 0) * tool)


def build(spec: BoxSpec) -> dict:
    """The base and lid as solids, notes on what was made, and checks worth a look."""
    spec.check()
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
    if spec.lid == "screw":
        d, depth = spec.hole(spec.lid_screw, spec.lid_screw_hole)
        post_boss = boss = _post_boss(spec, d)
        inset = boss / 2
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = sx * (L / 2 - inset), sy * (W / 2 - inset)
                h = top - spec.floor
                post = Cylinder(boss / 2, h).locate(Location((x, y, spec.floor + h / 2)))
                post += Box(boss / 2, boss / 2, h).locate(Location((x + sx * boss / 4, y + sy * boss / 4, spec.floor + h / 2)))
                base += post
                hole_depth = depth or (h - 1.0)
                post_holes.append(Cylinder(d / 2, hole_depth).locate(Location((x, y, top - hole_depth / 2))))
                posts.append((x, y))
                keep_out.append((x, y, boss / 2))
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
            hole_depth = depth or h
            if spec.standoff_hole == "clearance":
                hole_depth = h + spec.floor  # through the floor, for a nut underneath
            elif depth and depth > h + spec.floor - 0.6:
                checks.append(f"standoff at ({x:g}, {y:g}): the {depth - 0.5:g} mm insert is longer than "
                              f"the standoff and floor allow; make standoffs at least {depth - spec.floor + 0.1:.1f} mm tall")
                hole_depth = h + spec.floor - 0.6
            base -= Cylinder(d / 2, hole_depth).locate(Location((x, y, spec.floor + h - hole_depth / 2)))
            keep_out.append((x, y, boss / 2))
        notes.append(f"{len(spec.standoffs)} standoffs, {h:g} mm tall, {spec.standoff_screw} "
                     f"{spec.standoff_hole} holes Ø{d:g}" + (", with gussets" if spec.standoff_ribs and h >= 3 else ""))

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

    for hole in post_holes:  # after the gasket ledge, which covers the posts' tops
        base -= hole

    lid = None
    lip_c = spec.fit_clearance
    if spec.lid in ("screw", "friction", "snap"):
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
        if spec.lid == "snap" and spec.lip > 0:
            rib, z_rib = 0.5, top - spec.lip + 1.0
            for sy in (-1, 1):
                lid += Box(L * 0.6, rib * 2, 1.0).locate(Location((0, sy * (W / 2 - lip_c), z_rib)))
                base -= Box(L * 0.6 + 2, (rib + lip_c) * 2, 1.0 + 2 * lip_c).locate(Location((0, sy * W / 2, z_rib)))
            notes.append("snap lid: a 0.5 mm rib on each long side clicks into a groove in the wall")
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

    lid_top = (top + spec.lid_thickness) if spec.lid in ("screw", "friction", "snap") else None

    def cut(target, tool):
        nonlocal base, lid
        if target == "lid":
            if lid is None:
                raise ValueError("a lid cutout, vent or label needs a lid")
            lid = lid - tool
        else:
            base = base - tool

    # Cutouts.
    for raw in spec.cutouts:
        c = Cutout(**resolve(raw))
        if c.face in ("lid", "floor"):
            z = top if c.face == "lid" else 0.0
            cut("lid" if c.face == "lid" else "base",
                Pos(c.at[0], c.at[1], z) * _profile(c.shape, c.size, c.radius, 50.0))
        else:
            along, height = c.at
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
        label = c.preset or f"{c.shape} {'x'.join(f'{v:g}' for v in c.size)}"
        notes.append(f"cutout {c.face} {label} at {c.at}" + (f" ({c.source})" if c.source else ""))

    # Vents: slots filling an area, upright on walls, along Y on the lid or floor.
    for v in spec.vents:
        face = face_name(v["face"])
        (w, h), (a, b) = v["size"], v.get("at", [0, 0])
        slot, pitch = v.get("slot", 2.0), v.get("pitch", 4.0)
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
        gap = 0.2
        hook_y = RAIL_W / 2 + gap
        drop = RAIL_T + gap + 1.2  # below the floor: the rail's lip, clearance, the hook's lip
        hook = Box(oL * 0.5, 2.0, drop).locate(Location((0, hook_y + 1.0, -drop / 2)))
        hook += Box(oL * 0.5, 2.0 + 1.0, 1.2).locate(Location((0, hook_y + 1.0 - 0.5, -drop + 0.6)))
        base += hook
        # The latch: a beam along X, free at one end, its lip ramped so the box snaps on.
        beam_len, bt = min(0.4 * oL, 30.0), 1.6
        ly = -(RAIL_W / 2 + gap + bt / 2)
        pad = Box(6.0, bt + 4.0, drop).locate(Location((-beam_len / 2 - 3.0, ly - 1.0, -drop / 2)))
        beam = Box(beam_len, bt, drop).locate(Location((0, ly, -drop / 2)))
        lip = extrude(Polygon((0, 0), (1.2, 0), (0, 2.4), align=None), amount=4.0, both=True)
        lip = Pos(beam_len / 2 - 4.0, ly + bt / 2, -drop) * (Rot(0, 0, 90) * (Rot(90, 0, 0) * lip))
        base += pad + beam + lip
        notes.append("DIN rail clip (TS35, rail along X): hook on +Y, sprung latch on -Y; print a test first")

    # Labels: raised (depth > 0) or recessed (depth < 0) text.
    for t in spec.labels:
        face = face_name(t["face"])
        size, depth = t.get("size", 6.0), t.get("depth", -0.6)
        a, b = t.get("at", [0, 0])
        text = Text(t["text"], size, align=(Align.CENTER, Align.CENTER))
        body = extrude(text, amount=abs(depth))
        if face == "lid":
            z = lid_top if depth > 0 else lid_top - abs(depth)
            placed = Pos(a, b, z) * body
            lid = lid + placed if depth > 0 else lid - placed
        else:
            # Upright on the wall, reading from outside; the extrusion points out of the wall.
            turn = {"-Y": 0, "+Y": 180, "-X": -90, "+X": 90}[face]
            out = {"-Y": (0, -1), "+Y": (0, 1), "-X": (-1, 0), "+X": (1, 0)}[face]
            right = {"-Y": (1, 0), "+Y": (-1, 0), "-X": (0, -1), "+X": (0, 1)}[face]
            half = (oL / 2) if face in ("-X", "+X") else (oW / 2)
            inset = 0.0 if depth > 0 else -abs(depth)  # recessed text starts inside the wall
            x = out[0] * (half + inset) + right[0] * a
            y = out[1] * (half + inset) + right[1] * a
            placed = Pos(x, y, spec.floor + b) * (Rot(0, 0, turn) * (Rot(90, 0, 0) * body))
            base = base + placed if depth > 0 else base - placed
        notes.append(f"label {t['text']!r} on {face}, {'raised' if depth > 0 else 'recessed'} {abs(depth):g} mm")

    return {"base": base, "lid": lid, "notes": notes, "checks": checks,
            "inner": [round(v, 3) for v in spec.inner], "outer": [round(v, 3) for v in spec.outer]}


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
                export_stl(Pos(0, 0, top) * (Rot(180, 0, 0) * lid), str(folder / "lid.stl"))
                files["lid_stl"] = str(folder / "lid.stl")
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
            "checks": made["checks"]}


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
