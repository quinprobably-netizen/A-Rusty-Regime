"""Harpoon: a scrap-built pneumatic line gun. A welded square-tube rail carries a barbed spear in an
open channel; a ram cylinder kicks it out, fed by a painted pressure tank slung under the rail through
a trigger valve and a copper line. A rope drum with a crank rides the right side, a gauge the left."""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import kit
from kit import _obj, apply_modifiers, begin, block, cut, hole_through, join, mat, prism, slots
from parts import MAKER, common_clips

SZ = 0.0405                      # spear axis height (it lies in the channel on the rail)
RZ = 0.056                       # ram cylinder axis height
TZ, TR = -0.044, 0.033           # tank axis height and radius
TY0, TY1 = 0.082, 0.335          # tank ends (dome tips)
SC = (0.058, -0.165, 0.012)      # rope drum / crank axle centre
GC = (-0.041, 0.11, -0.004)      # gauge centre (body middle)
GF = -0.0478                     # gauge dial face (x)
EYE = (0.0, -0.066, SZ)          # spear rope eye: the spear bone's pivot
NEEDLE = (GF - 0.0014, GC[1], GC[2])


# ------------------------------------------------------------------------------------- helpers

def cyl(*a, **k):
    """kit.cyl with single-segment bevels by default (round parts are many; keeps the body in budget)."""
    k.setdefault("bsegs", 1)
    return kit.cyl(*a, **k)


def ring(*a, **k):
    o = kit.ring(*a, **k)
    o["segs"] = 1
    return o


def add(g, o, bone="root"):
    """g.add with the part's bevel baked first: Gun.finish applies modifiers and then kit.join applies
    them again, which would bevel every part twice."""
    apply_modifiers(o)
    o["bevel"] = 0.0
    return g.add(o, bone)


def fuse(objs, name):
    """Join pieces after baking each one's own bevel (kit.join keeps only the first piece's bevel
    setting, which would bevel every edge of e.g. a coil of rope)."""
    objs = [o for o in objs if o is not None]
    for o in objs:
        apply_modifiers(o)
        o["bevel"] = 0.0
    out = join(objs, name)
    out["bevel"] = 0.0
    return out


def label(text, at, size, material, side=-1, depth=0.0003):
    """kit.label with a coarse curve resolution: raised stencil lettering at a fraction of the triangles."""
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = depth
    cu.resolution_u = 2 if size > 0.004 else 1
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    o = bpy.data.objects.new("label", cu)
    bpy.context.scene.collection.objects.link(o)
    o.location = at
    o.rotation_euler = (math.pi / 2, 0, -math.pi / 2 if side < 0 else math.pi / 2)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    mw = o.matrix_world.copy()
    bpy.data.objects.remove(o, do_unlink=True)
    me.transform(mw)
    me.materials.clear()
    me.materials.append(mat(material))
    out = bpy.data.objects.new("label", me)
    bpy.context.scene.collection.objects.link(out)
    out["bevel"] = 0.0
    return out


def xf(o, m):
    o.data.transform(m)
    return o


def rot_about(o, deg, axis, center):
    c = Vector(center)
    return xf(o, Matrix.Translation(c) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-c))


def obox(name, c, size, ax, ay, material, bevel=0.0004):
    """A box of `size` (along ax, ay, ax x ay) centred at `c`."""
    o = block(name, (0, 0, 0), size, material, bevel=bevel)
    ax = Vector(ax).normalized()
    ay = Vector(ay)
    ay = (ay - ay.dot(ax) * ax).normalized()
    az = ax.cross(ay)
    m = Matrix((ax, ay, az)).transposed().to_4x4()
    m.translation = Vector(c)
    return xf(o, m)


def spline(pts, n=6):
    """Catmull-Rom through `pts`, `n` samples per span."""
    pts = [Vector(p) for p in pts]
    if len(pts) < 3:
        return [pts[0].lerp(pts[-1], i / n) for i in range(n + 1)]
    ext = [pts[0] * 2 - pts[1]] + pts + [pts[-1] * 2 - pts[-2]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1:i + 3]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(pts[-1])
    return out


def _lengths(pts):
    s = [0.0]
    for i in range(1, len(pts)):
        s.append(s[-1] + (pts[i] - pts[i - 1]).length)
    return s


def resample(pts, step):
    pts = [Vector(p) for p in pts]
    s = _lengths(pts)
    L = s[-1]
    n = max(1, round(L / step))
    out, j = [], 0
    for i in range(n + 1):
        t = L * i / n
        while j < len(pts) - 2 and s[j + 1] < t:
            j += 1
        seg = s[j + 1] - s[j]
        f = 0 if seg <= 0 else (t - s[j]) / seg
        out.append(pts[j].lerp(pts[j + 1], min(1, max(0, f))))
    return out


def at_len(pts, t):
    """Point and tangent at arc length t along a polyline."""
    s = _lengths(pts)
    for j in range(len(pts) - 1):
        if s[j + 1] >= t or j == len(pts) - 2:
            seg = max(1e-9, s[j + 1] - s[j])
            f = min(1, max(0, (t - s[j]) / seg))
            return pts[j].lerp(pts[j + 1], f), (pts[j + 1] - pts[j]).normalized()


