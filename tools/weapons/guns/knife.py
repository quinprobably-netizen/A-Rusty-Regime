"""Talon: a fixed-blade combat knife. Drop-point blade with a fuller, a thumb-ramp of serrations on the
spine and the maker's name on the flat, a small crossguard, a cord-wrapped grip with finger grooves,
and a pommel with a lanyard hole, a glass-breaker stud and a red-beaded lanyard that swings.

Modelled with the origin at the middle of the grip, the blade along +Y and the edge down (-Z), then
set into the pistol grip's place: the handle lies where a pistol's grip does (assets/grips.toml
[pistol] right, leaning like the solver's right hold) with the blade up and forward and the edge
forward, so the right hand's solved pistol pose wraps it, the index along the guard.
"""

import math

from mathutils import Matrix, Vector

from kit import begin, block, cut, cyl, hole_through, join, label, prism, slots
from parts import MAKER

HOLE = (0.0, -0.074, -0.011)

# The pistol's right hold in Blender axes (glTF (x, y, z) is Blender (x, -z, y)): the grip's middle
# and the way it leans, up and forward.
GRIP = Vector((0.0, -0.055, -0.05))
_up = Vector((0.0, 0.4, 1.0)).normalized()
_edge = Vector((0.0, _up.z, -_up.y))  # forward, square to the handle
# Knife +Y (blade) -> up, knife -Z (edge) -> forward, so knife +Z -> back; X stays the knife's own.
_z = -_edge
_x = _up.cross(_z)
SET = Matrix(((_x.x, _up.x, _z.x), (_x.y, _up.y, _z.y), (_x.z, _up.z, _z.z))).to_4x4()
SET.translation = GRIP


def at(p):
    """A point of the knife as modelled, in the weapon's space."""
    return SET @ Vector(p)


def swing(deg, push=(0, 0, 0)):
    """A pose that turns the knife by `deg` (x, y, z) about the grip, plus `push` metres."""
    r = Matrix.Rotation(math.radians(deg[2]), 3, "Z") @ Matrix.Rotation(math.radians(deg[1]), 3, "Y") @ Matrix.Rotation(math.radians(deg[0]), 3, "X")
    t = GRIP - r @ GRIP + Vector(push)
    return tuple(round(v, 5) for v in t), tuple(deg)


