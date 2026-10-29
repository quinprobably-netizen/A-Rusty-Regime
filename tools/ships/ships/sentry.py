"""The PMC's Sentry: a patrol fighter in the Vantage's styling. A faceted diamond wedge of gunmetal
with white deck plates and chines, forward-swept wings with white leading edges and blue tip lights,
one big engine in a faceted housing, two small canted fins with the corporate stencil, blue
running-light strips down the chines. Solid hull: a flush faceted canopy over the seat."""

from fighter import band, cockpit
from kit import Ship, block, cyl, label, leg, loft, nav_light, plan, prism, rotate, sphere, stripe, tube

REST = 1.3
SIDES, PHASE = 6, 0.0  # hexagon with corners on the flanks: flat deck and belly, sharp chines
HULL = [(-3.9, 0, 0.0, 1.0, 0.62), (-2.6, 0, 0.0, 1.45, 0.72), (-0.6, 0, 0.0, 1.55, 0.74), (1.4, 0, -0.04, 1.2, 0.6),
        (3.0, 0, -0.1, 0.7, 0.4), (4.2, 0, -0.15, 0.25, 0.16), (4.6, 0, -0.16, 0, 0)]
DECK = 0.866  # the flat deck of the hexagon sits at DECK * rz


def build():
    s = Ship("sentry")
    gm, white = "gunmetal", "white"
    hull = loft("hull", HULL, gm, sides=SIDES, phase=PHASE)
    canopy = [(0.2, 0, 0.3, 0.0, 0.0), (0.7, 0, 0.3, 0.42, 0.52), (1.6, 0, 0.3, 0.44, 0.62), (2.4, 0, 0.25, 0.36, 0.44),
              (3.1, 0, 0.18, 0, 0)]
    hull = cockpit(s, hull, ((0, 1.25, 0.2), (0.7, 1.6, 1.0)), canopy, (0, 1.35, -0.15), sides=SIDES, phase=PHASE,
                   hull_mat=gm, seat_mat="black", frame=white, trim="steel", screen="blue_light", hoops=(0.75,))
    s.add(hull)
    # White deck plate and chine strips, panel seams, a white nose chevron.
    z = DECK * 0.72
    s.add(plan("deck", [(-0.52, -3.4), (0.52, -3.4), (0.6, -1.0), (0.24, 0.25), (-0.24, 0.25), (-0.6, -1.0)], 0.04, white, z=z + 0.02, bevel=0.005))
    for sx in (-1, 1):
        # Blue running-light strips along the deck plate's edges.
        s.add(plan("deckstrip", [(sx * 0.7, -3.3), (sx * 0.77, -1.0), (sx * 0.4, 0.15), (sx * 0.28, 0.15), (sx * 0.64, -1.0), (sx * 0.58, -3.3)],
                   0.03, "blue_light", z=z + 0.025, bevel=0), "lights")
    for y in (-2.4, -1.2):
        s.add(block("seam", (0, y, z + 0.045), (1.1, 0.03, 0.01), gm, bevel=0))
    s.add(block("spine", (0, -1.6, z + 0.06), (0.04, 3.4, 0.02), gm, bevel=0))
    s.add(plan("chevron", [(0, 3.9), (0.42, 2.9), (0.3, 2.75), (0, 3.45), (-0.3, 2.75), (-0.42, 2.9)], 0.03, white, z=DECK * 0.38 - 0.04, bevel=0))
    for sx in (-1, 1):
        # Blue running-light strips just under each chine, a white chine cap above.
        s.add(plan("chine", [(sx * 1.56, -2.6), (sx * 1.58, -0.6), (sx * 1.22, 1.4), (sx * 0.72, 3.0), (sx * 0.66, 3.0), (sx * 1.15, 1.4),
                             (sx * 1.5, -0.6), (sx * 1.48, -2.6)], 0.05, white, z=0.03, bevel=0))
        s.add(plan("strip", [(sx * 1.5, -2.4), (sx * 1.52, -0.6), (sx * 1.16, 1.4), (sx * 1.1, 1.4), (sx * 1.45, -0.6), (sx * 1.43, -2.4)], 0.03,
                   "blue_light", z=-0.06, bevel=0), "lights")
        s.add(block("intake", (sx * 1.0, -0.4, -0.38), (0.5, 1.6, 0.26), "black", bevel=0.02, taper=(0.8, 1.0), rot=180))
        s.add(sphere("blister", (sx * 0.55, -2.9, z + 0.04), 0.18, "black", segs=10))
    # Forward-swept wings: the tips reach ahead of the roots. White leading edges, blue tip lights.
    for sx in (-1, 1):
        root_le, root_te, tip_le, tip_te = (sx * 1.3, -0.9), (sx * 1.3, -3.0), (sx * 4.3, 0.5), (sx * 4.3, -0.4)
        s.add(plan("wing", [root_le, tip_le, tip_te, root_te], 0.16, gm, z=-0.05, bevel=0.02))
        s.add(plan("wingedge", [(sx * 1.35, -0.9), (sx * 4.3, 0.5), (sx * 4.3, 0.25), (sx * 1.35, -1.2)], 0.18, white, z=-0.05, bevel=0.01))
        s.add(block("wingseam", (sx * 2.8, -1.0, 0.035), (0.03, 1.4, 0.01), white, bevel=0))
        s.add(block("fence", (sx * 3.4, -0.3, 0.1), (0.04, 1.2, 0.14), white, bevel=0.003))
        s.add(block("tipcap", (sx * 4.33, 0.05, -0.05), (0.08, 0.9, 0.2), white, bevel=0.01))
        s.add(cyl("tiplight", (sx * 4.37, 0.35, -0.05), (sx * 4.45, 0.35, -0.05), 0.07, "blue_light", segs=10, bevel=0), "lights")
        s.node(f"light.{0 if sx < 0 else 1}", (sx * 4.45, 0.35, -0.05))
        # Small canted tail fins with the corporate stencil.
        fx = sx * 0.85
        fin = prism("fin", [(-3.95, 0.4), (-2.4, 0.4), (-3.4, 1.55), (-3.95, 1.55)], 0.1, gm, x=fx, bevel=0.015)
        s.add(rotate(fin, (fx, -3.0, 0.4), "y", sx * 20))
        s.add(rotate(stripe("finstripe", (fx, -3.7, 1.35), (0.1, 0.5, 0.12), white), (fx, -3.0, 0.4), "y", sx * 20))
        s.add(rotate(label("VSEC", (fx + sx * 0.06, -3.3, 0.85), 0.2, white, side=sx, depth=0.005), (fx, -3.0, 0.4), "y", sx * 20))
        s.add(rotate(cyl("finlight", (fx, -3.95, 1.5), (fx, -4.0, 1.5), 0.05, "blue_light", segs=8, bevel=0), (fx, -3.0, 0.4), "y", sx * 20), "lights")
    for sx in (-1, 1):
        # The stencil laid flat on each wing's upper face.
        c = (sx * 2.45, -1.25, 0.035)
        s.add(rotate(rotate(label("VANTAGE SEC", c, 0.16, white, side=1, depth=0.004), c, "y", -90), c, "z", -90))
    # One big engine: a faceted housing, a white collar, a round liner you can see down.
    eng = [(-2.8, 0, 0.0, 1.0, 0.62), (-4.0, 0, 0.0, 0.95, 0.6), (-4.6, 0, 0.0, 0.9, 0.56)]
    s.add(loft("housing", eng, gm, sides=SIDES, phase=PHASE, bevel=0.02))
    s.add(band("collar", eng, -4.45, 0.2, white, sides=SIDES, phase=PHASE))
    s.add(tube("liner", (0, -4.3, 0.0), (0, -4.75, 0.0), 0.5, 0.42, "steel", segs=20))
    s.add(cyl("core", (0, -4.0, 0.0), (0, -4.5, 0.0), 0.43, "black", r1=0.2, segs=16, bevel=0))
    s.node("exhaust.0", (0, -4.77, 0.0))
    s.add(sphere("sensor", (0, 2.6, -0.55), 0.18, "black", segs=12))
    s.add(cyl("antenna", (0.4, -2.6, z), (0.4, -2.75, z + 0.6), 0.015, "steel", segs=6, bevel=0))
    nav_light(s, "light.2", (0, -3.3, z + 0.08), "blue_light", r=0.06)
    # Three legs with white doors.
    for x, y in ((0.0, 2.6), (-1.0, -1.9), (1.0, -1.9)):
        s.add(leg("leg", (x, y), -REST, -0.5, r=0.07))
        s.add(block("legdoor", (x + 0.15, y, -0.6), (0.03, 0.6, 0.3), white, bevel=0.003))
    s.node("heat", (0, 4.7, -0.16))
    return s


SPEC = {
    "build": build,
    "size": (9.35, 8.9, 2.8),
    "rest": REST,
    "nodes": ["exhaust.0", "heat", "light.0", "light.1", "light.2"],
    "view": {"cam": (-8.0, 8.5, 4.6), "look": (0, -0.3, 0.0), "lens": 40},
    "top": {"cam": (0, -0.01, 22.0), "look": (0, 0, 0), "lens": 50},
}
