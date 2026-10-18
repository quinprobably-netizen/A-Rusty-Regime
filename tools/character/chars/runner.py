"""Runner, Deserters: the player's default. An ex-Regime parkour pilot: hood up over a respirator,
softshell jacket, Regime chest plate scratched clean and repainted cream with a clay stripe, the cult
uplink torn off the back leaving a stub and cut cables, grapple launcher on the left forearm, rope
coil, cargo trousers with knee pads, climbing boots. The reference character for the kit.

Tints: primary = jacket and hood (slate), secondary = trousers (kraft), accent = straps (clay).
"""

import math

from mathutils import Vector

import kit
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS, FEET


def build():
    b = kit.Build(height=1.80, width=1.0, bulk=0.95)
    c = kit.begin("runner", b)
    parts = kit.body(b, skin="skin")
    flesh = c.flesh(parts["body"])
    head = c.add(parts["head"], kit.HEAD_BONES)
    hc = b.j("head", 0.45)  # head centre
    wrists = [b.j("hand.L", 0.0), b.j("hand.R", 0.0)]

    def off_wrist(p, d=0.03):
        return all((p - w).length > d for w in wrists)

    # Gloves: the gripping hands in leather, with taped wrists and slate knuckle guards.
    hands = parts["hands"]
    hands.data.materials[0] = kit.mat("leather")
    c.add(hands, kit.HAND_BONES)
    for s in ("L", "R"):
        w = b.j("hand." + s, 0.0)
        fa = b.j("forearm." + s, 0.88)
        c.add(kit.band("tape", fa, (0.040, 0.036), 0.035, 0.006, "cream", axis=fa - w))
        hb = Vector(b.all["hand." + s][0])
        down = (Vector(b.all["hand." + s][1]) - hb).normalized()
        sx = 1 if s == "L" else -1
        knuckle = hb + down * 0.092 + Vector((sx * 0.012, -0.002, 0))
        guard = kit.block("knuckle", (0, 0, 0), (0.016, 0.075, 0.022), "slate", bevel=0.003)
        guard.data.transform(kit.Matrix.Translation(knuckle))
        c.rigid(guard, "hand." + s)

    # Jacket: torso and sleeves down to the wrist, a high collar and a zip.
    jacket = kit.shell(flesh, lambda p: p.z > 0.86 and off_wrist(p, 0.045), "jacket", "primary",
                       offset=0.015, thick=0.004, smooth_iter=2, bones=TORSO | UPPER_ARMS | FOREARMS | {"neck"})
    c.add(jacket)
    c.cover(TORSO | UPPER_ARMS | FOREARMS, lambda p: p.z > 0.9 and off_wrist(p, 0.07))
    collar_z = b.j("neck", 0.15).z
    c.add(kit.band("collar", Vector((0, 0.008, collar_z)), (0.075, 0.07), 0.07, 0.008, "primary"))
    c.add(kit.strap("zip", [(0, -0.118, 0.93), (0, -0.124, 1.05), (0, -0.13, 1.18), (0, -0.112, 1.36)], 0.012, 0.004, "slate"))
    for s, sx in (("L", 1), ("R", -1)):
        # Elbow patches and a cuff on each sleeve.
        e = b.j("forearm." + s, 0.0)
        c.add(kit.band("cuff", b.j("forearm." + s, 0.8), (0.046, 0.042), 0.04, 0.008, "primary", axis=b.j("forearm." + s, 1) - e))
        patch = kit.block("elbow", e + Vector((0, 0.045, 0.01)), (0.06, 0.012, 0.08), "slate", bevel=0.004)
        c.add(patch)

    # Hood: over the head with a clean oval opening for the face, and a cowl over the shoulders.
    hood = kit.shell(head, None, "hood", "primary", offset=0.026, thick=0.006, smooth_iter=6,
                     outside=[kit.blob_cutter("face_hole", hc + Vector((0, -0.115, -0.012)), (0.068, 0.07, 0.092), rot=(-8, 0, 0))])
    kit.place(hood, (0, 0.01, 0.01))
    c.add(hood, kit.HEAD_BONES)
    cowl = kit.shell(flesh, lambda p: p.z > 1.25, "cowl", "primary", offset=0.026, thick=0.006, bones=TORSO | {"neck"},
                     inside=[kit.blob_cutter("cowl_cut", b.j("neck", 0.0) + Vector((0, 0.02, -0.02)), (0.21, 0.17, 0.16))])
    c.add(cowl)

    # Respirator over mouth and nose, two clay filter cans.
    mask = kit.shell(head, lambda p: p.y < hc.y - 0.02, "mask", "slate", offset=0.007, thick=0.008, detail=1.0,
                     inside=[kit.blob_cutter("mask_cut", hc + Vector((0, -0.09, -0.06)), (0.07, 0.06, 0.05), rot=(-15, 0, 0))])
    c.rigid(mask, "head")
    for sx in (1, -1):
        can0 = hc + Vector((sx * 0.045, -0.1, -0.07))
        can = kit.cyl("filter", can0, can0 + Vector((sx * 0.03, -0.018, -0.006)), 0.022, "clay", segs=20, bevel=0.003)
        kit.cut(can, *[kit.cyl("vent", can0 + Vector((sx * 0.033, -0.02, -0.006 + dz)), can0 + Vector((sx * 0.02, -0.012, -0.006 + dz)), 0.003, "steel", segs=8)
                       for dz in (-0.009, 0.0, 0.009)])
        c.rigid(can, "head")
        c.rigid(kit.ring("filter_ring", can0 + Vector((sx * 0.004, -0.003, -0.001)), (sx * 1, -0.6, -0.2), 0.024, 0.018, 0.006, "gunmetal"), "head")
    c.rigid(kit.cyl("valve", hc + Vector((0, -0.118, -0.08)), hc + Vector((0, -0.133, -0.085)), 0.016, "gunmetal", segs=18, bevel=0.003), "head")

    # Stolen Regime chest plate, scratched clean and repainted cream, with a clay stripe.
    front = kit.slab("front_cut", kit.rounded([(-0.15, 1.02), (0.15, 1.02), (0.15, 1.30), (0.09, 1.38), (-0.09, 1.38), (-0.15, 1.30)], 0.025), -0.3, 0.0)
    plate = kit.plate(flesh, front, "chest_plate", "cream", offset=0.042, thick=0.016, bevel=0.004, bones=TORSO)
    kit.cut(plate, solver="MANIFOLD", *[kit.block("scratch", (x, -0.16, z), (0.004, 0.08, 0.05), "steel", rot=40) for x, z in ((-0.06, 1.25), (-0.04, 1.27), (0.07, 1.16), (0.09, 1.14), (-0.02, 1.12))])
    c.rigid(plate, "chest")
    stripe = kit.slab("stripe_cut", [(-0.16, 1.22), (0.16, 1.27), (0.16, 1.31), (-0.16, 1.26)], -0.3, 0.0)
    c.rigid(kit.plate(flesh, stripe, "stripe", "clay", offset=0.059, thick=0.002, bevel=0.0, bones=TORSO), "chest")
    c.rigid(kit.label_front("07", (0.08, -0.152, 1.10), 0.04, "slate"), "chest")
    back = kit.slab("back_cut", kit.rounded([(-0.15, 1.02), (0.15, 1.02), (0.15, 1.36), (-0.15, 1.36)], 0.03), 0.0, 0.3)
    c.rigid(kit.plate(flesh, back, "back_plate", "cream", offset=0.042, thick=0.016, bevel=0.004, bones=TORSO), "chest")
    # Carrier: cummerbund, shoulder straps, three mag pouches with clay pull tabs.
    c.add(kit.band("cummerbund", Vector((0, 0, 1.06)), (0.175, 0.13), 0.09, 0.012, "webbing"))
    for sx in (1, -1):
        c.add(kit.strap("shoulder_strap", [(sx * 0.11, -0.15, 1.36), (sx * 0.12, -0.08, 1.44), (sx * 0.12, 0.04, 1.45), (sx * 0.11, 0.15, 1.36)], 0.045, 0.01, "accent"))
    for i, x in enumerate((-0.085, 0.0, 0.085)):
        pouch = kit.block("pouch", (x, -0.175, 1.10), (0.075, 0.05, 0.11), "webbing", bevel=0.006)
        flap = kit.block("flap", (x, -0.178, 1.165), (0.08, 0.056, 0.03), "webbing", bevel=0.005)
        tab = kit.block("tab", (x, -0.205, 1.168), (0.03, 0.006, 0.04), "clay", bevel=0.002)
        c.rigid(kit.join([pouch, flap, tab], "pouch"), "spine")

    # The torn-out uplink: a Regime mount on the upper back, antenna snapped, cables cut.
    mount = kit.block("mount", (0, 0.165, 1.30), (0.12, 0.04, 0.12), "bone", bevel=0.006)
    kit.cut(mount, kit.cyl("socket", (0, 0.15, 1.30), (0, 0.2, 1.30), 0.03, "steel", segs=20))
    c.rigid(mount, "chest")
    stub = kit.cyl("antenna_stub", (0.03, 0.18, 1.34), (0.035, 0.20, 1.43), 0.011, "gunmetal", segs=12, bevel=0.002)
    kit.cut(stub, kit.block("snap", (0.035, 0.2, 1.44), (0.05, 0.05, 0.03), "steel", rot=35))
    c.rigid(stub, "chest")
    for i, (dx, dz) in enumerate(((-0.02, 0.0), (0.0, -0.012), (0.02, 0.005))):
        cable = kit.rope("cable", [Vector((dx, 0.17, 1.30 + dz)), Vector((dx * 2, 0.20, 1.28 + dz)), Vector((dx * 3 + 0.01, 0.215, 1.22 + dz))], 0.0045, "rubber")
        c.rigid(cable, "chest")
        c.rigid(kit.cyl("cut_end", (dx * 3 + 0.01, 0.215, 1.22 + dz), (dx * 3 + 0.01, 0.216, 1.212 + dz), 0.003, "copper", segs=8), "chest")
    for x in (-0.05, 0.05):
        for z in (1.255, 1.345):
            c.rigid(kit.screw((x, 0.186, z), "y", r=0.005, material="gunmetal", head=0.003), "chest")

    # Grapple launcher on the left forearm: housing, barrel, spool, clay band, strapped on.
    fa0, fa1 = b.j("forearm.L", 0.25), b.j("forearm.L", 0.9)
    axis = (fa1 - fa0).normalized()
    out = Vector((1, 0, 0)) - axis * axis.x
    out.normalize()
    housing = kit.cyl("launcher", fa0 + out * 0.05, fa1 + out * 0.05, 0.03, "gunmetal", segs=24, bevel=0.003)
    kit.cut(housing, *[kit.block("vent", fa0.lerp(fa1, t) + out * 0.08, (0.02, 0.012, 0.03), "steel") for t in (0.2, 0.35, 0.5)])
    c.rigid(housing, "forearm.L")
    c.rigid(kit.cyl("barrel", fa1 + out * 0.05, fa1 + out * 0.05 + axis * 0.07, 0.014, "black", segs=16, bevel=0.002), "forearm.L")
    c.rigid(kit.ring("muzzle", fa1 + out * 0.05 + axis * 0.07, axis, 0.018, 0.009, 0.012, "clay"), "forearm.L")
    c.rigid(kit.cyl("spool", fa0.lerp(fa1, 0.6) + out * 0.085, fa0.lerp(fa1, 0.6) + out * 0.105, 0.024, "clay", segs=20, bevel=0.002), "forearm.L")
    c.rigid(kit.cyl("hook", fa1 + out * 0.05 + axis * 0.07, fa1 + out * 0.05 + axis * 0.09, 0.008, "bright", r1=0.002, segs=10), "forearm.L")
    for t in (0.15, 0.7):
        c.rigid(kit.band("launcher_strap", fa0.lerp(fa1, t) + out * 0.02, (0.06, 0.05), 0.022, 0.006, "webbing", axis=axis), "forearm.L")
    for t in (0.1, 0.9):
        c.rigid(kit.screw(fa0.lerp(fa1, t) + out * 0.081, "x", r=0.004, material="steel", head=0.003), "forearm.L")

    # Rope coil from the left shoulder across to the right hip.
    for i in range(3):
        o = i * 0.016
        pts = [Vector((0.14 - o, -0.15, 1.38 - o)), Vector((0.19, 0.0, 1.42 - o)), Vector((0.10, 0.18, 1.22 - o)),
               Vector((-0.10, 0.19, 1.02 - o)), Vector((-0.19, 0.0, 0.98 - o)), Vector((-0.09, -0.19, 1.13 - o)), Vector((0.14 - o, -0.16, 1.38 - o))]
        c.add(kit.rope("rope", pts, 0.009, "canvas"))

    # Trousers, belt with a clay buckle, cargo pockets, knee pads.
    trousers = kit.shell(flesh, lambda p: 0.11 < p.z < 1.0, "trousers", "secondary", offset=0.022, thick=0.004, smooth_iter=3,
                         bones=THIGHS | SHINS | {"hips"})
    c.add(trousers)
    c.cover(THIGHS | SHINS | {"hips"}, lambda p: 0.15 < p.z < 0.98)
    c.add(kit.band("belt", Vector((0, 0.0, 0.965)), (0.165, 0.125), 0.04, 0.01, "webbing"))
    c.rigid(kit.block("buckle", (0, -0.135, 0.965), (0.05, 0.012, 0.035), "clay", bevel=0.003), "hips")
    for s, sx in (("L", 1), ("R", -1)):
        thigh = b.j("upper_leg." + s, 0.45)
        pocket = kit.block("pocket", thigh + Vector((sx * 0.085, 0.0, 0)), (0.03, 0.12, 0.15), "secondary", bevel=0.008)
        flap = kit.block("pocket_flap", thigh + Vector((sx * 0.088, 0.0, 0.07)), (0.034, 0.125, 0.03), "secondary", bevel=0.006)
        snap = kit.cyl("snap", thigh + Vector((sx * 0.104, 0, 0.07)), thigh + Vector((sx * 0.108, 0, 0.07)), 0.007, "gunmetal", segs=12)
        c.rigid(kit.join([pocket, flap, snap], "pocket"), "upper_leg." + s)
        knee = b.j("lower_leg." + s, 0.04)
        pad_cut = kit.slab("pad_cut", kit.rounded([(knee.x - 0.06, knee.z - 0.08), (knee.x + 0.06, knee.z - 0.08), (knee.x + 0.06, knee.z + 0.07), (knee.x - 0.06, knee.z + 0.07)], 0.03), -0.4, knee.y - 0.01)
        pad = kit.plate(flesh, pad_cut, "kneepad", "slate", offset=0.03, thick=0.014, bevel=0.005, bones=THIGHS | SHINS)
        c.rigid(pad, "lower_leg." + s)
        c.add(kit.band("pad_strap", knee + Vector((0, 0.01, -0.05)), (0.06, 0.06), 0.02, 0.006, "webbing", axis=(0, 0, 1)), ["lower_leg." + s])

    # Climbing boots: leather uppers, rubber soles with a clay toe cap.
    for s, sx in (("L", 1), ("R", -1)):
        boot = kit.shell(flesh, lambda p, sx=sx: p.z < 0.2 and p.x * sx > 0, "boot", "leather", offset=0.012, thick=0.006,
                         bones={"foot." + s, "lower_leg." + s})
        c.add(boot, ["foot." + s, "lower_leg." + s])
        f0, f1 = b.j("foot." + s, 0.0), b.j("foot." + s, 1.0)
        sole_pts = kit.rounded([(f0.x - 0.05, 0.085), (f0.x + 0.05, 0.085), (f0.x + 0.055, -0.17), (f0.x - 0.045, -0.17)], 0.035)
        sole = kit.plan("sole", sole_pts, 0.025, "rubber", z=0.0125, bevel=0.003)
        kit.cut(sole, *kit.slots("tread", -0.15, 0.06, 9, -0.002, 0.006, f0.x - 0.07, f0.x + 0.07))
        c.rigid(sole, "foot." + s)
        c.rigid(kit.block("toecap", (f0.x + sx * 0.002, -0.165, 0.04), (0.085, 0.03, 0.045), "clay", bevel=0.008), "foot." + s)
        for i in range(3):
            c.rigid(kit.block("lace", (f0.x, -0.07 + i * 0.03, 0.09 + i * 0.025), (0.05, 0.008, 0.006), "cream", bevel=0.001, rot=-30), "foot." + s)
    c.cover(FEET | SHINS, lambda p: p.z < 0.17)

    # Chalk bag on the back of the belt.
    bag = kit.cyl("chalkbag", (-0.07, 0.15, 0.86), (-0.07, 0.15, 0.95), 0.045, "clay", r1=0.05, segs=20, bevel=0.004)
    c.rigid(bag, "hips")
    c.rigid(kit.ring("bag_rim", (-0.07, 0.15, 0.955), (0, 0, 1), 0.053, 0.043, 0.014, "slate"), "hips")
    return c


SPEC = {"build": build, "faction": "deserters", "budget": (25000, 75000),
        "loadout": "smg",
        "colors": {"primary": "#141413", "secondary": "#D4A27F", "accent": "#D97757"}}
