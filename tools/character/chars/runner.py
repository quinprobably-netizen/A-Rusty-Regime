"""Runner, Deserters: the player's default. A Regime pilot who walked out, built as one outfit from the
skin out: a fitted slate pilot suit with clay piping along its seams, padded shoulders, elbows and
knees and rib-knit cuffs; a soft-shell hood over a half-face respirator with pancake filters, goggles
pushed up on the hood; a kraft climbing harness (waist belt, leg loops, belay loop, shoulder and side
straps) carrying a Regime chest plate with its code ground off and repainted cream, a cream back
plate with the torn-out uplink stub, the grapple pack below it with a rope coil strapped on and the
line running over the shoulder to the grapple launcher on the left forearm; carabiners on the gear
loops, gloves and approach boots.

Built on the realistic layer (real.py): a real body, face and eyes, gloved fists, suit and hood draped
by the cloth simulation, procedural surfaces baked into one atlas.

Tints: primary = suit and hood (slate), secondary = harness webbing (kraft), accent = piping, belay
loop, filters, carabiners and small hardware (clay). Cream (the repainted Regime plates) is fixed.
"""

import math
import random

import bmesh
from mathutils import Matrix, Vector

import kit
import real
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS, FEET
from chars.contractor import (tree, hit, frame, put, panel, rrect, sweep, radial, smooth_path, wrap, _limb, _radius,
                              side_buckle, economise, band, grow)

kit.hs.PALETTE.update({
    "runner_lens": ((0.30, 0.15, 0.045), (0.30, 0.15, 0.045), 0.5, 0.05, 0.0, 0),   # amber mirrored goggle lens
})

ARMS = UPPER_ARMS | FOREARMS
LEGS = THIGHS | SHINS


# ------------------------------------------------------------------------------------ helpers

def hard(o, kind):
    """Give a part a realistic-layer material ("polymer.accent": moulded, tinted as accent)."""
    o.data.materials.clear()
    o.data.materials.append(real.mat(kind))
    return o


def mat_of(o, kind):
    return hard(o, kind) if "." in kind else o


def skinned_on(c, src, obj):
    """Skin `obj` (piping, a cable, a strap lying on a garment) with the weights of the nearest face
    of `src`, a garment's game mesh: it bends exactly as the cloth under it."""
    kit.hs.apply_modifiers(obj)
    kit.transfer(src, obj)
    c.parts.append((obj, "DONE", None))
    return obj


def tube(name, pts, r, material, closed=False, segs=8):
    """A round tube along points (piping, cables, carabiners, rope): rings carried along by parallel
    transport so it never twists, capped when open."""
    P = [Vector(p) for p in pts]
    n = len(P)
    bm = bmesh.new()
    tan = []
    for i in range(n):
        if closed:
            a, b = P[i - 1], P[(i + 1) % n]
        else:
            a, b = P[max(0, i - 1)], P[min(n - 1, i + 1)]
        tan.append((b - a).normalized())
    ref = Vector((0, 0, 1)) if abs(tan[0].z) < 0.9 else Vector((1, 0, 0))
    nrm = (ref - tan[0] * ref.dot(tan[0])).normalized()
    rings = []
    for i in range(n):
        if i:
            nrm = tan[i - 1].rotation_difference(tan[i]) @ nrm
            nrm = (nrm - tan[i] * nrm.dot(tan[i])).normalized()
        bi = tan[i].cross(nrm)
        rings.append([bm.verts.new(P[i] + (nrm * math.cos(2 * math.pi * k / segs) + bi * math.sin(2 * math.pi * k / segs)) * r) for k in range(segs)])
    spans = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for r0, r1 in spans:
        for k in range(segs):
            j = (k + 1) % segs
            bm.faces.new((r0[k], r0[j], r1[j], r1[k]))
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = kit.hs._obj(name, bm, "steel" if "." in material else material, 0.0)
    mat_of(o, material)
    o["shaded"] = True
    return o


def relax(pts, n=2, closed=True):
    """Laplacian smoothing of a point list."""
    P = [Vector(p) for p in pts]
    for _ in range(n):
        Q = []
        for i in range(len(P)):
            if not closed and i in (0, len(P) - 1):
                Q.append(P[i])
                continue
            Q.append((P[i - 1] + P[i] * 2 + P[(i + 1) % len(P)]) / 4)
        P = Q
    return P


def resample(pts, step, closed=False):
    """Points every `step` metres along a polyline."""
    P = [Vector(p) for p in pts] + ([Vector(pts[0])] if closed else [])
    out = [P[0]]
    acc = 0.0
    for a, b in zip(P, P[1:]):
        L = (b - a).length
        while acc + L >= step:
            t = (step - acc) / L
            a = a.lerp(b, t)
            L = (b - a).length
            out.append(a)
            acc = 0.0
        acc += L
    if not closed and (out[-1] - P[-1]).length > step * 0.3:
        out.append(P[-1])
    return out


def limb_pts(tr, a, b, ang, t0, t1, n, off, front=(0, -1, 0)):
    """Points on the surface in tree `tr` along the limb a->b at angle `ang` round it (degrees, a
    number or a function of t; 0 faces `front`, +90 the +X side), `off` outside it."""
    a, b = Vector(a), Vector(b)
    A = (b - a).normalized()
    F = Vector(front)
    F = (F - A * F.dot(A)).normalized()
    S = F.cross(A).normalized()
    out = []
    for i in range(n):
        t = t0 + (t1 - t0) * i / (n - 1)
        c0 = a.lerp(b, t)
        ph = math.radians(ang(t) if callable(ang) else ang)
        d = F * math.cos(ph) + S * math.sin(ph)
        loc, _ = hit(tr, c0, d)
        if loc is not None and (loc - c0).length < 0.2:
            out.append(loc + d * off)
    return out


def arc_pts(tr, c, z, off, a0, a1, n):
    """Points round the torso at height z from angle a0 to a1 (degrees; 0 = front, 90 = left),
    `off` outside the surface in tree `tr`, found by rays from inside out."""
    out = []
    for i in range(n):
        a = math.radians(a0 + (a1 - a0) * i / max(1, n - 1))
        d = Vector((math.sin(a), -math.cos(a), 0))
        loc, _ = hit(tr, Vector((c[0], c[1], z)), d)
        out.append(loc + d * off if loc is not None else Vector((c[0], c[1], z)) + d * 0.15)
    return out


def angdiff(a, b):
    return abs((a - b + 180) % 360 - 180)


def hug_ring(trees, ctr, axis, off, n=20, rmax=0.2):
    """A closed loop round `axis` through `ctr`, `off` outside the outermost surface of `trees` met
    by rays from the axis (a strap over a sleeve and the bracer on it)."""
    a = Vector(axis).normalized()
    u_ = a.cross(Vector((0, 0, 1)) if abs(a.z) < 0.9 else Vector((1, 0, 0))).normalized()
    v_ = a.cross(u_)
    out = []
    for k in range(n):
        t = 2 * math.pi * k / n
        d = u_ * math.cos(t) + v_ * math.sin(t)
        best = None
        for tr in trees:
            loc, _ = hit(tr, ctr, d)
            if loc is not None and (loc - Vector(ctr)).length < rmax and (best is None or (loc - Vector(ctr)).length > (best - Vector(ctr)).length):
                best = loc
        out.append((best if best is not None else Vector(ctr) + d * 0.06) + d * off)
    return out


def grid_plate(name, x0, x1, z0, z1, yfun, thick, material, back=False, step=0.011):
    """A plate whose outer face is y = yfun(x, z) over a grid, thickened toward the body (+Y for a
    front plate, -Y for a back plate). Trim it to an outline with kit.intersect."""
    bm = bmesh.new()
    nx = max(2, int((x1 - x0) / step) + 1)
    nz = max(2, int((z1 - z0) / step) + 1)
    rows = [[bm.verts.new((x0 + (x1 - x0) * i / (nx - 1), 0.0, z0 + (z1 - z0) * j / (nz - 1))) for i in range(nx)] for j in range(nz)]
    for row in rows:
        for v in row:
            v.co.y = yfun(v.co.x, v.co.z)
    for j in range(nz - 1):
        for i in range(nx - 1):
            q = (rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i])
            bm.faces.new(q[::-1] if back else q)
    o = kit.hs._obj(name, bm, material, 0.0)
    sm = o.modifiers.new("thick", "SOLIDIFY")
    sm.thickness = thick
    sm.offset = -1.0
    sm.use_even_offset = True
    sm.use_rim = True
    kit.hs._apply(o, sm.name)
    return o


