"""The Deserters' Roost, on the flat south-east of Haven's apron beyond the course, door toward the
pad: a lived-in rebel camp round a two-storey hangar, in Haven's comic look. The hangar is painted
cream with big orange panels, a dark skirt and fascia, black chevrons pointing into the bay and a
roosting-bird roundel on its flanks; a striped awning shades the bay, crates spill out of it, and a
timber stair climbs the west side to a timber lookout deck under shade cloth on the roof, beside a
turning radar, a windsock with a spinning anemometer and a radio mast with a red beacon.
Round it: a cook fire under a shade sail with log benches and string lights, laundry lines, raised
veg beds and a polytunnel greenhouse on the east, the generator and its fuel out the back, and the
supply depot (Quartermaster) in the front yard. Inside: bunks and a hammock, a mess table, a
planning table under a ceiling fan, the radio bench, gun racks, the lockers by the bay door,
bunting and string lights off the timber mezzanine."""

import math

import bmesh
from basekit import Base, box, door_frame, floodlight, hall, life_node, railing, ring, room, room_boxes, sandbags, slab, slope, spinner, stair, tank, window
from kit import block, cyl, join, label, sphere, srgb, wk
from interior import barrel, bunk, cabinet, first_aid, gun_rack, lamp, turn, tyre
from mathutils import Vector

FLOOR = 0.3
ROOF = 8.5
DECK = ROOF + 0.12  # the lookout deck's planks
dark, pale, orange, tan = "deserter_dark", "deserter_pale", "deserter_orange", "deserter_tan"
wood, wood_dk, plank = "roost_wood", "roost_wood_dark", "roost_plank"
leaf, leaf_dk, teal = "roost_leaf", "roost_leaf_dark", "roost_teal"

wk.PALETTE.update({
    "roost_wood": srgb("#8A5A34", roughness=0.85, wear=0.4),
    "roost_wood_dark": srgb("#5A3820", roughness=0.9, wear=0.4),
    "roost_plank": srgb("#B98552", roughness=0.85, wear=0.35),
    "roost_leaf": srgb("#5DB03C", roughness=0.8, wear=0.1),
    "roost_leaf_dark": srgb("#2F7D34", roughness=0.8, wear=0.1),
    "roost_soil": srgb("#4B3322", roughness=1.0, wear=0.1),
    "roost_tomato": srgb("#E5412B", roughness=0.5, wear=0.1),
    "roost_poly": srgb("#DCE9D2", roughness=0.4, wear=0.15),
    "roost_teal": srgb("#2C8F8C", roughness=0.8, wear=0.3),
    "roost_stone": srgb("#8F8B83", roughness=0.95, wear=0.3),
    "roost_ember": ((1.0, 0.32, 0.05), (1.0, 0.32, 0.05), 0.0, 0.5, 0.0, 6.0),
    "roost_flame": ((1.0, 0.72, 0.18), (1.0, 0.72, 0.18), 0.0, 0.5, 0.0, 8.0),
    "roost_bulb": ((1.0, 0.82, 0.5), (1.0, 0.82, 0.5), 0.0, 0.3, 0.0, 5.0),
})


# ------------------------------------------------------------------------------- local helpers

def B(name, c, s, m, bevel=0.0, **k):
    """A block with crisp edges: the ink outline draws them, and a bevel costs ten times the tris."""
    return block(name, c, s, m, bevel=bevel, **k)


def C(name, p0, p1, r, m, segs=8, **k):
    return cyl(name, p0, p1, r, m, segs=segs, bevel=0, **k)


