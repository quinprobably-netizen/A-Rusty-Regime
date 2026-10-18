"""Character kit: a skeleton built from each character's proportions, an organic body from metaballs,
garments and armour shelled off that body, hard-surface gear from the weapon kit, distance-based
skinning, the twelve gameplay clips with solved two-hand carries, one baked wear texture per character,
glTF export and a checker.

Blender is Z-up and the character faces -Y with its left side on +X; the glTF exporter turns that into
Y-up facing +Z, which is what the game expects. Units are metres, feet on the ground at the origin.

Hands are modelled closed around a weapon. `prop_hand.R` / `prop_hand.L` are the grip frames: each
bone's head sits where the weapon's `hand_r` / `hand_l` socket goes, the bone points down the barrel
and its Z axis is the weapon's up. The game hangs the third-person weapon on `prop_hand.R` and, in
first person, solves the arms so both prop frames land on the weapon's sockets.
"""

import math
import os
import sys

import bpy  # first: bpy makes bmesh importable
import bmesh  # noqa: E402
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
# The weapon kit (block, cyl, prism, plan, cut, unite, join, screw, label, bake), loaded under its own
# name since both modules are called kit.py.
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("weapon_kit", os.path.join(os.path.dirname(HERE), "weapons", "kit.py"))
hs = importlib.util.module_from_spec(_spec)
sys.modules["weapon_kit"] = hs
_spec.loader.exec_module(hs)

# Hard-surface helpers, re-exported so character modules can say kit.block(...) etc.
block, cyl, prism, plan, tube, ring = hs.block, hs.cyl, hs.prism, hs.plan, hs.tube, hs.ring
cut, unite, join, screw, pin, label, slots, dimples = hs.cut, hs.unite, hs.join, hs.screw, hs.pin, hs.label, hs.slots, hs.dimples
mat = hs.mat

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "assets", "models", "character")
FPS = 24
TEX = 2048

# Character materials on top of the weapon palette. Tinted cloth (primary, secondary, accent) bakes
# near-white so the game's outfit colours multiply over the wear and dirt.
# name: (base color, worn color, metallic, roughness, edge wear 0..1, emission strength)
hs.PALETTE.update({
    "primary": ((0.80, 0.80, 0.80), (0.95, 0.95, 0.93), 0.0, 0.85, 0.25, 0),
    "secondary": ((0.80, 0.80, 0.80), (0.95, 0.95, 0.93), 0.0, 0.85, 0.25, 0),
    "accent": ((0.80, 0.80, 0.80), (0.95, 0.95, 0.93), 0.0, 0.7, 0.35, 0),
    "skin": ((0.62, 0.42, 0.32), (0.66, 0.46, 0.36), 0.0, 0.6, 0.0, 0),
    "skin_pale": ((0.72, 0.60, 0.52), (0.75, 0.63, 0.55), 0.0, 0.55, 0.0, 0),
    "skin_dark": ((0.30, 0.19, 0.13), (0.34, 0.22, 0.15), 0.0, 0.55, 0.0, 0),
    "lips": ((0.45, 0.25, 0.22), (0.45, 0.25, 0.22), 0.0, 0.5, 0.0, 0),
    "eye": ((0.03, 0.03, 0.03), (0.03, 0.03, 0.03), 0.0, 0.1, 0.0, 0),
    "hair": ((0.05, 0.04, 0.035), (0.08, 0.07, 0.06), 0.0, 0.7, 0.0, 0),
    "ink": ((0.02, 0.02, 0.025), (0.06, 0.06, 0.06), 0.0, 0.5, 0.2, 0),
    "bone": ((0.78, 0.75, 0.68), (0.92, 0.90, 0.85), 0.0, 0.42, 0.55, 0),
    "leather": ((0.22, 0.13, 0.07), (0.42, 0.30, 0.20), 0.0, 0.62, 0.5, 0),
    "canvas": ((0.36, 0.33, 0.25), (0.50, 0.47, 0.38), 0.0, 0.9, 0.3, 0),
    "webbing": ((0.10, 0.10, 0.09), (0.20, 0.20, 0.18), 0.0, 0.85, 0.3, 0),
    "oilskin": ((0.20, 0.17, 0.10), (0.36, 0.31, 0.20), 0.0, 0.35, 0.45, 0),
    "slate": ((0.075, 0.075, 0.07), (0.25, 0.24, 0.22), 0.0, 0.6, 0.5, 0),
    "clay": ((0.70, 0.29, 0.18), (0.80, 0.55, 0.45), 0.0, 0.55, 0.6, 0),
    "cream": ((0.86, 0.84, 0.78), (0.95, 0.94, 0.90), 0.0, 0.6, 0.3, 0),
    "kraft": ((0.66, 0.48, 0.32), (0.80, 0.66, 0.52), 0.0, 0.7, 0.4, 0),
    "corp": ((0.12, 0.20, 0.32), (0.40, 0.45, 0.50), 0.0, 0.45, 0.5, 0),
    "white": ((0.85, 0.86, 0.87), (0.95, 0.95, 0.95), 0.0, 0.4, 0.4, 0),
    "gunmetal": ((0.12, 0.125, 0.13), (0.45, 0.45, 0.47), 0.7, 0.4, 0.7, 0),
    "glow_red": ((1.0, 0.08, 0.04), (1.0, 0.08, 0.04), 0.0, 0.3, 0.0, 8.0),
    "glow_white": ((0.9, 0.95, 1.0), (0.9, 0.95, 1.0), 0.0, 0.3, 0.0, 4.0),
    "glow_cyan": ((0.15, 0.85, 1.0), (0.15, 0.85, 1.0), 0.0, 0.3, 0.0, 5.0),
    "glow_amber": ((1.0, 0.55, 0.1), (1.0, 0.55, 0.1), 0.0, 0.3, 0.0, 5.0),
})

# ------------------------------------------------------------------------------------------ skeleton

# The reference skeleton for a 1.80 m build. name: (head, tail, parent). Left side is +X; .R mirrors.
BASE_BONES = {
    "hips": ((0, 0, 0.95), (0, 0, 1.05), None),
    "spine": ((0, 0, 1.05), (0, 0, 1.20), "hips"),
    "chest": ((0, 0, 1.20), (0, 0, 1.42), "spine"),
    "neck": ((0, 0, 1.42), (0, 0, 1.52), "chest"),
    "head": ((0, 0, 1.52), (0, 0, 1.80), "neck"),
    "prop_back": ((0, 0.10, 1.28), (0, 0.10, 1.38), "chest"),
    "shoulder.L": ((0.04, 0, 1.40), (0.17, 0, 1.40), "chest"),
    "upper_arm.L": ((0.17, 0, 1.40), (0.22, 0, 1.12), "shoulder.L"),
    "forearm.L": ((0.22, 0, 1.12), (0.26, -0.02, 0.86), "upper_arm.L"),
    "hand.L": ((0.26, -0.02, 0.86), (0.28, -0.03, 0.74), "forearm.L"),
    "upper_leg.L": ((0.10, 0, 0.95), (0.11, 0, 0.52), "hips"),
    "lower_leg.L": ((0.11, 0, 0.52), (0.11, 0, 0.09), "upper_leg.L"),
    "foot.L": ((0.11, 0, 0.09), (0.11, -0.16, 0.02), "lower_leg.L"),
}
DEFORM = ["hips", "spine", "chest", "neck", "head"] + [b + s for b in ("shoulder.", "upper_arm.", "forearm.", "hand.", "upper_leg.", "lower_leg.", "foot.") for s in ("L", "R")]
ARM_BONES = [b + side for b in ("upper_arm.", "forearm.", "hand.") for side in ("L", "R")]
CLIP_NAMES = ["idle", "walk", "run", "sprint", "jump", "fall", "crouch", "slide", "wallrun_l", "wallrun_r", "mantle", "grapple"]
ALL_BONE_NAMES = [n for n in BASE_BONES] + [n[:-2] + ".R" for n in BASE_BONES if n.endswith(".L")] + ["prop_hand.L", "prop_hand.R"]


