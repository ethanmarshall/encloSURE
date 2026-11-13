"""Files for cutting a bought box's holes on a machine: a DXF of each face's holes at 1:1, and G-code.

DXF (R12, millimetres): one per face, as seen from outside, with the face's outline on layer OUTLINE
and the holes on layer HOLES, origin at the outline's bottom-left corner; for a laser, router or CAM.

G-code (millimetres, absolute, G21 G90): one program per face, the same origin, Z0 on the outside
surface. Round holes up to the drill size are drilled (G81 with retract); bigger round holes are
milled in a helix; rectangles are cut as an inside contour with the corners left at the tool's
radius. The feeds, speeds and step-down are placeholders for a 1/8" (3.175 mm) single-flute end mill
in aluminium: set them for your machine and material, and run it in the air first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Cutting:
    tool: float = 3.175  # end mill diameter, mm
    drill_max: float = 6.5  # holes up to this are drilled with a bit their size
    spindle: int = 12000
    feed: float = 300.0  # mm/min
    plunge: float = 100.0
    step_down: float = 0.3
    safe_z: float = 5.0
    breakthrough: float = 0.4  # below the inside surface


def _dxf(entities: list[str]) -> str:
    head = "0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n"
    return head + "".join(entities) + "0\nENDSEC\n0\nEOF\n"


def _line(a, b, layer):
    return f"0\nLINE\n8\n{layer}\n10\n{a[0]:.4f}\n20\n{a[1]:.4f}\n30\n0\n11\n{b[0]:.4f}\n21\n{b[1]:.4f}\n31\n0\n"


def _circle(c, r, layer):
    return f"0\nCIRCLE\n8\n{layer}\n10\n{c[0]:.4f}\n20\n{c[1]:.4f}\n30\n0\n40\n{r:.4f}\n"


def _arc(c, r, a0, a1, layer):
    return f"0\nARC\n8\n{layer}\n10\n{c[0]:.4f}\n20\n{c[1]:.4f}\n30\n0\n40\n{r:.4f}\n50\n{a0:.3f}\n51\n{a1:.3f}\n"


def _rounded_rect(cx, cy, w, h, r, layer):
    r = min(r, w / 2, h / 2)
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    if r <= 1e-6:
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return [_line(a, b, layer) for a, b in zip(pts, pts[1:] + pts[:1])]
    return [_line((x0 + r, y0), (x1 - r, y0), layer), _line((x1, y0 + r), (x1, y1 - r), layer),
            _line((x1 - r, y1), (x0 + r, y1), layer), _line((x0, y1 - r), (x0, y0 + r), layer),
            _arc((x1 - r, y0 + r), r, 270, 360, layer), _arc((x1 - r, y1 - r), r, 0, 90, layer),
            _arc((x0 + r, y1 - r), r, 90, 180, layer), _arc((x0 + r, y0 + r), r, 180, 270, layer)]


def dxf(holes: list[dict]) -> dict[str, str]:
    """A DXF per face."""
    out = {}
    for face in sorted({h["face"] for h in holes}):
        mine = [h for h in holes if h["face"] == face]
        fw, fh = mine[0]["face_size"]
        ents = _rounded_rect(fw / 2, fh / 2, fw, fh, 0, "OUTLINE")
        for h in mine:
            c = (h["from_left"], h["from_bottom"])
            if h["shape"] == "round":
                ents.append(_circle(c, h["size"][0] / 2, "HOLES"))
            else:
                ents += _rounded_rect(c[0], c[1], h["size"][0], h["size"][1], h.get("radius") or 0, "HOLES")
        out[face] = _dxf(ents)
    return out


def _n(v):
    return f"{v:.3f}".rstrip("0").rstrip(".")


def gcode(holes: list[dict], cut: Cutting | None = None) -> dict[str, str]:
    """A G-code program per face."""
    k = cut or Cutting()
    rt = k.tool / 2
    out = {}
    for face in sorted({h["face"] for h in holes}):
        mine = [h for h in holes if h["face"] == face]
        depth = max(h.get("thickness") or 3.0 for h in mine) + k.breakthrough
        g = [f"( EncloSURE: holes in the {face} face, seen from outside )",
             "( Origin: the face outline's bottom-left corner. Z0: the outside surface. mm. )",
             f"( Tool: {k.tool:g} mm end mill; drills up to {k.drill_max:g} mm. Depth {depth:.2f} mm. )",
             "( Placeholder feeds and speeds: set them for your machine and material. Dry-run first. )",
             "G21 G90 G17 G94", f"G0 Z{_n(k.safe_z)}", f"M3 S{k.spindle}"]
        drills = [h for h in mine if h["shape"] == "round" and h["size"][0] <= k.drill_max]
        for d in sorted({h["size"][0] for h in drills}):
            g.append(f"( Drill {d:g} mm: change to a {d:g} mm bit )")
            g.append("M5")
            g.append(f"M0 ( load the {d:g} mm drill )")
            g.append(f"M3 S{k.spindle}")
            for h in [h for h in drills if h["size"][0] == d]:
                g.append(f"G98 G81 X{_n(h['from_left'])} Y{_n(h['from_bottom'])} Z{_n(-depth)} R{_n(k.safe_z / 2)} F{_n(k.plunge)}")
            g.append("G80")
        mills = [h for h in mine if h not in drills]
        if mills:
            g += ["M5", f"M0 ( load the {k.tool:g} mm end mill )", f"M3 S{k.spindle}"]
        for h in mills:
            x, y = h["from_left"], h["from_bottom"]
            if h["shape"] == "round":
                r = h["size"][0] / 2 - rt
                if r <= 0:
                    continue
                g.append(f"( Hole Ø{h['size'][0]:g} at {_n(x)}, {_n(y)}: helix )")
                g += [f"G0 X{_n(x + r)} Y{_n(y)}", f"G0 Z{_n(k.safe_z / 2)}", f"G1 Z0 F{_n(k.plunge)}"]
                z = 0.0
                while z > -depth + 1e-9:
                    z = max(z - k.step_down, -depth)
                    g.append(f"G2 X{_n(x + r)} Y{_n(y)} I{_n(-r)} J0 Z{_n(z)} F{_n(k.feed)}")
                g += [f"G2 X{_n(x + r)} Y{_n(y)} I{_n(-r)} J0", f"G0 Z{_n(k.safe_z)}"]
            else:
                w, hh = h["size"][0] - 2 * rt, h["size"][1] - 2 * rt
                if w <= 0 or hh <= 0:
                    continue
                x0, y0, x1, y1 = x - w / 2, y - hh / 2, x + w / 2, y + hh / 2
                g.append(f"( Rectangle {h['size'][0]:g} x {h['size'][1]:g} at {_n(x)}, {_n(y)}: inside contour, corners R{rt:g} )")
                g += [f"G0 X{_n(x0)} Y{_n(y0)}", f"G0 Z{_n(k.safe_z / 2)}", f"G1 Z0 F{_n(k.plunge)}"]
                z = 0.0
                while z > -depth + 1e-9:
                    z = max(z - k.step_down, -depth)
                    g += [f"G1 Z{_n(z)} F{_n(k.plunge)}", f"G1 X{_n(x1)} Y{_n(y0)} F{_n(k.feed)}", f"G1 X{_n(x1)} Y{_n(y1)}",
                          f"G1 X{_n(x0)} Y{_n(y1)}", f"G1 X{_n(x0)} Y{_n(y0)}"]
                g.append(f"G0 Z{_n(k.safe_z)}")
        g += ["M5", f"G0 Z{_n(k.safe_z)}", "M30"]
        out[face] = "\n".join(g) + "\n"
    return out


def write(holes: list[dict], folder, cut: Cutting | None = None) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    names = {"-X": "left", "+X": "right", "-Y": "front", "+Y": "back", "lid": "lid", "floor": "floor"}
    files = {}
    for face, text in dxf(holes).items():
        p = folder / f"{names[face]}.dxf"
        p.write_text(text)
        files[f"{names[face]}_dxf"] = str(p)
    for face, text in gcode(holes, cut).items():
        p = folder / f"{names[face]}.nc"
        p.write_text(text)
        files[f"{names[face]}_gcode"] = str(p)
    return files
