"""Writing the enclosure's limits into a KiCad board (a .kicad_pcb written as text; no KiCad needed).

The board gets:
- an Edge.Cuts outline: the cavity at board height, inset by the clearance;
- a mounting hole on each standoff, sized for its screw, with a keepout ring for the screw head;
- notes on User.1: the tallest part allowed on top (to the lid, or the rim) and underneath (to
  the floor), and the frame;
- markers on User.2 for each opening: at the board edge for a wall opening (its width, and its
  height above the board's top), and over the board for a lid opening (a button or display).

KiCad's Y axis points down, so the enclosure's (x, y) is KiCad's (x0 + x, y0 - y), with
(x0, y0) the page position of the enclosure's origin, stored on User.1 and returned.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path

from .shell import Enclosure, board_hole_for

ORIGIN = (150.0, 100.0)  # where the enclosure's origin lands on KiCad's page, mm

# KiCad 7's board format. KiCad 8, 9 and 10 (and Backplane's KiCad) open it and upgrade it on save.
VERSION = 20221018
LAYERS = [(0, "F.Cu", "signal"), (31, "B.Cu", "signal"), (32, "B.Adhes", "user", "B.Adhesive"),
          (33, "F.Adhes", "user", "F.Adhesive"), (34, "B.Paste", "user"), (35, "F.Paste", "user"),
          (36, "B.SilkS", "user", "B.Silkscreen"), (37, "F.SilkS", "user", "F.Silkscreen"),
          (38, "B.Mask", "user"), (39, "F.Mask", "user"), (40, "Dwgs.User", "user", "User.Drawings"),
          (41, "Cmts.User", "user", "User.Comments"), (42, "Eco1.User", "user", "User.Eco1"),
          (43, "Eco2.User", "user", "User.Eco2"), (44, "Edge.Cuts", "user"), (45, "Margin", "user"),
          (46, "B.CrtYd", "user", "B.Courtyard"), (47, "F.CrtYd", "user", "F.Courtyard"),
          (48, "B.Fab", "user"), (49, "F.Fab", "user")] + [(49 + i, f"User.{i}", "user") for i in range(1, 10)]


def _q(text: str) -> str:
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _n(v: float) -> str:
    t = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if t in ("-0", "") else t


class _Board:
    """A .kicad_pcb written as text, so no KiCad is needed to make one."""

    def __init__(self, origin, thickness):
        self.origin, self.thickness, self.items = origin, thickness, []

    def pt(self, x, y):
        return self.origin[0] + x, self.origin[1] - y

    def line(self, layer, a, b, width=0.1):
        (ax, ay), (bx, by) = self.pt(*a), self.pt(*b)
        self.items.append(f"  (gr_line (start {_n(ax)} {_n(ay)}) (end {_n(bx)} {_n(by)})\n"
                          f"    (stroke (width {_n(width)}) (type default)) (layer {_q(layer)}) (tstamp {uuid.uuid4()}))")

    def text(self, layer, at, text, size=1.0):
        x, y = self.pt(*at)
        self.items.append(f"  (gr_text {_q(text)} (at {_n(x)} {_n(y)}) (layer {_q(layer)}) (tstamp {uuid.uuid4()})\n"
                          f"    (effects (font (size {_n(size)} {_n(size)}) (thickness {_n(size * 0.15)})) (justify left))\n  )")

    def circle(self, layer, c, r, width=0.1):
        x, y = self.pt(*c)
        self.items.append(f"  (gr_circle (center {_n(x)} {_n(y)}) (end {_n(x + r)} {_n(y)})\n"
                          f"    (stroke (width {_n(width)}) (type default)) (fill none) (layer {_q(layer)}) (tstamp {uuid.uuid4()}))")

    def keepout(self, c, r, name):
        x, y = self.pt(*c)
        pts = " ".join(f"(xy {_n(x + r * math.cos(2 * math.pi * i / 24))} {_n(y + r * math.sin(2 * math.pi * i / 24))})"
                       for i in range(24))
        self.items.append(
            f'  (zone (net 0) (net_name "") (layers "F&B.Cu") (tstamp {uuid.uuid4()}) (name {_q(name)}) (hatch edge 0.5)\n'
            "    (connect_pads (clearance 0))\n    (min_thickness 0.25) (filled_areas_thickness no)\n"
            "    (keepout (tracks not_allowed) (vias not_allowed) (pads not_allowed) (copperpour allowed) (footprints not_allowed))\n"
            "    (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))\n"
            f"    (polygon (pts {pts}))\n  )")

    def hole(self, c, d, ref):
        x, y = self.pt(*c)
        name = f"MountingHole_{d:.1f}mm"
        text = lambda kind, val: (f'    (fp_text {kind} {_q(val)} (at 0 {_n(-d / 2 - 1.5 if kind == "reference" else d / 2 + 1.5)}) '  # noqa: E731
                                  f'(layer {_q("F.SilkS" if kind == "reference" else "F.Fab")})\n'
                                  f"      (effects (font (size 1 1) (thickness 0.15))) (tstamp {uuid.uuid4()})\n    )")
        self.items.append(
            f'  (footprint {_q("EncloSURE:" + name)} (layer "F.Cu")\n    (tstamp {uuid.uuid4()})\n'
            f"    (at {_n(x)} {_n(y)})\n    (attr exclude_from_pos_files exclude_from_bom)\n"
            f'{text("reference", ref)}\n{text("value", name)}\n'
            f'    (pad "" np_thru_hole circle (at 0 0) (size {_n(d)} {_n(d)}) (drill {_n(d)}) '
            f'(layers "F&B.Cu" "*.Mask") (tstamp {uuid.uuid4()}))\n  )')

    def text_out(self) -> str:
        layers = "\n".join("    (" + " ".join([str(n)] + [_q(x) if i != 1 else x for i, x in enumerate(rest)]) + ")"
                           for n, *rest in LAYERS)
        return (f'(kicad_pcb (version {VERSION}) (generator "enclosure")\n\n'
                f"  (general\n    (thickness {_n(self.thickness)})\n  )\n\n"
                f'  (paper "A4")\n  (layers\n{layers}\n  )\n\n'
                "  (setup\n    (pad_to_mask_clearance 0)\n  )\n\n"
                '  (net 0 "")\n\n' + "\n\n".join(self.items) + "\n)\n")


def free_outline(base, cavity_bounds, z: float, clearance: float):
    """The space free for the board at height z: the inside less the base there (rounded corners,
    corner posts, ribs), inset by the clearance, as page-free (x, y) points. None if it can't be found."""
    from build123d import Axis, Box, Location
    (x0, y0, _), (x1, y1, _) = cavity_bounds
    slab = Box(x1 - x0, y1 - y0, 0.4).locate(Location(((x0 + x1) / 2, (y0 + y1) / 2, z)))
    try:
        free = slab - base
        solids = free.solids()
        if not solids:
            return None
        piece = max(solids, key=lambda s: s.volume)
        top = piece.faces().sort_by(Axis.Z)[-1]
        wire = top.outer_wire().offset_2d(-clearance, kind=__import__("build123d").Kind.ARC)
    except Exception:
        return None
    pts = []
    for e in wire.edges():
        n = 2 if e.geom_type.name == "LINE" else 9
        for i in range(n - 1):
            p = e.position_at(i / (n - 1))
            pts.append((round(p.X, 4), round(p.Y, 4)))
    # Drop repeats and points on straight runs.
    clean = []
    for p in pts:
        if not clean or abs(p[0] - clean[-1][0]) > 1e-4 or abs(p[1] - clean[-1][1]) > 1e-4:
            clean.append(p)
    return clean if len(clean) >= 3 else None


