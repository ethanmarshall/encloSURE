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
BEDS = {"prusa-mk4": (250, 210), "prusa-mini": (180, 180), "bambu-x1": (256, 256), "ender-3": (220, 220),
        "prusa-xl": (360, 360), "voron-350": (350, 350)}
DENSITY = {"PETG": 1.27, "PLA": 1.24, "ABS": 1.04, "ASA": 1.07, "nylon": 1.14}


def on_bed(shape):
    """The shape moved so it stands on z = 0, centred on x = y = 0."""
    bb = shape.bounding_box()
    return Pos(-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2, -bb.min.Z) * shape


def box_items(spec, made: dict) -> list[tuple[str, object]]:
    """The box's printed parts, turned to print: the base upright, a lid on top flipped onto its
    face (its lip, knuckles or posts up)."""
    items = [("base", made["base"])]
    lid = made.get("lid")
    if lid is not None:
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
        current.append((name, Pos(x + w / 2 - bed[0] / 2, y + d / 2 - bed[1] / 2, 0) * s))
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
        m.add_shape(s, linear_deflection=0.02, angular_deflection=0.2, part_number=name)
    m.write(str(path))
    return str(path)


def slicer() -> str | None:
    return shutil.which("prusa-slicer") or shutil.which("PrusaSlicer")


def slice_numbers(path_3mf, material: str = "PETG", layer: float = 0.2, infill: int = 15, timeout: int = 240) -> dict | None:
    """PrusaSlicer's print time and filament for a 3MF (its default printer settings, no supports),
    or None when PrusaSlicer isn't installed or fails."""
    exe = slicer()
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "plate.gcode"
        cmd = [exe, "--export-gcode", str(path_3mf), "--layer-height", str(layer), "--fill-density", f"{infill}%",
               "--perimeters", "2", "--filament-diameter", "1.75", "--nozzle-diameter", "0.4",
               "--filament-density", str(DENSITY.get(material, 1.25)), "--dont-arrange", "-o", str(out)]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
        except (subprocess.SubprocessError, OSError):
            return None
        text = out.read_text(errors="replace")[-40000:] if out.exists() else ""
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
            "settings": f"PrusaSlicer defaults, {layer:g} mm layers, {infill}% infill, 2 perimeters, no supports, {material}"}


def write(items, folder, bed=(250.0, 210.0), material: str = "PETG", slice_it: bool = True) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    r = make(items, bed)
    files, sliced = [], []
    for i, p in enumerate(r["plates"], 1):
        path = folder / (f"plate_{i}.3mf" if len(r["plates"]) > 1 else "plate.3mf")
        export_3mf(p, path)
        files.append(str(path))
        if slice_it:
            sliced.append(slice_numbers(path, material))
    out = {"files": files, "notes": r["notes"], "checks": r["checks"],
           "parts": [[n for n, _ in p] for p in r["plates"]]}
    if slice_it:
        if all(sliced):
            out["slicer"] = {"hours": round(sum(s["hours"] for s in sliced), 2),
                             "grams": round(sum(s["grams"] or 0 for s in sliced), 1),
                             "per_plate": sliced, "settings": sliced[0]["settings"]}
        else:
            out["notes"].append("no slicer on this server: times and grams are the rough estimate")
    return out
