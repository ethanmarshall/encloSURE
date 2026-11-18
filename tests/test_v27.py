"""v2.7: a hinged case laid out from a list of sections."""
import pytest

from enclosure import case

I = 25.4
KIT = [{"kind": "space", "name": "soldering iron box", "x": 8 * I, "y": 4 * I, "z": 1 * I},
       {"kind": "holes", "name": "heat stake tips", "count": 7, "d": 8, "depth": 15, "slot_l": 60, "slot_w": 12},
       {"kind": "cells", "name": "heat-set inserts", "count": 15, "x": I, "y": I}]


def _vol(x):
    return 0.0 if x is None else x.volume


def test_sections_plan_the_case():
    p = case.plan_sections(KIT)
    # Two rows, the box along the back: compact, and longer than deep so the hinges are on a long side.
    assert (round(p["L"], 1), round(p["W"], 1), p["bands"], p["swap"]) == (204.2, 182.4, 2, False)
    box, holes, cells = p["sections"]
    assert not box["turned"] and box["len"] == pytest.approx(204.2) and box["band"] == 0 and holes["band"] == cells["band"] == 1
    assert holes["per_row"] == 7 and holes["rows"] == 1 and (cells["rows"], cells["per_row"]) == (5, 3)
    loose = case.plan_sections([{"kind": "cells", "count": 10, "x": 30, "y": 20}])   # nothing fixes the width: most nearly square
    assert max(loose["L"], loose["W"]) < 100 and not loose["swap"]
    # A layout that comes out deeper than long is turned a quarter turn, so the hinges are never on a short side.
    for secs in ([{"kind": "holes", "count": 6, "d": 8, "depth": 15, "slot_l": 63.5, "slot_w": 12.7}],
                 [{"kind": "space", "x": 50, "y": 120, "z": 10, "turn": "as typed"}, {"kind": "cells", "count": 4, "x": 25, "y": 25}]):
        q = case.plan_sections(secs)
        m = case.build(case.Case(sections=secs))
        assert q["swap"] and m["inner"][0] > m["inner"][1] and m["base"].is_valid and len(m["base"].solids()) == 1
        assert any("hinges are on a long side" in n for n in m["notes"])


def test_sections_build_into_the_tray():
    from build123d import Box, Pos
    m = case.build(case.Case(sections=KIT))
    tray, L, W = m["base"], m["inner"][0], m["inner"][1]
    assert tray.is_valid and len(tray.solids()) == 1 and m["inner"] == [204.2, 182.4, 30.0]
    said = [n for n in m["notes"] if n.startswith("  ")]
    assert len(said) == 3 and "7 holes Ø8 mm going 15 mm down from its top" in said[1] and "15 compartments, 5 along the length by 3 across" in said[2]
    fl = 2.4
    # The soldering iron box drops into its space along the back and the lid shuts over it.
    thing = Pos(0, W / 2 - 102.6 / 2, fl + 0.05 + I / 2) * Box(8 * I, 4 * I, I)
    assert _vol(tray & thing) < 1e-3 and _vol(m["lid"] & thing) < 1e-3
    # The block of holes is solid right up to the top of the tray, with the holes going down into it.
    hole = next(e for e in case.plan_sections(KIT)["sections"] if e["kind"] == "holes")
    xc, yc = -L / 2 + hole["x0"], W / 2 - hole["y0"] - hole["dep"] / 2
    used = hole["pitch"] + 3 + hole["slot_w"]
    hx = xc + (hole["len"] - used) / 2 + hole["pitch"] / 2
    assert _vol(tray & Pos(hx, yc, fl + 20) * Box(2, 2, 2)) < 1e-3                       # down the middle hole
    assert _vol(tray & Pos(hx, yc, fl + 5) * Box(2, 2, 2)) == pytest.approx(8.0)        # solid under it
    assert _vol(tray & Pos(xc + 1.5, yc + 30, fl + 23) * Box(2, 2, 2)) == pytest.approx(8.0)   # solid near the top, away from the holes
    # A tall thing raises the case.
    tall = case.build(case.Case(sections=[{"kind": "space", "x": 60, "y": 40, "z": 55}]))
    assert tall["inner"][2] == 57.0 and any("height went up" in n for n in tall["notes"])
    small = case.build(case.Case(sections=[{"kind": "holes", "count": 2, "d": 6, "depth": 10}]))
    assert small["inner"][0] == 45.0 and small["base"].is_valid
    # The first row can go by the latches instead.
    flipped = case.build(case.Case(sections=KIT, sections_front=True))
    assert _vol(flipped["base"] & Pos(0, -(W / 2 - 102.6 / 2), fl + 0.05 + I / 2) * Box(8 * I, 4 * I, I)) < 1e-3


