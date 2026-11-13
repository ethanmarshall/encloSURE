"""Check, fix, re-export, check again, until the board fits or only a person can fix what's left.

    enclosure autofit base.step board.kicad_pcb --lid lid.step -o autofit

Each round exports the board's STEP with KiCad (`kicad-cli`, or `$BACKPLANE_KICAD_CLI`), runs the
fit check, and applies the KiCad moves it asks for to a new copy of the board. Your .kicad_pcb is
never changed: the result is autofit/board_fixed.kicad_pcb, with each round's report beside it.
It stops when the board fits, when a round asks for no moves (a part too tall, an opening too small:
those need you), or after --rounds.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import fit as fitmod
from . import kicad, report
from .geom import step_names


def kicad_cli() -> str:
    for c in (os.environ.get("BACKPLANE_KICAD_CLI"), shutil.which("kicad-cli")):
        if c:
            return c
    raise RuntimeError("kicad-cli was not found: install KiCad, or run inside Backplane (it sets $BACKPLANE_KICAD_CLI)")


def export_step(pcb: Path, step: Path):
    r = subprocess.run([kicad_cli(), "pcb", "export", "step", "--subst-models", "-f", "-o", str(step), str(pcb)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not step.exists():
        raise RuntimeError(f"kicad-cli could not export {pcb.name}: {(r.stderr or r.stdout).strip()[-400:]}")


def run(enc, base, lid, pcb, out, rounds: int = 4, settings: fitmod.Settings | None = None,
        specs: dict | None = None) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    current = out / "board_fixed.kicad_pcb"
    shutil.copyfile(pcb, current)
    history = []
    for n in range(1, rounds + 1):
        step = out / f"round{n}.step"
        export_step(current, step)
        from . import parts as partsmod
        result = fitmod.check(enc, base, lid, step_names(step), settings or fitmod.Settings(), None,
                              specs or {}, partsmod.from_board(current))
        j = result.to_json()
        folder = out / f"round{n}"
        report.write(folder, enc, result, base, lid, title=f"EncloSURE autofit, round {n}")
        entry = {"round": n, "fits": j["fits"], "errors": j["errors"], "warnings": j["warnings"], "report": str(folder)}
        history.append(entry)
        if j["fits"]:
            break
        moves = kicad.moves_from_fit(j["findings"])
        if not moves:
            entry["left"] = [f"{f['subject']}: {f['message']}" for f in j["findings"] if f["severity"] == "error"]
            break
        entry["moved"] = kicad.move_footprints(current, moves, current)
    final = history[-1]
    (out / "autofit.json").write_text(json.dumps(history, indent=2) + "\n")
    return {"fits": final["fits"], "rounds": history, "board": str(current),
            "next": "open board_fixed.kicad_pcb in KiCad" if final["fits"] else
            "what is left needs you: see the last round's punch list"}
