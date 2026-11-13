"""A one-page summary of a box, as a PDF: a picture, its sizes, the parts list with costs, the print
plan, the temperature estimate and anything worth a look; and the fit result when a board was checked."""

from __future__ import annotations

import io
from pathlib import Path


def _picture(ax, made):
    """The base and the lid lifted above it, shaded, from above and in front."""
    import numpy as np
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from build123d import Pos
    shapes = [(made["base"], "#8d9aa6")]
    if made.get("lid") is not None:
        bb = made["base"].bounding_box()
        shapes.append((Pos(0, 0, (bb.max.Z - bb.min.Z) * 0.45) * made["lid"], "#d9a066"))
    light = np.array([0.4, -0.5, 0.8])
    light /= np.linalg.norm(light)
    allpts = []
    for shape, colour in shapes:
        verts, tris = shape.tessellate(0.3, 0.4)
        v = np.array([[p.X, p.Y, p.Z] for p in verts])
        t = np.array(tris)
        faces = v[t]
        n = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1)[:, None], 1e-9)
        shade = 0.45 + 0.55 * np.clip(n @ light, 0, 1)
        base = np.array([int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)])
        cols = np.clip(base[None, :] * shade[:, None], 0, 1)
        ax.add_collection3d(Poly3DCollection(faces, facecolors=cols, edgecolors="none"))
        allpts.append(v)
    pts = np.vstack(allpts)
    lo, hi = pts.min(0), pts.max(0)
    mid, span = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(mid[0] - span, mid[0] + span)
    ax.set_ylim(mid[1] - span, mid[1] + span)
    ax.set_zlim(mid[2] - span, mid[2] + span)
    ax.view_init(24, -58)
    ax.set_axis_off()


def make(spec, made: dict, cost: dict | None = None, fit: dict | None = None, title: str = "EncloSURE box",
         units: str = "mm") -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    k = 25.4 if units == "in" else 1.0
    u = "in" if units == "in" else "mm"
    num = lambda x: f"{x / k:.3f}".rstrip("0").rstrip(".")  # noqa: E731
    dims = lambda v: " x ".join(num(x) for x in v) + f" {u}"  # noqa: E731
    fig = plt.figure(figsize=(8.5, 11))
    fig.text(0.06, 0.955, title, fontsize=17, weight="bold")
    fig.text(0.06, 0.935, f"Inside {dims(made['inner'])}   Outside {dims(made['outer'])}   "
             f"{spec.lid} lid, {num(spec.wall)} {u} walls", fontsize=9.5)
    ax = fig.add_axes([0.03, 0.62, 0.5, 0.3], projection="3d")
    _picture(ax, made)
    # Key facts beside the picture.
    facts = []
    est = made.get("estimate") or {}
    if est:
        facts.append(f"About {est['grams']:.0f} g of {est['material']}, {est['hours']} h to print"
                     + (" (PrusaSlicer, " + est["source"].split(", ", 1)[1] + ")" if est.get("source") else " (rough)"))
    th = made.get("thermal")
    if th:
        facts.append(f"{th['power_w']:g} W inside: air about {th['rise_c']:g} °C over the room")
    plan = made.get("print_plan") or {}
    if plan.get("base"):
        facts.append("Base: " + plan["base"])
    if plan.get("lid"):
        facts.append("Lid: " + plan["lid"])
    if spec.standoffs:
        facts.append(f"{len(spec.standoffs)} standoffs, {num(spec.standoff_height)} {u}, {spec.standoff_screw} {spec.standoff_hole}")
    if fit:
        facts.append(("Board fits" if fit.get("fits") else f"Board does not fit: {fit.get('errors')} problems")
                     + (f", {fit.get('warnings')} warnings" if fit.get("warnings") else ""))
    y = 0.9
    import textwrap
    for f_ in facts:
        for i, line in enumerate(textwrap.wrap(f_, 52)):
            fig.text(0.56, y, ("• " if i == 0 else "  ") + line, fontsize=8.5)
            y -= 0.018
        y -= 0.006
    # Parts list.
    fig.text(0.06, 0.6, "Parts", fontsize=12, weight="bold")
    rows = (cost or {}).get("rows") or []
    y = 0.58
    fig.text(0.06, y, "Qty", fontsize=8, weight="bold")
    fig.text(0.11, y, "Item", fontsize=8, weight="bold")
    fig.text(0.42, y, "Suggested part", fontsize=8, weight="bold")
    fig.text(0.86, y, "Line", fontsize=8, weight="bold")
    y -= 0.017
    for r in rows[:18]:
        fig.text(0.06, y, str(r["qty"]), fontsize=8)
        fig.text(0.11, y, r["item"][:40], fontsize=8)
        sug = f"{r.get('manufacturer', '')} {r.get('mpn', '')}".strip() if r.get("mpn") else ("printed" if r["make"] == "make" else "")
        fig.text(0.42, y, sug[:52], fontsize=8)
        if r.get("line") is not None:
            fig.text(0.86, y, f"${r['line']:.2f}", fontsize=8)
        y -= 0.016
    if cost:
        if cost.get("plastic") is not None:
            fig.text(0.11, y, f"Plastic at ${cost['filament_per_kg']:g}/kg", fontsize=8)
            fig.text(0.86, y, f"${cost['plastic']:.2f}", fontsize=8)
            y -= 0.016
        fig.text(0.11, y, "Total", fontsize=8.5, weight="bold")
        fig.text(0.86, y, f"${cost['total']:.2f}", fontsize=8.5, weight="bold")
        y -= 0.02
        for n in [cost.get("caveat", "")] + cost.get("notes", []):
            if n:
                fig.text(0.06, y, n[:110], fontsize=7, color="0.35")
                y -= 0.014
    # Checks and fit findings.
    y -= 0.01
    items = [("Check", c) for c in made.get("checks") or []]
    if fit:
        items += [(f["severity"].title(), f"{f['subject']}: {f['message']}") for f in fit.get("findings", [])]
    if items:
        fig.text(0.06, y, "Worth a look", fontsize=12, weight="bold")
        y -= 0.02
        for kind, text in items[:14]:
            for i, line in enumerate(textwrap.wrap(text, 105)):
                fig.text(0.06, y, (f"{kind}: " if i == 0 else "   ") + line, fontsize=7.5)
                y -= 0.014
                if y < 0.05:
                    break
            if y < 0.05:
                break
    fig.text(0.06, 0.025, "Made with EncloSURE. Estimates are rough; check sizes against your parts' datasheets.",
             fontsize=7, color="0.45")
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf")
    plt.close(fig)
    return buf.getvalue()


def write(spec, path, cost=None, fit=None, title="EncloSURE box", units="mm") -> str:
    from . import box
    made = box.build(spec)
    Path(path).write_bytes(make(spec, made, cost, fit, title, units))
    return str(path)
