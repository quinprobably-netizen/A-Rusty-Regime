"""Ghost, Deserters: the light scout, a sniper's spotter who walked out of the Regime with nothing but
the mask on his face. A slim body under a kraft cotton-duck cowl, one piece from the hood to the shoulder
cape, and two long tails hanging down the back to the knees with a cream hem band, all draped by the
cloth simulation. Under the hood a black knit balaclava and the Acolyte's faceplate, cracked and
patched: the bone-white mask from the jaw to the brow with the respirator kept, the sensor slit lit
amber on the right and smashed open over the left eye (a jagged break in the brow plate, the dark
glass behind it), a riveted steel patch over the left temple, staples across a crack down the right
cheek, the cult's code scratched off the jaw, one clay stripe painted down over the right eye.

Under the cowl the crew's slate combat shirt and cargo trousers, a low slate chest rig with
three pistol magazines; a cream climbing harness (waist belt, leg loops, belay loop and ring, two
carabiners), an empty drop-leg holster on the right thigh, the Runner's clay knee caps, calf-mounted
jump jets (the crew's slate housing, clay cover and gunmetal nozzles), a wrist unit on the left
forearm, armoured gloves and low tactical boots.

Built on the realistic layer (real.py) with the Acolyte's armour classes; the suit, glove, paint and
plate helpers come from breaker.py. The mask's paint is breaker's "scavpaint" recipe with this
module's own stripe and cracks (MARKS, CRACKS: shapes in rest-pose space, read at bake time); the code
scratched off it is breaker's scratched-out tiles.

Tints: primary = shirt, trousers, balaclava and chest rig (slate); secondary = the cloak, cowl and
tails (kraft); accent = harness, rig straps, pull tabs and the tails' hem band (cream). The mask and
the clay shells are fixed colours in the same palette.
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
from kit import UPPER_ARMS, FOREARMS, THIGHS, SHINS
from chars import contractor as pmc
from chars import acolyte as reg
from chars import breaker as brk
from chars.breaker import PAINT, SLATE, CREAM, KRAFT, hard, glove_guards, combat_shirt, combat_trousers, _sm
from chars.runner import oriented

ARMS = UPPER_ARMS | FOREARMS
LEGS = THIGHS | SHINS
FAST = bool(os.environ.get("GHOST_FAST")) or brk.FAST   # look-dev: skip the cloth simulation

# ------------------------------------------------------------------------------------ the mask's paint

kit.hs.PALETTE.update({
    # name: (paint, worn (the coat under it), metallic, roughness, shared edge wear, emission)
    "gst_mask": (PAINT["cream"], (0.47, 0.45, 0.41), 0.0, 0.46, 0.0, 0),
    "gst_clay": (PAINT["clay"], (0.36, 0.26, 0.21), 0.0, 0.5, 0.35, 0),
})

MARKS = []     # the clay stripe (breaker.stripe's layout)
CRACKS = []    # (centre, radius, seed): crazing round the impacts


def ghost_mask(g, pal):
    """The cracked Regime mask: breaker's scavenged paint over the bone coat, with this mask's own clay
    stripe and cracks."""
    return brk.scav_paint(g, pal, marks=MARKS, mark_col=PAINT["clay"], cracks=CRACKS)


def duck(g, pal):
    """Heavy cotton duck for the cloak, worn hard: a coarse plain weave of thick yarns 3.4 mm apart
    (nothing finer than the bake resolves: a fine weave would alias into a checker on a garment this
    size), thick-and-thin slub streaks along the warp, then the field wear that makes it read as cloth
    from across a room: sun-bleached and darkened patches and soft grey grime."""
    base = pal[0]
    uv = g.uv()
    u, v, _ = g.xyz(uv)
    pos = g.geo("Position")
    p = 0.0034
    wa = g.math("SINE", g.mul(u, 2 * math.pi / p))
    wb = g.math("SINE", g.mul(v, 2 * math.pi / p))
    weave = g.add(0.5, g.mul(g.mul(wa, wb), 0.5))
    slub = g.remap(g.noise(g.combine(u, g.mul(v, 0.05), 0.0), 34.0, detail=2), 0.35, 0.65)
    yarn = g.remap(g.noise(g.combine(g.mul(u, 0.06), v, 0.0), 90.0, detail=1), 0.3, 0.7)
    fade = g.noise(pos, 2.6, detail=3)
    stain = g.remap(g.noise(pos, 6.0, detail=4, distort=0.3), 0.52, 0.72)
    shade = g.add(g.remap(fade, 0.3, 0.7, 0.74, 0.98, smooth=False),
                  g.add(g.mul(g.sub(slub, 0.5), 0.12), g.add(g.mul(g.sub(yarn, 0.5), 0.06), g.mul(g.sub(weave, 0.5), 0.07))))
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    col = g.mix(g.mul(stain, 0.32), col, (0.42, 0.42, 0.44))       # grime: darker and greyer than the cloth
    h = g.add(g.mul(weave, 0.55), g.add(g.mul(slub, 0.3), g.mul(yarn, 0.15)))
    rough = g.lerp(stain, g.lerp(weave, 0.86, 0.95), 0.97)
    return dict(color=col, rough=rough, metal=0.0, height=h, bump=0.0005)


surfaces.RECIPES.setdefault("duck", duck)
surfaces.SOFT.add("duck")   # fabric wear (fading, fraying, stitching), as the crew's other cloth
surfaces.RECIPES.setdefault("ghostmask", ghost_mask)
surfaces.RECIPE.setdefault("gst_mask", "ghostmask")
kit.hs.PALETTE.setdefault("gst_mask_scr", kit.hs.PALETTE["gst_mask"][:3] + (0.52, 0.0, 0))
surfaces.RECIPE.setdefault("gst_mask_scr", "scratched")
surfaces.RECIPE.setdefault("gst_clay", "pilotshell")
MASK, CLAY = "gst_mask", "gst_clay"


def stripe(p, n, hw, ball=None, r=0.0, halves=()):
    MARKS.append((Vector(p).copy(), Vector(n).normalized(), hw, Vector(ball).copy() if ball is not None else None, r,
                  [(Vector(a).copy(), Vector(b).normalized()) for a, b in halves]))


def crack(p, r, seed):
    CRACKS.append((Vector(p).copy(), r, seed))


def _rnd(i):
    """A repeatable pseudo-random number in 0..1 for an integer."""
    f = math.sin(i * 12.9898 + 78.233) * 43758.5453
    return f - math.floor(f)


def _jag(x, step):
    """A random jagged line: a value in -1..1 per `step`, joined straight."""
    k = math.floor(x / step)
    t = x / step - k
    return (2 * _rnd(k) - 1) * (1 - t) + (2 * _rnd(k + 1) - 1) * t


def _head_tree(man):
    dom = kit.dominant(man.low)
    me = man.low.data
    co = [v.co.copy() for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons if sum(dom[i] in ("head", "neck") for i in p.vertices) * 2 > len(p.vertices)]
    return BVHTree.FromPolygons(co, polys)


def _collider(objs, bone, name):
    """A copy of rigid parts as one mesh skinned wholly to `bone` (a collision object for real.drape)."""
    copies = []
    for o in objs:
        h = bpy.data.objects.new(name, o.data.copy())
        bpy.context.scene.collection.objects.link(h)
        h.matrix_world = o.matrix_world.copy()
        copies.append(h)
    j = kit.join(copies, name) if len(copies) > 1 else copies[0]
    j.vertex_groups.clear()
    j.vertex_groups.new(name=bone).add(list(range(len(j.data.vertices))), 1.0, "REPLACE")
    return j


# ------------------------------------------------------------------------------------ the mask

def cracked_mask(c, man, arm):
    """The Acolyte's faceplate, cracked and patched (see the module docstring). Returns (envelope,
    the mask's pieces for collision)."""
    hc = man.head_center()
    O = hc + Vector((0, -0.016, -0.018))
    env = reg.Env([_head_tree(man)], O, reach=0.22, lat=(-80.0, 90.0), dlat=4.0, dlon=5.0, spread=14.0, blur=10.0, floor=0.006)
    SLIT_LO, SLIT_HI = 3.0, 12.5
    BROW = 0.0155   # the brow plate's outer surface over the envelope

    def chin(lo):
        return -57.0 + 17.0 * _sm(abs(lo), 0, 82)

    def mtop0(lo):
        return SLIT_LO + 12.5 * _sm(abs(lo), 54, 70)

    def bite(lo):   # a chip out of the faceplate's top edge under the left eye
        w = _sm(lo, 14, 22) * (1 - _sm(lo, 34, 44))
        return w * (3.6 + 1.4 * _jag(lo + 20.0, 2.7))

    def mtop(lo):
        return mtop0(lo) - bite(lo)

    def mask_off(la, lo):
        keel = 0.0034 * math.exp(-(lo / 5.0) ** 2) * _sm(SLIT_LO - la, 2.0, 14.0)
        snout = 0.0105 * math.exp(-((la + 30.0) / 17.0) ** 2 - (lo / 30.0) ** 2)
        return 0.0215 + keel + snout

    def broken(lo):  # the brow plate broken away over the left eye: a jagged edge
        w = _sm(lo, 7, 15) * (1 - _sm(lo, 50, 60))
        return w * (8.0 + 3.0 * _jag(lo, 3.1) + 1.2 * _jag(lo + 40.0, 1.3))

    def blo(lo):
        return SLIT_HI + (mtop0(lo) - 1.5 - SLIT_HI) * _sm(abs(lo), 54, 70) + broken(lo)

    def bhi(lo):
        return 55.0 - 22.0 * _sm(abs(lo), 30, 82)

    def brow_off(la, lo):
        ridge = 0.0025 * math.exp(-((la - SLIT_HI - 5.0) / 5.0) ** 2) * (1 - _sm(abs(lo), 50, 75))
        return BROW + ridge

    face = env.patch("faceplate", MASK, -82.0, 82.0, chin, mtop, mask_off, 0.0065, nu=34, nv=11, inner="regime_pad", bevel=0.0016)
    brow = env.patch("brow_plate", MASK, -82.0, 82.0, blo, bhi, brow_off, 0.0055, nu=66, nv=6, inner="regime_pad", bevel=0.0012)
    arm.add(face, "head")
    arm.add(brow, "head")
    visor = env.patch("visor", "glass", -76.0, 76.0, lambda lo: mtop(lo) - 1.5, lambda lo: blo(lo) + 1.5, 0.0092, 0.002, nu=44, nv=3, bevel=0.0)
    c.rigid(visor, "head")
    # The sensor slit: still lit (amber) on the right, dead under the break on the left.
    c.rigid(env.patch("sensor", "glow_amber", -52.0, -6.0, lambda lo: 6.6, lambda lo: 8.6, 0.0108, 0.0022, nu=12, nv=1, bevel=0.0), "head")
    c.rigid(env.patch("sensor_dead", "black", 4.0, 12.0, lambda lo: 6.6, lambda lo: 8.6, 0.0108, 0.0022, nu=3, nv=1, bevel=0.0), "head")

    # Respirator vents either side of the snout (the Acolyte's), screws at the corners.
    for sx in (1, -1):
        a0, a1 = sorted((sx * 17.0, sx * 38.0))
        c.rigid(env.patch("vent", "black", a0, a1, lambda lo: -40.0, lambda lo: -20.0, lambda la, lo: mask_off(la, lo) + 0.0012, 0.003,
                          nu=6, nv=4, bevel=0.0008, segs=1), "head")
        for k in range(4):
            la0 = -37.0 + k * 4.6
            c.rigid(env.patch("vent_slat", "gunmetal", a0 + 1.5, a1 - 1.5, lambda lo, la0=la0: la0, lambda lo, la0=la0: la0 + 1.6,
                              lambda la, lo: mask_off(la, lo) + 0.0028, 0.0018, nu=5, nv=1, bevel=0.0), "head")
        for la, lo in ((-6, sx * 74), (-34, sx * 70)):
            arm.detail(reg.screw(env.P(la, lo, mask_off(la, lo)), env.normal(la, lo, mask_off(la, lo)), r=0.0032))
        for la, lo in ((28, sx * 70),):
            arm.detail(reg.screw(env.P(la, lo, brow_off(la, lo)), env.normal(la, lo, brow_off(la, lo)), r=0.003))

    # The steel patch riveted over the left temple, across the end of the break.
    pat = env.patch("mask_patch", "gunmetal", 50.0, 72.0, lambda lo: 6.0 + 0.1 * (lo - 50), lambda lo: 31.0 - 0.15 * (lo - 50),
                    lambda la, lo: max(mask_off(la, lo), brow_off(la, lo)) + 0.0028, 0.0024, nu=6, nv=5, bevel=0.0008)
    arm.add(pat, "head")
    for la, lo in ((9.5, 53.5), (26.5, 53.5), (9.5, 68.5), (25.0, 68.5)):
        off = max(mask_off(la, lo), brow_off(la, lo)) + 0.0028
        arm.detail(reg.screw(env.P(la, lo, off), env.normal(la, lo, off), r=0.0024, material="bright"))
    # Staples across the crack down the right cheek.
    for la in (-3.0, -11.0, -19.0):
        lo = -44.0 + 0.15 * la
        off = mask_off(la, lo)
        p, n = env.P(la, lo, off), env.normal(la, lo, off)
        t = (env.P(la, lo + 2.0, off) - env.P(la, lo - 2.0, off)).normalized()
        st = kit.block("staple", (0, 0, 0), (0.013, 0.0022, 0.0022), "bright", bevel=0.0004)
        oriented(st, p + n * 0.0009, t, n, n.cross(t))
        arm.detail(st)

    # Paint: the code scratched off the jaw and the brow; one clay stripe down over the right eye;
    # crazing round the break, the stapled crack and a knock on the chin.
    for sx in (1, -1):
        for la in (-19.0, -24.5):
            brk.scratch_out(arm, face, [env.P(la, sx * lo, mask_off(la, sx * lo)) for lo in brk._steps(52, 68, 2)], 0.0048, MASK,
                            seed=int(la * sx) + 90)
    for la, l0, l1 in ((34.0, -62, -37), (29.5, -60, -40), (40.0, -10, 16)):
        brk.scratch_out(arm, brow, [env.P(la, lo, brow_off(la, lo)) for lo in brk._steps(l0, l1, 3)], 0.005, MASK, seed=int(la) + 7)
    sp = env.P(0, -27, mask_off(0, -27))
    stripe(sp, (1, 0, 0), 0.0095, O, 0.2)
    crack(env.P(SLIT_HI + 10, 30, BROW), 0.05, 1.3)
    crack(env.P(-12, -44, mask_off(-12, -44)), 0.032, 4.1)
    crack(env.P(-46, 16, mask_off(-46, 16)), 0.02, 7.7)
    return env, [face, brow, pat]


