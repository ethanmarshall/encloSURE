"""One print plate: the box's printed parts and any printed hardware, each turned to the way it
prints best, laid out on the bed and written as a 3MF; and, when PrusaSlicer is installed, its real
print time and grams.

    plate.make(items, bed=(250, 210)) -> {"plates": [[placed...]], "notes", "checks"}
    plate.write(items, folder, ...) -> 3MF per plate, and slicer numbers when it can
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from build123d import Mesher, Pos, Rot

GAP = 5.0  # between parts on the bed, mm
LAST_ERROR = ""  # why the slicer last failed, for the health check
BEDS = {"prusa-mk4": (250, 210), "prusa-mini": (180, 180), "bambu-x1": (256, 256), "bambu-h3c": (330, 320), "ender-3": (220, 220),
        "prusa-xl": (360, 360), "voron-350": (350, 350)}
# Speeds (mm/s) and accelerations (mm/s²) for the slicer's time estimate, from each maker's own
# "0.20mm Standard" process and machine profiles (Bambu Studio's resources/profiles/BBL); a printer
# without an entry gets PrusaSlicer's defaults. Filament flow caps from Bambu's generic profiles (mm³/s).
SPEEDS = {
    "bambu-h3c": {"external": 200, "perimeter": 300, "infill": 350, "solid": 250, "top": 200, "travel": 1400, "first": 50,
                  "accel": 20000, "accel_external": 7000, "accel_perimeter": 12000, "accel_top": 2000, "accel_travel": 25000,
                  "machine_accel": 25000, "machine_speed": 1400, "name": "Bambu Lab H3C (Bambu Studio's 0.20mm Standard @BBL H3C)"},
    "bambu-x1": {"external": 200, "perimeter": 300, "infill": 270, "solid": 250, "top": 200, "travel": 500, "first": 50,
                 "accel": 10000, "accel_external": 5000, "accel_perimeter": 10000, "accel_top": 2000, "accel_travel": 10000,
                 "machine_accel": 20000, "machine_speed": 500, "name": "Bambu Lab X1 Carbon (Bambu Studio's 0.20mm Standard @BBL X1C)"},
}
MAX_FLOW = {"PLA": 12, "PETG": 12, "ABS": 15, "ASA": 12, "nylon": 10}
DENSITY = {"PETG": 1.27, "PLA": 1.24, "ABS": 1.04, "ASA": 1.07, "nylon": 1.14}


def on_bed(shape):
    """The shape moved so it stands on z = 0, centred on x = y = 0."""
    bb = shape.bounding_box()
    return Pos(-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2, -bb.min.Z) * shape


def box_items(spec, made: dict) -> list[tuple[str, object]]:
    """The box's printed parts, turned to print: the base upright, a lid on top flipped onto its
    face (its lip, knuckles or posts up)."""
    inl = made.get("inlays") or []

    def grouped(name, host, which):
        # A part with its second-colour bodies kept together: they move as one and go in the 3MF as
        # separate objects in place, so each can get its own filament.
        mine = [(n, sh) for n, sh, h in inl if h == which]
        if not mine:
            return host
        from build123d import Compound
        host = Compound(children=[host] + [sh for _, sh in mine])
        host.label = "group:" + "|".join([name] + [n for n, _ in mine])
        return host

    if made.get("print_body") is not None:  # a living hinge: one piece, the lid standing on the back wall
        from .box import living_turn
        turn = living_turn(spec)
        inl = [(n, sh if h == "base" else turn(sh), "base") for n, sh, h in inl]
        return [("box", grouped("box", made["print_body"], "base"))] + list(made.get("extras") or [])
    items = [("base", grouped("base", made["base"], "base"))]
    lid = made.get("lid")
    if lid is not None:
        lid = grouped("lid", lid, "lid")
        if spec.lid == "slide":
            items.append(("lid", lid))
        else:
            items.append(("lid", Rot(180, 0, 0) * lid))
    items += list(made.get("extras") or [])  # a battery door, cable clamps, a wall bracket: flat as built
    return items


def part_item(kind: str, shape, name: str | None = None):
    """A hardware part turned the way its notes say it prints."""
    from .hardware import PRINT_ROTATION
    rot = PRINT_ROTATION.get(kind)
    return (name or kind, Rot(*rot) * shape if rot else shape)


def make(items: list[tuple[str, object]], bed=(250.0, 210.0), gap: float = GAP) -> dict:
    """Shelf packing: biggest first, rows across the bed's width; a new plate when one fills."""
    placed = [(name, on_bed(s)) for name, s in items]
    sized = []
    checks = []
    for name, s in placed:
        bb = s.bounding_box()
        w, d = bb.size.X, bb.size.Y
        if (w > bed[0] or d > bed[1]) and d <= bed[0] and w <= bed[1]:
            s = on_bed(Rot(0, 0, 90) * s)  # turn it to fit
            bb = s.bounding_box()
            w, d = bb.size.X, bb.size.Y
        if w > bed[0] or d > bed[1]:
            checks.append(f"{name} ({w:.0f} x {d:.0f} mm) is bigger than the {bed[0]:g} x {bed[1]:g} mm bed")
        sized.append((name, s, w, d))
    sized.sort(key=lambda t: -t[3] * 1000 - t[2])
    plates, current = [], []
    x = y = row_d = 0.0
    for name, s, w, d in sized:
        if current and x + w > bed[0]:
            x, y, row_d = 0.0, y + row_d + gap, 0.0
        if current and y + d > bed[1]:
            plates.append(current)
            current, x, y, row_d = [], 0.0, 0.0, 0.0
        current.append((name, Pos(x + w / 2, y + d / 2, 0) * s))  # the bed's corner at the origin, as slicers expect
        x += w + gap
        row_d = max(row_d, d)
    if current:
        plates.append(current)
    notes = [f"{len(items)} part{'s' if len(items) != 1 else ''} on {len(plates)} plate{'s' if len(plates) != 1 else ''} "
             f"of {bed[0]:g} x {bed[1]:g} mm, each turned the way it prints best"]
    return {"plates": plates, "notes": notes, "checks": checks}


