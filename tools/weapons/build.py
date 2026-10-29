"""Build Rust Regime's first-person weapons as rigged glTF files, one per weapon.

Runs inside Blender's Python (`bpy`), headless:

    tools/weapons/build.sh                  # every weapon -> assets/models/weapons/<id>.glb
    tools/weapons/build.sh pistol rifle     # just these
    tools/weapons/build.sh --check          # verify every glb's rig (bones, parts, sockets, clips, size)
    tools/weapons/build.sh --preview pistol # also render a look-dev image to screenshots/weapons/<id>.png
    tools/weapons/build.sh --no-bake pistol # skip the wear texture bake (fast iteration)

Each weapon lives in guns/<id>.py with a `build()` returning a kit.Gun and a `SPEC` dict for the
checker. Conventions (axes, bones, sockets, clips, attachments): docs/superpowers/specs/2026-10-18-custom-weapons-design.md.
"""

import importlib
import os
import sys

if "--" in sys.argv:  # under `blender --python build.py -- args` our args follow the "--"
    sys.argv = sys.argv[:1] + sys.argv[sys.argv.index("--") + 1:]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from kit import check, preview  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "assets", "models", "weapons")
SHOTS = os.path.join(ROOT, "screenshots", "weapons")
ORDER = ["rocket", "rifle", "shotgun", "pistol", "smg", "dmr", "revolver", "grenade", "harpoon", "fist", "knife"]


def spec(gid):
    return importlib.import_module(f"guns.{gid}").SPEC


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = args or [g for g in ORDER if os.path.exists(os.path.join(HERE, "guns", f"{g}.py"))]
    if "--check" in sys.argv:
        bad = 0
        for gid in ids:
            path = os.path.join(OUT, f"{gid}.glb")
            problems, stats = check(path, spec(gid)) if os.path.exists(path) else (["not built"], {})
            print(f"{gid}: {'ok' if not problems else '; '.join(problems)} {stats}")
            bad += bool(problems)
        sys.exit(1 if bad else 0)
    for gid in ids:
        s = spec(gid)
        g = s["build"]()
        g.finish(OUT, bake="--no-bake" not in sys.argv)
        if "--preview" in sys.argv:
            os.makedirs(SHOTS, exist_ok=True)
            preview(os.path.join(SHOTS, f"{gid}.png"), **s["view"])


if __name__ == "__main__":
    main()
