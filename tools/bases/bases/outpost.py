"""The PMC's Site Vantage on Frost, an airless ice ball: sealed, pressurised white modules with
chamfered hulls and gunmetal pressure ribs, sunk to their sills in pale ice berms behind quilted
navy insulated skirts. An airlock vestibule with a hazard-striped outer door faces the pad down a
lit walkway of chasing bollards; heat-radiator combs stand on the side modules' roofs, a tracking
radar sweeps from a lattice tower to the east and an ice-core drill rig turns its auger in a
derrick to the west. Nothing outside makes a sound: the hum and air handling are indoors.
Inside: the ops module with its desk, screens and server racks under a turning air-handler fan,
the quarters with bunks, lockers and a hydroponic rack, the armoury with gun cages, and the
freight office with the Courier desk."""

import math

import bmesh
import kit as shipkit
from basekit import Base, band, box, door_frame, floodlight, life_node, railing, room, room_boxes, slope, spinner, stair, window
from kit import block, cut, cyl, join, label, prism, sphere, stripe
from interior import (bucket_seat, bunk, cabinet, dash, duct, extinguisher, first_aid, gas_bottle, gun_rack, lamp, overhead,
                      pipe_run, server_rack, turn)

wk = shipkit.wk
wk.PALETTE.update({
    "vantage_navy": ((0.03, 0.055, 0.12), (0.18, 0.22, 0.3), 0.0, 0.75, 0.35, 0),
    "vantage_blue": ((0.03, 0.17, 0.52), (0.25, 0.36, 0.56), 0.0, 0.45, 0.35, 0),
    "frost_ice": ((0.22, 0.3, 0.4), (0.4, 0.48, 0.58), 0.0, 0.55, 0.25, 0),
    "frost_berm": ((0.5, 0.62, 0.76), (0.7, 0.78, 0.86), 0.0, 0.45, 0.2, 0),
    "vantage_panel": ((0.42, 0.44, 0.47), (0.6, 0.62, 0.64), 0.0, 0.45, 0.35, 0),
    "frost_core": ((0.5, 0.78, 0.95), (0.6, 0.8, 0.95), 0.0, 0.1, 0.1, 0),
    "vantage_lining": ((0.24, 0.26, 0.29), (0.42, 0.44, 0.47), 0.2, 0.5, 0.4, 0),
})

JACK = 0.6          # the modules' floors stand this high over the ice, hidden by the berms
WALL = 0.15
FLOOR = JACK + WALL
H = 3.2             # module height, underside to roof
CT, CB = 0.6, 0.25  # top and bottom chamfers of the hull profile
BH = 1.45           # the berms come this far up the walls
CEIL = JACK + H - WALL
white, gm, blue, paint, navy, ice = "ice_white", "gunmetal", "blue_light", "vantage_blue", "vantage_navy", "frost_ice"

# Pods: (centre (x, y), length, width, long axis).
OPS = ((0.0, 6.5), 10.0, 5.4, "x")
QTR = ((-9.5, 2.5), 12.0, 5.0, "y")
ARM = ((9.5, 2.5), 12.0, 5.0, "y")
VEST = ((0.0, 2.15), 3.5, 3.4, "y")
LW = ((-6.0, 6.5), 2.2, 2.4, "x")
LE = ((6.0, 6.5), 2.2, 2.4, "x")
LINK_H = 2.9
DOOR = (1.6, 2.2)

FREIGHT = ((18.0, -4.0), (7.0, 5.0, 3.0))
FREIGHT_DOORS = [("-y", -2.0, 1.6, 2.2)]
FX, FY = FREIGHT[0]
COUNTER_Y = -3.5
DRILL = (-16.6, 2.5)
RADAR = (18.0, 7.5)
TOWER_H = 6.0


def ext(p):
    """A pod's world extents (x0, x1, y0, y1)."""
    (x, y), length, width, axis = p
    sx, sy = (length, width) if axis == "x" else (width, length)
    return (x - sx / 2, x + sx / 2, y - sy / 2, y + sy / 2)


def _profile(cy, w, z0, z1, ct, cb):
    y0, y1 = cy - w / 2, cy + w / 2
    pts = [(y0 + cb, z0), (y1 - cb, z0), (y1, z0 + cb)] if cb else [(y0, z0), (y1, z0)]
    pts += [(y1, z1 - ct), (y1 - ct, z1), (y0 + ct, z1), (y0, z1 - ct)]
    if cb:
        pts.append((y0, z0 + cb))
    return pts


def pod(b, name, p, material, openings, height=H, ct=CT, ribs=(), rib_mat=gm):
    """A pressurised module: a chamfered hull hollowed out, doorways cut through it (openings as in
    `hall`), gunmetal pressure ribs round the skin at `ribs` (offsets along its length) and a
    filler under the floor so nothing shows through the jack space."""
    (cx, cy), length, width, axis = p
    z0, z1 = JACK, JACK + height
    outer = prism(name, _profile(cy, width, z0, z1, ct, CB), length, material, x=cx, bevel=0.04)
    cav = prism("cavity", _profile(cy, width - 2 * WALL, z0 + WALL, z1 - WALL, ct - 0.06, 0), length - 2 * WALL, material, x=cx, bevel=0)
    rib_parts = []
    RW, P = 0.24, 0.08
    for r in ribs:
        rx = cx + r
        rib_parts.append(block("rib", (rx, cy, z1 + P / 2 - 0.01), (RW, width - 2 * ct + 0.12, P), rib_mat, bevel=0))
        zs = BH - 0.25
        for s in (-1, 1):
            rib_parts.append(block("rib", (rx, cy + s * (width / 2 + P / 2 - 0.01), (zs + z1 - ct) / 2), (RW, P, z1 - ct - zs), rib_mat, bevel=0))
            d = (P / 2 - 0.01) * 0.7071
            rib_parts.append(block("rib", (rx, cy + s * (width / 2 - ct / 2) + s * d, z1 - ct / 2 + d), (RW, ct * 1.4142 + 0.06, P), rib_mat, bevel=0, rot=-s * 45))
    if axis == "y":
        for o in [outer, cav] + rib_parts:
            turn(o, (cx, cy, 0), 90)
    x0, x1, y0, y1 = ext(p)
    sx, sy = x1 - x0, y1 - y0
    cutters = [cav]
    for face, off, w, h, zb in openings:
        if face in ("-y", "+y"):
            fy = -1 if face == "-y" else 1
            cutters.append(block("opening", (cx + off, cy + fy * sy / 2, FLOOR + zb + h / 2), (w, WALL * 4, h), material, bevel=0))
        else:
            fx = -1 if face == "-x" else 1
            cutters.append(block("opening", (cx + fx * sx / 2, cy + off, FLOOR + zb + h / 2), (WALL * 4, w, h), material, bevel=0))
    b.add(cut(outer, *cutters))
    for o in rib_parts:
        b.add(o)
    b.add(block("underfill", (cx, cy, JACK / 2), (sx - 0.3, sy - 0.3, JACK + 0.02), gm, bevel=0))
    b.add(block("floor", (cx, cy, FLOOR + 0.01), (sx - 2 * WALL - 0.05, sy - 2 * WALL - 0.05, 0.02), "vantage_lining", bevel=0))


def pod_boxes(name, p, gaps=(), height=H, open_faces=()):
    """Floor, roof and walls of a pod; `gaps` are (face, offset, width) doorways, with a lintel."""
    x0, x1, y0, y1 = ext(p)
    cx, cy, sx, sy = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    z0, z1 = JACK, JACK + height
    out = [box(f"{name} floor", (cx, cy, z0 + WALL / 2), (sx, sy, WALL)), box(f"{name} roof", (cx, cy, z1 - WALL / 2), (sx, sy, WALL))]
    top = FLOOR + DOOR[1]
    for face in ("-y", "+y", "-x", "+x"):
        if face in open_faces:
            continue
        along_x = face in ("-y", "+y")
        f = -1 if face[0] == "-" else 1
        length = sx if along_x else sy
        spans, cur = [], -length / 2
        for off, w in sorted((o, w) for fc, o, w in gaps if fc == face):
            spans += [(cur, off - w / 2, z0, z1), (off - w / 2, off + w / 2, top, z1)]
            cur = off + w / 2
        spans.append((cur, length / 2, z0, z1))
        for a, bb, za, zb in spans:
            if bb - a < 0.01:
                continue
            if along_x:
                out.append(box(f"{name} wall", (cx + (a + bb) / 2, cy + f * (sy / 2 - WALL / 2), (za + zb) / 2), (bb - a, WALL, zb - za)))
            else:
                out.append(box(f"{name} wall", (cx + f * (sx / 2 - WALL / 2), cy + (a + bb) / 2, (za + zb) / 2), (WALL, bb - a, zb - za)))
    return out


