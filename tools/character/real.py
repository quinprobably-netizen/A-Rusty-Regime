"""Realistic layer for the character kit: real human bodies, gloved fists, draped garments and baked
procedural textures. Every realistic character shares one pipeline (see chars/contractor.py):

    import kit, real

    def build():
        b = real.Anatomy(height=1.80, body="male", sole=0.03)  # skeleton measured from the base body,
                                                               # standing on 3 cm boot soles
        c = real.begin("runner", b)                 # a kit.Char whose finish bakes the realistic maps
        man = real.body(c, skin="skin", stubble=0.6)  # body, face, eyes; fists closed on the grips
        lead = real.bones_at(man)                   # p -> the bone leading the nearest skin (regions)
        real.gloves(c, man, "glove")                # or leave the hands bare
        shirt = real.garment(c, man, "shirt", "primary",            # cut from the body, cloth-simulated
                             keep=lambda p: lead(p) in kit.TORSO | kit.UPPER_ARMS,
                             cuts=[(point, normal), ...], ease=0.01, pin=..., slack=...)
        c.hide_under(shirt.low)                     # drop the skin it covers
        real.layer(c, man, "collar", "knit.primary", keep, cuts, ease=0.008, thick=0.003)  # tight layers
        real.patch(c, shirt.low, "pocket", "primary", region, puff=0.006)  # sewn-on pockets, pads
        real.boots(c, man, "boot")                  # shaft from the skin, sole, toe cap, laces
        c.rigid(kit.block(...), "chest")            # hard gear exactly as with the kit
        return c                                    # build.py calls c.finish()

In the rest pose the hands hang beside the hips: a region keyed to the arms by distance (a cuff
cut, sleeve slack) must also ask `lead(p) in kit.UPPER_ARMS | kit.FOREARMS`, and the waist by
`not` that, or the shirt's sides get cut, pinned or bloused with the sleeves.

Landmarks for placing gear: `b.at("armpit")`, `b.at("crotch")`, `b.at("neck_z")` (heights), `b.j(bone, t)`
(points along the rest-pose bones), `man.face()` (between the eyes, scale), `man.head_center()`.
Materials are palette kinds ("pmc_navy", "glove") or "<surface>.<tint>" ("twill.secondary",
"knit.primary"): the surface names a recipe in surfaces.py, the tint keeps the game's colour slots.

The base bodies are Blender Studio's Human Base Meshes (CC0), fetched by build.sh into vendor/. The
body keeps its multires sculpt as a separate high-poly copy (`Body.high`) that is baked into the
normal map; garments are shells of the body draped by Blender's cloth simulation in the idle pose and
carried back to the rest pose, their game mesh keeping the body's own topology and weights while the
finer simulated cloth bakes its folds and stitching into the maps; hard-surface gear is unchanged
from the kit. `Char.finish` lays out one 2048 atlas and bakes colour, normal and
occlusion/roughness/metal (surfaces.py), then exports with tangents.

Coordinates follow the kit: Blender Z-up, the character faces -Y, left side on +X, metres.
"""

import heapq
import math
import os

import bpy  # first: bpy makes bmesh importable
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import kit  # noqa: E402
import surfaces  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.join(HERE, "vendor", "human-base-meshes-bundle-v1.4.1", "human_base_meshes_bundle.blend")

# The realistic base bodies in the bundle: name -> (body object, eye objects).
BODIES = {
    "male": ("GEO-body_male_realistic", ("GEO-body_male_realistic.eye.L", "GEO-body_male_realistic.eye.R")),
    "female": ("GEO-body_female_realistic", ("GEO-body_female_realistic.eye.L", "GEO-body_female_realistic.eye.R")),
}
FINGERS = kit.FINGERS

# Realistic surfaces on top of the kit palette. name: (base, worn, metallic, roughness, wear, emission)
kit.hs.PALETTE.update({
    "glove": ((0.032, 0.032, 0.034), (0.16, 0.16, 0.16), 0.0, 0.6, 0.4, 0),     # synthetic leather
    "boot": ((0.045, 0.04, 0.036), (0.22, 0.2, 0.17), 0.0, 0.62, 0.55, 0),      # leather and nylon
    "thread": ((0.6, 0.6, 0.58), (0.7, 0.7, 0.68), 0.0, 0.7, 0.0, 0),
})


# ------------------------------------------------------------------------------------------ assets

def load(names):
    """Append objects from the base-mesh bundle into the current scene, unparented, at their own
    world positions (the bundle offsets each body sideways; callers move them)."""
    if not os.path.exists(BUNDLE):
        raise SystemExit(f"missing {BUNDLE}: run tools/character/build.sh once to fetch the Human Base Meshes")
    with bpy.data.libraries.load(BUNDLE) as (src, dst):
        dst.objects = [n for n in names]
    out = []
    for o in dst.objects:
        bpy.context.scene.collection.objects.link(o)
        out.append(o)
    bpy.context.view_layer.update()
    for o in out:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    return out


class _Mesh:
    """Numpy view of a mesh for measuring: vertices, edges, faces as edge lists, edge adjacency."""

    def __init__(self, me, mw=None):
        mw = mw or Matrix()
        self.V = np.array([(mw @ v.co)[:] for v in me.vertices])
        self.E = np.array([e.vertices[:] for e in me.edges])
        key = {tuple(sorted(e)): i for i, e in enumerate(self.E.tolist())}
        self.F = [[key[tuple(sorted(k))] for k in p.edge_keys] for p in me.polygons]
        self.adj = [[] for _ in range(len(self.V))]
        for a, b in self.E.tolist():
            d = float(np.linalg.norm(self.V[a] - self.V[b]))
            self.adj[a].append((b, d))
            self.adj[b].append((a, d))

    def section(self, o, n):
        """Contours where the plane through `o` with normal `n` cuts the mesh: a list of point arrays,
        one per connected loop."""
        V, E = self.V, self.E
        o, n = np.asarray(o, float), np.asarray(n, float) / np.linalg.norm(n)
        d = (V - o) @ n
        a, b = d[E[:, 0]], d[E[:, 1]]
        cross = np.where((a > 0) != (b > 0))[0]
        if not len(cross):
            return []
        t = a[cross] / (a[cross] - b[cross])
        P = V[E[cross, 0]] + (V[E[cross, 1]] - V[E[cross, 0]]) * t[:, None]
        idx = {e: i for i, e in enumerate(cross.tolist())}
        par = list(range(len(cross)))

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i
        for fe in self.F:
            c = [idx[e] for e in fe if e in idx]
            for k in range(1, len(c)):
                par[find(c[k])] = find(c[0])
        comps = {}
        for i in range(len(cross)):
            comps.setdefault(find(i), []).append(P[i])
        return [np.array(v) for v in comps.values()]

    def geodesic(self, sources, limit, mask=None):
        dist = {s: 0.0 for s in sources}
        h = [(0.0, s) for s in sources]
        while h:
            d, u = heapq.heappop(h)
            if d > dist.get(u, 1e9) or d > limit:
                continue
            for w, l in self.adj[u]:
                if mask is not None and not mask[w]:
                    continue
                nd = d + l
                if nd < dist.get(w, 1e9):
                    dist[w] = nd
                    heapq.heappush(h, (nd, w))
        return dist


def _radius(p):
    """Mean radius of a section contour (its perimeter over 2 pi)."""
    c = p.mean(0)
    _, _, vt = np.linalg.svd(p - c)
    a = np.arctan2((p - c) @ vt[1], (p - c) @ vt[0])
    q = p[np.argsort(a)]
    return np.linalg.norm(np.roll(q, -1, 0) - q, axis=1).sum() / (2 * math.pi)


_MEASURED = {}