def export_3mf(plate: list, path) -> str:
    m = Mesher()
    for name, s in plate:
        label = getattr(s, "label", "") or ""
        if label.startswith("group:"):
            names = label[6:].split("|")
            for n, child in zip(names, s.children):
                m.add_shape(child, linear_deflection=0.02, angular_deflection=0.2, part_number=n)
            continue
        m.add_shape(s, linear_deflection=0.02, angular_deflection=0.2, part_number=name)
    m.write(str(path))
    return str(path)


def slicer() -> str | None:
    return shutil.which("prusa-slicer") or shutil.which("PrusaSlicer")


def _speed_args(printer: str | None, material: str) -> list[str]:
    sp = SPEEDS.get(printer or "")
    if not sp:
        return []
    return ["--external-perimeter-speed", str(sp["external"]), "--perimeter-speed", str(sp["perimeter"]),
            "--infill-speed", str(sp["infill"]), "--solid-infill-speed", str(sp["solid"]),
            "--top-solid-infill-speed", str(sp["top"]), "--travel-speed", str(sp["travel"]),
            "--first-layer-speed", str(sp["first"]), "--default-acceleration", str(sp["accel"]),
            "--external-perimeter-acceleration", str(sp["accel_external"]), "--perimeter-acceleration", str(sp["accel_perimeter"]),
            "--top-solid-infill-acceleration", str(sp["accel_top"]), "--travel-acceleration", str(sp["accel_travel"]),
            "--infill-acceleration", str(sp["accel"]), "--max-volumetric-speed", str(MAX_FLOW.get(material, 12)),
            "--machine-limits-usage", "time_estimate_only",
            "--machine-max-acceleration-extruding", str(sp["machine_accel"]),
            "--machine-max-acceleration-x", str(sp["machine_accel"]), "--machine-max-acceleration-y", str(sp["machine_accel"]),
            "--machine-max-feedrate-x", str(sp["machine_speed"]), "--machine-max-feedrate-y", str(sp["machine_speed"])]


