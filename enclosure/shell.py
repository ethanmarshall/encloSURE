"""Reading an enclosure: its cavity, floor, rim, standoff bosses and wall openings.

Conventions: Z is up (the direction the lid comes off), millimetres, the enclosure's own STEP
frame. The base is an open-topped shell; a lid, if given, closes it from above.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from build123d import Align, Axis, Box, Cylinder, GeomType, Location, Plane, Shape, Vector

from .geom import bbox, vec

UP = Vector(0, 0, 1)


@dataclass
class Boss:
    """A standoff the board can sit on: a round top face facing up inside the cavity."""

    center: list[float]  # top centre, x y z
    diameter: float
    hole: float | None  # the hole in its top (a pilot, tap or insert hole), if any
    top: float  # z of its top face

    @property
    def screw(self) -> str | None:
        return screw_for(self.hole)


@dataclass
class Opening:
    """A hole through a wall, floor or lid: where a connector, button or cable passes."""

    wall: str  # -X +X -Y +Y floor lid
    center: list[float]
    width: float  # along the wall, horizontal (for floor and lid: along X)
    height: float  # vertical (for floor and lid: along Y)
    wall_thickness: float
    outer: float  # the outer surface's coordinate on the wall's axis


@dataclass
class Enclosure:
    bounds: tuple
    cavity_bounds: tuple
    floor: float  # z of the cavity floor
    rim: float  # z of the top of the walls
    lid_underside: float | None  # z of the lid's lowest point over the cavity, if a lid is given
    bosses: list[Boss] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)

    @property
    def ceiling(self) -> float:
        """The highest z a part may reach: the lid's underside, else the rim."""
        return self.lid_underside if self.lid_underside is not None else self.rim

    def to_json(self) -> dict:
        d = asdict(self)
        d["ceiling"] = round(self.ceiling, 3)
        for b, boss in zip(d["bosses"], self.bosses):
            b["screw"] = boss.screw
        return d


# Pilot/tap/insert hole sizes to the metric screw they are for, and that screw's board
# clearance hole (ISO 273 medium fit). (hole up to, screw, board hole)
SCREWS = [
    (1.9, "M2 (self-tapping) or M2 thread", 2.2),
    (2.2, "M2.5 (self-tapping)", 2.7),
    (2.65, "M2.5 thread, or M3 self-tapping", 2.7),
    (3.6, "M3 heat-set insert or thread", 3.2),
    (4.3, "M3 heat-set insert", 3.2),
    (5.0, "M4 thread", 4.3),
]


