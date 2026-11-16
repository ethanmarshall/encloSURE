"""v2.4: your own knob markings, upright cell-pack holders, a top chamfer and words on any part,
RC wheel sizes by scale, and collars, couplers, bearing blocks, T-slot feet and vise jaws."""
import math

import pytest

from enclosure import hardware as hw
from enclosure import turning


def _vol(x):
    return 0.0 if x is None else x.volume


def _ok(r, solids=1):
    assert r["shape"].is_valid and len(r["shape"].solids()) == solids
    return r


def test_knob_markings_are_yours():
    assert turning._knob_marks("OFF|LO|MED|HI", 270, 0) == [("OFF", 0.0), ("LO", 90.0), ("MED", 180.0), ("HI", 270.0)]
    assert turning._knob_marks("0|1|2|3", 360, 0)[-1] == ("3", 270.0)                      # all the way round: no doubling up at the start
    assert turning._knob_marks("OFF@0|-@45|BAKE@180|.", 270, 30) == [("OFF", 0.0), ("-", 45.0), ("BAKE", 180.0), (".", 30.0)]
    plain = _ok(hw.make("appliance_knob", grip="snug"))
    marked = _ok(hw.make("appliance_knob", grip="snug", marks="OFF|LO|2|3|4|HI"))
    assert marked["size"][0] == 61.0 and plain["size"][0] == 45.0                           # a ring added for them
    assert any("6 markings" in n and "HI at 270°" in n for n in marked["notes"])
    two = _ok(hw.make("appliance_knob", style="round, fluted (washer, dryer)", marks="NORMAL@0|DELICATE@120|HEAVY DUTY@240", two_color=True, diameter=60))
    assert two["inlay"].is_valid and len(two["inlay"].solids()) > 10                        # the pointer and every letter
    assert hw.make("appliance_knob", marks="|".join(str(i) for i in range(20)), mark_size=6)["checks"]   # crowded
    for bad in ({"marks": "A@x"}, {"marks": "|".join("x" * 25)}, {"marks": "ABCDEFGHIJKLMNOP"}, {"marks": "A|B", "mark_size": 20}):
        with pytest.raises(ValueError):
            hw.make("appliance_knob", **bad)


