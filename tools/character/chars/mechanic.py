"""Mechanic, Scrappers: a Luddite homesteader who keeps the settlement's machines running, dressed for
the forge and armoured by it. Over the face a riveted steel welding mask, flipped down on brass pivots:
a slit of dark glass in a brass holder, a chin plate with a brass breather, the Scrappers' cog painted
on the brow; under it an oiled-leather hood. Hand-beaten riveted steel over the workwear: a breastplate
(two sheets riveted down a centre strap, a scrap patch over a hole), a pauldron on the left shoulder and
forearm guards, the edges rolled, worn on tan straps with brass buckles, a pressure gauge on the left
guard. Under it a waxed-canvas chore jacket with a corduroy collar and leather elbow patches, a
split-leg leather welding apron with a hand-painted cog, and patched duck trousers with turn-ups; a
tool belt with a hammer, an adjustable wrench in a tool pouch, a spanner pouch, an oil can and a waxed
tool roll; suede work gloves and worn leather work boots. Nothing electric: leather, brass, riveted
steel, waxed cloth and paint.

Built on the realistic layer (real.py), like the Contractor and the Acolyte: a real body, gloved fists
closed round the grips, jacket, apron and trousers cut from the body and draped by the cloth
simulation, hard plates laid on envelopes of what they cover (the Acolyte's Env / Tube / Plate) and
baked with their painted marks, procedural surfaces (this module's own: hammered steel, waxed canvas,
cotton duck, corduroy, oiled leather, brushed paint, ash wood) baked into a 2048 atlas.

Tints: primary = jacket (and the knee patches cut from the same cloth), secondary = trousers, accent =
the tan straps (plate harness, mask crown strap, apron, guards, tool roll). The steel, brass, collar,
hood and other leathers are fixed colours.

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
from chars import acolyte as aco  # noqa: E402  (envelopes that hard plates are laid on, the armour bake)

kit.hs.PALETTE.setdefault("scrap_boot", ((0.16, 0.095, 0.05), (0.40, 0.29, 0.19), 0.0, 0.6, 0.65, 0))      # oiled work-boot leather
kit.hs.PALETTE.setdefault("scrap_lace", ((0.36, 0.24, 0.13), (0.50, 0.38, 0.25), 0.0, 0.75, 0.3, 0))       # rawhide laces
kit.hs.PALETTE.setdefault("scrap_lens", ((0.006, 0.026, 0.016), (0.006, 0.026, 0.016), 0.0, 0.05, 0.0, 0))  # shade-5 welding glass
kit.hs.PALETTE.setdefault("scrap_paint", ((0.80, 0.57, 0.12), (0.20, 0.12, 0.065), 0.0, 0.5, 0.7, 0))      # yellow enamel, chipped to leather
kit.hs.PALETTE.setdefault("scrap_copper", ((0.56, 0.30, 0.17), (0.80, 0.52, 0.36), 1.0, 0.38, 0.4, 0))
kit.hs.PALETTE.setdefault("scrap_cord", ((0.15, 0.085, 0.045), (0.30, 0.20, 0.12), 0.0, 0.85, 0.35, 0))      # brown corduroy
kit.hs.PALETTE.setdefault("scrap_cap", ((0.115, 0.068, 0.038), (0.27, 0.18, 0.11), 0.0, 0.62, 0.35, 0))   # oiled cap leather, dark with handling
kit.hs.PALETTE.setdefault("scrap_hood", ((0.046, 0.036, 0.029), (0.16, 0.115, 0.08), 0.0, 0.6, 0.4, 0))   # welder's hood, near-black oiled leather
kit.hs.PALETTE.setdefault("scrap_plate", ((0.045, 0.043, 0.04), (0.46, 0.44, 0.41), 0.85, 0.46, 0.9, 0))  # blackened sheet steel, worn bright
kit.hs.PALETTE.setdefault("scrap_wax", ((0.21, 0.18, 0.11), (0.36, 0.31, 0.20), 0.0, 0.5, 0.45, 0))         # brown waxed cotton

# This character's kinds -> surface recipes (all prefixed, so no other character's materials change).
for _k, _s in (("scrap_suede", "leather"), ("scrap_boot", "leather"), ("scrap_cap", "oiled"), ("scrap_hood", "oiled"), ("scrap_lace", "leather"), ("scrap_lens", "glass"),
               ("scrap_paint", "paint"), ("scrap_hair", "hair"), ("scrap_kerchief", "canvas"), ("scrap_ash", "wood"),
               ("scrap_copper", "metal"), ("scrap_wax", "waxed"), ("scrap_cord", "corduroy"), ("scrap_plate", "hammered")):
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


def _hammered(g, pal):
    """Hand-beaten sheet steel: blackened mill scale over the whole sheet, the peen marks of the hammer
    (two or three centimetres across) in its relief, catching the light as the plate turns, the scale
    flaked off in patches to grey steel, rust blooming here and there (the edge chips, worn bright,
    and the cavity dirt come from the shared wear)."""
    base = pal[0]
    pos = g.geo("Position")
    d1 = g.voronoi(pos, 40.0, "F1")
    d2 = g.voronoi(g.vec("ADD", pos, (0.31, 0.17, 0.53)), 70.0, "F1")
    dent = g.math("MINIMUM", g.remap(d1, 0.0, 0.55), g.remap(d2, 0.0, 0.5))  # 0 in a blow's hollow, 1 on the ridges
    mottle = g.remap(g.noise(pos, 5.0, detail=3), 0.3, 0.7, 0.8, 1.2, smooth=False)
    col = g.mix(1.0, base, g.rgb(mottle, mottle, mottle), "MULTIPLY")
    flake = g.remap(g.noise(g.vec("ADD", pos, (2.1, 0.4, 1.7)), 11.0, detail=5, rough=0.62), 0.57, 0.66)
    col = g.mix(g.mul(flake, 0.7), col, surfaces._scale(base, 2.8))
    rust = g.remap(g.noise(g.vec("ADD", pos, (1.3, 0.7, 2.1)), 7.0, detail=5, distort=0.3), 0.66, 0.74)
    col = g.mix(g.mul(rust, 0.75), col, (0.19, 0.075, 0.03))
    h = g.add(g.mul(dent, 0.7), g.mul(rust, 0.15))
    rough = g.lerp(rust, g.lerp(flake, 0.58, 0.4), 0.85)
    metal = g.lerp(rust, g.lerp(flake, 0.7, 0.9), 0.15)
    return dict(color=col, rough=rough, metal=metal, height=h, bump=0.0008)


surfaces.RECIPES.setdefault("hammered", _hammered)
surfaces.RECIPES.setdefault("waxed", _waxed)
surfaces.RECIPES.setdefault("oiled", _oiled)
surfaces.RECIPES.setdefault("corduroy", _corduroy)
surfaces.RECIPES.setdefault("paint", _paint)
surfaces.RECIPES.setdefault("wood", _wood)
surfaces.RECIPES.setdefault("duck", _duck)
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


def hold(c, obj, src, frac, bone="chest"):
    """Skin a hard-kit strap: wholly to `bone` (where it is fixed to a plate), blended by frac(p) toward
    the weights of the garment `src` it lies on."""
    kit.hs.apply_modifiers(obj)
    obj.vertex_groups.clear()
    obj.vertex_groups.new(name=bone).add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    weights_from(obj, src, frac)
    c.parts.append((obj, "DONE", None))
    return obj


def torso_only(obj):
    """A copy of a skinned garment without the faces its arms lead: a source of weights for parts on
    the body of a jacket, not its sleeves."""
    o = obj.copy()
    o.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(o)
    dom = kit.dominant(o)
    arms = set(kit.ARM_BONES)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if sum(dom[v.index] in arms for v in f.verts) * 2 >= len(f.verts)], context="FACES")
    bm.to_mesh(o.data)
    bm.free()
    return o


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


# ---------------------------------------------------------------------------------- the build

def build():
    b = real.Anatomy(height=1.78, body="male", sole=0.034)
    c = real.begin("mechanic", b)
    man = real.body(c, stubble=0.0, face_detail=1.0)
    J, seg, sm = b.j, kit.seg_dist, real._smooth
    lead = real.bones_at(man)
    hc = man.head_center()
    tb = pmc.tree(man.low)
    armpit, crotch = b.at("armpit"), b.at("crotch")
    LIMBS = UPPER_ARMS | FOREARMS
    LEGS = THIGHS | SHINS

    def on_arm(p):
        return lead(p) in LIMBS

    # ---------------------------------------------------------------- hands and feet
    gl = real.gloves(c, man, "glove.scrap_suede", cuff=0.05)
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
    glue(c, decal("painted_cog", tj, cog(0.0, cz, 0.078, teeth=10, depth=0.25), (0.0, cz, 0.026), 1, "paint.scrap_paint", density=1), jacket.low)

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

    # ---------------------------------------------------------------- head: hood and welding mask
    # Faceless: the eyes go, and the head's skin under the hood and mask.
    arm = aco.Armour(c, "armour", texel=2.2)
    for e in man.eyes:
        c.parts = [p for p in c.parts if p[0] is not e]
        bpy.data.objects.remove(e, do_unlink=True)
    c.cover({"head"})
    # No skin shows anywhere: what is left under the hems needs few texels.
    surfaces._TEXEL_FN[man.low.name] = lambda obj: (lambda isl: 0.3)
    head_gear(c, man, hc, lead, neckline, arm)

    # ---------------------------------------------------------------- welding apron, plate, tool belt
    ap, neck_strap = apron(c, man, lead, jacket, trousers, col)
    ta = pmc.tree(ap.low)
    torso = aco.region_tree(jacket.low, TORSO | {"neck"})
    straps = breastplate(c, b, arm, [ta, torso, pmc.tree(col), pmc.tree(neck_strap)], [torso, ta], jacket.low)
    pauldron(c, b, jacket.low, arm, straps)
    vambraces(c, b, jacket.low, gl, arm)
    tool_belt(c, b, [ta, tj, tt])
    arm.finish()

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


# ------------------------------------------------------------------------------------- hard kit
# Hand-made riveted steel over the workwear: every plate is laid on an envelope of what it covers (the
# Acolyte's Env / Tube / Plate), its edges rolled over a wire, its rivets real, its paint baked.

PLATE = "scrap_plate"


def spaced(pts, step, closed=True):
    """Points every `step` along a polyline [(x, z)]."""
    P = [Vector(p) for p in pts] + ([Vector(pts[0])] if closed else [])
    out, carry = [], 0.0
    for a, b_ in zip(P, P[1:]):
        L = (b_ - a).length
        t = carry
        while t < L:
            q = a.lerp(b_, t / L)
            out.append((q.x, q.y))
            t += step
        carry = t - L
    return out


def bead(name, pts, r, material=PLATE, closed=True, segs=6, normal=None):
    """A round bead along points: a plate's edge rolled over a wire. `normal(p)` steadies the ring frames
    (the plate's outward normal), so a closed loop does not twist."""
    pts = [Vector(p) for p in pts]
    m = len(pts)
    bm = bmesh.new()
    rings, prev = [], None
    for i, p in enumerate(pts):
        a = pts[i - 1] if (closed or i > 0) else p
        b_ = pts[(i + 1) % m] if (closed or i < m - 1) else p
        tan = (b_ - a).normalized()
        ref = Vector(normal(p)) if normal else (prev if prev is not None else Vector((0, 0, 1)))
        if abs(ref.normalized().dot(tan)) > 0.95:
            ref = Vector((1, 0, 0))
        e1 = (ref - tan * ref.dot(tan)).normalized()
        e2 = tan.cross(e1)
        prev = e1
        rings.append([bm.verts.new(p + (e1 * math.cos(2 * math.pi * k / segs) + e2 * math.sin(2 * math.pi * k / segs)) * r) for k in range(segs)])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for r0, r1 in pairs:
        for k in range(segs):
            j = (k + 1) % segs
            bm.faces.new((r0[k], r0[j], r1[j], r1[k]))
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = kit.hs._obj(name, bm, material, 0.0)
    o["shaded"] = True
    return o


def decal_on(name, t, outline, hole, M, kind, offset=0.0006, density=2):
    """Paint on any surface: the flat (x, z) `outline` (with a round `hole` (x, z, r) or None) in the
    build plane of frame M (pmc.frame: its front, -Y, faces out), triangulated and dropped onto tree
    `t` along the frame's inward axis, `offset` off it: bake detail for an armour piece."""
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
        bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if e.calc_length() > 0.006], cuts=density, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
    d = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
    for v in bm.verts:
        o = M @ Vector((v.co.x, -0.06, v.co.z))
        loc, nor = pmc.hit(t, o, d)
        if loc is None:
            loc, nor = nearest(t, o)
        v.co = loc + nor * offset
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    if bm.faces and bm.faces[0].normal.dot(d) > 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    return mesh_obj(name, bm, kind)


