"""Bruiser, Scrappers: a big man in a riveted steel exo-frame worn over heavy work clothes. Piston
struts along every arm and leg bone (steel barrels, bright rods, brass glands) pinned to hubs on the
joint axes, a waist ring, shoulder yokes with a hand-painted cog, steel shoulder caps, flared gauntlets,
and a back frame carrying a small riveted copper boiler with a gauge, safety valve, firebox and stack.
Bald, a big ginger beard, leather gloves with knuckle plates, steel-capped boots.

Tints: primary = shirt (faded chambray), secondary = canvas trousers, accent = harness straps.
"""

import math

import bmesh
from mathutils import Vector

import kit
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS
from chars.mechanic import (ARMS, SPINE, UP, Probe, boots, catmull, cog, contour, gauge, hair_cap, local, onto, plate,
                            rivets, smoothstep, spot, strap_over, transfer_from, tube_path, wrap)

kit.hs.PALETTE.setdefault("scrap_ginger", ((0.42, 0.12, 0.03), (0.62, 0.26, 0.08), 0.0, 0.7, 0.0, 0))


def lateral(b, bone, sx):
    """The outward side (+X for .L) of `bone`, square to it: where a joint's hinge axis comes out."""
    a = (b.j(bone, 1) - b.j(bone, 0)).normalized()
    x = Vector((sx, 0, 0))
    return (x - a * x.dot(a)).normalized()


def reach(b, probe, bone, out, t0, t1, n=8):
    """How far the surface sticks out along `out` from `bone` between t0 and t1."""
    r = 0.0
    for i in range(n + 1):
        d = probe.depth(b.j(bone, t0 + (t1 - t0) * i / n), out, 0.4)
        if d:
            r = max(r, d)
    return r


def loft(name, b, probe, bone, t0, t1, nt, gap, thick, material, n=24, bevel=0.002):
    """A tube round `bone` from t0 to t1 hugging the surface `gap(t)` off it (gauntlets, paint bands)."""
    a = b.j(bone, 1) - b.j(bone, 0)
    cs, rings = [], []
    for i in range(nt + 1):
        t = t0 + (t1 - t0) * i / nt
        cc = b.j(bone, t)
        pts, dirs, _ = contour(probe, cc, a, gap(t), n=n, reach=0.3)
        cs.append(cc)
        rings.append([((p - cc).length, d) for p, d in zip(pts, dirs)])
    for _ in range(2):  # no ripples along the bone either
        rings = [[(max(r[j][0], (rings[max(0, i - 1)][j][0] + r[j][0] + rings[min(nt, i + 1)][j][0]) / 3), r[j][1]) for j in range(n)]
                 for i, r in enumerate(rings)]
    bm = bmesh.new()
    vs = [[bm.verts.new(cc + d * rr) for rr, d in ring] for cc, ring in zip(cs, rings)]
    for i in range(nt):
        for j in range(n):
            j1 = (j + 1) % n
            bm.faces.new((vs[i][j], vs[i][j1], vs[i + 1][j1], vs[i + 1][j]))
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    f = bm.faces[0]
    if f.normal.dot(f.calc_center_median() - cs[0]) < 0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    o = kit.hs._obj(name, bm, material, bevel)
    m = o.modifiers.new("thick", "SOLIDIFY")
    m.thickness, m.offset, m.use_rim, m.use_even_offset = thick, 1.0, True, True
    kit.hs._apply(o, m.name)
    return o


def piston(name, p0, p1, r, out, split=0.56):
    """A piston strut from p0 to p1: steel barrel, bright rod, brass gland and collar, eye lugs at both
    ends facing `out` (they sit over the hub bolts)."""
    p0, p1 = Vector(p0), Vector(p1)
    u = (p1 - p0).normalized()
    a, z = p0 + u * 0.022, p1 - u * 0.022
    m = a.lerp(z, split)
    parts = [kit.cyl(name, a, m, r, "steel", segs=14, bevel=0.0015, bsegs=1),
             kit.cyl(name + "_rod", m, z, r * 0.45, "bright", segs=10, bevel=0, bsegs=1),
             kit.cyl(name + "_gland", m - u * 0.012, m + u * 0.004, r * 1.2, "brass", segs=14, bevel=0.0012, bsegs=1),
             kit.cyl(name + "_collar", a + u * 0.01, a + u * 0.022, r * 1.16, "brass", segs=14, bevel=0.001, bsegs=1),
             kit.cyl(name + "_rod_end", z - u * 0.012, z, r * 0.62, "steel", segs=10, bevel=0.001, bsegs=1)]
    for e, f in ((p0, a), (p1, z)):
        parts.append(kit.cyl(name + "_eye", e - Vector(out) * 0.006, e + Vector(out) * 0.006, 0.02, "steel", segs=14, bevel=0.0015, bsegs=1))
        parts.append(kit.cyl(name + "_neck", e + (f - e).normalized() * 0.012, f, r * 0.55, "steel", segs=8, bevel=0, bsegs=1))
    return kit.join(parts, name)