def test_sections_say_what_is_wrong():
    for bad in ([{"kind": "x"}], [{"kind": "space", "x": 1, "y": 2}], [{"kind": "holes", "count": 0}], [{"kind": "cells", "count": 0}], "x",
                [{"kind": "holes", "count": 2, "slot_l": 30}], [{"kind": "holes", "count": 2, "slot_w": 30}], [{"kind": "space", "x": "a", "y": 2}], [KIT[0]] * 17):
        with pytest.raises(ValueError):
            case.build(case.Case(sections=bad))
    with pytest.raises(ValueError, match="pick one"):
        case.build(case.Case(sections=KIT, grid_cols=2, grid_rows=2))
    turned = case.plan_sections([{"kind": "holes", "count": 3, "d": 8, "slot_l": 12, "slot_w": 60}])["sections"][0]
    assert (turned["slot_l"], turned["slot_w"], turned["slot_d"]) == (60, 12, 12)      # the longer one is the length, whichever box it was typed in
    shallow = case.build(case.Case(sections=[{"kind": "holes", "count": 4, "d": 6, "depth": 60}]))
    assert any("holes are" in c for c in shallow["checks"])


def test_sections_in_rows_to_set_sizes():
    """The case as asked for in inches: irons and tips along the back, 18 one-inch compartments and a catch-all in front."""
    secs = [{"kind": "space", "name": "soldering irons", "x": 8.1 * I, "y": 3.25 * I, "z": 0, "fit": 0, "turn": "as typed"},
            {"kind": "holes", "name": "heat stake tips", "count": 7, "d": 8, "depth": 15, "slot_l": 60, "slot_w": 12, "len": 1.3 * I, "dep": 3.25 * I},
            {"kind": "break"},
            {"kind": "cells", "name": "heat-set inserts", "count": 18, "x": I, "y": I},
            {"kind": "open", "name": "catch-all"}]
    p = case.plan_sections(secs, 0.1 * I)
    assert p["L"] / I == pytest.approx(9.5) and p["W"] / I == pytest.approx(6.55) and p["bands"] == 2
    irons, tips, cells, rest = p["sections"]
    assert (irons["y0"], tips["y0"]) == (0.0, 0.0) and tips["x0"] / I == pytest.approx(8.2) and tips["per_row"] == 7
    assert (cells["rows"], cells["per_row"]) == (6, 3) and cells["y0"] / I == pytest.approx(3.35) and cells["cell_len"] == pytest.approx(I)
    assert rest["len"] / I == pytest.approx(2.9) and rest["dep"] / I == pytest.approx(3.2)
    m = case.build(case.Case(sections=secs, section_wall=0.1 * I))
    tray, (L, W, H) = m["base"], m["inner"]
    assert tray.is_valid and len(tray.solids()) == 1 and (L, W) == (241.3, 166.37)
    from build123d import Box, Pos
    fl = 2.4
    probe = lambda x_in, y_in: _vol(tray & Pos(-L / 2 + x_in * I, W / 2 - y_in * I, fl + 8) * Box(1, 1, 1))   # x from the left, y from the hinges
    assert probe(4, 1.6) < 1e-6                       # the irons' space is open
    assert probe(8.15, 1.6) == pytest.approx(1.0)     # the wall between the irons and the tips
    assert probe(4, 3.3) == pytest.approx(1.0)        # the wall between the two rows
    assert probe(0.5, 3.85) < 1e-6 and probe(1.05, 3.85) == pytest.approx(1.0) and probe(0.5, 4.4) == pytest.approx(1.0)   # a compartment and its walls
    assert probe(6.55, 5) == pytest.approx(1.0) and probe(8, 5) < 1e-6                                        # the catch-all, walled off
    assert any("they set the inside to 241.3 x 166.37 mm" in n for n in m["notes"])
    wide = case.plan_sections([{"kind": "space", "x": 50, "y": 30}, {"kind": "break"}, {"kind": "holes", "count": 3, "d": 8, "len": 80}, {"kind": "space", "x": 40, "y": 20}])
    assert wide["L"] == pytest.approx(80 + 1.2 + 41) and wide["sections"][1]["spare"]          # the longest row sets the length; the short one is left open at its end
    with pytest.raises(ValueError):
        case.build(case.Case(sections=secs, section_wall=0.2))


