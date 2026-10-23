"""Hand poses on every weapon, solved against the weapons' real meshes (rig contract v2, see
docs/superpowers/specs/2026-10-22-rig-rebuild-design.md). Run by `real.Char.finish` before the
carries are solved, and by `build.py --grips`.

A hold is a cylinder: the gun's pistol grip, handguard, pump or foregrip is fitted as an axis and a
radius from the weapon mesh around the point in assets/grips.toml. The palm frame (`prop_hand`,
origin on the palm's skin, Y wrist to knuckles, Z out of the palm) sits tangent to it with the
cylinder crossing the palm along the frame's X, on the side the hold approaches from. The fingers
wrap the cylinder in closed form (each joint turns until the next lands on it), then every joint is
nudged against the real mesh: opened until it clears the gun, closed until it touches, never more
than `REFINE` from the wrap. The right index lies on the trigger blade instead (`R_fire` pulls it
6 mm); the thumb crosses the far side of a grip or lies along the near side of a handguard.

Writes assets/models/character/<id>.grips.toml:

    [<weapon>.<pose>]            # pose: R, R_fire, L, L_vertical, L_angled
    at = [x, y, z]               # weapon glTF space: the palm frame's origin
    rot = [x, y, z, w]           # palm frame -> weapon space
    thumb = [[x, y, z, w], ...]  # each finger: three joints' rotations over the relaxed rest hand

The game sets each finger joint to its rest rotation times these (glTF node rotation = rest * pose,
as Blender's pose basis exports) and puts each prop_hand on its frame.

Right-hand poses are solved as the left hand on the mirrored weapon (the bodies are symmetric) and
mirrored back; the left hand is solved as is."""

import math
import os
import re
import tomllib
from collections import namedtuple

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

import kit
import real

FINGERS = kit.FINGERS
WEAPONS = os.path.join(kit.ROOT, "assets", "models", "weapons")
TABLE = os.path.join(kit.ROOT, "assets", "grips.toml")
# Parts the bare gun shows; every other att.* mesh is a gunsmith part that isn't fitted.
BARE = {"att.optic.irons", "att.muzzle.bare", "att.grip.standard", "att.stock.standard"}
TOUCH = 0.0015  # the palm and fingers stop this far off the gun's surface (the flesh presses in)
STEP = math.radians(0.5)
REFINE = math.radians(25)  # how far the real mesh may move a joint off the closed-form wrap
PRESS = 0.75  # a finger may sink into the gun by this much of its radius (the flesh flattens)
DEBUG = bool(os.environ.get("GRIPS_DEBUG"))

# A hold: the table point it closes on; the direction its cylinder runs (weapon space: -Z down the
# barrel, +Y up, +X right; a seed for the fit) and how far round it the fit looks; which way the palm
# faces (from the palm toward the axis); whether the frame's X (toward the thumb on the right hand,
# the little finger on the left) runs with (+1) or against (-1) that axis; how far the palm slides
# toward its knuckles (m); how the thumb lies ("wrap" round the far side, "along" the near side);
# the gunsmith part it needs.
Hold = namedtuple("Hold", "point axis reach palm x_sign shift thumb part")
HOLDS = {
    # The right hand round the pistol grip: the grip leans back, the palm faces the gun's left and a
    # little forward, the thumb at the top.
    "R": Hold("right", (0, 1, -0.4), 0.035, (-1, 0, -0.35), +1, 0.0, "wrap", None),
    # The support hand cups the handguard from its lower-left corner: the fingers cross under it, wrap
    # up the far side and lie over its top edge, the thumb runs forward along the near top edge.
    "cradle": Hold("cradle", (0, 0, -1), 0.05, (0.7, 1, 0), -1, -0.02, "along", None),
    # A vertical foregrip is held like a pistol grip with the left hand, thumb up.
    "vertical": Hold("vertical", (0, 1, 0), 0.035, (1, 0, -0.35), -1, 0.0, "wrap", "att.grip.vertical"),
    # An angled grip is a stop: the hand cradles the handguard just behind it.
    "angled": Hold("angled", (0, 0, -1), 0.05, (0.7, 1, 0), -1, -0.02, "along", "att.grip.angled"),
}
# A placed hold: the palm frame in (possibly mirrored) weapon space, its cylinder, and what it needs.
Frame = namedtuple("Frame", "at rot cen d r extra mirror thumb cap")
MIRROR = Matrix.Scale(-1, 3, (1, 0, 0))
SHOTS = os.path.join(kit.ROOT, "screenshots", "characters")


