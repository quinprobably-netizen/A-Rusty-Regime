"""Build Rust Regime's character: rig, body, clothes and animation clips, as one glTF.

Runs inside Blender's Python (`bpy`), headless:

    tools/character/build.sh            # builds assets/models/character/character.glb + previews
    tools/character/build.sh --check    # re-imports the glb and verifies bones, parts and clips

Everything is procedural low-poly geometry so the look is ours and reproducible. Blender is Z-up and the
character faces -Y here; the glTF exporter turns that into Y-up, facing +Z, which is what body.rs expects.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "models", "character", "character.glb")
SHOTS = os.path.join(ROOT, "screenshots")

# ----------------------------------------------------------------------------------------------- rig

# name: (head, tail, parent). Metres, Z up, -Y forward. Left side is +X; the right side is mirrored.
BONES = {
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
    "prop_hand.L": ((0.27, -0.06, 0.80), (0.27, -0.14, 0.80), "hand.L"),
    "upper_leg.L": ((0.10, 0, 0.95), (0.11, 0, 0.52), "hips"),
    "lower_leg.L": ((0.11, 0, 0.52), (0.11, 0, 0.09), "upper_leg.L"),
    "foot.L": ((0.11, 0, 0.09), (0.11, -0.16, 0.02), "lower_leg.L"),
}


def mirrored():
    out = {}
    for name, (h, t, p) in BONES.items():
        out[name] = (h, t, p)
        if name.endswith(".L"):
            m = lambda v: (-v[0], v[1], v[2])
            pr = p[:-2] + ".R" if p and p.endswith(".L") else p
            out[name[:-2] + ".R"] = (m(h), m(t), pr)
    return out


ALL_BONES = mirrored()


def build_armature():
    arm_data = bpy.data.armatures.new("rig")
    arm = bpy.data.objects.new("rig", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    for name, (h, t, _) in ALL_BONES.items():
        b = eb.new(name)
        b.head, b.tail = Vector(h), Vector(t)
    for name, (_, _, p) in ALL_BONES.items():
        if p:
            eb[name].parent = eb[p]
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


# ---------------------------------------------------------------------------------------------- mesh

class Geo:
    """Vertex/face accumulator with per-face material and per-vertex bone candidates."""

    def __init__(self):
        self.verts, self.faces, self.mats, self.cands = [], [], [], []

    def add(self, verts, faces, mat, bones):
        base = len(self.verts)
        self.verts += [Vector(v) for v in verts]
        self.faces += [tuple(base + i for i in f) for f in faces]
        self.mats += [mat] * len(faces)
        self.cands += [bones] * len(verts)


def frame(p0, p1):
    axis = (Vector(p1) - Vector(p0))
    n = axis.normalized()
    up = Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((0, -1, 0))
    u = n.cross(up).normalized()
    v = n.cross(u)
    return u, v


def tube(geo, p0, p1, r0, r1, mat, bones, n=8, caps=True, sx=1.0):
    """Cylinder from p0 to p1 with radii r0, r1; sx squashes it along the first frame axis."""
    u, v = frame(p0, p1)
    verts = []
    for p, r in ((p0, r0), (p1, r1)):
        for i in range(n):
            a = 2 * math.pi * i / n
            verts.append(Vector(p) + u * (r * sx * math.cos(a)) + v * (r * math.sin(a)))
    faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    if caps:
        faces.append(tuple(range(n - 1, -1, -1)))
        faces.append(tuple(range(n, 2 * n)))
    geo.add(verts, faces, mat, bones)


def box(geo, c, s, mat, bones, taper=1.0):
    cx, cy, cz = c
    hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
    t = taper
    verts = [
        (cx - hx * t, cy - hy * t, cz - hz), (cx + hx * t, cy - hy * t, cz - hz),
        (cx + hx * t, cy + hy * t, cz - hz), (cx - hx * t, cy + hy * t, cz - hz),
        (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz),
    ]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    geo.add(verts, faces, mat, bones)


def sphere(geo, c, r, mat, bones, rings=6, segs=10, keep=None, scale=(1, 1, 1)):
    """UV sphere; `keep(face_center)` can drop faces (open hood, visor cut-out)."""
    verts = []
    for i in range(rings + 1):
        phi = math.pi * i / rings
        for j in range(segs):
            th = 2 * math.pi * j / segs
            verts.append(Vector((
                c[0] + r * scale[0] * math.sin(phi) * math.cos(th),
                c[1] + r * scale[1] * math.sin(phi) * math.sin(th),
                c[2] + r * scale[2] * math.cos(phi))))
    faces = []
    for i in range(rings):
        for j in range(segs):
            a, b = i * segs + j, i * segs + (j + 1) % segs
            cc, d = (i + 1) * segs + (j + 1) % segs, (i + 1) * segs + j
            f = (a, b, cc, d) if 0 < i < rings - 1 else ((a, b, cc) if i == 0 else (a, cc, d))
            f = tuple(dict.fromkeys(f))
            if len(f) < 3:
                continue
            if keep and not keep(sum((verts[k] for k in f), Vector()) / len(f)):
                continue
            faces.append(f)
    geo.add(verts, faces, mat, bones)


def seg_dist(p, a, b):
    a, b = Vector(a), Vector(b)
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    return (a + ab * t - p).length


def weights_for(p, cands, blend=0.07):
    ds = sorted((seg_dist(p, *ALL_BONES[b][:2]), b) for b in cands)
    (d1, b1) = ds[0]
    out = {b1: 1.0}
    if len(ds) > 1 and ds[1][0] < d1 + blend:
        w = 1.0 - (ds[1][0] - d1) / blend
        out[ds[1][1]] = w * 0.5
    s = sum(out.values())
    return {k: v / s for k, v in out.items()}


MATERIALS = {
    "skin": (0.80, 0.60, 0.48),
    "primary": (0.17, 0.18, 0.20),
    "secondary": (0.29, 0.35, 0.28),
    "accent": (0.80, 0.45, 0.12),
    "metal": (0.35, 0.36, 0.38),
}


def material(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*MATERIALS[name], 1.0)
        bsdf.inputs["Roughness"].default_value = 0.85
        if name == "metal":
            bsdf.inputs["Metallic"].default_value = 0.8
            bsdf.inputs["Roughness"].default_value = 0.4
    return m


def make_object(name, geo, arm):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in geo.verts], [], geo.faces)
    mesh.update()
    mats = list(dict.fromkeys(geo.mats))
    for m in mats:
        mesh.materials.append(material(m))
    for poly, m in zip(mesh.polygons, geo.mats):
        poly.material_index = mats.index(m)
        poly.use_smooth = False
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    groups = {}
    for i, (v, cands) in enumerate(zip(geo.verts, geo.cands)):
        for bone, w in weights_for(v, cands).items():
            groups.setdefault(bone, obj.vertex_groups.new(name=bone)).add([i], w, "REPLACE")
    obj.parent = arm
    obj.modifiers.new("rig", "ARMATURE").object = arm
    return obj


# --------------------------------------------------------------------------------------------- parts

def LR(name):
    return [name + ".L", name + ".R"]


def body_head(geo):
    # Head and neck skin: its own part so the player's own head can go on the shadow-only layer.
    sphere(geo, (0, 0, 1.68), 0.11, "skin", ["head"], scale=(1, 1.1, 1.15))
    box(geo, (0, -0.07, 1.63), (0.06, 0.05, 0.05), "skin", ["head"])  # jaw/chin hint
    tube(geo, (0, 0, 1.42), (0, 0, 1.54), 0.045, 0.045, "skin", ["neck"])


def body(geo):
    # Hands, torso and limbs under the clothes, so bare styles still have a body.
    for s, x in (("L", 1), ("R", -1)):
        box(geo, (x * 0.27, -0.025, 0.80), (0.07, 0.045, 0.14), "skin", ["hand." + s])
    tube(geo, (0, 0, 0.95), (0, 0, 1.42), 0.14, 0.17, "primary", ["hips", "spine", "chest"], sx=0.7)
    for s, x in (("L", 1), ("R", -1)):
        tube(geo, (x * 0.17, 0, 1.40), (x * 0.22, 0, 1.12), 0.055, 0.045, "primary", ["upper_arm." + s])
        tube(geo, (x * 0.22, 0, 1.12), (x * 0.26, -0.02, 0.86), 0.045, 0.035, "primary", ["forearm." + s])
        tube(geo, (x * 0.10, 0, 0.95), (x * 0.11, 0, 0.52), 0.085, 0.06, "primary", ["upper_leg." + s])
        tube(geo, (x * 0.11, 0, 0.52), (x * 0.11, 0, 0.09), 0.06, 0.045, "primary", ["lower_leg." + s])
        box(geo, (x * 0.11, -0.05, 0.04), (0.09, 0.24, 0.07), "primary", ["foot." + s])


def head_hood(geo):
    def keep(c):
        return not (c.y < -0.03 and c.z > 1.58 and c.z < 1.76)
    sphere(geo, (0, 0.01, 1.67), 0.15, "primary", ["head"], rings=7, segs=12, keep=keep, scale=(1, 1.05, 1.1))
    # Hood draping down the back of the neck and over the shoulders.
    tube(geo, (0, 0.03, 1.55), (0, 0.06, 1.40), 0.13, 0.19, "primary", ["neck", "chest"], caps=False, sx=1.2)


def head_beanie(geo):
    sphere(geo, (0, 0, 1.70), 0.125, "secondary", ["head"], keep=lambda c: c.z > 1.66, scale=(1, 1.1, 1.1))
    tube(geo, (0, 0, 1.63), (0, 0, 1.68), 0.125, 0.13, "secondary", ["head"], caps=False, sx=1.1)


def head_cap(geo):
    sphere(geo, (0, 0, 1.70), 0.12, "secondary", ["head"], keep=lambda c: c.z > 1.68, scale=(1, 1.1, 1.0))
    box(geo, (0, -0.14, 1.69), (0.18, 0.12, 0.015), "secondary", ["head"])


def head_helmet(geo):
    sphere(geo, (0, 0, 1.69), 0.14, "secondary", ["head"], rings=6, segs=12, keep=lambda c: c.z > 1.62, scale=(1, 1.1, 1.0))
    box(geo, (0, -0.14, 1.66), (0.2, 0.08, 0.02), "metal", ["head"])


def face_mask(geo):
    sphere(geo, (0, -0.02, 1.63), 0.115, "accent", ["head"], keep=lambda c: c.y < -0.05 and c.z < 1.665, scale=(1, 1.1, 1.0))


def face_goggles(geo):
    box(geo, (0, -0.11, 1.70), (0.18, 0.04, 0.05), "metal", ["head"])
    tube(geo, (0, 0, 1.70), (0, 0.001, 1.70), 0.13, 0.13, "accent", ["head"], n=12, caps=False, sx=0.9)


def torso_jacket(geo):
    tube(geo, (0, 0, 0.93), (0, 0, 1.43), 0.17, 0.20, "primary", ["hips", "spine", "chest"], n=10, sx=0.7)
    box(geo, (0, 0.0, 1.0), (0.36, 0.26, 0.06), "primary", ["hips"])  # hem
    for s, x in (("L", 1), ("R", -1)):
        tube(geo, (x * 0.16, 0, 1.42), (x * 0.22, 0, 1.10), 0.075, 0.06, "primary", ["shoulder." + s, "upper_arm." + s])
        tube(geo, (x * 0.22, 0, 1.12), (x * 0.26, -0.02, 0.87), 0.06, 0.05, "primary", ["forearm." + s])
    # Zip line and collar.
    box(geo, (0, -0.145, 1.2), (0.02, 0.01, 0.42), "accent", ["spine", "chest"])
    tube(geo, (0, 0.01, 1.41), (0, 0.01, 1.47), 0.10, 0.11, "primary", ["chest", "neck"], caps=False, sx=1.1)


def torso_shirt(geo):
    tube(geo, (0, 0, 0.94), (0, 0, 1.43), 0.155, 0.18, "secondary", ["hips", "spine", "chest"], n=10, sx=0.7)
    for s, x in (("L", 1), ("R", -1)):
        tube(geo, (x * 0.16, 0, 1.42), (x * 0.20, 0, 1.26), 0.07, 0.06, "secondary", ["shoulder." + s, "upper_arm." + s])


def torso_carrier(geo):
    box(geo, (0, -0.13, 1.25), (0.26, 0.05, 0.30), "secondary", ["spine", "chest"])
    box(geo, (0, 0.14, 1.25), (0.26, 0.05, 0.30), "secondary", ["spine", "chest"])
    for s, x in (("L", 1), ("R", -1)):
        box(geo, (x * 0.12, 0, 1.40), (0.05, 0.30, 0.03), "accent", ["chest"])  # shoulder straps
        box(geo, (x * 0.07, -0.165, 1.18), (0.06, 0.03, 0.10), "accent", ["spine"])  # mag pouches
    box(geo, (0, 0, 1.08), (0.32, 0.30, 0.03), "accent", ["spine"])  # cummerbund


def hands_gloves(geo):
    for s, x in (("L", 1), ("R", -1)):
        box(geo, (x * 0.27, -0.025, 0.82), (0.08, 0.055, 0.10), "accent", ["hand." + s])
        box(geo, (x * 0.265, -0.02, 0.88), (0.075, 0.06, 0.04), "secondary", ["hand." + s, "forearm." + s])  # wrist tape


def hands_bare(geo):
    pass


def legs_cargo(geo):
    for s, x in (("L", 1), ("R", -1)):
        tube(geo, (x * 0.10, 0, 0.98), (x * 0.11, 0, 0.52), 0.11, 0.085, "secondary", ["hips", "upper_leg." + s])
        tube(geo, (x * 0.11, 0, 0.52), (x * 0.11, 0, 0.12), 0.085, 0.075, "secondary", ["lower_leg." + s])
        box(geo, (x * 0.20, 0.0, 0.70), (0.06, 0.14, 0.14), "secondary", ["upper_leg." + s])  # cargo pocket
    box(geo, (0, 0, 0.97), (0.32, 0.26, 0.04), "accent", ["hips"])  # belt


def legs_kneepads(geo):
    for s, x in (("L", 1), ("R", -1)):
        box(geo, (x * 0.11, -0.085, 0.47), (0.11, 0.04, 0.12), "primary", ["lower_leg." + s])


def feet_boots(geo):
    for s, x in (("L", 1), ("R", -1)):
        box(geo, (x * 0.11, -0.05, 0.05), (0.10, 0.26, 0.09), "primary", ["foot." + s])
        tube(geo, (x * 0.11, 0, 0.08), (x * 0.11, 0, 0.17), 0.07, 0.07, "primary", ["lower_leg." + s, "foot." + s])
        box(geo, (x * 0.11, -0.05, 0.012), (0.105, 0.265, 0.025), "accent", ["foot." + s])  # sole


def feet_sneakers(geo):
    for s, x in (("L", 1), ("R", -1)):
        box(geo, (x * 0.11, -0.05, 0.045), (0.095, 0.25, 0.07), "secondary", ["foot." + s])
        box(geo, (x * 0.11, -0.05, 0.012), (0.10, 0.255, 0.025), "primary", ["foot." + s])


def back_rope(geo):
    # Coiled rope slung from the left shoulder to the right hip.
    pts = [(0.13, -0.15, 1.40), (0.17, 0.0, 1.42), (0.08, 0.17, 1.22), (-0.10, 0.17, 1.02),
           (-0.17, 0.0, 0.98), (-0.08, -0.16, 1.14), (0.13, -0.15, 1.40)]
    for a, b in zip(pts, pts[1:]):
        tube(geo, a, b, 0.03, 0.03, "accent", ["chest", "spine", "hips"], n=6)


def back_pack(geo):
    box(geo, (0, 0.20, 1.22), (0.28, 0.14, 0.34), "secondary", ["chest", "spine", "prop_back"])
    box(geo, (0, 0.28, 1.12), (0.20, 0.04, 0.12), "accent", ["spine", "prop_back"])


def gear_launcher(geo):
    # Grapple launcher strapped to the left forearm, barrel forward over the back of the hand.
    box(geo, (0.26, -0.03, 0.98), (0.09, 0.08, 0.16), "metal", ["forearm.L"])
    tube(geo, (0.26, -0.05, 0.90), (0.26, -0.13, 0.86), 0.02, 0.025, "metal", ["forearm.L", "hand.L"], n=6)
    box(geo, (0.26, 0.0, 1.04), (0.10, 0.09, 0.02), "accent", ["forearm.L"])  # strap


def gear_chalkbag(geo):
    box(geo, (-0.12, 0.14, 0.90), (0.10, 0.09, 0.12), "accent", ["hips"], taper=0.8)
    tube(geo, (-0.12, 0.14, 0.96), (-0.12, 0.14, 0.99), 0.055, 0.045, "primary", ["hips"], caps=False)


PARTS = {
    "body": body, "body.head": body_head,
    "head.hood": head_hood, "head.beanie": head_beanie, "head.cap": head_cap, "head.helmet": head_helmet,
    "face.mask": face_mask, "face.goggles": face_goggles,
    "torso.jacket": torso_jacket, "torso.shirt": torso_shirt, "torso.carrier": torso_carrier,
    "hands.gloves": hands_gloves, "hands.bare": hands_bare,
    "legs.cargo": legs_cargo, "legs.kneepads": legs_kneepads,
    "feet.boots": feet_boots, "feet.sneakers": feet_sneakers,
    "back.rope": back_rope, "back.pack": back_pack,
    "gear.launcher": gear_launcher, "gear.chalkbag": gear_chalkbag,
}

OUTFITS = {
    "runner": ["body", "body.head", "head.hood", "face.mask", "torso.jacket", "torso.carrier", "hands.gloves",
               "legs.cargo", "legs.kneepads", "feet.boots", "back.rope", "gear.launcher", "gear.chalkbag"],
    "soldier": ["body", "body.head", "head.helmet", "torso.shirt", "torso.carrier", "legs.cargo", "feet.boots", "back.pack"],
}

# ---------------------------------------------------------------------------------------- animation

FPS = 24


def S(t, phase=0.0):
    return math.sin(2 * math.pi * t + phase)


def gait(t, leg, knee, arm, elbow, lean, bob):
    """A walk/run cycle. Legs swing about local X: negative is forward, knees bend positive."""
    p = {}
    for s, sign in (("L", 1), ("R", -1)):
        sw = S(t) * sign
        p["upper_leg." + s] = (-leg * sw, 0, 0)
        p["lower_leg." + s] = (knee * max(0.0, S(t, 1.1) * sign), 0, 0)
        p["foot." + s] = (-12 * max(0.0, S(t, 2.2) * sign) + 6, 0, 0)
        p["upper_arm." + s] = (arm * sw, 0, 0)
        p["forearm." + s] = (-elbow - 10 * max(0.0, sw), 0, 0)
    p["spine"] = (lean, 0, -4 * S(t))
    p["chest"] = (lean * 0.5, 0, 6 * S(t))
    p["head"] = (-lean * 0.8, 0, 0)
    p["hips"] = (0, -3 * S(t), 0)
    p["hips.loc"] = (0, -bob * abs(S(t)) + bob * 0.5, 0)
    return p


def clip_idle(t):
    b = S(t * 0.5)
    return {"chest": (2 * b, 0, 0), "head": (-1.5 * b, 0, 2 * S(t * 0.25)),
            "upper_arm.L": (0, 0, 2 * b), "upper_arm.R": (0, 0, -2 * b),
            "forearm.L": (-8, 0, 0), "forearm.R": (-8, 0, 0)}


def clip_walk(t):
    return gait(t, leg=24, knee=32, arm=18, elbow=15, lean=3, bob=0.02)


def clip_run(t):
    return gait(t, leg=42, knee=78, arm=34, elbow=70, lean=11, bob=0.04)


def clip_sprint(t):
    return gait(t, leg=54, knee=95, arm=44, elbow=85, lean=17, bob=0.05)


def clip_jump(t):
    k = min(1.0, t * 3)
    return {"upper_leg.L": (-35 * k, 0, 0), "upper_leg.R": (-20 * k, 0, 0),
            "lower_leg.L": (55 * k, 0, 0), "lower_leg.R": (40 * k, 0, 0),
            "upper_arm.L": (25, 0, -20), "upper_arm.R": (25, 0, 20),
            "forearm.L": (-30, 0, 0), "forearm.R": (-30, 0, 0), "spine": (6, 0, 0)}


def clip_fall(t):
    b = S(t)
    return {"upper_leg.L": (-10, 0, 0), "upper_leg.R": (10, 0, 0),
            "lower_leg.L": (25, 0, 0), "lower_leg.R": (30, 0, 0),
            "upper_arm.L": (-20 + 4 * b, 0, -45), "upper_arm.R": (-20 - 4 * b, 0, 45),
            "forearm.L": (-25, 0, 0), "forearm.R": (-25, 0, 0), "spine": (-5, 0, 0)}


def clip_crouch(t):
    b = S(t * 0.5)
    return {"hips.loc": (0, -0.34, 0), "upper_leg.L": (-72, 0, -6), "upper_leg.R": (-72, 0, 6),
            "lower_leg.L": (108, 0, 0), "lower_leg.R": (108, 0, 0), "foot.L": (-30, 0, 0), "foot.R": (-30, 0, 0),
            "spine": (24 + b, 0, 0), "chest": (6, 0, 0), "head": (-22, 0, 0),
            "upper_arm.L": (-25, 0, 0), "upper_arm.R": (-25, 0, 0), "forearm.L": (-45, 0, 0), "forearm.R": (-45, 0, 0)}


def clip_slide(t):
    b = S(t * 0.5)
    return {"hips.loc": (0, -0.50, 0), "hips": (-20, 0, 0),
            "upper_leg.L": (-70, 0, -8), "upper_leg.R": (-45, 0, 8), "lower_leg.L": (15, 0, 0), "lower_leg.R": (70, 0, 0),
            "foot.L": (-20, 0, 0), "foot.R": (-10, 0, 0), "spine": (12, 0, 0), "chest": (4, 0, 0), "head": (-18, 0, 0),
            "upper_arm.L": (-40 + 3 * b, 0, -25), "upper_arm.R": (20, 0, 30), "forearm.L": (-35, 0, 0), "forearm.R": (-60, 0, 0)}


def wallrun(t, side):
    # Running along a wall on `side` (+1 left, -1 right): body tilts away from it, inner arm reaches to it.
    p = gait(t, leg=38, knee=70, arm=20, elbow=60, lean=8, bob=0.02)
    inner = "L" if side > 0 else "R"
    outer = "R" if side > 0 else "L"
    p["hips"] = (0, 0, -14 * side)
    p["spine"] = (8, 0, -6 * side)
    p["head"] = (-6, 0, 10 * side)
    p["upper_arm." + inner] = (-30, 0, -80 * side)
    p["forearm." + inner] = (-20, 0, 0)
    p["upper_arm." + outer] = (-25, 0, 20 * side)
    p["forearm." + outer] = (-85, 0, 0)
    return p


def clip_wallrun_l(t):
    return wallrun(t, 1)


def clip_wallrun_r(t):
    return wallrun(t, -1)


def clip_mantle(t):
    # Hands on the ledge, pull up, then a knee comes over. Not looped; played at the mantle's speed.
    k = min(1.0, t * 2.0)
    step = max(0.0, (t - 0.5) * 2.0)
    return {"upper_arm.L": (-165 + 60 * k, 0, -15), "upper_arm.R": (-165 + 60 * k, 0, 15),
            "forearm.L": (-20 - 50 * k, 0, 0), "forearm.R": (-20 - 50 * k, 0, 0),
            "upper_leg.L": (-20 - 70 * step, 0, -5), "upper_leg.R": (-10 - 20 * k, 0, 5),
            "lower_leg.L": (30 + 60 * step, 0, 0), "lower_leg.R": (40, 0, 0),
            "spine": (25 - 10 * k, 0, 0), "chest": (10, 0, 0), "head": (-30 + 15 * k, 0, 0)}


def clip_grapple(t):
    # Left arm out along the rope, body stretched behind it, legs trailing.
    b = S(t * 0.5)
    return {"upper_arm.L": (-150, 0, -10), "forearm.L": (-10, 0, 0), "hand.L": (-20, 0, 0),
            "upper_arm.R": (-35 + 3 * b, 0, 35), "forearm.R": (-70, 0, 0),
            "upper_leg.L": (15, 0, -6), "upper_leg.R": (-5, 0, 6), "lower_leg.L": (35, 0, 0), "lower_leg.R": (55, 0, 0),
            "spine": (18, 0, 0), "chest": (8, 0, 0), "head": (-24, 0, 0)}


CLIPS = {
    "idle": (clip_idle, 96),
    "walk": (clip_walk, 24),
    "run": (clip_run, 20),
    "sprint": (clip_sprint, 18),
    "jump": (clip_jump, 24),
    "fall": (clip_fall, 48),
    "crouch": (clip_crouch, 96),
    "slide": (clip_slide, 48),
    "wallrun_l": (clip_wallrun_l, 20),
    "wallrun_r": (clip_wallrun_r, 20),
    "mantle": (clip_mantle, 24),
    "grapple": (clip_grapple, 48),
}


def bake_clips(arm):
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
            pose = fn(f / frames)
            for pb in arm.pose.bones:
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


# ----------------------------------------------------------------------------------------- preview

def render_preview(arm, parts, outfit, clip, frame, path, cam=(1.9, -2.9, 1.25)):
    scene = bpy.context.scene
    for name, obj in parts.items():
        obj.hide_render = name not in OUTFITS[outfit]
    for track in arm.animation_data.nla_tracks:
        track.mute = track.name != clip
    scene.frame_set(frame)
    scene.render.engine = "CYCLES"
    scene.view_settings.view_transform = "Standard"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = False
    scene.render.resolution_x, scene.render.resolution_y = 720, 960
    scene.render.filepath = path
    if "preview_cam" not in bpy.data.objects:
        cam_data = bpy.data.cameras.new("preview_cam")
        cam_data.lens = 55
        cam_obj = bpy.data.objects.new("preview_cam", cam_data)
        scene.collection.objects.link(cam_obj)
        scene.camera = cam_obj
        sun = bpy.data.lights.new("sun", "SUN")
        sun.energy = 4
        sun_obj = bpy.data.objects.new("sun", sun)
        sun_obj.rotation_euler = (math.radians(50), math.radians(10), math.radians(-30))
        scene.collection.objects.link(sun_obj)
        fill = bpy.data.lights.new("fill", "AREA")
        fill.energy = 300
        fill.size = 3
        fill_obj = bpy.data.objects.new("fill", fill)
        fill_obj.location = (-2.5, -2.0, 1.8)
        fill_obj.rotation_euler = (math.radians(70), 0, math.radians(-50))
        scene.collection.objects.link(fill_obj)
        floor = bpy.data.meshes.new("floor")
        floor.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
        floor_obj = bpy.data.objects.new("floor", floor)
        scene.collection.objects.link(floor_obj)
        fm = bpy.data.materials.new("floor")
        fm.use_nodes = True
        fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.45, 0.47, 0.42, 1)
        floor.materials.append(fm)
        scene.world = bpy.data.worlds.new("sky")
        scene.world.use_nodes = True
        scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.65, 0.8, 1)
        scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    cam_obj = bpy.data.objects["preview_cam"]
    cam_obj.location = cam
    direction = Vector((0, 0, 0.95)) - Vector(cam)
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.ops.render.render(write_still=True)
    for track in arm.animation_data.nla_tracks:
        track.mute = True
    for obj in parts.values():
        obj.hide_render = False


# ------------------------------------------------------------------------------------------- main

def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    arm = build_armature()
    parts = {}
    for name, fn in PARTS.items():
        geo = Geo()
        fn(geo)
        if not geo.verts:  # an empty style (bare hands) still needs a node to toggle
            geo.add([(0, 0, 0)] * 3, [(0, 1, 2)], "skin", ["hips"])
        parts[name] = make_object(name, geo, arm)
    bake_clips(arm)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    for obj in parts.values():
        obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=OUT, export_format="GLB", use_selection=True, export_apply=True,
        export_animations=True, export_animation_mode="NLA_TRACKS", export_skins=True,
        export_materials="EXPORT", export_image_format="NONE", export_yup=True,
    )
    print("wrote", OUT, os.path.getsize(OUT) // 1024, "KB")
    if "--no-render" not in sys.argv:
        os.makedirs(SHOTS, exist_ok=True)
        render_preview(arm, parts, "runner", "idle", 0, os.path.join(SHOTS, "character-runner.png"))
        render_preview(arm, parts, "runner", "run", 5, os.path.join(SHOTS, "character-runner-run.png"), cam=(2.4, -2.2, 1.1))
        render_preview(arm, parts, "soldier", "idle", 0, os.path.join(SHOTS, "character-soldier.png"))
        render_preview(arm, parts, "runner", "grapple", 0, os.path.join(SHOTS, "character-runner-grapple.png"), cam=(2.4, -2.2, 1.1))
        render_preview(arm, parts, "runner", "wallrun_l", 5, os.path.join(SHOTS, "character-runner-wallrun.png"), cam=(0.5, -3.2, 1.2))


def check():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=OUT)
    names = {o.name for o in bpy.data.objects}
    missing = [p for p in PARTS if p not in names]
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    bones = {b.name for b in arm.data.bones}
    missing += [b for b in ALL_BONES if b not in bones]
    clips = {a.name for a in bpy.data.actions}
    missing += [c for c in CLIPS if not any(a == c or a.startswith(c) for a in clips)]
    if missing:
        print("MISSING:", missing)
        sys.exit(1)
    print(f"ok: {len(bones)} bones, {len(PARTS)} parts, {len(CLIPS)} clips in {OUT}")


if __name__ == "__main__":
    check() if "--check" in sys.argv else build()
