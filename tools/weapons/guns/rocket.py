"""RR-1 Skyhammer: a four-round shoulder rocket launcher. Olive polymer furniture, black steel, red
accents; a see-through launch tube with a ribbed flared muzzle ring, a swing-aside venturi breech
cover, heat shields, a carry handle with an enclosed reflex sight and a flip-up range plate, and a
round counter strip on the left."""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import kit
from kit import block, cut, cyl, dimples, hole_through, join, pin, prism, rail, ring, slots, tube
from parts import MAKER, common_clips

ZC = 0.088          # tube axis height above the trigger
R_OUT = 0.035       # launch tube outer radius
R_IN = 0.031        # bore
Y_REAR = -0.30      # tube body ends (the breech ring and front ring sit past these)
Y_FRONT = 0.495


# ------------------------------------------------------------------------------- local helpers

def lathe(name, prof, material, segs=48, closed=True, bevel=0.0006, bsegs=2):
    """Revolve a (y, r) profile about the tube axis. A closed profile makes a hollow ring; an open one
    that starts and ends on the axis (r 0) makes a solid."""
    bm = bmesh.new()
    rings = []
    for y, r in prof:
        if r < 1e-6:
            rings.append([bm.verts.new((0.0, y, ZC))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / segs), y, ZC + r * math.sin(2 * math.pi * i / segs)))
                          for i in range(segs)])
    n = len(rings)
    for k in range(n if closed else n - 1):
        a, b = rings[k], rings[(k + 1) % n]
        for i in range(segs):
            j = (i + 1) % segs
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                bm.faces.new((a[0], b[j], b[i]))
            elif len(b) == 1:
                bm.faces.new((a[i], a[j], b[0]))
            else:
                bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return kit._obj(name, bm, material, bevel, bsegs)


