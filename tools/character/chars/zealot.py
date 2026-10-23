"""Zealot, Regime: an augmented officer of the Algorithm. A shaved head with gunmetal skull ports cabled
down into the collar, barcode tattoos behind the ear and on the nape and a halo crown of thin antennas
with glowing tips on a gunmetal circlet; the face covered by a smoked visor band with a red ocular
implant over the right eye and a bone rebreather mask over the nose, mouth and chin with twin filters,
strapped back to the comms modules over the ears. A long black leather robe over bone plate: a keeled
breastplate etched with scripture and fauld lames in the robe's open front, a bone gorget, the robe's
red stole round the collar and down the front edges embroidered with code, a skirt open at the front and
split up the back; bone pauldrons strapped over the robe, bone vambraces, knee caps and shin guards over
the Acolyte's undersuit, a belted sash with the cult's mark on its plaque.

Built on the realistic layer (real.py) like the Acolyte: a real body (only the scalp, temples and
cheekbones show, with a shaved scalp's shadow and ink decals baked into the skin), the undersuit, robe and
skirt draped by the cloth simulation (the robe tented over the plate, the skirt hung from the waist over
the legs and their plates), every hard plate laid on an envelope of the cloth or head it sits on and
baking its scripture and fasteners from detail meshes.

Tints: primary = robe and skirt, secondary = undersuit (shirt and trousers), accent = stole, sash and
straps.
"""

import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

import kit
import real
import surfaces
from chars import acolyte as aco
from chars import contractor as pmc
from kit import FOREARMS, SHINS, THIGHS, TORSO, UPPER_ARMS

BONE, NYLON = aco.BONE, aco.NYLON
ARMS = UPPER_ARMS | FOREARMS
FAST = os.environ.get("REGIME_FAST", "")  # look-dev: "1" skips every cloth simulation, "a,b" those garments


def simulated(name):
    return FAST != "1" and name not in FAST.split(",")


kit.hs.PALETTE.update({
    "zealot_skin": ((0.64, 0.51, 0.45), (0.68, 0.55, 0.48), 0.0, 0.55, 0.0, 0),     # pale, cool, indoor skin
    "zealot_ink": ((0.045, 0.06, 0.075), (0.045, 0.06, 0.075), 0.0, 0.5, 0.0, 0),   # blue-black tattoo ink
    "zealot_thread": ((0.70, 0.66, 0.57), (0.78, 0.74, 0.66), 0.0, 0.62, 0.1, 0),  # bone-white embroidery
})


def tattoo(g, pal):
    """Tattoo ink in the skin: the skin recipe's own pores and colour (continuous with the skin round
    it, the noise is in object space) under a faded blue-black, a little patchy, with the skin's sheen."""
    r = surfaces.skin(g, kit.hs.PALETTE["zealot_skin"])
    pos = g.geo("Position")
    fade = g.remap(g.noise(pos, 380.0, detail=3), 0.3, 0.7, 0.72, 0.9, smooth=False)
    col = g.mix(fade, r["color"], pal[0])
    return dict(color=col, rough=g.lerp(0.25, r["rough"], 0.5), metal=0.0, height=r["height"], bump=r["bump"])


surfaces.RECIPES.setdefault("tattoo", tattoo)
surfaces.RECIPE.setdefault("zealot_skin", "skin")
surfaces.RECIPE.setdefault("zealot_ink", "tattoo")
surfaces.RECIPE.setdefault("zealot_thread", "print")


def _sm(x, a, b):
    return float(real._smooth(x, a, b))


# ------------------------------------------------------------------------------------- helpers

def shaved_scalp(man, E, u, strength=0.55, brows=0.3):
    """The skin's `face` masks for a shaved head: the stubble channel becomes the shadow of hair shaved
    to the skin inside the natural hairline (the Contractor's hair cut planes: forehead, temples, nape),
    the brows fade. Written on the game mesh and the sculpt it bakes from."""
    planes = (((0, -0.06, 0.068), (0, -0.8, -1.0)), ((0, 0.035, 0.012), (0, -0.75, -1.0)), ((0, 0.0, -0.062), (0, -0.15, -1.0)))
    for o in (man.low, man.high):
        me = o.data
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        F = (co.reshape(-1, 3) - np.array(E[:])) / u
        m = np.ones(len(F))
        for P, n in planes:
            n = np.array(n) / np.linalg.norm(n)
            m *= real._smooth(-((F - np.array(P)) @ n), -0.001, 0.007)
        at = me.attributes["face"]
        vals = np.zeros(len(F) * 4, dtype=np.float32)
        at.data.foreach_get("color", vals)
        vals = vals.reshape(-1, 4)
        vals[:, 0] = np.maximum(vals[:, 0], strength * m)
        vals[:, 2] *= brows
        at.data.foreach_set("color", vals.ravel())


def decal(name, tree, items, origin, d, up=(0, 0, 1), material="zealot_ink", lift=0.00022, seg=0.004):
    """Flat marks laid on a surface (ink in the skin, for the bake): each item (x, y, w, h) a rectangle
    in the plane through `origin` across `d`, x right and y up, its grid of points every `seg` found by
    rays along d, so a long bar follows the skull's curve instead of cutting into it."""
    d = Vector(d).normalized()
    up = Vector(up).normalized()
    u0 = up.cross(-d).normalized()
    v0 = (-d).cross(u0).normalized()
    bm = bmesh.new()
    for x, y, w, h in items:
        nv, nu = max(1, math.ceil(h / seg)), max(1, math.ceil(w / seg))
        grid = []
        for i in range(nv + 1):
            row = []
            for j in range(nu + 1):
                p = Vector(origin) + u0 * (x - w / 2 + w * j / nu) + v0 * (y - h / 2 + h * i / nv)
                loc, nor, _, _ = tree.ray_cast(p - d * 0.3, d, 0.8)
                if loc is None:
                    break
                if nor.dot(d) > 0:
                    nor = -nor
                row.append(loc + nor * lift)
            if len(row) < nu + 1:
                grid = None
                break
            grid.append(row)
        if not grid:
            continue
        vs = [[bm.verts.new(p) for p in row] for row in grid]
        for i in range(nv):
            for j in range(nu):
                bm.faces.new((vs[i][j], vs[i][j + 1], vs[i + 1][j + 1], vs[i + 1][j]))
    return kit.hs._obj(name, bm, material, 0.0)


def bars(marks):
    """aco.barcode / tick_rows items as decal rectangles."""
    return [(x, y, m[0], m[1]) for x, y, m in marks]


def remat(obj, kind):
    obj.data.materials.clear()
    obj.data.materials.append(real.mat(kind))
    return obj


