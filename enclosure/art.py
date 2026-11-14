"""Artwork for a face: a logo or drawing from an SVG or DXF, made into flat faces the width you ask
for, centred on the origin and reading the right way up, to raise or engrave like a label.

SVG: filled shapes become solid (holes in them stay holes, as the SVG's fill rule draws them); lines
with no fill become strokes `line` mm wide. DXF: closed shapes are filled (a shape inside another is
a hole), open lines become strokes. Raster images (PNG, JPG) need tracing to an SVG first (Inkscape's
Trace Bitmap does it)."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

MAX_BYTES = 400_000


def _from_svg(text: str):
    from build123d import Face, Wire, import_svg
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = f.name
    try:
        shapes = import_svg(path, flip_y=True, align=None)
    finally:
        Path(path).unlink(missing_ok=True)
    faces = [s for s in shapes if isinstance(s, Face)]
    wires = [s for s in shapes if isinstance(s, Wire)]
    return faces, wires


def _from_dxf(text: str):
    import ezdxf
    from ezdxf import path as dxfpath
    from build123d import Face, Wire
    doc = ezdxf.read(io.StringIO(text))
    closed, open_ = [], []
    for e in doc.modelspace():
        t = e.dxftype()
        if t in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "SPLINE", "ELLIPSE"):
            try:
                p = dxfpath.make_path(e)
            except Exception:
                continue
            pts = [(v.x, v.y) for v in p.flattening(0.02)]
            if len(pts) < 2:
                continue
            is_closed = t == "CIRCLE" or (t in ("LWPOLYLINE", "POLYLINE") and e.closed) or \
                (len(pts) > 2 and abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6)
            if is_closed:
                if abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
                    pts = pts[:-1]
                if len(pts) >= 3:
                    closed.append(Face(Wire.make_polygon([(x, y, 0) for x, y in pts], close=True)))
            else:
                open_.append(Wire.make_polygon([(x, y, 0) for x, y in pts], close=False))
    # A closed shape inside another is a hole in it (even-odd, like most drawings mean).
    closed.sort(key=lambda f: -f.area)
    faces = []
    for f in closed:
        inside = [g for g in faces if g.is_inside(f.center())]
        depth = sum(1 for g in closed if g is not f and g.area > f.area and g.is_inside(f.center()))
        if depth % 2 == 0:
            faces.append(f)
        else:
            # Cut it from the shape it's in.
            for i, g in enumerate(faces):
                if g.is_inside(f.center()):
                    faces[i] = g - f
                    break
    return [f for f in faces], open_


def shape(data: str, kind: str, width: float, line: float = 0.8):
    """The artwork as a 2D shape `width` mm wide, centred, y up."""
    from build123d import Compound, Pos, scale
    if len(data.encode()) > MAX_BYTES:
        raise ValueError(f"artwork: up to {MAX_BYTES // 1000} kB (simplify it, or save it as plain SVG)")
    if kind == "svg":
        faces, wires = _from_svg(data)
    elif kind == "dxf":
        faces, wires = _from_dxf(data)
    else:
        raise ValueError("artwork: SVG or DXF (trace a PNG or JPG to SVG first)")
    if not faces and not wires:
        raise ValueError("no shapes found in the artwork: it needs filled shapes or lines")
    parts = list(faces)
    # Scale first, so the stroke width is in final mm.
    allshape = Compound(children=parts + list(wires))
    bb = allshape.bounding_box()
    if bb.size.X <= 0:
        raise ValueError("the artwork has no width")
    k = width / bb.size.X
    cx, cy = (bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2
    def move(s):
        from build123d import Wire
        out_ = scale(Pos(-cx, -cy, 0) * s, by=k)
        if isinstance(s, Wire) and not isinstance(out_, Wire):  # scaling hands back a Curve: its wire
            return out_.wires()[0] if out_.wires() else Wire(out_.edges())
        return out_
    out = [move(f) for f in parts]
    for w in wires:
        try:
            out.append(_stroke(move(w), line))
        except Exception:
            continue
    if not out:
        raise ValueError("nothing in the artwork could be made solid")
    return out, (width, bb.size.Y * k)


def solid(data: str, kind: str, width: float, depth: float, line: float = 0.8):
    """The artwork extruded `depth` mm up from z = 0, as one solid (its faces fused in 3D, which is
    sturdier than fusing them flat)."""
    from build123d import extrude
    faces, size = shape(data, kind, width, line)
    bodies = []
    for f in faces:
        try:
            bodies.append(extrude(f, amount=depth))
        except Exception:
            continue
    if not bodies:
        raise ValueError("nothing in the artwork could be made solid")
    body = bodies[0].fuse(*bodies[1:]) if len(bodies) > 1 else bodies[0]
    return body, size


def _stroke(wire, line: float):
    """A line drawn `line` mm wide."""
    from build123d import Face, Kind, Side
    return Face(wire.offset_2d(line / 2, kind=Kind.ARC, side=Side.BOTH))
