"""More printed things: parts to replace a broken one from caliper readings, mounts for common
boards, a kit for aluminium T-slot extrusion, shop jigs, funnels and hose adapters, and panel parts
for trainers and test gear. Same form as useful.py: built the way it prints, {shape, notes, checks,
info, buy} back.
"""

from __future__ import annotations

import math

from build123d import (Align, Axis, Box, Circle, Cone, Cylinder, Plane, Polygon, Pos, Rectangle, RectangleRounded, Rot,
                       chamfer, extrude, fillet, loft, revolve)

from .useful import MIN_, _csk, _out, _prism, _rng, _spaced


def _tube(ro: float, ri: float, h: float):
    return Cylinder(ro, h, align=MIN_) - Pos(0, 0, -1) * Cylinder(ri, h + 2, align=MIN_)


# ---------- Measure and replace ----------

def bushing(od=12.0, bore=6.0, length=10.0, flange_d=0.0, flange_t=2.0):
    """A bushing, sleeve or round spacer from three caliper readings: outside diameter, bore and
    length, with a flange at one end if the old one had one."""
    od, bore, ln, fd, ft = float(od), float(bore), float(length), float(flange_d), float(flange_t)
    _rng("outside diameter", od, 3, 150); _rng("bore", bore, 0, od - 1.6); _rng("length", ln, 1, 200)
    body = Cylinder(od / 2, ln, align=MIN_)
    if fd > 0:
        _rng("flange diameter", fd, od + 1, 200); _rng("flange thickness", ft, 0.8, ln)
        body += Cylinder(fd / 2, ft, align=MIN_)
    if bore > 0:
        body -= Pos(0, 0, -1) * Cylinder(bore / 2, ln + 2, align=MIN_)
    notes = [f"bushing Ø{od:g} x {ln:g} mm" + (f" with a Ø{bore:g} mm bore" if bore > 0 else ", solid")
             + (f" and a Ø{fd:g} x {ft:g} mm flange" if fd > 0 else ""),
             "print it standing" + (" on its flange" if fd > 0 else "") + "; holes print about 0.2 mm small, so add that to the bore for a sliding fit"]
    return _out(body, notes, ["a wall under 1.2 mm is fragile"] if bore > 0 and (od - bore) / 2 < 1.2 else [])


def flat_plate(length=80.0, width=50.0, thickness=3.0, corner=3.0, holes="corners", hole_d=4.5, inset=8.0, across=2, down=2,
               countersink=False, centre_hole=0.0):
    """A flat plate with a pattern of holes: a cover, a patch, an adapter or a mounting plate. Holes
    at the corners, in a grid, or none, and a big hole in the middle if you need one."""
    Ln, W, t, r = float(length), float(width), float(thickness), float(corner)
    _rng("length", Ln, 10, 400); _rng("width", W, 10, 400); _rng("thickness", t, 0.8, 20); _rng("hole", hole_d, 1.5, 20)
    if holes not in ("corners", "grid", "none"):
        raise ValueError("holes: corners, grid or none")
    r = max(0.0, min(r, Ln / 2 - 0.1, W / 2 - 0.1))
    body = extrude(RectangleRounded(Ln, W, r) if r > 0.05 else Rectangle(Ln, W), amount=t)
    ins = float(inset)
    nx, ny = (2, 2) if holes == "corners" else (int(across), int(down))
    pts = []
    if holes != "none":
        _rng("holes across", nx, 1, 20, ""); _rng("holes down", ny, 1, 20, "")
        if ins < hole_d / 2 + 1.5 or 2 * ins > min(Ln, W):
            raise ValueError(f"hole inset: {hole_d / 2 + 1.5:g} to {min(Ln, W) / 2:g} mm from the edge")
        pts = [(x, y) for x in _spaced(nx, -Ln / 2 + ins, Ln / 2 - ins) for y in _spaced(ny, -W / 2 + ins, W / 2 - ins)]
        for x, y in pts:
            body -= (Pos(x, y, t) * _csk(hole_d, 2 * hole_d, 40)) if countersink else Pos(x, y, -1) * Cylinder(hole_d / 2, t + 2, align=MIN_)
    if centre_hole > 0:
        _rng("middle hole", centre_hole, 2, min(Ln, W) - 6)
        body -= Pos(0, 0, -1) * Cylinder(centre_hole / 2, t + 2, align=MIN_)
    notes = [f"plate {Ln:g} x {W:g} x {t:g} mm, corners R{r:g}"
             + (f", {len(pts)} {'countersunk ' if countersink else ''}Ø{hole_d:g} mm holes {ins:g} mm in from the edges" if pts else ", no holes")
             + (f" ({Ln - 2 * ins:g} x {W - 2 * ins:g} mm between centres)" if holes == "corners" else "")
             + (f", a Ø{centre_hole:g} mm hole in the middle" if centre_hole > 0 else ""), "print it flat"]
    return _out(body, notes, [], {"hole_centres": [[round(x, 2), round(y, 2)] for x, y in pts]})


def tool_clip(grip_d=25.0, width=15.0, wall=2.4, screw_d=4.5):
    """A spring clip that grips a round handle (a broom, a torch, a tube, a tool): a C that the
    handle presses into, on a foot with a countersunk screw hole. Printed on its side."""
    d, W, t = float(grip_d), float(width), float(wall)
    _rng("handle diameter", d, 6, 80); _rng("width", W, 8, 50); _rng("wall", t, 1.6, 5)
    head = 2 * screw_d
    if W < head + 2:
        raise ValueError(f"a {screw_d:g} mm screw's head needs a clip at least {head + 2:g} mm wide")
    r = d / 2 - 0.3                     # a touch under size, so it grips
    R = r + t
    base_t = max(3.2, (head - screw_d) / 2 + 2.0)
    cy = base_t + r
    half = math.radians(55)             # the opening, each side of straight out
    ring = extrude(Pos(0, cy) * Circle(R), amount=W) - extrude(Pos(0, cy) * Circle(r), amount=W * 3, both=True)
    gap = _prism([(0, cy), (2 * R * math.sin(half), cy + 2 * R * math.cos(half)), (-2 * R * math.sin(half), cy + 2 * R * math.cos(half))], W * 3)
    ring -= Pos(0, 0, -W) * gap
    for s in (-1, 1):                   # flared lips to lead the handle in
        lx, ly = s * (r + t / 2) * math.sin(half), cy + (r + t / 2) * math.cos(half)
        ring += extrude(Pos(lx + s * t * 0.25, ly + t * 0.2) * Circle(t * 0.8), amount=W)
    foot = _prism([(-R * 0.75, 0), (R * 0.75, 0), (R * 0.75, base_t + r * 0.25), (-R * 0.75, base_t + r * 0.25)], W)
    body = foot + ring
    body -= extrude(Pos(0, cy) * Circle(r), amount=W * 3, both=True)
    body -= Pos(0, base_t - 0.4, W / 2) * (Rot(-90, 0, 0) * _csk(screw_d, head, 40))    # the head sits just under the handle
    notes = [f"spring clip for a Ø{d:g} mm handle: {W:g} mm wide, {t:g} mm wall, a 110° opening, a countersunk Ø{screw_d:g} mm hole "
             "in the foot (reached through the opening)", "print it on its side as it lies; PETG springs, PLA cracks in time"]
    return _out(body, notes, ["a thick wall on a small clip is stiff: it may not open far enough"] if t > d * 0.14 else [])


def slip_cap(shape="round", inner=25.0, inner2=25.0, depth=20.0, wall=2.0, top=2.0, fit=0.2):
    """A cap that slips over the outside of a post, a tube, a leg or a pipe end: round, square or
    rectangular. The inside is the size you measure, plus a little to go on."""
    if shape not in ("round", "square", "rectangle"):
        raise ValueError("shape: round, square or rectangle")
    A, B = float(inner), float(inner2) if shape == "rectangle" else float(inner)
    dp, w, tp, f = float(depth), float(wall), float(top), float(fit)
    _rng("inside size", A, 4, 200); _rng("inside size (other way)", B, 4, 200); _rng("depth", dp, 3, 150)
    _rng("wall", w, 1.2, 6); _rng("top", tp, 1, 10); _rng("fit", f, 0, 1.5)
    ia, ib = A + 2 * f, B + 2 * f

    def sec(a, b, r):
        return Circle(a / 2) if shape == "round" else RectangleRounded(a, b, max(0.3, min(r, a / 2 - 0.1, b / 2 - 0.1)))
    body = extrude(sec(ia + 2 * w, ib + 2 * w, 2.0 + w), amount=dp + tp)
    try:
        body = chamfer(body.edges().group_by(Axis.Z)[0], min(1.0, tp * 0.4))
    except Exception:
        pass
    body -= Pos(0, 0, tp) * extrude(sec(ia, ib, 2.0), amount=dp + 1)
    size = f"Ø{A:g}" if shape == "round" else f"{A:g} x {B:g}"
    return _out(body, [f"slip-on cap for a {shape} {size} mm end: inside {ia:g}" + ("" if shape == "round" else f" x {ib:g}")
                       + f" mm ({f:g} mm of fit each side), {dp:g} mm deep, walls {w:g} mm", "print it top down as it stands; TPU grips and protects a floor"])