# ------------------------------------------------------------------------------------ the cloak

def cowl(c, man, lead, under, hc, mask_parts):
    """The hood and shoulder cape in one piece: cut from the body round the head, neck and shoulders,
    eased off it (loose at the back of the hood), the face opened by two planes that frame the mask,
    the hem slanting from the upper chest to the shoulder blades, draped by the cloth simulation
    (the face edge and crown held, the back of the hood and the hem free to fall)."""
    b = c.b
    J = b.j
    armpit = b.at("armpit")
    y_face = hc.y - 0.045
    zf = hc.z + 0.02
    P_face = Vector((0, y_face, zf))
    n_top = Vector((0, -1, -1.0)).normalized()
    n_side = Vector((0, -1, 0))
    chin_z = hc.z - 0.12
    zc = armpit + 0.02
    hem_n = Vector((0, -0.8, -1)).normalized()

    def on_arm(p):
        return lead(p) in ARMS

    def headish(p):
        return lead(p) in ("head", "neck")
    cuts = [(P_face, n_top, lambda p: headish(p) and p.z > zf),
            (P_face, n_side, lambda p: headish(p) and chin_z < p.z <= zf),
            (Vector((0, 0, zc)), hem_n, lambda p: not on_arm(p))]
    for s, sx in (("L", 1), ("R", -1)):
        a0, a1 = J("upper_arm." + s, 0.0), J("upper_arm." + s, 1.0)
        A = (a1 - a0).normalized()
        cuts.append((a0.lerp(a1, 0.16), a1 - a0, lambda p, s=s: on_arm(p) and lead(p).endswith(s)))
        # Only the outer half of the arm, cut along it (a straight edge, not the faces' steps): the
        # cape falls over the shoulder, not into the armpit.
        n_raw = Vector((-sx, 0.0, 0.0)) - A * A.dot(Vector((-sx, 0.0, 0.0)))
        cuts.append((a0 + n_raw.normalized() * (0.012 / max(n_raw.length, 0.3)), n_raw,
                     lambda p, s=s: on_arm(p) and lead(p).endswith(s)))
    region = {"head", "neck", "chest", "spine", "shoulder.L", "shoulder.R", "upper_arm.L", "upper_arm.R"}

    def keep(p):
        return lead(p) in region and p.z > armpit - 0.22

    def ease(p):
        L = lead(p)
        if L == "head":
            return 0.044 + 0.02 * _sm(p.y - hc.y, 0.0, 0.09) + 0.006 * _sm(p.z - hc.z, 0.04, 0.12)
        if L == "neck":
            return 0.04
        return 0.026

    def pin(p):
        if lead(p) == "head":
            if p.y < hc.y + 0.01 and p.z > hc.z - 0.07:
                return 1.0
            if p.z > hc.z + 0.085:
                return 1.0
        return 0.0

    def slack(p):
        w = 0.0
        if lead(p) == "head" and p.y > hc.y:
            w = 0.8 * _sm(p.y - hc.y, 0.0, 0.06)
        if lead(p) == "neck":
            w = 0.35
        d = (p - Vector((0, 0, zc))).dot(-hem_n)   # height over the hem plane
        if not on_arm(p):
            w = max(w, 0.06 * (1 - _sm(d, 0.0, 0.08)))
        return w
    cols = [_collider(mask_parts, "head", "mask_col")] + list(under)
    form = _hood_form(man, hc)
    g = _garment(c, form, "cowl", "duck.secondary", keep, cuts, ease=ease, smooth=6, pin=None if FAST else pin, slack=slack,
                 bend=14.0, collide=cols, texel=1.0, frames=34)
    bpy.data.objects.remove(cols[0], do_unlink=True)
    bpy.data.objects.remove(form.low, do_unlink=True)
    return g


