"""The Scrappers' Yard on Cinder: a container fort half-buried in the rust desert. The prevailing
wind comes off the west, so the dunes bank hardest against the west wall (deep enough to walk up
onto the containers), slat sand fences run across the drifts, and the north and front walls
carry smaller drifts. Two container-tower corners: the north-west lookout and the north-east one
carrying a three-blade wind turbine; a drum Savonius turbine spins on the south-east stack.
Inside: a scrap mountain heaped in the north-west corner under a tower crane whose jib slowly
slews over it, a glowing cupola smelter with a tall stack and ingot moulds, a burn-barrel
hangout under a yellow shade sail, a container made into quarters, and the workshop shed (a
buggy frame on stands being welded, a welding table, a bench grinder, the tool wall). Outside the
east wall the tuning garage: the engine on its stand, the Tuning rig console and the Parts rack
counter, each with its mechanic behind it. Brass, copper, rust, olive and the Scrappers'
yellow; sand in the "sand" palette."""

import math
import random

import bmesh
from basekit import Base, box, container, floodlight, hall, life_node, railing, ring, room, room_boxes, spinner, truss
from kit import block, cyl, label, rivets, rotate, seams, sphere, stripe, wk
from interior import (bunk, cabinet, cable_bundle, crate, extinguisher, gas_bottle, grating, gun_rack, hoist, lamp, pipe_run, turn,
                      tyre, wheel, workbench)
from mathutils import Vector

wk.PALETTE.setdefault("molten", ((1.0, 0.36, 0.05), (1.0, 0.36, 0.05), 0.0, 0.3, 0.0, 7.0))

C = (2.4, 6.0, 2.6)  # a container, long along Y
rust, brass, copper, hazard, leather, sand = "rust", "brass", "copper", "hazard", "leather", "sand"

# The fort: walls of containers round x -15..15, y -13.2..13.2; the gate in the front (-Y) wall.
WALL_X = 13.8  # the side walls' centre lines (x -15..-12.6 and 12.6..15)
WALL_Y = 12.0  # the front and back walls' centre lines (y 10.8..13.2)
SIDE_YS = (-7.8, -1.8, 4.2)  # side wall containers; the corner towers fill y 7.2..10.8
BACK_XS = (-12.0, -6.0, 0.0, 6.0, 12.0)
FRONT_XS = (-12.0, -6.0, 6.0, 12.0)
STACK = {"w": (1,), "e": (2,), "n": (1, 3), "s": (0, 3)}  # which get a second container on top
TOWER = (2.4, 3.6, 7.8)
TOWERS = ((-WALL_X, 9.0), (WALL_X, 9.0))
SHED = ((4.5, 5.9, 2.75), (13.0, 9.6, 5.5))
SMELTER = (8.6, -2.8)
QUARTERS = ((9.2, -8.0, 1.3), (6.0, 2.6, 2.6))
CRANE = (-5.0, -1.0)
CRANE_H = 13.0
HEAP = (-9.0, 6.0, 6.5, 8.0)  # x, y, radius, height
GENSET = (-11.6, -4.6)
GARAGE = ((22.0, -1.5), (8.0, 7.0, 3.8))
GARAGE_DOORS = [("-y", 0.0, 2.6, 2.8)]
RIG = (22.8, 0.4)  # the Tuning rig console's floor centre
RACK = (24.35, -2.5)  # the Parts rack counter's centre
F = 0.25  # the shed's and the garage's floor top

# The drifts: (face, wall's outer face, from, to along it, height at the wall, reach, taper).
_gy, _gx = GARAGE[0][1] + GARAGE[1][1] / 2, GARAGE[0][0] + GARAGE[1][0] / 2
DRIFTS = [
    ("-x", -15.0, -13.6, -0.5, 2.0, 7.5, 3.0),
    ("-x", -15.0, -4.5, 11.2, 2.5, 8.6, 3.5),
    ("+y", 13.2, -15.5, 4.0, 1.8, 5.0, 3.0),
    ("+y", 13.2, 1.0, 13.5, 1.1, 3.6, 2.5),
    ("-y", -13.2, -16.0, -4.6, 1.4, 3.3, 2.5),
    ("+x", 15.0, 2.2, 11.8, 1.5, 4.0, 2.5),
    ("+y", _gy, 17.6, 26.2, 1.2, 3.0, 2.0),
    ("+x", _gx, -5.2, 2.3, 1.3, 3.2, 2.0),
]
FENCES = [((-22.6, -15.0), (-21.6, 9.0)), ((-24.6, -4.0), (-24.0, 17.5)), ((-21.0, 17.6), (3.0, 18.2))]
FENCE_H = 1.15


class Collect:
    """Stands in for the base while building a moving part: kit helpers that `add` their parts
    land here, and the list goes to `spinner`."""

    def __init__(self):
        self.parts = []

    def add(self, obj, group="hull"):
        self.parts.append(obj)
        return obj


# ------------------------------------------------------------------------------------ the sand

def field(name, origin, eu, ev, us, vs, fn, base_z=0.0, material=sand):
    """A sand surface over a grid: world point origin + u*eu + v*ev (xy) at height base_z + fn(u, v)
    for u in `us`, v in `vs`. Quads flat on the base are left out; their edge vertices sit just
    under it so the sand meets the ground without a seam."""
    bm = bmesh.new()
    h = [[fn(u, v) for v in vs] for u in us]
    verts = {}

    def vert(i, j):
        if (i, j) not in verts:
            u, v = us[i], vs[j]
            z = base_z + (h[i][j] if h[i][j] > 0.005 else -0.03)
            verts[(i, j)] = bm.verts.new((origin[0] + u * eu[0] + v * ev[0], origin[1] + u * eu[1] + v * ev[1], z))
        return verts[(i, j)]

    for i in range(len(us) - 1):
        for j in range(len(vs) - 1):
            if max(h[i][j], h[i + 1][j], h[i + 1][j + 1], h[i][j + 1]) <= 0.005:
                continue
            q = [vert(i, j), vert(i + 1, j), vert(i + 1, j + 1), vert(i, j + 1)]
            n = (q[1].co - q[0].co).cross(q[2].co - q[0].co)
            bm.faces.new(q if n.z > 0 else q[::-1])
    return wk._obj(name, bm, material, 0.0)


def steps(a, b, step):
    n = max(1, int(math.ceil((b - a) / step)))
    return [a + (b - a) * i / n for i in range(n + 1)]


def smooth(e):
    e = max(0.0, min(1.0, e))
    return e * e * (3 - 2 * e)


FACE = {"-x": ((-1, 0), (0, 1)), "+x": ((1, 0), (0, 1)), "-y": ((0, -1), (1, 0)), "+y": ((0, 1), (1, 0))}


def drift_box(face, at, a0, a1, H, L, fall):
    """The collision box of a `drift`: a slab under the planar middle of its slope."""
    (nx, ny), (tx, ty) = FACE[face]
    ox, oy = at * abs(nx), at * abs(ny)
    th = 0.4
    norm = math.hypot(H / L, 1.0)
    vc, zc = L / 2 - (H / L) / norm * th / 2, H / 2 - th / norm / 2
    uc, width = (a0 + a1) / 2, a1 - a0 - 1.2 * fall
    cx, cy = ox + uc * tx + vc * nx, oy + uc * ty + vc * ny
    slen, deg = math.hypot(H, L), math.degrees(math.atan2(H, L))
    if face in ("-x", "+x"):
        return box("drift", (cx, cy, zc), (slen, width, th), (0, -deg if face == "-x" else deg, 0))
    return box("drift", (cx, cy, zc), (width, slen, th), (deg if face == "-y" else -deg, 0, 0))


def drift(b, face, at, a0, a1, H, L, fall, seed=0.0):
    """Sand banked against a wall whose outer face is at `at` on `face`, from a0 to a1 along it:
    H high at the wall, sloping straight down to the ground L out (with an eased toe), tapering
    off over `fall` at each end."""
    (nx, ny), (tx, ty) = FACE[face]

    def fn(u, v):
        g = smooth(min(u - a0, a1 - u) / fall)
        if g <= 0:
            return 0.0
        hs = H * g * (1 + 0.05 * math.sin(0.8 * u + seed))
        t = max(v, 0.0) / (L * (0.45 + 0.55 * g))
        prof = 1 - t if t < 0.85 else ((1.15 - t) ** 2 / 0.6 if t < 1.15 else 0.0)
        return hs * prof

    b.add(field("drift", (at * abs(nx), at * abs(ny)), (tx, ty), (nx, ny), steps(a0, a1, 0.7), [-0.8] + steps(0.0, L * 1.16, 0.6), fn))


def mound(b, c, R, H, base_z=0.0, step=0.7, squash=(1.0, 1.0)):
    """A round heap of sand: H high in the middle, gone at R (scaled by `squash` in x and y)."""
    x, y = c

    def fn(u, v):
        r = math.hypot(u / squash[0], v / squash[1]) / R
        return H * smooth(1 - r) * (1 + 0.05 * math.sin(3 * u + 2 * v)) if r < 1 else 0.0

    us = steps(-R * squash[0], R * squash[0], step)
    vs = steps(-R * squash[1], R * squash[1], step)
    b.add(field("mound", (x, y), (1, 0), (0, 1), us, vs, fn, base_z=base_z))


def ridge(b, p0, p1, H, w, lee=0.5):
    """The low drift a fence catches along its line, H high, banked to the lee (+X or -Y) side."""
    a, z = Vector((*p0, 0)), Vector((*p1, 0))
    length = (z - a).length
    t = (z - a).normalized()
    n = Vector((t.y, -t.x, 0))
    if n.x < -0.5 or (abs(n.x) <= 0.5 and n.y > 0):
        n = -n

    def fn(u, v):
        g = smooth(min(u, length - u) / 2.5)
        off = v - lee
        k = 1 - abs(off) / (w * (1.5 if off > 0 else 0.7))
        return H * g * smooth(k) * (1 + 0.1 * math.sin(1.3 * u)) if k > 0 else 0.0

    b.add(field("ridge", (a.x, a.y), (t.x, t.y), (n.x, n.y), steps(0, length, 0.8), steps(-w, w * 2.0, 0.35), fn))


