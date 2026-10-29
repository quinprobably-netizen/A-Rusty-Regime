"""Build Rust Regime's posts: small faction outposts the game scatters over each world, one glb each,
with headless Blender (`bpy`), on the base kit:

    tools/bases/posts.sh                     # every post -> assets/models/posts/<id>.glb
    tools/bases/posts.sh watch camp          # just these
    tools/bases/posts.sh --check             # verify every glb (tris, meshes, size, nodes, footprint, texture)
    tools/bases/posts.sh --preview watch     # also render screenshots/posts/<id>.png (30 m) and <id>-near.png
    tools/bases/posts.sh --no-bake watch     # skip the wear texture bake (fast iteration)
    tools/bases/posts.sh --toml              # only rewrite assets/posts.toml from the SPECs

A post is a base cut down: a footprint under POST_MAX metres a side, under TRIS_MAX triangles, at
most MESHES_MAX meshes and a TEX texture. Each lives in posts/<id>.py with a `build()` returning a
basekit.Base and a SPEC in the bases' format (footprint, door, collision boxes, nodes, crew), so the
game can read posts the way it reads bases. The id `outpost` is Site Vantage; these are "posts".
The previews stand each post on its world's ground under its world's sky (`WORLDS`), and light its
fire and beacons, so the render says whether it belongs there.
"""

import importlib
import math
import os
import struct
import sys

if "--" in sys.argv:  # under `blender --python posts.py -- args` our args follow the "--"
    sys.argv = sys.argv[:1] + sys.argv[sys.argv.index("--") + 1:]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(os.path.dirname(HERE), "ships"))

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "assets", "models", "posts")
SHOTS = os.path.join(ROOT, "screenshots", "posts")
ORDER = ["watch", "relay", "camp", "sensor"]

TRIS_MAX = 15000
MESHES_MAX = 4
TEX = 1024
POST_MAX = 14.0  # metres, either side of the footprint
KINDS = ("lamp", "flood", "blink", "strobe", "fire", "weld", "smoke", "sound", "spin")

# Each world's look for the previews: ground (its `palette.low` in assets/system.toml), sky, and the
# sun's tint and strength. Frost has no air: a black sky and a hard white sun.
WORLDS = {
    "home": {"ground": (0.22, 0.34, 0.14), "sky": (0.32, 0.5, 0.8), "sun": (1.0, 0.96, 0.88), "power": 4.5},
    "bastion": {"ground": (0.26, 0.28, 0.31), "sky": (0.55, 0.58, 0.62), "sun": (0.92, 0.95, 1.0), "power": 3.0},
    "cinder": {"ground": (0.55, 0.27, 0.12), "sky": (0.75, 0.38, 0.14), "sun": (1.0, 0.8, 0.6), "power": 3.2},
    "frost": {"ground": (0.62, 0.68, 0.76), "sky": (0.004, 0.005, 0.01), "sun": (1.0, 1.0, 1.0), "power": 2.6},
}
GLOWS = {"fire": ((1.0, 0.55, 0.2), 260.0), "blink": ((1.0, 0.1, 0.05), 60.0), "strobe": ((0.9, 0.95, 1.0), 80.0)}


def spec(pid):
    return importlib.import_module(f"posts.{pid}").SPEC


