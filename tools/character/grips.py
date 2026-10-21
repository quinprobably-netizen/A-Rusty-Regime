"""Finger poses for every weapon, solved against the weapons' real meshes. Run by `Char.finish` after
the character glb is written: each weapon glb (assets/models/weapons) is placed in each hand the way
the game holds it (assets/grips.toml), and every finger curls joint by joint until it meets the gun.
The right index finger is laid on the trigger instead (and pulled 6 mm back for `R_fire`); the left
hand also takes the vertical and angled foregrips. Writes assets/models/character/<id>.grips.toml:

    [<weapon>.<pose>]            # pose: R, R_fire, L, L_vertical, L_angled
    at = [x, y, z]               # weapon glTF space: where the grip frame sits (palm on the gun)
    rot = [x, y, z, w]           # grip frame -> weapon space
    thumb = [[x, y, z, w], ...]  # each finger: three joints' rotations on top of the rest fist

The game sets each finger joint to its rest rotation times these (glTF node rotation = rest * pose,
as Blender's pose basis exports)."""

import math
import os
import re
import tomllib

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

import kit

FINGERS = kit.FINGERS
WEAPONS = os.path.join(kit.ROOT, "assets", "models", "weapons")
TABLE = os.path.join(kit.ROOT, "assets", "grips.toml")
# Parts the bare gun shows; every other att.* mesh is a gunsmith part that isn't fitted.
BARE = {"att.optic.irons", "att.muzzle.bare", "att.grip.standard", "att.stock.standard"}
# Grip frame -> weapon space (frame +Y down the barrel, +Z up): the game's grip_rotation inverse.
DEFAULT_ROT = Quaternion((1, 0, 0), math.radians(-90))
# A vertical foregrip is held like a pistol grip: thumb up (frame +Y), the hand pointing down the
# barrel (frame +X), the palm facing the gun's right (frame +Z). The angled grip tips that hand 40
# degrees forward and down, the heel of the palm on its sloped back.
VERTICAL_ROT = Matrix(((0, 0, 1), (0, 1, 0), (-1, 0, 0))).to_quaternion()
ANGLED_ROT = Quaternion((1, 0, 0), math.radians(-40)) @ VERTICAL_ROT
TOUCH = 0.0015  # the palm and fingers stop this far off the gun's surface (the flesh presses in)
STEP = math.radians(0.5)
DEBUG = bool(os.environ.get("GRIPS_DEBUG"))


def solve(c, out_dir=kit.OUT):
    """Solve and write every weapon's poses for the built character `c` (its rig at rest)."""
    with open(TABLE, "rb") as f:
        table = tomllib.load(f)
    out = {}
    for wid, spec in table.items():
        if wid == "fist":
            continue
        path = os.path.join(WEAPONS, f"{wid}.glb")
        if not os.path.exists(path):
            print(f"grips: no {path}, skipped")
            continue
        meshes = _import(path)
        try:
            if DEBUG:
                print(wid)
            trig = _trigger_face(meshes)
            right = _place(c, meshes, Vector(spec["right"]), trig)
            out[f"{wid}.R"] = _pose(c, meshes, "R", right, DEFAULT_ROT, trigger=(trig, 0.0))
            out[f"{wid}.R_fire"] = _pose(c, meshes, "R", right, DEFAULT_ROT, trigger=(trig, 0.006))
            if "left" in spec:
                out[f"{wid}.L"] = _pose(c, meshes, "L", Vector(spec["left"]), DEFAULT_ROT)
                for part, rot in (("vertical", VERTICAL_ROT), ("angled", ANGLED_ROT)):
                    at = _part_centre(meshes, f"att.grip.{part}")
                    if at is not None:
                        out[f"{wid}.L_{part}"] = _pose(c, meshes, "L", at, rot, extra=f"att.grip.{part}")
        finally:
            _remove(meshes)
    path = os.path.join(out_dir, f"{c.id}.grips.toml")
    with open(path, "w") as f:
        f.write(f"# Finger poses for {c.id}, solved by tools/character/grips.py. Do not edit.\n")
        for key, pose in out.items():
            f.write(f'\n["{key}"]\n')
            f.write(f"at = {_fmt(pose['at'])}\nrot = {_fmt(pose['rot'])}\n")
            for fg in FINGERS:
                f.write(f"{fg} = [{', '.join(_fmt(q) for q in pose[fg])}]\n")
    print(f"wrote {path}: {len(out)} poses")
    return path


def _fmt(v):
    return "[" + ", ".join(f"{x:.5f}" for x in v) + "]"