def fence_box(p0, p1):
    a, z = Vector((*p0, 0)), Vector((*p1, 0))
    d, mid = z - a, (a + z) / 2
    return box("fence", (mid.x, mid.y, FENCE_H / 2), (d.length, 0.15, FENCE_H), (0, 0, math.degrees(math.atan2(d.y, d.x))))


def sand_fence(b, p0, p1, seed=1):
    """A slat fence across the dunes: grey timber pickets on two wires, posts every 3 m, leaning
    and half buried."""
    rng = random.Random(seed)
    a, z = Vector((*p0, 0)), Vector((*p1, 0))
    d = z - a
    yaw = math.degrees(math.atan2(d.y, d.x))
    parts = []
    n = int(d.length / 0.34)
    for i in range(n):
        p = a.lerp(z, (i + 0.5) / n)
        hh = FENCE_H * rng.uniform(0.78, 1.0)
        o = block("picket", (p.x, p.y, hh / 2 - rng.uniform(0.0, 0.25)), (0.035, 0.16, hh), "tan" if i % 7 else "grey", bevel=0)
        rotate(o, (p.x, p.y, 0), "y", rng.uniform(-6, 6))
        parts.append(turn(o, (p.x, p.y, 0), yaw))
    m = int(d.length / 3.0)
    for i in range(m + 1):
        p = a.lerp(z, i / m)
        parts.append(cyl("post", (p.x, p.y, -0.2), (p.x, p.y, FENCE_H + 0.1), 0.06, "black", segs=6, bevel=0))
    for zz in (0.3, FENCE_H - 0.15):
        parts.append(cyl("wire", (a.x, a.y, zz), (z.x, z.y, zz), 0.012, "steel", segs=4, bevel=0))
    b.add(wk.join(parts, "fence"))


def ground(b):
    """The sand the fort stands in: a slab over the foundation, its skirt sloping down so the
    foundation's edges are buried."""
    (fx, fy), (sx, sy) = SPEC["footprint_at"], SPEC["footprint"]
    b.add(block("ground", (fx, fy, -0.29), (sx + 5.0, sy + 5.0, 0.62), sand, taper=((sx + 0.3) / (sx + 5.0), (sy + 0.3) / (sy + 5.0)), bevel=0))


def dunes(b):
    """Drifts against the walls, sand on the corners, the roofs and in the gate, fences across."""
    for k, d in enumerate(DRIFTS):
        drift(b, *d, seed=k * 1.7)
    mound(b, (-15.6, 13.6), 6.0, 2.4)
    mound(b, (15.4, 13.4), 4.0, 1.4)
    mound(b, (-15.4, -13.4), 4.0, 1.5)
    mound(b, (-12.4, -9.6), 2.6, 0.7, squash=(0.7, 1.4))
    mound(b, (0.0, -12.2), 3.0, 0.12, squash=(1.0, 0.6))
    mound(b, (9.6, 9.0), 2.6, 0.45, base_z=5.5, squash=(1.0, 0.6))
    mound(b, (-13.8, -4.2), 2.4, 0.35, base_z=2.6, squash=(0.45, 1.0))
    mound(b, (6.0, 12.0), 2.6, 0.4, base_z=5.2, squash=(1.0, 0.45))
    for k, (p0, p1) in enumerate(FENCES):
        ridge(b, p0, p1, 0.5, 1.4)
        sand_fence(b, p0, p1, seed=k + 1)


# ------------------------------------------------------------------------------------ the walls

def wall_container(b, c, material, band=None, along="y", doors="-y"):
    """A container on the wall; `along` is the way its length runs."""
    o = container(b, c, C, material=material, band=band, doors=doors)
    if along == "x":
        turn(o, c, 90)
    return o


def walls(b):
    mats = [rust, "olive", copper, "grey", "yellow", "red"]
    for side, sx in (("w", -1), ("e", 1)):
        for i, y in enumerate(SIDE_YS):
            wall_container(b, (sx * WALL_X, y, 1.3), mats[(i + (0 if sx < 0 else 3)) % 6], band=hazard if i == 1 else None)
            if i in STACK[side]:
                wall_container(b, (sx * WALL_X, y, 3.9), mats[(i + 2) % 6], doors="+y")
    for side, y, xs in (("n", WALL_Y, BACK_XS), ("s", -WALL_Y, FRONT_XS)):
        for i, x in enumerate(xs):
            wall_container(b, (x, y, 1.3), mats[(i * 2 + (1 if y > 0 else 0)) % 6], band=hazard if i % 2 else None, along="x")
            if i in STACK[side]:
                wall_container(b, (x, y, 3.9), mats[(i + 3) % 6], along="x", doors="+y")
    # The corner towers: three containers' worth of welded plate, hazard bands, a railed deck.
    for k, (x, y) in enumerate(TOWERS):
        sx, sy, sz = TOWER
        container(b, (x, y, sz / 2), TOWER, material=[rust, "olive"][k], doors="-y")
        for z in (2.6, 5.2):
            b.add(block("seam", (x, y, z), (sx + 0.04, sy + 0.04, 0.12), "black", bevel=0))
        for z, m in ((6.9, hazard), (7.25, "black"), (7.6, hazard)):
            b.add(block("towerband", (x, y, z), (sx + 0.05, sy + 0.05, 0.3), m, bevel=0))
        b.add(block("towerdeck", (x, y, sz + 0.06), (sx + 0.6, sy + 0.6, 0.12), "black", bevel=0.01))
        x0, x1, y0, y1 = x - sx / 2 - 0.25, x + sx / 2 + 0.25, y - sy / 2 - 0.25, y + sy / 2 + 0.25
        top = sz + 0.12
        for p0, p1 in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            railing(b, (*p0, top), (*p1, top), spacing=1.4)
    # A lookout's canvas roof on the north-west tower.
    x, y = TOWERS[0]
    for ax in (-1, 1):
        for ay in (-1, 1):
            b.add(cyl("roofpost", (x + ax * 1.3, y + ay * 1.9, TOWER[2] + 0.12), (x + ax * 1.3, y + ay * 1.9, TOWER[2] + 2.3), 0.05, "steel", segs=6, bevel=0))
    b.add(block("lookoutroof", (x, y, TOWER[2] + 2.35), (3.0, 4.2, 0.08), "canvas", bevel=0.01))
    b.add(block("lookoutedge", (x, y, TOWER[2] + 2.25), (3.05, 4.25, 0.12), hazard, bevel=0))
    # Painted words for whoever flies in: SCRAP down the west wall, SCRAPPERS beside the gate.
    b.add(label("SCRAP", (-15.06, -1.8, 3.9), 1.3, hazard, side=-1, depth=0.04))
    c = (-12.0, -13.27, 3.9)
    b.add(turn(label("SCRAPPERS", c, 0.62, hazard, side=-1, depth=0.03), c, 90))
    # Chevrons on the south-east stack's face, hazard on black.
    b.add(block("chevpanel", (12.0, -13.23, 3.9), (5.2, 0.04, 1.6), "black", bevel=0))
    for i in range(5):
        cx = 9.9 + i * 1.05
        for s in (-1, 1):
            c = (cx + s * 0.22, -13.27, 3.9 + s * 0.38)
            b.add(rotate(block("chev", c, (0.3, 0.04, 0.9), hazard, bevel=0), c, "y", -s * 35))
    # Rebar spikes welded along the west wall's lip, against anyone coming up the drift.
    for i, y in enumerate(steps(-10.4, 6.8, 0.9)):
        if -4.8 < y < 1.2:
            continue
        b.add(cyl("spike", (-14.9, y, 2.55), (-15.5, y + 0.15 * (i % 3 - 1), 3.5 + 0.2 * (i % 2)), 0.035, "steel", r1=0.004, segs=5, bevel=0))
    for y0, y1 in ((-10.4, -4.8), (1.2, 6.8)):
        b.add(cyl("spikerail", (-14.95, y0, 2.75), (-14.95, y1, 2.75), 0.04, "black", segs=6, bevel=0))


def gate(b):
    """The gate: two striped posts, a truss gantry with the sign and floods, and the sliding
    leaf parked open behind the container east of the gap."""
    for sx in (-1, 1):
        b.add(block("gatepost", (sx * 3.3, -WALL_Y, 2.75), (0.6, 0.6, 5.5), "black", bevel=0.02))
        for z in (0.8, 2.0, 3.2, 4.4):
            b.add(stripe("gatechev", (sx * 3.3, -WALL_Y, z), (0.6, 0.6, 0.5), hazard))
    truss(b, (-3.6, -WALL_Y, 5.8), (3.6, -WALL_Y, 5.8), s=0.6)
    b.add(block("sign", (0, -WALL_Y, 4.6), (4.6, 0.1, 1.0), "black", bevel=0.01))
    b.add(block("signface", (0, -WALL_Y - 0.06, 4.6), (4.4, 0.03, 0.85), hazard, bevel=0))
    c = (0, -WALL_Y - 0.09, 4.6)
    b.add(turn(label("THE YARD", c, 0.62, "black", side=-1, depth=0.03), c, 90))
    for sx in (-1, 1):
        b.add(cyl("signchain", (sx * 1.8, -WALL_Y, 5.1), (sx * 1.8, -WALL_Y, 5.5), 0.02, "steel", segs=6, bevel=0))
    floodlight(b, "flood.0", (-3.3, -WALL_Y, 5.5), 0.6, aim=(0, -1))
    floodlight(b, "flood.1", (3.3, -WALL_Y, 5.5), 0.6, aim=(0, -1))
    lx = 6.2
    b.add(block("leafrail", (lx, -10.45, 0.04), (6.4, 0.18, 0.08), "black", bevel=0))
    for x in (lx - 3.0, lx, lx + 3.0):
        b.add(block("leafpost", (x, -10.5, 1.4), (0.14, 0.14, 2.8), "gunmetal", bevel=0))
    for z in (0.15, 2.75):
        b.add(block("leafbar", (lx, -10.5, z), (6.1, 0.14, 0.14), "gunmetal", bevel=0))
    for i in range(14):
        x = lx - 2.8 + i * 0.43
        b.add(cyl("leafbar", (x, -10.5, 0.2), (x, -10.5, 2.7), 0.025, "steel", segs=5, bevel=0))
    c = (lx - 1.5, -10.5, 1.45)
    b.add(rotate(block("leafdiag", c, (0.1, 0.1, 3.4), hazard, bevel=0), c, "y", 55))


