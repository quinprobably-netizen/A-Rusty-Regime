"""The PMC's Site Vantage on Frost: three white hab modules on jack legs joined by a short link
corridor each, an airlock vestibule with steps down to the ice, a radar dish, a radio mast,
floodlights, radiator panels and blue running strips. Gunmetal and white. Inside: the ops module
with a two-seat desk under a bank of screens and server racks, the quarters with bunks and
lockers, the armoury with gun cages, crates and a hatch."""

from basekit import Base, band, box, dish, door_frame, floodlight, hall, mast, railing, slab, slope, stair, tank, window
from kit import block, cyl, label, seams, stripe
from interior import (bucket_seat, bunk, cabinet, cable_bundle, crate, dash, duct, extinguisher, first_aid, gas_bottle, gun_rack, hatch, lamp,
                      overhead, server_rack, turn, wall_panels)

JACK = 1.2          # the modules stand this high over the ice
WALL = 0.15
FLOOR = JACK + WALL
H = 3.0
white, gm, blue = "ice_white", "gunmetal", "blue_light"

A = ((0.0, 6.0), (10.0, 5.0))      # ops: centre (x, y), size (x, y)
B = ((-8.0, 0.0), (5.0, 10.0))     # quarters
Cm = ((8.0, 0.0), (5.0, 10.0))     # armoury
V = ((0.0, 2.0), (3.0, 3.2))       # vestibule
LW = ((-4.25, 4.0), (3.5, 2.2))    # west link
LE = ((4.25, 4.0), (3.5, 2.2))     # east link


def module(b, name, m, openings, strips=True):
    (x, y), (sx, sy) = m
    hall(b, name, (x, y, JACK + H / 2), (sx, sy, H), white, wall=WALL, openings=openings, bevel=0.04)
    seams(b, (x, y, JACK + H / 2), (sx, sy, H), ys=tuple(-sy / 2 + 1.0 + i * 2.0 for i in range(int(sy / 2))), xs=(), material=gm, width=0.04, proud=0.012)
    band(b, (x, y, 0), (sx, sy, 0), JACK + 0.35, 0.5, gm)
    if strips:
        band(b, (x, y, 0), (sx, sy, 0), JACK + H - 0.25, 0.06, blue, proud=0.02)
    for ax in (-1, 1):
        for ay in (-1, 1):
            lx, ly = x + ax * (sx / 2 - 0.5), y + ay * (sy / 2 - 0.5)
            b.add(cyl("jack", (lx, ly, 0.1), (lx, ly, JACK + 0.1), 0.12, gm, segs=10, bevel=0.005))
            b.add(cyl("jackfoot", (lx, ly, 0), (lx, ly, 0.12), 0.4, gm, segs=12, bevel=0.01))
    for sx_ in (-1, 1):
        b.add(block("skid", (x + sx_ * (sx / 2 - 0.5), y, JACK - 0.08), (0.3, sy - 0.6, 0.16), gm, bevel=0.01))


