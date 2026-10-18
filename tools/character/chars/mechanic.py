"""Mechanic, Scrappers: a Luddite fixer. Welding goggles pushed up on the forehead (brass-rimmed round
lenses on a leather strap), a heavy split-leg leather apron with a hand-painted cog over a rolled-sleeve
work shirt and suspenders, a tool belt with a hammer, wrenches and screwdrivers, an oil can and a rag,
a brass pressure gauge strapped to the left wrist, suede welding gloves, steel-capped boots.

Tints: primary = shirt, secondary = trousers, accent = suspenders and apron straps.

The first part of this file holds placement helpers the other Scrappers (bruiser, trapper) import: ray
casts against the body so gear sits on the skin, straps draped over it, conforming bands, parametric
sheets (aprons, coat panels), rivet and stitch rows, custom skin weights.
"""

import math

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
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r, radius2=r * 0.5, depth=h, matrix=m)
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


# ---------------------------------------------------------------------------------------- the mechanic

def build():
    b = kit.Build(height=1.75, width=1.0, bulk=1.0)
    c = kit.begin("mechanic", b)
    k = b.k
    parts = kit.body(b, skin="skin", gut=0.3, head=False)
    head = kit.head_mesh(b, "skin", jaw=1.05, brow=1.15, nose=1.08)
    flesh = c.flesh(parts["body"])
    c.add(head, kit.HEAD_BONES)
    hc = b.j("head", 0.45)
    hip = b.hip_z
    body = Probe(flesh, skip=ARMS)

    # ---------------------------------------------------------------- head: hair, brows, moustache
    # Cropped hair: a thin cap trimmed by a side-view hairline (forehead, over the ears, down to the nape).
    line = kit.rounded([(-0.2, hc.z + 0.056 * k), (-0.058 * k, hc.z + 0.05 * k), (-0.037 * k, hc.z + 0.03 * k), (-0.036 * k, hc.z - 0.032 * k),
                        (-0.017 * k, hc.z - 0.032 * k), (-0.014 * k, hc.z + 0.026 * k), (0.03 * k, hc.z + 0.031 * k),
                        (0.06 * k, hc.z - 0.01 * k), (0.11 * k, hc.z - 0.062 * k), (0.2, hc.z - 0.09 * k), (0.2, hc.z + 0.3), (-0.2, hc.z + 0.3)], 0.008)
    face = Probe(head)

    def volume(p):
        top = smoothstep(hc.z + 0.02 * k, hc.z + 0.1 * k, p.z)
        quiff = smoothstep(-0.02, -0.075 * k, p.y) * smoothstep(hc.z + 0.035 * k, hc.z + 0.08 * k, p.z)
        return 0.011 * top + 0.007 * quiff
    hair = hair_cap(head, hc, k, line, volume, material="scrap_hair")
    c.rigid(hair, "head")
    # Combed-back ridges from a side parting on the left.
    ridges = []
    for gx, sweep in ((0.046, 0.006), (0.022, -0.004), (0.006, -0.008), (-0.01, -0.01), (-0.026, -0.012), (-0.042, -0.012)):
        pts = []
        for t in range(9):
            y = (-0.05 + 0.017 * t) * k
            x = (gx + sweep * t / 8) * k
            h = face.hit(Vector((x, y, hc.z)), (x * 3, 0, 1), 0.3)
            if h:
                pts.append(h[0] + h[1] * (0.0015 + volume(h[0]) + 0.0072))
        if len(pts) > 3:
            ridges.append(tube_path("comb_ridge", pts, 0.0032, "scrap_hair", segs=6, closed=False, taper=True))
    c.rigid(kit.join(ridges, "comb_ridges"), "head")
    for sx in (1, -1):
        pts = []
        for x, dz in ((0.013, 0.021), (0.031, 0.027), (0.049, 0.02)):
            s = face.surf(hc + Vector((sx * x * k, 0, dz * k)), (0, -1, 0), 0.25)
            pts.append(s + Vector((0, -0.0015, 0.0)))
        c.rigid(kit.rope("brow", pts, 0.0036, "scrap_hair"), "head")
    els = []
    for sx in (1, -1):
        a = face.surf(hc + Vector((0, 0, -0.047 * k)), (0, -1, 0), 0.25) + Vector((0, -0.004, 0))
        m = face.surf(hc + Vector((sx * 0.017 * k, 0, -0.052 * k)), (0, -1, 0), 0.25) + Vector((0, -0.004, 0))
        e = face.surf(hc + Vector((sx * 0.03 * k, 0, -0.066 * k)), (sx * 0.5, -1, 0), 0.25) + Vector((sx * 0.002, -0.003, 0))
        els += [kit.capsule(a, m, 0.0068, r1=0.0058), kit.capsule(m, e, 0.0058, r1=0.0032)]
    c.rigid(kit.meta("moustache", els, "scrap_hair", res=0.0018, target=900, smooth_iter=2), "head")

    # ---------------------------------------------------------------- welding goggles on the forehead
    gear = Probe([head, hair])
    sc = hc + Vector((0, 0.01, 0.066 * k))
    s_axis = Vector((0, 0.34, 1))
    pts, dirs, a = contour(gear, sc, s_axis, 0.0012 + 0.002, n=36, reach=0.2)
    c.rigid(ribbon("goggle_strap", pts, dirs, [a] * len(pts), 0.021, 0.004, "leather", closed=True), "head")
    c.rigid(dashes("strap_stitch", [(p + d * 0.0021 + a * sw * 0.0085, d, pts[(i + 1) % len(pts)] - p)
                                    for i, (p, d) in enumerate(zip(pts, dirs)) for sw in (1, -1)],
                   length=0.004, width=0.0009, height=0.0006, material="cream", flat=True), "head")
    cups = []
    for sx in (1, -1):
        p, d = spot(gear, sc, s_axis, 31 * sx, 0.0045)
        n = (d + UP * 0.1).normalized()
        t1 = n.cross(UP).normalized()
        t2 = n.cross(t1).normalized()
        cup = kit.cyl("goggle_cup", p - n * 0.003, p + n * 0.016, 0.0205, "gunmetal", segs=20, bevel=0.0015)
        gasket = kit.cyl("gasket", p - n * 0.0055, p + n * 0.002, 0.0222, "leather", segs=20, bevel=0.002)
        lens = kit.cyl("lens", p + n * 0.012, p + n * 0.0188, 0.0168, "glass", segs=20, bevel=0.0004)
        bezel = kit.ring("bezel", p + n * 0.0185, n, 0.0236, 0.0163, 0.0055, "brass", segs=24)
        vent = kit.cyl("vent", p + n * 0.007 + t1 * sx * 0.019, p + n * 0.007 + t1 * sx * 0.0245, 0.0042, "brass", segs=12, bevel=0.0005)
        screws = rivets("bezel_screws", [(p + n * 0.0212 + (t1 * math.cos(q) + t2 * math.sin(q)) * 0.0199, n)
                                         for q in (0.4, 0.4 + math.pi / 2, 0.4 + math.pi, 0.4 + 1.5 * math.pi)], r=0.0017, material="steel")
        c.rigid(kit.join([cup, gasket, lens, bezel, vent, screws], "goggle"), "head")
        cups.append((p, n, t1))
    (pl, nl, _), (pr, nr, _) = cups
    mid_p, mid_d = spot(gear, sc, s_axis, 0, 0.009)
    bridge = kit.rope("goggle_bridge", [pl + nl * 0.008 + (pr - pl).normalized() * 0.019, mid_p, pr + nr * 0.008 + (pl - pr).normalized() * 0.019], 0.0028, "brass")
    c.rigid(bridge, "head")
    bp, bd = spot(gear, sc, s_axis, 180, 0.004)
    buckle = kit.block("strap_buckle", (0, 0.0, 0), (0.024, 0.004, 0.026), "brass", bevel=0.001)
    kit.cut(buckle, kit.block("buckle_hole", (0, 0, 0), (0.016, 0.02, 0.016), "steel", bevel=0))
    c.rigid(onto(buckle, *local(bp, bd, a)), "head")

    # ---------------------------------------------------------------- suede welding gloves
    hands = parts["hands"]
    hands.data.materials[0] = kit.mat("scrap_suede")
    c.add(hands, kit.HAND_BONES)

    # ---------------------------------------------------------------- work shirt with rolled sleeves
    lim = 0.058 * k * b.bulk + 0.004

    def on_forearm(p, t0):
        for s in ("L", "R"):
            t, d = along(b, "forearm." + s, p)
            if t > t0 and d < lim:
                return True
        return False
    neck_top = b.j("neck", 0.35).z
    sleeve_cuts = []
    for s in ("L", "R"):
        f0, f1 = b.j("forearm." + s, 0.31), b.j("forearm." + s, 1.3)
        sleeve_cuts.append(kit.cyl("sleeve_cut", f0, f1, 0.058 * k, "steel", segs=24, bevel=0))
    shirt = kit.shell(flesh, lambda p: hip - 0.06 < p.z < neck_top and not on_forearm(p, 0.45), "shirt", "primary",
                      offset=0.011, thick=0.004, smooth_iter=2, bones=TORSO | UPPER_ARMS | FOREARMS | THIGHS | {"neck"}, outside=sleeve_cuts)
    c.add(shirt)
    c.cover(TORSO | UPPER_ARMS, lambda p: p.z > hip - 0.03)
    c.cover(FOREARMS, lambda p: not on_forearm(p, 0.24))
    neck = Probe(flesh, only={"neck", "chest"})
    c.add(wrap("collar", neck, b.j("neck", 0.27), Vector((0, 0.12, 1)), 0.042, 0.006, "primary", gap=0.016, n=28))
    # Neckerchief knotted at the throat.
    nk = b.j("neck", 0.55)
    c.add(wrap("neckerchief", neck, nk, Vector((0, 0.18, 1)), 0.028, 0.007, "scrap_kerchief", gap=0.004, n=24), kit.HEAD_BONES)
    kp, kd = spot(neck, nk, Vector((0, 0.18, 1)), 38, 0.011)
    c.add(kit.meta("kerchief_knot", [kit.ellipsoid(kp, 0.0085, (1.2, 0.9, 1.0))], "scrap_kerchief", res=0.002, target=300), kit.HEAD_BONES)
    side = Vector((kd.y, -kd.x, 0)).normalized()
    for i, sw in enumerate((1, -1)):
        tail = [kp + side * sw * 0.004 + Vector((0, 0, -0.004)), kp + kd * 0.004 + side * sw * 0.012 + Vector((0, 0, -0.03)), kp + kd * 0.006 + side * sw * (0.016 + 0.006 * i) + Vector((0, 0, -0.05 - 0.01 * i))]
        c.add(ribbon("kerchief_tail", tail, [kd] * 3, [side] * 3, 0.018, 0.0035, "scrap_kerchief"), ["neck", "chest"])
    for s in ("L", "R"):
        fa = Probe(flesh, only={"forearm." + s})
        ax = b.j("forearm." + s, 1.0) - b.j("forearm." + s, 0.0)
        for t, g in ((0.305, 0.0215), (0.345, 0.019)):
            pts, dirs, _ = contour(fa, b.j("forearm." + s, t), ax, g, n=20, reach=0.2)
            c.add(tube_path("rolled_sleeve", pts, 0.0072, "primary", segs=8), ["forearm." + s, "upper_arm." + s])
        # Glove gauntlet cuffs.
        c.rigid(wrap("glove_cuff", fa, b.j("forearm." + s, 0.93), ax, 0.045, 0.006, "scrap_suede", gap=0.004, n=20), "forearm." + s)
        c.rigid(wrap("glove_cuff_hem", fa, b.j("forearm." + s, 0.885), ax, 0.008, 0.004, "leather", gap=0.0095, n=20), "forearm." + s)

    # ---------------------------------------------------------------- suspenders (accent), crossed at the back
    sus_gap = 0.018
    for sx in (1, -1):
        g = [(sx * 0.068, -0.09, hip + 0.06), (sx * 0.07, -0.095, 1.18 * k), (sx * 0.074, -0.07, 1.33 * k), (sx * 0.078, 0.0, 1.41 * k),
             (sx * 0.072, 0.07, 1.34 * k), (sx * 0.035, 0.095, 1.18 * k), (-sx * 0.045, 0.1, 1.06 * k), (-sx * 0.075, 0.105, hip + 0.08)]
        st, pts, ns = strap_over("suspender", body, g, sus_gap + (0.0045 if sx < 0 else 0.0), 0.034, 0.004, "accent")
        c.add(st, SPINE)
        end, en = pts[-1], ns[-1]
        clip = kit.block("suspender_clip", (0, 0, 0), (0.04, 0.006, 0.026), "brass", bevel=0.0012)
        c.add(onto(clip, *local(end + en * 0.004 + Vector((0, 0, -0.004)), en)), SPINE)

    # ---------------------------------------------------------------- heavy leather apron: bib + split legs
    # Stiff leather hung from the chest: every apron piece sits on one hanging surface, so the pocket,
    # the paint, the rivets and the stitching follow it exactly.
    w = b.width
    T = 0.007  # leather thickness
    zt, zb = b.j("chest", 0.68).z, hip + 0.012
    fz0, fz1 = hip + 0.055, b.j("lower_leg.L", 0.04).z
    field = hang_field(body, -0.24 * w, 0.24 * w, 48, zt + 0.02, fz1 - 0.01, 50)
    front = Vector((0, -1, 0))

    def bib_pt(x, z, off=0.0):
        core = max(field(xx * w, z) for xx in (-0.06, -0.03, 0.0, 0.03, 0.06))
        g = 0.021 + 0.01 * smoothstep(zt, zt - 0.12, z)
        return Vector((x, -(max(core - 1.8 * x * x, field(x, z)) + g + off), z))
    bib_line = kit.rounded([(-0.098 * w, zt), (0.098 * w, zt), (0.15 * w, (zt + zb) * 0.5 + 0.02), (0.168 * w, zb), (-0.168 * w, zb),
                            (-0.15 * w, (zt + zb) * 0.5 + 0.02)], 0.022)
    c.add(panel("apron_bib", bib_pt, -0.19 * w, 0.19 * w, zb - 0.01, zt + 0.015, bib_line, 0.0, T, "leather", nu=24, nv=24, bevel=0.0025), SPINE)
    # Bib pocket with a pencil and a screwdriver, a painted cog.
    px, pz = -0.058 * w, zt - 0.085
    pocket_line = kit.rounded([(px - 0.048, pz - 0.05), (px + 0.048, pz - 0.05), (px + 0.048, pz + 0.035), (px - 0.048, pz + 0.035)], 0.012)
    c.add(panel("bib_pocket", bib_pt, px - 0.055, px + 0.055, pz - 0.06, pz + 0.045, pocket_line, T + 0.0003, 0.006, "leather", nu=8, nv=8), SPINE)
    pin_at = bib_pt(px, pz + 0.035, T + 0.003)
    pencil = kit.join([kit.cyl("pencil", pin_at + Vector((0.016, 0.0, -0.03)), pin_at + Vector((0.02, -0.002, 0.05)), 0.0042, "yellow", segs=6, bevel=0.0004),
                       kit.cyl("pencil_tip", pin_at + Vector((0.02, -0.002, 0.05)), pin_at + Vector((0.0205, -0.0022, 0.062)), 0.0042, "kraft", r1=0.0008, segs=6, bevel=0)], "pencil")
    driver = kit.join([kit.cyl("driver_handle", pin_at + Vector((-0.016, 0.0, 0.0)), pin_at + Vector((-0.019, -0.001, 0.06)), 0.0085, "red", segs=8, bevel=0.0012),
                       kit.ring("driver_ferrule", pin_at + Vector((-0.016, 0.0, 0.002)), (0.04, 0.0, -1), 0.009, 0.006, 0.006, "steel", segs=12)], "screwdriver")
    c.add(pencil, SPINE)
    c.add(driver, SPINE)
    cx, cz = 0.052 * w, zt - 0.11
    c.add(panel("bib_cog", bib_pt, cx - 0.05, cx + 0.05, cz - 0.05, cz + 0.05, cog(cx, cz, 0.04), T + 0.0003, 0.0012, "yellow", bevel=0.0, hole=(cx, cz, 0.0145)), SPINE)

    def normal(pt, x, z):
        e = 0.003
        n = (pt(x + e, z) - pt(x - e, z)).cross(pt(x, z + e) - pt(x, z - e)).normalized()
        return -n if n.y > 0 else n
    spots = [(bib_pt(x, z, T), normal(bib_pt, x, z)) for x, z in ((0.084 * w, zt - 0.014), (-0.084 * w, zt - 0.014), (0.148 * w, zb + 0.014), (-0.148 * w, zb + 0.014))]
    spots += [(bib_pt(x, pz + 0.025, T + 0.0063), front) for x in (px - 0.04, px + 0.04)]
    c.add(rivets("bib_rivets", spots, r=0.0042, material="brass"), SPINE)
    edge = kit.rounded([(-0.086 * w, zt - 0.012), (0.086 * w, zt - 0.012), (0.138 * w, (zt + zb) * 0.5 + 0.02), (0.155 * w, zb + 0.013),
                        (-0.155 * w, zb + 0.013), (-0.138 * w, (zt + zb) * 0.5 + 0.02)], 0.02)
    edge.append(edge[0])
    c.add(dashes("bib_stitch", seam([bib_pt(x, z, T) for x, z in edge], [normal(bib_pt, x, z) for x, z in edge], 0.012), material="cream", flat=True), SPINE)

    # Neck strap and waist ties (accent).
    nb = b.j("neck", 0.0)
    ng = [(0.088 * w, -0.11, zt - 0.006), (0.08 * w, -0.07, nb.z - 0.015), (0.07, -0.02, nb.z + 0.03), (0.045, 0.045, nb.z + 0.035), (0.0, 0.065, nb.z + 0.02),
          (-0.045, 0.045, nb.z + 0.035), (-0.07, -0.02, nb.z + 0.03), (-0.08 * w, -0.07, nb.z - 0.015), (-0.088 * w, -0.11, zt - 0.006)]
    st, _, _ = strap_over("apron_neck_strap", body, ng, 0.019, 0.026, 0.004, "accent")
    c.add(st)
    tz = b.j("spine", 0.15).z
    for sx in (1, -1):
        g = [(sx * 0.158 * w, -0.06, tz), (sx * 0.17 * w, 0.0, tz), (sx * 0.13, 0.075, tz), (sx * 0.05, 0.1, tz), (sx * 0.008, 0.105, tz)]
        st, _, _ = strap_over("apron_tie", body, g, 0.018, 0.018, 0.0035, "accent")
        c.add(st, SPINE)
    kh = body.hit(Vector((0, 0, tz)), (0, 1, 0))
    knot = kit.meta("apron_knot", [kit.ellipsoid(kh[0] + kh[1] * 0.03, 0.016, (1.2, 0.8, 0.8))], "accent", res=0.003, target=300)
    c.add(knot, SPINE)
    for sx in (1, -1):
        tail = [kh[0] + kh[1] * 0.032 + Vector((sx * 0.008, 0, -0.005)), kh[0] + kh[1] * 0.034 + Vector((sx * 0.02, 0, -0.06)), kh[0] + kh[1] * 0.036 + Vector((sx * 0.024, 0, -0.1))]
        st = ribbon("apron_tie_end", tail, [kh[1]] * 3, [Vector((1, 0, 0))] * 3, 0.017, 0.0035, "accent")
        c.add(st, ["spine", "hips"])

    # Split leg flaps hanging stiff in front of each thigh, strapped round the thigh; a cog on the left one.
    x0, x1 = 0.006 * w, 0.205 * w
    for s, sx in (("L", 1), ("R", -1)):
        thigh = "upper_leg." + s

        def flap_pt(x, z, off=0.0, sx=sx):
            xc = sx * (x0 + x1) / 2
            core = max(field(sx * (x0 + (x1 - x0) * i / 8), z) for i in range(9))
            v = (fz0 - z) / (fz0 - fz1)
            return Vector((x, -(max(core - 2.2 * (x - xc) ** 2, field(x, z)) + 0.042 + 0.012 * v + off), z))

        def wfn(p, thigh=thigh):
            t = smoothstep(fz0 - 0.03, fz0 - 0.17, p.z)
            return {"hips": 1 - t, thigh: t}
        outline = kit.rounded([(sx * (x0 - 0.01), fz0 + 0.01), (sx * (x1 + 0.01), fz0 + 0.01), (sx * x1, fz1), (sx * x0, fz1)], 0.045)
        lo, hi = sorted((sx * (x0 - 0.012), sx * (x1 + 0.012)))
        skin(c, panel("apron_flap", flap_pt, lo, hi, fz1 - 0.005, fz0 + 0.012, outline, 0.0, T, "leather", nu=12, nv=22, bevel=0.002), wfn)
        inset = kit.rounded([(sx * (x0 + 0.012), fz0 - 0.004), (sx * (x1 - 0.012), fz0 - 0.004), (sx * (x1 - 0.012), fz1 + 0.012), (sx * (x0 + 0.012), fz1 + 0.012)], 0.035)
        inset.append(inset[0])
        skin(c, dashes("flap_stitch", seam([flap_pt(x, z, T) for x, z in inset], [normal(flap_pt, x, z) for x, z in inset], 0.012), material="cream", flat=True), wfn)
        if sx > 0:
            gx, gz = sx * 0.108 * w, fz0 - 0.21
            skin(c, panel("flap_cog", flap_pt, gx - 0.06, gx + 0.06, gz - 0.06, gz + 0.06, cog(gx, gz, 0.052, teeth=10), T + 0.0003, 0.0012, "yellow",
                          nu=10, nv=10, bevel=0.0, hole=(gx, gz, 0.019)), wfn)
        # Thigh strap: from the flap's outer edge round the back of the thigh to its inner edge.
        tc = b.j(thigh, 0.42)
        th = Probe(flesh, only={thigh})
        pts = []
        for ang in range(70, 300, 10):
            a2 = math.radians(ang)
            d = Vector((sx * math.sin(a2), -math.cos(a2), 0))
            r = th.depth(tc, d, 0.3) or 0.07
            pts.append(tc + d * (r + 0.031))
        po = flap_pt(sx * (x1 - 0.004), tc.z, -0.002)
        pi = flap_pt(sx * (x0 + 0.004), tc.z, -0.002)
        path = [po] + pts + [pi]
        ns = [((p - tc) - UP * (p - tc).dot(UP)).normalized() for p in path]
        c.rigid(ribbon("thigh_strap", path, ns, [UP] * len(path), 0.024, 0.004, "accent"), thigh)
        bk = pts[len(pts) // 2 - 6]
        bn = (bk - tc).normalized()
        tbuckle = kit.block("thigh_buckle", (0, 0, 0), (0.026, 0.004, 0.032), "brass", bevel=0.001)
        kit.cut(tbuckle, kit.block("hole", (0, 0, 0), (0.018, 0.02, 0.022), "steel", bevel=0))
        c.rigid(onto(tbuckle, *local(bk + bn * 0.003, bn)), thigh)
        c.rigid(rivets("flap_rivets", [(flap_pt(sx * (x1 - 0.014), tc.z, T), front), (flap_pt(sx * (x0 + 0.014), tc.z, T), front)], r=0.0045, material="brass"), thigh)

    # ---------------------------------------------------------------- trousers and boots
    trousers = kit.shell(flesh, lambda p: 0.11 * k < p.z < hip + 0.085, "trousers", "secondary", offset=0.022, thick=0.004, smooth_iter=3,
                         bones=THIGHS | SHINS | {"hips", "spine"})
    c.add(trousers)
    c.cover(THIGHS | SHINS | {"hips"}, lambda p: 0.15 * k < p.z < hip + 0.07)
    for s in ("L", "R"):
        sh = Probe(flesh, only={"lower_leg." + s})
        ax = b.j("lower_leg." + s, 0.0) - b.j("lower_leg." + s, 1.0)
        for zz, g in ((0.16 * k, 0.03), (0.135 * k, 0.028)):
            cc = b.j("lower_leg." + s, 0.0).lerp(b.j("lower_leg." + s, 1.0), (b.j("lower_leg." + s, 0).z - zz) / (b.j("lower_leg." + s, 0).z - b.j("lower_leg." + s, 1).z))
            pts, dirs, _ = contour(sh, cc, ax, g, n=20, reach=0.2)
            c.add(tube_path("trouser_roll", pts, 0.0085, "secondary", segs=8), ["lower_leg." + s])
    boots(c, b, flesh, cap="steel")

    # ---------------------------------------------------------------- tool belt
    bz = hip + 0.045
    bc = Vector((0, 0, bz))

    def bgap(d):
        return 0.029 + 0.03 * smoothstep(0.25, 0.6, -d.y)
    c.add(wrap("tool_belt", body, bc, UP, 0.05, 0.009, "leather", gap=bgap, n=40, reach=0.45), ["hips", "spine"])
    belt_rivets = []
    for ang in range(0, 360, 20):
        if abs(((ang + 180) % 360) - 180) < 25:
            continue
        p, d = spot(body, bc, UP, ang, 0)
        g = bgap(d) + 0.009
        for dz in (0.016, -0.016):
            belt_rivets.append((p + d * g + Vector((0, 0, dz)), d))
    c.add(rivets("belt_rivets", belt_rivets, r=0.0032, material="brass"), ["hips", "spine"])
    p, d = spot(body, bc, UP, 0, 0)
    bp = p + d * (bgap(d) + 0.009)
    frame_b = kit.block("belt_buckle", (0, 0.003, 0), (0.06, 0.007, 0.062), "brass", bevel=0.002)
    kit.cut(frame_b, kit.block("buckle_hole", (0.006, 0.0, 0), (0.034, 0.03, 0.042), "steel", bevel=0))
    prong = kit.block("buckle_prong", (0.0, 0.006, 0), (0.044, 0.004, 0.005), "steel", bevel=0.001)
    c.rigid(onto(kit.join([frame_b, prong], "belt_buckle"), *local(bp, d)), "hips")

    def hang(ang, drop=0.14, extra=0.012):
        """Belt frame at angle `ang`: origin on the belt face, pushed out so a part hanging `drop` below
        clears the trousers."""
        p, d = spot(body, bc, UP, ang, 0)
        r0 = (p - bc).dot(d) + bgap(d) + 0.009
        need = 0.0
        for j in range(1, 8):
            z = bz - drop * j / 7
            dd = body.depth(Vector((0, 0, z)), d, 0.6) or 0.0
            need = max(need, dd + 0.028 - r0)
        o, x, y, zz = local(bc + d * r0, d)
        return o, x, y, zz, need + extra

    # Hammer on the right hip, hanging through a leather loop.
    o, x, y, z, push = hang(-118, 0.25)
    parts_h = [kit.block("hammer_loop", (0, 0.004, -0.012), (0.032, 0.008, 0.05), "leather", bevel=0.002),
               kit.ring("hammer_ring", (0, push + 0.006, -0.03), (0, 0, 1), 0.019, 0.0135, 0.022, "leather", segs=20),
               kit.cyl("hammer_handle", (0, push + 0.006, 0.03), (0, push + 0.012, -0.235), 0.0118, "scrap_ash", r1=0.0105, segs=12, bevel=0.0015),
               kit.cyl("hammer_grip", (0, push + 0.011, -0.15), (0, push + 0.012, -0.232), 0.0128, "leather", segs=12, bevel=0.0015),
               kit.cyl("hammer_face", (-0.062, push + 0.006, 0.046), (-0.02, push + 0.006, 0.046), 0.0135, "bright", segs=16, bevel=0.0018),
               kit.block("hammer_eye", (0.0, push + 0.006, 0.046), (0.042, 0.024, 0.026), "bright", bevel=0.002),
               kit.cyl("hammer_peen", (0.02, push + 0.006, 0.046), (0.07, push + 0.006, 0.046), 0.0115, "bright", r1=0.0035, segs=16, bevel=0.001),
               kit.cyl("hammer_wedge", (0, push + 0.006, 0.058), (0, push + 0.006, 0.0605), 0.0085, "scrap_ash", segs=10, bevel=0)]
    c.rigid(onto(kit.join(parts_h, "hammer"), o, x, y, z), "hips")

    # Tool pouch on the left hip: two screwdrivers and a spanner.
    o, x, y, z, push = hang(98, 0.13)
    pouch = kit.block("tool_pouch", (0, push + 0.02, -0.07), (0.088, 0.036, 0.11), "leather", bevel=0.006)
    kit.cut(pouch, kit.block("pouch_mouth", (0, push + 0.02, -0.014), (0.076, 0.026, 0.02), "steel", bevel=0))
    welt = kit.block("pouch_welt", (0, push + 0.039, -0.07), (0.074, 0.004, 0.09), "leather", bevel=0.0015)
    strap_p = kit.block("pouch_strap", (0, 0.005, -0.01), (0.034, 0.01, 0.06), "leather", bevel=0.002)
    tools = [pouch, welt, strap_p]
    for xx, mat in ((0.012, "red"), (0.031, "yellow")):
        tools.append(kit.cyl("driver", (xx, push + 0.02, -0.03), (xx, push + 0.021, 0.04), 0.0098, mat, segs=8, bevel=0.0015))
        tools.append(kit.ring("ferrule", (xx, push + 0.02, -0.026), (0, 0, 1), 0.0105, 0.006, 0.008, "steel", segs=12))
    sh = kit.block("spanner", (-0.02, push + 0.02, 0.0), (0.014, 0.0045, 0.11), "bright", bevel=0.0012)
    jaw = kit.cyl("spanner_head", (-0.02, push + 0.0175, 0.062), (-0.02, push + 0.0225, 0.062), 0.0175, "bright", segs=20, bevel=0.0008)
    kit.cut(jaw, kit.block("jaw", (-0.02, push + 0.02, 0.074), (0.0125, 0.03, 0.03), "steel", bevel=0))
    tools += [sh, jaw]
    sp = []
    for u in range(8):
        sp.append((Vector((-0.04 + u * 0.0114, push + 0.0385, -0.123)), Vector((0, 1, 0)), Vector((1, 0, 0))))
    for v in range(8):
        for xx in (-0.04, 0.04):
            sp.append((Vector((xx, push + 0.0385, -0.118 + v * 0.0118)), Vector((0, 1, 0)), Vector((0, 0, 1))))
    tools.append(dashes("pouch_stitch", sp, material="cream", flat=True))
    tools.append(rivets("pouch_rivets", [(Vector((xx, push + 0.0385, -0.025)), Vector((0, 1, 0))) for xx in (-0.034, 0.034)], r=0.0035, material="brass"))
    c.rigid(onto(kit.join(tools, "tool_pouch"), o, x, y, z), "hips")

    # Oil can at the back-left, spout up.
    o, x, y, z, push = hang(148, 0.15)
    can = [kit.block("can_loop", (0, 0.004, -0.02), (0.03, 0.008, 0.06), "leather", bevel=0.002),
           kit.cyl("oil_can", (0, push + 0.036, -0.15), (0, push + 0.036, -0.09), 0.034, "brass", segs=16, bevel=0.002),
           kit.cyl("can_shoulder", (0, push + 0.036, -0.09), (0, push + 0.036, -0.062), 0.034, "brass", r1=0.011, segs=16, bevel=0.0012),
           kit.ring("can_rim", (0, push + 0.036, -0.148), (0, 0, 1), 0.0355, 0.03, 0.006, "copper", segs=16),
           kit.ring("can_band", (0, push + 0.036, -0.105), (0, 0, 1), 0.0352, 0.03, 0.008, "copper", segs=16),
           kit.cyl("can_neck", (0, push + 0.036, -0.064), (0, push + 0.036, -0.05), 0.0095, "copper", segs=16, bevel=0.001),
           kit.cyl("can_spout", (0, push + 0.036, -0.052), (0.012, push + 0.06, 0.085), 0.0035, "copper", r1=0.0016, segs=10, bevel=0),
           kit.cyl("can_pump", (0.03, push + 0.036, -0.1), (0.045, push + 0.036, -0.098), 0.009, "steel", segs=12, bevel=0.001),
           kit.ring("can_strap", (0, push + 0.036, -0.075), (0, 0, 1), 0.024, 0.017, 0.014, "leather", segs=20)]
    c.rigid(onto(kit.join(can, "oil_can"), o, x, y, z), "hips")
    can_label = kit.ring("can_paint", (0, 0, 0), (0, 0, 1), 0.0356, 0.034, 0.018, "red", segs=16)
    c.rigid(onto(can_label, o + y * (push + 0.036) + z * (-0.125), x, y, z), "hips")

    # Shop rag tucked in at the back-right.
    o, x, y, z, push = hang(-150, 0.17, 0.004)

    def rag_fn(u, v):
        return Vector(((u - 0.5) * 0.085 * (1 + 0.35 * v), push + 0.004 + 0.006 * math.sin(u * 3 * math.pi + v * 2) + 0.012 * v, 0.02 - 0.18 * v))
    rag = sheet("rag", rag_fn, 10, 10, 0.003, "red", lambda p: Vector((0, 1, 0)))
    c.rigid(onto(rag, o, x, y, z), "hips")

    # ---------------------------------------------------------------- brass pressure gauge, left wrist
    fa = Probe(flesh, only={"forearm.L"})
    f0, f1 = b.j("forearm.L", 0.0), b.j("forearm.L", 1.0)
    ax = (f1 - f0).normalized()
    out = (Vector((1, 0, 0.0)) - ax * ax.x).normalized()
    wc = f0.lerp(f1, 0.7)
    c.rigid(wrap("gauge_cuff", fa, wc, ax, 0.05, 0.008, "leather", gap=0.003, n=24), "forearm.L")
    c.rigid(wrap("gauge_cuff_strap", fa, wc + ax * 0.0, ax, 0.018, 0.004, "leather", gap=0.0115, n=24), "forearm.L")
    gb = fa.surf(wc, out, 0.2) + out * 0.0105
    e1 = -ax
    g = gauge(gb, out, e1, r=0.0235, depth=0.013) + [
        kit.cyl("gauge_stem", gb + e1 * 0.022, gb + e1 * 0.03, 0.0045, "brass", segs=12, bevel=0.0005),
        kit.cyl("gauge_nut", gb + e1 * 0.029, gb + e1 * 0.037, 0.0062, "brass", segs=6, bevel=0.0005),
        kit.cyl("gauge_pipe", gb + e1 * 0.036 - out * 0.003, gb + e1 * 0.085 - out * 0.004, 0.003, "copper", segs=10, bevel=0),
        kit.cyl("gauge_union", gb + e1 * 0.083 - out * 0.004, gb + e1 * 0.093 - out * 0.004, 0.0055, "brass", segs=6, bevel=0.0005)]
    c.rigid(kit.join(g, "wrist_gauge"), "forearm.L")
    return c


SPEC = {"build": build, "faction": "scrappers", "budget": (25000, 75000), "loadout": "shotgun",
        "colors": {"primary": "#6e6450", "secondary": "#3d3a33", "accent": "#9a6a35"}}