def limits(enc: Enclosure, out: str | Path, clearance: float = 0.5, pcb_thickness: float = 1.6,
           origin=ORIGIN, base=None) -> dict:
    """Write a .kicad_pcb holding the enclosure's limits. Returns what was written. With the base,
    the outline follows the free space at board height (rounded corners, corner posts), else it is
    the inside rectangle less the clearance."""
    if not enc.bosses:
        raise ValueError("the enclosure has no standoffs to mount a board on")
    board = _Board(origin, pcb_thickness)
    seat = max(b.top for b in enc.bosses)
    top = seat + pcb_thickness
    (x0, y0, _), (x1, y1, _) = enc.cavity_bounds
    x0, y0, x1, y1 = x0 + clearance, y0 + clearance, x1 - clearance, y1 - clearance
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    shape = free_outline(base, enc.cavity_bounds, seat + pcb_thickness / 2, clearance) if base is not None else None
    if shape:
        corners = shape
        xs, ys = [p[0] for p in shape], [p[1] for p in shape]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    for a, b in zip(corners, corners[1:] + corners[:1]):
        board.line("Edge.Cuts", a, b, 0.1)

    holes = []
    for i, boss in enumerate(enc.bosses, 1):
        d = board_hole_for(boss.hole)
        c = boss.center[:2]
        board.hole(c, d, f"H{i}")
        # A screw head (pan head, about 2 x the thread) plus the clearance, kept free of copper.
        head = max(boss.diameter / 2, d) + clearance
        board.keepout(c, head, f"H{i} screw head")
        holes.append({"ref": f"H{i}", "at": boss.center[:2], "diameter": d, "screw": boss.screw,
                      "keepout_radius": round(head, 2)})

    ceiling = enc.ceiling
    up = round(ceiling - top, 2)
    down = round(seat - enc.floor, 2)
    under = "lid" if enc.lid_underside is not None else "rim (no lid given)"
    notes = [
        f"EncloSURE limits: tallest part on top {up:.2f} mm (to the {under}); underneath {down:.2f} mm (to the floor)",
        f"Board seat z {seat:.2f} mm, top z {top:.2f} mm; enclosure origin at KiCad ({origin[0]:.1f}, {origin[1]:.1f}), KiCad Y = -enclosure Y",
        f"Board edge {clearance:.2f} mm in from the walls",
    ]
    for k, n in enumerate(notes):
        board.text("User.1", (x0, y1 + 6 + 2.2 * (len(notes) - k)), n, 1.2)

    marks = []
    for o in enc.openings:
        if o.wall in ("-X", "+X", "-Y", "+Y"):
            above = round(o.center[2] - top, 2)
            label = (f"{o.wall} opening {o.width:.2f} x {o.height:.2f}: centre {above:+.2f} mm above board top; "
                     f"wall {o.wall_thickness:.2f}")
            if o.wall in ("-X", "+X"):
                x = x0 if o.wall == "-X" else x1
                a, b = (x, o.center[1] - o.width / 2), (x, o.center[1] + o.width / 2)
                at = (x + (1 if o.wall == "-X" else -40), o.center[1] + o.width / 2 + 1.5)
            else:
                y = y0 if o.wall == "-Y" else y1
                a, b = (o.center[0] - o.width / 2, y), (o.center[0] + o.width / 2, y)
                at = (o.center[0] - o.width / 2, y + (2 if o.wall == "-Y" else -1.5))
            board.line("User.2", a, b, 0.4)
            board.text("User.2", at, label, 0.8)
            marks.append({"wall": o.wall, "from": a, "to": b, "centre_above_board_top": above,
                          "width": o.width, "height": o.height})
        elif o.wall == "lid":
            board.circle("User.2", o.center[:2], max(o.width, o.height) / 2, 0.3)
            gap = round(o.center[2] - top, 2)
            board.text("User.2", (o.center[0] + max(o.width, o.height) / 2 + 1, o.center[1]),
                       f"lid opening {o.width:.2f} x {o.height:.2f}: lid {gap:.2f} mm above board top", 0.8)
            marks.append({"wall": "lid", "at": o.center[:2], "width": o.width, "height": o.height,
                          "lid_above_board_top": gap})
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(board.text_out())
    return {"file": str(out), "outline": [[x0, y0], [x1, y1]], "outline_points": len(corners), "holes": holes, "openings": marks,
            "max_height_top": up, "max_height_bottom": down, "seat": seat, "origin": list(origin)}


