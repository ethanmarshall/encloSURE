"""A bent sheet metal enclosure: a base (the floor with the two end walls and two low lips bent up)
and a cover (the top with its two sides bent down) that slides over it and screws into the lips.
Each comes as a flat pattern DXF to cut and bend (SendCutSend, Protocase or a local shop), with the
bend lines, and a STEP of the formed parts.

Flat lengths use the bend allowance BA = (pi / 2) (R + K t) for each 90 degree bend, R the inside
bend radius and K the K-factor (where the neutral axis sits); legs are measured to their outside.
Corners where two bends meet are left open by the bend relief (about R + t each way).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from build123d import Align, Box, Cylinder, Location, Pos, Rot

# Typical sheet: (thickness, inside bend radius) pairs a shop stocks, mm; K-factor for air bending.
MATERIALS = {"aluminium 5052": {"k": 0.40, "density": 2.68}, "steel (CRS)": {"k": 0.44, "density": 7.85},
             "stainless 304": {"k": 0.45, "density": 8.0}}
SCREW_TAP = {"M2.5": 2.05, "M3": 2.5, "M4": 3.3}  # thread-forming tap drill in the lips
SCREW_CLEAR = {"M2.5": 2.9, "M3": 3.4, "M4": 4.5}


@dataclass
class Sheet:
    size: list[float] = field(default_factory=lambda: [120.0, 80.0, 40.0])  # inside L x W x H
    thickness: float = 1.5
    bend_radius: float | None = None  # inside radius; None = the thickness
    material: str = "aluminium 5052"
    k_factor: float | None = None
    lip: float = 0.0  # the base's lips the cover screws into; 0: as short as clears the bend for its screws
    screw: str = "M3"
    screws_per_side: int = 2
    cutouts: list[dict] = field(default_factory=list)  # as the printed box: face, shape, size, at (or preset)

    def check(self):
        if len(self.size) != 3 or min(self.size) <= 10:
            raise ValueError("size: three numbers over 10 mm")
        if not 0.5 <= self.thickness <= 4:
            raise ValueError("thickness: 0.5 to 4 mm")
        if self.material not in MATERIALS:
            raise ValueError(f"material: one of {', '.join(MATERIALS)}")
        if self.screw not in SCREW_TAP:
            raise ValueError(f"screw: one of {', '.join(SCREW_TAP)}")
        if self.lip <= 0:
            self.lip = 0.0
            need = _screw_z(self) + SCREW_CLEAR[self.screw] / 2 + 1.5
            self.lip = max(10.0, math.ceil(need * 2) / 2)
            return
        need = _screw_z(self) + SCREW_CLEAR[self.screw] / 2 + 1.5
        if self.lip < need:
            raise ValueError(f"lip: at least {need:.1f} mm, so its screw holes sit clear of the bend")

    @property
    def R(self):
        return self.bend_radius if self.bend_radius is not None else self.thickness

    @property
    def K(self):
        return self.k_factor if self.k_factor is not None else MATERIALS[self.material]["k"]

    @property
    def BA(self):
        return math.pi / 2 * (self.R + self.K * self.thickness)


def _leg(sheet: Sheet, outside: float) -> float:
    """Flat length of a leg measured to the outside: what's left past the bend."""
    return outside - (sheet.R + sheet.thickness)


def _screw_z(sheet: "Sheet") -> float:
    """The lip screws' height: far enough from the bend that the hole's edge is 2 x thickness + bend
    radius from the bend line (RMFG's rule, and a good one anywhere), or mid-lip if that's higher."""
    t, R, BA = sheet.thickness, sheet.R, sheet.BA
    r = SCREW_CLEAR[sheet.screw] / 2
    return max(sheet.lip / 2, 2 * t + R + r + (R + t) - BA / 2 + 0.3)


def flats(sheet: Sheet) -> dict:
    """The flat patterns of the base and cover: outlines, bend lines and holes, in mm."""
    sheet.check()
    L, W, H = sheet.size
    t, R, BA = sheet.thickness, sheet.R, sheet.BA
    rt = R + t
    out = {}
    # Base: floor (L + 2t) x W outside; end walls up to the cover's underside (t + H); lips sheet.lip tall.
    bx, by = L + 2 * t, W
    core = (bx - 2 * rt, by - 2 * rt)
    wall_leg = _leg(sheet, t + H)
    lip_leg = _leg(sheet, sheet.lip)
    out["base"] = {"core": core, "flaps": {"+x": (wall_leg, core[1]), "-x": (wall_leg, core[1]),
                                           "+y": (lip_leg, core[0] - 2 * t), "-y": (lip_leg, core[0] - 2 * t)}}
    # Cover: top (L + 2t) x (W + 2t) outside; sides down to the bottom (2t + H).
    cx, cy = L + 2 * t, W + 2 * t
    ccore = (cx, cy - 2 * rt)  # no flaps on its ends: the full length
    side_leg = _leg(sheet, 2 * t + H)
    out["cover"] = {"core": ccore, "flaps": {"+y": (side_leg, ccore[0]), "-y": (side_leg, ccore[0])}}
    # Screws: through the cover's sides into the lips, halfway up the lip.
    xs = [(-0.5 + (i + 0.5) / sheet.screws_per_side) * (L * 0.8) for i in range(sheet.screws_per_side)]
    z_screw = _screw_z(sheet)
    out["screws"] = {"x": xs, "z": z_screw}
    return out