def face_run(p, face, a, bb, z, h, proud):
    """Centre and size of a strip on `face` of pod `p` from `a` to `bb` (world x or y)."""
    x0, x1, y0, y1 = ext(p)
    if face in ("-y", "+y"):
        y = y0 - proud / 2 if face == "-y" else y1 + proud / 2
        return ((a + bb) / 2, y, z), (bb - a, proud, h)
    x = x0 - proud / 2 if face == "-x" else x1 + proud / 2
    return (x, (a + bb) / 2, z), (proud, bb - a, h)


def skin(b, p, spans):
    """The pod's exposed faces: a quilted insulated skirt where the hull meets the ice, a painted
    blue band and a lit running strip under the eave. `spans` are (face, from, to) in world x or y."""
    for face, a, bb in spans:
        n = max(1, round((bb - a) / 1.05))
        w = (bb - a) / n
        for i in range(n):
            m = a + i * w + w / 2
            for zc, hh in ((BH - 0.05, 0.5), (BH + 0.47, 0.46)):
                c, s = face_run(p, face, m - (w - 0.07) / 2, m + (w - 0.07) / 2, zc, hh, 0.12)
                b.add(block("quilt", c, s, navy, bevel=0.045, segs=1))
        c, s = face_run(p, face, a, bb, BH + 0.73, 0.06, 0.13)
        b.add(block("skirtcap", c, s, gm, bevel=0))
        c, s = face_run(p, face, a, bb, 2.9, 0.18, 0.02)
        b.add(block("paint", c, s, paint, bevel=0))
        c, s = face_run(p, face, a, bb, JACK + H - CT - 0.12, 0.06, 0.03)
        b.add(block("strip", c, s, blue, bevel=0), "lights")


def wall_label(b, text, p, face, along, z, size, material=paint):
    """Raised lettering on a pod face, `along` its x (for ±y faces) or y."""
    x0, x1, y0, y1 = ext(p)
    if face == "-y":
        at = (along, y0 - 0.02, z)
        b.add(turn(label(text, at, size, material, side=-1, depth=0.02), at, 90))
    elif face == "+y":
        at = (along, y1 + 0.02, z)
        b.add(turn(label(text, at, size, material, side=-1, depth=0.02), at, -90))
    elif face == "-x":
        b.add(label(text, (x0 - 0.02, along, z), size, material, side=-1, depth=0.02))
    else:
        b.add(label(text, (x1 + 0.02, along, z), size, material, side=1, depth=0.02))


def mound(name, outline, h, run, material="frost_berm"):
    """An ice berm banked round `outline` (x0, x1, y0, y1): from `h` at the wall down to the ice
    `run` (w, e, s, n) metres out. Solid; the caller cuts the buildings out of it."""
    x0, x1, y0, y1 = outline
    rw, re, rs, rn = run
    bm = bmesh.new()
    top = [bm.verts.new(v) for v in ((x0 - 0.1, y0 - 0.1, h), (x1 + 0.1, y0 - 0.1, h), (x1 + 0.1, y1 + 0.1, h), (x0 - 0.1, y1 + 0.1, h))]
    bot = [bm.verts.new(v) for v in ((x0 - rw, y0 - rs, -0.05), (x1 + re, y0 - rs, -0.05), (x1 + re, y1 + rn, -0.05), (x0 - rw, y1 + rn, -0.05))]
    bm.faces.new(top)
    bm.faces.new(list(reversed(bot)))
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return wk._obj(name, bm, material, 0.6, 3)


def parcel_box(name, c, s, material="grey", band="black"):
    """A cheap crate: a box with a painted band round it and a dark lid line (the interior kit's
    crate costs ~750 triangles; this costs 36)."""
    x, y, z = c
    return join([block(name, c, s, material, bevel=0),
                 block("band", (x, y, z - s[2] * 0.1), (s[0] + 0.02, s[1] + 0.02, s[2] * 0.22), band, bevel=0),
                 block("lid", (x, y, z + s[2] / 2 - 0.05), (s[0] + 0.015, s[1] + 0.015, 0.03), "black", bevel=0)], name)


def lining(b, p, gaps=(), height=H, ct=CT, open_faces=(), upper="vantage_panel"):
    """Panels on a pod's inner walls, a dark dado under a grey upper panel, with `gaps` (face,
    offset, width) left for doorways and portholes, so the white hull does not glare inside."""
    x0, x1, y0, y1 = ext(p)
    cx, cy, sx, sy = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    top = JACK + height - WALL - (ct - 0.06) - 0.05
    bands = ((FLOOR + 0.01, FLOOR + 1.0, "vantage_lining"), (FLOOR + 1.04, top, upper))
    for face in ("-y", "+y", "-x", "+x"):
        if face in open_faces:
            continue
        along_x = face in ("-y", "+y")
        f = -1 if face[0] == "-" else 1
        length = (sx if along_x else sy) - 2 * WALL - 0.02
        spans, cur = [], -length / 2
        for off, w in sorted((o, w) for fc, o, w in gaps if fc == face):
            spans.append((cur, off - w / 2))
            cur = off + w / 2
        spans.append((cur, length / 2))
        for a, bb in spans:
            if bb - a < 0.05:
                continue
            for za, zb, m in bands:
                if along_x:
                    c, size = (cx + (a + bb) / 2, cy + f * (sy / 2 - WALL - 0.015), (za + zb) / 2), (bb - a, 0.03, zb - za)
                else:
                    c, size = (cx + f * (sx / 2 - WALL - 0.015), cy + (a + bb) / 2, (za + zb) / 2), (0.03, bb - a, zb - za)
                b.add(block("lining", c, size, m, bevel=0))


def berm_box(name, face, wall, a, bb, h, run, t=0.5):
    """A tilted collision slab lying on a berm's face: `face` names the wall it leans on, `wall` the
    wall's x or y, `a`..`bb` its extent along the wall."""
    L = math.hypot(run, h)
    th = math.degrees(math.atan2(h, run))
    d = -1 if face[0] == "-" else 1
    nh, nz = d * h / L, run / L
    if face in ("-x", "+x"):
        c = (wall + d * run / 2 - nh * t / 2, (a + bb) / 2, h / 2 - nz * t / 2)
        return (name, c, (L, bb - a, t), (0, d * th, 0))
    c = ((a + bb) / 2, wall + d * run / 2 - nh * t / 2, h / 2 - nz * t / 2)
    return (name, c, (bb - a, L, t), (-d * th, 0, 0))


# Berms: (pod, run (w, e, s, n), height). The freight office has a lower one, open to the south.
BERMS = [
    (OPS, (2.0, 2.0, 1.6, 2.2), BH),
    (QTR, (2.2, 1.6, 2.2, 2.2), BH),
    (ARM, (1.6, 2.0, 2.2, 2.2), BH),
]
FREIGHT_BERM = ((1.0, 1.0, 0.0, 1.0), 0.8)


def berms(b):
    s = FREIGHT[1]
    froom = (FX - s[0] / 2, FX + s[0] / 2, FY - s[1] / 2, FY + s[1] / 2)
    # Inset 0.08 so the cut faces hide inside the walls; the airlock and links reach on into the
    # modules they join, so no sliver of ice is left across their doorways.
    vx0, vx1, vy0, vy1 = ext(VEST)
    holes = [ext(p) for p in (OPS, QTR, ARM)] + [froom, (vx0, vx1, vy0, vy1 + 0.5)]
    for p in (LW, LE):
        x0, x1, y0, y1 = ext(p)
        holes.append((x0 - 0.5, x1 + 0.5, y0, y1))

    def cutters():
        return [block("hole", ((x0 + x1) / 2, (y0 + y1) / 2, 1.0), (x1 - x0 - 0.16, y1 - y0 - 0.16, 6.0), ice, bevel=0) for x0, x1, y0, y1 in holes]
    for p, run, h in BERMS:
        b.add(cut(mound("berm", ext(p), h, run), *cutters()))
    b.add(cut(mound("berm", froom, FREIGHT_BERM[1], FREIGHT_BERM[0]), *cutters()))
    # Ice lumps cut from the walkway and pushed aside.
    for x, y, sz in ((-6.0, -6.8, 1.1), (-14.5, -7.5, 1.4), (6.6, -6.6, 0.9), (13.0, 10.6, 1.2), (-19.0, 9.5, 1.3), (22.0, 10.0, 1.0), (-19.2, -9.6, 1.0)):
        b.add(block("lump", (x, y, sz * 0.25), (sz * 1.4, sz, sz * 0.6), "frost_berm", bevel=sz * 0.22, segs=2))


