"""The Scrappers' camp on Cinder: two shipping containers welded into an L and half swallowed by a
dune. The long one has its side cut out for a shelter, a hazard-yellow and rust shade sail stretched
from its roof to two poles; the other noses down into the sand. A small three-blade wind turbine
turns on a guyed mast, and a drum fire burns under the sail among tyres, drums and scrap."""

import math

from basekit import Base, box, container, ring, spinner
from kit import block, cut, cyl, plan, rotate, sphere, wk
from interior import barrel, crate, gas_bottle
from posts import flames, mound

A = ((-0.3, 1.9), (6.0, 2.4, 2.6))   # the shelter container: centre (x, y), size; open on -Y
B = ((3.9, 0.6), (2.4, 6.0, 2.6))    # the buried one, along Y
WALL = 0.08
rust, haz = "rust", "hazard"


def shelter(b):
    (x, y), (sx, sy, sz) = A
    for name, c, size, _ in _shelter_boxes()[:8]:  # walls, roof and floor as plain slabs: clean normals, few tris
        b.add(block(name, c, size, "olive" if "floor" not in name else "steel", bevel=0))
    for i in range(10):  # corrugation on the back and what is left of the front
        xx = x - sx / 2 + (i + 0.5) * sx / 10
        b.add(block("rib", (xx, y + sy / 2 + 0.015, sz / 2), (0.2, 0.03, sz - 0.3), "olive", bevel=0))
        if abs(xx - x + 0.2) > 2.2:
            b.add(block("rib", (xx, y - sy / 2 - 0.015, sz / 2), (0.2, 0.03, sz - 0.3), "olive", bevel=0))
    for ax in (-1, 1):
        for ay in (-1, 1):
            b.add(block("corner", (x + ax * (sx / 2 - 0.08), y + ay * (sy / 2 - 0.08), sz / 2), (0.18, 0.18, sz + 0.02), "black", bevel=0))
    b.add(block("band", (x, y - sy / 2 - 0.035, sz - 0.25), (sx, 0.03, 0.22), haz, bevel=0))
    b.add(block("lip", (x - 0.2, y - sy / 2 - 0.05, 2.15), (4.4, 0.1, 0.1), "brass", bevel=0))  # the weld bead round the cut
    for k in (-1, 1):
        b.add(block("lip", (x - 0.2 + k * 2.15, y - sy / 2 - 0.05, 1.08), (0.1, 0.1, 2.16), "brass", bevel=0))
    # Inside: a cot, a bench with a lamp, a gas bottle.
    b.add(block("cot", (x - 2.0, y + 0.5, 0.45), (1.8, 0.8, 0.12), "olive", bevel=0))
    for dx in (-0.8, 0.8):
        b.add(block("cotleg", (x - 2.0 + dx, y + 0.5, 0.22), (0.05, 0.75, 0.4), "steel", bevel=0))
    b.add(block("bench", (x + 1.6, y + 0.75, 0.85), (2.0, 0.6, 0.08), "steel", bevel=0))
    b.add(block("benchbase", (x + 1.6, y + 0.75, 0.42), (1.9, 0.5, 0.8), rust, bevel=0))
    b.add(gas_bottle("gas", (x + 2.6, y + 0.2, WALL), material="olive"))
    b.add(sphere("bulb", (x, y, sz - 0.35), 0.08, "lamp", segs=8), "lights")
    b.node("lamp.0", (x, y, sz - 0.5))


