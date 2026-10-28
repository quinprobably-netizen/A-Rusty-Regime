"""Build Rust Regime's faction bases as glTF files, one per base, with headless Blender (`bpy`):

    tools/bases/build.sh                    # every base -> assets/models/bases/<id>.glb, and assets/bases.toml
    tools/bases/build.sh yard outpost       # just these models
    tools/bases/build.sh --check            # verify every glb (tris, size, nodes, ground level, meshes)
    tools/bases/build.sh --preview yard     # also render look-dev images to screenshots/bases/<id>[-inside].png
    tools/bases/build.sh --no-bake yard     # skip the wear texture bake (fast iteration)
    tools/bases/build.sh --toml             # only rewrite assets/bases.toml from the SPECs

Each base lives in bases/<id>.py with a `build()` returning a basekit.Base and a `SPEC` dict: the
checker's numbers, and the site, pad, door and collision boxes the game reads, written out to
`assets/bases.toml` in the game's frame so the python file is the single source of truth.
Design: docs/superpowers/specs/2026-10-27-faction-bases-design.md.
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(os.path.dirname(HERE), "ships"))

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "assets", "models", "bases")
SHOTS = os.path.join(ROOT, "screenshots", "bases")
TOML = os.path.join(ROOT, "assets", "bases.toml")
ORDER = ["roost", "reliquary", "yard", "outpost"]


def spec(bid):
    return importlib.import_module(f"bases.{bid}").SPEC


def main():
    from basekit import check, preview, write_toml

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = args or [b for b in ORDER if os.path.exists(os.path.join(HERE, "bases", f"{b}.py"))]
    if "--check" in sys.argv:
        bad = 0
        for bid in ids:
            path = os.path.join(OUT, f"{bid}.glb")
            problems, stats = check(path, spec(bid)) if os.path.exists(path) else (["not built"], {})
            print(f"{bid}: {'ok' if not problems else '; '.join(problems)} {stats}")
            bad += bool(problems)
        sys.exit(1 if bad else 0)
    if "--toml" not in sys.argv:
        for bid in ids:
            s = spec(bid)
            base = s["build"]()
            base.finish(OUT, bake="--no-bake" not in sys.argv)
            if "--preview" in sys.argv:
                os.makedirs(SHOTS, exist_ok=True)
                preview(os.path.join(SHOTS, f"{bid}.png"), **s["view"])
                for key, suffix in (("inside", "-inside"), ("annex", "-annex"), ("annex_out", "-annex-out")):
                    if key in s:
                        preview(os.path.join(SHOTS, f"{bid}{suffix}.png"), **s[key])
    write_toml(TOML, [(bid, spec(bid)) for bid in ORDER if os.path.exists(os.path.join(HERE, "bases", f"{bid}.py"))])


if __name__ == "__main__":
    main()
