"""Lengths typed the way a shop says them: 5, 5 mm, 0.25 in, 1/4, 13/64", 1-1/2 or 1 1/2 in.

A fraction is inches. A plain number is millimetres unless it carries in or a " mark."""
from __future__ import annotations

import re
from fractions import Fraction

_FRAC = re.compile(r"^(?:(\d+)[\s-]+)?(\d+)\s*/\s*(\d+)$")


def parse(value, what: str = "size") -> tuple[float, str]:
    """(millimetres, how to say it). 0 or blank gives (0, "")."""
    if value is None or isinstance(value, bool):
        return 0.0, ""
    if isinstance(value, (int, float)):
        return float(value), f"{float(value):g} mm"
    s = str(value).strip().lower().replace("″", '"').replace("”", '"').replace("inches", "in").replace("inch", "in")
    if not s:
        return 0.0, ""
    unit = ""
    for suffix, u in (("mm", "mm"), ("in", "in"), ('"', "in")):
        if s.endswith(suffix):
            s, unit = s[: -len(suffix)].strip().rstrip("."), u
            break
    m = _FRAC.match(s)
    try:
        if m:
            if unit == "mm":
                raise ValueError
            whole, a, b = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
            if b == 0:
                raise ValueError
            inches = whole + Fraction(a, b)
            return round(float(inches) * 25.4, 6), f"{say_fraction(inches)} in ({float(inches) * 25.4:.4g} mm)"
        n = float(s)
    except ValueError:
        raise ValueError(f"{what}: a size such as 5, 5 mm, 0.25 in, 1/4 or 13/64 (a fraction is inches)") from None
    if unit == "in":
        return round(n * 25.4, 6), f"{n:g} in ({n * 25.4:.4g} mm)"
    return n, f"{n:g} mm"


def say_fraction(inches: Fraction) -> str:
    whole, rest = divmod(inches, 1)
    if not rest:
        return str(int(whole))
    return (f"{int(whole)}-" if whole else "") + f"{rest.numerator}/{rest.denominator}"


def short(value, mm: float) -> str:
    """A few characters to engrave: 1/4" for a size typed in inches, Ø5 for millimetres."""
    if isinstance(value, str):
        s = value.strip().lower()
        m = _FRAC.match(s.rstrip('"').replace("in", "").strip())
        if m:
            whole, a, b = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
            return say_fraction(whole + Fraction(a, b)) + '"'
        if s.endswith("in") or s.endswith('"'):
            return f"{mm / 25.4:.3f}".rstrip("0").rstrip(".").lstrip("0") + '"'
    return f"Ø{mm:.4g}"


def parse_list(text, what: str = "sizes") -> list[tuple[float, str]]:
    """Sizes with commas between: 3, 4, 1/4, 13/64 in."""
    out = []
    for part in str(text).replace(";", ",").split(","):
        if part.strip():
            mm, _ = parse(part, what)
            out.append((mm, part.strip()))
    return out
