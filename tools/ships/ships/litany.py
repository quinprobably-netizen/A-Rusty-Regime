"""The Regime's Litany: a cathedral in flight you can walk through. Long narrow nave with a rear
ramp between two bell engines (a third rides the roof), a tall dorsal spire, slit-window galleries
down each flank, buttress stabilisers with braziers, a prow blade. Slate and bone with gold ribs,
symmetrical and pristine. Inside: pews, a lectern, an altar console, candles and gold ribs."""

from kit import (Ship, bell, block, cabin, console, cyl, handrail, hinge, label, leg, light_strip, nav_light, prism, ramp, rivets, seams,
                 seat, side_plate, sphere, stripe, tube)

REST = 2.2
FLOOR = -1.48
CEIL = 1.48
HALF = 1.38


def build():
    s = Ship("litany")
    slate, bone, gold = "slate", "bone", "gold"
    # The nave: a hollow hull with the doorway aft.
    cabin(s, (0, 0, 0), (3.0, 18.0, 3.2), slate, wall=0.12, opening=(1.6, 2.5), bevel=0.1)
    seams(s, (0, 0, 0), (3.0, 18.0, 3.2), ys=(-6.0, -2.5, 1.5, 5.5), xs=(-0.9, 0.9))
    s.add(prism("prow", [(9.0, 1.6), (11.2, 0.3), (10.4, -1.2), (9.0, -1.6)], 1.4, bone, bevel=0.06, segs=3))
    s.add(prism("blade", [(9.0, 1.7), (11.4, 0.3), (9.0, -1.7)], 0.16, gold, bevel=0.02))
    s.add(block("keel", (0, 1.0, -1.65), (0.9, 15.0, 0.3), bone, bevel=0.04))
    # Gold ribs round the hull every few metres, a crest line down the roof.
    for y in (-7.0, -4.0, -1.0, 2.0, 5.0, 8.0):
        s.add(block("rib", (0, y, 1.62), (3.1, 0.16, 0.08), gold, bevel=0.005))
        s.add(block("rib", (0, y, -1.62), (3.1, 0.16, 0.08), gold, bevel=0.005))
        for sx in (-1, 1):
            s.add(block("rib", (sx * 1.56, y, 0), (0.08, 0.16, 3.2), gold, bevel=0.005))
    # Bone plating along the flanks, the gallery of slit windows, gold rivets, mullions.
    for x in (-1.56, 1.56):
        side = -1 if x < 0 else 1
        ax = "x" if side > 0 else "-x"
        s.add(side_plate("lower", x, (0.5, -0.9), (15.0, 1.0), bone, lines=(("y", -5.0), ("y", -1.0), ("y", 3.0), ("y", 6.0))))
        s.add(side_plate("upper", x, (-0.5, 1.25), (13.0, 0.45), bone, lines=(("y", -3.0), ("y", 2.0))))
        s.add(rivets("rv", (x + side * 0.05, -7.8, -0.3), (x + side * 0.05, 8.0, -0.3), 24, r=0.04, material=gold, axis=ax))
        s.add(rivets("rv2", (x + side * 0.05, -7.8, 1.5), (x + side * 0.05, 8.0, 1.5), 24, r=0.035, material=gold, axis=ax))
        for i in range(9):
            y = -6.4 + i * 1.6
            s.add(block("slit", (x + side * 0.02, y, 0.3), (0.06, 0.3, 1.0), "glass", bevel=0), "glass")
            s.add(block("mullion", (x + side * 0.05, y + 0.8, 0.3), (0.1, 0.14, 1.1), gold, bevel=0))
            s.add(block("sill", (x + side * 0.08, y, -0.3), (0.16, 0.5, 0.06), gold, bevel=0))
        # Incense vents: three short tubes low on each flank.
        for y in (-3.0, -2.5, -2.0):
            s.add(tube("vent", (x, y, -1.2), (x + side * 0.25, y, -1.2), 0.08, 0.05, "brass", segs=10))
    s.add(block("roof", (0, 3.0, 1.62), (2.0, 10.0, 0.1), bone, bevel=0.02))
    s.add(stripe("roofline", (0, 3.0, 1.62), (0.2, 10.0, 0.1), gold))
    # Door frame: gold jambs and lintel, the hinges, the ramp.
    for sx in (-1, 1):
        s.add(block("jamb", (sx * 0.98, -9.02, -0.2), (0.34, 0.24, 2.7), gold, bevel=0.02))
    s.add(prism("arch", [(-8.9, 1.1), (-8.9, 1.6), (-9.14, 1.6), (-9.14, 1.1)], 2.3, gold, bevel=0.01))
    for x in (-0.55, 0.55):
        s.add(hinge("hinge", (x, -9.05, FLOOR + 0.02), axis="x", length=0.3, material=gold))
    ramp(s, (0, -9.05, FLOOR), 1.6, 3.2, FLOOR + REST, material="slate")
    # The spire: a raked dorsal fin with bone faces, a gold crest and the name.
    s.add(prism("spire", [(-7.5, 1.5), (1.0, 1.5), (-1.6, 6.8), (-5.2, 6.8)], 0.6, slate, bevel=0.05))
    for x in (-0.32, 0.32):
        s.add(prism("spireface", [(-6.6, 2.0), (-0.3, 2.0), (-2.2, 6.3), (-5.0, 6.3)], 0.08, bone, x=x, bevel=0.01))
        s.add(prism("spirerib", [(-5.9, 2.0), (-5.6, 2.0), (-3.6, 6.3), (-3.9, 6.3)], 0.1, gold, x=x * 1.05, bevel=0))
        s.add(label("LITANY", (x * 1.6, -3.6, 4.1), 0.7, gold, side=-1 if x < 0 else 1, depth=0.01))
    s.add(block("crest", (0, -3.4, 6.82), (0.7, 3.7, 0.1), gold, bevel=0.01))
    s.add(block("crestfore", (0, -0.9, 5.0), (0.75, 0.12, 3.4), gold, bevel=0.01))
    s.add(cyl("finial", (0, -3.4, 6.85), (0, -3.4, 7.6), 0.05, gold, segs=8, bevel=0))
    nav_light(s, "light.0", (0, -3.4, 7.65), "gold_light", r=0.1)
    # Buttress stabilisers, bone over gold, with a brazier at each tip.
    for sx in (-1, 1):
        s.add(block("stab", (sx * 3.0, -5.0, -0.6), (3.0, 3.0, 0.3), bone, bevel=0.04, taper=(0.9, 0.7)))
    for sx in (-1, 1):
        x = sx * 4.3
        s.add(stripe("stabtip", (x, -5.0, -0.6), (0.4, 3.0, 0.3), gold))
        s.add(block("buttress", (sx * 2.6, -5.0, 0.6), (0.3, 2.0, 2.2), bone, bevel=0.03, rot=0))
        s.add(cyl("brazier", (x, -5.0, -0.45), (x, -5.0, 0.0), 0.3, gold, r1=0.45, segs=14, bevel=0.01))
        s.add(sphere("ember", (x, -5.0, 0.05), 0.3, "gold_light", segs=10), "lights")
        s.node(f"light.{1 if sx < 0 else 2}", (x, -5.0, 0.1))
    # Three censer engines: two flanking the door, one on the roof; collars, bells, rivets.
    for i, (x, z) in enumerate(((-2.0, -0.4), (2.0, -0.4), (0.0, 2.3))):
        s.add(cyl("housing", (x, -6.5, z), (x, -10.0, z), 0.95, slate, segs=20, bevel=0.05))
        s.add(cyl("mount", (x, -7.5, z), (x, -8.5, z), 1.05, bone, segs=20, bevel=0.02))
        s.add(tube("collar", (x, -9.9, z), (x, -10.2, z), 1.05, 0.85, gold, segs=20))
        s.add(bell("bell", (x, -10.0, z), (x, -11.0, z), 0.72, 1.0))
        s.add(rivets("hrv", (x, -7.0, z + 0.97), (x, -9.6, z + 0.97), 5, r=0.04, material=gold, axis="z"))
        s.node(f"exhaust.{i}", (x, -11.02, z))
    s.add(block("roofmount", (0, -8.2, 1.8), (1.4, 3.0, 0.5), slate, bevel=0.03))
    # Landing legs: two forward, two aft.
    for x, y in ((-1.1, 5.0), (1.1, 5.0), (-1.1, -6.0), (1.1, -6.0)):
        s.add(leg("leg", (x, y), -REST, -1.5, r=0.16))
    # Inside: pews either side of the aisle, a lectern, the altar console, candles, ribs, light.
    for i in range(5):
        y = -6.0 + i * 1.7
        for sx in (-1, 1):
            s.add(seat("pew", (sx * 0.75, y, FLOOR + 0.45), facing=1, material="leather", frame=gold, w=0.9))
    s.add(seat("throne", (0, 5.2, FLOOR + 0.5), facing=1, material="red", frame=gold, w=0.7))
    console(s, (0, 6.6, FLOOR + 0.55), (2.0, 0.7, 1.1), material=bone, screens=3, screen_mat="gold_light", facing=1)
    s.add(block("lectern", (0, 3.4, FLOOR + 0.6), (0.4, 0.3, 1.2), gold, bevel=0.01))
    s.add(block("book", (0, 3.3, FLOOR + 1.22), (0.5, 0.4, 0.06), bone, bevel=0.005, rot=-20))
    for i in range(6):
        y = -7.0 + i * 2.6
        for sx in (-1, 1):
            s.add(cyl("stand", (sx * 1.2, y, FLOOR), (sx * 1.2, y, FLOOR + 1.1), 0.03, gold, segs=8, bevel=0))
            s.add(cyl("candle", (sx * 1.2, y, FLOOR + 1.1), (sx * 1.2, y, FLOOR + 1.3), 0.04, bone, segs=8, bevel=0))
            s.add(sphere("flame", (sx * 1.2, y, FLOOR + 1.36), 0.04, "gold_light", segs=6), "lights")
        s.add(block("innerrib", (0, y + 1.3, CEIL - 0.05), (2.7, 0.1, 0.1), gold, bevel=0))
        for sx in (-1, 1):
            s.add(block("innerrib", (sx * 1.33, y + 1.3, 0), (0.1, 0.1, 2.9), gold, bevel=0))
    for sx in (-1, 1):
        s.add(block("banner", (sx * 1.3, 1.0, FLOOR + 1.6), (0.04, 0.8, 1.6), "red", bevel=0))
        s.add(block("bannerbar", (sx * 1.3, 1.0, FLOOR + 2.42), (0.08, 1.0, 0.06), gold, bevel=0))
    s.add(handrail("rail", (-1.2, -8.6, FLOOR + 0.9), (-1.2, -7.0, FLOOR + 0.9), posts=2, material=gold))
    light_strip(s, (0, -8.0, CEIL - 0.02), (0, 6.0, CEIL - 0.02), w=0.16, material="gold_light")
    s.add(block("aisle", (0, -1.0, FLOOR + 0.01), (1.0, 15.5, 0.02), "red", bevel=0))
    s.node("heat", (0, 11.0, 0.2))
    return s


SPEC = {
    "build": build,
    "size": (23.5, 9.0, 9.85),
    "rest": REST,
    "cabin": (FLOOR, CEIL, HALF),
    "nodes": ["exhaust.0", "exhaust.1", "exhaust.2", "heat", "ramp", "light.0", "light.1", "light.2"],
    "view": {"cam": (-20.0, -20.0, 9.0), "look": (0, -0.5, 1.5), "lens": 40},
    "inside": {"cam": (0.3, -11.5, FLOOR + 1.6), "look": (0, 5.0, FLOOR + 1.0), "lens": 24},
}
