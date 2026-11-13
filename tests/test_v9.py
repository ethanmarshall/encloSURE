"""v0.9: parametric hardware (screws, nuts, washers, spacers, springs, clips), reference and printed."""

import io
import json
import zipfile

import pytest
from build123d import Axis, Pos

from enclosure import hardware as hw


def test_thread_sizes():
    assert hw.thread_size("M3") == ("M3-0.5", 3.0, 0.5, "metric")
    assert hw.thread_size("M8x1") == ("M8-1", 8.0, 1.0, "metric")
    name, d, p, sys_ = hw.thread_size("#4-40")
    assert sys_ == "inch" and d == pytest.approx(0.112 * 25.4) and p == pytest.approx(25.4 / 40)
    assert hw.thread_size("1/4-20")[1] == pytest.approx(6.35)
    with pytest.raises(ValueError):
        hw.thread_size("bolt")


def test_reference_parts_are_standard_sizes():
    nut = hw.make("nut", size="M3")
    assert nut["size"][1] == pytest.approx(5.5) and nut["size"][2] == pytest.approx(2.4)  # ISO 4032 M3: 5.5 AF, 2.4 thick
    inch = hw.make("nut", size="1/4-20")
    assert inch["size"][1] == pytest.approx(7 / 16 * 25.4, abs=0.01)  # ASME B18.2.2: 7/16 across flats
    screw = hw.make("screw", size="M4", length=12)
    assert screw["size"][2] == pytest.approx(12 + 4, abs=0.01)  # ISO 4762 M4 head is 4 mm tall
    assert screw["buy"].startswith("M4-0.7 x 12")
    w = hw.make("washer", size="M3")
    assert w["info"]["id"] == pytest.approx(3.2) and w["info"]["od"] == pytest.approx(7.0)


@pytest.mark.parametrize("kind", list(hw.KINDS))
def test_every_part_builds_as_one_valid_solid(kind):
    r = hw.make(kind)
    shape = r["shape"]
    assert shape.is_valid and shape.volume > 0
    if not (kind in ("screw", "nut") and r.get("info", {}).get("standard")):
        assert len(shape.solids()) == 1, kind


def test_printed_bolt_turns_into_printed_nut():
    b = hw.make("screw", size="M8", length=16, mode="print")["shape"]
    n = hw.make("nut", size="M8", mode="print")["shape"]
    # At the right turn of the nut the threads mesh with no overlap; at the wrong one they clash.
    vols = [(b & (Pos(0, 0, -10) * n.rotate(Axis.Z, a))).volume for a in range(0, 360, 20)]
    assert min(vols) < 1e-3 and max(vols) > 0.5


def test_small_printed_threads_are_flagged():
    assert any("under M6" in c for c in hw.make("nut", size="M3", mode="print")["checks"])


def test_compression_spring_numbers():
    r = hw.make("compression_spring", d=1.0, od=10.0, free_length=20.0, coils=8, working_length=14)
    i = r["info"]
    # Shigley: k = G d^4 / (8 D^3 Na) with music wire G = 81.7 GPa, D = 9, Na = 6.
    assert i["rate_n_per_mm"] == pytest.approx(81_700 / (8 * 729 * 6), rel=1e-3)
    assert i["solid_height"] == pytest.approx(8.0)
    assert i["force_at_working_n"] == pytest.approx(i["rate_n_per_mm"] * 6, rel=1e-2)
    assert r["size"][2] == pytest.approx(20.0, abs=0.01)
    with pytest.raises(ValueError):
        hw.make("compression_spring", free_length=8.5, coils=8)


def test_snap_hook_strain_and_limit():
    r = hw.make("snap_hook", length=12, thickness=1.6, undercut=1.0)
    assert r["info"]["strain_pct"] == pytest.approx(1.5 * 1.6 * 1.0 / 144 * 100, rel=1e-3)
    short = hw.make("snap_hook", length=6, thickness=2.0, undercut=1.0, material="PLA")
    assert any("over the" in c for c in short["checks"])


def test_unknown_setting_is_an_error():
    with pytest.raises(ValueError):
        hw.make("screw", lenght=10)
    # Mode and material are quietly dropped for parts that don't use them.
    assert hw.make("cable_clip", mode="print")["shape"].is_valid


def test_part_endpoints():
    from fastapi.testclient import TestClient
    from enclosure.web import app
    c = TestClient(app)
    cat = c.get("/api/parts").json()
    assert "compression_spring" in cat["kinds"] and cat["kinds"]["snap_hook"]["printed_only"]
    r = c.post("/api/part", json={"kind": "washer", "params": {"size": "M4"}, "page": "t", "seq": 1})
    assert r.status_code == 200 and r.json()["mesh"]
    # A request overtaken by a newer one from the same page is skipped.
    c.post("/api/part", json={"kind": "washer", "params": {"size": "M4"}, "page": "t2", "seq": 5})
    assert c.post("/api/part", json={"kind": "washer", "params": {}, "page": "t2", "seq": 4}).json() == {"stale": True}
    bad = c.post("/api/part", json={"kind": "washer", "params": {"size": "M99"}})
    assert bad.status_code == 400
    z = c.post("/api/part/download", json={"kind": "tie_mount", "params": {}})
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert sorted(names) == ["notes.md", "tie_mount.step", "tie_mount.stl"]


def test_cli_part(tmp_path, capsys):
    from enclosure import cli
    assert cli.main(["part", "spacer", "size=M3", "length=8", "bore=insert", "-o", str(tmp_path / "s")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and (tmp_path / "s" / "spacer.step").exists()
