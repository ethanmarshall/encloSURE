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
    assert (round(p["L"], 1), round(p["W"], 1)) == (213.6, 204.2)                 # the box turned across: nearly square, not 370 mm long
    box, holes, cells = p["sections"]
    assert box["turned"] and box["len"] == pytest.approx(102.6) and holes["per_row"] == 7 and holes["rows"] == 1
    assert (cells["rows"], cells["per_row"]) == (3, 5) and cells["cell_len"] == I
    long = case.plan_sections([{**KIT[0], "turn": "as typed"}, *KIT[1:]])
    assert long["L"] > 330 and long["W"] == pytest.approx(102.6)
    loose = case.plan_sections([{"kind": "cells", "count": 10, "x": 30, "y": 20}])   # nothing fixes the width: most nearly square
    assert max(loose["L"], loose["W"]) < 100


def test_sections_build_into_the_tray():
    from build123d import Box, Pos
    m = case.build(case.Case(sections=KIT))
    tray, L, W = m["base"], m["inner"][0], m["inner"][1]
    assert tray.is_valid and len(tray.solids()) == 1 and m["inner"] == [213.6, 204.2, 30.0]
    said = [n for n in m["notes"] if n.startswith("  ")]
    assert len(said) == 3 and "7 upright holes Ø8 x 15 mm deep" in said[1] and "15 compartments, 3 along the length by 5 across" in said[2]
    fl = 2.4
    # The soldering iron box drops into its space and the lid shuts over it.
    thing = Pos(-L / 2 + 102.6 / 2, 0, fl + 0.05 + I / 2) * Box(4 * I, 8 * I, I)
    assert _vol(tray & thing) < 1e-3 and _vol(m["lid"] & thing) < 1e-3
    # The holes block is solid between its holes and open at each hole.
    assert _vol(tray & Pos(-L / 2 + 103.8 + 7.0, 0, fl + 10) * Box(2, 2, 2)) < 1e-3          # down the middle hole
    assert _vol(tray & Pos(-L / 2 + 103.8 + 7.0, 9, fl + 5) * Box(2, 2, 2)) == pytest.approx(8.0)   # between two holes
    plain = case.build(case.Case(size=(213.6, 204.2, 30.0)))
    assert tray.volume > plain["base"].volume + 30000
    # A tall thing raises the case.
    tall = case.build(case.Case(sections=[{"kind": "space", "x": 60, "y": 40, "z": 55}]))
    assert tall["inner"][2] == 57.0 and any("height went up" in n for n in tall["notes"])
    small = case.build(case.Case(sections=[{"kind": "holes", "count": 2, "d": 6, "depth": 10}]))
    assert small["inner"][0] == 45.0 and small["base"].is_valid


def test_sections_say_what_is_wrong():
    for bad in ([{"kind": "x"}], [{"kind": "space", "x": 1, "y": 2}], [{"kind": "holes", "count": 0}], [{"kind": "cells", "count": 0}], "x",
                [{"kind": "holes", "count": 2, "slot_l": 30}], [{"kind": "space", "x": "a", "y": 2}], [KIT[0]] * 9):
        with pytest.raises(ValueError):
            case.build(case.Case(sections=bad))
    with pytest.raises(ValueError, match="pick one"):
        case.build(case.Case(sections=KIT, grid_cols=2, grid_rows=2))
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
    assert any("9.50 x 6.55 in" in n for n in m["notes"])
    wide = case.plan_sections([{"kind": "space", "x": 50, "y": 30}, {"kind": "break"}, {"kind": "holes", "count": 3, "d": 8, "len": 80}, {"kind": "space", "x": 40, "y": 20}])
    assert wide["L"] == pytest.approx(80 + 1.2 + 41) and wide["sections"][1]["spare"]          # the longest row sets the length; the short one is left open at its end
    with pytest.raises(ValueError):
        case.build(case.Case(sections=secs, section_wall=0.2))