def poly(name, pts, c, n, depth, m, scale=1.0):
    """A flat painted shape: the outline `pts` (u, v) laid on a wall facing `n` (horizontal) round
    `c`, u along the wall to the right as you face it, v up, and `depth` proud of it."""
    n = Vector(n).normalized()
    u = Vector((0, 0, 1)).cross(n)
    v = Vector((0, 0, 1))
    bm = bmesh.new()
    vs = [bm.verts.new(Vector(c) + n * 0.004 + u * x * scale + v * y * scale) for x, y in pts]
    f = bm.faces.new(vs)
    ret = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, vec=n * depth, verts=[e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return wk._obj(name, bm, m, 0.0)


def flat(name, pts, m, thick=0.03):
    """A thin sheet through three or more 3D points (a shade sail, a tarp, a flag)."""
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in pts]
    f = bm.faces.new(vs)
    bm.normal_update()
    nrm = f.normal.copy()
    ret = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, vec=nrm * thick, verts=[e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return wk._obj(name, bm, m, 0.0)


def chevron(h, d, t):
    """A '>' chevron outline, `h` tall, its point `d` to the right, arms `t` thick."""
    return [(0, h / 2), (d, 0), (0, -h / 2), (-t, -h / 2), (d - t, 0), (-t, h / 2)]


BIRD = [(-0.82, -0.05), (-0.42, 0.06), (-0.22, 0.52), (0.12, 0.78), (0.05, 0.3), (0.3, 0.38), (0.5, 0.33),
        (0.78, 0.2), (0.5, 0.1), (0.38, -0.2), (0.1, -0.42), (-0.3, -0.36)]


def roundel(b, c, n, r):
    """The Deserters' mark: a cream disc in an orange ring, a black roosting bird on a branch."""
    n = Vector(n).normalized()
    p = Vector(c)
    b.add(C("roundel", p, p + n * 0.04, r, orange, segs=24))
    b.add(C("roundel", p + n * 0.03, p + n * 0.07, r * 0.82, pale, segs=24))
    b.add(poly("bird", BIRD, p + n * 0.06, n, 0.03, dark, scale=r * 0.8))
    b.add(poly("branch", [(-0.7, -0.5), (0.7, -0.44), (0.7, -0.54), (-0.7, -0.6)], p + n * 0.06, n, 0.03, dark, scale=r * 0.8))


def sag_line(a, b_, sag, n):
    """`n + 1` points along a hanging line from a to b, `sag` metres low in the middle."""
    a, b_ = Vector(a), Vector(b_)
    return [a.lerp(b_, i / n) - Vector((0, 0, sag * 4 * (i / n) * (1 - i / n))) for i in range(n + 1)]


def string_lights(b, a, b_, sag=0.4, pitch=0.7, cord="black"):
    """A festoon of warm bulbs on a sagging cord."""
    n = max(2, int((Vector(b_) - Vector(a)).length / pitch))
    pts = sag_line(a, b_, sag, n)
    b.add(join([C("cord", p, q, 0.012, cord, segs=4) for p, q in zip(pts, pts[1:])], "cord"))
    b.add(join([sphere("bulb", p - Vector((0, 0, 0.07)), 0.06, "roost_bulb", segs=6) for p in pts[1:-1]], "bulbs"), "lights")


def bunting(b, a, b_, sag=0.35, pitch=0.45, colours=(orange, pale, teal, "hazard")):
    """A line of triangle flags."""
    a, b_ = Vector(a), Vector(b_)
    n = max(2, int((b_ - a).length / pitch))
    pts = sag_line(a, b_, sag, n)
    d = (b_ - a).normalized()
    parts = [C("string", p, q, 0.008, "black", segs=4) for p, q in zip(pts, pts[1:])]
    for i, (p, q) in enumerate(zip(pts, pts[1:])):
        mid = (p + q) / 2
        parts.append(flat("flag", [p + d * 0.03, q - d * 0.03, mid - Vector((0, 0, 0.32))], colours[i % len(colours)], thick=0.01))
    b.add(join(parts, "bunting"))


def timber_rail(b, p0, p1, h=1.0, post=0.12, spacing=1.6):
    """A chunky timber guard rail: square posts, a top rail and a mid rail."""
    a, c = Vector(p0), Vector(p1)
    d = c - a
    L = d.length
    yaw = math.degrees(math.atan2(d.y, d.x))
    parts = []
    for z, t in ((h, 0.1), (h * 0.5, 0.07)):
        m = (a + c) / 2 + Vector((0, 0, z))
        parts.append(turn(B("rail", m, (L + post, t, t), wood), m, yaw))
    k = max(2, int(L / spacing) + 1)
    for i in range(k):
        p = a.lerp(c, i / (k - 1))
        parts.append(B("post", p + Vector((0, 0, h / 2)), (post, post, h), wood_dk))
    return b.add(join(parts, "timber rail"))


def plank_deck(b, c, s, along="x", gap=0.03, w=0.3, m=plank):
    """A timber deck of planks running `along` x or y, its top at c.z + s.z / 2, on a dark joist frame."""
    x, y, z = c
    sx, sy, sz = s
    parts = [B("joists", (x, y, z - 0.04), (sx, sy, sz - 0.08), "black")]
    across = sy if along == "x" else sx
    n = max(1, int(across / w))
    pw = across / n
    for i in range(n):
        o = -across / 2 + (i + 0.5) * pw
        tone = m if i % 3 else wood
        if along == "x":
            parts.append(B("plank", (x, y + o, z + sz / 2 - 0.04), (sx, pw - gap, 0.08), tone))
        else:
            parts.append(B("plank", (x + o, y, z + sz / 2 - 0.04), (pw - gap, sy, 0.08), tone))
    return b.add(join(parts, "deck"))


def box_crate(b, c, s, m=tan, yaw=0.0, stencil_mat="black"):
    """A cheap wooden crate: body, two dark bands and a painted stripe."""
    x, y, z = c
    parts = [B("crate", c, s, m)]
    for sx in (-1, 1):
        parts.append(B("band", (x + sx * (s[0] / 2 - 0.08), y, z), (0.06, s[1] + 0.02, s[2] + 0.02), wood_dk))
    parts.append(B("stencil", (x, y - s[1] / 2 - 0.006, z), (s[0] * 0.4, 0.01, s[2] * 0.22), stencil_mat))
    o = join(parts, "crate")
    if yaw:
        turn(o, c, yaw)
    return b.add(o)


def stool(b, c, m=wood):
    x, y, z = c
    parts = [C("seat", (x, y, z + 0.42), (x, y, z + 0.48), 0.2, m, segs=10)]
    for i in range(3):
        a = i * math.tau / 3
        parts.append(C("leg", (x + math.cos(a) * 0.14, y + math.sin(a) * 0.14, z), (x + math.cos(a) * 0.1, y + math.sin(a) * 0.1, z + 0.43), 0.02, "black", segs=4))
    return b.add(join(parts, "stool"))


def shirt(c, m, yaw=0.0, wide=0.55, long=0.65):
    x, y, z = c
    parts = [B("body", (x, y, z - long / 2), (wide, 0.03, long), m),
             B("sleeves", (x, y, z - 0.12), (wide + 0.36, 0.03, 0.2), m)]
    o = join(parts, "shirt")
    return turn(o, c, yaw) if yaw else o


def trousers(c, m, yaw=0.0):
    x, y, z = c
    parts = [B("waist", (x, y, z - 0.08), (0.42, 0.03, 0.16), m)]
    for sx in (-1, 1):
        parts.append(B("leg", (x + sx * 0.11, y, z - 0.5), (0.19, 0.03, 0.7), m))
    o = join(parts, "trousers")
    return turn(o, c, yaw) if yaw else o


def laundry(b, a, b_, items):
    """A washing line between two T-posts with pegged clothes: `items` are (t along, kind, colour)."""
    a, b_ = Vector(a), Vector(b_)
    yaw = math.degrees(math.atan2((b_ - a).y, (b_ - a).x))
    for p in (a, b_):
        b.add(C("post", (p.x, p.y, 0), (p.x, p.y, p.z + 0.15), 0.06, wood_dk, segs=6))
        b.add(turn(B("tee", (p.x, p.y, p.z + 0.05), (0.08, 0.9, 0.08), wood), (p.x, p.y, p.z), yaw))
    pts = sag_line(a, b_, 0.25, 10)
    b.add(join([C("line", p, q, 0.01, pale, segs=4) for p, q in zip(pts, pts[1:])], "line"))
    for t, kind, m in items:
        i = t * 10
        p = pts[int(i)].lerp(pts[min(10, int(i) + 1)], i - int(i))
        if kind == "shirt":
            b.add(shirt(p, m, yaw))
        elif kind == "towel":
            b.add(turn(B("towel", p - Vector((0, 0, 0.42)), (0.6, 0.03, 0.84), m), p, yaw))
        elif kind == "trousers":
            b.add(trousers(p, m, yaw))
        else:  # a pair of socks
            for dx in (-0.08, 0.08):
                q = p + Vector((dx * math.cos(math.radians(yaw)), dx * math.sin(math.radians(yaw)), 0))
                b.add(turn(B("sock", q - Vector((0, 0, 0.18)), (0.1, 0.03, 0.36), m), q, yaw))


def cabbage(c, r=0.22):
    x, y, z = c
    return join([sphere("head", (x, y, z + r * 0.7), r, leaf, segs=6),
                 cyl("leaves", (x, y, z + 0.02), (x, y, z + r * 0.5), r * 1.35, leaf_dk, r1=r * 1.5, segs=6, bevel=0)], "cabbage")


def tomato(c, h=0.9):
    """A staked tomato plant: a cane, a leafy cone and three red fruit."""
    x, y, z = c
    parts = [C("cane", (x, y, z), (x, y, z + h + 0.15), 0.015, wood, segs=4),
             cyl("bush", (x, y, z + 0.15), (x, y, z + h), 0.26, leaf_dk, r1=0.08, segs=6, bevel=0)]
    for i in range(3):
        a = i * 2.1
        parts.append(sphere("fruit", (x + math.cos(a) * 0.17, y + math.sin(a) * 0.17, z + 0.3 + 0.15 * i), 0.07, "roost_tomato", segs=6))
    return join(parts, "tomato")


def veg_bed(b, c, s, plants="cabbage"):
    """A raised timber bed of soil, `s` = (x, y) and 0.4 high, planted in two rows along its length."""
    x, y = c
    sx, sy = s
    h = 0.4
    b.add(B("bed", (x, y, h / 2), (sx, sy, h), wood))
    b.add(B("soil", (x, y, h + 0.01), (sx - 0.16, sy - 0.16, 0.04), "roost_soil"))
    for f in (-1, 1):
        b.add(B("bedcap", (x, y + f * (sy / 2 - 0.04), h + 0.02), (sx + 0.04, 0.1, 0.05), wood_dk))
    long_x = sx > sy
    L = sx if long_x else sy
    n = int(L / 0.6)
    for i in range(n):
        o = -L / 2 + (i + 0.5) * L / n
        for r in (-0.27, 0.27):
            p = (x + o, y + r, h) if long_x else (x + r, y + o, h)
            b.add(cabbage(p) if plants == "cabbage" else tomato(p))


def polytunnel(b, gx, y0, y1, R, n=8):
    """A hoop greenhouse along Y: a milky half-tube sheet (outside, inside and its front lip), a
    closed back end, dark hoops over it."""
    bm = bmesh.new()

    def arc(y, r):
        return [bm.verts.new((gx + r * math.cos(math.pi * k / n), y, r * math.sin(math.pi * k / n))) for k in range(n + 1)]
    o0, o1, i0, i1 = arc(y0, R), arc(y1, R), arc(y0, R - 0.04), arc(y1, R - 0.04)
    for k in range(n):
        bm.faces.new((o0[k], o0[k + 1], o1[k + 1], o1[k]))
        bm.faces.new((i0[k + 1], i0[k], i1[k], i1[k + 1]))
        bm.faces.new((o0[k + 1], o0[k], i0[k], i0[k + 1]))
    bm.faces.new(o1)
    bm.faces.new(i1[::-1])
    bm.normal_update()
    b.add(wk._obj("polytunnel", bm, "roost_poly", 0.0))
    for k in range(5):
        yy = y0 + 0.05 + k * (y1 - y0 - 0.1) / 4
        hoop = [(gx + (R + 0.03) * math.cos(math.pi * j / n), yy, (R + 0.03) * math.sin(math.pi * j / n)) for j in range(n + 1)]
        b.add(join([C("hoop", p, q, 0.04, dark, segs=4) for p, q in zip(hoop, hoop[1:])], "hoop"))


# ---------------------------------------------------------------------------------- the build

def build():
    b = Base("roost")
    hangar(b)
    roof(b)
    stairs(b)
    inside(b)
    yard(b)
    garden(b)
    backyard(b)
    depot(b)
    return b


def hangar(b):
    """The shell and its paint: cream walls, big orange panels, a dark skirt, fascia and corner
    posts, chevrons into the bay, the roundel on the flanks, the striped awning."""
    hall(b, "hangar", (0, 0, ROOF / 2), (22.0, 14.0, ROOF), pale, wall=0.3, bevel=0.04, segs=1,
         openings=[("-y", 0, 8.0, 5.0, 0), ("+x", -3.0, 1.4, 2.4, 0),
                   ("-y", -7.0, 2.5, 1.2, 5.5), ("-y", 7.0, 2.5, 1.2, 5.5), ("+y", -5.0, 2.0, 1.2, 5.5), ("+y", 5.0, 2.0, 1.2, 5.5)])
    slab(b, "plinth", (0, 0, -0.15), (23.0, 15.0, 0.3), "concrete", bevel=0)
    slab(b, "apron", (0, -8.1, 0.14), (9.0, 2.2, 0.28), "concrete", bevel=0)
    for x in (-3.0, 0.0, 3.0):
        b.add(B("apronline", (x, -8.1, 0.285), (0.12, 2.0, 0.01), "hazard"))
    P = 0.02  # paint stands this proud
    # The dark skirt and the fascia, the skirt broken round the doors.
    for z, h in ((0.55, 1.1), (7.85, 1.3)):
        b.add(B("skirt", (0, 7.0 + P / 2, z), (22.0 + 2 * P, P, h), dark))
        b.add(B("skirt", (-11.0 - P / 2, 0, z), (P, 14.0 + 2 * P, h), dark))
        if z < 1:
            for x0, x1 in ((-11.0, -4.0), (4.0, 11.0)):
                b.add(B("skirt", ((x0 + x1) / 2, -7.0 - P / 2, z), (x1 - x0 + 2 * P, P, h), dark))
            for y0, y1 in ((-7.0, -3.7), (-2.3, 7.0)):
                b.add(B("skirt", (11.0 + P / 2, (y0 + y1) / 2, z), (P, y1 - y0 + 2 * P, h), dark))
        else:
            b.add(B("skirt", (0, -7.0 - P / 2, z), (22.0 + 2 * P, P, h), dark))
            b.add(B("skirt", (11.0 + P / 2, 0, z), (P, 14.0 + 2 * P, h), dark))
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.add(B("corner", (sx * 10.9, sy * 6.9, ROOF / 2), (0.5, 0.5, ROOF + 0.1), dark))
    # The big orange panels: two on the back, two on the west, two on the east round the side door.
    for x0, x1 in ((-10.3, -4.6), (4.6, 10.3)):
        b.add(B("panel", ((x0 + x1) / 2, 7.0 + 0.03, 3.7), (x1 - x0, 0.04, 4.6), orange))
    for y0, y1 in ((-6.3, -0.6), (0.6, 6.3)):
        b.add(B("panel", (-11.0 - 0.03, (y0 + y1) / 2, 3.7), (0.04, y1 - y0, 4.6), orange))
    b.add(B("panel", (11.03, -5.6, 3.7), (0.04, 1.4, 4.6), orange))
    b.add(B("panel", (11.03, 3.1, 4.4), (0.04, 6.4, 6.0), orange))
    for sx in (-1, 1):
        # Beside the bay: an orange panel with black chevrons pointing in.
        b.add(B("panel", (sx * 5.3, -7.03, 2.9), (1.9, 0.04, 4.4), orange))
        for i in range(4):
            pts = [(-u if sx > 0 else u, v) for u, v in chevron(0.9, 0.55, 0.32)]
            b.add(poly("chev", pts, (sx * 5.25 - sx * 0.1, -7.05, 1.25 + i * 1.1), (0, -1, 0), 0.02, dark))
        b.add(B("jamb", (sx * 4.2, -7.1, 2.8), (0.4, 0.3, 5.0), dark))
        b.add(B("jambstripe", (sx * 4.2, -7.26, 2.8), (0.12, 0.02, 4.6), pale))
    b.add(B("lintel", (0, -7.1, 5.5), (8.8, 0.3, 0.4), dark))
    b.add(C("doorroll", (-4.1, -7.45, 5.95), (4.1, -7.45, 5.95), 0.32, dark, segs=10))
    b.add(B("rollbox", (0, -7.35, 6.35), (8.6, 0.5, 0.35), orange))
    # The hand-painted sign over the bay.
    b.add(B("signboard", (0, -7.1, 7.35), (7.2, 0.12, 1.2), orange))
    b.add(B("signedge", (0, -7.08, 7.35), (7.5, 0.1, 1.45), dark))
    b.add(turn(label("THE ROOST", (0, -7.19, 7.32), 0.85, pale, side=-1, depth=0.04), (0, -7.19, 7.32), 90))
    for x in (-7.0, 7.0):
        window(b, (x, -7.0, FLOOR + 6.1), (2.5, 0.1, 1.2), frame=dark, bars=2)
    for x in (-5.0, 5.0):
        window(b, (x, 7.0, FLOOR + 6.1), (2.0, 0.1, 1.2), frame=dark, bars=1)
    door_frame(b, (11.0, -3.0, FLOOR), 1.4, 2.4, material=dark, depth=0.5)
    b.add(B("sidedoorsign", (11.06, -3.0, 3.35), (0.04, 1.2, 0.4), "hazard"))
    roundel(b, (11.04, 3.1, 4.5), (1, 0, 0), 2.3)
    roundel(b, (-11.04, 0.0, 3.7), (-1, 0, 0), 1.9)
    # The striped awning over the bay on timber posts, its pointed valance.
    drop = 0.8
    a = math.degrees(math.atan2(drop, 3.6))
    n = 12
    for i in range(n):
        x = -5.5 + (i + 0.5) * 11.0 / n
        b.add(B("awning", (x, -8.8, 5.75 - drop / 2), (11.0 / n + 0.005, 3.7, 0.06), orange if i % 2 else pale, rot=a))
        b.add(flat("valance", [(x - 11.0 / n / 2, -10.62, 5.32 - drop), (x + 11.0 / n / 2, -10.62, 5.32 - drop), (x, -10.62, 4.95 - drop)],
                   pale if i % 2 else orange, thick=0.02))
    b.add(B("awningbar", (0, -10.6, 5.34 - drop), (11.2, 0.12, 0.1), wood_dk))
    for x in (-5.3, 5.3):
        b.add(B("awningpost", (x, -10.5, (5.3 - drop) / 2), (0.16, 0.16, 5.3 - drop), wood))
        b.add(C("stay", (x, -10.5, 5.3 - drop), (x * 0.9, -7.1, 7.0), 0.025, "steel", segs=4))
    for x in (-10.4, 10.4):
        b.add(C("downpipe", (x, 7.25, 0.1), (x, 7.25, ROOF - 0.2), 0.08, dark, segs=6))
    b.add(C("conduit", (-10.6, -7.18, 4.2), (-4.4, -7.18, 4.2), 0.05, "black", segs=6))


def roof(b):
    """The roof: a timber lookout deck under shade cloth at the front, a steel rail round the rest,
    the radar, the windsock and anemometer, the radio mast and its beacon, the water tank."""
    railing(b, (10.8, -6.8, ROOF), (10.8, 6.8, ROOF), spacing=2.4)
    railing(b, (10.8, 6.8, ROOF), (-10.8, 6.8, ROOF), spacing=2.4)
    railing(b, (-10.8, 6.8, ROOF), (-10.8, -0.6, ROOF), spacing=2.4)
    railing(b, (2.2, -6.8, ROOF), (10.8, -6.8, ROOF), spacing=2.4)
    # The lookout deck: planks over the front-west of the roof, a timber rail, sandbags, a shade cloth.
    b.add(B("membrane", (0, 0, ROOF + 0.005), (21.4, 13.4, 0.01), "grey"))
    plank_deck(b, (-4.3, -3.75, ROOF + 0.06), (13.0, 6.1, 0.12), along="x")
    timber_rail(b, (-10.75, -6.75, DECK), (2.15, -6.75, DECK))
    timber_rail(b, (2.15, -6.75, DECK), (2.15, -0.75, DECK))
    timber_rail(b, (-10.75, -0.75, DECK), (-10.75, -5.0, DECK))
    sandbags(b, (-4.5, -6.35, DECK), 5.0, rows=2)
    sandbags(b, (-0.5, -6.35, DECK), 2.0, rows=2)
    for x, y in ((-9.8, -6.4), (1.6, -6.4), (1.6, -1.2), (-9.8, -1.2)):
        b.add(B("canopypost", (x, y, DECK + 1.45), (0.16, 0.16, 2.9), wood))
    b.add(flat("shadecloth", [(-9.9, -6.5, DECK + 2.6), (1.7, -6.5, DECK + 2.6), (1.7, -1.1, DECK + 3.0), (-9.9, -1.1, DECK + 3.0)], teal, thick=0.03))
    b.add(B("clothedge", (-4.1, -6.52, DECK + 2.55), (11.8, 0.05, 0.12), orange))
    # On the deck: a spotting scope, two folding chairs and a crate table with a thermos.
    sx, sy = -6.5, -5.6
    b.add(join([C("tripod", (sx + 0.25 * math.cos(a), sy + 0.25 * math.sin(a), DECK), (sx, sy, DECK + 1.25), 0.015, "black", segs=4) for a in (0.5, 2.6, 4.7)]
               + [C("scope", (sx, sy + 0.25, DECK + 1.35), (sx, sy - 0.35, DECK + 1.25), 0.07, "olive", segs=8)], "scope"))
    for x in (-3.2, -1.6):
        b.add(B("chairseat", (x, -4.6, DECK + 0.45), (0.5, 0.5, 0.06), teal))
        b.add(B("chairback", (x, -4.35, DECK + 0.75), (0.5, 0.05, 0.55), teal, rot=-10))
        for dx in (-0.22, 0.22):
            b.add(C("chairleg", (x + dx, -4.85, DECK), (x + dx, -4.35, DECK + 0.45), 0.015, "black", segs=4))
            b.add(C("chairleg", (x + dx, -4.35, DECK), (x + dx, -4.85, DECK + 0.45), 0.015, "black", segs=4))
    box_crate(b, (-2.4, -3.6, DECK + 0.3), (0.8, 0.6, 0.6), m=orange)
    b.add(C("thermos", (-2.25, -3.6, DECK + 0.6), (-2.25, -3.6, DECK + 0.9), 0.05, "red", segs=8))
    b.add(C("mug", (-2.6, -3.5, DECK + 0.6), (-2.6, -3.5, DECK + 0.7), 0.04, pale, segs=8))
    floodlight(b, "flood.0", (-10.2, -6.2, DECK), 2.6, aim=(0, -1))
    floodlight(b, "flood.1", (10.2, -6.2, ROOF), 2.6, aim=(0, -1))
    # The water tank and the radio mast with its red beacon, back west.
    tank(b, (-6.5, 4.0, ROOF + 1.0), 1.4, 2.6, material=tan, band=orange, ground=ROOF)
    m = (-9.6, 5.6, ROOF)
    b.add(join([C("mast", m, (m[0], m[1], ROOF + 9.0), 0.08, "steel", segs=6)]
               + [C("arm", (m[0] - 0.6, m[1], ROOF + z), (m[0] + 0.6, m[1], ROOF + z), 0.03, "steel", segs=4) for z in (4.5, 6.5, 8.4)]
               + [C("guy", (m[0], m[1], ROOF + 6.0), (m[0] + dx, m[1] + dy, ROOF), 0.012, "black", segs=4) for dx, dy in ((1.0, 1.0), (1.0, -1.6), (-1.0, 1.0))], "mast"))
    b.add(sphere("beacon", (m[0], m[1], ROOF + 9.12), 0.14, "red_light", segs=8), "lights")
    life_node(b, "blink", 0, (m[0], m[1], ROOF + 9.15))
    for x in (-1.5, 2.0):
        b.add(B("ac", (x, 4.8, ROOF + 0.45), (2.0, 1.1, 0.9), "grey"))
        b.add(C("acfan", (x, 4.8, ROOF + 0.9), (x, 4.8, ROOF + 0.96), 0.4, "black", segs=12))
        b.add(B("aclouvre", (x, 4.24, ROOF + 0.45), (1.6, 0.03, 0.5), "black"))
    for x, y in ((-3.5, 1.5), (4.0, -1.0)):
        b.add(C("vent", (x, y, ROOF), (x, y, ROOF + 0.7), 0.13, "steel", segs=8))
        b.add(C("ventcap", (x, y, ROOF + 0.7), (x, y, ROOF + 0.85), 0.24, "black", r1=0.05, segs=8))
    b.add(B("hatchbox", (-9.0, 1.6, ROOF + 0.3), (1.4, 1.4, 0.6), dark))
    # The radar: a lattice pedestal and a turning array (spinner 0).
    rx, ry, rz = 6.5, 2.0, ROOF + 2.3
    for dx, dy in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
        b.add(C("radarleg", (rx + dx * 1.6, ry + dy * 1.6, ROOF), (rx + dx * 0.5, ry + dy * 0.5, rz - 0.2), 0.05, dark, segs=6))
    b.add(B("radarbrace", (rx, ry, ROOF + 1.0), (1.2, 1.2, 0.08), dark))
    b.add(C("radarbase", (rx, ry, rz - 0.25), (rx, ry, rz), 0.45, orange, segs=12))
    tilt = 15
    arr = [C("radarhub", (rx, ry, rz), (rx, ry, rz + 0.35), 0.28, "steel", segs=10),
           B("radaryoke", (rx, ry, rz + 0.5), (0.7, 0.3, 0.35), dark),
           B("radararray", (rx, ry - 0.1, rz + 0.95), (3.8, 0.18, 0.75), pale, rot=tilt),
           B("radarface", (rx, ry - 0.2, rz + 0.95), (3.6, 0.04, 0.32), orange, rot=tilt),
           B("radarback", (rx, ry + 0.15, rz + 0.85), (3.0, 0.16, 0.16), dark)]
    for sx in (-1, 1):
        arr.append(C("radarstrut", (rx, ry, rz + 0.5), (rx + sx * 1.6, ry + 0.05, rz + 0.9), 0.04, dark, segs=4))
        arr.append(B("radartip", (rx + sx * 1.95, ry - 0.1, rz + 0.95), (0.14, 0.24, 0.85), dark, rot=tilt))
    spinner(b, 0, (rx, ry, rz), "z", 10, arr)
    # The windsock on its pole at the front-east corner, an anemometer on top (spinner 1).
    wx, wy, wz = 9.8, -5.4, ROOF + 4.2
    b.add(C("sockpole", (wx, wy, ROOF), (wx, wy, wz), 0.06, "steel", segs=6))
    b.add(B("sockfoot", (wx, wy, ROOF + 0.05), (0.5, 0.5, 0.1), dark))
    ring_c = Vector((wx + 0.35, wy, wz - 0.4))
    d = Vector((0.92, 0.25, -0.3)).normalized()
    b.add(C("sockarm", (wx, wy, wz - 0.4), ring_c, 0.03, "steel", segs=4))
    b.add(ring("sockring", ring_c, d, 0.46, 0.4, 0.05, "steel", segs=12))
    for i, m_ in enumerate((orange, pale, orange, pale)):
        p0 = ring_c + d * (0.65 * i)
        b.add(cyl("sock", p0, p0 + d * 0.65, 0.42 - 0.07 * i, m_, r1=0.42 - 0.07 * (i + 1), segs=10, bevel=0))
    cups = [C("anemohub", (wx, wy, wz), (wx, wy, wz + 0.12), 0.05, dark, segs=6)]
    for i in range(3):
        a = i * math.tau / 3
        tip = (wx + math.cos(a) * 0.4, wy + math.sin(a) * 0.4, wz + 0.08)
        cups.append(C("anemoarm", (wx, wy, wz + 0.08), tip, 0.012, "steel", segs=4))
        t = Vector((-math.sin(a), math.cos(a), 0)) * 0.08
        cups.append(cyl("cup", Vector(tip) - t, Vector(tip) + t, 0.02, orange, r1=0.08, segs=8, bevel=0))
    spinner(b, 1, (wx, wy, wz), "z", 45, cups)
    life_node(b, "sound", 0, (-4.0, -3.5, DECK + 1.5), sound="wind")


def stairs(b):
    """The outside stair up the west side, in timber: two flights and a landing, a bridge to the deck."""
    stair(b, (-11.9, -6.0, 0), 1.6, 6.0, 4.2, 12, material=plank, facing=1)
    plank_deck(b, (-12.7, 0.8, 4.08), (3.2, 1.6, 0.12), along="y")
    stair(b, (-13.5, 0.0, 4.2), 1.6, 6.0, 4.3, 12, material=plank, facing=-1)
    plank_deck(b, (-12.65, -6.0, ROOF), (3.3, 1.6, 0.12), along="y")
    timber_rail(b, (-14.3, -6.8, ROOF + 0.06), (-14.3, 1.6, ROOF + 0.06), spacing=2.2)
    timber_rail(b, (-14.3, 1.6, 4.14), (-11.1, 1.6, 4.14))
    railing(b, (-14.3, -6.0, 0), (-14.3, 0.0, 4.2), material="black", mid=False)
    railing(b, (-12.7, 0.0, 4.2), (-12.7, -6.0, ROOF), material="black", mid=False)
    for x, y, h in ((-11.1, -6.0, ROOF), (-14.3, -6.0, ROOF), (-14.3, 0.0, 4.2), (-14.3, 1.6, 4.2), (-11.1, 1.6, 4.2)):
        b.add(B("stairpost", (x, y, h / 2), (0.18, 0.18, h), wood_dk))
    # A woodpile under the stair, a chopping block and axe.
    for i in range(3):
        for j in range(5 - i):
            y = -4.8 + j * 0.3 + i * 0.15
            z = 0.14 + i * 0.26
            b.add(C("log", (-12.4, y, z), (-11.4, y, z), 0.14, wood if (i + j) % 2 else wood_dk, segs=6))
    b.add(B("axeblock", (-12.9, -2.2, 0.25), (0.5, 0.5, 0.5), wood_dk))
    b.add(C("axe", (-12.9, -2.2, 0.5), (-12.7, -2.4, 1.1), 0.025, wood, segs=4))
    b.add(B("axehead", (-12.88, -2.18, 0.55), (0.04, 0.22, 0.14), "steel"))


def inside(b):
    """Inside the hangar: the timber mezzanine round three walls, the stair up by the east wall,
    bunks, hammock, mess and planning tables, the radio bench, lockers, racks, bunting, lights."""
    plank_deck(b, (0, 5.5, 4.0), (21.4, 2.4, 0.12), along="x")
    plank_deck(b, (-9.7, -0.5, 4.0), (2.0, 9.6, 0.12), along="y")
    plank_deck(b, (9.7, 1.5, 4.0), (2.0, 5.6, 0.12), along="y")
    railing(b, (-8.7, 4.35, 4.06), (8.7, 4.35, 4.06), spacing=2.2, material="black")
    railing(b, (-8.75, -5.3, 4.06), (-8.75, 4.3, 4.06), spacing=2.4, material="black")
    railing(b, (8.75, -1.3, 4.06), (8.75, 4.3, 4.06), spacing=2.4, material="black")
    stair(b, (9.7, -6.6, FLOOR), 1.6, 5.3, 3.76, 14, material=plank, facing=1)
    railing(b, (8.9, -6.6, FLOOR), (8.9, -1.3, 4.06), material="black", mid=False)
    for x in (-8.7, 8.7):
        for y in (-5.3, 4.3):
            b.add(B("prop", (x, y, 2.1), (0.2, 0.2, 3.8), wood_dk))
    b.add(B("prop", (-8.7, -1.0, 2.1), (0.2, 0.2, 3.8), wood_dk))
    # The floor: painted lines round the planning table, the threshold, chevrons into the bay.
    b.add(B("floorpaint", (0, 0, FLOOR + 0.005), (21.4, 13.4, 0.01), "gunmetal"))
    for p, s in (((0, -1.0), (3.6, 0.12)), ((0, 2.0), (3.6, 0.12)), ((-1.8, 0.5), (0.12, 3.1)), ((1.8, 0.5), (0.12, 3.1))):
        b.add(B("line", (p[0], p[1], FLOOR + 0.012), (s[0], s[1], 0.012), orange))
    b.add(B("threshold", (0, -6.4, FLOOR + 0.012), (8.0, 0.3, 0.012), "hazard"))
    for i in range(3):
        y = -5.2 + i * 1.3
        for sx in (-1, 1):
            b.add(turn(B("floorchev", (sx * 0.7, y, FLOOR + 0.012), (1.8, 0.3, 0.012), pale), (sx * 0.7, y, FLOOR + 0.012), -sx * 30))
    # Bunks two high along the west wall, colourful blankets, a hammock by the props.
    for i, y in enumerate((1.5, 4.5)):
        for j, z in enumerate((0.5, 1.6)):
            b.add(bunk("bunk", (-10.0, y, FLOOR + z), (0.9, 2.0, 0.15), material="olive", wall=-1))
            b.add(B("blanket", (-9.95, y - 0.25, FLOOR + z + 0.1), (0.95, 1.3, 0.06), (teal, orange, "roost_tomato", tan)[i * 2 + j]))
    pts = sag_line((-8.7, -5.1, FLOOR + 1.7), (-8.7, -1.2, FLOOR + 1.7), 0.7, 8)
    b.add(join([B("hammock", (p + q) / 2, (0.7, (q - p).length + 0.02, 0.04), orange if i % 2 else pale,
                  rot=math.degrees(math.atan2((q - p).z, (q - p).y))) for i, (p, q) in enumerate(zip(pts, pts[1:]))], "hammock"))
    b.add(B("footlocker", (-9.6, 3.0, FLOOR + 0.25), (0.7, 0.5, 0.5), orange))
    b.add(B("footlocker", (-9.6, 6.0, FLOOR + 0.25), (0.7, 0.5, 0.5), teal))
    # The planning table with its lit map, stools round it; the ceiling fan over (spinner 2).
    b.add(B("table", (0, 0.5, FLOOR + 0.8), (2.6, 1.3, 0.08), plank))
    b.add(B("map", (0, 0.5, FLOOR + 0.85), (2.2, 1.0, 0.02), "screen"), "lights")
    for x in (-1.15, 1.15):
        for y in (0.0, 1.0):
            b.add(B("tableleg", (x, y, FLOOR + 0.4), (0.1, 0.1, 0.78), "black"))
    for x in (-0.7, 0.7):
        stool(b, (x, -0.55, FLOOR))
        stool(b, (x, 1.55, FLOOR))
    b.add(C("fanrod", (0, 2.0, ROOF - 0.3), (0, 2.0, 6.85), 0.03, "black", segs=6))
    fan = [C("fanhub", (0, 2.0, 6.6), (0, 2.0, 6.85), 0.16, dark, segs=10)]
    for a in (0, 90, 180, 270):
        fan.append(turn(B("blade", (0.75, 2.0, 6.7), (1.2, 0.26, 0.03), plank), (0, 2.0, 6.7), a))
    spinner(b, 2, (0, 2.0, 6.7), "z", 50, fan)
    # The mess table under the back mezzanine, benches, mugs and a pot.
    b.add(B("messtable", (4.8, 4.9, FLOOR + 0.75), (4.0, 0.9, 0.08), plank))
    for x in (3.1, 6.5):
        b.add(B("messleg", (x, 4.9, FLOOR + 0.37), (0.1, 0.7, 0.74), "black"))
    for y in (4.15, 5.65):
        b.add(B("messbench", (4.8, y, FLOOR + 0.42), (3.8, 0.32, 0.06), wood))
        for x in (3.2, 6.4):
            b.add(B("benchleg", (x, y, FLOOR + 0.2), (0.08, 0.28, 0.4), "black"))
    for i, x in enumerate((3.4, 3.9, 5.0, 5.6, 6.2)):
        y = 4.75 + 0.3 * (i % 2)
        b.add(C("mug", (x, y, FLOOR + 0.79), (x, y, FLOOR + 0.9), 0.045, (pale, orange, teal)[i % 3], segs=8))
    b.add(C("pot", (4.6, 4.95, FLOOR + 0.79), (4.6, 4.95, FLOOR + 1.0), 0.16, "steel", segs=10))
    for x in (-3.0, -0.5):
        b.add(gun_rack("rack", (x, 6.62, FLOOR), facing=-1, n=3, material="gunmetal"))
    # The radio bench on the east wall: a set, a mic, a headset; a pegboard of tools and a poster.
    b.add(B("bench", (8.6, 3.0, FLOOR + 0.9), (1.1, 4.4, 0.08), plank))
    b.add(B("benchshelf", (8.6, 3.0, FLOOR + 0.3), (1.0, 4.2, 0.04), wood_dk))
    for y in (1.0, 5.0):
        for x in (8.15, 9.05):
            b.add(B("benchleg", (x, y, FLOOR + 0.45), (0.08, 0.08, 0.9), "black"))
    b.add(B("radio", (8.9, 4.2, FLOOR + 1.15), (0.5, 0.8, 0.42), "olive"))
    b.add(B("radioface", (8.64, 4.2, FLOOR + 1.15), (0.02, 0.7, 0.32), "black"))
    b.add(B("radioscreen", (8.62, 4.0, FLOOR + 1.22), (0.02, 0.24, 0.1), "screen"), "lights")
    for y in (4.3, 4.45):
        b.add(C("dial", (8.63, y, FLOOR + 1.05), (8.58, y, FLOOR + 1.05), 0.04, "steel", segs=8))
    b.add(C("radioant", (9.0, 4.5, FLOOR + 1.36), (9.0, 4.5, FLOOR + 2.3), 0.012, "black", segs=4))
    b.add(C("mic", (8.4, 3.7, FLOOR + 0.94), (8.4, 3.7, FLOOR + 1.1), 0.04, "black", segs=6))
    b.add(B("headset", (8.45, 3.4, FLOOR + 0.98), (0.2, 0.18, 0.08), teal))
    life_node(b, "sound", 1, (8.8, 4.2, FLOOR + 1.4), sound="radio")
    b.add(B("pegboard", (10.62, 2.0, FLOOR + 2.0), (0.05, 2.4, 1.0), wood_dk))
    for i in range(6):
        b.add(B("tool", (10.58, 1.1 + 0.36 * i, FLOOR + 1.95 + 0.12 * (i % 2)), (0.02, 0.06, 0.4), ("steel", "red", "hazard")[i % 3]))
    b.add(B("poster", (10.62, 4.4, FLOOR + 2.1), (0.03, 0.9, 1.2), orange))
    b.add(poly("posterbird", BIRD, (10.6, 4.4, FLOOR + 2.15), (-1, 0, 0), 0.01, dark, scale=0.35))
    # The lockers by the bay door (the Locker station), painted in camp colours.
    for i, x in enumerate((5.0, 5.7, 6.4)):
        c = (x, -6.4, FLOOR + 0.95)
        b.add(turn(cabinet("locker", c, (0.6, 0.5, 1.9), material=(orange, teal, tan)[i], doors=1, vents=False), c, 180))
    b.add(B("lockersign", (5.7, -6.67, FLOOR + 2.3), (1.8, 0.04, 0.35), dark))
    b.add(turn(label("LOCKER", (5.7, -6.64, FLOOR + 2.3), 0.22, pale, side=-1, depth=0.01), (5.7, -6.64, FLOOR + 2.3), -90))
    # Stores spilling toward the bay: crates, drums, a tyre.
    box_crate(b, (-7.4, -5.2, FLOOR + 0.5), (1.2, 1.0, 1.0), m=tan)
    box_crate(b, (-7.4, -5.2, FLOOR + 1.35), (0.9, 0.8, 0.7), m=orange, yaw=12)
    box_crate(b, (-5.8, -5.6, FLOOR + 0.4), (1.0, 0.9, 0.8), m="olive")
    for i, (x, y) in enumerate(((-9.6, -5.8), (-9.0, -6.1), (-9.9, -5.0))):
        b.add(barrel("drum", (x, y, FLOOR), r=0.3, h=0.9, material=(orange, "rust", teal)[i]))
    b.add(tyre("tyre", (-4.2, -6.0, FLOOR + 0.45), axis=(0, 1, 0), r=0.45, w=0.3))
    box_crate(b, (2.6, -5.4, FLOOR + 0.45), (1.1, 0.9, 0.9), m=tan, yaw=-8)
    box_crate(b, (3.1, -4.6, FLOOR + 0.35), (0.8, 0.7, 0.7), m="olive", yaw=20)
    c = (10.6, -5.2, FLOOR + 1.5)
    b.add(turn(first_aid("aid", c, facing=-1), c, 90))
    # Bunting and string lights off the mezzanine; the emblem on the back wall.
    bunting(b, (-8.7, -2.5, 5.0), (8.7, -2.5, 5.0), sag=0.6)
    bunting(b, (-8.7, 1.5, 5.1), (8.7, 1.5, 5.1), sag=0.5)
    string_lights(b, (-8.7, 4.4, 5.3), (8.7, 4.4, 5.3), sag=0.35, pitch=0.8)
    string_lights(b, (-8.7, -5.3, 5.6), (8.7, -1.3, 5.6), sag=0.6, pitch=0.9)
    roundel(b, (0, 6.69, 6.0), (0, -1, 0), 1.3)
    # Trusses overhead: a top and bottom chord with a web of flats; pendant lamps under orange shades.
    for y in (-4.0, 0.0, 4.0):
        b.add(B("chord", (0, y, ROOF - 0.55), (21.4, 0.2, 0.16), dark))
        b.add(B("chord", (0, y, ROOF - 1.15), (21.4, 0.2, 0.16), dark))
        for i in range(14):
            x = -10.0 + (i + 0.5) * 20.0 / 14
            web = B("web", (x, y, ROOF - 0.85), (0.08, 0.12, 0.8), dark)
            b.add(web if i % 2 else turn(web, (x, y, ROOF - 0.85), 0))
    for i, (x, y) in enumerate(((-5.0, -2.0), (5.0, -2.0), (-5.0, 2.5), (5.0, 2.5))):
        b.add(C("cord", (x, y, ROOF - 0.3), (x, y, 5.2), 0.015, "black", segs=4))
        b.add(C("shade", (x, y, 5.2), (x, y, 4.95), 0.12, orange, r1=0.42, segs=10))
        lamp(b, f"lamp.{i}", (x, y, 4.96), rim="gunmetal", r=0.2)
    lamp(b, "lamp.4", (-6.0, 5.5, 3.9), rim="black", r=0.16)
    lamp(b, "lamp.5", (6.0, 5.5, 3.9), rim="black", r=0.16)


def yard(b):
    """The front yard: crates spilling out of the bay, the cook fire under a shade sail with log
    benches and string lights."""
    b.add(B("pallet", (3.3, -9.2, 0.07), (1.4, 1.3, 0.14), wood))
    box_crate(b, (3.3, -9.2, 0.64), (1.3, 1.1, 1.0), m=orange)
    box_crate(b, (3.2, -9.15, 1.5), (1.0, 0.9, 0.72), m=tan, yaw=-10)
    box_crate(b, (4.9, -8.6, 0.45), (1.0, 0.9, 0.9), m="olive", yaw=15)
    box_crate(b, (2.6, -10.8, 0.35), (0.8, 0.7, 0.7), m=tan, yaw=38)
    box_crate(b, (5.0, -10.4, 0.3), (1.0, 0.7, 0.6), m=orange, yaw=-25)
    b.add(B("lid", (5.65, -10.9, 0.45), (1.0, 0.06, 0.7), orange, rot=60))
    for i in range(5):
        x, y = 4.2 + 0.22 * i, -11.3 - 0.1 * (i % 2)
        b.add(C("tin", (x, y, 0), (x, y, 0.16), 0.06, ("steel", "red", "hazard")[i % 3], segs=8))
    for x, y in ((-3.4, -9.6), (-3.0, -10.1), (-3.6, -10.3)):
        b.add(B("sack", (x, y, 0.2), (0.5, 0.35, 0.4), "canvas", bevel=0.08, segs=1))
    # The cook fire: a stone ring, logs and flames, a tripod with a pot, log benches round it.
    fx, fy = 8.0, -15.0
    for i in range(9):
        a = i * math.tau / 9
        p = (fx + math.cos(a) * 0.75, fy + math.sin(a) * 0.75, 0.13)
        b.add(turn(B("stone", p, (0.34, 0.26, 0.26), "roost_stone"), p, math.degrees(a)))
    b.add(C("ash", (fx, fy, 0.0), (fx, fy, 0.05), 0.62, "black", segs=10))
    for a in (20, 80, 140):
        r = math.radians(a)
        d = Vector((math.cos(r), math.sin(r), 0)) * 0.45
        b.add(C("firelog", Vector((fx, fy, 0.12)) - d, Vector((fx, fy, 0.22)) + d, 0.07, wood_dk, segs=6))
    b.add(C("embers", (fx, fy, 0.05), (fx, fy, 0.1), 0.42, "roost_ember", segs=10), "lights")
    for dx, dy, h, r in ((0, 0, 0.9, 0.24), (0.15, 0.1, 0.6, 0.16), (-0.14, -0.08, 0.7, 0.17)):
        b.add(cyl("flame", (fx + dx, fy + dy, 0.1), (fx + dx, fy + dy, 0.1 + h), r, "roost_flame", r1=0.0, segs=6, bevel=0), "lights")
    for a in (90, 210, 330):
        r = math.radians(a)
        b.add(C("tripod", (fx + math.cos(r) * 0.9, fy + math.sin(r) * 0.9, 0), (fx, fy, 1.7), 0.03, "black", segs=4))
    b.add(C("potchain", (fx, fy, 1.7), (fx, fy, 1.15), 0.01, "steel", segs=4))
    b.add(C("pot", (fx, fy, 0.9), (fx, fy, 1.15), 0.2, "black", segs=10))
    life_node(b, "fire", 0, (fx, fy, 0.5))
    life_node(b, "smoke", 0, (fx, fy, 1.4))
    life_node(b, "sound", 2, (fx, fy, 0.4), sound="fire")
    for a in (200, 270, 340):
        r = math.radians(a)
        c = Vector((fx + math.cos(r) * 2.1, fy + math.sin(r) * 2.1, 0.22))
        t = Vector((-math.sin(r), math.cos(r), 0)) * 0.85
        b.add(C("bench", c - t, c + t, 0.22, wood, segs=8))
    stool(b, (fx + 2.0, fy + 0.4, 0))
    box_crate(b, (fx - 2.0, fy + 0.6, 0.25), (0.6, 0.5, 0.5), m=tan, yaw=30)
    # The shade sail over the fire on three poles.
    sail = [(5.0, -17.6, 3.6), (11.2, -17.4, 3.2), (8.6, -12.2, 4.3)]
    for x, y, z in sail:
        b.add(C("sailpole", (x, y, 0), (x, y, z + 0.1), 0.07, wood_dk, segs=6))
    b.add(flat("sail", sail, teal, thick=0.03))
    # String lights: the awning to the sail poles, round the sail and back to the hangar.
    string_lights(b, (5.3, -10.55, 4.4), (8.6, -12.2, 4.2), sag=0.25)
    string_lights(b, (-5.3, -10.55, 4.4), (5.0, -17.6, 3.4), sag=0.6)
    string_lights(b, (5.0, -17.6, 3.4), (11.2, -17.4, 3.0), sag=0.4)
    string_lights(b, (11.2, -17.4, 3.0), (10.9, -7.3, 5.2), sag=0.6)
    b.add(B("sconce", (10.9, -7.25, 5.2), (0.15, 0.2, 0.15), dark))
    lamp(b, "lamp.7", (7.0, -13.0, 3.3), rim="black", r=0.02)
    lamp(b, "lamp.8", (0.0, -12.5, 3.6), rim="black", r=0.02)
    b.add(barrel("water", (-4.6, -7.7, 0), r=0.35, h=1.0, material=teal))
    b.add(tyre("wheel", (6.2, -7.4, 0.36), axis=(0, 1, 0), r=0.36, w=0.06))


def garden(b):
    """The east: raised veg beds, the polytunnel greenhouse, laundry lines, a wheelbarrow."""
    veg_bed(b, (15.4, -5.0), (4.4, 1.2), plants="cabbage")
    veg_bed(b, (15.4, -7.4), (4.4, 1.2), plants="tomato")
    for x in (13.8, 15.4, 17.0):  # bean teepees between the beds
        for a in (0, 120, 240):
            r = math.radians(a)
            b.add(C("cane", (x + math.cos(r) * 0.3, -6.2 + math.sin(r) * 0.15, 0), (x, -6.2, 1.8), 0.015, wood, segs=4))
        b.add(cyl("vine", (x, -6.2, 0.3), (x, -6.2, 1.6), 0.28, leaf, r1=0.06, segs=6, bevel=0))
    gx, y0, y1 = 16.0, -1.0, 7.0
    polytunnel(b, gx, y0, y1, 2.1)
    b.add(C("flap", (gx - 1.4, y0 - 0.05, 1.75), (gx + 1.4, y0 - 0.05, 1.75), 0.16, "roost_poly", segs=8))
    b.add(B("tunneltape", (gx, y0 - 0.03, 1.4), (0.08, 0.02, 0.6), orange))
    for sx in (-1, 1):
        b.add(B("baseboard", (gx + sx * 2.0, (y0 + y1) / 2, 0.12), (0.12, y1 - y0, 0.24), wood))
        bx = gx + sx * 1.15
        b.add(B("tunnelbed", (bx, 3.0, 0.2), (0.9, 7.2, 0.4), wood))
        b.add(B("tunnelsoil", (bx, 3.0, 0.41), (0.8, 7.0, 0.04), "roost_soil"))
        for i in range(6):
            p = (bx, -0.2 + i * 1.25, 0.4)
            b.add(tomato(p, h=1.1) if (i + (sx > 0)) % 2 else cabbage(p, r=0.24))
    b.add(B("tunnelpath", (gx, 3.0, 0.01), (1.0, 7.8, 0.02), "concrete"))
    b.add(barrel("butt", (13.4, -1.2, 0), r=0.4, h=1.0, material=teal))
    b.add(C("can", (14.0, -1.6, 0), (14.0, -1.6, 0.3), 0.12, "hazard", segs=8))
    b.add(C("canspout", (14.1, -1.6, 0.2), (14.4, -1.6, 0.35), 0.02, "hazard", segs=4))
    wb = [B("barrow", (18.9, 0.4, 0.55), (0.7, 1.0, 0.35), "red", taper=(1.2, 1.2)),
          C("barrowwheel", (18.82, -0.2, 0.2), (18.98, -0.2, 0.2), 0.2, "black", segs=10),
          C("handle", (18.65, 0.2, 0.45), (18.65, 1.3, 0.6), 0.025, wood, segs=4),
          C("handle", (19.15, 0.2, 0.45), (19.15, 1.3, 0.6), 0.025, wood, segs=4)]
    b.add(join(wb, "barrow"))
    laundry(b, Vector((12.6, -10.4, 2.3)), Vector((19.0, -10.6, 2.3)),
            [(0.12, "shirt", orange), (0.26, "towel", teal), (0.4, "trousers", "olive"), (0.55, "shirt", pale),
             (0.68, "socks", "roost_tomato"), (0.8, "towel", "hazard"), (0.92, "shirt", teal)])
    laundry(b, Vector((12.6, -12.4, 2.3)), Vector((17.6, -12.6, 2.3)),
            [(0.15, "towel", pale), (0.35, "shirt", "roost_tomato"), (0.55, "trousers", tan), (0.78, "socks", orange)])


def backyard(b):
    """Out the back: the generator (sound, exhaust smoke), its fuel tank, jerry cans, a hose reel."""
    gx, gy = 6.5, 8.6
    b.add(B("genset", (gx, gy, 0.75), (2.4, 1.3, 1.5), "olive"))
    b.add(B("gensetstripe", (gx, gy - 0.66, 0.9), (2.0, 0.02, 0.25), orange))
    b.add(B("gensetvent", (gx + 0.6, gy - 0.66, 1.15), (0.7, 0.02, 0.35), "black"))
    b.add(B("gensetskid", (gx, gy, 0.06), (2.6, 1.4, 0.12), "black"))
    b.add(C("stack", (gx - 0.8, gy + 0.2, 1.5), (gx - 0.8, gy + 0.2, 3.4), 0.1, "black", segs=6))
    b.add(C("stackcap", (gx - 0.8, gy + 0.2, 3.4), (gx - 0.8, gy + 0.2, 3.5), 0.16, "black", r1=0.12, segs=6))
    life_node(b, "smoke", 1, (gx - 0.8, gy + 0.2, 3.6))
    life_node(b, "sound", 3, (gx, gy, 0.9), sound="generator")
    b.add(C("cable", (gx - 1.2, gy - 0.3, 1.0), (gx - 2.2, 7.15, 3.0), 0.04, "black", segs=4))
    b.add(C("fuel", (9.4, 8.3, 0.9), (9.4, 9.7, 0.9), 0.4, "red", segs=10))
    for y in (8.4, 9.6):
        b.add(B("fuelstand", (9.4, y, 0.3), (0.7, 0.1, 0.6), "black"))
    for i in range(4):
        x, y = 3.6 + 0.3 * (i % 2), 8.2 + 0.3 * (i // 2)
        b.add(B("jerry", (x, y, 0.25), (0.24, 0.16, 0.5), ("olive", "red")[i % 2]))
    b.add(ring("reel", (2.4, 7.3, 1.0), (0, 1, 0), 0.4, 0.15, 0.2, "hazard", segs=12))
    b.add(B("tarp", (-3.0, 8.4, 0.7), (3.0, 1.6, 1.4), teal, bevel=0.15, segs=1))
    b.add(B("tarptie", (-3.0, 8.4, 0.8), (3.05, 0.05, 1.45), "black"))


DEPOT = ((-10.0, -13.5), (8.0, 5.0, 3.2))
DEPOT_DOORS = [("+x", 0.0, 1.4, 2.4)]


def depot(b):
    """The quartermaster's depot in the front yard beside the bay door: a tin shack painted orange
    with a timber porch, a counter with a terminal, racks and ammunition behind it, a cot."""
    (x, y), s = DEPOT
    z0 = 0.15
    room(b, "depot", (x, y), s, orange, DEPOT_DOORS, trim=dark)
    xe, xw, ys, yn = x + s[0] / 2, x - s[0] / 2, y - s[1] / 2, y + s[1] / 2
    # Inside, cream lining over a timber dado, the east wall's lining split round the door.
    w = 0.15 + 0.012
    for c, sz in (((x, ys + w, 0), (s[0] - 0.3, 0.02, 0)), ((x, yn - w, 0), (s[0] - 0.3, 0.02, 0)), ((xw + w, y, 0), (0.02, s[1] - 0.3, 0)),
                  ((xe - w, y - 1.6, 0), (0.02, 1.8, 0)), ((xe - w, y + 1.6, 0), (0.02, 1.8, 0))):
        b.add(B("dado", (c[0], c[1], 0.65), (sz[0], sz[1], 1.0), wood))
        b.add(B("lining", (c[0], c[1], 2.1), (sz[0], sz[1], 1.9), pale))
    b.add(B("lining", (xe - w, y, 2.85), (0.02, 1.4, 0.4), pale))
    b.add(B("depotskirt", (x, ys - 0.01, 0.4), (s[0] + 0.02, 0.02, 0.8), dark))
    b.add(B("depotskirt", (xe + 0.01, y - 1.6, 0.4), (0.02, 1.8, 0.8), dark))
    b.add(B("depotskirt", (xe + 0.01, y + 1.6, 0.4), (0.02, 1.8, 0.8), dark))
    b.add(B("depotband", (x, ys - 0.012, 2.55), (s[0], 0.02, 0.3), pale))
    b.add(B("depotband", (xw - 0.012, y, 2.55), (0.02, s[1], 0.3), pale))
    b.add(B("signboard", (x, ys - 0.06, 1.65), (4.0, 0.08, 0.9), pale))
    b.add(turn(label("SUPPLY", (x, ys - 0.11, 1.65), 0.62, dark, side=-1, depth=0.03), (x, ys - 0.11, 1.65), 90))
    b.add(C("crossdisc", (xe, y - 1.7, 2.0), (xe + 0.04, y - 1.7, 2.0), 0.55, pale, segs=16))
    b.add(B("cross", (xe + 0.05, y - 1.7, 2.0), (0.04, 0.7, 0.22), "red"))
    b.add(B("cross", (xe + 0.05, y - 1.7, 2.0), (0.04, 0.22, 0.7), "red"))
    b.add(B("porch", (xe + 1.0, y, 3.0), (2.2, 3.2, 0.08), teal))
    b.add(B("porchedge", (xe + 2.1, y, 2.98), (0.1, 3.3, 0.14), orange))
    for dy in (-1.5, 1.5):
        b.add(B("porchpost", (xe + 2.0, y + dy, 1.5), (0.14, 0.14, 3.0), wood))
    sandbags(b, (xe + 0.5, ys - 0.35, 0), 2.5, rows=2)
    box_crate(b, (xe + 0.8, y + 2.2, 0.4), (0.9, 0.8, 0.8), m=orange)
    b.add(barrel("drum", (xe + 0.5, y - 2.3, 0.0), r=0.3, h=0.9, material="rust"))
    # The counter and its terminal.
    b.add(B("counter", (x + 0.9, y + 0.1, z0 + 0.55), (0.7, 3.4, 1.1), wood))
    b.add(B("counterfront", (x + 1.26, y + 0.1, z0 + 0.55), (0.02, 3.2, 0.3), orange))
    b.add(B("countertop", (x + 0.9, y + 0.1, z0 + 1.12), (0.9, 3.6, 0.05), plank))
    b.add(B("termbody", (x + 0.9, y - 0.8, z0 + 1.3), (0.35, 0.5, 0.3), "black"))
    b.add(B("termscreen", (x + 1.08, y - 0.8, z0 + 1.32), (0.02, 0.42, 0.22), "screen"), "lights")
    b.add(C("stamp", (x + 0.9, y + 1.0, z0 + 1.15), (x + 0.9, y + 1.0, z0 + 1.3), 0.06, "brass", segs=8))
    for yy in (y + 0.3, y + 0.55):
        b.add(B("ammobox", (x + 0.9, yy, z0 + 1.22), (0.3, 0.18, 0.15), "olive"))
    for gx in (x - 2.6, x - 0.6):
        b.add(gun_rack("rack", (gx, ys + 0.2, z0), facing=1, n=3, material="gunmetal"))
    for i, cx in enumerate((x - 3.0, x - 1.8, x - 0.6)):
        box_crate(b, (cx, yn - 0.5, z0 + 0.3), (1.0, 0.7, 0.6), m=("olive", orange, "olive")[i])
    box_crate(b, (x - 1.8, yn - 0.5, z0 + 0.85), (0.8, 0.6, 0.5), m=tan)
    b.add(bunk("cot", (x - 3.2, y - 0.3, z0 + 0.5), (0.9, 2.0, 0.15), material="olive", wall=-1))
    b.add(first_aid("aid", (x - 1.4, yn - 0.2, z0 + 1.6), facing=-1))
    bunting(b, (xw + 0.3, y - 2.2, 2.85), (xw + 0.3, y + 2.2, 2.85), sag=0.25, pitch=0.4)
    lamp(b, "lamp.6", (x, y, s[2] - 0.17), rim="black", r=0.18, cage=True)


SPEC = {
    "build": build,
    "name": "The Roost",
    "color": (0.3, 1.0, 0.5),
    "faction": "deserters",
    "body": "home",
    "near_pad": (70.0, 85.0),
    "yaw": 180.0,
    "footprint": (36.0, 29.5),
    "footprint_at": (2.5, -4.0),
    "door": (0.0, -6.85, 1.2),
    "size": (27.4, 33.7, 18.1),
    "depth": 0.3,
    "traffic": "kestrel",
    "nodes": ["lamp.0", "lamp.1", "lamp.2", "lamp.3", "lamp.4", "lamp.5", "lamp.6", "lamp.7", "lamp.8", "flood.0", "flood.1",
              "spin.y.10.0", "spin.y.45.1", "spin.y.50.2", "blink.0", "fire.0", "smoke.0", "smoke.1",
              "sound.wind.0", "sound.radio.1", "sound.fire.2", "sound.generator.3"],
    "boxes": [
        box("floor", (0, 0, 0.15), (22.0, 14.0, 0.3)),
        box("roof", (0, 0, ROOF - 0.15), (22.0, 14.0, 0.3)),
        box("lookout deck", (-4.3, -3.75, ROOF + 0.06), (13.0, 6.1, 0.12)),
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
        box("stair landing", (-12.7, 0.8, 4.08), (3.2, 1.6, 0.12)),
        slope((-13.5, 0.0, 4.2), 1.6, 6.0, 4.3, -1),
        box("bridge", (-12.65, -6.0, ROOF), (3.3, 1.6, 0.12)),
        box("table", (0, 0.5, FLOOR + 0.42), (2.6, 1.3, 0.84)),
        box("mess table", (4.8, 4.9, FLOOR + 0.4), (4.0, 0.9, 0.8)),
        box("radio bench", (8.6, 3.0, FLOOR + 0.47), (1.1, 4.4, 0.94)),
        box("tank", (-6.5, 4.0, ROOF + 1.8), (2.8, 2.8, 3.6)),
        box("genset", (6.5, 8.6, 0.75), (2.6, 1.4, 1.5)),
        box("fuel tank", (9.4, 9.0, 0.65), (0.8, 1.4, 1.3)),
        box("bay crates", (3.3, -9.2, 0.95), (1.4, 1.3, 1.9)),
        box("bay crate", (4.9, -8.6, 0.45), (1.2, 1.1, 0.9)),
        box("cabbage bed", (15.4, -5.0, 0.2), (4.4, 1.2, 0.4)),
        box("tomato bed", (15.4, -7.4, 0.2), (4.4, 1.2, 0.4)),
        box("tunnel west", (14.0, 3.0, 0.8), (0.2, 8.0, 1.6)),
        box("tunnel east", (18.0, 3.0, 0.8), (0.2, 8.0, 1.6)),
        box("tunnel back", (16.0, 7.0, 1.0), (4.2, 0.1, 2.0)),
        *room_boxes("depot", DEPOT[0], DEPOT[1], DEPOT_DOORS),
        box("depot counter", (DEPOT[0][0] + 0.9, DEPOT[0][1] + 0.1, 0.7), (0.7, 3.4, 1.1)),
    ],
    "stations": [
        ("resupply", (DEPOT[0][0] + 2.0, DEPOT[0][1], 1.15), "Quartermaster"),
        ("locker", (5.7, -6.0, FLOOR + 1.0), "Locker"),
    ],
    "crew": [
        ("breaker", (DEPOT[0][0] - 0.3, DEPOT[0][1], 0.15), 90, []),
        ("ghost", (7.3, -5.6, FLOOR), 290, []),
        ("runner", (4.5, -11.4, 0.0), 0, [(4.5, -11.4, 0.0), (12.3, -9.6, 0.0), (12.3, -2.6, 0.0), (19.3, -2.6, 0.0), (19.3, -9.4, 0.0), (13.0, -13.4, 0.0)]),
        ("breaker", (-5.5, -3.5, FLOOR), 0, [(-5.5, -3.5, FLOOR), (-5.5, 2.8, FLOOR), (5.5, 2.8, FLOOR), (5.5, -3.5, FLOOR)]),
        ("ghost", (-4.6, -5.2, DECK), 0, []),
        ("runner", (6.2, -13.6, 0.0), 235, []),
    ],
    "view": {"cam": (30.0, -34.0, 15.0), "look": (2.0, -3.0, 3.5), "lens": 30},
    "annex": {"cam": (-6.6, -15.3, 2.0), "look": (-11.5, -12.8, 1.2), "lens": 22},
    "annex_out": {"cam": (-24.0, -30.0, 6.0), "look": (-6.0, -11.0, 2.0), "lens": 28},
    "inside": {"cam": (0.5, -9.5, FLOOR + 1.6), "look": (0, 2.0, FLOOR + 2.2), "lens": 22},
}