def ell_y(cx, cy, cz, rx, ry, rz, sign=-1):
    """The front (sign -1) or back (+1) of an ellipsoid as a height field y(x, z)."""
    def f(x, z):
        q = 1 - ((x - cx) / rx) ** 2 - ((z - cz) / rz) ** 2
        return cy + sign * ry * math.sqrt(max(q, 0.0))
    return f


def oriented(o, at, x, y, z):
    """Move a part built round the origin so its local axes become x, y, z at `at`."""
    M = Matrix((Vector(x), Vector(y), Vector(z))).transposed().to_4x4()
    M.translation = Vector(at)
    o.data.transform(M)
    return o


def carabiner(name, at, down, flat, size=0.075, material="gunmetal", lock=False, gate_kind="bright"):
    """A D carabiner hanging from `at` along `down`, its plane facing `flat`: a bent-rod body, the
    gate on the long side and (locking) a sleeve on it."""
    h, w, r = size, size * 0.56, size * 0.062
    # A D in the local XZ plane, hanging down -Z: the straight spine on x = 0, the gate on x = w.
    pts = []
    for i in range(6):
        pts.append(Vector((0.0, 0.0, -(h * 0.25 + h * 0.5 * i / 5))))
    # bottom bend round to the gate side
    for i in range(1, 7):
        a = math.pi * i / 7
        pts.append(Vector((w * 0.5 - w * 0.5 * math.cos(a), 0.0, -(h * 0.75 + h * 0.22 * math.sin(a)))))
    # gate side up
    for i in range(5):
        pts.append(Vector((w, 0.0, -(h * 0.72 - h * 0.42 * i / 4))))
    # top bend back over to the spine
    for i in range(1, 7):
        a = math.pi * i / 7
        pts.append(Vector((w * 0.5 + w * 0.5 * math.cos(a), 0.0, -(h * 0.27 - h * 0.25 * math.sin(a)))))
    body = tube(name, pts, r, material, closed=True, segs=6)
    parts = [body]
    if lock:
        parts.append(kit.cyl("lock_sleeve", (w, 0, -h * 0.34), (w, 0, -h * 0.5), r * 1.7, "grey", segs=10, bevel=0.0008))
        if "." in gate_kind:
            hard(parts[-1], gate_kind)
    o = kit.hs.join(parts, name)
    d = Vector(down).normalized()
    f = Vector(flat)
    f = (f - d * f.dot(d)).normalized()
    side = d.cross(f)
    M = Matrix((side, f, -d)).transposed().to_4x4()
    M.translation = Vector(at)
    o.data.transform(M)
    o["bevel"] = 0.0
    return o


# ------------------------------------------------------------------------------------ build