def arc_panel(name, y0, y1, r0, r1, a0, a1, material, bevel=0.0008):
    """A curved shell section around the tube: radii r0..r1, angles a0..a1 degrees (0 = right, 90 = top,
    180 = left), from y0 to y1."""
    n = max(4, int(abs(a1 - a0) / 6))
    ang = [math.radians(a0 + (a1 - a0) * i / n) for i in range(n + 1)]
    pts = [(r1 * math.cos(a), ZC + r1 * math.sin(a)) for a in ang] + [(r0 * math.cos(a), ZC + r0 * math.sin(a)) for a in reversed(ang)]
    bm = bmesh.new()
    face = bm.faces.new([bm.verts.new((x, y0, z)) for x, z in pts])
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, vec=(0, y1 - y0, 0), verts=[e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return kit._obj(name, bm, material, bevel, 2)


def radial(obj, a, y, r):
    """Move a part built at the origin with its +X pointing outward to angle `a` around the tube."""
    ar = math.radians(a)
    obj.data.transform(Matrix.Translation((r * math.cos(ar), y, ZC + r * math.sin(ar))) @ Matrix.Rotation(-ar, 4, "Y"))
    return obj


def rblock(a, y, r, rad, ylen, tang, material="steel", bevel=0.0):
    return radial(block("rb", (0, 0, 0), (rad, ylen, tang), material, bevel=bevel), a, y, r)


def rscrew(a, y, r_surf, rs=0.0021):
    return radial(screw((0, 0, 0), "x", rs), a, y, r_surf + 0.0002)


def rivet(a, y, r_surf, material="steel"):
    return radial(cyl("rivet", (-0.0006, 0, 0), (0.0011, 0, 0), 0.0016, material, r1=0.0009, segs=8, bevel=0), a, y, r_surf)


def flat_label(text, at, size, material, rot=(0.0, 0.0, math.pi / 2), depth=0.0003):
    """Raised lettering; by default on an upward face reading toward the muzzle, top toward the left.
    Glyph curves are kept coarse so the stencils stay inside the triangle budget."""
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = depth
    cu.resolution_u = 1
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    o = bpy.data.objects.new("label", cu)
    bpy.context.scene.collection.objects.link(o)
    o.location = at
    o.rotation_euler = rot
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    mw = o.matrix_world.copy()
    bpy.data.objects.remove(o, do_unlink=True)
    me.transform(mw)
    me.materials.clear()
    me.materials.append(kit.mat(material))
    out = bpy.data.objects.new("label", me)
    bpy.context.scene.collection.objects.link(out)
    out["bevel"] = 0.0
    return out


def label(text, at, size, material, side=-1, depth=0.0003):
    """kit.label with coarse glyphs (same placement: a side face, left by default)."""
    return flat_label(text, at, size, material, (math.pi / 2, 0, -math.pi / 2 if side < 0 else math.pi / 2), depth)


def prebevel(o):
    """Bevel a part now, before fine cuts, so stippling and slots are not bevelled into thousands of faces."""
    kit.apply_modifiers(o)
    o["bevel"] = 0.0
    return o


def screw(at, axis="x", r=0.0022, material="steel", head=0.0012):
    """A lighter socket-head screw than kit.screw (12 sides, one bevel segment)."""
    sgn = -1 if axis.startswith("-") else 1
    a = Vector({"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis[-1]]) * sgn
    at = Vector(at)
    s = prebevel(cyl("screw", at - a * head / 2, at + a * head / 2, r, material, segs=10, bevel=0.00025, bsegs=1))
    hexa = cyl("hex", at + a * (head / 2 - 0.0006), at + a * (head / 2 + 0.001), r * 0.45, material, segs=6, bevel=0)
    return cut(s, hexa, solver="FLOAT")


def assemble(parts, name):
    """Join parts into one mesh, bevelling each with its own width first. (kit.join keeps only the first
    part's bevel setting, which Gun.finish would then re-apply to the whole joined mesh, labels and
    already-bevelled parts included, roughly doubling the triangle count.)"""
    parts = [p for p in parts if p is not None]
    for p in parts:
        kit.apply_modifiers(p)
        p["bevel"] = 0.0
    o = join(parts, name)
    o["bevel"] = 0.0
    return o


def cutx(target, *cutters):
    """kit.cut for cutters that overlap each other (e.g. a slot plus its rounded ends). kit.cut joins
    the cutters into one self-intersecting mesh and the EXACT solver without self-intersection
    handling returns an empty result, so this turns that handling on."""
    cutter = join(list(cutters), "_cutter")
    mod = target.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.use_self = True
    mod.object = cutter
    kit._apply(target, mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def band(y, width=0.016, material="steel", lug=True):
    """A clamp band around the tube with a bolted lug on the left and rivets on top."""
    parts = [ring("band", (0, y, ZC), (0, 1, 0), R_OUT + 0.0028, R_OUT - 0.0006, width, material, segs=36)]
    parts[0]["segs"] = 1
    if lug:
        parts.append(block("lug", (-R_OUT - 0.0045, y, ZC - 0.006), (0.008, width * 0.8, 0.012), material, bevel=0.0008))
        parts.append(screw((-R_OUT - 0.0088, y, ZC - 0.006), "-x", 0.0022))
    parts += [rivet(a, y, R_OUT + 0.0028) for a in (60, 90, 120)]
    return parts


def shield(y0, y1, a0, a1, cols, rows_a):
    """A slotted heat shield standing off the tube, screwed down at its corners and edges."""
    p = prebevel(arc_panel("shield", y0, y1, R_OUT - 0.0005, R_OUT + 0.0032, a0, a1, "black", bevel=0.0007))
    cutters = []
    for i in range(cols):
        y = y0 + (y1 - y0) * (i + 0.5) / cols
        for k in range(rows_a):
            a = a0 + 9 + (a1 - a0 - 18) * k / max(1, rows_a - 1)
            cutters.append(rblock(a, y, R_OUT + 0.002, 0.008, (y1 - y0) / cols * 0.62, 0.0034))
    p = cut(p, *cutters)
    out = [p]
    for a in (a0 + 4, a1 - 4):
        for y in (y0 + 0.007, y1 - 0.007):
            out.append(rscrew(a, y, R_OUT + 0.0032, 0.0019))
    # Stand-off feet visible under the edges.
    for y in (y0 + 0.02, y1 - 0.02):
        out.append(rblock(a0 + 1.5, y, R_OUT + 0.0012, 0.0034, 0.012, 0.004, "steel", bevel=0.0003))
    return out


# --------------------------------------------------------------------------------------- build

def build():
    """Skyhammer: tube, breech cover, rocket, furniture, sights, counter strip, clips."""
    z1 = ZC + 0.078   # carry handle top
    g = begin_gun(z1)
    root = []

    # ---------------------------------------------------------------------- launch tube
    t = tube("tube", (0, Y_REAR, ZC), (0, Y_FRONT, ZC), R_OUT, R_IN, "olive", segs=48)
    # Inspection windows on the left show the loaded rocket.
    wl = [(0.33, 0.015), (0.375, 0.015), (0.42, 0.015), (0.459, 0.007)]   # (centre, half length of the straight part)
    wins = [rblock(188, y, R_OUT - 0.002, 0.012, 2 * h, 0.010) for y, h in wl]
    wins += [radial(cyl("wc", (-0.006, s * h, 0), (0.006, s * h, 0), 0.005, "steel", segs=14, bevel=0), 188, y, R_OUT - 0.002)
             for y, h in wl for s in (-1, 1)]
    t = cutx(t, *wins)
    root.append(t)
    # Red front band, ribbed flared muzzle ring, rivets and longitudinal gussets.
    root.append(ring("redband", (0, 0.481, ZC), (0, 1, 0), R_OUT + 0.0009, R_OUT - 0.001, 0.008, "red", segs=36))
    front = [(0.487, 0.0316), (0.487, 0.0372), (0.490, 0.0386), (0.497, 0.0386), (0.499, 0.0406), (0.505, 0.0406), (0.507, 0.0386),
             (0.511, 0.0386), (0.513, 0.0406), (0.519, 0.0406), (0.521, 0.0386), (0.525, 0.0386), (0.527, 0.0412), (0.534, 0.0412),
             (0.537, 0.0398), (0.549, 0.0452), (0.556, 0.0466), (0.5585, 0.0446), (0.5585, 0.0405), (0.548, 0.0352), (0.530, 0.0322)]
    root.append(lathe("front", front, "steel", segs=40, bevel=0.0004, bsegs=1))
    root += [rivet(a, 0.4935, 0.0386) for a in range(15, 360, 30)]
    for a in range(0, 360, 45):
        gu = prism("gusset", [(0.537, 0.0), (0.552, 0.0), (0.552, 0.004), (0.537, 0.0005)], 0.0018, "steel", bevel=0.0002)
        gu.data.transform(Matrix.Rotation(math.pi / 2, 4, "Y"))  # profile height -> outward
        root.append(radial(gu, a, 0, 0.0398))
    # Breech ring at the rear, with the fixed hinge knuckle and latch catch.
    breech = [(-0.326, 0.0312), (-0.326, 0.0395), (-0.323, 0.0412), (-0.302, 0.0412), (-0.299, 0.0392), (-0.290, 0.0378),
              (-0.287, 0.0356), (-0.287, 0.0312)]
    root.append(lathe("breech", breech, "steel", segs=40, bevel=0.0004))
    root += [rivet(a, -0.3125, 0.0412) for a in range(0, 360, 30) if a not in (180, 0)]
    root.append(cyl("knuckle", (-0.047, -0.326, ZC - 0.0062), (-0.047, -0.326, ZC + 0.0062), 0.0045, "steel", segs=16))
    root.append(block("leaf", (-0.0432, -0.3205, ZC), (0.008, 0.011, 0.012), "steel", bevel=0.0006))
    root.append(cyl("hpin", (-0.047, -0.326, ZC - 0.0215), (-0.047, -0.326, ZC + 0.0215), 0.0017, "bright", segs=12))
    root.append(block("catch", (0.0432, -0.319, ZC), (0.008, 0.012, 0.014), "steel", bevel=0.0007))
    root.append(screw((0.0475, -0.319, ZC), "x", 0.0018))

    # ---------------------------------------------------------------------- bands, shields, plates
    for y, w in ((-0.200, 0.016), (-0.115, 0.016), (0.140, 0.016), (0.280, 0.026)):
        root += band(y, w)
    root += shield(0.153, 0.266, 62, 168, 4, 6)
    root += shield(0.297, 0.474, 58, 166, 5, 6)
    root += shield(-0.286, -0.212, 52, 200, 2, 9)
    root += shield(0.153, 0.266, -42, 30, 3, 3)
    root += shield(0.297, 0.474, -42, 30, 4, 3)
    # Data plate on the left under the first shield.
    xp = -R_OUT - 0.0012
    plate = block("plate", (xp, 0.21, ZC - 0.009), (0.005, 0.104, 0.018), "black", bevel=0.0008)
    root += [plate, label("RR-1  SKYHAMMER", (xp - 0.0026, 0.21, ZC - 0.0055), 0.0062, "bright"),
             label("84MM HE/AT  4 RD", (xp - 0.0026, 0.21, ZC - 0.0135), 0.0029, "bright")]
    root += [screw((xp - 0.0025, y, ZC - 0.009), "-x", 0.0017) for y in (0.163, 0.257)]
    # Backblast warning plate on the left at the rear.
    hz = block("hazard", (xp, -0.158, ZC - 0.006), (0.005, 0.064, 0.022), "hazard", bevel=0.0008)
    stripes = [block("stripe", (xp - 0.0026, -0.186 + i * 0.0072, ZC - 0.0145), (0.0008, 0.0032, 0.004), "black", bevel=0, rot=40) for i in range(8)]
    root += [hz, *stripes, label("DANGER", (xp - 0.0026, -0.158, ZC + 0.0005), 0.0058, "black"),
             label("BACKBLAST 30M", (xp - 0.0026, -0.158, ZC - 0.0065), 0.0034, "black")]
    root += [rivet(180, y, R_OUT + 0.0038) for y in (-0.1875, -0.1285)]
    # Right side markings for inspect.
    root.append(label(MAKER, (R_OUT + 0.0001, 0.06, ZC + 0.006), 0.0045, "black", side=1))
    # Top stencil between the carry handle and the rear shield.
    root.append(flat_label("LIVE", (0, -0.17, ZC + R_OUT - 0.0001), 0.007, "red", rot=(0, 0, math.pi / 2)))

    # ---------------------------------------------------------------------- round counter (left)
    xs = -R_OUT - 0.0022
    strip = block("strip", (xs, -0.005, ZC + 0.002), (0.007, 0.104, 0.021), "black", bevel=0.0012, segs=3)
    strip = cut(strip, *[cyl("well", (xs - 0.006, -0.038 + i * 0.022, ZC + 0.0045), (xs - 0.002, -0.038 + i * 0.022, ZC + 0.0045), 0.0036,
                             "steel", segs=16, bevel=0) for i in range(4)])
    root.append(strip)
    for i in range(4):
        y = -0.038 + i * 0.022
        root.append(cyl("lamp", (xs - 0.0028, y, ZC + 0.0045), (xs - 0.0046, y, ZC + 0.0045), 0.003, "lamp", segs=12, bevel=0.0003))
        root.append(ring("bezel", (xs - 0.0042, y, ZC + 0.0045), (1, 0, 0), 0.0043, 0.0031, 0.0016, "steel", segs=12))
        root.append(label(str(i + 1), (xs - 0.0036, y, ZC - 0.0045), 0.0042, "bright"))
    root.append(label("RDY", (xs - 0.0036, -0.06, ZC + 0.0045), 0.0034, "red"))
    root.append(label("CHG", (xs - 0.0036, 0.05, ZC + 0.0045), 0.0034, "bright"))
    root += [screw((xs - 0.0036, y, ZC - 0.0045), "-x", 0.0014) for y in (-0.052, 0.042)]
    root.append(cyl("cable", (xs + 0.001, -0.056, ZC - 0.007), (xs + 0.004, -0.07, ZC - 0.026), 0.0022, "cord", segs=10))

    # ---------------------------------------------------------------------- fire control housing
    saddle = arc_panel("saddle", -0.100, 0.130, R_OUT - 0.0008, R_OUT + 0.0034, 196, 344, "olive", bevel=0.001)
    housing = prism("housing", [(-0.100, 0.060), (0.130, 0.060), (0.130, 0.034), (0.116, 0.014), (0.042, 0.002), (0.034, -0.003),
                                (-0.032, -0.003), (-0.072, 0.006), (-0.100, 0.024)], 0.036, "olive", bevel=0.0016, segs=2)
    hcuts = slots("hs", 0.060, 0.112, 6, 0.016, 0.040, -0.0195, -0.0165) + slots("hs", 0.060, 0.112, 6, 0.016, 0.040, 0.0165, 0.0195)
    hcuts += [block("pocket", (-0.0185, -0.052, 0.038), (0.004, 0.06, 0.02), "steel", bevel=0)]
    housing = cut(housing, *hcuts)
    root += [saddle, housing]
    # Inset firing module in the left pocket: arming switch, red arm button, markings.
    root.append(block("module", (-0.0172, -0.052, 0.038), (0.003, 0.056, 0.018), "black", bevel=0.0005))
    root.append(cyl("armbtn", (-0.0186, -0.068, 0.041), (-0.0212, -0.068, 0.041), 0.0042, "red", segs=20, bevel=0.0004))
    root.append(ring("armguard", (-0.0196, -0.068, 0.041), (1, 0, 0), 0.0058, 0.0046, 0.004, "steel", segs=20))
    sel = prism("selector", [(-0.044, 0.036), (-0.026, 0.040), (-0.024, 0.044), (-0.044, 0.044)], 0.0028, "steel", x=-0.0195, bevel=0.0003)
    root += [sel, cyl("selpivot", (-0.0185, -0.044, 0.040), (-0.0215, -0.044, 0.040), 0.0035, "steel", segs=16)]
    root.append(label("SAFE", (-0.0189, -0.035, 0.0316), 0.0032, "bright"))
    root.append(label("ARM", (-0.0189, -0.035, 0.0474), 0.0032, "red"))
    root.append(label("FIRE", (-0.0189, -0.068, 0.0322), 0.0026, "red"))
    root.append(label("MADE ON THE ISLAND", (-0.0181, 0.086, 0.009), 0.0026, "black"))
    root += [pin((0, y, z), "x", 0.0015, 0.039) for y, z in ((0.004, 0.006), (-0.014, 0.014), (0.098, 0.048))]
    root += [screw((s * 0.0182, y, z), "x" if s > 0 else "-x", 0.0021) for s in (-1, 1) for y, z in ((-0.088, 0.046), (0.122, 0.044), (0.02, 0.05))]
    # Right side battery cap.
    root.append(cyl("battery", (0.018, -0.05, 0.03), (0.0215, -0.05, 0.03), 0.0085, "black", segs=24, bevel=0.0006))
    root.append(cut(cyl("batknob", (0.0212, -0.05, 0.03), (0.0232, -0.05, 0.03), 0.006, "steel", segs=20),
                    block("slot", (0.0232, -0.05, 0.03), (0.002, 0.009, 0.0012), "steel", bevel=0)))

    # Trigger guard and pistol grip with stippled panels.
    guard = prism("guard", [(-0.016, -0.002), (0.030, -0.002), (0.034, -0.012), (0.031, -0.033), (0.024, -0.037), (-0.006, -0.037),
                            (-0.020, -0.030), (-0.024, -0.012)], 0.014, "black", bevel=0.0012)
    guard = cut(guard, prism("gh", [(-0.012, -0.004), (0.024, -0.004), (0.027, -0.012), (0.025, -0.030), (-0.004, -0.031), (-0.016, -0.026),
                                    (-0.017, -0.009)], 0.03, "steel", bevel=0))
    root.append(guard)
    grip = prism("grip", [(-0.022, 0.008), (-0.026, -0.018), (-0.031, -0.030), (-0.029, -0.042), (-0.035, -0.056), (-0.040, -0.068),
                          (-0.038, -0.080), (-0.044, -0.094), (-0.048, -0.108), (-0.050, -0.118), (-0.090, -0.121), (-0.095, -0.112),
                          (-0.081, -0.050), (-0.073, -0.010), (-0.076, 0.010)], 0.030, "olive", bevel=0.0016, segs=3)
    grip = cut(grip, *slots("gb", -0.088, -0.074, 4, -0.1, -0.06, -0.02, 0.02, angle=0))
    root.append(grip)
    for side in (-1, 1):
        x = side * 0.0163
        panel = prism("gpanel", [(-0.031, -0.010), (-0.035, -0.030), (-0.042, -0.060), (-0.050, -0.100), (-0.085, -0.104), (-0.076, -0.050),
                                 (-0.070, -0.012)], 0.004, "black", x=x, bevel=0.0008)
        panel = cut(prebevel(panel), *dimples("st", -0.082, -0.040, -0.018, -0.096, x + side * 0.002, 6, 9, r=0.0012, side=side))
        root += [panel, screw((x + side * 0.0022, -0.054, -0.018), "x" if side > 0 else "-x", 0.0022),
                 screw((x + side * 0.0022, -0.072, -0.092), "x" if side > 0 else "-x", 0.0022)]
    root.append(cyl("medal", (-0.0187, -0.062, -0.058), (-0.0177, -0.062, -0.058), 0.0048, "red", segs=20))
    root.append(prism("gcap", [(-0.049, -0.117), (-0.091, -0.120), (-0.093, -0.127), (-0.048, -0.124)], 0.032, "black", bevel=0.0015, segs=3))
    root.append(cyl("lanyard", (-0.006, -0.088, -0.124), (0.006, -0.088, -0.124), 0.0016, "bright", segs=10))

    # ---------------------------------------------------------------------- shoulder rest
    rest = block("rest", (0, -0.200, ZC - 0.050), (0.030, 0.058, 0.032), "olive", bevel=0.002, segs=3, taper=(1.25, 1.1))
    rest = cut(prebevel(rest), *slots("rs", -0.222, -0.178, 5, ZC - 0.064, ZC - 0.040, -0.02, -0.0135))
    root.append(rest)
    pad = block("pad", (0, -0.200, ZC - 0.070), (0.036, 0.076, 0.011), "rubber", bevel=0.003, segs=3)
    pad = cut(prebevel(pad), *[block("pg", (0, -0.230 + i * 0.01, ZC - 0.0765), (0.04, 0.0035, 0.004), "steel", bevel=0) for i in range(7)])
    root.append(pad)
    root += [screw((-0.0152, -0.200 + d, ZC - 0.050), "-x", 0.0019) for d in (-0.016, 0.016)]

    # ---------------------------------------------------------------------- forward handle
    yh = 0.280
    root.append(block("hmount", (0, yh, ZC - 0.041), (0.026, 0.034, 0.014), "black", bevel=0.0012))
    fh = prism("fhandle", [(0.262, 0.044), (0.300, 0.044), (0.303, 0.022), (0.299, 0.004), (0.304, -0.016), (0.300, -0.034), (0.305, -0.052),
                           (0.302, -0.072), (0.296, -0.082), (0.264, -0.082), (0.259, -0.072), (0.256, -0.036), (0.259, 0.004)],
               0.030, "black", bevel=0.003, segs=3)
    root.append(fh)
    for side in (-1, 1):
        x = side * 0.0158
        wrap = prism("wrap", [(0.263, 0.020), (0.297, 0.020), (0.300, -0.070), (0.265, -0.070), (0.260, -0.036)], 0.003, "rubber", x=x, bevel=0.0007)
        if side < 0:
            wrap = cut(prebevel(wrap), *dimples("fd", 0.262, 0.296, 0.012, -0.064, x - 0.0015, 5, 9, r=0.0012))
        root.append(wrap)
    root.append(prism("fcap", [(0.264, -0.081), (0.297, -0.081), (0.295, -0.089), (0.266, -0.089)], 0.031, "steel", bevel=0.0015, segs=3))
    root += [screw((-0.0132, yh + d, ZC - 0.041), "-x", 0.0018) for d in (-0.01, 0.01)]
    root.append(label("GRIP", (-0.0175, 0.281, -0.077), 0.0034, "bright"))

    # ---------------------------------------------------------------------- carry handle + reflex sight
    z0 = ZC + 0.030
    ch = prism("chandle", [(-0.150, z0), (0.090, z0), (0.085, z0 + 0.020), (0.062, z1), (-0.122, z1), (-0.146, z0 + 0.020)], 0.022, "black",
               bevel=0.0014, segs=2)
    ch = cut(ch, prism("chh", [(-0.114, z0 + 0.012), (0.054, z0 + 0.012), (0.046, z1 - 0.014), (-0.104, z1 - 0.014)], 0.04, "steel", bevel=0))
    ch = cut(ch, *slots("cg", -0.098, 0.040, 12, z1 - 0.016, z1 - 0.012, -0.02, 0.02))
    root.append(ch)
    root.append(label("SKYHAMMER", (-0.0112, -0.035, z1 - 0.007), 0.0075, "bright"))
    root += [screw((s * 0.0112, y, z0 + 0.006), "x" if s > 0 else "-x", 0.0019) for s in (-1, 1) for y in (-0.135, 0.075)]
    root.append(rail("rail", -0.100, 0.010, z1, "steel", width=0.021))
    # Enclosed reflex sight on the rail.
    ys, zb = -0.046, z1 + 0.0076
    root.append(block("rbase", (0, ys, zb + 0.004), (0.030, 0.056, 0.008), "black", bevel=0.001))
    root.append(block("rclamp", (0.016, ys, zb + 0.002), (0.004, 0.018, 0.011), "steel", bevel=0.0006))
    root.append(cyl("rknob", (0.018, ys, zb + 0.003), (0.024, ys, zb + 0.003), 0.0045, "steel", segs=18))
    hood = prism("hood", [(ys - 0.028, zb + 0.007), (ys + 0.030, zb + 0.007), (ys + 0.030, zb + 0.034), (ys + 0.024, zb + 0.041),
                          (ys - 0.022, zb + 0.041), (ys - 0.028, zb + 0.035)], 0.036, "black", x=0, bevel=0.0018, segs=2)
    hood = cut(hood, block("win", (0, ys, zb + 0.023), (0.028, 0.09, 0.024), "steel", bevel=0),
               *slots("hg", ys - 0.016, ys + 0.016, 5, zb + 0.039, zb + 0.043, -0.012, 0.012))
    root.append(hood)
    root.append(block("glassf", (0, ys + 0.026, zb + 0.023), (0.029, 0.0016, 0.025), "glass", bevel=0))
    root.append(block("glassr", (0, ys - 0.024, zb + 0.023), (0.029, 0.0012, 0.025), "glass", bevel=0))
    root.append(cyl("dot", (0, ys + 0.0245, zb + 0.023), (0, ys + 0.0235, zb + 0.023), 0.0009, "reticle", segs=12, bevel=0))
    root.append(ring("circle", (0, ys + 0.024, zb + 0.023), (0, 1, 0), 0.0058, 0.0050, 0.0008, "reticle", segs=20))
    root += [block("tick", (0, ys + 0.024, zb + 0.023 + s * 0.0075), (0.0008, 0.0008, 0.0025), "reticle", bevel=0) for s in (-1, 1)]
    root.append(cyl("turret", (-0.018, ys - 0.004, zb + 0.022), (-0.024, ys - 0.004, zb + 0.022), 0.0062, "black", segs=20))
    tk = cyl("tcap", (-0.024, ys - 0.004, zb + 0.022), (-0.0265, ys - 0.004, zb + 0.022), 0.0054, "steel", segs=20)
    root.append(tk)
    root += [block("knurl", (-0.0254, ys - 0.004 + 0.0058 * math.cos(math.radians(a)), zb + 0.022 + 0.0058 * math.sin(math.radians(a))),
                   (0.002, 0.0011, 0.0011), "steel", bevel=0) for a in range(0, 360, 30)]
    root.append(label("BRT", (-0.0181, ys + 0.014, zb + 0.022), 0.0032, "bright"))
    root.append(cyl("battcap", (0.018, ys - 0.004, zb + 0.022), (0.022, ys - 0.004, zb + 0.022), 0.0058, "black", segs=20))
    root.append(screw((-0.018, ys + 0.022, zb + 0.012), "-x", 0.0015))
    # Range plate hinge barrel at the front of the handle (the plate itself rides the sight bone).
    root.append(cyl("rhinge", (-0.013, 0.022, z1 + 0.003), (0.013, 0.022, z1 + 0.003), 0.003, "steel", segs=16))
    root.append(block("rstand", (0, 0.022, z1 + 0.0005), (0.028, 0.008, 0.004), "black", bevel=0.0006))
    root.append(block("rstop", (0, 0.05, z1 + 0.0004), (0.012, 0.008, 0.002), "rubber", bevel=0.0004))

    g.add(assemble(root, "root"), "root")

    # ---------------------------------------------------------------------- range plate (sight bone)
    zp = z1 + 0.0032
    plate = block("rplate", (0, 0.046, zp), (0.030, 0.044, 0.0022), "steel", bevel=0.0005)
    plate = cut(plate, *[hole_through("ap", (x, 0.050, zp), r, "z", 0.01, segs=16) for x, r in ((-0.008, 0.0016), (0.0, 0.0012), (0.008, 0.0009))],
                block("notch", (0, 0.068, zp), (0.004, 0.006, 0.01), "steel", bevel=0))
    knuckle = cyl("pk", (-0.006, 0.022, z1 + 0.003), (0.006, 0.022, z1 + 0.003), 0.0034, "steel", segs=16)
    nums = [flat_label(t, (x, 0.041, zp + 0.0011), 0.0032, "bright", rot=(0, 0, 0)) for t, x in (("1", -0.008), ("2", 0.0), ("3", 0.008))]
    g.add(assemble([plate, knuckle, *nums, flat_label("x100M", (0, 0.033, zp + 0.0011), 0.0028, "red", rot=(0, 0, 0))], "sight"), "sight")

    # ---------------------------------------------------------------------- breech cover (venturi)
    cone = [(-0.3275, 0.0315), (-0.3275, 0.0405), (-0.3355, 0.0425), (-0.3465, 0.0425), (-0.3495, 0.0410), (-0.4150, 0.0505),
            (-0.4180, 0.0545), (-0.4320, 0.0545), (-0.4340, 0.0520), (-0.4340, 0.0485), (-0.3600, 0.0350)]
    cv = lathe("cover", cone, "steel", segs=40, bevel=0.0005, bsegs=1)
    cv = cut(cv, *[rblock(a, -0.383, 0.046, 0.026, 0.044, 0.0052) for a in range(15, 360, 30)])
    cover = [cv, ring("lip", (0, -0.425, ZC), (0, 1, 0), 0.0552, 0.0490, 0.008, "red", segs=40)]
    cover += [rivet(a, -0.341, 0.0425) for a in range(0, 360, 36)]
    for dz in (-0.013, 0.013):
        cover.append(cyl("cknuckle", (-0.047, -0.326, ZC + dz - 0.006), (-0.047, -0.326, ZC + dz + 0.006), 0.0045, "steel", segs=16))
        cover.append(block("cleaf", (-0.0438, -0.333, ZC + dz), (0.008, 0.012, 0.011), "steel", bevel=0.0006))
    cover.append(block("latch", (0.046, -0.331, ZC), (0.007, 0.022, 0.010), "red", bevel=0.0012, segs=3))
    cover.append(block("latchtab", (0.0505, -0.338, ZC), (0.006, 0.008, 0.016), "red", bevel=0.0015, segs=3))
    cover.append(cyl("latchpin", (0.046, -0.338, ZC - 0.0075), (0.046, -0.338, ZC + 0.0075), 0.0016, "bright", segs=10))
    cover.append(label("OPEN", (0.0536, -0.338, ZC), 0.0028, "black", side=1))
    g.add(assemble(cover, "cover"), "cover")

    # ---------------------------------------------------------------------- the rocket
    rk = [lathe("nozzle", [(0.186, 0.0105), (0.186, 0.0135), (0.199, 0.0168), (0.206, 0.0168), (0.206, 0.006), (0.195, 0.0078)], "steel", segs=24),
          lathe("motor", [(0.204, 0.0), (0.204, 0.0235), (0.208, 0.0258), (0.440, 0.0258), (0.440, 0.0)], "olive", segs=32, closed=False),
          lathe("collar", [(0.437, 0.0), (0.437, 0.0272), (0.4525, 0.0272), (0.4525, 0.0)], "steel", segs=32, closed=False),
          lathe("warhead", [(0.451, 0.0), (0.451, 0.0262), (0.470, 0.0262), (0.500, 0.0244), (0.528, 0.0198), (0.550, 0.0130),
                            (0.563, 0.0072), (0.569, 0.0035), (0.570, 0.0)], "red", segs=32, closed=False),
          cyl("fuze", (0, 0.568, ZC), (0, 0.5765, ZC), 0.0036, "steel", r1=0.0016, segs=16),
          ring("stripe", (0, 0.405, ZC), (0, 1, 0), 0.0262, 0.0250, 0.007, "yellow", segs=24),
          ring("stripe2", (0, 0.250, ZC), (0, 1, 0), 0.0262, 0.0250, 0.004, "black", segs=24),
          label("HE-84", (-0.0259, 0.35, ZC), 0.0045, "black")]
    rk += [rblock(a, 0.232, 0.0255, 0.0094, 0.046, 0.0016, "olive", bevel=0.0003) for a in (45, 135, 225, 315)]
    rk += [rblock(a, 0.258, 0.0262, 0.0016, 0.004, 0.006, "steel", bevel=0.0002) for a in (45, 135, 225, 315)]
    g.add(assemble(rk, "rocket"), "rocket")

    # ---------------------------------------------------------------------- trigger
    trig = prism("trigger", [(-0.002, 0.002), (0.006, 0.002), (0.006, -0.008), (0.004, -0.022), (0.0, -0.024), (-0.001, -0.012)], 0.006, "bright",
                 bevel=0.0004)
    trig = cut(trig, *[hole_through("th", (0, 0.003, z), 0.0010, "x") for z in (-0.010, -0.015)])
    g.add(trig, "trigger")

    g.socket("muzzle", (0, 0.556, ZC))
    g.socket("backblast", (0, -0.434, ZC))
    clips(g)
    return g


def begin_gun(z1):
    return kit.begin("rocket", {
        "rocket": ((0, 0.38, ZC), None),
        "cover": ((-0.047, -0.326, ZC), None),
        "sight": ((0, 0.022, z1 + 0.003), None),
        "trigger": ((0, 0.003, 0.0), None),
    })


def clips(g):
    rest = ((0, 0, 0), (0, 0, 0))
    away = (0, 8.0, 0)
    g.clip("fire", 0.3, {
        "root": [(0, *rest), (0.035, (0, -0.075, 0.024), (13, 0, -2)), (0.12, (0, -0.028, 0.010), (5, 0, -0.5)), (0.3, *rest)],
        "rocket": [(0, *rest), (0.017, (0, 0.03, 0), (0, 0, 0)), (0.067, away, (0, 0, 0)), (0.283, away, (0, 0, 0)), (0.3, *rest)],
        "trigger": [(0, *rest), (0.02, (0, 0, 0), (-16, 0, 0)), (0.15, *rest)],
        "cover": [(0, *rest), (0.03, (0, 0, 0), (0, 0, -3)), (0.1, *rest)],
    })
    common_clips(g, 1.4, {
        "root": [(0, *rest), (0.25, (0.01, -0.03, 0.03), (14, -18, -14)), (1.0, (0.01, -0.03, 0.03), (15, -20, -15)),
                 (1.22, (0, 0, 0.006), (3, -3, -2)), (1.4, *rest)],
        # The spent tube empties at once, then a fresh rocket comes in from behind and seats.
        "rocket": [(0, *rest), (0.017, away, (0, 0, 0)), (0.30, away, (0, 0, 0)), (0.317, (0, -1.05, -0.10), (12, 0, 0)),
                   (0.55, (0, -0.95, -0.02), (3, 0, 0)), (0.62, (0, -0.88, 0), (0, 0, 0)), (0.92, (0, -0.02, 0), (0, 0, 0)), (0.96, *rest)],
        "cover": [(0, *rest), (0.12, *rest), (0.32, (0, 0, 0), (0, 0, -105)), (1.0, (0, 0, 0), (0, 0, -105)), (1.12, (0, 0, 0), (0, 0, 4)),
                  (1.18, *rest)],
    }, inspect_roll=25, draw_len=0.55)
    g.clip("inspect", 2.6, {
        "root": [(0, *rest), (0.5, (-0.03, 0.02, 0.03), (10, -25, 25)), (1.3, (-0.03, 0.02, 0.03), (12, -30, 30)),
                 (1.8, (0.02, 0.0, 0.02), (-8, 25, -20)), (2.3, *rest)],
        "sight": [(0, *rest), (0.35, *rest), (0.6, (0, 0, 0), (88, 0, 0)), (0.66, (0, 0, 0), (82, 0, 0)), (1.9, (0, 0, 0), (82, 0, 0)),
                  (2.15, *rest)],
    })


SPEC = {"build": build, "length": (0.9, 1.15), "tris": (20000, 70000),
        "bones": ["root", "rocket", "cover", "sight", "trigger"],
        "sockets": ["muzzle"],
        "parts": {"mesh.root": "root", "mesh.rocket": "rocket", "mesh.cover": "cover", "mesh.sight": "sight", "mesh.trigger": "trigger"},
        "moves": {"fire": ["root", "rocket", "trigger"], "reload": ["root", "rocket", "cover"], "draw": ["root"], "inspect": ["root", "sight"]},
        "view": {"cam": (-1.25, 0.02, 0.55), "look": (0, 0.06, 0.035), "lens": 45}}