def berm_boxes():
    out = []
    for p, (rw, re, rs, rn), h in BERMS:
        x0, x1, y0, y1 = ext(p)
        for face, wall, a, bb, run in (("-x", x0, y0, y1, rw), ("+x", x1, y0, y1, re), ("-y", y0, x0, x1, rs), ("+y", y1, x0, x1, rn)):
            if run >= 2.0:
                out.append(berm_box("berm", face, wall, a, bb, h, run))
    return out


def build():
    b = Base("outpost")
    # The ice apron the site was levelled into.
    b.add(block("apron", (1.5, 0.3, -0.15), (43.0, 22.6, 0.3), ice, bevel=0.05))
    modules(b)
    berms(b)
    airlock(b)
    roofs(b)
    approach(b)
    drill(b)
    radar(b)
    ops_inside(b)
    quarters_inside(b)
    armoury_inside(b)
    freight(b)
    sounds(b)
    return b


def modules(b):
    pod(b, "ops", OPS, white, [("-y", 0.0, *DOOR, 0), ("-x", 0.0, *DOOR, 0), ("+x", 0.0, *DOOR, 0)], ribs=(-4.85, -2.6, 2.6, 4.85))
    pod(b, "quarters", QTR, white, [("+x", 4.0, *DOOR, 0), ("-x", -2.0, 1.2, 0.5, 1.5), ("-x", 2.5, 1.2, 0.5, 1.5)], ribs=(-5.85, -2.9, 0.4, 5.85))
    pod(b, "armoury", ARM, white, [("-x", 4.0, *DOOR, 0), ("+x", -1.0, 1.2, 0.5, 1.5)], ribs=(-5.85, -2.9, 0.4, 5.85))
    pod(b, "airlock", VEST, white, [("-y", 0.0, *DOOR, 0), ("+y", 0.0, *DOOR, 0)], ribs=(-1.6, 1.0))
    for name, p in (("westlink", LW), ("eastlink", LE)):
        pod(b, name, p, gm, [("-x", 0.0, *DOOR, 0), ("+x", 0.0, *DOOR, 0)], height=LINK_H, ct=0.5)
        (x, y), *_ = p
        for dx in (-0.55, 0.55):
            b.add(block("collar", (x + dx, y, JACK + LINK_H / 2), (0.18, 2.6, LINK_H + 0.1), white, bevel=0.03))
        for sy in (-1, 1):
            b.add(block("linkstrip", (x, y + sy * 1.21, JACK + 2.3), (0.8, 0.03, 0.06), blue, bevel=0), "lights")
    D = DOOR[0] + 0.1
    lining(b, OPS, [("-y", 0.0, D), ("-x", 0.0, D), ("+x", 0.0, D)])
    lining(b, QTR, [("+x", 4.0, D), ("-x", -2.0, 1.4), ("-x", 2.5, 1.4)])
    lining(b, ARM, [("-x", 4.0, D), ("+x", -1.0, 1.4)])
    lining(b, VEST, [("-y", 0.0, D + 1.5), ("+y", 0.0, D)], upper=gm)
    ox0, ox1, oy0, oy1 = ext(OPS)
    qx0, qx1, qy0, qy1 = ext(QTR)
    ax0, ax1, ay0, ay1 = ext(ARM)
    vx0, vx1, vy0, vy1 = ext(VEST)
    skin(b, OPS, [("+y", ox0, ox1), ("-y", ox0, vx0), ("-y", vx1, ox1), ("-x", oy0, 5.3), ("-x", 7.7, oy1), ("+x", oy0, 5.3), ("+x", 7.7, oy1)])
    skin(b, QTR, [("-x", qy0, qy1), ("-y", qx0, qx1), ("+y", qx0, qx1), ("+x", qy0, 5.3), ("+x", 7.7, qy1)])
    skin(b, ARM, [("+x", ay0, ay1), ("-y", ax0, ax1), ("+y", ax0, ax1), ("-x", ay0, 5.3), ("-x", 7.7, ay1)])
    skin(b, VEST, [("-x", vy0, 3.8), ("+x", vy0, 3.8)])
    # Painted graphics: module numbers on the ends facing the pad, the site name down the west side.
    wall_label(b, "HAB-1", QTR, "-y", -9.5, 2.5, 0.5)
    wall_label(b, "ARM-2", ARM, "-y", 9.5, 2.5, 0.5)
    wall_label(b, "VANTAGE", QTR, "-x", 2.75, 2.5, 0.5)
    wall_label(b, "OPS-0", OPS, "+y", 0.0, 2.5, 0.5)
    for p, x in ((QTR, -9.5), (ARM, 9.5)):
        y0 = ext(p)[2]
        for k in range(3):
            b.add(stripe("chev", (x - 2.2 + k * 0.35, y0 - 0.02, 2.5), (0.16, 0.02, 0.5), "hazard"))
            b.add(stripe("chev", (x + 2.2 - k * 0.35, y0 - 0.02, 2.5), (0.16, 0.02, 0.5), "hazard"))
    # Portholes: the quarters' on the west, the armoury's on the east, the ops' over the north berm.
    for y in (0.5, 5.0):
        window(b, (qx0 - 0.03, y, FLOOR + 1.75), (0.1, 1.2, 0.5), frame=gm)
    window(b, (ax1 + 0.03, 1.5, FLOOR + 1.75), (0.1, 1.2, 0.5), frame=gm)
    for x in (-3.0, 3.0):
        window(b, (x, oy1 + 0.03, FLOOR + 1.75), (1.8, 0.1, 0.5), frame=gm)


def airlock(b):
    """The way in: a heavy hazard-striped frame round the outer door, its leaves slid back into the
    wall, a cycle light over it, the site name on a header, steps down to the walkway."""
    vx0, vx1, vy0, vy1 = ext(VEST)
    door_frame(b, (0, vy0 - 0.08, FLOOR), DOOR[0], DOOR[1], material=gm, depth=0.5, thick=0.22)
    for sx in (-1, 1):
        for k in range(4):
            b.add(stripe("chev", (sx * 0.91, vy0 - 0.34, FLOOR + 0.35 + k * 0.55), (0.2, 0.02, 0.24), "hazard"))
    b.add(block("header", (0, vy0 - 0.12, 3.45), (2.3, 0.14, 0.5), gm, bevel=0.02))
    at = (0, vy0 - 0.2, 3.45)
    b.add(turn(label("VANTAGE", at, 0.34, blue, side=-1, depth=0.015), at, 90), "lights")
    b.add(cyl("cyclelight", (0, vy0 - 0.35, FLOOR + 2.55), (0, vy0 - 0.15, FLOOR + 2.55), 0.09, "green_light", segs=10, bevel=0), "lights")
    stair(b, (0, vy0 - 1.6, 0), 1.8, 1.6, FLOOR, 4, material=gm, facing=1)
    for sx in (-1, 1):
        railing(b, (sx * 0.95, vy0 - 1.6, 0), (sx * 0.95, vy0 - 0.3, FLOOR), spacing=1.2)
    # Inside the lock: leaves pocketed each side, suits on the walls, a pressure panel.
    for sx in (-1, 1):
        b.add(block("leaf", (sx * 1.18, vy0 + WALL + 0.03, FLOOR + 1.1), (0.72, 0.05, 2.2), gm, bevel=0.01))
        b.add(stripe("leafstripe", (sx * 1.18, vy0 + WALL + 0.06, FLOOR + 1.1), (0.7, 0.01, 0.12), "hazard"))
        for y in (1.3, 2.6):
            x = sx * (vx1 - WALL - 0.22)
            b.add(cyl("suit", (x, y, FLOOR + 0.55), (x, y, FLOOR + 1.6), 0.2, white, segs=10, bevel=0.02))
            b.add(block("suitpack", (x + sx * 0.14, y, FLOOR + 1.3), (0.14, 0.36, 0.5), gm, bevel=0.02))
            b.add(sphere("helmet", (x, y, FLOOR + 1.82), 0.17, white, segs=10))
            b.add(block("visor", (x - sx * 0.12, y, FLOOR + 1.83), (0.06, 0.2, 0.1), blue, bevel=0.01), "lights")
            b.add(block("suitband", (x - sx * 0.2, y, FLOOR + 1.15), (0.02, 0.3, 0.08), "hazard", bevel=0))
    b.add(block("panel", (0.95, vy1 - 0.2, FLOOR + 1.4), (0.4, 0.05, 0.5), gm, bevel=0.01))
    b.add(block("panelscreen", (0.95, vy1 - 0.23, FLOOR + 1.45), (0.3, 0.01, 0.3), "screen", bevel=0), "lights")
    b.add(stripe("threshold", (0, vy0 + 0.45, FLOOR + 0.02), (1.6, 0.25, 0.01), "hazard"))
    b.add(stripe("threshold", (0, vy1 - 0.45, FLOOR + 0.02), (1.6, 0.25, 0.01), "hazard"))
    lamp(b, "lamp.6", (0, 2.15, CEIL - 0.02), rim=gm, r=0.14, cage=True)


