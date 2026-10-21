"""Breaker, Deserters: the heavy, a breacher who walked out of the Regime in its own armour. A bigger,
heavier body than the Runner's under the cult's plate, every piece repainted by hand in the crew's
colours: clay over the bone-white Regime coat, slate on the faceplate and the lames, cream stencil
stripes. Where the scripture and the sigils were, they are scratched out: the paint scuffed thin and
hatched with knife scratches through the bone coat to bright steel, specks of the black ink left in
it; everywhere else the new paint is scored and chipped through to the bone coat and, at the deepest
scratches and the edges, to the steel.

The reworked Regime helmet: the bone shell and respirator faceplate kept, the red sensor slit cut open
into a wide dark visor with a rubber gasket, the strobe on the rear battery swapped for an amber lamp,
the comms domes replaced by the Runner's twin optic (right) and comms pod with a whip antenna (left);
a knit hood under it. A slim slate carrier under a heavy clay breastplate with three frag grenades in
clay pouches on the placard, two shingled slate belly lames, the crew's jump kit on the back plate
(slate housing, clay cover, twin thrusters, fuel cells), cream padded shoulder straps with a PTT; big
clay shoulder caps over slate lames, clay vambraces, thigh guards hung from a padded battle belt, knee
caps and shin guards on black webbing; armoured gloves and tactical boots over a slate combat suit.

Built on the realistic layer (real.py) with the Acolyte's armour classes (Env, Tube, Plate, Armour):
every plate is laid on an envelope of the cloth or head it covers and bakes from a detail copy. The
paint is this module's own surface ("scavpaint"): the stencil stripes are shapes in rest-pose space
(MARKS) filled in while the plates are placed; the scratched-out scripture is laid on as flat detail
tiles in its own coat ("scratched") and baked in.

Tints: primary = combat suit, hood, carrier and battle belt (slate); secondary = shoulder straps,
belt, thigh hangers and the drag handle (cream); accent = grenade pouches and the jump kit's cover
(clay). The
painted plates are fixed colours in the same palette, so the bare steel under them stays steel.

ghost.py imports the suit, glove, paint and jump-kit helpers from here.
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
from chars import acolyte as reg
from chars.runner import tube, relax, oriented, basis

ARMS = UPPER_ARMS | FOREARMS
LEGS = THIGHS | SHINS
FAST = bool(os.environ.get("BREAKER_FAST"))  # look-dev: skip the cloth simulation


# ------------------------------------------------------------------------------------ palette

def lin(hx, k=1.0):
    """A #rrggbb colour as linear RGB, times k."""
    h = hx.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        c = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        out.append(c * k)
    return tuple(out)


SLATE, CLAY, CREAM, KRAFT = "#141413", "#D97757", "#F0EEE6", "#D4A27F"
# Paint as the game shows a tinted cloth of that colour (the bake's near-white 0.8 times the tint), so
# the painted plates sit with the Runner's tinted shells.
PAINT = {"slate": lin(SLATE, 0.8), "clay": lin(CLAY, 0.8), "cream": lin(CREAM, 0.8), "kraft": lin(KRAFT, 0.8)}
PRIMER = (0.74, 0.715, 0.655)    # the Regime's bone-white coat, under the repaint
STEEL = (0.54, 0.54, 0.55)       # plate steel, ground or scraped bright
INK = (0.02, 0.02, 0.025)        # the scripture's black ink

kit.hs.PALETTE.update({
    # name: (paint, worn, metallic, roughness, shared edge wear (the recipe chips its own), emission)
    "brk_clay": (PAINT["clay"], PRIMER, 0.0, 0.54, 0.0, 0),
    "brk_slate": (PAINT["slate"], PRIMER, 0.0, 0.5, 0.0, 0),
})


# ------------------------------------------------------------------------------------ the repaint

MARKS = []     # (point, normal, half width, ball centre, ball radius, [(point, normal) half-spaces]): stripes


def _marks(g, pos, marks):
    """1 inside the stencilled stripes, crisp-edged."""
    out = None
    for p, n, hw, bc, br, halves in marks:
        d = g.math("ABSOLUTE", g.vec("DOT_PRODUCT", g.vec("SUBTRACT", pos, tuple(p)), tuple(n)))
        m = g.remap(d, hw, hw - 0.0008)
        if bc is not None:
            m = g.mul(m, g.remap(g.vec("DISTANCE", pos, tuple(bc)), br, br - 0.004))
        for hp, hn in halves:
            m = g.mul(m, g.remap(g.vec("DOT_PRODUCT", g.vec("SUBTRACT", pos, tuple(hp)), tuple(hn)), 0.0, 0.0008))
        out = m if out is None else g.math("MAXIMUM", out, m)
    return out if out is not None else 0.0


def _unit(v):
    return tuple(Vector(v).normalized())


# Scratch families: (across, along, pitch, seed). Each is a set of parallel straight scores every
# `pitch` metres across, broken into random lengths along; a family fades out on faces turned to its
# `across` direction (there its scores would run together).
FAMILIES = [((0.8, 0.0, 0.6), (-0.6, 0.0, 0.8), 0.011, 0.0), ((-0.3, 0.6, 0.74), (0.0, 0.78, -0.63), 0.013, 3.1),
            ((0.25, -0.9, 0.36), (0.96, 0.27, 0.0), 0.017, 7.4)]
HATCH = [((1.0, 0.2, 0.3), (-0.3, 0.0, 1.0), 0.0047, 1.7), ((0.2, 1.0, -0.4), (1.0, -0.2, 0.0), 0.0053, 5.3),
         ((-0.3, 0.3, 1.0), (1.0, 0.3, 0.2), 0.0059, 9.1), ((0.7, -0.7, 0.2), (0.7, 0.7, 0.0), 0.0043, 2.9)]


def _scratches(g, pos, nrm, families, w_wide, w_core, cut):
    """(wide, core) masks of straight scratches: each family's scores `w_wide` wide (`w_core` at the
    bottom), kept where a noise along each score passes `cut` (higher: shorter, fewer)."""
    wide = core = None
    for across, along, pitch, sd in families:
        A, L = _unit(across), _unit(along)
        u = g.vec("DOT_PRODUCT", pos, A)
        u = g.add(u, g.mul(g.sub(g.noise(g.vec("ADD", pos, (sd, 0.0, 1.3)), 9.0, detail=1), 0.5), 0.003))
        v = g.vec("DOT_PRODUCT", pos, L)
        seg = g.noise(g.combine(g.mul(v, 1.0), g.mul(g.math("FLOOR", g.math("DIVIDE", u, pitch)), 0.37), sd), 12.0, detail=0)
        keep = g.mul(g.remap(seg, cut, cut + 0.03), g.remap(g.math("ABSOLUTE", g.vec("DOT_PRODUCT", nrm, A)), 0.75, 0.45))
        w = g.mul(g.lines(u, pitch, w_wide), keep)
        k = g.mul(g.lines(u, pitch, w_core), keep)
        wide = w if wide is None else g.math("MAXIMUM", wide, w)
        core = k if core is None else g.math("MAXIMUM", core, k)
    return wide, core


def _score(g, n, w):
    """A hairline where a noise crosses its middle, `w` wide in noise units."""
    return g.remap(g.math("ABSOLUTE", g.sub(n, 0.5)), w, 0.0)


