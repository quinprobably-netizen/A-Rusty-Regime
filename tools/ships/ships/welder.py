"""The Scrappers' Welder: a patrol fighter in the Mule's welded-hauler styling. Chunky and
asymmetric: a rust-orange core of mismatched slabs held on by fat weld beads, the cockpit pod hung
off the right flank, one big wing slab to port and one stubby slab to starboard, a big gunmetal
engine pod under the big wing and a small copper one by the pod, a claw rack on the nose, a strapped
brass tank and pipework, hazard stripes. Solid hull: the canopy shows the seat, nothing walkable."""

from fighter import cockpit
from kit import (Ship, bell, block, cyl, label, loft, nav_light, pipe, prism, rivets, rotate, skid, srgb, stripe, tube, wk)

wk.PALETTE["scrap_orange"] = srgb("#B5561F", metallic=0.35, roughness=0.75, wear=0.7)
wk.PALETTE["scrap_red"] = srgb("#7A2A14", metallic=0.3, roughness=0.8, wear=0.6)

REST = 1.35
POD = [(-0.9, 1.35, 0.15, 0.36, 0.34), (-0.5, 1.35, 0.15, 0.56, 0.56), (1.8, 1.35, 0.15, 0.58, 0.58), (2.8, 1.35, 0.08, 0.46, 0.44),
       (3.4, 1.35, 0.0, 0.22, 0.2)]


def weld(s, p0, p1, r=0.04):
    """A fat weld bead along a seam."""
    s.add(cyl("weld", p0, p1, r, "steel", segs=6, bevel=0))


