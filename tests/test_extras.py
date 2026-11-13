"""Presets, the box's extra options, the Onshape feature, bought boxes and the web page."""

import io
import json
import zipfile

import pytest
from build123d import Compound, Cylinder, Pos, RectangleRounded, Align, export_step, extrude

from enclosure import box, geom, onshape, presets, stock
from enclosure.cli import main


def test_presets_resolve_and_parse():
    c = box.Cutout.parse("back:pg9@20,20")
    assert c.face == "+Y" and c.preset == "pg9"
    r = presets.resolve({"face": "+Y", "preset": "pg9", "at": [20, 20]})
    assert r["shape"] == "round" and r["size"] == [15.4] and "VIOX" in r["source"]
    with pytest.raises(ValueError):
        presets.resolve({"face": "+Y", "preset": "pg99", "at": [0, 0]})
    assert all(src for *_, src in presets.PRESETS.values()), "every preset says where its size is from"


def full_spec(**kw):
    base = dict(size=[140, 90, 55], lid="screw", standoffs=box.standoff_pattern("rect:100x60"), gasket=2.0,
                cutouts=[{"face": "-X", "preset": "usb-c", "at": [0, 10]}, {"face": "+Y", "preset": "pg9", "at": [30, 25]},
                         {"face": "-Y", "preset": "m12", "at": [-30, 25]}, {"face": "floor", "preset": "drain", "at": [55, 30]}],
                vents=[box.parse_vent("right:30x20@0,25")], feet=10, keyholes="M4", din_rail=True,
                labels=[box.parse_label("lid:POWER@0,-20"), box.parse_label("front:IN@30,40:6")])
    base.update(kw)
    return box.BoxSpec(**base)


def test_every_option_together_builds_clean():
    made = box.build(full_spec())
    base, lid = made["base"], made["lid"]
    assert len(base.solids()) == 1 and base.is_valid
    assert len(lid.solids()) == 1 and lid.is_valid
    assert geom.overlap_volume(base, lid) < 1e-3
    assert any("gasket" in n for n in made["notes"])


@pytest.mark.parametrize("bad", [
    dict(gasket=2.0, lid="friction"),  # a gasket needs a screw lid
    dict(gasket=9.0),
    dict(feet=10, feet_depth=5),  # deeper than the floor
    dict(din_rail=True, size=[20, 20, 20], standoffs=[], cutouts=[], vents=[], labels=[], keyholes=None, feet=0),
])
def test_bad_extras_are_refused(bad):
    with pytest.raises(ValueError):
        full_spec(**bad).check()


def test_print_options_change_the_part():
    plain = box.BoxSpec(size=[60, 40, 30], lid="none", teardrop=False, bottom_chamfer=0, standoff_ribs=False,
                        standoffs=box.standoff_pattern("rect:40x20"), cutouts=[{"face": "-Y", "shape": "round", "size": [8.0], "at": [0, 10]}])
    tuned = box.BoxSpec(**{**box.asdict(plain), "teardrop": True, "bottom_chamfer": 0.6, "standoff_ribs": True})
    a, b = box.build(plain)["base"], box.build(tuned)["base"]
    assert a.volume != pytest.approx(b.volume, abs=1.0)


def test_onshape_feature_text():
    spec = full_spec(gasket=0, vents=[], feet=0, keyholes=None, din_rail=False, labels=[])
    text, skipped = onshape.feature_studio(spec)
    assert text.startswith(f"FeatureScript {onshape.VERSION};")
    assert "defineFeature" in text and '"EncloSURE Box"' in text
    # Keys are quoted: `length` and `floor` are std functions and break a bare map key.
    assert '"length" : 140 * millimeter' in text and '"floor" : 2 * millimeter' in text
    assert '"face" : EncFace.BACK' in text and "15.4 * millimeter" in text
    assert "standoff gussets" in skipped and "gasket" not in skipped
    assert text.count("{") == text.count("}") and text.count("(") == text.count(")")
    _, skipped = onshape.feature_studio(full_spec())
    assert {"gasket", "vents", "feet", "keyholes", "DIN clip", "labels"} <= set(skipped)


