"""Write the clips from `anim.py` into character glbs, in place, without Blender:

    python3 glbanim.py [ids]        # all characters when no ids are given

Only the animations change (the old ones and their data are dropped); meshes, skin, materials and
textures stay byte for byte. The two-hand carries the clips need come from the glb itself: the
`carries` extra this script writes, or, on a glb fresh from Blender, the carry clips `build.py`
bakes (`carry.<name>`), or an older glb's own clips (each gait's first frame held the gun).
"""
import json
import os
import struct
import sys

import numpy as np

import anim

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "assets", "models", "character")
ORDER = ["acolyte", "zealot", "choir", "mechanic", "bruiser", "trapper",
         "runner", "breaker", "ghost", "contractor", "juggernaut", "handler"]
# glTF's Y-up axes from Blender's Z-up: (x, y, z) -> (x, z, -y).
M = np.array([[1.0, 0, 0], [0, 0, 1], [0, -1, 0]])
# Which clip's first frame held each carry, in glbs from before the carry clips.
LEGACY = {"ready": "idle", "run": "run", "sprint": "sprint", "crouch": "crouch", "slide": "slide"}


def read(path):
    data = open(path, "rb").read()
    n = struct.unpack("<I", data[12:16])[0]
    j = json.loads(data[20:20 + n])
    o = 20 + n
    bn = struct.unpack("<I", data[o:o + 4])[0]
    return j, bytearray(data[o + 8:o + 8 + bn])


def write(path, j, binary):
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    binary = bytes(binary) + b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON") + js)
        f.write(struct.pack("<I4s", len(binary), b"BIN\0") + binary)


def accessor(j, binary, i):
    a = j["accessors"][i]
    v = j["bufferViews"][a["bufferView"]]
    n = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}[a["type"]]
    off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    return np.frombuffer(bytes(binary), dtype=np.float32, count=a["count"] * n, offset=off).reshape(a["count"], n)


def qmat(q):
    """glTF (x, y, z, w) to a matrix."""
    x, y, z, w = q
    return anim.from_quat((w, x, y, z))


def matq(m):
    w, x, y, z = anim.to_quat(m)
    return [x, y, z, w]


