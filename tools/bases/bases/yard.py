"""The Scrappers' Yard on Cinder: a junk fort. A wall of welded, stacked shipping containers with
a gate under a truss gantry, a workshop shed open at the front with a crane rail inside, a
gantry crane over the yard, a lookout derrick, a water tower, drums, tyres, gas bottles, pipe
runs, a scrap heap under a tarp and hazard stripes everywhere. Brass, copper, rust and hazard
yellow. Inside the shed: workbenches, cabinets, a hoist, a wheel on the wall, caged lamps; a
container made into quarters with bunks."""

import math

from basekit import ring, Base, box, container, floodlight, hall, ladder, mast, railing, room, room_boxes, slab, tank, truss, wall_lamp
from kit import join, block, chain, cyl, label, rivets, seams, sphere, stripe
from interior import (barrel, cabinet, cable_bundle, cargo_net, crate, dash, extinguisher, gas_bottle, grating, gun_rack, hoist, lamp, pipe_run, turn, tyre,
                      wheel, workbench)
from mathutils import Vector

C = (6.0, 2.4, 2.6)  # a container
rust, brass, copper, hazard, leather = "rust", "brass", "copper", "hazard", "leather"


def wall_x(b, x, ys, materials, stack=()):
    """Containers along Y at `x`, doors outward; `stack` lists which get a second on top."""
    for i, y in enumerate(ys):
        container(b, (x, y, 1.3), C, material=materials[i % len(materials)], band=hazard if i % 3 == 0 else None, doors="-y" if y < 0 else "+y")
        if i in stack:
            container(b, (x, y, 3.9), C, material=materials[(i + 1) % len(materials)])


def wall_y(b, y, xs, materials, stack=()):
    """Containers along X at `y` (turned a quarter), doors outward."""
    for i, x in enumerate(xs):
        c = (x, y, 1.3)
        turn(container(b, c, C, material=materials[i % len(materials)], band=hazard if i % 2 else None, doors="-y"), c, 90 if y < 0 else -90)
        if i in stack:
            c = (x, y, 3.9)
            turn(container(b, c, C, material=materials[(i + 2) % len(materials)]), c, 90 if y < 0 else -90)


