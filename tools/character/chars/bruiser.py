"""Bruiser, Scrappers: the settlement's strong arm, a big man in a steam exo-frame he riveted together
himself. One system from the boiler down: a riveted copper boiler on a hammered-steel back plate, its
stack up past the head, copper lines over steel yoke bands to the shoulders; a breastplate lapped from
two sheets with a belly lame under it and a pressure gauge on the chest, leather side straps with brass
buckles; big domed pauldrons, under their rims the shoulder hubs where piston struts run down the
outside of each arm to the elbow hubs and on down the gauntlets, flared forearm guards closed with
straps, brass knuckle bars over his gloved fists; a riveted waist ring carrying the hip hubs, piston
struts down the outside of each leg past knee cops to clamps on the boot tops, riveted shin guards,
steel-capped boots. Over the head a riveted steel cage helm: a barbute-cut shell with a crest, steel
bars across the face, a chin guard and a brow band; behind the bars brass goggles with smoked glass and
a black moulded-leather respirator bound in brass with a brass filter, under it all an oiled-leather
hood. Work clothes under the frame: a twill work shirt and heavy duck trousers. Nothing electric: steel,
brass, copper, leather.

Built on the realistic layer (real.py) like the Mechanic, whose surfaces (hammered steel, duck, oiled
leather, paint) and placement helpers it shares: a real body made heavier (`thicken`, a local version
of the bulk the Anatomy does not apply), gloved fists closed round the grips, shirt and trousers cut
from the body and draped by the cloth simulation, plates laid on envelopes of what they cover (the
Acolyte's Env / Tube / Plate) and baked with their painted marks. Local stand-ins for shared steps:
`thicken` (the Anatomy's bulk), `steel_caps` (real.boots' caps, decimated), `trim_under` (the hood under
the helm). The hood, goggles and respirator are shared with the Trapper.

Tints: primary = shirt, secondary = trousers, accent = the tan leather (pads under the yoke bands,
side straps, gauntlet straps). Steel, brass, copper, hood, respirator and boots are fixed colours.
"""

import math
import os

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

import kit
import real
import surfaces
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS
from chars import mechanic as mech  # the Scrappers' surfaces and palette, rivets, beads, buckles
from chars import contractor as pmc  # ray casts, sweeps
from chars import acolyte as aco  # Env / Tube / Plate envelopes, the armour bake

FAST = bool(os.environ.get("SCRAP_FAST"))  # look-dev: skip the cloth simulation
PLATE = mech.PLATE
ARMS = UPPER_ARMS | FOREARMS
LEGS = THIGHS | SHINS


def sm(x, a, b):
    return float(real._smooth(x, a, b))


# ------------------------------------------------------------------------------------- the body

# Extra flesh per bone region (metres along the normal), blended by the skin weights.
BULK = {"chest": 0.017, "spine": 0.02, "hips": 0.016, "neck": 0.016, "shoulder.L": 0.016, "shoulder.R": 0.016,
        "upper_arm.L": 0.014, "upper_arm.R": 0.014, "forearm.L": 0.009, "forearm.R": 0.009,
        "upper_leg.L": 0.014, "upper_leg.R": 0.014, "lower_leg.L": 0.008, "lower_leg.R": 0.008}


def thicken(man, bulk=BULK, belly=0.022):
    """A heavier man: the body's game mesh and its sculpt pushed out along their normals by the
    bone regions' `bulk` (blended by the skin weights), less on the sides that face each other (inner
    thighs, inner arms and the flanks under them) and more over the belly. A local stand-in for the
    Anatomy's `bulk`, which real.py stores but does not apply. The hands and head keep their shape (the
    fists stay closed on the grips)."""
    lo, hi = man.low, man.high
    b = man.b
    names = {g.index: g.name for g in lo.vertex_groups}
    me = lo.data
    armpit, hip = b.at("armpit"), b.hip_z
    amt = []
    for v in me.vertices:
        tot = sum(g.weight for g in v.groups) or 1.0
        w = {names[g.group]: g.weight / tot for g in v.groups}
        a = sum(x * bulk.get(n, 0.0) for n, x in w.items())
        n, p = v.normal, v.co
        sx = 1 if p.x > 0 else -1
        legs = w.get("upper_leg.L", 0) + w.get("upper_leg.R", 0) + w.get("lower_leg.L", 0) + w.get("lower_leg.R", 0)
        arms = sum(w.get(k, 0) for k in ("upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R"))
        trunk = w.get("chest", 0) + w.get("spine", 0) + w.get("hips", 0)
        inner = max(0.0, -n.x * sx)                      # facing the midline
        outer = max(0.0, n.x * sx)
        f = 1.0 - 0.7 * inner * legs - 0.75 * inner * arms
        # The flanks under the arms face the arms: keep them in, between the hips and the armpits.
        f -= 0.6 * outer * trunk * sm(p.z, hip + 0.05, hip + 0.15) * (1 - sm(p.z, armpit - 0.02, armpit + 0.06))
        a *= max(0.15, f)
        # The belly: forward and low on the trunk.
        a += belly * max(0.0, -n.y) ** 1.5 * math.exp(-((p.z - (hip + 0.17)) / 0.12) ** 2) * (w.get("spine", 0) + w.get("hips", 0))
        amt.append(a)
    # Relax the amounts over the mesh so region borders never step.
    nb = [[] for _ in me.vertices]
    for e in me.edges:
        i, j = e.vertices
        nb[i].append(j)
        nb[j].append(i)
    for _ in range(4):
        amt = [(amt[i] * 2 + sum(amt[j] for j in nb[i]) / max(1, len(nb[i]))) / 3 for i in range(len(amt))]
    kd = KDTree(len(me.vertices))
    for i, v in enumerate(me.vertices):
        kd.insert(v.co, i)
    kd.balance()
    hm = hi.data
    hamt = [amt[kd.find(v.co)[1]] for v in hm.vertices]
    hn = [v.normal.copy() for v in hm.vertices]
    for v, a, n in zip(hm.vertices, hamt, hn):
        v.co += n * a
    ln = [v.normal.copy() for v in me.vertices]
    for v, a, n in zip(me.vertices, amt, ln):
        v.co += n * a
    me.update()
    hm.update()
    man._tree = None


# ------------------------------------------------------------------------------------ helpers

def lateral(a, b_, sx):
    """The outward side (+X for the left) square to the segment a -> b_."""
    ax = (b_ - a).normalized()
    x = Vector((sx, 0, 0))
    return (x - ax * x.dot(ax)).normalized()


def basis(n, up=(0, 0, 1)):
    """(x, n, z): a frame with y = n, z as near `up` as it can be."""
    n = Vector(n).normalized()
    z = Vector(up)
    z = (z - n * z.dot(n))
    if z.length < 1e-6:
        z = Vector((1, 0, 0)) - n * n.x
    z.normalize()
    return n.cross(z).normalized(), n, z


def place(obj, at, x, y, z):
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(at)
    obj.data.transform(m)
    return obj


def tube_plate(tu, name, material, t0, t1, ph_c, half, off, thick, nu=16, nv=10, corner=3.0, bevel=0.0012):
    """aco.Tube.patch with an offset that may vary, off(t, ph): a flared gauntlet, a moulded guard."""
    rows = []
    for i in range(nv + 1):
        v = i / nv
        t = t0 + (t1 - t0) * v
        f = max(0.62, (1 - abs(2 * v - 1) ** corner) ** (1 / corner)) if corner else 1.0
        row = []
        for j in range(nu + 1):
            ph = ph_c + half * f * (2 * j / nu - 1)
            row.append(tu.P(t, ph, off(t, ph) if callable(off) else off))
        rows.append(row)
    return aco.sheet(name, rows, material, thick, tu.c((t0 + t1) / 2), bevel=bevel)


def piston(name, p0, p1, r, out):
    """A piston strut from eye p0 to eye p1: a steel barrel, a bright rod, a brass gland and collar,
    eye lugs facing `out` at both ends (they sit over the hub bolts)."""
    p0, p1 = Vector(p0), Vector(p1)
    u = (p1 - p0).normalized()
    out = Vector(out).normalized()
    a, z = p0 + u * 0.024, p1 - u * 0.024
    m = a.lerp(z, 0.55)
    parts = [kit.cyl(name, a, m, r, "steel", segs=12, bevel=0.0015, bsegs=1),
             kit.cyl(name + "_rod", m, z, r * 0.46, "bright", segs=10, bevel=0, bsegs=1),
             kit.cyl(name + "_gland", m - u * 0.013, m + u * 0.005, r * 1.22, "brass", segs=12, bevel=0.0012, bsegs=1),
             kit.cyl(name + "_collar", a + u * 0.008, a + u * 0.022, r * 1.16, "brass", segs=12, bevel=0.001, bsegs=1),
             kit.cyl(name + "_rod_end", z - u * 0.012, z, r * 0.62, "steel", segs=8, bevel=0.0, bsegs=1)]
    for e, f in ((p0, a), (p1, z)):
        parts.append(kit.cyl(name + "_eye", e - out * 0.0065, e + out * 0.0065, 0.0195, "steel", segs=12, bevel=0.0015, bsegs=1))
        parts.append(kit.cyl(name + "_neck", e + (f - e).normalized() * 0.012, f, r * 0.55, "steel", segs=8, bevel=0, bsegs=1))
    return join(parts, name)


