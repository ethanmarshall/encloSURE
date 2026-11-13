"""Describing a box in words, the autofit loop, the exploded assembly, batteries, lid posts, cables,
print checks and estimates, and the web calls for them."""

import io
import json
import shutil
import zipfile

import pytest

from enclosure import box, describe, geom, presets, samples, shell
from enclosure.cli import main

KICAD = shutil.which("kicad-cli") is not None


def _draftwright():
    from enclosure import drawing
    try:
        drawing.find_draftwright()
        return True
    except RuntimeError:
        return False


@pytest.mark.parametrize("text, lid, presets_wanted, extra", [
    ("ESP32 board 60x40, USB-C, two buttons, OLED, wall-mounted, splash-proof", "screw", {"usb-c", "pg9"}, "keyholes"),
    ("Raspberry Pi with ethernet and usb-c power, a fan, on my desk", "screw", {"usb-c", "keystone"}, "vents"),
    ("Arduino Uno, 2 AA batteries, toggle switch, 3 LEDs, 16x2 lcd, snap lid", "snap", {"toggle-1/4"}, "batteries"),
])
def test_describe(text, lid, presets_wanted, extra):
    r = describe.make(text)
    spec = r["spec"]
    assert spec.lid == lid
    assert presets_wanted <= {c.get("preset") for c in spec.cutouts}
    assert getattr(spec, extra)
    made = r["made"]
    assert made["base"].is_valid and len(made["base"].solids()) == 1
    assert r["kicad_pcb"].startswith("(kicad_pcb") and r["limits"]["holes"]
    assert not any("locknut" in c for c in made["checks"])


def test_describe_counts_and_words():
    spec, notes = describe.design("80x50 board, three LEDs and an OLED")
    leds = [c for c in spec.cutouts if c.get("size") == [5.2]]
    assert len(leds) == 3  # "OLED" is not an LED
    assert spec.windows and spec.size[0] >= 80
    assert any("15 mm" in n for n in notes)  # it says what it assumed


@pytest.mark.skipif(not KICAD, reason="KiCad is not installed")
def test_autofit_fixes_a_board(tmp_path):
    from enclosure import autofit, frompcb
    kb = samples.kicad_board(tmp_path / "kb")
    made = frompcb.make(kb["step"], frompcb.Settings(lid="friction"))["made"]
    enc, _ = shell.read(made["base"], made["lid"])
    bad = tmp_path / "bad.kicad_pcb"
    bad.write_text(open(kb["pcb"]).read().replace("(at 103.0 125.0 0)", "(at 103.0 126.3 0)"))
    r = autofit.run(enc, made["base"], made["lid"], bad, tmp_path / "af")
    assert r["fits"] and len(r["rounds"]) == 2
    assert r["rounds"][0]["moved"][0]["what"] == "J1"
    assert "126.3" in bad.read_text()  # the original is left alone


def test_batteries_lid_posts_cables_and_estimate():
    spec = box.BoxSpec(size=[120, 80, 45], lid="screw", standoffs=box.standoff_pattern("rect:40x30"),
                       lid_standoffs=[[-20, -15], [20, -15], [-20, 15], [20, 15]],
                       batteries=[{"cell": "AA", "count": 2, "axis": "x", "at": [20, -20]}],
                       tie_points=[[-45, 25]], cable_notches=[{"face": "left", "at": 0, "d": 6}], material="PLA")
    made = box.build(spec)
    base, lid = made["base"], made["lid"]
    assert base.is_valid and len(base.solids()) == 1 and lid.is_valid and len(lid.solids()) == 1
    assert geom.overlap_volume(base, lid) < 1e-3
    top = spec.floor + 45
    assert not shell.solid_at(base, (-61, 0, top - 1), (-61, 0, top - 0.2))  # the notch is open
    assert shell.solid_at(lid, (21.8, 15, top - 3.5), (21.8, 15, top - 0.5))  # a post hangs from the lid
    e = made["estimate"]
    assert e["material"] == "PLA" and 50 < e["grams"] < 300 and e["hours"] > 0
    with pytest.raises(ValueError):
        box.BoxSpec(batteries=[{"cell": "C", "count": 1}]).check()
    with pytest.raises(ValueError):
        box.build(box.BoxSpec(size=[60, 40, 30], batteries=[{"cell": "18650", "count": 2, "at": [0, 0]}]))


def test_print_checks():
    made = box.build(box.BoxSpec(size=[80, 50, 30], wall=1.0, teardrop=False,
                                 cutouts=[{"face": "-Y", "shape": "rect", "size": [25, 10], "at": [0, 12]},
                                          {"face": "+Y", "shape": "round", "size": [12.0], "at": [0, 12]}]))
    text = " ".join(made["checks"])
    assert "wall 1 mm" in text and "-Y 25 mm" in text and "+Y Ø12 hole" in text


def test_new_presets_have_sources():
    for name in ("sma-bulkhead", "bnc-bulkhead", "dc-barrel-snap"):
        shape, size, _, source = presets.PRESETS[name]
        assert shape == "round" and size[0] > 5 and "(" in source


@pytest.mark.skipif(not _draftwright(), reason="draftwright is not built here")
def test_assembly_and_drawing_endpoints(tmp_path):
    from fastapi.testclient import TestClient
    from enclosure import assembly
    from enclosure.web import app
    spec = box.BoxSpec(size=[80, 50, 30], lid="screw", standoffs=box.standoff_pattern("rect:60x30"), feet=10,
                       cutouts=[{"face": "+Y", "preset": "pg9", "at": [0, 12]}])
    r = assembly.make(spec, tmp_path / "a")
    assert r["files"].get("drawing") and not r["notes"]
    items = {row["item"]: row for row in r["parts_list"]}
    assert items["M3x8 screw"]["qty"] == 8 and items["Rubber foot Ø10 mm"]["qty"] == 4 and "pg9" in items
    c = TestClient(app)
    assert c.get("/api/health").json()["draftwright"] is True
    body = {"size": [80, 50, 30], "standoffs": "rect:60x30", "standard": "iso", "title": {"part_number": "T-1"}}
    z = zipfile.ZipFile(io.BytesIO(c.post("/api/drawing", json=body).content))
    assert {"base.pdf", "lid.pdf"} <= set(z.namelist())
    z = zipfile.ZipFile(io.BytesIO(c.post("/api/assembly", json=body).content))
    assert {"assembly_drawing.pdf", "parts_list.csv", "exploded.step"} <= set(z.namelist())


def test_describe_endpoint_and_cli(tmp_path):
    from fastapi.testclient import TestClient
    from enclosure.web import app
    d = TestClient(app).post("/api/describe", json={"text": "Raspberry Pi, usb-c, wall mount"}).json()
    assert d["spec"]["keyholes"] == "M4" and d["kicad_pcb"].startswith("(kicad_pcb")
    assert main(["describe", "60x40", "board,", "USB-C", "--no-stl", "-o", str(tmp_path / "d")]) == 0
    assert (tmp_path / "d" / "board.kicad_pcb").exists() and box.load(tmp_path / "d" / "box.json")
