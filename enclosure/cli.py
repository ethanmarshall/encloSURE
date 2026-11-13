"""enclosure: make a board and its enclosure fit.

  enclosure read   base.step [--lid lid.step]                      what the enclosure offers a board
  enclosure limits base.step [--lid lid.step] -o board.kicad_pcb   a KiCad board to design inside
  enclosure frompcb board.step -o box                               a box around a finished board
  enclosure fix    board.kicad_pcb fit/report.json -o fixed.kicad_pcb   apply fit's moves
  enclosure fit    base.step board.step [--lid lid.step] -o out/   does the board fit? punch list + 3D view
  enclosure parts  --pcb board.kicad_pcb [--set J1=MPN] [-p parts.json]  real parts from DigiKey/Mouser
  enclosure box    --size 100x60x40 --lid screw [...] -o folder    a quick enclosure, no board needed
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
from . import box as boxmod, geom, parts as partsmod, report, samples, shell


FORMATS = {"step": ("step",), "onshape": ("onshape",), "solidworks": ("step", "solidworks"),
           "both": ("step", "onshape"), "all": ("step", "onshape", "solidworks")}


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
    base, _, enc = _enclosure(args)
    return kicad.limits(enc, args.out, clearance=args.clearance, pcb_thickness=args.thickness, base=base)


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
    from . import tolerance
    tol = tolerance.stack(enc, result, tolerance.Tolerances(material=args.material))
    (Path(args.out) / "tolerances.json").write_text(json.dumps(tol, indent=2) + "\n")
    files["tolerances"] = str(Path(args.out) / "tolerances.json")
    return {"fits": j["fits"], "errors": j["errors"], "warnings": j["warnings"],
            "placement": j["placement"], "headroom": j["headroom"], "files": files,
            "worst_case": [f"{f['subject']}: {f['message']}" for f in tol["findings"]]}


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


def cmd_box(args):
    spec = boxmod.load(args.load) if args.load else boxmod.BoxSpec()
    if args.size:
        try:
            spec.size = [float(v) for v in args.size.lower().split("x")]
        except ValueError:
            raise ValueError("--size: L x W x H in mm, e.g. 100x60x40") from None
    if args.outer:
        spec.size_is = "outer"
    for flag, name in (("wall", "wall"), ("floor", "floor"), ("radius", "corner_radius"), ("lid", "lid"),
                       ("lid_thickness", "lid_thickness"), ("lid_screw", "lid_screw"),
                       ("lid_screw_hole", "lid_screw_hole"), ("lip", "lip"), ("clearance", "fit_clearance"),
                       ("standoff_height", "standoff_height"), ("standoff_screw", "standoff_screw"),
                       ("standoff_hole", "standoff_hole"), ("insert_hole", "insert_hole"),
                       ("insert_depth", "insert_depth"), ("flange", "flange"), ("flange_screw", "flange_screw"),
                       ("bottom_chamfer", "bottom_chamfer"), ("gasket", "gasket"), ("feet", "feet"),
                       ("feet_depth", "feet_depth"), ("keyholes", "keyholes"), ("keyhole_spacing", "keyhole_spacing")):
        value = getattr(args, flag)
        if value is not None:
            setattr(spec, name, value)
    if args.standoffs:
        spec.standoffs = boxmod.standoff_pattern(args.standoffs)
    if args.cutout:
        spec.cutouts = [{k: v for k, v in boxmod.asdict(boxmod.Cutout.parse(c)).items() if v is not None}
                        for c in args.cutout]
    if args.vent:
        spec.vents = [boxmod.parse_vent(v) for v in args.vent]
    if args.label:
        spec.labels = [boxmod.parse_label(t) for t in args.label]
    for flag, name in (("no_teardrop", "teardrop"), ("no_ribs", "standoff_ribs")):
        if getattr(args, flag):
            setattr(spec, name, False)
    if args.din_rail:
        spec.din_rail = True
    formats = FORMATS[args.format]
    return boxmod.write(spec, args.out, stl=not args.no_stl, formats=formats)


def cmd_presets(args):
    from .presets import PRESETS
    return {name: {"shape": shape, "size": size, "radius": radius, "source": source}
            for name, (shape, size, radius, source) in PRESETS.items()}


def cmd_stock(args):
    from . import stock
    cutouts = [{k: v for k, v in boxmod.asdict(boxmod.Cutout.parse(c)).items() if v is not None}
               for c in (args.cutout or [])]
    if not cutouts:
        raise ValueError("give at least one --cutout")
    return stock.run(args.step, cutouts, args.out, lid_path=args.lid, teardrop=args.teardrop)


def cmd_assembly(args):
    from . import assembly
    spec = boxmod.load(args.box)
    return assembly.make(spec, args.out, args.board, args.standard)


def cmd_describe(args):
    from . import describe
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    r = describe.make(" ".join(args.text), out / "board.kicad_pcb", pcb=args.pcb)
    files = boxmod.write(r["spec"], out, stl=not args.no_stl)
    return {"assumed": r["notes"], "inner": files["inner"], "outer": files["outer"], "checks": files["checks"],
            "files": {**files["files"], "kicad_board": str(out / "board.kicad_pcb")},
            "next": "adjust box.json (or the page's form) and rebuild with `enclosure box --from`"}


def cmd_autofit(args):
    from . import autofit
    base, lid, enc = _enclosure(args)
    settings = fitmod.Settings(clearance=args.clearance)
    specs = partsmod.load(args.parts) if args.parts else {}
    return autofit.run(enc, base, lid, args.pcb, args.out, args.rounds, settings, specs)


def cmd_drawing(args):
    from . import drawing
    title = {}
    for k in ("title", "part_number", "material", "drawn_by", "company"):
        v = getattr(args, k)
        if v:
            title[k] = v
    return drawing.make(args.folder, args.out, args.standard, title, args.formats)


def cmd_coupon(args):
    from . import coupon
    gaps = [float(g) for g in args.gaps.split(",")] if args.gaps else coupon.GAPS
    return coupon.write(args.out, gaps)


def cmd_fix(args):
    from . import kicad
    findings = json.loads(Path(args.report).read_text())["findings"]
    moves = kicad.moves_from_fit(findings)
    if not moves:
        return {"moved": [], "note": "the report asks for no footprint moves"}
    done = kicad.move_footprints(args.pcb, moves, args.out)
    left = [f["subject"] + ": " + f["message"] for f in findings if f["severity"] == "error" and not f.get("kicad_move")]
    return {"file": args.out, "moved": done, "not_fixed_by_moving": left,
            "next": "re-export the board's STEP from KiCad and run fit again"}


def cmd_frompcb(args):
    from . import frompcb
    st = frompcb.Settings(wall=args.wall, lid=args.lid, edge_gap=args.edge_gap, standoff_height=args.standoff_height,
                          headroom=args.headroom)
    specs = partsmod.load(args.parts) if args.parts else {}
    footprints = partsmod.from_board(args.pcb) if args.pcb else None
    if str(args.board).lower().endswith(".kicad_pcb"):
        r = frompcb.from_kicad(args.board, st, specs)
    else:
        r = frompcb.make(args.board, st, specs, footprints)
    out = Path(args.out)
    files = boxmod.write(r["spec"], out, stl=not args.no_stl, formats=FORMATS[args.format])
    rep = report.write(out / "fit", r["enclosure"], r["fit"], r["made"]["base"], r["made"]["lid"],
                       title=f"EncloSURE: box for {Path(args.board).stem}")
    j = r["fit"].to_json()
    return {"inner": files["inner"], "outer": files["outer"], "fits": j["fits"], "errors": j["errors"],
            "warnings": j["warnings"], "notes": r["notes"], "checks": files["checks"],
            "files": {**files["files"], **{f"fit_{k}": v for k, v in rep.items()}}}


def cmd_web(args):
    try:
        from .web import serve
    except ImportError:
        raise RuntimeError('the web page needs its extras: pip install "enclosure-sure[web]"') from None
    print(f"EncloSURE at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    serve(args.host, args.port)
    return None


def cmd_sample(args):
    return samples.write(args.out)


def _value(text: str):
    low = text.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    try:
        return float(text)
    except ValueError:
        return text


def cmd_part(args):
    from . import hardware
    if args.kind == "list":
        return {k: {"label": v["label"], "settings": {f["name"]: f["default"] for f in v["fields"]},
                    "modes": v["modes"], "material": v["material"]} for k, v in hardware.catalog()["kinds"].items()}
    params = {}
    for item in args.settings:
        name, eq, val = item.partition("=")
        if not eq:
            raise ValueError(f"{item!r}: write settings as name=value")
        params[name.strip()] = _value(val.strip())
    r = hardware.write(args.kind, args.out or args.kind, stl=not args.no_stl, **params)
    return {"ok": True, "part": r["label"], "size": r["size"], "files": r["files"], "notes": r["notes"],
            "checks": r["checks"], "info": r["info"], "buy": r["buy"]}


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
    p.add_argument("--material", default="PETG", choices=("PLA", "PETG", "ABS", "ASA"), help="for the shrink in the worst-case gaps")
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

    p = sub.add_parser("box", help="make a quick enclosure from a size and a few choices",
                       description=boxmod.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-o", "--out", default="box", help="folder for base.step, lid.step, assembly.step, STLs, box.json")
    p.add_argument("--from", dest="load", help="start from a saved box.json; other flags change it")
    p.add_argument("--size", help="L x W x H, mm: the space inside (or outside with --outer)")
    p.add_argument("--outer", action="store_true", help="--size is the outside")
    p.add_argument("--wall", type=float)
    p.add_argument("--floor", type=float)
    p.add_argument("--radius", type=float, help="outside corner radius, 0 for square")
    p.add_argument("--lid", choices=boxmod.LIDS)
    p.add_argument("--lid-thickness", type=float)
    p.add_argument("--lid-screw", choices=list(boxmod.SCREWS))
    p.add_argument("--lid-screw-hole", choices=["tap", "insert", "clearance"],
                   help="the corner posts' holes: thread-forming pilot, heat-set insert, or through for a nut")
    p.add_argument("--lip", type=float, help="the lid's lip depth, 0 for none")
    p.add_argument("--clearance", type=float, help="gap between mating parts per side (printing: 0.2)")
    p.add_argument("--standoffs", help="board standoffs from the inside centre: rect:80x50, or x,y;x,y")
    p.add_argument("--standoff-height", type=float)
    p.add_argument("--standoff-screw", choices=list(boxmod.SCREWS))
    p.add_argument("--standoff-hole", choices=["tap", "insert", "clearance"])
    p.add_argument("--insert-hole", type=float, help="heat-set insert hole diameter (your insert's datasheet)")
    p.add_argument("--insert-depth", type=float)
    p.add_argument("--cutout", action="append",
                   help="FACE:rect:WxH[rR]@a,b, FACE:round:D@a,b, or FACE:PRESET@a,b (enclosure presets); FACE left right front back lid floor "
                        "(-X +X -Y +Y; write --cutout=-X:... for those); on a wall a,b "
                        "is along the wall from its centre and height above the inside floor (repeatable)")
    p.add_argument("--flange", type=float, help="mounting ears this far out from the ends, mm")
    p.add_argument("--flange-screw", choices=list(boxmod.SCREWS))
    p.add_argument("--format", choices=["step", "onshape", "solidworks", "both", "all"], default="step",
                   help="STEP files (and STL), an Onshape custom feature (enclosure_box.fs), or both")
    p.add_argument("--no-stl", action="store_true")
    p.add_argument("--no-teardrop", action="store_true", help="plain round holes in walls")
    p.add_argument("--bottom-chamfer", type=float, help="against first-layer squish, mm (0 for none)")
    p.add_argument("--no-ribs", action="store_true", help="standoffs without gussets")
    p.add_argument("--gasket", type=float, help="O-ring cord diameter for a sealed screw lid, mm")
    p.add_argument("--vent", action="append", help="FACE:WxH@a,b[:slot[:pitch]]: slots filling an area (repeatable)")
    p.add_argument("--feet", type=float, help="rubber foot diameter: four recesses under the floor")
    p.add_argument("--feet-depth", type=float)
    p.add_argument("--keyholes", choices=list(boxmod.SCREWS), help="two keyholes in the floor for hanging")
    p.add_argument("--keyhole-spacing", type=float)
    p.add_argument("--din-rail", action="store_true", help="a TS35 DIN rail clip under the floor")
    p.add_argument("--label", action="append", help="FACE:TEXT@a,b[:size[:depth]]; depth < 0 recessed (repeatable)")
    p.set_defaults(fn=cmd_box)

    p = sub.add_parser("presets", help="the named cutouts (--cutout left:usb-c@0,9) and their sources")
    p.set_defaults(fn=cmd_presets)

    from . import stock as stockmod
    p = sub.add_parser("stock", help="cutouts and 1:1 drilling templates for a bought box (Hammond 1590...)",
                       description=stockmod.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", help="the maker's STEP of the box, opening up (+Z); may hold the lid too")
    p.add_argument("--lid", help="the lid's STEP, if it is a separate file")
    p.add_argument("--cutout", action="append", help="as for `enclosure box --cutout` (repeatable)")
    p.add_argument("--teardrop", action="store_true", help="teardrop wall holes (for a printed box)")
    p.add_argument("-o", "--out", default="stock", help="folder for base.step, lid.step, drill_templates.pdf, holes.json")
    p.set_defaults(fn=cmd_stock)

    from . import assembly as assemblymod
    p = sub.add_parser("assembly", help="an exploded assembly drawing with a parts list (uses draftwright)",
                       description=assemblymod.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("box", help="the box's box.json")
    p.add_argument("--board", help="the board's STEP from KiCad (else a plain plate stands in)")
    p.add_argument("--standard", default="asme", choices=("asme", "iso"))
    p.add_argument("-o", "--out", default="assembly")
    p.set_defaults(fn=cmd_assembly)

    from . import describe as describemod
    p = sub.add_parser("describe", help="a first box and KiCad board from a few words",
                       description=describemod.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("text", nargs="+", help='e.g. "Arduino Uno, USB-C, two buttons, OLED, wall-mounted"')
    p.add_argument("--pcb", help="your .kicad_pcb: the box is made round it, openings at its connectors; the words add the rest")
    p.add_argument("--no-stl", action="store_true")
    p.add_argument("-o", "--out", default="described")
    p.set_defaults(fn=cmd_describe)

    from . import autofit as autofitmod
    p = sub.add_parser("autofit", help="check, fix and re-export with KiCad until the board fits",
                       description=autofitmod.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("base"); p.add_argument("pcb", help="the board's .kicad_pcb (left unchanged)")
    p.add_argument("--lid"); p.add_argument("--parts"); p.add_argument("--clearance", type=float, default=0.5)
    p.add_argument("--rounds", type=int, default=4)
    p.add_argument("-o", "--out", default="autofit")
    p.set_defaults(fn=cmd_autofit)

    from . import drawing as drawingmod
    p = sub.add_parser("drawing", help="ASME or ISO drawings of a box's parts (uses draftwright)",
                       description=drawingmod.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folder", help="a folder with base.step and lid.step (from box, frompcb or stock)")
    p.add_argument("--standard", default="asme", choices=("asme", "iso"), help="asme: inches, Y14.5; iso: mm")
    p.add_argument("--title"); p.add_argument("--part-number"); p.add_argument("--material")
    p.add_argument("--drawn-by"); p.add_argument("--company")
    p.add_argument("--formats", default="pdf,svg")
    p.add_argument("-o", "--out", default="drawings")
    p.set_defaults(fn=cmd_drawing)

    from . import coupon as couponmod
    p = sub.add_parser("coupon", help="a fit test print to find your printer's lid gap",
                       description=couponmod.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gaps", help="gaps per side to try, mm, comma separated (default 0.10 to 0.35)")
    p.add_argument("-o", "--out", default="coupon")
    p.set_defaults(fn=cmd_coupon)

    p = sub.add_parser("fix", help="apply a fit report's KiCad moves to the .kicad_pcb")
    p.add_argument("pcb", help="the .kicad_pcb that was checked")
    p.add_argument("report", help="fit/report.json")
    p.add_argument("-o", "--out", required=True, help="the fixed .kicad_pcb to write (the original is left alone)")
    p.set_defaults(fn=cmd_fix)

    p = sub.add_parser("frompcb", help="a box around a board, from KiCad's STEP export",
                       description=__import__("enclosure.frompcb", fromlist=["x"]).__doc__,
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("board", help="the board's STEP from KiCad (File > Export > STEP, with 3D models), or the "
                   ".kicad_pcb itself (outline, holes and courtyards; heights from parts.json or typical ones)")
    p.add_argument("--pcb", help="the .kicad_pcb, to check parts that have no 3D model")
    p.add_argument("--parts", help="parts.json: datasheet panel cutouts are used for openings")
    p.add_argument("--lid", default="screw", choices=boxmod.LIDS)
    p.add_argument("--wall", type=float, default=2.0)
    p.add_argument("--edge-gap", type=float, default=1.0, help="board edge to the walls where nothing pokes out (mm)")
    p.add_argument("--standoff-height", type=float, default=5.0)
    p.add_argument("--headroom", type=float, default=2.0, help="above the tallest part (mm)")
    p.add_argument("--format", default="step", choices=("step", "onshape", "solidworks", "both", "all"))
    p.add_argument("--no-stl", action="store_true")
    p.add_argument("-o", "--out", default="box", help="folder for the box files and fit/ report")
    p.set_defaults(fn=cmd_frompcb)

    p = sub.add_parser("web", help="the quick box and bought-box tools as a web page with a 3D preview")
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to let other computers on your network in")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=cmd_web)

    p = sub.add_parser("part", help="a screw, nut, washer, spacer, spring or clip, as STEP and STL",
                       description="Settings as name=value: enclosure part screw size=M3 length=12 type=button; "
                                   "add mode=print for a part to 3D print (threads modelled with clearance=0.2). "
                                   "enclosure part list shows every part and its settings.")
    p.add_argument("kind", help="screw, nut, washer, spacer, insert, compression_spring, extension_spring, "
                                "torsion_spring, snap_hook, cable_clip, tie_mount, board_clip, din_clip, or list")
    p.add_argument("settings", nargs="*", help="name=value")
    p.add_argument("--no-stl", action="store_true")
    p.add_argument("-o", "--out", default=None, help="folder (default: the part's name)")
    p.set_defaults(fn=cmd_part)

    p = sub.add_parser("sample", help="write a sample enclosure, lid and board")
    p.add_argument("-o", "--out", default="sample")
    p.set_defaults(fn=cmd_sample)

    args = ap.parse_args(argv)
    try:
        result = args.fn(args)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2
    if result is None:
        return 0
    print(json.dumps(result, indent=2))
    if args.cmd == "fit":
        return 0 if result["fits"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
