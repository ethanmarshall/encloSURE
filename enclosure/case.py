"""A hinged case with snap-on latch tabs, the kind sold as a parts organiser: a tray, a lid that snaps
onto ball-and-socket hinges along the back, and separate closure tabs that pivot on the lid and click
onto the tray at the front. Nothing to buy: every joint is a printed ball in a printed socket.

How it goes together (z up, the front at -Y, the hinges at +Y):

- The tray's wall has a shoulder with a lip inside it; the lid's wall sits on the shoulder and has a
  rebate that drops over the lip, so the lid locates and dust stays out.
- Each hinge is a pair of cheeks on the tray with sockets facing each other, and a lug on the lid with
  a ball each side that snaps between them. The axis is at the parting line, outside the wall, so the
  lid opens right over to lie flat.
- Each latch is a pair of cheeks on the lid with sockets, a tab that snaps between them on two balls
  and swings, and a pair of posts on the tray below. The tab's lower balls are on thin sprung arms and
  click into sockets in the posts; they sit a little high of the sockets so the lid is pulled down.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from build123d import Align, Box, Cylinder, Polygon, Plane, Pos, Rot, RectangleRounded, Sphere, chamfer, extrude, Axis

LIP_H = 2.4        # the lip stands this far above the shoulder
LIP_GAP = 0.25     # between the lip and the lid's rebate, each side
CHEEK_W = 6.4      # every cheek and post is this wide
SIDE = 0.3         # sideways clearance between a lug or tab and its cheeks, each side
HINGE_E = 4.4      # the hinge axis is this far outside the wall
HINGE_R = 4.2      # radius of the hinge's round ends
HINGE_GAP = 13.2   # between a hinge's two cheeks
HINGE_BALL = (4.5, 1.2)   # (sphere radius, how far it stands out of the lug)
TAB_W = 25.0       # the latch tab's width
TAB_T = 6.0        # and thickness
TAB_E = 3.4        # the tab's pivot is this far outside the wall, and below the lid's top
POST_D = 8.0       # how far the latch's cheeks and posts stand out of the wall
PIVOT_BALL = (5.0, 1.1)
CATCH_BALL = (7.0, 0.8)
SOCKET_EXTRA = 0.15       # a socket's radius over its ball's
CATCH_MIN = 13.0   # pivot to catch, at least
TAIL = 10.0        # the tab runs this far past the catch (the sprung arms' roots and the finger lip)
PRELOAD = 0.45     # the catch sockets sit this far low, so the latch pulls the lid down
RIB = 1.2          # dividers and lid ribs


@dataclass
class Case:
    size: tuple = (160.0, 100.0, 30.0)  # inside length (X), width (Y) and height, floor to the lid's underside
    lid_depth: float = 6.0     # how much of the inside height is in the lid
    wall: float = 3.2
    floor: float = 2.4         # the tray's floor and the lid's top
    corner_radius: float = 3.0
    hinges: int = 0            # 0 picks by length
    latches: int = 0           # 0 picks by length
    dividers_x: int = 0        # walls across the tray, splitting its length
    dividers_y: int = 0        # walls along the tray, splitting its width
    lid_ribs: bool = True      # ribs under the lid over the dividers, so small parts stay in their pockets

    def check(self) -> None:
        L, W, H = self.size
        if not (45 <= L <= 400 and 30 <= W <= 400):
            raise ValueError("case: inside length 45 to 400 mm, width 30 to 400 mm")
        if not 2.4 <= self.wall <= 6:
            raise ValueError("case wall: 2.4 to 6 mm (it carries a lip and a rebate)")
        if not 1.2 <= self.floor <= 6:
            raise ValueError("case floor: 1.2 to 6 mm")
        if self.lid_depth < LIP_H + 0.6:
            raise ValueError(f"the lid's depth must be at least {LIP_H + 0.6:g} mm (it drops over a {LIP_H:g} mm lip)")
        if self.lid_depth > H - 6:
            raise ValueError("the lid's depth takes nearly all the inside height: leave the tray at least 6 mm")
        for n, what in ((self.hinges, "hinges"), (self.latches, "latches")):
            if not 0 <= int(n) <= 6:
                raise ValueError(f"{what}: 0 (automatic) to 6")
        if not (0 <= int(self.dividers_x) <= 12 and 0 <= int(self.dividers_y) <= 12):
            raise ValueError("dividers: 0 to 12 each way")


def _spread(n: int, span: float, unit: float, margin: float) -> list[float]:
    """Centres for n units `unit` wide across `span`, the outer ones `margin` in from the ends."""
    if n == 1:
        return [0.0]
    end = span / 2 - margin - unit / 2
    return [-end + 2 * end * i / (n - 1) for i in range(n)]


def _prism_yz(points, x0: float, x1: float):
    """A solid from a (y, z) outline, between x0 and x1."""
    return Pos(x0, 0, 0) * extrude(Plane.YZ * Polygon(*points, align=None), amount=x1 - x0, dir=(1, 0, 0))


def _block(sign: int, yw: float, depth: float, z0: float, z1: float, c: float, x0: float, x1: float, at: str):
    """A cheek or post standing `depth` out of the wall at y = sign * yw, from z0 to z1, rooted 0.2 mm inside
    the wall, with the box's own chamfer `c` on its outer edge at the bottom or the top."""
    yi, yo = yw - 0.2, yw + depth   # its root follows the chamfer, 0.2 mm inside the wall's face
    if at == "bottom":
        pts = [(yi - c, z0), (yo - c, z0), (yo, z0 + c), (yo, z1), (yi, z1), (yi, z0 + c)]
    else:
        pts = [(yi, z0), (yo, z0), (yo, z1 - c), (yo - c, z1), (yi - c, z1), (yi, z1 - c)]
    return _prism_yz([(sign * y, z) for y, z in pts], x0, x1)


