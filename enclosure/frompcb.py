"""A box around a board: the other way round from `limits`.

Give it KiCad's STEP export of the board (File > Export > STEP, with its 3D models) and it makes
the quick box that fits it:

- the inside is the board plus a gap on each side; on an edge with a connector, the wall moves in
  as far as the board allows so the connector's face sits close to the outside, where a plug
  reaches it;
- a standoff under every mounting hole, for the screw that hole takes, tall enough to clear the
  parts underneath;
- the inside height clears the tallest part, plus headroom and the lid's lip;
- an opening in front of every part that reaches an edge (connectors, terminal blocks, buttons
  set at the edge), its size the part's face plus a margin, or the datasheet cutout from
  parts.json when there is one.

The result is an ordinary box (`box.json`), so every setting can be changed afterwards, and it is
checked with `fit` before it is handed back.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import box as boxmod
from . import fit as fitmod
from .geom import bbox, step_names

# Board hole to the screw it takes (ISO 273 medium clearance holes, with some slack).
HOLE_SCREW = [(2.6, "M2"), (3.1, "M2.5"), (3.8, "M3"), (5.0, "M4")]


@dataclass
class Settings:
    wall: float = 2.0
    floor: float = 2.0
    lid: str = "screw"
    edge_gap: float = 1.0  # board edge to the inside of a wall, where nothing pokes out
    min_edge_gap: float = 0.5  # the least, on an edge where a connector pulls the wall in
    setback: float = 0.5  # how far behind the outside a connector's face should sit, ideally
    reach: float = 1.5  # a part this close to an edge (or past it) gets an opening
    margin: float = 0.5  # around a part's face in its opening, per side
    standoff_height: float = 5.0
    under_gap: float = 1.5  # below the lowest part under the board
    headroom: float = 2.0  # above the tallest part
    connector_prefixes: tuple = ("J", "P", "CN", "USB", "SW", "BT", "LED", "D")


def screw_for(hole: float) -> str:
    for top, screw in HOLE_SCREW:
        if hole <= top:
            return screw
    return "M4"


def _edges(pb):
    (x0, y0, _), (x1, y1, _) = pb
    return {"-X": x0, "+X": x1, "-Y": y0, "+Y": y1}


def _reach(face: str, part, edges) -> float:
    """How far past the board edge on *face* the part reaches (negative: short of it)."""
    (px0, py0, _), (px1, py1, _) = part
    return {"-X": edges["-X"] - px0, "+X": px1 - edges["+X"], "-Y": edges["-Y"] - py0, "+Y": py1 - edges["+Y"]}[face]


def design(board_step, settings: Settings | None = None, specs: dict | None = None,
           footprints: dict | None = None):
    """The BoxSpec that fits the board, and notes on why each choice was made."""
    s = settings or Settings()
    solids = step_names(board_step)
    pcb = fitmod.pcb_of(solids)
    pb = bbox(pcb.shape)
    (bx0, by0, bz0), (bx1, by1, bz1) = pb
    thick = bz1 - bz0
    edges = _edges(pb)
    parts = [n for n in solids if n is not pcb]
    holes = fitmod.mounting_holes(pcb.shape)
    if not holes:
        raise ValueError("no mounting holes found in the board (round holes 1.9 to 5.5 mm through it)")
    notes = []

    # Heights, from the board's top and bottom.
    tops = [bbox(p.shape)[1][2] - bz1 for p in parts if bbox(p.shape)[1][2] > bz1 + 0.01]
    bottoms = [bz0 - bbox(p.shape)[0][2] for p in parts if bbox(p.shape)[0][2] < bz0 - 0.01]
    tallest = max(tops, default=0.0)
    under = max(bottoms, default=0.0)
    so_h = max(s.standoff_height, round(under + s.under_gap, 1))
    if under:
        notes.append(f"standoffs {so_h:g} mm tall: the lowest part hangs {under:.1f} mm under the board")

    # Openings: parts at an edge, on the face they reach.
    openings, reach = [], {}
    for p in parts:
        name = p.name.split(" ")[0]
        pbb = bbox(p.shape)
        face = max(("-X", "+X", "-Y", "+Y"), key=lambda f: _reach(f, pbb, edges))
        r = _reach(face, pbb, edges)
        if r < -s.reach or not (name.upper().startswith(s.connector_prefixes) or r > 0):
            continue
        openings.append((name, face, pbb, r))
        reach[face] = max(reach.get(face, r), r)

    # The inside: the board plus a gap on each side. On a face with a connector, the wall comes in
    # so the connector's face sits `setback` behind the outside (setback = gap + wall - reach),
    # but never closer to the board edge than min_edge_gap.
    gap = {}
    for f in ("-X", "+X", "-Y", "+Y"):
        if f in reach:
            gap[f] = min(s.edge_gap, max(s.min_edge_gap, s.setback + reach[f] - s.wall))
            setback = gap[f] + s.wall - reach[f]
            notes.append(f"{f} wall {gap[f]:.2f} mm from the board edge: the connector's face sits "
                         f"{setback:.2f} mm behind the outside" + ("" if setback <= 2.0 else
                         " (more than 2 mm: a plug may not reach; use a thinner wall or move the part out)"))
        else:
            gap[f] = s.edge_gap

    # A screw lid's corner posts fill a square in each inside corner: grow the box along the axis
    # with fewer connectors until the board's corners clear them.
    if s.lid == "screw":
        boss = boxmod._post_boss(boxmod.BoxSpec(lid="screw"), boxmod.BoxSpec().hole("M3", "insert")[0])
        need_x = boss - min(gap["-X"], gap["+X"]) + 0.5
        need_y = boss - min(gap["-Y"], gap["+Y"]) + 0.5
        on_x = sum(f in reach for f in ("-X", "+X"))
        on_y = sum(f in reach for f in ("-Y", "+Y"))
        axis = "Y" if on_y < on_x or (on_y == on_x and need_y <= need_x) else "X"
        for f in (("-Y", "+Y") if axis == "Y" else ("-X", "+X")):
            if f in reach:
                notes.append(f"the {f} wall moved out {boss + 0.5:.1f} mm for the lid's corner posts, so its connector sits further back")
            gap[f] = max(gap[f], boss + 0.5)
        notes.append(f"the box is {2 * (boss + 0.5):.0f} mm longer in {axis} than the board needs, for the screw lid's "
                     f"corner posts; a press-fit or snap lid avoids that")

    ix0, ix1 = bx0 - gap["-X"], bx1 + gap["+X"]
    iy0, iy1 = by0 - gap["-Y"], by1 + gap["+Y"]
    cx, cy = (ix0 + ix1) / 2, (iy0 + iy1) / 2
    lip = 3.0 if s.lid in ("screw", "friction", "snap") else 0.0
    height = so_h + thick + tallest + s.headroom + lip
    L, W, H = round(ix1 - ix0, 2), round(iy1 - iy0, 2), round(height, 1)
    notes.insert(0, f"inside {L:g} x {W:g} x {H:g} mm: the board {bx1 - bx0:.1f} x {by1 - by0:.1f} mm, the tallest part "
                 f"{tallest:.1f} mm above it, {s.headroom:g} mm headroom" + (f" and the lid's {lip:g} mm lip" if lip else ""))

    standoffs = [[round(x - cx, 3), round(y - cy, 3)] for x, y, _ in holes]
    screws = {screw_for(d) for *_, d in holes}
    screw = max(screws, key=lambda m: float(m[1:]))
    if len(screws) > 1:
        notes.append(f"mounting holes take different screws ({', '.join(sorted(screws))}); standoffs are for {screw}")

    # The board's top sits at floor + so_h + thick; parts' z in the box frame follows.
    z_shift = s.floor + so_h - bz0  # board STEP z to box z
    cutouts = []
    for name, face, (p0, p1), r in openings:
        spec = (specs or {}).get(name)
        lo_z, hi_z = p0[2] + z_shift, p1[2] + z_shift
        if face in ("-X", "+X"):
            span = (p0[1], p1[1])
        else:
            span = (p0[0], p1[0])
        w = span[1] - span[0] + 2 * s.margin
        h = hi_z - lo_z + 2 * s.margin
        if spec is not None and spec.cutout:
            w = max(w, spec.cutout.get("width", 0))
            h = max(h, spec.cutout.get("height", 0))
        along_mid = (span[0] + span[1]) / 2 - (cy if face in ("-X", "+X") else cx)
        up = (lo_z + hi_z) / 2 - s.floor
        # Along a wall, `at[0]` runs with the axis on the front and right walls, against it on the
        # back and left (the box's own convention, looking at each wall from outside, is not used:
        # positions are box X or Y).
        cut = {"face": face, "shape": "rect", "size": [round(w, 2), round(h, 2)], "radius": round(min(1.0, w / 4, h / 4), 2),
               "at": [round(along_mid, 2), round(up, 2)]}
        cutouts.append(cut)
        notes.append(f"opening for {name} in the {face} wall: {w:.1f} x {h:.1f} mm "
                     f"({'its datasheet cutout' if spec is not None and spec.cutout else 'its face plus ' + format(s.margin, 'g') + ' mm a side'})")
    spec = boxmod.BoxSpec(size=[L, W, H], wall=s.wall, floor=s.floor, lid=s.lid, standoffs=standoffs,
                          standoff_height=so_h, standoff_screw=screw, cutouts=cutouts, teardrop=False)
    frame = {"board_to_box": [-cx, -cy, z_shift], "board_bounds": [list(pb[0]), list(pb[1])]}
    return spec, notes, frame


def make(board_step, settings: Settings | None = None, specs: dict | None = None, footprints: dict | None = None):
    """Design the box, build it, and check the board in it."""
    from . import shell
    spec, notes, frame = design(board_step, settings, specs, footprints)
    spec.check()
    made = boxmod.build(spec)
    enc, _ = shell.read(made["base"], made["lid"])
    result = fitmod.check(enc, made["base"], made["lid"], step_names(board_step), fitmod.Settings(), None,
                          specs or {}, footprints)
    return {"spec": spec, "notes": notes, "made": made, "enclosure": enc, "fit": result, "frame": frame}
