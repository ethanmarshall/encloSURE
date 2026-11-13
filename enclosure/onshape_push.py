"""The box in Onshape through its REST API: send a box (a new document with the feature inserted and
built), update that same document when the box changes, and read an enclosure from a Part Studio.

The server needs Onshape API keys (Onshape: My account > Developer > API keys) in
ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY. The document it makes belongs to that account; share it,
or use your own keys on your own copy.
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


def _signed_headers(method: str, path: str, query: str = "") -> dict:
    """Onshape's request signing for API keys: an HMAC-SHA256 of the method, a nonce, the date, the
    content type, the path and the query, lowercased, keyed with the secret key."""
    import email.utils
    import hashlib
    import hmac
    import secrets
    import string
    key, secret = os.environ["ONSHAPE_ACCESS_KEY"], os.environ["ONSHAPE_SECRET_KEY"]
    nonce = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(25))
    date = email.utils.formatdate(usegmt=True)
    ctype = "application/json"
    text = f"{method}\n{nonce}\n{date}\n{ctype}\n{path}\n{query}\n".lower()
    sig = base64.b64encode(hmac.new(secret.encode(), text.encode(), hashlib.sha256).digest()).decode()
    return {"Date": date, "On-Nonce": nonce, "Content-Type": ctype, "Accept": "application/json",
            "Authorization": f"On {key}:HmacSHA256:{sig}"}


def _call(method: str, path: str, body: dict | None = None, raw: bool = False):
    data = json.dumps(body).encode() if body is not None else None
    bare, _, query = path.partition("?")
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=_signed_headers(method, bare, query))
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            if raw:
                return r.read()
            text = r.read().decode()
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Onshape said {e.code} to {method} {path.split('?')[0]}: {detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not reach Onshape: {e.reason}") from None


def _write_studio(did: str, wid: str, eid: str, text: str) -> str:
    """Put the feature's text in the Feature Studio; return the studio's new microversion."""
    current = _call("GET", f"/api/featurestudios/d/{did}/w/{wid}/e/{eid}")
    r = _call("POST", f"/api/featurestudios/d/{did}/w/{wid}/e/{eid}", {
        "contents": text,
        "serializationVersion": current.get("serializationVersion", "1.1.23"),
        "sourceMicroversion": current.get("sourceMicroversion", ""),
        "rejectMicroversionSkew": False,
    })
    els = {e["id"]: e for e in _call("GET", f"/api/documents/d/{did}/w/{wid}/elements")}
    return els[eid]["microversionId"] if eid in els else r.get("microversionSkew", "")


def _feature(fs_eid: str, mv: str, fid: str | None = None) -> dict:
    f = {"btType": "BTMFeature-134", "featureType": "enclosureBox", "name": "EncloSURE Box",
         "namespace": f"e{fs_eid}::m{mv}", "parameters": [], "returnAfterSubfeatures": False, "suppressed": False}
    if fid:
        f["featureId"] = fid
    return {"btType": "BTFeatureDefinitionCall-1406", "feature": f}


def _links(ids: dict) -> dict:
    d, w = ids["did"], ids["wid"]
    return {"document": f"{BASE}/documents/{d}/w/{w}/e/{ids['partstudio']}",
            "feature_studio": f"{BASE}/documents/{d}/w/{w}/e/{ids['studio']}"}


def push(feature_text: str, name: str = "EncloSURE box") -> dict:
    """A new document: the feature's Feature Studio, and the feature inserted in its Part Studio
    (the Base and Lid built, with the settings as its defaults). Returns the ids for update()."""
    if not enabled():
        raise RuntimeError("set ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY on the server to send boxes to Onshape")
    doc = _call("POST", "/api/documents", {"name": name[:100]})
    did, wid = doc["id"], doc["defaultWorkspace"]["id"]
    eid = _call("POST", f"/api/featurestudios/d/{did}/w/{wid}", {"name": "EncloSURE Box"})["id"]
    mv = _write_studio(did, wid, eid, feature_text)
    studios = [e for e in _call("GET", f"/api/documents/d/{did}/w/{wid}/elements") if e.get("elementType") == "PARTSTUDIO"]
    ps = studios[0]["id"] if studios else _call("POST", f"/api/partstudios/d/{did}/w/{wid}", {"name": "Enclosure"})["id"]
    r = _call("POST", f"/api/v9/partstudios/d/{did}/w/{wid}/e/{ps}/features", _feature(eid, mv))
    ids = {"did": did, "wid": wid, "studio": eid, "partstudio": ps, "feature": r["feature"]["featureId"]}
    status = (r.get("featureState") or {}).get("featureStatus", "OK")
    return {"ids": ids, **_links(ids), "status": status,
            "next": "open the document: the box is in its Part Studio; double-click EncloSURE Box to change it"}


def update(ids: dict, feature_text: str) -> dict:
    """Change the box in a document push() made: the Feature Studio gets the new settings and the
    Part Studio's EncloSURE Box takes them (its dialog values reset to them). Your own features
    after it stay. If the feature was deleted there, it is inserted again."""
    if not enabled():
        raise RuntimeError("set ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY on the server to send boxes to Onshape")
    did, wid, eid, ps = ids["did"], ids["wid"], ids["studio"], ids["partstudio"]
    for k in ("did", "wid", "studio", "partstudio"):
        if not str(ids.get(k, "")).isalnum():
            raise ValueError("not an EncloSURE Onshape document")
    mv = _write_studio(did, wid, eid, feature_text)
    base = f"/api/v9/partstudios/d/{did}/w/{wid}/e/{ps}"
    feats = _call("GET", base + "/features")["features"]
    mine = next((f for f in feats if f.get("featureType") == "enclosureBox" and f["featureId"] == ids.get("feature")), None) \
        or next((f for f in feats if f.get("featureType") == "enclosureBox"), None)
    if mine is None:
        r = _call("POST", base + "/features", _feature(eid, mv))
    else:
        r = _call("POST", base + f"/features/featureid/{mine['featureId']}", _feature(eid, mv, mine["featureId"]))
    ids = {**ids, "feature": r["feature"]["featureId"]}
    status = (r.get("featureState") or {}).get("featureStatus", "OK")
    return {"ids": ids, **_links(ids), "status": status}


def parse_link(url: str) -> tuple[str, str, str, str]:
    """(document, w/v/m, its id, element) from an Onshape link to a Part Studio."""
    import re
    m = re.search(r"/documents/([0-9a-f]{24})/([wvm])/([0-9a-f]{24})/e/([0-9a-f]{24})", url)
    if not m:
        raise ValueError("paste a link to a Part Studio: cad.onshape.com/documents/.../w/.../e/...")
    return m.group(1), m.group(2), m.group(3), m.group(4)


def export_step(url: str, out) -> str:
    """The Part Studio as a STEP file (Onshape translates it), saved to *out*."""
    import time
    from pathlib import Path
    if not enabled():
        raise RuntimeError("set ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY on the server to read from Onshape")
    did, wvm, wvmid, eid = parse_link(url)
    t = _call("POST", f"/api/v9/partstudios/d/{did}/{wvm}/{wvmid}/e/{eid}/translations",
              {"formatName": "STEP", "storeInDocument": False, "translate": True})
    for _ in range(90):
        st = _call("GET", f"/api/v9/translations/{t['id']}")
        if st["requestState"] != "ACTIVE":
            break
        time.sleep(2)
    if st["requestState"] != "DONE":
        raise RuntimeError(f"Onshape could not export the Part Studio: {st.get('failureReason') or st['requestState']}")
    data = _call("GET", f"/api/v9/documents/d/{did}/externaldata/{st['resultExternalDataIds'][0]}", raw=True)
    Path(out).write_bytes(data)
    return str(out)