def roofs(b):
    """Radiator combs on the side modules, the comms mast and air plant on the ops roof."""
    top = JACK + H
    for p in (QTR, ARM):
        (x, y), *_ = p
        b.add(cyl("manifold", (x, y - 4.8, top + 0.2), (x, y + 2.6, top + 0.2), 0.1, gm, segs=10, bevel=0))
        for k in (-1, 1):
            b.add(cyl("coolant", (x + k * 0.5, y - 4.8, top + 0.12), (x + k * 0.5, y + 2.6, top + 0.12), 0.05, paint, segs=8, bevel=0))
        for i in range(9):
            yy = y - 4.6 + i * 0.9
            b.add(block("fin", (x, yy, top + 0.95), (2.9, 0.07, 1.4), white, bevel=0.01))
            b.add(block("fincap", (x, yy, top + 1.68), (2.95, 0.1, 0.07), gm, bevel=0))
            b.add(block("finfoot", (x, yy, top + 0.12), (3.0, 0.22, 0.2), gm, bevel=0))
        b.add(block("plant", (x, y + 4.4, top + 0.45), (1.8, 1.6, 0.9), white, bevel=0.04))
        b.add(cyl("plantfan", (x, y + 4.4, top + 0.9), (x, y + 4.4, top + 0.94), 0.55, "black", segs=16, bevel=0))
    # Ops: the comms mast with its strobe, an air plant, two pressure relief stacks.
    mx, my = -3.6, 8.0
    b.add(cyl("mastfoot", (mx, my, top), (mx, my, top + 0.4), 0.3, gm, segs=12, bevel=0.01))
    b.add(cyl("mast", (mx, my, top), (mx, my, top + 7.0), 0.07, "steel", segs=10, bevel=0))
    for i, zz in enumerate((4.0, 5.5, 6.6)):
        L = 0.8 - i * 0.2
        b.add(cyl("arm", (mx - L, my, top + zz), (mx + L, my, top + zz), 0.03, "steel", segs=6, bevel=0))
        for sx in (-1, 1):
            b.add(cyl("whip", (mx + sx * L, my, top + zz), (mx + sx * L, my, top + zz + 0.6), 0.015, "steel", segs=5, bevel=0))
    b.add(sphere("strobehead", (mx, my, top + 7.1), 0.12, "flood", segs=10), "lights")
    life_node(b, "strobe", 2, (mx, my, top + 7.25))
    b.add(block("airplant", (2.2, 7.4, top + 0.4), (2.4, 1.4, 0.8), white, bevel=0.04))
    b.add(block("airgrille", (2.2, 6.68, top + 0.45), (2.0, 0.03, 0.5), "black", bevel=0))
    for x in (-1.0, 0.0):
        b.add(cyl("stack", (x, 7.8, top), (x, 7.8, top + 0.9), 0.12, gm, segs=8, bevel=0))
        b.add(cyl("stackcap", (x, 7.8, top + 0.9), (x, 7.8, top + 1.0), 0.2, white, segs=8, bevel=0))


BOLLARDS = [(-1.5 if i % 2 == 0 else 1.5, -10.4 + i * 1.6) for i in range(6)]


def approach(b):
    """The walkway from the pad to the steps, lit by bollards that chase toward the door, a spur to
    the freight office, floodlights at the pad edge, a strobe on each pad corner, a parked sled."""
    y_end = ext(VEST)[2] - 1.6
    L = y_end + 11.0
    b.add(block("walk", (0, -11.0 + L / 2, 0.03), (2.4, L, 0.06), gm, bevel=0.01))
    for sx in (-1, 1):
        b.add(stripe("walkedge", (sx * 1.15, -11.0 + L / 2, 0.065), (0.1, L, 0.01), "hazard"))
    b.add(block("spur", (8.6, -8.6, 0.03), (14.6, 1.6, 0.06), gm, bevel=0.01))
    b.add(block("spur", (16.0, -7.55, 0.03), (1.6, 1.3, 0.06), gm, bevel=0.01))
    for i, (x, y) in enumerate(BOLLARDS):
        b.add(cyl("bollard", (x, y, 0), (x, y, 0.55), 0.11, gm, segs=10, bevel=0.01))
        b.add(cyl("bollardlens", (x, y, 0.55), (x, y, 0.68), 0.09, "red_light", segs=10, bevel=0), "lights")
        b.add(stripe("bollardband", (x, y, 0.35), (0.23, 0.23, 0.07), "hazard"))
        life_node(b, "blink", i, (x, y, 0.75))
    for i, sx in enumerate((-1, 1)):
        x = sx * 12.4
        b.add(cyl("padpost", (x, -10.6, 0), (x, -10.6, 1.2), 0.08, gm, segs=10, bevel=0))
        b.add(block("padplate", (x, -10.6, 0.7), (0.4, 0.05, 0.3), "hazard", bevel=0))
        b.add(sphere("padstrobe", (x, -10.6, 1.3), 0.12, "flood", segs=10), "lights")
        life_node(b, "strobe", i, (x, -10.6, 1.45))
    floodlight(b, "flood.0", (-5.5, -10.2, 0), 5.0, aim=(0, -1))
    floodlight(b, "flood.1", (5.5, -10.2, 0), 5.0, aim=(0, -1))
    # A tracked sled in the yard between the modules, gas bottles and a pallet across from it.
    sx, sy = 3.4, -1.2
    for k in (-1, 1):
        b.add(block("track", (sx + k * 0.75, sy, 0.3), (0.45, 3.0, 0.6), "black", bevel=0.12, segs=2))
    b.add(block("sledbody", (sx, sy, 0.9), (1.6, 2.6, 0.7), white, bevel=0.05))
    b.add(block("sledcab", (sx, sy + 0.5, 1.55), (1.4, 1.2, 0.7), white, bevel=0.06))
    b.add(block("sledglass", (sx, sy - 0.12, 1.6), (1.2, 0.04, 0.45), "glass", bevel=0), "glass")
    b.add(stripe("sledband", (sx, sy, 1.0), (1.62, 2.62, 0.12), paint))
    for k in (-1, 1):
        b.add(cyl("sledlamp", (sx + k * 0.5, sy - 1.3, 1.05), (sx + k * 0.5, sy - 1.34, 1.05), 0.08, "flood", segs=8, bevel=0), "lights")
    for i, x in enumerate((-3.6, -3.25, -2.9)):
        b.add(gas_bottle("gas", (x, -2.9, 0), material=white if i != 1 else "red"))
    b.add(block("gasrack", (-3.25, -3.1, 0.8), (1.2, 0.08, 0.08), gm, bevel=0))
    b.add(parcel_box("pallet", (-3.6, -1.2, 0.45), (1.3, 1.1, 0.9), material="grey", band=blue))
    b.add(parcel_box("pallet", (-3.6, -1.2, 1.2), (1.0, 0.8, 0.6), material=white, band="black"))


