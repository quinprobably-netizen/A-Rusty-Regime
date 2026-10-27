"""The Deserters' Roost, on the flat south-east of Haven's apron beyond the course, door toward the pad: a two-storey steel hangar with its bay door
rolled up, a mezzanine catwalk round three walls reached by an inside stair, a roof deck with a
sandbag nest, a water tank, floodlights and a radio mast, reached by an outside switchback stair,
and a tarp awning over the door. Dark plating with pale panels and orange chevrons. Inside: bunks,
a workbench, gun racks, a planning table, lockers, crates and drums, pendant lamps."""

from basekit import Base, band, box, catwalk, door_frame, floodlight, hall, ladder, mast, railing, sandbags, slab, slope, stair, tank, wall_lamp, window
from kit import block, cyl, label, light_strip, seams, stripe
from interior import (barrel, bunk, cabinet, cable_bundle, cargo_net, crate, duct, extinguisher, first_aid, gun_rack, jump_seat, lamp,
                      pipe_run, turn, tyre, wall_panels, workbench)

FLOOR = 0.3
ROOF = 8.5
dark, pale, orange, tan = "deserter_dark", "deserter_pale", "deserter_orange", "deserter_tan"


def build():
    b = Base("roost")
    # The hangar: a hollow block, bay door in the front, a side door, four windows up high.
    hall(b, "hangar", (0, 0, ROOF / 2), (22.0, 14.0, ROOF), dark, wall=0.3,
         openings=[("-y", 0, 8.0, 5.0, 0), ("+x", -3.0, 1.4, 2.4, 0),
                   ("-y", -7.0, 2.5, 1.2, 5.5), ("-y", 7.0, 2.5, 1.2, 5.5), ("+y", -5.0, 2.0, 1.2, 5.5), ("+y", 5.0, 2.0, 1.2, 5.5)])
    slab(b, "plinth", (0, 0, -0.15), (23.0, 15.0, 0.3), "concrete", bevel=0.02)
    slab(b, "apron", (0, -8.0, 0.14), (10.0, 2.2, 0.28), "concrete", bevel=0.05)
    seams(b, (0, 0, ROOF / 2), (22.0, 14.0, ROOF), ys=(-4.0, 0.0, 4.0), xs=(-7.5, -2.5, 2.5, 7.5), material="black", width=0.05, proud=0.015)
    band(b, (0, 0, 0), (22.0, 14.0, 0), 6.9, 0.5, pale)
    band(b, (0, 0, 0), (22.0, 14.0, 0), 0.9, 0.25, orange, front_gap=8.4)
    for f in (-1, 1):
        b.add(block("panel", (f * 11.02, 2.0, 3.0), (0.05, 6.0, 3.2), pale, bevel=0.01))
        b.add(stripe("chev", (f * 4.3, -7.02, 2.5), (0.5, 0.04, 5.0), orange))
        b.add(stripe("chev", (f * 4.3, -7.02, 2.5), (0.2, 0.05, 5.0), "black"))
    b.add(cyl("doorroll", (-4.3, -7.3, 5.35), (4.3, -7.3, 5.35), 0.35, dark, segs=14, bevel=0.01))
    b.add(block("rollbox", (0, -7.25, 5.75), (9.0, 0.5, 0.5), pale, bevel=0.02))
    b.add(turn(label("THE ROOST", (0, -7.03, 6.5), 0.5, pale, side=-1, depth=0.02), (0, -7.03, 6.5), 90))
    for x in (-7.0, 7.0):
        window(b, (x, -7.0, FLOOR + 6.1), (2.5, 0.1, 1.2), frame=pale, bars=2)
    for x in (-5.0, 5.0):
        window(b, (x, 7.0, FLOOR + 6.1), (2.0, 0.1, 1.2), frame=pale, bars=1)
    door_frame(b, (11.0, -3.0, FLOOR), 1.4, 2.4, material=pale, depth=0.5)
    # The tarp awning on two posts, orange edge.
    b.add(block("awning", (0, -8.6, 5.9), (11.0, 3.2, 0.06), "canvas", bevel=0.01))
    b.add(block("awningedge", (0, -10.2, 5.9), (11.0, 0.12, 0.1), orange, bevel=0.01))
    for x in (-5.2, 5.2):
        b.add(cyl("post", (x, -10.0, 0), (x, -10.0, 5.9), 0.07, "steel", segs=10, bevel=0))
        b.add(cyl("stay", (x, -10.0, 5.9), (x * 0.9, -7.0, 7.8), 0.03, "steel", segs=6, bevel=0))
    # Outside: a switchback stair up the west side to the roof, a generator with its exhaust on
    # the east, a ladder by the side door.
    stair(b, (-11.9, -6.0, 0), 1.6, 6.0, 4.2, 12, material="gunmetal", facing=1)
    slab(b, "landing", (-12.7, 0.8, 4.14), (3.2, 1.6, 0.12), "gunmetal", bevel=0.01)
    stair(b, (-13.5, 0.0, 4.2), 1.6, 6.0, 4.3, 12, material="gunmetal", facing=-1)
    slab(b, "bridge", (-12.65, -6.0, ROOF - 0.06), (3.3, 1.6, 0.12), "gunmetal", bevel=0.01)
    railing(b, (-14.3, -6.8, ROOF), (-14.3, 1.6, ROOF))
    railing(b, (-14.3, 1.6, ROOF), (-11.1, 1.6, ROOF))
    railing(b, (-14.3, -6.0, 0), (-14.3, 0.0, 4.2))
    railing(b, (-12.7, 0.0, 4.2), (-12.7, -6.0, ROOF))
    for x, y in ((-11.9, -6.0), (-13.5, 0.0), (-13.5, -6.0), (-11.9, 0.0)):
        b.add(block("stairpost", (x - 0.8 if x < -12.5 else x + 0.8, y, 2.1), (0.1, 0.1, 4.2), "black", bevel=0))
    b.add(block("genset", (11.9, 3.5, 0.75), (1.4, 2.2, 1.5), "olive", bevel=0.03))
    b.add(cyl("stack", (11.9, 2.8, 1.5), (11.9, 2.8, 3.2), 0.1, "black", segs=8, bevel=0))
    pipe_run(b, [(11.2, 3.5, 1.2), (11.1, 3.5, 2.5), (11.1, 0.0, 2.5), (11.1, 0.0, 0.6)], r=0.05, material="copper")
    ladder(b, (11.1, -1.0, 0), 8.4, facing=1)
    # The roof: a parapet rail, the sandbag nest, the tank, floodlights and the mast.
    for p0, p1 in (((-10.8, -6.8, ROOF), (10.8, -6.8, ROOF)), ((10.8, -6.8, ROOF), (10.8, 6.8, ROOF)), ((10.8, 6.8, ROOF), (-10.8, 6.8, ROOF)), ((-10.8, 6.8, ROOF), (-10.8, -5.0, ROOF))):
        railing(b, p0, p1, spacing=2.2)
    sandbags(b, (0, -6.0, ROOF), 7.0, rows=3)
    sandbags(b, (-3.5, -4.8, ROOF), 2.2, rows=3)
    sandbags(b, (3.5, -4.8, ROOF), 2.2, rows=3)
    tank(b, (7.0, 3.5, ROOF + 1.0), 1.4, 2.6, material="steel", band=orange, ground=ROOF)
    mast(b, (-7.0, 4.5, ROOF), 9.0, light="red_light")
    floodlight(b, "flood.0", (-9.5, -6.2, ROOF), 2.6, aim=(0, -1))
    floodlight(b, "flood.1", (9.5, -6.2, ROOF), 2.6, aim=(0, -1))
    b.add(block("hatchbox", (-9.0, 0.0, ROOF + 0.3), (1.4, 1.4, 0.6), dark, bevel=0.03))
    # Inside: the mezzanine round three walls, up the stair by the east wall.
    catwalk(b, (0, 5.5, 4.0), (21.4, 2.4, 0.12), rails=("-y",))
    catwalk(b, (-9.7, -0.5, 4.0), (2.0, 9.6, 0.12), rails=("+x",))
    catwalk(b, (9.7, 1.5, 4.0), (2.0, 5.6, 0.12), rails=("-x",))
    stair(b, (9.7, -6.6, FLOOR), 1.6, 5.3, 3.76, 14, material="gunmetal", facing=1)
    railing(b, (8.9, -6.6, FLOOR), (8.9, -1.3, 4.06))
    for x in (-8.7, 8.7):
        for y in (-5.3, 4.3):
            b.add(block("prop", (x, y, 2.1), (0.16, 0.16, 3.7), "black", bevel=0.005))
    b.add(block("floorplate", (0, 0, FLOOR + 0.01), (21.4, 13.4, 0.02), "gunmetal", bevel=0))
    seams(b, (0, 0, FLOOR + 0.012), (21.4, 13.4, 0.02), ys=(-4.0, 0.0, 4.0), xs=(-6.0, 0.0, 6.0), material=pale, width=0.05, proud=0.006)
    wall_panels(b, -10.7, -6.5, 6.5, FLOOR + 0.3, 3.6, pale, n=6)
    wall_panels(b, 10.7, -6.5, -4.0, FLOOR + 0.3, 3.6, pale, n=1)
    wall_panels(b, 10.7, -2.0, 6.5, FLOOR + 0.3, 3.6, pale, n=4)
    for x0, x1 in ((-10.0, -1.0), (1.0, 10.0)):
        light_strip(b, (x0, 5.5, 3.93), (x1, 5.5, 3.93), w=0.1, material="lights_amber")
    light_strip(b, (-9.7, -4.5, 3.93), (-9.7, 3.5, 3.93), w=0.1, material="lights_amber")
    b.add(workbench("bench", (8.6, 1.5, FLOOR), (1.1, 2.0, 0.9), top="steel", frame="gunmetal"))
    b.add(crate("crate", (3.0, 2.0, FLOOR + 0.35), (0.9, 0.7, 0.7), material=orange))
    b.add(crate("crate", (-3.2, -1.5, FLOOR + 0.45), (1.1, 0.9, 0.9), material="olive"))
    # Bunks two high along the west wall, lockers by the door, the bench and racks at the back.
    for y in (1.5, 4.5):
        for z in (0.5, 1.5):
            b.add(bunk("bunk", (-10.0, y, FLOOR + z), (0.9, 2.0, 0.15), material="olive", wall=-1))
    for x in (-3.0, 0.0, 3.0):
        b.add(gun_rack("rack", (x, 6.6, FLOOR), facing=-1, n=4, material="gunmetal"))
    b.add(workbench("bench", (8.6, 4.8, FLOOR), (1.1, 2.6, 0.9), top="steel", frame="gunmetal"))
    for i, x in enumerate((5.0, 5.7, 6.4)):
        c = (x, -6.4, FLOOR + 0.95)
        b.add(turn(cabinet("locker", c, (0.6, 0.5, 1.9), material=dark, doors=1), c, 180))
    # The planning table with a lit map and seats round it.
    b.add(block("table", (0, 0.5, FLOOR + 0.8), (2.6, 1.3, 0.06), pale, bevel=0.01))
    b.add(block("map", (0, 0.5, FLOOR + 0.84), (2.2, 1.0, 0.02), "screen", bevel=0), "lights")
    for x in (-1.1, 1.1):
        for y in (0.0, 1.0):
            b.add(block("tableleg", (x, y, FLOOR + 0.4), (0.08, 0.08, 0.78), "black", bevel=0))
    for x in (-0.6, 0.6):
        b.add(jump_seat("stool", (x, -0.6, FLOOR + 0.48), facing=1, material=tan, frame="black"))
        b.add(jump_seat("stool", (x, 1.6, FLOOR + 0.48), facing=-1, material=tan, frame="black"))
    # Stores: crates and drums in the west front corner, tyres, a net on the wall.
    b.add(crate("crate", (-7.5, -4.5, FLOOR + 0.5), (1.2, 1.0, 1.0), material="olive", stencil=None))
    b.add(crate("crate", (-7.5, -4.5, FLOOR + 1.35), (1.0, 0.8, 0.7), material=tan))
    b.add(crate("crate", (-5.8, -5.0, FLOOR + 0.4), (1.0, 1.0, 0.8), material="olive"))
    for i, (x, y) in enumerate(((-9.6, -5.6), (-9.0, -6.0), (-9.8, -4.8))):
        b.add(barrel("drum", (x, y, FLOOR), r=0.3, h=0.9, material=orange if i == 1 else "rust"))
    b.add(tyre("tyre", (-4.0, -6.0, FLOOR + 0.45), axis=(0, 1, 0), r=0.45, w=0.3))
    b.add(tyre("tyre", (-4.0, -5.6, FLOOR + 0.45), axis=(0, 1, 0), r=0.45, w=0.3))
    b.add(cargo_net("net", (-10.68, -3.0, FLOOR + 2.0), (1.8, 3.0), material="olive"))
    c = (10.6, 5.5, FLOOR + 1.5)
    b.add(turn(first_aid("aid", c, facing=-1), c, 90))
    b.add(extinguisher("ext", (10.5, -4.2, FLOOR + 0.3), wall=1))
    # Overhead: a duct and cables along the back, pendant lamps low enough to light the floor,
    # bulkhead lamps under the catwalks.
    b.add(duct("duct", (-10.0, 6.3, ROOF - 0.6), (10.0, 6.3, ROOF - 0.6), (0, 0.6, 0.4), material="grey", flange=2.0))
    b.add(cable_bundle("cables", [(-10.5, 5.8, ROOF - 0.35), (-3.0, 5.8, ROOF - 0.55), (4.0, 5.8, ROOF - 0.4), (10.5, 5.8, ROOF - 0.55)], material="black"))
    for i, (x, y) in enumerate(((-5.0, -3.0), (5.0, -3.0), (-5.0, 3.0), (5.0, 3.0))):
        b.add(cyl("cord", (x, y, ROOF - 0.3), (x, y, 5.1), 0.015, "black", segs=6, bevel=0))
        b.add(cyl("shade", (x, y, 5.1), (x, y, 4.85), 0.12, "gunmetal", r1=0.42, segs=14, bevel=0.005))
        lamp(b, f"lamp.{i}", (x, y, 4.86), rim="gunmetal", r=0.2, cage=True)
    wall_lamp(b, "lamp.4", (-6.0, 6.68, FLOOR + 2.6), rim="black")
    wall_lamp(b, "lamp.5", (6.0, 6.68, FLOOR + 2.6), rim="black")
    return b


