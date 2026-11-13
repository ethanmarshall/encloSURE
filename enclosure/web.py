"""EncloSURE in a browser: a form for `enclosure box` with a live 3D preview, downloads as STEP,
STL and/or the Onshape feature, and drilling templates for a bought box.

Run it with `enclosure web` (or `uvicorn enclosure.web:app`) and open http://localhost:8000.
Needs the `web` extras: pip install "enclosure-sure[web]".
"""

from __future__ import annotations

import base64
import io
import json
import re
import tempfile
import zipfile
from dataclasses import asdict, fields
from pathlib import Path

from build123d import Pos, Rot, export_stl
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import box as boxmod
from .presets import GLANDS, PRESETS, resolve

STATIC = Path(__file__).parent / "static"
FIELDS = {f.name for f in fields(boxmod.BoxSpec)}
LISTS = {"cutouts", "vents", "labels", "windows"}
MAX_SIDE = 1000.0  # mm: keeps one request from tying up the server

app = FastAPI(title="EncloSURE")


@app.middleware("http")
async def _password(request, call_next):
    """With ENCLOSURE_PASSWORD set, every page and call asks for it (any user name)."""
    import os
    import secrets
    want = os.environ.get("ENCLOSURE_PASSWORD")
    if want:
        auth = request.headers.get("authorization", "")
        ok = False
        if auth.lower().startswith("basic "):
            try:
                _, _, given = base64.b64decode(auth[6:]).decode().partition(":")
                ok = secrets.compare_digest(given.encode(), want.encode())
            except (ValueError, UnicodeDecodeError):
                ok = False
        if not ok:
            return Response("EncloSURE needs its password.", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="EncloSURE", charset="UTF-8"'})
    return await call_next(request)


def _num(v, name):
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: a number") from None


def _cutout(c) -> dict:
    if isinstance(c, str):
        return {k: v for k, v in asdict(boxmod.Cutout.parse(c)).items() if v is not None}
    d = {"face": boxmod.face_name(str(c.get("face", ""))), "at": [_num(x, "cutout position") for x in c.get("at", [0, 0])]}
    if c.get("preset"):
        d["preset"] = str(c["preset"])
    else:
        d["shape"] = c.get("shape", "round")
        d["size"] = [_num(x, "cutout size") for x in c.get("size", [])]
        if c.get("radius"):
            d["radius"] = _num(c["radius"], "corner radius")
    boxmod.Cutout(**resolve(d)).check()
    return d


def _vent(v) -> dict:
    if isinstance(v, str):
        return boxmod.parse_vent(v)
    d = {"face": boxmod.face_name(str(v.get("face", ""))), "size": [_num(x, "vent size") for x in v.get("size", [])],
         "at": [_num(x, "vent position") for x in v.get("at", [0, 0])]}
    for k in ("slot", "pitch", "cell", "web"):
        if v.get(k) not in (None, ""):
            d[k] = _num(v[k], f"vent {k}")
    if v.get("pattern") in ("slots", "honeycomb"):
        d["pattern"] = v["pattern"]
    return d


def _label(t) -> dict:
    if isinstance(t, str):
        return boxmod.parse_label(t)
    d = {"face": boxmod.face_name(str(t.get("face", ""))), "text": str(t.get("text", "")).strip(),
         "at": [_num(x, "label position") for x in t.get("at", [0, 0])]}
    if not d["text"]:
        raise ValueError("a label needs its text")
    for k in ("size", "depth"):
        if t.get(k) not in (None, ""):
            d[k] = _num(t[k], f"label {k}")
    return d


def _items(value) -> list:
    """Rows from the form (a list), or lines in the command line's syntax (a string)."""
    if isinstance(value, list):
        return value
    return [s.strip() for s in (value or "").splitlines() if s.strip()]


def spec_from(body: dict) -> boxmod.BoxSpec:
    """A BoxSpec from the page's form. Cutouts, vents and labels come as rows (dicts) or as lines in
    the command line's syntax (left:usb-c@0,9)."""
    settings = {k: v for k, v in body.items() if k in FIELDS and k not in LISTS and k != "standoffs"}
    spec = boxmod.BoxSpec(**settings)
    so = body.get("standoffs")
    if isinstance(so, list):
        spec.standoffs = [[_num(x, "standoff x"), _num(y, "standoff y")] for x, y in so]
    elif so:
        spec.standoffs = boxmod.standoff_pattern(so)
    spec.cutouts = [_cutout(c) for c in _items(body.get("cutouts"))]
    spec.vents = [_vent(v) for v in _items(body.get("vents"))]
    spec.labels = [_label(t) for t in _items(body.get("labels"))]
    spec.windows = [{"face": boxmod.face_name(str(w.get("face", ""))), "size": [_num(v, "window size") for v in w.get("size", [])],
                     "at": [_num(v, "window position") for v in w.get("at", [0, 0])],
                     "panel": [_num(v, "panel size") for v in w.get("panel", [])], "panel_t": _num(w.get("panel_t", 1.0), "panel thickness"),
                     "print_panel": bool(w.get("print_panel"))}
                    for w in body.get("windows") or []]
    spec.card_slots = [_num(x, "card slot") for x in body.get("card_slots") or []]
    if max(spec.size) > MAX_SIDE:
        raise ValueError(f"each side at most {MAX_SIDE:g} mm here")
    spec.check()
    return spec


def _stl(shape) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.stl"
        export_stl(shape, str(p), tolerance=0.05, angular_tolerance=0.3)
        return p.read_bytes()


def _bad(e: Exception):
    raise HTTPException(status_code=400, detail=str(e)) from None


@app.get("/", response_class=HTMLResponse)
def page():
    return (STATIC / "index.html").read_text()


# Installing the site as an app (Edge or Chrome: the install icon in the address bar).
_APP_FILES = {"manifest.webmanifest": "application/manifest+json", "sw.js": "text/javascript",
              "icon-192.png": "image/png", "icon-512.png": "image/png"}


@app.get("/{name}", include_in_schema=False)
def app_file(name: str):
    if name not in _APP_FILES:
        raise HTTPException(status_code=404, detail="not found")
    return Response((STATIC / name).read_bytes(), media_type=_APP_FILES[name],
                    headers={"Cache-Control": "no-cache"} if name == "sw.js" else {})


@app.get("/api/presets")
def presets():
    return {name: {"shape": s, "size": size, "radius": r, "source": src, "gland": name in GLANDS}
            for name, (s, size, r, src) in PRESETS.items()}


# ---------- Parametric parts: screws, nuts, washers, spacers, springs, clips ----------

@app.get("/api/parts")
def parts_catalog():
    from . import hardware
    return hardware.catalog()


def _part_params(body: dict) -> tuple[str, dict]:
    kind = str(body.get("kind", ""))
    params = {k: v for k, v in (body.get("params") or {}).items() if v is not None and v != ""}
    return kind, params


import threading  # noqa: E402

_PART_LOCK = threading.Lock()
_PART_LATEST: dict[str, int] = {}  # each page's newest preview request


@app.post("/api/part")
def part_preview(body: dict):
    """A part's mesh for the viewer, with its notes, checks and worked-out numbers. Previews run one
    at a time; one that a newer request from the same page has overtaken while it waited is skipped."""
    from . import hardware
    page_id, seq = str(body.get("page", ""))[:40], int(body.get("seq") or 0)
    if page_id:
        _PART_LATEST[page_id] = max(_PART_LATEST.get(page_id, 0), seq)
        while len(_PART_LATEST) > 500:
            _PART_LATEST.pop(next(iter(_PART_LATEST)))
    with _PART_LOCK:
        if page_id and seq < _PART_LATEST.get(page_id, 0):
            return {"stale": True}
        try:
            kind, params = _part_params(body)
            r = hardware.make(kind, **params)
        except (ValueError, RuntimeError, TypeError) as e:
            _bad(e)
    return {"label": r["label"], "notes": r["notes"], "checks": r["checks"], "info": r["info"], "size": r["size"],
            "buy": r["buy"], "mesh": base64.b64encode(_stl(r["shape"])).decode()}


@app.post("/api/part/onshape")
def part_to_onshape(body: dict):
    """The part's STEP, imported into a new Onshape document."""
    from . import hardware, onshape_push
    try:
        kind, params = _part_params(body)
        with tempfile.TemporaryDirectory() as d:
            r = hardware.write(kind, Path(d) / "part", stl=False, **params)
            data = Path(r["files"]["step"]).read_bytes()
        label = r["label"] + (f" {params['size']}" if params.get("size") else "") + (f" x {params['length']:g}" if params.get("length") else "")
        return onshape_push.push_step(data, f"{kind}.step", f"EncloSURE {label}")
    except (ValueError, RuntimeError, TypeError) as e:
        _bad(e)


@app.post("/api/part/download")
def part_download(body: dict):
    """The part as STEP and STL, with a notes file."""
    from . import hardware
    try:
        kind, params = _part_params(body)
        with tempfile.TemporaryDirectory() as d:
            hardware.write(kind, Path(d) / "part", **params)
            return _zip(Path(d) / "part", kind)
    except (ValueError, RuntimeError, TypeError) as e:
        _bad(e)


def _plate_items(body: dict) -> list:
    """The box's printed parts (when a box is given) and the listed parts, qty each."""
    from . import hardware, plate
    items = []
    if body.get("box"):
        spec = spec_from(body["box"])
        items += plate.box_items(spec, boxmod.build(spec))
    for i, p in enumerate(body.get("parts") or []):
        kind, params = _part_params(p)
        qty = int(p.get("qty") or 1)
        if not 1 <= qty <= 50:
            raise ValueError("qty: 1 to 50 of each part")
        r = hardware.make(kind, **params)
        for n in range(qty):
            items.append(plate.part_item(kind, r["shape"], f"{kind}_{i + 1}" + (f"_{n + 1}" if qty > 1 else "")))
    if not items:
        raise ValueError("nothing to print: add the box or some parts")
    if len(items) > 80:
        raise ValueError("up to 80 parts on a plate")
    return items


def _bed(body: dict) -> tuple[float, float]:
    from . import plate
    bed = body.get("bed") or "prusa-mk4"
    if isinstance(bed, str):
        if bed not in plate.BEDS:
            raise ValueError(f"bed: one of {', '.join(plate.BEDS)}, or [width, depth]")
        return plate.BEDS[bed]
    w, d = (float(v) for v in bed)
    if not (50 <= w <= 1000 and 50 <= d <= 1000):
        raise ValueError("bed: 50 to 1000 mm each way")
    return w, d


@app.post("/api/plate")
def print_plate(body: dict):
    """Lay the parts out on the bed: a picture of each plate, and PrusaSlicer's time and grams."""
    from . import plate
    try:
        with _PART_LOCK, tempfile.TemporaryDirectory() as d:
            items, bed = _plate_items(body), _bed(body)
            r = plate.write(items, Path(d), bed, str(body.get("material") or "PETG"),
                            printer=body.get("bed") if isinstance(body.get("bed"), str) else None)
            from build123d import Compound
            laid = plate.make(items, bed)["plates"]
            meshes = [base64.b64encode(_stl(Compound(children=[s for _, s in p]))).decode() for p in laid]
            return {"notes": r["notes"], "checks": r["checks"], "parts": r["parts"], "slicer": r.get("slicer"),
                    "estimate": r["estimate"], "material": r["material"],
                    "bed": _bed(body), "meshes": meshes}
    except (ValueError, RuntimeError, TypeError) as e:
        _bad(e)


@app.post("/api/plate/download")
def print_plate_download(body: dict):
    """The plate (or plates) as 3MF."""
    from . import plate
    try:
        with tempfile.TemporaryDirectory() as d:
            r = plate.write(_plate_items(body), Path(d) / "plate", _bed(body), str(body.get("material") or "PETG"), slice_it=False)
            return _zip(Path(d) / "plate", "print_plate")
    except (ValueError, RuntimeError, TypeError) as e:
        _bad(e)


# ---------- Other ways to make the box: bent sheet metal, laser-cut panels; and a moulding check ----------

def _cutouts_of(spec) -> list:
    return [dict(c) for c in spec.cutouts]


@app.post("/api/sheetmetal")
def sheet_metal(body: dict):
    """The box as bent sheet metal: flat pattern DXFs (base and cover), a STEP, notes."""
    from . import sheetmetal
    try:
        spec = spec_from(body.get("box") or {})
        o = body.get("sheet") or {}
        sheet = sheetmetal.Sheet(size=list(spec.inner), thickness=_num(o.get("thickness", 1.5), "thickness"),
                                 bend_radius=_num(o["bend_radius"], "bend radius") if o.get("bend_radius") not in (None, "") else None,
                                 material=str(o.get("material", "aluminium 5052")), lip=_num(o.get("lip", 0.0), "lip"),
                                 screw=str(o.get("screw", "M3")), cutouts=_cutouts_of(spec))
        if body.get("preview"):
            made = sheetmetal.formed(sheet)
            return {"notes": sheetmetal.notes_for(sheet), "grams": made["grams"], "rmfg": sheetmetal.rmfg_check(sheet),
                    "base": base64.b64encode(_stl(made["base"])).decode(), "lid": base64.b64encode(_stl(made["cover"])).decode()}
        with tempfile.TemporaryDirectory() as d:
            sheetmetal.write(sheet, Path(d) / "sheet")
            return _zip(Path(d) / "sheet", "sheet_metal_enclosure")
    except (ValueError, RuntimeError, TypeError, KeyError) as e:
        _bad(e)


@app.post("/api/lasercut")
def laser_cut(body: dict):
    """The box as laser-cut panels with finger joints: one DXF, a STEP put together, notes."""
    from . import lasercut
    try:
        spec = spec_from(body.get("box") or {})
        o = body.get("laser") or {}
        box = lasercut.Laser(size=list(spec.inner), thickness=_num(o.get("thickness", 3.0), "thickness"),
                             kerf=_num(o.get("kerf", 0.15), "kerf"), lid=str(o.get("lid", "fixed")), cutouts=_cutouts_of(spec))
        if body.get("preview"):
            whole = lasercut.assembled(box)
            ch = list(whole.children)
            from build123d import Compound
            return {"notes": [f"six {box.thickness:g} mm panels with finger joints; outside "
                              f"{' x '.join(f'{v + 2 * box.thickness:g}' for v in box.size)} mm"],
                    "base": base64.b64encode(_stl(Compound(children=[c for i, c in enumerate(ch) if i != 1]))).decode(),
                    "lid": base64.b64encode(_stl(ch[1])).decode()}
        with tempfile.TemporaryDirectory() as d:
            lasercut.write(box, Path(d) / "laser")
            return _zip(Path(d) / "laser", "laser_cut_box")
    except (ValueError, RuntimeError, TypeError, KeyError) as e:
        _bad(e)


@app.post("/api/moulding")
def moulding_check(body: dict):
    """Is this box ready to be injection moulded? Findings against the usual rules."""
    from . import dfm
    try:
        spec = spec_from(body.get("box") or body)
        return dfm.check(spec, boxmod.build(spec), str(body.get("resin") or "ABS"))
    except (ValueError, RuntimeError, TypeError) as e:
        _bad(e)


@app.post("/api/digikey_csv")
def digikey_list(body: dict):
    """The parts to buy as a CSV to upload to DigiKey (BOM Manager, or the cart's upload)."""
    from . import costing
    try:
        _, cost = _costed(spec_from(body), body)
        text = costing.digikey_csv(cost, str((body.get("title") or {}).get("title") or "EncloSURE"))
        return Response(text, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="digikey_parts.csv"'})
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.post("/api/compare")
def price_compare(body: dict):
    """Printed vs sheet metal vs laser-cut: rough cost at a few quantities, with your rates."""
    from . import compare
    try:
        spec = spec_from(body.get("box") or {})
        rates = compare.Rates(**{k: _num(v, k) for k, v in (body.get("rates") or {}).items() if k in compare.Rates.__dataclass_fields__})
        made, _ = _costed(spec, {"slice": body.get("slice")})
        return compare.compare(spec, made, rates, made.get("estimate") if made.get("estimate", {}).get("source") else None)
    except (ValueError, RuntimeError, TypeError) as e:
        _bad(e)


@app.post("/api/panels")
def panel_art(body: dict):
    """Each face's artwork as 1:1 SVG: outline, holes, vents, windows, labels."""
    from . import panels
    try:
        spec = spec_from(body)
        with tempfile.TemporaryDirectory() as d:
            panels.write(spec, Path(d) / "panels")
            return _zip(Path(d) / "panels", "panel_artwork")
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.post("/api/kicad_paste")
def kicad_paste(body: dict):
    """The board outline, mounting holes and keep-outs as text to paste into KiCad's PCB editor."""
    from . import kicad, shell
    try:
        spec = spec_from(body)
        made = boxmod.build(spec)
        enc, _ = shell.read(made["base"], made["lid"])
        with tempfile.TemporaryDirectory() as d:
            kicad.limits(enc, Path(d) / "limits.kicad_pcb", base=made["base"])
            return {"text": (Path(d) / "limits.kicad_pcb").read_text()}
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.post("/api/roundbox")
def round_box(body: dict):
    """A round box with a screw-on cap: preview, or STEP and STL."""
    from . import roundbox
    try:
        fields_ = roundbox.Round.__dataclass_fields__
        r = roundbox.Round(**{k: v for k, v in (body.get("round") or {}).items() if k in fields_})
        with _PART_LOCK:
            if body.get("preview"):
                m = roundbox.build(r)
                return {"notes": m["notes"], "base": base64.b64encode(_stl(m["base"])).decode(),
                        "lid": base64.b64encode(_stl(m["lid"])).decode(),
                        "inner": [r.inside_d, r.inside_d, r.height], "outer": [m["outside_d"], m["outside_d"], m["outside_h"]]}
            with tempfile.TemporaryDirectory() as d:
                roundbox.write(r, Path(d) / "round")
                return _zip(Path(d) / "round", "round_box")
    except (ValueError, RuntimeError, TypeError) as e:
        _bad(e)


@app.post("/api/outline")
async def outline_box(dxf: UploadFile = File(...), height: float = Form(30.0), wall: float = Form(2.0),
                      floor: float = Form(2.0), lip: float = Form(3.0), standoff_height: float = Form(5.0),
                      preview: bool = Form(False)):
    """A box shaped to the closed outline in a DXF (circles inside it become standoffs)."""
    from . import outline
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            path = await _save(dxf, d / "outline.dxf")
            o = outline.Outline(height=height, wall=wall, floor=floor, lip=lip, standoff_height=standoff_height)
            if not (5 <= height <= MAX_SIDE and 1 <= wall <= 10):
                raise ValueError("height 5 mm or more, wall 1 to 10 mm")
            if preview:
                pts, circles = outline.read_dxf(path)
                m = outline.build(pts, circles, o)
                bb = m["base"].bounding_box()
                return {"notes": m["notes"], "base": base64.b64encode(_stl(m["base"])).decode(),
                        "lid": base64.b64encode(_stl(m["lid"])).decode(), "outer": [round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z + o.lid_thickness, 2)]}
            outline.write(path, d / "outline_box", o)
            return _zip(d / "outline_box", "outline_box")
    except (ValueError, RuntimeError, OSError) as e:
        _bad(e)


@app.post("/api/preview")
def preview(body: dict):
    try:
        spec = spec_from(body)
        made = boxmod.build(spec)
    except (ValueError, RuntimeError) as e:
        _bad(e)
    out = {"inner": made["inner"], "outer": made["outer"], "notes": made["notes"], "checks": made["checks"],
           "estimate": made.get("estimate"), "print_plan": made.get("print_plan"), "thermal": made.get("thermal"),
           "base": base64.b64encode(_stl(made["base"])).decode()}
    if made["lid"] is not None:
        out["lid"] = base64.b64encode(_stl(made["lid"])).decode()
    if made.get("extras"):
        out["extras"] = [{"name": n, "mesh": base64.b64encode(_stl(e)).decode()} for n, e in made["extras"]]
    out["screws"] = made.get("screws")
    from . import ratings
    out["ip"] = ratings.ip_guide(spec)
    if made.get("inlays"):
        out["inlays"] = [{"name": n, "mesh": base64.b64encode(_stl(sh)).decode()} for n, sh, _ in made["inlays"]]
    if body.get("format") in ("onshape", "both"):
        from .onshape import unsupported
        skipped = unsupported(spec)
        if skipped:
            out["checks"] = out["checks"] + ["not in the Onshape feature yet (STEP has them): " + ", ".join(skipped)]
    return out


def _zip(folder: Path, name: str) -> Response:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.iterdir()):
            z.write(p, p.name)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})


