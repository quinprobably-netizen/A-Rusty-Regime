"""Longshot DMR: a semi-auto designated marksman rifle in tan/olive with black steel. Billet upper with
a side window onto the bolt carrier, long M-LOK handguard, fluted heavy barrel, big three-port brake,
folded bipod, 20-round steel magazine and a precision stock with a cheek riser and spacer butt pad."""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from kit import _apply, _obj, _orient, apply_modifiers, begin, block, cyl, hole_through, join, mat, mlok, pin, prism, rail, ring, screw, slots, tube
from parts import MAKER, SLOT_ATTS, grip_parts, lens_socket, muzzle_parts, optic_reddot, stock_parts, mag_drop

BORE = 0.042
RAIL_Z = 0.064          # top of the receiver/handguard, base of the top rail
RAIL_TOP = RAIL_Z + 0.0076
HG = (0.124, 0.52)      # handguard span along Y
HW, HZB, HZT, HC = 0.027, 0.004, 0.064, 0.011   # handguard half width, bottom, top, corner chamfer
UNDER_Z = HZB - 0.0076
MUZZLE_Y = 0.600


def carve(target, *cutters, pre=False):
    """kit.cut with the Exact solver's self-intersection mode on. kit.cut leaves it off, which breaks
    on cutters that overlap each other (M-LOK slot ends, a window crossing a channel): whole faces
    vanish. `pre` bevels the target first so fine knurling/stippling is not bevelled again."""
    if pre:
        settle(target)
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
    if pre:
        reshade(target)
    return target


def reshade(o, angle=30):
    """Re-derive normals after a boolean on an already bevelled part: the bevel's custom normals do
    not survive the cut and flat faces shade in waves. Sharp edges by angle, then weighted normals."""
    bpy.context.view_layer.objects.active = o
    for other in bpy.context.selected_objects:
        other.select_set(False)
    o.select_set(True)
    if o.data.has_custom_normals:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bm = bmesh.new()
    bm.from_mesh(o.data)
    lim = math.radians(angle)
    for e in bm.edges:
        e.smooth = not (len(e.link_faces) != 2 or e.calc_face_angle(0.0) > lim)
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(o.data)
    bm.free()
    wn = o.modifiers.new("wn", "WEIGHTED_NORMAL")
    wn.keep_sharp = True
    _apply(o, wn.name)
    return o


def settle(o):
    """Apply this part's own bevel now, so joining it into an assembly does not re-bevel it with
    the assembly's first part's width."""
    apply_modifiers(o)
    o["bevel"] = 0.0
    return o


def rl(*a, **k):
    """kit.rail with chamfered (one-segment) tooth edges: 60-odd teeth at two segments cost too much."""
    r = rail(*a, **k)
    r["segs"] = 1
    return r


def assemble(parts, name):
    return join([settle(p) for p in parts if p is not None], name)


def label(text, at, size, material, side=-1, depth=0.0003):
    """kit.label with a coarse curve resolution: the kit's default (12) costs thousands of
    triangles per word."""
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


# ------------------------------------------------------------------------------------ local helpers

