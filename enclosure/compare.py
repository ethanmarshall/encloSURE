"""Printed, bent sheet metal or laser-cut: roughly what one box costs each way, and where the fixed
costs make one cheaper than another as the quantity grows.

Every rate is yours to set: the defaults are placeholders of the right order for a hobby printer, a
small online sheet-metal shop and a laser cutter, not quotes. Get real quotes before deciding."""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class Rates:
    filament_per_kg: float = 25.0
    printer_per_hour: float = 0.50  # power, wear, your time if you count it
    sheet_per_kg: float = 12.0  # aluminium 5052 sheet, cut to size
    bend_each: float = 1.50
    sheet_setup: float = 30.0  # per order
    laser_sheet_per_m2: float = 45.0  # 3 mm acrylic
    laser_per_m_cut: float = 1.00
    laser_setup: float = 10.0


def compare(spec, made: dict, rates: Rates | None = None, sliced: dict | None = None, quantities=(1, 10, 50)) -> dict:
    from . import lasercut, sheetmetal
    r = rates or Rates()
    est = sliced or made.get("estimate") or {}
    grams, hours = est.get("grams", 0.0), est.get("hours", 0.0)
    printed_each = grams / 1000 * r.filament_per_kg + hours * r.printer_per_hour
    # Sheet metal: the two flat blanks' area x thickness x density, and its bends.
    sheet = sheetmetal.Sheet(size=list(spec.inner), cutouts=[dict(c) for c in spec.cutouts])
    f = sheetmetal.flats(sheet)
    area = 0.0
    for k in ("base", "cover"):
        cx, cy = f[k]["core"]
        area += cx * cy + sum((sheet.BA + leg) * width for leg, width in f[k]["flaps"].values())
    kg = area * sheet.thickness / 1e6 * sheetmetal.MATERIALS[sheet.material]["density"]
    bends = 6
    sheet_each = kg * r.sheet_per_kg + bends * r.bend_each
    # Laser: the six panels' area and the cut length round them (outlines plus fingers, roughly x 1.6).
    L, W, H = spec.inner
    t = 3.0
    panels = 2 * (L * W + L * H + W * H) / 1e6
    cut_m = 2 * (2 * (L + W) + 2 * (L + H) + 2 * (W + H)) / 1000 * 1.6
    laser_each = panels * 1.15 * r.laser_sheet_per_m2 + cut_m * r.laser_per_m_cut
    rows = []
    for q in quantities:
        rows.append({"qty": q, "printed": round(printed_each * q, 2), "sheet_metal": round(r.sheet_setup + sheet_each * q, 2),
                     "laser_cut": round(r.laser_setup + laser_each * q, 2)})
    each = {"printed": round(printed_each, 2), "sheet_metal": round(sheet_each, 2), "laser_cut": round(laser_each, 2)}
    notes = [f"printed: {grams:.0f} g and {hours:g} h each" + (" (PrusaSlicer)" if sliced else " (rough estimate)"),
             f"sheet metal: {kg * 1000:.0f} g of {sheet.thickness:g} mm {sheet.material}, {bends} bends, plus a setup charge per order",
             f"laser-cut: {panels:.3f} m² of {t:g} mm sheet and about {cut_m:.1f} m of cutting"]
    # Where the lines cross: printing has no setup, so it wins at one; past a point the others may.
    cross = {}
    for other, setup in (("sheet_metal", r.sheet_setup), ("laser_cut", r.laser_setup)):
        if printed_each > each[other]:
            cross[other] = round(setup / (printed_each - each[other]), 1)
    if cross:
        notes += [f"{k.replace('_', ' ')} gets cheaper than printing from about {v:g} boxes" for k, v in cross.items()]
    return {"each": each, "rows": rows, "notes": notes, "rates": asdict(r),
            "caveat": "placeholder rates, not quotes: set your own, and get quotes before choosing"}
