"""A box in any shape: the inside outline from a DXF (one closed shape: a polyline, or lines and arcs
end to end), walls round it, a floor, and a lid with a locating lip. Circles inside the outline in
the same DXF become standoffs, so a board's holes can be drawn right there."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from build123d import Align, Cylinder, Face, Kind, Pos, Wire, extrude, offset


@dataclass
class Outline:
    height: float = 30.0  # inside
    wall: float = 2.0
    floor: float = 2.0
    lid_thickness: float = 2.0
    lip: float = 3.0
    clearance: float = 0.2
    standoff_height: float = 5.0
    standoff_screw: str = "M3"


def read_dxf(path) -> tuple[list[tuple[float, float]], list[tuple[float, float, float]]]:
    """(the outline's points, the circles inside it as (x, y, d)) from a DXF in mm."""
    import ezdxf
    from ezdxf import path as dxfpath
    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()
    loops, circles, pieces = [], [], []
    for e in msp:
        t = e.dxftype()
        if t == "CIRCLE":
            circles.append((e.dxf.center.x, e.dxf.center.y, 2 * e.dxf.radius))
        elif t in ("LWPOLYLINE", "POLYLINE", "SPLINE", "ELLIPSE") or (t == "ARC" or t == "LINE"):
            p = dxfpath.make_path(e)
            pts = [(v.x, v.y) for v in p.flattening(0.05)]
            if t in ("LWPOLYLINE", "POLYLINE") and getattr(e, "closed", False) or (t in ("LWPOLYLINE",) and e.closed):
                loops.append(pts)
            elif len(pts) >= 2:
                pieces.append(pts)
    # Chain loose lines and arcs end to end.
    if not loops and pieces:
        chain = list(pieces.pop(0))
        while pieces:
            end = chain[-1]
            best = min(range(len(pieces)), key=lambda i: min(_d(end, pieces[i][0]), _d(end, pieces[i][-1])))
            p = pieces.pop(best)
            if _d(end, p[-1]) < _d(end, p[0]):
                p = p[::-1]
            if _d(end, p[0]) > 0.05:
                raise ValueError("the outline's lines and arcs don't meet end to end: close the shape")
            chain += p[1:]
        if _d(chain[0], chain[-1]) > 0.05:
            raise ValueError("the outline isn't closed")
        loops.append(chain[:-1])
    if not loops:
        raise ValueError("no closed outline in the DXF: draw the inside shape as one closed polyline")
    outline = max(loops, key=_area)
    return outline, circles


def _d(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _area(pts):
    return abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts)))) / 2


def build(points, circles, o: Outline | None = None) -> dict:
    from .box import SCREWS
    o = o or Outline()
    clean = [points[0]]
    for p in points[1:]:
        if _d(p, clean[-1]) > 0.01:
            clean.append(p)
    cx = sum(p[0] for p in clean) / len(clean)
    cy = sum(p[1] for p in clean) / len(clean)
    inner = Face(Wire.make_polygon([(x - cx, y - cy, 0) for x, y in clean], close=True))
    outer = offset(inner, amount=o.wall, kind=Kind.ARC)
    lip_out = offset(inner, amount=-o.clearance, kind=Kind.ARC)
    lip_in = offset(inner, amount=-(o.clearance + 1.6), kind=Kind.ARC)
    top = o.floor + o.height
    base = extrude(outer, amount=top) - Pos(0, 0, o.floor) * extrude(inner, amount=o.height + 1)
    lid = Pos(0, 0, top) * extrude(outer, amount=o.lid_thickness)
    if o.lip > 0:
        lid += Pos(0, 0, top - o.lip) * (extrude(lip_out, amount=o.lip) - extrude(lip_in, amount=o.lip))
    notes = [f"outline box: {o.height:g} mm inside, {o.wall:g} mm walls round your outline, a lid with a {o.lip:g} mm lip "
             f"({o.clearance:g} mm clearance)"]
    inside = [(x - cx, y - cy, d) for x, y, d in circles]
    so = []
    if inside:
        _, pilot, insert, depth, _ = SCREWS[o.standoff_screw]
        for x, y, d in inside:
            from build123d import Vector
            if not inner.is_inside(Vector(x, y, 0)):
                continue
            base += Pos(x, y, o.floor - 0.01) * Cylinder(insert / 2 + 2.0, o.standoff_height, align=(Align.CENTER, Align.CENTER, Align.MIN))
            base -= Pos(x, y, o.floor + o.standoff_height - depth - 0.5) * Cylinder(insert / 2, depth + 1,
                                                                                   align=(Align.CENTER, Align.CENTER, Align.MIN))
            so.append((x, y))
        if so:
            notes.append(f"{len(so)} standoffs where the DXF's circles are, {o.standoff_height:g} mm tall, {o.standoff_screw} inserts")
    notes.append("the outline is the inside: the walls go outside it. The shape is centred on its points' average")
    return {"base": base, "lid": lid, "notes": notes, "standoffs": so}


def write(path_dxf, folder, o: Outline | None = None) -> dict:
    from build123d import Rot, export_step, export_stl
    pts, circles = read_dxf(path_dxf)
    m = build(pts, circles, o)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    export_step(m["base"], str(folder / "outline_base.step"))
    export_step(m["lid"], str(folder / "outline_lid.step"))
    export_stl(m["base"], str(folder / "outline_base.stl"))
    export_stl(Rot(180, 0, 0) * m["lid"], str(folder / "outline_lid.stl"))
    (folder / "notes.md").write_text("# Box from an outline\n\n" + "\n".join(f"- {n}" for n in m["notes"]) + "\n", encoding="utf-8")
    return {"notes": m["notes"]}