def build():
    b = Base("yard")
    mats = [rust, "olive", copper, "grey"]
    slab(b, "plinth", (0, 0, -0.15), (36.0, 32.0, 0.3), "concrete", bevel=0.02)
    # The walls: containers on three sides, the gate wall in front with a gantry over the gap.
    wall_x(b, -15.0, (-9.0, -3.0, 3.0, 9.0), mats, stack=(1, 2))
    wall_x(b, 15.0, (-9.0, -3.0, 3.0, 9.0), mats[::-1], stack=(0, 3))
    wall_y(b, 12.0, (-12.0, -6.0, 0.0, 6.0, 12.0), mats, stack=(0, 2, 4))
    wall_y(b, -12.0, (-12.0, -6.0, 6.0, 12.0), mats[1:], stack=(1, 2))
    for sx in (-1, 1):
        b.add(block("gatepost", (sx * 3.3, -12.0, 2.75), (0.6, 0.6, 5.5), "black", bevel=0.02))
        for z in (0.8, 2.0, 3.2, 4.4):
            b.add(stripe("gatechev", (sx * 3.3, -12.0, z), (0.6, 0.6, 0.5), hazard))
    truss(b, (-3.6, -12.0, 5.8), (3.6, -12.0, 5.8), s=0.6)
    b.add(block("sign", (0, -12.0, 4.6), (4.4, 0.08, 0.9), "canvas", bevel=0.01))
    b.add(turn(label("THE YARD", (0, -12.05, 4.6), 0.65, hazard, side=-1, depth=0.03), (0, -12.05, 4.6), 90))
    for sx in (-1, 1):
        b.add(cyl("signchain", (sx * 1.8, -12.0, 5.05), (sx * 1.8, -12.0, 5.5), 0.02, "steel", segs=6, bevel=0))
    b.add(cyl("bell", (3.9, -12.3, 3.3), (3.9, -12.3, 2.9), 0.14, brass, r1=0.22, segs=12, bevel=0.01))
    floodlight(b, "flood.0", (-3.3, -12.0, 5.5), 0.6, aim=(0, -1))
    floodlight(b, "flood.1", (3.3, -12.0, 5.5), 0.6, aim=(0, -1))
    # The workshop shed at the back, open at the front under a canvas awning.
    hall(b, "shed", (4.0, 6.0, 2.75), (14.0, 10.0, 5.5), rust, wall=0.25, openings=[("-y", 0, 8.0, 4.5, 0), ("+x", -2.0, 1.2, 2.2, 0)], bevel=0.04)
    seams(b, (4.0, 6.0, 2.75), (14.0, 10.0, 5.5), ys=(-3.0, 0.0, 3.0), xs=(-4.5, -1.5, 1.5, 4.5), material="black", width=0.05, proud=0.015)
    for x in (-2.4, -1.2, 0.0, 1.2, 2.4):
        b.add(block("roofrib", (4.0 + x * 2.6, 6.0, 5.52), (0.12, 10.0, 0.08), "black", bevel=0))
    b.add(block("awning", (4.0, -0.4, 4.4), (9.0, 2.8, 0.06), "canvas", bevel=0.01))
    b.add(block("awningedge", (4.0, -1.8, 4.38), (9.0, 0.12, 0.1), hazard, bevel=0.01))
    for x in (-0.3, 8.3):
        b.add(cyl("awningpost", (x, -1.7, 0), (x, -1.7, 4.4), 0.06, "steel", segs=8, bevel=0))
    b.add(stripe("shedstripe", (4.0, 1.0, 5.0), (14.0, 0.05, 0.4), hazard))
    b.add(cyl("stovepipe", (9.5, 9.0, 5.5), (9.5, 9.0, 7.6), 0.14, "black", segs=10, bevel=0))
    b.add(cyl("stovecap", (9.5, 9.0, 7.6), (9.5, 9.0, 7.8), 0.3, "black", segs=10, bevel=0))
    # Quarters: a container with a door cut in its side, bunks inside.
    hall(b, "quarters", (11.5, -5.0, 1.3), (6.0, 2.6, 2.6), "olive", wall=0.1, openings=[("-x", 0.0, 0.9, 2.0, 0), ("+y", 0.0, 0.8, 0.5, 1.4)], bevel=0.02)
    b.add(block("quartersband", (11.5, -5.0, 0.6), (6.04, 2.64, 0.25), hazard, bevel=0))
    for y in (-5.9, -4.1):
        for z in (0.5, 1.4):
            from interior import bunk
            b.add(bunk("bunk", (12.9, y, 0.1 + z), (0.85, 1.7, 0.14), material="olive", wall=1))
    b.add(crate("qcrate", (9.4, -5.6, 0.45), (0.8, 0.7, 0.7), material="olive"))
    lamp(b, "lamp.3", (11.5, -5.0, 2.48), rim="black", r=0.14, cage=True)
    # The gantry crane down the west side of the yard, A-frame legs and a truss, hoist on the beam.
    for y in (-9.0, 9.0):
        for dx in (-1.2, 1.2):
            b.add(cyl("craneleg", (-8.0 + dx, y, 0), (-8.0, y, 7.0), 0.12, "steel", segs=10, bevel=0))
        b.add(block("cranefoot", (-8.0, y, 0.15), (3.2, 0.5, 0.3), "black", bevel=0.01))
    truss(b, (-8.0, -9.3, 7.0), (-8.0, 9.3, 7.0), s=0.7, bay=1.5)
    hoist(b, (-8.0, 0.0, 6.6), 18.0, 3.2)
    for sx in (-1, 1):
        b.add(stripe("cranestripe", (-8.0, sx * 9.0, 7.0), (0.75, 0.75, 0.75), hazard))
    # The lookout derrick in the south-west corner: four legs, a platform, a canvas roof.
    for ax, ay in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        b.add(cyl("derrickleg", (-12.0 + ax * 1.6, -8.5 + ay * 1.6, 0), (-12.0 + ax * 0.9, -8.5 + ay * 0.9, 9.0), 0.08, "steel", segs=8, bevel=0))
    for z in (3.0, 6.0):
        for ax, ay, bx, by in ((-1, -1, 1, -1), (1, -1, 1, 1), (1, 1, -1, 1), (-1, 1, -1, -1)):
            k = 1.6 - 0.7 * z / 9.0
            b.add(cyl("brace", (-12.0 + ax * k, -8.5 + ay * k, z), (-12.0 + bx * k, -8.5 + by * k, z), 0.04, "steel", segs=6, bevel=0))
    grating(b, (-12.0, -8.5, 9.0), (2.6, 2.6), material="gunmetal", pitch=0.2)
    b.add(block("platform", (-12.0, -8.5, 8.9), (2.6, 2.6, 0.12), "black", bevel=0.01))
    railing(b, (-13.3, -9.8, 9.0), (-10.7, -9.8, 9.0), spacing=1.3)
    railing(b, (-10.7, -9.8, 9.0), (-10.7, -7.2, 9.0), spacing=1.3)
    railing(b, (-10.7, -7.2, 9.0), (-13.3, -7.2, 9.0), spacing=1.3)
    railing(b, (-13.3, -7.2, 9.0), (-13.3, -9.8, 9.0), spacing=1.3)
    for ax, ay in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        b.add(cyl("roofpost", (-12.0 + ax * 1.2, -8.5 + ay * 1.2, 9.0), (-12.0 + ax * 1.2, -8.5 + ay * 1.2, 11.2), 0.04, "steel", segs=6, bevel=0))
    b.add(block("derrickroof", (-12.0, -8.5, 11.25), (3.0, 3.0, 0.08), "canvas", bevel=0.01))
    floodlight(b, "flood.2", (-11.2, -9.7, 9.0), 1.6, aim=(0, 1))
    mast(b, (-12.0, -8.5, 11.3), 6.0, r=0.05, arms=2, light="red_light")
    # The water tower, pipes to the shed, and the scrap.
    tank(b, (12.0, 8.0, 6.0), 1.6, 3.0, material=rust, band=hazard)
    pipe_run(b, [(12.0, 6.4, 6.3), (12.0, 4.6, 6.3), (12.0, 4.6, 1.0), (9.8, 4.6, 1.0), (9.8, 1.5, 1.0)], r=0.07, material=copper, brackets=1.5, valve_at=(12.0, 4.6, 2.0))
    b.add(block("scrap", (-11.0, 4.0, 0.9), (4.0, 5.0, 1.8), rust, bevel=0.2, segs=3))
    b.add(block("tarp", (-11.0, 4.0, 1.9), (4.6, 5.6, 0.1), "canvas", bevel=0.05))
    for i in range(8):
        a = i * 0.8
        b.add(tyre("tyre", (-5.0 + math.cos(a) * 0.9, -7.0 + math.sin(a) * 0.9, 0.15 + (i % 3) * 0.3), axis=(0, 0, 1), r=0.42, w=0.28))
    for i, (x, y) in enumerate(((-3.5, 9.0), (-2.9, 9.4), (-3.6, 9.9), (-4.3, 9.2), (-2.8, 10.3))):
        b.add(barrel("drum", (x, y, 0), r=0.3, h=0.9, material=[rust, hazard, "olive", copper][i % 4]))
    for i, x in enumerate((6.5, 6.9, 7.3)):
        b.add(gas_bottle("gas", (x, -9.5, 0), material=["olive", "red", "olive"][i]))
    b.add(crate("crate", (2.0, -8.5, 0.5), (1.2, 1.0, 1.0), material="olive", band=hazard))
    b.add(crate("crate", (2.0, -8.5, 1.35), (1.0, 0.8, 0.7), material=leather))
    b.add(block("genset", (-13.2, 0.0, 0.7), (1.6, 2.2, 1.4), "olive", bevel=0.03))
    b.add(cyl("stack", (-13.2, 0.7, 1.4), (-13.2, 0.7, 2.6), 0.08, "black", segs=8, bevel=0))
    ladder(b, (14.9, -3.0, 0), 5.0, facing=-1)
    # Inside the shed: benches, cabinets, a gun rack, a hoist, a wheel and a net on the wall,
    # cables and a pipe overhead, grating in the middle, caged lamps.
    b.add(workbench("bench", (-2.0, 9.4, 0.25), (1.0, 3.0, 0.9), top="steel", frame=rust))
    b.add(workbench("bench", (9.6, 6.0, 0.25), (1.0, 2.6, 0.9), top="steel", frame=rust))
    c = (-2.3, 2.5, 0.25 + 0.95)
    b.add(turn(cabinet("cabinet", c, (0.8, 0.5, 1.9), material="grey", doors=2), c, -90))
    c = (-2.3, 4.5, 0.25 + 0.95)
    b.add(turn(cabinet("cabinet", c, (0.8, 0.5, 1.9), material=rust, doors=2), c, -90))
    b.add(gun_rack("rack", (4.0, 10.6, 0.25), facing=-1, n=5, material=rust))
    b.add(crate("shedcrate", (6.5, 9.5, 0.75), (1.4, 1.0, 1.0), material="olive"))
    b.add(crate("shedcrate", (6.5, 9.5, 1.6), (1.0, 0.8, 0.7), material=brass))
    b.add(turn(wheel("wheel", (10.5, 3.0, 1.4), facing=-1, r=0.3), (10.5, 3.0, 1.4), 90))
    b.add(cargo_net("net", (-2.68, 7.0, 1.8), (1.6, 2.4), material="olive"))
    hoist(b, (3.0, 6.0, 5.2), 8.0, 1.6)
    grating(b, (4.0, 5.0, 0.26), (5.0, 4.0), material="gunmetal", pitch=0.2)
    b.add(cable_bundle("cables", [(-2.6, 2.0, 5.0), (0.0, 2.0, 4.8), (3.0, 2.0, 5.0), (6.0, 2.0, 4.85), (9.0, 2.0, 5.0)], material="black"))
    pipe_run(b, [(10.7, 8.0, 4.8), (10.7, 2.0, 4.8), (10.7, 2.0, 1.5)], r=0.05, material=copper, brackets=1.2)
    b.add(extinguisher("ext", (10.6, 1.8, 0.55), wall=1))
    for i, (x, y) in enumerate(((0.5, 4.0), (7.5, 4.0), (4.0, 8.5))):
        lamp(b, f"lamp.{i}", (x, y, 5.24), rim="black", r=0.2, cage=True)
    wall_lamp(b, "lamp.4", (-12.0, -8.5, 10.4), rim="black")
    wall_lamp(b, "lamp.5", (-8.0, 11.5, 2.2), rim="black")
    detail(b)
    garage(b)
    return b