# Reading a .kicad_pcb: a small s-expression reader, enough for footprints. Handles KiCad 6 and 7
# (fp_text reference/value) and KiCad 8 and later (property "Reference"/"Value").

def _tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            yield c
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    j += 1
                buf.append(text[j])
                j += 1
            yield ("s", "".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            yield text[i:j]
            i = j


def parse(text: str):
    """The s-expression as nested lists; quoted strings and bare atoms both come back as str."""
    stack = [[]]
    for t in _tokens(text):
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t[1] if isinstance(t, tuple) else t)
    return stack[0][0]


def _kids(node, name):
    return [k for k in node[1:] if isinstance(k, list) and k and k[0] == name]


def footprints(kicad_pcb: str | Path) -> dict[str, dict]:
    """Each footprint's reference, value, fields, page position (mm), rotation, side and whether it
    has a 3D model."""
    board = parse(Path(kicad_pcb).read_text(encoding="utf-8"))
    if not board or board[0] != "kicad_pcb":
        raise ValueError(f"{kicad_pcb}: not a KiCad board")
    out = {}
    for fp in _kids(board, "footprint") + _kids(board, "module"):
        fields = {}
        for p in _kids(fp, "property"):
            if len(p) >= 3:
                fields[p[1]] = p[2]
        for t in _kids(fp, "fp_text"):
            if len(t) >= 3 and t[1] in ("reference", "value"):
                fields.setdefault(t[1].capitalize(), t[2])
        at = (_kids(fp, "at") or [["at", "0", "0"]])[0]
        layer = (_kids(fp, "layer") or [["layer", "F.Cu"]])[0][1]
        ref = fields.get("Reference")
        if not ref:
            continue
        out[ref] = {"value": fields.get("Value", ""), "fields": fields,
                    "at": [float(at[1]), float(at[2])], "rotation": float(at[3]) if len(at) > 3 else 0.0,
                    "side": "bottom" if layer.startswith("B.") else "top", "has_model": bool(_kids(fp, "model"))}
    return out