# -------------------------------------------------------------------------------- the machines

def lattice(col, c, w, h, bay=1.3, material=hazard):
    """A square lattice tower: four chords and zig-zag lacing on every face."""
    x, y, z = c
    corners = [(x - w / 2, y - w / 2), (x + w / 2, y - w / 2), (x + w / 2, y + w / 2), (x - w / 2, y + w / 2)]
    for cx, cy in corners:
        col.add(cyl("chord", (cx, cy, z), (cx, cy, z + h), 0.07, material, segs=6, bevel=0))
    n = int(h / bay)
    for i in range(n):
        z0, z1 = z + i * h / n, z + (i + 1) * h / n
        for k in range(4):
            (ax, ay), (bx, by) = corners[k], corners[(k + 1) % 4]
            if i % 2:
                ax, ay, bx, by = bx, by, ax, ay
            col.add(cyl("lace", (ax, ay, z0), (bx, by, z1), 0.03, material, segs=5, bevel=0))
            col.add(cyl("lace", (ax, ay, z1), (bx, by, z1), 0.03, material, segs=5, bevel=0))


def crane(b):
    """The tower crane over the scrap: a yellow lattice tower on ballast, and on top the part that
    slews once a minute: the cab, the cat head, the jib with its trolley and magnet, the
    counter-jib with its weights."""
    x, y = CRANE
    b.add(block("ballast", (x, y, 0.4), (3.0, 3.0, 0.8), "concrete", bevel=0.03))
    for sx in (-1, 1):
        b.add(stripe("ballaststripe", (x + sx * 1.0, y - 1.5, 0.4), (0.5, 0.02, 0.8), hazard))
    lattice(b, (x, y, 0.8), 1.5, CRANE_H - 0.8)
    b.add(block("towertop", (x, y, CRANE_H - 0.1), (1.7, 1.7, 0.2), "black", bevel=0.01))
    floodlight(b, "flood.2", (x + 0.75, y - 0.75, 8.0), 0.3, aim=(0, -1))
    top = CRANE_H
    col = Collect()
    col.add(cyl("slew", (x, y, top), (x, y, top + 0.35), 0.95, "black", segs=16, bevel=0))
    col.add(block("cab", (x + 0.6, y - 1.25, top + 0.25), (1.4, 1.1, 1.3), hazard, bevel=0.05))
    col.add(block("cabglass", (x + 1.32, y - 1.25, top + 0.4), (0.04, 0.9, 0.7), "glass", bevel=0))
    col.add(block("cabglass", (x + 0.6, y - 1.81, top + 0.4), (1.1, 0.04, 0.7), "glass", bevel=0))
    col.add(block("cabroof", (x + 0.6, y - 1.25, top + 0.95), (1.5, 1.2, 0.08), "black", bevel=0.01))
    jz = top + 0.75
    truss(col, (x + 0.6, y, jz), (x + 12.0, y, jz), s=0.8, bay=1.4, material=hazard)
    truss(col, (x - 0.6, y, jz), (x - 5.0, y, jz), s=0.8, bay=1.4, material=hazard)
    col.add(block("walkway", (x - 2.8, y, jz - 0.42), (4.4, 1.0, 0.06), "black", bevel=0))
    for wx in (x - 4.2, x - 3.0):
        col.add(block("weight", (wx, y, jz - 0.95), (1.1, 1.4, 1.0), "concrete", bevel=0.03))
    col.add(stripe("weightstripe", (x - 3.6, y - 0.71, jz - 0.95), (2.2, 0.02, 0.3), hazard))
    apex = (x, y, top + 4.2)
    for sy in (-1, 1):
        for sx in (-1, 1):
            col.add(cyl("cathead", (x + sx * 0.5, y + sy * 0.45, jz), apex, 0.08, hazard, segs=6, bevel=0))
    col.add(cyl("tie", apex, (x + 8.5, y, jz + 0.4), 0.03, "steel", segs=5, bevel=0))
    col.add(cyl("tie", apex, (x - 4.8, y, jz + 0.4), 0.03, "steel", segs=5, bevel=0))
    col.add(sphere("beacon", (apex[0], apex[1], apex[2] + 0.15), 0.16, "red_light", segs=8))
    col.add(stripe("jibtip", (x + 11.7, y, jz), (0.6, 0.85, 0.85), "black"))
    tx, mz = x + 8.0, jz - 4.8
    col.add(block("trolley", (tx, y, jz - 0.55), (0.9, 0.9, 0.3), "black", bevel=0.01))
    for sy in (-0.12, 0.12):
        col.add(cyl("cable", (tx, y + sy, jz - 0.7), (tx, y + sy, mz + 0.5), 0.018, "steel", segs=4, bevel=0))
    col.add(block("hookblock", (tx, y, mz + 0.6), (0.3, 0.4, 0.4), hazard, bevel=0.02))
    col.add(cyl("magnet", (tx, y, mz), (tx, y, mz + 0.35), 0.75, "black", segs=16, bevel=0.01))
    col.add(cyl("magnetrim", (tx, y, mz + 0.05), (tx, y, mz + 0.3), 0.78, hazard, segs=16, bevel=0))
    col.add(block("hanging", (tx + 0.1, y, mz - 0.25), (1.2, 0.7, 0.3), rust, bevel=0.02))
    spinner(b, 2, (x, y, top), "z", 1, col.parts)
    life_node(b, "blink", 0, (apex[0], apex[1], apex[2] + 0.35))


def hawt(b):
    """The north-east turbine: a guyed pole on the corner tower, a nacelle facing the west wind, a
    tail vane, and three sheet-metal blades on the hub (the rotor turns)."""
    x, y = TOWERS[1]
    z0 = TOWER[2] + 0.12
    hub_z = z0 + 5.4
    b.add(cyl("pole", (x, y, z0), (x, y, hub_z - 0.3), 0.22, "grey", r1=0.14, segs=12, bevel=0))
    for a in (30, 150, 270):
        dx, dy = math.cos(math.radians(a)) * 1.5, math.sin(math.radians(a)) * 1.5
        b.add(cyl("guy", (x + dx, y + dy, z0), (x, y, z0 + 3.6), 0.012, "steel", segs=4, bevel=0))
    b.add(block("nacelle", (x + 0.2, y, hub_z), (1.8, 0.7, 0.7), "white", bevel=0.06))
    b.add(stripe("nacband", (x + 0.2, y, hub_z), (0.35, 0.71, 0.71), hazard))
    b.add(cyl("tailboom", (x + 1.0, y, hub_z), (x + 3.0, y, hub_z + 0.2), 0.06, "steel", segs=6, bevel=0))
    b.add(block("tail", (x + 3.2, y, hub_z + 0.4), (1.2, 0.04, 1.1), hazard, bevel=0.01, taper=(0.6, 1.0)))
    b.add(block("tailstripe", (x + 3.2, y, hub_z + 0.4), (0.3, 0.05, 1.1), "black", bevel=0))
    b.add(sphere("navlight", (x + 0.2, y, hub_z + 0.4), 0.08, "red_light", segs=8), "lights")
    life_node(b, "blink", 1, (x + 0.2, y, hub_z + 0.55))
    hx = x - 0.85
    col = Collect()
    col.add(cyl("hub", (hx + 0.15, y, hub_z), (hx - 0.35, y, hub_z), 0.28, "black", segs=12, bevel=0.01))
    col.add(cyl("spinnercap", (hx - 0.35, y, hub_z), (hx - 0.7, y, hub_z), 0.26, hazard, r1=0.05, segs=12, bevel=0))
    for k in range(3):
        bl = block("blade", (hx - 0.1, y, hub_z + 1.75), (0.05, 0.5, 3.0), ["grey", copper, "grey"][k], bevel=0.005, taper=(1.0, 0.45))
        bs = stripe("bladetip", (hx - 0.1, y, hub_z + 2.95), (0.06, 0.26, 0.4), hazard)
        for o in (bl, bs):
            turn(o, (hx - 0.1, y, hub_z), 18)  # pitch
            rotate(o, (hx, y, hub_z), "x", k * 120)
            col.add(o)
    spinner(b, 0, (hx, y, hub_z), "x", 30, col.parts)