def tyre0(name, c):
    """A flat tyre with sharp edges, for the stacks."""
    return join([ring(name, c, (0, 0, 1), 0.42, 0.23, 0.28, "black", segs=16), ring("hubring", c, (0, 0, 1), 0.23, 0.12, 0.17, "steel", segs=10)], name)


def coil(b, p0, p1, n, r=0.3):
    """A coil of razor wire: `n` loops from p0 to p1 on a wire."""
    a, z = Vector(p0), Vector(p1)
    d = (z - a).normalized()
    for i in range(n):
        b.add(ring("razor", a.lerp(z, (i + 0.5) / n), tuple(d), r, r - 0.025, 0.03, "steel", segs=9))
    b.add(cyl("razorwire", a, z, 0.015, "steel", segs=4, bevel=0))
    b.add(cyl("razorwire", a + Vector((0, 0, r * 0.9)), z + Vector((0, 0, r * 0.9)), 0.012, "steel", segs=4, bevel=0))


def festoon(b, p0, p1, sag, bulbs):
    """A string of bulbs on a sagging wire from p0 to p1."""
    a, z = Vector(p0), Vector(p1)
    pts = []
    for i in range(bulbs + 1):
        t = i / bulbs
        pts.append(a.lerp(z, t) - Vector((0, 0, sag * 4 * t * (1 - t))))
    for q0, q1 in zip(pts, pts[1:]):
        b.add(cyl("wire", q0, q1, 0.012, "black", segs=4, bevel=0))
    for q in pts[1:-1]:
        b.add(sphere("bulb", q - Vector((0, 0, 0.1)), 0.07, "lamp", segs=6), "lights")


