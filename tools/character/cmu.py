"""CMU motion capture (mocap.cs.cmu.edu) to the compact tables in `mocap/`.

Run once with network: `python3 cmu.py` downloads the ASF/AMC trials it needs into vendor/cmu
(gitignored), cuts each take to the frames a clip uses, resamples it to 24 fps and writes
`mocap/<clip>.json`: per frame, the root position and every mapped bone's world rotation relative
to the CMU rest pose. `anim.py` retargets those onto each character's own rest skeleton at build
time, so a build never needs the network.

Frames are in the rig's armature space (Blender, Z up, the character facing -Y, its left +X),
lengths in metres. Licence: CMU's data may ship in commercially sold products but may not be
resold on its own (http://mocap.cs.cmu.edu/faqs.php); see CREDITS.md.
"""
import json
import math
import os
import sys
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, "vendor", "cmu")
OUT = os.path.join(HERE, "mocap")
URL = "http://mocap.cs.cmu.edu/subjects/{s}/{f}"
SRC_FPS = 120
FPS = 24
INCH = 0.0254 / 0.45  # ASF "length 0.45": lengths are inches / 0.45

# Our bone: the CMU bone whose world rotation drives it.
BONES = {
    "hips": "root", "spine": "lowerback", "chest": "thorax", "neck": "lowerneck", "head": "head",
    "shoulder.L": "lclavicle", "upper_arm.L": "lhumerus", "forearm.L": "lradius", "hand.L": "lhand",
    "shoulder.R": "rclavicle", "upper_arm.R": "rhumerus", "forearm.R": "rradius", "hand.R": "rhand",
    "upper_leg.L": "lfemur", "lower_leg.L": "ltibia", "foot.L": "lfoot",
    "upper_leg.R": "rfemur", "lower_leg.R": "rtibia", "foot.R": "rfoot",
}

# clip: (trial, first frame, last frame at 120 fps or None for automatic, kind). Kinds: "loop" finds
# one whole gait cycle from `first` on and makes it seamless and in place; "once" keeps the range
# as is, the root's travel included (minus the start).
TAKES = {
    "idle": ("77_02", 200, 680, "loop"),
    "walk": ("08_01", 60, None, "loop"),
    "run": ("16_35", 30, None, "loop"),
    "sprint": ("09_01", 20, None, "loop"),
    "jump": ("16_05", 128, 162, "once"),
    "fall": ("16_05", 162, 192, "once"),
    "death": ("90_16", 280, 560, "once"),
    "death_back": ("90_18", 40, 220, "once"),
}


# ------------------------------------------------------------------------------------------ ASF/AMC

def rot(axis, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def euler(angles, order):
    """Rotation for `angles` about `order` (e.g. "xyz"): x applied first."""
    m = np.eye(3)
    for a, ax in zip(angles, order):
        m = rot(ax, a) @ m
    return m


class Skeleton:
    def __init__(self, path):
        self.bones, self.parent, self.children = {}, {}, {}
        section, bone = None, None
        lines = open(path).read().splitlines()
        for line in lines:
            t = line.split()
            if not t or t[0].startswith("#"):
                continue
            if t[0].startswith(":"):
                section = t[0]
                continue
            if section == ":bonedata":
                if t[0] == "begin":
                    bone = {"dof": [], "axis": np.eye(3)}
                elif t[0] == "end":
                    self.bones[bone["name"]] = bone
                elif t[0] == "name":
                    bone["name"] = t[1]
                elif t[0] == "direction":
                    bone["dir"] = np.array([float(v) for v in t[1:4]])
                elif t[0] == "length":
                    bone["len"] = float(t[1]) * INCH
                elif t[0] == "axis":
                    bone["axis"] = euler([float(v) for v in t[1:4]], t[4].lower())
                elif t[0] == "dof":
                    bone["dof"] = [d.lower() for d in t[1:]]
            elif section == ":hierarchy" and t[0] != "begin" and t[0] != "end":
                for c in t[1:]:
                    self.parent[c] = t[0]
                    self.children.setdefault(t[0], []).append(c)

    def order(self):
        out, todo = [], ["root"]
        while todo:
            b = todo.pop(0)
            out.append(b)
            todo += self.children.get(b, [])
        return out


def read_amc(path):
    frames, cur = [], None
    for line in open(path):
        t = line.split()
        if not t or t[0].startswith("#") or t[0].startswith(":"):
            continue
        if t[0].isdigit():
            cur = {}
            frames.append(cur)
        else:
            cur[t[0]] = [float(v) for v in t[1:]]
    return frames


def pose(skel, frame):
    """World rotation of every bone (relative to the T-pose rest), the root position and every
    bone's end, CMU axes."""
    world, pos, ends = {}, None, {}
    for name in skel.order():
        if name == "root":
            v = frame["root"]
            pos = np.array(v[:3]) * INCH
            world[name] = euler(v[3:6], "xyz")
            ends[name] = pos
            continue
        b = skel.bones[name]
        m = np.eye(3)
        if b["dof"]:
            m = euler(frame.get(name, [0] * len(b["dof"])), "".join(d[1] for d in b["dof"]))
        c = b["axis"]
        world[name] = world[skel.parent[name]] @ c @ m @ c.T
        ends[name] = ends[skel.parent[name]] + world[name] @ b["dir"] * b["len"]
    return pos, world, ends


# ------------------------------------------------------------------------------------------- tables

# CMU axes (Y up, the T-pose facing +Z, its left +X) to the armature's (Z up, facing -Y, left +X).
AXES = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])