def savonius(b):
    """A drum turbine on the south-east stack: half oil drums offset on a shaft between end
    plates, two tiers crossed, in a frame of angle iron. It turns about the vertical."""
    x, y = 12.0, -WALL_Y
    z0 = 5.2
    for sx in (-1, 1):
        b.add(block("frame", (x + sx * 1.1, y, z0 + 1.7), (0.1, 0.1, 3.4), "black", bevel=0))
    b.add(block("frametop", (x, y, z0 + 3.4), (2.4, 0.12, 0.12), "black", bevel=0))
    b.add(block("framefoot", (x, y, z0 + 0.06), (2.4, 0.5, 0.12), "black", bevel=0))
    col = Collect()
    r, zb, zt = 0.42, z0 + 0.45, z0 + 3.1
    zm = (zb + zt) / 2
    col.add(cyl("shaft", (x, y, z0 + 0.12), (x, y, z0 + 3.34), 0.05, "steel", segs=8, bevel=0))
    for z in (zb - 0.03, zm, zt + 0.03):
        col.add(cyl("endplate", (x, y, z - 0.02), (x, y, z + 0.02), 0.95, "black", segs=16, bevel=0))
    for tier, (za, zz) in enumerate(((zb, zm), (zm, zt))):
        for s in (-1, 1):
            cx, n = x + s * 0.38, 6
            for i in range(n):
                a = math.pi * (i + 0.5) / n + (0 if s > 0 else math.pi)
                px, py = cx + math.cos(a) * r, y + math.sin(a) * r
                chord = 2 * r * math.sin(math.pi / n / 2) + 0.02
                o = block("bucket", (px, py, (za + zz) / 2), (0.04, chord, zz - za - 0.06), [rust, hazard][(tier + (s > 0)) % 2], bevel=0)
                turn(o, (px, py, 0), math.degrees(a))
                if tier:
                    turn(o, (x, y, 0), 90)
                col.add(o)
    spinner(b, 1, (x, y, z0), "z", 40, col.parts)


def smelter(b):
    """The cupola smelter: a banded furnace on a concrete pad, its mouth glowing, a hood and a
    tall guyed stack, a tap trough running to a row of ingot moulds, a pile of charge scrap."""
    x, y = SMELTER
    b.add(block("smelterpad", (x - 0.6, y - 0.4, 0.1), (4.4, 3.8, 0.2), "concrete", bevel=0.02))
    b.add(cyl("furnace", (x, y, 0.2), (x, y, 3.2), 1.2, "black", segs=16, bevel=0.02))
    for z in (0.6, 1.9, 3.0):
        b.add(cyl("band", (x, y, z), (x, y, z + 0.18), 1.24, copper, segs=16, bevel=0))
    for a in range(45, 360, 90):
        dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
        b.add(block("leg", (x + dx * 1.15, y + dy * 1.15, 0.6), (0.2, 0.2, 0.9), rust, bevel=0))
    b.add(cyl("hood", (x, y, 3.2), (x, y, 4.1), 1.25, rust, r1=0.5, segs=16, bevel=0))
    b.add(cyl("stack", (x, y, 4.0), (x, y, 10.0), 0.42, "black", segs=12, bevel=0))
    for z in (5.5, 7.5, 9.6):
        b.add(cyl("stackband", (x, y, z), (x, y, z + 0.2), 0.45, hazard if z > 9 else copper, segs=12, bevel=0))
    b.add(cyl("stackcap", (x, y, 10.25), (x, y, 10.45), 0.75, "black", r1=0.2, segs=12, bevel=0))
    for a in (200, 320, 80):
        dx, dy = math.cos(math.radians(a)) * 4.2, math.sin(math.radians(a)) * 4.2
        b.add(cyl("guy", (x, y, 8.0), (x + dx, y + dy, 0.2), 0.012, "steel", segs=4, bevel=0))
    my = y - 1.22
    b.add(block("mouthframe", (x, my - 0.04, 1.2), (1.2, 0.2, 1.0), rust, bevel=0.02))
    b.add(block("mouth", (x, my - 0.15, 1.2), (0.8, 0.04, 0.62), "molten", bevel=0), "lights")
    b.add(block("mouthdoor", (x - 1.05, my - 0.45, 1.2), (0.06, 0.8, 0.8), rust, bevel=0.01))
    b.add(block("spyhole", (x + 0.6, my + 0.05, 2.5), (0.25, 0.1, 0.2), "molten", bevel=0), "lights")
    b.add(block("trough", (x - 0.9, my - 0.45, 0.62), (1.6, 0.3, 0.12), rust, bevel=0.01))
    b.add(block("pour", (x - 0.9, my - 0.45, 0.69), (1.5, 0.16, 0.03), "molten", bevel=0), "lights")
    for i in range(4):
        mx, mzy = x - 2.0, my - 0.15 - i * 0.55
        b.add(block("mould", (mx, mzy, 0.32), (0.8, 0.45, 0.25), "black", bevel=0.01))
        b.add(block("ingot", (mx, mzy, 0.45), (0.6, 0.3, 0.02), "molten" if i < 2 else copper, bevel=0), "lights" if i < 2 else "hull")
    for i, (dx, dy, s) in enumerate(((1.6, 0.4, 0.5), (1.9, -0.3, 0.35), (1.5, -0.9, 0.4))):
        c = (x + dx, y + dy, 0.2 + s / 2)
        b.add(turn(block("charge", c, (s * 1.6, s, s), [rust, "grey", copper][i], bevel=0.02), c, 25 * i))
    b.add(block("barrow", (x + 1.7, y + 1.7, 0.6), (0.7, 1.0, 0.35), "grey", bevel=0.03, taper=(1.2, 1.2)))
    b.add(tyre("barrowwheel", (x + 1.7, y + 1.1, 0.25), axis=(1, 0, 0), r=0.22, w=0.1))
    life_node(b, "fire", 0, (x, my - 0.6, 1.2))
    life_node(b, "smoke", 0, (x, y, 10.6))
    life_node(b, "sound", 0, (x, my - 0.3, 1.2), sound="fire")


def heap(b):
    """The scrap mountain: a lumpy rust cone heaped into the north-west corner, stuck all over with
    car bodies, plates, girders, drums, tyres, a fighter's wing, an engine bell and a container."""
    x, y, R, H = HEAP
    rng = random.Random(11)
    rings, segs = 9, 20
    bm = bmesh.new()
    top = bm.verts.new((x, y, H * 1.02))
    grid = []
    for i in range(1, rings + 1):
        r = R * i / rings
        row = []
        for k in range(segs):
            a = 2 * math.pi * (k + 0.5 * (i % 2)) / segs
            z = H * (1 - r / R) ** 1.2 * (1 + 0.16 * rng.uniform(-1, 1)) if i < rings else -0.03
            row.append(bm.verts.new((x + math.cos(a) * r, y + math.sin(a) * r, z)))
        grid.append(row)
    for k in range(segs):
        bm.faces.new((top, grid[0][k], grid[0][(k + 1) % segs]))
    for i in range(rings - 1):
        for k in range(segs):
            bm.faces.new((grid[i][k], grid[i + 1][k], grid[i + 1][(k + 1) % segs], grid[i][(k + 1) % segs]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    b.add(wk._obj("heap", bm, rust, 0.0))

    def surface(r):
        return H * max(0.0, 1 - r / R) ** 1.2

    kinds = ["car", "plate", "beam", "drum", "plate", "tyre", "car", "plate", "beam", "drum", "tyre", "plate"]
    for n in range(40):
        kind = kinds[n % len(kinds)]
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.15, 0.85) * R
        px, py = x + math.cos(a) * r, y + math.sin(a) * r
        if px > -2.8 or px < -12.4 or py > 10.6:
            continue  # keep the shed's side clear; the rest would be inside the walls
        pz = surface(r)
        c = (px, py, pz)
        if kind == "car":
            o = block("car", (px, py, pz + 0.2), (1.8, 3.4, 1.0), rng.choice(["olive", "red", "grey", "yellow", copper]), bevel=0.08, taper=(0.85, 0.7))
        elif kind == "plate":
            o = block("plate", (px, py, pz + 0.05), (rng.uniform(1.2, 2.4), rng.uniform(0.9, 1.6), 0.08), rng.choice([rust, copper, brass, "grey", "olive"]), bevel=0.01)
        elif kind == "beam":
            o = block("girder", (px, py, pz + 0.1), (0.3, rng.uniform(3.0, 4.5), 0.35), rng.choice(["black", "gunmetal", hazard]), bevel=0)
        elif kind == "drum":
            o = drum("drum", (px, py, pz - 0.2), r=0.3, h=0.9, material=rng.choice([rust, hazard, "olive", "red"]))
        else:
            o = ring("tyre", c, (0, 0, 1), 0.45, 0.25, 0.3, "black", segs=12)
        rotate(o, c, "x", rng.uniform(-35, 35))
        rotate(o, c, "y", rng.uniform(-35, 35))
        b.add(turn(o, c, rng.uniform(0, 360)))
    c = (x + 0.3, y - 0.4, H - 0.6)
    b.add(rotate(block("wing", (c[0], c[1], c[2] + 1.4), (0.18, 2.2, 3.4), "grey", bevel=0.02, taper=(0.6, 0.35)), c, "y", 18))
    b.add(rotate(stripe("wingstripe", (c[0], c[1], c[2] + 2.3), (0.19, 1.2, 0.35), hazard), c, "y", 18))
    c = (x + 2.2, y - 2.0, surface(3.0) - 0.2)
    b.add(cyl("bell", c, (c[0] + 1.4, c[1] - 0.6, c[2] + 0.8), 0.45, "steel", r1=0.95, segs=14, bevel=0))
    c = (x + 3.6, y - 3.6, 2.0)
    o = container(Collect(), c, (2.4, 6.0, 2.6), material="yellow", band="black")
    rotate(o, c, "x", -28)
    b.add(turn(o, c, 50))


def heap_boxes():
    x, y, R, H = HEAP
    out = []
    for z0, z1 in ((0.0, 2.2), (2.2, 4.4), (4.4, 6.4)):
        r = R * (1 - (z1 / H) ** (1 / 1.2)) * 0.85
        out.append(box("heap", (x, y, (z0 + z1) / 2), (2 * r, 2 * r, z1 - z0)))
    out.append(box("heap container", (x + 3.6, y - 3.6, 1.4), (2.0, 2.0, 2.8)))
    return out


# ------------------------------------------------------------------------------------ the yard

def sail(name, pts, sag, material):
    """A shade sail: a canvas triangle sagging between three corners, with a thickness."""
    a, b_, c = (Vector(p) for p in pts)
    down = Vector((0, 0, sag))
    m = (a + b_ + c) / 3 - down
    ab, bc, ca = (a + b_) / 2 - down * 0.45, (b_ + c) / 2 - down * 0.45, (c + a) / 2 - down * 0.45
    bm = bmesh.new()
    va, vb, vc, vab, vbc, vca, vm = (bm.verts.new(p) for p in (a, b_, c, ab, bc, ca, m))
    for tri in ((va, vab, vm), (vab, vb, vm), (vb, vbc, vm), (vbc, vc, vm), (vc, vca, vm), (vca, va, vm)):
        n = (tri[1].co - tri[0].co).cross(tri[2].co - tri[0].co)
        bm.faces.new(tri if n.z > 0 else tri[::-1])
    ret = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
    moved = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, -0.04), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return wk._obj(name, bm, material, 0.0)