def measure(body="male"):
    """Joint positions of a base body in its own space (the bundle's A-pose, feet at z=0), found from
    cross-sections: crotch, armpits, neck, wrists, knees and ankles by where the sections split or
    narrow, the rest by anatomical ratios; finger chains by marching sections in from each fingertip.
    Left side only (the bodies are symmetric). Cached per process."""
    if body in _MEASURED:
        return _MEASURED[body]
    name, eye_names = BODIES[body]
    with bpy.data.libraries.load(BUNDLE) as (src, dst):
        dst.objects = [name] + list(eye_names)
    o = dst.objects[0]
    for ob in dst.objects:
        bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    off = Vector((-o.location.x, -o.location.y, 0))
    M = _Mesh(o.data)
    eyes = [Vector(e.matrix_world.translation) + off for e in dst.objects[1:]]
    for ob in dst.objects:
        bpy.data.objects.remove(ob, do_unlink=True)
    V = M.V
    zmin, zmax = V[:, 2].min(), V[:, 2].max()
    H = zmax - zmin
    up = np.array((0, 0, 1.0))

    def comps(z):
        return M.section((0, 0, z), up)
    # Crotch: the lowest section where one loop spans x = 0.
    crotch = next(z for z in np.arange(0.3 * H, 0.65 * H, 0.004) if any(p[:, 0].min() < 0 < p[:, 0].max() for p in comps(z)))
    # Armpit: the lowest section above the hands where the torso and arms are one loop.
    armpit = next(z for z in np.arange(0.62 * H, 0.85 * H, 0.004) if len(comps(z)) == 1)
    # Neck: the narrowest single loop between armpit and eyes.
    eye_z = sum(e.z for e in eyes) / len(eyes)
    neck_z, neck_r, neck_y = None, 9.0, 0.0
    for z in np.arange(armpit + 0.1, eye_z - 0.05, 0.004):
        cs = [p for p in comps(z) if p[:, 0].min() < 0 < p[:, 0].max()]
        if len(cs) == 1:
            r = _radius(cs[0])
            if r < neck_r:
                neck_z, neck_r, neck_y = z, r, cs[0].mean(0)[1]
    # The upper-arm axis from sections just below the armpit, extended up to the shoulder joint.
    arm_pts = []
    for z in np.arange(armpit - 0.10, armpit - 0.012, 0.01):
        cs = [p for p in comps(z) if p.mean(0)[0] > 0.12 and p[:, 0].min() > 0.05]
        if cs:
            arm_pts.append(min(cs, key=lambda p: p.mean(0)[0]).mean(0))
    arm_pts = np.array(arm_pts)
    c0 = arm_pts.mean(0)
    _, _, vt = np.linalg.svd(arm_pts - c0)
    ax = vt[0] if vt[0][2] < 0 else -vt[0]
    sh_z = armpit + 0.62 * (neck_z - armpit)
    # The joint sits a deltoid's thickness inside the outer shoulder (the arm curves, so the axis
    # extended from below lands too far in).
    deltoid = max(q[:, 0].max() for q in comps(sh_z))
    shoulder = np.array((deltoid - 0.055 * H / 1.684, float(arm_pts[:, 1].mean()), sh_z))
    # March sections down the arm. Past the forearm's bulge the loops narrow to the wrist, then widen
    # into the palm: the wrist is the narrowest loop before that.
    rows = []
    p, d = c0 + ax * ((armpit - 0.03 - c0[2]) / ax[2]), ax.copy()
    r_min, wrist = 9.0, None
    for i in range(120):
        cs = [q for q in M.section(p, d) if np.linalg.norm(q.mean(0) - p) < 0.08]
        if not cs:
            break
        q = min(cs, key=lambda q: np.linalg.norm(q.mean(0) - p))
        c = q.mean(0)
        r = _radius(q)
        rows.append((c, r))
        if c[2] < shoulder[2] - 0.24 * H:
            if r < r_min:
                r_min, wrist = r, c
            elif r > 1.25 * r_min:
                break
        if len(rows) > 3:
            nd = c - rows[-3][0]
            d = 0.7 * d + 0.3 * nd / np.linalg.norm(nd)
            d /= np.linalg.norm(d)
        p = c + d * 0.006
    # Elbow: on the marched centreline at the humerus' share of the shoulder-wrist length.
    path = [shoulder] + [c for c, _ in rows]
    cum = np.concatenate([[0], np.cumsum([np.linalg.norm(path[i + 1] - path[i]) for i in range(len(path) - 1)])])
    wl = cum[[i for i, c in enumerate(path) if np.allclose(c, wrist)][0]]
    elbow = _along(path, cum, 0.55 * wl)
    # Legs: the narrowest loop between the thigh and the calf is the knee; the ankle by ratio.
    def leg(z):
        cs = [q for q in comps(z) if 0.02 < q.mean(0)[0] < 0.3 and q[:, 0].max() < 0.3]
        return min(cs, key=lambda q: q.mean(0)[0]) if cs else None
    kz = min(np.arange(0.22 * H, 0.34 * H, 0.004), key=lambda z: _radius(leg(z)))
    kz += 0.022 * H / 1.684  # the joint line sits just above the narrowest loop
    knee = leg(kz).mean(0)
    thigh = leg(crotch - 0.04).mean(0)
    hip = np.array((0.85 * thigh[0], thigh[1] + 0.01, crotch + 0.065 * H))
    ankle = leg(0.075 * H).mean(0)
    ankle[2] = 0.046 * H
    foot = V[(V[:, 2] < 0.06 * H) & (V[:, 0] > 0.03)]
    ytip = foot[:, 1].min()
    toes = foot[foot[:, 1] < ytip + 0.08]
    toe = np.array((toes[:, 0].mean(), ytip + 0.075 * H / 1.684, 0.012 * H))
    heels = foot[foot[:, 1] > foot[:, 1].max() - 0.03]
    heel = np.array((heels[:, 0].mean(), foot[:, 1].max(), 0.02))
    trunk_y = neck_y + 0.03
    neck_base = neck_z - 0.015
    head_z = eye_z - 0.05 * H / 1.684
    sec = comps(armpit + 0.06)
    back = max(p[:, 1].max() for p in sec)
    m = {
        "height": float(H), "zmin": float(zmin), "eyes": [tuple(e) for e in eyes],
        "crotch": float(crotch), "armpit": float(armpit), "neck_z": float(neck_z), "neck_r": float(neck_r),
        "hips": (0, trunk_y, hip[2]), "spine": (0, trunk_y, hip[2] + 0.213 * (neck_base - hip[2])),
        "chest": (0, trunk_y, hip[2] + 0.532 * (neck_base - hip[2])), "neck": (0, trunk_y - 0.005, neck_base),
        "head": (0, neck_y + 0.01, head_z), "top": (0, neck_y + 0.01, zmax),
        "prop_back": (0, back + 0.01, armpit + 0.06),
        "clavicle": (0.035, trunk_y - 0.01, neck_base - 0.01), "shoulder": tuple(shoulder), "elbow": tuple(elbow),
        "wrist": tuple(wrist), "hip": tuple(hip), "knee": tuple(knee), "ankle": tuple(ankle), "toe": tuple(toe),
        "heel": tuple(heel),
    }
    m.update(_measure_hand(M, np.array(wrist), np.array(elbow)))
    _MEASURED[body] = m
    return m


def _along(path, cum, s):
    i = int(np.searchsorted(cum, s)) - 1
    i = max(0, min(i, len(path) - 2))
    t = (s - cum[i]) / max(cum[i + 1] - cum[i], 1e-9)
    return path[i] + (path[i + 1] - path[i]) * t


def _measure_hand(M, wrist, elbow):
    """Finger chains of the left hand. Fingertips are the local maxima of surface distance from the
    wrist; each finger's centreline comes from sections marched in from its tip until the loop
    widens into the palm (the web), and the knuckles sit along it by phalanx ratios."""
    V = M.V
    fa = wrist - elbow
    fa /= np.linalg.norm(fa)
    t = (V - wrist) @ fa
    hand = (t > -0.004) & (V[:, 0] > wrist[0] - 0.06)
    ring = [i for i in np.where(hand)[0] if abs(t[i]) < 0.006]
    dist = M.geodesic(ring, 0.4, hand)
    cand = []
    for i, d in dist.items():
        if d < 0.08:
            continue
        nb = M.geodesic([i], 0.015, hand)
        if all(dist.get(j, 0) <= d for j in nb):
            cand.append((d, i))
    cand.sort(reverse=True)
    tips = []
    for d, i in cand:
        if all(np.linalg.norm(V[i] - V[j]) > 0.02 for _, j in tips):
            tips.append((d, i))
        if len(tips) == 5:
            break
    # The thumb is the tip nearest the wrist along the surface; the others, front (-Y) to back.
    tips.sort()
    thumb = tips[0][1]
    rest = sorted((i for _, i in tips[1:]), key=lambda i: V[i][1])
    knuckles = V[[i for i in rest]].mean(0)
    out = {}
    for fname, tip in zip(FINGERS, [thumb] + rest):
        p = V[tip].copy()
        d = (wrist + fa * 0.09) - p if fname != "thumb" else (wrist + fa * 0.03) - p
        d /= np.linalg.norm(d)
        line = [p.copy()]
        radii = []
        for i in range(30):
            q = p + d * 0.004
            cs = M.section(q, d)
            if not cs:
                break
            best = min(cs, key=lambda c: np.linalg.norm(c.mean(0) - q))
            c = best.mean(0)
            r = _radius(best)
            if np.linalg.norm(c - q) > 0.012 or (len(radii) > 4 and r > 1.45 * np.median(radii)):
                break
            radii.append(r)
            line.append(c)
            nd = c - p
            d = d * 0.6 + 0.4 * nd / np.linalg.norm(nd)
            d /= np.linalg.norm(d)
            p = c
        line = np.array(line)
        vis = float(np.sum(np.linalg.norm(line[1:] - line[:-1], axis=1)))
        back = (line[-1] - line[-4]) / np.linalg.norm(line[-1] - line[-4])
        if fname == "thumb":
            # Tip, IP, MCP along the thumb; the CMC sits back toward the wrist at the thumb's base.
            L = vis + 0.018
            ext = np.vstack([line, line[-1] + back * 0.018])
            ip, mcp = _poly_at(ext, 0.30 * L), ext[-1]
            cmc = mcp + (wrist + (knuckles - wrist) * 0.12 - mcp) * 0.55
            out["thumb"] = [tuple(cmc), tuple(mcp), tuple(ip), tuple(V[tip])]
            out["thumb_r"] = float(np.median(radii))
        else:
            L = vis + 0.025
            ext = np.vstack([line, line[-1] + back * 0.025])
            out[fname] = [tuple(_poly_at(ext, L)), tuple(_poly_at(ext, 0.55 * L)), tuple(_poly_at(ext, 0.25 * L)), tuple(V[tip])]
            out[fname + "_r"] = float(np.median(radii))
    return out


def _poly_at(line, s):
    """The point at arc length s along a polyline (extrapolating past its end)."""
    acc = 0.0
    for i in range(len(line) - 1):
        seg = float(np.linalg.norm(line[i + 1] - line[i]))
        if acc + seg >= s:
            return line[i] + (line[i + 1] - line[i]) * ((s - acc) / max(seg, 1e-9))
        acc += seg
    d = (line[-1] - line[-2]) / np.linalg.norm(line[-1] - line[-2])
    return line[-1] + d * (s - acc)


# ------------------------------------------------------------------------------------------ skeleton

def _v(p):
    return Vector(tuple(float(x) for x in p))


def _mirror(p):
    return Vector((-p[0], p[1], p[2]))


def _pivot(R, p):
    """A 4x4 rotation by 3x3 R about point p."""
    return Matrix.Translation(p) @ R.to_4x4() @ Matrix.Translation(-p)


def _toward(a, b):
    """The minimal rotation (3x3) taking direction a onto direction b."""
    return a.normalized().rotation_difference(b.normalized()).to_matrix()


