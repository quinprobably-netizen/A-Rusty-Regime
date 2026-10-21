"""Power fist: a scrap piston gauntlet. An open forearm cage of rusty tubes under worn hazard-yellow
plates, a four-block steel knuckle ram on two guide rails, driven by two tie-rod hydraulic pistons,
a banded pressure tank on top with steam vents and flap valves, and a bolted motor drum at the elbow.

The origin is the internal grip bar (where the fist closes); the forearm runs back down -Y.
"""

import math

import bpy  # kit imports bpy first; bmesh needs it
import bmesh
from mathutils import Matrix, Vector

from kit import _obj, begin, block, cut, cyl, hole_through, join, mat, plan, prism, ring, slots
from parts import MAKER

# ------------------------------------------------------------------------------------ local helpers


def _axis(a):
    if isinstance(a, str):
        s = -1 if a.startswith("-") else 1
        return Vector({"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[a[-1]]) * s
    return Vector(a).normalized()


def _fillet(pts, rad, n):
    P = [Vector(p) for p in pts]
    if rad <= 0 or len(P) < 3:
        return P
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        d1, d2 = a - b, c - b
        r = min(rad, d1.length * 0.45, d2.length * 0.45)
        p1, p2 = b + d1.normalized() * r, b + d2.normalized() * r
        for k in range(n + 1):
            t = k / n
            out.append((1 - t) ** 2 * p1 + 2 * (1 - t) * t * b + t * t * p2)
    out.append(P[-1])
    return out


def sweep(name, pts, r, material, segs=14, rad=0.02, n=6, bevel=0.0, caps=True):
    """A round tube swept along a polyline whose corners are filleted into smooth bends."""
    P = _fillet(pts, rad, n)
    T = []
    for i in range(len(P)):
        t = P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]
        T.append(t.normalized())
    up = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = T[0].cross(up).normalized()
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(P):
        if i:
            N = T[i - 1].rotation_difference(T[i]) @ N
            N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N)
        rings.append([bm.verts.new(p + (N * math.cos(2 * math.pi * k / segs) + B * math.sin(2 * math.pi * k / segs)) * r)
                      for k in range(segs)])
    for i in range(len(rings) - 1):
        for k in range(segs):
            j = (k + 1) % segs
            bm.faces.new((rings[i][k], rings[i][j], rings[i + 1][j], rings[i + 1][k]))
    if caps:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, material, bevel)


def lathe(name, prof, origin, axis, material, segs=32, bevel=0.0006, bsegs=2, closed=False):
    """Revolve a profile [(radius, distance along axis), ...] around `axis` through `origin`."""
    M = Matrix.Translation(Vector(origin)) @ Vector((0, 0, 1)).rotation_difference(_axis(axis)).to_matrix().to_4x4()
    bm = bmesh.new()
    rings = [[bm.verts.new((r * math.cos(2 * math.pi * k / segs), r * math.sin(2 * math.pi * k / segs), t)) for k in range(segs)]
             for r, t in prof]
    n = len(rings)
    for i in range(n if closed else n - 1):
        A, B = rings[i], rings[(i + 1) % n]
        for k in range(segs):
            j = (k + 1) % segs
            bm.faces.new((A[k], A[j], B[j], B[k]))
    if not closed:
        if prof[0][0] > 1e-6:
            bm.faces.new(list(reversed(rings[0])))
        if prof[-1][0] > 1e-6:
            bm.faces.new(rings[-1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, material, bevel, bsegs)


def extrude_y(name, pts, y0, y1, material, bevel=0.0008, segs=2):
    """Extrude an outline [(x, z), ...] along Y from y0 to y1."""
    bm = bmesh.new()
    face = bm.faces.new([bm.verts.new((x, y0, z)) for x, z in pts])
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, y1 - y0, 0), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, material, bevel, segs)


