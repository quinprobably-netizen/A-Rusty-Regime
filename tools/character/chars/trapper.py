"""Trapper, Scrappers: the settlement's hunter, who works the flooded scrapyards and the river with a
harpoon gun and comes back with whatever was in the net. One system, built for the wet and the line:
a long oilskin duster, the coat closed to the belt and open below it with a riding vent at the back,
hanging to the boot tops; a storm collar stood up round a black-leather respirator with twin brass
filter canisters; brass goggles under a wide-brimmed oilskin hat with a tan band, its edge bound in
leather. A broad belt with a brass buckle over the coat's waist seam; a bandolier from the left
shoulder to the right hip carrying spare barbed harpoon heads in leather loops, under a riveted
hammered-steel pauldron on the left shoulder (the line side); three coils of hemp rope over the right
shoulder. Riveted steel bracers on both forearms, the left one with a brass line guide at the wrist.
On the belt: a brass spyglass in a leather holster at the left hip, a brass line reel with a crank at
the back of the right hip, a rolled tarred net across the small of the back with a loose flap of it
hanging over the coat. Duck trousers tucked into tall laced boots with two buckled straps each. Nothing
electric: steel, brass, leather, hemp, oiled cloth.

Built on the realistic layer (real.py) like the Mechanic and the Bruiser, whose surfaces, palette and
helpers it shares (bruiser.py: the hood, goggles and respirator, joins, straps). The coat's body and
sleeves are cut from the body and draped by the cloth simulation; its tail is a pattern piece of its
own (`coat_tail`), a cone hung round the legs, weighted to the hips and thighs and draped over the
trousers and boots. Its own surfaces: oilskin (`_oilskin`) and tarred netting (`_netting`).

Tints: primary = the oilskin (coat, hat), secondary = the trousers, accent = the tan leather (belt,
bandolier, straps, hat band). Steel, brass, hemp, net, boots, hood and respirator are fixed colours.
"""

import math
import os

import bpy
import bmesh
from mathutils import Vector

import kit
import real
import surfaces
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS
from chars import mechanic as mech  # the Scrappers' surfaces and palette, rivets, beads, buckles
from chars import contractor as pmc  # ray casts, sweeps
from chars import acolyte as aco  # Env / Tube envelopes, the armour bake, hang weights
from chars import bruiser as bru  # hood, goggles, respirator, joins, straps

FAST = bool(os.environ.get("SCRAP_FAST"))  # look-dev: skip the cloth simulation
PLATE = mech.PLATE
ARMS = UPPER_ARMS | FOREARMS
LEGS = THIGHS | SHINS
sm, join, basis, place, leather = bru.sm, bru.join, bru.basis, bru.place, bru.leather


# ------------------------------------------------------------------------------------- surfaces

