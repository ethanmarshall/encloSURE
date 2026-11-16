"""Useful printed things for the house, the shop and the bench: brackets, clamps, hooks, cable
management, tool holders, repair parts and fan parts. Each is built the way it prints (standing on
z = 0, no supports) and returns the same {shape, notes, checks, info, buy} as the hardware parts.

Wood-screw holes take a hole diameter (4.5 mm suits a #8 or 4 mm screw) and are countersunk for a
head twice that across.
"""

from __future__ import annotations

import math

from build123d import (Align, Axis, Box, Circle, Cone, Cylinder, Plane, Polygon, Pos, Rectangle, RectangleRounded,
                       RegularPolygon, Rot, chamfer, extrude, fillet, loft)

MIN_ = (Align.CENTER, Align.CENTER, Align.MIN)


def _out(shape, notes, checks=None, info=None, buy=None):
    return {"shape": shape, "notes": notes, "checks": checks or [], "info": info or {}, "buy": buy}


def _rng(name: str, v: float, lo: float, hi: float, unit: str = "mm") -> None:
    if not lo <= v <= hi:
        raise ValueError(f"{name}: {lo:g} to {hi:g} {unit}".rstrip())


def _prism(points, depth: float):
    """A flat outline in XY, `depth` tall."""
    return extrude(Polygon(*points, align=None), amount=depth, dir=(0, 0, 1))


def _csk(d: float, head_d: float | None = None, length: float = 80.0):
    """A countersunk screw hole to cut: the head's seat at z = 0, the shank down -Z, open above."""
    head_d = head_d or 2 * d
    hh = (head_d - d) / 2
    t = Pos(0, 0, -length) * Cylinder(d / 2, length + 0.01, align=MIN_)
    t += Pos(0, 0, -hh) * Cone(d / 2, head_d / 2, hh + 0.01, align=MIN_)
    t += Cylinder(head_d / 2, 60, align=MIN_)
    return t


def _spaced(n: int, lo: float, hi: float) -> list[float]:
    return [(lo + hi) / 2] if n == 1 else [lo + (hi - lo) * i / (n - 1) for i in range(n)]


# ---------- Mounts and brackets ----------

def shelf_bracket(height=100.0, depth=120.0, width=25.0, thickness=5.0, screw_d=4.5, holes=2, brace=True):
    """A shelf bracket, printed on its side so the layers run along both legs: a leg up the wall, a leg
    under the shelf, and a diagonal brace. Screws into the wall go through holes in the brace."""
    H, D, W, t, n = float(height), float(depth), float(width), float(thickness), int(holes)
    _rng("bracket height", H, 30, 300); _rng("depth", D, 30, 300); _rng("width", W, 12, 80); _rng("thickness", t, 3, 12)
    _rng("screw hole", screw_d, 2.5, 7); _rng("holes on each leg", n, 1, 4, "")
    head = 2 * screw_d
    if W < head + 6:
        raise ValueError(f"a {screw_d:g} mm screw's head needs a bracket at least {head + 6:g} mm wide")
    # Outline in XY as it prints: x out from the wall, y up; the wall leg on x = 0..t, the shelf leg on top.
    body = _prism([(0, 0), (t, 0), (t, H - t), (D, H - t), (D, H), (0, H)], W)
    checks = []
    if brace:
        a, b = (t, 0.12 * H), (0.88 * D, H - t)        # the brace's two ends
        body += _prism([(a[0] - 0.2, a[1]), (b[0], b[1] + 0.2), (b[0] - t * 1.4, b[1] + 0.2), (a[0] - 0.2, a[1] + t * 1.4)], W)
    wall_y = _spaced(n, 0.25 * H if n > 1 else 0.5 * H, 0.8 * (H - t))
    shelf_x = _spaced(n, 0.3 * D if n > 1 else 0.55 * D, 0.85 * D)
    for y in wall_y:      # into the wall: the head seats on the leg's inner face, the driver comes through the brace
        body -= Pos(t, y, W / 2) * (Rot(0, 90, 0) * _csk(screw_d, head, 40))
        body -= Pos(t + 0.5, y, W / 2) * (Rot(0, 90, 0) * Cylinder((head + 1.5) / 2, 400, align=MIN_))
    for x in shelf_x:     # up into the shelf: the head seats under the shelf leg
        body -= Pos(x, H - t, W / 2) * (Rot(90, 0, 0) * _csk(screw_d, head, 40))
        body -= Pos(x, H - t - 0.5, W / 2) * (Rot(90, 0, 0) * Cylinder((head + 1.5) / 2, 400, align=MIN_))
    if brace and W < 2.2 * (head + 1.5):
        checks.append(f"the driver holes take much of the brace's {W:g} mm width: {2.2 * (head + 1.5):.0f} mm or wider keeps it strong")
    if D > 28 * t:
        checks.append("a long, thin shelf leg will sag under load: make it thicker or shorter")
    notes = [f"shelf bracket {H:g} mm up the wall, {D:g} mm under the shelf, {W:g} wide, {t:g} thick"
             + (", with a diagonal brace" if brace else "") + f"; {n} countersunk Ø{screw_d:g} mm holes on each leg",
             "print it on its side as it lies (no supports), 4 or more walls and 40% infill or more for a shelf that carries weight"]
    return _out(body, notes, checks, {"wall_holes_up": [round(y, 1) for y in wall_y], "shelf_holes_out": [round(x, 1) for x in shelf_x]})


def corner_brace(leg=40.0, width=20.0, thickness=4.0, screw_d=4.5, holes=2, rib=True):
    """A corner brace (an angle bracket): two equal legs at 90 degrees with countersunk holes, and a
    web in the corner. Printed on its side."""
    Lg, W, t, n = float(leg), float(width), float(thickness), int(holes)
    _rng("leg", Lg, 20, 200); _rng("width", W, 10, 80); _rng("thickness", t, 2.4, 10); _rng("holes on each leg", n, 1, 4, "")
    head = 2 * screw_d
    if W < head + 4:
        raise ValueError(f"a {screw_d:g} mm screw's head needs a brace at least {head + 4:g} mm wide")
    web = min(0.35 * Lg, Lg - t - n * (head + 2)) if rib else 0.0
    web = max(web, 0.0)
    pts = [(0, 0), (Lg, 0), (Lg, t)] + ([(t + web, t), (t, t + web)] if web > 1 else [(t, t)]) + [(t, Lg), (0, Lg)]
    body = _prism(pts, W)
    pos = _spaced(n, t + web + head / 2 + 1.5, Lg - head / 2 - 2)
    for p in pos:
        body -= Pos(p, t, W / 2) * (Rot(-90, 0, 0) * _csk(screw_d, head, 40))
        body -= Pos(t, p, W / 2) * (Rot(0, 90, 0) * _csk(screw_d, head, 40))
    return _out(body, [f"corner brace {Lg:g} x {Lg:g} mm, {W:g} wide, {t:g} thick, {n} countersunk Ø{screw_d:g} mm holes on each leg"
                       + (f", a {web:.0f} mm web in the corner" if web > 1 else ""), "print it on its side as it lies"],
                [], {"holes_from_corner": [round(p, 1) for p in pos]})


def pipe_clamp(pipe_d=22.0, width=15.0, thickness=3.0, screw_d=4.5, ears=2):
    """A saddle clamp that holds a pipe, conduit or tube against a surface: a half ring over the pipe
    with a screw ear on one or both sides. Printed on its side."""
    d, W, t, n = float(pipe_d), float(width), float(thickness), int(ears)
    _rng("pipe diameter", d, 4, 160); _rng("width", W, 8, 60); _rng("thickness", t, 2, 8)
    if n not in (1, 2):
        raise ValueError("ears: 1 or 2")
    head = 2 * screw_d
    if W < head + 3:
        raise ValueError(f"a {screw_d:g} mm screw's head needs a clamp at least {head + 3:g} mm wide")
    r = d / 2 + 0.2
    R = r + t
    ear = head + 5
    # Outline in XY: the surface along y = 0, the pipe's centre at (0, r).
    ring = extrude(Pos(0, r) * Circle(R), amount=W) + extrude(Pos(0, r / 2) * Rectangle(2 * R, r), amount=W)
    for s in ((-1, 1) if n == 2 else (1,)):
        ring += extrude(Pos(s * (R + ear / 2 - 0.1), t / 2) * Rectangle(ear + 0.2, t), amount=W)
    ring -= extrude(Pos(0, r) * Circle(r), amount=W * 3, both=True)
    ring -= extrude(Pos(0, r / 2 - 0.5) * Rectangle(2 * r, r + 1), amount=W * 3, both=True)
    ring -= Pos(0, -50, W / 2) * Box(4 * R + 4 * ear, 100, W * 3)       # nothing below the surface
    for s in ((-1, 1) if n == 2 else (1,)):
        ring -= Pos(s * (R + ear / 2), t, W / 2) * (Rot(-90, 0, 0) * _csk(screw_d, head, 40))
    notes = [f"saddle clamp for a Ø{d:g} mm pipe: {W:g} mm wide, {t:g} mm thick, {n} ear{'s' if n > 1 else ''} with a countersunk "
             f"Ø{screw_d:g} mm hole" + (f", holes {2 * (R + ear / 2):.1f} mm apart" if n == 2 else ""), "print it on its side as it lies"]
    return _out(ring, notes, [], {"hole_spacing": round(2 * (R + ear / 2), 2) if n == 2 else None, "over_all": round(2 * R + n * ear, 2)})


PEGBOARDS = {"1/4 in holes, 1 in apart": (6.35, 25.4, 4.8), "3/16 in holes, 1 in apart": (4.76, 25.4, 3.2),
             "6 mm holes, 25 mm apart": (6.0, 25.0, 5.0)}