def _frame(feet, heads, levels, b, leg_mat, brace_mat, leg_r, cross=False):
    """A tapered four-leg lattice from `feet` to `heads` with ring braces and diagonals."""
    for f, hd in zip(feet, heads):
        b.add(cyl("leg", f, hd, leg_r, leg_mat, segs=8, bevel=0))

    def at(i, t):
        return tuple(feet[i][k] + (heads[i][k] - feet[i][k]) * t for k in range(3))
    order = (0, 1, 3, 2)
    for li, t in enumerate(levels[1:]):
        for k in range(4):
            i, j = order[k], order[(k + 1) % 4]
            b.add(cyl("brace", at(i, t), at(j, t), leg_r * 0.5, brace_mat, segs=6, bevel=0))
            b.add(cyl("diag", at(i, levels[li]), at(j, t), leg_r * 0.35, brace_mat, segs=5, bevel=0))
            if cross:
                b.add(cyl("diag", at(j, levels[li]), at(i, t), leg_r * 0.35, brace_mat, segs=5, bevel=0))


def drill(b):
    """The ice-core rig west of the quarters: a deck over the bore, a tapered derrick with a crown
    block and a beacon, a top drive turning the drill string and its auger, a winch hut and a rack
    of cores laid out in a tray."""
    x, y = DRILL
    deck = 0.45
    b.add(block("rigdeck", (x, y, deck / 2), (3.4, 3.4, deck), gm, bevel=0.02))
    for sx in (-1, 1):
        b.add(stripe("deckedge", (x, y + sx * 1.69, deck - 0.05), (3.4, 0.04, 0.1), "hazard"))
        b.add(stripe("deckedge", (x + sx * 1.69, y, deck - 0.05), (0.04, 3.4, 0.1), "hazard"))
    b.add(cyl("casing", (x, y, deck), (x, y, deck + 0.35), 0.38, "steel", segs=16, bevel=0.01))
    b.add(cyl("table", (x, y, deck), (x, y, deck + 0.12), 0.7, "black", segs=16, bevel=0.01))
    top = 9.6
    feet = [(x + sx * 1.5, y + sy * 1.5, deck) for sx in (-1, 1) for sy in (-1, 1)]
    heads = [(x + sx * 0.35, y + sy * 0.35, top) for sx in (-1, 1) for sy in (-1, 1)]
    _frame(feet, heads, (0.0, 0.27, 0.52, 0.74, 0.92), b, white, gm, 0.08)
    b.add(block("crown", (x, y, top + 0.2), (1.1, 1.1, 0.4), "hazard", bevel=0.03))
    b.add(cyl("beaconpole", (x + 0.4, y + 0.4, top + 0.4), (x + 0.4, y + 0.4, top + 0.9), 0.03, "steel", segs=6, bevel=0))
    b.add(sphere("beacon", (x + 0.4, y + 0.4, top + 0.95), 0.1, "red_light", segs=10), "lights")
    life_node(b, "blink", 6, (x + 0.4, y + 0.4, top + 1.1))
    # Guide rails and the top drive's frame (still); the rotor and drill string under it (turning).
    for sx in (-1, 1):
        b.add(cyl("guiderail", (x + sx * 0.5, y + 0.55, deck + 0.5), (x + sx * 0.5, y + 0.55, top - 0.3), 0.05, "steel", segs=6, bevel=0))
    b.add(block("topdrive", (x, y + 0.2, 6.55), (1.2, 0.9, 0.7), "hazard", bevel=0.04))
    b.add(block("topdriveplate", (x, y - 0.26, 6.55), (0.8, 0.03, 0.4), "black", bevel=0))
    b.add(block("motor", (x, y + 0.2, 7.15), (0.6, 0.6, 0.5), gm, bevel=0.03))
    b.add(cyl("hoistline", (x, y + 0.2, 7.4), (x, y + 0.2, top), 0.025, "black", segs=6, bevel=0))
    parts = [cyl("rotor", (x, y, 5.75), (x, y, 6.2), 0.36, gm, segs=12, bevel=0.01),
             block("lug", (x + 0.36, y, 5.97), (0.24, 0.16, 0.3), "hazard", bevel=0.01),
             block("lug", (x - 0.36, y, 5.97), (0.24, 0.16, 0.3), "hazard", bevel=0.01),
             cyl("drillpipe", (x, y, deck - 0.2), (x, y, 5.75), 0.09, "steel", segs=10, bevel=0)]
    for zz in (3.2, 4.0, 4.8):
        parts.append(cyl("pipeband", (x, y, zz), (x, y, zz + 0.22), 0.1, "red", segs=10, bevel=0))
    # The auger flight: a helix of short segments round the pipe above the bore.
    n, turns, z0, z1, r = 54, 4.5, deck + 0.4, deck + 2.6, 0.26
    pts = [(x + r * math.cos(i / n * turns * math.tau), y + r * math.sin(i / n * turns * math.tau), z0 + (z1 - z0) * i / n) for i in range(n + 1)]
    for p0, p1 in zip(pts, pts[1:]):
        parts.append(cyl("flight", p0, p1, 0.07, "hazard", segs=6, bevel=0))
    for i in range(0, n, 3):
        parts.append(cyl("web", (x, y, pts[i][2]), pts[i], 0.03, "steel", segs=5, bevel=0))
    spinner(b, 1, (x, y, deck), "z", 40, parts)
    # Winch hut north of the deck, cable to the drum, a hose to the quarters.
    hx, hy = x, y + 3.3
    b.add(block("hut", (hx, hy, 1.1), (2.4, 1.8, 2.2), white, bevel=0.04))
    b.add(block("hutroof", (hx, hy, 2.25), (2.6, 2.0, 0.12), gm, bevel=0.02))
    b.add(stripe("hutband", (hx, hy, 1.6), (2.42, 1.82, 0.25), paint))
    at = (hx, hy - 0.92, 1.0)
    b.add(turn(label("CORE-3", at, 0.3, gm, side=-1, depth=0.015), at, 90))
    b.add(cyl("drum", (hx - 0.7, hy - 1.15, 0.5), (hx + 0.7, hy - 1.15, 0.5), 0.3, "hazard", segs=14, bevel=0.01))
    b.add(cyl("cable", (hx, hy - 1.15, 0.8), (x, y + 0.6, top - 0.1), 0.02, "black", segs=5, bevel=0))
    pipe_run(b, [(hx + 1.2, hy, 0.25), (-13.6, hy, 0.25), (-13.6, hy, 1.2)], r=0.06, material="black", brackets=1.5)
    # Cores laid in a tray on trestles, and core boxes.
    tx, ty = x - 2.6, y - 1.6
    b.add(block("tray", (tx, ty, 0.9), (0.9, 2.6, 0.1), gm, bevel=0.01))
    for sy in (-1, 1):
        b.add(block("trestle", (tx, ty + sy * 1.0, 0.43), (0.8, 0.08, 0.85), "steel", bevel=0))
    for k in range(4):
        b.add(cyl("core", (tx - 0.3 + k * 0.2, ty - 1.15, 1.02), (tx - 0.3 + k * 0.2, ty + 1.15, 1.02), 0.07, "frost_core", segs=8, bevel=0))
    for yy in (ty + 2.0, ty + 2.7):
        b.add(parcel_box("corebox", (tx, yy, 0.3), (0.9, 0.6, 0.6), material=white, band=blue))