class Anatomy(kit.Build):
    """A skeleton measured from one of the realistic base bodies (`body`: "male" or "female"),
    scaled to `height` (top of the head, metres). The bundle's A-pose is brought to the kit's rest
    pose: the arms hang `arm_hang` degrees out from vertical, the feet sit `stance` metres apart
    (centre to centre, at the 1.80 m scale) and turn out `toe_out` degrees. `width` widens the
    shoulders, `bulk` thickens limbs and torso (both 1.0 = the base body).

    The hands rest open and relaxed (a light curl, the thumb slightly opposed); weapon grips are
    poses solved on top by grips.py. prop_hand.R / prop_hand.L are the palm frames (see kit's module
    doc): origin on the palm's skin under the middle and ring knuckles, Y wrist to knuckles, Z out of
    the palm. Each finger bone rolls so its Z points out of the palm too, so flexion is a positive
    turn about its X on both hands.

    Besides kit.Build's fields (`k`, `hip_z`, `bones`, `all`, `j()`) it keeps what the body fit needs:
    `base` (bone -> (head, tail) in the scaled A-pose), `fit` (bone -> 4x4 matrix taking the A-pose
    bone onto its rest pose, fingers relaxed), `rest`, `finger_r`, `palm` (per side: the hand frame
    at rest, see `_relax`) and `m` (the raw measurement)."""

    def __init__(self, height=1.80, width=1.0, bulk=1.0, body="male", arm_hang=8.0, stance=0.20, toe_out=9.0, sole=0.0):
        m = measure(body)
        self.body, self.m = body, m
        self.height, self.width, self.bulk, self.legs = height, width, bulk, 0.55
        self.k = height / 1.80
        s = height / m["height"]
        self.s = s
        self.sole = sole
        lift = Vector((0, 0, -m["zmin"]))
        Up = Matrix.Translation((0, 0, sole))  # the whole body stands on its boot soles

        def P(name):
            return (_v(m[name]) + lift) * s
        J = {n: P(n) for n in ("hips", "spine", "chest", "neck", "head", "top", "prop_back", "clavicle", "shoulder", "elbow",
                               "wrist", "hip", "knee", "ankle", "toe", "heel")}
        fing = {f: [(_v(p) + lift) * s for p in m[f]] for f in FINGERS}
        self.finger_r = {f: m[f + "_r"] * s for f in FINGERS}
        mcp = {f: fing[f][0] for f in FINGERS}
        # A-pose bones (left side; the right mirrors).
        base = {
            "hips": (J["hips"], J["spine"], None), "spine": (J["spine"], J["chest"], "hips"),
            "chest": (J["chest"], J["neck"], "spine"), "neck": (J["neck"], J["head"], "chest"),
            "head": (J["head"], J["top"], "neck"),
            "prop_back": (J["prop_back"], J["prop_back"] + Vector((0, 0, 0.10 * s)), "chest"),
            "shoulder.L": (J["clavicle"], J["shoulder"], "chest"), "upper_arm.L": (J["shoulder"], J["elbow"], "shoulder.L"),
            "forearm.L": (J["elbow"], J["wrist"], "upper_arm.L"), "hand.L": (J["wrist"], mcp["middle"], "forearm.L"),
            "upper_leg.L": (J["hip"], J["knee"], "hips"), "lower_leg.L": (J["knee"], J["ankle"], "upper_leg.L"),
            "foot.L": (J["ankle"], J["toe"], "lower_leg.L"),
        }
        for f in FINGERS:
            ch = fing[f]
            for i in range(3):
                base[f"f_{f}.{i + 1}.L"] = (ch[i], ch[i + 1], "hand.L" if i == 0 else f"f_{f}.{i}.L")
        # Rest pose: rigid moves of each chain about its root joint.
        S, E, Wr = J["shoulder"], J["elbow"], J["wrist"]
        widen = Matrix.Translation(((width - 1.0) * S.x, 0, 0))
        u = E - S
        c = math.sqrt(max(1e-6, 1 - u.normalized().y ** 2))
        a = math.radians(arm_hang)
        target = Vector((math.sin(a) * c, u.normalized().y, -math.cos(a) * c))
        F_arm = Up @ widen @ _pivot(_toward(u, target), S)
        Hp, K, A = J["hip"], J["knee"], J["ankle"]
        want_x = stance / 2 * self.k
        leg = A - Hp
        tgt = Vector((want_x - Hp.x, leg.y, 0))
        tgt.z = -math.sqrt(max(1e-6, leg.length ** 2 - tgt.x ** 2 - tgt.y ** 2))
        F_leg = _pivot(_toward(leg, tgt), Hp)
        A2 = F_leg @ A
        fwd = (F_leg @ J["toe"]) - (F_leg @ J["heel"])
        yaw = math.atan2(fwd.x, -fwd.y) - math.radians(toe_out)
        F_foot = Up @ _pivot(Matrix.Rotation(-yaw, 3, "Z"), A2) @ F_leg
        F_leg = Up @ F_leg
        fit = {}
        for n in base:
            if n.startswith(("upper_arm", "forearm", "hand", "f_")):
                fit[n] = F_arm
            elif n.startswith("upper_leg") or n.startswith("lower_leg"):
                fit[n] = F_leg
            elif n.startswith("foot"):
                fit[n] = F_foot
            else:
                fit[n] = Up.copy()
        rest = {n: (fit[n] @ h, fit[n] @ t, p) for n, (h, t, p) in base.items()}
        # The hands: a relaxed curl at rest (solved on the left, mirrored for the right), the palm
        # frames and each finger bone's roll.
        self.grips = {}
        self.rolls = {}
        for side in ("L", "R"):
            curls, frame, rolls = self._relax(rest, side)
            self.grips[side] = frame
            self.rolls.update(rolls)
            arm = F_arm if side == "L" else _mirror_matrix(F_arm)
            for n, M in curls.items():
                fit[n[:-2] + "." + side] = M @ arm
        self.base = _mirror_bones(base)
        self.rest = _mirror_bones(rest)
        for n in list(fit):
            if n.endswith(".L"):
                r = n[:-2] + ".R"
                if r not in fit:
                    fit[r] = _mirror_matrix(fit[n])
        # Shoulders: the clavicle stretches to the widened joint.
        for side, sx in (("L", 1), ("R", -1)):
            h, t, _ = self.base["shoulder." + side]
            t2 = widen @ t if sx > 0 else _mirror(widen @ _mirror(t))
            fit["shoulder." + side] = Up @ _stretch(h, t, t2)
        self.fit = fit
        game = {n: (tuple(h), tuple(t), p) for n, (h, t, p) in self.rest.items() if not n.startswith("f_")}
        self.hip_z = game["hips"][0][2]
        self.bones = {n: v for n, v in game.items() if not n.endswith(".R")}
        self.all = dict(game)
        # The finger bones in their relaxed rest, each rolled so its Z points out of the palm.
        for n, (h, t, p) in self.base.items():
            if n.startswith("f_"):
                self.all[n] = (tuple(fit[n] @ h), tuple(fit[n] @ t), p, tuple(self.rolls[n]))
        for side in ("L", "R"):
            at, fwd, up = self.grips[side]
            self.all["prop_hand." + side] = (tuple(at), tuple(at + fwd * 0.08), "hand." + side, tuple(up))

    @property
    def carries(self):
        """kit.CARRIES for this body: the grips raised by how much higher its shoulders sit than the
        kit's (1.40 m at 1.80 m) and brought 4 cm nearer the chest (the ready carry 3 cm higher
        still), so the support hand reaches the handguard."""
        dz = self.all["upper_arm.L"][0][2] - 1.40 * self.k
        return {n: ((g[0], g[1] + 0.04, g[2] + dz / self.k + (0.03 if n == "ready" else 0.0)), f) for n, (g, f) in kit.CARRIES.items()}

    def at(self, name):
        """A landmark of the measured body at this character's scale, in the rest pose's frame (standing
        on its soles): "armpit", "crotch", "neck_z" are heights; "hip", "knee", "ankle", "toe", "heel",
        "shoulder", "elbow", "wrist", "chest", "neck", "head", "top", "clavicle" are left-side points
        (A-pose for the arm points: use `j()` for posed joints); "eyes" is (left, right)."""
        v = self.m[name]
        z0 = -self.m["zmin"]
        if isinstance(v, (int, float)):
            return (v + z0) * self.s + self.sole
        if name == "eyes":
            return tuple((_v(e) + Vector((0, 0, z0))) * self.s + Vector((0, 0, self.sole)) for e in v)
        return (_v(v) + Vector((0, 0, z0))) * self.s + Vector((0, 0, self.sole))

    def _relax(self, rest, side):
        """The relaxed rest hand, solved on the left (the bodies are symmetric) and mirrored for the
        right: the finger bones' extra pose matrices (over the arm's), the palm frame (origin, Y, Z)
        and each finger bone's Z direction (out of the palm) for its roll, in rest space."""
        sx = 1 if side == "L" else -1
        W = Vector(rest["hand.L"][0])
        mid = Vector(rest["hand.L"][1])
        L, T, Pn, palm, thick = hand_axes(rest, self.s)
        axis_c = L.cross(Pn).normalized()  # flexion: rotating about this brings a finger toward the palm
        out, rolls = {}, {}
        for f in FINGERS:
            names = [f"f_{f}.{i}.L" for i in (1, 2, 3)]
            js = [Vector(rest[names[0]][0])] + [Vector(rest[n][1]) for n in names]
            segs = [Matrix() for _ in names]

            def turn(j, R, js=js, segs=segs):
                M = _pivot(R, js[j])
                for q in range(j + 1, 4):
                    js[q] = M @ js[q]
                for q in range(j, 3):
                    segs[q] = M @ segs[q]
            if f == "thumb":
                # A little opposition toward the palm, and a light bend.
                d0 = js[3] - js[0]
                tgt = (W + L * (0.6 * palm) + Pn * (thick + 0.03 * self.s)) - js[0]
                turn(0, _toward(d0, d0.lerp(tgt, 0.25)))
                for j, ang in enumerate(REST_THUMB):
                    turn(j, Matrix.Rotation(math.radians(ang), 3, (js[j + 1] - js[j]).cross(Pn).normalized()))
            else:
                # Most of the spread closed, the fingers near parallel to the hand, then a light curl.
                d = js[3] - js[0]
                dp = (d - Pn * d.dot(Pn)).normalized()
                ang = math.atan2(dp.cross(L).dot(Pn), dp.dot(L))
                turn(0, Matrix.Rotation(ang * 0.6, 3, Pn))
                for j, ang in enumerate(REST_CURL):
                    turn(j, Matrix.Rotation(math.radians(ang), 3, axis_c))
            for q, n in enumerate(names):
                z = segs[q].to_3x3() @ Pn
                out[n] = segs[q] if sx > 0 else _mirror_matrix(segs[q])
                rolls[n[:-2] + "." + side] = z if sx > 0 else _mirror(z)
        at = W + L * (PALM_AT * palm) + Pn * thick
        fwd, up = L, Pn
        if side == "R":
            at, fwd, up = _mirror(at), _mirror(fwd), _mirror(up)
        return out, (at, fwd, up), rolls


