"""The Regime's Censer: a patrol fighter, the Litany's cathedral styling in miniature. A needle
fuselage of slate with gold ribs, a bone prow over a gold blade and a red lamp at the very nose,
narrow swept-back wings with bone leading edges, a tall thin spire on each wing tip with a gold
finial light, one bell engine in a gold collar, brass incense vents. Fast, slow-turning look.
Solid hull: a small canopy over the pilot's seat, nothing walkable."""

from fighter import band, cockpit
from kit import Ship, bell, block, cyl, label, leg, loft, nav_light, plan, prism, stripe, tube

REST = 1.25
SIDES, PHASE = 8, 22.5  # octagon with a flat roof, keel and flanks
# Fuselage stations (y, x, z, rx, rz), tail to nose.
HULL = [(-4.0, 0, 0, 0.52, 0.56), (-3.0, 0, 0, 0.66, 0.70), (-1.5, 0, 0, 0.70, 0.76), (0.0, 0, 0, 0.66, 0.72),
        (1.5, 0, 0, 0.56, 0.64), (3.0, 0, -0.02, 0.40, 0.44), (4.2, 0, -0.04, 0.22, 0.24), (5.0, 0, -0.05, 0.09, 0.09),
        (5.4, 0, -0.05, 0, 0)]
K = 0.924  # a flat face of the octagon sits at K * radius


def build():
    s = Ship("censer")
    slate, bone, gold = "slate", "bone", "gold"
    hull = loft("fuselage", HULL, slate, sides=SIDES, phase=PHASE)
    canopy = [(0.55, 0, 0.42, 0.0, 0.0), (0.9, 0, 0.42, 0.30, 0.45), (1.5, 0, 0.42, 0.38, 0.66), (2.3, 0, 0.42, 0.34, 0.56),
              (3.0, 0, 0.40, 0.20, 0.30), (3.4, 0, 0.38, 0, 0)]
    hull = cockpit(s, hull, ((0, 1.55, 0.25), (0.62, 1.5, 1.1)), canopy, (0, 1.75, -0.08), sides=SIDES, phase=PHASE,
                   hull_mat=slate, seat_mat="red", frame=bone, trim=gold, screen="gold_light", hoops=(1.2, 2.3))
    s.add(hull)
    # Gold ribs round the needle, a gold roofline behind the canopy, bone keel plating.
    for y in (-3.3, -2.2, -1.1, 0.0, 3.7):
        s.add(band("rib", HULL, y, 0.1, gold, sides=SIDES, phase=PHASE))
    s.add(band("collar", HULL, -3.85, 0.3, bone, sides=SIDES, phase=PHASE))
    s.add(stripe("roofline", (0, -1.8, K * 0.74), (0.14, 3.6, 0.02), gold))
    s.add(block("keel", (0, -0.8, -K * 0.72 - 0.03), (0.34, 5.0, 0.08), bone, bevel=0.02))
    # The prow: a bone collar, the gold blade under it, the red lamp at the tip.
    s.add(band("prow", HULL, 4.0, 0.8, bone, grow=1.02, sides=SIDES, phase=PHASE))
    s.add(prism("blade", [(2.4, -0.42), (5.35, -0.06), (4.6, -0.3), (2.4, -0.82)], 0.06, gold, bevel=0.005))
    nav_light(s, "light.0", (0, 5.42, -0.05), "red_light", r=0.1)
    # Brass incense vents low on each flank, gold slit windows behind the canopy.
    for sx in (-1, 1):
        for y in (-2.6, -2.25, -1.9):
            s.add(tube("vent", (sx * 0.6, y, -0.25), (sx * 0.82, y, -0.25), 0.06, 0.04, "brass", segs=10))
        for y in (-0.5, -0.2, 0.1):
            s.add(block("slit", (sx * K * 0.69, y, 0.25), (0.03, 0.12, 0.34), "glass", bevel=0), "glass")
    # Narrow swept-back wings with bone leading edges and gold tips.
    for sx in (-1, 1):
        s.add(plan("wing", [(sx * 0.5, 0.2), (sx * 3.4, -2.5), (sx * 3.4, -3.2), (sx * 0.5, -2.9)], 0.14, slate, z=-0.12, bevel=0.02))
        s.add(plan("edge", [(sx * 0.55, 0.2), (sx * 3.4, -2.5), (sx * 3.4, -2.75), (sx * 0.55, -0.15)], 0.16, bone, z=-0.12, bevel=0.01))
        s.add(block("flap", (sx * 1.9, -2.9, -0.12), (2.0, 0.3, 0.1), bone, bevel=0.01))
        # The spire: a tall thin raked fin on the tip, bone faces, a gold rib, a gold finial light.
        x = sx * 3.45
        s.add(prism("spire", [(-3.3, -0.12), (-2.45, -0.12), (-3.0, 1.6), (-3.2, 2.5), (-3.35, 2.5)], 0.14, slate, x=x, bevel=0.015))
        s.add(prism("spirefoot", [(-3.25, -0.12), (-2.65, -0.12), (-3.1, -0.75)], 0.12, slate, x=x, bevel=0.01))
        for fx in (-0.075, 0.075):
            s.add(prism("spireface", [(-3.22, 0.1), (-2.75, 0.1), (-3.06, 1.5), (-3.22, 1.5)], 0.02, bone, x=x + fx, bevel=0))
        s.add(prism("spirerib", [(-3.34, 2.2), (-3.18, 2.2), (-2.6, 0.0), (-2.76, 0.0)], 0.16, gold, x=x, bevel=0))
        s.add(cyl("finial", (x, -3.27, 2.5), (x, -3.27, 2.85), 0.03, gold, segs=8, bevel=0))
        nav_light(s, f"light.{1 if sx < 0 else 2}", (x, -3.27, 2.9), "gold_light", r=0.07)
        s.add(label("CENSER", (x + sx * 0.08, -3.0, 0.75), 0.16, gold, side=sx, depth=0.006))
    # One bell engine in a gold collar, rivetted housing.
    s.add(cyl("housing", (0, -3.2, 0), (0, -4.5, 0), 0.6, slate, segs=SIDES * 2, bevel=0.02))
    s.add(tube("collar", (0, -4.4, 0), (0, -4.65, 0), 0.66, 0.5, gold, segs=16))
    s.add(bell("bell", (0, -4.5, 0), (0, -5.25, 0), 0.42, 0.6, segs=18))
    s.node("exhaust.0", (0, -5.27, 0))
    s.add(prism("tailspike", [(-4.4, 0.55), (-3.0, 0.55), (-3.4, 1.15), (-4.3, 1.15)], 0.1, slate, bevel=0.01))
    s.add(stripe("tailtip", (0, -3.85, 1.12), (0.1, 0.9, 0.06), gold))
    nav_light(s, "light.3", (0, -4.3, 1.22), "red_light", r=0.06)
    # Three short landing legs.
    s.add(leg("noseleg", (0, 3.0), -REST, -0.35, r=0.07))
    for sx in (-1, 1):
        s.add(leg("leg", (sx * 1.3, -1.9), -REST, -0.15, r=0.08))
    s.node("heat", (0, 5.5, -0.05))
    return s


SPEC = {
    "build": build,
    "size": (10.8, 7.1, 4.2),
    "rest": REST,
    "nodes": ["exhaust.0", "heat", "light.0", "light.1", "light.2", "light.3"],
    "view": {"cam": (-8.5, 9.0, 4.5), "look": (0, -0.2, 0.4), "lens": 40},
    "top": {"cam": (0, -0.31, 26.0), "look": (0, -0.3, 0), "lens": 50},
}
