"""Acolyte, Regime: the faceless grunt of the Algorithm's cult, an elite black-clad trooper. A black
combat shirt and ripstop trousers draped by the cloth simulation, black gloves and tactical boots; a
black plate carrier with bone-white hard plates etched with black code scripture front and back, rifle
magazine pouches on the placard, red padded shoulder straps; bone shoulder caps over a lame, thigh
guards, knee caps and shin guards strapped over the cloth; a sealed bone helmet with a respirator
faceplate and one glowing red sensor slit over a knit hood; an uplink radio in a bone housing on the
back plate with a whip antenna and a fold-up SATCOM panel, cabled into the helmet.

Built on the realistic layer (real.py) like the Contractor: a real body, its head dropped under the
helmet and hood; every hard plate is laid on an envelope of the cloth or head it sits on and bakes its
scripture, screws and panel lines from detail meshes.

Tints: primary = combat shirt and hood, secondary = trousers, accent = straps and pull tabs.

The first half of this module holds the Regime's code-built helpers (scripture projected onto curved
plates, contour-following bands, analytic arc and ellipsoid plates, cheap screws, sockets, antennas,
the old sealed helmet) that zealot.py and choir.py import; the Acolyte uses `project` and the
scripture generators from it.
"""

import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

import kit
import real
import surfaces
from chars import contractor as pmc
from kit import FOREARMS, THIGHS, UPPER_ARMS

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


# ===================================================================== the realistic Acolyte
# Built on the realistic layer (real.py) like the Contractor: a real body under a draped black combat
# shirt and trousers, gloves and tactical boots; then a black plate carrier whose bone-white hard
# plates, shoulder caps and leg guards are fitted to the cloth they sit on (envelopes of that surface,
# smoothed the way a moulded plate bridges the folds), and a sealed helmet fitted the same way round
# the head. The hard plates bake their etched scripture, vents and panel lines from detail meshes
# that cost no game triangles.

kit.hs.PALETTE.update({
    "regime_bone": ((0.74, 0.715, 0.655), (0.52, 0.49, 0.44), 0.0, 0.44, 0.3, 0),    # bone-white hard plate
    "regime_nylon": ((0.030, 0.030, 0.033), (0.14, 0.14, 0.145), 0.0, 0.8, 0.3, 0),  # black carrier cordura
    "regime_pad": ((0.022, 0.022, 0.024), (0.08, 0.08, 0.08), 0.0, 0.92, 0.1, 0),    # helmet liner foam
})


def bone_plate(g, pal):
    """The Regime's hard plate: a moulded composite under a satin bone-white coat. A faint orange peel
    in the coat, slow mottling from the layup, and fine scratches through to the darker composite (the
    edge chips and cavity dirt come from the shared wear). Nothing finer than a few texels, so the coat
    stays clean at game resolution instead of breaking into speckle."""
    base, worn = pal[0], pal[1]
    pos = g.geo("Position")
    x, y, z = g.xyz(pos)
    peel = g.noise(pos, 140.0, detail=2, rough=0.45)
    mottle = g.noise(pos, 9.0, detail=3)
    shade = g.remap(mottle, 0.3, 0.7, 0.955, 1.03, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, g.mul(shade, 0.99)), "MULTIPLY")
    a = g.noise(g.combine(x, y, g.mul(z, 0.07)), 55.0, detail=2)
    b = g.noise(g.combine(g.mul(x, 0.07), g.add(y, 3.1), g.add(z, 1.7)), 55.0, detail=2)
    lines = g.math("MAXIMUM", g.remap(g.math("ABSOLUTE", g.sub(a, 0.5)), 0.012, 0.0), g.remap(g.math("ABSOLUTE", g.sub(b, 0.5)), 0.012, 0.0))
    scr = g.mul(lines, g.remap(g.noise(pos, 5.0, detail=2), 0.5, 0.65))
    col = g.mix(g.mul(scr, 0.45), col, worn)
    rough = g.lerp(peel, pal[3] - 0.04, pal[3] + 0.04)
    rough = g.lerp(scr, rough, 0.62)
    h = g.sub(g.add(g.mul(peel, 0.5), 0.25), g.mul(scr, 0.5))
    return dict(color=col, rough=rough, metal=0.0, height=h, bump=0.00006)


surfaces.RECIPES.setdefault("boneplate", bone_plate)
surfaces.RECIPE.setdefault("regime_bone", "boneplate")
surfaces.RECIPE.setdefault("regime_nylon", "cordura")
surfaces.RECIPE.setdefault("regime_pad", "canvas")

BONE, NYLON = "regime_bone", "regime_nylon"
FAST = bool(os.environ.get("ACOLYTE_FAST"))  # look-dev: skip the cloth simulation


def _sm(x, a, b):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def sheet(name, rows, material, thick, centre, closed=False, pole=None, bevel=0.0015, inner=None, segs=1):
    """A plate from rows of points on its OUTER surface: faces between the rows (closed round, or
    fanned into a `pole`), turned to face away from `centre`, thickened inward by `thick`. `inner` is
    the material of the inside surface (a helmet's liner)."""
    bm = bmesh.new()
    vrows = [[bm.verts.new(Vector(p)) for p in row] for row in rows]
    n = len(rows[0])
    for r0, r1 in zip(vrows, vrows[1:]):
        for j in range(n if closed else n - 1):
            k = (j + 1) % n
            bm.faces.new((r0[j], r0[k], r1[k], r1[j]))
    if pole is not None:
        top = bm.verts.new(Vector(pole))
        for j in range(n if closed else n - 1):
            k = (j + 1) % n
            bm.faces.new((vrows[-1][j], vrows[-1][k], top))
    bm.normal_update()
    c = Vector(centre)
    if sum(f.normal.dot(f.calc_center_median() - c) * f.calc_area() for f in bm.faces) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    o = kit.hs._obj(name, bm, material, 0.0)
    if inner:
        o.data.materials.append(kit.mat(inner))
    if thick:
        sm = o.modifiers.new("thick", "SOLIDIFY")
        sm.thickness = thick
        sm.offset = -1.0
        sm.use_even_offset = True
        sm.use_rim = True
        sm.material_offset = 1 if inner else 0
        kit.hs._apply(o, sm.name)
        # Inner faces (a liner, a plate's back) get few texels: see Armour.finish.
        me = o.data
        flags = np.array([int(p.normal.dot((p.center - c).normalized()) < -0.3) for p in me.polygons], dtype=np.int32)
        me.attributes.new("inner", "INT", "FACE").data.foreach_set("value", flags)
    o["bevel"] = bevel
    o["segs"] = segs
    o["shaded"] = False
    return o


def _trees(objs):
    return [o if isinstance(o, BVHTree) else pmc.tree(o) for o in objs]


