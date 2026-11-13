"""What the box can claim: the IP rating to expect from its openings and seal (IEC 60529's probe
sizes: a first digit of 1 keeps out 50 mm, 2 keeps out 12.5 mm fingers, 3 keeps out 2.5 mm tools,
4 keeps out 1 mm wires, 5 is dust protected, 6 dust tight). A rating is only real once tested: this
says what the design can reach at best and what holds it back."""

from __future__ import annotations

from .box import face_name, _honeycomb
from .presets import GLANDS, expand, resolve

# Panel parts that seal their own hole when the part is a sealed type (glands, M8/M12 panel connectors).
SEALING = set(GLANDS) | {"m8-panel", "m12-panel"}


def _first_digit(gap: float | None) -> int:
    if gap is None:
        return 5
    if gap < 1.0:
        return 4
    if gap < 2.5:
        return 3
    if gap < 12.5:
        return 2
    if gap < 50:
        return 1
    return 0


def ip_guide(spec) -> dict:
    openings = []  # (smallest dimension that a probe could pass, what)
    for raw in expand(spec.cutouts):
        c = resolve(dict(raw))
        if c.get("preset") in SEALING:
            continue
        smallest = min(c["size"]) if c["shape"] == "rect" else c["size"][0]
        openings.append((smallest, c.get("preset") or f"{c['shape']} hole on {face_name(c['face'])}"))
    for v in spec.vents:
        if v.get("pattern") == "honeycomb":
            openings.append((v.get("cell", 4.0), f"honeycomb vent on {face_name(v['face'])}"))
        else:
            openings.append((v.get("slot", 2.0), f"vent slots on {face_name(v['face'])}"))
    for sr in spec.strain_reliefs:
        openings.append((0.8, "the gap round a strain-relief cable"))
    if spec.battery_door:
        openings.append((spec.fit_clearance * 2, "the battery door's edge"))
    for n in spec.cable_notches:
        openings.append((float(n.get("d", 6)), "a cable notch"))
    sealed_lid = bool(spec.gasket)
    if spec.lid not in ("none",) and not sealed_lid:
        openings.append((spec.fit_clearance, "the lid's seam (no gasket)"))
    if spec.lid == "none":
        openings.append((min(spec.inner[:2]), "the open top"))
    gap = max((o[0] for o in openings), default=None)
    first = _first_digit(gap)
    limiting = [what for size, what in openings if size == gap] if gap is not None else []
    if not openings and sealed_lid:
        first_txt = "5 or 6 (dust protected; dust tight takes a good gasket and a test)"
    else:
        first_txt = str(first)
    if sealed_lid and all(size < 0.01 for size, _ in openings):
        second, second_txt = 5, "5 to 7 is possible with the gasket and sealed glands; it needs a water test"
    elif sealed_lid and not openings:
        second, second_txt = 5, "5 to 7 is possible with the gasket and sealed glands; it needs a water test"
    else:
        second, second_txt = 0, "0: open holes or an unsealed lid let water in"
    code = f"IP{first if openings or not sealed_lid else 5}{second}"
    reasons = []
    if limiting:
        reasons.append(f"the biggest opening is {gap:g} mm across ({', '.join(limiting[:3])}), which sets the first digit")
    if not sealed_lid and spec.lid != "none":
        reasons.append("no gasket: the lid seam is open to water and fine dust (screw lid + gasket to seal it)")
    if any(c.get("preset") in SEALING for c in spec.cutouts):
        reasons.append("glands and M8/M12 connectors only seal if the parts you buy are IP-rated themselves")
    return {"code": code, "first": first_txt, "second": second_txt, "reasons": reasons,
            "note": "the best the design can reach: a real IP rating needs the IEC 60529 tests"}
