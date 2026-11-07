"""Writing the enclosure's limits into a KiCad board, through KiCad's own `pcbnew` module.

The board gets:
- an Edge.Cuts outline: the cavity at board height, inset by the clearance;
- a mounting hole on each standoff, sized for its screw, with a keepout ring for the screw head;
- notes on User.1: the tallest part allowed on top (to the lid, or the rim) and underneath (to
  the floor), and the frame;
- markers on User.2 for each opening: at the board edge for a wall opening (its width, and its
  height above the board's top), and over the board for a lid opening (a button or display).

KiCad's Y axis points down, so the enclosure's (x, y) is KiCad's (x0 + x, y0 - y), with
(x0, y0) the page position of the enclosure's origin, stored on User.1 and returned.
"""

from __future__ import annotations

import math
from pathlib import Path

from .shell import Enclosure, board_hole_for

try:
    import pcbnew
except ImportError:  # KiCad's Python module comes with KiCad itself
    pcbnew = None

ORIGIN = (150.0, 100.0)  # where the enclosure's origin lands on KiCad's page, mm


def _mm(v: float) -> int:
    return pcbnew.FromMM(v)


def _pt(x: float, y: float, origin=ORIGIN):
    return pcbnew.VECTOR2I(_mm(origin[0] + x), _mm(origin[1] - y))


def _line(board, layer, a, b, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(a)
    s.SetEnd(b)
    s.SetLayer(layer)
    s.SetWidth(_mm(width))
    board.Add(s)


def _text(board, layer, at, text, size=1.0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(at)
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(_mm(size), _mm(size)))
    t.SetTextThickness(_mm(size * 0.15))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    board.Add(t)


def _circle(board, layer, center, r, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_CIRCLE)
    s.SetCenter(center)
    s.SetEnd(pcbnew.VECTOR2I(center.x + _mm(r), center.y))
    s.SetLayer(layer)
    s.SetWidth(_mm(width))
    board.Add(s)


def _keepout(board, center, r, name):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(True)
    z.SetDoNotAllowFootprints(True)
    z.SetDoNotAllowCopperPour(False)
    z.SetZoneName(name)
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    poly = z.Outline()
    poly.NewOutline()
    for i in range(24):
        a = 2 * math.pi * i / 24
        poly.Append(center.x + _mm(r * math.cos(a)), center.y + _mm(r * math.sin(a)))
    board.Add(z)


def _hole(board, center, d, ref):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue(f"MountingHole_{d:.1f}mm")
    fp.SetPosition(center)
    fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    pad = pcbnew.PAD(fp)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I(_mm(d), _mm(d)))
    pad.SetDrillSize(pcbnew.VECTOR2I(_mm(d), _mm(d)))
    pad.SetPosition(center)
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.B_Cu)
    ls.AddLayer(pcbnew.F_Mask)
    ls.AddLayer(pcbnew.B_Mask)
    pad.SetLayerSet(ls)
    fp.Add(pad)
    board.Add(fp)
    return fp


def limits(enc: Enclosure, out: str | Path, clearance: float = 0.5, pcb_thickness: float = 1.6,
           origin=ORIGIN) -> dict:
    """Write a .kicad_pcb holding the enclosure's limits. Returns what was written."""
    if pcbnew is None:
        raise RuntimeError("writing KiCad boards needs KiCad's Python module (pcbnew): install KiCad")
    if not enc.bosses:
        raise ValueError("the enclosure has no standoffs to mount a board on")
    board = pcbnew.BOARD()
    board.GetDesignSettings().SetBoardThickness(_mm(pcb_thickness))
    seat = max(b.top for b in enc.bosses)
    top = seat + pcb_thickness
    (x0, y0, _), (x1, y1, _) = enc.cavity_bounds
    x0, y0, x1, y1 = x0 + clearance, y0 + clearance, x1 - clearance, y1 - clearance
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        _line(board, pcbnew.Edge_Cuts, _pt(*a, origin=origin), _pt(*b, origin=origin), 0.1)

    holes = []
    for i, boss in enumerate(enc.bosses, 1):
        d = board_hole_for(boss.hole)
        c = _pt(boss.center[0], boss.center[1], origin=origin)
        _hole(board, c, d, f"H{i}")
        # A screw head (pan head, about 2 x the thread) plus the clearance, kept free of copper.
        head = max(boss.diameter / 2, d) + clearance
        _keepout(board, c, head, f"H{i} screw head")
        holes.append({"ref": f"H{i}", "at": boss.center[:2], "diameter": d, "screw": boss.screw,
                      "keepout_radius": round(head, 2)})

    ceiling = enc.ceiling
    up = round(ceiling - top, 2)
    down = round(seat - enc.floor, 2)
    under = "lid" if enc.lid_underside is not None else "rim (no lid given)"
    notes = [
        f"EncloSURE limits: tallest part on top {up:.2f} mm (to the {under}); underneath {down:.2f} mm (to the floor)",
        f"Board seat z {seat:.2f} mm, top z {top:.2f} mm; enclosure origin at KiCad ({origin[0]:.1f}, {origin[1]:.1f}), KiCad Y = -enclosure Y",
        f"Board edge {clearance:.2f} mm in from the walls",
    ]
    for k, n in enumerate(notes):
        _text(board, pcbnew.User_1, _pt(x0, y1 + 6 + 2.2 * (len(notes) - k), origin=origin), n, 1.2)

    marks = []
    for o in enc.openings:
        if o.wall in ("-X", "+X", "-Y", "+Y"):
            above = round(o.center[2] - top, 2)
            label = (f"{o.wall} opening {o.width:.2f} x {o.height:.2f}: centre {above:+.2f} mm above board top; "
                     f"wall {o.wall_thickness:.2f}")
            if o.wall in ("-X", "+X"):
                x = x0 if o.wall == "-X" else x1
                a, b = (x, o.center[1] - o.width / 2), (x, o.center[1] + o.width / 2)
                at = (x + (1 if o.wall == "-X" else -40), o.center[1] + o.width / 2 + 1.5)
            else:
                y = y0 if o.wall == "-Y" else y1
                a, b = (o.center[0] - o.width / 2, y), (o.center[0] + o.width / 2, y)
                at = (o.center[0] - o.width / 2, y + (2 if o.wall == "-Y" else -1.5))
            _line(board, pcbnew.User_2, _pt(*a, origin=origin), _pt(*b, origin=origin), 0.4)
            _text(board, pcbnew.User_2, _pt(*at, origin=origin), label, 0.8)
            marks.append({"wall": o.wall, "from": a, "to": b, "centre_above_board_top": above,
                          "width": o.width, "height": o.height})
        elif o.wall == "lid":
            c = _pt(o.center[0], o.center[1], origin=origin)
            _circle(board, pcbnew.User_2, c, max(o.width, o.height) / 2, 0.3)
            gap = round(o.center[2] - top, 2)
            _text(board, pcbnew.User_2, _pt(o.center[0] + max(o.width, o.height) / 2 + 1, o.center[1], origin=origin),
                  f"lid opening {o.width:.2f} x {o.height:.2f}: lid {gap:.2f} mm above board top", 0.8)
            marks.append({"wall": "lid", "at": o.center[:2], "width": o.width, "height": o.height,
                          "lid_above_board_top": gap})
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(out), board)
    return {"file": str(out), "outline": [[x0, y0], [x1, y1]], "holes": holes, "openings": marks,
            "max_height_top": up, "max_height_bottom": down, "seat": seat, "origin": list(origin)}
