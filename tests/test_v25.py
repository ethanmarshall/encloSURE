"""v2.5: fit-test prints, the RC wheel and tyre as one two-material print, a wire channel on the
battery compartment, and a cable clamp, French cleat, hose barb and belt clamp."""
import pytest

from enclosure import hardware as hw


def _vol(x):
    return 0.0 if x is None else x.volume


def test_fit_test_is_three_small_pieces():
    for kind in hw.FIT_TESTS:
        extra = {"mode": "print"} if hw.catalog()["kinds"][kind]["modes"] else {}
        whole = hw.make(kind, **extra)
        r = hw.make(kind, fit_test=True, **extra)
        assert r["shape"].is_valid and len(r["shape"].solids()) == 3, kind
        assert r["size"][2] <= 8 and r["size"][0] < 100, kind
        assert len(r["info"]["fits"]) == 3 and r["info"]["fits"][0] >= 0 and "one notch" in r["notes"][1], kind
        assert any(f["name"] == "fit_test" for f in hw.catalog()["kinds"][kind]["fields"])
    k = hw.make("appliance_knob", fit_test=True, fit=0.2, bottom_chamfer=0.4, engrave_text="X")
    assert k["info"]["fits"] == [0.1, 0.2, 0.3] and "inlay" not in k
    # The loosest piece's hole is bigger than the tightest's.
    a, b, c = sorted(hw.make("shaft_collar", fit_test=True)["shape"].solids(), key=lambda s: s.bounding_box().min.X)
    assert a.bounding_box().size.Z < b.bounding_box().size.Z < c.bounding_box().size.Z
    with pytest.raises(ValueError, match="no fit test"):
        hw.make("flat_plate", fit_test=True)
    assert not any(f["name"] == "fit_test" for f in hw.catalog()["kinds"]["flat_plate"]["fields"])


def test_rc_wheel_and_tyre_in_one_print():
    r = hw.make("rc_wheel", piece="both, as one two-material print")
    assert r["shape"].is_valid and r["inlay"].is_valid and len(r["inlay"].solids()) == 1
    assert _vol(r["shape"] & r["inlay"]) < 1e-3                                   # they touch and don't overlap
    assert r["inlay"].bounding_box().size.X == pytest.approx(65, abs=0.1)
    slick = hw.make("rc_wheel", piece="both, as one two-material print", tread="slick")
    assert slick["inlay"].volume > r["inlay"].volume
    from enclosure import plate
    name, both = plate.part_item("rc_wheel", r["shape"], inlay=r["inlay"])
    assert both.label.startswith("group:") and len(both.solids()) == 2


def test_battery_wire_channel():
    a = hw.make("battery_holder", count=2)
    b = hw.make("battery_holder", count=2, wire_channel=True)
    assert b["shape"].is_valid and len(b["shape"].solids()) == 1
    assert b["size"][1] - a["size"][1] == pytest.approx(4.2) and any("wire channel" in n for n in b["notes"])
    assert hw.make("battery_holder", wire_channel=True, mount="internal holes")["shape"].is_valid
    nine = hw.make("battery_holder", cell="9V", wire_channel=True)
    assert nine["size"] == hw.make("battery_holder", cell="9V")["size"]


def test_clamp_cleat_barb_and_belt():
    from build123d import Align, Cylinder, Pos
    cc = hw.make("cable_clamp")
    assert cc["shape"].is_valid and len(cc["shape"].solids()) == 2 and cc["info"]["height_closed"] == pytest.approx(11.0)
    cl = hw.make("french_cleat")
    assert cl["shape"].is_valid and len(cl["shape"].solids()) == 2 and cl["size"][2] == 12.0 and cl["size"][1] == 150.0
    wall, hang = sorted(cl["shape"].solids(), key=lambda s: s.bounding_box().min.X)
    assert hang.volume < wall.volume                                              # the hanger is cut a little short
    assert len(hw.make("french_cleat", piece="wall cleat")["shape"].solids()) == 1
    hb = hw.make("hose_barb", tube_a="1/2", tube_b="1/4", barbs=4)
    assert hb["shape"].is_valid and len(hb["shape"].solids()) == 1 and "1/2 in (12.7 mm)" in hb["notes"][0]
    assert _vol(hb["shape"] & Cylinder(hb["info"]["bore_b"] / 2 - 0.05, 200)) < 1e-3          # open right through
    same = hw.make("hose_barb")
    assert same["size"][0] == pytest.approx(8 * 1.08 + 3, abs=0.01)
    bc = hw.make("belt_clamp")
    assert bc["shape"].is_valid and len(bc["shape"].solids()) == 2 and "6 grooves 0.75 mm deep" in bc["notes"][0]
    for kind, bad in (("cable_clamp", {"squeeze": 5}), ("french_cleat", {"height": 15}), ("hose_barb", {"tube_a": 3, "wall": 1.6}), ("belt_clamp", {"teeth": 1})):
        with pytest.raises(ValueError):
            hw.make(kind, **bad)
