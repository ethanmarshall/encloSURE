"""v1.0: real screws and their lengths, the print plate and slicer, gears, pulleys, knobs, caps,
hinges, latches, the test print, sheet metal, laser-cut, the moulding check, honeycomb vents,
battery door, strain relief, wall bracket, stacking, insertion, parts in the library."""

import io
import itertools
import zipfile
from types import SimpleNamespace as NS

import pytest
from build123d import Box, Location, Pos

from enclosure import box, dfm, fit, hardware as hw, lasercut, plate, sheetmetal
from enclosure.geom import Named


def test_screw_lengths_fit_their_holes():
    s = box.BoxSpec(size=[100, 60, 40], standoffs=[[-30, -15], [30, 15]])
    plan = box.screw_plan(s)
    for role in ("board", "lid"):
        r = plan[role]
        assert r["length"] - r["clamp"] <= r["hole_depth"] + 0.05  # never bottoms out
    assert not plan["checks"]
    long = box.screw_plan(box.BoxSpec(size=[100, 60, 40], standoffs=[[-30, -15], [30, 15]], board_screw_length=12))
    assert any("bottom out" in c for c in long["checks"])
    nut = box.screw_plan(box.BoxSpec(size=[100, 60, 40], standoffs=[[-30, -15]], standoff_hole="clearance"))
    assert nut["board"]["length"] - 1.6 >= nut["board"]["hole_depth"] + box.NUT_HEIGHT["M3"]


def test_assembly_uses_real_screws_and_inserts():
    from enclosure import assembly
    s = box.BoxSpec(size=[100, 60, 40], standoffs=[[-30, -15], [30, 15]])
    whole, bom = assembly.exploded(s, box.build(s))
    names = [c.label for c in whole.children]
    assert "M3 heat-set insert" in names and any(n.startswith("M3x") for n in names)


def test_print_plate_and_slicer(tmp_path):
    s = box.BoxSpec(size=[80, 50, 30], lid="hinge")
    m = box.build(s)
    items = plate.box_items(s, m) + [plate.part_item("knob", hw.make("knob")["shape"])]
    r = plate.make(items, (180, 180))
    for name, shape in r["plates"][0]:
        bb = shape.bounding_box()
        assert abs(bb.min.Z) < 1e-6 and -90 - 1e-6 <= bb.min.X and bb.max.X <= 90 + 1e-6
    for (_, a), (_, b) in itertools.combinations(r["plates"][0], 2):
        assert (a & b).volume < 1e-6  # nothing overlaps on the bed
    out = plate.write(items, tmp_path, (180, 180))
    assert out["files"][0].endswith(".3mf")
    if plate.slicer():
        assert out["slicer"]["hours"] > 0 and out["slicer"]["grams"] > 0
    big = plate.make([("a", Box(150, 150, 10)), ("b", Box(150, 150, 10))], (180, 180))
    assert len(big["plates"]) == 2


@pytest.mark.parametrize("kind", ["spur_gear", "gt2_pulley", "knob", "button_cap", "hinge", "latch"])
def test_new_parts_build(kind):
    r = hw.make(kind)
    assert r["shape"].is_valid and r["shape"].volume > 0


def test_gear_and_pulley_numbers():
    g = hw.make("spur_gear", module=1.5, teeth=24)
    assert g["info"]["pitch_d"] == pytest.approx(36) and g["size"][0] == pytest.approx(39, abs=0.05)
    p = hw.make("gt2_pulley", teeth=20)
    assert p["info"]["pitch_d"] == pytest.approx(40 / 3.141592653589793, abs=1e-3) and p["info"]["mm_per_turn"] == 40


def test_knob_d_bore_has_its_flat():
    k = hw.make("knob", shaft="d", shaft_d=6.0, depth=10)["shape"]
    # A probe in the D's round part is empty; one past the flat is solid.
    assert (k & Pos(0, -2.5, 5) * Box(0.3, 0.3, 0.3)).volume < 1e-6
    assert (k & Pos(0, 2.9, 5) * Box(0.3, 0.3, 0.3)).volume > 0


def test_test_print():
    r = hw.make("test_print", clearances="0.15,0.25", hooks="0.8")
    assert len(r["shape"].solids()) >= 4 and r["info"]["clearances"] == [0.15, 0.25]


def test_sheet_metal_flat_length(tmp_path):
    s = sheetmetal.Sheet(size=[120, 80, 40], thickness=1.5)
    f = sheetmetal.flats(s)["base"]
    BD = 2 * (s.R + s.thickness) - s.BA
    flat_x = f["core"][0] + 2 * (s.BA + f["flaps"]["+x"][0])
    assert flat_x == pytest.approx((120 + 3) + 2 * (1.5 + 40) - 2 * BD)  # A + B1 + B2 - 2 BD
    out = sheetmetal.write(s, tmp_path)
    import ezdxf
    doc = ezdxf.readfile(out["files"]["base_dxf"])
    assert len(doc.modelspace().query("LINE[layer=='BEND']")) == 4
    m = sheetmetal.formed(s)
    assert (m["base"] & m["cover"]).volume < 1e-6


