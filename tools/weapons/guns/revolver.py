"""Warden revolver: a heavy top-break six-shot in dark steel with bright-steel and red accents.

The barrel assembly (`breech`) carries the barrel, ventilated top rib, full underlug, top strap and
the latch; it hinges at the lower front of the frame and tips down for reload. The fluted cylinder
spins on its own axis (`cylinder`), the star extractor (`extractor`) pops back to throw the empties,
and the six cartridges ride `rounds` (a child of the cylinder, so they turn with it on every shot).
The hammer rests cocked and falls on fire; the cylinder indexes 60 degrees as it re-cocks.
"""

import math

import bmesh
from mathutils import Matrix, Vector

import kit
from kit import begin, block, cyl, dimples, hole_through, join, label, mlok, pin, prism, rail, ring, screw, slots, tube
from parts import MAKER, SLOT_ATTS, optic_reddot, optic_scope

BORE = 0.046            # bore axis height
CR = 0.0135             # chamber circle radius (cylinder axis to chamber centre)
ZC = BORE - CR          # cylinder axis height
CYL_R = 0.0215          # cylinder radius
CY0, CY1 = -0.004, 0.042  # cylinder rear and front faces
CH_R = 0.0058           # chamber radius
HINGE = (0, 0.052, 0.003)
HAMMER = (0, -0.031, 0.026)
COCK = 26               # degrees the hammer sits back from its fallen pose
MUZZLE_Y = 0.226


# ------------------------------------------------------------------------------- local helpers