class Build:
    """Proportions of one character. `height` is to the top of the head; `width` scales shoulders and
    hips; `bulk` scales limb and torso thickness; `legs` is the fraction of extra height that goes to
    the legs (the rest goes to the torso)."""

    def __init__(self, height=1.80, width=1.0, bulk=1.0, legs=0.55):
        self.height, self.width, self.bulk, self.legs = height, width, bulk, legs
        k = height / 1.80
        self.k = k
        hip_z = 0.95 * (1 + (k - 1) * legs / 0.53)  # legs take `legs` of the change
        torso_k = (height - hip_z) / (1.80 - 0.95)
        self.hip_z = hip_z

        def z(v):
            return v * hip_z / 0.95 if v <= 0.95 else hip_z + (v - 0.95) * torso_k

        def p(v):
            return (v[0] * width, v[1] * k, z(v[2]))
        bones = {}
        for name, (h, t, par) in BASE_BONES.items():
            bones[name] = (p(h), p(t), par)
        # Forearm/hand keep their length ratio with the torso so long torsos get long arms.
        self.bones = bones
        self.all = mirrored(bones)
        # Grip frames (see the module doc): built from the hand bone so they move with the build.
        for s, sx in (("L", 1), ("R", -1)):
            h, t, _ = self.all["hand." + s]
            h, t = Vector(h), Vector(t)
            down = (t - h).normalized()
            palm_in = Vector((-sx, 0, 0))
            if s == "R":
                at = h + down * 0.085 * k + palm_in * 0.034 * k + Vector((0, -0.006, 0))
                fwd, up = down, Vector((0, -1, 0))
            else:
                at = h + down * 0.085 * k + palm_in * 0.040 * k + Vector((0, 0.004, 0))
                fwd, up = Vector((0, -1, 0)), palm_in
            self.all["prop_hand." + s] = (tuple(at), tuple(at + fwd * 0.08), "hand." + s, tuple(up))

    def j(self, name, at=0.0):
        """A point `at` (0 head .. 1 tail) along bone `name`."""
        h, t = Vector(self.all[name][0]), Vector(self.all[name][1])
        return h.lerp(t, at)


def mirrored(bones):
    out = {}
    for name, (h, t, p) in bones.items():
        out[name] = (h, t, p)
        if name.endswith(".L"):
            def m(v):
                return (-v[0], v[1], v[2])
            pr = p[:-2] + ".R" if p and p.endswith(".L") else p
            out[name[:-2] + ".R"] = (m(h), m(t), pr)
    return out