def shot(path, view, body):
    """A look-dev render on `body`'s ground under its sky: `basekit.preview` sets up the camera,
    lights and ground (at a thumbnail, thrown away), then the stage is tinted and rendered again."""
    import bpy
    from basekit import preview
    from mathutils import Vector

    preview(path, **view, res=(48, 30), fresh=True)
    w = WORLDS[body]
    scene = bpy.context.scene
    for o in [o for o in bpy.data.objects if o.get("preview")]:
        if o.name.startswith("ground"):
            o.location.z = -0.02
            o.scale = (40, 40, 1)
            bsdf = o.data.materials[0].node_tree.nodes["Principled BSDF"]
            bsdf.inputs["Base Color"].default_value = (*w["ground"], 1)
        elif o.type == "LIGHT" and o.data.type == "SUN":
            o.data.color = w["sun"]
            o.data.energy *= w["power"] / 4.0
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (*w["sky"], 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0 if body != "frost" else 0.0
    for e in [o for o in bpy.data.objects if o.type == "EMPTY"]:
        kind = e.name.split(".")[0]
        if kind in GLOWS:
            colour, energy = GLOWS[kind]
            ld = bpy.data.lights.new(e.name, "POINT")
            ld.energy, ld.color, ld.shadow_soft_size = energy, colour, 0.2
            lo = bpy.data.objects.new(e.name, ld)
            lo.location = e.matrix_world.translation + Vector((0, 0, 0.2))
            lo["preview"] = True
            scene.collection.objects.link(lo)
    scene.cycles.samples = 32
    scene.render.resolution_x, scene.render.resolution_y = 960, 600
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def _jpeg_size(data):
    """(width, height) of a JPEG from its first frame header, or None."""
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker, length = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + length
    return None


def check(pid):
    """The base checker at the post budget, the SPEC's own sense (`basekit.check_spec`), and the
    post rules: footprint, every node a known kind, a sound and a light that moves, the texture size."""
    import kit
    import weapons_kit as wk
    from basekit import SOUNDS, check_spec

    s = spec(pid)
    path = os.path.join(OUT, f"{pid}.glb")
    if not os.path.exists(path):
        return ["not built"], {}
    kit.TRIS_MAX, kit.MESHES_MAX = TRIS_MAX, MESHES_MAX
    problems, stats = kit.check(path, {"size": s["size"], "rest": s["depth"], "nodes": s["nodes"]})
    problems += check_spec(s)
    if max(s["footprint"]) > POST_MAX:
        problems.append(f"footprint {s['footprint']}, want under {POST_MAX} m a side")
    for n in s["nodes"]:
        parts = n.split(".")
        if parts[0] not in KINDS:
            problems.append(f"node {n}: unknown kind")
        elif parts[0] == "sound" and (len(parts) != 3 or parts[1] not in SOUNDS):
            problems.append(f"node {n}: unknown sound")
        elif parts[0] == "spin" and (len(parts) != 4 or parts[1] not in "xyz" or not parts[2].lstrip("-").isdigit()):
            problems.append(f"node {n}: want spin.<axis>.<rpm>.<n>")
    kinds = {n.split(".")[0] for n in s["nodes"]}
    if "sound" not in kinds:
        problems.append("no sound node")
    if not kinds & {"blink", "strobe", "fire"}:
        problems.append("no blink, strobe or fire")
    if s["body"] == "frost" and kinds & {"fire", "smoke"}:
        problems.append("fire or smoke on airless Frost")
    j, _ = wk.read_glb(path)
    data = open(path, "rb").read()
    blob = data[20 + struct.unpack("<I", data[12:16])[0] + 8:]
    for img in j.get("images", []):
        view = j["bufferViews"][img["bufferView"]]
        start = view.get("byteOffset", 0)
        size = _jpeg_size(blob[start:start + view["byteLength"]])
        if size and max(size) > TEX:
            problems.append(f"texture {size[0]}x{size[1]}, want at most {TEX}")
    stats["meshes"] = sum(1 for n in j["nodes"] if "mesh" in n)
    return problems, stats


TOML = os.path.join(ROOT, "assets", "posts.toml")
HEADER = [
    "# The posts: small faction outposts the game scatters over each post's world (`src/solar/post.rs`),",
    "# for `models/posts/<id>.glb`. GENERATED by `tools/bases/posts.sh --toml` from the SPEC in",
    "# `tools/bases/posts/<id>.py`: edit that, not this. The same fields and frame as `bases.toml`, with",
    "# no site: the game picks each post's places from its world's seed. Each has a supply cache at its door.",
    "",
]


def write_toml():
    import basekit

    specs = []
    for pid in ORDER:
        s = dict(spec(pid))
        s["stations"] = [("cache", s["door"], "Supply cache")]
        specs.append((pid, s))
    basekit.write_toml(TOML, specs, table="post", header=HEADER)


def main():
    import basekit

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = args or [p for p in ORDER if os.path.exists(os.path.join(HERE, "posts", f"{p}.py"))]
    if "--check" in sys.argv:
        bad = 0
        for pid in ids:
            problems, stats = check(pid)
            print(f"{pid}: {'ok' if not problems else '; '.join(problems)} {stats}")
            bad += bool(problems)
        sys.exit(1 if bad else 0)
    if "--toml" in sys.argv:
        write_toml()
        return
    basekit.TEX = TEX  # Base.finish bakes at basekit.TEX
    for pid in ids:
        s = spec(pid)
        post = s["build"]()
        post.finish(OUT, bake="--no-bake" not in sys.argv)
        if "--preview" in sys.argv:
            os.makedirs(SHOTS, exist_ok=True)
            shot(os.path.join(SHOTS, f"{pid}.png"), s["view"], s["body"])
            if "near" in s:
                shot(os.path.join(SHOTS, f"{pid}-near.png"), s["near"], s["body"])
    write_toml()


if __name__ == "__main__":
    main()
