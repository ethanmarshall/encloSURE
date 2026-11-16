"""v1.7: the useful printed things, lift-out bins for the hinged case, groups for the Make page, and kept answers."""

import pytest
from fastapi.testclient import TestClient

from enclosure import case, hardware as hw, useful
from enclosure.web import app

VARIANTS = {
    "shelf_bracket": [{}, {"brace": False, "holes": 1}, {"height": 60, "depth": 200, "thickness": 8, "width": 40, "holes": 3}],
    "corner_brace": [{}, {"rib": False, "holes": 1, "leg": 25}],
    "pipe_clamp": [{}, {"ears": 1, "pipe_d": 50}, {"ears": "2", "pipe_d": 8}],
    "pegboard_hook": [{}, {"board": "6 mm holes, 25 mm apart", "reach": 20, "tip": 0}],
    "wall_pocket": [{}, {"front_slot": 30, "cable_slot": 12}, {"item_w": 20, "item_d": 8, "height": 30}],
    "cable_comb": [{}, {"mount": True, "cables": 3, "cable_d": 10}],
    "raceway": [{}, {"holes": 0, "length": 60}],
    "desk_grommet": [{}, {"cable_slot": 0, "hole_d": 35}],
    "bit_holder": [{}, {"hole": "round", "hole_d": 10, "rows": 1, "cols": 3}],
    "tool_rack": [{}, {"slots": 1, "shaft_d": 20, "pitch": 40, "reach": 40}],
    "sanding_block": [{}],
    "drill_guide": [{}, {"sizes": "2.5; 6", "v_groove": False}],
    "foot": [{}, {"screw_d": 0, "taper": 1.0}],
    "end_cap": [{}, {"shape": "square", "outer": 20}, {"shape": "rectangle", "outer": 40, "outer2": 20, "tube_wall": 2}],
    "shim": [{}, {"thickness2": 5, "slot": 8}],
    "hole_plug": [{}, {"hole_d": 40, "panel": 4}],
    "drawer_organizer": [{}, {"div_x": 0, "div_y": 3}],
    "battery_caddy": [{}, {"cell": "9V", "rows": 1, "cols": 2}, {"cell": "18650"}],
    "fan_guard": [{}, {"fan": "120"}, {"fan": 40}],
    "label_plate": [{}, {"text": "MAIN VALVE|Shut off here", "style": "engraved", "mount": "cable tie slots"},
                    {"text": "12 V", "icon": "dc", "mount": "screw holes"}, {"text": "FUSES", "mount": "magnets", "style": "engraved"},
                    {"text": "TOMATO", "mount": "stake"}, {"text": "OK", "width": 80, "height": 40, "corners": "square", "border": False}],
    "fan_adapter": [{}, {"from_size": "140", "to_size": "120"}],
}


def test_every_new_part_has_variants():
    assert set(VARIANTS) == set(useful.KINDS)


@pytest.mark.parametrize("kind,params", [(k, p) for k, ps in VARIANTS.items() for p in ps])
def test_useful_parts(kind, params):
    r = hw.make(kind, **params)
    assert r["shape"].is_valid and r["shape"].volume > 0 and r["notes"]
    assert r["shape"].bounding_box().min.Z > -0.01          # built standing on the bed
    assert len(r["shape"].solids()) == (2 if kind in ("raceway", "desk_grommet") else 1)


def test_useful_errors():
    for kind, bad in [("shelf_bracket", {"width": 10}), ("pipe_clamp", {"ears": 3}), ("fan_adapter", {"from_size": 80, "to_size": 120}),
                      ("fan_adapter", {"height": 10}), ("fan_guard", {"fan": 77}), ("tool_rack", {"pitch": 10}), ("drill_guide", {"sizes": "a, b"}),
                      ("end_cap", {"outer": 8, "tube_wall": 3}), ("battery_caddy", {"cell": "AAAA"})]:
        with pytest.raises(ValueError):
            hw.make(kind, **bad)


def test_catalog_groups():
    c = hw.catalog()
    assert all(v["group"] in c["groups"] for v in c["kinds"].values())
    assert c["kinds"]["shelf_bracket"]["group"] == "Mounts and brackets" and "angle" in c["kinds"]["corner_brace"]["words"]
    fan = next(f for f in c["kinds"]["fan_guard"]["fields"] if f["name"] == "fan")
    assert fan["type"] == "select" and 120 in fan["options"]


def _overlap(a, b) -> float:
    i = a.intersect(b)
    return 0.0 if i is None else sum(s.volume for s in i.solids())


