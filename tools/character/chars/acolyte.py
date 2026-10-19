"""Acolyte, Regime: the faceless grunt of the Algorithm's cult. A sealed bone-white helmet with one
curved red sensor slit, bone polymer plate etched with black code scripture (cuirass, back plate,
abdomen lames, layered pauldrons, vambraces, tassets, knee cops, greaves) over a black undersuit, and
cables from the helmet and the plates into an uplink node on the back with a short antenna.

Tints: primary = undersuit, secondary = waist wrap and pouches, accent = straps.

This module also holds the Regime's shared helpers (scripture projected onto curved plates,
contour-following bands and grooves, analytic arc plates and ellipsoid plate forms, cheap screws,
bands, sockets, antennas, the sealed helmet) that zealot.py and choir.py import.
"""

import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

import kit
from kit import FEET, SHINS, TORSO

# ------------------------------------------------------------------------------- Regime helpers


def bvh(obj):
    """A ray-cast tree of an object's mesh (parts here carry identity transforms)."""
    me = obj.data
    return BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])


def hit(tree, p, d, dist=1.0):
    """First surface point and outward normal from `p` along `d`, or None."""
    d = Vector(d).normalized()
    loc, n, _, _ = tree.ray_cast(Vector(p), d, dist)
    if loc is None:
        return None
    if n.dot(d) > 0:
        n = -n
    return loc, n


_GLYPHS = {}


def glyph(ch, size):
    """A raised character (verts, faces) centred on the origin in the XY plane, extruded along Z."""
    key = (ch, round(size, 5))
    if ch == "∴" and key not in _GLYPHS:  # three square dots: a third of the font glyph's triangles
        vs, fs = [], []
        for dx, dy in ((0, 0.28), (-0.27, -0.2), (0.27, -0.2)):
            bv, bf = bar(size * 0.17, size * 0.17)
            fs += [tuple(i + len(vs) for i in f) for f in bf]
            vs += [v + Vector((dx * size, dy * size, 0)) for v in bv]
        _GLYPHS[key] = (vs, fs)
    if key not in _GLYPHS:
        cu = bpy.data.curves.new("g", "FONT")
        cu.body = ch
        cu.size = size
        cu.extrude = 0.00045
        cu.resolution_u = 1
        o = bpy.data.objects.new("g", cu)
        bpy.context.scene.collection.objects.link(o)
        bpy.context.view_layer.update()
        me = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        verts = [v.co.copy() for v in me.vertices]
        # Drop the back cap: it sits under the surface the glyph is laid on.
        faces = [tuple(p.vertices) for p in me.polygons if not all(me.vertices[i].co.z < 0 for i in p.vertices)]
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)
        if verts:
            cx = (min(v.x for v in verts) + max(v.x for v in verts)) / 2
            verts = [v - Vector((cx, size * 0.36, 0)) for v in verts]  # common baseline
        _GLYPHS[key] = (verts, faces)
    return _GLYPHS[key]


def bar(w, h, angle=0.0, t=0.0009):
    """A small raised block (barcode bar, code tick) as (verts, faces); no bottom face."""
    vs = [Vector((x * w / 2, y * h / 2, z * t / 2)) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    fs = [(4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return vs, fs


def project(target, items, origin, d, up=(0, 0, 1), lift=0.0003, material="ink", name="code", tree=None):
    """Lay small marks onto `target`'s surface: each item (x, y, mark) sits where a ray along `d`
    through `origin` + x right + y up meets the surface, turned to its normal. A mark is (char, size)
    or a (w, h) bar. Code scripture, barcodes, tick rows."""
    tree = tree or bvh(target)
    d = Vector(d).normalized()
    up = Vector(up).normalized()
    u0 = up.cross(-d).normalized()
    v0 = (-d).cross(u0).normalized()
    bm = bmesh.new()
    for x, y, mark in items:
        h = hit(tree, Vector(origin) + u0 * x + v0 * y - d * 0.3, d, 0.8)
        if not h:
            continue
        loc, n = h
        u = up.cross(n)
        if u.length < 1e-6:
            u = u0.copy()
        u.normalize()
        v = n.cross(u)
        verts, faces = glyph(*mark) if isinstance(mark[0], str) else bar(*mark)
        m = Matrix((u, v, n)).transposed()
        if not isinstance(mark[0], str) and len(mark) == 3:
            m = m @ Matrix.Rotation(mark[2], 3, "Z")
        base = loc + n * lift
        vs = [bm.verts.new(base + m @ co) for co in verts]
        for f in faces:
            try:
                bm.faces.new([vs[i] for i in f])
            except ValueError:
                pass
    return kit.hs._obj(name, bm, material, 0.0)


def code_rows(lines, size, lead=1.5, adv=0.64):
    """Items for `project`: lines of monospaced code, centred, rows going down."""
    items = []
    n = len(lines)
    for r, line in enumerate(lines):
        y = ((n - 1) / 2 - r) * size * lead
        w = len(line) * size * adv
        for i, ch in enumerate(line):
            if ch != " ":
                items.append((-w / 2 + (i + 0.5) * size * adv, y, (ch, size)))
    return items


def tick_rows(seed, rows, length, h, unit=0.0012, lead=1.7):
    """Items for `project`: rows of binary ticks and dashes (cheap scripture for small plates)."""
    rnd = random.Random(seed)
    items = []
    for r in range(rows):
        y = ((rows - 1) / 2 - r) * h * lead
        x = 0.0
        row = []
        while x < length:
            kind = rnd.random()
            w = unit if kind < 0.5 else unit * 3.2 if kind < 0.85 else unit * 6
            row.append((x + w / 2, w))
            x += w + unit * (1.4 if rnd.random() < 0.8 else 4)
        items += [(bx - x / 2, y, (w, h)) for bx, w in row]
    return items


def sigil(r, n=28, w=0.0032):
    """Items for `project`: the Algorithm's ring (with code_rows(["∴"]) inside it, the cult mark)."""
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), (w, 2 * math.pi * r / n * 1.05, 2 * math.pi * i / n)) for i in range(n)]


def barcode(seed, length, h, unit=0.0011):
    """Items for `project`: one barcode of bars along x, centred."""
    rnd = random.Random(seed)
    bars = []
    x = 0.0
    while x < length:
        w = unit * rnd.choice((1, 1, 2, 3))
        bars.append((x + w / 2, w))
        x += w + unit * rnd.choice((1, 1, 2))
    return [(bx - x / 2, 0.0, (w, h)) for bx, w in bars]


def scripture(seed, rows, cols):
    """Pseudo-random hex and binary scripture lines with the cult's ∴ marks."""
    rnd = random.Random(seed)
    words = ["0x7F", "0xA3", "FF", "1E", "C0DE", "0110", "1011", "∴", "7F3A", "00", "9C", "0x1D", "101", "E7", "∴", "11"]
    out = []
    for _ in range(rows):
        line = ""
        while len(line) < cols:
            line += rnd.choice(words) + " "
        out.append(line[:cols].strip())
    return out


def contour(tree, c, z, angles, reach=0.6):
    """Surface radius around the vertical axis through `c` at height `z`, seen from outside, per angle
    (degrees, 0 = front -Y, positive toward +X). `tree` may be a list: the outermost hit wins.
    Returns [(direction, radius or None)]."""
    trees = tree if isinstance(tree, (list, tuple)) else [tree]
    out = []
    c = Vector((c[0], c[1], z))
    for a in angles:
        r = math.radians(a)
        dv = Vector((math.sin(r), -math.cos(r), 0))
        best = None
        for t in trees:
            h = hit(t, c + dv * reach, -dv, reach)
            if h and (best is None or (h[0] - c).length > best):
                best = (h[0] - c).length
        out.append((dv, best))
    return out


