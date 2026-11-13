"""The box as an Onshape custom feature: `enclosure box --format onshape` writes
`enclosure_box.fs`, a FeatureScript feature whose dialog holds the box's settings (yours as the
defaults). Paste it into a Feature Studio in your Onshape document, then insert "EncloSURE Box"
in any Part Studio: it builds the base and lid as two parts, and changing a number in its dialog
rebuilds them, with your own features after it kept.

The feature covers the size, walls, corner radius, screw / friction / no lid with its lip, the
lid screws' corner posts, board standoffs (a rectangle pattern), and round or rectangular
cutouts on any face. The rest (snap and slide lids, gaskets, vents, feet, keyholes, DIN clip,
labels, gussets, teardrops, chamfers, mounting ears) is in the STEP files only for now;
`feature_studio` reports which of those a box uses.
"""

from __future__ import annotations

from .box import SCREWS, BoxSpec, Cutout, _post_boss
from .presets import resolve

VERSION = 3112  # the FeatureScript library this was tested against

FACE_ENUM = {"-X": "LEFT", "+X": "RIGHT", "-Y": "FRONT", "+Y": "BACK", "lid": "LID", "floor": "FLOOR"}


def _mm(v: float) -> str:
    return f"{float(v):g} * millimeter"


def unsupported(spec: BoxSpec) -> list[str]:
    out = []
    if spec.lid in ("snap", "slide"):
        out.append(f"{spec.lid} lid (the feature makes a friction lid)")
    for name, on in (("gasket", spec.gasket), ("vents", spec.vents), ("feet", spec.feet),
                     ("keyholes", spec.keyholes), ("DIN clip", spec.din_rail), ("labels", spec.labels),
                     ("mounting ears", spec.flange), ("standoff gussets", spec.standoffs and spec.standoff_ribs),
                     ("bottom chamfer", spec.bottom_chamfer)):
        if on:
            out.append(name)
    if any(resolve(c)["shape"] == "round" and c.get("face") not in ("lid", "floor") for c in spec.cutouts) and spec.teardrop:
        out.append("teardrop holes")
    if any(resolve(c).get("radius") for c in spec.cutouts):
        out.append("rounded cutout corners")
    if spec.standoffs and not _is_rect(spec.standoffs):
        out.append("standoffs other than a rectangle pattern (the feature uses their bounding rectangle)")
    return out


def _is_rect(points) -> bool:
    xs = sorted({round(abs(p[0]), 6) for p in points})
    ys = sorted({round(abs(p[1]), 6) for p in points})
    return len(points) == 4 and len(xs) == 1 and len(ys) == 1


def feature_studio(spec: BoxSpec) -> tuple[str, list[str]]:
    """The Feature Studio text, and the settings it leaves out."""
    spec.check()
    L, W, H = spec.inner
    lid = {"screw": "SCREW", "friction": "FRICTION", "snap": "FRICTION", "slide": "NONE", "none": "NONE"}[spec.lid]
    d_post, depth_post = spec.hole(spec.lid_screw, spec.lid_screw_hole)
    clear, _, _, _, head = SCREWS[spec.lid_screw]
    if spec.standoffs:
        sx = max(abs(p[0]) for p in spec.standoffs) * 2
        sy = max(abs(p[1]) for p in spec.standoffs) * 2
    else:
        sx, sy = L * 0.8, W * 0.8
    d_so, depth_so = spec.hole(spec.standoff_screw, spec.standoff_hole)
    cutouts = []
    for raw in spec.cutouts:
        c = Cutout(**resolve(raw))
        w = c.size[0]
        h = c.size[1] if c.shape == "rect" else c.size[0]
        cutouts.append("{ \"face\" : EncFace.%s, \"shape\" : EncShape.%s, \"w\" : %s, \"h\" : %s, \"a\" : %s, \"b\" : %s }" % (
            FACE_ENUM[c.face], "ROUND" if c.shape == "round" else "RECT", _mm(w), _mm(h), _mm(c.at[0]), _mm(c.at[1])))
    defaults = {
        "length": _mm(L), "width": _mm(W), "height": _mm(H), "wall": _mm(spec.wall), "floor": _mm(spec.floor),
        "cornerRadius": _mm(spec.corner_radius), "lidType": f"EncLidType.{lid}", "lidThickness": _mm(spec.lid_thickness),
        "lip": _mm(spec.lip), "clearance": _mm(spec.fit_clearance), "postHole": _mm(d_post),
        "postHoleDepth": _mm(depth_post or 0), "lidScrewClearance": _mm(clear), "screwHead": _mm(head),
        "standoffs": "true" if spec.standoffs else "false", "standoffX": _mm(sx), "standoffY": _mm(sy),
        "standoffHeight": _mm(spec.standoff_height), "standoffHole": _mm(d_so),
        "standoffHoleDepth": _mm(depth_so or 0),
        "cutouts": "[" + ", ".join(cutouts) + "]",
    }
    text = TEMPLATE.replace("__VERSION__", str(VERSION)).replace(
        "__DEFAULTS__", ",\n        ".join(f'"{k}" : {v}' for k, v in defaults.items()))
    return text, unsupported(spec)