def pegboard_hook(board="1/4 in holes, 1 in apart", reach=50.0, tip=10.0, arm=6.0):
    """A pegboard hook, printed on its side: a top peg that hooks up behind the board, a bottom peg
    that stops it swinging, and an arm with an upturned tip."""
    if board not in PEGBOARDS:
        raise ValueError(f"board: one of {', '.join(PEGBOARDS)}")
    hole, pitch, bt = PEGBOARDS[board]
    reach, tip, arm = float(reach), float(tip), float(arm)
    _rng("reach", reach, 10, 200); _rng("tip", tip, 0, 60); _rng("arm thickness", arm, 4, 15)
    p = hole - 0.7                      # the pegs, and how thick the whole hook prints
    bar = 5.0
    y0 = -pitch - p / 2 - 3             # the bar's bottom
    pts_bar = [(0, y0), (bar, y0), (bar, p / 2 + 3), (0, p / 2 + 3)]
    body = _prism(pts_bar, p)
    # The top peg: back through the board, then up behind it.
    body += _prism([(0.1, -p / 2), (0.1, p / 2), (-(bt + 0.8), p / 2), (-(bt + 0.8), p / 2 + 7), (-(bt + 0.8 + p), p / 2 + 7),
                    (-(bt + 0.8 + p), -p / 2)], p)
    body += _prism([(0.1, -pitch - p / 2), (0.1, -pitch + p / 2), (-(bt - 0.5), -pitch + p / 2), (-(bt - 0.5), -pitch - p / 2)], p)
    ya = -pitch / 2                     # the arm leaves the bar half way down
    body += _prism([(bar - 0.1, ya - arm / 2), (bar + reach + arm, ya - arm / 2),
                    (bar + reach + arm, ya + arm / 2 + tip), (bar + reach, ya + arm / 2 + tip), (bar + reach, ya + arm / 2),
                    (bar - 0.1, ya + arm / 2)], p)
    notes = [f"pegboard hook for {board} (board up to {bt:g} mm thick): {reach:g} mm reach, {tip:g} mm upturned tip, "
             f"{p:.1f} mm thick; tilt it to hook the top peg in, then swing it down",
             "print it on its side as it lies; the layers then run along the arm, which is what makes it strong"]
    checks = ["a long arm bends: for more than a kilo or so, shorten the reach or thicken the arm"] if reach > 12 * arm else []
    return _out(body, notes, checks, {"peg": round(p, 2), "pitch": pitch})