# The relaxed rest hand: flexion at the knuckle, middle and tip joints (degrees), the thumb's bends,
# and where the palm frame sits along the hand (0 wrist .. 1 middle knuckle).
REST_CURL = (12.0, 18.0, 8.0)
REST_THUMB = (0.0, 12.0, 10.0)
PALM_AT = 0.75


def hand_axes(rest, s):
    """The left hand's frame at rest: L wrist to middle knuckle, T across the knuckles toward the
    index, Pn out of the palm (the palm faces the body's midline), the palm's length and half
    thickness."""
    W = Vector(rest["hand.L"][0])
    mid = Vector(rest["hand.L"][1])
    L = (mid - W).normalized()
    T = Vector(rest["f_index.1.L"][0]) - Vector(rest["f_pinky.1.L"][0])
    T = (T - L * T.dot(L)).normalized()
    Pn = L.cross(T).normalized()
    if Pn.x > 0:
        Pn = -Pn
    return L, T, Pn, (mid - W).length, 0.0125 * s


def _mirror_matrix(M):
    X = Matrix.Scale(-1, 4, (1, 0, 0))
    return X @ M @ X


def _stretch(h, t, t2):
    """A matrix that keeps `h` and moves `t` to `t2` (scaling along the bone)."""
    d0, d1 = t - h, t2 - h
    R = _toward(d0, d1).to_4x4()
    k = d1.length / max(d0.length, 1e-9)
    n = d0.normalized()
    Sc = Matrix.Identity(4)
    for i in range(3):
        for j in range(3):
            Sc[i][j] = (1.0 if i == j else 0.0) + (k - 1) * n[i] * n[j]
    return Matrix.Translation(h) @ R @ Sc @ Matrix.Translation(-h)


def _mirror_bones(bones):
    out = {}
    for n, (h, t, p) in bones.items():
        out[n] = (Vector(h), Vector(t), p)
        if n.endswith(".L"):
            pr = p[:-2] + ".R" if p and p.endswith(".L") else p
            out[n[:-2] + ".R"] = (_mirror(h), _mirror(t), pr)
    return out


# ------------------------------------------------------------------------------------------ the body

class Body:
    """A realistic body fitted to a character's Anatomy. `low` is the game mesh (the base body's own
    cage, weighted by bone heat; garments copy their weights from it), `high` its multires sculpt
    realised as a mesh for baking, `eyes` the two eyeballs. `tree` ray-casts the low surface."""

    def __init__(self, low, high, eyes, anatomy):
        self.low, self.high, self.eyes, self.b = low, high, eyes, anatomy
        self._tree = None

    @property
    def tree(self):
        if self._tree is None:
            from mathutils.bvhtree import BVHTree
            me = self.low.data
            self._tree = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [p.vertices[:] for p in me.polygons])
        return self._tree

    def face(self):
        """(the point between the eyes, scale): the base bodies share one face layout, `u` metres per
        metre of it (a face 6.6 cm between the eye centres has u = 1)."""
        e = [Vector(x.matrix_world.translation) for x in self.eyes]
        return (e[0] + e[1]) / 2, (e[0] - e[1]).length / 0.066

    def head_center(self):
        """The middle of the skull (between the ears, at brow height), for placing headgear."""
        e = [Vector(x.matrix_world.translation) for x in self.eyes]
        mid = (e[0] + e[1]) / 2
        return mid + Vector((0, 0.085 * self.b.s, 0.012 * self.b.s))


def _realise(obj, level):
    """A new mesh object with `obj`'s multires evaluated at `level` (modifiers otherwise ignored)."""
    mr = next(m for m in obj.modifiers if m.type == "MULTIRES")
    mr.levels = level
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    o = bpy.data.objects.new(obj.name + ".high", me)
    bpy.context.scene.collection.objects.link(o)
    o.matrix_world = obj.matrix_world
    obj.modifiers.remove(mr)
    return o


def _fit_rig(b):
    """A throwaway armature at the base body's own joints (A-pose, scaled): the game bones plus three
    bones per finger."""
    data = bpy.data.armatures.new("fit_rig")
    arm = bpy.data.objects.new("fit_rig", data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for n, (h, t, _) in b.base.items():
        e = data.edit_bones.new(n)
        e.head, e.tail = h, t
        e.use_deform = n in kit.DEFORM or n.startswith("f_")
    for n, (_, _, p) in b.base.items():
        if p:
            data.edit_bones[n].parent = data.edit_bones[p]
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def _pose_fit(arm, b):
    """Pose the fit rig so every bone lands on its rest-pose place: pose = fit @ rest, written as each
    bone's local basis relative to its parent's pose."""
    bones = arm.data.bones
    posed = {}
    order = []

    def visit(bn):
        order.append(bn)
        for ch in bn.children:
            visit(ch)
    for bn in bones:
        if bn.parent is None:
            visit(bn)
    for bn in order:
        P = b.fit.get(bn.name, Matrix()) @ bn.matrix_local
        if bn.parent:
            par = bn.parent
            basis = (posed[par.name] @ par.matrix_local.inverted() @ bn.matrix_local).inverted() @ P
        else:
            basis = bn.matrix_local.inverted() @ P
        posed[bn.name] = P
        pb = arm.pose.bones[bn.name]
        pb.rotation_mode = "QUATERNION"
        pb.matrix_basis = basis
    bpy.context.view_layer.update()


def _deform(obj, arm):
    m = obj.modifiers.new("fit", "ARMATURE")
    m.object = arm
    kit.hs._apply(obj, m.name)


def body(c, sex=None, high_level=3, skin="skin", face_detail=2.0, stubble=1.0):
    """Load the base body for `c.b` (an Anatomy), fit it to the character's rest pose with curled
    fists, weight it to the game rig and register it as the character's flesh (garments copy its
    weights) with its eyes (rigid to the head). Returns a Body.

    `skin` is the palette kind of the skin (its colour; the "skin" surface adds pores, colour
    variation and the face masks); `face_detail` is how many times more texels the head gets than the
    rest of the atlas; `stubble` (0..1) scales the shaved-beard shadow."""
    b = c.b
    name, eye_names = BODIES[sex or b.body]
    low, *eyes = load([name] + list(eye_names))
    lift = Vector((-low.location.x, -low.location.y, -b.m["zmin"]))
    for o in [low] + eyes:
        o.location += lift
    bpy.context.view_layer.update()
    high = _realise(low, high_level)
    S = Matrix.Scale(b.s, 4)
    for o in [low, high] + eyes:
        o.matrix_world = S @ o.matrix_world
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        # The eyes keep their origin at their centre (Body.head_center and gaze use it).
        bpy.ops.object.transform_apply(location=o not in eyes, rotation=True, scale=True)
    low.name, high.name = "body", "body.high"
    for e in eyes:
        e.matrix_world = b.fit["head"] @ e.matrix_world  # the head's rest move (the sole lift)
    rig = _fit_rig(b)
    kit.heat(rig, low)
    for g in list(high.vertex_groups):
        high.vertex_groups.remove(g)
    kit.transfer(low, high)
    _pose_fit(rig, b)
    _deform(low, rig)
    _deform(high, rig)
    bpy.data.objects.remove(rig, do_unlink=True)
    for g in list(high.vertex_groups):
        high.vertex_groups.remove(g)
    for o in (low, high):
        o.data.materials.clear()
        o.data.materials.append(kit.mat(skin))
        for p in o.data.polygons:
            p.use_smooth = True
    for e in eyes:
        e.data.materials.clear()
        e.data.materials.append(kit.mat("eye"))
        for p in e.data.polygons:
            p.use_smooth = True
        e["shaded"] = True
        e["bevel"] = 0.0
        _eye_attrs(e)
        c.rigid(e, "head")
    low["shaded"] = True
    low["bevel"] = 0.0
    me = Body(low, high, eyes, b)
    for o in (low, high):
        _face_masks(o, me, stubble)
    c.skin_source = low
    c.parts.append((low, "DONE", None))
    c.detail(low, [high], ext=0.012, ray=0.03)
    c.body = me

    def texel(obj):
        dom = kit.dominant(obj)  # at layout time: the covered skin is gone by then

        def f(isl):
            head = sum(1 for f in isl if sum(dom[v.index] in kit.HEAD_GROUP for v in f.verts) * 2 > len(f.verts))
            return face_detail if head * 2 > len(isl) else 1.0
        return f
    surfaces._TEXEL_FN[low.name] = texel
    low["texel"] = 1.0
    return me


def _eye_attrs(e):
    """eye_r / eye_a on an eyeball (origin at its centre, looking down -Y): the angle from the gaze
    axis (1 = 90 degrees) and around it (0..1), for the iris and pupil."""
    me = e.data
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    n = co / np.maximum(np.linalg.norm(co, axis=1, keepdims=True), 1e-9)
    r = np.degrees(np.arccos(np.clip(-n[:, 1], -1, 1))) / 90.0
    a = (np.arctan2(n[:, 2], n[:, 0]) / (2 * math.pi)) + 0.5
    for name, vals in (("eye_r", r), ("eye_a", a)):
        at = me.attributes.new(name, "FLOAT", "POINT")
        at.data.foreach_set("value", vals.astype(np.float32))


def _smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _face_masks(o, man, stubble=1.0):
    """The `face` colour attribute on a body mesh: (stubble, lips, brows, eye sockets), placed from the
    eyes (the base bodies share one face layout)."""
    me = o.data
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    eL, eR = [np.array(x.matrix_world.translation) for x in man.eyes]
    E = (eL + eR) / 2
    u = np.linalg.norm(eL - eR) / 0.066
    x, y, z = (co[:, 0] - E[0]) / u, (co[:, 1] - E[1]) / u, (co[:, 2] - E[2]) / u
    ax = np.abs(x)
    front = _smooth(-y, -0.03, -0.0)
    # Brows: an arch over each eye, thick at the inner end, tapering outward.
    zc = 0.020 + 0.006 * (1 - ((ax - 0.030) / 0.03) ** 2)
    half = 0.0062 - 0.0025 * _smooth(ax, 0.02, 0.06)
    brows = _smooth(half - np.abs(z - zc), 0.0, 0.002) * _smooth(ax, 0.006, 0.012) * (1 - _smooth(ax, 0.055, 0.064))
    brows *= _smooth(-y, 0.0, 0.03)
    # Lips: an ellipse below the nose.
    lz = z + 0.073
    lips = _smooth(1.0 - ((x / 0.0255) ** 2 + (lz / (0.0105 + 0.002 * (lz < 0))) ** 2), 0.0, 0.35) * _smooth(-y, 0.03, 0.06)
    # Stubble: jaw, chin, cheeks below the cheekbones, upper lip, under the chin and the sideburns.
    cheek = 1 - _smooth(z, -0.042 - 0.02 * _smooth(ax, 0.045, 0.02), -0.028)
    under = _smooth(z, -0.16, -0.125)
    side = 1 - _smooth(ax, 0.066, 0.076)
    burns = _smooth(z, -0.055, -0.045) * (1 - _smooth(z, 0.0, 0.012)) * _smooth(ax, 0.058, 0.064) * (1 - _smooth(ax, 0.075, 0.082)) * _smooth(y, -0.01, 0.0) * (1 - _smooth(y, 0.03, 0.04))
    nose = _smooth(z, -0.06, -0.052) * (1 - _smooth(ax, 0.016, 0.024))
    beard = np.maximum(cheek * under * side * front * (1 - nose), burns)
    beard = np.clip(beard - lips * 1.6, 0, 1) * stubble
    # Eye sockets: shading round each eye.
    sock = np.zeros(len(co))
    for e in (eL, eR):
        d = np.linalg.norm(co - e, axis=1) / u
        sock = np.maximum(sock, (1 - _smooth(d, 0.016, 0.03)) * front)
    vals = np.stack([beard, lips, brows, sock], axis=1).astype(np.float32)
    at = me.attributes.new("face", "FLOAT_COLOR", "POINT")
    at.data.foreach_set("color", vals.ravel())


# ------------------------------------------------------------------------------------------ garments

def _bm_obj(name, bm, material=None, groups=()):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    # Vertex groups in the source mesh's order, so the deform weights bmesh carried line up.
    for g in groups:
        o.vertex_groups.new(name=g)
    if material:
        me.materials.clear()
        me.materials.append(kit.mat(material))
    for p in me.polygons:
        p.use_smooth = True
    o["bevel"] = 0.0
    o["shaded"] = True
    return o


def _shell_bm(man, keep, cuts=(), ease=0.012, smooth=3):
    bm = bmesh.new()
    bm.from_mesh(man.low.data)
    bm.faces.ensure_lookup_table()
    drop = [f for f in bm.faces if not keep(f.calc_center_median())]
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    for cut in cuts:
        p, n = Vector(cut[0]), Vector(cut[1]).normalized()
        near = cut[2] if len(cut) > 2 else (lambda q: True)
        faces = [f for f in bm.faces if near(f.calc_center_median())]
        verts = {v for f in faces for v in f.verts}
        edges = {e for f in faces for e in f.edges}
        bmesh.ops.bisect_plane(bm, geom=list(verts) + list(edges) + faces, dist=1e-5, plane_co=p, plane_no=n, clear_outer=True)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    _drop_islands(bm)
    bm.normal_update()
    for v in bm.verts:
        e = ease(v.co) if callable(ease) else ease
        v.co += v.normal * e
    for _ in range(smooth):
        bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=0.5,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
    return bm


def shell(man, name, keep, cuts=(), ease=0.012, smooth=3, subdivide=2, material=None):
    """The start of a garment: the body's surface where `keep(p)` holds for the face centre and on
    the inner side of every cut plane ((point, normal) or (point, normal, near): the side the normal
    points to is removed, only among faces where `near(centre)` holds),
    pushed out along the normals by `ease` metres (a number or a function of the point) and relaxed
    `smooth` times so it bridges the body's hollows, then subdivided `subdivide` times for the cloth
    simulation. The cuts make clean straight hems; the body's UVs come along (garment islands), and so
    do its skin weights, vertex by vertex (a sleeve's inner side keeps the arm's weights even where it
    passes close to the ribs)."""
    bm = _shell_bm(man, keep, cuts, ease, smooth)
    if subdivide:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=subdivide, use_grid_fill=True, smooth=0.0)
    return _bm_obj(name, bm, material, [g.name for g in man.low.vertex_groups])


