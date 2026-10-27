"""The Deserters' Kestrel: a patched ex-military gunship you can walk into. Slab fuselage with a
rear ramp, stub wings with twin pod engines and missile pods, raised canopy, chin gun, raked tail
fin, four skids. Dark hull, pale bolted plates, orange stripes, tan canvas and tape. Inside: a
pilot's seat and console, four jump seats, lockers, crates, a canvas roll and a light strip."""

from kit import (Ship, bell, block, cabin, chain, console, crate, cyl, handrail, hinge, label, light_strip, locker, nav_light, pipe,
                 prism, ramp, rivets, seams, seat, side_plate, skid, stripe, tube)

REST = 1.6
FLOOR = -0.88
CEIL = 1.58
HALF = 1.28


def build():
    s = Ship("kestrel")
    dark, pale, orange, tan = "deserter_dark", "deserter_pale", "deserter_orange", "deserter_tan"
    # Fuselage: a hollow slab, 2.8 wide and 2.7 tall, open at the back for the ramp.
    cabin(s, (0, -0.5, 0.35), (2.8, 9.5, 2.7), dark, wall=0.12, opening=(1.6, 2.3), bevel=0.08)
    seams(s, (0, -0.5, 0.35), (2.8, 9.5, 2.7), ys=(-3.6, -1.2, 1.4, 3.4), xs=(-0.8, 0.8))
    s.add(prism("nose", [(4.2, 1.7), (6.0, 1.3), (7.2, 0.3), (6.8, -0.7), (4.2, -1.0)], 2.6, dark, bevel=0.06, segs=3))
    for x in (-1.2, 1.2):
        for i in range(4):
            s.add(block("vent", (x, 4.8 + i * 0.3, 0.2), (0.08, 0.08, 0.6), "black", bevel=0))
    # Door frame and the ramp hinges.
    for sx in (-1, 1):
        s.add(block("jamb", (sx * 0.95, -5.28, 0.3), (0.3, 0.2, 2.5), pale, bevel=0.02))
    s.add(block("lintel", (0, -5.28, 1.55), (2.2, 0.2, 0.25), pale, bevel=0.02))
    for x in (-0.55, 0.55):
        s.add(hinge("hinge", (x, -5.3, FLOOR + 0.02), axis="x", length=0.3))
    slope = ramp(s, (0, -5.3, FLOOR), 1.6, 2.6, FLOOR + REST, material="gunmetal")
    # Canopy with frame struts.
    s.add(prism("canopy", [(2.4, 1.7), (4.6, 1.7), (5.6, 1.3), (5.6, 1.15), (2.0, 2.15), (1.5, 2.15)], 1.9, "glass", bevel=0.03), "glass")
    s.add(prism("frame", [(1.0, 1.68), (2.4, 1.68), (1.3, 2.2), (0.8, 2.2)], 2.0, dark, bevel=0.02))
    for x in (-0.95, 0.0, 0.95):
        s.add(prism("strut", [(2.4, 1.7), (2.55, 1.7), (2.15, 2.15), (2.0, 2.15)], 0.08, dark, x=x, bevel=0))
    s.add(block("wiper", (0.6, 5.3, 1.4), (0.04, 0.5, 0.04), "black", bevel=0, rot=30))
    # Pale armour plates bolted on the flanks and roof: seams, rivets, latches.
    for x in (-1.45, 1.45):
        side = -1 if x < 0 else 1
        ax = "x" if side > 0 else "-x"
        s.add(side_plate("flank", x, (-2.6, 0.4), (4.6, 1.6), pale, lines=(("y", -1.2), ("y", 1.0), ("z", 0.5))))
        s.add(side_plate("flankfore", x, (1.6, 0.0), (2.6, 1.2), pale, lines=(("z", 0.0),)))
        s.add(side_plate("belt", x, (0.0, -0.75), (8.6, 0.3), orange, thick=0.06))
        s.add(rivets("rv", (x + side * 0.05, -4.8, -0.45), (x + side * 0.05, 2.8, -0.45), 16, axis=ax))
        s.add(rivets("rv", (x + side * 0.05, -4.8, 1.3), (x + side * 0.05, 0.0, 1.3), 10, axis=ax))
        for y in (-3.9, -1.3, 2.4):
            s.add(block("latch", (x + side * 0.08, y, 0.9), (0.08, 0.18, 0.1), "steel", bevel=0.005))
        s.add(block("handle", (x + side * 0.1, -4.6, 0.3), (0.06, 0.4, 0.06), "steel", bevel=0))
        s.add(block("step", (x + side * 0.15, -4.6, -0.6), (0.3, 0.5, 0.05), "steel", bevel=0.005))
    s.add(block("roofplate", (0, -2.8, 1.72), (2.0, 3.8, 0.1), pale, bevel=0.02))
    s.add(stripe("roofstripe", (0, -1.0, 1.7), (2.9, 0.5, 0.0), orange))
    s.add(block("spine", (0, -2.5, 1.74), (0.5, 6.0, 0.14), dark, bevel=0.03))
    s.add(pipe("cable", [(1.2, 1.0, 1.72), (1.2, -3.5, 1.72), (1.2, -3.5, 1.4)], 0.04, material="cord"))
    s.add(pipe("cable2", [(-1.2, 0.5, 1.72), (-1.2, -4.0, 1.72)], 0.03, material="cord"))
    # Roof kit: antenna array, beacon, canvas roll and strapped crate.
    for i, (x, y, h) in enumerate(((-0.9, 3.0, 1.6), (-0.7, 2.6, 1.0), (0.9, -4.2, 1.2))):
        s.add(cyl("antenna", (x, y, 1.7), (x, y, 1.7 + h), 0.025, "steel", segs=6, bevel=0))
        s.add(cyl("antbase", (x, y, 1.7), (x, y, 1.85), 0.07, "black", segs=8, bevel=0))
    nav_light(s, "light.0", (0.0, -4.5, 1.85), "red_light", r=0.09)
    s.add(cyl("roll", (0.7, -3.9, 1.95), (0.7, -1.4, 1.95), 0.26, tan, segs=14, bevel=0.03))
    for y in (-3.6, -1.8):
        s.add(block("strap", (0.7, y, 1.95), (0.58, 0.07, 0.58), "leather", bevel=0.004))
    s.add(crate("roofcrate", (-0.6, -3.2, 2.0), (0.8, 1.1, 0.5), material=tan))
    # Chin gun with a feed and a sensor ball.
    s.add(cyl("turret", (0, 3.8, -1.0), (0, 3.8, -1.45), 0.45, dark, segs=16, bevel=0.02))
    s.add(cyl("barrel", (0, 3.8, -1.25), (0, 6.6, -1.25), 0.09, "steel", segs=10, bevel=0))
    s.add(cyl("barrel2", (0, 3.8, -1.25), (0, 5.6, -1.25), 0.15, dark, segs=10, bevel=0))
    s.add(block("feed", (0.35, 3.8, -1.2), (0.25, 0.5, 0.3), "gunmetal", bevel=0.01))
    s.add(cyl("sensor", (-0.9, 5.2, -1.0), (-0.9, 5.2, -1.25), 0.22, "black", segs=14, bevel=0.01))
    s.add(block("hook", (0, -0.3, -1.15), (0.6, 0.9, 0.35), "gunmetal", bevel=0.02))
    # Stub wings with orange tips, fences, flaps, hardpoints, pylons and twin pod engines.
    for sx in (-1, 1):
        s.add(block("wing", (sx * 3.7, -1.5, 0.3), (4.6, 3.6, 0.28), dark, bevel=0.04, taper=(1.0, 0.85)))
        s.add(block("wingroot", (sx * 1.5, -1.5, 0.3), (0.3, 3.8, 0.5), pale, bevel=0.03))
    for sx in (-1, 1):
        x = sx * 5.5
        s.add(stripe("tip", (x, -1.5, 0.3), (1.0, 3.6, 0.28), orange))
        s.add(block("fence", (sx * 4.6, -1.5, 0.5), (0.05, 3.0, 0.3), pale, bevel=0.005))
        s.add(block("flap", (sx * 3.2, -3.5, 0.3), (3.6, 0.5, 0.18), pale, bevel=0.02))
        s.add(rivets("wingrv", (sx * 1.6, -1.5, 0.45), (sx * 5.0, -1.5, 0.45), 8, axis="z"))
        nav_light(s, f"light.{1 if sx < 0 else 2}", (sx * 5.95, -1.5, 0.3), "red_light" if sx < 0 else "green_light")
        # Missile pod under the outer wing.
        px = sx * 4.1
        s.add(block("hardpoint", (px, -1.4, 0.0), (0.2, 1.2, 0.35), dark, bevel=0.01))
        s.add(cyl("pod", (px, -0.2, -0.3), (px, -2.6, -0.3), 0.32, "gunmetal", segs=16, bevel=0.03))
        for (ox, oz) in ((0.0, 0.17), (-0.15, -0.09), (0.15, -0.09)):
            s.add(tube("tubeend", (px + ox, -0.2, -0.3 + oz), (px + ox, 0.0, -0.3 + oz), 0.11, 0.08, "black", segs=12))
        # Engine pod on a pylon.
        ex = sx * 2.1
        s.add(block("pylon", (ex, -2.4, -0.1), (0.3, 2.0, 0.6), dark, bevel=0.02))
        s.add(cyl("enginepod", (ex, -1.0, -0.4), (ex, -5.8, -0.4), 0.65, "gunmetal", segs=20, bevel=0.04))
        s.add(cyl("intake", (ex, -1.0, -0.4), (ex, -0.65, -0.4), 0.65, dark, r1=0.42, segs=20, bevel=0.02))
        s.add(cyl("spinner", (ex, -0.9, -0.4), (ex, -0.5, -0.4), 0.18, "steel", r1=0.05, segs=12, bevel=0))
        s.add(tube("shield", (ex, -5.2, -0.4), (ex, -5.9, -0.4), 0.74, 0.68, "black", segs=20))
        s.add(bell("bell", (ex, -5.8, -0.4), (ex, -6.9, -0.4), 0.48, 0.62))
        s.add(rivets("podrv", (ex, -1.4, 0.26), (ex, -5.4, 0.26), 8, axis="z"))
        for y in (-2.0, -4.0):
            s.add(block("podlatch", (ex + sx * 0.66, y, -0.4), (0.06, 0.3, 0.14), "steel", bevel=0))
        s.node(f"exhaust.{0 if sx < 0 else 1}", (ex, -6.92, -0.4))
    # Tail: raked fin, stabiliser, rudder, beacon.
    s.add(prism("fin", [(-5.2, 1.7), (-2.9, 1.7), (-3.9, 4.0), (-5.2, 4.0)], 0.24, orange, bevel=0.03))
    s.add(block("finplate", (0, -4.5, 3.0), (0.26, 0.9, 1.2), pale, bevel=0.01))
    s.add(block("stab", (0, -5.0, 2.3), (3.8, 1.0, 0.14), orange, bevel=0.02))
    s.add(block("rudder", (0, -5.3, 3.0), (0.16, 0.5, 1.9), pale, bevel=0.02))
    nav_light(s, "light.3", (0.0, -5.2, 4.05), "red_light", r=0.08)
    # Skids: two a side, with a diagonal brace each.
    for sx in (-1, 1):
        x = sx * 1.3
        for y in (2.4, -2.8):
            s.add(skid("skid", (x, y), 1.9, -REST, -0.98))
            s.add(cyl("brace", (x, y + 0.5, -0.98), (x, y - 0.45, -1.45), 0.04, "steel", segs=8, bevel=0))
    # Markings.
    s.add(label("DSR-07", (-1.53, 1.6, 0.6), 0.5, pale, side=-1, depth=0.01))
    s.add(label("07", (1.53, 1.6, 0.6), 0.5, orange, side=1, depth=0.01))
    s.add(label("NO STEP", (-1.53, -3.6, -0.2), 0.16, orange, side=-1, depth=0.008))
    # Inside: cockpit forward, jump seats along the walls, lockers, crates, a canvas roll, light.
    s.add(seat("pilot", (0, 2.6, FLOOR + 0.5), facing=1, material="leather"))
    console(s, (0, 3.9, FLOOR + 0.5), (1.9, 0.6, 1.0), material=dark, screens=3, screen_mat="screen", facing=1)
    s.add(block("stick", (0, 3.1, FLOOR + 0.6), (0.05, 0.05, 0.4), "black", bevel=0))
    for sx in (-1, 1):
        for y in (-1.4, -2.9):
            s.add(seat("jump", (sx * 0.9, y, FLOOR + 0.5), facing=1, material=tan))
        s.add(locker("locker", (sx * 0.95, 4.35, FLOOR + 0.95), (0.55, 0.5, 1.9), material="grey"))
    s.add(crate("crate", (0.55, -4.2, FLOOR + 0.3), (0.7, 0.7, 0.6), material="olive"))
    s.add(crate("crate2", (-0.6, -4.3, FLOOR + 0.25), (0.8, 0.6, 0.5), material=tan))
    s.add(cyl("roll2", (-0.95, -0.5, FLOOR + 0.26), (-0.95, 1.2, FLOOR + 0.26), 0.25, tan, segs=12, bevel=0.02))
    s.add(handrail("rail", (1.2, -4.6, 0.1), (1.2, -0.8, 0.1), posts=3))
    s.add(chain("chain", (-1.1, -3.6, CEIL), (-1.1, -3.6, CEIL - 0.9), links=8))
    light_strip(s, (0, -4.6, CEIL - 0.02), (0, 2.0, CEIL - 0.02))
    s.add(block("floorplate", (0, -0.6, FLOOR + 0.01), (2.4, 8.8, 0.02), "gunmetal", bevel=0))
    s.node("heat", (0, 6.9, 0.2))
    return s


SPEC = {
    "build": build,
    "size": (15.0, 12.0, 5.6),
    "rest": REST,
    "cabin": (FLOOR, CEIL, HALF),
    "nodes": ["exhaust.0", "exhaust.1", "heat", "ramp", "light.0", "light.1", "light.2", "light.3"],
    "view": {"cam": (-13.0, -15.0, 7.0), "look": (0, -0.5, 0.5), "lens": 40},
    "inside": {"cam": (0.3, -7.5, FLOOR + 1.5), "look": (0, 3.0, FLOOR + 0.9), "lens": 24},
}
