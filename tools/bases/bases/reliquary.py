"""The Regime's Reliquary on Bastion: a slate basilica on a podium up a flight of steps. A 30 m
nave with a pitched roof and a bell tower and spire over the door, two side chapels making the
cross, an apse, buttresses with gold ribs, red slit windows, bone statues flanking the steps and
braziers at the great door. Inside: bone columns, pews either side of a red aisle, a font, the
dais with the altar, candelabra and the throne, censers swinging over the aisle."""

import math

from basekit import ring, Base, band, box, column, door_frame, hall, room, room_boxes, slab, slope, stair, window
from kit import block, chain, cyl, label, prism, sphere, stripe
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
    b.add(block("tympanum", (0, -13.3, FLOOR + 8.3), (6.4, 0.3, 1.6), bone, bevel=0.03))
    b.add(turn(label("THE ALGORITHM PROVIDES", (0, -13.46, FLOOR + 8.3), 0.4, gold, side=-1, depth=0.03), (0, -13.46, FLOOR + 8.3), 90))
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
    detail(b)
    chantry(b)
    return b


def detail(b):
    """The second pass: a rose window and a clock on the front, gargoyles and spikes on the
    buttresses, a stepped balustrade, crockets on the ridge; inside, vault ribs, banners, choir
    stalls, votive stands and gilt lines down the runner."""
    # The rose window over the great door: a gold ring, eight spokes, an inner ring and red glass.
    fy = -13.06
    zc = FLOOR + 11.3
    b.add(cyl("rosepane", (0, fy + 0.04, zc), (0, fy, zc), 1.5, "red_glass", segs=24, bevel=0), "glass")
    b.add(ring("rose", (0, fy - 0.02, zc), (0, 1, 0), 1.75, 1.45, 0.08, gold, segs=24))
    b.add(ring("roseinner", (0, fy - 0.02, zc), (0, 1, 0), 0.55, 0.42, 0.08, gold, segs=16))
    for i in range(8):
        a = math.radians(i * 45 + 22.5)
        b.add(cyl("spoke", (0.5 * math.cos(a), fy - 0.03, zc + 0.5 * math.sin(a)), (1.5 * math.cos(a), fy - 0.03, zc + 1.5 * math.sin(a)), 0.05, gold, segs=6, bevel=0))
        b.add(sphere("roseknob", (1.62 * math.cos(a), fy - 0.03, zc + 1.62 * math.sin(a)), 0.1, gold, segs=8))
    # A clock on the tower: bone face, gold rim, twelve ticks and two hands.
    zc, fy = 17.2, -13.06
    b.add(cyl("clockface", (0, fy + 0.02, zc), (0, fy - 0.03, zc), 1.15, bone, segs=24, bevel=0.01))
    b.add(ring("clockrim", (0, fy - 0.03, zc), (0, 1, 0), 1.3, 1.1, 0.1, gold, segs=24))
    for i in range(12):
        a = math.radians(i * 30)
        b.add(block("tick", (0.95 * math.sin(a), fy - 0.05, zc + 0.95 * math.cos(a)), (0.06, 0.02, 0.18), "black", bevel=0))
    b.add(block("hourhand", (0.0, fy - 0.07, zc + 0.3), (0.08, 0.02, 0.6), "black", bevel=0))
    b.add(block("minhand", (0.35, fy - 0.07, zc), (0.7, 0.02, 0.06), "black", bevel=0))
    b.add(sphere("clockhub", (0, fy - 0.08, zc), 0.08, gold, segs=8))
    # Buttresses: a gargoyle spouting from each, a gold spike on each cap.
    for y in (-10.0, -4.0, 12.0, 16.0):
        for sx in (-1, 1):
            x = sx * 7.7
            b.add(block("gargbody", (x + sx * 0.9, y, 8.6), (0.9, 0.35, 0.35), bone, bevel=0.06, segs=3))
            b.add(sphere("garghead", (x + sx * 1.5, y, 8.65), 0.26, bone, segs=10))
            b.add(block("gargwing", (x + sx * 0.5, y, 9.05), (0.2, 0.9, 0.5), bone, bevel=0.03))
            b.add(cyl("gargjaw", (x + sx * 1.6, y, 8.55), (x + sx * 1.85, y, 8.5), 0.1, "black", r1=0.04, segs=6, bevel=0))
            b.add(cyl("spike", (sx * 7.5, y, 10.25), (sx * 7.5, y, 11.6), 0.2, gold, r1=0.02, segs=8, bevel=0))
    # The steps get a stepped balustrade with a gold ball at the foot; the ridge gets crockets.
    for sx in (-1, 1):
        for i in range(4):
            b.add(block("baluster", (sx * 4.2, -15.7 + 0.6 * i, 0.3 * (i + 1) + 0.4), (0.3, 0.6, 0.8), bone, bevel=0.03))
        b.add(sphere("newel", (sx * 4.2, -15.7, 1.3), 0.2, gold, segs=10))
    for i in range(14):
        y = -11.5 + i * 2.1
        b.add(cyl("crocket", (0, y, 18.5), (0, y, 19.1), 0.12, gold, r1=0.02, segs=6, bevel=0))
    # Inside: gold-ribbed vault arches between the columns, with a boss at the crown.
    for y in (-8.0, -4.0, 0.0, 4.0, 8.0, 12.0):
        for sx in (-1, 1):
            b.add(cyl("rib", (sx * 5.6, y, CEIL - 1.6), (sx * 2.6, y, CEIL - 0.45), 0.13, gold, segs=8, bevel=0))
            b.add(cyl("rib", (sx * 2.6, y, CEIL - 0.45), (0, y, CEIL - 0.2), 0.13, gold, segs=8, bevel=0))
            b.add(block("corbel", (sx * 5.4, y, CEIL - 1.9), (0.5, 0.5, 0.4), bone, bevel=0.04, taper=(0.4, 0.4)))
        b.add(sphere("boss", (0, y, CEIL - 0.2), 0.22, gold, segs=10))
    # Banners down the nave walls between the windows, red with a gold sunburst.
    for y in (-10.0, -6.0, -2.0, 6.0, 10.0):
        for sx in (-1, 1):
            x = sx * 6.45
            b.add(block("banner", (x, y, FLOOR + 7.2), (0.04, 1.3, 4.0), "red", bevel=0.01))
            b.add(block("bannerrod", (x, y, FLOOR + 9.3), (0.07, 1.6, 0.07), gold, bevel=0))
            b.add(block("bannerfringe", (x, y, FLOOR + 5.15), (0.05, 1.3, 0.1), gold, bevel=0))
            b.add(ring("bannersun", (x - sx * 0.03, y, FLOOR + 7.4), (1, 0, 0), 0.38, 0.3, 0.02, gold, segs=14))
            b.add(block("bannerbar", (x - sx * 0.03, y, FLOOR + 6.7), (0.02, 0.1, 0.9), gold, bevel=0))
    # Choir stalls either side of the dais, votive stands by the door, gilt lines along the runner.
    for sx in (-1, 1):
        x = sx * 3.6
        b.add(block("stallseat", (x, 13.2, FLOOR + 0.55), (0.6, 2.6, 0.12), "leather", bevel=0.02))
        b.add(block("stallbase", (x, 13.2, FLOOR + 0.3), (0.6, 2.6, 0.5), bone, bevel=0.02))
        b.add(block("stallback", (x + sx * 0.3, 13.2, FLOOR + 1.3), (0.1, 2.6, 1.4), bone, bevel=0.02))
        b.add(block("stallrail", (x + sx * 0.3, 13.2, FLOOR + 2.05), (0.16, 2.7, 0.1), gold, bevel=0.01))
        for y in (11.95, 14.45):
            b.add(block("stallpost", (x + sx * 0.3, y, FLOOR + 1.1), (0.14, 0.14, 2.2), gold, bevel=0.01))
        b.add(block("votive", (sx * 4.9, -6.5, FLOOR + 0.45), (0.5, 1.5, 0.9), bone, bevel=0.03))
        for i in range(5):
            b.add(sphere("votiveflame", (sx * 4.9, -7.0 + i * 0.25, FLOOR + 0.98), 0.07, "gold_light", segs=6), "lights")
        b.add(stripe("gilt", (sx * 1.25, 0.5, FLOOR + 0.05), (0.06, 24.0, 0.02), gold))


