"""Parts: distributor answers are read right (mocked: no keys in tests), and parts.json data
reaches the fit check: a block for a part with no 3D model, a model height against the
datasheet, and an opening against the datasheet's recommended cutout."""

import io
import json
import shutil
import subprocess
import urllib.error

import pytest

from enclosure import fit, geom, parts, samples, shell


class Fake:
    """DigiKey and Mouser as their APIs answer; a PDF for the datasheet link."""

    def __init__(self):
        self.seen = []

    def __call__(self, req):
        url = req.full_url
        self.seen.append(url)
        if url.endswith("/v1/oauth2/token"):
            body = {"access_token": "t", "expires_in": 600}
        elif "/products/v4/search/USB4105-GF-A/productdetails" in url:
            assert req.get_header("Authorization") == "Bearer t"
            body = {"Product": {
                "ManufacturerProductNumber": "USB4105-GF-A", "Manufacturer": {"Name": "GCT"},
                "Description": {"ProductDescription": "USB-C receptacle"},
                "DatasheetUrl": "https://example.com/usb4105.pdf",
                "Parameters": [{"ParameterText": "Height - Seated (Max)", "ValueText": '0.130" (3.31mm)'},
                               {"ParameterText": "Size / Dimension",
                                "ValueText": '0.352" L x 0.289" W (8.94mm x 7.35mm)'}]}}
        elif "/products/v4/search/" in url:
            raise urllib.error.HTTPError(url, 404, "not found", {}, io.BytesIO())
        elif "api.mouser.com" in url:
            body = {"SearchResults": {"Parts": [{
                "ManufacturerPartNumber": "B3U-1000P", "Manufacturer": "Omron",
                "Description": "Tactile switch", "DataSheetUrl": "https://example.com/b3u.pdf",
                "ProductAttributes": [{"AttributeName": "Height", "AttributeValue": "1.6 mm"},
                                      {"AttributeName": "Length", "AttributeValue": "3 mm"},
                                      {"AttributeName": "Width", "AttributeValue": "2.5 mm"}]}]}}
        elif url.endswith(".pdf"):
            return io.BytesIO(b"%PDF-1.7 fake")
        else:
            raise AssertionError(url)
        return io.BytesIO(json.dumps(body).encode())


def test_distributor_values_read_in_millimetres():
    assert parts.millimetres('0.126" (3.20mm)') == [3.2]
    assert parts.millimetres("3.2 mm") == [3.2]
    assert parts.millimetres('0.25"') == [6.35]
    h, size, src = parts.dimensions({"Height - Seated (Max)": '0.130" (3.31mm)',
                                     "Size / Dimension": '0.352" L x 0.289" W (8.94mm x 7.35mm)'})
    assert (h, size) == (3.31, [8.94, 7.35]) and src["height"] == "Height - Seated (Max)"


def test_fetch_from_digikey_then_mouser(tmp_path):
    fake = Fake()
    sources = [parts.DigiKey("id", "secret", fake), parts.Mouser("key", fake)]
    j1 = parts.Part("J1", mpn="USB4105-GF-A")
    notes = parts.fetch(j1, sources, tmp_path, fake)
    assert j1.body == [8.94, 7.35, 3.31] and j1.height == 3.31 and j1.manufacturer == "GCT"
    assert j1.source["height"] == "DigiKey: Height - Seated (Max)"
    assert (tmp_path / "USB4105-GF-A.pdf").read_bytes().startswith(b"%PDF")
    sw = parts.Part("SW1", mpn="B3U-1000P", height=1.5, source={"height": "datasheet p.1"})
    parts.fetch(sw, sources, None, fake)
    assert sw.height == 1.5, "a datasheet reading is kept over a distributor's listing"
    assert sw.body == [3.0, 2.5, 1.5] and sw.manufacturer == "Omron"
    assert any("from DigiKey" in n for n in notes)


def test_parts_file_round_trip_and_refusals(tmp_path):
    path = tmp_path / "parts.json"
    parts.save(path, {"J1": parts.Part("J1", mpn="X", body=[1, 2, 3], cutout={"width": 9.8, "height": 4})})
    assert parts.load(path)["J1"].cutout["width"] == 9.8
    path.write_text(json.dumps({"parts": {"J1": {"body": [1, 2]}}}))
    with pytest.raises(ValueError):
        parts.load(path)
    path.write_text(json.dumps({"parts": {"J1": {"colour": "red"}}}))
    with pytest.raises(ValueError):
        parts.load(path)


@pytest.mark.skipif(shutil.which("kicad-cli") is None, reason="KiCad is not installed")
def test_datasheet_data_in_the_fit(tmp_path):
    from enclosure import kicad
    if kicad.pcbnew is None:
        pytest.skip("KiCad's Python module is not available")
    import pcbnew
    paths = samples.write(tmp_path)
    base, lid = geom.load(paths["base"]), geom.load(paths["lid"])
    enc, _ = shell.read(base, lid)
    pcb_path = tmp_path / "b.kicad_pcb"
    kicad.limits(enc, pcb_path)
    board = pcbnew.LoadBoard(str(pcb_path))
    # J1: a USB-C receptacle with no 3D model, at the -X edge, centred on the opening.
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("J1")
    x = kicad.ORIGIN[0] - 47.5 + 8.94 / 2 - 0.6
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(kicad.ORIGIN[1])))
    board.Add(fp)
    pcbnew.SaveBoard(str(pcb_path), board)
    step = tmp_path / "b.step"
    subprocess.run(["kicad-cli", "pcb", "export", "step", "-o", str(step), str(pcb_path)],
                   check=True, capture_output=True)
    footprints = parts.from_board(pcb_path)
    assert footprints["J1"]["has_model"] is False
    solids = geom.step_names(step)
    # Without parts.json, J1 cannot be checked.
    j = fit.check(enc, base, lid, solids, footprints=footprints).to_json()
    assert any(f["code"] == "unchecked_part" and f["subject"] == "J1" for f in j["findings"])
    # With its body and its datasheet's cutout (larger than the enclosure's opening).
    specs = {"J1": parts.Part("J1", body=[8.94, 7.35, 3.26], cutout={"width": 9.8, "height": 4.0},
                              source={"cutout": "datasheet p.2"})}
    j = fit.check(enc, base, lid, solids, specs=specs, footprints=footprints).to_json()
    codes = {(f["code"], f["subject"].split(" at ")[0]) for f in j["findings"]}
    assert ("datasheet_block", "J1") in codes
    below = next(f for f in j["findings"] if f["code"] == "opening_below_datasheet")
    assert "9.80 × 4.00" in below["message"] and "datasheet p.2" in below["message"]
    assert ("opening_misaligned", "J1") not in codes
