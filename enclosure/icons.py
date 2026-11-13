"""Small symbols to put beside panel holes: drawn as flat faces about `size` mm tall, centred, to be
extruded (engraved or raised). Simple line drawings that print at 0.4 mm nozzle sizes: strokes are
at least 0.7 mm wide.

The power symbol follows IEC 60417-5009 (a broken circle with a line through the gap); the USB one is
the usual trident; the antenna is a mast with a V; the rest are short text.
"""

from __future__ import annotations

import math

from build123d import Align, Circle, Pos, Rectangle, Rot, Text

# Which symbol suits which preset.
BY_PRESET = {"usb-c": "usb", "dc-barrel-snap": "dc", "iec-c14": "power", "fuse-5x20": "fuse", "sma-bulkhead": "antenna",
             "bnc-bulkhead": "antenna", "keystone": "lan", "fan-40": "fan", "fan-60": "fan", "fan-80": "fan",
             "pushbutton-22": "power", "toggle-1/4": "onoff", "toggle-15/32": "onoff"}
NAMES = ("usb", "power", "antenna", "fan", "dc", "fuse", "lan", "onoff")


def icon_for(preset: str | None) -> str | None:
    return BY_PRESET.get(preset or "")


def _bar(x0, y0, x1, y1, w):
    """A stroke from (x0, y0) to (x1, y1), w wide."""
    length = math.hypot(x1 - x0, y1 - y0)
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    return Pos((x0 + x1) / 2, (y0 + y1) / 2) * (Rot(0, 0, ang) * Rectangle(length + w, w))


def icon_shape(name: str, size: float = 6.0):
    s = size
    w = max(0.7, 0.12 * s)
    if name == "power":
        r = s / 2 - w / 2
        ring = Circle(r + w / 2) - Circle(r - w / 2)
        ring -= Pos(0, s / 2) * Rectangle(0.55 * s, 0.6 * s)  # the gap at the top
        return ring + _bar(0, 0.05 * s, 0, s / 2 + 0.05 * s, w)
    if name == "usb":
        stem = _bar(0, -0.35 * s, 0, 0.42 * s, w)
        head = Pos(0, 0.42 * s) * (Rot(0, 0, 90) * Circle(0.17 * s))  # the arrow's place: a dot reads cleaner when small
        left = _bar(0, -0.05 * s, -0.28 * s, 0.12 * s, w) + _bar(-0.28 * s, 0.12 * s, -0.28 * s, 0.22 * s, w)
        right = _bar(0, -0.2 * s, 0.28 * s, -0.03 * s, w) + _bar(0.28 * s, -0.03 * s, 0.28 * s, 0.08 * s, w)
        foot = Pos(0, -0.4 * s) * Circle(0.13 * s)
        return stem + head + left + right + foot + Pos(-0.28 * s, 0.26 * s) * Circle(0.09 * s) + \
            Pos(0.28 * s, 0.12 * s) * Rectangle(0.17 * s, 0.17 * s)
    if name == "antenna":
        return (_bar(0, -s / 2, 0, s / 2 - w, w) + _bar(0, 0.05 * s, -0.35 * s, s / 2 - w / 2, w)
                + _bar(0, 0.05 * s, 0.35 * s, s / 2 - w / 2, w))
    if name == "fan":
        ring = Circle(s / 2) - Circle(s / 2 - w)
        blades = None
        for k in range(3):
            b = Rot(0, 0, 120 * k) * (Pos(0, 0.2 * s) * (Rot(0, 0, 25) * Rectangle(0.16 * s, 0.4 * s)))
            blades = b if blades is None else blades + b
        return ring + blades + Circle(0.1 * s)
    text = {"dc": "DC", "fuse": "F", "lan": "LAN", "onoff": "I/O"}.get(name)
    if text:
        return Text(text, s * (0.75 if len(text) > 2 else 0.9), align=(Align.CENTER, Align.CENTER))
    raise ValueError(f"icon: one of {', '.join(NAMES)}")
