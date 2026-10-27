"""The PMC's Vantage: a faceted interceptor with a two-seat cabin you can walk into. Angular hull
with chamfered decks, a chamfered nose, swept wings, a canopy flush with the hull, two slot
engines flanking a rear ramp, twin fins, blue running lights and strips, a corporate stencil.
Gunmetal and white. Inside: pilot and co-pilot seats, a wide console, white panels, lockers."""

from kit import (Ship, block, cabin, console, cyl, handrail, hinge, label, leg, light_strip, locker, nav_light, plan, prism, ramp, rivets,
                 seams, seat, side_plate, sphere, stripe, tube)

REST = 1.9
FLOOR = -1.1
CEIL = 1.3
HALF = 1.4


def build():
    s = Ship("vantage")
    gm, white = "gunmetal", "white"
    # Hull: a hollow core with chamfered upper and lower decks and a faceted nose.
    cabin(s, (0, -1.0, 0.1), (3.0, 9.0, 2.6), gm, wall=0.1, opening=(1.6, 2.3), bevel=0.05)
    s.add(block("upper", (0, -1.0, 1.6), (3.0, 8.6, 0.5), gm, bevel=0.04, taper=(0.5, 0.9)))
    s.add(block("lower", (0, -1.2, -1.4), (3.0, 8.8, 0.5), gm, bevel=0.04, taper=(0.6, 0.92), rot=180))
    s.add(prism("nose", [(3.5, 1.4), (5.5, 0.9), (7.0, 0.1), (6.5, -0.7), (3.5, -1.2)], 2.8, gm, bevel=0.04, segs=3))
    s.add(prism("chine", [(3.4, 0.25), (7.2, 0.05), (3.4, -0.25)], 1.0, white, bevel=0.02))
    seams(s, (0, -1.0, 0.1), (3.0, 9.0, 2.6), ys=(-3.5, -1.0, 1.5), xs=(-1.0, 1.0), material="black", width=0.03, proud=0.012)
    s.add(block("plate", (0, -1.4, 1.87), (1.3, 5.0, 0.06), white, bevel=0.01))
    seams(s, (0, -1.4, 1.89), (1.3, 5.0, 0.06), ys=(-1.5, 1.0), material=gm, width=0.03, proud=0.01)
    s.add(prism("canopy", [(2.2, 1.4), (4.4, 1.4), (5.6, 1.0), (5.6, 0.85), (1.9, 1.84), (1.4, 1.84)], 1.6, "glass", bevel=0.02), "glass")
    s.add(prism("frame", [(0.8, 1.38), (2.2, 1.38), (1.3, 1.88), (0.6, 1.88)], 1.7, gm, bevel=0.01))
    for x in (-1.5, 1.5):
        sx = -1 if x < 0 else 1
        s.add(side_plate("cheek", x * 1.0, (0.0, 0.2), (6.0, 1.4), white, thick=0.08, lines=(("y", -2.0), ("y", 1.5))))
        s.add(rivets("rv", (x + sx * 0.04, -4.8, 1.0), (x + sx * 0.04, 2.8, 1.0), 10, r=0.025, axis="x" if sx > 0 else "-x"))
        s.add(block("intake", (x * 1.05, 0.5, 0.3), (0.3, 1.8, 0.5), "black", bevel=0.02))
        s.add(block("intakelip", (x * 1.1, 1.45, 0.3), (0.34, 0.1, 0.6), white, bevel=0.01))
        s.add(block("chinestrip", (x * 1.02, -1.5, -0.9), (0.04, 7.0, 0.06), "blue_light", bevel=0), "lights")
        s.add(sphere("blister", (x * 1.1, -3.5, 0.9), 0.3, "black", segs=12))
    s.add(sphere("sensor", (0, 4.6, -1.2), 0.32, "black", segs=14))
    s.add(cyl("antenna", (-0.8, -4.2, 1.85), (-0.8, -4.4, 2.9), 0.02, "steel", segs=6, bevel=0))
    nav_light(s, "light.4", (0.0, -4.5, 1.9), "red_light", r=0.07)
    # Swept wings with white leading edges, fences, blue tip lights and hardpoint bays.
    for side in (-1, 1):
        s.add(plan("wing", [(side * 1.5, 1.0), (side * 5.5, -3.2), (side * 5.5, -4.5), (side * 1.5, -4.0)], 0.26, gm, z=0.2, bevel=0.03))
        s.add(plan("wingedge", [(side * 1.55, 1.0), (side * 5.5, -3.15), (side * 5.5, -3.45), (side * 1.55, 0.5)], 0.28, white, z=0.2, bevel=0.01))
        s.add(block("fence", (side * 4.0, -2.6, 0.42), (0.04, 1.6, 0.2), white, bevel=0.005))
        s.add(block("baydoor", (side * 3.0, -2.0, 0.05), (1.2, 1.6, 0.04), gm, bevel=0.005))
        s.add(block("bayseam", (side * 3.0, -2.0, 0.03), (1.24, 0.03, 0.05), "black", bevel=0))
        s.add(cyl("tiplight", (side * 5.4, -3.9, 0.2), (side * 5.52, -3.9, 0.2), 0.12, "blue_light", segs=10, bevel=0), "lights")
        s.node(f"light.{0 if side < 0 else 1}", (side * 5.5, -3.9, 0.2))
        # Slot engines flanking the door, with a round liner showing at the back.
        x = side * 1.9
        s.add(block("engine", (x, -5.2, -0.1), (1.4, 2.8, 0.9), gm, bevel=0.04, taper=(0.8, 1.0)))
        s.add(tube("liner", (x, -6.0, -0.1), (x, -6.7, -0.1), 0.36, 0.28, "steel", segs=18))
        s.add(block("enginefin", (x, -5.0, 0.45), (0.05, 2.0, 0.2), white, bevel=0))
        s.node(f"exhaust.{0 if side < 0 else 1}", (x, -6.72, -0.1))
        # Twin fins on the roof, with the stencil on their outer faces.
        fx = side * 1.1
        s.add(prism("fin", [(-5.4, 1.7), (-3.0, 1.7), (-4.2, 3.4), (-5.4, 3.4)], 0.12, gm, x=fx, bevel=0.02))
        s.add(stripe("finstripe", (fx, -4.7, 3.0), (0.12, 1.3, 0.08), white))
        s.add(label("VANTAGE SEC", (fx + side * 0.07, -4.3, 2.4), 0.3, white, side=side, depth=0.006))
        s.add(cyl("finlight", (fx, -5.45, 3.35), (fx, -5.4, 3.35), 0.07, "blue_light", segs=8, bevel=0), "lights")
        s.node(f"light.{2 if side < 0 else 3}", (fx, -5.45, 3.35))
    # Door frame, hinges and the belly-level ramp.
    for sx in (-1, 1):
        s.add(block("jamb", (sx * 0.95, -5.52, 0.1), (0.3, 0.14, 2.5), white, bevel=0.02))
    s.add(block("lintel", (0, -5.52, 1.3), (2.2, 0.14, 0.2), white, bevel=0.02))
    for x in (-0.55, 0.55):
        s.add(hinge("hinge", (x, -5.55, FLOOR + 0.02), axis="x", length=0.3))
    ramp(s, (0, -5.55, FLOOR), 1.6, 2.6, FLOOR + REST, material=gm)
    # Three legs with covers: nose and two main.
    for x, y in ((0.0, 3.4), (-1.0, -2.6), (1.0, -2.6)):
        s.add(leg("leg", (x, y), -REST, -1.5, r=0.1))
        s.add(block("legdoor", (x + 0.2, y, -1.6), (0.06, 0.8, 0.6), white, bevel=0.005))
    # Inside: two seats, a wide console, white panels, lockers, blue strips, grating.
    for x in (-0.5, 0.5):
        s.add(seat("seat", (x, 1.4, FLOOR + 0.5), facing=1, material="black", frame=white))
    console(s, (0, 2.6, FLOOR + 0.55), (2.4, 0.7, 1.0), material=white, screens=4, screen_mat="blue_light", facing=1)
    s.add(block("stick", (0.5, 1.9, FLOOR + 0.6), (0.04, 0.04, 0.4), "black", bevel=0))
    s.add(block("throttle", (-0.5, 1.9, FLOOR + 0.6), (0.08, 0.2, 0.3), "black", bevel=0))
    for sx in (-1, 1):
        s.add(side_plate("innerpanel", sx * 1.35, (-1.5, 0.2), (6.0, 1.8), white, thick=0.04))
        s.add(locker("locker", (sx * 1.05, 3.0, FLOOR + 0.95), (0.5, 0.45, 1.9), material=white, doors=1))
        s.add(block("innerstrip", (sx * 1.3, -1.5, CEIL - 0.04), (0.04, 6.5, 0.04), "blue_light", bevel=0), "lights")
    s.add(handrail("rail", (1.25, -5.0, FLOOR + 1.0), (1.25, -2.0, FLOOR + 1.0), posts=2))
    s.add(block("bench", (-1.0, -3.5, FLOOR + 0.25), (0.6, 2.0, 0.5), "black", bevel=0.02))
    light_strip(s, (0, -4.8, CEIL - 0.02), (0, 1.0, CEIL - 0.02), w=0.1)
    s.add(block("floorplate", (0, -1.0, FLOOR + 0.01), (2.6, 8.6, 0.02), gm, bevel=0))
    s.node("heat", (0, 6.9, 0.1))
    return s


SPEC = {
    "build": build,
    "size": (14.9, 11.0, 5.3),
    "rest": REST,
    "cabin": (FLOOR, CEIL, HALF),
    "nodes": ["exhaust.0", "exhaust.1", "heat", "ramp", "light.0", "light.1", "light.2", "light.3", "light.4"],
    "view": {"cam": (-12.0, -13.0, 6.0), "look": (0, -0.5, 0.3), "lens": 40},
    "inside": {"cam": (0.3, -8.3, FLOOR + 1.5), "look": (0, 2.0, FLOOR + 0.9), "lens": 24},
}