def build():
    b = Base("outpost")
    slab(b, "plinth", (0, 1.0, -0.15), (26.0, 20.0, 0.3), "concrete", bevel=0.02)
    # The modules and what joins them.
    module(b, "ops", A, [("-y", 0, 1.6, 2.2, 0), ("-x", -2.0, 1.6, 2.2, 0), ("+x", -2.0, 1.6, 2.2, 0), ("+y", -3.0, 2.0, 0.8, 1.4), ("+y", 3.0, 2.0, 0.8, 1.4)])
    module(b, "quarters", B, [("+x", 4.0, 1.6, 2.2, 0), ("-x", -2.0, 1.2, 0.6, 1.5), ("-x", 2.0, 1.2, 0.6, 1.5)])
    module(b, "armoury", Cm, [("-x", 4.0, 1.6, 2.2, 0), ("+x", 0.0, 1.2, 0.6, 1.5)])
    for name, m in (("westlink", LW), ("eastlink", LE)):
        (x, y), (sx, sy) = m
        hall(b, name, (x, y, JACK + 1.3), (sx, sy, 2.6), gm, wall=0.12, openings=[("-x", 0, 1.6, 2.2, 0), ("+x", 0, 1.6, 2.2, 0)], bevel=0.03)
        band(b, (x, y, 0), (sx, sy, 0), JACK + 2.2, 0.06, blue, proud=0.02)
    (vx, vy), (vsx, vsy) = V
    hall(b, "vestibule", (vx, vy, JACK + H / 2), (vsx, vsy, H), gm, wall=WALL, openings=[("+y", 0, 1.6, 2.2, 0), ("-y", 0, 1.6, 2.2, 0)], bevel=0.04)
    door_frame(b, (0, 0.4, FLOOR), 1.6, 2.2, material=white, depth=0.5, thick=0.15)
    for sx in (-1, 1):
        b.add(stripe("chev", (sx * 1.0, 0.33, FLOOR + 1.1), (0.2, 0.04, 2.2), "hazard"))
    b.add(turn(label("VANTAGE SEC", (0, 0.32, FLOOR + 2.75), 0.26, blue, side=-1, depth=0.015), (0, 0.32, FLOOR + 2.75), 90))
    b.add(turn(label("SITE 4", (-5.5, -5.1, JACK + 2.2), 0.4, gm, side=-1, depth=0.015), (-5.5, -5.1, JACK + 2.2), 90))
    stair(b, (0, -2.0, 0), 1.8, 2.4, FLOOR, 6, material=gm, facing=1)
    railing(b, (-0.95, -2.0, 0), (-0.95, 0.4, FLOOR), spacing=1.2)
    railing(b, (0.95, -2.0, 0), (0.95, 0.4, FLOOR), spacing=1.2)
    for x in (-3.0, 3.0):
        window(b, (x, 8.5, FLOOR + 1.8), (2.0, 0.1, 0.8), frame=gm)
    for y in (-2.0, 2.0):
        window(b, (-10.5, y, FLOOR + 1.8), (0.1, 1.2, 0.6), frame=gm)
    window(b, (10.5, 0.0, FLOOR + 1.8), (0.1, 1.2, 0.6), frame=gm)
    # On the roofs: radiators, the dish, the mast, a tank, floodlights on the pad side.
    for i in range(4):
        b.add(block("radiator", (-3.6 + i * 2.4, 6.0, JACK + H + 0.5), (0.08, 3.6, 0.9), white, bevel=0.01))
        b.add(block("radiatorfoot", (-3.6 + i * 2.4, 6.0, JACK + H + 0.05), (0.3, 3.8, 0.1), gm, bevel=0.005))
    dish(b, (8.0, -2.5, JACK + H), 1.6, 1.2, material=white, facing=-1)
    mast(b, (-8.0, 3.5, JACK + H), 7.0, r=0.06, light="red_light")
    tank(b, (12.0, 4.0, 1.0), 1.0, 2.4, material=white, band=blue)
    b.add(cyl("tankpipe", (11.0, 4.0, 1.4), (10.5, 4.0, 1.4), 0.05, gm, segs=8, bevel=0))
    floodlight(b, "flood.0", (-11.5, -4.0, 0), 5.0, aim=(0, -1))
    floodlight(b, "flood.1", (11.5, -4.0, 0), 5.0, aim=(0, -1))
    b.add(crate("pallet", (-5.0, -5.0, 0.5), (1.4, 1.2, 1.0), material="grey", band="black"))
    b.add(crate("pallet", (-5.0, -5.0, 1.35), (1.1, 0.9, 0.7), material=white, band=blue))
    for i, x in enumerate((5.0, 5.4, 5.8)):
        b.add(gas_bottle("gas", (x, -5.2, 0), material=white if i != 1 else "red"))
    # Ops: the desk under its screens, two seats, racks and an overhead panel.
    (ax, ay), (asx, asy) = A
    b.add(block("opsfloor", (ax, ay, FLOOR + 0.01), (asx - 0.4, asy - 0.4, 0.02), gm, bevel=0))
    wall_panels(b, ax + asx / 2 - WALL, ay - 1.5, ay + 2.3, FLOOR + 0.2, FLOOR + 2.5, white, n=2)
    dash(b, (ax, ay + 1.6, FLOOR), 3.4, material=white, screens=5, screen_mat=blue, facing=1)
    for x in (-0.7, 0.7):
        b.add(bucket_seat("seat", (ax + x, ay + 0.6, FLOOR + 0.5), facing=1, material="black", frame=white, trim="steel"))
    overhead(b, (ax, ay + 1.0, FLOOR + 2.7), (1.8, 0.5, 0.06), material=white, facing=1, light_mat=blue)
    for x in (-3.8, -3.1):
        server_rack(b, (ax + x, ay + 1.5, FLOOR + 0.95), (0.6, 0.5, 1.9), material=white)
    c = (ax + 3.9, ay + 1.2, FLOOR + 0.95)
    b.add(turn(cabinet("locker", c, (0.6, 0.5, 1.9), material=white, doors=1), c, 90))
    b.add(duct("duct", (ax - 4.5, ay - 1.8, FLOOR + 2.65), (ax + 4.5, ay - 1.8, FLOOR + 2.65), (0, 0.4, 0.2), material=gm, flange=1.5))
    b.add(cable_bundle("cables", [(ax - 4.5, ay + 2.2, FLOOR + 2.6), (ax - 1.0, ay + 2.2, FLOOR + 2.5), (ax + 3.0, ay + 2.2, FLOOR + 2.6)], material="black"))
    for i, x in enumerate((-2.5, 2.5)):
        lamp(b, f"lamp.{i}", (ax + x, ay, FLOOR + 2.68), rim=white, r=0.18)
    b.add(first_aid("aid", (ax - 2.0, ay - 2.3, FLOOR + 1.5), facing=1))
    lamp(b, "lamp.6", (vx, vy, FLOOR + 2.68), rim=gm, r=0.14)
    # Quarters: four bunks, lockers, a lamp each end.
    (bx, by), (bsx, bsy) = B
    b.add(block("qfloor", (bx, by, FLOOR + 0.01), (bsx - 0.4, bsy - 0.4, 0.02), gm, bevel=0))
    for y in (-3.0, 2.0):
        for z in (0.45, 1.45):
            b.add(bunk("bunk", (bx - 1.6, y, FLOOR + z), (0.9, 2.0, 0.15), material="grey", wall=-1))
    for i, y in enumerate((-4.0, -3.4, 3.6, 4.2)):
        c = (bx + 2.0, y, FLOOR + 0.95)
        b.add(turn(cabinet("locker", c, (0.55, 0.5, 1.9), material=white, doors=1), c, -90))
    b.add(block("qtable", (bx + 1.2, by, FLOOR + 0.75), (1.0, 1.6, 0.05), white, bevel=0.01))
    b.add(cyl("qtableleg", (bx + 1.2, by, FLOOR), (bx + 1.2, by, FLOOR + 0.73), 0.06, gm, segs=8, bevel=0))
    for i, y in enumerate((-3.0, 2.0)):
        lamp(b, f"lamp.{2 + i}", (bx, y, FLOOR + 2.68), rim=white, r=0.18)
    b.add(extinguisher("ext", (bx + 2.3, 0.5, FLOOR + 0.3), wall=1))
    # Armoury: gun cages, crates, a hatch in the end wall, a lamp each end.
    (cx, cy), (csx, csy) = Cm
    b.add(block("afloor", (cx, cy, FLOOR + 0.01), (csx - 0.4, csy - 0.4, 0.02), gm, bevel=0))
    for y in (-3.5, -1.0, 1.5):
        c = (cx + 2.2, y, FLOOR)
        b.add(turn(gun_rack("cage", c, facing=1, n=4, material=white), c, 90))
    b.add(crate("acrate", (cx - 1.5, -3.5, FLOOR + 0.45), (1.0, 1.4, 0.9), material="grey", band=blue))
    b.add(crate("acrate", (cx - 1.5, -3.5, FLOOR + 1.25), (0.8, 1.0, 0.7), material=white))
    b.add(crate("acrate", (cx - 1.5, 3.5, FLOOR + 0.45), (1.0, 1.2, 0.9), material="grey"))
    c = (cx - 2.2, 0.5, FLOOR + 0.95)
    b.add(turn(cabinet("cabinet", c, (0.8, 0.5, 1.9), material=white, doors=2), c, -90))
    b.add(turn(hatch("hatch", (cx, cy + csy / 2 - WALL, FLOOR + 1.4), facing=1, r=0.4, material=gm), (cx, cy + csy / 2 - WALL, FLOOR + 1.4), 0))
    for i, y in enumerate((-3.0, 2.0)):
        lamp(b, f"lamp.{4 + i}", (cx, y, FLOOR + 2.68), rim=white, r=0.18)
    return b