def detail(b):
    """The second pass: razor wire along the container walls, festoon lights across the yard, a burn
    barrel with a bench, tyre stacks, a crane cab, welded patches and junk on the shed and the
    scrap heap, roof clutter."""
    top = 2.6 + 0.02
    for y in (-9.0, 9.0):
        coil(b, (-17.6, y, top + 0.28), (-12.4, y, top + 0.28), 9)
    for y in (-3.0, 3.0):
        coil(b, (12.4, y, top + 0.28), (17.6, y, top + 0.28), 9)
    for x in (-6.0, 6.0):
        coil(b, (x, 9.4, top + 0.28), (x, 14.6, top + 0.28), 9)
    for x in (-12.0, 12.0):
        coil(b, (x, -14.6, top + 0.28), (x, -9.4, top + 0.28), 9)
    # Festoon lights from the crane to the gate and to the shed.
    festoon(b, (-8.0, -9.0, 7.0), (-3.3, -12.0, 5.5), 0.7, 8)
    festoon(b, (-8.0, 9.0, 7.0), (-2.9, 1.1, 5.4), 0.9, 12)
    festoon(b, (3.3, -12.0, 5.5), (11.0, -7.0, 5.0), 0.8, 11)
    b.add(block("festoonpole", (11.0, -7.0, 2.5), (0.1, 0.1, 5.0), "black", bevel=0))
    # A burn barrel with a bench of scaffold planks, a crate each side.
    b.add(barrel("burnbarrel", (-1.5, -4.5, 0), r=0.32, h=0.95, material="rust"))
    b.add(cyl("burncoals", (-1.5, -4.5, 0.93), (-1.5, -4.5, 0.97), 0.28, "lamp", segs=10, bevel=0), "lights")
    for i, (dx, dy, h) in enumerate(((0.0, 0.0, 0.5), (0.12, 0.1, 0.35), (-0.1, -0.08, 0.28))):
        b.add(cyl("flame", (-1.5 + dx, -4.5 + dy, 0.95), (-1.5 + dx, -4.5 + dy, 0.95 + h), 0.09, "lamp", r1=0.0, segs=6, bevel=0), "lights")
    b.add(block("plank", (-1.5, -3.2, 0.42), (2.2, 0.35, 0.06), "tan", bevel=0.01))
    for dx in (-0.9, 0.9):
        b.add(block("plankleg", (-1.5 + dx, -3.2, 0.2), (0.1, 0.3, 0.4), "black", bevel=0))
    b.add(crate("seat", (-2.9, -4.2, 0.3), (0.6, 0.6, 0.6), material="olive"))
    # Tyre stacks by the gate and a heap of wheels on the scrap.
    for x, y, n in ((4.2, -7.0, 4), (5.0, -7.4, 3), (-3.8, -8.0, 5)):
        for i in range(n):
            b.add(tyre0("tyre", (x, y, 0.14 + 0.28 * i)))
    for i in range(6):
        x, y = -12.2 + 0.7 * (i % 3), 2.4 + 1.5 * (i // 3) + 0.4 * (i % 2)
        b.add(tyre0("tyre", (x, y, 2.1)))
    for i, (x, y, rot, sz) in enumerate(((-12.0, 3.2, 20, (1.6, 0.06, 0.9)), (-10.2, 5.0, -35, (1.4, 0.06, 0.8)), (-10.6, 2.8, 50, (1.1, 0.08, 1.0)))):
        b.add(block("junkplate", (x, y, 2.3 + 0.15 * i), sz, [rust, brass, "grey"][i], bevel=0.02, rot=rot))
    b.add(cyl("junkpipe", (-12.5, 5.6, 2.1), (-9.6, 3.6, 2.6), 0.1, copper, segs=8, bevel=0))
    b.add(cyl("junkpipe", (-12.4, 5.9, 2.0), (-9.5, 5.2, 2.3), 0.07, "steel", segs=8, bevel=0))
    # The crane: an operator's cab under the truss and a cable to the hoist.
    b.add(block("cab", (-8.0, -7.0, 6.05), (1.3, 1.3, 1.3), hazard, bevel=0.04))
    b.add(block("cabglass", (-7.34, -7.0, 6.2), (0.02, 1.0, 0.6), "glass", bevel=0), "glass")
    b.add(block("cabroof", (-8.0, -7.0, 6.75), (1.5, 1.5, 0.08), "black", bevel=0.01))
    b.add(chain("cabhanger", (-8.0, -7.0, 6.7), (-8.0, -7.0, 6.98), links=3, r=0.04))
    # Welded patch plates and rivets on the shed's side walls, vents and a TV aerial on its roof.
    for sx, x in ((-1, -3.04), (1, 11.04)):
        for i, (y, z, w, h) in enumerate(((4.0, 2.2, 1.4, 0.9), (7.5, 3.4, 0.9, 1.1), (9.0, 1.6, 1.0, 0.7))):
            b.add(block("patch", (x, y, z), (0.04, w, h), [brass, copper, "grey"][i], bevel=0.01))
            b.add(rivets("patchrivets", (x + sx * 0.03, y - w / 2 + 0.1, z + h / 2 - 0.08), (x + sx * 0.03, y + w / 2 - 0.1, z + h / 2 - 0.08), 5, axis="x" if sx > 0 else "-x"))
    for x in (0.0, 4.0, 8.0):
        b.add(cyl("roofvent", (x, 7.5, 5.5), (x, 7.5, 6.1), 0.18, "black", segs=8, bevel=0))
        b.add(cyl("roofventcap", (x, 7.5, 6.1), (x, 7.5, 6.3), 0.32, "black", r1=0.05, segs=8, bevel=0))
    b.add(cyl("aerial", (1.0, 3.0, 5.5), (1.0, 3.0, 7.4), 0.03, "steel", segs=6, bevel=0))
    for z, w in ((6.4, 0.9), (6.8, 0.7), (7.1, 0.5)):
        b.add(block("aerialarm", (1.0, 3.0, z), (w, 0.03, 0.03), "steel", bevel=0))
    for i in range(3):
        b.add(barrel("roofdrum", (-1.5 + 0.7 * i, 9.5, 5.55), r=0.3, h=0.8, material=[rust, hazard, "olive"][i]))
    # A tool wall inside the shed: pegboard, wrenches, a saw blade.
    b.add(block("pegboard", (-2.66, 9.4, 1.9), (0.05, 2.6, 1.0), "black", bevel=0))
    b.add(cyl("sawblade", (-2.62, 8.4, 2.0), (-2.6, 8.4, 2.0), 0.28, "steel", segs=18, bevel=0))
    for i in range(6):
        y = 8.9 + 0.3 * i
        b.add(block("tool", (-2.62, y, 1.85 + 0.12 * (i % 2)), (0.03, 0.05, 0.4), "steel" if i % 2 else copper, bevel=0))


GARAGE = ((22.0, -2.0), (8.0, 6.0, 3.6))
GARAGE_DOORS = [("-y", 0.0, 2.6, 2.8)]


def garage(b):
    """The tuning garage outside the east wall: a ship engine on a stand under a hoist rail, a
    console with its screens, a bench and tyres. Pay here to tune the Kestrel's engines."""
    (x, y), s = GARAGE
    z0 = 0.25
    room(b, "garage", (x, y), s, rust, GARAGE_DOORS, wall=0.25, trim="black")
    for sx in (-1, 1):
        b.add(stripe("doorchev", (x + sx * 1.6, y - s[1] / 2, 1.5), (0.4, 0.04, 3.0), hazard))
    b.add(stripe("garagestripe", (x, y - s[1] / 2, 3.3), (s[0], 0.05, 0.3), hazard))
    b.add(turn(label("TUNING", (x, y - s[1] / 2 - 0.03, 3.0), 0.5, hazard, side=-1, depth=0.02), (x, y - s[1] / 2 - 0.03, 3.0), 90))
    b.add(cyl("vent", (x + 2.5, y + 1.5, s[2] + 0.1), (x + 2.5, y + 1.5, s[2] + 1.0), 0.18, "black", segs=10, bevel=0))
    b.add(cyl("ventcap", (x + 2.5, y + 1.5, s[2] + 1.0), (x + 2.5, y + 1.5, s[2] + 1.1), 0.3, "black", segs=10, bevel=0))
    for i, gx in enumerate((x - 3.0, x + 3.0)):
        b.add(gas_bottle("gas", (gx, y - s[1] / 2 - 0.5, 0), material="olive" if i else "red"))
    # The engine: a drum body, a flared bell and bands, in a cradle on a low stand, a spare nozzle beside it.
    ex = x - 1.6
    b.add(block("stand", (ex, y - 1.2, z0 + 0.25), (1.5, 2.6, 0.5), "black", bevel=0.02))
    for dy in (-1.6, -0.2):
        b.add(block("cradle", (ex, y + dy, z0 + 0.7), (1.1, 0.12, 0.5), "gunmetal", bevel=0.01))
    b.add(cyl("engine", (ex, y - 2.0, z0 + 1.05), (ex, y + 0.2, z0 + 1.05), 0.5, "gunmetal", segs=16, bevel=0.01))
    b.add(cyl("bell", (ex, y + 0.2, z0 + 1.05), (ex, y + 1.1, z0 + 1.05), 0.34, "steel", r1=0.62, segs=16, bevel=0.01))
    for dy in (-1.6, -0.9, -0.2):
        b.add(cyl("enginering", (ex, y + dy, z0 + 1.05), (ex, y + dy + 0.12, z0 + 1.05), 0.54, copper, segs=16, bevel=0))
    b.add(cyl("feed", (ex, y - 2.0, z0 + 1.05), (ex, y - 2.4, z0 + 1.05), 0.25, brass, segs=12, bevel=0))
    hoist(b, (ex, y - 0.4, s[2] - 0.5), 4.4, 0.9)
    # The console on the north wall and the bench along the east.
    dash(b, (x + 1.8, y + s[1] / 2 - 0.65, z0), 2.4, material="gunmetal", screens=3, screen_mat="lights_amber", facing=1)
    b.add(workbench("bench", (x + s[0] / 2 - 0.7, y - 0.6, z0), (0.9, 2.4, 0.9), top="steel", frame=rust))
    for i, ty in enumerate((y - 2.4, y - 2.2)):
        b.add(tyre("tyre", (x + 3.0, ty, z0 + 0.15 + i * 0.3), axis=(0, 0, 1), r=0.42, w=0.28))
    b.add(crate("part", (x + 3.0, y + 1.6, z0 + 0.35), (0.9, 0.9, 0.7), material="olive", band=hazard))
    b.add(barrel("drum", (x - 3.2, y + 2.2, z0), r=0.3, h=0.9, material=hazard))
    lamp(b, "lamp.6", (x, y, s[2] - 0.27), rim="black", r=0.2, cage=True)


def _containers():
    out = []
    for x, ys, stack in ((-15.0, (-9.0, -3.0, 3.0, 9.0), (1, 2)), (15.0, (-9.0, -3.0, 3.0, 9.0), (0, 3))):
        for i, y in enumerate(ys):
            out.append(box("container", (x, y, 1.3), C))
            if i in stack:
                out.append(box("container", (x, y, 3.9), C))
    for y, xs, stack in ((12.0, (-12.0, -6.0, 0.0, 6.0, 12.0), (0, 2, 4)), (-12.0, (-12.0, -6.0, 6.0, 12.0), (1, 2))):
        for i, x in enumerate(xs):
            out.append(box("container", (x, y, 1.3), (C[1], C[0], C[2])))
            if i in stack:
                out.append(box("container", (x, y, 3.9), (C[1], C[0], C[2])))
    return out


SPEC = {
    "build": build,
    "name": "The Yard",
    "color": (1.0, 0.85, 0.1),
    "faction": "scrappers",
    "body": "cinder",
    "lat": -8.0,
    "lon": 120.0,
    "footprint": (44.0, 32.0),
    "footprint_at": (4.0, 0.0),
    "pad": (0.0, -30.0),
    "door": (0.0, -12.0, 1.2),
    "size": (32.0, 44.2, 17.8),
    "depth": 0.3,
    "nodes": [f"lamp.{i}" for i in range(7)] + ["flood.0", "flood.1", "flood.2"],
    "boxes": [
        *_containers(),
        box("gatepost", (-3.3, -12.0, 2.75), (0.6, 0.6, 5.5)),
        box("gatepost", (3.3, -12.0, 2.75), (0.6, 0.6, 5.5)),
        box("shed floor", (4.0, 6.0, 0.125), (14.0, 10.0, 0.25)),
        box("shed roof", (4.0, 6.0, 5.375), (14.0, 10.0, 0.25)),
        box("shed west", (-2.875, 6.0, 2.75), (0.25, 10.0, 5.5)),
        box("shed back", (4.0, 10.875, 2.75), (14.0, 0.25, 5.5)),
        box("shed east", (10.875, 7.1, 2.75), (0.25, 7.8, 5.5)),
        box("shed east", (10.875, 1.3, 2.75), (0.25, 0.6, 5.5)),
        box("shed east lintel", (10.875, 4.0, 4.0), (0.25, 1.2, 3.0)),
        box("shed front", (0.1, 1.125, 2.75), (3.0, 0.25, 5.5)),
        box("shed front", (9.5, 1.125, 2.75), (3.0, 0.25, 5.5)),
        box("shed lintel", (4.0, 1.125, 5.0), (8.0, 0.25, 1.0)),
        box("quarters floor", (11.5, -5.0, 0.05), (6.0, 2.6, 0.1)),
        box("quarters roof", (11.5, -5.0, 2.55), (6.0, 2.6, 0.1)),
        box("quarters wall", (11.5, -6.25, 1.3), (6.0, 0.1, 2.6)),
        box("quarters wall", (11.5, -3.75, 1.3), (6.0, 0.1, 2.6)),
        box("quarters end", (14.45, -5.0, 1.3), (0.1, 2.6, 2.6)),
        box("quarters end", (8.55, -5.95, 1.3), (0.1, 0.7, 2.6)),
        box("quarters end", (8.55, -4.05, 1.3), (0.1, 0.7, 2.6)),
        box("quarters lintel", (8.55, -5.0, 2.35), (0.1, 0.9, 0.5)),
        box("derrick platform", (-12.0, -8.5, 8.9), (2.6, 2.6, 0.12)),
        box("crane foot", (-8.0, -9.0, 0.15), (3.2, 0.5, 0.3)),
        box("crane foot", (-8.0, 9.0, 0.15), (3.2, 0.5, 0.3)),
        box("scrap", (-11.0, 4.0, 0.95), (4.4, 5.4, 1.9)),
        box("genset", (-13.2, 0.0, 0.7), (1.6, 2.2, 1.4)),
        box("tank", (12.0, 8.0, 7.5), (3.2, 3.2, 3.2)),
        box("bench", (-2.0, 9.4, 0.7), (1.0, 3.0, 0.9)),
        box("bench", (9.6, 6.0, 0.7), (1.0, 2.6, 0.9)),
        box("crate", (2.0, -8.5, 0.5), (1.2, 1.0, 1.0)),
        box("crate", (6.5, 9.5, 0.75), (1.4, 1.0, 1.0)),
        *room_boxes("garage", GARAGE[0], GARAGE[1], GARAGE_DOORS, wall=0.25),
        box("engine stand", (GARAGE[0][0] - 1.6, GARAGE[0][1] - 1.2, 0.5), (1.5, 2.6, 0.5)),
        box("garage bench", (GARAGE[0][0] + 3.3, GARAGE[0][1] - 0.6, 0.7), (0.9, 2.4, 0.9)),
    ],
    "stations": [("workshop", (GARAGE[0][0] + 1.8, GARAGE[0][1] + 1.2, 1.3), "Tuning rig")],
    "view": {"cam": (-30.0, -40.0, 18.0), "look": (0, 0, 3.0), "lens": 35},
    "annex": {"cam": (25.4, -4.5, 1.9), "look": (21.0, -0.6, 1.2), "lens": 22},
    "annex_out": {"cam": (36.0, -16.0, 6.0), "look": (22.0, -2.0, 2.0), "lens": 30},
    "inside": {"cam": (4.0, -4.0, 1.7), "look": (4.0, 8.0, 2.0), "lens": 24},
}