def _blocks(text: str):
    """(start, end) of each top-level footprint in a .kicad_pcb's text."""
    i, depth, out, start = 0, 0, [], None
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif c == "(":
            depth += 1
            if depth == 2 and (text.startswith("(footprint", i) or text.startswith("(module", i)):
                start = i
        elif c == ")":
            if depth == 2 and start is not None:
                out.append((start, i + 1))
                start = None
            depth -= 1
        i += 1
    return out


def _own_at(block: str):
    """The span of a footprint's own `(at x y [rot])`: the first one directly inside it."""
    depth, i, n = 0, 0, len(block)
    while i < n:
        c = block[i]
        if c == '"':
            i += 1
            while i < n and block[i] != '"':
                i += 2 if block[i] == "\\" else 1
        elif c == "(":
            depth += 1
            if depth == 2 and block.startswith("(at ", i):
                return i, block.index(")", i) + 1
        elif c == ")":
            depth -= 1
        i += 1
    return None


def move_footprints(kicad_pcb: str | Path, moves: dict, out: str | Path) -> list[dict]:
    """Move footprints by (dx, dy) mm on KiCad's page and write the board to *out*. *moves* keys
    are references (J1) or page positions (x, y) for footprints with no useful reference (a
    mounting hole found by where it is). Returns what moved."""
    text = Path(kicad_pcb).read_text(encoding="utf-8")
    edits, done = [], []
    found = footprints(kicad_pcb)
    by_pos = {ref: fp["at"] for ref, fp in found.items()}
    want = {}
    for key, (dx, dy) in moves.items():
        if isinstance(key, tuple):
            ref = next((r for r, (x, y) in by_pos.items() if abs(x - key[0]) < 0.05 and abs(y - key[1]) < 0.05), None)
            if ref is None:
                done.append({"what": f"hole at ({key[0]:.2f}, {key[1]:.2f})", "moved": False,
                             "why": "no footprint sits there (the hole may be a pad of a larger footprint)"})
                continue
        else:
            ref = key
        want[ref] = (want.get(ref, (0, 0))[0] + dx, want.get(ref, (0, 0))[1] + dy)
    for start, end in _blocks(text):
        block = text[start:end]
        node = parse(block)
        refs = [p[2] for p in _kids(node, "property") if len(p) >= 3 and p[1] == "Reference"]
        refs += [t[2] for t in _kids(node, "fp_text") if len(t) >= 3 and t[1] == "reference"]
        ref = refs[0] if refs else None
        if ref not in want:
            continue
        span = _own_at(block)
        if span is None:
            continue
        parts = block[span[0] + 1:span[1] - 1].split()
        x, y = float(parts[1]), float(parts[2])
        dx, dy = want.pop(ref)
        parts[1], parts[2] = _n(x + dx), _n(y + dy)
        edits.append((start + span[0], start + span[1], "(" + " ".join(parts) + ")"))
        done.append({"what": ref, "moved": True, "from": [x, y], "to": [round(x + dx, 4), round(y + dy, 4)]})
    for ref in want:
        done.append({"what": ref, "moved": False, "why": "not on the board"})
    for a, b, new in sorted(edits, reverse=True):
        text = text[:a] + new + text[b:]
    Path(out).write_text(text, encoding="utf-8")
    return done


