"""A box from the .kicad_pcb alone, the free board outline, board-against-post collisions, the
clamshell and light pipes, heat, print plan, tolerances, machining files and the shared library."""

import json
import shutil

import pytest

from enclosure import box, fit, frompcb, geom, kicad, machining, samples, shell, stock, tolerance

KICAD = shutil.which("kicad-cli") is not None


@pytest.fixture(scope="module")
def kb(tmp_path_factory):
    if not KICAD:
        pytest.skip("KiCad is not installed")
    return samples.kicad_board(tmp_path_factory.mktemp("kb7"))


def test_board_geometry_reads_arcs_and_holes(tmp_path):
    text = """(kicad_pcb (version 20221018) (generator "x") (general (thickness 1.6))
  (gr_line (start 105 100) (end 175 100) (layer "Edge.Cuts"))
  (gr_arc (start 175 100) (mid 178.535534 101.464466) (end 180 105) (layer "Edge.Cuts"))
  (gr_line (start 180 105) (end 180 150) (layer "Edge.Cuts"))
  (gr_line (start 180 150) (end 100 150) (layer "Edge.Cuts"))
  (gr_line (start 100 150) (end 100 105) (layer "Edge.Cuts"))
  (gr_arc (start 100 105) (mid 101.464466 101.464466) (end 105 100) (layer "Edge.Cuts"))
  (footprint "MountingHole:MountingHole_3.2mm_M3" (layer "F.Cu") (at 110 110)
    (fp_text reference "H1" (at 0 0) (layer "F.SilkS"))
    (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu")))
  (footprint "Connector_USB:USB_C" (layer "F.Cu") (at 102 125 90)
    (fp_text reference "J1" (at 0 0) (layer "F.SilkS"))
    (fp_line (start -4.5 -2) (end 4.5 -2) (layer "F.CrtYd"))
    (fp_line (start 4.5 -2) (end 4.5 6) (layer "F.CrtYd"))
    (fp_line (start 4.5 6) (end -4.5 6) (layer "F.CrtYd"))
    (fp_line (start -4.5 6) (end -4.5 -2) (layer "F.CrtYd"))))"""
    p = tmp_path / "b.kicad_pcb"
    p.write_text(text)
    g = kicad.board_geometry(p)
    assert len(g["outline"]) > 20  # the arcs are followed
    assert g["holes"] == [(110.0, 110.0, 3.2)]
    xs = [q[0] for q in g["parts"]["J1"]["courtyard"]]
    ys = [q[1] for q in g["parts"]["J1"]["courtyard"]]
    # Turned 90°: the courtyard's 9 mm runs along Y on the page, its 8 mm along X.
    assert max(xs) - min(xs) == pytest.approx(8.0) and max(ys) - min(ys) == pytest.approx(9.0)
    solids, notes = kicad.board_solids(p)
    plate = solids[0].shape
    assert plate.is_valid and geom.bbox(plate)[0][2] == pytest.approx(0.0)
    assert fit.mounting_holes(plate) == [(110.0, -110.0, 3.2)]
    assert any("J1 3.3" in n for n in notes)


def test_box_from_kicad_pcb_alone(kb):
    r = frompcb.from_kicad(kb["pcb"], frompcb.Settings(lid="friction"))
    assert r["fit"].to_json()["fits"]
    assert sorted(c["face"] for c in r["spec"].cutouts) == ["+X", "-X"]


def test_free_outline_clears_corner_posts(tmp_path):
    import subprocess
    if not KICAD:
        pytest.skip("KiCad is not installed")
    spec = box.BoxSpec(size=[100, 60, 40], lid="screw", standoffs=box.standoff_pattern("rect:80x40"), corner_radius=6)
    made = box.build(spec)
    enc, _ = shell.read(made["base"], made["lid"])
    out = {}
    for name, base in (("free", made["base"]), ("rect", None)):
        lim = kicad.limits(enc, tmp_path / f"{name}.kicad_pcb", base=base)
        subprocess.run(["kicad-cli", "pcb", "export", "step", "-f", "-o", str(tmp_path / f"{name}.step"),
                        str(tmp_path / f"{name}.kicad_pcb")], check=True, capture_output=True)
        out[name] = (lim, fit.check(enc, made["base"], made["lid"], geom.step_names(tmp_path / f"{name}.step")).to_json())
    assert out["free"][0]["outline_points"] > 4 and out["free"][1]["fits"]
    # The plain rectangle runs into the corner posts, and the fit check now says so.
    assert any(f["code"] == "board_collision" for f in out["rect"][1]["findings"])