def lathe(name, prof, c, material, segs=32, bevel=0.0005, bsegs=2):
    """Closed solid of revolution around a Y-parallel axis through (c[0], c[1]); `prof` is
    [(y, r), ...] from rear to front, starting and ending on the axis (r == 0)."""
    bm = bmesh.new()
    rings = []
    for y, r in prof:
        if r <= 1e-9:
            rings.append(bm.verts.new((c[0], y, c[1])))
        else:
            rings.append([bm.verts.new((c[0] + r * math.cos(2 * math.pi * i / segs), y, c[1] + r * math.sin(2 * math.pi * i / segs)))
                          for i in range(segs)])
    for a, b in zip(rings, rings[1:]):
        if isinstance(a, list) and isinstance(b, list):
            for i in range(segs):
                j = (i + 1) % segs
                bm.faces.new((a[i], a[j], b[j], b[i]))
        elif isinstance(a, list):
            for i in range(segs):
                bm.faces.new((a[i], a[(i + 1) % segs], b))
        elif isinstance(b, list):
            for i in range(segs):
                bm.faces.new((a, b[(i + 1) % segs], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return kit._obj(name, bm, material, bevel, bsegs)


def capsule(name, y0, y1, r, c, segs=16):
    """Round-ended cutter along Y (for flutes)."""
    prof = [(y0, 0)]
    for k in range(1, 5):
        a = math.pi / 2 * k / 4
        prof.append((y0 + r - r * math.cos(a), r * math.sin(a)))
    for k in range(0, 4):
        a = math.pi / 2 * k / 4
        prof.append((y1 - r + r * math.sin(a), r * math.cos(a)))
    prof.append((y1, 0))
    return lathe(name, prof, c, "steel", segs=segs, bevel=0)


def roty(obj, c, deg):
    """Spin a mesh about the Y-parallel axis through (c[0], c[1])."""
    obj.data.transform(Matrix.Translation((c[0], 0, c[1])) @ Matrix.Rotation(math.radians(deg), 4, "Y")
                       @ Matrix.Translation((-c[0], 0, -c[1])))
    return obj


def rotx(obj, p, deg):
    p = Vector(p)
    obj.data.transform(Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, "X") @ Matrix.Translation(-p))
    return obj


def cutx(target, *cutters):
    """kit.cut with the exact solver's self-intersection on, for cutters that overlap each other."""
    if not cutters:
        return target
    cutter = join(list(cutters), "_cutter") if len(cutters) > 1 else cutters[0]
    mod = target.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.use_self = True
    mod.object = cutter
    kit._apply(target, mod.name)
    kit.bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def edge_grooves(pts, x, w=0.0007, d=0.0016, closed=True):
    """Thin engraved line cutters following a side outline [(y, z), ...] on the face at `x`."""
    out = []
    seq = list(zip(pts, pts[1:] + pts[:1])) if closed else list(zip(pts, pts[1:]))
    for (y0, z0), (y1, z1) in seq:
        L = math.hypot(y1 - y0, z1 - z0)
        out.append(block("g", (x, (y0 + y1) / 2, (z0 + z1) / 2), (d, L + w, w), "steel", bevel=0,
                         rot=math.degrees(math.atan2(z1 - z0, y1 - y0))))
    return out


def chambers(r_from_axis=CR):
    """(x, z) of the six chamber centres; the first one sits on the bore line."""
    return [(r_from_axis * math.cos(math.radians(90 + 60 * k)), ZC + r_from_axis * math.sin(math.radians(90 + 60 * k))) for k in range(6)]


def reshade(o, angle=40):
    """Drop custom normals (e.g. after cutting into an already bevelled mesh) and smooth by angle."""
    bpy = kit.bpy
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    return o


def taper_rear(o, amount=0.33, top=0.056):
    """Narrow the frame behind the recoil shield toward its top, the way a revolver frame rounds off
    around the hammer. Works on any mesh, so screws and markings follow the slanted side."""
    for v in o.data.vertices:
        y, z = v.co.y, v.co.z
        g = min(1.0, max(0.0, (-0.008 - y) / 0.008))
        t = min(1.0, max(0.0, z / top))
        v.co.x *= 1 - amount * t * t * (3 - 2 * t) * g
    return o


def named(o, name):
    o.name = name
    return o


# ------------------------------------------------------------------------------------- build

def build():
    """Warden: a heavy top-break six-shot revolver."""
    g = begin("revolver", {
        "breech": (HINGE, None),
        "cylinder": ((0, CY0, ZC), "breech"),
        "extractor": ((0, CY0, ZC), "breech"),
        "rounds": ((0, CY0, ZC), "cylinder"),
        "hammer": (HAMMER, None),
        "trigger": ((0, 0.006, 0.002), None),
    })
    frame(g)
    grips(g)
    barrel(g)
    cylinder(g)
    hammer_trigger(g)
    gunsmith(g)
    clips(g)
    return g


def frame(g):
    """Frame: standing breech and recoil shield, bottom strap to the hinge, hammer slot, side plate,
    grip tang and trigger guard."""
    F = [(0.058, 0.010), (0.058, 0.000), (0.054, -0.005), (0.040, -0.006), (-0.016, -0.006), (-0.024, -0.008), (-0.062, -0.002),
         (-0.067, 0.004), (-0.061, 0.018), (-0.051, 0.032), (-0.041, 0.045), (-0.031, 0.053), (-0.0215, 0.056), (-0.0055, 0.056),
         (-0.0055, 0.0095), (0.043, 0.0095), (0.046, 0.011)]
    fr = prism("frame", F, 0.034, "steel", bevel=0.0009)
    fr = kit.cut(fr,
                 block("hslot", (0, -0.035, 0.05), (0.0094, 0.031, 0.06), "steel", bevel=0),
                 block("tslot", (0, 0.007, -0.004), (0.0072, 0.022, 0.016), "steel", bevel=0),
                 block("fslot", (0, 0.055, 0.004), (0.0186, 0.024, 0.034), "steel", bevel=0))
    # Side plate outline, engraved on both sides; screws on the left, the maker's mark inside it.
    plate = [(-0.0135, 0.004), (-0.0135, 0.046), (-0.022, 0.052), (-0.034, 0.049), (-0.045, 0.034), (-0.054, 0.016), (-0.056, 0.004)]
    fr = cutx(fr, *edge_grooves(plate, -0.017), *edge_grooves(plate, 0.017))
    # Lightening flutes along the bottom strap.
    fr = cutx(fr, *[block("bf", (s * 0.017, 0.019, 0.0018), (0.0016, 0.040, 0.0032), "steel", bevel=0) for s in (-1, 1)],
              *[cyl("bfe", (s * 0.0175, y, 0.0018), (s * 0.0165, y, 0.0018), 0.0016, "steel", segs=12, bevel=0)
                for s in (-1, 1) for y in (-0.001, 0.039)])
    bits = [fr]
    # Recoil shield: a disc as wide as the cylinder, with the firing-pin bushing on the bore line.
    shield = cyl("shield", (0, -0.0105, ZC), (0, -0.0055, ZC), CYL_R + 0.0003, "steel", segs=64, bevel=0.0006)
    shield = kit.cut(shield, cyl("fp", (0, -0.0062, BORE), (0, -0.004, BORE), 0.0024, "steel", segs=16, bevel=0))
    bits += [shield, cyl("bush", (0, -0.0066, BORE), (0, -0.0060, BORE), 0.0018, "bright", segs=16, bevel=0.0001),
             cyl("fpin", (0, -0.0070, BORE), (0, -0.0059, BORE), 0.0008, "bright", segs=10, bevel=0)]
    # Hinge knuckles either side of the breech lug, a bright pin and a screw head on the left.
    for s in (-1, 1):
        bits.append(cyl("knuckle", (s * 0.0093, HINGE[1], HINGE[2]), (s * 0.017, HINGE[1], HINGE[2]), 0.0075, "steel", segs=28, bevel=0.0007))
    bits += [pin((0, HINGE[1], HINGE[2]), "x", 0.0024, 0.0352), screw((-0.0178, HINGE[1], HINGE[2]), "-x", 0.0032, head=0.0014),
             screw((0.0178, HINGE[1], HINGE[2]), "x", 0.0032, head=0.0014)]
    # Cylinder stop peeking out of the bottom strap.
    bits.append(block("stop", (0, 0.022, 0.0098), (0.004, 0.007, 0.0016), "bright", bevel=0.0003))
    # Side plate screws, hammer and trigger pin heads.
    bits += [screw((-0.0172, y, z), "-x", 0.0021) for y, z in ((-0.018, 0.041), (-0.047, 0.012), (-0.019, 0.008))]
    bits += [screw((0.0172, y, z), "x", 0.0021) for y, z in ((-0.018, 0.041), (-0.047, 0.012))]
    bits += [pin((0, HAMMER[1], HAMMER[2]), "x", 0.0026, 0.0352), pin((0, 0.006, 0.002), "x", 0.0018, 0.0350)]
    bits += [label(MAKER, (-0.017, -0.032, 0.022), 0.0029, "bright"), label("WARDEN  TOP-BREAK", (-0.017, -0.032, 0.016), 0.0021, "bright"),
             label("No. 0457", (-0.017, 0.026, 0.0035), 0.0029, "bright"),
             label("MADE ON THE ISLAND", (0.017, -0.032, 0.020), 0.0024, "bright", side=1)]
    # Grip tang: narrow steel straps the grip panels wrap around.
    tang = prism("tang", [(-0.018, -0.004), (-0.022, -0.010), (-0.037, -0.050), (-0.054, -0.100), (-0.058, -0.106), (-0.096, -0.104),
                          (-0.098, -0.096), (-0.084, -0.050), (-0.072, -0.014), (-0.064, 0.002), (-0.040, 0.000)], 0.016, "steel", bevel=0.0012)
    tang = kit.cut(tang, hole_through("lan", (0, -0.078, -0.099), 0.0022, "x", 0.04))
    bits += [tang, pin((0, -0.078, -0.099), "x", 0.0016, 0.019)]
    # Trigger guard.
    guard = prism("guard", [(-0.016, -0.004), (0.038, -0.004), (0.042, -0.012), (0.040, -0.026), (0.032, -0.034), (0.004, -0.036),
                            (-0.010, -0.031), (-0.018, -0.018), (-0.022, -0.010)], 0.010, "steel", bevel=0.0012, segs=3)
    guard = kit.cut(guard, prism("gh", [(-0.010, -0.008), (0.034, -0.008), (0.037, -0.013), (0.035, -0.024), (0.029, -0.030),
                                        (0.005, -0.0315), (-0.007, -0.027), (-0.013, -0.017), (-0.015, -0.010)], 0.03, "steel", bevel=0))
    bits += [guard, screw((0, 0.034, -0.0335), "-z", 0.0018)]
    for b in bits:  # added one by one so each keeps its own bevel width
        g.add(taper_rear(b), "root")


def finger_profile(top, bottom, depth, bumps=3, n=36):
    """Front edge of a finger-groove grip from `top` to `bottom` (y, z), bulging forward between fingers."""
    (y0, z0), (y1, z1) = top, bottom
    L = math.hypot(y1 - y0, z1 - z0)
    ny, nz = (z0 - z1) / L, -(y0 - y1) / L  # forward normal
    ny, nz = abs(ny), -abs(nz)
    pts = []
    for i in range(n + 1):
        t = i / n
        off = depth * (0.5 + 0.5 * math.cos(2 * math.pi * bumps * t))
        pts.append((y0 + (y1 - y0) * t + ny * off, z0 + (z1 - z0) * t + nz * off))
    return pts


def grip_shell(name, width, front_depth, butt_z, material):
    front = finger_profile((-0.0215, -0.006), (-0.056, butt_z + 0.006), front_depth)
    pts = [(-0.017, -0.002)] + front + [(-0.060, butt_z), (-0.098, butt_z), (-0.104, butt_z + 0.007), (-0.101, butt_z + 0.02),
                                        (-0.088, -0.060), (-0.078, -0.028), (-0.071, -0.010), (-0.067, 0.0), (-0.064, 0.003), (-0.026, -0.0035)]
    o = prism(name, pts, width, material, bevel=0.0034, segs=3)
    kit.apply_modifiers(o)  # round it first, so the stippling cut afterwards is not bevelled dimple by dimple
    o["bevel"] = 0.0
    return o


def grips(g):
    """Gunsmith stock slot = grips. Standard: rubber finger-groove wrap with stippling and a red medallion.
    Light: slim red G10 target panels. Heavy: a fat rubber wrap with an extended butt and a lanyard ring."""
    std = grip_shell("att.stock.standard", 0.035, 0.0042, -0.114, "rubber")
    st = []
    for s in (-1, 1):
        st += dimples("st", -0.079, -0.053, -0.033, -0.094, s * 0.0175, 7, 10, r=0.00105, depth=0.0018, side=s)
    std = reshade(kit.cut(std, *st))
    bits = [std]
    for s in (-1, 1):
        x = s * 0.0175
        bits += [cyl("medal", (x - s * 0.0004, -0.051, -0.018), (x + s * 0.0009, -0.051, -0.018), 0.0056, "red", segs=28, bevel=0.0002),
                 ring("mring", (x + s * 0.0004, -0.051, -0.018), (1, 0, 0), 0.0066, 0.0055, 0.0014, "bright", segs=28),
                 label("W", (x + s * 0.0010, -0.051, -0.018), 0.0066, "bright", side=s),
                 screw((x + s * 0.0004, -0.078, -0.103), "x" if s > 0 else "-x", 0.0021)]
    g.add(named(join(bits, "att.stock.standard"), "att.stock.standard"), "root")

    bits = []
    for s in (-1, 1):
        x = s * 0.0101
        p = prism("lp", [(-0.024, -0.008), (-0.036, -0.048), (-0.052, -0.096), (-0.091, -0.097), (-0.081, -0.050), (-0.070, -0.012),
                         (-0.062, -0.002), (-0.040, -0.003)], 0.0042, "red", x=x, bevel=0.0012, segs=3)
        p = kit.cut(p, *[block("lg", (x + s * 0.002, -0.058 - i * 0.0022, -0.030 - i * 0.0085), (0.0016, 0.034, 0.0022), "steel", bevel=0, rot=-12)
                         for i in range(6)])
        bits += [p, screw((x + s * 0.0021, -0.053, -0.020), "x" if s > 0 else "-x", 0.0021),
                 screw((x + s * 0.0021, -0.073, -0.088), "x" if s > 0 else "-x", 0.0021)]
    g.add(named(join(bits, "att.stock.light"), "att.stock.light"), "root")

    heavy = grip_shell("att.stock.heavy", 0.041, 0.0055, -0.132, "rubber")
    st = []
    for s in (-1, 1):
        st += dimples("hs", -0.088, -0.056, -0.012, -0.116, s * 0.0205, 8, 13, r=0.0011, depth=0.0018, side=s)
    heavy = reshade(kit.cut(heavy, *st))
    cap = prism("cap", [(-0.060, -0.128), (-0.099, -0.128), (-0.1055, -0.123), (-0.1045, -0.137), (-0.062, -0.137)], 0.036, "steel",
                bevel=0.0015, segs=3)
    lan = ring("lan", (0, -0.082, -0.142), (1, 0, 0), 0.0065, 0.0042, 0.003, "bright", segs=24)
    g.add(named(join([heavy, cap, lan, pin((0, -0.082, -0.1345), "x", 0.0018, 0.038),
                      cyl("hm", (-0.0206, -0.054, -0.012), (-0.0193, -0.054, -0.012), 0.005, "red", segs=24)], "att.stock.heavy"),
                "att.stock.heavy"), "root")
    g.socket("stock", (0, -0.078, -0.114), "root")


def barrel(g):
    """Barrel assembly on the breech bone: barrel, vent rib, full underlug with a short rail, top strap,
    hinge arm and latch."""
    bits = []
    bits.append(tube("barrel", (0, 0.0425, BORE), (0, MUZZLE_Y, BORE), 0.0105, 0.0058, "steel", segs=40))
    bits.append(ring("crown", (0, MUZZLE_Y - 0.0004, BORE), (0, 1, 0), 0.0076, 0.0058, 0.0012, "bright", segs=32))
    # Rifling: six lands you can see down the bore.
    for k in range(6):
        a = math.radians(60 * k + 15)
        bits.append(block("land", (0.0055 * math.cos(a), MUZZLE_Y - 0.03, BORE + 0.0055 * math.sin(a)), (0.0012, 0.058, 0.0012), "steel",
                          bevel=0))
        roty(bits[-1], (0.0055 * math.cos(a), BORE + 0.0055 * math.sin(a)), -math.degrees(a))
    # Full underlug, with a long pocket on each side carrying the name.
    lug = prism("lug", [(0.046, BORE), (MUZZLE_Y, BORE), (MUZZLE_Y, 0.028), (MUZZLE_Y - 0.0045, 0.0215), (0.066, 0.0215), (0.058, 0.026),
                        (0.046, 0.026)], 0.0175, "steel", bevel=0.0011)
    lug = kit.cut(lug, block("pk", (-0.00875, 0.128, 0.0335), (0.0016, 0.112, 0.0118), "steel", bevel=0),
                  block("pk", (0.00875, 0.128, 0.0335), (0.0016, 0.112, 0.0118), "steel", bevel=0),
                  hole_through("arbor", (0, 0.05, ZC), 0.0031, "y", 0.012))
    bits += [lug, label("WARDEN", (-0.0080, 0.118, 0.0336), 0.0088, "bright"), label(".455 MAG", (-0.0080, 0.167, 0.0336), 0.0042, "red"),
             label(MAKER, (0.0080, 0.128, 0.0336), 0.0040, "bright", side=1)]
    bits += [screw((-0.00885, y, 0.0245), "-x", 0.0015, head=0.0008) for y in (0.172, 0.208)]
    bits.append(rail("rail", 0.163, 0.217, 0.0215, "steel", flip=True, width=0.0165))
    # Hinge arm down to the frame knuckles.
    arm = prism("arm", [(0.046, 0.027), (0.046, 0.008), (0.0485, 0.0005), (0.052, -0.0040), (0.0565, -0.0025), (0.0605, 0.004),
                        (0.068, 0.023), (0.068, 0.027)], 0.0172, "steel", bevel=0.0009)
    bits.append(kit.cut(arm, hole_through("hp", (0, HINGE[1], HINGE[2]), 0.0024, "x", 0.04)))
    bits.append(cyl("arbor", (0, 0.034, ZC), (0, 0.054, ZC), 0.0029, "bright", segs=20, bevel=0.0003))
    # Breech shoulder joining strap, barrel and lug above the cylinder front.
    bits.append(block("shoulder", (0, 0.0475, 0.047), (0.0235, 0.010, 0.033), "steel", bevel=0.0015, segs=3))
    # Top strap over the cylinder, matted on top.
    strap = prism("strap", [(-0.0165, 0.0555), (0.050, 0.0555), (0.050, 0.064), (-0.0125, 0.064), (-0.0165, 0.0605)], 0.022, "steel",
                  bevel=0.001)
    strap = kit.cut(strap, block("chan", (0, 0.017, 0.0645), (0.0062, 0.05, 0.0024), "steel", bevel=0))
    bits += [strap, label("TOP-BREAK  .455  6 SHOT", (-0.011, 0.018, 0.0598), 0.0028, "bright")]
    # Ventilated rib: see-through vents and cross serrations along the top.
    rib = prism("rib", [(0.046, 0.0545), (MUZZLE_Y - 0.002, 0.0545), (MUZZLE_Y, 0.0610), (MUZZLE_Y - 0.002, 0.064), (0.046, 0.064)], 0.0095,
                "steel", bevel=0.0006)
    rib = cutx(rib, *mlok("vent", 0.054, 0.214, 8, 0.0587, 0.0, depth=0.02, h=0.0038))
    rib = kit.cut(rib, *slots("ser", 0.050, 0.200, 40, 0.0633, 0.0655, -0.006, 0.006))
    bits.append(rib)
    # Latch thumbpiece on the strap's rear: checkered, a pivot screw and a red button.
    latch = prism("latch", [(-0.0165, 0.0555), (-0.0125, 0.064), (-0.0140, 0.0685), (-0.0200, 0.0705), (-0.0265, 0.0690), (-0.0280, 0.0655),
                            (-0.0235, 0.0605), (-0.0205, 0.0565)], 0.020, "bright", bevel=0.0008, segs=3)
    latch = kit.cut(latch, *slots("lc", -0.0262, -0.0150, 7, 0.0682, 0.0742, -0.011, 0.011))
    bits += [latch, screw((-0.0103, -0.0185, 0.0625), "-x", 0.0019), screw((0.0103, -0.0185, 0.0625), "x", 0.0019),
             cyl("btn", (-0.0102, -0.0238, 0.0655), (-0.0114, -0.0238, 0.0655), 0.0017, "red", segs=14, bevel=0.0002)]
    for b in bits:
        g.add(b, "breech")

    # Iron sights (vanish under an optic): ramp blade with a red insert, adjustable notch rear sight.
    blade = prism("blade", [(0.203, 0.0638), (0.2215, 0.0638), (0.2215, 0.0675), (0.2175, 0.0735), (0.2125, 0.0735)], 0.0036, "steel",
                  bevel=0.0003)
    blade = kit.cut(blade, block("bc", (0, 0.207, 0.0638), (0.006, 0.004, 0.003), "steel", bevel=0))
    insert = block("ins", (0, 0.2128, 0.0715), (0.0038, 0.0012, 0.0032), "red", bevel=0.0001)
    rear = block("rear", (0, -0.0045, 0.0665), (0.0135, 0.0125, 0.0052), "steel", bevel=0.0006)
    rear = kit.cut(rear, block("notch", (0, -0.0045, 0.0695), (0.0032, 0.02, 0.0052), "steel", bevel=0),
                   *slots("rs", -0.0105, -0.0085, 2, 0.068, 0.0702, -0.0068, 0.0068))
    dots = [cyl("dot", (s * 0.0042, -0.0109, 0.0678), (s * 0.0042, -0.0112, 0.0678), 0.0009, "lamp", segs=10, bevel=0) for s in (-1, 1)]
    irons = join([blade, insert, rear, *dots, screw((0, -0.0045, 0.0692), "z", 0.0013, head=0.0006),
                  screw((-0.0068, -0.002, 0.0665), "-x", 0.0011, head=0.0006)], "att.optic.irons")
    g.add(named(irons, "att.optic.irons"), "breech")
    g.socket("muzzle", (0, MUZZLE_Y + 0.0002, BORE), "breech")


def cylinder(g):
    """Fluted six-shot cylinder with bolt notches, chamfered chamber mouths, rim counterbores and a
    star extractor recess; the extractor and six rounds sit in it."""
    c = (0, ZC)
    body = lathe("cyl", [(CY0, 0), (CY0, CYL_R - 0.0008), (CY0 + 0.0008, CYL_R), (CY1 - 0.0024, CYL_R), (CY1, CYL_R - 0.0022), (CY1, 0)],
                 c, "steel", segs=60, bevel=0.0003)
    ch = chambers()
    body = kit.cut(body, *[cyl("ch", (x, CY0 - 0.004, z), (x, CY1 + 0.004, z), CH_R, "steel", segs=28, bevel=0) for x, z in ch])
    body = kit.cut(body, *[cyl("cb", (x, CY0 - 0.002, z), (x, CY0 + 0.0012, z), 0.0066, "steel", segs=28, bevel=0) for x, z in ch])
    body = cutx(body, cyl("rec", (0, CY0 - 0.002, ZC), (0, -0.0010, ZC), 0.0112, "steel", segs=40, bevel=0),
                *[cyl("mouth", (x, CY1 + 0.0008, z), (x, CY1 - 0.0016, z), 0.0071, "steel", r1=CH_R - 0.0002, segs=28, bevel=0) for x, z in ch],
                cyl("ah", (0, 0.030, ZC), (0, CY1 + 0.002, ZC), 0.0032, "steel", segs=16, bevel=0))
    flutes = []
    for k in range(6):
        a = math.radians(120 + 60 * k)
        flutes.append(capsule("fl", 0.0075, 0.0345, 0.0042, (0.0247 * math.cos(a), ZC + 0.0247 * math.sin(a)), segs=16))
    body = kit.cut(body, *flutes)
    notches = []
    for k in range(6):
        n = block("bn", (0, 0.0045, ZC + CYL_R), (0.0032, 0.0052, 0.0024), "steel", bevel=0)
        lead = block("bl", (0, 0.0105, ZC + CYL_R + 0.0004), (0.0016, 0.0085, 0.0016), "steel", bevel=0)
        notches += [roty(n, c, 60 * k), roty(lead, c, 60 * k)]
    body = cutx(body, *notches)
    g.add(body, "cylinder")

    # Star extractor: a hub disc with the chambers bitten out of it, a hex ratchet and its stem.
    star = cyl("star", (0, -0.0028, ZC), (0, -0.0010, ZC), 0.0108, "bright", segs=40, bevel=0.0002)
    star = kit.cut(star, *[cyl("sc", (x, -0.004, z), (x, 0.0, z), CH_R, "steel", segs=24, bevel=0) for x, z in ch])
    hub = cyl("hub", (0, -0.0045, ZC), (0, -0.0028, ZC), 0.0042, "bright", segs=6, bevel=0.0002)
    teeth = [roty(block("tooth", (0, -0.0040, ZC + 0.0046), (0.0022, 0.0010, 0.0016), "bright", bevel=0.0001), c, 60 * k + 30)
             for k in range(6)]
    stem = cyl("stem", (0, -0.0010, ZC), (0, 0.024, ZC), 0.0030, "bright", segs=16)
    g.add(join([star, hub, *teeth, stem], "extractor"), "extractor")

    # Six cartridges: rim, case, primer and a jacketed bullet just shy of the chamber mouth.
    rounds = []
    for x, z in ch:
        rounds.append(lathe("rim", [(CY0, 0), (CY0, 0.0058), (CY0 + 0.0002, 0.0064), (CY0 + 0.0012, 0.0064), (CY0 + 0.0012, 0)], (x, z), "brass",
                            segs=24, bevel=0))
        rounds.append(cyl("case", (x, CY0 + 0.0012, z), (x, 0.029, z), 0.0056, "brass", segs=20, bevel=0))
        rounds.append(lathe("bullet", [(0.029, 0), (0.029, 0.0055), (0.0335, 0.0055), (0.0365, 0.0046), (0.0386, 0.0031), (0.0394, 0.0016),
                                       (0.0394, 0)], (x, z), "copper", segs=20, bevel=0))
        rounds.append(cyl("primer", (x, CY0 - 0.00015, z), (x, CY0 + 0.0006, z), 0.0021, "bright", segs=14, bevel=0))
        rounds.append(ring("hs", (x, CY0 - 0.00005, z), (0, 1, 0), 0.0047, 0.0039, 0.0002, "copper", segs=24))
    g.add(join(rounds, "rounds"), "rounds")


def hammer_trigger(g):
    # Hammer, modelled fallen and turned back to its cocked rest pose. Checkered spur, bright steel.
    hp = [(-0.024, 0.018), (-0.0205, 0.032), (-0.0205, 0.050), (-0.0235, 0.0535), (-0.031, 0.0565), (-0.039, 0.0605), (-0.045, 0.0640),
          (-0.0495, 0.0648), (-0.0507, 0.0618), (-0.0450, 0.0565), (-0.0395, 0.0490), (-0.0365, 0.0370), (-0.0350, 0.0200), (-0.031, 0.0165)]
    ham = prism("hammer", hp, 0.0084, "bright", bevel=0.0005)
    spur = prism("spur", [(-0.031, 0.0566), (-0.039, 0.0606), (-0.045, 0.0641), (-0.0496, 0.0649), (-0.0508, 0.0617), (-0.046, 0.0598),
                          (-0.039, 0.0566), (-0.033, 0.0540)], 0.0112, "bright", bevel=0.0006)
    ham = join([ham, spur], "hammer")
    chk = [block("hc", (0, y, 0.0565 + (-0.031 - y) * 0.432 + 0.0019), (0.012, 0.0007, 0.004), "steel", bevel=0, rot=-23)
           for y in [-0.0325 - i * 0.0023 for i in range(7)]]
    chk += [block("hl", (sx, -0.040, 0.0604), (0.0006, 0.024, 0.0016), "steel", bevel=0, rot=-23) for sx in (-0.0015, 0.0015)]
    ham = cutx(ham, *chk, hole_through("hh", (0, -0.029, 0.040), 0.0024, "x", 0.02))
    nose = cyl("nose", (0, -0.0212, BORE), (0, -0.0195, BORE), 0.0012, "bright", segs=10, bevel=0)
    ham = join([ham, nose], "hammer")
    rotx(ham, HAMMER, COCK)
    g.add(ham, "hammer")
    # Trigger: a curved bright blade with a grooved face.
    trig = prism("trigger", [(0.004, 0.003), (0.0105, 0.003), (0.0125, -0.008), (0.0108, -0.018), (0.0055, -0.026), (0.0015, -0.0265),
                             (0.0045, -0.017), (0.0055, -0.007)], 0.0062, "bright", bevel=0.0005)
    trig = kit.cut(trig, *[block("tg", (0, 0.0118 - i * 0.0006, -0.010 - i * 0.0028), (0.009, 0.0016, 0.0007), "steel", bevel=0)
                           for i in range(5)])
    g.add(trig, "trigger")


def gunsmith(g):
    """All eight parts plus the bare gun's own pieces. Optic: red dot or long-eye-relief scope clamped on
    the rib. Muzzle: ported compensator or suppressor in place of the crown cap. Grip slot: weapon light or
    laser on the underlug rail (rubber rail cover when empty). Stock slot: grip variants (see grips())."""
    top = (0, 0.085, 0.064)
    optic_reddot(g, top, "breech")
    optic_scope(g, (0, 0.105, 0.064), "breech", length=0.15, mag=0.017)
    g.socket("optic", top, "breech")
    m = (0, MUZZLE_Y, BORE)
    # Bare: knurled crown cap.
    cap = tube("att.muzzle.bare", (0, MUZZLE_Y - 0.0005, BORE), (0, MUZZLE_Y + 0.0045, BORE), 0.0099, 0.0062, "bright", segs=40)
    cap = kit.cut(cap, *[block("kn", (0.0099 * math.cos(math.radians(a)), MUZZLE_Y + 0.0025, BORE + 0.0099 * math.sin(math.radians(a))),
                               (0.0012, 0.006, 0.0012), "steel", bevel=0) for a in range(0, 360, 15)])
    g.add(named(cap, "att.muzzle.bare"), "breech")
    # Compensator: follows the barrel's rib/lug silhouette, three top ports and two side ports a side.
    y0, y1 = MUZZLE_Y, MUZZLE_Y + 0.036
    comp = prism("att.muzzle.comp", [(y0, 0.0215), (y1 - 0.004, 0.0215), (y1, 0.027), (y1, 0.0595), (y1 - 0.004, 0.064), (y0, 0.064)], 0.0205,
                 "steel", bevel=0.0012, segs=3)
    comp = kit.cut(comp, hole_through("cb", (0, (y0 + y1) / 2, BORE), 0.0066, "y", 0.05),
                   *[block("tp", (0, y0 + 0.008 + i * 0.0095, 0.058), (0.0105, 0.0042, 0.016), "steel", bevel=0) for i in range(3)],
                   *[block("sp", (0, y0 + 0.012 + i * 0.012, BORE - 0.002), (0.03, 0.0045, 0.0085), "steel", bevel=0) for i in range(2)])
    comp = join([comp, block("cr", (-0.0104, y0 + 0.004, 0.030), (0.0012, 0.004, 0.012), "red", bevel=0.0002),
                 screw((-0.0103, y0 + 0.004, 0.0565), "-x", 0.0016), screw((0.0103, y0 + 0.004, 0.0565), "x", 0.0016)], "att.muzzle.comp")
    g.add(named(comp, "att.muzzle.comp"), "breech")
    # Suppressor on a lug adapter.
    sl = 0.165
    supp = tube("att.muzzle.supp", (0, y0 + 0.012, BORE), (0, y0 + sl, BORE), 0.0205, 0.0062, "black", segs=40)
    adapter = prism("ad", [(y0, 0.0215), (y0 + 0.014, 0.0215), (y0 + 0.014, 0.064), (y0, 0.064)], 0.0195, "steel", bevel=0.0012, segs=3)
    adapter = kit.cut(adapter, hole_through("ab", (0, y0 + 0.007, BORE), 0.0066, "y", 0.03))
    collar = ring("collar", (0, y0 + 0.018, BORE), (0, 1, 0), 0.0215, 0.0062, 0.012, "steel", segs=40)
    endc = ring("endc", (0, y0 + sl - 0.003, BORE), (0, 1, 0), 0.0212, 0.0062, 0.006, "steel", segs=40)
    grooves = [ring("gr", (0, y0 + 0.05 + i * 0.008, BORE), (0, 1, 0), 0.0211, 0.0198, 0.003, "steel", segs=40) for i in range(5)]
    supp = join([supp, adapter, collar, endc, *grooves, label(MAKER, (-0.0206, y0 + 0.115, BORE), 0.0036, "bright"),
                 label("WARDEN", (-0.0206, y0 + 0.115, BORE - 0.0065), 0.0030, "red")], "att.muzzle.supp")
    g.add(named(supp, "att.muzzle.supp"), "breech")
    # Under-rail: rubber cover, weapon light (grip.vertical), laser (grip.angled).
    rz = 0.0215 - 0.0076
    under = (0, 0.190, rz)
    cover = block("att.grip.standard", (0, 0.190, rz + 0.0018), (0.018, 0.052, 0.0058), "rubber", bevel=0.0012, segs=3)
    cover = kit.cut(cover, *slots("cv", 0.170, 0.210, 6, rz - 0.002, rz + 0.0002, -0.012, 0.012))
    g.add(named(cover, "att.grip.standard"), "breech")
    lz = rz - 0.0115
    light = cyl("att.grip.vertical", (0, 0.166, lz), (0, 0.214, lz), 0.0098, "black", segs=36, bevel=0.0006)
    clamp = block("clamp", (0, 0.190, rz - 0.0005), (0.0215, 0.036, 0.0075), "black", bevel=0.0012)
    clamp = kit.cut(clamp, block("ct", (0, 0.190, rz + 0.0005), (0.0168, 0.04, 0.0045), "steel", bevel=0))
    bezel = tube("bezel", (0, 0.212, lz), (0, 0.226, lz), 0.0114, 0.0086, "steel", segs=36)
    bezel = kit.cut(bezel, *[block("bz", (0.0114 * math.cos(math.radians(a)), 0.224, lz + 0.0114 * math.sin(math.radians(a))),
                                   (0.003, 0.006, 0.003), "steel", bevel=0) for a in range(0, 360, 30)])
    fins = [ring("fin", (0, 0.172 + i * 0.006, lz), (0, 1, 0), 0.0106, 0.0096, 0.0028, "black", segs=36) for i in range(5)]
    light = join([light, clamp, bezel, *fins, cyl("lens", (0, 0.2205, lz), (0, 0.2215, lz), 0.0088, "lamp", segs=36, bevel=0),
                  cyl("led", (0, 0.2195, lz), (0, 0.2215, lz), 0.0032, "bright", segs=16, bevel=0),
                  cyl("sw", (-0.0094, 0.170, lz + 0.002), (-0.0118, 0.170, lz + 0.002), 0.0026, "red", segs=16),
                  screw((-0.0108, 0.190, rz - 0.0005), "-x", 0.0016)], "att.grip.vertical")
    g.add(named(light, "att.grip.vertical"), "breech")
    lb = block("att.grip.angled", (0, 0.191, rz - 0.0105), (0.0175, 0.046, 0.0145), "black", bevel=0.0016, segs=3)
    lb = kit.cut(lb, block("lw", (0, 0.2145, rz - 0.0125), (0.010, 0.004, 0.007), "steel", bevel=0),
                 *slots("lr", 0.172, 0.200, 6, rz - 0.019, rz - 0.0165, -0.012, 0.012))
    laser = join([lb, block("lclamp", (0, 0.190, rz - 0.0012), (0.0205, 0.030, 0.006), "black", bevel=0.001),
                  tube("em", (0, 0.2125, rz - 0.0125), (0, 0.2165, rz - 0.0125), 0.0034, 0.0022, "steel", segs=20),
                  cyl("beam", (0, 0.2135, rz - 0.0125), (0, 0.2145, rz - 0.0125), 0.0022, "reticle", segs=16, bevel=0),
                  screw((-0.0088, 0.182, rz - 0.010), "-x", 0.0018), screw((0, 0.182, rz - 0.018), "-z", 0.0018),
                  block("lred", (-0.0089, 0.200, rz - 0.0065), (0.0006, 0.016, 0.002), "red", bevel=0),
                  label("LASER", (-0.0089, 0.199, rz - 0.0115), 0.0030, "bright")], "att.grip.angled")
    g.add(named(laser, "att.grip.angled"), "breech")
    g.socket("under", under, "breech")


# --------------------------------------------------------------------------------------- clips

def clips(g):
    F1 = 1 / 60  # one frame: the cylinder's six-fold symmetry hides a 60-degree snap
    z = (0, 0, 0)
    g.clip("idle", 1.0, {})
    g.clip("fire", 0.25, {
        "root": [(0, z, z), (0.035, (0, -0.024, 0.011), (17, 0, 2.5)), (0.11, (0, -0.007, 0.004), (5, 0, 0.8)), (0.25, z, z)],
        "hammer": [(0, z, z), (0.012, z, (-COCK, 0, 0)), (0.10, z, (-COCK, 0, 0)), (0.21, z, z)],
        "trigger": [(0, z, z), (0.01, z, (-14, 0, 0)), (0.12, z, (-14, 0, 0)), (0.20, z, z)],
        "cylinder": [(0, z, z), (F1, z, (0, -60, 0)), (0.10, z, (0, -60, 0)), (0.21, z, z)],
    })
    g.clip("reload", 2.2, {
        "root": [(0, z, z), (0.25, (0.01, 0.0, 0.025), (18, 22, 8)), (0.42, (0.01, 0.0, 0.03), (16, 24, 8)),
                 (0.53, (0.01, -0.004, 0.036), (24, 24, 9)), (0.75, (0.01, 0.0, 0.03), (14, 24, 8)),
                 (1.0, (0.0, 0.0, 0.03), (-12, 26, 10)), (1.5, (0.0, 0.0, 0.03), (-14, 26, 10)),
                 (1.72, (0.0, -0.004, 0.02), (14, 8, 2)), (1.9, (0, 0, 0.006), (3, 2, 0)), (2.2, z, z)],
        "breech": [(0, z, z), (0.22, z, z), (0.27, z, (-4, 0, 0)), (0.45, z, (-55, 0, 0)), (1.6, z, (-55, 0, 0)), (1.74, z, (2, 0, 0)),
                   (1.8, z, z)],
        "extractor": [(0, z, z), (0.47, z, z), (0.52, (0, -0.014, 0), z), (0.62, (0, -0.014, 0), z), (0.70, z, z)],
        "rounds": [(0, z, z), (0.47, z, z), (0.52, (0, -0.014, 0), z), (0.58, (-0.006, -0.05, 0.004), (-10, 0, 8)),
                   (0.72, (-0.06, -0.09, -0.06), (-60, 0, -40)), (0.90, (-0.20, 0.10, -0.45), (-150, 0, -90)),
                   (0.94, (-0.15, 0.10, -0.40), (-20, 0, 0)), (1.08, (-0.06, 0.0, -0.10), (-8, 0, 0)),
                   (1.20, (-0.02, -0.05, -0.01), z), (1.27, (0, -0.03, 0), z), (1.43, (0, -0.003, 0), z), (1.50, z, z)],
    })
    g.clip("draw", 0.45, {
        "root": [(0, (0, -0.04, -0.12), (-55, 0, 10)), (0.32, (0, 0.004, 0.004), (4, 0, 0)), (0.45, z, z)],
        "hammer": [(0, z, (-COCK, 0, 0)), (0.26, z, (-COCK, 0, 0)), (0.36, z, (3, 0, 0)), (0.42, z, z)],
        "cylinder": [(0, z, z), (0.26, z, z), (0.27, z, (0, -60, 0)), (0.36, z, z)],
    })
    g.clip("inspect", 2.8, {
        "root": [(0, z, z), (0.45, (-0.03, 0.02, 0.03), (10, -32, 22)), (0.9, (-0.03, 0.02, 0.035), (12, -36, 26)),
                 (1.1, (-0.01, 0.0, 0.04), (16, 18, 6)), (1.85, (-0.01, 0.0, 0.04), (18, 22, 8)),
                 (2.25, (0.02, 0.0, 0.02), (-6, 28, -16)), (2.8, z, z)],
        "breech": [(0, z, z), (1.05, z, z), (1.25, z, (-42, 0, 0)), (1.95, z, (-42, 0, 0)), (2.08, z, (2, 0, 0)), (2.14, z, z)],
        "cylinder": [(0, z, z), (1.3, z, z), (1.3 + F1, z, (0, -360, 0)), (1.42, z, (0, -170, 0)), (1.65, z, (0, -40, 0)), (1.85, z, z)],
    })


SHOW = ("att.optic.irons", "att.muzzle.bare", "att.grip.standard", "att.stock.standard")

SPEC = {"build": build, "length": (0.27, 0.36), "tris": (20000, 70000),
        "bones": ["root", "breech", "cylinder", "extractor", "rounds", "hammer", "trigger"],
        "sockets": ["muzzle", "optic", "under", "stock", "scope.eye", "reddot.lens"],
        "attachments": SLOT_ATTS + list(SHOW),
        "parts": {"mesh.root": "root", "mesh.breech": "breech", "mesh.cylinder": "cylinder", "mesh.extractor": "extractor",
                  "mesh.rounds": "rounds", "mesh.hammer": "hammer", "mesh.trigger": "trigger"},
        "moves": {"fire": ["root", "hammer", "trigger", "cylinder"], "reload": ["root", "breech", "extractor", "rounds"],
                  "draw": ["root", "hammer"], "inspect": ["root", "breech", "cylinder"]},
        "view": {"cam": (-0.46, 0.0, 0.14), "look": (0, 0.068, -0.012), "lens": 50, "show": SHOW}}