def slice_numbers(path_3mf, material: str = "PETG", layer: float = 0.2, infill: int = 15, timeout: int = 240,
                  bed=(250.0, 210.0), printer: str | None = None) -> dict | None:
    """PrusaSlicer's print time and filament for a 3MF (its default printer settings, no supports),
    or None when PrusaSlicer isn't installed or fails."""
    exe = slicer()
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "plate.gcode"
        cmd = [exe, "--export-gcode", str(path_3mf), "--layer-height", str(layer), "--fill-density", f"{infill}%",
               "--perimeters", "2", "--filament-diameter", "1.75", "--nozzle-diameter", "0.4",
               "--filament-density", str(DENSITY.get(material, 1.25)), "--dont-arrange",
               "--bed-shape", f"0x0,{bed[0]:g}x0,{bed[0]:g}x{bed[1]:g},0x{bed[1]:g}", "-o", str(out)]
        global LAST_ERROR
        tuned = _speed_args(printer, material)
        try:
            try:
                run = subprocess.run(cmd[:-2] + tuned + cmd[-2:], capture_output=True, text=True, timeout=timeout, check=True)
            except subprocess.CalledProcessError:
                if not tuned:
                    raise
                tuned = []  # an older PrusaSlicer without one of these options: its defaults, then
                run = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
        except subprocess.CalledProcessError as e:
            LAST_ERROR = ((e.stderr or "") + (e.stdout or "")).strip()[-400:]
            return None
        except (subprocess.SubprocessError, OSError) as e:
            LAST_ERROR = str(e)[:400]
            return None
        text = out.read_text(errors="replace")[-40000:] if out.exists() else ""
        if "estimated printing time" not in text:
            made = [p.name for p in Path(d).iterdir()]
            LAST_ERROR = (f"no time in the G-code (files: {made}); " + (run.stdout or "")[-300:] + (run.stderr or "")[-200:]).strip()
    t = re.search(r"estimated printing time \(normal mode\) = ([^\n]+)", text)
    g = re.search(r"total filament used \[g\] = ([\d.]+)", text)
    mm = re.search(r"filament used \[mm\] = ([\d.]+)", text)
    if not t:
        return None
    secs = 0
    for n, unit in re.findall(r"(\d+)([dhms])", t.group(1)):
        secs += int(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    return {"time": t.group(1).strip(), "hours": round(secs / 3600, 2), "grams": float(g.group(1)) if g else None,
            "filament_m": round(float(mm.group(1)) / 1000, 2) if mm else None,
            "settings": (f"PrusaSlicer with the speeds of the {SPEEDS[printer]['name']}" if tuned else "PrusaSlicer defaults")
            + f", {layer:g} mm layers, {infill}% infill, 2 perimeters, no supports, {material}"}


def write(items, folder, bed=(250.0, 210.0), material: str = "PETG", slice_it: bool = True, printer: str | None = None) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    r = make(items, bed)
    files, sliced = [], []
    for i, p in enumerate(r["plates"], 1):
        path = folder / (f"plate_{i}.3mf" if len(r["plates"]) > 1 else "plate.3mf")
        export_3mf(p, path)
        files.append(str(path))
        if slice_it:
            sliced.append(slice_numbers(path, material, bed=bed, printer=printer))
    out = {"files": files, "notes": r["notes"], "checks": r["checks"],
           "parts": [[n for n, _ in p] for p in r["plates"]]}
    if slice_it:
        if all(sliced):
            out["slicer"] = {"hours": round(sum(s["hours"] for s in sliced), 2),
                             "grams": round(sum(s["grams"] or 0 for s in sliced), 1),
                             "per_plate": sliced, "settings": sliced[0]["settings"]}
        else:
            out["notes"].append("no slicer on this server: times and grams are the rough estimate" if not slicer() else
                                f"PrusaSlicer didn't slice it ({LAST_ERROR[-160:] or 'no reason given'}): times and grams are the rough estimate")
    return out
