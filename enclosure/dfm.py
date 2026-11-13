"""Ready for injection moulding? A check of a box's base and lid against the usual moulding rules:
draft on faces along the pull, even wall thickness, boss and rib thickness against the wall (sink
marks), inside corner radii, wall thickness for the plastic, and features that need side actions.

The thickness ranges are Protolabs' recommended wall thicknesses per resin; the rest are the common
rules of thumb (boss walls at most 60% of the nominal wall, inside radius at least half the wall,
outside radius the inside plus the wall, at least 0.5 to 1 degree of draft). A moulder will review
it too: this is to catch the big things before you ask for a quote.
"""

from __future__ import annotations

import math

from build123d import GeomType

# Protolabs' recommended wall thickness ranges, mm.
RESINS = {"ABS": (1.14, 3.56), "PC": (1.02, 3.81), "PC/ABS": (1.02, 3.81), "nylon": (0.76, 2.92),
          "PP": (0.64, 3.81), "acetal": (0.76, 3.05), "PBT": (0.64, 3.18), "TPE": (0.51, 3.18)}


def draft(shape, pull=(0, 0, 1), min_deg=0.5) -> dict:
    """Faces that run along the pull direction with less than *min_deg* of draft: their count and area."""
    import numpy as np
    pz = np.array(pull, float)
    pz /= np.linalg.norm(pz)
    flat_area, flat_n, total_side = 0.0, 0, 0.0
    for f in shape.faces():
        try:
            n = f.normal_at(f.center())
        except Exception:
            continue
        nv = np.array([n.X, n.Y, n.Z])
        ang = math.degrees(math.asin(min(1.0, abs(float(nv @ pz)))))  # 0 = parallel to the pull
        if ang < 45:
            total_side += f.area
            if ang < min_deg and f.geom_type in (GeomType.PLANE, GeomType.CYLINDER):
                flat_area += f.area
                flat_n += 1
    return {"faces_without_draft": flat_n, "area_mm2": round(flat_area), "side_area_mm2": round(total_side)}


def check(spec, made: dict, resin: str = "ABS") -> dict:
    """Findings for a printed-box design moving to a moulded one."""
    from .box import SCREWS, _post_boss
    if resin not in RESINS:
        raise ValueError(f"resin: one of {', '.join(RESINS)}")
    lo, hi = RESINS[resin]
    t = spec.wall
    out = []

    def add(sev, what, msg, fix=None):
        out.append({"severity": sev, "what": what, "message": msg, "fix": fix})

    if not lo <= t <= hi:
        add("error", "wall", f"{t:g} mm walls are outside {lo:g} to {hi:g} mm, the range Protolabs gives for {resin}",
            f"make the walls {min(max(t, lo), hi):g} mm")
    if abs(spec.floor - t) > 0.25 * t:
        add("warning", "floor", f"the floor ({spec.floor:g} mm) and walls ({t:g} mm) differ by more than 25%: the thick one "
            "cools slower and warps the part", f"make the floor {t:g} mm")
    if spec.lid_thickness and spec.lid in ("screw", "friction", "snap", "hinge", "living") and abs(spec.lid_thickness - t) > 0.25 * t:
        add("warning", "lid", f"the lid ({spec.lid_thickness:g} mm) and walls ({t:g} mm) differ by more than 25%", f"make the lid {t:g} mm")
    r_in = max(spec.corner_radius - t, 0.0)
    if r_in < 0.5 * t:
        add("warning", "corners", f"inside corners have a {r_in:g} mm radius: under half the wall ({0.5 * t:g} mm) they "
            "concentrate stress and the plastic flows badly round them", f"corner radius at least {t * 1.5:g} mm outside")
    if spec.standoffs:
        d, _ = spec.hole(spec.standoff_screw, spec.standoff_hole)
        boss = _post_boss(spec, d)
        bw = (boss - d) / 2
        if bw > 0.6 * t + 1e-6:
            add("warning", "bosses", f"standoff walls are {bw:.2f} mm, over 60% of the {t:g} mm wall: expect sink marks on the "
                "outside under them", f"core them out, or {0.6 * t:.2f} mm walls with gussets for strength")
        if spec.standoff_hole == "insert":
            add("info", "inserts", "heat-set inserts work in moulded parts too, or ask for ultrasonic or moulded-in inserts")
    if spec.lid == "screw":
        add("info", "posts", "the corner posts are solid columns: in a moulded part core them (a ring round the screw hole) "
            "and tie them to the walls with ribs, or they sink and take far longer to cool")
    if spec.standoff_ribs and spec.standoffs:
        if 1.2 > 0.6 * t:
            add("warning", "ribs", f"the 1.2 mm gussets are over 60% of the {t:g} mm wall: thin them to {0.5 * t:.2f} mm")
        else:
            add("info", "ribs", f"the 1.2 mm gussets are fine against a {t:g} mm wall (ribs at 50 to 60% of the wall)")
    walls = [c for c in spec.cutouts if c.get("face") in ("-X", "+X", "-Y", "+Y", "left", "right", "front", "back")]
    if walls or spec.vents or spec.windows:
        n = len(walls) + len(spec.vents) + len(spec.windows)
        add("warning", "side actions", f"{n} opening{'s' if n != 1 else ''} through the side walls need{'s' if n == 1 else ''} side "
            "actions (slides) in the mould, which cost more: or open them toward the top edge so the core can pull them", None)
    if spec.lid == "snap":
        add("warning", "undercuts", "the snap rib and groove are undercuts: they need a lifter or a bump-off design")
    if spec.teardrop:
        add("info", "teardrops", "teardrop holes are for printing: a moulded part can have round holes")
    if spec.gasket:
        add("info", "gasket", "the gasket groove moulds fine in the lid; the cord could become a moulded-in or dispensed seal")
    d_base = draft(made["base"])
    if d_base["faces_without_draft"]:
        add("warning", "draft", f"{d_base['faces_without_draft']} faces along the pull ({d_base['area_mm2']} mm²) have no draft: "
            "the part drags on the mould as it comes out", "1° on outside walls, 0.5° on inside ones; more on textured faces (1° per 0.025 mm of texture)")
    if made.get("lid") is not None:
        d_lid = draft(made["lid"], (0, 0, -1))
        if d_lid["faces_without_draft"]:
            add("info", "lid draft", f"the lid has {d_lid['faces_without_draft']} faces along its pull without draft (its lip, posts and edges)")
    errors = sum(1 for f in out if f["severity"] == "error")
    return {"resin": resin, "wall_range": [lo, hi], "findings": out, "ready": errors == 0,
            "summary": f"{errors} must-fix, {sum(1 for f in out if f['severity'] == 'warning')} to look at before a moulding quote"}
