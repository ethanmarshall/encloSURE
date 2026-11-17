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
    assert len(said) == 3 and "7 upright holes Ø8 x 15 mm deep" in said[1] and "15 compartments in 3 rows of 5" in said[2]
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