def head_gear(c, man, hc, lead, neckline, arm):
    """The welder's head: an oiled-leather hood over the head and neck, tucked into the collar, and over
    the face a riveted steel welding mask flipped down on brass pivots: a flat front with a slit of dark
    glass in a brass holder at the eyes and the Scrappers' cog painted above it, a chin plate angled back
    with a crease down it and a brass breather, the rim rolled; a steel headband round the back of the
    hood to the pivots, a tan crown strap over the top, a brass ratchet knob behind. Returns the hood."""
    dom = kit.dominant(man.low)
    me = man.low.data
    co = [v.co.copy() for v in me.vertices]
    head = BVHTree.FromPolygons(co, [p.vertices[:] for p in me.polygons
                                     if sum(dom[i] in ("head", "neck") for i in p.vertices) * 2 > len(p.vertices)])
    env = aco.Env([head], hc + Vector((0, -0.016, -0.018)), reach=0.22, lat=(-80.0, 90.0), dlat=4.0, dlon=5.0,
                  spread=14.0, blur=10.0, floor=0.006)
    O = env.O
    sm = real._smooth
    SIDE, TAB = 86.0, 93.0  # the mask's sides; the tabs at the pivots

    def top(lo):
        return 26.0 - 12.0 * float(sm(abs(lo), 35.0, SIDE))

    def chin(lo):
        a = abs(lo)
        return -60.0 + 22.0 * float(sm(a, 10.0, SIDE)) + 32.0 * float(sm(a, SIDE - 2.0, TAB))

    # The shell: a squared-off upright (leaning back 12 degrees) round the face, clear of it by 1.7 cm in
    # front and 2 cm at the temples, cut under the chin by a plane angled back 40 degrees.
    th, be, NX = math.radians(12.0), math.radians(40.0), 4.0
    Fp = env.F * math.cos(th) + env.Z * math.sin(th)
    U = env.Z * math.cos(th) - env.F * math.sin(th)
    S = env.S
    Nb = -U * math.cos(be) + Fp * math.sin(be)
    Ra = max((env.r(la, lo) + 0.017) * env.dir(la, lo).dot(Fp) for la in range(-24, 28, 4) for lo in range(-30, 31, 6))
    Rb = max((env.r(la, lo) + 0.021) * abs(env.dir(la, lo).dot(S)) for la in range(-30, 24, 4) for lo in (-90, -84, -78, -72, 72, 78, 84, 90))
    Db = max((env.r(la, lo) + 0.02) * env.dir(la, lo).dot(Nb) for la in range(-76, -4, 4) for lo in range(-40, 41, 8)
             if env.dir(la, lo).dot(Nb) > 0.05)

    def r_mask(la, lo):
        d = env.dir(la, lo)
        df, ds = d.dot(Fp), d.dot(S)
        a = math.atan2(ds, df)
        rs = (abs(math.cos(a) / Ra) ** NX + abs(math.sin(a) / Rb) ** NX) ** (-1.0 / NX) / max(math.hypot(df, ds), 0.15)
        db = d.dot(Nb)
        rb = Db / db if db > 0.05 else 9.0
        k = 0.012
        r = max((rs + rb - math.sqrt((rs - rb) ** 2 + k * k)) / 2, env.r(la, lo) + 0.013)
        return r + 0.005 * max(0.0, 1.0 - abs(lo) / 10.0) * float(sm(-la, 8.0, 18.0))  # the crease down the chin

    def off(extra=0.0):
        return lambda la, lo: r_mask(la, lo) - env.r(la, lo) + extra

    def P(la, lo, extra=0.0):
        return O + env.dir(la, lo) * (r_mask(la, lo) + extra)

    def N(la, lo, h=1.5):
        a = P(la + h, lo) - P(la - h, lo)
        b_ = P(la, lo + h) - P(la, lo - h)
        n = b_.cross(a).normalized()
        return n if n.dot(env.dir(la, lo)) > 0 else -n

    # The hood: the head and neck in near-black oiled leather, open under the mask, a seam over the crown.
    def in_hood(q):
        if lead(q) not in ("head", "neck") or (Vector(q) - neckline[0]).dot(neckline[1]) < -0.03:
            return False
        d = (Vector(q) - O).normalized()
        la = math.degrees(math.asin(max(-1.0, min(1.0, d.dot(env.Z)))))
        lo = math.degrees(math.atan2(d.dot(env.S), d.dot(env.F)))
        return not (abs(lo) < SIDE - 10 and chin(lo) + 14 < la < top(lo) - 8)
    def h_ease(q):
        # Loose over the skull, closing in down the neck to tuck under the collar.
        return 0.006 + 0.0045 * float(sm(q.z, hc.z - 0.11, hc.z - 0.03))
    hood = real.layer(c, man, "hood", "oiled.scrap_hood", in_hood, [], ease=h_ease, smooth=4, texel=0.9, seams="hems")
    hood["unwrap"] = True
    hm = hood.data
    seam = [d.value for d in hm.attributes["seam"].data]
    su = [d.value for d in hm.attributes["seam_u"].data]
    for i, v in enumerate(hm.vertices):
        q = v.co - O
        if q.dot(env.Z) > -0.01 or q.dot(env.F) < -0.02:
            dd = abs(q.dot(env.S))
            if dd < seam[i]:
                seam[i] = dd
                su[i] = 0.1 * math.atan2(q.dot(env.Z), -q.dot(env.F))
    set_attr(hood, "seam", seam)
    set_attr(hood, "seam_u", su)
    c.hide_under(hood, 0.02, 1)
    th = pmc.tree(hood)

    def on_hood(la, lo, lift):
        d = env.dir(la, lo)
        loc, _ = pmc.hit(th, O + d * 0.3, -d)
        return loc + d * lift if loc is not None else env.P(la, lo, lift)

    mask = env.patch("welding_mask", PLATE, -TAB, TAB, chin, top, off(), 0.0025, nu=34, nv=12, bevel=0.0012)
    arm.add(mask, "head")
    tm = pmc.tree(mask)
    up = (P(22.0, 0.0) - P(16.0, 0.0)).normalized()
    arm.detail(decal_on("mask_cog", tm, cog(0.0, 0.0, 0.017, teeth=8, depth=0.28), (0.0, 0.0, 0.0062),
                        pmc.frame(P(19.5, 0.0), N(19.5, 0.0), up), "paint.scrap_paint"))
    rim = [P(top(lo), lo, -0.0012) for lo in [-TAB + 2 * TAB * i / 31 for i in range(32)]]
    rim += [P(top(TAB) + (chin(TAB) - top(TAB)) * k / 4, TAB, -0.0012) for k in range(1, 4)]
    rim += [P(chin(lo), lo, -0.0012) for lo in [TAB - 2 * TAB * i / 31 for i in range(32)]]
    rim += [P(chin(-TAB) + (top(-TAB) - chin(-TAB)) * k / 4, -TAB, -0.0012) for k in range(1, 4)]
    c.rigid(bead("mask_rim", rim, 0.0027, normal=lambda p: Vector(p) - O), "head")

    # The filter holder: a brass frame round the slit, the glass set back in it, screws at the corners.
    wl0, wl1, ww, fw = -1.5, 9.0, 27.0, 4.5
    for name, lo0, lo1, la0, la1 in (("holder", -ww - fw, ww + fw, wl1, wl1 + fw), ("holder", -ww - fw, ww + fw, wl0 - fw, wl0),
                                     ("holder", ww, ww + fw, wl0, wl1), ("holder", -ww - fw, -ww, wl0, wl1)):
        c.rigid(env.patch("filter_" + name, "brass", lo0, lo1, lambda lo, a=la0: a, lambda lo, a=la1: a, off(0.0045), 0.0045,
                          nu=max(2, int((lo1 - lo0) / 6)), nv=1, bevel=0.0008), "head")
    c.rigid(env.patch("filter_glass", "scrap_lens", -ww, ww, lambda lo: wl0, lambda lo: wl1, off(0.002), 0.0012, nu=9, nv=1, bevel=0.0), "head")
    spots = [(P(la, lo, 0.0045), N(la, lo)) for la in (wl0 - fw / 2, wl1 + fw / 2) for lo in (-ww - fw / 2, 0.0, ww + fw / 2)]
    c.rigid(rivets("holder_screws", spots, r=0.0024, material="brass", segs=6), "head")

    # The breather on the chin plate.
    p, n = P(-40.0, 0.0), N(-40.0, 0.0)
    upc = (P(-36.0, 0.0) - P(-44.0, 0.0)).normalized()
    sd = upc.cross(n).normalized()
    br = [kit.cyl("breather", p - n * 0.003, p + n * 0.006, 0.019, "brass", segs=18, bevel=0.0012),
          kit.cyl("breather_cap", p + n * 0.006, p + n * 0.0085, 0.0125, "brass", segs=16, bevel=0.0008)]
    for k in range(6):
        a = 2 * math.pi * k / 6 + 0.3
        q = p + n * 0.0062 + (upc * math.cos(a) + sd * math.sin(a)) * 0.0156
        br.append(kit.cyl("breather_hole", q - n * 0.001, q + n * 0.0008, 0.0021, "black", segs=6, bevel=0))
    c.rigid(kit.join(br, "breather"), "head")

    # Rivets round the rim and down the crease.
    spots = []
    for lo in range(-72, 73, 16):
        spots += [(top(lo) - 4.0, lo), (chin(lo) + 4.5, lo)]
    for sx in (1, -1):
        spots += [(-22.0, sx * (SIDE - 4.0)), (0.0, sx * (SIDE - 4.0))]
    spots += [(-15.0, 0.0), (-24.0, 0.0), (-55.0, 0.0)]
    c.rigid(rivets("mask_rivets", [(P(la, lo), N(la, lo)) for la, lo in spots], r=0.0034, material=PLATE, segs=6), "head")

    # Pivots, headband, crown strap, ratchet.
    for sx in (1, -1):
        a, m = on_hood(4.0, sx * 90.0, 0.0), P(4.0, sx * 90.0)
        ax = (m - a).normalized()
        c.rigid(kit.cyl("mask_pivot", a - ax * 0.002, m + ax * 0.005, 0.0115, "brass", segs=16, bevel=0.0012), "head")
        c.rigid(kit.cyl("pivot_nut", m + ax * 0.005, m + ax * 0.0095, 0.0072, PLATE, segs=6, bevel=0.0006), "head")
    band = [on_hood(4.0, 90.0 + 180.0 * i / 24, 0.0016) for i in range(25)]
    c.rigid(pmc.sweep("head_band", band, 0.02, 0.0022, PLATE, lambda q: Vector(q) - O), "head")
    crown = [on_hood(la, 90.0, 0.0018) for la in range(8, 88, 8)] + [on_hood(90.0, 0.0, 0.0018)] + [on_hood(la, -90.0, 0.0018) for la in range(80, 7, -8)]
    c.rigid(remat(pmc.sweep("crown_strap", crown, 0.024, 0.0028, "accent", lambda q: Vector(q) - O), "leather.accent"), "head")
    p = on_hood(4.0, 180.0, 0.003)
    n = (p - O).normalized()
    c.rigid(kit.join([kit.cyl("ratchet", p - n * 0.002, p + n * 0.011, 0.016, "brass", segs=16, bevel=0.0015),
                      kit.cyl("ratchet_cap", p + n * 0.011, p + n * 0.015, 0.009, PLATE, segs=6, bevel=0.0006)], "ratchet"), "head")
    return hood