def wall_pocket(item_w=80.0, item_d=15.0, height=60.0, wall=2.4, front_slot=0.0, cable_slot=0.0, screw_d=4.5):
    """A wall holder with a pocket sized to the thing it holds (a phone, a remote, a meter, a tool):
    open at the top, a slot down the front and one through the floor if you want them, and two
    screw holes in the back above the pocket."""
    w, d, h, t = float(item_w), float(item_d), float(height), float(wall)
    _rng("item width", w, 10, 300); _rng("item depth", d, 3, 150); _rng("pocket height", h, 10, 250); _rng("wall", t, 1.6, 6)
    iw, idp = w + 1.0, d + 1.0
    head = 2 * screw_d
    back_h = h + t + head + 10
    body = Pos(0, idp / 2 + t, 0) * Box(iw + 2 * t, t, back_h, align=(Align.CENTER, Align.MIN, Align.MIN))       # the back
    body += Pos(0, 0, 0) * Box(iw + 2 * t, idp + 2 * t, h + t, align=MIN_)
    body -= Pos(0, 0, t) * Box(iw, idp, h + 1, align=MIN_)
    if front_slot > 0:
        fs = min(float(front_slot), iw - 6)
        body -= Pos(0, -(idp / 2 + t / 2), t + h * 0.25) * Box(fs, t * 3, h, align=MIN_)
        body -= Pos(0, -(idp / 2 + t / 2), t + h * 0.25) * (Rot(90, 0, 0) * Cylinder(fs / 2, t * 3))
    if cable_slot > 0:
        cs = min(float(cable_slot), iw - 6, idp)
        body -= Pos(0, -idp / 4, -1) * Box(cs, idp / 2 + t + 2, t + 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
    sx = max(0.0, (iw + 2 * t) / 2 - head / 2 - 4)
    for x in ((-sx, sx) if sx > head else (0.0,)):
        body -= Pos(x, idp / 2 + t, h + t + head / 2 + 4) * (Rot(-90, 0, 0) * _csk(screw_d, head, 40))
    try:
        body = fillet(body.edges().filter_by(Axis.Z).group_by(Axis.Y)[0], min(2.0, t * 0.8))
    except Exception:
        pass
    notes = [f"wall pocket for something {w:g} x {d:g} mm: inside {iw:g} x {idp:g} x {h:g} mm deep, walls {t:g} mm, "
             f"countersunk Ø{screw_d:g} mm holes in the back above the pocket"
             + (f", a {front_slot:g} mm slot down the front" if front_slot > 0 else "")
             + (f", a {cable_slot:g} mm cable slot through the floor" if cable_slot > 0 else ""),
             "print it standing as it hangs, no supports"]
    return _out(body, notes, [], {"inside": [iw, idp, h], "outside": [iw + 2 * t, idp + 2 * t, round(back_h, 1)]})


# ---------- Cable management ----------

def cable_comb(cables=6, cable_d=5.0, thickness=5.0, mount=False, screw_d=3.5):
    """A cable comb: a bar with a row of round seats, each open at the top by a narrower slot the
    cable snaps through, to keep a run of cables in order."""
    n, d, t = int(cables), float(cable_d), float(thickness)
    _rng("cables", n, 2, 30, ""); _rng("cable diameter", d, 1.5, 25); _rng("thickness", t, 3, 15)
    seat = d + 0.3
    pitch = seat + max(2.0, 0.3 * d)
    end = (2 * screw_d + 6) if mount else max(2.5, 0.4 * d)
    Lb = (n - 1) * pitch + seat + 2 * end
    Hb = seat + 2.4 + max(1.6, 0.25 * d)
    body = Pos(0, Hb / 2, 0) * Box(Lb, Hb, t, align=MIN_)
    cy = 2.4 + seat / 2
    for i in range(n):
        x = (i - (n - 1) / 2) * pitch
        body -= Pos(x, cy, -1) * Cylinder(seat / 2, t + 2, align=MIN_)
        body -= Pos(x, cy + Hb / 2, -1) * Box(0.78 * d, Hb, t + 2, align=MIN_)
    if mount:
        for s in (-1, 1):
            body -= Pos(s * (Lb / 2 - end / 2), 0, t / 2) * (Rot(90, 0, 0) * Cylinder(screw_d / 2, 100))
    notes = [f"cable comb for {n} cables of Ø{d:g} mm: seats Ø{seat:g} mm, {pitch:.1f} mm apart, entry slots {0.78 * d:.1f} mm; "
             f"{Lb:.1f} x {Hb:.1f} x {t:g} mm" + (f", a Ø{screw_d:g} mm screw hole at each end" if mount else ""), "print it flat as it lies"]
    return _out(body, notes, [], {"pitch": round(pitch, 2), "length": round(Lb, 2)})


def raceway(length=150.0, width=20.0, height=15.0, wall=1.6, screw_d=4.0, holes=2):
    """A cable raceway: a channel that screws to the surface and a lid that snaps on. The two print
    side by side, the lid upside down."""
    Ln, W, H, t, n = float(length), float(width), float(height), float(wall), int(holes)
    _rng("length", Ln, 30, 400); _rng("width", W, 10, 80); _rng("height", H, 8, 60); _rng("wall", t, 1.2, 3); _rng("holes", n, 0, 8, "")
    ch = Box(Ln, W, H, align=MIN_) - Pos(0, 0, t) * Box(Ln + 2, W - 2 * t, H, align=MIN_)
    gz = H - 2.2                                  # a V groove inside each wall for the lid's bead
    for s in (-1, 1):
        y = s * (W / 2 - t)
        ch -= Pos(-Ln / 2 - 1, 0, 0) * extrude(Plane.YZ * Polygon((y - s * 0.01, gz - 0.5), (y + s * 0.5, gz), (y - s * 0.01, gz + 0.5), align=None),
                                              amount=Ln + 2, dir=(1, 0, 0))
    for x in (_spaced(n, -Ln / 2 + 12, Ln / 2 - 12) if n else []):
        ch -= Pos(x, 0, t) * _csk(screw_d, min(2 * screw_d, W - 2 * t - 1), 20)
    # The lid, top down: a plate with two lips that go inside the walls, a bead on each.
    lw = W - 2 * t - 0.3
    lid = Box(Ln, W, 1.4, align=MIN_)
    for s in (-1, 1):
        y = s * lw / 2
        lid += Pos(0, y - s * 0.6, 1.4) * Box(Ln, 1.2, 3.4, align=MIN_)
        lid += Pos(-Ln / 2, 0, 0) * extrude(Plane.YZ * Polygon((y - s * 0.01, 1.4 + 1.7), (y + s * 0.4, 1.4 + 2.2), (y - s * 0.01, 1.4 + 2.7), align=None),
                                           amount=Ln, dir=(1, 0, 0))
    shape = ch + Pos(0, W + 6, 0) * lid
    notes = [f"raceway {Ln:g} mm long, {W:g} x {H:g} mm outside, {W - 2 * t:g} x {H - t:g} mm inside for cables"
             + (f", {n} countersunk Ø{screw_d:g} mm holes in the floor" if n else " (stick it down with tape)"),
             "the channel and its snap-on lid print side by side, the lid top down; butt lengths end to end for a longer run"]
    return _out(shape, notes, ["the lid's snap is 0.4 mm a side: if it's loose or tight, scale the lid's width by a percent"],
                {"inside": [round(W - 2 * t, 2), round(H - t, 2)]})


def desk_grommet(hole_d=60.0, depth=25.0, flange=8.0, cable_slot=22.0):
    """A desk cable grommet: a sleeve with a flange that drops into a hole through the desk, and a
    cap with a notch for the cables. Both print flat, side by side."""
    D, dp, fl, cs = float(hole_d), float(depth), float(flange), float(cable_slot)
    _rng("hole", D, 20, 120); _rng("sleeve depth", dp, 8, 60); _rng("flange", fl, 3, 20); _rng("cable notch", cs, 0, D * 0.6)
    ro, ri = D / 2 - 0.3, D / 2 - 0.3 - 2.0
    ft = 2.6
    sleeve = Cylinder(ro + fl, ft, align=MIN_) + Cylinder(ro, dp, align=MIN_)
    sleeve -= Pos(0, 0, -1) * Cylinder(ri, dp + 2, align=MIN_)
    seat = 2.0                                     # a cone seat in the flange for the cap
    sleeve -= Cone(ri + seat, ri, seat, align=MIN_)
    try:
        sleeve = chamfer(sleeve.edges().group_by(Axis.Z)[0].sort_by(lambda e: -e.length)[0:1], 1.0)
    except Exception:
        pass
    cap = Cone(ri + seat - 0.2, ri - 0.2, seat, align=MIN_)
    if cs > 0:
        cap -= Pos(0, ri, -1) * Box(cs, 2 * ri, 10, align=MIN_)
        cap -= Pos(0, 0, -1) * Cylinder(cs / 2, 10, align=MIN_)
    shape = sleeve + Pos(2 * (ro + fl) + 6, 0, 0) * cap
    notes = [f"desk grommet for a Ø{D:g} mm hole: sleeve Ø{2 * ro:g} mm and {dp:g} mm deep, flange Ø{2 * (ro + fl):g} mm, "
             f"Ø{2 * ri:g} mm clear through" + (f"; the cap has a {cs:g} mm cable notch" if cs > 0 else "; a plain cap"),
             "both print flat as they lie (the sleeve flange down, the cap top down), no supports"]
    return _out(shape, notes, [], {"drill": D, "clear": round(2 * ri, 2)})


# ---------- Workshop ----------

def bit_holder(rows=2, cols=6, hole="hex", hole_d=6.35, depth=12.0):
    """A block of holes for driver bits (1/4 in hex), drill bits, pens or anything that stands up:
    rows and columns of round or hex holes."""
    r, c, d, dp = int(rows), int(cols), float(hole_d), float(depth)
    _rng("rows", r, 1, 12, ""); _rng("columns", c, 1, 24, ""); _rng("hole size", d, 1.5, 40); _rng("depth", dp, 4, 80)
    if hole not in ("hex", "round"):
        raise ValueError("hole: hex or round")
    fit = d + 0.35
    pitch = fit + max(3.0, 0.35 * d)
    body = Box(c * pitch + 2, r * pitch + 2, dp + 2.0, align=MIN_)
    try:
        body = fillet(body.edges().filter_by(Axis.Z), 2.0)
        body = chamfer(body.edges().group_by(Axis.Z)[-1], 0.8)
    except Exception:
        pass
    cut = extrude(RegularPolygon(fit / 2, 6, major_radius=False), amount=dp + 1) if hole == "hex" else Cylinder(fit / 2, dp + 1, align=MIN_)
    for i in range(c):
        for j in range(r):
            body -= Pos((i - (c - 1) / 2) * pitch, (j - (r - 1) / 2) * pitch, 2.0) * cut
    notes = [f"holder with {r * c} {hole} holes ({r} x {c}) for {d:g} mm{' across flats' if hole == 'hex' else ''}: holes "
             f"{fit:g} mm, {dp:g} deep, {pitch:.1f} apart; {c * pitch + 2:.0f} x {r * pitch + 2:.0f} x {dp + 2:g} mm", "print it as it stands"]
    return _out(body, notes, [], {"pitch": round(pitch, 2)})


def tool_rack(slots=5, shaft_d=8.0, pitch=30.0, reach=30.0, thickness=5.0, screw_d=4.5):
    """A wall rack for tools with a shaft and a wider handle or head (screwdrivers, chisels, files,
    pliers by one handle): a shelf with open slots, on a back plate that screws to the wall. It
    prints lying on its back."""
    n, d, p, rc, t = int(slots), float(shaft_d), float(pitch), float(reach), float(thickness)
    _rng("slots", n, 1, 20, ""); _rng("shaft diameter", d, 2, 50); _rng("reach", rc, 15, 100); _rng("thickness", t, 3, 10)
    sw = d + 1.0
    if p < sw + 6:
        raise ValueError(f"slots {p:g} mm apart leave no room between Ø{d:g} mm shafts: at least {sw + 6:g} mm")
    if rc < sw + 8:
        raise ValueError(f"the shelf must reach at least {sw + 8:g} mm for a Ø{d:g} mm shaft")
    head = 2 * screw_d
    Lb = n * p + 2 * t
    bh = max(40.0, head + 2 * t + 16)
    body = Pos(0, bh / 2, 0) * Box(Lb, bh, t, align=MIN_)                       # the back plate, flat on the bed
    body += Pos(0, bh - t / 2, 0) * Box(Lb, t, rc + t, align=MIN_)              # the shelf, standing up
    for s in (-1, 1):                                                            # a gusset at each end
        x0, x1 = sorted((s * (Lb / 2), s * (Lb / 2 - t)))
        g = extrude(Plane.YZ * Polygon((bh - t + 0.1, t - 0.1), (bh - t + 0.1, rc + t), (bh - t - min(rc, bh - t - 2), t - 0.1), align=None),
                    amount=x1 - x0, dir=(1, 0, 0))
        body += Pos(x0, 0, 0) * g
    for i in range(n):
        x = (i - (n - 1) / 2) * p
        zc = t + rc - sw / 2 - 5
        body -= Pos(x, bh - t / 2, zc) * (Rot(90, 0, 0) * Cylinder(sw / 2, t * 3))
        body -= Pos(x, bh - t / 2, zc + rc / 2) * Box(sw, t * 3, rc, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    hx = [0.0] if n == 1 else [-(n - 1) / 2 * p + p / 2 + k * p for k in range(n - 1)]
    hx = hx if len(hx) <= 3 else [hx[0], hx[len(hx) // 2], hx[-1]]
    for x in hx:
        body -= Pos(x, (bh - t) / 2, t) * _csk(screw_d, head, 40)
    notes = [f"tool rack with {n} slots for Ø{d:g} mm shafts ({sw:g} mm slots, {p:g} mm apart), shelf {rc:g} mm out from the wall, "
             f"{Lb:g} mm long; {len(hx)} countersunk Ø{screw_d:g} mm holes", "print it lying on its back as it lies, no supports"]
    return _out(body, notes, [], {"length": round(Lb, 1), "slot": sw})


def sanding_block(length=120.0, width=65.0, height=30.0):
    """A sanding block: finger grooves down both sides and a slit at each end to tuck the paper
    into. A quarter sheet wraps a 65 mm wide block."""
    Ln, W, H = float(length), float(width), float(height)
    _rng("length", Ln, 50, 300); _rng("width", W, 25, 150); _rng("height", H, 18, 60)
    body = Box(Ln, W, H, align=MIN_)
    try:
        body = fillet(body.edges().filter_by(Axis.X).group_by(Axis.Z)[-1], min(8.0, H * 0.3))
        body = fillet(body.edges().filter_by(Axis.Z), 3.0)
    except Exception:
        pass
    gr = min(9.0, H * 0.3)
    for s in (-1, 1):
        body -= Pos(0, s * (W / 2 + gr * 0.45), H * 0.58) * (Rot(0, 90, 0) * Cylinder(gr, Ln * 0.7))
    for s in (-1, 1):   # a slit down from the top near each end, leaning in, to tuck the paper's end into
        body -= Pos(s * (Ln / 2 - 10), 0, H - 6) * (Rot(0, -s * 20, 0) * Box(1.4, W + 2, 16))
    notes = [f"sanding block {Ln:g} x {W:g} x {H:g} mm: wrap the paper round the bottom and up both ends, and push each end into "
             f"its slit with a card; paper {W:g} mm wide and about {Ln + 2 * 28:.0f} mm long", "print it as it stands, flat face down"]
    return _out(body, notes, [], {"paper": [W, round(Ln + 56, 0)]})


def drill_guide(sizes="3, 4, 5, 6, 8", height=25.0, v_groove=True, corner_radius=0.0, engrave=True):
    """A drill guide block: a row of square, upright holes to start a drill straight, with a V groove
    underneath to sit it on a round bar or an edge, and marks on the hole line."""
    from . import sizes as sz
    got = sz.parse_list(sizes, "sizes")
    ds = [mm for mm, _ in got]
    marks = [sz.short(typed, mm) for mm, typed in got]
    if not 1 <= len(ds) <= 12 or any(not 1 <= d <= 16 for d in ds):
        raise ValueError("sizes: 1 to 12 drills, each 1 to 16 mm")
    H = float(height)
    _rng("height", H, 12, 60)
    gap = 7.0
    Ln = sum(d + 0.2 for d in ds) + gap * (len(ds) + 1)
    th = 3.2                                        # the engraved sizes run across the block, in front of each hole
    tw = max(len(m) for m in marks) * 0.62 * th
    W = max(26.0, max(ds) + 16, (max(ds) + 2 * (tw + 4.5)) if engrave else 0)
    body = Box(Ln, W, H, align=MIN_)
    if float(corner_radius) > 0:
        _rng("corner radius", float(corner_radius), 0, 6)
        body = fillet(body.edges().filter_by(Axis.Z), float(corner_radius))
    try:
        body = chamfer(body.edges().group_by(Axis.Z)[-1], 1.0)
    except Exception:
        pass
    x = -Ln / 2 + gap
    centres = []
    for d in ds:
        x += (d + 0.2) / 2
        centres.append(round(x, 2))
        body -= Pos(x, 0, -1) * Cylinder((d + 0.2) / 2, H + 2, align=MIN_)
        body -= Pos(x, W / 2, H / 2) * Box(0.8, 1.6, H + 2)          # a mark on each side, on the hole's centre
        body -= Pos(x, -W / 2, H / 2) * Box(0.8, 1.6, H + 2)
        if engrave:
            from .more import _engrave
            body = _engrave(body, marks[len(centres) - 1], th, x, -(d / 2 + (W - d) / 4 + 0.3), H, turn=90)
        x += (d + 0.2) / 2 + gap
    if v_groove:
        vd = min(6.0, W / 4)
        body -= Pos(-Ln / 2 - 1, 0, 0) * extrude(Plane.YZ * Polygon((-vd, -0.01), (vd, -0.01), (0, vd), align=None), amount=Ln + 2, dir=(1, 0, 0))
    for s in (-1, 1):
        body -= Pos(s * Ln / 2, 0, H / 2) * Box(1.6, 0.8, H + 2)     # and on each end, on the line of holes
    notes = [f"drill guide for {', '.join(m.replace('Ø', '') + ('' if m.endswith('"') else ' mm') for m in marks)} drills: holes {0.2:g} mm over size, {H:g} mm tall, "
             f"{Ln:.0f} x {W:g} mm" + (", a 90° V groove underneath for round stock" if v_groove else "")
             + (", each size cut into the top by its hole" if engrave else ""),
             "print it as it stands with 4 or more walls; plastic wears, so it's good for dozens of holes, not hundreds"]
    return _out(body, notes, ["a hole under 2 mm may print closed: drill it out with its own bit"] if min(ds) < 2 else [],
                {"centres": centres})


# ---------- Repairs around the house ----------

def foot(diameter=30.0, height=15.0, taper=0.8, screw_d=4.5):
    """A foot for furniture, a box or a machine: a tapered round pad that screws on through the
    middle, the screw's head sunk well inside. Print it in TPU for a foot that grips."""
    D, H, k = float(diameter), float(height), float(taper)
    _rng("diameter", D, 10, 120); _rng("height", H, 4, 80); _rng("taper", k, 0.4, 1.0, "")
    body = Cone(D / 2, D * k / 2, H, align=MIN_) if k < 0.999 else Cylinder(D / 2, H, align=MIN_)
    try:
        body = fillet(body.edges().group_by(Axis.Z)[-1], min(2.0, H * 0.2, D * k / 6))
    except Exception:
        pass
    notes = [f"foot Ø{D:g} mm at the top, Ø{D * k:g} mm on the floor, {H:g} mm tall"]
    if screw_d > 0:
        head = 2 * screw_d
        if head + 4 > D * k:
            raise ValueError(f"a {screw_d:g} mm screw's head needs a foot at least {(head + 4) / k:.0f} mm across")
        grip = max(2.5, min(5.0, H * 0.4))          # plastic left under the head
        body -= Pos(0, 0, -1) * Cylinder(screw_d / 2, H + 2, align=MIN_)
        body -= Pos(0, 0, grip) * Cylinder(head / 2 + 0.3, H, align=MIN_)
        notes[0] += f", a Ø{screw_d:g} mm screw through the middle with its head {H - grip:g} mm up inside"
    else:
        notes[0] += ", no hole (stick it on)"
    notes.append("print it wide face down as it stands; TPU grips and doesn't mark a floor")
    return _out(body, notes)


def end_cap(shape="round", outer=25.0, outer2=25.0, tube_wall=1.5, insert=15.0, cap=3.0):
    """An end cap that plugs a tube: round, square or rectangular. A head the tube's outside size,
    and a hollow plug with crush ribs that grips the inside. Prints head down."""
    if shape not in ("round", "square", "rectangle"):
        raise ValueError("shape: round, square or rectangle")
    A, B = float(outer), float(outer2) if shape == "rectangle" else float(outer)
    tw, ins, ct = float(tube_wall), float(insert), float(cap)
    _rng("outside size", A, 8, 150); _rng("outside size (other way)", B, 8, 150); _rng("tube wall", tw, 0.5, 10)
    _rng("insert", ins, 5, 60); _rng("cap", ct, 1.5, 10)
    ia, ib = A - 2 * tw - 0.4, B - 2 * tw - 0.4
    if min(ia, ib) < 5:
        raise ValueError("the tube's inside is under 5 mm: too small for a plug")
    pw = min(1.6, min(ia, ib) / 4)
    rib = 0.35

    def sec(a, b, r):
        return Circle(a / 2) if shape == "round" else RectangleRounded(a, b, max(0.3, min(r, a / 2 - 0.1, b / 2 - 0.1)))
    head = extrude(sec(A, B, 2.0), amount=ct)
    try:
        head = chamfer(head.edges().group_by(Axis.Z)[0], min(0.8, ct * 0.3))
    except Exception:
        pass
    plug = Pos(0, 0, ct - 0.01) * extrude(sec(ia, ib, 1.0), amount=ins + 0.01)
    try:
        plug = chamfer(plug.edges().group_by(Axis.Z)[-1], min(1.2, pw * 0.7))
    except Exception:
        pass
    body = head + plug
    body -= Pos(0, 0, ct) * extrude(sec(ia - 2 * pw, ib - 2 * pw, 0.5), amount=ins + 1)
    # Crush ribs up the plug: small triangles that bite the tube's inside.
    def rib_at(x, y, ang):
        tri = extrude(Polygon((-0.6, -0.05), (0.6, -0.05), (0, rib), align=None), amount=ins - 2.0)
        return Pos(x, y, ct) * (Rot(0, 0, ang) * tri)
    if shape == "round":
        for k in range(6):
            a = math.radians(60 * k)
            body += rib_at((ia / 2) * math.sin(a) * 1.0, (ia / 2) * math.cos(a), -60 * k)
    else:
        for fx in (-0.3, 0.3):
            body += rib_at(fx * ia, ib / 2, 0)
            body += rib_at(fx * ia, -ib / 2, 180)
        for fy in (-0.3, 0.3):
            body += rib_at(ia / 2, fy * ib, -90)
            body += rib_at(-ia / 2, fy * ib, 90)
    size = f"Ø{A:g}" if shape == "round" else f"{A:g} x {B:g}"
    notes = [f"end cap for a {shape} tube {size} mm outside with a {tw:g} mm wall: plug {ia:g}"
             + ("" if shape == "round" else f" x {ib:g}") + f" mm, {ins:g} mm long with {rib:g} mm crush ribs, head {ct:g} mm",
             "print it head down as it stands; tap it in. If it's loose, measure the tube's inside and lower the tube wall here"]
    return _out(body, notes, [], {"plug": [round(ia, 2), round(ib, 2)]})


def shim(length=50.0, width=30.0, thickness=2.0, thickness2=0.0, slot=0.0):
    """A shim or spacer plate, flat or a wedge (thicker at one end), with an open slot if you want
    it to slide round a bolt."""
    Ln, W, t = float(length), float(width), float(thickness)
    t2 = float(thickness2) or t
    _rng("length", Ln, 8, 300); _rng("width", W, 8, 300); _rng("thickness", t, 0.4, 40); _rng("thickness at the other end", t2, 0.4, 40)
    body = Pos(0, W / 2, 0) * extrude(Plane.XZ * Polygon((-Ln / 2, 0), (Ln / 2, 0), (Ln / 2, t2), (-Ln / 2, t), align=None), amount=W, dir=(0, -1, 0))
    if slot > 0:
        sw = float(slot)
        if sw > W - 6:
            raise ValueError("the slot is nearly as wide as the shim")
        body -= Pos(Ln / 4, 0, -1) * Box(Ln / 2 + 0.2, sw, max(t, t2) + 2, align=MIN_)
        body -= Pos(0, 0, -1) * Cylinder(sw / 2, max(t, t2) + 2, align=MIN_)
    wedge = abs(t2 - t) > 1e-6
    notes = [f"shim {Ln:g} x {W:g} mm, " + (f"a wedge from {t:g} to {t2:g} mm ({math.degrees(math.atan2(abs(t2 - t), Ln)):.1f}°)" if wedge else f"{t:g} mm thick")
             + (f", a {slot:g} mm slot open at one end" if slot > 0 else ""), "print it flat as it lies; thickness comes out in whole layers, "
             "so pick a multiple of your layer height"]
    return _out(body, notes, ["under 0.6 mm is two or three layers: fragile"] if min(t, t2) < 0.6 else [])


def hole_plug(hole_d=20.0, panel=2.0, flange=3.0):
    """A snap-in plug for an unused round hole in a panel: a low flange and a ring of sprung fingers
    with barbs that click behind the panel."""
    D, p, fl = float(hole_d), float(panel), float(flange)
    _rng("hole", D, 8, 80); _rng("panel", p, 0.5, 12); _rng("flange", fl, 1.5, 12)
    ro = D / 2 - 0.15
    wall = 1.3
    barb = min(0.8, 0.05 * D + 0.3)
    ft = 1.6
    hgt = p + 0.3 + 2 * barb + 1.2
    body = Cylinder(ro + fl, ft, align=MIN_)
    try:
        body = chamfer(body.edges().group_by(Axis.Z)[0], min(1.0, ft * 0.6))
    except Exception:
        pass
    ring = Pos(0, 0, ft - 0.01) * Cylinder(ro, hgt, align=MIN_)
    z0 = ft + p + 0.3                               # the barb: out at 45 degrees, back at 45
    ring += Pos(0, 0, z0) * Cone(ro, ro + barb, barb, align=MIN_)
    ring += Pos(0, 0, z0 + barb) * Cone(ro + barb, ro - 0.2, barb + 0.2, align=MIN_)
    ring -= Pos(0, 0, ft) * Cylinder(ro - wall, hgt + 5, align=MIN_)
    nf = 4 if D < 25 else 6
    for k in range(nf // 2):          # each cut crosses the ring twice
        ring -= Pos(0, 0, ft + 0.6) * (Rot(0, 0, 360.0 * k / nf) * Box(max(1.5, 0.12 * D), 3 * D, hgt + 5, align=MIN_))
    body += ring
    notes = [f"snap-in plug for a Ø{D:g} mm hole in a {p:g} mm panel: flange Ø{2 * (ro + fl):g} mm, {nf} sprung fingers with a "
             f"{barb:.2g} mm barb", "print it flange down as it stands; PETG fingers spring better than PLA"]
    return _out(body, notes, ["a thick panel makes long fingers that bend easily: it may pull out"] if p > 6 else [], {"barb": round(barb, 2)})


def drawer_organizer(length=150.0, width=80.0, height=40.0, wall=1.2, div_x=2, div_y=0, corner=3.0):
    """A drawer organiser tray to any size: thin walls, a floor, and dividers each way."""
    Ln, W, H, t, nx, ny = float(length), float(width), float(height), float(wall), int(div_x), int(div_y)
    _rng("length", Ln, 20, 400); _rng("width", W, 20, 400); _rng("height", H, 8, 150); _rng("wall", t, 0.8, 4)
    _rng("dividers", nx, 0, 15, ""); _rng("dividers", ny, 0, 15, "")
    r = max(0.5, min(float(corner), Ln / 4, W / 4))
    body = extrude(RectangleRounded(Ln, W, r), amount=H)
    try:
        body = chamfer(body.edges().group_by(Axis.Z)[0], min(0.8, t * 0.6))
    except Exception:
        pass
    body -= Pos(0, 0, 1.0) * extrude(RectangleRounded(Ln - 2 * t, W - 2 * t, max(0.3, r - t)), amount=H)
    il, iw = Ln - 2 * t, W - 2 * t
    for k in range(1, nx + 1):
        body += Pos(-il / 2 + k * il / (nx + 1), 0, 0.99) * Box(t, iw + 0.02, H - 1.0, align=MIN_)
    for k in range(1, ny + 1):
        body += Pos(0, -iw / 2 + k * iw / (ny + 1), 0.99) * Box(il + 0.02, t, H - 1.0, align=MIN_)
    notes = [f"organiser tray {Ln:g} x {W:g} x {H:g} mm, walls {t:g} mm, {(nx + 1) * (ny + 1)} pockets about "
             f"{(il - nx * t) / (nx + 1):.1f} x {(iw - ny * t) / (ny + 1):.1f} mm", "print it as it stands"]
    return _out(body, notes, [], {"pocket": [round((il - nx * t) / (nx + 1), 1), round((iw - ny * t) / (ny + 1), 1)]})


CELL_SIZES = {"AAA": (10.5, 44.5), "AA": (14.5, 50.5), "C": (26.2, 50.0), "D": (34.2, 61.5), "CR123A": (17.0, 34.5),
              "18650": (18.6, 65.2), "21700": (21.4, 70.2), "9V": (26.5, 48.5)}


def battery_caddy(cell="AA", rows=2, cols=4, depth_fraction=0.5):
    """A storage block for spare cells, standing up in pockets: AAA, AA, C, D, CR123A, 18650, 21700
    or 9V. It stores them; it has no contacts (the battery compartment is the powered one)."""
    if cell not in CELL_SIZES:
        raise ValueError(f"cell: one of {', '.join(CELL_SIZES)}")
    r, c, f = int(rows), int(cols), float(depth_fraction)
    _rng("rows", r, 1, 10, ""); _rng("columns", c, 1, 12, ""); _rng("pocket depth (part of the cell's length)", f, 0.25, 0.9, "")
    d, ln = CELL_SIZES[cell]
    dp = ln * f
    if cell == "9V":
        pw, pd = 26.5 + 0.6, 17.5 + 0.6
        cut = Box(pw, pd, dp + 1, align=MIN_)
    else:
        pw = pd = d + 0.6
        cut = Cylinder(pw / 2, dp + 1, align=MIN_)
    px, py = pw + 2.0, pd + 2.0
    body = Box(c * px + 2, r * py + 2, dp + 1.6, align=MIN_)
    try:
        body = fillet(body.edges().filter_by(Axis.Z), 2.5)
    except Exception:
        pass
    for i in range(c):
        for j in range(r):
            body -= Pos((i - (c - 1) / 2) * px, (j - (r - 1) / 2) * py, 1.6) * cut
    notes = [f"storage block for {r * c} {cell} cells ({r} x {c}): pockets {pw:g} mm, {dp:.0f} mm deep; "
             f"{c * px + 2:.0f} x {r * py + 2:.0f} x {dp + 1.6:.0f} mm", "print it as it stands"]
    return _out(body, notes, ["store lithium cells with their ends covered, and never loose with metal"] if cell in ("18650", "21700", "CR123A") else [])


# Cells for a holder with contacts: (diameter, length, contact plate width). A protected 18650 has a
# protection circuit on one end from the factory and runs 68 to 70 mm, against 65 mm for a bare one.
HOLDER_CELLS = {"AAA": (10.5, 44.5, 7.0), "AA": (14.5, 50.5, 9.5), "18650": (18.6, 65.2, 12.0),
                "18650 protected": (18.9, 69.5, 12.0), "21700": (21.4, 70.2, 14.0)}
NINE_V = (26.5, 17.5, 48.5)   # a PP3: width, thickness, length to the top of its terminals


BATTERY_MOUNTS = ("external ears", "internal holes", "none")
BATTERY_BAYS = ("each cell in its own bay", "one open compartment")
# As the holder first shows in the 3D view: its length left to right, the front toward you.
EAR_SIDES = ("front and back", "both ends", "front only", "back only", "left end only", "right end only")
_EARS = {"front and back": ("y", (-1, 1)), "both ends": ("x", (-1, 1)), "front only": ("y", (-1,)), "back only": ("y", (1,)),
         "left end only": ("x", (-1,)), "right end only": ("x", (1,))}


def battery_holder(cell="18650", count=1, cell_length=0.0, contact_room=6.5, contact_w=0.0, contact_t=0.6, mount="external ears",
                   ear_side="front and back", ears=None, bays="each cell in its own bay"):
    """A battery compartment with places for contacts: AAA, AA, 18650 (bare or with a protection
    circuit), 21700, or a 9V. Each cell lies in a trough between two end walls, and each end wall has
    a slot a flat contact plate drops into (a spring at one end, a button at the other). The cell
    length is yours to set, which is what makes a protected 18650 fit."""
    n = int(count)
    _rng("cells", n, 1, 8, "")
    if ears is not None:                 # a part saved before the fixing had choices
        mount = "external ears" if ears else "none"
    if mount not in BATTERY_MOUNTS:
        raise ValueError(f"fixing: one of {', '.join(BATTERY_MOUNTS)}")
    if ear_side not in EAR_SIDES:
        raise ValueError(f"ears on: one of {', '.join(EAR_SIDES)}")
    if bays not in BATTERY_BAYS:
        raise ValueError(f"cells: one of {', '.join(BATTERY_BAYS)}")
    side = 1.6
    between = side if bays == BATTERY_BAYS[0] or n == 1 else 0.0      # the wall between two cells, or none
    fl = 2.4 if mount == "internal holes" else 1.6     # a thicker floor to sink the screws' heads into
    notes, checks = [], []
    seats = []                           # (y of each cell's centre line, the floor's top there)
    if cell == "9V":
        w9, t9, l9 = NINE_V
        ln = float(cell_length) or l9
        _rng("battery length", ln, 40, 60)
        room = 9.0                                    # the snap connector on the terminals
        iw, il = n * (w9 + 0.6) + (n - 1) * between, ln + room
        wall_h = fl + 0.7 * t9
        body = Box(il + 2 * side, iw + 2 * side, wall_h, align=MIN_)
        for i in range(n):
            y = -iw / 2 + (w9 + 0.6) / 2 + i * (w9 + 0.6 + between)
            seats.append(y)
            body -= Pos(0, y, fl) * Box(il, w9 + 0.6 + (0.02 if not between else 0), wall_h, align=MIN_)
            body -= Pos(il / 2 + side / 2, y, fl + 3) * Box(side * 3, 6.0, wall_h, align=MIN_)        # the leads' way out
            body -= Pos(-il / 2 - side / 2, y, fl + wall_h * 0.5) * Box(side * 3, 14.0, wall_h, align=MIN_)   # a thumb notch to lift it
        notes.append(f"compartment for {n} x 9V (PP3, {w9:g} x {t9:g} x {ln:g} mm): {il:g} mm long inside with {room:g} mm for the "
                     f"snap connector and a slot for its leads; no contacts to fit, the snap connector is the contact")
        cw = None
        L_out, W_out = il + 2 * side, iw + 2 * side
    else:
        if cell not in HOLDER_CELLS:
            raise ValueError(f"cell: one of {', '.join(list(HOLDER_CELLS) + ['9V'])}")
        dia, std_len, cw_std = HOLDER_CELLS[cell]
        ln = float(cell_length) or std_len
        _rng("cell length", ln, std_len - 8, std_len + 12)
        room, ct = float(contact_room), float(contact_t)
        _rng("room for the contacts", room, 2, 14); _rng("contact thickness", ct, 0.2, 1.5)
        cw = float(contact_w) or cw_std
        pitch = dia + 0.5 + between
        if cw > pitch - 1.6:
            raise ValueError(f"a {cw:g} mm contact is too wide for {cell} cells {pitch:g} mm apart: {pitch - 1.6:g} mm at most")
        lip, back = 1.0, 1.4
        end_t = lip + ct + 0.3 + back                 # the end wall: a lip, the contact's slot, a back
        il = ln + room
        iw = n * (dia + 0.5) + (n - 1) * between
        L_out, W_out = il + 2 * end_t, iw + 2 * side
        zc = fl + dia / 2 + 0.2                       # the cells' axis
        low, high = fl + 0.55 * dia, fl + 0.9 * dia   # the side walls, and the end walls
        body = Box(L_out, W_out, low, align=MIN_)
        for sx in (-1, 1):
            body += Pos(sx * (L_out / 2 - end_t / 2), 0, 0) * Box(end_t, W_out, high, align=MIN_)
        for i in range(n):
            y = -iw / 2 + (dia + 0.5) / 2 + i * pitch
            seats.append(y)
            body -= Pos(0, y, zc) * (Rot(0, 90, 0) * Cylinder(dia / 2 + 0.25, il))        # the trough the cell lies in
            body -= Pos(0, y, zc + dia / 2) * Box(il, dia + 0.5 + (0.02 if not between else 0), dia, align=(Align.CENTER, Align.CENTER, Align.CENTER))
            body -= Pos(0, y, -1) * Box(min(18.0, il * 0.3), dia * 0.55, fl + 2, align=MIN_)   # a hole to push the cell out from below
            for sx in (-1, 1):
                x_in = sx * il / 2                     # the end wall's inner face
                # The plate's slot, open at the top, and a narrower window through the lip for the spring or button.
                body -= Pos(x_in + sx * (lip + (ct + 0.3) / 2), y, fl + 0.6) * Box(ct + 0.3, cw + 0.4, high, align=MIN_)
                body -= Pos(x_in + sx * lip / 2, y, zc - (cw - 3.0) / 2) * Box(lip + 0.02, cw - 3.0, high, align=MIN_)
                # The solder tab's way out through the back, at the top.
                body -= Pos(x_in + sx * (end_t - back / 2), y, zc + 1.0) * Box(back + 0.02, min(4.0, cw - 3.0), high, align=MIN_)
            # A plus sign sunk into the top of the positive end's wall; alternate ends, as cells in series go.
            px = (1 if i % 2 == 0 else -1) * (L_out / 2 - end_t / 2)
            for a, b in ((2.6, 0.7), (0.7, 2.6)):
                body -= Pos(px, y + cw / 2 + 1.3 if y + cw / 2 + 2.6 < W_out / 2 else y - cw / 2 - 1.3, high - 0.4) * Box(min(a, end_t - 0.6), b, 1, align=MIN_)
        spring, button = room - 1.5, 1.5
        notes.append(f"compartment for {n} x {cell} (Ø{dia:g} x {ln:g} mm cells): {il:g} mm between the end walls, which leaves "
                     f"{room:g} mm for the contacts (about {spring:g} mm for a spring squeezed down, {button:g} mm for a button)")
        notes.append(f"each end wall has a slot for a flat contact plate up to {cw:g} mm wide and {ct:g} mm thick, dropped in from the "
                     f"top, with a notch behind it for its solder tab; buy spring and button contact plates sold for {cell.split()[0]} cells")
        notes.append("a plus sign marks one end of each cell, alternating, which is how cells in series lie; for parallel, turn "
                     "every cell the same way and ignore the marks on the even ones" if n > 1 else "a plus sign marks the positive end")
        if cell.startswith("18650"):
            notes.append("18650 lengths differ: a bare cell is about 65 mm, one with a protection circuit 68 to 70 mm, and a button "
                         f"top adds about 1 mm. This one is set for {ln:g} mm: measure yours and set the cell length to match")
        if ln != std_len:
            notes[0] += f" (the standard {cell} is {std_len:g} mm)"
        checks.append("contact plates differ between makers: check yours against the slot before printing a set, and set the "
                      "contact width, thickness and room to match")
    if n > 1:
        notes.insert(1, f"each cell lies in its own bay, with a {side:g} mm wall between neighbours" if between else
                     ("the batteries share one open compartment, side by side with no wall between them" if cell == "9V" else
                      "the cells share one open compartment, side by side with no wall between them: a low ridge in the floor keeps each in its place, "
                      "and the pack is narrower"))
    eh = 3.4
    if mount == "external ears":
        axis, signs = _EARS[ear_side]
        long_side = axis == "y"
        for sg in signs:
            if long_side:
                ear = Pos(0, sg * (W_out / 2 + 4.5 - 0.1), 0) * Box(10.0, 9.2, fl + 0.8, align=MIN_)
                ear -= Pos(0, sg * (W_out / 2 + 4.8), -1) * Cylinder(eh / 2, 10, align=MIN_)
            else:
                ear = Pos(sg * (L_out / 2 + 4.5 - 0.1), 0, 0) * Box(9.2, 10.0, fl + 0.8, align=MIN_)
                ear -= Pos(sg * (L_out / 2 + 4.8), 0, -1) * Cylinder(eh / 2, 10, align=MIN_)
            body += ear
        apart = (W_out if long_side else L_out) + 9.6
        where = {"front and back": "at the front and the back (the long sides)", "both ends": "at each end"}.get(ear_side, "at the " + ear_side.replace(" only", "") + " only")
        notes.append(f"a screw ear {where} (Ø{eh:g} mm, M3)" + (f", {apart:.1f} mm apart" if len(signs) == 2 else ""))
        if len(signs) == 1:
            checks.append("one ear alone lets the holder rock: add a dab of tape or glue under the far side, or use two ears")
    elif mount == "internal holes":
        # Countersunk holes in the floor under the cells: at a quarter and three quarters of the length, on the
        # outer cells' centre lines (one cell: both on it), clear of the push-out hole in the middle.
        pts = [(-il / 4, seats[0]), (il / 4, seats[-1])]
        for x, y in pts:
            body -= Pos(x, y, fl) * _csk(eh, 6.4, 20)
        notes.append(f"two countersunk Ø{eh:g} mm holes (M3 flat head) inside, in the floor under the cells, "
                     f"{math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]):.1f} mm apart"
                     + (" on a diagonal" if len(seats) > 1 else "") + f"; the floor is {fl:g} mm thick so their heads sit below the cells")
        checks.append("use flat-head (countersunk) screws and check they sit flush: a proud head shorts or dents a cell")
    notes.append("print it as it stands, no supports")
    return _out(body, notes, checks, {"inside_length": round(il, 2), "outside": [round(L_out, 2), round(W_out, 2)],
                                      "cell_length": ln, "contact_width": cw})


# ---------- Fans ----------

# Fan size -> (screw hole spacing, screw hole for a self-tapping fan screw or M-screw clearance).
FANS = {30: (24.0, 3.4), 40: (32.0, 3.4), 50: (40.0, 4.5), 60: (50.0, 4.5), 70: (61.5, 4.5), 80: (71.5, 4.5), 92: (82.5, 4.5),
        120: (105.0, 4.5), 140: (124.5, 4.5)}


def _fan(size) -> tuple[float, float, float]:
    s = int(float(size))
    if s not in FANS:
        raise ValueError(f"fan size: one of {', '.join(str(k) for k in FANS)} mm")
    return float(s), FANS[s][0], FANS[s][1]


def fan_guard(fan=80, thickness=2.4, bar=1.6, gap=7.0):
    """A finger guard for a fan: a square frame with the fan's screw holes, rings and four spokes."""
    S, sp, hd = _fan(fan)
    t, b, g = float(thickness), float(bar), float(gap)
    _rng("thickness", t, 1.2, 6); _rng("bar", b, 1.0, 4); _rng("gap", g, 3, 15)
    body = extrude(RectangleRounded(S, S, min(5.0, S * 0.08)), amount=t)
    ro = S / 2 - 1.5
    body -= Pos(0, 0, -1) * Cylinder(ro, t + 2, align=MIN_)
    rr = ro - g
    rings = 0
    while rr > g * 0.7 + b:
        body += Cylinder(rr, t, align=MIN_) - Pos(0, 0, -1) * Cylinder(rr - b, t + 2, align=MIN_)
        rr -= g + b
        rings += 1
    hub = max(rr, 3.0)
    body += Cylinder(hub, t, align=MIN_)
    for a in (45, 135):
        body += Rot(0, 0, a) * Box(2 * ro + 1, b * 1.4, t, align=MIN_)
    for sx in (-1, 1):
        for sy in (-1, 1):
            body -= Pos(sx * sp / 2, sy * sp / 2, -1) * Cylinder(hd / 2, t + 2, align=MIN_)
    notes = [f"fan guard for a {S:g} mm fan: holes {sp:g} mm apart (Ø{hd:g}), {rings} rings and four spokes, bars {b:g} mm with "
             f"{g:g} mm gaps, {t:g} mm thick", "print it flat as it lies"]
    return _out(body, notes, ["gaps over 8 mm let a small finger through"] if g > 8 else [], {"hole_spacing": sp})


def fan_adapter(from_size=120, to_size=80, height=0.0, wall=2.0):
    """An adapter between two fan sizes: a square at each end with that fan's screw holes (for
    self-tapping fan screws) and a smooth round duct between. Prints big end down."""
    S1, sp1, _ = _fan(from_size)
    S2, sp2, _ = _fan(to_size)
    if S2 >= S1:
        raise ValueError("the first fan is the bigger one")
    w = float(wall)
    _rng("wall", w, 1.2, 5)
    need = (S1 - S2) / 2 + 6
    H = float(height) or max(20.0, round(need + 4))
    if H < need:
        raise ValueError(f"at least {need:.0f} mm tall keeps the walls at 45° or steeper, so it prints without supports")
    _rng("height", H, 12, 250)
    fl = 3.0
    outer = loft([RectangleRounded(S1, S1, 5).face(), Pos(0, 0, fl) * RectangleRounded(S1, S1, 5).face()])
    outer += loft([Pos(0, 0, fl) * RectangleRounded(S1, S1, 5).face(), Pos(0, 0, H - fl) * RectangleRounded(S2, S2, 4).face()])
    outer += loft([Pos(0, 0, H - fl) * RectangleRounded(S2, S2, 4).face(), Pos(0, 0, H) * RectangleRounded(S2, S2, 4).face()])
    d1, d2 = S1 - 2 * w - 1, S2 - 2 * w - 1
    inner = loft([Pos(0, 0, -0.01) * Circle(d1 / 2).face(), Pos(0, 0, fl) * Circle(d1 / 2).face()])
    inner += loft([Pos(0, 0, fl) * Circle(d1 / 2).face(), Pos(0, 0, H - fl) * Circle(d2 / 2).face()])
    inner += loft([Pos(0, 0, H - fl) * Circle(d2 / 2).face(), Pos(0, 0, H + 0.01) * Circle(d2 / 2).face()])
    body = outer - inner
    pilot = 3.6                                     # a self-tapping fan screw cuts its own thread in this
    for sx in (-1, 1):
        for sy in (-1, 1):
            body -= Pos(sx * sp1 / 2, sy * sp1 / 2, -0.01) * Cylinder(pilot / 2, 9, align=MIN_)
            body -= Pos(sx * sp2 / 2, sy * sp2 / 2, H - 9) * Cylinder(pilot / 2, 9.01, align=MIN_)
    notes = [f"fan adapter from {S1:g} mm to {S2:g} mm, {H:g} mm tall: a round duct Ø{d1:g} to Ø{d2:g} mm, Ø{pilot:g} mm pilot holes "
             f"9 mm deep at each fan's spacing ({sp1:g} and {sp2:g} mm) for self-tapping fan screws",
             "print it big end down as it stands, no supports"]
    return _out(body, notes, ["necking a fan down costs airflow: keep the duct as tall as you have room for"], {"height": H})


# ---------- Labels ----------

LABEL_MOUNTS = ("none", "screw holes", "cable tie slots", "key ring hole", "magnets", "stake")
LABEL_STYLES = ("raised", "engraved", "flush")


def label_plate(text="PUMP 1", text_size=8.0, style="raised", width=0.0, height=0.0, thickness=2.0, depth=0.6, bold=True,
                border=True, corners="rounded", mount="none", icon="", two_color=False, font="", google_font="", fit_text=True,
                logo="", logo_kind="svg", logo_only=False):
    """A label, tag or name plate: one or more lines of text (put | between lines), raised, engraved,
    or flush in a second colour, in any Google font, with a border, an icon or your own logo, and a
    way to fix it: screw holes, cable-tie slots, a key-ring hole, magnets in the back, or a stake to
    push into soil. Set a size and the text is sized to fill it."""
    from build123d import FontStyle, Text, scale
    from . import fonts, icons
    lines = [ln.strip() for ln in str(text).replace("\n", "|").split("|")]
    lines = [ln for ln in lines if ln]
    logo = str(logo or "").strip()
    if logo_only:
        if not logo:
            raise ValueError("logo only: choose a logo file first")
        lines = []
    if not lines and not logo:
        raise ValueError("label: type some text, or choose a logo")
    family = " ".join(str(google_font or "").split()) or (font if font and font != fonts.DEFAULT else "")
    font_file, file_is_bold = fonts.path(family, bool(bold)) if family else (None, False)
    style_ = FontStyle.BOLD if bold and not file_is_bold else FontStyle.REGULAR
    logo_faces, logo_aspect = None, 1.0
    if logo:
        from . import art
        logo_faces, (lw_, lh_) = art.shape(logo, str(logo_kind or "svg").lower(), 100.0, 3.0)
        if lh_ <= 0:
            raise ValueError("the logo has no height")
        logo_aspect = lw_ / lh_
    if len(lines) > 6 or any(len(ln) > 40 for ln in lines):
        raise ValueError("label: up to 6 lines of up to 40 characters")
    if style not in LABEL_STYLES:
        raise ValueError(f"style: one of {', '.join(LABEL_STYLES)}")
    if mount not in LABEL_MOUNTS:
        raise ValueError(f"fixing: one of {', '.join(LABEL_MOUNTS)}")
    if corners not in ("rounded", "square", "pill"):
        raise ValueError("corners: rounded, square or pill")
    if icon and icon not in icons.NAMES:
        raise ValueError(f"icon: one of {', '.join(icons.NAMES)}, or none")
    size, t, dp = float(text_size), float(thickness), float(depth)
    _rng("text size", size, 3, 80); _rng("thickness", t, 0.8, 10); _rng("text depth", dp, 0.2, 3)
    if mount == "magnets":
        t = max(t, 3.2)                      # room for a 6 x 2 mm magnet and a skin over it
    if style != "raised" and dp > t - 0.6:
        raise ValueError(f"text {dp:g} mm deep leaves too little of a {t:g} mm plate: a thicker plate or shallower text")
    W_ask, H_ask = float(width), float(height)

    def layout(sz: float):
        """The text and icon as flat faces centred on the origin, and their overall size."""
        pitch = 1.35 * sz
        parts, wmax = [], 0.0
        for i, ln in enumerate(lines):
            y = ((len(lines) - 1) / 2 - i) * pitch
            if font_file:                            # a chosen font: drawn from the font file's own outlines
                got, w_ = fonts.outline_faces(ln, sz, font_file)
                parts += [Pos(0, y) * f for f in got]
                wmax = max(wmax, w_)
                continue
            try:
                tx = Text(ln, sz, align=(Align.CENTER, Align.CENTER), font_style=style_)
            except Exception:
                raise ValueError(f"the text '{ln}' has a character this font can't draw") from None
            parts += [Pos(0, y) * f for f in fonts.sound_faces(tx)]
            wmax = max(wmax, tx.bounding_box().size.X)
        th = ((len(lines) - 1) * pitch + sz) if lines else 0.0
        tw = wmax
        if logo_faces is not None:               # your logo, as tall as the text block (or twice the text size on its own)
            lh = max(th, 1.8 * sz) if lines else 2.0 * sz
            lw = lh * logo_aspect
            k_ = lw / 100.0
            pic = [scale(f, by=k_) for f in logo_faces]
            if lines:
                gap = 0.5 * sz
                parts = [Pos((lw + gap) / 2, 0) * p for p in parts]
                parts += [Pos(-(tw + gap) / 2, 0) * f for f in pic]
                tw += lw + gap
            else:
                parts, tw = pic, lw
            th = max(th, lh)
        elif icon:
            isz = min(th, 1.8 * sz)
            gap = 0.5 * sz
            parts = [Pos((isz + gap) / 2, 0) * p for p in parts]
            parts.append(Pos(-(tw + gap) / 2, 0) * icons.icon_shape(icon, isz))
            tw += isz + gap
        return parts, tw, th

    margin = max(2.5, 0.45 * size)
    rim = 1.2 if border and style != "flush" else 0.0
    pad = margin + (rim + 0.8 if rim else 0.0)
    side = {"screw holes": 3.6 + 5.0, "cable tie slots": 3.0 + 4.0, "key ring hole": 0.0, "magnets": 0.0, "stake": 0.0, "none": 0.0}[mount]
    left = 5.0 + 5.0 if mount == "key ring hole" else side      # extra room at the left end, and at the right
    right = side
    parts, tw, th = layout(size)
    shrunk = None
    need_w, need_h = tw + 2 * pad + left + right, th + 2 * pad
    too_big = (W_ask and need_w > W_ask) or (H_ask and need_h > H_ask)
    fill = bool(fit_text) and (W_ask or H_ask)   # a size was set: make the text as big as fits it
    if too_big or fill:
        k = min((W_ask - 2 * pad - left - right) / tw if W_ask else 99, (H_ask - 2 * pad) / th if H_ask else 99)
        if k * size < 3:
            raise ValueError(f"the text doesn't fit {W_ask or need_w:g} x {H_ask or need_h:g} mm even at 3 mm tall: "
                             f"it needs {need_w:.0f} x {need_h:.0f} mm at {size:g} mm")
        new = round(min(80.0, size * k * 0.98), 1)
        if abs(new - size) > 0.05:
            shrunk = new
            parts, tw, th = layout(new)
            need_w, need_h = tw + 2 * pad + left + right, th + 2 * pad
    W, H = max(W_ask, need_w), max(H_ask, need_h)
    if mount == "magnets":
        H = max(H, 6.5 + 4)
        W = max(W, 2 * 6.5 + 12)
    _rng("label width", W, 8, 400); _rng("label height", H, 6, 300)
    r = {"square": 0.01, "rounded": min(3.0, H / 4), "pill": H / 2 - 0.01}[corners]
    outline = RectangleRounded(W, H, r) if r > 0.05 else Rectangle(W, H)
    plate = extrude(outline, amount=t)
    cx = (left - right) / 2                      # the text sits in what's left between the fixings
    faces = [Pos(cx, 0) * p for p in parts]

    def solid(amount: float, z: float):
        # Every letter's faces raised into solids and joined in one go (a letter can be several overlapping pieces).
        # Joined flat first (letters can overlap, and a letter can be several pieces), then raised.
        flat = faces[0] if len(faces) == 1 else faces[0].fuse(*faces[1:])
        pieces = [Pos(0, 0, z) * extrude(f, amount=amount, dir=(0, 0, 1)) for f in flat.faces()]
        return pieces[0] if len(pieces) == 1 else pieces[0].fuse(*pieces[1:])

    inlay = None
    if style == "raised":
        z0 = t if two_color else t - 0.01     # its own body sits exactly on the plate; fused, it bites in a hair
        txt = solid(dp, z0)
        if rim:
            ring = extrude(outline, amount=dp) - extrude(RectangleRounded(W - 2 * rim, H - 2 * rim, max(0.05, r - rim)) if r > rim + 0.05
                                                         else Rectangle(W - 2 * rim, H - 2 * rim), amount=dp + 1, both=True)
            txt = txt + Pos(0, 0, z0) * ring
        if two_color:
            inlay = txt
            body = plate
        else:
            body = plate + txt
    else:
        cut = solid(dp + 0.01, t - dp)
        body = plate - cut
        if style == "engraved" and rim:
            inset = 1.0
            groove = extrude(RectangleRounded(W - 2 * inset, H - 2 * inset, max(0.05, r - inset)) if r > inset + 0.05 else Rectangle(W - 2 * inset, H - 2 * inset), amount=dp + 0.01) \
                - extrude(RectangleRounded(W - 2 * inset - 2 * 0.8, H - 2 * inset - 2 * 0.8, max(0.05, r - inset - 0.8)) if r > inset + 0.85
                          else Rectangle(W - 2 * inset - 1.6, H - 2 * inset - 1.6), amount=dp + 1, both=True)
            body -= Pos(0, 0, t - dp) * groove
        if style == "flush":
            inlay = solid(dp, t - dp)
    notes = [f"label {W:.1f} x {H:.1f} x {t:g} mm, {len(lines)} line{'s' if len(lines) != 1 else ''} of {(shrunk or size):g} mm text, {style}"
             + (f" {dp:g} mm" if style != "flush" else f" in a second colour, {dp:g} mm deep")
             + (", with a border" if rim else "") + (", with your logo" if logo else f", {icon} icon" if icon else "")
             + (f", in {family}" + (" Bold" if file_is_bold else "") if family else "")]
    if not lines:
        notes[0] = notes[0].replace(f"0 lines of {(shrunk or size):g} mm text", "your logo alone").replace(", with your logo", "")
    checks = []
    if shrunk:
        notes.append(f"the text was sized to {'fill' if fill and not too_big else 'fit'} the tag you set: {shrunk:g} mm tall "
                     f"(it was {size:g}); untick 'Fill the tag with the text' to keep your own size" if fill else
                     f"the text was shrunk from {size:g} to {shrunk:g} mm to fit the size you set")
    if family and bold and not file_is_bold:
        notes.append(f"{family} has no bold of its own, so the regular weight is used")
    hx_l, hx_r = -W / 2 + left / 2, W / 2 - right / 2
    if mount == "screw holes":
        for x in (hx_l, hx_r):
            body -= Pos(x, 0, t) * _csk(3.6, min(7.0, H - 3), 30)
            if inlay is not None:
                inlay -= Pos(x, 0, -1) * Cylinder(4.5, 50, align=MIN_)
        notes.append(f"two countersunk Ø3.6 mm holes (M3 or a #4 screw), {hx_r - hx_l:.1f} mm apart")
    elif mount == "cable tie slots":
        sl = min(5.5, H - 4)
        for x in (hx_l, hx_r):
            body -= Pos(x, 0, -1) * Box(2.2, sl, t + 20, align=MIN_)
        notes.append(f"a 2.2 x {sl:g} mm slot at each end for a cable tie up to {sl - 0.5:g} mm wide: tie it round a cable, a pipe or a valve")
    elif mount == "key ring hole":
        body -= Pos(-W / 2 + 5.0, 0, -1) * Cylinder(2.5, t + 20, align=MIN_)
        notes.append("a Ø5 mm hole at the left end for a key ring or a cord")
    elif mount == "magnets":
        mx = W / 2 - 6.5 / 2 - 3
        for x in ((-mx, mx) if W > 40 else (0.0,)):
            body -= Pos(x, 0, -0.01) * Cylinder(6.5 / 2, 2.3, align=MIN_)
        notes.append(f"{'two pockets' if W > 40 else 'a pocket'} in the back for 6 x 2 mm magnets (Ø6.5 x 2.3 mm, glued in), "
                     f"which is why the plate is {t:g} mm thick")
    elif mount == "stake":
        sw, sl = min(12.0, W * 0.5), max(60.0, 1.2 * H)
        body += extrude(Polygon((-sw / 2, -H / 2 + 0.5), (sw / 2, -H / 2 + 0.5), (sw / 2, -H / 2 - sl * 0.7), (0, -H / 2 - sl), (-sw / 2, -H / 2 - sl * 0.7), align=None),
                        amount=t, dir=(0, 0, 1))
        notes.append(f"a {sl:.0f} mm stake underneath to push into soil")
        if t < 2:
            checks.append("a stake under 2 mm thick snaps easily: thicken the plate")
    if style == "raised" and not two_color:
        notes.append(f"for a second colour without a multi-colour printer, pause at {t:g} mm (where the text starts) and change filament")
    elif inlay is not None:
        notes.append("the text is its own body, in place: in the slicer load both files as one object and give the text another filament")
    notes.append("print it flat, face up, as it lies")
    strokes = 0.12 * (shrunk or size)
    if strokes < 0.5:
        checks.append(f"text {(shrunk or size):g} mm tall has strokes about {strokes:.1f} mm wide: thinner than a 0.4 mm nozzle draws cleanly. "
                      "5 mm or taller reads well")
    out = _out(body, notes, checks, {"size": [round(W, 1), round(H, 1), t], "text_size": shrunk or size})
    if inlay is not None:
        out["inlay"] = inlay
    return out


# ---------- What the page needs to know ----------

def _font_names() -> list:
    from . import fonts
    return [fonts.DEFAULT] + sorted(fonts.FAMILIES)


# kind -> (function, label, defaults)
KINDS = {
    "shelf_bracket": (shelf_bracket, "Shelf bracket", {"height": 100.0, "depth": 120.0, "width": 25.0, "thickness": 5.0, "screw_d": 4.5,
                                                         "holes": 2, "brace": True}),
    "corner_brace": (corner_brace, "Corner brace", {"leg": 40.0, "width": 20.0, "thickness": 4.0, "screw_d": 4.5, "holes": 2, "rib": True}),
    "pipe_clamp": (pipe_clamp, "Pipe or conduit clamp", {"pipe_d": 22.0, "width": 15.0, "thickness": 3.0, "screw_d": 4.5, "ears": 2}),
    "pegboard_hook": (pegboard_hook, "Pegboard hook", {"board": "1/4 in holes, 1 in apart", "reach": 50.0, "tip": 10.0, "arm": 6.0}),
    "wall_pocket": (wall_pocket, "Wall holder (pocket to size)", {"item_w": 80.0, "item_d": 15.0, "height": 60.0, "wall": 2.4,
                                                                    "front_slot": 0.0, "cable_slot": 0.0, "screw_d": 4.5}),
    "cable_comb": (cable_comb, "Cable comb", {"cables": 6, "cable_d": 5.0, "thickness": 5.0, "mount": False, "screw_d": 3.5}),
    "raceway": (raceway, "Cable raceway with lid", {"length": 150.0, "width": 20.0, "height": 15.0, "wall": 1.6, "screw_d": 4.0, "holes": 2}),
    "desk_grommet": (desk_grommet, "Desk cable grommet", {"hole_d": 60.0, "depth": 25.0, "flange": 8.0, "cable_slot": 22.0}),
    "bit_holder": (bit_holder, "Bit holder", {"rows": 2, "cols": 6, "hole": "hex", "hole_d": 6.35, "depth": 12.0}),
    "tool_rack": (tool_rack, "Tool rack", {"slots": 5, "shaft_d": 8.0, "pitch": 30.0, "reach": 30.0, "thickness": 5.0, "screw_d": 4.5}),
    "sanding_block": (sanding_block, "Sanding block", {"length": 120.0, "width": 65.0, "height": 30.0}),
    "drill_guide": (drill_guide, "Drill guide", {"sizes": "3, 4, 5, 6, 8", "height": 25.0, "v_groove": True, "corner_radius": 0.0, "engrave": True}),
    "foot": (foot, "Foot", {"diameter": 30.0, "height": 15.0, "taper": 0.8, "screw_d": 4.5}),
    "end_cap": (end_cap, "Tube end cap", {"shape": "round", "outer": 25.0, "outer2": 25.0, "tube_wall": 1.5, "insert": 15.0, "cap": 3.0}),
    "shim": (shim, "Shim or wedge", {"length": 50.0, "width": 30.0, "thickness": 2.0, "thickness2": 0.0, "slot": 0.0}),
    "hole_plug": (hole_plug, "Hole plug", {"hole_d": 20.0, "panel": 2.0, "flange": 3.0}),
    "drawer_organizer": (drawer_organizer, "Drawer organiser", {"length": 150.0, "width": 80.0, "height": 40.0, "wall": 1.2,
                                                                  "div_x": 2, "div_y": 0, "corner": 3.0}),
    "battery_caddy": (battery_caddy, "Battery storage block", {"cell": "AA", "rows": 2, "cols": 4, "depth_fraction": 0.5}),
    "label_plate": (label_plate, "Label, tag or name plate", {"text": "PUMP 1", "text_size": 8.0, "style": "raised", "mount": "none",
                                                               "width": 0.0, "height": 0.0, "thickness": 2.0, "depth": 0.6, "bold": True,
                                                               "fit_text": True, "font": "Default (DejaVu Sans)", "google_font": "",
                                                               "border": True, "corners": "rounded", "icon": "", "logo": "", "logo_only": False,
                                                               "two_color": False}),
    "battery_holder": (battery_holder, "Battery compartment (with contact slots)", {"cell": "18650", "count": 1, "bays": BATTERY_BAYS[0], "cell_length": 0.0,
                                                                                    "contact_room": 6.5, "contact_w": 0.0, "contact_t": 0.6,
                                                                                    "mount": "external ears", "ear_side": "front and back"}),
    "fan_guard": (fan_guard, "Fan guard", {"fan": 80, "thickness": 2.4, "bar": 1.6, "gap": 7.0}),
    "fan_adapter": (fan_adapter, "Fan size adapter", {"from_size": 120, "to_size": 80, "height": 0.0, "wall": 2.0}),
}
SCREW_HOLE = ("Screw hole (4.5 suits a #8 or 4 mm screw)", "len")
KIND_LABELS = {
    **{(k, "screw_d"): SCREW_HOLE for k in ("shelf_bracket", "corner_brace", "pipe_clamp", "wall_pocket", "tool_rack", "raceway")},
    ("shelf_bracket", "height"): ("Up the wall", "len"), ("shelf_bracket", "depth"): ("Under the shelf", "len"),
    ("shelf_bracket", "holes"): ("Holes on each leg", "num"), ("shelf_bracket", "brace"): ("Diagonal brace", "bool"),
    ("corner_brace", "leg"): ("Leg length", "len"), ("corner_brace", "holes"): ("Holes on each leg", "num"),
    ("corner_brace", "rib"): ("Web in the corner", "bool"),
    ("pipe_clamp", "pipe_d"): ("Pipe outside diameter", "len"), ("pipe_clamp", "ears"): ("Screw ears", "select"),
    ("pegboard_hook", "board"): ("Pegboard", "select"), ("pegboard_hook", "reach"): ("Reach", "len"),
    ("pegboard_hook", "tip"): ("Upturned tip", "len"), ("pegboard_hook", "arm"): ("Arm thickness", "len"),
    ("wall_pocket", "item_w"): ("Item width", "len"), ("wall_pocket", "item_d"): ("Item depth (front to back)", "len"),
    ("wall_pocket", "height"): ("Pocket height", "len"), ("wall_pocket", "front_slot"): ("Slot down the front (0 for none)", "len"),
    ("wall_pocket", "cable_slot"): ("Cable slot in the floor (0 for none)", "len"),
    ("cable_comb", "cables"): ("Cables", "num"), ("cable_comb", "mount"): ("Screw holes at the ends", "bool"),
    ("cable_comb", "screw_d"): ("Screw hole", "len"),
    ("raceway", "height"): ("Height", "len"), ("raceway", "holes"): ("Screw holes (0: tape it down)", "num"),
    ("desk_grommet", "hole_d"): ("Hole in the desk", "len"), ("desk_grommet", "depth"): ("Sleeve depth", "len"),
    ("desk_grommet", "flange"): ("Flange (each side of the hole)", "len"), ("desk_grommet", "cable_slot"): ("Cable notch (0 for none)", "len"),
    ("bit_holder", "rows"): ("Rows", "num"), ("bit_holder", "cols"): ("Columns", "num"), ("bit_holder", "hole"): ("Holes", "select"),
    ("bit_holder", "hole_d"): ("Bit size (hex: across flats)", "len"), ("bit_holder", "depth"): ("Hole depth", "len"),
    ("tool_rack", "slots"): ("Slots", "num"), ("tool_rack", "shaft_d"): ("Shaft diameter", "len"),
    ("tool_rack", "pitch"): ("Slot spacing", "len"), ("tool_rack", "reach"): ("Shelf reach from the wall", "len"),
    ("sanding_block", "height"): ("Height", "len"),
    ("drill_guide", "sizes"): ("Drill sizes: mm, or fractions for inches (3, 5, 1/4, 13/64)", "text"),
    ("drill_guide", "corner_radius"): ("Radius on the corners you hold (0: square)", "len"), ("drill_guide", "engrave"): ("Cut each size into the top", "bool"), ("drill_guide", "height"): ("Height", "len"),
    ("drill_guide", "v_groove"): ("V groove underneath", "bool"),
    ("foot", "height"): ("Height", "len"), ("foot", "taper"): ("Floor end, as a part of the diameter", "num"),
    ("foot", "screw_d"): ("Screw hole (0 for none)", "len"),
    ("end_cap", "shape"): ("Tube", "select"), ("end_cap", "outer"): ("Outside size (diameter or side)", "len"),
    ("end_cap", "outer2"): ("Other side (rectangle only)", "len"), ("end_cap", "tube_wall"): ("Tube wall", "len"),
    ("end_cap", "insert"): ("Plug length", "len"), ("end_cap", "cap"): ("Head thickness", "len"),
    ("shim", "thickness2"): ("Thickness at the other end (0: flat)", "len"), ("shim", "slot"): ("Slot width (0 for none)", "len"),
    ("hole_plug", "hole_d"): ("Hole", "len"), ("hole_plug", "flange"): ("Flange (each side of the hole)", "len"),
    ("drawer_organizer", "height"): ("Height", "len"), ("drawer_organizer", "div_x"): ("Dividers across the length", "num"),
    ("drawer_organizer", "div_y"): ("Dividers across the width", "num"), ("drawer_organizer", "corner"): ("Corner radius", "len"),
    ("battery_caddy", "cell"): ("Cell", "select"), ("battery_caddy", "rows"): ("Rows", "num"), ("battery_caddy", "cols"): ("Columns", "num"),
    ("battery_caddy", "depth_fraction"): ("Pocket depth, as a part of the cell", "num"),
    ("label_plate", "text"): ("Text (put | between lines)", "text"), ("label_plate", "text_size"): ("Text height", "len"),
    ("label_plate", "style"): ("Text", "select"), ("label_plate", "mount"): ("Fixing", "select"),
    ("label_plate", "width"): ("Width (0: fit the text)", "len"), ("label_plate", "height"): ("Height (0: fit the text)", "len"),
    ("label_plate", "depth"): ("Text depth or height", "len"), ("label_plate", "bold"): ("Bold", "bool"),
    ("label_plate", "border"): ("Border", "bool"), ("label_plate", "corners"): ("Corners", "select"), ("label_plate", "icon"): ("Icon", "select"),
    ("label_plate", "two_color"): ("Two colours", "bool"), ("label_plate", "fit_text"): ("Fill the tag with the text", "bool"),
    ("label_plate", "font"): ("Font", "select"), ("label_plate", "google_font"): ("Or any other Google font, by name", "text"),
    ("label_plate", "logo"): ("Your logo, SVG or DXF (used instead of the icon)", "file"),
    ("label_plate", "logo_only"): ("Logo only, no text", "bool"),
    ("battery_holder", "cell"): ("Cell", "select"), ("battery_holder", "count"): ("Cells, side by side", "num"),
    ("battery_holder", "cell_length"): ("Cell length (0: standard; a protected 18650 is 68 to 70)", "len"),
    ("battery_holder", "contact_room"): ("Room for both contacts", "len"), ("battery_holder", "contact_w"): ("Contact plate width (0: usual)", "len"),
    ("battery_holder", "contact_t"): ("Contact plate thickness", "len"), ("battery_holder", "mount"): ("Screw fixing", "select"),
    ("battery_holder", "ear_side"): ("External ears on", "select"),
    ("battery_holder", "bays"): ("With more than one cell", "select"),
    ("fan_guard", "fan"): ("Fan size, mm", "select"), ("fan_guard", "bar"): ("Bar width", "len"), ("fan_guard", "gap"): ("Gap between bars", "len"),
    ("fan_adapter", "from_size"): ("Bigger fan, mm", "select"), ("fan_adapter", "to_size"): ("Smaller fan, mm", "select"),
    ("fan_adapter", "height"): ("Height (0: shortest that prints)", "len"),
}
CHOICES = {
    ("pipe_clamp", "ears"): [1, 2], ("pegboard_hook", "board"): list(PEGBOARDS), ("bit_holder", "hole"): ["hex", "round"],
    ("end_cap", "shape"): ["round", "square", "rectangle"], ("battery_caddy", "cell"): list(CELL_SIZES),
    ("label_plate", "style"): list(LABEL_STYLES), ("label_plate", "mount"): list(LABEL_MOUNTS), ("label_plate", "font"): _font_names(),
    ("label_plate", "corners"): ["rounded", "square", "pill"], ("label_plate", "icon"): ["", "usb", "power", "antenna", "fan", "dc", "fuse", "lan", "onoff"],
    ("battery_holder", "cell"): list(HOLDER_CELLS) + ["9V"], ("battery_holder", "mount"): list(BATTERY_MOUNTS),
    ("battery_holder", "ear_side"): list(EAR_SIDES), ("battery_holder", "bays"): list(BATTERY_BAYS),
    ("fan_guard", "fan"): list(FANS), ("fan_adapter", "from_size"): list(FANS), ("fan_adapter", "to_size"): list(FANS),
}