def head_gear(c, man, lead, neck):
    """The soft-shell hood, the half-face respirator and the goggles pushed up on the hood."""
    E, u = man.face()
    hc = man.head_center()

    # The hood: snug round its opening (a balaclava's oval from the brow to the jaw, its edge
    # tucked under the respirator's), roomy over the crown and the back of the head, its hem in
    # the suit's standing collar. The opening is two cuts: a tilted one over the brow and the
    # temples, a plumb one down the cheeks.
    hood_hem = neck.z + 0.03
    o_y = E.y + 0.03
    slope = 1.25

    def ycut(z):
        return o_y - slope * max(0.0, z - E.z)

    def fd(p):
        return p.y - ycut(p.z)   # how far behind the opening

    def h_ease(p):
        up = float(real._smooth(p.z, neck.z + 0.03, E.z - 0.06))
        bk = float(real._smooth(p.y - hc.y, -0.03, 0.08))
        crown = float(real._smooth(p.z, E.z + 0.03, E.z + 0.1))
        # over the ears: room enough that the smoothed shell bridges them
        ear = (float(real._smooth(abs(p.x), 0.05, 0.075)) * (1 - float(real._smooth(abs(p.y - hc.y), 0.03, 0.06)))
               * float(real._smooth(p.z, E.z - 0.09, E.z - 0.06)) * (1 - float(real._smooth(p.z, E.z + 0.01, E.z + 0.04))))
        roomy = 0.008 * up + 0.012 * bk * up + 0.004 * crown + 0.016 * ear
        return 0.005 + roomy * float(real._smooth(fd(p), 0.0, 0.04))

    def h_pin(p):
        if p.z < hood_hem + 0.025 or fd(p) < 0.012:
            return 1.0
        # the shell holds its shape over the head; the back and the nape drape and fold
        hold = (float(real._smooth(p.z, E.z - 0.08, E.z - 0.03))
                * (1 - float(real._smooth(p.y - hc.y, 0.0, 0.05))))
        return 0.8 * hold

    def h_slack(p):
        bk = float(real._smooth(p.y - hc.y, -0.02, 0.06))
        return 0.8 * bk * (1 - float(real._smooth(p.z, E.z - 0.02, E.z + 0.06)))

    eyes = [E + Vector((sx * 0.032 * u, 0.0, 0.0)) for sx in (1, -1)]
    nb = Vector((0, -1, -slope)).normalized()
    hood = real.garment(c, man, "hood", "primary",
                        lambda p: (lead(p) in ("head", "neck") and p.z > hood_hem - 0.03
                                   and all((Vector(p) - q).length > 0.03 for q in eyes)),
                        [((0, o_y, E.z), nb, lambda q: q.z >= E.z - 0.004),
                         ((0, o_y, E.z), (0, -1, 0), lambda q: q.z < E.z + 0.004),
                         ((0, 0, hood_hem), (0, 0, -1))],
                        ease=h_ease, smooth=16, pin=h_pin, slack=h_slack, bend=6.0, texel=1.2, frames=45)
    c.hide_under(hood.low, 0.065, 1)
    th = tree(hood.low)
    # A rolled edge round the opening, the drawcords with clay cord locks at its lower ends.
    hme = hood.low.data
    rim = max(real.boundary_loops(hood.low), key=len)
    pts = [hme.vertices[i].co.copy() for i in rim]
    k0 = min(range(len(pts)), key=lambda i: pts[i].z)
    pts = pts[k0:] + pts[:k0]
    arc = [p for p in pts if p.z > hood_hem + 0.012 and p.y - hc.y < 0.03]
    rim_pts = relax(resample(arc, 0.011), 3, closed=False)
    if len(rim_pts) > 3:
        skinned_on(c, hood.low, tube("hood_rim", rim_pts, 0.0042, "ripstop.primary", segs=6))
        for p0 in (rim_pts[0], rim_pts[-1]):
            sx = 1 if p0.x > 0 else -1
            p0 = p0 + Vector((sx * 0.004, 0.0, 0.0))
            cord = [p0, p0 + Vector((sx * 0.004, -0.004, -0.02)), p0 + Vector((sx * 0.005, -0.006, -0.042))]
            c.rigid(tube("drawcord", cord, 0.0017, "webbing", segs=5), "head")
            q = cord[1]
            c.rigid(hard(kit.cyl("cord_lock", q + Vector((0, 0, 0.008)), q + Vector((0, 0, -0.008)), 0.0045, "grey", segs=10, bevel=0.001), "polymer.accent"), "head")
            c.rigid(kit.cyl("cord_end", cord[-1] + Vector((0, 0, 0.004)), cord[-1] + Vector((0, 0, -0.006)), 0.0028, "gunmetal", segs=8), "head")
    # The hood's three panels: two seams from the brow over the crown to the nape.
    for sx in (1, -1):
        sm = []
        for k in range(26):
            el = math.radians(40 + 175 * k / 25)
            d = Vector((0, -math.cos(el), math.sin(el)))
            o0 = hc + Vector((sx * 0.036, 0, 0))
            loc, _ = hit(th, o0, d)
            if loc is None or (loc - o0).length > 0.2 or fd(loc) < 0.014 or loc.z < hood_hem + 0.05:
                continue
            sm.append(loc + d * 0.001)
        if len(sm) > 3:
            skinned_on(c, hood.low, tube("hood_seam", relax(sm, 2, closed=False), 0.0021, "ripstop.primary", segs=5))

    # ---------------------------------------------------------------- respirator
    tb = tree(man.low)
    mouth = E + Vector((0, 0, -0.072 * u))
    mask = kit.shell(man.low, lambda p: lead(p) == "head" and p.y < E.y + 0.05 and p.z < E.z - 0.005, "mask", "rubber",
                     offset=0.0095, thick=0.0035, smooth_iter=16, detail=0.45,
                     inside=[kit.blob_cutter("mask_cut", mouth + Vector((0, 0.05, -0.006)), (0.066, 0.13, 0.058), rot=(-12, 0, 0))])
    c.rigid(mask, "head")
    tm = tree(mask)
    loc, _ = hit(tm, mouth + Vector((0, -0.3, -0.008)), (0, 1, 0))
    vp = loc if loc is not None else mouth + Vector((0, -0.05, 0))
    valve = kit.cyl("valve", vp + Vector((0, 0.004, 0)), vp + Vector((0, -0.016, -0.003)), 0.019, "slate", r1=0.016, segs=20, bevel=0.002)
    kit.cut(valve, *[kit.block("vent", vp + Vector((0, -0.016, -0.003 + dz)), (0.022, 0.006, 0.0026), "steel", bevel=0) for dz in (-0.008, -0.003, 0.002, 0.007)])
    c.rigid(valve, "head")
    c.rigid(kit.block("valve_frame", vp + Vector((0, 0.002, 0.016)), (0.03, 0.012, 0.012), "slate", bevel=0.003), "head")
    for sx in (1, -1):
        ctr = mouth + Vector((sx * 0.046, -0.0, -0.002))
        d = Vector((sx * 0.8, -0.6, -0.12)).normalized()
        loc, nor = hit(tm, ctr + d * 0.2, -d)
        at = loc if loc is not None else ctr + d * 0.03
        n = (nor if nor is not None and nor.dot(d) > 0 else d).lerp(d, 0.5).normalized()
        c.rigid(kit.cyl("filter_mount", at - n * 0.002, at + n * 0.006, 0.02, "rubber", segs=18, bevel=0.0015), "head")
        filt = kit.cyl("filter", at + n * 0.005, at + n * 0.017, 0.031, "grey", r1=0.029, segs=24, bevel=0.003)
        c.rigid(hard(filt, "polymer.accent"), "head")
        grille = kit.cyl("filter_grille", at + n * 0.016, at + n * 0.0195, 0.021, "slate", segs=16, bevel=0.001)
        side = n.cross(Vector((0, 0, 1))).normalized()
        up2 = side.cross(n)
        kit.cut(grille, *[oriented(kit.block("slot", (0, 0, 0), (0.0028, 0.012, 0.03 - 0.25 * abs(dx)), "steel", bevel=0), at + n * 0.02 + side * dx, side, n, up2)
                          for dx in (-0.0105, -0.0035, 0.0035, 0.0105)], solver="MANIFOLD")
        c.rigid(grille, "head")
        # Head-harness straps from the frame back along the cheek, under the hood.
        for dz, ez in ((0.016, 0.0), (-0.016, -0.06)):
            st = at + up2 * dz
            ear = hc + Vector((sx * 0.07, 0.01, ez))
            pts = []
            for k in range(6):
                q = st.lerp(ear, k / 5)
                dd = (q - hc).normalized()
                loc, _ = hit(tb, hc, dd)
                if loc is not None:
                    pts.append(loc + dd * (0.004 + 0.004 * (1 - k / 5)))
            if len(pts) > 2:
                c.rigid(sweep("mask_strap", smooth_path(pts, 2), 0.011, 0.0022, "webbing", lambda p: Vector(p) - hc), "head")

    # ---------------------------------------------------------------- goggles on the hood
    D = Vector((0, -math.cos(math.radians(38)), math.sin(math.radians(38))))
    loc, nor = hit(th, hc + D * 0.4, -D)
    g_at = loc if loc is not None else hc + D * 0.12
    g_n = (nor if nor is not None and nor.dot(D) > 0 else D).lerp(D, 0.65).normalized()
    g_up = (Vector((0, 1, 0)) - g_n * g_n.dot(Vector((0, 1, 0)))).normalized()
    lens_o = []
    for a in range(0, 360, 20):
        t = math.radians(a)
        x = 0.078 * math.copysign(abs(math.cos(t)) ** 0.7, math.cos(t))
        z = 0.026 * math.copysign(abs(math.sin(t)) ** 0.8, math.sin(t))
        if z < 0 and abs(x) < 0.025:
            z += 0.012 * (1 - abs(x) / 0.025)   # the nose cut-out
        lens_o.append((x, z))
    frame_o = [(x * 1.12, z * 1.25 + (0.002 if z > 0 else -0.002)) for x, z in lens_o]
    gog = [panel("goggle_frame", frame_o, 0.0, 0.016, "grey", bevel=0.003),
           panel("goggle_lens", lens_o, -0.016, 0.003, "runner_lens", bevel=0.0008)]
    Mg = frame(g_at + g_n * 0.0, g_n, g_up)
    put(gog, Mg, 0.105, step=0.01)
    for o in gog:
        c.rigid(o, "head")
    # The goggle strap round the hood, tilted down to the back of the head.
    strap = []
    X = Vector((1, 0, 0))
    for a in range(55, 306, 10):
        t = math.radians(a)
        d = (X * math.sin(t) + D * math.cos(t)).normalized()
        loc, _ = hit(th, hc, d)
        if loc is not None and (loc - hc).length < 0.2:
            strap.append(loc + d * 0.0045)
    if len(strap) > 3:
        c.rigid(sweep("goggle_strap", resample(relax(smooth_path(strap, 2), 4, closed=False), 0.018), 0.02, 0.003, "webbing", lambda p: Vector(p) - hc), "head")