def _garment(c, man, name, kind, keep, cuts=(), ease=0.012, smooth=3, pin=None, slack=None, fine=2, texel=1.0,
             hem_relax=8, **sim):
    """real.garment with one step more (a local copy, real.py stays as it is): before the cloth is
    subdivided and draped, every open edge of the shell is relaxed along itself `hem_relax` times.
    Where a cut plane's reach (its `near` test, decided per face) changes from one face to the next,
    the bisected edge zig-zags between the two planes; relaxed along the loop, it runs as one clean
    hem instead of a saw-tooth."""
    groups = [g.name for g in man.low.vertex_groups]
    bm = real._shell_bm(man, keep, cuts, ease, smooth)
    bnd = [v for v in bm.verts if v.is_boundary]
    nbr = {v: [e.other_vert(v) for e in v.link_edges if e.is_boundary] for v in bnd}
    for _ in range(hem_relax):
        new = {v: v.co * 0.5 + (nb[0].co + nb[1].co) * 0.25 for v, nb in nbr.items() if len(nb) == 2}
        for v, co in new.items():
            v.co = co
    coarse = [v.co.copy() for v in bm.verts]
    low = real._bm_obj(name, bm.copy(), None, groups)
    if fine:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=fine, use_grid_fill=True, smooth=0.0)
    kd = KDTree(len(bm.verts))
    for i, v in enumerate(bm.verts):
        kd.insert(v.co, i)
    kd.balance()
    where = np.array([kd.find(q)[1] for q in coarse])
    high = real._bm_obj(name + ".high", bm, None, groups)
    m = real.mat(kind)
    for o in (low, high):
        o.data.materials.append(m)
    if pin is not None:
        real.drape(c, man, high, pin, slack, **sim)
    co = np.zeros(len(high.data.vertices) * 3)
    high.data.vertices.foreach_get("co", co)
    low.data.vertices.foreach_set("co", co.reshape(-1, 3)[where].ravel())
    low.data.update()
    real.seam_attrs(high)
    real.seam_attrs(low)
    low["texel"] = texel
    c.parts.append((low, "DONE", None))
    c.detail(low, [high], ext=0.012, ray=0.03)
    return real.Garment(low, high)


