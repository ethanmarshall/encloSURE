"""A round enclosure: a cylinder with a screw-on cap. The thread is a coarse ISO profile (3 mm pitch
by default) on the outside of the body's neck and the inside of the cap, with clearance for printing,
so it screws on by hand. Standoffs on a circle, holes in the side by angle and height, holes in the cap."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from build123d import Align, Box, Cylinder, Pos, Rot, chamfer, Axis


@dataclass
class Round:
    inside_d: float = 70.0
    height: float = 40.0  # inside, floor to the cap's underside
    wall: float = 2.4
    floor: float = 2.4
    pitch: float = 3.0
    thread_len: float = 8.0
    clearance: float = 0.3  # radial, each thread
    cap_top: float = 2.4
    standoffs: int = 0  # how many, on a circle
    standoff_circle: float = 0.0  # its diameter; 0: 70% of the inside
    standoff_height: float = 5.0
    standoff_screw: str = "M3"
    side_holes: list[dict] = field(default_factory=list)  # {angle (deg, 0 = +X), height, d}
    cap_holes: list[dict] = field(default_factory=list)  # {at: [x, y], d}
    grip: bool = True  # ridges round the cap

    def check(self):
        if not 20 <= self.inside_d <= 300:
            raise ValueError("inside diameter: 20 to 300 mm")
        if not 10 <= self.height <= 300:
            raise ValueError("height: 10 to 300 mm")
        if not 1.6 <= self.wall <= 8:
            raise ValueError("wall: 1.6 to 8 mm")
        if not 1.5 <= self.pitch <= 5:
            raise ValueError("thread pitch: 1.5 to 5 mm")
        if self.thread_len < 2 * self.pitch:
            raise ValueError("thread length: at least two turns")


def build(r: Round) -> dict:
    from bd_warehouse.thread import IsoThread
    from .box import SCREWS
    r.check()
    ri = r.inside_d / 2
    ro = ri + r.wall
    depth = 0.6134 * r.pitch  # ISO thread depth (external)
    neck_ro = ro  # the neck's outside is the thread's root
    major = 2 * (neck_ro + depth)
    body_h = r.floor + r.height
    # Body: floor and wall, a shoulder below the neck so the cap seats on it.
    shoulder_ro = ro + depth + r.wall + r.clearance
    body = Cylinder(shoulder_ro, body_h - r.thread_len, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body += Pos(0, 0, body_h - r.thread_len) * Cylinder(neck_ro + 0.01, r.thread_len, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body -= Pos(0, 0, r.floor) * Cylinder(ri, body_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    ext = IsoThread(major, r.pitch, r.thread_len - 0.5, external=True, end_finishes=("fade", "fade"),
                    manufacturing_compensation=r.clearance)
    body = body.fuse(Pos(0, 0, body_h - r.thread_len + 0.25) * ext)
    try:
        body = chamfer(body.edges().group_by(Axis.Z)[0], 0.4)
    except Exception:
        pass
    notes = [f"round box: Ø{r.inside_d:g} x {r.height:g} mm inside, Ø{2 * shoulder_ro:.1f} mm outside; a screw-on cap "
             f"with an M{major:.0f} x {r.pitch:g} thread, {r.clearance:g} mm clearance each side, {r.thread_len:g} mm long"]
    # Cap: top and a skirt with the internal thread.
    cap_ro = shoulder_ro
    cap_h = r.cap_top + r.thread_len
    cap = Cylinder(cap_ro, cap_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    cap -= Cylinder(major / 2 + r.clearance + 0.02, r.thread_len + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    inner = IsoThread(major, r.pitch, r.thread_len - 0.5, external=False, end_finishes=("fade", "fade"),
                      manufacturing_compensation=r.clearance)
    cap = cap.fuse(Pos(0, 0, 0.25) * inner)
    if r.grip:
        n = max(12, int(2 * math.pi * cap_ro / 4))
        for i in range(n):
            cap -= Rot(0, 0, 360 * i / n) * Pos(cap_ro + 0.3, 0, 0) * Cylinder(0.9, cap_h * 3)
    for hole in r.cap_holes:
        x, y = hole.get("at", [0, 0])
        cap -= Pos(x, y, 0) * Cylinder(float(hole["d"]) / 2, cap_h * 3)
    # Standoffs.
    if r.standoffs:
        circ = r.standoff_circle or 0.7 * r.inside_d
        _, pilot, insert, ins_depth, _ = SCREWS[r.standoff_screw]
        for i in range(r.standoffs):
            a = 2 * math.pi * i / r.standoffs
            x, y = circ / 2 * math.cos(a), circ / 2 * math.sin(a)
            body += Pos(x, y, r.floor - 0.01) * Cylinder(insert / 2 + 2.0, r.standoff_height, align=(Align.CENTER, Align.CENTER, Align.MIN))
            body -= Pos(x, y, r.floor + r.standoff_height - ins_depth - 0.5) * Cylinder(insert / 2, ins_depth + 1,
                                                                                       align=(Align.CENTER, Align.CENTER, Align.MIN))
        notes.append(f"{r.standoffs} standoffs on a Ø{circ:g} mm circle, {r.standoff_height:g} mm tall, {r.standoff_screw} inserts")
    for hole in r.side_holes:
        a = math.radians(float(hole.get("angle", 0)))
        z = r.floor + float(hole.get("height", r.height / 2))
        if z + float(hole["d"]) / 2 > body_h - r.thread_len - 1:
            raise ValueError("a side hole runs into the thread: lower it")
        tool = Cylinder(float(hole["d"]) / 2, r.wall * 6 + 10, rotation=(0, 90, 0))
        body -= Pos(0, 0, z) * (Rot(0, 0, math.degrees(a)) * Pos(ro, 0, 0) * tool)
    notes.append("print the body upright and the cap top down; both without supports. Grease the thread lightly, or "
                 "print the cap in PETG and the body in PLA so they don't gall")
    return {"base": body, "lid": Pos(0, 0, body_h - r.thread_len) * cap,  # screwed on
            "cap_print": Rot(180, 0, 0) * cap, "notes": notes, "outside_d": round(2 * shoulder_ro, 2),
            "outside_h": round(body_h + r.cap_top, 2)}


def write(r: Round, folder) -> dict:
    from build123d import export_step, export_stl
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    m = build(r)
    export_step(m["base"], str(folder / "round_body.step"))
    export_step(m["lid"], str(folder / "round_cap.step"))
    export_stl(m["base"], str(folder / "round_body.stl"))
    export_stl(m["cap_print"], str(folder / "round_cap.stl"))
    (folder / "notes.md").write_text("# Round box\n\n" + "\n".join(f"- {n}" for n in m["notes"]) + "\n", encoding="utf-8")
    return {"notes": m["notes"]}
