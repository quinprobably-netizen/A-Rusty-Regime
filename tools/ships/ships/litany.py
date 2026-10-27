"""The Regime's Litany: a cathedral in flight. Long narrow hull, a tall dorsal spire, slit-window
galleries down each flank, three censer engines in a trefoil, a prow blade. Slate and bone with
gold trim, symmetrical and pristine."""

from kit import Ship, bell, block, cyl, label, leg, prism, rivets, seams, side_plate, stripe, tube

REST = 2.2


def build():
    s = Ship("litany")
    slate, bone, gold = "slate", "bone", "gold"
    # Hull and prow.
    s.add(block("body", (0, 0, 0), (3.0, 18.0, 3.2), slate, bevel=0.1, segs=3))
    seams(s, (0, 0, 0), (3.0, 18.0, 3.2), ys=(-6.0, -2.5, 1.5, 5.5), xs=(-0.9, 0.9))
    s.add(prism("prow", [(9.0, 1.6), (11.2, 0.3), (10.4, -1.2), (9.0, -1.6)], 1.4, bone, bevel=0.06, segs=3))
    s.add(prism("blade", [(9.0, 1.7), (11.4, 0.3), (9.0, -1.7)], 0.16, gold, bevel=0.02))
    s.add(block("keel", (0, 1.0, -1.65), (0.9, 15.0, 0.3), bone, bevel=0.04))
    # Bone plating along the flanks and the roof, with gold rivet rows.
    for x in (-1.55, 1.55):
        side = -1 if x < 0 else 1
        s.add(side_plate("lower", x, (0.5, -0.85), (15.0, 1.1), bone, lines=(("y", -5.0), ("y", -1.0), ("y", 3.0), ("y", 6.0))))
        s.add(side_plate("upper", x, (-1.0, 1.25), (12.0, 0.5), bone, lines=(("y", -3.0), ("y", 2.0))))
        s.add(rivets("rv", (x + side * 0.05, -6.8, -0.25), (x + side * 0.05, 7.8, -0.25), 22, r=0.04, material=gold, axis="x" if x > 0 else "-x"))
        # The gallery: slit windows between the plates.
        for i in range(8):
            y = -5.6 + i * 1.6
            s.add(block("slit", (x + side * 0.02, y, 0.25), (0.06, 0.32, 0.9), "glass", bevel=0), "glass")
            s.add(block("mullion", (x + side * 0.04, y + 0.8, 0.25), (0.08, 0.14, 1.0), gold, bevel=0))
    s.add(block("roof", (0, 3.0, 1.62), (2.0, 10.0, 0.1), bone, bevel=0.02))
    s.add(stripe("roofline", (0, 3.0, 1.62), (0.2, 10.0, 0.1), gold))
    # The spire: a raked dorsal fin with bone faces and a gold crest.
    s.add(prism("spire", [(-7.5, 1.5), (1.0, 1.5), (-1.6, 6.8), (-5.2, 6.8)], 0.6, slate, bevel=0.05))
    for x in (-0.32, 0.32):
        s.add(prism("spireface", [(-6.6, 2.0), (-0.3, 2.0), (-2.2, 6.3), (-5.0, 6.3)], 0.08, bone, x=x, bevel=0.01))
        s.add(label("LITANY", (x * 1.5, -3.6, 4.1), 0.7, gold, side=-1 if x < 0 else 1, depth=0.01))
    s.add(block("crest", (0, -3.4, 6.82), (0.7, 3.7, 0.1), gold, bevel=0.01))
    s.add(block("crestfore", (0, -0.9, 5.0), (0.75, 0.12, 3.4), gold, bevel=0.01, rot=0))
    # Buttress stabilisers, bone over gold.
    s.add(block("stab", (0, -5.0, -0.6), (9.0, 3.0, 0.3), bone, bevel=0.04, taper=(0.9, 0.7)))
    for x in (-4.3, 4.3):
        s.add(stripe("stabtip", (x, -5.0, -0.6), (0.4, 3.0, 0.3), gold))
    # Three censer engines in a trefoil: housings, gold collars, flared bells.
    for i, (x, z) in enumerate(((0.0, 1.2), (-1.9, -0.6), (1.9, -0.6))):
        s.add(cyl("housing", (x, -6.5, z), (x, -10.0, z), 0.95, slate, segs=20, bevel=0.05))
        s.add(tube("collar", (x, -9.9, z), (x, -10.2, z), 1.05, 0.85, gold, segs=20))
        s.add(bell("bell", (x, -10.0, z), (x, -11.0, z), 0.72, 1.0))
        s.add(rivets("hrv", (x, -7.0, z + 0.97), (x, -9.6, z + 0.97), 5, r=0.04, material=gold, axis="z"))
        s.node(f"exhaust.{i}", (x, -11.02, z))
    s.add(block("tailblock", (0, -8.2, 0.3), (3.6, 3.4, 2.2), slate, bevel=0.08))
    # Landing legs: two forward, one aft.
    for x, y in ((-1.1, 5.0), (1.1, 5.0), (0.0, -5.5)):
        s.add(leg("leg", (x, y), -REST, -1.5, r=0.16))
    s.node("heat", (0, 11.0, 0.2))
    return s


SPEC = {
    "build": build,
    "size": (22.4, 9.0, 9.0),
    "rest": REST,
    "nodes": ["exhaust.0", "exhaust.1", "exhaust.2", "heat"],
    "view": {"cam": (-22.0, 18.0, 9.0), "look": (0, -0.5, 1.5), "lens": 40},
}