def ring_band(name, tree, c, z, a0, a1, r0, r1, height, material, n=24, reach=0.6):
    """A horizontal band following the surface around the axis through `c`, from `r0` to `r1` off the
    surface (negative is inside): groove cutters, glowing slits, inlaid seams. A full 360 degree span
    closes into a loop (a strap hugging a limb and the plate on it)."""
    loop = abs(a1 - a0) >= 359.9
    angles = [a0 + (a1 - a0) * i / n for i in range(n if loop else n + 1)]
    prof = [(d, r) for d, r in contour(tree, c, z, angles, reach) if r is not None]
    if len(prof) < (n if loop else 2):
        return None
    cc = Vector((c[0], c[1]))
    outer = [cc + d.to_2d() * (r + r1) for d, r in prof]
    inner = [cc + d.to_2d() * (r + r0) for d, r in prof]
    bm = bmesh.new()
    rows = []
    for zz in (z - height / 2, z + height / 2):
        rows.append(([bm.verts.new((p.x, p.y, zz)) for p in outer], [bm.verts.new((p.x, p.y, zz)) for p in inner]))
    (o0, i0), (o1, i1) = rows
    m = len(outer)
    for i in range(m if loop else m - 1):
        j = (i + 1) % m
        bm.faces.new((o0[i], o0[j], o1[j], o1[i]))
        bm.faces.new((i0[j], i0[i], i1[i], i1[j]))
        bm.faces.new((o0[j], o0[i], i0[i], i0[j]))
        bm.faces.new((o1[i], o1[j], i1[j], i1[i]))
    if not loop:
        bm.faces.new((o0[0], o1[0], i1[0], i0[0]))
        bm.faces.new((o0[-1], i0[-1], i1[-1], o1[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return kit.hs._obj(name, bm, material, 0.0)


def line_band(name, tree, a, b_, d, r0, r1, width, material="steel", n=12):
    """A band along the surface from `a` to `b_` (seen along `d`), from `r0` to `r1` off the surface,
    `width` wide: vertical seams, keels, groove cutters on curved plates."""
    a, b_, d = Vector(a), Vector(b_), Vector(d).normalized()
    side = (b_ - a).normalized().cross(d).normalized()
    bm = bmesh.new()
    rings = []
    for i in range(n + 1):
        h = hit(tree, a.lerp(b_, i / n) - d * 0.4, d, 0.8)
        if h:
            loc, nn = h
            rings.append([bm.verts.new(loc + nn * rr + side * s * width / 2) for rr, s in ((r0, -1), (r0, 1), (r1, 1), (r1, -1))])
    for ra, rb in zip(rings, rings[1:]):
        for q in range(4):
            j = (q + 1) % 4
            bm.faces.new((ra[q], ra[j], rb[j], rb[q]))
    if len(rings) > 1:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return kit.hs._obj(name, bm, material, 0.0)


def seam(name, tree, axis_pts, outward, r0=-0.0008, r1=0.0024, width=0.008, material="secondary"):
    """Piping along a body surface: casts from points inside a limb (`axis_pts`) toward `outward` and
    runs a raised strip through the hits."""
    out = Vector(outward).normalized()
    bm = bmesh.new()
    rings = []
    pts = [Vector(p) for p in axis_pts]
    for i, p in enumerate(pts):
        loc, _, _, _ = tree.ray_cast(p, out, 0.3)
        if loc is None:
            continue
        along = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        side = along.cross(out).normalized()
        rings.append([bm.verts.new(loc + out * rr + side * sw * width / 2) for rr, sw in ((r0, -1), (r0, 1), (r1, 1), (r1, -1))])
    for ra, rb in zip(rings, rings[1:]):
        for q in range(4):
            j = (q + 1) % 4
            bm.faces.new((ra[q], ra[j], rb[j], rb[q]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return kit.hs._obj(name, bm, material, 0.0)


def frame(a, b_, out):
    """A limb frame: Z along a->b_, X toward `out`, Y = Z x X (3x3, columns X, Y, Z)."""
    z = (Vector(b_) - Vector(a)).normalized()
    out = Vector(out)
    x = (out - z * out.dot(z)).normalized()
    return Matrix((x, z.cross(x), z)).transposed()


def put(obj, m3, at):
    obj.data.transform(Matrix.Translation(Vector(at)) @ m3.to_4x4())
    return obj


def arc_plate(name, a, b_, out, r0, r1, half, thick, material="bone", bulge=0.0, squash=1.0, segs=12, rings=4, bevel=0.003, flare=0.0):
    """A curved plate around an axis: the part of a tapered tube (radius r0 at `a` .. r1 at `b_`)
    within `half` degrees of the `out` side (a number, or (at a, at b_) for a tapering plate),
    `thick` thick, bulging `bulge` mid-length, its sides `squash`ed, its far end flared out by `flare`.
    Vambraces, greaves, tassets, pauldron lames, abdomen lames."""
    a, b_ = Vector(a), Vector(b_)
    L = (b_ - a).length
    h0, h1 = (half, half) if not isinstance(half, tuple) else half
    bm = bmesh.new()

    def pt(t, j, extra):
        hh = math.radians(h0 + (h1 - h0) * t)
        th = -hh + 2 * hh * j / segs
        r = r0 + (r1 - r0) * t + bulge * math.sin(math.pi * t) + flare * t ** 3 + extra
        return Vector((r * math.cos(th), r * math.sin(th) * squash, t * L))
    ts = [i / rings for i in range(rings + 1)]
    O = [[bm.verts.new(pt(t, j, thick)) for j in range(segs + 1)] for t in ts]
    I = [[bm.verts.new(pt(t, j, 0.0)) for j in range(segs + 1)] for t in ts]
    for i in range(rings):
        for j in range(segs):
            bm.faces.new((O[i][j], O[i][j + 1], O[i + 1][j + 1], O[i + 1][j]))
            bm.faces.new((I[i][j + 1], I[i][j], I[i + 1][j], I[i + 1][j + 1]))
    for i in (0, rings):
        for j in range(segs):
            bm.faces.new((O[i][j + 1], O[i][j], I[i][j], I[i][j + 1]))
    for j in (0, segs):
        for i in range(rings):
            bm.faces.new((O[i][j], O[i + 1][j], I[i + 1][j], I[i][j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = kit.hs._obj(name, bm, material, bevel, 1)
    for p in o.data.polygons:
        p.use_smooth = True
    o["shaded"] = False
    return put(o, frame(a, b_, out), a)


def arc_point(a, b_, out, r, t, deg, squash=1.0):
    """A point on the arc_plate surface of radius `r` at `t` along and `deg` round from `out`."""
    a, b_ = Vector(a), Vector(b_)
    th = math.radians(deg)
    return Vector(a) + frame(a, b_, out) @ Vector((r * math.cos(th), r * math.sin(th) * squash, t * (b_ - a).length))


def ell_form(c, radii, rot=(90, 0, 0), u=40, v=24):
    """An ellipsoid to shell plates from (domes, cuirasses). Its poles lie along local Z, turned by
    `rot` (degrees); the default puts them on Y so front and back caps get clean ring edges."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=1.0)
    m = Matrix.Translation(Vector(c)) @ Euler(tuple(math.radians(x) for x in rot)).to_matrix().to_4x4() @ Matrix.Diagonal((*radii, 1))
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    return kit.hs._obj("form", bm, "steel", 0.0)


def form_plate(form, cutter, name, material="bone", thick=0.01, keep=None, bevel=0.003, offset=0.0):
    """A plate shelled off a form (outward, `thick` thick), trimmed to `cutter` (None: the kept region
    only). The form stays for more plates; drop it with `done(form)`."""
    o = kit.shell(form, keep, name, material, offset=offset, thick=thick, detail=1.0)
    if cutter is not None:
        o = kit.intersect(o, cutter)
    o["bevel"] = bevel
    o["segs"] = 1
    o["shaded"] = False
    return o


def done(*objs):
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)


def screw(at, normal, r=0.004, material="gunmetal"):
    """A cheap socket-head screw: a bevelled octagonal head with a dark hex socket."""
    n = Vector(normal).normalized()
    at = Vector(at)
    head = kit.cyl("screw", at - n * 0.0012, at + n * 0.0024, r, material, segs=8, bevel=0.0006, bsegs=1)
    hexa = kit.cyl("screw_hex", at + n * 0.0021, at + n * 0.0029, r * 0.45, "black", segs=6, bevel=0)
    return kit.join([head, hexa], "screw")


def screw_on(tree, p, d, r=0.004, material="gunmetal"):
    h = hit(tree, p, d)
    return screw(h[0], h[1], r, material) if h else None


def fix(c, obj, bone):
    """c.rigid for parts that may be missing (a screw whose ray missed its plate)."""
    if obj is not None:
        c.rigid(obj, bone)


def band(name, c, radii, width, thick, material, axis=(0, 0, 1), segs=14):
    """kit.band with fewer segments and flat-shaded edges instead of a bevel (a quarter of the
    triangles). Always takes kit's general path: kit.band's vertical-axis path sweeps kit.strap, whose
    normals point away from the world origin, so a vertical band round an off-centre limb twists."""
    a = Vector(axis).normalized()
    u = Vector((1, 0, 0)) if abs(a.z) >= 0.9 else a.cross(Vector((0, 0, 1))).normalized()
    v = a.cross(u).normalized()
    c = Vector(c)
    pts = [c + u * radii[0] * math.cos(2 * math.pi * i / segs) + v * radii[1] * math.sin(2 * math.pi * i / segs) for i in range(segs)]
    o = kit._band_general(name, pts, a, width, thick, material, c)
    o["bevel"] = 0.0
    return o


def ring(name, c, axis, r_out, r_in, width, material, segs=20):
    o = kit.ring(name, c, axis, r_out, r_in, width, material, segs=segs)
    o["bevel"] = 0.0
    return o


def antenna(name, base, tip, r=0.005, bars=(), tip_mat="glow_red", material="gunmetal"):
    """A thin mast from `base` to `tip` with a collar, crossbars (t, half length) and a glowing tip."""
    base, tip = Vector(base), Vector(tip)
    ax = (tip - base).normalized()
    side = ax.cross(Vector((0, 1, 0)) if abs(ax.y) < 0.9 else Vector((1, 0, 0))).normalized()
    parts = [kit.cyl(name, base, tip, r, material, r1=r * 0.6, segs=8, bevel=0),
             kit.cyl(name, base - ax * 0.004, base + ax * 0.03, r * 2.4, material, segs=10, bevel=0.001, bsegs=1)]
    for t, half in bars:
        p = base.lerp(tip, t)
        parts.append(kit.cyl(name, p - side * half, p + side * half, r * 0.45, material, segs=6, bevel=0))
        for s in (-1, 1):
            parts.append(kit.cyl(name, p + side * s * half - ax * 0.004, p + side * s * half + ax * 0.004, r * 0.8, material, segs=6, bevel=0))
    parts.append(kit.cyl(name, tip - ax * 0.002, tip + ax * 0.012, r * 1.1, tip_mat, segs=8, bevel=0))
    return kit.join(parts, name)


def socket(name, at, axis, r=0.012, material="gunmetal", lip="bone"):
    """A cable socket: a gunmetal port in a collar, looking along `axis`."""
    at, a = Vector(at), Vector(axis).normalized()
    port = kit.cyl(name, at - a * 0.006, at + a * 0.008, r, material, segs=12, bevel=0.001, bsegs=1)
    plug = kit.cyl(name, at + a * 0.007, at + a * 0.0085, r * 0.55, "black", segs=8, bevel=0)
    collar = ring(name, at + a * 0.001, a, r * 1.35, r * 0.95, 0.006, lip, segs=12)
    return kit.join([port, plug, collar], name)


def cable(name, pts, r=0.0045, material="rubber"):
    return kit.rope(name, [Vector(p) for p in pts], r, material)


# -------------------------------------------------------------------------------- hanging cloth


def weigh_custom(c, obj, fn):
    """Skin `obj` with weights from `fn(point) -> {bone: weight}` and hand it to the character as
    already weighted (kit has no hook for custom weights; parts tagged "DONE" keep their groups, the
    same tag Char.flesh uses)."""
    hs = kit.hs
    for m in list(obj.modifiers):
        hs._apply(obj, m.name)
    obj.vertex_groups.clear()
    groups = {}
    for v in obj.data.vertices:
        for bn, wt in fn(v.co).items():
            if wt <= 1e-4:
                continue
            if bn not in groups:
                groups[bn] = obj.vertex_groups.new(name=bn)
            groups[bn].add([v.index], wt, "REPLACE")
    c.parts.append((obj, "DONE", None))
    return obj


def lifted_weights(flesh, offset, groups):
    """Weights for a part lifted about `offset` off the body (a robe shell, a stole on it): each
    point copies the body weights where it was lifted from, choosing among the body regions in
    `groups` (bone sets) the one whose nearest surface lies closest to `offset` away. Unlike kit's
    nearest-point transfer, a robe's flank next to a hanging arm keeps the torso's weights."""
    dom = kit.dominant(flesh)
    me = flesh.data
    names = {g.index: g.name for g in flesh.vertex_groups}
    vw = [{names[g.group]: g.weight for g in v.groups} for v in me.vertices]
    co = [v.co.copy() for v in me.vertices]
    trees = []
    for bones in groups:
        polys = [tuple(p.vertices) for p in me.polygons if sum(dom[i] in bones for i in p.vertices) * 2 >= len(p.vertices)]
        trees.append((BVHTree.FromPolygons(co, polys), polys))

    def fn(p):
        best = None
        for tree, polys in trees:
            loc, _, idx, dist = tree.find_nearest(p)
            if loc is not None and (best is None or abs(dist - offset) < best[0]):
                best = (abs(dist - offset), loc, polys[idx])
        if best is None:
            return {"hips": 1.0}
        _, loc, poly = best
        acc, tot = {}, 0.0
        for i in poly:
            wt = 1.0 / max((co[i] - loc).length, 1e-5)
            tot += wt
            for bn, ww in vw[i].items():
                acc[bn] = acc.get(bn, 0.0) + ww * wt
        return {bn: ww / tot for bn, ww in acc.items()}
    return fn


def hang_weights(z_top, z_bottom, side=0.09, legs=0.82, lower=None):
    """Weights for cloth hanging from the hips over both legs: hips at the top, more and more the
    leg on its own side further down (both legs share the middle). With `lower` = (z_knee, share) the
    cloth below the knee also follows the shin by that share."""
    def smooth(t):
        t = max(0.0, min(1.0, t))
        return t * t * (3 - 2 * t)

    def fn(p):
        h = smooth((z_top - p.z) / max(z_top - z_bottom, 1e-6))
        wl = legs * h
        out = {"hips": 1.0 - wl}
        left = 0.5 + 0.5 * max(-1.0, min(1.0, p.x / side))
        for s, share in (("L", left), ("R", 1.0 - left)):
            leg = wl * share
            if lower and p.z < lower[0]:
                f = smooth((lower[0] - p.z) / 0.2) * lower[1]
                out["lower_leg." + s] = leg * f
                leg *= 1 - f
            out["upper_leg." + s] = leg
        return out
    return fn


def skirt(name, z_top, z_bottom, r_top, r_bottom, cy=(0.012, 0.03), gap=(14, 32), folds=9, fold=0.03, nu=48, nv=12,
          thick=0.005, material="primary", span=None):
    """A hanging robe skirt or coat tail: elliptical rings from `z_top` (radii `r_top`, centre y cy[0])
    flaring to `z_bottom` (`r_bottom`, cy[1]), open at the front by `gap` degrees each side (top,
    bottom), with soft pleats. `span` = (a0, a1) degrees (0 front, + toward +X) makes a panel instead."""
    bm = bmesh.new()
    grid = []
    for i in range(nv + 1):
        h = i / nv
        z = z_top + (z_bottom - z_top) * h
        f = 1 - (1 - h) ** 1.6
        rx = r_top[0] + (r_bottom[0] - r_top[0]) * f
        ry = r_top[1] + (r_bottom[1] - r_top[1]) * f
        yc = cy[0] + (cy[1] - cy[0]) * h
        if span:
            a0, a1 = span
        else:
            g = gap[0] + (gap[1] - gap[0]) * h
            a0, a1 = g, 360 - g
        row = []
        for j in range(nu + 1):
            ph = math.radians(a0 + (a1 - a0) * j / nu)
            amp = 1 + fold * h * math.sin(folds * ph)
            row.append(bm.verts.new((rx * math.sin(ph) * amp, yc - ry * math.cos(ph) * amp, z)))
        grid.append(row)
    for i in range(nv):
        for j in range(nu):
            bm.faces.new((grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    me.materials.append(kit.mat(material))
    # Face the normals outward (away from the skirt's axis) before thickening outward.
    me.calc_loop_triangles()
    p0 = me.polygons[len(me.polygons) // 2]
    if p0.normal.dot(Vector((p0.center.x, p0.center.y - (cy[0] + cy[1]) / 2, 0))) < 0:
        me.flip_normals()
    m = o.modifiers.new("thick", "SOLIDIFY")
    m.thickness = thick
    m.offset = -1.0
    m.use_rim = True
    kit.hs._apply(o, m.name)
    for p in me.polygons:
        p.use_smooth = True
    o["bevel"] = 0.0
    o["shaded"] = True
    return o


def skirt_pt(h, deg, z_top, z_bottom, r_top, r_bottom, cy=(0.012, 0.03), out=0.0, fold=0.0, folds=9):
    """A point on the skirt surface at height fraction `h` and angle `deg` (0 front, + toward +X),
    pushed `out` along the ring's outward direction; pass the skirt's `fold` to follow its pleats."""
    f = 1 - (1 - h) ** 1.6
    ph = math.radians(deg)
    amp = 1 + fold * h * math.sin(folds * ph)
    rx = (r_top[0] + (r_bottom[0] - r_top[0]) * f) * amp + out
    ry = (r_top[1] + (r_bottom[1] - r_top[1]) * f) * amp + out
    yc = cy[0] + (cy[1] - cy[0]) * h
    return Vector((rx * math.sin(ph), yc - ry * math.cos(ph), z_top + (z_bottom - z_top) * h))


# --------------------------------------------------------------------------------------- helmet


def sealed_helmet(c, b, name="helmet", slit=True, glow="glow_red", ears=True, vents=True, scale=(1.0, 1.0, 1.0)):
    """The faceless sealed helmet, rigid to the head: a smooth bone shell with a brow plate and a
    faceplate either side of one curved sensor slit, a crest, cheek vents, ear modules and scripture.
    Returns (shell, tree of the shell before cuts)."""
    k = b.k
    hc = b.j("head", 0.45)
    sx, sy, sz = scale
    el = [kit.ellipsoid(hc + Vector((0, 0.006, 0.02 * k)), 0.118 * k, (0.85 * sx, 1.0 * sy, 0.98 * sz)),
          kit.ellipsoid(hc + Vector((0, -0.03, -0.062 * k)), 0.078 * k, (1.06 * sx, 1.0 * sy, 0.9)),
          kit.capsule(hc + Vector((0, 0.03, -0.05 * k)), hc + Vector((0, 0.035, -0.125 * k)), 0.08 * k),
          kit.ellipsoid(hc + Vector((0, -0.074 * sy, 0.036 * k)), 0.05 * k, (1.5 * sx, 0.7, 0.55))]
    shell = kit.meta(name, el, "bone", res=0.0045 * k, target=2600, smooth_iter=6)
    floor = hc.z - 0.138 * k
    kit.cut(shell, kit.block("floor", (0, 0, floor - 0.1), (0.4, 0.4, 0.2), "steel", bevel=0))
    tree = bvh(shell)
    zs = hc.z + 0.004 * k
    vz = [hc.z - (0.058 + i * 0.013) * k for i in range(3)] if vents else []

    # Brow plate above the slit, faceplate below (vents cut through), a keel and a crest, all shelled
    # off the uncut helmet.
    zt = zs + 0.009 * k
    brow = kit.slab("brow_cut", kit.rounded([(-0.094 * k * sx, zt), (0.094 * k * sx, zt), (0.08 * k * sx, zt + 0.045 * k), (0.03 * k, zt + 0.07 * k),
                                              (-0.03 * k, zt + 0.07 * k), (-0.08 * k * sx, zt + 0.045 * k)], 0.012), -0.4, hc.y - 0.035)
    c.rigid(form_plate(shell, brow, "brow", thick=0.0055, offset=-0.0015, bevel=0.0015,
                       keep=lambda p: p.y < hc.y - 0.02 and p.z > zt - 0.02), "head")
    zb = zs - 0.009 * k
    face = kit.slab("face_cut", kit.rounded([(-0.1 * k * sx, zb), (0.1 * k * sx, zb), (0.085 * k * sx, zb - 0.07 * k), (0.05 * k, zb - 0.128 * k),
                                              (-0.05 * k, zb - 0.128 * k), (-0.085 * k * sx, zb - 0.07 * k)], 0.012), -0.4, hc.y - 0.02)
    fp = form_plate(shell, face, "faceplate", thick=0.0055, offset=-0.0015, bevel=0.0015, keep=lambda p: p.y < hc.y - 0.01 and p.z < zb + 0.02)
    ftree = bvh(fp)
    if vz:
        kit.cut(fp, *[ring_band("vent_cut2", ftree, hc, z, s * 16, s * 40, -0.012, 0.03, 0.0045 * k, "steel", n=6) for s in (-1, 1) for z in vz],
                solver="MANIFOLD")
    c.rigid(fp, "head")
    c.rigid(line_band("keel", ftree, hc + Vector((0, 0, -0.016 * k)), hc + Vector((0, 0, -0.118 * k)), (0, 1, 0), -0.001, 0.004, 0.012 * k, "bone", n=8), "head")
    crest = kit.slab("crest_cut", [(-0.016 * k, zt + 0.055 * k), (0.016 * k, zt + 0.055 * k), (0.016 * k, hc.z + 0.3), (-0.016 * k, hc.z + 0.3)], -0.4, 0.4)
    c.rigid(form_plate(shell, crest, "crest", thick=0.0055, offset=0.002, bevel=0.0015, keep=lambda p: abs(p.x) < 0.03 and p.z > zt + 0.03), "head")

    # Then the slit (a glowing bar sunk in a curved groove) and the cheek vents into the shell.
    cuts = []
    if slit:
        cuts.append(ring_band("slit_cut", tree, hc, zs, -56, 56, -0.009, 0.03, 0.012 * k, "steel", n=20))
        c.rigid(ring_band("slit", tree, hc, zs, -55, 55, -0.0085, -0.005, 0.0105 * k, glow, n=20), "head")
    for s in (-1, 1):
        for z in vz:
            cuts.append(ring_band("vent_cut", tree, hc, z, s * 16, s * 40, -0.006, 0.03, 0.0045 * k, "steel", n=6))
            c.rigid(ring_band("vent", tree, hc, z, s * 15, s * 41, -0.0058, -0.0035, 0.0052 * k, "gunmetal", n=6), "head")
    if cuts:
        kit.cut(shell, *cuts, solver="MANIFOLD")
    c.rigid(shell, "head")
    # The cult mark on the brow, scripture on the temples and the back of the helmet.
    c.rigid(project(shell, code_rows(["∴"], 0.016 * k), hc + Vector((0, 0, 0.043 * k)), (0, 1, 0), lift=0.0045, tree=tree), "head")
    for s in (-1, 1):
        c.rigid(project(shell, code_rows(scripture(11 + s, 2, 7), 0.0085 * k), hc + Vector((s * 0.2, 0.045, 0.035 * k)), (-s, 0, 0), tree=tree), "head")
    c.rigid(project(shell, code_rows(["0x7F ∴ 0x7F", "C0DE 9C 1E"], 0.0085 * k), hc + Vector((0, 0.3, -0.03 * k)), (0, -1, 0), tree=tree), "head")
    if ears:
        for s in (-1, 1):
            h = hit(tree, hc + Vector((s * 0.3, 0.012, -0.012 * k)), (-s, 0, 0))
            at = h[0] if h else hc + Vector((s * 0.1 * k, 0.012, -0.012 * k))
            ax = Vector((s, 0, 0))
            drum = kit.cyl("ear", at - ax * 0.008, at + ax * 0.014, 0.025 * k, "gunmetal", segs=20, bevel=0.0012, bsegs=1)
            kit.cut(drum, *[kit.block("ear_slot", at + ax * 0.014 + Vector((0, dy, 0)), (0.008, 0.004, 0.026 * k), "steel", bevel=0) for dy in (-0.009, 0.0, 0.009)])
            c.rigid(drum, "head")
            c.rigid(ring("ear_collar", at + ax * 0.004, ax, 0.031 * k, 0.0245 * k, 0.012, "bone", segs=20), "head")
            for ang in (45, 135, 225, 315):
                r = math.radians(ang)
                c.rigid(screw(at + ax * 0.0095 + Vector((0, math.cos(r), math.sin(r))) * 0.028 * k, ax, r=0.0022), "head")
    return shell, tree


# ------------------------------------------------------------------------------- Regime armour


def J(b, x, z):
    """A front-view point given for the 1.80 m reference build, scaled to build `b`."""
    return (x * b.width, z * b.k)


def gloves(c, b, parts, material="rubber", guard="bone"):
    """Recolour the gripping hands as gloves and add a knuckle plate on each."""
    k = b.k
    hands = parts["hands"]
    hands.data.materials[0] = kit.mat(material)
    c.add(hands, kit.HAND_BONES)
    for s, sx in (("L", 1), ("R", -1)):
        hb = Vector(b.all["hand." + s][0])
        down = (Vector(b.all["hand." + s][1]) - hb).normalized()
        g = kit.block("knuckle", (0, 0, 0), (0.016, 0.07, 0.024), guard, bevel=0.003)
        g.data.transform(Matrix.Translation(hb + down * 0.088 * k + Vector((sx * 0.013, -0.002, 0))))
        c.rigid(g, "hand." + s)


def piping(c, b, flesh, legs=True, arms=True, material="secondary"):
    """Undersuit piping down the outside of the arms and legs."""
    ftree = bvh(flesh)
    for s, sx in (("L", 1), ("R", -1)):
        if arms:
            pts = [b.j("upper_arm." + s, t) for t in (0.3, 0.5, 0.7, 0.9, 1.0)] + [b.j("forearm." + s, t) for t in (0.1, 0.3, 0.5, 0.7, 0.85)]
            c.add(seam("piping", ftree, pts, (sx, 0.15, 0), material=material))
        if legs:
            pts = [b.j("upper_leg." + s, t) for t in (0.05, 0.2, 0.4, 0.6, 0.8, 1.0)] + [b.j("lower_leg." + s, t) for t in (0.15, 0.35, 0.55, 0.75)]
            c.add(seam("piping", ftree, pts, (sx, 0.0, 0), material=material))


def neck_seal(c, b, n=5, r0=0.058, step=0.0035):
    """Ribbed rubber bellows from the collar up into a sealed helmet."""
    for i in range(n):
        z = b.j("neck", 0.15 + i * 0.95 / n).z
        r = r0 + i * step
        c.add(band("bellows", Vector((0, 0.006, z)), (r * b.k, (r - 0.002) * b.k), 0.012, 0.009, "rubber", segs=16), ["neck", "chest", "head"])


CHEST_OUTLINE = [(-0.132, 1.165), (0.132, 1.165), (0.145, 1.25), (0.142, 1.33), (0.112, 1.393), (0.064, 1.418),
                 (0.038, 1.392), (0.0, 1.378), (-0.038, 1.392), (-0.064, 1.418), (-0.112, 1.393), (-0.142, 1.33), (-0.145, 1.25)]
BACK_OUTLINE = [(-0.135, 1.17), (0.135, 1.17), (0.148, 1.33), (0.1, 1.415), (-0.1, 1.415), (-0.148, 1.33)]


def cuirass(c, b, back=True, seed=3, rows=4, cols=9, grow=1.0, outline=CHEST_OUTLINE, vents=True, sigil_z=1.212, vent_z=1.19, seam_z=1.262):
    """Bone breast and back plates shelled off one ellipsoid form round the ribcage, with gunmetal
    seams and vents, scripture on both breasts, the cult mark and screws. Returns (chest, back)."""
    k, w = b.k, b.width
    form = ell_form(b.j("chest", 0.36), (0.172 * w * grow, 0.128 * b.bulk * grow, 0.205 * k), rot=(0, 0, 0), u=48, v=28)
    chest = form_plate(form, kit.slab("chest_cut", kit.rounded([J(b, x, z) for x, z in outline], 0.016), -0.4, -0.02), "chest_plate",
                       thick=0.014, keep=lambda p: p.y < -0.01, bevel=0.004)
    ct = bvh(chest)
    c.rigid(chest, "chest")
    fix(c, ring_band("seam", ct, (0, 0.0), seam_z * k, -58, 58, -0.0006, 0.0011, 0.0035, "gunmetal", n=20), "chest")
    for s in (-1, 1):
        if vents:
            for i in range(4):
                fix(c, ring_band("vent", ct, (0, 0.0), (vent_z + i * 0.015) * k, s * 30, s * 50, -0.0006, 0.0016, 0.006, "gunmetal", n=5), "chest")
        c.rigid(project(chest, code_rows(scripture(seed + s, rows, cols), 0.0105 * k), (s * 0.07 * w, -0.3, 1.326 * k), (0, 1, 0), tree=ct), "chest")
    c.rigid(project(chest, sigil(0.028) + code_rows(["∴"], 0.03), (0, -0.3, sigil_z * k), (0, 1, 0), tree=ct), "chest")
    for x, z in ((-0.11, 1.19), (0.11, 1.19), (-0.098, 1.372), (0.098, 1.372)):
        fix(c, screw_on(ct, (x * w, -0.3, z * k), (0, 1, 0), r=0.0045), "chest")
    bp = None
    if back:
        bp = form_plate(form, kit.slab("back_cut", kit.rounded([J(b, x, z) for x, z in BACK_OUTLINE], 0.02), 0.02, 0.4), "back_plate",
                        thick=0.012, keep=lambda p: p.y > 0.01, bevel=0.004)
        bt = bvh(bp)
        c.rigid(bp, "chest")
        c.rigid(ring_band("seam", bt, (0, 0.0), 1.2 * k, 122, 238, -0.0006, 0.0011, 0.0035, "gunmetal", n=20), "chest")
        c.rigid(project(bp, tick_rows(seed + 18, 2, 0.16, 0.006), (0, 0.3, 1.185 * k), (0, -1, 0), tree=bt), "chest")
    done(form)
    return chest, bp


def side_straps(c, b, zs=(1.2, 1.3)):
    """Red straps with gunmetal buckles tying the breast and back plates together under the arms."""
    for s in (-1, 1):
        for z in zs:
            x = s * 0.16 * b.width
            c.rigid(kit.strap("side_strap", [(x * 0.95, -0.06, z * b.k), (x * 1.02, 0.0, z * b.k), (x * 0.95, 0.06, z * b.k)], 0.022, 0.006, "accent"), "chest")
            c.rigid(kit.block("strap_buckle", (x * 1.04, 0.0, z * b.k), (0.008, 0.026, 0.03), "gunmetal", bevel=0.002), "chest")


def abdomen_lames(c, b, seed=31):
    """Two bone lames over the belly, tucked under the breastplate, ticked with code."""
    k = b.k
    for i, (z0, z1, r) in enumerate(((1.112, 1.162, 0.106), (1.066, 1.114, 0.103))):
        lame = arc_plate("abdomen_lame", (0, 0.0, z0 * k), (0, 0.0, z1 * k), (0, -1, 0), r * b.bulk, (r - 0.006) * b.bulk, (70, 72), 0.01,
                         squash=1.22 * b.width, segs=16, rings=1)
        c.rigid(lame, "spine")
        c.rigid(project(lame, tick_rows(seed + i, 1, 0.15, 0.007), (0, -0.3, (z0 + z1) / 2 * k), (0, 1, 0)), "spine")


def pauldron(c, b, s, sx, grow=1.0, seed=41, lames=((0.12, 0.3, 0.074), (0.27, 0.45, 0.07)), rows=3, trim="gunmetal", rib=True):
    """A bone dome over the shoulder with a sloped hem, gunmetal trim, a raised rib and scripture, and
    shingled lames below it on the upper arm. `grow` scales it out (for a pauldron over a robe)."""
    k, w = b.k, b.width
    ua = "upper_arm." + s
    sh = b.j(ua, 0.0)
    dc = sh + Vector((sx * 0.015 * grow, 0.0, 0.012 + 0.03 * (grow - 1))) * k
    form = ell_form(dc, (0.078 * k * grow, 0.088 * k * grow, 0.068 * k * grow), rot=(0, 0, 0), u=28, v=16)

    def dz(x):  # the hem slopes down outward
        return sh.z - 0.06 * k - 0.4 * (abs(x) - abs(sh.x))
    hem = [(sx * 0.11 * w, dz(0.11 * w) + 0.05), (sx * 0.11 * w, sh.z + 0.3), (sx * 0.4, sh.z + 0.3), (sx * 0.4, dz(0.4))]
    dome = form_plate(form, kit.slab("dome_cut", hem if sx > 0 else hem[::-1], -0.4, 0.4), "pauldron", thick=0.011,
                      keep=lambda p: p.x * sx > 0.1 * w and p.z > sh.z - 0.09 * k, bevel=0.0035)
    done(form)
    c.rigid(dome, ua)
    dt = bvh(dome)
    c.rigid(project(dome, code_rows(scripture(seed + sx, rows, 7), 0.0085 * k), dc + Vector((sx * 0.3, 0, 0.02 * grow)), (-sx, 0, 0), tree=dt), ua)
    if trim:
        c.rigid(ring_band("pauldron_trim", dt, dc, sh.z + (0.03 + 0.035 * (grow - 1)) * k, sx * 35, sx * 145, -0.0006, 0.0014, 0.005, trim, n=12), ua)
    if rib:
        c.rigid(line_band("pauldron_rib", dt, dc + Vector((sx * 0.012, -0.075 * grow, 0.3)), dc + Vector((sx * 0.012, 0.075 * grow, 0.3)), (0, 0, -1),
                          -0.001, 0.0055, 0.012, "bone", n=10), ua)
    lame = None
    for t0, t1, r in lames:
        lame = arc_plate("pauldron_lame", b.j(ua, t0), b.j(ua, t1), Vector((sx, 0, 0.1)), r * k * grow, (r - 0.004) * k * grow, 78, 0.009, segs=14, rings=2, flare=0.006)
        c.rigid(lame, ua)
    if lame is not None:
        c.rigid(project(lame, tick_rows(seed + 4 + sx, 2, 0.07, 0.0055), b.j(ua, 0.36) + Vector((sx * 0.3, 0, 0)), (-sx, 0, 0)), ua)
    return dome


def vambrace(c, b, s, sx, seed=51, straps=True, t=(0.1, 0.82), r=(0.051, 0.044), wrist="gunmetal"):
    """A bone vambrace with a code column and end screws, a wrist ring, red straps."""
    k = b.k
    fa = "forearm." + s
    out = Vector((sx, -0.55, 0.0))
    a0, a1 = b.j(fa, t[0]), b.j(fa, t[1])
    va = arc_plate("vambrace", a0, a1, out, r[0] * k, r[1] * k, (82, 70), 0.009, bulge=0.004, segs=14, rings=4)
    c.rigid(va, fa)
    vt = bvh(va)
    ax = (a1 - a0).normalized()
    ow = (out - ax * out.dot(ax)).normalized()
    c.rigid(project(va, code_rows(scripture(seed + sx, 2, 4), 0.0075 * k) + [(x, y - 0.03, m) for x, y, m in tick_rows(seed + 4 + sx, 4, 0.03, 0.005)],
                    a0.lerp(a1, 0.5) + ow * 0.3, -ow, up=-ax, tree=vt), fa)
    for tt in (0.06, 0.94):
        fix(c, screw_on(vt, a0.lerp(a1, tt) + ow * 0.3, -ow, r=0.0035), fa)
    if wrist:
        c.rigid(band("wrist_ring", b.j(fa, 0.92), (0.045 * k, 0.04 * k), 0.022, 0.01, wrist, axis=b.j(fa, 1.0) - b.j(fa, 0.8)), fa)
    if straps:
        for tt in (0.3, 0.66):
            c.add(band("vambrace_strap", b.j(fa, tt), (0.046 * k, 0.042 * k), 0.016, 0.006, "accent", axis=b.j(fa, 1.0) - b.j(fa, 0.0)), [fa])
    return va


def tassets(c, b, s, sx, seed=61, spans=((0.03, 0.25, 0.094), (0.22, 0.46, 0.088)), strap=True):
    """Shingled bone plates on the front-outer thigh, code on the lower one, a red thigh strap."""
    k = b.k
    ul = "upper_leg." + s
    tout = Vector((sx * 0.7, -1, 0))
    tas = None
    for t0, t1, r in spans:
        tas = arc_plate("tasset", b.j(ul, t0), b.j(ul, t1), tout, r * k * b.bulk, (r - 0.006) * k * b.bulk, (52, 46), 0.009, segs=12, rings=2, flare=0.006)
        c.rigid(tas, ul)
    t0, t1 = spans[-1][:2]
    tp = arc_point(b.j(ul, t0), b.j(ul, t1), tout, 0.3, 0.5, 0)
    c.rigid(project(tas, code_rows(scripture(seed + sx, 2, 7), 0.0082 * k), tp, b.j(ul, (t0 + t1) / 2) - tp), ul)
    if strap:
        c.add(band("thigh_strap", b.j(ul, 0.52), (0.077 * k * b.bulk, 0.073 * k * b.bulk), 0.022, 0.007, "accent", axis=b.j(ul, 1) - b.j(ul, 0)), [ul])


def knee_cop(c, b, s):
    """A bone dome over the knee with a gunmetal hex boss."""
    k = b.k
    ll = "lower_leg." + s
    knee = b.j(ll, 0.0)
    kf = ell_form(knee + Vector((0, -0.03, 0.008)), (0.056 * k, 0.044 * k, 0.064 * k), u=24, v=16)
    kc = form_plate(kf, None, "knee", thick=0.011, keep=lambda p: p.y < knee.y - 0.046, bevel=0.003)
    done(kf)
    c.rigid(kc, ll)
    h = hit(bvh(kc), knee + Vector((0, -0.3, 0.006)), (0, 1, 0))
    if h:
        c.rigid(kit.cyl("knee_boss", h[0] - h[1] * 0.003, h[0] + h[1] * 0.006, 0.014, "gunmetal", segs=6, bevel=0.0015, bsegs=1), ll)


def greave(c, b, s, sx, seed=71, t=(0.1, 0.74), strap=True):
    """A bulging bone shin plate with a raised keel, a code column and screws; a red calf strap."""
    k = b.k
    ll = "lower_leg." + s
    gout = Vector((sx * 0.2, -1, 0))
    g0, g1 = b.j(ll, t[0]), b.j(ll, t[1])
    gr = arc_plate("greave", g0, g1, gout, 0.056 * k, 0.046 * k, (70, 62), 0.011, bulge=0.008, segs=14, rings=5)
    c.rigid(gr, ll)
    keel = c.rigid(arc_plate("greave_keel", b.j(ll, t[0] + 0.02), b.j(ll, t[1] - 0.04), gout, 0.066 * k, 0.056 * k, 3.5, 0.004, bulge=0.008, segs=1, rings=5, bevel=0.001), ll)
    gt = bvh(gr)
    gp = arc_point(g0, g1, gout, 0.3, 0.5, -sx * 28)
    c.rigid(project(gr, code_rows(scripture(seed + sx, 2, 3), 0.0075 * k) + [(x, y - 0.035, m) for x, y, m in tick_rows(seed + 4 + sx, 5, 0.022, 0.005)],
                    gp, b.j(ll, (t[0] + t[1]) / 2) - gp, tree=gt), ll)
    for tt in (0.06, 0.95):
        p = arc_point(g0, g1, gout, 0.3, tt, 0)
        fix(c, screw_on(gt, p, b.j(ll, t[0] + (t[1] - t[0]) * tt) - p, r=0.0035), ll)
    if strap:
        # Hug the calf and the plate on it instead of a fixed ellipse, so it never stands off at the sides.
        sp = b.j(ll, 0.6)
        st = ring_band("calf_strap", [bvh(c.skin_source), gt, bvh(keel)], sp, sp.z, 0, 360, 0.0004, 0.0065, 0.02, "accent", n=28, reach=0.16)
        if st is None:
            st = band("calf_strap", sp, (0.067 * k, 0.071 * k), 0.02, 0.007, "accent", axis=(0, 0, 1))
        c.add(st, [ll])
    return gr


def hug_tube(name, tree, a, b_, r0, r1, n=24, rings=6, reach=0.12, material="black", bevel=0.0025, smooth=1):
    """A closed sleeve following the surface round the (near vertical) axis a -> b_, from `r0` to `r1`
    off it: boot shafts, cuffs. Rays miss nothing at these heights; a miss takes the ring's mean."""
    a, b_ = Vector(a), Vector(b_)
    angles = [360.0 * i / n for i in range(n)]
    profs = []
    for ri in range(rings + 1):
        p = a.lerp(b_, ri / rings)
        prof = contour(tree, p, p.z, angles, reach)
        known = [r for _, r in prof if r is not None]
        if not known:
            return None
        rs = [r if r is not None else sum(known) / len(known) for _, r in prof]
        for _ in range(smooth):
            rs = [(rs[i - 1] + 2 * rs[i] + rs[(i + 1) % n]) / 4 for i in range(n)]
        profs.append((p, [d for d, _ in prof], rs))
    # A straight-walled sleeve: never narrower than what lies above it, and no waist below a straight
    # taper from bottom to top (so an ankle bulge does not make a pot).
    for i in range(n):
        col = [pr[2][i] for pr in profs]
        for ri in range(rings - 1, -1, -1):
            col[ri] = max(col[ri], col[ri + 1])
        for ri in range(rings + 1):
            profs[ri][2][i] = max(col[ri], col[0] + (col[-1] - col[0]) * ri / rings)
    bm = bmesh.new()
    O, I = [], []
    for p, ds, rs in profs:
        cc = Vector((p.x, p.y))
        O.append([bm.verts.new((*(cc + d.to_2d() * (r + r1)), p.z)) for d, r in zip(ds, rs)])
        I.append([bm.verts.new((*(cc + d.to_2d() * (r + r0)), p.z)) for d, r in zip(ds, rs)])
    for ri in range(rings):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((O[ri][i], O[ri][j], O[ri + 1][j], O[ri + 1][i]))
            bm.faces.new((I[ri][j], I[ri][i], I[ri + 1][i], I[ri + 1][j]))
    for ri in (0, rings):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((O[ri][j], O[ri][i], I[ri][i], I[ri][j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = kit.hs._obj(name, bm, material, bevel, 1)
    for f in o.data.polygons:
        f.use_smooth = True
    o["shaded"] = False
    return o


def boot(c, b, flesh, s, sx, top=0.19, material="black", toe="bone"):
    """A black boot: the foot shelled off the body and trimmed low, a sleeve-built shaft hugging the
    ankle with a rolled rim, a bone toe cap, a treaded rubber sole and a red ankle strap with a buckle."""
    k = b.k
    ll, ft = "lower_leg." + s, "foot." + s
    f0 = b.j(ft, 0.0)
    top = top * k
    low = 0.125 * k
    bt = kit.shell(flesh, lambda p: p.z < low + 0.03 and p.x * sx > 0, "boot", material, offset=0.012, thick=0.006,
                   bones={ft, ll}, inside=[kit.block("boot_cut", (f0.x, -0.05, low / 2), (0.3, 0.6, low), "steel", bevel=0)])
    c.add(bt, [ft, ll])
    ftree = bvh(flesh)
    z0 = f0.z + 0.004 * k
    sh = hug_tube("boot_shaft", ftree, Vector((f0.x, f0.y, z0)), b.j(ll, (b.j(ll, 0.0).z - top) / (b.j(ll, 0.0).z - b.j(ll, 1.0).z)),
                  0.013, 0.022, n=24, rings=5, material=material)
    if sh is not None:
        c.add(sh, [ll, ft])
        st = bvh(sh)
        rim = ring_band("boot_rim", st, Vector((f0.x, f0.y)), top - 0.006, 0, 360, -0.002, 0.003, 0.012, "rubber", n=24, reach=0.15)
        if rim is not None:
            c.add(rim, [ll])
        az = b.j(ll, 0.86).z
        strap = ring_band("ankle_strap", st, Vector((f0.x, f0.y)), az, 0, 360, 0.0004, 0.006, 0.022, "accent", n=24, reach=0.15)
        if strap is not None:
            c.add(strap, [ll, ft])
            h = hit(bvh(strap), Vector((f0.x + sx * 0.2, f0.y, az)), (-sx, 0, 0))
            if h:
                bk = kit.block("ankle_buckle", (0, 0, 0), (0.006, 0.028, 0.03), "gunmetal", bevel=0.0015)
                bk.data.transform(Matrix.Translation(h[0] + h[1] * 0.002))
                c.rigid(bk, ll)
                c.rigid(screw(h[0] + h[1] * 0.005, h[1], r=0.0035), ll)
    toe_c = b.j(ft, 1.0) + Vector((0, -0.016, -0.004))
    tf = ell_form(toe_c, (0.05 * k, 0.052 * k, 0.04 * k), u=24, v=16)
    cap = form_plate(tf, kit.block("toe_cut", (f0.x, toe_c.y - 0.1, toe_c.z + 0.075), (0.2, 0.2, 0.12), "steel", bevel=0), "toecap", thick=0.007,
                     keep=lambda p: p.y < toe_c.y + 0.012, bevel=0.003)
    done(tf)
    c.rigid(cap, ft)
    sole = kit.plan("sole", kit.rounded([(f0.x - 0.05 * k, 0.09 * k), (f0.x + 0.05 * k, 0.09 * k), (f0.x + 0.058 * k, -0.235 * k), (f0.x - 0.048 * k, -0.235 * k)], 0.04),
                    0.026, "rubber", z=0.013, bevel=0.002, segs=1)
    kit.cut(sole, *kit.slots("tread", -0.21 * k, 0.065 * k, 9, -0.002, 0.006, f0.x - 0.07, f0.x + 0.07))
    c.rigid(sole, ft)


# ----------------------------------------------------------------------------------------- build


def build():
    b = kit.Build(height=1.80, width=1.0, bulk=1.0)
    k = b.k
    c = kit.begin("acolyte", b)
    parts = kit.body(b, skin="primary", head=False)
    flesh = c.flesh(parts["body"])
    hc = b.j("head", 0.45)
    piping(c, b, flesh)
    gloves(c, b, parts)
    _, htree = sealed_helmet(c, b)
    neck_seal(c, b)
    chest, _ = cuirass(c, b)
    ct = bvh(chest)
    side_straps(c, b)

    # Uplink node on the back plate: vented bone casing, gunmetal data drum with a red lens, antenna.
    ny, nz = 0.168 * b.bulk, 1.285 * k
    node = kit.block("node", (0, ny, nz), (0.15, 0.07, 0.2 * k), "bone", bevel=0.008, taper=(0.86, 0.86))
    kit.cut(node, *[kit.block("node_vent", (s * 0.075, ny, nz - 0.06 + i * 0.024), (0.016, 0.05, 0.007), "steel", bevel=0)
                    for s in (-1, 1) for i in range(5)])
    c.rigid(node, "chest")
    c.rigid(kit.block("node_band", (0, ny, nz + 0.075 * k), (0.135, 0.074, 0.018), "gunmetal", bevel=0.002, taper=(0.98, 0.98)), "chest")
    fy = ny + 0.035
    core = kit.cyl("core", (0, fy - 0.01, nz), (0, fy + 0.012, nz), 0.043, "gunmetal", segs=24, bevel=0.0015, bsegs=1)
    kit.cut(core, *[kit.block("core_fin", (math.cos(a) * 0.03, fy + 0.014, nz + math.sin(a) * 0.03), (0.006, 0.01, 0.022), "steel", bevel=0)
                    for a in [math.radians(30 + 60 * i) for i in range(6)]])
    c.rigid(core, "chest")
    c.rigid(ring("core_ring", (0, fy + 0.004, nz), (0, 1, 0), 0.05, 0.042, 0.014, "bone", segs=24), "chest")
    c.rigid(kit.cyl("lens", (0, fy + 0.006, nz), (0, fy + 0.0145, nz), 0.012, "glow_red", segs=16, bevel=0), "chest")
    c.rigid(ring("lens_bezel", (0, fy + 0.012, nz), (0, 1, 0), 0.017, 0.0115, 0.006, "gunmetal", segs=16), "chest")
    nt = bvh(node)
    c.rigid(project(node, code_rows(["UPLINK ∴ 07"], 0.011), (0, 0.4, nz - 0.074 * k), (0, -1, 0), tree=nt), "chest")
    for x in (-0.052, 0.052):
        for z in (nz - 0.08 * k, nz + 0.05 * k):
            fix(c, screw_on(nt, (x, 0.4, z), (0, -1, 0), r=0.004), "chest")
    c.rigid(antenna("antenna", (0.05, ny + 0.01, nz + 0.1 * k), (0.068, ny + 0.03, nz + 0.33 * k), r=0.005, bars=((0.62, 0.016), (0.8, 0.011))), "chest")
    # Sockets and cables: helmet -> node top, node -> over the shoulders onto the cuirass, node -> belt.
    for s in (-1, 1):
        c.rigid(socket("node_port", (s * 0.045, ny + 0.012, nz + 0.1 * k), (0, 0, 1), r=0.009), "chest")
        h = hit(htree, hc + Vector((s * 0.035, 0.3, -0.105 * k)), (0, -1, 0))
        if h:
            c.rigid(socket("helmet_port", h[0], h[1], r=0.0085), "head")
            top = Vector((s * 0.045, ny + 0.012, nz + 0.112 * k))
            p0 = h[0] + h[1] * 0.01
            c.add(cable("neck_cable", [p0, p0 + Vector((0, 0.03, -0.035)), top + Vector((s * 0.004, 0.012, 0.045)), top], 0.0055), ["head", "neck", "chest"])
        start = Vector((s * 0.066, ny - 0.01, nz + 0.07 * k))
        cp = hit(ct, (s * 0.082 * b.width, -0.3, 1.388 * k), (0, 1, 0))
        if cp:
            c.rigid(socket("chest_port", cp[0], cp[1], r=0.0075), "chest")
            end = cp[0] + cp[1] * 0.01
            c.rigid(cable("shoulder_cable", [start, Vector((s * 0.085, 0.12, 1.42 * k)), Vector((s * 0.088, 0.02, 1.458 * k)),
                                              end + Vector((0, -0.01, 0.04)), end], 0.0048), "chest")
        low = Vector((s * 0.05, ny - 0.005, nz - 0.1 * k))
        c.add(cable("belt_cable", [low, low + Vector((s * 0.01, 0.01, -0.06)), Vector((s * 0.075, 0.15, 1.04 * k)), Vector((s * 0.085, 0.135, 0.995 * k))], 0.0048),
              ["chest", "spine", "hips"])

    # Waist: a quilted wrap, two abdomen lames tucked under the cuirass, the belt, pouches, a canister.
    c.add(kit.shell(flesh, lambda p: 0.965 * k < p.z < 1.19 * k, "waist", "secondary", offset=0.012, thick=0.004, smooth_iter=2, bones=TORSO))
    abdomen_lames(c, b)
    c.add(band("belt", Vector((0, 0.0, 0.99 * k)), (0.168 * b.width, 0.13), 0.045, 0.012, "accent", segs=20), ["hips", "spine"])
    buckle = c.rigid(kit.block("buckle", (0, -0.139, 0.99 * k), (0.06, 0.012, 0.042), "bone", bevel=0.003), "hips")
    c.rigid(project(buckle, code_rows(["∴"], 0.026), (0, -0.3, 0.99 * k), (0, 1, 0)), "hips")
    for s in (-1, 1):
        x = s * 0.12 * b.width
        pouch = kit.block("pouch", (x, -0.115, 0.95 * k), (0.06, 0.04, 0.08), "secondary", bevel=0.006)
        flap = kit.block("pouch_flap", (x, -0.118, 0.985 * k), (0.064, 0.046, 0.022), "secondary", bevel=0.005)
        snap = kit.cyl("snap", (x, -0.142, 0.982 * k), (x, -0.145, 0.982 * k), 0.006, "gunmetal", segs=10, bevel=0)
        c.rigid(kit.join([pouch, flap, snap], "pouch"), "hips")
    c.rigid(kit.cyl("canister", (-0.07, 0.15, 0.94 * k), (0.07, 0.15, 0.94 * k), 0.032, "gunmetal", segs=20, bevel=0.0015, bsegs=1), "hips")
    for x in (-0.045, 0.045):
        c.rigid(band("can_band", Vector((x, 0.15, 0.94 * k)), (0.035, 0.035), 0.01, 0.005, "bone", axis=(1, 0, 0), segs=16), "hips")

    for s, sx in (("L", 1), ("R", -1)):
        pauldron(c, b, s, sx)
        vambrace(c, b, s, sx)
        tassets(c, b, s, sx)
        knee_cop(c, b, s)
        greave(c, b, s, sx)
        boot(c, b, flesh, s, sx)
    c.cover(FEET | SHINS, lambda p: p.z < 0.16 * k)
    return c


SPEC = {"build": build, "faction": "regime", "budget": (25000, 75000), "loadout": "rifle",
        "colors": {"primary": "#1a1a1d", "secondary": "#2a2a2e", "accent": "#7a1010"}}