def _drop_islands(bm, keep_min=60):
    """Delete loose bits a cut left behind (fewer than keep_min faces)."""
    seen = set()
    small = []
    for f in bm.faces:
        if f in seen:
            continue
        stack, isl = [f], []
        seen.add(f)
        while stack:
            g = stack.pop()
            isl.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen:
                        seen.add(h)
                        stack.append(h)
        if len(isl) < keep_min:
            small += isl
    if small:
        bmesh.ops.delete(bm, geom=small, context="FACES")


def boundary_loops(obj):
    """The open edge loops of a mesh as lists of vertex indices (hems, cuffs, collars)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    edges = [e for e in bm.edges if e.is_boundary]
    nb = {}
    for e in edges:
        a, b = e.verts[0].index, e.verts[1].index
        nb.setdefault(a, []).append(b)
        nb.setdefault(b, []).append(a)
    bm.free()
    loops, seen = [], set()
    for s in nb:
        if s in seen:
            continue
        loop, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nxt = [x for x in nb[cur] if x != prev and x not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        loops.append(loop)
    return loops


def weigh_garment(c, man, obj, far=0.075):
    """Skin a garment like Char.add (weights copied from the nearest body surface), but drop forearm
    and hand influence from vertices more than `far` from those bones, so a waistband next to the
    hanging fists does not follow the arms."""
    kit.transfer(man.low, obj)
    arm = ("forearm.L", "forearm.R", "hand.L", "hand.R")
    names = {g.index: g.name for g in obj.vertex_groups}
    segs = {n: (Vector(c.b.all[n][0]), Vector(c.b.all[n][1])) for n in arm}
    groups = {g.name: g for g in obj.vertex_groups}
    for v in obj.data.vertices:
        bad = [g for g in v.groups if names[g.group] in segs and kit.seg_dist(v.co, *segs[names[g.group]]) > far]
        if not bad:
            continue
        for g in bad:
            g.weight = 0.0
        tot = sum(g.weight for g in v.groups)
        if tot > 1e-4:
            for g in v.groups:
                g.weight /= tot
        else:
            for bn, w in kit.weights_at(c.b, v.co, sorted(kit.TORSO | kit.THIGHS)).items():
                if bn not in groups:
                    groups[bn] = obj.vertex_groups.new(name=bn)
                groups[bn].add([v.index], w, "REPLACE")


def reference_pose(c):
    """The pose garments are draped in: the idle clip's first frame (the rifle-ready carry every
    gameplay clip is close to), so sleeves fold where the elbows bend. Solves the carries first."""
    kit.solve_carries(c.b, c.arm)
    return kit.clip_idle(c.b, 0.0)


def posed_copy(obj, arm, name):
    """A static copy of `obj` deformed by `arm`'s current pose."""
    m = obj.modifiers.new("posed", "ARMATURE")
    m.object = arm
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    obj.modifiers.remove(m)
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def _outside(points, body, gap):
    """Points lifted out of `body` (and off it to at least `gap`) along its surface normal: where skinning
    folds the skin (an armpit, the inside of an elbow) a shell can start under it, and cloth that
    starts inside a collider stays there."""
    from mathutils.bvhtree import BVHTree
    me = body.data
    tree = BVHTree.FromPolygons([v.co for v in me.vertices], [p.vertices[:] for p in me.polygons])
    out = []
    for p in points:
        loc, nor, _, _ = tree.find_nearest(p)
        h = (p - loc).dot(nor)
        out.append(p + nor * (gap - h) if h < gap else p)
    return out


def _skin_matrices(arm):
    """bone -> 4x4 deformation (pose @ rest^-1) in armature space, for the current pose."""
    return {pb.name: pb.matrix @ pb.bone.matrix_local.inverted() for pb in arm.pose.bones}


def unskin(obj, arm):
    """Move a mesh posed by `arm`'s current pose back to the rest pose: each vertex through the
    inverse of its blended bone matrices (the inverse of linear blend skinning), so skinning it to this
    pose again gives back exactly this shape."""
    D = _skin_matrices(arm)
    names = {g.index: g.name for g in obj.vertex_groups}
    for v in obj.data.vertices:
        M = Matrix(((0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)))
        tot = 0.0
        for g in v.groups:
            n = names[g.group]
            if n in D and g.weight > 0:
                M = M + D[n] * g.weight
                tot += g.weight
        if tot < 1e-6:
            continue
        M = M * (1.0 / tot)
        try:
            v.co = M.inverted() @ v.co
        except ValueError:
            pass
    obj.data.update()


