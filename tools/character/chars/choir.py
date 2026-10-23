"""Choir, Regime: the cult's tall faceless marksman, who listens to the Algorithm through an antenna array
on his back. An elongated bone helmet swept back over the skull, its face a recessed black lens deck
holding a cluster of seven glowing red lenses over a smooth faceplate with a slatted voice grille, a
rangefinder pod on the right rail and comms domes over the ears; a knit hood under it. The Acolyte's
black combat shirt and ripstop trousers, gloves and tactical boots; a slim black plate carrier with
bone-white plates etched with scripture, two marksman magazine pouches on the placard, red padded
shoulder straps and a cummerbund; bone shoulder caps over a lame, a bone data slate with a glowing code
screen on the left forearm, a bone thigh guard on the left leg and a drop-leg magazine rig on the right,
knee caps and long shin guards. On the back plate a bone-housed array: a manifold of organ pipes
rising into seven masts with dipole bars and glowing tips, fanned like a choir, cabled into the helmet.

Built on the realistic layer (real.py) like the Acolyte, on a 1.95 m body: the head dropped under the
helmet and hood, the shirt and trousers draped by the cloth simulation, every hard plate laid on an
envelope of the cloth or head it sits on, baking its scripture, screws and panel lines from detail.

Tints: primary = combat shirt and hood, secondary = trousers, accent = straps and pull tabs.
"""

import math
import os

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import kit
import real
import surfaces
from chars import acolyte as aco
from chars import contractor as pmc
from kit import FOREARMS, SHINS, THIGHS, TORSO, UPPER_ARMS

BONE, NYLON = aco.BONE, aco.NYLON
ARMS = UPPER_ARMS | FOREARMS
FAST = bool(os.environ.get("REGIME_FAST"))  # look-dev: skip the cloth simulations


def _sm(x, a, b):
    return float(real._smooth(x, a, b))


def lens(c, at, n, r, segs=16):
    """A helmet lens looking along `n`: a gunmetal cup, a glowing red ring round a dark glass eye."""
    at, n = Vector(at), Vector(n).normalized()
    cup = kit.cyl("lens_cup", at - n * 0.004, at + n * 0.009, r + 0.0038, "gunmetal", segs=segs, bevel=0.0008, bsegs=1)
    kit.cut(cup, kit.cyl("bore", at + n * 0.0052, at + n * 0.02, r, "steel", segs=segs, bevel=0))
    c.rigid(cup, "head")
    c.rigid(aco.ring("lens_ring", at + n * 0.0062, n, r * 0.98, r * 0.6, 0.0014, "glow_red", segs=segs), "head")
    c.rigid(kit.cyl("lens_glass", at + n * 0.005, at + n * 0.0068, r * 0.62, "glass", segs=max(8, segs - 4), bevel=0), "head")


# ------------------------------------------------------------------------------------------ helmet

