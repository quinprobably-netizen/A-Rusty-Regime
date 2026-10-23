"""Runner, Deserters: the player's default, a jump-kit pilot who walked out on the Regime. A sealed pilot
helmet with a clay shell, a wide dark visor and a slate jaw guard, panel seams, a twin optic on the right
and a comms pod with a whip antenna on the left; a slim clay plate carrier with laser-cut MOLLE rows,
three rifle mag pouches, a radio pouch on the left side, kraft padded shoulder straps with a PTT, and a
cummerbund; the jump kit on the back plate (housing, clay cover, twin thrusters, fuel cells); a slate
combat suit (ripstop shirt with knit collar and cuffs, twill trousers with cargo pockets) under hard clay
shoulder caps, a clay forearm guard on the right arm, the grapple launcher on the left forearm and
clay knee caps over black pads; gloves, a kraft belt and tactical boots.

Built on the realistic layer (real.py) like the Contractor: a real body with the head under the helmet
and a knit hood, gloved fists, shirt and trousers draped by the cloth simulation, procedural surfaces
baked into one atlas. The helmet is laid on an envelope of the head (rays out to the skull, max-filtered
and blurred so the shell bridges the nose, ears and jaw).

Tints: primary = suit, hood, mag and radio pouches, jaw guard (slate); secondary = carrier, helmet shell
and the hard plates (clay); accent = shoulder straps, belt, webbing and pull tabs (kraft).
"""

import math

import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import kit
import real
import surfaces
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS
from chars.contractor import (tree, hit, frame, put, to_world, fit, panel, rrect, sweep, radial, smooth_path, wrap, _grid_obj,
                              _limb, _radius, _ring_side, side_buckle, economise, band, rigid_all, screws, ring_pts)

ARMS = UPPER_ARMS | FOREARMS


