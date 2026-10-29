"""The PMC's sensor post on Frost: a sealed white hab pod, a capsule on four jacks, dug into a
horseshoe berm of ice open to the front. Steps climb to an airlock hatch in its flank; inside are a
console and a bunk under one light. A radar dish turns on a mast beside it, white strobes flash on
the mast and the pod's roof, radiator fins stand off its back. No air: no smoke, no fire, and its
one sound, the hum of the console, is inside."""

import math

from basekit import Base, box, slope, spinner, stair
from kit import block, cut, cyl, sphere, tube
from mathutils import Vector
from posts import rock

JACK = 1.0                       # the tube's underside clears the ice by about this
PC, PR, PL = (0.0, 1.4, 2.5), 1.55, 5.0   # the pod: axis centre (x, y, z), outer radius, length
FLOOR = PC[2] - 0.9              # the deck inside
DW, DH = 1.1, 2.0                # the hatchway
W, GM, BL, HZ = "pmc_white", "gunmetal", "blue_light", "hazard"


def build():
    b = Base("sensor")
    px, py, pz = PC
    # The berm: lumps of ice in a horseshoe round the back and sides, open to the front.
    for i, (a, r, s) in enumerate(((-20, 5.6, (1.7, 1.6, 1.4)), (15, 5.4, (2.1, 1.9, 2.0)), (50, 5.3, (2.2, 2.0, 2.4)), (90, 5.0, (2.8, 1.9, 2.6)),
                                   (130, 5.3, (2.2, 2.0, 2.3)), (165, 5.4, (2.1, 1.9, 1.9)), (200, 5.6, (1.7, 1.5, 1.3)))):
        x, y = px + (r - 0.5) * math.cos(math.radians(a)), py - 0.4 + r * math.sin(math.radians(a))
        rock(b, "berm", (x, y, -0.4), s, material="ice", seed=21 + i, subdiv=2, jitter=0.18, flat=0.2)
    # The pod: a hollow tube on its side with rounded end caps, the hatchway cut in its front flank.
    shell = tube("pod", (px - PL / 2, py, pz), (px + PL / 2, py, pz), PR, PR - 0.1, W, segs=18, bevel=0)
    shell = cut(shell, block("hatchway", (px, py - PR, FLOOR + DH / 2), (DW, 1.2, DH), W, bevel=0))
    b.add(shell)
    for k in (-1, 1):
        cap = sphere("cap", (0, 0, 0), 1.0, W, segs=14)
        cap.scale = (0.75, PR, PR)
        cap.location = (px + k * PL / 2, py, pz)
        b.add(cap)
    b.add(block("deck", (px, py, FLOOR - 0.05), (PL, 2.3, 0.1), GM, bevel=0))
    for x, w, m in ((-1.6, 0.24, GM), (-0.95, 0.5, "pmc_blue"), (1.6, 0.24, GM)):  # hoops and a painted band round the shell
        b.add(tube("hoop", (px + x - w / 2, py, pz), (px + x + w / 2, py, pz), PR + 0.04, PR - 0.02, m, segs=18, bevel=0))
    for k in (-1, 1):
        b.add(block("strip", (px, py + k * 0.6, pz + PR * 0.88), (PL - 0.4, 0.06, 0.04), BL, bevel=0), "lights")
    b.add(block("band", (px, py - PR * 0.72, pz + PR * 0.7), (PL, 0.05, 0.28), "hazard", bevel=0, rot=45))
    # The hatch: a frame, chevrons, the door slid aside on a rail, a lamp over it.
    fy = py - math.sqrt(PR ** 2 - (FLOOR + 0.2 - pz) ** 2) - 0.02
    for k in (-1, 1):
        b.add(block("jamb", (px + k * (DW / 2 + 0.08), fy, FLOOR + DH / 2), (0.16, 0.3, DH + 0.1), GM, bevel=0))
        b.add(block("chev", (px + k * (DW / 2 + 0.08), fy - 0.16, FLOOR + DH / 2), (0.1, 0.02, DH), HZ, bevel=0))
    b.add(block("lintel", (px, fy - 0.1, FLOOR + DH + 0.1), (DW + 0.32, 0.5, 0.2), GM, bevel=0))
    b.add(block("hatchdoor", (px + DW + 0.1, fy - 0.2, FLOOR + DH / 2), (DW, 0.1, DH), W, bevel=0))
    b.add(block("hatchrail", (px + DW / 2 + 0.1, fy - 0.28, FLOOR + DH + 0.05), (2 * DW + 0.3, 0.06, 0.08), GM, bevel=0))
    b.add(block("hatchwindow", (px + DW + 0.1, fy - 0.26, FLOOR + DH * 0.72), (0.4, 0.02, 0.3), "glass", bevel=0), "glass")
    b.add(sphere("lamp", (px, fy - 0.38, FLOOR + DH + 0.32), 0.08, "lamp", segs=8), "lights")
    # Portholes either side of the hatch.
    for x in (-1.7, 1.7):
        y = py - math.sqrt(PR ** 2 - 0.25) - 0.01
        b.add(cyl("porthole", (px + x, y + 0.05, pz + 0.5), (px + x, y - 0.03, pz + 0.5), 0.3, GM, segs=12, bevel=0))
        b.add(cyl("glass", (px + x, y - 0.03, pz + 0.5), (px + x, y - 0.05, pz + 0.5), 0.22, "screen", segs=12, bevel=0), "lights")
    # Jacks, an insulated skirt round them, the landing and steps up to the hatch.
    for ax in (-1, 1):
        for ay in (-1, 1):
            x, y = px + ax * 1.7, py + ay * 0.9
            b.add(cyl("jack", (x, y, 0.15), (x, y, pz - 1.0), 0.11, GM, segs=8, bevel=0))
            b.add(cyl("jackfoot", (x, y, 0), (x, y, 0.15), 0.35, GM, segs=8, bevel=0))
    b.add(block("belly", (px, py, pz - 1.3), (3.0, 1.6, 0.4), GM, bevel=0))
    b.add(block("bellystrip", (px, py - 0.81, pz - 1.3), (2.6, 0.03, 0.08), BL, bevel=0), "lights")
    for ax in (-1, 1):
        b.add(block("saddle", (px + ax * 1.7, py, pz - 1.15), (0.3, 2.2, 0.3), GM, bevel=0))
    ly = fy - 0.55
    b.add(block("landing", (px, ly, FLOOR - 0.06), (1.5, 1.0, 0.12), GM, bevel=0))
    stair(b, (px, ly - 0.5 - 2.0, 0), 1.2, 2.0, FLOOR - 0.06, 6, material=GM, facing=1)
    for k in (-1, 1):
        b.add(cyl("handrail", (px + k * 0.65, ly - 2.5, 1.0), (px + k * 0.65, ly - 0.5, FLOOR + 1.0), 0.03, "steel", segs=6, bevel=0))
        b.add(cyl("railpost", (px + k * 0.65, ly - 2.45, 0), (px + k * 0.65, ly - 2.45, 1.0), 0.03, "steel", segs=6, bevel=0))
        b.add(cyl("railpost", (px + k * 0.65, ly - 0.5, FLOOR), (px + k * 0.65, ly - 0.5, FLOOR + 1.0), 0.03, "steel", segs=6, bevel=0))
    # Inside: a console under screens at the east end, a bunk at the west, a light.
    b.add(block("console", (px + 1.7, py + 0.55, FLOOR + 0.45), (0.9, 0.7, 0.9), GM, bevel=0))
    b.add(block("screens", (px + 1.7, py + 0.95, FLOOR + 1.35), (1.0, 0.05, 0.6), "blue_light", bevel=0, rot=-10), "lights")
    b.add(block("bunk", (px - 1.7, py + 0.5, FLOOR + 0.45), (1.0, 0.9, 0.15), "olive", bevel=0))
    b.add(block("locker", (px - 0.9, py + 0.85, FLOOR + 0.8), (0.5, 0.4, 1.6), "grey", bevel=0))
    b.node("lamp.0", (px, py, pz + 1.1))
    b.node("sound.hum.0", (px + 1.7, py + 0.55, FLOOR + 1.0))
    # Radiator fins off the back.
    for x in (-1.2, 0.0, 1.2):
        b.add(block("fin", (px + x, py + PR + 0.6, pz), (0.06, 1.0, 1.6), W, bevel=0))
        b.add(block("finstrut", (px + x, py + PR + 0.05, pz), (0.08, 0.3, 0.08), GM, bevel=0))
    # The radar mast west of the pod, its dish turning; strobes on it and on the pod roof.
    mx, my, mh = px - 3.6, py + 1.0, 4.6
    for ax, ay in ((-1, -1), (1, -1), (0, 1)):
        b.add(cyl("mastleg", (mx + ax * 0.6, my + ay * 0.5, 0), (mx, my, mh), 0.05, GM, segs=6, bevel=0))
    b.add(cyl("mast", (mx, my, 0), (mx, my, mh + 0.2), 0.09, GM, segs=8, bevel=0))
    b.add(block("radarbox", (mx, my, mh + 0.25), (0.5, 0.5, 0.3), W, bevel=0))
    pivot = (mx, my, mh + 0.4)
    tilt = (0.0, -0.5, 0.86)
    t = Vector(tilt).normalized()
    c = Vector((mx, my, mh + 0.95))
    dish = [block("yoke", (mx, my, mh + 0.6), (0.5, 0.3, 0.4), GM, bevel=0),
            cyl("dish", c - t * 0.1, c + t * 0.32, 0.25, W, r1=1.2, segs=18, bevel=0),
            cyl("feed", c + t * 0.3, c + t * 1.05, 0.03, "black", segs=6, bevel=0),
            sphere("horn", c + t * 1.05, 0.08, "black", segs=8),
            block("counter", (mx, my + 0.4, mh + 0.6), (0.3, 0.4, 0.3), HZ, bevel=0)]
    spinner(b, 0, pivot, "z", 12, dish)
    b.add(cyl("strobemount", (mx + 0.25, my, mh + 0.2), (mx + 0.25, my, mh + 0.0), 0.06, GM, segs=6, bevel=0))
    b.add(sphere("strobe", (mx + 0.3, my - 0.3, mh + 0.0), 0.1, "flood", segs=8), "lights")
    b.node("strobe.0", (mx + 0.3, my - 0.3, mh + 0.0))
    b.add(cyl("antenna", (px - 1.9, py, pz + PR - 0.1), (px - 1.9, py, pz + PR + 1.6), 0.03, "steel", segs=6, bevel=0))
    b.add(sphere("strobe", (px + 2.1, py, pz + PR + 0.08), 0.1, "flood", segs=8), "lights")
    b.node("strobe.1", (px + 2.1, py, pz + PR + 0.08))
    b.add(sphere("beacon", (px - 1.9, py, pz + PR + 1.65), 0.07, "red_light", segs=8), "lights")
    b.node("blink.0", (px - 1.9, py, pz + PR + 1.65))
    # A cargo crate and a fuel cell by the steps.
    b.add(block("crate", (px + 2.4, py - 2.6, 0.4), (1.0, 0.8, 0.8), GM, bevel=0))
    b.add(block("crateband", (px + 2.4, py - 2.6, 0.4), (1.02, 0.82, 0.18), HZ, bevel=0))
    b.add(cyl("cell", (px - 2.1, py - 2.4, 0), (px - 2.1, py - 2.4, 1.1), 0.3, W, segs=10, bevel=0))
    b.add(cyl("cellband", (px - 2.1, py - 2.4, 0.7), (px - 2.1, py - 2.4, 0.85), 0.31, BL, segs=10, bevel=0), "lights")
    return b