class Env:
    """The outer envelope of surfaces seen from a centre point O: r(lat, lon), the distance to the
    outermost surface along each direction, max-filtered over `spread` degrees and blurred over `blur`
    so a plate laid on it bridges folds, noses and ears like a moulded shell, and never closer than
    `floor` to the raw surface. Directions: latitude from the equator to `Z` (90 = pole), longitude
    from `F` (0) toward Z x F (+90)."""

    def __init__(self, objs, O, Z=(0, 0, 1), F=(0, -1, 0), reach=0.3, lat=(-90.0, 90.0), dlat=4.0, dlon=5.0,
                 spread=12.0, blur=8.0, floor=0.004):
        self.O = Vector(O)
        Z = Vector(Z).normalized()
        F = Vector(F)
        F = (F - Z * F.dot(Z)).normalized()
        self.Z, self.F, self.S = Z, F, Z.cross(F)
        self.lats = np.arange(lat[0], lat[1] + 1e-6, dlat)
        self.lons = np.arange(-180.0, 180.0 - 1e-6, dlon)
        self.dlat, self.dlon = dlat, dlon
        D = np.array([tuple(self.dir(la, lo)) for la in self.lats for lo in self.lons], dtype=np.float32)
        trees = _trees(objs)
        r = np.full(len(D), np.nan, dtype=np.float32)
        for i, d in enumerate(D):
            v = Vector(tuple(float(x) for x in d))
            best = None
            for t in trees:
                loc, _, _, _ = t.ray_cast(self.O + v * reach, -v, reach)
                if loc is not None:
                    dd = (loc - self.O).length
                    best = dd if best is None else max(best, dd)
            if best is not None:
                r[i] = best
        self.raw = r.reshape(len(self.lats), len(self.lons))
        ok = ~np.isnan(r)
        ang = np.degrees(np.arccos(np.clip(D @ D[ok].T, -1, 1)))
        mx = np.where(ang < spread, r[ok][None, :], -np.inf).max(1)
        fin = np.isfinite(mx)
        ang2 = np.degrees(np.arccos(np.clip(D @ D[fin].T, -1, 1)))
        w = np.exp(-(ang2 / blur) ** 2)
        env = (w @ mx[fin]) / np.maximum(w.sum(1), 1e-9)
        env = np.where(ok, np.maximum(env, np.nan_to_num(r) + floor), env)
        self.R = env.reshape(len(self.lats), len(self.lons)).astype(float)

    def dir(self, la, lo):
        la, lo = math.radians(la), math.radians(lo)
        return (self.F * math.cos(lo) + self.S * math.sin(lo)) * math.cos(la) + self.Z * math.sin(la)

    def r(self, la, lo):
        fi = min(max((la - self.lats[0]) / self.dlat, 0.0), len(self.lats) - 1.0001)
        i0 = int(fi)
        fj = ((lo + 180.0) % 360.0) / self.dlon
        j0 = int(fj) % len(self.lons)
        j1 = (j0 + 1) % len(self.lons)
        a, b = fi - i0, fj - int(fj)
        R = self.R
        return ((R[i0, j0] * (1 - b) + R[i0, j1] * b) * (1 - a) + (R[i0 + 1, j0] * (1 - b) + R[i0 + 1, j1] * b) * a)

    def P(self, la, lo, off=0.0):
        return self.O + self.dir(la, lo) * (self.r(la, lo) + off)

    def normal(self, la, lo, off=0.0, h=1.0):
        """The outward surface normal of the offset envelope at (la, lo)."""
        a = self.P(la + h, lo, off) - self.P(la - h, lo, off)
        b = self.P(la, lo + h, off) - self.P(la, lo - h, off)
        n = b.cross(a).normalized()
        return n if n.dot(self.dir(la, lo)) > 0 else -n

    def patch(self, name, material, lo0, lo1, lat_lo, lat_hi, off, thick, nu, nv, closed=False, pole=None, **kw):
        """A plate on the envelope: columns from lon lo0 to lo1, each running from lat_lo(lon) to
        lat_hi(lon); `off(lat, lon)` (or a number) is its outer surface's height over the envelope.
        `pole`: fan the last row into the pole (lat 90)."""
        def o(la, lo):
            return off(la, lo) if callable(off) else off
        rows = []
        for i in range(nv + 1):
            v = i / nv
            row = []
            for j in range(nu if closed else nu + 1):
                lo = lo0 + (lo1 - lo0) * j / nu
                a, b = lat_lo(lo), lat_hi(lo)
                la = a + (b - a) * v
                row.append(self.P(la, lo, o(la, lo)))
            rows.append(row)
        return sheet(name, rows, material, thick, self.O, closed=closed, pole=self.P(90, 0, o(90, 0)) if pole else None, **kw)


class Tube:
    """The envelope of a limb's cloth round the axis a -> b: r(t, phi) to the cloth (rays from the axis
    out, so the other leg never counts) and to `hard` parts (rays from outside in), max-filtered over
    `spread` metres and blurred over `blur`. phi = 0 faces `front`, +90 faces F x A (the outside of a
    left limb hanging down)."""

    def __init__(self, cloth, a, b, front=(0, -1, 0), hard=(), t=(-0.1, 1.1), nt=40, nphi=60, reach=0.16, spread=0.025,
                 blur=0.018, floor=0.003):
        self.a, self.b = Vector(a), Vector(b)
        self.L = (self.b - self.a).length
        A = (self.b - self.a) / self.L
        F = Vector(front)
        self.F = (F - A * F.dot(A)).normalized()
        self.S = self.F.cross(A).normalized()
        self.A = A
        self.ts = np.linspace(t[0], t[1], nt)
        self.phis = np.arange(-180.0, 180.0 - 1e-6, 360.0 / nphi)
        self.dphi = 360.0 / nphi
        soft, hard_t = _trees(cloth), _trees(hard)
        r = np.full((nt, nphi), np.nan)
        for i, tt in enumerate(self.ts):
            c = self.c(tt)
            for j, ph in enumerate(self.phis):
                d = self.d(ph)
                best = None
                for tr in soft:
                    loc, _, _, _ = tr.ray_cast(c, d, reach)
                    if loc is not None:
                        best = (loc - c).length if best is None else max(best, (loc - c).length)
                for tr in hard_t:
                    loc, _, _, _ = tr.ray_cast(c + d * reach, -d, reach)
                    if loc is not None:
                        best = (loc - c).length if best is None else max(best, (loc - c).length)
                if best is not None:
                    r[i, j] = best
        self.raw = r
        rbar = float(np.nanmedian(r))
        T, PH = np.meshgrid(self.ts, np.radians(self.phis), indexing="ij")
        X = np.stack([T.ravel() * self.L, rbar * np.cos(PH.ravel()), rbar * np.sin(PH.ravel())], 1)
        rv = r.ravel()
        ok = ~np.isnan(rv)
        dist = np.linalg.norm(X[:, None, :] - X[None, ok, :], axis=2)
        mx = np.where(dist < spread, rv[ok][None, :], -np.inf).max(1)
        fin = np.isfinite(mx)
        dist2 = np.linalg.norm(X[:, None, :] - X[None, fin, :], axis=2)
        w = np.exp(-(dist2 / blur) ** 2)
        env = (w @ mx[fin]) / np.maximum(w.sum(1), 1e-9)
        env = np.where(ok, np.maximum(env, np.nan_to_num(rv) + floor), env)
        self.R = env.reshape(r.shape)

    def c(self, t):
        return self.a.lerp(self.b, t)

    def d(self, ph):
        ph = math.radians(ph)
        return self.F * math.cos(ph) + self.S * math.sin(ph)

    def r(self, t, ph):
        fi = (t - self.ts[0]) / (self.ts[1] - self.ts[0])
        fi = min(max(fi, 0.0), len(self.ts) - 1.0001)
        i0 = int(fi)
        fj = ((ph + 180.0) % 360.0) / self.dphi
        j0 = int(fj) % len(self.phis)
        j1 = (j0 + 1) % len(self.phis)
        a, b = fi - i0, fj - int(fj)
        R = self.R
        return ((R[i0, j0] * (1 - b) + R[i0, j1] * b) * (1 - a) + (R[i0 + 1, j0] * (1 - b) + R[i0 + 1, j1] * b) * a)

    def P(self, t, ph, off=0.0):
        return self.c(t) + self.d(ph) * (self.r(t, ph) + off)

    def patch(self, name, material, t0, t1, ph_c, half, off, thick, nu=12, nv=10, corner=3.0, bulge=0.0, **kw):
        """A limb plate from t0 to t1, `half` degrees either side of `ph_c` (corners rounded by a
        squircle of exponent `corner`), its outer surface `off` over the envelope, swelling `bulge`
        in the middle (a moulded greave)."""
        rows = []
        for i in range(nv + 1):
            v = i / nv
            t = t0 + (t1 - t0) * v
            f = max(0.62, (1 - abs(2 * v - 1) ** corner) ** (1 / corner)) if corner else 1.0
            row = []
            for j in range(nu + 1):
                u = j / nu
                ph = ph_c + half * f * (2 * u - 1)
                sw = bulge * math.sin(math.pi * v) * max(0.0, math.cos(math.pi * (u - 0.5))) ** 0.5
                row.append(self.P(t, ph, off + sw))
            rows.append(row)
        return sheet(name, rows, material, thick, self.c((t0 + t1) / 2), **kw)

    def ring(self, t, lift=0.0015, n=28):
        """A strap's path round the limb at t: pulled taut, it follows the convex hull of the section
        through the cloth and the hard parts on it, `lift` off it."""
        i0 = int(round(min(max((t - self.ts[0]) / (self.ts[1] - self.ts[0]), 0), len(self.ts) - 1)))
        row = self.raw[i0]
        med = float(np.nanmedian(row))
        pts = [(float(rr if not np.isnan(rr) else med) * math.cos(math.radians(ph)), float(rr if not np.isnan(rr) else med) * math.sin(math.radians(ph)))
               for ph, rr in zip(self.phis, row)]
        hull = real._resample(real._hull2d(pts), n)
        c = self.c(t)
        out = []
        for x, y in hull:
            q = Vector((x, y))
            q = q * (1 + lift / max(q.length, 1e-6))
            out.append(c + self.F * q.x + self.S * q.y)
        return out