def tails(c, man, name, kind, hem_kind, under, top, z_bot, a_in, a_out, cy=0.01, nu=14, nv=22, fine=2, ease=0.012,
          flare=0.035, hem=0.042, collide=(), texel=1.0):
    """The cloak's two tails down the back: panels round the back from `a_in` to `a_out` degrees each
    side of the spine (0 = straight back, + toward the left), from `top(a)` (a height for each azimuth
    a: tucked under the cape's hem) to `z_bot`. Each column keeps the widest radius of the `under` surfaces met on the way down
    (shirt, trousers, belt kit) plus `ease`, flaring out `flare` at the hem; the bottom `hem` metres
    are the band in `hem_kind`. Weighted chest -> spine -> hips -> its own thigh further down, and
    draped by the cloth simulation pinned along the top. Returns a real.Garment, registered."""
    b = c.b
    armpit = b.at("armpit")
    trees = [o if isinstance(o, BVHTree) else pmc.tree(o) for o in under]

    def d_of(a):
        a = math.radians(a)
        return Vector((math.sin(a), math.cos(a), 0.0))

    def outer(a, z):
        d = d_of(a)
        o = Vector((0.0, cy, z))
        best = 0.0
        for t in trees:
            loc, _, _, _ = t.ray_cast(o + d * 0.6, -d, 0.6)
            if loc is not None:
                best = max(best, (loc - o).dot(d))
        return best
    groups = ["chest", "spine", "hips", "upper_leg.L", "upper_leg.R"]
    gi = {g_: k for k, g_ in enumerate(groups)}

    def weights(z, s):
        up = _sm(z, b.hip_z + 0.03, b.hip_z + 0.17)
        cs = _sm(z, armpit - 0.16, armpit - 0.06)
        leg = 0.55 * _sm(b.hip_z - 0.03 - z, 0.0, b.hip_z - 0.03 - z_bot)
        return {"chest": up * cs, "spine": up * (1 - cs), "hips": (1 - up) * (1 - leg), "upper_leg." + s: (1 - up) * leg}
    bm = bmesh.new()
    dl = bm.verts.layers.deform.verify()
    uvl = bm.loops.layers.uv.new("UVMap")
    for s, sx in (("L", 1), ("R", -1)):
        az = [sx * (a_in + (a_out - a_in) * j / nu) for j in range(nu + 1)]
        # Each column's top under the cape's hem, then its radii: the running maximum down from there.
        t0 = [top(a) for a in az]
        tops = [(t0[max(j - 1, 0)] + 2 * t0[j] + t0[min(j + 1, nu)]) / 4 for j in range(nu + 1)]
        Zs = [[t + (z_bot - t) * i / nv for t in tops] for i in range(nv + 1)]
        raw = [[outer(a, Zs[i][j]) for j, a in enumerate(az)] for i in range(nv + 1)]
        for j in range(nu + 1):
            # A column whose top misses every surface (above them all) takes its first hit below:
            # never a point on the spine's axis, inside the body.
            hit = next((raw[i][j] for i in range(nv + 1) if raw[i][j] > 0.0), 0.13)
            for i in range(nv + 1):
                if raw[i][j] > 0.0:
                    break
                raw[i][j] = hit
        R = []
        run = [0.0] * len(az)
        for i in range(nv + 1):
            run = [max(r, raw[i][j]) for j, r in enumerate(run)]
            h = i / nv
            R.append([r + ease + flare * h ** 1.5 + (0.003 + 0.011 * h) * math.sin(2 * math.pi * 3.2 * j / nu + 1.3 * sx)
                      for j, r in enumerate(run)])
        grid = []
        for i in range(nv + 1):
            row = []
            for j, a in enumerate(az):
                z = Zs[i][j]
                v = bm.verts.new(Vector((0.0, cy, z)) + d_of(a) * R[i][j])
                for gname, wt in weights(z, s).items():
                    if wt > 1e-4:
                        v[dl][gi[gname]] = wt
                row.append(v)
            grid.append(row)
        for i in range(nv):
            for j in range(nu):
                q = (grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j])
                f = bm.faces.new(q if sx > 0 else q[::-1])
                if (Zs[i][j] + Zs[i + 1][j]) / 2 < z_bot + hem:
                    f.material_index = 1
                for l in f.loops:
                    p = l.vert.co
                    a = math.degrees(math.atan2(p.x, p.y - cy))
                    l[uvl].uv = (math.radians(a) * 0.2, p.z)
    bm.normal_update()
    if sum(f.normal.dot(Vector((f.calc_center_median().x, f.calc_center_median().y - cy, 0))) for f in bm.faces) < 0:
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
        o.data.materials.append(real.mat(kind))
        o.data.materials.append(real.mat(hem_kind))
    if not FAST:
        real.drape(c, man, high, lambda p: 1.0 if p.z > top(math.degrees(math.atan2(p.x, p.y - cy))) - 0.03 else 0.0, None,
                   collide=collide, bend=7.0, mass=0.3, frames=36)
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


