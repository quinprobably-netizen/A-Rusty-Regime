"""Contractor, PMC: a corporate private military contractor. A navy HALCYON plate carrier with laser-cut
MOLLE rows, rifle mag pouches, a velcro admin panel with sponsor patches and the hexagon-chevron company
mark, padded shoulder straps and a cummerbund; a baseball cap worn under an over-ear headset with a boom
mic, wraparound sunglasses, a combat shirt with sleeve pockets and shoulder patches, cargo trousers with
knee pads, a drop-leg holster and tactical boots.

Tints: primary = combat shirt, secondary = trousers, accent = carrier straps.

This module also holds the PMC hard-surface helpers that the juggernaut and handler share: panels built
flat and bent around the body, fitted to it with rays; ellipsoid and limb-wrapping armour patches; swept
straps; the company mark and sponsor patches.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import kit
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS, FEET

# PMC fixed colours. name: (base, worn, metallic, roughness, edge wear, emission)
kit.hs.PALETTE.update({
    "pmc_navy": ((0.075, 0.12, 0.21), (0.30, 0.34, 0.40), 0.0, 0.75, 0.35, 0),       # carrier nylon
    "pmc_velcro": ((0.10, 0.105, 0.11), (0.18, 0.18, 0.19), 0.0, 0.95, 0.15, 0),    # loop field
    "pmc_plate": ((0.80, 0.81, 0.82), (0.93, 0.93, 0.93), 0.0, 0.38, 0.45, 0),      # white hard plate
    "pmc_navy_hard": ((0.07, 0.11, 0.20), (0.40, 0.44, 0.50), 0.0, 0.42, 0.55, 0),  # navy hard plate
})


# --------------------------------------------------------------------------- PMC hard-surface helpers

def tree(obj):
    """A ray-cast tree of a mesh in world space."""
    mw = obj.matrix_world
    return BVHTree.FromPolygons([mw @ v.co for v in obj.data.vertices], [p.vertices[:] for p in obj.data.polygons])


def hit(t, origin, d):
    loc, nor, _, _ = t.ray_cast(Vector(origin), Vector(d).normalized())
    return loc, nor


def frame(origin, n, up=(0, 0, 1)):
    """The matrix taking flat build space (front toward -Y, up +Z, origin at 0) to `origin`, facing `n`."""
    n = Vector(n).normalized()
    u = Vector(up)
    u = (u - n * u.dot(n)).normalized()
    r = (-n).cross(u)
    m = Matrix((r, -n, u)).transposed().to_4x4()
    m.translation = Vector(origin)
    return m


def slice_x(obj, step=0.02):
    """Add vertical edge loops every `step` so a flat part can bend smoothly."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    xs = [v.co.x for v in bm.verts]
    x0, x1 = min(xs), max(xs)
    n = int((x1 - x0) / step)
    for i in range(1, n):
        x = x0 + (x1 - x0) * i / n
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-6, plane_co=(x, 0, 0), plane_no=(1, 0, 0))
    bm.to_mesh(obj.data)
    bm.free()


def bend_pt(p, R):
    x, y, z = p
    r = R - y
    a = x / R
    return Vector((r * math.sin(a), R - r * math.cos(a), z))


def bend(obj, R):
    """Wrap a part built flat (back on the y=0 plane, front toward -Y) around a vertical cylinder of
    radius R whose axis runs through (0, R): a carrier panel around a chest, a patch around an arm."""
    for v in obj.data.vertices:
        v.co = bend_pt(v.co, R)
    obj.data.update()


def put(objs, M, R=None, step=None):
    """Bend flat parts (if R) and move them into place with frame matrix M. Parts get an edge loop
    every `step` (default every 8.6 degrees of bend) so they curve smoothly."""
    step = step or (R * 0.15 if R else 1.0)
    for o in objs:
        if R:
            xs = [v.co.x for v in o.data.vertices]
            if max(xs) - min(xs) > step * 1.3 and not o.name.startswith("label"):
                slice_x(o, step)
            bend(o, R)
        o.data.transform(M)
    return objs


def to_world(p, M, R=None):
    return M @ (bend_pt(p, R) if R else Vector(p))


def inside_poly(x, z, pts):
    c = False
    for i in range(len(pts)):
        (x0, z0), (x1, z1) = pts[i - 1], pts[i]
        if (z0 > z) != (z1 > z) and x < x0 + (z - z0) * (x1 - x0) / (z1 - z0):
            c = not c
    return c


def fit(t, pts, R, clear, side=-1, step=0.012, tilt=0.0):
    """Place a panel with outline `pts` [(x, z)], bent with radius R, on the front (side -1) or back
    (+1) of the body so its back clears the surface in tree `t` by `clear`, its top leaning `tilt`
    degrees in toward the body. Returns the frame matrix for the panel's flat build space."""
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    zc = (min(zs) + max(zs)) / 2
    tn = math.tan(math.radians(tilt))
    best = None
    nx, nz = int((max(xs) - min(xs)) / step) + 1, int((max(zs) - min(zs)) / step) + 1
    for i in range(nx + 1):
        x = min(xs) + (max(xs) - min(xs)) * i / nx
        for j in range(nz + 1):
            z = min(zs) + (max(zs) - min(zs)) * j / nz
            if not inside_poly(x, z, pts):
                continue
            loc, _ = hit(t, (x * -side if side > 0 else x, side * 1.0, z), (0, -side, 0))
            if loc is None:
                continue
            cand = loc.y + side * (clear + R * (1 - math.cos(x / R)) + (z - zc) * tn)
            if best is None or (cand < best if side < 0 else cand > best):
                best = cand
    rot = Matrix.Rotation(math.radians(tilt if side > 0 else -tilt), 4, "X")
    M = Matrix.Translation((0, best, zc)) @ rot @ Matrix.Translation((0, 0, -zc))
    if side > 0:
        M = M @ Matrix.Rotation(math.pi, 4, "Z")
    return M


def ring_pts(t, c, z, offset, n=28, rx=None):
    """A loop around the body at height z: rays from inside out, pushed `offset` past the surface."""
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        d = Vector((math.sin(a), -math.cos(a), 0))
        loc, _ = hit(t, (c[0], c[1], z), d)
        r = (Vector((loc.x, loc.y, z)) - Vector((c[0], c[1], z))).length if loc else 0.12
        out.append(Vector((c[0], c[1], z)) + d * (r + offset))
    return out