def _module_boxes(name, m, gaps):
    """Floor, roof and walls of a module; `gaps` are (face, offset, width) doorways to leave open."""
    (x, y), (sx, sy) = m
    out = [box(f"{name} floor", (x, y, JACK + WALL / 2), (sx, sy, WALL)), box(f"{name} roof", (x, y, JACK + H - WALL / 2), (sx, sy, WALL))]
    for face, (fx, fy) in (("-y", (0, -1)), ("+y", (0, 1)), ("-x", (-1, 0)), ("+x", (1, 0))):
        length = sx if fy else sy
        gap = next(((off, w) for f, off, w in gaps if f == face), None)
        if gap is None:
            segs = [(0.0, length)]
        else:
            off, w = gap
            segs = [(-length / 2 + (off - w / 2 + length / 2) / 2, off - w / 2 + length / 2), ((off + w / 2 + length / 2) / 2, length / 2 - (off + w / 2))]
            out.append(box(f"{name} lintel", (x + (off if fy else fx * (sx / 2 - WALL / 2)), y + (fy * (sy / 2 - WALL / 2) if fy else off), JACK + WALL + 2.2 + (H - WALL - 2.2 - WALL) / 2), ((w, WALL, H - WALL - 2.2 - WALL) if fy else (WALL, w, H - WALL - 2.2 - WALL))))
        for centre, size in segs:
            if size <= 0.01:
                continue
            if fy:
                out.append(box(f"{name} wall", (x + centre, y + fy * (sy / 2 - WALL / 2), JACK + H / 2), (size, WALL, H)))
            else:
                out.append(box(f"{name} wall", (x + fx * (sx / 2 - WALL / 2), y + centre, JACK + H / 2), (WALL, size, H)))
    return out


