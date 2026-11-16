"""Things you turn or that turn: handwheels, wheels with soft tyres for radio-controlled cars and
robots, and replacement knobs for appliances. Same form as useful.py: built the way it prints,
{shape, notes, checks, info, buy} back, with `fitted` for a part shown in place but not in the files.
"""

from __future__ import annotations

import math

from build123d import (Align, Axis, Box, Compound, Cylinder, Plane, Polygon, Pos, RectangleRounded, RegularPolygon, Rot,
                       chamfer, extrude, fillet, revolve)

from . import sizes
from .useful import MIN_, _out, _rng

# Holes a set screw cuts its own thread in (a little over tap size, for printed plastic).
SET_SCREWS = {"none": 0.0, "M3": 2.7, "M4": 3.6, "M5": 4.5, "M6": 5.3}
SHAFTS = ("round", "D (one flat)", "double D (two flats)", "hex", "square")


def _shaft_tool(shaft: str, d: float, flat: float, height: float):
    """The hole for a shaft, standing on z = 0. A D's flat faces +Y. `flat` is the caliper reading
    across the flat (a D: flat to the round side opposite; a double D: flat to flat); 0 takes 3/4 of d."""
    if shaft == "round":
        return Cylinder(d / 2, height, align=MIN_)
    if shaft == "hex":
        return extrude(RegularPolygon(d / 2, 6, major_radius=False), amount=height, dir=(0, 0, 1))
    if shaft == "square":
        return Box(d, d, height, align=MIN_)
    f = flat or round(d * 0.75, 2)
    if not d * 0.5 <= f < d:
        raise ValueError(f"across the flat: between {d * 0.5:g} and {d:g} mm for a {d:g} mm shaft (0 takes three quarters of it)")
    tool = Cylinder(d / 2, height, align=MIN_)
    if shaft == "D (one flat)":
        return tool - Pos(0, f - d / 2, -1) * Box(2 * d, d, height + 2, align=(Align.CENTER, Align.MIN, Align.MIN))
    if shaft == "double D (two flats)":
        return tool & Box(2 * d, f, height, align=MIN_)
    raise ValueError(f"shaft: one of {', '.join(SHAFTS)}")


def _shaft_say(shaft: str, d: float, flat: float, say: str) -> str:
    if shaft in ("D (one flat)", "double D (two flats)"):
        return f"a {say} {shaft.split(' (')[0]} shaft, {flat or round(d * 0.75, 2):g} mm across the flat{'s' if shaft.startswith('double') else ''}"
    return f"a {say} {shaft} shaft" + (" (across the flats)" if shaft in ("hex", "square") else "")


# ---------- Handwheel ----------

HANDLES = ("none", "printed post", "hole for a bolt-on handle")


