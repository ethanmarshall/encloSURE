"""A box from a board, fixing a board from a fit report, the fit coupon, pins, card guides and
windows, the Onshape extras, drawings, and the page's password."""

import json
import shutil
import subprocess

import pytest

from enclosure import box, coupon, fit, frompcb, geom, kicad, onshape, samples, shell
from enclosure.cli import main

KICAD = shutil.which("kicad-cli") is not None


@pytest.fixture(scope="module")
def kboard(tmp_path_factory):
    if not KICAD:
        pytest.skip("KiCad is not installed")
    return samples.kicad_board(tmp_path_factory.mktemp("kboard"))


def _export(pcb, step):
    subprocess.run(["kicad-cli", "pcb", "export", "step", "--subst-models", "-f", "-o", str(step), str(pcb)],
                   check=True, capture_output=True)


def test_box_from_board_fits(kboard):
    r = frompcb.make(kboard["step"], frompcb.Settings(lid="friction"))
    spec, j = r["spec"], r["fit"].to_json()
    assert j["fits"] and j["warnings"] == 0, j["findings"]
    assert j["placement"]["how"] == "4 of 4 mounting holes on standoffs"
    assert spec.standoff_screw == "M3" and len(spec.standoffs) == 4
    faces = sorted(c["face"] for c in spec.cutouts)
    assert faces == ["+X", "-X"]  # USB-C and the terminal block; C1 and SW1 are inside
    # The board's tallest part (C1, 11.5 mm) plus headroom and the lip fit under the lid.
    assert spec.size[2] >= 5 + 1.6 + 11.5 + 2


def test_box_from_board_screw_lid_clears_posts(kboard):
    r = frompcb.make(kboard["step"], frompcb.Settings(lid="screw"))
    assert r["fit"].to_json()["fits"]
    assert any("corner posts" in n for n in r["notes"])


def test_fix_moves_footprints_and_the_board_then_fits(kboard, tmp_path):
    made = frompcb.make(kboard["step"], frompcb.Settings(lid="friction"))["made"]
    enc, _ = shell.read(made["base"], made["lid"])
    text = open(kboard["pcb"]).read().replace("(at 103.0 125.0 0)", "(at 103.0 126.3 0)").replace(
        "(at 176.0 146.0)", "(at 176.6 146.0)")
    bad = tmp_path / "bad.kicad_pcb"
    bad.write_text(text)
    _export(bad, tmp_path / "bad.step")
    j = fit.check(enc, made["base"], made["lid"], geom.step_names(tmp_path / "bad.step")).to_json()
    assert not j["fits"]
    (tmp_path / "report.json").write_text(json.dumps(j))
    assert main(["fix", str(bad), str(tmp_path / "report.json"), "-o", str(tmp_path / "fixed.kicad_pcb")]) == 0
    moved = {m["what"]: m for m in kicad.move_footprints(bad, kicad.moves_from_fit(j["findings"]), tmp_path / "f2.kicad_pcb")}
    assert moved["J1"]["to"] == [103.0, 125.0] and moved["H4"]["to"] == [176.0, 146.0]
    _export(tmp_path / "fixed.kicad_pcb", tmp_path / "fixed.step")
    j = fit.check(enc, made["base"], made["lid"], geom.step_names(tmp_path / "fixed.step")).to_json()
    assert j["fits"] and not j["findings"]


def test_frompcb_cli(kboard, tmp_path):
    assert main(["frompcb", kboard["step"], "--lid", "snap", "--no-stl", "-o", str(tmp_path / "b")]) == 0
    assert box.load(tmp_path / "b" / "box.json").lid == "snap"
    assert (tmp_path / "b" / "fit" / "punch_list.md").exists()


def test_coupon():
    plate, plugs = coupon.build()
    assert plate.is_valid and len(plate.solids()) == 1
    assert plugs.is_valid and len(plugs.solids()) == len(coupon.GAPS)
    # Each plug is its pocket less the gap on every side.
    sizes = sorted(round(s.bounding_box().size.X, 3) for s in plugs.solids())
    assert sizes == sorted(round(coupon.POCKET[0] - 2 * g, 3) for g in coupon.GAPS)
    with pytest.raises(ValueError):
        coupon.build([2.0])