def test_holes_of_different_sizes():
    from build123d import GeomType
    secs = [{"kind": "holes", "name": "tips", "ds": [8, 8, 6.5, 5, 5, 4, 10], "depth": 15, "slot_l": 26, "slot_w": 12, "len": 33.02, "dep": 82.55}]
    e = case.plan_sections(secs)["sections"][0]
    assert e["count"] == 7 and e["d"] == 10 and e["ds"] == [8, 8, 6.5, 5, 5, 4, 10]
    m = case.build(case.Case(sections=secs))
    assert m["base"].is_valid and any("7 holes of Ø8 mm, Ø8 mm, Ø6.5 mm, Ø5 mm, Ø5 mm, Ø4 mm, Ø10 mm" in n and "a slot 26 x 12 mm" in n for n in m["notes"])
    radii = sorted({round(f.radius, 2) for f in m["base"].faces() if f.geom_type == GeomType.CYLINDER and f.radius in (2.0, 2.5, 3.25, 4.0, 5.0)})
    assert radii == [2.0, 2.5, 3.25, 4.0, 5.0]
    assert case.plan_sections([{"kind": "holes", "ds": "8, 1/4, 5mm"}])["sections"][0]["ds"] == [8.0, 6.35, 5.0]
    same = case.plan_sections([{"kind": "holes", "count": 3, "d": 6}])["sections"][0]
    assert same["ds"] is None and same["count"] == 3
    for bad in ({"ds": [1]}, {"ds": "a,b"}, {"ds": [5] * 61}):
        with pytest.raises(ValueError):
            case.plan_sections([{"kind": "holes", **bad}])


def test_lid_ribs_over_the_compartments():
    from build123d import Box, Pos
    secs = [{"kind": "space", "name": "irons", "x": 205.74, "y": 82.55, "z": 0, "fit": 0, "turn": "as typed"},
            {"kind": "holes", "name": "tips", "ds": [8, 8, 8, 8, 8, 8, 10], "depth": 15, "slot_l": 27, "slot_w": 8, "slot_d": 7, "len": 33.02, "dep": 82.55},
            {"kind": "break"}, {"kind": "cells", "name": "inserts", "count": 24, "x": I, "y": I}]
    kw = dict(size=(241.3, 166.37, 38.1), sections=secs, section_wall=2.54)
    m, bare = case.build(case.Case(**kw)), case.build(case.Case(**kw, lid_ribs=False))
    lid, (L, W, H) = m["lid"], m["inner"]
    assert lid.is_valid and len(lid.solids()) == 1 and _vol(lid & m["base"]) < 1e-3
    assert lid.volume - bare["lid"].volume > 5000 and any("ribs 3.3 mm deep under the lid" in n for n in m["notes"])
    assert not any("ribs" in n and "under the lid" in n for n in bare["notes"])
    # Over a compartment wall the lid comes down to 0.3 mm above it; over a compartment, and over the irons, it doesn't.
    cells = next(e for e in case.plan_sections(secs, 2.54)["sections"] if e["kind"] == "cells")
    z = 2.4 + H - 2.0                                   # 2 mm under the lid's inside face
    x_wall, y_mid = -L / 2 + cells["cell_len"] + 1.27, W / 2 - cells["y0"] - 12.7
    assert _vol(lid & Pos(x_wall, y_mid, z) * Box(1, 1, 1)) == pytest.approx(1.0)
    assert _vol(lid & Pos(-L / 2 + 12, y_mid, z) * Box(1, 1, 1)) < 1e-6
    assert _vol(lid & Pos(0, W / 2 - 40, z) * Box(1, 1, 1)) < 1e-6
    assert cells["rows"] == 8 and cells["per_row"] == 3 and m["inner"][2] == 38.1


