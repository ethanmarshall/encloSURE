"""Worst-case gaps between the board and the box, once real-world errors stack up.

Nominal gaps come from the fit check. Each is then reduced by what can go wrong at once:
- the board's outline, routed by the fab (typically ±0.2 mm);
- where the printer puts each standoff and wall (typically ±0.15 mm on a tuned printer);
- the plastic shrinking as it cools, over the distance from the box's middle (PLA about 0.3%,
  PETG 0.4%, ABS and ASA 0.7%; a slicer's shrink compensation takes most of it back).

These are typical figures, not your printer's or fab's: change them in Tolerances if you know better.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass

from .fit import mounting_holes
from .geom import bbox

SHRINK = {"PLA": 0.003, "PETG": 0.004, "ABS": 0.007, "ASA": 0.007}
SCREW_D = {"M2": 2.0, "M2.5": 2.5, "M3": 3.0, "M4": 4.0}


@dataclass
class Tolerances:
    board_outline: float = 0.2  # ± fab routing
    board_holes: float = 0.1  # ± drilled hole position
    print_position: float = 0.15  # ± where a printed feature lands
    material: str = "PETG"
    shrink_compensated: bool = False


def stack(enc, fit, tol: Tolerances | None = None) -> dict:
    """Worst-case board-edge gaps per side, and whether the screws still all go in."""
    t = tol or Tolerances()
    shrink = 0.0 if t.shrink_compensated else SHRINK.get(t.material, 0.004)
    (bx0, by0, _), (bx1, by1, _) = bbox(fit.pcb)
    (wx0, wy0, _), (wx1, wy1, _) = enc.cavity_bounds
    cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
    rows, findings = [], []
    for side, gap, dist in (("-X", bx0 - wx0, abs(wx0 - cx)), ("+X", wx1 - bx1, abs(wx1 - cx)),
                            ("-Y", by0 - wy0, abs(wy0 - cy)), ("+Y", wy1 - by1, abs(wy1 - cy))):
        loss = t.board_outline + t.print_position + shrink * dist
        worst = gap - loss
        rows.append({"what": f"board edge to the {side} wall", "nominal": round(gap, 2), "worst": round(worst, 2),
                     "loses": round(loss, 2)})
        if worst < -0.05:
            findings.append({"severity": "warning", "code": "tolerance_tight", "subject": f"board edge {side}",
                             "message": f"{gap:.2f} mm nominal, {worst:.2f} mm worst case: the board may not drop in",
                             "fix": f"pull the board edge in {-worst + 0.1:.2f} mm"})
    # Screws: each board hole floats round its screw; the misplacement between standoff and hole
    # must stay inside that float.
    for boss in enc.bosses:
        m = re.match(r"(M\d(?:\.\d)?)", boss.screw or "")
        d_screw = SCREW_D.get(m.group(1), 3.0) if m else 3.0
        holes = mounting_holes(fit.pcb)
        near = min(holes, key=lambda h: math.dist(h[:2], boss.center[:2]), default=None)
        if near is None or math.dist(near[:2], boss.center[:2]) > 3:
            continue
        float_ = (near[2] - d_screw) / 2
        off = math.dist(near[:2], boss.center[:2])
        dist = math.dist(boss.center[:2], (cx, cy))
        miss = off + t.board_holes + t.print_position + shrink * dist
        rows.append({"what": f"screw at ({boss.center[0]:.1f}, {boss.center[1]:.1f})", "float": round(float_, 2),
                     "worst_misplacement": round(miss, 2), "spare": round(float_ - miss, 2),
                     "note": "fine in practice up to about 0.25 mm short: inserts and printed standoffs give a little"})
        if miss > float_ + 0.25:  # past what inserts and printed standoffs usually give
            findings.append({"severity": "warning", "code": "tolerance_tight", "subject": f"screw at ({boss.center[0]:.1f}, {boss.center[1]:.1f})",
                             "message": f"the hole floats {float_:.2f} mm round the screw, but the standoff can be "
                                        f"{miss:.2f} mm off: the last screw may not go in",
                             "fix": f"open the board hole to Ø{d_screw + 2 * miss + 0.1:.1f}, or use shrink compensation"})
    return {"tolerances": asdict(t), "shrink": shrink, "rows": rows, "findings": findings}
