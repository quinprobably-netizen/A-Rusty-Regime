"""The raiders' Jackal: the smallest fighter, a twin-boom scrapper built from stolen parts. A short
octagonal pod under a big bubble canopy, a pusher engine out of a Regime hull, straight stub wings
out to two booms that carry the tail fins and a tailplane joining them, small nozzles on the boom
ends, missile pods lashed under the wings with straps and cord. Patched, mismatched paint: Deserter
dark and orange, Regime slate, PMC white and gunmetal, Scrapper rust and brass, olive drab.
Solid hull: the canopy shows the seat, nothing walkable."""

from fighter import band, cockpit
from kit import Ship, bell, block, cyl, label, loft, nav_light, pipe, plan, prism, rivets, skid, stripe, tube

REST = 1.05
SIDES, PHASE = 8, 22.5
POD = [(-1.8, 0, 0.0, 0.46, 0.46), (-1.0, 0, 0.0, 0.62, 0.6), (0.5, 0, 0.0, 0.64, 0.62), (1.6, 0, -0.04, 0.5, 0.48),
       (2.5, 0, -0.08, 0.3, 0.28), (3.0, 0, -0.1, 0.12, 0.1), (3.2, 0, -0.1, 0, 0)]
K = 0.924
BOOM_X = 1.75