def test_clamshell_and_light_pipes():
    spec = box.BoxSpec(size=[100, 60, 40], lid="clamshell", standoffs=box.standoff_pattern("rect:80x40"),
                       cutouts=[{"face": "-X", "preset": "usb-c", "at": [0, 8]}], light_pipes=[{"at": [10, 5], "d": 3}])
    made = box.build(spec)
    lower, upper = made["base"], made["lid"]
    assert lower.is_valid and len(lower.solids()) == 1 and upper.is_valid and len(upper.solids()) == 1
    assert geom.overlap_volume(lower, upper) < 1e-3
    z = spec.floor + spec.split * 40
    assert shell.solid_at(lower, (-51, 0, z + 0.2), (-51, 0, z + 1.3))  # the tongue
    assert not shell.solid_at(upper, (-51, 0, z + 0.2), (-51, 0, z + 1.3))  # its groove
    assert not shell.solid_at(upper, (10, 5, 10), (10, 5, 44))  # the pipe's bore is open
    enc, _ = shell.read(lower, upper)
    assert len(enc.bosses) == 4 and enc.lid_underside == pytest.approx(42.0)
    crossing = box.build(box.BoxSpec(size=[100, 60, 40], lid="clamshell", cutouts=[{"face": "-Y", "preset": "pg9", "at": [0, 24]}]))
    assert any("parting line" in c for c in crossing["checks"])


def test_frompcb_clamshell_parts_above_openings(kb):
    r = frompcb.make(kb["step"], frompcb.Settings(lid="clamshell"))
    assert r["fit"].to_json()["fits"] and r["spec"].split >= 0.5


def test_heat_print_plan_and_supports(tmp_path):
    spec = box.BoxSpec(size=[100, 60, 40], power_w=3, cutouts=[{"face": "-Y", "shape": "rect", "size": [25, 10], "at": [0, 15]}])
    made = box.build(spec)
    assert made["thermal"]["rise_c"] == pytest.approx(17.8, abs=0.5)
    assert any("°C above the room" in c for c in made["checks"])
    assert "support" in made["print_plan"]["base"]
    assert len(made["supports"]) == 1 and geom.overlap_volume(made["supports"][0], made["base"]) < 1e-3
    vented = box.BoxSpec(**{**box.asdict(spec), "vents": [box.parse_vent("left:30x8@0,4"), box.parse_vent("right:30x8@0,34")]})
    assert box.build(vented)["thermal"]["rise_c"] < made["thermal"]["rise_c"]
    files = box.write(spec, tmp_path / "b")["files"]
    assert "support_enforcers" in files


def test_tolerance_stack(kb):
    r = frompcb.make(kb["step"], frompcb.Settings(lid="friction"))
    st = tolerance.stack(r["enclosure"], r["fit"])
    sides = [row for row in st["rows"] if row["what"].startswith("board edge")]
    assert len(sides) == 4 and all(row["worst"] < row["nominal"] for row in sides)
    tight = tolerance.stack(r["enclosure"], r["fit"], tolerance.Tolerances(board_outline=1.0))
    assert any(f["code"] == "tolerance_tight" for f in tight["findings"])


def test_machining_files(tmp_path):
    from build123d import Compound, Pos, RectangleRounded, export_step, extrude
    outer = extrude(RectangleRounded(112, 60, 6), 31)
    body = outer - Pos(0, 0, 3) * extrude(RectangleRounded(106, 54, 4), 31)
    lid = Pos(0, 0, 31) * extrude(RectangleRounded(112, 60, 6), 3)
    step = tmp_path / "b.step"
    export_step(Compound(children=[body, lid]), str(step))
    r = stock.run(step, [{"face": "-Y", "preset": "pg9", "at": [0, 12]}, {"face": "-Y", "shape": "round", "size": [5.0], "at": [25, 12]},
                         {"face": "lid", "shape": "rect", "size": [30, 20], "radius": 2, "at": [0, 0]}], tmp_path / "o")
    files = r["files"]
    assert {"front_dxf", "front_gcode", "lid_dxf", "lid_gcode"} <= set(files)
    g = open(files["front_gcode"]).read()
    assert "G81 X81 Y15" in g and "G2 X" in g and g.rstrip().endswith("M30")
    lid_g = open(files["lid_gcode"]).read()
    assert "inside contour" in lid_g
    dxf = open(files["lid_dxf"]).read()
    assert dxf.count("\nARC\n") == 4 and dxf.startswith("0\nSECTION")


def test_library(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from enclosure.web import app
    c = TestClient(app)
    assert c.get("/api/health").json()["library"] is False
    assert c.post("/api/library", json={"name": "x", "design": {}}).status_code == 400
    monkeypatch.setenv("ENCLOSURE_DATA_DIR", str(tmp_path))
    r = c.post("/api/library", json={"name": "Sump alarm", "by": "E", "design": {"size": [100, 60, 40]}}).json()
    items = c.get("/api/library").json()["designs"]
    assert items[0]["name"] == "Sump alarm" and items[0]["id"] == r["id"]
    assert c.get(f"/api/library/{r['id']}").json()["design"]["size"] == [100, 60, 40]
    assert c.get("/api/library/not-an-id").status_code == 404
    assert c.post("/api/library", json={"name": "bad", "design": {"lid": "hinged"}}).status_code == 400
    c.delete(f"/api/library/{r['id']}")
    assert c.get("/api/library").json()["designs"] == []