def _oilskin(g, pal):
    """Oilskin: close cotton drill soaked in oil and wax, the weave nearly filled: a greasy sheen that
    runs along every fold, darker where the dressing has gathered in the creases, worn dull and pale on
    the ridges and edges that rub. Soft and even: no blotches."""
    base = pal[0]
    uv = g.uv()
    slub, fib, tex = mech._cloth_grain(g, uv)
    pos = g.geo("Position")
    cr = g.noise(pos, 22.0, detail=5, rough=0.65, distort=0.5)
    lines = g.remap(g.math("ABSOLUTE", g.sub(cr, 0.5)), 0.008, 0.0)
    ridge = g.edge(0.005, lo=0.9985, hi=0.985)
    tide = g.remap(g.noise(pos, 3.0, detail=2), 0.4, 0.6)
    shade = g.remap(g.add(g.mul(slub, 0.5), g.mul(fib, 0.5)), 0.3, 0.7, 0.95, 1.03, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    col = g.mix(g.mul(tide, 0.12), col, surfaces._scale(base, 0.88))
    col = g.mix(g.mul(lines, 0.45), col, surfaces._scale(base, 0.72))
    col = g.mix(g.mul(ridge, 0.5), col, surfaces._scale(base, 1.3))
    h = g.sub(g.add(g.mul(tex, 0.25), g.mul(fib, 0.2)), g.mul(lines, 0.4))
    rough = g.lerp(ridge, g.lerp(tide, 0.36, 0.44), 0.76)
    return dict(color=col, rough=rough, metal=0.0, height=h, bump=0.0004)


def _netting(g, pal):
    """Tarred hemp netting, rolled: diamond meshes of cord about four centimetres across, the cord
    lighter where it is worn, the layers under it dark through the holes."""
    base, worn = pal[0], pal[1]
    uv = g.uv()
    u, v, _ = g.xyz(uv)
    a = g.math("FRACT", g.math("DIVIDE", g.add(u, v), 0.042))
    b = g.math("FRACT", g.math("DIVIDE", g.sub(u, v), 0.042))
    da = g.math("ABSOLUTE", g.sub(a, 0.5))
    db = g.math("ABSOLUTE", g.sub(b, 0.5))
    cord = g.remap(g.math("MAXIMUM", da, db), 0.40, 0.46)
    knot = g.remap(g.math("MINIMUM", da, db), 0.40, 0.47)
    rub = g.remap(g.noise(g.geo("Position"), 9.0, detail=3), 0.45, 0.7)
    col = g.mix(cord, surfaces._scale(base, 0.3), g.mix(g.mul(rub, 0.6), base, worn))
    h = g.add(g.mul(cord, 0.7), g.mul(knot, 0.3))
    return dict(color=col, rough=0.88, metal=0.0, height=h, bump=0.0012)


kit.hs.PALETTE.setdefault("trap_net", ((0.06, 0.05, 0.035), (0.33, 0.27, 0.17), 0.0, 0.88, 0.3, 0))   # tarred hemp net
kit.hs.PALETTE.setdefault("trap_hemp", ((0.40, 0.32, 0.20), (0.56, 0.47, 0.33), 0.0, 0.9, 0.35, 0))  # hemp rope
for _k, _s in (("trap_net", "netting"), ("trap_hemp", "canvas")):
    surfaces.RECIPE.setdefault(_k, _s)
surfaces.RECIPES.setdefault("oilskin", _oilskin)
surfaces.RECIPES.setdefault("netting", _netting)
surfaces.SOFT.update({"oilskin"})


# ------------------------------------------------------------------------------------ helpers

def weigh(obj, fn):
    """Vertex groups from fn(point) -> {bone: weight}."""
    obj.vertex_groups.clear()
    groups = {}
    for v in obj.data.vertices:
        for bn, wt in fn(v.co).items():
            if wt <= 1e-4:
                continue
            if bn not in groups:
                groups[bn] = obj.vertex_groups.new(name=bn)
            groups[bn].add([v.index], wt, "REPLACE")


def _ray_hull(hull, o, d):
    """Distance from o along d (2D) to the convex polygon `hull` it lies in."""
    best = None
    n = len(hull)
    for k in range(n):
        ax, ay = hull[k]
        bx, by = hull[(k + 1) % n]
        ex, ey = bx - ax, by - ay
        det = -d[0] * ey + d[1] * ex
        if abs(det) < 1e-12:
            continue
        rx, ry = ax - o[0], ay - o[1]
        t = (-rx * ey + ry * ex) / det
        s = (d[0] * ry - d[1] * rx) / det
        if -1e-6 <= s <= 1 + 1e-6 and t > 0:
            best = t if best is None else max(best, t)
    return best


def near_tree(obj, at, radius):
    """A ray-cast tree of the faces of `obj` within `radius` of `at` (a strap where a plate sits on it)."""
    from mathutils.bvhtree import BVHTree
    me = obj.data
    co = [obj.matrix_world @ v.co for v in me.vertices]
    at = Vector(at)
    return BVHTree.FromPolygons(co, [p.vertices[:] for p in me.polygons if (co[p.vertices[0]] - at).length < radius])


def glue_body(c, obj, coat, z_arm=1.3):
    """Skin a part lying on the coat with the coat's own weights (nearest face) less its forearms and
    hands, and its upper arms below `z_arm`: a rope coil or a bandolier hangs past the sleeves in the
    rest pose and must not follow them (over the shoulder it goes with the shoulder, as the coat does)."""
    mech.glue(c, obj, coat)
    vg = obj.vertex_groups
    drop = {g.index for g in vg if g.name.startswith(("forearm.", "hand.", "f_", "thumb"))}
    upper = {g.index for g in vg if g.name.startswith("upper_arm.")}
    hips = vg.get("hips") or vg.new(name="hips")
    for v in obj.data.vertices:
        ws = [(g.group, g.weight) for g in v.groups]
        keep = [(i, w) for i, w in ws if i not in drop and not (i in upper and v.co.z < z_arm)]
        tot = sum(w for _, w in keep)
        for i, _ in ws:
            if i in drop or (i in upper and v.co.z < z_arm):
                vg[i].remove([v.index])
        if tot < 1e-4:
            hips.add([v.index], 1.0, "REPLACE")
        else:
            for i, w in keep:
                vg[i].add([v.index], w / tot, "REPLACE")
    return obj


def reglue(joined, pts, coat):
    """Re-skin the vertices of a joined armour part that sit at `pts` (its pieces' vertices when they
    were added) with the coat's own weights, as `glue_body` skins a strap: the Armour joins every piece
    rigid to one bone, and a pauldron rigid to the upper arm swings off the shoulder of the cloth (whose
    weights blend shoulder, chest and arm) as soon as the arm comes up."""
    from mathutils.kdtree import KDTree
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    mw = joined.matrix_world
    hit = [v.index for v in joined.data.vertices if kd.find(mw @ v.co)[2] < 1e-5]
    if not hit:
        return joined
    me = bpy.data.meshes.new("reglue")
    me.from_pydata([tuple(mw @ joined.data.vertices[i].co) for i in hit], [], [])
    tmp = bpy.data.objects.new("reglue", me)
    bpy.context.scene.collection.objects.link(tmp)
    kit.transfer(coat, tmp)
    names = {g.index: g.name for g in tmp.vertex_groups}
    vg = joined.vertex_groups
    for g in list(vg):
        g.remove(hit)
    for k, i in enumerate(hit):
        ws = [(names[g.group], g.weight) for g in tmp.data.vertices[k].groups
              if g.weight > 1e-4 and not names[g.group].startswith(("forearm.", "hand.", "f_", "thumb"))]
        tot = sum(w for _, w in ws) or 1.0
        for n, w in ws:
            (vg.get(n) or vg.new(name=n)).add([i], w / tot, "REPLACE")
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.meshes.remove(me)
    return joined


def press(objs, pts, nfn, width, thick, closed=True, under=0.0015, margin=0.012):
    """Press the cloth under a strap down beneath it, as a strap pulled tight flattens the folds it
    crosses: every vertex of `objs` within the strap's `width` (fading over `margin` beyond it) that
    stands above the strap's underside is moved down along the strap's normal to `under` below it."""
    from mathutils.kdtree import KDTree
    n = len(pts)
    kd = KDTree(n)
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    frames = []
    for i, p in enumerate(pts):
        a, b_ = (pts[i - 1], pts[(i + 1) % n]) if closed else (pts[max(0, i - 1)], pts[min(n - 1, i + 1)])
        T = (b_ - a).normalized()
        N = Vector(nfn(p))
        N = (N - T * N.dot(T)).normalized()
        frames.append((T, N, T.cross(N)))
    lim = -thick / 2 - under
    for o in objs:
        me = o.data
        for v in me.vertices:
            _, i, dist = kd.find(v.co)
            if dist > width + margin + 0.04:
                continue
            T, N, S = frames[i]
            d = v.co - pts[i]
            sd = abs(d.dot(S))
            h = d.dot(N)
            if abs(d.dot(T)) > 0.04 or sd > width / 2 + margin or not (lim < h < 0.03):
                continue
            w = 1.0 if sd <= width / 2 else 1.0 - (sd - width / 2) / margin
            v.co -= N * (h - lim) * w
        me.update()


def loop_round(trees, C, A, n=48, lift=0.004, reach=0.6, smooth=2):
    """A band round the body in the plane through C square to A (a bandolier, a rope coil): the
    outermost surface along rays from C in that plane, lifted off it, relaxed."""
    A = Vector(A).normalized()
    X = (Vector((0, 1, 0)) - A * A.y).normalized()
    Y = A.cross(X)
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        d = X * math.cos(a) + Y * math.sin(a)
        loc, _ = mech.outermost(trees, C, d, reach)
        if loc is not None:
            pts.append(loc + d * lift)
    for _ in range(smooth):
        m = len(pts)
        pts = [(pts[i - 1] + pts[i] * 2 + pts[(i + 1) % m]) / 4 for i in range(m)]
    return pts


# ---------------------------------------------------------------------------------- the build

def build():
    b = real.Anatomy(height=1.81, width=0.97, body="male", sole=0.036)
    c = real.begin("trapper", b)
    man = real.body(c, stubble=0.0, face_detail=1.0)
    J, seg = b.j, kit.seg_dist
    lead = real.bones_at(man)
    hc = man.head_center()
    armpit, crotch = b.at("armpit"), b.at("crotch")
    eyes = [Vector(e.matrix_world.translation) for e in man.eyes]
    E, u = man.face()

    def on_arm(p):
        return lead(p) in ARMS

    # ---------------------------------------------------------------- hands and feet
    gl = real.gloves(c, man, "glove.scrap_suede", cuff=0.065, ease=0.0026)
    boot_top = 0.31
    boots = real.boots(c, man, "leather.scrap_boot", sole_kind="rubber", trim="leather", top=boot_top, lace="scrap_lace", tab="leather")
    bru.steel_caps(c, b, boots["upper"], "leather")

    # ---------------------------------------------------------------- duck trousers, tucked into the boots
    top_z = b.hip_z + 0.10
    hem = b.sole + boot_top - 0.04

    def t_ease(p):
        band = 0.003 * (1 - sm(top_z - p.z, 0.02, 0.07))
        return 0.011 + band + 0.006 * sm(top_z - p.z, 0.04, 0.2) + 0.005 * sm(J("lower_leg.L", 0.0).z - p.z, 0.0, 0.15)

    def t_pin(p):
        return 1.0 if p.z > top_z - 0.045 or p.z < hem + 0.018 else 0.0

    def t_slack(p):
        return sm(hem + 0.12 - p.z, 0.0, 0.1)
    trousers = real.garment(c, man, "trousers", "duck.secondary",
                            lambda p: lead(p) in LEGS | {"hips", "spine"} and hem - 0.03 < p.z < top_z + 0.03,
                            [((0, 0, top_z), (0, 0, 1)), ((0, 0, hem), (0, 0, -1), lambda p: lead(p) in LEGS)],
                            ease=t_ease, pin=None if FAST else t_pin, slack=t_slack, bend=18.0, texel=1.0)
    c.hide_under(trousers.low, 0.06, 2)

    # ---------------------------------------------------------------- the oilskin coat: body and sleeves
    neck = J("neck", 0.0)
    coat_hem = b.hip_z + 0.03
    neckline = (Vector((0, 0, neck.z + 0.03)), Vector((0, -0.3, 1)).normalized())
    cuts = [neckline]
    for s in ("L", "R"):
        e, w = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        cuts.append((e.lerp(w, 0.9), w - e, lambda p, e=e, w=w: on_arm(p) and seg(p, e, w + (w - e) * 0.6) < 0.1))
    cuts.append(((0, 0, coat_hem), (0, 0, -1), lambda p: not on_arm(p)))

    def c_ease(p):
        if not on_arm(p) and p.z < armpit - 0.06:
            return 0.015 + 0.004 * sm(armpit - 0.06 - p.z, 0.0, 0.25)
        dd, s = min((seg(p, J("upper_arm." + s, 0.3), J("forearm." + s, 1.0)), s) for s in ("L", "R"))
        e = 0.015 + 0.012 * max(0.0, min(1.0, (0.1 - dd) / 0.03))
        f0, f1 = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        if seg(p, f0, f1) < 0.1:  # the sleeve opens out toward the cuff, over the glove's gauntlet
            e += 0.006 * sm((p - f0).dot(f1 - f0) / (f1 - f0).length_squared, 0.55, 0.9)
        return e

    def c_pin(p):
        if not on_arm(p) and (p.z > neck.z - 0.015 or p.z < coat_hem + 0.03):
            return 1.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.9)
            d = (wr - e).normalized()
            if on_arm(p) and seg(p, e, wr) < 0.11 and (p - wr).dot(d) > -0.025:
                return 1.0
        return 0.0

    def c_slack(p):
        w = 0.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.9)
            d = wr - e
            L = d.length
            d.normalize()
            t = (p - e).dot(d) / L
            if on_arm(p) and seg(p, e, wr) < 0.11 and t > 0.2:
                w = max(w, min(1.0, (t - 0.2) / 0.5))
        return w
    coat = real.garment(c, man, "coat", "oilskin.primary", lambda p: lead(p) in TORSO | ARMS | THIGHS | {"neck"} and p.z > coat_hem - 0.05,
                        cuts, ease=c_ease, pin=None if FAST else c_pin, slack=c_slack, bend=24.0, stiff=1.5, texel=1.15,
                        collide=[trousers.low])
    c.hide_under(coat.low, 0.05, 2)

    # ---------------------------------------------------------------- its tail, the collar
    z_tail = b.hip_z + 0.095
    tail, tail_hi = coat_tail(c, man, b, coat.low, [trousers.low, boots["upper"]], "oilskin.primary", z_tail, b.sole + 0.335, crotch - 0.02)
    cloth = [coat.low, coat.high, tail, tail_hi]  # what the straps press down
    collar = storm_collar(c, coat.low, neck, J("neck", 1.0) - neck)
    pockets(c, b, tail)

    # ---------------------------------------------------------------- head
    arm = aco.Armour(c, "armour", texel=2.0)
    for e in man.eyes:
        c.parts = [p for p in c.parts if p[0] is not e]
        bpy.data.objects.remove(e, do_unlink=True)
    c.cover({"head"})
    surfaces._TEXEL_FN[man.low.name] = lambda obj: (lambda isl: 0.3)  # no skin shows
    hood, th = bru.hood_layer(c, man, lead, neckline, hc, smooth=9)
    gear = bru.goggles(c, th, eyes, E, u, hc)
    resp, can = bru.respirator(c, man, lead, E, u, hc, twin=True)
    gear.append(can)
    hat = wide_hat(c, hc, [th, pmc.tree(resp)] + [pmc.tree(g) for g in gear])
    bru.trim_under(hood, [hat, resp] + gear, 0.04, erode=1, only=lambda p: p.z > hc.z + 0.03 or p.y < hc.y - 0.05)

    # ---------------------------------------------------------------- belt, harness, gear
    torso = aco.region_tree(coat.low, TORSO | UPPER_ARMS)
    tt, tc, tcol = pmc.tree(tail), pmc.tree(coat.low), pmc.tree(collar)
    belt = waist_belt(c, b, [tt, tc], b.hip_z + 0.072, cloth)
    sash = bandolier(c, b, coat.low, [torso, tt, tcol], cloth)
    glued = pauldron(c, b, arm, coat.low, [near_tree(sash, J("upper_arm.L", 0.0), 0.11)], "L", 1)
    rope_coil(c, b, coat.low, [torso, tt, tcol, pmc.tree(sash)], cloth)
    for s, sx in (("L", 1), ("R", -1)):
        bracer(c, b, arm, coat.low, gl, s, sx, guide=(s == "L"))
    spyglass(c, b, belt)
    line_reel(c, b, belt)
    net_roll(c, b, belt, tail)
    boot_straps(c, b, boots["upper"])
    if os.environ.get("TRIS"):
        print("ARMOUR " + ", ".join(f"{o.name} {kit.tris(o)}" for o, _ in sorted(arm.pieces, key=lambda q: -kit.tris(q[0]))), flush=True)
    reglue(arm.finish(), glued, coat.low)
    pmc.economise(c)
    return c