class Plate:
    """A torso plate's surface: a smooth multi-curve fitted to the cloth seen from the front (side -1)
    or back (+1), h(x, z) = a + b x^2 + c dz + d dz^2 outward, moved out until it clears the cloth by
    `gap` everywhere under the outline. Real plates are moulded this way: they bear on the chest's
    high points and bridge its hollows."""

    def __init__(self, objs, outline, side, gap, bend=(-2.4, -0.9), rise=(-2.5, 0.0)):
        self.side = side
        self.outline = outline
        xs, zs = [p[0] for p in outline], [p[1] for p in outline]
        self.zc = (min(zs) + max(zs)) / 2
        trees = _trees(objs)
        S, H = [], []
        for x in np.arange(min(xs), max(xs) + 1e-6, 0.01):
            for z in np.arange(min(zs), max(zs) + 1e-6, 0.01):
                if not pmc.inside_poly(x, z, pmc.grow(outline, 0.01)):
                    continue
                best = None
                for t in trees:
                    loc, _, _, _ = t.ray_cast(Vector((x, side * 0.6, z)), Vector((0, -side, 0)), 1.0)
                    if loc is not None:
                        h = side * loc.y
                        best = h if best is None else max(best, h)
                if best is not None:
                    S.append((x, z))
                    H.append(best)
        S, H = np.array(S), np.array(H)
        dz = S[:, 1] - self.zc
        M = np.stack([np.ones(len(S)), S[:, 0] ** 2, dz, dz ** 2], 1)
        k = np.linalg.lstsq(M, H, rcond=None)[0]
        k[1] = min(max(k[1], bend[0]), bend[1])
        k[3] = min(max(k[3], rise[0]), rise[1])
        k[2] = np.linalg.lstsq(dz[:, None], H - k[0] - k[1] * S[:, 0] ** 2 - k[3] * dz ** 2, rcond=None)[0][0]
        k[0] = 0.0
        k[0] = float(np.max(H + gap - M @ k))
        self.k = k

    def h(self, x, z):
        dz = z - self.zc
        a, b, c, d = self.k
        return a + b * x * x + c * dz + d * dz * dz

    def P(self, x, z, off=0.0):
        return Vector((x, self.side * (self.h(x, z) + off), z))

    def normal(self, x, z):
        # The surface is y = side * h(x, z); the gradient of side * y - h points outward.
        _, b, c, d = self.k
        return Vector((-2 * b * x, self.side, -(c + 2 * d * (z - self.zc)))).normalized()

    def span(self, outline, z):
        xs = []
        for i in range(len(outline)):
            (x0, z0), (x1, z1) = outline[i - 1], outline[i]
            if (z0 - z) * (z1 - z) <= 0 and z0 != z1:
                xs.append(x0 + (z - z0) * (x1 - x0) / (z1 - z0))
        return (min(xs), max(xs)) if xs else None

    def patch(self, name, material, outline, off, thick, nu=16, nv=14, **kw):
        """A panel with `outline` [(x, z)] whose outer surface is `off` over the fitted surface."""
        zs = [p[1] for p in outline]
        z0, z1 = min(zs) + 1e-4, max(zs) - 1e-4
        rows = []
        for i in range(nv + 1):
            z = z0 + (z1 - z0) * i / nv
            x0, x1 = self.span(outline, z)
            rows.append([self.P(x0 + (x1 - x0) * j / nu, z, off(x0 + (x1 - x0) * j / nu, z) if callable(off) else off) for j in range(nu + 1)])
        return sheet(name, rows, material, thick, Vector((0, -self.side * 0.3, self.zc)), **kw)

    def border(self, outline, off, inset=0.011, width=0.0016):
        """An inked panel line `inset` inside `outline` on the outer surface (bake detail)."""
        pts = [self.P(x, z, off + 0.0002) for x, z in pmc.grow(outline, -inset)]
        return pmc.sweep("panel_line", pts, width, 0.0007, "ink", lambda q: self.normal(q.x, q.z), closed=True, bevel=0.0)

    def frame(self, x, z, off=0.0):
        """pmc.frame at a point of the surface: flat build space (front -Y, up +Z) onto it."""
        n = self.normal(x, z)
        return pmc.frame(self.P(x, z, off), n, (0, 0, 1))


class Armour:
    """Bone-white hard parts that bake their maps from detail: each piece (rigid to its bone) gets a
    high copy, `etch` lays code scripture on it and `detail` adds any other high-only meshes (vents,
    panel lines). `finish` joins the pieces into one part, each vertex weighted to its piece's bone,
    and registers the bake. Pieces are bevelled before they are copied, so the copy matches."""

    def __init__(self, c, name, texel=1.8):
        self.c, self.name, self.texel = c, name, texel
        self.pieces, self.highs = [], []

    def add(self, obj, bone):
        kit.hs.apply_modifiers(obj)
        self.pieces.append((obj, bone))
        return obj

    def etch(self, obj, items, origin, d, up=(0, 0, 1), lift=0.0002):
        o = project(obj, items, origin, d, up=up, lift=lift, material="ink", name="etch", tree=bvh(obj))
        self.highs.append(o)
        return o

    def detail(self, obj):
        kit.hs.apply_modifiers(obj)
        self.highs.append(obj)
        return obj

    def finish(self):
        for o, bone in self.pieces:
            h = bpy.data.objects.new(o.name + ".high", o.data.copy())
            bpy.context.scene.collection.objects.link(h)
            h["shaded"] = True  # keeps the piece's own normals
            self.highs.append(h)
            o.vertex_groups.clear()
            o.vertex_groups.new(name=bone).add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
        joined = kit.join_skinned([o for o, _ in self.pieces], self.name)
        joined["texel"] = self.texel
        joined["bevel"] = 0.0
        joined["shaded"] = True
        surfaces._TEXEL_FN[joined.name] = _outer_texels
        # One high object: the selected-to-active bake renders once per high object.
        for h in self.highs:
            kit.hs.apply_modifiers(h)
        high = kit.join_skinned(self.highs, self.name + ".high")
        self.c.parts.append((joined, "DONE", None))
        self.c.detail(joined, [high], ext=0.003, ray=0.008)
        return joined


def _outer_texels(obj):
    """Texel factor per UV island of a joined armour part: the faces flagged `inner` (liners, plate
    backs) get a quarter of the density, the outer faces where the scripture shows keep it all."""
    me = obj.data
    flags = np.zeros(len(me.polygons), dtype=np.int32)
    if "inner" in me.attributes:
        me.attributes["inner"].data.foreach_get("value", flags)

    def f(isl):
        return 0.3 if sum(int(flags[fc.index]) for fc in isl) * 2 > len(isl) else 1.0
    return f


def region_tree(obj, bones):
    """A ray-cast tree of the faces of a skinned mesh led by `bones` (a sleeve without the chest)."""
    dom = kit.dominant(obj)
    me = obj.data
    return BVHTree.FromPolygons([v.co.copy() for v in me.vertices],
                                [p.vertices[:] for p in me.polygons if sum(dom[i] in bones for i in p.vertices) * 2 >= len(p.vertices)])