def quat(m):
    """(w, x, y, z) of a rotation matrix."""
    w = math.sqrt(max(0.0, 1 + m[0, 0] + m[1, 1] + m[2, 2])) / 2
    x = math.copysign(math.sqrt(max(0.0, 1 + m[0, 0] - m[1, 1] - m[2, 2])) / 2, m[2, 1] - m[1, 2])
    y = math.copysign(math.sqrt(max(0.0, 1 - m[0, 0] + m[1, 1] - m[2, 2])) / 2, m[0, 2] - m[2, 0])
    z = math.copysign(math.sqrt(max(0.0, 1 - m[0, 0] - m[1, 1] + m[2, 2])) / 2, m[1, 0] - m[0, 1])
    return np.array([w, x, y, z])


def fetch(name):
    os.makedirs(VENDOR, exist_ok=True)
    s = name.split("_")[0]
    for f in (f"{s}.asf", f"{name}.amc"):
        p = os.path.join(VENDOR, f)
        if not os.path.exists(p):
            urllib.request.urlretrieve(URL.format(s=s, f=f), p)
    return os.path.join(VENDOR, f"{s}.asf"), os.path.join(VENDOR, f"{name}.amc")


def frames_of(trial):
    asf, amc = fetch(trial)
    skel = Skeleton(asf)
    return skel, [pose(skel, f) for f in read_amc(amc)]


def ankle_height(frames):
    """How high the ankles sit when a foot is down (CMU puts the floor at y = 0)."""
    lows = [min(e["ltibia"][1], e["rtibia"][1]) for _, _, e in frames]
    return float(np.percentile(lows, 5))


def facing(world):
    """Yaw of the pelvis (radians about CMU +Y, 0 = facing +Z)."""
    f = world["root"] @ np.array([0, 0, 1.0])
    return math.atan2(f[0], f[2])


def cycle(frames, start):
    """The gait period (in 120 fps frames) from `start`: the lag that best repeats the legs."""
    def feat(i):
        w = frames[i][1]
        return np.concatenate([w[b].ravel() for b in ("lfemur", "rfemur", "ltibia", "rtibia")])
    best = None
    for lag in range(50, 200):
        if start + lag + 10 >= len(frames):
            break
        d = sum(np.linalg.norm(feat(start + k) - feat(start + lag + k)) for k in range(0, 10, 3))
        if best is None or d < best[0]:
            best = (d, lag)
    return best[1]


def table(clip):
    trial, first, last, kind = TAKES[clip]
    skel, frames = frames_of(trial)
    if kind == "loop" and last is None:
        last = first + cycle(frames, first)
    last = min(last if last is not None else len(frames) - 1, len(frames) - 1)
    span = frames[first:last + 1]
    # Face -Y: undo the take's mean heading (unwrapped, so the average is sound).
    yaws = np.unwrap([facing(w) for _, w, _ in span])
    turn = rot("y", -math.degrees(float(np.mean(yaws))))
    to_rig = AXES @ turn
    n = max(2, round((len(span) - 1) * FPS / SRC_FPS))
    hip = skel.bones["lfemur"]["len"] + skel.bones["ltibia"]["len"]
    # Standing straight, the root is this far above the ankles, plus the ankles' own height.
    drop = -sum(skel.bones[b]["dir"][1] * skel.bones[b]["len"] for b in ("lhipjoint", "lfemur", "ltibia"))
    dirs = {ours: [round(float(v), 5) for v in AXES @ skel.bones[theirs]["dir"]] for ours, theirs in BONES.items() if theirs != "root"}
    out = {"trial": trial, "kind": kind, "frames": n, "leg": hip, "leg_rest": drop + ankle_height(frames),
           "dirs": dirs, "root": [], "bones": {b: [] for b in BONES}}
    p0 = to_rig @ span[0][0]
    p0[2] = 0.0  # keep the height above the floor
    for i in range(n + 1):
        src = span[min(len(span) - 1, round(i * SRC_FPS / FPS))]
        pos, world, _ = src
        p = to_rig @ pos - p0
        out["root"].append([round(float(v), 4) for v in p])
        for ours, theirs in BONES.items():
            # Undo the heading, then the same rotation in the armature's axes.
            m = AXES @ turn @ world[theirs] @ AXES.T
            out["bones"][ours].append([round(float(v), 5) for v in quat(m)])
    if kind == "loop":
        # In place: take out the cycle's mean travel; keep sway and bob.
        r = np.array(out["root"])
        drift = (r[-1] - r[0]) / n
        r = r - np.outer(np.arange(n + 1), drift)
        r[:, :2] -= r[:, :2].mean(axis=0)
        out["root"] = [[round(float(v), 4) for v in p] for p in r]
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    clips = sys.argv[1:] or list(TAKES)
    for clip in clips:
        t = table(clip)
        with open(os.path.join(OUT, f"{clip}.json"), "w") as f:
            json.dump(t, f, separators=(",", ":"))
        r = np.array(t["root"])
        print(f"{clip}: {t['trial']} {t['frames']} frames, root z {r[:, 2].min():.2f}..{r[:, 2].max():.2f}")


if __name__ == "__main__":
    main()