def _flat_pos(sheet: Sheet, which: str, face: str, along: float, height: float):
    """Where a feature on the formed part lands on the flat pattern: (x, y) on the flat."""
    L, W, H = sheet.size
    t, rt, BA = sheet.thickness, sheet.R + sheet.thickness, sheet.BA
    f = flats(sheet)[which]
    cx, cy = f["core"]
    if which == "base" and face in ("-X", "+X"):
        z = t + height  # outside height from the bottom
        d = cx / 2 + BA + (z - rt)
        return (d if face == "+X" else -d, along)
    if which == "base" and face in ("-Y", "+Y"):
        z = t + height
        d = cy / 2 + BA + (z - rt)
        return (along, d if face == "+Y" else -d)
    if which == "cover" and face in ("-Y", "+Y"):
        z = t + height
        down = (2 * t + H) - z  # from the cover's top, outside
        d = cy / 2 + BA + (down - rt)
        return (along, d if face == "+Y" else -d)
    return (along, height)


def _outline(core, flaps, BA, relief):
    """The flat's outline as one polygon going round: core with flaps (bend zone + leg) on its edges."""
    cx, cy = core
    pts = []
    hx, hy = cx / 2, cy / 2
    # Walk: bottom edge (-y) left to right, right edge (+x) bottom to top, top (+y), left (-x).
    def flap_pts(edge):
        if edge not in flaps:
            return []
        leg, width = flaps[edge]
        reach = BA + leg
        w = width / 2
        if edge == "-y":
            return [(-w, -hy), (-w, -hy - reach), (w, -hy - reach), (w, -hy)]
        if edge == "+x":
            return [(hx, -w), (hx + reach, -w), (hx + reach, w), (hx, w)]
        if edge == "+y":
            return [(w, hy), (w, hy + reach), (-w, hy + reach), (-w, hy)]
        return [(-hx, w), (-hx - reach, w), (-hx - reach, -w), (-hx, -w)]
    pts += [(-hx, -hy)] + flap_pts("-y") + [(hx, -hy)] + flap_pts("+x") + [(hx, hy)] + flap_pts("+y") + [(-hx, hy)] + flap_pts("-x")
    # Drop repeated points.
    clean = []
    for p in pts:
        if not clean or (abs(p[0] - clean[-1][0]) > 1e-9 or abs(p[1] - clean[-1][1]) > 1e-9):
            clean.append(p)
    return clean


def _bend_lines(core, flaps, BA):
    cx, cy = core
    lines = []
    for edge, (leg, width) in flaps.items():
        w = width / 2
        for off in (BA / 2,):  # the bend's centre line
            if edge == "+x":
                lines.append(((cx / 2 + off, -w), (cx / 2 + off, w)))
            elif edge == "-x":
                lines.append(((-cx / 2 - off, -w), (-cx / 2 - off, w)))
            elif edge == "+y":
                lines.append(((-w, cy / 2 + off), (w, cy / 2 + off)))
            else:
                lines.append(((-w, -cy / 2 - off), (w, -cy / 2 - off)))
    return lines