def scav_paint(g, pal, marks=None, mark_col=None, cracks=()):
    """A scavenged plate repainted by hand: the paint (pal[0]) brushed over the old coat (pal[1], the
    Regime's bone white) on steel, slow mottling and brush marks, stencil stripes (MARKS, cream or
    `mark_col`); `cracks` [(centre, radius, seed)] split the coat in branching hairlines round an
    impact (ghost.py's mask). The coats are scored by
    long hairline scratches in three directions (most stop in the bone coat, the deepest reach the
    steel), flaked off in sparse impact patches and chipped along the edges: bone round bright steel.
    The scratched-out scripture is its own coat (`scratched`, laid on by `scratch_out`). All of it
    at least a few texels wide, so it holds at game resolution."""
    marks = MARKS if marks is None else marks
    paint, under, rough0 = pal[0], pal[1], pal[3]
    pos = g.geo("Position")
    x, y, z = g.xyz(pos)
    mottle = g.noise(pos, 6.0, detail=3)
    brush = g.noise(g.combine(x, y, g.mul(z, 0.12)), 120.0, detail=2)
    shade = g.add(g.remap(mottle, 0.3, 0.7, 0.93, 1.05, smooth=False), g.mul(g.sub(brush, 0.5), 0.07))
    tone = g.rgb(shade, shade, shade)
    col = g.mix(1.0, paint, tone, "MULTIPLY")
    mark = _marks(g, pos, marks)
    col = g.mix(mark, col, g.mix(1.0, mark_col or PAINT["cream"], tone, "MULTIPLY"))
    peel = g.noise(pos, 110.0, detail=2, rough=0.45)
    # Scratches: sparse straight scores in three directions, most stopping in the old coat, the
    # deepest reaching the steel.
    nrm = g.geo("Normal")
    wide, core = _scratches(g, pos, nrm, FAMILIES, 0.0008, 0.0003, 0.64)
    where = g.remap(g.noise(pos, 3.5, detail=2), 0.46, 0.6)
    deep = g.remap(g.noise(g.vec("ADD", pos, (2.0, 0.5, 1.1)), 3.0, detail=2), 0.5, 0.62)
    to_primer = g.mul(wide, where)
    to_steel = g.mul(g.mul(core, where), deep)
    # Impact flakes and edge chips.
    flake = g.noise(g.vec("ADD", pos, (1.3, 2.9, 0.4)), 9.0, detail=5, rough=0.62)
    edge = g.edge(0.003)
    chip_n = g.noise(pos, 120.0, detail=5)
    hollow = g.remap(g.ao(0.02), 0.8, 0.95)
    to_primer = g.math("MAXIMUM", to_primer, g.remap(flake, 0.69, 0.70))
    to_steel = g.math("MAXIMUM", to_steel, g.remap(flake, 0.725, 0.735))
    to_primer = g.math("MAXIMUM", to_primer, g.mul(g.mul(edge, g.remap(chip_n, 0.4, 0.5)), hollow))
    to_steel = g.math("MAXIMUM", to_steel, g.mul(g.mul(edge, g.remap(chip_n, 0.5, 0.58)), hollow))
    grind = g.math("MAXIMUM", g.noise(g.combine(g.mul(x, 0.05), y, z), 600.0, detail=2),
                   g.noise(g.combine(x, g.mul(y, 0.05), g.add(z, 0.7)), 600.0, detail=2))
    primer = g.mix(1.0, under, tone, "MULTIPLY")
    gs = g.remap(grind, 0.3, 0.75, 0.82, 1.1, smooth=False)
    steel = g.mix(1.0, STEEL, g.rgb(gs, gs, gs), "MULTIPLY")
    col = g.mix(to_primer, col, primer)
    col = g.mix(to_steel, col, steel)
    metal = to_steel
    rough = g.lerp(peel, rough0 - 0.05, rough0 + 0.04)
    rough = g.lerp(to_primer, rough, 0.5)
    rough = g.lerp(to_steel, rough, g.lerp(grind, 0.28, 0.42))
    h = g.add(g.mul(peel, 0.15), g.mul(mark, 0.08))
    h = g.sub(g.add(h, 0.62), g.add(g.mul(to_primer, 0.3), g.mul(to_steel, 0.3)))
    h = g.sub(h, g.mul(g.mul(grind, to_steel), 0.06))
    if cracks:
        cr = None
        for cc, r, sd in cracks:
            q = g.vec("ADD", pos, (sd, sd * 1.7, sd * 0.6))
            dist = g.vec("DISTANCE", pos, tuple(cc))
            n1 = g.noise(q, 30.0, detail=3, rough=0.55, distort=0.6)
            n2 = g.noise(g.vec("ADD", q, (3.1, 0.7, 1.9)), 58.0, detail=2, rough=0.5, distort=0.4)
            line = g.math("MAXIMUM", g.mul(_score(g, n1, 0.024), g.remap(dist, r, r * 0.3)),
                          g.mul(_score(g, n2, 0.018), g.remap(dist, r * 0.6, r * 0.15)))
            cr = line if cr is None else g.math("MAXIMUM", cr, line)
        col = g.mix(cr, col, INK)
        metal = g.mul(metal, g.sub(1.0, cr))
        rough = g.lerp(cr, rough, 0.85)
        h = g.sub(h, g.mul(cr, 0.45))
    return dict(color=col, rough=rough, metal=metal, height=h, bump=0.0002)


def scratched(g, pal):
    """Scripture scratched out of a painted plate: the paint (pal[0]) scuffed thin toward the old coat
    (pal[1]) and cut by a hatch of knife scratches in every direction, the coat at their shoulders
    and bright steel at the bottom, specks of the old black ink left in it."""
    paint, under, rough0 = pal[0], pal[1], pal[3]
    pos = g.geo("Position")
    x, y, z = g.xyz(pos)
    mottle = g.noise(pos, 6.0, detail=3)
    shade = g.remap(mottle, 0.3, 0.7, 0.93, 1.05, smooth=False)
    tone = g.rgb(shade, shade, shade)
    primer = g.mix(1.0, under, tone, "MULTIPLY")
    col = g.mix(0.24, g.mix(1.0, paint, tone, "MULTIPLY"), primer)
    hatch, hcore = _scratches(g, pos, g.geo("Normal"), HATCH, 0.0008, 0.00035, 0.5)
    ink = g.remap(g.noise(pos, 75.0, detail=3), 0.67, 0.71)
    grind = g.noise(g.combine(g.mul(x, 0.05), y, z), 600.0, detail=2)
    gs = g.remap(grind, 0.3, 0.75, 0.82, 1.1, smooth=False)
    col = g.mix(hatch, col, primer)
    col = g.mix(hcore, col, g.mix(1.0, STEEL, g.rgb(gs, gs, gs), "MULTIPLY"))
    col = g.mix(g.mul(ink, 0.85), col, INK)
    metal = g.mul(hcore, g.sub(1.0, ink))
    rough = g.lerp(hatch, rough0 + 0.1, 0.5)
    rough = g.lerp(hcore, rough, 0.34)
    h = g.sub(0.66, g.add(g.mul(hatch, 0.3), g.mul(hcore, 0.3)))
    return dict(color=col, rough=rough, metal=metal, height=h, bump=0.0002)


surfaces.RECIPES.setdefault("scavpaint", scav_paint)
surfaces.RECIPES.setdefault("scratched", scratched)
for _k in ("brk_clay", "brk_slate"):
    surfaces.RECIPE.setdefault(_k, "scavpaint")
    kit.hs.PALETTE.setdefault(_k + "_scr", kit.hs.PALETTE[_k][:3] + (kit.hs.PALETTE[_k][3] + 0.06, 0.0, 0))
    surfaces.RECIPE.setdefault(_k + "_scr", "scratched")
PLATE, PLATE2 = "brk_clay", "brk_slate"