TEMPLATE = r'''FeatureScript __VERSION__;
import(path : "onshape/std/common.fs", version : "__VERSION__.0");

// EncloSURE Box: an enclosure base and lid from a few settings.
// Made by EncloSURE (github.com/ethanmarshall/encloSURE). Z up, the base's outside centred on
// the origin with its bottom at Z = 0; positions are measured from the centre of the inside.

const SIZE = { (millimeter) : [1, 100, 2000] } as LengthBoundSpec;
const THICK = { (millimeter) : [0.5, 2, 50] } as LengthBoundSpec;
const SMALL = { (millimeter) : [0, 0.2, 50] } as LengthBoundSpec;
const SIGNED = { (millimeter) : [-2000, 0, 2000] } as LengthBoundSpec;

export enum EncLidType
{
    annotation { "Name" : "Screw (corner posts)" }
    SCREW,
    annotation { "Name" : "Friction (press-in lip)" }
    FRICTION,
    annotation { "Name" : "None" }
    NONE
}

export enum EncFace
{
    annotation { "Name" : "Left (-X)" }
    LEFT,
    annotation { "Name" : "Right (+X)" }
    RIGHT,
    annotation { "Name" : "Front (-Y)" }
    FRONT,
    annotation { "Name" : "Back (+Y)" }
    BACK,
    annotation { "Name" : "Lid" }
    LID,
    annotation { "Name" : "Floor" }
    FLOOR
}

export enum EncShape
{
    annotation { "Name" : "Round" }
    ROUND,
    annotation { "Name" : "Rectangle" }
    RECT
}

annotation { "Feature Type Name" : "EncloSURE Box", "Feature Type Description" : "An enclosure base and lid from a few settings" }
export const enclosureBox = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Inside length (X)" }
        isLength(definition.length, SIZE);
        annotation { "Name" : "Inside width (Y)" }
        isLength(definition.width, SIZE);
        annotation { "Name" : "Inside height" }
        isLength(definition.height, SIZE);
        annotation { "Name" : "Wall" }
        isLength(definition.wall, THICK);
        annotation { "Name" : "Floor" }
        isLength(definition.floor, THICK);
        annotation { "Name" : "Outside corner radius" }
        isLength(definition.cornerRadius, SMALL);
        annotation { "Name" : "Lid" }
        definition.lidType is EncLidType;
        if (definition.lidType != EncLidType.NONE)
        {
            annotation { "Name" : "Lid thickness" }
            isLength(definition.lidThickness, THICK);
            annotation { "Name" : "Lip depth (0 for none)" }
            isLength(definition.lip, SMALL);
            annotation { "Name" : "Fit clearance per side" }
            isLength(definition.clearance, SMALL);
        }
        if (definition.lidType == EncLidType.SCREW)
        {
            annotation { "Name" : "Post hole (insert or pilot)" }
            isLength(definition.postHole, THICK);
            annotation { "Name" : "Post hole depth (0 for full)" }
            isLength(definition.postHoleDepth, SMALL);
            annotation { "Name" : "Lid screw clearance hole" }
            isLength(definition.lidScrewClearance, THICK);
            annotation { "Name" : "Screw head (counterbore)" }
            isLength(definition.screwHead, THICK);
        }
        annotation { "Name" : "Board standoffs" }
        definition.standoffs is boolean;
        if (definition.standoffs)
        {
            annotation { "Name" : "Standoff spacing X" }
            isLength(definition.standoffX, SIZE);
            annotation { "Name" : "Standoff spacing Y" }
            isLength(definition.standoffY, SIZE);
            annotation { "Name" : "Standoff height" }
            isLength(definition.standoffHeight, THICK);
            annotation { "Name" : "Standoff hole" }
            isLength(definition.standoffHole, THICK);
            annotation { "Name" : "Standoff hole depth (0 for full)" }
            isLength(definition.standoffHoleDepth, SMALL);
        }
        annotation { "Name" : "Cutouts", "Item name" : "Cutout", "Item label template" : "#face #shape" }
        definition.cutouts is array;
        for (var c in definition.cutouts)
        {
            annotation { "Name" : "Face" }
            c.face is EncFace;
            annotation { "Name" : "Shape" }
            c.shape is EncShape;
            annotation { "Name" : "Width (or diameter)" }
            isLength(c.w, THICK);
            annotation { "Name" : "Height" }
            isLength(c.h, THICK);
            annotation { "Name" : "Along (wall) or X (lid, floor)" }
            isLength(c.a, SIGNED);
            annotation { "Name" : "Height above floor (wall) or Y (lid, floor)" }
            isLength(c.b, SIGNED);
        }
    }
    {
        const L = definition.length;
        const W = definition.width;
        const H = definition.height;
        const t = definition.wall;
        const f = definition.floor;
        const oL = L + 2 * t;
        const oW = W + 2 * t;
        const top = f + H;
        const rOut = definition.cornerRadius;
        const rIn = max(rOut - t, 0 * millimeter);

        // The base: a rounded block, hollowed.
        const base = slab(context, id + "outer", oL, oW, 0 * millimeter, top, rOut);
        const cavity = slab(context, id + "cavity", L, W, f, top + 1 * millimeter, rIn);
        subtract(context, id + "hollow", base, cavity);

        var posts = [];
        var boss = 0 * millimeter;
        if (definition.lidType == EncLidType.SCREW)
        {
            boss = max(2.2 * definition.postHole, definition.postHole + 3.2 * millimeter);
            var i = 0;
            for (var sx in [-1, 1])
            {
                for (var sy in [-1, 1])
                {
                    const x = sx * (L / 2 - boss / 2);
                    const y = sy * (W / 2 - boss / 2);
                    fCylinder(context, id + ("post" ~ i), { "bottomCenter" : vector(x, y, f), "topCenter" : vector(x, y, top), "radius" : boss / 2 });
                    fCuboid(context, id + ("postback" ~ i), { "corner1" : vector(x, y, f), "corner2" : vector(x + sx * boss / 2, y + sy * boss / 2, top) });
                    add(context, id + ("postjoin" ~ i), base, qUnion([qCreatedBy(id + ("post" ~ i), EntityType.BODY), qCreatedBy(id + ("postback" ~ i), EntityType.BODY)]));
                    const depth = definition.postHoleDepth > 0 * millimeter ? definition.postHoleDepth : top - f - 1 * millimeter;
                    fCylinder(context, id + ("posthole" ~ i), { "bottomCenter" : vector(x, y, top - depth), "topCenter" : vector(x, y, top + 1 * millimeter), "radius" : definition.postHole / 2 });
                    subtract(context, id + ("postcut" ~ i), base, qCreatedBy(id + ("posthole" ~ i), EntityType.BODY));
                    posts = append(posts, [x, y]);
                    i += 1;
                }
            }
        }

        if (definition.standoffs)
        {
            const d = definition.standoffHole;
            const so = max(2.2 * d, d + 3.2 * millimeter);
            const h = definition.standoffHeight;
            var i = 0;
            for (var sx in [-1, 1])
            {
                for (var sy in [-1, 1])
                {
                    const x = sx * definition.standoffX / 2;
                    const y = sy * definition.standoffY / 2;
                    fCylinder(context, id + ("so" ~ i), { "bottomCenter" : vector(x, y, f - 0.01 * millimeter), "topCenter" : vector(x, y, f + h), "radius" : so / 2 });
                    add(context, id + ("sojoin" ~ i), base, qCreatedBy(id + ("so" ~ i), EntityType.BODY));
                    const depth = definition.standoffHoleDepth > 0 * millimeter ? min(definition.standoffHoleDepth, h + f - 0.6 * millimeter) : h;
                    fCylinder(context, id + ("sohole" ~ i), { "bottomCenter" : vector(x, y, f + h - depth), "topCenter" : vector(x, y, f + h + 1 * millimeter), "radius" : d / 2 });
                    subtract(context, id + ("socut" ~ i), base, qCreatedBy(id + ("sohole" ~ i), EntityType.BODY));
                    i += 1;
                }
            }
        }

        var lid = qNothing();
        if (definition.lidType != EncLidType.NONE)
        {
            const lt = definition.lidThickness;
            const c = definition.clearance;
            lid = slab(context, id + "lid", oL, oW, top, lt, rOut);
            if (definition.lip > 0 * millimeter)
            {
                const lip = slab(context, id + "lip", L - 2 * c, W - 2 * c, top - definition.lip, definition.lip, max(rIn - c, 0 * millimeter));
                const lipIn = slab(context, id + "lipin", L - 2 * c - 3.2 * millimeter, W - 2 * c - 3.2 * millimeter, top - definition.lip - 1 * millimeter, definition.lip + 1 * millimeter, max(rIn - c - 1.6 * millimeter, 0 * millimeter));
                subtract(context, id + "lipcut", lip, lipIn);
                var i = 0;
                for (var p in posts)
                {
                    const sx = p[0] > 0 * millimeter ? 1 : -1;
                    const sy = p[1] > 0 * millimeter ? 1 : -1;
                    fCuboid(context, id + ("lipclear" ~ i), { "corner1" : vector(p[0] - sx * (boss / 2 + c + 0.3 * millimeter), p[1] - sy * (boss / 2 + c + 0.3 * millimeter), top - definition.lip - 1 * millimeter), "corner2" : vector(p[0] + sx * boss, p[1] + sy * boss, top + 1 * millimeter) });
                    subtract(context, id + ("lipclearcut" ~ i), lip, qCreatedBy(id + ("lipclear" ~ i), EntityType.BODY));
                    i += 1;
                }
                add(context, id + "lipjoin", lid, lip);
            }
            var i = 0;
            for (var p in posts)
            {
                fCylinder(context, id + ("lidhole" ~ i), { "bottomCenter" : vector(p[0], p[1], top - 1 * millimeter), "topCenter" : vector(p[0], p[1], top + lt + 1 * millimeter), "radius" : definition.lidScrewClearance / 2 });
                subtract(context, id + ("lidholecut" ~ i), lid, qCreatedBy(id + ("lidhole" ~ i), EntityType.BODY));
                fCylinder(context, id + ("cbore" ~ i), { "bottomCenter" : vector(p[0], p[1], top + lt / 2), "topCenter" : vector(p[0], p[1], top + lt + 1 * millimeter), "radius" : definition.screwHead / 2 + 0.3 * millimeter });
                subtract(context, id + ("cborecut" ~ i), lid, qCreatedBy(id + ("cbore" ~ i), EntityType.BODY));
                i += 1;
            }
        }

        var n = 0;
        for (var c in definition.cutouts)
        {
            const tool = id + ("cut" ~ n);
            const w = c.w;
            const h = c.shape == EncShape.ROUND ? c.w : c.h;
            const deep = 4 * t + 2 * millimeter;
            var target = base;
            if (c.face == EncFace.LID || c.face == EncFace.FLOOR)
            {
                const z0 = c.face == EncFace.LID ? top - 5 * millimeter : -5 * millimeter;
                const z1 = c.face == EncFace.LID ? top + 50 * millimeter : f + 0.001 * millimeter;
                if (c.face == EncFace.LID)
                    target = lid;
                if (c.shape == EncShape.ROUND)
                    fCylinder(context, tool, { "bottomCenter" : vector(c.a, c.b, z0), "topCenter" : vector(c.a, c.b, z1), "radius" : w / 2 });
                else
                    fCuboid(context, tool, { "corner1" : vector(c.a - w / 2, c.b - h / 2, z0), "corner2" : vector(c.a + w / 2, c.b + h / 2, z1) });
            }
            else
            {
                const z = f + c.b;
                var p0;
                var p1;
                var a0;
                var a1;
                if (c.face == EncFace.LEFT || c.face == EncFace.RIGHT)
                {
                    const s = c.face == EncFace.LEFT ? -1 : 1;
                    p0 = vector(s * (oL / 2) - deep / 2, c.a, z);
                    p1 = vector(s * (oL / 2) + deep / 2, c.a, z);
                    a0 = vector(s * (oL / 2) - deep / 2, c.a - w / 2, z - h / 2);
                    a1 = vector(s * (oL / 2) + deep / 2, c.a + w / 2, z + h / 2);
                }
                else
                {
                    const s = c.face == EncFace.FRONT ? -1 : 1;
                    p0 = vector(c.a, s * (oW / 2) - deep / 2, z);
                    p1 = vector(c.a, s * (oW / 2) + deep / 2, z);
                    a0 = vector(c.a - w / 2, s * (oW / 2) - deep / 2, z - h / 2);
                    a1 = vector(c.a + w / 2, s * (oW / 2) + deep / 2, z + h / 2);
                }
                if (c.shape == EncShape.ROUND)
                    fCylinder(context, tool, { "bottomCenter" : p0, "topCenter" : p1, "radius" : w / 2 });
                else
                    fCuboid(context, tool, { "corner1" : a0, "corner2" : a1 });
            }
            subtract(context, id + ("cutdo" ~ n), target, qCreatedBy(tool, EntityType.BODY));
            n += 1;
        }

        setProperty(context, { "entities" : base, "propertyType" : PropertyType.NAME, "value" : "Base" });
        if (definition.lidType != EncLidType.NONE)
            setProperty(context, { "entities" : lid, "propertyType" : PropertyType.NAME, "value" : "Lid" });
    }, {
        __DEFAULTS__
    });

// A block centred on the Z axis from z0 up by h, its vertical edges rounded r.
function slab(context is Context, id is Id, L is ValueWithUnits, W is ValueWithUnits, z0 is ValueWithUnits, h is ValueWithUnits, r is ValueWithUnits) returns Query
{
    fCuboid(context, id, { "corner1" : vector(-L / 2, -W / 2, z0), "corner2" : vector(L / 2, W / 2, z0 + h) });
    const r2 = min(r, min(L, W) / 2 - 0.01 * millimeter);
    if (r2 > 0.05 * millimeter)
        opFillet(context, id + "round", { "entities" : qParallelEdges(qCreatedBy(id, EntityType.EDGE), Z_DIRECTION), "radius" : r2 });
    return qCreatedBy(id, EntityType.BODY);
}

function subtract(context is Context, id is Id, target is Query, tools is Query)
{
    opBoolean(context, id, { "tools" : tools, "targets" : target, "operationType" : BooleanOperationType.SUBTRACTION });
}

function add(context is Context, id is Id, target is Query, tools is Query)
{
    opBoolean(context, id, { "tools" : qUnion([target, tools]), "operationType" : BooleanOperationType.UNION });
}
'''
