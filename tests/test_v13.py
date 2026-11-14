"""v1.3: wheels, grommets, dowels, snap rings and thumb screws; magnet pockets and a magnet-held lid."""

import pytest

from enclosure import box, hardware as hw


@pytest.mark.parametrize("kind,params", [
    ("wheel", {}),
    ("wheel", {"bore": "bearing", "bearing": "608", "tread": "o-ring", "holes": 5, "diameter": 60, "width": 16}),
    ("wheel", {"tread": "v-groove", "hub": 6, "set_screw": "M3"}),
    ("grommet", {"split": True}),
    ("grommet", {"membrane": True, "mode": "reference"}),
    ("dowel", {}),
    ("dowel", {"mode": "print", "fit": "slip"}),
    ("snap_ring", {"size": 10, "type": "external"}),
    ("snap_ring", {"size": 16, "type": "internal"}),
    ("thumbscrew", {}),
    ("thumbscrew", {"style": "wing", "size": "M4"}),
    ("thumbscrew", {"style": "cap"}),
])
def test_new_parts(kind, params):
    r = hw.make(kind, **params)
    assert r["shape"].is_valid and r["shape"].volume > 0 and r["notes"]


def test_new_part_details():
    w = hw.make("wheel", bore="bearing", bearing="608", diameter=60, width=16)
    assert "2 x 608" in w["buy"]
    o = hw.make("wheel", tread="o-ring", o_ring=3.0, diameter=40)
    assert o["info"]["groove_d"] == pytest.approx(40 - 2 * 2.25, abs=0.01)
    assert hw.make("dowel", diameter=4, length=20)["buy"].startswith("Ø4 x 20")
    assert hw.make("snap_ring", size=10)["info"]["groove_d"] == 9.6
    with pytest.raises(ValueError):
        hw.make("snap_ring", size=11)
    with pytest.raises(ValueError):
        hw.make("wheel", bore="bearing", bearing="608", diameter=20)
    cat = hw.catalog()["kinds"]
    assert {"wheel", "grommet", "dowel", "snap_ring", "thumbscrew"} <= set(cat)
    assert next(f for f in cat["snap_ring"]["fields"] if f["name"] == "size")["type"] == "select"


def test_magnets_on_a_box():
    plain = box.build(box.BoxSpec(size=[100, 60, 40], lid="friction"))
    spec = box.BoxSpec(size=[100, 60, 40], lid="friction", magnet_lid={"d": 6, "t": 2}, magnets=[
        {"face": "floor", "at": [20, 0], "d": 10, "t": 3},
        {"face": "front", "at": [0, 15], "d": 8, "t": 2, "side": "inside"},
        {"face": "lid", "at": [0, 0], "d": 6, "t": 2, "hidden": True}])
    r = box.build(spec)
    assert r["base"].is_valid and r["lid"].is_valid
    text = " ".join(r["notes"])
    assert "magnet lid: 8 magnets" in text and "magnet 3" in text and "pause the print" in text
    assert r["lid"].volume != plain["lid"].volume
    with pytest.raises(ValueError):
        box.build(box.BoxSpec(lid="screw", magnet_lid={"d": 6, "t": 2}))
    with pytest.raises(ValueError):
        box.build(box.BoxSpec(magnets=[{"face": "front", "hidden": True}]))


def test_magnets_through_the_web():
    from fastapi.testclient import TestClient
    from enclosure.web import app
    c = TestClient(app)
    r = c.post("/api/preview", json={"size": [100, 60, 40], "lid": "snap", "magnet_lid": {"d": 6, "t": 2},
                                     "magnets": [{"face": "floor", "at": [0, 0], "d": 10, "t": 2}]})
    assert r.status_code == 200, r.text
    notes = " ".join(r.json()["notes"])
    assert "magnet lid" in notes and "magnet 1" in notes