CHANTRY = ((-12.5, -19.5), (9.0, 5.0, 5.5))
CHANTRY_DOORS = [("+x", 0.0, 1.6, 3.0)]
CHANTRY_WALL = 0.25


def chantry(b):
    """The chantry before the steps: a small stone chapel with red slit windows, a gilded
    reliquary on its altar between candelabra, and a kneeler. Make the tithe here."""
    (x, y), s = CHANTRY
    z0 = CHANTRY_WALL
    slits = [(f, off, 0.6, 2.2, 1.6) for f in ("-y", "+y") for off in (-2.5, 2.5)]
    room(b, "chantry", (x, y), s, slate, CHANTRY_DOORS, wall=CHANTRY_WALL, trim=gold, windows=slits)
    for f, off, w, h, z in slits:
        window(b, (x + off, y + (-1 if f == "-y" else 1) * s[1] / 2, z0 + z + h / 2), (w, 0.1, h), frame=gold, glass="red_glass")
    band(b, (x, y, 0), (s[0], s[1], 0), s[2] - 0.6, 0.25, gold)
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.add(block("buttress", (x + sx * (s[0] / 2 + 0.2), y + sy * (s[1] / 2 + 0.2), s[2] / 2), (0.5, 0.5, s[2]), slate, bevel=0.04))
            b.add(cyl("pinnacle", (x + sx * (s[0] / 2 + 0.2), y + sy * (s[1] / 2 + 0.2), s[2]), (x + sx * (s[0] / 2 + 0.2), y + sy * (s[1] / 2 + 0.2), s[2] + 0.9), 0.22, gold, r1=0.03, segs=8, bevel=0))
    b.add(block("crossbar", (x, y, s[2] + 1.0), (0.12, 0.12, 1.4), gold, bevel=0.01))
    b.add(block("crossarm", (x, y, s[2] + 1.3), (0.12, 0.7, 0.12), gold, bevel=0.01))
    for sy in (-1, 1):
        b.add(block("brazier", (x + s[0] / 2 + 0.9, y + sy * 1.4, 0.4), (0.4, 0.4, 0.8), "black", bevel=0.02))
        b.add(sphere("flame", (x + s[0] / 2 + 0.9, y + sy * 1.4, 0.95), 0.15, "gold_light", segs=8), "lights")
    # The altar against the west wall, the casket on it, candelabra either side, the kneeler.
    ax = x - s[0] / 2 + CHANTRY_WALL + 0.6
    altar(b, (ax, y, z0), (1.0, 2.4, 1.05), material=bone, cloth="red", trim=gold)
    b.add(block("casket", (ax, y, z0 + 1.3), (0.5, 1.1, 0.3), gold, bevel=0.02))
    b.add(prism("casketlid", [(y - 0.55, z0 + 1.45), (y, z0 + 1.7), (y + 0.55, z0 + 1.45)], 0.5, gold, x=ax, bevel=0.01))
    b.add(sphere("jewel", (ax + 0.27, y, z0 + 1.3), 0.06, "red_light", segs=8), "lights")
    for dy in (-1.5, 1.5):
        candelabra(b, (ax, y + dy, z0), material=gold, arms=5, h=1.5)
    b.add(block("kneeler", (ax + 1.7, y, z0 + 0.2), (0.5, 1.6, 0.4), "leather", bevel=0.05, segs=3))
    b.add(block("kneelerrail", (ax + 1.7, y, z0 + 0.62), (0.2, 1.6, 0.05), gold, bevel=0.01))
    for dy in (-1.4, 1.4):
        b.add(block("bonestatue", (ax + 3.2, y + dy, z0 + 0.8), (0.4, 0.4, 1.6), bone, bevel=0.1, segs=3))
        b.add(sphere("skull", (ax + 3.2, y + dy, z0 + 1.8), 0.22, bone, segs=10))
    b.add(block("aisle", (x + 0.8, y, z0 + 0.01), (s[0] - 2.4, 1.2, 0.02), "red", bevel=0))
    lamp(b, "lamp.8", (x, y, s[2] - CHANTRY_WALL - 0.02), material="gold_light", rim=gold, r=0.25)


