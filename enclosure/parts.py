"""Real parts: what EncloSURE knows about each component, from distributors and datasheets.

A project keeps a `parts.json`:

    {"parts": {
      "J1": {"mpn": "USB4105-GF-A", "manufacturer": "GCT",
             "datasheet": "https://...pdf", "datasheet_file": "datasheets/USB4105-GF-A.pdf",
             "body": [8.94, 7.35, 3.31],      # length x width x height above the board, mm
             "height": 3.31,
             "cutout": {"width": 9.5, "height": 3.8, "max_setback": 1.0},
             "source": {"height": "DigiKey: Height - Seated (Max)", "cutout": "datasheet p.2"}},
      ...}}

`enclosure parts fetch` fills `mpn`, `manufacturer`, `description`, `datasheet` and, where the
distributor lists them, `height` and `body`, and downloads the datasheet. What only the datasheet
drawing gives (a connector's recommended panel cutout and how far back it may sit, a body the
distributor does not list) is read from the PDF and written in by hand or by an agent, with its
page in `source`. Nothing is guessed: a field is there or it is not.

Distributor keys come from the environment, never the file:
  DigiKey: DIGIKEY_CLIENT_ID, DIGIKEY_CLIENT_SECRET (developer.digikey.com, an app with Product
           Information v4)
  Mouser:  MOUSER_API_KEY (mouser.com/api-hub, a Search API key)
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DIGIKEY = "https://api.digikey.com"
MOUSER = "https://api.mouser.com"
USER_AGENT = "EncloSURE/0.2 (+https://github.com/ethanmarshall/encloSURE)"


@dataclass
class Part:
    ref: str
    mpn: str | None = None
    manufacturer: str | None = None
    description: str | None = None
    datasheet: str | None = None
    datasheet_file: str | None = None
    body: list[float] | None = None  # length, width, height above the board, mm
    height: float | None = None
    cutout: dict | None = None  # width, height (mm) and optional max_setback
    side: str | None = None  # top or bottom; read from the board when not given
    source: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "ref" and v not in (None, {}, [])}
        return d


def load(path: str | Path) -> dict[str, Part]:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    out = {}
    for ref, d in (data.get("parts") or {}).items():
        unknown = set(d) - set(Part.__dataclass_fields__) - {"ref"}
        if unknown:
            raise ValueError(f"{path}: parts/{ref} has unknown fields {sorted(unknown)}")
        out[ref] = Part(ref=ref, **d)
        check(out[ref])
    return out


def save(path: str | Path, parts: dict[str, Part]):
    Path(path).write_text(json.dumps({"parts": {r: p.to_json() for r, p in sorted(parts.items())}}, indent=2) + "\n")


def check(p: Part):
    if p.body is not None and (len(p.body) != 3 or min(p.body) <= 0):
        raise ValueError(f"parts/{p.ref}/body is [length, width, height] in mm, all above 0")
    if p.cutout is not None:
        for k in ("width", "height"):
            if not isinstance(p.cutout.get(k), (int, float)) or p.cutout[k] <= 0:
                raise ValueError(f"parts/{p.ref}/cutout needs {k} in mm")
    if p.side not in (None, "top", "bottom"):
        raise ValueError(f"parts/{p.ref}/side is top or bottom")


# Distributor values come as text: `0.126" (3.20mm)`, `3.2 mm`, `0.354" L x 0.287" W (9.00mm x 7.30mm)`.
MM = re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.I)
INCH = re.compile(r"(\d*\.?\d+)\s*(?:\"|in\b)", re.I)


def millimetres(text: str) -> list[float]:
    """The lengths in a distributor's value, in mm (the mm figures where given, else inches)."""
    mm = [float(v) for v in MM.findall(text or "")]
    if mm:
        return mm
    return [round(float(v) * 25.4, 3) for v in INCH.findall(text or "")]


# Names as DigiKey and Mouser list them (checked against live DigiKey answers): a chip
# capacitor gives its height as "Thickness (Max)", a tactile switch as its actuator's height.
HEIGHT_NAMES = ("height - seated (max)", "height above board", "height (max)", "height",
                "thickness (max)", "actuator height off pcb, vertical")
SIZE_NAMES = ("size / dimension", "dimensions")


