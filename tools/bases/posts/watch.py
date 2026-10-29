"""The Deserters' watch on Haven: a timber and steel watchtower. Four leaning timber legs braced
with steel crosses carry a lookout deck six metres up behind painted ply parapets, under a bold
orange tarp roof. A ladder climbs the open front; a field radio on the deck feeds a whip antenna
with a red beacon; a sandbag ring guards the legs on three sides, and a cook fire smokes out front."""

import math

from basekit import Base, box, ladder
from kit import block, cyl, prism, sphere
from interior import crate, lamp
from posts import bags, flames, turned

DECK = 6.0          # the deck's top
TOP = 1.38          # the legs' half-spread at the deck
FOOT = 1.75         # and at the ground
ROOF = 8.5          # the ridge
T, TD, P, D, O = "timber", "timber_dark", "deserter_pale", "deserter_dark", "tarp"


def leg_at(z, ax, ay):
    k = FOOT + (TOP - FOOT) * z / DECK
    return (ax * k, ay * k, z)


def build():
    b = Base("watch")
    # Footings, legs and the ring beams.
    for ax in (-1, 1):
        for ay in (-1, 1):
            b.add(block("footing", (ax * FOOT, ay * FOOT, 0.12), (0.55, 0.55, 0.3), "concrete", bevel=0))
            b.add(cyl("leg", leg_at(0, ax, ay), leg_at(DECK + 1.05, ax, ay), 0.13, T, segs=6, bevel=0))
    for z, s in ((2.9, 0.16), (DECK - 0.2, 0.2)):
        for (ax, ay), (bx, by) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
            b.add(cyl("beam", leg_at(z, ax, ay), leg_at(z, bx, by), s / 2, TD, segs=6, bevel=0))
    # Steel X bracing on the back and both sides; the front is left for the ladder.
    for z0, z1 in ((0.4, 2.9), (2.9, DECK - 0.2)):
        for (ax, ay), (bx, by) in (((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
            b.add(cyl("brace", leg_at(z0, ax, ay), leg_at(z1, bx, by), 0.035, "steel", segs=5, bevel=0))
            b.add(cyl("brace", leg_at(z0, bx, by), leg_at(z1, ax, ay), 0.035, "steel", segs=5, bevel=0))
    # The deck, its joists showing underneath, and painted ply parapets with an orange chevron band.
    b.add(block("deck", (0, 0, DECK - 0.09), (3.9, 3.9, 0.18), T, bevel=0))
    for x in (-1.2, 0.0, 1.2):
        b.add(block("joist", (x, 0, DECK - 0.27), (0.14, 3.9, 0.2), TD, bevel=0))
    for i in range(6):
        b.add(block("plank", (0, -1.95 + (i + 0.5) * 0.65, DECK + 0.005), (3.9, 0.02, 0.01), TD, bevel=0))
    H = 1.05
    for name, c, s in _parapets(H):
        b.add(block(name, c, s, P, bevel=0))
    for side in (-1, 1):  # the front panels either side of the ladder gap: orange band, dark chevrons
        x = side * 1.21
        b.add(block("band", (x, -1.97, DECK + 0.55), (1.48, 0.03, 0.32), O, bevel=0))
        for i in range(5):
            b.add(turned(block("chev", (x - 0.56 + i * 0.28, -1.99, DECK + 0.55), (0.11, 0.02, 0.36), D, bevel=0), (x - 0.56 + i * 0.28, -1.99, DECK + 0.55), 35, "y"))
    for x in (-1.97, 1.97):
        b.add(block("band", (x, 0, DECK + 0.55), (0.03, 3.9, 0.32), O, bevel=0))
    b.add(block("cap", (0, -1.95, DECK + H), (3.95, 0.12, 0.06), TD, bevel=0))
    for x in (-1.95, 1.95):
        b.add(block("cap", (x, 0, DECK + H), (0.12, 3.95, 0.06), TD, bevel=0))
    b.add(cyl("backrail", (-1.9, 1.92, DECK + H), (1.9, 1.92, DECK + H), 0.04, TD, segs=6, bevel=0))
    # Sandbags along the front parapet's inside, a radio on a crate, the antenna and its beacon.
    bags(b, (-1.2, -1.7, DECK), 1.3, rows=2, axis="x")
    bags(b, (1.2, -1.7, DECK), 1.3, rows=2, axis="x")
    b.add(crate("radiocrate", (1.2, 1.4, DECK + 0.3), (0.9, 0.6, 0.6), material="olive"))
    b.add(block("radio", (1.2, 1.4, DECK + 0.82), (0.62, 0.4, 0.44), D, bevel=0.02, segs=1))
    b.add(block("dial", (1.2, 1.19, DECK + 0.86), (0.4, 0.02, 0.18), "screen", bevel=0), "lights")
    b.add(block("knobs", (1.2, 1.19, DECK + 0.68), (0.44, 0.03, 0.06), "steel", bevel=0))
    b.add(cyl("handset", (0.85, 1.35, DECK + 1.06), (0.85, 1.35, DECK + 0.78), 0.04, "black", segs=6, bevel=0))
    b.add(cyl("mast", (1.6, 1.6, DECK + 0.3), (1.6, 1.6, ROOF + 2.8), 0.04, "steel", segs=6, bevel=0))
    b.add(cyl("coax", (1.45, 1.45, DECK + 0.9), (1.58, 1.58, DECK + 1.6), 0.02, "black", segs=4, bevel=0))
    b.add(sphere("beacon", (1.6, 1.6, ROOF + 2.9), 0.11, "red_light", segs=8), "lights")
    b.add(prism("pennant", [(1.62, ROOF + 2.6), (1.62, ROOF + 2.0), (2.9, ROOF + 2.3)], 0.02, "deserter_green", x=1.6, bevel=0))
    b.node("blink.0", (1.6, 1.6, ROOF + 2.9))
    b.node("sound.radio.0", (1.2, 1.4, DECK + 0.9))
    # The tarp roof: posts from the deck corners to a ridge across X, two sloped sheets, guy lines.
    for ax in (-1, 1):
        b.add(cyl("ridgepost", (ax * 1.8, 0, DECK + H), (ax * 1.8, 0, ROOF), 0.07, TD, segs=6, bevel=0))
    b.add(cyl("ridge", (-2.3, 0, ROOF), (2.3, 0, ROOF), 0.07, TD, segs=6, bevel=0))
    a = math.degrees(math.atan2(ROOF - DECK - 1.6, 2.2))
    for side in (-1, 1):
        b.add(block("tarp", (0, side * 1.15, (ROOF + DECK + 1.55) / 2 - 0.02), (4.8, 2.6, 0.05), O, bevel=0, rot=-side * a))
        b.add(block("hem", (0, side * 2.28, DECK + 1.6), (4.8, 0.08, 0.1), D, bevel=0))
        for x in (-2.3, 0.0, 2.3):
            b.add(cyl("tie", (x, side * 2.26, DECK + 1.56), (x * 0.82, side * 1.92, DECK + 1.08), 0.015, "black", segs=4, bevel=0))
    lamp(b, "lamp.0", (0, 0, ROOF - 0.5), rim="black", r=0.12)
    # The ladder up the open front, through a gap in the parapet.
    ladder(b, (0, -2.05, 0), DECK + 1.0, material="steel", w=0.55)
    for z in (1.0, 3.5, DECK - 0.4):
        b.add(block("ladderbracket", (0, -1.95, z), (0.6, 0.2, 0.05), "steel", bevel=0))
    # The sandbag ring round the legs, open at the front.
    bags(b, (0, 2.9, 0), 6.0, rows=3, axis="x")
    for x in (-2.9, 2.9):
        bags(b, (x, 0.35, 0), 4.7, rows=3, axis="y")
    # The cook fire out front: a ring of stones, crossed logs, a log to sit on.
    fx, fy = 2.4, -3.2
    for i in range(7):
        a = i * math.tau / 7
        b.add(block("stone", (fx + 0.45 * math.cos(a), fy + 0.45 * math.sin(a), 0.1), (0.24, 0.2, 0.2), "grey", bevel=0.05, segs=1))
    for a in (0.6, 2.2):
        b.add(cyl("log", (fx - 0.35 * math.cos(a), fy - 0.35 * math.sin(a), 0.1), (fx + 0.35 * math.cos(a), fy + 0.35 * math.sin(a), 0.22), 0.06, TD, segs=5, bevel=0))
    b.add(sphere("embers", (fx, fy, 0.16), 0.18, "fire_light", segs=8), "lights")
    flames(b, (fx, fy, 0.14), 0.3, n=4)
    b.add(cyl("seatlog", (fx - 1.0, fy - 0.9, 0.18), (fx + 0.8, fy - 1.3, 0.18), 0.17, T, segs=7, bevel=0))
    b.node("fire.0", (fx, fy, 0.4))
    b.node("smoke.0", (fx, fy, 0.9))
    b.node("sound.fire.0", (fx, fy, 0.3))
    b.add(crate("ammo", (-2.3, -2.6, 0.25), (0.8, 0.5, 0.5), material="olive"))
    b.add(crate("ammo", (-2.3, -2.6, 0.72), (0.6, 0.45, 0.44), material="tarp"))
    return b


def _parapets(h):
    """The ply parapet panels: two at the front either side of the ladder, one each side."""
    z = DECK + h / 2
    return [("parapet", (-1.21, -1.93, z), (1.48, 0.05, h)), ("parapet", (1.21, -1.93, z), (1.48, 0.05, h)),
            ("parapet", (-1.93, 0, z), (0.05, 3.9, h)), ("parapet", (1.93, 0, z), (0.05, 3.9, h))]


SPEC = {
    "build": build,
    "name": "Deserter watch",
    "color": (0.3, 1.0, 0.5),
    "faction": "deserters",
    "body": "home",
    "footprint": (7.0, 7.0),
    "footprint_at": (0.0, -0.3),
    "door": (0.0, -3.2, 1.2),
    "size": (7.7, 6.3, 11.5),
    "depth": 0.03,
    "nodes": ["lamp.0", "blink.0", "fire.0", "smoke.0", "sound.radio.0", "sound.fire.0"],
    "boxes": [
        *[box("leg", (ax * (FOOT + TOP) / 2, ay * (FOOT + TOP) / 2, DECK / 2), (0.3, 0.3, DECK)) for ax in (-1, 1) for ay in (-1, 1)],
        *[box("footing", (ax * FOOT, ay * FOOT, 0.12), (0.55, 0.55, 0.3)) for ax in (-1, 1) for ay in (-1, 1)],
        box("deck", (0, 0, DECK - 0.09), (3.9, 3.9, 0.18)),
        *[box(n, c, s) for n, c, s in _parapets(1.05)],
        box("back rail", (0, 1.92, DECK + 0.55), (3.9, 0.1, 1.1)),
        box("sandbags back", (0, 2.9, 0.3), (6.0, 0.36, 0.6)),
        box("sandbags west", (-2.9, 0.35, 0.3), (0.36, 4.7, 0.6)),
        box("sandbags east", (2.9, 0.35, 0.3), (0.36, 4.7, 0.6)),
        box("radio", (1.2, 1.4, DECK + 0.5), (0.9, 0.6, 1.0)),
        box("ammo", (-2.3, -2.6, 0.48), (0.8, 0.5, 0.96)),
    ],
    "crew": [
        ("runner", (-0.6, 0.3, DECK), 0.0, []),
        ("breaker", (1.6, -2.4, 0.0), 220.0, []),
    ],
    "view": {"cam": (-17.0, -25.0, 9.0), "look": (0, 0, 4.0), "lens": 40},
    "near": {"cam": (4.5, -9.0, 1.7), "look": (0, 0, 3.5), "lens": 24},
}
