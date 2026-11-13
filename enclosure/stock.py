"""Off-the-shelf enclosures: put cutouts in a bought box and print drilling templates.

Download the maker's 3D model of the box you bought (Hammond, for one, has a STEP for each
1590 die-cast box on its product pages), then run

    enclosure stock 1590B.step --cutout front:pg9@0,12 --cutout lid:pushbutton-22@0,0 -o out

The model must stand with its opening up (+Z). Cutouts use the same positions as
`enclosure box`: on a wall, `a` along the wall from the middle of the inside and `b` up from the
inside floor; on the lid or floor, X and Y from the middle of the inside.

You get the box with its holes as STEP (in the maker's own position, so it lines up with
anything else you have in that frame) and `drill_templates.pdf`: one 1:1 page per face as seen
from outside, with every hole drawn, centre-punch marks and dimensions from the face's
bottom-left corner. Print it at 100% ("Actual size"), check the 50 mm bar with a ruler, tape it
on and drill. A drafted (tapered) die-cast wall leans a little, so the face's outline on the
page is its largest extent; measure from the bottom edge and the middle line to be safe.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from build123d import Compound, Pos, Rot, export_step

from . import geom, shell
from .box import Cutout, _profile
from .presets import GLANDS, resolve

LETTER = (215.9, 279.4)
FACES = {
    "-X": "left (-X)", "+X": "right (+X)", "-Y": "front (-Y)", "+Y": "back (+Y)",
    "lid": "lid, from above", "floor": "floor, from below",
}


def split(path: str | Path, lid_path: str | Path | None = None):
    """The base and lid. With one file holding both, the taller solid is the base."""
    shape = geom.load(path)
    solids = sorted(shape.solids(), key=lambda s: s.volume, reverse=True)
    if not solids:
        raise ValueError(f"{path}: no solids in it")
    if lid_path:
        lid = geom.load(lid_path)
        base = solids[0] if len(solids) == 1 else Compound(children=solids)
        return base, lid
    if len(solids) == 1:
        return solids[0], None
    height = lambda s: s.bounding_box().size.Z  # noqa: E731
    solids.sort(key=height, reverse=True)
    base, lid = solids[0], solids[1]
    return base, (lid if height(lid) < 0.5 * height(base) else None)


def _frame(base, lid):
    enc, _ = shell.read(base, lid)
    (bx0, by0, bz0), (bx1, by1, bz1) = geom.bbox(base)
    (cx0, cy0, _), (cx1, cy1, _) = enc.cavity_bounds
    return enc, dict(bx0=bx0, by0=by0, bz0=bz0, bx1=bx1, by1=by1, bz1=bz1,
                     cx0=cx0, cy0=cy0, cx1=cx1, cy1=cy1, mx=(cx0 + cx1) / 2, my=(cy0 + cy1) / 2)


def _tool(c: Cutout, f: dict, enc, lid, teardrop: bool):
    """The cutting tool in the box's own frame and the hole's centre (x, y, z)."""
    if c.face in ("lid", "floor"):
        x, y = f["mx"] + c.at[0], f["my"] + c.at[1]
        if c.face == "lid":
            (_, _, z0), (_, _, z1) = geom.bbox(lid)
        else:
            z0, z1 = f["bz0"], enc.floor
        depth = (z1 - z0) + 4
        return Pos(x, y, (z0 + z1) / 2) * _profile(c.shape, c.size, c.radius, depth), (x, y, z1 if c.face == "lid" else z0)
    z = enc.floor + c.at[1]
    if c.face in ("-X", "+X"):
        edge = f["bx0"] if c.face == "-X" else f["bx1"]
        gap = (f["cx0"] - f["bx0"]) if c.face == "-X" else (f["bx1"] - f["cx1"])
        along = f["my"] + c.at[0]
        tool = _profile(c.shape, c.size, c.radius, 2 * gap + 6, teardrop)
        return Pos(edge, along, z) * (Rot(0, 90, 0) * Rot(0, 0, 90) * tool), (edge, along, z)
    edge = f["by0"] if c.face == "-Y" else f["by1"]
    gap = (f["cy0"] - f["by0"]) if c.face == "-Y" else (f["by1"] - f["cy1"])
    along = f["mx"] + c.at[0]
    tool = _profile(c.shape, c.size, c.radius, 2 * gap + 6, teardrop)
    return Pos(along, edge, z) * (Rot(90, 0, 0) * tool), (along, edge, z)


def _face_uv(face: str, p, f: dict, lid_box=None):
    """A point on a face, as seen from outside: (from the left edge, from the bottom edge), and the
    face's width and height."""
    x, y, z = p
    up = z - f["bz0"]
    h = f["bz1"] - f["bz0"]
    if face == "-X":  # seen from -X, right is -Y
        return (f["by1"] - y, up), (f["by1"] - f["by0"], h)
    if face == "+X":
        return (y - f["by0"], up), (f["by1"] - f["by0"], h)
    if face == "-Y":
        return (x - f["bx0"], up), (f["bx1"] - f["bx0"], h)
    if face == "+Y":
        return (f["bx1"] - x, up), (f["bx1"] - f["bx0"], h)
    if face == "lid":
        (lx0, ly0, _), (lx1, ly1, _) = lid_box
        return (x - lx0, y - ly0), (lx1 - lx0, ly1 - ly0)
    # floor, seen from below: right is -X
    return (f["bx1"] - x, y - f["by0"]), (f["bx1"] - f["bx0"], f["by1"] - f["by0"])


