"""v2.8: cut a test piece out of anything on screen."""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from enclosure import web

I = 25.4


def _cut(client, **body):
    r = client.post("/api/cut", json=body)
    if r.status_code != 200:
        return r.status_code, r.text
    z = zipfile.ZipFile(io.BytesIO(r.content))
    return sorted(z.namelist()), z.read("notes.txt").decode(), z.read("test_piece.stl")


def _stl_size(data: bytes):
    import struct
    n = struct.unpack("<I", data[80:84])[0]
    pts = [struct.unpack("<fff", data[84 + i * 50 + 12 + k * 12: 84 + i * 50 + 24 + k * 12]) for i in range(n) for k in range(3)]
    return [round(max(p[a] for p in pts) - min(p[a] for p in pts), 1) for a in range(3)] + [round(min(p[2] for p in pts), 2)]


def test_cut_a_piece_of_a_part_a_box_a_case_and_a_round_box():
    c = TestClient(web.app)
    names, notes, stl = _cut(c, api="part", request={"kind": "flat_plate", "params": {}}, region=[-10, -10, 0, 10, 10, 3])
    assert names == ["notes.txt", "test_piece.step", "test_piece.stl"] and "20.0 x 20.0 x 3.0 mm" in notes
    assert _stl_size(stl) == [20.0, 20.0, 3.0, 0.0]                                      # set down on the bed
    _, notes, stl = _cut(c, api="box", request={"size": [80, 60, 30]}, target="base", region=[20, 10, 0, 60, 50, 12])
    assert "cut from the base" in notes and _stl_size(stl)[2] == 12.0
    # The corner of a hinged case's lid, turned over as a lid prints.
    _, notes, stl = _cut(c, api="case", request={"case": {}}, target="lid", region=[40, 20, 0, 100, 80, 60])
    assert "cut from the lid" in notes and "turned over" in notes and _stl_size(stl)[3] == 0.0
    _, notes, _ = _cut(c, api="round", request={"round": {}}, target="base", region=[-60, -60, 0, 60, 60, 8])
    assert "8.0 mm, cut from the base" in notes
    # Just the block of holes of a sectioned case, the top of it.
    secs = [{"kind": "holes", "name": "tips", "ds": [8, 10], "depth": 15, "slot_l": 30, "slot_w": 8}, {"kind": "cells", "count": 4, "x": I, "y": I}]
    from enclosure import case
    m = case.build(case.Case(sections=secs))
    L, W = m["inner"][0], m["inner"][1]
    _, notes, stl = _cut(c, api="case", request={"case": {"sections": secs}}, target="base", region=[-L / 2, -W / 2, 10, -L / 2 + 20, W / 2, 40])
    assert _stl_size(stl)[0] == 20.0 and 15 < _stl_size(stl)[2] < 20


def test_cut_says_what_is_wrong():
    c = TestClient(web.app)
    part = {"kind": "flat_plate", "params": {}}
    for body, word in ((dict(api="part", request=part, region=[500, 500, 0, 510, 510, 3]), "nothing of the part inside"),
                       (dict(api="part", request=part, region=[0, 0, 0, 0.2, 10, 3]), "under 1 mm"),
                       (dict(api="part", request=part, region=[0, 0, 0]), "six numbers"),
                       (dict(api="outline", request={}, region=[0, 0, 0, 5, 5, 5]), "can be cut from"),
                       (dict(api="part", request=part, target="handle", region=[0, 0, 0, 5, 5, 5]), "base or the lid"),
                       (dict(api="part", request={"kind": "nope"}, region=[0, 0, 0, 5, 5, 5]), "")):
        code, text = _cut(c, **body)[:2]
        assert code >= 400 and word in text
    page = (web.STATIC / "index.html").read_text() if hasattr(web, "STATIC") else open("enclosure/static/index.html").read()
    assert 'id="cutopen"' in page and "api/cut" in page