@app.post("/api/box")
def make_box(body: dict):
    fmt = body.get("format", "step")
    formats = {"step": ("step",), "onshape": ("onshape",), "both": ("step", "onshape"),
               "solidworks": ("step", "solidworks"), "all": ("step", "onshape", "solidworks")}.get(fmt)
    if formats is None:
        _bad(ValueError("format: step, onshape or both"))
    try:
        spec = spec_from(body)
        with tempfile.TemporaryDirectory() as d:
            result = boxmod.write(spec, d, stl=bool(body.get("stl", True)), formats=formats)
            (Path(d) / "checks.json").write_text(json.dumps(
                {k: result[k] for k in ("inner", "outer", "notes", "checks")}, indent=2) + "\n")
            return _zip(Path(d), "enclosure_box")
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.post("/api/stock")
async def make_stock(step: UploadFile = File(...), lid: UploadFile | None = File(None),
                     cutouts: str = Form(...), teardrop: bool = Form(False), drawings: str = Form(""),
                     part_number: str = Form(""), material: str = Form("")):
    from . import stock
    try:
        rows = json.loads(cutouts) if cutouts.lstrip().startswith("[") else cutouts
        parsed = [_cutout(c) for c in _items(rows)]
        if not parsed:
            raise ValueError("give at least one cutout")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in"
            src.mkdir()
            base_path = src / (Path(step.filename or "box.step").stem + ".step")
            base_path.write_bytes(await step.read())
            lid_path = None
            if lid is not None and lid.filename:
                lid_path = src / "lid_in.step"
                lid_path.write_bytes(await lid.read())
            out = Path(d) / "out"
            result = stock.run(base_path, parsed, out, lid_path=lid_path, teardrop=teardrop)
            (out / "checks.json").write_text(json.dumps(
                {"inside": result["inside"], "checks": result["checks"]}, indent=2) + "\n")
            if drawings in ("asme", "iso"):
                from . import drawing
                title = {k: v for k, v in (("part_number", part_number), ("material", material)) if v.strip()}
                drawing.make(out, out / "drawings", drawings, title, "pdf")
                for j in (out / "drawings").glob("*.drawing.json"):
                    j.unlink()
                for pdf in (out / "drawings").glob("*.pdf"):
                    pdf.rename(out / f"drawing_{pdf.name}")
                (out / "drawings").rmdir() if not any((out / "drawings").iterdir()) else None
            return _zip(out, base_path.stem + "_drilled")
    except (ValueError, RuntimeError) as e:
        _bad(e)


