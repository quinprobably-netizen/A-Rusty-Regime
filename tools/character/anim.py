"""Every character's animation clips, without Blender: CMU mocap retargeted onto the character's own
rest skeleton for the gaits, idle, jump, deaths and seats, hand-keyed poses for the parkour moves,
and two upper-body overlays (reload, fire) the game layers on top.

Poses are dicts of bone -> XYZ euler degrees in the bone's own rest frame (Blender's pose basis,
which is also what a glTF node's rotation is relative to its rest), plus "hips.loc" in the hips'
frame. Matrices are in armature space: Z up, the character facing -Y, its left +X.

`glbanim.py` writes these into the character glbs. Clip order is the game's `Pose` order.
"""
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MOCAP = os.path.join(HERE, "mocap")
FPS = 24

# name: (frames, loops). The overlays come last: "reload" overrides the arms only, "fire" is added on
# top of whatever plays (its rotations are deltas, see `ADDITIVE`).
CLIPS = {
    "idle": (None, True), "walk": (None, True), "run": (None, True), "sprint": (None, True),
    "jump": (None, False), "fall": (None, False), "crouch": (96, True), "slide": (48, True),
    "wallrun_l": (None, True), "wallrun_r": (None, True), "mantle": (16, False), "grapple": (48, True),
    "crouch_walk": (28, True), "double_jump": (12, False), "death": (40, False), "death_back": (None, False),
    "drive": (72, True), "ride": (72, True), "reload": (48, False), "fire": (4, False),
}
CLIP_NAMES = list(CLIPS)
ADDITIVE = {"fire"}
# Bones the overlays drive (the game masks "reload" to these).
ARM_CHAIN = [b + s for s in ("L", "R") for b in ("upper_arm.", "forearm.", "hand.")]
TORSO = ["hips", "spine", "chest", "neck", "head"]


# ------------------------------------------------------------------------------------------ rotations

def rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def from_euler(e):
    """Blender XYZ euler (degrees) to a matrix: X is applied first."""
    x, y, z = (math.radians(v) for v in e)
    return rz(z) @ ry(y) @ rx(x)


def to_euler(m):
    y = math.asin(max(-1.0, min(1.0, -m[2, 0])))
    if abs(m[2, 0]) < 0.9999:
        x = math.atan2(m[2, 1], m[2, 2])
        z = math.atan2(m[1, 0], m[0, 0])
    else:  # gimbal lock: put it all on X
        x = math.atan2(-m[1, 2], m[1, 1])
        z = 0.0
    return (math.degrees(x), math.degrees(y), math.degrees(z))


