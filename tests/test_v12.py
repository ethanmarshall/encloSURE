"""v1.2: artwork from SVG and DXF, label turns and bold, and handles on the lid and walls."""

import io

import pytest

from enclosure import art, box

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60">
  <path d="M10 10 H90 V50 H10 Z M30 20 H70 V40 H30 Z" fill="#000" fill-rule="evenodd"/>
  <circle cx="50" cy="30" r="6" fill="#000"/>
  <path d="M5 55 C 20 40, 40 40, 55 55" stroke="#000" stroke-width="3" fill="none"/></svg>"""


def test_artwork_from_svg_and_dxf():
    body, (w, h) = art.solid(SVG, "svg", 40, 0.6)
    assert body.is_valid and w == 40 and body.bounding_box().size.X == pytest.approx(40.4, abs=0.2)  # the stroke counts
    import ezdxf
    doc = ezdxf.new()
    m = doc.modelspace()
    m.add_lwpolyline([(0, 0), (50, 0), (50, 30), (0, 30)], close=True)
    m.add_circle((25, 15), 8)  # a hole in the rectangle
    buf = io.StringIO()
    doc.write(buf)
    body, _ = art.solid(buf.getvalue(), "dxf", 50, 1.0)
    assert body.volume == pytest.approx((50 * 30 - 3.14159 * 64) * 1.0, rel=0.02)
    with pytest.raises(ValueError):
        art.solid("<svg xmlns='http://www.w3.org/2000/svg'></svg>", "svg", 30, 0.6)


def test_art_labels_and_handles_on_a_box():
    s = box.BoxSpec(size=[140, 90, 50], lid="screw",
                    labels=[{"face": "-Y", "text": "PUMP", "at": [0, 30], "bold": True, "rotate": 10}],
                    art=[{"face": "lid", "data": SVG, "kind": "svg", "width": 40, "at": [20, 10], "depth": 0.6},
                         {"face": "+X", "data": SVG, "kind": "svg", "width": 30, "at": [0, 25], "depth": -0.6}],
                    handles=[{"face": "lid", "type": "bar"}, {"face": "-X", "type": "grip", "at": [0, 30]},
                             {"face": "+Y", "type": "strap", "at": [0, 40]}, {"face": "-Y", "type": "knob", "at": [40, 25]},
                             {"face": "+X", "type": "bar", "length": 60, "at": [0, 10]}])
    m = box.build(s)
    assert m["base"].is_valid and len(m["base"].solids()) == 1 and len(m["lid"].solids()) == 1
    assert [n for n, _ in m["extras"]] == ["handle_1", "handle_4", "handle_5"]
    notes = " ".join(m["notes"])
    for word in ("turned 10", "artwork 1 on lid", "finger grip", "strap loops", "pull knob", "bar handle on +X"):
        assert word in notes
    with pytest.raises(ValueError):
        box.build(box.BoxSpec(size=[100, 60, 40], handles=[{"face": "lid", "type": "grip"}]))
    # The older single lid handle still works.
    old = box.build(box.BoxSpec(size=[100, 60, 40], handle=True))
    assert [n for n, _ in old["extras"]] == ["handle_1"]


def test_label_rotation_from_the_page():
    from fastapi.testclient import TestClient
    from enclosure.web import app
    r = TestClient(app).post("/api/preview", json={"size": [100, 60, 40], "labels": [{"face": "lid", "text": "A", "at": [0, 0], "rotate": 45, "bold": True}],
                                                    "art": [{"face": "lid", "data": SVG, "kind": "svg", "width": 20, "at": [20, 0]}]})
    assert r.status_code == 200 and any("turned 45" in n for n in r.json()["notes"])