def solid_at(shape: Shape, a, b, r: float = 0.15) -> bool:
    """Whether *shape* has material on the segment from point *a* to *b* (a thin rod's worth)."""
    a, b = Vector(*a), Vector(*b)
    length = (b - a).length
    if length < 1e-6:
        return False
    rod = Cylinder(r, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    d = (b - a).normalized()
    rod = rod.moved(Location(Plane(origin=a, z_dir=d)))
    common = shape & rod
    try:
        return common is not None and sum(x.volume for x in common.solids()) > 1e-4
    except Exception:
        return False


# The heat-set insert holes `enclosure box` makes: hole, screw, the board's clearance hole.
INSERTS = [(3.2, "M2", 2.2), (3.6, "M2.5", 2.7), (4.0, "M3", 3.2), (5.6, "M4", 4.3)]


def _insert(hole: float | None):
    return next((i for i in INSERTS if hole is not None and abs(hole - i[0]) < 0.03), None)


def screw_for(hole: float | None) -> str | None:
    if hole is None:
        return None
    if ins := _insert(hole):
        return f"{ins[1]} heat-set insert"
    for top, name, _ in SCREWS:
        if hole <= top + 1e-6:
            return name
    return None


def board_hole_for(hole: float | None) -> float:
    """The PCB mounting hole for a boss with this hole: the screw's clearance hole."""
    if hole is None:
        return 3.2
    if ins := _insert(hole):
        return ins[2]
    for top, _, clearance in SCREWS:
        if hole <= top + 1e-6:
            return clearance
    return round(hole + 0.2, 2)


def cavity_of(base: Shape) -> Shape:
    """The empty space inside an open-topped base: its bounding box less the base, keeping the
    largest piece."""
    (x0, y0, z0), (x1, y1, z1) = bbox(base)
    box = Box(x1 - x0, y1 - y0, z1 - z0).locate(
        Location(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    )
    void = box - base
    pieces = void.solids()
    if not pieces:
        raise ValueError("the base has no inside space: is it a solid block?")
    return max(pieces, key=lambda s: s.volume)


def _circle_d(wire) -> float:
    (x0, y0, _), (x1, y1, _) = bbox(wire)
    return (x1 - x0 + y1 - y0) / 2


def bosses_of(base: Shape, cavity_xy, floor: float) -> list[Boss]:
    (cx0, cy0), (cx1, cy1) = cavity_xy
    found = []
    for face in base.faces():
        if face.geom_type != GeomType.PLANE:
            continue
        n = face.normal_at()
        if n.Z < 0.999:
            continue
        (fx0, fy0, fz), (fx1, fy1, _) = bbox(face)
        if fz < floor + 0.3:
            continue  # the floor itself, or a step in it
        w, h = fx1 - fx0, fy1 - fy0
        if max(w, h) > 15 or abs(w - h) > 0.15 * max(w, h):
            continue  # not round and standoff sized
        cxm, cym = (fx0 + fx1) / 2, (fy0 + fy1) / 2
        if not (cx0 < cxm < cx1 and cy0 < cym < cy1):
            continue
        outer = face.outer_wire()
        if not all(e.geom_type == GeomType.CIRCLE for e in outer.edges()):
            continue
        rim = bbox(base)[1][2]
        if solid_at(base, (cxm, cym, fz + 0.05), (cxm, cym, rim + 1)):
            continue  # material above it: not a top
        r_out = (w + h) / 4 + 0.3
        walled = sum(solid_at(base, (cxm + dx * r_out, cym + dy * r_out, fz + 0.2),
                              (cxm + dx * r_out, cym + dy * r_out, fz + 0.6))
                     for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if walled == 4:
            continue  # walled in all round just above it: the bottom of a blind hole
        inner = face.inner_wires()
        hole = round(_circle_d(inner[0]), 3) if inner else None
        found.append(Boss([round(cxm, 3), round(cym, 3), round(fz, 3)], round((w + h) / 2, 3), hole, round(fz, 3)))
    # A blind hole's bottom is round and faces up too: drop any candidate lying inside a
    # higher, wider one.
    found = [
        b for b in found
        if not any(o is not b and o.top > b.top and o.diameter > b.diameter
                   and math.dist(o.center[:2], b.center[:2]) < o.diameter / 2 for o in found)
    ]
    found.sort(key=lambda b: (b.center[1], b.center[0]))
    return found


def openings_of(base: Shape, cavity: Shape, walls=None) -> list[Opening]:
    """Holes through the side walls and the floor, read from the faces bounding the cavity.
    *walls* are the inner wall surfaces ((x0, y0), (x1, y1)); the cavity's box by default."""
    (bx0, by0, bz0), (bx1, by1, bz1) = bbox(base)
    (cx0, cy0, cz0), (cx1, cy1, _) = bbox(cavity)
    if walls is not None:
        (cx0, cy0), (cx1, cy1) = walls
    center = Vector((cx0 + cx1) / 2, (cy0 + cy1) / 2, (cz0 + bz1) / 2)
    out: list[Opening] = []
    for face in base.faces():
        if face.geom_type != GeomType.PLANE or not face.inner_wires():
            continue
        n = face.normal_at()
        fc = face.center()
        inward = (center - fc).dot(n) > 0  # the face looks into the cavity
        if not inward:
            continue
        for wire in face.inner_wires():
            (wx0, wy0, wz0), (wx1, wy1, wz1) = bbox(wire)
            mid = [(wx0 + wx1) / 2, (wy0 + wy1) / 2, (wz0 + wz1) / 2]
            if abs(n.Z) > 0.999:
                inside = cx0 < mid[0] < cx1 and cy0 < mid[1] < cy1
                through = not solid_at(base, (mid[0], mid[1], fc.Z - 0.05), (mid[0], mid[1], bz0 - 1))
                if n.Z > 0 and inside and through:  # the floor, seen from inside
                    out.append(Opening("floor", [round(v, 3) for v in mid], round(wx1 - wx0, 3),
                                       round(wy1 - wy0, 3), round(fc.Z - bz0, 3), round(bz0, 3)))
                continue
            if abs(n.X) > 0.999:
                wall = "-X" if n.X > 0 else "+X"
                outer = bx0 if n.X > 0 else bx1
                thick = abs(fc.X - outer)
                width = wy1 - wy0
            elif abs(n.Y) > 0.999:
                wall = "-Y" if n.Y > 0 else "+Y"
                outer = by0 if n.Y > 0 else by1
                thick = abs(fc.Y - outer)
                width = wx1 - wx0
            else:
                continue
            # Only a hole in a wall round the cavity (not a hinge knuckle's pin hole outside it).
            if (wall in ("-X", "+X") and not cy0 < mid[1] < cy1) or (wall in ("-Y", "+Y") and not cx0 < mid[0] < cx1):
                continue
            # Only a hole through the wall: a groove (a snap lid's, a slide lid's) is not one.
            start = Vector(*mid) - n * 0.05
            if solid_at(base, start, start - n * (thick + 1.0)):
                continue
            out.append(Opening(wall, [round(v, 3) for v in mid], round(width, 3),
                               round(wz1 - wz0, 3), round(thick, 3), round(outer, 3)))
    # A boss's own hole opens in its top face, which looks up into the cavity too: keep floor
    # openings only where they are not a boss top.
    return out


def lid_underside(lid: Shape, cavity_xy) -> float:
    """The lid's underside over the cavity: the middle height of a grid of points across it. Things
    that hang lower in places (a lip at the walls, corner posts, light pipe tubes) are left to the
    fit check's collision test, which sees them as they are."""
    (cx0, cy0), (cx1, cy1) = cavity_xy
    (_, _, lz0), (_, _, lz1) = bbox(lid)
    hits = []
    for i in range(5):
        for j in range(5):
            x = cx0 + (cx1 - cx0) * (0.2 + 0.15 * i)
            y = cy0 + (cy1 - cy0) * (0.2 + 0.15 * j)
            col = Box(0.4, 0.4, lz1 - lz0 + 2).locate(Location((x, y, (lz0 + lz1) / 2)))
            over = lid & col
            solids = over.solids() if hasattr(over, "solids") else list(over)
            if solids:
                hits.append(min(bbox(s)[0][2] for s in solids))
    if not hits:
        return lz0
    hits.sort()
    return hits[len(hits) // 2]


def lid_openings(lid: Shape, base: Shape | None = None) -> list[Opening]:
    """Holes through the lid. A loop that is not through (a lip's inside) is not one, nor is a
    hole over a post of the base (a lid screw's)."""
    out = []
    (_, _, lz0), (_, _, lz1) = bbox(lid)
    for face in lid.faces():
        if face.geom_type != GeomType.PLANE or face.normal_at().Z > -0.999:
            continue
        for wire in face.inner_wires():
            (wx0, wy0, wz0), (wx1, wy1, _) = bbox(wire)
            cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
            if solid_at(lid, (cx, cy, wz0 - 1), (cx, cy, lz1 + 1)):
                continue  # not through
            if base is not None:
                (_, _, bz0), _ = bbox(base)
                if solid_at(base, (cx, cy, wz0 - 0.5), (cx, cy, bz0 + 0.5 + 2.0)):
                    continue  # over a post: a lid screw's hole
            out.append(Opening("lid", [round((wx0 + wx1) / 2, 3), round((wy0 + wy1) / 2, 3), round(wz0, 3)],
                               round(wx1 - wx0, 3), round(wy1 - wy0, 3), round(lz1 - wz0, 3), round(lz1, 3)))
    return out


def inner_walls(base: Shape, cavity: Shape):
    """(x0, y0), (x1, y1): the inner wall surfaces, each the largest face looking into the
    cavity from that side (an opening's tunnel would stretch the cavity's own box)."""
    (cx0, cy0, _), (cx1, cy1, _) = bbox(cavity)
    (bx0, by0, _), (bx1, by1, _) = bbox(base)
    best = {}
    for face in base.faces():
        if face.geom_type != GeomType.PLANE:
            continue
        n = face.normal_at()
        for key, comp, sign in (("x0", "X", 1), ("x1", "X", -1), ("y0", "Y", 1), ("y1", "Y", -1)):
            if getattr(n, comp) * sign > 0.999:
                at = getattr(face.center(), comp)
                lo, hi = (bx0, bx1) if comp == "X" else (by0, by1)
                if not (lo + 0.05 < at < hi - 0.05):
                    continue  # an outside face
                if (at - (lo + hi) / 2) * sign > 0:
                    continue  # faces away from the middle: an outside face (past a flange, say)
                area = face.area
                if area > best.get(key, (0, None))[0]:
                    best[key] = (area, getattr(face.center(), comp))
    get = lambda k, fallback: best[k][1] if k in best else fallback
    return (get("x0", cx0), get("y0", cy0)), (get("x1", cx1), get("y1", cy1))


def floor_of(base: Shape, walls) -> float:
    """The inside floor's height: the top of the material under a few points spread over the
    cavity, taking the lowest (a standoff under one point does not lift the floor)."""
    (x0, y0), (x1, y1) = walls
    (_, _, bz0), (_, _, bz1) = bbox(base)
    tops = []
    for fx, fy in ((0.5, 0.5), (0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7), (0.5, 0.2), (0.5, 0.8)):
        x, y = x0 + fx * (x1 - x0), y0 + fy * (y1 - y0)
        rod = Cylinder(0.2, bz1 - bz0 + 2).locate(Location((x, y, (bz0 + bz1) / 2)))
        common = base & rod
        pieces = common.solids() if common is not None else []
        if pieces:
            # The lowest piece of material on this line is the floor there.
            low = min(pieces, key=lambda p: bbox(p)[0][2])
            tops.append(bbox(low)[1][2])
    return min(tops) if tops else bz0


def read(base: Shape, lid: Shape | None = None) -> Enclosure:
    cavity = cavity_of(base)
    (_, _, cz0), (_, _, cz1) = bbox(cavity)
    (cx0, cy0), (cx1, cy1) = inner_walls(base, cavity)
    # The floor: the cavity's lowest face over most of its area. A slice just above the lowest
    # point that still spans the cavity tells it; bosses and ribs rise from there.
    cavity_xy = ((cx0, cy0), (cx1, cy1))
    floor = floor_of(base, cavity_xy)
    bosses = bosses_of(base, cavity_xy, floor)
    boss_holes = {(b.center[0], b.center[1]) for b in bosses}
    openings = [
        o for o in openings_of(base, cavity, cavity_xy)
        if not (o.wall == "floor" and any(math.dist(o.center[:2], h) < 0.5 for h in boss_holes))
    ]
    under = None
    if lid is not None:
        under = round(lid_underside(lid, cavity_xy), 3)
        openings += lid_openings(lid, base)
    return Enclosure(
        bounds=tuple(map(tuple, bbox(base))),
        cavity_bounds=((round(cx0, 3), round(cy0, 3), round(floor, 3)), (round(cx1, 3), round(cy1, 3), round(cz1, 3))),
        floor=round(floor, 3),
        rim=round(bbox(base)[1][2], 3),
        lid_underside=under,
        bosses=bosses,
        openings=openings,
    ), cavity


def section_at(cavity: Shape, z: float):
    """The cavity's outline at height *z*: the faces of a horizontal cut."""
    return cavity.section(Plane.XY.offset(z) if hasattr(Plane.XY, "offset") else Plane(origin=(0, 0, z)))