def hub(name, at, out, r=0.032, thick=0.02, bolt="brass"):
    """A pivot hub on a joint axis: a steel disc, a hex bolt, six rivets."""
    at, out = Vector(at), Vector(out).normalized()
    t1 = out.cross(Vector((0, 0, 1)) if abs(out.z) < 0.9 else Vector((1, 0, 0))).normalized()
    t2 = out.cross(t1)
    parts = [kit.cyl(name, at - out * thick * 0.5, at + out * thick * 0.5, r, PLATE, segs=16, bevel=0.002, bsegs=1),
             kit.cyl(name + "_bolt", at + out * thick * 0.5, at + out * (thick * 0.5 + 0.009), r * 0.36, bolt, segs=6, bevel=0.0008, bsegs=1),
             mech.rivets(name + "_rivets", [(at + out * thick * 0.5 + (t1 * math.cos(q) + t2 * math.sin(q)) * r * 0.72, out)
                                           for q in [i * math.pi / 3 for i in range(6)]], r=0.0038, material="steel", segs=6)]
    return join(parts, name)


def join(parts, name):
    """kit.join with one-segment bevels: a joined group bakes its members' bevels, and two segments on
    every small part is triangles nobody sees."""
    for o in parts:
        if o is not None and o.get("segs", 2) > 1:
            o["segs"] = 1
    return kit.join(parts, name)


def baked(o):
    """Bake an object's transform into its mesh (kit.place leaves it on the object)."""
    bpy.context.view_layer.update()
    o.data.transform(o.matrix_world)
    o.matrix_world = Matrix()
    return o


def trim_under(obj, covers, depth, erode=1, only=None):
    """Delete the faces of `obj` that `covers` hide: every vertex whose normal runs into a cover within
    `depth` is under it, less `erode` rings at the edges so no gap opens; faces with all corners under go.
    `only(p)` limits it to some of the vertices (not where the cover's rim is seen under, at the neck)."""
    trees = [pmc.tree(o) for o in covers]
    me = obj.data
    n = len(me.vertices)
    under = [False] * n
    for v in me.vertices:
        p = obj.matrix_world @ v.co
        if only is not None and not only(p):
            continue
        nn = (obj.matrix_world.to_3x3() @ v.normal).normalized()
        for t in trees:
            loc, _, _, _ = t.ray_cast(p + nn * 0.0005, nn, depth)
            if loc is not None:
                under[v.index] = True
                break
    nb = [[] for _ in range(n)]
    for e in me.edges:
        a, b_ = e.vertices
        nb[a].append(b_)
        nb[b_].append(a)
    for _ in range(erode):
        under = [under[i] and all(under[j] for j in nb[i]) for i in range(n)]
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if all(under[v.index] for v in f.verts)], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()


def leather(o):
    return mech.remat(o, "leather.accent")


def steel_caps(c, b, up, material=PLATE):
    """Steel toe caps and heel counters on the boots. real.boots lays its own as a full-density copy
    of the vamp (1.7k triangles a cap); these are the same regions decimated before they get their
    thickness, a local version of that step."""
    for o in [p[0] for p in c.parts if p[0].name.startswith(("toe_cap", "heel_counter"))]:
        c.parts = [p for p in c.parts if p[0] is not o]
        bpy.data.objects.remove(o, do_unlink=True)
    z0 = b.sole
    for sx in (1, -1):
        ys = [v.co.y for v in up.data.vertices if v.co.x * sx > 0.02 and v.co.z < z0 + 0.03]
        toe_y, heel_y = min(ys), max(ys)
        for name, reg in (("toe_cap", lambda p: p.x * sx > 0.0 and p.y < toe_y + 0.072 and z0 + 0.004 < p.z < z0 + 0.062),
                          ("heel_counter", lambda p: p.x * sx > 0.0 and p.y > heel_y - 0.06 and z0 + 0.004 < p.z < z0 + 0.075)):
            o = real.patch(c, up, name, material, reg, lift=0.0016, thick=0.0, subdivide=0, smooth=1)
            kit.decimate(o, 0.42)
            m = o.modifiers.new("thick", "SOLIDIFY")
            m.thickness, m.offset, m.use_rim, m.use_even_offset, m.use_quality_normals = 0.0022, -1.0, True, False, True
            kit.hs._apply(o, m.name)


def strap_round(c, name, tu, t, bone, width, thick, kind="accent", buckle_ph=None, lift=0.0015):
    """A strap pulled taut round a Tube at t, with a brass buckle facing buckle_ph."""
    ring = tu.ring(t, lift, n=22)
    cc = tu.c(t)
    o = aco.strap_ring(name, ring, cc, tu.A, width, thick, kind)
    if kind == "accent":
        leather(o)
    c.rigid(o, bone)
    if buckle_ph is not None:
        k = max(range(len(ring)), key=lambda i: (ring[i] - cc).normalized().dot(tu.d(buckle_ph)))
        q = ring[k]
        nn = (q - cc - tu.A * (q - cc).dot(tu.A)).normalized()
        c.rigid(mech.buckle(name + "_buckle", q + nn * (thick / 2 + 0.001), (ring[(k + 1) % len(ring)] - ring[k - 1]).normalized(), nn, width + 0.004), bone)
    return o


# ---------------------------------------------------------------------------------- the build

def build():
    b = real.Anatomy(height=1.93, width=1.10, body="male", arm_hang=10.0, stance=0.25, sole=0.042)
    c = real.begin("bruiser", b)
    man = real.body(c, stubble=0.0, face_detail=1.0)
    thicken(man)
    J, seg = b.j, kit.seg_dist
    lead = real.bones_at(man)
    hc = man.head_center()
    armpit, crotch = b.at("armpit"), b.at("crotch")
    eyes = [Vector(e.matrix_world.translation) for e in man.eyes]
    E, u = man.face()

    def on_arm(p):
        return lead(p) in ARMS

    # ---------------------------------------------------------------- hands and feet
    gl = real.gloves(c, man, "glove.scrap_cap", cuff=0.055, ease=0.0028)
    boot_top = 0.215
    boots = real.boots(c, man, "leather.scrap_boot", sole_kind="rubber", trim=PLATE, top=boot_top, lace="scrap_lace", tab="leather")
    steel_caps(c, b, boots["upper"])

    # ---------------------------------------------------------------- work shirt
    neck = J("neck", 0.0)
    tuck = b.hip_z + 0.095
    waist = tuck - 0.03
    neckline = (Vector((0, 0, neck.z + 0.024)), Vector((0, -0.4, 1)).normalized())
    cuts = [neckline]
    for s in ("L", "R"):
        e, w = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        cuts.append((e.lerp(w, 0.84), w - e, lambda p, e=e, w=w: on_arm(p) and seg(p, e, w + (w - e) * 0.6) < 0.1))
    cuts.append(((0, 0, waist), (0, 0, -1), lambda p: not on_arm(p)))

    def ease(p):
        if not on_arm(p) and p.z < armpit - 0.06:
            return 0.009 - 0.004 * sm(tuck + 0.03 - p.z, 0.0, 0.03)
        a = min(seg(p, J("upper_arm." + s, 0.3), J("forearm." + s, 1.0)) for s in ("L", "R"))
        return 0.009 + 0.012 * max(0.0, min(1.0, (0.1 - a) / 0.03))

    def pin(p):
        w = 0.0
        if p.z > neck.z - 0.01 and not on_arm(p):
            w = 1.0
        if p.z < tuck and not on_arm(p):
            w = 1.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.84)
            d = (wr - e).normalized()
            if on_arm(p) and seg(p, e, wr) < 0.11 and (p - wr).dot(d) > -0.025:
                w = 1.0
        return w

    def slack(p):
        w = 0.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.84)
            d = wr - e
            L = d.length
            d.normalize()
            t = (p - e).dot(d) / L
            if on_arm(p) and seg(p, e, wr) < 0.11 and t > 0.2:
                w = max(w, min(1.0, (t - 0.2) / 0.5))
        if not on_arm(p) and tuck < p.z < tuck + 0.12:
            w = max(w, 0.6 * (1 - (p.z - tuck) / 0.12))
        return w
    shirt = real.garment(c, man, "shirt", "twill.primary", lambda p: lead(p) in TORSO | ARMS | THIGHS | {"neck"} and p.z > waist - 0.05,
                         cuts, ease=ease, pin=None if FAST else pin, slack=slack, bend=14.0, texel=1.0)
    c.hide_under(shirt.low, 0.05, 2)

    # ---------------------------------------------------------------- duck trousers, bloused over the boots
    top_z = tuck
    hem = b.sole + boot_top - 0.035

    def t_ease(p):
        band = 0.003 * (1 - sm(top_z - p.z, 0.02, 0.07))
        return 0.012 + band + 0.006 * sm(top_z - p.z, 0.04, 0.2) + 0.008 * sm(J("lower_leg.L", 0.0).z - p.z, 0.0, 0.15)

    def t_pin(p):
        return 1.0 if p.z > top_z - 0.045 or p.z < hem + 0.018 else 0.0

    def t_slack(p):
        return sm(hem + 0.13 - p.z, 0.0, 0.1)
    trousers = real.garment(c, man, "trousers", "duck.secondary",
                            lambda p: lead(p) in LEGS | {"hips", "spine"} and hem - 0.03 < p.z < top_z + 0.03,
                            [((0, 0, top_z), (0, 0, 1)), ((0, 0, hem), (0, 0, -1), lambda p: lead(p) in LEGS)],
                            ease=t_ease, pin=None if FAST else t_pin, slack=t_slack, bend=18.0, texel=1.0)
    c.hide_under(trousers.low, 0.06, 2)

    # ---------------------------------------------------------------- head
    arm = aco.Armour(c, "armour", texel=2.0)
    for e in man.eyes:
        c.parts = [p for p in c.parts if p[0] is not e]
        bpy.data.objects.remove(e, do_unlink=True)
    c.cover({"head"})
    surfaces._TEXEL_FN[man.low.name] = lambda obj: (lambda isl: 0.3)  # no skin shows
    head_gear(c, man, lead, neckline, arm, eyes, E, u, hc)

    # ---------------------------------------------------------------- the frame
    torso = aco.region_tree(shirt.low, TORSO | {"neck"})
    tt = pmc.tree(trousers.low)
    pf, pb, yoke = cuirass(c, b, arm, torso, shirt.low)
    back_unit(c, b, arm, pb, yoke)
    ring = waist_ring(c, b, [tt, torso])
    for s, sx in (("L", 1), ("R", -1)):
        arm_frame(c, b, arm, shirt.low, gl, yoke, s, sx)
        fist(c, b, gl, s, sx)
        leg_frame(c, b, arm, trousers.low, boots["upper"], ring, s, sx)
    if os.environ.get("TRIS"):
        print("ARMOUR " + ", ".join(f"{o.name} {kit.tris(o)}" for o, _ in sorted(arm.pieces, key=lambda q: -kit.tris(q[0]))), flush=True)
    arm.finish()
    pmc.economise(c)
    return c