def test_laser_box_interlocks(tmp_path):
    b = lasercut.Laser(size=[100, 70, 50], thickness=3)
    whole = lasercut.assembled(b)
    for a, c in itertools.combinations(list(whole.children), 2):
        assert (a & c).volume < 1e-6
    out = lasercut.write(b, tmp_path)
    assert out["files"]["dxf"].endswith(".dxf")


def test_moulding_check():
    s = box.BoxSpec(size=[100, 60, 40], wall=4.5, standoffs=[[-30, -15], [30, 15]])
    r = dfm.check(s, box.build(s), "ABS")
    assert not r["ready"] and any(f["what"] == "wall" for f in r["findings"])
    assert any(f["what"] == "draft" for f in r["findings"])


def test_box_features():
    s = box.BoxSpec(size=[120, 80, 40], floor=3, vents=[{"face": "-Y", "size": [40, 20], "at": [0, 20], "pattern": "honeycomb"}],
                    battery_door={"size": [30, 55], "at": [20, 0]}, strain_reliefs=[{"face": "+X", "d": 6, "at": [0, 6]}],
                    wall_bracket=True, stacking=True, power_w=3)
    m = box.build(s)
    assert m["base"].is_valid and len(m["base"].solids()) == 1 and len(m["lid"].solids()) == 1
    names = [n for n, _ in m["extras"]]
    assert names == ["battery_door", "cable_clamp_1", "wall_bracket"]
    assert all(len(e.solids()) == 1 for _, e in m["extras"])
    assert m["thermal"]["vent_area_mm2"] > 300


def test_box_hangs_on_its_bracket():
    s = box.BoxSpec(size=[120, 80, 40], floor=3, wall_bracket=True)
    m = box.build(s)
    bracket = dict(m["extras"])["wall_bracket"]
    # Lowered onto the bracket (floor to the wall), it stops on the cleat instead of passing it.
    contact = next(dy for dy in [x * -0.5 for x in range(-20, 80)] if ((Pos(0, dy, 8) * m["base"]) & bracket).volume > 0.01)
    assert -30 < contact < 0


def test_insertion_slide_and_tilt():
    base = Pos(0, 0, 20) * Box(110, 70, 40) - Pos(0, 0, 22) * Box(100, 60, 40)
    enc = NS(rim=40.0, cavity_bounds=((-50, -30, 2), (50, 30, 40)))
    pcb = Pos(0, 0, 7) * Box(80, 50, 1.6)
    out = fit.insertion(enc, base, pcb, [Named("J1", Pos(-41, 0, 9) * Box(22, 8, 4))], fit.Settings())
    assert [f.code for f in out] == ["insertion_slide"]
    wide = Pos(0, 0, 7) * Box(99, 50, 1.6)
    out = fit.insertion(enc, base, wide, [Named("J1", Pos(-46, 0, 9) * Box(12, 8, 4))], fit.Settings())
    assert [f.code for f in out] == ["insertion_tilt"]


def test_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from enclosure.web import app
    monkeypatch.setenv("ENCLOSURE_DATA_DIR", str(tmp_path))
    c = TestClient(app)
    boxb = {"size": [90, 60, 35], "cutouts": [{"face": "-X", "preset": "usb-c", "at": [0, 8]}]}
    assert c.post("/api/sheetmetal", json={"box": boxb}).status_code == 200
    assert c.post("/api/lasercut", json={"box": boxb, "preview": True}).json()["base"]
    assert "findings" in c.post("/api/moulding", json={"box": boxb}).json()
    r = c.post("/api/plate", json={"parts": [{"kind": "tie_mount", "params": {}, "qty": 2}], "bed": "prusa-mini"})
    assert r.status_code == 200 and r.json()["parts"] == [["tie_mount_1_1", "tie_mount_1_2"]]
    z = c.post("/api/plate/download", json={"box": boxb})
    assert zipfile.ZipFile(io.BytesIO(z.content)).namelist() == ["plate.3mf"]
    # Parts in the team library.
    saved = c.post("/api/library", json={"name": "knob", "part": {"kind": "knob", "params": {"diameter": 25}}}).json()
    listed = c.get("/api/library").json()["designs"]
    assert listed[0]["type"] == "part" and c.get(f"/api/library/{saved['id']}").json()["part"]["params"]["diameter"] == 25
    assert c.post("/api/library", json={"name": "bad", "part": {"kind": "knob", "params": {"nope": 1}}}).status_code == 400
