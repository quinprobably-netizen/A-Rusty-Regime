"""The PMC's Vantage: a faceted interceptor. Angular stealth hull, swept wings, a canopy flush with
the hull, two slot engines, twin fins, blue running lights, a corporate stencil. Gunmetal and white."""

from kit import Ship, block, cyl, label, leg, plan, prism, seams, stripe, tube

REST = 1.1


def build():
    s = Ship("vantage")
    gm, white = "gunmetal", "white"
    # Hull: a diamond plan with chamfered upper and lower decks.
    s.add(plan("core", [(0, 6.0), (1.3, 2.0), (1.3, -5.2), (0.7, -6.0), (-0.7, -6.0), (-1.3, -5.2), (-1.3, 2.0)], 1.0, gm, bevel=0.04))
    s.add(block("upper", (0, -1.2, 0.72), (2.4, 7.2, 0.5), gm, bevel=0.04, taper=(0.55, 0.9)))
    s.add(block("lower", (0, -1.0, -0.72), (2.4, 7.6, 0.5), gm, bevel=0.04, taper=(0.6, 0.92), rot=180))
    s.add(prism("chine", [(2.0, 0.3), (5.9, 0.05), (2.0, -0.3)], 2.0, gm, bevel=0.03))
    s.add(block("plate", (0, -2.4, 0.95), (1.2, 4.0, 0.06), white, bevel=0.01))
    seams(s, (0, -2.4, 0.97), (1.2, 4.0, 0.06), ys=(-1.2, 0.6), material=gm, width=0.03, proud=0.01)
    s.add(prism("canopy", [(1.2, 0.5), (3.6, 0.5), (4.8, 0.15), (0.8, 0.97), (0.3, 0.97)], 1.1, "glass", bevel=0.02), "glass")
    # Swept wings, white leading edges, blue tip lights.
    for side in (-1, 1):
        s.add(plan("wing", [(side * 1.2, 1.0), (side * 5.0, -3.0), (side * 5.0, -4.2), (side * 1.2, -3.6)], 0.24, gm, z=-0.15, bevel=0.03))
        s.add(plan("wingedge", [(side * 1.25, 1.0), (side * 5.0, -2.95), (side * 5.0, -3.25), (side * 1.25, 0.5)], 0.26, white, z=-0.15, bevel=0.01))
        s.add(cyl("tiplight", (side * 4.9, -3.7, -0.15), (side * 5.02, -3.7, -0.15), 0.12, "blue_light", segs=10, bevel=0), "lights")
        s.node(f"light.{0 if side < 0 else 1}", (side * 5.0, -3.7, -0.15))
        # Slot engines: a tapered block each side with a round liner showing at the back.
        x = side * 1.2
        s.add(block("engine", (x, -4.9, 0.0), (1.4, 2.6, 0.8), gm, bevel=0.04, taper=(0.8, 1.0)))
        s.add(tube("liner", (x, -5.6, 0.0), (x, -6.4, 0.0), 0.34, 0.26, "steel", segs=18))
        s.node(f"exhaust.{0 if side < 0 else 1}", (x, -6.42, 0.0))
        # Twin fins, with the stencil on their outer faces.
        fx = side * 0.95
        s.add(prism("fin", [(-5.8, 0.4), (-3.4, 0.4), (-4.6, 2.3), (-5.8, 2.3)], 0.12, gm, x=fx, bevel=0.02))
        s.add(stripe("finstripe", (fx, -5.1, 1.9), (0.12, 1.3, 0.08), white))
        s.add(label("VANTAGE SEC", (fx + side * 0.07, -4.7, 1.2), 0.3, white, side=side, depth=0.006))
        s.add(cyl("finlight", (fx, -5.85, 2.25), (fx, -5.8, 2.25), 0.07, "blue_light", segs=8, bevel=0), "lights")
        s.node(f"light.{2 if side < 0 else 3}", (fx, -5.85, 2.25))
    # Sensor bump, intakes and a ventral pod.
    s.add(cyl("sensor", (0, 4.4, -0.55), (0, 4.4, -0.75), 0.3, "black", segs=14, bevel=0.01))
    for side in (-1, 1):
        s.add(block("intake", (side * 1.35, 0.0, 0.1), (0.3, 1.6, 0.5), "black", bevel=0.02))
    s.add(block("pod", (0, -1.5, -0.95), (0.8, 3.0, 0.3), gm, bevel=0.03))
    # Three legs: nose and two main.
    for x, y in ((0.0, 3.2), (-0.9, -2.6), (0.9, -2.6)):
        s.add(leg("leg", (x, y), -REST, -0.7, r=0.09))
    s.node("heat", (0, 5.9, 0.0))
    return s


SPEC = {
    "build": build,
    "size": (12.4, 10.0, 3.4),
    "rest": REST,
    "nodes": ["exhaust.0", "exhaust.1", "heat", "light.0", "light.1", "light.2", "light.3"],
    "view": {"cam": (-12.0, 10.0, 5.0), "look": (0, -0.5, 0.2), "lens": 40},
}