def breastplate(c, b, arm, under, around, jacket):
    """A breastplate beaten from two sheets riveted down a centre strap, a scrap patch riveted over a
    hole on the left, the edges rolled; worn on tan straps over the shoulders and round the back,
    buckled in front. `under`: what it is fitted over; `around`: what the straps lie on. Off the plate
    the straps move with the jacket under them (the shoulders roll forward round a gun). Returns the
    shoulder straps."""
    yc = b.j("spine", 0.0).y
    outline = kit.rounded([(-0.13, 1.172), (0.13, 1.172), (0.155, 1.29), (0.149, 1.378), (0.09, 1.432), (-0.09, 1.432),
                           (-0.149, 1.378), (-0.155, 1.29)], 0.02)
    pf = aco.Plate(under, outline, -1, 0.006)
    OFF, TH = 0.0042, 0.0028
    arm.add(pf.patch("breastplate", PLATE, outline, OFF, TH, nu=20, nv=16, bevel=0.0012), "chest")
    strip = kit.rounded([(-0.017, 1.18), (0.017, 1.18), (0.017, 1.424), (-0.017, 1.424)], 0.006)
    arm.add(pf.patch("plate_strap", PLATE, strip, OFF + 0.0024, 0.0024, nu=3, nv=12, bevel=0.0008), "chest")
    scrap = [(0.052, 1.205), (0.116, 1.198), (0.124, 1.262), (0.058, 1.272)]
    arm.add(pf.patch("plate_patch", PLATE, scrap, OFF + 0.002, 0.002, nu=6, nv=6, bevel=0.0008), "chest")
    c.rigid(bead("plate_rim", [pf.P(x, z, OFF - 0.0013) for x, z in spaced(outline, 0.012)], 0.0026,
                 normal=lambda q: pf.normal(q.x, q.z)), "chest")
    spots = [(pf.P(x, z, OFF), pf.normal(x, z)) for x, z in spaced(pmc.grow(outline, -0.012), 0.032) if abs(x) > 0.03]
    spots += [(pf.P(sx * 0.0085, z, OFF + 0.0024), pf.normal(0.0, z)) for sx in (1, -1) for z in [1.192 + 0.0305 * k for k in range(8)]]
    spots += [(pf.P(x, z, OFF + 0.002), pf.normal(x, z)) for x, z in ((0.058, 1.211), (0.11, 1.205), (0.117, 1.256), (0.063, 1.265))]
    c.rigid(rivets("plate_rivets", spots, r=0.0034, material=PLATE, segs=6), "chest")

    # Straps: from the top corners over the shoulders and down the back to a strap round it.
    zb = 1.22
    torso, ta = around

    # Off the plate the straps take the weights of the jacket's body under them (not of the sleeves:
    # under the armpits a sleeve is nearer than the side it hangs against).
    body = torso_only(jacket)

    def off_plate(q):
        return max(float(real._smooth(q.z, 1.425, 1.46)), float(real._smooth(q.y, yc - 0.04, yc)))
    out = []
    anchors = []
    for sx in (1, -1):
        pts = [pf.P(sx * 0.072, 1.392, OFF + 0.0035), pf.P(sx * 0.076, 1.43, OFF + 0.0035)]
        for y in (-0.07, -0.045, -0.02, 0.005, 0.03, 0.055, 0.08):
            loc, _ = outermost([torso], (sx * 0.098, y, 1.3), (0, 0, 1), 0.5)
            if loc is not None and loc.z > 1.42:
                pts.append(loc + Vector((0, 0, 0.0055)))
        for z in (1.41, 1.37, 1.33, 1.29, 1.255, zb + 0.012):
            x = 0.1 - 0.03 * (1.41 - z) / (1.41 - zb)  # converging a little toward the spine, off the shoulder blades
            loc, _ = outermost([torso], (sx * x, yc, z), (0, 1, 0), 0.5)
            if loc is not None:
                pts.append(loc + Vector((0, 0.0055, 0)))
        path = pmc.smooth_path(pts, 3)
        s_ = hold(c, remat(pmc.sweep("shoulder_strap", path, 0.032, 0.0035, "accent", pmc.radial((sx * 0.098, 0, 1.33), (1, 0, 0))),
                           "leather.accent"), body, off_plate)
        out.append(s_)
        k = min(range(1, len(path) - 1), key=lambda i: abs(path[i].z - 1.452) + (5.0 if path[i].y > -0.02 else 0.0))
        tan = (path[k + 1] - path[k - 1]).normalized()
        nn = pmc.radial((sx * 0.098, 0, 1.33), (1, 0, 0))(path[k]).normalized()
        hold(c, buckle("strap_buckle", path[k] + nn * 0.0035, tan, nn, 0.034), body, off_plate)
        anchors += [(pf.P(sx * 0.072 + dx, 1.392, OFF + 0.0055), pf.normal(sx * 0.072, 1.392)) for dx in (-0.009, 0.009)]
    x_edge = 0.14
    ring = [pf.P(x_edge, zb, -0.002)]
    for i in range(23):
        a = math.radians(66 + 228 * i / 22)
        d = Vector((math.sin(a), -math.cos(a), 0))
        loc, _ = outermost([torso, ta], (0, yc, zb), d, 0.5)
        if loc is not None:
            ring.append(loc + d * 0.005)
    ring.append(pf.P(-x_edge, zb, -0.002))
    y_edge = ring[0].y
    hold(c, remat(pmc.sweep("back_strap", pmc.smooth_path(ring, 2), 0.03, 0.0035, "accent", pmc.radial((0, yc, 0))), "leather.accent"), body,
         lambda q: float(real._smooth(q.y, y_edge, y_edge + 0.03)))
    k = 1 + round((262 - 66) / 228 * 22)  # the buckle on the right side, clear of the shoulder strap
    q = ring[k]
    tan = (ring[k + 1] - ring[k - 1]).normalized()
    nn = Vector((q.x, q.y - yc, 0)).normalized()
    hold(c, buckle("back_buckle", q + nn * 0.0035, tan, nn, 0.032), body, lambda q: 1.0)
    c.rigid(rivets("strap_rivets", anchors, r=0.0036, material="brass", segs=6), "chest")
    me = body.data
    bpy.data.objects.remove(body, do_unlink=True)
    bpy.data.meshes.remove(me)
    return out


