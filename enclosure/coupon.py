"""A fit test print: find the gap your printer needs before printing a whole box.

The plate has a row of pockets, all the same size; each plug is that size less a different gap per
side, its gap printed on top and the same number recessed beside its pocket. Print both, push each
plug into its pocket, and use the gap of the one that fits the way you want:

- press-fit lid: the smallest gap that goes in by hand and holds when you shake the plate;
- snap lid: the same, or 0.05 mm looser;
- a lid that should drop in and lift out freely: the first one that falls out on its own.

Then set the box's fit gap (`--clearance`, or "Fit gap per side" on the page) to it.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Align, Box, Pos, Text, export_step, export_stl, extrude, fillet, Axis

GAPS = (0.10, 0.15, 0.20, 0.25, 0.30, 0.35)
POCKET = (14.0, 10.0, 4.0)  # length, width, depth, mm
PITCH = 20.0
PLATE_T = 6.0
CORNER = 1.5  # pocket corner radius, like a box's inside corners


def _rbox(L, W, H, r, z0=0.0):
    b = Pos(0, 0, z0) * Box(L, W, H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return fillet(b.edges().filter_by(Axis.Z), min(r, L / 2 - 0.01, W / 2 - 0.01)) if r > 0.05 else b


def label(g: float) -> str:
    return f"{g:.2f}".lstrip("0")


def build(gaps=GAPS):
    """(plate, plugs): the plate with its pockets and numbers, the plugs laid out to print."""
    gaps = tuple(sorted(gaps))
    if not gaps or min(gaps) < 0 or max(gaps) > 1.0:
        raise ValueError("gaps between 0 and 1 mm")
    pl, pw, pd = POCKET
    n = len(gaps)
    length = n * PITCH + 4
    width = pw + 18
    plate = _rbox(length, width, PLATE_T, 3.0)
    plugs = None
    for i, g in enumerate(gaps):
        x = -length / 2 + 2 + PITCH / 2 + i * PITCH
        plate -= Pos(x, 3.0, 0) * _rbox(pl, pw, pd + 0.01, CORNER, z0=PLATE_T - pd)
        num = extrude(Text(label(g), 4.0, align=(Align.CENTER, Align.CENTER)), amount=0.6)
        plate -= Pos(x, -width / 2 + 4.5, PLATE_T - 0.6) * num
        # The plug: smaller by the gap on every side, a bit taller than the pocket so it can be pulled.
        plug = _rbox(pl - 2 * g, pw - 2 * g, pd + 3.0, max(CORNER - g, 0.1))
        plug -= Pos(0, 0, pd + 3.0 - 0.6) * extrude(Text(label(g), 3.5, align=(Align.CENTER, Align.CENTER)), amount=0.6)
        plug = Pos(x, 0, 0) * plug
        plugs = plug if plugs is None else plugs + plug
    return plate, plugs


def write(folder, gaps=GAPS) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    plate, plugs = build(gaps)
    files = {}
    for name, shape in (("coupon_plate", plate), ("coupon_plugs", plugs)):
        export_step(shape, str(folder / f"{name}.step"))
        export_stl(shape, str(folder / f"{name}.stl"), tolerance=0.02, angular_tolerance=0.2)
        files[name] = str(folder / f"{name}.stl")
    (folder / "README.txt").write_text(__doc__.strip() + "\n\nGaps (per side, mm): " + ", ".join(label(g) for g in sorted(gaps)) + "\n")
    files["readme"] = str(folder / "README.txt")
    return {"files": files, "gaps": [round(g, 3) for g in sorted(gaps)]}