def build():
    s = Ship("welder")
    orange, red = "scrap_orange", "scrap_red"
    # The core: a rust-orange box with a tapered snout, slabs welded on at odd angles.
    s.add(block("core", (-0.2, -0.4, 0.0), (1.7, 6.2, 1.3), orange, bevel=0.05))
    s.add(block("snout", (-0.2, 3.3, -0.1), (1.5, 1.6, 1.0), orange, bevel=0.05, taper=(0.8, 0.6)))
    s.add(rotate(block("roofslab", (-0.35, -1.0, 0.72), (1.3, 3.2, 0.16), "brass", bevel=0.02), (-0.35, -1.0, 0.72), "y", 5))
    weld(s, (-1.0, -2.6, 0.72), (-1.0, 0.6, 0.72))
    weld(s, (0.3, -2.6, 0.78), (0.3, 0.6, 0.78))
    s.add(rotate(block("noseslab", (-0.2, 2.1, 0.62), (1.4, 1.4, 0.14), red, bevel=0.02), (-0.2, 2.1, 0.62), "x", -6))
    weld(s, (-0.9, 1.4, 0.66), (0.5, 1.4, 0.66))
    s.add(rotate(block("portslab", (-1.08, 0.6, -0.05), (0.14, 3.0, 1.0), "rust", bevel=0.02), (-1.08, 0.6, -0.05), "z", 3))
    weld(s, (-1.13, -0.9, 0.45), (-1.13, 2.1, 0.45))
    weld(s, (-1.13, -0.9, -0.55), (-1.13, 2.1, -0.55))
    s.add(block("bellyslab", (-0.3, -1.2, -0.7), (1.4, 3.6, 0.14), "copper", bevel=0.02))
    weld(s, (-1.0, -3.0, -0.72), (0.4, -3.0, -0.72))
    for i in range(5):
        s.add(stripe("hazard", (-1.07, -2.8 + i * 0.36, -0.35), (0.02, 0.18, 0.4), "hazard" if i % 2 == 0 else "black"))
    s.add(rivets("rv", (-1.13, -3.2, 0.5), (-1.13, -1.2, 0.5), 7, r=0.035, axis="-x"))
    s.add(rivets("rv2", (-1.16, -0.8, -0.3), (-1.16, 2.0, -0.3), 8, r=0.035, axis="-x"))
    s.add(label("W-9", (-1.17, 0.9, 0.05), 0.42, "black", side=-1, depth=0.01))
    # The cockpit pod off the right flank on a welded bracket, canopy over the seat.
    pod = loft("pod", POD, "rust", sides=10)
    canopy = [(0.0, 1.35, 0.55, 0.0, 0.0), (0.3, 1.35, 0.55, 0.32, 0.36), (1.0, 1.35, 0.55, 0.4, 0.6), (1.9, 1.35, 0.5, 0.36, 0.5),
              (2.6, 1.35, 0.4, 0.18, 0.28), (2.9, 1.35, 0.35, 0, 0)]
    s.add(cockpit(s, pod, ((1.35, 1.1, 0.5), (0.66, 1.7, 1.0)), canopy, (1.35, 1.25, 0.12), sides=10, hull_mat="rust",
                  seat_mat="leather", frame="steel", trim="brass", screen="screen", hoops=(0.65, 1.6)))
    s.add(block("bracket", (0.8, 0.4, 0.0), (0.6, 2.4, 0.5), orange, bevel=0.03))
    s.add(block("bracket2", (0.8, 1.9, -0.25), (0.5, 0.5, 0.3), "copper", bevel=0.02))
    weld(s, (0.65, -0.8, 0.27), (0.65, 1.6, 0.27))
    weld(s, (1.05, -0.8, 0.27), (1.05, 1.6, 0.27))
    for y in (-0.5, 2.4):
        s.add(tube("podring", (1.35, y - 0.06, 0.15), (1.35, y + 0.06, 0.15), 0.6, 0.5, "steel", segs=10))
    s.add(rivets("podrv", (1.95, -0.3, 0.15), (1.95, 2.2, 0.15), 7, r=0.03, axis="x"))
    # One big wing slab to port, bent down a touch, hazard tip; one stubby slab to starboard.
    big = block("bigwing", (-2.75, -1.3, -0.15), (3.4, 2.6, 0.22), orange, bevel=0.03, taper=(1.0, 0.92))
    s.add(rotate(big, (-1.05, -1.3, -0.15), "y", 6))
    s.add(rotate(block("wingslab", (-2.4, -0.8, 0.0), (1.6, 1.2, 0.08), "brass", bevel=0.01), (-1.05, -1.3, -0.15), "y", 6))
    for i in range(4):
        s.add(rotate(stripe("tip", (-4.3, -2.3 + i * 0.6, -0.15), (0.32, 0.3, 0.22), "hazard"), (-1.05, -1.3, -0.15), "y", 6))
    weld(s, (-1.1, -2.6, -0.02), (-1.1, 0.0, -0.02))
    s.add(block("stub", (2.6, -0.7, 0.0), (1.4, 1.3, 0.18), red, bevel=0.03))
    s.add(stripe("stubtip", (3.15, -0.7, 0.0), (0.3, 1.3, 0.18), "hazard"))
    weld(s, (1.92, -1.3, 0.1), (1.92, -0.1, 0.1))
    nav_light(s, "light.0", (-4.5, -1.6, -0.35), "red_light", r=0.09)
    nav_light(s, "light.1", (3.36, -0.7, 0.0), "green_light", r=0.08)
    # Two different engines: a big gunmetal pod under the big wing, a small copper one by the pod.
    s.add(cyl("bigengine", (-2.1, 0.3, -0.6), (-2.1, -3.5, -0.6), 0.62, "gunmetal", segs=18, bevel=0.03))
    s.add(cyl("intake", (-2.1, 0.3, -0.6), (-2.1, 0.55, -0.6), 0.62, "black", r1=0.42, segs=18, bevel=0.01))
    s.add(tube("bigcollar", (-2.1, -3.3, -0.6), (-2.1, -3.6, -0.6), 0.68, 0.5, "brass", segs=18))
    s.add(bell("bigbell", (-2.1, -3.5, -0.6), (-2.1, -4.3, -0.6), 0.46, 0.62, segs=18))
    s.add(rivets("engrv", (-2.1, -0.2, 0.03), (-2.1, -3.0, 0.03), 6, r=0.04, axis="z"))
    s.add(block("pylon", (-2.1, -1.4, -0.12), (0.3, 1.8, 0.4), "rust", bevel=0.02))
    s.node("exhaust.0", (-2.1, -4.32, -0.6))
    s.add(cyl("smallengine", (1.05, -1.6, -0.25), (1.05, -3.7, -0.25), 0.36, "copper", segs=14, bevel=0.02))
    s.add(bell("smallbell", (1.05, -3.7, -0.25), (1.05, -4.1, -0.25), 0.28, 0.38, segs=14))
    s.add(block("smallmount", (0.75, -2.6, -0.25), (0.4, 1.2, 0.4), orange, bevel=0.02))
    s.node("exhaust.1", (1.05, -4.12, -0.25))
    s.add(block("tail", (-0.2, -3.7, 0.0), (1.2, 0.4, 1.0), "rust", bevel=0.03))
    # The claw rack on the nose: a crossbar, three hooked claws on rams, hazard paint.
    s.add(cyl("clawbar", (-0.95, 4.15, -0.35), (0.55, 4.15, -0.35), 0.1, "steel", segs=10, bevel=0))
    for i, x in enumerate((-0.75, -0.2, 0.35)):
        s.add(prism("claw", [(4.0, -0.2), (4.7, -0.25), (5.1, -0.6), (4.95, -0.95), (4.75, -0.65), (4.45, -0.5), (4.0, -0.52)], 0.12,
                    "hazard" if i != 1 else "steel", x=x, bevel=0.01))
        s.add(cyl("ram", (x, 3.3, 0.05), (x, 4.15, -0.3), 0.05, "steel", segs=8, bevel=0))
        s.add(cyl("ramsleeve", (x, 3.3, 0.05), (x, 3.7, -0.1), 0.08, "gunmetal", segs=8, bevel=0))
    s.add(block("rackplate", (-0.2, 3.95, -0.35), (1.7, 0.2, 0.4), "rust", bevel=0.02))
    # A strapped brass tank on the roof, pipework to the big engine, a stack, an antenna, a beacon.
    s.add(cyl("tank", (-0.55, -3.2, 1.15), (-0.55, -0.6, 1.15), 0.32, "brass", segs=14, bevel=0.04))
    for y in (-2.6, -1.3):
        s.add(block("strap", (-0.55, y, 1.15), (0.68, 0.08, 0.68), "leather", bevel=0.005))
    s.add(pipe("fuel", [(-0.55, -3.2, 1.15), (-0.55, -3.5, 0.9), (-1.4, -3.5, 0.9), (-2.1, -3.0, 0.0)], 0.05))
    s.add(pipe("fuel2", [(0.4, -1.2, 0.68), (0.9, -1.2, 0.68), (1.05, -1.8, 0.1)], 0.04, material="copper"))
    s.add(cyl("stack", (0.25, -2.9, 0.65), (0.25, -2.9, 1.5), 0.12, "rust", segs=10, bevel=0))
    s.add(cyl("stackcap", (0.25, -2.9, 1.48), (0.25, -2.9, 1.53), 0.17, "black", segs=10, bevel=0))
    s.add(cyl("antenna", (-0.9, 1.0, 0.68), (-0.9, 1.0, 1.7), 0.02, "steel", segs=6, bevel=0))
    nav_light(s, "light.2", (0.25, -1.0, 0.86), "lights_amber", r=0.09)
    # Skids: one under the core, one under the pod, a stub under the big engine.
    s.add(skid("skid", (-0.3, -0.4), 3.6, -REST, -0.65, bar=0.18))
    s.add(skid("podskid", (1.35, 1.0), 2.0, -REST, -0.4, bar=0.16))
    s.add(skid("engskid", (-2.1, -1.6), 1.4, -REST, -1.15, bar=0.14))
    s.node("heat", (-0.2, 4.4, -0.1))
    return s


SPEC = {
    "build": build,
    "size": (9.4, 8.0, 3.05),
    "rest": REST,
    "nodes": ["exhaust.0", "exhaust.1", "heat", "light.0", "light.1", "light.2"],
    "view": {"cam": (7.5, 9.5, 7.0), "look": (-0.6, -0.3, -0.1), "lens": 40},
    "top": {"cam": (-0.4, -0.01, 24.0), "look": (-0.4, 0, 0), "lens": 50},
}