def pauldron(c, b, jacket, arm, hard, s="L", sx=1):
    """One pauldron, on the left: a domed cap beaten over the shoulder, two lames below it riveted at
    their ends, the bottom edges rolled, the Scrappers' cog painted on the cap, a tan strap round the
    arm under the lames."""
    ua = "upper_arm." + s
    ua0, ua1 = b.j(ua, 0.0), b.j(ua, 1.0)
    sleeve = aco.region_tree(jacket, {ua, "shoulder." + s})
    tu = aco.Tube([sleeve], ua0, ua1, front=(0, -1, 0), t=(0.05, 0.75), nt=22, nphi=48, reach=0.14, spread=0.03, blur=0.02)
    lames, spots = [], []
    for t0, t1, off in ((0.30, 0.47, 0.0065), (0.17, 0.34, 0.0105)):
        lame = tu.patch("pauldron_lame", PLATE, t0, t1, 90 * sx, 60, off, 0.0026, nu=12, nv=3, corner=2.5, bevel=0.001)
        arm.add(lame, ua)
        lames.append(lame)
        f = 0.62
        c.rigid(bead("lame_rim", [tu.P(t1, 90 * sx + 60 * f * (2 * k / 10 - 1), off - 0.0013) for k in range(11)], 0.0024, closed=False,
                     normal=lambda q: tu.d(90 * sx)), ua)
        for ph in (90 * sx - 50, 90 * sx + 50):
            tm = (t0 + t1) / 2
            spots.append((tu.P(tm, ph, off), tu.d(ph)))
    O = ua0 + Vector((-sx * 0.012, 0.0, -0.012))
    cap_env = aco.Env([sleeve] + lames + list(hard), O, Z=(sx * 0.6, 0.0, 0.8), F=(0, -sx, 0), reach=0.16, lat=(-40.0, 90.0),
                      dlat=4.0, dlon=6.0, spread=9.0, blur=7.0, floor=0.003)

    def cap_rim(lo):
        sn = math.sin(math.radians(lo))
        return 38.0 - 45.0 * max(0.0, sn) ** 1.3 + 7.0 * max(0.0, -sn)
    CAP = 0.0105
    cap = cap_env.patch("pauldron", PLATE, -180.0, 180.0, cap_rim, lambda lo: 84.0, CAP, 0.003, nu=28, nv=6, closed=True, pole=True,
                        bevel=0.0015)
    arm.add(cap, ua)
    c.rigid(bead("pauldron_rim", [cap_env.P(cap_rim(lo), lo, CAP - 0.0013) for lo in range(-180, 180, 10)], 0.0027,
                 normal=lambda q: Vector(q) - O), ua)
    for lo in range(-160, 180, 40):
        la = cap_rim(lo) + 6
        spots.append((cap_env.P(la, lo, CAP), cap_env.normal(la, lo, CAP)))
    c.rigid(rivets("pauldron_rivets", spots, r=0.0034, material=PLATE, segs=6), ua)
    M = pmc.frame(cap_env.P(30, 90, CAP), cap_env.normal(30, 90, CAP), (0, 0, 1))
    arm.detail(decal_on("pauldron_cog", pmc.tree(cap), cog(0.0, 0.0, 0.03, teeth=9, depth=0.26), (0.0, 0.0, 0.011), M, "paint.scrap_paint"))
    tu2 = aco.Tube([sleeve], ua0, ua1, hard=lames, t=(0.3, 0.6), nt=7, nphi=36, reach=0.14)
    ring = tu2.ring(0.43, 0.0015, n=22)
    c.rigid(remat(aco.strap_ring("arm_strap", ring, ua0.lerp(ua1, 0.43), ua1 - ua0, 0.024, 0.0035, "accent"), "leather.accent"), ua)
    cc = ua0.lerp(ua1, 0.43)
    k = min(range(len(ring)), key=lambda i: (ring[i] - cc).normalized().dot(tu.d(-90 * sx)) * -1)
    q = ring[k]
    nn = (q - cc - (ua1 - ua0).normalized() * (q - cc).dot((ua1 - ua0).normalized())).normalized()
    c.rigid(buckle("arm_buckle", q + nn * 0.003, (ring[(k + 1) % len(ring)] - ring[k - 1]).normalized(), nn, 0.024), ua)


