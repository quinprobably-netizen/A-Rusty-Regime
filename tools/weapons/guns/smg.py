"""Stinger SMG: a compact grey bullpup with red accents, a skeleton handguard under a full-length rail,
an AUG-style full-hand trigger guard and a magazine behind the grip with a witness window onto the
stacked brass."""

import math

import bpy  # first, so bmesh imports
import bmesh
from mathutils import Matrix, Vector

from kit import _apply, _obj, apply_modifiers, begin, block, cyl, dimples, hole_through, join, mat, mlok, pin, prism, rail, ring, screw, slots, tube
from parts import MAKER, SLOT_ATTS, attachments, common_clips, mag_drop

BORE = 0.045
MAG_PIVOT = (0.0, -0.112, -0.035)
MAG_TILT = -6.0  # degrees about X: the mag leans back as it goes down, away from the grip
MAG_AXIS = (math.sin(math.radians(MAG_TILT)), -math.cos(math.radians(MAG_TILT)))  # (y, z) toward its base
F = 1 / 60  # one frame: fire keys sit on frame boundaries so none collapse onto frame 0

# Handguard / receiver cross-sections, (x, z).
HG = [(-0.024, 0.010), (-0.016, 0.002), (0.016, 0.002), (0.024, 0.010), (0.024, 0.062), (0.017, 0.070), (-0.017, 0.070), (-0.024, 0.062)]
UPPER = [(-0.022, 0.022), (0.022, 0.022), (0.022, 0.063), (0.015, 0.070), (-0.015, 0.070), (-0.022, 0.063)]
# Pistol grip side profile (y, z); GRIP_FRONT runs bottom to top along its finger grooves.
GRIP_FRONT = [(-0.034, -0.106), (-0.028, -0.092), (-0.024, -0.078), (-0.023, -0.066), (-0.018, -0.060), (-0.015, -0.045),
              (-0.013, -0.033), (-0.009, -0.020), (-0.003, -0.008), (0.002, 0.003)]
GRIP = [(-0.050, 0.003), (-0.058, -0.030), (-0.072, -0.098), (-0.069, -0.106)] + GRIP_FRONT


# ------------------------------------------------------------------------------------- helpers