def radar(b):
    """The tracking radar on its lattice tower east of the armoury: a platform with a rail and a
    beacon, and the dish on its turret sweeping the sky."""
    x, y = RADAR
    h = TOWER_H
    feet = [(x + sx * 1.2, y + sy * 1.2, 0) for sx in (-1, 1) for sy in (-1, 1)]
    heads = [(x + sx * 0.75, y + sy * 0.75, h) for sx in (-1, 1) for sy in (-1, 1)]
    _frame(feet, heads, (0.05, 0.35, 0.68, 1.0), b, gm, "steel", 0.09, cross=True)
    for f in feet:
        b.add(block("towerfoot", (f[0], f[1], 0.15), (0.6, 0.6, 0.3), "concrete", bevel=0.02))
    b.add(block("platform", (x, y, h + 0.08), (2.4, 2.4, 0.16), gm, bevel=0.02))
    b.add(stripe("platedge", (x, y, h + 0.1), (2.42, 2.42, 0.06), "hazard"))
    for sx in (-1, 1):
        railing(b, (x + sx * 1.15, y - 1.15, h + 0.16), (x + sx * 1.15, y + 1.15, h + 0.16), h=0.9, spacing=1.1)
    b.add(cyl("beaconpole", (x + 1.1, y + 1.1, h + 0.16), (x + 1.1, y + 1.1, h + 1.6), 0.03, "steel", segs=6, bevel=0))
    b.add(sphere("beacon", (x + 1.1, y + 1.1, h + 1.65), 0.1, "red_light", segs=10), "lights")
    life_node(b, "blink", 7, (x + 1.1, y + 1.1, h + 1.8))
    b.add(cyl("bearing", (x, y, h + 0.16), (x, y, h + 0.45), 0.55, "steel", segs=16, bevel=0.01))
    # The turning part: turret, yoke, the dish tilted up toward -Y, its feed and counterweight.
    z = h + 0.45
    el = math.radians(40)
    tilt = (0.0, -math.cos(el), math.sin(el))
    up = (0.0, math.sin(el), math.cos(el))
    c = (x, y - 0.15, z + 1.55)

    def along(t, o=(0.0, 0.0)):
        return tuple(c[k] + tilt[k] * t + (o[0] if k == 0 else 0.0) + up[k] * o[1] for k in range(3))
    parts = [cyl("turret", (x, y, z), (x, y, z + 0.6), 0.5, white, segs=14, bevel=0.02),
             block("turretband", (x, y, z + 0.3), (1.02, 1.02, 0.14), paint, bevel=0),
             block("yoke", (x, y, z + 0.8), (1.6, 0.4, 0.4), gm, bevel=0.02)]
    for sx in (-1, 1):
        parts.append(block("yokearm", (x + sx * 0.75, y, z + 1.25), (0.16, 0.36, 1.1), gm, bevel=0.02))
    parts.append(cyl("trunnion", (x - 0.85, c[1], c[2]), (x + 0.85, c[1], c[2]), 0.1, "steel", segs=10, bevel=0))
    parts.append(cyl("dishback", along(-0.35), along(0.0), 0.45, gm, r1=0.9, segs=16, bevel=0.01))
    parts.append(cyl("dish", along(0.0), along(0.45), 0.9, white, r1=2.3, segs=28, bevel=0.01))
    parts.append(cyl("dishrim", along(0.44), along(0.5), 2.33, paint, segs=28, bevel=0))
    parts.append(cyl("dishface", along(0.49), along(0.53), 1.9, white, segs=28, bevel=0))
    for a in (90, 210, 330):
        o = (math.cos(math.radians(a)) * 2.0, math.sin(math.radians(a)) * 2.0)
        parts.append(cyl("strut", along(0.5, o), along(1.8), 0.025, gm, segs=5, bevel=0))
    parts.append(cyl("feed", along(0.5), along(1.8), 0.05, "black", segs=8, bevel=0))
    parts.append(cyl("horn", along(1.7), along(2.0), 0.18, gm, r1=0.08, segs=10, bevel=0))
    parts.append(block("counterweight", (x, y + 0.9, z + 0.8), (1.0, 0.6, 0.6), gm, bevel=0.03))
    parts.append(stripe("cwband", (x, y + 0.9, z + 0.8), (1.02, 0.62, 0.12), "hazard"))
    spinner(b, 0, (x, y, z), "z", 6, parts)
    pipe_run(b, [(x - 1.2, y - 1.2, 0.2), (14.6, y - 1.2, 0.2)], r=0.07, material="black", brackets=1.5)


def ops_inside(b):
    """Ops: the desk under its screens, two seats, racks humming in rows, a wall display, lockers,
    a coffee corner and the air-handler fan turning in the ceiling."""
    x0, x1, y0, y1 = ext(OPS)
    dash(b, (0, y1 - WALL - 0.4, FLOOR), 3.4, material=white, screens=5, screen_mat=blue, facing=1)
    for x in (-0.7, 0.7):
        b.add(bucket_seat("seat", (x, y1 - 1.6, FLOOR + 0.5), facing=1, material="black", frame=white, trim="steel"))
    overhead(b, (0, y1 - 1.0, CEIL - 0.08), (1.8, 0.5, 0.06), material=white, facing=1, light_mat=blue)
    for x in (-4.3, -3.65, -3.0):
        server_rack(b, (x, y1 - WALL - 0.3, FLOOR + 0.95), (0.6, 0.5, 1.9), material=white)
        b.add(turn_rack(b, (x, y0 + WALL + 0.3, FLOOR + 0.95), 180))
    for x in (3.7, 4.3):
        c = (x, y1 - WALL - 0.3, FLOOR + 0.95)
        b.add(cabinet("locker", c, (0.55, 0.5, 1.9), material=white, doors=1))
    ys = y0 + WALL + 0.03
    b.add(block("wallscreenframe", (3.0, ys, FLOOR + 1.6), (2.0, 0.05, 1.2), "black", bevel=0.01))
    b.add(block("wallscreen", (3.0, ys + 0.03, FLOOR + 1.6), (1.8, 0.02, 1.0), "screen", bevel=0), "lights")
    for i in range(4):
        b.add(block("wallbar", (2.4 + i * 0.4, ys + 0.045, FLOOR + 1.3 + 0.12 * i), (0.22, 0.01, 0.14 + 0.08 * i), blue, bevel=0), "lights")
    b.add(block("statusstrip", (0, y1 - WALL - 0.02, FLOOR + 2.3), (3.4, 0.03, 0.08), blue, bevel=0), "lights")
    b.add(block("coffeetable", (4.2, 5.0, FLOOR + 0.5), (0.7, 0.7, 0.05), white, bevel=0.01))
    b.add(cyl("coffeeleg", (4.2, 5.0, FLOOR), (4.2, 5.0, FLOOR + 0.5), 0.05, gm, segs=8, bevel=0))
    b.add(cyl("kettle", (4.2, 5.0, FLOOR + 0.53), (4.2, 5.0, FLOOR + 0.8), 0.1, "steel", segs=10, bevel=0.01))
    for dx in (-0.2, 0.2):
        b.add(cyl("mug", (4.2 + dx, 5.15, FLOOR + 0.53), (4.2 + dx, 5.15, FLOOR + 0.62), 0.04, "red", segs=8, bevel=0))
    b.add(first_aid("aid", (-1.8, y0 + WALL + 0.02, FLOOR + 1.5), facing=1))
    b.add(duct("duct", (x0 + 0.3, y1 - 0.9, CEIL - 0.2), (-1.0, y1 - 0.9, CEIL - 0.2), (0, 0.4, 0.2), material=gm, flange=1.5))
    for i, x in enumerate((-2.5, 2.5)):
        lamp(b, f"lamp.{i}", (x, 6.5, CEIL - 0.02), rim=white, r=0.18)
    # The fan: a housing in the ceiling (still), four blades and a cap under it (turning).
    fx, fy = 0.0, 6.2
    b.add(cyl("fanhousing", (fx, fy, CEIL - 0.12), (fx, fy, CEIL), 0.62, gm, segs=20, bevel=0.01))
    b.add(cyl("fanhub", (fx, fy, CEIL - 0.3), (fx, fy, CEIL - 0.12), 0.1, "black", segs=10, bevel=0))
    blades = [cyl("hubcap", (fx, fy, CEIL - 0.34), (fx, fy, CEIL - 0.26), 0.14, white, segs=10, bevel=0)]
    for a in (0, 90, 180, 270):
        blades.append(turn(block("blade", (fx + 0.32, fy, CEIL - 0.3), (0.5, 0.14, 0.025), white if a % 180 else paint, bevel=0), (fx, fy, 0), a))
    spinner(b, 2, (fx, fy, CEIL - 0.3), "z", 90, blades)


def turn_rack(b, c, yaw):
    """A server rack facing +Y (its door toward the room from the north wall): built facing -Y in
    a scratch list, then swung round."""
    parts = []

    class Scratch:
        def add(self, obj, group="hull"):
            parts.append((obj, group))
            return obj
    server_rack(Scratch(), c, (0.6, 0.5, 1.9), material=white)
    for obj, group in parts:
        turn(obj, c, yaw)
        if group != "hull":
            b.add(obj, group)
    hull = [o for o, g in parts if g == "hull"]
    return join(hull, "rack")


