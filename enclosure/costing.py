"""What a box costs: its hardware priced from DigiKey, and its plastic from the weight estimate.

Each hardware line becomes a DigiKey keyword search; the first in-stock match with a price is
suggested, with its link. They are suggestions to check (the right screw head, the insert's length
for your printer), not a checked order. Without DigiKey keys (DIGIKEY_CLIENT_ID and
DIGIKEY_CLIENT_SECRET), the list comes back unpriced.
"""

from __future__ import annotations

import os
import re

FILAMENT_PER_KG = 25.0  # USD, a typical spool price; set yours

# Parts-list item to DigiKey keywords.
KEYWORDS = [
    (r"^(M\d(?:\.\d)?)x(\d+) screw$", lambda m: f"{m.group(1)} x {m.group(2)}mm socket head cap screw stainless steel"),
    (r"^(M\d(?:\.\d)?) heat-set insert$", lambda m: f"{m.group(1)} heat set threaded insert brass"),
    (r"^O-ring cord .(\d+(?:\.\d+)?) mm$", lambda m: f"O-ring cord {m.group(1)}mm nitrile"),
    (r"^Rubber foot .(\d+(?:\.\d+)?) mm$", lambda m: f"bumper adhesive round {m.group(1)}mm"),
    (r"^pg(\d+(?:\.\d+)?)$", lambda m: f"cable gland PG{m.group(1)} nylon"),
    (r"^m(\d+)$", lambda m: f"cable gland M{m.group(1)}x1.5 nylon"),
    (r"^pushbutton-22$", lambda m: "22mm pushbutton switch momentary"),
    (r"^toggle-1/4$", lambda m: "toggle switch SPST panel mount 1/4-40"),
    (r"^dc-barrel-snap$", lambda m: "DC power jack panel mount 2.1mm 5.5mm"),
    (r"^keystone$", lambda m: "keystone jack RJ45 coupler"),
    (r"^iec-c14$", lambda m: "IEC C14 inlet snap-in panel mount"),
    (r"^fuse-5x20$", lambda m: "fuse holder panel mount 5x20mm"),
    (r"^fan-(\d+)$", lambda m: f"fan {m.group(1)}mm 12V axial"),
]


def keywords_for(item: str) -> str | None:
    for pattern, make in KEYWORDS:
        m = re.match(pattern, item)
        if m:
            return make(m)
    return None


def price(bom: list[dict], estimate: dict | None, filament_per_kg: float = FILAMENT_PER_KG, digikey=None) -> dict:
    """The parts list with suggested DigiKey parts and prices, the plastic's cost, and the total."""
    from . import parts as partsmod
    if digikey is None and os.environ.get("DIGIKEY_CLIENT_ID") and os.environ.get("DIGIKEY_CLIENT_SECRET"):
        digikey = partsmod.DigiKey(os.environ["DIGIKEY_CLIENT_ID"], os.environ["DIGIKEY_CLIENT_SECRET"])
    rows, total, notes = [], 0.0, []
    for b in bom:
        row = dict(b)
        kw = keywords_for(b["item"]) if b["make"] == "buy" else None
        if kw and digikey is not None:
            row["searched"] = kw
            try:
                hits = [h for h in digikey.search(kw) if (h.get("stock") or 0) > 0 and (h.get("price") or 0) > 0]
            except Exception as e:  # a lookup failing should not lose the rest of the list
                hits = []
                notes.append(f"DigiKey lookup for {b['item']} failed: {e}")
            if hits:
                h = hits[0]
                row.update({"mpn": h["mpn"], "manufacturer": h["manufacturer"], "description": h["description"],
                            "unit_price": h["price"], "url": h["url"], "line": round(h["price"] * b["qty"], 2)})
                total += row["line"]
            else:
                row["note"] = (row.get("note", "") + "; no in-stock match found on DigiKey").lstrip("; ")
        rows.append(row)
    plastic = None
    if estimate:
        plastic = round(estimate["grams"] / 1000 * filament_per_kg, 2)
        total += plastic
    if digikey is None:
        notes.append("no DigiKey keys on the server (DIGIKEY_CLIENT_ID, DIGIKEY_CLIENT_SECRET): hardware is unpriced")
    return {"rows": rows, "plastic": plastic, "filament_per_kg": filament_per_kg, "total": round(total, 2),
            "currency": "USD", "notes": notes,
            "caveat": "DigiKey's first in-stock match for each line, at single-unit price: check each before ordering"}
