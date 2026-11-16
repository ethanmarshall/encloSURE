"""v2.6: Gridfinity bins inside the hinged case."""
import pytest

from enclosure import case, gridfinity


def _vol(x):
    return 0.0 if x is None else x.volume


def test_gridfinity_in_the_case():
    m = case.build(case.Case(grid_cols=3, grid_rows=2))
    plain = case.build(case.Case(size=(126.6, 84.6, 30.0)))
    assert m["base"].is_valid and len(m["base"].solids()) == 1
    assert m["base"].volume > plain["base"].volume + 2000                       # the baseplate is part of the floor
    assert m["base"].bounding_box().size.X == pytest.approx(plain["base"].bounding_box().size.X)
    [bins] = m["inserts"]
    assert bins["name"] == "gridfinity_bin_1x1x4" and bins["count"] == 6 and bins["size"] == [41.5, 41.5, 28.0]
    assert len(m["insert_placed"]) == 6
    for p in m["insert_placed"]:                                                # each drops into its pocket and clears the lid
        assert _vol(m["base"] & p) < 0.5 and _vol(m["lid"] & p) < 1e-3
    assert any("Gridfinity inside: a 3 x 2 baseplate" in n and "the grid sets it" in n for n in m["notes"])
    # A standard bin from the Gridfinity page fits the same pocket.
    std = gridfinity.bin_(1, 1, 3, lip=False)
    from build123d import Pos
    assert _vol(m["base"] & Pos(-42, -21, 2.4) * std) < 0.5


def test_gridfinity_bigger_bins_heights_and_gaps():
    m = case.build(case.Case(size=(100, 100, 45), grid_cols=4, grid_rows=3, grid_bins="2x1:2, 2x2:1"))
    got = {i["name"]: i["count"] for i in m["inserts"]}
    assert got == {"gridfinity_bin_1x1x6": 4, "gridfinity_bin_2x1x6": 2, "gridfinity_bin_2x2x6": 1}
    assert all(i["shape"].is_valid for i in m["inserts"])
    short = case.build(case.Case(grid_cols=2, grid_rows=1, grid_height=2, insert_label=True))
    assert short["inserts"][0]["size"][2] == 14.0 and any("between the bins and the lid" in c for c in short["checks"])
    assert _vol(short["base"] & short["insert_placed"][0]) < 0.5                # the label tab stays inside a short bin
    some = case.build(case.Case(grid_cols=2, grid_rows=2, grid_fill=False, grid_bins="1x1:1"))
    assert some["inserts"][0]["count"] == 1 and any("3 units of the grid left empty" in n for n in some["notes"])
    for bad in (dict(grid_cols=3), dict(grid_cols=2, grid_rows=2, size=(100, 100, 12)), dict(grid_cols=2, grid_rows=2, dividers_x=1),
                dict(grid_cols=2, grid_rows=2, insert_cols=2, insert_rows=2), dict(grid_cols=2, grid_rows=2, grid_height=9), dict(grid_cols=12, grid_rows=2)):
        with pytest.raises(ValueError):
            case.build(case.Case(**bad))


def test_gridfinity_case_writes_its_bins(tmp_path):
    out = case.write(case.Case(grid_cols=2, grid_rows=1), tmp_path)
    names = {p.name for p in tmp_path.iterdir()}
    assert "case_gridfinity_bin_1x1x4.stl" in names and "case_assembly.step" in names