def dimensions(params: dict[str, str]) -> tuple[float | None, list[float] | None, dict]:
    """Height and [length, width] from a part's parameters, with the parameter each came from."""
    lower = {k.lower().strip(): (k, v) for k, v in params.items()}
    height = size = None
    src = {}
    for name in HEIGHT_NAMES:
        if name in lower:
            vals = millimetres(lower[name][1])
            if vals:
                height = max(vals)
                src["height"] = lower[name][0]
                break
    for name in SIZE_NAMES:
        if name in lower:
            vals = millimetres(lower[name][1])
            if len(vals) >= 2:
                size = vals[:2]
                src["body"] = lower[name][0]
                break
    if size is None and "length" in lower and "width" in lower:
        l, w = millimetres(lower["length"][1]), millimetres(lower["width"][1])
        if l and w:
            size = [l[0], w[0]]
            src["body"] = "Length, Width"
    return height, size, src


def _request(req: urllib.request.Request, opener=None, tries: int = 4):
    opener = opener or urllib.request.urlopen
    req.add_header("User-Agent", USER_AGENT)
    for attempt in range(tries):
        try:
            with opener(req) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < tries - 1:
                time.sleep(float(e.headers.get("Retry-After") or 2 ** attempt))
                continue
            raise


class DigiKey:
    def __init__(self, client_id: str, secret: str, opener=None):
        self.id, self.secret, self.opener = client_id, secret, opener
        self.token, self.expires = None, 0.0

    def _token(self) -> str:
        if self.token and time.time() < self.expires - 30:
            return self.token
        body = urllib.parse.urlencode({"client_id": self.id, "client_secret": self.secret,
                                       "grant_type": "client_credentials"}).encode()
        req = urllib.request.Request(DIGIKEY + "/v1/oauth2/token", data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        d = json.loads(_request(req, self.opener))
        self.token, self.expires = d["access_token"], time.time() + float(d.get("expires_in", 600))
        return self.token

    def lookup(self, mpn: str) -> dict | None:
        req = urllib.request.Request(
            f"{DIGIKEY}/products/v4/search/{urllib.parse.quote(mpn, safe='')}/productdetails")
        req.add_header("X-DIGIKEY-Client-Id", self.id)
        req.add_header("Authorization", f"Bearer {self._token()}")
        req.add_header("Accept", "application/json")
        try:
            d = json.loads(_request(req, self.opener))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        p = d.get("Product") or d
        params = {x.get("ParameterText", ""): x.get("ValueText", "") for x in p.get("Parameters") or []}
        return {
            "mpn": p.get("ManufacturerProductNumber") or mpn,
            "manufacturer": (p.get("Manufacturer") or {}).get("Name"),
            "description": (p.get("Description") or {}).get("ProductDescription"),
            "datasheet": p.get("DatasheetUrl"),
            "parameters": params,
            "distributor": "DigiKey",
        }


    def search(self, keywords: str, limit: int = 8) -> list[dict]:
        """Products matching the words, in DigiKey's order, with their single-unit price and stock."""
        body = json.dumps({"Keywords": keywords, "Limit": limit, "Offset": 0}).encode()
        req = urllib.request.Request(f"{DIGIKEY}/products/v4/search/keyword", data=body, method="POST")
        req.add_header("X-DIGIKEY-Client-Id", self.id)
        req.add_header("Authorization", f"Bearer {self._token()}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        d = json.loads(_request(req, self.opener))
        out = []
        for p in d.get("Products") or []:
            out.append({"mpn": p.get("ManufacturerProductNumber"), "manufacturer": (p.get("Manufacturer") or {}).get("Name"),
                        "description": (p.get("Description") or {}).get("ProductDescription"),
                        "price": p.get("UnitPrice"), "stock": p.get("QuantityAvailable"), "url": p.get("ProductUrl")})
        return out


class Mouser:
    def __init__(self, key: str, opener=None):
        self.key, self.opener = key, opener

    def lookup(self, mpn: str) -> dict | None:
        body = json.dumps({"SearchByPartRequest": {"mouserPartNumber": mpn, "partSearchOptions": "Exact"}}).encode()
        req = urllib.request.Request(f"{MOUSER}/api/v1/search/partnumber?apiKey={urllib.parse.quote(self.key)}",
                                     data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        d = json.loads(_request(req, self.opener))
        found = ((d.get("SearchResults") or {}).get("Parts")) or []
        exact = [x for x in found if (x.get("ManufacturerPartNumber") or "").upper() == mpn.upper()]
        if not (exact or found):
            return None
        p = (exact or found)[0]
        params = {x.get("AttributeName", ""): x.get("AttributeValue", "") for x in p.get("ProductAttributes") or []}
        return {
            "mpn": p.get("ManufacturerPartNumber") or mpn,
            "manufacturer": p.get("Manufacturer"),
            "description": p.get("Description"),
            "datasheet": p.get("DataSheetUrl"),
            "parameters": params,
            "distributor": "Mouser",
        }


def distributors(opener=None) -> list:
    out = []
    if os.environ.get("DIGIKEY_CLIENT_ID") and os.environ.get("DIGIKEY_CLIENT_SECRET"):
        out.append(DigiKey(os.environ["DIGIKEY_CLIENT_ID"], os.environ["DIGIKEY_CLIENT_SECRET"], opener))
    if os.environ.get("MOUSER_API_KEY"):
        out.append(Mouser(os.environ["MOUSER_API_KEY"], opener))
    return out


def fetch(part: Part, sources: list, folder: Path | None = None, opener=None) -> list[str]:
    """Fill *part* from the first distributor that knows its MPN; download its datasheet into
    *folder*. Fields already set are kept (a datasheet reading beats a distributor's listing).
    Returns notes on what was done."""
    if not part.mpn:
        return [f"{part.ref}: no mpn"]
    notes = []
    found = None
    for src in sources:
        try:
            found = src.lookup(part.mpn)
        except urllib.error.HTTPError as e:
            notes.append(f"{part.ref}: {type(src).__name__} answered HTTP {e.code}")
            continue
        if found:
            break
    if not found:
        notes.append(f"{part.ref}: {part.mpn} not found" + ("" if sources else " (no distributor keys set)"))
        return notes
    dist = found["distributor"]
    for k in ("manufacturer", "description", "datasheet"):
        if getattr(part, k) is None and found.get(k):
            setattr(part, k, found[k])
    height, size, src = dimensions(found["parameters"])
    if part.height is None and height is not None:
        part.height = height
        part.source["height"] = f"{dist}: {src['height']}"
    if part.body is None and size is not None and (part.height or height):
        part.body = [size[0], size[1], part.height or height]
        part.source["body"] = f"{dist}: {src['body']}" + (f" and {src['height']}" if "height" in src else "")
    notes.append(f"{part.ref}: {part.mpn} from {dist}"
                 + (f", height {part.height} mm" if part.height else ", no height listed"))
    if folder is not None and part.datasheet and not part.datasheet_file:
        url = part.datasheet if not part.datasheet.startswith("//") else "https:" + part.datasheet
        folder.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", part.mpn) + ".pdf"
        try:
            data = _request(urllib.request.Request(url), opener)
            if data[:4] == b"%PDF":
                (folder / name).write_bytes(data)
                part.datasheet_file = str(folder / name)
                notes.append(f"{part.ref}: datasheet saved")
            else:
                notes.append(f"{part.ref}: the datasheet link is a web page, not a PDF: open {url}")
        except (urllib.error.URLError, OSError) as e:
            notes.append(f"{part.ref}: could not download the datasheet ({e}); open {url}")
    return notes


def from_board(kicad_pcb: str | Path) -> dict[str, dict]:
    """Each footprint's reference, value, MPN field, position (KiCad page mm), rotation and side,
    read from the .kicad_pcb file itself (no KiCad needed)."""
    from .kicad import footprints
    out = {}
    for ref, fp in footprints(kicad_pcb).items():
        mpn = next((v for k, v in fp["fields"].items()
                    if k.lower() in ("mpn", "manufacturer part number", "mfr part number", "part number") and v), None)
        out[ref] = {"value": fp["value"], "mpn": mpn, "at": fp["at"], "rotation": fp["rotation"],
                    "side": fp["side"], "has_model": fp["has_model"]}
    return out
