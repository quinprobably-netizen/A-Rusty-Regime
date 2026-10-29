"""The Regime's Reliquary on Bastion, rebuilt for a 12.5 g world (living bases, 2026-10-29): a
fortress-cathedral that is also a data fortress, because the Regime keeps its scripture as data.

Nothing tall and thin stands under that weight, so it is low, wide and buried: a 34 m terrace of
cut slate rock with a grand flight of steps up its face, braziers on stepped cheek walls either
side; the nave sunk into the rock, its lower walls hugged by two rock shoulders and propped by
massive stepped buttresses whose top stages are black data monoliths split by glowing red seams;
black data vaults lining the rock ledges with thick cable trunks climbing the shoulders into the
nave; a squat bell tower over the narthex in place of the old spire, its bell turning in an open
belfry, an uplink spire for a finial; long red banners, gold ribs and red slit windows. Inside: a
wide nave with squat columns under a gold-ribbed architrave, cable trunks along the ceiling into
server stacks set into the walls like reliquaries, pews either side of a red runner, censers (the
middle one circling on its chain) smoking over the aisle, the shrine altar on a dais and behind
it the sealed archive core between the two ranks of the organ. The Chantry with the Shrine still
stands before the steps.
"""

import math

import bmesh
from basekit import Base, band, box, column, door_frame, hall, life_node, ring, room, room_boxes, slab, slope, spinner, stair, window
from kit import bell, block, chain, cyl, label, pipe, prism, sphere, stripe, wk
from interior import altar, candelabra, censer, font, lamp, pew, turn

wk.PALETTE.update({
    # Bastion's slate rock, cut in courses; darker joints; a lead roof; brazier coals; the
    # obsidian black of the data vaults.
    "bastion_rock": ((0.19, 0.195, 0.2), (0.34, 0.35, 0.36), 0.0, 0.9, 0.5, 0),
    "bastion_joint": ((0.10, 0.105, 0.11), (0.2, 0.2, 0.21), 0.0, 0.9, 0.3, 0),
    "roof_lead": ((0.09, 0.095, 0.11), (0.3, 0.31, 0.33), 0.3, 0.55, 0.5, 0),
    "ember": ((1.0, 0.32, 0.06), (1.0, 0.32, 0.06), 0.0, 0.3, 0.0, 6.0),
    "vault_black": ((0.018, 0.018, 0.022), (0.16, 0.16, 0.17), 0.4, 0.35, 0.35, 0),
})

slate, bone, gold, rock, joint, vblack, seam = "slate", "bone", "gold", "bastion_rock", "bastion_joint", "vault_black", "red_light"

TT = 2.4                    # the terrace top
FLOOR = TT + 0.03           # the nave and narthex floors, just proud of the terrace
W = 0.8                     # the nave walls
EAVE = TT + 9.5             # the nave walls' top
CEIL = EAVE - W             # the nave ceiling
RIDGE = TT + 12.5
SHOULDER = TT + 4.0         # the rock hugging the nave
NAVE = ((0.0, 8.8), (20.0, 24.4))       # centre (x, y), size (x, y): y -3.4..21
TOWER = ((0.0, -7.7), (12.0, 8.6))      # y -12..-3.4
BUTTRESSES = (0.0, 6.0, 12.0, 18.0)
BAYS = (3.0, 9.0, 15.0)
COLUMNS = [(sx * 5.0, y) for y in (0.0, 6.0, 12.0) for sx in (-1, 1)]
STAIR_FOOT, STAIR_RUN = -22.0, 5.5
CHEEKS = [(sx, k) for sx in (-1, 1) for k in range(3)]
VAULTS = (3.0, 9.0, 15.0)           # data vaults on the side ledges, one per bay
BELL_PIVOT = (0.0, -7.7, TT + 15.0)
CENSER_PIVOT = (0.0, 9.0, CEIL)
UPLINK_TOP = TT + 17.5 + 8.2

FIRES = [(sx * 6.8, STAIR_FOOT + (k + 0.5) * STAIR_RUN / 3, TT * (k + 1) / 3 + 1.0 + 1.0) for sx, k in CHEEKS]
FIRES += [(sx * 3.6, -13.4, TT + 2.0) for sx in (-1, 1)]       # the great braziers at the portal
FIRES += [(-6.6, -19.5 + sy * 1.5, 1.35) for sy in (-1, 1)]    # the chantry door
SMOKES = [(sx * 3.6, -13.4, TT + 2.6) for sx in (-1, 1)] + [(0, y, TT + 3.4) for y in (3.0, 9.0, 15.0)]
SOUNDS = [("organ", (0.0, 19.4, TT + 4.0)), ("bell", (0.0, -7.7, TT + 15.0)), ("fire", (0.0, -14.5, TT + 1.5)), ("hum", (0.0, 19.0, TT + 2.0))]
BLINKS = [(0.0, -7.7, UPLINK_TOP + 0.2)]
BELL_SPIN = "spin.x.3.0"
CENSER_SPIN = "spin.y.5.1"


def build():
    b = Base("reliquary")
    terrace(b)
    nave(b)
    tower(b)
    steps(b)
    inside(b)
    chantry(b)
    for i, p in enumerate(FIRES):
        life_node(b, "fire", i, p)
    for i, p in enumerate(SMOKES):
        life_node(b, "smoke", i, p)
    for i, p in enumerate(BLINKS):
        life_node(b, "blink", i, p)
    for kind, p in SOUNDS:
        life_node(b, "sound", 0, p, sound=kind)
    return b


# ------------------------------------------------------------------------------------- helpers