def cut(base, lid, cutouts: list[dict], teardrop: bool = False) -> dict:
    """The base and lid with their holes, each hole's place on its face, and checks."""
    enc, f = _frame(base, lid)
    checks, holes = [], []
    lid_box = geom.bbox(lid) if lid is not None else None
    for raw in cutouts:
        c = Cutout(**resolve(raw))
        c.check()
        if c.face == "lid" and lid is None:
            raise ValueError("a lid cutout needs the lid: pass --lid, or a STEP holding both parts")
        tool, centre = _tool(c, f, enc, lid, teardrop)
        target = lid if c.face == "lid" else base
        before = target.volume
        target = target - tool
        if c.face == "lid":
            lid = target
        else:
            base = target
        if before - target.volume < 1e-3:
            checks.append(f"{c.face} cutout at {c.at}: it missed the part, so nothing was cut")
        w = c.size[0]
        h = c.size[1] if c.shape == "rect" else c.size[0]
        (u, v), (fw, fh) = _face_uv(c.face, centre, f, lid_box)
        # Room on the face: walls from the floor to the rim, lid and floor inside the walls.
        if c.face in ("-X", "+X", "-Y", "+Y"):
            span = (f["cy1"] - f["cy0"]) if c.face in ("-X", "+X") else (f["cx1"] - f["cx0"])
            if abs(c.at[0]) + w / 2 > span / 2 - 1 or c.at[1] - h / 2 < 1 or enc.floor + c.at[1] + h / 2 > enc.rim - 1:
                checks.append(f"{c.face} cutout at {c.at}: within 1 mm of an inside corner, the floor or the rim")
        for b in enc.bosses:
            if c.face in ("lid", "floor") and math.dist(b.center[:2], centre[:2]) < (b.diameter + w) / 2:
                checks.append(f"{c.face} cutout at {c.at}: over the boss at {b.center[:2]}")
        if c.preset in GLANDS and c.face != "lid":
            nut = w * 1.6  # a gland's locknut is roughly 1.5-1.7 times the thread across its flats
            if c.at[1] - nut / 2 < 0 and c.face != "floor":
                checks.append(f"{c.face} {c.preset} at {c.at}: its locknut (about {nut:.0f} mm) may not clear the floor inside")
        holes.append({"face": c.face, "shape": c.shape, "size": [w, h] if c.shape == "rect" else [w],
                      "radius": c.radius, "preset": c.preset, "source": c.source,
                      "from_left": round(u, 2), "from_bottom": round(v, 2), "face_size": [round(fw, 2), round(fh, 2)]})
    return {"base": base, "lid": lid, "holes": holes, "checks": checks, "enclosure": enc}