def moves_from_fit(findings: list[dict]) -> dict:
    """The footprint moves a fit report's findings ask for."""
    import re
    moves = {}
    for f in findings:
        km = f.get("kicad_move")
        if not km or not any(abs(v) > 1e-6 for v in km):
            continue
        subject = f.get("subject", "")
        m = re.match(r"hole at \(([-\d.]+), ([-\d.]+)\)", subject)
        # A hole is named by where it is in the board's STEP, which is KiCad's page with Y flipped.
        key = (float(m.group(1)), -float(m.group(2))) if m else subject.split(" ")[0]
        if key in moves:
            continue  # one move per footprint: the first finding's
        moves[key] = (km[0], km[1])
    return moves


# The board's shape from the .kicad_pcb: its Edge.Cuts outline, holes and each footprint's courtyard,
# so a box can be made from the KiCad file alone (no STEP export, no 3D models).

def _xy(node):
    return float(node[1]), float(node[2])


def _arc_points(a, m, b, n=12):
    """Points along the circle through a, m, b (start, mid, end)."""
    (ax, ay), (mx, my), (bx, by) = a, m, b
    d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(d) < 1e-9:
        return [a, b]
    ux = ((ax * ax + ay * ay) * (my - by) + (mx * mx + my * my) * (by - ay) + (bx * bx + by * by) * (ay - my)) / d
    uy = ((ax * ax + ay * ay) * (bx - mx) + (mx * mx + my * my) * (ax - bx) + (bx * bx + by * by) * (mx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    t0, tm, t1 = (math.atan2(p[1] - uy, p[0] - ux) for p in (a, m, b))
    # Go from t0 to t1 the way that passes tm.
    def norm(t):
        return t % (2 * math.pi)
    span = norm(t1 - t0)
    if norm(tm - t0) > span:
        span -= 2 * math.pi
    return [(ux + r * math.cos(t0 + span * i / n), uy + r * math.sin(t0 + span * i / n)) for i in range(n + 1)]


def _shape_points(node):
    """The polyline (or closed polygon) of a gr_/fp_ graphic, and whether it is closed."""
    kind = node[0][3:]  # line, arc, rect, circle, poly
    get = {k[0]: k for k in node[1:] if isinstance(k, list) and k}
    if kind == "line":
        return [_xy(get["start"]), _xy(get["end"])], False
    if kind == "arc":
        if "mid" in get:
            return _arc_points(_xy(get["start"]), _xy(get["mid"]), _xy(get["end"])), False
        # KiCad 6: (start centre) (end point) (angle)
        c, p = _xy(get["start"]), _xy(get["end"])
        ang = math.radians(float(get["angle"][1]))
        r, t0 = math.hypot(p[0] - c[0], p[1] - c[1]), math.atan2(p[1] - c[1], p[0] - c[0])
        return [(c[0] + r * math.cos(t0 + ang * i / 12), c[1] + r * math.sin(t0 + ang * i / 12)) for i in range(13)], False
    if kind == "rect":
        (x0, y0), (x1, y1) = _xy(get["start"]), _xy(get["end"])
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True
    if kind == "circle":
        c, e = _xy(get["center"]), _xy(get["end"])
        r = math.hypot(e[0] - c[0], e[1] - c[1])
        return [(c[0] + r * math.cos(2 * math.pi * i / 36), c[1] + r * math.sin(2 * math.pi * i / 36)) for i in range(36)], True
    if kind == "poly":
        pts = get.get("pts")
        return ([_xy(p) for p in pts[1:] if isinstance(p, list) and p[0] == "xy"] if pts else []), True
    return [], False


def _loops(pieces, tol=0.02):
    """Chain open polylines end to end into closed loops."""
    loops = [p for p, closed in pieces if closed and len(p) >= 3]
    open_ = [list(p) for p, closed in pieces if not closed and len(p) >= 2]
    near = lambda a, b: abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol  # noqa: E731
    while open_:
        chain = open_.pop(0)
        grew = True
        while grew and not near(chain[0], chain[-1]):
            grew = False
            for i, seg in enumerate(open_):
                if near(chain[-1], seg[0]):
                    chain += seg[1:]
                elif near(chain[-1], seg[-1]):
                    chain += seg[::-1][1:]
                elif near(chain[0], seg[-1]):
                    chain = seg[:-1] + chain
                elif near(chain[0], seg[0]):
                    chain = seg[::-1][:-1] + chain
                else:
                    continue
                open_.pop(i)
                grew = True
                break
        if near(chain[0], chain[-1]) and len(chain) >= 4:
            loops.append(chain[:-1])
    return loops


def _area(poly):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))) / 2