def edge_clip(panel=3.0, depth=12.0, length=30.0, wall=1.8, grip=0.3):
    """A U clip that pushes onto the edge of a panel, a shelf or a sheet: to hold something to it, cap
    a sharp edge, or join two sheets. Its jaws lean in a little so it grips."""
    p, dp, ln, w, g = float(panel), float(depth), float(length), float(wall), float(grip)
    _rng("panel thickness", p, 0.5, 40); _rng("depth", dp, 4, 80); _rng("length", ln, 5, 300); _rng("wall", w, 1.2, 5)
    _rng("grip", g, 0, min(1.5, p * 0.4))
    # Outline in XY, printed on its side: the back along x = 0, the jaws along +x, leaning in by `grip` at their tips.
    yo = p / 2 + w
    pts = [(0, -yo), (w + dp, -(yo - g)), (w + dp, -(p / 2 - g)), (w, -p / 2), (w, p / 2), (w + dp, p / 2 - g), (w + dp, yo - g), (0, yo)]
    body = _prism(pts, ln)
    notes = [f"edge clip for a {p:g} mm panel: {dp:g} mm deep, {ln:g} mm long, jaws {w:g} mm thick leaning in {g:g} mm each to grip",
             "print it on its side as it lies"]
    return _out(body, notes)


# ---------- Mounts for common boards ----------

# name -> (length, width, [(x, y) of each mounting hole from one corner], hole diameter, screw for it)
BOARDS = {
    "Raspberry Pi 3, 4 or 5 (Model B)": (85.0, 56.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)], 2.7, "M2.5"),
    "Raspberry Pi Zero": (65.0, 30.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 26.5), (61.5, 26.5)], 2.75, "M2.5"),
    "Raspberry Pi Pico": (51.0, 21.0, [(2.0, 4.8), (49.0, 4.8), (2.0, 16.2), (49.0, 16.2)], 2.1, "M2"),
    "Arduino Uno": (68.6, 53.4, [(13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)], 3.2, "M3"),
    "Arduino Mega 2560": (101.6, 53.4, [(13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56), (90.17, 50.8), (96.52, 2.54)], 3.2, "M3"),
    "Arduino Nano": (43.2, 17.8, [], 0.0, ""),
    "ESP32 DevKit (38 pin; clones vary, measure)": (55.0, 28.0, [], 0.0, ""),
    "Your own board": (0.0, 0.0, [], 0.0, ""),
}
PILOT = {"M2": 1.7, "M2.5": 2.1, "M3": 2.5}      # a hole a screw of that size cuts its own thread in


def board_mount(board="Raspberry Pi 3, 4 or 5 (Model B)", style="standoffs", standoff=5.0, board_l=60.0, board_w=40.0,
                hole_l=52.0, hole_w=32.0, screw="M3", base=2.4, plate_holes=True):
    """A mount for a circuit board, by name: a Raspberry Pi, a Pico, an Arduino, or your own board's
    size and holes. Either a plate with standoffs under the board's mounting holes, or a corner tray
    that holds the board by its corners with two snap hooks (for boards with no holes)."""
    if board not in BOARDS:
        raise ValueError(f"board: one of {', '.join(BOARDS)}")
    if style not in ("standoffs", "corner tray"):
        raise ValueError("style: standoffs or corner tray")
    L, W, holes, hd, scr = BOARDS[board]
    if board == "Your own board":
        L, W = float(board_l), float(board_w)
        _rng("board length", L, 10, 300); _rng("board width", W, 8, 300)
        if screw not in PILOT:
            raise ValueError(f"screw: one of {', '.join(PILOT)}")
        scr = screw
        if style == "standoffs":
            hl, hw = float(hole_l), float(hole_w)
            if not (4 <= hl <= L - 3 and 4 <= hw <= W - 3):
                raise ValueError("the holes' spacing must fit inside the board")
            holes = [((L - hl) / 2 + i * hl, (W - hw) / 2 + j * hw) for i in (0, 1) for j in (0, 1)]
    h, bt = float(standoff), float(base)
    _rng("standoff height", h, 2, 40); _rng("base", bt, 1.6, 6)
    notes, checks = [], []
    if style == "standoffs":
        if not holes:
            raise ValueError(f"the {board.split(' (')[0]} has no usable mounting holes: use the corner tray")
        pilot = PILOT[scr]
        margin = 9.0 if plate_holes else 3.0
        plate = extrude(RectangleRounded(L + 2 * margin, W + 6, 3.0), amount=bt)
        body = plate
        od = pilot + 3.6
        for x, y in holes:
            px, py = x - L / 2, y - W / 2
            body += Pos(px, py, bt - 0.01) * Cone(od / 2 + 1.0, od / 2, h + 0.01, align=MIN_)
            body -= Pos(px, py, bt + h - min(h + bt - 0.8, 8.0)) * Cylinder(pilot / 2, 20, align=MIN_)
        if plate_holes:
            for sx in (-1, 1):
                for sy in (-1, 1):
                    body -= Pos(sx * (L / 2 + margin - 4.5), sy * (W / 2 - 4), bt) * _csk(3.6, 7.0, 20)
        notes.append(f"standoff plate for the {board.split(' (')[0]} ({L:g} x {W:g} mm): {len(holes)} standoffs {h:g} mm tall under its "
                     f"mounting holes, with Ø{pilot:g} mm holes for {scr} screws to cut their own thread"
                     + (", and four countersunk Ø3.6 mm holes in the plate" if plate_holes else ""))
        info = {"board": [L, W], "standoffs": [[round(x, 2), round(y, 2)] for x, y in holes]}
    else:
        pcb, cl, wall = 1.7, 0.3, 2.0
        body = extrude(RectangleRounded(L + 2 * (cl + wall), W + 2 * (cl + wall), 2.5), amount=bt)
        arm = min(9.0, L / 4, W / 3)
        for sx in (-1, 1):
            for sy in (-1, 1):
                cx, cy = sx * (L / 2 + cl), sy * (W / 2 + cl)          # the board's corner, with clearance
                post = Pos(cx + sx * wall / 2 - sx * arm / 2 - sx * 0, cy + sy * wall / 2, bt - 0.01) * Box(arm + wall, wall, h + pcb + 1.2, align=MIN_)
                post += Pos(cx + sx * wall / 2, cy + sy * wall / 2 - sy * arm / 2, bt - 0.01) * Box(wall, arm + wall, h + pcb + 1.2, align=MIN_)
                # A ledge inside the corner for the board to sit on.
                post += Pos(cx - sx * 1.5, cy - sy * 1.5, bt - 0.01) * Box(3.0 + 0.02, 3.0 + 0.02, h + 0.01, align=MIN_)
                body += post
        hook_w = min(8.0, L / 5)
        for sy in (-1, 1):                                             # a snap hook at the middle of each long side
            y0 = sy * (W / 2 + cl)
            top_z = bt + h + pcb
            prof = [(y0, bt - 0.01), (y0 + sy * 1.6, bt - 0.01), (y0 + sy * 1.6, top_z + 2.2), (y0 - sy * 0.1, top_z + 2.2),
                    (y0 - sy * 0.8, top_z + 0.9), (y0 - sy * 0.8, top_z + 0.2), (y0, top_z + 0.2)]
            body += Pos(-hook_w / 2, 0, 0) * extrude(Plane.YZ * Polygon(*prof, align=None), amount=hook_w, dir=(1, 0, 0))
        for sx in (-1, 1):
            body -= Pos(sx * L * 0.25, 0, bt) * _csk(3.6, 7.0, 20)
        notes.append(f"corner tray for the {board.split(' (')[0]} ({L:g} x {W:g} mm): the board drops into four corner posts and sits "
                     f"on ledges {h:g} mm above the base; a snap hook on each long side holds it (0.8 mm over the board's top); two "
                     "countersunk Ø3.6 mm holes in the base")
        checks.append("check the hooks and corners clear the board's parts: a connector that hangs over an edge needs that corner or side free")
        if board.startswith("ESP32") or board == "Arduino Nano":
            checks.append("clone boards differ by a millimetre or more: measure yours, and use 'Your own board' if it isn't this size")
        info = {"board": [L, W]}
    notes.append("print it as it stands, no supports")
    return _out(body, notes, checks, info)


# ---------- T-slot extrusion ----------

# name -> (side, slot width, bolt, its clearance hole, slots on a wide face, wide side)
PROFILES = {
    "1515 (80/20, 1.5 in)": (38.1, 8.13, "5/16-18", 8.4, 1, 38.1),
    "1530 (80/20, 1.5 x 3 in)": (38.1, 8.13, "5/16-18", 8.4, 2, 76.2),
    "1010 (80/20, 1 in)": (25.4, 6.5, "1/4-20", 6.8, 1, 25.4),
    "2020 (20 mm)": (20.0, 6.2, "M5", 5.5, 1, 20.0),
    "3030 (30 mm)": (30.0, 8.2, "M6", 6.6, 1, 30.0),
    "4040 (40 mm)": (40.0, 8.2, "M8", 8.6, 1, 40.0),
}


def _profile(name):
    if name not in PROFILES:
        raise ValueError(f"profile: one of {', '.join(PROFILES)}")
    return PROFILES[name]


def extrusion_end_cap(profile="1515 (80/20, 1.5 in)", thickness=3.0, tab=7.0):
    """An end cap for T-slot extrusion: a plate the size of the profile's end, with a tab that pushes
    into each slot to hold it."""
    side, slot, bolt, _, nwide, wide = _profile(profile)
    t, tb = float(thickness), float(tab)
    _rng("thickness", t, 1.6, 8); _rng("tab length", tb, 3, 15)
    body = extrude(RectangleRounded(wide, side, 2.0), amount=t)
    try:
        body = chamfer(body.edges().group_by(Axis.Z)[0], min(0.8, t * 0.3))
    except Exception:
        pass
    tw, td = slot - 0.15, min(4.0, side * 0.12)
    spots = []                                   # (x, y, turned): a tab at the mouth of each slot
    xs = [0.0] if nwide == 1 else [-wide / 4, wide / 4]
    for x in xs:
        spots += [(x, side / 2 - td / 2, False), (x, -side / 2 + td / 2, False)]
    spots += [(wide / 2 - td / 2, 0.0, True), (-wide / 2 + td / 2, 0.0, True)]
    for x, y, turned in spots:
        tabb = Box(td, tw, tb, align=MIN_) if turned else Box(tw, td, tb, align=MIN_)
        try:
            tabb = chamfer(tabb.edges().group_by(Axis.Z)[-1], 0.6)
        except Exception:
            pass
        body += Pos(x, y, t - 0.01) * tabb
    notes = [f"end cap for {profile}: {wide:g} x {side:g} x {t:g} mm, with {len(spots)} tabs {tw:g} mm wide that push {tb:g} mm into the slots",
             "print it cap down as it stands; if the tabs are loose, a dab of glue, or raise the tab width by scaling"]
    return _out(body, notes, ["slot widths differ a little between makers: try one before printing a set"])


