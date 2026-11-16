"""v2.0: the second batch of printed things, battery fixings, pocket trays for the hinged case, trays shaped to an outline."""

import pytest
from fastapi.testclient import TestClient

from enclosure import case, hardware as hw, more, outline, useful
from enclosure.web import app

VARIANTS = {
    "bushing": [{}, {"flange_d": 20, "bore": 0}],
    "flat_plate": [{}, {"holes": "grid", "across": 4, "down": 3, "countersink": True, "centre_hole": 20}, {"holes": "none", "corner": 0}],
    "tool_clip": [{}, {"grip_d": 10, "wall": 1.6}, {"grip_d": 60, "width": 25}],
    "slip_cap": [{}, {"shape": "square", "inner": 20}, {"shape": "rectangle", "inner": 40, "inner2": 20}],
    "edge_clip": [{}, {"panel": 18, "depth": 30, "grip": 0}],
    "board_mount": [{}, {"style": "corner tray"}, {"board": "Arduino Uno"}, {"board": "Arduino Mega 2560", "plate_holes": False},
                    {"board": "Raspberry Pi Pico"}, {"board": "Arduino Nano", "style": "corner tray"},
                    {"board": "Your own board", "board_l": 70, "board_w": 50, "hole_l": 62, "hole_w": 42, "screw": "M2.5"}],
    "extrusion_end_cap": [{}, {"profile": "1530 (80/20, 1.5 x 3 in)"}, {"profile": "2020 (20 mm)"}],
    "extrusion_bracket": [{}, {"holes": "2"}, {"profile": "2020 (20 mm)", "thickness": 4}],
    "extrusion_cable_guide": [{}, {"profile": "3030 (30 mm)", "bundle_d": 40}],
    "extrusion_panel_clip": [{}, {"panel": 6}, {"panel": 1.5, "profile": "2020 (20 mm)"}],
    "extrusion_handle": [{}, {"profile": "4040 (40 mm)", "span": 200}],
    "shelf_pin_jig": [{}, {"lip": False, "holes": 3, "pitch": 25.4, "hole_d": 6.35}],
    "clamp_square": [{}, {"leg": 60, "width": 18}],
    "centre_finder": [{}, {"max_d": 40}],
    "setup_blocks": [{}, {"sizes": "1.5; 25"}],
    "funnel": [{}, {"hang_tab": False, "top_d": 40, "neck_d": 8, "neck_length": 15}],
    "hose_adapter": [{}, {"a_fits": "over the port", "b_fits": "over the port"}, {"end_a": 100, "end_b": 32, "b_fits": "over the port"}],
    "test_point_plate": [{}, {"labels": "A|B|C|D|E|F", "rows": 2, "hole_d": 6}, {"labels": "GND", "mount_holes": False}],
    "panel_bezel": [{}, {"depth": 0, "screw_d": 0}],
    "terminal_cover": [{}, {"wire_slot": 0, "length": 30}],
}


def test_every_new_part_has_variants():
    assert set(VARIANTS) == set(more.KINDS)


@pytest.mark.parametrize("kind,params", [(k, p) for k, ps in VARIANTS.items() for p in ps])
def test_more_parts(kind, params):
    r = hw.make(kind, **params)
    assert r["shape"].is_valid and r["shape"].volume > 0 and r["notes"]
    assert r["shape"].bounding_box().min.Z > -0.01
    if kind != "setup_blocks":
        assert len(r["shape"].solids()) == 1


def test_more_errors():
    for kind, bad in [("board_mount", {"board": "Arduino Nano"}), ("board_mount", {"board": "Commodore 64"}), ("hose_adapter", {"a_fits": "sideways"}),
                      ("funnel", {"height": 5}), ("extrusion_end_cap", {"profile": "9999"}), ("flat_plate", {"inset": 1}),
                      ("bushing", {"bore": 12}), ("setup_blocks", {"sizes": "tall"}), ("panel_bezel", {"flange": 4})]:
        with pytest.raises(ValueError):
            hw.make(kind, **bad)


def test_board_data():
    L, W, holes, hd, scr = more.BOARDS["Raspberry Pi 3, 4 or 5 (Model B)"]
    assert (L, W) == (85.0, 56.0) and holes[1][0] - holes[0][0] == 58.0 and holes[2][1] - holes[0][1] == 49.0 and scr == "M2.5"
    r = hw.make("board_mount")
    assert r["info"]["standoffs"] == [[3.5, 3.5], [61.5, 3.5], [3.5, 52.5], [61.5, 52.5]]
    assert len(more.BOARDS["Arduino Mega 2560"][2]) == 6