def strap_ring(name, pts, centre, axis, width, thick, material):
    return pmc.sweep(name, pts, width, thick, material, pmc.radial(centre, axis), closed=True, bevel=0.0)


# ------------------------------------------------------------------------------------------ helmet

def helmet(c, man, arm):
    """The sealed helmet: a bone shell fitted round the head with a black liner, a faceplate with a
    respirator snout and keel, one glowing sensor slit between the brow and the faceplate behind a
    dark visor, side rails, comms domes over the ears, a rear battery module and a brow mount.
    Returns (envelope, shell rim lat(lon), mask chin lat(lon), rear port point)."""
    hc = man.head_center()
    dom = kit.dominant(man.low)
    me = man.low.data
    co = [v.co.copy() for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons if sum(dom[i] in ("head", "neck") for i in p.vertices) * 2 > len(p.vertices)]
    head = BVHTree.FromPolygons(co, polys)
    O = hc + Vector((0, -0.016, -0.018))
    env = Env([head], O, reach=0.22, lat=(-80.0, 90.0), dlat=4.0, dlon=5.0, spread=14.0, blur=10.0, floor=0.006)

    BROW, SLIT_LO = 12.0, 3.0

    def rim(lo):
        a = abs(lo)
        side = -38.0 + 5.0 * _sm(a, 110, 180)
        return BROW + (side - BROW) * _sm(a, 58, 76)

    def chin(lo):
        return -57.0 + 17.0 * _sm(abs(lo), 0, 82)

    def mtop(lo):
        return SLIT_LO + 12.5 * _sm(abs(lo), 54, 70)

    SHELL = 0.0135  # outer surface over the envelope

    def mask_off(la, lo):
        keel = 0.0032 * math.exp(-(lo / 5.0) ** 2) * _sm(SLIT_LO - la, 2.0, 14.0)
        snout = 0.009 * math.exp(-((la + 30.0) / 17.0) ** 2 - (lo / 30.0) ** 2)
        return 0.0205 + keel + snout

    shell = env.patch("helmet", BONE, -180.0, 180.0, rim, lambda lo: 86.0, SHELL, 0.0055, nu=56, nv=14, closed=True, pole=True,
                      inner="regime_pad", bevel=0.0018)
    mask = env.patch("faceplate", BONE, -82.0, 82.0, chin, mtop, mask_off, 0.006, nu=30, nv=11, inner="regime_pad", bevel=0.0018)
    visor = env.patch("visor", "glass", -72.0, 72.0, lambda lo: -1.0, lambda lo: 16.0, 0.0075, 0.002, nu=24, nv=3, bevel=0.0)
    glow = env.patch("sensor", "glow_red", -54.0, 54.0, lambda lo: 6.3, lambda lo: 8.7, 0.0105, 0.0025, nu=20, nv=1, bevel=0.0)
    c.rigid(visor, "head")
    c.rigid(glow, "head")
    arm.add(shell, "head")
    arm.add(mask, "head")

    # Scripture: the cult mark on the back, code down the temples, ticks along the faceplate's jaw.
    def at(la, lo, off=SHELL):
        n = env.normal(la, lo, off)
        return env.P(la, lo, off) + n * 0.1, -n
    o, d = at(28, 180)
    arm.etch(shell, sigil(0.026, n=24, w=0.0028) + code_rows(["∴"], 0.028), o, d)
    o, d = at(4, 180)
    arm.etch(shell, code_rows(scripture(17, 2, 11), 0.0082), o, d)
    for sx in (1, -1):
        o, d = at(24, sx * 62)
        arm.etch(shell, code_rows(scripture(5 + sx, 3, 6), 0.0082), o, d)
        o, d = at(-22, sx * 60, mask_off(-22, sx * 60))
        arm.etch(mask, tick_rows(9 + sx, 3, 0.03, 0.0035, unit=0.001), o, d)

    # Panel lines and fasteners (baked detail): a groove round the crown, screws on the faceplate.
    lines = []
    for sx in (1, -1):
        for la, lo in ((-6, sx * 74), (-34, sx * 70)):
            p = env.P(la, lo, mask_off(la, lo))
            lines.append(screw(p, env.normal(la, lo, mask_off(la, lo)), r=0.0034))
    for o_ in lines:
        arm.detail(o_)

    # Respirator vents either side of the snout: black grilles with gunmetal slats.
    for sx in (1, -1):
        lo0, lo1 = sorted((sx * 17.0, sx * 38.0))
        vent = env.patch("vent", "black", lo0, lo1, lambda lo: -40.0, lambda lo: -20.0, lambda la, lo: mask_off(la, lo) + 0.0012, 0.003,
                         nu=6, nv=4, bevel=0.0008, segs=1)
        c.rigid(vent, "head")
        for k in range(4):
            la0 = -37.0 + k * 4.6
            c.rigid(env.patch("vent_slat", "gunmetal", lo0 + 1.5, lo1 - 1.5, lambda lo, la0=la0: la0, lambda lo, la0=la0: la0 + 1.6,
                              lambda la, lo: mask_off(la, lo) + 0.0028, 0.0018, nu=5, nv=1, bevel=0.0), "head")

    # Side rails, comms domes over the ears, rear battery module, brow mount.
    for sx in (1, -1):
        lo0, lo1 = sorted((sx * 96.0, sx * 152.0))
        c.rigid(env.patch("rail", "black", lo0, lo1, lambda lo: -3.0 + 0.04 * (abs(lo) - 96), lambda lo: 4.5 + 0.04 * (abs(lo) - 96),
                          SHELL + 0.0055, 0.0055, nu=10, nv=1, bevel=0.0012, segs=1), "head")
        p = env.P(-15, sx * 100, SHELL - 0.002)
        n = env.normal(-15, sx * 100, SHELL)
        c.rigid(kit.cyl("comms", p, p + n * 0.013, 0.031, "black", segs=20, bevel=0.002, bsegs=1), "head")
        c.rigid(kit.cyl("comms_cap", p + n * 0.012, p + n * 0.017, 0.022, "gunmetal", segs=20, bevel=0.0012, bsegs=1), "head")
        c.rigid(kit.cyl("comms_btn", p + n * 0.012 + Vector((0, 0.02, 0.024)), p + n * 0.02 + Vector((0, 0.02, 0.024)), 0.0055, "rubber",
                        segs=10, bevel=0.0008, bsegs=1), "head")
    n = env.normal(6, 180, SHELL)
    M = pmc.frame(env.P(6, 180, SHELL) + n * 0.014, n, (0, 0, 1))
    batt = [kit.block("battery", (0, 0, 0), (0.074, 0.03, 0.046), "black", bevel=0.005),
            kit.block("battery_lid", (0, -0.016, 0.004), (0.06, 0.004, 0.03), "gunmetal", bevel=0.0012),
            kit.cyl("strobe", (0.0, -0.012, 0.026), (0.0, -0.012, 0.031), 0.008, "glow_red", segs=10, bevel=0)]
    for o_ in batt:
        o_.data.transform(M)
        c.rigid(o_, "head")
    port = M @ Vector((0.0, 0.0, -0.026))
    n = env.normal(30, 0, SHELL)
    M = pmc.frame(env.P(30, 0, SHELL) + n * 0.004, n, (0, 0, 1))
    shroud = [kit.block("shroud", (0, 0, 0), (0.05, 0.009, 0.032), "gunmetal", bevel=0.002, taper=(0.8, 1.0)),
              kit.block("shroud_slot", (0, -0.006, -0.002), (0.022, 0.006, 0.012), "black", bevel=0.001)]
    for o_ in shroud:
        o_.data.transform(M)
        c.rigid(o_, "head")
    return env, rim, chin, port


# ------------------------------------------------------------------------------------------ build

