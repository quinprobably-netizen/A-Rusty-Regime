"""The Scrappers' Mule: a welded hauler. Box hull with a side bay that makes the right flank longer
than the left, one big engine and one small, external tanks and pipe runs down the left, a crane
folded over the roof, canvas lashed over the cargo bay, hazard stripes on the bay door, a smoke
stack. Brass, copper, rust, leather and hazard yellow."""

from kit import Ship, bell, block, cyl, label, pipe, prism, rivets, seams, side_plate, skid, stripe

REST = 1.9


def build():
    s = Ship("mule")
    # Hull: rust box with brass and copper plates welded on, and the side bay on the right.
    s.add(block("body", (0, 0, 0.3), (6.0, 11.0, 3.6), "rust", bevel=0.06))
    seams(s, (0, 0, 0.3), (6.0, 11.0, 3.6), ys=(-3.0, 0.5, 3.5), xs=(-1.8, 1.8), material="rust", width=0.06, proud=0.03)
    s.add(block("bay", (3.4, 0.5, 0.0), (2.0, 12.5, 2.4), "brass", bevel=0.05))
    s.add(side_plate("bayplate", 4.45, (0.5, 0.0), (5.0, 1.8), "copper", thick=0.12, lines=(("y", -1.5), ("y", 1.2), ("z", 0.4))))
    s.add(rivets("bayrv", (4.5, -5.0, 1.0), (4.5, 6.0, 1.0), 16, r=0.045, axis="x"))
    s.add(rivets("bayrv2", (4.5, -5.0, -1.0), (4.5, 6.0, -1.0), 16, r=0.045, axis="x"))
    # Hazard stripes on the bay door.
    for i in range(6):
        s.add(stripe("hazard", (4.46, -1.6 + i * 0.7, -0.9), (0.02, 0.35, 0.5), "hazard" if i % 2 == 0 else "black"))
    s.add(side_plate("leftplate", -3.05, (3.0, 0.9), (4.0, 1.6), "brass", thick=0.12, lines=(("z", 0.0),)))
    s.add(side_plate("leftplate2", -3.05, (-3.5, -0.6), (3.0, 1.4), "copper", thick=0.12, lines=(("y", 0.0),)))
    s.add(rivets("lrv", (-3.1, -5.0, 1.9), (-3.1, 5.0, 1.9), 14, r=0.045, axis="-x"))
    # Cab with a flat windscreen and a bumper of welded bar.
    s.add(block("cab", (0, 6.6, 0.9), (4.2, 3.0, 2.6), "rust", bevel=0.06))
    s.add(prism("screen", [(7.6, 1.9), (8.15, 0.5), (8.15, 0.0), (7.6, 0.0)], 3.4, "glass", bevel=0.02), "glass")
    s.add(block("visor", (0, 7.9, 2.2), (4.0, 0.7, 0.14), "copper", bevel=0.02))
    s.add(block("bumper", (0, 8.1, -0.8), (4.6, 0.3, 0.3), "steel", bevel=0.04))
    for x in (-1.5, 0.0, 1.5):
        s.add(block("bumperbar", (x, 7.9, -0.3), (0.2, 0.5, 1.0), "steel", bevel=0.02))
    s.add(cyl("lamp", (-1.6, 8.0, 1.0), (-1.6, 8.3, 1.0), 0.25, "lamp", segs=12, bevel=0), "lights")
    s.add(cyl("lamp", (1.6, 8.0, 1.0), (1.6, 8.3, 1.0), 0.25, "lamp", segs=12, bevel=0), "lights")
    # Engines: a big one on the right, a small one on the left, with brass collars.
    s.add(cyl("bigengine", (2.6, -4.0, 0.0), (2.6, -7.5, 0.0), 1.2, "gunmetal", segs=22, bevel=0.05))
    s.add(cyl("bigcollar", (2.6, -7.3, 0.0), (2.6, -7.6, 0.0), 1.28, "brass", segs=22, bevel=0.02))
    s.add(bell("bigbell", (2.6, -7.5, 0.0), (2.6, -8.3, 0.0), 0.9, 1.2))
    s.add(rivets("bigrv", (2.6, -4.3, 1.22), (2.6, -7.0, 1.22), 6, r=0.05, axis="z"))
    s.add(cyl("smallengine", (-2.4, -3.5, -0.3), (-2.4, -7.0, -0.3), 0.7, "copper", segs=18, bevel=0.04))
    s.add(bell("smallbell", (-2.4, -7.0, -0.3), (-2.4, -7.6, -0.3), 0.5, 0.72))
    s.add(block("enginemount", (0.0, -6.0, 0.0), (5.4, 1.4, 1.8), "rust", bevel=0.05))
    s.node("exhaust.0", (2.6, -8.32, 0.0))
    s.node("exhaust.1", (-2.4, -7.62, -0.3))
    # Tanks and pipework down the left flank.
    for y in (-5.0, -1.6, 1.8):
        s.add(cyl("tank", (-3.7, y, 0.6), (-3.7, y + 2.6, 0.6), 0.62, "brass", segs=16, bevel=0.06))
        s.add(block("tankstrap", (-3.7, y + 1.3, 0.6), (1.34, 0.12, 1.34), "leather", bevel=0.005))
    s.add(pipe("pipe", [(-3.7, -2.4, 1.3), (-3.7, -1.9, 1.75), (-3.7, 3.6, 1.75), (-3.7, 4.0, 1.3)], 0.09))
    s.add(pipe("pipe2", [(-3.0, -5.2, 2.0), (-3.5, -5.2, 2.0), (-3.5, -5.2, 1.3)], 0.07))
    # Crane folded over the roof, a smoke stack, canvas over the cargo bay.
    s.add(cyl("pivot", (1.2, -1.0, 2.1), (1.2, -1.0, 2.9), 0.45, "gunmetal", segs=16, bevel=0.03))
    s.add(block("arm", (1.2, 1.8, 3.0), (0.36, 6.5, 0.36), "hazard", bevel=0.02))
    s.add(block("armtip", (1.2, 4.9, 2.6), (0.3, 0.3, 0.9), "gunmetal", bevel=0.02))
    s.add(cyl("stack", (-1.6, -4.6, 2.0), (-1.6, -4.6, 4.1), 0.26, "rust", segs=12, bevel=0.02))
    s.add(cyl("stackcap", (-1.6, -4.6, 4.05), (-1.6, -4.6, 4.1), 0.36, "black", segs=12, bevel=0.0))
    s.add(block("canvas", (-0.9, -1.6, 2.4), (3.4, 5.0, 0.6), "deserter_tan", bevel=0.1, segs=3, taper=(0.8, 0.9)))
    for y in (-3.4, -1.6, 0.2):
        s.add(block("rope", (-0.9, y, 2.4), (3.5, 0.06, 0.66), "leather", bevel=0.0))
    # Outrigger stabilisers with hazard tips make the width.
    s.add(block("outrigger", (0, -2.0, -0.7), (13.0, 2.6, 0.3), "rust", bevel=0.04))
    for x in (-6.0, 6.0):
        s.add(stripe("outtip", (x, -2.0, -0.7), (1.0, 2.6, 0.3), "hazard"))
    # Four skids under the box.
    for x in (-2.3, 2.3):
        for y in (4.5, -3.5):
            s.add(skid("skid", (x, y), 2.2, -REST, -1.5, bar=0.26))
    s.add(label("MULE", (4.53, 3.2, 0.5), 0.8, "black", side=1, depth=0.012))
    s.add(label("SCRAP", (-3.14, 0.8, -0.4), 0.5, "hazard", side=-1, depth=0.012))
    s.node("heat", (0, 8.2, 0.3))
    return s


SPEC = {
    "build": build,
    "size": (16.5, 13.0, 6.0),
    "rest": REST,
    "nodes": ["exhaust.0", "exhaust.1", "heat"],
    "view": {"cam": (18.0, 16.0, 8.0), "look": (0, 0.0, 0.8), "lens": 40},
}