def hub(name, at, out, r=0.034, thick=0.022, bolt="brass"):
    """A pivot hub: a riveted steel disc on a joint axis with a hex bolt."""
    at, out = Vector(at), Vector(out).normalized()
    t1 = out.cross(UP if abs(out.z) < 0.9 else Vector((1, 0, 0))).normalized()
    t2 = out.cross(t1)
    parts = [kit.cyl(name, at - out * thick * 0.5, at + out * thick * 0.5, r, "steel", segs=18, bevel=0.002, bsegs=1),
             kit.cyl(name + "_bolt", at + out * thick * 0.5, at + out * (thick * 0.5 + 0.009), r * 0.36, bolt, segs=6, bevel=0.0008, bsegs=1),
             rivets(name + "_rivets", [(at + out * thick * 0.5 + (t1 * math.cos(q) + t2 * math.sin(q)) * r * 0.72, out)
                                       for q in [i * math.pi / 3 for i in range(6)]], r=0.0042, material="bright", segs=6)]
    return kit.join(parts, name)


def hard_plate(src, cutter, name, material, offset, thick, keep=None, bones=None, bevel=0.0025):
    """kit.plate (decimated) with a single-step bevel: the frame's many plates on a budget."""
    o = kit.plate(src, cutter, name, material, offset=offset, thick=thick, bevel=bevel, keep=keep, bones=bones)
    o["segs"] = 1
    return o


def band(name, c, axis, r, width, material, segs=24):
    """A short closed cylinder round a cylinder of radius < r: boiler bands, saddles, clamps."""
    c, a = Vector(c), Vector(axis).normalized()
    return kit.cyl(name, c - a * width / 2, c + a * width / 2, r, material, segs=segs, bevel=0.001, bsegs=1)