# ------------------------------------------------------------------------------------- the coat

def coat_tail(c, man, b, coat, under, kind, z_top, z_bot, z_vent, gap=(3.0, 21.0), nu=44, nv=12, fine=2, flare=0.075, texel=1.15):
    """The duster's tail: a cone of oilskin from the waist seam (under the belt) to the boot tops, open
    at the front (the edges meeting at the belt, parting further down) and split at the back from just
    under the seat (a riding vent). Its rest shape stands off the trousers and boots by more and more
    toward the hem, so the cloth simulation drops it into long folds round the legs. It hangs from the
    hips, more and more with the thigh on its side further down, the shins taking a share below the
    knees. Like real.garment, the cloth is simulated `fine` subdivisions finer than the game mesh,
    whose vertices take the simulated positions, and baked into its normal map. Returns the game mesh."""
    yc = b.j("spine", 0.0).y
    dom = kit.dominant(coat)
    pts = [v.co.copy() for v in coat.data.vertices if dom[v.index] in TORSO | THIGHS]
    for o in under:
        pts += [v.co.copy() for v in o.data.vertices]
    # The hull of what it hangs round, per height and angle (a table, smoothed).
    NZ, NA = 26, 60
    zs = [z_top + (z_bot - z_top) * k / (NZ - 1) for k in range(NZ)]
    table = []
    for z in zs:
        band = [(p.x, p.y) for p in pts if abs(p.z - z) < 0.02]
        hull = real._hull2d(band) if len(band) > 3 else None
        row = []
        for k in range(NA):
            a = math.radians(360.0 * k / NA)
            r = _ray_hull(hull, (0.0, yc), (math.sin(a), -math.cos(a))) if hull else None
            row.append(r)
        table.append(row)
    for i, row in enumerate(table):
        for k in range(NA):
            if row[k] is None:
                row[k] = next((table[j][k] for j in sorted(range(NZ), key=lambda j: abs(j - i)) if table[j][k] is not None), 0.17)
    for _ in range(2):
        table = [[(row[k - 1] + row[k] * 2 + row[(k + 1) % NA]) / 4 for k in range(NA)] for row in table]
        table = [[(table[max(0, i - 1)][k] + table[i][k] * 2 + table[min(NZ - 1, i + 1)][k]) / 4 for k in range(NA)] for i in range(NZ)]

    def R(h, a):
        fi = min(max(h * (NZ - 1), 0.0), NZ - 1.0001)
        i0 = int(fi)
        fk = (a % 360.0) / 360.0 * NA
        k0 = int(fk) % NA
        k1 = (k0 + 1) % NA
        x, y = fi - i0, fk - int(fk)
        return ((table[i0][k0] * (1 - y) + table[i0][k1] * y) * (1 - x) + (table[i0 + 1][k0] * (1 - y) + table[i0 + 1][k1] * y) * x)

    def P(h, a):
        z = z_top + (z_bot - z_top) * h
        ra_ = math.radians(a)
        folds = 0.6 * math.sin(6 * ra_ + 0.7) + 0.4 * math.sin(11 * ra_ + 2.1)  # long folds, more cloth than room
        r = R(h, a) + 0.006 + 0.022 * h + flare * h ** 1.6 + 0.02 * h ** 1.2 * folds
        ra = math.radians(a)
        return Vector((math.sin(ra) * r, yc - math.cos(ra) * r, z))

    iv = max(1, round(nv * (z_top - z_vent) / (z_top - z_bot)))

    def grid(nu_, nv_, iv_):
        bm = bmesh.new()
        mid = nu_ // 2
        V = {}

        def key(i, j, half):
            return (i, j, half) if (j == mid and i >= iv_) else (i, j, 0)
        for i in range(nv_ + 1):
            h = i / nv_
            g = gap[0] + (gap[1] - gap[0]) * h ** 0.7
            for j in range(nu_ + 1):
                a = g + (360.0 - 2 * g) * j / nu_
                for k in {key(i, j, 0), key(i, j, 1)}:
                    V[k] = bm.verts.new(P(h, a))
        for i in range(nv_):
            for j in range(nu_):
                hf = 0 if j < mid else 1
                bm.faces.new((V[key(i, j, hf)], V[key(i + 1, j, hf)], V[key(i + 1, j + 1, hf)], V[key(i, j + 1, hf)]))
        bm.verts.index_update()
        return bm, {k: v.index for k, v in V.items()}

    bm_lo, idx_lo = grid(nu, nv, iv)
    bm_hi, idx_hi = grid(nu * fine, nv * fine, iv * fine)
    low = real._bm_obj("coat_tail", bm_lo)
    high = real._bm_obj("coat_tail.high", bm_hi)
    m = real.mat(kind)
    for o in (low, high):
        o.data.materials.append(m)
    knee = b.j("lower_leg.L", 0.0).z
    fn = aco.hang_weights(z_top, z_bot, side=0.08, legs=0.85, lower=(knee - 0.02, 0.5))
    weigh(low, fn)
    weigh(high, fn)
    if not FAST:
        real.drape(c, man, high, lambda p: 1.0 if p.z > z_top - 0.028 else 0.0, None, frames=60, gravity=1.0, stiff=1.6, bend=9.0,
                   collide=[coat] + list(under), mass=0.45)
    co = [v.co.copy() for v in high.data.vertices]
    for (i, j, hf), li in idx_lo.items():
        low.data.vertices[li].co = co[idx_hi[(i * fine, j * fine, hf)]]
    low.data.update()
    real.seam_attrs(high)
    real.seam_attrs(low)
    low["texel"] = texel
    c.parts.append((low, "DONE", None))
    c.detail(low, [high], ext=0.012, ray=0.03)
    return low, high


