#!/usr/bin/env python3
"""Slice this folder's print plates with the Bambu Studio on this computer.

Run it from the print folder EncloSURE made (double-click "Slice in Bambu Studio.command" on a Mac,
or `python3 slice_with_bambu_studio.py`). For each print/plate*.3mf it writes a sliced
print/plate*.gcode.3mf beside it, ready to send to the printer or to upload.

It uses Bambu Studio's own command line with the printer, process and filament named in
print_settings.json. Bambu Studio's command line wants each preset as one complete file, and the app
ships them as chains (each "inherits" from another), so this first writes the complete ones from the
profiles inside your Bambu Studio. If slicing fails for any reason it opens the plate in Bambu Studio
instead, parts already laid out, so you can press Slice there.

Standard library only; needs Python 3.8 or later.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def find_studio():
    """(the Bambu Studio program, its profiles/BBL folder), or (None, None)."""
    system = platform.system()
    tries = []
    if os.environ.get("BAMBU_STUDIO"):
        exe = Path(os.environ["BAMBU_STUDIO"])
        tries.append((exe, exe.parent.parent / "Resources" / "profiles" / "BBL"))
        tries.append((exe, exe.parent / "resources" / "profiles" / "BBL"))
    if system == "Darwin":
        for app in (Path("/Applications/BambuStudio.app"), Path.home() / "Applications" / "BambuStudio.app"):
            tries.append((app / "Contents" / "MacOS" / "BambuStudio", app / "Contents" / "Resources" / "profiles" / "BBL"))
    elif system == "Windows":
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
            if root:
                d = Path(root) / "Bambu Studio"
                tries.append((d / "bambu-studio.exe", d / "resources" / "profiles" / "BBL"))
    else:
        exe = shutil.which("bambu-studio") or shutil.which("BambuStudio")
        if exe:
            exe = Path(exe).resolve()
            for res in (exe.parent / "resources", exe.parent.parent / "resources", exe.parent.parent / "share" / "BambuStudio"):
                tries.append((exe, res / "profiles" / "BBL"))
    for exe, profiles in tries:
        if exe.exists() and profiles.is_dir():
            return exe, profiles
    return None, None


def flatten(profiles: Path, kind: str, name: str, _seen=None) -> dict:
    """One preset with everything it inherits and includes merged in: parents first, then the
    templates it includes, then its own values on top."""
    _seen = _seen or set()
    if (kind, name) in _seen:
        raise ValueError(f"preset '{name}' inherits from itself")
    _seen.add((kind, name))
    path = profiles / kind / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"this Bambu Studio has no {kind} preset named '{name}'")
    own = json.loads(path.read_text(encoding="utf-8"))
    out: dict = {}
    if own.get("inherits"):
        out.update(flatten(profiles, kind, own["inherits"], _seen))
    for inc in own.get("include") or []:
        out.update(flatten(profiles, kind, inc, _seen))
    out.update(own)
    return out


def complete(profiles: Path, kind: str, name: str) -> dict:
    full = flatten(profiles, kind, name)
    full.pop("include", None)
    full["inherits"] = ""
    full["name"] = name
    full["from"] = "system"
    full.pop("instantiation", None)
    return full


def open_in_studio(exe: Path, plate: Path) -> None:
    if platform.system() == "Darwin":
        app = exe.parents[2]
        subprocess.Popen(["open", "-a", str(app), str(plate)])
    else:
        subprocess.Popen([str(exe), str(plate)])


def main() -> int:
    here = Path(__file__).resolve().parent
    settings_file = here / "print_settings.json"
    if not settings_file.exists():
        print("print_settings.json isn't here: run this from the print folder.")
        return 2
    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    plates = [here / p for p in settings.get("plates", [])]
    plates = [p for p in plates if p.exists()]
    if not plates:
        print("No plates to slice in print/.")
        return 2
    exe, profiles = find_studio()
    if not exe:
        print("Bambu Studio wasn't found. Install it, or set BAMBU_STUDIO to its program, then run this again.")
        return 2
    b = settings.get("bambu") or {}
    work = here / "print" / "_presets"
    try:
        if not b:
            raise ValueError(f"no Bambu Studio presets are set for the printer '{settings.get('printer')}'")
        work.mkdir(parents=True, exist_ok=True)
        files = {}
        for kind, key in (("machine", "machine"), ("process", "process"), ("filament", "filament")):
            files[key] = work / f"{key}.json"
            files[key].write_text(json.dumps(complete(profiles, kind, b[key]), indent=1), encoding="utf-8")
    except (OSError, ValueError, KeyError) as e:
        print(f"Couldn't set up the presets ({e}). Opening the plate in Bambu Studio instead: choose the printer and press Slice.")
        open_in_studio(exe, plates[0])
        return 1
    print(f"Bambu Studio: {exe}")
    print(f"Printer: {b['machine']}\nProcess: {b['process']}\nFilament: {b['filament']}\n")
    failed = []
    for plate in plates:
        out = plate.with_name(plate.stem + ".gcode.3mf")
        if out.exists():
            out.unlink()
        cmd = [str(exe), "--load-settings", f"{files['machine']};{files['process']}", "--load-filaments", str(files["filament"]),
               "--slice", "0", "--outputdir", str(plate.parent), "--export-3mf", out.name, str(plate)]
        print(f"Slicing {plate.name} ...", flush=True)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except (OSError, subprocess.TimeoutExpired) as e:
            r = None
            print(f"  it didn't run: {e}")
        if r is not None and r.returncode == 0 and out.exists():
            print(f"  wrote {out.relative_to(here)}")
        else:
            failed.append(plate)
            if r is not None:
                tail = "\n".join((r.stdout + "\n" + r.stderr).strip().splitlines()[-12:])
                (plate.parent / (plate.stem + "_slice_log.txt")).write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")
                print(f"  Bambu Studio returned {r.returncode}. The last of what it said:\n{tail}\n  (all of it is in {plate.stem}_slice_log.txt)")
    shutil.rmtree(work, ignore_errors=True)
    if failed:
        print("\nOpening the plate in Bambu Studio so you can slice it there.")
        open_in_studio(exe, failed[0])
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