# ------------------------------------------------------------------------------------- head gear

def head_gear(c, man, lead, neckline, arm, eyes, E, u, hc):
    """Hood, goggles, respirator and the cage helm over them (the eyes are gone: their places, the
    face frame E, u and the head centre hc were taken before)."""
    hood, th = hood_layer(c, man, lead, neckline, hc)
    gear = goggles(c, th, eyes, E, u, hc)
    resp, can = respirator(c, man, lead, E, u, hc)
    gear.append(can)
    shell = cage_helm(c, man, hc, [th, pmc.tree(resp)] + [pmc.tree(g) for g in gear], arm)
    # The hood shows only round the face and under the helm's rim: drop what the helm, the respirator
    # and the goggles cover.
    trim_under(hood, [shell, resp] + gear, 0.04, erode=1, only=lambda p: p.z > hc.z - 0.05 or p.y < hc.y - 0.05)


def hood_layer(c, man, lead, neckline, hc, kind="oiled.scrap_hood", smooth=4):
    """The head and neck in near-black oiled leather, face and all, tucked into the collar. Returns
    (the hood, its ray tree)."""
    def in_hood(q):
        # The neck, and the base of it the chest and shoulders lead, down to under the collar.
        L = lead(q)
        return (L in ("head", "neck") or (L in TORSO and Vector(q).z > neckline[0].z - 0.07)) and (Vector(q) - neckline[0]).dot(neckline[1]) > -0.03

    def h_ease(q):
        return 0.0055 + 0.004 * sm(q.z, hc.z - 0.11, hc.z - 0.03)
    hood = real.layer(c, man, "hood", kind, in_hood, [], ease=h_ease, smooth=smooth, texel=0.8, seams="hems")
    hood["unwrap"] = True
    c.hide_under(hood, 0.02, 1)
    return hood, pmc.tree(hood)


def goggles(c, th, eyes, E, u, hc, strap=True):
    """Brass goggles on the hood (ray tree th): cups on leather gaskets, smoked glass, three screws, a
    bridge over the nose and a tan strap round the back at eye level. Returns the cups and the bridge."""
    def F(x, y, z):
        return E + Vector((x, y, z)) * u
    gear = []
    rims = {}
    for e, sx in zip(eyes, (1, -1) if eyes[0].x > 0 else (-1, 1)):
        d = Vector((sx * 0.2, -1.0, 0.03)).normalized()
        loc, _ = pmc.hit(th, e + d * 0.15, -d)
        base = loc if loc is not None else e + d * 0.018
        x, _, z = basis(d)
        parts = [kit.ring("goggle_gasket", base + d * 0.003, d, 0.0262, 0.0145, 0.009, "scrap_cap", segs=14),
                 kit.cyl("goggle_cup", base + d * 0.004, base + d * 0.021, 0.0218, "brass", r1=0.0206, segs=14, bevel=0.0012, bsegs=1),
                 kit.cyl("goggle_lens", base + d * 0.0195, base + d * 0.0225, 0.0172, "scrap_lens", segs=14, bevel=0),
                 kit.ring("goggle_bezel", base + d * 0.0222, d, 0.0222, 0.0166, 0.0036, "brass", segs=14)]
        spots = [(base + d * 0.024 + (x * math.cos(a) + z * math.sin(a)) * 0.0194, d) for a in [math.radians(90 + 120 * k) for k in range(3)]]
        parts.append(mech.rivets("goggle_screws", spots, r=0.0017, material="steel", segs=6))
        g = join(parts, "goggles")
        c.rigid(g, "head")
        gear.append(g)
        rims[sx] = (base, d, x)
    a = rims[1][0] + rims[1][2] * -0.021 + rims[1][1] * 0.012
    b_ = rims[-1][0] + rims[-1][2] * 0.021 + rims[-1][1] * 0.012
    loc, _ = pmc.hit(th, F(0, -0.3, 0.0), (0, 1, 0))
    mid = (loc if loc is not None else (a + b_) / 2) + Vector((0, -0.006, 0.002))
    bridge = mech.tube_path("goggle_bridge", pmc.smooth_path([a, mid, b_], 4), 0.0026, "brass", segs=6, closed=False)
    c.rigid(bridge, "head")
    gear.append(bridge)
    if strap:
        # From under each cup's outer rim round the back of the hood (no loose end beside the cup).
        ez = (eyes[0].z + eyes[1].z) / 2 + 0.004
        o = Vector((hc.x, hc.y, ez))
        a0, a1 = (math.degrees(math.atan2(rims[sx][0].x - o.x, -(rims[sx][0].y - o.y))) for sx in (1, -1))
        a0, a1 = a0 + 9.0, 360.0 + a1 - 9.0
        pts = []
        for k in range(37):
            ang = math.radians(a0 + (a1 - a0) * k / 36)
            dd = Vector((math.sin(ang), -math.cos(ang), 0))
            loc, _ = pmc.hit(th, o + dd * 0.3, -dd)
            if loc is not None:
                pts.append(loc + dd * 0.0022)
        c.rigid(leather(pmc.sweep("goggle_strap", pts, 0.022, 0.0028, "accent", pmc.radial(o), bevel=0.0)), "head")
    return gear


def mould(obj, O, K=0.14, reach=0.5, edge=(0.006, 0.026), passes=14):
    """Lay a face layer out over its own rolling envelope seen from `O` inside the head, so leather
    moulded over the face bridges the nose and the lips instead of showing them: each vertex rises to
    the highest of r_j - K * angle^2 over its neighbours within `reach` radians, the lift smoothed over
    the mesh and faded to nothing at the layer's edges (which stay down on the face)."""
    me = obj.data
    vs = me.vertices
    n = len(vs)
    O = Vector(O)
    R = [(v.co - O).length for v in vs]
    D = [(v.co - O) / max(R[i], 1e-9) for i, v in enumerate(vs)]
    kd = KDTree(n)
    for i, d in enumerate(D):
        kd.insert(d, i)
    kd.balance()
    chord = 2 * math.sin(reach / 2)
    lift = [0.0] * n
    for i in range(n):
        best = R[i]
        for _, j, ch in kd.find_range(D[i], chord):
            a = 2 * math.asin(min(1.0, ch / 2))
            best = max(best, R[j] - K * a * a)
        lift[i] = best - R[i]
    nb = [[] for _ in range(n)]
    for e in me.edges:
        a, b_ = e.vertices
        nb[a].append(b_)
        nb[b_].append(a)
    for _ in range(passes):
        lift = [(lift[i] + sum(lift[j] for j in nb[i])) / (1 + len(nb[i])) if nb[i] else lift[i] for i in range(n)]
    rim = {i for lp in real.boundary_loops(obj) for i in lp}
    kr = KDTree(max(1, len(rim)))
    for i in rim:
        kr.insert(vs[i].co, i)
    kr.balance()
    for i, v in enumerate(vs):
        de = kr.find(v.co)[2] if rim else 1.0
        v.co = O + D[i] * (R[i] + lift[i] * sm(de, *edge))
    me.update()


