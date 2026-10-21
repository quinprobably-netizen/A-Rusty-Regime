"""Thumper: a stubby single-shot break-action 40 mm grenade launcher. Olive receiver, black steel,
a fat rifled barrel on a hinge ahead of the trigger guard, a flip-up ladder sight on the left, a
top latch lever, stippled pistol grip and a skeleton wire stock with a thick rubber pad."""

import math

import bpy  # noqa: F401  (first: bpy makes bmesh importable)
import bmesh
from mathutils import Matrix, Vector

from kit import _obj, begin, block, cyl, hole_through, join, mat, mlok, pin, plan, prism, ring, slots
from parts import MAKER, common_clips

BORE = 0.045  # bore axis height
LAND = 0.0225  # 45 mm bore
GROOVE = 0.0234
HINGE = (0, 0.075, 0.006)


# ------------------------------------------------------------------------------------- helpers


def cut(target, *cutters):
    """kit.cut, but tolerant of overlapping cutters/targets: kit.cut joins every cutter into one object
    and runs EXACT without self-intersection, which empties the target when the cutters overlap
    (box + rounded ends, fluting caps) or the target is a join of overlapping pieces."""
    if not cutters:
        return target
    cutter = join(list(cutters), "_cutter") if len(cutters) > 1 else cutters[0]
    mod = target.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.use_self = True
    mod.object = cutter
    bpy.context.view_layer.objects.active = target
    for o in bpy.context.selected_objects:
        o.select_set(False)
    target.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def prebevel(obj):
    """Bake the part's own bevel now, so detail cut afterwards (stippling, knurls, grooves) stays crisp
    and is not bevelled hole by hole at export, which multiplies its triangles."""
    from kit import apply_modifiers
    apply_modifiers(obj)
    obj["bevel"] = 0.0
    return obj


def screw(at, axis="x", r=0.0022, material="steel", head=0.0012):
    """kit.screw at a third of the triangles: bevel the head first, then sink the hex socket."""
    sgn = -1 if axis.startswith("-") else 1
    a = {"x": Vector((1, 0, 0)), "y": Vector((0, 1, 0)), "z": Vector((0, 0, 1))}[axis[-1]] * sgn
    at = Vector(at)
    s = prebevel(cyl("screw", at - a * head / 2, at + a * head / 2, r, material, segs=12, bevel=0.0002, bsegs=1))
    hexa = cyl("hex", at + a * (head / 2 - 0.0006), at + a * (head / 2 + 0.001), r * 0.45, material, segs=6, bevel=0)
    mod = s.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "FLOAT"
    mod.object = hexa
    from kit import _apply
    _apply(s, mod.name)
    bpy.data.objects.remove(hexa, do_unlink=True)
    return s


def fuse(objs, name):
    """kit.join keeps the first member's bevel for the whole group, so labels, stippled panels and screws
    joined behind a bevelled part get bevelled again at export. Bake each member's own bevel first."""
    objs = [prebevel(o) for o in objs if o is not None]
    o = join(objs, name)
    o["bevel"] = 0.0
    return o


def label(text, at, size, material, side=-1, depth=0.0003, res=3):
    """kit.label with a coarser curve resolution (kit's default 12 costs ~1-2k verts a word)."""
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = depth
    cu.resolution_u = res
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

def section(name, pts, y0, y1, material, bevel=0.0008, segs=2):
    """Extrude a front-on outline [(x, z), ...] along Y from y0 to y1."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y0, z)) for x, z in pts]
    face = bm.faces.new(vs)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, y1 - y0, 0), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, material, bevel, segs)


def arc(cx, cz, r, a0, a1, n):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def rounded(x0, x1, z0, z1, r, n=4):
    """Rounded rectangle outline in (x, z)."""
    return (arc(x1 - r, z0 + r, r, -90, 0, n) + arc(x1 - r, z1 - r, r, 0, 90, n) + arc(x0 + r, z1 - r, r, 90, 180, n)
            + arc(x0 + r, z0 + r, r, 180, 270, n))


def spin_y(obj, deg, centre=(0, 0, BORE)):
    """Rotate a part's mesh about a line along Y through `centre` (angle from +X toward +Z)."""
    c = Vector(centre)
    obj.data.transform(Matrix.Translation(c) @ Matrix.Rotation(math.radians(-deg), 4, "Y") @ Matrix.Translation(-c))
    return obj


def flat_label(text, at, size, material, normal, read, up, depth=0.0003):
    """Raised lettering on any flat face: `normal` out of the face, `read` the reading direction."""
    o = label(text, (0, 0, 0), size, material, depth=depth)
    w = Matrix((normal, read, up)).transposed()  # columns: normal, read, up
    m = w @ Matrix(((-1, 0, 0), (0, -1, 0), (0, 0, 1)))  # label() builds with normal -X, read -Y, up +Z
    o.data.transform(Matrix.Translation(Vector(at)) @ m.to_4x4())
    return o


