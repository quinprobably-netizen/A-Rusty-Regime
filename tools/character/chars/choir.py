"""Choir, Regime: the cult's tall faceless sniper, who listens to the Algorithm through a long antenna
array. A tall sealed helmet with a cluster of glowing red lens rings for a face and a rangefinder pod,
a fitted coat with long split tails, light bone plate (breastplate, shoulder caps, vambraces, knee
cops, greaves), and a slim uplink pack on the back carrying five tall masts with crossbars.

Tints: primary = undersuit, secondary = coat, accent = straps and trim.
"""

import math

from mathutils import Vector

import kit
from kit import FEET, FOREARMS, SHINS, TORSO, UPPER_ARMS
from chars.acolyte import (antenna, band, boot, bvh, cable, code_rows, cuirass, done, fix, gloves, greave, hang_weights, hit,
                           knee_cop, lifted_weights, neck_seal, pauldron, project, ring, scripture, screw, screw_on, sealed_helmet,
                           skirt, skirt_pt, socket, tick_rows, vambrace, weigh_custom, J)

LIGHT_CHEST = [(-0.115, 1.2), (0.115, 1.2), (0.13, 1.27), (0.128, 1.335), (0.1, 1.39), (0.058, 1.41),
               (0.034, 1.388), (0.0, 1.376), (-0.034, 1.388), (-0.058, 1.41), (-0.1, 1.39), (-0.128, 1.335), (-0.13, 1.27)]


def lens(name, at, n, r):
    """A helmet lens: a gunmetal cup with a glowing red ring round a dark glass eye."""
    at, n = Vector(at), Vector(n).normalized()
    cup = kit.cyl(name, at - n * 0.004, at + n * 0.011, r + 0.0045, "gunmetal", segs=16, bevel=0.001, bsegs=1)
    kit.cut(cup, kit.cyl("bore", at + n * 0.006, at + n * 0.02, r, "steel", segs=16, bevel=0))
    glow = ring(name + "_ring", at + n * 0.0068, n, r * 0.97, r * 0.6, 0.0016, "glow_red", segs=16)
    glass = kit.cyl(name + "_glass", at + n * 0.0055, at + n * 0.0072, r * 0.62, "glass", segs=12, bevel=0)
    return [cup, glow, glass]


