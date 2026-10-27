"""The Regime's Reliquary on Bastion: a slate basilica on a podium up a flight of steps. A 30 m
nave with a pitched roof and a bell tower and spire over the door, two side chapels making the
cross, an apse, buttresses with gold ribs, red slit windows, bone statues flanking the steps and
braziers at the great door. Inside: bone columns, pews either side of a red aisle, a font, the
dais with the altar, candelabra and the throne, censers swinging over the aisle."""

from basekit import Base, band, box, column, door_frame, hall, slab, slope, stair, window
from kit import block, cyl, label, prism, sphere, stripe
from interior import altar, candelabra, censer, font, lamp, pew, turn, wall_panels

FLOOR = 1.2
CEIL = 14.2
slate, bone, gold = "slate", "bone", "gold"


def build():
    b = Base("reliquary")
    # The podium and its steps, the nave with the great door, the chapel arches and slit windows.
    slab(b, "podium", (0, 3.2, 0.6), (18.0, 33.6, 1.2), "concrete", bevel=0.04)
    slab(b, "plinth", (0, 2.0, -0.15), (20.0, 40.0, 0.3), "concrete", bevel=0.02)
    stair(b, (0, -16.0, 0), 8.0, 2.4, 1.2, 4, material="concrete", facing=1, stringers=False)
    nave_openings = [("-y", 0, 4.0, 7.0, 0), ("-x", 4.0, 4.0, 6.0, 0), ("+x", 4.0, 4.0, 6.0, 0)]
    for y in (-10.0, -6.0, -2.0, 10.0, 14.0):
        nave_openings += [("-x", y - 2.0, 0.6, 5.0, 6.0), ("+x", y - 2.0, 0.6, 5.0, 6.0)]
    hall(b, "nave", (0, 2.0, 7.7), (14.0, 30.0, 14.0), slate, wall=0.5, openings=nave_openings, bevel=0.08)
    for sx in (-1, 1):
        hall(b, "chapel", (sx * 10.0, 6.0, 6.2), (8.0, 8.0, 11.0), slate, wall=0.5, openings=[("-x" if sx > 0 else "+x", 0, 4.0, 6.0, 0), ("-y", 0, 0.6, 4.0, 4.0), ("+y", 0, 0.6, 4.0, 4.0)], bevel=0.08)
        for y in (2.0, 10.0):
            window(b, (sx * 10.0, y, FLOOR + 6.0), (0.6, 0.1, 4.0), frame=gold, glass="red_glass")
        band(b, (sx * 10.0, 6.0, 0), (8.0, 8.0, 0), 11.0, 0.3, gold)
        band(b, (sx * 10.0, 6.0, 0), (8.0, 8.0, 0), FLOOR + 0.3, 0.6, bone)
    for y in (-10.0, -6.0, -2.0, 10.0, 14.0):
        for sx in (-1, 1):
            window(b, (sx * 7.0, y - 2.0, FLOOR + 8.5), (0.1, 0.6, 5.0), frame=gold, glass="red_glass")
    # Gold ribs round the nave, a bone dado, buttresses between the windows.
    for z in (5.5, 10.5, 14.4):
        band(b, (0, 2.0, 0), (14.0, 30.0, 0), z, 0.25, gold)
    band(b, (0, 2.0, 0), (14.0, 30.0, 0), FLOOR + 0.3, 0.6, bone)
    for y in (-10.0, -4.0, 12.0, 16.0):
        for sx in (-1, 1):
            b.add(block("buttress", (sx * 7.7, y, 5.0), (1.4, 1.0, 10.0), bone, bevel=0.04, taper=(0.3, 1.0)))
            b.add(block("buttresscap", (sx * 7.5, y, 10.1), (1.0, 1.1, 0.3), gold, bevel=0.02))
    # The apse behind the altar, the pitched roof, the tower and spire over the door.
    b.add(block("apse", (0, 18.5, 7.7), (9.0, 3.0, 13.0), slate, bevel=0.1, segs=3, taper=(0.9, 0.6)))
    b.add(block("apseroof", (0, 18.3, 14.4), (9.4, 3.4, 0.4), bone, bevel=0.05))
    b.add(turn(prism("roof", [(-7.6, 14.4), (0, 18.4), (7.6, 14.4)], 30.0, slate, x=2.0, bevel=0.05), (0, 0, 0), 90))
    b.add(block("ridge", (0, 2.0, 18.4), (0.4, 30.4, 0.25), gold, bevel=0.02))
    for y in (-8.0, 0.0, 8.0):
        b.add(turn(prism("rooftrim", [(-7.8, 14.3), (0, 18.5), (7.8, 14.3), (7.8, 14.1), (0, 18.2), (-7.8, 14.1)], 0.3, gold, x=y, bevel=0.01), (0, 0, 0), 90))
    b.add(block("tower", (0, -10.0, 19.7), (6.0, 6.0, 10.0), slate, bevel=0.08, segs=3))
    band(b, (0, -10.0, 0), (6.0, 6.0, 0), 24.5, 0.3, gold)
    band(b, (0, -10.0, 0), (6.0, 6.0, 0), 15.0, 0.4, bone)
    for sx in (-1, 1):
        window(b, (sx * 3.0, -10.0, 21.0), (0.1, 1.0, 4.0), frame=gold, glass="red_glass", bars=1)
    window(b, (0, -13.0, 21.0), (1.0, 0.1, 4.0), frame=gold, glass="red_glass", bars=1)
    b.add(cyl("bell", (0, -10.0, 23.0), (0, -10.0, 22.2), 0.5, "brass", r1=0.75, segs=16, bevel=0.01))
    b.add(cyl("spire", (0, -10.0, 24.7), (0, -10.0, 33.5), 3.2, slate, r1=0.08, segs=8, bevel=0.02))
    for i in range(4):
        b.add(stripe("spirerib", (0, -10.0, 26.0), (0.12, 0.12, 2.5), gold))
    b.add(cyl("finial", (0, -10.0, 33.4), (0, -10.0, 34.6), 0.08, gold, segs=8, bevel=0))
    b.add(sphere("orb", (0, -10.0, 34.3), 0.3, gold, segs=12))
    # The great door: gold frame, a bone tympanum with the name, braziers, and statues on
    # plinths flanking the steps.
    door_frame(b, (0, -13.0, FLOOR), 4.0, 7.0, material=gold, depth=0.9, thick=0.35)
    b.add(block("tympanum", (0, -13.3, FLOOR + 8.3), (5.2, 0.3, 1.6), bone, bevel=0.03))
    b.add(turn(label("THE ALGORITHM PROVIDES", (0, -13.46, FLOOR + 8.3), 0.32, gold, side=-1, depth=0.02), (0, -13.46, FLOOR + 8.3), 90))
    for sx in (-1, 1):
        b.add(cyl("brazier", (sx * 3.2, -14.2, FLOOR), (sx * 3.2, -14.2, FLOOR + 1.0), 0.12, gold, segs=10, bevel=0))
        b.add(cyl("bowl", (sx * 3.2, -14.2, FLOOR + 1.0), (sx * 3.2, -14.2, FLOOR + 1.35), 0.25, gold, r1=0.45, segs=14, bevel=0.01))
        b.add(sphere("flame", (sx * 3.2, -14.2, FLOOR + 1.45), 0.2, "gold_light", segs=10), "lights")
        b.node(f"lamp.{4 if sx < 0 else 5}", (sx * 3.2, -14.2, FLOOR + 1.9))
        b.add(block("statueplinth", (sx * 6.0, -15.5, 0.8), (1.4, 1.4, 1.6), bone, bevel=0.03))
        b.add(cyl("robe", (sx * 6.0, -15.5, 1.6), (sx * 6.0, -15.5, 4.4), 0.45, bone, r1=0.28, segs=14, bevel=0.01))
        b.add(sphere("hood", (sx * 6.0, -15.5, 4.6), 0.32, bone, segs=12))
        b.add(cyl("staff", (sx * 6.0 + sx * 0.5, -15.9, 1.6), (sx * 6.0 + sx * 0.5, -15.9, 5.4), 0.04, gold, segs=6, bevel=0))
    # Inside: the nave. Bone columns down each side, pews either side of a red runner, the
    # font by the door, the dais with the altar, candelabra and the throne; censers overhead.
    b.add(block("floorplate", (0, 2.0, FLOOR + 0.01), (13.0, 29.0, 0.02), bone, bevel=0))
    b.add(block("runner", (0, 0.5, FLOOR + 0.025), (2.4, 24.0, 0.03), "red", bevel=0))
    for y in (-8.0, -4.0, 0.0, 4.0, 8.0, 12.0):
        for sx in (-1, 1):
            column(b, (sx * 5.6, y, FLOOR), 0.45, CEIL - FLOOR)
    wall_panels(b, -6.5, -12.4, 16.4, FLOOR + 0.9, FLOOR + 4.9, bone, n=8, bolt_mat=gold)
    wall_panels(b, 6.5, -12.4, 16.4, FLOOR + 0.9, FLOOR + 4.9, bone, n=8, bolt_mat=gold)
    for i in range(7):
        y = -9.0 + i * 2.5
        for sx in (-1, 1):
            b.add(pew("pew", (sx * 3.2, y, FLOOR + 0.45), w=2.6, facing=1))
    b.add(font("font", (0, -10.5, FLOOR)))
    slab(b, "dais", (0, 13.0, FLOOR + 0.15), (8.0, 5.0, 0.3), bone, bevel=0.02)
    slab(b, "daisstep", (0, 10.3, FLOOR + 0.075), (8.0, 0.6, 0.15), bone, bevel=0.01)
    altar(b, (0, 13.5, FLOOR + 0.3), (2.4, 1.0, 1.1))
    for x, y in ((-2.6, 11.8), (2.6, 11.8), (-2.6, 15.0), (2.6, 15.0)):
        candelabra(b, (x, y, FLOOR + 0.3), arms=5, h=1.6)
    b.add(block("throne", (0, 15.8, FLOOR + 0.85), (1.0, 0.8, 0.5), "leather", bevel=0.04, segs=3))
    b.add(block("throneback", (0, 16.15, FLOOR + 1.8), (1.1, 0.12, 2.4), gold, bevel=0.03))
    b.add(block("thronecap", (0, 16.15, FLOOR + 3.1), (1.4, 0.2, 0.3), gold, bevel=0.03))
    for i, y in enumerate((-6.0, 2.0, 10.0)):
        censer(b, (0, y, CEIL), 9.0)
        b.node(f"lamp.{i}", (0, y, CEIL - 9.6))
    b.node("lamp.3", (0, 13.5, FLOOR + 2.5))
    for sx in (-1, 1):
        lamp(b, f"lamp.{6 if sx < 0 else 7}", (sx * 10.0, 6.0, FLOOR + 9.9), material="gold_light", rim=gold, r=0.3)
        b.add(block("chapelaltar", (sx * 12.5, 6.0, FLOOR + 0.5), (1.0, 2.0, 1.0), bone, bevel=0.03))
        candelabra(b, (sx * 11.5, 4.5, FLOOR), arms=3, h=1.3)
        candelabra(b, (sx * 11.5, 7.5, FLOOR), arms=3, h=1.3)
    return b