def drape(c, man, garment, pin, slack=None, frames=30, gravity=1.0, stiff=1.0, bend=10.0, collide=(),
          shrink=-0.10, quality=6, self_collide=False, mass=0.25):
    """Drape `garment` (a shell in the rest pose) with Blender's cloth simulation in the reference pose
    (`reference_pose`, the idle carry every gameplay clip is close to), then bring the result back to
    the rest pose (`unskin`), so the skinned game mesh shows the folds exactly where that pose makes
    them.

    The shell is skinned into the pose by its own weights (the skin's) and simulated with its
    rest-pose shape as the cloth's rest shape: where the pose bunches the sleeve (inside the elbow,
    under the raised arm) the fabric is longer than the room it has and buckles into folds; where it
    stretches (over the shoulder blade) it relaxes instead of cutting into the skin.

    `pin(p)` (0..1, rest-pose point) holds hems, collars and waistbands; `slack(p)` (0..1) grows the fabric there by up to -`shrink`
    of its length so it stacks (sleeves above the cuffs, trousers above the boots, a shirt bloused over
    its belt). `bend` is the bending stiffness (broader folds when high); `collide` holds extra
    collision objects in the rest pose (a garment underneath). The garment keeps its skin weights
    (vertex groups). Returns the garment, its mesh now the draped shape in the rest pose."""
    if not garment.vertex_groups:
        weigh_garment(c, man, garment)
    me = garment.data
    rest_co = [v.co.copy() for v in me.vertices]
    arm = c.arm
    kit.apply_pose(arm, reference_pose(c))
    posed_body = posed_copy(man.low, arm, "drape_body")
    posed_cols = [posed_body] + [posed_copy(o, arm, "drape_col") for o in collide]
    # The shell's start in the pose: skinned by its own weights, so it moves exactly with the skin.
    tmp = posed_copy(garment, arm, "drape_start")
    posed = [v.co.copy() for v in tmp.data.vertices]
    bpy.data.objects.remove(tmp, do_unlink=True)
    posed = _outside(posed, posed_body, 0.005)
    # Each vertex's rest length factor (rest-pose edge length over posed length, geometric mean over
    # its edges) plus the slack, as Blender's per-vertex shrink: rest length = start length * (1 - shrink).
    logk = [0.0] * len(rest_co)
    cnt = [0] * len(rest_co)
    for e in me.edges:
        a, b = e.vertices
        lp = (posed[a] - posed[b]).length
        lr = (rest_co[a] - rest_co[b]).length
        if lp > 1e-7 and lr > 1e-7:
            r = math.log(lr / lp)
            for i in (a, b):
                logk[i] += r
                cnt[i] += 1
    shr = []
    for i, v in enumerate(me.vertices):
        # Only where the pose bunches the fabric (k > 1) does it keep its rest length and fold; where
        # the pose stretches it (over a raised shoulder) it relaxes to the room it has instead of
        # pulling into the skin.
        k = max(1.0, math.exp(logk[i] / cnt[i])) if cnt[i] else 1.0
        sl = max(0.0, min(1.0, slack(rest_co[i]))) if slack else 0.0
        shr.append((1.0 - k) + sl * shrink)
    lo, hi = min(shr), max(shr)
    if hi - lo < 1e-4:
        hi = lo + 1e-4
    pg = garment.vertex_groups.new(name="pin")
    sg = garment.vertex_groups.new(name="shrink")
    for v in me.vertices:
        w = max(0.0, min(1.0, pin(rest_co[v.index])))
        if w > 0:
            pg.add([v.index], w, "REPLACE")
        sg.add([v.index], (shr[v.index] - lo) / (hi - lo), "REPLACE")
    for v, p in zip(me.vertices, posed):
        v.co = p
    me.update()
    for o in posed_cols:
        o.modifiers.new("collide", "COLLISION")
        o.collision.thickness_outer = 0.004
        o.collision.thickness_inner = 0.008
        o.collision.cloth_friction = 5.0
        o.collision.damping = 0.6
    cl = garment.modifiers.new("cloth", "CLOTH")
    st = cl.settings
    st.quality = quality
    st.mass = mass
    st.air_damping = 2.0
    st.tension_stiffness = 18 * stiff
    st.compression_stiffness = 18 * stiff
    st.shear_stiffness = 6 * stiff
    st.bending_stiffness = bend
    st.tension_damping = 6
    st.compression_damping = 6
    st.shear_damping = 6
    st.bending_damping = 0.6
    st.vertex_group_mass = "pin"
    st.pin_stiffness = 2.0
    st.effector_weights.gravity = gravity
    st.shrink_min = lo
    st.shrink_max = hi
    st.vertex_group_shrink = "shrink"
    cs = cl.collision_settings
    cs.use_collision = True
    cs.distance_min = 0.003
    cs.collision_quality = 3
    cs.use_self_collision = self_collide
    cs.self_distance_min = 0.0025
    cs.self_friction = 5.0
    cl.point_cache.frame_start = 1
    cl.point_cache.frame_end = frames
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frames
    for f in range(1, frames + 1):
        sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    new = bpy.data.meshes.new_from_object(garment.evaluated_get(dg))
    garment.modifiers.clear()
    old = garment.data
    garment.data = new  # vertex groups live on the object and survive the swap
    bpy.data.meshes.remove(old)
    for g in ("pin", "shrink"):
        garment.vertex_groups.remove(garment.vertex_groups[g])
    unskin(garment, arm)
    for o in posed_cols:
        bpy.data.objects.remove(o, do_unlink=True)
    kit.apply_pose(arm, {})
    sc.frame_set(1)
    return garment


# ------------------------------------------------------------------------------- garments, layers

class Garment:
    """A draped garment: `low` is the game mesh (the body's own topology, weighted vertex by vertex
    from the skin), `high` the simulated cloth it bakes its folds and stitching from."""

    def __init__(self, low, high):
        self.low, self.high = low, high

    @property
    def tree(self):
        from mathutils.bvhtree import BVHTree
        me = self.low.data
        return BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [p.vertices[:] for p in me.polygons])


def garment(c, man, name, kind, keep, cuts=(), ease=0.012, smooth=3, pin=None, slack=None, fine=2, texel=1.0,
            seams=True, ext=0.012, ray=0.03, trims=(), **sim):
    """A garment cut from the body (see `shell` for keep / cuts / ease / smooth) and draped with the
    cloth simulation (see `drape` for pin / slack and the **sim settings; no pin: no simulation).
    The cloth is simulated `fine` subdivisions finer than the game mesh, which keeps the body's
    vertices and takes the simulated positions there; the fine cloth is baked into its normal map.
    `kind` is its material ("primary", or "<surface>.<tint>" such as "twill.secondary"); `texel`
    gives it that many times the atlas's texel density; `seams` stitches its hems and the body's UV
    seams (the garment's pattern pieces). `trims` [(kind, region(p))] give the faces whose centre
    passes region another material, in one piece with the rest (a knit collar and cuffs on a
    shirt). Registers the garment with `c` and returns a Garment."""
    groups = [g.name for g in man.low.vertex_groups]
    bm = _shell_bm(man, keep, cuts, ease, smooth)
    coarse = [v.co.copy() for v in bm.verts]
    low = _bm_obj(name, bm.copy(), None, groups)
    if fine:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=fine, use_grid_fill=True, smooth=0.0)
    # The game mesh's vertices among the fine cloth's (subdividing keeps them where they were).
    from mathutils.kdtree import KDTree
    kd = KDTree(len(bm.verts))
    for i, v in enumerate(bm.verts):
        kd.insert(v.co, i)
    kd.balance()
    where = np.array([kd.find(p)[1] for p in coarse])
    high = _bm_obj(name + ".high", bm, None, groups)
    m = mat(kind)
    for o in (low, high):
        o.data.materials.append(m)
        for k, region in trims:
            o.data.materials.append(mat(k))
            i = len(o.data.materials) - 1
            for p in o.data.polygons:
                if region(p.center):
                    p.material_index = i
    if pin is not None:
        drape(c, man, high, pin, slack, **sim)
    co = np.zeros(len(high.data.vertices) * 3)
    high.data.vertices.foreach_get("co", co)
    low.data.vertices.foreach_set("co", co.reshape(-1, 3)[where].ravel())
    low.data.update()
    if seams:
        seam_attrs(high)
        seam_attrs(low)
    low["texel"] = texel
    c.parts.append((low, "DONE", None))
    c.detail(low, [high], ext=ext, ray=ray)
    return Garment(low, high)


def layer(c, man, name, kind, keep, cuts=(), ease=0.003, smooth=0, subdivide=0, texel=1.0, seams=True, thick=0.0):
    """A thin layer over the skin that bends with it exactly (gloves, socks, short hair, a balaclava,
    a collar, a cap): a shell of the body (see `shell`), weighted vertex by vertex from the skin,
    baked as is, optionally given `thick`ness inward (a rim shows at its edges). `seams`: True stitches
    hems and the body's UV seams, "hems" only the open edges (hair thins out there), False none."""
    o = shell(man, name, keep, cuts, ease, smooth, subdivide)
    o.data.materials.append(mat(kind))
    if seams:
        seam_attrs(o, uv_seams=seams != "hems")
    if thick:
        sm = o.modifiers.new("thick", "SOLIDIFY")
        sm.thickness = thick
        sm.offset = -1.0
        sm.use_rim = True
        sm.use_even_offset = True
        kit.hs._apply(o, sm.name)
        o["unwrap"] = True
    o["texel"] = texel
    c.parts.append((o, "DONE", None))
    return o


def bones_at(man):
    """A function p -> the bone that leads the skin at p (regions for `keep`: "the torso and arms",
    whatever the pose): the nearest corner of the nearest face that p is not behind. In the rest
    pose the hanging forearms press on the hips, and the nearest skin vertex to a point on the hip
    can be the arm's."""
    from mathutils.bvhtree import BVHTree
    me = man.low.data
    dom = kit.dominant(man.low)
    co = [v.co.copy() for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons]
    t = BVHTree.FromPolygons(co, polys)

    def lead(p):
        p = Vector(p)
        loc, nor, i, d = t.find_nearest(p)
        if i is None:
            return "hips"
        if d < 0.05:
            front = [(dd, ii) for l, n, ii, dd in t.find_nearest_range(p, d + 0.008) if (p - l).dot(n) > -0.001]
            if front:
                i = min(front)[1]
        return dom[min(polys[i], key=lambda k: (co[k] - p).length_squared)]
    return lead