def pockets(c, b, tail, kind="oilskin.primary"):
    """Two big patch pockets on the skirt at the hips, each under a flap closed with a brass stud."""
    yc = b.j("spine", 0.0).y
    hip = b.hip_z
    tt = pmc.tree(tail)
    for sx in (1, -1):
        def ang(p, sx=sx):
            return math.degrees(math.atan2(p.x * sx, -(p.y - yc)))

        def pocket(p, ang=ang):
            return 36.0 < ang(p) < 74.0 and hip - 0.2 < p.z < hip - 0.025

        def flap(p, ang=ang):
            return 34.0 < ang(p) < 76.0 and hip - 0.055 < p.z < hip + 0.004
        real.patch(c, tail, "pocket", kind, pocket, lift=0.0022, puff=0.003, thick=0.002, subdivide=1)
        f = real.patch(c, tail, "pocket_flap", kind, flap, lift=0.0055, puff=0.002, thick=0.0025, subdivide=1)
        ps = [v.co for v in f.data.vertices]
        q = sum(ps, Vector()) / max(1, len(ps))
        d = Vector((q.x, q.y - yc, 0)).normalized()
        loc, nor = pmc.hit(tt, q + d * 0.2 - Vector((0, 0, 0.012)), -d)
        if loc is not None:
            nor = Vector(nor).normalized()
            mech.glue(c, kit.cyl("pocket_stud", loc + nor * 0.006, loc + nor * 0.0105, 0.0065, "brass", segs=10, bevel=0.0012), tail)