def handwheel(diameter=100.0, rim=12.0, spokes=3, shaft="round", bore_d=8.0, flat=0.0, hub_length=20.0, hub_d=0.0, set_screw="M4",
              handle="none", fit=0.15):
    """A handwheel for a machine, a valve or a jig: a rounded rim to grip, spokes or a solid web, and
    a bore for a round, D, hex or square shaft. With a hub that stands up for a set screw, or flush
    with no hub at all to press or bolt on."""
    D, rm, n, f = float(diameter), float(rim), int(spokes), float(fit)
    d, d_say = sizes.parse(bore_d, "bore")
    fl, _ = sizes.parse(flat, "across the flat")
    hl, hd_ = float(hub_length), float(hub_d)
    _rng("diameter", D, 40, 300); _rng("rim", rm, 6, 30); _rng("spokes", n, 0, 8, ""); _rng("bore", d, 3, 40); _rng("fit", f, 0, 0.5)
    if rm > D / 5:
        raise ValueError(f"rim: up to {D / 5:g} mm on a {D:g} mm wheel")
    if set_screw not in SET_SCREWS:
        raise ValueError(f"set screw: one of {', '.join(SET_SCREWS)}")
    if handle not in HANDLES:
        raise ValueError(f"handle: one of {', '.join(HANDLES)}")
    across = d * (1.16 if shaft == "hex" else 1.42 if shaft == "square" else 1.0)        # the hole's widest reach
    hub_od = hd_ or max(across + 10, d * 1.9, 18.0)
    if hub_od < across + 5 or hub_od > D - 2 * rm - 6:
        raise ValueError(f"hub diameter: {across + 5:.1f} to {D - 2 * rm - 6:.1f} mm here (0 picks one)")
    if hl and hl < rm:
        raise ValueError(f"hub length: 0 for none, or {rm:g} mm (the rim's height) and up")
    _rng("hub length", hl, 0, 80)
    total = hl or rm
    web_t = round(rm * 0.6, 2)
    # The rim: a rounded section with a flat to print on.
    ring = revolve(Plane.XZ * Pos(D / 2 - rm / 2, rm / 2) * RectangleRounded(rm, rm, rm * 0.32), axis=Axis.Z)
    body = ring + Cylinder(hub_od / 2, total, align=MIN_)
    inner = D / 2 - rm + 0.6
    if n == 0:
        body += Cylinder(inner, web_t, align=MIN_)
    else:
        sw = max(7.0, min(D * 0.1, hub_od * 0.8))
        for i in range(n):
            body += Rot(0, 0, 360 * i / n) * Pos(inner / 2, 0, 0) * Box(inner, sw, web_t, align=MIN_)
    try:
        body = chamfer(body.edges().filter_by(lambda e: abs(e.center().Z - total) < 1e-6 and abs(e.length - math.pi * hub_od) < 1e-3), 1.0)
    except Exception:
        pass
    body -= Pos(0, 0, -1) * _shaft_tool(shaft, d + 2 * f, fl + 2 * f if fl else 0.0, total + 2)
    notes = [f"handwheel Ø{D:g} mm with a {rm:g} mm rim, " + (f"{n} spokes" if n else "a solid web") + f", for {_shaft_say(shaft, d, fl, d_say)}"
             + (f"; the hub is Ø{hub_od:g} x {total:g} mm" if hl else f"; no hub: the centre is Ø{hub_od:g} mm, flush with the rim")]
    checks = []
    tap = SET_SCREWS[set_screw]
    if tap:
        if hl < web_t + tap + 4:
            raise ValueError(f"a set screw needs a hub that stands up: a hub length of {math.ceil(web_t + tap + 4)} mm or more, or no set screw")
        z = (web_t + total) / 2
        # Across the flat of a D shaft (it sits at +Y), between two spokes where it can.
        ang = 90.0 if shaft in SHAFTS[1:3] else (180.0 / n if n else 0.0)
        body -= Rot(0, 0, ang) * Pos(0, 0, z) * (Rot(0, 90, 0) * Cylinder(tap / 2, hub_od / 2 + 1, align=MIN_))
        notes.append(f"a Ø{tap:g} mm hole through the hub for an {set_screw} set screw: the screw cuts its own thread, or open it up and melt in a threaded insert"
                     + ("; it bears on the shaft's flat" if shaft in SHAFTS[1:3] else ""))
    elif shaft == "round":
        checks.append("a round bore with no set screw only holds if it is a press fit or glued: take the fit down to 0, or pick a D, hex or square shaft")
    if handle != "none":
        hr = D / 2 - rm / 2
        if handle == "printed post":
            post = Pos(hr, 0, rm - 0.01) * Cylinder(min(6.0, rm * 0.45), 38.0, align=MIN_)
            try:
                post = fillet(post.edges().sort_by(Axis.Z)[-1], 2.0)
            except Exception:
                pass
            body += post
            notes.append("a fixed post on the rim to spin it by; it prints standing on the rim")
        else:
            body -= Pos(hr, 0, -1) * Cylinder(2.75, rm + 2, align=MIN_)
            body -= Pos(hr, 0, -0.01) * extrude(RegularPolygon(4.1, 6, major_radius=False), amount=4.5, dir=(0, 0, 1))
            notes.append("a Ø5.5 mm hole through the rim with a pocket for an M5 nut underneath: bolt on a revolving handle, or an M5 screw with a sleeve over it")
    notes.append("print it as it lies, rim and spokes on the bed, 4 walls and 30% infill or more; no supports")
    return _out(body, notes, checks, {"hub_d": round(hub_od, 2), "height": total, "bore": round(d + 2 * f, 3)})


# ---------- Wheel and tyre for a radio-controlled car ----------

PIECES = ("wheel (rigid plastic)", "tyre (TPU)")
# Usual sizes by scale: tyre diameter, width, wheel diameter, drive hex, hex depth, axle.
RC_SCALES = {"custom (the sizes below)": None,
             "1/10 touring car (65 x 26, 12 mm hex)": (65.0, 26.0, 52.0, 12.0, 5.0, 4.0),
             "1/10 buggy, rear (85 x 38, 12 mm hex)": (85.0, 38.0, 56.0, 12.0, 5.0, 4.0),
             "1/10 crawler, 1.9 in (100 x 35, 12 mm hex)": (100.0, 35.0, 48.3, 12.0, 5.0, 4.0),
             "1/18 to 1/24 mini (30 x 12, 7 mm hex)": (30.0, 12.0, 22.0, 7.0, 3.0, 2.0),
             "1/8 buggy (112 x 42, 17 mm hex)": (112.0, 42.0, 83.0, 17.0, 7.0, 8.0)}