def strip_uvs(obj, width, thick):
    """UVs for a pmc.sweep strip (4 vertices per ring, built ring by ring): metres along its length
    by metres round its section, so a weave keeps its size and the strip bakes as one island."""
    me = obj.data
    V = [v.co for v in me.vertices]
    n = len(V) // 4
    cum = [0.0]
    for i in range(1, n):
        cum.append(cum[-1] + (sum((V[4 * i + k] - V[4 * (i - 1) + k] for k in range(4)), Vector()) / 4).length)
    per = [0.0, width, width + thick, 2 * width + thick, 2 * width + 2 * thick]
    uv = me.uv_layers.new(name="UVMap")
    for f in me.polygons:
        ks = [me.loops[li].vertex_index % 4 for li in f.loop_indices]
        wrap = 0 in ks and 3 in ks and len(set(me.loops[li].vertex_index // 4 for li in f.loop_indices)) > 1
        for li in f.loop_indices:
            vi = me.loops[li].vertex_index
            k = vi % 4
            if wrap and k == 0:
                k = 4
            uv.data[li].uv = (cum[vi // 4], per[k])


def high_of(c, low):
    """The list of high meshes `low` bakes from (to add embroidery, tattoos)."""
    return next(h for lo, h, _ in c.highs if lo is low)


def tent(obj, hard, region, gap=0.009, slope=0.75, reach=0.04, grid=0.005, step=0.002):
    """Lift the vertices of `obj` where region(p) over the hard parts in front of the body (a robe over
    a cuirass that stands off the chest like a board): seen from the front, every vertex stays `gap`
    in front of the plates and of a slope falling away from their edges, so the faces between a
    vertex on the plate and one beside it pass over the plate's edge, never through it. Each vertex
    moves out along its normal until it is clear. Returns over(p): is p within reach of a plate,
    seen from the front."""
    fwd = Vector((0, -1, 0))
    trees = [pmc.tree(o) for o in hard]
    lo = [min((o.matrix_world @ Vector(cc))[i] for o in hard for cc in o.bound_box) for i in range(3)]
    hi = [max((o.matrix_world @ Vector(cc))[i] for o in hard for cc in o.bound_box) for i in range(3)]
    pts, ys = [], []
    x = lo[0]
    while x <= hi[0]:
        z = lo[2]
        while z <= hi[2]:
            best = None
            for t in trees:
                loc, _, _, _ = t.ray_cast(Vector((x, lo[1] - 0.3, z)), -fwd, 1.0)
                if loc is not None and (best is None or loc.y < best):
                    best = loc.y
            if best is not None:
                pts.append(Vector((x, 0.0, z)))
                ys.append(best)
            z += grid
        x += grid
    kd = KDTree(len(pts))
    for i, q in enumerate(pts):
        kd.insert(q, i)
    kd.balance()

    def front_y(q):
        found = kd.find_range(Vector((q.x, 0.0, q.z)), reach)
        return min((ys[i] + slope * d for _, i, d in found), default=None)
    me = obj.data
    moved = 0
    for v in me.vertices:
        q = v.co.copy()
        if not region(q):
            continue
        fy = front_y(q)
        if fy is None or q.y <= fy - gap:
            continue
        n = Vector(v.normal)
        n = (n + fwd * 0.3).normalized() if n.dot(fwd) > -0.2 else fwd
        for _ in range(60):
            q = q + n * step
            fy = front_y(q)
            if fy is None or q.y <= fy - gap:
                break
        v.co = q
        moved += 1
    me.update()
    print(f"  {obj.name}: {moved} vertices lifted over the plates")
    return lambda q: front_y(Vector(q)) is not None


def bind_under(obj, plates, depth=0.07, region=lambda p: True):
    """Weight every vertex of `obj` (where region(p)) whose normal runs into one of `plates`
    [(object, thickness, bone)] within `depth` wholly to that plate's bone."""
    trees = [(pmc.tree(o), bn) for o, _, bn in plates]
    for v in obj.data.vertices:
        p, n = v.co, Vector(v.normal)
        if not region(p):
            continue
        best = None
        for t, bn in trees:
            loc, _, _, d = t.ray_cast(p + n * 0.001, n, depth)
            if loc is not None and (best is None or d < best[0]):
                best = (d, bn)
        if best is not None:
            to_bone_vertex(obj, v, best[1])


def to_bone_vertex(obj, v, bone):
    vg = obj.vertex_groups
    g = vg.get(bone) or vg.new(name=bone)
    for ge in list(v.groups):
        if ge.group != g.index:
            vg[ge.group].remove([v.index])
    g.add([v.index], 1.0, "REPLACE")


def to_bone(obj, bone, frac):
    """Hand the fraction frac(p) of every vertex's skin weights to one bone."""
    vg = obj.vertex_groups
    g = vg.get(bone) or vg.new(name=bone)
    for v in obj.data.vertices:
        t = frac(v.co)
        if t <= 0.0:
            continue
        own = 0.0
        for ge in list(v.groups):
            if ge.group == g.index:
                own = ge.weight
            else:
                vg[ge.group].add([v.index], ge.weight * (1.0 - t), "REPLACE")
        g.add([v.index], own * (1.0 - t) + t, "REPLACE")


def collider(obj, bone):
    """A copy of a hard part weighted wholly to `bone`, for a cloth simulation to collide with (the
    drape poses its colliders by their weights). Remove it after."""
    o = bpy.data.objects.new(obj.name + ".col", obj.data.copy())
    bpy.context.scene.collection.objects.link(o)
    o.vertex_groups.new(name=bone).add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
    return o


def drop(objs):
    for o in objs:
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)


def vline(p0, p1, side):
    """The plane through the front-view line p0 -> p1 ((x, z)), removing the side `side` points to."""
    d = Vector((p1[0] - p0[0], 0, p1[1] - p0[1]))
    n = Vector((-d.z, 0, d.x)).normalized()
    if n.dot(Vector((side[0], 0, side[1]))) < 0:
        n = -n
    return Vector((p0[0], 0, p0[1])), n


def relax(pts, n=3):
    """Laplacian smoothing of an open polyline (or of per-point vectors), its ends held."""
    pts = [Vector(p) for p in pts]
    for _ in range(n):
        pts = [pts[0]] + [(pts[i - 1] + pts[i] * 2 + pts[i + 1]) / 4 for i in range(1, len(pts) - 1)] + [pts[-1]]
    return pts


def resample(pts, step):
    """An open polyline resampled evenly, about `step` apart."""
    P = [Vector(p) for p in pts]
    L = [(P[i + 1] - P[i]).length for i in range(len(P) - 1)]
    tot = sum(L)
    n = max(2, int(round(tot / step)) + 1)
    out, i, acc = [], 0, 0.0
    for k in range(n):
        t = tot * k / (n - 1)
        while i < len(L) - 1 and acc + L[i] < t:
            acc += L[i]
            i += 1
        out.append(P[i].lerp(P[i + 1], min(1.0, (t - acc) / max(L[i], 1e-9))))
    return out


def opening(obj, want):
    """The run of `obj`'s longest boundary loop where want(p) holds (the front edges and collar of an
    open robe, without its hem): [(point, inward direction along the surface)] in order."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    bm.verts.ensure_lookup_table()
    adj = {}
    for e in bm.edges:
        if e.is_boundary:
            a, b = e.verts
            adj.setdefault(a.index, []).append(b.index)
            adj.setdefault(b.index, []).append(a.index)
    seen, loops = set(), []
    for s0 in adj:
        if s0 in seen:
            continue
        loop, prev, cur = [s0], None, s0
        seen.add(s0)
        while True:
            nxt = [n for n in adj[cur] if n != prev and n not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            loop.append(cur)
            seen.add(cur)
        loops.append(loop)

    def length(lp):
        return sum((bm.verts[lp[i]].co - bm.verts[lp[i - 1]].co).length for i in range(len(lp)))
    loop = max(loops, key=length)
    ok = [want(bm.verts[i].co) for i in loop]
    n = len(loop)
    if all(ok):
        start = 0
    else:
        start = next(i for i in range(n) if not ok[i])
    best, cur_run = [], []
    for k in range(1, n + 1):
        i = (start + k) % n
        if ok[i]:
            cur_run.append(i)
            if len(cur_run) > len(best):
                best = list(cur_run)
        else:
            cur_run = []
    out = []
    for j, i in enumerate(best):
        v = bm.verts[loop[i]]
        a = bm.verts[loop[best[max(0, j - 1)]]].co
        b = bm.verts[loop[best[min(len(best) - 1, j + 1)]]].co
        tan = (b - a).normalized()
        inner = [e.other_vert(v).co - v.co for e in v.link_edges if not e.is_boundary]
        d = sum(inner, Vector()) if inner else Vector(v.normal).cross(tan)
        nrm = Vector(v.normal)
        d = d - tan * d.dot(tan) - nrm * d.dot(nrm)
        out.append((v.co.copy(), d.normalized() if d.length > 1e-9 else Vector((0, 0, -1))))
    bm.free()
    return out


def outer_ring(trees, c, z, n, lift, reach=0.5):
    """A closed loop round everything in `trees` at height z, seen from outside, `lift` off it."""
    out = []
    for dv, r in aco.contour(trees, c, z, [360.0 * i / n for i in range(n)], reach):
        out.append((dv, r))
    known = [r for _, r in out if r is not None]
    mean = sum(known) / len(known)
    cc = Vector((c[0], c[1], z))
    return [cc + dv * ((r if r is not None else mean) + lift) for dv, r in out]


def section_hull(trees, c, z, n=72, reach=0.6):
    """The convex hull (2D, about c) of the sections through `trees` at height z, from rays cast in
    from outside: what a skirt hanging there has to clear (both legs at once)."""
    pts = []
    for dv, r in aco.contour(trees, c, z, [360.0 * i / n for i in range(n)], reach):
        if r is not None:
            pts.append((dv.x * r, dv.y * r))
    return real._hull2d(pts) if len(pts) > 3 else None


def hull_radius(hull, phi):
    """Distance from the origin to a convex polygon along direction phi (degrees, 0 = -Y, + toward +X)."""
    a = math.radians(phi)
    dx, dy = math.sin(a), -math.cos(a)
    best = 0.0
    for i in range(len(hull)):
        (x0, y0), (x1, y1) = hull[i - 1], hull[i]
        ex, ey = x1 - x0, y1 - y0
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        t = (x0 * ey - y0 * ex) / den
        s = (x0 * dy - y0 * dx) / den
        if t > 0 and -1e-6 <= s <= 1 + 1e-6:
            best = max(best, t)
    return best


# ------------------------------------------------------------------------------------- the skirt

def skirt(c, man, name, kind, z_top, z_bot, under, gap, slit_z, knee_z, cy=0.0, ease=(0.006, 0.018), flare=0.05,
          nu=30, nv=15, fine=2, trims=(), collide=(), texel=1.0, **sim):
    """A robe's skirt hung from the waist: two panels round the hips and legs (open at the front, `gap`
    (h) degrees either side of centre at height fraction h, split at the back below `slit_z`), made
    from rings round the convex hull of `under` (trees) at each height plus `ease`, never narrower
    than the ring above it and flaring out `flare` at the hem, then draped by the cloth simulation
    pinned at the waist (`real.drape`). Each panel hangs from the hips and follows its own leg more
    and more toward the hem (the shin too below `knee_z`). `trims` [(kind, fn(h, f))] give faces at
    height fraction h and fraction f from the panel's front edge (0) to the back slit (1) another
    material. Returns a real.Garment (game mesh, simulated cloth); registered with `c`."""
    zs = [z_top + (z_bot - z_top) * i / nv for i in range(nv + 1)]
    hulls = [section_hull(under, (0.0, cy), z) for z in zs]
    # Ring radii: the hull plus ease, never narrower than above, flaring toward the hem.
    phis = np.linspace(0.0, 360.0, 145)
    R = []
    prev = None
    for i, (z, hu) in enumerate(zip(zs, hulls)):
        h = i / nv
        e = ease[0] + (ease[1] - ease[0]) * _sm(h, 0.0, 0.5)
        r = np.array([hull_radius(hu, p) if hu else 0.0 for p in phis]) + e
        if prev is not None:
            r = np.maximum(r, prev)
        r = r + flare * h * h * 0.08
        R.append(r)
        prev = r
    for i in range(1, len(R)):
        R[i] = np.maximum(R[i], R[i - 1] + flare * (2 * (i / nv)) / nv)

    def rad(i, phi):
        return float(np.interp(phi % 360.0, phis, R[i]))

    groups = ["hips", "upper_leg.L", "upper_leg.R", "lower_leg.L", "lower_leg.R"]
    gi = {g: k for k, g in enumerate(groups)}
    bm = bmesh.new()
    dl = bm.verts.layers.deform.verify()
    uvl = bm.loops.layers.uv.new("UVMap")
    R_uv = 0.2

    def weights(z, side):
        h = _sm((z_top - z) / (z_top - z_bot), 0.0, 1.0)
        leg = 0.85 * h
        w = {"hips": 1.0 - leg}
        f = _sm((knee_z - z) / 0.2, 0.0, 1.0) * 0.4
        for s, share in side.items():
            w["lower_leg." + s] = leg * share * f
            w["upper_leg." + s] = leg * share * (1 - f)
        return w

    grid = {}
    cols = {}
    for pi, (s, a_of) in enumerate((("L", lambda i: (gap(i / nv), 180.0)), ("R", lambda i: (180.0, 360.0 - gap(i / nv))))):
        G = []
        for i, z in enumerate(zs):
            a0, a1 = a_of(i)
            row = []
            for j in range(nu + 1):
                phi = a0 + (a1 - a0) * j / nu
                shared = (s == "R" and j == 0 and z > slit_z)
                if shared:
                    row.append(grid["L"][i][nu])
                    continue
                r = rad(i, phi)
                a = math.radians(phi)
                v = bm.verts.new((r * math.sin(a), cy - r * math.cos(a), z))
                side = {s: 1.0}
                if s == "L" and j == nu and z > slit_z:
                    side = {"L": 0.5, "R": 0.5}
                for gname, wt in weights(z, side).items():
                    if wt > 1e-4:
                        v[dl][gi[gname]] = wt
                row.append(v)
            G.append(row)
        grid[s] = G
        cols[s] = a_of
    mats = [kind] + [k for k, _ in trims]
    for s in ("L", "R"):
        G = grid[s]
        for i in range(nv):
            for j in range(nu):
                q = (G[i][j], G[i][j + 1], G[i + 1][j + 1], G[i + 1][j])
                try:
                    f = bm.faces.new(q)
                except ValueError:
                    continue
                h = (i + 0.5) / nv
                fr = (j + 0.5) / nu if s == "L" else 1.0 - (j + 0.5) / nu
                for k, (_, fn) in enumerate(trims):
                    if fn(h, fr):
                        f.material_index = k + 1
                for l in f.loops:
                    p = l.vert.co
                    phi = math.degrees(math.atan2(p.x, -(p.y - cy))) % 360.0
                    if s == "R" and phi < 90.0:
                        phi += 360.0
                    if s == "L" and phi > 270.0:
                        phi -= 360.0
                    l[uvl].uv = (math.radians(phi) * R_uv, p.z)
    bm.normal_update()
    if sum(f.normal.dot(f.calc_center_median() - Vector((0, cy, f.calc_center_median().z))) for f in bm.faces) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    coarse = [v.co.copy() for v in bm.verts]
    low = real._bm_obj(name, bm.copy(), None, groups)
    if fine:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=fine, use_grid_fill=True, smooth=0.0)
    kd = KDTree(len(bm.verts))
    for i, v in enumerate(bm.verts):
        kd.insert(v.co, i)
    kd.balance()
    where = np.array([kd.find(p)[1] for p in coarse])
    high = real._bm_obj(name + ".high", bm, None, groups)
    for o in (low, high):
        for k in mats:
            o.data.materials.append(real.mat(k))
    if simulated(name):
        real.drape(c, man, high, lambda p: 1.0 if p.z > z_top - 0.035 else 0.0, None, collide=collide, **sim)
    co = np.zeros(len(high.data.vertices) * 3)
    high.data.vertices.foreach_get("co", co)
    low.data.vertices.foreach_set("co", co.reshape(-1, 3)[where].ravel())
    low.data.update()
    real.seam_attrs(high, uv_seams=False)
    real.seam_attrs(low, uv_seams=False)
    low["texel"] = texel
    c.parts.append((low, "DONE", None))
    c.detail(low, [high], ext=0.012, ray=0.03)
    return real.Garment(low, high)


# ------------------------------------------------------------------------------------- head gear

def head_gear(c, man, hc, arm):
    """Visor band, ocular implant, rebreather jaw plate, ear modules, crown circlet and halo antennas,
    skull ports. Returns (face envelope, skull envelope, covered(p) for the skin under the mask, the
    cable ends at the back of the skull [(point, lon)])."""
    dom = kit.dominant(man.low)
    me = man.low.data
    co = [v.co.copy() for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons if sum(dom[i] in ("head", "neck") for i in p.vertices) * 2 > len(p.vertices)]
    head = BVHTree.FromPolygons(co, polys)
    O = hc + Vector((0, -0.016, -0.018))
    face = aco.Env([head], O, reach=0.22, lat=(-80.0, 90.0), dlat=3.0, dlon=4.0, spread=11.0, blur=8.0, floor=0.004)
    skull = aco.Env([head], O, reach=0.22, lat=(-80.0, 90.0), dlat=3.0, dlon=4.0, spread=5.0, blur=4.0, floor=0.0015)

    # ---- visor band across the eyes: a black frame from ear to ear, smoked glass, the ocular implant.
    def v_lo(lo):
        return -9.0 + 5.0 * _sm(abs(lo), 45, 96)

    def v_hi(lo):
        return 17.0 - 8.0 * _sm(abs(lo), 45, 96)
    VIS = 0.0105
    frame = face.patch("visor_frame", "black", -100.0, 100.0, v_lo, v_hi, VIS, 0.0055, nu=40, nv=4, bevel=0.0014)
    c.rigid(frame, "head")
    glass = face.patch("visor", "glass", -84.0, 84.0, lambda lo: v_lo(lo) + 2.6, lambda lo: v_hi(lo) - 2.6, VIS + 0.0016, 0.0022,
                       nu=32, nv=3, bevel=0.0)
    c.rigid(glass, "head")
    # Ocular implant over the right eye, through the glass.
    p = face.P(3.3, -25.0, VIS)
    n = face.normal(3.3, -25.0, VIS)
    imp = [kit.cyl("ocular", p - n * 0.004, p + n * 0.013, 0.0152, "gunmetal", segs=20, bevel=0.0012, bsegs=1),
           kit.cyl("ocular_ring", p + n * 0.0125, p + n * 0.0145, 0.0118, "glow_red", segs=20, bevel=0),
           kit.cyl("ocular_lens", p + n * 0.0135, p + n * 0.0158, 0.0072, "glass", segs=16, bevel=0)]
    kit.cut(imp[0], kit.cyl("bore", p + n * 0.009, p + n * 0.02, 0.0122, "steel", segs=20, bevel=0))
    for o in imp:
        c.rigid(o, "head")
    c.rigid(aco.ring("ocular_bezel", p + n * 0.0035, n, 0.0195, 0.0148, 0.0055, BONE, segs=20), "head")
    side = n.cross(Vector((0, 0, 1))).normalized()
    upv = side.cross(n).normalized()
    for ang in (30, 150, 270):
        a = math.radians(ang)
        c.rigid(aco.screw(p + n * 0.006 + (side * math.cos(a) + upv * math.sin(a)) * 0.0172, n, r=0.0016), "head")
    # A second, small lens out at the temple.
    p2 = face.P(9.0, -52.0, VIS + 0.001)
    n2 = face.normal(9.0, -52.0, VIS)
    c.rigid(kit.cyl("ocular_aux", p2 - n2 * 0.002, p2 + n2 * 0.006, 0.0062, "gunmetal", segs=14, bevel=0.0008, bsegs=1), "head")
    c.rigid(kit.cyl("ocular_aux_lens", p2 + n2 * 0.0055, p2 + n2 * 0.0068, 0.0038, "glow_red", segs=12, bevel=0), "head")

    # ---- rebreather mask: a bone snout over the nose, mouth and chin, tucked under the visor, held by
    # a black strap from each side back to the ear module. Only the cheekbones and jaw show skin.
    def chin(lo):
        return -58.0 + 18.0 * _sm(abs(lo), 10, 64)

    def j_hi(lo):
        return -9.6 - 13.0 * _sm(abs(lo), 14, 52)
    MASK = 60.0

    def jaw_off(la, lo):
        keel = 0.0026 * math.exp(-(lo / 5.0) ** 2) * _sm(-14.0 - la, 0.0, 14.0)
        snout = 0.0075 * math.exp(-((la + 28.0) / 15.0) ** 2 - (lo / 22.0) ** 2)
        return 0.0092 + keel + snout
    jaw = face.patch("jaw_plate", BONE, -MASK, MASK, chin, j_hi, jaw_off, 0.0058, nu=34, nv=12, inner="regime_pad", bevel=0.0018)
    arm.add(jaw, "head")

    def at(la, lo, off):
        nn = face.normal(la, lo, off)
        return face.P(la, lo, off) + nn * 0.1, -nn
    o_, d_ = at(-49, 15, jaw_off(-49, 15))
    arm.etch(jaw, aco.tick_rows(91, 2, 0.018, 0.003, unit=0.0009), o_, d_)
    o_, d_ = at(-49, -15, jaw_off(-49, -15))
    arm.etch(jaw, aco.code_rows(["7F"], 0.0058), o_, d_)
    o_, d_ = at(-53, 0, jaw_off(-53, 0))
    arm.etch(jaw, aco.code_rows(["∴"], 0.011), o_, d_)
    for sx in (1, -1):
        la, lo = -35.0, sx * 50.0
        arm.detail(aco.screw(face.P(la, lo, jaw_off(la, lo)), face.normal(la, lo, jaw_off(la, lo)), r=0.0028))
        # The strap: from under the mask's side edge, over the cheek, under the ear module.
        lo0, lo1 = sorted((sx * (MASK - 6.0), sx * 100.0))

        def mid(lo):
            return -35.0 + 29.0 * _sm(abs(lo), MASK - 6.0, 100.0)
        c.rigid(skull.patch("mask_strap", "black", lo0, lo1, lambda lo: mid(lo) - 3.2, lambda lo: mid(lo) + 3.2, 0.0024, 0.0022,
                            nu=12, nv=1, bevel=0.0006), "head")
        q = skull.P(mid(sx * 80.0), sx * 80.0, 0.0046)
        nq = skull.normal(mid(sx * 80.0), sx * 80.0, 0.0046)
        sd = (skull.P(mid(sx * 84.0), sx * 84.0, 0.0046) - skull.P(mid(sx * 76.0), sx * 76.0, 0.0046)).normalized()
        bk = kit.block("strap_buckle", (0, 0, 0), (0.016, 0.0035, 0.013), "gunmetal", bevel=0.0009)
        kit.hs.apply_modifiers(bk)
        bk.data.transform(pmc.frame(q, nq, nq.cross(sd)))
        c.rigid(bk, "head")
    # Grille vents either side of the snout, and the twin filters further out on the jaw.
    for sx in (1, -1):
        lo0, lo1 = sorted((sx * 8.0, sx * 22.0))
        c.rigid(face.patch("vent", "black", lo0, lo1, lambda lo: -41.0, lambda lo: -24.0, lambda la, lo: jaw_off(la, lo) + 0.0012, 0.003,
                           nu=5, nv=4, bevel=0.0008, segs=1), "head")
        for k in range(4):
            la0 = -39.0 + k * 4.0
            c.rigid(face.patch("vent_slat", "gunmetal", lo0 + 1.5, lo1 - 1.5, lambda lo, la0=la0: la0, lambda lo, la0=la0: la0 + 1.4,
                               lambda la, lo: jaw_off(la, lo) + 0.0026, 0.0016, nu=4, nv=1, bevel=0.0), "head")
        la, lo = -46.0, sx * 34.0
        q = face.P(la, lo, jaw_off(la, lo) - 0.002)
        nq = face.normal(la, lo, jaw_off(la, lo))
        ax = (nq + Vector((0, 0, -0.75))).normalized()
        can = kit.cyl("filter", q - ax * 0.002, q + ax * 0.021, 0.0118, "gunmetal", segs=18, bevel=0.0012, bsegs=1)
        kit.cut(can, *[kit.cyl("filter_groove", q + ax * t, q + ax * (t + 0.0016), 0.015, "steel", segs=18, bevel=0) for t in (0.008, 0.0125, 0.017)],
                solver="MANIFOLD")
        c.rigid(can, "head")
        c.rigid(kit.cyl("filter_cap", q + ax * 0.0205, q + ax * 0.0255, 0.0125, BONE, segs=18, bevel=0.0012, bsegs=1), "head")
        c.rigid(kit.cyl("filter_grid", q + ax * 0.025, q + ax * 0.0265, 0.008, "black", segs=14, bevel=0), "head")
        c.rigid(aco.ring("filter_collar", q + ax * 0.0015, ax, 0.015, 0.011, 0.005, "black", segs=18), "head")

    # ---- comms modules over the ears: the visor band and the jaw plate end under them.
    for sx in (1, -1):
        lo = sx * 104.0
        q = face.P(-1.0, lo, 0.003)
        nq = face.normal(-1.0, lo, 0.003)
        c.rigid(kit.cyl("ear", q - nq * 0.004, q + nq * 0.015, 0.033, "gunmetal", segs=24, bevel=0.002, bsegs=1), "head")
        c.rigid(kit.cyl("ear_cap", q + nq * 0.0145, q + nq * 0.0195, 0.024, "black", segs=24, bevel=0.0012, bsegs=1), "head")
        c.rigid(aco.ring("ear_trim", q + nq * 0.008, nq, 0.0362, 0.0318, 0.008, BONE, segs=24), "head")
        sd = nq.cross(Vector((0, 0, 1))).normalized()
        c.rigid(kit.cyl("ear_led", q + nq * 0.0185 + sd * 0.012 * sx + Vector((0, 0, 0.012)), q + nq * 0.021 + sd * 0.012 * sx + Vector((0, 0, 0.012)),
                        0.0028, "glow_red", segs=10, bevel=0), "head")
        for ang in (90, 270):
            a = math.radians(ang)
            c.rigid(aco.screw(q + nq * 0.015 + (sd * math.cos(a) + Vector((0, 0, math.sin(a)))) * 0.0285, nq, r=0.0019), "head")

    # ---- crown: a gunmetal circlet round the skull, the bone brow plaque, the halo of antennas.
    def cl(lo):
        return 33.0 - 9.0 * _sm(abs(lo), 60, 170)
    CIRC = 0.0072
    circ = skull.patch("circlet", "gunmetal", -180.0, 180.0, lambda lo: cl(lo) - 2.5, lambda lo: cl(lo) + 2.5, CIRC, 0.0052, nu=72, nv=2,
                       closed=True, bevel=0.0012)
    c.rigid(circ, "head")
    c.rigid(skull.patch("circlet_trim", BONE, -180.0, 180.0, lambda lo: cl(lo) + 1.2, lambda lo: cl(lo) + 2.1, CIRC + 0.0016, 0.0016,
                        nu=72, nv=1, closed=True, bevel=0.0), "head")
    plaque = skull.patch("crown_plaque", BONE, -13.0, 13.0, lambda lo: cl(lo) - 4.5 + 2.0 * _sm(abs(lo), 6, 13),
                         lambda lo: cl(lo) + 9.0 - 6.0 * _sm(abs(lo), 3, 13), CIRC + 0.003, 0.0045, nu=8, nv=4, bevel=0.0012)
    arm.add(plaque, "head")
    nn = skull.normal(cl(0) + 2.5, 0, CIRC + 0.003)
    arm.etch(plaque, aco.code_rows(["∴"], 0.016), skull.P(cl(0) + 2.0, 0, CIRC + 0.003) + nn * 0.1, -nn)
    tips = []
    lons = [s * (66.0 + 114.0 * i / 6) for i in range(7) for s in ((1, -1) if i < 6 else (1,))]
    for lo in sorted(lons, key=lambda x: x % 360.0):
        back = _sm(abs(lo), 62, 180)
        base = skull.P(cl(lo) + 0.6, lo, CIRC + 0.002)
        h = skull.dir(0.0, lo)
        tilt = math.radians(14.0 + 40.0 * (1.0 - back))
        dv = (Vector((0, 0, 1)) * math.cos(tilt) + h * math.sin(tilt)).normalized()
        L = 0.07 + 0.115 * back ** 1.3
        bars_ = ((0.82, 0.009),) if back > 0.9 else ()
        c.rigid(aco.antenna("crown_antenna", base, base + dv * L, r=0.0024, bars=bars_), "head")
        tips.append((lo % 360.0, base + dv * L * 0.7))
    tips.sort()
    hoop = [p for _, p in tips]
    ends = [hoop[0] + (hoop[0] - hoop[1]) * 0.5, hoop[-1] + (hoop[-1] - hoop[-2]) * 0.5]
    c.rigid(kit.rope("halo", [ends[0]] + hoop + [ends[1]], 0.0021, "gunmetal"), "head")

    # ---- skull ports: gunmetal implants with bone-lipped sockets; the back ones take cables.
    ports = []
    for la, lo in ((50.0, 146.0), (50.0, -146.0), (44.0, -116.0), (68.0, 180.0)):
        q = skull.P(la, lo, 0.0)
        nq = skull.normal(la, lo, 0.0)
        c.rigid(aco.socket("skull_port", q - nq * 0.002, nq, r=0.0078, material="gunmetal", lip=BONE), "head")
        c.rigid(aco.ring("port_flange", q + nq * 0.0004, nq, 0.0152, 0.0085, 0.0022, "gunmetal", segs=16), "head")
        sd = nq.cross(Vector((0, 0, 1)) if abs(nq.z) < 0.9 else Vector((1, 0, 0))).normalized()
        u2 = sd.cross(nq).normalized()
        for ang in (45, 225):
            a = math.radians(ang)
            c.rigid(aco.screw(q + nq * 0.0012 + (sd * math.cos(a) + u2 * math.sin(a)) * 0.0128, nq, r=0.0014), "head")
        ports.append((la, lo, q + nq * 0.012))
    # The ocular implant's lead along the top of the visor band to the temple port.
    pts = [p + side * 0.012 + upv * 0.006 + n * 0.006]
    for la, lo in ((v_hi(-60) - 1.0, -62.0), (v_hi(-86) + 1.5, -88.0), (30.0, -108.0)):
        pts.append(face.P(la, lo, VIS + 0.003) if la < 25 else skull.P(la, lo, 0.004))
    pts.append(ports[2][2])
    c.rigid(kit.rope("ocular_lead", pmc.smooth_path(pts, 3), 0.0018, "black"), "head")

    def covered(p):
        """The skin under the visor, the mask and the ear modules (well inside their edges)."""
        d = Vector(p) - O
        if d.length < 1e-6:
            return True
        la = math.degrees(math.asin(max(-1.0, min(1.0, d.normalized().z))))
        lo = math.degrees(math.atan2(d.x, -d.y))
        if abs(lo) < 95 and v_lo(lo) + 5 < la < v_hi(lo) - 4:
            return True
        if abs(lo) < MASK - 9 and chin(lo) + 6 < la < j_hi(lo) - 7:
            return True
        return 92 < abs(lo) < 116 and abs(la + 1.0) < 13
    return face, skull, covered, ports, cl


# ------------------------------------------------------------------------------------------ build

def build():
    b = real.Anatomy(height=1.85, sole=0.032)
    c = real.begin("zealot", b)
    man = real.body(c, skin="zealot_skin", stubble=0.0, face_detail=2.4)
    J, seg, sm = b.j, kit.seg_dist, real._smooth
    lead = real.bones_at(man)
    armpit = b.at("armpit")
    E, u = man.face()
    hc = man.head_center()
    shaved_scalp(man, E, u)
    head_arm = aco.Armour(c, "armour_head", texel=2.4)
    torso_arm = aco.Armour(c, "armour_torso", texel=2.2)
    limb_arm = aco.Armour(c, "armour_limbs", texel=2.0)

    # Only the head's skin shows: it keeps the face detail, the rest (left under the hems) few texels.
    def texel(obj):
        dom = kit.dominant(obj)

        def f(isl):
            head = sum(1 for fc in isl if sum(dom[v.index] in kit.HEAD_GROUP for v in fc.verts) * 2 > len(fc.verts))
            return 2.4 if head * 2 > len(isl) else 0.3
        return f
    surfaces._TEXEL_FN[man.low.name] = texel

    # The eyes are behind the visor band.
    for e in man.eyes:
        c.parts = [p for p in c.parts if p[0] is not e]
    face, skull, covered, ports, cl = head_gear(c, man, hc, head_arm)
    for e in man.eyes:
        bpy.data.objects.remove(e, do_unlink=True)
    c.cover({"head", "neck"}, covered)

    # ---------------------------------------------------------------- tattoos, inked into the skin
    ink = high_of(c, man.low)
    hi_t = aco.bvh(man.high)
    for (la, lo, items, up) in ((12.0, 134.0, bars(aco.barcode(7, 0.046, 0.016, unit=0.0013)), (0, 0, 1)),
                                (-34.0, 180.0, bars(aco.barcode(3, 0.034, 0.015, unit=0.0012)), (0, 0, 1)),
                                (8.0, -146.0, bars(aco.tick_rows(17, 4, 0.032, 0.0032, unit=0.0011, lead=1.9)), (0, 0, 1))):
        dv = skull.dir(la, lo)
        ink.append(decal("tattoo", hi_t, items, skull.O + dv * 0.3, -dv, up))
    # The officer's number under the nape barcode.
    dv = skull.dir(-40.0, 180.0)
    ink.append(decal("tattoo", hi_t, bars(aco.tick_rows(23, 1, 0.03, 0.0022, unit=0.0011)), skull.O + dv * 0.3, -dv))

    # ---------------------------------------------------------------- gloves and boots
    gl = real.gloves(c, man, "glove", cuff=0.045)
    tg = pmc.tree(gl)
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
        mid = sum(mcp, Vector()) / 4
        loc, _ = pmc.hit(tg, mid + back * 0.12, -back)
        loc = loc if loc is not None else mid + back * 0.02
        guard = kit.block("knuckle", (0, 0, 0), (0.074, 0.011, 0.024), BONE, bevel=0.0028)
        kit.cut(guard, *[kit.block("groove", (x, 0.006, 0), (0.004, 0.004, 0.03), "steel", bevel=0) for x in (-0.019, 0.0, 0.019)])
        M = Matrix((T, back, Lh)).transposed().to_4x4()
        M.translation = loc + back * 0.0055 - Lh * 0.004
        guard.data.transform(M)
        c.rigid(guard, "hand." + s)
        ax = J("hand." + s, 0.0) - J("forearm." + s, 0.0)
        cc = J("hand." + s, 0.0) - ax.normalized() * 0.024
        r = pmc._radius(tg, cc, ax)
        c.rigid(pmc.band("glove_cuff", cc, (r + 0.003, r * 0.82 + 0.003), 0.032, 0.004, "glove", axis=ax), "forearm." + s)
    real.boots(c, man, "boot", sole_kind="rubber", trim="rubber", top=0.19, lace="webbing", tab="accent")

    # ---------------------------------------------------------------- undersuit: shirt
    neck = J("neck", 0.0)
    belt_z = b.hip_z + 0.065
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
            return 0.007 - 0.003 * float(sm(tuck + 0.03 - p.z, 0.0, 0.03))
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
    shirt = real.garment(c, man, "shirt", "ripstop.secondary", lambda p: lead(p) in TORSO | ARMS | THIGHS | {"neck"} and p.z > waist - 0.05,
                         cuts, ease=ease, pin=pin if simulated("shirt") else None, slack=slack, bend=12.0, texel=1.0,
                         trims=[("knit.secondary", lambda p: (above(neckline, p) and lead(p) not in ARMS) or cuff(p))])
    c.hide_under(shirt.low, 0.05, 2)
    tshirt = pmc.tree(shirt.low)

    # ---------------------------------------------------------------- undersuit: trousers
    top_z = tuck
    hem = b.sole + 0.19 - 0.03
    LEGS = THIGHS | SHINS

    def t_ease(p):
        band = 0.003 * (1 - sm(top_z - p.z, 0.02, 0.07))
        return 0.011 + band + 0.004 * sm(top_z - p.z, 0.04, 0.2) + 0.007 * sm(J("lower_leg.L", 0.0).z - p.z, 0.0, 0.15)

    def t_pin(p):
        return 1.0 if p.z > top_z - 0.045 or p.z < hem + 0.018 else 0.0

    def t_slack(p):
        return sm(hem + 0.13 - p.z, 0.0, 0.1)

    trousers = real.garment(c, man, "trousers", "ripstop.secondary",
                            lambda p: lead(p) in LEGS | {"hips", "spine"} and hem - 0.03 < p.z < top_z + 0.03,
                            [((0, 0, top_z), (0, 0, 1)), ((0, 0, hem), (0, 0, -1), lambda p: lead(p) in LEGS)],
                            ease=t_ease, pin=t_pin if simulated("trousers") else None, slack=t_slack, bend=14.0, texel=0.9)
    c.hide_under(trousers.low, 0.06, 2)
    tt = pmc.tree(trousers.low)

    # ---------------------------------------------------------------- the plate: cuirass, faulds, gorget
    dz = (armpit - 0.198) - 1.03

    def Z(z):
        return z + dz
    f_plate = kit.rounded([(-0.124, Z(1.105)), (0.124, Z(1.105)), (0.13, Z(1.29)), (0.084, Z(1.386)), (-0.084, Z(1.386)), (-0.13, Z(1.29))], 0.02)
    pf = aco.Plate([tshirt], f_plate, -1, 0.006)
    PL = 0.016
    fp = pf.patch("breastplate", BONE, f_plate, PL, 0.0095, nu=18, nv=16, bevel=0.003)
    torso_arm.add(fp, "chest")
    torso_arm.detail(pf.border(f_plate, PL))
    keel_o = kit.rounded([(-0.011, Z(1.12)), (0.011, Z(1.12)), (0.011, Z(1.37)), (-0.011, Z(1.37))], 0.006)
    keel = pf.patch("keel", BONE, keel_o, PL + 0.0055, 0.0065, nu=3, nv=12, bevel=0.0018)
    torso_arm.add(keel, "chest")
    for sx in (1, -1):
        p = pf.P(sx * 0.064, Z(1.30), PL)
        torso_arm.etch(fp, aco.code_rows(aco.scripture(5 + sx, 5, 7), 0.0102), p + Vector((0, -0.1, 0)), (0, 1, 0))
        p = pf.P(sx * 0.07, Z(1.165), PL)
        torso_arm.etch(fp, aco.tick_rows(9 + sx, 3, 0.07, 0.0046), p + Vector((0, -0.1, 0)), (0, 1, 0))
    p = pf.P(0.0, Z(1.215), PL + 0.0055)
    torso_arm.etch(keel, aco.code_rows(["∴"], 0.016), p + Vector((0, -0.1, 0)), (0, 1, 0))
    for x, z in ((-0.1, Z(1.14)), (0.1, Z(1.14)), (-0.1, Z(1.29)), (0.1, Z(1.29))):
        torso_arm.detail(aco.screw(pf.P(x, z, PL), pf.normal(x, z), r=0.0042))
    plates = [(fp, 0.0095, "chest"), (keel, 0.0065, "chest")]
    # Fauld lames down the belly to the belt, shingled: each upper one over the one below.
    for i, (z0, z1, w) in enumerate(((1.042, 1.112, 0.118), (0.982, 1.05, 0.114), (0.93, 0.99, 0.11))):
        o_ = kit.rounded([(-w, Z(z0)), (w, Z(z0)), (w + 0.004, Z(z1)), (-w - 0.004, Z(z1))], 0.012)
        pl = aco.Plate([tshirt, tt], o_, -1, 0.006)
        lame = pl.patch("fauld", BONE, o_, PL - 0.003 - 0.0028 * i, 0.007, nu=12, nv=3, bevel=0.0022)
        lb_ = "spine" if i == 0 else "hips"
        torso_arm.add(lame, lb_)
        torso_arm.etch(lame, aco.tick_rows(31 + i, 1, 0.16, 0.0042), pl.P(0, Z((z0 + z1) / 2), PL) + Vector((0, -0.1, 0)), (0, 1, 0))
        plates.append((lame, 0.007, lb_))
    # Gorget: a bone collar round the front of the throat, up under the jaw plate.
    nt_ = aco.region_tree(man.low, {"neck", "head", "chest"})
    gt = aco.Tube([nt_, tshirt], J("neck", -0.3), J("neck", 1.0), front=(0, -1, 0), t=(-0.1, 1.0), nt=20, nphi=48, reach=0.13,
                  spread=0.02, blur=0.014)
    gorget = gt.patch("gorget", BONE, 0.08, 0.66, 0.0, 104.0, 0.0065, 0.0055, nu=18, nv=5, corner=0.0, bevel=0.0018)
    torso_arm.add(gorget, "chest")
    for sx in (1, -1):
        torso_arm.detail(aco.screw(gt.P(0.4, sx * 80.0, 0.0065), gt.d(sx * 80.0), r=0.003))
    torso_arm.etch(gorget, aco.tick_rows(41, 2, 0.05, 0.0034), gt.P(0.36, 0.0, 0.0065) + gt.d(0.0) * 0.1, -gt.d(0.0), up=J("neck", 1.0) - J("neck", 0.0))
    plates.append((gorget, 0.0055, "chest"))
    # The shirt under the plate moves with the plate (the chest's shoulder weights would bulge it
    # through when the arms come up).
    bind_under(shirt.low, plates, 0.07, lambda p: not on_arm(p))

    # ---------------------------------------------------------------- leg plates (under the skirt)
    leg_cols = []
    for s, sx in (("L", 1), ("R", -1)):
        ll = "lower_leg." + s
        ll0, ll1 = J(ll, 0.0), J(ll, 1.0)
        ts = aco.Tube([tt], ll0, ll1, t=(-0.1, 0.8), nt=30, nphi=60, reach=0.15, spread=0.03, blur=0.022)
        shin = ts.patch("shin_guard", BONE, 0.13, 0.64, 4 * sx, 58, 0.009, 0.0065, nu=10, nv=9, corner=3.0, bulge=0.004, bevel=0.0025)
        limb_arm.add(shin, ll)
        n = ts.d(4 * sx)
        limb_arm.etch(shin, aco.code_rows(aco.scripture(73 + sx, 8, 3), 0.0092), ts.P(0.42, 4 * sx, 0.009) + n * 0.1, -n, up=(ll0 - ll1).normalized())
        kn = ll0 + Vector((0, 0.012, 0.004))
        kenv = aco.Env([tt, shin], kn, Z=(0, -1, 0.12), F=(0, 0, 1), reach=0.14, lat=(0.0, 90.0), dlat=4.0, dlon=8.0, spread=16.0, blur=10.0,
                       floor=0.004)
        knee = kenv.patch("knee_cap", BONE, -180.0, 180.0, lambda lo: 50.0 - 10.0 * math.cos(math.radians(lo)) ** 2, lambda lo: 84.0, 0.011,
                          0.0065, nu=16, nv=4, closed=True, pole=True, inner="regime_pad", bevel=0.0022)
        limb_arm.add(knee, ll)
        kp = kenv.P(90, 0, 0.011)
        kn_n = kenv.normal(90, 0, 0.011, h=4.0)
        c.rigid(kit.cyl("knee_boss", kp - kn_n * 0.003, kp + kn_n * 0.0045, 0.013, "gunmetal", segs=6, bevel=0.0012, bsegs=1), ll)
        ts2 = aco.Tube([tt], ll0, ll1, hard=[shin], t=(0.1, 0.7), nt=13, nphi=36, reach=0.15)
        for tq in (0.24, 0.56):
            c.rigid(aco.strap_ring("shin_strap", ts2.ring(tq, 0.0015, n=22), ll0.lerp(ll1, tq), ll1 - ll0, 0.024, 0.0045, "accent"), ll)
        leg_cols += [collider(shin, ll), collider(knee, ll)]

    # ---------------------------------------------------------------- the robe (upper)
    r_hem = belt_z - 0.012          # the robe's body ends under the belt
    collar = (Vector((0, 0, neck.z + 0.04)), Vector((0, -0.42, 1)).normalized())   # standing collar, higher at the back
    z_chest = Z(1.27)
    edge_pts = [(0.05, collar[0].z + 0.03), (0.088, z_chest), (0.074, r_hem - 0.02)]

    def edge_x(z):
        (x0, z0), (x1, z1), (x2, z2) = edge_pts
        if z >= z1:
            return x1 + (x0 - x1) * (z - z1) / (z0 - z1)
        return x1 + (x2 - x1) * (z1 - z) / (z1 - z2)

    def front(p):
        return p.y < -0.025

    r_cuts = [(collar[0], collar[1])]
    for s, sx in (("L", 1), ("R", -1)):
        a, e = J("upper_arm." + s, 0.0), J("upper_arm." + s, 1.0)
        r_cuts.append((a.lerp(e, 0.72), e - a, lambda p, a=a, e=e: on_arm(p) and seg(p, a, e) < 0.1))
        for (p0, p1), zr in (((edge_pts[0], edge_pts[1]), (z_chest - 0.01, 9.0)), ((edge_pts[1], edge_pts[2]), (-9.0, z_chest + 0.01))):
            pl = vline((sx * p0[0], p0[1]), (sx * p1[0], p1[1]), (-sx, 0))
            r_cuts.append(pl + (lambda p, sx=sx, zr=zr: front(p) and p.x * sx > -0.004 and zr[0] < p.z < zr[1] and not on_arm(p),))
    r_cuts.append(((0, 0, r_hem), (0, 0, -1), lambda p: not on_arm(p)))

    def r_keep(p):
        if not (lead(p) in TORSO | UPPER_ARMS | {"neck"} and p.z > r_hem - 0.05):
            return False
        return not (front(p) and abs(p.x) < edge_x(p.z) - 0.02 and not on_arm(p))
    hard_t = [(pmc.tree(o), th) for o, th, _ in plates]

    def r_ease(p):
        e = 0.013 if not on_arm(p) else 0.017
        _, nrm, _, _ = man.tree.find_nearest(p)
        loc, _, _, d = tshirt.ray_cast(p + nrm * 0.001, nrm, 0.1)
        if loc is not None:
            e = max(e, d + 0.008)
        for t, th in hard_t:
            loc, _, _, d = t.ray_cast(p + nrm * 0.001, nrm, 0.15)
            if loc is not None:
                e = max(e, d + th + 0.009)
        # The cuirass stands off the chest like a board: the front panels go out over it, never
        # under it (out along the normal until nothing of the plate is in front of the point), and
        # round its edges (out until clear of every plate).
        if front(p) and not on_arm(p):
            fwd = Vector((0, -1, 0))
            for _ in range(30):
                q = p + nrm * e
                if all(t.ray_cast(q, fwd, 0.3)[0] is None for t, _ in hard_t):
                    break
                e += 0.003
        for _ in range(6):
            q = p + nrm * e
            push = 0.0
            for t, th in hard_t:
                loc, _, _, d = t.find_nearest(q, 0.012)
                if loc is not None:
                    push = max(push, 0.0105 - d)
            if push <= 0.0:
                break
            e += push
        return e

    def r_pin(p):
        """The yoke over the shoulders, the waist under the belt and the front panels over the
        cuirass are held to the cut; the sleeves, the sides and the back drape."""
        if on_arm(p):
            return 0.0
        if p.z > armpit + 0.01 or p.z < r_hem + 0.03:
            return 1.0
        if front(p):
            # The front panels lie on the cuirass: they do not hang, and must not sink into it.
            return 1.0 - _sm(abs(p.x), 0.16, 0.2)
        return 0.0

    tcols = [collider(o, bn) for o, _, bn in plates]
    robe = real.garment(c, man, "robe", "leather.primary", r_keep, r_cuts, ease=r_ease, smooth=1, pin=r_pin if simulated("robe") else None, slack=None,
                        bend=40.0, stiff=2.0, mass=0.35, texel=1.1, collide=[shirt.low] + tcols)
    drop(tcols)
    for o in (robe.low, robe.high):
        over = tent(o, [o_ for o_, _, _ in plates if o_ is not gorget], lambda p: front(p) and not on_arm(p) and p.z < neck.z - 0.03)
    # Over the cuirass the robe moves with the chest like the plate under it (the skin's shoulder and
    # arm weights would drag its front panels into the plate when the arms come forward).
    def on_chest(p):
        if front(p) and over(p) and Z(1.1) < p.z < neck.z - 0.03:
            return 1.0
        if on_arm(p):
            return 0.0
        if p.z > armpit - 0.02 and abs(p.x) < 0.11:
            # The collar and the yoke between the shoulders: they stay with the chest when the arms
            # come up (the skin's shoulder weights would crumple the stole there).
            return 1.0 - _sm(abs(p.x), 0.08, 0.11)
        return (_sm(p.z, Z(1.07), Z(1.12)) * (1.0 - _sm(p.z, armpit, armpit + 0.05)) * (1.0 - _sm(abs(p.x), 0.155, 0.215))
                * (1.0 if front(p) else 0.6))
    to_bone(robe.low, "chest", on_chest)
    c.hide_under(robe.low, 0.06, 2)
    trobe = pmc.tree(robe.low)
    # Embroidery: the cult's ring and mark between the shoulder blades, scripture down the back and
    # down both front bands of the stole, in bone-white thread.
    emb = high_of(c, robe.low)
    rh = aco.bvh(robe.high)
    emb.append(aco.project(robe.high, aco.sigil(0.052, n=36, w=0.0042) + aco.code_rows(["∴"], 0.05), (0, 0.5, Z(1.32)), (0, -1, 0),
                           lift=0.0004, material="zealot_thread", name="embroidery", tree=rh))
    emb.append(aco.project(robe.high, aco.code_rows(aco.scripture(83, 7, 9), 0.0135), (0, 0.5, Z(1.155)), (0, -1, 0), lift=0.0004,
                           material="zealot_thread", name="embroidery", tree=rh))

    # The stole: a red band round the collar and down both front edges of the draped robe, along its
    # cut edge, with scripture embroidered down its front; it moves with the robe under it.
    def r_nrm(p):
        _, nor, _, _ = trobe.find_nearest(p)
        q = Vector((0, -0.01, p.z))
        return nor if nor.dot(Vector(p) - q) > 0 else -nor
    run = opening(robe.low, lambda p: p.z > r_hem + 0.035 and not on_arm(p))
    edge = relax(resample(relax([v for v, _ in run], 2), 0.012), 30)
    pts, nrms = [], []
    prev = None
    for i, v in enumerate(edge):
        tan = (edge[min(len(edge) - 1, i + 1)] - edge[max(0, i - 1)]).normalized()
        nr = r_nrm(v)
        side = tan.cross(nr).normalized()
        if prev is None:
            # Into the cloth: the robe is right under that side, the other side is open.
            d1 = (trobe.find_nearest(v + side * 0.02)[0] - (v + side * 0.02)).length
            d2 = (trobe.find_nearest(v - side * 0.02)[0] - (v - side * 0.02)).length
            inward = side if d1 < d2 else -side
        else:
            inward = side if side.dot(prev) > 0 else -side
        prev = inward
        loc, _, _, _ = trobe.find_nearest(v + inward * 0.0235)
        pts.append(loc)
        nrms.append(r_nrm(loc))
    # Broad smoothing spreads the stole's turn from the chest up round the collar over a hand's
    # width, so it bends there instead of folding; then it is laid back onto the robe.
    nrms = relax(nrms, 12)
    pts = [trobe.find_nearest(p_)[0] + n_.normalized() * 0.0042 for p_, n_ in zip(relax(pts, 8), nrms)]
    kd_st = KDTree(len(pts))
    for i, q in enumerate(pts):
        kd_st.insert(q, i)
    kd_st.balance()

    def st_nrm(p_):
        return nrms[kd_st.find(p_)[1]].normalized()
    path = pts
    stole = remat(pmc.sweep("stole", path, 0.05, 0.0035, "accent", st_nrm, bevel=0.0), "twill.accent")
    kit.hs.apply_modifiers(stole)
    strip_uvs(stole, 0.05, 0.0035)
    kit.transfer(robe.low, stole)
    c.parts.append((stole, "DONE", None))
    st_hi = bpy.data.objects.new("stole.high", stole.data.copy())
    bpy.context.scene.collection.objects.link(st_hi)
    sth = aco.bvh(st_hi)
    stole["texel"] = 1.5
    st_his = [st_hi]
    z_e = Z(1.135)
    for sx in (1, -1):
        side_ = [q for q in path if q.x * sx > 0 and q.y < 0]
        if not side_:
            continue
        q = min(side_, key=lambda q: abs(q.z - z_e))
        st_his.append(aco.project(st_hi, aco.code_rows(["∴"] + aco.scripture(91 + sx, 12, 1), 0.013, lead=1.45), (q.x, -0.5, z_e),
                                  (0, 1, 0), lift=0.0003, material="zealot_thread", name="embroidery", tree=sth))
    c.detail(stole, st_his, ext=0.004, ray=0.01)
    # Red cuffs where the robe's sleeves end above the elbows.
    for s in ("L", "R"):
        ua0, ua1 = J("upper_arm." + s, 0.0), J("upper_arm." + s, 1.0)
        tsl = aco.Tube([aco.region_tree(robe.low, {"upper_arm." + s})], ua0, ua1, t=(0.55, 0.8), nt=8, nphi=36, reach=0.15)
        cf = aco.strap_ring("robe_cuff", tsl.ring(0.69, 0.002, n=22), ua0.lerp(ua1, 0.69), ua1 - ua0, 0.03, 0.004, "accent")
        c.rigid(remat(cf, "twill.accent"), "upper_arm." + s)

    # ---------------------------------------------------------------- the robe's skirt
    crotch = b.at("crotch")
    z_top = belt_z + 0.018
    z_bot = J("lower_leg.L", 0.0).z - 0.17
    knee_z = J("lower_leg.L", 0.0).z

    def gap(h):
        return 23.0 + 17.0 * _sm(h, 0.12, 1.0)

    def band_f(h, f):
        return f < 0.1

    def hem_f(h, f):
        return h > 0.94
    skirt_g = skirt(c, man, "robe_skirt", "leather.primary", z_top, z_bot,
                    [tt, aco.region_tree(robe.low, TORSO), aco.region_tree(shirt.low, TORSO | THIGHS)] + [pmc.tree(o) for o in leg_cols],
                    gap, crotch - 0.02, knee_z, cy=0.006, ease=(0.004, 0.022), flare=0.07, nu=30, nv=15, fine=2,
                    trims=[("twill.accent", lambda h, f: band_f(h, f) or hem_f(h, f))],
                    collide=[trousers.low, robe.low] + leg_cols, bend=34.0, stiff=2.0, mass=0.4, frames=40, texel=1.0)
    drop(leg_cols)
    tsk = pmc.tree(skirt_g.low)

    # ---------------------------------------------------------------- sash and belt
    cen = (0.0, 0.004)
    sash = pmc.sweep("sash", outer_ring([tsk, trobe, tt] + [pmc.tree(o) for o, _, _ in plates[2:5]], cen, belt_z, 40, 0.004), 0.07, 0.008, "accent", pmc.radial((0, 0.004, 0)), closed=True)
    remat(sash, "twill.accent")
    c.add(sash, ["hips", "spine", "upper_leg.L", "upper_leg.R"])
    tsa = pmc.tree(sash)
    belt = pmc.sweep("belt", outer_ring([tsa], cen, belt_z - 0.004, 40, 0.0035), 0.032, 0.007, "black", pmc.radial((0, 0.004, 0)), closed=True)
    c.add(belt, ["hips", "spine", "upper_leg.L", "upper_leg.R"])
    loc, nor = pmc.hit(pmc.tree(belt), (0, -0.6, belt_z - 0.004), (0, 1, 0))
    if loc is not None:
        M = pmc.frame(loc + Vector((0, -0.005, 0)), (0, -1, 0), (0, 0, 1))
        pq = kit.block("belt_plaque", (0, -0.004, 0), (0.07, 0.008, 0.056), BONE, bevel=0.003, taper=(0.86, 1.0))
        kit.hs.apply_modifiers(pq)
        pq.data.transform(M)
        torso_arm.add(pq, "hips")
        torso_arm.etch(pq, aco.sigil(0.019, n=22, w=0.0026) + aco.code_rows(["∴"], 0.02), M @ Vector((0, -0.1, 0)), (0, 1, 0))
        for x in (-0.026, 0.026):
            for z in (-0.02, 0.02):
                torso_arm.detail(aco.screw(M @ Vector((x * (0.93 if z > 0 else 1.0), -0.0085, z)), (0, -1, 0), r=0.0026))
    # Chains of the cult's beads hanging from the belt at the left hip: a data rosary.
    for s, sx in (("L", 1),):
        top = None
        lb, _ = pmc.hit(pmc.tree(belt), (sx * 0.5, -0.03, belt_z - 0.004), (-sx, 0, 0))
        if lb is not None:
            top = lb + Vector((sx * 0.004, -0.004, -0.012))
            pts = [top + Vector((sx * 0.008 * math.sin(i * 0.5), -0.004 * i, -0.022 * i)) for i in range(7)]
            for i, q in enumerate(pts):
                if i % 2 == 0:
                    c.rigid(kit.cyl("bead", q - Vector((0, 0, 0.006)), q + Vector((0, 0, 0.006)), 0.0055, BONE if i % 4 == 0 else "gunmetal",
                                    segs=8, bevel=0.0012, bsegs=1), "hips")
            c.rigid(kit.rope("bead_cord", pts, 0.0012, "black"), "hips")
            tag = kit.block("bead_tag", pts[-1] + Vector((0, 0, -0.03)), (0.024, 0.004, 0.036), BONE, bevel=0.0015)
            c.rigid(tag, "hips")

    # ---------------------------------------------------------------- pauldrons over the robe
    for s, sx in (("L", 1), ("R", -1)):
        ua = "upper_arm." + s
        ua0, ua1 = J(ua, 0.0), J(ua, 1.0)
        big = s == "L"
        sleeve = aco.region_tree(robe.low, {ua, "shoulder." + s})
        tu = aco.Tube([sleeve], ua0, ua1, front=(0, -1, 0), t=(0.1, 0.75), nt=22, nphi=48, reach=0.15, spread=0.03, blur=0.02)
        lames = [tu.patch("pauldron_lame", BONE, 0.2, 0.42, 90 * sx, 70, 0.0075, 0.0055, nu=10, nv=3, corner=2.5, bevel=0.002)]
        if big:
            lames.append(tu.patch("pauldron_lame", BONE, 0.36, 0.55, 90 * sx, 66, 0.0065, 0.005, nu=10, nv=3, corner=2.5, bevel=0.002))
        for lm in lames:
            limb_arm.add(lm, ua)
        O = ua0 + Vector((-sx * 0.012, 0.0, -0.012))
        cap_env = aco.Env([sleeve] + lames, O, Z=(sx * 0.6, 0.0, 0.8), F=(0, -sx, 0), reach=0.17, lat=(-40.0, 90.0), dlat=4.0, dlon=6.0,
                          spread=9.0, blur=7.0, floor=0.003)
        grow = 0.012 if big else 0.0095

        def cap_rim(lo, big=big):
            sn = math.sin(math.radians(lo))
            return (34.0 if big else 38.0) - 63.0 * max(0.0, sn) ** 1.3 + 7.0 * max(0.0, -sn)
        cap = cap_env.patch("pauldron", BONE, -180.0, 180.0, cap_rim, lambda lo: 84.0, grow, 0.0065, nu=30, nv=6, closed=True, pole=True,
                            inner="regime_pad", bevel=0.0024)
        limb_arm.add(cap, ua)
        if big:
            # A raised ridge along the officer's pauldron and a gunmetal boss with the mark.
            ridge = cap_env.patch("pauldron_ridge", BONE, -150.0, -30.0, lambda lo: cap_rim(lo) + 9.0, lambda lo: cap_rim(lo) + 13.0, grow + 0.0045,
                                  0.005, nu=12, nv=1, bevel=0.0014)
            limb_arm.add(ridge, ua)
            q = cap_env.P(56, 90, grow)
            nq = cap_env.normal(56, 90, grow)
            c.rigid(kit.cyl("pauldron_boss", q - nq * 0.002, q + nq * 0.006, 0.019, "gunmetal", segs=6, bevel=0.0015, bsegs=1), ua)
        n = cap_env.normal(40, 90)
        limb_arm.etch(cap, aco.code_rows(aco.scripture(45 + sx, 3, 7), 0.0095), cap_env.P(40, 90, grow) + n * 0.1, -n, up=(0, 0, 1))
        n = tu.d(90 * sx)
        limb_arm.etch(lames[0], aco.tick_rows(48 + sx, 2, 0.06, 0.0045), tu.P(0.33, 90 * sx, 0.0075) + n * 0.1, -n, up=(ua0 - ua1).normalized())
        for lo in (-40, -140):
            la = cap_rim(lo) + 7
            limb_arm.detail(aco.screw(cap_env.P(la, lo, grow), cap_env.normal(la, lo, grow), r=0.0035))
        tu2 = aco.Tube([sleeve], ua0, ua1, hard=lames, t=(0.3, 0.6), nt=7, nphi=36, reach=0.15)
        c.rigid(aco.strap_ring("arm_strap", tu2.ring(0.4, 0.0015, n=20), ua0.lerp(ua1, 0.4), ua1 - ua0, 0.022, 0.004, "accent"), ua)

    # ---------------------------------------------------------------- vambraces over the sleeves
    for s, sx in (("L", 1), ("R", -1)):
        fa = "forearm." + s
        fa0, fa1 = J(fa, 0.0), J(fa, 1.0)
        sl = aco.region_tree(shirt.low, {fa})
        tf = aco.Tube([sl], fa0, fa1, front=(0, -1, 0), t=(0.0, 1.0), nt=26, nphi=48, reach=0.12, spread=0.025, blur=0.016)
        vb = tf.patch("vambrace", BONE, 0.14, 0.82, 68 * sx, 80, 0.0085, 0.006, nu=12, nv=8, corner=3.0, bulge=0.003, bevel=0.0024)
        limb_arm.add(vb, fa)
        n = tf.d(68 * sx)
        limb_arm.etch(vb, aco.code_rows(aco.scripture(55 + sx, 2, 4), 0.0078) + [(x, y - 0.03, m) for x, y, m in aco.tick_rows(59 + sx, 4, 0.03, 0.005)],
                      tf.P(0.46, 68 * sx, 0.0085) + n * 0.1, -n, up=(fa0 - fa1).normalized())
        for tq in (0.2, 0.76):
            limb_arm.detail(aco.screw(tf.P(tq, 68 * sx, 0.0085), tf.d(68 * sx), r=0.0032))
        tf2 = aco.Tube([sl], fa0, fa1, hard=[vb], t=(0.2, 0.8), nt=13, nphi=36, reach=0.12)
        for tq in (0.3, 0.68):
            c.rigid(aco.strap_ring("vambrace_strap", tf2.ring(tq, 0.0015, n=20), fa0.lerp(fa1, tq), fa1 - fa0, 0.018, 0.004, NYLON), fa)

    # ---------------------------------------------------------------- the skull cables into the collar
    nb = J("neck", 0.0)
    for la, lo, q in ports[:2]:
        sx = 1 if lo > 0 else -1
        lo1 = 158.0 * sx
        pts = [q]
        for k, la_k in enumerate((la - 9, cl(lo) + 7, cl(lo) + 3.2, cl(lo) - 3.2, cl(lo) - 8, 2.0, -16.0, -30.0, -40.0)):
            t = min(1.0, (k + 1) / 6.0)
            lo_k = lo + (lo1 - lo) * t
            off = 0.0128 if abs(la_k - cl(lo_k)) < 3.6 else 0.0062
            pts.append(skull.P(la_k, lo_k, off))
        # Into the robe's collar at the back of the neck.
        x = 0.032 * sx
        hit_, _ = pmc.hit(trobe, (x, 0.5, nb.z + 0.035), (0, -1, 0))
        end = (hit_ if hit_ is not None else Vector((x, 0.07, nb.z + 0.035))) + Vector((0, -0.012, -0.012))
        pts.append(end)
        c.add(kit.rope("skull_cable", pmc.smooth_path(pts, 2), 0.0042, "rubber", segs=6), ["head", "neck", "chest"])

    for a in (head_arm, torso_arm, limb_arm):
        a.finish()
    pmc.economise(c)
    return c


SPEC = {"build": build, "faction": "regime", "budget": (25000, 120000), "loadout": "revolver",
        "colors": {"primary": "#1c1a1e", "secondary": "#3a3036", "accent": "#8a1414"}}
