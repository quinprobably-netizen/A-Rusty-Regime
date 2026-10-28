"""The Deserters' Roost, on the flat south-east of Haven's apron beyond the course, door toward the pad: a two-storey steel hangar with its bay door
rolled up, a mezzanine catwalk round three walls reached by an inside stair, a roof deck with a
sandbag nest, a water tank, floodlights and a radio mast, reached by an outside switchback stair,
and a tarp awning over the door. Dark plating with pale panels and orange chevrons. Inside: bunks,
a workbench, gun racks, a planning table, lockers, crates and drums, pendant lamps."""

from basekit import ring, Base, band, box, catwalk, door_frame, floodlight, hall, ladder, mast, railing, room, room_boxes, sandbags, slab, slope, stair, tank, truss, wall_lamp, window
from kit import block, chain, cyl, label, light_strip, rivets, seams, stripe
from interior import (grating, barrel, bunk, cabinet, cable_bundle, cargo_net, crate, duct, extinguisher, first_aid, gun_rack, jump_seat, lamp,
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
    b.add(block("signplate", (0, -7.04, 6.4), (6.4, 0.06, 1.0), "black", bevel=0.01))
    b.add(turn(label("THE ROOST", (0, -7.09, 6.4), 0.8, pale, side=-1, depth=0.03), (0, -7.09, 6.4), 90))
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
    detail(b)
    depot(b)
    return b


def detail(b):
    """The second pass: roof gear, pipework and rivets outside; trusses, banners, a pegboard and floor
    markings inside."""
    # Outside: air handlers and vents on the roof, downpipes, a conduit run, rivets on the side panels.
    for x in (-2.5, 1.0):
        b.add(block("ac", (x, 4.6, ROOF + 0.45), (2.0, 1.1, 0.9), "grey", bevel=0.03))
        b.add(cyl("acfan", (x, 4.6, ROOF + 0.9), (x, 4.6, ROOF + 0.96), 0.4, "black", segs=16, bevel=0.01))
        b.add(ring("acguard", (x, 4.6, ROOF + 0.97), (0, 0, 1), 0.42, 0.36, 0.03, "steel", segs=16))
        b.add(block("aclouvre", (x, 4.6 - 0.56, ROOF + 0.45), (1.6, 0.03, 0.5), "black", bevel=0))
        b.add(block("acfoot", (x, 4.6, ROOF + 0.03), (2.1, 1.2, 0.06), "black", bevel=0))
    for x, y in ((-4.5, 3.0), (-1.0, 1.5), (3.5, -1.5)):
        b.add(cyl("vent", (x, y, ROOF), (x, y, ROOF + 0.7), 0.13, "steel", segs=10, bevel=0.01))
        b.add(cyl("ventcap", (x, y, ROOF + 0.7), (x, y, ROOF + 0.85), 0.24, "black", r1=0.05, segs=10, bevel=0))
    for x in (-11.15, 11.15):
        b.add(cyl("downpipe", (x, 6.8, 0.1), (x, 6.8, ROOF - 0.2), 0.07, "black", segs=8, bevel=0))
        for z in (1.0, 3.0, 5.0, 7.0):
            b.add(block("bracket", (x, 6.8, z), (0.06, 0.2, 0.08), "black", bevel=0))
    pipe_run(b, [(-10.8, -7.15, 3.6), (-4.6, -7.15, 3.6), (-4.6, -7.15, 5.2), (-3.4, -7.15, 5.2)], r=0.04, material="steel")
    for x in (11.06, -11.06):
        ax = "x" if x > 0 else "-x"
        for z in (1.2, 4.6):
            b.add(rivets("rivets", (x, 0.0, z), (x, 4.0, z), 9, axis=ax))
    for i, x in enumerate((-6.0, 6.0)):
        b.add(turn(label(f"R-{i + 1}", (x, -7.03, 3.4), 0.6, orange, side=-1, depth=0.02), (x, -7.03, 3.4), 90))
    # The genset's fuel: a horizontal tank on a stand, jerry cans, a pallet, a hose reel.
    b.add(cyl("fuel", (12.1, 5.4, 0.9), (12.1, 6.8, 0.9), 0.35, "olive", segs=14, bevel=0.01))
    for y in (5.5, 6.7):
        b.add(block("fuelstand", (12.1, y, 0.35), (0.7, 0.1, 0.7), "black", bevel=0.01))
    b.add(cyl("fuelcap", (12.1, 6.1, 1.25), (12.1, 6.1, 1.33), 0.08, "brass", segs=8, bevel=0))
    for i in range(4):
        x, y = 11.5 + 0.28 * (i % 2), 0.4 + 0.3 * (i // 2)
        b.add(block("jerry", (x, y, 0.28), (0.24, 0.16, 0.5), "olive" if i % 2 else "rust", bevel=0.02))
        b.add(block("jerrycap", (x, y, 0.55), (0.08, 0.06, 0.05), "black", bevel=0))
    b.add(block("pallet", (12.3, 0.3, 0.07), (1.1, 1.1, 0.14), "tan", bevel=0.01))
    b.add(ring("reel", (11.1, 5.5, 1.4), (1, 0, 0), 0.4, 0.12, 0.06, "red", segs=18))
    b.add(ring("reelrim", (11.1, 5.5, 1.4), (1, 0, 0), 0.4, 0.3, 0.22, "red", segs=18))
    b.add(cyl("reelhub", (11.0, 5.5, 1.4), (11.35, 5.5, 1.4), 0.07, "steel", segs=8, bevel=0))
    # Inside: lattice trusses across the hangar, a hoist on the middle one, banners off the catwalk.
    for y in (-4.0, 0.0, 4.0):
        truss(b, (-10.5, y, ROOF - 0.8), (10.5, y, ROOF - 0.8), s=0.45, material="gunmetal", bay=1.5)
    for x in (-10.2, 10.2):
        for y in (-4.0, 0.0, 4.0):
            b.add(block("truss end", (x, y, ROOF - 0.8), (0.4, 0.5, 0.6), "black", bevel=0.01))
    b.add(block("hoistbeam", (-6.5, 0.0, ROOF - 1.1), (0.14, 6.0, 0.16), "steel", bevel=0.006))
    b.add(block("trolley", (-6.5, -0.8, ROOF - 1.25), (0.3, 0.26, 0.14), "black", bevel=0.01))
    b.add(chain("chain", (-6.5, -0.8, ROOF - 1.3), (-6.5, -0.8, 5.2), links=18, r=0.025))
    b.add(ring("hook", (-6.5, -0.74, 5.05), (1, 0, 0), 0.08, 0.05, 0.035, "steel", segs=12))
    for x, m in ((-6.0, orange), (6.0, "olive")):
        b.add(block("banner", (x, 4.18, 2.6), (1.5, 0.04, 2.6), m, bevel=0.01))
        b.add(block("bannerrod", (x, 4.18, 3.95), (1.7, 0.06, 0.06), "black", bevel=0))
        b.add(block("bannerbadge", (x, 4.15, 2.9), (0.8, 0.02, 0.8), pale, bevel=0.01))
        b.add(block("bannerbar", (x, 4.14, 2.9), (0.5, 0.02, 0.14), "black", bevel=0))
        b.add(block("bannerbar", (x, 4.14, 2.9), (0.14, 0.02, 0.5), "black", bevel=0))
    # A notice board by the side door, a pegboard of tools over the benches, a radio and a vice.
    b.add(block("board", (10.6, -5.5, FLOOR + 1.9), (0.06, 1.3, 0.9), "canvas", bevel=0.01))
    for y, z in ((-5.9, 2.0), (-5.5, 1.8), (-5.1, 2.1), (-5.6, 2.35)):
        b.add(block("notice", (10.56, y, FLOOR + z), (0.01, 0.26, 0.32), pale, bevel=0))
        b.add(cyl("pin", (10.56, y, FLOOR + z + 0.13), (10.53, y, FLOOR + z + 0.13), 0.02, "red", segs=6, bevel=0))
    b.add(block("pegboard", (10.62, 3.2, FLOOR + 2.0), (0.05, 3.2, 0.9), "black", bevel=0))
    for i in range(8):
        y = 1.8 + 0.4 * i
        z = FLOOR + 1.8 + 0.25 * (i % 3)
        if i % 2:
            b.add(block("wrench", (10.57, y, z), (0.02, 0.05, 0.3), "steel", bevel=0))
            b.add(ring("wrenchhead", (10.57, y, z + 0.17), (1, 0, 0), 0.07, 0.035, 0.02, "steel", segs=8))
        else:
            b.add(block("hammerstem", (10.57, y, z), (0.02, 0.04, 0.32), "tan", bevel=0))
            b.add(block("hammerhead", (10.57, y, z + 0.18), (0.04, 0.05, 0.1), "steel", bevel=0.005))
    b.add(block("radio", (8.7, 4.2, FLOOR + 1.04), (0.5, 0.3, 0.24), "olive", bevel=0.015))
    b.add(block("radioscreen", (8.44, 4.2, FLOOR + 1.08), (0.02, 0.2, 0.08), "screen", bevel=0), "lights")
    b.add(cyl("radiomast", (8.9, 4.3, FLOOR + 1.16), (8.9, 4.3, FLOOR + 1.9), 0.012, "black", segs=6, bevel=0))
    b.add(block("vice", (8.6, 1.0, FLOOR + 0.99), (0.2, 0.18, 0.18), "black", bevel=0.01))
    # Floor: painted lines round the planning table and the door threshold, a drain grate.
    for p, s in (((0, -1.0, 2.1), (3.4, 0.08, 0.1)), ((0, 2.0, 2.1), (3.4, 0.08, 0.1)),
                 ((-1.7, 0.5, 2.1), (0.08, 3.0, 0.1)), ((1.7, 0.5, 2.1), (0.08, 3.0, 0.1))):
        b.add(stripe("line", (p[0], p[1], FLOOR + 0.012), (s[0], s[1], 0.012), orange))
    b.add(stripe("threshold", (0, -6.5, FLOOR + 0.012), (8.0, 0.2, 0.012), orange))
    grating(b, (-6.0, -2.0, FLOOR + 0.02), (1.2, 0.8))


DEPOT = ((-10.0, -13.5), (8.0, 5.0, 3.2))
DEPOT_DOORS = [("+x", 0.0, 1.4, 2.4)]


def depot(b):
    """The quartermaster's depot in the front yard beside the bay door: a counter with a terminal,
    gun racks and ammunition stacked behind it, a medic's cot and the first-aid box. Resupply here."""
    (x, y), s = DEPOT
    z0 = 0.15
    room(b, "depot", (x, y), s, dark, DEPOT_DOORS, trim=pale)
    band(b, (x, y, 0), (s[0], s[1], 0), 2.7, 0.3, orange, front_gap=0.0)
    b.add(turn(label("SUPPLY", (x, y - s[1] / 2 - 0.03, 2.95), 0.6, pale, side=-1, depth=0.03), (x, y - s[1] / 2 - 0.03, 2.95), 90))
    xe = x + s[0] / 2
    b.add(block("cross", (xe + 0.02, y - 2.0, 2.0), (0.06, 0.8, 0.26), "red", bevel=0))
    b.add(block("cross", (xe + 0.02, y - 2.0, 2.0), (0.06, 0.26, 0.8), "red", bevel=0))
    b.add(crate("crate", (xe + 0.7, y + 1.4, 0.5), (1.0, 0.8, 0.8), material=orange))
    b.add(barrel("drum", (xe + 0.5, y - 1.7, 0.1), r=0.3, h=0.9, material="rust"))
    # The counter and its terminal.
    b.add(block("counter", (x + 0.9, y + 0.1, z0 + 0.55), (0.7, 3.4, 1.1), dark, bevel=0.02))
    b.add(block("countertop", (x + 0.9, y + 0.1, z0 + 1.12), (0.9, 3.6, 0.05), "steel", bevel=0.01))
    b.add(block("termbody", (x + 0.9, y - 0.8, z0 + 1.3), (0.35, 0.5, 0.3), "black", bevel=0.01))
    b.add(block("termscreen", (x + 1.07, y - 0.8, z0 + 1.32), (0.02, 0.42, 0.22), "screen", bevel=0), "lights")
    b.add(cyl("stamp", (x + 0.9, y + 1.0, z0 + 1.15), (x + 0.9, y + 1.0, z0 + 1.3), 0.06, "brass", segs=8, bevel=0))
    # Behind it: racks on the south wall, ammunition on the north, the cot in the west corner.
    for gx in (x - 2.6, x - 0.6):
        b.add(gun_rack("rack", (gx, y - 2.3, z0), facing=1, n=4, material="gunmetal"))
    for i, cx in enumerate((x - 3.0, x - 1.8, x - 0.6)):
        b.add(crate("ammo", (cx, y + 2.0, z0 + 0.3), (1.0, 0.7, 0.6), material="olive" if i != 1 else orange))
    b.add(crate("ammo", (x - 1.8, y + 2.0, z0 + 0.9), (0.8, 0.6, 0.5), material=tan))
    b.add(bunk("cot", (x - 3.2, y - 0.3, z0 + 0.5), (0.9, 2.0, 0.15), material="olive", wall=-1))
    b.add(first_aid("aid", (x - 1.4, y + s[1] / 2 - 0.2, z0 + 1.6), facing=-1))
    b.add(extinguisher("ext", (x + 3.1, y + 2.0, z0 + 0.3), wall=1))
    lamp(b, "lamp.6", (x, y, s[2] - 0.17), rim="black", r=0.18, cage=True)


SPEC = {
    "build": build,
    "name": "The Roost",
    "color": (0.3, 1.0, 0.5),
    "faction": "deserters",
    "body": "home",
    "near_pad": (70.0, 85.0),
    "yaw": 180.0,
    "footprint": (28.0, 25.0),
    "footprint_at": (-1.0, -4.0),
    "door": (0.0, -6.85, 1.2),
    "size": (23.7, 27.0, 18.0),
    "depth": 0.3,
    "nodes": ["lamp.0", "lamp.1", "lamp.2", "lamp.3", "lamp.4", "lamp.5", "lamp.6", "flood.0", "flood.1"],
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
        *room_boxes("depot", DEPOT[0], DEPOT[1], DEPOT_DOORS),
        box("depot counter", (DEPOT[0][0] + 0.9, DEPOT[0][1] + 0.1, 0.7), (0.7, 3.4, 1.1)),
    ],
    "stations": [
        ("resupply", (DEPOT[0][0] + 2.0, DEPOT[0][1], 1.15), "Quartermaster"),
        ("locker", (5.7, -6.0, FLOOR + 1.0), "Locker"),
    ],
    "view": {"cam": (-24.0, -30.0, 14.0), "look": (0, 0, 4.0), "lens": 35},
    "annex": {"cam": (-6.6, -15.3, 2.0), "look": (-11.5, -12.8, 1.2), "lens": 22},
    "annex_out": {"cam": (-22.0, -27.0, 5.0), "look": (-10.0, -13.5, 1.5), "lens": 30},
    "inside": {"cam": (0.5, -9.5, FLOOR + 1.6), "look": (0, 2.0, FLOOR + 1.8), "lens": 22},
}