_NAVE_WALL = [box(n, c, s) for n, c, s in (
    ("west wall", (-6.75, -5.5, 7.7), (0.5, 15.0, 14.0)), ("west wall", (-6.75, 3.0, 7.7), (0.5, 2.0, 14.0)), ("west wall", (-6.75, 12.5, 7.7), (0.5, 9.0, 14.0)),
    ("west arch", (-6.75, 6.0, 10.95), (0.5, 4.0, 7.5)),
    ("east wall", (6.75, -5.5, 7.7), (0.5, 15.0, 14.0)), ("east wall", (6.75, 3.0, 7.7), (0.5, 2.0, 14.0)), ("east wall", (6.75, 12.5, 7.7), (0.5, 9.0, 14.0)),
    ("east arch", (6.75, 6.0, 10.95), (0.5, 4.0, 7.5)),
)]

SPEC = {
    "build": build,
    "name": "The Reliquary",
    "color": (1.0, 0.2, 0.2),
    "faction": "regime",
    "body": "bastion",
    "lat": 18.0,
    "lon": -35.0,
    "footprint": (28.0, 44.0),
    "footprint_at": (-3.0, -1.0),
    "pad": (0.0, -36.0),
    "door": (0.0, -12.75, FLOOR + 1.3),
    "size": (44.5, 31.5, 34.9),
    "depth": 0.3,
    "nodes": [f"lamp.{i}" for i in range(9)],
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
        box("stall", (-3.6, 13.2, FLOOR + 0.6), (0.7, 2.6, 1.2)),
        box("stall", (3.6, 13.2, FLOOR + 0.6), (0.7, 2.6, 1.2)),
        box("roof slope", (-3.8, 2.0, 16.4), (8.6, 30.0, 0.3), (0, -27.8, 0)),
        box("roof slope", (3.8, 2.0, 16.4), (8.6, 30.0, 0.3), (0, 27.8, 0)),
        box("tower", (0, -10.0, 19.7), (6.0, 6.0, 10.0)),
        *room_boxes("chantry", CHANTRY[0], CHANTRY[1], CHANTRY_DOORS, wall=CHANTRY_WALL),
        box("chantry altar", (CHANTRY[0][0] - CHANTRY[1][0] / 2 + CHANTRY_WALL + 0.6, CHANTRY[0][1], 0.775), (1.0, 2.4, 1.05)),
    ],
    "stations": [("shrine", (CHANTRY[0][0] - 1.6, CHANTRY[0][1], 1.4), "Shrine")],
    "view": {"cam": (-34.0, -42.0, 16.0), "look": (0, 2.0, 9.0), "lens": 35},
    "annex": {"cam": (-8.9, -21.4, 2.1), "look": (-15.5, -19.5, 1.5), "lens": 22},
    "annex_out": {"cam": (-26.0, -32.0, 6.0), "look": (-12.5, -19.5, 3.0), "lens": 30},
    "inside": {"cam": (0.0, -11.5, FLOOR + 1.6), "look": (0, 6.0, FLOOR + 2.5), "lens": 24},
}