def flat(name, pts, plane, at, thick, material, bevel=0.0):
    """A flat polygon `thick` deep: `pts` are (u, z) in the plane x-z (at y = `at`) or y-z (at x =
    `at`). For banners with swallow tails and other outlines a block cannot make."""
    bm = bmesh.new()
    if plane == "xz":
        vs = [bm.verts.new((u, at - thick / 2, z)) for u, z in pts]
        d = (0, thick, 0)
    else:
        vs = [bm.verts.new((at - thick / 2, u, z)) for u, z in pts]
        d = (thick, 0, 0)
    face = bm.faces.new(vs)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, vec=d, verts=[e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return wk._obj(name, bm, material, bevel, 2)


def _p(plane, u, a, z):
    """A point in a wall's plane: `u` along the wall, `a` across it, `z` up."""
    return (u, a, z) if plane == "xz" else (a, u, z)


def banner(b, u, at, top, length, width, plane, out):
    """A long red banner hung flat on a wall: `u` is its centre along the wall, `at` the wall's
    face (x or y), `out` which way the wall faces (+1 or -1). Gold rod, gold hems, a gold
    sunburst and a swallow tail."""
    t = 0.06
    bot = top - length
    pts = [(u - width / 2, top), (u + width / 2, top), (u + width / 2, bot), (u, bot + width * 0.55), (u - width / 2, bot)]
    b.add(flat("banner", pts, plane, at + out * t / 2, t, "red"))
    a2 = at + out * (t + 0.012)
    for su in (-1, 1):
        edge = [(u + su * (width / 2 - 0.1), top), (u + su * width / 2, top), (u + su * width / 2, bot), (u + su * (width / 2 - 0.1), bot + 0.1)]
        b.add(flat("bannerhem", edge, plane, a2, 0.02, gold))
    zc = top - min(1.6, length * 0.25)
    axis = (0, 1, 0) if plane == "xz" else (1, 0, 0)
    b.add(ring("bannersun", _p(plane, u, a2, zc), axis, width * 0.32, width * 0.24, 0.02, gold, segs=16))
    b.add(block("bannerdot", _p(plane, u, a2, zc), (width * 0.16, 0.02, width * 0.16) if plane == "xz" else (0.02, width * 0.16, width * 0.16), gold, bevel=0))
    b.add(block("bannerbar", _p(plane, u, a2, zc - width * 0.75), (0.08, 0.02, width * 0.7) if plane == "xz" else (0.02, 0.08, width * 0.7), gold, bevel=0))
    a3 = at + out * 0.12
    p0, p1 = _p(plane, u - width / 2 - 0.2, a3, top + 0.05), _p(plane, u + width / 2 + 0.2, a3, top + 0.05)
    b.add(cyl("bannerrod", p0, p1, 0.06, gold, segs=8, bevel=0))
    for p in (p0, p1):
        b.add(sphere("rodknob", p, 0.11, gold, segs=8))


def courses(b, c, s, face, rows, material=joint, step=3.0):
    """Mason's joints on a rock face: horizontal course lines and staggered vertical joints, painted
    proud of the face `face` ("-y", "+x", ...) of the block at `c`, `s`."""
    x, y, z = c
    sx, sy, sz = s
    p = 0.012
    along_x = face in ("-y", "+y")
    f = -1 if face[0] == "-" else 1
    length = sx if along_x else sy
    h = sz / rows
    for r in range(rows):
        z0 = z - sz / 2 + r * h
        if r:
            if along_x:
                b.add(block("course", (x, y + f * (sy / 2 + p / 2), z0), (sx, p, 0.07), material, bevel=0))
            else:
                b.add(block("course", (x + f * (sx / 2 + p / 2), y, z0), (p, sy, 0.07), material, bevel=0))
        n = max(1, int(length / step))
        for i in range(n):
            off = -length / 2 + (i + (0.5 if r % 2 else 1.0)) * length / n
            if abs(off) >= length / 2 - 0.2:
                continue
            if along_x:
                b.add(block("joint", (x + off, y + f * (sy / 2 + p / 2), z0 + h / 2), (0.07, p, h), material, bevel=0))
            else:
                b.add(block("joint", (x + f * (sx / 2 + p / 2), y + off, z0 + h / 2), (p, 0.07, h), material, bevel=0))


def cut_rock(b, name, c, s, faces=(), rows=2, cap=None):
    """A block of cut rock with its joints on `faces` and, with `cap`, a coping slab on top."""
    b.add(block(name, c, s, rock, bevel=0.08, segs=2))
    for f in faces:
        courses(b, c, s, f, rows)
    if cap:
        b.add(block("coping", (c[0], c[1], c[2] + s[2] / 2 + 0.06), (s[0] + 0.12, s[1] + 0.12, 0.12), cap, bevel=0.02))


def seams(b, c, s, faces, rows=3, cols=2, w=0.06):
    """Glowing red data seams cut into the faces of a black block: `rows` horizontal lines and
    `cols` vertical ones on each face named, a few centimetres proud, in the lights group. The
    lines run to uneven lengths from alternate edges, like rows of data, not a window grid."""
    x, y, z = c
    sx, sy, sz = s
    p = 0.02
    fr = (0.86, 0.5, 0.72, 0.36, 0.8, 0.6)
    for k, face in enumerate(faces):
        f = -1 if face[0] == "-" else 1
        on_y = face[1] == "y"
        length = sx if on_y else sy
        for r in range(rows):
            zz = z - sz / 2 + (r + 1) * sz / (rows + 1)
            run = length * fr[(r + k) % len(fr)]
            side = -1 if (r + k) % 2 else 1
            off = side * (0.43 * length - run / 2)
            cc = (x + off, y + f * (sy / 2 + p / 2), zz) if on_y else (x + f * (sx / 2 + p / 2), y + off, zz)
            b.add(block("seam", cc, (run, p, w) if on_y else (p, run, w), seam, bevel=0), "lights")
        for i in range(cols):
            off = -length / 2 + (i + 1) * length / (cols + 1)
            run = sz * fr[(i + k + 2) % len(fr)]
            zz = z + 0.43 * sz - run / 2
            cc = (x + off, y + f * (sy / 2 + p / 2), zz) if on_y else (x + f * (sx / 2 + p / 2), y + off, zz)
            b.add(block("seam", cc, (w, p, run) if on_y else (p, w, run), seam, bevel=0), "lights")


def vault(b, c, s, faces, rows=3, cols=2, cap=gold):
    """A monolithic black data vault: an obsidian block with red seams and a gold cap."""
    b.add(block("vault", c, s, vblack, bevel=0.06))
    seams(b, c, s, faces, rows, cols)
    if cap:
        b.add(block("vaultcap", (c[0], c[1], c[2] + s[2] / 2 + 0.08), (s[0] + 0.2, s[1] + 0.2, 0.16), cap, bevel=0.03))


def trunk(b, pts, r=0.16, material="black", collars=gold):
    """A thick cable trunk through `pts`, with gold collars at every bend."""
    b.add(pipe("trunk", pts, r, material, segs=10))
    for p in pts[1:-1]:
        b.add(sphere("collar", p, r * 1.5, collars, segs=10))


def brazier(b, c, r=0.6, h=1.0, pedestal=True):
    """A brazier standing at `c` (floor level): a rock pedestal of height `h`, a gold bowl of
    mouth radius `r`, glowing coals and two tongues of flame."""
    x, y, z = c
    if pedestal:
        b.add(block("pedestal", (x, y, z + h / 2), (r * 1.3, r * 1.3, h), rock, bevel=0.05, taper=(0.8, 0.8)))
        b.add(block("pedcap", (x, y, z + h - 0.05), (r * 1.15, r * 1.15, 0.12), gold, bevel=0.02))
    zb = z + h
    b.add(cyl("bowl", (x, y, zb), (x, y, zb + r * 0.6), r * 0.45, gold, r1=r, segs=14, bevel=0.01))
    b.add(ring("bowlrim", (x, y, zb + r * 0.6), (0, 0, 1), r + 0.05, r - 0.04, 0.08, gold, segs=14))
    b.add(cyl("coals", (x, y, zb + r * 0.45), (x, y, zb + r * 0.58), r * 0.9, "ember", segs=14, bevel=0), "lights")
    b.add(cyl("flame", (x, y, zb + r * 0.5), (x, y, zb + r * 2.0), r * 0.55, "gold_light", r1=0.02, segs=8, bevel=0), "lights")
    b.add(cyl("flame", (x + r * 0.3, y - r * 0.2, zb + r * 0.5), (x + r * 0.35, y - r * 0.25, zb + r * 1.4), r * 0.3, "ember", r1=0.02, segs=6, bevel=0), "lights")


def statue(b, c, s=1.0):
    """A hooded bone figure leaning on a gold staff, broad and squat as Bastion makes everything."""
    x, y, z = c
    b.add(block("statueplinth", (x, y, z + 0.4 * s), (1.9 * s, 1.9 * s, 0.8 * s), rock, bevel=0.05))
    b.add(cyl("robe", (x, y, z + 0.8 * s), (x, y, z + 3.6 * s), 0.85 * s, bone, r1=0.5 * s, segs=12, bevel=0.02))
    b.add(block("shoulders", (x, y, z + 3.5 * s), (1.3 * s, 0.8 * s, 0.4 * s), bone, bevel=0.12, segs=3))
    b.add(sphere("hood", (x, y + 0.05, z + 4.0 * s), 0.5 * s, bone, segs=12))
    b.add(sphere("face", (x, y - 0.32 * s, z + 3.95 * s), 0.26 * s, "black", segs=10))
    b.add(block("eyes", (x, y - 0.55 * s, z + 4.0 * s), (0.3 * s, 0.04, 0.05 * s), seam, bevel=0), "lights")
    b.add(cyl("staff", (x + 0.75 * s, y - 0.35 * s, z + 0.8 * s), (x + 0.75 * s, y - 0.35 * s, z + 5.0 * s), 0.07 * s, gold, segs=8, bevel=0))
    b.add(ring("staffsun", (x + 0.75 * s, y - 0.35 * s, z + 5.2 * s), (0, 1, 0), 0.32 * s, 0.22 * s, 0.06, gold, segs=14))
    b.add(block("hands", (x + 0.55 * s, y - 0.45 * s, z + 2.6 * s), (0.5 * s, 0.3 * s, 0.3 * s), bone, bevel=0.08))


def spire(b, c, h, r=0.18):
    """A short uplink spire: a black mast in gold collars with dipole bars and red tips."""
    x, y, z = c
    b.add(cyl("spire", (x, y, z), (x, y, z + h), r, vblack, r1=r * 0.4, segs=8, bevel=0))
    for i in range(3):
        zz = z + h * (0.3 + 0.22 * i)
        w = 0.9 - 0.22 * i
        b.add(ring("spirecollar", (x, y, zz), (0, 0, 1), r * 1.6, r * 0.5, 0.12, gold, segs=10))
        for dx, dy in ((w, 0), (0, w)):
            b.add(cyl("dipole", (x - dx, y - dy, zz + 0.1), (x + dx, y + dy, zz + 0.1), 0.035, vblack, segs=6, bevel=0))
            for sgn in (-1, 1):
                b.add(sphere("tip", (x + sgn * dx, y + sgn * dy, zz + 0.1), 0.06, seam, segs=6), "lights")
    b.add(sphere("spiretip", (x, y, z + h + 0.05), 0.1, seam, segs=8), "lights")


# ------------------------------------------------------------------------------------ the rock

def terrace(b):
    """The terrace of cut rock the cathedral is sunk into: the lower tier with a coping, two
    shoulders (a high inner tier, a lower outer ledge) hugging the nave and the tower, and the
    data vaults on the ledges with their cable trunks climbing into the nave."""
    cut_rock(b, "terrace", (0, 4.75, (TT - 0.3) / 2), (34.0, 42.5, TT + 0.3), faces=("-y", "-x", "+x", "+y"), rows=2)
    for sx in (-1, 1):
        b.add(block("coping", (sx * 11.8, -16.45, TT + 0.06), (10.4, 0.3, 0.12), bone, bevel=0.02))
    for sx in (-1, 1):
        cut_rock(b, "shoulder", (sx * 9.6, -7.7, SHOULDER - 2.0), (7.2, 8.6, 4.0), faces=("-y",), rows=3, cap=bone)
        cut_rock(b, "shoulder", (sx * 11.6, 8.8, SHOULDER - 2.0), (3.2, 24.4, 4.0), faces=("-x" if sx < 0 else "+x",), rows=3, cap=bone)
        cut_rock(b, "ledge", (sx * 14.7, 6.75, TT + 1.0), (3.0, 37.5, 2.0), faces=("-y", "-x" if sx < 0 else "+x"), rows=1, cap=bone)
        # The data vaults: black monoliths on the ledge, one per bay, each feeding a trunk up the
        # shoulder and into the nave wall under the windows.
        for y in VAULTS:
            c = (sx * 14.7, y, TT + 2.12 + 2.2)
            vault(b, c, (2.4, 2.6, 4.4), ("-y", "+y", "-x" if sx < 0 else "+x"), rows=4, cols=2)
            trunk(b, [(sx * 13.5, y - 0.6, TT + 3.4), (sx * 12.9, y - 0.6, TT + 3.4), (sx * 12.9, y - 0.6, SHOULDER + 0.35), (sx * 10.0, y - 0.6, SHOULDER + 0.35)], r=0.17)
            trunk(b, [(sx * 13.5, y + 0.6, TT + 2.9), (sx * 13.1, y + 0.6, TT + 2.9), (sx * 13.1, y + 0.6, SHOULDER + 0.3), (sx * 10.0, y + 0.6, SHOULDER + 0.3)], r=0.13)
            b.add(block("socket", (sx * 10.15, y, SHOULDER + 0.35), (0.3, 1.8, 0.7), gold, bevel=0.03))
    cut_rock(b, "shoulder", (0, 22.75, SHOULDER - 2.0), (26.4, 3.5, 4.0), faces=("+y",), rows=3, cap=bone)
    cut_rock(b, "ledge", (0, 25.05, TT + 1.0), (26.4, 1.1, 2.0), faces=("+y",), rows=1)
    # Statues of the faithful on the shoulder's front, banners down the rock under them.
    for sx in (-1, 1):
        statue(b, (sx * 9.8, -10.6, SHOULDER + 0.12), 1.0)
        banner(b, sx * 9.8, -12.0, SHOULDER - 0.2, 3.4, 1.5, "xz", -1)


# -------------------------------------------------------------------------------- the cathedral

def nave(b):
    """The nave sunk into the shoulders: thick slate walls with paired red slit windows in three
    bays, massive stepped buttresses whose top stages are black data monoliths, a low lead roof
    with gold ribs, the apse with the archive's uplink spires."""
    (cx, cy), (sx_, sy_) = NAVE
    zb = FLOOR - W
    openings = [("-y", 0, 6.0, 7.0, 0)]
    for yc in BAYS:
        for d in (-0.9, 0.9):
            for f in ("-x", "+x"):
                openings.append((f, yc + d - cy, 0.8, 3.6, 4.6))
    hall(b, "nave", (cx, cy, (zb + EAVE) / 2), (sx_, sy_, EAVE - zb), slate, wall=W, openings=openings, bevel=0.1)
    for yc in BAYS:
        for d in (-0.9, 0.9):
            for sx in (-1, 1):
                window(b, (sx * 9.95, yc + d, FLOOR + 6.4), (0.06, 0.8, 3.6), frame=gold, glass="red_glass")
        for sx in (-1, 1):
            b.add(block("windowhood", (sx * 10.1, yc, FLOOR + 8.45), (0.3, 2.8, 0.3), bone, bevel=0.03))
    band(b, (cx, cy, 0), (sx_, sy_, 0), EAVE - 0.25, 0.35, gold, front_gap=12.0)
    band(b, (cx, cy, 0), (sx_, sy_, 0), SHOULDER + 0.9, 0.25, gold, front_gap=12.0)
    # Buttresses: two stone setbacks with gold caps, then a black data monolith with red seams.
    for y in BUTTRESSES:
        for sx in (-1, 1):
            for x0, x1, z0, z1 in ((10.0, 13.0, SHOULDER, SHOULDER + 2.3), (10.0, 12.0, SHOULDER + 2.3, SHOULDER + 4.0)):
                xc, w = sx * (x0 + x1) / 2, x1 - x0
                b.add(block("buttress", (xc, y, (z0 + z1) / 2), (w, 2.4, z1 - z0), slate, bevel=0.08))
                b.add(block("buttcap", (xc + sx * 0.05, y, z1), (w + 0.1, 2.6, 0.18), gold, bevel=0.03))
                b.add(stripe("buttrib", (sx * (x1 + 0.005), y, (z0 + z1) / 2), (0.01, 0.3, z1 - z0 - 0.2), gold))
            z0, z1 = SHOULDER + 4.1, EAVE + 0.9
            c = (sx * 10.55, y, (z0 + z1) / 2)
            vault(b, c, (1.1, 1.8, z1 - z0), ("-y", "+y", "-x" if sx < 0 else "+x"), rows=3, cols=1, cap=gold)
    # The apse rising from the back shoulder, the archive's uplink spires on it.
    b.add(block("apse", (0, 22.6, SHOULDER + 2.6), (12.0, 3.2, 5.2), vblack, bevel=0.1, segs=3, taper=(0.75, 0.6)))
    seams(b, (0, 22.6, SHOULDER + 2.2), (11.0, 3.2, 3.6), ("+y",), rows=2, cols=5)
    b.add(block("apsecap", (0, 22.3, SHOULDER + 5.3), (9.4, 2.2, 0.3), gold, bevel=0.03))
    for x in (-3.0, 0.0, 3.0):
        spire(b, (x, 22.3, SHOULDER + 5.45), 3.6 if x else 5.0)
    # The roof: low and lead-dark under the weight of the sky, gold ribs over each buttress.
    span = sx_ / 2 + 0.8
    ylen = sy_ + 0.4
    roof = prism("roof", [(-span, EAVE - 0.2), (0, RIDGE), (span, EAVE - 0.2)], ylen, "roof_lead", x=cy + 0.2, bevel=0.05)
    b.add(turn(roof, (0, 0, 0), 90))
    b.add(block("ridge", (0, cy + 0.2, RIDGE + 0.05), (0.5, ylen + 0.1, 0.3), gold, bevel=0.03))
    for y in BUTTRESSES + (20.9,):
        trim = prism("rooftrim", [(-span - 0.1, EAVE - 0.3), (0, RIDGE + 0.1), (span + 0.1, EAVE - 0.3), (span + 0.1, EAVE - 0.55), (0, RIDGE - 0.15), (-span - 0.1, EAVE - 0.55)], 0.35, gold, x=y, bevel=0.01)
        b.add(turn(trim, (0, 0, 0), 90))


def tower(b):
    """The squat bell tower over the narthex: the hollow narthex with the great portal, a solid
    stage with the rose window, an open belfry on four piers with the bell turning on its axle,
    a heavy cornice, a low pyramid cap and the uplink spire on it."""
    (cx, cy), (sx_, sy_) = TOWER
    top = TT + 8.0
    hall(b, "narthex", (cx, cy, (FLOOR - W + top) / 2), (sx_, sy_, top - FLOOR + W), slate, wall=W,
         openings=[("-y", 0, 4.4, 6.5, 0), ("+y", 0, sx_ - 2 * W, top - FLOOR, 0)], bevel=0.1)
    b.add(block("stage", (cx, cy, top + 2.5), (sx_, sy_, 5.0), slate, bevel=0.1))
    belfry, cornice = TT + 13.0, TT + 17.5
    for px in (-1, 1):
        for py in (-1, 1):
            c = (px * (sx_ / 2 - 1.1), cy + py * (sy_ / 2 - 1.1), (belfry + cornice) / 2)
            b.add(block("pier", c, (2.2, 2.2, cornice - belfry), vblack, bevel=0.08))
            seams(b, c, (2.2, 2.2, cornice - belfry), ("-y" if py < 0 else "+y", "-x" if px < 0 else "+x"), rows=3, cols=1)
    b.add(block("cornice", (cx, cy, cornice + 0.4), (sx_ + 0.8, sy_ + 0.8, 0.8), slate, bevel=0.08))
    b.add(block("cap", (cx, cy, cornice + 0.8 + 1.2), (sx_ - 0.2, sy_ - 0.2, 2.4), "roof_lead", bevel=0.05, taper=(0.12, 0.16)))
    b.add(sphere("orb", (cx, cy, cornice + 3.4), 0.55, gold, segs=14))
    spire(b, (cx, cy, cornice + 3.8), UPLINK_TOP - cornice - 3.8, r=0.2)
    for z, h in ((top, 0.35), (belfry, 0.35), (cornice - 0.1, 0.25), (TT + 4.25, 0.25)):
        # Three faces only: the back opens on the nave, and a +y strip would cross its arch.
        b.add(block("band", (cx, cy - sy_ / 2 - 0.008, z), (sx_ + 0.015, 0.015, h), gold, bevel=0))
        for sx in (-1, 1):
            b.add(block("band", (cx + sx * (sx_ / 2 + 0.008), cy, z), (0.015, sy_ + 0.015, h), gold, bevel=0))
    for px in (-1, 1):
        for py in (-1, 1):
            b.add(stripe("cornerrib", (px * (sx_ / 2 + 0.01), cy + py * (sy_ / 2 + 0.01), (TT + belfry) / 2 + 0.6), (0.25, 0.25, belfry - TT - 1.2), gold))
    # The bell: bearings on the side piers, and the turning part (axle, headstock, bell and
    # clapper) about its middle, so it clears the piers and the cornice as it goes over.
    px, py, pz = BELL_PIVOT
    for sx in (-1, 1):
        b.add(block("bearing", (sx * 3.95, py, pz), (0.5, 0.6, 0.5), gold, bevel=0.03))
        b.add(block("beam", (sx * 3.95, py, pz - 0.6), (0.4, 4.4, 0.4), "black", bevel=0.02))
    parts = [cyl("axle", (-3.8, py, pz), (3.8, py, pz), 0.12, "steel", segs=10, bevel=0),
             block("headstock", (px, py, pz + 1.15), (1.8, 0.55, 0.4), "black", bevel=0.03),
             bell("bell", (px, py, pz + 0.95), (px, py, pz - 0.95), 0.55, 0.95, "brass", segs=20),
             sphere("crown", (px, py, pz + 0.85), 0.56, "brass", segs=14),
             ring("lip", (px, py, pz - 0.85), (0, 0, 1), 1.0, 0.9, 0.12, gold, segs=20),
             cyl("clapperrod", (px, py, pz + 0.8), (px, py, pz - 0.5), 0.05, "black", segs=6, bevel=0),
             sphere("clapper", (px, py, pz - 0.6), 0.18, "black", segs=10)]
    for sx in (-1, 1):
        parts.append(cyl("strap", (sx * 0.6, py, pz + 1.0), (sx * 0.6, py, pz), 0.06, "black", segs=6, bevel=0))
    spinner(b, 0, BELL_PIVOT, "x", 3, parts)
    # The great portal: a gold door frame inside two receding stone orders, the motto, the rose
    # window over it, slit windows up the tower's sides, banners down its face and sides.
    fy = cy - sy_ / 2
    door_frame(b, (0, fy, FLOOR), 4.4, 6.5, material=gold, depth=1.0, thick=0.35)
    for w, h, t, d, m in ((5.8, 7.2, 0.5, 0.7, bone), (7.2, 7.9, 0.6, 1.0, slate)):
        for sx in (-1, 1):
            b.add(block("order", (sx * (w / 2 + t / 2), fy - d / 2 + 0.05, FLOOR + (h + t) / 2), (t, d, h + t), m, bevel=0.04))
        b.add(block("order", (0, fy - d / 2 + 0.05, FLOOR + h + t / 2), (w + 2 * t, d, t), m, bevel=0.04))
    for sx in (-1, 1):
        b.add(block("orderseam", (sx * 3.6, fy - 0.96, FLOOR + 4.0), (0.06, 0.02, 6.6), seam, bevel=0), "lights")
    b.add(block("plaque", (0, fy - 1.0, FLOOR + 8.25), (6.0, 0.14, 0.8), bone, bevel=0.02))
    b.add(turn(label("THE ALGORITHM PROVIDES", (0, fy - 1.08, FLOOR + 8.25), 0.42, gold, side=-1, depth=0.03), (0, fy - 1.08, FLOOR + 8.25), 90))
    zc = TT + 10.6
    b.add(cyl("rosepane", (0, fy + 0.02, zc), (0, fy - 0.04, zc), 1.55, "red_glass", segs=24, bevel=0), "glass")
    b.add(ring("rose", (0, fy - 0.06, zc), (0, 1, 0), 1.85, 1.5, 0.14, gold, segs=24))
    b.add(ring("roseinner", (0, fy - 0.06, zc), (0, 1, 0), 0.55, 0.4, 0.12, gold, segs=16))
    for i in range(8):
        a = math.radians(i * 45 + 22.5)
        b.add(cyl("spoke", (0.5 * math.cos(a), fy - 0.06, zc + 0.5 * math.sin(a)), (1.55 * math.cos(a), fy - 0.06, zc + 1.55 * math.sin(a)), 0.07, gold, segs=6, bevel=0))
    for sx in (-1, 1):
        for d in (-1.6, 1.6):
            window(b, (sx * (sx_ / 2 + 0.03), cy + d, TT + 10.4), (0.06, 0.7, 3.0), frame=gold, glass="red_glass")
        banner(b, sx * 4.95, fy, TT + 12.6, 11.0, 1.5, "xz", -1)
        banner(b, cy, sx * sx_ / 2, TT + 12.4, 7.6, 1.5, "yz", sx)


def steps(b):
    """The grand stair up the terrace face, its stepped cheek walls each carrying a brazier, the
    great braziers at the portal."""
    stair(b, (0, STAIR_FOOT, 0), 12.0, STAIR_RUN, TT, 8, material=rock, facing=1, stringers=False)
    for sx, k in CHEEKS:
        y = STAIR_FOOT + (k + 0.5) * STAIR_RUN / 3
        top = TT * (k + 1) / 3 + 1.0
        cut_rock(b, "cheek", (sx * 6.8, y, top / 2), (1.6, STAIR_RUN / 3, top), faces=("-y", "-x" if sx < 0 else "+x"), rows=1, cap=bone)
        brazier(b, (sx * 6.8, y, top + 0.12), r=0.5, h=0.0, pedestal=False)
    for sx in (-1, 1):
        brazier(b, (sx * 3.6, -13.4, TT), r=0.75, h=1.0)


def inside(b):
    """The nave and narthex inside: a bone floor and red runner, squat columns with gold-banded
    capitals under a ribbed architrave, gold ribs across the ceiling, pews, banners, cable trunks
    along the ceiling into the server reliquaries in the walls, the censers, the dais with the
    shrine altar, and behind it the archive core between the organ's ranks."""
    fz = FLOOR
    b.add(block("floorplate", (0, 8.8, fz + 0.01), (18.3, 22.7, 0.02), bone, bevel=0))
    b.add(block("floorplate", (0, -7.3, fz + 0.01), (10.3, 7.8, 0.02), bone, bevel=0))
    b.add(block("runner", (0, 5.0, fz + 0.025), (2.4, 21.0, 0.03), "red", bevel=0))
    for sx in (-1, 1):
        b.add(stripe("gilt", (sx * 1.25, 5.0, fz + 0.04), (0.06, 21.0, 0.02), gold))
    # Columns, capitals and the architrave, ribs across the nave and out to the walls.
    cap = TT + 6.0
    for x, y in COLUMNS:
        column(b, (x, y, fz), 0.75, cap - fz - 0.5, material=bone, segs=16)
        b.add(block("capital", (x, y, cap - 0.25), (1.9, 1.9, 0.5), slate, bevel=0.05))
        b.add(block("capband", (x, y, cap - 0.45), (1.95, 1.95, 0.1), gold, bevel=0))
    for sx in (-1, 1):
        b.add(block("architrave", (sx * 5.0, 8.8, cap + 0.45), (1.2, 22.8, 0.9), slate, bevel=0.04))
        b.add(block("archgold", (sx * 5.0, 8.8, cap - 0.02), (0.6, 22.8, 0.06), gold, bevel=0))
        b.add(block("archseam", (sx * 5.0 - sx * 0.61, 8.8, cap + 0.45), (0.02, 22.8, 0.08), seam, bevel=0), "lights")
    for y in (0.0, 6.0, 12.0, 18.0):
        for sx in (-1, 1):
            b.add(cyl("rib", (sx * 5.0, y, cap + 0.9), (sx * 2.4, y, CEIL - 0.35), 0.14, gold, segs=8, bevel=0))
            b.add(cyl("rib", (sx * 2.4, y, CEIL - 0.35), (0, y, CEIL - 0.12), 0.14, gold, segs=8, bevel=0))
            b.add(cyl("rib", (sx * 5.0, y, cap + 0.9), (sx * 9.2, y, CEIL - 0.6), 0.14, gold, segs=8, bevel=0))
            b.add(block("corbel", (sx * 8.95, y, CEIL - 0.85), (0.5, 0.7, 0.5), bone, bevel=0.04, taper=(0.4, 0.6)))
            banner(b, y, sx * 9.2, CEIL - 1.3, 5.0, 1.3, "yz", -sx)
        b.add(sphere("boss", (0, y, CEIL - 0.12), 0.25, gold, segs=10))
    for sx in (-1, 1):
        b.add(block("dado", (sx * 9.15, 8.8, fz + 0.6), (0.1, 22.7, 1.2), bone, bevel=0.01))
        b.add(block("dadorail", (sx * 9.1, 8.8, fz + 1.22), (0.14, 22.7, 0.08), gold, bevel=0))
        # The server reliquaries: a black stack in each bay, set into the wall behind a gold
        # frame like a relic in its niche, fed by a trunk that runs the length of the ceiling's
        # edge from the archive core.
        for y in BAYS:
            x = sx * 8.85
            c = (x, y, fz + 1.6)
            b.add(block("stack", c, (0.7, 1.5, 3.2), vblack, bevel=0.03))
            seams(b, c, (0.7, 1.5, 3.2), ("+x" if sx < 0 else "-x",), rows=7, cols=0, w=0.05)
            b.add(block("stackled", (x - sx * 0.37, y - 0.5, fz + 2.9), (0.02, 0.2, 0.2), "lights_amber", bevel=0), "lights")
            for d in (-1, 1):
                b.add(block("niche", (x - sx * 0.3, y + d * 0.85, fz + 1.7), (0.3, 0.2, 3.4), gold, bevel=0.02))
            b.add(block("niche", (x - sx * 0.3, y, fz + 3.45), (0.3, 1.9, 0.25), gold, bevel=0.02))
            b.add(prism("nichepeak", [(y - 0.95, fz + 3.57), (y, fz + 4.2), (y + 0.95, fz + 3.57)], 0.3, gold, x=x - sx * 0.3, bevel=0.01))
            b.add(ring("nichesun", (x - sx * 0.46, y, fz + 3.85), (1, 0, 0), 0.2, 0.13, 0.03, seam, segs=12), "lights")
            trunk(b, [(sx * 8.95, y, fz + 3.25), (sx * 8.95, y, CEIL - 1.9)], r=0.12)
        trunk(b, [(sx * 2.2, 19.4, fz + 0.4 + 6.6), (sx * 2.2, 19.4, CEIL - 0.3), (sx * 8.95, 19.4, CEIL - 0.3), (sx * 8.95, 19.4, CEIL - 1.9), (sx * 8.95, -1.5, CEIL - 1.9)], r=0.18)
    # Pews either side of the runner.
    for i in range(6):
        y = 0.8 + i * 2.2
        for sx in (-1, 1):
            b.add(pew("pew", (sx * 2.95, y, fz + 0.45), w=2.4, facing=1))
    # The censers: two hang still, the middle one circles on its chain.
    for i, y in enumerate((3.0, 15.0)):
        censer(b, (0, y, CEIL), CEIL - (TT + 3.8))
        b.node(f"lamp.{i}", (0, y, TT + 3.4))
    cx, cy, cz = CENSER_PIVOT
    bx, bz = 1.3, TT + 3.6
    parts = [cyl("pivot", (cx, cy, cz), (cx, cy, cz - 0.25), 0.18, gold, segs=10, bevel=0),
             chain("chain", (cx, cy, cz - 0.2), (cx + bx, cy, bz + 0.1), links=40, r=0.03, material=gold),
             sphere("bowl", (cx + bx, cy, bz - 0.2), 0.32, gold, segs=14),
             cyl("lid", (cx + bx, cy, bz - 0.02), (cx + bx, cy, bz + 0.25), 0.24, gold, r1=0.05, segs=12, bevel=0),
             ring("band", (cx + bx, cy, bz - 0.15), (0, 0, 1), 0.34, 0.3, 0.06, slate, segs=14),
             sphere("ember", (cx + bx, cy, bz - 0.08), 0.16, "ember", segs=10)]
    spinner(b, 1, CENSER_PIVOT, "z", 5, parts)
    b.node("lamp.2", (0, 9.0, TT + 3.0))
    for i, sx in enumerate((-1, 1)):
        lamp(b, f"lamp.{3 + i}", (sx * 7.2, 9.0, CEIL), material="gold_light", rim=gold, r=0.35)
    # The narthex: two fonts and a lamp.
    for sx in (-1, 1):
        b.add(font("font", (sx * 3.2, -6.4, fz)))
    lamp(b, "lamp.5", (0, -7.7, TT + 7.2), material="gold_light", rim=gold, r=0.35)
    # The dais with the shrine: the altar under the reliquary, candelabra, choir stalls.
    slab(b, "dais", (0, 17.5, fz + 0.2), (13.0, 5.4, 0.4), bone, bevel=0.02)
    slab(b, "daisstep", (0, 14.6, fz + 0.1), (13.0, 0.4, 0.2), bone, bevel=0.01)
    b.add(block("daistrim", (0, 14.8, fz + 0.41), (13.0, 0.08, 0.04), gold, bevel=0))
    az = fz + 0.4
    altar(b, (0, 16.8, az), (3.0, 1.2, 1.1))
    b.add(block("reliquary", (0, 16.9, az + 1.35), (1.2, 0.7, 0.5), gold, bevel=0.03))
    b.add(prism("reliquarylid", [(16.9 - 0.35, az + 1.6), (16.9, az + 1.95), (16.9 + 0.35, az + 1.6)], 1.2, gold, x=0, bevel=0.01))
    b.add(sphere("relic", (0, 16.53, az + 1.35), 0.12, "red_light", segs=10), "lights")
    b.add(ring("relicsun", (0, 16.5, az + 1.35), (0, 1, 0), 0.24, 0.17, 0.03, gold, segs=14))
    for x, y in ((-2.4, 15.8), (2.4, 15.8)):
        candelabra(b, (x, y, az), arms=5, h=1.7)
    b.node("lamp.6", (0, 15.6, az + 2.6))
    for sx in (-1, 1):
        x = sx * 5.2
        b.add(block("stallbase", (x, 17.0, az + 0.3), (0.7, 3.0, 0.6), slate, bevel=0.02))
        b.add(block("stallseat", (x, 17.0, az + 0.63), (0.7, 3.0, 0.08), "leather", bevel=0.02))
        b.add(block("stallback", (x + sx * 0.35, 17.0, az + 1.3), (0.12, 3.0, 1.4), slate, bevel=0.02))
        b.add(block("stallrail", (x + sx * 0.35, 17.0, az + 2.05), (0.18, 3.1, 0.1), gold, bevel=0.01))
    archive(b, az)
    organ(b, az)


def archive(b, az):
    """The sealed archive core behind the altar: a black monolith from the dais to the vault in a
    gold frame, its sealed door scored with red seams, cable trunks spilling from its feet."""
    y = 19.4
    c = (0, y, (az + CEIL) / 2)
    s = (3.4, 1.6, CEIL - az)
    b.add(block("archive", c, s, vblack, bevel=0.06))
    seams(b, (0, y, az + 3.0), (3.4, 1.6, 5.0), ("-y",), rows=6, cols=3, w=0.05)
    for sx in (-1, 1):
        b.add(block("archiveframe", (sx * 1.85, y - 0.1, c[2]), (0.3, 1.6, s[2]), gold, bevel=0.03))
    b.add(block("archivelintel", (0, y - 0.82, az + 5.9), (3.9, 0.12, 0.5), gold, bevel=0.02))
    b.add(block("seal", (0, y - 0.84, az + 2.6), (1.0, 0.06, 1.0), gold, bevel=0.02))
    b.add(ring("sealsun", (0, y - 0.87, az + 2.6), (0, 1, 0), 0.38, 0.26, 0.03, seam, segs=16), "lights")
    b.add(turn(label("SCRIPTURE IS DATA", (0, y - 0.9, az + 5.9), 0.26, "black", side=-1, depth=0.02), (0, y - 0.9, az + 5.9), 90))
    for sx in (-1, 1):
        trunk(b, [(sx * 1.4, y - 0.9, az + 0.2), (sx * 2.2, y - 1.3, az + 0.2), (sx * 2.2, y - 1.3, az + 0.15)], r=0.15)


def organ(b, az):
    """The organ's two ranks either side of the archive core: slate cases, gold pipes graded
    outward, and the console at the side, where the drone comes from."""
    y = 19.75
    for sx in (-1, 1):
        xc = sx * 3.9
        b.add(block("organcase", (xc, y, az + 1.1), (3.8, 0.9, 2.2), slate, bevel=0.04))
        b.add(block("organtrim", (xc, y - 0.46, az + 2.2), (3.9, 0.08, 0.14), gold, bevel=0))
        for i in range(7):
            x = sx * (2.3 + i * 0.52)
            h = 5.6 - i * 0.45 + (0.3 if i % 2 else 0)
            r = 0.2 if i % 2 else 0.24
            b.add(cyl("pipe", (x, y - 0.1, az + 2.2), (x, y - 0.1, az + 2.2 + h), r, gold, segs=10, bevel=0))
            b.add(block("mouth", (x, y - 0.1 - r, az + 2.6), (r * 0.9, 0.04, 0.2), "black", bevel=0))
    b.add(block("console", (6.0, 18.6, az + 0.55), (1.6, 0.7, 1.1), slate, bevel=0.03))
    b.add(block("keys", (6.0, 18.2, az + 1.02), (1.4, 0.2, 0.05), bone, bevel=0))
    b.add(block("bench", (6.0, 17.7, az + 0.25), (1.2, 0.35, 0.5), "leather", bevel=0.02))


# ------------------------------------------------------------------------------------ the chantry

CHANTRY = ((-12.5, -19.5), (9.0, 5.0, 5.5))
CHANTRY_DOORS = [("+x", 0.0, 1.6, 3.0)]
CHANTRY_WALL = 0.25
CHANTRY_ALTAR = (-15.0, -19.5)


def chantry(b):
    """The chantry before the steps: a squat stone chapel with heavy stepped corner buttresses, red
    slit windows and a low gold-ridged roof; inside, the shrine altar with the gilded reliquary
    before a data stack, the priest's place behind it, candelabra, a kneeler and bone statues.
    Make the tithe here."""
    (x, y), s = CHANTRY
    z0 = CHANTRY_WALL
    slits = [(f, off, 0.6, 2.2, 1.6) for f in ("-y", "+y") for off in (-2.5, 2.5)]
    room(b, "chantry", (x, y), s, slate, CHANTRY_DOORS, wall=CHANTRY_WALL, trim=gold, windows=slits)
    for f, off, w, h, z in slits:
        window(b, (x + off, y + (-1 if f == "-y" else 1) * s[1] / 2, z0 + z + h / 2), (w, 0.1, h), frame=gold, glass="red_glass")
    band(b, (x, y, 0), (s[0], s[1], 0), s[2] - 0.6, 0.25, gold)
    b.add(block("chantryroof", (x, y, s[2] + 0.75), (s[0] + 0.1, s[1] + 0.1, 1.2), "roof_lead", bevel=0.04, taper=(0.75, 0.12)))
    b.add(block("chantryridge", (x, y, s[2] + 1.38), (s[0] * 0.75 + 0.1, 0.25, 0.12), gold, bevel=0.01))
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx_, cy_ = x + sx * (s[0] / 2 + 0.4), y + sy * (s[1] / 2 + 0.4)
            b.add(block("buttress", (cx_, cy_, 1.4), (1.1, 1.1, 2.8), rock, bevel=0.05))
            vault(b, (cx_ - sx * 0.1, cy_ - sy * 0.1, 3.6), (0.8, 0.8, 1.6), ("-y" if sy < 0 else "+y", "-x" if sx < 0 else "+x"), rows=2, cols=1)
    spire(b, (x, y, s[2] + 1.44), 2.4, r=0.12)
    # The door: gold-framed already; braziers either side, short banners above them.
    for sy in (-1, 1):
        brazier(b, (x + s[0] / 2 + 1.4, y + sy * 1.5, 0), r=0.4, h=0.9)
        banner(b, y + sy * 1.5, x + s[0] / 2, 4.6, 2.6, 0.9, "yz", 1)
    # The altar stands off the west wall with the priest's place behind it, a data stack
    # behind him for a reredos.
    ax, ay = CHANTRY_ALTAR
    altar(b, (ax, ay, z0), (0.9, 2.4, 1.05), material=bone, cloth="red", trim=gold)
    b.add(block("casket", (ax, ay, z0 + 1.3), (0.5, 1.1, 0.3), gold, bevel=0.02))
    b.add(prism("casketlid", [(ay - 0.55, z0 + 1.45), (ay, z0 + 1.7), (ay + 0.55, z0 + 1.45)], 0.5, gold, x=ax, bevel=0.01))
    b.add(sphere("jewel", (ax + 0.27, ay, z0 + 1.3), 0.06, "red_light", segs=8), "lights")
    for dy in (-1.75, 1.75):
        candelabra(b, (ax - 0.4, ay + dy, z0), material=gold, arms=5, h=1.5)
    wx = x - s[0] / 2 + CHANTRY_WALL
    rc = (wx + 0.12, ay, z0 + 2.6)
    b.add(block("reredos", rc, (0.24, 2.6, 4.0), vblack, bevel=0.02))
    seams(b, rc, (0.24, 2.6, 4.0), ("+x",), rows=5, cols=2, w=0.04)
    b.add(ring("reredossun", (wx + 0.27, ay, z0 + 3.4), (1, 0, 0), 0.7, 0.55, 0.04, gold, segs=18))
    b.add(block("kneeler", (ax + 1.5, ay, z0 + 0.2), (0.5, 1.6, 0.4), "leather", bevel=0.05, segs=3))
    b.add(block("kneelerrail", (ax + 1.5, ay, z0 + 0.62), (0.2, 1.6, 0.05), gold, bevel=0.01))
    for dy in (-1.6, 1.6):
        b.add(block("bonestatue", (ax + 2.9, ay + dy, z0 + 0.8), (0.5, 0.5, 1.6), bone, bevel=0.1, segs=3))
        b.add(sphere("skull", (ax + 2.9, ay + dy, z0 + 1.8), 0.24, bone, segs=10))
    b.add(block("aisle", (x + 1.2, y, z0 + 0.01), (s[0] - 3.4, 1.2, 0.02), "red", bevel=0))
    lamp(b, "lamp.7", (x, y, s[2] - CHANTRY_WALL - 0.02), material="gold_light", rim=gold, r=0.25)


# ---------------------------------------------------------------------------------------- SPEC

def _boxes():
    (nx, ny), (nsx, nsy) = NAVE
    (tx, ty), (tsx, tsy) = TOWER
    fy = ty - tsy / 2
    az = FLOOR + 0.4
    out = [
        box("terrace", (0, 4.75, (TT - 0.3) / 2), (34.0, 42.5, TT + 0.3)),
        box("nave floor", (nx, ny, FLOOR - 0.4), (nsx, nsy, 0.8)),
        box("narthex floor", (tx, ty, FLOOR - 0.4), (tsx, tsy, 0.8)),
        slope((0, STAIR_FOOT, 0), 12.0, STAIR_RUN, TT, 1),
        box("shoulder", (0, 22.75, SHOULDER - 2.0), (26.4, 3.5, 4.0)),
        box("ledge", (0, 25.05, TT + 1.0), (26.4, 1.1, 2.0)),
        box("nave front", (-6.5, ny - nsy / 2 + W / 2, (FLOOR + EAVE) / 2), (7.0, W, EAVE - FLOOR)),
        box("nave front", (6.5, ny - nsy / 2 + W / 2, (FLOOR + EAVE) / 2), (7.0, W, EAVE - FLOOR)),
        box("nave arch", (0, ny - nsy / 2 + W / 2, (FLOOR + 7.0 + EAVE) / 2), (6.0, W, EAVE - FLOOR - 7.0)),
        box("nave back", (0, ny + nsy / 2 - W / 2, (FLOOR + EAVE) / 2), (nsx, W, EAVE - FLOOR)),
        box("nave roof", (nx, ny, EAVE - W / 2), (nsx, nsy, W)),
        box("apse", (0, 22.6, SHOULDER + 2.6), (12.0, 3.2, 5.2)),
        box("portal wall", (-(2.2 + 6.0) / 2, fy + W / 2, (FLOOR + TT + 8.0) / 2), (6.0 - 2.2, W, TT + 8.0 - FLOOR)),
        box("portal wall", ((2.2 + 6.0) / 2, fy + W / 2, (FLOOR + TT + 8.0) / 2), (6.0 - 2.2, W, TT + 8.0 - FLOOR)),
        box("portal lintel", (0, fy + W / 2, (FLOOR + 6.5 + TT + 8.0) / 2), (4.4, W, TT + 8.0 - FLOOR - 6.5)),
        box("narthex ceiling", (tx, ty, TT + 7.6), (tsx, tsy, 0.8)),
        box("stage", (tx, ty, TT + 10.5), (tsx, tsy, 5.0)),
        box("cornice", (tx, ty, TT + 17.9), (tsx + 0.8, tsy + 0.8, 0.8)),
        box("cap", (tx, ty, TT + 19.5), (tsx * 0.6, tsy * 0.6, 2.4)),
        *[box("portal order", (sx * 4.2, fy - 0.45, FLOOR + 4.25), (0.6, 1.0, 8.5)) for sx in (-1, 1)],
        *[box("brazier", (sx * 3.6, -13.4, TT + 0.85), (1.0, 1.0, 1.7)) for sx in (-1, 1)],
        *[box("font", (sx * 3.2, -6.4, FLOOR + 0.5), (0.7, 0.7, 1.0)) for sx in (-1, 1)],
        *[box("column", (x, y, (FLOOR + TT + 6.0) / 2), (1.5, 1.5, TT + 6.0 - FLOOR)) for x, y in COLUMNS],
        box("dais", (0, 17.5, FLOOR + 0.2), (13.0, 5.4, 0.4)),
        box("dais step", (0, 14.6, FLOOR + 0.1), (13.0, 0.4, 0.2)),
        box("altar", (0, 16.8, az + 0.55), (3.2, 1.3, 1.1)),
        *[box("stall", (sx * 5.2, 17.0, az + 0.7), (0.9, 3.0, 1.4)) for sx in (-1, 1)],
        box("archive core", (0, 19.4, (az + CEIL) / 2), (4.0, 1.6, CEIL - az)),
        *[box("organ", (sx * 3.9, 19.75, az + 1.1), (3.8, 0.9, 2.2)) for sx in (-1, 1)],
        box("organ console", (6.0, 18.6, az + 0.55), (1.6, 0.7, 1.1)),
    ]
    for sx in (-1, 1):
        out += [
            box("shoulder", (sx * 9.6, -7.7, SHOULDER - 2.0), (7.2, 8.6, 4.0)),
            box("shoulder", (sx * 11.6, 8.8, SHOULDER - 2.0), (3.2, 24.4, 4.0)),
            box("ledge", (sx * 14.7, 6.75, TT + 1.0), (3.0, 37.5, 2.0)),
            box("nave wall", (sx * (nsx / 2 - W / 2), ny, (FLOOR + EAVE) / 2), (W, nsy, EAVE - FLOOR)),
            box("roof slope", (sx * 5.4, ny + 0.2, (EAVE + RIDGE) / 2 - 0.1), (math.hypot(nsx / 2 + 0.8, RIDGE - EAVE + 0.2), nsy + 0.4, 0.3), (0, sx * math.degrees(math.atan2(RIDGE - EAVE + 0.2, nsx / 2 + 0.8)), 0)),
            box("narthex wall", (sx * (tsx / 2 - W / 2), ty, (FLOOR + TT + 8.0) / 2), (W, tsy, TT + 8.0 - FLOOR)),
            *[box("pier", (sx * (tsx / 2 - 1.1), ty + py * (tsy / 2 - 1.1), TT + 15.25), (2.2, 2.2, 4.5)) for py in (-1, 1)],
            *[box("cheek", (sx * 6.8, STAIR_FOOT + (k + 0.5) * STAIR_RUN / 3, (TT * (k + 1) / 3 + 1.0) / 2), (1.6, STAIR_RUN / 3, TT * (k + 1) / 3 + 1.0)) for k in range(3)],
            *[box("buttress", (sx * 11.5, y, SHOULDER + 1.15), (3.0, 2.4, 2.3)) for y in BUTTRESSES],
            *[box("data vault", (sx * 14.7, y, TT + 2.12 + 2.2), (2.4, 2.6, 4.4)) for y in VAULTS],
            *[box("server stack", (sx * 8.85, y, FLOOR + 1.6), (0.7, 1.9, 3.2)) for y in BAYS],
            box("chantry brazier", (CHANTRY[0][0] + CHANTRY[1][0] / 2 + 1.4, CHANTRY[0][1] + sx * 1.5, 0.6), (0.6, 0.6, 1.2)),
        ]
    (x, y), s = CHANTRY
    out += [*room_boxes("chantry", CHANTRY[0], CHANTRY[1], CHANTRY_DOORS, wall=CHANTRY_WALL),
            box("chantry altar", (CHANTRY_ALTAR[0], CHANTRY_ALTAR[1], CHANTRY_WALL + 0.525), (1.0, 2.6, 1.05)),
            *[box("chantry buttress", (x + sx * (s[0] / 2 + 0.4), y + sy * (s[1] / 2 + 0.4), 1.4), (1.1, 1.1, 2.8)) for sx in (-1, 1) for sy in (-1, 1)]]
    return out


SPEC = {
    "build": build,
    "name": "The Reliquary",
    "color": (1.0, 0.2, 0.2),
    "faction": "regime",
    "body": "bastion",
    "lat": 18.0,
    "lon": -35.0,
    "footprint": (35.0, 49.0),
    "footprint_at": (0.0, 1.75),
    "pad": (0.0, -36.0),
    "door": (0.0, -11.6, FLOOR + 1.3),
    "size": (48.1, 34.2, 28.5),
    "depth": 0.3,
    "nodes": [f"lamp.{i}" for i in range(8)] + [f"fire.{i}" for i in range(len(FIRES))] + [f"smoke.{i}" for i in range(len(SMOKES))]
             + [f"blink.{i}" for i in range(len(BLINKS))] + [f"sound.{k}.0" for k, _ in SOUNDS] + [BELL_SPIN, CENSER_SPIN],
    "traffic": "litany",
    "crew": [
        # The priest behind the shrine's altar in the chantry, facing the door (+X).
        ("zealot", (-16.2, -19.5, CHANTRY_WALL), 90, []),
        # Two acolytes processing round the nave in opposite directions: up the aisle, across before
        # the dais, down a side aisle and back across inside the door.
        ("acolyte", (-0.6, -1.3, FLOOR), 0, [(-0.6, -1.3, FLOOR), (-0.6, 13.3, FLOOR), (-7.3, 13.3, FLOOR), (-7.3, -1.3, FLOOR)]),
        ("acolyte", (0.6, 13.3, FLOOR), 180, [(0.6, 13.3, FLOOR), (0.6, -1.3, FLOOR), (7.3, -1.3, FLOOR), (7.3, 13.3, FLOOR)]),
        # A choir keeping watch along the forecourt at the top of the steps.
        ("choir", (-12.5, -14.6, TT), 270, [(-12.5, -14.6, TT), (12.5, -14.6, TT), (0.0, -14.4, TT)]),
        # A choir at the organ console on the dais.
        ("choir", (6.2, 17.3, FLOOR + 0.4), 180, []),
    ],
    "boxes": _boxes(),
    "stations": [("shrine", (CHANTRY_ALTAR[0] + 1.5, CHANTRY[0][1], 1.4), "Shrine")],
    "view": {"cam": (-44.0, -50.0, 20.0), "look": (0, 2.0, 7.0), "lens": 35},
    "annex": {"cam": (-8.6, -19.9, 2.0), "look": (-15.5, -19.5, 1.6), "lens": 22},
    "annex_out": {"cam": (-2.0, -34.0, 6.0), "look": (-12.0, -19.5, 2.5), "lens": 30},
    "inside": {"cam": (0.0, -9.5, FLOOR + 1.7), "look": (0, 15.0, FLOOR + 3.0), "lens": 22},
}