def helmet(c, man, arm):
    """The Choir's helmet: a bone shell fitted round the head and swept back and up over the skull, a
    black liner; a smooth faceplate with a keel and a slatted voice grille; between them a recessed
    black lens deck with seven lenses; side rails, comms domes over the ears, a rangefinder pod on the
    right rail and a rear module with the array cable's port. Returns (envelope, shell rim lat(lon),
    mask chin lat(lon), rear port point)."""
    hc = man.head_center()
    dom = kit.dominant(man.low)
    me = man.low.data
    co = [v.co.copy() for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons if sum(dom[i] in ("head", "neck") for i in p.vertices) * 2 > len(p.vertices)]
    head = BVHTree.FromPolygons(co, polys)
    O = hc + Vector((0, -0.016, -0.018))
    env = aco.Env([head], O, reach=0.24, lat=(-80.0, 90.0), dlat=4.0, dlon=5.0, spread=14.0, blur=10.0, floor=0.006)

    BROW, DECK_LO = 21.0, -6.0

    def rim(lo):
        a = abs(lo)
        side = -38.0 + 5.0 * _sm(a, 110, 180)
        return BROW + (side - BROW) * _sm(a, 64, 80)

    def chin(lo):
        return -57.0 + 17.0 * _sm(abs(lo), 0, 82)

    def mtop(lo):
        return DECK_LO + 24.0 * _sm(abs(lo), 52, 72)

    B = Vector((0, 0.55, 0.835)).normalized()  # the shell sweeps back and up toward this

    def shell_off(la, lo):
        w = max(0.0, env.dir(la, lo).dot(B))
        return 0.0135 + 0.032 * w ** 2.2

    def mask_off(la, lo):
        keel = 0.003 * math.exp(-(lo / 5.0) ** 2) * _sm(DECK_LO - la, 3.0, 16.0)
        return 0.0195 + keel - 0.002 * _sm(abs(lo), 40, 80)

    shell = env.patch("helmet", BONE, -180.0, 180.0, rim, lambda lo: 86.0, shell_off, 0.0055, nu=56, nv=14, closed=True, pole=True,
                      inner="regime_pad", bevel=0.0018)
    mask = env.patch("faceplate", BONE, -82.0, 82.0, chin, mtop, mask_off, 0.006, nu=30, nv=11, inner="regime_pad", bevel=0.0018)
    deck = env.patch("lens_deck", "black", -78.0, 78.0, lambda lo: DECK_LO - 2.5, lambda lo: BROW + 2.5, 0.011, 0.0035, nu=26, nv=5,
                     bevel=0.0008)
    arm.add(shell, "head")
    arm.add(mask, "head")
    c.rigid(deck, "head")
    # The lens cluster: a big centre lens, two above and two below it, two out at the temples.
    for la, lo, r in ((8.0, 0.0, 0.0158), (15.5, 18.0, 0.0105), (15.5, -18.0, 0.0105), (0.5, 19.0, 0.0088), (0.5, -19.0, 0.0088),
                      (9.0, 37.0, 0.0068), (9.0, -37.0, 0.0068)):
        n = (env.normal(la, lo, 0.011) + Vector((0, -0.35, 0))).normalized()
        lens(c, env.P(la, lo, 0.011), n, r, segs=16 if r > 0.009 else 12)

    def at(la, lo, off):
        n = env.normal(la, lo, off)
        return env.P(la, lo, off) + n * 0.1, -n
    # Scripture: the cult mark high on the swept-back crown, code on the temples, ticks on the jaw.
    o, d = at(42, 180, shell_off(42, 180))
    arm.etch(shell, aco.sigil(0.027, n=24, w=0.0028) + aco.code_rows(["∴"], 0.029), o, d)
    o, d = at(14, 180, shell_off(14, 180))
    arm.etch(shell, aco.code_rows(["CHOIR 07"] + aco.scripture(19, 1, 11), 0.0082), o, d)
    for sx in (1, -1):
        o, d = at(34, sx * 66, shell_off(34, sx * 66))
        arm.etch(shell, aco.code_rows(aco.scripture(7 + sx, 3, 6), 0.0082), o, d)
        o, d = at(-24, sx * 58, mask_off(-24, sx * 58))
        arm.etch(mask, aco.tick_rows(11 + sx, 3, 0.03, 0.0035, unit=0.001), o, d)
        for la, lo in ((-8, sx * 74), (-36, sx * 70)):
            arm.detail(aco.screw(env.P(la, lo, mask_off(la, lo)), env.normal(la, lo, mask_off(la, lo)), r=0.0034))

    # The voice grille down the middle of the faceplate, and slots either side.
    c.rigid(env.patch("voice_grille", "black", -7.5, 7.5, lambda lo: -44.0, lambda lo: -15.0, lambda la, lo: mask_off(la, lo) + 0.001, 0.003,
                      nu=4, nv=6, bevel=0.0008, segs=1), "head")
    for k in range(6):
        la0 = -42.0 + k * 4.6
        c.rigid(env.patch("grille_slat", "gunmetal", -6.0, 6.0, lambda lo, la0=la0: la0, lambda lo, la0=la0: la0 + 1.7,
                          lambda la, lo: mask_off(la, lo) + 0.0026, 0.0016, nu=3, nv=1, bevel=0.0), "head")
    for sx in (1, -1):
        for lo0 in (26.0, 33.0):
            l0, l1 = sorted((sx * lo0, sx * (lo0 + 3.0)))
            c.rigid(env.patch("cheek_slot", "black", l0, l1, lambda lo: -40.0, lambda lo: -20.0, lambda la, lo: mask_off(la, lo) + 0.0008,
                              0.0024, nu=1, nv=4, bevel=0.0006, segs=1), "head")

    # Side rails, comms domes over the ears, the rangefinder on the right rail, the rear module.
    for sx in (1, -1):
        lo0, lo1 = sorted((sx * 94.0, sx * 150.0))
        c.rigid(env.patch("rail", "black", lo0, lo1, lambda lo: -3.0 + 0.05 * (abs(lo) - 94), lambda lo: 4.5 + 0.05 * (abs(lo) - 94),
                          lambda la, lo: shell_off(la, lo) + 0.0055, 0.0055, nu=10, nv=1, bevel=0.0012, segs=1), "head")
        p = env.P(-15, sx * 100, shell_off(-15, sx * 100) - 0.002)
        n = env.normal(-15, sx * 100, 0.0135)
        c.rigid(kit.cyl("comms", p, p + n * 0.013, 0.031, "black", segs=20, bevel=0.002, bsegs=1), "head")
        c.rigid(kit.cyl("comms_cap", p + n * 0.012, p + n * 0.017, 0.022, "gunmetal", segs=20, bevel=0.0012, bsegs=1), "head")
    # Rangefinder: a gunmetal box on the right rail, its lens looking forward, a fin stack behind.
    p = env.P(1.0, -100.0, shell_off(1.0, -100.0) + 0.011)
    n = env.normal(1.0, -100.0, 0.0135)
    M = pmc.frame(p + n * 0.012, n, (0, 0, 1))
    rf = [kit.block("rangefinder", (0, -0.003, 0), (0.07, 0.024, 0.03), "gunmetal", bevel=0.003),
          kit.block("rf_mount", (0.0, 0.009, 0.0), (0.03, 0.012, 0.02), "black", bevel=0.0015)]
    for i in range(3):
        rf.append(kit.block("rf_fin", (0.024 + i * 0.007, -0.016, 0.0), (0.003, 0.004, 0.032), "black", bevel=0))
    for o in rf:
        o.data.transform(M)
        c.rigid(o, "head")
    fwd = (M.to_3x3() @ Vector((-1, 0, 0))).normalized()  # the box's front end (toward the face)
    if fwd.y > 0:
        fwd = -fwd
    front = M @ Vector((0.0, -0.003, 0.0)) + fwd * 0.035
    lens(c, front, fwd, 0.0085, segs=14)
    n = env.normal(6, 180, shell_off(6, 180))
    M = pmc.frame(env.P(6, 180, shell_off(6, 180)) + n * 0.014, n, (0, 0, 1))
    batt = [kit.block("battery", (0, 0, 0), (0.07, 0.03, 0.05), "black", bevel=0.005),
            kit.block("battery_lid", (0, -0.016, 0.004), (0.056, 0.004, 0.034), "gunmetal", bevel=0.0012),
            kit.cyl("strobe", (0.0, -0.012, 0.028), (0.0, -0.012, 0.033), 0.008, "glow_red", segs=10, bevel=0)]
    for o in batt:
        o.data.transform(M)
        c.rigid(o, "head")
    # The array cable's plug under the module.
    c.rigid(kit.cyl("cable_plug", M @ Vector((0.0, 0.0, -0.022)), M @ Vector((0.0, 0.0, -0.036)), 0.0068, "gunmetal", segs=12, bevel=0.001,
                    bsegs=1), "head")
    c.rigid(aco.ring("plug_collar", M @ Vector((0.0, 0.0, -0.03)), M.to_3x3() @ Vector((0, 0, -1)), 0.0082, 0.0062, 0.004, "black", segs=12),
            "head")
    port = M @ Vector((0.0, 0.0, -0.034))
    return env, rim, chin, port