def build():
    b = Base("camp")
    # The dune: a long heap behind and round the east end, a lower tail west; the shelter's inside
    # is cut out of it so the sand stops at the walls.
    (ax, ay), (asx, asy, asz) = A
    dune = mound(b, "dune", (2.4, 4.2, -2.4), (5.6, 4.4, 6.0), "dune", segs=20)
    tail = mound(b, "dune", (-3.3, 3.4, -1.2), (2.7, 2.6, 2.9), "dune", segs=14)
    drift = mound(b, "drift", (-0.6, 2.9, 2.3), (3.0, 1.3, 0.62), "dune", segs=12)
    for o in (dune, tail, drift):
        cut(o, block("cavity", (ax, ay, asz / 2), (asx - 0.02, asy - 0.02, asz + 1.0), "dune", bevel=0),
            block("apron", (ax - 0.3, ay - asy / 2 - 2.4, 2.0), (asx + 0.6, 5.0, 4.0), "dune", bevel=0))
        wk.apply_modifiers(o)
    shelter(b)
    # The second container welded to its east end, nose down into the sand.
    (bx, by), bs = B
    c = (bx, by, bs[2] / 2 - 0.35)
    rotate(container(b, c, bs, material=rust, band=haz, doors="-y"), c, "x", -7)
    for z in (0.6, 1.4, 2.2):
        b.add(block("weld", (ax + asx / 2 + 0.02, ay - 1.0, z), (0.1, 0.12, 0.5), "brass", bevel=0))
    # The shade sail: two overlapping triangles from the shelter roof to two poles, sloping down.
    for k in (-1, 1):
        px = k * 3.0
        b.add(cyl("pole", (px, -3.4, 0), (px, -3.4, 2.75), 0.06, "steel", segs=6, bevel=0))
        b.add(cyl("guy", (px, -3.4, 2.7), (px * 1.25, -4.6, 0), 0.012, "black", segs=4, bevel=0))
    s1 = plan("sail", [(-3.3, 0.7), (2.7, 0.7), (-3.0, -3.4)], 0.03, haz, z=0, bevel=0)
    s2 = plan("sail", [(2.7, 0.7), (3.0, -3.4), (-3.0, -3.4)], 0.03, rust, z=0, bevel=0)
    for s, dz in ((s1, 0.05), (s2, 0.0)):
        for v in s.data.vertices:  # slope each from the roof (2.7) down to the poles (2.6)
            v.co.z += 2.55 + dz + (v.co.y + 3.4) / 4.1 * 0.12 + (0.25 if v.co.y > 0 else 0.0)
        b.add(s)
    # The wind turbine: a guyed mast, a nacelle and tail, three blades that turn.
    tx, ty, th = -4.2, -0.9, 6.4
    b.add(cyl("tower", (tx, ty, 0), (tx, ty, th), 0.09, "steel", segs=6, bevel=0))
    for a in (0.5, 2.6, 4.7):
        b.add(cyl("guy", (tx, ty, th * 0.7), (tx + 2.1 * math.cos(a), ty + 2.1 * math.sin(a), 0), 0.012, "black", segs=4, bevel=0))
    b.add(block("nacelle", (tx, ty + 0.15, th + 0.1), (0.3, 0.8, 0.3), "olive", bevel=0))
    b.add(block("tailboom", (tx, ty + 0.9, th + 0.1), (0.05, 0.9, 0.05), "steel", bevel=0))
    b.add(block("vane", (tx, ty + 1.4, th + 0.2), (0.03, 0.6, 0.55), haz, bevel=0))
    hub = (tx, ty - 0.3, th + 0.1)
    rotor = [cyl("hub", (hub[0], hub[1] + 0.1, hub[2]), (hub[0], hub[1] - 0.15, hub[2]), 0.14, "brass", r1=0.05, segs=8, bevel=0)]
    for i in range(3):
        a = i * math.tau / 3
        blade = block("blade", (hub[0], hub[1] - 0.02, hub[2] + 0.85), (0.24, 0.04, 1.5), "white" if i else haz, bevel=0, taper=(0.4, 1.0))
        rotate(blade, hub, "y", math.degrees(a))
        rotor.append(blade)
    spinner(b, 0, hub, "y", 90, rotor)
    b.node("sound.wind.0", (tx, ty, th))
    # The drum fire under the sail, and what lies about.
    fx, fy = 0.4, -1.9
    b.add(barrel("firedrum", (fx, fy, 0), r=0.3, h=0.85, material=rust))
    for i in range(6):
        a = i * math.tau / 6
        b.add(block("vent", (fx + 0.305 * math.cos(a), fy + 0.305 * math.sin(a), 0.35), (0.06, 0.06, 0.14), "fire_light", bevel=0), "lights")
    b.add(cyl("coals", (fx, fy, 0.82), (fx, fy, 0.86), 0.27, "fire_light", segs=8, bevel=0), "lights")
    flames(b, (fx, fy, 0.84), 0.28)
    b.node("fire.0", (fx, fy, 1.2))
    b.node("smoke.0", (fx, fy, 1.6))
    b.node("sound.fire.0", (fx, fy, 0.9))
    for i, (x, y) in enumerate(((-2.4, -1.4), (-1.9, -2.2))):
        b.add(crate("seat", (x, y, 0.22), (0.6, 0.45, 0.44), material=["olive", "brass"][i]))
    for i, z in enumerate((0.13, 0.41, 0.69)):
        b.add(ring("tyre", (2.6 + 0.04 * i, -2.6, z), (0, 0, 1), 0.42, 0.24, 0.26, "black", segs=12))
    for i, (x, y) in enumerate(((-3.6, 0.2), (-3.0, 0.5))):
        b.add(cyl("drum", (x, y, 0), (x, y, 0.9), 0.3, ["olive", haz][i], segs=10, bevel=0))
    b.add(block("sheet", (B[0][0] - 0.2, B[0][1] - 3.25, 0.75), (1.6, 0.05, 1.5), "grey", bevel=0, rot=-14))
    # A sand fence on the windward side, half drifted under.
    for i in range(7):
        b.add(block("slat", (-5.7 + i * 0.05, -1.6 + i * 0.55, 0.45), (0.06, 0.12, 0.9), "timber_dark", bevel=0))
    b.add(block("fencewire", (-5.55, 0.05, 0.75), (0.02, 3.4, 0.02), "black", bevel=0))
    return b