def shell(name, y0, y1, r, th, a0, a1, material, n=18, cz=0.0, bevel=0.0009):
    """A curved plate: the arc a0..a1 (degrees from +X toward +Z) of a ring around the Y axis."""
    out = [((r + th) * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cz + (r + th) * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
           for i in range(n + 1)]
    inn = [(r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
           for i in range(n, -1, -1)]
    return extrude_y(name, out + inn, y0, y1, material, bevel, 2)


def hexbolt(at, axis, s=0.0034, material="steel", washer=True, stub=False):
    """Hex bolt head (with washer) sitting on a surface at `at`, facing `axis`."""
    a, at = _axis(axis), Vector(at)
    parts, h = [], 0.0
    if washer:
        parts.append(cyl("washer", at, at + a * s * 0.3, s * 1.45, material, segs=10, bevel=0))
        h = s * 0.3
    parts.append(cyl("hex", at + a * h, at + a * (h + s * 0.75), s, material, segs=6, bevel=0.0003, bsegs=1))
    if stub:
        parts.append(cyl("stub", at + a * (h + s * 0.75), at + a * (h + s * 1.3), s * 0.5, material, r1=s * 0.36, segs=10, bevel=0))
    return join(parts, "bolt")


def rivet(at, axis, r=0.0017, material="steel"):
    a, at = _axis(axis), Vector(at)
    return cyl("rivet", at - a * 0.0004, at + a * 0.0012, r, material, r1=r * 0.55, segs=8, bevel=0)


def weld(p0, p1, normal, r=0.0021, material="steel"):
    """A welded seam: a row of flattened, overlapping beads from p0 to p1."""
    p0, p1 = Vector(p0), Vector(p1)
    t = p1 - p0
    L = t.length
    t.normalize()
    nrm = Vector(normal)
    nrm = (nrm - t * nrm.dot(t)).normalized()
    b = nrm.cross(t)
    count = max(2, int(L / (r * 1.35)))
    bm = bmesh.new()
    for i in range(count):
        c = p0 + (p1 - p0) * ((i + 0.5) / count)
        g = bmesh.ops.create_uvsphere(bm, u_segments=5, v_segments=3, radius=1.0)
        M = Matrix(((t.x * r * 0.9, b.x * r, nrm.x * r * 0.45, c.x), (t.y * r * 0.9, b.y * r, nrm.y * r * 0.45, c.y),
                    (t.z * r * 0.9, b.z * r, nrm.z * r * 0.45, c.z), (0, 0, 0, 1)))
        bmesh.ops.transform(bm, matrix=M, verts=g["verts"])
    return _obj("weld", bm, material, 0.0)


def _clip(poly, u0, u1, v0, v1):
    def edge(pts, inside, inter):
        out = []
        for i in range(len(pts)):
            cur, prev = pts[i], pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(inter(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(inter(prev, cur))
        return out

    def iu(a, b, u):
        t = (u - a[0]) / (b[0] - a[0])
        return (u, a[1] + t * (b[1] - a[1]))

    def iv(a, b, v):
        t = (v - a[1]) / (b[1] - a[1])
        return (a[0] + t * (b[0] - a[0]), v)
    p = poly
    for inside, inter in ((lambda q: q[0] >= u0, lambda a, b: iu(a, b, u0)), (lambda q: q[0] <= u1, lambda a, b: iu(a, b, u1)),
                          (lambda q: q[1] >= v0, lambda a, b: iv(a, b, v0)), (lambda q: q[1] <= v1, lambda a, b: iv(a, b, v1))):
        if len(p) < 3:
            return []
        p = edge(p, inside, inter)
    clean = []
    for q in p:
        if not clean or abs(q[0] - clean[-1][0]) + abs(q[1] - clean[-1][1]) > 1e-6:
            clean.append(q)
    if len(clean) > 2 and abs(clean[0][0] - clean[-1][0]) + abs(clean[0][1] - clean[-1][1]) < 1e-6:
        clean.pop()
    area = 0.5 * abs(sum(clean[i][0] * clean[(i + 1) % len(clean)][1] - clean[(i + 1) % len(clean)][0] * clean[i][1]
                         for i in range(len(clean)))) if len(clean) > 2 else 0
    return clean if area > 2e-7 else []


def _stripes(u0, u1, v0, v1, pitch):
    h = v1 - v0
    out, s = [], u0 - h - pitch
    while s < u1 + pitch:
        poly = _clip([(s, v0), (s + pitch / 2, v0), (s + pitch / 2 + h, v1), (s + h, v1)], u0, u1, v0, v1)
        if poly:
            out.append(poly)
        s += pitch
    return out


def hazard_side(y0, y1, z0, z1, x, th=0.0012, pitch=0.013):
    """A painted hazard-stripe patch on a side face at `x` (black diagonals on hazard yellow)."""
    parts = [prism("haz", [(y0, z0), (y1, z0), (y1, z1), (y0, z1)], th, "hazard", x=x, bevel=0)]
    parts += [prism("hs", p, th + 0.0003, "black", x=x, bevel=0) for p in _stripes(y0, y1, z0, z1, pitch)]
    return parts


def hazard_top(x0, x1, y0, y1, z, th=0.0012, pitch=0.013):
    parts = [plan("haz", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], th, "hazard", z=z, bevel=0)]
    parts += [plan("hs", p, th + 0.0003, "black", z=z, bevel=0) for p in _stripes(x0, x1, y0, y1, pitch)]
    return parts


def _text(text, at, size, material, rot, depth=0.0003):
    """Raised lettering at a low curve resolution (the kit's default resolution costs ~1.5k tris a word)."""
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = depth
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.resolution_u = 1 if size < 0.004 else 2
    o = bpy.data.objects.new("label", cu)
    bpy.context.scene.collection.objects.link(o)
    o.location = at
    o.rotation_euler = rot
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


def label(text, at, size, material, side=-1, depth=0.0003):
    """Side-face lettering like kit.label (reads correctly seen from that side)."""
    return _text(text, at, size, material, (math.pi / 2, 0, -math.pi / 2 if side < 0 else math.pi / 2), depth)


def label_top(text, at, size, material, rot=90.0, depth=0.0003):
    """Lettering on an upward face, reading along +Y (rot=90) or across +X (rot=0)."""
    return _text(text, at, size, material, (0, 0, math.radians(rot)), depth)


def placed(obj, loc, rot):
    """Move a part built around the origin into place (rot in degrees, XYZ euler)."""
    obj.location = loc
    obj.rotation_euler = tuple(math.radians(a) for a in rot)
    return obj


def spin_track(t0, t1, turns=2, steps=12, ease=True, length=None):
    """Drum spin keys: `turns` full turns (keep it even so the end quaternion is the rest one)."""
    keys = [(0.0, (0, 0, 0), (0, 0, 0))] if t0 > 0 else []
    for i in range(steps + 1):
        f = i / steps
        e = f * f * (3 - 2 * f) if ease else f
        keys.append((t0 + (t1 - t0) * f, (0, 0, 0), (0, -360.0 * turns * e, 0)))
    return keys


# -------------------------------------------------------------------------------------------- layout

R_CAGE = 0.066       # forearm cage hoop radius (around the Y axis through the grip)
HOOPS = (-0.062, -0.14, -0.215, -0.262)
PX, PZ = 0.097, -0.032   # piston axes at (+/-PX, PZ)
RAILX, RAILZ = 0.035, -0.045
TANK_Z = 0.122
VENT_X, VENT_Y, VENT_TOP = 0.045, -0.04, 0.166
HINGE = (0, VENT_Y - 0.0155, VENT_TOP + 0.0035)
DRUM_Y = -0.29


def build():
    """Power fist: piston gauntlet with a four-block knuckle ram."""
    g = begin("fist", {
        "ram": ((0, 0.09, 0), None),
        "rods": ((0, 0.084, PZ), None),
        "vent": (HINGE, None),
        "spin": ((0, DRUM_Y, 0), None),
    })
    root, ram, rods, vent, spin = [], [], [], [], []

    # ---------------------------------------------------------------- front housing around the fist
    for s in (-1, 1):
        x = s * 0.066
        cheek = prism("cheek", [(-0.055, -0.058), (0.058, -0.064), (0.072, -0.052), (0.072, 0.052), (0.06, 0.062), (-0.04, 0.062),
                                (-0.055, 0.046)], 0.008, "yellow", x=x, bevel=0.0012, segs=2)
        cheek = cut(cheek, hole_through("lh", (x, -0.03, 0.034), 0.0095, "x", 0.03, segs=20),
                    hole_through("lh", (x, 0.036, 0.036), 0.0085, "x", 0.03, segs=20),
                    *slots("cs", 0.03, 0.058, 5, -0.05, -0.024, x - 0.01, x + 0.01))
        root.append(cheek)
        root.append(label("PF-0", (x + s * 0.0041, 0.003, 0.036), 0.0095, "black", side=s))
        xo = x + s * 0.004
        for y, z in ((-0.046, 0.054), (-0.046, -0.05), (0.064, 0.054), (0.064, -0.046), (0.01, 0.056), (0.012, -0.055)):
            root.append(rivet((xo, y, z), (s, 0, 0)))
        # grip bar nut and the welded seam where the cheek meets the deck
        root.append(hexbolt((xo, 0, 0), (s, 0, 0), 0.0085, stub=True))
        root.append(weld((x - s * 0.004, -0.05, 0.062), (x - s * 0.004, 0.066, 0.062), (s, 0, 1), 0.0022))
    # Grip bar: bright core, rubber wrap with ribs.
    root.append(cyl("bar", (-0.064, 0, 0), (0.064, 0, 0), 0.0105, "bright", segs=20))
    root.append(cyl("wrap", (-0.05, 0, 0), (0.05, 0, 0), 0.0135, "rubber", segs=24, bevel=0.0015))
    root += [cyl("rib", (x - 0.0015, 0, 0), (x + 0.0015, 0, 0), 0.0148, "rubber", segs=20, bevel=0) for x in (-0.042, -0.028, -0.014, 0.0, 0.014, 0.028, 0.042)]
    # Top deck: worn yellow armour with a grille, hazard band and stencil.
    deck = plan("deck", [(-0.074, -0.058), (0.074, -0.058), (0.074, 0.06), (0.064, 0.074), (-0.064, 0.074), (-0.074, 0.06)], 0.008,
                "yellow", z=0.066, bevel=0.0014, segs=2)
    deck = cut(deck, *slots("dg", -0.05, -0.012, 7, 0.058, 0.074, -0.066, -0.054), *slots("dg", -0.05, -0.012, 7, 0.058, 0.074, 0.054, 0.066))
    root.append(deck)
    root += hazard_top(-0.062, 0.062, 0.05, 0.069, 0.0703)
    root.append(label_top("PF-0", (-0.062, 0.012, 0.0703), 0.0085, "black", rot=0))
    for x in (-0.068, 0.068):
        for y in (-0.052, 0.0, 0.054):
            root.append(rivet((x, y, 0.07), "z"))
    # Bulkhead the ram slams back against, with rail bushings and rubber bumpers.
    bulk = block("bulk", (0, 0.066, -0.002), (0.124, 0.012, 0.112), "steel", bevel=0.0012)
    bulk = cut(bulk, block("bw", (0, 0.066, 0.02), (0.06, 0.03, 0.03), "steel", bevel=0))
    root.append(bulk)
    for s in (-1, 1):
        root.append(ring("bush", (s * RAILX, 0.071, RAILZ), (0, 1, 0), 0.0115, 0.0068, 0.006, "bright", segs=14))
        root.append(block("bump", (s * 0.012, 0.074, 0.044), (0.02, 0.004, 0.012), "rubber", bevel=0.001))
        root.append(block("bump", (s * 0.05, 0.074, -0.015), (0.012, 0.004, 0.02), "rubber", bevel=0.001))
        for z in (0.052, -0.058):
            root.append(hexbolt((s * 0.05, 0.072, z), "y", 0.0032))
        # rear rail guide under the fist
        gb = block("guide", (s * RAILX, -0.042, -0.051), (0.022, 0.016, 0.022), "steel", bevel=0.0012)
        root.append(cut(gb, hole_through("gh", (s * RAILX, -0.042, RAILZ), 0.0068, "y", 0.03)))
        root.append(hexbolt((s * (RAILX + 0.011), -0.042, -0.055), (s, 0, 0), 0.0028, washer=False))
    root.append(block("xbar", (0, -0.042, -0.064), (0.14, 0.018, 0.008), "steel", bevel=0.0012))
    root.append(block("xbar", (0, 0.04, -0.064), (0.14, 0.018, 0.008), "steel", bevel=0.0012))

    # ---------------------------------------------------------------- forearm cage
    for i, y in enumerate(HOOPS):
        pts = [(R_CAGE * math.cos(math.radians(a)), y, R_CAGE * math.sin(math.radians(a))) for a in range(-25, 206, 10)]
        root.append(sweep("hoop", pts, 0.0055, "rust", segs=12, rad=0))
    for a in (30, 150, -20, 200):
        x, z = R_CAGE * math.cos(math.radians(a)), R_CAGE * math.sin(math.radians(a))
        root.append(cyl("rail", (x, -0.052, z), (x, -0.268, z), 0.0055, "rust", segs=12, bevel=0))
        for y in HOOPS:
            root.append(cyl("collar", (x, y - 0.0045, z), (x, y + 0.0045, z), 0.0077, "steel", segs=12, bevel=0.0004, bsegs=1))
        root.append(weld((x, -0.053, z - 0.007), (x, -0.053, z + 0.007), (0, -1, 0), 0.002))
    # Top armour plates bolted over the hoops.
    for y0, y1 in ((-0.068, -0.135), (-0.146, -0.208)):
        p = shell("plate", y0, y1, 0.0715, 0.0045, 50, 130, "yellow", n=16)
        root.append(p)
        for a in (56, 72, 108, 124):
            for y in (y0 - 0.005, y1 + 0.005):
                c = Vector((math.cos(math.radians(a)), 0, math.sin(math.radians(a))))
                root.append(rivet(Vector((0, y, 0)) + c * 0.0762, c))
    # Left side plate: the camera's view. Stencils, red warning plate, hazard band, standoffs.
    for s in (-1, 1):
        x = s * 0.083
        sp = prism("side", [(-0.075, 0.0), (-0.19, 0.0), (-0.198, 0.008), (-0.198, 0.046), (-0.19, 0.054), (-0.085, 0.054), (-0.075, 0.044)],
                   0.005, "yellow", x=x, bevel=0.0012, segs=2)
        root.append(sp)
        xo = x + s * 0.0026
        root += hazard_side(-0.078, -0.104, 0.004, 0.05, xo, pitch=0.012) if s < 0 else hazard_side(-0.17, -0.194, 0.004, 0.05, xo, pitch=0.012)
        for y, z in ((-0.084, 0.006), (-0.084, 0.047), (-0.19, 0.006), (-0.19, 0.047), (-0.14, 0.006), (-0.14, 0.05)):
            root.append(hexbolt((xo, y, z), (s, 0, 0), 0.0027, washer=False))
        for y, z, a in ((-0.1, 0.033, 150), (-0.18, 0.033, 150), (-0.14, 0.009, 172)):
            hx = s * abs(R_CAGE * math.cos(math.radians(a)))
            root.append(block("standoff", ((hx + x) / 2, y, z), (abs(x - hx) + 0.002, 0.008, 0.008), "steel", bevel=0.0008))
    root.append(label("POWER FIST", (-0.0859, -0.142, 0.043), 0.0085, "black"))
    root.append(label("PF-0  PNEUMATIC RAM  MK.II", (-0.0859, -0.142, 0.032), 0.0033, "black"))
    root.append(label(MAKER, (0.0859, -0.12, 0.04), 0.0042, "black", side=1))
    root.append(block("warn", (-0.0862, -0.155, 0.016), (0.0012, 0.058, 0.019), "red", bevel=0.0003))
    root.append(label("DANGER", (-0.0871, -0.155, 0.0195), 0.0062, "hazard"))
    root.append(label("KEEP HANDS CLEAR OF RAM", (-0.0871, -0.155, 0.0107), 0.0026, "hazard"))
    # Leather straps under the forearm, wrapped round the lower tubes, with a buckle.
    for y in (-0.105, -0.235):
        root.append(shell("strap", y - 0.014, y + 0.014, 0.0605, 0.0035, 196, 344, "cord", n=18, bevel=0.0006))
        for a in (200, -20):
            x, z = R_CAGE * math.cos(math.radians(a)), R_CAGE * math.sin(math.radians(a))
            root.append(cyl("wrap", (x, y - 0.0145, z), (x, y + 0.0145, z), 0.0082, "cord", segs=12, bevel=0.0006))
        a = 228
        buckle = block("buckle", (0, 0, 0), (0.016, 0.034, 0.003), "steel", bevel=0.0005)
        buckle = cut(buckle, block("bi", (0, 0, 0), (0.01, 0.026, 0.01), "steel", bevel=0))
        prong = cyl("prong", (-0.006, 0, 0.0015), (0.005, 0, 0.0025), 0.0011, "bright", segs=8, bevel=0)
        tail = block("tail", (0.012, 0, -0.0005), (0.022, 0.024, 0.0035), "cord", bevel=0.0005)
        keeper = block("keeper", (0.016, 0, 0.0005), (0.004, 0.03, 0.0055), "cord", bevel=0.0004)
        bk = join([buckle, prong, tail, keeper], "buckle")
        c = Vector((math.cos(math.radians(a)), 0, math.sin(math.radians(a)))) * 0.0665
        root.append(placed(bk, (c.x, y, c.z), (0, 90 - a, 0)))

    # ---------------------------------------------------------------- hydraulic pistons (static part)
    for s in (-1, 1):
        x = s * PX
        root.append(cyl("barrel", (x, -0.186, PZ), (x, -0.02, PZ), 0.0185, "yellow", segs=28, bevel=0))
        for y0, y1 in ((-0.2, -0.186), (-0.02, -0.006)):
            root.append(block("cap", (x, (y0 + y1) / 2, PZ), (0.05, y1 - y0, 0.05), "steel", bevel=0.0018, segs=2))
        root.append(lathe("gland", [(0.0088, 0.0), (0.015, 0.0), (0.015, 0.006), (0.012, 0.009), (0.0088, 0.009)], (x, -0.006, PZ), "y", "steel",
                          segs=20, closed=True))
        root.append(ring("wiper", (x, 0.0035, PZ), (0, 1, 0), 0.0106, 0.0086, 0.002, "rubber", segs=14))
        for dx in (-0.0195, 0.0195):
            for dz in (-0.0195, 0.0195):
                root.append(cyl("tie", (x + dx, -0.204, PZ + dz), (x + dx, -0.002, PZ + dz), 0.0019, "bright", segs=8, bevel=0))
                for y in (-0.204, -0.002):
                    root.append(cyl("nut", (x + dx, y - 0.002, PZ + dz), (x + dx, y + 0.002, PZ + dz), 0.0035, "steel", segs=6, bevel=0.0003, bsegs=1))
        # rear clevis on a bracket from the cage hoop
        root.append(block("lug", (x, -0.207, PZ), (0.014, 0.014, 0.022), "steel", bevel=0.001))
        root.append(cyl("cpin", (x - 0.012, -0.21, PZ), (x + 0.012, -0.21, PZ), 0.0028, "bright", segs=12))
        hx = s * R_CAGE * math.cos(math.radians(20))
        root.append(block("bracket", ((hx + x) / 2, -0.214, PZ + 0.004), (abs(x - hx) + 0.006, 0.008, 0.016), "steel", bevel=0.001))
        root.append(weld((hx, -0.219, PZ - 0.006), (hx, -0.219, PZ + 0.012), (0, -1, 0), 0.0018))
        # front trunnion bolted to the cheek plate
        root.append(block("trun", (s * 0.0715, -0.013, PZ), (0.006, 0.016, 0.026), "steel", bevel=0.001))
        root.append(hexbolt((x + s * 0.025, -0.013, PZ), (s, 0, 0), 0.0034, stub=True))
        # oil port on the rear cap
        root.append(cyl("port", (x, -0.193, PZ + 0.025), (x, -0.193, PZ + 0.031), 0.005, "copper", segs=6, bevel=0.0003, bsegs=1))
    root.append(label("MAX 900 PSI", (-PX - 0.0188, -0.1, PZ), 0.0036, "black"))
    root.append(label("14 T", (-PX - 0.0188, -0.06, PZ), 0.005, "black"))

    # Hoses: tank to the pistons' rear ports, with clamps and copper elbows.
    for s in (-1, 1):
        pts = [(s * 0.02, -0.236, 0.095), (s * 0.055, -0.236, 0.085), (s * 0.103, -0.226, 0.045), (s * 0.1, -0.197, 0.008), (s * PX, -0.193, PZ + 0.03)]
        root.append(sweep("hose", pts, 0.0062, "rubber", segs=12, rad=0.025, n=6))
        for p, q in ((pts[0], pts[1]), (pts[-1], pts[-2])):
            p, q = Vector(p), Vector(q)
            d = (q - p).normalized()
            c = p + d * 0.012
            root.append(ring("clamp", c, d, 0.0074, 0.0061, 0.005, "steel", segs=12))
            side = d.cross(Vector((0, 1, 0)) if abs(d.y) < 0.9 else Vector((1, 0, 0))).normalized()
            root.append(block("clampscrew", tuple(c + side * 0.0082), (0.005, 0.005, 0.005), "steel", bevel=0.0006))
        root.append(cyl("elbow", (s * 0.012, -0.236, 0.099), (s * 0.024, -0.236, 0.094), 0.0068, "copper", segs=6, bevel=0.0003, bsegs=1))
    # Copper line from the tank to the right piston, pinned to the cage with P-clips.
    cpts = [(0.026, -0.12, 0.1), (0.05, -0.12, 0.074), (0.074, -0.12, 0.052), (0.083, -0.07, 0.0), (0.083, -0.025, -0.008), (0.083, -0.016, -0.008)]
    root.append(sweep("cline", cpts, 0.0035, "copper", segs=10, rad=0.018, n=5))

    # ---------------------------------------------------------------- pressure tank on top
    prof = [(0.0, 0.0)] + [(0.033 * math.sin(math.radians(a)), 0.02 * (1 - math.cos(math.radians(a)))) for a in range(15, 91, 15)]
    prof += [(0.033, 0.15)] + [(0.033 * math.cos(math.radians(a)), 0.15 + 0.02 * math.sin(math.radians(a))) for a in range(15, 76, 15)] + [(0.0, 0.17)]
    root.append(lathe("tank", prof, (0, -0.255, TANK_Z), "y", "steel", segs=40, bevel=0))
    root.append(cyl("weldring", (0, -0.235 - 0.0015, TANK_Z), (0, -0.235 + 0.0015, TANK_Z), 0.0337, "steel", segs=32, bevel=0))
    root.append(cyl("weldring", (0, -0.105 - 0.0015, TANK_Z), (0, -0.105 + 0.0015, TANK_Z), 0.0337, "steel", segs=32, bevel=0))
    for y in (-0.105, -0.142, -0.18, -0.218):
        root.append(ring("band", (0, y, TANK_Z), (0, 1, 0), 0.0362, 0.0328, 0.009, "steel", segs=24))
        root.append(block("tens", (-0.0375, y, TANK_Z + 0.006), (0.006, 0.013, 0.018), "steel", bevel=0.0007))
        root.append(cyl("tbolt", (-0.0405, y, TANK_Z - 0.006), (-0.0405, y, TANK_Z + 0.02), 0.0016, "bright", segs=8, bevel=0))
        root.append(cyl("tnut", (-0.0405, y, TANK_Z + 0.015), (-0.0405, y, TANK_Z + 0.019), 0.003, "steel", segs=6, bevel=0.0003, bsegs=1))
    for y in (-0.105, -0.18):
        sd = block("saddle", (0, y, 0.083), (0.05, 0.012, 0.016), "steel", bevel=0.001)
        sd = cut(sd, cyl("sc", (0, y - 0.01, TANK_Z), (0, y + 0.01, TANK_Z), 0.0335, "steel", segs=40, bevel=0))
        root.append(sd)
        for x in (-0.019, 0.019):
            root.append(hexbolt((x, y, 0.0785), "z", 0.0026, washer=False))
    root.append(ring("paint", (0, -0.161, TANK_Z), (0, 1, 0), 0.0333, 0.031, 0.026, "yellow", segs=32))
    root.append(label_top("N2  200 BAR", (0, -0.198, TANK_Z + 0.0333), 0.0062, "hazard", rot=90))
    root.append(label_top("FILL", (0.0, -0.125, TANK_Z + 0.0336), 0.0055, "black", rot=0))
    # Gauge on the tank's upper left, angled toward the player.
    gp = [lathe("bezel", [(0.0, 0.0), (0.0165, 0.0), (0.0165, 0.006), (0.0148, 0.0085), (0.0128, 0.0085), (0.0128, 0.0055), (0.0, 0.0055)],
                (0, 0, 0), "z", "bright", segs=24, bevel=0)]
    gp.append(cyl("face", (0, 0, 0.0052), (0, 0, 0.0058), 0.0128, "lamp", segs=32, bevel=0))
    for k in range(9):
        a = math.radians(225 - k * 33.75)
        c, w = Vector((math.cos(a), math.sin(a), 0)), Vector((-math.sin(a), math.cos(a), 0))
        L = 0.003 if k % 2 == 0 else 0.0018
        p0, p1 = c * 0.0115, c * (0.0115 - L)
        pts = [tuple((p0 + w * 0.0004).xy), tuple((p1 + w * 0.0004).xy), tuple((p1 - w * 0.0004).xy), tuple((p0 - w * 0.0004).xy)]
        gp.append(plan("tick", pts, 0.0004, "red" if k >= 7 else "black", z=0.006, bevel=0))
    na = math.radians(140)
    nd, nw = Vector((math.cos(na), math.sin(na), 0)), Vector((-math.sin(na), math.cos(na), 0))
    gp.append(plan("needle", [tuple((nd * 0.0105).xy), tuple((nw * 0.0009).xy), tuple((-nd * 0.003).xy), tuple((-nw * 0.0009).xy)], 0.0004, "red",
                   z=0.0064, bevel=0))
    gp.append(cyl("hub", (0, 0, 0.006), (0, 0, 0.0068), 0.0014, "black", segs=10, bevel=0))
    gp.append(cyl("stem", (0, 0, -0.012), (0, 0, 0.0), 0.004, "copper", segs=10))
    gp.append(cyl("stemnut", (0, 0, -0.008), (0, 0, -0.003), 0.0055, "copper", segs=6, bevel=0.0003, bsegs=1))
    gc = Vector((-0.707, 0, 0.707)) * 0.045 + Vector((0, -0.136, TANK_Z))
    root.append(placed(join(gp, "gauge"), tuple(gc), (0, -45, 0)))
    # Relief valve on the tank's rear top.
    root.append(lathe("relief", [(0.0, 0.0), (0.006, 0.0), (0.006, 0.006), (0.0045, 0.008), (0.0045, 0.016), (0.0065, 0.017), (0.0065, 0.021), (0.0, 0.022)],
                      (0, -0.235, TANK_Z + 0.03), "z", "copper", segs=18))
    root.append(cyl("ring", (-0.008, -0.235, TANK_Z + 0.048), (0.008, -0.235, TANK_Z + 0.048), 0.001, "bright", segs=8, bevel=0))

    # ---------------------------------------------------------------- steam vents with flap valves
    root.append(block("manifold", (0, 0.025, 0.079), (0.112, 0.03, 0.018), "steel", bevel=0.0016, segs=2))
    for x in (-0.05, 0.05):
        for y in (0.014, 0.036):
            root.append(hexbolt((x, y, 0.088), "z", 0.0026, washer=False))
    for s in (-1, 1):
        x = s * VENT_X
        pts = [(x, 0.03, 0.086), (x, 0.03, 0.118), (x, VENT_Y, 0.124), (x, VENT_Y, VENT_TOP - 0.01)]
        root.append(sweep("vpipe", pts, 0.0085, "steel", segs=16, rad=0.02, n=7))
        root.append(ring("flange", (x, 0.03, 0.09), (0, 0, 1), 0.0125, 0.008, 0.004, "steel", segs=20))
        root.append(ring("coupler", (x, -0.005, 0.1215), (0, -1, 0.08), 0.0108, 0.008, 0.01, "steel", segs=6))
        root.append(ring("coupler", (x, VENT_Y, 0.143), (0, 0, 1), 0.0104, 0.008, 0.006, "copper", segs=20))
        root.append(lathe("nozzle", [(0.0085, 0.0), (0.0105, 0.0), (0.0118, 0.008), (0.0128, 0.0105), (0.0108, 0.0105), (0.0085, 0.004)],
                          (x, VENT_Y, VENT_TOP - 0.0105), "z", "steel", segs=24, closed=True))
        root.append(block("hbr", (x, HINGE[1] - 0.001, HINGE[2] - 0.006), (0.012, 0.004, 0.012), "steel", bevel=0.0006))
        # the flap itself rides the vent bone
        flap = cyl("flap", (x, VENT_Y, VENT_TOP + 0.0005), (x, VENT_Y, VENT_TOP + 0.0035), 0.0145, "steel", segs=24, bevel=0.0006)
        rib = cyl("rib", (x, VENT_Y, VENT_TOP + 0.0035), (x, VENT_Y, VENT_TOP + 0.005), 0.007, "steel", segs=16, bevel=0.0003)
        tab = block("tab", (x, HINGE[1] + 0.005, HINGE[2] - 0.0005), (0.01, 0.011, 0.003), "steel", bevel=0.0004)
        knuckle = cyl("knuckle", (x - 0.0045, HINGE[1], HINGE[2]), (x + 0.0045, HINGE[1], HINGE[2]), 0.0026, "steel", segs=12)
        weight = block("weight", (x, VENT_Y + 0.007, VENT_TOP + 0.0065), (0.006, 0.006, 0.003), "copper", bevel=0.0005)
        vent += [flap, rib, tab, knuckle, weight]
    root.append(cyl("hinge", (-VENT_X - 0.008, HINGE[1], HINGE[2]), (VENT_X + 0.008, HINGE[1], HINGE[2]), 0.0013, "bright", segs=8, bevel=0))
    # Copper feed line from the tank's front dome to the manifold, with a red handwheel valve.
    fpts = [(0, -0.087, TANK_Z), (0, -0.058, TANK_Z), (0, -0.034, 0.104), (0, 0.004, 0.096), (0, 0.014, 0.088)]
    root.append(sweep("feed", fpts, 0.0045, "copper", segs=12, rad=0.014, n=5))
    root.append(cyl("valve", (0, -0.052, TANK_Z - 0.003), (0, -0.04, TANK_Z - 0.01), 0.0085, "copper", segs=6, bevel=0.0004, bsegs=1))
    root.append(cyl("vstem", (0, -0.046, TANK_Z - 0.003), (0, -0.046, TANK_Z + 0.02), 0.0018, "bright", segs=8, bevel=0))
    root.append(ring("wheel", (0, -0.046, TANK_Z + 0.019), (0, 0, 1), 0.0135, 0.0105, 0.003, "red", segs=24))
    for k in range(3):
        a = math.radians(30 + k * 120)
        root.append(cyl("spoke", (0, -0.046, TANK_Z + 0.019), (0.0115 * math.cos(a), -0.046 + 0.0115 * math.sin(a), TANK_Z + 0.019), 0.0012,
                        "red", segs=6, bevel=0))
    root.append(cyl("whub", (0, -0.046, TANK_Z + 0.0175), (0, -0.046, TANK_Z + 0.022), 0.0032, "red", segs=10))

    # ---------------------------------------------------------------- rear motor drum (spins)
    root.append(ring("bearing", (0, -0.267, 0), (0, 1, 0), 0.079, 0.06, 0.008, "steel", segs=40))
    for k in range(10):
        a = math.radians(9 + k * 36)
        root.append(hexbolt((0.071 * math.cos(a), -0.263, 0.071 * math.sin(a)), "y", 0.0028, washer=False))
    dprof = [(0.06, 0.0), (0.077, 0.0), (0.079, 0.002), (0.079, 0.007), (0.073, 0.009)]
    for i in range(4):
        t = 0.011 + i * 0.006
        dprof += [(0.073, t), (0.082, t + 0.0005), (0.082, t + 0.0025), (0.073, t + 0.003)]
    dprof += [(0.073, 0.036), (0.08, 0.037), (0.082, 0.039), (0.082, 0.045), (0.06, 0.045)]
    spin.append(lathe("drum", dprof, (0, -0.271, 0), "-y", "steel", segs=40, closed=True, bevel=0))
    for k in range(12):
        a = math.radians(k * 30)
        c = Vector((math.cos(a), 0, math.sin(a)))
        spin.append(hexbolt(Vector((0, -0.316, 0)) + c * 0.071, "-y", 0.0028, washer=False))
    for k in range(6):
        a = math.radians(15 + k * 60)
        c = Vector((math.cos(a), 0, math.sin(a)))
        lug = block("lug", (0, 0, 0), (0.014, 0.03, 0.006), "steel", bevel=0.0008)
        spin.append(placed(lug, tuple(Vector((0, DRUM_Y - 0.003, 0)) + c * 0.084), (0, 90 - math.degrees(a), 0)))
        spin.append(hexbolt(Vector((0, DRUM_Y - 0.003, 0)) + c * 0.087, c, 0.0024, washer=False))
    spin.append(ring("winding", (0, DRUM_Y - 0.009, 0), (0, 1, 0), 0.0765, 0.072, 0.004, "copper", segs=40))
    spin.append(ring("rearring", (0, -0.318, 0), (0, 1, 0), 0.07, 0.061, 0.004, "bright", segs=40))

    # ---------------------------------------------------------------- knuckle ram (moving)
    yoke = prism("yoke", [(0.08, -0.054), (0.096, -0.058), (0.101, -0.054), (0.101, 0.05), (0.097, 0.056), (0.082, 0.056), (0.08, 0.053)],
                 0.176, "rust", bevel=0.0016, segs=2)
    ram.append(yoke)
    ram += hazard_top(-0.082, 0.082, 0.083, 0.096, 0.0563, pitch=0.012)
    for s in (-1, 1):
        x = s * PX
        cl = block("clevis", (x, 0.089, PZ), (0.03, 0.024, 0.03), "steel", bevel=0.0014)
        cl = cut(cl, block("slot", (x, 0.08, PZ), (0.012, 0.026, 0.04), "steel", bevel=0))
        ram.append(cl)
        ram.append(cyl("rpin", (x - 0.017, 0.087, PZ), (x + 0.017, 0.087, PZ), 0.0032, "bright", segs=12))
        ram.append(hexbolt((x + s * 0.0151, 0.087, PZ), (s, 0, 0), 0.0042))
        ram += hazard_side(0.0825, 0.0995, 0.0, 0.05, s * 0.0884, th=0.001, pitch=0.01)
        # guide rails slide through the bulkhead bushings
        ram.append(cyl("grail", (s * RAILX, -0.11, RAILZ), (s * RAILX, 0.081, RAILZ), 0.0062, "bright", segs=16))
        ram.append(cyl("rstop", (s * RAILX, -0.116, RAILZ), (s * RAILX, -0.109, RAILZ), 0.0095, "steel", segs=6, bevel=0.0004, bsegs=1))
        ram.append(weld((s * RAILX - 0.008, 0.08, RAILZ + 0.004), (s * RAILX + 0.008, 0.08, RAILZ + 0.004), (0, -1, 0), 0.0018))
    fronts = (0.146, 0.156, 0.155, 0.144)
    tops = (0.026, 0.04, 0.037, 0.024)
    for i, xc in enumerate((-0.039, -0.013, 0.013, 0.039)):
        yf, top, yb, bot = fronts[i], tops[i], 0.105, -0.036
        # rounded knuckle crown over a toothed striking face
        rr = 0.016
        cy, cz = yf - rr, top - rr
        pts = [(yb, bot), (yf - 0.009, bot), (yf - 0.003, bot + 0.006)]
        z = bot + 0.009
        while z + 0.0055 < cz:
            pts += [(yf - 0.0035, z), (yf, z + 0.0015), (yf, z + 0.004), (yf - 0.0035, z + 0.0055)]
            z += 0.0075
        pts += [(cy + rr * math.cos(math.radians(a)), cz + rr * math.sin(math.radians(a))) for a in range(0, 91, 15)]
        pts += [(yb + 0.004, top), (yb, top - 0.004)]
        kb = prism("knuckle", pts, 0.0215, "steel", x=xc, bevel=0.0007, segs=2)
        kb = cut(kb, hole_through("kh", (xc, 0.128, -0.012), 0.0042, "x", 0.04, segs=12))
        ram.append(kb)
        ram.append(block("pad", (xc, 0.103, (bot + top) / 2), (0.021, 0.004, top - bot - 0.006), "rubber", bevel=0.0006))
        ram.append(hexbolt((xc, 0.113, top), "z", 0.003, washer=False))
    # through pin tying the knuckles together, nutted on both sides
    ram.append(cyl("kpin", (-0.056, 0.128, -0.012), (0.056, 0.128, -0.012), 0.0036, "bright", segs=12))
    for s_ in (-1, 1):
        ram.append(cyl("knut", (s_ * 0.0505, 0.128, -0.012), (s_ * 0.0555, 0.128, -0.012), 0.0068, "steel", segs=6, bevel=0.0004, bsegs=1))
    ram.append(block("strap", (0, 0.118, -0.039), (0.098, 0.016, 0.006), "steel", bevel=0.0009))
    for xc in (-0.039, -0.013, 0.013, 0.039):
        ram.append(hexbolt((xc, 0.118, -0.042), "-z", 0.0028, washer=False))

    # ---------------------------------------------------------------- piston rods (moving with the ram)
    for s in (-1, 1):
        x = s * PX
        rods.append(cyl("rod", (x, -0.17, PZ), (x, 0.074, PZ), 0.0086, "bright", segs=24, bevel=0))
        rods.append(cyl("locknut", (x, 0.064, PZ), (x, 0.071, PZ), 0.0115, "steel", segs=6, bevel=0.0005, bsegs=1))
        eye = block("eye", (x, 0.083, PZ), (0.011, 0.024, 0.022), "steel", bevel=0.0012)
        rods.append(eye)

    for o in root:
        g.add(o, "root")
    for o in ram:
        g.add(o, "ram")
    for o in rods:
        g.add(o, "rods")
    for o in vent:
        g.add(o, "vent")
    for o in spin:
        g.add(o, "spin")
    g.socket("muzzle", (0, 0.155, 0), "ram")

    # ---------------------------------------------------------------- clips
    Z = (0, 0, 0)
    ram_fire = [(0, Z, Z), (0.06, (0, -0.003, 0), Z), (0.1, (0, 0.14, 0), Z), (0.16, (0, 0.136, 0), Z), (0.3, (0, 0.085, 0), Z),
                (0.48, (0, 0.02, 0), Z), (0.6, Z, Z)]
    g.clip("fire", 0.6, {
        "root": [(0, Z, Z), (0.05, (0, -0.014, -0.004), (2, 0, 0)), (0.1, (0, 0.075, 0.008), (-3, 0, -2)), (0.13, (0, 0.062, 0.013), (6, 0, 2)),
                 (0.35, (0, 0.012, 0.002), (1, 0, 0)), (0.6, Z, Z)],
        "ram": ram_fire,
        "rods": ram_fire,
        "vent": [(0, Z, Z), (0.1, Z, Z), (0.135, Z, (80, 0, 0)), (0.2, Z, (62, 0, 0)), (0.26, Z, (76, 0, 0)), (0.42, Z, (45, 0, 0)), (0.56, Z, Z)],
        "spin": spin_track(0.08, 0.6, turns=2, steps=12),
    })
    ram_charge = [(0, Z, Z), (0.2, (0, -0.004, 0), Z), (0.95, (0, -0.004, 0), Z), (1.05, Z, Z)]
    g.clip("reload", 1.2, {
        "root": [(0, Z, Z), (0.22, (-0.01, -0.02, 0.02), (14, -8, 16)), (0.9, (-0.01, -0.02, 0.022), (16, -10, 19)), (1.05, (0, 0, 0.004), (3, 0, 3)),
                 (1.2, Z, Z)],
        "ram": ram_charge,
        "rods": ram_charge,
        "vent": [(0, Z, Z), (0.15, Z, (82, 0, 0)), (0.3, Z, (64, 0, 0)), (0.45, Z, (84, 0, 0)), (0.6, Z, (66, 0, 0)), (0.8, Z, (80, 0, 0)),
                 (1.0, Z, (12, 0, 0)), (1.1, Z, Z)],
        "spin": spin_track(0.1, 1.08, turns=4, steps=20),
    })
    g.clip("draw", 0.5, {
        "root": [(0, (0, -0.05, -0.14), (-52, 0, 12)), (0.34, (0, 0.004, 0.004), (4, 0, 0)), (0.5, Z, Z)],
        "spin": spin_track(0.0, 0.5, turns=2, steps=10),
        "vent": [(0, Z, Z), (0.3, Z, Z), (0.36, Z, (55, 0, 0)), (0.48, Z, Z)],
    })
    ram_test = [(0, Z, Z), (1.0, Z, Z), (1.12, (0, 0.06, 0), Z), (1.5, Z, Z)]
    g.clip("inspect", 2.8, {
        "root": [(0, Z, Z), (0.5, (-0.03, 0.02, 0.03), (10, -35, 25)), (1.4, (-0.03, 0.02, 0.03), (12, -40, 30)), (1.9, (0.02, 0.0, 0.02), (-8, 30, -20)),
                 (2.5, Z, Z)],
        "ram": ram_test,
        "rods": ram_test,
        "vent": [(0, Z, Z), (1.12, Z, Z), (1.18, Z, (70, 0, 0)), (1.45, Z, (50, 0, 0)), (1.7, Z, Z)],
        "spin": spin_track(0.6, 2.2, turns=2, steps=14),
    })
    g.clip("idle", 2.0, {"root": [(0, Z, Z), (1.0, (0, 0, 0.0015), (0.6, 0, 0)), (2.0, Z, Z)]})
    return g


SPEC = {"build": build, "length": (0.4, 0.55), "tris": (20000, 70000), "muzzle_front": True,
        "bones": ["root", "ram", "rods", "vent", "spin"],
        "sockets": ["muzzle"],
        "parts": {"mesh.root": "root", "mesh.ram": "ram", "mesh.rods": "rods", "mesh.vent": "vent", "mesh.spin": "spin"},
        "moves": {"fire": ["root", "ram", "rods", "vent", "spin"], "reload": ["root", "vent", "spin", "ram", "rods"],
                  "draw": ["root", "spin", "vent"], "inspect": ["root", "ram", "rods", "vent", "spin"]},
        "view": {"cam": (-0.62, 0.34, 0.38), "look": (0, -0.07, 0.02), "lens": 50}}
