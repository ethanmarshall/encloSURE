"""EncloSURE in a browser: a form for `enclosure box` with a live 3D preview, downloads as STEP,
STL and/or the Onshape feature, and drilling templates for a bought box.

Run it with `enclosure web` (or `uvicorn enclosure.web:app`) and open http://localhost:8000.
Needs the `web` extras: pip install "enclosure-sure[web]".
"""

from __future__ import annotations

import base64
import io
import json
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
    for k in ("slot", "pitch"):
        if v.get(k) not in (None, ""):
            d[k] = _num(v[k], f"vent {k}")
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
                     "panel": [_num(v, "panel size") for v in w.get("panel", [])], "panel_t": _num(w.get("panel_t", 1.0), "panel thickness")}
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


@app.get("/api/presets")
def presets():
    return {name: {"shape": s, "size": size, "radius": r, "source": src, "gland": name in GLANDS}
            for name, (s, size, r, src) in PRESETS.items()}


@app.post("/api/preview")
def preview(body: dict):
    try:
        spec = spec_from(body)
        made = boxmod.build(spec)
    except (ValueError, RuntimeError) as e:
        _bad(e)
    out = {"inner": made["inner"], "outer": made["outer"], "notes": made["notes"], "checks": made["checks"],
           "estimate": made.get("estimate"),
           "base": base64.b64encode(_stl(made["base"])).decode()}
    if made["lid"] is not None:
        out["lid"] = base64.b64encode(_stl(made["lid"])).decode()
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
    formats = {"step": ("step",), "onshape": ("onshape",), "both": ("step", "onshape")}.get(fmt)
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
                          sample: bool = False):
    """The enclosure: uploaded STEPs, a quick box from the page's settings, or the sample."""
    from . import geom, samples, shell
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
                         box: str | None = Form(None), sample: bool = Form(False),
                         clearance: float = Form(0.5), thickness: float = Form(1.6)):
    """What EncloSURE reads from the enclosure, and a KiCad board to start the design in."""
    from . import kicad
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            b, l, enc, name = await _enclosure_from(d, base, lid, box, sample)
            out = {"name": name, "enclosure": enc.to_json(),
                   "base": base64.b64encode(_stl(b)).decode(),
                   "lid": base64.b64encode(_stl(l)).decode() if l is not None else None}
            try:
                lim = kicad.limits(enc, d / "board.kicad_pcb", clearance=clearance, pcb_thickness=thickness)
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
                    sample: bool = Form(False), clearance: float = Form(0.5),
                    opening_margin: float = Form(0.25), max_setback: float = Form(2.0)):
    """Check a finished board (KiCad's STEP export) in its enclosure."""
    from . import fit as fitmod, geom, parts as partsmod, report
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            b, l, enc, name = await _enclosure_from(d, base, lid, box, sample)
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
            result = fitmod.check(enc, b, l, geom.step_names(board_path), settings, None, specs, footprints)
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
            return {"fixed": fixed, "fits": j["fits"], "errors": j["errors"], "warnings": j["warnings"],
                    "placement": j["placement"], "headroom": j["headroom"], "findings": j["findings"],
                    "punch_list": Path(files["punch_list"]).read_text(),
                    "report": json.loads(Path(files["report"]).read_text()),
                    "view": Path(files["view"]).read_text()}
    except (ValueError, RuntimeError, json.JSONDecodeError) as e:
        _bad(e)


def _title(body: dict) -> dict:
    t = body.get("title") or {}
    return {k: str(v).strip()[:60] for k, v in t.items() if k in ("title", "part_number", "material", "drawn_by", "company") and str(v).strip()}


@app.get("/api/health")
def health():
    from . import drawing
    try:
        drawing.find_draftwright()
        dw = True
    except RuntimeError:
        dw = False
    return {"ok": True, "draftwright": dw}


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
def describe_box(body: dict):
    from . import describe
    text = str(body.get("text", ""))[:600]
    if not text.strip():
        _bad(ValueError("describe the project first"))
    try:
        r = describe.make(text)
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


@app.get("/api/coupon")
def fit_coupon():
    from . import coupon
    with tempfile.TemporaryDirectory() as d:
        coupon.write(d)
        return _zip(Path(d), "fit_test_coupon")


@app.post("/api/frompcb")
async def from_board(board: UploadFile = File(...), pcb: UploadFile | None = File(None),
                     parts: UploadFile | None = File(None), lid: str = Form("screw"), wall: float = Form(2.0),
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
            r = frompcb.make(step, st, partsmod.load(parts_path) if parts_path else {},
                             partsmod.from_board(pcb_path) if pcb_path else None)
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