def solve(c, out_dir=kit.OUT):
    """Solve and write every weapon's poses for the character `c` (its rig at rest). Returns them."""
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
        w = _import(path)
        try:
            if DEBUG:
                print(wid)
            trig = _trigger_face(w)
            right = _hold(w, HOLDS["R"], Vector(spec["right"]), mirror=True)
            right = _place(c, w, right, trig)
            out[f"{wid}.R"] = _pose(c, w, right, trigger=(trig, 0.0))
            out[f"{wid}.R_fire"] = _pose(c, w, right, trigger=(trig, 0.006))
            support = "cradle" if "cradle" in spec else "vertical" if "vertical" in spec else None
            if support:
                out[f"{wid}.L"] = _pose(c, w, _hold(w, HOLDS[support], Vector(spec[support])))
            for name in ("vertical", "angled"):
                h = HOLDS[name]
                if h.part in w.parts and name in spec:
                    out[f"{wid}.L_{name}"] = _pose(c, w, _hold(w, h, Vector(spec[name])))
        finally:
            _remove(w)
    path = os.path.join(out_dir, f"{c.id}.grips.toml")
    with open(path, "w") as f:
        f.write(f"# Finger poses for {c.id}, solved by tools/character/grips.py. Do not edit.\n")
        for key, pose in out.items():
            f.write(f'\n["{key}"]\n')
            f.write(f"at = {_fmt(pose['at'])}\nrot = {_fmt(pose['rot'])}\n")
            for fg in FINGERS:
                f.write(f"{fg} = [{', '.join(_fmt(q) for q in pose[fg])}]\n")
    print(f"wrote {path}: {len(out)} poses")
    return out


def carry_frames(poses, weapon):
    """Where the left palm frame sits relative to the right one on `weapon` (a 4x4 in the right
    frame's coordinates) for the third-person carries, or None for a one-handed weapon."""
    r, l = poses.get(f"{weapon}.R"), poses.get(f"{weapon}.L")
    if r is None or l is None:
        return None

    def mat(p):
        x, y, z, w = p["rot"]
        return Matrix.Translation(Vector(p["at"])) @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
    return mat(r).inverted() @ mat(l)


def _fmt(v):
    return "[" + ", ".join(f"{x:.5f}" for x in v) + "]"


# ----------------------------------------------------------------------------------- the weapon

class Weapon:
    """One imported weapon glb: its meshes in glTF weapon space (-Z down the barrel, +Y up), by
    node name, and BVHs of the bare gun (plus one gunsmith part), mirrored across x for the right
    hand's solve."""

    def __init__(self, objects, parts):
        self.objects = objects
        self.parts = parts  # name -> (verts, polys) in weapon space
        self._trees = {}

    def _shown(self, extra):
        for name, (vs, ps) in self.parts.items():
            if name.startswith("att.") and name not in BARE and name != extra:
                continue
            yield vs, ps

    def verts(self, extra=None, mirror=False):
        return [MIRROR @ Vector(v) if mirror else Vector(v) for vs, _ in self._shown(extra) for v in vs]

    def tree(self, extra=None, mirror=False):
        key = (extra, mirror)
        if key not in self._trees:
            verts, polys = [], []
            for vs, ps in self._shown(extra):
                base = len(verts)
                verts += [(-v[0], v[1], v[2]) if mirror else v for v in vs]
                # A mirrored polygon keeps its outward normal by reversing its winding.
                polys += [[i + base for i in (p[::-1] if mirror else p)] for p in ps]
            self._trees[key] = BVHTree.FromPolygons(verts, polys)
        return self._trees[key]