def sweep(name, pts, radius, material, segs=12, hint=(1, 0, 0), caps=True, closed=False, bevel=0.0):
    """Tube through `pts` (parallel-transport frames). `radius`: number, (rx, ry), a list per point or
    f(t 0..1, s metres) returning either. rx lies along `hint` at the start."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    s = _lengths(pts)
    L = s[-1] or 1.0
    tans = []
    for i in range(n):
        a, b = (pts[(i - 1) % n], pts[(i + 1) % n]) if closed else (pts[max(i - 1, 0)], pts[min(i + 1, n - 1)])
        tans.append((b - a).normalized())
    h = Vector(hint)
    u = h - h.dot(tans[0]) * tans[0]
    if u.length < 1e-6:
        u = tans[0].orthogonal()
    u.normalize()
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(pts):
        if i:
            u = tans[i - 1].rotation_difference(tans[i]) @ u
            u = (u - u.dot(tans[i]) * tans[i]).normalized()
        v = tans[i].cross(u)
        r = radius(s[i] / L, s[i]) if callable(radius) else (radius[i] if isinstance(radius, list) else radius)
        rx, ry = r if isinstance(r, tuple) else (r, r)
        rings.append([bm.verts.new(p + u * (rx * math.cos(2 * math.pi * k / segs)) + v * (ry * math.sin(2 * math.pi * k / segs)))
                      for k in range(segs)])
    for i in range(n if closed else n - 1):
        A, B = rings[i], rings[(i + 1) % n]
        for k in range(segs):
            j = (k + 1) % segs
            bm.faces.new((A[k], A[j], B[j], B[k]))
    if caps and not closed:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _obj(name, bm, material, bevel)
    o["shaded"] = True  # tubes stay smooth all round (kit would sharpen their coarse facets)
    return o


def circle(c, axis, r, n=24):
    a = Vector(axis).normalized()
    e1 = a.orthogonal().normalized()
    e2 = a.cross(e1)
    return [Vector(c) + (e1 * math.cos(2 * math.pi * i / n) + e2 * math.sin(2 * math.pi * i / n)) * r for i in range(n)]


def torus(name, c, axis, R, r, material, segs=20, rsegs=6):
    return sweep(name, circle(c, axis, R, segs), r, material, segs=rsegs, hint=axis, closed=True)


def weld(pts, r=0.0015, closed=False, smooth=False, period=0.0055):
    """A rippled weld bead along a line (or a closed loop)."""
    pts = [Vector(p) for p in pts]
    if smooth:
        pts = spline(pts, 8)
    if closed:
        pts = pts + [pts[0]]
    pts = resample(pts, period / 3)
    if closed:
        pts = pts[:-1]
    L = _lengths(pts)[-1]
    ripple = (1.0, 1.3, 1.14)

    def rad(t, s):
        k = ripple[int(round(s / (period / 3))) % 3]
        taper = 1.0 if closed else min(1.0, 0.45 + s / 0.003, 0.45 + (L - s) / 0.003)
        return r * k * taper
    d = (pts[-1] - pts[0])
    hint = Vector((0, 0, 1)) if abs(d.normalized().z) < 0.9 else Vector((1, 0, 0))
    return sweep("weld", pts, rad, "steel", segs=6, hint=hint, closed=closed)


AX = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}


def _axis(axis):
    return Vector(AX[axis[-1]]) * (-1 if axis.startswith("-") else 1)


def bolt(at, axis="-x", size=0.0034, material="steel", washer=True):
    """A hex bolt head (with a washer) sitting on a surface at `at`, facing `axis`."""
    a, at = _axis(axis), Vector(at)
    parts = []
    base = at
    if washer:
        parts.append(cyl("washer", at - a * 0.0003, at + a * 0.0007, size * 1.45, material, segs=12, bevel=0.00015, bsegs=1))
        base = at + a * 0.0007
    parts.append(cyl("bolt", base - a * 0.0002, base + a * size * 0.75, size, material, segs=6, bevel=0.0003, bsegs=1))
    parts.append(cyl("tip", base + a * size * 0.75, base + a * size * 0.95, size * 0.55, material, r1=size * 0.4, segs=10, bevel=0))
    return fuse(parts, "bolt")


def nut(at, axis="x", size=0.0034, material="steel"):
    """A hex nut with the bolt's threaded end poking out past it."""
    a, at = _axis(axis), Vector(at)
    n = cyl("nut", at - a * 0.0002, at + a * size * 0.85, size, material, segs=6, bevel=0.0003, bsegs=1)
    th = cyl("thread", at, at + a * size * 1.5, size * 0.52, "steel", segs=10, bevel=0.0002, bsegs=1)
    return fuse([n, th], "nut")


def rivet(at, axis="-x", r=0.0017, material="steel"):
    a, at = _axis(axis), Vector(at)
    return cyl("rivet", at - a * 0.0003, at + a * r * 0.55, r, material, r1=r * 0.55, segs=12, bevel=0.0002, bsegs=1)


def hose_clamp(c, axis, r, up=(-1, 0, 0)):
    """A worm-drive hose clamp around a hose of radius r; the screw housing faces `up`."""
    c, a = Vector(c), Vector(axis).normalized()
    up = Vector(up)
    up = (up - up.dot(a) * a).normalized()
    tang = up.cross(a)
    band = ring("clamp", c, a, r + 0.0011, r - 0.0004, 0.0058, "bright", segs=18)
    hc = c + up * (r + 0.0022)
    house = obox("house", hc, (0.0066, 0.009, 0.0036), a, tang, "bright", bevel=0.0004)
    sc = hc + up * 0.0006
    scr = cyl("screw", sc - tang * 0.006, sc + tang * 0.0055, 0.0016, "steel", segs=10, bevel=0.0002)
    head = cyl("head", sc + tang * 0.0055, sc + tang * 0.0085, 0.0026, "steel", segs=6, bevel=0.0003)
    return fuse([band, house, scr, head], "clamp")


def tape_band(c0, c1, rx, ry, tilt, material="tan"):
    """One wrap of tape around an elliptical core, tilted `tilt` degrees about X."""
    c0, c1 = Vector(c0), Vector(c1)
    mid = (c0 + c1) / 2
    o = sweep("tape", [c0, mid, c1], [(rx, ry), (rx * 1.012, ry * 1.012), (rx, ry)], material, segs=16, hint=(1, 0, 0))
    return rot_about(o, tilt, "X", mid)


def stripes_flat(face, y0, y1, a, b, x_or_z, w=0.0065, pitch=0.013, h=0.0003):
    """Black diagonal hazard stripes on a flat face of the rail, clipped to y0..y1. face "x": (y, z) with
    z in a..b at x; face "z": (x, y) with x in a..b at z."""
    out = []
    span = b - a
    y = y0 - span - pitch
    while y < y1 + pitch:
        quad = [(y, a), (y + w, a), (y + w + span, b), (y + span, b)]
        if face == "x":
            out.append(prism("st", quad, h, "black", x=x_or_z, bevel=0))
        else:
            out.append(plan_pts("st", [(q[1], q[0]) for q in quad], h, x_or_z))
        y += pitch
    s = join(out, "stripes")
    big = 0.2
    return cut(s, block("c", (0, y0 - big / 2, 0.02), (0.3, big, 0.3), "steel", bevel=0),
               block("c", (0, y1 + big / 2, 0.02), (0.3, big, 0.3), "steel", bevel=0))


def plan_pts(name, pts, h, z):
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z - h / 2)) for x, y in pts]
    face = bm.faces.new(vs)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, vec=(0, 0, h), verts=[e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, "black", 0.0)


