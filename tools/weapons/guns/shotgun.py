"""Breacher shotgun: a pump-action 12 gauge fed from a 20-round drum, with a ventilated heat shield,
twin action bars, a side saddle and a breaching muzzle."""

import math

import bmesh
import bpy
from mathutils import Matrix

from kit import _obj, apply_modifiers, mat, block, cut, cyl, hole_through, join, label, pin, prism, rail, ring, screw, slots, tube, begin
from parts import MAKER, SLOT_ATTS, grip_parts, muzzle_parts, optic_reddot, optic_scope, stock_parts

BORE = 0.035          # bore height
DRUM = (0.115, -0.128)  # drum centre (y, z); the drum's axis runs along X
DR = 0.080            # drum radius
DT = 0.034            # drum half thickness
STROKE = 0.08         # pump stroke


# ------------------------------------------------------------------------------------ local helpers

def section(name, pts, y0, y1, material, bevel=0.0008, segs=2):
    """Extrude a cross-section [(x, z), ...] along Y from y0 to y1."""
    bm = bmesh.new()
    face = bm.faces.new([bm.verts.new((x, y0, z)) for x, z in pts])
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, y1 - y0, 0), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, material, bevel, segs)


def spin_y(obj, deg, cx=0.0, cz=BORE):
    """Rotate a mesh about the line parallel to Y through (cx, cz), e.g. around the bore."""
    m = Matrix.Translation((cx, 0, cz)) @ Matrix.Rotation(math.radians(deg), 4, "Y") @ Matrix.Translation((-cx, 0, -cz))
    obj.data.transform(m)
    return obj


def on_drum(r, th, x):
    """A point on a drum face: radius r at angle th (0 = up, 90 = toward the muzzle)."""
    t = math.radians(th)
    return (x, DRUM[0] + r * math.sin(t), DRUM[1] + r * math.cos(t))


def radial(name, r, th, x, s, material, bevel=0.0004):
    """A block on a drum face whose Z size runs outward along the radius at angle th."""
    return block(name, on_drum(r, th, x), s, material, bevel=bevel, rot=-th)


def shell(p0, d, hull="red", length=0.070, segs=16):
    """A 12 gauge shell from its brass head at p0 along unit vector d."""
    p0 = tuple(p0)

    def at(t):
        return tuple(p0[k] + d[k] * t for k in range(3))
    return [cyl("rim", at(-0.0002), at(0.0015), 0.0112, "brass", segs=segs, bevel=0.0002, bsegs=1),
            cyl("head", at(0.0015), at(0.014), 0.0104, "brass", segs=segs, bevel=0.0002, bsegs=1),
            cyl("primer", at(-0.0005), at(0.0), 0.0026, "bright", segs=10, bevel=0),
            cyl("hull", at(0.014), at(length - 0.004), 0.0101, hull, segs=segs, bevel=0.0002, bsegs=1),
            cyl("crimp", at(length - 0.004), at(length), 0.0101, hull, r1=0.0084, segs=segs, bevel=0),
            cyl("star", at(length - 0.0002), at(length + 0.0003), 0.004, "black", r1=0.0025, segs=10, bevel=0)]


def grid_dimples(p0, p1, half, nu, nv, x, side, r=0.0011, depth=0.002):
    """Stippling on a side face at x, laid out along the slanted axis p0 -> p1 (y, z)."""
    dy, dz = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(dy, dz)
    py, pz = -dz / n, dy / n
    out = []
    for i in range(nu):
        t = (i + 0.5) / nu
        for j in range(nv):
            s = -half + 2 * half * (j + (0.5 if i % 2 else 0.25)) / nv
            y = p0[0] + dy * t + py * s
            z = p0[1] + dz * t + pz * s
            out.append(cyl("st", (x - side * depth, y, z), (x + side * depth, y, z), r, "steel", segs=8, bevel=0))
    return out


def fuse(objs, name):
    """Bevel each piece with its own settings, then join them; the join carries no further bevel (kit's
    finish would otherwise bevel the whole group, labels and screws included, with the first piece's width)."""
    objs = [o for o in objs if o is not None]
    for o in objs:
        apply_modifiers(o)
    o = join(objs, name)
    o.name = name
    o["bevel"] = 0.0
    return o


named = fuse


def lscrew(at, axis="x", r=0.0022, material="steel"):
    """kit.screw with a single bevel segment."""
    return light(screw(at, axis, r, material))


def flat(o):
    """Flat shading and no bevel: for thin stippled inserts, which stay crisp that way."""
    for p in o.data.polygons:
        p.use_smooth = False
    o["bevel"] = 0.0
    return o


def prebevel(o):
    """Bevel now, so cuts made afterwards (stippling, small grooves) stay crisp and cheap."""
    apply_modifiers(o)
    o["bevel"] = 0.0
    return o


def light(o, segs=1, bevel=None):
    """Fewer bevel segments (or none) for a part with many round edges."""
    o["segs"] = segs
    if bevel is not None:
        o["bevel"] = bevel
    return o


def mark(text, at, size, material, side=-1, depth=0.0003):
    """kit.label with a coarser curve resolution: raised lettering at a fraction of the triangles."""
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