def gloves(c, man, kind="glove", cuff=0.035, ease=0.0022, texel=1.4):
    """Gloves: the hands' skin as a layer `ease` thick, ending `cuff` above the wrist joint in a clean
    hem; the bare hands are dropped. Returns the layer (both hands)."""
    b = c.b
    seg = kit.seg_dist

    def axis(s):
        return (b.j("hand." + s, 0.0) - b.j("forearm." + s, 0.0)).normalized()

    def near(p, s, r=0.2):
        return seg(p, b.j("forearm." + s, 0.4), b.j("hand." + s, 1.0)) < r

    def keep(p):
        return any(near(p, s) and (p - b.j("hand." + s, 0.0)).dot(axis(s)) > -cuff - 0.01 for s in ("L", "R"))
    cuts = [(b.j("hand." + s, 0.0) - axis(s) * cuff, -axis(s), lambda p, s=s: near(p, s, 0.12)) for s in ("L", "R")]
    o = layer(c, man, "gloves", kind, keep, cuts, ease=ease, texel=texel)
    c.cover({"hand.L", "hand.R"})
    return o


def boots(c, man, kind="boot", sole_kind="rubber", trim="rubber", top=0.19, lace="webbing", tab="black"):
    """Tactical boots over the feet: the shaft and vamp are a layer of the skin (smoothed so the toes
    vanish), cut level at `top` above the sole; a rubber sole with tread under it (the build's
    `sole` thickness: make the Anatomy with sole=0.03 or so), toe cap and heel counter, laces and a
    pull tab. The bare feet are dropped. Returns {"L": upper, "R": upper}, the uppers in one object
    under key "upper"."""
    b = c.b
    z0 = b.sole
    zt = z0 + top

    def ease(p):
        return 0.006 + 0.006 * _smooth(p.z, z0 + 0.06, z0 + 0.13)

    def keep(p):
        return p.z < zt + 0.03
    up = layer(c, man, "boot", kind, keep, [((0, 0, zt), (0, 0, 1))], ease=ease, smooth=5, texel=1.0)
    c.cover(kit.FEET | kit.SHINS, lambda p: p.z < zt - 0.012)
    me = man.low.data
    out = {"upper": up}
    from mathutils.bvhtree import BVHTree
    tu = BVHTree.FromPolygons([v.co.copy() for v in up.data.vertices], [p.vertices[:] for p in up.data.polygons])
    for s, sx in (("L", 1), ("R", -1)):
        bone = "foot." + s
        pts = [v.co for v in me.vertices if v.co.z < z0 + 0.03 and v.co.x * sx > 0.02]
        hull = _hull2d([(p.x, p.y) for p in pts])
        cx = sum(p[0] for p in hull) / len(hull)
        cy = sum(p[1] for p in hull) / len(hull)
        ring = []
        for x, y in hull:
            d = Vector((x - cx, y - cy))
            ring.append((x + d.normalized().x * 0.008, y + d.normalized().y * 0.008))
        ring = kit.rounded(_resample(ring, 18), 0.012, n=2)
        sole = kit.plan("sole", ring, z0 + 0.012, sole_kind, z=(z0 + 0.012) / 2, bevel=0.003)
        ys = [p[1] for p in ring]
        kit.cut(sole, *kit.slots("tread", min(ys) + 0.025, max(ys) - 0.025, 7, -0.002, 0.006, cx - 0.1, cx + 0.1))
        c.rigid(sole, bone)
        # Toe cap and heel counter: rubber over the front and back of the vamp.
        toe_y, heel_y = min(ys), max(ys)
        patch(c, up, "toe_cap", trim, lambda p, sx=sx, toe_y=toe_y: p.x * sx > 0.0 and p.y < toe_y + 0.07 and z0 + 0.004 < p.z < z0 + 0.06,
              lift=0.0015, thick=0.002, subdivide=0, smooth=1)
        patch(c, up, "heel_counter", trim, lambda p, sx=sx, heel_y=heel_y: p.x * sx > 0.0 and p.y > heel_y - 0.06 and z0 + 0.004 < p.z < z0 + 0.075,
              lift=0.0015, thick=0.002, subdivide=0, smooth=1)
        # Laces up the front of the shaft, found with rays.
        ax = b.j("lower_leg." + s, 1.0)
        for i in range(6):
            z = z0 + 0.06 + i * 0.022
            y_front = -0.02 - 0.06 * max(0.0, 1 - i / 2.5)
            loc, nor, _, _ = tu.ray_cast(Vector((ax.x, y_front - 0.3, z)), Vector((0, 1, 0)))
            if loc is None:
                continue
            o = kit.block("lace", (0, 0, 0), (0.036, 0.005, 0.005), lace, bevel=0.0012)
            q = Vector((0, -1, 0)).rotation_difference(nor)
            o.data.transform(Matrix.Translation(loc + nor * 0.002) @ q.to_matrix().to_4x4() @ Matrix.Rotation(math.radians(18 if i % 2 else -18), 4, "Y"))
            c.rigid(o, bone if i < 2 else "lower_leg." + s)
        loc, nor, _, _ = tu.ray_cast(Vector((ax.x, 0.4, zt - 0.02)), Vector((0, -1, 0)))
        if loc is not None:
            c.rigid(kit.block("pull_tab", loc + Vector((0, 0.005, 0.016)), (0.02, 0.005, 0.045), tab, bevel=0.0015), "lower_leg." + s)
    return out


