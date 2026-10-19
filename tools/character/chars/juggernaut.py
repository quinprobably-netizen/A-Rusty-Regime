"""Juggernaut, PMC: HALCYON's heavy assault contractor in full plate. A sealed white helmet with a
wraparound smoked visor (faceless), comms modules, a crest and a rear battery; a two-ring gorget; a
layered white-on-navy chest plate carrying the company mark, articulated abdominal lames, a back plate
with a power unit and two spare rockets; big layered pauldrons, rerebraces, elbow cops and vambraces;
tassets, cuisses, knee cops and greaves over a navy undersuit; heavy boots with armoured toes.

Tints: primary = undersuit (torso and arms), secondary = undersuit legs, accent = plate straps.
"""

import math

from mathutils import Matrix, Vector

import kit
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS, FEET
from chars.contractor import (band, boot, cloth, dome, economise, fit, frame, grow, half_space, hazard_band, hexagon, hit, logo,
                              name_patch, panel, put, radial, rigid_all, ring_pts, rrect, screws, side_buckle, smooth_path, sweep, text,
                              to_world, tree, wrap)

WHITE, NAVY = "pmc_plate", "pmc_navy_hard"


def limb_patch(c, name, a, b, r0, r1, phi0, phi1, thick, material, bone, **kw):
    return c.rigid(wrap(name, a, b, r0, r1, phi0, phi1, thick, material, **kw), bone)