TREADS = ("slick", "ribbed", "blocks")
WEBS = ("spokes", "dish")


def _rim_profile(rb: float, lip: float, lw: float, W: float, grow: float = 0.0):
    """(r, z) points up the outside of the wheel's barrel: a lip at each edge with a 45° slope on its
    inner side, so the top one prints without support and the tyre's beads lock behind both."""
    g = grow
    return [(rb + lip + g, 0), (rb + lip + g, lw + g), (rb + g, lw + lip + g), (rb + g, W - lw - lip - g),
            (rb + lip + g, W - lw - g), (rb + lip + g, W)]


def rc_wheel(piece="wheel (rigid plastic)", tyre_d=65.0, width=26.0, rim_d=52.0, hex=12.0, hex_depth=5.0, axle_d=4.0, mount_inset=0.0,
             web="spokes", spokes=6, tread="blocks", fit=0.15, scale="custom (the sizes below)"):
    """A wheel for a radio-controlled car or a robot in two prints: a rigid wheel (PETG or PLA) with
    a pocket for the drive hex, and a soft tyre (TPU) that stretches over it and locks behind a lip
    at each edge. Pick which of the two to make; the other is shown with it in grey."""
    if piece not in PIECES:
        raise ValueError(f"piece: one of {', '.join(PIECES)}")
    if tread not in TREADS or web not in WEBS:
        raise ValueError(f"tread: one of {', '.join(TREADS)}; centre: one of {', '.join(WEBS)}")
    if scale not in RC_SCALES:
        raise ValueError(f"scale: one of {', '.join(RC_SCALES)}")
    preset = RC_SCALES[scale]
    if preset:
        tyre_d, width, rim_d, hex, hex_depth, axle_d = preset
    OD, W, RD, f = float(tyre_d), float(width), float(rim_d), float(fit)
    hx, _ = sizes.parse(hex, "drive hex")
    ax, _ = sizes.parse(axle_d, "axle")
    hd, n = float(hex_depth), int(spokes)
    _rng("tyre diameter", OD, 20, 200); _rng("width", W, 8, 90); _rng("fit", f, 0, 0.5); _rng("spokes", n, 3, 12, "")
    _rng("axle", ax, 1.5, 12)
    if hx:
        _rng("drive hex", hx, 5, 24); _rng("hex depth", hd, 2, 10)
        if hx < ax + 2:
            raise ValueError(f"the drive hex is at least {ax + 2:g} mm across for a {ax:g} mm axle")
    thick = (OD - RD) / 2
    if thick < 3 or RD < 12:
        raise ValueError(f"wheel diameter: 12 to {OD - 6:g} mm, so the tyre is at least 3 mm thick")
    rb = RD / 2
    lip = round(min(1.6, thick * 0.3), 2)
    lw = 1.2
    wall = 2.0 if RD < 40 else 2.4
    ri = rb - wall
    boss_r = max(hx * 0.58 + 2.5, ax / 2 + 3.5) if hx else ax / 2 + 3.5
    if boss_r > ri - 1:
        raise ValueError("the drive hex or axle is too big for this wheel: a bigger wheel diameter or a smaller hex")
    inset = float(mount_inset) or W / 2
    seat = 4.0                                        # plastic between the hex and the wheel nut
    _rng("mounting face from the inner edge", inset, 1.0 if hx else 0.0, W - seat)
    web_t = 3.0

    # The wheel, its outer face on the bed (z = 0) and its inner edge up at z = W.
    outline = _rim_profile(rb, lip, lw, W) + [(ri, W), (ri, 0)]
    rim = revolve(Plane.XZ * Polygon(*outline, align=None), axis=Axis.Z)
    rim += Cylinder(ri + 0.2, web_t, align=MIN_)
    face_z = W - inset                                # the face the drive hex bears on, up from the bed
    boss_h = face_z + (hd if hx else 0.0)
    rim += Cylinder(boss_r, min(W, boss_h), align=MIN_)
    if hx:
        rim -= Pos(0, 0, face_z) * extrude(RegularPolygon(hx / 2 + f, 6, major_radius=False), amount=W, dir=(0, 0, 1))
    rim -= Pos(0, 0, -1) * Cylinder(ax / 2 + f, W + 2, align=MIN_)
    nut_r = max(ax * 1.15 + 1.5, ax / 2 + 2.5)        # room for the wheel nut and a socket on it
    if face_z > seat + 0.5:
        rim -= Pos(0, 0, -0.01) * Cylinder(min(nut_r, boss_r - 1.2), face_z - seat, align=MIN_)
    windows = 0
    if web == "spokes":
        mid, room = (boss_r + ri) / 2, ri - boss_r
        wd = min(room - 3.0, 2 * math.pi * mid / n - 3.0)
        if wd >= 3:
            for i in range(n):
                rim -= Rot(0, 0, 360 * i / n) * Pos(mid, 0, -1) * Cylinder(wd / 2, web_t + 2, align=MIN_)
            windows = n

    # The tyre: stretched on 2%, with a groove inside each edge for the wheel's lips.
    squeeze = 0.98
    inner = [(r * squeeze, z) for r, z in _rim_profile(rb, lip, lw, W, 0.1)]
    ro = OD / 2
    sh = round(min(3.0, thick * 0.35, W * 0.15), 2)   # the shoulders are cut back at 45°
    tyre = revolve(Plane.XZ * Polygon(*inner, (ro - sh, W), (ro, W - sh), (ro, sh), (ro - sh, 0), align=None), axis=Axis.Z)
    td = round(min(2.5, thick * 0.35), 2)
    if tread == "ribbed":
        ribs = max(1, int(W // 8))
        for i in range(ribs):
            z = W * (i + 1) / (ribs + 1)
            tyre -= Pos(0, 0, z - 0.8) * (Cylinder(ro + 1, 1.6, align=MIN_) - Cylinder(ro - td, 1.6, align=MIN_))
    elif tread == "blocks":
        cuts = max(8, round(math.pi * OD / 9))
        slot = Pos(ro - td, 0, -1) * Box(td + 2, 2.0, W + 2, align=(Align.MIN, Align.CENTER, Align.MIN))
        tools = Compound(children=[Rot(0, 0, 360 * i / cuts) * slot for i in range(cuts)])
        tyre -= tools
        tyre -= Pos(0, 0, W / 2 - 0.8) * (Cylinder(ro + 1, 1.6, align=MIN_) - Cylinder(ro - td, 1.6, align=MIN_))

    making_rim = piece == PIECES[0]
    info = {"tyre_d": OD, "wheel_d": RD, "width": W, "tyre_thickness": round(thick, 2), "tyre_bore": round(2 * rb * squeeze, 2),
            "mounting_face_from_inner_edge": round(inset, 2)}
    both = (f"Ø{OD:g} x {W:g} mm tyre on a Ø{RD:g} mm wheel" + (f", {hx:g} mm drive hex {hd:g} mm deep" if hx else "") + f", Ø{ax:g} mm axle")
    if making_rim:
        notes = [f"wheel for a radio-controlled car: {both}; " + (f"{windows} round windows in its face" if windows else "a solid dish face"),
                 f"the hex bears on a face {inset:g} mm in from the wheel's inner edge" + (" (the middle of the wheel: zero offset)" if not float(mount_inset) else "")
                 + f", with {min(seat, face_z):g} mm of plastic between it and the wheel nut" if hx else
                 f"a plain Ø{ax + 2 * f:g} mm bore through a boss: press it on the axle or lock it with a collar or a nut each side",
                 "print it in PETG, or PLA for indoors, outer face on the bed as it lies, 4 walls and 40% infill; no supports. Print four",
                 "shown in grey: the TPU tyre. It is not in these files: choose 'tyre (TPU)' above to make it"]
        out = _out(rim, notes, [], info)
        out["fitted"] = tyre
    else:
        notes = [f"tyre for a radio-controlled car: {both}; {tread}" + (f", tread {td:g} mm deep" if tread != "slick" else ""),
                 f"its bore is Ø{2 * rb * squeeze:.1f} mm, 2% under the wheel, with a groove inside each edge that snaps over the wheel's lips; "
                 "warm it in hot water if it is stiff to get on, and a drop of superglue at the bead holds it for hard driving",
                 "print it in TPU (95A, or softer for grip) on its side as it lies, 2 walls and 10 to 15% gyroid infill for a tyre that gives, more for a firmer one; "
                 "no supports, slow (25 mm/s) and dry filament",
                 "shown in grey: the wheel. It is not in these files: choose 'wheel (rigid plastic)' above to make it"]
        out = _out(tyre, notes, [], info)
        out["fitted"] = rim
    if preset:
        out["notes"].insert(1, f"sizes are the usual ones for {scale.split(' (')[0]}: cars differ, so check the hex, the axle and the room in the wheel arch on yours. "
                               "Pick 'custom' to set every size yourself")
    if thick < 5:
        out["checks"].append(f"the tyre is only {thick:g} mm thick: there is little rubber to soak up bumps")
    return out


# ---------- Replacement knob for an appliance ----------

def _knob_marks(text, sweep: float, start: float) -> list[tuple[str, float]]:
    """Markings and where they go, clockwise from the pointer: "OFF|LO|MED|HI" spreads them evenly
    over the sweep from the start angle; "OFF@0|LO@60|HI@300" puts each where you say. A lone - is a
    line and a lone . is a dot."""
    items = [t.strip() for t in str(text or "").replace("\n", "|").split("|") if t.strip()]
    if not items:
        return []
    if len(items) > 24 or any(len(t.split("@")[0].strip()) > 14 for t in items):
        raise ValueError("markings: up to 24 of them, each up to 14 characters, with | between")
    _rng("sweep", sweep, 0, 360, "°")
    out, free = [], []
    for t in items:
        if "@" in t:
            label, _, at = t.rpartition("@")
            try:
                out.append((label.strip() or "-", float(at)))
            except ValueError:
                raise ValueError(f"markings: '{t}' should be a marking, an @ and an angle, such as HI@270") from None
        else:
            free.append(len(out))
            out.append((t, 0.0))
    step = (sweep / len(free) if sweep >= 359.9 else sweep / (len(free) - 1)) if len(free) > 1 else 0.0
    for i, at in enumerate(free):
        out[at] = (out[at][0], start + i * step)
    return out


KNOB_STYLES = ("pointer bar (oven, hob)", "round, fluted (washer, dryer)", "round, smooth")
KNOB_SHAFTS = ("D (one flat)", "double D (two flats)", "round", "splined")
FLAT_AT = ("12 o'clock (toward the pointer)", "3 o'clock", "6 o'clock (away from the pointer)", "9 o'clock")
GRIPS = ("snug", "split, springy")


def appliance_knob(style="pointer bar (oven, hob)", diameter=45.0, height=28.0, skirt=5.0, shaft="D (one flat)", shaft_d=6.0, flat=0.0,
                   depth=14.0, flat_at="12 o'clock (toward the pointer)", grip="split, springy", stem_below=0.0, set_screw="none",
                   two_color=False, fit=0.1, marks="", mark_size=4.0, mark_sweep=270.0, mark_start=0.0):
    """A replacement knob for an oven, hob, washer, dryer or anything else with a D shaft: measure
    the shaft, say which way its flat faces when the pointer is straight up, and pick a shape. A
    split stem springs onto the shaft the way the original's clip did."""
    if style not in KNOB_STYLES:
        raise ValueError(f"style: one of {', '.join(KNOB_STYLES)}")
    if shaft not in KNOB_SHAFTS:
        raise ValueError(f"shaft: one of {', '.join(KNOB_SHAFTS)}")
    if flat_at not in FLAT_AT or grip not in GRIPS:
        raise ValueError(f"flat: one of {', '.join(FLAT_AT)}; grip: one of {', '.join(GRIPS)}")
    if set_screw not in ("none", "M3", "M4"):
        raise ValueError("set screw: none, M3 or M4")
    D, H, sk, dp, below, f = float(diameter), float(height), float(skirt), float(depth), float(stem_below), float(fit)
    d, d_say = sizes.parse(shaft_d, "shaft")
    fl, _ = sizes.parse(flat, "across the flat")
    _rng("diameter", D, 18, 120); _rng("height", H, 10, 60); _rng("skirt", sk, 0, 15); _rng("shaft", d, 3, 12)
    _rng("socket depth", dp, 5, 40); _rng("stem below the knob", below, 0, 30); _rng("fit", f, -0.1, 0.4)
    if dp - below > H - 2.5:
        raise ValueError(f"socket depth: up to {H - 2.5 + below:g} mm here, to leave 2.5 mm over the shaft")
    bar = style == KNOB_STYLES[0]
    split = grip == GRIPS[1]
    stem_r = d / 2 + 2.4
    relief = 1.4 if split else 0.0
    core_r = stem_r + relief + (2.4 if split else 0.0)
    if 2 * core_r > D * (0.62 if bar else 0.8):
        raise ValueError(f"this shaft needs a knob at least {2 * core_r / (0.62 if bar else 0.8):.0f} mm across")

    labels = _knob_marks(marks, float(mark_sweep), float(mark_start))
    ms = float(mark_size)
    ring = 0.0
    if labels:
        _rng("marking size", ms, 2.5, 10)
        ring = ms + (4.0 if bar else 3.0)             # a flat ring round the skirt for the markings to sit on
        sk = sk or 3.0
    # The body, its base on the bed, the pointer toward +Y.
    if bar:
        base_h = sk or 3.0
        body = Cylinder(D / 2 + ring, base_h, align=MIN_)
        try:
            body = chamfer(body.edges().sort_by(Axis.Z)[-1], min(1.2, base_h * 0.4))
        except Exception:
            pass
        bw = max(9.0, D * 0.27)
        grip_bar = Pos(0, 0, base_h - 0.01) * extrude(RectangleRounded(bw, D * 0.94, bw * 0.38), amount=H - base_h + 0.01, dir=(0, 0, 1))
        try:
            grip_bar = fillet(grip_bar.edges().group_by(Axis.Z)[-1], min(1.5, bw * 0.15))
        except Exception:
            pass
        body += grip_bar
        hub_h = min(H, max(base_h, dp - below + 2.5))
        if 2 * core_r > bw - 1 and hub_h > base_h:
            body += Cylinder(core_r, hub_h, align=MIN_)       # room for the stem where the bar is narrower than it
        ml = D * 0.47 - 4.5
        mark = Pos(0, 3 + ml / 2, H - 0.6) * Box(1.6, ml, 0.61, align=MIN_)
    else:
        from build123d import Cone
        body = Cone(D / 2, D / 2 * 0.9, H, align=MIN_)
        try:
            body = fillet(body.edges().sort_by(Axis.Z)[-1], min(2.0, H * 0.1))
        except Exception:
            pass
        if style == KNOB_STYLES[1]:
            nfl = max(8, round(D / 4.5))
            fr = math.pi * D / nfl * 0.3
            flute = Pos(D / 2 + fr * 0.45, 0, sk) * Cylinder(fr, H + 2, align=MIN_)
            for i in range(nfl):
                body -= Rot(0, 0, 360 * (i + 0.5) / nfl + 90) * flute
        if sk:
            flange = Cylinder(D / 2 + (ring + 0.5 if ring else 3), sk, align=MIN_)
            try:
                flange = chamfer(flange.edges().sort_by(Axis.Z)[-1], min(1.0, sk * 0.4))
            except Exception:
                pass
            body += flange
        ml = D * 0.45 * 0.9 - 4
        mark = Pos(0, 4 + ml / 2, H - 0.6) * Box(1.8, ml, 0.61, align=MIN_)
    if below:
        body += Pos(0, 0, -below) * Cylinder(stem_r, below + 0.01, align=MIN_)

    # The socket, turned to where the shaft's flat sits when the pointer is at 12.
    turn = -90.0 * FLAT_AT.index(flat_at)
    hole_d = d + 2 * f if shaft != "splined" else d - 0.3
    kind = "round" if shaft in ("round", "splined") else shaft
    tool = _shaft_tool(kind, hole_d, (fl + 2 * f) if fl and kind != "round" else 0.0, dp + 0.01)
    body -= Pos(0, 0, -below - 0.01) * (Rot(0, 0, turn) * tool)
    if split:
        # A ring cut round the stem frees it from the knob, and a slot across it lets it open.
        free = min(dp - below, H - 3.5) * 0.85
        if free > 2:
            body -= Pos(0, 0, -0.01) * (Cylinder(stem_r + relief, free, align=MIN_) - Cylinder(stem_r, free, align=MIN_))
        slot_h = (below + free) if free > 2 else below
        if slot_h > 2:
            body -= Pos(0, 0, -below - 0.01) * (Rot(0, 0, turn) * Box(2 * stem_r + 2 * relief - 0.4, 1.0, slot_h, align=MIN_))
    body -= mark
    crowded = False
    if labels:
        from build123d import Text
        from . import fonts
        rt = D / 2 + (ring / 2 - 0.3 if bar else 0.5 + ring / 2 - 0.2)
        top = sk if not bar else base_h
        cuts = []
        for text, ang in labels:
            if text == "-":
                flat = [Box(0.9, ring - 2.0, 0.61, align=MIN_)]
            elif text == ".":
                flat = [Cylinder(max(0.8, ms * 0.22), 0.61, align=MIN_)]
            else:
                try:
                    flat = [extrude(f, amount=0.61, dir=(0, 0, 1)) for f in fonts.sound_faces(Text(text, ms, align=(Align.CENTER, Align.CENTER)))]
                except Exception:
                    raise ValueError(f"markings: '{text}' has a character that can't be drawn") from None
            a = math.radians(ang)
            cuts += [Pos(rt * math.sin(a), rt * math.cos(a), top - 0.6) * (Rot(0, 0, -ang) * c) for c in flat]
        angs = sorted(a % 360 for _, a in labels)
        gaps = [(angs[(i + 1) % len(angs)] - angs[i]) % 360 or 360 for i in range(len(angs))] if len(angs) > 1 else [360]
        widest = max(len(t) for t, _ in labels) * 0.62 * ms
        crowded = math.radians(min(gaps)) * rt < widest + 1.0
        mark = Compound(children=[mark] + cuts)
        for c in cuts:
            body -= c
    notes = [f"{style.split(' (')[0].split(',')[0]} knob Ø{D:g} x {H:g} mm for {_shaft_say(kind if shaft != 'splined' else 'round', d, fl, d_say).replace('round shaft', shaft + ' shaft')}"
             f", socket {dp:g} mm deep" + (f", on a stem {below:g} mm below the knob" if below else ""),
             ]
    if kind != "round":
        notes.append(f"with the pointer straight up the shaft's flat is at {flat_at.split(' (')[0]}: turn the appliance to off (or a known mark), look at the shaft, and change this if the flat is somewhere else"
                     + ("" if fl else f". The flat is taken as {round(d * 0.75, 2):g} mm across (three quarters of the shaft): measure yours across the flat and type it if it differs"))
    if split:
        notes.append("the stem is cut free of the knob and slotted so it springs onto the shaft like the original's clip; for a tighter grip take the fit down to 0 or -0.05")
    if shaft == "splined":
        notes.append(f"the socket is Ø{hole_d:g} mm, 0.3 mm under the splines, so they bite into the plastic as it goes on")
    checks = []
    tap = SET_SCREWS.get(set_screw, 0.0)
    if tap:
        zs = max(tap, min(dp - below, H - 3) / 2 if not bar else (sk or 3.0) / 2)
        ang = turn + 90.0 if kind != "round" else 180.0
        reach = D / 2 + 4
        body -= Rot(0, 0, ang) * Pos(0, 0, max(zs, tap / 2 + 1.0)) * (Rot(0, 90, 0) * Cylinder(tap / 2, reach, align=MIN_))
        notes.append(f"a Ø{tap:g} mm hole from the side for an {set_screw} set screw" + (" onto the flat" if kind != "round" else ""))
        if split:
            checks.append("a set screw and a split stem fight each other: pick the snug grip with a set screw")
    elif shaft == "round":
        checks.append("a round shaft needs a set screw (or glue) to turn with the knob")
    inlay = None
    what = "the pointer and the markings" if labels else "the pointer"
    if labels:
        notes.append(f"{len(labels)} markings round the skirt, {ms:g} mm tall, on a {ring:g} mm ring added for them (the skirt is now Ø{body.bounding_box().size.X:g} mm): "
                     + ", ".join(f"{'a line' if t == '-' else 'a dot' if t == '.' else t} at {a % 360:g}°" for t, a in labels[:12])
                     + "; angles run clockwise from the pointer, seen from the front")
        if crowded:
            checks.append("some markings are close enough to touch: fewer of them, a smaller marking size, a wider sweep or a bigger knob")
    if two_color:
        inlay = mark
        notes.append(f"{what} come as their own body for a second colour; without a multi-colour printer, fill the grooves with paint or a wax crayon")
    else:
        notes.append(f"{what} are cut 0.6 mm deep: fill with paint or a wax crayon to make them show" if labels else
                     "the pointer is a groove 0.6 mm deep: fill it with paint or a wax crayon to make it show")
    if below:
        checks.append("the stem stands below the knob, so the knob's underside hangs in the air: print with supports from the bed only")
    notes.append("print it as it stands, base on the bed, in PETG or ASA (an oven or hob knob gets warm: not PLA), 3 walls and 30% infill"
                 + ("" if below else "; no supports"))
    out = _out(body, notes, checks, {"socket": round(hole_d, 3), "flat": round((fl or d * 0.75) + (2 * f if kind != "round" else 0), 3) if kind != "round" else 0,
                                     "depth": dp})
    if inlay is not None:
        out["inlay"] = inlay
    return out


KINDS = {
    "handwheel": (handwheel, "Handwheel", {"diameter": 100.0, "rim": 12.0, "spokes": 3, "shaft": "round", "bore_d": 8.0, "flat": 0.0,
                                           "hub_length": 20.0, "hub_d": 0.0, "set_screw": "M4", "handle": "none", "fit": 0.15}),
    "rc_wheel": (rc_wheel, "RC car wheel and tyre", {"piece": PIECES[0], "scale": "custom (the sizes below)", "tyre_d": 65.0, "width": 26.0, "rim_d": 52.0, "hex": 12.0, "hex_depth": 5.0,
                                                     "axle_d": 4.0, "mount_inset": 0.0, "web": "spokes", "spokes": 6, "tread": "blocks", "fit": 0.15}),
    "appliance_knob": (appliance_knob, "Appliance knob (oven, washer, dryer)", {
        "style": KNOB_STYLES[0], "diameter": 45.0, "height": 28.0, "skirt": 5.0, "shaft": "D (one flat)", "shaft_d": 6.0, "flat": 0.0, "depth": 14.0,
        "flat_at": FLAT_AT[0], "grip": GRIPS[1], "stem_below": 0.0, "set_screw": "none", "two_color": False, "fit": 0.1,
        "marks": "", "mark_size": 4.0, "mark_sweep": 270.0, "mark_start": 0.0}),
}
KIND_LABELS = {
    ("handwheel", "diameter"): ("Diameter", "len"), ("handwheel", "rim"): ("Rim thickness", "len"), ("handwheel", "spokes"): ("Spokes (0: a solid web)", "num"),
    ("handwheel", "shaft"): ("Shaft", "select"), ("handwheel", "bore_d"): ("Shaft size: 8, 3/8, 0.5 in (hex and square: across the flats)", "size"),
    ("handwheel", "flat"): ("D shaft: across the flat (0: three quarters of the shaft)", "size"),
    ("handwheel", "hub_length"): ("Hub length (0: no hub, flush with the rim)", "len"), ("handwheel", "hub_d"): ("Hub diameter (0: to suit)", "len"),
    ("handwheel", "set_screw"): ("Set screw", "select"), ("handwheel", "handle"): ("Spinner handle", "select"), ("handwheel", "fit"): ("Fit (added round the shaft)", "len"),
    ("rc_wheel", "piece"): ("Make the", "select"), ("rc_wheel", "scale"): ("Scale", "select"), ("rc_wheel", "tyre_d"): ("Tyre outside diameter", "len"), ("rc_wheel", "width"): ("Width", "len"),
    ("rc_wheel", "rim_d"): ("Wheel diameter (where the tyre sits)", "len"), ("rc_wheel", "hex"): ("Drive hex: 12 for 1/10, 7 for small scales, 17 for 1/8 (0: none)", "size"),
    ("rc_wheel", "hex_depth"): ("Hex depth", "len"), ("rc_wheel", "axle_d"): ("Axle diameter", "size"),
    ("rc_wheel", "mount_inset"): ("Hex face in from the inner edge (0: the middle)", "len"), ("rc_wheel", "web"): ("Face", "select"),
    ("rc_wheel", "spokes"): ("Windows in the face", "num"), ("rc_wheel", "tread"): ("Tread", "select"), ("rc_wheel", "fit"): ("Fit (round the hex and axle)", "len"),
    ("appliance_knob", "style"): ("Shape", "select"), ("appliance_knob", "diameter"): ("Diameter", "len"), ("appliance_knob", "height"): ("Height", "len"),
    ("appliance_knob", "skirt"): ("Skirt height (0: none)", "len"), ("appliance_knob", "shaft"): ("Shaft", "select"),
    ("appliance_knob", "shaft_d"): ("Shaft diameter: 6, 1/4, 3/16", "size"), ("appliance_knob", "flat"): ("Across the flat (0: three quarters of the shaft)", "size"),
    ("appliance_knob", "depth"): ("Socket depth (how much shaft goes in)", "len"), ("appliance_knob", "flat_at"): ("With the pointer up, the flat is at", "select"),
    ("appliance_knob", "grip"): ("Grip on the shaft", "select"), ("appliance_knob", "stem_below"): ("Stem below the knob, for a shaft set back in the panel (0: none)", "len"),
    ("appliance_knob", "set_screw"): ("Set screw", "select"), ("appliance_knob", "two_color"): ("Pointer and markings in a second colour", "bool"),
    ("appliance_knob", "fit"): ("Fit (added round the shaft)", "len"),
    ("appliance_knob", "marks"): ("Your markings round the skirt, | between: OFF|LO|MED|HI, or each at its own angle: OFF@0|1@45|2@90 (- is a line, . a dot)", "text"),
    ("appliance_knob", "mark_size"): ("Marking height", "len"), ("appliance_knob", "mark_sweep"): ("Spread them over, °", "num"),
    ("appliance_knob", "mark_start"): ("First one at, ° clockwise from the pointer", "num"),
}
CHOICES = {
    ("handwheel", "shaft"): list(SHAFTS), ("handwheel", "set_screw"): list(SET_SCREWS), ("handwheel", "handle"): list(HANDLES),
    ("rc_wheel", "piece"): list(PIECES), ("rc_wheel", "scale"): list(RC_SCALES), ("rc_wheel", "web"): list(WEBS), ("rc_wheel", "tread"): list(TREADS),
    ("appliance_knob", "style"): list(KNOB_STYLES), ("appliance_knob", "shaft"): list(KNOB_SHAFTS), ("appliance_knob", "flat_at"): list(FLAT_AT),
    ("appliance_knob", "grip"): list(GRIPS), ("appliance_knob", "set_screw"): ["none", "M3", "M4"],
}
GROUPS: dict = {}       # filed with the gears and pulleys, in hardware.py
WORDS = {
    "handwheel": "hand wheel crank valve wheel machine lathe mill handle hub set screw",
    "rc_wheel": "rc car radio control tire tyre tpu rim robot wheel 12mm hex buggy crawler",
    "appliance_knob": "oven stove range hob cooker washer dryer washing machine dial knob replacement d shaft timer",
}
