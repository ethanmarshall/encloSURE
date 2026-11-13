"""An exploded assembly drawing with a parts list: the base, the board, the lid and their screws,
pulled apart along Z, drawn by draftwright's assembly pack (balloons, a parts list as PDF and CSV).

    enclosure assembly my_box/box.json --board board.step -o assembly

Without a board STEP, a plain plate stands in for the board, sized round the standoffs.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from build123d import Box, Compound, Cylinder, Location, Pos, export_step

from . import box as boxmod

# Screw lengths in stock (ISO 4762 / 7380 preferred lengths, mm).
LENGTHS = (4, 5, 6, 8, 10, 12, 16, 20, 25)


def _screw(m: str, length: float, name: str):
    """A real ISO 4762 socket head cap screw (plain threads), its head on z = 0."""
    from . import hardware
    try:
        s = hardware.make("screw", size=m, length=float(length), type="socket")["shape"]
        s = Compound(children=[s]) if not isinstance(s, Compound) else s
    except Exception:  # a size the tables lack: a plain stand-in
        d = float(m[1:])
        head_d, head_h = boxmod.SCREWS[m][4], 0.6 * d
        s = Cylinder(d / 2, length).locate(Location((0, 0, -length / 2))) + Cylinder(head_d / 2, head_h).locate(Location((0, 0, head_h / 2)))
    s.label = name
    return s


def _insert(m: str, name: str):
    """A heat-set insert (CNC Kitchen's), its top on z = 0."""
    from . import hardware
    try:
        s = hardware.make("insert", size=m)["shape"]
        bb = s.bounding_box()
        s = Pos(0, 0, -bb.max.Z) * s
    except Exception:
        _, _, d, depth, _ = boxmod.SCREWS[m]
        s = Cylinder(d / 2, depth).locate(Location((0, 0, -depth / 2)))
    s = Compound(children=[s])
    s.label = name
    return s


def _stock(length: float) -> int:
    return next((n for n in LENGTHS if n >= length - 0.5), LENGTHS[-1])


def exploded(spec: boxmod.BoxSpec, made: dict, board=None, gap: float = 25.0):
    """The parts, each named and lifted apart, and the parts list (what draftwright should call each)."""
    parts, bom = [], []
    plan = boxmod.screw_plan(spec)
    base = made["base"]
    base.label = "Enclosure base"
    parts.append(base)
    bom.append({"item": "Enclosure base", "qty": 1, "make": "make", "note": f"{spec.material}, printed"})
    top = spec.base_height()
    seat = spec.floor + spec.standoff_height
    lift = 0.0
    if spec.standoffs:
        if board is None:
            xs = [p[0] for p in spec.standoffs]
            ys = [p[1] for p in spec.standoffs]
            bl, bw = max(xs) - min(xs) + 12, max(ys) - min(ys) + 12
            board = Pos((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, seat + 0.8) * Box(bl, bw, 1.6)
            bom.append({"item": "PCB", "qty": 1, "make": "buy", "note": "placeholder: your board"})
        else:
            bom.append({"item": "PCB", "qty": 1, "make": "buy", "note": "your board, with parts"})
        lift = gap
        board = Pos(0, 0, lift) * board
        board.label = "PCB"
        parts.append(board)
        if spec.standoff_hole != "pin":
            m = spec.standoff_screw
            length = plan["board"]["length"]
            name = f"{m}x{length:g} screw"
            for i, (x, y) in enumerate(spec.standoffs):
                s = Pos(x, y, seat + 1.6 + lift + gap * 0.6) * _screw(m, length, name)
                parts.append(s)
                if spec.standoff_hole == "insert":
                    parts.append(Pos(x, y, seat + gap * 0.35) * _insert(m, f"{m} heat-set insert"))
            kind = "into heat-set inserts" if spec.standoff_hole == "insert" else "self-tapping" if spec.standoff_hole == "tap" else "with nuts"
            bom.append({"item": name, "qty": len(spec.standoffs), "make": "buy", "note": f"board screws, {kind}"})
            if spec.standoff_hole == "insert":
                bom.append({"item": f"{m} heat-set insert", "qty": len(spec.standoffs), "make": "buy", "note": "in the standoffs"})
    lid = made.get("lid")
    if lid is not None:
        lid_lift = lift + gap * (2.2 if spec.standoffs else 1.0)
        lid = Pos(0, 0, lid_lift) * lid
        lid.label = "Enclosure lid"
        parts.append(lid)
        bom.append({"item": "Enclosure lid", "qty": 1, "make": "make", "note": f"{spec.material}, printed"})
        if spec.lid in ("screw", "clamshell"):
            m = spec.lid_screw
            length = plan["lid"]["length"] if "lid" in plan else _stock(spec.lid_thickness / 2 + boxmod.SCREWS[m][3])
            name = f"{m}x{length:g} screw"
            L, W, _ = spec.inner
            boss = boxmod._post_boss(spec, spec.hole(m, spec.lid_screw_hole)[0])
            for sx in (-1, 1):
                for sy in (-1, 1):
                    s = Pos(sx * (L / 2 - boss / 2), sy * (W / 2 - boss / 2), top + spec.lid_thickness / 2 + lid_lift + gap * 0.6) * _screw(m, length, name)
                    parts.append(s)
                    if spec.lid_screw_hole == "insert" and spec.lid == "screw":
                        parts.append(Pos(sx * (L / 2 - boss / 2), sy * (W / 2 - boss / 2), top + lift * 0 + gap * 0.35) * _insert(m, f"{m} heat-set insert"))
            bom.append({"item": name, "qty": 4, "make": "buy", "note": "lid screws"})
            if spec.lid_screw_hole == "insert":
                bom.append({"item": f"{m} heat-set insert", "qty": 4, "make": "buy", "note": "in the corner posts"})
        if spec.gasket:
            bom.append({"item": f"O-ring cord Ø{spec.gasket:g} mm", "qty": 1, "make": "buy", "note": "in the lid's groove"})
    if spec.feet:
        bom.append({"item": f"Rubber foot Ø{spec.feet:g} mm", "qty": 4, "make": "buy", "note": "stick-on"})
    for c in spec.cutouts:
        if c.get("preset") and c["preset"] not in ("usb-c", "drain"):  # panel parts, not the board's own
            bom.append({"item": c["preset"], "qty": 1, "make": "buy", "note": f"panel part, {c['face']} face"})
    merged = {}
    for row in bom:
        if row["item"] in merged:
            m = merged[row["item"]]
            m["qty"] += row["qty"]
            if row["note"] not in m["note"]:
                m["note"] += "; " + row["note"]
        else:
            merged[row["item"]] = dict(row)
    whole = Compound(children=parts)
    whole.label = "Enclosure assembly"
    return whole, list(merged.values())


def make(spec: boxmod.BoxSpec, out, board_step=None, standard: str = "asme") -> dict:
    """The exploded assembly STEP, the parts list (CSV), and draftwright's assembly drawing."""
    import csv
    from . import drawing, geom
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    made = boxmod.build(spec)
    board = None
    if board_step:
        # The board as KiCad exported it, moved onto the standoffs.
        from . import fit as fitmod
        solids = geom.step_names(board_step)
        pcb = fitmod.pcb_of(solids)
        holes = fitmod.mounting_holes(pcb.shape)
        (bx0, by0, bz0), (bx1, by1, _) = geom.bbox(pcb.shape)
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        if spec.standoffs:
            sx = sum(p[0] for p in spec.standoffs) / len(spec.standoffs)
            sy = sum(p[1] for p in spec.standoffs) / len(spec.standoffs)
            hx = sum(h[0] for h in holes) / len(holes) if holes else cx
            hy = sum(h[1] for h in holes) / len(holes) if holes else cy
            dx, dy = sx - hx, sy - hy
        else:
            dx, dy = -cx, -cy
        # Just the board itself: its parts would each be a separate item in the parts list.
        board = Pos(dx, dy, spec.floor + spec.standoff_height - bz0) * pcb.shape
    assembly, bom = exploded(spec, made, board)
    step = out / "exploded.step"
    export_step(assembly, str(step))
    with open(out / "parts_list.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item", "qty", "make", "note"])
        w.writeheader()
        for i, row in enumerate(bom, 1):
            w.writerow(row)
    files = {"step": str(step), "parts_list": str(out / "parts_list.csv")}
    notes = []
    try:
        exe = drawing.find_draftwright()
        spec_path = out / "pack.spec.json"
        spec_path.write_text(json.dumps({"schema": "draftwright.pack-spec/1",
                                         "ga": {"horizontal_axis": "x", "drawing": {"sheet": {
                                             "standard": standard, "title": {"title": "ENCLOSURE ASSEMBLY", "number": "ENC-ASSY"}}}}},
                                        indent=2) + "\n")
        r = subprocess.run([exe, "pack", str(step), "--spec", str(spec_path), "-o", str(out / "pack"), "--formats", "pdf,csv"],
                           capture_output=True, text=True)
        if r.returncode == 0 and (out / "pack" / "pack.pdf").exists():
            files["drawing"] = str(out / "pack" / "pack.pdf")
            files["pack_csv"] = str(out / "pack" / "pack.csv")
        else:
            notes.append("draftwright could not draw the assembly: " + (r.stderr or r.stdout).strip()[-400:])
    except RuntimeError as e:
        notes.append(str(e))
    return {"files": files, "parts_list": bom, "notes": notes}
