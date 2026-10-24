"""Juggernaut, PMC: HALCYON's heavy assault contractor, an EOD-grade suit built as one system. A sealed
white helmet with a wide smoked visor in a rubber gasket, a navy moulded chin guard with a breather, a
navy crest with the hazard stripe, comms drums with the company mark over the ears and a fan pack at
the back; a padded navy ballistic collar; a navy soft-armour chest rig carrying a white blast plate
with the hexagon-chevron mark, HALCYON lettering, the unit tabs and the hazard band, two abdominal
lames and a groin flap; a back plate with the suit's cooling pack and two spare rockets; layered white
pauldrons trimmed in hazard yellow over navy lames, rerebraces, navy elbow cops, white vambraces with
navy ridges; white cuisses on navy, navy knee cops with the white hexagon cap, white greaves; all of it
strapped on with the Contractor's yellow straps over a graphite cordura undersuit, gauntleted gloves
and heavy boots.

Built on the realistic layer (real.py) like the Contractor: a real body, its head under the helmet and
a knit hood, gloved fists, the undersuit draped by the cloth simulation; every hard plate is laid on an
envelope of the cloth or head it sits on (the Acolyte's Env / Tube / Plate) and bakes its panel lines
from detail meshes; the company marks, lettering and hazard bands are raised parts bent onto the
plates. Procedural surfaces baked into one 2048 atlas; the white and navy shells use this module's
satin "halcyon" coat (registered for the Handler too).

Tints: primary = undersuit top and hood (graphite), secondary = undersuit legs, accent = the straps
(Contractor yellow). The armour, the navy soft armour and the marks are the PMC's fixed colours.

The first part of this module holds the PMC shell helpers the Handler imports: the coat recipe,
re-materialling, and laying flat marks onto curved surfaces.
"""

import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import kit
import real
import surfaces
from kit import TORSO, UPPER_ARMS, FOREARMS, THIGHS, SHINS
from chars import contractor as pmc
from chars.acolyte import Env, Tube, Plate, Armour, region_tree, sheet, weigh_custom
from chars.runner import tube, relax, oriented

ARMS = UPPER_ARMS | FOREARMS
LEGS = THIGHS | SHINS
FAST = bool(os.environ.get("PMC_FAST"))  # look-dev: skip the cloth simulation

# ------------------------------------------------------------------------------- PMC shell helpers

kit.hs.PALETTE.setdefault("pmc_liner", ((0.024, 0.025, 0.028), (0.08, 0.08, 0.085), 0.0, 0.92, 0.1, 0))   # helmet foam
surfaces.RECIPE.setdefault("pmc_liner", "canvas")


