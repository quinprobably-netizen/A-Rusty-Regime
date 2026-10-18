"""Breaker, Deserters: the heavy. An ex-Regime breacher in the cult's own bone-white plate with the
uplinks torn out and the code scratched off: chest, abdomen, back, shoulders, forearms and thighs
repainted cream with clay hazard stripes and stencilled numbers. A cracked Regime helmet with the
face shield torn off (one hinge stub left) so the face shows again, a battle belt of breaching charge
pouches with a firing device and a det-cord spool, a strip charge across the back, heavy boots with
steel toe caps and shin guards.

Tints: primary = undersuit (slate), secondary = trousers (kraft), accent = straps (clay).
"""

import math

import bmesh
from mathutils import Matrix, Vector

import kit
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS, FEET

kit.hs.PALETTE["brk_skin"] = ((0.50, 0.33, 0.24), (0.54, 0.37, 0.27), 0.0, 0.6, 0.0, 0)
kit.hs.PALETTE["brk_scar"] = ((0.62, 0.42, 0.34), (0.66, 0.46, 0.38), 0.0, 0.5, 0.0, 0)


# ------------------------------------------------------------------------------------ local helpers

def hit(obj, p, d, far=1.0):
    """First point of `obj` met by a ray travelling along `d` that passes through `p`, from outside."""
    bpy_update()
    d = Vector(d).normalized()
    ok, loc, n, _ = obj.ray_cast(Vector(p) - d * far, d)
    if not ok:
        print(f"  miss: {obj.name} ({len(obj.data.polygons)} faces) at {tuple(round(v, 3) for v in p)} along {tuple(d)}")
    return (Vector(loc), Vector(n)) if ok else (None, None)


def bpy_update():
    import bpy
    bpy.context.view_layer.update()


def frame(n, t):
    """An orthonormal frame (t, n x t, n) with z along the surface normal `n`."""
    n = Vector(n).normalized()
    t = Vector(t)
    t = (t - n * t.dot(n)).normalized()
    return t, n.cross(t), n


def obox(name, c, t, n, size, material, bevel=0.0):
    """A box centred at `c`, its x along `t` and its z along `n`."""
    tx, ty, tz = frame(n, t)
    o = kit.block(name, (0, 0, 0), size, material, bevel=bevel)
    m = Matrix((tx, ty, tz)).transposed().to_4x4()
    m.translation = Vector(c)
    o.data.transform(m)
    return o


def bolt(p, n, r=0.006, material="gunmetal", head=0.004):
    """A socket-head screw on a curved surface, facing along the normal `n` (None if `p` is None)."""
    if p is None:
        return None
    n = Vector(n).normalized()
    p = Vector(p)
    s = kit.cyl("screw", p - n * head * 0.6, p + n * head * 0.4, r, material, segs=10, bevel=0)
    hexa = kit.cyl("hex", p + n * (head * 0.4 - 0.0015), p + n * (head * 0.4 + 0.002), r * 0.45, material, segs=6, bevel=0)
    return kit.cut(s, hexa, solver="FLOAT")


DETAIL = 0.3  # shell density for plates and their paint (the kit default 0.5 blows the budget on plate-heavy builds)
SOFT = 0.35  # shell density for cloth


def plate(src, cutter, name, material, offset=0.012, thick=0.008, bevel=0.002, keep=None, bones=None, detail=DETAIL):
    """kit.plate with a lower shell density."""
    o = kit.shell(src, keep, name, material, offset=offset, thick=thick, bevel=0.0, bones=bones, detail=detail)
    o = kit.intersect(o, cutter)
    o["bevel"] = bevel
    o["segs"] = 1  # a single chamfer: two segments double a plate's triangles
    o["shaded"] = False
    return o


def paint(src, outer, name, cutters, keep=None, bones=None, material="clay", detail=DETAIL):
    """A paint layer 1 mm proud of a plate whose outer surface sits `outer` off `src` (same keep and
    bones as the plate), trimmed to every cutter in `cutters`."""
    return kit.shell(src, keep, name, material, offset=outer + 0.001, thick=0.0016, bones=bones, detail=detail, inside=cutters)


def below(z, name="trim"):
    """A cutter keeping everything under height z (clean shell edges)."""
    return kit.block(name, (0, 0, z - 1.0), (3.0, 3.0, 2.0), "steel", bevel=0)


def above(z, name="trim"):
    return kit.block(name, (0, 0, z + 1.0), (3.0, 3.0, 2.0), "steel", bevel=0)


def cloth(c, src, keep, name, material, offset=0.008, thick=0.004, smooth_iter=0, bones=None, detail=0.5, inside=None, outside=None):
    """kit.shell for clothes that keeps the bone-heat weights of the faces it was cut from, and adds
    the result to `c` as already weighted. (c.add copies weights from the nearest body surface, and
    where a hanging forearm sits a centimetre from the hip, waist cloth picks up forearm weights and
    tears into a plank when the arms lift.)"""
    import bpy
    me = src.data.copy()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.matrix_world = src.matrix_world
    for g in src.vertex_groups:
        o.vertex_groups.new(name=g.name)
    dom = kit.dominant(src) if bones else None
    bm = bmesh.new()
    bm.from_mesh(me)
    keep = keep or (lambda p: True)

    def ok(f):
        if not keep(f.calc_center_median()):
            return False
        return not dom or sum(dom[v.index] in bones for v in f.verts) * 2 >= len(f.verts)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not ok(f)], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.normal_update()
    for v in bm.verts:
        v.co = v.co + v.normal * offset
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    me.materials.append(kit.mat(material))
    if smooth_iter:
        kit.smooth(o, smooth_iter, 0.5)
    if detail < 1.0 and len(me.polygons) > 200:
        kit.decimate(o, detail)
    if thick:
        m = o.modifiers.new("thick", "SOLIDIFY")
        m.thickness = thick
        m.offset = 1.0
        m.use_even_offset = False
        m.use_rim = True
        kit.hs._apply(o, m.name)
    for cutter in inside or ():
        o = kit.intersect(o, cutter)
    for cutter in outside or ():
        o = kit.subtract(o, cutter)
    fill_weights(o)
    o["bevel"] = 0.0
    o["shaded"] = True
    for p in o.data.polygons:
        p.use_smooth = True
    c.parts.append((o, "DONE", None))
    return o