def scratch_out(arm, obj, pts, r, kind, seed=1, step=0.0045):
    """Scripture scratched out of a painted plate: a ragged band 2r wide along the surface points `pts`
    (a single point: a disc of radius r), laid on `obj` as flat tiles in the scratched coat of the
    plate's `kind` ("<kind>_scr") and baked from detail with the Armour `arm`."""
    import random
    tree = reg.bvh(obj)
    rnd = random.Random(seed)
    bm = bmesh.new()

    def tile(p, along, w, h):
        loc, n, _, _ = tree.find_nearest(Vector(p))
        if loc is None:
            return
        n = n.normalized()
        u = along - n * along.dot(n)
        if u.length < 1e-6:
            return
        u.normalize()
        v = n.cross(u)
        base = loc + n * 0.00025
        bm.faces.new([bm.verts.new(base + u * (sx * w / 2) + v * (sy * h / 2)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    pts = [Vector(p) for p in pts]
    if len(pts) == 1:
        c0 = pts[0]
        _, n0, _, _ = tree.find_nearest(c0)
        u0 = n0.cross(Vector((0, 0, 1)) if abs(n0.z) < 0.9 else Vector((1, 0, 0))).normalized()
        v0 = n0.cross(u0)
        k = int(r / step) + 1
        for i in range(-k, k + 1):
            for j in range(-k, k + 1):
                q = u0 * (i * step) + v0 * (j * step)
                if q.length < r * (0.82 + 0.3 * rnd.random()):
                    tile(c0 + q, u0, step * 1.5, step * 1.5)
    else:
        for a, b in zip(pts, pts[1:]):
            along = b - a
            m = max(1, int(along.length / step))
            for k in range(m + 1):
                p = a.lerp(b, k / m)
                _, n, _, _ = tree.find_nearest(p)
                side = n.cross(along).normalized()
                tile(p + side * ((rnd.random() - 0.5) * 0.35 * r), along, step * 1.45, 2 * r * (0.78 + 0.4 * rnd.random()))
    if not bm.faces:
        bm.free()
        return None
    o = kit.hs._obj("scratched", bm, kind + "_scr", 0.0)
    arm.highs.append(o)
    return o


def _steps(a, b, n):
    return [a + (b - a) * i / n for i in range(n + 1)]


def stripe(p, n, hw, ball=None, r=0.0, halves=()):
    MARKS.append((Vector(p).copy(), Vector(n).normalized(), hw, Vector(ball).copy() if ball is not None else None, r,
                  [(Vector(a).copy(), Vector(b).normalized()) for a, b in halves]))


# ------------------------------------------------------------------------------------ helpers

def _sm(x, a, b):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def hard(o, kind):
    """A part's material set to `kind` on every face ("cordura.primary" through real.mat)."""
    o.data.materials.clear()
    o.data.materials.append(real.mat(kind) if "." in kind else kit.mat(kind))
    for p in o.data.polygons:
        p.material_index = 0
    return o


BULK = {"chest": 0.013, "spine": 0.015, "hips": 0.010, "shoulder.L": 0.010, "shoulder.R": 0.010, "neck": 0.009,
        "upper_arm.L": 0.010, "upper_arm.R": 0.010, "upper_leg.L": 0.010, "upper_leg.R": 0.010}


def bulk_up(c, man, k=1.0, amounts=BULK):
    """A heavier build than the base body: the game skin pushed out along its normals, most on the
    belly and chest, less on the limbs, fading out down the forearms and shins (the gloved fists and
    the feet in their boots keep their shape). The skin weights blend across the joints, so the
    swell does too. Garments are cut from this skin, so they follow. (The sculpt copy is left: no
    skin shows, and the bake's rays reach it.)"""
    b = c.b
    me = man.low.data
    names = {g.index: g.name for g in man.low.vertex_groups}
    disp = []
    for v in me.vertices:
        amt = 0.0
        for g in v.groups:
            n = names[g.group]
            a = amounts.get(n)
            if a is None and n.startswith(("forearm", "lower_leg")):
                h, t = Vector(b.all[n][0]), Vector(b.all[n][1])
                s = (v.co - h).dot(t - h) / (t - h).length_squared
                a = 0.006 * (1 - _sm(s, 0.1, 0.7))
            amt += g.weight * (a or 0.0)
        disp.append(v.normal * (amt * k))
    for v, d in zip(me.vertices, disp):
        v.co += d
    me.update()
    man._tree = None


def glove_guards(c, man, gloves, guard="slate", tab="secondary", plate=None):
    """The Runner's armoured gloves: a grooved knuckle guard over each fist (or a painted `plate` kind),
    a cuff strap round the wrist with a pull tab."""
    b = c.b
    J = b.j
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
        g = kit.block("knuckle", (0, 0, 0), (0.076, 0.012, 0.026), plate or guard, bevel=0.003)
        kit.cut(g, *[kit.block("groove", (x, 0.0065, 0), (0.004, 0.004, 0.032), "steel", bevel=0) for x in (-0.019, 0.0, 0.019)])
        M = Matrix((T, back, Lh)).transposed().to_4x4()
        M.translation = loc + back * 0.006 - Lh * 0.004
        g.data.transform(M)
        if plate:
            hard(g, plate)
        c.rigid(g, "hand." + s)
        ax = J("hand." + s, 0.0) - J("forearm." + s, 0.0)
        cc = J("hand." + s, 0.0) - ax.normalized() * 0.022
        r = pmc._radius(tg, cc, ax)
        c.rigid(pmc.band("glove_cuff", cc, (r + 0.003, r * 0.82 + 0.003), 0.03, 0.004, "glove", axis=ax), "hand." + s)
        c.rigid(hard(kit.block("cuff_tab", cc + back * (r + 0.006), (0.02, 0.004, 0.028), "grey", bevel=0.0012), "webbing." + tab), "hand." + s)


def combat_shirt(c, man, lead, kind="primary", texel=1.2, ease_k=1.0):
    """The crew's combat shirt (as the Runner's): cut from the body, a knit mock collar and cuffs in
    one piece with it, draped by the cloth simulation in the idle carry. Returns (garment, neckline)."""
    b = c.b
    J, seg = b.j, kit.seg_dist
    armpit = b.at("armpit")
    neck = J("neck", 0.0)
    tuck = b.hip_z + 0.095
    waist = tuck - 0.03
    neckline = (Vector((0, 0, neck.z + 0.028)), Vector((0, -0.45, 1)).normalized())
    collar_top = (neckline[0] + Vector((0, 0, 0.03)), Vector((0, -0.25, 1)).normalized())
    tint = kind.split(".")[-1]

    def on_arm(p):
        return lead(p) in ARMS
    cuts = [collar_top]
    for s in ("L", "R"):
        e, w = J("forearm." + s, 0.0), J("forearm." + s, 1.0)
        cuts.append((e.lerp(w, 0.86), w - e, lambda p, e=e, w=w: on_arm(p) and seg(p, e, w + (w - e) * 0.6) < 0.09))
    cuts.append(((0, 0, waist), (0, 0, -1), lambda p: not on_arm(p)))

    def ease(p):
        if not on_arm(p) and p.z < armpit - 0.06:
            return (0.007 - 0.003 * float(real._smooth(tuck + 0.03 - p.z, 0.0, 0.03))) * ease_k
        a = min(seg(p, J("upper_arm." + s, 0.3), J("forearm." + s, 1.0)) for s in ("L", "R"))
        return (0.008 + 0.012 * max(0.0, min(1.0, (0.09 - a) / 0.03))) * ease_k

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
    shirt = real.garment(c, man, "shirt", kind, lambda p: lead(p) in TORSO | ARMS | THIGHS | {"neck"} and p.z > waist - 0.05,
                         cuts, ease=ease, pin=None if FAST else pin, slack=slack, bend=12.0, texel=texel,
                         trims=[("knit." + tint, lambda p: (above(neckline, p) and lead(p) not in ARMS) or cuff(p))])
    c.hide_under(shirt.low, 0.05, 2)
    return shirt, neckline


def combat_trousers(c, man, lead, kind="twill.primary", top=0.19, cargo=True, texel=1.0):
    """The crew's trousers (as the Runner's): waistband over the tucked shirt, bloused over the boot
    tops, cargo pockets with flaps. Returns (garment, belt height)."""
    b = c.b
    J = b.j
    top_z = b.hip_z + 0.095
    belt_z = b.hip_z + 0.07
    hem = b.sole + top - 0.03

    def t_ease(p):
        band = 0.003 * (1 - real._smooth(top_z - p.z, 0.02, 0.07))
        return 0.011 + band + 0.004 * real._smooth(top_z - p.z, 0.04, 0.2) + 0.007 * real._smooth(J("lower_leg.L", 0.0).z - p.z, 0.0, 0.15)

    def t_pin(p):
        return 1.0 if p.z > top_z - 0.045 or p.z < hem + 0.018 else 0.0

    def t_slack(p):
        return real._smooth(hem + 0.13 - p.z, 0.0, 0.1)
    trousers = real.garment(c, man, "trousers", kind, lambda p: lead(p) in LEGS | {"hips", "spine"} and hem - 0.03 < p.z < top_z + 0.03,
                            [((0, 0, top_z), (0, 0, 1)), ((0, 0, hem), (0, 0, -1), lambda p: lead(p) in LEGS)],
                            ease=t_ease, pin=None if FAST else t_pin, slack=t_slack, bend=14.0, texel=texel)
    c.hide_under(trousers.low, 0.06, 2)
    if cargo:
        for s, sx in (("L", 1), ("R", -1)):
            ul0, ul1 = J("upper_leg." + s, 0.0), J("upper_leg." + s, 1.0)
            around = pmc._limb(ul0, ul1)
            out = 96 * sx
            real.patch(c, trousers.low, "cargo", kind,
                       lambda p, around=around, out=out: (lambda t, a: 0.47 < t < 0.76 and abs((a - out + 180) % 360 - 180) < 34)(*around(p)),
                       lift=0.002, puff=0.013, thick=0.003)
            real.patch(c, trousers.low, "cargo_flap", kind,
                       lambda p, around=around, out=out: (lambda t, a: 0.445 < t < 0.53 and abs((a - out + 180) % 360 - 180) < 37)(*around(p)),
                       lift=0.016, puff=0.002, thick=0.003)
    return trousers, belt_z


def jump_kit(M, cover="pilotshell.accent", strap="webbing.secondary", scale=1.0, lamp=True):
    """The crew's jump kit (as on the Runner's back plate), built in a plate's frame M (pmc.frame: x
    across, -y out of the plate, z up, origin on its surface): a slate housing, a clay cover with
    vents, twin thrusters angled down and out, fuel cells across the top, a status lamp and two
    straps. Returns the parts, placed."""
    s = scale
    jd = 0.07 * s
    jo = -jd
    pack = kit.block("jump_pack", (0, -jd / 2, 0), (0.18 * s, jd, 0.165 * s), "slate", bevel=0.009)
    kit.cut(pack, *[kit.block("fin", (x * s, -jd / 2, -0.085 * s), (0.006, jd + 0.02, 0.03 * s), "steel", bevel=0) for x in (-0.03, -0.015, 0.0, 0.015, 0.03)])
    parts = [pack]
    cv = kit.block("jump_cover", (0, jo - 0.003, 0.018 * s), (0.158 * s, 0.012, 0.112 * s), "grey", bevel=0.004)
    kit.cut(cv, *[kit.block("vent", (0, jo - 0.009, (0.012 + k * 0.017) * s), (0.1 * s, 0.01, 0.0065), "steel", bevel=0) for k in (-1, 0, 1)])
    parts.append(hard(cv, cover))
    for sx in (1, -1):
        a = Vector((sx * 0.055 * s, -jd * 0.55, -0.069 * s))
        d = Vector((sx * 0.36, -0.14, -1)).normalized()
        e = a + d * 0.072 * s
        parts += [kit.cyl("thruster", a, e, 0.024 * s, "gunmetal", r1=0.031 * s, segs=18, bevel=0.0015),
                  kit.cyl("thruster_throat", e - d * 0.005, e + d * 0.0005, 0.027 * s, "black", segs=18, bevel=0.0),
                  kit.ring("thruster_ring", a + d * 0.022 * s, d, 0.0285 * s, 0.023 * s, 0.009, "steel", segs=18)]
    fy = -jd * 0.45
    fz = 0.098 * s
    parts += [kit.cyl("fuel_cell", (-0.082 * s, fy, fz), (0.082 * s, fy, fz), 0.017 * s, "gunmetal", segs=14, bevel=0.002),
              kit.cyl("fuel_cap", (-0.093 * s, fy, fz), (-0.082 * s, fy, fz), 0.013 * s, "black", segs=12, bevel=0.001),
              kit.cyl("fuel_cap", (0.082 * s, fy, fz), (0.093 * s, fy, fz), 0.013 * s, "black", segs=12, bevel=0.001)]
    if lamp:
        parts.append(kit.cyl("status", (0.058 * s, jo - 0.008, 0.06 * s), (0.058 * s, jo - 0.0115, 0.06 * s), 0.0042, "glow_amber", segs=10, bevel=0.0))
    for sx in (1, -1):
        parts.append(hard(kit.block("pack_strap", (sx * 0.094 * s, -jd / 2, 0), (0.022, jd + 0.004, 0.012), "webbing", bevel=0.0015), strap))
    for o in parts:
        o.data.transform(M)
    return parts


def grenade(at, up, out, body="gunmetal"):
    """A frag grenade standing upright: the rounded body, the fuse, the spoon down its outer side and
    the pull ring. Returns the parts."""
    up = Vector(up).normalized()
    out = Vector(out)
    out = (out - up * out.dot(up)).normalized()
    side = up.cross(out).normalized()
    at = Vector(at)
    top = at + up * 0.064
    parts = [kit.cyl("grenade", at, top, 0.028, body, segs=16, bevel=0.011),
             kit.cyl("grenade_fuse", top - up * 0.004, top + up * 0.016, 0.0095, "steel", segs=10, bevel=0.001, bsegs=1)]
    sp = kit.block("grenade_spoon", (0, 0, 0), (0.014, 0.0035, 0.05), "bright", bevel=0.0008)
    oriented(sp, top - up * 0.02 + out * 0.0285, side, out, up)
    parts.append(sp)
    lever = kit.block("grenade_lever", (0, 0, 0), (0.014, 0.024, 0.004), "bright", bevel=0.0006)
    oriented(lever, top + up * 0.014 + out * 0.017, side, out, up)
    parts.append(lever)
    parts.append(reg.ring("pin_ring", top + up * 0.007 + side * 0.017, out, 0.0105, 0.0075, 0.0022, "bright", segs=12))
    return parts


# ------------------------------------------------------------------------------------ helmet

def regime_helmet(c, man, arm):
    """The reworked Regime helmet: the Acolyte's bone shell (repainted clay, a cream stripe over the
    crown) and respirator faceplate (repainted slate), the red sensor slit cut open into a wide dark
    visor with a rubber gasket round it; the Runner's twin optic on the right and comms pod with a whip
    antenna on the left in place of the comms domes, the rear battery's strobe swapped for an amber
    lamp, the brow mount kept. The scripture's places are ground to steel. Returns (envelope, shell
    rim lat(lon), faceplate chin lat(lon))."""
    hc = man.head_center()
    dom = kit.dominant(man.low)
    me = man.low.data
    co = [v.co.copy() for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons if sum(dom[i] in ("head", "neck") for i in p.vertices) * 2 > len(p.vertices)]
    head = BVHTree.FromPolygons(co, polys)
    O = hc + Vector((0, -0.016, -0.018))
    env = reg.Env([head], O, reach=0.22, lat=(-80.0, 90.0), dlat=4.0, dlon=5.0, spread=14.0, blur=10.0, floor=0.006)
    BROW, VIS = 17.0, -3.0

    def rim(lo):
        a = abs(lo)
        side = -38.0 + 5.0 * _sm(a, 110, 180)
        return BROW + (side - BROW) * _sm(a, 58, 76)

    def chin(lo):
        return -57.0 + 17.0 * _sm(abs(lo), 0, 82)

    def mtop(lo):
        return VIS + (BROW - 2.0 - VIS) * _sm(abs(lo), 54, 70)

    SHELL = 0.0145

    def mask_off(la, lo):
        keel = 0.0034 * math.exp(-(lo / 5.0) ** 2) * _sm(VIS - la, 2.0, 14.0)
        snout = 0.0105 * math.exp(-((la + 30.0) / 17.0) ** 2 - (lo / 30.0) ** 2)
        return 0.0215 + keel + snout

    shell = env.patch("helmet", PLATE, -180.0, 180.0, rim, lambda lo: 86.0, SHELL, 0.006, nu=56, nv=14, closed=True, pole=True,
                      inner="regime_pad", bevel=0.0018)
    mask = env.patch("faceplate", PLATE2, -82.0, 82.0, chin, mtop, mask_off, 0.0065, nu=30, nv=11, inner="regime_pad", bevel=0.0018)
    visor = env.patch("visor", "glass", -74.0, 74.0, lambda lo: VIS - 4.0, lambda lo: BROW + 3.0, 0.0086, 0.002, nu=26, nv=4, bevel=0.0)
    c.rigid(visor, "head")
    arm.add(shell, "head")
    arm.add(mask, "head")
    # The rubber gasket round the cut-open visor: under the shell's brow and along the faceplate's top.
    lo1 = 63.0
    brow = [env.P(rim(lo) - 0.6, lo, SHELL - 0.0025) for lo in pmc_steps(-lo1, lo1, 4.0)]
    c.rigid(tube("visor_gasket", relax(brow, 1, closed=False), 0.0028, "rubber", segs=6), "head")
    low = [env.P(mtop(lo) + 0.6, lo, mask_off(mtop(lo), lo) - 0.003) for lo in pmc_steps(-lo1, lo1, 4.0)]
    c.rigid(tube("visor_gasket", relax(low, 1, closed=False), 0.0028, "rubber", segs=6), "head")

    # Where the scripture was: the sigil and code at the back, code on the temples, ticks on the jaw.
    scratch_out(arm, shell, [env.P(28, 180, SHELL)], 0.026, PLATE, seed=11)
    for la in (6.0, 1.0):
        scratch_out(arm, shell, [env.P(la, lo, SHELL) for lo in _steps(156, 204, 4)], 0.0055, PLATE, seed=int(la) + 3)
    for sx in (1, -1):
        for la, l1 in ((31.0, 70), (26.5, 66), (22.0, 70)):
            scratch_out(arm, shell, [env.P(la, sx * lo, SHELL) for lo in _steps(50, l1, 2)], 0.0052, PLATE, seed=int(la * sx))
        for la in (-19.0, -24.5):
            scratch_out(arm, mask, [env.P(la, sx * lo, mask_off(la, sx * lo)) for lo in _steps(52, 68, 2)], 0.0048, PLATE2, seed=int(la * sx) + 50)
    # The crew's stripe over the crown, from the brow to the nape.
    top = env.P(BROW + 1.0, 0, SHELL)
    stripe(O, (1, 0, 0), 0.012, O + Vector((0, 0.01, 0.02)), 0.2, [(top, (0, 0.6, 1))])

    # Fasteners on the faceplate (baked detail), as the Acolyte's.
    for sx in (1, -1):
        for la, lo in ((-6, sx * 74), (-34, sx * 70)):
            arm.detail(reg.screw(env.P(la, lo, mask_off(la, lo)), env.normal(la, lo, mask_off(la, lo)), r=0.0034))
    # Respirator vents either side of the snout.
    for sx in (1, -1):
        a0, a1 = sorted((sx * 17.0, sx * 38.0))
        c.rigid(env.patch("vent", "black", a0, a1, lambda lo: -40.0, lambda lo: -20.0, lambda la, lo: mask_off(la, lo) + 0.0012, 0.003,
                          nu=6, nv=4, bevel=0.0008, segs=1), "head")
        for k in range(4):
            la0 = -37.0 + k * 4.6
            c.rigid(env.patch("vent_slat", "gunmetal", a0 + 1.5, a1 - 1.5, lambda lo, la0=la0: la0, lambda lo, la0=la0: la0 + 1.6,
                              lambda la, lo: mask_off(la, lo) + 0.0028, 0.0018, nu=5, nv=1, bevel=0.0), "head")
    # Side rails kept.
    for sx in (1, -1):
        a0, a1 = sorted((sx * 118.0, sx * 152.0))
        c.rigid(env.patch("rail", "black", a0, a1, lambda lo: -3.0 + 0.04 * (abs(lo) - 96), lambda lo: 4.5 + 0.04 * (abs(lo) - 96),
                          SHELL + 0.0055, 0.0055, nu=8, nv=1, bevel=0.0012, segs=1), "head")
    # Twin optic on the right side, facing forward (the Runner's).
    la, lo = 2.0, -100.0
    p, n = env.P(la, lo, SHELL), env.normal(la, lo, SHELL)
    t, n, zz = basis(n)
    c.rigid(oriented(kit.block("optic", (0, 0, 0), (0.05, 0.022, 0.034), "slate", bevel=0.004), p + n * 0.009 + t * 0.006, t, n, zz), "head")
    for dz in (0.008, -0.008):
        q = p + n * 0.011 + t * 0.031 + zz * dz
        c.rigid(kit.cyl("optic_lens", q - t * 0.003, q + t * 0.004, 0.0072, "gunmetal", segs=14, bevel=0.0008), "head")
        c.rigid(kit.cyl("optic_glass", q + t * 0.0035, q + t * 0.0048, 0.0052, "glass", segs=14, bevel=0.0), "head")
    c.rigid(kit.cyl("optic_led", p + n * 0.0205 - t * 0.012 + zz * 0.01, p + n * 0.0222 - t * 0.012 + zz * 0.01, 0.0026, "glow_amber", segs=8, bevel=0.0), "head")
    # Comms pod on the left with a whip antenna back over the crown (the Runner's).
    la, lo = -8.0, 100.0
    p, n = env.P(la, lo, SHELL), env.normal(la, lo, SHELL)
    t, n, zz = basis(n)
    c.rigid(kit.cyl("comms", p - n * 0.003, p + n * 0.012, 0.03, "slate", segs=20, bevel=0.002), "head")
    c.rigid(kit.cyl("comms_cap", p + n * 0.012, p + n * 0.016, 0.021, "gunmetal", segs=20, bevel=0.0012), "head")
    for dz in (-0.009, 0.0, 0.009):
        c.rigid(oriented(kit.block("comms_grille", (0, 0, 0), (0.024, 0.0016, 0.0035), "black", bevel=0.0), p + n * 0.0165 + zz * dz, t, n, zz), "head")
    base = p + n * 0.008 + zz * 0.026 - t * 0.01
    c.rigid(kit.cyl("antenna_base", base - zz * 0.004, base + zz * 0.01, 0.0055, "black", segs=10, bevel=0.001), "head")
    tip = base + (zz * 0.75 - t * 0.66).normalized() * 0.15
    c.rigid(kit.cyl("antenna", base + zz * 0.008, tip, 0.0024, "rubber", r1=0.0015, segs=6, bevel=0.0), "head")
    # Rear battery module (the Regime's), an amber lamp in place of the strobe.
    n = env.normal(6, 180, SHELL)
    M = pmc.frame(env.P(6, 180, SHELL) + n * 0.014, n, (0, 0, 1))
    for o_ in (kit.block("battery", (0, 0, 0), (0.074, 0.03, 0.046), "black", bevel=0.005),
               kit.block("battery_lid", (0, -0.016, 0.004), (0.06, 0.004, 0.03), "gunmetal", bevel=0.0012),
               kit.cyl("battery_lamp", (0.0, -0.012, 0.026), (0.0, -0.012, 0.031), 0.008, "glow_amber", segs=10, bevel=0)):
        o_.data.transform(M)
        c.rigid(o_, "head")
    # The brow mount.
    n = env.normal(33, 0, SHELL)
    M = pmc.frame(env.P(33, 0, SHELL) + n * 0.004, n, (0, 0, 1))
    for o_ in (kit.block("shroud", (0, 0, 0), (0.05, 0.009, 0.032), "gunmetal", bevel=0.002, taper=(0.8, 1.0)),
               kit.block("shroud_slot", (0, -0.006, -0.002), (0.022, 0.006, 0.012), "black", bevel=0.001)):
        o_.data.transform(M)
        c.rigid(o_, "head")
    return env, rim, chin


def pmc_steps(a, b, step):
    n = max(2, int(round((b - a) / step)))
    return [a + (b - a) * i / n for i in range(n + 1)]


# ------------------------------------------------------------------------------------ build

def build():
    del MARKS[:]
    b = real.Anatomy(height=1.86, width=1.08, body="male", sole=0.036, stance=0.25, arm_hang=11.0)
    c = real.begin("breaker", b)
    man = real.body(c, stubble=0.0, face_detail=1.0)
    bulk_up(c, man)
    surfaces._TEXEL_FN[man.low.name] = lambda obj: (lambda isl: 0.3)   # no skin shows
    J = b.j
    lead = real.bones_at(man)
    armpit = b.at("armpit")
    WX = 1.1   # the plates' layout widened for the broad torso
    head_arm = reg.Armour(c, "armour_head", texel=2.6)
    torso_arm = reg.Armour(c, "armour_torso", texel=2.4)
    arm_arm = reg.Armour(c, "armour_arms", texel=2.2)
    leg_arm = reg.Armour(c, "armour_legs", texel=2.2)

    # ---------------------------------------------------------------- helmet (the head goes under it)
    for e in man.eyes:
        c.parts = [p for p in c.parts if p[0] is not e]
    env, rim, chin = regime_helmet(c, man, head_arm)
    for e in man.eyes:
        bpy.data.objects.remove(e, do_unlink=True)
    c.cover({"head"})

    # ---------------------------------------------------------------- gloves
    gloves = real.gloves(c, man, "glove", cuff=0.07)
    glove_guards(c, man, gloves, plate=PLATE2)

    # ---------------------------------------------------------------- suit and hood
    shirt, neckline = combat_shirt(c, man, lead, "primary", texel=1.0)
    tshirt = pmc.tree(shirt.low)

    def hood_top(lo):
        return (chin(lo) if abs(lo) < 82 else rim(lo)) + 5.0

    def in_hood(p):
        if lead(p) not in ("head", "neck") or (Vector(p) - neckline[0]).dot(neckline[1]) < -0.025:
            return False
        d = Vector(p) - env.O
        la = math.degrees(math.asin(max(-1.0, min(1.0, d.normalized().dot(env.Z)))))
        lo = math.degrees(math.atan2(d.dot(env.S), d.dot(env.F)))
        return la < hood_top(lo)
    hood = real.layer(c, man, "hood", "knit.primary", in_hood, [], ease=0.004, smooth=1, texel=0.8, seams="hems")
    c.hide_under(hood, 0.02, 1)

    trousers, belt_z = combat_trousers(c, man, lead, "twill.primary", top=0.2)
    tt = pmc.tree(trousers.low)

    # ---------------------------------------------------------------- plate carrier and breastplate
    dz = (armpit - 0.198) - 1.03

    def Z(z):
        return z + dz

    def X(x):
        return x * WX
    f_cover = kit.rounded([(X(-0.13), Z(1.10)), (X(0.13), Z(1.10)), (X(0.13), Z(1.29)), (X(0.08), Z(1.382)), (X(-0.08), Z(1.382)), (X(-0.13), Z(1.29))], 0.022)
    f_plate = kit.rounded([(X(-0.124), Z(1.108)), (X(0.124), Z(1.108)), (X(0.126), Z(1.29)), (X(0.074), Z(1.376)), (X(0.03), Z(1.388)),
                           (X(-0.03), Z(1.388)), (X(-0.074), Z(1.376)), (X(-0.126), Z(1.29))], 0.018)
    pf = reg.Plate([tshirt], f_cover, -1, 0.008)
    c.rigid(hard(pf.patch("carrier_front", "grey", f_cover, 0.022, 0.022, nu=16, nv=12, bevel=0.005), "cordura.primary"), "chest")
    PO = 0.037   # the breastplate's outer surface over the fitted surface
    fp = pf.patch("chest_plate", PLATE, f_plate, PO, 0.014, nu=18, nv=14, bevel=0.0035)
    torso_arm.add(fp, "chest")
    for x, z in ((X(-0.104), Z(1.14)), (X(0.104), Z(1.14)), (X(-0.1), Z(1.29)), (X(0.1), Z(1.29))):
        torso_arm.detail(reg.screw(pf.P(x, z, PO), pf.normal(x, z), r=0.0045))
    # The scripture's places on the breasts, the sigil and the barcode.
    for sx in (1, -1):
        for zz, x1 in ((1.318, 0.098), (1.299, 0.084), (1.28, 0.092)):
            scratch_out(torso_arm, fp, [pf.P(X(sx * x), Z(zz), PO) for x in _steps(0.028, x1, 2)], 0.0058, PLATE, seed=int(zz * 1000) * sx)
    scratch_out(torso_arm, fp, [pf.P(0.0, Z(1.215), PO)], 0.024, PLATE, seed=7)
    # Two cream stripes slanting down over the right breast.
    for k in (0.0, 0.032):
        p = pf.P(X(-0.07), Z(1.31), PO) + Vector((0.8, 0, 0.6)).normalized() * k
        stripe(p, (0.8, 0, 0.6), 0.0095, pf.P(X(-0.07), Z(1.30), PO), 0.075, [(pf.P(0, Z(1.3), PO - 0.03), (0, -1, 0))])
    # The placard: three frag grenades in clay pouches along the bottom of the plate.
    for x in (-0.072, 0.0, 0.072):
        M = pf.frame(X(x), Z(1.168), PO)
        objs = [hard(kit.block("grenade_pouch", (0, -0.03, -0.012), (0.066, 0.06, 0.072), "grey", bevel=0.006), "cordura.accent"),
                hard(kit.block("pouch_rim", (0, -0.03, 0.024), (0.07, 0.064, 0.008), "grey", bevel=0.003), "cordura.accent"),
                kit.block("bungee", (0, -0.062, 0.026), (0.072, 0.004, 0.006), "black", bevel=0.0012)]
        for o in objs:
            o.data.transform(M)
            c.rigid(o, "chest")
        at = M @ Vector((0, -0.03, 0.0))
        up = (M.to_3x3() @ Vector((0, 0, 1))).normalized()
        out = (M.to_3x3() @ Vector((0, -1, 0))).normalized()
        for o in grenade(at, up, out):
            c.rigid(o, "chest")

    # Belly lames: two slate plates shingled down from under the carrier, over the shirt.
    for i, (z0, z1, off) in enumerate(((Z(1.035), Z(1.118), 0.018), (Z(0.975), Z(1.05), 0.024))):
        ol = kit.rounded([(X(-0.118), z0), (X(0.118), z0), (X(0.122), z1), (X(-0.122), z1)], 0.016)
        pl = reg.Plate([tshirt], ol, -1, 0.006)
        lame = pl.patch("belly_lame", PLATE2, ol, off, 0.009, nu=14, nv=4, bevel=0.0025)
        torso_arm.add(lame, "spine")
        for x in (-0.095, 0.095):
            torso_arm.detail(reg.screw(pl.P(X(x), (z0 + z1) / 2, off), pl.normal(X(x), (z0 + z1) / 2), r=0.0036))
        scratch_out(torso_arm, lame, [pl.P(X(x), (z0 + z1) / 2, off) for x in _steps(-0.07, 0.07, 3)], 0.0062, PLATE2, seed=20 + i)

    # The back: carrier, back plate and the jump kit on it.
    b_cover = kit.rounded([(X(-0.132), Z(1.03)), (X(0.132), Z(1.03)), (X(0.132), Z(1.29)), (X(0.104), Z(1.365)), (X(-0.104), Z(1.365)), (X(-0.132), Z(1.29))], 0.025)
    b_plate = kit.rounded([(X(-0.122), Z(1.042)), (X(0.122), Z(1.042)), (X(0.122), Z(1.286)), (X(0.094), Z(1.353)), (X(-0.094), Z(1.353)), (X(-0.122), Z(1.286))], 0.02)
    pb = reg.Plate([tshirt], b_cover, 1, 0.008)
    c.rigid(hard(pb.patch("carrier_back", "grey", b_cover, 0.022, 0.022, nu=16, nv=12, bevel=0.005), "cordura.primary"), "chest")
    bp = pb.patch("back_plate", PLATE, b_plate, 0.035, 0.012, nu=18, nv=14, bevel=0.003)
    torso_arm.add(bp, "chest")
    for zz in (1.335, 1.317):
        scratch_out(torso_arm, bp, [pb.P(X(x), Z(zz), 0.035) for x in _steps(-0.085, 0.085, 4)], 0.0055, PLATE, seed=int(zz * 1000))
    Mb = pb.frame(0.0, Z(1.17), 0.035)
    jk = jump_kit(Mb, scale=1.08)
    for o in jk:
        c.rigid(o, "chest")
    handle = pmc.sweep("drag_handle", pmc.smooth_path([Mb @ Vector(p) for p in ((-0.04, 0.004, 0.155), (-0.032, -0.018, 0.19), (0.032, -0.018, 0.19),
                                                                                (0.04, 0.004, 0.155))], 4),
                       0.026, 0.005, "webbing", lambda q: Mb.to_3x3() @ Vector((0, -1, 0)))
    c.rigid(hard(handle, "webbing.secondary"), "chest")

    # Padded shoulder straps (cream) with buckles, a PTT on the left one.
    for s, sx in (("L", 1), ("R", -1)):
        xs = sx * 0.088
        pts = []
        for y in (-0.13, -0.10, -0.07, -0.04, -0.01, 0.02, 0.05, 0.08, 0.11, 0.13):
            loc, _ = pmc.hit(tshirt, (xs, y, 1.95), (0, 0, -1))
            zz = loc.z + 0.009 if loc and loc.z > armpit + 0.05 else Z(1.37)
            pts.append((xs, y, zz))
        pts[0] = pf.P(sx * 0.077, Z(1.37), 0.012)
        pts[-1] = pb.P(sx * 0.085, Z(1.348), 0.012)
        path = pmc.smooth_path(pts, 3)
        nrm = pmc.radial((sx * 0.088, 0, Z(1.33)), (1, 0, 0))
        c.rigid(hard(pmc.sweep("shoulder_strap", path, 0.054, 0.014, "grey", nrm), "cordura.secondary"), "chest")
        k = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.07))
        tan = (path[k + 1] - path[k - 1]).normalized()
        nn = nrm(path[k]).normalized()
        c.rigid(pmc.side_buckle("strap_buckle", path[k] + nn * 0.0095, -tan, nn, w=0.042), "chest")
        if s == "L":
            k2 = min(range(1, len(path) - 1), key=lambda i: abs(path[i].y + 0.035))
            t2 = (path[k2 + 1] - path[k2 - 1]).normalized()
            n2 = nrm(path[k2]).normalized()
            Mp = pmc.frame(path[k2] + n2 * 0.007, n2, t2)
            ptt = [kit.block("ptt", (0, -0.009, 0), (0.034, 0.018, 0.042), "black", bevel=0.003),
                   hard(kit.cyl("ptt_button", (0, -0.017, 0.004), (0, -0.023, 0.004), 0.009, "grey", segs=14, bevel=0.0015), "pilotshell.accent")]
            pmc.put(ptt, Mp)
            pmc.rigid_all(c, ptt, "chest")
    # Cummerbund from under the front plate round to the back.
    for s, sx in (("L", 1), ("R", -1)):
        for zc, w in ((Z(1.075), 0.06), (Z(1.15), 0.06)):
            pts = pmc._ring_side(tshirt, (0, -0.004), zc, 0.012, sx * 46, sx * 136)
            c.rigid(hard(pmc.sweep("cummerbund", pmc.smooth_path(pts, 3), w, 0.013, "grey", pmc.radial((0, -0.004, 0))), "cordura.primary"), "chest")
        side = pmc._ring_side(tshirt, (0, -0.004), Z(1.11), 0.027, sx * 90, sx * 90, n=2)[0]
        c.rigid(kit.block("cb_tab", side, (0.012, 0.03, 0.11), "black", bevel=0.003), "chest")

    # ---------------------------------------------------------------- arms: shoulder plates, vambraces
    for s, sx in (("L", 1), ("R", -1)):
        ua, fa = "upper_arm." + s, "forearm." + s
        ua0, ua1 = J(ua, 0.0), J(ua, 1.0)
        sleeve = reg.region_tree(shirt.low, {ua, "shoulder." + s})
        tu = reg.Tube([sleeve], ua0, ua1, front=(0, -1, 0), t=(0.1, 0.8), nt=24, nphi=48, reach=0.15, spread=0.03, blur=0.02)
        lame1 = tu.patch("shoulder_lame", PLATE2, 0.22, 0.44, 90 * sx, 68, 0.0075, 0.006, nu=10, nv=3, corner=2.5, bevel=0.002)
        lame2 = tu.patch("shoulder_lame", PLATE2, 0.38, 0.58, 90 * sx, 64, 0.0075, 0.006, nu=10, nv=3, corner=2.5, bevel=0.002)
        arm_arm.add(lame2, ua)
        arm_arm.add(lame1, ua)
        O = ua0 + Vector((-sx * 0.012, 0.0, -0.012))
        cap_env = reg.Env([sleeve, lame1, lame2], O, Z=(sx * 0.6, 0.0, 0.8), F=(0, -sx, 0), reach=0.17, lat=(-40.0, 90.0), dlat=4.0, dlon=6.0,
                          spread=9.0, blur=7.0, floor=0.003)

        def cap_rim(lo):
            sn = math.sin(math.radians(lo))
            return 32.0 - 63.0 * max(0.0, sn) ** 1.3 + 7.0 * max(0.0, -sn)
        cap = cap_env.patch("shoulder_cap", PLATE, -180.0, 180.0, cap_rim, lambda lo: 84.0, 0.0115, 0.0075, nu=36, nv=10, closed=True, pole=True,
                            inner="regime_pad", bevel=0.0025)
        arm_arm.add(cap, ua)
        scratch_out(arm_arm, cap, [cap_env.P(40, 90, 0.0115)], 0.028, PLATE, seed=30 + sx)
        scratch_out(arm_arm, lame1, [tu.P(0.33, 90 * sx + k, 0.0075) for k in _steps(-28, 28, 4)], 0.0058, PLATE2, seed=33 + sx)
        for lo in (-40, -140):
            la = cap_rim(lo) + 7
            arm_arm.detail(reg.screw(cap_env.P(la, lo, 0.0115), cap_env.normal(la, lo, 0.0115), r=0.0036))
        if s == "L":
            # A cream band round the outside of the left cap.
            A = (ua1 - ua0).normalized()
            stripe(ua0 - A * 0.015, A, 0.011, ua0, 0.13, [(ua0 + Vector((-0.005, 0, 0)), (1, 0, 0))])
        tu2 = reg.Tube([sleeve], ua0, ua1, hard=[lame1, lame2], t=(0.3, 0.62), nt=8, nphi=36, reach=0.15)
        c.rigid(reg.strap_ring("arm_strap", tu2.ring(0.5, 0.0015, n=20), ua0.lerp(ua1, 0.5), ua1 - ua0, 0.022, 0.004, "webbing"), ua)
        # Elbow pad and the vambrace: a clay plate over the outside of the forearm on two straps.
        fa0, fa1 = J(fa, 0.0), J(fa, 1.0)
        ax = (fa1 - fa0).normalized()
        r = pmc._radius(tshirt, fa0 + ax * 0.01, ax) + 0.003
        c.rigid(pmc.wrap("elbow_pad", fa0 - ax * 0.03, fa0 + ax * 0.055, r, r - 0.005, 180 - 55 * sx, 180 + 55 * sx, 0.009, "black",
                         nt=4, nphi=8, bevel=0.003, bulge=0.004, fit=(tshirt, 0.0025)), fa)
        fsleeve = reg.region_tree(shirt.low, {fa})
        tf = reg.Tube([fsleeve], fa0, fa1, front=(0, -1, 0), t=(0.05, 0.9), nt=20, nphi=40, reach=0.13, spread=0.025, blur=0.018)
        vam = tf.patch("vambrace", PLATE, 0.16, 0.74, 70 * sx, 72, 0.0085, 0.0065, nu=10, nv=6, corner=3.0, bulge=0.003, bevel=0.0022)
        arm_arm.add(vam, fa)
        scratch_out(arm_arm, vam, [tf.P(t, 70 * sx, 0.0085) for t in _steps(0.3, 0.62, 4)], 0.0058, PLATE, seed=40 + sx)
        for tq in (0.2, 0.7):
            arm_arm.detail(reg.screw(tf.P(tq, 70 * sx, 0.0085), tf.d(70 * sx), r=0.0032))
        tf2 = reg.Tube([fsleeve], fa0, fa1, hard=[vam], t=(0.2, 0.75), nt=8, nphi=36, reach=0.13)
        for tq in (0.3, 0.62):
            c.rigid(reg.strap_ring("vambrace_strap", tf2.ring(tq, 0.0015, n=20), fa0.lerp(fa1, tq), fa1 - fa0, 0.02, 0.004, "webbing"), fa)

    # ---------------------------------------------------------------- battle belt
    belt_pad = pmc.sweep("battle_belt", pmc.ring_pts(tt, (0, -0.005), belt_z, 0.006, n=32), 0.062, 0.012, "grey", pmc.radial((0, -0.005, 0)), closed=True)
    c.add(hard(belt_pad, "cordura.primary"), ["hips", "spine", "upper_leg.L", "upper_leg.R"])
    belt = pmc.sweep("belt", pmc.ring_pts(tt, (0, -0.005), belt_z, 0.014, n=32), 0.045, 0.006, "grey", pmc.radial((0, -0.005, 0)), closed=True)
    c.add(hard(belt, "webbing.secondary"), ["hips", "spine", "upper_leg.L", "upper_leg.R"])
    loc, _ = pmc.hit(tt, (0, -0.5, belt_z), (0, 1, 0))
    bk = kit.block("buckle", (0, 0, 0), (0.066, 0.013, 0.042), "gunmetal", bevel=0.003)
    kit.cut(bk, kit.block("buckle_slot", (0, -0.007, 0), (0.046, 0.006, 0.022), "steel", bevel=0))
    bk.data.transform(Matrix.Translation(Vector((0, loc.y - 0.024, belt_z))))
    c.rigid(bk, "hips")
    # Two more grenades on the back of each hip.
    for s, sx in (("L", 1), ("R", -1)):
        for ang in (118, 142):
            a = math.radians(ang)
            d = Vector((sx * math.sin(a), -math.cos(a), 0))
            loc, _ = pmc.hit(tt, (0, -0.005, belt_z), d)
            if loc is None:
                continue
            M = pmc.frame(loc + d * 0.018, d, (0, 0, 1))
            pouch = [hard(kit.block("grenade_pouch", (0, -0.03, -0.022), (0.064, 0.06, 0.07), "grey", bevel=0.006), "cordura.accent"),
                     hard(kit.block("pouch_rim", (0, -0.03, 0.012), (0.068, 0.064, 0.008), "grey", bevel=0.003), "cordura.accent")]
            for o in pouch:
                o.data.transform(M)
                c.rigid(o, "hips")
            for o in grenade(M @ Vector((0, -0.03, -0.01)), (0, 0, 1), d):
                c.rigid(o, "hips")

    # ---------------------------------------------------------------- leg armour
    for s, sx in (("L", 1), ("R", -1)):
        ul, ll = "upper_leg." + s, "lower_leg." + s
        ul0, ul1 = J(ul, 0.0), J(ul, 1.0)
        ll0, ll1 = J(ll, 0.0), J(ll, 1.0)
        tu = reg.Tube([tt], ul0, ul1, t=(-0.05, 0.62), nt=28, nphi=60, reach=0.17, spread=0.03, blur=0.022)
        thigh = tu.patch("thigh_guard", PLATE, 0.1, 0.46, 42 * sx, 40, 0.0105, 0.0075, nu=10, nv=7, corner=3.0, bulge=0.003, bevel=0.0025)
        leg_arm.add(thigh, ul)
        for k in (-9, 9):
            scratch_out(leg_arm, thigh, [tu.P(t, 44 * sx + k, 0.0105) for t in _steps(0.17, 0.37, 4)], 0.0055, PLATE, seed=50 + k * sx)
        for tq in (0.14, 0.41):
            for pq in (-29, 29):
                ph = 42 * sx + pq
                leg_arm.detail(reg.screw(tu.P(tq, ph, 0.0105), tu.d(ph), r=0.0034))
        if s == "R":
            # Tally marks stencilled low on the right thigh guard.
            n = tu.d(42 * sx)
            cc = tu.P(0.38, 42 * sx, 0.0105)
            A = (ul1 - ul0).normalized()
            side = n.cross(A).normalized()
            for k in range(4):
                stripe(cc + side * (k - 1.5) * 0.011, side, 0.0028, cc, 0.03,
                       [(cc - A * 0.018, A), (cc + A * 0.018, -A)])
        tu2 = reg.Tube([tt], ul0, ul1, hard=[thigh], t=(0.0, 0.5), nt=11, nphi=36, reach=0.18)
        c.rigid(reg.strap_ring("thigh_strap", tu2.ring(0.3, 0.0015, n=22), ul0.lerp(ul1, 0.3), ul1 - ul0, 0.03, 0.0045, "webbing"), ul)
        p = tu2.P(0.3, -30 * sx, 0.0)
        M = pmc.frame(p + tu2.d(-30 * sx) * 0.0045, tu2.d(-30 * sx), ul0 - ul1)
        bkl = kit.block("leg_buckle", (0, 0, 0), (0.034, 0.008, 0.03), "gunmetal", bevel=0.0012)
        bkl.data.transform(M)
        c.rigid(bkl, ul)
        # The hanger: from under the battle belt down the trousers to the guard's top edge, hugging the cloth.
        top = tu.P(0.1, 42 * sx, 0.0)
        hd = Vector((top.x, top.y + 0.005, 0.0))
        hd = hd.normalized() if hd.length > 1e-6 else Vector((sx, 0, 0))
        hz0, hz1 = belt_z - 0.012, top.z + 0.014
        hpts = []
        for k in range(6):
            zk = hz0 + (hz1 - hz0) * k / 5
            loc, nrm_ = pmc.hit(tt, Vector((0, -0.005, zk)) + hd * 0.5, -hd)
            if loc is not None:
                hpts.append(loc + (nrm_ if nrm_.dot(hd) > 0 else -nrm_) * 0.0035)
        if len(hpts) >= 2:
            c.add(hard(pmc.sweep("hanger", hpts, 0.024, 0.004, "grey", lambda q, hd=hd: hd), "webbing.secondary"), ["hips", ul])

        ts = reg.Tube([tt], ll0, ll1, t=(-0.1, 0.8), nt=30, nphi=60, reach=0.16, spread=0.03, blur=0.022)
        shin = ts.patch("shin_guard", PLATE, 0.13, 0.66, 4 * sx, 60, 0.0095, 0.007, nu=10, nv=9, corner=3.0, bulge=0.004, bevel=0.0025)
        leg_arm.add(shin, ll)
        scratch_out(leg_arm, shin, [ts.P(t, 4 * sx, 0.0095) for t in _steps(0.26, 0.56, 4)], 0.0062, PLATE, seed=60 + sx)
        kn = ll0 + Vector((0, 0.012, 0.004))
        kenv = reg.Env([tt, shin], kn, Z=(0, -1, 0.12), F=(0, 0, 1), reach=0.15, lat=(0.0, 90.0), dlat=4.0, dlon=8.0, spread=16.0, blur=10.0, floor=0.004)

        def knee_rim(lo):
            return 47.0 - 10.0 * math.cos(math.radians(lo)) ** 2
        knee = kenv.patch("knee_cap", PLATE, -180.0, 180.0, knee_rim, lambda lo: 84.0, 0.012, 0.007, nu=16, nv=4, closed=True, pole=True,
                          inner="regime_pad", bevel=0.0022)
        leg_arm.add(knee, ll)
        kp = kenv.P(90, 0, 0.012)
        kn_n = kenv.normal(90, 0, 0.012, h=4.0)
        c.rigid(kit.cyl("knee_boss", kp - kn_n * 0.003, kp + kn_n * 0.0045, 0.013, "gunmetal", segs=6, bevel=0.0012, bsegs=1), ll)
        ts2 = reg.Tube([tt], ll0, ll1, hard=[shin], t=(0.1, 0.72), nt=13, nphi=36, reach=0.16)
        for tq in (0.24, 0.58):
            c.rigid(reg.strap_ring("shin_strap", ts2.ring(tq, 0.0015, n=22), ll0.lerp(ll1, tq), ll1 - ll0, 0.024, 0.0045, "webbing"), ll)

    # ---------------------------------------------------------------- boots
    real.boots(c, man, "boot", sole_kind="rubber", trim="rubber", top=0.2, lace="webbing", tab="secondary")
    for a in (head_arm, torso_arm, arm_arm, leg_arm):
        a.finish()
    pmc.economise(c)
    return c


SPEC = {"build": build, "faction": "deserters", "budget": (25000, 80000), "loadout": "grenade",
        "colors": {"primary": SLATE, "secondary": CREAM, "accent": CLAY}}
