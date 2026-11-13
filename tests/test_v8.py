"""v0.8: the hinged lid, fan and power presets, stacked boards, connectors placed on openings,
the SolidWorks macro, costing, the summary PDF, and installing the site as an app."""

import pytest
from build123d import Axis

from enclosure import box, costing, fit, frompcb, kicad, samples, shell, solidworks, summary


def test_hinge_lid_opens_without_hitting_the_base():
    s = box.BoxSpec(size=[100, 60, 40], lid="hinge")
    m = box.build(s)
    base, lid = m["base"], m["lid"]
    assert len(base.solids()) == 1 and len(lid.solids()) == 1
    assert (base & lid).volume < 1e-6
    ay, az, _ = box.hinge_axis(s)
    ax = Axis((0, ay, az), (1, 0, 0))
    # Past the snap rib's first few degrees, nothing touches all the way over.
    for deg in (6, 15, 45, 90, 135, 180):
        assert (base & lid.rotate(ax, -deg)).volume < 1e-6, deg
    # The pin hole is not read as an opening in the walls.
    enc, _ = shell.read(base, lid)
    assert not [o for o in enc.openings if o.wall in ("-X", "+X")]


def test_fan_presets_bring_their_screw_holes_once():
    s = box.BoxSpec(size=[100, 90, 60], cutouts=[{"face": "-X", "preset": "fan-40", "at": [0, 30]}])
    s.check()
    s.check()
    holes = [c for c in s.cutouts if c.get("source") == "fan-40 screw hole"]
    assert len(holes) == 4 and {tuple(c["at"]) for c in holes} == {(-16, 14), (-16, 46), (16, 14), (16, 46)}
    m = box.build(s)
    assert any("fan-40" in n for n in m["notes"])


def test_iec_inlet_wants_a_thin_panel():
    m = box.build(box.BoxSpec(size=[100, 60, 40], wall=4, cutouts=[{"face": "+X", "preset": "iec-c14", "at": [0, 15]}]))
    assert any("iec-c14" in c for c in m["checks"])


@pytest.fixture(scope="module")
def kb(tmp_path_factory):
    return samples.kicad_board(tmp_path_factory.mktemp("kb8"))


def test_stacked_board_fits_with_openings_for_both(kb):
    main, _ = kicad.board_solids(kb["pcb"])
    top, _ = kicad.board_solids(kb["pcb"])
    solids, notes = frompcb.stack(main, top, 11.0)
    assert "PCB2" in [s.name for s in solids] and "J1/top" in [s.name for s in solids]
    r = frompcb.make(solids, frompcb.Settings(lid="hinge"))
    assert r["fit"].to_json()["fits"]
    assert len(r["spec"].cutouts) == 4  # two connectors on each board
    assert kicad.moves_from_fit([{"subject": "J1/top", "kicad_move": [1, 0]}]) == {}


def test_connector_moved_onto_an_empty_opening(kb, tmp_path):
    main, _ = kicad.board_solids(kb["pcb"])
    spec = frompcb.make(main, frompcb.Settings())["spec"]
    a, b = spec.cutouts[0]["at"]
    spec.cutouts[0]["at"] = [a + 15, b]
    m = box.build(spec)
    enc, _ = shell.read(m["base"], m["lid"])
    j = fit.check(enc, m["base"], m["lid"], main).to_json()
    f = next(f for f in j["findings"] if f["code"] == "connector_no_opening")
    assert "onto the opening" in f["fix"]
    moves = kicad.moves_from_fit(j["findings"])
    done = kicad.move_footprints(kb["pcb"], moves, tmp_path / "fixed.kicad_pcb")
    assert done and done[0]["moved"]


def test_solidworks_macro():
    text, skipped = solidworks.macro(box.BoxSpec(size=[100, 60, 40], standoffs=[[-30, -15], [30, 15]],
                                                 cutouts=[{"face": "-X", "preset": "usb-c", "at": [0, 8]}]))
    assert text.startswith("'") or "Sub main" in text
    for call in ("FeatureExtrusion2", "FeatureCut4", "InsertFeatureShell"):
        assert call in text
    assert "Dim Step " not in text  # a reserved word in VBA
    _, skipped = solidworks.macro(box.BoxSpec(size=[100, 60, 40], lid="hinge"))
    assert any("hinge" in s for s in skipped)


def test_costing_with_a_stand_in_for_digikey():
    class Fake:
        def search(self, kw, limit=8):
            return [{"mpn": "X1", "manufacturer": "Acme", "description": kw, "price": 0.10, "stock": 100, "url": "u"}]
    bom = [{"item": "M3x8 screw", "qty": 4, "make": "buy"}, {"item": "base", "qty": 1, "make": "make"}]
    c = costing.price(bom, {"grams": 40.0}, 20.0, Fake())
    assert c["plastic"] == pytest.approx(0.8)
    assert c["total"] == pytest.approx(0.8 + 0.4)


def test_summary_pdf():
    s = box.BoxSpec(size=[80, 50, 30])
    pdf = summary.make(s, box.build(s), None, None, "Test", "in")
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000


def test_app_files_and_summary_endpoint():
    from fastapi.testclient import TestClient
    from enclosure.web import app
    c = TestClient(app)
    m = c.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.json()["display"] == "standalone"
    assert c.get("/sw.js").status_code == 200 and c.get("/icon-512.png").content[:4] == b"\x89PNG"
    assert c.get("/nope.txt").status_code == 404
    r = c.post("/api/summary", json={"size": [80, 50, 30], "units": "in"})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
