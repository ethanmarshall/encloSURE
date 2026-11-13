"""A laser-cut box: six flat panels (acrylic, plywood, MDF) with finger joints, as one DXF to cut,
and a STEP of it put together.

Every edge is split into an odd number of fingers about three thicknesses wide. Where two panels
meet, one has fingers on the even places and the other on the odd ones, so they interlock; the top
and bottom carry the fingers of their edges, the sides take the front and back's. The outlines grow
by half the kerf so the joints come out snug (set your laser's kerf: 0.1 to 0.2 mm is common for
3 mm acrylic). Four of the outside corners are left open, a thickness square.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from build123d import Align, Box, Cylinder, Location, Pos, Rot, Polygon, extrude


@dataclass
class Laser:
    size: list[float] = field(default_factory=lambda: [120.0, 80.0, 50.0])  # inside L x W x H
    thickness: float = 3.0
    kerf: float = 0.15
    finger: float | None = None  # finger width; None = about 3 x thickness
    lid: str = "fixed"  # fixed (glued or fingered on) or loose (the top's fingers dropped: a lift-off lid with a lip)
    cutouts: list[dict] = field(default_factory=list)

    def check(self):
        if len(self.size) != 3 or min(self.size) < 6 * self.thickness:
            raise ValueError(f"size: each at least {6 * self.thickness:g} mm (six thicknesses)")
        if not 1 <= self.thickness <= 12:
            raise ValueError("thickness: 1 to 12 mm")
        if not 0 <= self.kerf <= 0.6:
            raise ValueError("kerf: 0 to 0.6 mm")
        if self.lid not in ("fixed", "loose"):
            raise ValueError("lid: fixed or loose")


def _count(length, finger):
    n = max(3, int(round(length / finger)))
    return n if n % 2 else n + 1


def _edge(a, b, n, t, out_dir, even: bool):
    """Points along one edge from a to b, n fingers; on the even (or odd) places the edge steps out by t."""
    import numpy as np
    a, b, o = np.array(a, float), np.array(b, float), np.array(out_dir, float) * t
    pts = []
    for i in range(n):
        p0 = a + (b - a) * i / n
        p1 = a + (b - a) * (i + 1) / n
        out = (i % 2 == 0) == even
        if out:
            pts += [tuple(p0 + o), tuple(p1 + o)]
        else:
            pts += [tuple(p0), tuple(p1)]
    return pts


def panel_outline(w, h, t, finger, edges):
    """The outline of a w x h panel (its inside size) with fingers per edge: edges = {bottom, right,
    top, left: True (fingers on the even places), False (odd places) or None (a plain edge)}."""
    pts = []
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    dirs = {"bottom": (0, -1), "right": (1, 0), "top": (0, 1), "left": (-1, 0)}
    for i, name in enumerate(("bottom", "right", "top", "left")):
        a, b = corners[i], corners[(i + 1) % 4]
        length = abs(b[0] - a[0]) + abs(b[1] - a[1])
        e = edges.get(name)
        if e is None:
            pts += [a, b]
        else:
            pts += _edge(a, b, _count(length, finger), t, dirs[name], e)
    clean = []
    for p in pts:
        if not clean or abs(p[0] - clean[-1][0]) > 1e-9 or abs(p[1] - clean[-1][1]) > 1e-9:
            clean.append(p)
    if abs(clean[0][0] - clean[-1][0]) < 1e-9 and abs(clean[0][1] - clean[-1][1]) < 1e-9:
        clean.pop()
    return clean


def panels(box: Laser) -> dict:
    """Each panel: its size, edges and the holes on it (in the panel's own coordinates)."""
    box.check()
    L, W, H = box.size
    t = box.thickness
    f = box.finger or 3 * t
    top_edges = True if box.lid == "fixed" else None
    out = {
        "bottom": {"size": (L, W), "edges": {"bottom": True, "right": True, "top": True, "left": True}},
        "top": {"size": (L, W), "edges": {k: top_edges for k in ("bottom", "right", "top", "left")}},
        "front": {"size": (L, H), "edges": {"bottom": False, "top": False if box.lid == "fixed" else None, "left": True, "right": True}},
        "back": {"size": (L, H), "edges": {"bottom": False, "top": False if box.lid == "fixed" else None, "left": True, "right": True}},
        "left": {"size": (W, H), "edges": {"bottom": False, "top": False if box.lid == "fixed" else None, "left": False, "right": False}},
        "right": {"size": (W, H), "edges": {"bottom": False, "top": False if box.lid == "fixed" else None, "left": False, "right": False}},
    }
    from .presets import expand, resolve
    for p in out.values():
        p["holes"] = []
    face_panel = {"-Y": "front", "+Y": "back", "-X": "left", "+X": "right", "lid": "top", "floor": "bottom",
                  "front": "front", "back": "back", "left": "left", "right": "right"}
    for raw in expand(box.cutouts):
        c = resolve(dict(raw))
        name = face_panel.get(c["face"])
        if not name:
            continue
        a, b = c.get("at", [0, 0])
        if name in ("front", "back", "left", "right"):
            b = b - H / 2  # height above the inside floor, to the panel's centre
        out[name]["holes"].append({"shape": c["shape"], "size": c["size"], "at": (a, b), "radius": c.get("radius", 0.0)})
    if box.lid == "loose":
        # A lip under the loose top, inside the walls, to keep it in place.
        out["lip"] = {"size": (L - 2 * 0.3, W - 2 * 0.3), "edges": {}, "holes": [], "ring": 2 * t}
    return out


def _grow(points, d):
    """The polygon grown outward by d (the kerf's half), keeping its corners square."""
    from build123d import Face, Wire, offset, Kind
    if d <= 0:
        return points
    face = Face(Wire.make_polygon([(x, y, 0) for x, y in points], close=True))
    grown = offset(face, amount=d, kind=Kind.INTERSECTION)
    w = grown.outer_wire() if hasattr(grown, "outer_wire") else grown.faces()[0].outer_wire()
    return [(v.X, v.Y) for v in w.vertices()]


def write(box: Laser, folder) -> dict:
    """box_panels.dxf (all six laid out, labelled on a separate layer) and box_laser.step put together."""
    import ezdxf
    from build123d import Compound, export_step
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    ps = panels(box)
    t, f, k = box.thickness, box.finger or 3 * box.thickness, box.kerf
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    doc.layers.add("CUT", color=1)
    doc.layers.add("LABELS", color=5)
    msp = doc.modelspace()
    x = 0.0
    for name, p in ps.items():
        w, h = p["size"]
        outline = _grow(panel_outline(w, h, t, f, p["edges"]), k / 2)
        xs = [q[0] for q in outline]
        dx = x - min(xs)
        msp.add_lwpolyline([(q[0] + dx, q[1]) for q in outline], close=True, dxfattribs={"layer": "CUT"})
        if p.get("ring"):
            inner = (w - 2 * p["ring"], h - 2 * p["ring"])
            pts = [(-inner[0] / 2, -inner[1] / 2), (inner[0] / 2, -inner[1] / 2), (inner[0] / 2, inner[1] / 2), (-inner[0] / 2, inner[1] / 2)]
            msp.add_lwpolyline([(q[0] + dx, q[1]) for q in pts], close=True, dxfattribs={"layer": "CUT"})
        for hole in p["holes"]:
            a, b = hole["at"]
            if hole["shape"] == "round":
                msp.add_circle((a + dx, b), max(hole["size"][0] / 2 - k / 2, 0.05), dxfattribs={"layer": "CUT"})
            else:
                hw, hh = hole["size"][0] - k, hole["size"][1] - k
                msp.add_lwpolyline([(a + dx - hw / 2, b - hh / 2), (a + dx + hw / 2, b - hh / 2), (a + dx + hw / 2, b + hh / 2),
                                    (a + dx - hw / 2, b + hh / 2)], close=True, dxfattribs={"layer": "CUT"})
        msp.add_text(name, height=min(6, h / 6), dxfattribs={"layer": "LABELS"}).set_placement((dx - w / 4, -h / 2 + t + 2))
        x = max(q[0] + dx for q in outline) + 6
    p_dxf = folder / "box_panels.dxf"
    doc.saveas(p_dxf)
    whole = assembled(box)
    step = folder / "box_laser.step"
    export_step(whole, str(step))
    L, W, H = box.size
    notes = [f"six panels from {t:g} mm sheet, inside {L:g} x {W:g} x {H:g} mm, outside {L + 2 * t:g} x {W + 2 * t:g} x {H + 2 * t:g} mm",
             f"fingers about {f:g} mm; outlines {k / 2:g} mm bigger all round for a {k:g} mm kerf (holes {k / 2:g} mm smaller): "
             "cut a test corner first and change the kerf if it's loose or won't go",
             "the DXF has the cuts on layer CUT and each panel's name on LABELS (engrave it, or turn it off)",
             "the top lifts off and a lip under it keeps it in place" if box.lid == "loose" else "glue the joints (acrylic cement, wood glue), or leave the top dry-fitted"]
    (folder / "notes.md").write_text("# Laser-cut box\n\n" + "\n".join(f"- {n}" for n in notes) + "\n", encoding="utf-8")
    return {"files": {"dxf": str(p_dxf), "step": str(step), "notes": str(folder / "notes.md")}, "notes": notes,
            "sheet": [round(x - 6, 1), round(max(p["size"][1] for p in ps.values()) + 2 * t, 1)]}


def assembled(box: Laser):
    """The panels as solids, put together."""
    from build123d import Compound
    ps = panels(box)
    L, W, H = box.size
    t, f = box.thickness, box.finger or 3 * box.thickness
    solids = {}
    for name, p in ps.items():
        w, h = p["size"]
        pl = extrude(Polygon(*panel_outline(w, h, t, f, p["edges"]), align=None), amount=t)
        if p.get("ring"):
            pl -= Box(w - 2 * p["ring"], h - 2 * p["ring"], t * 3)
        for hole in p["holes"]:
            a, b = hole["at"]
            tool = Cylinder(hole["size"][0] / 2, t * 3) if hole["shape"] == "round" else Box(hole["size"][0], hole["size"][1], t * 3)
            pl -= Pos(a, b, 0) * tool
        solids[name] = pl
    out = [Pos(0, 0, -t) * solids["bottom"], Pos(0, 0, H) * solids["top"]]
    out.append(Pos(0, -W / 2, H / 2) * (Rot(90, 0, 0) * solids["front"]))
    out.append(Pos(0, W / 2 + t, H / 2) * (Rot(90, 0, 0) * solids["back"]))
    out.append(Pos(-L / 2 - t, 0, H / 2) * (Rot(0, 0, 90) * (Rot(90, 0, 0) * solids["left"])))
    out.append(Pos(L / 2, 0, H / 2) * (Rot(0, 0, 90) * (Rot(90, 0, 0) * solids["right"])))
    if "lip" in solids:
        out.append(Pos(0, 0, H - t) * solids["lip"])
    return Compound(children=out)