def respirator(c, man, lead, E, u, hc, twin=False):
    """A respirator over the face from the nose to under the chin: oiled black leather moulded out into
    a snout over the mouth (the face under it is gone, nose and lips with it), its edge bound in brass.
    One brass filter canister over the mouth with exhale valves at the cheeks, or with `twin` a
    canister angled out on each cheek and a valve in front. Returns (the mask, the hardware)."""
    def F(x, y, z):
        return E + Vector((x, y, z)) * u

    def in_resp(p):
        d = (Vector(p) - E) / u
        return lead(p) in ("head", "neck") and -0.17 < d.z < 0.01 and abs(d.x) < 0.08 and d.y < 0.05
    cuts = [(F(0, 0, -0.004), Vector((0.62, 0.12, 1.0)).normalized()), (F(0, 0, -0.004), Vector((-0.62, 0.12, 1.0)).normalized()),
            (F(0.062, 0, 0), Vector((1, 0.4, 0)).normalized()), (F(-0.062, 0, 0), Vector((-1, 0.4, 0)).normalized()),
            (F(0, 0.02, -0.122), Vector((0, 0.55, -1.0)).normalized()), (F(0, 0.045, 0), Vector((0, 1, 0)))]
    resp = real.layer(c, man, "respirator", "oiled.scrap_hood", in_resp, cuts, ease=0.0125, smooth=12, texel=1.1, seams=False)
    mouth = F(0, 0, -0.07)
    for v in resp.data.vertices:
        d = (v.co - mouth) / u
        w = math.exp(-(d.x / 0.05) ** 2 - (d.z / 0.045) ** 2)
        v.co += Vector((0, -0.016, -0.003)) * w * u
    mould(resp, F(0, 0.075, -0.07))
    kit.decimate(resp, 0.4)
    loop = max(real.boundary_loops(resp), key=len)
    me = resp.data
    edge = [me.vertices[i].co.copy() for i in loop][::2]
    for _ in range(2):
        edge = [(edge[i - 1] + edge[i] * 2 + edge[(i + 1) % len(edge)]) / 4 for i in range(len(edge))]
    if len(edge) > 8:
        c.rigid(mech.bead("respirator_rim", edge, 0.0028, material="brass", closed=True, segs=5,
                          normal=lambda q: Vector(q) - hc), "head")
    real.seam_attrs(resp, uv_seams=False)
    sm_ = resp.modifiers.new("thick", "SOLIDIFY")
    # Plain offsets: even ones blow up on the decimated mask's slivers (a vertex shot a metre off).
    sm_.thickness, sm_.offset, sm_.use_rim, sm_.use_even_offset, sm_.use_quality_normals = 0.004, -1.0, True, False, True
    kit.hs._apply(resp, sm_.name)
    resp["unwrap"] = True
    tr = pmc.tree(resp)

    def canister(at, n, r=0.02, depth=0.025):
        x, _, z = basis(n)
        out = [kit.cyl("filter", at - n * 0.004, at + n * (depth - 0.004), r, "brass", segs=16, bevel=0.0015, bsegs=1),
               kit.ring("filter_band", at + n * 0.008, n, r + 0.0012, r - 0.0015, 0.005, "scrap_copper", segs=16),
               kit.cyl("filter_cap", at + n * (depth - 0.004), at + n * (depth + 0.002), r * 0.84, PLATE, r1=r * 0.72, segs=16, bevel=0.001, bsegs=1)]
        for k in range(7):
            q = at + n * (depth + 0.0015) + ((x * math.cos(2 * math.pi * k / 6) + z * math.sin(2 * math.pi * k / 6)) * r * 0.42 if k < 6 else Vector())
            out.append(kit.cyl("filter_hole", q - n * 0.001, q + n * 0.0008, 0.0021, "black", segs=6, bevel=0))
        return out

    def valve(at, n):
        return [kit.cyl("valve", at - n * 0.002, at + n * 0.007, 0.0105, "brass", segs=14, bevel=0.0012),
                kit.cyl("valve_flap", at + n * 0.007, at + n * 0.009, 0.0075, "black", segs=12, bevel=0)]
    can = []
    if not twin:
        loc, nor = pmc.hit(tr, F(0, -0.3, -0.074), (0, 1, 0))
        if loc is None:
            loc, nor = F(0, -0.03, -0.074), Vector((0, -1, 0))
        can += canister(loc, (Vector((0, -1, 0)) * 0.8 + nor * 0.2 + Vector((0, 0, -0.3))).normalized())
        for sx in (1, -1):
            loc2, nor2 = pmc.hit(tr, F(sx * 0.05, -0.3, -0.064), (0, 1, 0))
            if loc2 is not None:
                can += valve(loc2, (nor2 + Vector((sx * 0.5, 0, 0))).normalized())
    else:
        for sx in (1, -1):
            loc2, nor2 = pmc.hit(tr, F(sx * 0.042, -0.3, -0.08), (0, 1, 0))
            if loc2 is not None:
                n2 = (nor2 + Vector((sx * 0.9, -0.2, -0.45))).normalized()
                can += canister(loc2, n2, r=0.019, depth=0.034)
                can.append(kit.ring("filter_collar", loc2 + n2 * 0.001, n2, 0.0225, 0.017, 0.006, PLATE, segs=16))
        loc, nor = pmc.hit(tr, F(0, -0.3, -0.07), (0, 1, 0))
        if loc is not None:
            can += valve(loc, (nor + Vector((0, -0.4, -0.2))).normalized())
    hw = join(can, "filter")
    c.rigid(hw, "head")
    return resp, hw


def cage_helm(c, man, hc, trees, arm):
    """A riveted steel cage helm: a barbute-cut shell (crown, cheek guards down to the jaw, the nape)
    with a crest, a brow band, steel bars across the face opening, a chin guard under the respirator,
    the rims rolled, punched air holes and pivot bosses on the cheeks, the Scrappers' cog painted on the
    left. Laid on the envelope of the hood and of everything on the face, so nothing pokes through."""
    dom = kit.dominant(man.low)
    me = man.low.data
    co = [v.co.copy() for v in me.vertices]
    head = BVHTree.FromPolygons(co, [p.vertices[:] for p in me.polygons if sum(dom[i] in ("head", "neck") for i in p.vertices) * 2 > len(p.vertices)])
    env = aco.Env([head] + trees, hc + Vector((0, -0.012, -0.02)), reach=0.26, lat=(-82.0, 90.0), dlat=4.0, dlon=5.0,
                  spread=12.0, blur=8.0, floor=0.004)
    OFF, TH = 0.0105, 0.0032
    BROW, JAW, NAPE = 21.0, -58.0, -33.0

    def rim(lo):
        a = abs(lo)
        return BROW + (JAW - BROW) * sm(a, 38.0, 64.0) + (NAPE - JAW) * sm(a, 118.0, 165.0)
    shell = env.patch("cage_helm", PLATE, -180.0, 180.0, rim, lambda lo: 86.0, OFF, TH, nu=48, nv=10, closed=True, pole=True, bevel=0.0012)
    tree_shell = pmc.tree(shell)
    arm.add(shell, "head")
    c.rigid(mech.bead("helm_rim", [env.P(rim(lo), lo, OFF - 0.0014) for lo in range(-180, 180, 5)], 0.0029, segs=5,
                      normal=lambda q: Vector(q) - env.O), "head")
    # Crest: a raised strip from the brow over the crown to the nape.
    for lo0, la0, la1 in ((0.0, BROW + 3.0, 88.0), (180.0, NAPE + 6.0, 88.0)):
        crest = env.patch("helm_crest", PLATE, lo0 - 4.0, lo0 + 4.0, lambda lo, a=la0: a, lambda lo, a=la1: a, OFF + 0.004, 0.004, nu=2, nv=10, bevel=0.0015)
        arm.add(crest, "head")
    # Brow band across the front, anchoring the bars.
    band = env.patch("brow_band", PLATE, -62.0, 62.0, lambda lo: BROW - 4.0, lambda lo: BROW + 5.0,
                     OFF + 0.0032, 0.0035, nu=18, nv=2, bevel=0.0012)
    arm.add(band, "head")
    # Chin guard under the respirator, its ends lapped over the cheek guards.
    CH0, CH1 = -76.0, -46.0

    def chin_top(lo):
        return CH1 + 8.0 * sm(abs(lo), 18.0, 60.0)
    chin = env.patch("chin_guard", PLATE, -70.0, 70.0, lambda lo: CH0 + 14.0 * sm(abs(lo), 30.0, 70.0), chin_top, OFF + 0.004, 0.0035,
                     nu=20, nv=4, bevel=0.0012)
    arm.add(chin, "head")
    c.rigid(mech.bead("chin_rim", [env.P(chin_top(lo), lo, OFF + 0.0026) for lo in range(-68, 69, 4)], 0.0026, closed=False,
                      normal=lambda q: Vector(q) - env.O), "head")
    # The bars: five down the face from the brow band to the chin guard, one across under the goggles.
    bars = []
    for lo in (-28.0, -14.0, 0.0, 14.0, 28.0):
        top = BROW - 1.0
        bot = chin_top(lo) + 1.0
        pts = [env.P(top + (bot - top) * k / 11, lo, OFF + 0.0055) for k in range(12)]
        bars.append(mech.bead("cage_bar", pts, 0.0042, material="steel", closed=False, segs=6, normal=lambda q: Vector(q) - env.O))
    pts = [env.P(-14.0, lo, OFF + 0.0098) for lo in range(-50, 51, 5)]
    bars.append(mech.bead("cage_bar", pts, 0.0038, material="steel", closed=False, segs=6, normal=lambda q: Vector(q) - env.O))
    c.rigid(join(bars, "cage_bars"), "head")

    # Rivets: round the rim, along the crest, the brow band (one at each bar), the chin guard's ends.
    spots = []
    for lo in range(-180, 180, 12):
        if abs(lo) > 44:
            la = rim(lo) + 5.0
            spots.append((env.P(la, lo, OFF), env.normal(la, lo, OFF)))
    for la in range(int(BROW) + 10, 86, 9):
        for lo in (0.0, 180.0):
            spots.append((env.P(la, lo, OFF + 0.004), env.normal(la, lo, OFF + 0.004)))
    for lo in (-56.0, -42.0, -28.0, -14.0, 0.0, 14.0, 28.0, 42.0, 56.0):
        spots.append((env.P(BROW + 0.5, lo, OFF + 0.0067), env.normal(BROW + 0.5, lo, OFF + 0.0067)))
    for lo in (-64.0, -52.0, 52.0, 64.0):
        for la in (CH0 + 10.0, chin_top(lo) - 5.0):
            spots.append((env.P(la, lo, OFF + 0.0075), env.normal(la, lo, OFF + 0.0075)))
    c.rigid(mech.rivets("helm_rivets", spots, r=0.0034, material=PLATE, segs=6), "head")
    # Punched air holes on each cheek guard and a pivot boss.
    holes = []
    for sx in (1, -1):
        for la in (-30.0, -38.0, -46.0):
            for k in range(3):
                lo = sx * (72.0 + 7.0 * k + (3.5 if la == -38.0 else 0.0))
                p, n = env.P(la, lo, OFF + 0.0002), env.normal(la, lo, OFF)
                holes.append(kit.cyl("air_hole", p - n * 0.001, p + n * 0.0006, 0.0028, "black", segs=6, bevel=0))
        p, n = env.P(-6.0, sx * 92.0, OFF), env.normal(-6.0, sx * 92.0, OFF)
        holes += [kit.cyl("helm_boss", p - n * 0.001, p + n * 0.006, 0.014, "brass", segs=12, bevel=0.0012),
                  kit.cyl("helm_boss_nut", p + n * 0.006, p + n * 0.0105, 0.008, PLATE, segs=6, bevel=0.0006)]
    c.rigid(join(holes, "helm_bits"), "head")
    # The cog, hand-painted on the left cheek guard.
    M = pmc.frame(env.P(-6.0, 88.0, OFF), env.normal(-6.0, 88.0, OFF), (0, 0, 1))
    arm.detail(mech.decal_on("helm_cog", tree_shell, mech.cog(0.0, 0.035, 0.019, teeth=8, depth=0.28), (0.0, 0.035, 0.007), M, "paint.scrap_paint"))
    return shell