def build():
    b = kit.Build(height=1.95, width=1.15, bulk=1.2)
    c = kit.begin("juggernaut", b)
    parts = kit.body(b, skin="skin", head=False, neck=1.1)
    flesh = c.flesh(parts["body"])
    tf = tree(flesh)
    hc = b.j("head", 0.45)
    J = b.j
    wrists = [J("hand.L", 0.0), J("hand.R", 0.0)]

    def off_wrist(p, d=0.03):
        return all((p - w).length > d for w in wrists)

    # ---------------------------------------------------------------- undersuit
    neck_cut = kit.cyl("neck_cut", (0, 0.004, 1.565), (0, 0.004, 1.9), 0.09, "steel", segs=32, bevel=0)
    wrist_cuts = [half_space("wrist_cut", J("forearm." + s, 0.84), J("hand." + s, 0.0) - J("forearm." + s, 0.0), size=0.2) for s in ("L", "R")]
    suit = kit.shell(flesh, lambda p: 0.93 < p.z < 1.66 and off_wrist(p, 0.03), "undersuit", "primary", offset=0.012, thick=0.004,
                     smooth_iter=2, detail=0.35, outside=[neck_cut] + wrist_cuts)
    cloth(c, suit)
    c.cover(TORSO | UPPER_ARMS | FOREARMS, lambda p: 0.98 < p.z < 1.56 and off_wrist(p, 0.07))
    c.cover(TORSO | THIGHS, lambda p: 0.93 < p.z < 1.2)
    c.cover(FOREARMS, lambda p: not off_wrist(p, 0.05))
    legs = kit.shell(flesh, lambda p: 0.11 < p.z < 1.12, "undersuit_legs", "secondary", offset=0.012, thick=0.003, smooth_iter=3, detail=0.4,
                     bones=THIGHS | SHINS | TORSO, inside=[half_space("waist", (0, 0, 1.075), (0, 0, -1)), half_space("hem", (0, 0, 0.24), (0, 0, 1))])
    cloth(c, legs)
    c.cover(THIGHS | SHINS | {"hips"}, lambda p: 0.2 < p.z < 1.07)
    belt = sweep("belt", ring_pts(tf, (0, -0.004), 1.06, 0.03, n=32), 0.05, 0.012, "webbing", radial((0, -0.004, 0)), closed=True)
    c.add(belt, ["hips", "spine", "upper_leg.L", "upper_leg.R"])

    # Gloves: black, armoured knuckles and back-of-hand plates, gauntlet cuffs.
    hands = parts["hands"]
    hands.data.materials[0] = kit.mat("black")
    c.add(hands, kit.HAND_BONES)
    for s, sx in (("L", 1), ("R", -1)):
        hb = Vector(b.all["hand." + s][0])
        down = (Vector(b.all["hand." + s][1]) - hb).normalized()
        fax = J("hand." + s, 0.0) - J("forearm." + s, 0.0)
        knuckle = hb + down * 0.1 + Vector((sx * 0.014, -0.002, 0))
        g = kit.block("knuckle", (0, 0, 0), (0.02, 0.086, 0.03), NAVY, bevel=0.003)
        kit.cut(g, *[kit.block("groove", (sx * 0.011, y, 0), (0.006, 0.0035, 0.036), "steel", bevel=0) for y in (-0.021, 0.0, 0.021)])
        g.data.transform(Matrix.Translation(knuckle))
        c.rigid(g, "hand." + s)
        bh = kit.block("hand_plate", hb + down * 0.05 + Vector((sx * 0.026, 0, 0)), (0.012, 0.06, 0.07), WHITE, bevel=0.003)
        c.rigid(bh, "hand." + s)
        c.rigid(band("gauntlet", J("hand." + s, 0.0) - fax.normalized() * 0.015, (0.05, 0.045), 0.075, 0.01, NAVY, axis=fax), "hand." + s)

    # ---------------------------------------------------------------- helmet (faceless, rigid to the head)
    el = [kit.ellipsoid(hc + Vector((0, 0.004, 0.03)), 1.0, (0.128, 0.142, 0.136)),
          kit.ellipsoid(hc + Vector((0, -0.03, -0.058)), 1.0, (0.112, 0.118, 0.105)),
          kit.ellipsoid(hc + Vector((0, 0.045, -0.06)), 1.0, (0.118, 0.108, 0.1))]
    helm = kit.meta("helmet", el, WHITE, res=0.006, target=4200, smooth_iter=6)
    helm = kit.intersect(helm, half_space("helm_bottom", hc + Vector((0, 0, -0.14)), (0, 0, 1)))
    # Wraparound visor: a recess cut round the face, smoked glass set into it over a black gasket.
    Rv = 0.10
    vis = kit.rounded([(-0.09, hc.z + 0.036), (0.09, hc.z + 0.036), (0.1, hc.z - 0.004), (0.058, hc.z - 0.042), (-0.058, hc.z - 0.042),
                       (-0.1, hc.z - 0.004)], 0.016)
    Mv = frame((0, hc.y - 0.12, 0), (0, -1, 0))
    cutter = panel("visor_cut", grow(vis, 0.005), 0.003, 0.2, "steel", bevel=0)
    put([cutter], Mv, Rv, step=0.01)
    kit.cut(helm, cutter, solver="EXACT")
    helm["shaded"] = False
    c.rigid(helm, "head")
    th = tree(helm)
    vparts = [panel("visor", vis, 0.0, 0.006, "glass", bevel=0.002), panel("gasket", grow(vis, 0.004), 0.002, 0.002, "black", bevel=0.0)]
    put(vparts, Mv, Rv, step=0.01)
    rigid_all(c, vparts, "head")
    # Crest: a navy ridge down the middle with a yellow stripe.
    crest = kit.shell(helm, lambda p: p.z > hc.z - 0.02, "crest", NAVY, offset=0.0, thick=0.008, detail=1.0,
                      inside=[kit.block("crest_cut", (0, 0.0, hc.z + 0.12), (0.06, 0.5, 0.3), "steel", bevel=0),
                              kit.blob_cutter("crest_end", hc + Vector((0, 0.0, 0.15)), (0.3, 0.19, 0.15))])
    c.rigid(crest, "head")
    stripe = kit.shell(helm, lambda p: p.z > hc.z - 0.02, "crest_stripe", "hazard", offset=0.008, thick=0.003, detail=1.0,
                       inside=[kit.block("stripe_cut", (0, 0.0, hc.z + 0.12), (0.016, 0.5, 0.3), "steel", bevel=0),
                               kit.blob_cutter("stripe_end", hc + Vector((0, 0.0, 0.155)), (0.3, 0.188, 0.15))])
    c.rigid(stripe, "head")
    # Comms modules over the ears: navy drums, grey caps with the mark and screws, antenna on the left.
    for s, sx in (("L", 1), ("R", -1)):
        X = Vector((sx, 0, 0))
        cc = hc + Vector((sx * 0.116, 0.006, -0.016))
        c.rigid(kit.cyl("ear_module", cc - X * 0.012, cc + X * 0.024, 0.05, NAVY, segs=24, bevel=0.004), "head")
        c.rigid(kit.cyl("ear_cap", cc + X * 0.024, cc + X * 0.03, 0.038, "grey", segs=24, bevel=0.0015), "head")
        Me = frame(cc + X * 0.03, X, (0, 0, 1))
        objs = logo(0, 0, 0.042, 0.0, base="white", inset=NAVY, mark="hazard")
        objs += screws([(0.03 * math.cos(math.radians(a)), 0.03 * math.sin(math.radians(a))) for a in (45, 135, 225, 315)], 0.0, r=0.0032)
        put(objs, Me)
        rigid_all(c, objs, "head")
        c.rigid(kit.block("module_mount", cc + Vector((sx * 0.004, 0.0, 0.052)), (0.026, 0.05, 0.02), NAVY, bevel=0.003), "head")
        if s == "L":
            c.rigid(kit.cyl("antenna_base", cc + Vector((0.008, 0.03, 0.04)), cc + Vector((0.01, 0.04, 0.06)), 0.007, "black", segs=12, bevel=0.001), "head")
            c.rigid(kit.cyl("antenna", cc + Vector((0.01, 0.04, 0.06)), cc + Vector((0.02, 0.085, 0.2)), 0.0035, "rubber", r1=0.0022, segs=8, bevel=0), "head")
    # Chin vents and rear battery.
    loc, nor = hit(th, hc + Vector((0, -0.5, -0.075)), (0, 1, 0))
    Mc = frame(loc + Vector((0, 0.003, 0)), Vector((0, -1, -0.35)), (0, 0, 1))
    chin = panel("chin_grill", rrect(-0.042, -0.022, 0.042, 0.022, 0.01), 0.0, 0.008, "grey", bevel=0.002)
    kit.cut(chin, *[kit.block("vent", (0, -0.008, z), (0.064, 0.008, 0.0045), "steel", bevel=0) for z in (-0.011, 0.0, 0.011)])
    cobjs = [chin] + screws([(-0.034, 0.0), (0.034, 0.0)], -0.008, r=0.003)
    put(cobjs, Mc, 0.07)
    rigid_all(c, cobjs, "head")
    loc, nor = hit(th, hc + Vector((0, 0.5, -0.02)), (0, -1, 0))
    Mb = frame(loc + Vector((0, -0.004, 0)), (0, 1, 0), (0, 0, 1))
    batt = kit.block("battery", (0, -0.02, 0), (0.09, 0.04, 0.07), NAVY, bevel=0.004)
    kit.cut(batt, *[kit.block("rib", (0, -0.04, z), (0.1, 0.006, 0.005), "steel", bevel=0) for z in (-0.02, -0.008, 0.004)])
    bobjs = [batt, kit.block("led", (0.03, -0.0405, 0.022), (0.012, 0.003, 0.006), "glow_cyan", bevel=0.0)]
    bobjs += hazard_band(-0.04, 0.04, 0.026, 0.034, -0.04)
    put(bobjs, Mb)
    rigid_all(c, bobjs, "head")

    # ---------------------------------------------------------------- gorget
    c.rigid(wrap("gorget_low", Vector((0, 0.006, 1.5)), Vector((0, 0.006, 1.588)), 0.158, 0.122, -180, 180, 0.014, NAVY, nt=3, nphi=28, bevel=0.004), "chest")
    c.rigid(wrap("gorget_high", Vector((0, 0.006, 1.572)), Vector((0, 0.006, 1.662)), 0.118, 0.099, -180, 180, 0.012, WHITE, nt=3, nphi=28, bevel=0.004), "chest")

    # ---------------------------------------------------------------- chest, abdomen, back
    R = 0.34
    out_c = kit.rounded([(-0.168, 1.255), (0.168, 1.255), (0.176, 1.45), (0.115, 1.552), (0.05, 1.556), (0.0, 1.53), (-0.05, 1.556), (-0.115, 1.552),
                         (-0.176, 1.45)], 0.025)
    MF = fit(tf, out_c, R, 0.032, side=-1, tilt=4)
    front = [panel("chest_base", grow(out_c, 0.008), 0.0, 0.022, NAVY, bevel=0.006),
             panel("chest_plate", out_c, -0.016, 0.018, WHITE, bevel=0.007)]
    y = -0.034
    front += logo(0, 1.425, 0.112, y, base=NAVY, inset="black", mark="hazard")
    front += [text("HALCYON", 0, 1.335, 0.03, y, NAVY, depth=0.0012)]
    front += hazard_band(-0.13, 0.13, 1.272, 1.29, y)
    front += screws([(-0.15, 1.3), (0.15, 1.3), (-0.13, 1.5), (0.13, 1.5)], y, r=0.0045)
    put(front, MF, R)
    rigid_all(c, front, "chest")
    # Abdominal lames: three overlapping bands, each upper one over the next.
    lames = [((1.175, 1.262), "chest"), ((1.105, 1.19), "spine"), ((1.035, 1.12), "hips")]
    union = rrect(-0.135, 1.035, 0.135, 1.262, 0.02)
    MA = fit(tf, union, 0.3, 0.03, side=-1)
    for i, ((z0, z1), bone) in enumerate(lames):
        Mi = Matrix.Translation((0, -0.012 * (2 - i), 0)) @ MA
        lo = [panel("lame", kit.rounded([(-0.13 + 0.008 * i, z0), (0.13 - 0.008 * i, z0), (0.135 - 0.008 * i, z1), (-0.135 + 0.008 * i, z1)], 0.018), 0.0, 0.016,
                    NAVY if i != 1 else WHITE, bevel=0.005)]
        lo += screws([(-0.11 + 0.008 * i, (z0 + z1) / 2), (0.11 - 0.008 * i, (z0 + z1) / 2)], -0.016, r=0.004)
        if i == 1:
            lo += [text("ARGENT-7", 0, (z0 + z1) / 2, 0.022, -0.016, "black", depth=0.001)]
        put(lo, Mi, 0.3)
        rigid_all(c, lo, bone)
    # Side straps from the chest plate to the back plate.
    for s, sx in (("L", 1), ("R", -1)):
        for z in (1.29, 1.36):
            pts = [Vector((sx * 0.172 * math.sin(math.radians(a)), -0.004 - 0.135 * math.cos(math.radians(a)), z)) for a in range(50, 131, 10)]
            c.rigid(sweep("side_strap", smooth_path(pts, 2), 0.035, 0.01, "accent", radial((0, -0.004, 0))), "chest")
            c.rigid(side_buckle("side_buckle", Vector((sx * 0.172, -0.004, z)) + Vector((sx * 0.007, 0, 0)), (0, 1, 0), (sx, 0, 0), w=0.03), "chest")
    # Back plate and power unit with two spare rockets.
    out_b = kit.rounded([(-0.17, 1.14), (0.17, 1.14), (0.175, 1.46), (0.11, 1.552), (-0.11, 1.552), (-0.175, 1.46)], 0.03)
    MB = fit(tf, out_b, R, 0.032, side=1, tilt=4)
    plates = [panel("back_base", grow(out_b, 0.008), 0.0, 0.02, NAVY, bevel=0.006), panel("back_plate", out_b, -0.014, 0.016, WHITE, bevel=0.006)]
    put(plates, MB, R)
    rigid_all(c, plates, "chest")
    back = []
    yb = -0.03
    unit = kit.block("power_unit", (0, yb - 0.045, 1.33), (0.22, 0.09, 0.27), NAVY, bevel=0.01)
    kit.cut(unit, *[kit.block("vent", (x, yb - 0.09, z), (0.028, 0.008, 0.006), "steel", bevel=0) for x in (-0.06, -0.025, 0.01) for z in (1.37, 1.39, 1.41, 1.43)])
    back += [unit, kit.block("unit_lid", (0, yb - 0.048, 1.472), (0.2, 0.08, 0.02), WHITE, bevel=0.005)]
    back += [kit.cyl("unit_port", (0.06, yb - 0.09, 1.4), (0.06, yb - 0.1, 1.4), 0.018, "grey", segs=16, bevel=0.002),
             kit.block("unit_led", (0.06, yb - 0.091, 1.365), (0.03, 0.003, 0.006), "glow_cyan", bevel=0.0)]
    back += hazard_band(-0.1, 0.1, 1.215, 1.235, yb - 0.09)
    back += name_patch("VANTA LOGISTICS", 0, 1.29, 0.16, 0.026, yb - 0.09, base="white", ink="black", size=0.0135)
    back += screws([(x, z) for x in (-0.095, 0.095) for z in (1.22, 1.44)], yb - 0.09, r=0.0045)
    for sx in (1, -1):
        x = sx * 0.135
        tube = kit.cyl("rocket_tube", (x, yb - 0.06, 1.13), (x, yb - 0.06, 1.62), 0.042, "olive", segs=20, bevel=0.003)
        back += [tube, kit.cyl("tube_cap", (x, yb - 0.06, 1.62), (x, yb - 0.06, 1.645), 0.046, "black", segs=20, bevel=0.003),
                 kit.cyl("tube_cap", (x, yb - 0.06, 1.105), (x, yb - 0.06, 1.13), 0.046, "black", segs=20, bevel=0.003),
                 kit.cyl("tube_band", (x, yb - 0.06, 1.28), (x, yb - 0.06, 1.305), 0.045, "hazard", segs=20, bevel=0.0015),
                 kit.cyl("tube_band", (x, yb - 0.06, 1.48), (x, yb - 0.06, 1.505), 0.045, "black", segs=20, bevel=0.0015)]
    put(back, MB, None)
    rigid_all(c, back, "chest")

    # ---------------------------------------------------------------- pauldrons and arms
    for s, sx in (("L", 1), ("R", -1)):
        ua0, ua1 = J("upper_arm." + s, 0.0), J("upper_arm." + s, 1.0)
        out = 90 * sx
        cap_c = J("upper_arm." + s, 0.06) + Vector((sx * 0.004, 0.0, 0.0))
        Mcap = Matrix.Translation(cap_c) @ Matrix.Rotation(math.radians(24 * sx), 4, "Y")
        lo_, hi_ = (-115, 115) if sx > 0 else (65, 295)
        c.rigid(dome("pauldron", Mcap, (0.128, 0.138, 0.112), 8, 90, 0.016, WHITE, lon0=lo_, lon1=hi_, nlat=7, nlon=20, bevel=0.005), "shoulder." + s)
        c.rigid(dome("pauldron_trim", Mcap, (0.146, 0.156, 0.128), 4, 16, 0.006, "hazard", lon0=lo_, lon1=hi_, nlat=1, nlon=20, bevel=0.0015), "shoulder." + s)
        # Two lames under the cap that move with the arm.
        limb_patch(c, "pauldron_lame", ua0 + (ua0 - ua1).normalized() * 0.01, ua0.lerp(ua1, 0.2), 0.118, 0.112, out - 95, out + 95, 0.012, NAVY,
                   "upper_arm." + s, nt=2, nphi=14, bevel=0.004)
        limb_patch(c, "pauldron_lame", ua0.lerp(ua1, 0.16), ua0.lerp(ua1, 0.36), 0.108, 0.1, out - 90, out + 90, 0.012, WHITE,
                   "upper_arm." + s, nt=2, nphi=14, bevel=0.004)
        # The lower lame carries a patch: ARGENT-7 on the left, the mark on the right.
        ax = (ua0 - ua1).normalized()
        n = Vector((sx, 0, 0))
        n = (n - ax * n.dot(ax)).normalized()
        centre = ua0.lerp(ua1, 0.26)
        Mp = frame(centre + n * 0.112, n, ax)
        objs = name_patch("ARGENT-7", 0, 0, 0.07, 0.024, 0.0, base="black", ink="white", size=0.0125) if s == "L" else logo(0, 0, 0.05, 0.0)
        put(objs, Mp, 0.112)
        rigid_all(c, objs, "upper_arm." + s)
        # Rerebrace, elbow cop, vambrace with a navy ridge.
        limb_patch(c, "rerebrace", ua0.lerp(ua1, 0.42), ua0.lerp(ua1, 0.86), 0.088, 0.082, out - 70, out + 70, 0.012, NAVY, "upper_arm." + s, nt=6, nphi=10,
                   bevel=0.004, round_ends=3)
        fa0, fa1 = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        fx = (fa1 - fa0).normalized()
        limb_patch(c, "elbow_cop", fa0 - fx * 0.05, fa0 + fx * 0.06, 0.074, 0.07, 180 - 70 * sx, 180 + 70 * sx, 0.014, WHITE, "forearm." + s,
                   nt=4, nphi=10, bevel=0.005, bulge=0.012)
        limb_patch(c, "vambrace", fa0.lerp(fa1, 0.2), fa0.lerp(fa1, 0.82), 0.072, 0.062, out - 105 * sx, out + 75 * sx, 0.013, WHITE, "forearm." + s,
                   nt=7, nphi=12, bevel=0.005, bulge=0.004, round_ends=3)
        limb_patch(c, "vambrace_ridge", fa0.lerp(fa1, 0.24), fa0.lerp(fa1, 0.78), 0.083, 0.073, out - 12, out + 12, 0.008, NAVY, "forearm." + s,
                   nt=3, nphi=2, bevel=0.002, bulge=0.004)
        for t in (0.3, 0.7):
            c.rigid(screw_on(fa0.lerp(fa1, t), n, 0.084 + 0.004 * (1 - t)), "forearm." + s)

    # ---------------------------------------------------------------- legs
    for s, sx in (("L", 1), ("R", -1)):
        ul0, ul1 = J("upper_leg." + s, 0.0), J("upper_leg." + s, 1.0)
        ll0, ll1 = J("lower_leg." + s, 0.0), J("lower_leg." + s, 1.0)
        out = 90 * sx
        leg = "upper_leg." + s
        # Tasset hanging from the belt, cuisse over the thigh, a strap.
        limb_patch(c, "tasset", ul0 + Vector((0, 0, 0.02)), ul0.lerp(ul1, 0.27), 0.132, 0.127, out - 100 * sx, out + 10 * sx, 0.013, WHITE, leg,
                   nt=6, nphi=12, bevel=0.005, round_ends=3)
        limb_patch(c, "cuisse", ul0.lerp(ul1, 0.32), ul0.lerp(ul1, 0.8), 0.13, 0.112, -75, 75, 0.014, NAVY, leg, nt=7, nphi=12, bevel=0.005, bulge=0.008,
                   round_ends=3)
        limb_patch(c, "cuisse_plate", ul0.lerp(ul1, 0.4), ul0.lerp(ul1, 0.72), 0.147, 0.135, -40, 40, 0.008, WHITE, leg, nt=6, nphi=8, bevel=0.003,
                   bulge=0.008, round_ends=3)
        p = ul0.lerp(ul1, 0.35)

        def sr(a):
            a = abs(((a + 180) % 360) - 180)
            return 0.142 if a <= 80 else 0.142 - 0.029 * min(1.0, (a - 80) / 40)
        c.rigid(sweep("thigh_strap", [p + Vector((sr(a) * math.sin(math.radians(a)), -sr(a) * math.cos(math.radians(a)), 0)) for a in range(0, 360, 15)],
                      0.03, 0.007, "accent", radial(p), closed=True), leg)
        # Knee cop with a yellow ring and screws, greave down the shin.
        kn = ll0 + Vector((0, -0.056, 0.004))
        Mk = Matrix.Translation(kn) @ Matrix.Rotation(math.radians(90), 4, "X")
        c.rigid(dome("knee_cop", Mk, (0.074, 0.09, 0.062), -12, 90, 0.016, WHITE, nlat=7, nlon=18, bevel=0.005), "lower_leg." + s)
        c.rigid(dome("knee_ring", Mk, (0.091, 0.107, 0.075), -4, 12, 0.006, "hazard", nlat=1, nlon=18, bevel=0.0015), "lower_leg." + s)
        tip = kn + Vector((0, -0.062 - 0.016, 0))
        c.rigid(kit.cyl("knee_stud", tip + Vector((0, 0.004, 0)), tip + Vector((0, -0.006, 0)), 0.014, "gunmetal", segs=12, bevel=0.002), "lower_leg." + s)
        limb_patch(c, "greave", ll0.lerp(ll1, 0.16), ll0.lerp(ll1, 0.62), 0.09, 0.076, -92, 92, 0.016, WHITE, "lower_leg." + s, nt=8, nphi=14,
                   bevel=0.005, bulge=0.012, round_ends=3)
        limb_patch(c, "greave_ridge", ll0.lerp(ll1, 0.2), ll0.lerp(ll1, 0.58), 0.108, 0.092, -14, 14, 0.008, NAVY, "lower_leg." + s, nt=4, nphi=2,
                   bevel=0.002, bulge=0.012)
        for t in (0.25, 0.5):
            c.rigid(screw_on(ll0.lerp(ll1, t), Vector((sx, -1, 0)).normalized(), 0.09 + 0.012 * math.sin(math.pi * (t - 0.14) / 0.48)), "lower_leg." + s)
        # Heavy boots with an armoured ankle plate.
        c.add(boot(c, b, s, upper="black", trim=NAVY, sole_mat="rubber", lace="grey", tab="hazard", top=0.29, scale=1.15, heavy=True),
              ["foot." + s, "lower_leg." + s])
        limb_patch(c, "ankle_plate", ll0.lerp(ll1, 0.68), ll0.lerp(ll1, 0.9), 0.074, 0.08, -80, 80, 0.012, NAVY, "lower_leg." + s, nt=2, nphi=10, bevel=0.004)
    c.cover(FEET | SHINS, lambda p: p.z < 0.27)

    # Codpiece and hip pouches on the belt.
    loc, _ = hit(tf, (0, -0.5, 1.0), (0, 1, 0))
    Mcp = frame(loc + Vector((0, -0.03, 0)), (0, -1, 0))
    cod = [panel("codpiece", kit.rounded([(-0.065, 0.06), (0.065, 0.06), (0.05, -0.02), (0.0, -0.06), (-0.05, -0.02)], 0.015), 0.0, 0.014, NAVY, bevel=0.004)]
    cod += screws([(-0.04, 0.035), (0.04, 0.035)], -0.014, r=0.004)
    put(cod, Mcp, 0.14)
    rigid_all(c, cod, "hips")
    for sx in (1, -1):
        d = Vector((sx, 1.0, 0)).normalized()
        loc, _ = hit(tf, Vector((0, 0.0, 1.08)) + d * 0.5, -d)
        M = frame(loc + d * 0.034, d)
        pouch = [kit.block("hip_pouch", (0, -0.025, 0), (0.09, 0.05, 0.08), "pmc_navy", bevel=0.007),
                 kit.block("pouch_flap", (0, -0.027, 0.035), (0.094, 0.056, 0.022), "pmc_navy", bevel=0.005),
                 kit.block("pull_tab", (0, -0.056, 0.022), (0.024, 0.005, 0.03), "hazard", bevel=0.0015)]
        put(pouch, M)
        rigid_all(c, pouch, "hips")
    economise(c)
    return c


def screw_on(p, n, r, material="gunmetal"):
    """A screw on a cylindrical plate: at distance r from p along n, facing n."""
    n = Vector(n).normalized()
    at = Vector(p) + n * r
    o = kit.cyl("screw", at - n * 0.001, at + n * 0.0025, 0.0045, material, segs=10, bevel=0.0)
    o["bevel"] = 0.0
    return o


SPEC = {"build": build, "faction": "pmc", "budget": (25000, 75000), "loadout": "rocket",
        "colors": {"primary": "#26303f", "secondary": "#353a42", "accent": "#c9a227"}}
