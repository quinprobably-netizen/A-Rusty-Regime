"""Build Rust Regime's faction ships as glTF files, one per ship, with headless Blender (`bpy`):

    tools/ships/build.sh                   # every ship -> assets/models/ships/<id>.glb
    tools/ships/build.sh mule vantage      # just these
    tools/ships/build.sh --check           # verify every glb (tris, size, nodes, rest height, meshes)
    tools/ships/build.sh --preview mule    # also render a look-dev image to screenshots/ships/<id>.png
    tools/ships/build.sh --no-bake mule    # skip the wear texture bake (fast iteration)

Each ship lives in ships/<id>.py with a `build()` returning a kit.Ship and a `SPEC` dict for the
checker. Frame and budget: docs/superpowers/specs/2026-10-27-faction-ships-design.md.
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from kit import check, preview  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "assets", "models", "ships")
SHOTS = os.path.join(ROOT, "screenshots", "ships")
ORDER = ["kestrel", "litany", "mule", "vantage", "censer", "welder", "sentry", "jackal"]


def spec(sid):
    return importlib.import_module(f"ships.{sid}").SPEC


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = args or [s for s in ORDER if os.path.exists(os.path.join(HERE, "ships", f"{s}.py"))]
    if "--check" in sys.argv:
        bad = 0
        for sid in ids:
            path = os.path.join(OUT, f"{sid}.glb")
            problems, stats = check(path, spec(sid)) if os.path.exists(path) else (["not built"], {})
            print(f"{sid}: {'ok' if not problems else '; '.join(problems)} {stats}")
            bad += bool(problems)
        sys.exit(1 if bad else 0)
    for sid in ids:
        s = spec(sid)
        ship = s["build"]()
        ship.finish(OUT, bake="--no-bake" not in sys.argv)
        if "--preview" in sys.argv:
            os.makedirs(SHOTS, exist_ok=True)
            preview(os.path.join(SHOTS, f"{sid}.png"), **s["view"])
            for extra in ("inside", "top"):
                if extra in s:
                    preview(os.path.join(SHOTS, f"{sid}-{extra}.png"), **s[extra], fresh=extra == "top")


if __name__ == "__main__":
    main()
