"""Handler, PMC: HALCYON's drone operator, the Contractor's kit fitted out to fly. A navy high-cut
ballistic helmet with the company mark, side rails carrying the over-ear headset, an NVG shroud and a
link beacon; a knit balaclava under it and wraparound AR glasses over its eye slot, so no skin shows
but a sliver round the eyes; a rugged white tablet on a cradle strapped to the left forearm, its
screen lit with the drone's feed; the navy HALCYON plate carrier with SMG pouches, the admin panel and
the sponsor patches, the yellow padded straps, a radio with a tall link whip, and on the back a dock
holding a white quadcopter in prop guards; the ripstop combat shirt with knit collar and cuffs, elbow
pads and sleeve patches, twill trousers with knee pads, a drop-leg holster, a cargo pocket and a spare
battery on the belt, tactical boots.

Built on the realistic layer (real.py) like the Contractor: a real body, gloved fists, shirt and
trousers draped by the cloth simulation; the helmet laid on an envelope of the head (the Acolyte's
Env) in the Juggernaut's satin "halcyon" coat; procedural surfaces baked into one 2048 atlas.

Tints: primary = combat shirt, secondary = trousers and balaclava, accent = carrier straps and the
dock latches (the Contractor's colours).
"""

import math

import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import kit
import real
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS
from chars.contractor import (tree, hit, frame, put, to_world, fit, panel, rrect, sweep, radial, smooth_path, logo, name_patch,
                              screws, hexagon, wrap, band, rigid_all, side_buckle, _radius, _ring_side, ring_pts, _limb, hazard_band,
                              economise, inside_poly)
from chars.acolyte import Env, Armour
from chars.runner import tube, relax, oriented
from chars.juggernaut import WHITE, NAVYH, FAST, remat, conform, on_env, tangents, mark, screw, tab_buckle, _sm

ARMS = UPPER_ARMS | FOREARMS
LEGS = THIGHS | SHINS


# ------------------------------------------------------------------------------------------ head

def balaclava(c, man, lead, E, u, bottom_z, hidden=lambda p: False):
    """A knit balaclava over the head and neck with a crisp eye slot: the skin's shell (real.shell),
    edge loops cut along the slot's outline (in the face frame, only across the front of the face),
    the faces inside it dropped (and those deep under the helmet, `hidden`). A layer like real.layer,
    so it bends with the skin."""
    def fx(p):
        return (Vector(p) - E) / u

    def keep(p):
        return lead(p) in ("head", "neck") and p.z > bottom_z - 0.02 and not hidden(p)
    bm = real._shell_bm(man, keep, [((0, 0, bottom_z), (0, 0, -1))], ease=0.0045, smooth=2)
    # The slot, notched up over the bridge of the nose so the knit covers it between the lenses.
    # Up to the glasses' bridge (E.z + 0.007 and up), the knit under the lenses' inner edges.
    slot = [(-0.034, -0.0145), (-0.02, -0.0145), (-0.012, 0.0075), (0.012, 0.0075), (0.02, -0.0145), (0.034, -0.0145), (0.05, -0.0065),
            (0.05, 0.0055), (0.038, 0.0125), (-0.038, 0.0125), (-0.05, 0.0055), (-0.05, -0.0065)]

    def front(f):
        q = fx(f.calc_center_median())
        return q.y < 0.04 and abs(q.x) < 0.095 and -0.06 < q.z < 0.06
    for i in range(len(slot)):
        (x0, z0), (x1, z1) = slot[i - 1], slot[i]
        n = Vector((z1 - z0, 0.0, -(x1 - x0))).normalized()   # the edge's normal in the face plane
        faces = [f for f in bm.faces if front(f)]
        geom = list({v for f in faces for v in f.verts}) + list({e for f in faces for e in f.edges}) + faces
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=E + Vector((x0, 0.0, z0)) * u, plane_no=n)

    def inside(f):
        q = fx(f.calc_center_median())
        return q.y < 0.04 and inside_poly(q.x, q.z, slot)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if inside(f)], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    real._drop_islands(bm)
    o = real._bm_obj("balaclava", bm, None, [g.name for g in man.low.vertex_groups])
    o.data.materials.append(real.mat("knit.secondary"))
    real.seam_attrs(o, uv_seams=False)
    o["texel"] = 1.0
    c.parts.append((o, "DONE", None))
    return o


