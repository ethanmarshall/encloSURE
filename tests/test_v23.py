"""v2.3: handwheels, a wheel and TPU tyre for radio-controlled cars, and replacement appliance knobs."""
import pytest

from enclosure import hardware as hw


def _ok(r):
    assert r["shape"].is_valid and len(r["shape"].solids()) == 1
    return r


def test_handwheel_with_and_without_a_hub():
    hubbed = _ok(hw.make("handwheel"))
    assert hubbed["size"] == [100.0, 100.0, 20.0] and any("M4 set screw" in n for n in hubbed["notes"])
    flush = _ok(hw.make("handwheel", hub_length=0, set_screw="none", shaft="hex", bore_d="1/2", spokes=5))
    assert flush["size"][2] == 12.0 and "no hub" in flush["notes"][0] and "1/2 in (12.7 mm) hex shaft" in flush["notes"][0]
    assert flush["info"]["bore"] == pytest.approx(13.0)
    no_screw = _ok(hw.make("handwheel", set_screw="none"))
    assert no_screw["shape"].volume > hubbed["shape"].volume and no_screw["checks"]          # round, and nothing to hold it
    d = _ok(hw.make("handwheel", shaft="D (one flat)", spokes=0, handle="printed post", diameter=80))
    assert d["size"][2] > 45 and any("bears on the shaft's flat" in n for n in d["notes"])
    _ok(hw.make("handwheel", shaft="square", bore_d=10, diameter=150, rim=16, spokes=4, handle="hole for a bolt-on handle"))
    for bad in ({"hub_length": 0}, {"hub_length": 5}, {"rim": 30}, {"bore_d": 60}, {"shaft": "oval"}, {"shaft": "D (one flat)", "flat": 2}):
        with pytest.raises(ValueError):
            hw.make("handwheel", **bad)


def test_rc_wheel_and_tyre_go_together():
    rim = _ok(hw.make("rc_wheel"))
    tyre = _ok(hw.make("rc_wheel", piece="tyre (TPU)"))
    assert rim["size"][2] == 26.0 and tyre["size"][2] == 26.0 and tyre["size"][0] == pytest.approx(65, abs=0.1)
    # Each shows the other in place, and the two are the same pair of solids.
    assert rim["fitted"].volume == pytest.approx(tyre["shape"].volume) and tyre["fitted"].volume == pytest.approx(rim["shape"].volume)
    assert rim["info"]["tyre_bore"] == pytest.approx(50.96) and rim["info"]["tyre_thickness"] == 6.5
    # The tyre is stretched on: at the barrel the two overlap by the 2% squeeze and no more.
    both = rim["shape"] & tyre["shape"]
    assert both is not None and 0 < both.volume < rim["shape"].volume * 0.25
    slick = _ok(hw.make("rc_wheel", piece="tyre (TPU)", tread="slick"))
    ribbed = _ok(hw.make("rc_wheel", piece="tyre (TPU)", tread="ribbed"))
    assert slick["shape"].volume > ribbed["shape"].volume > tyre["shape"].volume
    small = _ok(hw.make("rc_wheel", tyre_d=30, width=12, rim_d=22, hex=7, hex_depth=3, axle_d=2, web="dish"))
    assert "7 mm drive hex" in small["notes"][0] and "solid dish" in small["notes"][0]
    plain = _ok(hw.make("rc_wheel", hex=0, axle_d="1/8"))
    assert "plain" in plain["notes"][1]
    for bad in ({"rim_d": 62}, {"hex": 30}, {"hex": 5, "axle_d": 4}, {"piece": "hubcap"}, {"mount_inset": 25}):
        with pytest.raises(ValueError):
            hw.make("rc_wheel", **bad)