def build():
    b = real.Anatomy(height=1.80, sole=0.032)
    c = real.begin("acolyte", b)
    man = real.body(c, stubble=0.0, face_detail=1.0)
    J, seg = b.j, kit.seg_dist
    lead = real.bones_at(man)
    armpit = b.at("armpit")
    ARMS = UPPER_ARMS | FOREARMS
    head_arm = Armour(c, "armour_head", texel=2.6)
    torso_arm = Armour(c, "armour_torso", texel=2.4)
    arm_arm = Armour(c, "armour_arms", texel=2.2)
    leg_arm = Armour(c, "armour_legs", texel=2.2)
    # No skin shows: what is left under the hems needs few texels.
    surfaces._TEXEL_FN[man.low.name] = lambda obj: (lambda isl: 0.3)

    # Faceless: the eyes go, and the head's skin under the helmet and hood.
    for e in man.eyes:
        c.parts = [p for p in c.parts if p[0] is not e]
    env, rim, chin, port = helmet(c, man, head_arm)
    for e in man.eyes:
        bpy.data.objects.remove(e, do_unlink=True)
    c.cover({"head"})

    # ---------------------------------------------------------------- gloves
    gloves_ = real.gloves(c, man, "glove", cuff=0.042, knuckle="black")
    tg = pmc.tree(gloves_)
    for s, sx in (("L", 1), ("R", -1)):
        W = Vector(b.rest["hand." + s][0])
        Lh = (Vector(b.rest["hand." + s][1]) - W).normalized()
        mcp = [Vector(b.rest[f"f_{f}.1.{s}"][0]) for f in ("index", "middle", "ring", "pinky")]
        T = mcp[0] - mcp[3]
        T = (T - Lh * T.dot(Lh)).normalized()
        Pn = Lh.cross(T).normalized()
        if Pn.x * sx > 0:
            Pn = -Pn
        back = -Pn
        M = Matrix((T, back, Lh)).transposed().to_4x4()
        ax = J("hand." + s, 0.0) - J("forearm." + s, 0.0)
        cc = J("hand." + s, 0.0) - ax.normalized() * 0.022
        r = pmc._radius(tg, cc, ax)
        c.rigid(pmc.band("glove_cuff", cc, (r + 0.003, r * 0.82 + 0.003), 0.03, 0.004, "glove", axis=ax), "forearm." + s)
        tab = kit.block("cuff_tab", (0, 0, 0), (0.02, 0.004, 0.028), "accent", bevel=0.0012)
        M.translation = cc + back * (r + 0.005)
        tab.data.transform(M)
        c.rigid(tab, "forearm." + s)

    # ---------------------------------------------------------------- combat shirt
    neck = J("neck", 0.0)
    tuck = b.hip_z + 0.095
    waist = tuck - 0.03
    neckline = (Vector((0, 0, neck.z + 0.028)), Vector((0, -0.45, 1)).normalized())
    collar_top = (neckline[0] + Vector((0, 0, 0.03)), Vector((0, -0.25, 1)).normalized())

    def on_arm(p):
        return lead(p) in ARMS

    cuts = [collar_top]
    for s in ("L", "R"):
        e, w = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        cuts.append((e.lerp(w, 0.86), w - e, lambda p, e=e, w=w: on_arm(p) and seg(p, e, w + (w - e) * 0.6) < 0.09))
    cuts.append(((0, 0, waist), (0, 0, -1), lambda p: not on_arm(p)))

    def ease(p):
        if not on_arm(p) and p.z < armpit - 0.06:
            return 0.007 - 0.003 * float(real._smooth(tuck + 0.03 - p.z, 0.0, 0.03))
        a = min(seg(p, J("upper_arm." + s, 0.3), J("forearm." + s, 1.0)) for s in ("L", "R"))
        return 0.007 + 0.011 * max(0.0, min(1.0, (0.09 - a) / 0.03))

    def pin(p):
        w = 0.0
        if p.z > neck.z - 0.01 and not on_arm(p):
            w = 1.0
        if p.z < tuck and not on_arm(p):
            w = 1.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.86)
            d = (wr - e).normalized()
            if on_arm(p) and seg(p, e, wr) < 0.1 and (p - wr).dot(d) > -0.025:
                w = 1.0
        return w

    def slack(p):
        w = 0.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.86)
            d = wr - e
            L = d.length
            d.normalize()
            t = (p - e).dot(d) / L
            if on_arm(p) and seg(p, e, wr) < 0.1 and t > 0.2:
                w = max(w, min(1.0, (t - 0.2) / 0.5))
        if not on_arm(p) and tuck < p.z < tuck + 0.12:
            w = max(w, 0.6 * (1 - (p.z - tuck) / 0.12))
        return w

    def above(plane, p):
        return (Vector(p) - plane[0]).dot(plane[1]) > 0

    def cuff(p):
        for s in ("L", "R"):
            e, w = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
            d = (w - e).normalized()
            if on_arm(p) and seg(p, e, w) < 0.09 and (p - e.lerp(w, 0.80)).dot(d) > 0:
                return True
        return False
    shirt = real.garment(c, man, "shirt", "primary", lambda p: lead(p) in kit.TORSO | ARMS | THIGHS | {"neck"} and p.z > waist - 0.05,
                         cuts, ease=ease, pin=None if FAST else pin, slack=slack, bend=12.0, texel=1.2,
                         trims=[("knit.primary", lambda p: (above(neckline, p) and lead(p) not in ARMS) or cuff(p))])
    c.hide_under(shirt.low, 0.05, 2)
    tshirt = pmc.tree(shirt.low)

    # Hood: a knit balaclava from inside the collar up under the helmet and faceplate.
    def hood_top(lo):
        return (chin(lo) if abs(lo) < 82 else rim(lo)) + 5.0

    def in_hood(p):
        if lead(p) not in ("head", "neck") or (Vector(p) - neckline[0]).dot(neckline[1]) < -0.025:
            return False
        d = Vector(p) - env.O
        la = math.degrees(math.asin(max(-1.0, min(1.0, d.normalized().dot(env.Z)))))
        lo = math.degrees(math.atan2(d.dot(env.S), d.dot(env.F)))
        return la < hood_top(lo)
    hood = real.layer(c, man, "hood", "knit.primary", in_hood, [], ease=0.004, smooth=1, texel=0.8, seams="hems")
    c.hide_under(hood, 0.02, 1)

    for s, sx in (("L", 1), ("R", -1)):
        fa0, fa1 = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        ax = (fa1 - fa0).normalized()
        r = pmc._radius(tshirt, fa0 + ax * 0.01, ax) + 0.003
        pad = pmc.wrap("elbow_pad", fa0 - ax * 0.03, fa0 + ax * 0.055, r, r - 0.005, 180 - 55 * sx, 180 + 55 * sx, 0.009, "black",
                       nt=4, nphi=8, bevel=0.003, bulge=0.004, fit=(tshirt, 0.0025))
        c.rigid(pad, "forearm." + s)
        # Sleeve pocket under the shoulder plates.
        ua0, ua1 = J("upper_arm." + s, 0.0), J("upper_arm." + s, 1.0)
        around = pmc._limb(ua0, ua1, front=(0, -1, 0))
        out = 90 * sx - 15 * sx
        real.patch(c, shirt.low, "sleeve_pocket", "primary",
                   lambda p, around=around, out=out: (lambda t, a: 0.50 < t < 0.76 and abs((a - out + 180) % 360 - 180) < 34)(*around(p)),
                   lift=0.0015, puff=0.006, thick=0.002)

    # ---------------------------------------------------------------- trousers
    top_z = tuck
    belt_z = b.hip_z + 0.07
    hem = b.sole + 0.19 - 0.03
    LEGS = THIGHS | kit.SHINS

    def t_ease(p):
        band = 0.003 * (1 - real._smooth(top_z - p.z, 0.02, 0.07))
        return 0.011 + band + 0.004 * real._smooth(top_z - p.z, 0.04, 0.2) + 0.007 * real._smooth(J("lower_leg.L", 0.0).z - p.z, 0.0, 0.15)

    def t_pin(p):
        return 1.0 if p.z > top_z - 0.045 or p.z < hem + 0.018 else 0.0

    def t_slack(p):
        return real._smooth(hem + 0.13 - p.z, 0.0, 0.1)

    trousers = real.garment(c, man, "trousers", "ripstop.secondary",
                            lambda p: lead(p) in LEGS | {"hips", "spine"} and hem - 0.03 < p.z < top_z + 0.03,
                            [((0, 0, top_z), (0, 0, 1)), ((0, 0, hem), (0, 0, -1), lambda p: lead(p) in LEGS)],
                            ease=t_ease, pin=None if FAST else t_pin, slack=t_slack, bend=14.0, texel=1.0)
    c.hide_under(trousers.low, 0.06, 2)
    tt = pmc.tree(trousers.low)
    belt = pmc.sweep("belt", pmc.ring_pts(tt, (0, -0.005), belt_z, 0.004, n=32), 0.048, 0.01, "webbing", pmc.radial((0, -0.005, 0)), closed=True)
    c.add(belt, ["hips", "spine", "upper_leg.L", "upper_leg.R"])
    loc, _ = pmc.hit(tt, (0, -0.5, belt_z), (0, 1, 0))
    bk = kit.block("buckle", (0, 0, 0), (0.062, 0.013, 0.04), "gunmetal", bevel=0.003)
    kit.cut(bk, kit.block("buckle_slot", (0, -0.007, 0), (0.044, 0.006, 0.02), "steel", bevel=0))
    bk.data.transform(Matrix.Translation(Vector((0, loc.y - 0.016, belt_z))))
    c.rigid(bk, "hips")
    for s, sx in (("L", 1), ("R", -1)):
        ul0, ul1 = J("upper_leg." + s, 0.0), J("upper_leg." + s, 1.0)
        around = pmc._limb(ul0, ul1)
        out = 98 * sx
        real.patch(c, trousers.low, "cargo", "ripstop.secondary",
                   lambda p, around=around, out=out: (lambda t, a: 0.47 < t < 0.76 and abs((a - out + 180) % 360 - 180) < 34)(*around(p)),
                   lift=0.002, puff=0.013, thick=0.003)
        real.patch(c, trousers.low, "cargo_flap", "ripstop.secondary",
                   lambda p, around=around, out=out: (lambda t, a: 0.445 < t < 0.53 and abs((a - out + 180) % 360 - 180) < 37)(*around(p)),
                   lift=0.016, puff=0.002, thick=0.003)

    # ---------------------------------------------------------------- plate carrier
    dz = (armpit - 0.198) - 1.03

    def Z(z):
        return z + dz
    shirt_hard = [tshirt]
    f_cover = kit.rounded([(-0.13, Z(1.10)), (0.13, Z(1.10)), (0.13, Z(1.29)), (0.078, Z(1.378)), (-0.078, Z(1.378)), (-0.13, Z(1.29))], 0.022)
    f_plate = kit.rounded([(-0.118, Z(1.112)), (0.118, Z(1.112)), (0.118, Z(1.286)), (0.07, Z(1.366)), (-0.07, Z(1.366)), (-0.118, Z(1.286))], 0.018)
    pf = Plate(shirt_hard, f_cover, -1, 0.007)
    front = pf.patch("carrier_front", NYLON, f_cover, 0.022, 0.022, nu=16, nv=12, bevel=0.005)
    c.rigid(front, "chest")
    fp = pf.patch("chest_plate", BONE, f_plate, 0.032, 0.0105, nu=18, nv=14, bevel=0.003)
    torso_arm.add(fp, "chest")
    torso_arm.detail(pf.border(f_plate, 0.032))
    for sx in (1, -1):
        p = pf.P(sx * 0.056, Z(1.298), 0.032)
        torso_arm.etch(fp, code_rows(scripture(3 + sx, 5, 8), 0.0108), p + Vector((0, -0.1, 0)), (0, 1, 0))
    p = pf.P(0.0, Z(1.19), 0.032)
    torso_arm.etch(fp, sigil(0.03, n=28, w=0.0032) + code_rows(["∴"], 0.032), p + Vector((0, -0.1, 0)), (0, 1, 0))
    p = pf.P(0.0, Z(1.13), 0.032)
    torso_arm.etch(fp, barcode(23, 0.16, 0.007), p + Vector((0, -0.1, 0)), (0, 1, 0))
    for x, z in ((-0.1, Z(1.14)), (0.1, Z(1.14)), (-0.094, Z(1.285)), (0.094, Z(1.285))):
        n = pf.normal(x, z)
        torso_arm.detail(screw(pf.P(x, z, 0.032), n, r=0.0042))
    # The placard below the plate: three rifle-magazine pouches with red pull tabs.
    for x in (-0.08, 0.0, 0.08):
        M = pf.frame(x, Z(1.165), 0.022)
        objs = [kit.block("mag_pouch", (0, -0.021, -0.006), (0.07, 0.042, 0.118), NYLON, bevel=0.006),
                kit.block("pouch_flap", (0, -0.023, 0.046), (0.074, 0.048, 0.028), NYLON, bevel=0.005),
                kit.block("bungee", (0, -0.043, -0.01), (0.072, 0.004, 0.012), "black", bevel=0.0015),
                kit.block("pull_tab", (0, -0.05, 0.036), (0.026, 0.005, 0.034), "accent", bevel=0.0015)]
        for o in objs:
            o.data.transform(M)
            c.rigid(o, "chest")

    b_cover = kit.rounded([(-0.132, Z(1.03)), (0.132, Z(1.03)), (0.132, Z(1.29)), (0.104, Z(1.365)), (-0.104, Z(1.365)), (-0.132, Z(1.29))], 0.025)
    b_plate = kit.rounded([(-0.12, Z(1.042)), (0.12, Z(1.042)), (0.12, Z(1.286)), (0.094, Z(1.353)), (-0.094, Z(1.353)), (-0.12, Z(1.286))], 0.02)
    pb = Plate(shirt_hard, b_cover, 1, 0.007)
    back = pb.patch("carrier_back", NYLON, b_cover, 0.022, 0.022, nu=16, nv=12, bevel=0.005)
    c.rigid(back, "chest")
    bp = pb.patch("back_plate", BONE, b_plate, 0.032, 0.0105, nu=18, nv=14, bevel=0.003)
    torso_arm.add(bp, "chest")
    torso_arm.detail(pb.border(b_plate, 0.032))
    p = pb.P(0.0, Z(1.322), 0.032)
    torso_arm.etch(bp, code_rows(scripture(29, 2, 18), 0.0082), p + Vector((0, 0.1, 0)), (0, -1, 0))
    p = pb.P(0.0, Z(1.065), 0.032)
    torso_arm.etch(bp, tick_rows(31, 2, 0.2, 0.005), p + Vector((0, 0.1, 0)), (0, -1, 0))

    # The uplink: a bone-housed radio on the back plate, a whip antenna and a fold-up SATCOM panel.
    Mb = pb.frame(0.0, Z(1.19), 0.032)
    hw, hd, hh = 0.19, 0.075, 0.25

    def W_(p):
        return Mb @ Vector(p)
    # The radio rides in a black cordura pouch behind a bone armour lid.
    pouch = kit.block("uplink_pouch", (0, -hd / 2, 0), (hw, hd, hh), NYLON, bevel=0.012, taper=(0.95, 0.97))
    pouch.data.transform(Mb)
    c.rigid(pouch, "chest")
    lid = kit.block("uplink_lid", (0, -hd - 0.003, 0.004), (hw - 0.028, 0.008, hh - 0.05), BONE, bevel=0.003)
    kit.hs.apply_modifiers(lid)
    lid.data.transform(Mb)
    torso_arm.add(lid, "chest")
    nrm = (Mb.to_3x3() @ Vector((0, -1, 0))).normalized()
    torso_arm.etch(lid, sigil(0.036, n=30, w=0.0034) + code_rows(["∴"], 0.04), W_((0, -hd - 0.007, 0.03)) + nrm * 0.1, -nrm)
    torso_arm.etch(lid, code_rows(["UPLINK 07", "0x7F A3 C0DE"], 0.0085), W_((0, -hd - 0.007, -0.062)) + nrm * 0.1, -nrm)
    for x in (-0.067, 0.067):
        for z in (-0.083, 0.091):
            torso_arm.detail(screw(W_((x, -hd - 0.007, z)), nrm, r=0.0038))
    parts = [kit.block("uplink_cap", (0, -hd / 2, hh / 2 + 0.012), (hw * 0.92, hd * 0.9, 0.026), "gunmetal", bevel=0.004),
             kit.block("uplink_base", (0, -hd / 2, -hh / 2 - 0.008), (hw * 0.9, hd * 0.88, 0.02), "gunmetal", bevel=0.004),
             kit.cyl("knob", (0.035, -hd / 2, hh / 2 + 0.024), (0.035, -hd / 2, hh / 2 + 0.04), 0.011, "black", segs=14, bevel=0.0015),
             kit.cyl("knob", (0.0, -hd / 2, hh / 2 + 0.024), (0.0, -hd / 2, hh / 2 + 0.036), 0.008, "black", segs=12, bevel=0.0015),
             kit.cyl("led", (-0.025, -hd / 2 - 0.02, hh / 2 + 0.024), (-0.025, -hd / 2 - 0.02, hh / 2 + 0.03), 0.004, "glow_red", segs=8, bevel=0),
             kit.cyl("whip_base", (-0.07, -hd / 2, hh / 2 + 0.024), (-0.07, -hd / 2, hh / 2 + 0.05), 0.011, "black", segs=12, bevel=0.0015),
             kit.cyl("sat_mast", (0.062, -hd / 2 + 0.01, hh / 2 + 0.024), (0.062, -hd / 2 + 0.01, hh / 2 + 0.07), 0.007, "gunmetal", segs=10, bevel=0.001)]
    for z in (-0.112, 0.118):
        parts.append(kit.block("uplink_strap", (0, -hd / 2 - 0.002, z), (hw + 0.008, hd + 0.01, 0.022), "webbing", bevel=0.002))
    for o in parts:
        o.data.transform(Mb)
        c.rigid(o, "chest")
    whip = [W_((-0.07, -hd / 2, hh / 2 + 0.05)), W_((-0.072, -hd / 2 - 0.004, hh / 2 + 0.09)), W_((-0.08, -hd / 2 - 0.016, hh / 2 + 0.2)),
            W_((-0.092, -hd / 2 - 0.05, hh / 2 + 0.52))]
    c.rigid(kit.rope("whip_goose", whip[:2] + [whip[1].lerp(whip[2], 0.5)], 0.0065, "rubber"), "chest")
    c.rigid(kit.cyl("whip", whip[1].lerp(whip[2], 0.45), whip[3], 0.0042, "rubber", r1=0.0022, segs=8, bevel=0), "chest")
    c.rigid(kit.cyl("whip_tip", whip[3], whip[3] + (whip[3] - whip[2]).normalized() * 0.012, 0.004, "black", segs=8, bevel=0), "chest")
    # SATCOM panel hinged up on its mast, facing up and back.
    hinge = W_((0.062, -hd / 2 + 0.01, hh / 2 + 0.07))
    Ms = Matrix.Translation(hinge) @ Mb.to_3x3().to_4x4() @ Matrix.Rotation(math.radians(30), 4, "X") @ Matrix.Translation((0, -0.004, 0.058))
    sat = kit.block("satcom", (0, 0, 0), (0.115, 0.012, 0.11), BONE, bevel=0.003)
    kit.hs.apply_modifiers(sat)
    sat.data.transform(Ms)
    torso_arm.add(sat, "chest")
    sn = (Ms.to_3x3() @ Vector((0, -1, 0))).normalized()
    torso_arm.etch(sat, code_rows(scripture(41, 6, 9), 0.0072), Ms @ Vector((0, -0.006, 0)) + sn * 0.1, -sn,
                   up=Ms.to_3x3() @ Vector((0, 0, 1)))
    c.rigid(kit.block("sat_hinge", hinge, (0.03, 0.014, 0.014), "gunmetal", bevel=0.002), "chest")
    sat_back = kit.block("satcom_back", (0, 0.009, 0), (0.1, 0.008, 0.095), "gunmetal", bevel=0.002)
    sat_back.data.transform(Ms)
    c.rigid(sat_back, "chest")
    # Cable from the radio up the back of the neck into the helmet's rear module.
    rt = W_((-0.03, -hd / 2 - 0.01, hh / 2 + 0.03))
    c.add(kit.rope("helmet_cable", [port + Vector((0, 0.004, -0.004)), port + Vector((0.0, 0.03, -0.05)), rt + Vector((-0.01, 0.02, 0.06)), rt], 0.0045,
                   "rubber"), ["head", "neck", "chest"])

    # Padded shoulder straps in the accent colour with buckles, over the shirt.
    for s, sx in (("L", 1), ("R", -1)):
        xs = sx * 0.085
        pts = []
        for y in (-0.13, -0.10, -0.07, -0.04, -0.01, 0.02, 0.05, 0.08, 0.11, 0.13):
            loc, _ = pmc.hit(tshirt, (xs, y, 1.9), (0, 0, -1))
            z = loc.z + 0.008 if loc and loc.z > armpit + 0.05 else Z(1.36)
            pts.append((xs, y, z))
        pts[0] = pf.P(sx * 0.074, Z(1.362), 0.012)
        pts[-1] = pb.P(sx * 0.082, Z(1.348), 0.012)
        path = pmc.smooth_path(pts, 3)
        nrm = pmc.radial((sx * 0.085, 0, Z(1.33)), (1, 0, 0))
        c.rigid(pmc.sweep("shoulder_strap", path, 0.05, 0.013, "accent", nrm), "chest")
        k = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.07))
        tan = (path[k + 1] - path[k - 1]).normalized()
        nn = nrm(path[k]).normalized()
        c.rigid(pmc.side_buckle("strap_buckle", path[k] + nn * 0.009, -tan, nn, w=0.04), "chest")
        if s == "L":
            k2 = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.035))
            t2 = (path[k2 + 1] - path[k2 - 1]).normalized()
            n2 = nrm(path[k2]).normalized()
            Mp = pmc.frame(path[k2] + n2 * 0.0065, n2, t2)
            ptt = [kit.block("ptt", (0, -0.009, 0), (0.034, 0.018, 0.042), "black", bevel=0.003),
                   kit.cyl("ptt_button", (0, -0.017, 0.004), (0, -0.023, 0.004), 0.009, "accent", segs=14, bevel=0.0015)]
            pmc.put(ptt, Mp)
            pmc.rigid_all(c, ptt, "chest")
            ptt_top = Mp @ Vector((0, -0.01, 0.022))
            over = [path[i] + nrm(path[i]).normalized() * 0.014 + Vector((0.026, 0, 0)) for i in range(k2 + 3, len(path) - 4, 3)]
            c.rigid(kit.rope("ptt_cable", [ptt_top] + over + [rt + Vector((0.06, 0.01, 0.03)), rt + Vector((0.03, 0, 0))], 0.0035, "black"), "chest")

    # Cummerbund from under the front plate round to the back.
    for s, sx in (("L", 1), ("R", -1)):
        for z, w in ((Z(1.075), 0.06), (Z(1.15), 0.06)):
            pts = pmc._ring_side(tshirt, (0, -0.004), z, 0.012, sx * 46, sx * 136)
            c.rigid(pmc.sweep("cummerbund", pmc.smooth_path(pts, 3), w, 0.012, NYLON, pmc.radial((0, -0.004, 0))), "chest")

    # ---------------------------------------------------------------- shoulder plates
    for s, sx in (("L", 1), ("R", -1)):
        ua = "upper_arm." + s
        ua0, ua1 = J(ua, 0.0), J(ua, 1.0)
        # The lower lame first: a band round the outside of the upper arm, tucked under the cap.
        sleeve = region_tree(shirt.low, {ua, "shoulder." + s})
        tu = Tube([sleeve], ua0, ua1, front=(0, -1, 0), t=(0.1, 0.75), nt=22, nphi=48, reach=0.14, spread=0.03, blur=0.02)
        lame = tu.patch("shoulder_lame", BONE, 0.2, 0.42, 90 * sx, 66, 0.007, 0.0055, nu=10, nv=3, corner=2.5, bevel=0.002)
        arm_arm.add(lame, ua)
        # The cap: a dome over the deltoid fitted round the shoulder joint, clearing the lame.
        O = ua0 + Vector((-sx * 0.012, 0.0, -0.012))
        cap_env = Env([sleeve, lame], O, Z=(sx * 0.6, 0.0, 0.8), F=(0, -sx, 0), reach=0.16, lat=(-40.0, 90.0), dlat=4.0, dlon=6.0,
                      spread=9.0, blur=7.0, floor=0.003)

        def cap_rim(lo):
            sn = math.sin(math.radians(lo))
            return 38.0 - 63.0 * max(0.0, sn) ** 1.3 + 7.0 * max(0.0, -sn)
        cap = cap_env.patch("shoulder_cap", BONE, -180.0, 180.0, cap_rim, lambda lo: 84.0, 0.0095, 0.006, nu=28, nv=6, closed=True, pole=True,
                            inner="regime_pad", bevel=0.0022)
        arm_arm.add(cap, ua)
        n = cap_env.normal(40, 90)
        arm_arm.etch(cap, code_rows(scripture(41 + sx, 3, 7), 0.0095), cap_env.P(40, 90, 0.0095) + n * 0.1, -n, up=(0, 0, 1))
        n = tu.d(90 * sx)
        p = tu.P(0.33, 90 * sx, 0.007)
        arm_arm.etch(lame, tick_rows(44 + sx, 2, 0.06, 0.0045), p + n * 0.1, -n, up=(ua0 - ua1).normalized())
        for lo in (-40, -140):
            la = cap_rim(lo) + 7
            arm_arm.detail(screw(cap_env.P(la, lo, 0.0095), cap_env.normal(la, lo, 0.0095), r=0.0035))
        # A strap round the arm under the lame holds it.
        tu2 = Tube([sleeve], ua0, ua1, hard=[lame], t=(0.3, 0.5), nt=6, nphi=36, reach=0.14)
        c.rigid(strap_ring("arm_strap", tu2.ring(0.38, 0.0015, n=20), ua0.lerp(ua1, 0.38), ua1 - ua0, 0.022, 0.004, NYLON), ua)

    # ---------------------------------------------------------------- leg guards
    tt = pmc.tree(trousers.low)
    for s, sx in (("L", 1), ("R", -1)):
        ul, ll = "upper_leg." + s, "lower_leg." + s
        ul0, ul1 = J(ul, 0.0), J(ul, 1.0)
        ll0, ll1 = J(ll, 0.0), J(ll, 1.0)
        # Thigh guard: front and outside of the upper thigh, hung from the belt, two straps.
        tu = Tube([tt], ul0, ul1, t=(-0.05, 0.6), nt=28, nphi=60, reach=0.16, spread=0.03, blur=0.022)
        thigh = tu.patch("thigh_guard", BONE, 0.1, 0.44, 42 * sx, 38, 0.0095, 0.007, nu=10, nv=7, corner=3.0, bulge=0.003, bevel=0.0025)
        leg_arm.add(thigh, ul)
        n = tu.d(44 * sx)
        p = tu.P(0.27, 44 * sx, 0.0095)
        leg_arm.etch(thigh, code_rows(scripture(61 + sx, 4, 6), 0.0098), p + n * 0.1, -n, up=(ul0 - ul1).normalized())
        for tq in (0.14, 0.4):
            for pq in (-28, 28):
                ph = 42 * sx + pq
                leg_arm.detail(screw(tu.P(tq, ph, 0.0095), tu.d(ph), r=0.0034))
        tu2 = Tube([tt], ul0, ul1, hard=[thigh], t=(0.0, 0.5), nt=11, nphi=36, reach=0.17)
        for tq in (0.3,):
            c.rigid(strap_ring("thigh_strap", tu2.ring(tq, 0.0015, n=22), ul0.lerp(ul1, tq), ul1 - ul0, 0.03, 0.0045, "accent"), ul)
            p = tu2.P(tq, -30 * sx, 0.0)
            M = pmc.frame(p + tu2.d(-30 * sx) * 0.0045, tu2.d(-30 * sx), ul0 - ul1)
            bk = kit.block("leg_buckle", (0, 0, 0), (0.034, 0.008, 0.03), "gunmetal", bevel=0.0012)
            bk.data.transform(M)
            c.rigid(bk, ul)
        top = tu.P(0.1, 42 * sx, 0.006)
        c.add(pmc.sweep("hanger", [Vector((top.x, top.y, belt_z + 0.01)) + (top - ul0.lerp(ul1, 0.06)).normalized() * 0.004, top + Vector((0, 0, 0.012))],
                        0.022, 0.004, "black", lambda p, s_=sx: tu.d(42 * s_)), ["hips", ul])

        # Shin guard and knee cap over the trousers.
        ts = Tube([tt], ll0, ll1, t=(-0.1, 0.8), nt=30, nphi=60, reach=0.15, spread=0.03, blur=0.022)
        shin = ts.patch("shin_guard", BONE, 0.13, 0.64, 4 * sx, 58, 0.009, 0.0065, nu=10, nv=9, corner=3.0, bulge=0.004, bevel=0.0025)
        leg_arm.add(shin, ll)
        n = ts.d(4 * sx)
        p = ts.P(0.42, 4 * sx, 0.009)
        leg_arm.etch(shin, code_rows(scripture(71 + sx, 8, 3), 0.0092), p + n * 0.1, -n, up=(ll0 - ll1).normalized())
        kn = ll0 + Vector((0, 0.012, 0.004))
        kenv = Env([tt, shin], kn, Z=(0, -1, 0.12), F=(0, 0, 1), reach=0.14, lat=(0.0, 90.0), dlat=4.0, dlon=8.0, spread=16.0, blur=10.0, floor=0.004)

        def knee_rim(lo):
            return 50.0 - 10.0 * math.cos(math.radians(lo)) ** 2
        knee = kenv.patch("knee_cap", BONE, -180.0, 180.0, knee_rim, lambda lo: 84.0, 0.011, 0.0065, nu=16, nv=4, closed=True, pole=True,
                          inner="regime_pad", bevel=0.0022)
        leg_arm.add(knee, ll)
        kp = kenv.P(90, 0, 0.011)
        kn_n = kenv.normal(90, 0, 0.011, h=4.0)
        c.rigid(kit.cyl("knee_boss", kp - kn_n * 0.003, kp + kn_n * 0.0045, 0.013, "gunmetal", segs=6, bevel=0.0012, bsegs=1), ll)
        ts2 = Tube([tt], ll0, ll1, hard=[shin], t=(0.1, 0.7), nt=13, nphi=36, reach=0.15)
        for tq in (0.24, 0.56):
            c.rigid(strap_ring("shin_strap", ts2.ring(tq, 0.0015, n=22), ll0.lerp(ll1, tq), ll1 - ll0, 0.024, 0.0045, "webbing"), ll)

    # Tactical boots.
    real.boots(c, man, "boot", sole_kind="rubber", trim="rubber", top=0.19, lace="webbing", tab="accent")
    for a in (head_arm, torso_arm, arm_arm, leg_arm):
        a.finish()
    pmc.economise(c)
    return c


SPEC = {"build": build, "faction": "regime", "budget": (25000, 120000), "loadout": "rifle",
        "colors": {"primary": "#1a1a1d", "secondary": "#2a2a2e", "accent": "#7a1010"}}