def extrusion_bracket(profile="1515 (80/20, 1.5 in)", leg=0.0, thickness=6.0, holes=1):
    """An inside corner bracket for T-slot extrusion: two legs with a gusset, a clearance hole on each
    leg's slot line. Bolt it down with T-nuts. Printed on its side."""
    side, slot, bolt, clear, nwide, wide = _profile(profile)
    t, n = float(thickness), int(holes)
    _rng("thickness", t, 4, 12); _rng("holes on each leg", n, 1, 2, "")
    Lg = float(leg) or max(side, 2.2 * clear + t + (n - 1) * 2.4 * clear + 8)
    _rng("leg", Lg, 2 * clear + t + 6, 150)
    W = side
    body = _prism([(0, 0), (Lg, 0), (Lg, t), (t, Lg), (0, Lg)], W)          # the two legs and a full gusset
    # Open the gusset over each bolt so a hex key and the bolt's head get in.
    pos = _spaced(n, t + 1.3 * clear + 2, Lg - 1.1 * clear - 2) if n > 1 else [(t + Lg) / 2]
    head = 1.7 * clear
    for p in pos:
        body -= Pos(p, -1, W / 2) * (Rot(-90, 0, 0) * Cylinder(clear / 2, t + 2, align=MIN_))
        body -= Pos(p, t, W / 2) * (Rot(-90, 0, 0) * Cylinder(head / 2 + 0.6, Lg, align=MIN_))
        body -= Pos(-1, p, W / 2) * (Rot(0, 90, 0) * Cylinder(clear / 2, t + 2, align=MIN_))
        body -= Pos(t, p, W / 2) * (Rot(0, 90, 0) * Cylinder(head / 2 + 0.6, Lg, align=MIN_))
    notes = [f"corner bracket for {profile}: legs {Lg:g} mm, {W:g} mm wide, {t:g} mm under each bolt, {n} Ø{clear:g} mm hole"
             f"{'s' if n > 1 else ''} on each leg for {bolt} bolts and T-nuts", "print it on its side as it lies, 5 walls or more: it carries load across the layers otherwise"]
    return _out(body, notes, ["a printed bracket holds light frames and panels; for a cart that carries weight, use metal brackets at the load-bearing corners"],
                {"holes_from_corner": [round(p, 1) for p in pos], "bolt": bolt})


def extrusion_cable_guide(profile="1515 (80/20, 1.5 in)", bundle_d=15.0, width=12.0, wall=2.4):
    """A cable guide for T-slot extrusion: an open hook for a bundle of cables, on a foot that bolts
    to a slot with one T-nut. Printed on its side."""
    side, slot, bolt, clear, _, _ = _profile(profile)
    d, W, t = float(bundle_d), float(width), float(wall)
    _rng("bundle diameter", d, 5, 80); _rng("wall", t, 1.8, 5)
    W = max(W, 1.9 * clear + 3)
    _rng("width", W, 8, 60)
    r, R = d / 2, d / 2 + t
    foot_l = 1.9 * clear + 8
    bt = max(4.0, t)
    # Outline in XY: the extrusion's face along y = 0; the foot to the left, the hook to the right.
    body = _prism([(-foot_l, 0), (R, 0), (R, bt), (-foot_l, bt)], W)
    ring = extrude(Pos(0, bt + r) * Circle(R), amount=W) - extrude(Pos(0, bt + r) * Circle(r), amount=W * 3, both=True)
    ring -= Pos(0, 0, -W) * _prism([(0, bt + r), (-2 * R, bt + r + 0.25 * R), (-2 * R, bt + r + 2.2 * R), (-0.55 * R, bt + r + 2.2 * R)], W * 3)
    body += ring
    body -= extrude(Pos(0, bt + r) * Circle(r), amount=W * 3, both=True)
    body -= Pos(-foot_l / 2 - 1, -1, W / 2) * (Rot(-90, 0, 0) * Cylinder(clear / 2, bt + 2, align=MIN_))
    notes = [f"cable guide for {profile}: an open hook for a Ø{d:g} mm bundle, {W:g} mm wide, one Ø{clear:g} mm hole for a {bolt} bolt and T-nut",
             "print it on its side as it lies"]
    return _out(body, notes)


def extrusion_panel_clip(profile="1515 (80/20, 1.5 in)", panel=3.0, width=20.0, reach=12.0):
    """A panel clip for T-slot extrusion: it bolts to a slot and its finger holds a sheet (acrylic,
    plywood, polycarbonate) down against the frame. Printed on its side."""
    side, slot, bolt, clear, _, _ = _profile(profile)
    p, W, rc = float(panel), float(width), float(reach)
    _rng("panel thickness", p, 1, 25); _rng("reach over the panel", rc, 5, 40)
    W = max(W, 1.9 * clear + 3)
    _rng("width", W, 10, 60)
    t = 4.0
    foot_l = 1.9 * clear + 8
    # Outline in XY: the frame's face along y = 0; the foot on it, then a step up over the panel's edge.
    body = _prism([(0, 0), (foot_l, 0), (foot_l, p - 0.2), (foot_l + rc, p - 0.2), (foot_l + rc, p - 0.2 + t), (foot_l - t, p - 0.2 + t),
                   (foot_l - t, t), (0, t)] if p - 0.2 > t else
                  [(0, 0), (foot_l, 0), (foot_l, p - 0.2), (foot_l + rc, p - 0.2), (foot_l + rc, p - 0.2 + t), (0, p - 0.2 + t)], W)
    body -= Pos(foot_l / 2 - 1, -1, W / 2) * (Rot(-90, 0, 0) * Cylinder(clear / 2, p + t + 4, align=MIN_))
    notes = [f"panel clip for {profile}: holds a {p:g} mm sheet with a finger {rc:g} mm over its edge (0.2 mm of squeeze), {W:g} mm wide, "
             f"one Ø{clear:g} mm hole for a {bolt} bolt and T-nut", "print it on its side as it lies"]
    return _out(body, notes)


def extrusion_handle(profile="1515 (80/20, 1.5 in)", span=120.0, clearance=35.0, width=0.0, grip=14.0):
    """A handle for T-slot extrusion: an arch with a foot at each end, each with a counterbored hole
    for a bolt and T-nut. Printed on its side."""
    side, slot, bolt, clear, _, _ = _profile(profile)
    sp, cl, g = float(span), float(clearance), float(grip)
    _rng("hole spacing", sp, 60, 300); _rng("hand clearance", cl, 20, 80); _rng("grip thickness", g, 8, 30)
    W = float(width) or min(side, max(20.0, 1.9 * clear + 6))
    _rng("width", W, 1.9 * clear + 3, 80)
    foot = 1.9 * clear + 10
    H = cl + g
    half = sp / 2
    out = [(-half - foot / 2, 0), (half + foot / 2, 0), (half + foot / 2, H * 0.55), (half + foot / 2 - H * 0.45, H), (-half - foot / 2 + H * 0.45, H),
           (-half - foot / 2, H * 0.55)]
    body = _prism(out, W)
    inn = [(-half + foot / 2, -1), (half - foot / 2, -1), (half - foot / 2, cl * 0.55), (half - foot / 2 - cl * 0.45, cl), (-half + foot / 2 + cl * 0.45, cl),
           (-half + foot / 2, cl * 0.55)]
    body -= Pos(0, 0, -1) * _prism(inn, W + 2)
    seat = 8.0                                  # plastic under each bolt's head
    for s in (-1, 1):
        body -= Pos(s * half, -1, W / 2) * (Rot(-90, 0, 0) * Cylinder(clear / 2, H + 2, align=MIN_))
        body -= Pos(s * half, seat, W / 2) * (Rot(-90, 0, 0) * Cylinder(0.85 * clear + 0.6, H, align=MIN_))
    try:
        body = fillet(body.edges().filter_by(Axis.Z).group_by(Axis.Y)[-1], min(4.0, g * 0.3))
    except Exception:
        pass
    notes = [f"handle for {profile}: holes {sp:g} mm apart, {cl:g} mm of room for a hand, {W:g} mm wide; each foot has a Ø{clear:g} mm hole "
             f"for a {bolt} bolt and T-nut, its head sunk to {seat:g} mm above the frame", "print it on its side as it lies, 5 walls or more"]
    return _out(body, notes, ["for pulling a loaded cart, a printed handle is the weak link: use it to steer and lift light things"],
                {"bolt": bolt, "bolt_length_under_head": seat})


# ---------- Drilling and alignment jigs for T-slot extrusion ----------

# The hole a hex key reaches a hidden bolt through: 80/20's own jigs use .281 in on 15 series and .201 in on 10
# series; the metric ones here are a size that clears the key for that bolt (4, 5 and 6 mm keys).
ACCESS_HOLE = {"1515 (80/20, 1.5 in)": 7.14, "1530 (80/20, 1.5 x 3 in)": 7.14, "1010 (80/20, 1 in)": 5.1,
               "2020 (20 mm)": 5.0, "3030 (30 mm)": 6.0, "4040 (40 mm)": 7.0}