def _rest_nodes(path):
    """Each node's own rest transform from the glb's JSON, by name: the importer leaves every
    animated node posed at frame 1 of the first clip (the draw), not at rest."""
    import json
    import struct
    with open(path, "rb") as f:
        head = f.read(12)
        length = struct.unpack_from("<I", f.read(8), 0)[0]
        doc = json.loads(f.read(length))
    assert head[:4] == b"glTF"
    rest = {}
    for n in doc.get("nodes", []):
        if "matrix" in n:
            M = Matrix([n["matrix"][i::4] for i in range(4)])
        else:
            q = n.get("rotation", (0, 0, 0, 1))
            M = Matrix.LocRotScale(Vector(n.get("translation", (0, 0, 0))),
                                   Quaternion((q[3], q[0], q[1], q[2])),
                                   Vector(n.get("scale", (1, 1, 1))))
        rest[n.get("name", "")] = M
    return rest


def _import(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    objects = [o for o in bpy.data.objects if o not in before]
    rest = _rest_nodes(path)
    for o in objects:
        if o.type == "ARMATURE":
            o.data.pose_position = "REST"
        o.animation_data_clear()
        name = re.sub(r"\.\d{3}$", "", o.name)
        if name in rest:  # Blender's Z-up local = C @ glTF local @ C^-1
            o.matrix_local = TO_GLTF.inverted() @ rest[name] @ TO_GLTF
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    parts = {}
    for o in objects:
        if o.type != "MESH":
            continue
        me = o.evaluated_get(dg).to_mesh()
        M = TO_GLTF @ o.matrix_world
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


# Blender's Z-up import of glTF's Y-up: weapon space (x, y, z) is Blender (x, -z, y).
TO_GLTF = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))


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


# ---------------------------------------------------------------------------------- the hold