def test_inserts_fill_the_tray():
    assert case.parse_bins("2x1:2, 2 × 2") == [(2, 1, 2), (2, 2, 1)]
    spots = case.lay_out(4, 3, [(2, 2, 1), (2, 1, 2)])
    assert sum(a * b for a, b, _, _ in spots) == 12
    m = case.build(case.Case(insert_cols=4, insert_rows=3, insert_bins="2x2:1, 2x1:2", insert_scoop=True, insert_label=True))
    assert {i["name"]: i["count"] for i in m["inserts"]} == {"bin_1x1": 4, "bin_2x1": 2, "bin_2x2": 1}
    placed = m["insert_placed"]
    assert len(placed) == 7 and all(i["shape"].is_valid for i in m["inserts"])
    assert sum(_overlap(b, m["base"]) + _overlap(b, m["lid"]) for b in placed) < 1e-3
    assert sum(_overlap(placed[i], placed[j]) for i in range(7) for j in range(i + 1, 7)) < 1e-3
    two = case.build(case.Case(insert_cols=2, insert_rows=1, insert_layers=2))
    assert two["inserts"][0]["count"] == 4 and two["inserts"][0]["size"][2] == pytest.approx(14.6)


def test_insert_errors():
    for bad in ({"insert_cols": 3}, {"insert_cols": 2, "insert_rows": 2, "insert_bins": "2x2:2"},
                {"insert_cols": 2, "insert_rows": 2, "dividers_x": 1}, {"insert_cols": 2, "insert_rows": 2, "insert_bins": "big"}):
        with pytest.raises(ValueError):
            case.build(case.Case(**bad))


def test_kept_answers_and_case_inserts_through_the_web():
    import io, zipfile
    c = TestClient(app)
    body = {"kind": "foot", "params": {"diameter": 31}}
    a, b = c.post("/api/part", json={**body, "page": "x", "seq": 1}), c.post("/api/part", json={**body, "page": "y", "seq": 9})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    a, b = c.post("/api/part/download", json=body), c.post("/api/part/download", json=body)
    assert a.content == b.content and "foot.zip" in b.headers["content-disposition"]
    r = c.post("/api/case", json={"case": {"size": [120, 80, 28], "insert_cols": 3, "insert_rows": 2}, "preview": True})
    assert r.status_code == 200 and r.json()["inserts"] == [{"name": "bin_1x1", "count": 6, "size": r.json()["inserts"][0]["size"]}]
    assert sum(1 for m in r.json()["mounted"] if m["host"] == "base") == 6
    r = c.post("/api/kit", json={"case": {"size": [120, 80, 28], "insert_cols": 3, "insert_rows": 2}, "bed": "bambu-h3c"})
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert any(n.endswith("stl/bin_1x1.stl") for n in names)


def test_label_plates():
    flush = hw.make("label_plate", text="Ethan", style="flush", mount="key ring hole", corners="pill")
    assert flush["inlay"].is_valid and _overlap(flush["shape"], flush["inlay"]) < 1e-3
    assert flush["size"][2] == pytest.approx(2.0)                      # flush: nothing stands proud
    raised = hw.make("label_plate", text="Ethan")
    assert "inlay" not in raised and raised["size"][2] == pytest.approx(2.59, abs=0.02) and "pause at 2 mm" in " ".join(raised["notes"])
    two = hw.make("label_plate", text="Ethan", two_color=True)
    assert _overlap(two["shape"], two["inlay"]) < 1e-3
    small = hw.make("label_plate", text="A LONG LINE OF TEXT", width=60)
    assert small["size"][0] == pytest.approx(60) and small["info"]["text_size"] < 8
    assert hw.make("label_plate", text="X", mount="magnets")["info"]["size"][2] == 3.2
    for bad in ({"text": "X", "width": 8, "text_size": 20}, {"style": "engraved", "depth": 2}, {"mount": "glue"}, {"text": "a|b|c|d|e|f|g"}):
        with pytest.raises(ValueError):
            hw.make("label_plate", **bad)
    c = TestClient(app)
    r = c.post("/api/part", json={"kind": "label_plate", "params": {"style": "flush"}})
    assert r.status_code == 200 and r.json()["inlay"]
    import io, zipfile
    z = zipfile.ZipFile(io.BytesIO(c.post("/api/part/download", json={"kind": "label_plate", "params": {"style": "flush"}}).content))
    assert any(n.endswith("label_plate_second_colour.stl") for n in z.namelist())