def _ball(R: float):
    """A sphere with its seam turned to the side, away from the faces the balls and sockets are cut on."""
    return Rot(0, 0, 90) * Sphere(R)


def _cap(x_face: float, out: int, y: float, z: float, ball):
    """A ball standing out of a face at x = x_face (out = +1 or -1 is the way it points)."""
    R, p = ball
    s = Pos(x_face - out * (R - p), y, z) * _ball(R)
    keep = Pos(x_face + out * R, y, z) * Box(2 * R, 4 * R, 4 * R)
    return s & keep


def _socket(x_face: float, into: int, y: float, z: float, ball):
    """The hollow for that ball, in a face at x = x_face that is SIDE away from the ball's own face
    (into = +1 or -1 is the way it goes in)."""
    R, p = ball
    # The ball's face is SIDE back from this one; its sphere's centre is R - p behind that.
    return Pos(x_face - into * (SIDE + R - p), y, z) * _ball(R + SOCKET_EXTRA)


def tab(catch: float = CATCH_MIN):
    """A latch tab lying flat, as it prints: its outside face on z = 0, the pivot along X through
    (y = 0, z = TAB_T / 2), its length along +Y to the free end."""
    hw, t = TAB_W / 2, TAB_T
    end = catch + TAIL
    body = Pos(0, end / 2, 0) * Box(TAB_W, end, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body += Pos(0, 0, t / 2) * Cylinder(t / 2, TAB_W, rotation=(0, 90, 0))  # the round nose it turns on
    # The arch between the two pivot lobes, so they can spring in.
    arch = extrude(RectangleRounded(16.0, 20.0, 3.5), amount=t * 3)
    body -= Pos(0, 3.7 - 10.0, -t) * arch
    # A notch each side makes a neck for each lobe to bend at.
    for s in (-1, 1):
        notch = extrude(Polygon((s * (hw + 0.1), 3.7), (s * (hw - 3.0), 6.7), (s * (hw + 0.1), 9.7), align=None), amount=t * 3)
        body -= Pos(0, 0, -t) * notch
    # The sprung arms that carry the catch balls: rooted near the free end, free toward the pivot.
    arm_w, slot = 2.4, 1.0
    free, root = catch - 2.6, catch + TAIL - 2.5
    for s in (-1, 1):
        x_in = hw - arm_w - slot
        body -= Pos(s * (x_in + slot / 2), (free - slot + root) / 2, -t) * Box(slot, root - free + slot, t * 3,
                                                                              align=(Align.CENTER, Align.CENTER, Align.MIN))
        body -= Pos(s * (x_in + slot / 2), root, -t) * Cylinder(slot / 2, t * 3, align=(Align.CENTER, Align.CENTER, Align.MIN))
        body -= Pos(s * (x_in + (arm_w + slot + 0.2) / 2), free - slot / 2, -t) * Box(arm_w + slot + 0.2, slot, t * 3,
                                                                                    align=(Align.CENTER, Align.CENTER, Align.MIN))
    # The finger lip: the wall side of the free end slopes away so a fingertip gets behind it.
    body -= _prism_yz([(end - 5.0, t + 0.1), (end + 0.1, t + 0.1), (end + 0.1, 1.2)], -TAB_W, TAB_W)
    # The balls, trimmed to the tab's thickness.
    slab = Pos(0, 0, t / 2) * Box(TAB_W + 10, 400, t)
    for s in (-1, 1):
        body += _cap(s * hw, s, 0.0, t / 2, PIVOT_BALL) & slab
        body += _cap(s * hw, s, catch, t / 2, CATCH_BALL) & slab
    return body.clean()


def build(c: Case) -> dict:
    c.check()
    L, W, H = (float(v) for v in c.size)
    w, fl = float(c.wall), float(c.floor)
    oL, oW = L + 2 * w, W + 2 * w
    r = max(0.6, min(float(c.corner_radius), min(oL, oW) / 2 - 1))
    ch = max(0.4, min(2.0, w - 0.8, fl - 0.4))   # the chamfer on the bottom and top edges
    shoulder = max(1.05, 0.4 * w)                 # the step the lid's wall sits on
    lip_t = w - shoulder
    Hs = fl + H - c.lid_depth                     # the shoulder's height: the parting line
    T = fl + c.lid_depth                          # the lid, top to rim
    top = Hs + T
    yw = oW / 2
    notes, checks = [], []

    def rect(dl: float, dr: float):
        return RectangleRounded(L + 2 * dl, W + 2 * dl, max(0.5, r - dr))

    # ----- The tray -----
    tray = extrude(rect(w, 0), amount=Hs)
    tray = chamfer(tray.edges().group_by(Axis.Z)[0], ch)
    lip = Pos(0, 0, Hs - 0.01) * extrude(rect(lip_t, shoulder), amount=LIP_H + 0.01)
    lip = chamfer(lip.edges().group_by(Axis.Z)[-1], min(0.6, lip_t * 0.4))
    tray += lip
    tray -= Pos(0, 0, fl) * extrude(rect(0, w), amount=H + 10)

    # ----- The lid, where it sits when shut -----
    lid = Pos(0, 0, Hs) * extrude(rect(w, 0), amount=T)
    lid = chamfer(lid.edges().group_by(Axis.Z)[-1], ch)
    lid -= Pos(0, 0, Hs - 0.01) * extrude(rect(0, w), amount=c.lid_depth + 0.01)
    lid -= Pos(0, 0, Hs - 0.01) * extrude(rect(lip_t + LIP_GAP, shoulder - LIP_GAP), amount=LIP_H + 0.35)

    # ----- Dividers, and ribs under the lid over them -----
    nx, ny = int(c.dividers_x), int(c.dividers_y)
    div_top = Hs + LIP_H - 0.5
    rib_h = c.lid_depth - LIP_H - 0.3
    for k in range(1, nx + 1):
        x = -L / 2 + k * L / (nx + 1)
        tray += Pos(x, 0, fl - 0.01) * Box(RIB, W + 0.02, div_top - fl, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if c.lid_ribs and rib_h >= 1:
            lid += Pos(x, 0, top - fl - rib_h) * Box(RIB, W + 0.02, rib_h + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for k in range(1, ny + 1):
        y = -W / 2 + k * W / (ny + 1)
        tray += Pos(0, y, fl - 0.01) * Box(L + 0.02, RIB, div_top - fl, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if c.lid_ribs and rib_h >= 1:
            lid += Pos(0, y, top - fl - rib_h) * Box(L + 0.02, RIB, rib_h + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    if nx or ny:
        notes.append(f"{(nx + 1) * (ny + 1)} pockets, each about {(L - nx * RIB) / (nx + 1):.1f} x {(W - ny * RIB) / (ny + 1):.1f} mm; "
                     f"dividers {RIB:g} mm" + (f", ribs under the lid {rib_h:.1f} mm deep over them" if c.lid_ribs and rib_h >= 1 else ""))

    margin = max(6.0, r)
    # ----- Hinges along the back -----
    h_unit = HINGE_GAP + 2 * CHEEK_W
    room_h = int((oL - 2 * margin + 4) // (h_unit + 4))
    n_h = int(c.hinges) or (2 if oL < 120 else 3 if oL < 280 else 4)
    if n_h > room_h:
        if c.hinges:
            raise ValueError(f"{n_h} hinges don't fit along {oL:g} mm: {room_h} at most")
        n_h = room_h
    if n_h < 1:
        raise ValueError("the case is too short for a hinge")
    ya = yw + HINGE_E            # the hinge axis
    lug_w = HINGE_GAP - 2 * SIDE
    # The cheeks spring apart to let the balls in: short cheeks are stiff, so they get a shallower ball
    # (about 2% strain at the cheek's root).
    grab = max(0.45, min(HINGE_BALL[1] - SIDE, Hs * Hs / 480.0))
    hinge_ball = (HINGE_BALL[0], round(grab + SIDE, 2))
    for xc in _spread(n_h, oL, h_unit, margin):
        for s in (-1, 1):
            x_in = xc + s * HINGE_GAP / 2          # the cheek's inner face
            x0, x1 = sorted((x_in, x_in + s * CHEEK_W))
            cheek = _block(1, yw, HINGE_E + HINGE_R, 0.0, Hs, ch, x0, x1, "bottom")
            cheek += Pos((x0 + x1) / 2, ya, Hs) * Cylinder(HINGE_R, CHEEK_W, rotation=(0, 90, 0))
            cheek -= _socket(x_in, s, ya, Hs, hinge_ball)
            tray += cheek
        lug = _block(1, yw, HINGE_E + HINGE_R, Hs, top, ch, xc - lug_w / 2, xc + lug_w / 2, "top")
        lug += Pos(xc, ya, Hs) * Cylinder(HINGE_R, lug_w, rotation=(0, 90, 0))
        for s in (-1, 1):
            lug += _cap(xc + s * lug_w / 2, s, ya, Hs, hinge_ball) & (Pos(xc, ya, Hs) * Cylinder(HINGE_R, lug_w + 10, rotation=(0, 90, 0)))
        lid += lug
    notes.append(f"{n_h} snap hinges along the back: a lug on the lid with a ball each side ({grab:.2g} mm into "
                 f"its socket) between two cheeks on the tray; the lid opens right over")

    # ----- Latches along the front -----
    l_unit = TAB_W + 2 * SIDE + 2 * CHEEK_W
    room_l = int((oL - 2 * margin + 4) // (l_unit + 4))
    n_l = int(c.latches) or (1 if oL < 100 else 2 if oL < 280 else 3)
    if n_l > room_l:
        if c.latches:
            raise ValueError(f"{n_l} latches don't fit along {oL:g} mm: {room_l} at most")
        n_l = room_l
    if n_l < 1:
        raise ValueError(f"the case is too short for a latch: at least {l_unit + 2 * margin - 2 * w:.0f} mm inside")
    if T < 2 * TAB_E + 0.4:
        raise ValueError(f"the lid is too shallow for the latch's pivot: a lid depth of at least {2 * TAB_E + 0.4 - fl:.1f} mm")
    zp = top - TAB_E                         # the tab's pivot
    catch = max(CATCH_MIN, T - TAB_E + 4.5)  # pivot to catch: the catch must be well under the parting line
    need = catch + TAIL - (T - TAB_E) + 1.5  # the tray's height the tab hangs down over
    if Hs < need:
        raise ValueError(f"the tray is too shallow for the latch tab: it needs {need:.1f} mm from the floor's underside to "
                         f"the parting line and has {Hs:.1f} mm. Make the inside {need - Hs:.1f} mm taller")
    yp = -(yw + TAB_E)
    gap = TAB_W + 2 * SIDE
    one = tab(catch)
    mounted = []
    for xc in _spread(n_l, oL, l_unit, margin):
        for s in (-1, 1):
            x_in = xc + s * gap / 2
            x0, x1 = sorted((x_in, x_in + s * CHEEK_W))
            cheek = _block(-1, yw, POST_D, Hs, top, ch, x0, x1, "top")
            cheek -= _socket(x_in, s, yp, zp, PIVOT_BALL)
            lid += cheek
            post = _block(-1, yw, POST_D, 0.0, Hs, ch, x0, x1, "bottom")
            post -= _socket(x_in, s, yp, zp - catch - PRELOAD, CATCH_BALL)
            tray += post
        mounted.append(Pos(xc, -(yw + TAB_E + TAB_T / 2), zp) * (Rot(-90, 0, 0) * one))
    notes.append(f"{n_l} latch tab{'s' if n_l > 1 else ''} {TAB_W:g} x {catch + TAIL + TAB_T / 2:g} x {TAB_T:g} mm: each snaps "
                 f"between two cheeks on the lid and clicks onto two posts on the tray ({CATCH_BALL[1] - SIDE:g} mm catch on "
                 f"sprung arms, set {PRELOAD:g} mm tight so it pulls the lid down)")

    out_h = top
    notes.insert(0, f"hinged case: inside {L:g} x {W:g} x {H:g} mm ({H - c.lid_depth:g} in the tray to the parting line, "
                    f"{c.lid_depth:g} in the lid), outside {oL:g} x {oW + HINGE_E + HINGE_R + POST_D:.1f} x {out_h:g} mm with "
                    f"the hinges and latches; walls {w:g} mm, a {LIP_H:g} mm lip inside the lid's rim")
    notes.append("print the tray as it stands, the lid top down, the tabs flat on their outside face: no supports. "
                 "PETG is kinder to the snap joints than PLA")
    notes.append("to put it together: press each tab's rounded end between its two cheeks on the lid until both balls click "
                 "in, then press the lid's lugs down between the hinge cheeks, one hinge at a time")
    if Hs < 20:
        checks.append("a shallow tray makes short, stiff hinge cheeks: the lid will be hard to snap on. Print in PETG, or "
                      "make the tray deeper")
    checks.append("the snap joints are modelled on a printed case that works, but this one hasn't been printed: print one "
                  "tab and try it on the lid before printing a set")
    return {"base": tray.clean(), "lid": lid.clean(), "tab": one, "tabs": mounted, "n_tabs": n_l, "n_hinges": n_h, "notes": notes,
            "checks": checks, "inner": [L, W, H], "outer": [round(oL, 2), round(oW + HINGE_E + HINGE_R + POST_D, 2), round(out_h, 2)],
            "parting": Hs, "top": top}


def write(c: Case, folder) -> dict:
    from build123d import export_step, export_stl
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    m = build(c)
    export_step(m["base"], str(folder / "case_tray.step"))
    export_step(m["lid"], str(folder / "case_lid.step"))
    export_step(m["tab"], str(folder / "case_latch_tab.step"))
    export_stl(m["base"], str(folder / "case_tray.stl"))
    export_stl(Pos(0, 0, m["top"]) * (Rot(180, 0, 0) * m["lid"]), str(folder / "case_lid.stl"))  # top down, on the bed
    export_stl(m["tab"], str(folder / "case_latch_tab.stl"))
    from build123d import Compound
    export_step(Compound(children=[m["base"], m["lid"], *m["tabs"]]), str(folder / "case_assembly.step"))
    text = "# Hinged case\n\n" + "\n".join(f"- {n}" for n in m["notes"]) + \
           f"\n\nPrint {m['n_tabs']} of case_latch_tab.stl.\n\n## Check\n\n" + "\n".join(f"- {n}" for n in m["checks"]) + "\n"
    (folder / "notes.md").write_text(text, encoding="utf-8")
    return m