MAX_UPLOAD = 60 * 1024 * 1024


async def _save(upload: UploadFile | None, path: Path) -> Path | None:
    if upload is None or not upload.filename:
        return None
    data = await upload.read()
    if len(data) > MAX_UPLOAD:
        raise ValueError(f"{upload.filename}: over {MAX_UPLOAD // 2**20} MB")
    path.write_bytes(data)
    return path


async def _enclosure_from(d: Path, base: UploadFile | None, lid: UploadFile | None, box: str | None,
                          sample: bool = False, onshape_url: str | None = None):
    """The enclosure: uploaded STEPs, a quick box from the page's settings, an Onshape Part Studio,
    or the sample."""
    from . import geom, samples, shell
    if onshape_url:
        from . import onshape_push, stock
        step = onshape_push.export_step(onshape_url, d / "onshape.step")
        b, l = stock.split(step)
        enc, _ = shell.read(b, l)
        return b, l, enc, "onshape"
    if sample:
        paths = samples.write(d / "sample")
        b, l = geom.load(paths["base"]), geom.load(paths["lid"])
        name = "sample"
    elif base is not None and base.filename:
        b = geom.load(await _save(base, d / "base.step"))
        lp = await _save(lid, d / "lid.step")
        l = geom.load(lp) if lp else None
        name = Path(base.filename).stem
    elif box:
        made = boxmod.build(spec_from(json.loads(box)))
        b, l, name = made["base"], made["lid"], "enclosure_box"
    else:
        raise ValueError("give an enclosure: upload its STEP, or use the quick box")
    enc, _ = shell.read(b, l)
    return b, l, enc, name