def slant_dimples(name, rows, z0, z1, front, back, x, side, cols, r=0.001, depth=0.002):
    """Stippling on a raked grip panel: front(z)/back(z) give the panel's y edges at each row."""
    out = []
    for j in range(rows):
        z = z0 + (z1 - z0) * j / (rows - 1)
        y0, y1 = front(z), back(z)
        n = cols - (j % 2)
        for i in range(n):
            y = y0 + (y1 - y0) * (i + (0.5 if j % 2 else 0.0) + 0.5) / cols
            out.append(cyl(name, (x - side * depth, y, z), (x + side * depth, y, z), r, "steel", segs=8, bevel=0))
    return out


def barrel_mesh(name, outer, inner, segs=48, grooves=12, twist=5.2, material="steel", bevel=0.0003):
    """A lathed barrel with a rifled, see-through bore. `outer` [(y, r)] rear to front; `inner`
    [(y, r or None)] where None is the rifled bore (lands LAND, grooves GROOVE, twisting `twist` rad/m)."""
    bm = bmesh.new()
    per = segs // grooves
    y_ref = inner[0][0]

    def angles(y):
        off = twist * (y - y_ref)
        p = 2 * math.pi / grooves
        land = p * 0.55
        out = []
        for k in range(grooves):
            a = off + k * p
            out += [(a, LAND), (a + land, LAND), (a + land, GROOVE), (a + p, GROOVE)]
        return out

    def vring(y, pts):
        return [bm.verts.new((r * math.cos(a), y, BORE + r * math.sin(a))) for a, r in pts]

    assert per == 4
    outs = [vring(y, [(2 * math.pi * i / segs, r) for i in range(segs)]) for y, r in outer]
    ins = []
    for y, r in inner:
        pts = angles(y)
        ins.append(vring(y, [(a, r) for a, _ in pts] if r else pts))

    def bridge(a, b):
        for i in range(segs):
            j = (i + 1) % segs
            bm.faces.new((a[i], a[j], b[j], b[i]))

    for a, b in zip(outs, outs[1:]):
        bridge(a, b)
    for a, b in zip(ins, ins[1:]):
        bridge(b, a)
    bridge(ins[0], outs[0])
    bridge(outs[-1], ins[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, material, bevel, 2)


# --------------------------------------------------------------------------------------- build

def build():
    """Thumper: break-action 40 mm launcher, ~0.55 m."""
    g = begin_gun()
    receiver(g)
    barrel(g)
    sight(g)
    shell(g)
    latch_and_trigger(g)
    grip_and_stock(g)
    g.socket("muzzle", (0, 0.252, BORE), "breech")
    g.socket("eject", (0, -0.02, BORE), "breech")
    clips(g)
    return g


def begin_gun():
    return begin("grenade", {
        "breech": (HINGE, None),
        "shell": ((0, -0.02, BORE), "breech"),
        "sight": ((-0.042, 0.035, 0.067), "breech"),
        "latch": ((0, -0.075, 0.049), None),
        "trigger": ((0, 0.007, -0.004), None),
    })


def receiver(g):
    # Lower receiver: tang behind the breech, frame under the barrel ending in the hinge knuckle.
    knuckle = arc(HINGE[1], HINGE[2], 0.013, 50, -115, 8)
    prof = [(-0.128, -0.004), (-0.128, 0.040), (-0.124, 0.046), (-0.058, 0.046), (-0.02, 0.046), (-0.02, 0.010), (0.072, 0.010)]
    prof += knuckle[1:] + [(0.05, -0.008), (-0.03, -0.008), (-0.1, -0.006)]
    rec = prism("receiver", prof, 0.05, "olive", bevel=0.0012, segs=3)
    cuts = [block("lugslot", (0, 0.07, 0.004), (0.0275, 0.05, 0.04), "steel", bevel=0)]
    cuts += [hole_through("pinhole", HINGE, 0.003, "x", 0.08)]
    # right-side lightening pocket and a top groove on the tang
    cuts += [block("pocket", (0.025, -0.085, 0.012), (0.003, 0.04, 0.016), "steel", bevel=0)]
    # left: index line grooves above the grip
    cuts += [block("groove", (-0.025, -0.083, 0.023), (0.0016, 0.074, 0.0014), "steel", bevel=0)]
    cuts += [block("groove", (-0.025, 0.02, 0.003), (0.0016, 0.06, 0.0014), "steel", bevel=0)]
    rec = cut(rec, *cuts)
    # Standing breech (recoil shield): flares round the barrel's rear face.
    sh_out = [(-0.036, 0.0), (0.036, 0.0)] + arc(0, BORE, 0.036, 0, 180, 16)[:]
    shield = section("shield", sh_out, -0.058, -0.02, "olive", bevel=0.0012, segs=3)
    wedge = prism("wedge", [(-0.062, 0.052), (-0.062, 0.095), (-0.034, 0.095)], 0.1, "steel", bevel=0)
    ch_l = plan("ch", [(-0.045, -0.062), (-0.028, -0.062), (-0.045, -0.042)], 0.2, "steel", bevel=0)
    ch_r = plan("ch", [(0.045, -0.062), (0.028, -0.062), (0.045, -0.042)], 0.2, "steel", bevel=0)
    fp = hole_through("fp", (0, -0.02, BORE), 0.0018, "y", 0.006)
    shield = cut(shield, wedge, ch_l, ch_r, fp)
    face = [ring("fpbush", (0, -0.0195, BORE), (0, 1, 0), 0.0065, 0.0019, 0.0015, "bright", segs=24)]
    face += [screw((x, -0.0198, z), "y", 0.0018, "bright") for x, z in ((-0.024, 0.06), (0.024, 0.06), (-0.026, 0.02), (0.026, 0.02))]
    # Left-side hardware: hinge pin head, shield screws, trigger and grip pins, markings.
    hw = [cyl("hingehead", (-0.0248, HINGE[1], HINGE[2]), (-0.0285, HINGE[1], HINGE[2]), 0.0072, "steel", segs=24, bevel=0.0004)]
    hw[0] = cut(hw[0], block("slot", (-0.029, HINGE[1], HINGE[2]), (0.002, 0.011, 0.0014), "steel", bevel=0, rot=30))
    hw += [cyl("hingenut", (0.0248, HINGE[1], HINGE[2]), (0.0282, HINGE[1], HINGE[2]), 0.0068, "steel", segs=6, bevel=0.0004)]
    hw += [cyl("pinbar", (-0.03, HINGE[1], HINGE[2]), (0.03, HINGE[1], HINGE[2]), 0.0029, "bright", segs=16)]
    hw += [screw((s * 0.0365, y, z), "x" if s > 0 else "-x", 0.0021) for s in (-1, 1) for y, z in ((-0.027, 0.008), (-0.05, 0.008), (-0.027, 0.04), (-0.05, 0.04))]
    hw += [pin((0, 0.007, -0.003), "x", 0.0015, 0.052), pin((0, -0.04, 0.0), "x", 0.0015, 0.052), pin((0, -0.108, 0.01), "x", 0.0016, 0.052)]
    hw += [screw((-0.0252, -0.112, 0.038), "-x", 0.0022), screw((-0.0252, -0.112, 0.004), "-x", 0.0022), screw((-0.0252, 0.058, 0.002), "-x", 0.0018)]
    marks = [label("THUMPER", (-0.0252, -0.083, 0.031), 0.0105, "bright"),
             label("M-79R  40MM GL", (-0.0252, -0.083, 0.0175), 0.0042, "bright"),
             label("CAL 40x46  LOW VEL", (-0.0252, -0.083, 0.0115), 0.0031, "bright"),
             label("No 0417", (-0.0362, -0.0385, 0.024), 0.0036, "bright"),
             label(MAKER, (0.0252, -0.083, 0.031), 0.0042, "bright", side=1),
             label("RIFLED BORE - DO NOT FIRE WITHIN 30 M", (0.0252, 0.012, 0.0015), 0.0021, "bright", side=1)]
    # top: tang markings and an arrow telling which way the latch opens
    marks += [flat_label("OPEN >", (0.0, -0.027, 0.0812), 0.0032, "bright", (0, 0, 1), (1, 0, 0), (0, 1, 0), depth=0.0006),
              flat_label("S", (-0.013, -0.118, 0.0465), 0.003, "bright", (0, 0, 1), (1, 0, 0), (0, 1, 0)),
              flat_label("F", (0.013, -0.118, 0.0465), 0.003, "red", (0, 0, 1), (1, 0, 0), (0, 1, 0))]
    safety = prebevel(block("safety", (0, -0.118, 0.0485), (0.012, 0.009, 0.005), "steel", bevel=0.0006))
    safety = cut(safety, *slots("ss", -0.121, -0.115, 4, 0.0505, 0.052, -0.007, 0.007))
    g.add(fuse([rec, shield, *face, *hw, *marks, safety], "receiver"), "root")


def barrel(g):
    outer = [(-0.02, 0.0326), (-0.0196, 0.0336), (-0.0186, 0.034), (0.0436, 0.034), (0.0446, 0.0336), (0.0496, 0.0314), (0.0506, 0.031),
             (0.2316, 0.031), (0.2326, 0.0306), (0.2346, 0.0298), (0.235, 0.0296), (0.2466, 0.0296), (0.2474, 0.0292), (0.250, 0.0270)]
    # Outer tube (bevelled, fluted) with a plain bore; a separate flat-shaded liner carries the rifling.
    b = barrel_mesh("barrel", outer, [(-0.02, 0.0242), (-0.0165, 0.0242), (-0.0165, 0.0237), (0.25, 0.0237)], bevel=0.0005)
    liner = barrel_mesh("liner", [(-0.0165, 0.0239), (0.2496, 0.0239)],
                        [(-0.0165 + (0.2661 / 16) * i, None) for i in range(17)], bevel=0.0)
    for poly in liner.data.polygons:
        poly.use_smooth = False
    flutes = []
    for ang in (22, 52, 128, 158, 200, 340):
        y0, y1 = (0.062, 0.168) if ang in (22, 52, 128, 158) else (0.062, 0.086)
        f = [block("fl", (0, (y0 + y1) / 2, BORE + 0.031), (0.0058, y1 - y0, 0.006), "steel", bevel=0)]
        f += [cyl("fl", (0, y, BORE + 0.028), (0, y, BORE + 0.034), 0.0029, "steel", segs=12, bevel=0) for y in (y0, y1)]
        flutes += [spin_y(o, ang - 90) for o in f]
    # band seat groove and a crown groove
    b = cut(b, *flutes, ring("crowngroove", (0, 0.241, BORE), (0, 1, 0), 0.033, 0.0285, 0.0016, "steel", segs=48))
    parts = [b, liner]
    # Riveted data plate on the chamber reinforce, facing the camera.
    parts += [block("dplate", (-0.0343, 0.001, 0.045), (0.0025, 0.026, 0.014), "bright", bevel=0.0004)]
    parts += [cyl("rivet", (-0.0356, y, z), (-0.0362, y, z), 0.0008, "steel", segs=8, bevel=0) for y in (-0.0095, 0.0115) for z in (0.0395, 0.0505)]
    parts += [label("40x46 LV", (-0.0357, 0.001, 0.0478), 0.0034, "black"), label("LOT 26-04  HE", (-0.0357, 0.001, 0.0418), 0.0024, "black")]
    # A bright collar where the chamber reinforce steps down.
    parts += [ring("collar", (0, 0.047, BORE), (0, 1, 0), 0.0328, 0.030, 0.0035, "bright", segs=48)]
    # Hinge lug under the barrel, locking lug on top of the breech end, extractor.
    lug = block("lug", (0, 0.063, 0.012), (0.026, 0.034, 0.012), "steel", bevel=0.001)
    knuckle = cyl("lugk", (-0.013, HINGE[1], HINGE[2]), (0.013, HINGE[1], HINGE[2]), 0.0108, "steel", segs=24, bevel=0.0008)
    parts += [cut(fuse([lug, knuckle], "lug"), hole_through("lh", HINGE, 0.0031, "x", 0.04))]
    parts += [block("locklug", (0, -0.012, 0.0785), (0.014, 0.014, 0.006), "steel", bevel=0.0006)]
    parts += [block("extractor", (-0.017, -0.0185, 0.023), (0.012, 0.004, 0.008), "bright", bevel=0.0004, rot=40)]
    # Top rib with glare serrations.
    rib = prebevel(block("rib", (0, 0.122, 0.0775), (0.012, 0.13, 0.006), "steel", bevel=0.0006))
    rib = cut(rib, *slots("rs", 0.064, 0.18, 26, 0.0795, 0.082, -0.01, 0.01))
    parts += [rib]
    parts += [block("ribpost", (0, y, 0.0735), (0.006, 0.008, 0.006), "steel", bevel=0.0004) for y in (0.068, 0.176)]
    # Hazard band near the muzzle, with a stencilled calibre.
    band = ring("band", (0, 0.2085, BORE), (0, 1, 0), 0.0319, 0.0305, 0.026, "hazard", segs=48)
    parts += [band, label("40MM", (-0.0322, 0.2085, BORE), 0.0068, "black", depth=0.0005),
              label("40MM", (0.0322, 0.2085, BORE), 0.0068, "black", side=1, depth=0.0005)]
    # Front sight on a left bracket, post between two ears.
    fb = block("fsb", (-0.031, 0.181, 0.062), (0.019, 0.012, 0.014), "black", bevel=0.0008)
    fb = cut(fb, hole_through("fsh", (-0.034, 0.181, 0.06), 0.0025, "y", 0.03))
    post = block("post", (-0.040, 0.181, 0.078), (0.0025, 0.0025, 0.022), "black", bevel=0.0003)
    tip = block("posttip", (-0.040, 0.181, 0.0895), (0.0026, 0.0026, 0.002), "hazard", bevel=0)
    ears = [block("ear", (x, 0.181, 0.076), (0.0022, 0.009, 0.026), "black", bevel=0.0005, taper=(1, 0.6)) for x in (-0.0465, -0.0335)]
    parts += [fb, post, tip, *ears, screw((-0.0405, 0.181, 0.06), "-x", 0.0018)]
    # Ladder sight base and a rest pad the folded ladder sits on.
    base = block("sbase", (-0.033, 0.03, 0.064), (0.014, 0.026, 0.018), "black", bevel=0.0009)
    base = cut(base, block("sgap", (-0.0415, 0.035, 0.067), (0.004, 0.012, 0.012), "steel", bevel=0))
    parts += [base, screw((-0.0402, 0.022, 0.058), "-x", 0.0019), screw((-0.0402, 0.022, 0.071), "-x", 0.0019)]
    parts += [block("rest", (-0.0315, 0.106, 0.062), (0.017, 0.008, 0.01), "black", bevel=0.0008),
              block("restpad", (-0.0405, 0.106, 0.062), (0.0015, 0.006, 0.007), "rubber", bevel=0.0003)]
    # Forend: an olive half-shell hugging the barrel, vents through to the flutes, finger grooves.
    fo = [(0.036, BORE), (0.036, 0.014), (0.034, 0.006), (0.029, 0.0), (0.022, -0.003), (-0.022, -0.003), (-0.029, 0.0), (-0.034, 0.006),
          (-0.036, 0.014), (-0.036, BORE)]
    fo += arc(0, BORE, 0.0314, 180, 360, 24)
    fore = section("forend", fo, 0.092, 0.188, "olive", bevel=0.0012, segs=3)
    fcuts = [prism("fw", [(0.168, -0.01), (0.2, -0.01), (0.2, 0.024)], 0.1, "steel", bevel=0),
             prism("rw", [(0.086, -0.01), (0.102, -0.01), (0.086, 0.008)], 0.1, "steel", bevel=0)]
    fcuts += slots("fg", 0.108, 0.156, 5, -0.007, 0.0, -0.05, 0.05)
    fcuts += mlok("v", 0.104, 0.176, 4, 0.025, -0.03, depth=0.03, h=0.007) + mlok("v", 0.104, 0.176, 4, 0.025, 0.03, depth=0.03, h=0.007)
    fore = cut(fore, *fcuts)
    parts += [fore, screw((-0.0362, 0.098, 0.034), "-x", 0.0019), screw((-0.0362, 0.182, 0.034), "-x", 0.0019),
              screw((0.0362, 0.098, 0.034), "x", 0.0019), screw((0.0362, 0.182, 0.034), "x", 0.0019),
              label("40x46 LV  RIFLED", (-0.0362, 0.14, 0.0395), 0.0031, "bright"),
              label("THUMPER", (0.0362, 0.14, 0.0395), 0.0036, "bright", side=1)]
    swivel = [block("swb", (0, 0.172, -0.005), (0.008, 0.01, 0.006), "steel", bevel=0.0005),
              ring("sw", (0, 0.172, -0.0115), (1, 0, 0), 0.0065, 0.0042, 0.0035, "steel", segs=20)]
    parts += swivel
    for p in parts:
        g.add(p, "breech")


def sight(g):
    """Ladder sight lying flat along the barrel's left side, graduated 50-350 m; flips up about its rear knuckle."""
    x = -0.042
    plate = block("ladder", (x, 0.071, 0.067), (0.003, 0.074, 0.022), "black", bevel=0.0005)
    win = block("win", (x, 0.074, 0.0725), (0.01, 0.056, 0.0055), "steel", bevel=0)
    hole = hole_through("lh", (x, 0.035, 0.067), 0.0016, "x", 0.02)
    plate = cut(plate, win, hole)
    parts = [plate, cyl("knuckle", (x - 0.0025, 0.035, 0.067), (x + 0.0025, 0.035, 0.067), 0.0042, "black", segs=20),
             cyl("kpin", (x - 0.0032, 0.035, 0.067), (x + 0.0032, 0.035, 0.067), 0.0016, "bright", segs=12)]
    face = x - 0.0015
    for i, rng in enumerate(range(50, 351, 50)):
        y = 0.046 + i * 0.0088
        parts.append(flat_label(str(rng), (face - 0.0001, y, 0.0618), 0.0036, "bright", (-1, 0, 0), (0, 0, 1), (0, 1, 0)))
        parts.append(block("tick", (face - 0.0002, y, 0.0675), (0.0006, 0.0007, 0.003), "bright", bevel=0))
        if i < 6:
            parts.append(block("tick", (face - 0.0002, y + 0.0044, 0.0682), (0.0006, 0.0005, 0.0016), "bright", bevel=0))
    # Slider with its peep aperture (looks along Y once the ladder stands up) and knurled lock screw.
    slider = block("slider", (x, 0.083, 0.0725), (0.0068, 0.008, 0.0105), "steel", bevel=0.0005)
    slider = cut(slider, hole_through("peep", (x - 0.0008, 0.083, 0.0725), 0.0012, "z", 0.02))
    knob = prebevel(cyl("knob", (x - 0.0034, 0.083, 0.0725), (x - 0.0075, 0.083, 0.0725), 0.0032, "steel", segs=16, bevel=0.0003))
    knob = cut(knob, *[spin_x(block("k", (x - 0.006, 0.083, 0.0725 + 0.0033), (0.005, 0.0007, 0.0012), "steel", bevel=0), a, (0, 0.083, 0.0725))
                       for a in range(0, 360, 30)])
    parts += [slider, knob, block("spring", (x + 0.0006, 0.04, 0.0595), (0.0012, 0.008, 0.0025), "bright", bevel=0.0002)]
    parts.append(flat_label("M", (face - 0.0001, 0.1035, 0.0618), 0.003, "bright", (-1, 0, 0), (0, 0, 1), (0, 1, 0)))
    g.add(fuse(parts, "sight"), "sight")


def spin_x(obj, deg, centre):
    c = Vector(centre)
    obj.data.transform(Matrix.Translation(c) @ Matrix.Rotation(math.radians(deg), 4, "X") @ Matrix.Translation(-c))
    return obj


def shell(g):
    """The chambered 40 mm round: brass case with primer and headstamp, copper drive band, olive HE body with a
    yellow band and a fuze tip."""
    y0 = -0.0198
    p = [cyl("rim", (0, y0, BORE), (0, y0 + 0.003, BORE), 0.0239, "brass", segs=32, bevel=0.0004)]
    p += [cyl("case", (0, y0 + 0.003, BORE), (0, 0.026, BORE), 0.0219, "brass", segs=32, bevel=0.0004)]
    p += [ring("extgroove", (0, y0 + 0.0042, BORE), (0, 1, 0), 0.0221, 0.0205, 0.0012, "brass", segs=32)]
    p += [cyl("primer", (0, y0 - 0.0004, BORE), (0, y0 + 0.001, BORE), 0.0036, "bright", segs=20, bevel=0.0002)]
    p += [ring("pcup", (0, y0 - 0.0002, BORE), (0, 1, 0), 0.0062, 0.0042, 0.0006, "brass", segs=24)]
    p += [flat_label("40MM M406", (0, y0 - 0.0002, BORE - 0.012), 0.0024, "black", (0, -1, 0), (1, 0, 0), (0, 0, 1)),
          flat_label("RR 26", (0, y0 - 0.0002, BORE + 0.012), 0.0024, "black", (0, -1, 0), (1, 0, 0), (0, 0, 1))]
    p += [cyl("crimp", (0, 0.0245, BORE), (0, 0.027, BORE), 0.0219, "brass", r1=0.0214, segs=32, bevel=0)]
    p += [cyl("driveband", (0, 0.027, BORE), (0, 0.031, BORE), 0.0222, "copper", segs=32, bevel=0.0003)]
    p += [cyl("body", (0, 0.031, BORE), (0, 0.05, BORE), 0.0216, "olive", segs=32, bevel=0.0003)]
    p += [ring("hazband", (0, 0.037, BORE), (0, 1, 0), 0.0218, 0.021, 0.006, "yellow", segs=32)]
    prof = [(0.05, 0.0216), (0.055, 0.0204), (0.059, 0.0183), (0.0625, 0.0153), (0.0655, 0.0115), (0.068, 0.0078)]
    for (ya, ra), (yb, rb) in zip(prof, prof[1:]):
        p.append(cyl("ogive", (0, ya, BORE), (0, yb, BORE), ra, "olive", r1=rb, segs=32, bevel=0))
    p += [cyl("fuze", (0, 0.068, BORE), (0, 0.0715, BORE), 0.0078, "steel", r1=0.0052, segs=24, bevel=0.0002),
          cyl("fuzetip", (0, 0.0715, BORE), (0, 0.073, BORE), 0.0052, "bright", r1=0.0025, segs=24, bevel=0.0002)]
    g.add(fuse(p, "shell"), "shell")


def latch_and_trigger(g):
    # Top latch lever: pivots on the tang, its thumb tab sticks out to the left; push it right to open.
    lv = plan("latch", [(-0.0065, -0.066), (0.0065, -0.066), (0.0075, -0.092), (0.004, -0.099), (-0.021, -0.104), (-0.027, -0.1),
                        (-0.026, -0.093), (-0.007, -0.088)], 0.005, "steel", z=0.0485, bevel=0.0007)
    lv = prebevel(lv)
    lv = cut(lv, *[block("lg", (-0.017 + dx, -0.098, 0.051), (0.0012, 0.011, 0.002), "steel", bevel=0) for dx in (-0.006, -0.003, 0, 0.003, 0.006)])
    head = cyl("lhead", (0, -0.075, 0.051), (0, -0.075, 0.0535), 0.0052, "bright", segs=20, bevel=0.0003)
    head = cut(head, block("ls", (0, -0.075, 0.0535), (0.008, 0.0012, 0.0016), "steel", bevel=0))
    nose = block("lnose", (0, -0.0625, 0.0485), (0.006, 0.008, 0.004), "steel", bevel=0.0005)
    g.add(fuse([lv, head, nose], "latch"), "latch")
    trig = prism("trigger", [(0.002, -0.006), (0.012, -0.006), (0.0125, -0.012), (0.0095, -0.021), (0.012, -0.029), (0.0075, -0.0305),
                             (0.0035, -0.021), (0.001, -0.012)], 0.0075, "bright", bevel=0.0005)
    trig = cut(trig, *[block("tg", (0, 0.0105 + 0.0006 * k, -0.013 - 0.004 * k), (0.01, 0.0012, 0.0012), "steel", bevel=0) for k in range(4)])
    g.add(trig, "trigger")


def grip_and_stock(g):
    parts = []
    # Trigger guard: big enough for a glove.
    guard = prism("guard", [(-0.026, -0.005), (0.056, -0.005), (0.06, -0.013), (0.057, -0.035), (0.049, -0.042), (-0.006, -0.042),
                            (-0.03, -0.03)], 0.012, "steel", bevel=0.0009)
    guard = cut(guard, prism("gh", [(-0.02, -0.0088), (0.051, -0.0088), (0.054, -0.014), (0.051, -0.031), (0.045, -0.0365),
                                    (-0.004, -0.0365), (-0.022, -0.026)], 0.03, "steel", bevel=0),
                hole_through("gp", (0, 0.052, -0.0065), 0.0013, "x", 0.03))
    parts += [guard, pin((0, 0.052, -0.0065), "x", 0.0013, 0.0125)]
    # Pistol grip with finger grooves, rubber side panels stippled all over, screw, cap and lanyard loop.
    grip = prism("grip", [(-0.026, -0.006), (-0.034, -0.026), (-0.040, -0.036), (-0.038, -0.046), (-0.043, -0.056), (-0.042, -0.066),
                          (-0.047, -0.077), (-0.047, -0.087), (-0.053, -0.104), (-0.058, -0.112), (-0.096, -0.112), (-0.099, -0.104),
                          (-0.091, -0.06), (-0.087, -0.03), (-0.092, -0.012), (-0.104, -0.006)], 0.032, "black", bevel=0.0018, segs=3)
    parts.append(grip)
    pan = [(-0.046, -0.022), (-0.05, -0.05), (-0.054, -0.08), (-0.06, -0.1), (-0.09, -0.1), (-0.086, -0.06), (-0.082, -0.03), (-0.078, -0.022)]

    def front(z):
        return -0.046 + (z + 0.022) * 0.18 - 0.002

    def back(z):
        return -0.078 + (z + 0.022) * 0.16 + 0.002

    for side in (-1, 1):
        x = side * 0.0165
        panel = prebevel(prism("panel", pan, 0.004, "rubber", x=x, bevel=0.0008))
        panel = cut(panel, *slant_dimples("st", 11, -0.032, -0.095, front, back, x + side * 0.002, side, 9, r=0.00105))
        parts += [panel, screw((x + side * 0.0022, -0.058, -0.026), "x" if side > 0 else "-x", 0.0023)]
    parts += [cyl("medal", (-0.0189, -0.072, -0.026), (-0.0182, -0.072, -0.026), 0.004, "hazard", segs=20)]
    cap = block("gcap", (0, -0.077, -0.114), (0.034, 0.043, 0.006), "steel", bevel=0.001)
    parts += [cap, ring("lanyard", (0, -0.092, -0.1205), (1, 0, 0), 0.0055, 0.0034, 0.004, "steel", segs=20),
              screw((0, -0.066, -0.1172), "-z", 0.0024)]
    # Stock hinge block, folding knuckle on the left with a hazard-yellow release button.
    sb = block("sbase", (0, -0.134, 0.02), (0.05, 0.014, 0.054), "black", bevel=0.0012)
    sb = cut(sb, *slots("sbs", -0.139, -0.129, 3, 0.04, 0.05, -0.03, 0.03))
    kn = cyl("sknuckle", (-0.027, -0.136, -0.004), (-0.027, -0.136, 0.046), 0.0055, "steel", segs=20)
    kn = cut(kn, *[block("kg", (-0.027, -0.136, z), (0.02, 0.02, 0.0012), "steel", bevel=0) for z in (0.008, 0.021, 0.034)])
    parts += [sb, kn, cyl("kcap", (-0.027, -0.136, 0.046), (-0.027, -0.136, 0.0485), 0.0045, "bright", segs=16)]
    btn = cyl("release", (-0.025, -0.122, 0.031), (-0.0305, -0.122, 0.031), 0.0042, "hazard", segs=20, bevel=0.0004)
    parts += [btn, ring("btnring", (-0.0262, -0.122, 0.031), (1, 0, 0), 0.0056, 0.0043, 0.0025, "steel", segs=20)]
    parts += [label("FOLD", (-0.0252, -0.122, 0.042), 0.003, "bright")]
    # Wire skeleton stock: two side frames of steel rod with braces, cross bars and joint bosses.
    yb = -0.274
    for x in (-0.021, 0.021):
        parts += [cyl("rod", (x, -0.138, 0.040), (x, yb, 0.038), 0.0045, "steel", segs=16),
                  cyl("rod", (x, -0.138, 0.0), (x, yb, -0.068), 0.0045, "steel", segs=16),
                  cyl("brace", (x, -0.165, -0.0128), (x, -0.236, 0.0386), 0.0038, "steel", segs=16)]
        for y, z in ((-0.165, -0.0128), (-0.236, 0.0386), (-0.2, -0.031)):
            parts.append(cyl("boss", (x - 0.0055, y, z), (x + 0.0055, y, z), 0.0058, "steel", segs=16))
    parts += [cyl("cross", (-0.021, -0.2, -0.031), (0.021, -0.2, -0.031), 0.0035, "steel", segs=14)]
    parts += [ring("sling", (0, -0.2, -0.0395), (1, 0, 0), 0.007, 0.0046, 0.004, "steel", segs=20)]
    # Butt plate and the thick rubber recoil pad with grooves and recessed screws.
    plate = section("bplate", rounded(-0.026, 0.026, -0.086, 0.054, 0.01), yb - 0.006, yb + 0.002, "black", bevel=0.0008)
    plate = cut(plate, section("bpw", rounded(-0.014, 0.014, -0.058, 0.026, 0.006), yb - 0.01, yb + 0.01, "steel", bevel=0))
    parts += [plate, cyl("crossT", (-0.021, yb + 0.002, 0.038), (0.021, yb + 0.002, 0.038), 0.0045, "steel", segs=16),
              cyl("crossB", (-0.021, yb + 0.002, -0.068), (0.021, yb + 0.002, -0.068), 0.0045, "steel", segs=16)]
    pad = prebevel(section("pad", rounded(-0.0275, 0.0275, -0.092, 0.06, 0.014, 5), yb - 0.031, yb - 0.006, "rubber", bevel=0.003, segs=3))
    pc = []
    for k in range(6):
        z = -0.072 + k * 0.022
        pc += [block("pg", (-0.0275, yb - 0.0195, z), (0.005, 0.016, 0.0022), "steel", bevel=0),
               block("pg", (0.0275, yb - 0.0195, z), (0.005, 0.016, 0.0022), "steel", bevel=0),
               block("pg", (0, yb - 0.031, z), (0.04, 0.005, 0.0022), "steel", bevel=0)]
    pc += [hole_through("ph", (0, yb - 0.031, z), 0.0042, "y", 0.012) for z in (-0.061, 0.029)]
    pad = cut(pad, *pc)
    parts += [pad] + [screw((0, yb - 0.026, z), "-y", 0.0028) for z in (-0.061, 0.029)]
    parts += [label("RRA", (-0.0276, yb - 0.0195, -0.061), 0.0042, "grey")]
    g.add(fuse(parts, "furniture"), "root")


# ---------------------------------------------------------------------------------------- clips

def clips(g):
    g.clip("fire", 0.5, {
        "trigger": [(0, (0, 0, 0), (0, 0, 0)), (0.03, (0, 0, 0), (-16, 0, 0)), (0.18, (0, 0, 0), (-16, 0, 0)), (0.28, (0, 0, 0), (0, 0, 0))],
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.035, (0.004, -0.055, 0.018), (15, 1.5, 3)), (0.09, (0.003, -0.04, 0.016), (12, 1, 2.5)),
                 (0.22, (0.001, -0.012, 0.004), (3, 0, 0.6)), (0.34, (0, 0.002, -0.001), (-0.8, 0, 0)), (0.5, (0, 0, 0), (0, 0, 0))],
        "sight": [(0, (0, 0, 0), (0, 0, 0)), (0.03, (0, 0, 0), (3, 0, 0)), (0.1, (0, 0, 0), (-1, 0, 0)), (0.18, (0, 0, 0), (0, 0, 0))],
    })
    reload = {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.22, (0.012, 0.0, 0.03), (10, -14, 14)), (0.42, (0.012, 0.004, 0.026), (5, -15, 14)),
                 (0.5, (0.012, 0.0, 0.03), (11, -14, 14)), (0.75, (0.016, -0.01, 0.036), (16, -10, 10)), (1.15, (0.012, 0.0, 0.034), (12, -16, 14)),
                 (1.3, (0.01, 0.0, 0.03), (11, -14, 13)), (1.36, (0.01, 0.004, 0.036), (16, -12, 12)), (1.5, (0.006, 0, 0.018), (6, -6, 6)),
                 (1.8, (0, 0, 0), (0, 0, 0))],
        "latch": [(0, (0, 0, 0), (0, 0, 0)), (0.1, (0, 0, 0), (0, 0, 0)), (0.2, (0, 0, 0), (0, 0, 32)), (1.34, (0, 0, 0), (0, 0, 32)),
                  (1.4, (0, 0, 0), (0, 0, 0))],
        "breech": [(0, (0, 0, 0), (0, 0, 0)), (0.22, (0, 0, 0), (0, 0, 0)), (0.4, (0, 0, 0), (-43, 0, 0)), (0.46, (0, 0, 0), (-40, 0, 0)),
                   (1.22, (0, 0, 0), (-40, 0, 0)), (1.34, (0, 0, 0), (0, 0, 0))],
        "shell": [(0, (0, 0, 0), (0, 0, 0)), (0.42, (0, 0, 0), (0, 0, 0)), (0.5, (0, -0.03, 0), (0, 0, 0)),
                  (0.6, (0.01, -0.13, 0.05), (-35, 25, 10)), (0.72, (0.04, -0.32, 0.12), (-110, 80, 40)),
                  (0.74, (0.07, -0.22, -0.12), (25, 0, -20)), (0.92, (0.012, -0.11, -0.01), (6, 0, -4)),
                  (1.02, (0, -0.06, 0), (0, 0, 0)), (1.14, (0, 0, 0), (0, 0, 0))],
    }
    common_clips(g, 1.8, reload)
    g.clip("idle", 2.0, {"root": [(0, (0, 0, 0), (0, 0, 0)), (1.0, (0, 0, 0.0015), (0.6, 0, 0.2)), (2.0, (0, 0, 0), (0, 0, 0))]})
    g.clip("inspect", 2.6, {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.5, (-0.03, 0.02, 0.03), (10, -32, 25)), (1.3, (-0.03, 0.02, 0.03), (12, -36, 30)),
                 (1.8, (0.02, 0.0, 0.02), (-8, 28, -20)), (2.3, (0, 0, 0), (0, 0, 0))],
        "sight": [(0, (0, 0, 0), (0, 0, 0)), (0.45, (0, 0, 0), (0, 0, 0)), (0.7, (0, 0, 0), (90, 0, 0)), (0.76, (0, 0, 0), (84, 0, 0)),
                  (1.7, (0, 0, 0), (84, 0, 0)), (1.95, (0, 0, 0), (0, 0, 0))],
    })


SPEC = {"build": build, "length": (0.5, 0.6), "tris": (20000, 70000),
        "bones": ["root", "breech", "shell", "latch", "sight", "trigger"],
        "sockets": ["muzzle", "eject"],
        "parts": {"mesh.root": "root", "mesh.breech": "breech", "mesh.shell": "shell", "mesh.latch": "latch", "mesh.sight": "sight",
                  "mesh.trigger": "trigger"},
        "moves": {"fire": ["root", "trigger"], "reload": ["root", "breech", "shell", "latch"], "draw": ["root"],
                  "inspect": ["root", "sight"]},
        "view": {"cam": (-0.78, 0.2, 0.3), "look": (0, -0.025, 0.0), "lens": 50}}
