"""Writing a fit check out: report.json, a Markdown punch list, and a 3D view (one HTML file)."""

from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

from build123d import Compound, export_gltf

from .fit import Fit
from .shell import Enclosure


def punch_list(enc: Enclosure, fit: Fit, title: str = "EncloSURE fit check") -> str:
    j = fit.to_json()
    verdict = "Fits." if j["fits"] else f"Does not fit: {j['errors']} error(s)."
    lines = [
        f"# {title}",
        "",
        f"**{verdict}** {j['warnings']} warning(s). Placement: {fit.placement.how}, "
        f"turned {fit.placement.rotation}°.",
        "",
        f"Cavity {_box(enc.cavity_bounds)}; floor z {enc.floor:.2f}; ceiling z {enc.ceiling:.2f} "
        f"({'lid' if enc.lid_underside is not None else 'rim, no lid given'}); "
        f"{len(enc.bosses)} standoff(s), {len(enc.openings)} opening(s). "
        f"Least headroom over a part: {fit.headroom:.2f} mm." if fit.headroom is not None else "",
        "",
        "Moves are in the enclosure's frame and, where given, as a KiCad move (KiCad's Y points down).",
        "",
    ]
    for severity, heading in (("error", "Must fix"), ("warning", "Check"), ("info", "Notes")):
        rows = [f for f in j["findings"] if f["severity"] == severity]
        if not rows:
            continue
        lines += [f"## {heading}", "", "| What | Problem | Fix | KiCad move |", "|---|---|---|---|"]
        for f in rows:
            km = f"X {f['kicad_move'][0]:+.2f}, Y {f['kicad_move'][1]:+.2f} mm" if f["kicad_move"] else ""
            lines.append(f"| {f['subject']} | {f['message']} | {f['fix'] or ''} | {km} |")
        lines.append("")
    lines += ["## Parts", "", "| Part | Top z | Headroom | Gap to enclosure |", "|---|---|---|---|"]
    for r in sorted(j["parts"], key=lambda r: r["headroom"]):
        gap = f"{r['gap']:.2f}" if "gap" in r else f"collides with the {r.get('collides')}"
        lines.append(f"| {r['part']} | {r['top']:.2f} | {r['headroom']:.2f} | {gap} |")
    return "\n".join(lines) + "\n"


def _box(b):
    (x0, y0, z0), (x1, y1, z1) = b
    return f"{x1 - x0:.2f} × {y1 - y0:.2f} × {z1 - z0:.2f} mm"


def _glb(shapes) -> str | None:
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        return None
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "m.glb"
        export_gltf(Compound(children=shapes), str(path), binary=True)
        return base64.b64encode(path.read_bytes()).decode()


def viewer(base, lid, fit: Fit, title: str = "EncloSURE") -> str:
    """One self-contained HTML page: the enclosure see-through, the board green, parts with an
    error red. three.js is loaded from a CDN."""
    bad = {f.subject.split(" at ")[0] for f in fit.findings if f.severity == "error"}
    layers = {
        "base": _glb([base]),
        "lid": _glb([lid]) if lid is not None else None,
        "pcb": _glb([fit.pcb]),
        "parts": _glb([p.shape for p in fit.placed if p.name not in bad]),
        "bad": _glb([p.shape for p in fit.placed if p.name in bad]),
    }
    findings = [
        {"severity": f.severity, "subject": f.subject, "message": f.message, "fix": f.fix or ""}
        for f in fit.findings
    ]
    return PAGE.replace("__TITLE__", title).replace("__LAYERS__", json.dumps(layers)).replace(
        "__FINDINGS__", json.dumps(findings))