def arc_slot(r, half_w, th0, th1, x0, x1, n=24):
    """Cutter: an annular slot with rounded ends on a drum face, radius r, width 2*half_w, th0..th1 degrees."""
    pts = []
    for k in range(n + 1):
        th = th0 + (th1 - th0) * k / n
        pts.append(on_drum(r + half_w, th, 0)[1:])
    t1 = math.radians(th1)
    for k in range(1, 8):
        a = t1 + math.pi * k / 8
        pts.append((DRUM[0] + r * math.sin(t1) + half_w * math.sin(a), DRUM[1] + r * math.cos(t1) + half_w * math.cos(a)))
    for k in range(n + 1):
        th = th1 - (th1 - th0) * k / n
        pts.append(on_drum(r - half_w, th, 0)[1:])
    t0 = math.radians(th0)
    for k in range(1, 8):
        a = t0 + math.pi + math.pi * k / 8
        pts.append((DRUM[0] + r * math.sin(t0) + half_w * math.sin(a), DRUM[1] + r * math.cos(t0) + half_w * math.cos(a)))
    return prism("arc", pts, x1 - x0, "steel", x=(x0 + x1) / 2, bevel=0)


# ------------------------------------------------------------------------------------------- build

def build():
    """Breacher: pump 12 gauge, drum fed, heat shield, side saddle, breaching muzzle."""
    g = begin("shotgun", {
        "pump": ((0, 0.30, 0.012), None),
        "bolt": ((0, 0.07, BORE), None),
        "lifter": ((0, 0.032, 0.001), None),
        "trigger": ((0, 0.008, -0.036), None),
        "mag": ((0, DRUM[0], -0.04), None),
        "key": ((-0.0385, DRUM[0], DRUM[1]), "mag"),
    })

    # ---- upper receiver: chamfered box, big framed ejection port on the left, feed opening below.
    rec = section("receiver", [(-0.018, -0.005), (0.018, -0.005), (0.018, 0.052), (0.013, 0.060), (-0.013, 0.060), (-0.018, 0.052)],
                  -0.115, 0.130, "black", bevel=0.0009)
    # Overlapping cutters go in separate cut() calls: one joined cutter that overlaps itself confuses the
    # exact boolean (it can drop the cut or the whole target).
    rec = cut(rec, block("recess", (-0.0185, 0.069, 0.025), (0.004, 0.096, 0.054), "steel", bevel=0))
    rec = cut(rec, block("port", (-0.006, 0.069, 0.0245), (0.038, 0.087, 0.049), "steel", bevel=0))
    rec = cut(rec, block("feed", (0, 0.105, -0.002), (0.022, 0.05, 0.012), "steel", bevel=0))
    cuts = [block("bar", (s * 0.0135, 0.125, 0.0135), (0.004, 0.02, 0.008), "steel", bevel=0) for s in (-1, 1)]
    cuts += [block("panel", (0.0185, -0.05, 0.026), (0.003, 0.095, 0.036), "steel", bevel=0)]
    cuts += slots("vent", -0.10, -0.02, 9, 0.054, 0.064, -0.02, -0.0145, angle=0)
    cuts += slots("vent", -0.10, -0.02, 9, 0.054, 0.064, 0.0145, 0.02, angle=0)
    rec = cut(rec, *cuts)
    top_rail = rail("rail", -0.105, 0.112, 0.060, "black")
    rail_screws = [lscrew((0, y, 0.0645), "z", 0.0021) for y in (-0.0615, 0.0085, 0.0685)]
    deflector = block("deflector", (-0.0195, 0.1205, 0.034), (0.004, 0.009, 0.03), "steel", bevel=0.0008, taper=(0.6, 1.0))
    endplate = block("endplate", (0, -0.1175, 0.0115), (0.034, 0.006, 0.078), "steel", bevel=0.001)
    stub = cyl("stub", (0, -0.12, 0.03), (0, -0.128, 0.03), 0.008, "steel", segs=20)
    collar = ring("collar", (0, 0.1325, BORE), (0, 1, 0), 0.0165, 0.0117, 0.005, "steel", segs=32)
    chamber = ring("chamber", (0, 0.1135, BORE), (0, 1, 0), 0.0128, 0.0094, 0.004, "bright", segs=28)
    rpins = [pin((0, y, z), "x", 0.0016, 0.0375) for y, z in ((-0.095, 0.03), (-0.01, 0.03))]
    right_marks = [mark(MAKER, (0.0175, -0.05, 0.034), 0.0036, "bright", side=1),
                   mark("BREACHER  12 GA  76 MM", (0.0175, -0.05, 0.019), 0.0028, "bright", side=1)]
    g.add(fuse([rec, top_rail, *rail_screws, deflector, endplate, stub, collar, chamber, *rpins, *right_marks], "receiver"), "root")

    # ---- lower: trigger housing, flared mag well, trigger guard, grip with stippling.
    lower = prism("lower", [(-0.115, -0.005), (0.052, -0.005), (0.052, -0.036), (-0.104, -0.036), (-0.115, -0.026)], 0.034, "black", bevel=0.0009)
    lower = cut(lower, *slots("ser", -0.012, 0.03, 6, -0.037, -0.033, -0.02, 0.02))
    well = prism("well", [(0.050, -0.005), (0.162, -0.005), (0.162, -0.012), (0.158, -0.040), (0.054, -0.040), (0.050, -0.036)],
                 0.040, "black", bevel=0.0012, segs=3)
    well = cut(well, block("mouth", (0, 0.115, -0.025), (0.027, 0.062, 0.05), "steel", bevel=0),
               *slots("rib", 0.135, 0.156, 4, -0.034, -0.012, -0.022, -0.0185), *slots("rib", 0.135, 0.156, 4, -0.034, -0.012, 0.0185, 0.022))
    guard = prism("guard", [(-0.018, -0.035), (0.052, -0.035), (0.055, -0.044), (0.051, -0.062), (0.041, -0.068), (-0.004, -0.068),
                            (-0.018, -0.060), (-0.026, -0.045)], 0.012, "black", bevel=0.0012, segs=3)
    guard = cut(guard, prism("gh", [(-0.012, -0.039), (0.046, -0.039), (0.048, -0.046), (0.045, -0.058), (0.038, -0.062), (-0.002, -0.062),
                                    (-0.012, -0.056), (-0.016, -0.046)], 0.03, "steel", bevel=0))
    grip = prism("grip", [(-0.022, -0.036), (-0.080, -0.036), (-0.092, -0.060), (-0.112, -0.130), (-0.114, -0.140), (-0.106, -0.148),
                          (-0.074, -0.148), (-0.067, -0.140), (-0.053, -0.100), (-0.047, -0.093), (-0.049, -0.084), (-0.041, -0.074),
                          (-0.043, -0.066), (-0.033, -0.057), (-0.025, -0.046)], 0.030, "black", bevel=0.0016, segs=2)
    inserts = []
    for side in (-1, 1):
        x = side * 0.0152
        ins = prism("insert", [(-0.058, -0.046), (-0.082, -0.046), (-0.104, -0.128), (-0.100, -0.138), (-0.080, -0.138), (-0.066, -0.096),
                               (-0.050, -0.062)], 0.0009, "rubber", x=x, bevel=0)
        ins = cut(ins, *grid_dimples((-0.066, -0.05), (-0.089, -0.136), 0.0115, 13, 5, x, side, r=0.00105, depth=0.0012))
        inserts.append(flat(ins))
    cap = prism("cap", [(-0.073, -0.147), (-0.107, -0.147), (-0.111, -0.152), (-0.106, -0.157), (-0.076, -0.157), (-0.071, -0.152)],
                0.031, "steel", bevel=0.001)
    cap = cut(cap, hole_through("lanyard", (0, -0.1, -0.152), 0.0025, "x"))
    safety = cyl("safety", (-0.0185, -0.006, -0.028), (0.0185, -0.006, -0.028), 0.0036, "steel", segs=18)
    safety_ring = cyl("safecap", (-0.0185, -0.006, -0.028), (-0.0191, -0.006, -0.028), 0.0027, "red", segs=16, bevel=0.0002)
    release = cyl("release", (-0.020, 0.064, -0.026), (-0.0235, 0.064, -0.026), 0.0042, "red", segs=18)
    release_guard = prism("rguard", [(0.056, -0.02), (0.072, -0.02), (0.072, -0.033), (0.056, -0.033)], 0.002, "black", x=-0.021, bevel=0.0004)
    release_guard = cut(release_guard, hole_through("rg", (-0.021, 0.064, -0.026), 0.0047, "x", 0.01))
    bolt_rel = prism("boltrel", [(0.030, -0.012), (0.046, -0.012), (0.046, -0.018), (0.032, -0.020)], 0.003, "steel", x=-0.0185, bevel=0.0004)
    lpins = [pin((0, y, -0.02), "x", 0.0015, 0.0355) for y in (-0.06, 0.022)]
    marks = [mark("BREACHER", (-0.0202, 0.112, -0.017), 0.0062, "bright"),
             mark("12 GA  20 RD DRUM", (-0.0202, 0.112, -0.029), 0.0034, "bright")]
    g.add(fuse([lower, well, guard, grip, *inserts, cap, safety, safety_ring, release, release_guard, bolt_rel, *lpins, *marks], "lower"), "root")

    # ---- side saddle: a plate on the left of the receiver holding four shells, brass down.
    plate = block("saddle", (-0.0203, -0.061, 0.008), (0.0046, 0.094, 0.084), "black", bevel=0.0015, segs=3)
    plate = cut(plate, *[block("sl", (-0.0225, -0.061, z), (0.002, 0.08, 0.004), "steel", bevel=0) for z in (0.044, -0.028)])
    sad = [plate, lscrew((-0.0228, -0.105, 0.008), "-x", 0.0022), lscrew((-0.0228, -0.017, 0.008), "-x", 0.0022)]
    for i in range(4):
        y = -0.096 + i * 0.023
        sad += shell((-0.0334, y, -0.035), (0, 0, 1))
        for z in (0.026, -0.012):
            sad.append(light(ring("loop", (-0.0334, y, z), (0, 0, 1), 0.0119, 0.0100, 0.009, "rubber", segs=20)))
            sad.append(block("web", (-0.0245, y, z), (0.005, 0.012, 0.009), "rubber", bevel=0.0005))
    g.add(fuse(sad, "saddle"), "root")

    # ---- barrel, chamber, heat shield with rows of slots, guide rod and front clamp.
    g.add(tube("barrel", (0, 0.112, BORE), (0, 0.535, BORE), 0.0118, 0.0094, "steel", segs=36), "root")
    shield = light(tube("shield", (0, 0.142, BORE), (0, 0.495, BORE), 0.0176, 0.0158, "black", segs=40))
    sc = [block("low", (0, 0.32, BORE - 0.023), (0.05, 0.4, 0.04), "steel", bevel=0)]
    for k, phi in enumerate((-64, -22, 22, 64)):
        off = 0.0145 if k % 2 else 0.0
        for i in range(11 if k % 2 == 0 else 10):
            y = 0.168 + i * 0.029 + off
            sc.append(spin_y(block("slot", (0, y, BORE + 0.0167), (0.0055, 0.019, 0.008), "steel", bevel=0), phi))
    shield = cut(shield, *sc)
    rb = ring("band", (0, 0.147, BORE), (0, 1, 0), 0.0196, 0.0157, 0.009, "steel", segs=40)
    rb = cut(rb, block("low", (0, 0.147, BORE - 0.023), (0.05, 0.03, 0.04), "steel", bevel=0))
    bands = [rb, lscrew((-0.0192, 0.147, BORE + 0.006), "-x", 0.0019), lscrew((0.0192, 0.147, BORE + 0.006), "x", 0.0019)]
    y = 0.487
    bands += [ring("band", (0, y, BORE), (0, 1, 0), 0.0196, 0.0117, 0.009, "steel", segs=40),
              block("lug", (0, y, BORE - 0.018), (0.016, 0.009, 0.01), "steel", bevel=0.0008), lscrew((-0.0085, y, BORE - 0.018), "-x", 0.0019)]
    rod = cyl("rod", (0, 0.125, 0.0085), (0, 0.462, 0.0085), 0.0045, "bright", segs=18)
    clamp = section("clamp", [(-0.013, 0.003), (0.013, 0.003), (0.013, 0.028), (0.011, 0.034), (-0.011, 0.034), (-0.013, 0.028)],
                    0.450, 0.464, "steel", bevel=0.0012)
    clamp = cut(clamp, hole_through("cb", (0, 0.457, BORE), 0.0116, "y", 0.03, segs=32), hole_through("cr", (0, 0.457, 0.0085), 0.0044, "y", 0.03))
    clamp = cut(clamp, block("slit", (0, 0.457, 0.0035), (0.0018, 0.03, 0.004), "steel", bevel=0))
    g.add(fuse([shield, *bands, rod, clamp, lscrew((-0.0135, 0.457, 0.016), "-x", 0.0022), lscrew((0.0135, 0.457, 0.016), "x", 0.0022)], "front"), "root")

    # ---- pump: ribbed forend riding the guide rod, twin action bars back into the receiver.
    def fsec(d):
        a = 0.024 + d
        z0 = -0.012 - d
        return [(-a, 0.024), (-a, z0 + 0.012), (-a + 0.004, z0 + 0.004), (-a + 0.012, z0), (a - 0.012, z0), (a - 0.004, z0 + 0.004),
                (a, z0 + 0.012), (a, 0.024), (a - 0.006, 0.031), (0.0128, 0.031), (0.009, 0.0247), (0.0, 0.0225), (-0.009, 0.0247),
                (-0.0128, 0.031), (-a + 0.006, 0.031)]
    y0, y1 = 0.215, 0.395
    fore = section("forend", fsec(0.0), y0, y1, "grey", bevel=0.0012, segs=2)
    ribs = [section("lip", fsec(0.0045), y0, y0 + 0.011, "grey", bevel=0.0015, segs=3),
            section("lip", fsec(0.0045), y1 - 0.011, y1, "grey", bevel=0.0015, segs=3)]
    for i in range(12):
        yc = y0 + 0.021 + i * 0.0125
        ribs.append(section("rib", fsec(0.0017), yc - 0.0028, yc + 0.0028, "grey", bevel=0.0007))
    bars = [block("abar", (s * 0.0135, 0.2075, 0.0135), (0.0025, 0.185, 0.0068), "steel", bevel=0.0004) for s in (-1, 1)]
    bar_pins = [pin((0, 0.221, 0.006), "x", 0.0016, 0.058), pin((0, 0.389, 0.006), "x", 0.0016, 0.058)]
    nut = ring("nut", (0, 0.398, 0.0085), (0, 1, 0), 0.0085, 0.0046, 0.006, "steel", segs=6)
    under_rail = rail("urail", 0.29, 0.36, -0.0125, "black", flip=True, width=0.02)
    stripe = block("stripe", (-0.0287, 0.389, 0.006), (0.0012, 0.004, 0.024), "red", bevel=0.0002)
    g.add(fuse([fore, *ribs, *bars, *bar_pins, nut, under_rail, stripe], "pump"), "pump")
    handstop = prism("hs", [(0.366, -0.0145), (0.392, -0.0145), (0.392, -0.022), (0.386, -0.034), (0.381, -0.034)], 0.02, "black", bevel=0.0015, segs=3)
    g.add(named([handstop], "att.grip.standard"), "pump")

    # ---- bolt, seen through the port; it rides back with the action bars.
    bolt = block("bolt", (0, 0.0695, BORE + 0.001), (0.024, 0.083, 0.024), "steel", bevel=0.001)
    bolt = cut(bolt, *[block("gr", (-0.012, 0.066, z), (0.003, 0.056, 0.0022), "steel", bevel=0) for z in (0.03, 0.042)],
               block("face", (0, 0.111, BORE), (0.016, 0.004, 0.016), "steel", bevel=0))
    extractor = block("extractor", (-0.0123, 0.1, BORE + 0.001), (0.0026, 0.02, 0.0058), "bright", bevel=0.0003)
    bolt_parts = [bolt, extractor, pin((-0.0122, 0.045, 0.036), "x", 0.002, 0.002, "bright"),
                  block("lock", (-0.0124, 0.07, 0.036), (0.002, 0.012, 0.007), "black", bevel=0.0003)]
    g.add(fuse(bolt_parts, "bolt"), "bolt")

    # ---- shell lifter with the next round on it.
    tray = [block("tray", (0, 0.069, 0.002), (0.022, 0.076, 0.003), "black", bevel=0.0004),
            block("wall", (-0.0118, 0.069, 0.006), (0.0016, 0.07, 0.009), "black", bevel=0.0003),
            block("wall", (0.0118, 0.069, 0.006), (0.0016, 0.07, 0.009), "black", bevel=0.0003),
            cyl("boss", (-0.011, 0.032, 0.001), (0.011, 0.032, 0.001), 0.0035, "bright", segs=14)]
    tray[1] = cut(tray[1], *[hole_through("lh", (-0.0118, 0.05 + i * 0.018, 0.0065), 0.0022, "x", 0.01) for i in range(3)])
    g.add(fuse(tray + shell((0, 0.036, 0.0136), (0, 1, 0)), "lifter"), "lifter")

    # ---- trigger.
    trig = prism("trigger", [(0.004, -0.036), (0.011, -0.036), (0.012, -0.044), (0.016, -0.055), (0.015, -0.0585), (0.011, -0.0575),
                             (0.006, -0.047)], 0.006, "bright", bevel=0.0004)
    g.add(trig, "trigger")

    # ---- drum magazine: ribbed polymer drum, steel bands, winding key, witness window of red shells.
    cy, cz = DRUM
    body = cyl("drum", (-DT, cy, cz), (DT, cy, cz), DR, "grey", segs=64, bevel=0.0015, bsegs=2)
    th0, th1, rw = 98.0, 212.0, 0.064
    body = cut(body, arc_slot(rw, 0.00625, th0, th1, -DT - 0.01, -DT + 0.006))
    dparts = [body]
    for th in range(int(th0) - 4, int(th1) + 8, 16):
        dparts.append(cyl("rnd", on_drum(rw, th, -DT + 0.004), on_drum(rw, th, -DT + 0.020), 0.0096, "red", segs=16, bevel=0.0002, bsegs=1))
        dparts.append(cyl("crimp", on_drum(rw, th, -DT + 0.0045), on_drum(rw, th, -DT + 0.004), 0.0045, "black", r1=0.0015, segs=10, bevel=0))
    for x in (-0.021, 0.0, 0.021):
        dparts.append(light(ring("rib", (x, cy, cz), (1, 0, 0), DR + 0.0025, DR - 0.004, 0.004, "grey", segs=48)))
    for s in (-1, 1):
        dparts.append(light(ring("band", (s * (DT - 0.0035), cy, cz), (1, 0, 0), DR + 0.0015, DR - 0.006, 0.007, "steel", segs=48)))
        fx = s * DT
        dparts.append(cyl("hub", (fx, cy, cz), (fx + s * 0.0045, cy, cz), 0.023, "black", r1=0.020, segs=40))
        for k in range(8):
            th = 22.5 + 45 * k
            dparts.append(radial("dr", 0.039, th, fx + s * 0.0012, (0.0024, 0.0042, 0.026), "grey", bevel=0.0005))
        for th in ((-140, -90, -40, 35, 75) if s < 0 else (-135, -45, 45, 135)):
            dparts.append(screw(on_drum(0.0735, th, fx + s * 0.0006), "x" if s > 0 else "-x", 0.0022))
    dparts.append(ring("bezel", (-DT - 0.0006, cy, cz), (1, 0, 0), 0.0255, 0.0232, 0.0012, "steel", segs=40))
    neck = block("neck", (0, cy, -0.026), (0.025, 0.058, 0.044), "black", bevel=0.0009)
    neck = cut(neck, *slots("nr", 0.09, 0.14, 6, -0.047, -0.041, -0.014, -0.011), *slots("nr", 0.09, 0.14, 6, -0.047, -0.041, 0.011, 0.014))
    dparts += [neck, block("latch", (0, cy - 0.031, -0.03), (0.012, 0.004, 0.01), "steel", bevel=0.0004),
               block("foot", (0, cy, cz - DR - 0.001), (0.05, 0.05, 0.004), "rubber", bevel=0.0015)]
    dparts += [mark("BREACHER", (-DT - 0.0003, cy, cz + 0.064), 0.0072, "bright"),
               mark("20 RD", (-DT - 0.0003, cy - 0.056, cz + 0.008), 0.0052, "bright"),
               mark("12 GA", (-DT - 0.0003, cy + 0.060, cz + 0.033), 0.0045, "bright"),
               mark("WIND", (-DT - 0.0003, cy, cz - 0.03), 0.0035, "bright"),
               mark("BREACHER", (DT + 0.0003, cy, cz + 0.064), 0.0072, "bright", side=1)]
    g.add(fuse(dparts, "drum"), "mag")
    kx = -DT - 0.0045
    key = [cyl("shaft", (kx, cy, cz), (kx - 0.004, cy, cz), 0.0055, "steel", segs=18),
           block("wing", (kx - 0.006, cy, cz), (0.004, 0.011, 0.034), "steel", bevel=0.0006)]
    for dz in (-0.017, 0.017):
        lobe = cyl("lobe", (kx - 0.004, cy, cz + dz), (kx - 0.008, cy, cz + dz), 0.0078, "steel", segs=24)
        key.append(cut(lobe, hole_through("lh", (kx - 0.006, cy, cz + dz), 0.0032, "x", 0.02)))
    g.add(fuse(key, "key"), "key")

    # ---- gunsmith: flip-up irons, breaching muzzle and fixed stock are the bare gun's own parts.
    rear = [block("rbase", (0, -0.08, 0.0716), (0.024, 0.026, 0.008), "black", bevel=0.001),
            block("post", (0, -0.08, 0.0785), (0.006, 0.006, 0.008), "black", bevel=0.0005),
            ring("aperture", (0, -0.08, 0.087), (0, 1, 0), 0.0062, 0.003, 0.004, "steel", segs=24),
            cyl("windage", (-0.012, -0.072, 0.072), (-0.0158, -0.072, 0.072), 0.003, "steel", segs=16),
            lscrew((0.0125, -0.08, 0.071), "x", 0.0018)]
    for s in (-1, 1):
        ear = prism("ear", [(-0.093, 0.075), (-0.067, 0.075), (-0.071, 0.095), (-0.085, 0.097)], 0.0035, "black", x=s * 0.0098, bevel=0.0006)
        rear.append(cut(ear, hole_through("eh", (s * 0.0098, -0.077, 0.081), 0.0022, "x", 0.01)))
    front = [block("fbase", (0, 0.487, 0.0585), (0.013, 0.016, 0.009), "black", bevel=0.001),
             block("blade", (0, 0.487, 0.0725), (0.0026, 0.0045, 0.026), "black", bevel=0.0003),
             cyl("fiber", (0, 0.4845, 0.0845), (0, 0.4895, 0.0845), 0.0012, "reticle", segs=10, bevel=0)]
    for s in (-1, 1):
        front.append(prism("fear", [(0.478, 0.062), (0.496, 0.062), (0.494, 0.088), (0.482, 0.09)], 0.0025, "black", x=s * 0.0068, bevel=0.0004))
    g.add(named(rear + front, "att.optic.irons"), "root")

    br = tube("brm", (0, 0.507, BORE), (0, 0.570, BORE), 0.0174, 0.0121, "black", segs=36)
    bc = [spin_y(block("tooth", (0, 0.568, BORE + 0.0172), (0.0095, 0.012, 0.014), "steel", bevel=0), 30 + 60 * k) for k in range(6)]
    ports = [hole_through("vp", (0, 0.546, BORE), 0.0035, "x", 0.05), hole_through("vp", (0, 0.546, BORE), 0.0035, "z", 0.05)]
    for a in (45, -45):
        t = math.radians(a)
        dx, dz = math.sin(t) * 0.03, math.cos(t) * 0.03
        ports.append(cyl("vp", (-dx, 0.556, BORE - dz), (dx, 0.556, BORE + dz), 0.003, "steel", segs=16, bevel=0))
    bc += [ring("kn", (0, 0.512 + i * 0.0035, BORE), (0, 1, 0), 0.019, 0.0168, 0.0015, "steel", segs=36) for i in range(3)]
    br = cut(br, *bc)
    for p in ports:
        br = cut(br, p)
    blug = block("blug", (0, 0.516, BORE - 0.0185), (0.013, 0.016, 0.008), "black", bevel=0.0008)
    blug = cut(blug, block("bslit", (0, 0.516, BORE - 0.019), (0.0018, 0.03, 0.012), "steel", bevel=0))
    g.add(named([br, blug, lscrew((-0.0068, 0.516, BORE - 0.0185), "-x", 0.0017), mark("BREACH", (-0.0176, 0.528, BORE), 0.003, "bright")],
                "att.muzzle.bare"), "root")

    stock = prism("stock", [(-0.118, 0.058), (-0.20, 0.056), (-0.355, 0.052), (-0.362, 0.050), (-0.362, -0.098), (-0.350, -0.103),
                            (-0.300, -0.088), (-0.200, -0.052), (-0.145, -0.036), (-0.118, -0.034)], 0.038, "grey", bevel=0.0022, segs=2)
    sk = [prism("skel", [(-0.165, 0.030), (-0.315, 0.026), (-0.325, 0.016), (-0.325, -0.050), (-0.312, -0.062), (-0.21, -0.030),
                         (-0.17, -0.016), (-0.158, -0.004)], 0.06, "steel", bevel=0)]
    stock = cut(stock, sk.pop(0), cyl("sling", (-0.03, -0.345, -0.035), (0.03, -0.345, -0.035), 0.0035, "steel", segs=14, bevel=0))
    for side in (-1, 1):
        x = side * 0.0194
        ins = prism("sinsert", [(-0.21, -0.033), (-0.295, -0.062), (-0.295, -0.083), (-0.21, -0.0505)], 0.0009, "rubber", x=x, bevel=0)
        sk.append(flat(cut(ins, *grid_dimples((-0.213, -0.042), (-0.292, -0.0725), 0.0058, 15, 3, x, side, r=0.001, depth=0.0012))))
    comb = block("comb", (0, -0.25, 0.0565), (0.03, 0.12, 0.007), "rubber", bevel=0.002, segs=3)
    qd = cyl("qd", (-0.0188, -0.343, 0.01), (-0.0215, -0.343, 0.01), 0.0068, "steel", segs=20)
    qd = cut(qd, hole_through("qh", (-0.02, -0.343, 0.01), 0.0034, "x", 0.01))
    pad = prism("pad", [(-0.362, 0.051), (-0.392, 0.052), (-0.397, 0.046), (-0.397, -0.096), (-0.392, -0.105), (-0.362, -0.100)],
                0.042, "rubber", bevel=0.003, segs=2)
    pad = cut(pad, *[block("pg", (s * 0.021, -0.38, z), (0.004, 0.022, 0.0024), "steel", bevel=0)
                     for s in (-1, 1) for z in [0.036 - 0.0165 * i for i in range(8)]])
    spacer = prism("spacer", [(-0.3615, 0.0505), (-0.365, 0.0508), (-0.365, -0.1005), (-0.3615, -0.099)], 0.040, "black", bevel=0.0006)
    smarks = [mark(MAKER, (-0.0192, -0.245, 0.0415), 0.0042, "bright"), mark("RR", (-0.0192, -0.137, 0.012), 0.008, "red")]
    sscrews = [lscrew((-0.0195, -0.13, 0.045), "-x", 0.0022), lscrew((-0.0195, -0.13, -0.022), "-x", 0.0022)]
    g.add(named([stock, *sk, comb, qd, pad, spacer, *smarks, *sscrews], "att.stock.standard"), "root")

    # Gunsmith parts on the sockets: optics on the rail, muzzle devices on the barrel, foregrips under
    # the pump (they ride it), light/heavy stocks on the receiver's stub.
    top = (0, -0.01, 0.0676)
    muzzle = (0, 0.535, BORE)
    under = (0, 0.325, -0.0201)
    stock_at = (0, -0.12, 0.03)
    optic_reddot(g, top)
    optic_scope(g, top)
    muzzle_parts(g, muzzle, r=0.0118)
    grip_parts(g, under, bone="pump")
    stock_parts(g, stock_at)
    g.socket("optic", top)
    g.socket("muzzle", muzzle)
    g.socket("under", under, "pump")
    g.socket("stock", stock_at)
    g.socket("eject", (-0.022, 0.07, 0.036))

    # ---- clips.
    s = STROKE
    g.clip("idle", 2.0, {"root": [(0, (0, 0, 0), (0, 0, 0)), (1.0, (0, 0, 0.0015), (0.35, 0, 0.2)), (2.0, (0, 0, 0), (0, 0, 0))]})
    g.clip("fire", 0.65, {
        "trigger": [(0, (0, 0, 0), (0, 0, 0)), (0.02, (0, 0, 0), (-13, 0, 0)), (0.12, (0, 0, 0), (0, 0, 0))],
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.035, (0, -0.042, 0.013), (11, 0, 2)), (0.12, (0, -0.014, 0.005), (4, 0, 0.6)),
                 (0.22, (0, 0, 0), (0, 0, 0)), (0.31, (0.002, -0.005, -0.004), (-1.5, -3, 0)), (0.45, (0, 0.003, 0), (0.6, 1, 0)),
                 (0.62, (0, 0, 0), (0, 0, 0))],
        "pump": [(0, (0, 0, 0), (0, 0, 0)), (0.22, (0, 0, 0), (0, 0, 0)), (0.33, (0, -s, 0), (0, 0, 0)), (0.37, (0, -s, 0), (0, 0, 0)),
                 (0.49, (0, 0, 0), (0, 0, 0))],
        "bolt": [(0, (0, 0, 0), (0, 0, 0)), (0.235, (0, 0, 0), (0, 0, 0)), (0.335, (0, -s, 0), (0, 0, 0)), (0.375, (0, -s, 0), (0, 0, 0)),
                 (0.49, (0, 0, 0), (0, 0, 0))],
        "lifter": [(0, (0, 0, 0), (0, 0, 0)), (0.30, (0, 0, 0), (0, 0, 0)), (0.34, (0, 0, 0), (18, 0, 0)), (0.375, (0, 0, 0), (18, 0, 0)),
                   (0.405, (0, 0, 0), (0, 0, 0))],
    })
    g.clip("reload", 2.3, {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.25, (0.01, 0, 0.03), (12, 25, 0)), (1.25, (0.01, 0, 0.03), (14, 27, 0)),
                 (1.32, (0.01, 0.0, 0.037), (17, 27, 0)), (1.6, (0.006, 0, 0.03), (12, 22, 0)), (1.72, (0, 0, 0.02), (7, 6, 0)),
                 (1.85, (0, -0.004, 0.016), (5, -4, 0)), (2.05, (0, 0, 0.005), (2, 0, 0)), (2.3, (0, 0, 0), (0, 0, 0))],
        "mag": [(0, (0, 0, 0), (0, 0, 0)), (0.35, (0, 0, -0.012), (0, 0, 0)), (0.6, (0, 0.02, -0.30), (-30, 0, 0)),
                (0.601, (0, 0.06, -0.21), (12, 0, 0)), (1.05, (0, 0.025, -0.05), (10, 0, 0)), (1.22, (0, 0.004, -0.012), (4, 0, 0)),
                (1.3, (0, 0, 0), (0, 0, 0))],
        "key": [(0, (0, 0, 0), (0, 0, 0)), (1.34, (0, 0, 0), (0, 0, 0)), (1.44, (0, 0, 0), (-120, 0, 0)), (1.54, (0, 0, 0), (-240, 0, 0)),
                (1.64, (0, 0, 0), (-360, 0, 0)), (1.66, (0, 0, 0), (0, 0, 0))],
        "pump": [(0, (0, 0, 0), (0, 0, 0)), (1.72, (0, 0, 0), (0, 0, 0)), (1.84, (0, -s, 0), (0, 0, 0)), (1.9, (0, -s, 0), (0, 0, 0)),
                 (2.02, (0, 0, 0), (0, 0, 0))],
        "bolt": [(0, (0, 0, 0), (0, 0, 0)), (1.73, (0, 0, 0), (0, 0, 0)), (1.845, (0, -s, 0), (0, 0, 0)), (1.9, (0, -s, 0), (0, 0, 0)),
                 (2.02, (0, 0, 0), (0, 0, 0))],
        "lifter": [(0, (0, 0, 0), (0, 0, 0)), (1.8, (0, 0, 0), (0, 0, 0)), (1.84, (0, 0, 0), (18, 0, 0)), (1.9, (0, 0, 0), (18, 0, 0)),
                   (1.93, (0, 0, 0), (0, 0, 0))],
    })
    g.clip("draw", 0.5, {"root": [(0, (0, -0.05, -0.14), (-50, 0, 12)), (0.35, (0, 0.004, 0.004), (4, 0, 0)), (0.5, (0, 0, 0), (0, 0, 0))]})
    g.clip("inspect", 3.2, {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.55, (-0.02, 0.03, 0.035), (12, -30, 24)), (1.25, (-0.02, 0.03, 0.035), (14, -34, 28)),
                 (1.75, (0.02, 0.01, 0.03), (6, 32, -22)), (2.45, (0.02, 0.01, 0.03), (8, 35, -25)), (2.95, (0, 0, 0), (0, 0, 0))],
        "pump": [(0, (0, 0, 0), (0, 0, 0)), (0.6, (0, 0, 0), (0, 0, 0)), (0.8, (0, -0.05, 0), (0, 0, 0)), (1.1, (0, -0.05, 0), (0, 0, 0)),
                 (1.25, (0, 0, 0), (0, 0, 0))],
        "bolt": [(0, (0, 0, 0), (0, 0, 0)), (0.6, (0, 0, 0), (0, 0, 0)), (0.8, (0, -0.05, 0), (0, 0, 0)), (1.1, (0, -0.05, 0), (0, 0, 0)),
                 (1.25, (0, 0, 0), (0, 0, 0))],
        "key": [(0, (0, 0, 0), (0, 0, 0)), (1.9, (0, 0, 0), (0, 0, 0)), (2.05, (0, 0, 0), (-120, 0, 0)), (2.2, (0, 0, 0), (-240, 0, 0)),
                (2.35, (0, 0, 0), (-360, 0, 0)), (2.37, (0, 0, 0), (0, 0, 0))],
    })
    return g


BARE = ["att.optic.irons", "att.muzzle.bare", "att.grip.standard", "att.stock.standard"]

SPEC = {"build": build, "length": (0.60, 0.75), "tris": (20000, 70000),
        "bones": ["root", "pump", "bolt", "lifter", "trigger", "mag", "key"],
        "sockets": ["muzzle", "eject", "optic", "under", "stock"], "attachments": SLOT_ATTS + BARE,
        "parts": {"mesh.root": "root", "mesh.pump": "pump", "mesh.bolt": "bolt", "mesh.lifter": "lifter", "mesh.trigger": "trigger",
                  "mesh.mag": "mag", "mesh.key": "key"},
        "moves": {"idle": ["root"], "fire": ["root", "pump", "bolt", "lifter", "trigger"], "reload": ["root", "mag", "key", "pump", "bolt"],
                  "draw": ["root"], "inspect": ["root", "pump", "bolt", "key"]},
        "view": {"cam": (-0.9, 0.19, 0.22), "look": (0, 0.21, -0.07), "lens": 40}}