def _place(local, at, rot_deg):
    """A footprint-local point on the page (KiCad: Y down, rotation counter-clockwise on screen)."""
    t = math.radians(rot_deg)
    x, y = local
    return at[0] + x * math.cos(t) + y * math.sin(t), at[1] - x * math.sin(t) + y * math.cos(t)


def board_geometry(kicad_pcb: str | Path) -> dict:
    """The board's outline (the largest Edge.Cuts loop, page mm), its cutouts (the other loops), its
    thickness, its holes (x, y, drill) and each footprint's courtyard outline on the page."""
    board = parse(Path(kicad_pcb).read_text(encoding="utf-8"))
    if not board or board[0] != "kicad_pcb":
        raise ValueError(f"{kicad_pcb}: not a KiCad board")
    general = _kids(board, "general")
    thick = 1.6
    if general:
        t = _kids(general[0], "thickness")
        thick = float(t[0][1]) if t else 1.6
    pieces = []
    for node in board[1:]:
        if isinstance(node, list) and node and str(node[0]).startswith("gr_"):
            layer = _kids(node, "layer")
            if layer and layer[0][1] == "Edge.Cuts":
                pieces.append(_shape_points(node))
    loops = sorted(_loops(pieces), key=_area, reverse=True)
    if not loops:
        raise ValueError(f"{kicad_pcb}: no closed outline on Edge.Cuts")
    holes, parts = [], {}
    for fp in _kids(board, "footprint") + _kids(board, "module"):
        at = (_kids(fp, "at") or [["at", "0", "0"]])[0]
        pos, rot = (float(at[1]), float(at[2])), float(at[3]) if len(at) > 3 else 0.0
        lib = fp[1] if len(fp) > 1 and isinstance(fp[1], str) else ""
        refs = [p[2] for p in _kids(fp, "property") if len(p) >= 3 and p[1] == "Reference"]
        refs += [t[2] for t in _kids(fp, "fp_text") if len(t) >= 3 and t[1] == "reference"]
        ref = refs[0] if refs else ""
        layer = (_kids(fp, "layer") or [["layer", "F.Cu"]])[0][1]
        court = []
        for g in fp[1:]:
            if isinstance(g, list) and g and str(g[0]).startswith("fp_"):
                gl = _kids(g, "layer")
                if gl and gl[0][1] in ("F.CrtYd", "B.CrtYd"):
                    pts, _ = _shape_points(g)
                    court += [_place(p, pos, rot) for p in pts]
        mounting = "mountinghole" in lib.lower().replace("_", "") or ref.upper().startswith(("H", "MH"))
        for pad in _kids(fp, "pad"):
            drill = _kids(pad, "drill")
            if not drill or len(drill[0]) < 2:
                continue
            try:
                d = float(drill[0][2] if drill[0][1] == "oval" else drill[0][1])
            except (ValueError, IndexError):
                continue
            pat = (_kids(pad, "at") or [["at", "0", "0"]])[0]
            px, py = _place((float(pat[1]), float(pat[2])), pos, rot)
            if mounting or (pad[2] == "np_thru_hole" and 1.9 <= d <= 5.5):
                holes.append((round(px, 4), round(py, 4), d))
        if ref:
            parts[ref] = {"lib": lib, "at": list(pos), "rotation": rot, "side": "bottom" if layer.startswith("B.") else "top",
                          "courtyard": court, "has_model": bool(_kids(fp, "model")), "mounting": mounting}
    return {"outline": loops[0], "cutouts": loops[1:], "thickness": thick, "holes": holes, "parts": parts}