@app.post("/api/enclosure")
async def enclosure_read(base: UploadFile | None = File(None), lid: UploadFile | None = File(None),
                         box: str | None = Form(None), sample: bool = Form(False), onshape_url: str | None = Form(None),
                         clearance: float = Form(0.5), thickness: float = Form(1.6)):
    """What EncloSURE reads from the enclosure, and a KiCad board to start the design in."""
    from . import kicad
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            b, l, enc, name = await _enclosure_from(d, base, lid, box, sample, onshape_url)
            out = {"name": name, "enclosure": enc.to_json(),
                   "base": base64.b64encode(_stl(b)).decode(),
                   "lid": base64.b64encode(_stl(l)).decode() if l is not None else None}
            try:
                lim = kicad.limits(enc, d / "board.kicad_pcb", clearance=clearance, pcb_thickness=thickness, base=b)
                lim.pop("file")
                out["limits"] = lim
                out["kicad_pcb"] = (d / "board.kicad_pcb").read_text()
            except ValueError as e:
                out["limits_error"] = str(e)
            return out
    except (ValueError, RuntimeError, json.JSONDecodeError) as e:
        _bad(e)


@app.post("/api/fit")
async def fit_check(board: UploadFile | None = File(None), base: UploadFile | None = File(None),
                    lid: UploadFile | None = File(None), box: str | None = Form(None),
                    pcb: UploadFile | None = File(None), parts: UploadFile | None = File(None),
                    board2: UploadFile | None = File(None), pcb2: UploadFile | None = File(None),
                    stack_gap: float = Form(11.0), stack_dx: float = Form(0.0), stack_dy: float = Form(0.0),
                    sample: bool = Form(False), onshape_url: str | None = Form(None), clearance: float = Form(0.5),
                    opening_margin: float = Form(0.25), max_setback: float = Form(2.0), material: str = Form("PETG")):
    """Check a finished board (KiCad's STEP export) in its enclosure."""
    from . import fit as fitmod, geom, parts as partsmod, report
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            b, l, enc, name = await _enclosure_from(d, base, lid, box, sample, onshape_url)
            if sample:
                board_path = d / "sample" / "sample_board.step"
            else:
                board_path = await _save(board, d / "board.step")
                if board_path is None:
                    raise ValueError("upload the board's STEP (KiCad: File > Export > STEP)")
            pcb_path = await _save(pcb, d / "board.kicad_pcb")
            parts_path = await _save(parts, d / "parts.json")
            settings = fitmod.Settings(clearance=clearance, opening_margin=opening_margin, max_setback=max_setback)
            specs = partsmod.load(parts_path) if parts_path else {}
            footprints = partsmod.from_board(pcb_path) if pcb_path else None
            solids, stack_notes = await _stacked(d, geom.step_names(board_path), board2, pcb2, stack_gap, stack_dx, stack_dy, specs)
            result = fitmod.check(enc, b, l, solids, settings, None, specs, footprints)
            from . import tolerance
            tol = tolerance.stack(enc, result, tolerance.Tolerances(material=material))
            title = f"EncloSURE: {Path(board.filename).stem if board is not None and board.filename else name}"
            files = report.write(d / "fit", enc, result, b, l, title=title)
            j = result.to_json()
            fixed = None
            if pcb_path is not None:
                from . import kicad
                moves = kicad.moves_from_fit(j["findings"])
                if moves:
                    done = kicad.move_footprints(pcb_path, moves, d / "fixed.kicad_pcb")
                    fixed = {"kicad_pcb": (d / "fixed.kicad_pcb").read_text(), "moved": done,
                             "name": Path(pcb.filename).stem + "_fixed.kicad_pcb"}
            return {"stack_notes": stack_notes, "tolerances": tol, "fixed": fixed, "fits": j["fits"], "errors": j["errors"], "warnings": j["warnings"],
                    "placement": j["placement"], "headroom": j["headroom"], "findings": j["findings"],
                    "punch_list": Path(files["punch_list"]).read_text(),
                    "report": json.loads(Path(files["report"]).read_text()),
                    "view": Path(files["view"]).read_text()}
    except (ValueError, RuntimeError, json.JSONDecodeError) as e:
        _bad(e)