# ------------------------------------------------------------------------------------- torso frame

def cuirass(c, b, arm, torso, shirt):
    """Breastplate (two sheets lapped across the chest, a keel strap down the middle, a gauge on the
    left), a belly lame under it, a back plate, steel yoke bands on leather pads over the shoulders and
    leather side straps with brass buckles. Returns (front Plate, back Plate, the yoke parts)."""
    yc = b.j("spine", 0.0).y
    hip, armpit = b.hip_z, b.at("armpit")
    zt, zb = armpit + 0.118, hip + 0.19
    OFF, TH = 0.0046, 0.003
    out_f = kit.rounded([(-0.152, zb), (0.152, zb), (0.181, zb + 0.15), (0.176, zt - 0.06), (0.108, zt), (-0.108, zt), (-0.176, zt - 0.06),
                         (-0.181, zb + 0.15)], 0.022)
    pf = aco.Plate([torso], out_f, -1, 0.008)
    arm.add(pf.patch("breastplate", PLATE, out_f, OFF, TH, nu=18, nv=14, bevel=0.0012), "chest")
    # The upper sheet lapped over the lower one, a keel strap down the middle.
    zl = zb + 0.17
    span = pf.span(out_f, zl)
    lap = [(span[0] + 0.004, zl), (span[1] - 0.004, zl), (span[1] - 0.004, zl + 0.014), (span[0] + 0.004, zl + 0.014)]
    arm.add(pf.patch("plate_lap", PLATE, kit.rounded(lap, 0.004), OFF + 0.0022, 0.0022, nu=14, nv=1, bevel=0.0008), "chest")
    keel = kit.rounded([(-0.019, zb + 0.008), (0.019, zb + 0.008), (0.019, zt - 0.008), (-0.019, zt - 0.008)], 0.007)
    arm.add(pf.patch("plate_keel", PLATE, keel, OFF + 0.0034, 0.0028, nu=2, nv=10, bevel=0.0009), "chest")
    c.rigid(mech.bead("plate_rim", [pf.P(x, z, OFF - 0.0014) for x, z in mech.spaced(out_f, 0.017)], 0.0029, segs=5,
                      normal=lambda q: pf.normal(q.x, q.z)), "chest")
    spots = [(pf.P(x, z, OFF), pf.normal(x, z)) for x, z in mech.spaced(pmc.grow(out_f, -0.014), 0.044) if abs(x) > 0.035]
    spots += [(pf.P(sx * 0.0095, z, OFF + 0.0034), pf.normal(0.0, z)) for sx in (1, -1) for z in [zb + 0.024 + (zt - zb - 0.048) * k / 7 for k in range(8)]]
    spots += [(pf.P(x, zl + 0.007, OFF + 0.0022), pf.normal(x, zl)) for x in [span[0] + 0.02 + (span[1] - span[0] - 0.04) * k / 6 for k in range(7)] if abs(x) > 0.035]
    c.rigid(mech.rivets("plate_rivets", spots, r=0.0036, material=PLATE, segs=6), "chest")
    # The pressure gauge on the left of the chest, on a brass flange.
    gx, gz = 0.098, zt - 0.075
    gp, gn = pf.P(gx, gz, OFF + 0.002), pf.normal(gx, gz)
    g = mech.gauge(gp + gn * 0.004, gn, (0, 0, 1), r=0.025, depth=0.013, needle=30)
    g.append(kit.cyl("gauge_flange", gp - gn * 0.002, gp + gn * 0.005, 0.031, "brass", segs=16, bevel=0.0012))
    c.rigid(join(g, "chest_gauge"), "chest")

    # The belly lame under the breastplate's hem.
    zl0, zl1 = hip + 0.105, zb + 0.022
    out_l = kit.rounded([(-0.158, zl0), (0.158, zl0), (0.166, zl1), (-0.166, zl1)], 0.014)
    pl = aco.Plate([torso], out_l, -1, 0.008)
    arm.add(pl.patch("belly_lame", PLATE, out_l, OFF, TH, nu=16, nv=4, bevel=0.0012), "spine")
    c.rigid(mech.bead("lame_rim", [pl.P(-0.158 + 0.316 * k / 26, zl0 + 0.002, OFF - 0.0014) for k in range(27)], 0.0026, closed=False,
                      normal=lambda q: pl.normal(q.x, q.z)), "spine")
    c.rigid(mech.rivets("lame_rivets", [(pl.P(sx * x, (zl0 + zl1) / 2 - 0.006, OFF), pl.normal(sx * x, zl0)) for sx in (1, -1) for x in (0.05, 0.1, 0.145)],
                        r=0.0036, material=PLATE, segs=6), "spine")

    # The back plate (the boiler rides on it).
    zbt, zbb = armpit + 0.13, hip + 0.2
    out_b = kit.rounded([(-0.158, zbb), (0.158, zbb), (0.176, zbb + 0.15), (0.14, zbt), (-0.14, zbt), (-0.176, zbb + 0.15)], 0.025)
    pb = aco.Plate([torso], out_b, 1, 0.008)
    arm.add(pb.patch("back_plate", PLATE, out_b, OFF, TH, nu=16, nv=12, bevel=0.0012), "chest")
    c.rigid(mech.bead("back_rim", [pb.P(x, z, OFF - 0.0014) for x, z in mech.spaced(out_b, 0.018)], 0.0029, segs=5, normal=lambda q: pb.normal(q.x, q.z)), "chest")
    spots = [(pb.P(x, z, OFF), pb.normal(x, z)) for x, z in mech.spaced(pmc.grow(out_b, -0.014), 0.046)]
    c.rigid(mech.rivets("back_rivets", spots, r=0.0036, material=PLATE, segs=6), "chest")

    # Yoke: steel bands on tan leather pads over the shoulders, from the breastplate's top to the back
    # plate's, riveted at both ends.
    yoke = {"parts": [], "top": {}}
    anchors = []
    for sx in (1, -1):
        pts = [pf.P(sx * 0.082, zt - 0.03, OFF + 0.004), pf.P(sx * 0.086, zt - 0.004, OFF + 0.006)]
        for y in (-0.075, -0.05, -0.025, 0.0, 0.025, 0.05, 0.075):
            loc, _ = mech.outermost([torso], (sx * 0.106, y, armpit), (0, 0, 1), 0.6)
            if loc is not None and loc.z > armpit + 0.1:
                pts.append(loc + Vector((0, 0, 0.009)))
        pts += [pb.P(sx * 0.09, zbt - 0.004, OFF + 0.006), pb.P(sx * 0.086, zbt - 0.03, OFF + 0.004)]
        path = pmc.smooth_path(pts, 3)
        nrm = pmc.radial((sx * 0.106, 0, armpit + 0.04), (1, 0, 0))
        pad = leather(pmc.sweep("yoke_pad", [q - nrm(q).normalized() * 0.003 for q in path], 0.066, 0.007, "accent", nrm, bevel=0.0))
        band = pmc.sweep("yoke_band", [q + nrm(q).normalized() * 0.003 for q in path], 0.05, 0.005, PLATE, nrm, bevel=0.0012)
        c.rigid(pad, "chest")
        c.rigid(band, "chest")
        yoke["parts"] += [pad, band]
        for q in (path[1], path[-2]):
            nn = nrm(q).normalized()
            tan = (path[2] - path[0]).normalized() if q is path[1] else (path[-1] - path[-3]).normalized()
            side = nn.cross(tan).normalized()
            anchors += [(q + nn * 0.0058 + side * dx, nn) for dx in (-0.014, 0.014)]
        k = min(range(len(path)), key=lambda i: -path[i].z)
        nn = nrm(path[k]).normalized()
        yoke["top"][sx] = (path[k] + nn * 0.0055, nn)
    c.rigid(mech.rivets("yoke_rivets", anchors, r=0.0042, material="brass", segs=6), "chest")
    # Side straps, front plate to back plate under each arm.
    for sx in (1, -1):
        for z in (zb + 0.06, zb + 0.16):
            ring = []
            for i in range(13):
                a = math.radians(sx * (62 + 56 * i / 12))
                d = Vector((math.sin(a), -math.cos(a), 0))
                loc, _ = mech.outermost([torso], (0, yc, z), d, 0.5)
                if loc is not None:
                    ring.append(loc + d * 0.0045)
            if len(ring) < 4:
                continue
            ring = [pf.P(sx * 0.168, z, OFF - 0.002)] + ring + [pb.P(sx * 0.165, z, OFF - 0.002)]
            st = leather(pmc.sweep("side_strap", pmc.smooth_path(ring, 2), 0.028, 0.0035, "accent", pmc.radial((0, yc, 0)), bevel=0.0))
            c.rigid(st, "chest")
            q = ring[len(ring) // 2]
            tan = (ring[len(ring) // 2 + 1] - ring[len(ring) // 2 - 1]).normalized()
            nn = Vector((q.x, q.y - yc, 0)).normalized()
            c.rigid(mech.buckle("side_buckle", q + nn * 0.003, tan, nn, 0.03), "chest")
    return pf, pb, yoke


def back_unit(c, b, arm, pb, yoke):
    """The boiler on the back plate: a riveted copper drum in brass bands with a dome, a safety valve
    and a whistle, a gauge, a brass name plate; a firebox under it with a vented door; the stack up the
    left past the head; copper steam lines from the dome over the shoulders."""
    armpit = b.at("armpit")
    zc = armpit + 0.0
    M = pb.frame(0.0, zc, 0.0046)
    R = 0.078
    yb = -(R + 0.01)                 # the drum's axis, out from the plate (its saddles bear on it)
    z0, z1 = -0.13, 0.12             # its ends (local, from the plate's centre)

    def at(z, r=0.0, ang=0.0):
        a = math.radians(ang)
        return Vector((math.sin(a) * (R + r), yb - math.cos(a) * (R + r), z))
    parts = [kit.cyl("boiler", at(z0), at(z1), R, "scrap_copper", segs=20, bevel=0.002, bsegs=1),
             kit.cyl("boiler_dome", at(z1), at(z1 + 0.036), R, "scrap_copper", r1=R * 0.55, segs=20, bevel=0.0015, bsegs=1),
             kit.cyl("boiler_crown", at(z1 + 0.036), at(z1 + 0.046), R * 0.55, "brass", r1=R * 0.42, segs=14, bevel=0.001, bsegs=1),
             kit.cyl("boiler_sump", at(z0 - 0.028), at(z0), R * 0.72, "scrap_copper", r1=R, segs=20, bevel=0.0, bsegs=1)]
    spots = []
    for zz in (z0 + 0.02, z0 + (z1 - z0) * 0.55, z1 - 0.018):
        parts.append(kit.cyl("boiler_band", at(zz - 0.009), at(zz + 0.009), R + 0.004, "brass", segs=20, bevel=0.001, bsegs=1))
        for i in range(-4, 5):
            a = i * 22.0
            spots.append((at(zz, 0.004, a), Vector((math.sin(math.radians(a)), -math.cos(math.radians(a)), 0))))
    for i in range(1, 6):
        zz = z0 + (z1 - z0) * i / 6
        spots.append((at(zz, 0.0, 34.0), Vector((math.sin(math.radians(34)), -math.cos(math.radians(34)), 0))))
    parts.append(mech.rivets("boiler_rivets", spots, r=0.0038, material="brass", segs=6))
    # Saddles holding the drum to the plate.
    for zz in (z0 + 0.06, z1 - 0.06):
        parts.append(kit.cyl("saddle", at(zz - 0.011), at(zz + 0.011), R + 0.009, PLATE, segs=16, bevel=0.001, bsegs=1))
        parts.append(kit.block("saddle_foot", (0, -0.008, zz), (0.11, 0.016, 0.026), PLATE, bevel=0.002))
    # Gauge, safety valve, whistle.
    gd = Vector((math.sin(math.radians(-48)), -math.cos(math.radians(-48)), 0.15)).normalized()
    ga = at(z1 - 0.075, 0.004, -48)
    parts += mech.gauge(ga + gd * 0.012, gd, (0, 0, 1), r=0.027, depth=0.014, needle=60)
    parts.append(kit.cyl("gauge_stem", ga - gd * 0.004, ga + gd * 0.014, 0.007, "brass", segs=8, bevel=0.0008))
    vt = at(z1 + 0.046) + Vector((0.022, 0.012, 0))
    parts += [kit.cyl("valve", vt, vt + Vector((0, 0, 0.042)), 0.011, "brass", segs=12, bevel=0.001),
              kit.block("valve_lever", vt + Vector((0.036, 0, 0.044)), (0.082, 0.008, 0.006), "steel", bevel=0.001),
              kit.cyl("valve_weight", vt + Vector((0.072, -0.012, 0.044)), vt + Vector((0.072, 0.012, 0.044)), 0.012, "steel", segs=12, bevel=0.0015),
              kit.cyl("whistle", at(z1 + 0.046) + Vector((-0.03, -0.004, 0)), at(z1 + 0.046) + Vector((-0.03, -0.004, 0.055)), 0.009, "brass", r1=0.015, segs=12, bevel=0.001)]
    # Name plate.
    npos = at(z0 + (z1 - z0) * 0.78, 0.0055)
    parts += [kit.block("name_plate", npos, (0.078, 0.004, 0.036), "brass", bevel=0.001),
              baked(kit.label_front("No 3", npos + Vector((0, -0.002, 0)), 0.022, "black", depth=0.0012)),
              mech.rivets("name_rivets", [(npos + Vector((x, -0.002, z)), Vector((0, -1, 0))) for x in (-0.032, 0.032) for z in (-0.012, 0.012)],
                          r=0.0024, material="steel", segs=6)]
    # Firebox and door.
    ft = z0 - 0.028
    fb = kit.block("firebox", (0, (yb - 0.046) / 2, ft - 0.048), (0.136, 0.046 - yb, 0.096), PLATE, bevel=0.004)  # back on the plate
    door = kit.block("firebox_door", (0, yb - 0.048, ft - 0.048), (0.092, 0.008, 0.064), "black", bevel=0.002)
    kit.cut(door, *[kit.block("vent", (x, yb - 0.053, ft - 0.048), (0.006, 0.02, 0.04), "steel", bevel=0) for x in (-0.03, -0.015, 0.0, 0.015, 0.03)])
    parts += [fb, door,
              kit.cyl("door_hinge", (-0.049, yb - 0.053, ft - 0.08), (-0.049, yb - 0.053, ft - 0.016), 0.005, "brass", segs=8, bevel=0),
              kit.block("door_latch", (0.041, yb - 0.056, ft - 0.048), (0.008, 0.008, 0.022), "brass", bevel=0.001),
              mech.rivets("firebox_rivets", [(Vector((x, yb - 0.046, z)), Vector((0, -1, 0))) for x in (-0.06, 0.06) for z in (ft - 0.088, ft - 0.048, ft - 0.008)],
                          r=0.0034, material=PLATE, segs=6)]
    # The stack, up the left side (local -X is the body's left from behind: the plate frame is mirrored).
    s0 = Vector((-(R + 0.026), yb + 0.012, ft - 0.03))
    top = s0 + Vector((-0.004, 0.004, 0.6))
    parts += [kit.cyl("stack", s0, top, 0.016, PLATE, segs=12, bevel=0.0012),
              kit.cyl("stack_cap", top, top + Vector((0, 0, 0.04)), 0.017, PLATE, r1=0.029, segs=12, bevel=0.0012),
              kit.cyl("stack_top", top + Vector((0, 0, 0.04)), top + Vector((0, 0, 0.048)), 0.029, PLATE, segs=12, bevel=0.001)]
    for zz in (z0 + 0.04, z1 - 0.02, z1 + 0.18):
        q = s0.lerp(top, (zz - s0.z) / (top.z - s0.z))
        parts.append(kit.cyl("stack_clamp", q - Vector((0, 0, 0.006)), q + Vector((0, 0, 0.006)), 0.021, "brass", segs=12, bevel=0.0008))
        if zz < z1 + 0.1:
            parts.append(kit.cyl("stack_stay", q + Vector((0.012, 0, 0)), at(zz, -0.004, -90), 0.0042, "steel", segs=8, bevel=0))
    for p in parts:
        p.data.transform(M)
    unit = join(parts, "boiler")
    c.rigid(unit, "chest")
    # Steam lines from the dome over the shoulders to the yoke bands' tops.
    dome = M @ at(z1 + 0.02, -0.01, 0.0)
    for sx in (1, -1):
        a0 = M @ at(z1 - 0.01, 0.0, -sx * 60.0)
        top, nn = yoke["top"][sx]
        un = top + nn * 0.012 + Vector((0, 0.022, 0))
        path = [a0, a0 + (M.to_3x3() @ Vector((0, 0, 0.05))), Vector((un.x * 0.92, un.y + 0.05, un.z - 0.02)), un + Vector((0, 0.012, 0.004)), un]
        c.rigid(mech.tube_path("steam_line", pmc.smooth_path(path, 6), 0.0068, "scrap_copper", segs=8, closed=False), "chest")
        c.rigid(kit.cyl("steam_union", un - nn * 0.014, un + nn * 0.004, 0.0105, "brass", segs=6, bevel=0.001), "chest")
    _ = dome


def waist_ring(c, b, trees):
    """A riveted steel waist ring over the shirt's tuck and the trousers' waistband, latched in front:
    the frame's hips. Returns (centre, its points, out directions)."""
    yc = b.j("spine", 0.0).y
    zr = b.hip_z + 0.06
    n = 36
    pts, dirs = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        d = Vector((math.sin(a), -math.cos(a), 0))
        loc, _ = mech.outermost(trees, (0, yc, zr), d, 0.5)
        pts.append((loc if loc is not None else Vector((0, yc, zr)) + d * 0.18) + d * 0.009)
        dirs.append(d)
    for _ in range(2):
        pts = [(pts[i - 1] + pts[i] * 2 + pts[(i + 1) % n]) / 4 for i in range(n)]
    ring = pmc.sweep("waist_ring", pts, 0.072, 0.0085, PLATE, pmc.radial((0, yc, 0)), closed=True, bevel=0.0015)
    c.rigid(ring, "hips")
    spots = []
    for i in range(n):
        if i in (0, 1, n - 1) or i % 2:
            continue
        for dz in (0.024, -0.024):
            spots.append((pts[i] + dirs[i] * 0.0045 + Vector((0, 0, dz)), dirs[i]))
    c.rigid(mech.rivets("ring_rivets", spots, r=0.0038, material=PLATE, segs=6), "hips")
    c.rigid(mech.bead("ring_rim", [p + d * 0.002 + Vector((0, 0, 0.036)) for p, d in zip(pts, dirs)], 0.0028, normal=lambda q: Vector((q.x, q.y - yc, 0))), "hips")
    c.rigid(mech.bead("ring_rim", [p + d * 0.002 - Vector((0, 0, 0.036)) for p, d in zip(pts, dirs)], 0.0028, normal=lambda q: Vector((q.x, q.y - yc, 0))), "hips")
    # The latch in front.
    p, d = pts[0], dirs[0]
    x, y, z = basis(d)
    latch = [kit.block("latch", (0, 0.008, 0), (0.07, 0.014, 0.052), "brass", bevel=0.002),
             kit.block("latch_bar", (0, 0.017, 0.006), (0.052, 0.006, 0.012), "steel", bevel=0.001),
             kit.cyl("latch_pin", (-0.03, 0.016, -0.014), (0.03, 0.016, -0.014), 0.004, "steel", segs=8, bevel=0)]
    c.rigid(place(join(latch, "latch"), p, x, y, z), "hips")
    return (Vector((0, yc, zr)), pts, dirs)


# ------------------------------------------------------------------------------------------ arms

def arm_frame(c, b, arm, shirt, gloves, yoke, s, sx):
    """One arm: the shoulder hub under a domed pauldron (its cap and one lame), a piston strut down the
    outside of the upper arm to the elbow hub, a flared gauntlet over the forearm closed with two straps
    on the inside, a second strut from the elbow hub down the gauntlet to the wrist."""
    ua, fa = "upper_arm." + s, "forearm." + s
    ua0, ua1 = b.j(ua, 0.0), b.j(ua, 1.0)
    fa0, fa1 = b.j(fa, 0.0), b.j(fa, 1.0)
    OUT = 90 * sx
    sleeve_u = aco.region_tree(shirt, {ua, "shoulder." + s})
    sleeve_f = aco.region_tree(shirt, {fa})
    tg = pmc.tree(gloves)
    tu = aco.Tube([sleeve_u], ua0, ua1, front=(0, -1, 0), t=(0.0, 1.05), nt=24, nphi=48, reach=0.15, spread=0.03, blur=0.02)
    tf = aco.Tube([sleeve_f, tg], fa0, fa1, front=(0, -1, 0), t=(0.0, 1.08), nt=26, nphi=48, reach=0.13, spread=0.025, blur=0.018)

    # The gauntlet: 300 degrees of hammered steel round the forearm, flaring to the wrist, open on the inside.
    def g_off(t, ph):
        return 0.0055 + 0.016 * sm(t, 0.5, 1.02)
    G0, G1, GH = 0.16, 1.02, 150.0
    gaunt = tube_plate(tf, "gauntlet", PLATE, G0, G1, OUT, GH, g_off, 0.0035, nu=18, nv=8, corner=0.0, bevel=0.0012)
    arm.add(gaunt, fa)
    for t in (G0, G1):
        c.rigid(mech.bead("gauntlet_rim", [tf.P(t, OUT + GH * (2 * k / 20 - 1), g_off(t, 0) - 0.0015) for k in range(21)], 0.0028,
                          closed=False, segs=5, normal=lambda q: tf.d(OUT)), fa)
    spots = []
    for t in [G0 + 0.05 + (G1 - G0 - 0.1) * k / 6 for k in range(7)]:
        for ph in (OUT - GH + 9, OUT + GH - 9):
            spots.append((tf.P(t, ph, g_off(t, ph)), tf.d(ph)))
    for t in (G0 + 0.04, G1 - 0.04):
        for k in range(1, 9):
            ph = OUT - GH + 2 * GH * k / 9
            spots.append((tf.P(t, ph, g_off(t, ph)), tf.d(ph)))
    c.rigid(mech.rivets("gauntlet_rivets", spots, r=0.0036, material=PLATE, segs=6), fa)
    tf2 = aco.Tube([sleeve_f, tg], fa0, fa1, hard=[gaunt], t=(0.2, 1.0), nt=17, nphi=36, reach=0.15)
    for t in (0.36, 0.72):
        strap_round(c, "gauntlet_strap", tf2, t, fa, 0.024, 0.0035, buckle_ph=OUT + 180)

    # Hubs and struts on the outside of the arm.
    lat_u, lat_f = lateral(ua0, ua1, sx), lateral(fa0, fa1, sx)
    r_e = max(tu.r(1.0, OUT) + 0.026, tf.r(0.0, OUT) + 0.026)
    pe = fa0 + lat_f * r_e
    ps = ua0.lerp(ua1, 0.34) + lat_u * (tu.r(0.34, OUT) + 0.026)
    pw = fa0.lerp(fa1, 0.9) + lat_f * (tf.r(0.9, OUT) + g_off(0.9, 0) + 0.02)
    c.rigid(join([hub("shoulder_hub", ps, lat_u), piston("arm_strut", ps + lat_u * 0.013, pe + lat_u * 0.013, 0.0165, lat_u)], "arm_frame"), ua)
    # A clamp band round the upper arm holds the shoulder hub.
    tu2 = aco.Tube([sleeve_u], ua0, ua1, t=(0.2, 0.5), nt=7, nphi=36, reach=0.15)
    ring = tu2.ring(0.34, 0.002, n=22)
    c.rigid(aco.strap_ring("arm_clamp", ring, tu2.c(0.34), tu2.A, 0.03, 0.005, PLATE), ua)
    wl = [kit.block("wrist_lug", pw - lat_f * 0.006, (0.03, 0.03, 0.03), PLATE, bevel=0.003)]
    c.rigid(join([hub("elbow_hub", pe, lat_f, r=0.03), piston("forearm_strut", pe + lat_f * 0.03, pw + lat_f * 0.011, 0.0145, lat_f)] + wl,
                     "forearm_frame"), fa)

    # The pauldron over the shoulder, clearing the hub and the yoke.
    hard = [pmc.tree(o) for o in yoke["parts"]]
    lame_tu = aco.Tube([sleeve_u], ua0, ua1, front=(0, -1, 0), t=(0.05, 0.6), nt=16, nphi=48, reach=0.16, spread=0.03, blur=0.02)
    lame = lame_tu.patch("pauldron_lame", PLATE, 0.16, 0.3, OUT, 70, 0.0095, 0.003, nu=14, nv=3, corner=2.5, bevel=0.0012)
    arm.add(lame, ua)
    c.rigid(mech.bead("lame_rim", [lame_tu.P(0.3, OUT + 70 * 0.62 * (2 * k / 12 - 1), 0.0095 - 0.0013) for k in range(13)], 0.0026, closed=False,
                      normal=lambda q: lame_tu.d(OUT)), ua)
    O = ua0 + Vector((-sx * 0.012, 0.0, -0.01))
    cap_env = aco.Env([sleeve_u, lame] + hard, O, Z=(sx * 0.6, 0.0, 0.8), F=(0, -sx, 0), reach=0.18, lat=(-40.0, 90.0),
                      dlat=4.0, dlon=6.0, spread=9.0, blur=7.0, floor=0.003)

    def cap_rim(lo):
        sn = math.sin(math.radians(lo))
        return 30.0 - 42.0 * max(0.0, sn) ** 1.3 + 7.0 * max(0.0, -sn)
    CAP = 0.015
    cap = cap_env.patch("pauldron", PLATE, -180.0, 180.0, cap_rim, lambda lo: 84.0, CAP, 0.0035, nu=24, nv=5, closed=True, pole=True, bevel=0.0015)
    arm.add(cap, ua)
    c.rigid(mech.bead("pauldron_rim", [cap_env.P(cap_rim(lo), lo, CAP - 0.0014) for lo in range(-180, 180, 10)], 0.003, segs=5,
                      normal=lambda q: Vector(q) - O), ua)
    spots = [(cap_env.P(cap_rim(lo) + 6, lo, CAP), cap_env.normal(cap_rim(lo) + 6, lo, CAP)) for lo in range(-160, 180, 32)]
    spots += [(lame_tu.P(0.23, ph, 0.0095), lame_tu.d(ph)) for ph in (OUT - 55, OUT + 55)]
    c.rigid(mech.rivets("pauldron_rivets", spots, r=0.0037, material=PLATE, segs=6), ua)
    if s == "L":
        M = pmc.frame(cap_env.P(34, 90, CAP), cap_env.normal(34, 90, CAP), (0, 0, 1))
        arm.detail(mech.decal_on("pauldron_cog", pmc.tree(cap), mech.cog(0.0, 0.0, 0.034, teeth=9, depth=0.26), (0.0, 0.0, 0.012), M, "paint.scrap_paint"))


def fist(c, b, gloves, s, sx):
    """The striking end: a brass knuckle bar with four bosses across the closed fist and a riveted steel
    plate on the back of the hand."""
    tg = pmc.tree(gloves)
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
    hand = "hand." + s
    # Knuckle bar: over the knuckles, facing between the back of the hand and down the fist.
    d = (back + Lh * 0.9).normalized()
    d = (d - T * d.dot(T)).normalized()
    loc, _ = pmc.hit(tg, mid + Lh * 0.02 + d * 0.15, -d)
    loc = loc if loc is not None else mid + d * 0.03
    z = T.cross(d).normalized()
    parts = [kit.block("knuckle_bar", (0, 0.006, 0), (0.088, 0.012, 0.026), "brass", bevel=0.004)]
    for k in range(4):
        x = -0.0315 + 0.021 * k
        parts.append(kit.cyl("knuckle_boss", (x, 0.011, 0), (x, 0.0175, 0), 0.0085, "brass", r1=0.0065, segs=12, bevel=0.0012))
    c.rigid(place(join(parts, "knuckle_bar"), loc - d * 0.001, T, d, z), hand)
    # Back plate.
    q = mid - Lh * 0.036
    loc, _ = pmc.hit(tg, q + back * 0.15, -back)
    loc = loc if loc is not None else q + back * 0.02
    z2 = T.cross(back).normalized()
    pl = [kit.block("hand_plate", (0, 0.003, 0), (0.07, 0.006, 0.058), PLATE, bevel=0.002),
          mech.rivets("hand_rivets", [(Vector((x, 0.006, zz)), Vector((0, 1, 0))) for x in (-0.027, 0.027) for zz in (-0.021, 0.021)], r=0.0032, material="brass")]
    c.rigid(place(join(pl, "hand_plate"), loc + back * 0.001, T, back, z2), hand)


# ------------------------------------------------------------------------------------------ legs

def leg_frame(c, b, arm, trousers, boot, ring, s, sx):
    """One leg: a hip hub hung from the waist ring, a piston strut down the outside of the thigh to the
    knee hub, a clamp band round the thigh, a knee cop, a riveted shin guard, a second strut from the knee
    hub to a clamp round the boot top."""
    ul, ll = "upper_leg." + s, "lower_leg." + s
    ul0, ul1 = b.j(ul, 0.0), b.j(ul, 1.0)
    ll0, ll1 = b.j(ll, 0.0), b.j(ll, 1.0)
    OUT = 90 * sx
    t_leg = aco.region_tree(trousers, {ul, ll})
    tb = pmc.tree(boot)
    tu = aco.Tube([t_leg], ul0, ul1, front=(0, -1, 0), t=(-0.05, 1.05), nt=24, nphi=48, reach=0.2, spread=0.03, blur=0.02)
    ts = aco.Tube([t_leg, tb], ll0, ll1, front=(0, -1, 0), t=(-0.05, 1.0), nt=26, nphi=48, reach=0.17, spread=0.03, blur=0.02)
    lat_u, lat_s = lateral(ul0, ul1, sx), lateral(ll0, ll1, sx)
    ph = ul0 + lat_u * (tu.r(0.04, OUT) + 0.03)
    pk = ll0 + lat_s * (max(tu.r(1.0, OUT), ts.r(0.0, OUT)) + 0.032)
    t_ank = (ll0.z - (b.sole + 0.2)) / (ll0.z - ll1.z)
    pa = ll0.lerp(ll1, t_ank) + lat_s * (ts.r(t_ank, OUT) + 0.024)
    # Hip hub on a bracket from the waist ring.
    ctr, rpts, rdirs = ring
    i = min(range(len(rpts)), key=lambda k: (rpts[k] - Vector((ph.x, ph.y, rpts[k].z))).length)
    rp = rpts[i] + rdirs[i] * 0.006
    br = kit.block("hip_bracket", (0, 0, 0), (0.044, 0.012, (rp.z - ph.z) + 0.05), PLATE, bevel=0.002)
    x, y, z = basis(lat_u)
    place(br, (rp + ph) / 2 + y * 0.002, x, y, z)
    c.rigid(join([hub("hip_hub", ph, lat_u, r=0.038, thick=0.022), br], "hip_hub"), "hips")
    # Thigh strut and its clamp band.
    tu2 = aco.Tube([t_leg], ul0, ul1, t=(0.4, 0.7), nt=7, nphi=36, reach=0.2)
    band = tu2.ring(0.55, 0.002, n=24)
    cp = ul0.lerp(ul1, 0.55) + lat_u * (tu.r(0.55, OUT) + 0.008)
    sp = ph.lerp(pk, 0.55)
    c.rigid(join([piston("thigh_strut", ph + lat_u * 0.016, pk + lat_s * 0.016, 0.0185, lat_u),
                      aco.strap_ring("thigh_clamp", band, tu2.c(0.55), tu2.A, 0.034, 0.005, PLATE),
                      kit.cyl("clamp_bracket", cp, sp + lat_u * 0.004, 0.0095, PLATE, segs=10, bevel=0.001)], "thigh_frame"), ul)
    # Knee hub, knee cop, shin strut, ankle clamp, shin guard.
    kn = ll0 + Vector((0, 0.012, 0.004))
    kenv = aco.Env([t_leg], kn, Z=(0, -1, 0.12), F=(0, 0, 1), reach=0.15, lat=(0.0, 90.0), dlat=4.0, dlon=8.0, spread=16.0, blur=10.0, floor=0.004)

    def knee_rim(lo):
        return 55.0 - 9.0 * math.cos(math.radians(lo)) ** 2
    cop = kenv.patch("knee_cop", PLATE, -180.0, 180.0, knee_rim, lambda lo: 84.0, 0.0095, 0.0035, nu=16, nv=4, closed=True, pole=True, bevel=0.0015)
    arm.add(cop, ll)
    c.rigid(mech.bead("cop_rim", [kenv.P(knee_rim(lo), lo, 0.0095 - 0.0014) for lo in range(-180, 180, 15)], 0.0028, segs=5, normal=lambda q: Vector(q) - kn), ll)
    G0, G1 = 0.16, t_ank - 0.04
    guard = tube_plate(ts, "shin_guard", PLATE, G0, G1, 4 * sx, 62, lambda t, p: 0.0075 + 0.003 * math.sin(math.pi * (t - G0) / (G1 - G0)), 0.0035,
                       nu=10, nv=8, corner=3.0, bevel=0.0012)
    arm.add(guard, ll)
    spots = [(kenv.P(knee_rim(lo) + 8, lo, 0.0095), kenv.normal(knee_rim(lo) + 8, lo, 0.0095)) for lo in range(-150, 180, 60)]
    for t in [G0 + 0.04 + (G1 - G0 - 0.08) * k / 4 for k in range(5)]:
        for p_ in (4 * sx - 46, 4 * sx + 46):
            spots.append((ts.P(t, p_, 0.0075 + 0.003 * math.sin(math.pi * (t - G0) / (G1 - G0))), ts.d(p_)))
    c.rigid(mech.rivets("leg_rivets", spots, r=0.0036, material=PLATE, segs=6), ll)
    ts2 = aco.Tube([t_leg, tb], ll0, ll1, hard=[guard], t=(0.2, 1.0), nt=17, nphi=36, reach=0.17)
    ank = ts2.ring(t_ank, 0.002, n=24)
    c.rigid(join([hub("knee_hub", pk, lat_s, r=0.034), piston("shin_strut", pk + lat_s * 0.03, pa + lat_s * 0.012, 0.0165, lat_s),
                      aco.strap_ring("ankle_clamp", ank, ts2.c(t_ank), ts2.A, 0.036, 0.005, PLATE),
                      kit.block("ankle_lug", pa - lat_s * 0.004, (0.028, 0.028, 0.036), PLATE, bevel=0.003)], "shin_frame"), ll)
    for t in (0.42,):
        strap_round(c, "shin_strap", ts2, t, ll, 0.026, 0.0035, buckle_ph=OUT + 40 * sx)


SPEC = {"build": build, "faction": "scrappers", "budget": (25000, 120000), "loadout": "fist",
        "colors": {"primary": "#55606a", "secondary": "#4f4536", "accent": "#a0743c"}}