def smooth_path(pts, n=4, closed=False):
    """Catmull-Rom points through `pts`, `n` per span."""
    P = [Vector(p) for p in pts]
    m = len(P)
    out = []
    spans = m if closed else m - 1
    for i in range(spans):
        p0 = P[(i - 1) % m] if closed else P[max(0, i - 1)]
        p1, p2 = P[i], P[(i + 1) % m]
        p3 = P[(i + 2) % m] if closed else P[min(m - 1, i + 2)]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-1])
    return out


def sweep(name, pts, width, thick, material, normal, closed=False, bevel=None):
    """A flat strap along points with its face normal from `normal(p)` (kit.strap with a per-point
    normal, so a strap over a shoulder lies flat on it)."""
    pts = [Vector(p) for p in pts]
    m = len(pts)
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(pts):
        if closed:
            a, c = pts[i - 1], pts[(i + 1) % m]
        else:
            a, c = pts[max(0, i - 1)], pts[min(m - 1, i + 1)]
        tan = (c - a).normalized()
        nn = Vector(normal(p))
        nn = (nn - tan * nn.dot(tan)).normalized()
        sd = tan.cross(nn).normalized()
        rings.append([bm.verts.new(p + sd * sw * width / 2 + nn * k * thick / 2) for sw, k in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    segs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for r0, r1 in segs:
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = kit.hs._obj(name, bm, material, min(width, thick) * 0.3 if bevel is None else bevel)
    o["segs"] = 1
    return o


def radial(c, axis=(0, 0, 1)):
    """A normal function for sweep: away from the line through c along axis."""
    c, a = Vector(c), Vector(axis).normalized()

    def f(p):
        d = Vector(p) - c
        return d - a * d.dot(a)
    return f


def _grid_obj(name, rows, closed_u, material, thick, bevel, centre, pole=None):
    """Faces between rows of points, oriented away from `centre`, thickened outward."""
    bm = bmesh.new()
    vrows = [[bm.verts.new(p) for p in row] for row in rows]
    n = len(rows[0])
    for r0, r1 in zip(vrows, vrows[1:]):
        for j in range(n if closed_u else n - 1):
            k = (j + 1) % n
            bm.faces.new((r0[j], r0[k], r1[k], r1[j]))
    if pole is not None:
        top = bm.verts.new(pole)
        r0 = vrows[-1]
        for j in range(n if closed_u else n - 1):
            k = (j + 1) % n
            bm.faces.new((r0[j], r0[k], top))
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    f = bm.faces[len(bm.faces) // 2]
    if f.normal.dot(f.calc_center_median() - Vector(centre)) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    o = kit.hs._obj(name, bm, material, 0.0)
    if thick:
        sm = o.modifiers.new("thick", "SOLIDIFY")
        sm.thickness = thick
        sm.offset = 1.0
        sm.use_even_offset = True
        sm.use_rim = True
        kit.hs._apply(o, sm.name)
    o["bevel"] = bevel
    o["segs"] = 2
    return o


def dome(name, M, radii, lat0, lat1, thick, material, lon0=-180.0, lon1=180.0, nlat=8, nlon=24, bevel=0.003):
    """A patch of an ellipsoid (local pole +Z, radii rx, ry, rz) between latitudes and longitudes in
    degrees, thickened outward, placed by matrix M: pauldrons, knee cops, helmet shells."""
    rx, ry, rz = radii
    full = abs(lon1 - lon0) >= 359.99
    pole = lat1 >= 89.99
    lats = [lat0 + (lat1 - lat0) * i / nlat for i in range(nlat + (0 if pole else 1))]
    lons = [lon0 + (lon1 - lon0) * j / nlon for j in range(nlon if full else nlon + 1)]

    def P(la, lo):
        la, lo = math.radians(la), math.radians(lo)
        return M @ Vector((rx * math.cos(la) * math.cos(lo), ry * math.cos(la) * math.sin(lo), rz * math.sin(la)))
    rows = [[P(la, lo) for lo in lons] for la in lats]
    return _grid_obj(name, rows, full, material, thick, bevel, M.translation, pole=(M @ Vector((0, 0, rz))) if pole else None)


def wrap(name, a, b, r0, r1, phi0, phi1, thick, material, front=(0, -1, 0), nt=6, nphi=16, bevel=0.003, ef=1.0, es=1.0, bulge=0.0):
    """A plate wrapped around the segment a->b (a limb): a tapered elliptic cylinder patch of radius
    r0 at a to r1 at b, from angle phi0 to phi1 (degrees; 0 faces `front`, +90 faces front x axis,
    which is the outside of a left limb hanging down). `bulge` swells the middle (a rounded greave)."""
    a, b = Vector(a), Vector(b)
    A = (b - a).normalized()
    F = Vector(front)
    F = (F - A * F.dot(A)).normalized()
    S = F.cross(A).normalized()
    closed = abs(phi1 - phi0) >= 359.9
    rows = []
    for i in range(nt + 1):
        t = i / nt
        r = r0 + (r1 - r0) * t + bulge * math.sin(math.pi * t)
        c = a.lerp(b, t)
        rows.append([c + F * math.cos(math.radians(p)) * r * ef + S * math.sin(math.radians(p)) * r * es
                     for p in [phi0 + (phi1 - phi0) * j / nphi for j in range(nphi if closed else nphi + 1)]])
    o = _grid_obj(name, rows, closed, material, thick, bevel, a.lerp(b, 0.5))
    return o


def grow(pts, d):
    """Push an outline [(x, z)] out from its centroid by about d."""
    cx = sum(p[0] for p in pts) / len(pts)
    cz = sum(p[1] for p in pts) / len(pts)
    out = []
    for x, z in pts:
        v = Vector((x - cx, z - cz))
        out.append((cx + v.x * (1 + d / max(v.length, 1e-6)), cz + v.y * (1 + d / max(v.length, 1e-6))))
    return out


def hazard_band(x0, x1, z0, z1, y, slant=0.7):
    """A yellow strip with black diagonal bars, in flat space."""
    h = z1 - z0
    out = [panel("hazard", [(x0, z0), (x1, z0), (x1, z1), (x0, z1)], y, 0.0015, "hazard", bevel=0.0)]
    w, step = h * 0.7, h * 1.6
    x = x0 + h * 0.3
    while x + w + h * slant < x1 - h * 0.2:
        out.append(panel("hazard_bar", [(x, z0), (x + w, z0), (x + w + h * slant, z1), (x + h * slant, z1)], y - 0.0015, 0.001, "black", bevel=0.0))
        x += step
    return out


def half_space(name, p, n, size=0.8):
    """A big box filling the side of the plane through p that n points to (a cutter)."""
    o = kit.block(name, (0, 0, size / 2), (size, size, size), "steel", bevel=0)
    q = Vector((0, 0, 1)).rotation_difference(Vector(n).normalized())
    o.data.transform(Matrix.Translation(Vector(p)) @ q.to_matrix().to_4x4())
    return o


def rrect(x0, z0, x1, z1, r=0.006):
    return kit.rounded([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], r)


def panel(name, pts, y_back, thick, material, bevel=0.002):
    """A flat panel with outline pts [(x, z)] from y_back toward the front (-Y) by `thick`."""
    return kit.slab(name, pts, y_back - thick, y_back, material, bevel=bevel)


def hexagon(cx, cz, r, rot=90.0):
    return [(cx + r * math.cos(math.radians(rot + 60 * i)), cz + r * math.sin(math.radians(rot + 60 * i))) for i in range(6)]


def logo(cx, cz, size, y, base="white", inset="pmc_navy", mark="hazard"):
    """The company mark in flat space: a white hexagon badge, a navy inset and two stacked yellow
    chevrons, raised in layers from y toward the front."""
    out = [panel("logo", hexagon(cx, cz, size * 0.5), y, 0.0018, base, bevel=0.0),
           panel("logo", hexagon(cx, cz, size * 0.4), y - 0.0012, 0.0012, inset, bevel=0.0)]
    for dz in (0.07, -0.13):
        ch = [(0, 0.12), (0.2, -0.06), (0.2, -0.15), (0, 0.03), (-0.2, -0.15), (-0.2, -0.06)]
        out.append(panel("logo", [(cx + x * size, cz + (z + dz) * size) for x, z in ch], y - 0.0018, 0.0012, mark, bevel=0.0))
    return out


def text(t, x, z, size, y, material, depth=0.0006):
    """Raised lettering in flat space, standing proud of y (kit.label_front with coarser curves:
    the same lettering at about two thirds of the triangles)."""
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = t
    cu.size = size
    cu.extrude = depth
    cu.resolution_u = 2
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    o = bpy.data.objects.new("label", cu)
    bpy.context.scene.collection.objects.link(o)
    o.location = (x, y - depth, z)
    o.rotation_euler = (math.pi / 2, 0, 0)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    mw = o.matrix_world.copy()
    bpy.data.objects.remove(o, do_unlink=True)
    me.transform(mw)
    me.materials.clear()
    me.materials.append(kit.mat(material))
    out = bpy.data.objects.new("label", me)
    bpy.context.scene.collection.objects.link(out)
    out["bevel"] = 0.0
    return out


def name_patch(t, cx, cz, w, h, y, base="white", ink="pmc_navy", size=None):
    """A sponsor patch: a rounded tab with raised lettering."""
    size = size or h * 0.62
    return [panel("patch", rrect(cx - w / 2, cz - h / 2, cx + w / 2, cz + h / 2, min(w, h) * 0.2), y, 0.0022, base, bevel=0.0),
            text(t, cx, cz, size, y - 0.0022, ink)]


def screws(pts, y, r=0.0035, material="gunmetal"):
    """Socket-head screws in flat space, facing the front."""
    return [screw((x, y - 0.0008, z), "-y", r=r, material=material) for x, z in pts]


def screw(at, axis="-y", r=0.0035, material="gunmetal", head=0.0018):
    """kit.screw with crisp unbevelled edges (a bevelled screw costs ~400 triangles)."""
    o = kit.screw(at, axis, r=r, material=material, head=head)
    o["bevel"] = 0.0
    return o


def economise(c):
    """Single-segment bevels on every small or finely bevelled part."""
    for o, _, _ in c.parts:
        bv = o.get("bevel", 0.0)
        if bv and (bv <= 0.0026 or max(o.dimensions) < 0.05):
            o["segs"] = 1


def boot(c, b, s, upper="black", trim="grey", sole_mat="rubber", lace="grey", tab="hazard", top=0.205, scale=1.0, heavy=False):
    """A tactical boot around one foot: a fused upper cut clean at the ankle, a treaded sole, toe cap,
    heel counter, ray-placed laces and a pull tab. Returns the upper (cloth-weighted to foot and
    shin); the hard parts are added rigid to the foot."""
    sx = 1 if s == "L" else -1
    x = b.j("foot." + s, 0.0).x
    k = scale
    q = b.k  # lengths follow the build
    el = [kit.capsule((x, 0.002, top + 0.02), (x, 0.0, 0.07), 0.056 * k),
          kit.ellipsoid((x, 0.03 * q, 0.05), 1.0, (0.048 * k, 0.052 * q, 0.046)),
          kit.capsule((x, 0.02 * q, 0.045), (x + sx * 0.004, -0.19 * q, 0.036), 0.047 * k, r1=0.044 * k),
          kit.ellipsoid((x + sx * 0.003, -0.175 * q, 0.04), 1.0, (0.054 * k, 0.07 * q, 0.038))]
    up = kit.meta("boot", el, upper, res=0.006, target=1100, smooth_iter=4)
    up = kit.intersect(up, half_space("boot_top", (x, 0, top), (0, 0, -1), size=0.4))
    up = kit.intersect(up, half_space("boot_bottom", (x, 0, 0.012), (0, 0, 1), size=0.4))
    tb = tree(up)
    rig = "foot." + s
    sole_pts = kit.rounded([(x - 0.054 * k, 0.095 * q), (x + 0.054 * k, 0.095 * q), (x + 0.062 * k, -0.2 * q), (x + 0.032 * k, -0.25 * q),
                            (x - 0.032 * k, -0.25 * q), (x - 0.058 * k, -0.2 * q)], 0.03, n=2)
    sole = kit.plan("sole", sole_pts, 0.03 if not heavy else 0.04, sole_mat, z=0.015 if not heavy else 0.02, bevel=0.0025)
    kit.cut(sole, *kit.slots("tread", -0.21 * q, 0.06 * q, 7, -0.002, 0.006, x - 0.09, x + 0.09))
    c.rigid(sole, rig)
    # Toe cap and heel counter: conforming layers over the upper with clean curved edges.
    c.rigid(kit.shell(up, lambda p: p.y < -0.1, "toe_cap", trim, offset=0.002, thick=0.005, detail=1.0,
                      inside=[kit.blob_cutter("toe_cut", (x, -0.26 * q, 0.0), (0.13 * k, 0.12 * q, 0.062))]), rig)
    c.rigid(kit.shell(up, lambda p: p.y > 0.0, "heel_counter", trim, offset=0.002, thick=0.005, detail=1.0,
                      inside=[kit.blob_cutter("heel_cut", (x, 0.1 * q, 0.0), (0.12 * k, 0.085 * q, 0.1))]), rig)
    # Laces up the tongue, found with rays.
    for i in range(5):
        z = 0.075 + i * 0.026
        loc, nor = hit(tb, (x, -0.5, z), (0, 1, 0))
        if loc is None:
            continue
        o = kit.block("lace", (0, 0, 0), (0.042 * k, 0.006, 0.006), lace, bevel=0.001)
        q = Vector((0, -1, 0)).rotation_difference(nor)
        o.data.transform(Matrix.Translation(loc + nor * 0.002) @ q.to_matrix().to_4x4() @ Matrix.Rotation(math.radians(18 if i % 2 else -18), 4, "Y"))
        c.rigid(o, rig)
    loc, nor = hit(tb, (x, 0.5, top - 0.02), (0, -1, 0))
    c.rigid(kit.block("pull_tab", loc + Vector((0, 0.006, 0.012)), (0.018, 0.006, 0.04), tab, bevel=0.0015), rig)
    return up


def cloth(c, obj, far=0.075, extra=()):
    """Skin a garment like Char.add (weights copied from the nearest body surface), but drop forearm
    and hand influence from vertices more than `far` from those bones: the hanging forearms sit next
    to the hips, so a waistband would otherwise follow the arms and tear into shards."""
    kit.hs.apply_modifiers(obj)
    kit.transfer(c.skin_source, obj)
    arm = ("forearm.L", "forearm.R", "hand.L", "hand.R") + tuple(extra)
    names = {g.index: g.name for g in obj.vertex_groups}
    segs = {n: (Vector(c.b.all[n][0]), Vector(c.b.all[n][1])) for n in arm}
    groups = {g.name: g for g in obj.vertex_groups}
    mw = obj.matrix_world
    for v in obj.data.vertices:
        p = mw @ v.co
        bad = [g for g in v.groups if names[g.group] in segs and kit.seg_dist(p, *segs[names[g.group]]) > far]
        if not bad:
            continue
        for g in bad:
            g.weight = 0.0
        tot = sum(g.weight for g in v.groups)
        if tot > 1e-4:
            for g in v.groups:
                g.weight /= tot
        else:
            for bn, w in kit.weights_at(c.b, p, sorted(TORSO | THIGHS)).items():
                if bn not in groups:
                    groups[bn] = obj.vertex_groups.new(name=bn)
                groups[bn].add([v.index], w, "REPLACE")
    c.parts.append((obj, "DONE", None))
    return obj


def band(name, c, radii, width, thick, material, axis=(0, 0, 1)):
    """kit.band at 16 segments."""
    return kit.band(name, c, radii, width, thick, material, axis=axis, segs=16)


def rigid_all(c, objs, bone):
    for o in objs:
        c.rigid(o, bone)


def side_buckle(name, at, axis_u, axis_n, w=0.032, material="black"):
    """A side-release buckle (male + female halves) along strap direction axis_u, facing axis_n."""
    u, n = Vector(axis_u).normalized(), Vector(axis_n).normalized()
    s = u.cross(n)
    M = Matrix((s, u, n)).transposed().to_4x4()
    M.translation = Vector(at)
    body = kit.block(name, (0, 0, 0), (w, 0.034, 0.008), material, bevel=0.0012)
    kit.cut(body, kit.block("slot", (0, 0.004, 0.004), (w * 0.55, 0.012, 0.006), "steel", bevel=0))
    prong = kit.block(name, (0, -0.022, 0), (w * 0.75, 0.012, 0.006), material, bevel=0.001, taper=(0.8, 1.0))
    o = kit.join([body, prong], name)
    o.data.transform(M)
    return o


# ------------------------------------------------------------------------------------------ build

def build():
    b = kit.Build(height=1.80, width=1.0, bulk=1.0)
    c = kit.begin("contractor", b)
    parts = kit.body(b, skin="skin", head=False, neck=1.2)
    flesh = c.flesh(parts["body"])
    head = kit.head_mesh(b, "skin", jaw=1.12, brow=1.05)
    c.add(head, kit.HEAD_BONES)
    hc = b.j("head", 0.45)
    tf = tree(flesh)
    wrists = [b.j("hand.L", 0.0), b.j("hand.R", 0.0)]

    def off_wrist(p, d=0.03):
        return all((p - w).length > d for w in wrists)

    # Gloves: black, with grey hard knuckles and a velcro cuff.
    hands = parts["hands"]
    hands.data.materials[0] = kit.mat("black")
    c.add(hands, kit.HAND_BONES)
    for s, sx in (("L", 1), ("R", -1)):
        hb = Vector(b.all["hand." + s][0])
        down = (Vector(b.all["hand." + s][1]) - hb).normalized()
        knuckle = hb + down * 0.092 + Vector((sx * 0.012, -0.002, 0))
        guard = kit.block("knuckle", (0, 0, 0), (0.018, 0.078, 0.024), "grey", bevel=0.0025)
        kit.cut(guard, *[kit.block("groove", (0.01, y, 0), (0.006, 0.003, 0.03), "steel", bevel=0) for y in (-0.019, 0.0, 0.019)])
        guard.data.transform(Matrix.Translation(knuckle))
        c.rigid(guard, "hand." + s)
        fa = b.j("forearm." + s, 0.93)
        fax = b.j("hand." + s, 0.0) - b.j("forearm." + s, 0.0)
        c.rigid(band("glove_cuff", b.j("hand." + s, 0.0) - fax.normalized() * 0.01, (0.044, 0.039), 0.066, 0.008, "black", axis=fax), "hand." + s)
        c.rigid(band("cuff_tab", b.j("hand." + s, 0.0) - fax.normalized() * 0.03, (0.0485, 0.0435), 0.014, 0.005, "grey", axis=fax), "hand." + s)

    # Combat shirt: torso and sleeves to the wrist, a round neck with a collar, cuffs.
    neck_cut = kit.cyl("neck_cut", (0, 0.003, 1.448), (0, 0.003, 1.75), 0.082, "steel", segs=32, bevel=0)
    wrist_cuts = [half_space("wrist_cut", b.j("forearm." + s, 0.84), b.j("hand." + s, 0.0) - b.j("forearm." + s, 0.0), size=0.18) for s in ("L", "R")]
    shirt = kit.shell(flesh, lambda p: 0.86 < p.z < 1.50 and off_wrist(p, 0.03), "shirt", "primary",
                      offset=0.012, thick=0.004, smooth_iter=2, detail=0.42, outside=[neck_cut] + wrist_cuts)
    cloth(c, shirt)
    c.cover(TORSO | UPPER_ARMS | FOREARMS, lambda p: p.z > 0.9 and p.z < 1.44 and off_wrist(p, 0.07))
    c.cover(TORSO | THIGHS, lambda p: 0.86 < p.z < 1.1)
    c.cover(FOREARMS, lambda p: not off_wrist(p, 0.05))
    collar = band("collar", Vector((0, 0.002, 1.458)), (0.09, 0.078), 0.03, 0.007, "primary")
    c.add(collar)
    for s, sx in (("L", 1), ("R", -1)):
        fa0, fa1 = b.j("forearm." + s, 0.0), b.j("forearm." + s, 1.0)
        c.rigid(band("sleeve_cuff", b.j("forearm." + s, 0.8), (0.054, 0.05), 0.05, 0.008, "primary", axis=fa1 - fa0), "forearm." + s)
        # Elbow pad: a hard black plate wrapped round the point of the elbow.
        ax = (fa1 - fa0).normalized()
        pad = wrap("elbow_pad", fa0 - ax * 0.03, fa0 + ax * 0.055, 0.058, 0.053, 180 - 55 * sx, 180 + 55 * sx, 0.009, "black",
                   nt=4, nphi=8, bevel=0.003, bulge=0.004)
        c.rigid(pad, "forearm." + s)

    tshirt = tree(shirt)

    # Sleeve pockets on the upper arms with sponsor patches: ARGENT-7 left, the company mark right.
    for s, sx in (("L", 1), ("R", -1)):
        ua0, ua1 = b.j("upper_arm." + s, 0.0), b.j("upper_arm." + s, 1.0)
        ax = (ua0 - ua1).normalized()  # up the arm
        n = Vector((sx, 0, 0))
        n = (n - ax * n.dot(ax)).normalized()
        n = (n + Vector((0, -0.25, 0))).normalized()
        n = (n - ax * n.dot(ax)).normalized()
        centre = ua0.lerp(ua1, 0.36)
        loc, _ = hit(tshirt, centre + n * 0.3, -n)
        R = (loc - centre).length
        M = frame(loc, n, ax)
        objs = [panel("sleeve_pocket", rrect(-0.04, -0.05, 0.04, 0.05, 0.01), 0.002, 0.007, "primary", bevel=0.002),
                panel("pocket_flap", rrect(-0.042, 0.035, 0.042, 0.058, 0.006), -0.003, 0.006, "primary", bevel=0.0018),
                panel("velcro", rrect(-0.033, -0.042, 0.033, 0.028, 0.006), -0.005, 0.002, "pmc_velcro", bevel=0.0006)]
        if s == "L":
            objs += name_patch("ARGENT-7", 0, -0.002, 0.058, 0.026, -0.007, base="white", ink="black", size=0.0125)
            objs += [panel("stripe", rrect(-0.027, -0.03, 0.027, -0.022, 0.002), -0.007, 0.002, "hazard", bevel=0.0004)]
        else:
            objs += logo(0, 0.0, 0.05, -0.007)
            objs += [panel("stripe", rrect(-0.027, -0.037, 0.027, -0.03, 0.002), -0.007, 0.002, "hazard", bevel=0.0004)]
        put(objs, M, R, step=0.012)
        rigid_all(c, objs, "upper_arm." + s)

    # ---------------------------------------------------------------- plate carrier
    R = 0.30
    th = 0.032
    f_out = kit.rounded([(-0.125, 1.03), (0.125, 1.03), (0.125, 1.29), (0.072, 1.372), (-0.072, 1.372), (-0.125, 1.29)], 0.02)
    MF = fit(tf, f_out, R, 0.022, side=-1, tilt=5)
    front = [panel("carrier_front", f_out, 0.0, th, "pmc_navy", bevel=0.007)]
    # Laser-cut MOLLE: three rows of slots across the plate.
    slot_cut = [kit.block("slot", (x, -th, z), (0.036, 0.007, 0.0075), "steel", bevel=0)
                for z in (1.168, 1.196, 1.224) for x in (-0.075, -0.025, 0.025, 0.075)]
    kit.cut(front[0], *slot_cut)
    y1 = -th
    front += [panel("velcro", rrect(-0.08, 1.252, 0.08, 1.343, 0.008), y1, 0.003, "pmc_velcro", bevel=0.001)]
    front += name_patch("HALCYON", 0, 1.322, 0.128, 0.03, y1 - 0.003, base="white", ink="pmc_navy", size=0.021)
    front += logo(-0.048, 1.279, 0.036, y1 - 0.003)
    front += name_patch("07", 0.012, 1.279, 0.03, 0.024, y1 - 0.003, base="hazard", ink="black", size=0.016)
    front += name_patch("A POS", 0.056, 1.279, 0.036, 0.024, y1 - 0.003, base="black", ink="white", size=0.0095)
    # Three rifle mag pouches with yellow pull tabs and bungee retention.
    for x in (-0.08, 0.0, 0.08):
        p = [kit.block("mag_pouch", (x, y1 - 0.021, 1.085), (0.07, 0.042, 0.13), "pmc_navy", bevel=0.006),
             kit.block("pouch_flap", (x, y1 - 0.023, 1.142), (0.074, 0.048, 0.03), "pmc_navy", bevel=0.005),
             kit.block("bungee", (x, y1 - 0.043, 1.08), (0.072, 0.004, 0.012), "black", bevel=0.0015),
             kit.block("pull_tab", (x, y1 - 0.05, 1.132), (0.026, 0.005, 0.034), "hazard", bevel=0.0015)]
        p += [kit.block("stitch", (x + dx, y1 - 0.0425, 1.085), (0.003, 0.002, 0.11), "black", bevel=0) for dx in (-0.031, 0.031)]
        front += p
    put(front, MF, R)
    rigid_all(c, front, "chest")

    b_out = kit.rounded([(-0.128, 1.03), (0.128, 1.03), (0.128, 1.29), (0.1, 1.36), (-0.1, 1.36), (-0.128, 1.29)], 0.025)
    MB = fit(tf, b_out, R, 0.022, side=1, tilt=6)
    back = [panel("carrier_back", b_out, 0.0, th, "pmc_navy", bevel=0.007)]
    kit.cut(back[0], *[kit.block("slot", (x, -th, z), (0.036, 0.007, 0.0075), "steel", bevel=0)
                       for z in (1.158, 1.186, 1.214, 1.242) for x in (-0.075, -0.025, 0.025, 0.075)])
    front_y = -th
    back += name_patch("VANTA LOGISTICS", 0, 1.302, 0.21, 0.032, front_y, base="white", ink="black", size=0.0165)
    back += [panel("stripe", rrect(-0.105, 1.276, 0.105, 1.282, 0.002), front_y, 0.002, "hazard", bevel=0.0004)]
    # Drag handle at the top, a general-purpose pouch low on the back.
    handle = sweep("drag_handle", smooth_path([(-0.04, front_y + 0.004, 1.335), (-0.032, front_y - 0.018, 1.37), (0.032, front_y - 0.018, 1.37),
                                               (0.04, front_y + 0.004, 1.335)], 4), 0.026, 0.005, "black", radial((0, front_y + 0.01, 1.33), (1, 0, 0)))
    back += [handle]
    back += [kit.block("gp_pouch", (0, front_y - 0.026, 1.085), (0.16, 0.052, 0.105), "pmc_navy", bevel=0.008),
             kit.block("zip", (0, front_y - 0.0525, 1.122), (0.15, 0.004, 0.006), "black", bevel=0.001),
             kit.block("zip_pull", (0.05, front_y - 0.055, 1.112), (0.008, 0.004, 0.022), "hazard", bevel=0.001)]
    back += name_patch("HALCYON", 0, 1.08, 0.08, 0.02, front_y - 0.052, base="pmc_navy", ink="white", size=0.013)
    # Radio on the MOLLE, upper left, with a whip antenna and a channel knob.
    radio = kit.block("radio", (-0.088, front_y - 0.02, 1.205), (0.058, 0.036, 0.112), "black", bevel=0.004)
    kit.cut(radio, *[kit.block("grip", (-0.088, front_y - 0.038, 1.17 + i * 0.012), (0.062, 0.006, 0.004), "steel", bevel=0) for i in range(4)])
    back += [radio,
             kit.block("radio_strap", (-0.088, front_y - 0.039, 1.23), (0.064, 0.004, 0.018), "pmc_navy", bevel=0.001),
             kit.cyl("radio_knob", (-0.072, front_y - 0.02, 1.261), (-0.072, front_y - 0.02, 1.274), 0.008, "grey", segs=14, bevel=0.0015),
             kit.cyl("antenna_base", (-0.103, front_y - 0.02, 1.261), (-0.103, front_y - 0.02, 1.282), 0.007, "black", segs=12, bevel=0.001),
             kit.cyl("antenna", (-0.103, front_y - 0.02, 1.28), (-0.118, front_y - 0.03, 1.44), 0.0035, "rubber", r1=0.0025, segs=8, bevel=0)]
    back += name_patch("CH 7", -0.088, 1.2, 0.034, 0.016, front_y - 0.038, base="hazard", ink="black", size=0.0095)
    put(back, MB, R)
    rigid_all(c, back, "chest")

    # Padded shoulder straps (accent) with buckles, over the shirt.
    for s, sx in (("L", 1), ("R", -1)):
        xs = sx * 0.085
        pts = []
        for y in (-0.13, -0.10, -0.07, -0.04, -0.01, 0.02, 0.05, 0.08, 0.11, 0.13):
            loc, _ = hit(tshirt, (xs, y, 1.7), (0, 0, -1))
            z = loc.z + 0.008 if loc and loc.z > 1.3 else None
            pts.append((xs, y, z))
        # Ends drop down to the plate tops.
        pts = [(xs, y, z if z is not None else 1.36) for xs, y, z in pts]
        pts[0] = to_world((sx * 0.07, -0.012, 1.352), MF, R)
        pts[-1] = to_world((-sx * 0.075, -0.012, 1.34), MB, R)
        path = smooth_path(pts, 3)
        nrm = radial((sx * 0.085, 0, 1.33), (1, 0, 0))
        strap = sweep("shoulder_strap", path, 0.05, 0.013, "accent", nrm)
        c.rigid(strap, "chest")
        k = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.072))
        tan = (path[k + 1] - path[k - 1]).normalized()
        nn = nrm(path[k]).normalized()
        c.rigid(side_buckle("strap_buckle", path[k] + nn * 0.009, -tan, nn, w=0.04), "chest")
        if s == "L":
            # Push-to-talk on the left strap, cabled over the shoulder to the radio on the back.
            k2 = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.035))
            t2 = (path[k2 + 1] - path[k2 - 1]).normalized()
            n2 = nrm(path[k2]).normalized()
            Mp = frame(path[k2] + n2 * 0.0065, n2, t2)
            ptt = [kit.block("ptt", (0, -0.009, 0), (0.034, 0.018, 0.042), "black", bevel=0.003),
                   kit.cyl("ptt_button", (0, -0.017, 0.004), (0, -0.023, 0.004), 0.009, "hazard", segs=14, bevel=0.0015)]
            put(ptt, Mp)
            rigid_all(c, ptt, "chest")
            ptt_top = Mp @ Vector((0, -0.01, 0.022))
            radio_top = to_world((-0.088, -th - 0.02, 1.27), MB, R)
            over = [path[i] + nrm(path[i]).normalized() * 0.014 + Vector((0.026, 0, 0)) for i in range(k2 + 3, len(path) - 4, 3)]
            c.rigid(kit.rope("ptt_cable", [ptt_top] + over + [radio_top + Vector((0.0, 0.01, 0.02)), radio_top], 0.0035, "black"), "chest")

    # Cummerbund: both sides from under the front plate to under the back plate.
    for s, sx in (("L", 1), ("R", -1)):
        for z, w in ((1.07, 0.055), (1.135, 0.055)):
            pts = []
            for i in range(9):
                a = math.radians(46 + 90 * i / 8)
                pts.append(Vector((sx * 0.142 * math.sin(a), -0.004 - 0.112 * math.cos(a), z)))
            c.rigid(sweep("cummerbund", smooth_path(pts, 3), w, 0.012, "pmc_navy", radial((0, -0.004, 0))), "chest")
        c.rigid(kit.block("cb_tab", (sx * 0.14, -0.03, 1.1), (0.012, 0.03, 0.11), "black", bevel=0.003), "chest")

    # ---------------------------------------------------------------- head: cap, headset, glasses, hair
    plane_p = hc + Vector((0, 0, 0.03))
    plane_n = Vector((0, 0.15, 1)).normalized()
    cap = kit.shell(head, lambda p: p.z > hc.z - 0.03, "cap", "pmc_navy", offset=0.012, thick=0.004, smooth_iter=6, detail=1.0,
                    inside=[half_space("cap_cut", plane_p, plane_n)])
    c.rigid(cap, "head")
    tcap = tree(cap)
    # Brim: a crescent in plan, curved down at the sides, tipped down at the front.
    outer = [(0.093 * math.sin(math.radians(a)), -0.178 * math.cos(math.radians(a))) for a in range(-78, 79, 12)]
    inner = [(0.081 * math.sin(math.radians(a)), -0.096 * math.cos(math.radians(a))) for a in range(78, -79, -12)]
    brim = kit.plan("brim", outer + inner, 0.006, "pmc_navy", z=0.0, bevel=0.0025)
    slice_x(brim, 0.012)
    for v in brim.data.vertices:
        v.co.z -= 2.4 * v.co.x * v.co.x
    brim.data.transform(Matrix.Translation(hc + Vector((0, -0.096, 0.043))) @ Matrix.Rotation(math.radians(9), 4, "X") @ Matrix.Translation((0, 0.096, 0)))
    c.rigid(brim, "head")
    c.rigid(kit.cyl("cap_button", hc + Vector((0, 0.004, 0.128)), hc + Vector((0, 0.004, 0.137)), 0.009, "pmc_navy", segs=16, bevel=0.002), "head")
    loc, nor = hit(tcap, hc + Vector((0, -0.3, 0.072)), (0, 1, 0))
    nf = Vector((0, -1, 0.55)).normalized()
    cap_logo = logo(0, 0, 0.042, 0.0)
    put(cap_logo, frame(loc, nf, (0, 0.3, 1)), 0.09, step=0.008)
    rigid_all(c, cap_logo, "head")
    # Short hair below the cap at the back and sides.
    hair = kit.shell(head, lambda p: p.z > hc.z - 0.07 and p.y > hc.y - 0.06, "hair", "hair", offset=0.003, thick=0.003, smooth_iter=2, detail=0.6,
                     inside=[half_space("hair_top", plane_p - plane_n * 0.006, -plane_n),
                             half_space("hair_nape", hc + Vector((0, 0.0, -0.05)), Vector((0, 0.2, 1))),
                             half_space("hair_front", hc + Vector((0, -0.035, 0)), Vector((0, 1, 0)))])
    c.rigid(hair, "head")

    # Over-ear headset: cups with cushions, covers and the mark, a band over the cap, boom mic.
    for s, sx in (("L", 1), ("R", -1)):
        cc = hc + Vector((sx * 0.106, 0.004, -0.006))
        X = Vector((sx, 0, 0))
        c.rigid(kit.ring("cushion", hc + Vector((sx * 0.094, 0.004, -0.006)), X, 0.041, 0.022, 0.012, "rubber", segs=20), "head")
        cup = kit.cyl("cup", cc - X * 0.006, cc + X * 0.016, 0.043, "black", segs=24, bevel=0.004)
        c.rigid(cup, "head")
        cover = kit.cyl("cup_cover", cc + X * 0.016, cc + X * 0.021, 0.034, "grey", segs=24, bevel=0.0015)
        c.rigid(cover, "head")
        Mc = frame(cc + X * 0.021, X, (0, 0, 1))
        objs = logo(0, 0.006, 0.032, 0.0) + screws([(-0.024, -0.016), (0.024, -0.016)], 0.0, r=0.003)
        put(objs, Mc)
        rigid_all(c, objs, "head")
        c.rigid(kit.cyl("knob", cc + Vector((sx * 0.004, 0.026, -0.03)), cc + Vector((sx * 0.004, 0.034, -0.036)), 0.007, "grey", segs=12, bevel=0.001), "head")
        c.rigid(kit.block("yoke", cc + Vector((sx * 0.005, 0, 0.05)), (0.012, 0.03, 0.03), "grey", bevel=0.003), "head")
    band_pts = []
    for i in range(17):
        a = math.radians(-78 + 156 * i / 16)
        band_pts.append(hc + Vector((0.108 * math.sin(a), 0.004, 0.02 + 0.13 * math.cos(a))))
    c.rigid(sweep("headband", band_pts, 0.024, 0.007, "black", radial(hc + Vector((0, 0, 0.02)), (0, 1, 0))), "head")
    c.rigid(sweep("headband_pad", band_pts[5:12], 0.018, 0.006, "grey", radial(hc + Vector((0, 0, 0.026)), (0, 1, 0))), "head")
    mic_pts = [hc + Vector(p) for p in ((0.114, -0.046, -0.026), (0.108, -0.07, -0.042), (0.088, -0.098, -0.058), (0.052, -0.118, -0.066))]
    c.rigid(kit.cyl("mic_pivot", hc + Vector((0.104, -0.04, -0.024)), hc + Vector((0.122, -0.04, -0.024)), 0.01, "grey", segs=14, bevel=0.002), "head")
    c.rigid(kit.rope("boom", mic_pts, 0.003, "black"), "head")
    c.rigid(kit.cyl("mic", hc + Vector((0.056, -0.117, -0.066)), hc + Vector((0.03, -0.121, -0.068)), 0.0065, "black", segs=14, bevel=0.002), "head")

    # Wraparound sunglasses: two lenses, a bridge, top bar and temple arms.
    gl = []
    for sx in (1, -1):
        lens = [(sx * x, z) for x, z in ((0.013, 0.014), (0.036, 0.018), (0.062, 0.015), (0.066, 0.002), (0.057, -0.012), (0.034, -0.018), (0.017, -0.010))]
        if sx < 0:
            lens = lens[::-1]
        gl.append(panel("lens", [(x, hc.z + z) for x, z in lens], 0.0, 0.003, "glass", bevel=0.0008))
        bar = [(sx * x, z) for x, z in ((0.011, 0.012), (0.036, 0.0215), (0.066, 0.018), (0.068, 0.010), (0.036, 0.0145), (0.011, 0.007))]
        if sx < 0:
            bar = bar[::-1]
        gl.append(panel("frame", [(x, hc.z + z) for x, z in bar], 0.0012, 0.0055, "black", bevel=0.0008))
    gl.append(panel("bridge", rrect(-0.013, hc.z + 0.006, 0.013, hc.z + 0.012, 0.002), 0.0012, 0.005, "black", bevel=0.0006))
    Mg = frame((0, hc.y - 0.111, 0), (0, -1, 0))
    put(gl, Mg, 0.105, step=0.008)
    rigid_all(c, gl, "head")
    for sx in (1, -1):
        e0 = to_world((sx * 0.066, 0.0, hc.z + 0.014), Mg, 0.105)
        tp = [e0, hc + Vector((sx * 0.088, -0.05, 0.013)), hc + Vector((sx * 0.092, -0.02, 0.011))]
        c.rigid(sweep("temple", smooth_path(tp, 3), 0.007, 0.0028, "black", lambda p, sx=sx: Vector((sx, 0, 0))), "head")

    # ---------------------------------------------------------------- legs
    trousers = kit.shell(flesh, lambda p: 0.11 < p.z < 1.03, "trousers", "secondary", offset=0.02, thick=0.004, smooth_iter=3,
                         bones=THIGHS | SHINS | TORSO, inside=[half_space("waist", (0, 0, 0.986), (0, 0, -1)), half_space("hem", (0, 0, 0.178), (0, 0, 1))])
    cloth(c, trousers)
    c.cover(THIGHS | SHINS | {"hips"}, lambda p: 0.15 < p.z < 0.98)
    belt = sweep("belt", ring_pts(tf, (0, -0.005), 0.97, 0.027, n=32), 0.044, 0.009, "black", radial((0, -0.005, 0)), closed=True)
    c.add(belt, ["hips", "spine", "upper_leg.L", "upper_leg.R"])
    bk = [kit.block("buckle", (0, 0, 0), (0.062, 0.012, 0.038), "gunmetal", bevel=0.003)]
    kit.cut(bk[0], kit.block("buckle_slot", (0, -0.006, 0), (0.044, 0.006, 0.02), "steel", bevel=0))
    bk.append(kit.block("buckle_bar", (0, -0.002, 0), (0.05, 0.006, 0.006), "bright", bevel=0.0015))
    loc, _ = hit(tf, (0, -0.5, 0.968), (0, 1, 0))
    for o in bk:
        o.data.transform(Matrix.Translation(Vector((0, loc.y - 0.033, 0.968))))
        c.rigid(o, "hips")
    for s, sx in (("L", 1), ("R", -1)):
        ul0, ul1 = b.j("upper_leg." + s, 0.0), b.j("upper_leg." + s, 1.0)
        out = 90 * sx
        if s == "L":
            # Cargo pocket and flap on the outside of the thigh.
            c.rigid(wrap("cargo", ul0.lerp(ul1, 0.36), ul0.lerp(ul1, 0.72), 0.099, 0.095, out - 38, out + 38, 0.014, "secondary", nt=4, nphi=10, bevel=0.004), "upper_leg." + s)
            c.rigid(wrap("cargo_flap", ul0.lerp(ul1, 0.33), ul0.lerp(ul1, 0.42), 0.113, 0.111, out - 41, out + 41, 0.006, "secondary", nt=2, nphi=10, bevel=0.002), "upper_leg." + s)
            snap = ul0.lerp(ul1, 0.4) + Vector((0.119, 0, 0))
            c.rigid(kit.cyl("snap", snap, snap + Vector((0.005, 0, 0)), 0.006, "gunmetal", segs=12, bevel=0.001), "upper_leg." + s)
        else:
            # Drop-leg holster: platform on two thigh straps, holster shell, pistol grip.
            th0 = ul0.lerp(ul1, 0.42)
            for t in (0.36, 0.62):
                p = ul0.lerp(ul1, t)
                c.rigid(sweep("leg_strap", [p + Vector((0.1 * math.sin(math.radians(a)), -0.1 * math.cos(math.radians(a)), 0)) for a in range(0, 361, 20)][:-1],
                              0.03, 0.006, "black", radial(p), closed=True), "upper_leg." + s)
                c.rigid(side_buckle("leg_buckle", p + Vector((-0.04, -0.099, 0)), (1, 0, 0), (0, -1, 0), w=0.028), "upper_leg." + s)
            c.rigid(wrap("platform", ul0.lerp(ul1, 0.30), ul0.lerp(ul1, 0.68), 0.105, 0.102, out - 30, out + 30, 0.008, "pmc_navy", nt=4, nphi=8, bevel=0.003), "upper_leg." + s)
            hol = kit.prism("holster", [(-0.05, 0.11), (0.06, 0.11), (0.07, -0.02), (0.05, -0.12), (-0.02, -0.12), (-0.05, 0.02)], 0.045, "black", bevel=0.006)
            kit.cut(hol, kit.block("hol_groove", (0.03, 0.0, -0.02), (0.006, 0.12, 0.004), "steel", bevel=0))
            grip = kit.block("pistol_grip", (0.0, -0.035, 0.155), (0.026, 0.035, 0.08), "black", bevel=0.004, rot=-12)
            hood = kit.block("hood", (0.0, 0.0, 0.12), (0.05, 0.11, 0.02), "pmc_navy", bevel=0.004)
            hol = kit.join([hol, grip, hood], "holster")
            hol.data.transform(Matrix.Translation(th0 + Vector((-0.135, 0.0, -0.05))))
            c.rigid(hol, "upper_leg." + s)
        # Knee pads: conforming black pad with a grey hard cap and screws.
        knee = b.j("lower_leg." + s, 0.04)
        pad_cut = kit.slab("pad_cut", kit.rounded([(knee.x - 0.058, knee.z - 0.08), (knee.x + 0.058, knee.z - 0.08), (knee.x + 0.058, knee.z + 0.07),
                                                   (knee.x - 0.058, knee.z + 0.07)], 0.03), -0.4, knee.y - 0.01)
        pad = kit.plate(flesh, pad_cut, "kneepad", "black", offset=0.03, thick=0.016, bevel=0.006, bones=THIGHS | SHINS)
        c.rigid(pad, "lower_leg." + s)
        tp = tree(pad)
        loc, _ = hit(tp, knee + Vector((0, -0.4, -0.005)), (0, 1, 0))
        Mk = frame(loc + Vector((0, 0.001, 0)), (0, -1, 0.1))
        cap_objs = [panel("knee_cap", hexagon(0, 0, 0.034, rot=90), 0.0, 0.006, "grey", bevel=0.002)]
        cap_objs += screws([(0.0, 0.022), (0.0, -0.022)], -0.006, r=0.0035)
        put(cap_objs, Mk, 0.06, step=0.01)
        rigid_all(c, cap_objs, "lower_leg." + s)
        c.add(band("pad_strap", knee + Vector((0, 0.012, -0.055)), (0.058, 0.056), 0.02, 0.006, "black", axis=(0, 0, 1)), ["lower_leg." + s])

    # Tactical boots: fused black uppers, rubber soles with tread, grey toe caps and heel counters, laces.
    for s, sx in (("L", 1), ("R", -1)):
        c.add(boot(c, b, s, upper="black", trim="grey", sole_mat="rubber", lace="grey", tab="hazard"), ["foot." + s, "lower_leg." + s])
    c.cover(FEET | SHINS, lambda p: p.z < 0.19)
    economise(c)
    return c


SPEC = {"build": build, "faction": "pmc", "budget": (25000, 75000), "loadout": "rifle",
        "colors": {"primary": "#b9bec6", "secondary": "#33383f", "accent": "#c9a227"}}