def _holes(sheet: Sheet, which: str) -> list[dict]:
    """Holes on a flat: the screw holes and the cutouts that land on this part."""
    from .presets import expand, resolve
    f = flats(sheet)
    out = []
    z = f["screws"]["z"]
    for x in f["screws"]["x"]:
        for face in ("-Y", "+Y"):
            if which == "base":
                pos = _flat_pos(sheet, "base", face, x, z - sheet.thickness)
                out.append({"shape": "round", "size": [SCREW_TAP[sheet.screw]], "at": pos, "what": f"{sheet.screw} tap"})
            else:
                pos = _flat_pos(sheet, "cover", face, x, z - sheet.thickness)
                out.append({"shape": "round", "size": [SCREW_CLEAR[sheet.screw]], "at": pos, "what": f"{sheet.screw} clearance"})
    for raw in expand(sheet.cutouts):
        c = resolve(dict(raw))
        face = {"left": "-X", "right": "+X", "front": "-Y", "back": "+Y"}.get(c["face"], c["face"])
        a, b = c.get("at", [0, 0])
        if which == "base" and face in ("-X", "+X", "floor"):
            pos = (a, b) if face == "floor" else _flat_pos(sheet, "base", face, a, b)
        elif which == "cover" and face in ("-Y", "+Y", "lid"):
            pos = (a, b) if face == "lid" else _flat_pos(sheet, "cover", face, a, b)
        else:
            continue
        size = list(c["size"])
        if face in ("-X", "+X") and c["shape"] == "rect":
            pass  # along the wall is the flat's y, height its x: swap so the rectangle lies right
        out.append({"shape": c["shape"], "size": size, "at": pos, "radius": c.get("radius", 0.0),
                    "turn": face in ("-X", "+X"), "what": c.get("preset") or c["shape"]})
    return out