def build():
    b = kit.Build(height=1.92, width=1.15, bulk=1.25)
    c = kit.begin("bruiser", b)
    k, w = b.k, b.width
    hip = b.hip_z
    parts = kit.body(b, skin="skin", gut=0.15, chest=1.1, head=False)
    head = kit.head_mesh(b, "skin", jaw=1.3, brow=1.35, nose=1.12)
    flesh = c.flesh(parts["body"])
    c.add(head, kit.HEAD_BONES)
    hc = b.j("head", 0.45)
    body = Probe(flesh, skip=ARMS)
    face = Probe(head)

    # ---------------------------------------------------------------- head: bald, big ginger beard, brows, a scar
    line = kit.rounded([(-0.036 * k, hc.z + 0.012 * k), (-0.04 * k, hc.z - 0.012 * k), (-0.072 * k, hc.z - 0.036 * k), (-0.2, hc.z - 0.044 * k),
                        (-0.2, hc.z - 0.215 * k), (0.0, hc.z - 0.2 * k), (-0.012 * k, hc.z - 0.11 * k), (-0.016 * k, hc.z - 0.05 * k),
                        (-0.017 * k, hc.z + 0.012 * k)], 0.008)

    def beard_bulk(p):
        chin = smoothstep(hc.z - 0.04 * k, hc.z - 0.11 * k, p.z) * smoothstep(0.0, -0.06 * k, p.y)
        jaw = smoothstep(hc.z - 0.02 * k, hc.z - 0.07 * k, p.z)
        return 0.003 + 0.006 * jaw + 0.024 * chin
    mouth = kit.blob_cutter("mouth", hc + Vector((0, -0.098 * k, -0.066 * k)), (0.017 * k, 0.04, 0.0045 * k))
    beard = hair_cap(head, hc, k, line, beard_bulk, offset=0.001, thick=0.006, grooves=[mouth], material="scrap_ginger", low=0.22)
    c.rigid(beard, "head")
    # Combed strands down the beard, and a big drooping moustache over the mouth.
    bp = Probe(beard)
    strands = []
    for ang in range(-80, 81, 16):
        a2 = math.radians(ang)
        d = Vector((math.sin(a2), -math.cos(a2), 0.0))
        pts = []
        top = hc.z - (0.05 + 0.025 * abs(ang) / 80) * k
        bot = hc.z - (0.2 - 0.07 * abs(ang) / 80) * k
        for i in range(8):
            z = top + (bot - top) * i / 7
            h = bp.hit(Vector((hc.x, hc.y - 0.01 * k, z)) + d * 0.01, d + Vector((0, 0, -0.35)) * (i / 7), 0.25)
            if h:
                pts.append(h[0] + h[1] * 0.0008)
        if len(pts) > 3:
            strands.append(tube_path("beard_strand", pts, 0.0034, "scrap_ginger", segs=5, closed=False, taper=True))
    c.rigid(kit.join(strands, "beard_strands"), "head")
    els = []
    for sx in (1, -1):
        a = face.surf(hc + Vector((0, 0, -0.05 * k)), (0, -1, 0), 0.25) + Vector((0, -0.006, 0))
        m = face.surf(hc + Vector((sx * 0.02 * k, 0, -0.056 * k)), (0, -1, 0), 0.25) + Vector((sx * 0.001, -0.007, 0))
        e = face.surf(hc + Vector((sx * 0.036 * k, 0, -0.08 * k)), (sx * 0.6, -1, 0), 0.25) + Vector((sx * 0.004, -0.008, 0))
        els += [kit.capsule(a, m, 0.0095, r1=0.0085), kit.capsule(m, e, 0.0085, r1=0.0045)]
    c.rigid(kit.meta("moustache", els, "scrap_ginger", res=0.002, target=900, smooth_iter=2), "head")
    for sx in (1, -1):
        pts = []
        for x, dz in ((0.012, 0.02), (0.03, 0.027), (0.05, 0.018)):
            pts.append(face.surf(hc + Vector((sx * x * k, 0, dz * k)), (0, -1, 0), 0.25) + Vector((0, -0.002, 0)))
        c.rigid(kit.rope("brow", pts, 0.0052, "scrap_ginger"), "head")
    scar = []
    for x, y in ((0.012, -0.07), (0.03, -0.045), (0.045, -0.015), (0.052, 0.012)):
        h = face.hit(hc + Vector((x * k, y * k, 0)), (0.3, 0, 1), 0.3)
        if h:
            scar.append(h[0] + h[1] * 0.0006)
    c.rigid(tube_path("scar", scar, 0.0022, "skin_pale", segs=6, closed=False, taper=True), "head")

    # ---------------------------------------------------------------- leather gloves with steel knuckle plates
    hands = parts["hands"]
    hands.data.materials[0] = kit.mat("leather")
    c.add(hands, kit.HAND_BONES)
    hp = Probe(hands)
    for s, sx in (("L", 1), ("R", -1)):
        hb = b.j("hand." + s, 0.0)
        down = (b.j("hand." + s, 1.0) - hb).normalized()
        h = hp.hit(hb + down * 0.06 * k, (sx, 0, 0), 0.15)
        if h:
            o, x, y, z = local(h[0] + Vector((sx, 0, 0)) * 0.002, Vector((sx, 0, 0)))
            pl = kit.block("knuckle_plate", (0, 0.004, 0), (0.07, 0.008, 0.058), "steel", bevel=0.002)
            rv = rivets("knuckle_rivets", [(Vector((xx, 0.008, zz)), Vector((0, 1, 0))) for xx in (-0.026, 0.026) for zz in (-0.021, 0.021)], r=0.0035, material="brass")
            c.rigid(onto(kit.join([pl, rv], "knuckle_plate"), o, x, y, z), "hand." + s)

    # ---------------------------------------------------------------- heavy work shirt and trousers
    wrists = [b.j("hand.L", 0.0), b.j("hand.R", 0.0)]
    neck_top = b.j("neck", 0.2).z
    shirt = kit.shell(flesh, lambda p: hip - 0.06 < p.z < neck_top and all((p - w0).length > 0.05 * k for w0 in wrists), "shirt", "primary",
                      offset=0.013, thick=0.005, smooth_iter=2, bones=TORSO | UPPER_ARMS | FOREARMS | THIGHS | {"neck"}, detail=0.4)
    c.add(shirt)
    c.cover(TORSO | UPPER_ARMS | FOREARMS, lambda p: p.z > hip - 0.03 and all((p - w0).length > 0.085 * k for w0 in wrists))
    neck = Probe(flesh, only={"neck", "chest"})
    c.add(wrap("collar", neck, b.j("neck", 0.25), Vector((0, 0.12, 1)), 0.04, 0.007, "primary", gap=0.019, n=28))
    trousers = kit.shell(flesh, lambda p: 0.12 * k < p.z < hip + 0.085, "trousers", "secondary", offset=0.024, thick=0.005, smooth_iter=3,
                         bones=THIGHS | SHINS | {"hips", "spine"}, detail=0.4)
    transfer_from(c, trousers, flesh, THIGHS | SHINS | {"hips", "spine"})
    c.cover(THIGHS | SHINS | {"hips"}, lambda p: 0.14 * k < p.z < hip + 0.07)
    for s in ("L", "R"):
        sn = "lower_leg." + s
        t = (b.j(sn, 0).z - 0.132 * k) / (b.j(sn, 0).z - b.j(sn, 1).z)
        pts, _, _ = contour(Probe(flesh, only={sn}), b.j(sn, t), b.j(sn, 0) - b.j(sn, 1), 0.031, n=18, reach=0.25)
        c.add(tube_path("trouser_roll", pts, 0.009, "secondary", segs=8), [sn])
    boots(c, b, flesh, cap="steel", top=0.22)

    # ---------------------------------------------------------------- shoulder yokes and caps, harness
    sh = b.j("shoulder.L", 1.0).z
    y_off, y_th = 0.036, 0.009
    yokes, caps = {}, {}
    for s, sx in (("L", 1), ("R", -1)):
        outline = kit.rounded([(sx * 0.082 * w, sh + 0.25), (sx * 0.2 * w, sh + 0.25), (sx * 0.2 * w, sh - 0.062), (sx * 0.15 * w, sh - 0.055), (sx * 0.082 * w, sh - 0.028)], 0.02)
        if sx < 0:
            outline = outline[::-1]
        keep = (lambda p: p.z > sh - 0.13)
        yoke = hard_plate(flesh, kit.slab("yoke_cut", outline, -0.4, 0.4), "yoke", "steel", offset=y_off, thick=y_th, keep=keep, bevel=0.003)
        yp = Probe(yoke)
        spots = []
        for i in range(7):
            x = sx * (0.095 + 0.09 * i / 6) * w
            zl = sh - 0.028 - (0.055 - 0.028) * min(1.0, i / 4.5) + 0.014
            for dy in (-1, 1):
                h = yp.hit(Vector((x, 0, zl)), (0, dy, 0), 0.4)
                if h:
                    spots.append(h)
        if sx > 0:  # hand-painted cog on the left yoke, a skin of the plate itself
            paint = kit.shell(yoke, lambda p: p.y < -0.03, "painted_cog", "yellow", offset=0.0006, thick=0.0009, detail=1.0)
            paint = kit.intersect(paint, kit.slab("cog_cut", cog(0.15 * w, sh - 0.01, 0.03), -0.4, -0.02))
            paint = kit.subtract(paint, kit.cyl("cog_hole", (0.15 * w, -0.4, sh - 0.01), (0.15 * w, 0.0, sh - 0.01), 0.011, "steel", segs=16))
            c.rigid(paint, "chest")
        c.rigid(kit.join([yoke, rivets("yoke_rivets", spots, r=0.0045, material="bright", segs=6)], "yoke"), "chest")
        yokes[s] = yp
        # Steel cap over the deltoid, riveted round its rim.
        ua = "upper_arm." + s
        cc = b.j(ua, 0.1) + Vector((sx * 0.035 * k, 0, 0.005))
        cap = hard_plate(flesh, kit.blob_cutter("cap_cut", cc, (0.085 * k, 0.1 * k, 0.095 * k)), "shoulder_cap", "steel", offset=0.05, thick=0.009,
                         keep=lambda p, sx=sx: p.x * sx > 0.16 * w, bevel=0.003)
        cp = Probe(cap)
        caps[s] = cp
        # Rivets round the lower rim, front through the outside to the back (-90 * sx is straight out).
        spots = [spot(cp, b.j(ua, 0.24), b.j(ua, 1) - b.j(ua, 0), -90 * sx + a2, 0.0) for a2 in range(-75, 76, 25)]
        c.rigid(kit.join([cap, rivets("cap_rivets", spots, r=0.0042, material="bright", segs=6)], "shoulder_cap"), ua)
    # Leather harness down the chest to the waist ring, a chest strap with a buckle.
    hz = b.j("chest", 0.42).z
    for sx in (1, -1):
        g = [(sx * 0.12 * w, -0.1, sh - 0.03), (sx * 0.115 * w, -0.13, hz + 0.05), (sx * 0.105 * w, -0.12, b.j("spine", 0.5).z), (sx * 0.1 * w, -0.11, hip + 0.08)]
        st, _, _ = strap_over("harness", body, g, 0.019, 0.045, 0.005, "accent")
        c.add(st, SPINE)
    g = [(0.15 * w, -0.08, hz), (0.07 * w, -0.13, hz), (0.0, -0.135, hz), (-0.07 * w, -0.13, hz), (-0.15 * w, -0.08, hz)]
    st, pts, ns = strap_over("chest_strap", body, g, 0.025, 0.04, 0.005, "accent")
    c.add(st, SPINE)
    mid = len(pts) // 2
    buckle = kit.block("buckle", (0, 0.004, 0), (0.06, 0.008, 0.05), "brass", bevel=0.0015)
    kit.cut(buckle, kit.block("buckle_hole", (0.006, 0, 0), (0.036, 0.03, 0.032), "steel", bevel=0))
    c.add(onto(kit.join([buckle, kit.block("prong", (0, 0.008, 0), (0.042, 0.004, 0.005), "steel", bevel=0.001)], "buckle"), *local(pts[mid] + ns[mid] * 0.002, ns[mid])), SPINE)

    # ---------------------------------------------------------------- arms: gauntlets, struts, hubs
    for s, sx in (("L", 1), ("R", -1)):
        ua, fa = "upper_arm." + s, "forearm." + s
        ax = b.j(fa, 1) - b.j(fa, 0)
        fpb = Probe(flesh, only={fa})
        gaunt = loft("gauntlet", b, fpb, fa, 0.24, 1.05, 8, lambda t: 0.027 + 0.024 * smoothstep(0.55, 1.05, t), 0.008, "steel", n=18)
        gaunt["segs"] = 1
        gp = Probe(gaunt)
        bits = [gaunt]
        for t in (0.262, 1.03):
            pts, _, _ = contour(gp, b.j(fa, t), ax, 0.001, n=18, reach=0.3)
            bits.append(tube_path("gauntlet_trim", pts, 0.0055, "brass", segs=5))
        spots = []
        for ang in (0, 180, 90 * sx):  # front, back and inner seams (the strut runs down the outside)
            for i in range(5):
                spots.append(spot(gp, b.j(fa, 0.34 + 0.13 * i), ax, ang, 0.0))
        bits.append(rivets("gauntlet_rivets", spots, r=0.0042, material="bright", segs=6))
        if sx < 0:
            for t0 in (0.5, 0.62):  # painted bands
                bits.append(loft("paint_band", b, gp, fa, t0, t0 + 0.06, 1, lambda t: 0.0006, 0.0012, "yellow", n=18, bevel=0.0))
        else:
            p, d = spot(gp, b.j(fa, 0.72), ax, -140, 0.0)
            bits += gauge(p, d, -ax.normalized(), r=0.022, depth=0.012)
            bits.append(kit.cyl("gauge_pipe", p + d * 0.004 - ax.normalized() * 0.02, p + d * 0.004 - ax.normalized() * 0.07, 0.0035, "copper", segs=10, bevel=0))
        c.rigid(kit.join(bits, "gauntlet"), fa)
        # Struts: shoulder hub -> elbow hub on the upper arm, elbow hub -> wrist on the gauntlet.
        out_u, out_f = lateral(b, ua, sx), lateral(b, fa, sx)
        cap_p = caps[s]
        upp = Probe(flesh, only={ua})
        rs = max(reach(b, upp, ua, out_u, 0.0, 0.3), reach(b, cap_p, ua, out_u, 0.0, 0.25)) + 0.02
        re = max(reach(b, upp, ua, out_u, 0.5, 1.0) + 0.04, reach(b, gp, fa, out_f, 0.24, 0.4) + 0.02)
        rw = max(re - 0.01, reach(b, gp, fa, out_f, 0.6, 1.05) + 0.02)
        ps, pe, pw = b.j(ua, 0.0) + out_u * rs, b.j(fa, 0.0) + out_f * re, b.j(fa, 0.95) + out_f * rw
        clamp = wrap("arm_clamp", upp, b.j(ua, 0.55), b.j(ua, 1) - b.j(ua, 0), 0.034, 0.007, "steel", gap=0.02, n=16, bevel=0)
        cpt = b.j(ua, 0.55) + out_u * ((reach(b, upp, ua, out_u, 0.5, 0.6) + 0.024))
        bracket = kit.cyl("clamp_bracket", cpt, ps.lerp(pe, 0.55) - out_u * 0.008, 0.009, "steel", segs=10, bevel=0.001)
        c.rigid(kit.join([hub("shoulder_hub", ps, out_u), piston("arm_strut", ps + out_u * 0.014, pe + out_u * 0.014, 0.017 * k, out_u), clamp, bracket], "arm_frame"), ua)
        c.rigid(kit.join([hub("elbow_hub", pe, out_f), piston("forearm_strut", pe + out_f * 0.03, pw + out_f * 0.012, 0.015 * k, out_f),
                          kit.block("wrist_lug", pw - out_f * 0.008, (0.03, 0.03, 0.03), "steel", bevel=0.003)], "forearm_frame"), fa)
        # Brass union on the yoke where the steam line comes over the shoulder.
        yp = yokes[s]
        top = yp.hit(Vector((sx * 0.17 * w, 0.02, sh)), (0, 0, 1), 0.4)
        if top:
            c.rigid(kit.join([kit.cyl("union", top[0] - top[1] * 0.002, top[0] + top[1] * 0.012, 0.011, "brass", segs=6, bevel=0.001)], "yoke_union"), "chest")

    # ---------------------------------------------------------------- legs: waist ring, hubs, struts, shin guards
    wz = hip + 0.05
    ring = wrap("waist_ring", body, Vector((0, 0, wz)), UP, 0.06, 0.012, "steel", gap=0.031, n=32, reach=0.5)
    rp = Probe(ring)
    spots = []
    for ang in range(0, 360, 15):
        if abs(((ang + 180) % 360) - 180) < 20:
            continue
        for dz in (0.019, -0.019):
            p, d = spot(rp, Vector((0, 0, wz + dz)), UP, ang, 0.0, reach=0.5)
            spots.append((p, d))
    p, d = spot(rp, Vector((0, 0, wz)), UP, 0, 0.0, reach=0.5)
    latch = kit.block("latch", (0, 0.007, 0), (0.07, 0.014, 0.05), "brass", bevel=0.002)
    latch_bar = kit.block("latch_bar", (0, 0.016, 0), (0.05, 0.006, 0.012), "steel", bevel=0.001)
    c.rigid(kit.join([ring, rivets("ring_rivets", spots, r=0.0045, material="bright", segs=6), onto(kit.join([latch, latch_bar], "latch"), *local(p, d))], "waist_ring"), "hips")
    for s, sx in (("L", 1), ("R", -1)):
        th, sn = "upper_leg." + s, "lower_leg." + s
        out_t, out_s = lateral(b, th, sx), lateral(b, sn, sx)
        tpb, spb = Probe(flesh, only={th}), Probe(flesh, only={sn})
        rh = (body.depth(b.j(th, 0.0), out_t, 0.5) or 0.1) + 0.04
        rk = max(reach(b, tpb, th, out_t, 0.5, 1.0), reach(b, spb, sn, out_s, 0.0, 0.3)) + 0.045
        ra = reach(b, spb, sn, out_s, 0.55, 0.8) + 0.042
        ph, pk, pa = b.j(th, 0.0) + out_t * rh, b.j(sn, 0.0) + out_s * rk, b.j(sn, 0.8) + out_s * ra
        c.rigid(kit.join([hub("hip_hub", ph, out_t, r=0.042, thick=0.024),
                          kit.block("hip_mount", ph - out_t * 0.012 + Vector((0, 0, 0.03)), (0.03, 0.05, 0.06), "steel", bevel=0.003)], "hip_hub"), "hips")
        bits = [piston("thigh_strut", ph + out_t * 0.016, pk + out_s * 0.016, 0.02 * k, out_t)]
        for t in (0.33, 0.7):
            bits.append(wrap("thigh_clamp", tpb, b.j(th, t), b.j(th, 0) - b.j(th, 1), 0.036, 0.008, "steel", gap=0.03, n=18, bevel=0))
            cp0 = b.j(th, t) + out_t * (reach(b, tpb, th, out_t, t - 0.05, t + 0.05) + 0.036)
            bits.append(kit.cyl("clamp_bracket", cp0, ph.lerp(pk, t) + out_t * 0.006, 0.01, "steel", segs=10, bevel=0.001))
        c.rigid(kit.join(bits, "thigh_frame"), th)
        bits = [hub("knee_hub", pk, out_s, r=0.038), piston("shin_strut", pk + out_s * 0.03, pa + out_s * 0.012, 0.018 * k, out_s),
                wrap("ankle_clamp", spb, b.j(sn, 0.8), b.j(sn, 0) - b.j(sn, 1), 0.04, 0.009, "steel", gap=0.036, n=18, bevel=0)]
        # Riveted shin guard and knee cop.
        sc = b.j(sn, 0.5)
        guard_line = kit.rounded([(sc.x - 0.052 * k, b.j(sn, 0.8).z), (sc.x + 0.052 * k, b.j(sn, 0.8).z), (sc.x + 0.058 * k, b.j(sn, 0.12).z), (sc.x - 0.058 * k, b.j(sn, 0.12).z)], 0.03)
        guard = hard_plate(flesh, kit.slab("guard_cut", guard_line, -0.4, sc.y - 0.005), "shin_guard", "steel", offset=0.036, thick=0.009, bones={sn})
        gpb = Probe(guard)
        spots = []
        for i in range(4):
            z = b.j(sn, 0.2 + 0.17 * i).z
            for dx in (-0.04, 0.04):
                h = gpb.hit(Vector((sc.x + dx * k, 0, z)), (0, -1, 0), 0.4)
                if h:
                    spots.append(h)
        bits += [guard, rivets("guard_rivets", spots, r=0.0045, material="bright", segs=6)]
        kc = b.j(sn, 0.0) + Vector((0, -0.06 * k, -0.005))
        bits.append(hard_plate(flesh, kit.blob_cutter("cop_cut", kc, (0.06 * k, 0.07 * k, 0.065 * k)), "knee_cop", "steel", offset=0.04, thick=0.009,
                               keep=lambda p: p.y < kc.y + 0.06))
        c.rigid(kit.join(bits, "shin_frame"), sn)

    # ---------------------------------------------------------------- back frame: plate, spine rods, boiler
    z0, z1 = b.j("chest", 0.0).z - 0.02, b.j("chest", 0.86).z
    back_line = kit.rounded([(-0.125 * w, z0), (0.125 * w, z0), (0.125 * w, z1), (-0.125 * w, z1)], 0.03)
    bplate = hard_plate(flesh, kit.slab("back_cut", back_line, 0.0, 0.4), "back_plate", "steel", offset=0.036, thick=0.01)
    bpp = Probe(bplate)
    spots = []
    for i in range(8):
        x = (-0.105 + 0.21 * i / 7) * w
        for z in (z0 + 0.016, z1 - 0.016):
            h = bpp.hit(Vector((x, 0, z)), (0, 1, 0), 0.4)
            if h:
                spots.append(h)
    for i in range(1, 6):
        z = z0 + (z1 - z0) * i / 6
        for x in (-0.109 * w, 0.109 * w):
            h = bpp.hit(Vector((x, 0, z)), (0, 1, 0), 0.4)
            if h:
                spots.append(h)
    frame = [bplate, rivets("plate_rivets", spots, r=0.0045, material="bright", segs=6)]
    zc = (z0 + z1) / 2
    back_y = bpp.hit(Vector((0, 0, zc)), (0, 1, 0), 0.4)[0].y
    R = 0.074 * k
    bc = Vector((0, back_y + R + 0.016, 0))
    zb0, zb1 = z0 + 0.03, z1 + 0.01

    def at(z, r=0.0, ang=0.0):
        """A point on the boiler at height z, radius R + r, `ang` degrees round from straight back."""
        a2 = math.radians(ang)
        return Vector((bc.x + math.sin(a2) * (R + r), bc.y + math.cos(a2) * (R + r), z))
    frame += [kit.cyl("boiler", at(zb0), at(zb1), R, "copper", segs=20, bevel=0.002, bsegs=1),
              kit.cyl("boiler_dome", at(zb1), at(zb1 + 0.032), R, "copper", r1=R * 0.55, segs=20, bevel=0.0015, bsegs=1),
              kit.cyl("boiler_crown", at(zb1 + 0.032), at(zb1 + 0.04), R * 0.55, "brass", r1=R * 0.42, segs=16, bevel=0.001, bsegs=1),
              kit.cyl("boiler_sump", at(zb0 - 0.026), at(zb0), R * 0.7, "copper", r1=R, segs=20, bevel=0.0015, bsegs=1),
              band("boiler_paint", at(zb0 + (zb1 - zb0) * 0.36), UP, R + 0.0012, 0.036, "red", segs=20)]
    spots = []
    for zz in (zb0 + 0.018, zb0 + (zb1 - zb0) * 0.62, zb1 - 0.016):
        frame.append(band("boiler_band", at(zz), UP, R + 0.004, 0.016, "brass", segs=20))
        for i in range(-4, 5):  # the back half only shows
            spots.append((at(zz, 0.004, i * 22.5), Vector((math.sin(math.radians(i * 22.5)), math.cos(math.radians(i * 22.5)), 0))))
    for i in range(1, 7):
        zz = zb0 + (zb1 - zb0) * i / 7
        spots.append((at(zz, 0.0, 28), Vector((math.sin(math.radians(28)), math.cos(math.radians(28)), 0))))
    frame.append(rivets("boiler_rivets", spots, r=0.0042, material="brass", segs=6))
    # Saddle straps holding the boiler to the plate.
    for zz in (zb0 + 0.05, zb1 - 0.05):
        frame.append(band("saddle", at(zz), UP, R + 0.009, 0.02, "steel", segs=20))
        frame.append(kit.block("saddle_foot", (0, back_y + 0.012, zz), (0.07, 0.024, 0.02), "steel", bevel=0.002))
    # Gauge, safety valve, whistle, name plate.
    gd = Vector((math.sin(math.radians(-50)), math.cos(math.radians(-50)), 0.15)).normalized()
    gat = at(zb1 - 0.07, 0.004, -50)
    frame += gauge(gat + gd * 0.012, gd, UP, r=0.028, depth=0.014)
    frame.append(kit.cyl("gauge_stem", gat - gd * 0.004, gat + gd * 0.014, 0.007, "brass", segs=8, bevel=0.0008))
    vt = at(zb1 + 0.04) + Vector((0.02, -0.01, 0))
    frame += [kit.cyl("valve", vt, vt + Vector((0, 0, 0.04)), 0.011, "brass", segs=12, bevel=0.001),
              kit.block("valve_lever", vt + Vector((0.035, 0, 0.042)), (0.08, 0.008, 0.006), "steel", bevel=0.001),
              kit.cyl("valve_weight", vt + Vector((0.07, -0.012, 0.042)), vt + Vector((0.07, 0.012, 0.042)), 0.012, "steel", segs=12, bevel=0.0015),
              kit.cyl("whistle", at(zb1 + 0.04) + Vector((-0.03, 0.0, 0)), at(zb1 + 0.04) + Vector((-0.03, 0.0, 0.05)), 0.009, "brass", r1=0.014, segs=12, bevel=0.001)]
    npos = at(zb0 + (zb1 - zb0) * 0.8, 0.006)
    nplate = kit.block("name_plate", npos, (0.075, 0.004, 0.036), "brass", bevel=0.001)
    frame += [nplate, kit.label_front("No 3", npos + Vector((0, 0.002, 0)), 0.022, "black", depth=0.0015, facing=(0, 1, 0)),
              rivets("plate_rivets", [(npos + Vector((x, 0.002, z)), Vector((0, 1, 0))) for x in (-0.031, 0.031) for z in (-0.012, 0.012)], r=0.0025, material="steel", segs=6)]
    # Firebox under the boiler with a vented door, and the stack up the left.
    fb_top = zb0 - 0.026
    fb = kit.block("firebox", (bc.x, bc.y - 0.006, fb_top - 0.045), (0.13, 0.1, 0.09), "steel", bevel=0.004)
    door = kit.block("firebox_door", (bc.x, bc.y + 0.046, fb_top - 0.045), (0.09, 0.008, 0.062), "black", bevel=0.002)
    kit.cut(door, *[kit.block("vent", (bc.x + x, bc.y + 0.05, fb_top - 0.045), (0.006, 0.02, 0.04), "steel", bevel=0) for x in (-0.03, -0.015, 0.0, 0.015, 0.03)])
    hinge = kit.cyl("door_hinge", (bc.x - 0.048, bc.y + 0.05, fb_top - 0.075), (bc.x - 0.048, bc.y + 0.05, fb_top - 0.015), 0.005, "brass", segs=8, bevel=0)
    frame += [fb, door, hinge, kit.block("door_latch", (bc.x + 0.04, bc.y + 0.054, fb_top - 0.045), (0.008, 0.008, 0.02), "brass", bevel=0.001)]
    sx0 = Vector((-R - 0.02, bc.y, fb_top - 0.02))
    frame += [kit.cyl("stack", sx0, sx0 + Vector((-0.004, 0.006, 0.52 * k)), 0.015, "steel", segs=14, bevel=0.0012),
              kit.cyl("stack_cap", sx0 + Vector((-0.004, 0.006, 0.52 * k)), sx0 + Vector((-0.004, 0.006, 0.56 * k)), 0.016, "steel", r1=0.028, segs=14, bevel=0.0012),
              kit.cyl("stack_top", sx0 + Vector((-0.004, 0.006, 0.56 * k)), sx0 + Vector((-0.004, 0.006, 0.567 * k)), 0.028, "steel", segs=14, bevel=0.001)]
    for zz in (zb0 + 0.04, zb1 - 0.02):
        frame.append(band("stack_clamp", sx0 + Vector((-0.0005, 0.0003, zz - sx0.z)), UP, 0.02, 0.012, "brass", segs=14))
        frame.append(kit.cyl("stack_stay", sx0 + Vector((0.012, 0, zz - sx0.z)), at(zz, -0.004, -90), 0.004, "steel", segs=8, bevel=0))
    # Steam lines over the shoulders to the yoke unions.
    for sx in (1, -1):
        top = yokes["L" if sx > 0 else "R"].hit(Vector((sx * 0.17 * w, 0.02, sh)), (0, 0, 1), 0.4)
        if top:
            a0 = at(zb1 - 0.03, 0.0, 70 * sx)
            path = [a0, a0 + Vector((sx * 0.03, 0.01, 0.0)), Vector((sx * 0.11 * w, back_y + 0.04, sh + 0.02)), top[0] + top[1] * 0.012 + Vector((0, 0.03, 0.02)), top[0] + top[1] * 0.012]
            frame.append(tube_path("steam_line", catmull(path, 0.035), 0.0075, "copper", segs=8, closed=False))
    c.rigid(kit.join(frame, "back_frame"), "chest")
    # Telescoping spine rods from the waist ring up into sleeves on the plate.
    for x in (-0.06 * w, 0.06 * w):
        lo = rp.hit(Vector((x, 0, wz)), (0, 1, 0), 0.5)
        hi = bpp.hit(Vector((x, 0, z0 + 0.03)), (0, 1, 0), 0.5)
        if lo and hi:
            yr = max(lo[0].y, hi[0].y) + 0.014
            c.rigid(kit.join([kit.cyl("spine_rod", (x, yr, wz), (x, yr, z0 + 0.01), 0.0075, "bright", segs=12, bevel=0.0006),
                              kit.block("rod_foot", (x, yr - 0.006, wz), (0.026, 0.02, 0.03), "steel", bevel=0.002)], "spine_rod"), "hips")
            c.rigid(kit.join([kit.cyl("rod_sleeve", (x, yr, z0 - 0.07), (x, yr, z0 + 0.03), 0.013, "steel", segs=14, bevel=0.0012),
                              band("sleeve_collar", (x, yr, z0 - 0.068), UP, 0.016, 0.01, "brass", segs=14)], "rod_sleeve"), "chest")
    return c


SPEC = {"build": build, "faction": "scrappers", "budget": (25000, 75000), "loadout": "fist",
        "colors": {"primary": "#55606a", "secondary": "#4f4536", "accent": "#a0743c"}}