def storm_collar(c, coat, neck, axis, kind="oilskin.primary", H=0.068, gap=13.0, n=36):
    """A storm collar stood up round the neck from the coat's neckline, flaring a little, taller at the
    back, open at the throat (where the respirator sits) with a strap and buckle across."""
    loops = real.boundary_loops(coat)
    me = coat.data
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
    up = Vector(axis).normalized()
    rings = []
    for i in range(n + 1):
        th = gap + (360 - 2 * gap) * i / n
        p = at(th)
        d = Vector((math.sin(math.radians(th)), -math.cos(math.radians(th)), 0))
        back = (1 - math.cos(math.radians(th))) / 2
        h = H * (0.85 + 0.25 * back)
        fl = 0.008 + 0.004 * back
        rings.append([p - d * 0.003 - up * 0.004, p + up * h + d * (fl - 0.002), p + up * (h + 0.003) + d * (fl + 0.003),
                      p + d * 0.007 - up * 0.01])
    o = mech.loft("collar", rings, kind)
    o["texel"] = 1.2
    o["unwrap"] = True
    mech.glue(c, o, coat)
    # The throat strap.
    a, z = rings[0], rings[-1]
    q0, q1 = a[2].lerp(a[3], 0.5), z[2].lerp(z[3], 0.5)
    mid = (q0 + q1) / 2 + Vector((0, -0.012, 0))
    strap = leather(pmc.sweep("collar_strap", pmc.smooth_path([q0 + (q0 - mid) * 0.15, mid, q1 + (q1 - mid) * 0.15], 3), 0.016, 0.003, "accent",
                              lambda q: Vector((q.x, q.y - yc, 0)), bevel=0.0))
    mech.glue(c, strap, coat)
    mech.glue(c, mech.buckle("collar_buckle", mid + Vector((0, -0.003, 0)), (q1 - q0).normalized(), Vector((0, -1, 0)), 0.02), coat)
    return o


# ------------------------------------------------------------------------------------- the hat

def wide_hat(c, hc, trees, kind="oilskin.primary"):
    """A wide-brimmed oilskin hat over the hood: a crown with straight walls and a dented top, sat
    lower at the back than over the brow; a brim that dips at the front and back and turns up a little
    at the sides, its edge bound in leather; a tan band with a brass buckle. Laid on the envelope of
    the hood and the face gear. Returns the hat."""
    env = aco.Env(trees, hc + Vector((0, 0.004, -0.01)), reach=0.26, lat=(-30.0, 90.0), dlat=4.0, dlon=6.0, spread=10.0, blur=8.0, floor=0.004)
    N = 48
    los = [-180.0 + 360.0 * j / N for j in range(N)]

    def band(lo):
        return 15.0 + 10.0 * (1 + math.cos(math.radians(lo))) / 2
    base = [env.P(band(lo), lo, 0.007) for lo in los]
    C = sum(base, Vector()) / N
    top_z = max(env.P(la, lo, 0.0).z for la in range(40, 91, 10) for lo in range(-180, 180, 30)) + 0.03
    rings = []
    K = 5
    for k in range(K + 1):
        t = k / K
        ring = []
        for p in base:
            q = C + Vector(((p - C).x, (p - C).y, 0)) * (1 - 0.05 * t)
            ring.append(Vector((q.x, q.y, p.z + (top_z - 0.012 - p.z) * t)))
        rings.append(ring)
    # Over the top edge into a dented top.
    for sc, dz in ((0.9, -0.002), (0.74, -0.008), (0.4, -0.017)):
        rings.append([Vector((C.x + (p.x - C.x) * sc * 0.95, C.y + (p.y - C.y) * sc * 0.95, top_z + dz)) for p in base])
    # The brim, out from the band.
    brim = []
    for s in (0.25, 0.5, 0.75, 1.0):
        ring = []
        for p, lo in zip(base, los):
            r = Vector(((p - C).x, (p - C).y, 0)).normalized()
            cl, sn = math.cos(math.radians(lo)), math.sin(math.radians(lo))
            W = 0.08 + 0.01 * cl * cl
            dz = (-0.026 * cl * cl + 0.016 * sn * sn) * s ** 1.7
            ring.append(p + r * (0.003 + W * s) + Vector((0, 0, dz)))
        brim.append(ring)
    bm = bmesh.new()
    rows = [[bm.verts.new(p) for p in ring] for ring in brim[::-1] + rings]
    for r0, r1 in zip(rows, rows[1:]):
        for j in range(N):
            k = (j + 1) % N
            bm.faces.new((r0[j], r0[k], r1[k], r1[j]))
    ctr = bm.verts.new(Vector((C.x, C.y, top_z - 0.02)))
    for j in range(N):
        bm.faces.new((rows[-1][j], rows[-1][(j + 1) % N], ctr))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    f = next(f for f in bm.faces if rows[len(brim) + 2][0] in f.verts)
    if f.normal.dot(f.calc_center_median() - Vector((C.x, C.y, f.calc_center_median().z))) < 0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    hat = mech.mesh_obj("hat", bm, kind, texel=1.0)
    hat["unwrap"] = True
    m = hat.modifiers.new("thick", "SOLIDIFY")
    m.thickness, m.offset, m.use_rim, m.use_even_offset, m.use_quality_normals = 0.0045, -1.0, True, False, True
    kit.hs._apply(hat, m.name)
    c.rigid(hat, "head")
    # The bound edge and the band.
    edge = brim[-1]
    c.rigid(mech.remat(mech.tube_path("hat_binding", [p + Vector((0, 0, -0.002)) for p in edge], 0.003, "accent", segs=6), "leather.accent"), "head")
    bandp = [C + Vector(((p - C).x, (p - C).y, 0)) * 1.012 + Vector((0, 0, p.z - C.z + 0.014)) for p in base]
    c.rigid(leather(pmc.sweep("hat_band", bandp, 0.024, 0.003, "accent", lambda q: Vector((q.x - C.x, q.y - C.y, 0)), closed=True, bevel=0.0)), "head")
    j = N // 2 + N // 4  # lon +90: the left side
    q = bandp[j]
    nn = Vector((q.x - C.x, q.y - C.y, 0)).normalized()
    c.rigid(mech.buckle("hat_buckle", q + nn * 0.0025, (bandp[(j + 1) % N] - bandp[j - 1]).normalized(), nn, 0.026), "head")
    return hat


# ------------------------------------------------------------------------------------- belt and harness