def test_pins_card_guides_and_windows():
    spec = box.BoxSpec(size=[100, 70, 50], lid="screw", lid_thickness=2.5, wall=2.5,
                       standoffs=box.standoff_pattern("rect:60x30"), standoff_hole="pin", card_slots=[0],
                       windows=[{"face": "lid", "size": [40, 25], "at": [0, 0], "panel": [46, 31], "panel_t": 1.0},
                                {"face": "front", "size": [20, 10], "at": [0, 25], "panel": [26, 16], "panel_t": 1.0}])
    made = box.build(spec)
    base, lid = made["base"], made["lid"]
    assert base.is_valid and len(base.solids()) == 1 and lid.is_valid and len(lid.solids()) == 1
    assert geom.overlap_volume(base, lid) < 1e-3
    assert not made["checks"]
    top = spec.floor + 50
    # The lid's recess: 1 mm deep from below, 1.5 mm of lid left over it.
    assert not shell.solid_at(lid, (21.5, 0, top + 0.1), (21.5, 0, top + 0.9))
    assert shell.solid_at(lid, (21.5, 0, top + 1.1), (21.5, 0, top + 2.4))
    # A pin stands above each standoff.
    assert shell.solid_at(base, (30.0 + 1.2, 15.0, spec.floor + 5.3), (30.0 + 1.2, 15.0, spec.floor + 6.5))
    with pytest.raises(ValueError):
        box.BoxSpec(windows=[{"face": "lid", "size": [20, 10], "panel": [24, 14], "panel_t": 1.5}]).check()
    clash = box.build(box.BoxSpec(size=[100, 70, 50], standoffs=box.standoff_pattern("rect:60x30"), card_slots=[30]))
    assert any("card slot" in c for c in clash["checks"])


def test_onshape_extras_only_when_used():
    plain, _ = onshape.feature_studio(box.BoxSpec(bottom_chamfer=0))
    assert '("extra" ~' not in plain
    spec = box.BoxSpec(feet=10, card_slots=[0], vents=[box.parse_vent("right:20x10@0,10")],
                       windows=[{"face": "lid", "size": [20, 10], "at": [0, 0], "panel": [24, 14], "panel_t": 1.0}],
                       cutouts=[{"face": "lid", "shape": "rect", "size": [12, 8], "radius": 2, "at": [-30, 0]}])
    text, skipped = onshape.feature_studio(spec)
    for word in ("Vent on +X", "rubber feet", "Window on lid", "Card guides", "Bottom edge chamfer", '"r" : 2 * millimeter'):
        assert word in text
    assert not {"vents", "feet", "windows", "card guides", "bottom chamfer"} & set(skipped)
    assert text.count("{") == text.count("}") and text.count("(") == text.count(")")


def test_drawings(tmp_path):
    from enclosure import drawing
    try:
        drawing.find_draftwright()
    except RuntimeError:
        pytest.skip("draftwright is not built here")
    box.write(box.BoxSpec(size=[60, 40, 25], cutouts=[{"face": "-X", "shape": "round", "size": [6.0], "at": [0, 8]}]),
              tmp_path / "b", stl=False)
    r = drawing.make(tmp_path / "b", tmp_path / "d", "asme", {"part_number": "ENC-001"})
    assert r["files"]["base"] and r["files"]["lid"]
    assert any(f.endswith(".pdf") for f in r["files"]["base"])


def test_password(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from enclosure.web import app
    c = TestClient(app)
    assert c.get("/api/presets").status_code == 200
    monkeypatch.setenv("ENCLOSURE_PASSWORD", "s3cret")
    assert c.get("/api/presets").status_code == 401
    assert c.get("/api/presets", auth=("x", "wrong")).status_code == 401
    assert c.get("/api/presets", auth=("anyone", "s3cret")).status_code == 200