def _cylinder(verts, seed, hint, half, reach):
    """Fit the cylinder of the part round `seed`: its axis (through the centroids of 1 cm stations
    along `hint`, within `half` of the seed and `reach` of the axis), the axis point nearest the
    seed, its mean radius and the verts it was fitted to."""
    a = Vector(hint).normalized()
    sel = []
    for v in verts:
        q = v - seed
        t = q.dot(a)
        if abs(t) < half and (q - a * t).length < reach:
            sel.append((t, v))
    bins = {}
    for t, v in sel:
        bins.setdefault(round(t / 0.01), []).append(v)
    cents = [sum(vs, Vector()) / len(vs) for _, vs in sorted(bins.items()) if len(vs) >= 3]
    d, mean = a, seed
    if len(cents) >= 2:
        import numpy as np
        mean = sum(cents, Vector()) / len(cents)
        P = np.array([[c.x - mean.x, c.y - mean.y, c.z - mean.z] for c in cents])
        _, _, vt = np.linalg.svd(P)
        d = Vector(vt[0]).normalized()
        if d.dot(a) < 0:
            d = -d
        if d.angle(a) > math.radians(25):
            d = a
    cen = mean + d * (seed - mean).dot(d)
    rs = sorted(((v - cen) - d * (v - cen).dot(d)).length for _, v in sel) or [0.015]
    return cen, d, rs[len(rs) // 2], [v for _, v in sel]


def _hold(w, hold, seed, mirror=False):
    """Place `hold` on the weapon: fit its cylinder and set the palm frame tangent to it. A right-hand
    hold (`mirror`) is placed on the mirrored weapon as a left hand."""
    hint, palm = Vector(hold.axis), Vector(hold.palm)
    x_sign = hold.x_sign
    if mirror:
        seed, hint, palm, x_sign = MIRROR @ seed, MIRROR @ hint, MIRROR @ palm, -hold.x_sign
    cen, d, r, sel = _cylinder(w.verts(hold.part, mirror), seed, hint, 0.03, hold.reach)
    X = d * x_sign
    Z = (palm - X * palm.dot(X)).normalized()
    Y = Z.cross(X)
    rot = Matrix((X, Y, Z)).transposed()  # columns X, Y, Z: frame -> weapon
    # The palm sits against the surface on its side: as far out as the part reaches toward it.
    strip = [v for v in sel if abs((v - cen).dot(X)) < 0.025 and abs((v - cen).dot(Y)) < 0.015]
    ext = max((-(v - cen).dot(Z) for v in strip), default=r)
    at = cen - Z * (ext + TOUCH) + Y * hold.shift
    # A cradled handguard lets the fingertips lie over its top edge but not rise above it, and lays
    # the thumb along the near side just under that edge, where the player sees it.
    cap = max(v.y for v in sel) + 0.012 if hold.thumb == "along" and not mirror else None
    if DEBUG:
        print(f"  hold {hold.point}: axis {tuple(round(x, 2) for x in d)} r {r * 1000:.1f} mm, palm {ext * 1000:.1f} mm from the axis"
              + (f", fingertips under {cap * 1000:.0f} mm" if cap else ""))
    # The fingers hug the real extent where it is deeper than the fitted cylinder (a boxy handguard),
    # then settle on the mesh from outside rather than press through it.
    return Frame(at, rot, cen, d, max(r, ext), hold.part, mirror, hold.thumb, cap)


def _moved(F, dt, roll):
    """`F` slid `dt` along its cylinder and turned `roll` radians round it."""
    R = Matrix.Rotation(roll, 3, F.d)
    at = F.cen + R @ (F.at - F.cen) + F.d * dt
    return F._replace(at=at, rot=R @ F.rot)


def _place(c, w, F, trig):
    """Slide the right hand along the grip and turn it round the grip (within 2 cm and 16 degrees)
    to where its index finger lies best on the trigger."""
    best = None
    for dt in (-0.02, -0.01, 0.0, 0.01, 0.02):
        for roll in (-16, -8, 0, 8, 16):
            F2 = _moved(F, dt, math.radians(roll))
            cost = _pose(c, w, F2, trigger=(trig, 0.0), probe=True) + 0.1 * abs(dt) + 0.0004 * abs(roll)
            if best is None or cost < best[0]:
                best = (cost, F2, dt, roll)
    if DEBUG:
        print(f"  placed right hand: slid {best[2] * 1000:.0f} mm, turned {best[3]} deg, reach {best[0] * 1000:.1f} mm")
    return best[1]


# ------------------------------------------------------------------------------------ the solve

def _pose(c, w, F, trigger=None, probe=False):
    """The left hand on the weapon at the placed hold `F`: the palm frame settled on the surface and
    every finger wrapped. Returns the frame and each finger's three joint rotations over the relaxed
    rest hand, mirrored back for a right-hand hold. With `probe`, only how far the index finger falls
    short of the trigger (m)."""
    b = c.b
    tree = w.tree(F.extra, F.mirror)
    G, fwd, up = (Vector(v) for v in b.grips["L"])
    X = fwd.cross(up)
    R = F.rot
    Rt = R.transposed()
    at = F.at.copy()

    def weapon_point(p):
        q = p - G
        return at + R @ Vector((q.dot(X), q.dot(fwd), q.dot(up)))

    def to_hand(wp):
        u = Rt @ (wp - at)
        return G + X * u.x + fwd * u.y + up * u.z

    def to_hand_dir(wv):
        u = Rt @ wv
        return X * u.x + fwd * u.y + up * u.z

    rest = b.rest
    L, T, Pn, palm, thick = real.hand_axes(rest, b.s)
    W = Vector(rest["hand.L"][0])

    def signed(p):
        """Distance from the gun's surface, negative inside it."""
        q = weapon_point(p)
        loc, nrm, _, dist = tree.find_nearest(q)
        if loc is None:
            return 1.0
        return -dist if (q - loc).dot(nrm) < 0 else dist

    # Palm on the gun: settle the frame along the palm normal until the palm just touches.
    palm_pts = [W + L * (k * palm) + Pn * thick for k in (0.45, 0.65, 0.85)]
    palm_pts += [Vector(rest[f"f_{f}.1.L"][0]) + Pn * thick * 0.8 for f in ("index", "middle", "ring", "pinky")]
    Zw = R @ Vector((0, 0, 1))
    moved = 0.0
    for _ in range(6):
        d = min(signed(p) for p in palm_pts)
        if abs(d - TOUCH) < 2e-4:
            break
        step = max(-0.01 - moved, min(0.01 - moved, d - TOUCH))
        at += Zw * step
        moved += step
    # The cylinder in hand space.
    c_h, d_h = to_hand(F.cen), to_hand_dir(F.d).normalized()

    def dist_axis(p):
        q = p - c_h
        return (q - d_h * q.dot(d_h)).length

    axis_c = L.cross(Pn).normalized()  # flexion: rotating about this brings a finger toward the palm
    out = {}
    for f in ("index",) if probe else FINGERS:
        names = [f"f_{f}.{i}.L" for i in (1, 2, 3)]
        js = [Vector(rest[names[0]][0])] + [Vector(rest[n][1]) for n in names]
        segs = [Matrix() for _ in names]
        rho = b.finger_r[f]
        hug = F.r + rho + 0.0025 * b.s

        def turn(j, Rm, js=js, segs=segs):
            M = _pivot(Rm, js[j])
            for q in range(j + 1, 4):
                js[q] = M @ js[q]
            for q in range(j, 3):
                segs[q] = M @ segs[q]

        def touching(j, js=js, rho=rho):
            """Whether phalanx j touches the gun."""
            return any(signed(js[j].lerp(js[j + 1], t)) <= rho + TOUCH for t in (0.5, 1.0))

        def through(j, js=js, rho=rho, first=1 if f == "thumb" else 0):
            """Whether the chain from joint j out is inside the gun anywhere (the thumb's first bone
            lies in the palm's heel, which presses into the grip)."""
            return any(signed(js[q].lerp(js[q + 1], t)) < rho * PRESS - TOUCH for q in range(max(j, first), 3) for t in (0.25, 0.5, 0.75, 1.0))

        def capped(q, js=js, rho=rho):
            """Whether joint q has reached the hold's height cap."""
            return F.cap is not None and weapon_point(js[q]).y > F.cap - rho

        def refine(j, ax, close=True):
            """Nudge joint j against the real mesh: open until the chain clears it, else close until
            this phalanx touches it, within REFINE of the wrap."""
            n = int(REFINE / STEP)
            if through(j):
                for _ in range(n):
                    turn(j, Matrix.Rotation(-STEP, 3, ax))
                    if not through(j):
                        break
            elif close and not touching(j) and not capped(j + 1):
                for _ in range(n):
                    turn(j, Matrix.Rotation(STEP, 3, ax))
                    if touching(j) or through(j) or capped(j + 1):
                        break
                if through(j):
                    turn(j, Matrix.Rotation(-STEP, 3, ax))

        def thumb_axis(j, js=js):
            return (js[j + 1] - js[j]).cross(Pn).normalized()


        if f == "thumb":
            d0 = js[3] - js[0]
            if F.thumb == "wrap":
                # Opposition: swing the thumb round the back of the grip toward its far side (the
                # fingers take the front), then flex each joint until it lands on the cylinder.
                tgt = (c_h - fwd * F.r + up * (F.r + rho)) - js[0]
                turn(0, _toward(d0, d0.lerp(tgt, 0.7)))
                # Round the cylinder the opposite way to the fingers: back to far side.
                for j, lim in enumerate((30, 55, 60)):
                    for _ in range(lim * 2):
                        if dist_axis(js[j + 1]) <= hug:
                            break
                        turn(j, Matrix.Rotation(STEP, 3, -axis_c))
                for j in range(3):
                    refine(j, -axis_c)
            else:
                # Along the near side, pointing the way the fingers' knuckle line runs (-X: forward
                # on a handguard), straight, its tip laid on the nearest skin of the gun; only backed
                # off the mesh.
                ahead = weapon_point(js[0] - X * d0.length)
                if F.cap is not None:  # on a handguard, up along its top edge
                    ahead.y = max(ahead.y, F.cap - 0.012 + rho)
                loc, nrm, _, _ = tree.find_nearest(ahead)
                tgt = (to_hand(loc + nrm * rho) if loc is not None else js[0] - X * d0.length) - js[0]
                turn(0, _toward(d0, tgt))
                for j in range(3):
                    refine(j, thumb_axis(j), close=False)
        else:
            # Close the spread: each finger parallel to the hand axis, side by side.
            d = js[3] - js[0]
            dp = (d - Pn * d.dot(Pn)).normalized()
            ang = math.atan2(dp.cross(L).dot(Pn), dp.dot(L))
            turn(0, Matrix.Rotation(ang * 0.85, 3, Pn))
            if f == "index" and trigger is not None:
                ok = _on_trigger(js, turn, signed, weapon_point, rho, axis_c, Pn, trigger, coarse=probe)
                if probe:
                    return ok
            else:
                for j, lim in enumerate((88, 105, 75)):
                    for _ in range(lim * 2):
                        if dist_axis(js[j + 1]) <= hug or capped(j + 1):
                            break
                        turn(j, Matrix.Rotation(STEP, 3, axis_c))
                for j in range(3):
                    refine(j, axis_c)
        if DEBUG:
            seg = [min(signed(js[q].lerp(js[q + 1], t)) for t in (0.25, 0.5, 0.75, 1.0)) for q in range(3)]
            unm = (lambda v: MIRROR @ v) if F.mirror else (lambda v: v)
            tip = tuple(round(x * 1000) for x in unm(weapon_point(js[3])))
            print(f"  {'R' if F.mirror else 'L'} {f}: rho {rho * 1000:.1f} gap {[round((x - rho) * 1000, 1) for x in seg]} mm, tip {tip} mm")
        out[f] = segs
    side = "R" if F.mirror else "L"
    if F.mirror:
        at = MIRROR @ at
        rot = Matrix((-(MIRROR @ R.col[0]), MIRROR @ R.col[1], MIRROR @ R.col[2])).transposed()
    else:
        rot = R
    q = rot.to_quaternion().normalized()
    return {"at": tuple(at), "rot": (q.x, q.y, q.z, q.w), **_deltas(c, side, out)}


def _on_trigger(js, turn, signed, weapon_point, rho, axis_c, spread, trigger, coarse=False):
    """Lay the index finger's last pad on the trigger's front face: a search over the finger's spread
    and its first two joints' flexion (the last follows at 0.6 of the second) that keeps the finger
    off the gun elsewhere. `trigger` is the blade's front face and how far it is pulled back (m)."""
    face, pull = trigger
    target = face + Vector((0.0, 0.0, pull - rho * 0.8))  # the finger's centre, its pad on the face
    start = [v.copy() for v in js]
    best = None
    k = 3 if coarse else 1
    for a0 in range(-24, 28, 4 * k):
        for a1 in range(0, 84, 4 * k):
            for a2 in range(0, 104, 4 * k):
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
                cost = (weapon_point(pad) - target).length
                for q in range(2):  # the last bone may rest on the trigger
                    for t in (0.3, 0.7, 1.0):
                        pen = rho - signed(p[q].lerp(p[q + 1], t))
                        if pen > 0:
                            cost += pen * 4.0
                if best is None or cost < best[0]:
                    best = (cost, a0, a1, a2)
    cost, a0, a1, a2 = best
    if coarse:
        return cost
    if DEBUG:
        print(f"  trigger: pad {cost * 1000:.1f} mm off at spread {a0}, flex {a1}/{a2}")
    turn(0, Matrix.Rotation(math.radians(a0), 3, spread))
    for j, deg in ((0, a1), (1, a2), (2, a2 * 0.6)):
        turn(j, Matrix.Rotation(math.radians(deg), 3, axis_c))
    return cost <= 0.02


def _deltas(c, side, segs):
    """Each finger joint's pose basis (rotation over its rest) for the solved chains."""
    b = c.b
    arm_bones = c.arm.data.bones
    hand = b.fit["hand." + side]
    out = {}
    for f in FINGERS:
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


def _mirror_matrix(M):
    X = Matrix.Scale(-1, 4, (1, 0, 0))
    return X @ M @ X


def _pivot(R, p):
    return Matrix.Translation(p) @ R.to_4x4() @ Matrix.Translation(-p)


def _toward(a, b):
    return a.normalized().rotation_difference(b.normalized()).to_matrix()


# ----------------------------------------------------------------------------------- the check

def render(cid, weapons=("rifle", "shotgun", "pistol", "dmr", "smg"), out_dir=SHOTS, res=384):
    """Render the built character's hands on each weapon, posed from its grips file, as the game
    poses them: <out_dir>/<cid>-hands-<weapon>.png, the right hand from the gun's left and front,
    the support hand from the right and below. Headless Workbench, seconds per weapon."""
    glb = os.path.join(kit.OUT, f"{cid}.glb")
    with open(os.path.join(kit.OUT, f"{cid}.grips.toml"), "rb") as f:
        poses = tomllib.load(f)
    os.makedirs(out_dir, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"  # headless: no GPU context for Workbench or Eevee
    scene.cycles.device = "CPU"
    scene.cycles.samples = 12
    scene.cycles.use_denoising = False
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x, scene.render.resolution_y = res, res
    scene.world = bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.55, 0.62, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.2
    for name, energy, rot in (("key", 3.0, (50, 10, -30)), ("fill", 1.5, (60, 0, 150))):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        lo = bpy.data.objects.new(name, ld)
        lo.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(lo)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 50
    cam.data.clip_start = 0.01
    scene.collection.objects.link(cam)
    scene.camera = cam
    bpy.ops.import_scene.gltf(filepath=glb)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    arm.animation_data_clear()
    arm.data.pose_position = "POSE"
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name not in kit.MESHES:
            o.hide_render = True
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    outs = []
    for wid in weapons:
        views = [("R", (-0.22, -0.06, -0.16)), ("R", (0.04, -0.12, -0.30))]
        if f"{wid}.L" in poses:
            views += [("L", (0.26, -0.14, -0.45)), ("L", (-0.1, -0.3, -0.55))]
        gun = _import(os.path.join(WEAPONS, f"{wid}.glb")).objects
        for o in gun:
            if o.type == "MESH":
                name = re.sub(r"\.\d{3}$", "", o.name)
                o.hide_render = name.startswith("att.") and name not in BARE
        base = {o: o.matrix_world.copy() for o in gun if o.parent is None}
        cols = []
        for i, (side, eye) in enumerate(views):
            pose = poses[f"{wid}.{side}"]
            for pb in arm.pose.bones:
                pb.rotation_quaternion = (1, 0, 0, 0)
            for fg in FINGERS:
                for j in range(3):
                    x, y, z, w = pose[fg][j]
                    arm.pose.bones[f"f_{fg}.{j + 1}.{side}"].rotation_quaternion = (w, x, y, z)
            bpy.context.view_layer.update()
            x, y, z, w = pose["rot"]
            frame = Matrix.Translation(Vector(pose["at"])) @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
            hand = arm.matrix_world @ arm.pose.bones[f"prop_hand.{side}"].matrix
            place = hand @ frame.inverted() @ TO_GLTF
            for o, m in base.items():
                o.matrix_world = place @ m
            bpy.context.view_layer.update()
            look = place @ TO_GLTF.inverted() @ Vector(pose["at"])
            cam.location = place @ TO_GLTF.inverted() @ (Vector(pose["at"]) + Vector(eye))
            cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
            path = os.path.join(out_dir, f"{cid}-hands-{wid}-{i}.png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True)
            cols.append(path)
        for o in gun:
            bpy.data.objects.remove(o, do_unlink=True)
        outs.append(_sheet(cols, os.path.join(out_dir, f"{cid}-hands-{wid}.png")))
    return outs


# Where the game rests the viewmodel's trigger in front of the eye (src/viewmodel.rs REST) and its
# vertical field of view, for the first-person check renders.
FP_REST = (0.14, -0.19, -0.33)
FP_FOV = 75.0


def render_fp(cid, weapons=("rifle",), out_dir=SHOTS, res=(960, 540)):
    """Render what the player sees of each hand on each weapon: the gun at the game's hip rest in
    front of the eye, each hand posed from the grips file (the arm is not solved here, only where the
    hand sits). Writes <out_dir>/<cid>-fp-<weapon>.png: the right hand's frame beside the left's."""
    glb = os.path.join(kit.OUT, f"{cid}.glb")
    with open(os.path.join(kit.OUT, f"{cid}.grips.toml"), "rb") as f:
        poses = tomllib.load(f)
    os.makedirs(out_dir, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 12
    scene.cycles.use_denoising = False
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.world = bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.55, 0.62, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.2
    for name, energy, rot in (("key", 3.0, (50, 10, -30)), ("fill", 1.5, (60, 0, 150))):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        lo = bpy.data.objects.new(name, ld)
        lo.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(lo)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.sensor_fit = "VERTICAL"
    cam.data.angle_y = math.radians(FP_FOV)
    cam.data.clip_start = 0.01
    scene.collection.objects.link(cam)
    scene.camera = cam
    bpy.ops.import_scene.gltf(filepath=glb)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    arm.animation_data_clear()
    arm.data.pose_position = "POSE"
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name != "mesh.arms":  # the eye sits inside the resting body
            o.hide_render = True
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    outs = []
    for wid in weapons:
        gun = _import(os.path.join(WEAPONS, f"{wid}.glb")).objects
        for o in gun:
            if o.type == "MESH":
                name = re.sub(r"\.\d{3}$", "", o.name)
                o.hide_render = name.startswith("att.") and name not in BARE
        base = {o: o.matrix_world.copy() for o in gun if o.parent is None}
        tiles = []
        for side in ("R", "L"):
            if f"{wid}.{side}" not in poses:
                continue
            pose = poses[f"{wid}.{side}"]
            for pb in arm.pose.bones:
                pb.rotation_quaternion = (1, 0, 0, 0)
            for fg in FINGERS:
                for j in range(3):
                    x, y, z, w = pose[fg][j]
                    arm.pose.bones[f"f_{fg}.{j + 1}.{side}"].rotation_quaternion = (w, x, y, z)
            bpy.context.view_layer.update()
            x, y, z, w = pose["rot"]
            frame = Matrix.Translation(Vector(pose["at"])) @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
            hand = arm.matrix_world @ arm.pose.bones[f"prop_hand.{side}"].matrix
            place = hand @ frame.inverted() @ TO_GLTF
            for o, m in base.items():
                o.matrix_world = place @ m
            cam.matrix_world = place @ TO_GLTF.inverted() @ Matrix.Translation(-Vector(FP_REST))
            bpy.context.view_layer.update()
            path = os.path.join(out_dir, f"{cid}-fp-{wid}-{side}.png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True)
            tiles.append(path)
        for o in gun:
            bpy.data.objects.remove(o, do_unlink=True)
        outs.append(_sheet(tiles, os.path.join(out_dir, f"{cid}-fp-{wid}.png")))
    return outs


def _sheet(paths, out):
    """Tile renders side by side into one image (and drop the tiles)."""
    imgs = [bpy.data.images.load(p) for p in paths]
    w, h = imgs[0].size
    sheet = bpy.data.images.new("sheet", w * len(imgs), h, alpha=False)
    px = [0.0] * (w * len(imgs) * h * 4)
    for k, im in enumerate(imgs):
        src = list(im.pixels)
        for row in range(h):
            a = (row * w * len(imgs) + k * w) * 4
            s = row * w * 4
            px[a:a + w * 4] = src[s:s + w * 4]
    sheet.pixels = px
    sheet.filepath_raw = out
    sheet.file_format = "PNG"
    sheet.save()
    for p in paths:
        os.remove(p)
    return out
