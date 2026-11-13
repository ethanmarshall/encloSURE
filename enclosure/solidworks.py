"""The box as a SolidWorks macro: `enclosure_box.swb`, run with Tools > Macro > Run (pick the file;
"SW VBA Macros" or all files). It makes a new part and builds the box as ordinary SolidWorks features
you can edit: the outside block with its corners filleted, a shell for the inside, the corner posts
and their holes, board standoffs and their holes, the lid as a second body, and the cutouts in the
walls, lid and floor. Each feature is named (Box, Corners, Inside, Posts, ...) and its sizes are its
own dimensions, so double-click a feature to change it.

SolidWorks is Y up: the box's height runs along Y and its depth along Z (the box's +Y is SolidWorks'
-Z). The macro builds the core of the box; extras (vents, labels, gaskets, keyholes and so on) are
in the STEP, and the macro lists what it left out.

Written for the SolidWorks API without SolidWorks to try it on: if a step fails on your version,
the macro stops with a message saying which.
"""

from __future__ import annotations

from .box import SCREWS, BoxSpec, Cutout, _post_boss, face_name
from .presets import resolve

LEFT_OUT = ("vents", "labels", "gasket", "keyholes", "din_rail", "feet", "windows", "card_slots", "batteries",
            "tie_points", "cable_notches", "light_pipes", "lid_standoffs", "flange")


def _m(mm: float) -> str:
    return f"{mm / 1000:.6f}"