# ------------------------------------------------------------------------------------------ build

def build():
    b = real.Anatomy(height=1.95, sole=0.034)
    c = real.begin("choir", b)
    man = real.body(c, stubble=0.0, face_detail=1.0)
    J, seg, sm = b.j, kit.seg_dist, real._smooth
    k = b.k
    lead = real.bones_at(man)
    armpit = b.at("armpit")
    head_arm = aco.Armour(c, "armour_head", texel=2.6)
    torso_arm = aco.Armour(c, "armour_torso", texel=2.3)
    arm_arm = aco.Armour(c, "armour_arms", texel=2.2)
    leg_arm = aco.Armour(c, "armour_legs", texel=2.1)
    surfaces._TEXEL_FN[man.low.name] = lambda obj: (lambda isl: 0.3)  # no skin shows

    # Faceless: the eyes go, and the head's skin under the helmet and hood.
    for e in man.eyes:
        c.parts = [p for p in c.parts if p[0] is not e]
    env, rim, chin, port = helmet(c, man, head_arm)
    for e in man.eyes:
        bpy.data.objects.remove(e, do_unlink=True)
    c.cover({"head"})

    # ---------------------------------------------------------------- gloves and boots
    gl = real.gloves(c, man, "glove", cuff=0.045, knuckle="black")
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
        M = Matrix((T, back, Lh)).transposed().to_4x4()
        ax = J("hand." + s, 0.0) - J("forearm." + s, 0.0)
        cc = J("hand." + s, 0.0) - ax.normalized() * 0.024
        r = pmc._radius(tg, cc, ax)
        c.rigid(pmc.band("glove_cuff", cc, (r + 0.003, r * 0.82 + 0.003), 0.032, 0.004, "glove", axis=ax), "forearm." + s)
        tab = kit.block("cuff_tab", (0, 0, 0), (0.02, 0.004, 0.028), "accent", bevel=0.0012)
        M.translation = cc + back * (r + 0.005)
        tab.data.transform(M)
        c.rigid(tab, "forearm." + s)
    real.boots(c, man, "boot", sole_kind="rubber", trim="rubber", top=0.2, lace="webbing", tab="accent")

    # ---------------------------------------------------------------- combat shirt and hood
    neck = J("neck", 0.0)
    tuck = b.hip_z + 0.1
    waist = tuck - 0.03
    neckline = (Vector((0, 0, neck.z + 0.03)), Vector((0, -0.45, 1)).normalized())
    collar_top = (neckline[0] + Vector((0, 0, 0.032)), Vector((0, -0.25, 1)).normalized())

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
        return 0.007 + 0.011 * max(0.0, min(1.0, (0.095 - a) / 0.03))

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
    shirt = real.garment(c, man, "shirt", "primary", lambda p: lead(p) in TORSO | ARMS | THIGHS | {"neck"} and p.z > waist - 0.05,
                         cuts, ease=ease, pin=None if FAST else pin, slack=slack, bend=12.0, texel=1.15,
                         trims=[("knit.primary", lambda p: (above(neckline, p) and lead(p) not in ARMS) or cuff(p))])
    c.hide_under(shirt.low, 0.05, 2)
    tshirt = pmc.tree(shirt.low)

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

    # ---------------------------------------------------------------- trousers
    top_z = tuck
    belt_z = b.hip_z + 0.075
    hem = b.sole + 0.2 - 0.03
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

    # ---------------------------------------------------------------- plate carrier
    def Z(z):
        return armpit - 0.198 * k + (z - 1.03) * k

    def X(x):
        return x * k

    def outline(pts, r):
        return kit.rounded([(X(x), Z(z)) for x, z in pts], r)
    shirt_hard = [tshirt]
    f_cover = outline([(-0.124, 1.10), (0.124, 1.10), (0.124, 1.29), (0.074, 1.378), (-0.074, 1.378), (-0.124, 1.29)], 0.022)
    f_plate = outline([(-0.112, 1.112), (0.112, 1.112), (0.112, 1.286), (0.066, 1.366), (-0.066, 1.366), (-0.112, 1.286)], 0.018)
    pf = aco.Plate(shirt_hard, f_cover, -1, 0.007)
    front = pf.patch("carrier_front", NYLON, f_cover, 0.022, 0.022, nu=16, nv=12, bevel=0.005)
    c.rigid(front, "chest")
    fp = pf.patch("chest_plate", BONE, f_plate, 0.032, 0.0105, nu=18, nv=14, bevel=0.003)
    torso_arm.add(fp, "chest")
    torso_arm.detail(pf.border(f_plate, 0.032))
    for sx in (1, -1):
        p = pf.P(sx * X(0.052), Z(1.298), 0.032)
        torso_arm.etch(fp, aco.code_rows(aco.scripture(13 + sx, 5, 7), 0.0104), p + Vector((0, -0.1, 0)), (0, 1, 0))
    # The Choir's mark: three concentric rings (the array's reach) round the cult's sign.
    p = pf.P(0.0, Z(1.19), 0.032)
    torso_arm.etch(fp, aco.sigil(0.032, n=30, w=0.0026) + aco.sigil(0.022, n=22, w=0.0024) + aco.code_rows(["∴"], 0.024),
                   p + Vector((0, -0.1, 0)), (0, 1, 0))
    p = pf.P(0.0, Z(1.13), 0.032)
    torso_arm.etch(fp, aco.barcode(29, 0.15, 0.007), p + Vector((0, -0.1, 0)), (0, 1, 0))
    for x, z in ((-0.094, 1.14), (0.094, 1.14), (-0.088, 1.285), (0.088, 1.285)):
        torso_arm.detail(aco.screw(pf.P(X(x), Z(z), 0.032), pf.normal(X(x), Z(z)), r=0.0042))
    # The placard: two marksman magazine pouches with red pull tabs, a small admin pouch between them.
    for x, w, h, tab in ((-0.062, 0.078, 0.128, True), (0.062, 0.078, 0.128, True), (0.0, 0.04, 0.09, False)):
        M = pf.frame(X(x), Z(1.163), 0.022)
        objs = [kit.block("mag_pouch", (0, -0.022, -0.008 + (0.128 - h) / 2), (w, 0.044, h), NYLON, bevel=0.006),
                kit.block("pouch_flap", (0, -0.024, 0.048), (w + 0.004, 0.05, 0.03), NYLON, bevel=0.005)]
        if tab:
            objs += [kit.block("bungee", (0, -0.045, -0.014), (w + 0.002, 0.004, 0.012), "black", bevel=0.0015),
                     kit.block("pull_tab", (0, -0.052, 0.038), (0.026, 0.005, 0.034), "accent", bevel=0.0015)]
        else:
            objs += [kit.block("admin_tab", (0, -0.0475, 0.03), (0.024, 0.004, 0.018), BONE, bevel=0.0012)]
        for o in objs:
            o.data.transform(M)
            c.rigid(o, "chest")

    b_cover = outline([(-0.128, 1.03), (0.128, 1.03), (0.128, 1.29), (0.1, 1.365), (-0.1, 1.365), (-0.128, 1.29)], 0.025)
    b_plate = outline([(-0.116, 1.042), (0.116, 1.042), (0.116, 1.286), (0.09, 1.353), (-0.09, 1.353), (-0.116, 1.286)], 0.02)
    pb = aco.Plate(shirt_hard, b_cover, 1, 0.007)
    back = pb.patch("carrier_back", NYLON, b_cover, 0.022, 0.022, nu=16, nv=12, bevel=0.005)
    c.rigid(back, "chest")
    bp = pb.patch("back_plate", BONE, b_plate, 0.032, 0.0105, nu=18, nv=14, bevel=0.003)
    torso_arm.add(bp, "chest")
    torso_arm.detail(pb.border(b_plate, 0.032))
    p = pb.P(0.0, Z(1.065), 0.032)
    torso_arm.etch(bp, aco.tick_rows(37, 2, 0.2, 0.005), p + Vector((0, 0.1, 0)), (0, -1, 0))

    # ---------------------------------------------------------------- the array
    # A bone housing on the back plate; on it a gunmetal manifold of organ pipes, each rising into a
    # mast with dipole bars and a glowing tip, fanned out like a choir; cabled into the helmet.
    Mb = pb.frame(0.0, Z(1.205), 0.032)
    hw, hd, hh = 0.15, 0.07, 0.25

    def W_(p):
        return Mb @ Vector(p)
    nrm = (Mb.to_3x3() @ Vector((0, -1, 0))).normalized()
    upv = (Mb.to_3x3() @ Vector((0, 0, 1))).normalized()
    house = kit.block("array_housing", (0, -hd / 2, 0), (hw, hd, hh), NYLON, bevel=0.01, taper=(0.94, 0.97))
    house.data.transform(Mb)
    c.rigid(house, "chest")
    lid = kit.block("array_lid", (0, -hd - 0.003, 0.006), (hw - 0.024, 0.008, hh - 0.046), BONE, bevel=0.003)
    kit.hs.apply_modifiers(lid)
    lid.data.transform(Mb)
    torso_arm.add(lid, "chest")
    torso_arm.etch(lid, aco.sigil(0.036, n=30, w=0.003) + aco.sigil(0.025, n=24, w=0.0026) + aco.code_rows(["∴"], 0.03),
                   W_((0, -hd - 0.007, 0.036)) + nrm * 0.1, -nrm)
    torso_arm.etch(lid, aco.code_rows(["CHOIR", "0x7F A3 C0DE", "LISTEN"], 0.0082), W_((0, -hd - 0.007, -0.062)) + nrm * 0.1, -nrm)
    for x in (-0.05, 0.05):
        for z in (-0.088, 0.094):
            torso_arm.detail(aco.screw(W_((x, -hd - 0.007, z)), nrm, r=0.0036))
    for z in (-0.104, 0.11):
        c.rigid(_placed(kit.block("array_strap", (0, -hd / 2 - 0.002, z), (hw + 0.008, hd + 0.01, 0.022), "webbing", bevel=0.002), Mb), "chest")
    man_z = hh / 2 + 0.018
    c.rigid(_placed(kit.block("manifold", (0, -hd / 2, man_z), (hw + 0.012, hd * 0.9, 0.034), "gunmetal", bevel=0.004), Mb), "chest")
    c.rigid(_placed(kit.block("manifold_band", (0, -hd / 2, man_z - 0.021), (hw + 0.004, hd * 0.92, 0.01), BONE, bevel=0.002), Mb), "chest")
    c.rigid(_placed(kit.cyl("manifold_led", (0.06, -hd - 0.003, man_z), (0.06, -hd - 0.008, man_z), 0.004, "glow_red", segs=8, bevel=0), Mb),
            "chest")
    pipes = ((-3, 0.07, 0.28), (-2, 0.09, 0.34), (-1, 0.11, 0.4), (0, 0.13, 0.46), (1, 0.11, 0.4), (2, 0.09, 0.34), (3, 0.07, 0.28))
    for i, ph, L in pipes:
        x = i * 0.023
        base = W_((x, -hd / 2, man_z + 0.017))
        fan = math.radians(i * 7.0)
        side = (Mb.to_3x3() @ Vector((1, 0, 0))).normalized()
        dv = (upv * math.cos(fan) + side * math.sin(fan) - nrm * 0.12).normalized()
        top = base + dv * ph
        c.rigid(kit.cyl("organ_pipe", base, top, 0.0105, "gunmetal", segs=12, bevel=0.001, bsegs=1), "chest")
        c.rigid(kit.cyl("pipe_collar", top - dv * 0.012, top + dv * 0.002, 0.0125, BONE, segs=12, bevel=0.001, bsegs=1), "chest")
        c.rigid(kit.cyl("pipe_mouth", base + dv * ph * 0.3, base + dv * (ph * 0.3 + 0.014), 0.0112, "black", segs=12, bevel=0), "chest")
        bars_ = [(0.32 + 0.16 * j, 0.032 - 0.006 * j) for j in range(4)]
        c.rigid(aco.antenna("mast", top, top + dv * L * k, r=0.0042, bars=bars_), "chest")
    # Cable from the helmet's rear module round the neck into the manifold.
    end = W_((-0.05, -hd / 2 + 0.012, man_z + 0.016))
    c.add(kit.rope("array_cable", [port, port + Vector((0.0, 0.012, -0.03)), end + Vector((-0.012, 0.03, 0.05)), end],
                   0.0048, "rubber", segs=6), ["head", "neck", "chest"])
    c.rigid(aco.socket("array_port", end, nrm.lerp(upv, 0.5), r=0.0075), "chest")

    # Padded shoulder straps in the accent colour, buckles, a PTT on the left one.
    for s, sx in (("L", 1), ("R", -1)):
        xs = sx * X(0.083)
        pts = []
        for y in (-0.13, -0.10, -0.07, -0.04, -0.01, 0.02, 0.05, 0.08, 0.11, 0.13):
            loc, _ = pmc.hit(tshirt, (xs, y * k, 2.2), (0, 0, -1))
            z = loc.z + 0.008 if loc and loc.z > armpit + 0.05 else Z(1.36)
            pts.append((xs, y * k, z))
        pts[0] = pf.P(sx * X(0.07), Z(1.362), 0.012)
        pts[-1] = pb.P(sx * X(0.078), Z(1.348), 0.012)
        path = pmc.smooth_path(pts, 3)
        nr = pmc.radial((xs, 0, Z(1.33)), (1, 0, 0))
        c.rigid(pmc.sweep("shoulder_strap", path, 0.05, 0.013, "accent", nr), "chest")
        kk = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.07 * k))
        tan = (path[kk + 1] - path[kk - 1]).normalized()
        nn = nr(path[kk]).normalized()
        c.rigid(pmc.side_buckle("strap_buckle", path[kk] + nn * 0.009, -tan, nn, w=0.04), "chest")
        if s == "L":
            k2 = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.035 * k))
            t2 = (path[k2 + 1] - path[k2 - 1]).normalized()
            n2 = nr(path[k2]).normalized()
            Mp = pmc.frame(path[k2] + n2 * 0.0065, n2, t2)
            ptt = [kit.block("ptt", (0, -0.009, 0), (0.034, 0.018, 0.042), "black", bevel=0.003),
                   kit.cyl("ptt_button", (0, -0.017, 0.004), (0, -0.023, 0.004), 0.009, "accent", segs=14, bevel=0.0015)]
            pmc.put(ptt, Mp)
            pmc.rigid_all(c, ptt, "chest")
            ptt_top = Mp @ Vector((0, -0.01, 0.022))
            over = [path[i] + nr(path[i]).normalized() * 0.014 + Vector((0.026, 0, 0)) for i in range(k2 + 3, len(path) - 4, 3)]
            c.rigid(kit.rope("ptt_cable", [ptt_top] + over + [end + Vector((0.08, 0.0, 0.0)), end + Vector((0.05, 0.0, -0.01))], 0.0035, "black",
                             segs=6), "chest")
    for s, sx in (("L", 1), ("R", -1)):
        for z, w in ((Z(1.075), 0.06), (Z(1.15), 0.06)):
            pts = pmc._ring_side(tshirt, (0, -0.004), z, 0.012, sx * 46, sx * 136)
            c.rigid(pmc.sweep("cummerbund", pmc.smooth_path(pts, 3), w, 0.012, NYLON, pmc.radial((0, -0.004, 0))), "chest")

    # ---------------------------------------------------------------- shoulder caps
    for s, sx in (("L", 1), ("R", -1)):
        ua = "upper_arm." + s
        ua0, ua1 = J(ua, 0.0), J(ua, 1.0)
        sleeve = aco.region_tree(shirt.low, {ua, "shoulder." + s})
        tu = aco.Tube([sleeve], ua0, ua1, front=(0, -1, 0), t=(0.1, 0.75), nt=22, nphi=48, reach=0.14, spread=0.03, blur=0.02)
        lame = tu.patch("shoulder_lame", BONE, 0.2, 0.42, 90 * sx, 66, 0.007, 0.0055, nu=10, nv=3, corner=2.5, bevel=0.002)
        arm_arm.add(lame, ua)
        O = ua0 + Vector((-sx * 0.012, 0.0, -0.012))
        cap_env = aco.Env([sleeve, lame], O, Z=(sx * 0.6, 0.0, 0.8), F=(0, -sx, 0), reach=0.16, lat=(-40.0, 90.0), dlat=4.0, dlon=6.0,
                          spread=9.0, blur=7.0, floor=0.003)

        def cap_rim(lo):
            sn = math.sin(math.radians(lo))
            return 38.0 - 63.0 * max(0.0, sn) ** 1.3 + 7.0 * max(0.0, -sn)
        cap = cap_env.patch("shoulder_cap", BONE, -180.0, 180.0, cap_rim, lambda lo: 84.0, 0.0095, 0.006, nu=28, nv=6, closed=True, pole=True,
                            inner="regime_pad", bevel=0.0022)
        arm_arm.add(cap, ua)
        n = cap_env.normal(40, 90)
        arm_arm.etch(cap, aco.code_rows(aco.scripture(141 + sx, 3, 7), 0.0095), cap_env.P(40, 90, 0.0095) + n * 0.1, -n, up=(0, 0, 1))
        n = tu.d(90 * sx)
        arm_arm.etch(lame, aco.tick_rows(144 + sx, 2, 0.06, 0.0045), tu.P(0.33, 90 * sx, 0.007) + n * 0.1, -n, up=(ua0 - ua1).normalized())
        for lo in (-40, -140):
            la = cap_rim(lo) + 7
            arm_arm.detail(aco.screw(cap_env.P(la, lo, 0.0095), cap_env.normal(la, lo, 0.0095), r=0.0035))
        tu2 = aco.Tube([sleeve], ua0, ua1, hard=[lame], t=(0.3, 0.5), nt=6, nphi=36, reach=0.14)
        c.rigid(aco.strap_ring("arm_strap", tu2.ring(0.38, 0.0015, n=20), ua0.lerp(ua1, 0.38), ua1 - ua0, 0.022, 0.004, NYLON), ua)

    # ---------------------------------------------------------------- the data slate (left forearm)
    s, sx = "L", 1
    fa = "forearm." + s
    fa0, fa1 = J(fa, 0.0), J(fa, 1.0)
    sl = aco.region_tree(shirt.low, {fa})
    tf = aco.Tube([sl], fa0, fa1, front=(0, -1, 0), t=(0.0, 1.0), nt=26, nphi=48, reach=0.12, spread=0.03, blur=0.02)
    PH = 62.0
    slate = tf.patch("slate", BONE, 0.2, 0.74, PH, 52, 0.016, 0.012, nu=10, nv=8, corner=4.0, bevel=0.003)
    arm_arm.add(slate, fa)
    screen = tf.patch("slate_screen", "glass", 0.27, 0.62, PH, 34, 0.0172, 0.0025, nu=8, nv=6, corner=6.0, bevel=0.0)
    c.rigid(screen, fa)
    n = tf.d(PH)
    upa = (fa0 - fa1).normalized()
    # Code scrolling on the screen: rows of glowing ticks (cheap geometry, they glow in the game).
    glow = aco.project(screen, aco.tick_rows(161, 6, 0.036, 0.0024, unit=0.0011, lead=2.2), tf.P(0.445, PH, 0.0172) + n * 0.1, -n,
                       up=upa, lift=0.0003, material="glow_red", name="slate_code")
    c.rigid(glow, fa)
    arm_arm.etch(slate, aco.code_rows(["∴ 07"], 0.0068), tf.P(0.69, PH, 0.016) + n * 0.1, -n, up=upa)
    for tq in (0.23, 0.71):
        for pq in (-36, 36):
            arm_arm.detail(aco.screw(tf.P(tq, PH + pq, 0.016), tf.d(PH + pq), r=0.0024))
    tf2 = aco.Tube([sl], fa0, fa1, hard=[slate], t=(0.15, 0.8), nt=14, nphi=36, reach=0.12)
    for tq in (0.3, 0.64):
        c.rigid(aco.strap_ring("slate_strap", tf2.ring(tq, 0.0015, n=20), fa0.lerp(fa1, tq), fa1 - fa0, 0.02, 0.004, NYLON), fa)
    # A light bone guard on the right forearm.
    s, sx = "R", -1
    fa = "forearm." + s
    fa0, fa1 = J(fa, 0.0), J(fa, 1.0)
    sl = aco.region_tree(shirt.low, {fa})
    tf = aco.Tube([sl], fa0, fa1, front=(0, -1, 0), t=(0.0, 1.0), nt=26, nphi=48, reach=0.12, spread=0.025, blur=0.016)
    vb = tf.patch("forearm_guard", BONE, 0.18, 0.74, 68 * sx, 62, 0.0085, 0.006, nu=10, nv=7, corner=3.0, bulge=0.003, bevel=0.0024)
    arm_arm.add(vb, fa)
    n = tf.d(68 * sx)
    arm_arm.etch(vb, aco.code_rows(aco.scripture(151, 2, 4), 0.0078), tf.P(0.46, 68 * sx, 0.0085) + n * 0.1, -n, up=(fa0 - fa1).normalized())
    tf2 = aco.Tube([sl], fa0, fa1, hard=[vb], t=(0.15, 0.8), nt=14, nphi=36, reach=0.12)
    for tq in (0.3, 0.64):
        c.rigid(aco.strap_ring("guard_strap", tf2.ring(tq, 0.0015, n=20), fa0.lerp(fa1, tq), fa1 - fa0, 0.018, 0.004, NYLON), fa)

    # ---------------------------------------------------------------- legs
    for s, sx in (("L", 1), ("R", -1)):
        ul, ll = "upper_leg." + s, "lower_leg." + s
        ul0, ul1 = J(ul, 0.0), J(ul, 1.0)
        ll0, ll1 = J(ll, 0.0), J(ll, 1.0)
        tu = aco.Tube([tt], ul0, ul1, t=(-0.05, 0.75), nt=30, nphi=60, reach=0.17, spread=0.03, blur=0.022)
        if s == "L":
            # Thigh guard: front and outside of the thigh, hung from the belt.
            thigh = tu.patch("thigh_guard", BONE, 0.1, 0.46, 42 * sx, 38, 0.0095, 0.007, nu=10, nv=7, corner=3.0, bulge=0.003, bevel=0.0025)
            leg_arm.add(thigh, ul)
            n = tu.d(44 * sx)
            leg_arm.etch(thigh, aco.code_rows(aco.scripture(161 + sx, 4, 6), 0.0098), tu.P(0.28, 44 * sx, 0.0095) + n * 0.1, -n,
                         up=(ul0 - ul1).normalized())
            for tq in (0.14, 0.42):
                for pq in (-28, 28):
                    ph = 42 * sx + pq
                    leg_arm.detail(aco.screw(tu.P(tq, ph, 0.0095), tu.d(ph), r=0.0034))
            tu2 = aco.Tube([tt], ul0, ul1, hard=[thigh], t=(0.0, 0.5), nt=11, nphi=36, reach=0.17)
            c.rigid(aco.strap_ring("thigh_strap", tu2.ring(0.32, 0.0015, n=22), ul0.lerp(ul1, 0.32), ul1 - ul0, 0.03, 0.0045, "accent"), ul)
            top = tu.P(0.1, 42 * sx, 0.006)
            hanger(c, tt, Vector((top.x, top.y, belt_z + 0.01)), top + Vector((0, 0, 0.012)), tu.d(42 * sx), 0.022, "black", ["hips", ul])
        else:
            # Drop-leg rig: a nylon platform on two straps, two marksman magazine pouches on it.
            PHr = 78.0 * sx
            plat = tu.patch("leg_platform", NYLON, 0.3, 0.62, PHr, 34, 0.012, 0.009, nu=8, nv=6, corner=3.0, bevel=0.003)
            c.rigid(plat, ul)
            for tq in (0.38, 0.55):
                M = pmc.frame(tu.P(tq, PHr, 0.012), tu.d(PHr), ul0 - ul1)
                po = [kit.block("leg_mag", (0, -0.018, 0), (0.07, 0.036, 0.075), NYLON, bevel=0.005),
                      kit.block("leg_mag_flap", (0, -0.02, 0.03), (0.074, 0.04, 0.022), NYLON, bevel=0.004),
                      kit.block("pull_tab", (0, -0.042, 0.024), (0.022, 0.005, 0.028), "accent", bevel=0.0012)]
                for o in po:
                    o.data.transform(M)
                    c.rigid(o, ul)
            tu2 = aco.Tube([tt], ul0, ul1, hard=[plat], t=(0.2, 0.7), nt=11, nphi=36, reach=0.17)
            for tq in (0.34, 0.58):
                c.rigid(aco.strap_ring("leg_strap", tu2.ring(tq, 0.0015, n=22), ul0.lerp(ul1, tq), ul1 - ul0, 0.026, 0.0045, "accent"), ul)
            top = tu.P(0.3, PHr, 0.008)
            hanger(c, tt, Vector((top.x, top.y, belt_z + 0.01)), top + Vector((0, 0, 0.01)), tu.d(PHr), 0.03, "webbing", ["hips", ul])

        # Long shin guards and knee caps over the trousers.
        ts = aco.Tube([tt], ll0, ll1, t=(-0.1, 0.85), nt=30, nphi=60, reach=0.15, spread=0.03, blur=0.022)
        shin = ts.patch("shin_guard", BONE, 0.11, 0.7, 4 * sx, 58, 0.009, 0.0065, nu=10, nv=10, corner=3.0, bulge=0.004, bevel=0.0025)
        leg_arm.add(shin, ll)
        n = ts.d(4 * sx)
        leg_arm.etch(shin, aco.code_rows(aco.scripture(171 + sx, 9, 3), 0.0092), ts.P(0.44, 4 * sx, 0.009) + n * 0.1, -n, up=(ll0 - ll1).normalized())
        kn = ll0 + Vector((0, 0.012, 0.004))
        kenv = aco.Env([tt, shin], kn, Z=(0, -1, 0.12), F=(0, 0, 1), reach=0.14, lat=(0.0, 90.0), dlat=4.0, dlon=8.0, spread=16.0, blur=10.0,
                       floor=0.004)
        knee = kenv.patch("knee_cap", BONE, -180.0, 180.0, lambda lo: 50.0 - 10.0 * math.cos(math.radians(lo)) ** 2, lambda lo: 84.0, 0.011,
                          0.0065, nu=16, nv=4, closed=True, pole=True, inner="regime_pad", bevel=0.0022)
        leg_arm.add(knee, ll)
        kp = kenv.P(90, 0, 0.011)
        kn_n = kenv.normal(90, 0, 0.011, h=4.0)
        c.rigid(kit.cyl("knee_boss", kp - kn_n * 0.003, kp + kn_n * 0.0045, 0.013, "gunmetal", segs=6, bevel=0.0012, bsegs=1), ll)
        ts2 = aco.Tube([tt], ll0, ll1, hard=[shin], t=(0.1, 0.75), nt=13, nphi=36, reach=0.15)
        for tq in (0.24, 0.58):
            c.rigid(aco.strap_ring("shin_strap", ts2.ring(tq, 0.0015, n=22), ll0.lerp(ll1, tq), ll1 - ll0, 0.024, 0.0045, "webbing"), ll)

    for a in (head_arm, torso_arm, arm_arm, leg_arm):
        a.finish()
    pmc.economise(c)
    return c


def hanger(c, tree, p0, p1, d, width, material, bones, n=7, lift=0.0032):
    """A strap hung from the belt (p0) down to a leg piece (p1), laid on the cloth under it (`tree`),
    seen from outward direction `d`."""
    d = Vector(d).normalized()
    pts, nrm = [], {}
    for i in range(n):
        q = Vector(p0).lerp(Vector(p1), i / (n - 1))
        loc, nor, _, _ = tree.ray_cast(q + d * 0.12, -d, 0.3)
        if loc is not None:
            nor = nor if nor.dot(d) > 0 else -nor
            q = loc + nor * lift
            nrm[i] = nor
        pts.append(q)
    pts[-1] = Vector(p1)
    path = pmc.smooth_path(pts, 2)

    def normal(p):
        i = min(range(n), key=lambda j: (pts[j] - p).length)
        return nrm.get(i, d)
    c.add(pmc.sweep("hanger", path, width, 0.004, material, normal), bones)


def _placed(obj, M):
    obj.data.transform(M)
    return obj


SPEC = {"build": build, "faction": "regime", "budget": (25000, 120000), "loadout": "dmr",
        "colors": {"primary": "#202024", "secondary": "#34343a", "accent": "#6e1212"}}
