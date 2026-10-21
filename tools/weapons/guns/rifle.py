"""MA-14 rifle: our take on the MAD.ASA concept. Olive polymer receiver and handguard, black steel
barrel, gas block, rails and buffer tube; a big knurled rotary selector dial and a long side window
onto the bolt carrier on the left; a forward-swept polymer magazine with a brass witness window."""

import math

import bmesh
import bpy
import kit
from mathutils import Matrix, Vector

from kit import _apply, _obj, apply_modifiers, begin, block, cut, cyl, hole_through, mat, pin, plan, prism, ring, slots, tube
from parts import MAKER, SLOT_ATTS, attachments, common_clips, mag_drop

BORE = 0.045          # bore height above the trigger
UP_TOP = 0.062        # top of the upper receiver / handguard, where the rail sits
RAIL_TOP = UP_TOP + 0.0076
HG_Y0, HG_Y1 = 0.134, 0.400   # handguard
MUZZLE_Y = 0.490
DIAL = (-0.046, 0.012)        # selector dial centre (y, z)
TILT = math.radians(8)        # magazine forward sweep
MAG_O = (0.036, 0.022)        # rear-top corner of the magazine (y, z)
MAG_L, MAG_W = 0.188, 0.062   # magazine depth below its lips, and front-to-back size


# ------------------------------------------------------------------------------- local helpers


def join(objs, name):
    """kit.join keeps only the first member's bevel setting, and Gun.finish then bevels the whole joined mesh
    with it (re-bevelling labels, dimples and rail teeth). Bake each member's own bevel first instead."""
    objs = [o for o in objs if o is not None]
    for o in objs:
        if not o.get("bevel", 0.0) and o.name.split(".")[0] != "label":
            for poly in o.data.polygons:  # unbevelled booleaned parts shade cleanly only when flat
                poly.use_smooth = False
        apply_modifiers(o)
        o["bevel"] = 0.0
    return kit.join(objs, name)


def label(text, at, size, material, side=-1, depth=0.0003):
    """kit.label with a coarse curve resolution: same raised lettering at a fraction of the triangles."""
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = depth
    cu.resolution_u = 2
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


def rail(name, y0, y1, z, material="black", x=0.0, flip=False, width=0.021):
    """kit.rail with single-segment bevels on the teeth (the rail is the biggest triangle sink)."""
    s = -1 if flip else 1
    parts = [block(name, (x, (y0 + y1) / 2, z + s * 0.002), (width * 0.8, y1 - y0, 0.004), material, bevel=0.0004)]
    n = int((y1 - y0) / 0.01)
    start = (y0 + y1) / 2 - (n - 1) * 0.005
    for i in range(n):
        parts.append(block(name, (x, start + i * 0.01, z + s * 0.0058), (width, 0.0052, 0.0036), material, bevel=0.0005, segs=1,
                           taper=(0.82, 0.9) if not flip else None))
    return join(parts, name)


def screw(at, axis="x", r=0.0022, material="steel", head=0.0012):
    """kit.screw with fewer segments."""
    sgn = -1 if axis.startswith("-") else 1
    a = {"x": Vector((1, 0, 0)), "y": Vector((0, 1, 0)), "z": Vector((0, 0, 1))}[axis[-1]] * sgn
    at = Vector(at)
    s = cyl("screw", at - a * head / 2, at + a * head / 2, r, material, segs=10, bevel=0.0002, bsegs=1)
    hexa = cyl("hex", at + a * (head / 2 - 0.0006), at + a * (head / 2 + 0.001), r * 0.45, material, segs=6, bevel=0)
    return cut(s, hexa, solver="FLOAT")

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


def xf(obj, m):
    obj.data.transform(m)
    obj.data.update()
    return obj


def rot_y(obj, deg, x=0.0, z=BORE):
    """Spin a part about an axis parallel to Y through (x, z)."""
    c = Vector((x, 0, z))
    return xf(obj, Matrix.Translation(c) @ Matrix.Rotation(math.radians(deg), 4, "Y") @ Matrix.Translation(-c))