def shade(b, pts, poles, material, sag=0.35):
    """A sail on its corners; a corner with a pole foot (x, y, z) gets a steel pole and a guy."""
    b.add(sail("sail", pts, sag, material))
    cen = Vector((sum(p[0] for p in pts) / 3, sum(p[1] for p in pts) / 3, 0))
    for p, foot in zip(pts, poles):
        if foot is None:
            b.add(block("sailplate", p, (0.2, 0.2, 0.2), "black", bevel=0))
            continue
        b.add(cyl("sailpole", foot, (p[0], p[1], p[2] + 0.25), 0.07, "steel", segs=8, bevel=0))
        b.add(sphere("sailcap", (p[0], p[1], p[2] + 0.28), 0.1, hazard, segs=8))
        d = (Vector((p[0], p[1], 0)) - cen).normalized() * 1.6
        b.add(cyl("guy", (p[0], p[1], p[2] + 0.2), (p[0] + d.x, p[1] + d.y, foot[2]), 0.012, "steel", segs=4, bevel=0))


def festoon(b, p0, p1, sag, bulbs):
    """A string of bulbs on a sagging wire from p0 to p1."""
    a, z = Vector(p0), Vector(p1)
    pts = [a.lerp(z, i / bulbs) - Vector((0, 0, sag * 4 * (i / bulbs) * (1 - i / bulbs))) for i in range(bulbs + 1)]
    for q0, q1 in zip(pts, pts[1:]):
        b.add(cyl("wire", q0, q1, 0.012, "black", segs=4, bevel=0))
    for q in pts[1:-1]:
        b.add(sphere("bulb", q - Vector((0, 0, 0.1)), 0.07, "lamp", segs=6), "lights")


def drum(name, c, r=0.3, h=0.9, material=rust):
    """An oil drum with sharp edges: a body, two rolled hoops, a bung (the interior kit's barrel
    bevels every edge, dear at the dozens in the yard)."""
    x, y, z = c
    parts = [cyl(name, (x, y, z), (x, y, z + h), r, material, segs=14, bevel=0),
             cyl("bung", (x + r * 0.5, y, z + h), (x + r * 0.5, y, z + h + 0.02), 0.04, "steel", segs=6, bevel=0)]
    for k in (0.28, 0.72):
        parts.append(ring("hoop", (x, y, z + h * k), (0, 0, 1), r + 0.02, r - 0.01, 0.05, "steel", segs=14))
    return wk.join(parts, name)


def tyre0(name, c):
    """A flat tyre with sharp edges, for the stacks."""
    return wk.join([ring(name, c, (0, 0, 1), 0.42, 0.23, 0.28, "black", segs=14), ring("hubring", c, (0, 0, 1), 0.23, 0.12, 0.17, "steel", segs=8)], name)


def yard(b):
    """Inside the walls, but the shed: the hangout, the genset, the quarters, the sails, clutter."""
    bx, by = -8.6, -7.4
    b.add(drum("burnbarrel", (bx, by, 0), r=0.32, h=0.95, material=rust))
    b.add(cyl("coals", (bx, by, 0.93), (bx, by, 0.97), 0.28, "molten", segs=10, bevel=0), "lights")
    for dx, dy, h in ((0.0, 0.0, 0.5), (0.12, 0.1, 0.35), (-0.1, -0.08, 0.28)):
        b.add(cyl("flame", (bx + dx, by + dy, 0.95), (bx + dx, by + dy, 0.95 + h), 0.09, "lights_amber", r1=0.0, segs=6, bevel=0), "lights")
    for i in range(6):
        a = math.radians(i * 60 + 15)
        b.add(block("vent", (bx + math.cos(a) * 0.31, by + math.sin(a) * 0.31, 0.45), (0.05, 0.05, 0.12), "molten", bevel=0), "lights")
    b.add(block("plank", (bx, by + 1.4, 0.42), (2.4, 0.35, 0.06), "tan", bevel=0.01))
    for dx in (-1.0, 1.0):
        b.add(block("plankleg", (bx + dx, by + 1.4, 0.2), (0.1, 0.3, 0.4), "black", bevel=0))
    b.add(crate("seat", (bx - 1.5, by - 0.4, 0.3), (0.6, 0.6, 0.6), material="olive"))
    b.add(crate("seat", (bx + 1.4, by - 0.6, 0.3), (0.6, 0.6, 0.6), material=leather))
    b.add(block("tabletop", (bx + 2.6, by + 0.4, 0.75), (1.1, 1.1, 0.06), "grey", bevel=0.01))
    b.add(drum("tabledrum", (bx + 2.6, by + 0.4, 0), r=0.3, h=0.72, material="olive"))
    life_node(b, "fire", 1, (bx, by, 1.3))
    life_node(b, "smoke", 1, (bx, by, 1.8))
    shade(b, [(-12.4, -10.6, 4.5), (-4.2, -10.0, 3.7), (-10.2, -3.0, 4.0)], [None, (-4.2, -10.0, 0.0), (-10.2, -3.0, 0.0)], hazard)
    gx, gy = GENSET
    b.add(block("genset", (gx, gy, 0.7), (1.4, 2.2, 1.4), "olive", bevel=0.04))
    b.add(stripe("gensetband", (gx, gy, 1.2), (1.4, 2.2, 0.2), hazard))
    for i in range(5):
        b.add(block("grille", (gx + 0.71, gy - 0.8 + i * 0.2, 0.75), (0.03, 0.1, 0.8), "black", bevel=0))
    b.add(cyl("exhaust", (gx - 0.3, gy + 0.8, 1.4), (gx - 0.3, gy + 0.8, 3.1), 0.08, "black", segs=8, bevel=0))
    b.add(cable_bundle("gencable", [(gx + 0.7, gy + 1.1, 0.2), (gx + 3.0, gy + 2.5, 0.05), (-1.9, 2.5, 0.05)], material="black"))
    life_node(b, "sound", 0, (gx, gy, 1.0), sound="generator")
    life_node(b, "sound", 0, (-15.0, -1.8, 5.6), sound="wind")
    life_node(b, "sound", 1, (WALL_X, 9.0, 11.0), sound="wind")
    (qx, qy, qz), qs = QUARTERS
    hall(b, "quarters", (qx, qy, qz), qs, "olive", wall=0.1, openings=[("-x", 0.0, 0.9, 2.0, 0), ("-y", 1.0, 1.2, 0.6, 1.3)], bevel=0.02)
    b.add(block("quartersband", (qx, qy, 0.6), (qs[0] + 0.04, qs[1] + 0.04, 0.25), hazard, bevel=0))
    for i in range(10):
        if abs(qx - 2.7 + i * 0.6 - (qx + 1.0)) < 0.7:
            continue
        b.add(block("rib", (qx - 2.7 + i * 0.6, qy - 1.31, 1.3), (0.2, 0.03, 2.3), "olive", bevel=0))
    for xx in (qx + 0.8, qx + 2.2):
        for z in (0.5, 1.4):
            c = (xx, qy + 0.8, 0.1 + z)
            b.add(turn(bunk("bunk", c, (0.85, 1.7, 0.14), material="olive", wall=1), c, 90))
    b.add(crate("qcrate", (qx - 1.6, qy + 0.7, 0.45), (0.8, 0.7, 0.7), material="olive"))
    lamp(b, "lamp.3", (qx, qy, 2.48), rim="black", r=0.14, cage=True)
    b.add(block("qawning", (qx - 3.3, qy, 2.35), (0.7, 1.6, 0.05), hazard, bevel=0))
    shade(b, [(0.2, 1.0, 5.0), (8.8, 1.0, 5.0), (4.5, -4.8, 3.6)], [None, None, (4.5, -4.8, 0.0)], "canvas", sag=0.45)
    for x, y, n in ((-3.0, -9.6, 4), (-2.3, -9.9, 3), (2.6, -9.8, 5)):
        for i in range(n):
            b.add(tyre0("tyre", (x, y, 0.14 + 0.28 * i)))
    for i, (x, y) in enumerate(((11.6, -4.2), (12.0, -3.6), (11.5, -3.2), (12.1, -2.8))):
        b.add(drum("drum", (x, y, 0), r=0.3, h=0.9, material=[rust, hazard, "olive", copper][i % 4]))
    for i, x in enumerate((5.9, 6.2, 6.5)):
        b.add(gas_bottle("gas", (x, -10.4, 0), material=["olive", "red", "olive"][i]))
    b.add(crate("crate", (1.0, -9.9, 0.5), (1.2, 1.0, 1.0), material="olive", band=hazard))
    b.add(crate("crate", (1.0, -9.9, 1.35), (1.0, 0.8, 0.7), material=leather))
    festoon(b, (CRANE[0] + 0.75, CRANE[1] + 0.75, 6.0), (-1.9, 2.0, 5.3), 0.6, 8)
    festoon(b, (CRANE[0] - 0.75, CRANE[1] - 0.75, 6.0), (-10.2, -3.0, 4.1), 0.5, 7)
    festoon(b, (-4.2, -10.0, 3.8), (-3.3, -11.7, 5.2), 0.2, 3)