def vambraces(c, b, jacket, gloves, arm):
    """Forearm guards beaten to the arm over the sleeves, ends rolled, riveted, on two tan straps each;
    a brass pressure gauge on the left one, piped down to the wrist."""
    tg = pmc.tree(gloves)
    for s, sx in (("L", 1), ("R", -1)):
        fa = "forearm." + s
        f0, f1 = b.j(fa, 0.0), b.j(fa, 1.0)
        A = (f1 - f0).normalized()
        sleeve = aco.region_tree(jacket, {fa})
        tu = aco.Tube([sleeve, tg], f0, f1, front=(0, -1, 0), t=(0.0, 1.0), nt=26, nphi=48, reach=0.12, spread=0.025, blur=0.018)
        T0, T1, PH, HALF, OFF = 0.12, 0.76, 90 * sx, 108, 0.0042
        guard = tu.patch("vambrace", PLATE, T0, T1, PH, HALF, OFF, 0.0026, nu=18, nv=10, corner=3.0, bulge=0.003, bevel=0.0012)
        arm.add(guard, fa)
        for t in (T0, T1):
            c.rigid(bead("vambrace_rim", [tu.P(t, PH + HALF * 0.62 * (2 * k / 10 - 1), OFF - 0.0013) for k in range(11)], 0.0024,
                         closed=False, normal=lambda q: tu.d(PH)), fa)
        spots = [(tu.P(t, PH + dp, OFF + 0.0008), tu.d(PH + dp)) for t in (T0 + 0.05, T1 - 0.05) for dp in (-58, 0, 58)]
        c.rigid(rivets("vambrace_rivets", spots, r=0.0032, material=PLATE, segs=6), fa)
        tu2 = aco.Tube([sleeve, tg], f0, f1, hard=[guard], t=(0.2, 0.7), nt=11, nphi=36, reach=0.12)
        for tq in (0.3, 0.6):
            ring = tu2.ring(tq, 0.0015, n=22)
            c.rigid(remat(aco.strap_ring("vambrace_strap", ring, f0.lerp(f1, tq), f1 - f0, 0.02, 0.0032, "accent"), "leather.accent"), fa)
            cc = f0.lerp(f1, tq)
            k = max(range(len(ring)), key=lambda i: (ring[i] - cc).normalized().dot(tu.d(-PH)))
            q = ring[k]
            nn = (q - cc - A * (q - cc).dot(A)).normalized()
            c.rigid(buckle("vambrace_buckle", q + nn * 0.003, (ring[(k + 1) % len(ring)] - ring[k - 1]).normalized(), nn, 0.02), fa)
        if s == "L":
            out = tu.d(PH)
            gb = tu.P(0.45, PH, OFF + 0.002)
            g = gauge(gb, out, -A, r=0.0215, depth=0.011, needle=40)
            g += [kit.cyl("gauge_stem", gb + A * 0.02, gb + A * 0.029, 0.0045, "brass", segs=12, bevel=0.0005),
                  kit.cyl("gauge_nut", gb + A * 0.028, gb + A * 0.036, 0.0062, "brass", segs=6, bevel=0.0005),
                  kit.cyl("gauge_pipe", gb + A * 0.035 - out * 0.002, tu.P(0.8, PH, OFF + 0.006), 0.0028, "scrap_copper", segs=10, bevel=0),
                  kit.cyl("gauge_union", tu.P(0.79, PH, OFF + 0.006), tu.P(0.83, PH, OFF + 0.006), 0.0052, "brass", segs=6, bevel=0.0005)]
            c.rigid(kit.join(g, "wrist_gauge"), fa)