def waist_belt(c, b, trees, z, cloth, n=40):
    """A broad tan belt over the coat's waist seam, a big brass buckle in front. Returns its points
    and out directions."""
    yc = b.j("spine", 0.0).y
    pts, dirs = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        d = Vector((math.sin(a), -math.cos(a), 0))
        loc, _ = mech.outermost(trees, (0, yc, z), d, 0.5)
        pts.append((loc if loc is not None else Vector((0, yc, z)) + d * 0.17) + d * 0.0045)
        dirs.append(d)
    for _ in range(2):
        pts = [(pts[i - 1] + pts[i] * 2 + pts[(i + 1) % n]) / 4 for i in range(n)]
    c.rigid(leather(pmc.sweep("belt", pts, 0.058, 0.0065, "accent", pmc.radial((0, yc, 0)), closed=True, bevel=0.0)), "hips")
    press(cloth, pts, pmc.radial((0, yc, 0)), 0.058, 0.0065)
    tan = (pts[1] - pts[-1]).normalized()
    c.rigid(mech.buckle("belt_buckle", pts[0] + dirs[0] * 0.0045, tan, dirs[0], 0.066), "hips")
    spots = [(pts[i] + dirs[i] * 0.0035 + Vector((0, 0, dz)), dirs[i]) for i in range(3, n - 2, 4) for dz in (0.019, -0.019)]
    c.rigid(mech.rivets("belt_rivets", spots, r=0.0028, material="brass", segs=6), "hips")
    return {"z": z, "pts": pts, "dirs": dirs, "yc": yc}