def test_formats(tmp_path):
    spec = box.BoxSpec(size=[60, 40, 30])
    only = box.write(spec, tmp_path / "o", formats=("onshape",))
    assert set(only["files"]) == {"onshape", "settings"}
    both = box.write(spec, tmp_path / "b", stl=False, formats=("step", "onshape"))
    assert {"base", "lid", "assembly", "onshape"} <= set(both["files"])
    assert main(["box", "--size", "60x40x30", "--format", "both", "--no-stl", "--gasket", "1.5",
                 "--vent", "left:20x10@0,10", "--label", "lid:HI@0,0", "--feet", "8", "-o", str(tmp_path / "c")]) == 0
    assert (tmp_path / "c" / "enclosure_box.fs").exists()


@pytest.fixture(scope="module")
def die_cast(tmp_path_factory):
    """A stand-in for a maker's STEP: a drafted die-cast box and its lid in one file, off-origin."""
    L, W, H, t = 112.0, 60.0, 31.0, 3.0
    body = extrude(RectangleRounded(L, W, 6), H, taper=1)
    body -= Pos(0, 0, t) * extrude(RectangleRounded(L - 2 * t, W - 2 * t, 4), H, taper=-1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            body += Pos(sx * (L / 2 - t - 3), sy * (W / 2 - t - 3), t) * Cylinder(
                3.5, H - t, align=(Align.CENTER, Align.CENTER, Align.MIN))
    lid = Pos(0, 0, H) * extrude(RectangleRounded(L, W, 6), 3)
    path = tmp_path_factory.mktemp("stock") / "fake1590.step"
    export_step(Pos(30, 40, 5) * Compound(children=[body, lid]), str(path))
    return path


def test_stock_box_cutouts_and_templates(die_cast, tmp_path):
    cuts = [{"face": "-Y", "preset": "pg9", "at": [0, 12]}, {"face": "+X", "shape": "round", "size": [6.0], "at": [10, 15]},
            {"face": "lid", "preset": "pushbutton-22", "at": [20, 0]}]
    before_base, before_lid = stock.split(die_cast)
    r = stock.run(die_cast, cuts, tmp_path)
    holes = {h["face"]: h for h in r["holes"]}
    # From the face's bottom-left corner as seen from outside.
    assert (holes["-Y"]["from_left"], holes["-Y"]["from_bottom"]) == (56.0, 15.0)
    assert (holes["+X"]["from_left"], holes["+X"]["from_bottom"]) == (40.0, 18.0)
    assert (holes["lid"]["from_left"], holes["lid"]["from_bottom"]) == (76.0, 30.0)
    base, lid = geom.load(r["files"]["base"]), geom.load(r["files"]["lid"])
    assert base.volume < before_base.volume - 100 and lid.volume < before_lid.volume - 100
    # It stays where the maker put it.
    assert geom.bbox(base)[0][0] == pytest.approx(geom.bbox(before_base)[0][0], abs=1e-3)
    from pypdf import PdfReader
    pages = PdfReader(r["files"]["templates"]).pages
    assert len(pages) == 3 and round(float(pages[0].mediabox.width)) == 612  # Letter, 1:1


def test_stock_refuses_lid_cut_without_lid(die_cast, tmp_path):
    base, _ = stock.split(die_cast)
    with pytest.raises(ValueError):
        stock.cut(base, None, [{"face": "lid", "shape": "round", "size": [5.0], "at": [0, 0]}])


def test_web(die_cast):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from enclosure.web import app
    c = TestClient(app)
    assert "EncloSURE" in c.get("/").text
    assert "pg9" in c.get("/api/presets").json()
    body = {"size": [80, 50, 30], "lid": "screw", "standoffs": "rect:60x30", "cutouts": "left:usb-c@0,8", "format": "both"}
    p = c.post("/api/preview", json=body).json()
    assert p["outer"] == [84.0, 54.0, 34.0] and p["base"] and p["lid"]
    assert any("Onshape" in x for x in p["checks"])
    z = zipfile.ZipFile(io.BytesIO(c.post("/api/box", json={**body, "stl": False}).content))
    assert {"base.step", "lid.step", "enclosure_box.fs", "box.json", "checks.json"} <= set(z.namelist())
    bad = c.post("/api/preview", json={**body, "cutouts": "left:nope@0,0"})
    assert bad.status_code == 400 and "nope" in bad.json()["error"]
    assert c.post("/api/preview", json={**body, "size": [5000, 50, 30]}).status_code == 400
    with open(die_cast, "rb") as f:
        res = c.post("/api/stock", files={"step": ("fake1590.step", f, "application/step")},
                     data={"cutouts": "front:pg9@0,12\nlid:pushbutton-22@0,0"})
    assert res.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(res.content)).namelist()
    assert {"base.step", "lid.step", "drill_templates.pdf", "holes.json"} <= set(names)
