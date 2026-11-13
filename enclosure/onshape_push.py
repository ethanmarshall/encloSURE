"""Put the box's Onshape feature straight into an Onshape document, through Onshape's REST API.

The server needs Onshape API keys (Onshape: My account > Developer > API keys) in
ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY. The document it makes belongs to that account; share it,
or use your own keys on your own copy. Then open the document's Part Studio and insert
"EncloSURE Box" from the custom features on the toolbar.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("ONSHAPE_URL", "https://cad.onshape.com")


def enabled() -> bool:
    return bool(os.environ.get("ONSHAPE_ACCESS_KEY") and os.environ.get("ONSHAPE_SECRET_KEY"))


def _call(method: str, path: str, body: dict | None = None) -> dict:
    key, secret = os.environ["ONSHAPE_ACCESS_KEY"], os.environ["ONSHAPE_SECRET_KEY"]
    auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={
        "Authorization": f"Basic {auth}", "Accept": "application/json;charset=UTF-8; qs=0.09",
        "Content-Type": "application/json;charset=UTF-8; qs=0.09"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode()
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Onshape said {e.code} to {method} {path.split('?')[0]}: {detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not reach Onshape: {e.reason}") from None


def push(feature_text: str, name: str = "EncloSURE box") -> dict:
    """A new document holding the feature in a Feature Studio. Returns its links."""
    if not enabled():
        raise RuntimeError("set ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY on the server to send boxes to Onshape")
    doc = _call("POST", "/api/documents", {"name": name[:100]})
    did, wid = doc["id"], doc["defaultWorkspace"]["id"]
    fs = _call("POST", f"/api/featurestudios/d/{did}/w/{wid}", {"name": "EncloSURE Box"})
    eid = fs["id"]
    current = _call("GET", f"/api/featurestudios/d/{did}/w/{wid}/e/{eid}")
    _call("POST", f"/api/featurestudios/d/{did}/w/{wid}/e/{eid}", {
        "contents": feature_text,
        "serializationVersion": current.get("serializationVersion", "1.1.23"),
        "sourceMicroversion": current.get("sourceMicroversion", ""),
        "rejectMicroversionSkew": False,
    })
    return {"document": f"{BASE}/documents/{did}/w/{wid}", "feature_studio": f"{BASE}/documents/{did}/w/{wid}/e/{eid}",
            "next": "open the document's Part Studio and insert EncloSURE Box from the custom features"}