def _hood_form(man, hc):
    """The body with the head rounded out to a broad envelope (ears and jaw bridged): the form a loose
    hood is cut from and falls over (a stand-in for `man` in real.garment)."""
    import types
    o = bpy.data.objects.new("hood_form", man.low.data.copy())
    bpy.context.scene.collection.objects.link(o)
    for g in man.low.vertex_groups:
        o.vertex_groups.new(name=g.name)
    O = hc + Vector((0, -0.016, -0.018))
    env = reg.Env([_head_tree(man)], O, reach=0.24, lat=(-80.0, 90.0), dlat=5.0, dlon=6.0, spread=30.0, blur=16.0, floor=0.004)
    dom = kit.dominant(man.low)
    for v in o.data.vertices:
        if dom[v.index] != "head":
            continue
        d = v.co - O
        r = d.length
        d.normalize()
        la = math.degrees(math.asin(max(-1.0, min(1.0, d.z))))
        lo = math.degrees(math.atan2(d.x, -d.y))
        re = env.r(max(la, -80.0), lo)
        if re > r:
            v.co = O + d * (r + (re - r) * _sm(la, -62.0, -30.0))
    o.data.update()
    return types.SimpleNamespace(low=o)


def _offset_copy(obj, d, name):
    """A copy of a skinned garment pushed `d` out along its normals (a collision proxy that covers
    the straps lying on it)."""
    h = bpy.data.objects.new(name, obj.data.copy())
    bpy.context.scene.collection.objects.link(h)
    for g in obj.vertex_groups:
        h.vertex_groups.new(name=g.name)
    me = h.data
    for v in me.vertices:
        v.co += v.normal * d
    me.update()
    return h


# ------------------------------------------------------------------------------------ build

