"""Ghost, Deserters: the light scout. A hooded cloak over a fitted top: a mantle over the shoulders and
a long back hanging to mid-thigh in two halves (split up the back and open at the sides) with a cream
hem band. Under the hood, a cracked bone-white Regime mask: one sensor slit still whole, the other
broken open around the eye with a clay stripe painted over it, cracks, the code half scratched off,
the uplink torn from the temple. A slim chest harness and a climbing harness with carabiners and a
chalk bag, an empty drop-leg holster, taped wrists and soft climbing shoes.

Tints: primary = cloak and top (slate), secondary = trousers (kraft), accent = straps (clay).
"""

import math

import bmesh
from mathutils import Vector

import kit
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS, FEET
from chars.breaker import hit, obox, bolt, cloth, hug, sweep, torso, below, above, bpy_update, scratches

kit.hs.PALETTE["gst_skin"] = ((0.66, 0.50, 0.40), (0.70, 0.54, 0.44), 0.0, 0.6, 0.0, 0)


def drape(name, src, axis, az0, az1, top, bottom, offset, material, scan_top=None, flare=0.0, n_az=16, n_z=16, thick=0.006, grow=0.0):
    """Cloth hanging from the body like a curtain. For each azimuth around the vertical `axis` (0 is
    the back, +Y; 90 the left side, +X) the cloth keeps the widest radius of `src` met on the way
    down from `scan_top`, plus `offset` and `flare` per metre of drop, and runs from `top(az)` down
    to `bottom(az)` (numbers or functions). Sheets with the same scan line up exactly (hem bands)."""
    ax = Vector((axis[0], axis[1], 0))
    top_f = top if callable(top) else (lambda a: top)
    bot_f = bottom if callable(bottom) else (lambda a: bottom)
    z0 = scan_top if scan_top is not None else max(top_f(az0), top_f(az1))
    bpy_update()

    def column(a):
        d = Vector((math.sin(math.radians(a)), math.cos(math.radians(a)), 0))
        prof, best, z = [], 0.0, z0
        while z > bot_f(a) - 0.02:
            o = ax + Vector((0, 0, z))
            ok, loc, _, _ = src.ray_cast(o + d * 0.6, -d)
            best = max(best, (Vector(loc) - o).dot(d) if ok else 0.0)
            prof.append((z, best + offset + flare * (z0 - z)))
            z -= 0.01
        return d, prof

    def radius(prof, z):
        for (za, ra), (zb, rb) in zip(prof, prof[1:]):
            if zb <= z <= za:
                return ra + (rb - ra) * (za - z) / (za - zb)
        return prof[-1][1] if z < prof[-1][0] else prof[0][1]
    azs = [az0 + (az1 - az0) * i / n_az for i in range(n_az + 1)]
    cols = [column(a) for a in azs]
    # Relax the profiles sideways so ridges of the body do not crease the cloth.
    for _ in range(2):
        new = []
        for i, (d, prof) in enumerate(cols):
            nb = [cols[max(i - 1, 0)][1], prof, cols[min(i + 1, n_az)][1]]
            new.append((d, [(z, max(r, sum(radius(q, z) for q in nb) / 3)) for z, r in prof]))
        cols = new
    bm = bmesh.new()
    vs = []
    for a, (d, prof) in zip(azs, cols):
        zt, zb = top_f(a), bot_f(a)
        col = []
        for j in range(n_z + 1):
            z = zt + (zb - zt) * j / n_z
            col.append(bm.verts.new(ax + Vector((0, 0, z)) + d * (radius(prof, z) + grow)))
        vs.append(col)
    for i in range(n_az):
        for j in range(n_z):
            bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = kit.hs._obj(name, bm, material, bevel=0.0)
    if thick:
        m = o.modifiers.new("thick", "SOLIDIFY")
        m.thickness = thick
        m.offset = 0.0
        m.use_rim = True
        kit.hs._apply(o, m.name)
    for poly in o.data.polygons:
        poly.use_smooth = True
    o["shaded"] = True
    return o


