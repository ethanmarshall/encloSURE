"""A print folder: everything for one design in one place, to print now and to upload somewhere later.

    <name>/
      README.md                 what it is, sizes, how to print and put it together (written to paste as a description)
      print_settings.json       the printer, material and plates, for the slicing script
      print/plate.3mf           every part laid out on the bed, turned the way it prints
      stl/<part>.stl            each part on its own, turned the way it prints
      step/<part>.step          each part as designed, for CAD
      step/assembly.step        the parts together, where there is an assembly
      images/*.png              pictures from the page's 3D view
      slice_with_bambu_studio.py, "Slice in Bambu Studio.command"   (Bambu printers) slice the plates with your Bambu Studio
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import plate as platemod

# Bambu Studio's own preset names, by this tool's printer and material (from its resources/profiles/BBL).
BAMBU = {
    "bambu-h3c": {"machine": "Bambu Lab H3C 0.4 nozzle", "process": "0.20mm Standard @BBL H3C", "suffix": "H3C"},
    "bambu-x1": {"machine": "Bambu Lab X1 Carbon 0.4 nozzle", "process": "0.20mm Standard @BBL X1C", "suffix": "X1C"},
}
BAMBU_FILAMENT = {"PLA": "Bambu PLA Basic", "PETG": "Bambu PETG HF", "ABS": "Bambu ABS", "ASA": "Bambu ASA", "nylon": "Bambu PAHT-CF"}
PRINTER_NAMES = {"prusa-mk4": "Prusa MK4", "prusa-mini": "Prusa MINI", "bambu-x1": "Bambu Lab X1 Carbon", "bambu-h3c": "Bambu Lab H3C",
                 "ender-3": "Creality Ender-3", "prusa-xl": "Prusa XL", "voron-350": "Voron 350"}
MAX_IMAGE = 3_000_000


def slug(text: str, fallback: str = "design") -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return s[:60] or fallback


def bambu_presets(printer: str | None, material: str) -> dict | None:
    b = BAMBU.get(printer or "")
    if not b:
        return None
    return {"machine": b["machine"], "process": b["process"],
            "filament": f"{BAMBU_FILAMENT.get(material, BAMBU_FILAMENT['PLA'])} @BBL {b['suffix']}"}


def _hm(hours: float) -> str:
    m = int(round(hours * 60))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def write(folder, title: str, groups: list, designed: list | None = None, assembly=None, notes: list | None = None,
          checks: list | None = None, about: str = "", bed=(250.0, 210.0), printer: str | None = None, material: str = "PETG",
          images: list | None = None) -> dict:
    """groups: [(name, shape turned to print, how many)], one entry per different part.
    designed: [(name, shape as designed)] for STEP; defaults to the parts as they print.
    assembly: the shapes that make the assembly, where they sit together."""
    from build123d import export_step, export_stl
    folder = Path(folder)
    for sub in ("print", "stl", "step"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    notes, checks = list(notes or []), list(checks or [])
    how_many = {name: int(n) for name, _, n in groups}
    if sum(how_many.values()) > 80:
        raise ValueError("up to 80 parts in a print folder")

    # The plates, with a real slice for time and grams where the server has a slicer.
    items = [(name if n == 1 else f"{name}_{i + 1}", shape) for name, shape, n in groups for i in range(int(n))]
    r = platemod.write(items, folder / "print", bed, material, slice_it=True, printer=printer)
    plates = [f"print/{Path(f).name}" for f in r["files"]]

    # One STL per different part, turned to print; one STEP per different part, as designed.
    for name, shape, _ in groups:
        label = getattr(shape, "label", "") or ""
        if label.startswith("group:"):  # a part with a second colour: each body its own file, kept in register
            for n, child in zip(label[6:].split("|"), shape.children):
                export_stl(child, str(folder / "stl" / f"{slug(n)}.stl"))
        else:
            export_stl(platemod.on_bed(shape), str(folder / "stl" / f"{slug(name)}.stl"))
    for name, shape in (designed if designed is not None else [(n, s) for n, s, _ in groups]):
        export_step(shape, str(folder / "step" / f"{slug(name)}.step"))
    if assembly:  # last: putting shapes in an assembly ties them to it
        from build123d import Compound
        export_step(Compound(children=list(assembly)), str(folder / "step" / "assembly.step"))

    # Pictures from the page.
    saved = []
    if images:
        (folder / "images").mkdir(exist_ok=True)
        for i, (name, data) in enumerate(images[:8], 1):
            if not data or len(data) > MAX_IMAGE or not data.startswith(b"\x89PNG"):
                continue
            p = folder / "images" / f"{i:02d}_{slug(name, 'view')}.png"
            p.write_bytes(data)
            saved.append(f"images/{p.name}")

    est = r["estimate"]
    bambu = bambu_presets(printer, material)
    settings = {"title": title, "printer": printer, "printer_name": PRINTER_NAMES.get(printer or "", "a printer of this bed size"),
                "bed_mm": list(bed), "material": material, "layer_mm": 0.2, "infill_percent": 15, "walls": 2, "supports": False,
                "plates": plates, "parts": how_many, "estimate": {"hours": est["hours"], "grams": est["grams"], "source": est["source"]},
                "bambu": bambu}
    (folder / "print_settings.json").write_text(json.dumps(settings, indent=1), encoding="utf-8")
    if bambu:
        src = Path(__file__).with_name("bambu_slice.py")
        shutil.copyfile(src, folder / "slice_with_bambu_studio.py")
        cmd = folder / "Slice in Bambu Studio.command"
        cmd.write_text('#!/bin/bash\ncd "$(dirname "$0")" || exit 1\npython3 slice_with_bambu_studio.py\necho\nread -r -p "Press Return to close." _\n',
                       encoding="utf-8")
        cmd.chmod(0o755)

    # The README, plain enough to paste as a model's description.
    L = [f"# {title}", ""]
    if about:
        L += [about, ""]
    if notes:
        L += ["## What it is", ""] + [f"- {n}" for n in notes] + [""]
    L += ["## Parts to print", ""]
    L += [f"- {v} x `stl/{slug(k)}.stl`" for k, v in how_many.items()]
    L += ["", "## Printing", "",
          f"- {'Plates' if len(plates) > 1 else 'Plate'}: " + ", ".join(f"`{p}`" for p in plates)
          + f" ({bed[0]:g} x {bed[1]:g} mm bed, {settings['printer_name']}), every part already turned the way it prints",
          f"- {material}, 0.2 mm layers, 15% infill, 2 walls, no supports",
          f"- About {_hm(est['hours'])} and {est['grams']:g} g of filament ({est['source']})"]
    L += [f"- {n}" for n in r["checks"]]
    if bambu:
        L += ["", "## Slicing with Bambu Studio", "",
              "Double-click `Slice in Bambu Studio.command` (Mac), or run `python3 slice_with_bambu_studio.py`. It slices each plate with "
              f"your Bambu Studio ({bambu['machine']}, {bambu['process']}, {bambu['filament']}) and writes `print/plate.gcode.3mf` "
              "beside it. If that fails it opens the plate in Bambu Studio for you to slice by hand. Or just open the plate 3MF "
              "yourself: the parts are laid out and oriented."]
    if checks:
        L += ["", "## Check before printing", ""] + [f"- {c}" for c in checks]
    L += ["", "## Files", "", "- `print/`: the plate as 3MF", "- `stl/`: each part, turned to print", "- `step/`: each part as designed, for CAD"
          + (" (and `assembly.step`, the parts together)" if assembly is not None else "")]
    if saved:
        L += ["- `images/`: pictures"]
    L += ["", "Made with EncloSURE.", ""]
    (folder / "README.md").write_text("\n".join(L), encoding="utf-8")
    return {"plates": plates, "parts": how_many, "estimate": est, "images": saved, "bambu": bambu}