# ----------------------------------------------------------------------------------- the weapon

class Weapon:
    """One imported weapon glb: its meshes in glTF weapon space (-Z down the barrel, +Y up), by
    node name."""

    def __init__(self, objects, parts):
        self.objects = objects
        self.parts = parts  # name -> (verts, polys) in weapon space
        self._trees = {}

    def tree(self, extra=None):
        """A BVH of the bare gun, plus the gunsmith part `extra`."""
        if extra not in self._trees:
            verts, polys = [], []
            for name, (vs, ps) in self.parts.items():
                if name.startswith("att.") and name not in BARE and name != extra:
                    continue
                base = len(verts)
                verts += vs
                polys += [[i + base for i in p] for p in ps]
            self._trees[extra] = BVHTree.FromPolygons(verts, polys)
        return self._trees[extra]


def _import(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    objects = [o for o in bpy.data.objects if o not in before]
    for o in objects:
        if o.type == "ARMATURE":
            o.data.pose_position = "REST"
            o.animation_data_clear()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    # Blender's Z-up import of glTF's Y-up: weapon space (x, y, z) is Blender (x, -z, y).
    to_gltf = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))
    parts = {}
    for o in objects:
        if o.type != "MESH":
            continue
        me = o.evaluated_get(dg).to_mesh()
        M = to_gltf @ o.matrix_world
        name = re.sub(r"\.\d{3}$", "", o.name)
        vs = [tuple(M @ v.co) for v in me.vertices]
        ps = [list(p.vertices) for p in me.polygons]
        if name in parts:  # several primitives of one node
            base = len(parts[name][0])
            parts[name][0].extend(vs)
            parts[name][1].extend([[i + base for i in p] for p in ps])
        else:
            parts[name] = (vs, ps)
        o.evaluated_get(dg).to_mesh_clear()
    return Weapon(objects, parts)


def _remove(w):
    for o in w.objects:
        bpy.data.objects.remove(o, do_unlink=True)


def _trigger_face(w):
    """The middle of the trigger blade's front face (`mesh.trigger`), in weapon space."""
    if "mesh.trigger" not in w.parts:
        return Vector((0.0, -0.01, -0.006))
    vs = w.parts["mesh.trigger"][0]
    lo = Vector([min(v[i] for v in vs) for i in range(3)])
    hi = Vector([max(v[i] for v in vs) for i in range(3)])
    return Vector(((lo.x + hi.x) / 2, hi.y - (hi.y - lo.y) * 0.5, lo.z))


def _part_centre(w, name):
    """Where the left hand holds a foregrip: its body's centre (the clamp at the top left out)."""
    if name not in w.parts:
        return None
    vs = w.parts[name][0]
    lo = Vector([min(v[i] for v in vs) for i in range(3)])
    hi = Vector([max(v[i] for v in vs) for i in range(3)])
    c = (lo + hi) / 2
    c.y = lo.y + (hi.y - lo.y) * 0.45
    return c


# ------------------------------------------------------------------------------------ the solve