def templates(holes: list[dict], path: str | Path, title: str = "") -> str:
    """One 1:1 drilling template page per face, as a PDF."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

    margin = 22.0
    mm = 1 / 25.4
    with PdfPages(path) as pdf:
        for face in FACES:
            mine = [h for h in holes if h["face"] == face]
            if not mine:
                continue
            fw, fh = mine[0]["face_size"]
            need = (max(fw + 2 * margin, 120.0), fh + 2 * margin + 30)
            # A Letter page when it fits (it prints at 100% everywhere), else one just big enough.
            if need[0] <= LETTER[0] and need[1] <= LETTER[1]:
                W, H = LETTER
            elif need[0] <= LETTER[1] and need[1] <= LETTER[0]:
                W, H = LETTER[1], LETTER[0]
            else:
                W, H = need
            fig = plt.figure(figsize=(W * mm, H * mm))
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set_xlim(0, W)
            ax.set_ylim(0, H)
            ax.set_aspect("equal")
            ax.axis("off")
            ox, oy = margin, H - margin - 12 - fh
            ax.add_patch(Rectangle((ox, oy), fw, fh, fill=False, lw=0.6))
            ax.plot([ox + fw / 2] * 2, [oy - 3, oy + fh + 3], lw=0.25, ls=(0, (6, 2, 1, 2)), color="0.4")
            for h in mine:
                u, v = ox + h["from_left"], oy + h["from_bottom"]
                if h["shape"] == "round":
                    ax.add_patch(Circle((u, v), h["size"][0] / 2, fill=False, lw=0.5))
                    r = h["size"][0] / 2
                    label = f"Ø{h['size'][0]:g}"
                else:
                    w, hh = h["size"]
                    rr = min(h.get("radius") or 0, min(w, hh) / 2)
                    ax.add_patch(FancyBboxPatch((u - w / 2 + rr, v - hh / 2 + rr), w - 2 * rr, hh - 2 * rr,
                                                boxstyle=f"round,pad={rr}" if rr else "square,pad=0", fill=False, lw=0.5))
                    r = max(w, hh) / 2
                    label = f"{w:g} x {hh:g}"
                ax.plot([u - r - 2, u + r + 2], [v, v], lw=0.25, color="k")
                ax.plot([u, u], [v - r - 2, v + r + 2], lw=0.25, color="k")
                ax.plot([u], [v], marker="+", ms=4, mew=0.4, color="k")
                if h.get("preset"):
                    label += f" ({h['preset']})"
                ax.text(u + r + 1.5, v + 1, f"{label}\n{h['from_left']:g} from left, {h['from_bottom']:g} up",
                        fontsize=5.5, va="bottom")
            name = FACES[face]
            ax.text(margin, H - 8, f"{title}  {name}".strip(), fontsize=8, weight="bold")
            ax.text(margin, H - 13, "Print at 100% (Actual size). Dimensions in mm from the outline's bottom-left corner.",
                    fontsize=5.5)
            by = oy - 14
            ax.plot([margin, margin + 50], [by, by], lw=1.2, color="k")
            for x in (margin, margin + 50):
                ax.plot([x, x], [by - 1.5, by + 1.5], lw=0.6, color="k")
            ax.text(margin + 52, by - 1, "50 mm: check this with a ruler", fontsize=5.5)
            pdf.savefig(fig)
            plt.close(fig)
    return str(path)


def run(base_path, cutouts: list[dict], folder, lid_path=None, teardrop=False) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    base, lid = split(base_path, lid_path)
    made = cut(base, lid, cutouts, teardrop)
    files = {}
    export_step(made["base"], str(folder / "base.step"))
    files["base"] = str(folder / "base.step")
    if made["lid"] is not None:
        export_step(made["lid"], str(folder / "lid.step"))
        files["lid"] = str(folder / "lid.step")
    if made["holes"]:
        files["templates"] = templates(made["holes"], folder / "drill_templates.pdf", Path(base_path).stem)
    (folder / "holes.json").write_text(json.dumps(made["holes"], indent=2) + "\n")
    files["holes"] = str(folder / "holes.json")
    enc = made["enclosure"]
    return {"files": files, "inside": [round(enc.cavity_bounds[1][i] - enc.cavity_bounds[0][i], 2) for i in range(3)],
            "holes": made["holes"], "checks": made["checks"]}