def test_cell_pack_holders():
    r = _ok(hw.make("cell_pack_holder"))
    assert "1S3P" in r["notes"][0] and r["info"]["cells"] == 3 and len(r["fitted"].solids()) == 3
    assert r["info"]["pitch"] == pytest.approx(20.3) and r["info"]["pocket"] == pytest.approx(18.7)
    grid = _ok(hw.make("cell_pack_holder", series=3, parallel=4, layout="grid (rows of cells)", ears="four ears"))
    assert grid["info"]["cells"] == 12 and "10.8 V" in grid["notes"][0]
    cs = grid["info"]["centres"]
    assert min(math.dist(a, b) for i, a in enumerate(cs) for b in cs[i + 1:]) == pytest.approx(20.3, abs=0.01)
    tri = _ok(hw.make("cell_pack_holder", layout="round bundle (fits a tube)"))
    assert tri["size"][0] == pytest.approx(tri["size"][1]) and tri["size"][0] < 46            # three in a triangle, in a circle
    seven = _ok(hw.make("cell_pack_holder", cell="21700", parallel=7, layout="round bundle (fits a tube)"))
    assert [0.0, 0.0] in seven["info"]["centres"]                                             # one in the middle, six round it
    # A cell drops into its pocket and is stopped by the lip.
    from build123d import Align, Cylinder, Pos
    x, y = r["info"]["centres"][0]
    cell = Cylinder(9.2, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
    assert _vol(r["shape"] & Pos(x, y, 1.6) * cell) < 1e-3
    assert (r["shape"] & Pos(x, y, 0.5) * cell).volume > 20
    _ok(hw.make("cell_pack_holder", series=13, parallel=5))
    for bad in ({"series": 10, "parallel": 10}, {"cell": "D"}, {"gap": 0.2}, {"layout": "spiral"}):
        with pytest.raises(ValueError):
            hw.make("cell_pack_holder", **bad)
    assert hw.catalog()["kinds"]["cell_pack_holder"]["group"] == "Batteries"


def test_top_chamfer_and_words_on_any_part():
    a = hw.make("flat_plate")
    b = _ok(hw.make("flat_plate", top_chamfer=1.0))
    assert 0 < a["shape"].volume - b["shape"].volume and b["size"] == a["size"] and any("on the top edges" in n for n in b["notes"])
    c = _ok(hw.make("flat_plate", engrave_text="AB-12"))
    assert 0.5 < a["shape"].volume - c["shape"].volume < 60 and any("'AB-12' cut" in n for n in c["notes"])
    both = _ok(hw.make("extrusion_foot", engrave_text="LEG 1", top_chamfer=0.5, bottom_chamfer=0.4))
    assert len([n for n in both["notes"] if "chamfer" in n or "cut 0.5" in n]) >= 2
    small = hw.make("washer", mode="print", engrave_text="TOO BIG TO FIT HERE")
    assert small["shape"].is_valid and any("left off" in c for c in small["checks"])
    assert hw.make("screw", engrave_text="X", top_chamfer=1)["shape"].volume == pytest.approx(hw.make("screw")["shape"].volume)   # bought
    for bad in ({"top_chamfer": 9}, {"engrave_text": "x" * 30}):
        with pytest.raises(ValueError):
            hw.make("flat_plate", **bad)
    names = [f["name"] for f in hw.catalog()["kinds"]["shim"]["fields"]]
    assert names[-3:] == ["bottom_chamfer", "top_chamfer", "engrave_text"]
    assert "engrave_text" not in [f["name"] for f in hw.catalog()["kinds"]["label_plate"]["fields"]]


def test_rc_wheels_by_scale():
    for name, sizes_ in list(turning.RC_SCALES.items())[1:]:
        rim = _ok(hw.make("rc_wheel", scale=name))
        tyre = _ok(hw.make("rc_wheel", scale=name, piece="tyre (TPU)"))
        assert tyre["size"][0] == pytest.approx(sizes_[0], abs=0.1) and rim["size"][2] == sizes_[1]
        assert "usual ones" in rim["notes"][1]
    assert hw.make("rc_wheel", scale="1/8 buggy (112 x 42, 17 mm hex)", tyre_d=20)["info"]["tyre_d"] == 112.0   # the scale wins
    with pytest.raises(ValueError):
        hw.make("rc_wheel", scale="1/5")


def test_collars_couplers_blocks_feet_and_jaws():
    from build123d import Align, Cylinder, Pos
    col = _ok(hw.make("shaft_collar"))
    assert col["info"] == {"od": 26, "bore": 8.2}
    rod = Cylinder(4.0, 30, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    assert _vol(col["shape"] & rod) < 1e-6
    _ok(hw.make("shaft_collar", style="set screw", shaft_d="1/2"))
    cp = _ok(hw.make("shaft_coupler"))
    assert cp["size"][2] == 25.0 and not cp["checks"] and hw.make("shaft_coupler", shaft_a=8, shaft_b=5)["checks"]
    assert _vol(cp["shape"] & Pos(0, 0, 18) * Cylinder(4.0, 10)) < 1e-6 and (cp["shape"] & Pos(0, 0, 6) * Cylinder(4.0, 10)).volume > 10
    blk = _ok(hw.make("bearing_block"))
    assert blk["info"]["centre_height"] == 18 and blk["buy"].startswith("608") and blk["size"][2] == 9.0
    assert _ok(hw.make("bearing_block", bearing="6001", centre_height=40))["info"]["centre_height"] == 40
    foot = _ok(hw.make("extrusion_foot"))
    assert foot["size"][2] == pytest.approx(10, abs=0.02) and "5/16-18" in foot["notes"][0]
    assert "two holes" in _ok(hw.make("extrusion_foot", profile="1530 (80/20, 1.5 x 3 in)"))["notes"][0]
    assert _ok(hw.make("extrusion_foot", profile="2020 (20 mm)", keys=False))["size"] == [28.0, 28.0, 8.0]
    jaw = _ok(hw.make("vise_jaws"))
    assert jaw["size"] == [100.0, 23.0, 17.0]
    flat = [f for f in jaw["shape"].faces() if abs(f.center().Z) < 1e-6]
    assert sum(f.area for f in flat) > 100 * 23 * 0.6                                         # it lies on its work face to print
    _ok(hw.make("vise_jaws", grooves="horizontal and upright V", jaw_width=150)); _ok(hw.make("vise_jaws", magnet_d=0, grooves="plain"))
    for kind, bad in (("shaft_collar", {"od": 10}), ("shaft_coupler", {"length": 5}), ("bearing_block", {"centre_height": 5}), ("vise_jaws", {"magnet_t": 9})):
        with pytest.raises(ValueError):
            hw.make(kind, **bad)
    cat = hw.catalog()["kinds"]
    assert cat["shaft_collar"]["group"] == "Shafts and bearings" and cat["extrusion_foot"]["group"] == "T-slot extrusion" and cat["vise_jaws"]["group"] == "Jigs"