def _title(body: dict) -> dict:
    t = body.get("title") or {}
    return {k: str(v).strip()[:60] for k, v in t.items() if k in ("title", "part_number", "material", "drawn_by", "company") and str(v).strip()}


def _library():
    """The shared designs folder ($ENCLOSURE_DATA_DIR/library), or None when the server keeps none."""
    import os
    root = os.environ.get("ENCLOSURE_DATA_DIR")
    if not root:
        return None
    p = Path(root) / "library"
    p.mkdir(parents=True, exist_ok=True)
    return p


@app.get("/api/library")
def library_list():
    lib = _library()
    if lib is None:
        return {"enabled": False, "designs": []}
    items = []
    for f in sorted(lib.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            d = json.loads(f.read_text())
            if d.get("part"):
                items.append({"id": f.stem, "name": d["name"], "by": d.get("by", ""), "at": d.get("at", 0),
                              "type": "part", "kind": d["part"].get("kind")})
            else:
                items.append({"id": f.stem, "name": d["name"], "by": d.get("by", ""), "at": d.get("at", 0),
                              "type": "box", "size": d["design"].get("size")})
        except (ValueError, KeyError):
            continue
    return {"enabled": True, "designs": items}


@app.get("/api/library/{item}")
def library_get(item: str):
    lib = _library()
    if lib is None or not re.fullmatch(r"[0-9a-f]{32}", item) or not (lib / f"{item}.json").exists():
        raise HTTPException(status_code=404, detail="no such design")
    return json.loads((lib / f"{item}.json").read_text())


@app.post("/api/library")
def library_add(body: dict):
    import time
    import uuid
    lib = _library()
    if lib is None:
        _bad(ValueError("this server keeps no shared library (set ENCLOSURE_DATA_DIR)"))
    name = str(body.get("name", "")).strip()[:80]
    if not name:
        _bad(ValueError("give the design a name"))
    design = body.get("design") or {}
    part = body.get("part")
    try:
        if part:  # a part's settings: only ones that build go in
            from . import hardware
            kind, params = _part_params(part)
            hardware.make(kind, **params)
            record = {"part": {"kind": kind, "params": params}}
        else:
            spec_from(dict(design))  # only boxes that build go in
            record = {"design": design}
    except (ValueError, TypeError) as e:
        _bad(e)
    item = uuid.uuid4().hex
    (lib / f"{item}.json").write_text(json.dumps({"name": name, "by": str(body.get("by", "")).strip()[:60],
                                                  "at": int(time.time() * 1000), **record}) + "\n")
    return {"id": item}


@app.delete("/api/library/{item}")
def library_delete(item: str):
    lib = _library()
    if lib is None or not re.fullmatch(r"[0-9a-f]{32}", item):
        raise HTTPException(status_code=404, detail="no such design")
    (lib / f"{item}.json").unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/onshape")
def to_onshape(body: dict):
    """Send the quick box's Onshape feature to a new Onshape document."""
    from . import onshape, onshape_push
    try:
        spec = spec_from(body)
        text, skipped = onshape.feature_studio(spec)
        L, W, H = spec.inner
        out = onshape_push.push(text, f"EncloSURE box {L:g}x{W:g}x{H:g}")
        out["skipped"] = skipped
        return out
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.post("/api/onshape/update")
def onshape_update(body: dict):
    """Change the box in the Onshape document Send made, keeping the user's later features."""
    from . import onshape, onshape_push
    ids = body.pop("onshape_ids", None)
    if not isinstance(ids, dict):
        _bad(ValueError("no Onshape document to update: send the box first"))
    try:
        spec = spec_from(body)
        text, skipped = onshape.feature_studio(spec)
        out = onshape_push.update(ids, text)
        out["skipped"] = skipped
        return out
    except (ValueError, RuntimeError, KeyError) as e:
        _bad(e)


@app.get("/api/health")
def health():
    from . import drawing
    try:
        drawing.find_draftwright()
        dw = True
    except RuntimeError:
        dw = False
    from . import onshape_push
    from . import plate
    return {"ok": True, "draftwright": dw, "library": _library() is not None, "onshape": onshape_push.enabled(),
            "slicer": bool(plate.slicer()), "slicer_error": plate.LAST_ERROR or None}


@app.post("/api/drawing")
def make_drawing(body: dict):
    """ASME or ISO drawings of the quick box's base and lid, as PDF and SVG."""
    from . import drawing
    standard = body.get("standard", "asme")
    try:
        spec = spec_from(body)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            boxmod.write(spec, d / "box", stl=False)
            r = drawing.make(d / "box", d / "out", standard, _title(body), "pdf,svg")
            (d / "out" / "review.txt").write_text("\n".join(r["review"]) + "\n" if r["review"] else "No problems found.\n")
            for j in (d / "out").glob("*.drawing.json"):
                j.unlink()
            return _zip(d / "out", f"enclosure_drawings_{standard}")
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.post("/api/describe")
async def describe_box(text: str = Form(""), pcb: UploadFile | None = File(None)):
    from . import describe
    text = text[:600]
    if not text.strip() and (pcb is None or not pcb.filename):
        _bad(ValueError("describe the project first"))
    try:
        with tempfile.TemporaryDirectory() as d:
            pcb_path = await _save(pcb, Path(d) / "board.kicad_pcb")
            r = describe.make(text, pcb=pcb_path)
        return {"spec": asdict(r["spec"]), "notes": r["notes"], "kicad_pcb": r["kicad_pcb"]}
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.post("/api/assembly")
def make_assembly(body: dict):
    """An exploded assembly drawing and parts list for the quick box (a plate stands in for the board)."""
    from . import assembly
    try:
        spec = spec_from(body)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            r = assembly.make(spec, d / "a", None, body.get("standard", "asme"))
            out = d / "out"
            out.mkdir()
            for key, name in (("drawing", "assembly_drawing.pdf"), ("parts_list", "parts_list.csv"), ("step", "exploded.step")):
                if key in r["files"]:
                    Path(r["files"][key]).rename(out / name)
            if r["notes"]:
                (out / "notes.txt").write_text("\n".join(r["notes"]) + "\n")
            return _zip(out, "enclosure_assembly")
    except (ValueError, RuntimeError) as e:
        _bad(e)


def _costed(spec, body):
    from . import assembly, costing
    made = boxmod.build(spec)
    _, bom = assembly.exploded(spec, made)
    try:
        per_kg = float(body.get("filament_per_kg") or costing.FILAMENT_PER_KG)
    except (TypeError, ValueError):
        per_kg = costing.FILAMENT_PER_KG
    est = made.get("estimate")
    if body.get("slice"):
        from . import plate
        with tempfile.TemporaryDirectory() as d:
            r = plate.write(plate.box_items(spec, made), Path(d), material=spec.material)
        if r.get("slicer"):
            sl = r["slicer"]
            est = {**(est or {}), "grams": sl["grams"], "hours": sl["hours"], "source": sl["settings"]}
            made = {**made, "estimate": est}
    return made, costing.price(bom, est, per_kg)


@app.post("/api/bom")
def costed_bom(body: dict):
    """The parts list with DigiKey suggestions and prices, and the plastic's cost."""
    try:
        _, cost = _costed(spec_from(body), body)
        return cost
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.post("/api/summary")
def summary_pdf(body: dict):
    """A one-page PDF of the box: picture, sizes, costed parts, print plan, checks."""
    from . import summary
    try:
        spec = spec_from(body)
        made, cost = _costed(spec, body)
        title = str((body.get("title") or {}).get("title") or "EncloSURE box")[:60]
        pdf = summary.make(spec, made, cost, None, title, "in" if body.get("units") == "in" else "mm")
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="enclosure_summary.pdf"'})
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.get("/api/coupon")
def fit_coupon():
    from . import coupon
    with tempfile.TemporaryDirectory() as d:
        coupon.write(d)
        return _zip(Path(d), "fit_test_coupon")


async def _stacked(d: Path, solids: list, board2, pcb2, gap: float, dx: float, dy: float, specs: dict):
    """The board with a second one stacked on it, when a second board was uploaded."""
    from . import frompcb
    step2 = await _save(board2, d / "board2.step")
    pcb2_path = await _save(pcb2, d / "board2.kicad_pcb")
    if step2 is None and pcb2_path is None:
        return solids, []
    if not 0 <= gap <= 100:
        raise ValueError("stack_gap: 0 to 100 mm between the boards")
    top, notes = frompcb.board_solids(step2, pcb2_path if step2 is None else None, specs)
    out, more = frompcb.stack(solids, top, gap, (dx, dy))
    return out, notes + more


@app.post("/api/frompcb")
async def from_board(board: UploadFile | None = File(None), pcb: UploadFile | None = File(None),
                     parts: UploadFile | None = File(None), lid: str = Form("screw"), wall: float = Form(2.0),
                     board2: UploadFile | None = File(None), pcb2: UploadFile | None = File(None),
                     stack_gap: float = Form(11.0), stack_dx: float = Form(0.0), stack_dy: float = Form(0.0),
                     edge_gap: float = Form(1.0), standoff_height: float = Form(5.0), headroom: float = Form(2.0)):
    """A quick box designed around a board, checked with the board in it."""
    from . import frompcb, parts as partsmod
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            step = await _save(board, d / "board.step")
            pcb_path = await _save(pcb, d / "board.kicad_pcb")
            parts_path = await _save(parts, d / "parts.json")
            st = frompcb.Settings(lid=lid, wall=wall, edge_gap=edge_gap, standoff_height=standoff_height, headroom=headroom)
            specs = partsmod.load(parts_path) if parts_path else {}
            solids, first_notes = frompcb.board_solids(step, pcb_path if step is None else None, specs)
            solids, stack_notes = await _stacked(d, solids, board2, pcb2, stack_gap, stack_dx, stack_dy, specs)
            r = frompcb.make(solids, st, specs, partsmod.from_board(pcb_path) if step is not None and pcb_path else None)
            r["notes"] = first_notes + stack_notes + r["notes"]
            j = r["fit"].to_json()
            return {"spec": asdict(r["spec"]), "notes": r["notes"], "fits": j["fits"], "errors": j["errors"],
                    "warnings": j["warnings"], "findings": j["findings"]}
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.exception_handler(HTTPException)
def _errors(request, exc: HTTPException):
    return JSONResponse({"ok": False, "error": exc.detail}, status_code=exc.status_code)


def serve(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