def _pod_boxes():
    px, py, pz = PC
    r = PR - 0.05
    return [
        box("pod deck", (px, py, FLOOR - 0.05), (PL, 2.3, 0.1)),
        box("pod roof", (px, py, pz + r - 0.1), (PL, 2.0, 0.2)),
        box("pod back", (px, py + 1.2, pz), (PL, 0.2, 2.2)),
        box("pod front", (px - (PL / 4 + DW / 4), py - 1.2, pz), (PL / 2 - DW / 2, 0.2, 2.2)),
        box("pod front", (px + (PL / 4 + DW / 4), py - 1.2, pz), (PL / 2 - DW / 2, 0.2, 2.2)),
        box("pod west", (px - PL / 2 - 0.3, py, pz), (0.6, 2.6, 2.6)),
        box("pod east", (px + PL / 2 + 0.3, py, pz), (0.6, 2.6, 2.6)),
        box("console", (px + 1.7, py + 0.55, FLOOR + 0.45), (0.9, 0.7, 0.9)),
        box("bunk", (px - 1.7, py + 0.5, FLOOR + 0.3), (1.0, 0.9, 0.6)),
        box("locker", (px - 0.9, py + 0.85, FLOOR + 0.8), (0.5, 0.4, 1.6)),
    ]


def _landing_y():
    px, py, pz = PC
    return py - math.sqrt(PR ** 2 - (FLOOR + 0.2 - pz) ** 2) - 0.02 - 0.55