def build():
    b = real.Anatomy(height=1.80, body="male", sole=0.028)
    c = real.begin("runner", b)
    man = real.body(c, stubble=0.6)
    J, seg = b.j, kit.seg_dist
    lead = real.bones_at(man)
    armpit = b.at("armpit")
    crotch = b.at("crotch")
    neck = J("neck", 0.0)
    rnd = random.Random(7)

    def on_arm(p):
        return lead(p) in ARMS

    # ---------------------------------------------------------------- gloves
    gloves = real.gloves(c, man, "glove", cuff=0.045)
    tg = tree(gloves)
    for s, sx in (("L", 1), ("R", -1)):
        W = Vector(b.rest["hand." + s][0])
        Lh = (Vector(b.rest["hand." + s][1]) - W).normalized()
        mcp = [Vector(b.rest[f"f_{f}.1.{s}"][0]) for f in ("index", "middle", "ring", "pinky")]
        T = mcp[0] - mcp[3]
        T = (T - Lh * T.dot(Lh)).normalized()
        Pn = Lh.cross(T).normalized()
        if Pn.x * sx > 0:
            Pn = -Pn
        back = -Pn
        mid = sum(mcp, Vector()) / 4
        loc, _ = hit(tg, mid + back * 0.12, -back)
        loc = loc if loc is not None else mid + back * 0.02
        guard = kit.block("knuckle", (0, 0, 0), (0.07, 0.009, 0.022), "slate", bevel=0.003)
        kit.cut(guard, *[kit.block("groove", (x, 0.005, 0), (0.0035, 0.004, 0.03), "steel", bevel=0) for x in (-0.012, 0.012)])
        M = Matrix((T, back, Lh)).transposed().to_4x4()
        M.translation = loc + back * 0.0045 - Lh * 0.004
        guard.data.transform(M)
        c.rigid(guard, "hand." + s)
        ax = J("hand." + s, 0.0) - J("forearm." + s, 0.0)
        cc = J("hand." + s, 0.0) - ax.normalized() * 0.012
        r = _radius(tg, cc, ax)
        c.rigid(band("glove_cuff", cc, (r + 0.003, r * 0.82 + 0.003), 0.022, 0.004, "glove", axis=ax), "hand." + s)
        c.rigid(hard(kit.block("cuff_tab", cc + back * (r + 0.006), (0.016, 0.004, 0.022), "grey", bevel=0.0012), "polymer.accent"), "hand." + s)

    # ---------------------------------------------------------------- pilot suit
    # One fitted suit from the collar to the boots: snug on the body, room at the elbows, armpits
    # and knees for the pose, the sleeves stacking above rib-knit cuffs, the legs tucked into the boots.
    boot_top = b.sole + 0.165
    hem = boot_top - 0.04
    belt_z = b.hip_z + 0.065          # the harness waist belt
    collar_top = (Vector((0, 0, neck.z + 0.064)), Vector((0, -0.42, 1)).normalized())
    elbows = [J("forearm." + s, 0.0) for s in ("L", "R")]
    knees = [J("lower_leg." + s, 0.0) for s in ("L", "R")]

    cuts = [collar_top]
    for s in ("L", "R"):
        e, w = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        cuts.append((e.lerp(w, 0.88), w - e, lambda p, e=e, w=w: on_arm(p) and seg(p, e, w + (w - e) * 0.6) < 0.09))
    cuts.append(((0, 0, hem), (0, 0, -1), lambda p: lead(p) in LEGS | FEET))

    def ease(p):
        if on_arm(p):
            el = min((p - e).length for e in elbows)
            arm = min(seg(p, J("upper_arm." + s, 0.3), J("forearm." + s, 1.0)) for s in ("L", "R"))
            return 0.0085 + 0.007 * float(real._smooth(0.11 - el, 0.0, 0.05)) + 0.004 * max(0.0, min(1.0, (0.09 - arm) / 0.03))
        if p.z > neck.z - 0.03:
            return 0.006 + 0.008 * float(real._smooth(p.z, neck.z - 0.03, neck.z + 0.01))   # the standing collar, over the hood
        if lead(p) in LEGS | FEET:
            kn = min((p - k).length for k in knees)
            return 0.007 + 0.004 * float(real._smooth(0.12 - kn, 0.0, 0.05))
        if p.z > armpit - 0.08:
            return 0.0065 + 0.003 * float(real._smooth(p.z, armpit - 0.08, armpit))
        return 0.006

    def pin(p):
        if p.z > neck.z - 0.005 and not on_arm(p):
            return 1.0
        if p.z < hem + 0.02 and lead(p) in LEGS | FEET:
            return 1.0
        if abs(p.z - belt_z) < 0.022 and not on_arm(p):
            return 1.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.88)
            d = (wr - e).normalized()
            if on_arm(p) and seg(p, e, wr) < 0.1 and (p - wr).dot(d) > -0.02:
                return 1.0
        return 0.0

    def slack(p):
        w = 0.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.88)
            d = wr - e
            L = d.length
            d.normalize()
            t = (p - e).dot(d) / L
            if on_arm(p) and seg(p, e, wr) < 0.1 and t > 0.35:
                w = max(w, 0.5 * min(1.0, (t - 0.35) / 0.45))
        if lead(p) in LEGS and boot_top < p.z < boot_top + 0.1:
            w = max(w, 0.4 * (1 - (p.z - boot_top) / 0.1))
        if not on_arm(p) and belt_z + 0.02 < p.z < belt_z + 0.08:
            w = max(w, 0.3 * (1 - (p.z - belt_z - 0.02) / 0.06))
        return w

    def cuff(p):
        for s in ("L", "R"):
            e, w = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
            d = (w - e).normalized()
            if on_arm(p) and seg(p, e, w) < 0.09 and (p - e.lerp(w, 0.78)).dot(d) > 0:
                return True
        return False

    def gusset(p):
        """Stretch knit under the arms: the torso's sides and the inside of the upper sleeves."""
        if on_arm(p):
            for s, sx in (("L", 1), ("R", -1)):
                t, a = _limb(J("upper_arm." + s, 0.0), J("upper_arm." + s, 1.0))(p)
                if p.x * sx > 0 and t < 0.7 and angdiff(a, -90 * sx) < 36:
                    return True
            return False
        a = math.degrees(math.atan2(abs(p.x), -p.y))
        return armpit - 0.2 < p.z < armpit + 0.01 and 74 < a < 110

    suit = real.garment(c, man, "suit", "twill.primary",
                        lambda p: lead(p) in TORSO | ARMS | LEGS | {"neck"} and p.z > hem - 0.05,
                        cuts, ease=ease, pin=pin, slack=slack, bend=11.0, texel=1.25,
                        trims=[("knit.primary", lambda p: cuff(p) or gusset(p))])
    c.hide_under(suit.low, 0.05, 2)
    ts = tree(suit.low)

    # Padding over the suit: quilted caps on the shoulders, pads on the elbows (moulded to the sleeve,
    # rounded corners), a thigh pocket on the right.
    for s, sx in (("L", 1), ("R", -1)):
        ua0, ua1 = J("upper_arm." + s, 0.0), J("upper_arm." + s, 1.0)
        top = ua0 + (ua0 - ua1).normalized() * 0.03
        r = _radius(ts, ua0.lerp(ua1, 0.2), ua1 - ua0)
        pad = wrap("shoulder_pad", top, ua0.lerp(ua1, 0.4), r + 0.01, r + 0.004, 90 * sx - 64, 90 * sx + 64, 0.007, "slate",
                   nt=7, nphi=10, bevel=0.003, bulge=0.003, round_ends=3.0, fit=(ts, 0.0025))
        c.rigid(hard(pad, "cordura.primary"), "upper_arm." + s)
        tp = tree(pad)
        for t in (0.42, 0.7):
            q = top.lerp(ua0.lerp(ua1, 0.4), t)
            arc = []
            for k in range(9):
                ph = 90 * sx - 50 + 100 * k / 8
                pts_ = limb_pts(tp, q, q + (ua1 - ua0).normalized() * 0.01, ph, 0.0, 0.0001, 2, 0.0004)
                if pts_:
                    arc.append(pts_[0])
            if len(arc) > 3:
                c.rigid(tube("quilt", arc, 0.0014, "slate", segs=4), "upper_arm." + s)
        fa0, fa1 = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        A_ = (fa1 - fa0).normalized()
        r = _radius(ts, fa0 + A_ * 0.01, A_) + 0.004
        pad = wrap("elbow_pad", fa0 - A_ * 0.035, fa0 + A_ * 0.06, r, r - 0.004, 180 - 58, 180 + 58, 0.008, "slate",
                   nt=5, nphi=8, bevel=0.003, bulge=0.004, round_ends=3.0, fit=(ts, 0.0025))
        c.rigid(hard(pad, "cordura.primary"), "forearm." + s)
    ul0, ul1 = J("upper_leg.R", 0.0), J("upper_leg.R", 1.0)
    thigh = _limb(ul0, ul1)
    real.patch(c, suit.low, "thigh_pocket", "twill.primary",
               lambda p: lead(p) in LEGS and p.x < 0 and (lambda t, a: 0.36 < t < 0.66 and angdiff(a, -90) < 32)(*thigh(p)),
               lift=0.002, puff=0.011, thick=0.0025, subdivide=0)
    real.patch(c, suit.low, "pocket_flap", "twill.primary",
               lambda p: lead(p) in LEGS and p.x < 0 and (lambda t, a: 0.33 < t < 0.41 and angdiff(a, -90) < 35)(*thigh(p)),
               lift=0.014, puff=0.002, thick=0.0025, subdivide=0)

    # Hard knee caps over the padding, strapped behind the knee.
    for s, sx in (("L", 1), ("R", -1)):
        knee = J("lower_leg." + s, 0.04)
        cut_ = kit.slab("cap_cut", kit.rounded([(knee.x - 0.05, knee.z - 0.07), (knee.x + 0.05, knee.z - 0.07),
                                                 (knee.x + 0.052, knee.z + 0.05), (knee.x - 0.052, knee.z + 0.05)], 0.025), -0.4, knee.y - 0.01)
        cap = kit.plate(suit.low, cut_, "knee_cap", "slate", offset=0.012, thick=0.008, bevel=0.004)
        c.rigid(cap, "lower_leg." + s)
        kz = J("lower_leg." + s, 0.2)
        ring = hug_ring([ts, tree(cap)], kz, J("lower_leg." + s, 1.0) - J("lower_leg." + s, 0.0), 0.003, n=18)
        c.rigid(sweep("cap_strap", ring, 0.02, 0.004, "webbing", radial(kz, J("lower_leg." + s, 1.0) - J("lower_leg." + s, 0.0)), closed=True),
                "lower_leg." + s)

    # Clay piping: the collar's top edge, a stripe from the collar over each shoulder and down the
    # outside of the arm to the cuff, and down the outside of each leg to the boot.
    loops = real.boundary_loops(suit.low)
    me = suit.low.data
    collar = max(loops, key=lambda lp: sum(me.vertices[i].co.z for i in lp) / len(lp))
    pts = relax([me.vertices[i].co.copy() for i in collar][::2], 2)
    skinned_on(c, suit.low, tube("piping", pts, 0.0028, "cordura.accent", closed=True, segs=5))
    for s, sx in (("L", 1), ("R", -1)):
        top = []
        for x in (0.092, 0.112, 0.132, 0.15):
            loc, _ = hit(ts, (sx * x, 0.005, 2.0), (0, 0, -1))
            if loc is not None:
                top.append(loc + Vector((0, 0, 0.002)))
        ua0, ua1 = J("upper_arm." + s, 0.0), J("upper_arm." + s, 1.0)
        fa0, fa1 = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        arm = limb_pts(ts, ua0, ua1, lambda t: 90 * sx - 8 * sx * t, -0.08, 1.0, 22, 0.002)
        arm += limb_pts(ts, fa0, fa1, 82 * sx, 0.08, 0.78, 14, 0.002)
        path = resample(smooth_path(top + arm, 3), 0.016)
        skinned_on(c, suit.low, tube("piping", path, 0.0024, "cordura.accent", segs=5))
        lg = limb_pts(ts, J("upper_leg." + s, 0.0), J("upper_leg." + s, 1.0), 90 * sx, 0.06, 1.0, 26, 0.002)
        lg += limb_pts(ts, J("lower_leg." + s, 0.0), J("lower_leg." + s, 1.0), 92 * sx, 0.06, 0.74, 18, 0.002)
        path = resample(smooth_path(lg, 3), 0.016)
        skinned_on(c, suit.low, tube("piping", path, 0.0024, "cordura.accent", segs=5))
    # Front zip on the collar, with its pull.
    zip_pts = []
    for z in [collar_top[0].z - 0.004 - 0.012 * i for i in range(9)]:
        loc, _ = hit(ts, (0, -0.5, z), (0, 1, 0))
        if loc is not None:
            zip_pts.append(loc + Vector((0, -0.0015, 0)))
    if len(zip_pts) > 2:
        skinned_on(c, suit.low, tube("zip", zip_pts, 0.0026, "slate", segs=6))
        zp = zip_pts[0] + Vector((0, -0.004, -0.012))
        c.rigid(kit.block("zip_pull", zp, (0.009, 0.003, 0.022), "gunmetal", bevel=0.001), "neck")

    head_gear(c, man, lead, neck)

    # ---------------------------------------------------------------- boots
    real.boots(c, man, "boot", sole_kind="rubber", trim="rubber", top=0.165, lace="webbing", tab="grey")
    for o, _, _ in c.parts:
        if o.name.startswith("pull_tab"):
            hard(o, "polymer.accent")

    # ---------------------------------------------------------------- climbing harness
    WEB = "webbing.secondary"
    ctr = (0, 0.0)
    belt = arc_pts(ts, ctr, belt_z, 0.005, 0, 360, 37)[:-1]
    o = sweep("harness_belt", belt, 0.042, 0.008, "webbing", radial((0, 0, 0)), closed=True)
    c.rigid(hard(o, WEB), "hips")
    pad = arc_pts(ts, ctr, belt_z + 0.004, 0.013, 95, 265, 15)
    o = sweep("belt_pad", pad, 0.068, 0.009, "webbing", radial((0, 0, 0)))
    c.rigid(hard(o, "cordura.secondary"), "hips")
    front = arc_pts(ts, ctr, belt_z, 0.01, 0, 0, 1)[0]
    bk = kit.block("harness_buckle", front + Vector((0, -0.006, 0)), (0.05, 0.008, 0.038), "gunmetal", bevel=0.003)
    kit.cut(bk, kit.block("slot", front + Vector((0, -0.012, 0)), (0.036, 0.01, 0.012), "steel", bevel=0))
    c.rigid(bk, "hips")
    c.rigid(kit.block("buckle_bar", front + Vector((0, -0.013, 0.0)), (0.04, 0.005, 0.005), "bright", bevel=0.001), "hips")
    # Leg loops round the tops of the thighs, higher on the inside.
    tie = {}
    for s, sx in (("L", 1), ("R", -1)):
        a0, a1 = J("upper_leg." + s, 0.0), J("upper_leg." + s, 1.0)
        z0 = crotch - 0.06
        tt = (a0.z - z0) / (a0.z - a1.z)
        cl = a0.lerp(a1, tt)
        ring = []
        for k in range(24):
            a = 2 * math.pi * k / 24
            d = Vector((math.sin(a), -math.cos(a), 0))
            z = z0 + 0.022 * (-math.sin(a) * sx) - 0.006 * math.cos(a)
            loc, _ = hit(ts, Vector((cl.x, cl.y, z)), d)
            ring.append(loc + d * 0.005 if loc is not None and (loc - Vector((cl.x, cl.y, z))).length < 0.2 else Vector((cl.x, cl.y, z)) + d * 0.09)
        o = sweep("leg_loop", ring, 0.036, 0.008, "webbing", radial(cl), closed=True)
        c.rigid(hard(o, WEB), "upper_leg." + s)
        tie[s] = ring[21 if s == "L" else 3]   # inner front
        # Elastic riser from the back of the loop up to the belt.
        bot = ring[12]
        rs = []
        for i in range(7):
            z = bot.z + (belt_z - 0.02 - bot.z) * i / 6
            loc, _ = hit(ts, (sx * 0.075 + sx * 0.01 * (1 - i / 6), 0.5, z), (0, -1, 0))
            if loc is not None:
                rs.append(loc + Vector((0, 0.004, 0)))
        if len(rs) > 2:
            c.add(sweep("riser", rs, 0.016, 0.004, "webbing", lambda p: Vector((0, 1, 0))), ["hips", "upper_leg." + s])
    # Belay loop (clay) from the belt's front down to the leg loops' tie-in, a locking carabiner on it.
    bl = []
    for i in range(6):
        z = belt_z - 0.022 - (belt_z - 0.022 - (tie["L"].z + 0.012)) * i / 5
        loc, _ = hit(ts, (0, -0.5, z), (0, 1, 0))
        if loc is not None:
            bl.append(loc + Vector((0, -0.012 - 0.006 * math.sin(math.pi * i / 5), 0)))
    if len(bl) > 2:
        o = sweep("belay_loop", smooth_path(bl, 3), 0.022, 0.009, "webbing", lambda p: Vector((0, -1, 0)))
        c.rigid(hard(o, "webbing.accent"), "hips")
        for s in ("L", "R"):
            a, bb = bl[-1] + Vector((0, 0.002, 0)), tie[s]
            o = sweep("tie_in", smooth_path([a, a.lerp(bb, 0.5) + Vector((0, -0.006, -0.004)), bb], 3), 0.02, 0.007, "webbing",
                      lambda p: Vector((0, -1, 0)))
            c.add(hard(o, WEB), ["hips", "upper_leg." + s])
        c.rigid(carabiner("belay_biner", bl[-2] + Vector((0, -0.01, 0)), (0, -0.25, -1), (0, -1, 0.1), size=0.085, material="metal.accent",
                          lock=True), "hips")
    # Gear loops on the hips with carabiners and a quickdraw.
    for s, sx in (("L", 1), ("R", -1)):
        for k, ang in enumerate((68, 112)):
            p0 = arc_pts(ts, ctr, belt_z - 0.02, 0.009, sx * ang, sx * ang, 1)[0]
            out = Vector((p0.x, p0.y, 0)).normalized()
            tan = Vector((0, 0, 1)).cross(out)
            loop = [p0 - tan * 0.022, p0 - tan * 0.018 + out * 0.004 + Vector((0, 0, -0.03)), p0 + tan * 0.018 + out * 0.004 + Vector((0, 0, -0.03)),
                    p0 + tan * 0.022]
            c.rigid(tube("gear_loop", smooth_path(loop, 3), 0.0035, "black", segs=6), "hips")
            low = p0 + out * 0.008 + Vector((0, 0, -0.032))
            kind = "metal.accent" if k == 0 else "gunmetal"
            c.rigid(carabiner("biner", low + tan * (0.006 * sx), (0, 0, -1), out, size=0.066, material=kind), "hips")
            if k == 1 and s == "L":
                # A quickdraw: a second carabiner on a short dogbone below the first.
                q0 = low + Vector((0, 0, -0.06)) + out * 0.004
                c.rigid(kit.block("dogbone", q0 + Vector((0, 0, -0.03)), (0.016, 0.008, 0.065), "black", bevel=0.003), "hips")
                c.rigid(hard(kit.block("dogbone_band", q0 + Vector((0, 0, -0.03)), (0.0175, 0.0085, 0.02), "grey", bevel=0.002), "polymer.accent"), "hips")
                c.rigid(carabiner("biner", q0 + Vector((0, 0, -0.06)), (0, 0, -1), out, size=0.062, material="bright"), "hips")

    # ---------------------------------------------------------------- Regime chest plate, repainted
    zt, zb = armpit + 0.11, armpit - 0.155
    outline = kit.rounded([(-0.04, zt - 0.028), (0.04, zt - 0.028), (0.078, zt), (0.11, zt - 0.004), (0.136, zt - 0.072),
                           (0.128, zb + 0.07), (0.094, zb + 0.01), (0.0, zb - 0.014), (-0.094, zb + 0.01), (-0.128, zb + 0.07),
                           (-0.136, zt - 0.072), (-0.11, zt - 0.004), (-0.078, zt)], 0.012)
    zc = (zt + zb) / 2
    base = ell_y(0, 0.0, zc + 0.03, 0.21, 0.17, 0.3, -1)

    def keel(x, z):
        return -0.005 * math.exp(-(x / 0.016) ** 2) * float(real._smooth(z, zb, zb + 0.08))
    # Fit: the plate's back clears the suit by 1.4 cm where it comes closest.
    shift = -1.0
    for x in [i * 0.02 for i in range(-7, 8)]:
        for z in [zb + 0.02 + (zt - zb - 0.04) * j / 10 for j in range(11)]:
            loc, _ = hit(ts, (x, -0.6, z), (0, 1, 0))
            if loc is None:
                continue
            need = (base(x, z) + 0.011) - (loc.y - 0.014)
            shift = max(shift, need)
    yf = lambda x, z: base(x, z) - shift + keel(x, z)   # noqa: E731
    plate = grid_plate("chest_plate", -0.15, 0.15, zb - 0.03, zt + 0.01, yf, 0.011, "steel", step=0.016)
    plate = kit.intersect(plate, kit.slab("plate_cut", outline, -0.6, 0.2))
    # Where the code was: ground down to two shallow panels with the grinder's strokes in them, then
    # painted over; a raised bead round the edge, as the Regime moulds them.
    cutters = []
    for sx in (1, -1):
        rec = grid_plate("recess", -0.15, 0.15, zt - 0.11, zt - 0.025, lambda x, z: yf(x, z) - 0.01, 0.0108, "steel", step=0.016)
        rec = kit.intersect(rec, kit.slab("recess_cut", rrect(min(sx * 0.03, sx * 0.104), zt - 0.1, max(sx * 0.03, sx * 0.104), zt - 0.036, 0.008), -0.6, 0.2))
        cutters.append(rec)
        for i in range(5):
            x = sx * rnd.uniform(0.045, 0.09)
            z = zt - 0.045 - i * 0.011 + rnd.uniform(-0.003, 0.003)
            o = kit.block("scratch", (0, 0, 0), (rnd.uniform(0.03, 0.05), 0.0034, 0.0016), "steel", bevel=0)
            o.data.transform(Matrix.Translation((x, yf(x, z) + 0.0008, z)) @ Matrix.Rotation(math.radians(-14 * sx + rnd.uniform(-5, 5)), 4, "Y"))
            cutters.append(o)
    kit.cut(plate, *cutters, solver="MANIFOLD")
    hard(plate, "polymer.cream")
    for f in plate.data.polygons:
        f.material_index = 0
    plate["bevel"] = 0.0035
    plate["segs"] = 2
    c.rigid(plate, "chest")
    ring2d = resample([Vector((x, z, 0)) for x, z in grow(outline, -0.005)], 0.012, closed=True)
    bead = [Vector((q.x, yf(q.x, q.y) - 0.0012, q.y)) for q in ring2d]
    c.rigid(tube("plate_bead", relax(bead, 1), 0.0028, "polymer.cream", closed=True, segs=5), "chest")
    # A clay stripe painted across it, and ghosts of the code left in the grind marks.
    stripe = grid_plate("stripe", -0.15, 0.15, zb, zt, lambda x, z: yf(x, z) - 0.0007, 0.0012, "grey", step=0.016)
    stripe = kit.intersect(stripe, kit.slab("stripe_cut", [(-0.17, zb + 0.072), (0.17, zb + 0.122), (0.17, zb + 0.142), (-0.17, zb + 0.092)], -0.6, 0.2))
    stripe = kit.intersect(stripe, kit.slab("plate_cut", outline, -0.6, 0.2))
    c.rigid(hard(stripe, "polymer.accent"), "chest")
    for sx in (1, -1):
        for row in range(4):
            z = zt - 0.05 - row * 0.012
            x = sx * 0.04
            while abs(x) < 0.094:
                w = rnd.choice((0.004, 0.006, 0.009, 0.013))
                if rnd.random() < 0.22:
                    xc = x + sx * w / 2
                    o = kit.block("code_ghost", (xc, yf(xc, z) + 0.0006, z), (w, 0.001, 0.005), "slate", bevel=0)
                    c.rigid(o, "chest")
                x += sx * (w + 0.003)
    for x, z in ((0.092, zt - 0.03), (-0.092, zt - 0.03), (0.104, zb + 0.06), (-0.104, zb + 0.06)):
        c.rigid(kit.cyl("plate_screw", (x, yf(x, z) + 0.001, z), (x, yf(x, z) - 0.003, z), 0.0045, "gunmetal", segs=10, bevel=0.0008), "chest")

    # ---------------------------------------------------------------- back plate with the uplink stub
    bzt, bzb = armpit + 0.1, armpit - 0.075
    b_out = kit.rounded([(-0.07, bzt + 0.005), (0.07, bzt + 0.005), (0.122, bzt - 0.02), (0.112, bzb + 0.03), (0.07, bzb),
                         (-0.07, bzb), (-0.112, bzb + 0.03), (-0.122, bzt - 0.02)], 0.014)
    bbase = ell_y(0, 0.0, (bzt + bzb) / 2 + 0.02, 0.22, 0.15, 0.3, 1)
    bshift = -1.0
    for x in [i * 0.02 for i in range(-6, 7)]:
        for z in [bzb + 0.01 + (bzt - bzb - 0.02) * j / 8 for j in range(9)]:
            loc, _ = hit(ts, (x, 0.6, z), (0, -1, 0))
            if loc is None:
                continue
            bshift = max(bshift, (loc.y + 0.013) - (bbase(x, z) - 0.01))
    byf = lambda x, z: bbase(x, z) + bshift   # noqa: E731
    bplate = grid_plate("back_plate", -0.14, 0.14, bzb - 0.02, bzt + 0.02, byf, 0.01, "cream", back=True, step=0.016)
    bplate = kit.intersect(bplate, kit.slab("back_cut", b_out, -0.2, 0.6))
    hard(bplate, "polymer.cream")
    bplate["bevel"] = 0.0035
    bplate["segs"] = 2
    c.rigid(bplate, "chest")
    mz = bzt - 0.05
    my = byf(0, mz)
    mount = kit.block("mount", (0, my + 0.014, mz), (0.1, 0.03, 0.075), "cream", bevel=0.006)
    kit.cut(mount, kit.cyl("socket", (0, my + 0.005, mz), (0, my + 0.04, mz), 0.022, "steel", segs=20),
            kit.block("mount_groove", (0, my + 0.03, mz - 0.03), (0.11, 0.006, 0.004), "steel", bevel=0))
    hard(mount, "polymer.cream")
    for f in mount.data.polygons:
        f.material_index = 0
    c.rigid(mount, "chest")
    c.rigid(kit.cyl("socket_floor", (0, my + 0.008, mz), (0, my + 0.012, mz), 0.022, "black", segs=20), "chest")
    stub = kit.cyl("antenna_stub", (0.03, my + 0.02, mz + 0.03), (0.034, my + 0.034, mz + 0.105), 0.008, "gunmetal", segs=12, bevel=0.0015)
    kit.cut(stub, kit.block("snap", (0.034, my + 0.034, mz + 0.112), (0.04, 0.04, 0.02), "steel", rot=35))
    c.rigid(stub, "chest")
    c.rigid(kit.cyl("stub_base", (0.03, my + 0.012, mz + 0.03), (0.03, my + 0.03, mz + 0.03), 0.013, "gunmetal", segs=14, bevel=0.002), "chest")
    for i, (dx, dz) in enumerate(((-0.012, 0.004), (0.0, -0.006), (0.012, 0.002))):
        p0 = Vector((dx, my + 0.012, mz + dz))
        pts = [p0, p0 + Vector((dx * 0.8, 0.016, -0.008)), p0 + Vector((dx * 1.8 + 0.004, 0.026, -0.034 - 0.006 * i))]
        c.rigid(tube("cut_cable", pts, 0.0032, "rubber", segs=6), "chest")
        e = pts[-1]
        c.rigid(kit.cyl("cut_end", e, e + (e - pts[-2]).normalized() * 0.004, 0.002, "copper", segs=6), "chest")
    for x in (-0.04, 0.04):
        for dz in (-0.028, 0.028):
            c.rigid(kit.cyl("mount_screw", (x, my + 0.029, mz + dz), (x, my + 0.032, mz + dz), 0.0042, "gunmetal", segs=8, bevel=0.0006), "chest")

    # ---------------------------------------------------------------- harness straps on the plates
    def plate_pt(x, z):
        return Vector((x, yf(x, z) - 0.002, z))

    def bplate_pt(x, z):
        return Vector((x, byf(x, z) + 0.002, z))
    for s, sx in (("L", 1), ("R", -1)):
        xs = sx * 0.1
        pts = [plate_pt(sx * 0.1, zt - 0.025)]
        for y in (-0.10, -0.075, -0.05, -0.025, 0.0, 0.025, 0.05, 0.075):
            loc, _ = hit(ts, (xs, y, 2.0), (0, 0, -1))
            if loc is not None and loc.z > armpit + 0.05:
                pts.append(loc + Vector((0, 0, 0.007)))
        pts.append(bplate_pt(sx * 0.098, bzt - 0.02))
        path = smooth_path(pts, 3)
        o = sweep("shoulder_strap", path, 0.04, 0.007, "webbing", radial((sx * 0.1, 0, armpit + 0.02), (1, 0, 0)))
        c.rigid(hard(o, WEB), "chest")
        for p, n in ((plate_pt(sx * 0.1, zt - 0.03), (0, -1, 0)), (bplate_pt(sx * 0.098, bzt - 0.025), (0, 1, 0))):
            c.rigid(kit.block("strap_slot", p + Vector(n) * 0.003, (0.046, 0.005, 0.012), "gunmetal", bevel=0.0015), "chest")
        k = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.07))
        tan = (path[k + 1] - path[k - 1]).normalized()
        nn = radial((sx * 0.1, 0, armpit + 0.02), (1, 0, 0))(path[k]).normalized()
        c.rigid(side_buckle("strap_buckle", path[k] + nn * 0.007, -tan, nn, w=0.042, material="gunmetal"), "chest")
        # Side straps under the arms from the chest plate's lower corners to the back plate.
        sp = [plate_pt(sx * 0.13, zb + 0.06)] + arc_pts(ts, (0, 0.0), zb + 0.065, 0.008, sx * 62, sx * 128, 6) + [bplate_pt(sx * 0.105, bzb + 0.03)]
        o = sweep("side_strap", smooth_path(sp, 3), 0.03, 0.006, "webbing", radial((0, 0, 0)))
        c.rigid(hard(o, WEB), "chest")

    # ---------------------------------------------------------------- grapple pack, rope coil
    pz0, pz1 = belt_z + 0.04, bzb - 0.012
    py = -1.0
    for x in (-0.1, -0.05, 0.0, 0.05, 0.1):
        for z in (pz0, (pz0 + pz1) / 2, pz1):
            loc, _ = hit(ts, (x, 0.6, z), (0, -1, 0))
            if loc is not None:
                py = max(py, loc.y)
    py += 0.016
    pzc = (pz0 + pz1) / 2
    ph = pz1 - pz0
    pack = kit.block("grapple_pack", (0, py + 0.036, pzc), (0.235, 0.072, ph), "slate", bevel=0.014)
    kit.cut(pack, *[kit.block("vent", (sx * 0.1185, py + 0.036, pzc + dz), (0.012, 0.04, 0.0045), "steel", bevel=0)
                    for sx in (1, -1) for dz in (-0.03, -0.018, -0.006, 0.006)])
    c.rigid(pack, "spine")
    c.rigid(kit.block("pack_lid", (0, py + 0.073, pzc + 0.01), (0.2, 0.006, ph - 0.03), "gunmetal", bevel=0.004), "spine")
    # Cable drum across the top with the grapple line wound on it, clay flanges.
    dz_ = pz1 + 0.012
    drum_y = py + 0.04
    c.rigid(kit.cyl("drum", (-0.085, drum_y, dz_), (0.085, drum_y, dz_), 0.02, "gunmetal", segs=20, bevel=0.002), "spine")
    c.rigid(kit.cyl("line_wound", (-0.078, drum_y, dz_), (0.078, drum_y, dz_), 0.0245, "rubber", segs=20, bevel=0.003), "spine")
    for sx in (1, -1):
        c.rigid(hard(kit.cyl("drum_flange", (sx * 0.083, drum_y, dz_), (sx * 0.093, drum_y, dz_), 0.03, "grey", segs=20, bevel=0.002), "polymer.accent"), "spine")
        c.rigid(kit.block("drum_bracket", (sx * 0.1, drum_y - 0.012, dz_ - 0.012), (0.014, 0.04, 0.04), "slate", bevel=0.003), "spine")
    # Rope coil strapped across the pack's face: loose loops lying over each other, the ends wrapped.
    ry = py + 0.078
    rng = random.Random(11)
    for k in range(7):
        rx_ = 0.1 + rng.uniform(-0.006, 0.006)
        rz_ = 0.047 + rng.uniform(-0.005, 0.005)
        ox, oz = rng.uniform(-0.006, 0.006), rng.uniform(-0.004, 0.004)
        tilt = rng.uniform(-0.1, 0.1)
        ph_ = rng.uniform(0, 2 * math.pi)
        pts = []
        for a in range(0, 360, 12):
            t = math.radians(a)
            x = rx_ * math.cos(t) + ox
            pts.append(Vector((x, ry + 0.0072 * k + tilt * x + 0.0035 * math.sin(2 * t + ph_), pzc - 0.004 + oz + rz_ * math.sin(t))))
        c.rigid(tube("rope", pts, 0.0052, "canvas.cream", closed=True, segs=5), "spine")
    for sx in (1, -1):
        wpts = []
        for k in range(31):
            t = 2 * math.pi * k / 10
            wpts.append(Vector((sx * (0.103 + 0.013 * math.cos(t)), ry + 0.022 + 0.031 * math.sin(t), pzc - 0.012 + 0.018 * k / 30)))
        c.rigid(tube("rope_wrap", wpts, 0.0045, "canvas.cream", segs=5), "spine")
    sy = ry + 0.0072 * 6 + 0.014
    for sx in (1, -1):
        sp = [Vector((sx * 0.055, py + 0.074, pz1 + 0.006)), Vector((sx * 0.055, sy, pzc + 0.03)), Vector((sx * 0.055, sy, pzc - 0.035)),
              Vector((sx * 0.055, py + 0.074, pz0 - 0.004))]
        o = sweep("compression_strap", smooth_path(sp, 3), 0.024, 0.004, "webbing", lambda p: Vector((0, 1, 0)))
        c.rigid(hard(o, WEB), "spine")
        c.rigid(side_buckle("pack_buckle", Vector((sx * 0.055, sy + 0.005, pzc - 0.008)), (0, 0, -1), (0, 1, 0), w=0.028, material="gunmetal"), "spine")
    # The pack hangs from the back plate and the belt.
    for sx in (1, -1):
        for zz, zz2 in ((pz1 - 0.01, bzb + 0.02), (pz0 + 0.01, belt_z)):
            p0 = Vector((sx * 0.09, py + 0.002, zz))
            p1 = bplate_pt(sx * 0.09, zz2) if zz2 > pz1 else arc_pts(ts, (0, 0), zz2, 0.008, 180 - sx * 30, 180 - sx * 30, 1)[0]
            o = sweep("pack_strap", [p0, p0.lerp(p1, 0.5) + Vector((0, 0.004, 0)), p1], 0.022, 0.004, "webbing", lambda p: Vector((0, 1, 0)))
            c.rigid(hard(o, WEB), "spine")

    # ---------------------------------------------------------------- grapple launcher
    fa0, fa1 = J("forearm.L", 0.0), J("forearm.L", 1.0)
    A = (fa1 - fa0).normalized()
    out = Vector((1, 0, 0))
    out = (out - A * out.dot(A)).normalized()
    side = A.cross(out).normalized()     # toward the front of the hanging arm
    rr = _radius(ts, fa0.lerp(fa1, 0.5), A)
    br = wrap("bracer", fa0.lerp(fa1, 0.16), fa0.lerp(fa1, 0.8), rr + 0.006, rr + 0.002, 90 - 70, 90 + 70, 0.006, "slate",
              nt=6, nphi=10, bevel=0.003, fit=(ts, 0.0045))
    c.rigid(br, "forearm.L")
    tb_ = tree(br)

    def on_bracer(t, lift):
        q = fa0.lerp(fa1, t)
        loc, _ = hit(tb_, q + out * 0.3, -out)
        return (loc if loc is not None else q + out * (rr + 0.012)) + out * lift
    hz0, hz1 = 0.22, 0.74
    hc0, hc1 = on_bracer(hz0, 0.017), on_bracer(hz1, 0.017)
    L = (hc1 - hc0).length
    mid = (hc0 + hc1) / 2
    housing = kit.block("launcher", (0, 0, 0), (0.046, L, 0.03), "gunmetal", bevel=0.007)
    kit.cut(housing, *[kit.block("vent", (0.0, -L * 0.3 + i * 0.012, 0.015), (0.03, 0.0045, 0.008), "steel", bevel=0) for i in range(4)])
    oriented(housing, mid, side, (hc1 - hc0).normalized(), out)
    c.rigid(housing, "forearm.L")
    cover = hard(kit.block("launcher_cover", (0, 0, 0), (0.036, L * 0.5, 0.004), "cream", bevel=0.0015), "polymer.cream")
    oriented(cover, mid + out * 0.016 + A * (L * 0.18), side, A, out)
    c.rigid(cover, "forearm.L")
    muzzle = hc1 + A * 0.004
    c.rigid(kit.cyl("barrel", muzzle - A * 0.01, muzzle + A * 0.045, 0.0135, "gunmetal", segs=18, bevel=0.0015), "forearm.L")
    c.rigid(hard(kit.ring("muzzle_ring", muzzle + A * 0.04, A, 0.0175, 0.0105, 0.01, "grey", segs=20), "polymer.accent"), "forearm.L")
    tip = muzzle + A * 0.045
    c.rigid(kit.cyl("hook_bolt", tip - A * 0.004, tip + A * 0.03, 0.0095, "bright", r1=0.0035, segs=12, bevel=0.001), "forearm.L")
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.3
        d = out * math.cos(a) + side * math.sin(a)
        claw = kit.block("claw", (0, 0, 0), (0.004, 0.032, 0.006), "bright", bevel=0.0008)
        oriented(claw, tip + A * 0.012 + d * 0.0105, d.cross(A), A, d)
        c.rigid(claw, "forearm.L")
    sp_c = on_bracer(0.42, 0.012) + side * 0.03
    c.rigid(kit.cyl("spool", sp_c - side * 0.006, sp_c + side * 0.014, 0.019, "slate", segs=18, bevel=0.002), "forearm.L")
    c.rigid(hard(kit.cyl("spool_cap", sp_c + side * 0.014, sp_c + side * 0.018, 0.012, "grey", segs=16, bevel=0.001), "polymer.accent"), "forearm.L")
    for t in (0.3, 0.7):
        cc = fa0.lerp(fa1, t)
        r = _radius(ts, cc, A) + 0.004
        o = sweep("launcher_strap", hug_ring([ts, tb_], cc, A, 0.003, n=18), 0.022, 0.004, "webbing", radial(cc, A), closed=True)
        c.rigid(hard(o, WEB), "forearm.L")
        bkl = kit.block("strap_buckle", (0, 0, 0), (0.026, 0.006, 0.02), "gunmetal", bevel=0.0012)
        c.rigid(oriented(bkl, cc - side * (r + 0.003), A.cross(side), -side, A), "forearm.L")
    rel = hard(kit.block("release", (0, 0, 0), (0.012, 0.016, 0.008), "grey", bevel=0.002), "polymer.accent")
    c.rigid(oriented(rel, hc0.lerp(hc1, 0.72) + side * 0.026, side, A, out), "forearm.L")
    # The grapple line: off the drum, up the back past the plate, over the left shoulder and down the
    # outside of the arm into the launcher.
    line = [Vector((0.07, drum_y + 0.012, dz_ + 0.02)), Vector((0.11, drum_y + 0.004, dz_ + 0.05))]
    line += [bplate_pt(0.13, z) + Vector((0.004, 0.006, 0)) for z in (bzb + 0.05, bzt - 0.03)]
    for y in (0.06, 0.02, -0.02):
        loc, _ = hit(ts, (0.15, y, 2.0), (0, 0, -1))
        if loc is not None:
            line.append(loc + Vector((0, 0, 0.007)))
    line += limb_pts(ts, J("upper_arm.L", 0.0), J("upper_arm.L", 1.0), 125, 0.12, 0.95, 8, 0.006)
    line += [hc0 - A * 0.03 + out * 0.004, hc0 - A * 0.004]
    skinned_on(c, suit.low, tube("grapple_line", resample(smooth_path(line, 3), 0.02), 0.003, "rubber", segs=6))

    economise(c)
    return c


SPEC = {"build": build, "faction": "deserters", "budget": (25000, 80000),
        "loadout": "smg",
        "colors": {"primary": "#141413", "secondary": "#D4A27F", "accent": "#D97757"}}