def macro(spec: BoxSpec) -> tuple[str, list[str]]:
    spec.check()
    L, W, H = spec.inner
    t, f = spec.wall, spec.floor
    oL, oW = L + 2 * t, W + 2 * t
    top = f + H
    skipped = [k for k in LEFT_OUT if getattr(spec, k)]
    if spec.lid in ("snap", "hinge", "slide", "clamshell"):
        skipped.append(f"{spec.lid} lid (the macro makes a flat lid)")
    if spec.lip and spec.lid in ("screw", "friction", "snap", "hinge"):
        skipped.append("the lid's lip")
    if spec.floor != spec.wall:
        skipped.append(f"a {spec.floor:g} mm floor (the shell makes it {spec.wall:g} mm, like the walls)")
    if spec.teardrop:
        skipped.append("teardrop holes")
    b = []
    a = b.append
    a("' EncloSURE box: a SolidWorks macro (Tools > Macro > Run). Sizes in metres, as the API takes them.")
    a(f"' Inside {L:g} x {W:g} x {H:g} mm, wall {t:g} mm, lid {spec.lid}.")
    a("Dim swApp As Object")
    a("Dim Part As Object")
    a("")
    a("Sub Fail(what As String)")
    a('    MsgBox "EncloSURE: the macro stopped at " & what & ". Send this message to whoever made the macro.", vbExclamation')
    a("    End")
    a("End Sub")
    a("")
    a("Function Plane(baseName As String, d As Double, flip As Boolean) As Object")
    a("    Dim opt As Long")
    a("    Part.ClearSelection2 True")
    a('    Part.Extension.SelectByID2 baseName, "PLANE", 0, 0, 0, False, 0, Nothing, 0')
    a("    opt = 8")
    a("    If flip Then opt = 8 + 256")
    a("    Set Plane = Part.FeatureManager.InsertRefPlane(opt, d, 0, 0, 0, 0)")
    a('    If Plane Is Nothing Then Fail "a reference plane " & d & " m from " & baseName')
    a("End Function")
    a("")
    a("Sub StartSketch(pl As Object)")
    a("    Part.ClearSelection2 True")
    a("    pl.Select2 False, 0")
    a("    Part.SketchManager.InsertSketch True")
    a("End Sub")
    a("")
    a("Sub EndSketch()")
    a("    Part.SketchManager.InsertSketch True")
    a("End Sub")
    a("")
    a("Function Boss(depth As Double, mergeIt As Boolean, nm As String) As Object")
    a("    Set Boss = Part.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, depth, 0, False, False, False, False, 0, 0, False, False, False, False, mergeIt, True, True, 0, 0, False)")
    a('    If Boss Is Nothing Then Fail "the extrusion " & nm')
    a("    Boss.Name = nm")
    a("End Function")
    a("")
    a("Function Cut(depth As Double, flipIt As Boolean, nm As String) As Object")
    a("    Set Cut = Part.FeatureManager.FeatureCut4(True, flipIt, False, 0, 0, depth, 0, False, False, False, False, 0, 0, False, False, False, False, False, True, True, True, True, False, 0, 0, False, False)")
    a('    If Cut Is Nothing Then Fail "the cut " & nm')
    a("    Cut.Name = nm")
    a("End Function")
    a("")
    a("Sub Circ(x As Double, y As Double, r As Double)")
    a("    Part.SketchManager.CreateCircleByRadius x, y, 0, r")
    a("End Sub")
    a("")
    a("Sub Rect(x As Double, y As Double, w As Double, h As Double)")
    a("    Part.SketchManager.CreateCenterRectangle x, y, 0, x + w / 2, y + h / 2, 0")
    a("End Sub")
    a("")
    a("Sub main()")
    a("    Dim pl As Object, f As Object, ok As Boolean")
    a("    Dim radiiArray0 As Variant, setBackArray0 As Variant, pointRadiusArray0 As Variant")
    a("    Set swApp = Application.SldWorks")
    a("    Set Part = swApp.NewDocument(swApp.GetUserPreferenceStringValue(8), 0, 0, 0)")
    a('    If Part Is Nothing Then Fail "making a new part (set a default part template in Options)"')
    a("    Part.SketchManager.AddToDB = True")
    a("")
    a("    ' The outside block, from the Top plane up.")
    a("    Part.ClearSelection2 True")
    a('    Part.Extension.SelectByID2 "Top Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0')
    a("    Part.SketchManager.InsertSketch True")
    a(f"    Rect 0, 0, {_m(oL)}, {_m(oW)}")
    a("    EndSketch")
    a(f'    Boss {_m(top)}, True, "Box"')
    if spec.corner_radius > 0.05:
        a("")
        a("    ' The four upright corners rounded.")
        a("    Part.ClearSelection2 True")
        for sx in (-1, 1):
            for sz in (-1, 1):
                a(f'    Part.Extension.SelectByID2 "", "EDGE", {_m(sx * oL / 2)}, {_m(top / 2)}, {_m(sz * oW / 2)}, True, 1, Nothing, 0')
        a(f"    Part.FeatureManager.FeatureFillet 195, {_m(min(spec.corner_radius, min(oL, oW) / 2 - 0.01))}, 0, 0, radiiArray0, setBackArray0, pointRadiusArray0")
        a("    Set f = Part.FeatureByPositionReverse(0)")
        a('    If Not f Is Nothing Then f.Name = "Corners"')
    a("")
    a("    ' The inside: shell the block, open at the top.")
    a("    Part.ClearSelection2 True")
    a(f'    ok = Part.Extension.SelectByID2("", "FACE", 0, {_m(top)}, 0, False, 0, Nothing, 0)')
    a('    If Not ok Then Fail "selecting the top face for the shell"')
    a(f"    Part.InsertFeatureShell {_m(t)}, False")
    a("    Set f = Part.FeatureByPositionReverse(0)")
    a('    If Not f Is Nothing Then f.Name = "Inside"')
    posts = []
    if spec.lid == "screw":
        d, depth = spec.hole(spec.lid_screw, spec.lid_screw_hole)
        boss = _post_boss(spec, d)
        posts = [(sx * (L / 2 - boss / 2), sy * (W / 2 - boss / 2)) for sx in (-1, 1) for sy in (-1, 1)]
        a("")
        a(f"    ' Corner posts for the lid's {spec.lid_screw} screws, and their {spec.lid_screw_hole} holes.")
        a(f"    Set pl = Plane(\"Top Plane\", {_m(t)}, False)")
        a("    StartSketch pl")
        for x, y in posts:
            a(f"    Circ {_m(x)}, {_m(y)}, {_m(boss / 2)}")
        a("    EndSketch")
        a(f'    Boss {_m(top - t)}, True, "Posts"')
        a(f"    Set pl = Plane(\"Top Plane\", {_m(top + 1)}, False)")
        a("    StartSketch pl")
        for x, y in posts:
            a(f"    Circ {_m(x)}, {_m(y)}, {_m(d / 2)}")
        a("    EndSketch")
        a(f'    Cut {_m((depth or top - t - 1) + 1)}, False, "Post holes"')
    if spec.standoffs:
        d, depth = spec.hole(spec.standoff_screw, spec.standoff_hole if spec.standoff_hole != "pin" else "insert")
        so = _post_boss(spec, d)
        h = spec.standoff_height
        a("")
        a(f"    ' Board standoffs, {h:g} mm tall, with {spec.standoff_screw} holes.")
        a(f"    Set pl = Plane(\"Top Plane\", {_m(t)}, False)")
        a("    StartSketch pl")
        for x, y in spec.standoffs:
            a(f"    Circ {_m(x)}, {_m(y)}, {_m(so / 2)}")
        a("    EndSketch")
        a(f'    Boss {_m(h)}, True, "Standoffs"')
        a(f"    Set pl = Plane(\"Top Plane\", {_m(t + h + 1)}, False)")
        a("    StartSketch pl")
        for x, y in spec.standoffs:
            a(f"    Circ {_m(x)}, {_m(y)}, {_m(d / 2)}")
        a("    EndSketch")
        a(f'    Cut {_m(min(depth or h, h + t - 0.6) + 1)}, False, "Standoff holes"')
    lid = spec.lid in ("screw", "friction", "snap", "hinge", "clamshell")
    if lid:
        lt = spec.lid_thickness
        a("")
        a("    ' The lid, a second body on top.")
        a(f"    Set pl = Plane(\"Top Plane\", {_m(top)}, False)")
        a("    StartSketch pl")
        a(f"    Rect 0, 0, {_m(oL)}, {_m(oW)}")
        a("    EndSketch")
        a(f'    Boss {_m(lt)}, False, "Lid"')
        if posts:
            clear, *_, head = SCREWS[spec.lid_screw]
            a(f"    Set pl = Plane(\"Top Plane\", {_m(top + lt + 1)}, False)")
            a("    StartSketch pl")
            for x, y in posts:
                a(f"    Circ {_m(x)}, {_m(y)}, {_m(clear / 2)}")
            a("    EndSketch")
            a(f'    Cut {_m(lt + 1)}, False, "Lid screw holes"')
    # Cutouts.
    n = 0
    for raw in spec.cutouts:
        c = Cutout(**resolve(raw))
        face = face_name(c.face)
        w = c.size[0]
        hh = c.size[1] if c.shape == "rect" else c.size[0]
        n += 1
        a("")
        a(f"    ' Cutout {n}: {c.preset or c.shape} on {face}.")
        if face in ("lid", "floor"):
            if face == "lid" and not lid:
                continue
            if face == "lid":
                a(f"    Set pl = Plane(\"Top Plane\", {_m(top + spec.lid_thickness + 1)}, False)")
                cut = f"{_m(spec.lid_thickness + 1.5)}, False"
            else:
                a(f"    Set pl = Plane(\"Top Plane\", {_m(1)}, True)")
                cut = f"{_m(t + 1.5)}, True"
            sx, sy = c.at[0], c.at[1]
        else:
            # Front plane (XY) for the -Y and +Y walls, Right plane (YZ) for -X and +X; a plane just outside
            # the wall, then a cut back through it.
            base_plane = "Front Plane" if face in ("-Y", "+Y") else "Right Plane"
            half = oW / 2 if face in ("-Y", "+Y") else oL / 2
            outside_positive = face in ("-Y", "+X")  # SolidWorks +Z is the box's -Y; +X is +X
            a(f"    Set pl = Plane(\"{base_plane}\", {_m(half + 1)}, {'False' if outside_positive else 'True'})")
            cut = f"{_m(t + 2)}, {'False' if outside_positive else 'True'}"
            sx, sy = c.at[0], f + c.at[1]
        a("    StartSketch pl")
        if c.shape == "round":
            a(f"    Circ {_m(sx)}, {_m(sy)}, {_m(w / 2)}")
        else:
            a(f"    Rect {_m(sx)}, {_m(sy)}, {_m(w)}, {_m(hh)}")
        a("    EndSketch")
        a(f'    Cut {cut}, "Cutout {n} {(c.preset or c.shape)}"')
    a("")
    a("    Part.ClearSelection2 True")
    a("    Part.ViewZoomtofit2")
    note = "Done. Left out (in the STEP): " + ", ".join(skipped) if skipped else "Done."
    a(f'    MsgBox "EncloSURE: {note.replace(chr(34), chr(39))}", vbInformation')
    a("End Sub")
    return "\r\n".join(b) + "\r\n", skipped