def weigh_cloak(c, o, b, side, legs=0.75):
    """Weights for a hanging cloak half: the torso bone it hangs from, and below the hips more and more
    of the thigh on its own `side` ("L" or "R"), so the halves follow the legs."""
    o.vertex_groups.clear()
    groups = {}

    def g(name):
        if name not in groups:
            groups[name] = o.vertex_groups.new(name=name)
        return groups[name]
    for v in o.data.vertices:
        w = kit.weights_at(b, v.co, ["chest", "spine", "hips"], blend=0.08)
        t = max(0.0, min(1.0, (b.hip_z - 0.02 - v.co.z) / 0.3))
        leg = legs * t * t * (3 - 2 * t)
        w = {k: x * (1 - leg) for k, x in w.items()}
        if leg > 0:
            w["upper_leg." + side] = leg
        for name, x in w.items():
            g(name).add([v.index], x, "REPLACE")
    c.parts.append((o, "DONE", None))
    return o


def build():
    b = kit.Build(height=1.74, width=0.94, bulk=0.9)
    c = kit.begin("ghost", b)
    J = b.j
    tk = (b.height - b.hip_z) / 0.85
    sx = b.k * b.width * b.bulk

    def Z(v):
        return v * b.hip_z / 0.95 if v <= 0.95 else b.hip_z + (v - 0.95) * tk

    def rig(o, bone):
        if o is not None:
            c.rigid(o, bone)

    parts = kit.body(b, skin="gst_skin", chest=0.95)
    flesh = c.flesh(parts["body"])
    head = c.add(parts["head"], kit.HEAD_BONES)
    hc = J("head", 0.45)
    wrists = [J("hand.L", 0.0), J("hand.R", 0.0)]

    def off_wrist(p, d=0.03):
        return all((p - w).length > d for w in wrists)

    # ---- bare hands with taped knuckles; wrist wraps
    hands = parts["hands"]
    c.add(hands, kit.HAND_BONES)
    for s in ("L", "R"):
        sg = 1 if s == "L" else -1
        hb = Vector(b.all["hand." + s][0])
        down = (Vector(b.all["hand." + s][1]) - hb).normalized()
        knuckle = hb + down * 0.088 * b.k + Vector((sg * 0.013, -0.002, 0))
        c.rigid(obox("knuckle_tape", knuckle, Vector((0, -1, 0)), Vector((sg, 0, 0)), (0.074, 0.02, 0.006), "cream", bevel=0.0015), "hand." + s)
        ax = J("forearm." + s, 1) - J("forearm." + s, 0)
        side = ax.cross(Vector((0, 1, 0))).normalized()
        for i, t in enumerate((0.6, 0.68, 0.76, 0.84, 0.92, 0.99)):
            tilt = (ax.normalized() + side * (0.18 if i % 2 else -0.18)).normalized()
            c.add(hug("wrap", flesh, J("forearm." + s, t), tilt, 0.003 + 0.0015 * (i % 2), 0.02, 0.004, "cream", n=14), ["forearm." + s, "hand." + s])

    # ---- fitted top: torso and sleeves to the wraps
    cloth(c, flesh, lambda p: p.z > Z(0.88) and off_wrist(p, 0.08), "top", "primary", offset=0.008, thick=0.004, smooth_iter=2,
          bones=TORSO | UPPER_ARMS | FOREARMS | {"neck"}, detail=0.35)
    c.cover(TORSO | UPPER_ARMS | FOREARMS | {"neck"}, lambda p: p.z > Z(0.92) and off_wrist(p, 0.1))

    # ---- trousers, knee patches, cinched ankle cuffs
    cloth(c, flesh, lambda p: Z(0.07) < p.z < Z(1.0), "trousers", "secondary", offset=0.014, thick=0.004, smooth_iter=3,
          bones=THIGHS | SHINS | {"hips"}, detail=0.35, inside=[below(Z(0.985)), above(Z(0.155))])
    c.cover(THIGHS | SHINS | {"hips"}, lambda p: Z(0.17) < p.z < Z(0.97))
    for s, sg in (("L", 1), ("R", -1)):
        knee = J("lower_leg." + s, 0.04)
        patch = [(knee.x - 0.05, knee.z - 0.07), (knee.x + 0.05, knee.z - 0.07), (knee.x + 0.05, knee.z + 0.07), (knee.x - 0.05, knee.z + 0.07)]
        cloth(c, flesh, lambda p, s=s: p.y < 0.0, "knee_patch", "webbing", offset=0.019, thick=0.004, bones={"upper_leg." + s, "lower_leg." + s},
              detail=0.6, inside=[kit.slab("patch_cut", kit.rounded(patch, 0.03), -0.4, 0.0)])
        c.add(hug("ankle_cuff", flesh, J("lower_leg." + s, 0.82), (0, 0, 1), 0.017, 0.03, 0.007, "secondary"), ["lower_leg." + s])

    # ---- soft climbing shoes: slate uppers, rubber rand and sole, clay velcro straps, heel loop
    for s, sg in (("L", 1), ("R", -1)):
        top_z = Z(0.115)
        shoe = kit.shell(flesh, lambda p, sg=sg: p.z < top_z + 0.03 and p.x * sg > 0, "shoe", "slate", offset=0.007, thick=0.005,
                         bones={"foot." + s, "lower_leg." + s}, detail=0.5, inside=[below(top_z)])
        c.add(shoe, ["foot." + s, "lower_leg." + s])
        fx = J("foot." + s, 0.0).x
        c.add(hug("shoe_collar", flesh, Vector((J("lower_leg." + s, 0.0).x, 0.0, top_z - 0.006)), (0, 0, 1), 0.013, 0.014, 0.006, "rubber", n=16),
              ["lower_leg." + s, "foot." + s])
        sole = kit.plan("sole", kit.rounded([(fx - 0.045, 0.075), (fx + 0.045, 0.075), (fx + 0.05, -0.17), (fx - 0.04, -0.17)], 0.035), 0.014, "rubber",
                        z=0.007, bevel=0.003)
        sole["segs"] = 1
        c.rigid(sole, "foot." + s)
        rand = kit.block("toe_rand", (fx + sg * 0.003, -0.148, 0.026), (0.086, 0.05, 0.036), "rubber", bevel=0.012)
        c.rigid(rand, "foot." + s)
        c.rigid(kit.block("heel_rand", (fx, 0.055, 0.03), (0.075, 0.03, 0.04), "rubber", bevel=0.01), "foot." + s)
        c.rigid(kit.block("heel_loop", (fx, 0.072, 0.078), (0.02, 0.008, 0.04), "accent", bevel=0.002), "foot." + s)
        for i, (y, z) in enumerate(((-0.075, 0.072), (-0.035, 0.088))):
            c.rigid(obox("velcro", (fx, y, z), Vector((1, 0, 0)), Vector((0, -0.45 - 0.2 * i, 1)), (0.08, 0.022, 0.006), "accent", bevel=0.0015), "foot." + s)
            c.rigid(kit.block("velcro_tab", (fx + sg * 0.042, y, z - 0.012), (0.008, 0.024, 0.026), "accent", bevel=0.0015), "foot." + s)
    c.cover(FEET | SHINS, lambda p: p.z < Z(0.1))

    # ---- climbing harness: waist belt, leg loops, belay loop, gear loops with carabiners, chalk bag
    bz = Z(0.965)
    c.rigid(hug("harness", flesh, Vector((0, 0.01, bz)), (0, 0, 1), 0.02, 0.042, 0.009, "accent", n=28), "hips")
    front, _ = hit(flesh, (0, 0, bz - 0.01), (0, 1, 0))
    c.rigid(kit.block("harness_buckle", (front.x + 0.03, front.y - 0.03, bz), (0.04, 0.012, 0.03), "gunmetal", bevel=0.003), "hips")
    for s, sg in (("L", 1), ("R", -1)):
        lp = J("upper_leg." + s, 0.2)
        c.add(hug("leg_loop", flesh, lp, (sg * 0.25, 0, 1), 0.017, 0.032, 0.008, "accent", n=18, rmax=0.09), ["upper_leg." + s])
        c.add(kit.strap("riser", [Vector((sg * 0.03, front.y - 0.024, bz - 0.02)), Vector((sg * 0.05, front.y - 0.03, bz - 0.06)),
                                  Vector((lp.x - sg * 0.035, front.y - 0.02, lp.z - 0.01))], 0.02, 0.006, "accent", up=(0, -1, 0)), ["hips", "upper_leg." + s])
    c.rigid(kit.ring("belay_loop", (0, front.y - 0.03, bz - 0.055), (1, 0, 0), 0.03, 0.022, 0.016, "webbing", segs=20), "hips")
    for s, sg in (("L", 1), ("R", -1)):
        a = math.radians(sg * 105)
        d = Vector((math.sin(a), -math.cos(a), 0))
        loc, n = hit(flesh, Vector((0, 0.01, bz)) + d * 0.5, -d)
        gl = loc + n * 0.032 + Vector((0, 0, -0.03))
        t = Vector((0, 0, 1)).cross(n).normalized()
        c.rigid(kit.rope("gear_loop", [gl + t * 0.05 + Vector((0, 0, 0.02)), gl + n * 0.01, gl - t * 0.05 + Vector((0, 0, 0.02))], 0.004, "webbing"), "hips")
        for k, off in enumerate((-0.025, 0.02)):
            p = gl + t * off + n * 0.012
            pts = [p + Vector((0, 0, 0.0)), p + t * 0.012 + Vector((0, 0, -0.015)), p + t * 0.012 + Vector((0, 0, -0.05)), p + Vector((0, 0, -0.06)),
                   p - t * 0.012 + Vector((0, 0, -0.048)), p - t * 0.012 + Vector((0, 0, -0.012)), p + Vector((0, 0, 0.001))]
            c.rigid(kit.rope("carabiner", pts, 0.0035, "clay" if (k + (s == "R")) % 2 else "bright"), "hips")
    # Rope coil clipped on the left hip, chalk bag on the right.
    a = math.radians(118)
    d = Vector((math.sin(a), -math.cos(a), 0))
    loc, n = hit(flesh, Vector((0, 0.01, bz)) + d * 0.5, -d)
    rc = loc + n * 0.05 + Vector((0, 0, -0.11))
    t = Vector((0, 0, 1)).cross(n).normalized()
    for i in range(3):
        o = (i - 1) * 0.012
        ring = [rc + n * o + t * 0.055 * math.cos(math.radians(q)) + Vector((0, 0, 0.075 * math.sin(math.radians(q)))) for q in range(0, 361, 30)]
        c.rigid(kit.rope("rope_coil", ring, 0.007, "canvas"), "hips")
    c.rigid(kit.cyl("coil_tie", rc + Vector((0, 0, 0.06)) - n * 0.03, rc + Vector((0, 0, 0.06)) + n * 0.03, 0.012, "accent", segs=12, bevel=0), "hips")
    a = math.radians(-120)
    d = Vector((math.sin(a), -math.cos(a), 0))
    loc, n = hit(flesh, Vector((0, 0.01, bz - 0.06)) + d * 0.5, -d)
    cb = loc + n * 0.05
    c.rigid(kit.cyl("chalkbag", cb + Vector((0, 0, -0.07)), cb + Vector((0, 0, 0.0)), 0.038, "clay", r1=0.043, segs=18, bevel=0.003), "hips")
    c.rigid(kit.ring("bag_rim", cb + Vector((0, 0, 0.004)), (0, 0, 1), 0.046, 0.036, 0.012, "slate", segs=18), "hips")
    c.rigid(kit.rope("bag_cord", [cb + Vector((0.03, -0.02, 0.008)), cb + Vector((0.04, -0.03, -0.02)), cb + Vector((0.035, -0.035, -0.045))], 0.0022, "cream"), "hips")

    # ---- drop-leg holster on the right thigh (the pistol is in hand)
    th0 = J("upper_leg.R", 0.42)
    loc, n = hit(flesh, th0, (1, 0, 0))
    hp = loc + n * 0.03
    tt = Vector((0, -1, 0))
    c.rigid(obox("holster_plate", hp, tt, n, (0.10, 0.16, 0.008), "webbing", bevel=0.003), "upper_leg.R")
    shell_ = obox("holster", hp + n * 0.024 + Vector((0, -0.005, 0.0)), tt, n, (0.055, 0.14, 0.04), "slate", bevel=0.008)
    kit.cut(shell_, obox("holster_mouth", hp + n * 0.024 + Vector((0, -0.005, 0.07)), tt, n, (0.035, 0.03, 0.026), "steel"), solver="MANIFOLD")
    c.rigid(shell_, "upper_leg.R")
    c.rigid(obox("holster_strap", hp + n * 0.046 + Vector((0, -0.005, 0.035)), tt, n, (0.06, 0.018, 0.004), "accent", bevel=0.001), "upper_leg.R")
    rig(bolt(hp + n * 0.048 + Vector((0, -0.005, 0.035)), n, r=0.006, material="gunmetal", head=0.003), "upper_leg.R")
    for t in (0.3, 0.55):
        c.add(hug("holster_band", flesh, J("upper_leg.R", t), (0, 0, 1), 0.019, 0.026, 0.007, "accent", n=16), ["upper_leg.R"])
    c.add(kit.strap("drop_strap", [Vector((-0.17 * sx, 0.0, bz - 0.02)), hp + Vector((0, 0, 0.09))], 0.03, 0.006, "accent", up=(-1, 0, 0)), ["hips", "upper_leg.R"])

    # ---- slim chest harness: two straps down the chest to the belt, sternum strap, a small pouch
    def chest_line(x0, x1, z0, z1, n=6, grow=0.018):
        pts = []
        for i in range(n + 1):
            t = i / n
            loc, nn = hit(flesh, (x0 + (x1 - x0) * t, 0, z0 + (z1 - z0) * t), (0, 1, 0))
            if loc is not None:
                pts.append(loc + nn * grow)
        return pts
    for sg in (1, -1):
        c.add(kit.strap("chest_strap", chest_line(sg * 0.075 * sx, sg * 0.05 * sx, Z(1.38), bz + 0.02), 0.026, 0.006, "accent", up=(0, -1, 0)))
    st = chest_line(-0.075 * sx, 0.075 * sx, Z(1.255), Z(1.255), n=6)
    c.add(kit.strap("sternum_strap", st, 0.018, 0.005, "accent", up=(0, -1, 0)))
    mid = st[len(st) // 2]
    c.rigid(kit.block("sternum_buckle", mid + Vector((0, -0.006, 0)), (0.035, 0.01, 0.024), "gunmetal", bevel=0.002), "chest")
    loc, nn = hit(flesh, (0.0, 0, Z(1.17)), (0, 1, 0))
    pouch = obox("chest_pouch", loc + nn * 0.035, Vector((1, 0, 0)), nn, (0.1, 0.07, 0.035), "kraft", bevel=0.006)
    c.rigid(pouch, "spine")
    c.rigid(obox("pouch_flap", loc + nn * 0.05 + Vector((0, 0, 0.028)), Vector((1, 0, 0)), nn, (0.104, 0.024, 0.008), "kraft", bevel=0.003), "spine")
    c.rigid(obox("pouch_tab", loc + nn * 0.055 + Vector((0, 0, 0.02)), Vector((1, 0, 0)), nn, (0.02, 0.03, 0.004), "accent", bevel=0.001), "spine")

    # ---- the cloak: a mantle over the shoulders and a long back in two halves
    mantle_cut = kit.blob_cutter("mantle_cut", J("neck", 0.0) + Vector((0, 0.03, -0.01)), (0.33 * sx, 0.24, 0.215))
    cloth(c, flesh, lambda p: p.z > Z(1.12), "mantle", "primary", offset=0.05, thick=0.006, smooth_iter=4, bones=TORSO | UPPER_ARMS | {"neck"},
          detail=0.5, inside=[mantle_cut])
    core = torso(b, chest=0.95, legs=True, target=4000)

    def hem(a):
        return Z(0.70) + 0.05 * (abs(a) / 72.0) ** 1.5
    for side, (a0, a1) in (("L", (0.0, 72.0)), ("R", (-72.0, 0.0))):
        half = drape("cloak_back", core, (0, 0.0), a0, a1, Z(1.37), hem, 0.03, "primary", flare=0.06, n_az=12, n_z=16)
        weigh_cloak(c, half, b, side)
        band = drape("cloak_band", core, (0, 0.0), a0, a1, lambda a: hem(a) + 0.05, lambda a: hem(a) + 0.032, 0.03, "cream", scan_top=Z(1.37),
                     flare=0.06, n_az=12, n_z=1, thick=0.002, grow=0.0042)
        weigh_cloak(c, band, b, side)
    import bpy
    bpy.data.objects.remove(core, do_unlink=True)

    # ---- hood: loose over the head, opening framing the mask
    hood = kit.shell(head, None, "hood", "primary", offset=0.034, thick=0.006, smooth_iter=8, detail=0.6,
                     outside=[kit.blob_cutter("face_hole", hc + Vector((0, -0.118, -0.018)), (0.076, 0.08, 0.1), rot=(-6, 0, 0))])
    kit.place(hood, (0, 0.012, 0.012))
    c.add(hood, kit.HEAD_BONES)

    # ---- the cracked Regime mask
    eye = {sg: hc + Vector((sg * 0.034, -0.066, 0.003)) for sg in (1, -1)}
    outline = kit.rounded([(-0.07, hc.z + 0.05), (0.07, hc.z + 0.05), (0.074, hc.z - 0.02), (0.05, hc.z - 0.085), (0.022, hc.z - 0.11),
                           (-0.022, hc.z - 0.11), (-0.05, hc.z - 0.085), (-0.074, hc.z - 0.02)], 0.02)
    mkeep = (lambda p: p.y < hc.y - 0.02)
    mask = kit.shell(head, mkeep, "mask", "bone", offset=0.011, thick=0.007, smooth_iter=6, detail=1.0,
                     inside=[kit.slab("mask_cut", outline, -0.4, hc.y - 0.02)])
    # The broken slit: a jagged hole torn open around the left eye.
    ex, ez = eye[1].x, eye[1].z
    jag = [(ex - 0.022, ez + 0.004), (ex - 0.012, ez + 0.016), (ex - 0.004, ez + 0.009), (ex + 0.006, ez + 0.022), (ex + 0.014, ez + 0.01),
           (ex + 0.026, ez + 0.012), (ex + 0.021, ez - 0.002), (ex + 0.03, ez - 0.012), (ex + 0.012, ez - 0.014), (ex + 0.004, ez - 0.026),
           (ex - 0.006, ez - 0.013), (ex - 0.02, ez - 0.016), (ex - 0.016, ez - 0.004)]
    kit.cut(mask, kit.slab("broken_slit", jag, -0.4, hc.y), solver="MANIFOLD")
    # The whole slit on the right, a breathing grille, cracks running out of the hole.
    rx, rz = eye[-1].x, eye[-1].z
    kit.cut(mask, kit.slab("slit", kit.rounded([(rx - 0.022, rz - 0.004), (rx + 0.02, rz - 0.004), (rx + 0.02, rz + 0.004), (rx - 0.022, rz + 0.004)], 0.003),
                           -0.4, hc.y), solver="MANIFOLD")
    kit.cut(mask, *[kit.slab("grille", [(-0.018 + 0.002 * abs(i), hc.z - 0.062 - 0.009 * i), (0.018 - 0.002 * abs(i), hc.z - 0.062 - 0.009 * i),
                                        (0.018 - 0.002 * abs(i), hc.z - 0.0585 - 0.009 * i), (-0.018 + 0.002 * abs(i), hc.z - 0.0585 - 0.009 * i)], -0.4, hc.y)
                    for i in range(3)], solver="MANIFOLD")
    for path in (((ex + 0.03, ez - 0.012), (ex + 0.04, ez - 0.022), (ex + 0.037, ez - 0.034), (ex + 0.045, ez - 0.05)),
                 ((ex - 0.004, ez - 0.026), (ex - 0.008, ez - 0.04), (ex + 0.0, ez - 0.055), (ex - 0.006, ez - 0.07)),
                 ((ex + 0.006, ez + 0.022), (ex + 0.0, ez + 0.032), (ex + 0.008, ez + 0.042))):
        pts, ns = [], []
        for x, z in path:
            loc, nn = hit(mask, (x, 0, z), (0, 1, 0))
            if loc is not None:
                pts.append(loc)
                ns.append(nn)
        if len(pts) >= 2:
            kit.cut(mask, sweep("crack", pts, ns, 0.0022, 0.008, "steel"), solver="MANIFOLD")
    scratches(mask, [(Vector((x, 0, hc.z + z)), a, 0.03) for x, z, a in ((-0.05, -0.03, 30), (-0.045, -0.045, 25), (0.04, -0.075, -40))], (0, 1, 0), depth=0.004)
    mask["bevel"] = 0.0015
    mask["shaded"] = False
    c.rigid(mask, "head")
    # Clay stripe painted down over the broken eye, around the hole.
    stripe = [(ex - 0.014, hc.z + 0.06), (ex + 0.016, hc.z + 0.06), (ex + 0.019, hc.z - 0.04), (ex + 0.012, hc.z - 0.075), (ex - 0.01, hc.z - 0.07),
              (ex - 0.016, hc.z - 0.03)]
    paint = kit.shell(head, mkeep, "mask_stripe", "clay", offset=0.011 + 0.007 + 0.0008, thick=0.0014, smooth_iter=6, detail=1.0,
                      inside=[kit.slab("mask_cut2", outline, -0.4, hc.y - 0.02), kit.slab("stripe_cut", stripe, -0.4, hc.y - 0.02)],
                      outside=[kit.slab("hole2", [(x * 1.12 - ex * 0.12, z * 1.12 - ez * 0.12) for x, z in jag], -0.4, hc.y)])
    c.rigid(paint, "head")
    # Dark lens behind the whole slit; the left eye shows through the hole.
    loc, nn = hit(head, (rx, 0, rz), (0, 1, 0))
    c.rigid(obox("lens", loc + nn * 0.006, Vector((1, 0, 0)), nn, (0.046, 0.014, 0.002), "glass"), "head")
    # Leftover code on the right cheek, half scratched off.
    for txt, dz in (("01 101", -0.03), ("1 0 11", -0.042)):
        loc, nn = hit(mask, (-0.045, 0, hc.z + dz), (0, 1, 0))
        if loc is not None:
            lab = kit.label_front(txt, (0, 0, 0), 0.008, "ink", depth=0.0008)
            yaw = math.degrees(math.atan2(nn.x, -nn.y))
            kit.place(lab, loc + nn * 0.0004, (0, 0, yaw))
            c.rigid(lab, "head")
    # The uplink torn from the right temple: a boss, a snapped stub, a cut wire.
    loc, nn = hit(mask, (-0.07, 0, hc.z + 0.035), (0, 1, 0))
    if loc is not None:
        c.rigid(kit.cyl("uplink_boss", loc - nn * 0.003, loc + nn * 0.008, 0.011, "bone", segs=14, bevel=0.0015), "head")
        c.rigid(kit.cyl("uplink_stub", loc + nn * 0.006, loc + nn * 0.016 + Vector((-0.004, 0, 0.012)), 0.004, "gunmetal", segs=8, bevel=0), "head")
        c.rigid(kit.rope("uplink_wire", [loc + nn * 0.006, loc + nn * 0.01 + Vector((-0.012, 0, -0.008)), loc + nn * 0.008 + Vector((-0.016, 0.004, -0.03))],
                         0.0018, "copper"), "head")
    # Mask straps running back under the hood, riveted to the mask.
    for sg in (1, -1):
        for dz in (0.028, -0.06):
            loc, nn = hit(mask, (sg * 0.066, 0, hc.z + dz), (0, 1, 0))
            if loc is None:
                continue
            rig(bolt(loc, nn, r=0.0045, material="gunmetal", head=0.0025), "head")
            p1 = hc + Vector((sg * 0.088, -0.035, dz * 0.8))
            p2 = hc + Vector((sg * 0.094, 0.0, dz * 0.6))
            c.rigid(kit.strap("mask_strap", [loc + nn * 0.001, p1, p2], 0.014, 0.003, "webbing", up=(sg, 0, 0)), "head")
    return c


SPEC = {"build": build, "faction": "deserters", "budget": (25000, 75000), "loadout": "pistol",
        "colors": {"primary": "#141413", "secondary": "#D4A27F", "accent": "#D97757"}}