def extrude_y(name, pts, y0, y1, material, bevel=0.0008, segs=2):
    """Extrude a cross-section [(x, z), ...] along Y from y0 to y1."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y0, z)) for x, z in pts]
    face = bm.faces.new(vs)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, y1 - y0, 0), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, material, bevel, segs)


def octagon(hw, zb, zt, c, x=0.0):
    return [(x - hw, zb + c), (x - hw + c, zb), (x + hw - c, zb), (x + hw, zb + c), (x + hw, zt - c), (x + hw - c, zt), (x - hw + c, zt), (x - hw, zt - c)]


def xform(o, m):
    o.data.transform(m)
    o.data.update()
    return o


def spun(o, axis, deg, about):
    about = Vector(about)
    return xform(o, Matrix.Translation(about) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-about))


def knurl(at, axis, r, length, n=20, depth=0.0008, w=0.0007):
    """Cutters for straight knurling round a cylinder of radius r centred at `at` along `axis`."""
    a = Vector(axis).normalized()
    orient = Vector((0, 0, 1)).rotation_difference(a).to_matrix().to_4x4()
    out = []
    for i in range(n):
        k = block("kn", (0, r, 0), (w, depth * 2, length), "steel", bevel=0)
        xform(k, Matrix.Translation(Vector(at)) @ orient @ Matrix.Rotation(2 * math.pi * i / n, 4, "Z"))
        out.append(k)
    return out


def knob(at, axis, r, length, material="black", n=16, segs=20):
    """A knurled knob: cylinder from `at` along `axis` for `length`, grooved, with a domed cap."""
    a = Vector(axis).normalized()
    p0, p1 = Vector(at), Vector(at) + a * length
    body = cyl("knob", p0, p1, r, material, segs=segs, bevel=0.0004)
    body = carve(body, *knurl((p0 + p1) / 2 + a * 0.0006, a, r, length * 0.8, n), pre=True)
    cap = cyl("kcap", p1, p1 + a * 0.0015, r * 0.85, material, r1=r * 0.6, segs=segs, bevel=0.0002)
    return assemble([body, cap], "knob")


def coil(name, p0, p1, r, wire, turns, material="bright", segs=5, steps=10):
    """Helical spring from p0 to p1."""
    L = (Vector(p1) - Vector(p0)).length
    bm = bmesh.new()
    n = int(turns * steps)
    rings = []
    for i in range(n + 1):
        t = i / n
        a = 2 * math.pi * turns * t
        c = Vector((r * math.cos(a), r * math.sin(a), -L / 2 + L * t))
        tan = Vector((-r * math.sin(a) * 2 * math.pi * turns, r * math.cos(a) * 2 * math.pi * turns, L)).normalized()
        nrm = Vector((math.cos(a), math.sin(a), 0))
        bi = tan.cross(nrm).normalized()
        rings.append([bm.verts.new(c + wire * (math.cos(2 * math.pi * k / segs) * nrm + math.sin(2 * math.pi * k / segs) * bi)) for k in range(segs)])
    for i in range(n):
        for k in range(segs):
            j = (k + 1) % segs
            bm.faces.new((rings[i][k], rings[i][j], rings[i + 1][j], rings[i + 1][k]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    _orient(bm, p0, p1)
    return _obj(name, bm, material, 0.0)


def mlok_z(name, y0, y1, count, z, x=0.0, depth=0.01, h=0.0075):
    """M-LOK slot cutters through a bottom (Z-facing) face."""
    out = []
    step = (y1 - y0) / count
    for i in range(count):
        yc = y0 + step * (i + 0.5)
        L = step * 0.62
        out.append(block(name, (x, yc, z), (h, L - h, depth), "steel", bevel=0))
        for e in (-1, 1):
            out.append(cyl(name, (x, yc + e * (L - h) / 2, z - depth / 2), (x, yc + e * (L - h) / 2, z + depth / 2), h / 2, "steel", segs=12, bevel=0))
    return out


def diag_vents(y0, y1, count, side, upper=True, L=0.02, w=0.005):
    """Rounded vent slots through a 45 degree handguard corner face."""
    cx = side * (HW - HC / 2)
    cz = (HZT - HC / 2) if upper else (HZB + HC / 2)
    nrm = Vector((side, 0, 1 if upper else -1)).normalized()
    beta = 45 * side if upper else -45 * side
    out = []
    step = (y1 - y0) / count
    for i in range(count):
        yc = y0 + step * (i + 0.5)
        b = block("v", (0, 0, 0), (w, L - w, 0.014), "steel", bevel=0)
        xform(b, Matrix.Translation((cx, yc, cz)) @ Matrix.Rotation(math.radians(beta), 4, "Y"))
        out.append(b)
        for e in (-1, 1):
            c = Vector((cx, yc + e * (L - w) / 2, cz))
            out.append(cyl("v", c - nrm * 0.007, c + nrm * 0.007, w / 2, "steel", segs=12, bevel=0))
    return out


def stipple(name, y0, y1, z0, z1, x, nx, nz, shear=0.0, r=0.0011, side=-1):
    """Dimple cutters like kit.dimples, but sheared so the grid follows a raked grip."""
    out = []
    for i in range(nx):
        for j in range(nz):
            z = z0 + (z1 - z0) * j / max(1, nz - 1)
            y = y0 + (y1 - y0) * (i + (0.5 if j % 2 else 0.0)) / nx + shear * (z - z0)
            out.append(cyl(name, (x - side * 0.002, y, z), (x + side * 0.002, y, z), r, "steel", segs=6, bevel=0))
    return out


# ------------------------------------------------------------------------------------ the rifle

def build():
    g = begin("dmr", {
        "bolt": ((0, -0.02, BORE), None),
        "charge": ((0, -0.128, 0.060), None),
        "mag": ((0, 0.09, -0.02), None),
        "trigger": ((0, 0.009, 0.0), None),
    })
    upper(g)
    lower(g)
    handguard_and_barrel(g)
    bipod(g)
    internals(g)
    magazine(g)
    standard_parts(g)
    gunsmith(g)
    clips(g)
    return g


def upper(g):
    """Billet upper: chamfered top, left window onto the carrier, ejection port with an open dust
    cover and a forward assist on the right, a full-length top rail."""
    up = extrude_y("upper", [(-0.016, 0.012), (0.016, 0.012), (0.016, 0.056), (0.010, RAIL_Z), (-0.010, RAIL_Z), (-0.016, 0.056)],
                   -0.125, 0.126, "tan", bevel=0.0009)
    cuts = [cyl("chan", (0, -0.13, BORE), (0, 0.08, BORE), 0.0133, "steel", segs=32, bevel=0)]
    cuts += [block("win", (-0.016, -0.028, 0.042), (0.012, 0.078, 0.018), "steel", bevel=0)]              # left window
    cuts += [block("port", (0.016, 0.048, 0.043), (0.012, 0.062, 0.021), "steel", bevel=0)]               # ejection port
    cuts += [prism("rch", [(-0.13, 0.054), (-0.112, RAIL_Z + 0.01), (-0.13, RAIL_Z + 0.01)], 0.05, "steel", bevel=0)]  # rear chamfer
    cuts += [block("ln", (s * 0.0165, 0.0, 0.0255), (0.0016, 0.24, 0.0016), "steel", bevel=0) for s in (-1, 1)]       # accent lines
    cuts += [block("pk", (-0.0165, -0.097, 0.040), (0.0024, 0.034, 0.024), "steel", bevel=0)]             # left billet pocket
    cuts += slots("pks", -0.109, -0.085, 6, 0.031, 0.049, -0.019, -0.0165)                                  # grip grooves in it
    cuts += [block("fp", (-0.0165, 0.088, 0.040), (0.0018, 0.05, 0.03), "steel", bevel=0)]                # front left panel
    up = carve(up, *cuts)
    parts = [up, rl("rail", -0.122, HG[1] - 0.005, RAIL_Z, "black")]
    # Window bezel with four screws.
    bez = block("bez", (-0.0168, -0.028, 0.042), (0.0016, 0.088, 0.026), "black", bevel=0.0005)
    bez = carve(bez, block("bh", (-0.0168, -0.028, 0.042), (0.01, 0.078, 0.018), "steel", bevel=0))
    parts.append(bez)
    for y in (-0.068, 0.012):
        for z in (0.031, 0.053):
            parts.append(screw((-0.0178, y, z), "-x", 0.0013, head=0.0009))
    # Forward assist housing and plunger (right rear).
    fa0, fa1 = Vector((0.026, -0.112, 0.044)), Vector((0.015, -0.070, 0.043))
    parts.append(cyl("fah", fa0, fa1, 0.0072, "tan", segs=24, bevel=0.0005))
    fa = (fa0 - fa1).normalized()
    btn = cyl("fab", fa0 - fa * 0.001, fa0 + fa * 0.009, 0.0058, "black", segs=24, bevel=0.0004)
    btn = carve(btn, *knurl(fa0 + fa * 0.0045, fa, 0.0058, 0.008, 16), pre=True)
    parts.append(btn)
    # Open dust cover hanging from its hinge under the port, with the hinge rod and latch bump.
    cover = block("cover", (0.0, 0.048, 0.0), (0.0016, 0.066, 0.024), "black", bevel=0.0004)
    cover = carve(cover, *slots("cs", 0.03, 0.066, 7, -0.004, 0.004, -0.002, -0.0006))
    xform(cover, Matrix.Translation((0.0195, 0, 0.0215)) @ Matrix.Rotation(math.radians(-25), 4, "Y"))
    parts += [cover, cyl("hinge", (0.0172, 0.014, 0.031), (0.0172, 0.082, 0.031), 0.0016, "bright", segs=10),
              block("latch", (0.0255, 0.074, 0.016), (0.003, 0.006, 0.004), "black", bevel=0.0003)]
    # Brass deflector behind the port.
    parts.append(prism("defl", [(0.008, 0.030), (0.020, 0.030), (0.016, 0.054), (0.010, 0.054)], 0.008, "tan", x=0.019, bevel=0.0008))
    g.add(assemble(parts, "upper"), "root")
    g.add(label("LONGSHOT", (-0.01665, 0.088, 0.046), 0.0068, "bright"), "root")
    g.add(label("7.62x51  DMR-20", (-0.01665, 0.088, 0.034), 0.0026, "bright"), "root")
    # Rail slot numbers along the top rail's left edge.
    for i, y in enumerate(range(-100, 500, 100)):
        g.add(label(str(i * 10 + 1), (-0.0086, y / 1000 + 0.004, RAIL_Z + 0.002), 0.0022, "bright"), "root")


def lower(g):
    """Billet lower with a flared magwell, trigger guard, ambi safety, bolt catch, pins, a stippled
    grip and the buffer tube."""
    pts = [(-0.145, 0.016), (-0.145, 0.052), (-0.126, 0.052), (-0.126, 0.012), (0.134, 0.012), (0.134, -0.012), (0.138, -0.036),
           (0.132, -0.042), (0.040, -0.042), (0.034, -0.034), (0.034, -0.008), (-0.11, -0.008), (-0.136, 0.002)]
    lo = prism("lower", pts, 0.030, "tan", bevel=0.0009)
    cuts = [block("well", (0, 0.0865, -0.016), (0.023, 0.08, 0.06), "steel", bevel=0)]
    cuts += [block("tslot", (0, 0.008, -0.006), (0.0075, 0.03, 0.012), "steel", bevel=0)]
    cuts += [block("fs", (0, 0.1375, -0.012 - i * 0.004), (0.034, 0.003, 0.0016), "steel", bevel=0, rot=-8) for i in range(6)]  # magwell front serrations
    cuts += [block("lp", (-0.0153, 0.086, -0.020), (0.0016, 0.07, 0.026), "steel", bevel=0)]                  # magwell side panel
    cuts += [block("rp", (s * 0.0153, -0.135, 0.032), (0.0016, 0.012, 0.03), "steel", bevel=0) for s in (-1, 1)]  # tower flutes
    lo = carve(lo, *cuts)
    parts = [lo]
    guard = prism("guard", [(-0.022, -0.006), (0.036, -0.006), (0.036, -0.030), (0.030, -0.037), (-0.006, -0.037), (-0.022, -0.026)],
                  0.012, "tan", bevel=0.0012, segs=3)
    guard = carve(guard, prism("gh", [(-0.016, -0.010), (0.031, -0.010), (0.031, -0.028), (0.027, -0.032), (-0.005, -0.032), (-0.016, -0.023)],
                             0.03, "steel", bevel=0))
    parts.append(guard)
    # Pins and screws on the left: front pivot, rear takedown, trigger, hammer.
    for y, z in ((0.124, 0.004), (-0.136, 0.034), (0.006, -0.001), (-0.020, -0.001)):
        parts.append(pin((0, y, z), "x", 0.0018 if abs(y) > 0.1 else 0.0013, 0.0322))
    parts.append(screw((-0.0152, -0.136, 0.044), "-x", 0.0016, head=0.0009))
    # Ambi safety: hub, long lever on the left, short one on the right.
    for s in (-1, 1):
        parts.append(cyl("hub", (s * 0.015, -0.036, 0.003), (s * 0.0175, -0.036, 0.003), 0.0052, "steel", segs=20))
        lev = prism("lever", [(-0.038, 0.0), (-0.016 if s < 0 else -0.026, 0.004), (-0.015 if s < 0 else -0.025, 0.009), (-0.038, 0.008)],
                    0.0024, "steel", x=s * 0.0182, bevel=0.0004)
        if s < 0:
            lev = carve(lev, *slots("ls", -0.024, -0.017, 4, 0.0035, 0.0095, -0.022, -0.0185, angle=0))
        parts.append(lev)
    # Bolt catch paddle on the left, mag release on the right.
    bc = prism("catch", [(0.024, -0.003), (0.044, -0.001), (0.044, 0.010), (0.028, 0.011)], 0.0028, "steel", x=-0.0163, bevel=0.0004)
    bc = carve(bc, *slots("bcs", 0.029, 0.041, 5, -0.002, 0.010, -0.019, -0.0168))
    parts.append(bc)
    parts.append(cyl("magrel", (0.015, 0.031, -0.003), (0.0195, 0.031, -0.003), 0.0048, "black", segs=20))
    parts.append(prism("fence", [(0.022, -0.012), (0.040, -0.012), (0.040, 0.006), (0.024, 0.006)], 0.003, "tan", x=0.0158, bevel=0.0008))
    # Buffer tube with a castle nut and end plate with a QD socket.
    parts.append(tube("buffer", (0, -0.156, BORE), (0, -0.31, BORE), 0.0148, 0.0125, "black", segs=24))
    parts.append(cyl("bcap", (0, -0.31, BORE), (0, -0.313, BORE), 0.0148, "black", segs=24))
    nut = ring("castle", (0, -0.152, BORE), (0, 1, 0), 0.0185, 0.0146, 0.008, "steel", segs=24)
    nut = carve(nut, *[block("cn", (0.0185 * math.sin(a), -0.149, BORE + 0.0185 * math.cos(a)), (0.004, 0.004, 0.004), "steel", bevel=0)
                     for a in [i * math.pi / 4 for i in range(8)]])
    parts.append(nut)
    plate = prism("plate", [(-0.145, 0.006), (-0.149, 0.006), (-0.149, 0.058), (-0.145, 0.058)], 0.032, "black", bevel=0.0005)
    parts.append(plate)
    parts.append(ring("qd", (-0.0172, -0.147, 0.016), (1, 0, 0), 0.0045, 0.0028, 0.003, "steel", segs=16))
    g.add(assemble(parts, "lower"), "root")
    # Grip: raked, finger-ridged, stippled on both sides, with a storage cap.
    grip = prism("grip", [(-0.022, -0.0078), (-0.027, -0.034), (-0.025, -0.042), (-0.032, -0.060), (-0.031, -0.068), (-0.038, -0.088),
                          (-0.042, -0.112), (-0.046, -0.118), (-0.088, -0.118), (-0.092, -0.110), (-0.080, -0.060), (-0.070, -0.022),
                          (-0.069, -0.010), (-0.080, -0.0078)], 0.03, "olive", bevel=0.0022, segs=3)
    grip = carve(grip, *stipple("st", -0.068, -0.040, -0.028, -0.104, -0.015, 7, 10, shear=0.28, side=-1),
               *stipple("st", -0.068, -0.040, -0.028, -0.104, 0.015, 6, 9, shear=0.28, side=1), pre=True)
    capp = prism("gcap", [(-0.047, -0.117), (-0.087, -0.117), (-0.089, -0.124), (-0.048, -0.124)], 0.027, "black", bevel=0.0012, segs=2)
    capp = carve(capp, *[block("cs", (0, -0.068 + i * 0.0045, -0.124), (0.03, 0.0018, 0.002), "steel", bevel=0) for i in range(7)])
    g.add(assemble([grip, capp, screw((0, -0.066, -0.1245), "-z", 0.0024)], "grip"), "root")
    # Markings.
    g.add(label("SAFE", (-0.0154, -0.036, 0.012), 0.0022, "bright"), "root")
    g.add(label("SEMI", (-0.0154, -0.018, 0.0094), 0.0022, "red"), "root")
    g.add(label(MAKER, (-0.0156, 0.086, -0.011), 0.0029, "bright"), "root")
    g.add(label("SN RR-06-1047   CAL 7.62", (-0.0156, 0.086, -0.026), 0.0021, "bright"), "root")
    g.add(label("MADE ON THE ISLAND", (0.0156, 0.086, -0.022), 0.0026, "bright", side=1), "root")


def handguard_and_barrel(g):
    y0, y1 = HG
    hg = extrude_y("hg", octagon(HW, HZB, HZT, HC), y0, y1, "tan", bevel=0.0009)
    inner = extrude_y("hgi", octagon(HW - 0.003, HZB + 0.003, HZT - 0.003, HC - 0.0012), y0 + 0.012, y1 + 0.01, "steel", bevel=0)
    cuts = [inner]
    for s in (-1, 1):
        cuts += mlok("ml", 0.17, 0.50, 7, 0.034, s * HW)
        cuts += diag_vents(0.17, 0.50, 7, s, upper=True)
    cuts += mlok_z("mb", 0.15, 0.50, 7, HZB)
    cuts += [block("rimg", (0, y1 - 0.003, 0.034), (0.07, 0.0016, 0.08), "steel", bevel=0)]  # end-cap seam
    # Rear clamp slit.
    cuts += [block("slit", (0, 0.132, HZB + 0.002), (0.004, 0.012, 0.01), "steel", bevel=0)]
    hg = carve(hg, *cuts, pre=True)
    parts = [hg, rl("urail", 0.178, 0.246, HZB, "black", flip=True, width=0.020)]
    for s in (-1, 1):
        ax = "x" if s > 0 else "-x"
        parts += [screw((s * (HW + 0.0004), 0.131, z), ax, 0.0021) for z in (0.020, 0.048)]
    parts.append(ring("qdh", (-HW - 0.0012, 0.153, 0.034), (1, 0, 0), 0.0062, 0.0034, 0.0026, "steel", segs=20))
    g.add(assemble(parts, "handguard"), "root")
    g.add(label("LONGSHOT  .308 FREE FLOAT", (-HW - 0.0002, 0.335, 0.0475), 0.0028, "bright"), "root")
    # Heavy fluted barrel, shoulder and threads; barrel nut; gas block and tube inside the handguard.
    bar = tube("barrel", (0, 0.07, BORE), (0, 0.578, BORE), 0.0115, 0.0039, "steel", segs=32)
    fl = []
    for k in range(6):
        a = 2 * math.pi * k / 6 + math.pi / 6
        off = Vector((0.0138 * math.cos(a), 0, 0.0138 * math.sin(a)))
        base = Vector((0, 0, BORE)) + off
        fl.append(cyl("fl", base + Vector((0, 0.215, 0)), base + Vector((0, 0.560, 0)), 0.0036, "steel", segs=8, bevel=0))
        fl.append(cyl("fl", base + Vector((0, 0.200, 0)), base + Vector((0, 0.215, 0)), 0.0005, "steel", r1=0.0036, segs=12, bevel=0))
        fl.append(cyl("fl", base + Vector((0, 0.560, 0)), base + Vector((0, 0.570, 0)), 0.0036, "steel", r1=0.0005, segs=12, bevel=0))
    bar = carve(bar, *fl)
    parts = [bar, cyl("shoulder", (0, 0.578, BORE), (0, 0.585, BORE), 0.0115, "steel", r1=0.0085, segs=32)]
    parts.append(tube("thread", (0, 0.585, BORE), (0, MUZZLE_Y, BORE), 0.0078, 0.0039, "steel", segs=32))
    parts += [ring("th", (0, 0.5875 + i * 0.0032, BORE), (0, 1, 0), 0.0081, 0.0060, 0.0012, "steel", segs=24) for i in range(4)]
    parts.append(cyl("nut", (0, 0.126, BORE), (0, 0.15, BORE), 0.0185, "steel", segs=20))
    parts.append(block("gasblk", (0, 0.40, BORE + 0.004), (0.022, 0.022, 0.03), "steel", bevel=0.0008))
    parts.append(cyl("gastube", (0, 0.11, 0.0575), (0, 0.395, 0.0575), 0.0024, "steel", segs=12))
    g.add(assemble(parts, "barrel"), "root")


def bipod(g):
    """Folded bipod clamped under the handguard front: legs lie back along the handguard."""
    yc = 0.472
    parts = [block("bclamp", (0, yc, HZB - 0.003), (0.03, 0.04, 0.006), "black", bevel=0.0008)]
    yoke = prism("yoke", [(yc - 0.022, -0.002), (yc + 0.02, -0.002), (yc + 0.016, -0.020), (yc - 0.012, -0.022)], 0.026, "black", bevel=0.0012)
    yoke = carve(yoke, *slots("ys", yc - 0.006, yc + 0.012, 4, -0.020, -0.014, -0.02, 0.02))
    parts.append(yoke)
    parts.append(knob((-0.015, yc + 0.004, -0.007), (-1, 0, 0), 0.0062, 0.010, "black", n=12, segs=16))
    parts.append(knob((0.015, yc + 0.004, -0.007), (1, 0, 0), 0.004, 0.004, "steel", n=10))
    parts.append(pin((0, yc - 0.012, -0.015), "x", 0.0016, 0.036))
    for s in (-1, 1):
        x = s * 0.0145
        parts.append(cyl("hubd", (x - 0.003, yc - 0.012, -0.015), (x + 0.003, yc - 0.012, -0.015), 0.0072, "black", segs=16))
        parts.append(tube("leg", (x, yc - 0.014, -0.014), (x, 0.318, -0.014), 0.0056, 0.0042, "black", segs=16))
        parts.append(ring("collar", (x, 0.322, -0.014), (0, 1, 0), 0.0064, 0.0050, 0.008, "black", segs=16))
        parts.append(cyl("lockb", (x + s * 0.006, 0.322, -0.014), (x + s * 0.0085, 0.322, -0.014), 0.0022, "steel", segs=12))
        inner = cyl("inleg", (x, 0.33, -0.014), (x, 0.286, -0.014), 0.0042, "bright", segs=16)
        inner = carve(inner, *[ring("nt", (x, 0.293 + i * 0.006, -0.014), (0, 1, 0), 0.005, 0.0036, 0.0016, "steel", segs=16) for i in range(3)])
        parts.append(inner)
        parts.append(cyl("foot", (x, 0.286, -0.014), (x, 0.274, -0.014), 0.0062, "rubber", r1=0.0048, segs=16, bevel=0.0006))
        parts.append(coil("spring", (x + s * 0.0062, yc - 0.008, -0.009), (x + s * 0.0062, 0.40, -0.012), 0.0022, 0.00055, 12, steps=8))
        parts.append(cyl("hook", (x + s * 0.0062, 0.40, -0.012), (x + s * 0.0062, 0.396, -0.0135), 0.0012, "bright", segs=8))
    g.add(assemble(parts, "bipod"), "root")
    g.add(label("RR-BP", (-0.0132, yc + 0.001, -0.012), 0.0026, "bright"), "root")


def internals(g):
    """Moving parts: bolt carrier group, charging handle, trigger."""
    car = cyl("carrier", (0, -0.115, BORE), (0, 0.058, BORE), 0.0125, "bright", segs=24, bevel=0.0005)
    grooves = [block("cf", (-0.0125, -0.03, BORE), (0.003, 0.05, 0.007), "steel", bevel=0)]   # flat with lightening cuts
    grooves += [cyl("ch", (-0.016, y, BORE), (-0.008, y, BORE), 0.0022, "steel", segs=14, bevel=0) for y in (-0.045, -0.03, -0.015)]
    car = carve(car, *grooves)
    parts = [car, block("gaskey", (0, -0.045, BORE + 0.0135), (0.007, 0.05, 0.006), "steel", bevel=0.0004)]
    parts += [screw((0, -0.045 + dy, BORE + 0.0168), "z", 0.0014, head=0.0008) for dy in (-0.012, 0.012)]
    parts.append(cyl("cam", (0, 0.03, BORE), (0, 0.03, BORE + 0.015), 0.0028, "steel", segs=12))
    head = cyl("bolthead", (0, 0.058, BORE), (0, 0.072, BORE), 0.0075, "bright", segs=24)
    parts.append(head)
    parts += [block("lug", (0.0085 * math.cos(a), 0.069, BORE + 0.0085 * math.sin(a)), (0.003, 0.006, 0.003), "bright", bevel=0.0002)
              for a in [i * 2 * math.pi / 7 for i in range(7)]]
    parts.append(block("extractor", (0.0105, 0.05, BORE), (0.0025, 0.03, 0.004), "steel", bevel=0.0003))
    parts.append(pin((0.0, 0.048, BORE), "x", 0.0012, 0.023))
    parts.append(cyl("firing", (0, -0.12, BORE), (0, -0.115, BORE), 0.0035, "steel", segs=12))
    g.add(assemble(parts, "bolt"), "bolt")
    # Charging handle: T-bar with an extended left latch, shaft forward under the rail.
    ch = [block("chbar", (0, -0.132, 0.0605), (0.040, 0.009, 0.008), "black", bevel=0.0008),
          block("chshaft", (0, -0.06, 0.0605), (0.008, 0.14, 0.0055), "black", bevel=0.0004)]
    latch = prism("chlatch", [(-0.140, 0.057), (-0.124, 0.057), (-0.124, 0.065), (-0.136, 0.066), (-0.142, 0.063)], 0.014, "black", x=-0.026, bevel=0.0008)
    latch = carve(latch, *slots("chs", -0.139, -0.128, 4, 0.064, 0.068, -0.033, -0.019))
    ch += [latch, block("chr", (0.024, -0.131, 0.0605), (0.008, 0.009, 0.007), "black", bevel=0.0008), pin((-0.02, -0.131, 0.0605), "z", 0.001, 0.009)]
    g.add(assemble(ch, "charge"), "charge")
    # Flat-faced trigger with a set screw.
    trig = prism("trigger", [(0.004, 0.002), (0.012, 0.002), (0.012, -0.010), (0.013, -0.025), (0.008, -0.026), (0.008, -0.010)], 0.0058, "black", bevel=0.0004)
    trig = carve(trig, *slots("ts", 0.0125, 0.0125, 1, -0.024, -0.012, -0.004, 0.004))
    g.add(assemble([trig, screw((0, 0.0105, -0.0265), "-z", 0.0011, "bright", head=0.0006)], "trigger"), "trigger")


def magazine(g):
    """20-round steel magazine with pressed ribs, witness dimples, floorplate and two rounds up top."""
    mg = prism("mag", [(0.0485, 0.010), (0.1255, 0.010), (0.128, -0.042), (0.135, -0.11), (0.138, -0.140), (0.068, -0.140), (0.062, -0.11),
                       (0.052, -0.042)], 0.0215, "steel", bevel=0.0006)
    cuts = []
    for s in (-1, 1):
        cuts += [cyl("wit", (s * 0.0102, 0.120 + 0.0001 * k, -0.052 - k * 0.019), (s * 0.0118, 0.120 + 0.0001 * k, -0.052 - k * 0.019), 0.0018, "steel", segs=12, bevel=0)
                 for k in range(4)]
    mg = carve(mg, *cuts)
    parts = [mg]
    for s in (-1, 1):
        parts.append(prism("ribs", [(0.062, -0.060), (0.11, -0.060), (0.116, -0.112), (0.070, -0.112)], 0.0012, "steel", x=s * 0.0112, bevel=0.0004))
    fp = prism("floor", [(0.062, -0.140), (0.142, -0.140), (0.145, -0.146), (0.141, -0.151), (0.060, -0.151), (0.058, -0.146)], 0.0255, "black",
               bevel=0.0012, segs=2)
    fp = carve(fp, *slots("fps", 0.07, 0.13, 8, -0.152, -0.148, -0.02, 0.02))
    parts.append(fp)
    for i, (y, z) in enumerate(((0.087, 0.014), (0.090, 0.0055))):
        x = 0.003 if i else -0.003
        parts.append(cyl("case", (x, y - 0.035, z), (x, y + 0.016, z), 0.0059, "brass", segs=18))
        parts.append(cyl("neck", (x, y + 0.016, z), (x, y + 0.022, z), 0.0059, "brass", r1=0.0044, segs=18))
        parts.append(cyl("bullet", (x, y + 0.022, z), (x, y + 0.04, z), 0.0039, "copper", r1=0.0012, segs=18))
    g.add(assemble(parts, "mag"), "mag")
    for k, n in enumerate(("5", "10", "15", "20")):
        g.add(label(n, (-0.0113, 0.110, -0.052 - k * 0.019), 0.0035, "bright"), "mag")
    g.add(label("7.62 STEEL 20", (-0.0118, 0.090, -0.086), 0.0034, "bright"), "mag")


# ------------------------------------------------------------------------------- standard parts

def standard_parts(g):
    muzzle_brake(g)
    irons(g)
    precision_stock(g)


def muzzle_brake(g):
    y0, y1 = 0.584, 0.672
    sec = [(-0.017, -0.009), (-0.011, -0.0145), (0.011, -0.0145), (0.017, -0.009), (0.017, 0.009), (0.011, 0.0145), (-0.011, 0.0145), (-0.017, 0.009)]
    br = extrude_y("brake", [(x, z + BORE) for x, z in sec], y0, y1, "steel", bevel=0.001)
    cuts = [hole_through("bore", (0, (y0 + y1) / 2, BORE), 0.0058, "y", 0.12, segs=24)]
    cuts += [block("port", (0, y, BORE), (0.05, 0.0125, 0.020), "steel", bevel=0) for y in (0.606, 0.628, 0.650)]
    cuts += [cyl("top", (sx * 0.0065, y, BORE), (sx * 0.0065, y, BORE + 0.03), 0.0026, "steel", segs=14, bevel=0) for y in (0.6175, 0.6395) for sx in (-1, 1)]
    cuts += [block("flat", (s * 0.0175, 0.592, BORE), (0.003, 0.012, 0.03), "steel", bevel=0) for s in (-1, 1)]   # wrench flats
    cuts += [block("cr", (0, y1, BORE + s * 0.0146), (0.04, 0.012, 0.004), "steel", bevel=0, rot=s * 30) for s in (-1, 1)]
    br = carve(br, *cuts)
    nut = ring("jam", (0, 0.580, BORE), (0, 1, 0), 0.0136, 0.0078, 0.008, "black", segs=32)
    nut = carve(nut, *knurl((0, 0.580, BORE), (0, 1, 0), 0.0136, 0.01, 16, depth=0.001, w=0.0012), pre=True)
    o = assemble([br, nut, label("LS-3", (-0.0172, 0.660, BORE), 0.0034, "bright")], "att.muzzle.bare")
    o.name = "att.muzzle.bare"
    g.add(o, "root")


def irons(g):
    z = RAIL_TOP
    parts = []
    # Rear: clamp base, aperture tower between guard ears, windage knob on the left.
    yr = -0.104
    parts.append(block("rbase", (0, yr, z + 0.004), (0.023, 0.024, 0.008), "black", bevel=0.0008))
    parts.append(block("rclamp", (0.013, yr, z - 0.002), (0.004, 0.018, 0.012), "black", bevel=0.0005))
    parts.append(screw((0.0152, yr, z - 0.001), "x", 0.0017))
    tower = prism("rtower", [(yr - 0.006, z + 0.008), (yr + 0.006, z + 0.008), (yr + 0.0035, z + 0.031), (yr - 0.0035, z + 0.031)], 0.012, "black",
                  bevel=0.0005)
    tower = carve(tower, hole_through("ap", (0, yr, z + 0.025), 0.0016, "y", 0.03, segs=16))
    parts.append(tower)
    for s in (-1, 1):
        parts.append(prism("rear", [(yr - 0.007, z + 0.008), (yr + 0.007, z + 0.008), (yr + 0.005, z + 0.033), (yr - 0.005, z + 0.033)],
                           0.0024, "black", x=s * 0.0085, bevel=0.0004))
    parts.append(knob((-0.0115, yr, z + 0.013), (-1, 0, 0), 0.0045, 0.005, "black", n=14))
    parts.append(pin((0, yr, z + 0.0105), "x", 0.0012, 0.022))
    # Front: base, hooded ears and a post.
    yf = 0.488
    parts.append(block("fbase", (0, yf, z + 0.004), (0.023, 0.022, 0.008), "black", bevel=0.0008))
    parts.append(block("fclamp", (0.013, yf, z - 0.002), (0.004, 0.016, 0.012), "black", bevel=0.0005))
    parts.append(screw((0.0152, yf, z - 0.001), "x", 0.0017))
    for s in (-1, 1):
        ear = prism("ear", [(yf - 0.008, z + 0.008), (yf + 0.008, z + 0.008), (yf + 0.005, z + 0.040), (yf - 0.005, z + 0.040)], 0.0028, "black",
                    x=s * 0.0075, bevel=0.0004)
        ear = carve(ear, hole_through("eh", (s * 0.0075, yf, z + 0.020), 0.003, "x", 0.01, segs=14))
        parts.append(ear)
    parts.append(block("fpb", (0, yf, z + 0.011), (0.009, 0.007, 0.006), "black", bevel=0.0004))
    parts.append(cyl("post", (0, yf, z + 0.014), (0, yf, z + 0.034), 0.0013, "black", segs=10))
    parts.append(cyl("fdot", (-0.0006, yf - 0.0007, z + 0.032), (-0.0006, yf - 0.0007, z + 0.033), 0.0008, "lamp", segs=8, bevel=0))
    parts.append(pin((0, yf, z + 0.0105), "x", 0.0012, 0.02))
    o = assemble(parts, "att.optic.irons")
    o.name = "att.optic.irons"
    g.add(o, "root")


def precision_stock(g):
    """Precision stock: slab body round the buffer tube, adjustable cheek riser on posts with a
    knurled lock knob, spacer stack and a grooved butt pad with its own knurled length knob."""
    body = prism("stock", [(-0.150, 0.060), (-0.336, 0.060), (-0.345, 0.054), (-0.345, -0.068), (-0.336, -0.075), (-0.300, -0.075),
                           (-0.292, -0.066), (-0.262, -0.036), (-0.200, 0.012), (-0.170, 0.022), (-0.150, 0.024)],
                 0.031, "olive", bevel=0.0018, segs=3)
    cuts = [prism("hole", [(-0.238, 0.010), (-0.326, 0.010), (-0.326, -0.052), (-0.306, -0.054)], 0.05, "steel", bevel=0)]
    cuts += [hole_through("tubeh", (0, -0.20, BORE), 0.0152, "y", 0.12, segs=32)]
    cuts += [block("ps", (s * 0.0155, -0.19, BORE), (0.002, 0.05, 0.022), "steel", bevel=0) for s in (-1, 1)]   # side pockets
    cuts += slots("bs", -0.335, -0.300, 7, -0.077, -0.073, -0.02, 0.02)                                          # hook serrations
    body = carve(body, *cuts)
    parts = [body]
    # Cheek riser raised on two posts.
    riser = prism("riser", [(-0.188, 0.064), (-0.330, 0.064), (-0.332, 0.076), (-0.322, 0.082), (-0.200, 0.082), (-0.188, 0.074)],
                  0.028, "olive", bevel=0.002, segs=3)
    pad = prism("cheekpad", [(-0.205, 0.0815), (-0.318, 0.0815), (-0.318, 0.0835), (-0.205, 0.0835)], 0.022, "rubber", bevel=0.0008)
    parts += [riser, pad]
    for y in (-0.212, -0.302):
        parts.append(cyl("post", (0, y, 0.056), (0, y, 0.066), 0.0042, "bright", segs=16))
        parts.append(ring("pcol", (0, y, 0.061), (0, 0, 1), 0.0055, 0.0040, 0.002, "steel", segs=16))
    parts.append(knob((-0.0155, -0.257, 0.050), (-1, 0, 0), 0.0072, 0.010, "black"))
    parts.append(knob((0.0155, -0.257, 0.050), (1, 0, 0), 0.0050, 0.004, "black", n=12))
    # Spacer stack and butt pad.
    for i, m in enumerate(("black", "olive", "black")):
        ya = -0.345 - i * 0.005
        parts.append(prism("spacer", [(ya, 0.058), (ya - 0.0048, 0.058), (ya - 0.0048, -0.072), (ya, -0.072)], 0.032, m, bevel=0.0006))
    bp = prism("buttpad", [(-0.360, 0.064), (-0.372, 0.061), (-0.377, 0.040), (-0.378, -0.040), (-0.373, -0.070), (-0.360, -0.077)],
               0.035, "rubber", bevel=0.0025, segs=3)
    bp = carve(bp, *[block("bg", (0, -0.3775, -0.05 + i * 0.008), (0.04, 0.003, 0.0026), "steel", bevel=0) for i in range(13)])
    parts.append(bp)
    for z in (0.035, -0.045):
        parts.append(screw((-0.0162, -0.352, z), "-x", 0.002))
    parts.append(knob((-0.0155, -0.322, 0.035), (-1, 0, 0), 0.0068, 0.009, "black"))
    parts.append(ring("sqd", (-0.0158, -0.175, 0.030), (1, 0, 0), 0.0058, 0.0032, 0.003, "steel", segs=18))
    parts.append(rl("brail", -0.334, -0.302, -0.075, "black", flip=True, width=0.02))
    parts.append(label("LS PRECISION", (-0.0157, -0.290, 0.030), 0.0036, "bright"))
    parts.append(label("LOP", (-0.0157, -0.322, 0.047), 0.0025, "bright"))
    parts.append(label("CHEEK", (-0.0157, -0.257, 0.063), 0.0022, "bright"))
    o = assemble(parts, "att.stock.standard")
    o.name = "att.stock.standard"
    g.add(o, "root")


# ------------------------------------------------------------------------------------- gunsmith

def long_scope(g, top):
    """5-25x56 first-focal-plane scope in a one-piece cantilever mount."""
    x, y, z = top
    zc = z + 0.042
    P = lambda yy, dz=0.0: (x, y + yy, zc + dz)  # noqa: E731
    parts = []
    # Ocular: eye cup, diopter, power ring with a throw lever.
    parts.append(tube("eyecup", P(-0.205), P(-0.196), 0.0225, 0.0185, "rubber", segs=40))
    parts.append(cyl("rlens", P(-0.199), P(-0.198), 0.0186, "glass", segs=40, bevel=0))
    for w, h in ((0.024, 0.00035), (0.00035, 0.024)):
        parts.append(block("ret", P(-0.1994), (w, 0.0003, h), "reticle", bevel=0))
    parts.append(cyl("retdot", P(-0.1995), P(-0.1993), 0.0007, "reticle", segs=8, bevel=0))
    oc = cyl("ocular", P(-0.196), P(-0.150), 0.0215, "black", segs=40, bevel=0.0006)
    oc = carve(oc, *knurl(P(-0.188), (0, 1, 0), 0.0215, 0.01, 28), pre=True)
    parts.append(oc)
    parts.append(cyl("taper", P(-0.150), P(-0.132), 0.0205, "black", r1=0.018, segs=40))
    pr = cyl("power", P(-0.132), P(-0.106), 0.0198, "black", segs=40)
    pr = carve(pr, *knurl(P(-0.119), (0, 1, 0), 0.0198, 0.018, 30, depth=0.001), pre=True)
    parts.append(pr)
    parts.append(prism("throw", [(y - 0.128, zc + 0.018), (y - 0.110, zc + 0.018), (y - 0.112, zc + 0.027), (y - 0.126, zc + 0.027)], 0.004, "black",
                       x=x - 0.008, bevel=0.0006))
    # Main 34 mm tube and turret saddle.
    parts.append(cyl("main", P(-0.106), P(0.118), 0.017, "black", segs=40))
    parts.append(cyl("saddle", P(-0.024), P(0.024), 0.0205, "black", segs=40))
    parts.append(block("sbox", P(0.0, 0.004), (0.036, 0.042, 0.03), "black", bevel=0.003, segs=3))
    # Elevation turret: knurled cap, zero-stop ring, index marks.
    parts.append(cyl("eskirt", P(0, 0.018), P(0, 0.026), 0.0125, "black", segs=36))
    et = cyl("ecap", P(0, 0.026), P(0, 0.044), 0.0135, "black", segs=36)
    et = carve(et, *knurl(P(0, 0.037), (0, 0, 1), 0.0135, 0.010, 32), pre=True)
    parts += [et, ring("ezero", P(0, 0.0275), (0, 0, 1), 0.0139, 0.0125, 0.0018, "bright", segs=36)]
    parts += [block("tick", (x + 0.0138 * math.sin(a), y + 0.0138 * math.cos(a), zc + 0.0305), (0.0006, 0.0006, 0.004 if i % 5 == 0 else 0.0022),
                    "bright", bevel=0) for i, a in enumerate([k * 2 * math.pi / 30 for k in range(30)])]
    parts.append(cyl("ecap2", P(0, 0.044), P(0, 0.0455), 0.011, "steel", segs=32))
    # Windage turret (right), parallax / illumination turret (left, red illumination ring).
    wt = cyl("wind", (x + 0.018, y, zc), (x + 0.036, y, zc), 0.0122, "black", segs=32)
    wt = carve(wt, *knurl((x + 0.030, y, zc), (1, 0, 0), 0.0122, 0.009, 28), pre=True)
    parts.append(wt)
    lt = cyl("plx", (x - 0.018, y, zc), (x - 0.034, y, zc), 0.0122, "black", segs=32)
    lt = carve(lt, *knurl((x - 0.029, y, zc), (1, 0, 0), 0.0122, 0.008, 28), pre=True)
    parts += [lt, ring("illum", (x - 0.021, y, zc), (1, 0, 0), 0.0127, 0.011, 0.0022, "red", segs=32)]
    parts.append(cyl("plxcap", (x - 0.034, y, zc), (x - 0.036, y, zc), 0.0095, "steel", segs=24))
    # Objective: taper, bell, recessed front glass, sunshade lip.
    parts.append(cyl("otaper", P(0.118), P(0.160), 0.017, "black", r1=0.031, segs=48))
    parts.append(cyl("bell", P(0.160), P(0.205), 0.031, "black", segs=48))
    parts.append(tube("shade", P(0.205), P(0.222), 0.0312, 0.0285, "black", segs=48))
    parts.append(cyl("flens", P(0.208), P(0.209), 0.0286, "glass", segs=48, bevel=0))
    parts.append(ring("bellr", P(0.2), (0, 1, 0), 0.0316, 0.029, 0.0025, "steel", segs=48))
    # One-piece cantilever mount: base on the rail, two uprights, split ring caps with screws, cross bolts, level.
    parts.append(block("mbase", (x, y + 0.004, z + 0.005), (0.024, 0.17, 0.010), "black", bevel=0.0012))
    mb = []
    for ry in (-0.068, 0.076):
        up = block("upright", (x, y + ry, (z + zc) / 2 + 0.002), (0.022, 0.016, zc - z - 0.004), "black", bevel=0.0008)
        up = carve(up, block("ul", (x - 0.011, y + ry, (z + zc) / 2), (0.004, 0.008, 0.012), "steel", bevel=0))
        mb.append(up)
        mb.append(ring("mring", (x, y + ry, zc), (0, 1, 0), 0.0215, 0.0168, 0.016, "black", segs=40))
        mb.append(ring("rsplit", (x, y + ry, zc), (0, 1, 0), 0.0218, 0.0212, 0.0165, "steel", segs=40))
        for dy in (-0.0045, 0.0045):
            for sx in (-1, 1):
                mb.append(screw((x + sx * 0.0165, y + ry + dy, zc + 0.0135), "z", 0.0015, head=0.0012))
        mb.append(cyl("xbolt", (x + 0.012, y + ry, z - 0.002), (x + 0.018, y + ry, z - 0.002), 0.0042, "steel", segs=6))
        mb.append(cyl("xnut", (x - 0.012, y + ry, z - 0.002), (x - 0.015, y + ry, z - 0.002), 0.0036, "steel", segs=16))
    parts += mb
    parts.append(block("lvl", (x - 0.012, y + 0.004, z + 0.012), (0.006, 0.024, 0.006), "black", bevel=0.0008))
    parts.append(cyl("vial", (x - 0.0151, y - 0.004, z + 0.012), (x - 0.0151, y + 0.012, z + 0.012), 0.0018, "yellow", segs=12, bevel=0))
    parts.append(label("5-25x56 FFP", (x - 0.0172, y - 0.046, zc + 0.002), 0.0032, "bright"))
    parts.append(label("RR OPTICS", (x - 0.0172, y + 0.10, zc + 0.002), 0.0030, "bright"))
    parts.append(label("MRAD", (x - 0.0136, y, zc + 0.022), 0.0026, "bright"))
    o = assemble(parts, "att.optic.scope")
    o.name = "att.optic.scope"
    lens_socket(g, "scope.eye", P(-0.2), (0.0186, 0.0186, 0.0186), "root")
    return g.add(o, "root")


def gunsmith(g):
    top = (0, 0.0, RAIL_TOP)
    optic_reddot(g, top)
    long_scope(g, top)
    muzzle_parts(g, (0, MUZZLE_Y, BORE), r=0.0105, supp_len=0.19, supp_r=0.022)
    under = (0, 0.212, UNDER_Z)
    grip_parts(g, under)
    stock_at = (0, -0.152, BORE)
    stock_parts(g, stock_at)
    g.socket("optic", top)
    g.socket("muzzle", (0, MUZZLE_Y, BORE))
    g.socket("under", under)
    g.socket("stock", stock_at)
    g.socket("eject", (0.02, 0.048, 0.046))


# ---------------------------------------------------------------------------------------- clips

def clips(g):
    rest = ((0, 0, 0), (0, 0, 0))
    g.clip("idle", 1.0, {})
    g.clip("fire", 0.2, {
        "root": [(0, *rest), (0.022, (0, -0.030, 0.009), (11, 0, 1.6)), (0.07, (0, -0.014, 0.005), (6, 0, 0.8)), (0.13, (0, -0.003, 0.001), (1.2, 0, 0.1)),
                 (0.2, *rest)],
        "bolt": [(0, *rest), (0.028, (0, -0.088, 0), (0, 0, 0)), (0.042, (0, -0.088, 0), (0, 0, 0)), (0.10, *rest)],
        "trigger": [(0, *rest), (0.01, (0, 0, 0), (-14, 0, 0)), (0.13, (0, 0, 0), (-14, 0, 0)), (0.17, *rest)],
    })
    ax = Vector((0.04, -1)).normalized()
    g.clip("reload", 2.6, {
        "root": [(0, *rest), (0.3, (0.012, 0.0, 0.032), (10, 24, 0)), (1.1, (0.012, 0.0, 0.03), (12, 26, 0)), (1.32, (0.006, 0.0, 0.034), (16, 20, 0)),
                 (1.6, (-0.008, -0.012, 0.024), (6, -20, -8)), (1.95, (-0.008, -0.012, 0.024), (5, -22, -8)), (2.3, (0, 0, 0.004), (2, -3, 0)),
                 (2.6, *rest)],
        "mag": mag_drop((ax.x, ax.y), 0.35, 1.12, 1.30),
        "charge": [(0, *rest), (1.62, *rest), (1.75, (0, -0.058, 0), (0, 0, 0)), (1.82, (0, -0.058, 0), (0, 0, 0)), (1.88, *rest)],
        "bolt": [(0, *rest), (1.62, *rest), (1.75, (0, -0.058, 0), (0, 0, 0)), (1.82, (0, -0.058, 0), (0, 0, 0)), (1.86, *rest)],
    })
    g.clip("draw", 0.6, {"root": [(0, (0, -0.06, -0.16), (-50, 0, 12)), (0.42, (0, 0.004, 0.004), (3, 0, 0)), (0.6, *rest)]})
    g.clip("inspect", 3.0, {
        "root": [(0, *rest), (0.5, (-0.03, 0.02, 0.03), (10, -32, 24)), (1.3, (-0.03, 0.02, 0.032), (12, -36, 28)), (1.8, (0.02, 0.0, 0.025), (-6, 30, -18)),
                 (2.5, (0.02, 0.0, 0.025), (-6, 33, -20)), (2.9, *rest), (3.0, *rest)],
        "charge": [(0, *rest), (1.9, *rest), (2.02, (0, -0.026, 0), (0, 0, 0)), (2.25, (0, -0.026, 0), (0, 0, 0)), (2.34, *rest)],
        "bolt": [(0, *rest), (1.9, *rest), (2.02, (0, -0.026, 0), (0, 0, 0)), (2.25, (0, -0.026, 0), (0, 0, 0)), (2.33, *rest)],
    })


STANDARD = ["att.optic.irons", "att.muzzle.bare", "att.stock.standard"]

VIEW = {"cam": (-1.45, 0.15, 0.50), "look": (0, 0.15, 0.0), "lens": 50, "show": tuple(STANDARD)}

SPEC = {"build": build, "length": (0.85, 0.98), "tris": (20000, 70000),
        "bones": ["root", "bolt", "charge", "mag", "trigger"],
        "sockets": ["muzzle", "eject", "optic", "under", "stock", "scope.eye", "reddot.lens"], "attachments": SLOT_ATTS + STANDARD,
        "parts": {"mesh.root": "root", "mesh.bolt": "bolt", "mesh.charge": "charge", "mesh.mag": "mag", "mesh.trigger": "trigger"},
        "moves": {"fire": ["root", "bolt", "trigger"], "reload": ["root", "mag", "charge", "bolt"], "draw": ["root"],
                  "inspect": ["root", "charge", "bolt"]},
        "view": VIEW}