def quarters_inside(b):
    x0, x1, y0, y1 = ext(QTR)
    for y in (-1.8, 4.2):
        for z in (0.45, 1.45):
            b.add(bunk("bunk", (x0 + WALL + 0.5, y, FLOOR + z), (0.9, 2.0, 0.15), material="grey", wall=-1))
    for y in (-2.9, -2.3, 7.4, 8.0):
        c = (x1 - WALL - 0.27, y, FLOOR + 0.95)
        b.add(turn(cabinet("locker", c, (0.55, 0.5, 1.9), material=white, doors=1), c, -90))
    b.add(block("qtable", (-10.3, 1.2, FLOOR + 0.75), (1.0, 1.6, 0.05), white, bevel=0.01))
    b.add(cyl("qtableleg", (-10.3, 1.2, FLOOR), (-10.3, 1.2, FLOOR + 0.73), 0.06, gm, segs=8, bevel=0))
    for i, y in enumerate((-1.5, 4.5)):
        lamp(b, f"lamp.{2 + i}", (-9.5, y, CEIL - 0.02), rim=white, r=0.18)
    b.add(extinguisher("ext", (x1 - WALL - 0.1, 3.2, FLOOR + 0.3), wall=1))
    # The hydroponic rack on the south end wall.
    yh = y0 + WALL + 0.3
    b.add(block("hydroframe", (-9.5, yh, FLOOR + 0.95), (2.2, 0.5, 1.9), gm, bevel=0.02))
    for z in (0.35, 0.95, 1.55):
        b.add(block("hydroshelf", (-9.5, yh + 0.02, FLOOR + z), (2.0, 0.44, 0.04), white, bevel=0))
        b.add(block("hydrostrip", (-9.5, yh + 0.02, FLOOR + z + 0.45), (1.9, 0.06, 0.02), "green_light", bevel=0), "lights")
        for k in range(5):
            b.add(sphere("plant", (-10.3 + k * 0.4, yh + 0.02, FLOOR + z + 0.12), 0.11, "olive", segs=8))
    # Air handling: a duct along the ceiling to a vent box.
    b.add(duct("qduct", (-9.5, y0 + 1.0, CEIL - 0.2), (-9.5, y1 - 1.0, CEIL - 0.2), (0.5, 0, 0.2), material=gm, flange=1.5))
    b.add(block("ventbox", (-9.5, 2.5, CEIL - 0.3), (0.9, 0.9, 0.4), gm, bevel=0.02))
    b.add(block("ventgrille", (-9.5, 2.5, CEIL - 0.51), (0.7, 0.7, 0.02), "black", bevel=0))


def armoury_inside(b):
    x0, x1, y0, y1 = ext(ARM)
    for y in (-2.0, 1.0):
        c = (x1 - WALL - 0.05, y, FLOOR)
        b.add(turn(gun_rack("cage", c, facing=1, n=4, material=white), c, 90))
    b.add(parcel_box("acrate", (8.5, -2.2, FLOOR + 0.45), (1.0, 1.4, 0.9), material="grey", band=blue))
    b.add(parcel_box("acrate", (8.5, -2.2, FLOOR + 1.25), (0.8, 1.0, 0.7), material=white))
    b.add(parcel_box("acrate", (8.5, 1.6, FLOOR + 0.45), (1.0, 1.2, 0.9), material="grey"))
    c = (x0 + WALL + 0.27, -0.5, FLOOR + 0.95)
    b.add(turn(cabinet("cabinet", c, (0.8, 0.5, 1.9), material=white, doors=2), c, 90))
    for i, y in enumerate((-1.5, 4.5)):
        lamp(b, f"lamp.{4 + i}", (9.5, y, CEIL - 0.02), rim=white, r=0.18)
    b.add(stripe("hazardline", (9.5, 2.5, FLOOR + 0.025), (0.12, 11.0, 0.01), "hazard"))
    b.add(block("bench", (9.5, 7.3, FLOOR + 0.45), (2.4, 0.7, 0.06), "steel", bevel=0.01))
    for sx in (-1, 1):
        b.add(block("benchleg", (9.5 + sx * 1.1, 7.3, FLOOR + 0.22), (0.06, 0.6, 0.44), gm, bevel=0))


def freight(b):
    """The freight office on the ice by the pad: a courier counter across the room with the clerk's
    terminal behind it under the lit contract board, parcels stacked for pickup and a scale. Take
    a contract here; it pays at the far door."""
    s = FREIGHT[1]
    x, y = FX, FY
    z0 = 0.15
    room(b, "freight", (x, y), s, white, FREIGHT_DOORS, trim=gm)
    x0, x1, y0, y1 = x - s[0] / 2, x + s[0] / 2, y - s[1] / 2, y + s[1] / 2
    band(b, (x, y, 0), (s[0], s[1], 0), s[2] - 0.35, 0.06, blue, proud=0.02)
    for a, bb in ((x0, x - 2.0 - 1.0), (x - 2.0 + 1.0, x1)):
        b.add(block("paint", ((a + bb) / 2, y0 - 0.01, 1.7), (bb - a, 0.02, 0.3), paint, bevel=0))
    b.add(block("paint", (x, y1 + 0.01, 1.7), (s[0], 0.02, 0.3), paint, bevel=0))
    for fx in (x0 - 0.01, x1 + 0.01):
        b.add(block("paint", (fx, y, 1.7), (0.02, s[1], 0.3), paint, bevel=0))
    at = (x + 1.0, y0 - 0.03, 2.35)
    b.add(turn(label("FREIGHT", at, 0.45, paint, side=-1, depth=0.02), at, 90))
    b.add(cyl("beaconmast", (x + 2.5, y + 1.5, s[2] + 0.1), (x + 2.5, y + 1.5, s[2] + 2.2), 0.05, "steel", segs=8, bevel=0))
    b.add(cyl("beacon", (x + 2.5, y + 1.5, s[2] + 2.2), (x + 2.5, y + 1.5, s[2] + 2.4), 0.12, blue, segs=10, bevel=0), "lights")
    b.add(join([cyl("ped", (x - 2.4, y + 1.2, s[2] + 0.1), (x - 2.4, y + 1.2, s[2] + 0.7), 0.08, gm, segs=8, bevel=0),
                cyl("updish", (x - 2.4, y + 1.1, s[2] + 0.75), (x - 2.4, y + 0.85, s[2] + 0.95), 0.1, white, r1=0.55, segs=16, bevel=0)], "updish"))
    for i, px in enumerate((x + 0.1, x + 1.3, x + 2.5)):
        b.add(parcel_box("parcel", (px, y0 - 0.8, 0.45), (1.0, 0.9, 0.9), material="grey", band=blue if i != 1 else "black"))
    # Lining, so the white box does not glare inside.
    b.add(block("lining", (x, y1 - 0.17, s[2] / 2), (s[0] - 0.34, 0.02, s[2] - 0.34), "vantage_lining", bevel=0))
    for fx in (x0 + 0.17, x1 - 0.17):
        b.add(block("lining", (fx, y, s[2] / 2), (0.02, s[1] - 0.34, s[2] - 0.34), "vantage_lining", bevel=0))
    for a, bb in ((x0 + 0.17, x - 2.0 - 0.8), (x - 2.0 + 0.8, x1 - 0.17)):
        b.add(block("lining", ((a + bb) / 2, y0 + 0.17, s[2] / 2), (bb - a, 0.02, s[2] - 0.34), "vantage_lining", bevel=0))
    b.add(block("ffloor", (x, y, z0 + 0.01), (s[0] - 0.34, s[1] - 0.34, 0.02), gm, bevel=0))
    # The counter across the room: body, top, a lit strip and the name on its face; terminals.
    cx0, cx1 = x0 + 0.15, x + 1.85
    cy = COUNTER_Y
    ccx = (cx0 + cx1) / 2
    b.add(block("counter", (ccx, cy, z0 + 0.5), (cx1 - cx0, 0.6, 1.0), white, bevel=0.02))
    b.add(block("countertop", (ccx, cy, z0 + 1.03), (cx1 - cx0 + 0.06, 0.75, 0.06), gm, bevel=0.01))
    b.add(block("counterstrip", (ccx, cy - 0.31, z0 + 0.85), (cx1 - cx0 - 0.1, 0.02, 0.06), blue, bevel=0), "lights")
    at = (x - 0.5, cy - 0.31, z0 + 0.5)
    b.add(turn(label("COURIER", at, 0.2, paint, side=-1, depth=0.01), at, 90))
    b.add(block("terminal", (x - 0.5, cy + 0.15, z0 + 1.3), (0.6, 0.06, 0.4), "black", bevel=0.01))
    b.add(block("terminalscreen", (x - 0.5, cy + 0.19, z0 + 1.3), (0.52, 0.01, 0.32), "screen", bevel=0), "lights")
    b.add(block("padscreen", (x - 0.5, cy - 0.2, z0 + 1.08), (0.4, 0.25, 0.03), blue, bevel=0, rot=-15), "lights")
    b.add(block("parcelslot", (x + 1.2, cy, z0 + 1.1), (0.6, 0.5, 0.08), "black", bevel=0.01))
    # Behind the counter: the contract board on the north wall and a parcel shelf.
    yn = y1 - 0.2
    b.add(block("board", (x - 0.5, yn, z0 + 2.0), (3.6, 0.05, 1.0), "black", bevel=0.01))
    for i in range(6):
        b.add(block("boardrow", (x - 2.0 + i * 0.6, yn - 0.03, z0 + 2.0), (0.5, 0.02, 0.8), blue if i % 2 else "screen", bevel=0), "lights")
    b.add(block("shelf", (x + 2.6, yn - 0.25, z0 + 1.0), (1.4, 0.5, 0.05), gm, bevel=0))
    for px in (x + 2.25, x + 2.95):
        b.add(parcel_box("parcel", (px, yn - 0.25, z0 + 1.3), (0.6, 0.45, 0.5), material="grey", band=blue))
        b.add(parcel_box("parcel", (px, yn - 0.25, z0 + 0.4), (0.6, 0.45, 0.7), material=white, band=blue))
    # The customer side: a scale and a parcel waiting.
    b.add(block("scale", (x + 2.5, y0 + 0.8, z0 + 0.06), (1.0, 1.0, 0.12), gm, bevel=0.02))
    b.add(cyl("scalepost", (x + 2.5, y0 + 1.25, z0 + 0.1), (x + 2.5, y0 + 1.25, z0 + 0.9), 0.04, gm, segs=8, bevel=0))
    b.add(block("scaleread", (x + 2.5, y0 + 1.22, z0 + 0.95), (0.3, 0.05, 0.2), "screen", bevel=0), "lights")
    b.add(parcel_box("parcel", (x + 0.6, y0 + 0.6, z0 + 0.35), (0.8, 0.7, 0.7), material="grey", band=blue))
    b.add(extinguisher("ext", (x0 + 0.2, y - 0.5, z0 + 0.3), wall=-1))
    lamp(b, "lamp.7", (x, y, s[2] - 0.17), rim=white, r=0.18)