def apron(c, man, lead, jacket, trousers, col):
    """A split-leg welding apron of heavy leather: a bib from the chest, a skirt round the front of the
    hips, a flap down the front of each thigh; cut from the body and draped stiff over the jacket and
    trousers. Tan neck and thigh straps with brass buckles and rivets, the Scrappers' cog painted on the
    left flap. Returns (the garment, the neck strap)."""
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

    rivets_at = []

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
    neck_strap = c.rigid(remat(pmc.sweep("neck_strap", strap, 0.022, 0.0035, "accent", pmc.radial((0, neck.y, 0))), "leather.accent"), "chest")

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
    paint = decal("painted_cog", ta, cog(cx, cz, 0.046, teeth=9, depth=0.26), (cx, cz, 0.0165), -1, "paint.scrap_paint", density=1)
    glue(c, paint, ap.low)
    return ap, neck_strap


def buckle(name, at, along, out, w=0.03):
    """A forged brass roller buckle: a frame with a centre bar and a tongue, lying on a strap running
    `along`, facing `out`. Four bars, not a box with a hole cut in it: a buckle is a few centimetres
    across and a dozen of them hang on the harness."""
    u, n = Vector(along).normalized(), Vector(out).normalized()
    s = n.cross(u).normalized()
    M = Matrix((u, s, n)).transposed().to_4x4()
    M.translation = Vector(at)
    hx, hy, bx, by = w * 0.45, w * 0.575, w * 0.14, w * 0.15
    parts = [kit.block(name, (0, sy * (hy - by / 2), 0.001), (2 * hx, by, 0.004), "brass", bevel=0) for sy in (1, -1)]
    parts += [kit.block(name, (sx * (hx - bx / 2), 0, 0.001), (bx, 2 * hy - 2 * by, 0.004), "brass", bevel=0) for sx in (1, -1)]
    parts.append(kit.cyl(name, (0, -hy + by, 0.002), (0, hy - by, 0.002), 0.0019, "brass", segs=6, bevel=0))
    parts.append(kit.block(name, (w * 0.2, 0, 0.0028), (w * 0.42, 0.0026, 0.002), "steel", bevel=0))
    o = kit.join(parts, name)
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

    # Tool pouch on the left hip: an adjustable wrench, a spanner and a screwdriver standing in it.
    o, x, y, z, push = hang(100, 0.14)
    pouch = kit.block("tool_pouch", (0, push + 0.02, -0.072), (0.09, 0.036, 0.11), "leather", bevel=0.006)
    kit.cut(pouch, kit.block("pouch_mouth", (0, push + 0.02, -0.014), (0.078, 0.026, 0.02), "steel", bevel=0))
    yt = push + 0.02
    tools = [pouch, kit.block("pouch_strap", (0, 0.005, -0.012), (0.036, 0.01, 0.062), "leather", bevel=0.002),
             kit.block("pouch_welt", (0, push + 0.039, -0.072), (0.076, 0.004, 0.092), "leather", bevel=0.0015),
             kit.cyl("driver", (0.03, yt, -0.03), (0.03, yt + 0.001, 0.04), 0.0098, "scrap_ash", segs=8, bevel=0.0015),
             kit.ring("ferrule", (0.03, yt, -0.024), (0, 0, 1), 0.0105, 0.006, 0.008, "brass", segs=12)]
    # The adjustable wrench, jaws forward: a forged shank, a fixed jaw at the top, a sliding jaw under
    # it on a knurled worm.
    tools += [kit.block("wrench_shank", (-0.03, yt, 0.0), (0.017, 0.0085, 0.18), "steel", bevel=0.0018),
              kit.block("wrench_jaw", (-0.013, yt, 0.083), (0.05, 0.0105, 0.013), "steel", bevel=0.0018, taper=(1.0, 0.85)),
              kit.block("wrench_jaw", (-0.011, yt, 0.054), (0.044, 0.0095, 0.015), "steel", bevel=0.0018),
              kit.cyl("wrench_worm", (-0.03, yt, 0.024), (-0.03, yt, 0.042), 0.0105, "steel", segs=10, bevel=0.0008)]
    tools.append(kit.block("spanner", (0.011, yt, -0.02), (0.013, 0.0045, 0.1), "steel", bevel=0.0012))
    jaw = kit.cyl("spanner_head", (0.011, yt - 0.0025, 0.035), (0.011, yt + 0.0025, 0.035), 0.0145, "steel", segs=16, bevel=0.0008)
    kit.cut(jaw, kit.block("jaw", (0.011, yt, 0.046), (0.0105, 0.03, 0.026), "steel", bevel=0))
    tools.append(jaw)
    tools.append(rivets("pouch_rivets", [(Vector((xx, push + 0.0385, -0.03)), Vector((0, 1, 0))) for xx in (-0.034, 0.034)], r=0.0035, material="brass"))
    c.rigid(onto(kit.join(tools, "tool_pouch"), o, x, y, z), "hips")

    # Spanner pouch on the left front: riveted leather, the flap on a brass stud, a ring spanner
    # standing in a loop on its front.
    o, x, y, z, push = hang(62, 0.09)
    yp = push + 0.016
    sp = [kit.block("spanner_pouch", (0, yp, -0.05), (0.066, 0.028, 0.078), "leather", bevel=0.005),
          kit.block("pouch_strap", (0, 0.005, -0.012), (0.03, 0.01, 0.05), "leather", bevel=0.002),
          kit.block("pouch_flap", (0, yp + 0.002, -0.022), (0.07, 0.031, 0.03), "leather", bevel=0.004, taper=(1.0, 0.92)),
          kit.cyl("pouch_stud", (0, yp + 0.0155, -0.03), (0, yp + 0.0205, -0.03), 0.0055, "brass", segs=10, bevel=0.001),
          kit.block("spanner_loop", (0.02, yp + 0.0165, -0.064), (0.022, 0.004, 0.014), "leather", bevel=0.0012),
          kit.block("ring_spanner", (0.02, yp + 0.021, -0.025), (0.011, 0.0042, 0.105), "steel", bevel=0.001)]
    eye = kit.ring("spanner_ring", (0.02, yp + 0.021, 0.034), (0, 1, 0), 0.0135, 0.0075, 0.0045, "steel", segs=14)
    sp.append(eye)
    sp.append(rivets("pouch_rivets", [(Vector((xx, yp + 0.014, zz)), Vector((0, 1, 0))) for xx in (-0.028, 0.028) for zz in (-0.04, -0.082)],
                     r=0.0032, material="brass"))
    c.rigid(onto(kit.join(sp, "spanner_pouch"), o, x, y, z), "hips")

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


SPEC = {"build": build, "faction": "scrappers", "budget": (25000, 80000), "loadout": "shotgun",
        "colors": {"primary": "#6e6450", "secondary": "#3d3a33", "accent": "#9a6a35"}}