def write(out: str | Path, enc: Enclosure, fit: Fit, base, lid, title: str = "EncloSURE fit check") -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    report = {"enclosure": enc.to_json(), **fit.to_json()}
    (out / "report.json").write_text(json.dumps(report, indent=2))
    (out / "punch_list.md").write_text(punch_list(enc, fit, title))
    (out / "view.html").write_text(viewer(base, lid, fit, title))
    return {k: str(out / v) for k, v in
            (("report", "report.json"), ("punch_list", "punch_list.md"), ("view", "view.html"))}


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
 :root{--bg:#f4f5f7;--ink:#1d2430;--muted:#5b6574;--card:#fff;--line:#d8dde4;--err:#c62828;--warn:#a26a00}
 @media (prefers-color-scheme:dark){:root{--bg:#14171c;--ink:#e6e9ee;--muted:#9aa3b0;--card:#1d2128;--line:#2c323b}}
 body{margin:0;font:14px system-ui,sans-serif;background:var(--bg);color:var(--ink);display:grid;grid-template-columns:1fr 360px;height:100vh}
 #view{position:relative} canvas{display:block}
 aside{background:var(--card);border-left:1px solid var(--line);overflow:auto;padding:14px}
 h1{font-size:16px;margin:0 0 8px} .f{border-top:1px solid var(--line);padding:8px 0}
 .error b{color:var(--err)} .warning b{color:var(--warn)} .info b{color:var(--muted)} small{color:var(--muted)}
 label{display:block;margin:4px 0}
 @media (max-width:760px){body{grid-template-columns:1fr;grid-template-rows:60vh auto}aside{border-left:0;border-top:1px solid var(--line)}}
</style></head><body>
<div id="view"></div>
<aside><h1>__TITLE__</h1>
 <label><input type="checkbox" id="t-lid" checked> Lid</label>
 <label><input type="checkbox" id="t-base" checked> Enclosure</label>
 <div id="list"></div></aside>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from "three";
import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js";
import {OrbitControls} from "three/addons/controls/OrbitControls.js";
const layers = __LAYERS__, findings = __FINDINGS__;
const list = document.getElementById("list");
for (const f of findings) { const d = document.createElement("div"); d.className = "f " + f.severity;
  d.innerHTML = `<b>${f.subject}</b><br>${f.message}${f.fix ? `<br><small>Fix: ${f.fix}</small>` : ""}`; list.appendChild(d); }
if (!findings.length) list.textContent = "No findings.";
const host = document.getElementById("view");
const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true}); host.appendChild(renderer.domElement);
const scene = new THREE.Scene(); const camera = new THREE.PerspectiveCamera(40, 1, 0.0001, 100);
scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 2.2)); const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(1,2,3); scene.add(sun);
const controls = new OrbitControls(camera, renderer.domElement);
const style = {base:[0x8a96a8,0.28], lid:[0xb0bac8,0.18], pcb:[0x1f7a3a,1], parts:[0x3c4a5c,1], bad:[0xd32f2f,1]};
const groups = {}; const root = new THREE.Group(); scene.add(root);  // glTF is already Y-up
const loader = new GLTFLoader(); const bin = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer;
let pending = 0;
for (const [k, b64] of Object.entries(layers)) { if (!b64) continue; pending++;
  loader.parse(bin(b64), "", g => { const [c, o] = style[k];
    g.scene.traverse(m => { if (m.isMesh) m.material = new THREE.MeshStandardMaterial({color:c, transparent:o<1, opacity:o, depthWrite:o>=1, side:THREE.DoubleSide, metalness:0.1, roughness:0.7}); });
    groups[k] = g.scene; root.add(g.scene); if (--pending === 0) frame(); }); }
function frame(){ const box = new THREE.Box3().setFromObject(root); const c = box.getCenter(new THREE.Vector3()); const s = box.getSize(new THREE.Vector3()).length();
  controls.target.copy(c); camera.position.copy(c).add(new THREE.Vector3(0.6, 0.55, 0.8).multiplyScalar(s)); camera.near = s/1000; camera.far = s*20; camera.updateProjectionMatrix(); }
for (const k of ["lid","base"]) document.getElementById("t-"+k).onchange = e => { if (groups[k]) groups[k].visible = e.target.checked; };
function size(){ const w = host.clientWidth, h = host.clientHeight; renderer.setSize(w, h); camera.aspect = w/h; camera.updateProjectionMatrix(); }
addEventListener("resize", size); size();
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
</script></body></html>
"""
