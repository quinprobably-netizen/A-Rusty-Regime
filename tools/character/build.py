"""Build Rust Regime's characters as skinned glTF files, one per character.

Runs inside Blender's Python (`bpy`), headless:

    tools/character/build.sh                    # every character -> assets/models/character/<id>.glb
    tools/character/build.sh runner acolyte     # just these
    tools/character/build.sh --check            # verify every glb (bones, clips, meshes, triangles)
    tools/character/build.sh --preview runner   # also render look-dev images to screenshots/characters/
    tools/character/build.sh --no-bake runner   # skip the wear texture bake (fast iteration)
    tools/character/build.sh --grips runner     # re-solve only the hand poses on each weapon
    tools/character/build.sh --hands runner     # render the built hands on each weapon (a check)
    tools/character/build.sh --eye runner       # render the rifle hands from the player's eye

Each character lives in chars/<id>.py with a `build()` returning a kit.Char and a `SPEC` dict. The
contract (skeleton, grip frames, meshes, clips): docs/superpowers/specs/2026-10-18-character-roster-design.md.
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import kit  # noqa: E402

SHOTS = os.path.join(kit.ROOT, "screenshots", "characters")
ORDER = ["acolyte", "zealot", "choir", "mechanic", "bruiser", "trapper",
         "runner", "breaker", "ghost", "contractor", "juggernaut", "handler"]


def spec(cid):
    return importlib.import_module(f"chars.{cid}").SPEC


def solve_grips(ids):
    """Re-solve only the finger poses: each character's rig is all the solver needs, so its build
    stops as soon as the rig exists."""
    import grips
    import real

    class Rigged(Exception):
        pass
    begin = real.begin

    def stop(cid, build):
        raise Rigged(begin(cid, build))
    real.begin = stop
    try:
        for cid in ids:
            try:
                spec(cid)["build"]()
            except Rigged as r:
                grips.solve(r.args[0])
    finally:
        real.begin = begin


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = args or [c for c in ORDER if os.path.exists(os.path.join(HERE, "chars", f"{c}.py"))]
    if "--check" in sys.argv:
        bad = 0
        for cid in ids:
            path = os.path.join(kit.OUT, f"{cid}.glb")
            problems, stats = kit.check(path, spec(cid).get("budget", (25000, 75000))) if os.path.exists(path) else (["not built"], {})
            print(f"{cid}: {'ok' if not problems else '; '.join(problems)} {stats}")
            bad += bool(problems)
        sys.exit(1 if bad else 0)
    if "--grips" in sys.argv:
        solve_grips(ids)
    if "--hands" in sys.argv:
        import grips
        for cid in ids:
            print("\n".join(grips.render(cid)))
    if "--eye" in sys.argv:
        import grips
        for cid in ids:
            print("\n".join(grips.render_fp(cid)))
    if any(a in sys.argv for a in ("--grips", "--hands", "--eye")):
        return
    for cid in ids:
        s = spec(cid)
        c = s["build"]()
        c.finish(bake="--no-bake" not in sys.argv, budget=s.get("budget", (25000, 75000)))
        if "--preview" in sys.argv:
            os.makedirs(SHOTS, exist_ok=True)
            col = s.get("colors")
            kit.preview(os.path.join(SHOTS, f"{cid}.png"), colors=col)
            kit.preview(os.path.join(SHOTS, f"{cid}-back.png"), cam=(-1.6, 2.8, 1.4))
            kit.preview(os.path.join(SHOTS, f"{cid}-face.png"), cam=(0.35, -0.9, 1.68), look=(0, 0, 1.6), lens=70, gun=False)
            kit.preview(os.path.join(SHOTS, f"{cid}-run.png"), clip="run", frame=5, cam=(2.6, -1.4, 1.2))


if __name__ == "__main__":
    main()
