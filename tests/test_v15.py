"""v1.5: the hinged case with snap hinges and latch tabs."""

import pytest

from build123d import Pos, Rot

from enclosure import case


def _overlap(a, b) -> float:
    i = a.intersect(b)
    return 0.0 if i is None else sum(s.volume for s in i.solids())


@pytest.fixture(scope="module")
def made():
    c = case.Case(dividers_x=2, dividers_y=1)
    return c, case.build(c)


def test_parts_are_sound(made):
    c, m = made
    for k in ("base", "lid", "tab"):
        assert m[k].is_valid and len(m[k].solids()) == 1
    assert m["n_tabs"] == 2 and m["n_hinges"] == 3 and len(m["tabs"]) == 2
    assert m["inner"] == [160.0, 100.0, 30.0]
    assert _overlap(m["base"], m["lid"]) < 1e-3
    for t in m["tabs"]:
        assert _overlap(t, m["lid"]) < 1e-3 and _overlap(t, m["base"]) < 0.5   # the catch is set a touch tight


def test_lid_opens_right_over(made):
    c, m = made
    ya, hs = c.size[1] / 2 + c.wall + case.HINGE_E, m["parting"]
    for ang in (5, 45, 90, 135, 180):
        lid = Pos(0, ya, hs) * Rot(-ang, 0, 0) * Pos(0, -ya, -hs) * m["lid"]
        assert _overlap(lid, m["base"]) < 1e-3, ang


def test_tab_swings_clear(made):
    c, m = made
    yp, zp = -(c.size[1] / 2 + c.wall + case.TAB_E), m["top"] - case.TAB_E
    for ang in (45, 90, 150):
        t = Pos(0, yp, zp) * Rot(-ang, 0, 0) * Pos(0, -yp, -zp) * m["tabs"][0]
        assert _overlap(t, m["lid"]) < 1e-3 and _overlap(t, m["base"]) < 1e-3, ang
    # On the way it has to spring past the posts: the catch balls, and nothing more.
    t = Pos(0, yp, zp) * Rot(-12, 0, 0) * Pos(0, -yp, -zp) * m["tabs"][0]
    assert 0.5 < _overlap(t, m["base"]) < 15


def test_sizes_and_errors():
    small = case.build(case.Case(size=(60, 40, 24)))
    assert small["n_tabs"] == 1 and small["base"].is_valid
    deep = case.build(case.Case(size=(300, 200, 60), lid_depth=20))
    assert deep["n_tabs"] == 3 and deep["lid"].is_valid
    with pytest.raises(ValueError, match="too shallow for the latch tab"):
        case.build(case.Case(size=(160, 100, 18)))
    with pytest.raises(ValueError, match="hinges don't fit"):
        case.build(case.Case(size=(45, 30, 26), hinges=2))
    with pytest.raises(ValueError):
        case.build(case.Case(wall=1.6))


def test_through_the_web(tmp_path):
    import io, zipfile
    from fastapi.testclient import TestClient
    from enclosure.web import app
    c = TestClient(app)
    r = c.post("/api/case", json={"case": {"size": [120, 80, 28], "dividers_x": 1}, "preview": True})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["base"] and j["lid"] and len(j["mounted"]) == 2 and j["checks"]
    r = c.post("/api/case", json={"case": {"size": [120, 80, 28]}})
    assert r.status_code == 200
    names = set(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
    assert {"case_tray.stl", "case_lid.stl", "case_latch_tab.stl", "case_assembly.step", "notes.md"} <= {n.split("/")[-1] for n in names}
    assert c.post("/api/case", json={"case": {"size": [160, 100, 18]}, "preview": True}).status_code == 400
