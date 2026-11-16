"""v1.6: the print folder, and the Bambu Studio slicing script's preset handling."""

import base64
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from enclosure import bambu_slice, kit
from enclosure.web import app

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _kit(body):
    r = TestClient(app).post("/api/kit", json=body)
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(r.content))
    top = z.namelist()[0].split("/")[0]
    return z, top, {n[len(top) + 1:] for n in z.namelist()}


def test_box_and_parts_folder():
    z, top, names = _kit({"box": {"size": [70, 45, 25]}, "parts": [{"kind": "dowel", "params": {"mode": "print"}, "qty": 3}],
                          "bed": "bambu-h3c", "material": "PETG",
                          "images": [{"name": "view", "data": "data:image/png;base64," + base64.b64encode(PNG).decode()},
                                     {"name": "bad", "data": "bm90IGEgcG5n"}]})
    assert {"README.md", "print_settings.json", "print/plate.3mf", "stl/base.stl", "stl/lid.stl", "stl/dowel.stl",
            "step/base.step", "step/lid.step", "step/dowel.step", "step/assembly.step", "images/01_view.png",
            "slice_with_bambu_studio.py", "Slice in Bambu Studio.command"} <= names
    assert not any("bad" in n for n in names)
    s = json.loads(z.read(f"{top}/print_settings.json"))
    assert s["parts"] == {"base": 1, "lid": 1, "dowel": 3} and s["bambu"]["filament"] == "Bambu PETG HF @BBL H3C"
    readme = z.read(f"{top}/README.md").decode()
    assert "3 x `stl/dowel.stl`" in readme and "Slicing with Bambu Studio" in readme
    cmd = z.getinfo(f"{top}/Slice in Bambu Studio.command")
    assert (cmd.external_attr >> 16) & 0o111


def test_case_folder_and_no_script_for_other_printers():
    z, top, names = _kit({"case": {"size": [120, 80, 28]}, "bed": "prusa-mk4", "material": "PLA"})
    assert {"stl/tray.stl", "stl/lid.stl", "stl/latch_tab.stl", "step/assembly.step"} <= names
    assert {"print/plate_1.3mf", "print/plate_2.3mf"} <= names   # the tray and lid don't share a 250 x 210 mm bed
    assert "slice_with_bambu_studio.py" not in names
    assert json.loads(z.read(f"{top}/print_settings.json"))["parts"]["latch_tab"] == 2


def test_nothing_to_print():
    assert TestClient(app).post("/api/kit", json={"parts": []}).status_code == 400


def test_presets_flatten(tmp_path):
    prof = tmp_path / "BBL"
    for kind in ("machine", "process", "filament"):
        (prof / kind).mkdir(parents=True)
    (prof / "machine" / "root.json").write_text(json.dumps({"name": "root", "type": "machine", "a": "1", "b": "1"}))
    (prof / "machine" / "tmpl.json").write_text(json.dumps({"name": "tmpl", "b": "2", "c": "2"}))
    (prof / "machine" / "mine.json").write_text(json.dumps({"name": "mine", "inherits": "root", "include": ["tmpl"], "c": "3",
                                                             "instantiation": "true"}))
    full = bambu_slice.complete(prof, "machine", "mine")
    assert (full["a"], full["b"], full["c"]) == ("1", "2", "3")
    assert full["inherits"] == "" and "include" not in full and full["name"] == "mine" and full["type"] == "machine"
    with pytest.raises(FileNotFoundError):
        bambu_slice.complete(prof, "machine", "nope")
    (prof / "machine" / "loop.json").write_text(json.dumps({"name": "loop", "inherits": "loop"}))
    with pytest.raises(ValueError):
        bambu_slice.complete(prof, "machine", "loop")


def test_bambu_names():
    assert kit.bambu_presets("prusa-mk4", "PLA") is None
    assert kit.bambu_presets("bambu-x1", "PLA")["filament"] == "Bambu PLA Basic @BBL X1C"