# ------------------------------------------------------------------------------------ the shed

def shed(b):
    """The workshop: a corrugated shed open at the front. Inside, a buggy frame on stands under
    the hoist (weld point one), a welding table with a plate clamped on it (weld point two), the
    bench grinder, the tool wall, cabinets, the gun rack, caged lamps and the crew's cog painted
    on the back wall."""
    (x, y, z), s = SHED
    x0, x1, y0, y1 = x - s[0] / 2, x + s[0] / 2, y - s[1] / 2, y + s[1] / 2
    hall(b, "shed", (x, y, z), s, rust, wall=0.25, openings=[("-y", 0, 8.0, 4.5, 0)], bevel=0.04)
    seams(b, (x, y, z), s, ys=(-3.0, 0.0, 3.0), xs=(-4.5, -1.5, 1.5, 4.5), material="black", width=0.05, proud=0.015)
    for i in range(int(s[1] / 0.6)):
        for xx in (x0 - 0.02, x1 + 0.02):
            b.add(block("rib", (xx, y0 + 0.3 + i * 0.6, 2.75), (0.04, 0.22, 5.0), rust, bevel=0))
    for i in range(6):
        b.add(block("roofrib", (x0 + 1.0 + i * 2.2, y, 5.52), (0.12, s[1], 0.08), "black", bevel=0))
    b.add(stripe("shedstripe", (x, y0, 5.05), (s[0], 0.05, 0.5), hazard))
    b.add(block("lintelpanel", (x, y0 - 0.03, 5.05), (7.6, 0.04, 0.45), "black", bevel=0))
    c = (x, y0 - 0.07, 5.05)
    b.add(turn(label("WORKSHOP", c, 0.36, hazard, side=-1, depth=0.02), c, 90))
    b.add(cyl("stovepipe", (x1 - 1.5, y1 - 1.0, 5.5), (x1 - 1.5, y1 - 1.0, 7.4), 0.14, "black", segs=10, bevel=0))
    b.add(cyl("stovecap", (x1 - 1.5, y1 - 1.0, 7.4), (x1 - 1.5, y1 - 1.0, 7.6), 0.3, "black", r1=0.06, segs=10, bevel=0))
    for xx in (x - 4.0, x, x + 4.0):
        b.add(cyl("roofvent", (xx, y + 1.5, 5.5), (xx, y + 1.5, 6.1), 0.18, "black", segs=8, bevel=0))
        b.add(cyl("roofventcap", (xx, y + 1.5, 6.1), (xx, y + 1.5, 6.3), 0.32, "black", r1=0.05, segs=8, bevel=0))
    for i, (yy, zz, w, h) in enumerate(((4.0, 2.2, 1.4, 0.9), (7.5, 3.4, 0.9, 1.1), (9.0, 1.6, 1.0, 0.7))):
        b.add(block("patch", (x0 - 0.04, yy, zz), (0.04, w, h), [brass, copper, "grey"][i], bevel=0.01))
        b.add(rivets("patchrivets", (x0 - 0.07, yy - w / 2 + 0.1, zz + h / 2 - 0.08), (x0 - 0.07, yy + w / 2 - 0.1, zz + h / 2 - 0.08), 5, axis="-x"))
    # The buggy frame on stands in the middle, its wheels off and leaning by the front stands.
    bx, by = x, y + 0.8
    bz = F + 0.75
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.add(block("stand", (bx + sx * 0.7, by + sy * 1.1, F + 0.35), (0.3, 0.3, 0.7), hazard, bevel=0.01))
        b.add(cyl("rail", (bx + sx * 0.75, by - 1.7, bz), (bx + sx * 0.75, by + 1.6, bz), 0.05, "gunmetal", segs=8, bevel=0))
        b.add(cyl("cage", (bx + sx * 0.75, by - 0.3, bz), (bx + sx * 0.55, by - 0.1, bz + 1.15), 0.045, "gunmetal", segs=8, bevel=0))
        b.add(cyl("cage", (bx + sx * 0.75, by + 0.9, bz), (bx + sx * 0.55, by + 0.3, bz + 1.15), 0.045, "gunmetal", segs=8, bevel=0))
        b.add(cyl("cage", (bx + sx * 0.75, by - 1.7, bz), (bx + sx * 0.6, by - 1.2, bz + 0.6), 0.04, "gunmetal", segs=8, bevel=0))
        c = (bx + sx * 1.4, by - 2.0, F + 0.16)
        b.add(wk.join([ring("wheel", c, (0, 0, 1), 0.5, 0.28, 0.32, "black", segs=16), ring("rim", c, (0, 0, 1), 0.28, 0.12, 0.2, "steel", segs=10)], "wheel"))
    for yy in (by - 1.7, by - 0.3, by + 0.9, by + 1.6):
        b.add(cyl("cross", (bx - 0.75, yy, bz), (bx + 0.75, yy, bz), 0.045, "gunmetal", segs=8, bevel=0))
    for yy in (by - 0.1, by + 0.3):
        b.add(cyl("hoop", (bx - 0.55, yy, bz + 1.15), (bx + 0.55, yy, bz + 1.15), 0.045, "gunmetal", segs=8, bevel=0))
    b.add(block("engine", (bx, by + 1.25, bz + 0.3), (0.7, 0.6, 0.5), "black", bevel=0.03))
    b.add(block("seatpan", (bx, by + 0.1, bz + 0.1), (0.5, 0.5, 0.1), "olive", bevel=0.02))
    life_node(b, "weld", 0, (bx + 0.72, by + 0.45, bz + 0.6))
    hoist(b, (bx, by, 5.2), 7.0, 2.4)
    # The welding table at the back-east, a plate clamped on it, bottles on a cart beside.
    wx, wy = x1 - 2.0, y1 - 1.6
    b.add(block("weldtop", (wx, wy, F + 0.85), (1.2, 2.0, 0.08), "steel", bevel=0.005))
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.add(block("weldleg", (wx + sx * 0.5, wy + sy * 0.9, F + 0.42), (0.08, 0.08, 0.84), "black", bevel=0))
    b.add(block("weldplate", (wx, wy - 0.2, F + 0.92), (0.9, 1.1, 0.04), copper, bevel=0.005))
    b.add(block("weldbracket", (wx - 0.1, wy + 0.2, F + 1.1), (0.08, 0.6, 0.35), "steel", bevel=0.005))
    b.add(block("weldscreen", (wx - 0.9, wy, F + 1.0), (0.04, 1.6, 1.6), "olive", bevel=0.005))
    life_node(b, "weld", 1, (wx - 0.05, wy, F + 1.05))
    for dy, m in ((0.0, "olive"), (0.32, "red")):
        b.add(gas_bottle("weldgas", (wx + 0.85, wy - 1.2 + dy, F), material=m))
    b.add(block("weldcart", (wx + 0.85, wy - 1.05, F + 0.1), (0.4, 0.8, 0.12), "black", bevel=0))
    b.add(cable_bundle("weldlead", [(wx + 0.85, wy - 1.1, F + 1.2), (wx + 0.4, wy - 0.6, F + 0.95), (wx, wy - 0.2, F + 0.98)], n=2, material="black"))
    # The bench grinder on its pedestal in the front-east corner, a bin of offcuts.
    gx, gy = x1 - 0.9, y0 + 1.6
    b.add(cyl("pedestal", (gx, gy, F), (gx, gy, F + 0.9), 0.08, "gunmetal", segs=8, bevel=0))
    b.add(block("pedfoot", (gx, gy, F + 0.03), (0.5, 0.5, 0.06), "black", bevel=0))
    b.add(cyl("motor", (gx, gy - 0.15, F + 1.02), (gx, gy + 0.15, F + 1.02), 0.12, hazard, segs=12, bevel=0.01))
    for sy in (-1, 1):
        b.add(cyl("stone", (gx, gy + sy * 0.2, F + 1.02), (gx, gy + sy * 0.28, F + 1.02), 0.15, "grey", segs=14, bevel=0))
        b.add(block("guard", (gx, gy + sy * 0.24, F + 1.12), (0.34, 0.12, 0.2), "black", bevel=0.01))
    b.add(drum("offcuts", (gx - 0.1, gy + 1.0, F), r=0.28, h=0.6, material="grey"))
    life_node(b, "sound", 0, (gx, gy, F + 1.0), sound="grinder")
    # The west wall: a workbench, the tool board, the cabinets; the gun rack on the back.
    b.add(workbench("bench", (x0 + 0.85, y + 0.8, F), (1.0, 3.0, 0.9), top="steel", frame=rust))
    b.add(block("pegboard", (x0 + 0.29, y + 0.8, 1.9), (0.05, 2.6, 1.1), "black", bevel=0))
    b.add(cyl("sawblade", (x0 + 0.33, y - 0.2, 2.0), (x0 + 0.35, y - 0.2, 2.0), 0.28, "steel", segs=18, bevel=0))
    for i in range(7):
        b.add(block("tool", (x0 + 0.33, y + 0.3 + 0.3 * i, 1.85 + 0.12 * (i % 2)), (0.03, 0.05, 0.4), "steel" if i % 2 else copper, bevel=0))
    for i, yy in enumerate((y - 3.0, y - 2.1)):
        c = (x0 + 0.55, yy, F + 0.95)
        b.add(turn(cabinet("cabinet", c, (0.8, 0.5, 1.9), material=["grey", rust][i], doors=2), c, -90))
    b.add(gun_rack("rack", (x - 3.0, y1 - 0.3, F), facing=-1, n=5, material=rust))
    b.add(crate("shedcrate", (x - 0.8, y1 - 0.8, F + 0.5), (1.4, 1.0, 1.0), material="olive"))
    b.add(crate("shedcrate", (x - 0.8, y1 - 0.8, F + 1.35), (1.0, 0.8, 0.7), material=brass))
    b.add(extinguisher("ext", (x1 - 0.35, y0 + 0.7, 0.55), wall=1))
    b.add(turn(wheel("wheelwall", (x1 - 0.3, y, 1.8), facing=-1, r=0.3), (x1 - 0.3, y, 1.8), 90))
    # The cog on the back wall: a yellow ring with teeth round a hub, and the crew's name under it.
    cx, cy, cz = x + 2.2, y1 - 0.27, 3.2
    b.add(ring("cog", (cx, cy, cz), (0, 1, 0), 0.9, 0.5, 0.04, hazard, segs=20))
    for k in range(10):
        a = 2 * math.pi * k / 10
        b.add(block("tooth", (cx + math.cos(a) * 1.0, cy, cz + math.sin(a) * 1.0), (0.26, 0.04, 0.26), hazard, bevel=0))
    b.add(cyl("hub", (cx, cy, cz), (cx, cy - 0.03, cz), 0.22, hazard, segs=12, bevel=0))
    c = (cx, cy - 0.02, cz - 1.6)
    b.add(turn(label("SCRAPPERS", c, 0.34, hazard, side=-1, depth=0.02), c, 90))
    grating(b, (bx, by, F + 0.01), (4.0, 5.4), material="gunmetal", pitch=0.25)
    b.add(cable_bundle("cables", [(x0 + 0.4, y0 + 0.9, 5.0), (x - 2.0, y0 + 0.9, 4.8), (x + 1.0, y0 + 0.9, 5.0), (x1 - 0.4, y0 + 0.9, 4.85)], material="black"))
    pipe_run(b, [(x1 - 0.3, y1 - 1.0, 4.8), (x1 - 0.3, y0 + 1.0, 4.8), (x1 - 0.3, y0 + 1.0, 1.5)], r=0.05, material=copper, brackets=1.2)
    for i, (lx, ly) in enumerate(((x - 3.5, y - 1.5), (x + 3.5, y - 1.5), (x, y + 2.8))):
        lamp(b, f"lamp.{i}", (lx, ly, 5.24), rim="black", r=0.2, cage=True)