JIG_HOLES = ("bolt clearance", "hex key access")


def _jig_drill(profile: str, hole: str, drill_d: float) -> tuple[float, str]:
    side, slot, bolt, clear, nwide, wide = _profile(profile)
    if hole not in JIG_HOLES:
        raise ValueError(f"hole: one of {', '.join(JIG_HOLES)}")
    if float(drill_d) > 0:
        _rng("drill", float(drill_d), 2, 14)
        return float(drill_d), f"a {float(drill_d):g} mm drill"
    if hole == "bolt clearance":
        return clear, f"a {clear:g} mm drill (clearance for a {bolt} bolt)"
    return ACCESS_HOLE[profile], f"a {ACCESS_HOLE[profile]:g} mm drill (a hex key reaches a {bolt} bolt through it)"


def _saddle(face_w: float, grip: float, length: float, top: float, wall: float, fit: float):
    """A channel that sits over an extrusion, printed upside down: its top plate on z = 0 .. top, its two
    side walls standing up from it, the extrusion's face on z = top, its length along X."""
    iw = face_w + 2 * fit
    body = Box(length, iw + 2 * wall, top + grip, align=MIN_)
    body -= Pos(0, 0, top) * Box(length + 2, iw, grip + 1, align=MIN_)
    return body, iw


def _guide(body, x: float, y: float, d: float, top: float, bushing: float):
    """A guide hole down through the top plate, for the drill or for a pressed-in steel bushing."""
    hole = bushing if bushing > 0 else d + 0.25
    return body - Pos(x, y, -1) * Cylinder(hole / 2, top + 2, align=MIN_)


def _slot_lines(profile: str, face: str) -> tuple[float, float, list[float]]:
    """(the face's width, the other side, where the slots run across that face)."""
    side, slot, bolt, clear, nwide, wide = _profile(profile)
    if face not in ("narrow face", "wide face"):
        raise ValueError("face: narrow face or wide face")
    if wide > side and face == "wide face":
        return wide, side, ([-wide / 4, wide / 4] if nwide == 2 else [0.0])
    return side, wide, [0.0]


