"""EncloSURE on its sample: the enclosure is read right, the board's four planted misfits are
found with the right moves, the KiCad limits board fits, and the report files are written."""

import json
import shutil
import subprocess

import pytest

from enclosure import fit, geom, report, samples, shell


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    folder = tmp_path_factory.mktemp("sample")
    paths = samples.write(folder)
    base, lid = geom.load(paths["base"]), geom.load(paths["lid"])
    enc, _ = shell.read(base, lid)
    return folder, paths, base, lid, enc


def test_reads_cavity_standoffs_and_openings(sample):
    _, _, _, _, enc = sample
    assert enc.cavity_bounds == ((-48.0, -28.0, 2.0), (48.0, 28.0, 30.0))
    assert enc.floor == 2.0 and enc.ceiling == 30.0
    assert sorted((b.center[0], b.center[1]) for b in enc.bosses) == sorted(samples.BOSS_XY)
    assert all(b.hole == 2.5 and b.top == 7.0 for b in enc.bosses)
    walls = {o.wall: o for o in enc.openings}
    assert set(walls) == {"-X", "lid"}
    usb = walls["-X"]
    assert (usb.width, usb.height, usb.wall_thickness) == (9.5, 3.8, 2.0)
    assert usb.center[1] == 0.0


def test_board_misfits_are_found(sample):
    _, paths, base, lid, enc = sample
    result = fit.check(enc, base, lid, geom.step_names(paths["board"]))
    j = result.to_json()
    assert not j["fits"]
    by = {(f["code"], f["subject"].split(" at ")[0]): f for f in j["findings"]}
    # The board lands on its standoffs from its own frame, three holes exactly.
    assert j["placement"]["translation"] == [-150.0, -100.0, 7.0]
    hole = next(f for f in j["findings"] if f["code"] == "hole_off_standoff")
    assert hole["move"] == [-0.8, 0.0, 0.0]
    j1 = by[("opening_misaligned", "J1")]
    assert j1["move"] == [0.0, -1.5, 0.0] and j1["kicad_move"] == [0.0, 1.5]
    c1 = by[("collision", "C1")]
    assert "2.60 mm above the lid" in c1["message"]
    assert ("collision", "J2") in by and ("connector_no_opening", "J2") in by
    assert ("under_lid_opening", "SW1") in by
    assert j["errors"] == 4


@pytest.mark.skipif(shutil.which("kicad-cli") is None, reason="KiCad is not installed")
def test_limits_board_fits_its_enclosure(sample, tmp_path):
    from enclosure import kicad
    if kicad.pcbnew is None:
        pytest.skip("KiCad's Python module is not available")
    folder, _, base, lid, enc = sample
    written = kicad.limits(enc, tmp_path / "limits.kicad_pcb")
    assert [h["diameter"] for h in written["holes"]] == [2.7] * 4
    assert written["max_height_top"] == 21.4 and written["max_height_bottom"] == 5.0
    step = tmp_path / "limits.step"
    subprocess.run(["kicad-cli", "pcb", "export", "step", "-o", str(step), str(tmp_path / "limits.kicad_pcb")],
                   check=True, capture_output=True)
    j = fit.check(enc, base, lid, geom.step_names(step)).to_json()
    assert j["fits"], j["findings"]
    assert j["placement"]["how"] == "4 of 4 mounting holes on standoffs"


def test_report_files(sample, tmp_path):
    _, paths, base, lid, enc = sample
    result = fit.check(enc, base, lid, geom.step_names(paths["board"]))
    files = report.write(tmp_path, enc, result, base, lid)
    assert json.loads(open(files["report"]).read())["errors"] == 4
    md = open(files["punch_list"]).read()
    assert "## Must fix" in md and "X +0.00, Y +1.50 mm" in md
    html = open(files["view"]).read()
    assert "three@0.160.0" in html and '"bad": "' in html