def helmet(c, man, arm, tb):
    """A high-cut ballistic helmet in navy: the shell over the crown, its brim a finger above the
    brows, cut high over the ears and down over the nape, a rubber edge trim; side rails carrying the
    headset, an NVG shroud with its mount, a velcro panel with the company mark on the left, a unit
    tab on the right and the hazard stripe with the drone-link beacon at the back. Returns the
    envelope, its rim and the headset's ear offset."""
    hc = man.head_center()
    E, u = man.face()
    dom = kit.dominant(man.low)
    me = man.low.data
    co = [v.co.copy() for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons if sum(dom[i] == "head" for i in p.vertices) * 2 > len(p.vertices)]
    head = BVHTree.FromPolygons(co, polys)
    O = hc + Vector((0, -0.006, -0.012))
    env = Env([head], O, reach=0.24, lat=(-40.0, 90.0), dlat=4.0, dlon=5.0, spread=14.0, blur=10.0, floor=0.006)
    SO, ST = 0.019, 0.007

    def lat_of(p):
        d = (Vector(p) - env.O).normalized()
        return math.degrees(math.asin(max(-1.0, min(1.0, d.dot(env.Z)))))
    fh, _ = hit(tb, (0, -0.5, E.z + 0.034 * u), (0, 1, 0))
    BROW = lat_of(fh) if fh is not None else 22.0
    ear, _ = hit(tb, hc + Vector((0.3, 0.004, -0.006)), (-1, 0, 0))
    dxe = (ear.x - hc.x + 0.004) - 0.088 if ear else 0.0
    SIDE = max(BROW + 2.0, lat_of(hc + Vector((0.1 + dxe, 0.004, 0.05))) + 1.0)   # clear of the headset cups
    NAPE = -10.0

    def rim(lo):
        a = abs(lo)
        return BROW + (SIDE - BROW) * _sm(a, 36, 70) + (NAPE - SIDE) * _sm(a, 120, 166)

    shell = env.patch("helmet", "pmc_navy_hard", -180.0, 180.0, rim, lambda lo: 86.0, SO, ST, nu=48, nv=10, closed=True, pole=True,
                      inner="pmc_liner", bevel=0.0022)
    arm.add(remat(shell, NAVYH), "head")
    edge = [env.P(rim(lo), lo, SO - ST * 0.5) for lo in [-180.0 + 6.0 * i for i in range(60)]]
    c.rigid(tube("helmet_trim", relax(edge, 1), 0.0046, "rubber", closed=True, segs=5), "head")

    # Side rails along the high cut, three screws each.
    for sx in (1, -1):
        lo0, lo1 = sorted((sx * 56.0, sx * 134.0))
        rail = env.patch("arc_rail", "black", lo0, lo1, lambda lo: rim(lo) + 1.2, lambda lo: rim(lo) + 7.6, SO + 0.0058, 0.0075, nu=14, nv=2,
                         bevel=0.0012)
        c.rigid(rail, "head")
        for lo in (sx * 64.0, sx * 126.0):
            c.rigid(screw(env.P(rim(lo) + 4.4, lo, SO + 0.0058), env.normal(rim(lo) + 4.4, lo, SO), r=0.003), "head")

    # The NVG shroud over the brow and its mount.
    shroud = env.patch("nvg_shroud", "black", -14.0, 14.0, lambda lo: BROW + 1.5, lambda lo: BROW + 13.0, SO + 0.0042, 0.006, nu=6, nv=3,
                       bevel=0.0015)
    c.rigid(shroud, "head")
    p, n = env.P(BROW + 6.0, 0.0, SO + 0.0042), env.normal(BROW + 6.0, 0.0, SO)
    f, up = tangents(n)
    side = n.cross(up).normalized()
    c.rigid(oriented(kit.block("nvg_mount", (0, 0, 0), (0.03, 0.016, 0.026), "gunmetal", bevel=0.002), p + n * 0.008, side, n, up), "head")
    c.rigid(oriented(kit.block("nvg_lever", (0, 0, 0), (0.008, 0.008, 0.016), "black", bevel=0.001), p + n * 0.018 + side * 0.019, side, n, up), "head")
    for k in (-1, 1):
        c.rigid(screw(env.P(BROW + 10.0, k * 9.0, SO + 0.0042), env.normal(BROW + 10.0, k * 9.0, SO), r=0.0026), "head")

    # Velcro with the company mark on the left, the unit tab on the right.
    for sx in (1, -1):
        lo_c = sx * 96.0
        la0, la1 = SIDE + 11.0, SIDE + 29.0
        lo0, lo1 = sorted((lo_c - 17.0, lo_c + 17.0))
        c.rigid(env.patch("helmet_velcro", "pmc_velcro", lo0, lo1, lambda lo: la0, lambda lo: la1, SO + 0.0016, 0.0022, nu=6, nv=4, bevel=0.0),
                "head")
        la_c = (la0 + la1) / 2
        if sx > 0:
            objs = mark(0.036)
        else:
            objs = name_patch("UAS", 0.0, 0.0, 0.03, 0.017, 0.0, base="hazard", ink="black", size=0.011)
        conform(objs, on_env(env, la_c, lo_c, SO + 0.0016), step=0.008)
        rigid_all(c, objs, "head")
    # The back: hazard stripe and the drone-link beacon.
    la_b = NAPE + 20.0
    band_objs = hazard_band(-0.045, 0.045, -0.006, 0.006, 0.0)
    conform(band_objs, on_env(env, la_b + 10.0, 180.0, SO), step=0.012)
    rigid_all(c, band_objs, "head")
    p, n = env.P(la_b, 180.0, SO), env.normal(la_b, 180.0, SO)
    f, up = tangents(n)
    side = n.cross(up).normalized()
    c.rigid(oriented(kit.block("beacon", (0, 0, 0), (0.03, 0.014, 0.022), "black", bevel=0.002), p + n * 0.006, side, n, up), "head")
    c.rigid(oriented(kit.block("beacon_lens", (0, 0, 0), (0.02, 0.003, 0.01), "glow_cyan", bevel=0.0), p + n * 0.0135, side, n, up), "head")
    return env, rim, dxe, SO


# ------------------------------------------------------------------------------------------ gear