def extrusion_offset_jig(profile="1515 (80/20, 1.5 in)", offsets="", hole="bolt clearance", drill_d=0.0, bushing_od=0.0,
                         face="narrow face", top=12.0, wall=4.0, fit=0.15):
    """A drilling jig that caps the end of a T-slot extrusion and guides the drill at set distances
    from the end, on the slot's centre line: the holes for a blind joint, where a bolt goes through
    this extrusion into the tapped end of the one that butts against it."""
    side, slot, bolt, clear, nwide, wide = _profile(profile)
    fw, other, lines = _slot_lines(profile, face)
    d, what = _jig_drill(profile, hole, drill_d)
    tp, w, f, bo = float(top), float(wall), float(fit), float(bushing_od)
    _rng("top thickness", tp, 6, 30); _rng("wall", w, 3, 10); _rng("fit", f, 0, 0.6)
    if bo and bo < d + 2:
        raise ValueError(f"a bushing for a {d:g} mm drill is at least {d + 2:g} mm outside")
    if str(offsets).strip():
        try:
            offs = sorted(float(v) for v in str(offsets).replace(";", ",").split(",") if v.strip())
        except ValueError:
            raise ValueError("offsets: distances from the end in mm, with commas between (19.05, 57.15)") from None
    else:
        offs = [side / 2]                         # the centre of a same-size extrusion butted flush with the end
    if not 1 <= len(offs) <= 6 or offs[0] < d / 2 + 1.5 or offs[-1] > 300:
        raise ValueError(f"offsets: 1 to 6 of them, from {d / 2 + 1.5:g} to 300 mm from the end")
    grip = min(other, max(18.0, side * 0.6))
    ln = offs[-1] + max(d, bo) / 2 + 12.0
    stop = 5.0
    body, iw = _saddle(fw, grip, ln + stop, tp, w, f)
    body = Pos((ln + stop) / 2 - stop, 0, 0) * body                   # x = 0 is the extrusion's end; the jig runs along +x
    body += Pos(-stop / 2, 0, 0) * Box(stop, iw + 2 * w, tp + grip, align=MIN_)   # the end stop
    for x in offs:
        for y in lines:
            body = _guide(body, x, y, d, tp, bo)
        for sy in (-1, 1):                                             # a mark on each side at every hole
            body -= Pos(x, sy * (iw / 2 + w), tp + grip) * Box(0.8, 1.6, 6, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    # A clamp bolt through one wall on the slot's line, past the last hole.
    cz = tp + min(grip - clear / 2 - 3, other / 2 if grip >= other / 2 + clear / 2 + 3 else grip / 2)
    body -= Pos(max(offs[-1] / 2, clear), iw / 2 - 1, cz) * (Rot(-90, 0, 0) * Cylinder(clear / 2, w + 2, align=MIN_))
    notes = [f"offset drilling jig for {profile}, on its {fw:g} mm face: it caps the end and guides {what} at "
             f"{', '.join(f'{x:g}' for x in offs)} mm from the end" + (f", on both slot lines ({len(lines) * len(offs)} holes)" if len(lines) > 1 else ", on the slot's centre line"),
             f"the guide is {tp:g} mm deep" + (f", bored Ø{bo:g} mm for a steel drill bushing (press or glue it in)" if bo else
                                              f", a plain Ø{d + 0.25:g} mm printed hole")
             + f"; hold it with a clamp, or with a {bolt} bolt and T-nut through the hole in its side",
             "print it top down as it lies (the open side up), 5 walls or more and 40% infill"]
    checks = []
    if not bo:
        checks.append("a printed guide hole wears after a dozen or so holes in aluminium: for more, set a bushing diameter and fit a steel drill bushing")
    if not str(offsets).strip():
        notes.append(f"{offs[0]:g} mm is half this extrusion: the centre of one the same size butted flush with the end. For another size, or several holes, type the distances")
    return _out(body, notes, checks, {"drill": d, "offsets": offs, "inside_width": round(iw, 2)})


def extrusion_freehand_jig(profile="1515 (80/20, 1.5 in)", holes=1, pitch=0.0, hole="bolt clearance", drill_d=0.0, bushing_od=0.0,
                           face="narrow face", top=12.0, wall=4.0, fit=0.15):
    """A drilling jig that sits anywhere along a T-slot extrusion: line the gap in its side up with
    your mark and it guides the drill on the slot's centre line. One hole, or two or three in a row
    for joining to a double or triple extrusion."""
    side, slot, bolt, clear, nwide, wide = _profile(profile)
    fw, other, lines = _slot_lines(profile, face)
    d, what = _jig_drill(profile, hole, drill_d)
    n, tp, w, f, bo = int(holes), float(top), float(wall), float(fit), float(bushing_od)
    _rng("holes", n, 1, 4, ""); _rng("top thickness", tp, 6, 30); _rng("wall", w, 3, 10); _rng("fit", f, 0, 0.6)
    if bo and bo < d + 2:
        raise ValueError(f"a bushing for a {d:g} mm drill is at least {d + 2:g} mm outside")
    p = float(pitch) or side
    _rng("spacing", p, max(d, bo) + 3, 150)
    grip = min(other, max(18.0, side * 0.6))
    ln = (n - 1) * p + max(d, bo) + 2 * (clear + 10)
    body, iw = _saddle(fw, grip, ln, tp, w, f)
    xs = [(i - (n - 1) / 2) * p for i in range(n)]
    for x in xs:
        for y in lines:
            body = _guide(body, x, y, d, tp, bo)
        for sy in (-1, 1):       # the gap: a slot down each wall at the hole's centre, to see your mark on the extrusion through
            body -= Pos(x, sy * (iw / 2 + w / 2), tp + 3) * Box(2.0, w + 2, grip, align=MIN_)
            body -= Pos(x, sy * (iw / 2 + w), tp / 2) * Box(0.8, 1.6, tp + 2, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    cz = tp + min(grip - clear / 2 - 3, other / 2 if grip >= other / 2 + clear / 2 + 3 else grip / 2)
    for sx in (-1, 1):           # a clamp bolt at each end, on the slot's line
        body -= Pos(sx * (ln / 2 - clear / 2 - 4), iw / 2 - 1, cz) * (Rot(-90, 0, 0) * Cylinder(clear / 2, w + 2, align=MIN_))
    notes = [f"freehand drilling jig for {profile}, on its {fw:g} mm face: {n} guide hole{'s' if n > 1 else ''} for {what}"
             + (f", {p:g} mm apart" if n > 1 else "") + (" on both slot lines" if len(lines) > 1 else " on the slot's centre line"),
             "mark where the hole goes on the extrusion's side, slide the jig along until the mark shows in the middle of the 2 mm gap in its wall, and clamp it; "
             f"or fix it with {bolt} bolts and T-nuts through the holes in its side",
             f"the guide is {tp:g} mm deep" + (f", bored Ø{bo:g} mm for a steel drill bushing" if bo else f", a plain Ø{d + 0.25:g} mm printed hole"),
             "print it top down as it lies (the open side up), 5 walls or more and 40% infill"]
    checks = ["a printed guide hole wears after a dozen or so holes in aluminium: for more, set a bushing diameter and fit a steel drill bushing"] if not bo else []
    return _out(body, notes, checks, {"drill": d, "hole_centres": [round(x, 2) for x in xs], "length": round(ln, 1)})


def extrusion_alignment_jig(profile="1515 (80/20, 1.5 in)", leg=0.0, thickness=8.0, key=1.6):
    """A perpendicular alignment jig for T-slot extrusion: a flat L that bolts across a joint with a
    key in each extrusion's slot, to hold the two flush and square while you tighten the joint. Print
    a pair, one for each side."""
    side, slot, bolt, clear, nwide, wide = _profile(profile)
    t, k = float(thickness), float(key)
    _rng("thickness", t, 5, 15); _rng("key depth", k, 0, 3)
    Lg = float(leg) or round(side * 2.6)
    _rng("leg", Lg, side * 1.8, 300)
    body = _prism([(0, 0), (Lg, 0), (Lg, side), (side, side), (side, Lg), (0, Lg)], t)
    kw = slot - 0.3
    if k > 0:
        # The keys stand up from the plate as it prints (they go down into the slots in use), clear of the corner.
        body += Pos((side + Lg) / 2 + 2, side / 2, t - 0.01) * Box(Lg - side - 4, kw, k, align=MIN_)
        body += Pos(side / 2, (side + Lg) / 2 + 2, t - 0.01) * Box(kw, Lg - side - 4, k, align=MIN_)
    hp = [side + (Lg - side) * 0.3, side + (Lg - side) * 0.8]
    for p_ in hp:
        body -= Pos(p_, side / 2, -1) * Cylinder(clear / 2, t + k + 2, align=MIN_)
        body -= Pos(side / 2, p_, -1) * Cylinder(clear / 2, t + k + 2, align=MIN_)
    body -= Pos(side, side, -1) * Cylinder(3.0, t + 2, align=MIN_)        # relief at the inside corner
    notes = [f"alignment jig for {profile}: a flat L with {Lg:g} mm legs {side:g} mm wide and {t:g} mm thick"
             + (f", a {kw:g} x {k:g} mm key along each leg that sits in the slot" if k > 0 else "")
             + f", two Ø{clear:g} mm holes on each leg for {bolt} bolts and T-nuts",
             "bolt it across the joint with the keys in the slots, tighten the joint, then take it off; a pair, one each side, holds the faces flush too",
             "print it flat as it lies, keys up"]
    return _out(body, notes, ["it is as square as your printer: check a printed one against a square before trusting a frame to it"],
                {"holes_from_corner": [round(v, 1) for v in hp]})


# ---------- Shop jigs ----------

def shelf_pin_jig(holes=6, pitch=32.0, setback=37.0, hole_d=5.0, thickness=8.0, lip=True):
    """A jig for drilling rows of shelf-pin holes: a bar of evenly spaced guide holes with a lip that
    hooks the board's edge. The first and last holes register on a pin to carry the row on."""
    n, p, sb, d, t = int(holes), float(pitch), float(setback), float(hole_d), float(thickness)
    _rng("holes", n, 2, 20, ""); _rng("spacing", p, 12, 100); _rng("setback from the edge", sb, 10, 150)
    _rng("drill", d, 2, 12); _rng("thickness", t, 5, 20)
    Ln, W = (n - 1) * p + 30, sb + 14
    body = Box(Ln, W, t, align=(Align.CENTER, Align.MIN, Align.MIN))
    if lip:
        body += Pos(0, -4, 0) * Box(Ln, 4.01, t + 8, align=(Align.CENTER, Align.MIN, Align.MIN))     # hooks over the board's edge
    for i in range(n):
        x = (i - (n - 1) / 2) * p
        body -= Pos(x, sb, -1) * Cylinder((d + 0.2) / 2, t + 2, align=MIN_)
        body -= Pos(x, W, t) * Box(0.8, 3, 1.2)                               # a mark on the far edge at each hole
    notes = [f"shelf-pin jig: {n} guide holes for a {d:g} mm drill, {p:g} mm apart, {sb:g} mm from the board's edge; {Ln:g} x {W:g} x {t:g} mm"
             + (", with a lip that hooks the edge" if lip else ""),
             "print it flat, lip up, 5 walls: it's printed upside down from how it's used, so flip it over and the lip hangs down over the edge",
             "drop a pin or the drill's shank through the last hole into the hole you just drilled to carry the row on; use a depth stop"]
    return _out(body, notes, ["plastic guide holes wear oversize after a few dozen holes: reprint, or press in metal bushings"])


def clamp_square(leg=100.0, width=25.0, thickness=10.0):
    """A clamping square: a 90 degree corner block with clamp slots, to hold two boards square while
    the glue sets or the screws go in."""
    Lg, W, t = float(leg), float(width), float(thickness)
    _rng("leg", Lg, 50, 250); _rng("width", W, 15, 60); _rng("thickness", t, 6, 25)
    body = _prism([(0, 0), (Lg, 0), (Lg, W), (W * 1.6, W), (W, W * 1.6), (W, Lg), (0, Lg)], t)
    body -= Pos(W * 0.2, W * 0.2, -1) * Box(W * 0.25, W * 0.25, t + 2, align=(Align.MAX, Align.MAX, Align.MIN))  # relief so glue squeeze-out and a proud corner don't hold it off
    slot_w = min(W * 0.4, 9.0)
    for a, b in (((W * 2.0, W / 2), (Lg - W * 0.6, W / 2)), ((W / 2, W * 2.0), (W / 2, Lg - W * 0.6))):
        horiz = abs(a[1] - b[1]) < 1e-6
        ln = (b[0] - a[0]) if horiz else (b[1] - a[1])
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        body -= Pos(cx, cy, -1) * (Box(ln, slot_w, t + 2, align=MIN_) if horiz else Box(slot_w, ln, t + 2, align=MIN_))
    notes = [f"clamping square, legs {Lg:g} mm, {W:g} mm wide, {t:g} mm thick, with a slot in each leg for a clamp's jaw and a relieved inside corner",
             "print it flat; check it against a square you trust before relying on it, and print a pair"]
    return _out(body, notes, ["a printed square is as square as your printer: measure the diagonals of a printed test square first"])


def centre_finder(max_d=100.0, thickness=4.0):
    """A centre finder for round stock: push the bar or disc into the 90 degree corner and scribe
    along the straight edge, turn it, scribe again. The lines cross at the centre."""
    D, t = float(max_d), float(thickness)
    _rng("largest diameter", D, 20, 250); _rng("thickness", t, 2.5, 8)
    a = D * 0.62                                    # the fences' length
    body = _prism([(0, 0), (a, 0), (a, 6), (6, 6), (6, a), (0, a)], t + 8)        # two fences at 90 degrees
    blade = _prism([(0, 0), (D * 0.95, D * 0.95), (D * 0.95 - 14, D * 0.95), (0, 14)], t)   # its lower edge runs along the diagonal
    blade2 = _prism([(0, 0), (14, 0), (D * 0.95, D * 0.95 - 14), (D * 0.95, D * 0.95)], t)
    body += blade
    notes = [f"centre finder for rounds up to Ø{D:g} mm: two fences at 90° and a blade whose edge bisects them; {t:g} mm blade",
             "print it flat as it lies, blade down; scribe along the blade's straight inner edge"]
    del blade2
    return _out(body, notes, ["check it: scribe, turn the work a third of a turn and scribe again twice; three lines through one point means it's true"])


def setup_blocks(sizes="3, 6, 10, 12, 20", length=50.0, width=20.0):
    """A set of setup blocks: bars of exact heights for setting a blade's height, a fence's distance
    or a gap. Each has its size sunk into its top, and they print side by side."""
    try:
        hs = [float(x) for x in str(sizes).replace(";", ",").split(",") if x.strip()]
    except ValueError:
        raise ValueError("sizes: block heights in mm, with commas between (3, 6, 10)")
    if not 1 <= len(hs) <= 10 or any(not 1 <= v <= 60 for v in hs):
        raise ValueError("sizes: 1 to 10 blocks, each 1 to 60 mm")
    Ln, W = float(length), float(width)
    _rng("length", Ln, 25, 150); _rng("width", W, 10, 50)
    from build123d import Text
    body = None
    for i, hgt in enumerate(hs):
        b = Box(Ln, W, hgt, align=MIN_)
        try:
            txt = Text(f"{hgt:g}", min(W * 0.55, 10.0), align=(Align.CENTER, Align.CENTER))
            b -= Pos(0, 0, hgt - 0.5) * extrude(txt, amount=1.0)
        except Exception:
            pass
        b = Pos(0, i * (W + 4), 0) * b
        body = b if body is None else body + b
    notes = [f"{len(hs)} setup blocks, {Ln:g} x {W:g} mm: {', '.join(f'{v:g}' for v in hs)} mm tall, each marked on top",
             "print them flat as they lie; heights come out in whole layers, so pick multiples of your layer height, and measure each with calipers once"]
    return _out(body, notes, ["a printed block is good to about 0.1 mm: fine for woodwork, not for machining"])


# ---------- Funnels and hose adapters ----------

def funnel(top_d=90.0, neck_d=18.0, neck_length=35.0, height=0.0, wall=1.6, hang_tab=True):
    """A funnel to fit a neck: the top's width, the spout's outside diameter and length. A rib down
    the spout lets air out as you pour, and a tab at the rim hangs it up."""
    D, d, nl, w = float(top_d), float(neck_d), float(neck_length), float(wall)
    _rng("top", D, 30, 250); _rng("spout", d, 5, D - 12); _rng("spout length", nl, 5, 150); _rng("wall", w, 1.2, 4)
    cone_h = float(height) or round((D - d) / 2 * 1.1, 1)        # a little steeper than 45 degrees
    if cone_h < (D - d) / 2 * 0.95:
        raise ValueError(f"at least {(D - d) / 2:.0f} mm tall keeps the cone at 45° or steeper, so it prints without supports")
    # Printed rim down: the cone on the bed, the spout standing up.
    outer = Cone(D / 2, d / 2, cone_h, align=MIN_) + Pos(0, 0, cone_h - 0.01) * Cone(d / 2, d / 2 - 0.6, nl, align=MIN_)
    inner = Pos(0, 0, -0.01) * Cone(D / 2 - w, d / 2 - w, cone_h + 0.02, align=MIN_) + Pos(0, 0, cone_h - 0.02) * Cylinder(d / 2 - w - 0.3, nl + 1, align=MIN_)
    body = outer - inner
    body += Pos(d / 2 - 0.2, 0, cone_h + nl * 0.15) * Box(1.4, 1.6, nl * 0.7, align=(Align.MIN, Align.CENTER, Align.MIN))   # the air rib
    if hang_tab:
        tabb = Pos(D / 2 + 5, 0, 0) * Cylinder(8, 2.4, align=MIN_) + Pos(D / 2 - 1, 0, 0) * Box(8, 16, 2.4, align=(Align.MIN, Align.CENTER, Align.MIN))
        tabb -= Pos(D / 2 + 6, 0, -1) * Cylinder(3, 5, align=MIN_)
        body += tabb - Pos(0, 0, -1) * Cylinder(D / 2 - w, 5, align=MIN_)
    notes = [f"funnel Ø{D:g} mm at the top, a spout Ø{d:g} mm outside ({d - 2 * w - 0.6:g} mm bore) and {nl:g} mm long, {cone_h + nl:g} mm tall, "
             f"walls {w:g} mm, with an air rib on the spout" + (" and a hanging tab" if hang_tab else ""),
             "print it rim down as it stands, no supports; PETG for anything but water, and not for food unless your filament and nozzle are rated for it"]
    return _out(body, notes, [], {"bore": round(d - 2 * w - 0.6, 2)})


def hose_adapter(end_a=35.0, a_fits="inside the hose", end_b=58.0, b_fits="inside the hose", length_a=30.0, length_b=30.0, wall=2.0):
    """An adapter between two hose or port sizes (a shop vac to a tool, two dust hoses): each end
    either pushes inside a hose or slips over a port, with a slight taper so it wedges tight."""
    A, B, la, lb, w = float(end_a), float(end_b), float(length_a), float(length_b), float(wall)
    _rng("end A", A, 8, 200); _rng("end B", B, 8, 200); _rng("length A", la, 10, 100); _rng("length B", lb, 10, 100); _rng("wall", w, 1.4, 5)
    ways = ("inside the hose", "over the port")
    if a_fits not in ways or b_fits not in ways:
        raise ValueError(f"each end goes: {' or '.join(ways)}")
    tp = 0.4                                      # taper on the diameter over an end's length

    def radii(d, fits):                            # (outside at the mouth, outside at the root, inside at the mouth, inside at the root)
        if fits == ways[0]:                        # a plug: the outside is the size, a touch smaller at the mouth
            return (d - tp) / 2, (d + tp) / 2, (d - tp) / 2 - w, (d + tp) / 2 - w
        return (d + tp) / 2 + w, (d - tp) / 2 + w, (d + tp) / 2, (d - tp) / 2      # a socket: the inside is the size, wider at the mouth
    a_om, a_or, a_im, a_ir = radii(A, a_fits)
    b_om, b_or, b_im, b_ir = radii(B, b_fits)
    if min(a_im, a_ir, b_im, b_ir) < 2:
        raise ValueError("an end is too small for this wall: a thinner wall, or a bigger end")
    # The bigger end goes on the bed, so the middle narrows upward and needs no support.
    if max(b_om, b_or) > max(a_om, a_or):
        (A, la, a_om, a_or, a_im, a_ir, a_fits), (B, lb, b_om, b_or, b_im, b_ir, b_fits) = \
            (B, lb, b_om, b_or, b_im, b_ir, b_fits), (A, la, a_om, a_or, a_im, a_ir, a_fits)
    mid = max(6.0, abs(a_or - b_or) * 1.15, abs(a_ir - b_ir) * 1.15)
    z1, z2, z3 = la, la + mid, la + mid + lb
    outer = revolve(Plane.XZ * Polygon((0, 0), (a_om, 0), (a_or, z1), (b_or, z2), (b_om, z3), (0, z3), align=None), Axis.Z)
    inner = revolve(Plane.XZ * Polygon((0, -1), (a_im, -1), (a_im, 0), (a_ir, z1), (b_ir, z2), (b_im, z3), (b_im, z3 + 1), (0, z3 + 1), align=None), Axis.Z)
    body = outer - inner
    notes = [f"hose adapter: one end Ø{A:g} mm ({a_fits}), the other Ø{B:g} mm ({b_fits}), {z3:g} mm long, walls {w:g} mm, "
             f"each end tapered {tp:g} mm on its diameter to wedge", "print it big end down as it stands, no supports",
             "measure the hose or port with calipers: 'inside the hose' takes the hose's inside diameter, 'over the port' the port's outside"]
    return _out(body, notes, ["hose cuffs are rubbery and ports are tapered: if it's loose, add 0.5 mm and reprint the end"],
                {"length": round(z3, 1), "bore": round(2 * min(a_im, a_ir, b_im, b_ir), 2)})


# ---------- Panels for trainers and test gear ----------

def test_point_plate(labels="TP1|TP2|TP3|GND", hole_d=8.0, pitch=19.05, text_size=5.0, thickness=3.0, rows=1, mount_holes=True):
    """A labelled plate of jack or test-point holes: a row (or rows) of holes for banana jacks,
    binding posts, switches or LEDs, with a label engraved under each, and screw holes to fix it."""
    from build123d import Text
    names = [s.strip() for s in str(labels).replace("\n", "|").replace(",", "|").split("|") if s.strip()]
    if not 1 <= len(names) <= 40:
        raise ValueError("labels: 1 to 40, with | between them (TP1|TP2|GND)")
    d, p, ts, t, nr = float(hole_d), float(pitch), float(text_size), float(thickness), int(rows)
    _rng("hole", d, 2, 30); _rng("spacing", p, d + 3, 80); _rng("text", ts, 3, 12); _rng("thickness", t, 1.6, 6); _rng("rows", nr, 1, 6, "")
    per = math.ceil(len(names) / nr)
    row_h = d + ts + 9
    side = 12.0 if mount_holes else 6.0
    Ln, W = (per - 1) * p + d + 2 * side + 4, nr * row_h + 6
    body = extrude(RectangleRounded(Ln, W, 3.0), amount=t)
    k = 0
    for r in range(nr):
        yc = W / 2 - 3 - r * row_h - d / 2 - 3
        for c in range(per):
            if k >= len(names):
                break
            x = (c - (per - 1) / 2) * p
            body -= Pos(x, yc, -1) * Cylinder(d / 2, t + 2, align=MIN_)
            try:
                size = min(ts, (p - 1.5) / max(1, len(names[k])) * 1.5)
                body -= Pos(x, yc - d / 2 - 2.5 - ts / 2, t - 0.5) * extrude(Text(names[k], size, align=(Align.CENTER, Align.CENTER)), amount=1.0)
            except Exception:
                raise ValueError(f"the label '{names[k]}' has a character this font can't draw") from None
            k += 1
    if mount_holes:
        for sx in (-1, 1):
            for sy in ((-1, 1) if W > 30 else (0,)):
                body -= Pos(sx * (Ln / 2 - 5), sy * (W / 2 - 5), t) * _csk(3.6, 7.0, 20)
    notes = [f"test-point plate {Ln:.1f} x {W:.1f} x {t:g} mm: {len(names)} holes of Ø{d:g} mm, {p:g} mm apart"
             + (f" in {nr} rows" if nr > 1 else "") + f", each labelled underneath in {ts:g} mm engraved text"
             + (", countersunk Ø3.6 mm fixing holes" if mount_holes else ""),
             "print it flat, face up; fill the engraved text with paint or a wax crayon and wipe it off for contrast",
             "19.05 mm (3/4 in) is the standard spacing for a dual banana plug; check your jacks' panel hole before printing"]
    return _out(body, notes, [], {"size": [round(Ln, 1), round(W, 1)]})


def panel_bezel(opening_w=60.0, opening_h=30.0, flange=8.0, depth=6.0, panel=2.0, wall=1.6, screw_d=3.4):
    """A bezel for a rectangular cutout in a panel (a display, a meter, a switch bank): a frame that
    covers the cutout's edge, with a collar that drops into it and screw holes in the corners."""
    ow, oh, fl, dp, pn, w = float(opening_w), float(opening_h), float(flange), float(depth), float(panel), float(wall)
    _rng("opening width", ow, 8, 300); _rng("opening height", oh, 8, 300); _rng("flange", fl, 3, 30); _rng("collar depth", dp, 0, 40)
    _rng("wall", w, 1.2, 4)
    ft = 2.4
    body = extrude(RectangleRounded(ow + 2 * w + 2 * fl, oh + 2 * w + 2 * fl, min(4.0, fl * 0.6)), amount=ft)
    try:
        body = chamfer(body.edges().group_by(Axis.Z)[0], 0.8)
    except Exception:
        pass
    if dp > 0:
        body += Pos(0, 0, ft - 0.01) * extrude(Rectangle(ow + 2 * w - 0.3, oh + 2 * w - 0.3), amount=dp)
    body -= Pos(0, 0, -1) * extrude(Rectangle(ow, oh), amount=ft + dp + 2)
    if screw_d > 0:
        if fl < screw_d + 3:
            raise ValueError(f"a flange of {fl:g} mm has no room for Ø{screw_d:g} mm screws: {screw_d + 3:g} mm or more, or set the screw hole to 0")
        for sx in (-1, 1):
            for sy in (-1, 1):
                body -= Pos(sx * (ow / 2 + w + fl / 2), sy * (oh / 2 + w + fl / 2), -1) * Cylinder(screw_d / 2, ft + 2, align=MIN_)
    notes = [f"bezel for a {ow:g} x {oh:g} mm opening: a {fl:g} mm flange all round ({ow + 2 * w + 2 * fl:g} x {oh + 2 * w + 2 * fl:g} mm outside), "
             + (f"a collar {dp:g} mm deep that needs a {ow + 2 * w:g} x {oh + 2 * w:g} mm cutout" if dp > 0 else "no collar")
             + (f", Ø{screw_d:g} mm holes in the corners" if screw_d > 0 else ""), "print it face down as it stands"]
    return _out(body, notes, [], {"cutout": [round(ow + 2 * w, 2), round(oh + 2 * w, 2)]})


def terminal_cover(length=80.0, width=25.0, height=18.0, wall=2.0, wire_slot=8.0, screw_d=3.6):
    """A cover for a terminal strip or live terminals: a clear-span hood with open slots along both
    long sides for the wires, and a screw ear at each end. A guard against fingers, not a seal."""
    Ln, W, H, w, ws = float(length), float(width), float(height), float(wall), float(wire_slot)
    _rng("inside length", Ln, 15, 300); _rng("inside width", W, 8, 150); _rng("inside height", H, 5, 100); _rng("wall", w, 1.6, 4)
    _rng("wire slot height", ws, 0, H - 2)
    body = Box(Ln + 2 * w, W + 2 * w, H + w, align=MIN_)
    try:
        body = fillet(body.edges().filter_by(Axis.Z), min(3.0, w * 1.2))
    except Exception:
        pass
    # Printed top down: the hood's roof on the bed, its open side up.
    body -= Pos(0, 0, w) * Box(Ln, W, H + 1, align=MIN_)
    if ws > 0:
        body -= Pos(0, 0, w + H - ws) * Box(Ln - 2 * 4, W + 2 * w + 2, ws + 1, align=MIN_)       # wire slots along both sides, at the open edge
    ear = 2 * screw_d + 5
    for s in (-1, 1):
        e = Pos(s * (Ln / 2 + w + ear / 2 - 0.1), 0, w + H - 3.0) * Box(ear + 0.2, min(W + 2 * w, ear + 6), 3.0, align=MIN_)
        e -= Pos(s * (Ln / 2 + w + ear / 2), 0, w + H - 4) * Cylinder(screw_d / 2, 6, align=MIN_)
        # A 45 degree web under each ear so it prints without support.
        web = extrude(Plane.XZ * Polygon((s * (Ln / 2 + w - 0.1), w + H - 3.0), (s * (Ln / 2 + w + ear), w + H - 3.0), (s * (Ln / 2 + w - 0.1), w + H - 3.0 - ear),
                                         align=None), amount=min(W + 2 * w, ear + 6) / 2, both=True)
        web -= Pos(s * (Ln / 2 + w + ear / 2), 0, 0) * Cylinder(screw_d / 2 + 2.2, H + w + 5, align=MIN_)
        body += e + web
    notes = [f"terminal cover: inside {Ln:g} x {W:g} x {H:g} mm, walls {w:g} mm"
             + (f", wire slots {ws:g} mm tall along both long sides" if ws > 0 else ", closed sides")
             + f", a screw ear each end (Ø{screw_d:g} mm, {Ln + 2 * w + ear:.1f} mm apart)",
             "print it top down as it stands, no supports; clear PETG lets you see the terminals"]
    return _out(body, notes, ["this keeps fingers and dropped tools off the terminals; it is not an insulation rating. Use a listed cover where code asks for one"],
                {"ear_spacing": round(Ln + 2 * w + ear, 1)})


# ---------- What the page needs to know ----------

KINDS = {
    "bushing": (bushing, "Bushing or sleeve", {"od": 12.0, "bore": 6.0, "length": 10.0, "flange_d": 0.0, "flange_t": 2.0}),
    "flat_plate": (flat_plate, "Plate with holes", {"length": 80.0, "width": 50.0, "thickness": 3.0, "corner": 3.0, "holes": "corners", "hole_d": 4.5,
                                                     "inset": 8.0, "across": 2, "down": 2, "countersink": False, "centre_hole": 0.0}),
    "tool_clip": (tool_clip, "Spring clip for a round handle", {"grip_d": 25.0, "width": 15.0, "wall": 2.4, "screw_d": 4.5}),
    "slip_cap": (slip_cap, "Slip-on cap", {"shape": "round", "inner": 25.0, "inner2": 25.0, "depth": 20.0, "wall": 2.0, "top": 2.0, "fit": 0.2}),
    "edge_clip": (edge_clip, "Edge clip", {"panel": 3.0, "depth": 12.0, "length": 30.0, "wall": 1.8, "grip": 0.3}),
    "board_mount": (board_mount, "Circuit board mount", {"board": "Raspberry Pi 3, 4 or 5 (Model B)", "style": "standoffs", "standoff": 5.0,
                                                           "plate_holes": True, "board_l": 60.0, "board_w": 40.0, "hole_l": 52.0, "hole_w": 32.0,
                                                           "screw": "M3", "base": 2.4}),
    "extrusion_end_cap": (extrusion_end_cap, "T-slot end cap", {"profile": "1515 (80/20, 1.5 in)", "thickness": 3.0, "tab": 7.0}),
    "extrusion_bracket": (extrusion_bracket, "T-slot corner bracket", {"profile": "1515 (80/20, 1.5 in)", "leg": 0.0, "thickness": 6.0, "holes": 1}),
    "extrusion_cable_guide": (extrusion_cable_guide, "T-slot cable guide", {"profile": "1515 (80/20, 1.5 in)", "bundle_d": 15.0, "width": 12.0, "wall": 2.4}),
    "extrusion_panel_clip": (extrusion_panel_clip, "T-slot panel clip", {"profile": "1515 (80/20, 1.5 in)", "panel": 3.0, "width": 20.0, "reach": 12.0}),
    "extrusion_handle": (extrusion_handle, "T-slot handle", {"profile": "1515 (80/20, 1.5 in)", "span": 120.0, "clearance": 35.0, "width": 0.0, "grip": 14.0}),
    "extrusion_offset_jig": (extrusion_offset_jig, "T-slot drilling jig: holes from the end", {
        "profile": "1515 (80/20, 1.5 in)", "offsets": "", "hole": "bolt clearance", "drill_d": 0.0, "bushing_od": 0.0, "face": "narrow face",
        "top": 12.0, "wall": 4.0, "fit": 0.15}),
    "extrusion_freehand_jig": (extrusion_freehand_jig, "T-slot drilling jig: anywhere along", {
        "profile": "1515 (80/20, 1.5 in)", "holes": 1, "pitch": 0.0, "hole": "bolt clearance", "drill_d": 0.0, "bushing_od": 0.0,
        "face": "narrow face", "top": 12.0, "wall": 4.0, "fit": 0.15}),
    "extrusion_alignment_jig": (extrusion_alignment_jig, "T-slot alignment jig", {"profile": "1515 (80/20, 1.5 in)", "leg": 0.0, "thickness": 8.0, "key": 1.6}),
    "shelf_pin_jig": (shelf_pin_jig, "Shelf-pin drilling jig", {"holes": 6, "pitch": 32.0, "setback": 37.0, "hole_d": 5.0, "thickness": 8.0, "lip": True}),
    "clamp_square": (clamp_square, "Clamping square", {"leg": 100.0, "width": 25.0, "thickness": 10.0}),
    "centre_finder": (centre_finder, "Centre finder", {"max_d": 100.0, "thickness": 4.0}),
    "setup_blocks": (setup_blocks, "Setup blocks", {"sizes": "3, 6, 10, 12, 20", "length": 50.0, "width": 20.0}),
    "funnel": (funnel, "Funnel", {"top_d": 90.0, "neck_d": 18.0, "neck_length": 35.0, "height": 0.0, "wall": 1.6, "hang_tab": True}),
    "hose_adapter": (hose_adapter, "Hose or vacuum adapter", {"end_a": 35.0, "a_fits": "inside the hose", "end_b": 58.0, "b_fits": "inside the hose",
                                                                "length_a": 30.0, "length_b": 30.0, "wall": 2.0}),
    "test_point_plate": (test_point_plate, "Test-point or jack plate", {"labels": "TP1|TP2|TP3|GND", "hole_d": 8.0, "pitch": 19.05, "text_size": 5.0,
                                                                         "thickness": 3.0, "rows": 1, "mount_holes": True}),
    "panel_bezel": (panel_bezel, "Panel bezel", {"opening_w": 60.0, "opening_h": 30.0, "flange": 8.0, "depth": 6.0, "panel": 2.0, "wall": 1.6, "screw_d": 3.4}),
    "terminal_cover": (terminal_cover, "Terminal cover", {"length": 80.0, "width": 25.0, "height": 18.0, "wall": 2.0, "wire_slot": 8.0, "screw_d": 3.6}),
}
_SCREW = ("Screw hole (4.5 suits a #8 or 4 mm screw)", "len")
_PROFILE = ("Extrusion", "select")
KIND_LABELS = {
    **{(k, "profile"): _PROFILE for k in ("extrusion_end_cap", "extrusion_bracket", "extrusion_cable_guide", "extrusion_panel_clip", "extrusion_handle",
                                          "extrusion_offset_jig", "extrusion_freehand_jig", "extrusion_alignment_jig")},
    **{(k, f): lab for k in ("extrusion_offset_jig", "extrusion_freehand_jig") for f, lab in {
        "hole": ("Hole for", "select"), "drill_d": ("Drill size (0: from the choice above)", "len"),
        "bushing_od": ("Steel bushing outside diameter (0: plain printed hole)", "len"), "face": ("On the", "select"),
        "top": ("Guide depth (top thickness)", "len"), "fit": ("Fit (added each side)", "len")}.items()},
    ("extrusion_offset_jig", "offsets"): ("Distances from the end, mm (blank: half the extrusion)", "text"),
    ("extrusion_freehand_jig", "holes"): ("Holes in a row", "num"), ("extrusion_freehand_jig", "pitch"): ("Hole spacing (0: the extrusion's size)", "len"),
    ("extrusion_alignment_jig", "leg"): ("Leg length (0: to suit)", "len"), ("extrusion_alignment_jig", "key"): ("Slot key depth (0: none)", "len"),
    ("bushing", "od"): ("Outside diameter", "len"), ("bushing", "bore"): ("Bore (0: solid)", "len"),
    ("bushing", "flange_d"): ("Flange diameter (0: none)", "len"), ("bushing", "flange_t"): ("Flange thickness", "len"),
    ("flat_plate", "corner"): ("Corner radius", "len"), ("flat_plate", "holes"): ("Holes", "select"), ("flat_plate", "hole_d"): ("Hole diameter", "len"),
    ("flat_plate", "inset"): ("Holes in from the edge", "len"), ("flat_plate", "across"): ("Holes across (grid)", "num"),
    ("flat_plate", "down"): ("Holes down (grid)", "num"), ("flat_plate", "countersink"): ("Countersunk", "bool"),
    ("flat_plate", "centre_hole"): ("Hole in the middle (0: none)", "len"),
    ("tool_clip", "grip_d"): ("Handle diameter", "len"), ("tool_clip", "screw_d"): _SCREW,
    ("slip_cap", "shape"): ("Fits over a", "select"), ("slip_cap", "inner"): ("Its outside size (diameter or side)", "len"),
    ("slip_cap", "inner2"): ("Other side (rectangle only)", "len"), ("slip_cap", "depth"): ("How far it goes on", "len"),
    ("slip_cap", "top"): ("Top thickness", "len"), ("slip_cap", "fit"): ("Fit (added each side)", "len"),
    ("edge_clip", "panel"): ("Panel thickness", "len"), ("edge_clip", "depth"): ("How far it goes on", "len"), ("edge_clip", "grip"): ("Grip (lean of each jaw)", "len"),
    ("board_mount", "board"): ("Board", "select"), ("board_mount", "style"): ("Mount", "select"), ("board_mount", "standoff"): ("Height under the board", "len"),
    ("board_mount", "plate_holes"): ("Fixing holes in the plate", "bool"), ("board_mount", "board_l"): ("Your board: length", "len"),
    ("board_mount", "board_w"): ("Your board: width", "len"), ("board_mount", "hole_l"): ("Your board: holes apart, lengthways", "len"),
    ("board_mount", "hole_w"): ("Your board: holes apart, across", "len"), ("board_mount", "screw"): ("Your board: screw", "select"),
    ("board_mount", "base"): ("Base thickness", "len"),
    ("extrusion_end_cap", "tab"): ("Tab length into the slot", "len"),
    ("extrusion_bracket", "leg"): ("Leg length (0: to suit)", "len"), ("extrusion_bracket", "thickness"): ("Thickness under the bolts", "len"),
    ("extrusion_bracket", "holes"): ("Bolts on each leg", "select"),
    ("extrusion_cable_guide", "bundle_d"): ("Cable bundle diameter", "len"),
    ("extrusion_panel_clip", "panel"): ("Panel thickness", "len"), ("extrusion_panel_clip", "reach"): ("Reach over the panel", "len"),
    ("extrusion_handle", "span"): ("Bolt holes apart", "len"), ("extrusion_handle", "clearance"): ("Room for a hand", "len"),
    ("extrusion_handle", "width"): ("Width (0: to suit)", "len"), ("extrusion_handle", "grip"): ("Grip thickness", "len"),
    ("shelf_pin_jig", "holes"): ("Guide holes", "num"), ("shelf_pin_jig", "pitch"): ("Hole spacing (32 is the cabinet standard)", "len"),
    ("shelf_pin_jig", "setback"): ("From the board's edge (37 is standard)", "len"), ("shelf_pin_jig", "hole_d"): ("Drill size", "len"),
    ("shelf_pin_jig", "lip"): ("Lip that hooks the edge", "bool"),
    ("clamp_square", "leg"): ("Leg length", "len"),
    ("centre_finder", "max_d"): ("Largest diameter", "len"),
    ("setup_blocks", "sizes"): ("Heights, mm (commas between)", "text"),
    ("funnel", "top_d"): ("Top diameter", "len"), ("funnel", "neck_d"): ("Spout outside diameter", "len"), ("funnel", "neck_length"): ("Spout length", "len"),
    ("funnel", "height"): ("Cone height (0: just over 45°)", "len"), ("funnel", "hang_tab"): ("Hanging tab", "bool"),
    ("hose_adapter", "end_a"): ("End A diameter", "len"), ("hose_adapter", "a_fits"): ("End A goes", "select"),
    ("hose_adapter", "end_b"): ("End B diameter", "len"), ("hose_adapter", "b_fits"): ("End B goes", "select"),
    ("hose_adapter", "length_a"): ("End A length", "len"), ("hose_adapter", "length_b"): ("End B length", "len"),
    ("test_point_plate", "labels"): ("Labels (put | between them)", "text"), ("test_point_plate", "hole_d"): ("Hole diameter", "len"),
    ("test_point_plate", "pitch"): ("Hole spacing (19.05: dual banana)", "len"), ("test_point_plate", "text_size"): ("Text height", "len"),
    ("test_point_plate", "rows"): ("Rows", "num"), ("test_point_plate", "mount_holes"): ("Fixing holes", "bool"),
    ("panel_bezel", "opening_w"): ("Window width", "len"), ("panel_bezel", "opening_h"): ("Window height", "len"),
    ("panel_bezel", "flange"): ("Flange all round", "len"), ("panel_bezel", "depth"): ("Collar depth into the panel (0: none)", "len"),
    ("panel_bezel", "panel"): ("Panel thickness", "len"), ("panel_bezel", "screw_d"): ("Corner screw holes (0: none)", "len"),
    ("terminal_cover", "length"): ("Inside length", "len"), ("terminal_cover", "width"): ("Inside width", "len"),
    ("terminal_cover", "height"): ("Inside height", "len"), ("terminal_cover", "wire_slot"): ("Wire slot height (0: closed)", "len"),
    ("terminal_cover", "screw_d"): ("Screw hole", "len"),
}
_WAYS = ["inside the hose", "over the port"]
CHOICES = {
    **{(k, "profile"): list(PROFILES) for k in ("extrusion_end_cap", "extrusion_bracket", "extrusion_cable_guide", "extrusion_panel_clip", "extrusion_handle",
                                                  "extrusion_offset_jig", "extrusion_freehand_jig", "extrusion_alignment_jig")},
    **{(k, "hole"): list(JIG_HOLES) for k in ("extrusion_offset_jig", "extrusion_freehand_jig")},
    **{(k, "face"): ["narrow face", "wide face"] for k in ("extrusion_offset_jig", "extrusion_freehand_jig")},
    ("flat_plate", "holes"): ["corners", "grid", "none"], ("slip_cap", "shape"): ["round", "square", "rectangle"],
    ("board_mount", "board"): list(BOARDS), ("board_mount", "style"): ["standoffs", "corner tray"], ("board_mount", "screw"): list(PILOT),
    ("extrusion_bracket", "holes"): [1, 2], ("hose_adapter", "a_fits"): _WAYS, ("hose_adapter", "b_fits"): _WAYS,
}
GROUPS = {
    "Measure and replace": ["bushing", "flat_plate", "slip_cap", "edge_clip", "tool_clip"],
    "Circuit boards": ["board_mount"],
    "T-slot extrusion": ["extrusion_offset_jig", "extrusion_freehand_jig", "extrusion_alignment_jig", "extrusion_end_cap", "extrusion_bracket",
                         "extrusion_cable_guide", "extrusion_panel_clip", "extrusion_handle"],
    "Jigs": ["shelf_pin_jig", "clamp_square", "centre_finder", "setup_blocks"],
    "Funnels and hoses": ["funnel", "hose_adapter"],
    "Panels and trainers": ["test_point_plate", "panel_bezel", "terminal_cover"],
}
WORDS = {
    "bushing": "spacer sleeve collar washer round replace broken", "flat_plate": "cover patch adapter mounting plate blank", "tool_clip": "broom clip terry clip holder torch",
    "slip_cap": "chair leg cap ferrule post cap pipe cap cover", "edge_clip": "u clip shelf clip trim channel", "board_mount": "raspberry pi arduino esp32 pico pcb standoff tray",
    "extrusion_offset_jig": "8020 80/20 1515 2020 aluminium aluminum drill jig blind joint access hole end", "extrusion_freehand_jig": "8020 80/20 1515 2020 aluminium aluminum drill jig blind joint access hole",
    "extrusion_alignment_jig": "8020 80/20 1515 2020 aluminium aluminum square perpendicular jig",
    "extrusion_end_cap": "8020 80/20 1515 2020 aluminium aluminum profile cap", "extrusion_bracket": "8020 80/20 1515 2020 gusset angle corner",
    "extrusion_cable_guide": "8020 80/20 cable clip wire hook", "extrusion_panel_clip": "8020 80/20 acrylic panel holder", "extrusion_handle": "8020 80/20 cart pull grab",
    "shelf_pin_jig": "cabinet drilling 32 mm system", "clamp_square": "corner clamp square assembly woodworking", "centre_finder": "center finder round stock",
    "setup_blocks": "gauge blocks height spacer", "funnel": "pour spout", "hose_adapter": "shop vac vacuum dust collection reducer coupler",
    "test_point_plate": "banana jack binding post panel trainer", "panel_bezel": "display frame meter trim", "terminal_cover": "terminal block guard shield barrier strip",
}
