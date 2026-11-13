"""Drawings of a box: an ASME (inch) or ISO (mm) drawing of each part, made by draftwright.

    enclosure drawing my_box/ --standard asme -o drawings       # a quick box's base and lid
    enclosure drawing drill/ --standard asme --material "Al 380" # a drilled bought box, for a machinist

It runs draftwright (github.com/ethanmarshall/draftwright-rust, the ASME fork) on each part's STEP.
Point at the binary with $DRAFTWRIGHT, or put `draftwright` on the PATH; a checkout next to this one
(../draftwright-rust/target/release/draftwright) is found too.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

PARTS = (("base.step", "Base"), ("lid.step", "Lid"))
TITLE_CELLS = ("title", "number", "material", "tolerance", "drawn_by", "approved_by", "date", "revision",
               "company", "document_type", "cage")


def find_draftwright() -> str:
    for c in (os.environ.get("DRAFTWRIGHT"), shutil.which("draftwright"),
              str(Path(__file__).resolve().parents[2] / "draftwright-rust" / "target" / "release" / "draftwright")):
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    raise RuntimeError("draftwright is not installed: build github.com/ethanmarshall/draftwright-rust "
                       "(cargo build --release) and set DRAFTWRIGHT to target/release/draftwright")


def make(folder, out, standard: str = "asme", title: dict | None = None, formats: str = "pdf,svg") -> dict:
    """A drawing for each part in *folder* (base.step and lid.step, as `box`, `frompcb` and `stock`
    write them). Returns the files and draftwright's review notes."""
    if standard not in ("asme", "iso"):
        raise ValueError("standard: asme or iso")
    exe = find_draftwright()
    folder, out = Path(folder), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    made, notes = {}, []
    found = [(folder / f, name) for f, name in PARTS if (folder / f).exists()]
    if not found:
        raise ValueError(f"{folder}: no base.step or lid.step in it")
    stem = (title or {}).get("part_number") or folder.name.upper().replace(" ", "-")
    for step, name in found:
        given = dict(title or {})
        number = given.pop("part_number", None) or given.pop("number", None) or stem
        bought = (folder / "holes.json").exists()  # from `stock`: a bought box, drilled
        material = "AS SUPPLIED" if bought else ("PETG" if standard == "iso" else "PETG (3D PRINTED)")
        t = {"title": f"{given.pop('title', 'ENCLOSURE')} {name.upper()}", "number": f"{number}-{name[0]}",
             "revision": "A", "material": material, **given}
        t = {k: v for k, v in t.items() if k in TITLE_CELLS}
        spec = {"sheet": {"standard": standard, "title": {k: str(v) for k, v in t.items()}}}
        spec_path = out / f"{name.lower()}.drawing.json"
        spec_path.write_text(json.dumps(spec, indent=2) + "\n")
        dest = out / name.lower()
        r = subprocess.run([exe, "render", str(step), "--spec", str(spec_path), "-o", str(dest), "--formats", formats],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"draftwright could not draw {step.name}: {(r.stderr or r.stdout).strip()[-600:]}")
        files = sorted(str(p) for p in dest.parent.glob(f"{dest.name}*") if p.suffix.lower() in (".pdf", ".svg", ".png", ".dxf"))
        if not files and dest.is_dir():
            files = sorted(str(p) for p in dest.iterdir() if p.suffix.lower() in (".pdf", ".svg", ".png", ".dxf"))
        made[name.lower()] = files
        rv = subprocess.run([exe, "review", str(step), "--spec", str(spec_path)], capture_output=True, text=True)
        if rv.returncode == 0:
            try:
                problems = json.loads(rv.stdout).get("problems", [])
                msgs = [str(p.get("message", p)) if isinstance(p, dict) else str(p) for p in problems]
                rounding = [m for m in msgs if "default three-place limit" in m or "default two-place limit" in m]
                if rounding:
                    notes.append(f"{name}: {len(rounding)} dimensions round off the metric model at the drawing's "
                                 f"default decimal places (fine for a printed or drilled box; add tolerances if it matters)")
                notes += [f"{name}: {m}" for m in msgs if m not in rounding][:8]
            except (json.JSONDecodeError, AttributeError):
                pass
    return {"files": made, "standard": standard, "review": notes}