_NAVE_WALL = [box(n, c, s) for n, c, s in (
    ("west wall", (-6.75, -5.5, 7.7), (0.5, 15.0, 14.0)), ("west wall", (-6.75, 3.0, 7.7), (0.5, 2.0, 14.0)), ("west wall", (-6.75, 12.5, 7.7), (0.5, 9.0, 14.0)),
    ("west arch", (-6.75, 6.0, 10.95), (0.5, 4.0, 7.5)),
    ("east wall", (6.75, -5.5, 7.7), (0.5, 15.0, 14.0)), ("east wall", (6.75, 3.0, 7.7), (0.5, 2.0, 14.0)), ("east wall", (6.75, 12.5, 7.7), (0.5, 9.0, 14.0)),
    ("east arch", (6.75, 6.0, 10.95), (0.5, 4.0, 7.5)),
)]

SPEC = {
    "build": build,
    "name": "The Reliquary",
    "faction": "regime",
    "body": "bastion",
    "lat": 18.0,
    "lon": -35.0,
    "footprint": (22.0, 42.0),
    "pad": (0.0, -36.0),
    "door": (0.0, -12.75, FLOOR + 1.3),
    "size": (40.0, 28.0, 34.9),
    "depth": 0.3,
    "nodes": [f"lamp.{i}" for i in range(8)],
    "boxes": [
        box("podium", (0, 3.2, 0.6), (18.0, 33.6, 1.2)),
        slope((0, -16.0, 0), 8.0, 2.4, 1.2, 1),
        box("nave floor", (0, 2.0, 0.95), (14.0, 30.0, 0.5)),
        box("nave roof", (0, 2.0, 14.45), (14.0, 30.0, 0.5)),
        box("front wall", (-4.5, -12.75, 7.7), (5.0, 0.5, 14.0)),
        box("front wall", (4.5, -12.75, 7.7), (5.0, 0.5, 14.0)),
        box("door lintel", (0, -12.75, 11.45), (4.0, 0.5, 6.5)),
        box("back wall", (0, 16.75, 7.7), (14.0, 0.5, 14.0)),
        *_NAVE_WALL,
        *[box(n, c, s) for sx in (-1, 1) for n, c, s in (
            ("chapel floor", (sx * 10.0, 6.0, 0.95), (8.0, 8.0, 0.5)), ("chapel roof", (sx * 10.0, 6.0, 11.45), (8.0, 8.0, 0.5)),
            ("chapel wall", (sx * 13.75, 6.0, 6.2), (0.5, 8.0, 11.0)), ("chapel wall", (sx * 10.0, 2.25, 6.2), (8.0, 0.5, 11.0)), ("chapel wall", (sx * 10.0, 9.75, 6.2), (8.0, 0.5, 11.0)),
            ("chapel altar", (sx * 12.5, 6.0, FLOOR + 0.5), (1.0, 2.0, 1.0)))],
        box("dais", (0, 13.0, FLOOR + 0.15), (8.0, 5.0, 0.3)),
        box("altar", (0, 13.5, FLOOR + 0.85), (2.4, 1.0, 1.1)),
        box("font", (0, -10.5, FLOOR + 0.5), (0.8, 0.8, 1.0)),
        box("roof slope", (-3.8, 2.0, 16.4), (8.6, 30.0, 0.3), (0, -27.8, 0)),
        box("roof slope", (3.8, 2.0, 16.4), (8.6, 30.0, 0.3), (0, 27.8, 0)),
        box("tower", (0, -10.0, 19.7), (6.0, 6.0, 10.0)),
    ],
    "view": {"cam": (-34.0, -42.0, 16.0), "look": (0, 2.0, 9.0), "lens": 35},
    "inside": {"cam": (0.0, -11.5, FLOOR + 1.6), "look": (0, 6.0, FLOOR + 2.5), "lens": 24},
}
