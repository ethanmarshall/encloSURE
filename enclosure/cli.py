"""enclosure: make a board and its enclosure fit.

  enclosure read   base.step [--lid lid.step]                      what the enclosure offers a board
  enclosure limits base.step [--lid lid.step] -o board.kicad_pcb   a KiCad board to design inside
  enclosure fit    base.step board.step [--lid lid.step] -o out/   does the board fit? punch list + 3D view
  enclosure parts  --pcb board.kicad_pcb [--set J1=MPN] [-p parts.json]  real parts from DigiKey/Mouser
  enclosure sample -o folder                                       a sample enclosure, lid and board

Z is up (the way the lid comes off), millimetres. The board STEP is KiCad's export
(File > Export > STEP, or `kicad-cli pcb export step`), which names each part by reference.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import fit as fitmod
from . import geom, parts as partsmod, report, samples, shell


def _enclosure(args):
    base = geom.load(args.base)
    lid = geom.load(args.lid) if args.lid else None
    enc, _ = shell.read(base, lid)
    return base, lid, enc


def cmd_read(args):
    _, _, enc = _enclosure(args)
    return enc.to_json()


def cmd_limits(args):
    from . import kicad
    _, _, enc = _enclosure(args)
    return kicad.limits(enc, args.out, clearance=args.clearance, pcb_thickness=args.thickness)


def _placement(text: str | None):
    if not text:
        return None
    x, y, z, *rot = (float(v) for v in text.split(","))
    return fitmod.Placement(rot[0] if rot else 0.0, [x, y, z], "given")


def cmd_fit(args):
    base, lid, enc = _enclosure(args)
    board = geom.step_names(args.board)
    settings = fitmod.Settings(clearance=args.clearance, opening_margin=args.opening_margin,
                               max_setback=args.max_setback)
    placement = _placement(args.place)
    specs = partsmod.load(args.parts) if args.parts else {}
    footprints = partsmod.from_board(args.pcb) if args.pcb else None
    result = fitmod.check(enc, base, lid, board, settings, placement, specs, footprints)
    files = report.write(args.out, enc, result, base, lid, title=f"EncloSURE: {Path(args.board).stem}")
    j = result.to_json()
    return {"fits": j["fits"], "errors": j["errors"], "warnings": j["warnings"],
            "placement": j["placement"], "headroom": j["headroom"], "files": files}


def cmd_parts(args):
    """Merge the board's footprints (their MPN fields) and --set into parts.json, then fetch."""
    path = Path(args.parts)
    specs = partsmod.load(path)
    if args.pcb:
        for ref, fp in partsmod.from_board(args.pcb).items():
            if fp["mpn"] and ref not in specs:
                specs[ref] = partsmod.Part(ref=ref, mpn=fp["mpn"])
    for item in args.set or []:
        ref, _, mpn = item.partition("=")
        if not mpn:
            raise ValueError(f"--set {item}: give REF=MPN")
        specs.setdefault(ref, partsmod.Part(ref=ref)).mpn = mpn
    notes = []
    sources = partsmod.distributors()
    if not args.no_fetch:
        if not sources:
            notes.append("no distributor keys set: DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET, or MOUSER_API_KEY")
        else:
            folder = Path(args.datasheets) if args.datasheets else path.parent / "datasheets"
            for ref in sorted(specs):
                if args.only and ref not in args.only:
                    continue
                notes += partsmod.fetch(specs[ref], sources, folder)
    partsmod.save(path, specs)
    todo = [r for r, p in sorted(specs.items()) if p.body is None]
    cutouts = [r for r, p in sorted(specs.items()) if r.upper().startswith("J") and p.cutout is None]
    return {"parts_file": str(path), "parts": len(specs), "notes": notes,
            "need_body_from_datasheet": todo, "connectors_without_cutout": cutouts}


def cmd_sample(args):
    return samples.write(args.out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="enclosure", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def enclosure_args(p):
        p.add_argument("base", help="the enclosure's base (an open-topped shell), STEP")
        p.add_argument("--lid", help="its lid, STEP, in the same frame")

    p = sub.add_parser("read", help="what the enclosure offers a board")
    enclosure_args(p)
    p.set_defaults(fn=cmd_read)

    p = sub.add_parser("limits", help="write a KiCad board holding the enclosure's limits")
    enclosure_args(p)
    p.add_argument("-o", "--out", required=True, help="the .kicad_pcb to write")
    p.add_argument("--clearance", type=float, default=0.5, help="board edge to walls, mm")
    p.add_argument("--thickness", type=float, default=1.6, help="PCB thickness, mm")
    p.set_defaults(fn=cmd_limits)

    p = sub.add_parser("fit", help="check a board's STEP against the enclosure")
    enclosure_args(p)
    p.add_argument("board", help="the board with its parts, STEP (KiCad export)")
    p.add_argument("-o", "--out", default="fit", help="folder for report.json, punch_list.md, view.html")
    p.add_argument("--place", help="x,y,z[,rotation]: put the board here instead of on its standoffs")
    p.add_argument("--clearance", type=float, default=0.5, help="part and board edge to enclosure, mm")
    p.add_argument("--opening-margin", type=float, default=0.25, help="opening clear of a connector face, mm")
    p.add_argument("--max-setback", type=float, default=2.0, help="connector face to outer wall, mm")
    p.add_argument("--parts", help="parts.json: datasheet heights, bodies and connector cutouts")
    p.add_argument("--pcb", help="the .kicad_pcb, to place blocks for parts without 3D models")
    p.set_defaults(fn=cmd_fit)

    p = sub.add_parser("parts", help="collect the board's real parts into parts.json from DigiKey or Mouser")
    p.add_argument("-p", "--parts", default="parts.json", help="the parts file to update")
    p.add_argument("--pcb", help="a .kicad_pcb: take each footprint's MPN field")
    p.add_argument("--set", action="append", metavar="REF=MPN", help="a part's MPN (repeatable)")
    p.add_argument("--only", nargs="*", help="fetch only these references")
    p.add_argument("--datasheets", help="folder for downloaded datasheets (default: datasheets/ by parts.json)")
    p.add_argument("--no-fetch", action="store_true", help="only merge MPNs into parts.json")
    p.set_defaults(fn=cmd_parts)

    p = sub.add_parser("sample", help="write a sample enclosure, lid and board")
    p.add_argument("-o", "--out", default="sample")
    p.set_defaults(fn=cmd_sample)

    args = ap.parse_args(argv)
    try:
        result = args.fn(args)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2
    print(json.dumps(result, indent=2))
    if args.cmd == "fit":
        return 0 if result["fits"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
