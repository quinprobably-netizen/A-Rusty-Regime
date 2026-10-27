"""The Deserters' Kestrel: a patched ex-military gunship. Slab fuselage, stub wings with twin pod
engines, raised canopy, chin gun, raked tail fin, four skids. Dark hull, pale panels, orange
stripes, tan canvas lashed to the roof."""

from kit import Ship, bell, block, cyl, label, prism, rivets, seams, side_plate, skid, stripe

REST = 1.45


def build():
    s = Ship("kestrel")
    dark, pale, orange, tan = "deserter_dark", "deserter_pale", "deserter_orange", "deserter_tan"
    # Fuselage: slab with a chamfered nose and a boat tail.
    s.add(block("body", (0, -0.5, 0), (2.4, 9.0, 1.6), dark, bevel=0.08, segs=3))
    seams(s, (0, -0.5, 0), (2.4, 9.0, 1.6), ys=(-3.4, -1.0, 1.6, 3.6), xs=(-0.7, 0.7))
    nose = prism("nose", [(3.9, 0.8), (6.0, 0.55), (7.0, 0.05), (6.6, -0.55), (3.9, -0.8)], 2.2, dark, bevel=0.06, segs=3)
    # Louvred vents on the nose cheeks.
    s.add(nose)
    for x in (-1.08, 1.08):
        for i in range(4):
            s.add(block("vent", (x, 4.6 + i * 0.28, 0.1), (0.06, 0.07, 0.5), "black", bevel=0))
    s.add(block("spine", (0, -2.0, 0.84), (0.5, 6.0, 0.12), dark, bevel=0.03))
    s.add(cyl("antenna", (-0.9, 3.2, 0.8), (-0.9, 3.0, 2.3), 0.025, "steel", segs=6, bevel=0))
    s.add(block("hook", (0, -0.2, -0.95), (0.6, 0.9, 0.35), "gunmetal", bevel=0.02))
    s.add(prism("tail", [(-5.0, 0.8), (-5.0, -0.8), (-6.2, -0.35), (-6.2, 0.45)], 2.0, dark, bevel=0.05))
    # Canopy and the nose glass seam.
    s.add(prism("canopy", [(1.4, 0.8), (3.4, 0.8), (4.6, 0.5), (4.6, 0.3), (1.0, 1.3), (0.6, 1.3)], 1.6, "glass", bevel=0.03), "glass")
    s.add(prism("frame", [(0.5, 0.78), (1.4, 0.78), (0.5, 1.35), (0.2, 1.35)], 1.7, dark, bevel=0.02))
    # Pale armour plates bolted on the flanks and roof, with panel lines.
    for x in (-1.25, 1.25):
        side = -1 if x < 0 else 1
        s.add(side_plate("flank", x, (-2.3, 0.1), (4.6, 1.2), pale, lines=(("y", -1.0), ("y", 1.2), ("z", 0.35))))
        s.add(side_plate("flankfore", x, (1.6, -0.25), (2.4, 0.9), pale, lines=(("z", 0.0),)))
        s.add(rivets("rv", (x + side * 0.05, -4.4, -0.45), (x + side * 0.05, 2.6, -0.45), 14, axis="x" if x > 0 else "-x"))
        s.add(rivets("rv", (x + side * 0.05, -4.4, 0.62), (x + side * 0.05, 0.0, 0.62), 9, axis="x" if x > 0 else "-x"))
    s.add(block("roofplate", (0, -2.8, 0.85), (1.8, 3.6, 0.1), pale, bevel=0.02))
    s.add(stripe("roofstripe", (0, -1.2, 0.8), (2.5, 0.5, 0.0), orange))
    # Chin gun under the nose.
    s.add(cyl("turret", (0, 3.6, -0.75), (0, 3.6, -1.15), 0.42, dark, segs=16, bevel=0.02))
    s.add(cyl("barrel", (0, 3.6, -1.0), (0, 6.2, -1.0), 0.09, "steel", segs=10, bevel=0))
    s.add(cyl("barrel2", (0, 3.6, -1.0), (0, 5.4, -1.0), 0.14, dark, segs=10, bevel=0))
    # Stub wings with orange tips, pylons and twin pod engines.
    s.add(block("wing", (0, -1.0, -0.2), (11.0, 3.5, 0.26), dark, bevel=0.04, taper=(1.0, 0.85)))
    for x in (-5.0, 5.0):
        s.add(stripe("tip", (x, -1.0, -0.2), (1.0, 3.5, 0.26), orange))
        s.add(block("flap", (x * 0.55, -2.95, -0.2), (3.6, 0.5, 0.18), pale, bevel=0.02))
    for x in (-1.9, 1.9):
        s.add(block("pylon", (x, -2.0, -0.55), (0.3, 1.8, 0.5), dark, bevel=0.02))
        s.add(cyl("pod", (x, -1.4, -0.8), (x, -5.6, -0.8), 0.62, "gunmetal", segs=20, bevel=0.04))
        s.add(cyl("intake", (x, -1.4, -0.8), (x, -1.1, -0.8), 0.62, dark, r1=0.42, segs=20, bevel=0.02))
        s.add(bell("bell", (x, -5.6, -0.8), (x, -6.6, -0.8), 0.46, 0.6))
        s.add(rivets("podrv", (x, -1.7, -0.15), (x, -5.3, -0.15), 7, axis="z"))
        s.node(f"exhaust.{0 if x < 0 else 1}", (x, -6.62, -0.8))
    # Tail: raked fin and a stabiliser, both orange.
    s.add(prism("fin", [(-5.9, 0.6), (-3.2, 0.6), (-4.3, 3.0), (-5.9, 3.0)], 0.22, orange, bevel=0.03))
    s.add(block("stab", (0, -5.4, 1.1), (3.4, 0.9, 0.14), orange, bevel=0.02))
    s.add(block("rudder", (0, -6.0, 2.0), (0.14, 0.5, 1.6), pale, bevel=0.02))
    # Canvas roll and straps on the roof: the Deserters carry everything they own.
    s.add(cyl("roll", (0.65, -3.9, 1.1), (0.65, -1.6, 1.1), 0.28, tan, segs=14, bevel=0.03))
    s.add(block("crate", (-0.55, -3.3, 1.08), (0.7, 1.2, 0.5), tan, bevel=0.03))
    for y in (-3.6, -2.0):
        s.add(block("strap", (0.65, y, 1.1), (0.62, 0.08, 0.62), "leather", bevel=0.005))
    # Skids: two a side, bars at -1.45.
    for x in (-1.15, 1.15):
        for y in (2.2, -2.6):
            s.add(skid("skid", (x, y), 1.8, -REST, -0.78))
    # Markings.
    s.add(label("DSR-07", (-1.33, 1.6, 0.35), 0.5, pale, side=-1, depth=0.01))
    s.add(label("07", (1.33, 1.6, 0.35), 0.5, orange, side=1, depth=0.01))
    s.node("heat", (0, 6.4, 0.0))
    return s


SPEC = {
    "build": build,
    "size": (13.7, 11.0, 4.45),
    "rest": REST,
    "nodes": ["exhaust.0", "exhaust.1", "heat"],
    "view": {"cam": (-14.0, 13.0, 6.0), "look": (0, -0.5, 0.2), "lens": 40},
}