def pilot_shell(g, pal):
    """The pilot's hard shells (helmet, shoulder caps, guards, covers): a satin two-part paint over
    composite. Slow mottling and a faint peel in the coat, sparse long scuffs through it; nothing finer
    than a few texels, so the coat reads clean at game resolution (the default moulded-plastic
    stipple breaks into speckle on big curved shells). Edge chips and cavity dirt come from the shared
    wear."""
    base, worn = pal[0], pal[1]
    pos = g.geo("Position")
    x, y, z = g.xyz(pos)
    peel = g.noise(pos, 110.0, detail=2, rough=0.45)
    mottle = g.noise(pos, 8.0, detail=3)
    shade = g.remap(mottle, 0.3, 0.7, 0.955, 1.035, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    a = g.noise(g.combine(x, y, g.mul(z, 0.08)), 48.0, detail=2)
    b = g.noise(g.combine(g.mul(x, 0.08), g.add(y, 2.3), g.add(z, 0.9)), 48.0, detail=2)
    lines = g.math("MAXIMUM", g.remap(g.math("ABSOLUTE", g.sub(a, 0.5)), 0.01, 0.0), g.remap(g.math("ABSOLUTE", g.sub(b, 0.5)), 0.01, 0.0))
    scuff = g.mul(lines, g.remap(g.noise(pos, 4.0, detail=2), 0.52, 0.66))
    col = g.mix(g.mul(scuff, 0.4), col, worn)
    rough = g.lerp(peel, pal[3] - 0.06, pal[3] + 0.02)
    rough = g.lerp(scuff, rough, 0.7)
    h = g.sub(g.add(g.mul(peel, 0.4), 0.3), g.mul(scuff, 0.4))
    return dict(color=col, rough=rough, metal=0.0, height=h, bump=0.00005)


surfaces.RECIPES.setdefault("pilotshell", pilot_shell)
SHELL2, SHELL1 = "pilotshell.secondary", "pilotshell.primary"   # clay shells, the slate jaw guard
LEGS = THIGHS | SHINS


# ------------------------------------------------------------------------------------ helpers

def hard(o, kind):
    """Give a part a realistic-layer material ("cordura.secondary": a woven nylon tinted as secondary),
    every face on it (booleans leave their cutters' materials on the cut faces)."""
    o.data.materials.clear()
    o.data.materials.append(real.mat(kind))
    for p in o.data.polygons:
        p.material_index = 0
    return o


def mat_of(o, kind):
    return hard(o, kind) if "." in kind else o


def _sm(x, a, b):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def tube(name, pts, r, material, closed=False, segs=8):
    """A round tube along points (gaskets, seams, cables): rings carried along by parallel transport
    so it never twists, capped when open."""
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


def hug_ring(trees, ctr, axis, off, n=20, rmax=0.2):
    """A closed loop round `axis` through `ctr`, `off` outside the outermost surface of `trees` met
    by rays from the axis (a strap over a sleeve and the guard on it)."""
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


def oriented(o, at, x, y, z):
    """Move a part built round the origin so its local axes become x, y, z at `at`."""
    M = Matrix((Vector(x), Vector(y), Vector(z))).transposed().to_4x4()
    M.translation = Vector(at)
    o.data.transform(M)
    return o


def basis(n, fwd=(0, -1, 0)):
    """A right-handed frame on a surface with normal n: (t, n, t x n), t the tangent nearest `fwd`."""
    n = Vector(n).normalized()
    t = Vector(fwd)
    t = (t - n * t.dot(n))
    t = t.normalized() if t.length > 1e-6 else n.orthogonal().normalized()
    return t, n, t.cross(n)


class HeadEnv:
    """The head's outer envelope seen from a centre O: r(lat, lon), the distance out to the outermost
    surface of the head and neck along each direction, max-filtered over `spread` degrees and blurred
    over `blur` so a shell laid on it bridges the nose, the ears and the jaw like a moulded helmet, and
    never nearer than `floor` to the skin. Latitude from the equator (90 = up), longitude from the
    front (0, toward -Y) to the left (+90, toward +X)."""

    def __init__(self, tr, O, reach=0.24, lat=(-84.0, 90.0), dlat=4.0, dlon=5.0, spread=14.0, blur=10.0, floor=0.006):
        self.O = Vector(O)
        self.lats = np.arange(lat[0], lat[1] + 1e-6, dlat)
        self.lons = np.arange(-180.0, 180.0 - 1e-6, dlon)
        self.dlat, self.dlon = dlat, dlon
        D = np.array([tuple(self.dir(la, lo)) for la in self.lats for lo in self.lons], dtype=np.float32)
        r = np.full(len(D), np.nan, dtype=np.float32)
        for i, d in enumerate(D):
            v = Vector(tuple(float(x) for x in d))
            loc, _, _, _ = tr.ray_cast(self.O + v * reach, -v, reach)
            if loc is not None:
                r[i] = (loc - self.O).length
        ok = ~np.isnan(r)
        dots = D @ D[ok].T
        mx = np.where(dots > math.cos(math.radians(spread)), r[ok][None, :], -np.inf).max(1)
        del dots
        fin = np.isfinite(mx)
        ang = np.degrees(np.arccos(np.clip(D @ D[fin].T, -1, 1)))
        w = np.exp(-(ang / blur) ** 2)
        del ang
        env = (w @ mx[fin]) / np.maximum(w.sum(1), 1e-9)
        env = np.where(ok, np.maximum(env, np.nan_to_num(r) + floor), env)
        self.R = env.reshape(len(self.lats), len(self.lons)).astype(float)

    @staticmethod
    def dir(la, lo):
        la, lo = math.radians(la), math.radians(lo)
        return Vector((math.sin(lo) * math.cos(la), -math.cos(lo) * math.cos(la), math.sin(la)))

    def r(self, la, lo):
        fi = min(max((la - self.lats[0]) / self.dlat, 0.0), len(self.lats) - 1.0001)
        i0 = int(fi)
        fj = ((lo + 180.0) % 360.0) / self.dlon
        j0 = int(fj) % len(self.lons)
        j1 = (j0 + 1) % len(self.lons)
        a, b = fi - i0, fj - int(fj)
        R = self.R
        return (R[i0, j0] * (1 - b) + R[i0, j1] * b) * (1 - a) + (R[i0 + 1, j0] * (1 - b) + R[i0 + 1, j1] * b) * a

    def P(self, la, lo, off=0.0):
        return self.O + self.dir(la, lo) * (self.r(la, lo) + off)

    def normal(self, la, lo, off=0.0, h=1.0):
        """The outward normal of the offset envelope at (la, lo)."""
        a = self.P(la + h, lo, off) - self.P(la - h, lo, off)
        b = self.P(la, lo + h, off) - self.P(la, lo - h, off)
        n = b.cross(a).normalized()
        return n if n.dot(self.dir(la, lo)) > 0 else -n

    def latlon(self, p):
        d = (Vector(p) - self.O).normalized()
        return math.degrees(math.asin(max(-1.0, min(1.0, d.z)))), math.degrees(math.atan2(d.x, -d.y))

    def patch(self, name, material, lons, lat_lo, lat_hi, off, thick, nv, closed=False, pole=False, bevel=0.002):
        """A plate on the envelope: columns at the longitudes `lons`, each from lat_lo(lon) to
        lat_hi(lon), its inner surface `off(lat, lon)` (or a number) over the envelope, thickened
        outward by `thick`; `pole` fans the last row into the top."""
        def o(la, lo):
            return off(la, lo) if callable(off) else off
        rows = []
        for i in range(nv + 1):
            v = i / nv
            row = []
            for lo in lons:
                a, b = lat_lo(lo), lat_hi(lo)
                la = a + (b - a) * v
                row.append(self.P(la, lo, o(la, lo)))
            rows.append(row)
        g = _grid_obj(name, rows, closed, "grey", thick, bevel, self.O, pole=self.P(90.0, 0.0, o(90.0, 0.0)) if pole else None)
        return hard(g, material) if "." in material else _recolour(g, material)


def _recolour(o, kind):
    o.data.materials.clear()
    o.data.materials.append(kit.mat(kind))
    return o


def lon_steps(lo0, lo1, step, fine=(), fine_step=1.5):
    """Longitudes from lo0 to lo1 every `step` degrees, every `fine_step` inside the (a, b) ranges."""
    out = [lo0]
    lo = lo0
    while lo < lo1 - 1e-6:
        s = fine_step if any(a <= lo < b for a, b in fine) else step
        lo = min(lo1, lo + s)
        out.append(lo)
    return out


# ------------------------------------------------------------------------------------ helmet

def helmet(c, man):
    """The sealed pilot helmet: a clay shell over the crown, the sides and the nape with its brow over
    the visor, a wide dark visor from the brow to the bridge of the nose, a slate jaw guard with a
    breathing vent, rubber gaskets round the face opening and the lower edge, panel seams, a twin optic
    on the right, a comms pod with a whip antenna on the left and a battery at the back. Returns the
    envelope and the helmet's lower edge lat(lon) (for the hood under it)."""
    hc = man.head_center()
    dom = kit.dominant(man.low)
    me = man.low.data
    co = [v.co.copy() for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons if sum(dom[i] in ("head", "neck") for i in p.vertices) * 2 > len(p.vertices)]
    env = HeadEnv(BVHTree.FromPolygons(co, polys), hc + Vector((0, -0.016, -0.018)))
    SH, ST = 0.008, 0.0055   # the shell's inner surface over the envelope, its thickness
    SO = SH + ST
    BROW, CHEEK, NAPE, CHIN = 19.0, -40.0, -30.0, -49.0
    JAW = 74.0               # the jaw guard's reach round the sides

    def rim(lo):             # the shell's lower edge: brow, down the cheeks, under the ears, the nape
        a = abs(lo)
        return BROW + (CHEEK - BROW) * _sm(a, 52, JAW) + (NAPE - CHEEK) * _sm(a, 110, 160)

    def vis(lo):             # the visor's lower edge, over the bridge of the nose
        return -7.0 + 5.0 * _sm(abs(lo), 25, 62)

    def chin(lo):            # the jaw guard's lower edge, rising to meet the shell
        return CHIN + (CHEEK - CHIN) * _sm(abs(lo), 28, JAW)

    def bottom(lo):
        return chin(lo) if abs(lo) < JAW else rim(lo)

    def solve(f, a, b):
        for _ in range(40):
            m = (a + b) / 2
            a, b = (m, b) if f(m) > 0 else (a, m)
        return (a + b) / 2
    VL = solve(lambda lo: rim(lo) - vis(lo), 30.0, JAW) - 0.7

    def vtop(lo):
        return min(BROW, rim(lo))

    def off_v(la, lo):
        # Proud in the middle, curving in under the brow and the shell's cheeks.
        base = 0.0095 + 0.0065 * (1 - _sm(abs(lo), 28, 58))
        tuck = _sm(la, vtop(lo) - 7.0, vtop(lo))
        return base * (1 - tuck) + 0.004 * tuck

    def off_j(la, lo):
        # Close round the jaw, a moulded snout over the mouth, a keel down its middle.
        snout = 0.011 * math.exp(-((la + 25.0) / 12.0) ** 2 - (lo / 22.0) ** 2)
        keel = 0.0028 * math.exp(-(lo / 4.5) ** 2) * _sm(-la, 9.0, 18.0)
        return 0.009 + 0.004 * (1 - _sm(abs(lo), 26, 66)) + snout + keel

    sides = ((-JAW - 8, -44), (44, JAW + 8))
    shell = env.patch("helmet", SHELL2, lon_steps(-180.0, 174.0, 6.0, sides, 2.0),
                      rim, lambda lo: 86.0, SH, ST, nv=11, closed=True, pole=True, bevel=0.002)
    c.rigid(shell, "head")
    ts = tree(shell)
    visor = env.patch("visor", "glass", lon_steps(-VL, VL, 5.0, ((-VL, -40), (40, VL)), 2.0), vis, vtop, off_v, 0.003, nv=6, bevel=0.0)
    c.rigid(visor, "head")
    jaw = env.patch("jaw_guard", SHELL1, lon_steps(-JAW + 0.5, JAW - 0.5, 5.0, ((-JAW, -40), (-10, 10), (40, JAW)), 2.0),
                    chin, lambda lo: min(vis(lo), rim(lo)), off_j, 0.005, nv=7, bevel=0.002)
    c.rigid(jaw, "head")
    # A black seal between the visor and the jaw guard.
    c.rigid(env.patch("visor_seal", "black", lon_steps(-VL, VL, 5.0, ((-VL, -40), (40, VL)), 2.0),
                      lambda lo: vis(lo) - 1.8, lambda lo: vis(lo) + 1.8,
                      lambda la, lo: max(off_v(la, lo) + 0.003, off_j(la, lo) + 0.005) - 0.001, 0.003, nv=1, bevel=0.0), "head")
    # Rubber gaskets: round the face opening, and the helmet's whole lower edge.
    edge = [env.P(rim(lo), lo, SH + ST * 0.5) for lo in lon_steps(-JAW + 1.0, JAW - 1.0, 4.0, ((-JAW, -44), (44, JAW)), 1.5)]
    c.rigid(tube("visor_gasket", edge, 0.0032, "rubber", segs=6), "head")
    low = []
    for lo in lon_steps(-180.0, 180.0 - 4.0, 4.0, ((-JAW - 6, -JAW + 6), (JAW - 6, JAW + 6)), 2.0):
        if abs(lo) < JAW:
            low.append(env.P(chin(lo), lo, off_j(chin(lo), lo) + 0.0025))
        else:
            low.append(env.P(rim(lo), lo, SH + ST * 0.5))
    c.rigid(tube("helmet_gasket", relax(low, 1), 0.0036, "rubber", closed=True, segs=6), "head")

    # Panel seams: two grooves from the brow over the crown to the back, one round the back.
    def groove(name, pts):
        if len(pts) > 3:
            c.rigid(tube(name, relax(pts, 2, closed=False), 0.0013, "rubber", segs=5), "head")
    for sx in (1, -1):
        pts = []
        o0 = env.O + Vector((sx * 0.042, 0, 0))
        for k in range(30):
            el = math.radians(28 + 182 * k / 29)
            d = Vector((0, -math.cos(el), math.sin(el)))
            loc, nor = hit(ts, o0 + d * 0.3, -d)
            if loc is None:
                continue
            la, lo = env.latlon(loc)
            if la < rim(lo) + 5.0:
                continue
            pts.append(loc + d * 0.0004)
        groove("helmet_seam", pts)
    back = []
    for lo in range(84, 277, 4):
        lo_ = (lo + 180) % 360 - 180
        back.append(env.P(-2.0, lo_, SO + 0.0004))
    groove("helmet_seam", back)

    # Twin optic on the right side, facing forward.
    la, lo = 2.0, -100.0
    p, n = env.P(la, lo, SO), env.normal(la, lo, SO)
    t, n, z = basis(n)
    hous = kit.block("optic", (0, 0, 0), (0.05, 0.022, 0.034), "slate", bevel=0.004)
    c.rigid(oriented(hous, p + n * 0.009 + t * 0.006, t, n, z), "head")
    for dz in (0.008, -0.008):
        q = p + n * 0.011 + t * 0.031 + z * dz
        c.rigid(kit.cyl("optic_lens", q - t * 0.003, q + t * 0.004, 0.0072, "gunmetal", segs=14, bevel=0.0008), "head")
        c.rigid(kit.cyl("optic_glass", q + t * 0.0035, q + t * 0.0048, 0.0052, "glass", segs=14, bevel=0.0), "head")
    c.rigid(kit.cyl("optic_led", p + n * 0.0205 - t * 0.012 + z * 0.01, p + n * 0.0222 - t * 0.012 + z * 0.01, 0.0026, "glow_amber", segs=8, bevel=0.0), "head")
    # Comms pod on the left with a whip antenna back over the crown.
    la, lo = -8.0, 98.0
    p, n = env.P(la, lo, SO), env.normal(la, lo, SO)
    t, n, z = basis(n)
    c.rigid(kit.cyl("comms", p - n * 0.003, p + n * 0.012, 0.03, "slate", segs=20, bevel=0.002), "head")
    c.rigid(kit.cyl("comms_cap", p + n * 0.012, p + n * 0.016, 0.021, "gunmetal", segs=20, bevel=0.0012), "head")
    for dz in (-0.009, 0.0, 0.009):
        c.rigid(oriented(kit.block("comms_grille", (0, 0, 0), (0.024, 0.0016, 0.0035), "black", bevel=0.0), p + n * 0.0165 + z * dz, t, n, z), "head")
    base = p + n * 0.008 + z * 0.026 - t * 0.01
    c.rigid(kit.cyl("antenna_base", base - z * 0.004, base + z * 0.01, 0.0055, "black", segs=10, bevel=0.001), "head")
    tip = base + (z * 0.75 - t * 0.66).normalized() * 0.14
    c.rigid(kit.cyl("antenna", base + z * 0.008, tip, 0.0024, "rubber", r1=0.0015, segs=6, bevel=0.0), "head")
    # Battery at the back, low on the shell.
    la, lo = 4.0, 180.0
    p, n = env.P(la, lo, SO), env.normal(la, lo, SO)
    t, n, z = basis(n, fwd=(1, 0, 0))
    bat = kit.block("battery", (0, 0, 0), (0.07, 0.024, 0.04), "slate", bevel=0.005)
    kit.cut(bat, *[kit.block("groove", (x, 0.012, 0), (0.004, 0.006, 0.05), "steel", bevel=0) for x in (-0.02, 0.0, 0.02)])
    c.rigid(oriented(bat, p + n * 0.01, t, n, z), "head")
    # The breathing vent at the front of the jaw guard.
    la, lo = -30.0, 0.0
    p, n = env.P(la, lo, off_j(la, lo) + 0.005), env.normal(la, lo, off_j(la, lo) + 0.005)
    t, n, z = basis(n, fwd=(1, 0, 0))
    vent = kit.block("jaw_vent", (0, 0, 0), (0.042, 0.012, 0.03), "black", bevel=0.004)
    kit.cut(vent, *[kit.block("slot", (0, 0.006, dz), (0.03, 0.006, 0.0032), "steel", bevel=0) for dz in (-0.008, 0.0, 0.008)])
    c.rigid(oriented(vent, p + n * 0.003, t, n, z), "head")
    for sx in (1, -1):
        la, lo = -36.0, sx * 40.0
        p, n = env.P(la, lo, off_j(la, lo) + 0.005), env.normal(la, lo, off_j(la, lo) + 0.005)
        t, n, h = basis(n, fwd=(0, 0, 1))
        for k in range(3):
            slat = kit.block("jaw_slat", (0, 0, 0), (0.022, 0.003, 0.0035), "gunmetal", bevel=0.0)
            c.rigid(oriented(slat, p + n * 0.0012 + t * (k - 1) * 0.007, h, n, h.cross(n)), "head")
    return env, bottom


# ------------------------------------------------------------------------------------ build

def build():
    b = real.Anatomy(height=1.80, body="male", sole=0.032)
    c = real.begin("runner", b)
    man = real.body(c, stubble=0.0, face_detail=1.0)
    surfaces._TEXEL_FN[man.low.name] = lambda obj: (lambda isl: 0.3)   # no skin shows
    J, seg = b.j, kit.seg_dist
    lead = real.bones_at(man)
    armpit = b.at("armpit")

    # ---------------------------------------------------------------- helmet (the head goes under it)
    for e in man.eyes:
        c.parts = [p for p in c.parts if p[0] is not e]
    env, bottom = helmet(c, man)
    for e in man.eyes:
        bpy_remove(e)
    c.cover({"head"})

    # ---------------------------------------------------------------- gloves
    gloves = real.gloves(c, man, "glove", cuff=0.065, knuckle="slate")
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
        ax = J("hand." + s, 0.0) - J("forearm." + s, 0.0)
        cc = J("hand." + s, 0.0) - ax.normalized() * 0.022
        r = _radius(tg, cc, ax)
        c.rigid(band("glove_cuff", cc, (r + 0.003, r * 0.82 + 0.003), 0.03, 0.004, "glove", axis=ax), "forearm." + s)
        tab = kit.block("cuff_tab", (0, 0, 0), (0.02, 0.004, 0.028), "accent", bevel=0.0012)
        M = Matrix((T, back, Lh)).transposed().to_4x4()
        M.translation = cc + back * (r + 0.005)
        tab.data.transform(M)
        c.rigid(tab, "forearm." + s)

    # ---------------------------------------------------------------- combat shirt
    neck = J("neck", 0.0)
    tuck = b.hip_z + 0.095
    waist = tuck - 0.03
    neckline = (Vector((0, 0, neck.z + 0.028)), Vector((0, -0.45, 1)).normalized())
    collar_top = (neckline[0] + Vector((0, 0, 0.03)), Vector((0, -0.25, 1)).normalized())

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
        a = min(seg(p, J("upper_arm." + s, 0.3), J("forearm." + s, 1.0)) for s in ("L", "R"))
        return 0.008 + 0.012 * max(0.0, min(1.0, (0.09 - a) / 0.03))

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
                         cuts, ease=ease, pin=pin, slack=slack, bend=12.0, texel=1.2,
                         trims=[("knit.primary", lambda p: (above(neckline, p) and lead(p) not in ARMS) or cuff(p))])
    c.hide_under(shirt.low, 0.05, 2)
    tshirt = tree(shirt.low)

    # The knit hood: from inside the collar up under the helmet's lower edge.
    def in_hood(p):
        if lead(p) not in ("head", "neck") or (Vector(p) - neckline[0]).dot(neckline[1]) < -0.025:
            return False
        la, lo = env.latlon(p)
        return la < bottom(lo) + 6.0
    hood = real.layer(c, man, "hood", "knit.primary", in_hood, [], ease=0.004, smooth=1, texel=0.8, seams="hems")
    c.hide_under(hood, 0.02, 1)

    # ---------------------------------------------------------------- hard plates on the arms
    for s, sx in (("L", 1), ("R", -1)):
        fa0, fa1 = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        ax = (fa1 - fa0).normalized()
        r = _radius(tshirt, fa0 + ax * 0.01, ax) + 0.003
        pad = wrap("elbow_pad", fa0 - ax * 0.03, fa0 + ax * 0.055, r, r - 0.005, 180 - 55 * sx, 180 + 55 * sx, 0.009, "black",
                   nt=4, nphi=8, bevel=0.003, bulge=0.004, fit=(tshirt, 0.0025))
        c.rigid(pad, "forearm." + s)
        # Shoulder caps: a clay shell over the deltoid with a slate lame under its edge.
        ua0, ua1 = J("upper_arm." + s, 0.0), J("upper_arm." + s, 1.0)
        A_ = (ua1 - ua0).normalized()
        top = ua0 - A_ * 0.035
        r = _radius(tshirt, ua0.lerp(ua1, 0.2), A_)
        cap = wrap("shoulder_cap", top, ua0.lerp(ua1, 0.4), r + 0.014, r + 0.007, 90 * sx - 66, 90 * sx + 66, 0.007, "grey",
                   nt=7, nphi=12, bevel=0.003, bulge=0.0025, round_ends=3.0, fit=(tshirt, 0.0065))
        c.rigid(hard(cap, SHELL2), "upper_arm." + s)
        lame = wrap("cap_lame", ua0.lerp(ua1, 0.34), ua0.lerp(ua1, 0.5), r + 0.01, r + 0.008, 90 * sx - 56, 90 * sx + 56, 0.006, "slate",
                    nt=3, nphi=10, bevel=0.0025, round_ends=3.0, fit=(tshirt, 0.004))
        c.rigid(lame, "upper_arm." + s)
        tcap = tree(cap)
        for ph in (90 * sx - 40, 90 * sx + 40):
            q = ua0.lerp(ua1, 0.28)
            d = Vector((math.sin(math.radians(ph)), -math.cos(math.radians(ph)), 0))
            loc, nor = hit(tcap, q + d * 0.3, -d)
            if loc is not None:
                c.rigid(kit.cyl("cap_screw", loc - d * 0.001, loc + d * 0.0022, 0.0042, "gunmetal", segs=8, bevel=0.0), "upper_arm." + s)
    # A clay guard on the right forearm, strapped on.
    fa0, fa1 = J("forearm.R", 0.0), J("forearm.R", 1.0)
    A_ = (fa1 - fa0).normalized()
    rr = _radius(tshirt, fa0.lerp(fa1, 0.5), A_)
    fg = wrap("forearm_guard", fa0.lerp(fa1, 0.2), fa0.lerp(fa1, 0.8), rr + 0.008, rr + 0.004, -90 - 66, -90 + 66, 0.007, "grey",
              nt=7, nphi=10, bevel=0.003, bulge=0.002, round_ends=3.0, fit=(tshirt, 0.0045))
    c.rigid(hard(fg, SHELL2), "forearm.R")
    tfg = tree(fg)
    for t in (0.33, 0.68):
        cc = fa0.lerp(fa1, t)
        o = sweep("guard_strap", hug_ring([tshirt, tfg], cc, A_, 0.0022, n=18), 0.02, 0.0035, "webbing", radial(cc, A_), closed=True)
        c.rigid(hard(o, "webbing.accent"), "forearm.R")
    # A raised rib down the guard.
    rib = []
    for i in range(9):
        q = fa0.lerp(fa1, 0.26 + 0.48 * i / 8)
        d = Vector((-1, 0, 0))
        d = (d - A_ * d.dot(A_)).normalized()
        loc, _ = hit(tfg, q + d * 0.3, -d)
        if loc is not None:
            rib.append(loc + d * 0.0008)
    if len(rib) > 3:
        c.rigid(tube("guard_rib", rib, 0.0022, "slate", segs=5), "forearm.R")

    # ---------------------------------------------------------------- plate carrier
    dz = (armpit - 0.198) - 1.03

    def Z(z):
        return z + dz
    R = 0.30
    th = 0.03
    f_out = kit.rounded([(-0.122, Z(1.03)), (0.122, Z(1.03)), (0.122, Z(1.29)), (0.07, Z(1.37)), (-0.07, Z(1.37)), (-0.122, Z(1.29))], 0.02)
    MF = fit(tshirt, f_out, R, 0.014, side=-1, tilt=5)
    front = [panel("carrier_front", f_out, 0.0, th, "grey", bevel=0.007)]
    kit.cut(front[0], *[kit.block("slot", (x, -th, Z(z)), (0.036, 0.007, 0.0075), "steel", bevel=0)
                        for z in (1.17, 1.198, 1.226) for x in (-0.075, -0.025, 0.025, 0.075)])
    hard(front[0], "cordura.secondary")
    y1 = -th
    # Admin panel: a slate loop field with a blank cream tab.
    front += [panel("velcro", rrect(-0.08, Z(1.255), 0.08, Z(1.345), 0.008), y1, 0.003, "pmc_velcro", bevel=0.001)]
    front += [hard(panel("id_tab", rrect(-0.05, Z(1.312), 0.05, Z(1.334), 0.004), y1 - 0.003, 0.002, "grey", bevel=0.0), "polymer.cream")]
    for x in (-0.08, 0.0, 0.08):
        p = [hard(kit.block("mag_pouch", (x, y1 - 0.021, Z(1.085)), (0.07, 0.042, 0.13), "grey", bevel=0.006), "cordura.primary"),
             hard(kit.block("pouch_flap", (x, y1 - 0.023, Z(1.142)), (0.074, 0.048, 0.03), "grey", bevel=0.005), "cordura.primary"),
             kit.block("bungee", (x, y1 - 0.043, Z(1.08)), (0.072, 0.004, 0.012), "black", bevel=0.0015),
             hard(kit.block("pull_tab", (x, y1 - 0.05, Z(1.132)), (0.026, 0.005, 0.034), "grey", bevel=0.0015), "webbing.accent")]
        p += [kit.block("stitch", (x + dx, y1 - 0.0425, Z(1.085)), (0.003, 0.002, 0.11), "black", bevel=0) for dx in (-0.031, 0.031)]
        front += p
    put(front, MF, R)
    rigid_all(c, front, "chest")

    b_out = kit.rounded([(-0.126, Z(1.03)), (0.126, Z(1.03)), (0.126, Z(1.29)), (0.098, Z(1.36)), (-0.098, Z(1.36)), (-0.126, Z(1.29))], 0.025)
    MB = fit(tshirt, b_out, R, 0.014, side=1, tilt=6)
    rear = [panel("carrier_back", b_out, 0.0, th, "grey", bevel=0.007)]
    kit.cut(rear[0], *[kit.block("slot", (x, -th, Z(z)), (0.036, 0.007, 0.0075), "steel", bevel=0)
                       for z in (1.262, 1.29) for x in (-0.075, -0.025, 0.025, 0.075)])
    hard(rear[0], "cordura.secondary")
    by = -th
    handle = sweep("drag_handle", smooth_path([(-0.04, by + 0.004, Z(1.335)), (-0.032, by - 0.018, Z(1.37)), (0.032, by - 0.018, Z(1.37)),
                                               (0.04, by + 0.004, Z(1.335))], 4), 0.026, 0.005, "webbing", radial((0, by + 0.01, Z(1.33)), (1, 0, 0)))
    rear += [hard(handle, "webbing.accent")]
    # The jump kit: a slate housing on the back plate, a clay cover with vents, twin thrusters angled
    # down and out under it, fuel cells across its top, a status lamp.
    jz = Z(1.135)
    jd = 0.07                          # the housing's depth off the plate
    jo = by - jd                       # its outer face
    pack = kit.block("jump_pack", (0, by - jd / 2, jz), (0.18, jd, 0.165), "slate", bevel=0.009)
    kit.cut(pack, *[kit.block("fin", (x, by - jd / 2, Z(1.05)), (0.006, jd + 0.02, 0.03), "steel", bevel=0) for x in (-0.03, -0.015, 0.0, 0.015, 0.03)])
    rear += [pack]
    cover = kit.block("jump_cover", (0, jo - 0.003, jz + 0.018), (0.158, 0.012, 0.112), "grey", bevel=0.004)
    kit.cut(cover, *[kit.block("vent", (0, jo - 0.009, jz + 0.012 + k * 0.017), (0.1, 0.01, 0.0065), "steel", bevel=0) for k in (-1, 0, 1)])
    rear += [hard(cover, SHELL2)]
    for sx in (1, -1):
        a = Vector((sx * 0.055, by - jd * 0.55, Z(1.066)))
        d = Vector((sx * 0.36, -0.14, -1)).normalized()
        e = a + d * 0.072
        rear += [kit.cyl("thruster", a, e, 0.024, "gunmetal", r1=0.031, segs=18, bevel=0.0015),
                 kit.cyl("thruster_throat", e - d * 0.005, e + d * 0.0005, 0.027, "black", segs=18, bevel=0.0),
                 kit.ring("thruster_ring", a + d * 0.022, d, 0.0285, 0.023, 0.009, "steel", segs=18)]
    rear += [kit.cyl("fuel_cell", (-0.082, by - jd * 0.45, jz + 0.098), (0.082, by - jd * 0.45, jz + 0.098), 0.017, "gunmetal", segs=14, bevel=0.002),
             kit.cyl("fuel_cap", (-0.093, by - jd * 0.45, jz + 0.098), (-0.082, by - jd * 0.45, jz + 0.098), 0.013, "black", segs=12, bevel=0.001),
             kit.cyl("fuel_cap", (0.082, by - jd * 0.45, jz + 0.098), (0.093, by - jd * 0.45, jz + 0.098), 0.013, "black", segs=12, bevel=0.001),
             kit.cyl("status", (0.058, jo - 0.008, jz + 0.06), (0.058, jo - 0.0115, jz + 0.06), 0.0042, "glow_amber", segs=10, bevel=0.0)]
    for sx in (1, -1):
        rear += [hard(kit.block("pack_strap", (sx * 0.094, by - jd / 2, jz), (0.022, jd + 0.004, 0.012), "webbing", bevel=0.0015), "webbing.accent")]
    put(rear, MB, R)
    rigid_all(c, rear, "chest")

    # Padded shoulder straps (accent) with buckles, a PTT on the left one.
    for s, sx in (("L", 1), ("R", -1)):
        xs = sx * 0.085
        pts = []
        for y in (-0.13, -0.10, -0.07, -0.04, -0.01, 0.02, 0.05, 0.08, 0.11, 0.13):
            loc, _ = hit(tshirt, (xs, y, 1.9), (0, 0, -1))
            z = loc.z + 0.008 if loc and loc.z > armpit + 0.05 else None
            pts.append((xs, y, z))
        pts = [(xs, y, z if z is not None else Z(1.36)) for xs, y, z in pts]
        pts[0] = to_world((sx * 0.068, -0.012, Z(1.352)), MF, R)
        pts[-1] = to_world((-sx * 0.075, -0.012, Z(1.34)), MB, R)
        path = smooth_path(pts, 3)
        nrm = radial((sx * 0.085, 0, Z(1.33)), (1, 0, 0))
        strap = sweep("shoulder_strap", path, 0.05, 0.013, "accent", nrm)
        c.rigid(strap, "chest")
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
                   hard(kit.cyl("ptt_button", (0, -0.017, 0.004), (0, -0.023, 0.004), 0.009, "grey", segs=14, bevel=0.0015), SHELL2)]
            put(ptt, Mp)
            rigid_all(c, ptt, "chest")

    # Cummerbund: both sides from under the front plate to under the back plate.
    for s, sx in (("L", 1), ("R", -1)):
        for z, w in ((Z(1.07), 0.055), (Z(1.135), 0.055)):
            pts = _ring_side(tshirt, (0, -0.004), z, 0.012, sx * 46, sx * 136)
            c.rigid(hard(sweep("cummerbund", smooth_path(pts, 3), w, 0.012, "grey", radial((0, -0.004, 0))), "cordura.secondary"), "chest")
        side = _ring_side(tshirt, (0, -0.004), Z(1.1), 0.026, sx * 90, sx * 90, n=2)[0]
        c.rigid(kit.block("cb_tab", side, (0.012, 0.03, 0.11), "black", bevel=0.003), "chest")
    # Radio pouch on the left side, behind the arm: the radio's top and its whip antenna show.
    a = math.radians(122)
    pt = _ring_side(tshirt, (0, -0.004), Z(1.11), 0.038, 122, 122, n=2)[0]
    n = Vector((math.sin(a), -math.cos(a), 0))
    tt = Vector((math.cos(a), math.sin(a), 0))
    up = Vector((0, 0, 1))
    c.rigid(oriented(hard(kit.block("radio_pouch", (0, 0, 0), (0.062, 0.036, 0.11), "grey", bevel=0.005), "cordura.primary"), pt, -tt, n, up), "chest")
    c.rigid(oriented(hard(kit.block("radio_flap", (0, 0, 0), (0.064, 0.04, 0.012), "grey", bevel=0.003), "webbing.accent"), pt + up * 0.04, -tt, n, up), "chest")
    rtop = pt + up * 0.07
    c.rigid(oriented(kit.block("radio", (0, 0, 0), (0.054, 0.03, 0.04), "black", bevel=0.004), rtop - up * 0.008, -tt, n, up), "chest")
    c.rigid(kit.cyl("radio_knob", rtop + up * 0.012 + tt * 0.014, rtop + up * 0.022 + tt * 0.014, 0.0075, "grey", segs=12, bevel=0.0012), "chest")
    ab = rtop + up * 0.012 - tt * 0.014
    c.rigid(kit.cyl("radio_antenna_base", ab, ab + up * 0.02, 0.0065, "black", segs=10, bevel=0.001), "chest")
    c.rigid(kit.cyl("radio_antenna", ab + up * 0.018, ab + up * 0.018 + (up * 0.93 + n * 0.25 + Vector((0, 0.2, 0))).normalized() * 0.2,
                    0.0032, "rubber", r1=0.0022, segs=6, bevel=0.0), "chest")

    # ---------------------------------------------------------------- trousers
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

    trousers = real.garment(c, man, "trousers", "twill.primary", lambda p: lead(p) in LEGS | {"hips", "spine"} and hem - 0.03 < p.z < top_z + 0.03,
                            [((0, 0, top_z), (0, 0, 1)), ((0, 0, hem), (0, 0, -1), lambda p: lead(p) in LEGS)],
                            ease=t_ease, pin=t_pin, slack=t_slack, bend=14.0, texel=1.0)
    c.hide_under(trousers.low, 0.06, 2)
    tt_ = tree(trousers.low)
    belt = sweep("belt", ring_pts(tt_, (0, -0.005), belt_z, 0.004, n=32), 0.044, 0.009, "webbing", radial((0, -0.005, 0)), closed=True)
    c.add(hard(belt, "webbing.accent"), ["hips", "spine"])
    bk = [kit.block("buckle", (0, 0, 0), (0.062, 0.012, 0.038), "gunmetal", bevel=0.003)]
    kit.cut(bk[0], kit.block("buckle_slot", (0, -0.006, 0), (0.044, 0.006, 0.02), "steel", bevel=0))
    bk.append(kit.block("buckle_bar", (0, -0.002, 0), (0.05, 0.006, 0.006), "bright", bevel=0.0015))
    loc, _ = hit(tt_, (0, -0.5, belt_z), (0, 1, 0))
    for o in bk:
        o.data.transform(Matrix.Translation(Vector((0, loc.y - 0.015, belt_z))))
        c.rigid(o, "hips")
    for s, sx in (("L", 1), ("R", -1)):
        ul0, ul1 = J("upper_leg." + s, 0.0), J("upper_leg." + s, 1.0)
        around = _limb(ul0, ul1)
        out = 90 * sx
        # Cargo pockets with flaps and a snap on the outside of each thigh.
        real.patch(c, trousers.low, "cargo", "twill.primary",
                   lambda p, out=out, around=around: (lambda t, a: 0.36 < t < 0.70 and abs(a - out) < 36)(*around(p)), lift=0.002, puff=0.014, thick=0.003)
        real.patch(c, trousers.low, "cargo_flap", "twill.primary",
                   lambda p, out=out, around=around: (lambda t, a: 0.33 < t < 0.42 and abs(a - out) < 39)(*around(p)), lift=0.017, puff=0.002, thick=0.003)
        sn = ul0.lerp(ul1, 0.4)
        loc, nor = hit(tt_, sn + Vector((sx * 0.3, 0, 0)), (-sx, 0, 0))
        if loc is not None:
            snap = loc + Vector((sx * 0.019, 0, 0))
            c.rigid(kit.cyl("snap", snap, snap + Vector((sx * 0.004, 0, 0)), 0.006, "gunmetal", segs=12, bevel=0.001), "upper_leg." + s)
        # Knee pads: a conforming black pad with a clay hard cap and screws, strapped behind the knee.
        knee = J("lower_leg." + s, 0.04)
        pad_cut = kit.slab("pad_cut", kit.rounded([(knee.x - 0.058, knee.z - 0.08), (knee.x + 0.058, knee.z - 0.08), (knee.x + 0.058, knee.z + 0.07),
                                                   (knee.x - 0.058, knee.z + 0.07)], 0.03), -0.4, knee.y - 0.01)
        pad = kit.plate(trousers.low, pad_cut, "kneepad", "black", offset=0.004, thick=0.016, bevel=0.006)
        c.rigid(pad, "lower_leg." + s)
        tp = tree(pad)
        loc, _ = hit(tp, knee + Vector((0, -0.4, -0.005)), (0, 1, 0))
        Mk = frame(loc + Vector((0, 0.001, 0)), (0, -1, 0.1))
        cap_objs = [hard(panel("knee_cap", kit.rounded([(-0.036, -0.046), (0.036, -0.046), (0.04, 0.03), (0.0, 0.05), (-0.04, 0.03)], 0.012),
                                0.0, 0.007, "grey", bevel=0.0025), SHELL2)]
        cap_objs += [panel("knee_rib", rrect(-0.028, -0.004, 0.028, 0.004, 0.002), -0.007, 0.002, "slate", bevel=0.0)]
        cap_objs += screws([(-0.026, -0.032), (0.026, -0.032)], -0.007, r=0.0034)
        put(cap_objs, Mk, 0.06, step=0.01)
        rigid_all(c, cap_objs, "lower_leg." + s)
        kz = knee + Vector((0, 0.0, -0.055))
        r = _radius(tt_, kz, (0, 0, 1)) + 0.004
        c.add(hard(band("pad_strap", kz, (r, r), 0.02, 0.006, "webbing", axis=(0, 0, 1)), "webbing.accent"), ["lower_leg." + s])

    # ---------------------------------------------------------------- boots
    real.boots(c, man, "boot", sole_kind="rubber", trim="rubber", top=0.19, lace="webbing", tab="accent")

    # ---------------------------------------------------------------- grapple launcher (left forearm)
    fa0, fa1 = J("forearm.L", 0.0), J("forearm.L", 1.0)
    A = (fa1 - fa0).normalized()
    out = Vector((1, 0, 0))
    out = (out - A * out.dot(A)).normalized()
    side = A.cross(out).normalized()     # toward the front of the hanging arm
    rr = _radius(tshirt, fa0.lerp(fa1, 0.5), A)
    br = wrap("bracer", fa0.lerp(fa1, 0.16), fa0.lerp(fa1, 0.8), rr + 0.006, rr + 0.002, 90 - 70, 90 + 70, 0.006, "slate",
              nt=6, nphi=10, bevel=0.003, fit=(tshirt, 0.0045))
    c.rigid(br, "forearm.L")
    tb_ = tree(br)

    def on_bracer(t, lift):
        q = fa0.lerp(fa1, t)
        loc, _ = hit(tb_, q + out * 0.3, -out)
        return (loc if loc is not None else q + out * (rr + 0.012)) + out * lift
    hc0, hc1 = on_bracer(0.22, 0.017), on_bracer(0.74, 0.017)
    L = (hc1 - hc0).length
    mid = (hc0 + hc1) / 2
    housing = kit.block("launcher", (0, 0, 0), (0.046, L, 0.03), "gunmetal", bevel=0.007)
    kit.cut(housing, *[kit.block("vent", (0.0, -L * 0.3 + i * 0.012, 0.015), (0.03, 0.0045, 0.008), "steel", bevel=0) for i in range(4)])
    oriented(housing, mid, side, (hc1 - hc0).normalized(), out)
    c.rigid(housing, "forearm.L")
    cv = hard(kit.block("launcher_cover", (0, 0, 0), (0.036, L * 0.5, 0.004), "grey", bevel=0.0015), SHELL2)
    oriented(cv, mid + out * 0.016 + A * (L * 0.18), side, A, out)
    c.rigid(cv, "forearm.L")
    muzzle = hc1 + A * 0.004
    c.rigid(kit.cyl("barrel", muzzle - A * 0.01, muzzle + A * 0.045, 0.0135, "gunmetal", segs=18, bevel=0.0015), "forearm.L")
    c.rigid(kit.ring("muzzle_ring", muzzle + A * 0.04, A, 0.0175, 0.0105, 0.01, "slate", segs=20), "forearm.L")
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
    c.rigid(hard(kit.cyl("spool_cap", sp_c + side * 0.014, sp_c + side * 0.018, 0.012, "grey", segs=16, bevel=0.001), SHELL2), "forearm.L")
    for t in (0.3, 0.7):
        cc = fa0.lerp(fa1, t)
        r = _radius(tshirt, cc, A) + 0.004
        o = sweep("launcher_strap", hug_ring([tshirt, tb_], cc, A, 0.003, n=18), 0.022, 0.004, "webbing", radial(cc, A), closed=True)
        c.rigid(hard(o, "webbing.accent"), "forearm.L")
        bkl = kit.block("strap_buckle", (0, 0, 0), (0.026, 0.006, 0.02), "gunmetal", bevel=0.0012)
        c.rigid(oriented(bkl, cc - side * (r + 0.003), A.cross(side), -side, A), "forearm.L")
    rel = hard(kit.block("release", (0, 0, 0), (0.012, 0.016, 0.008), "grey", bevel=0.002), SHELL2)
    c.rigid(oriented(rel, hc0.lerp(hc1, 0.72) + side * 0.026, side, A, out), "forearm.L")

    economise(c)
    return c


def bpy_remove(obj):
    import bpy
    bpy.data.objects.remove(obj, do_unlink=True)


SPEC = {"build": build, "faction": "deserters", "budget": (25000, 120000),
        "loadout": "smg",
        "colors": {"primary": "#141413", "secondary": "#D97757", "accent": "#D4A27F"}}
