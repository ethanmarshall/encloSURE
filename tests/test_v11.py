"""v1.1: per-printer slicing, two colours, icons, living hinge, round and outline boxes, handheld
extras, grounding, IP guide, fan layout, DigiKey CSV, cost comparison, panel art, KiCad paste, guide."""

import io
import zipfile

import pytest
from build123d import Axis

from enclosure import box, compare, icons, outline, panels, plate, ratings, roundbox


def test_icons_and_two_colour_inlays():
    for n in icons.NAMES:
        from build123d import extrude
        assert extrude(icons.icon_shape(n, 6), amount=0.6).is_valid
    s = box.BoxSpec(size=[100, 60, 40], icons=True, two_color=True, labels=[{"face": "lid", "text": "HI"}],
                    cutouts=[{"face": "-X", "preset": "usb-c", "at": [0, 8]}])
    m = box.build(s)
    names = [n for n, _, _ in m["inlays"]]
    assert names == ["label_1", "icon_usb_1"]
    for n, sh, host in m["inlays"]:
        assert (sh & (m["base"] if host == "base" else m["lid"])).volume < 1e-6  # fills its recess exactly
    items = plate.box_items(s, m)
    labels = [getattr(sh, "label", "") for _, sh in items]
    assert any(str(l).startswith("group:") for l in labels)


def test_living_hinge_prints_in_one_piece():
    s = box.BoxSpec(size=[100, 60, 40], lid="living")
    m = box.build(s)
    assert m["print_body"].is_valid and len(m["print_body"].solids()) == 1
    assert (m["base"] & m["lid"]).volume < 1e-6
    assert any("PLA" in c for c in box.build(box.BoxSpec(size=[100, 60, 40], lid="living", material="PLA"))["checks"])


def test_round_box_cap_screws_on():
    r = roundbox.Round(inside_d=50, height=30, standoffs=3, side_holes=[{"angle": 0, "height": 10, "d": 6}])
    m = roundbox.build(r)
    assert m["base"].is_valid and m["lid"].is_valid
    vols = [(m["base"] & m["lid"].rotate(Axis.Z, a)).volume for a in range(0, 360, 30)]
    assert min(vols) < 1e-3 and max(vols) > 1  # meshes at the right turn


def test_outline_box(tmp_path):
    import ezdxf
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (80, 0)); msp.add_arc((80, 25), 25, -90, 90); msp.add_line((80, 50), (0, 50)); msp.add_line((0, 50), (0, 0))
    msp.add_circle((15, 10), 1.6)
    doc.saveas(tmp_path / "d.dxf")
    pts, circles = outline.read_dxf(tmp_path / "d.dxf")
    m = outline.build(pts, circles)
    assert m["base"].is_valid and len(m["standoffs"]) == 1 and (m["base"] & m["lid"]).volume < 1e-6
    assert m["base"].bounding_box().size.X == pytest.approx(80 + 25 + 4, abs=0.1)


def test_handheld_grounding_fan():
    s = box.BoxSpec(size=[120, 80, 40], power_w=5, fan_flow_cfm=3, cutouts=[{"face": "-X", "preset": "fan-40", "at": [0, 20]}],
                    lanyard=True, belt_clip=True, handle=True, ground_lug=[30, 20], shielding=True)
    m = box.build(s)
    assert len(m["base"].solids()) == 1
    assert [n for n, _ in m["extras"]] == ["belt_clip", "handle"]
    assert any("nowhere for the air" in c for c in m["checks"])  # no vents for the fan
    assert m["thermal"]["rise_c"] < 5


def test_ip_guide():
    assert ratings.ip_guide(box.BoxSpec(size=[100, 60, 40], cutouts=[{"face": "-X", "preset": "usb-c", "at": [0, 8]}]))["code"] == "IP20"
    sealed = box.BoxSpec(size=[100, 60, 40], lid="screw", gasket=2.0, cutouts=[{"face": "-X", "preset": "pg9", "at": [0, 15]}])
    assert ratings.ip_guide(sealed)["code"] == "IP55"


def test_compare_and_panels(tmp_path):
    s = box.BoxSpec(size=[100, 60, 40], cutouts=[{"face": "-X", "preset": "usb-c", "at": [0, 8]}], labels=[{"face": "-Y", "text": "A"}])
    r = compare.compare(s, box.build(s))
    assert r["rows"][0]["qty"] == 1 and r["each"]["printed"] > 0
    files = panels.write(s, tmp_path)
    assert set(files) == {"left", "front"} and "<circle" not in open(files["front"]).read()


def test_bambu_speeds_used(tmp_path):
    if not plate.slicer():
        pytest.skip("no PrusaSlicer")
    s = box.BoxSpec(size=[80, 50, 30])
    items = plate.box_items(s, box.build(s))
    fast = plate.write(items, tmp_path / "a", plate.BEDS["bambu-h3c"], printer="bambu-h3c")["slicer"]
    slow = plate.write(items, tmp_path / "b", plate.BEDS["prusa-mk4"])["slicer"]
    assert "H3C" in fast["settings"] and fast["hours"] < slow["hours"]


def test_new_endpoints():
    from fastapi.testclient import TestClient
    from enclosure.web import app
    c = TestClient(app)
    b = {"size": [100, 60, 40], "standoffs": "rect:60x30", "cutouts": [{"face": "-X", "preset": "usb-c", "at": [0, 8]}]}
    assert c.post("/api/digikey_csv", json=b).text.startswith("Quantity,Manufacturer Part Number")
    assert c.post("/api/kicad_paste", json=b).json()["text"].startswith("(kicad_pcb")
    assert c.post("/api/panels", json=b).status_code == 200
    assert c.post("/api/preview", json=b).json()["ip"]["code"] == "IP20"
    z = c.post("/api/roundbox", json={"round": {"inside_d": 40, "height": 20}})
    assert "round_cap.stl" in zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    page = c.get("/").text
    assert 'id="guide"' in page and "Designing a box from scratch" in page


def test_rmfg_rules():
    from enclosure import sheetmetal as sm
    ok = sm.Sheet(size=[150, 100, 30], thickness=1.5)
    assert not [r for r in sm.rmfg_check(ok) if r["severity"] == "error"]  # lip holes clear of the bends
    deep = sm.Sheet(size=[100, 60, 40], thickness=1.5, cutouts=[{"face": "-X", "preset": "usb-c", "at": [0, 3]}])
    rules = {(r["severity"], r["rule"]) for r in sm.rmfg_check(deep)}
    assert ("warning", "U-channel") in rules and ("error", "hole near a bend") in rules
    thin = sm.Sheet(size=[150, 100, 30], thickness=0.5, lip=10)
    assert ("error", "material") in {(r["severity"], r["rule"]) for r in sm.rmfg_check(thin)}
