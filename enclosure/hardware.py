"""Parametric hardware: screws, nuts, washers, spacers, springs and clips.

Each part comes in two modes:

- reference: the standard part at its standard size (ISO or ASME, from bd_warehouse's tables), to
  drop into an assembly. Threads are plain cylinders unless asked for, so assemblies stay fast.
- print: the same part made to be 3D printed. Threads are always modelled, with `clearance`
  taken off external threads and added to internal ones (radially); holes grow by the same amount.

`make(kind, **params)` returns {"shape", "notes", "checks", "info", "buy"}; `KINDS` lists the
kinds, their settings and defaults.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction

from build123d import (Align, Axis, Box, Cylinder, Edge, Location, Plane, Polygon, Pos, RegularPolygon, Rot,
                       Spline, Text, Torus, Wire, Circle, chamfer, extrude, fillet, sweep)

from .box import RAIL_T, RAIL_W, SCREWS, din_clip

# Materials for springs: shear modulus G and Young's modulus E in MPa, and the ultimate tensile
# strength fit Sut = A / d^m (MPa, d in mm), from Shigley's Mechanical Engineering Design, table 10-4/10-5.
WIRE = {
    "music": {"G": 81_700, "E": 203_400, "A": 2211, "m": 0.145, "name": "music wire (ASTM A228)"},
    "stainless": {"G": 69_600, "E": 193_000, "A": 1867, "m": 0.146, "name": "302 stainless (ASTM A313)"},
    "hard-drawn": {"G": 80_000, "E": 198_600, "A": 1783, "m": 0.190, "name": "hard-drawn steel (ASTM A227)"},
}
# Printed plastics: rough moduli for a 3D printed part (MPa), and a strain we'd let a snap beam
# reach once. These are rules of thumb, not datasheet figures: print the fit test and adjust.
PLASTIC = {"PLA": {"E": 3500, "strain": 0.015}, "PETG": {"E": 2100, "strain": 0.025},
           "ABS": {"E": 2200, "strain": 0.025}, "nylon": {"E": 1400, "strain": 0.04}}

SCREW_TYPES = {
    "socket": ("SocketHeadCapScrew", {"metric": "iso4762", "inch": "asme_b18.3"}, "socket head cap screw"),
    "button": ("ButtonHeadScrew", {"metric": "iso7380_1"}, "button head screw"),
    "flat": ("CounterSunkScrew", {"metric": "iso10642"}, "flat (countersunk) socket screw"),
    "hex": ("HexHeadScrew", {"metric": "iso4017"}, "hex head bolt, fully threaded"),
    "pan": ("PanHeadScrew", {"metric": "iso14583", "inch": "asme_b_18.6.3"}, "pan head screw"),
    "set": ("SetScrew", {"metric": "iso4026"}, "set screw"),
}
NUT_TYPES = {
    "hex": ("HexNut", {"metric": "iso4032"}, "hex nut"),
    "thin": ("HexNut", {"metric": "iso4035"}, "thin hex nut"),
    "square": ("SquareNut", {"metric": "din557"}, "square nut"),
    "flange": ("HexNutWithFlange", {"metric": "din1665"}, "flange nut"),
    "cap": ("DomedCapNut", {"metric": "din1587"}, "domed cap nut"),
}
WASHER_TYPES = {"plain": ("PlainWasher", "iso7089", "plain washer"),
                "small": ("PlainWasher", "iso7092", "small washer"),
                "large": ("PlainWasher", "iso7093", "large (fender) washer"),
                "heavy": ("PlainWasher", "iso7094", "heavy washer")}


def _fastener():
    import warnings
    warnings.filterwarnings("ignore")
    import bd_warehouse.fastener as f
    return f


def thread_size(size: str) -> tuple[str, float, float, str]:
    """(table size, major diameter mm, pitch mm, system) from M3, M3-0.5, #4-40, 1/4-20 or 1/4-28."""
    s = size.strip().replace(" ", "")
    m = re.fullmatch(r"[Mm](\d+(?:\.\d+)?)(?:[-x](\d+(?:\.\d+)?))?", s)
    if m:
        d = float(m.group(1))
        pitch = float(m.group(2)) if m.group(2) else COARSE.get(d)
        if pitch is None:
            raise ValueError(f"{size}: give the pitch too, like M{d:g}-1")
        return f"M{d:g}-{pitch:g}", d, pitch, "metric"
    m = re.fullmatch(r"(#\d+|\d+/\d+|\d+(?:\.\d+)?)-(\d+)", s)
    if m:
        body, tpi = m.group(1), int(m.group(2))
        if body.startswith("#"):
            d_in = 0.060 + 0.013 * int(body[1:])  # ASME B1.1 numbered sizes
        else:
            d_in = float(Fraction(body))
        return f"{body}-{tpi}", d_in * 25.4, 25.4 / tpi, "inch"
    raise ValueError(f"size {size!r}: write it like M3, M3-0.5, #4-40 or 1/4-20")


# ISO 261 coarse pitches.
COARSE = {1.6: 0.35, 2: 0.4, 2.5: 0.45, 3: 0.5, 3.5: 0.6, 4: 0.7, 5: 0.8, 6: 1.0, 8: 1.25, 10: 1.5, 12: 1.75,
          14: 2.0, 16: 2.0, 20: 2.5, 24: 3.0}


def _table(cls, ftype: str, size: str, d: float):
    """The size name bd_warehouse's table uses for this thread, or an error listing what it has."""
    sizes = cls.sizes(ftype)
    if size in sizes:
        return size
    short = [s for s in sizes if s.split("-")[0] == size.split("-")[0]]
    if short:
        return short[0]
    raise ValueError(f"{size} is not in the {ftype} table; it has {', '.join(sizes[:24])}")


def _thread(d, pitch, length, external, clearance, finishes):
    from bd_warehouse.thread import IsoThread
    return IsoThread(d, pitch, length, external=external, end_finishes=finishes,
                     manufacturing_compensation=clearance)


def _printed_thread_checks(d, pitch, checks):
    if d < 6:
        checks.append(f"printed threads under M6 come out rough on most FDM printers (this is {d:g} mm); "
                      "for small sizes a heat-set insert or a tapped hole is more reliable")
    if pitch < 0.8:
        checks.append(f"a {pitch:g} mm pitch is fine for a printer; a coarser pitch prints cleaner if this "
                      "doesn't have to mate with bought hardware")


