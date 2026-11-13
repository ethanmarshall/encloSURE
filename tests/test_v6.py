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
    d = TestClient(app).post("/api/describe", data={"text": "Raspberry Pi, usb-c, wall mount"}).json()
    assert d["spec"]["keyholes"] == "M4" and d["kicad_pcb"].startswith("(kicad_pcb")
    assert main(["describe", "60x40", "board,", "USB-C", "--no-stl", "-o", str(tmp_path / "d")]) == 0
    assert (tmp_path / "d" / "board.kicad_pcb").exists() and box.load(tmp_path / "d" / "box.json")


def test_onshape_push_calls(monkeypatch):
    """The calls the Onshape push and update make, against a stand-in for Onshape's API."""
    import urllib.request
    from enclosure import onshape_push
    calls = []
    feats = []

    class R:
        def __init__(self, body):
            self.body = body
        def read(self):
            return json.dumps(self.body).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake(req, timeout=60):
        path, body = req.full_url.replace(onshape_push.BASE, ""), json.loads(req.data) if req.data else None
        m = req.get_method()
        calls.append((m, path, body))
        auth = req.headers["Authorization"]
        assert auth.startswith("On k:HmacSHA256:") and len(req.headers["On-nonce"]) == 25 and req.headers["Date"].endswith("GMT")
        # The signature is HMAC-SHA256 of the documented string, keyed with the secret.
        import base64, hashlib, hmac
        text = (f"{m}\n{req.headers['On-nonce']}\n{req.headers['Date']}\napplication/json\n"
                f"{path}\n\n").lower()
        assert auth.split(":")[2] == base64.b64encode(hmac.new(b"s", text.encode(), hashlib.sha256).digest()).decode()
        if path == "/api/documents":
            return R({"id": "D1", "defaultWorkspace": {"id": "W1"}})
        if m == "POST" and path == "/api/featurestudios/d/D1/w/W1":
            return R({"id": "E1"})
        if path == "/api/documents/d/D1/w/W1/elements":
            return R([{"id": "E1", "elementType": "FEATURESTUDIO", "microversionId": "M2"},
                      {"id": "P1", "elementType": "PARTSTUDIO", "microversionId": "M3"}])
        if "/partstudios/" in path and path.endswith("/features") and m == "GET":
            return R({"features": feats})
        if "/partstudios/" in path and m == "POST":
            fid = body["feature"].get("featureId", "F1")
            feats[:] = [{"featureType": "enclosureBox", "featureId": fid}]
            return R({"feature": {"featureId": fid}, "featureState": {"featureStatus": "OK"}})
        if m == "GET":
            return R({"sourceMicroversion": "MV", "serializationVersion": "1.2.3"})
        return R({})

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.delenv("ONSHAPE_ACCESS_KEY", raising=False)
    with pytest.raises(RuntimeError):
        onshape_push.push("x")
    monkeypatch.setenv("ONSHAPE_ACCESS_KEY", "k")
    monkeypatch.setenv("ONSHAPE_SECRET_KEY", "s")
    out = onshape_push.push("FeatureScript 3112;", "Box")
    assert out["feature_studio"].endswith("/documents/D1/w/W1/e/E1")
    assert out["document"].endswith("/documents/D1/w/W1/e/P1")
    assert out["ids"] == {"did": "D1", "wid": "W1", "studio": "E1", "partstudio": "P1", "feature": "F1"}
    assert ("POST", "/api/featurestudios/d/D1/w/W1/e/E1", {"contents": "FeatureScript 3112;", "serializationVersion": "1.2.3",
            "sourceMicroversion": "MV", "rejectMicroversionSkew": False}) in calls
    insert = [c for c in calls if c[1] == "/api/v9/partstudios/d/D1/w/W1/e/P1/features"][0]
    assert insert[2]["feature"]["featureType"] == "enclosureBox" and insert[2]["feature"]["namespace"] == "eE1::mM2"
    # Update: the same feature is changed in place, not added again.
    calls.clear()
    up = onshape_push.update(out["ids"], "FeatureScript 3112; // v2")
    assert up["ids"]["feature"] == "F1"
    assert ("POST", "/api/v9/partstudios/d/D1/w/W1/e/P1/features/featureid/F1") in [c[:2] for c in calls]
    with pytest.raises(ValueError):
        onshape_push.update({**out["ids"], "did": "../x"}, "x")
    # Links to a Part Studio.
    assert onshape_push.parse_link("https://cad.onshape.com/documents/" + "a" * 24 + "/w/" + "b" * 24 + "/e/" + "c" * 24) == \
        ("a" * 24, "w", "b" * 24, "c" * 24)
    with pytest.raises(ValueError):
        onshape_push.parse_link("https://example.com/not-onshape")