def bandolier(c, b, coat, trees, cloth):
    """A tan bandolier from the left shoulder to the right hip, four spare barbed harpoon heads in
    leather loops on the chest. Returns the strap."""
    armpit = b.at("armpit")
    C = Vector((0.0, b.j("spine", 0.0).y, armpit - 0.05))
    A = Vector((0, 1, 0)).cross(Vector((-0.34, 0, -1)))   # the band runs from the left shoulder down to the right hip
    pts = loop_round(trees, C, A, n=60, lift=0.0075)
    press(cloth, pts, pmc.radial(C, A), 0.052, 0.0055)
    strap = leather(pmc.sweep("bandolier", pts, 0.052, 0.0055, "accent", pmc.radial(C, A), closed=True, bevel=0.0))
    glue_body(c, strap, coat, armpit - 0.04)
    # Harpoon heads on the front, points up toward the shoulder.
    front = [i for i, p in enumerate(pts) if p.y < C.y - 0.05 and armpit - 0.17 < p.z < armpit + 0.06]
    front.sort(key=lambda i: -pts[i].z)
    picks = front[1::max(1, len(front) // 4)][:4]
    heads, loops = [], []
    nrm = pmc.radial(C, A)
    for i in picks:
        p = pts[i]
        T = (pts[(i + 1) % len(pts)] - pts[i - 1]).normalized()
        if T.z < 0:
            T = -T
        n = Vector(nrm(p)).normalized()
        n = (n - T * n.dot(T)).normalized()
        S = T.cross(n)
        base = p + n * 0.012
        heads += [kit.cyl("head_socket", base - T * 0.035, base + T * 0.004, 0.0075, PLATE, segs=8, bevel=0.0008),
                  kit.cyl("head_point", base + T * 0.004, base + T * 0.058, 0.0105, "steel", r1=0.0006, segs=4, bevel=0.0)]
        for sd in (1, -1):
            bp = base + T * 0.012 + S * sd * 0.008
            tip = base - T * 0.012 + S * sd * 0.02
            heads.append(kit.cyl("head_barb", bp, tip, 0.0032, "steel", r1=0.0007, segs=4, bevel=0.0))
        loops.append(kit.ring("head_loop", base - T * 0.018, T, 0.0118, 0.0078, 0.012, "accent", segs=10))
    if heads:
        glue_body(c, join(heads, "harpoon_heads"), coat, armpit - 0.04)
        glue_body(c, leather(join(loops, "head_loops")), coat, armpit - 0.04)
    return strap


def rope_coil(c, b, coat, trees, cloth):
    """Four coils of hemp rope over the right shoulder, hanging to the left hip, bound together with
    two leather ties."""
    armpit = b.at("armpit")
    yc = b.j("spine", 0.0).y
    coils = []
    for k, (lift, tilt, dz) in enumerate(((0.0085, 0.0, 0.0), (0.017, 0.05, -0.012), (0.026, -0.04, -0.022), (0.018, -0.09, 0.01))):
        C = Vector((0.0, yc, armpit - 0.06 + dz))
        A = Vector((0, 1, 0)).cross(Vector((0.36 + tilt, 0, -1)))
        pts = loop_round(trees, C, A, n=46, lift=lift, smooth=3)
        coils.append(mech.tube_path("rope", pts, 0.0076, "trap_hemp", segs=6, closed=True, strands=3, pitch=0.017))
        if k == 0:
            first = (pts, C, A)
            press(cloth, pts, pmc.radial(C, A), 0.012, 0.0152)
    glue_body(c, join(coils, "rope_coil"), coat, armpit - 0.04)
    # Ties round the bundle, low on the left hip at front and back.
    pts, C, A = first
    ties = []
    for want in (Vector((0.14, -0.2, 0)), Vector((0.14, 0.2, 0))):
        i = min(range(len(pts)), key=lambda i: (Vector((pts[i].x, pts[i].y - yc, 0)) - want).length + abs(pts[i].z - (b.hip_z + 0.2)) * 2)
        T = (pts[(i + 1) % len(pts)] - pts[i - 1]).normalized()
        n = Vector(pmc.radial(C, A)(pts[i])).normalized()
        ties.append(kit.ring("rope_tie", pts[i] + n * 0.008, T, 0.024, 0.019, 0.016, "accent", segs=10))
    glue_body(c, leather(join(ties, "rope_ties")), coat, armpit - 0.04)


def pauldron(c, b, arm, coat, hard, s="L", sx=1):
    """A riveted hammered-steel pauldron on the line shoulder over the bandolier: a domed cap and one
    lame, rims rolled, a tan strap round the arm under it, the Scrappers' cog painted on the cap."""
    ua = "upper_arm." + s
    ua0, ua1 = b.j(ua, 0.0), b.j(ua, 1.0)
    OUT = 90 * sx
    # The sleeve's top and the outer half of the shoulder (the rest of the shoulder region runs up the
    # trapezius to the collar, and a cap laid over that grows a fin toward the neck).
    from mathutils.bvhtree import BVHTree
    dom = kit.dominant(coat)
    me = coat.data
    co = [v.co.copy() for v in me.vertices]
    sleeve = BVHTree.FromPolygons(co, [p.vertices[:] for p in me.polygons if sum(dom[i] in (ua, "shoulder." + s) for i in p.vertices) * 2 >= len(p.vertices)
                                       and p.center.x * sx > ua0.x * sx - 0.035])
    lame_tu = aco.Tube([sleeve], ua0, ua1, front=(0, -1, 0), t=(0.05, 0.6), nt=16, nphi=48, reach=0.16, spread=0.03, blur=0.02)
    lame = lame_tu.patch("pauldron_lame", PLATE, 0.17, 0.32, OUT, 68, 0.009, 0.003, nu=14, nv=3, corner=2.5, bevel=0.0012)
    arm.add(lame, ua)
    glued = [lame.matrix_world @ v.co for v in lame.data.vertices]
    glue_body(c, mech.bead("lame_rim", [lame_tu.P(0.32, OUT + 68 * 0.62 * (2 * k / 12 - 1), 0.0077) for k in range(13)], 0.0026, closed=False,
                           normal=lambda q: lame_tu.d(OUT)), coat, 0.0)
    O = ua0 + Vector((-sx * 0.012, 0.0, -0.01))
    env = aco.Env([sleeve, lame] + list(hard), O, Z=(sx * 0.6, 0.0, 0.8), F=(0, -sx, 0), reach=0.16, lat=(-40.0, 90.0),
                  dlat=4.0, dlon=6.0, spread=9.0, blur=7.0, floor=0.003)

    def rim(lo):
        # The Mechanic's cap: round over the outside of the shoulder, down the deltoid, short on the neck
        # side (a cap reaching far down the front and back stands out like a fin once the arm comes up).
        sn = math.sin(math.radians(lo))
        return 38.0 - 45.0 * max(0.0, sn) ** 1.3 + 7.0 * max(0.0, -sn)
    CAP = 0.0115
    cap = env.patch("pauldron", PLATE, -180.0, 180.0, rim, lambda lo: 84.0, CAP, 0.0035, nu=24, nv=5, closed=True, pole=True, bevel=0.0015)
    arm.add(cap, ua)
    glued += [cap.matrix_world @ v.co for v in cap.data.vertices]
    glue_body(c, mech.bead("pauldron_rim", [env.P(rim(lo), lo, CAP - 0.0014) for lo in range(-180, 180, 10)], 0.003, segs=5,
                           normal=lambda q: Vector(q) - O), coat, 0.0)
    spots = [(env.P(rim(lo) + 6, lo, CAP), env.normal(rim(lo) + 6, lo, CAP)) for lo in range(-160, 180, 32)]
    spots += [(lame_tu.P(0.245, ph, 0.009), lame_tu.d(ph)) for ph in (OUT - 52, OUT + 52)]
    glue_body(c, mech.rivets("pauldron_rivets", spots, r=0.0036, material=PLATE, segs=6), coat, 0.0)
    M = pmc.frame(env.P(30, 90, CAP), env.normal(30, 90, CAP), (0, 0, 1))
    arm.detail(mech.decal_on("pauldron_cog", pmc.tree(cap), mech.cog(0.0, 0.0, 0.03, teeth=9, depth=0.26), (0.0, 0.0, 0.011), M, "paint.scrap_paint"))
    tu = aco.Tube([sleeve], ua0, ua1, hard=[lame], t=(0.2, 0.6), nt=9, nphi=36, reach=0.16)
    bru.strap_round(c, "pauldron_strap", tu, 0.4, ua, 0.022, 0.0035, buckle_ph=OUT + 150 * sx)
    return glued


def bracer(c, b, arm, coat, gloves, s, sx, guide=False):
    """A riveted steel bracer over the sleeve's end and the glove's cuff, open on the inside and closed
    with two straps; on the line arm a brass line guide (two rollers on a bracket) at the wrist."""
    fa = "forearm." + s
    fa0, fa1 = b.j(fa, 0.0), b.j(fa, 1.0)
    OUT = 90 * sx
    sleeve = aco.region_tree(coat, {fa})
    tg = pmc.tree(gloves)
    tf = aco.Tube([sleeve, tg], fa0, fa1, front=(0, -1, 0), t=(0.0, 1.08), nt=26, nphi=48, reach=0.13, spread=0.025, blur=0.018)

    def off(t, ph):
        return 0.005 + 0.006 * sm(t, 0.6, 1.0)
    G0, G1, GH = 0.36, 0.98, 128.0
    plate = bru.tube_plate(tf, "bracer", PLATE, G0, G1, OUT, GH, off, 0.0032, nu=16, nv=7, corner=0.0, bevel=0.0012)
    arm.add(plate, fa)
    for t in (G0, G1):
        c.rigid(mech.bead("bracer_rim", [tf.P(t, OUT + GH * (2 * k / 16 - 1), off(t, 0) - 0.0014) for k in range(17)], 0.0026,
                          closed=False, segs=5, normal=lambda q: tf.d(OUT)), fa)
    spots = []
    for t in (G0 + 0.05, G1 - 0.05):
        for k in range(1, 7):
            ph = OUT - GH + 2 * GH * k / 7
            spots.append((tf.P(t, ph, off(t, ph)), tf.d(ph)))
    c.rigid(mech.rivets("bracer_rivets", spots, r=0.0033, material=PLATE, segs=6), fa)
    tf2 = aco.Tube([sleeve, tg], fa0, fa1, hard=[plate], t=(0.3, 1.0), nt=15, nphi=36, reach=0.15)
    for t in (0.5, 0.82):
        bru.strap_round(c, "bracer_strap", tf2, t, fa, 0.02, 0.0032, buckle_ph=OUT + 180)
    if guide:
        t = 0.9
        p, n = tf.P(t, OUT, off(t, OUT)), tf.d(OUT)
        A = tf.A
        S = A.cross(n).normalized()
        parts = [kit.block("guide_bracket", (0, 0.006, 0), (0.05, 0.012, 0.03), "brass", bevel=0.0015)]
        for dx in (-0.009, 0.009):  # the rollers square to the line, which runs along the forearm
            parts.append(kit.cyl("guide_roller", (dx, 0.019, -0.017), (dx, 0.019, 0.017), 0.0062, "brass", segs=10, bevel=0.0008))
            parts.append(kit.cyl("guide_axle", (dx, 0.019, -0.021), (dx, 0.019, 0.021), 0.0024, "steel", segs=6, bevel=0))
        c.rigid(place(join(parts, "line_guide"), p, A, n, S), fa)


# ------------------------------------------------------------------------------------- on the belt

def spyglass(c, b, belt):
    """A brass spyglass, closed up, in a tan holster hanging from the belt at the left hip, tilted
    forward: the leather-wrapped barrel in the holster, the brass draw and eyepiece above it."""
    pts, dirs = belt["pts"], belt["dirs"]
    n = len(pts)
    i = round(n * 78 / 360)
    p, d = pts[i], dirs[i]
    A = (Vector((0, 0, 1)) + d * 0.18 + Vector((0, -0.32, 0))).normalized()
    base = p + d * 0.03 - Vector((0, 0, 0.075))
    x, _, z = basis(d, A)
    parts = [kit.cyl("holster", base - A * 0.075, base + A * 0.05, 0.027, "accent", r1=0.0255, segs=12, bevel=0.0015),
             kit.cyl("holster_tip", base - A * 0.085, base - A * 0.075, 0.021, "accent", r1=0.027, segs=12, bevel=0.0)]
    gl = [kit.cyl("glass_barrel", base + A * 0.05, base + A * 0.095, 0.0215, "brass", segs=14, bevel=0.0008),
          kit.cyl("glass_ring", base + A * 0.093, base + A * 0.101, 0.0232, "brass", segs=14, bevel=0.0008),
          kit.cyl("glass_draw", base + A * 0.101, base + A * 0.14, 0.0165, "brass", segs=12, bevel=0.0008),
          kit.cyl("glass_eye", base + A * 0.14, base + A * 0.152, 0.0135, "brass", r1=0.012, segs=12, bevel=0.0008),
          kit.cyl("glass_lens", base + A * 0.152, base + A * 0.1535, 0.008, "scrap_lens", segs=10, bevel=0.0)]
    hol = join(parts, "holster")
    leather(hol)
    c.rigid(hol, "hips")
    c.rigid(join(gl, "spyglass"), "hips")
    # The holster's loop over the belt.
    q = p + d * 0.0035
    c.rigid(leather(pmc.sweep("holster_loop", [q + Vector((0, 0, 0.034)), q + d * 0.012 + Vector((0, 0, 0.03)), base + A * 0.04 + d * 0.022],
                              0.026, 0.004, "accent", lambda qq: d, bevel=0.0)), "hips")
    _ = (x, z)


def line_reel(c, b, belt):
    """The harpoon line's reel on the back of the right hip: a brass drum of hemp line between two
    flanges on a riveted steel bracket from the belt, a crank with a turned handle."""
    pts, dirs = belt["pts"], belt["dirs"]
    n = len(pts)
    i = round(n * (360 - 112) / 360) % n
    p, d = pts[i], dirs[i]
    at = p + d * 0.04 - Vector((0, 0, 0.035))
    x, y, z = basis(d)
    parts = [kit.block("reel_bracket", (0, -0.034, 0.02), (0.05, 0.008, 0.09), PLATE, bevel=0.0015),
             kit.cyl("reel_flange", (0, -0.03, 0), (0, -0.024, 0), 0.056, "brass", segs=18, bevel=0.0012),
             kit.cyl("reel_flange", (0, 0.024, 0), (0, 0.03, 0), 0.056, "brass", segs=18, bevel=0.0012),
             kit.cyl("reel_line", (0, -0.024, 0), (0, 0.024, 0), 0.045, "trap_hemp", segs=18, bevel=0.0),
             kit.cyl("reel_hub", (0, 0.03, 0), (0, 0.04, 0), 0.014, PLATE, segs=10, bevel=0.001),
             kit.block("reel_crank", (0.024, 0.043, 0), (0.06, 0.006, 0.011), "steel", bevel=0.0015),
             kit.cyl("reel_handle", (0.05, 0.046, 0), (0.05, 0.072, 0), 0.0062, "scrap_ash", segs=8, bevel=0.0008)]
    parts.append(mech.rivets("reel_rivets", [(Vector((sx_ * 0.016, -0.038, zz)), Vector((0, -1, 0))) for sx_ in (-1, 1) for zz in (0.05, 0.03)],
                             r=0.003, material=PLATE, segs=6))
    reel = join(parts, "line_reel")
    place(reel, at, x, y, z)
    c.rigid(reel, "hips")


def net_roll(c, b, belt, tail):
    """A tarred net rolled up across the small of the back on the belt, two tan straps round it, and a
    loose flap of it hanging over the coat at the right hip, a few knots of it hanging free."""
    pts, dirs, yc = belt["pts"], belt["dirs"], belt["yc"]
    n = len(pts)
    p, d = pts[n // 2], dirs[n // 2]
    R, L = 0.052, 0.36
    ctr = p + d * (R + 0.006) + Vector((0, 0, R * 0.6))
    roll = [kit.cyl("net_roll", ctr - Vector((L / 2, 0, 0)), ctr + Vector((L / 2, 0, 0)), R, "trap_net", segs=16, bevel=0.004)]
    c.rigid(join(roll, "net_roll"), "hips")
    straps = []
    for x in (-0.11, 0.11):
        straps.append(kit.ring("net_strap", ctr + Vector((x, 0, 0)), (1, 0, 0), R + 0.0045, R - 0.001, 0.024, "accent", segs=16))
        q = Vector((x, p.y, p.z)) + d * 0.004
        straps.append(pmc.sweep("net_strap_tab", [q - Vector((0, 0, 0.026)), q + Vector((0, 0, 0.02)), ctr + Vector((x, 0, 0)) - d * (R - 0.002) + Vector((0, 0, -0.01))],
                                0.024, 0.004, "accent", lambda qq: d, bevel=0.0))
    c.rigid(leather(join(straps, "net_straps")), "hips")
    # The loose flap: a lattice of cord over the coat tail, diamonds, hanging from the roll's right end.
    tt = pmc.tree(tail)
    top = ctr + Vector((L / 2 - 0.1, 0, -R * 0.6))
    nu, nv, w, h = 5, 7, 0.025, 0.034
    bm = bmesh.new()
    V = {}
    for i in range(nu + 1):
        for j in range(nv + 1):
            s_, t_ = i - nu / 2, j
            x = top.x - (s_ - t_ * 0.35) * w * 0.9
            z = top.z - t_ * h - abs(s_) * 0.006
            sag = 0.018 * math.sin(math.pi * i / nu) * (j / nv)
            q0 = Vector((x, yc + 0.4, z - sag))
            loc, nor = pmc.hit(tt, q0, (0, -1, 0))
            if loc is None:
                loc, nor = Vector((x, p.y + 0.02, z - sag)), Vector((0, 1, 0))
            V[(i, j)] = bm.verts.new(loc + Vector(nor).normalized() * 0.007)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((V[(i, j)], V[(i + 1, j)], V[(i + 1, j + 1)], V[(i, j + 1)]))
    flap = real._bm_obj("net_flap", bm)
    flap.data.materials.append(kit.mat("trap_hemp"))
    wf = flap.modifiers.new("cord", "WIREFRAME")
    wf.thickness, wf.use_even_offset, wf.use_replace = 0.0034, True, True
    kit.hs._apply(flap, wf.name)
    knee = b.j("lower_leg.L", 0.0).z
    fn = aco.hang_weights(belt["z"] + 0.02, b.sole + 0.335, side=0.08, legs=0.85, lower=(knee - 0.02, 0.5))
    aco.weigh_custom(c, flap, fn)


def boot_straps(c, b, boot):
    """Two buckled straps round each boot's shaft."""
    tb = pmc.tree(boot)
    for s, sx in (("L", 1), ("R", -1)):
        ll = "lower_leg." + s
        a, e = b.j(ll, 0.0), b.j(ll, 1.0)
        tu = aco.Tube([tb], a, e, t=(0.3, 1.0), nt=15, nphi=36, reach=0.15)
        for zz in (b.sole + 0.2, b.sole + 0.272):
            t = (a.z - zz) / (a.z - e.z)
            bru.strap_round(c, "boot_strap", tu, t, ll, 0.019, 0.0032, buckle_ph=90 * sx)


SPEC = {"build": build, "faction": "scrappers", "budget": (25000, 120000), "loadout": "harpoon",
        "colors": {"primary": "#544632", "secondary": "#3f433b", "accent": "#8b5a2b"}}
