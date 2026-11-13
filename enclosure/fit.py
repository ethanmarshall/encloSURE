"""Checking a board against its enclosure.

The board comes as a STEP file (KiCad: File > Export > STEP, or `kicad-cli pcb export step`),
in its own frame: the PCB from z = 0 up, parts named by reference. EncloSURE places it on the
standoffs by matching its mounting holes to them (or where `place` says), then checks the
mounting holes, collisions, clearance to the walls, headroom under the lid, and that each
opening has its connector or button lined up behind it.

Moves are given two ways: in the enclosure's frame, and as a KiCad move (KiCad's Y axis points
down the page, and a KiCad STEP export flips it, so a +Y move in the board's STEP frame is a -Y
move in KiCad).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from build123d import Compound, Box, GeomType, Pos, Rot, Shape

from .geom import Named, bbox, distance, named_solids, overlap_volume
from .shell import Enclosure, board_hole_for


@dataclass
class Settings:
    clearance: float = 0.5  # minimum gap from a part or the board edge to the enclosure
    hole_tolerance: float = 0.15  # a mounting hole this close to its standoff's axis is on it
    opening_margin: float = 0.25  # an opening clears a connector's face by this on each side
    max_setback: float = 2.0  # connector face to the outer wall surface: past this, check the plug reaches
    wall_reach: float = 8.0  # a part this close to a wall is "at" that wall


@dataclass
class Finding:
    severity: str  # error, warning, info
    code: str
    subject: str
    message: str
    fix: str | None = None
    move: list[float] | None = None  # enclosure frame, mm
    kicad_move: list[float] | None = None  # KiCad board frame, mm


@dataclass
class Placement:
    rotation: float  # degrees about Z, board frame to enclosure
    translation: list[float]
    how: str
    matched: list[tuple[int, int]] = field(default_factory=list)  # (board hole, boss)


@dataclass
class Fit:
    placement: Placement
    findings: list[Finding]
    headroom: float | None
    parts: list[dict]
    pcb: Shape | None = None  # placed in the enclosure
    placed: list[Named] = field(default_factory=list)

    def to_json(self) -> dict:
        errors = sum(f.severity == "error" for f in self.findings)
        warnings = sum(f.severity == "warning" for f in self.findings)
        return {
            "fits": errors == 0,
            "errors": errors,
            "warnings": warnings,
            "placement": asdict(self.placement),
            "headroom": self.headroom,
            "findings": [asdict(f) for f in self.findings],
            "parts": self.parts,
        }


def pcb_of(solids: list[Named]) -> Named:
    """The board itself: a solid named like one, else the thin solid with the largest plan area."""
    for s in solids:
        if s.name.upper() in ("PCB", "BOARD") or s.name.lower().endswith(("_pcb", "pcb")):
            return s

    def plan(s: Named):
        (x0, y0, z0), (x1, y1, z1) = bbox(s.shape)
        thin = 0.3 < z1 - z0 < 3.3
        return (thin, (x1 - x0) * (y1 - y0))

    return max(solids, key=plan)


def mounting_holes(pcb: Shape) -> list[tuple[float, float, float]]:
    """(x, y, diameter) of each round through hole between 1.9 and 5.5 mm."""
    (_, _, z0), (_, _, z1) = bbox(pcb)
    thick = z1 - z0
    holes = []
    for face in pcb.faces():
        if face.geom_type != GeomType.CYLINDER:
            continue
        (fx0, fy0, fz0), (fx1, fy1, fz1) = bbox(face)
        if fz1 - fz0 < 0.9 * thick:
            continue
        d = ((fx1 - fx0) + (fy1 - fy0)) / 2
        if not 1.9 <= d <= 5.5 or abs((fx1 - fx0) - (fy1 - fy0)) > 0.1:
            continue
        x, y = (fx0 + fx1) / 2, (fy0 + fy1) / 2
        if not any(math.dist((x, y), h[:2]) < 0.05 for h in holes):
            holes.append((round(x, 4), round(y, 4), round(d, 3)))
    return holes


def _rot(p, deg):
    a = math.radians(deg)
    return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a))


def place(holes, enc: Enclosure, pcb_bottom: float, settings: Settings) -> Placement | None:
    """The rotation (a quarter turn) and translation that put the most holes exactly on standoffs."""
    bosses = enc.bosses
    if not holes or not bosses:
        return None
    best = None
    for deg in (0, 90, 180, 270):
        turned = [_rot(h, deg) for h in holes]
        for i, h in enumerate(turned):
            for b in bosses:
                t = (b.center[0] - h[0], b.center[1] - h[1])
                pairs = []
                for k, hk in enumerate(turned):
                    p = (hk[0] + t[0], hk[1] + t[1])
                    j = min(range(len(bosses)), key=lambda j: math.dist(p, bosses[j].center[:2]))
                    if math.dist(p, bosses[j].center[:2]) <= settings.hole_tolerance:
                        pairs.append((k, j))
                score = len(pairs)
                if best is None or score > best[0]:
                    best = (score, deg, t, pairs)
    score, deg, t, pairs = best
    if score < 2 and not (score == 1 and len(holes) == 1):
        return None
    # Refine on the holes that are on their standoffs, then pair every hole with its nearest.
    turned = [_rot(h, deg) for h in holes]
    tx = sum(bosses[j].center[0] - turned[k][0] for k, j in pairs) / len(pairs)
    ty = sum(bosses[j].center[1] - turned[k][1] for k, j in pairs) / len(pairs)
    matched = []
    for k, hk in enumerate(turned):
        p = (hk[0] + tx, hk[1] + ty)
        j = min(range(len(bosses)), key=lambda j: math.dist(p, bosses[j].center[:2]))
        if math.dist(p, bosses[j].center[:2]) < bosses[j].diameter:
            matched.append((k, j))
    top = max(bosses[j].top for _, j in matched)
    return Placement(deg, [round(tx, 4), round(ty, 4), round(top - pcb_bottom, 4)],
                     f"{len(pairs)} of {len(holes)} mounting holes on standoffs", matched)


def moved(shape: Shape, p: Placement) -> Shape:
    return Pos(*p.translation) * (Rot(0, 0, p.rotation) * shape)


def kicad_move(move, p: Placement):
    """An enclosure-frame move as a move on the KiCad board: undo the turn, flip Y."""
    x, y = _rot(move[:2], -p.rotation)
    return [round(x, 3) + 0.0, round(-y, 3) + 0.0]


def _f(severity, code, subject, message, fix=None, move=None, placement=None):
    km = kicad_move(move, placement) if move is not None and placement is not None else None
    return Finding(severity, code, subject, message, fix,
                   [round(v, 3) + 0.0 for v in move] if move is not None else None, km)


def stand_ins(pcb: Shape, have: set[str], specs: dict, footprints: dict) -> tuple[list[Named], list[str], list[str]]:
    """Blocks for parts the board STEP lacks (no 3D model), sized from parts.json's `body` and
    placed from the .kicad_pcb's footprint (KiCad page (x, y) is the STEP's (x, -y)). Returns the
    blocks, the references given one, and the references that could not be."""
    (_, _, z0), (_, _, z1) = bbox(pcb)
    blocks, made, missing = [], [], []
    for ref, fp in sorted(footprints.items()):
        if ref in have or ref.startswith(("H", "MH", "TP", "FID")) and not specs.get(ref):
            continue
        spec = specs.get(ref)
        if spec is None or not spec.body:
            if not fp.get("has_model"):
                missing.append(ref)
            continue
        if ref in have:
            continue
        length, width, height = spec.body
        side = spec.side or fp["side"]
        zc = z1 + height / 2 if side == "top" else z0 - height / 2
        block = Pos(fp["at"][0], -fp["at"][1], zc) * (Rot(0, 0, fp["rotation"]) * Box(length, width, height))
        blocks.append(Named(ref, block))
        made.append(ref)
    return blocks, made, missing


def check(enc: Enclosure, base: Shape, lid: Shape | None, board,
          settings: Settings | None = None, placement: Placement | None = None,
          specs: dict | None = None, footprints: dict | None = None) -> Fit:
    """*board* is the board's named solids (`geom.step_names`), or one shape. *specs* are the
    project's parts (`parts.load`), *footprints* the board's (`parts.from_board`): together they
    stand in blocks for parts without 3D models, check model heights against datasheets, and
    hold each connector's opening to its datasheet's recommended cutout."""
    settings = settings or Settings()
    specs = specs or {}
    solids = list(board) if isinstance(board, (list, tuple)) else named_solids(board)
    pcb = pcb_of(solids)
    parts = [s for s in solids if s is not pcb]
    holes = mounting_holes(pcb.shape)
    pcb_bottom = bbox(pcb.shape)[0][2]
    findings: list[Finding] = []
    blocks, made, unmodelled = stand_ins(pcb.shape, {s.name for s in parts}, specs, footprints or {})
    parts += blocks
    for ref in made:
        findings.append(_f("info", "datasheet_block", ref,
                           f"no 3D model: checked as a {' × '.join(f'{v:g}' for v in specs[ref].body)} mm block "
                           f"from {specs[ref].source.get('body', 'parts.json')}"))
    for ref in unmodelled:
        findings.append(_f("warning", "unchecked_part", ref,
                           "no 3D model and no body in parts.json: not checked",
                           "add its 3D model in KiCad, or its body from the datasheet to parts.json"))
    pcb_top = bbox(pcb.shape)[1][2]
    for part in parts:
        spec = specs.get(part.name)
        if spec and spec.height and part.name not in made:
            (_, _, pz0), (_, _, pz1) = bbox(part.shape)
            model = pz1 - pcb_top if pz1 > pcb_top else pcb_bottom - pz0
            if abs(model - spec.height) > 0.3:
                findings.append(_f("warning", "model_height_differs", part.name,
                                   f"its 3D model stands {model:.2f} mm; {spec.source.get('height', 'the datasheet')} "
                                   f"says {spec.height:.2f}", "check the model against the datasheet"))

    if placement is None:
        placement = place(holes, enc, pcb_bottom, settings)
    if placement is None:
        raise ValueError(
            f"cannot place the board: {len(holes)} mounting hole(s) found, {len(enc.bosses)} "
            "standoff(s); fewer than two line up. Give the placement (place=x,y,z,rotation)."
        )
    pcb_shape = moved(pcb.shape, placement)
    placed = [Named(s.name, moved(s.shape, placement)) for s in parts]
    p = placement

    # 1. Mounting holes on standoffs.
    turned = [_rot(h, p.rotation) for h in holes]
    used = set()
    for k, j in p.matched:
        boss = enc.bosses[j]
        used.add(j)
        hx, hy = turned[k][0] + p.translation[0], turned[k][1] + p.translation[1]
        dx, dy = boss.center[0] - hx, boss.center[1] - hy
        off = math.hypot(dx, dy)
        name = f"hole at ({holes[k][0]:.2f}, {holes[k][1]:.2f})"
        if off > settings.hole_tolerance:
            findings.append(_f("error", "hole_off_standoff", name,
                               f"{off:.2f} mm off the standoff at ({boss.center[0]:.2f}, {boss.center[1]:.2f})",
                               "move this hole onto the standoff", [dx, dy, 0], p))
        want = board_hole_for(boss.hole)
        if holes[k][2] + 0.05 < want:
            findings.append(_f("warning", "hole_small", name,
                               f"Ø{holes[k][2]:.2f} is under the Ø{want:.1f} clearance for the standoff's "
                               f"{boss.screw or 'screw'}", f"make it Ø{want:.1f}"))
    for k in range(len(holes)):
        if k not in {k for k, _ in p.matched}:
            findings.append(_f("warning", "hole_without_standoff", f"hole at ({holes[k][0]:.2f}, {holes[k][1]:.2f})",
                               "no standoff under this mounting hole"))
    for j, boss in enumerate(enc.bosses):
        if j not in used:
            findings.append(_f("info", "standoff_unused", f"standoff at ({boss.center[0]:.2f}, {boss.center[1]:.2f})",
                               "no board hole on this standoff"))

    # 2. The board edge to the walls (by its outline's box).
    (bx0, by0, _), (bx1, by1, _) = bbox(pcb_shape)
    (wx0, wy0, _), (wx1, wy1, _) = enc.cavity_bounds
    for side, gap, move in (("-X", bx0 - wx0, [1, 0, 0]), ("+X", wx1 - bx1, [-1, 0, 0]),
                            ("-Y", by0 - wy0, [0, 1, 0]), ("+Y", wy1 - by1, [0, -1, 0])):
        if gap < settings.clearance - 0.01:
            need = settings.clearance - gap
            findings.append(_f("error" if gap < 0 else "warning", "board_edge_clearance", f"board edge {side}",
                               f"{gap:.2f} mm from the {side} wall (want {settings.clearance:.2f})",
                               f"pull this edge in {need:.2f} mm", [v * need for v in move], p))

    # The board itself against the enclosure: corner posts, ribs, a gasket ledge (the box check
    # above only sees the walls).
    for label, body in (("base", base), ("lid", lid)):
        if body is None:
            continue
        vol = overlap_volume(pcb_shape, body)
        if vol > 0.05:
            common = pcb_shape & body
            pieces = list(common) if isinstance(common, list) else common.solids()
            where = []
            for piece in pieces[:6]:
                (ox0, oy0, _), (ox1, oy1, _) = bbox(piece)
                where.append(f"({(ox0 + ox1) / 2:.1f}, {(oy0 + oy1) / 2:.1f})")
            findings.append(_f("error", "board_collision", "board",
                               f"runs into the {label} ({vol:.1f} mm³ overlap) at {', '.join(where)} in the enclosure's "
                               f"frame: a corner post, rib or ledge where the board is",
                               "notch the board outline round it (enclosure limits draws the free outline), or move the obstacle"))

    # 3. Parts against the enclosure: overlaps, clearance, headroom.
    ceiling = enc.ceiling
    rows = []
    headroom = None
    enclosure_parts = [("base", base)] + ([("lid", lid)] if lid is not None else [])
    near_wall = {}
    for part in placed:
        (x0, y0, z0), (x1, y1, z1) = bbox(part.shape)
        room = round(ceiling - z1, 3)
        headroom = room if headroom is None else min(headroom, room)
        row = {"part": part.name, "top": round(z1, 3), "headroom": room}
        for label, body in enclosure_parts:
            vol = overlap_volume(part.shape, body)
            if vol > 1e-3:
                over = f"; its top is {-room:.2f} mm above the lid's underside" if label == "lid" and room < 0 else ""
                findings.append(_f("error", "collision", part.name,
                                   f"runs into the {label} ({vol:.1f} mm³ overlap){over}",
                                   (f"a part at most {z1 - z0 + room:.2f} mm tall, or lay it down, or raise the lid"
                                    if over else "move it clear, or cut the enclosure clear")))
                row["collides"] = label
        if "collides" not in row:
            gap = distance(part.shape, base)
            row["gap"] = round(gap, 3)
            if gap < settings.clearance:
                findings.append(_f("warning", "tight", part.name,
                                   f"{gap:.2f} mm from the enclosure (want {settings.clearance:.2f})"))
        if room < 0 and "collides" not in row:
            findings.append(_f("error", "too_tall", part.name,
                               f"{-room:.2f} mm above the {'lid' if enc.lid_underside is not None else 'rim'}"))
        elif 0 <= room < settings.clearance:
            findings.append(_f("warning", "low_headroom", part.name, f"{room:.2f} mm under the "
                               f"{'lid' if enc.lid_underside is not None else 'rim'}"))
        for side, gap in (("-X", x0 - wx0), ("+X", wx1 - x1), ("-Y", y0 - wy0), ("+Y", wy1 - y1)):
            if gap < settings.wall_reach and not part.name.upper().startswith("PCB"):  # a stacked board's plate
                near_wall.setdefault(side, []).append(part)
        rows.append(row)

    # 4. Openings: what sits behind each.
    behind = set()
    empty: dict[str, list] = {}  # wall openings with nothing behind them
    for o in enc.openings:
        if o.wall in ("-X", "+X", "-Y", "+Y"):
            axis = 0 if o.wall in ("-X", "+X") else 1
            along = 1 - axis
            best = None
            for part in near_wall.get(o.wall, []):
                (a0, a1), (z0, z1) = _span(part.shape, along), _span(part.shape, 2)
                lo, hi = o.center[along] - o.width / 2, o.center[along] + o.width / 2
                zlo, zhi = o.center[2] - o.height / 2, o.center[2] + o.height / 2
                overlap = min(a1, hi) - max(a0, lo)
                if overlap > 0 and min(z1, zhi) - max(z0, zlo) > 0:
                    if best is None or overlap > best[0]:
                        best = (overlap, part, (a0, a1), (z0, z1))
            if best is None:
                empty.setdefault(o.wall, []).append(o)
                findings.append(_f("warning", "opening_empty", f"{o.wall} opening at {_xyz(o.center)}",
                                   f"{o.width:.2f} × {o.height:.2f} mm, nothing behind it"))
                continue
            _, part, (a0, a1), (z0, z1) = best
            behind.add(part.name)
            spec = specs.get(part.name)
            cut = spec.cutout if spec else None
            m = 0.0 if cut else settings.opening_margin
            if cut and (o.width + 0.05 < cut["width"] or o.height + 0.05 < cut["height"]):
                findings.append(_f("error", "opening_below_datasheet", f"{part.name} at {o.wall} opening",
                                   f"the opening is {o.width:.2f} × {o.height:.2f} mm; {spec.source.get('cutout', 'its datasheet')} "
                                   f"calls for {cut['width']:.2f} × {cut['height']:.2f}",
                                   f"open it to {cut['width']:.2f} × {cut['height']:.2f} mm"))
            lo, hi = o.center[along] - o.width / 2, o.center[along] + o.width / 2
            zlo, zhi = o.center[2] - o.height / 2, o.center[2] + o.height / 2
            shift_a = (o.center[along] - (a0 + a1) / 2)
            shift_z = (o.center[2] - (z0 + z1) / 2)
            fits_a = a0 >= lo + m - 1e-6 and a1 <= hi - m + 1e-6
            fits_z = z0 >= zlo + m - 1e-6 and z1 <= zhi - m + 1e-6
            move = [0.0, 0.0, 0.0]
            move[along] = shift_a
            if not fits_a or not fits_z:
                too_small = not cut and ((a1 - a0) + 2 * m > o.width + 1e-6 or (z1 - z0) + 2 * m > o.height + 1e-6)
                if too_small:
                    want_w = (a1 - a0) + 2 * m
                    want_h = (z1 - z0) + 2 * m
                    findings.append(_f("error", "opening_too_small", f"{part.name} at {o.wall} opening",
                                       f"its face is {a1 - a0:.2f} × {z1 - z0:.2f} mm; the opening is "
                                       f"{o.width:.2f} × {o.height:.2f}",
                                       f"open it to at least {want_w:.2f} × {want_h:.2f} mm"))
                else:
                    msg = []
                    if not fits_a:
                        msg.append(f"{abs(shift_a):.2f} mm off centre sideways")
                    if not fits_z:
                        msg.append(f"{abs(shift_z):.2f} mm off centre in height")
                    fix = f"move {part.name} {abs(shift_a):.2f} mm to centre it" if not fits_a else None
                    if not fits_z:
                        fix = ((fix + "; ") if fix else "") + (
                            f"move the opening {shift_z:+.2f} mm in Z (or change the standoff height)")
                    findings.append(_f("error", "opening_misaligned", f"{part.name} at {o.wall} opening",
                                       ", ".join(msg), fix, move if not fits_a else None, p))
            # How far its face sits back from the outside surface.
            front = _span(part.shape, axis)[0 if o.wall.startswith("-") else 1]
            setback = abs(front - o.outer)
            limit = (cut or {}).get("max_setback", settings.max_setback)
            if setback > limit:
                findings.append(_f("warning", "connector_setback", part.name,
                                   f"its face is {setback:.2f} mm in from the outside of the {o.wall} wall: "
                                   "check the mating plug reaches",
                                   f"bring it {setback - limit:.2f} mm closer to the wall"))
        else:
            # Floor and lid openings: a part under a lid opening (a button), or over a floor one.
            under = [part for part in placed
                     if _span(part.shape, 0)[0] < o.center[0] < _span(part.shape, 0)[1]
                     and _span(part.shape, 1)[0] < o.center[1] < _span(part.shape, 1)[1]]
            if o.wall == "lid":
                if not under:
                    findings.append(_f("warning", "opening_empty", f"lid opening at {_xyz(o.center)}",
                                       f"{o.width:.2f} × {o.height:.2f} mm, nothing under it"))
                for part in under:
                    behind.add(part.name)
                    gap = (o.center[2]) - _span(part.shape, 2)[1]
                    findings.append(_f("info", "under_lid_opening", part.name,
                                       f"{gap:.2f} mm below the lid at its opening: the cap or actuator spans this"))

    # 5. Connectors at a wall with no opening.
    for side, ps in near_wall.items():
        for part in ps:
            if part.name.upper().startswith(("J", "USB", "P")) and not part.name.upper().startswith("PCB") and part.name not in behind:
                # An empty opening on the same wall: line the connector up with the nearest one.
                along = 1 if side in ("-X", "+X") else 0
                (a0, a1), (z0, z1) = _span(part.shape, along), _span(part.shape, 2)
                spare = sorted(empty.get(side, []), key=lambda o: abs(o.center[along] - (a0 + a1) / 2))
                o = next((o for o in spare if (a1 - a0) <= o.width + 1e-6 and (z1 - z0) <= o.height + 1e-6), None)
                if o is None:
                    findings.append(_f("warning", "connector_no_opening", part.name,
                                       f"sits at the {side} wall with no opening in front of it"))
                    continue
                empty[side].remove(o)
                move = [0.0, 0.0, 0.0]
                move[along] = o.center[along] - (a0 + a1) / 2
                dz = o.center[2] - (z0 + z1) / 2
                fix = f"move {part.name} {abs(move[along]):.2f} mm along the wall onto the opening at {_xyz(o.center)}"
                if abs(dz) > 0.3:
                    fix += f"; the opening is also {dz:+.2f} mm off in height (move it, or change the standoffs)"
                findings.append(_f("warning", "connector_no_opening", part.name,
                                   f"sits at the {side} wall beside an empty opening, not in it", fix, move, p))

    # 6. Getting it in: the board drops in from above, past whatever stands over it.
    findings += insertion(enc, base, pcb_shape, placed, settings, p)

    # A connector in its opening sits close to the wall by design: its fit is the opening check.
    findings = [f for f in findings if not (f.code == "tight" and f.subject in behind)]
    findings.sort(key=lambda f: ({"error": 0, "warning": 1, "info": 2}[f.severity], f.code, f.subject))
    return Fit(placement, findings, headroom, rows, pcb_shape, placed)


def insertion(enc, base, pcb_shape, placed, settings, placement=None) -> list:
    """Can the board go in? It is lowered from above the rim to where it sits. Anything of the base
    over the board's footprint (a ledge, a post, a guide) stops it; a connector reaching into a wall
    opening needs the board shifted away from that wall while it drops, then slid back; with
    connectors through opposite walls it can't go in without flexing the walls."""
    from build123d import Box as _Box, Pos as _Pos
    out = []
    rim = enc.rim
    (cx0, cy0, _), (cx1, cy1, _) = enc.cavity_bounds
    pieces = [Named("board", pcb_shape)] + list(placed)
    # Straight down: each piece's box swept up to the rim, against the base (walls excluded by the cavity box).
    blockers = []
    for pc in pieces:
        (x0, y0, z0), (x1, y1, z1) = bbox(pc.shape)
        x0, y0, x1, y1 = max(x0, cx0 + 0.05), max(y0, cy0 + 0.05), min(x1, cx1 - 0.05), min(y1, cy1 - 0.05)
        if x1 <= x0 or y1 <= y0 or z1 >= rim:
            continue
        prism = _Pos((x0 + x1) / 2, (y0 + y1) / 2, (z1 + rim + 1) / 2) * _Box(x1 - x0, y1 - y0, rim + 1 - z1)
        if pc.name == "board":
            # The board's own outline (it may be notched round posts), swept up from its top face.
            from build123d import Axis as _Axis, extrude as _extrude
            tops = [f for f in pc.shape.faces() if f.normal_at().Z > 0.99]
            if tops:
                top = max(tops, key=lambda f: f.area)
                prism = _extrude(top, amount=rim + 1 - top.center().Z) & _Pos((x0 + x1) / 2, (y0 + y1) / 2, rim / 2) * _Box(x1 - x0, y1 - y0, rim * 3)
        v = overlap_volume(prism, base)
        if v > 0.5:
            hit = prism & base
            hb = bbox(hit)
            blockers.append((pc.name, v, ((hb[0][0] + hb[1][0]) / 2, (hb[0][1] + hb[1][1]) / 2, hb[0][2])))
    for name, v, (hx, hy, hz) in blockers[:6]:
        out.append(_f("error", "insertion_blocked", name,
                      f"something of the base stands over it at ({hx:.1f}, {hy:.1f}), {hz:.1f} mm up: lowering the board "
                      "in from above would catch on it", "move the post, ledge or guide, or plan to tilt the board past it"))
    # Connectors into wall openings: how far each reaches past the walls.
    reach = {"-X": 0.0, "+X": 0.0, "-Y": 0.0, "+Y": 0.0}
    for pc in placed:
        (x0, y0, _), (x1, y1, _) = bbox(pc.shape)
        reach["-X"] = max(reach["-X"], cx0 - x0)
        reach["+X"] = max(reach["+X"], x1 - cx1)
        reach["-Y"] = max(reach["-Y"], cy0 - y0)
        reach["+Y"] = max(reach["+Y"], y1 - cy1)
    reach = {k: v for k, v in reach.items() if v > 0.05}
    if not reach:
        return out
    (bx0, by0, _), (bx1, by1, _) = bbox(pcb_shape)
    whole = [bbox(pc.shape) for pc in pieces]
    lo_x, hi_x = min(b[0][0] for b in whole), max(b[1][0] for b in whole)
    lo_y, hi_y = min(b[0][1] for b in whole), max(b[1][1] for b in whole)
    for a, b_, lo, hi, c0, c1 in (("-X", "+X", lo_x, hi_x, cx0, cx1), ("-Y", "+Y", lo_y, hi_y, cy0, cy1)):
        if a in reach and b_ in reach and reach[a] + reach[b_] <= 0.3:
            continue  # a tenth or two: nothing worth saying
        if a in reach and b_ in reach and reach[a] + reach[b_] <= 0.6:
            out.append(_f("info", "insertion_flex", f"{a} and {b_} connectors",
                          f"parts reach {reach[a]:.1f} and {reach[b_]:.1f} mm into the {a} and {b_} openings: the walls flex that "
                          "much as the board goes in"))
            continue
        if a in reach and b_ in reach:
            out.append(_f("error", "insertion_both_walls", f"{a} and {b_} connectors",
                          f"parts reach {reach[a]:.1f} mm through {a} and {reach[b_]:.1f} mm through {b_}: the board can't be "
                          "lowered in or slid into both openings", "move one connector back inside the wall, or split the box (clamshell)"))
            continue
        for side in (a, b_):
            if side not in reach:
                continue
            p_ = reach[side] + 0.3
            # Shift away from that wall by p_: does everything still fit across the cavity?
            span = (hi - lo) - reach[side]
            if span + p_ <= (c1 - c0) + 1e-6:
                out.append(_f("info", "insertion_slide", f"{side} connectors",
                              f"they reach {reach[side]:.1f} mm into the {side} wall: lower the board in {p_:.1f} mm toward the "
                              f"far wall, then slide it into the opening"))
            else:
                need = span + p_ - (c1 - c0)
                out.append(_f("warning", "insertion_tilt", f"{side} connectors",
                              f"they reach {reach[side]:.1f} mm into the {side} wall but there is only room to shift "
                              f"{p_ - need:.1f} mm: it has to go in tilted, connectors first",
                              f"make the cavity {need:.1f} mm longer that way, or check the tilt on the real board"))
    return out


def _span(shape: Shape, axis: int):
    (a, b) = bbox(shape)
    return a[axis], b[axis]


def _xyz(v):
    return "(" + ", ".join(f"{c:.2f}" for c in v) + ")"