def fill_weights(o):
    """Give vertices a boolean trim created without weights those of the nearest weighted vertex."""
    from mathutils.kdtree import KDTree
    vs = o.data.vertices
    done = [v for v in vs if sum(g.weight for g in v.groups) > 1e-4]
    if len(done) == len(vs) or not done:
        return
    kd = KDTree(len(done))
    for i, v in enumerate(done):
        kd.insert(v.co, i)
    kd.balance()
    for v in vs:
        if sum(g.weight for g in v.groups) > 1e-4:
            continue
        _, i, _ = kd.find(v.co)
        for g in done[i].groups:
            o.vertex_groups[g.group].add([v.index], g.weight, "REPLACE")


def torso(b, chest=1.0, gut=0.0, muscle=1.0, neck=1.0, target=5000, legs=False):
    """The torso of kit.body (same elements, no arms; thighs with `legs`): a clean surface to cut chest
    and back plates from without the armpit, where the arms' faces punch holes in a bone-filtered
    shell, and to drape cloth over. Delete it when done."""
    k, w, m = b.k, b.width, b.bulk * muscle
    J = b.j
    E, C = kit.ellipsoid, kit.capsule
    el = [E(J("hips", 0.2) + Vector((0, 0.01, 0)), 0.11 * k, (1.25 * w * m, 0.85 * m, 0.8)),
          E(J("spine", 0.4) + Vector((0, -0.01 - 0.03 * gut, 0)), 0.10 * k, ((1.1 + 0.15 * gut) * w * m, (0.8 + 0.3 * gut) * m, 1.0)),
          E(J("chest", 0.45), 0.13 * k, (1.15 * w * m * chest, 0.75 * m, 1.0)),
          C(J("neck", 0.0), J("neck", 1.0) + Vector((0, 0.005, 0)), 0.05 * k * neck * m)]
    for sx in (1, -1):
        el.append(E(J("chest", 0.62) + Vector((sx * 0.06 * w, -0.055 * m * chest, 0)), 0.065 * k, (1.1 * m, 0.6 * m, 0.75), stiff=1.5))
        el.append(E(J("chest", 0.5) + Vector((sx * 0.09 * w, 0.03, 0)), 0.07 * k, (0.9 * m, 0.7 * m, 1.1), stiff=1.5))
        el.append(C(J("neck", 0.0) + Vector((sx * 0.03, 0.01, -0.01)), J("shoulder." + ("L" if sx > 0 else "R"), 0.9) + Vector((0, 0.01, 0.01)),
                    0.045 * k * m, stiff=1.5))
        el.append(E(J("hips", 0.0) + Vector((sx * 0.06 * w, 0.06, -0.05)), 0.075 * k, (1.0 * m, 0.9 * m, 1.0), stiff=1.5))
        if legs:
            s = "L" if sx > 0 else "R"
            el.append(C(J("upper_leg." + s, 0.0) + Vector((0, 0, 0.02)), J("upper_leg." + s, 0.97), 0.068 * k * m))
            el.append(E(J("upper_leg." + s, 0.3) + Vector((0, -0.01, 0)), 0.075 * k, (0.95 * m, 0.95 * m, 1.6), stiff=1.4))
    return kit.meta("torso_proxy", el, "steel", res=0.01 * k, target=target)


def clip(poly, lo, hi):
    """Clip a 2-D polygon to lo <= u <= hi (Sutherland-Hodgman on the first coordinate)."""
    def side(pts, inside, at):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            if inside(b):
                if not inside(a):
                    out.append(cross(a, b, at))
                out.append(b)
            elif inside(a):
                out.append(cross(a, b, at))
        return out

    def cross(a, b, u):
        t = (u - a[0]) / (b[0] - a[0])
        return (u, a[1] + (b[1] - a[1]) * t)
    pts = side(list(poly), lambda p: p[0] >= lo, lo)
    return side(pts, lambda p: p[0] <= hi, hi) if pts else []


def bars(u0, u1, v0, v1, w, slant):
    """Hazard-stripe bars: parallelograms of width `w` leaning by `slant`, clipped to [u0, u1]."""
    out = []
    u = u0 - abs(slant) - w
    while u < u1 + abs(slant):
        poly = clip([(u, v0), (u + w, v0), (u + w + slant, v1), (u + slant, v1)], u0, u1)
        if len(poly) >= 3:
            out.append(poly)
        u += 2 * w
    return out


def stripes_y(u0, u1, v0, v1, w, slant, y0, y1):
    """Bars in the front view (x, z), extruded along Y: stripes on plates facing front or back."""
    return kit.join([kit.slab("bar", p, y0, y1) for p in bars(u0, u1, v0, v1, w, slant)], "stripes")


def stripes_x(u0, u1, v0, v1, w, slant, x0, x1):
    """Bars in the side view (y, z), extruded along X: stripes on plates facing the side."""
    return kit.join([kit.prism("bar", p, x1 - x0, "steel", x=(x0 + x1) / 2, bevel=0) for p in bars(u0, u1, v0, v1, w, slant)], "stripes")


def scratches(obj, spots, d, depth=0.006):
    """Cut thin scratch grooves into `obj` at (point, angle, length) spots seen along `d`."""
    cutters = []
    for p, ang, length in spots:
        loc, n = hit(obj, p, d)
        if loc is None:
            continue
        up = Vector((0, 0, 1))
        side = n.cross(up).normalized() if abs(n.z) < 0.9 else Vector((1, 0, 0))
        t = side * math.cos(math.radians(ang)) + n.cross(side) * math.sin(math.radians(ang))
        cutters.append(obox("scratch", loc, t, n, (length, 0.0022, depth), "steel"))
    if cutters:
        kit.cut(obj, *cutters, solver="MANIFOLD")
    return obj