def test_extrusion_profiles():
    assert more.PROFILES["1515 (80/20, 1.5 in)"][:3] == (38.1, 8.13, "5/16-18")
    wide = hw.make("extrusion_end_cap", profile="1530 (80/20, 1.5 x 3 in)")
    assert wide["size"][:2] == [76.2, 38.1] and "6 tabs" in wide["notes"][0]
    assert hw.make("extrusion_bracket", profile="2020 (20 mm)")["info"]["bolt"] == "M5"


def test_battery_fixings():
    base = hw.make("battery_holder", mount="none")["size"]
    assert hw.make("battery_holder", ear_side="front and back")["size"][1] > base[1] and hw.make("battery_holder", ear_side="both ends")["size"][0] > base[0]
    left = hw.make("battery_holder", ear_side="left end only")["shape"].bounding_box()
    assert left.min.X < -base[0] / 2 - 5 and left.max.X == pytest.approx(base[0] / 2, abs=0.01)
    inside = hw.make("battery_holder", mount="internal holes")
    assert inside["size"][:2] == base[:2] and inside["size"][2] == pytest.approx(base[2] + 0.8) and "countersunk" in " ".join(inside["notes"])
    assert hw.make("battery_holder", ears=False)["size"] == base
    with pytest.raises(ValueError):
        hw.make("battery_holder", mount="velcro")
    fields = {f["name"]: f for f in hw.catalog()["kinds"]["battery_holder"]["fields"]}
    assert fields["mount"]["options"] == list(useful.BATTERY_MOUNTS) and fields["ear_side"]["options"] == list(useful.EAR_SIDES)
    assert hw.catalog()["kinds"]["battery_holder"]["group"] == "Batteries" and hw.catalog()["kinds"]["battery_holder"]["rank"] == 0


def _overlap(a, b) -> float:
    i = a.intersect(b)
    return 0.0 if i is None else sum(s.volume for s in i.solids())


def test_case_pocket_tray():
    assert case.parse_pockets("round 12:6, rect 40 x 25:2, slot 80x12") == [("round", 12.0, 12.0, 6), ("rect", 40.0, 25.0, 2), ("slot", 80.0, 12.0, 1)]
    m = case.build(case.Case(insert_pockets="round 12:6, rect 40x25:2, slot 80x12"))
    tray = m["inserts"][0]
    assert tray["name"] == "pocket_tray" and tray["shape"].is_valid and len(tray["shape"].solids()) == 1
    assert _overlap(m["insert_placed"][0], m["base"]) + _overlap(m["insert_placed"][0], m["lid"]) < 1e-3
    solid = (160 - 0.3) * (100 - 0.3) * tray["size"][2]
    assert tray["shape"].volume < solid * 0.9                      # the pockets really are cut
    for bad in ({"insert_pockets": "rect 300x20"}, {"insert_pockets": "banana 3"}, {"insert_pockets": "round 10", "insert_cols": 2, "insert_rows": 2},
                {"insert_pockets": "round 60:9"}, {"insert_pockets": "round 10", "pocket_depth": 40}):
        with pytest.raises(ValueError):
            case.build(case.Case(**bad))


def test_tray_shaped_to_an_outline(tmp_path):
    pts = [(0, 0), (60, 0), (60, 12), (25, 12), (25, 30), (0, 30)]
    m = outline.build_tray(pts)
    assert m["base"].is_valid and m["size"] == [72.8, 42.8, 16.6]
    boxed = outline.build_tray(pts, out_l=100, out_w=60, finger=False)
    area = 60 * 12 + 25 * 18
    assert boxed["base"].volume == pytest.approx(100 * 60 * 16.6 - area * 15, rel=0.06)
    with pytest.raises(ValueError):
        outline.build_tray(pts, out_l=50, out_w=20)
    import ezdxf
    d = ezdxf.new()
    d.modelspace().add_lwpolyline(pts, close=True)
    d.saveas(tmp_path / "l.dxf")
    c = TestClient(app)
    with open(tmp_path / "l.dxf", "rb") as f:
        r = c.post("/api/outline", files={"dxf": ("l.dxf", f, "application/dxf")}, data={"make": "tray", "preview": "true", "depth": "10"})
    assert r.status_code == 200 and r.json()["lid"] is None and r.json()["outer"][2] == pytest.approx(11.6)
    with open(tmp_path / "l.dxf", "rb") as f:
        r = c.post("/api/outline", files={"dxf": ("l.dxf", f, "application/dxf")}, data={"make": "tray"})
    assert r.status_code == 200 and "shaped_tray.zip" in r.headers["content-disposition"]