def build():
    g = begin("knife", {"lanyard": (tuple(at(HOLE)), None)})
    add = g.add

    def put(obj, bone="root"):
        obj.data.transform(SET)
        return add(obj, bone)

    g.add = put
    # The blade: a drop point, ground with a fuller each side and serrations on the spine.
    blade = prism("blade", [(0.066, 0.0165), (0.150, 0.0165), (0.185, 0.0150), (0.215, 0.0085), (0.232, -0.001), (0.217, -0.0095),
                            (0.190, -0.0145), (0.140, -0.0175), (0.066, -0.0165)], 0.0048, "bright", bevel=0.0005)
    cuts = [block("fuller", (s * 0.0024, 0.138, 0.005), (0.0016, 0.105, 0.0052), "steel", bevel=0) for s in (-1, 1)]
    cuts += slots("ser", 0.082, 0.140, 8, 0.0125, 0.0200, -0.01, 0.01)
    blade = cut(blade, *cuts)
    # A darker secondary bevel along the edge, so the grind reads from the camera.
    edge = prism("edge", [(0.070, -0.0140), (0.140, -0.0150), (0.188, -0.0120), (0.216, -0.0085), (0.231, -0.0010), (0.214, -0.0090),
                          (0.190, -0.0145), (0.140, -0.0176), (0.070, -0.0166)], 0.0052, "steel", bevel=0.0002)
    g.add(join([blade, edge, label("TALON", (-0.0027, 0.092, -0.0085), 0.0052, "black"),
                label(MAKER, (0.0027, 0.100, -0.0085), 0.0030, "black", side=1)], "blade"), "root")
    # Guard and ricasso block.
    guard = prism("guard", [(0.054, -0.0215), (0.067, -0.0215), (0.069, -0.016), (0.069, 0.0195), (0.054, 0.0195)], 0.0235, "steel", bevel=0.0012)
    guard = cut(guard, block("slot", (0, 0.0615, 0.0), (0.0058, 0.0025, 0.05), "steel", bevel=0))
    g.add(guard, "root")
    # The handle: a profile with three finger grooves, wrapped in cord with a tan core showing.
    top = [(-0.070, 0.0140), (-0.040, 0.0172), (0.020, 0.0162), (0.056, 0.0135)]
    bottom = [(0.056, -0.0160), (0.046, -0.0160), (0.041, -0.0120), (0.031, -0.0120), (0.026, -0.0170), (0.013, -0.0170), (0.008, -0.0125),
              (-0.003, -0.0125), (-0.008, -0.0180), (-0.021, -0.0180), (-0.026, -0.0135), (-0.036, -0.0135), (-0.041, -0.0175), (-0.068, -0.0190)]
    handle = prism("handle", top + bottom, 0.0215, "tan", bevel=0.0012)
    wraps = []
    for i in range(15):
        y = -0.052 + i * 0.0072
        wraps.append(block("wrap", (0, y, 0.0), (0.0252, 0.0042, 0.0255), "olive" if i % 2 == 0 else "cord", bevel=0.0008))
    g.add(join([handle, *wraps], "grip"), "root")
    # The pommel: a block with the lanyard hole, a glass-breaker stud and a seam of red.
    pommel = block("pommel", (0, -0.076, 0.0), (0.0255, 0.0150, 0.0400), "steel", bevel=0.003, segs=3)
    pommel = cut(pommel, hole_through("lanyardhole", HOLE, 0.0036, "x"))
    stud = cyl("stud", (0, -0.082, 0.014), (0, -0.0925, 0.014), 0.0062, "bright", r1=0.0018, segs=12, bevel=0.0003)
    ring = block("pommelband", (0, -0.0675, 0.0), (0.0262, 0.0030, 0.0382), "red", bevel=0.0006)
    g.add(join([pommel, stud, ring], "pommel"), "root")
    # The lanyard: two cords through the hole and a bead, on its own bone so it swings.
    cord = [cyl("cord", (s * 0.002, -0.074, -0.011), (s * 0.002, -0.081, -0.052), 0.0016, "cord", segs=6, bevel=0) for s in (-1, 1)]
    bead = cyl("bead", (0, -0.081, -0.050), (0, -0.081, -0.062), 0.0055, "red", segs=12, bevel=0.0006)
    knot = cyl("knot", (0, -0.0805, -0.047), (0, -0.0805, -0.051), 0.0035, "cord", segs=8, bevel=0)
    g.add(join([*cord, bead, knot], "lanyard"), "lanyard")
    g.socket("muzzle", tuple(at((0, 0.232, -0.001))), "root")

    Z = (0, 0, 0)

    def pose(deg, push=(0, 0, 0)):
        t, r = swing(deg, push)
        return t, r

    def key(time, deg, push=(0, 0, 0)):
        t, r = swing(deg, push)
        return (time, t, r)

    # Slash: wind up with the tip back and the edge turned out, chop down across and through, recover.
    g.clip("fire", 0.5, {
        "root": [(0, Z, Z), key(0.09, (38, 6, -24), (0.0, -0.03, 0.02)), key(0.16, (-10, -4, 6), (0.0, 0.06, 0.0)),
                 key(0.22, (-78, 8, 24), (0.0, 0.1, -0.04)), key(0.3, (-60, 6, 18), (0.0, 0.08, -0.03)), (0.5, Z, Z)],
        "lanyard": [(0, Z, Z), (0.09, Z, (-35, 0, 0)), (0.2, Z, (40, 0, 0)), (0.32, Z, (-18, 0, 0)), (0.5, Z, Z)],
    })
    # Reload is the flourish: a flip of the knife about its own handle.
    g.clip("reload", 0.9, {
        "root": [(0, Z, Z), key(0.15, (-20, 0, 0)), key(0.4, (-120, 0, 0)), key(0.65, (-250, 0, 0)), key(0.8, (-340, 0, 0)), (0.9, Z, Z)],
        "lanyard": [(0, Z, Z), (0.3, Z, (50, 0, 0)), (0.6, Z, (-40, 0, 0)), (0.9, Z, Z)],
    })
    g.clip("draw", 0.4, {
        "root": [key(0, (-50, 0, 20), (0.0, -0.04, -0.14)), key(0.28, (4, 0, 0), (0.0, 0.004, 0.004)), (0.4, Z, Z)],
        "lanyard": [(0, Z, (-40, 0, 0)), (0.2, Z, (30, 0, 0)), (0.4, Z, Z)],
    })
    # Inspect: turn the blade over to the light and back.
    g.clip("inspect", 3.0, {
        "root": [(0, Z, Z), key(0.5, (0, -30, 15), (-0.03, 0.02, 0.03)), key(1.2, (0, -150, 25), (-0.03, 0.02, 0.03)),
                 key(1.9, (0, -250, 25), (-0.03, 0.02, 0.03)), key(2.4, (0, -380, 10), (0.0, 0.0, 0.02)), (3.0, Z, Z)],
        "lanyard": [(0, Z, Z), (1.0, Z, (60, 0, 0)), (1.6, Z, (-50, 0, 0)), (2.2, Z, (30, 0, 0)), (3.0, Z, Z)],
    })
    g.clip("idle", 2.4, {
        "root": [(0, Z, Z), (1.2, (0, 0, 0.0012), (0.5, 0, 0)), (2.4, Z, Z)],
        "lanyard": [(0, Z, Z), (0.8, Z, (6, 0, 0)), (1.6, Z, (-6, 0, 0)), (2.4, Z, Z)],
    })
    return g


SPEC = {"build": build, "length": (0.12, 0.2), "tris": (1500, 40000), "muzzle_front": False,  # length is along the barrel axis; the blade stands up
        
        "bones": ["root", "lanyard"],
        "sockets": ["muzzle"],
        "parts": {"mesh.root": "root", "mesh.lanyard": "lanyard"},
        "moves": {"fire": ["root", "lanyard"], "reload": ["root", "lanyard"], "draw": ["root", "lanyard"], "inspect": ["root", "lanyard"]},
        "view": {"cam": (-0.52, 0.0, 0.1), "look": (0, 0.0, 0.0), "lens": 45}}