def ext_y(name, pts, y0, y1, material, bevel=0.0008, segs=2):
    """Extrude a cross-section [(x, z), ...] along Y from y0 to y1."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y0, z)) for x, z in pts]
    face = bm.faces.new(vs)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, y1 - y0, 0), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, material, bevel, segs)


def turn(objs, deg, axis, pivot, move=(0, 0, 0)):
    """Rotate mesh data about `pivot` (then shift by `move`), in place."""
    p = Vector(pivot)
    m = Matrix.Translation(p + Vector(move)) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-p)
    for o in objs:
        o.data.transform(m)
    return objs


def inset(pts, d):
    """Offset a convex polygon inward by d (any winding)."""
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    s = 1 if area > 0 else -1
    lines = []
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy)
        nx, ny = -dy / ln * s, dx / ln * s
        lines.append(((ax + nx * d, ay + ny * d), (dx, dy)))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append((p1[0] + t * d1[0], p1[1] + t * d1[1]))
    return out


def cutx(target, *cutters):
    """kit.cut with self-intersection on: kit.cut empties the target when its joined cutters overlap
    (e.g. kit.mlok's block + end caps), so every cut here goes through this."""
    if not cutters:
        return target
    cutter = join(list(cutters), "_cutter") if len(cutters) > 1 else cutters[0]
    mod = target.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.use_self = True
    mod.object = cutter
    _apply(target, mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def fuse(objs, name):
    """Join parts after baking each one's own bevel. kit.Gun.finish bevels a joined group with its first
    member's width, which would bevel stippling and lettering too."""
    for o in objs:
        apply_modifiers(o)
    out = join(objs, name)
    out["bevel"] = 0.0
    return out


def prebevel(o):
    """Bevel now, so stippling cut afterwards keeps sharp, cheap rims instead of being bevelled too."""
    apply_modifiers(o)
    o["bevel"] = 0.0
    return o


def reshade(o, angle=35):
    """Clean shading after cutting into an already bevelled part: drop the stale custom normals, mark
    hard edges sharp, re-weight. Without this the stippling smears into blotches."""
    _apply_select(o)
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(angle):
            e.smooth = False
    bm.to_mesh(o.data)
    bm.free()
    m = o.modifiers.new("wn", "WEIGHTED_NORMAL")
    m.keep_sharp = True
    _apply(o, m.name)
    return o


def _apply_select(o):
    bpy.context.view_layer.objects.active = o
    for other in bpy.context.selected_objects:
        other.select_set(False)
    o.select_set(True)


def flat(o):
    """No bevel for tiny parts (threads, cups) where it only costs triangles."""
    o["bevel"] = 0.0
    return o


def label(text, at, size, material, side=-1, depth=0.0003):
    """kit.label with a coarse curve resolution: the default 12 steps per curve cost ~1k tris a word."""
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = depth
    cu.resolution_u = 3
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    o = bpy.data.objects.new("label", cu)
    bpy.context.scene.collection.objects.link(o)
    o.location = at
    o.rotation_euler = (math.pi / 2, 0, -math.pi / 2 if side < 0 else math.pi / 2)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    mw = o.matrix_world.copy()
    bpy.data.objects.remove(o, do_unlink=True)
    me.transform(mw)
    me.materials.clear()
    me.materials.append(mat(material))
    out = bpy.data.objects.new("label", me)
    bpy.context.scene.collection.objects.link(out)
    out["bevel"] = 0.0
    return out


def zslot(y0, y1, x, z, w, depth=0.02):
    """Rounded slot cutter running along Y, cut down through Z."""
    return [block("zs", (x, (y0 + y1) / 2, z), (w, y1 - y0 - w, depth), "steel", bevel=0),
            cyl("zs", (x, y0 + w / 2, z - depth / 2), (x, y0 + w / 2, z + depth / 2), w / 2, "steel", segs=12, bevel=0),
            cyl("zs", (x, y1 - w / 2, z - depth / 2), (x, y1 - w / 2, z + depth / 2), w / 2, "steel", segs=12, bevel=0)]


def grip_dimples(x, side):
    """Stippling that follows the grip's rake: rows up the grip, columns centred on its mid line."""
    out = []
    rows = 11
    for j in range(rows):
        z = -0.094 + j * (0.078 / (rows - 1))
        yc = -0.0275 + 0.2475 * z
        cols = 5
        for i in range(cols):
            y = yc + (i - (cols - 1) / 2) * 0.0068 + (0.0034 if j % 2 else 0.0)
            out.append(cyl("st", (x - side * 0.002, y, z), (x + side * 0.002, y, z), 0.00115, "steel", segs=8, bevel=0))
    return out


def ribs_z(y, x, z0, z1, count, w, depth, length):
    """Horizontal groove cutters stacked up Z on a face facing Y."""
    step = (z1 - z0) / max(1, count - 1)
    return [block("rz", (x, y, z0 + i * step), (length, depth, w), "steel", bevel=0) for i in range(count)]


# ---------------------------------------------------------------------------------------- build

def build():
    """Stinger: grey bullpup, red accents, skeleton handguard, mag behind the grip."""
    g = begin("smg", {
        "bolt": ((0, -0.17, BORE), None),
        "charge": ((-0.0265, 0.07, 0.049), None),
        "mag": (MAG_PIVOT, None),
        "trigger": ((0, 0.012, 0.002), None),
        "catch": ((-0.025, -0.066, 0.006), None),
        "release": ((-0.025, -0.163, -0.012), None),
    })

    # --- Upper receiver: chamfered extrusion with bore cavity, ejection port (right), charging slot (left).
    up = ext_y("upper", UPPER, -0.288, 0.092, "steel", bevel=0.0012, segs=2)
    cuts = [hole_through("cav", (0, -0.0875, BORE), 0.0135, "y", 0.365, segs=28),
            block("port", (0.017, -0.125, 0.047), (0.012, 0.06, 0.022), "steel", bevel=0),
            block("cslot", (-0.018, 0.0215, 0.049), (0.012, 0.113, 0.009), "steel", bevel=0),
            block("feed", (0, -0.112, 0.028), (0.022, 0.036, 0.012), "steel", bevel=0),
            prism("rch", [(-0.295, 0.050), (-0.295, 0.080), (-0.276, 0.080)], 0.06, "steel", bevel=0)]
    for s in (-1, 1):  # long lightening grooves along both sides
        x = s * 0.022
        cuts += [prism("vent", [(y0, 0.0255), (y0 + 0.008, 0.0255), (y0 + 0.0145, 0.0365), (y0 + 0.0065, 0.0365)], 0.006, "steel", x=x, bevel=0)
                 for y0 in (-0.274 + i * 0.0135 for i in range(8))]
        cuts += [block("gr", (x, 0.02, 0.031), (0.003, 0.09, 0.0032), "steel", bevel=0)] if s < 0 else []
    up = cutx(up, *cuts)
    upper_bits = [up]
    upper_bits.append(label("STINGER", (-0.0221, -0.205, 0.051), 0.0115, "red"))
    upper_bits.append(label("SMG-5   9x19mm", (-0.0221, -0.205, 0.0418), 0.0032, "bright"))
    upper_bits.append(label("No. RR-0517", (-0.0221, -0.125, 0.0418), 0.0026, "bright"))
    upper_bits.append(label(MAKER, (0.0221, -0.225, 0.052), 0.0034, "bright", side=1))
    upper_bits.append(label("CAL 9x19  STINGER SMG-5", (0.0221, -0.225, 0.043), 0.0026, "bright", side=1))
    for y, z in ((-0.272, 0.052), (-0.15, 0.03), (-0.075, 0.03), (-0.045, 0.058), (0.083, 0.031)):
        upper_bits.append(screw((-0.0224, y, z), "-x", 0.0021))
    for y, z in ((-0.272, 0.052), (-0.06, 0.03), (0.06, 0.03)):
        upper_bits.append(screw((0.0224, y, z), "x", 0.0021))
    # Brass deflector behind the port, and the chamber hood forward of it.
    defl = prism("defl", [(-0.184, 0.029), (-0.158, 0.029), (-0.158, 0.064), (-0.170, 0.067), (-0.184, 0.058)], 0.009, "steel", x=0.0255,
                 bevel=0.0012, segs=2)
    defl = cutx(defl, *slots("ds", -0.180, -0.162, 4, 0.034, 0.06, 0.029, 0.031))
    upper_bits.append(defl)
    # Top rail along the whole gun, numbered on its left flank.
    upper_bits.append(rail("rail", -0.272, 0.244, 0.070, "black"))
    for i, y in enumerate(range(-265, 240, 50)):
        upper_bits.append(label(str(i + 1), (-0.0086, y / 1000, 0.072), 0.0026, "bright"))
    # Charging rod inside the slot side of the cavity is on the charge bone (below).

    # --- Lower / stock shell.
    lower_pts = [(0.090, 0.024), (0.090, 0.010), (0.082, 0.000), (-0.060, 0.000), (-0.078, -0.020), (-0.082, -0.036), (-0.140, -0.036),
                 (-0.160, -0.032), (-0.200, -0.052), (-0.250, -0.070), (-0.286, -0.078), (-0.292, -0.072), (-0.292, 0.024)]
    lo = prism("lower", lower_pts, 0.048, "grey", bevel=0.0016, segs=3)
    mw = block("mw", (0, 0, 0.0), (0.0275, 0.0375, 0.12), "steel", bevel=0)
    turn([mw], MAG_TILT, "X", (0, 0, 0), MAG_PIVOT)
    cuts = [mw, block("tslot", (0, 0.013, 0.003), (0.008, 0.018, 0.012), "steel", bevel=0),
            block("cheek", (-0.024, -0.23, -0.013), (0.003, 0.084, 0.05), "steel", bevel=0)]
    cuts += mlok("sling", -0.292, -0.262, 1, -0.06, 0.0, depth=0.06, h=0.0065)
    cuts += mlok("rs", -0.272, -0.180, 3, -0.018, 0.024, depth=0.004, h=0.009)
    cuts += [hole_through("qd", (-0.024, 0.058, 0.009), 0.0032, "x", 0.012, segs=16)]
    lo = cutx(lo, *cuts)
    lo = reshade(cutx(prebevel(lo), *dimples("st", -0.266, -0.194, -0.032, 0.006, -0.0225, 11, 7, r=0.00115, depth=0.0018)))
    lower_bits = [lo]
    for s in (-1, 1):  # thin red stripe along the seam
        lower_bits.append(block("stripe", (s * 0.0243, -0.1425, 0.0175), (0.0008, 0.285, 0.0026), "red", bevel=0.0002))
    lower_bits.append(flat(ring("qdcup", (-0.0247, 0.058, 0.009), (1, 0, 0), 0.0058, 0.0032, 0.0016, "steel", segs=20)))
    lower_bits.append(flat(ring("fence", (-0.0248, -0.163, -0.012), (1, 0, 0), 0.0068, 0.0049, 0.0022, "grey", segs=24)))
    # Take-down pins with heads, and a few screws.
    for y, z in ((-0.282, 0.004), (0.03, 0.009)):
        lower_bits.append(pin((0, y, z), "x", 0.0016, 0.0505, "bright"))
        lower_bits.append(cyl("pinhead", (-0.0242, y, z), (-0.0262, y, z), 0.0034, "steel", segs=18, bevel=0.0003))
    for y, z in ((-0.145, 0.006), (-0.272, -0.052), (0.075, 0.016)):
        lower_bits.append(screw((-0.0244, y, z), "-x", 0.0021))
    for y, z in ((-0.145, 0.006), (-0.272, -0.052), (-0.04, 0.012)):
        lower_bits.append(screw((0.0244, y, z), "x", 0.0021))
    # Cross-bolt selector above the grip, S / F marked, red dot on fire.
    sel = cyl("sel", (-0.0238, -0.022, 0.009), (-0.0275, -0.022, 0.009), 0.0042, "black", segs=20)
    sel = cutx(sel, block("selslot", (-0.0275, -0.022, 0.009), (0.002, 0.0012, 0.006), "steel", bevel=0))
    lower_bits += [sel, cyl("selr", (0.0238, -0.022, 0.009), (0.0262, -0.022, 0.009), 0.0036, "black", segs=18),
                   label("S", (-0.0241, -0.0325, 0.009), 0.004, "bright"), label("F", (-0.0241, -0.0115, 0.009), 0.004, "bright"),
                   cyl("fdot", (-0.0240, -0.0115, 0.0035), (-0.0246, -0.0115, 0.0035), 0.0011, "red", segs=10, bevel=0)]
    lower_bits.append(label("MADE ON THE ISLAND", (0.0241, -0.235, -0.04), 0.0028, "black", side=1))
    # Magwell flare.
    flare = block("flare", (0, 0, -0.003), (0.034, 0.044, 0.008), "grey", bevel=0.0015, segs=2)
    flare = cutx(flare, block("fi", (0, 0, -0.003), (0.0255, 0.0355, 0.03), "steel", bevel=0))
    turn([flare], MAG_TILT, "X", (0, 0, 0), MAG_PIVOT)
    lower_bits.append(flare)

    # --- Pistol grip (black polymer, stippled) and the full-hand trigger guard.
    grip = prism("grip", GRIP, 0.030, "black", bevel=0.002, segs=3)
    grip = reshade(cutx(prebevel(grip), *grip_dimples(-0.015, -1), *grip_dimples(0.015, 1)))
    guard_out = [(0.084, 0.002), (0.089, -0.020), (0.084, -0.048), (0.067, -0.078), (0.040, -0.102), (0.006, -0.117), (-0.034, -0.120),
                 (-0.074, -0.120), (-0.074, -0.104), (-0.040, -0.100), (-0.012, 0.002)]
    guard_in = [(0.072, -0.002), (0.077, -0.020), (0.073, -0.045), (0.057, -0.072), (0.033, -0.093), (0.004, -0.106)]
    guard_in += [(y - 0.003, z) for y, z in GRIP_FRONT[:-1]] + [(-0.001, 0.006)]
    guard = prism("guard", guard_out, 0.020, "grey", bevel=0.0015, segs=3)
    guard = cutx(guard, prism("gin", guard_in, 0.05, "steel", bevel=0))
    grip_bits = [grip, guard, pin((0, 0.079, -0.004), "x", 0.0016, 0.0215),
                 screw((0, -0.054, -0.1205), "-z", 0.0024), screw((-0.0102, 0.03, -0.103), "-x", 0.0018)]
    # Ribbed finger pad on the guard's inner front.
    grip_bits += [block("gpad", (0, 0.074 + 0.0, -0.03 - i * 0.008), (0.014, 0.003, 0.003), "grey", bevel=0.0004) for i in range(3)]

    # --- Handguard: skeleton shell with truss windows, slotted belly, front cap, under rail.
    hg = ext_y("hg", HG, 0.088, 0.250, "steel", bevel=0.0012, segs=2)
    cuts = [ext_y("hgin", inset(HG, 0.0028), 0.080, 0.26, "steel", bevel=0)]
    zb, zt = 0.016, 0.058
    yb = [0.100, 0.147, 0.194, 0.241]
    yt = [0.1235, 0.1705, 0.2175]
    tris = []
    for i in range(3):
        tris.append([(yb[i], zb), (yb[i + 1], zb), (yt[i], zt)])
        if i < 2:
            tris.append([(yt[i], zt), (yb[i + 1], zb), (yt[i + 1], zt)])
    cuts += [prism("win", inset(t, 0.0034), 0.06, "steel", bevel=0) for t in tris]
    cuts += zslot(0.098, 0.128, 0, 0.002, 0.0075) + zslot(0.134, 0.164, 0, 0.002, 0.0075)
    hg = cutx(hg, *cuts)
    cap = ext_y("cap", inset(HG, -0.0004), 0.243, 0.252, "black", bevel=0.0008)
    cap = cutx(cap, hole_through("cb", (0, 0.25, BORE), 0.0098, "y", 0.03, segs=24),
              *[hole_through("cv", (s * 0.014, 0.25, z), 0.0022, "y", 0.03, segs=12) for s in (-1, 1) for z in (0.02, 0.054)])
    hg_bits = [hg, cap, rail("urail", 0.170, 0.236, 0.002, "black", flip=True)]
    for s in (-1, 1):
        for z in (0.02, 0.052):
            hg_bits.append(screw((s * 0.0244, 0.094, z), "x" if s > 0 else "-x", 0.0021))
    # Barrel: fluted inside the handguard, nut, threads at the muzzle, chamber hood at the port.
    barrel = tube("barrel", (0, -0.12, BORE), (0, 0.262, BORE), 0.0075, 0.0045, "steel", segs=28)
    flutes = []
    for k in range(6):
        c = block("fl", (0, 0.165, BORE + 0.0076), (0.0024, 0.12, 0.0034), "steel", bevel=0)
        turn([c], 30 + k * 60, "Y", (0, 0, BORE))
        flutes.append(c)
    barrel = cutx(barrel, *flutes)
    nut = ring("nut", (0, 0.1, BORE), (0, 1, 0), 0.0148, 0.0074, 0.012, "steel", segs=28)
    nut = cutx(nut, *[turn([block("nn", (0, 0.1, BORE + 0.0148), (0.004, 0.016, 0.004), "steel", bevel=0)], k * 45, "Y", (0, 0, BORE))[0]
                     for k in range(8)])
    barrel_bits = [barrel, nut, cyl("chamber", (0, -0.122, BORE), (0, -0.092, BORE), 0.0108, "steel", segs=24)]
    barrel_bits += [flat(ring("th", (0, 0.2508 + i * 0.0018, BORE), (0, 1, 0), 0.0080, 0.0070, 0.0009, "steel", segs=20)) for i in range(6)]
    barrel_bits.append(flat(ring("washer", (0, 0.2535, BORE), (0, 1, 0), 0.0095, 0.0072, 0.0015, "bright", segs=24)))

    g.add(fuse(upper_bits + lower_bits + grip_bits + hg_bits + barrel_bits, "body"), "root")

    # --- Bolt: visible through the port, flats and grooves on its right face.
    bolt = cyl("bolt", (0, -0.215, BORE), (0, -0.122, BORE), 0.0128, "bright", segs=28, bevel=0.0005)
    bolt = cutx(bolt, block("flat", (0.0128, -0.17, BORE), (0.004, 0.1, 0.03), "steel", bevel=0),
               *slots("bg", -0.205, -0.15, 6, BORE - 0.0065, BORE + 0.0065, 0.0095, 0.0125),
               hole_through("face", (0, -0.122, BORE), 0.0048, "y", 0.004, segs=18),
               block("top", (0, -0.17, BORE + 0.0128), (0.006, 0.1, 0.003), "steel", bevel=0))
    extractor = block("ext", (0.0108, -0.131, BORE + 0.004), (0.003, 0.02, 0.004), "steel", bevel=0.0003)
    g.add(fuse([bolt, extractor, pin((0.005, -0.18, BORE), "z", 0.0012, 0.022, "steel")], "bolt"), "bolt")

    # --- Side-folding charging handle on the left of the upper, plus its rod inside the cavity.
    slider = block("slider", (-0.0165, 0.07, 0.049), (0.013, 0.012, 0.0085), "steel", bevel=0.0004)
    knuckle = cyl("knuckle", (-0.0265, 0.07, 0.0425), (-0.0265, 0.07, 0.0555), 0.0035, "steel", segs=18)
    hpin = cyl("hpin", (-0.0265, 0.07, 0.041), (-0.0265, 0.07, 0.057), 0.0012, "bright", segs=10, bevel=0.0002)
    arm = prism("arm", [(0.068, 0.0445), (0.040, 0.0445), (0.032, 0.0425), (0.029, 0.049), (0.032, 0.0555), (0.040, 0.0535), (0.068, 0.0535)],
                0.004, "black", x=-0.0285, bevel=0.0006)
    arm = cutx(arm, *slots("cg", 0.032, 0.044, 5, 0.040, 0.058, -0.0315, -0.0297))
    rod = cyl("rod", (-0.009, -0.05, 0.051), (-0.009, 0.07, 0.051), 0.0025, "bright", segs=14)
    g.add(fuse([slider, knuckle, hpin, arm, rod], "charge"), "charge")

    # --- Red trigger, red bolt catch, red mag release.
    trig = prism("trigger", [(0.008, 0.007), (0.016, 0.007), (0.0165, -0.006), (0.0195, -0.018), (0.021, -0.027), (0.0175, -0.030),
                             (0.0135, -0.020), (0.009, -0.008)], 0.006, "red", bevel=0.0005)
    trig = cutx(trig, *[block("ts", (0, 0.0198 - i * 0.0004, -0.013 - i * 0.004), (0.01, 0.0016, 0.0012), "steel", bevel=0, rot=-20)
                       for i in range(4)])
    g.add(fuse([trig, pin((0, 0.012, 0.002), "x", 0.0013, 0.012)], "trigger"), "trigger")

    catch = prism("catch", [(-0.084, -0.004), (-0.070, -0.001), (-0.060, 0.004), (-0.060, 0.010), (-0.070, 0.011), (-0.086, 0.004)], 0.003,
                  "red", x=-0.0257, bevel=0.0004)
    catch = cutx(catch, *[block("cr", (-0.0272, -0.082 + i * 0.004, 0.003), (0.0012, 0.0014, 0.02), "steel", bevel=0) for i in range(4)])
    g.add(fuse([catch, cyl("cpiv", (-0.0238, -0.066, 0.006), (-0.0278, -0.066, 0.006), 0.0032, "red", segs=16),
                cyl("cscr", (-0.0278, -0.066, 0.006), (-0.0284, -0.066, 0.006), 0.0016, "steel", segs=10)], "catch"), "catch")

    rel = cyl("release", (-0.0236, -0.163, -0.012), (-0.0278, -0.163, -0.012), 0.0045, "red", segs=22)
    rel = cutx(rel, *[block("rr", (-0.0279, -0.163, -0.0145 + i * 0.0025), (0.0014, 0.012, 0.0009), "steel", bevel=0) for i in range(3)])
    g.add(rel, "release")

    # --- Magazine: hollow body with a witness window onto 30 staggered rounds; built upright then tilted.
    mag = block("mag", (0, 0, -0.029), (0.024, 0.034, 0.172), "black", bevel=0.0012)
    mag = cutx(mag, block("min", (0, 0, -0.02), (0.020, 0.030, 0.17), "steel", bevel=0),
              block("win", (-0.011, -0.001, -0.052), (0.006, 0.02, 0.08), "steel", bevel=0),
              *[hole_through("wh", (0.011, -0.006, -0.03 - i * 0.02), 0.0016, "x", 0.006, segs=12) for i in range(4)])
    frame = block("rim", (-0.0124, -0.001, -0.052), (0.0012, 0.026, 0.086), "black", bevel=0.0003)
    frame = cutx(frame, block("rimin", (-0.0124, -0.001, -0.052), (0.004, 0.02, 0.08), "steel", bevel=0))
    mag_bits = [mag, frame]
    mag_bits += [block("spine", (0, s * 0.0172, -0.04), (0.012, 0.0014, 0.15), "black", bevel=0.0003) for s in (-1, 1)]
    mag_bits += [block("rib", (-0.0124, -0.001, z), (0.0012, 0.026, 0.0016), "black", bevel=0.0002) for z in (-0.1, -0.106)]
    mag_bits += [block("lip", (s * 0.0085, -0.002, 0.059), (0.004, 0.028, 0.004), "black", bevel=0.0004) for s in (-1, 1)]
    pad = block("pad", (0, -0.001, -0.121), (0.028, 0.040, 0.012), "grey", bevel=0.002, segs=3)
    pad = cutx(pad, *ribs_z(-0.021, 0, -0.125, -0.117, 3, 0.0014, 0.002, 0.03))
    mag_bits += [pad, screw((0, -0.001, -0.1272), "-z", 0.0022), label("30", (-0.0131, -0.001, -0.1025), 0.0042, "bright")]
    for i in range(31):  # double stack: alternate sides, 4.9 mm per round
        z = 0.063 - i * 0.0049
        x = 0.0 if i == 0 else (-0.0043 if i % 2 else 0.0043)
        mag_bits.append(cyl("case", (x, -0.0145, z), (x, 0.0035, z), 0.00485, "brass", segs=12, bevel=0))
        mag_bits.append(cyl("tip", (x, 0.0035, z), (x, 0.0135, z), 0.0045, "copper", r1=0.0021, segs=12, bevel=0))
    turn(mag_bits, MAG_TILT, "X", (0, 0, 0), MAG_PIVOT)
    g.add(fuse(mag_bits, "mag"), "mag")

    # --- Gunsmith: the bare gun's own parts first (irons, brake, hand stop, skeleton butt pad).
    top = (0, -0.095, 0.0776)
    rz = 0.0776
    rear_base = block("att.optic.irons", (0, -0.25, rz + 0.004), (0.022, 0.022, 0.008), "black", bevel=0.0008)
    leaf = block("leaf", (0, -0.251, rz + 0.019), (0.022, 0.005, 0.024), "black", bevel=0.0006)
    leaf = cutx(leaf, block("ln", (0, -0.251, rz + 0.031), (0.012, 0.01, 0.012), "steel", bevel=0),
               hole_through("peep", (0, -0.251, rz + 0.019), 0.0015, "y", 0.01, segs=14))
    disc = ring("disc", (0, -0.2535, rz + 0.019), (0, 1, 0), 0.0048, 0.0015, 0.0012, "steel", segs=20)
    wind = cyl("wind", (-0.011, -0.25, rz + 0.005), (-0.016, -0.25, rz + 0.005), 0.0035, "steel", segs=16)
    wind = cutx(wind, *[turn([block("kn", (-0.0135, -0.25, rz + 0.0085), (0.006, 0.0008, 0.0015), "steel", bevel=0)], k * 30, "X",
                            (0, -0.25, rz + 0.005))[0] for k in range(12)])
    front_base = block("fbase", (0, 0.232, rz + 0.004), (0.022, 0.018, 0.008), "black", bevel=0.0008)
    tower = prism("tower", [(0.224, rz + 0.007), (0.240, rz + 0.007), (0.237, rz + 0.034), (0.227, rz + 0.034)], 0.022, "black", bevel=0.0006)
    tower = cutx(tower, block("tw", (0, 0.232, rz + 0.024), (0.016, 0.04, 0.02), "steel", bevel=0))
    post = cyl("post", (0, 0.232, rz + 0.008), (0, 0.232, rz + 0.026), 0.0011, "bright", segs=10, bevel=0)
    dot = cyl("dot", (0, 0.2306, rz + 0.0245), (0, 0.2304, rz + 0.0245), 0.0008, "lamp", segs=8, bevel=0)
    irons = fuse([rear_base, leaf, disc, wind, front_base, tower, post, dot, pin((0, -0.25, rz + 0.008), "x", 0.0011, 0.023),
                  pin((0, 0.232, rz + 0.008), "x", 0.0011, 0.023), screw((0.011, 0.232, rz + 0.004), "x", 0.0016)], "att.optic.irons")
    irons.name = "att.optic.irons"
    g.add(irons, "root")

    brake = cyl("att.muzzle.bare", (0, 0.256, BORE), (0, 0.300, BORE), 0.0115, "steel", segs=24, bevel=0.0006)
    brake = cutx(brake, hole_through("bb", (0, 0.28, BORE), 0.0056, "y", 0.06, segs=20),
                *[block("bp", (0, y, BORE), (0.03, 0.0055, 0.011), "steel", bevel=0) for y in (0.274, 0.284, 0.293)],
                *[hole_through("bt", (0, y, BORE + 0.009), 0.0019, "z", 0.01, segs=12) for y in (0.266, 0.279)],
                *[block("wf", (s * 0.0128, 0.2615, BORE), (0.004, 0.009, 0.03), "steel", bevel=0) for s in (-1, 1)])
    brake.name = "att.muzzle.bare"
    g.add(brake, "root")

    hstop = prism("att.grip.standard", [(0.212, -0.0056), (0.236, -0.0056), (0.234, -0.019), (0.229, -0.0235), (0.222, -0.019)], 0.018,
                  "black", bevel=0.0012, segs=2)
    hstop = fuse([hstop, screw((0.0094, 0.226, -0.009), "x", 0.0016)], "att.grip.standard")
    hstop.name = "att.grip.standard"
    g.add(hstop, "root")

    # Butt pads (the bullpup's stock slot): adjustable skeleton (standard), slim plate (light), thick pad (heavy).
    zc = -0.008
    rods = [cyl("rod", (0, -0.282, z), (0, -0.312, z), 0.0036, "steel", segs=16) for z in (0.035, -0.05)]
    rods += [ring("notch", (0, -0.296 - i * 0.004, z), (0, 1, 0), 0.0038, 0.0031, 0.0012, "bright", segs=16) for z in (0.035, -0.05)
             for i in range(3)]
    frame = block("att.stock.standard", (0, -0.311, zc), (0.040, 0.010, 0.142), "grey", bevel=0.002, segs=2)
    frame = cutx(frame, block("fw", (0, -0.311, 0.013), (0.026, 0.03, 0.026), "steel", bevel=0),
                block("fw", (0, -0.311, -0.029), (0.026, 0.03, 0.026), "steel", bevel=0))
    spad = block("spad", (0, -0.3215, zc), (0.044, 0.011, 0.148), "rubber", bevel=0.003, segs=3)
    spad = cutx(spad, *ribs_z(-0.327, 0, -0.07, 0.054, 14, 0.0022, 0.003, 0.06))
    std = fuse([frame, spad, *rods, cyl("adj", (-0.0195, -0.311, 0.052), (-0.0235, -0.311, 0.052), 0.0032, "red", segs=16),
                screw((0.0204, -0.311, 0.052), "x", 0.0018), screw((-0.0204, -0.311, -0.068), "-x", 0.0018)], "att.stock.standard")
    std.name = "att.stock.standard"
    g.add(std, "root")

    light = block("att.stock.light", (0, -0.297, zc), (0.042, 0.010, 0.150), "grey", bevel=0.0015, segs=2)
    light = cutx(light, *[block("lw", (0, -0.297, z), (0.028, 0.03, 0.03), "steel", bevel=0) for z in (0.034, -0.008, -0.05)])
    light = fuse([light, block("lp", (0, -0.3035, zc), (0.040, 0.004, 0.150), "rubber", bevel=0.0012)], "att.stock.light")
    light.name = "att.stock.light"
    g.add(light, "root")

    heavy = block("att.stock.heavy", (0, -0.298, zc), (0.046, 0.012, 0.152), "grey", bevel=0.002, segs=2)
    hpad = block("hp", (0, -0.317, zc), (0.050, 0.026, 0.162), "rubber", bevel=0.005, segs=3)
    hpad = cutx(hpad, *ribs_z(-0.317, -0.025, -0.075, 0.058, 10, 0.0025, 0.03, 0.004),
               *ribs_z(-0.317, 0.025, -0.075, 0.058, 10, 0.0025, 0.03, 0.004))
    heavy = fuse([heavy, hpad, label(MAKER, (-0.0251, -0.317, zc), 0.0026, "bright")], "att.stock.heavy")
    heavy.name = "att.stock.heavy"
    g.add(heavy, "root")

    # Shared parts: red dot / scope on the rail, comp / suppressor on the threads, foregrips on the under rail.
    attachments(g, top, (0, 0.262, BORE), (0, 0.203, -0.0056), None, muzzle_r=0.0085, scope=True,
                stock_socket=((0, -0.292, -0.005), "root"))
    g.socket("eject", (0.024, -0.125, 0.047), "root")

    # --- Clips.
    g.clip("fire", 0.07, {
        "bolt": [(0, (0, 0, 0), (0, 0, 0)), (F, (0, -0.045, 0), (0, 0, 0)), (3 * F, (0, 0, 0), (0, 0, 0))],
        "trigger": [(0, (0, 0, 0), (0, 0, 0)), (F, (0, 0, 0), (-12, 0, 0)), (3 * F, (0, 0, 0), (0, 0, 0))],
        "root": [(0, (0, 0, 0), (0, 0, 0)), (F, (0, -0.005, 0.0012), (2.5, 0, 0.6)), (0.07, (0, 0, 0), (0, 0, 0))],
    })
    unf = (0, 0, -90)
    common_clips(g, 2.1, {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.22, (0.01, 0, 0.03), (14, 24, 0)), (1.15, (0.01, 0, 0.03), (16, 26, 0)),
                 (1.32, (-0.01, 0, 0.02), (6, -18, -6)), (1.75, (-0.01, 0, 0.02), (8, -20, -6)), (1.95, (0, 0, 0.005), (2, 0, 0)),
                 (2.1, (0, 0, 0), (0, 0, 0))],
        "release": [(0, (0, 0, 0), (0, 0, 0)), (0.22, (0, 0, 0), (0, 0, 0)), (0.27, (0.002, 0, 0), (0, 0, 0)),
                    (0.42, (0.002, 0, 0), (0, 0, 0)), (0.47, (0, 0, 0), (0, 0, 0))],
        "mag": mag_drop(MAG_AXIS, 0.3, 0.95, 1.1),
        "charge": [(0, (0, 0, 0), (0, 0, 0)), (1.25, (0, 0, 0), (0, 0, 0)), (1.33, (0, 0, 0), unf), (1.48, (0, -0.055, 0), unf),
                   (1.53, (0, -0.055, 0), unf), (1.58, (0, 0, 0), unf), (1.68, (0, 0, 0), (0, 0, 0))],
        "bolt": [(0, (0, 0, 0), (0, 0, 0)), (1.33, (0, 0, 0), (0, 0, 0)), (1.48, (0, -0.055, 0), (0, 0, 0)),
                 (1.6, (0, -0.055, 0), (0, 0, 0)), (1.64, (0, 0, 0), (0, 0, 0))],
        "catch": [(0, (0, 0, 0), (0, 0, 0)), (1.4, (0, 0, 0), (0, 0, 0)), (1.48, (0, 0, 0), (-14, 0, 0)), (1.58, (0, 0, 0), (-14, 0, 0)),
                  (1.61, (0, 0, 0), (10, 0, 0)), (1.7, (0, 0, 0), (0, 0, 0))],
    }, draw_len=0.45)
    # Inspect: left side to camera, then roll to show the port while press-checking the bolt.
    g.clip("inspect", 2.6, {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.5, (-0.03, 0.02, 0.03), (10, -32, 25)), (1.3, (-0.03, 0.02, 0.03), (12, -37, 30)),
                 (1.75, (0.02, 0.0, 0.02), (-8, 32, -20)), (2.3, (0.02, 0.0, 0.02), (-6, 30, -18)), (2.55, (0, 0, 0), (0, 0, 0))],
        "charge": [(0, (0, 0, 0), (0, 0, 0)), (1.8, (0, 0, 0), (0, 0, 0)), (1.88, (0, 0, 0), unf), (2.0, (0, -0.025, 0), unf),
                   (2.12, (0, -0.025, 0), unf), (2.2, (0, 0, 0), unf), (2.3, (0, 0, 0), (0, 0, 0))],
        "bolt": [(0, (0, 0, 0), (0, 0, 0)), (1.88, (0, 0, 0), (0, 0, 0)), (2.0, (0, -0.025, 0), (0, 0, 0)),
                 (2.12, (0, -0.025, 0), (0, 0, 0)), (2.2, (0, 0, 0), (0, 0, 0))],
    })
    return g


BARE = ("att.optic.irons", "att.muzzle.bare", "att.grip.standard", "att.stock.standard")

SPEC = {"build": build, "length": (0.5, 0.64), "tris": (20000, 70000),
        "bones": ["root", "bolt", "charge", "mag", "trigger", "catch", "release"],
        "sockets": ["muzzle", "eject", "optic", "under", "stock", "scope.eye", "reddot.lens"],
        "attachments": SLOT_ATTS + list(BARE),
        "parts": {"mesh.root": "root", "mesh.bolt": "bolt", "mesh.charge": "charge", "mesh.mag": "mag", "mesh.trigger": "trigger",
                  "mesh.catch": "catch", "mesh.release": "release"},
        "moves": {"fire": ["bolt", "trigger", "root"], "reload": ["root", "mag", "release", "charge", "bolt", "catch"],
                  "draw": ["root"], "inspect": ["root", "charge", "bolt"]},
        "view": {"cam": (-0.9, -0.05, 0.22), "look": (0, -0.013, -0.025), "lens": 50, "show": BARE}}