def shed_boxes():
    (x, y, z), s = SHED
    x0, x1, y0, y1 = x - s[0] / 2, x + s[0] / 2, y - s[1] / 2, y + s[1] / 2
    t = 0.25
    return [
        box("shed floor", (x, y, t / 2), (s[0], s[1], t)),
        box("shed roof", (x, y, s[2] - t / 2), (s[0], s[1], t)),
        box("shed west", (x0 + t / 2, y, s[2] / 2), (t, s[1], s[2])),
        box("shed east", (x1 - t / 2, y, s[2] / 2), (t, s[1], s[2])),
        box("shed back", (x, y1 - t / 2, s[2] / 2), (s[0], t, s[2])),
        box("shed front", ((x0 + x - 4.0) / 2, y0 + t / 2, s[2] / 2), (x - 4.0 - x0, t, s[2])),
        box("shed front", ((x1 + x + 4.0) / 2, y0 + t / 2, s[2] / 2), (x1 - x - 4.0, t, s[2])),
        box("shed lintel", (x, y0 + t / 2, (t + 4.5 + s[2]) / 2), (8.0, t, s[2] - t - 4.5)),
        box("buggy", (x, y + 0.8, 0.9), (1.8, 3.6, 1.3)),
        box("weld table", (x1 - 2.0, y1 - 1.6, 0.7), (1.2, 2.0, 0.9)),
        box("bench", (x0 + 0.85, y + 0.8, 0.7), (1.0, 3.0, 0.9)),
        box("crate", (x - 0.8, y1 - 0.8, 0.75), (1.4, 1.0, 1.0)),
    ]


def quarters_boxes():
    (x, y, z), s = QUARTERS
    t = 0.1
    x0, x1 = x - s[0] / 2, x + s[0] / 2
    return [
        box("quarters floor", (x, y, t / 2), (s[0], s[1], t)),
        box("quarters roof", (x, y, s[2] - t / 2), (s[0], s[1], t)),
        box("quarters wall", (x, y - s[1] / 2 + t / 2, s[2] / 2), (s[0], t, s[2])),
        box("quarters wall", (x, y + s[1] / 2 - t / 2, s[2] / 2), (s[0], t, s[2])),
        box("quarters end", (x1 - t / 2, y, s[2] / 2), (t, s[1], s[2])),
        box("quarters end", (x0 + t / 2, y - 0.95, s[2] / 2), (t, 0.7, s[2])),
        box("quarters end", (x0 + t / 2, y + 0.95, s[2] / 2), (t, 0.7, s[2])),
        box("quarters lintel", (x0 + t / 2, y, (t + 2.0 + s[2]) / 2), (t, 0.9, s[2] - t - 2.0)),
    ]


# ----------------------------------------------------------------------------------- the garage

def garage(b):
    """The tuning garage outside the east wall, its north and east sides drifted in. The engine on
    its stand under a hoist rail; the Tuning rig console on the north side with its mechanic
    behind it and the diagnostics board over him; the Parts rack counter on the east side, the
    rack of hull plates, shield cells, gun barrels and missile pods behind it."""
    (x, y), s = GARAGE
    z0 = F
    x0, x1, y0, y1 = x - s[0] / 2, x + s[0] / 2, y - s[1] / 2, y + s[1] / 2
    room(b, "garage", (x, y), s, rust, GARAGE_DOORS, wall=0.25, trim="black")
    for i in range(int(s[0] / 0.6)):
        xx = x0 + 0.3 + i * 0.6
        if abs(xx - x) > 1.7:
            b.add(block("rib", (xx, y0 - 0.02, s[2] / 2), (0.22, 0.04, s[2] - 0.4), rust, bevel=0))
    for sx in (-1, 1):
        b.add(stripe("doorchev", (x + sx * 1.75, y0 - 0.05, 1.5), (0.35, 0.04, 3.0), hazard))
    b.add(block("signboard", (x, y0 - 0.06, 3.35), (3.6, 0.05, 0.5), "black", bevel=0))
    c = (x, y0 - 0.1, 3.35)
    b.add(turn(label("TUNING", c, 0.42, hazard, side=-1, depth=0.02), c, 90))
    b.add(cyl("vent", (x + 2.5, y + 1.5, s[2] + 0.1), (x + 2.5, y + 1.5, s[2] + 1.0), 0.18, "black", segs=10, bevel=0))
    b.add(cyl("ventcap", (x + 2.5, y + 1.5, s[2] + 1.0), (x + 2.5, y + 1.5, s[2] + 1.1), 0.3, "black", segs=10, bevel=0))
    for i, gx in enumerate((x - 3.0, x + 3.0)):
        b.add(gas_bottle("gas", (gx, y0 - 0.45, 0), material="olive" if i else "red"))
    floodlight(b, "flood.3", (x - 2.4, y0 - 0.2, s[2] + 0.1), 0.4, aim=(0, -1))
    shade(b, [(x0 + 0.3, y0 - 0.1, s[2] - 0.2), (x1 - 0.3, y0 - 0.1, s[2] - 0.2), (x + 2.6, y0 - 4.0, 3.0)], [None, None, (x + 2.6, y0 - 4.0, 0.0)], hazard, sag=0.3)
    # The engine: a drum body, a flared bell and bands, in a cradle on a low stand.
    ex, ey = x0 + 1.7, y - 0.4
    b.add(block("stand", (ex, ey, z0 + 0.25), (1.5, 2.6, 0.5), "black", bevel=0.02))
    for dy in (-0.8, 0.6):
        b.add(block("cradle", (ex, ey + dy, z0 + 0.7), (1.1, 0.12, 0.5), "gunmetal", bevel=0.01))
    b.add(cyl("engine", (ex, ey - 1.2, z0 + 1.05), (ex, ey + 1.0, z0 + 1.05), 0.5, "gunmetal", segs=16, bevel=0.01))
    b.add(cyl("bell", (ex, ey + 1.0, z0 + 1.05), (ex, ey + 1.9, z0 + 1.05), 0.34, "steel", r1=0.62, segs=16, bevel=0.01))
    for dy in (-0.8, -0.1, 0.6):
        b.add(cyl("enginering", (ex, ey + dy, z0 + 1.05), (ex, ey + dy + 0.12, z0 + 1.05), 0.54, copper, segs=16, bevel=0))
    b.add(cyl("feed", (ex, ey - 1.2, z0 + 1.05), (ex, ey - 1.6, z0 + 1.05), 0.25, brass, segs=12, bevel=0))
    hoist(b, (ex, ey, s[2] - 0.5), 4.4, 0.9)
    # The Tuning rig: a console facing the room, the board on the wall behind, leads to the engine.
    rx, ry = RIG
    b.add(block("rigdesk", (rx, ry, z0 + 0.4), (2.6, 0.7, 0.8), "gunmetal", bevel=0.02))
    b.add(block("rigtop", (rx, ry - 0.02, z0 + 0.82), (2.7, 0.76, 0.05), "black", bevel=0.005))
    b.add(stripe("rigstripe", (rx, ry - 0.36, z0 + 0.6), (2.6, 0.02, 0.12), hazard))
    pc = Vector((rx, ry + 0.15, z0 + 1.2))
    nrm = Vector((0, -math.cos(math.radians(20)), math.sin(math.radians(20))))
    b.add(block("rigbank", tuple(pc), (2.5, 0.12, 0.62), "gunmetal", bevel=0.01, rot=-20))
    for i in range(3):
        sc = pc + nrm * 0.065 + Vector((-0.82 + i * 0.82, 0, 0))
        b.add(block("rigscreen", tuple(sc), (0.7, 0.01, 0.44), "lights_amber" if i != 1 else "screen", bevel=0, rot=-20), "lights")
    for i in range(9):
        on = i % 3 == 0
        b.add(block("rigkey", (rx - 0.8 + i * 0.2, ry - 0.2, z0 + 0.86), (0.12, 0.1, 0.03), "lights_amber" if on else "black", bevel=0), "lights" if on else "hull")
    b.add(block("board", (rx, y1 - 0.29, 2.4), (2.8, 0.05, 1.2), "black", bevel=0.01))
    for i in range(3):
        b.add(block("boardscreen", (rx - 0.9 + i * 0.9, y1 - 0.32, 2.45), (0.75, 0.02, 0.8), "screen" if i != 1 else "lights_amber", bevel=0), "lights")
    b.add(stripe("boardstripe", (rx, y1 - 0.3, 3.1), (2.8, 0.05, 0.12), hazard))
    b.add(cable_bundle("leads", [(rx - 1.3, ry, z0 + 0.6), (ex + 1.2, ey + 0.3, z0 + 0.05), (ex + 0.5, ey, z0 + 1.0)], n=3, material="black"))
    # The Parts rack: a counter on the east side, a rack of parts on the wall behind it.
    kx, ky = RACK
    b.add(block("counter", (kx, ky, z0 + 0.5), (0.7, 2.4, 1.0), rust, bevel=0.02))
    b.add(block("countertop", (kx, ky, z0 + 1.03), (0.8, 2.5, 0.06), "steel", bevel=0.01))
    b.add(stripe("counterstripe", (kx - 0.35, ky, z0 + 0.85), (0.02, 2.4, 0.15), hazard))
    b.add(crate("part", (kx, ky - 0.6, z0 + 1.25), (0.5, 0.6, 0.35), material="olive", band=hazard))
    b.add(cyl("partnozzle", (kx, ky + 0.6, z0 + 1.06), (kx, ky + 0.6, z0 + 1.5), 0.12, "steel", r1=0.24, segs=12, bevel=0))
    rx_ = x1 - 0.38
    for z in (0.9, 1.7, 2.5):
        b.add(block("shelf", (rx_, ky, z), (0.3, 3.0, 0.05), "black", bevel=0))
    for sy in (-1.5, 0.0, 1.5):
        b.add(block("upright", (rx_, ky + sy, 1.6), (0.3, 0.06, 2.8), "black", bevel=0))
    for i in range(4):
        b.add(cyl("gunbarrel", (rx_, ky - 1.3 + i * 0.22, 0.95), (rx_, ky - 1.3 + i * 0.22 + 0.04, 1.65), 0.035, "gunmetal", segs=6, bevel=0))
    for i in range(3):
        b.add(block("hullplate", (rx_ + 0.05, ky + 0.3 + i * 0.35, 1.3), (0.06, 0.3, 0.7), [copper, "grey", hazard][i], bevel=0.01))
    for i in range(3):
        b.add(cyl("cell", (rx_, ky - 1.0 + i * 0.5, 1.75), (rx_, ky - 1.0 + i * 0.5, 2.15), 0.13, "blue_light" if i % 2 else "screen", segs=10, bevel=0), "lights")
    for i in range(2):
        b.add(block("pod", (rx_, ky + 0.6 + i * 0.7, 2.75), (0.28, 0.55, 0.4), "olive", bevel=0.03))
        for k in range(3):
            yy = ky + 0.45 + i * 0.7 + k * 0.15
            b.add(cyl("tube", (rx_ - 0.15, yy, 2.75), (rx_ - 0.17, yy, 2.75), 0.05, "black", segs=8, bevel=0))
    for i in range(2):
        b.add(tyre("tyre", (x0 + 0.7, y0 + 0.8, z0 + 0.15 + i * 0.3), axis=(0, 0, 1), r=0.42, w=0.28))
    b.add(drum("drum", (x1 - 0.6, y0 + 0.6, z0), r=0.3, h=0.9, material=hazard))
    lamp(b, "lamp.4", (x, y, s[2] - 0.27), rim="black", r=0.2, cage=True)


