"""Mechanic, Scrappers: a Luddite homesteader who keeps the settlement's machines running. A waxed-canvas
chore jacket with a corduroy collar and leather elbow patches; over it a split-leg leather welding apron
with a hand-painted cog, brass rivets and tan straps; a tool belt with a hammer, a tool pouch and an oil
can, and a waxed tool roll strapped across the small of the back. A leather work cap with brass welding
goggles pushed up on it, suede work gloves, a brass pressure gauge strapped to the left wrist, patched
duck trousers with turn-ups and worn leather work boots. A real face: stubble and a moustache. Nothing
electric: leather, brass, riveted steel, waxed cloth and paint.

Built on the realistic layer (real.py), like the Contractor: a real body, face and eyes, gloved fists
closed round the grips, jacket, apron and trousers cut from the body and draped by the cloth
simulation, procedural surfaces (this module's own: waxed canvas, cotton duck, corduroy, brushed paint,
ash wood, moustache) baked into a 2048 atlas.

Tints: primary = jacket (and the knee patches cut from the same cloth), secondary = trousers, accent =
the tan straps (apron, goggles, tool roll). The collar, leather and brass are fixed colours.

The first part of this file holds placement helpers the other Scrappers (bruiser, trapper) import: ray
casts against the body so gear sits on the skin, straps draped over it, conforming bands, parametric
sheets (aprons, coat panels), rivet and stitch rows, custom skin weights.
"""

import math

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import kit
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS, FEET

ARMS = {b + s for b in ("upper_arm.", "forearm.", "hand.") for s in ("L", "R")}
UP = Vector((0, 0, 1))

SPINE = ["hips", "spine", "chest"]
# Scrappers palette additions (prefixed so they never clash with another faction's entries).
kit.hs.PALETTE.setdefault("scrap_ash", ((0.50, 0.34, 0.18), (0.66, 0.52, 0.36), 0.0, 0.7, 0.45, 0))
kit.hs.PALETTE.setdefault("scrap_suede", ((0.40, 0.26, 0.13), (0.56, 0.42, 0.27), 0.0, 0.85, 0.35, 0))
kit.hs.PALETTE.setdefault("scrap_hair", ((0.075, 0.045, 0.025), (0.14, 0.09, 0.055), 0.0, 0.6, 0.0, 0))
kit.hs.PALETTE.setdefault("scrap_kerchief", ((0.40, 0.07, 0.05), (0.55, 0.22, 0.16), 0.0, 0.85, 0.3, 0))


# ----------------------------------------------------------------------------------- placement helpers

def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def along(b, bone, p):
    """(t along `bone` 0 head .. 1 tail, distance from its segment) for point p."""
    h, t = Vector(b.all[bone][0]), Vector(b.all[bone][1])
    ab = t - h
    s = (Vector(p) - h).dot(ab) / ab.length_squared
    return s, (h + ab * max(0.0, min(1.0, s)) - Vector(p)).length


def frame(axis):
    """(axis, u, v): u points to the front (-Y) where it can, v = axis x u."""
    a = Vector(axis).normalized()
    ref = Vector((0, -1, 0)) if abs(a.y) < 0.9 else Vector((0, 0, 1))
    u = (ref - a * ref.dot(a)).normalized()
    return a, u, a.cross(u).normalized()


class Probe:
    """Ray casts against meshes (the body, or only some bone regions of it) so gear lands on the skin."""

    def __init__(self, objs, only=None, skip=None):
        self.trees = []
        for o in (objs if isinstance(objs, (list, tuple)) else [objs]):
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bm.transform(o.matrix_world)
            if only or skip:
                dom = kit.dominant(o)

                def bad(f):
                    names = [dom[v.index] for v in f.verts]
                    if only and sum(n in only for n in names) * 2 < len(names):
                        return True
                    return bool(skip) and sum(n in skip for n in names) * 2 > len(names)
                bmesh.ops.delete(bm, geom=[f for f in bm.faces if bad(f)], context="FACES")
            self.trees.append(BVHTree.FromBMesh(bm))
            bm.free()

    def hit(self, p, d, reach=0.5):
        """The outermost surface point on the ray from p + d*reach back to p: (location, normal) or None."""
        d = Vector(d).normalized()
        o = Vector(p) + d * reach
        best = None
        for t in self.trees:
            loc, n, _, dist = t.ray_cast(o, -d, reach)
            if loc is not None and (best is None or dist < best[2]):
                best = (loc, n, dist)
        return (best[0], best[1]) if best else None

    def surf(self, p, d, reach=0.5):
        h = self.hit(p, d, reach)
        return h[0] if h else None

    def depth(self, p, d, reach=0.5):
        """How far out from p along d the surface is (None if it is not there)."""
        s = self.surf(p, d, reach)
        return None if s is None else (s - Vector(p)).dot(Vector(d).normalized())

    def near(self, p):
        best = None
        for t in self.trees:
            loc, n, _, dist = t.find_nearest(Vector(p))
            if loc is not None and (best is None or dist < best[2]):
                best = (loc, n, dist)
        return best[0], best[1]


def spot(probe, c, axis, ang, gap, reach=0.4):
    """A point `gap` out from the surface around `axis` through c, `ang` degrees from the front."""
    a, u, v = frame(axis)
    d = u * math.cos(math.radians(ang)) + v * math.sin(math.radians(ang))
    s = probe.surf(c, d, reach)
    r = (s - Vector(c)).dot(d) if s is not None else 0.05
    return Vector(c) + d * (r + gap), d


def contour(probe, c, axis, gap, n=24, reach=0.35, smooth=2):
    """Points around `axis` through c, `gap` (a number or a function of the direction) out from the
    surface; concave dips are bridged so straps do not dive into creases. Returns (pts, dirs, axis)."""
    a, u, v = frame(axis)
    c = Vector(c)
    dirs = [u * math.cos(2 * math.pi * i / n) + v * math.sin(2 * math.pi * i / n) for i in range(n)]
    rs = [probe.depth(c, d, reach) for d in dirs]
    ok = [r for r in rs if r is not None]
    base = sum(ok) / len(ok) if ok else 0.05
    rs = [r if r is not None else base for r in rs]
    for _ in range(smooth):
        rs = [max(rs[i], (rs[i - 1] + rs[i] + rs[(i + 1) % n]) / 3) for i in range(n)]
    gaps = [gap(d) if callable(gap) else gap for d in dirs]
    return [c + d * (r + g) for d, r, g in zip(dirs, rs, gaps)], dirs, a


