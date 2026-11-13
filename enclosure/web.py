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
from .presets import PRESETS

STATIC = Path(__file__).parent / "static"
FIELDS = {f.name for f in fields(boxmod.BoxSpec)}
LISTS = {"cutouts", "vents", "labels"}
MAX_SIDE = 1000.0  # mm: keeps one request from tying up the server

app = FastAPI(title="EncloSURE")


def spec_from(body: dict) -> boxmod.BoxSpec:
    """A BoxSpec from the page's form: plain settings, plus cutouts, vents and labels as lines in
    the same syntax as the command line (left:usb-c@0,9)."""
    settings = {k: v for k, v in body.items() if k in FIELDS and k not in LISTS and k != "standoffs"}
    spec = boxmod.BoxSpec(**settings)
    if body.get("standoffs"):
        spec.standoffs = boxmod.standoff_pattern(body["standoffs"])
    lines = lambda k: [s.strip() for s in (body.get(k) or "").splitlines() if s.strip()]  # noqa: E731
    spec.cutouts = [{k: v for k, v in asdict(boxmod.Cutout.parse(c)).items() if v is not None}
                    for c in lines("cutouts")]
    spec.vents = [boxmod.parse_vent(v) for v in lines("vents")]
    spec.labels = [boxmod.parse_label(t) for t in lines("labels")]
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
    return {name: {"shape": s, "size": size, "source": src} for name, (s, size, _, src) in PRESETS.items()}


@app.post("/api/preview")
def preview(body: dict):
    try:
        spec = spec_from(body)
        made = boxmod.build(spec)
    except (ValueError, RuntimeError) as e:
        _bad(e)
    out = {"inner": made["inner"], "outer": made["outer"], "notes": made["notes"], "checks": made["checks"],
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
                     cutouts: str = Form(...), teardrop: bool = Form(False)):
    from . import stock
    lines = [c.strip() for c in cutouts.splitlines() if c.strip()]
    try:
        parsed = [{k: v for k, v in asdict(boxmod.Cutout.parse(c)).items() if v is not None} for c in lines]
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
            return _zip(out, base_path.stem + "_drilled")
    except (ValueError, RuntimeError) as e:
        _bad(e)


@app.exception_handler(HTTPException)
def _errors(request, exc: HTTPException):
    return JSONResponse({"ok": False, "error": exc.detail}, status_code=exc.status_code)


def serve(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