def test_finger_notch_and_the_printed_kit_case():
    """The case as printed and corrected: the iron box along the back, tips and 18 compartments in front."""
    from build123d import Box, Pos
    secs = [{"kind": "space", "name": "soldering iron box", "x": 203.2, "y": 101.6, "z": I, "fit": 1, "turn": "as typed", "notch": 22},
            {"kind": "break"},
            {"kind": "holes", "name": "tips", "ds": [8, 8, 8, 8, 8, 8, 10], "depth": 15, "slot_l": 35.2, "slot_w": 7.4, "slot_d": 6.4},
            {"kind": "cells", "name": "inserts", "count": 18, "x": I, "y": I}]
    kw = dict(size=(204.2, 182.4, 38.1), sections=secs)
    m = case.build(case.Case(**kw))
    plain = case.build(case.Case(**{**kw, "sections": [dict(secs[0], notch=0)] + secs[1:]}))
    tray, (L, W, H) = m["base"], m["inner"]
    assert tray.is_valid and len(tray.solids()) == 1 and (L, W) == (204.2, 182.4)
    p = case.plan_sections(secs)
    cells = p["sections"][2]
    assert (cells["rows"], cells["per_row"]) == (6, 3) and p["sections"][1]["x0"] == 0.0     # the tips are at the left of the front row
    # The notch is in the wall between the box and the third compartment, centred on that compartment.
    assert 250 < plain["base"].volume - tray.volume < 400 and any("finger notch 22 mm wide, cut 12 mm down" in n and "compartment 3" in n for n in m["notes"])
    xc = -L / 2 + cells["x0"] + 2 * (cells["cell_len"] + 1.2) + cells["cell_len"] / 2
    y_wall = W / 2 - 102.6 - 0.6
    assert _vol(tray & Pos(xc, y_wall, 2.4 + 30) * Box(4, 0.6, 2)) < 1e-6                     # cut away near the top
    assert _vol(tray & Pos(xc, y_wall, 2.4 + 15) * Box(4, 0.6, 2)) == pytest.approx(4.8)      # still there lower down
    # Its depth is yours to set, and its corners can be rounded: less comes out, and nothing sharp is left.
    soft = case.build(case.Case(**{**kw, "sections": [dict(secs[0], notch_depth=10, notch_round=4)] + secs[1:]}))
    assert soft["base"].is_valid and len(soft["base"].solids()) == 1 and any("cut 10 mm down" in n and "corners rounded 4 mm" in n for n in soft["notes"])
    square = case.build(case.Case(**{**kw, "sections": [dict(secs[0], notch_depth=10)] + secs[1:]}))
    assert 0 < soft["base"].volume - square["base"].volume < 150
    assert _vol(soft["base"] & Pos(xc, y_wall, 2.4 + 34 - 5) * Box(4, 0.6, 2)) < 1e-6 and _vol(soft["base"] & Pos(xc, y_wall, 2.4 + 34 - 12) * Box(4, 0.6, 2)) == pytest.approx(4.8)
    assert _vol(tray & Pos(xc + 30, y_wall, 2.4 + 30) * Box(4, 0.6, 2)) == pytest.approx(4.8)  # and beside it
    # Holes of mixed sizes keep the same plastic between each pair.
    last = case.build(case.Case(sections=[{"kind": "space", "x": 60, "y": 40, "notch": 20}]))
    assert any("no finger notch" in c for c in last["checks"])


def test_scoops_at_the_front_of_each_compartment():
    from build123d import Box, Pos
    def kit(scoop):
        return [{"kind": "space", "name": "box", "x": 205.74, "y": 82.8, "fit": 0, "turn": "as typed"}, {"kind": "break"},
                {"kind": "cells", "name": "inserts", "count": 18, "x": I, "y": I, "scoop": scoop}]
    flat, m = case.build(case.Case(sections=kit(0))), case.build(case.Case(sections=kit(8)))
    tray, (L, W, H) = m["base"], m["inner"]
    assert tray.is_valid and len(tray.solids()) == 1 and tray.volume > flat["base"].volume + 4000
    assert any("scoop of 8 mm radius" in n for n in m["notes"])
    cells = case.plan_sections(kit(8))["sections"][1]
    cw = (cells["dep"] - 2 * 1.2) / 3
    xc = -L / 2 + cells["cell_len"] / 2
    front = W / 2 - cells["y0"] - cw                      # the first compartment's wall nearer the latches
    probe = lambda y, z: _vol(tray & Pos(xc, y, 2.4 + z) * Box(1, 0.4, 0.4))
    assert probe(front + 1.0, 1.0) == pytest.approx(0.16)    # filled in the corner by the front wall
    assert probe(front + 7.0, 5.0) < 1e-6                    # open above the curve
    assert probe(front + cw - 1.0, 1.0) < 1e-6               # and no ramp at the back wall
    turned = case.build(case.Case(sections=kit(8), sections_front=True))
    assert turned["base"].is_valid and turned["base"].volume == pytest.approx(tray.volume, rel=1e-4)
    with pytest.raises(ValueError):
        case.plan_sections(kit(40))