# --------------------------------------------------------------------------------------- build

def build():
    b = Base("yard")
    ground(b)
    dunes(b)
    walls(b)
    gate(b)
    heap(b)
    crane(b)
    hawt(b)
    savonius(b)
    smelter(b)
    yard(b)
    shed(b)
    garage(b)
    return b


def _containers():
    out = []
    for side, sx in (("w", -1), ("e", 1)):
        for i, y in enumerate(SIDE_YS):
            out.append(box("container", (sx * WALL_X, y, 1.3), C))
            if i in STACK[side]:
                out.append(box("container", (sx * WALL_X, y, 3.9), C))
    for side, y, xs in (("n", WALL_Y, BACK_XS), ("s", -WALL_Y, FRONT_XS)):
        for i, x in enumerate(xs):
            out.append(box("container", (x, y, 1.3), (C[1], C[0], C[2])))
            if i in STACK[side]:
                out.append(box("container", (x, y, 3.9), (C[1], C[0], C[2])))
    for x, y in TOWERS:
        out.append(box("tower", (x, y, TOWER[2] / 2), TOWER))
        out.append(box("tower deck", (x, y, TOWER[2] + 0.06), (TOWER[0] + 0.6, TOWER[1] + 0.6, 0.12)))
    return out


SPEC = {
    "build": build,
    "name": "The Yard",
    "color": (1.0, 0.85, 0.1),
    "faction": "scrappers",
    "body": "cinder",
    "lat": -8.0,
    "lon": 120.0,
    "footprint": (55.0, 36.0),
    "footprint_at": (2.25, 1.0),
    "pad": (0.0, -30.0),
    "door": (0.0, -12.0, 1.2),
    "traffic": "mule",
    "size": (41.0, 60.0, 18.1),
    "depth": 0.6,
    "nodes": [f"lamp.{i}" for i in range(5)] + [f"flood.{i}" for i in range(4)] + [
        "spin.x.30.0", "spin.y.40.1", "spin.y.1.2", "blink.0", "blink.1", "fire.0", "fire.1", "smoke.0", "smoke.1", "weld.0", "weld.1",
        "sound.fire.0", "sound.grinder.0", "sound.generator.0", "sound.wind.0", "sound.wind.1"],
    "boxes": [
        *_containers(),
        box("gatepost", (-3.3, -WALL_Y, 2.75), (0.6, 0.6, 5.5)),
        box("gatepost", (3.3, -WALL_Y, 2.75), (0.6, 0.6, 5.5)),
        *shed_boxes(),
        *quarters_boxes(),
        box("smelter pad", (SMELTER[0] - 0.6, SMELTER[1] - 0.4, 0.1), (4.4, 3.8, 0.2)),
        box("smelter", (SMELTER[0], SMELTER[1], 1.8), (2.6, 2.6, 3.6)),
        box("crane ballast", (CRANE[0], CRANE[1], 0.4), (3.0, 3.0, 0.8)),
        box("crane tower", (CRANE[0], CRANE[1], CRANE_H / 2), (1.5, 1.5, CRANE_H)),
        *heap_boxes(),
        box("genset", (GENSET[0], GENSET[1], 0.7), (1.4, 2.2, 1.4)),
        *room_boxes("garage", GARAGE[0], GARAGE[1], GARAGE_DOORS, wall=0.25),
        box("engine stand", (GARAGE[0][0] - GARAGE[1][0] / 2 + 1.7, GARAGE[0][1] - 0.4, F + 0.25), (1.5, 2.6, 0.5)),
        box("rig console", (RIG[0], RIG[1], F + 0.6), (2.6, 0.7, 1.2)),
        box("rack counter", (RACK[0], RACK[1], F + 0.53), (0.8, 2.5, 1.06)),
        *[drift_box(*d) for d in DRIFTS],
        *[fence_box(*f) for f in FENCES],
    ],
    "stations": [("workshop", (RIG[0], RIG[1] - 1.0, 1.3), "Tuning rig"), ("parts", (RACK[0] - 1.05, RACK[1], 1.3), "Parts rack")],
    "crew": [
        ("mechanic", (RIG[0], 1.25, F), 0, []),
        ("mechanic", (RACK[0] + 0.8, RACK[1], F), 270, []),
        ("mechanic", (SMELTER[0], -5.8, 0.0), 180, []),
        ("bruiser", (-1.5, -8.5, 0.0), 0, [(-1.5, -8.5, 0.0), (4.5, -8.5, 0.0), (3.0, -1.0, 0.0), (-2.5, -3.5, 0.0)]),
        ("trapper", (1.5, -14.6, 0.0), 0, [(1.5, -14.6, 0.0), (16.6, -14.6, 0.0), (16.6, -7.5, 0.0), (20.5, -7.5, 0.0), (20.5, -14.6, 0.0)]),
        ("mechanic", (1.5, 2.6, F), 0, [(1.5, 2.6, F), (8.0, 2.6, F), (7.2, 9.0, F), (2.0, 9.0, F)]),
    ],
    "view": {"cam": (-38.0, -50.0, 24.0), "look": (-1.0, 1.0, 3.0), "lens": 35},
    "annex": {"cam": (20.4, -4.5, 1.8), "look": (23.8, -0.8, 1.3), "lens": 20},
    "annex_out": {"cam": (36.0, -18.0, 7.0), "look": (21.0, -1.0, 2.0), "lens": 30},
    "inside": {"cam": (4.5, -2.5, 1.7), "look": (4.5, 8.0, 2.2), "lens": 24},
}