def build_armature(build):
    data = bpy.data.armatures.new("rig")
    arm = bpy.data.objects.new("rig", data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = data.edit_bones
    for name, v in build.all.items():
        b = eb.new(name)
        b.head, b.tail = Vector(v[0]), Vector(v[1])
        if len(v) > 3:
            b.align_roll(Vector(v[3]))
        b.use_deform = name in DEFORM
    for name, v in build.all.items():
        if v[2]:
            eb[name].parent = eb[v[2]]
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


# ------------------------------------------------------------------------------------------ organic

def meta(name, elements, material, res=0.012, target=None, smooth_iter=6):
    """An organic blob: mesh ellipsoids and tapered capsules fused into one watertight surface by a
    voxel remesh of size `res`, smoothed, then decimated to about `target` triangles. Elements come
    from capsule(), ellipsoid() and ball(); ones made with a negative `stiff` are carved out after the
    fuse (eye sockets). Returns a smooth-shaded mesh object."""
    add, sub = [], []
    for e in elements:
        (sub if e[-1] < 0 else add).append(_element(e))
    o = hs.join(add, name)
    m = o.modifiers.new("fuse", "REMESH")
    m.mode = "VOXEL"
    m.voxel_size = res
    m.adaptivity = 0.0
    hs._apply(o, m.name)
    if smooth_iter:
        sm = o.modifiers.new("smooth", "LAPLACIANSMOOTH")
        sm.iterations = smooth_iter
        sm.lambda_factor = 0.6
        sm.use_volume_preserve = True
        hs._apply(o, sm.name)
    for cutter in sub:
        mod = o.modifiers.new("carve", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
        hs._apply(o, mod.name)
        bpy.data.objects.remove(cutter, do_unlink=True)
    if target and tris(o) > target:
        decimate(o, target / tris(o))
    me = o.data
    me.materials.clear()
    me.materials.append(hs.mat(material))
    for poly in me.polygons:
        poly.use_smooth = True
    o["bevel"] = 0.0
    o["shaded"] = True
    return o


def _element(e):
    kind = e[0]
    bm = bmesh.new()
    if kind == "ELL":
        _, c, radii, rot, _ = e
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=14, radius=1.0)
        m = Matrix.Translation(c) @ (rot.to_matrix().to_4x4() if rot else Matrix()) @ Matrix.Diagonal((*radii, 1))
        bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    else:  # CAP: convex hull of two spheres
        _, a, b, r0, r1, _ = e
        for c, r in ((a, r0), (b, r1)):
            t = bmesh.new()
            bmesh.ops.create_uvsphere(t, u_segments=20, v_segments=12, radius=r)
            for v in t.verts:
                bm.verts.new(v.co + Vector(c))
            t.free()
        bmesh.ops.convex_hull(bm, input=bm.verts)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("el")
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("el", me)
    bpy.context.scene.collection.objects.link(o)
    return o


def capsule(a, b, r, stiff=1.0, r1=None):
    """Tapered capsule from a (radius r) to b (radius r1, default r)."""
    return ("CAP", Vector(a), Vector(b), r, r if r1 is None else r1, stiff)


def ellipsoid(c, r, size, rot=None, stiff=1.0):
    """Ellipsoid at c with radii r * size."""
    return ("ELL", Vector(c), tuple(r * s for s in size), rot, stiff)


def ball(c, r, stiff=1.0):
    return ("ELL", Vector(c), (r, r, r), None, stiff)


def decimate(obj, ratio):
    m = obj.modifiers.new("dec", "DECIMATE")
    m.ratio = ratio
    hs._apply(obj, m.name)
    return obj


def tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def smooth(obj, iterations=2, factor=0.5):
    m = obj.modifiers.new("smooth", "SMOOTH")
    m.iterations, m.factor = iterations, factor
    hs._apply(obj, m.name)


def body(b, skin="skin", muscle=1.0, gut=0.0, chest=1.0, neck=1.0, hands=True, head=True):
    """The base body for build `b`: torso, limbs, feet, and (optionally) head and gripping hands as
    separate objects. Returns {"body": obj, "head": obj or None, "hands": obj or None}."""
    k, w, m = b.k, b.width, b.bulk * muscle
    J = b.j
    el = []
    # Pelvis, belly, ribcage, pecs, lats, traps.
    el.append(ellipsoid(J("hips", 0.2) + Vector((0, 0.01, 0)), 0.11 * k, (1.25 * w * m, 0.85 * m, 0.8)))
    el.append(ellipsoid(J("spine", 0.4) + Vector((0, -0.01 - 0.03 * gut, 0)), 0.10 * k, ((1.1 + 0.15 * gut) * w * m, (0.8 + 0.3 * gut) * m, 1.0)))
    el.append(ellipsoid(J("chest", 0.45), 0.13 * k, (1.15 * w * m * chest, 0.75 * m, 1.0)))
    for sx in (1, -1):
        el.append(ellipsoid(J("chest", 0.62) + Vector((sx * 0.06 * w, -0.055 * m * chest, 0)), 0.065 * k, (1.1 * m, 0.6 * m, 0.75), stiff=1.5))
        el.append(ellipsoid(J("chest", 0.5) + Vector((sx * 0.09 * w, 0.03, 0)), 0.07 * k, (0.9 * m, 0.7 * m, 1.1), stiff=1.5))
        el.append(capsule(J("neck", 0.0) + Vector((sx * 0.03, 0.01, -0.01)), J("shoulder." + ("L" if sx > 0 else "R"), 0.9) + Vector((0, 0.01, 0.01)), 0.045 * k * m, stiff=1.5))
        # Glutes.
        el.append(ellipsoid(J("hips", 0.0) + Vector((sx * 0.06 * w, 0.06, -0.05)), 0.075 * k, (1.0 * m, 0.9 * m, 1.0), stiff=1.5))
    el.append(capsule(J("neck", 0.0), J("neck", 1.0) + Vector((0, 0.005, 0)), 0.05 * k * neck * m))
    for s, sx in (("L", 1), ("R", -1)):
        # Deltoid, biceps/triceps, forearm, thigh, calf, knee, ankle, foot.
        el.append(ellipsoid(J("upper_arm." + s, 0.08), 0.06 * k, (1.0 * m, 0.95 * m, 0.95), stiff=1.8))
        el.append(capsule(J("upper_arm." + s, 0.05), J("upper_arm." + s, 0.95), 0.042 * k * m))
        el.append(ellipsoid(J("upper_arm." + s, 0.45) + Vector((0, -0.012, 0)), 0.04 * k, (0.9 * m, 0.9 * m, 1.6), stiff=1.2))
        el.append(capsule(J("forearm." + s, 0.0), J("forearm." + s, 0.95), 0.034 * k * m))
        el.append(ellipsoid(J("forearm." + s, 0.25), 0.04 * k, (0.95 * m, 0.85 * m, 1.6), stiff=1.2))
        el.append(capsule(J("upper_leg." + s, 0.0) + Vector((0, 0, 0.02)), J("upper_leg." + s, 0.97), 0.068 * k * m))
        el.append(ellipsoid(J("upper_leg." + s, 0.3) + Vector((0, -0.01, 0)), 0.075 * k, (0.95 * m, 0.95 * m, 1.6), stiff=1.4))
        el.append(capsule(J("lower_leg." + s, 0.02), J("lower_leg." + s, 0.92), 0.042 * k * m))
        el.append(ellipsoid(J("lower_leg." + s, 0.3) + Vector((0, 0.02, 0)), 0.05 * k, (0.85 * m, 0.95 * m, 1.6), stiff=1.3))
        el.append(ball(J("lower_leg." + s, 0.0) + Vector((0, -0.02, 0)), 0.045 * k * m, stiff=1.2))
        heel = J("foot." + s, 0.0) + Vector((0, 0.035, -0.05 * k))
        toe = J("foot." + s, 1.0) + Vector((0, -0.03, -0.005))
        el.append(capsule(heel, toe, 0.035 * k))
        el.append(ellipsoid(J("foot." + s, 0.65) + Vector((0, 0, -0.02)), 0.04 * k, (1.1, 1.5, 0.6), stiff=1.5))
    out = {"body": meta("body", el, skin, res=0.009 * k, target=12000)}
    out["head"] = head_mesh(b, skin) if head else None
    out["hands"] = hand_meshes(b, skin) if hands else None
    return out


HAND_BONES = ["hand.L", "hand.R", "forearm.L", "forearm.R"]
HEAD_BONES = ["head", "neck", "chest"]


def head_mesh(b, skin="skin", jaw=1.0, brow=1.0, nose=1.0, bald=True):
    """A stylised head: cranium, brow ridge, cheekbones, jaw, nose, ears, eye sockets with eyes."""
    k = b.k
    c = b.j("head", 0.45)
    el = [
        ellipsoid(c + Vector((0, 0.01, 0.015)), 0.105 * k, (0.80, 0.98, 1.0)),
        ellipsoid(c + Vector((0, -0.05, -0.05)), 0.06 * k, (1.0 * jaw, 0.85, 0.85)),  # jaw
        ellipsoid(c + Vector((0, -0.082, -0.08)), 0.026 * k, (1.2 * jaw, 0.8, 0.85)),  # chin
        ellipsoid(c + Vector((0, -0.078, 0.032)), 0.03 * k, (2.0, 0.55 * brow, 0.45 * brow)),  # brow
        capsule(c + Vector((0, -0.094, 0.012)), c + Vector((0, -0.108 * nose, -0.028)), 0.008 * k, r1=0.013 * k),  # nose
        ellipsoid(c + Vector((0, -0.086, -0.062)), 0.022 * k, (1.0, 0.45, 0.35)),  # lips
        capsule(b.j("neck", 0.2), b.j("neck", 1.0) + Vector((0, -0.01, 0.02)), 0.052 * k),
    ]
    for sx in (1, -1):
        el.append(ellipsoid(c + Vector((sx * 0.047, -0.062, -0.022)), 0.026 * k, (1.0, 0.75, 0.7)))  # cheekbone
        el.append(ellipsoid(c + Vector((sx * 0.012, -0.104 * nose, -0.03)), 0.009 * k, (1.0, 0.9, 0.8)))  # nostril
        el.append(ellipsoid(c + Vector((sx * 0.083, 0.005, -0.008)), 0.024 * k, (0.35, 0.75, 1.15)))  # ear
        el.append(ball(c + Vector((sx * 0.034, -0.088, 0.003)), 0.017 * k, stiff=-1.0))  # eye socket
    h = meta("head", el, skin, res=0.004 * k, target=4500, smooth_iter=4)
    eyes = []
    for sx in (1, -1):
        e = _element(("ELL", c + Vector((sx * 0.034, -0.066, 0.003)) * 1.0, (0.0125 * k,) * 3, None, 1.0))
        e.data.materials.append(hs.mat("eye"))
        for p in e.data.polygons:
            p.use_smooth = True
        eyes.append(e)
    return hs.join([h] + eyes, "head")


def hand_meshes(b, material="skin", glove=0.0):
    """Both hands, closed around their grips (see the module doc). `glove` thickens everything for a
    glove shell. Returns one object for both hands."""
    objs = []
    for s, sx in (("L", 1), ("R", -1)):
        objs.append(hand(b, s, material, glove))
    return hs.join(objs, "hands")


def hand(b, s, material="skin", grow=0.0):
    """One hand. Palm block, four curled fingers, thumb. Built in a hand frame: L down the hand, P the
    palm normal, T toward the thumb."""
    k = b.k
    sx = 1 if s == "L" else -1
    wrist = Vector(b.all["hand." + s][0])
    L = (Vector(b.all["hand." + s][1]) - wrist).normalized()
    P = Vector((-sx, 0, 0))
    P = (P - L * P.dot(L)).normalized()
    T = Vector((0, -1, 0))  # thumbs point forward on a hanging hand
    T = (T - L * T.dot(L) - P * T.dot(P)).normalized()
    curl_axis = L.cross(P).normalized()  # rotating L about this bends it toward the palm
    g = grow
    tight = s == "R"
    el = []
    # Palm: thick at the heel, thinner toward the knuckles.
    el.append(ellipsoid(wrist + L * 0.045 * k + P * 0.002, 0.045 * k, (0.55 + g * 8, 0.95 + g * 6, 0.95 + g * 6),
                        rot=Matrix((T, P, L)).transposed().to_quaternion()))
    el.append(capsule(wrist - L * 0.01, wrist + L * 0.03, 0.03 * k + g))
    for i, (off, length) in enumerate(((0.027, 1.0), (0.009, 1.08), (-0.009, 1.02), (-0.026, 0.84))):
        if tight:
            curl = (35, 45, 25) if i == 0 else (80, 88, 60)  # index rests on the trigger
        else:
            curl = (55, 70, 45)
        base = wrist + L * (0.088 * k) + T * off * k
        d = L.copy()
        p = base
        segs = (0.045, 0.028, 0.022)
        r = (0.0105, 0.0095, 0.0085) if i < 3 else (0.0095, 0.0085, 0.0075)
        for seg, rad, ang in zip(segs, r, curl):
            d = (Matrix.Rotation(math.radians(ang), 3, curl_axis) @ d).normalized()
            q = p + d * seg * length * k
            el.append(capsule(p, q, (rad + g) * k, r1=(rad * 0.92 + g) * k))
            el.append(ball(p, (rad + 0.001 + g) * k))
            p = q
    # Thumb: from the heel of the palm, along the barrel for the trigger hand, around the handguard for the other.
    t0 = wrist + L * 0.03 * k + T * 0.022 * k + P * 0.012 * k
    t1 = t0 + (L * 0.6 + T * 0.55 + P * 0.35).normalized() * 0.045 * k
    t2 = t1 + (L * 0.9 + P * (0.35 if tight else 0.6) + T * 0.1).normalized() * 0.035 * k
    t3 = t2 + (L * 0.8 + P * (0.5 if tight else 0.8)).normalized() * 0.026 * k
    el += [capsule(t0, t1, (0.016 + g) * k), capsule(t1, t2, (0.012 + g) * k), capsule(t2, t3, (0.0105 + g) * k)]
    return meta("hand." + s, el, material, res=0.0028 * k, target=2600, smooth_iter=3)


# Weapon-frame helpers for detail that must follow a grip (a trigger finger glove seam etc.) are not
# needed: hands are skinned rigidly to their hand bone.


def shell(src, keep, name, material, offset=0.008, thick=0.004, bevel=0.0, loose=1.0, center=None, smooth_iter=0, bones=None, detail=0.5,
          inside=None, outside=None):
    """A conforming layer: copy `src`, keep the faces whose centre passes `keep(center)` (and, with
    `bones`, whose vertices mostly follow those bones), push it out along the normals by `offset` (or
    scale it away from `center` by `loose`), and give it `thick` thickness. Cloth, armour bases, hoods.
    For clean edges, keep a generous region and trim it with cutter objects: the result keeps only
    what is `inside` every one of them and nothing `outside`-listed (an opening for a face)."""
    me = src.data.copy()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.matrix_world = src.matrix_world
    o.vertex_groups.clear()
    dom = dominant(src) if bones else None
    bm = bmesh.new()
    bm.from_mesh(me)
    keep = keep or (lambda c: True)

    def ok(f):
        if not keep(f.calc_center_median()):
            return False
        return not dom or sum(dom[v.index] in bones for v in f.verts) * 2 >= len(f.verts)
    drop = [f for f in bm.faces if not ok(f)]
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.normal_update()
    for v in bm.verts:
        n = v.normal
        v.co = v.co + n * offset
        if center is not None and loose != 1.0:
            cz = Vector(center)
            d = v.co - Vector((cz.x, cz.y, v.co.z))
            v.co = Vector((cz.x, cz.y, v.co.z)) + d * loose
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    me.materials.append(hs.mat(material))
    if smooth_iter:
        smooth(o, smooth_iter, 0.5)
    if detail < 1.0 and len(me.polygons) > 200:
        decimate(o, detail)
    if thick:
        sm = o.modifiers.new("thick", "SOLIDIFY")
        sm.thickness = thick
        sm.offset = 1.0
        sm.use_even_offset = False
        sm.use_rim = True
        hs._apply(o, sm.name)
    for cutter in inside or ():
        o = intersect(o, cutter)
    for cutter in outside or ():
        o = subtract(o, cutter)
    o["bevel"] = bevel
    o["shaded"] = bevel <= 0
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def blob_cutter(name, c, radii, rot=None):
    """An ellipsoid object to trim shells with (hood openings, mask outlines)."""
    from mathutils import Euler
    q = Euler(tuple(math.radians(a) for a in rot)).to_quaternion() if rot else None
    o = _element(("ELL", Vector(c), tuple(radii), q, 1.0))
    o.name = name
    return o


def intersect(target, cutter):
    """Boolean-intersect `target` with `cutter` (deleted afterwards): crisp plate outlines."""
    mod = target.modifiers.new("isect", "BOOLEAN")
    mod.operation = "INTERSECT"
    mod.solver = "MANIFOLD"  # EXACT returns nothing for these shells
    mod.material_mode = "INDEX"  # cut faces take the target's material
    mod.object = cutter
    hs._apply(target, mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def subtract(target, cutter):
    """Boolean-subtract `cutter` (deleted afterwards); the cut faces keep the target's material."""
    mod = target.modifiers.new("sub", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "MANIFOLD"
    mod.material_mode = "INDEX"
    mod.object = cutter
    hs._apply(target, mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def plate(src, cutter, name, material, offset=0.012, thick=0.008, bevel=0.002, keep=None, bones=None):
    """Armour plate: a thick shell of `src` trimmed to the `cutter` volume (a block, prism or plan
    from the weapon kit), bevelled like the weapon parts."""
    o = shell(src, keep, name, material, offset=offset, thick=thick, bevel=0.0, bones=bones)
    o = intersect(o, cutter)
    o["bevel"] = bevel
    o["segs"] = 2
    o["shaded"] = False
    return o


def strap(name, pts, width, thick, material, up=None, closed=False):
    """A flat strap swept along points; `up` is the strap's face normal hint (default: away from the
    body's vertical axis)."""
    pts = [Vector(p) for p in pts]
    if closed:
        pts.append(pts[0])
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(pts):
        a = pts[max(0, i - 1)]
        c = pts[min(len(pts) - 1, i + 1)]
        tan = (c - a).normalized()
        n = Vector(up) if up else Vector((p.x, p.y, 0)).normalized()
        if n.length < 1e-6:
            n = Vector((0, -1, 0))
        n = (n - tan * n.dot(tan)).normalized()
        side = tan.cross(n).normalized()
        rings.append([bm.verts.new(p + side * sw * width / 2 + n * nn * thick / 2)
                      for sw, nn in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return hs._obj(name, bm, material, bevel=min(width, thick) * 0.25)


def band(name, c, radii, width, thick, material, axis=(0, 0, 1), segs=20):
    """A strap ring around a limb or torso: ellipse at `c` with radii (rx, ry), around `axis`."""
    a = Vector(axis).normalized()
    u = a.cross(Vector((0, 0, 1)) if abs(a.z) < 0.9 else Vector((1, 0, 0))).normalized()
    if abs(a.z) >= 0.9:
        u = Vector((1, 0, 0))
    v = a.cross(u).normalized()
    pts = [Vector(c) + u * radii[0] * math.cos(2 * math.pi * i / segs) + v * radii[1] * math.sin(2 * math.pi * i / segs) for i in range(segs)]
    return strap(name, pts, width, thick, material, up=None, closed=True) if abs(a.z) >= 0.9 else _band_general(name, pts, a, width, thick, material, Vector(c))


def _band_general(name, pts, axis, width, thick, material, c):
    bm = bmesh.new()
    rings = []
    for p in pts:
        n = (p - c)
        n = (n - axis * n.dot(axis)).normalized()
        rings.append([bm.verts.new(p + axis * aw * width / 2 + n * nn * thick / 2) for aw, nn in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for i in range(len(rings)):
        r0, r1 = rings[i], rings[(i + 1) % len(rings)]
        for q in range(4):
            j = (q + 1) % 4
            bm.faces.new((r0[q], r0[j], r1[j], r1[q]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return hs._obj(name, bm, material, bevel=min(width, thick) * 0.25)


def rope(name, pts, r, material, segs=8, twist=True):
    """A rope or cable along points (with a twisted look from a slight spiral of edges)."""
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = r
    curve.bevel_resolution = 2
    curve.resolution_u = 6
    sp = curve.splines.new("POLY" if len(pts) < 3 else "BEZIER")
    if sp.type == "BEZIER":
        sp.bezier_points.add(len(pts) - 1)
        for bp, p in zip(sp.bezier_points, pts):
            bp.co = p
            bp.handle_left_type = bp.handle_right_type = "AUTO"
    else:
        sp.points.add(len(pts) - 1)
        for pp, p in zip(sp.points, pts):
            pp.co = (*p, 1)
    o = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(o, do_unlink=True)
    out = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(out)
    me.materials.clear()
    me.materials.append(hs.mat(material))
    for p in me.polygons:
        p.use_smooth = True
    out["bevel"] = 0.0
    out["shaded"] = True
    return out


def mirror_x(obj, name=None):
    """A mirrored copy across X (left/right gear)."""
    me = obj.data.copy()
    me.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
    me.flip_normals()
    o = bpy.data.objects.new(name or obj.name, me)
    bpy.context.scene.collection.objects.link(o)
    for key in ("bevel", "segs", "shaded"):
        if key in obj:
            o[key] = obj[key]
    return o


def place(obj, at=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    """Bake a transform into a part's mesh (rot in degrees, XYZ)."""
    m = Matrix.Translation(at) @ Matrix.Rotation(math.radians(rot[2]), 4, "Z") @ Matrix.Rotation(math.radians(rot[1]), 4, "Y") @ Matrix.Rotation(math.radians(rot[0]), 4, "X") @ Matrix.Scale(scale, 4)
    obj.data.transform(m)
    return obj


# -------------------------------------------------------------------------------------- the character

class Char:
    """One character being built: its build, armature, and parts tagged for skinning."""

    def __init__(self, cid, build):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        hs._current["gun"] = cid
        self.id = cid
        self.b = build
        self.scene = bpy.context.scene
        self.scene.render.fps = FPS
        self.arm = build_armature(build)
        self.parts = []  # (obj, bones or None for automatic, rigid bone or None)
        self.skin_source = None
        self.covered = []  # (bones, keep) regions of skin hidden under clothes

    def flesh(self, obj):
        """The watertight body: weighted by Blender's bone heat, and the source every `add`ed part
        copies its weights from."""
        self.skin_source = obj
        heat(self.arm, obj)
        self.parts.append((obj, "DONE", None))
        return obj

    def add(self, obj, bones=None):
        """Skin `obj`: copy weights from the nearest point of the body (`flesh`), or, with `bones`,
        by distance to those bones only."""
        self.parts.append((obj, bones, None))
        return obj

    def cover(self, bones, keep=None):
        """Drop the body's skin under clothes in these bone regions (where `keep(center)` is true), so
        it cannot poke through when the joints bend."""
        self.covered.append((set(bones), keep or (lambda c: True)))

    def rigid(self, obj, bone):
        """Bind `obj` wholly to one bone (helmets, armour plates, hands, gear)."""
        self.parts.append((obj, None, bone))
        return obj

    def finish(self, out_dir=OUT, bake=True, budget=(25000, 75000)):
        for obj, _, _ in self.parts:
            hs.apply_modifiers(obj)
            dims = obj.dimensions
            if max(dims) > 0.9:
                print(f"WARNING {self.id}: part {obj.name} is {max(dims):.2f} m across")
        for obj, bones, bone in self.parts:
            if bones == "DONE":
                continue
            elif bones is None and bone is None and self.skin_source is not None:
                transfer(self.skin_source, obj)
            else:
                weigh(self.b, obj, bones, bone)
        if self.covered and self.skin_source is not None:
            drop_covered(self.skin_source, self.covered)
        whole = join_skinned([o for o, _, _ in self.parts], "whole")
        n = tris(whole)
        print(f"{self.id}: {n} tris")
        if bake:
            hs.bake_wear(self, [whole], scale=8.0)
        split(whole)
        bind(self.arm)
        solve_carries(self.b, self.arm)
        bake_clips(self.b, self.arm)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{self.id}.glb")
        bpy.ops.object.select_all(action="DESELECT")
        for o in bpy.data.objects:
            o.select_set(True)
        bpy.ops.export_scene.gltf(
            filepath=path, export_format="GLB", use_selection=True, export_apply=False,
            export_animations=True, export_animation_mode="NLA_TRACKS", export_skins=True,
            export_all_influences=False, export_def_bones=False,
            export_materials="EXPORT", export_image_format="JPEG", export_jpeg_quality=88, export_yup=True,
        )
        print(f"wrote {path}: {os.path.getsize(path) // 1024} KB, {n} tris")
        if not budget[0] <= n <= budget[1]:
            print(f"WARNING {self.id}: {n} triangles, budget {budget[0]}..{budget[1]}")
        return path


def begin(cid, build):
    return Char(cid, build)


# --------------------------------------------------------------------------------------- skinning

def seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    return (a + ab * t - p).length


def weights_at(build, p, bones=None, blend=0.05):
    """Distance-based weights: the nearest bone segment, blended with the next one within `blend`.
    Bones on the other side of the body are never candidates."""
    cands = bones or DEFORM
    side_l = p.x > 0.03
    side_r = p.x < -0.03
    ds = []
    for bn in cands:
        if (bn.endswith(".R") and side_l) or (bn.endswith(".L") and side_r):
            continue
        h, t = Vector(build.all[bn][0]), Vector(build.all[bn][1])
        d = seg_dist(p, h, t)
        if bn == "shoulder.L" or bn == "shoulder.R":
            d += 0.02  # the deltoid belongs to the upper arm
        if bn == "neck":
            d += 0.01
        ds.append((d, bn))
    ds.sort()
    d1, b1 = ds[0]
    out = {b1: 1.0}
    for d2, b2 in ds[1:3]:
        if d2 < d1 + blend:
            out[b2] = (1.0 - (d2 - d1) / blend) * 0.7
    s = sum(out.values())
    return {k: v / s for k, v in out.items()}


def weigh(build, obj, bones, rigid_bone):
    obj.vertex_groups.clear()
    groups = {}

    def group(name):
        if name not in groups:
            groups[name] = obj.vertex_groups.new(name=name)
        return groups[name]
    if rigid_bone:
        group(rigid_bone).add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
        return
    mw = obj.matrix_world
    for v in obj.data.vertices:
        for bn, w in weights_at(build, mw @ v.co, bones).items():
            group(bn).add([v.index], w, "REPLACE")


def heat(arm, obj):
    """Bone-heat weights from the deforming bones (needs a watertight mesh)."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    mw = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = mw
    for m in list(obj.modifiers):
        obj.modifiers.remove(m)
    if not obj.vertex_groups or not any(v.groups for v in obj.data.vertices[:50]):
        print("WARNING bone heat failed; falling back to distance weights")


def transfer(src, obj):
    """Copy vertex weights from the nearest face of `src`."""
    for g in src.vertex_groups:
        if g.name not in obj.vertex_groups:
            obj.vertex_groups.new(name=g.name)
    m = obj.modifiers.new("weights", "DATA_TRANSFER")
    m.object = src
    m.use_vert_data = True
    m.data_types_verts = {"VGROUP_WEIGHTS"}
    m.vert_mapping = "POLYINTERP_NEAREST"
    m.layers_vgroup_select_src = "ALL"
    m.layers_vgroup_select_dst = "NAME"
    hs._apply(obj, m.name)


def drop_covered(flesh, regions):
    dom = dominant(flesh)
    bm = bmesh.new()
    bm.from_mesh(flesh.data)
    drop = []
    for f in bm.faces:
        c = f.calc_center_median()
        for bones, keep in regions:
            if all(dom[v.index] in bones for v in f.verts) and keep(c):
                drop.append(f)
                break
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(flesh.data)
    bm.free()


def join_skinned(objs, name):
    objs = [o for o in objs if o is not None and o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    objs[0].name = name
    return objs[0]


def dominant(obj):
    names = {g.index: g.name for g in obj.vertex_groups}
    out = []
    for v in obj.data.vertices:
        best = max(v.groups, key=lambda g: g.weight, default=None)
        out.append(names[best.group] if best else "hips")
    return out


HEAD_GROUP = {"head", "neck"}
MESHES = ("mesh.body", "mesh.head", "fp.arms")


def split(whole):
    """Cut the joined character into `body`, `head` (what the player's own camera must not see) and
    `fp.arms` (a copy of the arms for the first-person view)."""
    dom = dominant(whole)
    head_faces = {p.index for p in whole.data.polygons if sum(dom[i] in HEAD_GROUP for i in p.vertices) * 2 > len(p.vertices)}
    arm_faces = {p.index for p in whole.data.polygons if all(dom[i] in ARM_BONES for i in p.vertices)}

    def part(name, keep):
        me = whole.data.copy()
        o = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(o)
        for g in whole.vertex_groups:
            o.vertex_groups.new(name=g.name)
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep(f.index)], context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bm.to_mesh(me)
        bm.free()
        return o
    part("mesh.body", lambda i: i not in head_faces)
    part("mesh.head", lambda i: i in head_faces)
    part("fp.arms", lambda i: i in arm_faces)
    bpy.data.objects.remove(whole, do_unlink=True)


def bind(arm):
    for o in list(bpy.data.objects):
        if o.type == "MESH" and o.name in MESHES:
            o.parent = arm
            o.modifiers.new("rig", "ARMATURE").object = arm


# ------------------------------------------------------------------------------------- arm solver

def apply_pose(arm, pose):
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"  # pose bones default to quaternions, which would ignore the euler
        rot = pose.get(pb.name, (0, 0, 0))
        pb.rotation_euler = tuple(math.radians(a) for a in rot)
        if pb.name == "hips":
            pb.location = pose.get("hips.loc", (0, 0, 0))
    bpy.context.view_layer.update()


def bone_frame(arm, bone):
    """(position, forward, up) of a bone in armature space in the current pose."""
    m = arm.pose.bones[bone].matrix
    return m.translation.copy(), m.col[1].to_3d().normalized(), m.col[2].to_3d().normalized()


RIGHT_DOFS = [("upper_arm.R", 0, -140, 40), ("upper_arm.R", 1, -90, 90), ("upper_arm.R", 2, -40, 70),
              ("forearm.R", 0, -150, 0), ("forearm.R", 1, -100, 100), ("hand.R", 0, -90, 90), ("hand.R", 1, -90, 90), ("hand.R", 2, -60, 60)]
LEFT_DOFS = [("upper_arm.L", 0, -150, 40), ("upper_arm.L", 1, -90, 90), ("upper_arm.L", 2, -70, 40),
             ("forearm.L", 0, -150, 0), ("forearm.L", 1, -100, 100), ("hand.L", 0, -90, 90), ("hand.L", 1, -90, 90), ("hand.L", 2, -60, 60)]


def descend(arm, pose, dofs, cost, step=24.0):
    """Coordinate descent on the listed (bone, axis, lo, hi) angles until the cost stops dropping."""
    for b, _, _, _ in dofs:
        pose.setdefault(b, (0, 0, 0))
    apply_pose(arm, pose)
    best = cost()
    while step >= 0.5:
        improved = False
        for b, ax, lo, hi in dofs:
            for delta in (step, -step):
                old = pose[b]
                new = list(old)
                new[ax] = max(lo, min(hi, old[ax] + delta))
                if new[ax] == old[ax]:
                    continue
                pose[b] = tuple(new)
                apply_pose(arm, pose)
                c = cost()
                if c < best - 1e-7:
                    best = c
                    improved = True
                    break
                pose[b] = old
        if not improved:
            step *= 0.5
    apply_pose(arm, pose)
    return best


# Distance from the trigger-hand grip to the support-hand grip along a long gun, and how far above.
SUPPORT = (0.30, 0.035)


def solve_rifle_arms(arm, base, grip, fwd, start=None):
    """Arm angles that put prop_hand.R at `grip` pointing along `fwd` with the gun upright, and
    prop_hand.L on the handguard, on top of the `base` body pose."""
    pose = {k: v for k, v in base.items() if k not in ARM_BONES}
    pose.update(start or {"upper_arm.R": (-50, 0, 10), "forearm.R": (-100, 0, 0), "upper_arm.L": (-70, 0, -10), "forearm.L": (-70, 0, 0)})
    grip, fwd = Vector(grip), Vector(fwd).normalized()
    side = fwd.cross(Vector((0, 0, 1))).normalized()
    up = side.cross(fwd).normalized()

    def right_cost():
        p, f, u = bone_frame(arm, "prop_hand.R")
        return (p - grip).length_squared * 60 + (1 - f.dot(fwd)) * 10 + (1 - u.dot(up)) * 4.0

    def left_cost():
        p, f, u = bone_frame(arm, "prop_hand.R")
        target = p + f * SUPPORT[0] + u * SUPPORT[1]
        q, lf, lu = bone_frame(arm, "prop_hand.L")
        return (q - target).length_squared * 60 + (1 - lf.dot(f)) * 1.0 + (1 - lu.dot(u)) * 1.0

    def multistart(dofs, cost, starts):
        best, best_pose = None, None
        for st in starts:
            for b, v in st.items():
                pose[b] = v
            c = min(descend(arm, pose, dofs, cost) for _ in range(2))
            if best is None or c < best:
                best, best_pose = c, {b: pose[b] for b, *_ in dofs}
        pose.update(best_pose)
        apply_pose(arm, pose)
        return best

    right_starts = [{k: v for k, v in (start or {}).items() if k.endswith(".R")}] if start else []
    right_starts += [{"upper_arm.R": (ua, 0, 10), "forearm.R": (fa, 0, 0), "hand.R": (hx, 0, 0)}
                     for ua in (-30, -60, -90) for fa in (-60, -100, -130) for hx in (-60, 0)]
    r = multistart(RIGHT_DOFS, right_cost, right_starts)
    left_starts = [{k: v for k, v in (start or {}).items() if k.endswith(".L")}] if start else []
    left_starts += [{"upper_arm.L": (ua, 0, rz), "forearm.L": (fa, 0, 0), "hand.L": (0, 0, 0)}
                    for ua in (-40, -70, -100) for fa in (-40, -80) for rz in (-10, 20)]
    l = multistart(LEFT_DOFS, left_cost, left_starts)
    p, _, _ = bone_frame(arm, "prop_hand.R")
    print(f"  carry: right {r:.4f} left {l:.4f}, grip err {(p - grip).length:.3f} m")
    return {b: pose[b] for b in ARM_BONES}


# Two-hand carries per body pose: (grip position, muzzle direction) for the 1.80 m build, armature space.
CARRIES = {
    "ready": ((-0.10, -0.24, 1.08), (0.0, -0.92, -0.40)),
    "run": ((-0.08, -0.22, 1.16), (0.0, -0.96, -0.28)),
    "sprint": ((-0.06, -0.19, 1.22), (0.15, -0.85, -0.50)),
    "crouch": ((-0.10, -0.32, 0.74), (0.0, -0.95, -0.30)),
    "slide": ((-0.10, -0.26, 0.60), (0.0, -0.90, 0.40)),
}
ARMS = {}


def solve_carries(build, arm):
    k = build.k
    bases = {"ready": clip_walk(build, 0.0), "run": clip_run(build, 0.0), "sprint": clip_sprint(build, 0.0),
             "crouch": clip_crouch(build, 0.0), "slide": clip_slide(build, 0.0)}
    ARMS.clear()
    prev = None
    for name, (grip, fwd) in CARRIES.items():
        g = (grip[0] * build.width, grip[1] * k, grip[2] * k)
        ARMS[name] = solve_rifle_arms(arm, bases[name], g, fwd, start=prev)
        prev = dict(ARMS[name])
    apply_pose(arm, {})


# -------------------------------------------------------------------------------------- animation

def S(t, phase=0.0):
    return math.sin(2 * math.pi * t + phase)


def gait(b, t, leg, knee, arm, elbow, lean, bob, carry=None):
    """A walk/run cycle. Legs swing about local X: negative is forward, knees bend positive.
    With `carry`, the arms hold the weapon in that carry instead of swinging."""
    p = {}
    for s, sign in (("L", 1), ("R", -1)):
        sw = S(t) * sign
        p["upper_leg." + s] = (-leg * sw, 0, 0)
        p["lower_leg." + s] = (knee * max(0.0, S(t, 1.1) * sign), 0, 0)
        p["foot." + s] = (-12 * max(0.0, S(t, 2.2) * sign) + 6, 0, 0)
        p["upper_arm." + s] = (arm * sw, 0, 0)
        p["forearm." + s] = (-elbow - 10 * max(0.0, sw), 0, 0)
    if carry and carry in ARMS:
        p.update(ARMS[carry])
    p["spine"] = (lean, 0, -4 * S(t))
    p["chest"] = (lean * 0.5, 0, 6 * S(t))
    p["head"] = (-lean * 0.8, 0, 0)
    p["hips"] = (0, -3 * S(t), 0)
    p["hips.loc"] = (0, (-bob * abs(S(t)) + bob * 0.5) * b.k, 0)
    return p


def with_arms(p, carry):
    if carry in ARMS:
        p.update(ARMS[carry])
    return p


def clip_idle(b, t):
    s = S(t * 0.5)
    return with_arms({"spine": (3, 0, 0), "chest": (2 * s, 0, 0), "head": (-1.5 * s, 0, 2 * S(t * 0.25))}, "ready")


def clip_walk(b, t):
    return gait(b, t, leg=24, knee=32, arm=18, elbow=15, lean=3, bob=0.02, carry="ready")


def clip_run(b, t):
    return gait(b, t, leg=42, knee=78, arm=34, elbow=70, lean=11, bob=0.04, carry="run")


def clip_sprint(b, t):
    return gait(b, t, leg=54, knee=95, arm=44, elbow=85, lean=17, bob=0.05, carry="sprint")


def clip_jump(b, t):
    k = min(1.0, t * 3)
    return with_arms({"upper_leg.L": (-35 * k, 0, 0), "upper_leg.R": (-20 * k, 0, 0),
                      "lower_leg.L": (55 * k, 0, 0), "lower_leg.R": (40 * k, 0, 0), "spine": (6, 0, 0)}, "run")


def clip_fall(b, t):
    return with_arms({"upper_leg.L": (-10, 0, 0), "upper_leg.R": (10, 0, 0),
                      "lower_leg.L": (25, 0, 0), "lower_leg.R": (30, 0, 0), "spine": (-5, 0, 0)}, "ready")


def clip_crouch(b, t):
    s = S(t * 0.5)
    return with_arms({"hips.loc": (0, -0.34 * b.hip_z / 0.95, 0), "upper_leg.L": (-72, 0, -6), "upper_leg.R": (-72, 0, 6),
                      "lower_leg.L": (108, 0, 0), "lower_leg.R": (108, 0, 0), "foot.L": (-30, 0, 0), "foot.R": (-30, 0, 0),
                      "spine": (24 + s, 0, 0), "chest": (6, 0, 0), "head": (-12, 0, 0)}, "crouch")


def clip_slide(b, t):
    return with_arms({"hips.loc": (0, -0.50 * b.hip_z / 0.95, 0), "hips": (-20, 0, 0),
                      "upper_leg.L": (-70, 0, -8), "upper_leg.R": (-45, 0, 8), "lower_leg.L": (15, 0, 0), "lower_leg.R": (70, 0, 0),
                      "foot.L": (-20, 0, 0), "foot.R": (-10, 0, 0), "spine": (12, 0, 0), "chest": (4, 0, 0), "head": (-10, 0, 0)}, "slide")


def wallrun(b, t, side):
    p = gait(b, t, leg=38, knee=70, arm=20, elbow=60, lean=8, bob=0.02, carry="run")
    p["hips"] = (0, 0, -14 * side)
    p["spine"] = (8, 0, -6 * side)
    p["head"] = (-6, 0, 10 * side)
    return p


def clip_wallrun_l(b, t):
    return wallrun(b, t, 1)


def clip_wallrun_r(b, t):
    return wallrun(b, t, -1)


def clip_mantle(b, t):
    # Left hand on the ledge, right keeps the weapon; pull up, then a knee comes over.
    k = min(1.0, t * 2.0)
    step = max(0.0, (t - 0.5) * 2.0)
    p = with_arms({"upper_leg.L": (-20 - 70 * step, 0, -5), "upper_leg.R": (-10 - 20 * k, 0, 5),
                   "lower_leg.L": (30 + 60 * step, 0, 0), "lower_leg.R": (40, 0, 0),
                   "spine": (25 - 10 * k, 0, 0), "chest": (10, 0, 0), "head": (-18 + 10 * k, 0, 0)}, "run")
    p["upper_arm.L"] = (-165 + 60 * k, 0, -15)
    p["forearm.L"] = (-20 - 50 * k, 0, 0)
    p["hand.L"] = (0, 0, 0)
    return p


def clip_grapple(b, t):
    # Left arm out along the rope, right hand keeps the weapon, legs trailing.
    p = with_arms({"upper_leg.L": (15, 0, -6), "upper_leg.R": (-5, 0, 6), "lower_leg.L": (35, 0, 0), "lower_leg.R": (55, 0, 0),
                   "spine": (18, 0, 0), "chest": (8, 0, 0), "head": (-14, 0, 0)}, "run")
    p["upper_arm.L"] = (-150, 0, -10)
    p["forearm.L"] = (-10, 0, 0)
    p["hand.L"] = (-20, 0, 0)
    return p


CLIPS = {
    "idle": (clip_idle, 96), "walk": (clip_walk, 24), "run": (clip_run, 20), "sprint": (clip_sprint, 18),
    "jump": (clip_jump, 24), "fall": (clip_fall, 48), "crouch": (clip_crouch, 96), "slide": (clip_slide, 48),
    "wallrun_l": (clip_wallrun_l, 20), "wallrun_r": (clip_wallrun_r, 20), "mantle": (clip_mantle, 24), "grapple": (clip_grapple, 48),
}
assert list(CLIPS) == CLIP_NAMES


def bake_clips(build, arm):
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
    arm.animation_data_create()
    for name, (fn, frames) in CLIPS.items():
        action = bpy.data.actions.new(name)
        arm.animation_data.action = action
        if hasattr(arm.animation_data, "action_slot") and len(action.slots) == 0:
            slot = action.slots.new(arm.id_type, arm.name)
            arm.animation_data.action_slot = slot
        for f in range(frames + 1):
            pose = fn(build, f / frames)
            for pb in arm.pose.bones:
                if pb.name.startswith("prop_"):
                    continue
                rot = pose.get(pb.name, (0, 0, 0))
                pb.rotation_euler = tuple(math.radians(a) for a in rot)
                pb.keyframe_insert("rotation_euler", frame=f)
                if pb.name == "hips":
                    pb.location = pose.get("hips.loc", (0, 0, 0))
                    pb.keyframe_insert("location", frame=f)
        action.use_fake_user = True
        arm.animation_data.action = None
        track = arm.animation_data.nla_tracks.new()
        track.name = name
        strip = track.strips.new(name, 0, action)
        if hasattr(strip, "action_slot") and len(action.slots):
            strip.action_slot = action.slots[0]
        track.mute = True
    bpy.ops.object.mode_set(mode="OBJECT")
    apply_pose(arm, {})


# ---------------------------------------------------------------------------------------- preview

def dummy_gun(arm):
    """A stand-in rifle on prop_hand.R for look-dev renders: grip at the bone head, barrel down the
    bone, a block where the support hand goes."""
    if "dummy_gun" in bpy.data.objects:
        return
    parts = [hs.block("g", (0, 0.1, 0.06), (0.05, 0.75, 0.07), "black", bevel=0.004),
             hs.block("g", (0, -0.01, -0.04), (0.03, 0.04, 0.12), "black", bevel=0.004, rot=-18),
             hs.block("g", (0, SUPPORT[0], SUPPORT[1] - 0.005), (0.05, 0.12, 0.05), "red", bevel=0.004)]
    g = hs.join(parts, "dummy_gun")
    hs.apply_modifiers(g)
    # Bone space: Y down the bone (barrel), Z up. Our blocks are built in gun space (Y fwd, Z up).
    g.parent = arm
    g.parent_type = "BONE"
    g.parent_bone = "prop_hand.R"
    g.matrix_parent_inverse = Matrix()
    g.location = (0, -arm.data.bones["prop_hand.R"].length, 0)  # bone parenting sits at the tail


def tint(colors):
    """Multiply the outfit colours over the tinted cloth, like the game does: {"primary": "#rrggbb"}."""
    for m in bpy.data.materials:
        kind = m.get("kind")
        if kind not in colors or not m.use_nodes:
            continue
        h = colors[kind].lstrip("#")
        rgb = [((int(h[i:i + 2], 16) / 255) + 0.055) / 1.055 for i in (0, 2, 4)]
        rgb = [c ** 2.4 for c in rgb]  # sRGB to linear
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        inp = bsdf.inputs["Base Color"]
        if inp.is_linked:
            if any(n.name == "tint" for n in nt.nodes):
                nt.nodes["tint"].inputs[7].default_value = (*rgb, 1)
                continue
            mix = nt.nodes.new("ShaderNodeMix")
            mix.name = "tint"
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            nt.links.new(inp.links[0].from_socket, mix.inputs[6])
            mix.inputs[7].default_value = (*rgb, 1)
            nt.links.new(mix.outputs[2], inp)
        else:
            inp.default_value = (*rgb, 1)


def preview(path, clip="idle", frame=0, cam=(1.9, -2.9, 1.25), look=None, lens=55, res=(720, 960), show_fp=False, gun=True, colors=None):
    """Look-dev render (not shipped). Default: three-quarter front view of the idle pose."""
    scene = bpy.context.scene
    arm = bpy.data.objects["rig"]
    if colors:
        tint(colors)
    if gun:
        dummy_gun(arm)
    for o in bpy.data.objects:
        if o.name == "fp.arms":
            o.hide_render = not show_fp
        if show_fp and o.name in ("mesh.body", "mesh.head"):
            o.hide_render = True
    if arm.animation_data:
        for track in arm.animation_data.nla_tracks:
            track.mute = track.name != clip
    scene.frame_set(frame)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = False
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.filepath = path
    if "preview_cam" not in bpy.data.objects:
        cd = bpy.data.cameras.new("preview_cam")
        cd.clip_start = 0.01
        c = bpy.data.objects.new("preview_cam", cd)
        scene.collection.objects.link(c)
        scene.camera = c
        for name, kind, energy, rot in (("key", "SUN", 3.5, (50, 10, -30)), ("rim", "SUN", 2.0, (60, 0, 150))):
            ld = bpy.data.lights.new(name, kind)
            ld.energy = energy
            lo = bpy.data.objects.new(name, ld)
            lo.rotation_euler = tuple(math.radians(a) for a in rot)
            scene.collection.objects.link(lo)
        floor = bpy.data.meshes.new("floor")
        floor.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
        fo = bpy.data.objects.new("floor", floor)
        scene.collection.objects.link(fo)
        fm = bpy.data.materials.new("floor")
        fm.use_nodes = True
        fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.35, 0.36, 0.34, 1)
        floor.materials.append(fm)
        scene.world = bpy.data.worlds.new("w")
        scene.world.use_nodes = True
        scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.55, 0.62, 1)
        scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.7
    c = bpy.data.objects["preview_cam"]
    c.data.lens = lens
    c.location = cam
    look = look or (0, 0, bpy.data.objects["rig"].data.bones["chest"].head_local.z * 0.82)
    c.rotation_euler = (Vector(look) - Vector(cam)).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.render.render(write_still=True)


# ------------------------------------------------------------------------------------------ check

def check(path, budget=(25000, 75000)):
    """Verify a character glb: the shared bone names, every clip, body/head/fp.arms skinned meshes,
    the triangle budget."""
    j, _ = hs.read_glb(path)
    names = {n.get("name", "") for n in j["nodes"]}
    problems = [f"missing bone {b}" for b in ALL_BONE_NAMES if b not in names]
    problems += [f"missing mesh {m}" for m in MESHES if m not in names]
    for n in j["nodes"]:
        if n.get("name") in MESHES and "skin" not in n:
            problems.append(f"{n['name']} is not skinned")
    anims = {a["name"] for a in j.get("animations", [])}
    problems += [f"missing clip {c}" for c in CLIP_NAMES if c not in anims]
    order = [a["name"] for a in j.get("animations", [])]
    if order != CLIP_NAMES:
        problems.append(f"clip order {order}")

    def tri(mesh):
        return sum(j["accessors"][p["indices"]]["count"] // 3 for p in j["meshes"][mesh]["primitives"])
    total = sum(tri(n["mesh"]) for n in j["nodes"] if "mesh" in n and n.get("name") in MESHES[:2])
    if not budget[0] <= total <= budget[1]:
        problems.append(f"{total} triangles, want {budget[0]}..{budget[1]}")
    return problems, {"tris": total, "kb": os.path.getsize(path) // 1024}


# ----------------------------------------------------------------------------------- body regions

L, R = ".L", ".R"
TORSO = {"hips", "spine", "chest", "shoulder.L", "shoulder.R"}
UPPER_ARMS = {"upper_arm.L", "upper_arm.R"}
FOREARMS = {"forearm.L", "forearm.R"}
THIGHS = {"upper_leg.L", "upper_leg.R"}
SHINS = {"lower_leg.L", "lower_leg.R"}
FEET = {"foot.L", "foot.R"}
NECK = {"neck"}


def side(bones, s):
    """Only the bones of one side ("L" or "R") from a region."""
    return {b for b in bones if b.endswith("." + s)}


def slab(name, pts, y0, y1, material="steel", bevel=0.0, segs=2):
    """Extrude a front-view outline [(x, z), ...] along Y from y0 to y1: plate outlines, cutters."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y0, z)) for x, z in pts]
    face = bm.faces.new(vs)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, y1 - y0, 0), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return hs._obj(name, bm, material, bevel, segs)


def rounded(pts, r=0.02, n=3):
    """Round the corners of a polygon outline [(a, b), ...] with arcs of radius r."""
    out = []
    m = len(pts)
    for i in range(m):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % m])
        d0, d1 = (p0 - p1).normalized(), (p2 - p1).normalized()
        rr = min(r, (p0 - p1).length / 2.1, (p2 - p1).length / 2.1)
        a, b = p1 + d0 * rr, p1 + d1 * rr
        for t in range(n + 1):
            u = t / n
            q = a.lerp(p1, u).lerp(p1.lerp(b, u), u)  # quadratic bezier through the corner
            out.append((q.x, q.y))
    return out


def label_front(text, at, size, material, depth=0.002, facing=(0, -1, 0)):
    """Raised lettering facing `facing` (default the front, -Y; (0, 1, 0) for the back)."""
    o = hs.label(text, (0, 0, 0), size, material, side=-1, depth=depth)
    yaw = math.degrees(math.atan2(facing[1], facing[0])) - 180.0  # the weapon label faces -X
    return place(o, at, (0, 0, yaw))
