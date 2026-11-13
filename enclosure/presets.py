"""Named cutouts for common panel parts, each with where its size comes from.

Use one as `--cutout left:pg9@0,20` (FACE:PRESET@a,b). A hole for a threaded part is its thread
plus a little clearance; check the datasheet of the exact part you buy, since makers differ.
"""

from __future__ import annotations

# name: (shape, size, corner radius, source)
PRESETS = {
    # USB-C: GCT USB4105 receptacle, 8.94 mm wide and 3.31 mm seated height (DigiKey listing),
    # plus about 0.25 mm per side. The receptacle's face should sit within about 1 mm of the
    # outside so a plug's overmold can reach it.
    "usb-c": ("rect", [9.5, 3.85], 1.6, "USB4105 receptacle face 8.94 x 3.31 mm (DigiKey) + 0.25 mm/side"),
    # Keystone jacks (RJ45, HDMI, USB couplers...): one cutout fits all modules.
    "keystone": ("rect", [14.9, 19.2], 0.0, "keystone module cutout 14.9 x 19.2 mm (Delock)"),
    # Pilot devices
    "pushbutton-22": ("round", [22.3], 0.0, "22 mm pushbuttons mount in a 22.3 mm hole (Omron)"),
    # Toggle switch bushings: thread major diameter plus clearance.
    "toggle-1/4": ("round", [6.5], 0.0, "1/4-40 bushing (6.35 mm) + clearance"),
    "toggle-15/32": ("round", [12.2], 0.0, "15/32-32 bushing (11.9 mm) + clearance"),
    # PG glands: the maker's recommended clearance hole (VIOX PG brass series, upper value).
    "pg7": ("round", [12.7], 0.0, "PG7 gland, clearance hole 12.5-12.7 mm (VIOX)"),
    "pg9": ("round", [15.4], 0.0, "PG9 gland, clearance hole 15.2-15.4 mm (VIOX)"),
    "pg11": ("round", [18.8], 0.0, "PG11 gland, clearance hole 18.6-18.8 mm (VIOX)"),
    "pg13.5": ("round", [20.6], 0.0, "PG13.5 gland, clearance hole 20.4-20.6 mm (VIOX)"),
    "pg16": ("round", [22.7], 0.0, "PG16 gland, clearance hole 22.5-22.7 mm (VIOX)"),
    "pg21": ("round", [28.5], 0.0, "PG21 gland, clearance hole 28.3-28.5 mm (VIOX)"),
    # Metric glands and M-thread panel parts: thread + 0.5 mm, the usual clearance.
    "m12": ("round", [12.5], 0.0, "M12x1.5 gland or M12 vent plug: 12 mm thread + 0.5 mm"),
    "m16": ("round", [16.5], 0.0, "M16x1.5 gland: 16 mm thread + 0.5 mm"),
    "m20": ("round", [20.5], 0.0, "M20x1.5 gland: 20 mm thread + 0.5 mm"),
    "m25": ("round", [25.5], 0.0, "M25x1.5 gland: 25 mm thread + 0.5 mm"),
    "m8-panel": ("round", [8.5], 0.0, "M8 panel connector: 8 mm thread + 0.5 mm"),
    "m12-panel": ("round", [12.5], 0.0, "M12 panel connector: 12 mm thread + 0.5 mm"),
    # RF and power panel parts, each from one maker's datasheet: check yours.
    "sma-bulkhead": ("round", [6.35], 0.0, "SMA rear-mount bulkhead, 1/4-36 thread: 6.35 mm panel hole (Wurth 60312042641504)"),
    "bnc-bulkhead": ("round", [12.7], 0.0, "BNC bulkhead jack with flange: 12.7 mm panel hole (Telegaertner J01001A0079)"),
    "dc-barrel-snap": ("round", [12.6], 0.0, "5.5 x 2.1 mm DC barrel jack, snap-in panel mount: 12.6 mm hole (Parts Express 090-5042)"),
    # Panel fuse holder for 5 x 20 mm fuses: Schurter FEF, 13 mm hole with a 12 mm flat, panel up to
    # 7 mm (Schurter FEF datasheet). This hole is round: tighten the nut well, or file the flat.
    "fuse-5x20": ("round", [13.0], 0.0, "Schurter FEF fuse holder: 13 mm hole (12 mm D-flat), panel up to 7 mm"),
    # IEC C14 mains inlet, snap-in: 20 x 27.5 mm cutout, made for 1 to 3 mm panels (Interpower).
    "iec-c14": ("rect", [27.5, 20.0], 0.0, "IEC C14 snap-in inlet: 27.5 x 20 mm cutout, 1 to 3 mm panel (Interpower)"),
    # Fans: a round opening the fan blows through, plus four screw holes (see FANS).
    "fan-40": ("round", [37.0], 0.0, "40 mm fan: 37 mm opening, 4 holes Ø3.5 on 32 mm (San Ace 109P0412H3013, Noctua NF-A4x10)"),
    "fan-60": ("round", [57.0], 0.0, "60 mm fan: 57 mm opening, 4 holes Ø4.5 on 50 mm (San Ace 60GT25 mounting reference)"),
    "fan-80": ("round", [76.0], 0.0, "80 mm fan: 76 mm opening, 4 holes Ø4.5 on 71.5 mm (San Ace 9G0824G102)"),
    # A drain or breather hole: a design choice, not a part.
    "drain": ("round", [3.0], 0.0, "3 mm drain hole"),
}

# Fan screw holes: (hole spacing centre to centre, hole diameter), from the makers' drawings.
FANS = {"fan-40": (32.0, 3.5), "fan-60": (50.0, 4.5), "fan-80": (71.5, 4.5)}


def expand(cutouts: list[dict]) -> list[dict]:
    """Fan presets bring their four screw holes along as plain round cutouts (once: a list that
    already has them is left as it is), so every output (STEP, Onshape, SolidWorks, drawings) gets them."""
    out = list(cutouts)
    for c in cutouts:
        if c.get("preset") not in FANS:
            continue
        pitch, d = FANS[c["preset"]]
        a, b = c.get("at", [0, 0])
        for sa in (-1, 1):
            for sb in (-1, 1):
                hole = {"face": c["face"], "shape": "round", "size": [d], "at": [a + sa * pitch / 2, b + sb * pitch / 2],
                        "source": f"{c['preset']} screw hole"}
                if not any(o.get("source") == hole["source"] and o.get("face") == hole["face"]
                           and [round(v, 3) for v in o.get("at", [])] == [round(v, 3) for v in hole["at"]] for o in out):
                    out.append(hole)
    return out


GLANDS = {k for k in PRESETS if k.startswith(("pg", "m1", "m2"))}


def resolve(cutout: dict) -> dict:
    """A cutout with `preset` set filled in with its shape and size."""
    name = cutout.get("preset")
    if not name:
        return cutout
    if name not in PRESETS:
        raise ValueError(f"cutout preset {name!r}: one of {', '.join(sorted(PRESETS))}")
    shape, size, radius, source = PRESETS[name]
    return {**cutout, "shape": shape, "size": list(size), "radius": radius, "source": source}