def test_appliance_knob_fits_its_shaft():
    from build123d import Box, Pos
    k = _ok(hw.make("appliance_knob", grip="snug"))
    assert k["size"] == [45.0, 45.0, 28.0] and k["info"] == {"socket": 6.2, "flat": 4.7, "depth": 14.0}
    # A 6 mm D shaft with its flat toward the pointer (+Y) goes in; one turned half round does not.
    from build123d import Align, Cylinder
    rod = Cylinder(3, 12, align=(Align.CENTER, Align.CENTER, Align.MIN)) - Pos(0, 1.5 + 3, 6) * Box(10, 6, 14)
    clash = k["shape"] & Pos(0, 0, 0.5) * rod
    assert clash is None or clash.volume < 1e-3
    from build123d import Rot
    turned = k["shape"] & Pos(0, 0, 0.5) * (Rot(0, 0, 180) * rod)
    assert turned is not None and turned.volume > 1
    other = _ok(hw.make("appliance_knob", grip="snug", flat_at="6 o'clock (away from the pointer)"))
    fits = other["shape"] & Pos(0, 0, 0.5) * (Rot(0, 0, 180) * rod)
    assert fits is None or fits.volume < 1e-3
    split = _ok(hw.make("appliance_knob"))
    assert split["shape"].volume < k["shape"].volume and any("springs onto the shaft" in n for n in split["notes"])
    fluted = _ok(hw.make("appliance_knob", style="round, fluted (washer, dryer)", shaft_d="1/4", diameter=55, two_color=True))
    assert "1/4 in (6.35 mm) D shaft" in fluted["notes"][0] and fluted["inlay"].is_valid
    setscrew = _ok(hw.make("appliance_knob", style="round, smooth", shaft="round", set_screw="M3", grip="snug", diameter=30, height=18, depth=10, skirt=0))
    assert not setscrew["checks"] and hw.make("appliance_knob", shaft="round", grip="snug")["checks"]
    stem = _ok(hw.make("appliance_knob", shaft="double D (two flats)", stem_below=8, depth=18))
    assert stem["size"][2] == 36.0 and any("supports" in c for c in stem["checks"])
    _ok(hw.make("appliance_knob", shaft="splined", grip="snug"))
    for bad in ({"depth": 30}, {"shaft_d": 20}, {"diameter": 18, "shaft_d": 10}, {"style": "lever"}, {"flat": 7}):
        with pytest.raises(ValueError):
            hw.make("appliance_knob", **bad)


def test_they_are_on_the_page():
    cat = hw.catalog()
    for kind in ("handwheel", "rc_wheel", "appliance_knob"):
        assert cat["kinds"][kind]["printed_only"] and cat["kinds"][kind]["group"] == "Wheels, gears and knobs"
    assert cat["kinds"]["spur_gear"]["group"] == cat["kinds"]["wheel"]["group"] == cat["kinds"]["knob"]["group"] == "Wheels, gears and knobs"
    assert not any(k["group"] == "Motion" for k in cat["kinds"].values())
    f = {x["name"]: x for x in cat["kinds"]["appliance_knob"]["fields"]}
    assert f["shaft_d"]["type"] == "size" and f["flat_at"]["type"] == "select" and len(f["flat_at"]["options"]) == 4


def test_battery_cells_apart_or_together():
    apart = hw.make("battery_holder", cell="AA", count=3, mount="none")
    together = hw.make("battery_holder", cell="AA", count=3, mount="none", bays="one open compartment")
    assert together["shape"].is_valid and len(together["shape"].solids()) == 1
    assert apart["size"][1] - together["size"][1] == pytest.approx(3.2)          # two 1.6 mm walls gone
    assert together["shape"].volume < apart["shape"].volume
    assert "own bay" in apart["notes"][1] and "one open compartment" in together["notes"][1]
    one = hw.make("battery_holder", bays="one open compartment")
    assert one["size"] == hw.make("battery_holder")["size"] and not any("open compartment" in n for n in one["notes"])
    nine = hw.make("battery_holder", cell="9V", count=2, bays="one open compartment")
    assert nine["shape"].is_valid and "no wall between" in nine["notes"][1]
    with pytest.raises(ValueError):
        hw.make("battery_holder", bays="loose")