def stripes_cyl(y0, y1, R, cz, n=10, material="black"):
    """Diagonal stripes painted round a cylinder along Y (a thin raised shell)."""
    bm = bmesh.new()
    w = math.pi / n
    m, k = 4, 3
    for i in range(n):
        a0 = 2 * math.pi * i / n
        layers = []
        for rr in (R + 0.0011, R + 0.0002):
            grid = []
            for j in range(m + 1):
                y = y0 + (y1 - y0) * j / m
                sh = (y - y0) / R
                grid.append([bm.verts.new((rr * math.cos(a0 + sh + w * q / k), y, cz + rr * math.sin(a0 + sh + w * q / k))) for q in range(k + 1)])
            layers.append(grid)
        out, inn = layers
        for j in range(m):
            for q in range(k):
                bm.faces.new((out[j][q], out[j][q + 1], out[j + 1][q + 1], out[j + 1][q]))
                bm.faces.new((inn[j + 1][q], inn[j + 1][q + 1], inn[j][q + 1], inn[j][q]))
        for j in range(m):
            for q in (0, k):
                bm.faces.new((out[j][q], out[j + 1][q], inn[j + 1][q], inn[j][q]))
        for j in (0, m):
            for q in range(k):
                bm.faces.new((out[j][q], out[j][q + 1], inn[j][q + 1], inn[j][q]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj("stripes", bm, material, 0.0)


def stadium(a, b, ra, rb, n=8):
    """Outline (y, z) of a bar joining a circle at a (radius ra) to one at b (radius rb)."""
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    pts = []
    for i in range(n + 1):
        f = ang - math.pi / 2 + math.pi * i / n
        pts.append((b[0] + rb * math.cos(f), b[1] + rb * math.sin(f)))
    for i in range(n + 1):
        f = ang + math.pi / 2 + math.pi * i / n
        pts.append((a[0] + ra * math.cos(f), a[1] + ra * math.sin(f)))
    return pts


# --------------------------------------------------------------------------------------- build

def build():
    g = begin("harpoon", {
        "spear": (EYE, None),
        "spool": (SC, None),
        "crank": (SC, None),
        "trigger": ((0, 0.02, -0.006), None),
        "gauge": (NEEDLE, None),
    })
    R = []  # root parts

    # --- frame rail: a welded square tube, drilled, with a spear channel on top -------------------
    Y0, Y1 = -0.27, 0.415
    rail = block("rail", (0, (Y0 + Y1) / 2, 0.017), (0.034, Y1 - Y0, 0.034), "yellow", bevel=0.0012)
    holes = [hole_through("h", (0, y, 0.017), 0.0068, "x", 0.06, segs=20) for y in (0.09, 0.13, 0.17)]
    holes += [hole_through("h", (0, y, 0.0), 0.0035, "z", 0.01, segs=12) for y in (0.36,)]
    rail = cut(rail, block("in", (0, (Y0 + Y1) / 2, 0.017), (0.028, Y1 - Y0 + 0.02, 0.028), "steel", bevel=0))
    rail = cut(rail, *holes)  # separately: EXACT booleans want a cutter that does not overlap itself
    R.append(rail)
    R.append(block("endcap", (0, Y0 - 0.0015, 0.017), (0.034, 0.003, 0.034), "rust", bevel=0.0006))
    R.append(weld([(-0.0175, Y0 + 0.0003, 0.0), (-0.0175, Y0 + 0.0003, 0.034)]))
    R.append(weld([(-0.017, Y0 + 0.0003, 0.0345), (0.017, Y0 + 0.0003, 0.0345)]))
    for x in (-0.0083, 0.0083):
        R.append(block("wall", (x, 0.175, 0.0385), (0.003, 0.45, 0.009), "steel", bevel=0.0005))
        for y in (-0.03, 0.05, 0.13, 0.21, 0.29, 0.38):
            s = 1 if x > 0 else -1
            R.append(weld([(x + s * 0.0018, y - 0.007, 0.0345), (x + s * 0.0018, y + 0.007, 0.0345)], r=0.0013))
    # stencil and scuffs on the left face
    R.append(label("RR-9 HARPOON", (-0.0172, 0.255, 0.021), 0.0072, "black"))
    R.append(label("LINE GUN  MK II   350 BAR RAM", (-0.0172, 0.255, 0.0095), 0.0028, "black"))
    R.append(label("NO 0419", (-0.0172, -0.012, 0.027), 0.0026, "black"))
    R.append(label(MAKER, (0.0172, 0.2, 0.022), 0.0042, "black", side=1))
    R.append(label("REWIND BEFORE LOADING", (0.0172, 0.2, 0.012), 0.0028, "black", side=1))
    # a bolted repair plate over the grip and a welded doubler strip along the lower edge
    R.append(block("patch", (-0.0181, -0.035, 0.0175), (0.0024, 0.05, 0.026), "steel", bevel=0.0006))
    for y in (-0.055, -0.015):
        for z in (0.009, 0.026):
            R.append(bolt((-0.0193, y, z), "-x", 0.0021, washer=False))
    R.append(weld([(-0.0193, -0.0605, 0.0045), (-0.0193, -0.0095, 0.0045)], r=0.0011))
    R.append(block("doubler", (-0.0185, 0.19, 0.004), (0.003, 0.25, 0.0065), "steel", bevel=0.0005))
    for y in (0.08, 0.15, 0.23, 0.3):
        R.append(weld([(-0.02, y - 0.006, 0.0075), (-0.02, y + 0.006, 0.0075)], r=0.0011))
    # hazard sleeve near the front
    HY0, HY1 = 0.33, 0.385
    R.append(block("sleeve", (0, (HY0 + HY1) / 2, 0.017), (0.0362, HY1 - HY0, 0.0362), "hazard", bevel=0.0006))
    R.append(stripes_flat("x", HY0 + 0.001, HY1 - 0.001, 0.0012, 0.0338, -0.0182))
    R.append(stripes_flat("x", HY0 + 0.001, HY1 - 0.001, 0.0012, 0.0338, 0.0182))
    for y in (HY0 + 0.004, HY1 - 0.004):
        for z in (0.006, 0.028):
            R.append(rivet((-0.0181, y, z), "-x"))
    # front plate with an open U-notch the spear drops into
    plate = block("plate", (0, 0.419, 0.024), (0.044, 0.008, 0.062), "rust", bevel=0.0009)
    plate = cut(plate, cyl("n", (0, 0.41, SZ), (0, 0.43, SZ), 0.0068, "steel", segs=20, bevel=0))
    plate = cut(plate, block("n", (0, 0.419, SZ + 0.02), (0.0136, 0.03, 0.04), "steel", bevel=0))
    plate = cut(plate, hole_through("h", (-0.013, 0.419, 0.0), 0.003, "y", 0.03), hole_through("h", (0.013, 0.419, 0.0), 0.003, "y", 0.03))
    R.append(plate)
    R.append(weld([(-0.0182, 0.4148, 0.0005), (-0.0182, 0.4148, 0.0345), (0.0182, 0.4148, 0.0345), (0.0182, 0.4148, 0.0005)]))
    R.append(bolt((-0.013, 0.4232, 0.0), "y", 0.0026))
    R.append(bolt((0.013, 0.4232, 0.0), "y", 0.0026))

    # --- ram cylinder and its saddle clamps ----------------------------------------------------
    RY0, RY1 = -0.262, -0.095
    R.append(cyl("ram", (0, RY0, RZ), (0, RY1, RZ), 0.020, "steel", segs=32))
    R.append(cyl("flange", (0, RY1 - 0.006, RZ), (0, RY1, RZ), 0.0255, "steel", segs=32, bevel=0.0006))
    R.append(cyl("cap", (0, RY1, RZ), (0, RY1 + 0.006, RZ), 0.0235, "steel", segs=32, bevel=0.0008))
    R.append(cyl("flange", (0, RY0, RZ), (0, RY0 + 0.006, RZ), 0.0255, "steel", segs=32, bevel=0.0006))
    R.append(cyl("cap", (0, RY0 - 0.006, RZ), (0, RY0, RZ), 0.0235, "steel", segs=32, bevel=0.0008))
    for k in range(6):
        f = math.radians(30 + 60 * k)
        R.append(bolt((0.0205 * math.cos(f), RY1 + 0.006, RZ + 0.0205 * math.sin(f)), "y", 0.0022, washer=False))
        R.append(bolt((0.0205 * math.cos(f), RY0 - 0.006, RZ + 0.0205 * math.sin(f)), "-y", 0.0022, washer=False))
    for y in (RY1 - 0.0062, RY0 + 0.0062):
        R.append(weld(circle((0, y, RZ), (0, 1, 0), 0.0205, 40), closed=True, r=0.0012))
    R.append(label("RAM", (-0.0203, -0.2, RZ + 0.002), 0.0068, "bright"))
    R.append(label("DO NOT DRY FIRE", (-0.0203, -0.2, RZ - 0.0078), 0.0024, "bright"))
    for y in (-0.235, -0.13):
        R.append(ring("band", (0, y, RZ), (0, 1, 0), 0.0228, 0.0197, 0.01, "steel", segs=32))
        R.append(block("saddle", (0, y, 0.036), (0.03, 0.014, 0.004), "steel", bevel=0.0005))
        R.append(block("base", (0, y, 0.0355), (0.066, 0.016, 0.003), "steel", bevel=0.0005))
        for s in (-1, 1):
            R.append(block("ear", (s * 0.026, y, 0.0395), (0.009, 0.01, 0.003), "steel", bevel=0.0004))
            R.append(bolt((s * 0.027, y, 0.041), "z", 0.0024, washer=False))
            R.append(nut((s * 0.027, y, 0.034), "-z", 0.0024))
            R.append(weld([(s * 0.0175, y - 0.0075, 0.034), (s * 0.0175, y + 0.0075, 0.034)], r=0.0012))
    # piston rod and the pusher that the spear's eye sits against
    R.append(cyl("rod", (0, RY1 + 0.006, RZ), (0, -0.0805, RZ), 0.0052, "bright", segs=18))
    R.append(block("pusher", (0, -0.0785, 0.0488), (0.014, 0.005, 0.0266), "steel", bevel=0.0006))
    R.append(cyl("pusherboss", (0, -0.0815, RZ), (0, -0.0785, RZ), 0.0072, "steel", segs=6, bevel=0.0004))
    # charge valve, relief valve and the air inlet on the ram
    R.append(cyl("schrader", (0, -0.205, RZ + 0.018), (0, -0.205, RZ + 0.03), 0.0035, "brass", segs=6, bevel=0.0003))
    R.append(cyl("schcap", (0, -0.205, RZ + 0.03), (0, -0.205, RZ + 0.036), 0.0032, "black", segs=16, bevel=0.0004))
    R.append(cyl("relief", (0, -0.16, RZ + 0.018), (0, -0.16, RZ + 0.028), 0.0048, "brass", segs=16, bevel=0.0004))
    R.append(cyl("relief2", (0, -0.16, RZ + 0.028), (0, -0.16, RZ + 0.032), 0.0032, "brass", segs=12, bevel=0.0003))
    R.append(torus("pullring", (0, -0.16, RZ + 0.037), (1, 0, 0), 0.0045, 0.0008, "bright", segs=16, rsegs=5))
    R.append(cyl("inlet", (-0.018, -0.19, RZ), (-0.026, -0.19, RZ), 0.0052, "brass", segs=6, bevel=0.0004))

    # --- trigger group: guard, ears, pivot bolt, valve ------------------------------------------
    guard = spline([(0, 0.053, -0.001), (0, 0.055, -0.03), (0, 0.046, -0.062), (0, 0.02, -0.072), (0, -0.01, -0.068), (0, -0.031, -0.056)], 6)
    R.append(sweep("guard", guard, (0.0048, 0.0026), "steel", segs=12, hint=(1, 0, 0)))
    R.append(weld([(-0.005, 0.0505, -0.0003), (0.005, 0.0505, -0.0003)], r=0.0012))
    R.append(weld([(-0.005, 0.0565, -0.0003), (0.005, 0.0565, -0.0003)], r=0.0012))
    R.append(weld([(-0.0048, -0.0315, -0.059), (-0.0048, -0.0315, -0.053)], r=0.0011))
    for s in (-1, 1):
        R.append(block("ear", (s * 0.0058, 0.019, -0.0065), (0.0022, 0.024, 0.013), "steel", bevel=0.0005))
        R.append(weld([(s * 0.0072, 0.008, -0.0003), (s * 0.0072, 0.03, -0.0003)], r=0.0011))
    R.append(bolt((-0.007, 0.02, -0.006), "-x", 0.0024))
    R.append(nut((0.007, 0.02, -0.006), "x", 0.0024))
    valve = block("valve", (0, 0.065, -0.013), (0.016, 0.014, 0.022), "brass", bevel=0.0008)
    valve = cut(valve, *slots("v", 0.06, 0.07, 3, -0.024, -0.02, -0.01, 0.01))
    R.append(valve)
    R.append(cyl("vport", (-0.008, 0.065, -0.012), (-0.013, 0.065, -0.012), 0.0048, "brass", segs=6, bevel=0.0003))
    R.append(cyl("vstem", (-0.008, 0.065, -0.003), (-0.012, 0.065, -0.003), 0.0022, "bright", segs=12))
    R.append(prism("vlever", [(0.062, -0.0045), (0.068, -0.0045), (0.08, 0.0), (0.08, 0.004), (0.062, 0.0)], 0.0022, "red", x=-0.0128, bevel=0.0004))
    R.append(bolt((-0.0082, 0.06, -0.021), "-x", 0.0018, washer=False))
    R.append(weld([(-0.0082, 0.058, -0.0003), (-0.0082, 0.072, -0.0003)], r=0.0011))
    R.append(sweep("tankline", spline([(0, 0.084, TZ), (0, 0.073, TZ), (0, 0.066, -0.032), (0, 0.065, -0.024)], 6), 0.0032, "copper", segs=12))
    R.append(cyl("tnut", (0, 0.0655, -0.0285), (0, 0.065, -0.0235), 0.0046, "brass", segs=6, bevel=0.0003))

    # --- trigger lever -------------------------------------------------------------------------
    lever = prism("lever", [(0.0135, -0.0015), (0.0265, -0.0015), (0.0275, -0.013), (0.031, -0.03), (0.0365, -0.046), (0.0365, -0.056),
                            (0.031, -0.0605), (0.0245, -0.056), (0.0215, -0.041), (0.0165, -0.024), (0.0135, -0.012)], 0.0085, "steel",
                  bevel=0.0009, segs=2)
    lever = cut(lever, hole_through("ph", (0, 0.02, -0.006), 0.0024, "x"),
                *[obox("gr", (0, 0.0335 + 0.0013 * i, -0.04 - 0.005 * i), (0.02, 0.0016, 0.002), (1, 0, 0), (0, 0.4, 1), "steel", bevel=0)
                  for i in range(3)])
    add(g, fuse([lever, cyl("tbush", (-0.0045, 0.02, -0.006), (0.0045, 0.02, -0.006), 0.0038, "bright", segs=16),
                cyl("link", (0, 0.025, -0.009), (0, 0.058, -0.011), 0.0016, "bright", segs=10),
                block("pad", (0, 0.0335, -0.051), (0.011, 0.004, 0.012), "rubber", bevel=0.0012, segs=2)], "trigger"), "trigger")

    # --- pistol grip: pipe core wrapped in cloth tape -------------------------------------------
    G0, G1 = Vector((0, -0.034, 0.0)), Vector((0, -0.064, -0.112))
    R.append(sweep("grip", resample([G0, G1], 0.02), (0.0135, 0.0165), "steel", segs=16))
    R.append(weld(circle((0, -0.034, -0.0012), (0, 0, 1), 0.0152, 28), closed=True, r=0.0013))
    R.append(cyl("gcap", G1 + Vector((0, -0.0005, 0.002)), G1 + Vector((0, -0.0015, -0.004)), 0.0158, "rust", segs=20, bevel=0.001))
    wraps = 13
    for i in range(wraps):
        t0 = 0.09 + 0.82 * i / wraps
        t1 = t0 + 0.82 / wraps * 1.5
        R.append(tape_band(G0.lerp(G1, t0), G0.lerp(G1, t1), 0.0142 + 0.0003 * (i % 2), 0.0172 + 0.0003 * (i % 2), 11 if i % 2 else 4, "tan"))
    R.append(obox("tapeend", G0.lerp(G1, 0.88) + Vector((-0.0118, 0.006, 0.0)), (0.0006, 0.012, 0.009), (1, 0, 0), (0, 0.6, 0.8), "tan", bevel=0.0002))

    # --- stock: pipe brace and a bolted rubber butt --------------------------------------------
    up = spline([(0, -0.262, 0.012), (0, -0.285, 0.010), (0, -0.307, -0.004), (0, -0.317, -0.018)], 6)
    R.append(sweep("stock", up, 0.0085, "steel", segs=16))
    low = spline([(0, -0.062, -0.108), (0, -0.15, -0.098), (0, -0.25, -0.083), (0, -0.317, -0.072)], 6)
    R.append(sweep("brace", low, 0.0072, "steel", segs=16))
    R.append(weld(circle((0, Y0 - 0.0032, 0.0115), (0, 1, 0), 0.0092, 24), closed=True, r=0.0013))
    R.append(weld([(-0.0075, -0.066, -0.1045), (-0.0075, -0.074, -0.1045)], r=0.0016))
    R.append(block("buttplate", (0, -0.321, -0.037), (0.032, 0.006, 0.094), "rust", bevel=0.0008))
    R.append(block("buttpad", (0, -0.331, -0.037), (0.036, 0.014, 0.1), "rubber", bevel=0.003, segs=3))
    for i in range(7):
        R.append(block("padrib", (0, -0.3385, -0.08 + 0.0145 * i), (0.032, 0.0015, 0.006), "rubber", bevel=0.0005))
    for z in (-0.002, -0.07):
        R.append(weld(circle((0, -0.3175, z), (0, 1, 0), 0.0095, 24), closed=True, r=0.0012))
    for z in (-0.075, 0.0):
        R.append(bolt((-0.0102, -0.3245, z + 0.004), "-y", 0.0022))
    R.append(tape_band((0, -0.268, 0.0115), (0, -0.282, 0.0102), 0.0094, 0.0094, 5, "black"))
    R.append(tape_band((0, -0.2795, 0.0105), (0, -0.2935, 0.0075), 0.0094, 0.0094, -7, "black"))

    # --- pressure tank under the rail ------------------------------------------------------------
    hd = 0.017
    prof, rad = [], []
    for k in range(9):
        th = 0.18 + (math.pi / 2 - 0.18) * k / 8
        prof.append((0, TY0 + hd * (1 - math.cos(th)), TZ))
        rad.append(TR * math.sin(th) if k < 8 else TR)
    for y in (0.13, 0.2, 0.26):
        prof.append((0, y, TZ))
        rad.append(TR)
    for k in range(8, -1, -1):
        th = 0.18 + (math.pi / 2 - 0.18) * k / 8
        prof.append((0, TY1 - hd * (1 - math.cos(th)), TZ))
        rad.append(TR * math.sin(th) if k < 8 else TR)
    R.append(sweep("tank", prof, rad, "yellow", segs=36))
    for y in (TY0 + hd, TY1 - hd):
        R.append(ring("seam", (0, y, TZ), (0, 1, 0), TR + 0.0011, TR - 0.002, 0.0035, "yellow", segs=32))
    for y in (0.14, 0.297):
        R.append(ring("strap", (0, y, TZ), (0, 1, 0), TR + 0.0022, TR - 0.001, 0.012, "steel", segs=32))
        R.append(block("hanger", (0, y, -0.0055), (0.02, 0.016, 0.011), "steel", bevel=0.0006))
        R.append(bolt((-0.0102, y, -0.0062), "-x", 0.0026))
        R.append(nut((0.0102, y, -0.0062), "x", 0.0026))
        R.append(weld([(-0.0102, y - 0.008, -0.0002), (-0.0102, y + 0.008, -0.0002)], r=0.0012))
        R.append(obox("tab", (0, y, TZ - TR - 0.004), (0.012, 0.012, 0.006), (1, 0, 0), (0, 1, 0), "steel"))
        R.append(bolt((-0.006, y, TZ - TR - 0.004), "-x", 0.0022, washer=False))
    R.append(ring("hazardband", (0, 0.267, TZ), (0, 1, 0), TR + 0.0007, TR - 0.002, 0.026, "hazard", segs=36))
    R.append(stripes_cyl(0.2545, 0.2795, TR + 0.0002, TZ, n=10))
    R.append(label("HIGH PRESSURE", (-TR - 0.0002, 0.205, TZ + 0.0062), 0.0047, "black"))
    R.append(label("MAX 200 BAR  -  AIR ONLY", (-TR - 0.0002, 0.205, TZ - 0.0035), 0.0027, "black"))
    R.append(label("TEST 03/41", (-TR - 0.0002, 0.205, TZ - 0.0105), 0.0024, "black"))
    # fill valve and red handwheel on the front dome
    R.append(cyl("fill", (0, TY1 - 0.002, TZ), (0, TY1 + 0.012, TZ), 0.0068, "brass", segs=6, bevel=0.0004))
    R.append(cyl("fill2", (0, TY1 + 0.012, TZ), (0, TY1 + 0.02, TZ), 0.0048, "brass", segs=16, bevel=0.0003))
    R.append(cyl("fillport", (0, TY1 + 0.008, TZ), (-0.011, TY1 + 0.008, TZ), 0.0032, "brass", segs=6, bevel=0.0003))
    R.append(cyl("fillcap", (-0.011, TY1 + 0.008, TZ), (-0.014, TY1 + 0.008, TZ), 0.0038, "red", segs=16, bevel=0.0004))
    R.append(torus("wheel", (0, TY1 + 0.024, TZ), (0, 1, 0), 0.0125, 0.0019, "red", segs=24, rsegs=6))
    for k in range(4):
        f = math.radians(45 + 90 * k)
        R.append(cyl("spoke", (0, TY1 + 0.024, TZ), (0.0125 * math.cos(f), TY1 + 0.024, TZ + 0.0125 * math.sin(f)), 0.0013, "red", segs=8))
    R.append(cyl("whub", (0, TY1 + 0.02, TZ), (0, TY1 + 0.0275, TZ), 0.0036, "steel", segs=6, bevel=0.0003))

    # --- gauge on the tank's left shoulder --------------------------------------------------------
    gx, gy, gz = GC
    R.append(cyl("gbody", (-0.034, gy, gz), (GF + 0.0005, gy, gz), 0.021, "brass", segs=36, bevel=0.0006))
    R.append(ring("bezel", (GF - 0.001, gy, gz), (1, 0, 0), 0.0226, 0.0191, 0.0042, "brass", segs=36))
    R.append(cyl("dial", (GF + 0.001, gy, gz), (GF, gy, gz), 0.0196, "tan", segs=36, bevel=0))
    for i in range(13):
        phi = 135 - 270 * i / 12
        major = i % 3 == 0
        L = 0.0042 if major else 0.0024
        rr = 0.0172 - L / 2
        t = block("tick", (GF - 0.0003, gy, gz + rr), (0.0006, 0.0009 if major else 0.0006, L), "red" if i >= 11 else "black", bevel=0)
        R.append(rot_about(t, -phi, "X", (0, gy, gz)))
    for i in range(10):
        phi = -95 - 40 * i / 9
        t = block("redzone", (GF - 0.0002, gy, gz + 0.0185), (0.0004, 0.0021, 0.0012), "red", bevel=0)
        R.append(rot_about(t, -phi, "X", (0, gy, gz)))
    for text, phi in (("0", 135), ("100", 45), ("200", -45), ("300", -135)):
        f = math.radians(phi)
        R.append(label(text, (GF - 0.0003, gy + math.sin(f) * 0.0115, gz + math.cos(f) * 0.0115), 0.0026, "black"))
    R.append(label("BAR", (GF - 0.0003, gy, gz - 0.0075), 0.0028, "black"))
    R.append(label("RR", (GF - 0.0003, gy, gz + 0.0072), 0.0022, "red"))
    glint = []
    for i in range(9):
        f = math.radians(40 + 70 * i / 8)
        glint.append((gy + math.sin(f) * 0.0178, gz + math.cos(f) * 0.0178))
    for i in range(8, -1, -1):
        f = math.radians(48 + 54 * i / 8)
        glint.append((gy + math.sin(f) * 0.0158, gz + math.cos(f) * 0.0158))
    R.append(prism("glass", glint, 0.0003, "glass", x=GF - 0.0026, bevel=0))
    stem = [Vector((gx, gy, gz - 0.019)), Vector((gx, gy, -0.034)), Vector((gx + 0.002, gy, -0.0385)), Vector((-0.031, gy, -0.0395))]
    R.append(sweep("gstem", resample(stem, 0.002), 0.0032, "brass", segs=12))
    R.append(cyl("gnut", (gx, gy, gz - 0.021), (gx, gy, gz - 0.026), 0.0052, "brass", segs=6, bevel=0.0003))
    R.append(cyl("gboss", (-0.0345, gy, -0.0395), (-0.028, gy, -0.0395), 0.0055, "steel", segs=6, bevel=0.0003))
    R.append(weld(circle((-0.0308, gy, -0.0395), (1, 0, 0), 0.0062, 20), closed=True, r=0.001))
    # needle (gauge bone): red pointer with a counterweight, black hub
    nx, ny, nz = NEEDLE
    needle = prism("needle", [(ny - 0.0013, nz - 0.0045), (ny + 0.0013, nz - 0.0045), (ny + 0.0006, nz + 0.003), (ny + 0.00035, nz + 0.0158),
                              (ny, nz + 0.0168), (ny - 0.00035, nz + 0.0158), (ny - 0.0006, nz + 0.003)], 0.0005, "red", x=nx, bevel=0)
    rot_about(needle, 80, "X", NEEDLE)
    hub = cyl("hub", (GF, ny, nz), (nx - 0.0009, ny, nz), 0.0016, "black", segs=14, bevel=0.0002)
    add(g, fuse([needle, hub], "gauge"), "gauge")

    # --- feed hose: rubber at both ends, copper hard line between, worm clamps ------------------
    path = spline([(-0.0125, 0.065, -0.012), (-0.026, 0.066, -0.0115), (-0.036, 0.046, -0.006), (-0.038, -0.02, 0.006), (-0.041, -0.09, 0.025),
                   (-0.043, -0.15, 0.048), (-0.037, -0.188, 0.0565), (-0.026, -0.19, RZ)], 8)
    path = resample(path, 0.004)
    Lh = _lengths(path)[-1]
    a, b = 0.05, Lh - 0.06
    seg_a = [p for p, s in zip(path, _lengths(path)) if s <= a + 0.004]
    seg_c = [p for p, s in zip(path, _lengths(path)) if s >= b - 0.004]
    seg_b = [p for p, s in zip(path, _lengths(path)) if a - 0.012 <= s <= b + 0.012]
    R.append(sweep("hose", seg_a, 0.0064, "rubber", segs=14))
    R.append(sweep("hose", seg_c, 0.0064, "rubber", segs=14))
    R.append(sweep("line", seg_b, 0.0042, "copper", segs=14))
    for s in (0.007, a - 0.006, b + 0.006, Lh - 0.008):
        p, t = at_len(path, s)
        R.append(hose_clamp(p, t, 0.0064, up=(-1, 0, 0.5)))
    p, t = at_len(path, Lh * 0.48)
    R.append(sweep("tape", [p - t * 0.009, p, p + t * 0.009], [0.0048, 0.0051, 0.0048], "black", segs=14))
    p, t = at_len(path, Lh * 0.48 + 0.0095)
    R.append(obox("tapetail", p + Vector((-0.004, 0.0, -0.004)), (0.0005, 0.006, 0.007), (1, 0, 0), t, "black", bevel=0.0001))

    # --- rope drum axle, bracket, pawl and fairlead (root) --------------------------------------
    sx, sy, sz = SC
    R.append(block("bracket", (0.0193, sy, sz), (0.0046, 0.034, 0.032), "steel", bevel=0.0008))
    R.append(weld([(0.0175, sy - 0.017, 0.0345), (0.0175, sy + 0.017, 0.0345)], r=0.0012))
    R.append(weld([(0.0175, sy - 0.017, -0.0003), (0.0175, sy + 0.017, -0.0003)], r=0.0012))
    R.append(cyl("axle", (0.021, sy, sz), (0.094, sy, sz), 0.0055, "bright", segs=16))
    R.append(cyl("axleboss", (0.021, sy, sz), (0.031, sy, sz), 0.0095, "steel", segs=6, bevel=0.0005))
    R.append(prism("pawl", [(sy + 0.012, sz + 0.028), (sy + 0.018, sz + 0.03), (sy + 0.004, sz + 0.0245), (sy + 0.002, sz + 0.0215)],
                   0.003, "steel", x=0.0305, bevel=0.0004))
    R.append(cyl("pawlpin", (0.022, sy + 0.015, sz + 0.029), (0.033, sy + 0.015, sz + 0.029), 0.0018, "bright", segs=10))
    R.append(block("pawlpost", (0.026, sy + 0.015, sz + 0.0255), (0.008, 0.006, 0.012), "steel", bevel=0.0004))
    fl = Vector((0.024, -0.075, 0.05))
    R.append(cyl("fpost", (0.017, -0.075, 0.034), fl + Vector((0, 0, -0.004)), 0.0018, "steel", segs=10))
    R.append(torus("fairlead", fl, (0, 1, 0), 0.0045, 0.0013, "bright", segs=16, rsegs=6))
    R.append(weld(circle((0.0172, -0.075, 0.0348), (0, 0, 1), 0.0028, 12), closed=True, r=0.0009))
    R.append(sweep("rope", spline([(0.07, sy + 0.0005, sz + 0.0343), (0.058, -0.13, 0.05), (0.036, -0.092, 0.051), fl], 8), 0.0021, "cord", segs=8))

    # --- spear (spear bone) -----------------------------------------------------------------------
    S = []
    S.append(cyl("shaft", (0, -0.056, SZ), (0, 0.458, SZ), 0.0052, "bright", segs=18))
    S.append(torus("eye", EYE, (0, 0, 1), 0.0072, 0.0022, "bright", segs=18, rsegs=8))
    S.append(cyl("ferrule", (0, -0.06, SZ), (0, -0.046, SZ), 0.0062, "steel", segs=18, r1=0.0056, bevel=0.0003))
    for y in (-0.03, -0.022):
        S.append(ring("notch", (0, y, SZ), (0, 1, 0), 0.0058, 0.005, 0.003, "steel", segs=18))
    S.append(ring("slider", (0, 0.06, SZ), (0, 1, 0), 0.0072, 0.0051, 0.009, "steel", segs=18))
    for k in range(3):
        S.append(torus("lash", (0.0072, EYE[1] - 0.004 + 0.004 * k, SZ), (0, 1, 0), 0.0034, 0.0012, "cord", segs=12, rsegs=5))
    S.append(sweep("tail", spline([(0.0095, -0.066, SZ), (0.016, -0.073, 0.046), fl + Vector((-0.003, 0, 0))], 6), 0.0021, "cord", segs=8))
    S.append(cyl("collar", (0, 0.454, SZ), (0, 0.478, SZ), 0.0066, "steel", segs=18, bevel=0.0004))
    S.append(cyl("neck", (0, 0.478, SZ), (0, 0.488, SZ), 0.0066, "bright", r1=0.0088, segs=18))
    S.append(rot_about(cyl("point", (0, 0.488, SZ), (0, 0.537, SZ), 0.0088, "bright", r1=0.0004, segs=3, bevel=0.0003), 90, "Y", (0, 0, SZ)))
    for k in range(3):
        barb = prism("barb", [(0.4795, SZ + 0.003), (0.4775, SZ + 0.0072), (0.446, SZ + 0.0195), (0.4442, SZ + 0.0182), (0.462, SZ + 0.0092),
                              (0.471, SZ + 0.003)], 0.0026, "bright", bevel=0.0003)
        hinge = cyl("hinge", (-0.003, 0.4755, SZ + 0.0058), (0.003, 0.4755, SZ + 0.0058), 0.0011, "steel", segs=10)
        S.append(rot_about(fuse([barb, hinge], "barb"), 120 * k + 30, "Y", (0, 0, SZ)))
    add(g, fuse(S, "spear"), "spear")

    # --- rope drum (spool bone) -------------------------------------------------------------------
    P = [cyl("core", (0.0375, sy, sz), (0.0805, sy, sz), 0.019, "steel", segs=28)]
    for x0, x1 in ((0.0345, 0.0385), (0.0795, 0.0835)):
        fl_ = cyl("flange", (x0, sy, sz), (x1, sy, sz), 0.045, "yellow", segs=32, bevel=0.0007)
        fl_ = cut(fl_, *[hole_through("lh", (0, sy + 0.0385 * math.cos(2 * math.pi * i / 7), sz + 0.0385 * math.sin(2 * math.pi * i / 7)),
                                      0.0042, "x", 0.2, segs=12) for i in range(7)])
        P.append(fl_)
    teeth = []
    for i in range(32):
        f = 2 * math.pi * i / 32
        r_ = 0.0245 if i % 2 == 0 else 0.0205
        teeth.append((sy + r_ * math.cos(f), sz + r_ * math.sin(f)))
    P.append(prism("ratchet", teeth, 0.0035, "steel", x=0.0325, bevel=0.0003))
    for k in range(4):
        f = 2 * math.pi * k / 4 + 0.4
        P.append(bolt((0.0836, sy + 0.012 * math.cos(f), sz + 0.012 * math.sin(f)), "x", 0.0018, washer=False))
    pitch = 0.0043
    for layer in range(1, 4):
        rr = 0.0213 + layer * 0.0041
        count = 9 if layer % 2 == 0 else 8
        if layer == 3:
            count = 5
        for i in range(count):
            x = 0.0405 + pitch * (i + (0.5 if layer % 2 else 0))
            P.append(torus("coil", (x, sy, sz), (1, 0, 0), rr, 0.0021, "cord", segs=16, rsegs=5))
    P.append(label("15 M LINE", (0.0838, sy, sz - 0.0305), 0.0036, "black", side=1))
    add(g, fuse(P, "spool"), "spool")

    # --- crank (crank bone) -----------------------------------------------------------------------
    hubc = (sy, sz)
    end = (sy - 0.026, sz - 0.03)
    arm = prism("arm", stadium(hubc, end, 0.0095, 0.0065), 0.004, "steel", x=0.0885, bevel=0.0007)
    arm = cut(arm, prism("lighten", stadium((sy - 0.009, sz - 0.0104), (sy - 0.0175, sz - 0.0202), 0.003, 0.0025), 0.01, "steel", x=0.0885, bevel=0))
    C = [arm, cyl("chub", (0.0865, sy, sz), (0.0935, sy, sz), 0.0085, "steel", segs=6, bevel=0.0005),
         nut((0.0935, sy, sz), "x", 0.0052),
         cyl("cpin", (0.0905, end[0], end[1]), (0.098, end[0], end[1]), 0.003, "bright", segs=12),
         cyl("knob", (0.0985, end[0], end[1]), (0.124, end[0], end[1]), 0.0068, "tan", segs=16, bevel=0.0008),
         cyl("kcap", (0.124, end[0], end[1]), (0.1265, end[0], end[1]), 0.0055, "steel", segs=14, bevel=0.0005)]
    for i in range(3):
        C.append(ring("kgroove", (0.104 + 0.006 * i, end[0], end[1]), (1, 0, 0), 0.0071, 0.0062, 0.0012, "cord", segs=16))
    add(g, fuse(C, "crank"), "crank")

    for o in R:
        add(g, o, "root")
    g.socket("muzzle", (0, 0.537, SZ), "root")

    # --- clips ------------------------------------------------------------------------------------
    drop = -205  # gauge needle sweep from full (200 bar) to empty
    g.clip("fire", 0.35, {
        "trigger": [(0, (0, 0, 0), (0, 0, 0)), (0.03, (0, 0, 0), (-16, 0, 0)), (0.17, (0, 0, 0), (-16, 0, 0)), (0.3, (0, 0, 0), (0, 0, 0))],
        "spear": [(0, (0, 0, 0), (0, 0, 0)), (0.02, (0, 0.04, 0), (0, 0, 0)), (0.07, (0, 2.2, 0), (0, 0, 0)), (0.34, (0, 2.4, 0), (0, 0, 0))],
        "spool": [(0, (0, 0, 0), (0, 0, 0)), (0.025, (0, 0, 0), (-30, 0, 0)), (0.28, (0, 0, 0), (-700, 0, 0)), (0.35, (0, 0, 0), (-720, 0, 0))],
        "gauge": [(0, (0, 0, 0), (0, 0, 0)), (0.025, (0, 0, 0), (drop * 0.8, 0, 0)), (0.06, (0, 0, 0), (drop, 0, 0)), (0.2, (0, 0, 0), (drop + 8, 0, 0)),
                  (0.35, (0, 0, 0), (0, 0, 0))],
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.035, (0, -0.035, 0.008), (7, 0, -1.5)), (0.13, (0, -0.012, 0.003), (2.5, 0, 0.5)),
                 (0.3, (0, 0, 0), (0, 0, 0))],
    })
    reload = {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.22, (0.02, -0.02, 0.012), (10, -8, -8)), (0.55, (0.03, -0.03, 0.02), (14, -16, -10)),
                 (1.12, (0.03, -0.025, 0.02), (12, -18, -8)), (1.24, (0.0, -0.012, 0.004), (4, -4, 0)), (1.32, (0, 0.004, -0.003), (-3, 0, 0)),
                 (1.6, (0, 0, 0), (0, 0, 0))],
        "spear": [(0, (0, 0, 0), (0, 0, 0)), (1 / 60, (-0.16, -0.8, -0.32), (12, 0, 8)), (0.45, (-0.16, -0.8, -0.32), (12, 0, 8)),
                  (0.78, (-0.06, -0.04, 0.03), (4, 0, 2)), (0.98, (0, -0.002, 0.02), (0, 0, 0)), (1.1, (0, 0, -0.0015), (0, 0, 0)),
                  (1.16, (0, 0, 0), (0, 0, 0))],
        "spool": [(0, (0, 0, 0), (0, 0, 0)), (0.15, (0, 0, 0), (0, 0, 0)), (1.08, (0, 0, 0), (1080, 0, 0)), (1.6, (0, 0, 0), (1080, 0, 0))],
        "crank": [(0, (0, 0, 0), (0, 0, 0)), (0.15, (0, 0, 0), (0, 0, 0)), (1.08, (0, 0, 0), (1080, 0, 0)), (1.6, (0, 0, 0), (1080, 0, 0))],
        "gauge": [(0, (0, 0, 0), (0, 0, 0)), (1 / 60, (0, 0, 0), (drop, 0, 0)), (1.18, (0, 0, 0), (drop, 0, 0)), (1.42, (0, 0, 0), (5, 0, 0)),
                  (1.5, (0, 0, 0), (-3, 0, 0)), (1.6, (0, 0, 0), (0, 0, 0))],
    }
    common_clips(g, 1.6, reload)
    g.clip("idle", 1.0, {"gauge": [(0, (0, 0, 0), (0, 0, 0)), (0.25, (0, 0, 0), (1.5, 0, 0)), (0.5, (0, 0, 0), (-1.0, 0, 0)),
                                   (0.75, (0, 0, 0), (1.0, 0, 0)), (1.0, (0, 0, 0), (0, 0, 0))]})
    g.clip("inspect", 2.6, {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.5, (0.02, 0.02, 0.03), (10, 32, 25)), (1.25, (0.02, 0.02, 0.03), (12, 36, 28)),
                 (1.75, (-0.02, 0.0, 0.02), (-6, -28, -18)), (2.3, (0, 0, 0), (0, 0, 0))],
        "crank": [(0, (0, 0, 0), (0, 0, 0)), (0.6, (0, 0, 0), (0, 0, 0)), (1.2, (0, 0, 0), (360, 0, 0)), (2.6, (0, 0, 0), (360, 0, 0))],
        "spool": [(0, (0, 0, 0), (0, 0, 0)), (0.6, (0, 0, 0), (0, 0, 0)), (1.2, (0, 0, 0), (360, 0, 0)), (2.6, (0, 0, 0), (360, 0, 0))],
        "gauge": [(0, (0, 0, 0), (0, 0, 0)), (1.8, (0, 0, 0), (0, 0, 0)), (1.85, (0, 0, 0), (-9, 0, 0)), (2.1, (0, 0, 0), (0, 0, 0))],
    })
    return g


SPEC = {"build": build, "length": (0.8, 0.92), "tris": (20000, 70000),
        "bones": ["root", "spear", "spool", "crank", "trigger", "gauge"],
        "sockets": ["muzzle"],
        "parts": {"mesh.root": "root", "mesh.spear": "spear", "mesh.spool": "spool", "mesh.crank": "crank", "mesh.trigger": "trigger",
                  "mesh.gauge": "gauge"},
        "moves": {"fire": ["spear", "spool", "trigger", "gauge", "root"], "reload": ["spear", "spool", "crank", "gauge", "root"],
                  "draw": ["root"], "inspect": ["root", "crank", "spool"]},
        "view": {"cam": (-1.15, 0.02, 0.5), "look": (0, 0.1, -0.01), "lens": 50}}