def _hull2d(pts):
    pts = sorted(set((round(x, 5), round(y, 5)) for x, y in pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _resample(poly, n):
    """A closed outline resampled to n points evenly along its length."""
    P = [Vector(p) for p in poly]
    L = [(P[(i + 1) % len(P)] - P[i]).length for i in range(len(P))]
    tot = sum(L)
    out, i, acc = [], 0, 0.0
    for k in range(n):
        t = tot * k / n
        while acc + L[i] < t:
            acc += L[i]
            i += 1
        f = (t - acc) / max(L[i], 1e-9)
        q = P[i].lerp(P[(i + 1) % len(P)], f)
        out.append((q.x, q.y))
    return out


def patch(c, src, name, kind, region, lift=0.004, puff=0.0, thick=0.003, subdivide=1, smooth=2, texel=1.0):
    """A soft patch sewn onto a garment or layer `src` (a pocket, a reinforcement, a pad cover): the
    faces of `src` whose centre passes `region(p)`, lifted `lift` off it, swelled `puff` in the middle,
    given `thick`ness and stitched round its edge. It bends with `src` (same weights). Returns it."""
    bm = bmesh.new()
    bm.from_mesh(src.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not region(f.calc_center_median())], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    if subdivide:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=subdivide, use_grid_fill=True, smooth=0.0)
    for _ in range(smooth):
        bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=0.5,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    # Distance to the edge (in rings) for the swell.
    ring = {v: 0 for v in bm.verts if v.is_boundary}
    front = list(ring)
    while front:
        nxt = []
        for v in front:
            for e in v.link_edges:
                w = e.other_vert(v)
                if w not in ring:
                    ring[w] = ring[v] + 1
                    nxt.append(w)
        front = nxt
    top = max(ring.values()) if ring else 1
    for v in bm.verts:
        t = min(1.0, ring.get(v, top) / max(1, min(top, 4)))
        v.co += v.normal * (lift + puff * math.sin(t * math.pi / 2))
    groups = [g.name for g in src.vertex_groups]
    o = _bm_obj(name, bm, None, groups)
    o.data.materials.append(mat(kind))
    seam_attrs(o)
    if thick:
        sm = o.modifiers.new("thick", "SOLIDIFY")
        sm.thickness = thick
        sm.offset = -1.0
        sm.use_rim = True
        sm.use_even_offset = True
        sm.use_quality_normals = True  # plain normals blow the even offset up where a patch folds (a spike off a toe cap)
        kit.hs._apply(o, sm.name)
    o["unwrap"] = True
    o["texel"] = texel
    c.parts.append((o, "DONE", None))
    return o


def seam_attrs(obj, seeds=None, uv_seams=True):
    """`seam` (distance to the nearest seam, m) and `seam_u` (length along it, m) on every vertex:
    stitching runs along the mesh's open edges (hems, cuffs, collars) and its UV seams (the pattern
    pieces). `seeds` overrides the seam edges (a set of (vertex, vertex) index pairs)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    uv = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.active
    if seeds is None:
        seeds = set()
        for e in bm.edges:
            if e.is_boundary:
                seeds.add(e)
            elif uv_seams and uv is not None and len(e.link_faces) == 2:
                f0, f1 = e.link_faces
                for v in e.verts:
                    u0 = next(l[uv].uv for l in f0.loops if l.vert == v)
                    u1 = next(l[uv].uv for l in f1.loops if l.vert == v)
                    if (u0 - u1).length > 1e-5:
                        seeds.add(e)
                        break
    else:
        seeds = {e for e in bm.edges if (e.verts[0].index, e.verts[1].index) in seeds or (e.verts[1].index, e.verts[0].index) in seeds}
    n = len(bm.verts)
    dist = [1.0] * n
    su = [0.0] * n
    # Length along each seam line: walk the seam graph from its ends.
    adj = {}
    for e in seeds:
        a, b = e.verts[0].index, e.verts[1].index
        L = e.calc_length()
        adj.setdefault(a, []).append((b, L))
        adj.setdefault(b, []).append((a, L))
    seen = set()
    for start in sorted(adj, key=lambda i: len(adj[i])):
        if start in seen:
            continue
        stack = [(start, 0.0)]
        seen.add(start)
        while stack:
            v, u = stack.pop()
            su[v] = u
            for w, L in adj[v]:
                if w not in seen:
                    seen.add(w)
                    stack.append((w, u + L))
    heap = [(0.0, v) for v in adj]
    for v in adj:
        dist[v] = 0.0
    heapq.heapify(heap)
    while heap:
        d, v = heapq.heappop(heap)
        if d > dist[v]:
            continue
        for e in bm.verts[v].link_edges:
            w = e.other_vert(bm.verts[v]).index
            nd = d + e.calc_length()
            if nd < dist[w] and nd < 0.05:
                dist[w] = nd
                su[w] = su[v]
                heapq.heappush(heap, (nd, w))
    bm.free()
    for name, vals in (("seam", dist), ("seam_u", su)):
        if name in me.attributes:
            me.attributes.remove(me.attributes[name])
        at = me.attributes.new(name, "FLOAT", "POINT")
        at.data.foreach_set("value", np.array(vals, dtype=np.float32))


# ------------------------------------------------------------------------------- the character

def mat(kind):
    """The character's material of `kind`: a palette kind ("pmc_navy", "primary"...) or
    "<surface>.<tint>" for a surface other than the kind's default that keeps the tint's colour and
    name suffix ("knit.primary" is a rib knit the game still tints as primary)."""
    if "." not in kind:
        return kit.mat(kind)
    surf, tint = kind.split(".", 1)
    full = f"{kit.hs._current['gun']}.{kind}"
    m = bpy.data.materials.get(full)
    if m is None:
        m = kit.mat(tint).copy()
        m.name = full
        m["kind"] = tint
        m["surface_kind"] = kind
    return m


class Char(kit.Char):
    """A kit.Char whose finish bakes the realistic maps: parts registered with `detail` take their
    colour and normals from high-detail meshes (the body sculpt, simulated cloth), everything else
    bakes its procedural surface onto itself. Use `real.begin`."""

    def __init__(self, cid, build):
        super().__init__(cid, build)
        self.highs = []  # (low, [high], {"ext": cage extrusion, "ray": max ray distance})
        self.unders = []  # (cover, depth, erode): skin to drop under garments
        self.body = None

    def hide_under(self, cover, depth=0.04, erode=2):
        """Drop the skin under `cover` (a garment's or layer's game mesh): every body vertex whose
        normal runs into it within `depth`, less `erode` rings at the edges so no gap opens at a hem.
        Done at finish, once every garment has its final shape."""
        self.unders.append((cover, depth, erode))

    def detail(self, low, highs, ext=0.01, ray=0.03):
        """Bake `low`'s maps from `highs` (selected-to-active: rays from `ext` outside `low`, up to
        `ray` long). The highs are dropped after the bake."""
        self.highs.append((low, list(highs), {"ext": ext, "ray": ray}))

    def finish(self, out_dir=kit.OUT, bake=True, budget=(25000, 80000)):
        import time
        t0 = time.time()
        for obj, _, _ in self.parts:
            kit.hs.apply_modifiers(obj)
            if max(obj.dimensions) > 0.9:
                print(f"WARNING {self.id}: part {obj.name} is {max(obj.dimensions):.2f} m across")
        for obj, bones, bone in self.parts:
            if bones == "DONE":
                continue
            elif bones is None and bone is None and self.skin_source is not None:
                kit.transfer(self.skin_source, obj)
            else:
                kit.weigh(self.b, obj, bones, bone)
        if self.covered and self.skin_source is not None:
            kit.drop_covered(self.skin_source, self.covered)
        if self.unders and self.skin_source is not None:
            _drop_under(self.skin_source, self.unders)
        lows = [o for o, _, _ in self.parts if o.type == "MESH" and len(o.data.polygons)]
        for o, _, _ in self.parts:
            if o not in lows:
                bpy.data.objects.remove(o, do_unlink=True)
        for o in lows:
            # World-space meshes (the join keeps the first part's frame), triangulated now so the bake's
            # tangent frames are the ones the exporter writes.
            if o.matrix_world != Matrix():
                o.data.transform(o.matrix_world)
                o.matrix_world = Matrix()
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
            bm.to_mesh(o.data)
            bm.free()
        his = [h for _, hs_, _ in self.highs for h in hs_]
        n = sum(kit.tris(o) for o in lows)
        print(f"{self.id}: {n} tris in {len(lows)} parts", flush=True)
        by = {}
        for o in lows:
            k = o.name.split(".")[0]
            by[k] = by.get(k, 0) + kit.tris(o)
        print("  " + ", ".join(f"{k} {v}" for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:24]), flush=True)
        for o in lows:
            if "texel" not in o:
                o["texel"] = HARD_TEXEL  # hard parts: small, mostly flat colour
        for o in lows + his:
            if "seam" not in o.data.attributes:
                at = o.data.attributes.new("seam", "FLOAT", "POINT")
                at.data.foreach_set("value", np.ones(len(o.data.vertices), dtype=np.float32))
        mats = {m for o in lows + his for m in o.data.materials if m is not None}
        if bake:
            surfaces.unwrap(lows)
            for o in lows + his:
                surfaces.fabric_uvs(o)
            surfaces.layout(lows)
            print(f"  uv layout {time.time() - t0:.0f}s", flush=True)
            detailed = {lo for lo, _, _ in self.highs}
            # Everything without a high mesh bakes onto itself, as one object: Blender bakes each
            # selected object with its own scene sync, which costs seconds per object.
            direct = [o for o in lows if o not in detailed]
            if len(direct) > 1:
                joined = kit.join_skinned(direct, "parts")
                lows = [o for o in lows if o in detailed] + [joined]
                direct = [joined]
            groups = [(direct, None)]
            groups += [([lo], hi, opt) for lo, hi, opt in self.highs if lo in lows]
            imgs = surfaces.bake(self.id, groups)
            print(f"  bake {time.time() - t0:.0f}s", flush=True)
        else:
            imgs = None
        for m in mats:
            surfaces.final(m, imgs)
        for h in his:
            bpy.data.objects.remove(h, do_unlink=True)
        for o in lows:
            if surfaces.FABRIC in o.data.uv_layers:
                o.data.uv_layers.remove(o.data.uv_layers[surfaces.FABRIC])
            for a in ("seam", "seam_u", "face", "eye_r", "eye_a"):
                if a in o.data.attributes:
                    o.data.attributes.remove(o.data.attributes[a])
        if os.environ.get("REAL_BLEND"):
            bpy.ops.wm.save_as_mainfile(filepath=os.environ["REAL_BLEND"], copy=True)
        whole = kit.join_skinned(lows, "whole")
        kit.split(whole)
        for name in kit.MESHES:
            if name in bpy.data.objects:
                bpy.data.objects[name].data.name = name  # not the base mesh's datablock name
        kit.bind(self.arm)
        # Every weapon's hand poses for this rig; the carries put the support hand where they put it
        # on the character's own weapon.
        import grips
        poses = grips.solve(self, out_dir)
        kit.solve_carries(self.b, self.arm, left_rel=grips.carry_frames(poses, carry_weapon(self.id)))
        kit.bake_clips(self.b, self.arm)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{self.id}.glb")
        bpy.ops.object.select_all(action="DESELECT")
        for o in bpy.data.objects:
            o.select_set(True)
        bpy.ops.export_scene.gltf(
            filepath=path, export_format="GLB", use_selection=True, export_apply=False,
            export_animations=True, export_animation_mode="NLA_TRACKS", export_skins=True,
            export_all_influences=False, export_def_bones=False, export_tangents=bool(imgs),
            export_materials="EXPORT", export_image_format="JPEG", export_jpeg_quality=JPEG_QUALITY, export_yup=True,
        )
        share_textures(path)
        # The baked materials step aside (same kinds, so kit.tint still finds them): props the
        # preview adds afterwards (the dummy gun) get flat palette materials of their own.
        for m in mats:
            m.name = m.name + ".baked"
        print(f"wrote {path}: {os.path.getsize(path) // 1024} KB, {n} tris ({time.time() - t0:.0f}s)")
        if not budget[0] <= n <= budget[1]:
            print(f"WARNING {self.id}: {n} triangles, budget {budget[0]}..{budget[1]}")
        return path


def carry_weapon(cid):
    """The two-handed weapon the character's carries are solved on: its loadout from
    assets/characters.toml, or the rifle when that is held in one hand."""
    import tomllib
    with open(os.path.join(kit.ROOT, "assets", "characters.toml"), "rb") as f:
        chars = tomllib.load(f).get("character", {})
    w = chars.get(cid, {}).get("loadout", "rifle")
    return w if w not in ("pistol", "revolver", "fist") else "rifle"


def _drop_under(flesh, unders):
    from mathutils.bvhtree import BVHTree
    me = flesh.data
    n = len(me.vertices)
    hidden = np.zeros(n, dtype=bool)
    for cover, depth, erode in unders:
        cm = cover.data
        mw = cover.matrix_world
        t = BVHTree.FromPolygons([mw @ v.co for v in cm.vertices], [p.vertices[:] for p in cm.polygons])
        under = np.zeros(n, dtype=bool)
        for v in me.vertices:
            loc, _, _, d = t.ray_cast(v.co + v.normal * 0.0005, v.normal, depth)
            if loc is None:
                # Or the cover dips just under the skin here (where the cloth settled tight): the
                # skin would show through it.
                loc, _, _, d = t.ray_cast(v.co + v.normal * 0.0005, -v.normal, 0.012)
            under[v.index] = loc is not None
        nb = [[] for _ in range(n)]
        for e in me.edges:
            a, b = e.vertices
            nb[a].append(b)
            nb[b].append(a)
        for _ in range(erode):
            under = np.array([under[i] and all(under[j] for j in nb[i]) for i in range(n)])
        hidden |= under
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    drop = [f for f in bm.faces if all(hidden[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(me)
    bm.free()


def share_textures(path):
    """Rewrite a glb so every material points at one shared texture per image. Blender's exporter
    writes a texture per material slot (63 for 21 materials on one atlas), and Bevy's loader decodes
    and uploads each texture on its own: 2048 maps times 63."""
    import json
    import struct
    data = open(path, "rb").read()
    jlen = struct.unpack("<I", data[12:16])[0]
    j = json.loads(data[20:20 + jlen])
    tex = j.get("textures", [])
    if not tex:
        return
    first, remap, out = {}, {}, []
    for i, t in enumerate(tex):
        key = json.dumps(t, sort_keys=True)
        if key not in first:
            first[key] = len(out)
            out.append(t)
        remap[i] = first[key]

    def fix(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.endswith("Texture") and isinstance(v, dict) and "index" in v:
                    v["index"] = remap[v["index"]]
                fix(v)
        elif isinstance(o, list):
            for v in o:
                fix(v)
    fix(j.get("materials", []))
    j["textures"] = out
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    rest = data[20 + jlen:]
    total = 12 + 8 + len(js) + len(rest)
    with open(path, "wb") as f:
        f.write(data[:8] + struct.pack("<I", total) + struct.pack("<I", len(js)) + b"JSON" + js + rest)


JPEG_QUALITY = 96
HARD_TEXEL = 0.65


def begin(cid, build):
    """Start a realistic character (`build` is usually an Anatomy)."""
    return Char(cid, build)
