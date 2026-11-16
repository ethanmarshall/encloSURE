"""Fonts for text on parts: a list of Google Fonts families to pick from, or any other family by
name. A family is fetched from Google Fonts the first time it is asked for and kept on disk.

Only the family's name ever goes into a request, and files only ever come from Google's font host.
"""

from __future__ import annotations

import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT = "Default (DejaVu Sans)"
# A spread of kinds: plain, condensed, slab, serif, mono, round, display, script and stencil.
FAMILIES = [
    "Roboto", "Open Sans", "Inter", "Montserrat", "Poppins", "Lato", "Rubik", "Nunito", "Raleway", "Ubuntu", "Barlow",
    "Roboto Condensed", "Barlow Condensed", "Oswald", "Bebas Neue", "Anton", "Archivo Black", "Teko", "Staatliches", "Russo One",
    "Roboto Slab", "Bitter", "Merriweather", "Playfair Display", "Lora", "Libre Baskerville",
    "Roboto Mono", "Source Code Pro", "JetBrains Mono", "Space Mono", "VT323", "Press Start 2P",
    "Fredoka", "Baloo 2", "Comfortaa", "Righteous", "Bangers", "Orbitron", "Audiowide", "Black Ops One",
    "Pacifico", "Lobster", "Caveat", "Dancing Script",
    "Saira Stencil One", "Stardos Stencil", "Allerta Stencil", "Big Shoulders Stencil",
]
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ]{0,48}$")
HOST = "https://fonts.gstatic.com/"
MAX_BYTES = 6_000_000
_DIR = Path(tempfile.gettempdir()) / "enclosure_fonts"
_MISSING: set = set()          # families Google didn't have, so they aren't asked for again and again


def _get(url: str, limit: int) -> bytes:
    # An old browser's name: Google then answers with plain TrueType files, which the text engine reads.
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/4.0"})
    with urllib.request.urlopen(req, timeout=12) as r:  # noqa: S310 (the two hosts are fixed above and below)
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("the font file is too big")
    return data


def parse_css(css: str) -> dict[int, str]:
    """{weight: file URL} from a Google Fonts stylesheet, TrueType files on Google's font host only."""
    out: dict[int, str] = {}
    for block in re.findall(r"@font-face\s*{(.*?)}", css, re.S):
        w = re.search(r"font-weight:\s*(\d+)", block)
        u = re.search(r"url\((https://fonts\.gstatic\.com/[^)\s]+\.ttf)\)", block)
        if u and "italic" not in block.split("font-style:")[-1].split(";")[0]:
            out.setdefault(int(w.group(1)) if w else 400, u.group(1))
    return out


def clean_name(name: str) -> str:
    name = " ".join(str(name or "").split())
    if not NAME.match(name):
        raise ValueError("font: a Google Fonts family name, letters, digits and spaces only (like 'Bebas Neue')")
    return name