def halcyon_shell(g, pal):
    """HALCYON's hard armour: a moulded composite shell under a satin two-pack coat, white or navy.
    A faint orange peel and slow mottling in the coat, sparse long scuffs through to the darker
    composite; nothing finer than a few texels, so a big curved plate reads clean instead of breaking
    into speckle (the default polymer stipple does). Edge chips and cavity dirt come from the shared
    wear."""
    base, worn = pal[0], pal[1]
    pos = g.geo("Position")
    x, y, z = g.xyz(pos)
    peel = g.noise(pos, 120.0, detail=2, rough=0.45)
    mottle = g.noise(pos, 7.0, detail=3)
    shade = g.remap(mottle, 0.3, 0.7, 0.965, 1.03, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    a = g.noise(g.combine(x, y, g.mul(z, 0.08)), 50.0, detail=2)
    b = g.noise(g.combine(g.mul(x, 0.08), g.add(y, 1.7), g.add(z, 0.4)), 50.0, detail=2)
    lines = g.math("MAXIMUM", g.remap(g.math("ABSOLUTE", g.sub(a, 0.5)), 0.01, 0.0), g.remap(g.math("ABSOLUTE", g.sub(b, 0.5)), 0.01, 0.0))
    scuff = g.mul(lines, g.remap(g.noise(pos, 4.0, detail=2), 0.55, 0.68))
    col = g.mix(g.mul(scuff, 0.35), col, worn)
    rough = g.lerp(peel, pal[3] - 0.05, pal[3] + 0.03)
    rough = g.lerp(scuff, rough, 0.65)
    h = g.sub(g.add(g.mul(peel, 0.4), 0.3), g.mul(scuff, 0.4))
    return dict(color=col, rough=rough, metal=0.0, height=h, bump=0.00005)


surfaces.RECIPES.setdefault("halcyon", halcyon_shell)


def _local_ao(g, dist, samples=3):
    """Occlusion from the part's own geometry only, at most 1.2 cm out."""
    n = g.node("ShaderNodeAmbientOcclusion", samples=samples, only_local=True)
    n.inputs["Distance"].default_value = min(dist, 0.012)
    return n.outputs["AO"]


def _halcyon_wear(g, surf, pal, r):
    """A local version of the shared wear (surfaces._wear) for the halcyon coat only; every other
    surface goes to the shared one unchanged. The shared cavity dirt reads occlusion from every part
    within 2 cm and darkens to 55%, so a strap lying over a white plate, a spare rocket beside it or
    a hand near it in the bake pose baked a grey ghost of itself onto the plate. Here the occlusion
    comes from the armour's own geometry (only_local), reaches 1.2 cm and darkens to 78%; the big
    grime mottle is halved (the coat has its own); edge chips and dust are the shared ones. The
    navy soft armour ("halcyon_cordura", the shared cordura) keeps the shared wear with local
    occlusion."""
    if surf == "halcyon_cordura":   # the shared soft wear, its occlusion local
        g.ao = lambda dist, samples=3: _local_ao(g, dist, samples)
        try:
            return _halcyon_wear.shared(g, surf, pal, r)
        finally:
            del g.ao
    if surf != "halcyon":
        return _halcyon_wear.shared(g, surf, pal, r)
    base, worn, metal_, rough_, amount, _ = pal
    col, rough, metal, h = r["color"], r["rough"], r["metal"], r["height"]
    pos = g.geo("Position")
    ao = _local_ao(g, 0.012, 4)
    big = g.noise(pos, 7.0, detail=3)
    grime = g.remap(big, 0.3, 0.75, 0.95, 1.02, smooth=False)
    col = g.mix(1.0, col, g.rgb(grime, grime, grime), "MULTIPLY")
    edge = g.edge(0.0016)
    chip = g.mul(edge, g.remap(g.noise(pos, 260.0, detail=6), 0.48, 0.62))
    chip = g.mul(chip, g.remap(ao, 0.8, 0.95), clamp=True)
    wear = g.mul(chip, amount, clamp=True)
    col = g.mix(wear, col, worn)
    rough = g.lerp(wear, rough, min(1.0, rough_ + 0.1))
    h = g.sub(h, g.mul(wear, 0.4))
    dirt = g.remap(ao, 0.35, 0.95, 0.78, 1.0)
    col = g.mix(1.0, col, g.rgb(dirt, dirt, g.mul(dirt, 0.97)), "MULTIPLY")
    _, _, z = g.xyz(pos)
    dust = g.mul(g.remap(z, 0.55, 0.04), g.remap(g.noise(pos, 14.0, detail=4), 0.35, 0.7, 0.3, 1.0, smooth=False))
    col = g.mix(g.mul(dust, 0.32), col, (0.36, 0.33, 0.29))
    rough = g.lerp(g.mul(dust, 0.5), rough, 0.95)
    return col, rough, metal, h, g.remap(ao, 0.0, 1.0, 0.5, 1.0, smooth=False)


if not getattr(surfaces._wear, "halcyon", False):
    _halcyon_wear.shared = surfaces._wear
    _halcyon_wear.halcyon = True
    surfaces._wear = _halcyon_wear
WHITE, NAVYH = "halcyon.pmc_plate", "halcyon.pmc_navy_hard"   # the white and navy hard shells
# Navy cordura soft armour: the Contractor's pmc_navy as its own kind, so its cavity dirt can be local too.
kit.hs.PALETTE.setdefault("pmc_navy_soft", kit.hs.PALETTE["pmc_navy"])
surfaces.RECIPE.setdefault("pmc_navy_soft", "halcyon_cordura")
surfaces.RECIPES.setdefault("halcyon_cordura", surfaces.RECIPES["cordura"])
surfaces.SOFT.add("halcyon_cordura")
NAVY = "pmc_navy_soft"


def _sm(x, a, b):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def remat(o, kind):
    """Give a part the material `kind` (a palette kind or "<surface>.<tint>") on every face; a sheet
    with a liner keeps its inner faces' material."""
    m = real.mat(kind)
    me = o.data
    if len(me.materials) > 1 and "inner" in me.attributes:
        me.materials[0] = m
        return o
    me.materials.clear()
    me.materials.append(m)
    for p in me.polygons:
        p.material_index = 0
    return o


def slice_xz(o, step):
    """Edge loops every `step` across x and z, so a part built flat bends smoothly onto a surface."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for axis in (0, 2):
        cs = [v.co[axis] for v in bm.verts]
        lo, hi = min(cs), max(cs)
        n = int((hi - lo) / step)
        no = [0.0, 0.0, 0.0]
        no[axis] = 1.0
        for i in range(1, n):
            co = [0.0, 0.0, 0.0]
            co[axis] = lo + (hi - lo) * i / n
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-6, plane_co=co, plane_no=no)
    bm.to_mesh(o.data)
    bm.free()


def conform(objs, at, step=0.01):
    """Lay parts built flat (facing -Y, round x and z: pmc.panel, logo, text...) onto a curved
    surface: `at(x, z, d)` is the point `d` out from the surface at flat coordinates (x, z), and each
    vertex (x, y, z) goes to at(x, z, -y). Big parts get edge loops every `step` first."""
    for o in objs:
        if o.type != "MESH":
            continue
        if max(o.dimensions[0], o.dimensions[2]) > step * 1.5 and not o.name.startswith("label"):
            slice_xz(o, step)
        for v in o.data.vertices:
            v.co = at(v.co.x, v.co.z, -v.co.y)
        o.data.update()
    return objs


def on_plate(plate, off, x0=0.0, z0=0.0):
    """`at` for conform on an acolyte Plate: flat (x, z) about (x0, z0) on its surface `off` out (the
    back plates mirror x, so marks read the right way round from behind)."""
    sx = -1 if plate.side > 0 else 1

    def at(x, z, d):
        return plate.P(x0 + sx * x, z0 + z, off + d)
    return at


def on_tube(tb, t_c, ph_c, off):
    """`at` for conform on a limb Tube: flat x round the limb (degrees from ph_c), z up it."""
    R = tb.r(t_c, ph_c) + off

    def at(x, z, d):
        return tb.P(t_c - z / tb.L, ph_c + math.degrees(x / R), off + d)
    return at


def on_env(env, la_c, lo_c, off):
    """`at` for conform on an acolyte Env: flat x along the longitude, z up the latitude."""
    R = env.r(la_c, lo_c) + off

    def at(x, z, d):
        la = la_c + math.degrees(z / R)
        return env.P(la, lo_c + math.degrees(x / (R * max(0.2, math.cos(math.radians(la))))), off + d)
    return at


def on_tree(t, origin, n, up=(0, 0, 1)):
    """`at` for conform on any surface in ray-cast tree `t` (a dome: a pauldron, a knee cop): flat
    (x, z) round `origin` in the plane facing `n` (x and up as pmc.frame), dropped onto the surface
    along -n."""
    n = Vector(n).normalized()
    u = Vector(up)
    u = (u - n * u.dot(n)).normalized()
    r = (-n).cross(u)
    O = Vector(origin)

    def at(x, z, d):
        q = O + r * x + u * z
        loc, _ = pmc.hit(t, q + n * 0.1, -n)
        return (loc if loc is not None else q) + n * d
    return at


def tangents(n):
    """(forward, up) tangents of a surface with normal n: world -Y and +Z flattened onto it."""
    n = Vector(n).normalized()
    f = Vector((0, -1, 0))
    f = (f - n * f.dot(n)).normalized()
    u = n.cross(f).normalized()
    if u.z < 0:
        u = -u
    return f, u


def mark(size, base="white", inset="pmc_navy", chev="hazard", rim=None):
    """The company mark in flat space (pmc.logo), optionally on a border hexagon of colour `rim` (so
    the white badge reads on a white plate)."""
    out = []
    if rim:
        out.append(pmc.panel("logo_rim", pmc.hexagon(0, 0, size * 0.6), 0.0006, 0.0012, rim, bevel=0.0))
    return out + pmc.logo(0, 0, size, 0.0, base=base, inset=inset, mark=chev)


def wide_ring(tb, t, width, lift=0.003, n=24):
    """Tube.ring over a strap's whole width: per direction the outermost of every section row within
    half the width of t, hulled, `lift` off. A strap at one row's radius sank into a plate that swells
    or ends under its other edge (a ragged seam where they cut through each other)."""
    half = width / 2 / tb.L + 1e-6
    step = tb.ts[1] - tb.ts[0]
    rows = [i for i, tt in enumerate(tb.ts) if abs(tt - t) <= half + step * 0.5]
    rows = rows or [int(round(min(max((t - tb.ts[0]) / step, 0), len(tb.ts) - 1)))]
    pts = []
    for j, ph in enumerate(tb.phis):
        rs = [float(tb.raw[i][j]) for i in rows if tb.raw[i][j] == tb.raw[i][j]]
        if rs:
            pts.append((max(rs) * math.cos(math.radians(ph)), max(rs) * math.sin(math.radians(ph))))
    hull = real._resample(real._hull2d(pts), n)
    c = tb.c(t)
    out = []
    for x, y in hull:
        q = Vector((x, y))
        q = q * (1 + lift / max(q.length, 1e-6))
        out.append(c + tb.F * q.x + tb.S * q.y)
    return out


def strap_on(name, pts, centre, axis, width, thick, kind="webbing"):
    """A strap round a limb over its plates (a ring from Tube.ring): black webbing, or the yellow
    accent straps."""
    o = pmc.sweep(name, pts, width, thick, "accent", pmc.radial(centre, axis), closed=True, bevel=0.0)
    return remat(o, kind)


def tab_buckle(at, along, out, w=0.03):
    """A gunmetal cam buckle on a strap, its long side along `along`, facing `out`: a plate with a
    black cam bar across it."""
    u, n = Vector(along).normalized(), Vector(out).normalized()
    s = u.cross(n).normalized()
    o = kit.block("buckle", (0, 0, 0), (w, 0.007, w * 0.72), "gunmetal", bevel=0.0)
    bar = kit.block("buckle_cam", (0, -0.0045, w * 0.12), (w * 0.82, 0.004, w * 0.2), "black", bevel=0.0)
    o = kit.join([o, bar], "buckle")
    return oriented(o, Vector(at) + n * 0.0038, s, -n, u)


def screw(at, normal, r=0.004, material="gunmetal"):
    """A cheap unbevelled socket-head screw: an octagonal head with a black hex socket on it."""
    n = Vector(normal).normalized()
    at = Vector(at)
    head = kit.cyl("screw", at - n * 0.0012, at + n * 0.0022, r, material, segs=8, bevel=0.0)
    hexa = kit.cyl("screw_hex", at + n * 0.0021, at + n * 0.0027, r * 0.45, "black", segs=6, bevel=0.0)
    o = kit.join([head, hexa], "screw")
    o["bevel"] = 0.0
    return o


def lathe(name, prof, material, segs=16, a=(0, 0, 0), axis=(0, 0, 1)):
    """Revolve a (h, r) profile about the line from `a` along `axis` (r 0 closes a solid's end)."""
    A = Vector(axis).normalized()
    u = A.orthogonal().normalized()
    v = A.cross(u)
    a = Vector(a)
    bm = bmesh.new()
    rings = []
    for h, r in prof:
        c = a + A * h
        if r < 1e-6:
            rings.append([bm.verts.new(c)])
        else:
            rings.append([bm.verts.new(c + (u * math.cos(2 * math.pi * i / segs) + v * math.sin(2 * math.pi * i / segs)) * r) for i in range(segs)])
    for ra, rb in zip(rings, rings[1:]):
        for i in range(segs):
            j = (i + 1) % segs
            if len(ra) == 1 and len(rb) == 1:
                continue
            if len(ra) == 1:
                bm.faces.new((ra[0], rb[j], rb[i]))
            elif len(rb) == 1:
                bm.faces.new((ra[i], ra[j], rb[0]))
            else:
                bm.faces.new((ra[i], ra[j], rb[j], rb[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = kit.hs._obj(name, bm, material, 0.0)
    o["shaded"] = True
    return o


def rocket(a, axis):
    """A spare RR-1 round (the Skyhammer's rocket): steel nozzle, olive motor with its yellow and black
    bands and fins, steel collar, red ogive warhead and fuze; from `a` (the nozzle) along `axis`."""
    A = Vector(axis).normalized()
    out = [lathe("rocket_nozzle", [(0.0, 0.0078), (0.0, 0.0135), (0.013, 0.0168), (0.02, 0.0168), (0.02, 0.0)], "steel", 12, a, A),
           lathe("rocket_motor", [(0.018, 0.0), (0.018, 0.0235), (0.022, 0.0258), (0.254, 0.0258), (0.254, 0.0)], "olive", 16, a, A),
           lathe("rocket_collar", [(0.251, 0.0), (0.251, 0.0272), (0.2665, 0.0272), (0.2665, 0.0)], "steel", 16, a, A),
           lathe("rocket_warhead", [(0.265, 0.0), (0.265, 0.0262), (0.284, 0.0262), (0.314, 0.0244), (0.342, 0.0198), (0.364, 0.013),
                                    (0.377, 0.0072), (0.383, 0.0035), (0.3855, 0.0)], "red", 16, a, A),
           lathe("rocket_fuze", [(0.382, 0.0), (0.382, 0.0036), (0.3905, 0.0016), (0.3905, 0.0)], "steel", 8, a, A),
           lathe("rocket_band", [(0.212, 0.0), (0.212, 0.0262), (0.226, 0.0262), (0.226, 0.0)], "yellow", 16, a, A),
           lathe("rocket_band", [(0.06, 0.0), (0.06, 0.0262), (0.066, 0.0262), (0.066, 0.0)], "black", 16, a, A)]
    u = A.orthogonal().normalized()
    for k in range(4):
        d = Matrix.Rotation(math.pi / 4 + k * math.pi / 2, 3, A) @ u
        f = kit.block("rocket_fin", (0, 0, 0), (0.0016, 0.046, 0.0094), "olive", bevel=0.0)
        out.append(oriented(f, Vector(a) + A * 0.046 + d * 0.0302, d.cross(A), A, d))
    for o in out:
        if o.name.startswith(("rocket_motor", "rocket_fin")):
            remat(o, "halcyon.olive")
        elif o.name.startswith("rocket_warhead"):
            remat(o, "halcyon.red")
    return out


def gauntlets(c, b, man, guard=NAVYH, back_plate=WHITE, cuff_tab="hazard"):
    """Gloves with a hard knuckle guard, a back-of-hand plate and a velcro cuff (the Contractor's
    gloves, armoured)."""
    J = b.j
    gloves = real.gloves(c, man, "glove", cuff=0.046)
    tg = pmc.tree(gloves)
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
        loc, _ = pmc.hit(tg, mid + back * 0.12, -back)
        loc = loc if loc is not None else mid + back * 0.02
        g = remat(kit.block("knuckle", (0, 0, 0), (0.078, 0.013, 0.026), "grey", bevel=0.0024), guard)
        ridges = [kit.block("knuckle_ridge", (x, 0.0075, 0), (0.012, 0.003, 0.02), "black", bevel=0.0) for x in (-0.026, -0.009, 0.009, 0.026)]
        M = Matrix((T, back, Lh)).transposed().to_4x4()
        M.translation = loc + back * 0.0065 - Lh * 0.004
        for o in [g] + ridges:
            o.data.transform(M)
            c.rigid(o, "hand." + s)
        # The back-of-hand plate, between the wrist and the knuckle guard.
        q = W.lerp(mid, 0.5)
        loc, _ = pmc.hit(tg, q + back * 0.12, -back)
        if loc is not None:
            bp = kit.block("hand_plate", (0, 0, 0), (0.062, 0.009, 0.05), "grey", bevel=0.0025, taper=(0.86, 1.0))
            Mb = Matrix((T, back, Lh)).transposed().to_4x4()
            Mb.translation = loc + back * 0.0055
            bp.data.transform(Mb)
            c.rigid(remat(bp, back_plate), "hand." + s)
        ax = J("hand." + s, 0.0) - J("forearm." + s, 0.0)
        cc = J("hand." + s, 0.0) - ax.normalized() * 0.024
        r = pmc._radius(tg, cc, ax)
        c.rigid(pmc.band("glove_cuff", cc, (r + 0.0035, r * 0.82 + 0.0035), 0.034, 0.005, "glove", axis=ax), "forearm." + s)
        c.rigid(kit.block("cuff_tab", cc + back * (r + 0.007), (0.02, 0.004, 0.03), cuff_tab, bevel=0.0012), "forearm." + s)
    return gloves


# ------------------------------------------------------------------------------------------ helmet

def helmet(c, man, arm):
    """The sealed assault helmet, EOD style: a white shell over the crown, sides and nape fitted round
    the head with a foam liner; a big smoked visor from the brow down over the mouth, framed by a navy
    brow guard and a rubber gasket; a navy chin guard moulded over the chin with a breather port and
    side vents; a navy crest with the hazard stripe, comms drums with the company mark over the ears
    (an antenna on the left), a fan pack at the back and a light on the right. Returns the envelope,
    its lower edge lat(lon) and the fan pack's cable port."""
    hc = man.head_center()
    dom = kit.dominant(man.low)
    me = man.low.data
    co = [v.co.copy() for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons if sum(dom[i] in ("head", "neck") for i in p.vertices) * 2 > len(p.vertices)]
    head = BVHTree.FromPolygons(co, polys)
    O = hc + Vector((0, -0.014, -0.02))
    env = Env([head], O, reach=0.24, lat=(-84.0, 90.0), dlat=4.0, dlon=5.0, spread=16.0, blur=11.0, floor=0.007)
    SO, ST = 0.022, 0.0075    # the shell's outer surface over the envelope, its thickness
    BROW, CHEEK, NAPE, CHIN, JAW = 19.0, -48.0, -36.0, -60.0, 86.0

    def rim(lo):              # the shell's lower edge: the brow, down the temples and cheeks, the nape
        a = abs(lo)
        return BROW + (CHEEK - BROW) * _sm(a, 50, 84) + (NAPE - CHEEK) * _sm(a, 112, 168)

    def vis(lo):              # the visor's lower edge: over the mouth, curving up to the temples
        return -36.0 + 22.0 * _sm(abs(lo), 20, 64)

    def chin(lo):             # the chin guard's lower edge, rising to meet the shell
        return CHIN + (CHEEK - CHIN) * _sm(abs(lo), 24, JAW)

    def bottom(lo):
        return chin(lo) if abs(lo) < JAW else rim(lo)

    def solve(f, a, b):
        for _ in range(40):
            m = (a + b) / 2
            a, b = (m, b) if f(m) > 0 else (a, m)
        return (a + b) / 2
    VL = solve(lambda lo: rim(lo) - vis(lo), 30.0, JAW) - 0.4

    def vtop(lo):
        return min(BROW, rim(lo))

    def off_v(la, lo):
        # Proud in the middle (a thick moulded visor), curving in under the brow guard at its edges.
        base = SO - 0.004 + 0.005 * (1 - _sm(abs(lo), 24, 58)) * (1 - _sm(-la, 18, 36))
        tuck = _sm(la, vtop(lo) - 6.0, vtop(lo))
        return base * (1 - tuck) + (SO - ST + 0.0015) * tuck

    def off_j(la, lo):
        # Close round the jaw, a moulded muzzle over the chin, a keel down its middle.
        snout = 0.009 * math.exp(-((la + 46.0) / 10.0) ** 2 - (lo / 26.0) ** 2)
        keel = 0.0025 * math.exp(-(lo / 4.5) ** 2) * _sm(-la, 40.0, 46.0)
        return SO + 0.001 + snout + keel

    shell = env.patch("helmet", "pmc_plate", -180.0, 180.0, rim, lambda lo: 86.0, SO, ST, nu=60, nv=12, closed=True, pole=True,
                      inner="pmc_liner", bevel=0.0024)
    arm.add(remat(shell, WHITE), "head")
    visor = env.patch("visor", "glass", -VL, VL, vis, vtop, off_v, 0.004, nu=28, nv=6, bevel=0.0)
    c.rigid(visor, "head")
    jaw = env.patch("chin_guard", "pmc_navy_hard", -JAW + 0.5, JAW - 0.5, chin, lambda lo: min(vis(lo), rim(lo)), off_j, 0.0075, nu=34, nv=6,
                    inner="pmc_liner", bevel=0.0022)
    arm.add(remat(jaw, NAVYH), "head")
    # The navy brow guard over the visor's top and sides, a gasket round the whole face opening.
    brow = env.patch("brow_guard", "pmc_navy_hard", -(VL + 9.0), VL + 9.0, lambda lo: rim(lo) + 0.4, lambda lo: rim(lo) + 5.5, SO + 0.0045, 0.0075,
                     nu=30, nv=2, bevel=0.0018)
    arm.add(remat(brow, NAVYH), "head")
    loop = [env.P(rim(lo), lo, SO - ST * 0.4) for lo in [-JAW + 1.0 + (2 * JAW - 2.0) * i / 44 for i in range(45)]]
    c.rigid(tube("visor_gasket", relax(loop, 1, closed=False), 0.0042, "rubber", segs=5), "head")
    seal = [env.P(vis(lo), lo, max(off_v(vis(lo), lo), off_j(vis(lo), lo) - 0.002)) for lo in [-VL + 0.5 + (2 * VL - 1.0) * i / 30 for i in range(31)]]
    c.rigid(tube("visor_seal", relax(seal, 1, closed=False), 0.0036, "rubber", segs=5), "head")
    low = []
    for i in range(60):
        lo = -180.0 + 6.0 * i
        low.append(env.P(chin(lo), lo, off_j(chin(lo), lo) - 0.003) if abs(lo) < JAW else env.P(rim(lo), lo, SO - ST * 0.5))
    c.rigid(tube("helmet_gasket", relax(low, 1), 0.0042, "rubber", closed=True, segs=5), "head")

    # The breather port on the muzzle: a gunmetal ring round a black grille; slatted vents either side.
    la, lo = -47.0, 0.0
    p, n = env.P(la, lo, off_j(la, lo)), env.normal(la, lo, off_j(la, lo))
    f, u = tangents(n)
    c.rigid(kit.cyl("breather", p - n * 0.003, p + n * 0.009, 0.019, "gunmetal", segs=16, bevel=0.0015), "head")
    c.rigid(kit.cyl("breather_grille", p + n * 0.009, p + n * 0.011, 0.014, "black", segs=16, bevel=0.0), "head")
    for k in (-1, 0, 1):
        c.rigid(oriented(kit.block("breather_slat", (0, 0, 0), (0.022, 0.002, 0.0028), "gunmetal", bevel=0.0), p + n * 0.0115 + u * k * 0.007,
                         n.cross(u), n, u), "head")
    for sx in (1, -1):
        la, lo = -42.0, sx * 44.0
        p, n = env.P(la, lo, off_j(la, lo)), env.normal(la, lo, off_j(la, lo))
        f, u = tangents(n)
        side = n.cross(u).normalized()
        c.rigid(oriented(kit.block("jaw_vent", (0, 0, 0), (0.03, 0.006, 0.024), "black", bevel=0.0015), p + n * 0.002, side, n, u), "head")
        for k in (-1, 0, 1):
            c.rigid(oriented(kit.block("jaw_slat", (0, 0, 0), (0.026, 0.002, 0.003), "gunmetal", bevel=0.0), p + n * 0.0052 + u * k * 0.0068,
                             side, n, u), "head")

    # The crest: a navy ridge from the brow guard over the crown to above the fan pack, the hazard
    # stripe on it.
    ts = pmc.tree(shell)
    crest, nrm = [], []
    for k in range(28):
        el = math.radians(BROW + 6.0 + (160.0 - BROW - 6.0) * k / 27)
        d = Vector((0, -math.cos(el), math.sin(el)))
        loc, n = pmc.hit(ts, env.O + d * 0.4, -d)
        if loc is not None:
            crest.append(loc)
            nrm.append(n)

    def crest_n(p):
        return nrm[min(range(len(crest)), key=lambda i: (crest[i] - p).length_squared)]
    c.rigid(remat(pmc.sweep("crest", [p + n * 0.0035 for p, n in zip(crest, nrm)], 0.036, 0.008, "grey", crest_n), NAVYH), "head")
    c.rigid(pmc.sweep("crest_stripe", [p + n * 0.0084 for p, n in zip(crest[1:-1], nrm[1:-1])], 0.011, 0.0016, "hazard", crest_n, bevel=0.0), "head")

    # Comms drums over the ears with the company mark, an antenna on the left.
    for sx in (1, -1):
        la, lo = -16.0, sx * 98.0
        p, n = env.P(la, lo, SO), env.normal(la, lo, SO)
        t, z = tangents(n)
        drum = kit.cyl("ear_drum", p - n * 0.006, p + n * 0.017, 0.044, "grey", segs=20, bevel=0.003)
        c.rigid(remat(drum, NAVYH), "head")
        c.rigid(kit.cyl("ear_cap", p + n * 0.017, p + n * 0.0225, 0.034, "grey", segs=20, bevel=0.0015), "head")
        Mc = pmc.frame(p + n * 0.0225, n, (0, 0, 1))
        objs = pmc.logo(0, 0.004, 0.034, 0.0) + [screw(Mc @ Vector((0.024 * math.cos(math.radians(a)), -0.0006, 0.024 * math.sin(math.radians(a)))),
                                                       n, r=0.0026) for a in (45, 135, 225, 315)]
        pmc.put(objs[:-4], Mc)
        pmc.rigid_all(c, objs, "head")
        c.rigid(kit.cyl("ptt_knob", p + n * 0.008 + t * 0.044 - z * 0.012, p + n * 0.008 + t * 0.056 - z * 0.012, 0.008, "black", segs=10,
                        bevel=0.001), "head")
        if sx > 0:
            base = p + n * 0.004 + z * 0.04 - t * 0.012
            c.rigid(kit.cyl("antenna_base", base - z * 0.006, base + z * 0.012, 0.0065, "black", segs=10, bevel=0.001), "head")
            tip = base + (z * 0.82 - t * 0.52 + n * 0.1).normalized() * 0.16
            c.rigid(kit.cyl("antenna", base + z * 0.01, tip, 0.0026, "rubber", r1=0.0016, segs=6, bevel=0.0), "head")
    # The fan pack at the back: a navy housing with vent slots, a hazard band and a status lamp.
    la, lo = 0.0, 180.0
    p, n = env.P(la, lo, SO), env.normal(la, lo, SO)
    Mb = pmc.frame(p + n * 0.002, n, (0, 0, 1))
    fan = kit.block("fan_pack", (0, -0.017, 0), (0.106, 0.036, 0.07), "grey", bevel=0.005)
    kit.cut(fan, *[kit.block("vent", (x, -0.035, -0.008), (0.012, 0.01, 0.034), "steel", bevel=0) for x in (-0.03, -0.015, 0.0, 0.015, 0.03)])
    objs = [remat(fan, NAVYH)]
    objs += pmc.hazard_band(-0.04, 0.04, 0.02, 0.031, -0.0352)
    objs += [kit.cyl("fan_lamp", (0.042, -0.033, -0.024), (0.042, -0.0375, -0.024), 0.0042, "glow_amber", segs=10, bevel=0.0)]
    pmc.put(objs, Mb)
    pmc.rigid_all(c, objs, "head")
    port = Mb @ Vector((0.0, -0.02, -0.036))
    # A light on a short rail on the right, pointing ahead.
    la, lo = 8.0, -106.0
    p, n = env.P(la, lo, SO), env.normal(la, lo, SO)
    t, z = tangents(n)
    c.rigid(oriented(kit.block("light_rail", (0, 0, 0), (0.07, 0.008, 0.018), "black", bevel=0.0015), p + n * 0.003, t, n, z), "head")
    lp = p + n * 0.017 + t * 0.008
    c.rigid(kit.cyl("light", lp - t * 0.026, lp + t * 0.03, 0.0125, "gunmetal", segs=14, bevel=0.0015), "head")
    c.rigid(kit.cyl("light_lens", lp + t * 0.03, lp + t * 0.033, 0.0105, "glass", segs=14, bevel=0.0), "head")
    c.rigid(oriented(kit.block("light_mount", (0, 0, 0), (0.018, 0.012, 0.012), "black", bevel=0.001), lp - n * 0.0095, t, n, z), "head")
    return env, bottom, port


# ------------------------------------------------------------------------------------------ build

def build():
    b = real.Anatomy(height=1.90, width=1.04, sole=0.04)
    c = real.begin("juggernaut", b)
    man = real.body(c, stubble=0.0, face_detail=1.0)
    surfaces._TEXEL_FN[man.low.name] = lambda obj: (lambda isl: 0.3)   # no skin shows
    J, seg = b.j, kit.seg_dist
    lead = real.bones_at(man)
    armpit = b.at("armpit")
    crotch = b.at("crotch")
    head_arm = Armour(c, "armour_head", texel=2.3)
    torso_arm = Armour(c, "armour_torso", texel=2.0)
    arm_arm = Armour(c, "armour_arms", texel=1.9)
    leg_arm = Armour(c, "armour_legs", texel=1.9)

    # ---------------------------------------------------------------- helmet (the head goes under it)
    for e in man.eyes:
        c.parts = [p for p in c.parts if p[0] is not e]
    env, bottom, port = helmet(c, man, head_arm)
    for e in man.eyes:
        bpy.data.objects.remove(e, do_unlink=True)
    c.cover({"head"})

    # ---------------------------------------------------------------- gauntleted gloves
    gauntlets(c, b, man)

    # ---------------------------------------------------------------- undersuit top (padded cordura)
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
            return 0.009 - 0.003 * float(real._smooth(tuck + 0.03 - p.z, 0.0, 0.03))
        a = min(seg(p, J("upper_arm." + s, 0.3), J("forearm." + s, 1.0)) for s in ("L", "R"))
        return 0.011 + 0.012 * max(0.0, min(1.0, (0.09 - a) / 0.03))

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

    suit = real.garment(c, man, "suit", "halcyon_cordura.primary", lambda p: lead(p) in TORSO | ARMS | THIGHS | {"neck"} and p.z > waist - 0.05,
                        cuts, ease=ease, pin=None if FAST else pin, slack=slack, bend=16.0, texel=1.0)
    c.hide_under(suit.low, 0.05, 2)
    tsuit = pmc.tree(suit.low)

    # The knit hood: from inside the collar up under the helmet's lower edge.
    def in_hood(p):
        if lead(p) not in ("head", "neck") or (Vector(p) - neckline[0]).dot(neckline[1]) < -0.025:
            return False
        d = Vector(p) - env.O
        la = math.degrees(math.asin(max(-1.0, min(1.0, d.normalized().dot(env.Z)))))
        lo = math.degrees(math.atan2(d.dot(env.S), d.dot(env.F)))
        return la < bottom(lo) + 6.0
    hood = real.layer(c, man, "hood", "knit.primary", in_hood, [], ease=0.004, smooth=1, texel=0.6, seams="hems")
    c.hide_under(hood, 0.02, 1)

    # ---------------------------------------------------------------- undersuit legs
    top_z = tuck
    belt_z = b.hip_z + 0.07
    hem = b.sole + 0.21 - 0.03

    def t_ease(p):
        bnd = 0.003 * (1 - real._smooth(top_z - p.z, 0.02, 0.07))
        return 0.013 + bnd + 0.004 * real._smooth(top_z - p.z, 0.04, 0.2) + 0.006 * real._smooth(J("lower_leg.L", 0.0).z - p.z, 0.0, 0.15)

    def t_pin(p):
        return 1.0 if p.z > top_z - 0.045 or p.z < hem + 0.018 else 0.0

    def t_slack(p):
        return real._smooth(hem + 0.13 - p.z, 0.0, 0.1)

    legs = real.garment(c, man, "suit_legs", "halcyon_cordura.secondary", lambda p: lead(p) in LEGS | {"hips", "spine"} and hem - 0.03 < p.z < top_z + 0.03,
                        [((0, 0, top_z), (0, 0, 1)), ((0, 0, hem), (0, 0, -1), lambda p: lead(p) in LEGS)],
                        ease=t_ease, pin=None if FAST else t_pin, slack=t_slack, bend=16.0, texel=0.9)
    c.hide_under(legs.low, 0.06, 2)
    tlegs = pmc.tree(legs.low)

    # ---------------------------------------------------------------- ballistic collar
    # A padded navy roll round the neck: from the shoulders (laid on the suit) up to under the helmet.
    na, nb = J("neck", 0.0), J("neck", 1.0)
    c0 = Vector((0, na.y + 0.004, na.z + 0.03))
    torso_t = region_tree(suit.low, TORSO | {"neck"})
    NPHI = 32
    base, top = [], []
    for k in range(NPHI):
        a = 2 * math.pi * k / NPHI
        d = Vector((math.sin(a), -math.cos(a), 0))
        back_ = 0.5 - 0.5 * math.cos(a)            # 0 at the front, 1 at the back
        ray = (d * math.cos(math.radians(35)) - Vector((0, 0, math.sin(math.radians(35))))).normalized()
        loc, _ = pmc.hit(torso_t, c0 + ray * 0.3, -ray)   # from outside in: the shoulders, never the neck
        base.append((loc if loc is not None else c0 + ray * 0.12) + ray * 0.003)
        zt = na.z + 0.022 + 0.026 * back_
        axis_p = na.lerp(nb, (zt - na.z) / (nb.z - na.z))
        loc, _ = pmc.hit(man.tree, axis_p + d * 0.2, -d)
        rn = (Vector((loc.x, loc.y, 0)) - Vector((axis_p.x, axis_p.y, 0))).length if loc is not None else 0.06
        top.append(Vector((axis_p.x, axis_p.y, zt)) + d * (rn + 0.026))
    rows = []
    for i in range(6):
        u = i / 5
        row = []
        for k in range(NPHI):
            a = 2 * math.pi * k / NPHI
            d = Vector((math.sin(a), -math.cos(a), 0))
            row.append(base[k].lerp(top[k], u) + d * 0.016 * math.sin(math.pi * u) ** 0.8)
        rows.append(row)
    collar = sheet("collar", rows, NAVY, 0.02, Vector((0, na.y, na.z + 0.02)), closed=True, bevel=0.004)
    collar["texel"] = 1.0
    c.rigid(collar, "chest")
    tcol = pmc.tree(collar)

    # ---------------------------------------------------------------- chest rig and blast plate
    c_out = kit.rounded([(-0.162, armpit - 0.205), (0.162, armpit - 0.205), (0.166, armpit - 0.02), (0.13, armpit + 0.125), (0.082, armpit + 0.168),
                         (-0.082, armpit + 0.168), (-0.13, armpit + 0.125), (-0.166, armpit - 0.02)], 0.028)
    p_out = kit.rounded([(-0.148, armpit - 0.19), (0.148, armpit - 0.19), (0.152, armpit - 0.03), (0.116, armpit + 0.118), (0.068, armpit + 0.156),
                         (-0.068, armpit + 0.156), (-0.116, armpit + 0.118), (-0.152, armpit - 0.03)], 0.02)
    pf = Plate([tsuit], c_out, -1, 0.008)
    RIG = 0.036
    rig = pf.patch("chest_rig", NAVY, c_out, RIG, 0.032, nu=14, nv=11, bevel=0.005)
    rig["texel"] = 1.0
    c.rigid(rig, "chest")
    OFF = 0.056
    fp = pf.patch("blast_plate", "pmc_plate", p_out, OFF, 0.016, nu=18, nv=15, bevel=0.0032)
    torso_arm.add(remat(fp, WHITE), "chest")
    zl = armpit + 0.02
    marks = mark(0.105, rim="pmc_navy_hard")
    conform(marks, on_plate(pf, OFF, 0.0, zl + 0.03), step=0.012)
    pmc.rigid_all(c, marks, "chest")
    lettering = [pmc.text("HALCYON", 0.0, 0.0, 0.03, 0.0, "pmc_navy_hard", depth=0.0009)]
    conform(lettering, on_plate(pf, OFF, 0.0, zl - 0.055))
    pmc.rigid_all(c, lettering, "chest")
    tabs = pmc.name_patch("07", -0.022, 0.0, 0.032, 0.024, 0.0, base="hazard", ink="black", size=0.016)
    tabs += pmc.name_patch("A POS", 0.024, 0.0, 0.038, 0.024, 0.0, base="black", ink="white", size=0.0095)
    conform(tabs, on_plate(pf, OFF, 0.0, zl - 0.098))
    pmc.rigid_all(c, tabs, "chest")
    hband = pmc.hazard_band(-0.122, 0.122, -0.009, 0.009, 0.0)
    conform(hband, on_plate(pf, OFF, 0.0, armpit - 0.162), step=0.015)
    pmc.rigid_all(c, hband, "chest")
    for x, z in ((-0.126, armpit - 0.135), (0.126, armpit - 0.135), (-0.104, armpit + 0.1), (0.104, armpit + 0.1)):
        c.rigid(screw(pf.P(x, z, OFF), pf.normal(x, z), r=0.0048), "chest")

    # Abdominal lames under the rig: navy over white, overlapping downward, on the spine.
    a_out = kit.rounded([(-0.14, belt_z + 0.012), (0.14, belt_z + 0.012), (0.145, armpit - 0.2), (-0.145, armpit - 0.2)], 0.02)
    pa = Plate([tsuit, tlegs], a_out, -1, 0.008)
    z_top = armpit - 0.212
    z_mid = (z_top + belt_z + 0.012) / 2
    l1 = kit.rounded([(-0.138, z_mid - 0.008), (0.138, z_mid - 0.008), (0.142, z_top), (-0.142, z_top)], 0.016)
    l2 = kit.rounded([(-0.13, belt_z + 0.014), (0.13, belt_z + 0.014), (0.134, z_mid + 0.006), (-0.134, z_mid + 0.006)], 0.016)
    lame1 = pa.patch("lame", "pmc_navy_hard", l1, 0.04, 0.012, nu=12, nv=4, bevel=0.0028)
    lame2 = pa.patch("lame", "pmc_plate", l2, 0.03, 0.012, nu=12, nv=4, bevel=0.0028)
    torso_arm.add(remat(lame1, NAVYH), "spine")
    torso_arm.add(remat(lame2, WHITE), "spine")
    for sx in (1, -1):
        for zz, off in ((z_mid + 0.02, 0.04), ((belt_z + z_mid) / 2 + 0.004, 0.03)):
            c.rigid(screw(pa.P(sx * 0.115, zz, off), pa.normal(sx * 0.115, zz), r=0.0042), "spine")
    lt = [pmc.text("JGR-1", 0.0, 0.0, 0.019, 0.0, "pmc_navy_hard", depth=0.0008)]
    conform(lt, on_plate(pa, 0.03, 0.0, (belt_z + z_mid) / 2 + 0.006))
    pmc.rigid_all(c, lt, "spine")

    # Back: a navy rig panel with the white back plate, the suit's cooling pack and two spare rounds.
    b_out = kit.rounded([(-0.162, armpit - 0.27), (0.162, armpit - 0.27), (0.166, armpit - 0.02), (0.134, armpit + 0.12), (0.092, armpit + 0.162),
                         (-0.092, armpit + 0.162), (-0.134, armpit + 0.12), (-0.166, armpit - 0.02)], 0.03)
    bp_out = kit.rounded([(-0.148, armpit - 0.255), (0.148, armpit - 0.255), (0.152, armpit - 0.03), (0.12, armpit + 0.112), (0.082, armpit + 0.15),
                          (-0.082, armpit + 0.15), (-0.12, armpit + 0.112), (-0.152, armpit - 0.03)], 0.022)
    pb = Plate([tsuit], b_out, 1, 0.008)
    brig = pb.patch("back_rig", NAVY, b_out, RIG, 0.032, nu=14, nv=11, bevel=0.005)
    brig["texel"] = 1.0
    c.rigid(brig, "chest")
    bplate = pb.patch("back_plate", "pmc_plate", bp_out, OFF, 0.016, nu=16, nv=14, bevel=0.0032)
    torso_arm.add(remat(bplate, WHITE), "chest")
    back_band = pmc.hazard_band(-0.12, 0.12, -0.008, 0.008, 0.0)
    conform(back_band, on_plate(pb, OFF, 0.0, armpit + 0.085), step=0.015)
    pmc.rigid_all(c, back_band, "chest")
    sponsor = pmc.name_patch("VANTA LOGISTICS", 0.0, 0.0, 0.2, 0.03, 0.0, base="white", ink="black", size=0.0155)
    conform(sponsor, on_plate(pb, OFF, 0.0, armpit + 0.118), step=0.015)
    pmc.rigid_all(c, sponsor, "chest")
    # The cooling pack, built flat on the back plate's frame.
    zc = armpit - 0.11
    Mb = pb.frame(0.0, zc, OFF)
    pw, pd, ph = 0.19, 0.075, 0.21
    unit = kit.block("cooling_pack", (0, -pd / 2, 0), (pw, pd, ph), "grey", bevel=0.009)
    kit.cut(unit, *[kit.block("vent", (x, -pd, z), (0.028, 0.01, 0.0065), "steel", bevel=0) for x in (-0.05, -0.016) for z in (0.035, 0.055, 0.075)])
    remat(unit, NAVYH)
    lid = remat(kit.block("pack_lid", (0, -pd - 0.002, -0.038), (pw - 0.03, 0.006, 0.1), "grey", bevel=0.0025), WHITE)
    pack = [unit, lid]
    pack += [screw(Mb @ Vector((x, -pd - 0.005, z)), (Mb.to_3x3() @ Vector((0, -1, 0))), r=0.0038) for x in (-0.072, 0.072) for z in (-0.076, 0.0)]
    pack += [kit.cyl("pack_port", (0.05, -pd * 0.55, ph / 2 - 0.003), (0.05, -pd * 0.55, ph / 2 + 0.009), 0.015, "gunmetal", segs=14, bevel=0.0015),
             kit.cyl("pack_lamp", (0.05, -pd - 0.002, 0.084), (0.05, -pd - 0.005, 0.084), 0.0045, "glow_amber", segs=10, bevel=0.0)]
    pmc.put([o for o in pack if not o.name.startswith("screw")], Mb)
    pmc.rigid_all(c, pack, "chest")
    lm = mark(0.062, rim="pmc_navy_hard")
    pmc.put(lm, Mb @ Matrix.Translation((0, -pd - 0.005, -0.038)))
    pmc.rigid_all(c, lm, "chest")
    # Two spare rounds for the Skyhammer, warheads up in navy sleeves either side of the pack.
    for sx in (1, -1):
        x = sx * 0.122
        rk = rocket(Vector((x, -0.04, -0.16)), (0, 0, 1))
        for z in (-0.04, 0.1):
            rk.append(remat(kit.cyl("rocket_sleeve", Vector((x, -0.04, z - 0.026)), Vector((x, -0.04, z + 0.026)), 0.031, "grey", segs=16, bevel=0.002), NAVY))
            rk.append(remat(kit.block("sleeve_strap", (x - sx * 0.04, -0.024, z), (0.05, 0.012, 0.03), "grey", bevel=0.002), NAVY))
        pmc.put(rk, Mb)
        pmc.rigid_all(c, rk, "chest")
    # The fan pack's air line, down the back of the collar into the port on the pack's top.
    c.add(kit.rope("helmet_cable", [port, port + Vector((0.0, 0.012, -0.04)), Mb @ Vector((0.05, -pd * 0.55, ph / 2 + 0.05)),
                                    Mb @ Vector((0.05, -pd * 0.55, ph / 2 + 0.008))], 0.0045, "rubber"), ["head", "neck", "chest"])

    # Cummerbund from under the front rig round to under the back rig.
    for s, sx in (("L", 1), ("R", -1)):
        for z, w in ((armpit - 0.175, 0.06), (armpit - 0.1, 0.06)):
            pts = pmc._ring_side(tsuit, (0, -0.004), z, 0.014, sx * 44, sx * 138)
            c.rigid(pmc.sweep("cummerbund", pmc.smooth_path(pts, 3), w, 0.014, NAVY, pmc.radial((0, -0.004, 0)), bevel=0.0025), "chest")

    # Padded yellow shoulder straps over the collar's flanks, buckles front and back.
    for s, sx in (("L", 1), ("R", -1)):
        xs = sx * 0.13
        pts = []
        for y in (-0.12, -0.09, -0.06, -0.03, 0.0, 0.03, 0.06, 0.09, 0.12):
            best = None
            for t_ in (tsuit, tcol):
                loc, _ = pmc.hit(t_, (xs, y, 2.0), (0, 0, -1))
                if loc is not None and loc.z > armpit + 0.06 and (best is None or loc.z > best):
                    best = loc.z
            pts.append(Vector((xs, y, (best if best is not None else armpit + 0.17) + 0.008)))
        pts[0] = pf.P(sx * 0.1, armpit + 0.15, RIG + 0.004)
        pts[-1] = pb.P(sx * 0.11, armpit + 0.145, RIG + 0.004)
        path = pmc.smooth_path(pts, 3)
        nrm = pmc.radial((sx * 0.13, 0, armpit + 0.12), (1, 0, 0))
        c.rigid(remat(pmc.sweep("shoulder_strap", path, 0.056, 0.015, "accent", nrm, bevel=0.0025), "cordura.accent"), "chest")
        for yy in (-0.07, 0.075):
            k = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y - yy))
            tan = (path[k + 1] - path[k - 1]).normalized()
            nn = nrm(path[k]).normalized()
            c.rigid(tab_buckle(path[k] + nn * 0.0075, tan, nn, w=0.042), "chest")

    # ---------------------------------------------------------------- belt and groin flap
    belt = pmc.sweep("belt", pmc.ring_pts(tlegs, (0, -0.005), belt_z, 0.005, n=32), 0.052, 0.011, "webbing", pmc.radial((0, -0.005, 0)), closed=True,
                     bevel=0.002)
    c.add(belt, ["hips", "spine", "upper_leg.L", "upper_leg.R"])
    tbelt = pmc.tree(belt)
    loc, _ = pmc.hit(tbelt, (0, -0.5, belt_z), (0, 1, 0))
    bk = kit.block("buckle", (0, 0, 0), (0.07, 0.014, 0.042), "gunmetal", bevel=0.0025)
    bar = kit.block("buckle_bar", (0, -0.008, 0), (0.054, 0.004, 0.012), "bright", bevel=0.0)
    for o in (bk, bar):
        o.data.transform(Matrix.Translation(Vector((0, loc.y - 0.006, belt_z))))
        c.rigid(o, "hips")
    g_out = kit.rounded([(-0.084, belt_z - 0.02), (0.084, belt_z - 0.02), (0.072, crotch + 0.02), (0.036, crotch - 0.03), (-0.036, crotch - 0.03),
                         (-0.072, crotch + 0.02)], 0.018)
    g_plate = kit.rounded([(-0.066, belt_z - 0.034), (0.066, belt_z - 0.034), (0.056, crotch + 0.024), (0.028, crotch - 0.016), (-0.028, crotch - 0.016),
                           (-0.056, crotch + 0.024)], 0.014)
    pg = Plate([tlegs, tbelt], g_out, -1, 0.006, bend=(-3.5, -1.0))
    flap = pg.patch("groin_flap", NAVY, g_out, 0.02, 0.018, nu=8, nv=7, bevel=0.004)
    gplate = remat(pg.patch("groin_plate", "pmc_plate", g_plate, 0.03, 0.01, nu=8, nv=7, bevel=0.0025), WHITE)
    for o in (flap, gplate):
        kit.hs.apply_modifiers(o)
    gmark = mark(0.04, rim="pmc_navy_hard")
    conform(gmark, on_plate(pg, 0.03, 0.0, (belt_z + crotch) / 2 - 0.008), step=0.01)
    for o in gmark:
        kit.hs.apply_modifiers(o)
    gpart = kit.join([flap, gplate] + gmark, "groin_flap")
    zt_, zb_ = belt_z, crotch - 0.03

    def groin_w(p):
        f = _sm(zt_ - p.z, 0.0, zt_ - zb_)
        return {"hips": 1.0 - 0.5 * f, "upper_leg.L": 0.25 * f, "upper_leg.R": 0.25 * f}
    weigh_custom(c, gpart, groin_w)

    # Belt pouches behind the hips.
    for sx in (1, -1):
        a = math.radians(sx * 122)
        d = Vector((math.sin(a), -math.cos(a), 0))
        loc, _ = pmc.hit(tbelt, Vector((0, -0.005, belt_z)), d)
        if loc is None:
            continue
        M = pmc.frame(loc + d * 0.004, d)
        pouch = [kit.block("belt_pouch", (0, -0.026, -0.014), (0.085, 0.05, 0.095), NAVY, bevel=0.007),
                 kit.block("pouch_flap", (0, -0.028, 0.03), (0.09, 0.056, 0.024), NAVY, bevel=0.005),
                 kit.block("pull_tab", (0, -0.057, 0.018), (0.024, 0.005, 0.03), "hazard", bevel=0.0015)]
        pmc.put(pouch, M)
        pmc.rigid_all(c, pouch, "hips")

    # ---------------------------------------------------------------- arms
    for s, sx in (("L", 1), ("R", -1)):
        ua, fa = "upper_arm." + s, "forearm." + s
        ua0, ua1 = J(ua, 0.0), J(ua, 1.0)
        fa0, fa1 = J(fa, 0.0), J(fa, 1.0)
        sleeve = region_tree(suit.low, {ua, "shoulder." + s})
        tu = Tube([sleeve], ua0, ua1, front=(0, -1, 0), t=(0.05, 1.0), nt=26, nphi=48, reach=0.15, spread=0.03, blur=0.02)
        # Pauldron: a navy lame round the top of the arm, the white cap over the shoulder joint, its
        # rim trimmed in hazard yellow.
        lame = tu.patch("pauldron_lame", "pmc_navy_hard", 0.17, 0.42, 90 * sx, 80, 0.016, 0.009, nu=10, nv=3, corner=2.5, bevel=0.0025)
        arm_arm.add(remat(lame, NAVYH), ua)
        O = ua0 + Vector((-sx * 0.014, 0.0, -0.01))
        cap_env = Env([sleeve, lame], O, Z=(sx * 0.6, 0.0, 0.8), F=(0, -sx, 0), reach=0.18, lat=(-40.0, 90.0), dlat=4.0, dlon=6.0,
                      spread=9.0, blur=7.0, floor=0.004)

        def cap_rim(lo):
            sn = math.sin(math.radians(lo))
            return 36.0 - 60.0 * max(0.0, sn) ** 1.3 + 8.0 * max(0.0, -sn)
        CO = 0.025
        cap = cap_env.patch("pauldron", "pmc_plate", -180.0, 180.0, cap_rim, lambda lo: 84.0, CO, 0.01, nu=28, nv=6, closed=True, pole=True,
                            inner="pmc_liner", bevel=0.0032)
        arm_arm.add(remat(cap, WHITE), ua)
        trim = cap_env.patch("pauldron_trim", "hazard", -180.0, 180.0, lambda lo: cap_rim(lo) + 1.5, lambda lo: cap_rim(lo) + 6.0, CO + 0.0014, 0.003,
                             nu=28, nv=1, closed=True, bevel=0.0)
        c.rigid(trim, ua)
        # The sponsor patch on the left cap, the mark on the right.
        objs = (pmc.name_patch("ARGENT-7", 0.0, 0.0, 0.066, 0.026, 0.0, base="black", ink="white", size=0.012) if s == "L"
                else mark(0.052, rim="pmc_navy_hard"))
        out = (cap_env.Z * 0.6 + cap_env.S * 0.8).normalized()
        conform(objs, on_tree(pmc.tree(cap), cap_env.O + out * 0.02, out, (0, 0, 1)), step=0.01)
        pmc.rigid_all(c, objs, ua)
        for lo in (-30.0, -150.0):
            la = cap_rim(lo) + 10.0
            c.rigid(screw(cap_env.P(la, lo, CO), cap_env.normal(la, lo, CO), r=0.0038), ua)
        # Rerebrace: a white plate down the outside of the upper arm, strapped on.
        reb = tu.patch("rerebrace", "pmc_plate", 0.46, 0.86, 90 * sx, 74, 0.014, 0.009, nu=10, nv=7, corner=3.0, bulge=0.003, bevel=0.0028)
        arm_arm.add(remat(reb, WHITE), ua)
        tu2 = Tube([sleeve], ua0, ua1, hard=[reb, lame], t=(0.3, 0.95), nt=27, nphi=36, reach=0.15)
        c.rigid(strap_on("arm_strap", wide_ring(tu2, 0.66, 0.026, n=20), ua0.lerp(ua1, 0.66), ua1 - ua0, 0.026, 0.0045), ua)
        c.rigid(tab_buckle(tu2.P(0.66, 0.0, 0.0045), ua1 - ua0, tu2.d(0.0)), ua)
        # Elbow cop and vambrace on the forearm.
        fsl = region_tree(suit.low, {fa, ua})
        tf = Tube([fsl], fa0, fa1, front=(0, -1, 0), t=(-0.3, 1.0), nt=30, nphi=48, reach=0.13, spread=0.028, blur=0.02)
        cop = tf.patch("elbow_cop", "pmc_navy_hard", -0.16, 0.13, 180.0, 74, 0.017, 0.009, nu=9, nv=6, corner=2.5, bulge=0.008, bevel=0.003)
        arm_arm.add(remat(cop, NAVYH), fa)
        vam = tf.patch("vambrace", "pmc_plate", 0.2, 0.8, 90 * sx, 95, 0.014, 0.009, nu=11, nv=8, corner=3.0, bulge=0.004, bevel=0.0028)
        arm_arm.add(remat(vam, WHITE), fa)
        ridge = tf.patch("vambrace_ridge", "pmc_navy_hard", 0.25, 0.75, 90 * sx, 10, 0.0195, 0.006, nu=2, nv=6, corner=3.0, bulge=0.004, bevel=0.0015)
        arm_arm.add(remat(ridge, NAVYH), fa)
        tf2 = Tube([fsl], fa0, fa1, hard=[vam], t=(0.2, 0.9), nt=29, nphi=36, reach=0.13)
        for tq in (0.32, 0.7):
            c.rigid(strap_on("vambrace_strap", wide_ring(tf2, tq, 0.022, n=20), fa0.lerp(fa1, tq), fa1 - fa0, 0.022, 0.004), fa)
        for tq in (0.3, 0.7):
            c.rigid(screw(tf.P(tq, 90 * sx + 44, 0.014), tf.d(90 * sx + 44), r=0.0036), fa)

    # ---------------------------------------------------------------- legs
    for s, sx in (("L", 1), ("R", -1)):
        ul, ll = "upper_leg." + s, "lower_leg." + s
        ul0, ul1 = J(ul, 0.0), J(ul, 1.0)
        ll0, ll1 = J(ll, 0.0), J(ll, 1.0)
        # Cuisse: a white plate on a navy one wrapped round the front and outside of the thigh, hung
        # from the belt, two straps.
        tl = Tube([tlegs], ul0, ul1, t=(-0.05, 0.85), nt=30, nphi=60, reach=0.17, spread=0.03, blur=0.022)
        under = tl.patch("cuisse", "pmc_navy_hard", 0.12, 0.66, 44 * sx, 92, 0.016, 0.009, nu=13, nv=9, corner=3.0, bulge=0.004, bevel=0.0028)
        leg_arm.add(remat(under, NAVYH), ul)
        over = tl.patch("cuisse_plate", "pmc_plate", 0.16, 0.6, 30 * sx, 56, 0.026, 0.009, nu=11, nv=8, corner=3.0, bulge=0.006, bevel=0.0028)
        leg_arm.add(remat(over, WHITE), ul)
        tl2 = Tube([tlegs], ul0, ul1, hard=[under, over], t=(0.0, 0.8), nt=41, nphi=36, reach=0.18)
        for tq in (0.26, 0.54):
            c.rigid(strap_on("thigh_strap", wide_ring(tl2, tq, 0.03, n=22), ul0.lerp(ul1, tq), ul1 - ul0, 0.03, 0.0045), ul)
            c.rigid(tab_buckle(tl2.P(tq, 100 * sx, 0.0045), ul1 - ul0, tl2.d(100 * sx)), ul)
        for tq in (0.21, 0.55):
            for pq in (-38, 38):
                ph = 30 * sx + pq
                c.rigid(screw(tl.P(tq, ph, 0.026), tl.d(ph), r=0.0036), ul)
        # The hanger strap from under the belt (on the hip, not in the air beside it) to the cuisse.
        # It lies on the suit down the hip (rays out from the thigh's axis, carried up past the hip
        # joint), steps over the navy plate's top edge and is screwed to it: a straight run from the
        # belt to the plate's edge stood in the air off the curve of the hip.
        hang = tl.P(0.15, 40 * sx, 0.0195)
        ang = math.degrees(math.atan2(hang.x, -(hang.y + 0.005)))
        top = pmc._ring_side(tlegs, (0, -0.005), belt_z + 0.004, 0.0035, ang, ang, n=2)[0]
        dh = Vector((hang.x - ul0.x, hang.y - ul0.y, 0.0)).normalized()
        ax = ul1 - ul0
        tb_ = (belt_z - ul0.z) / ax.z
        path = [top]
        for k in range(1, 6):
            t = tb_ + (0.085 - tb_) * k / 5
            a = ul0 + ax * t
            loc, _ = pmc.hit(tlegs, a, dh)
            if loc is not None and (loc - a).length < 0.2:
                path.append(loc + dh * 0.0035)
        path += [tl.P(0.114, 40 * sx, 0.0205), hang]
        c.add(remat(pmc.sweep("hanger", pmc.smooth_path(path, 2), 0.024, 0.004, "black",
                              lambda p, s_=sx: tl.d(40 * s_)), "webbing"), ["hips", ul])
        c.rigid(screw(tl.P(0.142, 40 * sx, 0.0215), tl.d(40 * sx), r=0.0036), ul)
        # Greave down the shin with a navy ridge, a navy calf plate behind, two straps round both.
        tsh = Tube([tlegs], ll0, ll1, t=(-0.1, 0.9), nt=30, nphi=60, reach=0.15, spread=0.03, blur=0.022)
        greave = tsh.patch("greave", "pmc_plate", 0.15, 0.68, 4 * sx, 72, 0.016, 0.01, nu=11, nv=9, corner=3.0, bulge=0.006, bevel=0.003)
        leg_arm.add(remat(greave, WHITE), ll)
        gr = tsh.patch("greave_ridge", "pmc_navy_hard", 0.2, 0.62, 4 * sx, 9, 0.0215, 0.006, nu=2, nv=7, corner=3.0, bulge=0.006, bevel=0.0015)
        leg_arm.add(remat(gr, NAVYH), ll)
        calf = tsh.patch("calf_plate", "pmc_navy_hard", 0.18, 0.6, 180.0, 70, 0.013, 0.008, nu=10, nv=7, corner=3.0, bulge=0.005, bevel=0.0026)
        leg_arm.add(remat(calf, NAVYH), ll)
        tsh2 = Tube([tlegs], ll0, ll1, hard=[greave, calf], t=(0.1, 0.8), nt=36, nphi=36, reach=0.15)
        for tq in (0.3, 0.58):
            c.rigid(strap_on("shin_strap", wide_ring(tsh2, tq, 0.026, n=22), ll0.lerp(ll1, tq), ll1 - ll0, 0.026, 0.0045), ll)
        # Knee cop: a navy dome over the knee with the white hexagon cap and a stud.
        kn = ll0 + Vector((0, 0.012, 0.004))
        kenv = Env([tlegs, greave], kn, Z=(0, -1, 0.12), F=(0, 0, 1), reach=0.15, lat=(0.0, 90.0), dlat=4.0, dlon=8.0, spread=16.0, blur=10.0,
                   floor=0.004)

        def knee_rim(lo):
            return 40.0 - 12.0 * math.cos(math.radians(lo)) ** 2
        KO = 0.02
        cop = kenv.patch("knee_cop", "pmc_navy_hard", -180.0, 180.0, knee_rim, lambda lo: 84.0, KO, 0.01, nu=18, nv=5, closed=True, pole=True,
                         inner="pmc_liner", bevel=0.003)
        leg_arm.add(remat(cop, NAVYH), ll)
        kp = kenv.P(90, 0, KO)
        kn_n = kenv.normal(88, 0, KO, h=4.0)
        cap_objs = [remat(pmc.panel("knee_cap", pmc.hexagon(0, 0, 0.04, rot=90), 0.0, 0.006, "grey", bevel=0.0018), WHITE)]
        conform(cap_objs, on_tree(pmc.tree(cop), kp, kn_n, (0, 0.2, 1)), step=0.01)
        pmc.rigid_all(c, cap_objs, ll)
        c.rigid(kit.cyl("knee_stud", kp + kn_n * 0.004, kp + kn_n * 0.014, 0.011, "gunmetal", segs=12, bevel=0.0015), ll)

    # ---------------------------------------------------------------- boots
    real.boots(c, man, "boot", sole_kind="rubber", trim="rubber", top=0.21, lace="webbing", tab="hazard")

    for a in (head_arm, torso_arm, arm_arm, leg_arm):
        a.finish()
    pmc.economise(c)
    return c


SPEC = {"build": build, "faction": "pmc", "budget": (25000, 120000), "loadout": "rocket",
        "colors": {"primary": "#33383f", "secondary": "#2b2f35", "accent": "#c9a227"}}