# Heights for parts with no model and no parts.json size, by footprint library name: typical, so a
# box can be made; parts.json `body` or a 3D model should replace them.
TYPICAL_HEIGHT = [("usb_c", 3.3), ("usb_micro", 2.7), ("usb_a", 7.0), ("rj45", 13.5), ("barrel", 11.0), ("dc_jack", 11.0),
                  ("terminalblock", 10.0), ("pinheader", 8.5), ("pinsocket", 8.5), ("jst", 6.0), ("idc", 9.0),
                  ("cp_radial", 12.0), ("button", 5.0), ("sw_", 5.0), ("led_d5", 8.6), ("led_d3", 5.3), ("led", 1.0),
                  ("relay", 15.5), ("buzzer", 9.5), ("module", 4.0), ("sot", 1.2), ("soic", 1.8), ("qfn", 1.0),
                  ("r_", 0.6), ("c_", 1.0)]


def typical_height(lib: str) -> float:
    key = lib.lower().split(":")[-1]
    return next((h for k, h in TYPICAL_HEIGHT if k in key), 3.0)


def board_solids(kicad_pcb: str | Path, specs: dict | None = None):
    """The board as Named solids in the STEP frame (KiCad page (x, y) is (x, -y), board bottom at
    z = 0): the plate with its holes, and a block for each footprint from its courtyard and a height
    (parts.json `body`, else a typical one for its kind). Returns (solids, notes)."""
    from build123d import Box, Cylinder, Polygon, Pos, extrude
    from .geom import Named
    g = board_geometry(kicad_pcb)
    t = g["thickness"]
    def slab(loop):
        s = extrude(Polygon(*[(x, -y) for x, y in loop], align=None), amount=t)
        z0 = s.bounding_box().min.Z
        return Pos(0, 0, -z0) * s if abs(z0) > 1e-6 else s  # flipping Y reverses the winding
    plate = slab(g["outline"])
    for loop in g["cutouts"]:
        plate -= slab(loop)
    for x, y, d in g["holes"]:
        plate -= Pos(x, -y, t / 2) * Cylinder(d / 2, t + 1)
    solids, typical = [Named("PCB", plate)], []
    for ref, p in g["parts"].items():
        if p["mounting"] or len(p["courtyard"]) < 2:
            continue
        xs = [q[0] for q in p["courtyard"]]
        ys = [-q[1] for q in p["courtyard"]]
        spec = (specs or {}).get(ref)
        if spec is not None and getattr(spec, "body", None):
            h = spec.body[2]
        else:
            h = typical_height(p["lib"])
            typical.append(f"{ref} {h:g}")
        w, l = max(xs) - min(xs), max(ys) - min(ys)
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        # The courtyard keeps a margin round the part (0.25 mm in KiCad's libraries): take it off.
        w, l = max(w - 0.5, 0.2), max(l - 0.5, 0.2)
        z = t + 0.05 + h / 2 if p["side"] == "top" else -0.05 - h / 2
        solids.append(Named(ref, Pos(cx, cy, z) * Box(w, l, h)))
    notes = []
    if typical:
        notes.append("typical heights used (no 3D model or parts.json size): " + ", ".join(typical))
    return solids, notes


def outline_text(points, layer="Edge.Cuts", width=0.1) -> list[str]:
    """gr_line items for a closed polyline (page mm)."""
    out = []
    for a, b in zip(points, points[1:] + points[:1]):
        out.append(f'  (gr_line (start {_n(a[0])} {_n(a[1])}) (end {_n(b[0])} {_n(b[1])})\n'
                   f'    (stroke (width {_n(width)}) (type default)) (layer {_q(layer)}) (tstamp {uuid.uuid4()}))')
    return out