SPEC = {
    "build": build,
    "name": "The Roost",
    "faction": "deserters",
    "body": "home",
    "near_pad": (70.0, 85.0),
    "yaw": 180.0,
    "footprint": (26.0, 18.0),
    "door": (0.0, -6.85, 1.2),
    "size": (17.8, 27.0, 18.0),
    "depth": 0.3,
    "nodes": ["lamp.0", "lamp.1", "lamp.2", "lamp.3", "lamp.4", "lamp.5", "flood.0", "flood.1"],
    "boxes": [
        box("floor", (0, 0, 0.15), (22.0, 14.0, 0.3)),
        box("roof", (0, 0, ROOF - 0.15), (22.0, 14.0, 0.3)),
        box("west wall", (-10.85, 0, ROOF / 2), (0.3, 14.0, ROOF)),
        box("back wall", (0, 6.85, ROOF / 2), (22.0, 0.3, ROOF)),
        box("front wall", (-7.5, -6.85, ROOF / 2), (7.0, 0.3, ROOF)),
        box("front wall", (7.5, -6.85, ROOF / 2), (7.0, 0.3, ROOF)),
        box("door lintel", (0, -6.85, 6.9), (8.0, 0.3, 3.2)),
        box("east wall", (10.85, 2.35, ROOF / 2), (0.3, 9.3, ROOF)),
        box("east wall", (10.85, -5.35, ROOF / 2), (0.3, 2.7, ROOF)),
        box("side door lintel", (10.85, -3.0, 5.6), (0.3, 1.4, 5.8)),
        box("back catwalk", (0, 5.5, 4.0), (21.4, 2.4, 0.12)),
        box("west catwalk", (-9.7, -0.5, 4.0), (2.0, 9.6, 0.12)),
        box("east landing", (9.7, 1.5, 4.0), (2.0, 5.6, 0.12)),
        slope((9.7, -6.6, FLOOR), 1.6, 5.3, 3.76, 1),
        slope((-11.9, -6.0, 0), 1.6, 6.0, 4.2, 1),
        box("stair landing", (-12.7, 0.8, 4.14), (3.2, 1.6, 0.12)),
        slope((-13.5, 0.0, 4.2), 1.6, 6.0, 4.3, -1),
        box("bridge", (-12.65, -6.0, ROOF - 0.06), (3.3, 1.6, 0.12)),
        box("table", (0, 0.5, FLOOR + 0.42), (2.6, 1.3, 0.84)),
        box("tank", (7.0, 3.5, ROOF + 1.8), (2.8, 2.8, 3.6)),
        box("genset", (11.9, 3.5, 0.75), (1.4, 2.2, 1.5)),
    ],
    "view": {"cam": (-24.0, -30.0, 14.0), "look": (0, 0, 4.0), "lens": 35},
    "inside": {"cam": (0.5, -9.5, FLOOR + 1.6), "look": (0, 2.0, FLOOR + 1.8), "lens": 22},
}
