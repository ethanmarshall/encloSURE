"""v1.4: Gridfinity bins, baseplates and feet under a box."""

import pytest

from build123d import Pos

from enclosure import box, gridfinity as gf, hardware as hw


def test_units():
    assert gf.units(41.5) == 1 and gf.units(41.6) == 2 and gf.units(125.5) == 3


def test_bin_fits_baseplate_and_stacks():
    plate, b = gf.baseplate(1, 1), gf.bin_(1, 1, 2, lip=False)
    i = plate.intersect(b)
    assert i is None or i.volume < 1e-3
    lo, up = gf.bin_(1, 1, 2), Pos(0, 0, 14) * gf.bin_(1, 1, 2)
    i = lo.intersect(up)
    assert i is None or i.volume < 1e-3


def test_parts():
    r = hw.make("gridfinity_bin", units_x=2, div_x=1, label=True, magnets=True)
    assert r["shape"].is_valid and r["size"][:2] == [83.5, 41.5]
    assert r["size"][2] == pytest.approx(21 + 4.4, abs=0.05)
    p = hw.make("gridfinity_baseplate", units_x=2, units_y=2)
    assert p["size"] == [84.0, 84.0, 4.65]
    with pytest.raises(ValueError):
        hw.make("gridfinity_bin", units_x=0)


def test_box_on_gridfinity_feet():
    r = box.build(box.BoxSpec(size=[100, 60, 40], gridfinity={"magnets": True}))
    bb = r["base"].bounding_box()
    assert r["base"].is_valid and bb.min.Z == pytest.approx(-5.95, abs=0.01)
    assert bb.size.X == pytest.approx(125.5, abs=0.01)
    assert any("Gridfinity base: 3 x 2" in n for n in r["notes"])
    with pytest.raises(ValueError):
        box.build(box.BoxSpec(gridfinity={}, din_rail=True))
