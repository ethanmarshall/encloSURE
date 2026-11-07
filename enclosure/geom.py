"""Small geometry helpers over build123d / OpenCascade: loading STEP, distances, overlaps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from build123d import Compound, Shape, Solid, Vector, import_step
from OCP.BRepExtrema import BRepExtrema_DistShapeShape


@dataclass
class Named:
    """A solid with the name its STEP file gives it (a KiCad reference such as U1, a product
    name, or `solid-<n>` when the file names none)."""

    name: str
    shape: Shape


def load(path: str | Path) -> Shape:
    shape = import_step(str(path))
    if shape is None or not shape.solids():
        raise ValueError(f"{path}: no solids in this STEP file")
    return shape


def step_names(path: str | Path) -> list[Named]:
    """Each solid of a STEP file with its instance name where the file gives one (KiCad names
    each placed footprint's instance by its reference, J1, and its product by the model file),
    else its product name. Read through OpenCascade's XDE, which keeps both."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence
    from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from build123d import Solid

    doc = TDocStd_Document(TCollection_ExtendedString("doc"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(str(path)) != IFSelect_RetDone or not reader.Transfer(doc):
        raise ValueError(f"{path}: not a readable STEP file")
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    def name_of(label) -> str:
        attr = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
            return TCollection_AsciiString(attr.Get()).ToCString()
        return ""

    def usable(n: str) -> bool:
        return bool(n) and not n.startswith("=>")

    out: list[Named] = []

    def walk(label, loc: TopLoc_Location, inherited: str):
        if tool.IsAssembly_s(label):
            comps = TDF_LabelSequence()
            tool.GetComponents_s(label, comps)
            for i in range(1, comps.Length() + 1):
                comp = comps.Value(i)
                ref = TDF_Label()
                tool.GetReferredShape_s(comp, ref)
                own = name_of(comp)
                name = own if usable(own) else (inherited if usable(inherited) else name_of(ref))
                walk(ref, loc.Multiplied(tool.GetLocation_s(comp)), name)
            return
        shape = tool.GetShape_s(label)
        name = inherited if usable(inherited) else name_of(label)
        exp = TopExp_Explorer(shape, TopAbs_SOLID)
        while exp.More():
            solid = Solid(exp.Current().Moved(loc) if not loc.IsIdentity() else exp.Current())
            out.append(Named(name if usable(name) else f"solid-{len(out) + 1}", solid))
            exp.Next()

    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i), TopLoc_Location(), "")
    if not out:
        raise ValueError(f"{path}: no solids in this STEP file")
    return out


def named_solids(shape: Shape) -> list[Named]:
    """Each solid with the nearest label above it in the STEP's product tree."""
    out: list[Named] = []

    def walk(node: Shape, label: str):
        own = getattr(node, "label", "") or label
        children = list(getattr(node, "children", ()) or ())
        if children:
            for child in children:
                walk(child, own)
        else:
            for solid in node.solids():
                out.append(Named(own or f"solid-{len(out) + 1}", solid))

    walk(shape, "")
    if not out:  # a flat compound: no tree
        out = [Named(f"solid-{i + 1}", s) for i, s in enumerate(shape.solids())]
    return out


def distance(a: Shape, b: Shape) -> float:
    """The shortest distance between two shapes (0 when they touch or overlap)."""
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    d.Perform()
    return d.Value() if d.IsDone() else float("nan")


def overlap_volume(a: Shape, b: Shape) -> float:
    """The volume two solids share, mm^3 (0 when they only touch)."""
    try:
        common = a & b
    except Exception:
        return 0.0
    if common is None:
        return 0.0
    try:
        return sum(s.volume for s in common.solids())
    except Exception:
        return 0.0


def bbox(shape: Shape):
    b = shape.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z)


def as_compound(shapes) -> Compound:
    return Compound(children=list(shapes)) if not isinstance(shapes, Compound) else shapes


def vec(v) -> list[float]:
    v = Vector(v)
    return [round(v.X, 3), round(v.Y, 3), round(v.Z, 3)]
