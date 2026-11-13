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
        t = {"title": f"ENCLOSURE {name.upper()}", "part_number": f"{stem}-{name[0]}", "revision": "A",
             "material": "PETG" if standard == "iso" else "PETG (3D PRINTED)", **(title or {})}
        t["title"] = f"{t['title']}" if "title" not in (title or {}) else f"{title['title']} {name.upper()}"
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
                notes += [f"{name}: {p.get('message', p)}" for p in problems[:8]]
            except (json.JSONDecodeError, AttributeError):
                pass
    return {"files": made, "standard": standard, "review": notes}