SPEC = {
    "build": build,
    "name": "PMC sensor post",
    "color": (0.3, 0.65, 1.0),
    "faction": "pmc",
    "body": "frost",
    "footprint": (12.0, 11.0),
    "footprint_at": (0.0, 0.8),
    "door": (0.0, -3.6, 1.0),
    "size": (11.3, 13.7, 6.8),
    "depth": 0.3,
    "nodes": ["lamp.0", "blink.0", "strobe.0", "strobe.1", "sound.hum.0", "spin.y.12.0"],
    "boxes": [
        *_pod_boxes(),
        box("landing", (0.0, _landing_y(), FLOOR - 0.06), (1.5, 1.0, 0.12)),
        slope((0.0, _landing_y() - 2.5, 0), 1.2, 2.0, FLOOR - 0.06, 1),
        box("crate", (2.4, PC[1] - 2.6, 0.4), (1.0, 0.8, 0.8)),
        box("cell", (-2.1, PC[1] - 2.4, 0.55), (0.6, 0.6, 1.1)),
        box("radar mast", (-3.6, PC[1] + 1.0, 2.4), (1.2, 1.0, 4.8)),
        box("berm", (0.0, PC[1] + 4.4, 0.9), (8.0, 2.6, 1.8)),
        box("berm", (-4.6, PC[1] - 0.4, 0.8), (2.4, 6.4, 1.6)),
        box("berm", (4.6, PC[1] - 0.4, 0.8), (2.4, 6.4, 1.6)),
    ],
    "crew": [
        ("contractor", (0.7, PC[1] + 0.1, FLOOR), 90.0, []),
        ("handler", (-3.0, -3.8, 0.0), 0.0, [(3.0, -3.8, 0.0), (3.2, -4.5, 0.0), (-3.2, -4.5, 0.0)]),
    ],
    "view": {"cam": (-16.0, -26.0, 10.0), "look": (0, 1.0, 2.0), "lens": 40},
    "near": {"cam": (2.8, -7.5, 1.7), "look": (0, 1.0, 2.2), "lens": 24},
}