def sounds(b):
    """Only indoors: Frost has no air to carry a sound outside."""
    life_node(b, "sound", 0, (-3.65, 4.6, FLOOR + 1.0), sound="hum")       # the ops server racks
    life_node(b, "sound", 0, (0.0, 2.6, CEIL - 0.3), sound="vent")       # the airlock's cycling air
    life_node(b, "sound", 1, (-9.5, 2.5, CEIL - 0.4), sound="vent")      # quarters air handler
    life_node(b, "sound", 1, (FX - 0.5, COUNTER_Y + 0.2, 1.3), sound="hum")  # the freight terminal


SPINNERS = ["spin.y.6.0", "spin.y.40.1", "spin.y.90.2"]
LIFE = ([f"blink.{i}" for i in range(8)] + [f"strobe.{i}" for i in range(3)]
        + ["sound.hum.0", "sound.vent.0", "sound.vent.1", "sound.hum.1"])

SPEC = {
    "build": build,
    "name": "Site Vantage",
    "color": (0.3, 0.65, 1.0),
    "faction": "pmc",
    "body": "frost",
    "lat": 24.0,
    "lon": 200.0,
    "footprint": (43.0, 22.6),
    "footprint_at": (1.5, 0.3),
    "pad": (0.0, -24.0),
    "door": (0.0, ext(VEST)[2], FLOOR + 1.1),
    "size": (22.6, 43.0, 11.0),
    "depth": 0.3,
    "nodes": [f"lamp.{i}" for i in range(8)] + ["flood.0", "flood.1"] + SPINNERS + LIFE,
    "traffic": "vantage",
    "boxes": [
        *pod_boxes("ops", OPS, [("-y", 0.0, 1.6), ("-x", 0.0, 1.6), ("+x", 0.0, 1.6)]),
        *pod_boxes("quarters", QTR, [("+x", 4.0, 1.6)]),
        *pod_boxes("armoury", ARM, [("-x", 4.0, 1.6)]),
        *pod_boxes("west link", LW, height=LINK_H, open_faces=("-x", "+x")),
        *pod_boxes("east link", LE, height=LINK_H, open_faces=("-x", "+x")),
        *pod_boxes("airlock", VEST, [("-y", 0.0, 1.6), ("+y", 0.0, 1.6)]),
        slope((0, ext(VEST)[2] - 1.6, 0), 1.8, 1.6, FLOOR, 1),
        *berm_boxes(),
        box("ops desk", (0, ext(OPS)[3] - WALL - 0.4, FLOOR + 0.6), (3.4, 0.7, 1.2)),
        box("sled", (3.4, -1.2, 0.95), (1.9, 3.0, 1.9)),
        box("pallet", (-3.6, -1.2, 0.75), (1.3, 1.1, 1.5)),
        box("rig deck", (DRILL[0], DRILL[1], 0.225), (3.4, 3.4, 0.45)),
        box("winch hut", (DRILL[0], DRILL[1] + 3.3, 1.15), (2.4, 1.8, 2.3)),
        box("core tray", (DRILL[0] - 2.6, DRILL[1] - 1.6, 0.48), (0.9, 2.6, 0.96)),
        *[box("tower leg", (RADAR[0] + sx * 1.05, RADAR[1] + sy * 1.05, 3.0), (0.4, 0.4, 6.0)) for sx in (-1, 1) for sy in (-1, 1)],
        *room_boxes("freight", FREIGHT[0], FREIGHT[1], FREIGHT_DOORS, wall=0.15),
        box("courier counter", ((FX - 3.35 + FX + 1.85) / 2, COUNTER_Y, 0.7), (5.2, 0.75, 1.1)),
        box("parcels", (FX + 1.3, FY - 2.5 - 0.8, 0.45), (3.4, 0.9, 0.9)),
    ],
    "stations": [("contracts", (FX - 0.5, COUNTER_Y - 0.75, 1.3), "Courier desk")],
    "crew": [
        # The courier clerk behind the counter, facing the customer side (-Y).
        ("contractor", (FX - 0.5, COUNTER_Y + 0.95, 0.15), 0, []),
        # The ops handler at the desk, looking at the screens (+Y).
        ("handler", (1.6, 7.3, FLOOR), 180, []),
        # The driller by the rig, watching the bit.
        ("contractor", (DRILL[0] + 0.6, DRILL[1] - 2.6, 0.0), 180, []),
        # A contractor's round: ops, the west link, down the quarters and back.
        ("contractor", (2.5, 5.2, FLOOR), 90, [(2.5, 5.2, FLOOR), (-6.0, 6.5, FLOOR), (-8.6, 6.0, FLOOR), (-8.6, -1.6, FLOOR), (-8.6, 5.6, FLOOR), (-6.0, 6.4, FLOOR)]),
        # A juggernaut walking the pad edge to the freight office and back.
        ("juggernaut", (-13.0, -8.25, 0.0), 90, [(-13.0, -8.25, 0.0), (12.5, -8.25, 0.0), (16.0, -8.6, 0.0)]),
        # A handler round the radar tower and behind the freight office.
        ("handler", (15.2, 0.6, 0.0), 90, [(15.2, 0.6, 0.0), (20.8, 0.6, 0.0), (20.8, 4.4, 0.0), (15.2, 4.4, 0.0)]),
    ],
    "view": {"cam": (-30.0, -32.0, 15.0), "look": (1.0, 1.0, 2.0), "lens": 30},
    "inside": {"cam": (-2.2, 4.4, FLOOR + 1.65), "look": (2.0, 8.4, FLOOR + 1.1), "lens": 20},
    "annex": {"cam": (15.6, -6.0, 1.8), "look": (18.5, -2.4, 1.3), "lens": 22},
    "annex_out": {"cam": (30.0, -20.0, 7.0), "look": (17.0, -2.0, 2.0), "lens": 30},
}