def ribbon(name, pts, ns, ws, width, thick, material, closed=False, bevel=None):
    """A flat strap through points with per-point face normals `ns` and width directions `ws`."""
    bm = bmesh.new()
    rings = []
    for p, n, w in zip(pts, ns, ws):
        n, w = Vector(n).normalized(), Vector(w).normalized()
        rings.append([bm.verts.new(Vector(p) + w * sw * width / 2 + n * nn * thick / 2)
                      for sw, nn in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for r0, r1 in pairs:
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bevel is None:
        bevel = 0.0 if thick <= 0.005 else min(width, thick) * 0.25
    return kit.hs._obj(name, bm, material, bevel=bevel)


def wrap(name, probe, c, axis, width, thick, material, gap=0.003, n=24, reach=0.35, bevel=None):
    """A band hugging the surface around `axis` (a belt, a cuff, a strut clamp)."""
    g = (lambda d: gap(d) + thick / 2) if callable(gap) else gap + thick / 2
    pts, dirs, a = contour(probe, c, axis, g, n, reach)
    return ribbon(name, pts, dirs, [a] * n, width, thick, material, closed=True, bevel=bevel)


def catmull(pts, step):
    """A Catmull-Rom curve through pts, sampled about every `step` metres."""
    pts = [Vector(p) for p in pts]
    out = []
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = pts[max(0, i - 1)], pts[i], pts[i + 1], pts[min(len(pts) - 1, i + 2)]
        n = max(1, int((p2 - p1).length / step))
        for s in range(n):
            t = s / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    out.append(pts[-1])
    return out


def drape(probe, guides, gap, step=0.015, smooth=3):
    """A path over the body: a curve through the guide points, each sample pulled onto the nearest skin
    and lifted `gap` off it. Returns (points, normals)."""
    hits = [probe.near(p) for p in catmull(guides, step)]
    ns = [n.normalized() for _, n in hits]
    for _ in range(smooth):
        ns = [(ns[max(0, i - 1)] + ns[i] * 2 + ns[min(len(ns) - 1, i + 1)]).normalized() for i in range(len(ns))]
    pts = [loc + n * gap for (loc, _), n in zip(hits, ns)]
    for _ in range(smooth):
        pts = [pts[0]] + [(pts[i - 1] + pts[i] * 2 + pts[i + 1]) / 4 for i in range(1, len(pts) - 1)] + [pts[-1]]
    return pts, ns


def strap_over(name, probe, guides, gap, width, thick, material, step=0.025):
    """A strap draped over the body along the guide points (suspenders, bandoliers, neck straps)."""
    pts, ns = drape(probe, guides, gap + thick / 2, step)
    ws = []
    for i in range(len(pts)):
        tan = (pts[min(len(pts) - 1, i + 1)] - pts[max(0, i - 1)]).normalized()
        ws.append(ns[i].cross(tan))
    return ribbon(name, pts, ns, ws, width, thick, material), pts, ns


def tube_path(name, pts, r, material, segs=8, closed=True, strands=0, pitch=0.02, taper=False):
    """A round tube along points (rolled cuffs, rope coils, pipes); `strands` twists the radius into a
    rope lay, `taper` thins an open tube to points at both ends (hair locks)."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    cen = sum(pts, Vector()) / n
    bm = bmesh.new()
    rings, prev, run = [], None, 0.0
    for i, p in enumerate(pts):
        if closed:
            tan = (pts[(i + 1) % n] - pts[i - 1]).normalized()
        else:
            tan = (pts[min(n - 1, i + 1)] - pts[max(0, i - 1)]).normalized()
        ref = (p - cen) if prev is None else prev
        if (ref - tan * ref.dot(tan)).length < 1e-6:
            ref = Vector((0, 0, 1)) if abs(tan.z) < 0.9 else Vector((1, 0, 0))
        x = (ref - tan * ref.dot(tan)).normalized()
        prev = x
        y = tan.cross(x)
        if i:
            run += (p - pts[i - 1]).length
        ring = []
        tp = max(0.2, math.sin(math.pi * i / max(1, n - 1)) ** 0.6) if taper else 1.0
        for k in range(segs):
            q = 2 * math.pi * k / segs
            rr = (r * (1 + 0.16 * math.cos(strands * q + run / pitch * 2 * math.pi)) if strands else r) * tp
            ring.append(bm.verts.new(p + (x * math.cos(q) + y * math.sin(q)) * rr))
        rings.append(ring)
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for r0, r1 in pairs:
        for k in range(segs):
            j = (k + 1) % segs
            bm.faces.new((r0[k], r0[j], r1[j], r1[k]))
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = kit.hs._obj(name, bm, material, bevel=0)
    o["shaded"] = True
    return o


def sheet(name, fn, nu, nv, thick, material, out, bevel=0.0, closed_u=False):
    """A surface from fn(u, v) -> point on a nu x nv grid, given `thick` thickness on the `out(p)` side."""
    bm = bmesh.new()
    cols = nu if closed_u else nu + 1
    grid = [[bm.verts.new(fn(i / nu, j / nv)) for i in range(cols)] for j in range(nv + 1)]
    for j in range(nv):
        for i in range(nu):
            i1 = (i + 1) % cols
            bm.faces.new((grid[j][i], grid[j][i1], grid[j + 1][i1], grid[j + 1][i]))
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    mid = bm.faces[len(bm.faces) // 2]
    if mid.normal.dot(out(mid.calc_center_median())) < 0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    o = kit.hs._obj(name, bm, material, bevel)
    if thick:
        m = o.modifiers.new("thick", "SOLIDIFY")
        m.thickness = thick
        m.offset = 1.0
        m.use_even_offset = True
        m.use_rim = True
        kit.hs._apply(o, m.name)
    return o


def rivets(name, spots, r=0.004, material="steel", segs=8):
    """Dome-head rivets at (point, normal) spots, one object."""
    bm = bmesh.new()
    for p, n in spots:
        n = Vector(n).normalized()
        rot = Vector((0, 0, 1)).rotation_difference(n).to_matrix().to_4x4()
        h = r * 0.75
        m = Matrix.Translation(Vector(p) + n * (h / 2 - r * 0.25)) @ rot
        made = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r, radius2=r * 0.5, depth=h, matrix=m)
        vs = set(made["verts"])
        bm.normal_update()
        under = [f for f in bm.faces if len(f.verts) == segs and set(f.verts) <= vs and f.normal.dot(n) < -0.9]
        bmesh.ops.delete(bm, geom=under, context="FACES_ONLY")  # the head sits on the plate: no underside
    o = kit.hs._obj(name, bm, material, bevel=0)
    o["shaded"] = True
    return o


def dashes(name, spots, length=0.007, width=0.0016, height=0.0012, material="cream", flat=False):
    """Small boxes at (point, normal, tangent) spots: stitching, tick marks. `flat` makes each a single
    quad `height` off the surface (stitching that only has to read, at a sixth of the triangles)."""
    bm = bmesh.new()
    for p, n, t in spots:
        n = Vector(n).normalized()
        t = Vector(t)
        t = (t - n * t.dot(n)).normalized()
        w = n.cross(t)
        if flat:
            bm.faces.new([bm.verts.new(Vector(p) + n * height + t * a * length / 2 + w * e * width / 2) for a, e in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
            continue
        m = Matrix((t, w, n)).transposed().to_4x4()
        m = Matrix.Translation(Vector(p)) @ m @ Matrix.Diagonal((length, width, height, 1))
        bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    return kit.hs._obj(name, bm, material, bevel=0)


def seam(pts, ns, spacing=0.011):
    """Stitch spots every `spacing` along a polyline with normals."""
    out, acc = [], spacing * 0.5
    for i in range(len(pts) - 1):
        a, b = Vector(pts[i]), Vector(pts[i + 1])
        seg = (b - a).length
        if seg < 1e-6:
            continue
        while acc < seg:
            t = acc / seg
            out.append((a.lerp(b, t), Vector(ns[i]).lerp(Vector(ns[i + 1]), t), b - a))
            acc += spacing
        acc -= seg
    return out


def onto(obj, origin, x, y, z):
    """Bake a local frame (x, y, z axes, origin) into a part built at the origin."""
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(origin)
    obj.data.transform(m)
    return obj


def local(origin, out, up=UP):
    """A right-handed frame on a surface: x along it (horizontal), y = out, z up."""
    y = Vector(out).normalized()
    x = y.cross(Vector(up)).normalized()
    z = x.cross(y).normalized()
    return Vector(origin), x, y, z


def hang_field(probe, x0, x1, nx, z0, z1, nz, d=(0, -1, 0)):
    """How far out along d (default the front) the body reaches at each (x, z) of a grid, carried down
    from z0 (top) to z1, so a stiff panel hung from the chest stays clear of everything below it.
    Returns f(x, z), bilinear."""
    d = Vector(d)
    cols = []
    for i in range(nx + 1):
        x = x0 + (x1 - x0) * i / nx
        run, col = 0.0, []
        for j in range(nz + 1):
            z = z0 + (z1 - z0) * j / nz
            run = max(run, probe.depth(Vector((x, 0, z)), d, 0.5) or 0.0)
            col.append(run)
        cols.append(col)

    def f(x, z):
        fi = min(max((x - x0) / (x1 - x0) * nx, 0.0), nx - 1e-6)
        fj = min(max((z - z0) / (z1 - z0) * nz, 0.0), nz - 1e-6)
        i, j = int(fi), int(fj)
        ti, tj = fi - i, fj - j
        a = cols[i][j] * (1 - ti) + cols[i + 1][j] * ti
        c = cols[i][j + 1] * (1 - ti) + cols[i + 1][j + 1] * ti
        return a * (1 - tj) + c * tj
    return f


def panel(name, pt, x0, x1, z0, z1, outline, off, thick, material, nu=10, nv=10, bevel=0.002, hole=None):
    """A front-facing piece on a hanging surface pt(x, z, off) -> point: trimmed to the (x, z) `outline`,
    `off` out from the surface's base. Pockets, painted marks, patches on aprons and coat panels.
    `hole` = (x, z, r) leaves a round hole (a painted cog's hub)."""
    o = sheet(name, lambda u, v: pt(x0 + (x1 - x0) * u, z1 + (z0 - z1) * v, off), nu, nv, thick, material, lambda p: Vector((0, -1, 0)))
    o = kit.intersect(o, kit.slab(name + "_cut", outline, -0.6, 0.3))
    if hole:
        hx, hz, hr = hole
        o = kit.subtract(o, kit.cyl(name + "_hole", (hx, -0.6, hz), (hx, 0.3, hz), hr, "steel", segs=20))
    o["bevel"] = bevel
    return o


def plate(src, cutter, name, material, offset, thick, bevel=0.002, bones=None, keep=None):
    """kit.plate without the decimation, so stacked plates (paint on a bib, a pocket) stay parallel."""
    o = kit.shell(src, keep, name, material, offset=offset, thick=thick, bevel=0.0, bones=bones, detail=1.0)
    o = kit.intersect(o, cutter)
    o["bevel"] = bevel
    o["segs"] = 2
    o["shaded"] = False
    return o


def skin(c, obj, fn):
    """Skin `obj` with weights from fn(point) -> {bone: weight} (coat panels that drape)."""
    obj.vertex_groups.clear()
    groups = {}
    for v in obj.data.vertices:
        for bn, w in fn(obj.matrix_world @ v.co).items():
            if w > 1e-4:
                if bn not in groups:
                    groups[bn] = obj.vertex_groups.new(name=bn)
                groups[bn].add([v.index], w, "REPLACE")
    c.parts.append((obj, "DONE", None))
    return obj


def transfer_from(c, obj, flesh, bones):
    """Skin `obj` by copying weights from the nearest face of the body that follows `bones` (trousers
    on a big man whose hands hang by his thighs must not pick up the forearms)."""
    import bpy
    tmp = flesh.copy()
    tmp.data = flesh.data.copy()
    bpy.context.scene.collection.objects.link(tmp)
    dom = kit.dominant(tmp)
    bm = bmesh.new()
    bm.from_mesh(tmp.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if sum(dom[v.index] in bones for v in f.verts) * 2 < len(f.verts)], context="FACES")
    bm.to_mesh(tmp.data)
    bm.free()
    obj.vertex_groups.clear()
    kit.transfer(tmp, obj)
    for g in list(obj.vertex_groups):
        if g.name not in bones:
            obj.vertex_groups.remove(g)
    bpy.data.objects.remove(tmp)
    c.parts.append((obj, "DONE", None))
    return obj


def hair_cap(head, hc, k, line, extra, offset=0.0015, thick=0.007, grooves=(), material="hair", low=0.1):
    """Hair as a shell of the head trimmed by a side-view hairline prism `line`, puffed out by
    extra(point) metres (volume on top, a quiff) and scored by `grooves` (cutter objects: a parting)."""
    cap = kit.shell(head, lambda p: p.z > hc.z - low * k, "hair", material, offset=offset, thick=0, smooth_iter=2, detail=0.6)
    bm = bmesh.new()
    bm.from_mesh(cap.data)
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * extra(v.co)
    bm.to_mesh(cap.data)
    bm.free()
    kit.smooth(cap, 2, 0.5)
    m = cap.modifiers.new("thick", "SOLIDIFY")
    m.thickness, m.offset, m.use_rim = thick, 1.0, True
    kit.hs._apply(cap, m.name)
    cap = kit.intersect(cap, kit.prism("hair_line", line, 0.4, "steel", bevel=0))
    for g in grooves:
        cap = kit.subtract(cap, g)
    cap["bevel"], cap["shaded"] = 0.0, False  # crisp hairline rim, smooth hair
    for poly in cap.data.polygons:
        poly.use_smooth = True
    return cap


def gauge(at, out, up, r=0.0235, depth=0.013, needle=48, body="brass"):
    """A brass pressure gauge with its back on `at`, face toward `out`, 12 o'clock toward `up`: bezel,
    cream dial, tick marks, a red line and a needle. Returns the parts (join them with their mounts)."""
    out = Vector(out).normalized()
    e1 = (Vector(up) - out * Vector(up).dot(out)).normalized()
    e2 = out.cross(e1).normalized()
    at = Vector(at)
    face = at + out * depth
    parts = [kit.cyl("gauge_body", at - out * 0.002, face, r, body, segs=24, bevel=0.0015),
             kit.ring("gauge_bezel", face + out * 0.0005, out, r * 1.1, r * 0.84, 0.0045, body, segs=28),
             kit.cyl("gauge_dial", face - out * 0.001, face + out * 0.0008, r * 0.85, "cream", segs=24, bevel=0),
             kit.cyl("gauge_hub", face + out * 0.0008, face + out * 0.0022, r * 0.1, body, segs=10, bevel=0)]
    ticks = []
    for i in range(11):
        q = math.radians(-135 + 27 * i)
        d = e1 * math.cos(q) + e2 * math.sin(q)
        ticks.append((face + out * 0.0012 + d * r * (0.66 if i % 5 else 0.63), out, d))
    parts.append(dashes("gauge_ticks", ticks, length=r * 0.17, width=r * 0.047, height=0.0008, material="black"))
    q = math.radians(needle)
    d = e1 * math.cos(q) + e2 * math.sin(q)
    parts.append(dashes("gauge_needle", [(face + out * 0.0022 + d * r * 0.28, out, d)], length=r * 0.68, width=r * 0.055, height=0.0008, material="red"))
    zone = []
    for i in range(5):
        q = math.radians(100 + 8 * i)
        d = e1 * math.cos(q) + e2 * math.sin(q)
        zone.append((face + out * 0.0012 + d * r * 0.745, out, e2 * math.cos(q) - e1 * math.sin(q)))
    parts.append(dashes("gauge_redline", zone, length=r * 0.136, width=r * 0.094, height=0.0007, material="red"))
    return parts


def cog(cx, cz, r, teeth=8, depth=0.24):
    """A cog outline in the (x, z) plane: the Scrappers' painted mark."""
    pts = []
    n = teeth * 4
    for i in range(n):
        a = 2 * math.pi * (i + 0.5) / n
        rr = r if i % 4 in (0, 1) else r * (1 - depth)
        pts.append((cx + math.cos(a) * rr, cz + math.sin(a) * rr))
    return pts


def painted_cog(src, cx, cz, r, offset, material, bones, front=True, hole=0.36):
    """A hand-painted cog on a layer `offset` off the body (front or back), with its hub left bare."""
    y0, y1 = (-0.5, -0.0) if front else (0.0, 0.5)
    o = plate(src, kit.slab("cog_cut", cog(cx, cz, r), y0, y1), "painted_cog", material, offset=offset, thick=0.0012, bevel=0.0, bones=bones)
    return kit.subtract(o, kit.cyl("cog_hole", (cx, y0, cz), (cx, y1, cz), r * hole, "steel", segs=20))


def boots(c, b, flesh, cap="steel", top=0.2, sole_mat="rubber", lace="canvas"):
    """Leather work boots with a toe cap, a stacked heel, tread, laces and eyelets. Returns the per-side
    boot objects."""
    k = b.k
    out = {}
    for s, sx in (("L", 1), ("R", -1)):
        bones = {"foot." + s, "lower_leg." + s}
        boot = kit.shell(flesh, lambda p, sx=sx: p.z < top * k and p.x * sx > 0, "boot", "leather", offset=0.012, thick=0.006, bones=bones)
        c.add(boot, ["foot." + s, "lower_leg." + s])
        out[s] = boot
        f0 = b.j("foot." + s, 0.0)
        sole_pts = kit.rounded([(f0.x - 0.052 * k, 0.088 * k), (f0.x + 0.052 * k, 0.088 * k), (f0.x + 0.056 * k, -0.2 * k), (f0.x - 0.046 * k, -0.2 * k)], 0.04)
        sole = kit.plan("sole", sole_pts, 0.022, sole_mat, z=0.011, bevel=0.003)
        kit.cut(sole, *kit.slots("tread", -0.18 * k, 0.07 * k, 8, -0.002, 0.006, f0.x - 0.08, f0.x + 0.08))
        c.rigid(sole, "foot." + s)
        heel = kit.block("heel", (f0.x, 0.05 * k, 0.03), (0.098 * k, 0.07 * k, 0.018), "leather", bevel=0.003)
        c.rigid(heel, "foot." + s)
        foot = Probe(flesh, only={"foot." + s})
        tip = Vector((f0.x + sx * 0.002, -0.205 * k, 0.03))
        capc = kit.blob_cutter("cap_cut", tip, (0.058 * k, 0.06 * k, 0.05))
        c.rigid(kit.plate(flesh, capc, "toecap", cap, offset=0.0185, thick=0.0035, bevel=0.001, bones={"foot." + s}), "foot." + s)
        spots, eyes = [], []
        for i in range(4):
            y = (-0.085 + i * 0.026) * k
            z = 0.075 + i * 0.022
            for side in (1, -1):
                h = foot.hit(Vector((f0.x + side * 0.022, y, z - 0.04)), (0, 0, 1), 0.2) or foot.hit(Vector((f0.x + side * 0.022, y, z)), (side, -0.3, 0.6), 0.2)
                if h:
                    eyes.append((h[0] + h[1] * 0.0185, h[1]))
            h = foot.hit(Vector((f0.x, y, z - 0.04)), (0, -0.4, 1), 0.2)
            if h:
                spots.append((h[0] + h[1] * 0.0195, h[1], Vector((1, 0, 0))))
        if spots:
            c.rigid(dashes("laces", spots, length=0.045, width=0.006, height=0.003, material=lace), "foot." + s)
        if eyes:
            c.rigid(rivets("eyelets", eyes, r=0.0032, material="brass"), "foot." + s)
        # Pull tab at the back of the shaft.
        h = foot.hit(Vector((f0.x, 0.0, 0.14 * k)), (0, 1, 0), 0.3) or Probe(flesh, only={"lower_leg." + s}).hit(Vector((f0.x, 0.0, 0.17 * k)), (0, 1, 0), 0.3)
        if h:
            tab = kit.block("pull_tab", h[0] + Vector((0, 0.02, 0.025)), (0.022, 0.005, 0.04), "leather", bevel=0.0015)
            c.rigid(tab, "lower_leg." + s)
    c.cover(FEET | SHINS, lambda p: p.z < (top - 0.03) * k)
    return out




# ===================================================================================== realistic layer
# The Mechanic proper, on the realistic layer (real.py). Everything below is this character's own; the
# helpers above stay for the bruiser and trapper.

import real  # noqa: E402
import surfaces  # noqa: E402
from chars import contractor as pmc  # noqa: E402  (ray-cast and strap helpers)

kit.hs.PALETTE.setdefault("scrap_boot", ((0.16, 0.095, 0.05), (0.40, 0.29, 0.19), 0.0, 0.6, 0.65, 0))      # oiled work-boot leather
kit.hs.PALETTE.setdefault("scrap_lace", ((0.36, 0.24, 0.13), (0.50, 0.38, 0.25), 0.0, 0.75, 0.3, 0))       # rawhide laces
kit.hs.PALETTE.setdefault("scrap_lens", ((0.012, 0.045, 0.026), (0.012, 0.045, 0.026), 0.0, 0.05, 0.0, 0))  # shade-5 welding glass
kit.hs.PALETTE.setdefault("scrap_paint", ((0.80, 0.57, 0.12), (0.20, 0.12, 0.065), 0.0, 0.5, 0.7, 0))      # yellow enamel, chipped to leather
kit.hs.PALETTE.setdefault("scrap_copper", ((0.56, 0.30, 0.17), (0.80, 0.52, 0.36), 1.0, 0.38, 0.4, 0))
kit.hs.PALETTE.setdefault("scrap_cord", ((0.15, 0.085, 0.045), (0.30, 0.20, 0.12), 0.0, 0.85, 0.35, 0))      # brown corduroy
kit.hs.PALETTE.setdefault("scrap_cap", ((0.115, 0.068, 0.038), (0.27, 0.18, 0.11), 0.0, 0.62, 0.35, 0))   # oiled cap leather, dark with handling
kit.hs.PALETTE.setdefault("scrap_wax", ((0.21, 0.18, 0.11), (0.36, 0.31, 0.20), 0.0, 0.5, 0.45, 0))         # brown waxed cotton

# This character's kinds -> surface recipes (all prefixed, so no other character's materials change).
for _k, _s in (("scrap_suede", "leather"), ("scrap_boot", "leather"), ("scrap_cap", "oiled"), ("scrap_lace", "leather"), ("scrap_lens", "glass"),
               ("scrap_paint", "paint"), ("scrap_hair", "hair"), ("scrap_kerchief", "canvas"), ("scrap_ash", "wood"),
               ("scrap_copper", "metal"), ("scrap_wax", "waxed"), ("scrap_cord", "corduroy")):
    surfaces.RECIPE.setdefault(_k, _s)


# ------------------------------------------------------------------------------------ own surfaces

def _cloth_grain(g, uv):
    """Thread-scale grain for heavy cotton, from noise only: the atlas has about a millimetre per texel,
    and a periodic weave that fine aliases into a check."""
    u, v, _ = g.xyz(uv)
    slub = g.noise(g.combine(u, g.mul(v, 0.12), 0.0), 160.0, detail=2)       # thick and thin yarns, streaking along the warp
    fib = surfaces._fibres(g, uv)
    tex = g.noise(g.combine(g.mul(u, 0.5), v, 0.0), 420.0, detail=1)          # the weave's own tooth, as noise
    return slub, fib, tex


def _duck(g, pal):
    """Heavy cotton duck (work trousers, patches): streaky slub yarns, a dry matte face, lighter where
    it has been rubbed."""
    base = pal[0]
    uv = g.uv()
    slub, fib, tex = _cloth_grain(g, uv)
    pos = g.geo("Position")
    rub = g.mul(g.edge(0.006, lo=0.9985, hi=0.98), g.remap(g.noise(pos, 8.0, detail=3), 0.35, 0.7))
    shade = g.remap(g.add(g.mul(slub, 0.6), g.mul(fib, 0.4)), 0.3, 0.7, 0.9, 1.06, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    col = g.mix(g.mul(rub, 0.4), col, surfaces._scale(base, 1.18))
    h = g.add(g.add(g.mul(tex, 0.45), g.mul(fib, 0.35)), g.mul(slub, 0.2))
    return dict(color=col, rough=g.lerp(rub, 0.9, 0.8), metal=0.0, height=h, bump=0.0004)


def _waxed(g, pal):
    """Waxed cotton duck: the weave darkened by the wax and given a dull sheen; the wax breaks into pale
    crease lines and lightens along the folds, where the cloth keeps getting bent."""
    base = pal[0]
    uv = g.uv()
    slub, fib, tex = _cloth_grain(g, uv)
    pos = g.geo("Position")
    cr = g.noise(pos, 26.0, detail=6, rough=0.7, distort=0.6)
    lines = g.remap(g.math("ABSOLUTE", g.sub(cr, 0.5)), 0.010, 0.0)
    ridge = g.edge(0.005, lo=0.9985, hi=0.985)
    patchy = g.remap(g.noise(pos, 5.0, detail=3), 0.35, 0.7)
    brk = g.math("MAXIMUM", g.mul(g.mul(lines, g.add(0.25, g.mul(patchy, 0.75))), 0.5), g.mul(ridge, g.add(0.35, g.mul(patchy, 0.65))), clamp=True)
    shade = g.remap(g.add(g.mul(slub, 0.6), g.mul(fib, 0.4)), 0.3, 0.7, 0.9, 1.05, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    col = g.mix(g.mul(patchy, 0.2), col, surfaces._scale(base, 0.8))     # heavier wax: darker blotches
    col = g.mix(g.mul(brk, 0.6), col, surfaces._scale(base, 1.22))       # the breaks: pale
    h = g.sub(g.add(g.mul(tex, 0.4), g.mul(fib, 0.35)), g.mul(lines, 0.35))
    rough = g.lerp(brk, g.lerp(patchy, 0.6, 0.48), 0.84)
    return dict(color=col, rough=rough, metal=0.0, height=h, bump=0.00045)


def _whiskers(g, pal):
    """A moustache: dense coarse hairs combed down and out, a few gone grey, thinning only at the edge."""
    base = pal[0]
    pos = g.geo("Position")
    x, y, z = g.xyz(pos)
    strands = g.noise(g.combine(g.mul(x, 0.6), y, g.mul(z, 0.08)), 1300.0, detail=2, rough=0.5)
    clumps = g.noise(g.combine(x, y, g.mul(z, 0.25)), 220.0, detail=2)
    shade = g.remap(g.add(g.mul(strands, 0.7), g.mul(clumps, 0.3)), 0.25, 0.75, 0.55, 1.45, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    grey = g.remap(g.noise(pos, 1900.0, detail=1), 0.68, 0.72)
    col = g.mix(g.mul(grey, 0.7), col, (0.42, 0.40, 0.37))
    edge = g.remap(g.attr("seam"), 0.0, 0.0025)
    sparse = g.remap(g.sub(strands, g.mul(g.sub(1.0, edge), 0.6)), 0.3, 0.5)
    col = g.mix(g.mul(g.sub(1.0, sparse), 0.9), col, surfaces._scale(kit.hs.PALETTE["skin"][0], 0.75))
    return dict(color=col, rough=g.lerp(strands, 0.7, 0.5), metal=0.0, height=strands, bump=0.0007)


def _corduroy(g, pal):
    """Corduroy: rounded wales 2.6 mm apart, the pile darker in the valleys, crushed and shiny on worn crowns."""
    base = pal[0]
    uv = g.uv()
    u, _, _ = g.xyz(uv)
    t = g.math("FRACT", g.math("DIVIDE", u, 0.0026))
    wale = g.math("SINE", g.mul(t, math.pi))
    pile = g.noise(uv, 1800.0, detail=3, rough=0.7)
    worn = g.remap(g.noise(g.geo("Position"), 16.0, detail=3), 0.5, 0.8)
    col = g.mix(g.mul(g.sub(1.0, wale), 0.5), base, surfaces._scale(base, 0.7))
    col = g.mix(g.mul(g.mul(wale, worn), 0.45), col, surfaces._scale(base, 1.15))
    h = g.add(g.mul(wale, 0.8), g.mul(pile, 0.2))
    return dict(color=col, rough=g.lerp(g.mul(wale, worn), 0.92, 0.72), metal=0.0, height=h, bump=0.0008)


def _paint(g, pal):
    """Hand-brushed enamel: vertical brush streaks, thin passes where the leather shows through."""
    base, worn = pal[0], pal[1]
    pos = g.geo("Position")
    x, y, z = g.xyz(pos)
    streak = g.noise(g.combine(x, y, g.mul(z, 0.1)), 240.0, detail=2)
    thin = g.remap(g.add(g.noise(pos, 40.0, detail=4), g.mul(streak, 0.25)), 0.66, 0.8)
    sh = g.remap(streak, 0.3, 0.7, 0.86, 1.06, smooth=False)
    col = g.mix(1.0, base, g.rgb(sh, sh, sh), "MULTIPLY")
    col = g.mix(g.mul(thin, 0.9), col, worn)
    h = g.sub(g.mul(streak, 0.6), g.mul(thin, 0.6))
    return dict(color=col, rough=g.lerp(thin, pal[3], 0.78), metal=0.0, height=h, bump=0.00025)


def _wood(g, pal):
    """Ash handle: long grain along the handle (the handles hang roughly upright), oiled and handled dark."""
    base = pal[0]
    pos = g.geo("Position")
    x, y, z = g.xyz(pos)
    grain = g.noise(g.combine(g.mul(x, 1.0), g.mul(y, 1.0), g.mul(z, 0.05)), 160.0, detail=3, distort=0.5)
    rings = g.remap(g.math("SINE", g.mul(grain, 60.0)), 0.6, 1.0)
    col = g.mix(g.mul(rings, 0.35), base, surfaces._scale(base, 0.62))
    grime = g.remap(g.noise(pos, 12.0, detail=3), 0.45, 0.75)
    col = g.mix(g.mul(grime, 0.4), col, surfaces._scale(base, 0.55))
    return dict(color=col, rough=g.lerp(grime, 0.62, 0.42), metal=0.0, height=rings, bump=0.0002)


def _oiled(g, pal):
    """Oiled, handled leather (the cap): the hide's pebble grain worn down smooth and larger, a soft sheen."""
    r = surfaces.leather(g, pal, grain=1.6)
    r["bump"] = 0.00018
    return r


surfaces.RECIPES.setdefault("waxed", _waxed)
surfaces.RECIPES.setdefault("oiled", _oiled)
surfaces.RECIPES.setdefault("corduroy", _corduroy)
surfaces.RECIPES.setdefault("paint", _paint)
surfaces.RECIPES.setdefault("wood", _wood)
surfaces.RECIPES.setdefault("duck", _duck)
surfaces.RECIPES.setdefault("whiskers", _whiskers)
surfaces.SOFT.update({"waxed", "corduroy", "duck", "oiled"})


# ---------------------------------------------------------------------------------- helpers

def remat(obj, kind):
    """Give a part built with a palette kind the realistic material `kind` ("<surface>.<tint>")."""
    obj.data.materials.clear()
    obj.data.materials.append(real.mat(kind))
    return obj


def glue(c, obj, src):
    """Skin a part sitting on a garment with that garment's own weights (nearest face), so it moves
    exactly with the cloth under it: the cloth simulation moved the garment's vertices off the body
    vertices their weights came from, and weights from the body would let the cloth swallow the part."""
    kit.hs.apply_modifiers(obj)
    kit.transfer(src, obj)
    c.parts.append((obj, "DONE", None))
    return obj


def to_hips(obj, frac):
    """Hand the fraction frac(p) of each vertex's thigh weights to the hips: a skirt hangs from the
    belt, it is not dragged along by the legs under it."""
    vg = obj.vertex_groups
    if "hips" not in vg:
        return
    hips = vg["hips"]
    legs = {vg[n].index: vg[n] for n in THIGHS if n in vg}
    for v in obj.data.vertices:
        t = frac(v.co)
        if t <= 0.0:
            continue
        moved = 0.0
        for ge in list(v.groups):
            if ge.group in legs:
                w = ge.weight
                legs[ge.group].add([v.index], w * (1.0 - t), "REPLACE")
                moved += w * t
        if moved > 0.0:
            hips.add([v.index], moved, "ADD")


def weights_from(obj, src, frac):
    """Blend each vertex's weights toward those of the nearest face of `src` by frac(p): a garment
    draped over another (its cloth moved it off the body points its weights came from) moves with
    the one under it."""
    tmp = obj.copy()
    tmp.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(tmp)
    kit.transfer(src, tmp)
    names = [g.name for g in tmp.vertex_groups]
    for n in names:
        if n not in obj.vertex_groups:
            obj.vertex_groups.new(name=n)
    vg = obj.vertex_groups
    for v, tv in zip(obj.data.vertices, tmp.data.vertices):
        t = frac(v.co)
        if t <= 0.0:
            continue
        w = {vg[g.group].name: g.weight * (1 - t) for g in v.groups}
        for g in tv.groups:
            n = names[g.group]
            w[n] = w.get(n, 0.0) + g.weight * t
        for g in list(v.groups):
            vg[g.group].remove([v.index])
        for n, x in w.items():
            if x > 1e-4:
                vg[n].add([v.index], x, "REPLACE")
    me = tmp.data
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.meshes.remove(me)


def hang_weights(obj, z0, z1, z_top):
    """Skirt weights: below z1 a vertex goes with the hips by sm(z, z0, z1) and with the thigh under it
    for the rest, split between the two across the middle, so each flap of a split skirt moves as one
    piece with its leg and the skirt above hangs from the belt; from z1 up to z_top the thigh weights go
    to the hips; above that the weights stay as they are."""
    vg = obj.vertex_groups
    for n in ("hips",) + tuple(sorted(THIGHS)):
        if n not in vg:
            vg.new(name=n)
    hips, L, R = vg["hips"], vg["upper_leg.L"], vg["upper_leg.R"]
    for v in obj.data.vertices:
        z = v.co.z
        if z >= z1:
            continue
        t = float(real._smooth(z, z0, z1))
        sL = float(real._smooth(v.co.x, -0.04, 0.04))
        for ge in list(v.groups):
            vg[ge.group].remove([v.index])
        for g, w in ((hips, t), (L, (1 - t) * sL), (R, (1 - t) * (1 - sL))):
            if w > 1e-4:
                g.add([v.index], w, "REPLACE")
    to_hips(obj, lambda p: 1.0 if z1 <= p.z < z_top else 0.0)


def mesh_obj(name, bm, kind, texel=None):
    """An object from a bmesh with the realistic material `kind`, smooth shaded, no bevel."""
    o = real._bm_obj(name, bm)
    o.data.materials.append(real.mat(kind))
    if texel:
        o["texel"] = texel
    return o


def loft(name, rings, kind, closed=False, cap=True):
    """A solid swept through cross-section rings (each a closed polygon, all the same length): faces
    between consecutive rings, the end rings capped. A collar, a rolled cuff, a tool roll."""
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in r] for r in rings]
    n = len(rings[0])
    pairs = list(zip(vr, vr[1:])) + ([(vr[-1], vr[0])] if closed else [])
    for r0, r1 in pairs:
        for j in range(n):
            k = (j + 1) % n
            bm.faces.new((r0[j], r0[k], r1[k], r1[j]))
    if cap and not closed:
        bm.faces.new(vr[0][::-1])
        bm.faces.new(vr[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_obj(name, bm, kind)


def set_attr(obj, name, values):
    me = obj.data
    if name in me.attributes:
        me.attributes.remove(me.attributes[name])
    at = me.attributes.new(name, "FLOAT", "POINT")
    at.data.foreach_set("value", [float(v) for v in values])


def ring_on(t, centre, normal, offset, n=36, front=(0, -1, 0)):
    """Points round `centre` in the plane with `normal`, `offset` out from the surface in tree `t`
    (rays from the centre outward: the first surface they meet). Starts at the front."""
    nn = Vector(normal).normalized()
    f = Vector(front)
    e1 = (f - nn * f.dot(nn)).normalized()
    e2 = nn.cross(e1).normalized()
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        d = e1 * math.cos(a) + e2 * math.sin(a)
        loc, _ = pmc.hit(t, centre, d)
        out.append(loc + d * offset if loc is not None else Vector(centre) + d * 0.1)
    return out


def outermost(trees, origin, d, reach=0.6):
    """The farthest surface out along d from origin among several trees (a belt over apron and jacket)."""
    d = Vector(d).normalized()
    best = None
    for t in trees:
        loc, nor, _, dist = t.ray_cast(Vector(origin) + d * reach, -d, reach)
        if loc is not None and (best is None or dist < best[2]):
            best = (loc, nor, dist)
    return (best[0], best[1]) if best else (None, None)


def decal(name, t, outline, hole, side, kind, offset=0.0012, thick=0.0007, density=2):
    """Paint laid on a surface: the flat (x, z) `outline` (with a round `hole` (x, z, r) or None)
    triangulated, subdivided `density` times and dropped onto tree `t` along Y from the front (side -1)
    or the back (+1), `offset` off it, `thick` deep. No booleans, so any surface takes it."""
    bm = bmesh.new()
    rings = [outline]
    if hole:
        hx, hz, hr = hole
        rings.append([(hx + hr * math.cos(2 * math.pi * i / 20), hz + hr * math.sin(2 * math.pi * i / 20)) for i in range(20)])
    edges = []
    for r in rings:
        vs = [bm.verts.new((x, 0.0, z)) for x, z in r]
        edges += [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    if density:
        bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if e.calc_length() > 0.008], cuts=density, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
    for v in bm.verts:
        loc, nor = pmc.hit(t, Vector((v.co.x, side * 0.6, v.co.z)), (0, -side, 0))
        if loc is None:
            loc, nor = nearest(t, Vector((v.co.x, 0, v.co.z)))
        v.co = loc + nor * offset
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    if bm.faces and bm.faces[0].normal.y * side < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    o = mesh_obj(name, bm, kind)
    if thick:
        sm = o.modifiers.new("thick", "SOLIDIFY")
        sm.thickness = thick
        sm.offset = -1.0
        sm.use_rim = True
        kit.hs._apply(o, sm.name)
    o["unwrap"] = True
    return o


def nearest(t, p):
    loc, nor, _, _ = t.find_nearest(Vector(p))
    return loc, nor


# ---------------------------------------------------------------------------------- the face

def moustache(c, man, kind="whiskers.scrap_hair"):
    """A full moustache over the upper lip, drooping a little past the corners of the mouth: a pad laid
    on the face with rays, thickest under the nose, thinning out to its edges (where the hair recipe
    lets the skin show through)."""
    E, u = man.face()
    tb = pmc.tree(man.low)
    ns, nv = 18, 7
    W = 0.0345

    def F(x, z):
        return E + Vector((x, 0, z)) * u

    def edge_z(x, v):
        a = min(1.0, abs(x) / W)
        top = -0.0515 - 0.011 * a ** 2
        bot = -0.0655 - 0.0165 * a ** 2.4
        return top + (bot - top) * v
    top_rows, bot_rows, seam = [], [], []
    for j in range(nv + 1):
        v = j / nv
        rt, rb = [], []
        for i in range(ns + 1):
            s = -1 + 2 * i / ns
            w = W * (0.86 + 0.14 * v)
            x = s * w
            p = F(x, edge_z(x, v))
            loc, nor = pmc.hit(tb, p + Vector((0, -0.12, 0)), (0, 1, 0))
            if loc is None:
                loc, nor = nearest(tb, p)
            prof = (max(0.0, 1 - abs(s) ** 2.2) ** 0.7) * (math.sin(math.pi * (0.08 + 0.84 * v)) ** 0.5)
            h = 0.0007 + 0.0048 * u * prof * (1.0 + 0.25 * v)
            rt.append(loc + nor * h)
            rb.append(loc + nor * 0.0004)
            seam.append(min((1 - abs(s)) * w * u, v * 0.016 * u, (1 - v) * 0.016 * u))
        top_rows.append(rt)
        bot_rows.append(rb)
    bm = bmesh.new()
    T = [[bm.verts.new(p) for p in r] for r in top_rows]
    B = [[bm.verts.new(p) for p in r] for r in bot_rows]
    for j in range(nv):
        for i in range(ns):
            bm.faces.new((T[j][i], T[j][i + 1], T[j + 1][i + 1], T[j + 1][i]))
            bm.faces.new((B[j][i], B[j + 1][i], B[j + 1][i + 1], B[j][i + 1]))
    ring = [(0, i) for i in range(ns)] + [(j, ns) for j in range(nv)] + [(nv, i) for i in range(ns, 0, -1)] + [(j, 0) for j in range(nv, 0, -1)]
    for k in range(len(ring)):
        a, b2 = ring[k], ring[(k + 1) % len(ring)]
        bm.faces.new((T[a[0]][a[1]], B[a[0]][a[1]], B[b2[0]][b2[1]], T[b2[0]][b2[1]]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = mesh_obj("moustache", bm, kind, texel=1.6)
    set_attr(o, "seam", seam + [0.0] * len(seam))
    c.rigid(o, "head")
    return o


# ---------------------------------------------------------------------------------- the build

def build():
    b = real.Anatomy(height=1.78, body="male", sole=0.034)
    c = real.begin("mechanic", b)
    man = real.body(c, stubble=0.8)
    J, seg, sm = b.j, kit.seg_dist, real._smooth
    lead = real.bones_at(man)
    E, u = man.face()
    hc = man.head_center()
    tb = pmc.tree(man.low)
    armpit, crotch = b.at("armpit"), b.at("crotch")
    LIMBS = UPPER_ARMS | FOREARMS
    LEGS = THIGHS | SHINS

    def on_arm(p):
        return lead(p) in LIMBS

    # ---------------------------------------------------------------- hands and feet
    real.gloves(c, man, "glove.scrap_suede", cuff=0.05)
    boot_top = 0.155
    real.boots(c, man, "leather.scrap_boot", sole_kind="rubber", trim="leather", top=boot_top, lace="scrap_lace", tab="leather")

    # ---------------------------------------------------------------- duck trousers with turn-ups
    top_z = b.hip_z + 0.10
    hem = b.sole + boot_top + 0.02

    def t_ease(p):
        band = 0.003 * (1 - sm(top_z - p.z, 0.02, 0.07))
        return 0.013 + band + 0.007 * sm(top_z - p.z, 0.04, 0.2) + 0.010 * sm(J("lower_leg.L", 0.0).z - p.z, 0.0, 0.15)

    def t_pin(p):
        return 1.0 if p.z > top_z - 0.045 or p.z < hem + 0.012 else 0.0

    def t_slack(p):
        return 0.6 * sm(hem + 0.12 - p.z, 0.0, 0.09)

    trousers = real.garment(c, man, "trousers", "duck.secondary", lambda p: lead(p) in LEGS | {"hips", "spine"} and hem - 0.03 < p.z < top_z + 0.03,
                            [((0, 0, top_z), (0, 0, 1)), ((0, 0, hem), (0, 0, -1), lambda p: lead(p) in LEGS)],
                            ease=t_ease, pin=t_pin, slack=t_slack, bend=18.0, texel=1.0)
    c.hide_under(trousers.low, 0.06, 2)
    tt = pmc.tree(trousers.low)
    for s in ("L", "R"):
        # Turn-ups: a 4 cm band of the trouser leg folded up outside it.
        k0, k1 = J("lower_leg." + s, 0.0), J("lower_leg." + s, 1.0)
        ax = (k1 - k0).normalized()
        t0 = (hem - k0.z) / (k1.z - k0.z)
        a, bb = k0.lerp(k1, t0 + 0.004 / (k0.z - k1.z)), k0.lerp(k1, t0 - 0.042 / (k0.z - k1.z))
        r = pmc._radius(tt, a.lerp(bb, 0.5), ax)
        cuff = pmc.wrap("turn_up", a, bb, r + 0.004, r + 0.004, -180, 180, 0.0035, "secondary", nt=3, nphi=24, bevel=0.0015, fit=(tt, 0.0025))
        remat(cuff, "duck.secondary")
        c.rigid(cuff, "lower_leg." + s)

    # Patched: scraps of the waxed jacket cloth over the knees (not quite matched), brown duck on the back of the right thigh.
    for s, sx, dz, hw, hh in (("L", 1, 0.004, 40, 0.068), ("R", -1, -0.018, 34, 0.058)):
        K = J("lower_leg." + s, 0.0)

        def knee(p, K=K, sx=sx, dz=dz, hw=hw, hh=hh):
            d = p - K
            if lead(p) not in LEGS or d.y > 0:
                return False
            a = math.degrees(math.atan2(d.x, -d.y))
            return abs(a - sx * 8) < hw and abs(d.z - dz - 0.12 * d.x * sx) < hh
        real.patch(c, trousers.low, "knee_patch", "waxed.primary", knee, lift=0.0015, puff=0.0025, thick=0.002)
    ra, rb = J("upper_leg.R", 0.0), J("upper_leg.R", 1.0)
    around = pmc._limb(ra, rb)

    def seat(p):
        if lead(p) != "upper_leg.R":
            return False
        t, a = around(p)
        return 0.22 < t < 0.42 and abs(abs(a) - 168) < 30
    real.patch(c, trousers.low, "seat_patch", "duck.scrap_wax", seat, lift=0.0015, puff=0.002, thick=0.002)

    # ---------------------------------------------------------------- waxed canvas chore jacket
    neck = J("neck", 0.0)
    jhem = crotch + 0.07
    neckline = (Vector((0, 0, neck.z + 0.02)), Vector((0, -0.38, 1)).normalized())
    cuts = [neckline]
    for s in ("L", "R"):
        e, w = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        cuts.append((e.lerp(w, 0.88), w - e, lambda p, e=e, w=w: on_arm(p) and seg(p, e, w + (w - e) * 0.6) < 0.09))
    cuts.append(((0, 0, jhem), (0, 0, -1), lambda p: not on_arm(p)))

    def j_ease(p):
        if not on_arm(p):
            return 0.009 + 0.010 * sm(neck.z + 0.01 - p.z, 0.0, 0.09) + 0.006 * sm(armpit - 0.1 - p.z, 0.0, 0.3)
        arm = min(seg(p, J("upper_arm." + s, 0.3), J("forearm." + s, 1.0)) for s in ("L", "R"))
        return 0.012 + 0.012 * max(0.0, min(1.0, (0.09 - arm) / 0.03))

    def j_pin(p):
        w = 0.0
        if p.z > neck.z - 0.025 and not on_arm(p):
            w = 1.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.88)
            d = (wr - e).normalized()
            if on_arm(p) and seg(p, e, wr) < 0.1 and (p - wr).dot(d) > -0.02:
                w = 1.0
        return w

    def j_slack(p):
        w = 0.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.88)
            d = wr - e
            L = d.length
            d.normalize()
            t = (p - e).dot(d) / L
            if on_arm(p) and seg(p, e, wr) < 0.1 and t > 0.25:
                w = max(w, min(1.0, (t - 0.25) / 0.45))
        return w
    jacket = real.garment(c, man, "jacket", "waxed.primary", lambda p: lead(p) in TORSO | LIMBS | THIGHS | {"neck"} and p.z > jhem - 0.05,
                          cuts, ease=j_ease, pin=j_pin, slack=j_slack, bend=20.0, stiff=1.4, texel=1.25, collide=[trousers.low])
    c.hide_under(jacket.low, 0.05, 2)
    # The jacket's skirt hangs from the hips (the thighs would push it out through the apron and the belt).
    to_hips(jacket.low, lambda p: 1 - float(sm(p.z, b.hip_z - 0.02, b.hip_z + 0.06)))
    tj = pmc.tree(jacket.low)

    # Corduroy collar, turned down over the neckline, open at the throat.
    col = collar(c, jacket.low, tj, neck, J("neck", 1.0) - neck)

    # Leather elbow patches, sewn on.
    for s, sx in (("L", 1), ("R", -1)):
        el = J("forearm." + s, 0.0)
        ua = (J("upper_arm." + s, 0.0) - el).normalized()
        fa = (J("forearm." + s, 1.0) - el).normalized()
        back = (Vector((0, 1, 0)) - (ua + fa).normalized()).normalized()  # the point of the elbow

        def region(p, el=el, back=back, ua=ua, fa=fa):
            if not on_arm(p):
                return False
            d = p - el
            if d.dot(back) < 0.004:
                return False
            a_u, a_f = d.dot(ua), d.dot(fa)
            along, ax = (a_u, ua) if a_u > a_f else (-a_f, fa)
            lat = d - ax * d.dot(ax) - back * d.dot(back)
            return ((along - 0.006) / 0.068) ** 2 + (lat.length / 0.042) ** 2 < 1.0
        real.patch(c, jacket.low, "elbow_patch", "leather", region, lift=0.0015, puff=0.003, thick=0.0025)

    # The Scrappers' cog, hand-painted big across the back.
    cz = armpit + 0.015
    glue(c, decal("painted_cog", tj, cog(0.0, cz, 0.078, teeth=10, depth=0.25), (0.0, cz, 0.026), 1, "paint.scrap_paint"), jacket.low)

    # Placket and brass buttons down the front.
    pl = []
    for i in range(16):
        z = jhem + 0.01 + (neckline[0].z - 0.05 - jhem) * i / 15
        loc, nor = pmc.hit(tj, (0, -0.5, z), (0, 1, 0))
        if loc is not None:
            pl.append(loc + Vector((0, -0.0025, 0)))
    placket = pmc.sweep("placket", pl, 0.032, 0.004, "primary", lambda p: Vector((0, -1, 0)))
    glue(c, remat(placket, "waxed.primary"), jacket.low)
    for k in range(4):
        q = pl[len(pl) - 1 - k * 4]
        glue(c, kit.cyl("button", q + Vector((0, -0.002, 0)), q + Vector((0, -0.0065, 0)), 0.0075, "brass", segs=14, bevel=0.0012), jacket.low)

    # ---------------------------------------------------------------- head: hair, moustache, cap, goggles
    def F(x, y, z):
        return E + Vector((x, y, z)) * u

    def fx(p):
        d = (Vector(p) - E) / u
        return d.x, d.y, d.z
    hair = real.layer(c, man, "hair", "hair.scrap_hair", lambda p: lead(p) in ("head", "neck") and fx(p)[2] > -0.09,
                      [(F(0, -0.06, 0.068), Vector((0, -0.8, -1.0))),
                       (F(0, 0.03, 0.006), Vector((0, -0.7, -1.0))),
                       (F(0, 0.0, -0.066), Vector((0, -0.15, -1.0)))],
                      ease=0.004, smooth=1, texel=1.2, seams="hems")
    c.hide_under(hair, 0.012, 1)
    moustache(c, man)

    # Leather work cap: the skull's shape eased out, a short stiff brim, a band, the goggles on it.
    plane_p = hc + Vector((0, 0, 0.014))
    plane_n = Vector((0, 0.17, 1)).normalized()
    def cap_ease(p):
        # Snug at the band, a fuller crown above it, fullest toward the front.
        return 0.0115 + 0.011 * float(sm(p.z, plane_p.z + 0.02, hc.z + 0.1)) * (0.75 + 0.25 * float(sm(-(p.y - hc.y), -0.06, 0.06)))
    cap = real.layer(c, man, "cap", "oiled.scrap_cap", lambda p: lead(p) == "head" and p.z > hc.z - 0.03, [(plane_p, -plane_n)],
                     ease=cap_ease, smooth=6, thick=0.0035, texel=1.2, seams="hems")
    tcap = pmc.tree(cap)
    crown = cap_panels(cap, tcap, hc)
    cap_welts(c, tcap, hc, crown[0], crown[1], plane_p, plane_n)
    c.rigid(kit.cyl("cap_button", crown[0] - crown[1] * 0.003, crown[0] + crown[1] * 0.0045, 0.0085, "scrap_cap", segs=16, bevel=0.002), "head")
    zb = plane_p.z - plane_n.y / plane_n.z * (hc.y - 0.1 - plane_p.y) + 0.006
    loc, _ = pmc.hit(tcap, Vector((hc.x, hc.y - 0.4, zb)), (0, 1, 0))
    front_y = loc.y
    side_hit, _ = pmc.hit(tcap, Vector((hc.x + 0.3, hc.y, zb)), (-1, 0, 0))
    rx_in = (side_hit.x - hc.x) * 0.92 if side_hit else 0.081
    ry_in = hc.y - front_y
    outer = [(1.08 * rx_in * math.sin(math.radians(a)), -(ry_in + 0.058) * math.cos(math.radians(a))) for a in range(-76, 77, 12)]
    inner = [(rx_in * math.sin(math.radians(a)), -ry_in * math.cos(math.radians(a))) for a in range(76, -77, -12)]
    brim = kit.plan("brim", outer + inner, 0.006, "scrap_cap", z=0.0, bevel=0.0022)
    pmc.slice_x(brim, 0.012)
    for v in brim.data.vertices:
        v.co.z -= 3.2 * v.co.x * v.co.x
    brim.data.transform(Matrix.Translation(Vector((hc.x, front_y + 0.003, zb))) @ Matrix.Rotation(math.radians(16), 4, "X")
                        @ Matrix.Translation((0, ry_in, 0)))
    c.rigid(brim, "head")
    band_pts = ring_on(tcap, plane_p + plane_n * 0.011, plane_n, 0.0035 + 0.0012, n=40)
    c.rigid(remat(pmc.sweep("cap_band", band_pts, 0.016, 0.0025, "leather", pmc.radial(plane_p, plane_n), closed=True), "leather.scrap_boot"), "head")
    goggles(c, tcap, hc, plane_p, plane_n, zb)

    # ---------------------------------------------------------------- welding apron, tool belt, gauges
    ap = apron(c, man, lead, jacket, trousers, col)
    tool_belt(c, b, [pmc.tree(ap.low), tj, tt])
    wrist_gauge(c, b, tj)

    economise(c)
    return c


def economise(c):
    """Single-segment bevels on every small or finely bevelled part (as the Contractor does)."""
    pmc.economise(c)


def collar(c, jacket, tj, neck, neck_axis, kind="corduroy.scrap_cord", gap=9.0, n=44):
    """A turned-down collar on the jacket's neckline: a stand up the neck and a fall folded down over it
    onto the shoulders, its points spreading onto the chest; open at the throat. Stitched along its
    edge."""
    loops = real.boundary_loops(jacket)
    me = jacket.data
    top = max(loops, key=lambda L: sum(me.vertices[i].co.z for i in L) / len(L))
    yc = neck.y
    pts = sorted(((math.degrees(math.atan2(me.vertices[i].co.x, -(me.vertices[i].co.y - yc))) % 360, me.vertices[i].co.copy()) for i in top),
                 key=lambda t: t[0])

    def at(th):
        th %= 360
        for k in range(len(pts)):
            a0, p0 = pts[k - 1]
            a1, p1 = pts[k]
            if k == 0:
                a0 -= 360
            if a0 <= th <= a1:
                return p0.lerp(p1, (th - a0) / max(a1 - a0, 1e-6))
        return pts[0][1]
    up = Vector(neck_axis).normalized()
    rings, seam, su = [], [], []
    for i in range(n + 1):
        th = gap + (360 - 2 * gap) * i / n
        tf = min(th, 360 - th)
        p = at(th)
        d = Vector((math.sin(math.radians(th)), -math.cos(math.radians(th)), 0))
        back = (1 - math.cos(math.radians(th))) / 2
        tip = float(real._smooth(tf, 42.0, 10.0))
        h = 0.013 + 0.012 * back
        q0 = p + d * (0.028 + 0.004 * tip) - up * (0.008 + 0.004 * back + 0.02 * tip)
        Fp, nF = nearest(tj, q0)
        Fo = Fp + nF * 0.0032
        Fi = Fp + nF * 0.0006
        crown_in = p - d * 0.0045 + up * h
        crown = p - d * 0.0012 + up * (h + 0.0035)
        crown_out = p + d * 0.0035 + up * (h + 0.0012)
        mid_o = crown_out.lerp(Fo, 0.5) + nF * 0.003
        mid_i = (p + d * 0.0035 + up * (h - 0.005)).lerp(Fi, 0.5)
        prof = [p - d * 0.0015, crown_in, crown, crown_out, mid_o, Fo, Fi, mid_i, p + d * 0.0035 + up * (h - 0.005), p + d * 0.002 + up * 0.002]
        rings.append(prof)
        L = [0.0]
        for k in range(1, len(prof)):
            L.append(L[-1] + (prof[k] - prof[k - 1]).length)
        iF = 5
        seam += [abs(L[k] - L[iF]) if k <= 6 else abs(L[k] - L[6]) for k in range(len(prof))]
        su += [th / 360 * 0.4] * len(prof)
    o = loft("collar", rings, kind)
    set_attr(o, "seam", seam)
    set_attr(o, "seam_u", su)
    o["texel"] = 1.2
    glue(c, o, jacket)
    return o


def cap_panels(cap, tcap, hc, panels=6):
    """Stitch the cap into `panels` gores meeting at the crown (the stitching and the seam's roll come
    from the seam attributes, joined with the hem's). Returns (crown point, axis)."""
    top, _ = pmc.hit(tcap, hc + Vector((0, 0.012, 0.4)), (0, 0, -1))
    axis = (top - (hc + Vector((0, 0.012, 0)))).normalized()
    f = Vector((0, -1, 0))
    f = (f - axis * f.dot(axis)).normalized()
    sd = axis.cross(f)
    me = cap.data
    seam = [d.value for d in me.attributes["seam"].data]
    su = [d.value for d in me.attributes["seam_u"].data]
    step = 2 * math.pi / panels
    for i, v in enumerate(me.vertices):
        q = v.co - top
        r = q - axis * q.dot(axis)
        phi = math.atan2(r.dot(sd), r.dot(f)) - step / 2  # a gore, not a seam, at the front
        k = round(phi / step)
        dist = abs(phi - k * step) * r.length
        if dist < seam[i]:
            seam[i] = dist
            su[i] = (v.co - top).length
    set_attr(cap, "seam", seam)
    set_attr(cap, "seam_u", su)
    return top, axis


def cap_welts(c, tcap, hc, top, axis, plane_p, plane_n, panels=6, thick=0.0035):
    """A raised welt of leather over each gore seam, from the crown button down to the band."""
    f = Vector((0, -1, 0))
    f = (f - axis * f.dot(axis)).normalized()
    sd = axis.cross(f)
    o = hc + Vector((0, 0.012, 0))
    stop = 0.011 + 0.0075  # the band's top edge above the cap plane
    for k in range(panels):
        phi = (k + 0.5) * 2 * math.pi / panels
        r = f * math.cos(phi) + sd * math.sin(phi)
        pts = []
        for j in range(24):
            e = math.radians(5.5 + 100 * j / 23)
            d = axis * math.cos(e) + r * math.sin(e)
            loc, _ = pmc.hit(tcap, o, d)
            if loc is None:
                continue
            q = loc + d * (thick + 0.0009)
            if (q - plane_p).dot(plane_n) < stop:
                break
            pts.append(q)
        if len(pts) > 3:
            w = pmc.sweep("cap_welt", pts, 0.0065, 0.0018, "scrap_cap", lambda p: Vector(p) - o, bevel=0.0007)
            c.rigid(w, "head")


def goggles(c, tcap, hc, plane_p, plane_n, zb):
    """Brass welding goggles pushed up on the cap: blackened steel eyecups with leather gaskets, dark
    green glass in screwed brass bezels, a hinged brass bridge, a tan strap round the crown."""
    zg = zb + 0.03
    cups = []
    for sx in (1, -1):
        loc, nor = pmc.hit(tcap, Vector((hc.x + sx * 0.035, hc.y - 0.4, zg)), (0, 1, 0))
        n = (nor + Vector((0, 0, 0.35))).normalized()
        X = Vector((sx, 0, 0))
        t1 = (X - n * n.dot(X)).normalized()  # outward
        t2 = n.cross(t1).normalized()
        p = loc + n * 0.002
        parts = [kit.cyl("gasket", p - n * 0.001, p + n * 0.005, 0.0235, "leather", r1=0.0225, segs=20, bevel=0.0015),
                 kit.cyl("eyecup", p + n * 0.004, p + n * 0.017, 0.0215, "steel", r1=0.0195, segs=20, bevel=0.0012),
                 kit.ring("bezel", p + n * 0.0175, n, 0.0222, 0.0158, 0.0048, "brass", segs=24),
                 kit.cyl("lens", p + n * 0.0155, p + n * 0.0185, 0.0162, "scrap_lens", segs=20, bevel=0.0004)]
        parts.append(rivets("bezel_screws", [(p + n * 0.0199 + (t1 * math.cos(q) + t2 * math.sin(q)) * 0.019, n) for q in (0.5, 0.5 + math.pi / 2, 0.5 + math.pi, 0.5 + 1.5 * math.pi)],
                            r=0.0015, material="steel", segs=6))
        lug = p + n * 0.009 + t1 * 0.023
        parts.append(kit.block("strap_lug", (0, 0, 0), (0.008, 0.012, 0.01), "brass", bevel=0.001))
        parts[-1].data.transform(Matrix.Translation(lug))
        c.rigid(kit.join(parts, "goggle"), "head")
        cups.append((p, n, t1, lug))
    (pl, nl, tl, gl), (pr, nr, tr, gr) = cups
    a = pl + nl * 0.010 - tl * 0.021
    bq = pr + nr * 0.010 - tr * 0.021
    mid = (a + bq) / 2 + (nl + nr).normalized() * 0.004
    c.rigid(kit.rope("goggle_bridge", [a, mid, bq], 0.0024, "brass"), "head")
    c.rigid(kit.cyl("bridge_hinge", mid - Vector((0.004, 0, 0)), mid + Vector((0.004, 0, 0)), 0.0036, "brass", segs=10, bevel=0.0006), "head")
    # The strap: from each lug round the back of the crown, just above the band.
    sn = Vector((0, 0.2, 1)).normalized()
    y_f = (gl.y + gr.y) / 2
    cen = Vector((hc.x, hc.y, (gl.z + gr.z) / 2 - 0.2 * (hc.y - y_f)))
    ring = ring_on(tcap, cen, sn, 0.0035 + 0.0025, n=48)
    keep = [q for q in ring if q.y > min(gl.y, gr.y) + 0.004]
    keep.sort(key=lambda q: math.atan2(q.x - hc.x, q.y - hc.y))
    path = [gr] + keep + [gl] if keep and keep[0].x < 0 else [gl] + keep + [gr]
    c.rigid(remat(pmc.sweep("goggle_strap", path, 0.02, 0.003, "accent", pmc.radial(cen, sn)), "leather.accent"), "head")


def apron(c, man, lead, jacket, trousers, col):
    """A split-leg welding apron of heavy leather: a bib from the chest, a skirt round the front of the
    hips, a flap down the front of each thigh; cut from the body and draped stiff over the jacket and
    trousers. Tan neck, waist and thigh straps with brass buckles and rivets, a bib pocket holding a
    pencil and a brass gauge, the Scrappers' cog painted on the left flap."""
    b = c.b
    J, sm = b.j, real._smooth
    armpit, crotch = b.at("armpit"), b.at("crotch")
    z_top = armpit + 0.09
    z_w1, z_w2 = b.hip_z + 0.26, b.hip_z + 0.13
    z_bot = J("lower_leg.L", 0.0).z + 0.115  # clear of the knee patches when the knee bends
    yc = J("spine", 0.0).y
    x_bib, x_skirt = 0.118, 0.162
    z_strap = {s: J("upper_leg." + s, 0.0).lerp(J("upper_leg." + s, 1.0), 0.52).z for s in ("L", "R")}
    LIMBS = UPPER_ARMS | FOREARMS | {"hand.L", "hand.R"}
    LEGS = THIGHS | SHINS

    def keep(p):
        if not (z_bot - 0.03 < p.z < z_top + 0.03):
            return False
        L = lead(p)
        if L in LIMBS or L in ("neck", "head"):
            return False
        if p.z > crotch + 0.01:
            return p.y < yc + 0.01
        return L in LEGS
    # The outline, all in lines seen from the front (planes along Y), so the skirt runs straight down
    # into the flaps: the bib's sides, a taper out to the skirt, one outer edge from the waist to the
    # hem, and a split between the legs, its inner edges rising to a shallow point over the crotch.
    xo_bot = x_skirt - 0.012
    xi_top, xi_bot = 0.036, 0.06
    z_split, z_apex = crotch, crotch + 0.025

    def line(p0, p1, side):
        """The plane through the front-view line p0 -> p1 ((x, z)), removing the side that `side` (x, z) points to."""
        d = Vector((p1[0] - p0[0], 0, p1[1] - p0[1]))
        n = Vector((-d.z, 0, d.x)).normalized()
        if n.dot(Vector((side[0], 0, side[1]))) < 0:
            n = -n
        return Vector((p0[0], 0, p0[1])), n
    cuts = [((0, 0, z_top), (0, 0, 1)), ((0, 0, z_bot), (0, 0, -1))]
    for sx in (1, -1):
        cuts.append(((sx * x_bib, 0, 0), (sx, 0, 0), lambda p: p.z > z_w1))
        cuts.append(line((sx * x_bib, z_w1), (sx * x_skirt, z_w2), (sx, 1)) + (lambda p: z_w2 - 0.01 < p.z <= z_w1,))
        cuts.append(line((sx * x_skirt, z_w2), (sx * xo_bot, z_bot), (sx, 0)) + (lambda p, sx=sx: p.z <= z_w2 + 0.01 and p.x * sx > 0,))
    for s, sx in (("L", 1), ("R", -1)):
        # The back of the leg off (the flap covers the front half of the thigh) ...
        a = J("upper_leg." + s, 0.0)
        A = (J("upper_leg." + s, 1.0) - a).normalized()
        N = (Vector((0, 1, 0)) - A * A.y).normalized()
        cuts.append((a + N * 0.012, N, lambda p, s=s: p.z < crotch + 0.012 and lead(p) in {"upper_leg." + s, "lower_leg." + s}))
        # ... its inner edge, then the top of the split.
        cuts.append(line((sx * xi_top, z_split), (sx * xi_bot, z_bot), (-sx, 0)) + (lambda p, sx=sx: p.z < z_split + 0.006 and p.x * sx > 0,))
        cuts.append(line((0.0, z_apex), (sx * xi_top, z_split), (0, -1))
                    + (lambda p, sx=sx: crotch - 0.04 < p.z < z_apex + 0.012 and 0 <= p.x * sx < xi_top,))

    under = [pmc.tree(jacket.low), pmc.tree(trousers.low)]
    # The skirt hangs flat across the front from the belt, not into the groin: at each height, the
    # front it bridges is the most forward point of the clothes under it, curving back a little to the sides.
    flat = {}
    for i in range(-8, 21):
        z = crotch + 0.01 * i
        ys = [outermost(under, (x, yc, z), (0, -1, 0))[0] for x in [-0.13 + 0.26 * k / 16 for k in range(17)]]
        flat[i] = min(q.y for q in ys if q is not None) - 0.016

    def ease(p):
        # Off the body by at least this, and always 1.4 cm clear of the jacket and trousers under it.
        e = 0.032 + 0.008 * float(sm(p.z, crotch, crotch + 0.12))
        _, n, _, _ = man.tree.find_nearest(p)
        for t in under:
            loc, _, _, d = t.ray_cast(p + n * 0.001, n, 0.2)
            if loc is not None:
                e = max(e, d + 0.014)
        k = float(sm(p.z, crotch - 0.035, crotch + 0.025)) * (1 - float(sm(p.z, crotch + 0.16, crotch + 0.2))) \
            * (1 - float(sm(abs(p.x), 0.09, 0.14)))  # forward over the groin, not out at the hips
        if k > 0 and n.y < -0.45:
            f = (p.z - crotch) / 0.01
            i0 = max(-8, min(19, int(math.floor(f))))
            yt = flat[i0] + (flat[i0 + 1] - flat[i0]) * max(0.0, min(1.0, f - i0)) + 1.6 * p.x * p.x
            e = max(e, min(0.1, k * (p.y - yt) / -n.y))
        return e

    def pin(p):
        if p.z > z_top - 0.03:
            return 1.0
        if p.z > crotch and abs(p.z - (b.hip_z + 0.02)) < 0.028:
            return 1.0  # under the tool belt
        if p.z < crotch and abs(p.z - z_strap["L" if p.x > 0 else "R"]) < 0.016:
            return 1.0
        return 0.0
    ap = real.garment(c, man, "apron", "leather", keep, cuts, ease=ease, smooth=3, pin=pin, bend=70.0, stiff=3.0, mass=0.5,
                      texel=1.15, seams=False, collide=[jacket.low, trousers.low])
    for o in (ap.low, ap.high):
        real.seam_attrs(o, uv_seams=False)
    # The skirt hangs from the belt; the flaps go with the thighs from just below the crotch.
    hang_weights(ap.low, crotch - 0.03, crotch + 0.06, b.hip_z + 0.04)
    # The bib moves with the jacket it lies on.
    weights_from(ap.low, jacket.low, lambda p: float(sm(p.z, b.hip_z + 0.03, b.hip_z + 0.10)))
    ta = pmc.tree(ap.low)
    tj, tt, tcol = pmc.tree(jacket.low), pmc.tree(trousers.low), pmc.tree(col)

    def on_front(x, z, off):
        loc, nor = pmc.hit(ta, (x, -0.6, z), (0, 1, 0))
        return (loc + nor * off, nor) if loc is not None else (None, None)

    # Bib pocket (the wearer's right) with a pencil and a brass gauge standing in it.
    px0, px1, pz0, pz1 = -0.092, -0.014, z_top - 0.135, z_top - 0.04
    real.patch(c, ap.low, "bib_pocket", "leather", lambda p: px0 < p.x < px1 and pz0 < p.z < pz1 and p.y < 0, lift=0.002, puff=0.006, thick=0.003)
    pm, pn = on_front(-0.05, pz1, 0.006)
    if pm is not None:
        c.rigid(kit.join([kit.cyl("pencil", pm + Vector((0.022, 0.004, -0.04)), pm + Vector((0.026, 0.0, 0.048)), 0.0042, "scrap_ash", segs=6, bevel=0.0004),
                          kit.cyl("pencil_tip", pm + Vector((0.026, 0.0, 0.048)), pm + Vector((0.0265, -0.0002, 0.06)), 0.0042, "black", r1=0.0008, segs=6, bevel=0)],
                         "pencil"), "chest")
        g0 = pm + Vector((-0.012, 0.002, 0.012))
        gp = gauge(g0, Vector((0, -1, 0.25)), Vector((0, 0, 1)), r=0.0195, depth=0.011, needle=-30)
        gp.append(kit.cyl("gauge_stem", g0 + Vector((0, 0.004, -0.018)), g0 + Vector((0, 0.004, -0.05)), 0.004, "brass", segs=10, bevel=0.0004))
        c.rigid(kit.join(gp, "pocket_gauge"), "chest")
    rivets_at = []
    for x, z in ((px0 + 0.006, pz1 - 0.006), (px1 - 0.006, pz1 - 0.006)):
        q, n = on_front(x, z, 0.0085)
        if q is not None:
            rivets_at.append((q, n))

    # Neck strap: from the bib's top corners up over the collar and round the back of the neck.
    neck = J("neck", 0.0)
    path = []
    for sx in (1, -1):
        side = []
        q, n = on_front(sx * (x_bib - 0.016), z_top - 0.012, 0.004)
        if q is not None:
            side.append(q)
            rivets_at.append((q + n * 0.0025, n))
        for x, z in ((x_bib - 0.02, z_top + 0.045), (x_bib - 0.028, z_top + 0.09)):
            loc, _ = outermost([tj, tcol], (sx * x, 0.0, z), (0, -1, 0), 0.4)
            if loc is not None:
                side.append(loc + Vector((0, -0.004, 0)))
        for th, z in ((68, neck.z - 0.006), (100, neck.z + 0.014), (135, neck.z + 0.026), (172, neck.z + 0.03)):
            d = Vector((sx * math.sin(math.radians(th)), -math.cos(math.radians(th)), 0))
            o = Vector((0, neck.y, z))
            loc, nor = outermost([tj, tcol], o, d, 0.4)
            if loc is not None:
                side.append(loc + d * 0.004)
        path.append(side)
    strap = path[0] + path[1][::-1]
    strap = pmc.smooth_path(strap, 3)
    c.rigid(remat(pmc.sweep("neck_strap", strap, 0.022, 0.0035, "accent", pmc.radial((0, neck.y, 0))), "leather.accent"), "chest")

    # Thigh straps round the back of each leg, from the flap's outer edge to its inner edge.
    for s, sx in (("L", 1), ("R", -1)):
        a, b1 = J("upper_leg." + s, 0.0), J("upper_leg." + s, 1.0)
        A = (b1 - a).normalized()
        cc = a + A * ((z_strap[s] - a.z) / A.z)
        pts = []
        for i in range(21):
            th = 70 + 220 * i / 20 if s == "L" else -70 - 220 * i / 20
            d = Vector((math.sin(math.radians(th)), -math.cos(math.radians(th)), 0))
            loc, nor = outermost([tt, ta], cc, d, 0.25)
            if loc is not None:
                pts.append(loc + d * 0.0035)
        c.rigid(remat(pmc.sweep("thigh_strap", pts, 0.022, 0.0035, "accent", pmc.radial(cc)), "leather.accent"), "upper_leg." + s)
        q = pts[len(pts) // 2 + 3 * (1 if s == "L" else -1)]
        tq = (pts[len(pts) // 2 + 4] - pts[len(pts) // 2 + 2]).normalized()
        nq = Vector((q.x - cc.x, q.y - cc.y, 0)).normalized()
        c.rigid(buckle("thigh_buckle", q + nq * 0.003, tq, nq, 0.028), "upper_leg." + s)
        for q2 in (pts[0], pts[-1]):
            n2 = Vector((q2.x - cc.x, q2.y - cc.y, 0)).normalized()
            rivets_at.append((q2 + n2 * 0.0022, n2))
    glue(c, rivets("apron_rivets", rivets_at, r=0.0042, material="brass"), ap.low)

    # The Scrappers' cog, hand-painted on the left flap.
    ul = J("upper_leg.L", 0.0).lerp(J("upper_leg.L", 1.0), 0.60)
    cx, cz = ul.x + 0.01, ul.z
    paint = decal("painted_cog", ta, cog(cx, cz, 0.046, teeth=9, depth=0.26), (cx, cz, 0.0165), -1, "paint.scrap_paint")
    glue(c, paint, ap.low)
    return ap


def buckle(name, at, along, out, w=0.03):
    """A forged brass roller buckle: a frame with a centre bar and a tongue, lying on a strap running
    `along`, facing `out`."""
    u, n = Vector(along).normalized(), Vector(out).normalized()
    s = n.cross(u).normalized()
    M = Matrix((u, s, n)).transposed().to_4x4()
    M.translation = Vector(at)
    fr = kit.block(name, (0, 0, 0.001), (w * 0.9, w * 1.15, 0.004), "brass", bevel=0.001)
    kit.cut(fr, kit.block("hole", (0.0, 0, 0.001), (w * 0.62, w * 0.85, 0.01), "steel", bevel=0))
    bar = kit.cyl(name, (0, -w * 0.5, 0.002), (0, w * 0.5, 0.002), 0.0022, "brass", segs=8, bevel=0)
    tongue = kit.block(name, (w * 0.2, 0, 0.0028), (w * 0.42, 0.0026, 0.002), "steel", bevel=0.0005)
    o = kit.join([fr, bar, tongue], name)
    o.data.transform(M)
    return o


def tool_belt(c, b, trees):
    """A wide leather tool belt over the apron and the jacket: a brass buckle, a hammer through a loop on
    the right hip, a tool pouch on the left, an oil can behind it and a waxed tool roll across the back."""
    yc = b.j("spine", 0.0).y
    zb = b.hip_z + 0.02
    pts, dirs = [], []
    n = 40
    for i in range(n):
        th = 360 * i / n
        d = Vector((math.sin(math.radians(th)), -math.cos(math.radians(th)), 0))
        loc, _ = outermost(trees, (0, yc, zb), d)
        pts.append((loc if loc is not None else Vector((0, yc, zb)) + d * 0.17) + d * 0.006)
        dirs.append(d)
    for _ in range(2):
        pts = [(pts[i - 1] + pts[i] * 2 + pts[(i + 1) % n]) / 4 for i in range(n)]
    belt = pmc.sweep("tool_belt", pts, 0.048, 0.008, "leather", pmc.radial((0, yc, 0)), closed=True)
    c.add(belt, ["hips", "spine"])
    spots = []
    for i in range(n):
        th = 360 * i / n
        if 25 < th < 335 and i % 2 == 0:
            for dz in (0.017, -0.017):
                spots.append((pts[i] + dirs[i] * 0.0042 + Vector((0, 0, dz)), dirs[i]))
    c.add(rivets("belt_rivets", spots, r=0.003, material="brass"), ["hips", "spine"])
    front = pts[0] + dirs[0] * 0.004
    frame_b = kit.block("belt_buckle", (0, 0, 0), (0.062, 0.007, 0.064), "brass", bevel=0.0022)
    kit.cut(frame_b, kit.block("buckle_hole", (0.007, 0.0, 0), (0.036, 0.03, 0.044), "steel", bevel=0))
    prong = kit.block("buckle_prong", (-0.006, -0.0045, 0), (0.046, 0.004, 0.005), "steel", bevel=0.001)
    o = kit.join([frame_b, prong], "belt_buckle")
    o.data.transform(Matrix.Translation(front + Vector((0, -0.002, 0))))
    c.rigid(o, "hips")

    def hang(th, drop, extra=0.012):
        """A frame on the belt at angle th (x along it, y out, z up), pushed out so a part hanging
        `drop` below clears what is under it."""
        i = int(round(th / 360 * n)) % n
        d = dirs[i]
        r0 = (Vector((pts[i].x, pts[i].y - yc, 0))).length + 0.004
        need = 0.0
        for j in range(1, 8):
            z = zb - drop * j / 7
            loc, _ = outermost(trees, (0, yc, z), d)
            if loc is not None:
                need = max(need, (Vector((loc.x, loc.y - yc, 0))).length + 0.022 - r0)
        x = Vector((0, 0, 1)).cross(d).normalized()
        return Vector((0, yc, zb)) + d * r0, -x, d, Vector((0, 0, 1)), need + extra

    # Hammer on the right hip, hanging through a leather loop, head forward.
    o, x, y, z, push = hang(-112 % 360, 0.24)
    parts_h = [kit.block("hammer_loop", (0, 0.004, -0.014), (0.034, 0.008, 0.056), "leather", bevel=0.002),
               kit.ring("hammer_ring", (0, push + 0.006, -0.036), (0, 0, 1), 0.019, 0.0135, 0.022, "leather", segs=20),
               kit.cyl("hammer_handle", (0, push + 0.006, 0.03), (0, push + 0.012, -0.22), 0.0118, "scrap_ash", r1=0.0105, segs=12, bevel=0.0015),
               kit.cyl("hammer_face", (-0.062, push + 0.006, 0.046), (-0.02, push + 0.006, 0.046), 0.0135, "bright", segs=16, bevel=0.0018),
               kit.block("hammer_eye", (0.0, push + 0.006, 0.046), (0.042, 0.024, 0.026), "steel", bevel=0.002),
               kit.cyl("hammer_peen", (0.02, push + 0.006, 0.046), (0.07, push + 0.006, 0.046), 0.0115, "steel", r1=0.0035, segs=16, bevel=0.001)]
    c.rigid(onto(kit.join(parts_h, "hammer"), o, x, y, z), "hips")

    # Tool pouch on the left hip: two screwdrivers and a spanner standing in it.
    o, x, y, z, push = hang(100, 0.14)
    pouch = kit.block("tool_pouch", (0, push + 0.02, -0.072), (0.09, 0.036, 0.11), "leather", bevel=0.006)
    kit.cut(pouch, kit.block("pouch_mouth", (0, push + 0.02, -0.014), (0.078, 0.026, 0.02), "steel", bevel=0))
    tools = [pouch, kit.block("pouch_strap", (0, 0.005, -0.012), (0.036, 0.01, 0.062), "leather", bevel=0.002),
             kit.block("pouch_welt", (0, push + 0.039, -0.072), (0.076, 0.004, 0.092), "leather", bevel=0.0015)]
    for xx in (0.012, 0.031):
        tools.append(kit.cyl("driver", (xx, push + 0.02, -0.03), (xx, push + 0.021, 0.042), 0.0098, "scrap_ash", segs=8, bevel=0.0015))
        tools.append(kit.ring("ferrule", (xx, push + 0.02, -0.024), (0, 0, 1), 0.0105, 0.006, 0.008, "brass", segs=12))
    tools.append(kit.block("spanner", (-0.02, push + 0.02, 0.0), (0.014, 0.0045, 0.11), "steel", bevel=0.0012))
    jaw = kit.cyl("spanner_head", (-0.02, push + 0.0175, 0.062), (-0.02, push + 0.0225, 0.062), 0.0175, "steel", segs=20, bevel=0.0008)
    kit.cut(jaw, kit.block("jaw", (-0.02, push + 0.02, 0.074), (0.0125, 0.03, 0.03), "steel", bevel=0))
    tools.append(jaw)
    tools.append(rivets("pouch_rivets", [(Vector((xx, push + 0.0385, -0.03)), Vector((0, 1, 0))) for xx in (-0.034, 0.034)], r=0.0035, material="brass"))
    c.rigid(onto(kit.join(tools, "tool_pouch"), o, x, y, z), "hips")

    # Oil can behind the left hip, spout up.
    o, x, y, z, push = hang(146, 0.16)
    can = [kit.block("can_loop", (0, 0.004, -0.022), (0.03, 0.008, 0.064), "leather", bevel=0.002),
           kit.cyl("oil_can", (0, push + 0.036, -0.155), (0, push + 0.036, -0.095), 0.034, "brass", segs=18, bevel=0.002),
           kit.cyl("can_shoulder", (0, push + 0.036, -0.095), (0, push + 0.036, -0.066), 0.034, "brass", r1=0.011, segs=18, bevel=0.0012),
           kit.ring("can_rim", (0, push + 0.036, -0.153), (0, 0, 1), 0.0355, 0.03, 0.006, "scrap_copper", segs=18),
           kit.cyl("can_neck", (0, push + 0.036, -0.068), (0, push + 0.036, -0.054), 0.0095, "scrap_copper", segs=12, bevel=0.001),
           kit.cyl("can_spout", (0, push + 0.036, -0.056), (0.012, push + 0.06, 0.07), 0.0035, "scrap_copper", r1=0.0016, segs=10, bevel=0),
           kit.cyl("can_pump", (0.03, push + 0.036, -0.105), (0.045, push + 0.036, -0.103), 0.009, "steel", segs=12, bevel=0.001),
           kit.ring("can_strap", (0, push + 0.036, -0.08), (0, 0, 1), 0.024, 0.017, 0.014, "leather", segs=20)]
    c.rigid(onto(kit.join(can, "oil_can"), o, x, y, z), "hips")

    # Tool roll: waxed cloth rolled round the tools, strapped under the belt across the small of the back.
    o, x, y, z, push = hang(180, 0.1, 0.004)
    L, R = 0.30, 0.036
    ctr = Vector((0.015, push + R, -0.03 - R))
    rings = []
    for i in range(13):
        t = i / 12
        xx = -L / 2 + L * t
        bul = 1.0 + 0.06 * math.sin(math.pi * t) - 0.03 * (abs(2 * t - 1) > 0.9)
        rings.append([ctr + Vector((xx, R * bul * math.cos(2 * math.pi * k / 18) * (1 + 0.04 * math.sin(3 * k)),
                                    R * bul * math.sin(2 * math.pi * k / 18))) for k in range(18)])
    roll = loft("tool_roll", rings, "waxed.scrap_wax")
    roll["texel"] = 1.0
    bits = [kit.cyl("roll_end", ctr + Vector((L / 2 - 0.002, 0, 0)), ctr + Vector((L / 2 + 0.004, 0, 0)), R * 0.82, "scrap_wax", segs=18, bevel=0.002),
            kit.ring("roll_layer", ctr + Vector((L / 2 + 0.003, 0, 0)), (1, 0, 0), R * 0.55, R * 0.47, 0.004, "scrap_wax", segs=16),
            kit.cyl("roll_end", ctr - Vector((L / 2 - 0.002, 0, 0)), ctr - Vector((L / 2 + 0.003, 0, 0)), R * 0.9, "scrap_wax", segs=18, bevel=0.002)]
    for k, (dy, dz, mat_, r_) in enumerate(((0.012, 0.01, "scrap_ash", 0.0075), (-0.01, 0.014, "scrap_ash", 0.0065), (0.004, -0.012, "steel", 0.0045))):
        p0 = ctr + Vector((-L / 2 + 0.02, dy, dz))
        p1 = ctr + Vector((-L / 2 - 0.045 - 0.012 * k, dy * 1.2, dz * 1.2))
        bits.append(kit.cyl("roll_tool", p0, p1, r_, mat_, segs=10, bevel=0.0012))
    bits.append(kit.block("wrench_end", ctr + Vector((-L / 2 - 0.05, 0.004, -0.012)), (0.012, 0.022, 0.006), "steel", bevel=0.0012))
    for xx in (-0.085, 0.09):
        strap = [ctr + Vector((xx, (R + 0.003) * math.cos(a), (R + 0.003) * math.sin(a))) for a in [2 * math.pi * k / 20 for k in range(20)]]
        bits.append(remat(pmc.sweep("roll_strap", strap, 0.02, 0.003, "accent", pmc.radial(ctr, (1, 0, 0)), closed=True), "leather.accent"))
        bits.append(kit.block("roll_hanger", Vector((xx + 0.015, 0.004 + push / 2, -0.012 - R * 0.3)), (0.022, push + 0.006, 0.05), "leather", bevel=0.0015))
        bits.append(buckle("roll_buckle", ctr + Vector((xx, R + 0.006, -0.008)), (0, 0, 1), (0, 1, 0), 0.022))
    for p_ in bits + [roll]:
        onto(p_, o, x, y, z)
        c.rigid(p_, "hips")


def wrist_gauge(c, b, tj):
    """A brass pressure gauge on a riveted leather cuff, strapped over the left jacket sleeve."""
    f0, f1 = b.j("forearm.L", 0.0), b.j("forearm.L", 1.0)
    ax = (f1 - f0).normalized()
    wc = f0.lerp(f1, 0.70)
    r = pmc._radius(tj, wc, ax)
    cuff = pmc.wrap("gauge_cuff", wc - ax * 0.024, wc + ax * 0.024, r + 0.004, r + 0.004, -180, 180, 0.005, "leather", nt=2, nphi=24,
                    bevel=0.0015, fit=(tj, 0.002))
    c.rigid(cuff, "forearm.L")
    out = (Vector((1, 0, 0.25)) - ax * Vector((1, 0, 0.25)).dot(ax)).normalized()
    loc, nor = pmc.hit(tj, wc + out * 0.2, -out)
    gb = (loc if loc is not None else wc + out * r) + out * 0.0075
    e1 = -ax
    g = gauge(gb, out, e1, r=0.0225, depth=0.012, needle=40)
    g += [kit.cyl("gauge_stem", gb + e1 * 0.021, gb + e1 * 0.029, 0.0045, "brass", segs=12, bevel=0.0005),
          kit.cyl("gauge_nut", gb + e1 * 0.028, gb + e1 * 0.036, 0.0062, "brass", segs=6, bevel=0.0005),
          kit.cyl("gauge_pipe", gb + e1 * 0.035 - out * 0.003, gb + e1 * 0.08 - out * 0.005, 0.0028, "scrap_copper", segs=10, bevel=0),
          kit.cyl("gauge_union", gb + e1 * 0.078 - out * 0.005, gb + e1 * 0.088 - out * 0.005, 0.0052, "brass", segs=6, bevel=0.0005)]
    c.rigid(kit.join(g, "wrist_gauge"), "forearm.L")
    spots = []
    for k in range(10):
        a = 2 * math.pi * k / 10
        d = (out * math.cos(a) + out.cross(ax) * math.sin(a)).normalized()
        if math.cos(a) > 0.3:
            continue
        q, _ = pmc.hit(pmc.tree(cuff), wc + d * 0.2, -d)
        if q is not None:
            spots.append((q, d))
    if spots:
        c.rigid(rivets("cuff_rivets", spots, r=0.0028, material="brass"), "forearm.L")


SPEC = {"build": build, "faction": "scrappers", "budget": (25000, 80000), "loadout": "shotgun",
        "colors": {"primary": "#6e6450", "secondary": "#3d3a33", "accent": "#9a6a35"}}
