"""The Scrappers' Mule: a welded hauler with a hold you can walk into. Box hull with a side bay that
makes the right flank longer than the left, a rear ramp between one big engine and one small,
tanks and pipework down the left, a crane folded over the roof, canvas over the cargo, a winch,
tyre bumpers, a ladder, a smoke stack. Brass, copper, rust, leather and hazard yellow. Inside:
crates, barrels, chains, a workbench, the pilot's seat and a greasy console."""

from kit import (Ship, bell, block, cabin, chain, console, crate, cyl, handrail, hinge, label, light_strip, locker, nav_light, pipe,
                 prism, ramp, rivets, seams, seat, side_plate, skid, stripe, tube)

REST = 1.9
FLOOR = -1.36
CEIL = 1.96
HALF = 2.86


def build():
    s = Ship("mule")
    # Hull: a hollow rust box with brass and copper plates welded on, open at the back.
    cabin(s, (0, 0, 0.3), (6.0, 11.0, 3.6), "rust", wall=0.14, opening=(2.0, 2.8), bevel=0.06)
    seams(s, (0, 0, 0.3), (6.0, 11.0, 3.6), ys=(-3.0, 0.5, 3.5), xs=(-1.8, 1.8), material="rust", width=0.06, proud=0.03)
    s.add(block("bay", (3.4, 0.5, 0.0), (2.0, 12.5, 2.4), "brass", bevel=0.05))
    s.add(side_plate("bayplate", 4.45, (0.5, 0.0), (5.0, 1.8), "copper", thick=0.12, lines=(("y", -1.5), ("y", 1.2), ("z", 0.4))))
    s.add(rivets("bayrv", (4.5, -5.0, 1.0), (4.5, 6.0, 1.0), 16, r=0.045, axis="x"))
    s.add(rivets("bayrv2", (4.5, -5.0, -1.0), (4.5, 6.0, -1.0), 16, r=0.045, axis="x"))
    for i in range(6):
        s.add(stripe("hazard", (4.46, -1.6 + i * 0.7, -0.9), (0.02, 0.35, 0.5), "hazard" if i % 2 == 0 else "black"))
    for y in (-4.0, 3.5):
        s.add(hinge("bayhinge", (4.5, y, 1.1), axis="y", length=0.5))
    s.add(side_plate("leftplate", -3.05, (3.0, 0.9), (4.0, 1.6), "brass", thick=0.12, lines=(("z", 0.0),)))
    s.add(side_plate("leftplate2", -3.05, (-3.5, -0.6), (3.0, 1.4), "copper", thick=0.12, lines=(("y", 0.0),)))
    s.add(rivets("lrv", (-3.1, -5.0, 1.9), (-3.1, 5.0, 1.9), 14, r=0.045, axis="-x"))
    for sx, x in ((-1, -3.05), (1, 3.05)):
        for y in (-4.5, -1.0, 2.5):
            s.add(block("bolt", (x + sx * 0.08, y, 1.6), (0.1, 0.12, 0.12), "steel", bevel=0))
    # Tyre bumpers hung on both flanks, a ladder up the left.
    for y in (-4.5, -2.0, 4.0):
        s.add(tube("tyre", (-3.1, y, -0.9), (-3.4, y, -0.9), 0.45, 0.25, "rubber", segs=16))
    for y in (-3.5, 5.5):
        s.add(tube("tyre", (4.5, y, -0.4), (4.8, y, -0.4), 0.45, 0.25, "rubber", segs=16))
    for z in (-1.0, -0.4, 0.2, 0.8, 1.4):
        s.add(cyl("rung", (-3.3, 5.2, z), (-3.3, 5.7, z), 0.03, "steel", segs=8, bevel=0))
    for y in (5.2, 5.7):
        s.add(cyl("rail", (-3.3, y, -1.3), (-3.3, y, 2.2), 0.03, "steel", segs=8, bevel=0))
    # Cab with a flat windscreen, visor, lamps and a welded bumper with a winch.
    s.add(block("cab", (0, 6.6, 0.9), (4.2, 3.0, 2.6), "rust", bevel=0.06))
    s.add(prism("screen", [(7.6, 1.9), (8.15, 0.5), (8.15, 0.0), (7.6, 0.0)], 3.4, "glass", bevel=0.02), "glass")
    s.add(block("visor", (0, 7.9, 2.2), (4.0, 0.7, 0.14), "copper", bevel=0.02))
    s.add(block("bumper", (0, 8.1, -0.8), (4.6, 0.3, 0.3), "steel", bevel=0.04))
    for x in (-1.5, 0.0, 1.5):
        s.add(block("bumperbar", (x, 7.9, -0.3), (0.2, 0.5, 1.0), "steel", bevel=0.02))
    s.add(cyl("winch", (-0.6, 8.0, -0.4), (0.6, 8.0, -0.4), 0.22, "gunmetal", segs=14, bevel=0.01))
    s.add(block("winchmount", (0, 7.85, -0.55), (1.5, 0.3, 0.5), "steel", bevel=0.01))
    s.add(chain("winchchain", (0, 8.2, -0.4), (0, 8.9, -1.6), links=6))
    s.add(block("hookblock", (0, 8.9, -1.7), (0.2, 0.2, 0.3), "steel", bevel=0))
    for x in (-1.6, 1.6):
        s.add(cyl("lamp", (x, 8.0, 1.0), (x, 8.3, 1.0), 0.25, "lamp", segs=12, bevel=0), "lights")
        s.add(tube("lamprim", (x, 8.0, 1.0), (x, 8.32, 1.0), 0.3, 0.25, "steel", segs=12))
    nav_light(s, "light.0", (-3.2, 8.0, 2.3), "red_light")
    nav_light(s, "light.1", (4.6, 7.0, 1.3), "green_light")
    # Engines flank the door: a big one on the right, a small one on the left, mounts beside the door.
    s.add(cyl("bigengine", (2.6, -4.0, 0.0), (2.6, -7.5, 0.0), 1.2, "gunmetal", segs=22, bevel=0.05))
    s.add(cyl("bigcollar", (2.6, -7.3, 0.0), (2.6, -7.6, 0.0), 1.28, "brass", segs=22, bevel=0.02))
    s.add(bell("bigbell", (2.6, -7.5, 0.0), (2.6, -8.3, 0.0), 0.9, 1.2))
    s.add(rivets("bigrv", (2.6, -4.3, 1.22), (2.6, -7.0, 1.22), 6, r=0.05, axis="z"))
    s.add(cyl("smallengine", (-2.4, -3.5, -0.3), (-2.4, -7.0, -0.3), 0.7, "copper", segs=18, bevel=0.04))
    s.add(bell("smallbell", (-2.4, -7.0, -0.3), (-2.4, -7.6, -0.3), 0.5, 0.72))
    s.add(block("mountr", (2.1, -6.0, 0.0), (1.6, 1.4, 1.6), "rust", bevel=0.05))
    s.add(block("mountl", (-1.9, -6.0, -0.2), (1.2, 1.4, 1.2), "rust", bevel=0.05))
    s.add(pipe("fuelline", [(2.6, -4.0, 1.3), (2.6, -3.0, 1.8), (1.0, -3.0, 2.2)], 0.07))
    s.node("exhaust.0", (2.6, -8.32, 0.0))
    s.node("exhaust.1", (-2.4, -7.62, -0.3))
    # Door frame, hinges and the ramp with chevrons.
    for sx in (-1, 1):
        s.add(block("jamb", (sx * 1.2, -5.52, 0.1), (0.4, 0.2, 3.0), "steel", bevel=0.02))
    s.add(block("lintel", (0, -5.52, 1.75), (2.8, 0.2, 0.3), "steel", bevel=0.02))
    for x in (-0.7, 0.7):
        s.add(hinge("hinge", (x, -5.55, FLOOR + 0.02), axis="x", length=0.4, r=0.045))
    ramp(s, (0, -5.55, FLOOR), 2.0, 3.0, FLOOR + REST, material="rust", thick=0.1)
    # Tanks and pipework down the left flank.
    for y in (-5.0, -1.6, 1.8):
        s.add(cyl("tank", (-3.7, y, 0.6), (-3.7, y + 2.6, 0.6), 0.62, "brass", segs=16, bevel=0.06))
        s.add(block("tankstrap", (-3.7, y + 1.3, 0.6), (1.34, 0.12, 1.34), "leather", bevel=0.005))
        s.add(cyl("valve", (-3.7, y + 2.6, 0.6), (-3.7, y + 2.85, 0.6), 0.12, "steel", segs=10, bevel=0))
    s.add(pipe("pipe", [(-3.7, -2.4, 1.3), (-3.7, -1.9, 1.75), (-3.7, 3.6, 1.75), (-3.7, 4.0, 1.3)], 0.09))
    s.add(pipe("pipe2", [(-3.0, -5.2, 2.0), (-3.5, -5.2, 2.0), (-3.5, -5.2, 1.3)], 0.07))
    s.add(pipe("pipe3", [(-3.1, 0.0, 2.1), (-3.9, 0.0, 2.1), (-3.9, 0.0, 1.3)], 0.06))
    # Crane folded over the roof, a smoke stack, tool boxes, canvas over the cargo.
    s.add(cyl("pivot", (1.2, -1.0, 2.1), (1.2, -1.0, 2.9), 0.45, "gunmetal", segs=16, bevel=0.03))
    s.add(block("arm", (1.2, 1.8, 3.0), (0.36, 6.5, 0.36), "hazard", bevel=0.02))
    s.add(block("armtip", (1.2, 4.9, 2.6), (0.3, 0.3, 0.9), "gunmetal", bevel=0.02))
    s.add(chain("cranechain", (1.2, 4.9, 2.15), (1.2, 4.9, 1.75), links=4))
    s.add(block("cranehook", (1.2, 4.9, 1.65), (0.15, 0.15, 0.2), "steel", bevel=0))
    s.add(cyl("stack", (-1.6, -4.6, 2.0), (-1.6, -4.6, 4.1), 0.26, "rust", segs=12, bevel=0.02))
    s.add(cyl("stackcap", (-1.6, -4.6, 4.05), (-1.6, -4.6, 4.1), 0.36, "black", segs=12, bevel=0.0))
    s.add(block("canvas", (-0.9, -1.6, 2.4), (3.4, 5.0, 0.6), "deserter_tan", bevel=0.1, segs=3, taper=(0.8, 0.9)))
    for y in (-3.4, -1.6, 0.2):
        s.add(block("rope", (-0.9, y, 2.4), (3.5, 0.06, 0.66), "leather", bevel=0.0))
    s.add(crate("toolbox", (-2.2, 3.6, 2.35), (0.9, 0.6, 0.5), material="red"))
    s.add(crate("toolbox2", (2.4, 3.2, 2.35), (0.7, 0.9, 0.5), material="olive"))
    # Outrigger stabilisers with hazard tips make the width.
    for sx in (-1, 1):
        s.add(block("outrigger", (sx * 4.75, -2.0, -0.7), (3.5, 2.6, 0.3), "rust", bevel=0.04))
    for x in (-6.0, 6.0):
        s.add(stripe("outtip", (x, -2.0, -0.7), (1.0, 2.6, 0.3), "hazard"))
        s.add(block("outbrace", (x * 0.6, -2.0, -0.3), (0.3, 1.5, 0.6), "rust", bevel=0.02))
    # Four skids under the box.
    for x in (-2.3, 2.3):
        for y in (4.5, -3.5):
            s.add(skid("skid", (x, y), 2.2, -REST, -1.5, bar=0.26))
    s.add(label("MULE", (4.53, 3.2, 0.5), 0.8, "black", side=1, depth=0.012))
    s.add(label("SCRAP", (-3.14, 0.8, -0.4), 0.5, "hazard", side=-1, depth=0.012))
    s.add(label("MAX 9T", (-3.14, -4.2, 1.6), 0.25, "black", side=-1, depth=0.01))
    # Inside: the hold, with crates, barrels, chains, a workbench and the pilot's seat up front.
    s.add(seat("pilot", (0, 3.6, FLOOR + 0.5), facing=1, material="leather"))
    console(s, (0, 4.8, FLOOR + 0.55), (2.2, 0.7, 1.0), material="rust", screens=2, screen_mat="screen", facing=1)
    s.add(block("wheel", (0, 4.2, FLOOR + 1.0), (0.5, 0.05, 0.5), "black", bevel=0.01))
    s.add(crate("c1", (-1.8, -1.0, FLOOR + 0.45), (1.2, 1.2, 0.9), material="olive"))
    s.add(crate("c2", (-1.8, -1.0, FLOOR + 1.3), (1.0, 1.0, 0.8), material="deserter_tan"))
    s.add(crate("c3", (1.9, -3.5, FLOOR + 0.4), (1.0, 1.4, 0.8), material="red"))
    s.add(crate("c4", (1.9, 1.0, FLOOR + 0.5), (1.2, 1.0, 1.0), material="olive"))
    for i, y in enumerate((-4.2, -3.4, -2.6)):
        s.add(cyl("barrel", (-2.2, y, FLOOR), (-2.2, y, FLOOR + 0.9), 0.32, "brass" if i % 2 else "rust", segs=14, bevel=0.02))
    s.add(block("bench", (2.2, 3.0, FLOOR + 0.9), (1.2, 2.4, 0.08), "steel", bevel=0.005))
    for y in (2.0, 4.0):
        s.add(block("benchleg", (2.2, y, FLOOR + 0.45), (1.0, 0.08, 0.9), "rust", bevel=0))
    s.add(crate("tools", (2.2, 3.4, FLOOR + 1.1), (0.5, 0.4, 0.3), material="red"))
    s.add(locker("locker", (-2.1, 4.9, FLOOR + 1.0), (1.2, 0.5, 2.0), material="grey", doors=2))
    for x, y in ((0.8, -2.0), (-0.6, 1.5), (1.4, -4.5)):
        s.add(chain("chain", (x, y, CEIL), (x, y, CEIL - 1.1), links=10, r=0.035))
        s.add(block("hook", (x, y, CEIL - 1.2), (0.12, 0.05, 0.2), "steel", bevel=0))
    s.add(handrail("rail", (-2.6, -5.0, FLOOR + 1.0), (-2.6, 2.0, FLOOR + 1.0), posts=4))
    light_strip(s, (-1.2, -4.5, CEIL - 0.02), (-1.2, 4.0, CEIL - 0.02))
    light_strip(s, (1.2, -4.5, CEIL - 0.02), (1.2, 4.0, CEIL - 0.02))
    for sx in (-1, 1):
        s.add(stripe("floorhaz", (sx * 2.6, -0.5, FLOOR), (0.2, 10.0, 0.0), "hazard"))
    s.add(block("floorplate", (0, -0.2, FLOOR + 0.01), (5.4, 10.4, 0.02), "gunmetal", bevel=0))
    s.node("heat", (0, 8.2, 0.3))
    return s


SPEC = {
    "build": build,
    "size": (17.4, 13.0, 6.0),
    "rest": REST,
    "cabin": (FLOOR, CEIL, HALF),
    "nodes": ["exhaust.0", "exhaust.1", "heat", "ramp", "light.0", "light.1"],
    "view": {"cam": (19.0, -15.0, 8.0), "look": (0, 0.0, 0.8), "lens": 40},
    "inside": {"cam": (0.3, -8.4, FLOOR + 1.6), "look": (0, 4.0, FLOOR + 1.0), "lens": 22},
}
