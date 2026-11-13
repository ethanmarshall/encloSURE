"""Front panel artwork: each face of the box drawn 1:1 in millimetres as SVG, seen from outside, with
its outline, every hole, vent slot, window and label in place, for a printed overlay, a sticker or a
panel graphic. Holes are drawn as cut lines (red) and labels as text (black); open it in Inkscape,
Illustrator or Affinity and add your artwork round them."""

from __future__ import annotations

from pathlib import Path

from .box import face_name, PLATE_LIDS
from .presets import expand, resolve

# How "along" on each wall maps to left-to-right seen from outside (the labels' convention).
SIGN = {"-Y": 1, "+Y": -1, "-X": -1, "+X": 1}


def _face_size(spec, face):
    L, W, H = spec.inner
    oL, oW = L + 2 * spec.wall, W + 2 * spec.wall
    bh = spec.base_height()
    if face in ("-Y", "+Y"):
        return oL, bh
    if face in ("-X", "+X"):
        return oW, bh
    return oL, oW


def svg(spec, face: str) -> str | None:
    """The SVG for one face, or None when nothing is on it."""
    w, h = _face_size(spec, face)
    items = []

    def to_svg(u, v):  # face coords (u right from centre, v up from the bottom or centre) -> SVG (y down)
        if face in ("lid", "floor"):
            return w / 2 + u, h / 2 - v
        return w / 2 + u, h - v

    for raw in expand(spec.cutouts):
        c = resolve(dict(raw))
        if face_name(c["face"]) != face:
            continue
        a, b = c.get("at", [0, 0])
        u = a * SIGN.get(face, 1)
        v = b + (spec.floor if face not in ("lid", "floor") else 0)
        x, y = to_svg(u, v)
        if c["shape"] == "round":
            items.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{c["size"][0] / 2:.3f}" class="cut"/>')
        else:
            cw, ch = c["size"]
            r = c.get("radius", 0) or 0
            items.append(f'<rect x="{x - cw / 2:.3f}" y="{y - ch / 2:.3f}" width="{cw:.3f}" height="{ch:.3f}" rx="{r:.3f}" class="cut"/>')
    for v_ in spec.vents:
        if face_name(v_["face"]) != face:
            continue
        (vw, vh), (a, b) = v_["size"], v_.get("at", [0, 0])
        x, y = to_svg(a * SIGN.get(face, 1), b + (spec.floor if face not in ("lid", "floor") else 0))
        items.append(f'<rect x="{x - vw / 2:.3f}" y="{y - vh / 2:.3f}" width="{vw:.3f}" height="{vh:.3f}" class="vent"/>')
    for wdw in spec.windows:
        if face_name(wdw["face"]) != face:
            continue
        (ww, wh), (a, b) = wdw["size"], wdw.get("at", [0, 0])
        x, y = to_svg(a * SIGN.get(face, 1), b + (spec.floor if face not in ("lid", "floor") else 0))
        items.append(f'<rect x="{x - ww / 2:.3f}" y="{y - wh / 2:.3f}" width="{ww:.3f}" height="{wh:.3f}" class="cut"/>')
    for t in spec.labels:
        if face_name(t["face"]) != face:
            continue
        a, b = t.get("at", [0, 0])
        x, y = to_svg(a, b + (spec.floor if face not in ("lid", "floor") else 0))
        size = t.get("size", 6.0)
        txt = str(t["text"]).replace("&", "&amp;").replace("<", "&lt;")
        items.append(f'<text x="{x:.3f}" y="{y + size * 0.35:.3f}" font-size="{size:.2f}" text-anchor="middle" class="label">{txt}</text>')
    if not items:
        return None
    r = spec.corner_radius if face in ("lid", "floor") else 0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.3f}mm" height="{h:.3f}mm" viewBox="0 0 {w:.3f} {h:.3f}">\n'
            f'<title>{face} face, seen from outside, 1:1 mm</title>\n'
            '<style>.outline{fill:none;stroke:#000;stroke-width:0.2}.cut{fill:none;stroke:#e00;stroke-width:0.2}'
            '.vent{fill:none;stroke:#e00;stroke-width:0.2;stroke-dasharray:1 0.6}.label{font-family:sans-serif;fill:#000}</style>\n'
            f'<rect x="0" y="0" width="{w:.3f}" height="{h:.3f}" rx="{r:.3f}" class="outline"/>\n' + "\n".join(items) + "\n</svg>\n")


def write(spec, folder) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    faces = ["-Y", "+Y", "-X", "+X", "floor"] + (["lid"] if spec.lid in PLATE_LIDS or spec.lid == "clamshell" else [])
    names = {"-Y": "front", "+Y": "back", "-X": "left", "+X": "right", "lid": "lid", "floor": "floor"}
    for f in faces:
        text = svg(spec, f)
        if text:
            p = folder / f"panel_{names[f]}.svg"
            p.write_text(text, encoding="utf-8")
            files[names[f]] = str(p)
    if not files:
        raise ValueError("no holes, vents, windows or labels on any face: nothing to draw")
    (folder / "README.txt").write_text("Each face 1:1 in mm, seen from outside. Red: cut lines (holes, dashed: vent areas). "
                                       "Black: the outline and labels. Print at 100% (no fit-to-page) and check one hole "
                                       "with a ruler before cutting a sticker.\n", encoding="utf-8")
    return files