def sweep(name, pts, normals, width, thick, material):
    """A flat ribbon along `pts`, its face along the per-point `normals` (cracks, curved straps)."""
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(pts):
        a, c = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        tan = (c - a).normalized()
        n = normals[i]
        n = (n - tan * n.dot(tan)).normalized()
        s = tan.cross(n).normalized()
        rings.append([bm.verts.new(p + s * sw * width / 2 + n * nn * thick / 2) for sw, nn in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return kit.hs._obj(name, bm, material, bevel=0.0)


def hug(name, src, c, axis, grow, width, thick, material, n=18, smooth=2):
    """A strap ring that hugs `src` around the point `c` (inside it) in the plane across `axis`: the
    surface is found by rays from `c` outward, then grown by `grow`."""
    c = Vector(c)
    a = Vector(axis).normalized()
    u = a.cross(Vector((0, 0, 1)) if abs(a.z) < 0.9 else Vector((1, 0, 0))).normalized()
    v = a.cross(u).normalized()
    bpy_update()
    dirs, rs = [], []
    for i in range(n):
        ang = 2 * math.pi * i / n
        d = u * math.cos(ang) + v * math.sin(ang)
        ok, loc, _, _ = src.ray_cast(c, d)
        dirs.append(d)
        rs.append((Vector(loc) - c).length if ok else None)
    good = [r for r in rs if r is not None]
    rs = [r if r is not None else max(good) for r in rs]
    for _ in range(smooth):
        rs = [max(rs[i], (rs[i - 1] + rs[i] + rs[(i + 1) % n]) / 3) for i in range(n)]
    pts = [c + d * (r + grow + thick / 2) for d, r in zip(dirs, rs)]
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(pts):
        tan = (pts[(i + 1) % n] - pts[i - 1]).normalized()
        nn = dirs[i]
        nn = (nn - tan * nn.dot(tan)).normalized()
        rings.append([bm.verts.new(p + a * sw * width / 2 + nn * k * thick / 2) for sw, k in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for i in range(n):
        r0, r1 = rings[i], rings[(i + 1) % n]
        for q in range(4):
            j = (q + 1) % 4
            bm.faces.new((r0[q], r0[j], r1[j], r1[q]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return kit.hs._obj(name, bm, material, bevel=min(width, thick) * 0.3, segs=1)


def arc(src, c, x, angles, grow):
    """Points hugging `src` over a ridge: rays in the (y, z) plane at `x` aimed at `c` from `angles`
    (degrees; 0 straight down onto the ridge, negative from the front, positive from the back)."""
    out = []
    for a in angles:
        r = math.radians(a)
        d = Vector((0, -math.sin(r), -math.cos(r)))  # direction of travel, toward c
        loc, n = hit(src, Vector((x, c.y, c.z)), d, far=0.5)
        if loc is not None:
            out.append(loc + n * grow)
    return out


def egg(name, c, radii, thick, material, segs=(40, 24)):
    """A hollow ellipsoid shell (helmets, masks): outer radii `radii`, wall `thick`."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs[0], v_segments=segs[1], radius=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * radii[0], v.co.y * radii[1], v.co.z * radii[2])) + Vector(c)
    o = kit.hs._obj(name, bm, material, bevel=0.0)
    m = o.modifiers.new("wall", "SOLIDIFY")
    m.thickness = thick
    m.offset = -1.0
    m.use_rim = True
    kit.hs._apply(o, m.name)
    return o


def on_egg(c, radii, az, el, grow=0.0):
    """Point and outward normal on an ellipsoid at azimuth `az` (0 = front, -Y; 90 = left, +X) and
    elevation `el` (degrees)."""
    a, e = math.radians(az), math.radians(el)
    u = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    r = Vector(radii) + Vector((grow, grow, grow))
    p = Vector(c) + Vector((u.x * r.x, u.y * r.y, u.z * r.z))
    n = Vector((u.x / r.x, u.y / r.y, u.z / r.z)).normalized()
    return p, n


# ------------------------------------------------------------------------------------------- build

def build():
    b = kit.Build(height=1.86, width=1.1, bulk=1.15)
    c = kit.begin("breaker", b)
    J = b.j
    tk = (b.height - b.hip_z) / 0.85
    sx = b.k * b.width * b.bulk

    def Z(v):
        """Height on the 1.80 m reference build -> this build."""
        return v * b.hip_z / 0.95 if v <= 0.95 else b.hip_z + (v - 0.95) * tk

    def XZ(pts):
        return [(x * sx, Z(z)) for x, z in pts]

    def rig(o, bone):
        if o is not None:
            c.rigid(o, bone)

    parts = kit.body(b, skin="brk_skin", chest=1.08, neck=1.25, head=False)
    flesh = c.flesh(parts["body"])
    head = kit.head_mesh(b, "brk_skin", jaw=1.22, brow=1.2, nose=1.08)
    c.add(head, kit.HEAD_BONES)
    hc = J("head", 0.45)
    wrists = [J("hand.L", 0.0), J("hand.R", 0.0)]

    def off_wrist(p, d=0.03):
        return all((p - w).length > d for w in wrists)

    # ---- face: a short beard along the jaw, heavy brows, a scar through the left brow
    beard = kit.shell(head, lambda p: p.y < hc.y + 0.06 and p.z < hc.z - 0.02, "beard", "hair", offset=0.0015, thick=0.004, detail=0.35,
                      inside=[kit.blob_cutter("beard_cut", hc + Vector((0, -0.04, -0.09)), (0.08, 0.095, 0.042), rot=(-12, 0, 0))],
                      outside=[kit.blob_cutter("mouth_cut", hc + Vector((0, -0.09, -0.062)), (0.021, 0.03, 0.0048))])
    c.rigid(beard, "head")
    for sg in (1, -1):
        brow = hc + Vector((sg * 0.034, -0.094, 0.027))
        c.rigid(obox("eyebrow", brow, Vector((1, 0, -0.18 * sg)), Vector((sg * 0.25, -1, 0.35)), (0.03, 0.007, 0.004), "hair", bevel=0.0015), "head")
    c.rigid(kit.cyl("scar", hc + Vector((0.03, -0.096, 0.038)), hc + Vector((0.037, -0.094, 0.016)), 0.0016, "brk_scar", segs=6, bevel=0), "head")

    # ---- gloves: leather, cream knuckle plates with two screws, clay wrist cuffs
    hands = parts["hands"]
    hands.data.materials[0] = kit.mat("leather")
    c.add(hands, kit.HAND_BONES)
    for s in ("L", "R"):
        sg = 1 if s == "L" else -1
        hb = Vector(b.all["hand." + s][0])
        down = (Vector(b.all["hand." + s][1]) - hb).normalized()
        knuckle = hb + down * 0.094 * b.k + Vector((sg * 0.014, -0.002, 0))
        c.rigid(obox("knuckle", knuckle, Vector((0, -1, 0)), Vector((sg, 0, 0)), (0.08, 0.026, 0.016), "cream", bevel=0.004), "hand." + s)
        for dy in (-0.022, 0.022):
            rig(bolt(knuckle + Vector((sg * 0.009, dy, 0)), (sg, 0, 0), r=0.004, head=0.003), "hand." + s)
        c.add(hug("cuff", flesh, J("forearm." + s, 0.91), J("forearm." + s, 1) - J("forearm." + s, 0), 0.004, 0.035, 0.008, "accent"),
              ["forearm." + s, "hand." + s])

    # ---- undersuit: torso and sleeves to the wrist, cut clean under a padded collar
    cloth(c, flesh, lambda p: p.z > Z(0.88) and off_wrist(p, 0.05), "undersuit", "primary", offset=0.016, thick=0.005, smooth_iter=2,
          bones=TORSO | UPPER_ARMS | FOREARMS, detail=SOFT)
    c.cover(TORSO | UPPER_ARMS | FOREARMS, lambda p: p.z > Z(0.92) and off_wrist(p, 0.075))
    c.add(hug("collar", flesh, J("neck", 0.45) + Vector((0, 0.005, 0)), (0, 0, 1), 0.022, 0.1, 0.012, "primary"), ["neck", "chest"])
    for s in ("L", "R"):
        c.add(hug("sleeve_cuff", flesh, J("forearm." + s, 0.8), J("forearm." + s, 1) - J("forearm." + s, 0), 0.022, 0.035, 0.009, "primary"),
              ["forearm." + s])

    # ---- chest plate, abdomen lames, back plate: the old Regime plate, scratched clean and repainted
    import bpy
    core = torso(b, chest=1.08, neck=1.25, target=2600)
    chest_out = 0.045 + 0.018
    chest_pts = XZ([(-0.135, 1.19), (0.135, 1.19), (0.14, 1.29), (0.112, 1.39), (0.065, 1.41), (0.0, 1.385), (-0.065, 1.41), (-0.112, 1.39), (-0.14, 1.29)])
    chest = plate(core, kit.slab("chest_cut", kit.rounded(chest_pts, 0.02), -0.4, -0.03), "chest_plate", "cream", offset=0.045, thick=0.018, bevel=0.005, detail=1.0)
    kit.cut(chest, kit.block("seam", (0, -0.25, Z(1.29)), (0.004, 0.2, Z(1.36) - Z(1.22)), "steel"), solver="MANIFOLD")
    scratches(chest, [(Vector((x * sx, 0, Z(z))), a, L) for x, z, a, L in (
        (-0.09, 1.33, 25, 0.07), (-0.07, 1.31, 30, 0.06), (0.08, 1.27, -35, 0.06), (0.10, 1.25, -30, 0.05), (0.05, 1.35, 70, 0.04))], (0, 1, 0))
    c.rigid(chest, "chest")
    c.rigid(paint(core, chest_out, "chest_hazard", [kit.slab("haz_band", XZ([(-0.13, 1.205), (0.13, 1.205), (0.13, 1.245), (-0.13, 1.245)]), -0.4, -0.03),
                                                     stripes_y(-0.14 * sx, 0.14 * sx, Z(1.20), Z(1.25), 0.024, 0.03, -0.4, -0.03)], detail=1.0), "chest")
    loc, _ = hit(chest, (0.075 * sx, 0, Z(1.335)), (0, 1, 0))
    c.rigid(kit.label_front("12", (loc.x, loc.y - 0.0005, loc.z), 0.04, "slate"), "chest")
    for x, z in ((-0.11, 1.215), (0.11, 1.215), (-0.1, 1.36), (0.1, 1.36)):
        loc, n = hit(chest, (x * sx, 0, Z(z)), (0, 1, 0))
        rig(bolt(loc, n), "chest")

    for i, (z0, z1, w) in enumerate(((1.105, 1.188, 0.13), (1.025, 1.11, 0.122))):
        lame = plate(core, kit.slab("lame_cut", kit.rounded(XZ([(-w, z0), (w, z0), (w + 0.005, z1), (-w - 0.005, z1)]), 0.015), -0.4, -0.035),
                     "lame", "cream", offset=0.04 - i * 0.003, thick=0.014, bevel=0.004, detail=0.6)
        scratches(lame, [(Vector((x * sx, 0, Z((z0 + z1) / 2))), a, 0.05) for x, a in ((-0.06, 15 + 20 * i), (0.07, -20))], (0, 1, 0))
        for x in (-w + 0.02, w - 0.02):
            loc, n = hit(lame, (x * sx, 0, Z((z0 + z1) / 2)), (0, 1, 0))
            rig(bolt(loc, n, r=0.005), "spine")
        c.rigid(lame, "spine")

    back_pts = XZ([(-0.135, 1.06), (0.135, 1.06), (0.135, 1.28), (0.115, 1.37), (0.08, 1.405), (-0.08, 1.405), (-0.115, 1.37), (-0.135, 1.28)])
    backp = plate(core, kit.slab("back_cut", kit.rounded(back_pts, 0.03), 0.03, 0.4), "back_plate", "cream", offset=0.045, thick=0.018, bevel=0.005, detail=1.0)
    scratches(backp, [(Vector((x * sx, 0, Z(z))), a, L) for x, z, a, L in ((-0.09, 1.2, 30, 0.07), (-0.07, 1.18, 35, 0.06), (0.1, 1.34, 60, 0.05))], (0, -1, 0))
    c.rigid(backp, "chest")
    c.rigid(paint(core, chest_out, "back_hazard", [kit.slab("haz_band", XZ([(-0.125, 1.068), (0.125, 1.068), (0.125, 1.105), (-0.125, 1.105)]), 0.03, 0.4),
                                                    stripes_y(-0.14 * sx, 0.14 * sx, Z(1.06), Z(1.11), 0.024, -0.03, 0.03, 0.4)], detail=1.0), "chest")
    bpy.data.objects.remove(core, do_unlink=True)

    # The torn-out uplink: the Regime mount on the back plate, mast snapped, cables cut.
    mz = Z(1.30)
    loc, n = hit(backp, (0, 0, mz), (0, -1, 0))
    my = loc.y + 0.018
    mount = kit.block("mount", (0, my, mz), (0.13, 0.04, 0.13), "bone", bevel=0.006)
    kit.cut(mount, kit.cyl("socket", (0, my - 0.01, mz), (0, my + 0.04, mz), 0.032, "steel", segs=20))
    c.rigid(mount, "chest")
    c.rigid(kit.ring("socket_ring", (0, my + 0.02, mz), (0, 1, 0), 0.04, 0.032, 0.008, "gunmetal", segs=20), "chest")
    stub = kit.cyl("mast_stub", (0.03, my + 0.01, mz + 0.04), (0.04, my + 0.03, mz + 0.14), 0.012, "gunmetal", segs=12, bevel=0.002)
    kit.cut(stub, kit.block("snap", (0.04, my + 0.03, mz + 0.15), (0.06, 0.06, 0.03), "steel", rot=35))
    c.rigid(stub, "chest")
    for dx, dz in ((-0.02, 0.0), (0.0, -0.014), (0.02, 0.006)):
        p0 = Vector((dx, my + 0.005, mz + dz))
        end = Vector((dx * 3 + 0.01, my + 0.045, mz - 0.08 + dz))
        c.rigid(kit.rope("cable", [p0, Vector((dx * 2, my + 0.035, mz - 0.02 + dz)), end], 0.005, "rubber"), "chest")
        c.rigid(kit.cyl("cut_end", end, end + Vector((0, 0.001, -0.01)), 0.0035, "copper", segs=8, bevel=0), "chest")
    for x in (-0.05, 0.05):
        for z in (mz - 0.045, mz + 0.045):
            rig(bolt((x, my + 0.021, z), (0, 1, 0), r=0.006), "chest")

    # Strip charge strapped across the small of the back: slate body, clay hazard bars, det caps.
    sz = Z(1.13)
    loc, _ = hit(backp, (0, 0, sz), (0, -1, 0))
    sy0 = loc.y + 0.02
    c.rigid(kit.block("strip_charge", (0, sy0, sz), (0.27 * sx, 0.035, 0.07), "slate", bevel=0.006), "chest")
    for x in (-0.09, -0.045, 0.0, 0.045, 0.09):
        c.rigid(obox("strip_bar", (x * sx, sy0 + 0.018, sz), Vector((0.5, 0, 1)), Vector((0, 1, 0)), (0.075, 0.018, 0.002), "clay"), "chest")
    for x in (-0.135, 0.135):
        c.rigid(kit.cyl("det_cap", (x * sx, sy0, sz + 0.035), (x * sx, sy0, sz + 0.06), 0.008, "brass", segs=10, bevel=0), "chest")
    for x in (-0.115, 0.115):
        c.rigid(kit.block("strip_strap", (x * sx, sy0 + 0.002, sz), (0.03, 0.042, 0.085), "accent", bevel=0.002), "chest")

    # Carrier: buckled straps from each plate's shoulder corner up under the pauldrons.
    for s, sg in (("L", 1), ("R", -1)):
        for obj, d in ((chest, (0, 1, 0)), (backp, (0, -1, 0))):
            loc, n = hit(obj, (sg * 0.088 * sx, 0, Z(1.385)), d)
            if loc is None:
                continue
            up = Vector((sg * 0.35, 0, 1))
            c.rigid(obox("plate_strap", loc + n * 0.003 + up.normalized() * 0.03, up, n, (0.08, 0.036, 0.006), "accent", bevel=0.0015), "chest")
            c.rigid(obox("strap_buckle", loc + n * 0.008 + up.normalized() * 0.012, up, n, (0.018, 0.046, 0.006), "gunmetal", bevel=0), "chest")

    # ---- shoulders: a cap on the shoulder and a lame on the upper arm, forearm vambraces
    for s, sg in (("L", 1), ("R", -1)):
        top = J("upper_arm." + s, 0.0)
        cap_keep = (lambda p, sg=sg, top=top: p.x * sg > 0.09 and p.z > top.z - 0.15)
        cap_bones = {"shoulder." + s, "upper_arm." + s, "chest"}
        pts = [(0.115, 1.56), (0.37, 1.56), (0.37, 1.36), (0.30, 1.345), (0.215, 1.42), (0.115, 1.475)]
        yr = 0.105 * b.k * b.bulk
        outline = kit.rounded([(sg * x * b.width, top.z + (z - 1.447)) for x, z in pts], 0.025)
        cut = kit.slab("cap_cut", outline, -yr, yr)
        cap = plate(flesh, cut, "pauldron", "cream", offset=0.04, thick=0.016, bevel=0.005, keep=cap_keep, bones=cap_bones)
        scratches(cap, [(top + Vector((sg * 0.05, 0, 0.05)), a, 0.05) for a in (20, 70)], (0, 0, -1))
        c.rigid(cap, "shoulder." + s)
        x0, x1 = (0.20, 0.5) if sg > 0 else (-0.5, -0.20)
        inset = [(sg * x * b.width, top.z + (z - 1.447)) for x, z in
                 [(0.13, 1.545), (0.355, 1.545), (0.355, 1.375), (0.30, 1.362), (0.22, 1.435), (0.13, 1.49)]]
        c.rigid(paint(flesh, 0.056, "cap_hazard", [kit.slab("cap_inset", kit.rounded(inset, 0.02), -yr + 0.012, yr - 0.012),
                                                   kit.prism("cap_band", [(-yr, top.z - 0.095), (yr, top.z - 0.095), (yr, top.z - 0.03),
                                                                          (-yr, top.z - 0.03)], 0.3, "steel", x=sg * 0.42, bevel=0),
                                                   stripes_x(-0.14, 0.14, top.z - 0.08, top.z - 0.015, 0.022, 0.028 * sg, x0, x1)],
                      keep=cap_keep, bones=cap_bones), "shoulder." + s)
        loc, n = hit(cap, top + Vector((sg * 0.02, 0, 0.0)), (0, 0, -1))
        rig(bolt(loc, n), "shoulder." + s)
        ua0, ua1 = J("upper_arm." + s, 0.18), J("upper_arm." + s, 0.62)
        ay = 0.075 * b.k * b.bulk
        lame = plate(flesh, kit.prism("arm_cut", kit.rounded([(-ay, ua1.z), (ay, ua1.z), (ay, ua0.z), (-ay, ua0.z)], 0.02), 0.2, "steel", x=ua0.x + sg * 0.09, bevel=0),
                     "arm_lame", "cream", offset=0.036, thick=0.012, bevel=0.004, bones={"upper_arm." + s})
        c.rigid(lame, "upper_arm." + s)
        c.add(hug("arm_strap", flesh, J("upper_arm." + s, 0.7), J("upper_arm." + s, 1) - J("upper_arm." + s, 0), 0.024, 0.025, 0.008, "webbing"),
              ["upper_arm." + s])

        f0, f1 = J("forearm." + s, 0.12), J("forearm." + s, 0.78)
        mid = f0.lerp(f1, 0.5)
        prof = kit.rounded([(mid.y - 0.072, f1.z), (mid.y + 0.068, f1.z), (mid.y + 0.068, f0.z), (mid.y - 0.072, f0.z)], 0.025)
        vam = plate(flesh, kit.prism("vam_cut", prof, 0.2, "steel", x=mid.x + sg * 0.095, bevel=0), "vambrace", "cream", offset=0.034, thick=0.012,
                    bevel=0.004, bones={"forearm." + s})
        scratches(vam, [(mid + Vector((0, dy, dz)), a, 0.04) for dy, dz, a in ((-0.02, 0.04, 30), (0.01, -0.045, 60))], (-sg, 0, 0))
        c.rigid(vam, "forearm." + s)
        band = kit.prism("vam_band", [(mid.y - 0.1, mid.z - 0.018), (mid.y + 0.1, mid.z - 0.018), (mid.y + 0.1, mid.z + 0.018), (mid.y - 0.1, mid.z + 0.018)],
                         0.2, "steel", x=mid.x + sg * 0.095, bevel=0)
        c.rigid(paint(flesh, 0.046, "vam_stripe", [kit.prism("vam_cut2", prof, 0.2, "steel", x=mid.x + sg * 0.095, bevel=0), band], bones={"forearm." + s}),
                "forearm." + s)
        for t in (0.12, 0.88):
            loc, n = hit(vam, f0.lerp(f1, t), (-sg, 0, 0))
            rig(bolt(loc, n, r=0.005), "forearm." + s)

    # ---- trousers (tucked into the boots), battle belt, breaching charge pouches
    bz = Z(0.965)
    cloth(c, flesh, lambda p: Z(0.30) < p.z < Z(1.09), "trousers", "secondary", offset=0.024, thick=0.005, smooth_iter=3,
          bones=THIGHS | SHINS | {"hips"}, detail=SOFT, inside=[below(Z(1.055)), above(Z(0.33))])
    c.cover(THIGHS | SHINS | {"hips"}, lambda p: Z(0.15) < p.z < Z(1.04))
    c.rigid(hug("belt", flesh, Vector((0, 0.01, bz)), (0, 0, 1), 0.03, 0.06, 0.014, "webbing", n=32), "hips")
    for sg in (1, -1):
        x0 = sg * 0.085 * sx
        pk = [(x0 - 0.045, Z(0.84)), (x0 + 0.045, Z(0.84)), (x0 + 0.05, Z(0.935)), (x0 - 0.05, Z(0.935))]
        cloth(c, flesh, lambda p, sg=sg: p.y > 0.0 and p.x * sg > 0.0 and Z(0.78) < p.z < Z(0.98), "seat_pocket", "secondary", offset=0.03, thick=0.004,
              bones=THIGHS | {"hips"}, detail=0.6, inside=[kit.slab("pocket_cut", kit.rounded(pk, 0.012), 0.0, 0.4)])
        fl = [(x0 - 0.05, Z(0.915)), (x0 + 0.05, Z(0.915)), (x0 + 0.052, Z(0.95)), (x0 - 0.052, Z(0.95))]
        cloth(c, flesh, lambda p, sg=sg: p.y > 0.0 and p.x * sg > 0.0 and Z(0.85) < p.z < Z(0.99), "pocket_flap", "secondary", offset=0.034, thick=0.004,
              bones=THIGHS | {"hips"}, detail=0.6, inside=[kit.slab("flap_cut", kit.rounded(fl, 0.008), 0.0, 0.4)])
    c.rigid(kit.block("buckle", (0, -0.152, bz), (0.07, 0.016, 0.05), "clay", bevel=0.004), "hips")
    c.rigid(kit.block("buckle_bar", (0, -0.161, bz), (0.05, 0.006, 0.012), "gunmetal", bevel=0.001), "hips")

    def on_belt(ang, out=0.03, dz=0.0):
        a = math.radians(ang)
        d = Vector((math.sin(a), -math.cos(a), 0))
        loc, n = hit(flesh, Vector((0, 0.01, bz + dz)) + d * 0.5, -d)
        n = Vector((n.x, n.y, 0)).normalized()
        return loc + n * (0.044 + out), n
    for ang in (-60, -36, 36, 60):
        p, n = on_belt(ang, 0.024, -0.01)
        t = Vector((0, 0, 1)).cross(n).normalized()
        pouch = obox("pouch", p, t, n, (0.072, 0.10, 0.048), "webbing", bevel=0.006)
        rim = obox("pouch_rim", p + Vector((0, 0, 0.047)), t, n, (0.076, 0.012, 0.052), "webbing", bevel=0.003)
        tab = obox("tab", p + n * 0.026 + Vector((0, 0, -0.01)), t, n, (0.03, 0.05, 0.005), "webbing", bevel=0.0015)
        c.rigid(kit.join([pouch, rim, tab], "charge_pouch"), "hips")
        rig(bolt(p + n * 0.0285 + Vector((0, 0, -0.024)), n, r=0.006, material="gunmetal", head=0.003), "hips")
        # The charge: a kraft-wrapped block standing out of the pouch, a clay retention strap, a brass det cap, a wire loop.
        q = p + Vector((0, 0, 0.07)) - n * 0.003
        c.rigid(obox("charge", q, t, n, (0.052, 0.05, 0.036), "kraft", bevel=0.004), "hips")
        c.rigid(obox("charge_band", q + Vector((0, 0, -0.01)), t, n, (0.056, 0.014, 0.04), "accent", bevel=0.001), "hips")
        cap0 = q + Vector((0, 0, 0.024)) + t * 0.012
        c.rigid(kit.cyl("det_cap", cap0, cap0 + Vector((0, 0, 0.022)), 0.006, "brass", segs=10, bevel=0), "hips")
        c.rigid(kit.rope("det_wire", [cap0 + Vector((0, 0, 0.022)), cap0 + Vector((0, 0, 0.04)) - t * 0.012, q + Vector((0, 0, 0.026)) - t * 0.02],
                         0.0018, "copper"), "hips")
    # Firing device on the left hip, det-cord spool on the right hip.
    p, n = on_belt(95, 0.02, -0.02)
    t = Vector((0, 0, 1)).cross(n).normalized()
    c.rigid(obox("clacker_pouch", p, t, n, (0.06, 0.12, 0.04), "webbing", bevel=0.005), "hips")
    c.rigid(obox("clacker", p + Vector((0, 0, 0.07)) + n * 0.002, t, n, (0.045, 0.06, 0.03), "gunmetal", bevel=0.004), "hips")
    c.rigid(obox("clacker_lever", p + Vector((0, 0, 0.09)) + n * 0.022, t, n, (0.012, 0.06, 0.01), "clay", bevel=0.002), "hips")
    sp, out = on_belt(-118, 0.0, -0.05)
    c.rigid(kit.cyl("spool_hub", sp, sp + out * 0.035, 0.03, "gunmetal", segs=16, bevel=0.002), "hips")
    for i in range(2):
        c.rigid(kit.ring("det_cord", sp + out * (0.01 + i * 0.012), out, 0.054, 0.034, 0.011, "accent", segs=20), "hips")
    c.rigid(kit.ring("spool_rim", sp + out * 0.036, out, 0.058, 0.026, 0.004, "gunmetal", segs=20), "hips")

    # Thigh plates hung from the belt, hazard band along the hem.
    for s, sg in (("L", 1), ("R", -1)):
        t0, t1 = J("upper_leg." + s, 0.12), J("upper_leg." + s, 0.58)
        pts = [(t0.x - sg * 0.06, t1.z), (t0.x + sg * 0.14, t1.z), (t0.x + sg * 0.14, t0.z), (t0.x - sg * 0.06, t0.z - 0.02)]
        bones = {"upper_leg." + s}
        tp = plate(flesh, kit.slab("thigh_cut", kit.rounded(pts, 0.03), -0.3, 0.035), "thigh_plate", "cream", offset=0.042, thick=0.014, bevel=0.004, bones=bones)
        mid = t0.lerp(t1, 0.45)
        scratches(tp, [(mid + Vector((sg * dx, 0, dz)), a, 0.05) for dx, dz, a in ((0.02, 0.05, 35), (-0.01, -0.04, 20), (0.04, -0.06, 50))], (0, 1, 0))
        c.rigid(tp, "upper_leg." + s)
        hem = [(t0.x - sg * 0.055, t1.z + 0.018), (t0.x + sg * 0.135, t1.z + 0.018), (t0.x + sg * 0.135, t1.z + 0.06), (t0.x - sg * 0.055, t1.z + 0.06)]
        c.rigid(paint(flesh, 0.056, "thigh_hazard", [kit.slab("thigh_band", hem, -0.3, 0.035),
                                                     stripes_y(t0.x - 0.2, t0.x + 0.2, t1.z + 0.012, t1.z + 0.066, 0.022, 0.025 * sg, -0.3, 0.035)],
                      bones=bones), "upper_leg." + s)
        for dx in (0.0, sg * 0.075):
            loc, n = hit(tp, Vector((t0.x + dx, 0, t0.z - 0.035)), (0, 1, 0))
            if loc is None:
                continue
            rig(bolt(loc, n, r=0.005), "upper_leg." + s)
            c.add(kit.strap("hanger", [Vector((loc.x, loc.y - 0.012, bz - 0.03)), loc + Vector((0, -0.006, 0.012))], 0.022, 0.006, "accent", up=(0, -1, 0)),
                  ["hips", "upper_leg." + s])

        # Knee cop.
        knee = J("lower_leg." + s, 0.06)
        kcut = kit.slab("knee_cut", kit.rounded([(knee.x - 0.062, knee.z - 0.08), (knee.x + 0.062, knee.z - 0.08), (knee.x + 0.062, knee.z + 0.06),
                                                 (knee.x - 0.062, knee.z + 0.06)], 0.035), -0.4, knee.y - 0.012)
        kp = plate(flesh, kcut, "knee_cop", "cream", offset=0.036, thick=0.016, bevel=0.005, bones=THIGHS | SHINS)
        kit.cut(kp, kit.block("knee_groove", (knee.x, -0.3, knee.z - 0.01), (0.15, 0.4, 0.005), "steel"), solver="MANIFOLD")
        c.rigid(kp, "lower_leg." + s)
        c.add(hug("knee_strap", flesh, J("lower_leg." + s, 0.17), (0, 0, 1), 0.03, 0.022, 0.007, "webbing"), ["lower_leg." + s])

    # ---- heavy boots over the trousers: slate shells, thick soles, steel toe caps, cream shin guards
    for s, sg in (("L", 1), ("R", -1)):
        top_z = Z(0.40)
        boot = kit.shell(flesh, lambda p, sg=sg: p.z < top_z + 0.03 and p.x * sg > 0, "boot", "slate", offset=0.032, thick=0.009,
                         bones={"foot." + s, "lower_leg." + s}, detail=SOFT, inside=[below(top_z)])
        c.add(boot, ["foot." + s, "lower_leg." + s])
        fx = J("foot." + s, 0.0).x
        sole = kit.plan("sole", kit.rounded([(fx - 0.062, 0.1), (fx + 0.062, 0.1), (fx + 0.067, -0.2), (fx - 0.057, -0.2)], 0.04), 0.04, "rubber", z=0.02, bevel=0.003)
        sole["segs"] = 1
        kit.cut(sole, *kit.slots("tread", -0.18, 0.08, 8, -0.002, 0.008, fx - 0.08, fx + 0.08))
        c.rigid(sole, "foot." + s)
        c.rigid(kit.block("heel", (fx, 0.065, 0.012), (0.108, 0.06, 0.024), "rubber", bevel=0.003), "foot." + s)
        c.rigid(kit.block("toecap", (fx + sg * 0.002, -0.175, 0.062), (0.115, 0.05, 0.062), "gunmetal", bevel=0.012), "foot." + s)
        for dx in (-0.035, 0.035):
            rig(bolt((fx + dx, -0.2, 0.062), (0, -1, 0), r=0.005, material="steel", head=0.003), "foot." + s)
        for i in range(3):
            c.rigid(kit.block("lace", (fx, -0.09 + i * 0.03, 0.125 + i * 0.022), (0.055, 0.008, 0.006), "cream", bevel=0, rot=-30), "foot." + s)
        s0, s1 = J("lower_leg." + s, 0.36), J("lower_leg." + s, 0.78)
        gpts = kit.rounded([(fx - 0.058, s1.z), (fx + 0.058, s1.z), (fx + 0.062, s0.z), (fx - 0.062, s0.z)], 0.03)
        gb = {"lower_leg." + s, "foot." + s}
        guard = plate(flesh, kit.slab("shin_cut", gpts, -0.4, -0.01), "shin_guard", "cream", offset=0.046, thick=0.012, bevel=0.004, bones=gb)
        kit.cut(guard, *[kit.block("shin_rib", (fx, -0.3, z), (0.2, 0.4, 0.004), "steel") for z in (s0.z - 0.03, s1.z + 0.03)], solver="MANIFOLD")
        c.rigid(guard, "lower_leg." + s)
        c.rigid(paint(flesh, 0.058, "shin_hazard", [kit.slab("shin_cut2", gpts, -0.4, -0.01),
                                                    kit.slab("shin_stripe", [(fx - 0.013, 0.0), (fx + 0.013, 0.0), (fx + 0.013, 1.0), (fx - 0.013, 1.0)], -0.4, -0.01)],
                      bones=gb), "lower_leg." + s)
        for t in (0.5, 0.72):
            p = J("lower_leg." + s, t)
            c.add(hug("boot_strap", flesh, p, (0, 0, 1), 0.044, 0.024, 0.008, "accent"), ["lower_leg." + s])
            loc, n = hit(flesh, p, (-sg, 0, 0))
            c.rigid(obox("strap_buckle", loc + n * 0.055, Vector((0, 0, 1)), n, (0.034, 0.03, 0.008), "gunmetal", bevel=0), "lower_leg." + s)
        c.add(hug("boot_cuff", flesh, Vector((J("lower_leg." + s, 0.0).x, 0.0, top_z - 0.012)), (0, 0, 1), 0.04, 0.036, 0.014, "slate"), ["lower_leg." + s])
    c.cover(FEET | SHINS, lambda p: p.z < Z(0.37))

    # ---- the cracked Regime helmet, face shield torn off
    hcen = hc + Vector((0, 0.012, 0.012))
    rad = (0.118, 0.137, 0.135)
    helm = egg("helmet", hcen, rad, 0.011, "bone", segs=(32, 20))
    face = kit.slab("face_cut", kit.rounded([(-0.076, hc.z - 0.25), (0.076, hc.z - 0.25), (0.076, hc.z + 0.012), (0.05, hc.z + 0.05), (-0.05, hc.z + 0.05),
                                             (-0.076, hc.z + 0.012)], 0.02), -0.4, hc.y - 0.012)
    helm = kit.subtract(helm, face)
    helm = kit.subtract(helm, below(hc.z - 0.105))
    for path in (((8, 18), (14, 28), (10, 38), (22, 50), (18, 62), (30, 72)), ((14, 28), (24, 30), (34, 26)),
                 ((-64, -12), (-70, -22), (-66, -32), (-74, -40))):
        pts, ns = [], []
        for az, el in path:
            q, nq = on_egg(hcen, rad, az, el)
            pts.append(q)
            ns.append(nq)
        kit.cut(helm, sweep("crack", pts, ns, 0.0035, 0.014, "steel"), solver="MANIFOLD")
    for az, el in ((106, 10), (118, 8)):
        q, nq = on_egg(hcen, rad, az, el)
        kit.cut(helm, obox("scratch", q, Vector((0, 0.4, 1)), nq, (0.05, 0.0022, 0.004), "steel"), solver="MANIFOLD")
    helm["bevel"] = 0.002
    helm["shaded"] = False
    c.rigid(helm, "head")
    # The painted clay crest down the middle.
    crest = egg("crest", hcen, tuple(r + 0.004 for r in rad), 0.006, "clay", segs=(32, 20))
    crest = kit.intersect(crest, kit.block("crest_cut", (0, 0.04, hc.z + 0.12), (0.03, 0.36, 0.2), "steel"))
    crest = kit.subtract(crest, kit.slab("crest_face", [(-0.1, hc.z - 0.3), (0.1, hc.z - 0.3), (0.1, hc.z + 0.05), (-0.1, hc.z + 0.05)], -0.4, hc.y - 0.012))
    crest["bevel"] = 0.0015
    crest["shaded"] = False
    c.rigid(crest, "head")
    # Shield hinges: bare pivot and bent bracket on the left, a jagged shield stub on the right.
    for sg in (1, -1):
        q, nq = on_egg(hcen, rad, sg * 72, -8)
        c.rigid(kit.cyl("pivot", q - nq * 0.004, q + nq * 0.01, 0.018, "gunmetal", segs=16, bevel=0.002), "head")
        rig(bolt(q + nq * 0.01, nq, r=0.008, material="steel"), "head")
    q, nq = on_egg(hcen, rad, 72, -8)
    c.rigid(obox("bracket", q + nq * 0.012 + Vector((0, -0.02, -0.004)), Vector((0, -1, -0.5)), nq, (0.04, 0.014, 0.005), "gunmetal", bevel=0.0015), "head")
    shield = egg("shield_stub", hcen + Vector((0, -0.004, 0)), (rad[0] + 0.016, rad[1] + 0.02, rad[2] + 0.01), 0.008, "bone", segs=(36, 22))
    jag = [(-0.142, hc.z + 0.026), (-0.1, hc.z + 0.026), (-0.088, hc.z + 0.01), (-0.098, hc.z - 0.002), (-0.084, hc.z - 0.016),
           (-0.1, hc.z - 0.03), (-0.094, hc.z - 0.044), (-0.142, hc.z - 0.044)]
    shield = kit.intersect(shield, kit.slab("jag", jag, -0.4, hc.y - 0.03))
    srad = (rad[0] + 0.016, rad[1] + 0.02, rad[2] + 0.01)
    q, nq = on_egg(hcen + Vector((0, -0.004, 0)), srad, -54, 2)
    kit.cut(shield, obox("slit", q, Vector((1, 0, 0)), nq, (0.05, 0.008, 0.02), "steel"), solver="MANIFOLD")
    shield["bevel"] = 0.0015
    shield["shaded"] = False
    c.rigid(shield, "head")
    q, nq = on_egg(hcen + Vector((0, -0.004, 0)), srad, -60, 2)
    c.rigid(obox("dead_lens", q - nq * 0.004, Vector((1, 0, 0)), nq, (0.026, 0.006, 0.003), "glass"), "head")
    # The uplink socket on the crown, its mast snapped off, a cut cable.
    q, nq = on_egg(hcen, rad, 180, 48)
    c.rigid(kit.cyl("uplink_boss", q - nq * 0.006, q + nq * 0.012, 0.022, "bone", segs=16, bevel=0.002), "head")
    c.rigid(kit.ring("uplink_ring", q + nq * 0.013, nq, 0.022, 0.012, 0.004, "gunmetal", segs=16), "head")
    c.rigid(kit.cyl("uplink_stub", q + nq * 0.01, q + nq * 0.03 + Vector((0.004, 0, 0)), 0.008, "gunmetal", segs=10, bevel=0.001), "head")
    q2 = q + nq * 0.005 + Vector((0.02, 0.0, 0))
    c.rigid(kit.rope("uplink_cable", [q2, q2 + Vector((0.025, 0.01, -0.005)), q2 + Vector((0.035, 0.02, -0.04))], 0.003, "rubber"), "head")
    # Leftover code etching on the left side, half scratched away.
    for txt, el in (("0110 1", 14), ("10 011", 4)):
        q, nq = on_egg(hcen, rad, 112, el, grow=0.0005)
        lab = kit.label(txt, (0, 0, 0), 0.012, "ink", side=1, depth=0.0012)
        kit.place(lab, q, (0, 0, math.degrees(math.atan2(nq.y, nq.x))))
        c.rigid(lab, "head")
    # A loose chin strap hanging from the left cheek guard.
    q, nq = on_egg(hcen, rad, 62, -50)
    c.rigid(kit.strap("chin_strap", [q + nq * 0.002, q + nq * 0.004 + Vector((-0.004, -0.004, -0.04)), q + nq * 0.002 + Vector((-0.012, -0.01, -0.07))],
                      0.02, 0.004, "accent", up=nq), "head")
    return c


SPEC = {"build": build, "faction": "deserters", "budget": (25000, 75000), "loadout": "grenade",
        "colors": {"primary": "#141413", "secondary": "#D4A27F", "accent": "#D97757"}}