def tablet(c, b, tshirt):
    """The rugged tablet on the left forearm: a black cradle on two straps, a white case with navy
    bumpers and a lit screen (the drone's feed, a reticle, link bars and battery)."""
    J = b.j
    fa0, fa1 = J("forearm.L", 0.0), J("forearm.L", 1.0)
    A = (fa1 - fa0).normalized()
    F0 = Vector((0, -1, 0))
    F0 = (F0 - A * F0.dot(A)).normalized()
    S0 = F0.cross(A).normalized()            # the outside of the left forearm
    # On the front of the forearm, turned in: with the support hand on the grip (the carry every
    # clip is close to) the forearm rolls palm-up and this side faces up and forward, to the eye.
    ph = math.radians(-45.0)
    d = (F0 * math.cos(ph) + S0 * math.sin(ph)).normalized()
    T = A.cross(d).normalized()
    cen = fa0.lerp(fa1, 0.55)
    top = None
    for x in (-0.03, 0.0, 0.03):
        for z in (-0.045, 0.0, 0.045):
            q = cen + T * x + A * z
            # Out from inside the sleeve: a ray in from 0.3 m off caught the shirt's hip in the rest
            # pose and stood the tablet 15 cm off the arm.
            loc, _ = hit(tshirt, q, d)
            if loc is not None and (loc - q).length < 0.09:
                h = (loc - cen).dot(d)
                top = h if top is None else max(top, h)
    top = top if top is not None else 0.045
    M = frame(cen + d * (top + 0.008), d, -A)
    parts = [kit.block("tablet_cradle", (0, 0.006, 0), (0.062, 0.03, 0.098), "black", bevel=0.003),
             remat(kit.block("tablet", (0, -0.0172, 0), (0.07, 0.016, 0.104), "grey", bevel=0.004), WHITE)]
    for bx in (-1, 1):
        for bz in (-1, 1):
            parts.append(remat(kit.block("tablet_bumper", (bx * 0.0315, -0.0172, bz * 0.0475), (0.015, 0.019, 0.015), "grey", bevel=0.003), NAVYH))
    y0 = -0.0252
    parts.append(panel("tablet_screen", rrect(-0.0285, -0.041, 0.0285, 0.04, 0.003), y0, 0.0012, "glass", bevel=0.0))
    y1 = y0 - 0.0012

    def quad(x0, z0, x1, z1):
        return [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    ui = [quad(-0.026, 0.032, 0.026, 0.0365)]                                              # status bar
    ui += [quad(-0.025, 0.026, 0.025, 0.0272), quad(-0.025, -0.012, 0.025, -0.0108),        # the feed's frame
           quad(-0.025, -0.0108, -0.0238, 0.026), quad(0.0238, -0.0108, 0.025, 0.026)]
    ui += [quad(-0.009, 0.0071, 0.009, 0.0081), quad(-0.0005, -0.002, 0.0005, 0.017)]      # reticle
    ui += [quad(-0.024 + i * 0.005, -0.034, -0.021 + i * 0.005, -0.03 + i * 0.003) for i in range(4)]  # link bars
    ui += [quad(-0.025, -0.022, 0.012, -0.0195)]                                           # a readout line
    parts += [panel("tablet_ui", pts, y1, 0.0004, "glow_cyan", bevel=0.0) for pts in ui]
    parts.append(panel("tablet_ui", hexagon(0.0, 0.0076, 0.0062), y1, 0.0004, "glow_cyan", bevel=0.0))
    parts.append(panel("tablet_ui", hexagon(0.0, 0.0076, 0.0046), y1 - 0.0004, 0.0002, "glass", bevel=0.0))
    parts.append(panel("tablet_battery", quad(0.008, -0.035, 0.024, -0.03), y1, 0.0004, "glow_amber", bevel=0.0))
    parts += [kit.block("tablet_key", (0.0365, -0.0172, z), (0.004, 0.006, 0.012), "black", bevel=0.0) for z in (0.01, 0.026)]
    put(parts, M)
    rigid_all(c, parts, "forearm.L")
    # Two straps round the forearm through the cradle.
    for t in (0.36, 0.74):
        p = fa0.lerp(fa1, t)
        U = F0
        V = S0
        ring = []
        for a in range(0, 360, 20):
            dd = U * math.cos(math.radians(a)) + V * math.sin(math.radians(a))
            loc, _ = hit(tshirt, p, dd)
            ring.append(loc + dd * 0.004 if loc is not None and (loc - p).length < 0.12 else p + dd * 0.045)
        c.rigid(sweep("tablet_strap", ring, 0.022, 0.004, "webbing", radial(p, A), closed=True), "forearm.L")


def drone(MB, front_y, zc):
    """The quadcopter docked on the carrier's back, in the back panel's flat space (top toward -Y,
    away from the wearer): a white body with a navy canopy and the mark, four navy arms to motors and
    two-blade props inside white guards, a sensor ball at its nose, amber tail lights. Not bent: it
    stands off the dock on its own."""
    out = []
    yb = front_y - 0.0115      # the body's underside, on the dock
    out.append(remat(kit.block("drone_body", (0, yb - 0.025, zc), (0.078, 0.05, 0.13), "grey", bevel=0.007), WHITE))
    out.append(remat(kit.block("drone_canopy", (0, yb - 0.052, zc + 0.012), (0.054, 0.008, 0.07), "grey", bevel=0.003), NAVYH))
    out += logo(0, zc + 0.012, 0.034, yb - 0.056)
    out += [kit.cyl("drone_tail_light", (sx * 0.022, yb - 0.03, zc - 0.064), (sx * 0.022, yb - 0.03, zc - 0.069), 0.004, "glow_amber", segs=8,
                    bevel=0.0) for sx in (1, -1)]
    out.append(kit.block("drone_gimbal", (0, yb - 0.024, zc + 0.07), (0.03, 0.022, 0.012), "black", bevel=0.002))
    out.append(kit.cyl("drone_camera", (0, yb - 0.024, zc + 0.074), (0, yb - 0.024, zc + 0.094), 0.012, "black", segs=14, bevel=0.002))
    out.append(kit.cyl("drone_lens", (0, yb - 0.024, zc + 0.094), (0, yb - 0.024, zc + 0.096), 0.0075, "glass", segs=12, bevel=0.0))
    ya = yb - 0.03
    for k, (ax, az) in enumerate(((1, 1), (-1, 1), (1, -1), (-1, -1))):
        a = Vector((ax * 0.03, ya, zc + az * 0.05))
        m = Vector((ax * 0.09, ya, zc + az * 0.082))
        zd = (m - a).normalized()
        yd = Vector((0, 1, 0))
        xd = yd.cross(zd).normalized()
        out.append(remat(oriented(kit.block("drone_arm", (0, 0, 0), (0.015, 0.012, (m - a).length + 0.01), "grey", bevel=0.002), (a + m) / 2,
                                  xd, yd, zd), NAVYH))
        out.append(kit.cyl("drone_motor", (m.x, ya + 0.008, m.z), (m.x, ya - 0.018, m.z), 0.0135, "gunmetal", segs=12, bevel=0.001))
        out.append(kit.cyl("drone_bell", (m.x, ya - 0.018, m.z), (m.x, ya - 0.023, m.z), 0.0095, "black", segs=12, bevel=0.0))
        ang = math.radians((25, -40, 70, 5)[k])
        out.append(oriented(kit.block("drone_prop", (0, 0, 0), (0.086, 0.002, 0.01), "black", bevel=0.0), Vector((m.x, ya - 0.025, m.z)),
                            Vector((math.cos(ang), 0, math.sin(ang))), yd, Vector((-math.sin(ang), 0, math.cos(ang)))))
        out.append(remat(kit.ring("drone_guard", Vector((m.x, ya - 0.02, m.z)), (0, 1, 0), 0.053, 0.0485, 0.014, "grey", segs=24), WHITE))
        # Two struts from the motor out to its guard, square to the arm.
        for sgn in (1, -1):
            dd = Vector((-zd.z * sgn, 0, zd.x * sgn))
            s0 = Vector((m.x, ya - 0.012, m.z)) + dd * 0.012
            s1 = Vector((m.x, ya - 0.012, m.z)) + dd * 0.05
            out.append(remat(oriented(kit.block("drone_strut", (0, 0, 0), (0.005, 0.005, 0.038), "grey", bevel=0.0), (s0 + s1) / 2,
                                      yd.cross(dd), yd, dd), NAVYH))
    put(out, MB)
    return out


# ------------------------------------------------------------------------------------------ build

def build():
    b = real.Anatomy(height=1.79, sole=0.032)
    c = real.begin("handler", b)
    man = real.body(c, stubble=0.0)
    J, seg = b.j, kit.seg_dist
    lead = real.bones_at(man)
    E, u = man.face()
    hc = man.head_center()
    tb = tree(man.low)
    armpit = b.at("armpit")
    head_arm = Armour(c, "armour_head", texel=2.0)

    # ---------------------------------------------------------------- gloves (the Contractor's)
    gloves = real.gloves(c, man, "glove", cuff=0.042, knuckle="grey")
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
        M = Matrix((T, back, Lh)).transposed().to_4x4()
        ax = J("hand." + s, 0.0) - J("forearm." + s, 0.0)
        cc = J("hand." + s, 0.0) - ax.normalized() * 0.022
        r = _radius(tg, cc, ax)
        c.rigid(band("glove_cuff", cc, (r + 0.003, r * 0.82 + 0.003), 0.03, 0.004, "glove", axis=ax), "forearm." + s)
        tab = kit.block("cuff_tab", (0, 0, 0), (0.02, 0.004, 0.028), "hazard", bevel=0.0012)
        M.translation = cc + back * (r + 0.005)
        tab.data.transform(M)
        c.rigid(tab, "forearm." + s)

    # ---------------------------------------------------------------- combat shirt (the Contractor's)
    neck = J("neck", 0.0)
    tuck = b.hip_z + 0.095
    waist = tuck - 0.03
    neckline = (Vector((0, 0, neck.z + 0.028)), Vector((0, -0.45, 1)).normalized())
    collar_top = (neckline[0] + Vector((0, 0, 0.026)), Vector((0, -0.25, 1)).normalized())

    def on_arm(p):
        return lead(p) in ARMS

    cuts = [collar_top]
    for s in ("L", "R"):
        e, w = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        cuts.append((e.lerp(w, 0.86), w - e, lambda p, e=e, w=w: on_arm(p) and seg(p, e, w + (w - e) * 0.6) < 0.09))
    cuts.append(((0, 0, waist), (0, 0, -1), lambda p: not on_arm(p)))

    def ease(p):
        if not on_arm(p) and p.z < armpit - 0.06:
            return 0.007 - 0.003 * float(real._smooth(tuck + 0.03 - p.z, 0.0, 0.03))
        arm = min(seg(p, J("upper_arm." + s, 0.3), J("forearm." + s, 1.0)) for s in ("L", "R"))
        return 0.007 + 0.011 * max(0.0, min(1.0, (0.09 - arm) / 0.03))

    def pin(p):
        w = 0.0
        if p.z > neck.z - 0.01 and not on_arm(p):
            w = 1.0
        if p.z < tuck and not on_arm(p):
            w = 1.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.86)
            d = (wr - e).normalized()
            if on_arm(p) and seg(p, e, wr) < 0.1 and (p - wr).dot(d) > -0.025:
                w = 1.0
        return w

    def slack(p):
        w = 0.0
        for s in ("L", "R"):
            e, wr = J("forearm." + s, 0.0), J("forearm." + s, 0.86)
            d = wr - e
            L = d.length
            d.normalize()
            t = (p - e).dot(d) / L
            if on_arm(p) and seg(p, e, wr) < 0.1 and t > 0.2:
                w = max(w, min(1.0, (t - 0.2) / 0.5))
        if not on_arm(p) and tuck < p.z < tuck + 0.12:
            w = max(w, 0.6 * (1 - (p.z - tuck) / 0.12))
        return w

    def above(plane, p):
        return (Vector(p) - plane[0]).dot(plane[1]) > 0

    def cuff(p):
        for s in ("L", "R"):
            e, w = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
            d = (w - e).normalized()
            if on_arm(p) and seg(p, e, w) < 0.09 and (p - e.lerp(w, 0.80)).dot(d) > 0:
                return True
        return False
    shirt = real.garment(c, man, "shirt", "primary", lambda p: lead(p) in TORSO | ARMS | THIGHS | {"neck"} and p.z > waist - 0.05,
                         cuts, ease=ease, pin=None if FAST else pin, slack=slack, bend=12.0, texel=1.3,
                         trims=[("knit.primary", lambda p: (above(neckline, p) and lead(p) not in ARMS) or cuff(p))])
    c.hide_under(shirt.low, 0.05, 2)
    tshirt = tree(shirt.low)
    for s, sx in (("L", 1), ("R", -1)):
        fa0, fa1 = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        ax = (fa1 - fa0).normalized()
        r = _radius(tshirt, fa0 + ax * 0.01, ax) + 0.003
        pad = wrap("elbow_pad", fa0 - ax * 0.03, fa0 + ax * 0.055, r, r - 0.005, 180 - 55 * sx, 180 + 55 * sx, 0.009, "black",
                   nt=4, nphi=8, bevel=0.003, bulge=0.004, fit=(tshirt, 0.0025))
        c.rigid(pad, "forearm." + s)

    # Sleeve pockets with patches: ARGENT-7 left, the company mark right.
    for s, sx in (("L", 1), ("R", -1)):
        ua0, ua1 = J("upper_arm." + s, 0.0), J("upper_arm." + s, 1.0)
        around = _limb(ua0, ua1, front=(0, -1, 0))
        out = 90 * sx - 15 * sx
        real.patch(c, shirt.low, "sleeve_pocket", "primary",
                   lambda p, around=around, out=out: (lambda t, a: 0.24 < t < 0.56 and abs((a - out + 180) % 360 - 180) < 36)(*around(p)),
                   lift=0.0015, puff=0.006, thick=0.002)
        ax = (ua0 - ua1).normalized()
        n = Vector((sx, 0, 0))
        n = (n - ax * n.dot(ax)).normalized()
        n = (n + Vector((0, -0.25, 0))).normalized()
        n = (n - ax * n.dot(ax)).normalized()
        centre = ua0.lerp(ua1, 0.38)
        loc, _ = hit(tshirt, centre + n * 0.3, -n)
        R = (loc - centre).length
        M = frame(loc + n * 0.0075, n, ax)
        objs = [panel("pocket_flap", rrect(-0.042, 0.035, 0.042, 0.058, 0.006), 0.0, 0.004, "primary", bevel=0.0015),
                panel("velcro", rrect(-0.033, -0.042, 0.033, 0.028, 0.006), 0.0, 0.002, "pmc_velcro", bevel=0.0006)]
        if s == "L":
            objs += name_patch("ARGENT-7", 0, -0.002, 0.058, 0.026, -0.002, base="white", ink="black", size=0.0125)
            objs += [panel("stripe", rrect(-0.027, -0.03, 0.027, -0.022, 0.002), -0.002, 0.002, "hazard", bevel=0.0004)]
        else:
            objs += logo(0, 0.0, 0.05, -0.002)
            objs += [panel("stripe", rrect(-0.027, -0.037, 0.027, -0.03, 0.002), -0.002, 0.002, "hazard", bevel=0.0004)]
        put(objs, M, R, step=0.012)
        rigid_all(c, objs, "upper_arm." + s)

    # ---------------------------------------------------------------- wrist tablet
    tablet(c, b, tshirt)

    # ---------------------------------------------------------------- plate carrier
    dz = (armpit - 0.198) - 1.03

    def Z(z):
        return z + dz
    R = 0.30
    th = 0.032
    f_out = kit.rounded([(-0.125, Z(1.03)), (0.125, Z(1.03)), (0.125, Z(1.29)), (0.072, Z(1.372)), (-0.072, Z(1.372)), (-0.125, Z(1.29))], 0.02)
    MF = fit(tshirt, f_out, R, 0.014, side=-1, tilt=5)
    front = [panel("carrier_front", f_out, 0.0, th, "pmc_navy", bevel=0.007)]
    kit.cut(front[0], *[kit.block("slot", (x, -th, Z(z)), (0.036, 0.007, 0.0075), "steel", bevel=0)
                        for z in (1.168, 1.196, 1.224) for x in (-0.075, -0.025, 0.025, 0.075)])
    y1 = -th
    front += [panel("velcro", rrect(-0.08, Z(1.252), 0.08, Z(1.343), 0.008), y1, 0.003, "pmc_velcro", bevel=0.001)]
    front += name_patch("HALCYON", 0, Z(1.322), 0.128, 0.03, y1 - 0.003, base="white", ink="pmc_navy", size=0.021)
    front += logo(-0.048, Z(1.279), 0.036, y1 - 0.003)
    front += name_patch("UAS", 0.012, Z(1.279), 0.034, 0.024, y1 - 0.003, base="hazard", ink="black", size=0.0125)
    front += name_patch("O NEG", 0.058, Z(1.279), 0.04, 0.024, y1 - 0.003, base="black", ink="white", size=0.0092)
    # Three SMG magazine pouches, shorter than the Contractor's rifle pouches.
    for x in (-0.08, 0.0, 0.08):
        front += [kit.block("mag_pouch", (x, y1 - 0.018, Z(1.08)), (0.06, 0.036, 0.11), "pmc_navy", bevel=0.006),
                  kit.block("pouch_flap", (x, y1 - 0.02, Z(1.128)), (0.064, 0.042, 0.026), "pmc_navy", bevel=0.005),
                  kit.block("bungee", (x, y1 - 0.037, Z(1.072)), (0.062, 0.004, 0.011), "black", bevel=0.0015),
                  kit.block("pull_tab", (x, y1 - 0.043, Z(1.12)), (0.024, 0.005, 0.03), "hazard", bevel=0.0015)]
    put(front, MF, R)
    rigid_all(c, front, "chest")

    b_out = kit.rounded([(-0.128, Z(1.03)), (0.128, Z(1.03)), (0.128, Z(1.29)), (0.1, Z(1.36)), (-0.1, Z(1.36)), (-0.128, Z(1.29))], 0.025)
    MB = fit(tshirt, b_out, R, 0.014, side=1, tilt=6)
    back = [panel("carrier_back", b_out, 0.0, th, "pmc_navy", bevel=0.007)]
    front_y = -th
    back += name_patch("VANTA LOGISTICS", 0, Z(1.302), 0.17, 0.028, front_y, base="white", ink="black", size=0.0136)
    back += [panel("stripe", rrect(-0.085, Z(1.279), 0.085, Z(1.285), 0.002), front_y, 0.002, "hazard", bevel=0.0004)]
    handle = sweep("drag_handle", smooth_path([(-0.04, front_y + 0.004, Z(1.335)), (-0.032, front_y - 0.018, Z(1.37)), (0.032, front_y - 0.018, Z(1.37)),
                                               (0.04, front_y + 0.004, Z(1.335))], 4), 0.026, 0.005, "webbing", radial((0, front_y + 0.01, Z(1.33)), (1, 0, 0)))
    back += [handle]
    # The drone dock: a navy hard plate with a hazard strip, two yellow latches gripping the drone.
    zc = Z(1.152)
    back += [remat(panel("uas_dock", rrect(-0.052, Z(1.06), 0.052, Z(1.245), 0.012), front_y, 0.012, "grey", bevel=0.003), NAVYH)]
    back += hazard_band(-0.044, 0.044, Z(1.07), Z(1.082), front_y - 0.012)
    back += [kit.block("dock_latch", (sx * 0.0445, front_y - 0.026, zc + dzl), (0.012, 0.028, 0.026), "accent", bevel=0.002)
             for sx in (1, -1) for dzl in (-0.03, 0.03)]
    # The radio high on the left, its link whip up past the shoulder.
    rx = -0.104
    radio = kit.block("radio", (rx, front_y - 0.016, Z(1.27)), (0.03, 0.032, 0.085), "black", bevel=0.004)
    kit.cut(radio, *[kit.block("grip", (rx, front_y - 0.032, Z(1.236 + i * 0.011)), (0.034, 0.005, 0.004), "steel", bevel=0) for i in range(3)])
    back += [radio,
             kit.block("radio_strap", (rx, front_y - 0.033, Z(1.295)), (0.034, 0.004, 0.016), "pmc_navy", bevel=0.001),
             kit.cyl("antenna_base", (rx - 0.007, front_y - 0.016, Z(1.3125)), (rx - 0.007, front_y - 0.016, Z(1.335)), 0.0065, "black", segs=12,
                     bevel=0.001),
             kit.cyl("antenna", (rx - 0.007, front_y - 0.016, Z(1.333)), (rx - 0.034, front_y - 0.04, Z(1.62)), 0.0034, "rubber", r1=0.0022, segs=8,
                     bevel=0)]
    back += name_patch("CH 7", rx, Z(1.274), 0.026, 0.012, front_y - 0.032, base="hazard", ink="black", size=0.0078)
    put(back, MB, R)
    rigid_all(c, back, "chest")
    rigid_all(c, drone(MB, front_y, zc), "chest")

    # Padded shoulder straps (accent) with buckles, the PTT on the left one cabled to the radio.
    for s, sx in (("L", 1), ("R", -1)):
        xs = sx * 0.085
        pts = []
        for y in (-0.13, -0.10, -0.07, -0.04, -0.01, 0.02, 0.05, 0.08, 0.11, 0.13):
            loc, _ = hit(tshirt, (xs, y, 1.9), (0, 0, -1))
            z = loc.z + 0.008 if loc and loc.z > armpit + 0.05 else None
            pts.append((xs, y, z))
        pts = [(xs, y, z if z is not None else Z(1.36)) for xs, y, z in pts]
        pts[0] = to_world((sx * 0.07, -0.012, Z(1.352)), MF, R)
        pts[-1] = to_world((-sx * 0.075, -0.012, Z(1.34)), MB, R)
        path = smooth_path(pts, 3)
        nrm = radial((sx * 0.085, 0, Z(1.33)), (1, 0, 0))
        c.rigid(sweep("shoulder_strap", path, 0.05, 0.013, "accent", nrm), "chest")
        k = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.072))
        tan = (path[k + 1] - path[k - 1]).normalized()
        nn = nrm(path[k]).normalized()
        c.rigid(side_buckle("strap_buckle", path[k] + nn * 0.009, -tan, nn, w=0.04), "chest")
        if s == "L":
            k2 = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.035))
            t2 = (path[k2 + 1] - path[k2 - 1]).normalized()
            n2 = nrm(path[k2]).normalized()
            Mp = frame(path[k2] + n2 * 0.0065, n2, t2)
            ptt = [kit.block("ptt", (0, -0.009, 0), (0.034, 0.018, 0.042), "black", bevel=0.003),
                   kit.cyl("ptt_button", (0, -0.017, 0.004), (0, -0.023, 0.004), 0.009, "hazard", segs=14, bevel=0.0015)]
            put(ptt, Mp)
            rigid_all(c, ptt, "chest")
            ptt_top = Mp @ Vector((0, -0.01, 0.022))
            radio_top = to_world((rx + 0.008, -th - 0.016, Z(1.3125)), MB, R)
            over = [path[i] + nrm(path[i]).normalized() * 0.014 + Vector((0.026, 0, 0)) for i in range(k2 + 3, len(path) - 4, 3)]
            c.rigid(kit.rope("ptt_cable", [ptt_top] + over + [radio_top + Vector((0.0, 0.01, 0.018)), radio_top], 0.0035, "black"), "chest")

    # Cummerbund.
    for s, sx in (("L", 1), ("R", -1)):
        for z, w in ((Z(1.07), 0.055), (Z(1.135), 0.055)):
            pts = _ring_side(tshirt, (0, -0.004), z, 0.012, sx * 46, sx * 136)
            c.rigid(sweep("cummerbund", smooth_path(pts, 3), w, 0.012, "pmc_navy", radial((0, -0.004, 0))), "chest")
        side = _ring_side(tshirt, (0, -0.004), Z(1.1), 0.026, sx * 90, sx * 90, n=2)[0]
        c.rigid(kit.block("cb_tab", side, (0.012, 0.03, 0.11), "black", bevel=0.003), "chest")

    # ---------------------------------------------------------------- head: balaclava, helmet, headset, glasses
    env, rim, dxe, SO = helmet(c, man, head_arm, tb)

    def under_shell(p):
        d = Vector(p) - env.O
        la = math.degrees(math.asin(max(-1.0, min(1.0, d.normalized().dot(env.Z)))))
        lo = math.degrees(math.atan2(d.dot(env.S), d.dot(env.F)))
        return la > rim(lo) + 14.0
    bala = balaclava(c, man, lead, E, u, neck.z + 0.012, hidden=under_shell)
    c.hide_under(bala, 0.015, 1)
    tbal = tree(bala)

    # Over-ear headset cups (the Contractor's), hung from the helmet rails on short arms; boom mic.
    for s, sx in (("L", 1), ("R", -1)):
        h2 = hc + Vector((sx * dxe, 0, 0))
        cc = h2 + Vector((sx * 0.108, 0.004, -0.006))
        X = Vector((sx, 0, 0))
        c.rigid(kit.ring("cushion", h2 + Vector((sx * 0.096, 0.004, -0.006)), X, 0.041, 0.022, 0.012, "rubber", segs=20), "head")
        c.rigid(kit.cyl("cup", cc - X * 0.006, cc + X * 0.016, 0.043, "black", segs=24, bevel=0.004), "head")
        c.rigid(kit.cyl("cup_cover", cc + X * 0.016, cc + X * 0.021, 0.034, "grey", segs=24, bevel=0.0015), "head")
        Mc = frame(cc + X * 0.021, X, (0, 0, 1))
        objs = logo(0, 0.006, 0.032, 0.0) + screws([(-0.024, -0.016), (0.024, -0.016)], 0.0, r=0.003)
        put(objs, Mc)
        rigid_all(c, objs, "head")
        c.rigid(kit.cyl("knob", cc + Vector((sx * 0.004, 0.026, -0.03)), cc + Vector((sx * 0.004, 0.034, -0.036)), 0.007, "grey", segs=12, bevel=0.001), "head")
        # The rail arm: from a clamp on the rail down to the top of the cup.
        lo_c = sx * 95.0
        pr = env.P(rim(lo_c) + 4.4, lo_c, SO + 0.0058)
        nr = env.normal(rim(lo_c) + 4.4, lo_c, SO)
        f_, up_ = tangents(nr)
        c.rigid(oriented(kit.block("rail_clamp", (0, 0, 0), (0.024, 0.012, 0.016), "black", bevel=0.0015), pr + nr * 0.004, f_, nr, up_), "head")
        a0 = cc + X * 0.006 + Vector((0, 0, 0.036))
        a1 = pr + nr * 0.006
        zd = (a1 - a0).normalized()
        xd = Vector((0, 1, 0)).cross(zd).normalized()
        c.rigid(oriented(kit.block("cup_arm", (0, 0, 0), (0.006, 0.014, (a1 - a0).length + 0.006), "grey", bevel=0.0015), (a0 + a1) / 2,
                         xd, zd.cross(xd), zd), "head")
    h2 = hc + Vector((dxe, 0, 0))
    mic_pts = [h2 + Vector(p) for p in ((0.116, -0.046, -0.026), (0.11, -0.07, -0.042), (0.09, -0.098, -0.058), (0.054, -0.12 - dxe, -0.066))]
    c.rigid(kit.cyl("mic_pivot", h2 + Vector((0.106, -0.04, -0.024)), h2 + Vector((0.124, -0.04, -0.024)), 0.01, "grey", segs=14, bevel=0.002), "head")
    c.rigid(kit.rope("boom", mic_pts, 0.003, "black"), "head")
    c.rigid(kit.cyl("mic", mic_pts[-1] + Vector((0.004, 0.001, 0)), mic_pts[-1] + Vector((-0.022, -0.003, -0.002)), 0.0068, "black", segs=14, bevel=0.002),
            "head")

    # The chin strap: from under the rim in front of each cup, under the jaw over the balaclava.
    la_t = rim(66.0) - 2.0
    Lt, Rt = env.P(la_t, 66.0, SO - 0.009), env.P(la_t, -66.0, SO - 0.009)
    Mt = (Lt + Rt) / 2
    chin, _ = hit(tbal, Vector((0, E.y - 0.03, E.z - 0.12 * u)) + Vector((0, 0, -0.3)), (0, 0, 1))
    chin = chin if chin is not None else Vector((0, E.y, E.z - 0.11))
    Wd = chin - Mt
    Wd.x = 0.0
    Wd.normalize()
    Xd = Vector((1, 0, 0))
    strap = []
    for i in range(23):
        phi = math.radians(-88.0 + 176.0 * i / 22)
        dd = Wd * math.cos(phi) + Xd * math.sin(phi)
        loc, _ = hit(tbal, Mt + dd * 0.3, -dd)
        if loc is not None:
            strap.append(loc + dd * 0.0035)
    if len(strap) > 4:
        strap = [Rt] + strap + [Lt]   # the rays sweep from the right side (-X) to the left
        strap = relax(strap, 2, closed=False)
        c.rigid(sweep("chin_strap", strap, 0.016, 0.003, "webbing", radial(Mt, Xd), bevel=0.0), "head")
        k = len(strap) * 2 // 3
        tan = (strap[k + 1] - strap[k - 1]).normalized()
        c.rigid(tab_buckle(strap[k], tan, radial(Mt, Xd)(strap[k]).normalized(), w=0.022), "head")

    # Wraparound AR glasses over the eye slot (the Contractor's sunglasses), the display pod on the left.
    nose, _ = hit(tb, Vector((0, -0.5, E.z + 0.004)), (0, 1, 0))
    gy = (nose.y if nose else E.y - 0.02) - 0.005
    gz = E.z + 0.001
    gl = []
    for sx in (1, -1):
        lens = [(sx * x, z) for x, z in ((0.013, 0.014), (0.036, 0.018), (0.062, 0.015), (0.066, 0.002), (0.057, -0.012), (0.034, -0.018), (0.017, -0.010))]
        if sx < 0:
            lens = lens[::-1]
        lens = [(p.x, p.y) for p in smooth_path([Vector((x, z, 0)) for x, z in lens], 3, closed=True)]
        gl.append(panel("lens", [(x, gz + z) for x, z in lens], 0.0, 0.003, "glass", bevel=0.0008))
        bar = [(sx * x, z) for x, z in ((0.011, 0.012), (0.036, 0.0215), (0.066, 0.018), (0.068, 0.010), (0.036, 0.0145), (0.011, 0.007))]
        if sx < 0:
            bar = bar[::-1]
        gl.append(panel("frame", [(x, gz + z) for x, z in bar], 0.0012, 0.0055, "black", bevel=0.0008))
    gl.append(panel("bridge", rrect(-0.013, gz + 0.006, 0.013, gz + 0.012, 0.002), 0.0012, 0.005, "black", bevel=0.0006))
    Mg = frame((0, gy, 0), (0, -1, 0))
    put(gl, Mg, 0.105, step=0.008)
    rigid_all(c, gl, "head")
    for sx in (1, -1):
        e0 = to_world((sx * 0.066, 0.0, gz + 0.014), Mg, 0.105)
        tp = [e0, Vector((sx * (0.074 + dxe), E.y + 0.04, gz + 0.013)), Vector((sx * (0.08 + dxe), E.y + 0.072, gz + 0.006))]
        c.rigid(sweep("temple", smooth_path(tp, 3), 0.007, 0.0028, "black", lambda p, sx=sx: Vector((sx, 0, 0))), "head")
        if sx > 0:
            q = e0.lerp(tp[1], 0.4)
            ty = (tp[1] - e0).normalized()
            c.rigid(oriented(kit.block("ar_pod", (0, 0, 0), (0.007, 0.03, 0.011), "black", bevel=0.0015), q + Vector((0.0045, 0, -0.002)),
                             Vector((1, 0, 0)), ty, Vector((1, 0, 0)).cross(ty).normalized()), "head")
            c.rigid(kit.cyl("ar_emitter", q + Vector((0.0045, 0, -0.002)) - ty * 0.0152, q + Vector((0.0045, 0, -0.002)) - ty * 0.0172, 0.003,
                            "glow_cyan", segs=8, bevel=0.0), "head")

    # ---------------------------------------------------------------- legs (the Contractor's)
    top_z = tuck
    belt_z = b.hip_z + 0.07
    hem = b.sole + 0.19 - 0.03

    def t_ease(p):
        bnd = 0.003 * (1 - real._smooth(top_z - p.z, 0.02, 0.07))
        return 0.011 + bnd + 0.004 * real._smooth(top_z - p.z, 0.04, 0.2) + 0.007 * real._smooth(J("lower_leg.L", 0.0).z - p.z, 0.0, 0.15)

    def t_pin(p):
        return 1.0 if p.z > top_z - 0.045 or p.z < hem + 0.018 else 0.0

    def t_slack(p):
        return real._smooth(hem + 0.13 - p.z, 0.0, 0.1)

    trousers = real.garment(c, man, "trousers", "secondary", lambda p: lead(p) in LEGS | {"hips", "spine"} and hem - 0.03 < p.z < top_z + 0.03,
                            [((0, 0, top_z), (0, 0, 1)), ((0, 0, hem), (0, 0, -1), lambda p: lead(p) in LEGS)],
                            ease=t_ease, pin=None if FAST else t_pin, slack=t_slack, bend=14.0, texel=1.0)
    c.hide_under(trousers.low, 0.06, 2)
    tt = tree(trousers.low)
    belt = sweep("belt", ring_pts(tt, (0, -0.005), belt_z, 0.004, n=32), 0.044, 0.009, "webbing", radial((0, -0.005, 0)), closed=True)
    c.add(belt, ["hips", "spine", "upper_leg.L", "upper_leg.R"])
    bk = [kit.block("buckle", (0, 0, 0), (0.062, 0.012, 0.038), "gunmetal", bevel=0.003)]
    kit.cut(bk[0], kit.block("buckle_slot", (0, -0.006, 0), (0.044, 0.006, 0.02), "steel", bevel=0))
    bk.append(kit.block("buckle_bar", (0, -0.002, 0), (0.05, 0.006, 0.006), "bright", bevel=0.0015))
    loc, _ = hit(tt, (0, -0.5, belt_z), (0, 1, 0))
    for o in bk:
        o.data.transform(Matrix.Translation(Vector((0, loc.y - 0.015, belt_z))))
        c.rigid(o, "hips")
    # A spare drone battery in a pouch on the belt, left front.
    bp = _ring_side(tt, (0, -0.005), belt_z, 0.0105, 52, 52, n=2)[0]
    bp2 = _ring_side(tt, (0, -0.005), belt_z - 0.065, 0.004, 52, 52, n=2)[0]
    upb = (bp - bp2).normalized()
    nb = Vector((bp.x, bp.y + 0.005, 0)).normalized()
    nb = (nb - upb * nb.dot(upb)).normalized()
    Mbp = frame(bp, nb, upb)
    pouch = [kit.block("battery_pouch", (0, -0.017, -0.03), (0.05, 0.034, 0.08), "pmc_navy", bevel=0.005),
             kit.block("battery_flap", (0, -0.019, 0.006), (0.054, 0.038, 0.016), "pmc_navy", bevel=0.004),
             kit.block("battery", (0, -0.017, 0.02), (0.042, 0.026, 0.016), "black", bevel=0.002),
             kit.block("pull_tab", (0, -0.038, -0.002), (0.02, 0.004, 0.024), "hazard", bevel=0.0012)]
    put(pouch, Mbp)
    rigid_all(c, pouch, "hips")
    for s, sx in (("L", 1), ("R", -1)):
        ul0, ul1 = J("upper_leg." + s, 0.0), J("upper_leg." + s, 1.0)
        around = _limb(ul0, ul1)
        out = 90 * sx
        if s == "L":
            real.patch(c, trousers.low, "cargo", "secondary",
                       lambda p: (lambda t, a: 0.36 < t < 0.70 and abs(a - out) < 36)(*around(p)), lift=0.002, puff=0.014, thick=0.003)
            real.patch(c, trousers.low, "cargo_flap", "secondary",
                       lambda p: (lambda t, a: 0.33 < t < 0.42 and abs(a - out) < 39)(*around(p)), lift=0.017, puff=0.002, thick=0.003)
            sn = ul0.lerp(ul1, 0.4)
            loc, nor = hit(tt, sn + Vector((0.3, 0, 0)), (-1, 0, 0))
            snap = loc + Vector((0.019, 0, 0))
            c.rigid(kit.cyl("snap", snap, snap + Vector((0.004, 0, 0)), 0.006, "gunmetal", segs=12, bevel=0.001), "upper_leg." + s)
        else:
            for t in (0.36, 0.62):
                p = ul0.lerp(ul1, t)
                r = _radius(tt, p, ul1 - ul0) + 0.004
                ring = []
                for a in range(0, 360, 20):
                    d = Vector((math.sin(math.radians(a)), -math.cos(math.radians(a)), 0))
                    loc, _ = hit(tt, p, d)
                    ring.append(loc + d * 0.005 if loc is not None and (loc - p).length < 0.2 else p + d * r)
                c.rigid(sweep("leg_strap", ring, 0.03, 0.006, "webbing", radial(p), closed=True), "upper_leg." + s)
                c.rigid(tab_buckle(p + Vector((-0.04, -r, 0)), (1, 0, 0), (0, -1, 0), w=0.026), "upper_leg." + s)
            r = _radius(tt, ul0.lerp(ul1, 0.5), ul1 - ul0)
            c.rigid(wrap("platform", ul0.lerp(ul1, 0.30), ul0.lerp(ul1, 0.68), r + 0.012, r + 0.009, out - 30, out + 30, 0.008, "pmc_navy",
                         nt=4, nphi=8, bevel=0.003, fit=(tt, 0.0105)), "upper_leg." + s)
            hol = kit.prism("holster", [(-0.05, 0.11), (0.06, 0.11), (0.07, -0.02), (0.05, -0.12), (-0.02, -0.12), (-0.05, 0.02)], 0.045, "black", bevel=0.006)
            kit.cut(hol, kit.block("hol_groove", (0.03, 0.0, -0.02), (0.006, 0.12, 0.004), "steel", bevel=0))
            grip = kit.block("pistol_grip", (0.0, -0.035, 0.155), (0.026, 0.035, 0.08), "black", bevel=0.004, rot=-12)
            hood = kit.block("hood", (0.0, 0.0, 0.12), (0.05, 0.11, 0.02), "pmc_navy", bevel=0.004)
            hol = kit.join([hol, grip, hood], "holster")
            th0 = ul0.lerp(ul1, 0.42)
            hol.data.transform(Matrix.Translation(th0 + Vector((-(r + 0.045), 0.0, -0.05))))
            c.rigid(hol, "upper_leg." + s)
        # Knee pads with the grey hexagon cap.
        knee = J("lower_leg." + s, 0.04)
        pad_cut = kit.slab("pad_cut", kit.rounded([(knee.x - 0.058, knee.z - 0.08), (knee.x + 0.058, knee.z - 0.08), (knee.x + 0.058, knee.z + 0.07),
                                                   (knee.x - 0.058, knee.z + 0.07)], 0.03), -0.4, knee.y - 0.01)
        pad = kit.plate(trousers.low, pad_cut, "kneepad", "black", offset=0.004, thick=0.016, bevel=0.006)
        c.rigid(pad, "lower_leg." + s)
        tp_ = tree(pad)
        loc, _ = hit(tp_, knee + Vector((0, -0.4, -0.005)), (0, 1, 0))
        Mk = frame(loc + Vector((0, 0.001, 0)), (0, -1, 0.1))
        cap_objs = [panel("knee_cap", hexagon(0, 0, 0.034, rot=90), 0.0, 0.006, "grey", bevel=0.002)]
        cap_objs += screws([(0.0, 0.022), (0.0, -0.022)], -0.006, r=0.0035)
        put(cap_objs, Mk, 0.06, step=0.01)
        rigid_all(c, cap_objs, "lower_leg." + s)
        kz = knee + Vector((0, 0.0, -0.055))
        r = _radius(tt, kz, (0, 0, 1)) + 0.004
        c.add(band("pad_strap", kz, (r, r), 0.02, 0.006, "webbing", axis=(0, 0, 1)), ["lower_leg." + s])

    real.boots(c, man, "boot", sole_kind="rubber", trim="rubber", top=0.19, lace="webbing", tab="hazard")
    head_arm.finish()
    economise(c)
    return c


SPEC = {"build": build, "faction": "pmc", "budget": (25000, 120000), "loadout": "smg",
        "colors": {"primary": "#b9bec6", "secondary": "#33383f", "accent": "#c9a227"}}