def screw(size="M3", length=10.0, type="socket", mode="reference", threads=False, clearance=0.2, pitch=None):
    """A screw, its head above z = 0 and its shank down to -length."""
    f = _fastener()
    tsize, d, p, system = thread_size(size)
    if pitch:
        p = float(pitch)
    if type not in SCREW_TYPES:
        raise ValueError(f"screw type: one of {', '.join(SCREW_TYPES)}")
    cls_name, tables, label = SCREW_TYPES[type]
    if system not in tables:
        raise ValueError(f"{label}: {'metric' if system == 'inch' else 'inch'} sizes only")
    if not 1 <= length <= 300:
        raise ValueError("length: 1 to 300 mm")
    cls = getattr(f, cls_name)
    name = _table(cls, tables[system], tsize, d)
    notes, checks = [], []
    if mode == "reference":
        shape = cls(name, length, tables[system], simple=not threads)
        notes.append(f"{label} {name} x {length:g} mm, {tables[system].upper()}" + ("" if threads else ", threads shown plain"))
        return {"shape": shape, "notes": notes, "checks": checks,
                "info": {"major_d": d, "pitch": p, "length": length, "standard": tables[system]},
                "buy": f"{name} x {length:g} {label}"}
    # Printing: the standard head, a core and a thread made smaller by the clearance.
    plain = cls(name, length, tables[system], simple=True)
    head = plain & Box(60, 60, 60, align=(Align.CENTER, Align.CENTER, Align.MIN))
    th = _thread(d, p, length, True, clearance, ("chamfer", "square"))
    core = Cylinder(th.root_radius + 0.01, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    shank = Pos(0, 0, -length) * (core + th)
    shape = head + shank if head.volume > 0 else shank
    _printed_thread_checks(d, p, checks)
    notes.append(f"printed {label} {d:g} mm x {p:g} mm pitch x {length:g} mm, threads {clearance:g} mm undersize (radial); "
                 "print it standing on its head, with a brim for long ones")
    return {"shape": shape, "notes": notes, "checks": checks,
            "info": {"major_d": d, "pitch": p, "length": length, "clearance": clearance}, "buy": None}


def nut(size="M3", type="hex", mode="reference", threads=False, clearance=0.2, pitch=None):
    """A nut on z = 0, its axis along Z."""
    f = _fastener()
    tsize, d, p, system = thread_size(size)
    if pitch:
        p = float(pitch)
    if type not in NUT_TYPES:
        raise ValueError(f"nut type: one of {', '.join(NUT_TYPES)}")
    cls_name, tables, label = NUT_TYPES[type]
    notes, checks = [], []
    if system == "inch":
        # bd_warehouse has metric nuts only: an ASME B18.2.2 hex nut from its formulas.
        if type != "hex":
            raise ValueError("inch nuts: hex only")
        af, h = _inch_nut(d / 25.4)
        body = extrude(RegularPolygon(af * 25.4 / 2, 6, major_radius=False), amount=h * 25.4)
        height = h * 25.4
        if mode == "reference" and not threads:
            shape = body - Cylinder(d / 2, height * 3)
            notes.append(f"hex nut {tsize}: {af:.4g} in across flats, {h:.4g} in thick (ASME B18.2.2 / B18.6.3)")
            return {"shape": shape, "notes": notes, "checks": checks,
                    "info": {"major_d": d, "pitch": p, "height": height}, "buy": f"{tsize} hex nut"}
        plain = body
    else:
        cls = getattr(f, cls_name)
        name = _table(cls, tables["metric"], tsize, d)
        if mode == "reference":
            shape = cls(name, tables["metric"], simple=not threads)
            notes.append(f"{label} {name}, {tables['metric'].upper()}" + ("" if threads else ", threads shown plain"))
            return {"shape": shape, "notes": notes, "checks": checks,
                    "info": {"major_d": d, "pitch": p, "height": shape.bounding_box().size.Z, "standard": tables["metric"]},
                    "buy": f"{name} {label}"}
        plain = cls(name, tables["metric"], simple=True)
    bb = plain.bounding_box()
    plain = Pos(0, 0, -bb.min.Z) * plain
    height = bb.size.Z
    th = _thread(d, p, height, False, clearance, ("fade", "fade"))
    shape = (plain - Cylinder(d / 2 + clearance + 0.02, height * 3)) + th
    if mode == "print":
        _printed_thread_checks(d, p, checks)
        notes.append(f"printed {label} {d:g} mm x {p:g} mm pitch, thread {clearance:g} mm oversize (radial); print it flat")
    else:
        notes.append(f"{label} {tsize} with modelled threads")
    return {"shape": shape, "notes": notes, "checks": checks,
            "info": {"major_d": d, "pitch": p, "height": round(height, 3)}, "buy": None if mode == "print" else f"{tsize} {label}"}


def _inch_nut(d_in: float) -> tuple[float, float]:
    """Hex nut across flats and thickness, inches: ASME B18.6.3 machine screw nuts (#0 to #12) and
    ASME B18.2.2 hex nuts (1/4 to 3/4)."""
    table = {0.060: (5 / 32, 3 / 64), 0.086: (3 / 16, 1 / 16), 0.112: (1 / 4, 3 / 32), 0.125: (5 / 16, 7 / 64),
             0.138: (5 / 16, 7 / 64), 0.164: (11 / 32, 1 / 8), 0.190: (3 / 8, 1 / 8), 0.216: (7 / 16, 5 / 32),
             0.250: (7 / 16, 7 / 32), 0.3125: (1 / 2, 17 / 64), 0.375: (9 / 16, 21 / 64), 0.4375: (11 / 16, 3 / 8),
             0.500: (3 / 4, 7 / 16), 0.625: (15 / 16, 35 / 64), 0.750: (9 / 8, 41 / 64)}
    for k, v in table.items():
        if abs(k - d_in) < 0.002:
            return v
    raise ValueError("inch nut: #0, #2, #4, #5, #6, #8, #10, #12, or 1/4, 5/16, 3/8, 7/16, 1/2, 5/8, 3/4")


def washer(size="M3", type="plain", mode="reference", clearance=0.2, id=None, od=None, thickness=None):
    """A washer on z = 0. A standard size, or any id/od/thickness."""
    notes, checks = [], []
    if id and od and thickness:
        idd, odd, t = float(id), float(od), float(thickness)
        if not 0 < idd < odd or t <= 0:
            raise ValueError("washer: 0 < id < od, thickness above 0")
        label, std = f"washer {idd:g} x {odd:g} x {t:g} mm", None
    else:
        f = _fastener()
        if type not in WASHER_TYPES:
            raise ValueError(f"washer type: one of {', '.join(WASHER_TYPES)}")
        cls_name, table, label = WASHER_TYPES[type]
        cls = getattr(f, cls_name)
        name = size.split("-")[0]
        if name not in cls.sizes(table):
            raise ValueError(f"{name} {label}: the {table} table has {', '.join(cls.sizes(table))}; or give id, od and thickness")
        ref = cls(name, table)
        bb = ref.bounding_box()
        odd, t = bb.size.X, bb.size.Z
        # The inner diameter: the hole's circular edge on the top face.
        top = ref.faces().sort_by(Axis.Z)[-1]
        idd = min(w.bounding_box().size.X for w in top.inner_wires()) if top.inner_wires() else 0.0
        std = table
        label = f"{label} {name} ({table.upper()})"
        if mode == "reference":
            notes.append(f"{label}: {idd:g} x {odd:g} x {t:g} mm")
            return {"shape": Pos(0, 0, -bb.min.Z) * ref, "notes": notes, "checks": checks,
                    "info": {"id": round(idd, 3), "od": round(odd, 3), "thickness": round(t, 3), "standard": std},
                    "buy": f"{name} {WASHER_TYPES[type][2]}"}
    hole = idd + (2 * clearance if mode == "print" else 0.0)
    shape = Cylinder(odd / 2, t, align=(Align.CENTER, Align.CENTER, Align.MIN)) - Cylinder(hole / 2, t * 3)
    notes.append(f"{label}" + (f", hole {hole:g} mm for printing" if mode == "print" else ""))
    if mode == "print" and t < 0.8:
        checks.append(f"a {t:g} mm washer is only a few layers: print it at 0.1 mm layers, or make it thicker")
    return {"shape": shape, "notes": notes, "checks": checks,
            "info": {"id": round(hole, 3), "od": odd, "thickness": t}, "buy": None if mode == "print" else label}


def spacer(size="M3", length=10.0, shape="hex", bore="clearance", mode="reference", clearance=0.2, od=None):
    """A spacer or standoff on z = 0: round or hex, its bore a clearance hole, a thread
    (female both ends), or a heat-set insert pocket at each end."""
    _, d, p, system = thread_size(size)
    if not 1 <= length <= 200:
        raise ValueError("length: 1 to 200 mm")
    notes, checks = [], []
    key = f"M{d:g}" if system == "metric" else None
    # Across flats (hex) or diameter (round): common stock sizes; give od to change it.
    af = float(od) if od else {2: 4.0, 2.5: 5.0, 3: 5.5, 4: 7.0, 5: 8.0, 6: 10.0}.get(d, round(d * 1.8 * 2) / 2)
    if shape == "hex":
        body = extrude(RegularPolygon(af / 2, 6, major_radius=False), amount=length)
    elif shape == "round":
        body = Cylinder(af / 2, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    else:
        raise ValueError("spacer shape: hex or round")
    c = clearance if mode == "print" else 0.0
    if bore == "clearance":
        hole = (SCREWS[key][0] if key in SCREWS else d * 1.1) + 2 * c
        body -= Cylinder(hole / 2, length * 3)
        what = f"clearance hole Ø{hole:g}"
    elif bore == "thread":
        th_len = min(length / 2, 2.5 * d)
        body -= Cylinder(d / 2 + c + 0.02, length * 3)
        for z0, fin in ((0.0, ("fade", "square")), (length - th_len, ("square", "fade"))):
            body += Pos(0, 0, z0) * _thread(d, p, th_len, False, c, fin)
        what = f"threaded {d:g} x {p:g} both ends, {th_len:g} mm deep"
        if mode == "print":
            _printed_thread_checks(d, p, checks)
    elif bore == "insert":
        if key not in SCREWS:
            raise ValueError("insert pockets: M2 to M5")
        _, pilot, insert_d, depth, _ = SCREWS[key]
        body -= Cylinder(SCREWS[key][0] / 2, length * 3)
        for z in (0.0, length):
            body -= Pos(0, 0, z) * Cylinder(insert_d / 2, 2 * (depth + 0.5))
        what = f"heat-set insert pockets Ø{insert_d:g} x {depth + 0.5:g} both ends"
        if length < 2 * (depth + 0.5) + 1:
            checks.append("the two insert pockets meet in the middle: make it longer")
    else:
        raise ValueError("spacer bore: clearance, thread or insert")
    notes.append(f"{shape} spacer {af:g} mm {'across flats' if shape == 'hex' else 'across'} x {length:g} mm, {what}")
    if af - (d + 2 * c) < 1.6:
        checks.append("under 0.8 mm of wall round the bore: give it a bigger od")
    if mode == "print":
        buy = None
    elif bore == "thread":
        buy = f"{key or size} {shape} standoff {length:g} mm, female-female"
    else:
        buy = f"{shape} spacer {af:g} x {length:g} mm for {key or size}"
    return {"shape": body, "notes": notes, "checks": checks, "info": {"od": af, "length": length, "bore": bore}, "buy": buy}


def heat_set_insert(size="M3", maker="CNCKitchen"):
    """A heat-set insert, reference only (bd_warehouse's tables of several makers' inserts)."""
    f = _fastener()
    tsize, d, p, system = thread_size(size)
    if maker not in f.HeatSetNut.types():
        raise ValueError(f"insert maker: one of {', '.join(sorted(f.HeatSetNut.types()))}")
    sizes = [s for s in f.HeatSetNut.sizes(maker) if s.startswith(f"M{d:g}-")]
    if not sizes:
        raise ValueError(f"{maker} has no M{d:g} insert; it has {', '.join(f.HeatSetNut.sizes(maker))}")
    shape = f.HeatSetNut(sizes[0], maker, simple=True)
    bb = shape.bounding_box()
    return {"shape": Pos(0, 0, -bb.min.Z) * shape, "notes": [f"{maker} heat-set insert {sizes[0]}"], "checks": [],
            "info": {"size": sizes[0], "length": round(bb.size.Z, 3), "od": round(bb.size.X, 3)},
            "buy": f"{sizes[0]} heat-set insert ({maker})"}


# ---------- Springs ----------

def _coil(D: float, d: float, z_of, turns: float, steps_per_turn: int = 24):
    """Sweep the wire along a coil of mean diameter D whose height after t turns is z_of(t)."""
    n = max(int(turns * steps_per_turn), 8)
    pts = [(D / 2 * math.cos(2 * math.pi * turns * i / n), D / 2 * math.sin(2 * math.pi * turns * i / n),
            z_of(turns * i / n)) for i in range(n + 1)]
    path = Wire([Spline(*pts)])
    prof = Plane(origin=path @ 0, z_dir=path % 0) * Circle(d / 2)
    return sweep(prof, path, is_frenet=True), pts


def _wire_strength(d, wire):
    w = WIRE[wire]
    return w["A"] / d ** w["m"]


def _wahl(C):
    return (4 * C - 1) / (4 * C - 4) + 0.615 / C


def compression_spring(d=1.0, od=10.0, free_length=20.0, coils=8.0, wire="music", ends="closed-ground",
                       working_length=None, mode="reference", material="PETG"):
    """A compression spring standing on z = 0. *coils* is the total coil count; closed ends have
    one dead coil each. Rate, solid height and stress from Shigley ch. 10."""
    D = od - d
    C = D / d
    notes, checks = [], []
    if C < 3 or C > 16:
        checks.append(f"spring index D/d = {C:.1f}: 4 to 12 is easy to wind and works well; outside 3 to 16 it is hard to make")
    closed = ends in ("closed", "closed-ground")
    ground = ends == "closed-ground"
    na = coils - (2 if closed else 0)
    if na < 1:
        raise ValueError("coils: at least 3 with closed ends")
    solid = (coils if ground else coils + 1) * d
    if free_length <= solid + d:
        raise ValueError(f"free length {free_length:g} mm is at or under the solid height ({solid:.2f} mm): fewer coils or longer")
    # Coil path: dead coils at pitch d, active coils at the pitch that fills the free length.
    g = 0.5 * d if ground else 0.0  # ground ends: the wire's centre starts half a wire below the flat
    z0 = d / 2 - g
    z1 = free_length - d / 2 + g
    dead = 1.0 if closed else 0.0
    p_active = (z1 - z0 - 2 * dead * d) / na

    def z_of(t):
        if t <= dead:
            return z0 + d * t
        if t >= coils - dead:
            return z1 - d * (coils - t)
        return z0 + dead * d + p_active * (t - dead)

    body, _ = _coil(D, d, z_of, coils)
    if ground:
        body = body & Box(od * 2, od * 2, free_length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    if mode == "print":
        E = PLASTIC[material]["E"]
        G = E / (2 * 1.35)
        mat = f"printed {material} (rough)"
    else:
        G = WIRE[wire]["G"]
        mat = WIRE[wire]["name"]
    k = G * d ** 4 / (8 * D ** 3 * na)  # N/mm
    info = {"mean_d": round(D, 3), "index": round(C, 2), "active_coils": na, "pitch": round(p_active, 3),
            "solid_height": round(solid, 3), "rate_n_per_mm": round(k, 4), "force_at_solid_n": round(k * (free_length - solid), 2)}
    notes.append(f"compression spring, {mat}: wire {d:g} mm, OD {od:g} mm, free {free_length:g} mm, {coils:g} coils "
                 f"({na:g} active, {ends} ends); rate {k:.3g} N/mm ({k * 25.4 / 4.448:.3g} lbf/in), solid at {solid:.2f} mm")
    if mode == "reference":
        Sut = _wire_strength(d, wire)
        allow = 0.45 * Sut  # Shigley: static torsional limit without set removal
        tau_solid = _wahl(C) * 8 * k * (free_length - solid) * D / (math.pi * d ** 3)
        info.update({"sut_mpa": round(Sut), "allowable_mpa": round(allow), "stress_at_solid_mpa": round(tau_solid)})
        if tau_solid > allow:
            checks.append(f"closed solid it reaches {tau_solid:.0f} MPa, over the {allow:.0f} MPa this wire takes without "
                          "taking a set: it will shorten the first time it is squashed flat. Use a thicker wire or fewer coils")
        if working_length:
            F = k * (free_length - working_length)
            tau = _wahl(C) * 8 * F * D / (math.pi * d ** 3)
            info.update({"force_at_working_n": round(F, 2), "stress_at_working_mpa": round(tau)})
            notes.append(f"at {working_length:g} mm it pushes {F:.2f} N ({F / 4.448:.2f} lbf), {tau:.0f} MPa in the wire")
            if working_length < solid * 1.15:
                checks.append("the working length is within 15% of solid: leave more room between the coils")
        if free_length / D > 4:
            checks.append(f"free length is {free_length / D:.1f} x its diameter: over about 4 it can buckle, so run it over a rod or in a bore")
    else:
        checks.append("a printed spring is weak and creeps under load: good for a prototype's feel, not for keeping force")
        notes.append("print it standing up, slowly, with no supports")
    return {"shape": body, "notes": notes, "checks": checks, "info": info,
            "buy": None if mode == "print" else f"compression spring {d:g} wire x {od:g} OD x {free_length:g} free, {mat}"}


def extension_spring(d=1.0, od=8.0, body_length=20.0, wire="music", mode="reference", material="PETG"):
    """A close-wound extension spring along Z with a full loop at each end (machine loops)."""
    D = od - d
    C = D / d
    nb = max(round(body_length / d - 1, 2), 2.0)
    notes, checks = [], []
    body, pts = _coil(D, d, lambda t: d / 2 + d * 1.03 * t, nb)  # a hair over close-wound, so the coils don't fuse
    top_z = pts[-1][2]

    # Crossover centre loops: a bar from each end of the coil to the axis, and a full loop standing on it.
    r = D / 2
    extra = []
    for (x, y, z), up in ((pts[0], False), (pts[-1], True)):
        phi = math.atan2(y, x)
        # The bar meets the wire a little back from its cut end, so their surfaces don't just touch.
        back = 0.3 * d * (1 if not up else -1)
        bx, by = -math.sin(phi) * back, math.cos(phi) * back
        extra.append(Pos(x / 2 + bx, y / 2 + by, z) * (Rot(0, 0, math.degrees(phi)) * Cylinder(0.55 * d, r + d / 2, rotation=(0, 90, 0))))
        # The loop stands across the bar (not along it), so the two tubes cross instead of running together.
        # The bar is a little fatter than the wire (as a bend is): two equal tubes crossing are a
        # degenerate case for the boolean.
        extra.append(Pos(0, 0, z + (r if up else -r)) * (Rot(0, 0, math.degrees(phi)) * Torus(r, d / 2, rotation=(0, 90, 0))))
    shape = body.fuse(*extra)
    start = pts[0]
    G = WIRE[wire]["G"] if mode == "reference" else PLASTIC[material]["E"] / 2.7
    E = WIRE[wire]["E"] if mode == "reference" else PLASTIC[material]["E"]
    na = nb + G / E  # Shigley eq. 10-39: the loops add G/E of a coil
    k = G * d ** 4 / (8 * D ** 3 * na)
    length = top_z - start[2] + 2 * D + d
    notes.append(f"extension spring: wire {d:g} mm, OD {od:g} mm, body {top_z - start[2] + d:.2f} mm ({nb:g} coils), about "
                 f"{length:.1f} mm over the loops; rate {k:.3g} N/mm after its initial tension")
    checks.append("the loops are the weak spot: the bend where each loop meets the body sees more stress than the coils")
    if mode == "print":
        checks.append("a printed extension spring is fragile at the loops: a prototype only")
    return {"shape": shape, "notes": notes, "checks": checks,
            "info": {"mean_d": round(D, 3), "index": round(C, 2), "body_coils": nb, "rate_n_per_mm": round(k, 4),
                     "length_over_loops": round(length, 2)},
            "buy": None if mode == "print" else f"extension spring {d:g} wire x {od:g} OD, body {body_length:g}"}


def torsion_spring(d=1.0, od=10.0, coils=5.0, leg=15.0, angle=90.0, wire="music", mode="reference", material="PETG"):
    """A close-wound torsion spring along Z with straight tangent legs *angle* degrees apart."""
    D = od - d
    C = D / d
    turns = math.floor(coils) + angle / 360.0
    body, pts = _coil(D, d, lambda t: d / 2 + d * 1.05 * t, turns)
    legs = []
    a0 = 0.0
    a1 = 2 * math.pi * turns
    for a, (x, y, z), sign in ((a0, pts[0], -1), (a1, pts[-1], 1)):
        tx, ty = -math.sin(a) * sign, math.cos(a) * sign  # along the tangent, away from the body
        mid = (x + tx * (leg - d) / 2, y + ty * (leg - d) / 2, z)  # it starts a wire's width back inside the coil
        rod = Cylinder(d / 2, leg + d, rotation=(0, 90, 0))
        rod = Rot(0, 0, math.degrees(math.atan2(ty, tx))) * rod
        legs.append(Pos(*mid) * rod)
    shape = body.fuse(*legs)  # one boolean: adding them one at a time can leave a leg loose
    E = WIRE[wire]["E"] if mode == "reference" else PLASTIC[material]["E"]
    na = turns + 2 * leg / (3 * math.pi * D)  # Shigley eq. 10-49: the legs add a little
    k = E * d ** 4 / (64 * D * na)  # N·mm per radian
    notes = [f"torsion spring: wire {d:g} mm, OD {od:g} mm, {turns:.2f} body turns, legs {leg:g} mm {angle:g}° apart; "
             f"rate {k * math.pi / 180:.3g} N·mm per degree ({k:.3g} N·mm/rad)"]
    checks = ["it winds tighter as it is loaded: its inside diameter shrinks, so leave room on the arbor"]
    info = {"mean_d": round(D, 3), "index": round(C, 2), "turns": round(turns, 3), "rate_nmm_per_deg": round(k * math.pi / 180, 4)}
    if mode == "reference":
        Sut = _wire_strength(d, wire)
        info["max_moment_nmm"] = round(0.78 * Sut * math.pi * d ** 3 / 32 / ((4 * C ** 2 - C - 1) / (4 * C * (C - 1))), 1)
        notes.append(f"it takes about {info['max_moment_nmm']:g} N·mm before the wire yields (0.78 Sut, Shigley)")
    return {"shape": shape, "notes": notes, "checks": checks, "info": info,
            "buy": None if mode == "print" else f"torsion spring {d:g} wire x {od:g} OD, {turns:.2f} turns, {angle:g}° legs"}


# ---------- Clips ----------

def snap_hook(length=12.0, thickness=1.6, width=6.0, undercut=1.0, entry_angle=30.0, retention_angle=90.0,
              material="PETG", friction=0.3):
    """A cantilever snap hook (the beam along X, the hook up), with its strain and forces worked out
    the way the Bayer snap-fit guide does for a straight beam of constant section."""
    L, t, b, y = length, thickness, width, undercut
    if not 0 < entry_angle < 80 or not 0 < retention_angle <= 90:
        raise ValueError("entry angle 0 to 80°, retention angle 0 to 90°")
    run_in = y / math.tan(math.radians(entry_angle))
    run_back = y / math.tan(math.radians(retention_angle)) if retention_angle < 89.9 else 0.0
    flat = 0.5
    x_top = L - run_in
    x_back = x_top - flat
    if x_back - run_back < 0.4 * L:
        raise ValueError("the hook takes up most of the beam: make the beam longer or the undercut smaller")
    base = 4.0
    pts = [(-base, -base), (0, -base), (0, 0), (L, 0), (L, t), (x_top, t + y), (x_back, t + y), (x_back - run_back, t), (0, t), (-base, t)]
    prof = Plane.XZ * Polygon(*pts, align=None)
    shape = extrude(prof, amount=-b)
    shape = Pos(0, -b / 2, 0) * shape if shape.bounding_box().min.Y > -1e-6 else Pos(0, b / 2, 0) * shape
    E, limit = PLASTIC[material]["E"], PLASTIC[material]["strain"]
    strain = 1.5 * t * y / L ** 2
    P = b * t ** 2 / 6 * E * strain / L  # the force to bend it the undercut, N
    mu = friction
    def push(angle):
        a = math.tan(math.radians(angle))
        return P * (mu + a) / (1 - mu * a) if mu * a < 1 else float("inf")
    W_in, W_out = push(entry_angle), push(retention_angle) if retention_angle < 89.9 else float("inf")
    notes = [f"snap hook {L:g} mm long, {t:g} mm thick, {b:g} mm wide, {y:g} mm undercut: {strain * 100:.2f}% strain at the root, "
             f"{P:.2f} N to bend it, about {W_in:.2f} N to push on"
             + (f", {W_out:.2f} N to pull off" if W_out != float('inf') else ", it does not pull off (90° face): press the hook to release")]
    checks = []
    if strain > limit:
        checks.append(f"{strain * 100:.2f}% strain is over the {limit * 100:g}% we'd allow for printed {material} "
                      f"(a rule of thumb): make the beam longer ({math.sqrt(1.5 * t * y / limit):.1f} mm), thinner, or the undercut smaller")
    notes.append("print it on its side so the layers run along the beam, not across it")
    return {"shape": shape, "notes": notes, "checks": checks,
            "info": {"strain_pct": round(strain * 100, 3), "deflection_force_n": round(P, 3), "mating_force_n": round(W_in, 3),
                     "separation_force_n": None if W_out == float("inf") else round(W_out, 3),
                     "catch": f"a ledge {y:g} mm deep, {L - x_back + run_back:.2f} mm from the beam's tip"},
            "buy": None}


def cable_clip(cable_d=6.0, screw="M3", wall=1.6, width=8.0, opening=0.75):
    """A snap-in cable clip on a screw-down foot: a C ring the cable presses into."""
    if screw not in SCREWS:
        raise ValueError(f"screw: one of {', '.join(SCREWS)}")
    r_in = cable_d / 2
    r_out = r_in + wall
    clear, _, _, _, head = SCREWS[screw]
    foot_l = 2 * r_out + head + 6
    t = max(wall, 2.0)
    foot = Box(foot_l, width, t, align=(Align.MIN, Align.CENTER, Align.MIN))
    cx = r_out
    ring = Pos(cx, 0, t + r_in) * (Rot(90, 0, 0) * (Cylinder(r_out, width) - Cylinder(r_in, width + 1)))
    gap = opening * cable_d
    ring -= Box(gap, width + 2, r_out * 2, align=(Align.CENTER, Align.CENTER, Align.MIN)).locate(Location((cx, 0, t + r_in)))
    shape = foot + ring
    shape -= Pos(cx, 0, t + r_in) * (Rot(90, 0, 0) * Cylinder(r_in, width + 1))
    hx = 2 * r_out + head / 2 + 3
    shape -= Pos(hx, 0, 0) * Cylinder(clear / 2, t * 3)
    return {"shape": shape, "checks": [] if wall >= 1.2 else ["a wall under 1.2 mm may crack when the cable goes in"],
            "notes": [f"cable clip for Ø{cable_d:g} mm cable, {gap:.1f} mm opening to press it in, {screw} clearance hole; "
                      "print it standing on its foot"],
            "info": {"opening": round(gap, 2), "length": round(foot_l, 2)}, "buy": None}


def tie_mount(tie_width=4.8, tie_thickness=1.3, screw="M3", size=20.0):
    """A cable-tie mount: a square pad with a tunnel for the tie and a screw hole through the middle."""
    if screw not in SCREWS:
        raise ValueError(f"screw: one of {', '.join(SCREWS)}")
    pad_t, cl = 2.0, 0.3
    tw, th = tie_width + 2 * cl, tie_thickness + 2 * cl
    block_h = pad_t + th + 1.6
    shape = Box(size, size, pad_t, align=(Align.CENTER, Align.CENTER, Align.MIN))
    shape += Box(tw + 4, size, block_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    shape -= Box(size * 2, tw, th, align=(Align.CENTER, Align.CENTER, Align.MIN)).locate(Location((0, 0, pad_t)))
    clear = SCREWS[screw][0]
    shape -= Cylinder(clear / 2, block_h * 3)
    return {"shape": shape, "checks": [], "info": {"tunnel": [round(tw, 2), round(th, 2)]}, "buy": None,
            "notes": [f"tie mount {size:g} mm square for ties up to {tie_width:g} x {tie_thickness:g} mm, {screw} hole; print flat"]}


def board_clip(board_thickness=1.6, height=5.0, grip=2.5, screw="M3", length=10.0, clearance=0.15):
    """A clip that holds a board's edge: a foot with a screw hole and an upright with a slot
    for the board *height* mm above the foot."""
    if screw not in SCREWS:
        raise ValueError(f"screw: one of {', '.join(SCREWS)}")
    clear, _, _, _, head = SCREWS[screw]
    t = 2.0
    slot = board_thickness + 2 * clearance
    up_w = grip + 2.5
    up_h = height + slot + 2.0
    foot_w = up_w + head + 4
    shape = Box(foot_w, length, t, align=(Align.MIN, Align.CENTER, Align.MIN))
    shape += Box(up_w, length, t + up_h, align=(Align.MIN, Align.CENTER, Align.MIN))
    shape -= Box(grip, length * 2, slot, align=(Align.MIN, Align.CENTER, Align.MIN)).locate(Location((up_w - grip, 0, t + height)))
    shape -= Pos(up_w + (foot_w - up_w) / 2, 0, 0) * Cylinder(clear / 2, t * 3)
    return {"shape": shape, "checks": [], "info": {"slot": round(slot, 3)}, "buy": None,
            "notes": [f"board edge clip: {slot:.2f} mm slot {grip:g} mm deep, the board's underside {height:g} mm above the foot; "
                      "use one each side, slide the board in"]}


def din_rail_clip(length=40.0, thickness=3.0, screw="M3"):
    """A TS35 DIN rail clip as its own part: a plate with two screw holes for whatever it carries."""
    if screw not in SCREWS:
        raise ValueError(f"screw: one of {', '.join(SCREWS)}")
    w = RAIL_W + 12
    plate = Box(length, w, thickness, align=(Align.CENTER, Align.CENTER, Align.MIN))
    shape = plate + din_clip(length)
    clear = SCREWS[screw][0]
    for x in (-length / 2 + 5, length / 2 - 5):
        shape -= Pos(x, 0, 0) * Cylinder(clear / 2, 20)
    return {"shape": shape, "checks": [], "info": {"rail": f"TS35 x {RAIL_T:g}"}, "buy": None,
            "notes": [f"DIN rail clip {length:g} mm long, {screw} holes {length - 10:g} mm apart; hook on +Y, latch on -Y; print a test first"]}


# ---------- Gears, pulleys, knobs, caps, hinges, latches ----------

def _bore(shape, height, bore: str, d: float, set_screw: str | None, z0: float = -1.0):
    """Cut a shaft bore up Z from z0 for *height*: round or D-flat (a 6 mm shaft's flat at 4.5 mm,
    others at 0.75 x d), with an optional set screw across it halfway up (tap size hole)."""
    if bore == "none":
        return shape
    tool = Cylinder(d / 2, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    if bore == "d":
        flat = 4.5 + (d - 6.0) if abs(d - 6.0) < 0.6 else round(d * 0.75, 2)  # across the flat, with the clearance
        tool -= Box(d * 2, d, height * 3).locate(Location((0, flat, height / 2)))  # removes y > flat - d / 2
    elif bore != "round":
        raise ValueError("bore: round, d (D-flat) or none")
    shape = shape - Pos(0, 0, z0) * tool
    if set_screw:
        c = SCREWS[set_screw][1] if set_screw in SCREWS else 2.5
        shape -= Pos(0, -30, z0 + height / 2) * Cylinder(c / 2, 60, rotation=(90, 0, 0))
    return shape


def spur_gear(module=1.0, teeth=20, thickness=6.0, pressure_angle=20.0, bore="round", bore_d=5.0, hub=0.0,
              set_screw=None, clearance=0.15):
    """A spur gear (involute teeth, bd_warehouse), lying on z = 0, with a bore and an optional hub.
    Two gears mesh at (teeth1 + teeth2) x module / 2 apart."""
    from bd_warehouse.gear import SpurGear
    if not 6 <= int(teeth) <= 300 or not 0.3 <= module <= 10:
        raise ValueError("teeth 6 to 300, module 0.3 to 10")
    g = SpurGear(module, int(teeth), pressure_angle, thickness)
    g = Pos(0, 0, thickness / 2) * g
    total = thickness
    if hub > 0:
        hub_d = max(bore_d * 2, bore_d + 6)
        if hub_d > 2 * g.root_radius:
            raise ValueError("the hub is bigger than the gear's teeth' roots: a smaller hub or a bigger gear")
        g += Pos(0, 0, thickness) * Cylinder(hub_d / 2, hub, align=(Align.CENTER, Align.CENTER, Align.MIN))
        total += hub
    g = _bore(g, total + 2, bore, bore_d + 2 * clearance, set_screw)
    pd = module * teeth
    checks = []
    if teeth < 17 and pressure_angle == 20:
        checks.append(f"under 17 teeth at 20°, involute teeth are undercut at the root: fine for printing, weaker")
    if module < 0.8:
        checks.append("teeth under module 0.8 are small for FDM: print with a 0.25 mm nozzle or go up a module")
    return {"shape": g, "checks": checks,
            "notes": [f"spur gear: {int(teeth)} teeth, module {module:g} ({pressure_angle:g}° pressure angle), pitch diameter "
                      f"{pd:g} mm, outside {pd + 2 * module:g} mm, {thickness:g} mm thick; two gears mesh with their centres "
                      f"(teeth1 + teeth2) x {module:g} / 2 mm apart, plus about 0.1 mm for printed backlash"],
            "info": {"pitch_d": pd, "outside_d": pd + 2 * module, "root_d": round(pd - 2.5 * module, 3), "module": module,
                     "teeth": int(teeth)},
            "buy": None}


GT2_PITCH = 2.0


def gt2_pulley(teeth=20, belt_width=6.0, bore="round", bore_d=5.0, flanges=True, hub=7.0, set_screw="M3"):
    """A GT2 (2 mm pitch) timing pulley. Its pitch diameter is teeth x 2 / pi; the outside is 0.508 mm
    smaller (the belt's pitch line sits 0.254 mm out). The groove is a round-bottomed stand-in for
    Gates' GT2 profile, 0.75 mm deep: close enough to print and run, not a moulded profile."""
    n = int(teeth)
    if not 10 <= n <= 120:
        raise ValueError("teeth: 10 to 120")
    pd = n * GT2_PITCH / math.pi
    od = pd - 0.508
    width = belt_width + 1.0
    body = Cylinder(od / 2, width, align=(Align.CENTER, Align.CENTER, Align.MIN))
    groove = Cylinder(0.555, width * 3, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    groove += Box(1.11, 1.0, width * 3).locate(Location((0, 0.5, 0)))
    r_g = od / 2 - 0.75 + 0.555
    for i in range(n):
        a = 360 * i / n
        body -= Rot(0, 0, a) * Pos(0, r_g, width / 2) * groove
    z = 0.0
    shape = body
    if flanges:
        fd = od + 3.0
        shape = Cylinder(fd / 2, 1.0, align=(Align.CENTER, Align.CENTER, Align.MIN)) + Pos(0, 0, 1.0) * shape
        shape += Pos(0, 0, 1.0 + width) * Cylinder(fd / 2, 1.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        z = 2.0 + width
    else:
        z = width
    if hub > 0:
        hub_d = max(bore_d + 7, min(od - 1, 16))
        shape += Pos(0, 0, z) * Cylinder(hub_d / 2, hub, align=(Align.CENTER, Align.CENTER, Align.MIN))
    total = z + hub
    shape = _bore(shape, total + 2, bore, bore_d + 0.3, None)
    if set_screw and hub > 0:
        c = SCREWS[set_screw][1]
        shape -= Pos(0, -20, z + hub / 2) * Cylinder(c / 2, 40, rotation=(90, 0, 0))
    return {"shape": shape, "checks": [] if n >= 16 else ["under 16 teeth, a GT2 belt wraps too tightly to last"],
            "notes": [f"GT2 pulley, {n} teeth: pitch diameter {pd:.2f} mm, outside {od:.2f} mm, for a {belt_width:g} mm belt, "
                      f"bore {bore_d:g} mm" + (f", {set_screw} set screw in the hub (tap size hole)" if set_screw and hub > 0 else "")],
            "info": {"pitch_d": round(pd, 3), "outside_d": round(od, 3), "mm_per_turn": n * GT2_PITCH}, "buy": None}


def knob(diameter=20.0, height=15.0, shaft="d", shaft_d=6.0, depth=10.0, grip=24, pointer=True, set_screw=None, clearance=0.1):
    """A knob for a pot or encoder shaft: a D-shaft (6 mm with a 4.5 mm flat), round with a set screw,
    or knurled (18 splines, pressed on). Grip ridges round it and a pointer line on top."""
    if depth >= height - 1.5:
        raise ValueError("the shaft hole must stop at least 1.5 mm under the top")
    k = Cylinder(diameter / 2, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    try:
        k = chamfer(k.edges().sort_by(Axis.Z)[-1], min(1.0, height / 10))
    except Exception:
        pass
    if grip:
        rib = Cylinder(0.6, height * 3)
        for i in range(int(grip)):
            k -= Rot(0, 0, 360 * i / grip) * Pos(diameter / 2 + 0.2, 0, 0) * rib
    if pointer:
        k -= Pos(0, diameter / 4, height) * Box(1.0, diameter / 2 - 1.5, 1.2)
    sd = shaft_d + 2 * clearance
    if shaft == "d":
        k = _bore(k, depth + 0.01, "d", sd, None, z0=-0.01)
    elif shaft == "round":
        k = _bore(k, depth + 0.01, "round", sd, None, z0=-0.01)
        set_screw = set_screw or "M3"
    elif shaft == "knurled":
        k -= Pos(0, 0, -0.01) * Cylinder(shaft_d / 2 - 0.15, depth + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    else:
        raise ValueError("shaft: d, round or knurled")
    if set_screw:
        c = SCREWS[set_screw][1]
        k -= Pos(0, -diameter / 2, depth / 2) * Cylinder(c / 2, diameter, rotation=(90, 0, 0))
    return {"shape": k, "checks": [],
            "notes": [f"knob Ø{diameter:g} x {height:g} mm for a {shaft_d:g} mm {shaft} shaft, {depth:g} mm deep"
                      + (f", {set_screw} set screw (tap size hole)" if set_screw else "") + "; print it upside down (top on the bed)"],
            "info": {"hole": round(sd if shaft != "knurled" else shaft_d - 0.3, 3)}, "buy": None}


def button_cap(diameter=10.0, height=6.0, stem_d=3.5, stem_depth=2.5, panel=2.0, flange=1.5, clearance=0.1):
    """A cap for a tactile switch, through a hole in a panel: the round top, a flange under the panel
    so it can't fall out, and a socket for the switch's round actuator."""
    top_h = height
    cap = Cylinder(diameter / 2, top_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    try:
        cap = fillet(cap.edges().sort_by(Axis.Z)[-1], min(1.0, diameter / 6))
    except Exception:
        pass
    fl = Cylinder(diameter / 2 + flange, 1.2, align=(Align.CENTER, Align.CENTER, Align.MAX))
    shape = cap + fl
    shape -= Pos(0, 0, -1.2) * Cylinder(stem_d / 2 + clearance, stem_depth * 2)
    hole = diameter + 0.4
    return {"shape": shape, "checks": [] if height > panel + 1 else ["the cap barely clears the panel: make it taller"],
            "notes": [f"button cap Ø{diameter:g} mm standing {height - panel:g} mm proud of a {panel:g} mm panel; cut a "
                      f"Ø{hole:g} mm hole (a round cutout on the lid); flange Ø{diameter + 2 * flange:g} mm inside; "
                      f"socket Ø{stem_d + 2 * clearance:g} mm for the switch's actuator"],
            "info": {"panel_hole": hole, "proud": height - panel}, "buy": None}


def hinge(length=40.0, leaf_width=15.0, thickness=2.5, knuckles=5, pin="filament", screw="M3", clearance=0.3):
    """A two-leaf hinge, printed flat as two parts side by side: knuckles along X, a pin of 1.75 mm
    filament or an M3 screw, and two countersunk-free screw holes in each leaf."""
    n = int(knuckles)
    if n < 3 or n % 2 == 0:
        raise ValueError("knuckles: an odd number, 3 or more")
    rk = thickness / 2 + 1.2
    pin_d = 1.75 + 0.35 if pin == "filament" else 3.4
    if 2 * rk < pin_d + 1.6:
        rk = (pin_d + 1.6) / 2
    seg = (length - (n - 1) * clearance) / n
    clear, _, _, _, head = SCREWS[screw]
    leaves = []
    for side in (0, 1):
        leaf = Box(length, leaf_width, thickness, align=(Align.CENTER, Align.MIN, Align.MIN))
        for i in range(n):
            if i % 2 != side:
                continue
            x0 = -length / 2 + i * (seg + clearance)
            leaf += Pos(x0 + seg / 2, 0, rk) * Cylinder(rk, seg, rotation=(0, 90, 0))
            leaf += Box(seg, rk, rk, align=(Align.CENTER, Align.MIN, Align.MIN)).locate(Location((x0 + seg / 2, 0, 0)))
        # Keep the other leaf's knuckles free: cut their room (plus clearance) out of this leaf.
        for i in range(n):
            if i % 2 == side:
                continue
            x0 = -length / 2 + i * (seg + clearance)
            leaf -= Pos(x0 + seg / 2, 0, rk) * Cylinder(rk + clearance, seg + 2 * clearance, rotation=(0, 90, 0))
        leaf -= Pos(0, 0, rk) * Cylinder(pin_d / 2, length * 2, rotation=(0, 90, 0))
        for x in (-length / 3, length / 3):
            leaf -= Pos(x, leaf_width - head / 2 - 2, 0) * Cylinder(clear / 2, thickness * 4)
        leaf = Pos(0, -rk, 0) * leaf  # the pin on y = 0
        leaves.append(leaf if side == 0 else Rot(0, 0, 180) * leaf)
    a, b = leaves
    b = Pos(0, -(2 * leaf_width + 6), 0) * b  # laid out apart on the bed
    shape = a + b
    return {"shape": shape, "checks": [],
            "notes": [f"hinge {length:g} mm long, leaves {leaf_width:g} mm, {n} knuckles Ø{2 * rk:.1f}, pin "
                      + ("1.75 mm filament (melt the ends)" if pin == "filament" else f"an M3 x {length + 4:.0f} screw and nut")
                      + f"; {screw} holes in each leaf; printed as two parts, flat"],
            "info": {"knuckle_d": round(2 * rk, 2), "pin_hole": pin_d}, "buy": None}


def latch(width=10.0, reach=8.0, undercut=1.2, thickness=1.8, material="PETG"):
    """A snap latch with a finger tab, and its keeper (a ledge to glue or screw on), side by side."""
    hook = snap_hook(length=reach + 6, thickness=thickness, width=width, undercut=undercut, entry_angle=35,
                     retention_angle=80, material=material)
    shape = hook["shape"]
    L = reach + 6
    shape += Box(6, width, thickness, align=(Align.MIN, Align.CENTER, Align.MIN)).locate(Location((L, 0, 0)))  # finger tab
    keeper = Box(width + 6, 6, undercut + 2.5, align=(Align.CENTER, Align.CENTER, Align.MIN))
    keeper = Pos(L / 2, width + 10, 0) * keeper
    shape += keeper
    return {"shape": shape, "checks": hook["checks"],
            "notes": [f"latch {width:g} mm wide with a finger tab: lift the tab to open; the keeper's ledge is "
                      f"{undercut + 2.5:g} mm tall, {width + 6:g} mm long, for the hook's {undercut:g} mm catch"] + hook["notes"][:1],
            "info": hook["info"], "buy": None}


def test_print(size="M8", clearances="0.1,0.15,0.2,0.25,0.3", hooks="0.6,1.0,1.4", material="PETG"):
    """Find your printer's settings once: a strip of threaded holes at several clearances with a bolt
    for each (the number on the strip and on each bolt's head), and snap hooks of three undercuts
    with a plate to snap through."""
    _, d, p, _ = thread_size(size)
    cs = [float(c) for c in str(clearances).split(",") if c.strip()]
    us = [float(u) for u in str(hooks).split(",") if u.strip()]
    if not 1 <= len(cs) <= 6 or not 0 <= len(us) <= 4:
        raise ValueError("1 to 6 clearances and up to 4 hook undercuts")
    pitch_x = d * 2 + 6
    t = max(6.0, d * 0.8)
    strip = Box(pitch_x * len(cs), d * 2 + 10, t, align=(Align.MIN, Align.CENTER, Align.MIN))
    threads = []
    for i, c in enumerate(cs):
        x = pitch_x * (i + 0.5)
        strip -= Pos(x, -2, 0) * Cylinder(d / 2 + c + 0.02, t * 3)
        threads.append(Pos(x, -2, 0) * _thread(d, p, t, False, c, ("fade", "fade")))
        strip -= Pos(x, d + 2.5, t - 0.6) * extrude(Text(f"{c:g}", 3.0, align=(Align.CENTER, Align.CENTER)), amount=0.6)
    pieces = [strip.fuse(*threads)]  # one boolean for all the threads: much quicker than one at a time
    for i, c in enumerate(cs):
        b = screw(size, length=t + 2, type="hex" if d >= 5 else "socket", mode="print", clearance=c)["shape"]
        b = Rot(180, 0, 0) * b  # head down, as it prints
        bb = b.bounding_box()
        pieces.append(Pos(pitch_x * (i + 0.5) - (bb.min.X + bb.max.X) / 2, -(d * 2 + 10) / 2 - 4 - bb.max.Y, -bb.min.Z) * b)
    notes = [f"{size} threads at clearances {', '.join(f'{c:g}' for c in cs)} mm: each hole has its number beside it, "
             f"each bolt is in line with its hole. Try each bolt in its hole; the smallest number that turns by hand "
             f"is your printer's clearance (use it for parts printed for printing)"]
    if us:
        # Hooks, and a plate with a slot for each to snap through.
        y0 = d * 2 + 20
        hb, ht, plate_t, L = 6.0, 1.6, 2.0, 12.0
        plate = Box(len(us) * 14 + 6, 10, plate_t, align=(Align.MIN, Align.MIN, Align.MIN)).locate(Location((0, y0, 0)))
        for j, u in enumerate(us):
            x = 6 + j * 14 + 1
            plate -= Box(hb + 0.4, ht + 0.3, plate_t * 3).locate(Location((x, y0 + 5, 0)))
            plate -= Pos(x, y0 + 8.6, plate_t - 0.4) * extrude(Text(f"{u:g}", 2.0, align=(Align.CENTER, Align.CENTER)), amount=0.6)
            hk = Rot(90, 0, 0) * snap_hook(length=L, thickness=ht, width=hb, undercut=u, material=material)["shape"]
            bb = hk.bounding_box()
            pieces.append(Pos(x - (bb.min.X + bb.max.X) / 2, y0 + 16 - bb.min.Y, -bb.min.Z) * hk)
        pieces.append(plate)
        notes.append(f"snap hooks with {', '.join(f'{u:g}' for u in us)} mm undercuts (the number by each slot): push each "
                     "through its slot in the plate; pick the biggest that goes in without cracking and holds")
    from build123d import Compound
    shape = Compound(children=pieces)
    return {"shape": shape, "checks": [], "notes": notes, "info": {"clearances": cs, "hook_undercuts": us}, "buy": None}


# ---------- Registry ----------

KINDS = {
    "screw": (screw, "Screw or bolt", {"size": "M3", "length": 10.0, "type": "socket", "threads": False, "pitch": None}),
    "nut": (nut, "Nut", {"size": "M3", "type": "hex", "threads": False, "pitch": None}),
    "washer": (washer, "Washer", {"size": "M3", "type": "plain", "id": None, "od": None, "thickness": None}),
    "spacer": (spacer, "Spacer or standoff", {"size": "M3", "length": 10.0, "shape": "hex", "bore": "clearance", "od": None}),
    "insert": (heat_set_insert, "Heat-set insert (reference)", {"size": "M3", "maker": "CNCKitchen"}),
    "compression_spring": (compression_spring, "Compression spring",
                           {"d": 1.0, "od": 10.0, "free_length": 20.0, "coils": 8.0, "wire": "music", "ends": "closed-ground", "working_length": None}),
    "extension_spring": (extension_spring, "Extension spring", {"d": 1.0, "od": 8.0, "body_length": 20.0, "wire": "music"}),
    "torsion_spring": (torsion_spring, "Torsion spring", {"d": 1.0, "od": 10.0, "coils": 5.0, "leg": 15.0, "angle": 90.0, "wire": "music"}),
    "snap_hook": (snap_hook, "Snap-fit hook",
                  {"length": 12.0, "thickness": 1.6, "width": 6.0, "undercut": 1.0, "entry_angle": 30.0, "retention_angle": 90.0}),
    "cable_clip": (cable_clip, "Cable clip", {"cable_d": 6.0, "screw": "M3", "wall": 1.6, "width": 8.0}),
    "tie_mount": (tie_mount, "Cable-tie mount", {"tie_width": 4.8, "tie_thickness": 1.3, "screw": "M3", "size": 20.0}),
    "board_clip": (board_clip, "Board edge clip", {"board_thickness": 1.6, "height": 5.0, "grip": 2.5, "screw": "M3", "length": 10.0}),
    "din_clip": (din_rail_clip, "DIN rail clip", {"length": 40.0, "thickness": 3.0, "screw": "M3"}),
    "spur_gear": (spur_gear, "Spur gear", {"module": 1.0, "teeth": 20, "thickness": 6.0, "pressure_angle": 20.0,
                                           "bore": "round", "bore_d": 5.0, "hub": 0.0, "set_screw": None}),
    "gt2_pulley": (gt2_pulley, "GT2 timing pulley", {"teeth": 20, "belt_width": 6.0, "bore": "round", "bore_d": 5.0,
                                                    "flanges": True, "hub": 7.0, "set_screw": "M3"}),
    "knob": (knob, "Knob", {"diameter": 20.0, "height": 15.0, "shaft": "d", "shaft_d": 6.0, "depth": 10.0, "grip": 24,
                            "pointer": True, "set_screw": None}),
    "button_cap": (button_cap, "Button cap", {"diameter": 10.0, "height": 6.0, "stem_d": 3.5, "stem_depth": 2.5, "panel": 2.0}),
    "hinge": (hinge, "Hinge", {"length": 40.0, "leaf_width": 15.0, "thickness": 2.5, "knuckles": 5, "pin": "filament", "screw": "M3"}),
    "latch": (latch, "Latch with keeper", {"width": 10.0, "reach": 8.0, "undercut": 1.2, "thickness": 1.8}),
    "test_print": (test_print, "Thread and snap test print", {"size": "M8", "clearances": "0.1,0.15,0.2,0.25,0.3", "hooks": "0.6,1.0,1.4"}),
}
# How each part sits on the print bed: a turn (x, y, z degrees) from how it is modelled.
PRINT_ROTATION = {"screw": (180, 0, 0), "snap_hook": (90, 0, 0), "din_clip": (180, 0, 0), "knob": (180, 0, 0),
                  "button_cap": (180, 0, 0), "latch": (90, 0, 0),
                  "extension_spring": (0, 0, 0), "torsion_spring": (0, 0, 0)}
# Parts that are always printed (no bought version): mode is ignored, and material matters.
PRINTED_ONLY = {"snap_hook", "cable_clip", "tie_mount", "board_clip", "din_clip", "spur_gear", "gt2_pulley", "knob",
                "button_cap", "hinge", "latch", "test_print"}


_CACHE: dict = {}


def make(kind: str, **params) -> dict:
    """Build a part (the last few are kept, so a download after a preview is instant)."""
    import copy
    import json
    key = json.dumps([kind, params], sort_keys=True, default=str)
    if key not in _CACHE:
        _CACHE[key] = _make(kind, **params)
        while len(_CACHE) > 12:
            _CACHE.pop(next(iter(_CACHE)))
    r = _CACHE[key]
    return {**r, "notes": list(r["notes"]), "checks": list(r["checks"]), "info": copy.deepcopy(r["info"])}


def _make(kind: str, **params) -> dict:
    """Build a part. Unknown settings are an error, so a typo doesn't pass silently."""
    if kind not in KINDS:
        raise ValueError(f"part: one of {', '.join(KINDS)}")
    fn, label, defaults = KINDS[kind]
    import inspect
    allowed = set(inspect.signature(fn).parameters)
    # Mode, clearance and material only mean something to some parts: drop them for the rest.
    params = {k: v for k, v in params.items() if k in allowed or k not in ("mode", "clearance", "material", "threads")}
    extra = set(params) - allowed
    if extra:
        raise ValueError(f"{label}: unknown setting(s) {', '.join(sorted(extra))}")
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    if clean.get("mode") not in (None, "reference", "print"):
        raise ValueError("mode: reference or print")
    r = fn(**clean)
    shape = r["shape"]
    if not shape.is_valid:
        r["checks"].append("the solid came out with a modelling flaw: check it before printing")
    r["kind"], r["label"] = kind, label
    bb = shape.bounding_box()
    r["size"] = [round(bb.size.X, 3), round(bb.size.Y, 3), round(bb.size.Z, 3)]
    return r


def write(kind: str, folder, stl: bool = True, **params) -> dict:
    """STEP (and STL) of the part, and a notes file."""
    from pathlib import Path
    from build123d import export_step, export_stl
    r = make(kind, **params)
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    stem = kind
    export_step(r["shape"], str(out / f"{stem}.step"))
    files = {"step": str(out / f"{stem}.step")}
    if stl:
        export_stl(r["shape"], str(out / f"{stem}.stl"), tolerance=0.01, angular_tolerance=0.2)
        files["stl"] = str(out / f"{stem}.stl")
    lines = [f"# {r['label']}", ""] + [f"- {n}" for n in r["notes"]] + [f"- check: {c}" for c in r["checks"]]
    lines += ["", "Settings: " + ", ".join(f"{k}={v}" for k, v in params.items())]
    (out / "notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files["notes"] = str(out / "notes.md")
    return {**r, "files": files}


# ---------- What the page needs to draw a form for each part ----------

SIZES_METRIC = ["M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "M10", "M12"]
SIZES_INCH = ["#2-56", "#4-40", "#6-32", "#8-32", "#10-24", "#10-32", "1/4-20", "5/16-18", "3/8-16"]
LABELS = {
    "size": ("Size", "text"), "length": ("Length", "len"), "type": ("Type", "select"), "threads": ("Model the threads", "bool"),
    "pitch": ("Pitch (blank for standard)", "len"), "id": ("Inside diameter (custom)", "len"), "od": ("Outside diameter", "len"),
    "thickness": ("Thickness", "len"), "shape": ("Shape", "select"), "bore": ("Bore", "select"), "maker": ("Maker", "select"),
    "d": ("Wire diameter", "len"), "free_length": ("Free length", "len"), "coils": ("Coils (total)", "num"), "wire": ("Wire", "select"),
    "ends": ("Ends", "select"), "working_length": ("Working length (optional)", "len"), "body_length": ("Body length", "len"),
    "leg": ("Leg length", "len"), "angle": ("Angle between legs, °", "num"), "width": ("Width", "len"), "undercut": ("Undercut", "len"),
    "entry_angle": ("Entry angle, °", "num"), "retention_angle": ("Retention angle, ° (90 holds for good)", "num"),
    "cable_d": ("Cable diameter", "len"), "screw": ("Screw", "select"), "wall": ("Wall", "len"), "tie_width": ("Tie width", "len"),
    "tie_thickness": ("Tie thickness", "len"), "board_thickness": ("Board thickness", "len"), "height": ("Board height above foot", "len"),
    "grip": ("Grip depth", "len"),
    "module": ("Module", "num"), "teeth": ("Teeth", "num"), "pressure_angle": ("Pressure angle, °", "num"),
    "bore_d": ("Bore", "len"), "hub": ("Hub length (0 for none)", "len"), "set_screw": ("Set screw", "select"),
    "belt_width": ("Belt width", "len"), "flanges": ("Flanges", "bool"), "diameter": ("Diameter", "len"),
    "shaft": ("Shaft", "select"), "shaft_d": ("Shaft diameter", "len"), "depth": ("Hole depth", "len"),
    "pointer": ("Pointer line", "bool"), "stem_d": ("Switch actuator diameter", "len"), "stem_depth": ("Socket depth", "len"),
    "panel": ("Panel thickness", "len"), "leaf_width": ("Leaf width", "len"), "knuckles": ("Knuckles", "num"),
    "pin": ("Pin", "select"), "reach": ("Reach", "len"), "clearances": ("Clearances to try (mm, commas)", "text"),
    "hooks": ("Hook undercuts to try (mm, commas)", "text"),
}


# Where one setting name means something else for a part.
KIND_LABELS = {("knob", "height"): ("Height", "len"), ("knob", "grip"): ("Grip ridges (0 for none)", "num"),
               ("button_cap", "height"): ("Height", "len"), ("button_cap", "diameter"): ("Cap diameter", "len"),
               ("spacer", "od"): ("Across (blank for stock)", "len"), ("test_print", "size"): ("Thread", "text")}


def catalog() -> dict:
    """Each part's fields, defaults and choices, for the page's form."""
    choices = {
        ("screw", "type"): list(SCREW_TYPES), ("nut", "type"): list(NUT_TYPES), ("washer", "type"): list(WASHER_TYPES),
        ("spacer", "shape"): ["hex", "round"], ("spacer", "bore"): ["clearance", "thread", "insert"],
        ("insert", "maker"): ["CNCKitchen", "ruthex", "McMaster-Carr", "Hilitchi", "AE-SamZhihui"],
        ("compression_spring", "ends"): ["closed-ground", "closed", "open"],
        ("spur_gear", "bore"): ["round", "d", "none"], ("gt2_pulley", "bore"): ["round", "d"],
        ("spur_gear", "set_screw"): ["", "M2", "M2.5", "M3", "M4"], ("gt2_pulley", "set_screw"): ["", "M2", "M2.5", "M3", "M4"],
        ("knob", "set_screw"): ["", "M2", "M2.5", "M3"], ("knob", "shaft"): ["d", "round", "knurled"],
        ("hinge", "pin"): ["filament", "M3"],
    }
    out = {}
    for kind, (fn, label, defaults) in KINDS.items():
        fields = []
        for name, default in defaults.items():
            lab, typ = KIND_LABELS.get((kind, name)) or LABELS.get(name, (name.replace("_", " ").capitalize(), "len"))
            opts = choices.get((kind, name))
            if name == "wire":
                opts = list(WIRE)
            if name == "screw":
                opts = list(SCREWS)
            f = {"name": name, "label": lab, "type": "select" if opts else typ, "default": default}
            if opts:
                f["options"] = opts
            if name == "size":
                f["options"] = SIZES_METRIC + SIZES_INCH
                f["type"] = "text"
            if typ == "text" and name != "size":
                f.pop("options", None)
                f["type"] = "text"
                f["options"] = []
            fields.append(f)
        import inspect
        params = inspect.signature(fn).parameters
        out[kind] = {"label": label, "fields": fields, "printed_only": kind in PRINTED_ONLY,
                     "modes": "mode" in params, "material": "material" in params,
                     "doc": (fn.__doc__ or "").strip().split("\n\n")[0].replace("\n", " ")}
    return {"kinds": out, "materials": list(PLASTIC), "wires": {k: v["name"] for k, v in WIRE.items()}}