SPEC = {
    "build": build,
    "name": "Site Vantage",
    "faction": "pmc",
    "body": "frost",
    "lat": 24.0,
    "lon": 200.0,
    "footprint": (26.0, 20.0),
    "pad": (0.0, -24.0),
    "door": (0.0, 0.4, FLOOR + 1.1),
    "size": (20.0, 26.0, 11.2),
    "depth": 0.3,
    "nodes": [f"lamp.{i}" for i in range(7)] + ["flood.0", "flood.1"],
    "boxes": [
        *_module_boxes("ops", A, [("-y", 0.0, 1.6), ("-x", -2.0, 1.6), ("+x", -2.0, 1.6)]),
        *_module_boxes("quarters", B, [("+x", 4.0, 1.6)]),
        *_module_boxes("armoury", Cm, [("-x", 4.0, 1.6)]),
        *_module_boxes("west link", LW, [("-x", 0.0, 1.6), ("+x", 0.0, 1.6)]),
        *_module_boxes("east link", LE, [("-x", 0.0, 1.6), ("+x", 0.0, 1.6)]),
        *_module_boxes("vestibule", V, [("-y", 0.0, 1.6), ("+y", 0.0, 1.6)]),
        slope((0, -2.0, 0), 1.8, 2.4, FLOOR, 1),
        box("desk", (A[0][0], A[0][1] + 1.6, FLOOR + 0.5), (3.4, 0.7, 1.0)),
        box("tank", (12.0, 4.0, 2.2), (2.0, 2.0, 2.8)),
        box("pallet", (-5.0, -5.0, 0.5), (1.4, 1.2, 1.0)),
    ],
    "view": {"cam": (-26.0, -28.0, 12.0), "look": (0, 2.0, 2.0), "lens": 35},
    "inside": {"cam": (0.0, -0.6, FLOOR + 1.6), "look": (0, 8.0, FLOOR + 1.3), "lens": 24},
}