def _pose(c, w, side, at, rot, trigger=None, extra=None, probe=False):
    """One hand on the weapon: the grip frame at weapon point `at` turned by `rot`; returns the
    palm-corrected `at`, `rot` and each finger's three joint rotations over the rest fist. With
    `probe`, only how far the index finger falls short of the trigger (m)."""
    b = c.b
    tree = w.tree(extra)
    # Solved on the left hand (the bodies are symmetric); a right-hand pose sees the gun mirrored.
    G, fwd, up = (Vector(v) for v in b.grips[side])
    if side == "R":
        G, fwd, up = _mirror(G), _mirror(fwd), _mirror(up)
        X = -fwd.cross(up)  # the mirror of the right frame's X = fwd x up
    else:
        X = fwd.cross(up)
    R = rot.to_matrix()

    def weapon_point(p, shift):
        q = p + shift - G
        return at + R @ Vector((q.dot(X), q.dot(fwd), q.dot(up)))

    rest = b.rest
    W = Vector(rest["hand.L"][0])
    mid = Vector(rest["hand.L"][1])
    L = (mid - W).normalized()
    T = Vector(rest["f_index.1.L"][0]) - Vector(rest["f_pinky.1.L"][0])
    T = (T - L * T.dot(L)).normalized()
    Pn = L.cross(T).normalized()
    if Pn.x > 0:
        Pn = -Pn
    palm = (mid - W).length
    thick = 0.0125 * b.s

    def signed(p, shift):
        """Distance from the gun's surface, negative inside it."""
        q = weapon_point(p, shift)
        loc, nrm, _, d = tree.find_nearest(q)
        if loc is None:
            return 1.0
        return -d if (q - loc).dot(nrm) < 0 else d

    # Palm on the gun: slide the gun along the palm normal until the palm just touches it.
    palm_pts = [W + L * (k * palm) + Pn * thick for k in (0.35, 0.6, 0.85)]
    palm_pts += [Vector(rest[f"f_{f}.1.L"][0]) + Pn * thick * 0.8 for f in ("index", "middle", "ring", "pinky")]
    shift = Vector()
    for _ in range(6):
        d = min(signed(p, shift) for p in palm_pts)
        if abs(d - TOUCH) < 2e-4:
            break
        shift += Pn * (d - TOUCH)
    shift.length = min(shift.length, 0.03)

    axis_c = L.cross(Pn).normalized()
    out = {}
    for f in ("index",) if probe else FINGERS:
        names = [f"f_{f}.{i}.L" for i in (1, 2, 3)]
        js = [Vector(rest[names[0]][0])] + [Vector(rest[n][1]) for n in names]
        segs = [Matrix() for _ in names]
        rho = b.finger_r[f]

        def turn(j, Rm, js=js, segs=segs):
            M = _pivot(Rm, js[j])
            for q in range(j + 1, 4):
                js[q] = M @ js[q]
            for q in range(j, 3):
                segs[q] = M @ segs[q]

        def near(j, js=js, rho=rho):
            """Whether the chain from joint j out touches the gun."""
            return any(signed(js[q].lerp(js[q + 1], t), shift) <= rho + TOUCH for q in range(j, 3) for t in (0.5, 1.0))

        def through(js=js, rho=rho, first=1 if f == "thumb" else 0):
            """Whether the finger ends up inside the gun anywhere (the thumb's first bone lies in the
            palm's heel, which presses into the grip)."""
            return any(signed(js[q].lerp(js[q + 1], t), shift) < rho * 0.4 - TOUCH for q in range(first, 3) for t in (0.25, 0.5, 0.75, 1.0))

        if f == "thumb":
            # Opposition: swing the thumb across toward the grip, a degree at a time, until it meets
            # the gun.
            d0 = js[3] - js[0]
            tgt = (G - shift + T * 0.012 * b.s) - js[0]
            swing = d0.rotation_difference(d0.lerp(tgt, 0.55))
            ax, total = swing.axis, swing.angle
            for _ in range(int(math.degrees(total))):
                turn(0, Matrix.Rotation(math.radians(1.0), 3, ax))
                if near(0):
                    turn(0, Matrix.Rotation(math.radians(-1.0), 3, ax))
                    break
            lims = (30, 55, 60)
        else:
            d = js[3] - js[0]
            dp = (d - Pn * d.dot(Pn)).normalized()
            ang = math.atan2(dp.cross(L).dot(Pn), dp.dot(L))
            turn(0, Matrix.Rotation(ang * 0.85, 3, Pn))
            lims = (88, 105, 75)
        if f == "index" and trigger is not None:
            ok = _on_trigger(js, turn, signed, shift, weapon_point, rho, axis_c, Pn, trigger, coarse=probe)
            if probe:
                return ok
        else:
            for j in range(3):
                ax = axis_c if f != "thumb" else (js[j + 1] - js[j]).cross(Pn).normalized()
                n = int(lims[j] / math.degrees(STEP))
                if near(j):
                    # Already on (or in) the gun: open the joint until the finger just clears it.
                    for _ in range(n):
                        turn(j, Matrix.Rotation(-STEP, 3, ax))
                        if not near(j):
                            break
                else:
                    for _ in range(n):
                        if near(j):
                            break
                        turn(j, Matrix.Rotation(STEP, 3, ax))
            ok = not through()
        if DEBUG:
            seg = [min(signed(js[q].lerp(js[q + 1], t), shift) for t in (0.25, 0.5, 0.75, 1.0)) for q in range(3)]
            print(f"  {side} {f}: {'ok' if ok else 'rest'} rho {rho * 1000:.1f} segs {[round(x * 1000, 1) for x in seg]}")
        # A finger the gun's shape defeats keeps the rest fist: never worse than before.
        out[f] = segs if ok else None
    return {"at": weapon_point(G, shift), "rot": (rot.x, rot.y, rot.z, rot.w), **_deltas(c, side, out)}