def path(family: str, bold: bool = False, fetch=_get) -> tuple[str | None, bool]:
    """(the font file for this family, whether that file is itself bold). None for the default font."""
    if not family or family == DEFAULT:
        return None, False
    family = clean_name(family)
    key = family.replace(" ", "_")
    have = {int(p.stem.rsplit("-", 1)[1]): p for p in _DIR.glob(f"{key}-*.ttf")} if _DIR.is_dir() else {}
    if not have:
        if family.lower() in _MISSING:
            raise ValueError(f"Google Fonts has no family called '{family}': check the spelling on fonts.google.com")
        q = urllib.parse.quote_plus(family)
        css = ""
        for url in (f"https://fonts.googleapis.com/css2?family={q}:wght@400;700", f"https://fonts.googleapis.com/css2?family={q}"):
            try:
                css = fetch(url, 200_000).decode("utf-8", "replace")
                break
            except Exception:
                continue
        files = parse_css(css)
        if not files:
            _MISSING.add(family.lower())
            raise ValueError(f"Google Fonts has no family called '{family}' (or it couldn't be reached): check the spelling on fonts.google.com")
        _DIR.mkdir(parents=True, exist_ok=True)
        for weight, url in files.items():
            if not url.startswith(HOST):
                continue
            data = fetch(url, MAX_BYTES)
            if data[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
                continue
            p = _DIR / f"{key}-{weight}.ttf"
            p.write_bytes(data)
            have[weight] = p
        if not have:
            raise ValueError(f"the font '{family}' came back in a form that can't be used")
    if bold and 700 in have:
        return str(have[700]), True
    regular = have.get(400) or have[min(have, key=lambda w: abs(w - 400))]
    return str(regular), False


_LOADED: dict = {}


def _font(file: str):
    from fontTools.ttLib import TTFont
    if file not in _LOADED:
        if len(_LOADED) > 24:
            _LOADED.pop(next(iter(_LOADED)))
        _LOADED[file] = TTFont(file, lazy=True)
    return _LOADED[file]


def _contours(glyph_set, name: str, steps: int) -> list[list[tuple[float, float]]]:
    """A glyph's outlines as closed polygons in font units, its curves cut into short straight pieces."""
    from fontTools.pens.basePen import decomposeQuadraticSegment
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)
    out, cur, at = [], [], (0.0, 0.0)

    def close():
        nonlocal cur
        if len(cur) >= 3:
            out.append(cur)
        cur = []

    for op, pts in pen.value:
        if op == "moveTo":
            close()
            at = pts[0]
            cur = [at]
        elif op == "lineTo":
            at = pts[0]
            cur.append(at)
        elif op == "qCurveTo":
            if pts[-1] is None:                      # a contour of off-curve points only: start half way between the last and first
                pts = list(pts[:-1])
                at = ((pts[-1][0] + pts[0][0]) / 2, (pts[-1][1] + pts[0][1]) / 2)
                cur = [at]
                pts = pts + [at]
            for c, e in decomposeQuadraticSegment(pts):
                for i in range(1, steps + 1):
                    t = i / steps
                    cur.append(((1 - t) ** 2 * at[0] + 2 * (1 - t) * t * c[0] + t * t * e[0], (1 - t) ** 2 * at[1] + 2 * (1 - t) * t * c[1] + t * t * e[1]))
                at = e
        elif op == "curveTo":
            c1, c2, e = pts[-3], pts[-2], pts[-1]
            for i in range(1, steps + 1):
                t = i / steps
                cur.append(tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d
                                 for a, b, c, d in zip(at, c1, c2, e)))
            at = e
        elif op in ("closePath", "endPath"):
            close()
    close()
    return out


def _area(pts) -> float:
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def outline_faces(text: str, size: float, file: str) -> tuple[list, float]:
    """(the text's faces in the XY plane, centred on the origin; its width) drawn from the font file's
    own outlines. The outlines are joined the way the font means (nonzero winding): strokes that
    overlap, in one letter or between joined-up letters, become one piece, and counters stay open."""
    import pyclipper
    from build123d import Face, Wire
    font = _font(file)
    cmap, glyphs, upm = font.getBestCmap(), font.getGlyphSet(), font["head"].unitsPerEm
    k = size / upm
    steps = 4 if size < 8 else 6 if size < 20 else 9
    S = 10000.0                                      # the clipper works in whole numbers: 0.1 micron steps
    polys, x = [], 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            raise ValueError(f"this font has no '{ch}'")
        for c in _contours(glyphs, name, steps):
            pts = [(round((x + px * k) * S), round(py * k * S)) for px, py in c]
            if len(pts) >= 3 and abs(_area(pts)) > 1.0:
                polys.append(pts)
        x += font["hmtx"][name][0] * k
    if not polys:
        return [], 0.0
    pc = pyclipper.Pyclipper()
    pc.AddPaths(polys, pyclipper.PT_SUBJECT, True)
    tree = pc.Execute2(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    xs = [q[0] for pts in polys for q in pts]
    ys = [q[1] for pts in polys for q in pts]
    cx, cy = (min(xs) + max(xs)) / 2 / S, (min(ys) + max(ys)) / 2 / S

    def wire(path):
        pts = pyclipper.CleanPolygon(path, 15)       # drop points closer than 1.5 microns
        if len(pts) < 3 or abs(pyclipper.Area(pts)) < 0.0004 * S * S:
            return None
        return Wire.make_polygon([(q[0] / S - cx, q[1] / S - cy, 0) for q in pts], close=True)

    faces = []

    def walk(node):
        for outer in node.Childs:                    # an outline; its children are its holes; theirs are islands
            w = wire(outer.Contour)
            if w is not None:
                holes = [h for h in (wire(c.Contour) for c in outer.Childs) if h is not None]
                try:
                    f = Face(w, holes) if holes else Face(w)
                    if f.normal_at().Z < 0:
                        f = -f
                    if f.is_valid:
                        faces.append(f)
                except Exception:
                    pass
            for hole in outer.Childs:
                walk(hole)

    walk(tree)
    return faces, (max(xs) - min(xs)) / S


def sound_faces(sketch) -> list:
    """The faces of a piece of text set in the built-in font, the unsound ones mended or dropped."""
    out = []
    for f in sketch.faces():
        if f.is_valid:
            out.append(f)
            continue
        try:
            out += [g for g in f.fix().faces() if g.is_valid and g.area > 1e-4]
        except Exception:
            continue
    return out
