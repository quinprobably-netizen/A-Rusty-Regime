"""Zealot, Regime: an augmented officer of the Algorithm. A bare shaved head with gunmetal skull ports
cabled down into the collar, barcode tattoos on the scalp and neck, a red ocular implant, and a halo
crown of thin antennas rigid to the skull. A long robe over bone plate: a code-etched breastplate in
the robe's open front, a high collar, a pleated skirt open at the front over greaves and boots, a red
stole embroidered with scripture, an ornate pauldron on the left and a lighter one on the right.

Tints: primary = robe, secondary = undersuit, accent = stole, sash and straps.
"""

import math

from mathutils import Vector

import kit
from kit import FEET, SHINS, TORSO, UPPER_ARMS
from chars.acolyte import (J, arc_plate, band, boot, bvh, cable, code_rows, cuirass, abdomen_lames, done, fix, gloves, greave,
                           hang_weights, hit, knee_cop, pauldron, project, ring, ring_band, scripture, screw, screw_on, sigil,
                           skirt, skirt_pt, socket, tick_rows, vambrace, weigh_custom, barcode, antenna, lifted_weights)


def build():
    b = kit.Build(height=1.88, width=0.95, bulk=0.88)
    k, w = b.k, b.width
    c = kit.begin("zealot", b)
    parts = kit.body(b, skin="secondary", head=False)
    flesh = c.flesh(parts["body"])
    gloves(c, b, parts, material="black")

    # ------------------------------------------------------------------------------------ head
    head = kit.head_mesh(b, "skin_pale", jaw=1.06, brow=1.2, nose=1.06)
    c.add(head, kit.HEAD_BONES)
    hc = b.j("head", 0.45)
    cc = hc + Vector((0, 0.01, 0.015 * k))  # cranium centre
    htree = bvh(head)

    # A bone gorget ring where the neck meets the breastplate.
    n0 = b.j("neck", 0.0)
    c.rigid(arc_plate("gorget", n0 + Vector((0, 0.004, -0.006)), n0 + Vector((0, 0.004, 0.032 * k)), (0, -1, 0), 0.079 * k, 0.066 * k, 180, 0.008,
                      segs=28, rings=2, bevel=0.002), "chest")

    # Skull ports: gunmetal sockets in the scalp, cables over the skull down into the collar.
    nape = Vector((0, 0.058 * k, b.j("neck", 0.55).z))
    for i, d in enumerate((Vector((0, 0.35, 1.0)), Vector((0.6, 0.6, -0.05)), Vector((-0.6, 0.6, -0.05)), Vector((0, 1.0, -0.15)))):
        d.normalize()
        h = hit(htree, cc + d * 0.3, -d)
        if not h:
            continue
        at, n = h
        port = socket("skull_port", at - n * 0.004, n, r=0.0085, lip="gunmetal")
        c.rigid(port, "head")
        # Cable: lifted off the scalp, over the back of the skull, down the nape into the collar.
        pts = [at + n * 0.008]
        for t in (0.35, 0.7):
            dd = d.lerp(Vector((d.x * 0.3, 1.0, -0.35)).normalized(), t).normalized()
            hh = hit(htree, cc + dd * 0.3, -dd)
            if hh:
                pts.append(hh[0] + hh[1] * (0.009 + 0.002 * i))
        pts += [nape + Vector((d.x * 0.03, 0.008 + 0.004 * i, 0.0)), Vector((d.x * 0.03, 0.085 * k, b.j("neck", 0.0).z + 0.01))]
        c.add(cable("skull_cable", pts, 0.0042), ["head", "neck", "chest"])

    # Barcode tattoos on the scalp and the side of the neck, a code line on the temple.
    for sx in (1, -1):
        c.add(project(head, barcode(7 + sx, 0.05, 0.02), hc + Vector((sx * 0.3, 0.03, 0.092 * k)), (-sx, 0, 0), lift=0.0002, tree=htree), kit.HEAD_BONES)
    c.add(project(head, barcode(3, 0.04, 0.014), Vector((0.3, -0.005, b.j("neck", 0.82).z)), (-1, 0, 0), lift=0.0002, tree=htree), kit.HEAD_BONES)
    c.add(project(head, code_rows(["0x7F∴1E"], 0.007), Vector((0.3, -0.008, b.j("neck", 0.82).z - 0.015)), (-1, 0, 0), lift=0.0002, tree=htree), kit.HEAD_BONES)
    c.add(project(head, tick_rows(9, 3, 0.03, 0.0035), hc + Vector((0.0, 0.05, 0.3)), (0, -0.25, -1), up=(0, -1, 0), lift=0.0002, tree=htree), kit.HEAD_BONES)

    # Ocular implant over the right eye: gunmetal bezel, red lens, two screws, a lead to the temple.
    eye = hc + Vector((-0.034, -0.066, 0.003))
    er = 0.0125 * k
    c.rigid(ring("ocular", eye + Vector((0, -er * 0.62, 0)), (0.12, -1, 0.05), 0.021 * k, 0.0135 * k, 0.007, "gunmetal", segs=20), "head")
    c.rigid(kit.cyl("ocular_lens", eye + Vector((0, -er * 0.5, 0)), eye + Vector((0, -er * 1.02, 0)), 0.0095 * k, "glow_red", segs=16, bevel=0), "head")
    for a in (35, 215):
        r = math.radians(a)
        c.rigid(screw(eye + Vector((math.cos(r) * 0.018, -er * 0.9, math.sin(r) * 0.018)), (0.1, -1, 0), r=0.0022), "head")
    temple = hit(htree, hc + Vector((-0.3, -0.03, 0.02)), (1, 0, 0))
    if temple:
        c.rigid(cable("ocular_lead", [eye + Vector((-0.02, -0.006, 0.004)), eye + Vector((-0.04, 0.0, 0.01)), temple[0] + temple[1] * 0.004], 0.0025, "gunmetal"), "head")

    # Halo crown: a gunmetal circlet round the skull with a bone plaque at the brow, nine thin
    # antennas fanned out behind (short at the temples, long at the back) with glowing tips, linked by
    # a halo arc.
    zc = hc.z + 0.052 * k
    axis = Vector((0, 0.01, 0))
    c.rigid(ring_band("circlet", htree, axis, zc, -179, 179, -0.0015, 0.006, 0.014 * k, "gunmetal", n=36), "head")
    c.rigid(ring_band("circlet_trim", htree, axis, zc + 0.008 * k, -179, 179, 0.0, 0.0035, 0.003, "bone", n=36), "head")
    fh = hit(htree, Vector((0, -0.4, zc)), (0, 1, 0))
    if fh:
        plaque = kit.block("crown_plaque", (0, 0, 0), (0.03, 0.006, 0.026), "bone", bevel=0.002, taper=(0.7, 1.0))
        plaque.data.transform(kit.Matrix.Translation(fh[0] + fh[1] * 0.009))
        c.rigid(plaque, "head")
        c.rigid(project(plaque, code_rows(["∴"], 0.02), fh[0] + Vector((0, -0.1, 0.002)), (0, 1, 0)), "head")
    arc = []
    n_ant = 9
    for i in range(n_ant):
        deg = 72 + (360 - 144) * i / (n_ant - 1)
        ph = math.radians(deg)
        d = Vector((math.sin(ph), -math.cos(ph), 0))
        back = max(0.0, ((1 - math.cos(ph)) / 2 - 0.34) / 0.66)  # 0 at the temples .. 1 at the back
        h = hit(htree, Vector((axis.x, axis.y, zc)) + d * 0.4, -d)
        if not h:
            continue
        base = h[0] + d * 0.004
        tilt = math.radians(22 + 22 * (1 - back))
        dirv = (Vector((0, 0, 1)) * math.cos(tilt) + d * math.sin(tilt) + Vector((0, 0.25, 0))).normalized()
        L = (0.05 + 0.13 * back ** 1.2) * k
        bars = ((0.78, 0.01),) if back > 0.85 else ()
        c.rigid(antenna("crown_antenna", base, base + dirv * L, r=0.0028, bars=bars), "head")
        arc.append(base + dirv * L * 0.72)
    ends = [arc[0] + (arc[0] - arc[1]) * 0.35, arc[-1] + (arc[-1] - arc[-2]) * 0.35]
    c.rigid(kit.strap("halo_arc", [ends[0]] + arc + [ends[1]], 0.005, 0.0028, "gunmetal"), "head")

    # ------------------------------------------------------------------------------ plate under
    chest, _ = cuirass(c, b, back=False, seed=5, rows=4, cols=9, vents=False, sigil_z=1.225)
    abdomen_lames(c, b, seed=35)

    # ------------------------------------------------------------------------------------- robe
    z_w = b.hip_z + 0.04
    z_h = 0.30
    r_top, r_bot, cy = (0.165 * w / 0.95, 0.118 * b.bulk / 0.88), (0.25, 0.22), (0.012, 0.03)
    opening = [(-0.068, 1.48), (0.068, 1.48), (0.122, 1.39), (0.128, 1.26), (0.098, 1.12), (0.06, 0.99),
               (-0.06, 0.99), (-0.098, 1.12), (-0.128, 1.26), (-0.122, 1.39)]
    sleeve_cuts = []
    for s in ("L", "R"):
        f0, f1 = b.j("forearm." + s, -0.12), b.j("forearm." + s, 1.0)
        mid = (f0 + f1) / 2
        ax = (f1 - f0).normalized()
        q = Vector((0, 0, 1)).rotation_difference(ax).to_euler()
        sleeve_cuts.append(kit.blob_cutter("sleeve_cut", mid, (0.09, 0.09, (f1 - f0).length / 2), rot=tuple(math.degrees(a) for a in q)))
    robe = kit.shell(flesh, lambda p: p.z > z_w - 0.02 and p.z < 1.5 * k, "robe", "primary", offset=0.042, thick=0.005, smooth_iter=3,
                     detail=0.7, bones=TORSO | UPPER_ARMS,
                     outside=[kit.slab("robe_opening", kit.rounded([J(b, x, z) for x, z in opening], 0.02), -0.4, -0.01)] + sleeve_cuts)
    rtree = bvh(robe)
    weigh_custom(c, robe, lifted_weights(flesh, 0.0445, [TORSO, UPPER_ARMS]))
    on_robe = lifted_weights(flesh, 0.05, [TORSO])  # stole and embroidery: torso only, never the arms
    c.cover(TORSO | UPPER_ARMS, lambda p: z_w + 0.02 < p.z < 1.44 * k and (p.y > -0.02 or abs(p.x) > 0.12 * w) and (abs(p.x) < 0.15 or p.z > 1.25 * k))
    # Scripture embroidered down the robe's back.
    weigh_custom(c, project(robe, code_rows(["∴"] + scripture(81, 8, 3), 0.012 * k), (0, 0.4, 1.27 * k), (0, -1, 0), material="bone", tree=rtree), on_robe)
    # High collar standing behind the neck, trimmed in bone.
    n0, n1 = Vector((0, 0.004, b.j("neck", 0.0).z - 0.02)), Vector((0, 0.016, b.j("neck", 0.0).z + 0.12 * k))
    c.rigid(arc_plate("collar", n0, n1, (0, 1, 0), 0.098 * k, 0.112 * k, (112, 100), 0.006, material="primary", segs=18, rings=3, bevel=0.0015), "chest")
    c.rigid(arc_plate("collar_trim", n1 - Vector((0, 0, 0.012)), n1 + Vector((0, 0.001, 0.0)), (0, 1, 0), 0.111 * k, 0.1125 * k, (101, 100), 0.004,
                      material="bone", segs=18, rings=1, bevel=0.001), "chest")
    # Sleeve cuffs where the robe ends above the elbows.
    for s in ("L", "R"):
        c.add(band("sleeve_cuff", b.j("upper_arm." + s, 0.83), (0.088 * k, 0.085 * k), 0.026, 0.007, "accent",
                   axis=b.j("upper_arm." + s, 1.0) - b.j("upper_arm." + s, 0.0), segs=18), ["upper_arm." + s])

    # Skirt: pleated, open at the front, weighted from the hips into the thighs.
    sk = skirt("robe_skirt", z_w, z_h, r_top, r_bot, cy=cy, gap=(14, 30), folds=9, fold=0.03, nu=46, nv=11, thick=0.005)
    hw = hang_weights(z_w, z_h, side=0.09, legs=0.85)
    weigh_custom(c, sk, hw)
    # Hem band and the stole's lower ends follow the skirt's own weights.
    hem = [skirt_pt(0.97, 30 + 300 * i / 40, z_w, z_h, r_top, r_bot, cy, out=0.0045, fold=0.03) for i in range(41)]
    weigh_custom(c, kit.strap("hem_band", [p + Vector((0, 0, 0.014)) for p in hem], 0.03, 0.004, "accent"), hw)
    for sx in (1, -1):
        edge = [skirt_pt(h, sx * (14 + 16 * h + 6), z_w, z_h, r_top, r_bot, cy, out=0.0045, fold=0.03) for h in [0.02 + i / 8.4 for i in range(9)]]
        low = kit.strap("stole_low", edge, 0.05, 0.004, "accent")
        weigh_custom(c, low, hw)
        st = bvh(low)
        mid = edge[4]
        weigh_custom(c, project(low, code_rows(["∴"] + scripture(91 + sx, 7, 1), 0.016), mid + Vector((0, -0.3, 0)) * 1.0, (0, 1, 0), tree=st), hw)
    # Hem scripture across the back of the skirt.
    for i, deg in enumerate((150, 180, 210)):
        p = skirt_pt(0.9, deg, z_w, z_h, r_top, r_bot, cy)
        d = Vector((p.x, p.y - cy[1], 0)).normalized()
        weigh_custom(c, project(sk, code_rows([scripture(95 + i, 1, 7)[0]], 0.013), p + d * 0.2, -d, material="bone"), hw)

    # Stole over the robe: from behind the collar, over the shoulders, down the edges of the opening.
    for sx in (1, -1):
        rows = [(0.07, 1.47), (0.095, 1.43), (0.118, 1.37), (0.128, 1.29), (0.12, 1.2), (0.098, 1.12), (0.078, 1.05)]
        pts = [Vector((sx * 0.05 * w, 0.1 * k, 1.47 * k)), Vector((sx * 0.07 * w, 0.03, 1.5 * k))]
        for x, z in rows:
            h = hit(rtree, (sx * x * w, -0.4, z * k), (0, 1, 0))
            pts.append(h[0] + h[1] * 0.004 if h else Vector((sx * x * w, -0.12, z * k)))
        stole = kit.strap("stole", pts, 0.05, 0.004, "accent")
        stole_code = project(stole, code_rows(scripture(97 + sx, 5, 1), 0.015), (sx * 0.115 * w, -0.4, 1.3 * k), (0, 1, 0))
        weigh_custom(c, stole, on_robe)
        weigh_custom(c, stole_code, on_robe)

    # Sash belt over the robe and skirt, a bone buckle with the cult mark, hanging tails.
    sash_r = (0.19 * w / 0.95, 0.142 * b.bulk / 0.88)
    c.add(band("sash", Vector((0, cy[0], z_w)), sash_r, 0.07, 0.01, "accent", segs=24), ["hips", "spine"])
    buckle = c.rigid(kit.block("buckle", (0, cy[0] - sash_r[1] - 0.009, z_w), (0.075, 0.012, 0.06), "bone", bevel=0.003), "hips")
    c.rigid(project(buckle, sigil(0.02, n=20, w=0.0028) + code_rows(["∴"], 0.022), (0, -0.4, z_w), (0, 1, 0)), "hips")
    for x, y in ((-0.06, -0.026), (0.06, -0.026)):
        c.rigid(screw((x * 0.48, cy[0] - sash_r[1] - 0.015, z_w + y + 0.02 + 0.006 * (y < 0)), (0, -1, 0), r=0.0032), "hips")

    # ------------------------------------------------------------------------------ arms, legs
    pauldron(c, b, "L", 1, grow=1.36, seed=43, rows=3, lames=((0.12, 0.3, 0.074), (0.27, 0.45, 0.07)))
    pauldron(c, b, "R", -1, grow=1.3, seed=47, rows=2, lames=((0.14, 0.32, 0.072),), rib=False)
    for s, sx in (("L", 1), ("R", -1)):
        vambrace(c, b, s, sx, seed=53)
        knee_cop(c, b, s)
        greave(c, b, s, sx, seed=73)
        boot(c, b, flesh, s, sx)
    c.cover(FEET | SHINS, lambda p: p.z < 0.16 * k)
    return c


SPEC = {"build": build, "faction": "regime", "budget": (25000, 75000), "loadout": "revolver",
        "colors": {"primary": "#1a1a1d", "secondary": "#2a2a2e", "accent": "#7a1010"}}