def _place(c, w, right, trig):
    """Slide the right hand up, down, forward or back along the grip (within 3 cm of the shared grip
    point) to where its index finger lies best on the trigger."""
    best = None
    for dy in range(-30, 33, 3):
        for dz in range(-21, 24, 3):
            at = right + Vector((0.0, dy / 1000, dz / 1000))
            cost = _pose(c, w, "R", at, DEFAULT_ROT, trigger=(trig, 0.0), probe=True) + 0.1 * (dy * dy + dz * dz) ** 0.5 / 1000
            if best is None or cost < best[0]:
                best = (cost, at)
    if DEBUG:
        print(f"  placed right hand {tuple(round(x, 3) for x in best[1])}, reach {best[0] * 1000:.1f} mm")
    return best[1]


def _on_trigger(js, turn, signed, shift, weapon_point, rho, axis_c, spread, trigger, coarse=False):
    """Lay the index finger's last pad on the trigger's front face: a search over the finger's spread
    and its first two joints' flexion (the last follows at 0.6 of the second) that keeps the finger
    off the gun elsewhere. `trigger` is the blade's front face and how far it is pulled back (m)."""
    face, pull = trigger
    target = face + Vector((0.0, 0.0, pull - rho * 0.8))  # the finger's centre, its pad on the face
    start = [v.copy() for v in js]
    best, best_d = None, 1.0
    k = 3 if coarse else 1
    for a0, a1, a2 in ((a0, a1, a2) for a0 in range(-24, 28, 4 * k) for a1 in range(0, 84, 4 * k) for a2 in range(0, 104, 4 * k)):
        p = [v.copy() for v in start]

        def flex(j, deg, axis=axis_c, p=p):
            M = _pivot(Matrix.Rotation(math.radians(deg), 3, axis), p[j])
            for q in range(j + 1, 4):
                p[q] = M @ p[q]
        flex(0, a0, spread)
        flex(0, a1)
        flex(1, a2)
        flex(2, a2 * 0.6)
        pad = p[2].lerp(p[3], 0.65)
        cost = (weapon_point(pad, shift) - target).length
        for q in range(2):  # the last bone may rest on the trigger
            for t in (0.3, 0.7, 1.0):
                pen = rho - signed(p[q].lerp(p[q + 1], t), shift)
                if pen > 0:
                    cost += pen * 4.0
        if best is None or cost < best[0]:
            best = (cost, a0, a1, a2)
        best_d = min(best_d, (weapon_point(pad, shift) - target).length)
    cost, a0, a1, a2 = best
    if coarse:
        return cost
    if DEBUG:
        wp = lambda v: tuple(round(x, 3) for x in weapon_point(v, shift))  # noqa: E731
        print(f"  index mcp {wp(start[0])} tip {wp(start[3])} closest pad {best_d * 1000:.1f} mm")
        print(f"  trigger cost {cost * 1000:.1f} mm at {a1},{a2}, target {tuple(round(x, 3) for x in target)}")
    if cost > 0.02:
        return False
    turn(0, Matrix.Rotation(math.radians(a0), 3, spread))
    for j, deg in ((0, a1), (1, a2), (2, a2 * 0.6)):
        turn(j, Matrix.Rotation(math.radians(deg), 3, axis_c))
    return True


def _deltas(c, side, segs):
    """Each finger joint's pose basis (rotation over its rest) for the solved chains."""
    b = c.b
    arm_bones = c.arm.data.bones
    hand = b.fit["hand." + side]
    out = {}
    for f in FINGERS:
        if segs[f] is None:
            out[f] = [(0.0, 0.0, 0.0, 1.0)] * 3
            continue
        posed = {}
        qs = []
        for i in (1, 2, 3):
            n = f"f_{f}.{i}.{side}"
            S = segs[f][i - 1] if side == "L" else _mirror_matrix(segs[f][i - 1])
            rest = arm_bones[n].matrix_local
            P = S @ hand @ b.fit[n].inverted() @ rest
            if i == 1:
                basis = rest.inverted() @ P
            else:
                pn = f"f_{f}.{i - 1}.{side}"
                basis = (posed[pn] @ arm_bones[pn].matrix_local.inverted() @ rest).inverted() @ P
            posed[n] = P
            q = basis.to_quaternion().normalized()
            qs.append((q.x, q.y, q.z, q.w))
        out[f] = qs
    return out


def _mirror(p):
    return Vector((-p[0], p[1], p[2]))


def _mirror_matrix(M):
    X = Matrix.Scale(-1, 4, (1, 0, 0))
    return X @ M @ X


def _pivot(R, p):
    return Matrix.Translation(p) @ R.to_4x4() @ Matrix.Translation(-p)


def _toward(a, b):
    return a.normalized().rotation_difference(b.normalized()).to_matrix()