def from_quat(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def to_quat(m):
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0:
        s = math.sqrt(t + 1) * 2
        q = (s / 4, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s)
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = ((m[2, 1] - m[1, 2]) / s, s / 4, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s)
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = ((m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, s / 4, (m[1, 2] + m[2, 1]) / s)
    else:
        s = math.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = ((m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, s / 4)
    q = np.array(q)
    return q / np.linalg.norm(q)


def slerp(a, b, t):
    """Between two rotation matrices."""
    qa, qb = to_quat(a), to_quat(b)
    if qa @ qb < 0:
        qb = -qb
    d = min(1.0, float(qa @ qb))
    ang = math.acos(d)
    if ang < 1e-6:
        return a
    q = (math.sin((1 - t) * ang) * qa + math.sin(t * ang) * qb) / math.sin(ang)
    return from_quat(q)


def mean_rot(ms):
    qs = [to_quat(m) for m in ms]
    acc = np.zeros(4)
    for q in qs:
        acc += q if q @ qs[0] >= 0 else -q
    return from_quat(acc / np.linalg.norm(acc))


def between(a, b):
    """The shortest rotation taking unit vector a to b."""
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(a @ b)
    if c < -0.9999:
        axis = np.cross(a, [1, 0, 0] if abs(a[0]) < 0.9 else [0, 1, 0])
        axis /= np.linalg.norm(axis)
        return 2 * np.outer(axis, axis) - np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def axis_angle(axis, deg):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    t = math.radians(deg)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * k + (1 - math.cos(t)) * k @ k


# ------------------------------------------------------------------------------------------- skeleton

class Rest:
    """The rest skeleton: per bone its parent, rest frame `F` (columns are the bone's axes; Y runs
    head to tail) and head position, in armature space."""

    def __init__(self, bones):
        self.bones = bones  # name: (parent, F, head, length)
        self.order = []
        todo = [n for n, b in bones.items() if b[0] is None]
        while todo:
            n = todo.pop(0)
            self.order.append(n)
            todo += [c for c, b in bones.items() if b[0] == n]
        self.cache = {}

    def F(self, b):
        return self.bones[b][1]

    def fk(self, pose):
        """World rotation and head of every bone in `pose`."""
        G, H = {}, {}
        for b in self.order:
            parent, F, head, _ = self.bones[b]
            P = pose_matrix(pose, b)
            if parent is None:
                G[b] = F @ P
                H[b] = head + F @ np.array(pose.get("hips.loc", (0, 0, 0)))
            else:
                pF, ph = self.F(parent), self.bones[parent][2]
                G[b] = G[parent] @ pF.T @ F @ P
                H[b] = H[parent] + G[parent] @ pF.T @ (head - ph)
        return G, H

    def local(self, b, G):
        """The pose basis that gives bone `b` the world rotation `G[b]` under its posed parent."""
        parent, F, _, _ = self.bones[b]
        if parent is None:
            return F.T @ G[b]
        return F.T @ self.F(parent) @ G[parent].T @ G[b]

    def tail(self, b, G, H):
        return H[b] + G[b] @ np.array([0, self.bones[b][3], 0])


def pose_matrix(pose, b):
    v = pose.get(b)
    if v is None:
        return np.eye(3)
    if isinstance(v, np.ndarray):
        return v
    return from_euler(v)


class Ctx:
    """One character: its rest skeleton, proportions, and how it holds its gun: `grips`, the
    character's solved palm frames on its carry weapon (the `<weapon>.R` / `.L` entries of its
    grips.toml, see `hold`), or, from older glbs, the baked two-hand carries (`carries_from`)."""

    def __init__(self, rest, carries=None, grips=None):
        self.rest = rest
        self.carries = carries or {}
        self.grips = grips
        self.hip_z = rest.bones["hips"][2][2]
        foot = rest.bones["foot.L"][2][2]
        self.leg = self.hip_z - foot  # hip joint to ankle
        self.k = self.hip_z / 0.95


# ---------------------------------------------------------------------------------------------- carries

CARRY_BASES = ("ready", "run", "sprint", "crouch", "slide")

# Where the held gun sits in each two-hand carry, in rest space (X left, -Y forward, Z up) turned
# with the chest: the trigger relative to the chest's head (metres at 1.80 m, scaled by `Ctx.k`),
# the barrel's direction, and the cant (degrees, + rolls the gun's top toward the support side).
# A compressed ready across the chest: the gun high in front of the chest rig (its pouches stand
# 25-30 cm out from the spine), the muzzle forward, down and well across to the left, so a rifle's
# stock (30 cm behind the trigger) sits in front of the right shoulder and the support hand stays
# within the arm's reach. The old carries aimed the palm instead of the gun, and with the solved
# diagonal grip the stock ended up inside the torso.
GUN_CARRIES = {
    "ready": ((-0.08, -0.31, -0.02), (0.55, -0.60, -0.58), 10),
    "run": ((-0.08, -0.30, 0.00), (0.52, -0.62, -0.59), 10),
    "sprint": ((-0.08, -0.29, 0.00), (0.50, -0.56, -0.66), 12),
    "crouch": ((-0.08, -0.31, -0.03), (0.55, -0.62, -0.56), 10),
    "slide": ((-0.08, -0.31, -0.02), (0.55, -0.60, -0.58), 10),
}
# Where the elbows go for each side's hold on the gun: the trigger elbow back and out so the stock
# passes in front of the upper arm, the support elbow out, forward and down so the forearm crosses
# in front of the chest rig rather than through it.
GUN_POLES = {"R": (-0.7, 0.5, -0.5), "L": (0.8, -0.6, -0.5)}


def gun_frame(ctx, pose, carry):
    """Where `carry` puts the gun in `pose`: (rotation whose columns are the gun's right, up and
    back, i.e. its glTF weapon axes; the trigger's position), armature space."""
    at, fwd, cant = GUN_CARRIES[carry]
    G, H = ctx.rest.fk(pose)
    turn = G["chest"] @ ctx.rest.F("chest").T  # the chest off its rest
    f = turn @ (np.asarray(fwd, float) / np.linalg.norm(fwd))
    up = turn @ np.array([0, 0, 1.0])
    up = up - f * (up @ f)
    up /= np.linalg.norm(up)
    up = axis_angle(f, -cant) @ up
    return np.column_stack([np.cross(f, up), up, -f]), H["chest"] + turn @ (np.asarray(at, float) * ctx.k)


def palm_on_gun(grip, R, T):
    """A solved palm frame (`at`, `rot` in weapon space, as grips.py writes and the game reads) on a
    gun at rotation `R`, trigger `T`: (position, rotation) of the palm frame in armature space."""
    x, y, z, w = grip["rot"]
    return T + R @ np.asarray(grip["at"], float), R @ from_quat((w, x, y, z))


def hold_gun(ctx, pose, carry):
    """Both arms on the gun where `carry` puts it, each palm where the character's solved grip sits
    on that gun. Arms the pose sets itself stay (a planted hand, a reach)."""
    R, T = gun_frame(ctx, pose, carry)
    for side in ("R", "L"):
        grip = ctx.grips.get(side)
        if grip is None or "upper_arm." + side in pose:
            continue
        at, rot = palm_on_gun(grip, R, T)
        reach(ctx, pose, side, at, rot, twist=0.5, pole=GUN_POLES[side])
    return pose


def carries_from(rest, poses):
    """Carries from posed bodies holding the gun ({carry: pose with its arms}): each arm's upper arm
    as a world rotation against the chest it was solved on, the forearm and hand as they bend."""
    out = {}
    for name, pose in poses.items():
        G, _ = rest.fk(pose)
        c = {"chest": G["chest"]}
        for s in ("L", "R"):
            c["upper_arm." + s] = G["upper_arm." + s]
            for b in ("forearm.", "hand."):
                c[b + s] = pose_matrix(pose, b + s)
        out[name] = c
    return out


def hold(ctx, poses, carry, steady=None):
    """Put the carry's arms into every pose of a clip (bones a pose sets itself stay). With the
    character's grips known, both arms are solved on the gun frame by frame (`hold_gun`), so the
    gun rides the chest exactly; a baked carry instead keeps its solved aim against the clip's
    average chest and rides the chest's sway around it."""
    if ctx.grips is not None:
        for p in poses:
            hold_gun(ctx, p, carry)
        return poses
    c = ctx.carries.get(carry)
    if c is None:
        return poses
    rest = ctx.rest
    chests = [rest.fk(p)[0]["chest"] for p in poses]
    mean = steady if steady is not None else mean_rot(chests)
    for p, chest in zip(poses, chests):
        G, _ = rest.fk(p)
        sway = chest @ mean.T
        free = "upper_arm.L" not in p
        for s in ("L", "R"):
            ua = "upper_arm." + s
            if ua in p:
                continue
            G[ua] = sway @ c[ua]
            p[ua] = rest.local(ua, G)
            for b in ("forearm.", "hand."):
                p.setdefault(b + s, c[b + s])
        if free:
            support(ctx, p)
    return poses


# ------------------------------------------------------------------------------------------------ mocap

_TABLES = {}


def table(name):
    if name not in _TABLES:
        with open(os.path.join(MOCAP, f"{name}.json")) as f:
            _TABLES[name] = json.load(f)
    return _TABLES[name]


def mocap(ctx, name, first=0, last=None, steady=0.0, arms=False, roll=0.0):
    """A take from `mocap/` on this skeleton: each bone gets the CMU bone's world rotation (its rest
    lined up with ours first), the hips the root's travel scaled to our legs. `steady` pulls the
    chest, neck and head toward their average (a gun carry keeps the torso quiet); `arms` keeps the
    mocap arms, else they are left for a carry. `roll` tips the whole body about the facing axis
    (degrees, + toward the character's right)."""
    t = table(name)
    rest = ctx.rest
    n = t["frames"]
    last = n if last is None else last
    scale = ctx.leg / t["leg"]
    K = {}
    for b, d in t["dirs"].items():
        ours = rest.F(b) @ np.array([0, 1.0, 0])
        K[b] = between(ours, np.array(d))
    tip = axis_angle((0, -1, 0), roll) if roll else np.eye(3)
    frames = []
    for i in range(first, last + 1):
        G = {}
        for b, qs in t["bones"].items():
            if not arms and b.split(".")[0] in ("shoulder", "upper_arm", "forearm", "hand"):
                continue
            G[b] = tip @ from_quat(qs[i]) @ K.get(b, np.eye(3)) @ rest.F(b)
        frames.append(G)
    if steady:
        for b in ("chest", "neck", "head"):
            m = mean_rot([g[b] for g in frames])
            for g in frames:
                g[b] = slerp(g[b], m, steady)
    poses = []
    root = np.array(t["root"])
    for j, G in enumerate(frames):
        i = first + j
        # Fill the bones the take leaves alone with their rest under the posed parent, then read
        # every bone's pose basis off the world rotations.
        full = {}
        for b in rest.order:
            parent = rest.bones[b][0]
            if b in G:
                full[b] = G[b]
            else:
                full[b] = full[parent] @ rest.F(parent).T @ rest.F(b) if parent else rest.F(b)
        p = {b: rest.local(b, full) for b in G}
        # The root: CMU's hip height over its legs, onto ours; travel scaled likewise.
        r = root[i] * scale
        lift = (root[i][2] - t["leg_rest"]) * scale
        world = np.array([r[0], r[1], lift])
        p["hips.loc"] = tuple(rest.F("hips").T @ world)
        poses.append(p)
    return poses


def loop_fix(poses):
    """Make a cycle seamless: spread the last frame's mismatch with the first over the whole clip."""
    n = len(poses) - 1
    out = []
    for i, p in enumerate(poses):
        q = dict(p)
        w = i / n
        for b, v in p.items():
            if b == "hips.loc":
                d = np.array(poses[0][b]) - np.array(poses[-1][b])
                q[b] = tuple(np.array(v) + d * w)
                continue
            first, lastm = pose_matrix(poses[0], b), pose_matrix(poses[-1], b)
            err = lastm.T @ first  # local correction at the end
            q[b] = pose_matrix(p, b) @ slerp(np.eye(3), err, w)
        out.append(q)
    return out


# --------------------------------------------------------------------------------------- hand keying

def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def keyed(t, keys):
    """Ease between key poses [(time, pose), ...] (euler entries and "hips.loc")."""
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t <= t1 or (t1, b) == keys[-1]:
            w = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
            out = {}
            for k in set(a) | set(b):
                va, vb = np.array(a.get(k, (0, 0, 0)), float), np.array(b.get(k, (0, 0, 0)), float)
                out[k] = tuple(va + (vb - va) * w)
            return out
    return dict(keys[-1][1])


def S(t, phase=0.0):
    return math.sin(2 * math.pi * t + phase)


def drop(ctx, metres):
    """hips.loc for lowering the hips by `metres` (scaled to this build)."""
    return (0, -metres * ctx.k, 0)


def crouch_pose(ctx, t):
    s = S(t * 0.5)
    return {"hips.loc": drop(ctx, 0.34), "upper_leg.L": (-72, 0, -6), "upper_leg.R": (-72, 0, 6),
            "lower_leg.L": (108, 0, 0), "lower_leg.R": (108, 0, 0), "foot.L": (-30, 0, 0), "foot.R": (-30, 0, 0),
            "spine": (24 + s, 0, 0), "chest": (6 + 0.8 * s, 0, 0), "head": (-12, 0, 2 * S(t * 0.25))}


def crouch_walk_pose(ctx, t):
    """A low, heel-to-toe stalk: thighs swing short and stay high, the hips barely bob."""
    p = crouch_pose(ctx, 0)
    for s, sign in (("L", 1), ("R", -1)):
        sw = S(t) * sign
        lift = max(0.0, S(t, 1.3) * sign)
        p["upper_leg." + s] = (-62 - 22 * sw - 10 * lift, 0, -6 * sign)
        p["lower_leg." + s] = (96 + 6 * sw + 26 * lift, 0, 0)
        p["foot." + s] = (-24 + 14 * sw, 0, 0)
    p["hips"] = (0, -4 * S(t), 2 * S(t))
    p["hips.loc"] = (0, -0.33 * ctx.k + 0.015 * ctx.k * abs(S(t)), 0)
    p["spine"] = (26, 0, -3 * S(t))
    p["chest"] = (6, 0, 4 * S(t))
    return p


def slide_pose(ctx, t):
    """Titanfall knee slide: leaning back, the lead leg out straight, the other folded under with the
    knee out to the side; a little chatter from the ground."""
    j = 0.6 * S(t * 7) + 0.4 * S(t * 11, 1.0)
    return {"hips.loc": drop(ctx, 0.56), "hips": (-26 + j, 0, -4),
            "upper_leg.L": (-60, 0, -4), "lower_leg.L": (10, 0, 0), "foot.L": (-30, 0, 0),
            "upper_leg.R": (-50, 0, 40), "lower_leg.R": (140, 0, 0), "foot.R": (20, 0, 0),
            "spine": (16 - j * 0.5, 0, 4), "chest": (8, 0, 2), "neck": (4, 0, 0), "head": (-14, 0, -4)}


def mantle_pose(ctx, t):
    """Hand on the ledge, haul up, knee over, stand: the left hand plants, the right keeps the gun."""
    reach = {"upper_leg.L": (-10, 0, -4), "upper_leg.R": (6, 0, 4), "lower_leg.L": (30, 0, 0), "lower_leg.R": (40, 0, 0),
             "spine": (10, 0, 0), "chest": (6, 0, 0), "head": (-16, 0, 0),
             "upper_arm.L": (-150, 0, -12), "forearm.L": (-30, 0, 0), "hand.L": (40, 0, 0)}
    haul = {"hips.loc": (0, 0.05 * ctx.k, 0), "upper_leg.L": (-60, 0, -6), "upper_leg.R": (-15, 0, 6),
            "lower_leg.L": (95, 0, 0), "lower_leg.R": (70, 0, 0), "spine": (30, 0, 0), "chest": (14, 0, 0), "head": (-26, 0, 0),
            "upper_arm.L": (-95, 0, -18), "forearm.L": (-95, 0, 0), "hand.L": (60, 0, 0)}
    knee = {"hips.loc": (0, 0.04 * ctx.k, 0), "upper_leg.L": (-105, 0, -8), "upper_leg.R": (-20, 0, 6),
            "lower_leg.L": (125, 0, 0), "lower_leg.R": (55, 0, 0), "foot.L": (-20, 0, 0), "spine": (34, 0, 0), "chest": (10, 0, 0),
            "head": (-26, 0, 0), "upper_arm.L": (-20, 0, -14), "forearm.L": (-30, 0, 0), "hand.L": (70, 0, 0)}
    stand = {"hips.loc": drop(ctx, 0.08), "upper_leg.L": (-35, 0, -4), "upper_leg.R": (-25, 0, 4),
             "lower_leg.L": (50, 0, 0), "lower_leg.R": (45, 0, 0), "spine": (14, 0, 0), "chest": (4, 0, 0), "head": (-10, 0, 0)}
    return keyed(t, [(0.0, reach), (0.35, haul), (0.7, knee), (1.0, stand)])


def grapple_pose(ctx, t):
    """Reeling in on the rope: left arm thrown out toward the hook, the body swinging under it, legs
    trailing and pedalling a little."""
    s, c = S(t), S(t, 1.6)
    return {"hips": (6 * s, 0, 4 * c), "upper_leg.L": (14 + 10 * s, 0, -8), "upper_leg.R": (-12 - 10 * s, 0, 8),
            "lower_leg.L": (50 + 10 * c, 0, 0), "lower_leg.R": (70 - 10 * c, 0, 0), "foot.L": (25, 0, 0), "foot.R": (15, 0, 0),
            "spine": (10 - 3 * s, 0, -10), "chest": (6, 0, -12), "head": (-10, 0, 14),
            "upper_arm.L": (-150 + 4 * s, 0, -24), "forearm.L": (-8, 0, 0), "hand.L": (-25, 0, 0)}


def double_jump_pose(ctx, t):
    """The pilot's second jump: knees snap up to the chest, then kick down and back."""
    start = {"upper_leg.L": (-30, 0, 0), "upper_leg.R": (-15, 0, 0), "lower_leg.L": (50, 0, 0), "lower_leg.R": (40, 0, 0), "spine": (6, 0, 0)}
    tuck = {"hips.loc": (0, 0.06 * ctx.k, 0), "upper_leg.L": (-105, 0, -6), "upper_leg.R": (-95, 0, 6),
            "lower_leg.L": (125, 0, 0), "lower_leg.R": (120, 0, 0), "foot.L": (-20, 0, 0), "foot.R": (-20, 0, 0),
            "spine": (22, 0, 0), "chest": (8, 0, 0), "head": (-22, 0, 0)}
    kick = {"upper_leg.L": (-25, 0, -4), "upper_leg.R": (15, 0, 4), "lower_leg.L": (35, 0, 0), "lower_leg.R": (55, 0, 0),
            "foot.L": (20, 0, 0), "foot.R": (30, 0, 0), "spine": (2, 0, 0), "head": (-6, 0, 0)}
    return keyed(t, [(0.0, start), (0.35, tuck), (0.8, kick), (1.0, kick)])


def death_pose(ctx, t):
    """Shot from the front: the knees go, the body folds over them and pitches onto its face. The
    gun stays up for the first hit, then the arms go limp."""
    if "death_arms" not in ctx.rest.cache:
        p = hold(ctx, [idle_base(ctx)], "ready")[0]
        ctx.rest.cache["death_arms"] = {b: to_euler(pose_matrix(p, b)) for b in ARM_CHAIN}
    held = ctx.rest.cache["death_arms"]
    limp = {"upper_arm.L": (-25, 0, -8), "upper_arm.R": (-35, 0, 8), "forearm.L": (-30, 0, 0), "forearm.R": (-45, 0, 0)}
    hit = {"spine": (-8, 0, 4), "chest": (-6, 0, 6), "head": (-14, 0, 0), **held}
    buckle = {"upper_leg.L": (-45, 0, -4), "upper_leg.R": (-30, 0, 6), "lower_leg.L": (85, 0, 0), "lower_leg.R": (70, 0, 0),
              "foot.L": (-20, 0, 0), "spine": (22, 0, -6), "chest": (12, 0, -4), "neck": (10, 0, 0), "head": (22, 0, 8), **limp}
    knees = {"hips": (12, 0, 4), "upper_leg.L": (-18, 0, -4), "upper_leg.R": (-12, 0, 6), "lower_leg.L": (118, 0, 0), "lower_leg.R": (112, 0, 0),
             "foot.L": (30, 0, 0), "foot.R": (30, 0, 0), "spine": (30, 0, -8), "chest": (16, 0, -4), "neck": (12, 0, 0), "head": (28, 0, 10), **limp}
    pitch = {"hips": (55, 0, 6), "upper_leg.L": (-10, 0, -4), "upper_leg.R": (-6, 0, 6), "lower_leg.L": (60, 0, 0), "lower_leg.R": (50, 0, 0),
             "foot.L": (30, 0, 0), "foot.R": (30, 0, 0), "spine": (20, 0, -6), "chest": (10, 0, 0), "neck": (6, 0, 0), "head": (-10, 0, 20),
             "upper_arm.L": (-60, 0, -25), "upper_arm.R": (-70, 0, 25), "forearm.L": (-50, 0, 0), "forearm.R": (-60, 0, 0)}
    prone = {"hips": (88, 0, 8), "upper_leg.L": (4, 0, -8), "upper_leg.R": (0, 0, 10), "lower_leg.L": (14, 0, 0), "lower_leg.R": (30, 0, 0),
             "foot.L": (40, 0, 0), "foot.R": (35, 0, 0), "spine": (2, 0, -4), "chest": (2, 0, 0), "neck": (-10, 0, 0), "head": (-30, 0, 60),
             "upper_arm.L": (-20, 0, -40), "upper_arm.R": (-150, 0, 30), "forearm.L": (-30, 0, 0), "forearm.R": (-20, 0, 0)}
    return keyed(t, [(0.0, {"spine": (3, 0, 0), **held}), (0.1, hit), (0.35, buckle), (0.55, knees), (0.78, pitch), (0.92, prone), (1.0, prone)])


def drive_pose(ctx, t):
    """Sitting in a car seat: thighs level, shins down to the pedals, leaning back, hands on the wheel
    (solved in `seated`)."""
    s = S(t)
    return {"hips.loc": drop(ctx, 0.47), "hips": (-12, 0, 0),
            "upper_leg.L": (-80, 0, -8), "upper_leg.R": (-80, 0, 8), "lower_leg.L": (70, 0, 0), "lower_leg.R": (65, 0, 0),
            "foot.L": (-10, 0, 0), "foot.R": (-15, 0, 0), "spine": (6, 0, 0), "chest": (2 + 0.6 * s, 0, 0),
            "neck": (4, 0, 0), "head": (-2, 0, 3 * S(t * 0.5))}


def ride_pose(ctx, t):
    """Astride a dirt bike: knees gripping the tank, feet on the pegs, forward over the bars."""
    s = S(t)
    return {"hips.loc": drop(ctx, 0.2), "hips": (8, 0, 0),
            "upper_leg.L": (-68, 0, -16), "upper_leg.R": (-68, 0, 16), "lower_leg.L": (100, 0, 0), "lower_leg.R": (100, 0, 0),
            "foot.L": (-20, 0, 0), "foot.R": (-20, 0, 0), "spine": (22, 0, 0), "chest": (10 + 0.6 * s, 0, 0),
            "neck": (-6, 0, 0), "head": (-18, 0, 0)}


# ------------------------------------------------------------------------------------------------- IK

def palm_frame(fingers, palm_out):
    """A palm frame's rotation: +Y along the fingers, +Z out of the palm."""
    y = np.asarray(fingers, float)
    y = y / np.linalg.norm(y)
    z = np.asarray(palm_out, float)
    z = z - y * (z @ y)
    z /= np.linalg.norm(z)
    return np.column_stack([np.cross(y, z), y, z])


def reach(ctx, pose, side, palm_at, palm_rot, twist=0.0, pole=None):
    """Bend one arm (two-bone IK, the elbow toward `pole`: by default out and down) so its palm frame
    (`prop_hand.<side>`) lands at `palm_at` turned to `palm_rot`, as far as the arm reaches. `twist`
    is the share of the wrist's twist about the forearm's axis the forearm takes, so the wrist
    doesn't pinch. `pole` is in armature space, as given."""
    rest = ctx.rest
    ua, fa, hd, pr = "upper_arm." + side, "forearm." + side, "hand." + side, "prop_hand." + side
    for b in (ua, fa, hd):
        pose.pop(b, None)
    G, H = rest.fk(pose)
    sh = H[ua]
    l1 = np.linalg.norm(rest.bones[fa][2] - rest.bones[ua][2])
    l2 = np.linalg.norm(rest.bones[hd][2] - rest.bones[fa][2])
    # The hand's world rotation that turns the palm frame to palm_rot, and the wrist that puts it there.
    hand_G = palm_rot @ (rest.F(hd).T @ rest.F(pr)).T
    wrist = np.asarray(palm_at, float) - hand_G @ (rest.F(hd).T @ (rest.bones[pr][2] - rest.bones[hd][2]))
    d = wrist - sh
    dist = max(1e-4, min(np.linalg.norm(d), (l1 + l2) * 0.999))
    dn = d / np.linalg.norm(d)
    sign = 1 if side == "L" else -1
    pole = np.array(pole if pole is not None else (0.7 * sign, 0.3, -1.0), float)
    pole = pole - dn * (pole @ dn)
    pole /= np.linalg.norm(pole)
    a = math.acos(max(-1.0, min(1.0, (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist))))
    elbow = sh + l1 * (math.cos(a) * dn + math.sin(a) * pole)
    w = sh + dn * dist

    def aim(b, frm, to):
        parent = rest.bones[b][0]
        Gb = G[parent] @ rest.F(parent).T @ rest.F(b)  # rest under the posed parent
        y = Gb @ np.array([0, 1.0, 0])
        return between(y, to - frm) @ Gb

    G[ua] = aim(ua, sh, elbow)
    pose[ua] = rest.local(ua, G)
    G[fa] = aim(fa, elbow, w)
    if twist:
        # The hand's turn about its own Y against its rest under the forearm; part of it goes into
        # the forearm as pronation.
        q = to_quat(rest.F(hd).T @ rest.F(fa) @ G[fa].T @ hand_G)
        G[fa] = G[fa] @ ry(2 * math.atan2(q[2], q[0]) * twist)
    pose[fa] = rest.local(fa, G)
    G[hd] = hand_G
    pose[hd] = rest.local(hd, G)
    return pose


def right_palm(ctx, pose):
    """Where the right palm frame (the gun) is in a pose: (position, rotation). Its +Y runs down the
    barrel, +X up out of the back of the hand, +Z to the gun's left."""
    G, H = ctx.rest.fk(pose)
    return H["prop_hand.R"], G["prop_hand.R"]


# The support palm against the right one on a rifle-sized gun, in the right palm frame (from the
# characters whose carries came out clean: 23 cm up the handguard, cupping it from the left).
SUPPORT_AT = np.array([0.047, 0.229, 0.11])
SUPPORT_ROT = from_euler((-124.6, 43.8, -105.3))


def support(ctx, pose):
    """Put the left palm on the handguard of whatever the right hand holds: where the character's
    solved support grip sits against its trigger grip, or the rifle-sized default."""
    at, rot = right_palm(ctx, pose)
    if ctx.grips and "L" in ctx.grips:
        # The gun from the right palm, then the left palm on that gun.
        x, y, z, w = ctx.grips["R"]["rot"]
        R = rot @ from_quat((w, x, y, z)).T
        l_at, l_rot = palm_on_gun(ctx.grips["L"], R, at - R @ np.asarray(ctx.grips["R"]["at"], float))
        return reach(ctx, pose, "L", l_at, l_rot, twist=0.5)
    return reach(ctx, pose, "L", at + rot @ SUPPORT_AT, rot @ SUPPORT_ROT)


def seated(ctx, p, half, ahead, height):
    """Hands on a wheel or bars `half` either side of a point `ahead`/`height` from the hips."""
    _, H = ctx.rest.fk(p)
    c = H["hips"] + np.array([0, -ahead, height])
    for s, sign in (("L", 1), ("R", -1)):
        rot = palm_frame((-sign * 0.25, -0.75, 0.6), (sign * 0.3, 0.2, -1.0))
        reach(ctx, p, s, c + np.array([sign * half, 0, 0]), rot)
    return p


# --------------------------------------------------------------------------------------------- reload

def reload_poses(ctx, frames):
    """Generic magazine change over the 'ready' carry: the gun cants, the support hand drops to the
    magwell, strips the mag, fetches one from the chest rig, seats it, slaps it home and returns."""
    rest = ctx.rest
    base = hold(ctx, [idle_base(ctx)], "ready")[0]
    _, H = rest.fk(base)
    cant = 24
    poses = []
    for f in range(frames + 1):
        t = f / frames
        p = dict(base)
        # The gun cants toward the support hand while it works.
        k = ease(t / 0.12) * (1 - ease((t - 0.85) / 0.15))
        p["forearm.R"] = pose_matrix(base, "forearm.R") @ from_euler((0, -cant * k, 0))
        at, rot = right_palm(ctx, p)
        fwd, up = rot[:, 1], rot[:, 0]
        hold_at = at + rot @ SUPPORT_AT
        magwell = at + fwd * 0.1 - up * 0.13
        keys = [(0.0, hold_at), (0.12, magwell), (0.25, magwell - up * 0.2), (0.45, H["chest"] + np.array([0.13, -0.19, -0.02])),
                (0.62, magwell - up * 0.06), (0.72, magwell), (0.8, magwell - up * 0.07), (0.92, hold_at), (1.0, hold_at)]
        for (t0, a), (t1, b) in zip(keys, keys[1:]):
            if t <= t1:
                break
        w = ease((t - t0) / (t1 - t0))
        # Palm up under the gun while it handles the mag, back to the grip at the ends.
        turn = ease(t / 0.1) * (1 - ease((t - 0.84) / 0.08))
        grip_rot = rot @ SUPPORT_ROT
        under = palm_frame(fwd * 0.6 - rot[:, 2] * 0.4, up)
        reach(ctx, p, "L", a + (b - a) * w, slerp(grip_rot, under, turn))
        poses.append({b: p[b] for b in ARM_CHAIN})
    return poses


# ---------------------------------------------------------------------------------------------- clips

def idle_base(ctx):
    """The calm standing pose the 'ready' carry was solved on (the old idle's first frame)."""
    return {"spine": (3, 0, 0)}


def pose_seq(ctx, fn, frames):
    return [fn(ctx, f / frames) for f in range(frames + 1)]


def ground(ctx, poses, height=0.06, parts=("lower_leg", "foot")):
    """Raise or drop each pose's hips so its lowest point (of the `parts` bones) sits `height`
    above the floor."""
    rest = ctx.rest
    for p in poses:
        G, H = rest.fk(p)
        low = min(min(H[b][2], rest.tail(b, G, H)[2]) for b in rest.order if b.split(".")[0] in parts)
        loc = np.array(p.get("hips.loc", (0, 0, 0)), float)
        p["hips.loc"] = tuple(loc + rest.F("hips").T @ np.array([0, 0, height - low]))
    return poses


def build(ctx):
    """Every clip as a list of poses (frame 0..n), keyed by clip name."""
    out = {}
    out["idle"] = hold(ctx, loop_fix(mocap(ctx, "idle", steady=0.4)), "ready")
    out["walk"] = hold(ctx, loop_fix(mocap(ctx, "walk", steady=0.6)), "ready")
    out["run"] = hold(ctx, loop_fix(mocap(ctx, "run", steady=0.6)), "run")
    out["sprint"] = hold(ctx, loop_fix(mocap(ctx, "sprint", steady=0.5)), "sprint")
    out["jump"] = hold(ctx, mocap(ctx, "jump", steady=0.5), "run")
    out["fall"] = hold(ctx, mocap(ctx, "fall", steady=0.5), "ready")
    out["crouch"] = hold(ctx, pose_seq(ctx, crouch_pose, CLIPS["crouch"][0]), "crouch")
    out["slide"] = hold(ctx, ground(ctx, pose_seq(ctx, slide_pose, CLIPS["slide"][0])), "slide")
    for name, side in (("wallrun_l", 1), ("wallrun_r", -1)):
        # Feet on the wall: the body tips away from it, the head comes back toward level.
        poses = loop_fix(mocap(ctx, "run", steady=0.6, roll=24 * side))
        for p in poses:
            p["head"] = from_euler((0, -14 * side, 0)) @ pose_matrix(p, "head")
        out[name] = hold(ctx, poses, "run")
    out["mantle"] = hold(ctx, pose_seq(ctx, mantle_pose, CLIPS["mantle"][0]), "run")
    out["grapple"] = hold(ctx, pose_seq(ctx, grapple_pose, CLIPS["grapple"][0]), "run")
    out["crouch_walk"] = hold(ctx, pose_seq(ctx, crouch_walk_pose, CLIPS["crouch_walk"][0]), "crouch")
    out["double_jump"] = hold(ctx, pose_seq(ctx, double_jump_pose, CLIPS["double_jump"][0]), "run")
    out["death"] = ground(ctx, pose_seq(ctx, death_pose, CLIPS["death"][0]), height=0.1, parts=("lower_leg", "foot", "hips", "spine", "chest", "neck", "head", "upper_leg"))
    out["death_back"] = mocap(ctx, "death_back", arms=True)
    out["drive"] = [seated(ctx, p, 0.19, 0.42, 0.42) for p in pose_seq(ctx, drive_pose, CLIPS["drive"][0])]
    out["ride"] = [seated(ctx, p, 0.3, 0.52, 0.5) for p in pose_seq(ctx, ride_pose, CLIPS["ride"][0])]
    out["reload"] = reload_poses(ctx, CLIPS["reload"][0])
    out["fire"] = fire_deltas(CLIPS["fire"][0])
    return out


def fire_deltas(frames):
    """Recoil, added on top of any pose: the chest and shoulders kick back, the head rides it."""
    out = []
    for f in range(frames + 1):
        k = (1 - f / frames) ** 2 if f else 0.6
        out.append({"spine": (-1.5 * k, 0, 0), "chest": (-3.5 * k, 0, 1.0 * k), "neck": (2 * k, 0, 0), "head": (2 * k, 0, 0)})
    return out