def _shelter_boxes():
    (x, y), (sx, sy, sz) = A
    door_x, door_w, door_h = x - 0.2, 4.2, 2.1
    left = (x - sx / 2, door_x - door_w / 2)
    right = (door_x + door_w / 2, x + sx / 2)
    yf = y - sy / 2 + WALL / 2
    return [
        box("shelter floor", (x, y, WALL / 2), (sx, sy, WALL)),
        box("shelter roof", (x, y, sz - WALL / 2), (sx, sy, WALL)),
        box("shelter back", (x, y + sy / 2 - WALL / 2, sz / 2), (sx, WALL, sz)),
        box("shelter west", (x - sx / 2 + WALL / 2, y, sz / 2), (WALL, sy, sz)),
        box("shelter east", (x + sx / 2 - WALL / 2, y, sz / 2), (WALL, sy, sz)),
        box("shelter front", ((left[0] + left[1]) / 2, yf, sz / 2), (left[1] - left[0], WALL, sz)),
        box("shelter front", ((right[0] + right[1]) / 2, yf, sz / 2), (right[1] - right[0], WALL, sz)),
        box("shelter lintel", (door_x, yf, (WALL + door_h + sz) / 2), (door_w, WALL, sz - WALL - door_h)),
        box("cot", (x - 2.0, y + 0.5, 0.25), (1.8, 0.8, 0.5)),
        box("bench", (x + 1.6, y + 0.75, 0.45), (2.0, 0.6, 0.9)),
    ]


SPEC = {
    "build": build,
    "name": "Scrapper camp",
    "color": (1.0, 0.85, 0.1),
    "faction": "scrappers",
    "body": "cinder",
    "footprint": (12.0, 11.0),
    "footprint_at": (0.5, 1.5),
    "door": (-0.5, -0.4, 1.0),
    "size": (12.9, 13.6, 8.8),
    "depth": 0.71,
    "nodes": ["lamp.0", "fire.0", "smoke.0", "sound.fire.0", "sound.wind.0", "spin.z.-90.0"],
    "boxes": [
        *_shelter_boxes(),
        box("container", (B[0][0], B[0][1], 0.95), (2.4, 6.0, 2.6), (-7, 0, 0)),
        box("dune", (1.9, 5.6, 1.2), (9.0, 3.4, 2.4)),
        box("drum fire", (0.4, -1.9, 0.45), (0.65, 0.65, 0.9)),
        box("tyres", (2.65, -2.6, 0.4), (0.9, 0.9, 0.8)),
    ],
    "crew": [
        ("mechanic", (-0.7, -2.4, 0.0), 300.0, []),
        ("bruiser", (0.4, 1.7, WALL), 0.0, []),
    ],
    "view": {"cam": (21.0, -21.0, 11.0), "look": (0.5, 1.0, 1.8), "lens": 40},
    "near": {"cam": (-3.0, -8.5, 1.7), "look": (0.5, 1.0, 1.4), "lens": 24},
}