def build():
    s = Ship("jackal")
    dark, orange, pale = "deserter_dark", "deserter_orange", "deserter_pale"
    pod = loft("pod", POD, dark, sides=SIDES, phase=PHASE)
    canopy = [(-0.4, 0, 0.32, 0.0, 0.0), (-0.1, 0, 0.32, 0.36, 0.42), (0.5, 0, 0.32, 0.5, 0.68), (1.2, 0, 0.3, 0.46, 0.6),
              (1.8, 0, 0.26, 0.3, 0.36), (2.15, 0, 0.22, 0, 0)]
    s.add(cockpit(s, pod, ((0, 0.6, 0.15), (0.66, 1.6, 1.0)), canopy, (0, 0.6, -0.12), sides=12, phase=0.0, hull_mat=dark,
                  seat_mat="olive", frame="steel", trim=orange, screen="screen", hoops=(0.2,)))
    # Patches over the pod from a dozen donors: Regime slate, PMC white, a Deserter stripe, rivets.
    s.add(block("patch", (-K * 0.62 - 0.01, -0.9, 0.1), (0.04, 1.1, 0.6), "slate", bevel=0.01))
    s.add(rivets("prv", (-K * 0.62 - 0.03, -1.4, 0.42), (-K * 0.62 - 0.03, -0.4, 0.42), 5, r=0.025, axis="-x"))
    s.add(block("patch2", (K * 0.62 + 0.01, -0.5, -0.05), (0.04, 0.9, 0.5), "white", bevel=0.01))
    s.add(rivets("prv2", (K * 0.62 + 0.03, -0.9, 0.22), (K * 0.62 + 0.03, -0.1, 0.22), 4, r=0.025, axis="x"))
    s.add(block("patch3", (0, -1.2, K * 0.6 + 0.01), (0.5, 0.9, 0.04), "rust", bevel=0.01))
    s.add(band("stripe", POD, 1.8, 0.25, orange, sides=SIDES, phase=PHASE))
    s.add(band("noseband", POD, 2.55, 0.12, "hazard", sides=SIDES, phase=PHASE))
    s.add(label("MINE", (-K * 0.6 - 0.02, 1.25, -0.15), 0.22, pale, side=-1, depth=0.006))
    # A pusher engine pulled off a Regime hull: slate housing, gold-ish collar gone brass, bell.
    s.add(cyl("housing", (0, -1.4, 0.0), (0, -2.6, 0.0), 0.44, "slate", segs=16, bevel=0.02))
    s.add(tube("collar", (0, -2.45, 0.0), (0, -2.65, 0.0), 0.5, 0.38, "brass", segs=16))
    s.add(bell("bell", (0, -2.6, 0.0), (0, -3.15, 0.0), 0.32, 0.46, segs=16))
    s.node("exhaust.0", (0, -3.17, 0.0))
    s.add(pipe("feed", [(0.3, -1.4, 0.4), (0.3, -1.9, 0.5), (0.0, -2.2, 0.48)], 0.04, material="copper"))
    # Straight stub wings, each from a different donor, out past the booms.
    for sx, mat, patch in ((-1, "white", "gunmetal"), (1, "rust", "brass")):
        s.add(plan("wing", [(sx * 0.5, 0.2), (sx * 2.85, 0.0), (sx * 2.85, -0.95), (sx * 0.5, -1.15)], 0.14, mat, z=-0.05, bevel=0.02))
        s.add(block("wingpatch", (sx * 1.1, -0.45, 0.04), (0.6, 0.7, 0.03), patch, bevel=0.005))
        s.add(stripe("wingtip", (sx * 2.7, -0.47, -0.05), (0.3, 0.98, 0.14), orange if sx < 0 else "hazard"))
        nav_light(s, f"light.{0 if sx < 0 else 1}", (sx * 2.9, -0.45, -0.05), "red_light" if sx < 0 else "green_light", r=0.07)
    # Twin booms, mismatched, small nozzles on the ends, fins with a tailplane across their tops.
    for sx, mat, fin_mat in ((-1, "gunmetal", "hazard"), (1, "olive", "red")):
        x = sx * BOOM_X
        s.add(cyl("boom", (x, 0.5, 0.0), (x, -3.4, 0.0), 0.2, mat, segs=10, bevel=0.01))
        s.add(cyl("boomnose", (x, 0.5, 0.0), (x, 1.1, 0.0), 0.2, mat, r1=0.05, segs=10, bevel=0.0))
        s.add(tube("boomring", (x, -1.4, 0.0), (x, -1.55, 0.0), 0.23, 0.18, "steel", segs=10))
        s.add(bell("nozzle", (x, -3.4, 0.0), (x, -3.75, 0.0), 0.14, 0.2, segs=12))
        s.node(f"exhaust.{1 if sx < 0 else 2}", (x, -3.77, 0.0))
        s.add(prism("fin", [(-3.4, 0.1), (-2.3, 0.1), (-2.8, 1.05), (-3.35, 1.05)], 0.08, fin_mat, x=x, bevel=0.01))
        s.add(prism("ventral", [(-3.3, -0.1), (-2.7, -0.1), (-3.2, -0.5)], 0.06, mat, x=x, bevel=0.005))
    s.add(block("tailplane", (0, -3.05, 1.06), (2 * BOOM_X + 0.3, 0.7, 0.08), "deserter_tan", bevel=0.01))
    s.add(block("tailpatch", (-0.6, -3.05, 1.11), (0.7, 0.5, 0.02), "slate", bevel=0))
    nav_light(s, "light.2", (0, -3.2, 1.15), "lights_amber", r=0.06)
    s.add(label("J4CK", (-BOOM_X - 0.21, -1.0, 0.0), 0.2, orange, side=-1, depth=0.006))
    # Missile pods lashed under the wings: straps round wing and pod, a cord wrap, mismatched.
    for sx, mat in ((-1, "olive"), (1, orange)):
        px = sx * 2.35
        s.add(cyl("pod", (px, 0.3, -0.36), (px, -1.4, -0.36), 0.22, mat, segs=12, bevel=0.02))
        for ox, oz in ((-0.09, 0.07), (0.09, 0.07), (-0.09, -0.09), (0.09, -0.09)):
            s.add(tube("tubeend", (px + ox, 0.3, -0.36 + oz), (px + ox, 0.36, -0.36 + oz), 0.07, 0.05, "black", segs=8))
        for y in (-0.05, -1.05):
            s.add(block("lash", (px, y, -0.2), (0.5, 0.08, 0.5), "leather", bevel=0.005))
        s.add(cyl("cord", (px, -0.55, -0.6), (px, -0.55, 0.05), 0.035, "cord", segs=6, bevel=0))
    # Skids under the booms and a nose prop.
    for sx in (-1, 1):
        s.add(skid("skid", (sx * BOOM_X, -1.0), 2.4, -REST, -0.2, bar=0.12))
    s.add(cyl("noseprop", (0, 2.0, -0.4), (0, 2.0, -REST + 0.06), 0.05, "steel", segs=8, bevel=0))
    s.add(cyl("nosepad", (0, 2.0, -REST), (0, 2.0, -REST + 0.06), 0.14, "black", segs=10, bevel=0))
    s.node("heat", (0, 3.3, -0.1))
    return s


SPEC = {
    "build": build,
    "size": (6.95, 5.95, 2.25),
    "rest": REST,
    "nodes": ["exhaust.0", "exhaust.1", "exhaust.2", "heat", "light.0", "light.1", "light.2"],
    "view": {"cam": (-6.5, 6.5, 3.8), "look": (0, -0.6, 0.1), "lens": 40},
    "top": {"cam": (0, -0.61, 17.0), "look": (0, -0.6, 0), "lens": 50},
}
