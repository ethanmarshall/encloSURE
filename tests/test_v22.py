"""v2.2: sizes in fractions of an inch, jigs that say their drill size and show their bushing,
rounded corners to hold, a bed-edge chamfer on any part, and labels drawn from font outlines."""
import pytest

from enclosure import hardware as hw
from enclosure import sizes


def test_sizes_as_a_shop_says_them():
    assert sizes.parse(5) == (5.0, "5 mm") and sizes.parse("5 mm")[0] == 5.0
    assert sizes.parse("1/4")[0] == pytest.approx(6.35) and sizes.parse('13/64"')[0] == pytest.approx(5.159375)
    assert sizes.parse("1-1/2")[0] == pytest.approx(38.1) and sizes.parse("1 1/2 in")[0] == pytest.approx(38.1)
    assert sizes.parse("0.201 in")[0] == pytest.approx(5.1054) and sizes.parse("")[0] == 0
    assert sizes.parse("13/64")[1] == "13/64 in (5.159 mm)"
    assert sizes.short("1/4", 6.35) == '1/4"' and sizes.short(5, 5.0) == "Ø5" and sizes.short("2/8", 6.35) == '1/4"'
    for bad in ("abc", "1/0", "1/4 mm", "1//4"):
        with pytest.raises(ValueError):
            sizes.parse(bad)


def test_jig_takes_fractions_and_shows_the_bushing():
    r = hw.make("extrusion_offset_jig", drill_d="13/64", bushing_od="3/8", offsets="3/4, 2-1/4")
    assert r["shape"].is_valid and len(r["shape"].solids()) == 1
    assert r["info"]["drill"] == pytest.approx(5.1594) and r["info"]["bushing"] == pytest.approx(9.525) and r["info"]["offsets"] == [19.05, 57.15]
    assert "13/64 in (5.159 mm) drill" in r["notes"][0]
    bush = r["fitted"]                               # two steel bushings, drawn but not part of the print
    assert len(bush.solids()) == 2 and bush.bounding_box().size.Z == pytest.approx(12)
    assert any("not printed" in n for n in r["notes"])
    plain = hw.make("extrusion_offset_jig", drill_d=5)
    assert "fitted" not in plain and plain["info"]["drill"] == 5
    with pytest.raises(ValueError, match="at least"):
        hw.make("extrusion_offset_jig", drill_d="1/4", bushing_od="5/16")
    cat = {f["name"]: f["type"] for f in hw.catalog()["kinds"]["extrusion_freehand_jig"]["fields"]}
    assert cat["drill_d"] == "size" and cat["bushing_od"] == "size" and cat["corner_radius"] == "len" and cat["engrave"] == "bool"


def test_jig_says_its_drill_size_and_rounds_its_corners():
    for kind in ("extrusion_offset_jig", "extrusion_freehand_jig"):
        marked = hw.make(kind, drill_d="1/4")
        bare = hw.make(kind, drill_d="1/4", engrave=False)
        assert marked["shape"].is_valid and 0.5 < bare["shape"].volume - marked["shape"].volume < 40
        assert any('(1/4")' in n for n in marked["notes"])
        soft = hw.make(kind, drill_d="1/4", engrave=False, corner_radius=4)
        assert soft["shape"].is_valid and soft["shape"].volume < bare["shape"].volume and soft["size"] == bare["size"]
        with pytest.raises(ValueError):
            hw.make(kind, corner_radius=6)           # more than the wall
    g = hw.make("drill_guide", sizes="1/8, 3/16, 13/64, 1/4, 5", corner_radius=3)
    assert g["shape"].is_valid and len(g["shape"].solids()) == 1 and '13/64"' in g["notes"][0]
    assert hw.make("drill_guide", engrave=False)["size"][:2] == [69.0, 26.0]
    s = hw.make("shelf_pin_jig", hole_d="1/4", corner_radius=3)
    assert s["shape"].is_valid and "1/4 in (6.35 mm) drill" in s["notes"][0]


def test_bed_edge_chamfer_on_any_part():
    for kind, extra in (("flat_plate", {}), ("shim", {}), ("drill_guide", {}), ("extrusion_offset_jig", {}), ("setup_blocks", {}),
                        ("thumbscrew", {}), ("gridfinity_baseplate", {}), ("nut", {"mode": "print"})):
        a, b = hw.make(kind, **extra), hw.make(kind, bottom_chamfer=0.4, **extra)
        assert b["shape"].is_valid and len(b["shape"].solids()) == len(a["shape"].solids()), kind
        assert 0 < a["shape"].volume - b["shape"].volume < a["shape"].volume * 0.1, kind
        assert b["size"] == a["size"] and any("elephant" in n for n in b["notes"]), kind
    # The edge is cut back 0.4 mm at the bed and not at all 0.4 mm up.
    from build123d import Box, Pos
    plate = hw.make("flat_plate", bottom_chamfer=0.4)["shape"]
    bb = plate.bounding_box()
    probe = Pos(bb.min.X + 0.1, 0, bb.min.Z + 0.1) * Box(0.1, 1, 0.1)
    cut = plate & probe
    assert cut is None or cut.volume < 1e-6
    assert hw.make("screw", bottom_chamfer=0.4)["shape"].volume == pytest.approx(hw.make("screw")["shape"].volume)   # a bought part
    for bad in (4, -1, "x"):
        with pytest.raises(ValueError):
            hw.make("flat_plate", bottom_chamfer=bad)
    assert all(k["fields"][-1]["name"] == "bottom_chamfer" or any(f["name"] == "bottom_chamfer" for f in k["fields"])
               for k in hw.catalog()["kinds"].values())


def test_letters_from_a_font_files_own_outlines():
    import matplotlib
    from pathlib import Path
    from enclosure import fonts
    ttf = str(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans-Bold.ttf")
    faces, width = fonts.outline_faces("PRB 8", 10, ttf)
    assert len(faces) == 4 and all(f.is_valid for f in faces) and 25 < width < 40
    assert sorted(len(f.wires()) for f in faces) == [2, 2, 3, 3]            # P and R have one counter, B and 8 two
    assert fonts.outline_faces(" ", 10, ttf) == ([], 0.0)
    # A stroke that crosses itself is one piece, not a hole where it overlaps.
    import pyclipper
    pc = pyclipper.Pyclipper()
    pc.AddPaths([[(0, 0), (10, 0), (10, 4), (0, 4)], [(3, -3), (7, -3), (7, 7), (3, 7)]], pyclipper.PT_SUBJECT, True)
    assert len(pc.Execute(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)) == 1