def carve(target, *cutters):
    """Boolean difference that tolerates overlapping cutters (self-intersection on)."""
    cutter = kit.join(list(cutters), "_carver") if len(cutters) > 1 else cutters[0]
    mod = target.modifiers.new("carve", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.use_self = True
    mod.object = cutter
    _apply(target, mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def slot_x(name, y0, y1, z, h, x, depth):
    """A round-ended slot cutter facing X (window, M-LOK style)."""
    r = h / 2
    return [block(name, (x, (y0 + y1) / 2, z), (depth, y1 - y0 - h, h), "steel", bevel=0),
            cyl(name, (x - depth / 2, y0 + r, z), (x + depth / 2, y0 + r, z), r, "steel", segs=16, bevel=0),
            cyl(name, (x - depth / 2, y1 - r, z), (x + depth / 2, y1 - r, z), r, "steel", segs=16, bevel=0)]


def slot_z(y, z0, z1, w, x, depth):
    """A round-ended vertical slot cutter facing X."""
    r = w / 2
    return [block("sz", (x, y, (z0 + z1) / 2), (depth, w, z1 - z0 - w), "steel", bevel=0),
            cyl("sz", (x - depth / 2, y, z0 + r), (x + depth / 2, y, z0 + r), r, "steel", segs=12, bevel=0),
            cyl("sz", (x - depth / 2, y, z1 - r), (x + depth / 2, y, z1 - r), r, "steel", segs=12, bevel=0)]


def side_rail(name, y0, y1, side, z):
    """A short Picatinny section on a handguard flank, teeth facing outward."""
    r = rail(name, y0, y1, 0.0, "black")
    return xf(r, Matrix.Translation((side * 0.021, 0, z)) @ Matrix.Rotation(math.radians(90 * side), 4, "Y"))


def magpt(u, d):
    """Point on the magazine: u front-to-back from its rear edge, d down from its lips. The mag leans
    forward by TILT and curves further forward toward the base."""
    c = 0.022 * (max(d, 0.0) / MAG_L) ** 2
    u = u + c
    return (MAG_O[0] + u * math.cos(TILT) + d * math.sin(TILT), MAG_O[1] + u * math.sin(TILT) - d * math.cos(TILT))


def mag_quad(u0, u1, d0, d1):
    return [magpt(u0, d0), magpt(u1, d0), magpt(u1, d1), magpt(u0, d1)]


def stipple(name, rows, x, side, r=0.00095, depth=0.0012):
    """Slanted stippling: rows of (z, y_front, y_back, count) dimples cut into a face at x."""
    out = []
    for j, (z, ya, yb, n) in enumerate(rows):
        for i in range(n):
            f = (i + (0.5 if j % 2 else 0.0)) / n
            if f > 1.0:
                continue
            y = ya + (yb - ya) * f
            out.append(cyl(name, (x - side * depth, y, z), (x + side * depth, y, z), r, "steel", segs=8, bevel=0))
    return out


def grip_rows(n_rows=13):
    rows = []
    for j in range(n_rows):
        z = -0.017 - j * 0.0066
        yf = -0.0155 + 0.29 * z - 0.0055
        yb = -0.072 + 0.21 * min(0.0, z + 0.02) + 0.0065
        rows.append((z, yf, yb, 7))
    return rows


# --------------------------------------------------------------------------------------- build

def build():
    """MA-14: olive polymer rifle with a rotary dial selector, side window and swept magazine."""
    g = begin_rifle()
    upper(g)
    lower(g)
    handguard(g)
    front_end(g)
    rear_end(g)
    moving_parts(g)
    magazine(g)
    standard_parts(g)
    attachments(g, (0, 0.0, RAIL_TOP), (0, MUZZLE_Y, BORE), (0, 0.346, 0.015 - 0.0076), (0, -0.125, BORE), muzzle_r=0.0078)
    g.socket("eject", (0.016, 0.034, BORE + 0.002))
    clips(g)
    return g


def begin_rifle():
    return begin("rifle", {
        "bolt": ((0, -0.02, BORE), None),
        "charge": ((0, -0.12, UP_TOP), None),
        "mag": ((0, 0.066, 0.026), None),
        "trigger": ((0, 0.003, 0.007), None),
        "selector": ((0, DIAL[0], DIAL[1]), None),
    })


def upper(g):
    """Upper receiver: olive shell hollowed for the carrier, long left window, right ejection port."""
    up = ext_y("upper", [(-0.014, 0.030), (0.014, 0.030), (0.014, 0.0565), (0.0105, UP_TOP), (-0.0105, UP_TOP), (-0.014, 0.0565)],
               -0.098, 0.135, "olive", bevel=0.0009)
    up = cut(up, hole_through("chan", (0, 0.02, BORE), 0.0103, "y", 0.25, segs=28))
    up = carve(up, *slot_x("win", -0.054, 0.050, BORE, 0.0135, -0.013, 0.014))
    cuts = [block("port", (0.013, 0.033, BORE + 0.001), (0.014, 0.05, 0.012), "steel", bevel=0),
            block("chslot", (0, -0.065, 0.0595), (0.009, 0.075, 0.007), "steel", bevel=0)]
    up = cut(up, *cuts)
    up = carve(up, *[c for side in (-1, 1) for y in (0.080, 0.091, 0.102, 0.113, 0.124) for c in slot_z(y, 0.036, 0.053, 0.0042, side * 0.0145, 0.003)])
    # Window bezel: a black steel frame screwed over the window edge.
    bez = block("bezel", (-0.0149, -0.002, BORE), (0.0022, 0.116, 0.0188), "black", bevel=0.0006)
    bez = carve(bez, *slot_x("bwin", -0.054, 0.050, BORE, 0.0135, -0.015, 0.006))
    bscrews = [screw((-0.0163, y, z), "-x", 0.0011, head=0.0008) for y in (-0.0575, 0.0535) for z in (0.0378, 0.0522)]
    top = rail("rail", -0.088, 0.396, UP_TOP, "black")
    # Rail index numbers on the left flank of the rail base.
    nums = [label(str(i), (-0.0086, -0.083 + i * 0.04, UP_TOP + 0.002), 0.0022, "bright") for i in range(3, 12, 4)]
    # Right side: dust cover hanging open, brass deflector, forward assist.
    cover = block("cover", (0.0151, 0.033, 0.0335), (0.0014, 0.05, 0.011), "steel", bevel=0.0003)
    rib = block("crib", (0.0161, 0.033, 0.034), (0.001, 0.036, 0.0018), "steel", bevel=0.0002)
    hinge = cyl("hinge", (0.0152, 0.006, 0.0285), (0.0152, 0.06, 0.0285), 0.0012, "bright", segs=10)
    defl = prism("defl", [(-0.016, 0.040), (0.004, 0.040), (0.004, 0.056), (-0.006, 0.058), (-0.016, 0.050)], 0.006, "olive", x=0.016, bevel=0.0008)
    fa_h = cyl("fa", (0.012, -0.072, 0.048), (0.0215, -0.072, 0.048), 0.0062, "olive", segs=20)
    fa_b = cyl("fab", (0.0215, -0.072, 0.048), (0.025, -0.072, 0.048), 0.0048, "steel", segs=20)
    fa_b = cut(fa_b, *[block("fas", (0.0255, -0.072, 0.048), (0.002, 0.012, 0.0008), "steel", bevel=0, rot=a) for a in (0, 45, 90, 135)])
    lab = [label(MAKER, (-0.0142, -0.002, 0.0333), 0.0026, "bright"),
           label("MADE ON THE ISLAND", (0.0142, -0.03, 0.0335), 0.0024, "bright", side=1),
           label("MA-14", (0.0142, 0.095, 0.0335), 0.0034, "bright", side=1)]
    g.add(join([up, bez, *bscrews, top, *nums, cover, rib, hinge, defl, fa_h, fa_b, *lab], "upper"), "root")


def lower(g):
    """Lower receiver, magwell, trigger guard, pistol grip, tower and the dial's position marks."""
    pts = [(-0.100, 0.031), magpt(0.0665, 0.0), magpt(0.0665, 0.050), magpt(-0.0045, 0.050), magpt(-0.0045, 0.024),
           (-0.016, -0.002), (-0.072, -0.002), (-0.092, 0.008), (-0.100, 0.020)]
    low = prism("lower", pts, 0.026, "olive", bevel=0.0011)
    lip = prism("lip", [magpt(-0.0045, 0.043), magpt(0.0665, 0.043), magpt(0.068, 0.057), magpt(-0.006, 0.057)], 0.030, "olive", bevel=0.0011)

    def well():
        return prism("well", mag_quad(-0.0007, MAG_W + 0.0007, -0.03, 0.07), 0.0232, "steel", bevel=0)
    low = cut(low, well())
    lip = cut(lip, well())
    tower = block("tower", (0, -0.103, 0.0448), (0.026, 0.010, 0.0295), "olive", bevel=0.001)
    guard = prism("guard", [(0.039, -0.002), (0.039, -0.033), (0.036, -0.038), (-0.012, -0.038), (-0.027, -0.031), (-0.023, -0.002)],
                  0.014, "olive", bevel=0.0011)
    guard = cut(guard, prism("gh", [(0.0325, -0.005), (0.0325, -0.029), (0.029, -0.031), (-0.009, -0.031), (-0.019, -0.026),
                                    (-0.0175, -0.005)], 0.03, "steel", bevel=0))
    grip_pts = [(-0.014, 0.004), (-0.017, -0.012), (-0.0255, -0.036), (-0.0252, -0.048), (-0.0335, -0.062), (-0.0342, -0.072),
                (-0.0425, -0.090), (-0.0432, -0.106), (-0.047, -0.117), (-0.089, -0.117), (-0.093, -0.110), (-0.087, -0.080),
                (-0.080, -0.045), (-0.075, -0.018), (-0.084, -0.008), (-0.096, 0.004), (-0.094, 0.011), (-0.086, 0.009), (-0.072, 0.004)]
    grip = prism("grip", grip_pts, 0.030, "olive", bevel=0.0024, segs=3)
    base = prism("gbase", [(-0.046, -0.1165), (-0.090, -0.1165), (-0.091, -0.1215), (-0.045, -0.1215)], 0.031, "black", bevel=0.0012, segs=2)
    # Stippled side panels set into the grip.
    panel_pts = [(-0.0215, -0.012), (-0.0285, -0.036), (-0.0282, -0.048), (-0.0365, -0.062), (-0.0372, -0.072), (-0.0455, -0.090),
                 (-0.0462, -0.104), (-0.086, -0.104), (-0.0815, -0.075), (-0.0755, -0.045), (-0.071, -0.012)]
    panels = []
    for side in (-1, 1):
        x = side * 0.0156
        p = prism("gpanel", panel_pts, 0.0026, "olive", x=x, bevel=0)
        p = cut(p, *stipple("st", grip_rows(), x + side * 0.0013, side))
        panels.append(p)
    # Pins, bolt catch, mag release, sling plate.
    pins = [pin((0, y, z), "x", 0.0016, 0.0278) for y, z in ((0.096, 0.025), (-0.089, 0.024), (0.004, 0.007), (-0.020, 0.012))]
    catch = prism("catch", [(0.021, 0.013), (0.031, 0.013), (0.032, 0.027), (0.022, 0.027)], 0.0024, "steel", x=-0.0142, bevel=0.0003)
    catch = cut(catch, *slots("cs", 0.0225, 0.0305, 4, 0.0205, 0.028, -0.0162, -0.0150))
    mrel = cyl("mrel", (0.013, 0.029, 0.008), (0.0158, 0.029, 0.008), 0.0042, "steel", segs=18)
    fence = ring("fence", (0.0138, 0.029, 0.008), (1, 0, 0), 0.0062, 0.0046, 0.003, "olive", segs=20)
    plate = block("splate", (0, -0.1075, 0.043), (0.028, 0.003, 0.034), "steel", bevel=0.0005)
    loop = ring("loop", (-0.017, -0.1075, 0.031), (0, 1, 0), 0.0048, 0.0032, 0.0028, "steel", segs=18)
    # Dial escutcheon: ticks and engraved positions S / 1 / A around the dial.
    ticks, marks = [], []
    for ang, txt in ((120, "S"), (150, "1"), (180, "A")):
        a = math.radians(ang)
        ty, tz = DIAL[0] + 0.0153 * math.cos(a), DIAL[1] + 0.0153 * math.sin(a)
        ticks.append(block("tick", (-0.0134, ty, tz), (0.0008, 0.0022, 0.0007), "bright", bevel=0, rot=ang))
        marks.append(label(txt, (-0.01325, DIAL[0] + 0.0192 * math.cos(a), DIAL[1] + 0.0192 * math.sin(a)), 0.0036,
                           "red" if txt == "A" else "bright"))
    lab = [label("MA-14", (-0.01325, 0.071, 0.009), 0.0085, "bright"),
           label("CAL 5.56x45", (-0.01325, 0.071, -0.003), 0.003, "bright"),
           label("SN RR-14-0071", (-0.01325, 0.073, -0.0095), 0.0023, "bright"),
           label(MAKER, (0.01325, 0.070, 0.004), 0.0026, "bright", side=1)]
    g.add(join([low, lip, tower, guard, grip, base, *panels, *pins, catch, mrel, fence, plate, loop, *ticks, *marks, *lab], "lower"), "root")


def handguard(g):
    """Free-float olive handguard: horizontal grip ribs, M-LOK slots, short side and bottom rails."""
    outer = [(-0.013, UP_TOP), (0.013, UP_TOP), (0.021, 0.054), (0.021, 0.026), (0.012, 0.015), (-0.012, 0.015), (-0.021, 0.026), (-0.021, 0.054)]
    inner = [(-0.0112, 0.0592), (0.0112, 0.0592), (0.0182, 0.0522), (0.0182, 0.0272), (0.0106, 0.0178), (-0.0106, 0.0178),
             (-0.0182, 0.0272), (-0.0182, 0.0522)]
    hg = ext_y("handguard", outer, HG_Y0, HG_Y1, "olive", bevel=0.001)
    cuts = [ext_y("hgin", inner, HG_Y0 - 0.01, HG_Y1 + 0.01, "steel", bevel=0)]
    for side in (-1, 1):
        cuts += [c for c in mlok("ml", 0.158, 0.330, 5, 0.0325, side * 0.021)]
        cuts += [block("vent", (side * 0.017, y, 0.0205), (0.012, 0.016, 0.004), "steel", bevel=0, rot=0) for y in (0.18, 0.225, 0.27, 0.315)]
    hg = carve(hg, *cuts)
    parts = [hg]
    for side in (-1, 1):
        for z in (0.0415, 0.0450, 0.0485, 0.0520):
            parts.append(block("rib", (side * 0.0216, 0.244, z), (0.0016, 0.168, 0.0017), "olive", bevel=0.0005))
        parts.append(side_rail("srail", 0.340, 0.392, side, 0.0395))
        for y in (0.144, 0.162):
            parts.append(screw((side * 0.0213, y, 0.040), "x" if side > 0 else "-x", 0.0021))
        parts.append(screw((side * 0.0213, 0.335, 0.0395), "x" if side > 0 else "-x", 0.0015))
    cap = ext_y("hgcap", outer, HG_Y1, HG_Y1 + 0.004, "black", bevel=0.0008)
    parts.append(carve(cap, ext_y("capin", inner, HG_Y1 - 0.01, HG_Y1 + 0.01, "steel", bevel=0)))
    parts.append(rail("brail", 0.300, 0.392, 0.015, "black", flip=True))
    # QD sling cup at the front left.
    qd = cyl("qd", (-0.0206, 0.375, 0.0215), (-0.0222, 0.375, 0.0215), 0.0045, "steel", segs=18)
    parts.append(cut(qd, cyl("qdh", (-0.024, 0.375, 0.0215), (-0.019, 0.375, 0.0215), 0.0025, "steel", segs=14, bevel=0)))
    g.add(join(parts, "hg"), "root")


def mlok(name, y0, y1, count, z, x, depth=0.012, h=0.0068):
    out = []
    step = (y1 - y0) / count
    for i in range(count):
        yc = y0 + step * (i + 0.5)
        out += slot_x(name, yc - step * 0.31, yc + step * 0.31, z, h, x, depth)
    return out


def front_end(g):
    """Barrel, gas tube and gas block, the black steel section in front of the handguard."""
    parts = [cyl("barrel", (0, 0.06, BORE), (0, 0.405, BORE), 0.0098, "steel", segs=28),
             tube("muzzle", (0, 0.43, BORE), (0, MUZZLE_Y - 0.006, BORE), 0.0082, 0.0029, "steel", segs=28),
             cyl("step", (0, 0.429, BORE), (0, 0.434, BORE), 0.0094, "steel", r1=0.0082, segs=28),
             tube("thread", (0, MUZZLE_Y - 0.0065, BORE), (0, MUZZLE_Y + 0.001, BORE), 0.0064, 0.0029, "bright", segs=24),
             cyl("gastube", (0, 0.14, BORE + 0.0128), (0, 0.408, BORE + 0.0128), 0.0024, "steel", segs=12),
             ring("nut", (0, 0.138, BORE), (0, 1, 0), 0.0168, 0.0098, 0.008, "steel", segs=28)]
    gb = block("gasblock", (0, 0.4175, BORE + 0.0035), (0.021, 0.025, 0.027), "steel", bevel=0.0012)
    gb = cut(gb, *slots("gbs", 0.409, 0.426, 4, BORE + 0.010, BORE + 0.018, -0.012, -0.0098),
             *slots("gbs", 0.409, 0.426, 4, BORE + 0.010, BORE + 0.018, 0.0098, 0.012))
    parts += [gb, screw((0, 0.411, BORE - 0.0101), "-z", 0.0018), screw((0, 0.424, BORE - 0.0101), "-z", 0.0018),
              pin((0, 0.4175, BORE + 0.0125), "x", 0.0013, 0.0225)]
    g.add(join(parts, "front"), "root")


def rear_end(g):
    """Buffer tube with castle nut and end cap, behind the receiver."""
    tb = cyl("buffer", (0, -0.106, BORE), (0, -0.300, BORE), 0.0145, "steel", segs=32)
    tb = cut(tb, *[hole_through("adj", (0, -0.205 - i * 0.017, BORE - 0.0145), 0.0022, "z", 0.008, segs=10) for i in range(6)])
    ridge = block("ridge", (0, -0.24, BORE - 0.0148), (0.006, 0.12, 0.003), "steel", bevel=0.0004)
    nut = ring("castle", (0, -0.113, BORE), (0, 1, 0), 0.0168, 0.0140, 0.008, "steel", segs=32)
    notches = []
    for k in range(8):
        n = block("notch", (0, -0.1105, BORE + 0.0168), (0.0035, 0.004, 0.005), "steel", bevel=0)
        notches.append(rot_y(n, 22.5 + k * 45))
    nut = carve(nut, *notches)
    cap = cyl("cap", (0, -0.300, BORE), (0, -0.303, BORE), 0.0135, "steel", segs=32)
    g.add(join([tb, ridge, nut, cap], "rear"), "root")


def moving_parts(g):
    """Bolt carrier (seen through the window), charging handle, trigger and the selector dial."""
    # Bolt carrier group.
    car = cyl("carrier", (0, -0.095, BORE), (0, 0.046, BORE), 0.0088, "bright", segs=28)
    cuts = [ring("groove", (0, y, BORE), (0, 1, 0), 0.0095, 0.0080, 0.0016, "steel", segs=28) for y in (-0.082, -0.076, -0.070)]
    cuts += slot_x("light", -0.040, -0.008, BORE, 0.0045, -0.0088, 0.004) + slot_x("light", 0.000, 0.026, BORE, 0.0045, -0.0088, 0.004)
    cuts += [hole_through("vent", (0.0088, y, BORE), 0.0012, "x", 0.006, segs=10) for y in (0.010, 0.016)]
    car = carve(car, *cuts)
    cam = cyl("campin", (-0.0098, 0.034, BORE + 0.001), (-0.004, 0.034, BORE + 0.001), 0.0023, "steel", segs=14)
    head = cyl("bolthead", (0, 0.046, BORE), (0, 0.062, BORE), 0.0062, "steel", segs=24)
    lugs = [rot_y(block("lug", (0, 0.059, BORE + 0.0066), (0.0028, 0.006, 0.0016), "steel", bevel=0.0002), k * 45) for k in range(8)]
    ext = block("extractor", (0.0066, 0.052, BORE + 0.001), (0.0016, 0.02, 0.003), "steel", bevel=0.0003)
    key = block("gaskey", (0, -0.02, BORE + 0.0108), (0.0062, 0.032, 0.0052), "steel", bevel=0.0005)
    keyscrews = [screw((0, y, BORE + 0.0137), "z", 0.0013, head=0.001) for y in (-0.028, -0.014)]
    g.add(join([car, cam, head, *lugs, ext, key, *keyscrews], "bolt"), "bolt")
    # Ambidextrous T charging handle at the top rear.
    ch = plan("charge", [(-0.004, -0.03), (0.004, -0.03), (0.004, -0.120), (0.016, -0.119), (0.019, -0.123), (0.016, -0.128),
                         (-0.017, -0.128), (-0.0245, -0.1245), (-0.022, -0.119), (-0.004, -0.120)], 0.005, "black", z=UP_TOP, bevel=0.0006)
    ch = cut(ch, *slots("chs", -0.1265, -0.1205, 4, UP_TOP + 0.0015, UP_TOP + 0.004, -0.025, -0.014))
    g.add(ch, "charge")
    # Trigger: curved black steel blade.
    trig = prism("trigger", [(0.000, 0.004), (0.006, 0.004), (0.0072, -0.006), (0.0075, -0.013), (0.0062, -0.020), (0.0035, -0.0245),
                             (0.0012, -0.0245), (0.0030, -0.019), (0.0034, -0.012), (0.0025, -0.005), (0.000, -0.001)], 0.006, "black",
                 bevel=0.0004)
    g.add(trig, "trigger")
    # Selector dial: escutcheon ring, knurled steel wheel, cap with a thumb fin and the index line.
    cy, cz = DIAL
    n = 60
    teeth = []
    for i in range(2 * n):
        a = math.pi * i / n
        r = 0.0130 if i % 2 == 0 else 0.0122
        teeth.append((cy + r * math.cos(a), cz + r * math.sin(a)))
    knurl = prism("knurl", teeth, 0.004, "steel", x=-0.0165, bevel=0)
    base = cyl("dbase", (-0.0128, cy, cz), (-0.0146, cy, cz), 0.0138, "black", segs=40)
    capd = cyl("dcap", (-0.0185, cy, cz), (-0.0196, cy, cz), 0.0108, "steel", segs=36, bevel=0.0005)
    groove = ring("dgroove", (-0.0196, cy, cz), (1, 0, 0), 0.0096, 0.0088, 0.0006, "steel", segs=36)
    capd = cut(capd, groove)
    fin = block("fin", (-0.0203, cy, cz), (0.0016, 0.019, 0.0024), "steel", bevel=0.0005)
    a = math.radians(180)
    index = block("index", (-0.0212, cy + 0.0064 * math.cos(a), cz + 0.0064 * math.sin(a)), (0.0005, 0.0055, 0.0009), "bright", bevel=0)
    lever = block("amblever", (0.0146, cy + 0.008 * math.cos(a), cz + 0.008 * math.sin(a)), (0.0026, 0.016, 0.0042), "steel", bevel=0.0005)
    hub = cyl("hub", (0.0128, cy, cz), (0.0158, cy, cz), 0.0045, "steel", segs=20)
    g.add(join([knurl, base, capd, fin, index, lever, hub], "selector"), "selector")


def magazine(g):
    """Forward-swept black polymer box mag: ribs, brass witness window, flared floorplate, top round."""
    ds = [-0.003, 0.02, 0.05, 0.08, 0.11, 0.14, 0.165, MAG_L]
    body = prism("mag", [magpt(0, d) for d in ds] + [magpt(MAG_W, d) for d in reversed(ds)], 0.022, "black", bevel=0.0012)
    body = cut(body, prism("wit", mag_quad(0.008, 0.017, 0.035, 0.125), 0.009, "steel", x=-0.0115, bevel=0))
    parts = [body]
    # Rounds stacked behind the witness window.
    for k in range(15):
        d = 0.034 + k * 0.0062
        p0, p1 = magpt(0.004, d), magpt(0.022, d)
        parts.append(cyl("case", (-0.0058 + 0.0012 * (k % 2), *p0), (-0.0058 + 0.0012 * (k % 2), *p1), 0.0028, "brass", segs=8, bevel=0))
    for d, txt in ((0.045, "30"), (0.085, "20"), (0.120, "10")):
        y, z = magpt(0.025, d)
        parts.append(label(txt, (-0.0112, y, z), 0.0026, "bright"))
        ty, tz = magpt(0.0195, d)
        parts.append(block("mtick", (-0.0112, ty, tz), (0.0006, 0.0028, 0.0006), "bright", bevel=0, rot=8))
    for d in (0.136, 0.146, 0.156, 0.166, 0.176):
        parts.append(prism("mrib", mag_quad(0.006, 0.056, d - 0.0012, d + 0.0012), 0.0254, "black", bevel=0.0005))
    for u in (0.005, 0.057):
        parts.append(prism("spine", mag_quad(u - 0.0015, u + 0.0015, 0.06, 0.13), 0.0236, "black", bevel=0.0004))
    floor = prism("floor", [magpt(-0.003, MAG_L - 0.002), magpt(MAG_W + 0.003, MAG_L - 0.002), magpt(MAG_W + 0.005, MAG_L + 0.011),
                            magpt(-0.004, MAG_L + 0.011)], 0.026, "black", bevel=0.002, segs=3)
    floor = cut(floor, *[prism("fg", mag_quad(MAG_W + 0.001 - 0.0015 * 0, MAG_W + 0.008, MAG_L + 0.001 + i * 0.0028, MAG_L + 0.0022 + i * 0.0028),
                               0.03, "steel", bevel=0) for i in range(3)])
    parts.append(floor)
    parts.append(label("RR", (-0.0131, *magpt(0.03, MAG_L + 0.0045)), 0.0045, "bright"))
    # Top round on the feed lips.
    c0, c1, c2, c3 = magpt(0.004, -0.0075), magpt(0.044, -0.0075), magpt(0.049, -0.0075), magpt(0.052, -0.0075)
    tip = magpt(0.062, -0.0075)
    x = -0.002
    parts += [cyl("rnd", (x, *c0), (x, *c1), 0.0047, "brass", segs=18), cyl("sh", (x, *c1), (x, *c2), 0.0047, "brass", r1=0.0031, segs=18),
              cyl("neck", (x, *c2), (x, *c3), 0.0031, "brass", segs=18), cyl("bullet", (x, *c3), (x, *tip), 0.0029, "copper", r1=0.0009, segs=18)]
    g.add(join(parts, "magazine"), "mag")


def standard_parts(g):
    """The bare gun's own slot pieces: flip-up irons, birdcage flash hider, hand stop, adjustable stock."""
    # Flip-up irons, both raised.
    rb = block("rbase", (0, -0.072, RAIL_TOP + 0.004), (0.022, 0.032, 0.008), "black", bevel=0.0008)
    leaf = block("leaf", (0, -0.074, RAIL_TOP + 0.0175), (0.022, 0.005, 0.019), "black", bevel=0.0006)
    leaf = cut(leaf, *[block("ln", (s * 0.0062, -0.074, RAIL_TOP + 0.024), (0.005, 0.01, 0.014), "steel", bevel=0) for s in (-1, 1)],
               hole_through("ap", (0, -0.074, RAIL_TOP + 0.0225), 0.0013, "y", 0.02, segs=14))
    rk = cyl("wind", (0.011, -0.068, RAIL_TOP + 0.005), (0.0155, -0.068, RAIL_TOP + 0.005), 0.0042, "steel", segs=18)
    rk = cut(rk, *[block("kn", (0.0155, -0.068, RAIL_TOP + 0.005), (0.002, 0.01, 0.0007), "steel", bevel=0, rot=a) for a in (0, 45, 90, 135)])
    rpin = pin((0, -0.0745, RAIL_TOP + 0.0085), "x", 0.0012, 0.024)
    fb = block("fbase", (0, 0.378, RAIL_TOP + 0.004), (0.022, 0.030, 0.008), "black", bevel=0.0008)
    tower = prism("ftower", [(0.366, RAIL_TOP + 0.008), (0.389, RAIL_TOP + 0.008), (0.3835, RAIL_TOP + 0.034), (0.3715, RAIL_TOP + 0.034)],
                  0.021, "black", bevel=0.0006)
    tower = cut(tower, block("fw", (0, 0.378, RAIL_TOP + 0.03), (0.013, 0.04, 0.03), "steel", bevel=0),
                hole_through("fh", (0, 0.378, RAIL_TOP + 0.013), 0.002, "x", 0.03, segs=12))
    post = cyl("post", (0, 0.378, RAIL_TOP + 0.014), (0, 0.378, RAIL_TOP + 0.031), 0.0012, "steel", segs=10)
    postb = cyl("postb", (0, 0.378, RAIL_TOP + 0.013), (0, 0.378, RAIL_TOP + 0.017), 0.0024, "steel", segs=12)
    fs = [screw((0.0112, y, RAIL_TOP + 0.003), "x", 0.0016) for y in (-0.064, 0.386)]
    irons = join([rb, leaf, rk, rpin, fb, tower, post, postb, *fs], "att.optic.irons")
    irons.name = "att.optic.irons"
    g.add(irons, "root")
    # Birdcage flash hider.
    fh = tube("att.muzzle.bare", (0, MUZZLE_Y - 0.0045, BORE), (0, MUZZLE_Y + 0.055, BORE), 0.0105, 0.0046, "steel", segs=32)
    fcuts = [rot_y(block("fs", (0, MUZZLE_Y + 0.034, BORE + 0.0105), (0.0028, 0.03, 0.009), "steel", bevel=0), a) for a in (0, 60, 120, -60, -120)]
    fcuts += [block("flat", (s * 0.0105, MUZZLE_Y + 0.006, BORE), (0.004, 0.012, 0.03), "steel", bevel=0) for s in (-1, 1)]
    fh = carve(fh, *fcuts)
    washer = ring("washer", (0, MUZZLE_Y - 0.0055, BORE), (0, 1, 0), 0.0094, 0.0064, 0.002, "bright", segs=28)
    fh = join([fh, washer], "att.muzzle.bare")
    fh.name = "att.muzzle.bare"
    g.add(fh, "root")
    # Hand stop on the bottom rail.
    hs = prism("att.grip.standard", [(0.326, 0.0074), (0.366, 0.0074), (0.360, 0.000), (0.347, -0.009), (0.336, -0.0125), (0.330, -0.006)],
               0.022, "black", bevel=0.0015, segs=3)
    hs = cut(hs, *slots("hsg", 0.334, 0.358, 4, -0.003, 0.004, -0.013, -0.0095), *slots("hsg", 0.334, 0.358, 4, -0.003, 0.004, 0.0095, 0.013))
    hs = join([hs, screw((0.0112, 0.350, 0.003), "x", 0.0016)], "att.grip.standard")
    hs.name = "att.grip.standard"
    g.add(hs, "root")
    # Adjustable stock riding the buffer tube.
    prof = [(-0.190, 0.026), (-0.190, 0.0635), (-0.288, 0.0655), (-0.300, 0.069), (-0.300, -0.048), (-0.291, -0.050), (-0.262, -0.020),
            (-0.232, 0.012), (-0.205, 0.022)]
    st = prism("att.stock.standard", prof, 0.034, "olive", bevel=0.0024, segs=3)
    st = carve(st, prism("sh", [(-0.228, 0.0245), (-0.283, 0.0245), (-0.287, -0.030), (-0.271, -0.022)], 0.05, "steel", bevel=0),
               hole_through("tubeh", (0, -0.19, BORE), 0.0149, "y", 0.03, segs=28),
               block("sling", (0, -0.294, -0.036), (0.05, 0.004, 0.012), "steel", bevel=0),
               *slots("cheek", -0.275, -0.215, 7, 0.060, 0.067, -0.02, 0.02))
    pad = prism("pad", [(-0.300, 0.068), (-0.318, 0.070), (-0.318, -0.050), (-0.300, -0.048)], 0.036, "rubber", bevel=0.003, segs=3)
    pad = cut(pad, *[block("pg", (0, -0.318, -0.04 + i * 0.0105), (0.04, 0.003, 0.0014), "steel", bevel=0) for i in range(11)])
    lever = prism("lever", [(-0.196, 0.026), (-0.228, 0.019), (-0.228, 0.015), (-0.198, 0.021)], 0.012, "black", bevel=0.0006)
    sqd = cyl("sqd", (-0.0168, -0.21, 0.047), (-0.0185, -0.21, 0.047), 0.0052, "steel", segs=18)
    sqd = cut(sqd, cyl("sqh", (-0.020, -0.21, 0.047), (-0.0155, -0.21, 0.047), 0.0028, "steel", segs=14, bevel=0))
    lock = screw((-0.0172, -0.236, 0.036), "-x", 0.0022)
    stock = join([st, pad, lever, sqd, lock, label("MA-14", (-0.0172, -0.270, 0.050), 0.005, "bright")], "att.stock.standard")
    stock.name = "att.stock.standard"
    g.add(stock, "root")


# --------------------------------------------------------------------------------------- clips

def clips(g):
    g.clip("fire", 0.09, {
        "bolt": [(0, (0, 0, 0), (0, 0, 0)), (0.033, (0, -0.07, 0), (0, 0, 0)), (0.067, (0, -0.01, 0), (0, 0, 0)), (0.09, (0, 0, 0), (0, 0, 0))],
        "trigger": [(0, (0, 0, 0), (0, 0, 0)), (0.017, (0, 0, 0), (-14, 0, 0)), (0.05, (0, 0, 0), (-14, 0, 0)), (0.09, (0, 0, 0), (0, 0, 0))],
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.033, (0, -0.008, 0.002), (2.5, 0, 0.6)), (0.09, (0, 0, 0), (0, 0, 0))],
    })
    drop = (math.sin(TILT), -math.cos(TILT))
    common_clips(g, 2.4, {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.3, (0.012, 0, 0.02), (10, 25, 6)), (1.2, (0.012, 0, 0.02), (12, 28, 6)),
                 (1.45, (0, -0.01, 0.02), (6, -12, -4)), (1.85, (0, -0.014, 0.018), (8, -14, -4)), (2.1, (0, 0, 0.006), (2, 0, 0)),
                 (2.4, (0, 0, 0), (0, 0, 0))],
        "mag": mag_drop(drop, 0.35, 1.02, 1.2),
        "charge": [(0, (0, 0, 0), (0, 0, 0)), (1.5, (0, 0, 0), (0, 0, 0)), (1.62, (0, -0.055, 0), (0, 0, 0)), (1.75, (0, -0.055, 0), (0, 0, 0)),
                   (1.8, (0, 0, 0), (0, 0, 0))],
        "bolt": [(0, (0, 0, 0), (0, 0, 0)), (1.5, (0, 0, 0), (0, 0, 0)), (1.62, (0, -0.055, 0), (0, 0, 0)), (1.75, (0, -0.055, 0), (0, 0, 0)),
                 (1.8, (0, 0, 0), (0, 0, 0))],
    }, draw_len=0.5)
    g.clip("inspect", 3.3, {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.5, (-0.03, 0.02, 0.03), (10, -35, 25)), (2.0, (-0.03, 0.02, 0.03), (12, -40, 30)),
                 (2.5, (0.02, 0, 0.02), (-8, 30, -20)), (2.9, (0.02, 0, 0.02), (-8, 32, -22)), (3.3, (0, 0, 0), (0, 0, 0))],
        "charge": [(0, (0, 0, 0), (0, 0, 0)), (0.7, (0, 0, 0), (0, 0, 0)), (0.85, (0, -0.022, 0), (0, 0, 0)), (1.1, (0, -0.022, 0), (0, 0, 0)),
                   (1.2, (0, 0, 0), (0, 0, 0))],
        "bolt": [(0, (0, 0, 0), (0, 0, 0)), (0.7, (0, 0, 0), (0, 0, 0)), (0.85, (0, -0.022, 0), (0, 0, 0)), (1.1, (0, -0.022, 0), (0, 0, 0)),
                 (1.2, (0, 0, 0), (0, 0, 0))],
        "selector": [(0, (0, 0, 0), (0, 0, 0)), (1.3, (0, 0, 0), (0, 0, 0)), (1.42, (0, 0, 0), (-30, 0, 0)), (1.62, (0, 0, 0), (-30, 0, 0)),
                     (1.74, (0, 0, 0), (-60, 0, 0)), (1.92, (0, 0, 0), (-60, 0, 0)), (2.1, (0, 0, 0), (0, 0, 0))],
    })


SPEC = {"build": build, "length": (0.74, 0.84), "tris": (20000, 70000),
        "bones": ["root", "bolt", "charge", "mag", "trigger", "selector"],
        "sockets": ["muzzle", "eject", "optic", "under", "stock", "scope.eye", "reddot.lens"],
        "attachments": SLOT_ATTS + ["att.optic.irons", "att.muzzle.bare", "att.grip.standard", "att.stock.standard"],
        "parts": {"mesh.root": "root", "mesh.bolt": "bolt", "mesh.charge": "charge", "mesh.mag": "mag", "mesh.trigger": "trigger",
                  "mesh.selector": "selector"},
        "moves": {"fire": ["bolt", "trigger", "root"], "reload": ["mag", "charge", "bolt", "root"], "draw": ["root"],
                  "inspect": ["root", "selector", "bolt"]},
        "view": {"cam": (-1.05, 0.03, 0.30), "look": (0, 0.115, -0.04), "lens": 40,
                 "show": ("att.optic.irons", "att.muzzle.bare", "att.grip.standard", "att.stock.standard")}}