class Glb:
    def __init__(self, path):
        self.path = path
        self.j, self.bin = read(path)
        nodes = self.j["nodes"]
        self.index = {n["name"]: i for i, n in enumerate(nodes)}
        self.parent = {}
        for i, n in enumerate(nodes):
            for c in n.get("children", []):
                self.parent[c] = i
        self.joints = [nodes[i]["name"] for i in self.j["skins"][0]["joints"]]
        self.rest_rot = {b: qmat(nodes[self.index[b]].get("rotation", [0, 0, 0, 1])) for b in self.joints}
        self.rest_t = {b: np.array(nodes[self.index[b]].get("translation", [0, 0, 0])) for b in self.joints}

    def rest(self):
        """The skeleton in armature space."""
        world = {}

        def frame(b):
            if b in world:
                return world[b]
            p = self.parent.get(self.index[b])
            pname = self.j["nodes"][p]["name"] if p is not None else None
            if pname in self.rest_rot:
                pr, pt = frame(pname)
                world[b] = (pr @ self.rest_rot[b], pt + pr @ self.rest_t[b])
            else:
                world[b] = (self.rest_rot[b], self.rest_t[b])
            return world[b]

        bones = {}
        for b in self.joints:
            r, t = frame(b)
            p = self.parent.get(self.index[b])
            pname = self.j["nodes"][p]["name"] if p is not None and self.j["nodes"][p]["name"] in self.rest_rot else None
            kids = [self.j["nodes"][c]["name"] for c in self.j["nodes"][self.index[b]].get("children", [])]
            # Length: to the child that carries the chain on (the one straight down the bone's Y).
            length = 0.1
            for k in kids:
                off = self.rest_t[k]
                if np.linalg.norm(off[[0, 2]]) < 0.02 * max(1e-6, abs(off[1])) + 1e-4:
                    length = float(off[1])
                    break
            bones[b] = (pname, M.T @ r, M.T @ t, length)
        return anim.Rest(bones)

    def clip_pose(self, name, frame=0):
        """A clip's frame as a pose (pose-basis matrices and hips.loc)."""
        a = next((a for a in self.j.get("animations", []) if a["name"] == name), None)
        if a is None:
            return None
        pose = {}
        for ch in a["channels"]:
            b = self.j["nodes"][ch["target"]["node"]]["name"]
            if b not in self.rest_rot:
                continue
            out = accessor(self.j, self.bin, a["samplers"][ch["sampler"]]["output"])
            v = out[min(frame, len(out) - 1)]
            if ch["target"]["path"] == "rotation":
                pose[b] = self.rest_rot[b].T @ qmat(v)
            elif ch["target"]["path"] == "translation" and b == "hips":
                pose["hips.loc"] = tuple(self.rest_rot[b].T @ (np.array(v) - self.rest_t[b]))
        return pose

    def carries(self, rest):
        saved = self.j.get("extras", {}).get("carries")
        if saved:
            return {c: {b: np.array(m) for b, m in v.items()} for c, v in saved.items()}
        poses = {}
        for carry, legacy in LEGACY.items():
            p = self.clip_pose(f"carry.{carry}") or self.clip_pose(legacy)
            if p is None:
                raise SystemExit(f"{self.path}: no carry {carry}")
            poses[carry] = p
        return anim.carries_from(rest, poses)

    def replace_animations(self, clips, carries):
        j = self.j
        old = {s[k] for a in j.get("animations", []) for s in a["samplers"] for k in ("input", "output")}
        keep = [i for i in range(len(j["accessors"])) if i not in old]
        amap = {o: n for n, o in enumerate(keep)}
        views_used = {j["accessors"][i]["bufferView"] for i in keep} | {im["bufferView"] for im in j.get("images", []) if "bufferView" in im}
        vkeep = sorted(views_used)
        vmap = {o: n for n, o in enumerate(vkeep)}
        out = bytearray()
        views = []
        for o in vkeep:
            v = dict(j["bufferViews"][o])
            start = v.get("byteOffset", 0)
            chunk = self.bin[start:start + v["byteLength"]]
            out += b"\0" * (-len(out) % 4)
            v["byteOffset"] = len(out)
            out += chunk
            views.append(v)
        accessors = []
        for o in keep:
            a = dict(j["accessors"][o])
            a["bufferView"] = vmap[a["bufferView"]]
            accessors.append(a)
        for m in j.get("meshes", []):
            for p in m["primitives"]:
                p["attributes"] = {k: amap[v] for k, v in p["attributes"].items()}
                if "indices" in p:
                    p["indices"] = amap[p["indices"]]
                if "targets" in p:
                    p["targets"] = [{k: amap[v] for k, v in t.items()} for t in p["targets"]]
        for s in j.get("skins", []):
            if "inverseBindMatrices" in s:
                s["inverseBindMatrices"] = amap[s["inverseBindMatrices"]]
        for im in j.get("images", []):
            if "bufferView" in im:
                im["bufferView"] = vmap[im["bufferView"]]

        def add(values, kind, minmax=False):
            arr = np.asarray(values, dtype=np.float32)
            nonlocal out
            out += b"\0" * (-len(out) % 4)
            views.append({"buffer": 0, "byteOffset": len(out), "byteLength": arr.nbytes})
            out += arr.tobytes()
            a = {"bufferView": len(views) - 1, "componentType": 5126, "count": len(arr), "type": kind}
            if minmax:
                a["min"], a["max"] = [float(arr.min())], [float(arr.max())]
            accessors.append(a)
            return len(accessors) - 1

        animations = []
        times = {}
        for name, poses in clips.items():
            n = len(poses)
            if n not in times:
                times[n] = add([i / anim.FPS for i in range(n)], "SCALAR", minmax=True)
            channels, samplers = [], []

            def channel(bone, path, values, kind):
                samplers.append({"input": times[n], "interpolation": "LINEAR", "output": add(values, kind)})
                channels.append({"sampler": len(samplers) - 1, "target": {"node": self.index[bone], "path": path}})

            if name == "reload":
                bones = anim.ARM_CHAIN
            elif name in anim.ADDITIVE:
                bones = sorted({b for p in poses for b in p if b != "hips.loc"})
            else:
                bones = [b for b in self.joints if not b.startswith("prop_")]
            for b in bones:
                qs, prev = [], None
                for p in poses:
                    P = anim.pose_matrix(p, b)
                    if name in anim.ADDITIVE:
                        m = self.rest_rot[b] @ P @ self.rest_rot[b].T
                    else:
                        m = self.rest_rot[b] @ P
                    q = np.array(matq(m))
                    if prev is not None and q @ prev < 0:
                        q = -q  # keep neighbours in the same hemisphere so LINEAR (slerp) takes the short way
                    qs.append(q)
                    prev = q
                channel(b, "rotation", qs, "VEC4")
            if name not in anim.ADDITIVE and name != "reload":
                ts = [self.rest_t["hips"] + self.rest_rot["hips"] @ np.array(p.get("hips.loc", (0, 0, 0))) for p in poses]
                channel("hips", "translation", ts, "VEC3")
            animations.append({"name": name, "channels": channels, "samplers": samplers})

        j["accessors"] = accessors
        j["bufferViews"] = views
        j["buffers"] = [{"byteLength": len(out)}]
        j["animations"] = animations
        j.setdefault("extras", {})["carries"] = {c: {b: np.asarray(m).tolist() for b, m in v.items()} for c, v in carries.items()}
        self.bin = out
        write(self.path, j, out)


def patch(path):
    g = Glb(path)
    rest = g.rest()
    carries = g.carries(rest)
    ctx = anim.Ctx(rest, carries)
    clips = anim.build(ctx)
    assert list(clips) == anim.CLIP_NAMES, list(clips)
    g.replace_animations(clips, carries)
    return path


def main():
    ids = [a for a in sys.argv[1:] if not a.startswith("--")] or ORDER
    for cid in ids:
        path = os.path.join(OUT, f"{cid}.glb")
        before = os.path.getsize(path)
        patch(path)
        print(f"{cid}: {before // 1024} -> {os.path.getsize(path) // 1024} KB")


if __name__ == "__main__":
    main()
