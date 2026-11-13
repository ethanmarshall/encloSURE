"""Quick boxes: every lid type builds as one valid base and lid that do not overlap, the box
reads back right (standoffs, openings, floor, ceiling), and bad settings are refused."""

import json

import pytest

from enclosure import box, geom, shell
from enclosure.cli import main

CUTOUTS = [
    {"face": "-X", "shape": "rect", "size": [9.5, 3.8], "at": [0, 8.6], "radius": 1.0},
    {"face": "+Y", "shape": "round", "size": [8.0], "at": [20, 15]},
]


def spec_for(lid, **kw):
    cut = CUTOUTS + ([{"face": "lid", "shape": "round", "size": [6.0], "at": [20, 0]}]
                     if lid in ("screw", "friction", "snap") else [])
    return box.BoxSpec(size=[100, 60, 40], lid=lid, standoffs=box.standoff_pattern("rect:80x40"),
                       cutouts=cut, **kw)


@pytest.mark.parametrize("lid", box.LIDS)
def test_every_lid_builds_and_reads_back(lid, tmp_path):
    spec = spec_for(lid, flange=10 if lid == "screw" else 0)
    out = box.write(spec, tmp_path, stl=False)
    made = box.build(spec)
    base, top = made["base"], made["lid"]
    assert len(base.solids()) == 1 and base.is_valid
    if lid == "none":
        assert top is None and "lid" not in out["files"]
    else:
        assert len(top.solids()) == 1 and top.is_valid
        assert geom.overlap_volume(base, top) < 1e-3, "the lid in place must not run into the base"
    enc, _ = shell.read(geom.load(out["files"]["base"]),
                        geom.load(out["files"]["lid"]) if top is not None else None)
    assert enc.floor == 2.0
    assert enc.cavity_bounds[0][:2] == (-50.0, -30.0) and enc.cavity_bounds[1][:2] == (50.0, 30.0)
    # The board standoffs, and only those (not the lid's corner posts or their holes).
    assert sorted(b.center[:2] for b in enc.bosses) == sorted([x, y] for x, y in spec.standoffs)
    assert all(b.top == 7.0 and b.screw == "M3 heat-set insert" for b in enc.bosses)
    walls = sorted(o.wall for o in enc.openings)
    assert walls == sorted(["-X", "+Y"] + (["lid"] if lid in ("screw", "friction", "snap") else []))
    usb = next(o for o in enc.openings if o.wall == "-X")
    assert (usb.width, usb.height) == (9.5, 3.8) and usb.center[2] == pytest.approx(10.6)


def test_sizes_inner_and_outer():
    inner = box.BoxSpec(size=[100, 60, 40], lid="screw")
    assert inner.outer == (104.0, 64.0, 44.0)
    outer = box.BoxSpec(size=[104, 64, 44], size_is="outer", lid="screw")
    assert outer.inner == (100.0, 60.0, 40.0)
    assert box.BoxSpec(size=[100, 60, 40], lid="slide").outer[2] == 45.0  # the panel sits in the walls


def test_settings_round_trip_and_cli(tmp_path, capsys):
    code = main(["box", "--size", "120x80x45", "--lid", "screw", "--standoffs", "rect:100x60",
                 "--standoff-screw", "M2.5", "--cutout", "left:rect:9.5x3.8r1@0,9",
                 "--cutout=+Y:round:8@20,15", "--no-stl", "-o", str(tmp_path / "a")])
    assert code == 0
    saved = box.load(tmp_path / "a" / "box.json")
    assert saved.standoff_screw == "M2.5" and saved.cutouts[0]["face"] == "-X"
    capsys.readouterr()
    assert main(["box", "--from", str(tmp_path / "a" / "box.json"), "--lid", "snap", "--no-stl",
                 "-o", str(tmp_path / "b")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["outer"] == [124.0, 84.0, 49.0]
    assert box.load(tmp_path / "b" / "box.json").lid == "snap"


def test_bad_settings_are_refused(capsys):
    with pytest.raises(ValueError):
        box.Cutout.parse("side:rect:9x3@0,1")
    with pytest.raises(ValueError):
        box.Cutout.parse("left:rect:9@0,1")
    with pytest.raises(ValueError):
        box.build(box.BoxSpec(size=[50, 40, 20], standoffs=[[30, 0]]))  # outside the walls
    with pytest.raises(ValueError):
        box.BoxSpec(size=[10, 10, 10], wall=0.5).check()
    with pytest.raises(ValueError):
        box.BoxSpec(lid="hinged").check()
    assert main(["box", "--size", "6x6x3", "--outer", "--wall", "3"]) == 2