def build():
    for L in (MARKS, CRACKS):
        del L[:]
    b = real.Anatomy(height=1.77, width=0.93, body="male", sole=0.03, stance=0.21)
    c = real.begin("ghost", b)
    man = real.body(c, stubble=0.0, face_detail=1.0)
    surfaces._TEXEL_FN[man.low.name] = lambda obj: (lambda isl: 0.3)   # no skin shows
    J = b.j
    lead = real.bones_at(man)
    armpit = b.at("armpit")
    hc = man.head_center()
    head_arm = reg.Armour(c, "armour_head", texel=2.8)

    # ---------------------------------------------------------------- mask and balaclava
    for e in man.eyes:
        c.parts = [p for p in c.parts if p[0] is not e]
    env, mask_parts = cracked_mask(c, man, head_arm)
    for e in man.eyes:
        bpy.data.objects.remove(e, do_unlink=True)
    Ob = hc + Vector((0, -0.016, -0.018))

    def bala_keep(p):
        # The neck, and the head only where it can show: round the mask's edge and under the chin
        # (the hood hides the back and the crown, the mask the face).
        L = lead(p)
        if L == "neck":
            return True
        if L != "head":
            return False
        d = (Vector(p) - Ob).normalized()
        la = math.degrees(math.asin(max(-1.0, min(1.0, d.z))))
        lo = abs(math.degrees(math.atan2(d.x, -d.y)))
        if lo > 118 or la > 74:
            return False
        return not (lo < 64 and -42 + 12 * _sm(lo, 0, 80) < la < 46 - 16 * _sm(lo, 30, 80))
    bala = real.layer(c, man, "balaclava", "knit.primary", bala_keep, [], ease=0.0035, smooth=2, texel=0.6, seams="hems")
    c.cover({"head"})
    c.hide_under(bala, 0.02, 1)

    # ---------------------------------------------------------------- gloves, suit
    gloves = real.gloves(c, man, "glove", cuff=0.07)
    glove_guards(c, man, gloves, guard="slate", tab="accent")
    shirt, neckline = combat_shirt(c, man, lead, "primary", texel=1.0)
    tshirt = pmc.tree(shirt.low)
    trousers, belt_z = combat_trousers(c, man, lead, "twill.primary", top=0.16)
    tt = pmc.tree(trousers.low)

    dz = (armpit - 0.198) - 1.03

    def Z(z):
        return z + dz

    # ---------------------------------------------------------------- chest rig (kraft)
    rig_ol = kit.rounded([(-0.104, Z(1.105)), (0.104, Z(1.105)), (0.108, Z(1.205)), (0.07, Z(1.228)), (-0.07, Z(1.228)), (-0.108, Z(1.205))], 0.014)
    pr = reg.Plate([tshirt], rig_ol, -1, 0.006)
    c.rigid(hard(pr.patch("chest_rig", "grey", rig_ol, 0.016, 0.016, nu=14, nv=8, bevel=0.004), "cordura.primary"), "chest")
    for x in (-0.05, 0.0, 0.05):
        M = pr.frame(x, Z(1.14), 0.016)
        objs = [hard(kit.block("mag_pouch", (0, -0.012, 0), (0.042, 0.024, 0.074), "grey", bevel=0.004), "cordura.primary"),
                kit.block("mag", (0, -0.012, 0.045), (0.026, 0.015, 0.03), "black", bevel=0.002),
                kit.block("mag_base", (0, -0.012, 0.061), (0.03, 0.019, 0.006), "black", bevel=0.0015),
                hard(kit.block("pull_tab", (0, -0.025, 0.03), (0.016, 0.004, 0.026), "grey", bevel=0.001), "webbing.accent")]
        for o in objs:
            o.data.transform(M)
            c.rigid(o, "chest")
    # Straps up under the cape and round the sides.
    back_gear = []
    for sx in (1, -1):
        pts = []
        for k in range(7):
            z = Z(1.222) + (armpit + 0.15 - Z(1.222)) * k / 6
            x = sx * (0.07 + 0.012 * k / 6)
            loc, nn = pmc.hit(tshirt, (x, -0.5, z), (0, 1, 0))
            if loc is not None:
                pts.append(loc + Vector((0, -0.006, 0)))
        if len(pts) > 2:
            c.rigid(hard(pmc.sweep("rig_strap", pmc.smooth_path(pts, 2), 0.03, 0.004, "grey", lambda q: (0, -1, 0.3)), "webbing.accent"), "chest")
        side = pmc._ring_side(tshirt, (0, -0.004), Z(1.165), 0.006, sx * 52, sx * 178, n=11)
        rs = pmc.sweep("rig_side", pmc.smooth_path(side, 2), 0.026, 0.004, "grey", pmc.radial((0, -0.004, 0)))
        c.rigid(hard(rs, "webbing.accent"), "chest")
        back_gear.append(rs)

    # ---------------------------------------------------------------- climbing harness (cream)
    harness = []
    hb = pmc.sweep("harness_belt", pmc.ring_pts(tt, (0, -0.005), belt_z, 0.005, n=32), 0.046, 0.008, "grey", pmc.radial((0, -0.005, 0)), closed=True)
    c.add(hard(hb, "webbing.accent"), ["hips", "spine", "upper_leg.L", "upper_leg.R"])
    harness.append(hb)
    loc, _ = pmc.hit(tt, (0, -0.5, belt_z), (0, 1, 0))
    fy = loc.y
    bk = [kit.block("harness_buckle", (0, 0, 0), (0.05, 0.012, 0.038), "gunmetal", bevel=0.003),
          kit.block("buckle_bar", (0, -0.0065, 0), (0.04, 0.004, 0.006), "bright", bevel=0.001)]
    for o in bk:
        o.data.transform(Matrix.Translation(Vector((0, fy - 0.013, belt_z))))
        c.rigid(o, "hips")
    # Belay loop and ring at the front, the leg loops tied into it.
    bz = belt_z - 0.05
    loc2, _ = pmc.hit(tt, (0, -0.5, bz), (0, 1, 0))
    by = (loc2.y if loc2 is not None else fy) - 0.012
    loop_pts = [Vector((0, by - 0.004, belt_z - 0.012)), Vector((0, by - 0.012, bz + 0.012)), Vector((0, by - 0.012, bz - 0.006)),
                Vector((0, by - 0.002, bz - 0.014)), Vector((0, by + 0.004, bz))]
    c.rigid(hard(pmc.sweep("belay_loop", pmc.smooth_path(loop_pts, 3), 0.024, 0.006, "grey", lambda q: (0, -1, 0)), "webbing.accent"), "hips")
    c.rigid(reg.ring("belay_ring", Vector((0, by - 0.012, bz - 0.004)), (1, 0, 0), 0.02, 0.014, 0.007, "gunmetal", segs=16), "hips")
    for s, sx in (("L", 1), ("R", -1)):
        ul = "upper_leg." + s
        ul0, ul1 = J(ul, 0.0), J(ul, 1.0)
        tu = reg.Tube([tt], ul0, ul1, t=(0.0, 0.4), nt=10, nphi=40, reach=0.17)
        ring = tu.ring(0.13, 0.002, n=24)
        c.rigid(hard(reg.strap_ring("leg_loop", ring, ul0.lerp(ul1, 0.13), ul1 - ul0, 0.034, 0.006, "grey"), "webbing.accent"), ul)
        front = tu.P(0.13, -22 * sx, 0.006)
        c.add(hard(pmc.sweep("loop_tie", [front, (front + Vector((0, by - 0.012, bz - 0.004))) / 2 + Vector((0, -0.004, 0.004)),
                                          Vector((-sx * 0.006, by - 0.014, bz - 0.006))], 0.02, 0.004, "grey", lambda q: (0, -1, 0)),
                   "webbing.accent"), ["hips", ul])
    # Two carabiners on the left hip.
    for k, ang in enumerate((62, 74)):
        a = math.radians(ang)
        d = Vector((math.sin(a), -math.cos(a), 0))
        loc, _ = pmc.hit(tt, (0, -0.005, belt_z), d)
        if loc is None:
            continue
        top = loc + d * 0.012 + Vector((0, 0, -0.012))
        cb = reg.ring("carabiner", Vector((0, 0, 0)), (1, 0, 0), 0.022, 0.0165, 0.0055, "bright", segs=16)
        cb.data.transform(Matrix.Scale(0.62, 4, (0, 1, 0)))
        side = d.cross(Vector((0, 0, 1))).normalized()
        M = Matrix((d, side, Vector((0, 0, 1)))).transposed().to_4x4()
        M.translation = top + Vector((0, 0, -0.02))
        cb.data.transform(M)
        c.rigid(cb, "hips")
        c.rigid(kit.cyl("gate", top + Vector((0, 0, -0.005)) + side * 0.008, top + Vector((0, 0, -0.035)) + side * 0.008, 0.0022, "gunmetal",
                        segs=6, bevel=0.0), "hips")

    # ---------------------------------------------------------------- holster, knee caps, jump jets
    for s, sx in (("L", 1), ("R", -1)):
        ul, ll = "upper_leg." + s, "lower_leg." + s
        ul0, ul1 = J(ul, 0.0), J(ul, 1.0)
        ll0, ll1 = J(ll, 0.0), J(ll, 1.0)
        if s == "R":
            # The drop-leg holster (empty: the pistol is in hand) on a platform strapped round the thigh.
            tu = reg.Tube([tt], ul0, ul1, t=(0.1, 0.8), nt=20, nphi=48, reach=0.17, spread=0.03, blur=0.02)
            plat = tu.patch("holster_platform", "black", 0.3, 0.58, 84 * sx, 26, 0.004, 0.006, nu=6, nv=6, corner=2.0, bevel=0.002)
            c.rigid(plat, ul)
            p = tu.P(0.42, 84 * sx, 0.004)
            n = tu.d(84 * sx)
            A = (ul0 - ul1).normalized()
            M = pmc.frame(p + n * 0.003, n, A)
            hol = [kit.block("holster", (0, -0.026, -0.02), (0.05, 0.05, 0.15), "black", bevel=0.008, taper=(0.82, 1.0)),
                   kit.block("holster_mouth", (0, -0.026, 0.058), (0.054, 0.054, 0.012), "black", bevel=0.004),
                   kit.block("holster_hood", (0, -0.046, 0.072), (0.04, 0.012, 0.024), "black", bevel=0.003),
                   kit.block("holster_lock", (0.0, -0.053, 0.02), (0.016, 0.006, 0.022), "gunmetal", bevel=0.0015)]
            for o in hol:
                o.data.transform(M)
                c.rigid(o, ul)
            tu2 = reg.Tube([tt], ul0, ul1, hard=[plat] + hol, t=(0.25, 0.65), nt=10, nphi=36, reach=0.18)
            for tq in (0.34, 0.52):
                c.rigid(reg.strap_ring("holster_strap", tu2.ring(tq, 0.0015, n=22), ul0.lerp(ul1, tq), ul1 - ul0, 0.024, 0.004, "webbing"), ul)
            top = tu.P(0.3, 84 * sx, 0.006)
            hd = Vector((top.x, top.y + 0.005, 0)).normalized()
            hp = []
            for k in range(5):
                zk = belt_z - 0.01 + (top.z + 0.01 - belt_z + 0.01) * k / 4
                lo_, nr_ = pmc.hit(tt, Vector((0, -0.005, zk)) + hd * 0.5, -hd)
                if lo_ is not None:
                    hp.append(lo_ + (nr_ if nr_.dot(hd) > 0 else -nr_) * 0.004)
            if len(hp) >= 2:
                c.add(pmc.sweep("holster_hanger", hp, 0.026, 0.004, "webbing", lambda q, hd=hd: hd), ["hips", ul])
        # Knee caps (the Runner's): a conforming black pad, a clay hard cap with a rib and screws.
        knee = J(ll, 0.04)
        pad_cut = kit.slab("pad_cut", kit.rounded([(knee.x - 0.054, knee.z - 0.076), (knee.x + 0.054, knee.z - 0.076), (knee.x + 0.054, knee.z + 0.066),
                                                   (knee.x - 0.054, knee.z + 0.066)], 0.028), -0.4, knee.y - 0.01)
        pad = kit.plate(trousers.low, pad_cut, "kneepad", "black", offset=0.004, thick=0.014, bevel=0.006)
        c.rigid(pad, ll)
        tp = pmc.tree(pad)
        loc, _ = pmc.hit(tp, knee + Vector((0, -0.4, -0.005)), (0, 1, 0))
        Mk = pmc.frame(loc + Vector((0, 0.001, 0)), (0, -1, 0.1))
        cap_objs = [pmc.panel("knee_cap", kit.rounded([(-0.034, -0.044), (0.034, -0.044), (0.038, 0.028), (0.0, 0.047), (-0.038, 0.028)], 0.012),
                              0.0, 0.007, CLAY, bevel=0.0025)]
        cap_objs += [pmc.panel("knee_rib", pmc.rrect(-0.026, -0.004, 0.026, 0.004, 0.002), -0.007, 0.002, "slate", bevel=0.0)]
        cap_objs += pmc.screws([(-0.024, -0.03), (0.024, -0.03)], -0.007, r=0.0032)
        pmc.put(cap_objs, Mk, 0.06, step=0.01)
        pmc.rigid_all(c, cap_objs, ll)
        kz = knee + Vector((0, 0.0, -0.052))
        r = pmc._radius(tt, kz, (0, 0, 1)) + 0.004
        c.add(pmc.band("pad_strap", kz, (r, r), 0.02, 0.006, "webbing", axis=(0, 0, 1)), [ll])
        # Jump jets on the back of the calves: the crew's slate housing and clay cover, a gunmetal
        # nozzle firing down, on two straps.
        ts = reg.Tube([tt], ll0, ll1, t=(0.1, 0.8), nt=20, nphi=48, reach=0.15, spread=0.03, blur=0.02)
        ph = 150 * sx
        p = ts.P(0.44, ph, 0.0)
        n = ts.d(ph)
        A = (ll0 - ll1).normalized()
        M = pmc.frame(p + n * 0.004, n, A)
        jet = [kit.block("jet_housing", (0, -0.018, 0), (0.05, 0.036, 0.11), "slate", bevel=0.006),
               kit.block("jet_cover", (0, -0.0375, 0.008), (0.042, 0.006, 0.07), "grey", bevel=0.002),
               kit.block("jet_fin", (0, -0.042, -0.005), (0.03, 0.004, 0.004), "black", bevel=0.0),
               kit.block("jet_fin", (0, -0.042, 0.009), (0.03, 0.004, 0.004), "black", bevel=0.0),
               kit.block("jet_fin", (0, -0.042, 0.023), (0.03, 0.004, 0.004), "black", bevel=0.0),
               kit.cyl("jet_lamp", (0.014, -0.036, 0.047), (0.014, -0.0405, 0.047), 0.0035, "glow_amber", segs=8, bevel=0.0)]
        hard(jet[1], CLAY)
        a_ = Vector((0, -0.02, -0.052))
        e_ = a_ + Vector((0, -0.012, -0.035))
        jet += [kit.cyl("jet_nozzle", a_, e_, 0.014, "gunmetal", r1=0.019, segs=14, bevel=0.0012),
                kit.cyl("jet_throat", e_ - (e_ - a_).normalized() * 0.004, e_ + (e_ - a_).normalized() * 0.0005, 0.0165, "black", segs=14, bevel=0.0)]
        for o in jet:
            o.data.transform(M)
            c.rigid(o, ll)
        ts2 = reg.Tube([tt], ll0, ll1, hard=jet[:2], t=(0.25, 0.65), nt=10, nphi=36, reach=0.16)
        for tq in (0.36, 0.52):
            c.rigid(reg.strap_ring("jet_strap", ts2.ring(tq, 0.0015, n=22), ll0.lerp(ll1, tq), ll1 - ll0, 0.02, 0.004, "webbing"), ll)

    # ---------------------------------------------------------------- wrist unit (left forearm)
    fa = "forearm.L"
    fa0, fa1 = J(fa, 0.0), J(fa, 1.0)
    fsleeve = reg.region_tree(shirt.low, {fa})
    tf = reg.Tube([fsleeve], fa0, fa1, front=(0, -1, 0), t=(0.05, 0.95), nt=16, nphi=36, reach=0.12, spread=0.02, blur=0.015)
    p, n = tf.P(0.6, 70, 0.0), tf.d(70)
    A = (fa1 - fa0).normalized()
    M = pmc.frame(p + n * 0.002, n, A)
    unit = [kit.block("wrist_unit", (0, -0.008, 0), (0.044, 0.016, 0.062), "slate", bevel=0.004),
            kit.block("wrist_screen", (0, -0.0165, 0.004), (0.032, 0.002, 0.036), "glow_amber", bevel=0.0),
            kit.block("wrist_bezel", (0, -0.0158, 0.004), (0.038, 0.0016, 0.042), "black", bevel=0.0006),
            kit.block("wrist_key", (0.0, -0.016, -0.023), (0.012, 0.003, 0.006), "gunmetal", bevel=0.001)]
    for o in unit:
        o.data.transform(M)
        c.rigid(o, fa)
    tf2 = reg.Tube([fsleeve], fa0, fa1, hard=unit[:1], t=(0.4, 0.8), nt=8, nphi=36, reach=0.12)
    for tq in (0.5, 0.7):
        c.rigid(reg.strap_ring("wrist_strap", tf2.ring(tq, 0.0015, n=20), fa0.lerp(fa1, tq), fa1 - fa0, 0.016, 0.004, "webbing"), fa)

    # ---------------------------------------------------------------- the cloak: cowl and tails
    proxy = _offset_copy(shirt.low, 0.012, "shirt_proxy")
    hood = cowl(c, man, lead, [proxy], hc, mask_parts)
    bpy.data.objects.remove(proxy, do_unlink=True)
    under = [reg.region_tree(shirt.low, {"chest", "spine", "hips", "shoulder.L", "shoulder.R", "neck"}),
             reg.region_tree(trousers.low, {"hips", "upper_leg.L", "upper_leg.R"}),
             pmc.tree(hb)] + [pmc.tree(o) for o in back_gear]
    # The tails hang from 4 cm up under the cape's hem as the simulation left it: the lowest point of
    # the draped cape at each azimuth round the back.
    hv = np.array([v.co[:] for v in hood.high.data.vertices])
    h_az = np.degrees(np.arctan2(hv[:, 0], hv[:, 1] - 0.01))
    h_back = (hv[:, 1] > 0.0) & (hv[:, 2] < armpit + 0.15)

    def under_hem(a):
        for w in (3.0, 6.0, 10.0):
            sel = h_back & (np.abs(h_az - a) < w)
            if sel.any():
                return float(hv[sel, 2].min()) + 0.04
        return armpit - 0.02
    tails(c, man, "tails", "duck.secondary", "duck.accent", under, under_hem, J("lower_leg.L", 0.0).z + 0.05,
          3.0, 48.0, ease=0.01, collide=[shirt.low, trousers.low])

    # ---------------------------------------------------------------- boots
    real.boots(c, man, "boot", sole_kind="rubber", trim="rubber", top=0.16, lace="webbing", tab="accent")
    head_arm.finish()
    pmc.economise(c)
    return c


SPEC = {"build": build, "faction": "deserters", "budget": (25000, 120000), "loadout": "pistol",
        "colors": {"primary": SLATE, "secondary": KRAFT, "accent": CREAM}}