def build():
    b = kit.Build(height=2.0, width=0.92, bulk=0.9)
    k, w = b.k, b.width
    c = kit.begin("choir", b)
    parts = kit.body(b, skin="primary", head=False)
    flesh = c.flesh(parts["body"])
    gloves(c, b, parts, material="rubber", guard="gunmetal")
    hc = b.j("head", 0.45)

    # ---------------------------------------------------------------------------------- helmet
    shell, htree = sealed_helmet(c, b, slit=False, vents=False, ears=False, scale=(0.95, 1.05, 1.08))
    neck_seal(c, b, n=5, r0=0.055, step=0.0035)
    zs = hc.z + 0.004 * k
    for x, dz, r in ((0.0, 0.003, 0.02), (0.041, 0.017, 0.012), (-0.041, 0.017, 0.012), (0.036, -0.021, 0.0105), (-0.036, -0.021, 0.0105),
                     (0.067, 0.002, 0.0075), (-0.067, 0.002, 0.0075), (0.0, -0.04, 0.0085)):
        h = hit(htree, Vector((x * k, -0.4, zs + dz * k)), (0, 1, 0))
        if h:
            for o in lens("lens", h[0], h[1].lerp(Vector((0, -1, 0)), 0.5), r * k):
                c.rigid(o, "head")
    # Rangefinder pod on the right temple: a gunmetal box with a lens and fins.
    h = hit(htree, hc + Vector((-0.3, -0.02, 0.01 * k)), (1, 0, 0))
    if h:
        p0 = h[0] + Vector((-0.012, 0, 0))
        pod = kit.block("pod", p0 + Vector((-0.006, -0.008, 0)), (0.024, 0.07, 0.03), "gunmetal", bevel=0.003)
        kit.cut(pod, *[kit.block("pod_fin", p0 + Vector((-0.019, 0.012 + i * 0.008, 0)), (0.006, 0.0035, 0.034), "steel", bevel=0) for i in range(3)])
        c.rigid(pod, "head")
        for o in lens("pod_lens", p0 + Vector((-0.006, -0.043, 0)), (0, -1, 0), 0.009):
            c.rigid(o, "head")
        c.rigid(screw(p0 + Vector((-0.0185, -0.02, 0)), (-1, 0, 0), r=0.003), "head")

    # ------------------------------------------------------------------------------------ coat
    wrists = [b.j("hand.L", 0.0), b.j("hand.R", 0.0)]

    def off_wrist(p, d):
        return all((p - q).length > d for q in wrists)
    z_top = b.hip_z + 0.05
    coat = kit.shell(flesh, lambda p: p.z > z_top - 0.03 and p.z < 1.62 * k and off_wrist(p, 0.07), "coat", "secondary", offset=0.017, thick=0.004,
                     smooth_iter=2, detail=0.6, bones=TORSO | UPPER_ARMS | FOREARMS)
    weigh_custom(c, coat, lifted_weights(flesh, 0.019, [TORSO, UPPER_ARMS | FOREARMS]))
    c.cover(TORSO | UPPER_ARMS | FOREARMS, lambda p: z_top + 0.02 < p.z < 1.56 * k and off_wrist(p, 0.1))
    for s in ("L", "R"):
        fa = "forearm." + s
        c.add(band("coat_cuff", b.j(fa, 0.8), (0.05 * k, 0.046 * k), 0.026, 0.006, "accent", axis=b.j(fa, 1.0) - b.j(fa, 0.0)), [fa])
    # Long split coat tails from the belt to mid-calf, edged red, scripture in bone thread on the back.
    z_bot = 0.4 * k
    r_top, r_bot, cy = (0.165 * w / 0.92, 0.138 * b.bulk / 0.9), (0.245, 0.215), (0.015, 0.03)
    hw = hang_weights(z_top, z_bot, side=0.09, legs=0.85)
    for i, (a0, a1) in enumerate(((58, 118), (122, 177), (183, 238), (242, 302))):
        tail = skirt("coat_tail", z_top, z_bot, r_top, r_bot, cy=cy, folds=7, fold=0.015, nu=10, nv=12, thick=0.0045, material="secondary", span=(a0, a1))
        weigh_custom(c, tail, hw)
        hem = [skirt_pt(0.975, a0 + (a1 - a0) * j / 8, z_top, z_bot, r_top, r_bot, cy, out=0.0035, fold=0.015, folds=7) for j in range(9)]
        weigh_custom(c, kit.strap("tail_hem", hem, 0.024, 0.004, "accent"), hw)
        if i in (1, 2):
            mid = skirt_pt(0.42, (a0 + a1) / 2, z_top, z_bot, r_top, r_bot, cy)
            d = Vector((mid.x, mid.y - cy[0], 0)).normalized()
            weigh_custom(c, project(tail, code_rows(scripture(121 + i, 6, 2), 0.013), mid + d * 0.25, -d, material="bone"), hw)
    # Belt with ammo pouches and a bone buckle.
    c.add(band("belt", Vector((0, cy[0], z_top)), (r_top[0] + 0.01, r_top[1] + 0.01), 0.05, 0.01, "accent", segs=24), ["hips", "spine"])
    buckle = c.rigid(kit.block("buckle", (0, cy[0] - r_top[1] - 0.017, z_top), (0.055, 0.012, 0.04), "bone", bevel=0.003), "hips")
    c.rigid(project(buckle, code_rows(["∴"], 0.024), (0, -0.4, z_top), (0, 1, 0)), "hips")
    for sx in (1, -1):
        for j, ang in enumerate((28, 44)):
            p = skirt_pt(0.0, sx * ang, z_top, z_bot, (r_top[0] + 0.03, r_top[1] + 0.03), r_bot, cy)
            pouch = kit.block("ammo_pouch", (0, 0, 0), (0.034, 0.03, 0.05), "secondary", bevel=0.005)
            lid = kit.block("ammo_lid", (0, -0.002, 0.024), (0.037, 0.034, 0.012), "secondary", bevel=0.004)
            snap = kit.cyl("snap", (0, -0.017, 0.022), (0, -0.02, 0.022), 0.005, "gunmetal", segs=8, bevel=0)
            o = kit.join([pouch, lid, snap], "ammo_pouch")
            o.data.transform(kit.Matrix.Translation(p + Vector((0, 0, -0.012))) @ kit.Matrix.Rotation(math.radians(-sx * ang * 0.8), 4, "Z"))
            c.rigid(o, "hips")

    # ----------------------------------------------------------------------------- light plate
    chest, _ = cuirass(c, b, back=False, seed=13, rows=3, cols=8, outline=LIGHT_CHEST, vents=True, sigil_z=1.25, vent_z=1.215, seam_z=1.29)
    for s, sx in (("L", 1), ("R", -1)):
        pauldron(c, b, s, sx, grow=1.06, seed=141, rows=2, lames=(), rib=False)
        vambrace(c, b, s, sx, seed=151, straps=False, r=(0.06, 0.053), t=(0.12, 0.74))
        knee_cop(c, b, s)
        greave(c, b, s, sx, seed=171)
        boot(c, b, flesh, s, sx)
    c.cover(FEET | SHINS, lambda p: p.z < 0.16 * k)

    # ------------------------------------------------------------------------ the antenna array
    # A slim bone pack on the upper back, a gunmetal hub on top, five masts leaning back in a fan.
    py, pz = 0.155 * b.bulk / 0.9, 1.42 * k
    pack = kit.block("pack", (0, py, pz), (0.12, 0.06, 0.25), "bone", bevel=0.007, taper=(0.9, 0.9))
    kit.cut(pack, *[kit.block("pack_vent", (s * 0.06, py, pz - 0.07 + i * 0.022), (0.014, 0.044, 0.007), "steel", bevel=0)
                    for s in (-1, 1) for i in range(5)])
    c.rigid(pack, "chest")
    pt = bvh(pack)
    c.rigid(project(pack, code_rows(["CHOIR", "∴ 7F ∴"] + scripture(131, 3, 6), 0.0105), (0, 0.4, pz - 0.02), (0, -1, 0), tree=pt), "chest")
    for x in (-0.042, 0.042):
        for z in (pz - 0.105, pz + 0.095):
            fix(c, screw_on(pt, (x, 0.4, z), (0, -1, 0), r=0.0035), "chest")
    hub_z = pz + 0.14
    hub = kit.block("hub", (0, py + 0.012, hub_z), (0.17, 0.06, 0.036), "gunmetal", bevel=0.003)
    c.rigid(hub, "chest")
    c.rigid(kit.block("hub_band", (0, py + 0.012, hub_z - 0.024), (0.15, 0.062, 0.012), "bone", bevel=0.002), "chest")
    for i, (x, L) in enumerate(((-0.064, 0.6), (-0.032, 0.72), (0.0, 0.82), (0.032, 0.72), (0.064, 0.6))):
        base = Vector((x, py + 0.02, hub_z + 0.018))
        d = Vector((x * 3.0, 0.4, 1.0)).normalized()
        bars = [(0.42 + 0.11 * j, 0.05 - 0.007 * j) for j in range(5)]
        c.rigid(antenna("mast", base, base + d * L * k, r=0.0042, bars=bars), "chest")
        c.rigid(kit.cyl("mast_foot", base - Vector((0, 0, 0.004)), base + Vector((0, 0, 0.012)), 0.009, "bone", segs=10, bevel=0.001, bsegs=1), "chest")
    # Cables: helmet -> hub, pack -> belt.
    for s in (-1, 1):
        h = hit(htree, hc + Vector((s * 0.035, 0.3, -0.1 * k)), (0, -1, 0))
        if h:
            c.rigid(socket("helmet_port", h[0], h[1], r=0.008), "head")
            end = Vector((s * 0.055, py + 0.04, hub_z))
            c.rigid(socket("hub_port", end, (0, 1, 0.2), r=0.007), "chest")
            p0 = h[0] + h[1] * 0.01
            c.add(cable("neck_cable", [p0, p0 + Vector((0, 0.035, -0.04)), end + Vector((0, 0.04, 0.0)), end + Vector((0, 0.008, 0))], 0.005),
                  ["head", "neck", "chest"])
        low = Vector((s * 0.045, py, pz - 0.125))
        c.add(cable("belt_cable", [low, low + Vector((s * 0.01, 0.012, -0.05)), Vector((s * 0.07, cy[0] + r_top[1] + 0.015, z_top + 0.03))], 0.0045),
              ["chest", "spine", "hips"])
    return c


SPEC = {"build": build, "faction": "regime", "budget": (25000, 75000), "loadout": "dmr",
        "colors": {"primary": "#1a1a1d", "secondary": "#2a2a2e", "accent": "#7a1010"}}