# RMFG's published limits (rmfg.com/docs: services/laser-cutting, services/bending, services/countersinking,
# services/powder-coating, shipping), in inches as they give them.
RMFG = {
    "max_flat": (60.0, 47.5), "laser_tol": 0.005, "bend_tol_per_line": 0.015, "angle_tol": 1.0, "max_bend_len": 60.0,
    "thickness": {"aluminium 5052": (0.032, 0.25), "steel (CRS)": (0.036, 0.135), "stainless 304": (0.031, 0.25)},
    "powder_min": {"aluminium 5052": 0.080, "steel (CRS)": 0.060, "stainless 304": 0.060},
    "taps": ("M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "M10", "M12"),
    "ship_box": (48.0, 30.0),
}
IN = 25.4


def rmfg_check(sheet: Sheet) -> list[dict]:
    """The design against RMFG's published sheet metal rules: what blocks a quote (error), what they
    flag (warning), and what to know (info)."""
    out = []

    def add(sev, rule, msg):
        out.append({"severity": sev, "rule": rule, "message": msg})

    t, R = sheet.thickness, sheet.R
    L, W, H = sheet.size
    f = flats(sheet)
    lo, hi = RMFG["thickness"][sheet.material]
    if not lo * IN - 0.01 <= t <= hi * IN + 0.01:
        add("error", "material", f"RMFG stocks {sheet.material} from {lo}\" to {hi}\" ({lo * IN:.2f} to {hi * IN:.2f} mm); "
                                 f"{t:g} mm is outside that")
    # Flat blank size.
    for k in ("base", "cover"):
        core, flaps = f[k]["core"], f[k]["flaps"]
        fx = core[0] + sum(sheet.BA + v[0] for e, v in flaps.items() if "x" in e)
        fy = core[1] + sum(sheet.BA + v[0] for e, v in flaps.items() if "y" in e)
        a, b = sorted((fx / IN, fy / IN), reverse=True)
        if a > RMFG["max_flat"][0] or b > RMFG["max_flat"][1]:
            add("error", "flat size", f"the {k}'s flat blank is {fx:.0f} x {fy:.0f} mm, over RMFG's 60\" x 47.5\" maximum")
    # Minimum flange: a fallback of 4 x thickness (the real minimum is the V-die opening / 2 plus its shoulder radius).
    for k, legs in (("base", [("end walls", t + H), ("lips", sheet.lip)]), ("cover", [("sides", 2 * t + H)])):
        for name, leg in legs:
            if leg < 4 * t:
                add("error", "flange length", f"the {k}'s {name} are {leg:.1f} mm, under 4 x thickness ({4 * t:.1f} mm), "
                                              "RMFG's fallback minimum flange")
    # U-channels: RMFG wants the base at least 3 x the flange height so the part clears the tooling.
    for k, base_w, flange, what in (("base", L + 2 * t, t + H, "floor between the end walls"),
                                    ("cover", W + 2 * t, 2 * t + H, "top between the sides")):
        if base_w < 3 * flange:
            add("warning", "U-channel", f"the {k} is a U with its {what} {base_w:.0f} mm across but flanges {flange:.0f} mm tall: RMFG "
                                       f"asks for the base to be at least 3 x the flange ({3 * flange:.0f} mm). Make the box lower, "
                                       "or build it from two L-shaped pieces, or check with RMFG for this part")
    # Features near bends: at least 2 x thickness + bend radius from a bend line.
    need = 2 * t + R
    for k in ("base", "cover"):
        core, flaps = f[k]["core"], f[k]["flaps"]
        for hole in _holes(sheet, k):
            x, y = hole["at"]
            r = (hole["size"][0] / 2) if hole["shape"] == "round" else max(hole["size"]) / 2
            for e in flaps:
                line = (core[0] if "x" in e else core[1]) / 2 + sheet.BA / 2
                pos = abs(x) if "x" in e else abs(y)
                same_side = (x if "x" in e else y) * (1 if e.startswith("+") else -1) > 0
                if same_side and abs(pos - line) - r < need - 1e-6:
                    add("error", "hole near a bend", f"{hole['what']} on the {k} is {max(abs(pos - line) - r, 0):.1f} mm from a bend "
                                                     f"line; RMFG needs {need:.1f} mm (2 x thickness + bend radius), and blocks the "
                                                     "order otherwise")
        # Smallest holes.
        for hole in _holes(sheet, k):
            m = min(hole["size"]) if hole["shape"] == "rect" else hole["size"][0]
            if m < 0.5 * t:
                add("warning", "small hole", f"{hole['what']} is {m:g} mm, under half the thickness: RMFG flags it (rough or undersize)")
            elif m < 1.5 * t:
                add("info", "small hole", f"{hole['what']} is {m:g} mm: RMFG cuts it, but 1.5 x thickness ({1.5 * t:g} mm) or more cuts best")
    if sheet.screw in RMFG["taps"]:
        add("info", "tapping", f"RMFG can tap the lips' {sheet.screw} holes for you (M2 to M12), instead of thread-forming screws; "
                               "taps, PEM nuts and countersinks can't sit inside a bend")
    pmin = RMFG["powder_min"][sheet.material]
    add("info", "powder coat", f"for powder coating: {sheet.material} at least {pmin}\" ({pmin * IN:.2f} mm)"
                               + (" (this part is thinner)" if t < pmin * IN - 0.01 else "") + ", and a hole of 2.2 mm or more to hang it")
    add("info", "tolerances", "RMFG holds ±0.005\" on laser-cut outlines, ±1° on bend angles, and ±0.015\" per bend line "
                              "(two parallel bends ±0.030\"); angles up to 90°, no hems")
    add("info", "flat pattern", "RMFG works out its own bend allowance for each material: the flat pattern here is a reference, "
                                "so send them the 3D STEP of each part")
    return out


def write(sheet: Sheet, folder) -> dict:
    """base_flat.dxf, cover_flat.dxf, enclosure_sheet.step and notes."""
    import ezdxf
    from build123d import export_step
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    f = flats(sheet)
    files = {}
    for which in ("base", "cover"):
        doc = ezdxf.new("R2010", setup=True)
        doc.units = ezdxf.units.MM
        for name, color in (("CUT", 7), ("BEND", 1), ("NOTES", 3)):
            doc.layers.add(name, color=color)
        doc.layers.get("BEND").dxf.linetype = "DASHED"
        msp = doc.modelspace()
        core, flaps = f[which]["core"], f[which]["flaps"]
        msp.add_lwpolyline(_outline(core, flaps, sheet.BA, 0), close=True, dxfattribs={"layer": "CUT"})
        for a, b in _bend_lines(core, flaps, sheet.BA):
            msp.add_line(a, b, dxfattribs={"layer": "BEND"})
        for hole in _holes(sheet, which):
            x, y = hole["at"]
            if hole["shape"] == "round":
                msp.add_circle((x, y), hole["size"][0] / 2, dxfattribs={"layer": "CUT"})
            else:
                w, h = hole["size"]
                if hole.get("turn"):
                    w, h = h, w
                msp.add_lwpolyline([(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)],
                                   close=True, dxfattribs={"layer": "CUT"})
        msp.add_text(f"{which.upper()}  {sheet.thickness:g} mm {sheet.material}  bends 90 deg UP, inside R {sheet.R:g}",
                     height=3, dxfattribs={"layer": "NOTES"}).set_placement((-core[0] / 2, 0))
        p = folder / f"{which}_flat.dxf"
        doc.saveas(p)
        files[f"{which}_dxf"] = str(p)
    made = formed(sheet)
    from build123d import Compound
    step = folder / "enclosure_sheet.step"
    export_step(Compound(children=[made["base"], made["cover"]]), str(step))
    files["step"] = str(step)
    notes = notes_for(sheet)
    rm = rmfg_check(sheet)
    lines = ["# Sheet metal enclosure", ""] + [f"- {n}" for n in notes] + ["", "## Against RMFG's rules", ""]
    lines += [f"- {r['severity']}: {r['rule']}: {r['message']}" for r in rm]
    (folder / "notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    from build123d import export_step as _es
    m2 = formed(sheet)
    _es(m2["base"], str(folder / "base_formed.step"))
    _es(m2["cover"], str(folder / "cover_formed.step"))
    files["notes"] = str(folder / "notes.md")
    return {"files": files, "notes": notes, "flats": {k: {"core": f[k]["core"]} for k in ("base", "cover")}}


def notes_for(sheet: Sheet) -> list[str]:
    sheet.check()
    L, W, H = sheet.size
    t = sheet.thickness
    f = flats(sheet)
    def span(k):
        core, flaps = f[k]["core"], f[k]["flaps"]
        ex = sum(sheet.BA + v[0] for e, v in flaps.items() if "x" in e)
        ey = sum(sheet.BA + v[0] for e, v in flaps.items() if "y" in e)
        return core[0] + ex, core[1] + ey
    b, c = span("base"), span("cover")
    return [f"{t:g} mm {sheet.material}, inside bend radius {sheet.R:g} mm, K-factor {sheet.K:g}: bend allowance {sheet.BA:.3f} mm per 90° bend",
            f"inside {L:g} x {W:g} x {H:g} mm; outside {L + 2 * t:g} x {W + 2 * t:g} x {H + 2 * t:g} mm",
            f"base flat {b[0]:.1f} x {b[1]:.1f} mm: the floor, end walls up and {sheet.lip:g} mm lips up along the sides",
            f"cover flat {c[0]:.1f} x {c[1]:.1f} mm: the top with its sides down; it slides on from above",
            f"{2 * sheet.screws_per_side} {sheet.screw} screws through the cover's sides into the lips (tap drill "
            f"{SCREW_TAP[sheet.screw]:g} mm for thread-forming screws, or put PEM nuts there instead)",
            "check the bend allowance against your shop's numbers: many publish their own K-factor or bend tables, and theirs win",
            "front and back (±Y) cutouts go in the cover's sides; end (±X) cutouts in the base's end walls"]


def formed(sheet: Sheet) -> dict:
    """The formed parts as solids (sharp corners: the bend radii are left out of the 3D)."""
    sheet.check()  # settles an automatic lip height first
    L, W, H = sheet.size
    t = sheet.thickness
    base = Box(L + 2 * t, W, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for s in (-1, 1):
        base += Pos(s * (L / 2 + t / 2), 0, 0) * Box(t, W, t + H, align=(Align.CENTER, Align.CENTER, Align.MIN))
        base += Pos(0, s * (W / 2 - t / 2), 0) * Box(L - 2 * sheet.thickness, t, sheet.lip, align=(Align.CENTER, Align.CENTER, Align.MIN))
    cover = Box(L + 2 * t, W + 2 * t, t, align=(Align.CENTER, Align.CENTER, Align.MIN)).locate(Location((0, 0, t + H)))
    for s in (-1, 1):
        cover += Pos(0, s * (W / 2 + t / 2), 0) * Box(L + 2 * t, t, 2 * t + H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    f = flats(sheet)
    z = f["screws"]["z"]
    for x in f["screws"]["x"]:
        for s in (-1, 1):
            base -= Pos(x, s * (W / 2 - t / 2), z) * Cylinder(SCREW_TAP[sheet.screw] / 2, 4 * t, rotation=(90, 0, 0))
            cover -= Pos(x, s * (W / 2 + t / 2), z) * Cylinder(SCREW_CLEAR[sheet.screw] / 2, 4 * t, rotation=(90, 0, 0))
    from .presets import expand, resolve
    for raw in expand(sheet.cutouts):
        c = resolve(dict(raw))
        face = {"left": "-X", "right": "+X", "front": "-Y", "back": "+Y"}.get(c["face"], c["face"])
        a, b = c.get("at", [0, 0])
        if c["shape"] == "round":
            tool = Cylinder(c["size"][0] / 2, 10 * t)
        else:
            tool = Box(c["size"][0], c["size"][1], 10 * t)
        if face == "floor":
            base -= Pos(a, b, 0) * tool
        elif face == "lid":
            cover -= Pos(a, b, t + H) * tool
        elif face in ("-X", "+X"):
            base -= Pos((1 if face == "+X" else -1) * (L / 2 + t / 2), a, t + b) * (Rot(0, 90, 0) * Rot(0, 0, 90) * tool)
        else:
            cover -= Pos(a, (1 if face == "+Y" else -1) * (W / 2 + t / 2), t + b) * (Rot(90, 0, 0) * tool)
    grams = (base.volume + cover.volume) / 1000 * MATERIALS[sheet.material]["density"]
    return {"base": base, "cover": cover, "grams": round(grams, 1)}
