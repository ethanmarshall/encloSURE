"""Quick enclosures: a box from a size and a few choices, no board needed.

`enclosure box` makes a base and a lid as STEP files (they open in Onshape and SolidWorks as
solid bodies you can edit with direct-edit tools) plus STL for printing, and saves the settings
as `box.json`, so changing a number and running again rebuilds it.

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
from dataclasses import asdict, dataclass, field  # noqa: F401 (asdict used by the CLI)
from pathlib import Path

from build123d import (Axis, Box, Compound, Cylinder, Location, Pos, Rot, Solid, export_step,
                       export_stl, fillet)

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
# Plain names for the walls (a leading "-" reads as a flag on the command line).
ALIASES = {"left": "-X", "right": "+X", "front": "-Y", "back": "+Y", "top": "lid", "bottom": "floor"}


@dataclass
class Cutout:
    """A hole through one face. On a wall, `at` is (along the wall from its centre, height above
    the inside floor); on the lid or floor, (x, y) from the centre."""

    face: str
    shape: str  # rect or round
    size: list[float]  # [width, height] for rect, [diameter] for round
    at: list[float]
    radius: float = 0.0  # corner radius of a rect

    @staticmethod
    def parse(text: str) -> "Cutout":
        """`left:rect:9.5x3.8@0,8`, `lid:round:12@20,0`, `back:rect:20x10r2@0,15` (or -X +X -Y +Y)."""
        try:
            face, shape, rest = text.split(":", 2)
            face = ALIASES.get(face.lower(), face)
            size_text, at_text = rest.split("@")
            radius = 0.0
            if "r" in size_text:
                size_text, r = size_text.split("r")
                radius = float(r)
            size = [float(v) for v in size_text.split("x")]
            at = [float(v) for v in at_text.split(",")]
        except ValueError:
            raise ValueError(f"cutout {text!r}: write FACE:rect:WxH@a,b or FACE:round:D@a,b") from None
        c = Cutout(face, shape, size, at, radius)
        c.check()
        return c

    def check(self):
        if self.face not in FACES:
            raise ValueError(f"cutout face {self.face!r}: one of {', '.join(FACES)}")
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
    insert_hole: float | None = None  # override the insert hole diameter
    insert_depth: float | None = None
    cutouts: list[dict] = field(default_factory=list)
    flange: float = 0.0  # mounting ears outside the base this far, 0 for none
    flange_screw: str = "M4"

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
        for name in ("lid_screw_hole", "standoff_hole"):
            if getattr(self, name) not in ("tap", "insert", "clearance"):
                raise ValueError(f"{name}: tap, insert or clearance")
        if min(self.inner) <= 0:
            raise ValueError("the walls, floor and lid leave no room inside: make the box bigger")
        if self.wall < 1.0 or self.floor < 1.0:
            raise ValueError("wall and floor: at least 1 mm")
        for c in self.cutouts:
            Cutout(**c).check()

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


def build(spec: BoxSpec) -> dict:
    """The base and lid as solids, plus notes on what was made."""
    spec.check()
    L, W, H = spec.inner
    oL, oW = L + 2 * spec.wall, W + 2 * spec.wall
    base_h = spec.base_height()
    r_out = spec.corner_radius
    r_in = max(r_out - spec.wall, 0.0)
    notes = []

    base = _rounded_box(oL, oW, base_h, r_out)
    base -= _rounded_box(L, W, base_h, r_in, z0=spec.floor)

    # Corner posts for the lid screws, tucked into the inside corners.
    posts = []
    if spec.lid == "screw":
        d, depth = spec.hole(spec.lid_screw, spec.lid_screw_hole)
        boss = _post_boss(spec, d)
        inset = boss / 2 + 0.2
        top = base_h
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = sx * (L / 2 - inset + 0.2), sy * (W / 2 - inset + 0.2)
                # A square-backed post merged into the corner, rounded where it faces the cavity.
                post = Cylinder(boss / 2, top - spec.floor).locate(Location((x, y, spec.floor + (top - spec.floor) / 2)))
                post += Box(boss / 2, boss / 2, top - spec.floor).locate(
                    Location((x + sx * boss / 4, y + sy * boss / 4, spec.floor + (top - spec.floor) / 2)))
                base += post
                hole_depth = depth or (top - spec.floor - 1.0)
                base -= Cylinder(d / 2, hole_depth).locate(Location((x, y, top - hole_depth / 2)))
                posts.append((x, y))
        notes.append(f"lid: {spec.lid_screw} screws into {len(posts)} corner posts ({spec.lid_screw_hole} holes Ø{d:g})")

    # Board standoffs on the floor.
    if spec.standoffs:
        d, depth = spec.hole(spec.standoff_screw, spec.standoff_hole)
        boss = _post_boss(spec, d)
        for x, y in spec.standoffs:
            if abs(x) + boss / 2 > L / 2 + 1e-6 or abs(y) + boss / 2 > W / 2 + 1e-6:
                raise ValueError(f"standoff at ({x:g}, {y:g}) does not fit inside the walls")
            h = spec.standoff_height
            base += Cylinder(boss / 2, h + 0.01).locate(Location((x, y, spec.floor + h / 2 - 0.005)))
            hole_depth = depth or h
            if spec.standoff_hole == "clearance":
                hole_depth = h + spec.floor  # through the floor, for a nut underneath
            base -= Cylinder(d / 2, hole_depth).locate(Location((x, y, spec.floor + h - hole_depth / 2)))
        notes.append(f"{len(spec.standoffs)} standoffs, {spec.standoff_height:g} mm tall, "
                     f"{spec.standoff_screw} {spec.standoff_hole} holes Ø{d:g}")

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

    lid = None
    lip_c = spec.fit_clearance
    top = base_h
    if spec.lid in ("screw", "friction", "snap"):
        lid = _rounded_box(oL, oW, spec.lid_thickness, r_out, z0=top)
        if spec.lip > 0:
            lip = _rounded_box(L - 2 * lip_c, W - 2 * lip_c, spec.lip, max(r_in - lip_c, 0), z0=top - spec.lip)
            lip -= _rounded_box(L - 2 * lip_c - 2 * 1.6, W - 2 * lip_c - 2 * 1.6, spec.lip, max(r_in - lip_c - 1.6, 0),
                                z0=top - spec.lip)
            if posts:  # clear the corner posts
                d, _ = spec.hole(spec.lid_screw, spec.lid_screw_hole)
                boss = _post_boss(spec, d)
                for x, y in posts:
                    lip -= Cylinder(boss / 2 + lip_c + 0.3, spec.lip * 2).locate(Location((x, y, top - spec.lip / 2)))
                    lip -= Box(boss + 2 * lip_c, boss + 2 * lip_c, spec.lip * 2).locate(
                        Location((x + (boss / 4 if x > 0 else -boss / 4), y + (boss / 4 if y > 0 else -boss / 4),
                                  top - spec.lip / 2)))
            lid += lip
        if spec.lid == "screw":
            c, _, _, _, head = SCREWS[spec.lid_screw]
            for x, y in posts:
                lid -= Cylinder(c / 2, spec.lid_thickness * 3).locate(Location((x, y, top + spec.lid_thickness / 2)))
                # Counterbore the screw heads half the lid's thickness.
                cb = spec.lid_thickness / 2
                lid -= Cylinder(head / 2 + 0.3, cb).locate(Location((x, y, top + spec.lid_thickness - cb / 2)))
        if spec.lid == "snap" and spec.lip > 0:
            # A rib along each long side of the lip, and a matching groove in the walls.
            rib, z_rib = 0.5, top - spec.lip + 1.0
            for sy in (-1, 1):
                y_lip = sy * (W / 2 - lip_c)
                lid += Box(L * 0.6, rib * 2, 1.0).locate(Location((0, y_lip, z_rib)))
                base -= Box(L * 0.6 + 2, (rib + lip_c) * 2, 1.0 + 2 * lip_c).locate(Location((0, sy * W / 2, z_rib)))
            notes.append("snap lid: a 0.5 mm rib on each long side clicks into a groove in the wall")
        notes.append(f"{spec.lid} lid, {spec.lid_thickness:g} mm" + (f", {spec.lip:g} mm lip" if spec.lip else ""))
    elif spec.lid == "slide":
        t = spec.lid_thickness
        g = min(spec.wall / 2, 1.2)  # groove depth into each long wall
        z0 = base_h - 1.0 - t  # the panel's underside; 1 mm of wall above it
        # Grooves in both long walls, open at +X.
        for sy in (-1, 1):
            base -= Box(L + spec.wall + 1, 2 * g, t + 2 * lip_c).locate(
                Location((spec.wall / 2 + 0.5, sy * W / 2, z0 + t / 2)))
        # Open the +X end down to the groove's bottom, so the panel slides in.
        base -= Box(2 * spec.wall + 2, W + 2 * g, base_h - z0 + lip_c + 1).locate(
            Location((oL / 2, 0, z0 - lip_c + (base_h - z0 + lip_c + 1) / 2)))
        lid = Box(L + spec.wall - lip_c, W + 2 * g - 2 * lip_c, t).locate(
            Location((spec.wall / 2 - lip_c / 2, 0, z0 + t / 2)))
        notes.append(f"slide lid: {t:g} mm panel in {g:g} mm grooves, slides in from the +X end")

    # Cutouts.
    for c in (Cutout(**c) for c in spec.cutouts):
        if c.face in ("lid", "floor"):
            target = "lid" if c.face == "lid" else "base"
            if target == "lid" and lid is None:
                raise ValueError("a lid cutout needs a lid")
            z = top if c.face == "lid" else 0.0
            depth = 50.0
            if c.shape == "round":
                cut = Cylinder(c.size[0] / 2, depth).locate(Location((c.at[0], c.at[1], z)))
            else:
                cut = Box(c.size[0], c.size[1], depth).locate(Location((c.at[0], c.at[1], z)))
                if c.radius > 0:
                    cut = fillet(cut.edges().filter_by(Axis.Z), min(c.radius, min(c.size) / 2 - 0.01))
            if target == "lid":
                lid -= cut
            else:
                base -= cut
        else:
            axis = 0 if c.face in ("-X", "+X") else 1
            sign = -1 if c.face.startswith("-") else 1
            along, height = c.at
            z = spec.floor + height
            depth = spec.wall * 4
            if c.shape == "round":
                cut = Cylinder(c.size[0] / 2, depth)
            else:
                cut = Box(c.size[0], c.size[1], depth)
                if c.radius > 0:
                    cut = fillet(cut.edges().filter_by(Axis.Z), min(c.radius, min(c.size) / 2 - 0.01))
            # The cut is built along Z; turn it to face the wall.
            if axis == 0:
                cut = Pos(sign * oL / 2, along, z) * (Rot(0, 90, 0) * Rot(0, 0, 90) * cut)
            else:
                cut = Pos(along, sign * oW / 2, z) * (Rot(90, 0, 0) * cut)
            base -= cut
        notes.append(f"cutout {c.face} {c.shape} {'x'.join(f'{v:g}' for v in c.size)} at {c.at}")

    return {"base": base, "lid": lid, "notes": notes,
            "inner": [round(v, 3) for v in spec.inner], "outer": [round(v, 3) for v in spec.outer]}


def write(spec: BoxSpec, folder: str | Path, stl: bool = True) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    made = build(spec)
    files = {}
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
            # For printing, the lid lies on its top face.
            lid = made["lid"]
            top = lid.bounding_box().max.Z
            export_stl(Pos(0, 0, top) * (Rot(180, 0, 0) * lid), str(folder / "lid.stl"))
            files["lid_stl"] = str(folder / "lid.stl")
    (folder / "box.json").write_text(json.dumps(asdict(spec), indent=2) + "\n")
    files["settings"] = str(folder / "box.json")
    return {"files": files, "inner": made["inner"], "outer": made["outer"], "notes": made["notes"]}


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
