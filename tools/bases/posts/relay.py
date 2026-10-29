"""The Regime's relay on Bastion: a squat data fortress braced against 12.5 g. A black monolith
vault stands on a battered slate terrace between stepped buttresses, its seams glowing red, a
lit terminal in an alcove in its face. Cable trunks run from its back into the rock it is built
against; a short uplink spire with a red beacon tops it, red banners hang on the buttresses, and
two braziers burn either side of the steps."""

from basekit import Base, box, slope, stair
from kit import block, cut, cyl, pipe, sphere
from posts import flames, rock, turned

TZ = 0.6                    # the terrace's top
VC, VS = (0.0, 1.2), (4.0, 3.2, 4.6)   # the vault: centre (x, y), size
AW, AH, AD = 1.4, 2.4, 1.3  # the alcove: width, height, depth
S, G, R = "slate", "gold", "seam"


def seam(b, c, s):
    b.add(block("seam", c, s, R, bevel=0), "lights")


def build():
    b = Base("relay")
    # The rock behind, and a boulder; the terrace with battered sides and steps up the front.
    rock(b, "crag", (0.4, 6.4, -0.6), (5.4, 2.5, 6.0), seed=3, flat=0.25)
    rock(b, "crag", (-4.5, 4.5, -0.4), (1.9, 2.4, 3.2), seed=5, subdiv=1)
    rock(b, "crag", (4.6, 4.7, -0.4), (1.7, 2.2, 2.4), seed=8, subdiv=1)
    rock(b, "scree", (-5.3, 1.2, -0.2), (0.8, 0.7, 0.6), seed=11, subdiv=1)
    b.add(block("terrace", (0, 0.75, TZ / 2), (10.0, 7.5, TZ), "rock", bevel=0.04, segs=1, taper=(0.97, 0.96)))
    b.add(block("kerb", (0, -2.95, TZ + 0.06), (10.0 * 0.97 - 0.2, 0.3, 0.12), "bone", bevel=0))
    stair(b, (0, -4.2, 0), 3.0, 1.2, TZ, 3, material=S, stringers=False)
    vx, vy = VC
    sx, sy, sz = VS
    front = vy - sy / 2
    # The vault: a black slab with an alcove cut into its face.
    vault = block("vault", (vx, vy, TZ + sz / 2), VS, "vault", bevel=0.02, segs=1)
    vault = cut(vault, block("alcove", (vx, front + AD / 2 - 0.1, TZ + AH / 2), (AW, AD + 0.2, AH), "vault", bevel=0))
    b.add(vault)
    b.add(block("cornice", (vx, vy, TZ + sz + 0.1), (sx + 0.4, sy + 0.4, 0.2), G, bevel=0))
    b.add(block("roof", (vx, vy, TZ + sz + 0.3), (sx - 0.4, sy - 0.4, 0.2), "vault", bevel=0))
    # Red seams: a frame round the alcove, verticals and a course line on every face.
    e = 0.02
    seam(b, (vx, front - e, TZ + AH + 0.08), (AW + 0.32, 0.04, 0.08))
    for k in (-1, 1):
        seam(b, (vx + k * (AW / 2 + 0.12), front - e, TZ + AH / 2 + 0.04), (0.08, 0.04, AH + 0.08))
    for y, f in ((front - e, 1), (vy + sy / 2 + e, -1)):
        for x in (-1.45, 1.45):
            seam(b, (vx + x, y, TZ + sz / 2), (0.07, 0.04, sz - 0.3))
        seam(b, (vx, y, TZ + 3.4), (sx - 0.3, 0.04, 0.07))
    for x in (vx - sx / 2 - e, vx + sx / 2 + e):
        for y in (-0.8, 0.8):
            seam(b, (x, vy + y, TZ + sz / 2), (0.04, 0.07, sz - 0.3))
        seam(b, (x, vy, TZ + 3.4), (0.04, sy - 0.3, 0.07))
    # The terminal in the alcove.
    back = front + AD - 0.1
    b.add(block("console", (vx, back - 0.25, TZ + 0.5), (1.0, 0.45, 1.0), "gunmetal", bevel=0.02, segs=1))
    b.add(block("screen", (vx, back - 0.05, TZ + 1.55), (0.9, 0.04, 0.6), "red_light", bevel=0), "lights")
    b.add(block("keys", (vx, back - 0.36, TZ + 1.02), (0.8, 0.3, 0.04), "red_glass", bevel=0), "lights")
    b.node("sound.hum.0", (vx, back - 0.3, TZ + 1.4))
    # Stepped buttresses either side, red banners on their faces.
    for k in (-1, 1):
        x = vx + k * (sx / 2 + 0.7)
        z0 = TZ
        for w, d, h in ((1.4, 3.6, 2.8), (1.0, 3.0, 1.4), (0.6, 2.2, 0.9)):
            b.add(block("buttress", (x - k * (1.4 - w) / 2, vy, z0 + h / 2), (w, d, h), S, bevel=0.03, segs=1))
            b.add(block("buttresscap", (x - k * (1.4 - w) / 2, vy, z0 + h + 0.03), (w + 0.1, d + 0.1, 0.06), "bone", bevel=0))
            z0 += h
        bx, by = x, vy - 1.8 - 0.03
        b.add(block("banner", (bx, by, TZ + 1.5), (0.9, 0.03, 2.4), "banner", bevel=0))
        b.add(block("bannerbar", (bx, by - 0.02, TZ + 2.75), (1.1, 0.05, 0.08), G, bevel=0))
        b.add(block("bannerhem", (bx, by - 0.02, TZ + 0.36), (0.9, 0.04, 0.12), G, bevel=0))
        b.add(block("sigil", (bx, by - 0.03, TZ + 1.8), (0.42, 0.02, 0.42), G, bevel=0))
        turned(b.parts[-1][0], (bx, by - 0.03, TZ + 1.8), 45, "y")
    # The uplink spire: a stepped plinth, a tapering mast with gold collars, a red beacon.
    top = TZ + sz + 0.4
    b.add(block("spireplinth", (vx, vy, top + 0.2), (1.2, 1.2, 0.4), S, bevel=0))
    b.add(cyl("spire", (vx, vy, top + 0.4), (vx, vy, top + 2.8), 0.3, "gunmetal", r1=0.06, segs=6, bevel=0))
    for z, r in ((top + 0.9, 0.27), (top + 1.8, 0.18)):
        b.add(cyl("collar", (vx, vy, z), (vx, vy, z + 0.12), r, G, segs=6, bevel=0))
    for k in (-1, 1):
        b.add(cyl("prong", (vx + k * 0.4, vy, top + 0.4), (vx + k * 0.55, vy, top + 1.7), 0.04, G, segs=4, bevel=0))
    b.add(sphere("beacon", (vx, vy, top + 2.9), 0.13, "red_light", segs=8), "lights")
    b.node("blink.0", (vx, vy, top + 2.9))
    # Cable trunks from the vault's back down into the rock, lit collars where they leave it.
    yb = vy + sy / 2
    for i, x in enumerate((-1.1, 0.0, 1.1)):
        z = TZ + 1.4 + 0.5 * i
        b.add(pipe("trunk", [(x, yb - 0.1, z), (x, yb + 0.7, z), (x * 1.3, yb + 1.6, TZ + 0.4), (x * 1.6, yb + 2.6, 0.3)], 0.17, "rubber", segs=8))
        b.add(cyl("collar", (x, yb + 0.05, z), (x, yb + 0.25, z), 0.24, "red_light", segs=8, bevel=0), "lights")
    for x in (-0.9, 0.9):  # two more over the roof's back edge, arching into the crag
        b.add(pipe("trunk", [(x, yb - 0.6, TZ + sz + 0.35), (x, yb + 0.2, TZ + sz + 0.6), (x * 1.4, yb + 1.6, TZ + sz + 0.2), (x * 1.6, yb + 3.0, TZ + 3.0)], 0.15, "rubber", segs=8))
        b.add(cyl("collar", (x, yb - 0.75, TZ + sz + 0.35), (x, yb - 0.4, TZ + sz + 0.35), 0.21, "red_light", segs=8, bevel=0), "lights")
    b.add(pipe("trunk", [(-sx / 2 - 1.3, vy + 0.6, TZ + 0.2), (-4.0, vy + 0.6, TZ + 0.2), (-4.4, vy + 1.6, 0.4)], 0.14, "rubber", segs=8))
    b.add(pipe("trunk", [(sx / 2 + 1.3, vy + 1.2, TZ + 0.2), (4.2, vy + 1.6, 0.3), (4.6, vy + 2.6, 0.2)], 0.14, "rubber", segs=8))
    # Two braziers either side of the steps.
    for i, k in enumerate((-1, 1)):
        x, y = k * 2.3, -3.9
        b.add(block("pedestal", (x, y, 0.45), (0.6, 0.6, 0.9), S, bevel=0.02, segs=1))
        b.add(block("pedestalcap", (x, y, 0.93), (0.75, 0.75, 0.06), "bone", bevel=0))
        b.add(cyl("bowl", (x, y, 0.96), (x, y, 1.36), 0.24, G, r1=0.5, segs=8, bevel=0))
        b.add(cyl("coals", (x, y, 1.3), (x, y, 1.34), 0.44, "fire_light", segs=8, bevel=0), "lights")
        flames(b, (x, y, 1.32), 0.24)
        b.node(f"fire.{i}", (x, y, 1.6))
    b.node("smoke.0", (-2.3, -3.9, 2.3))
    b.node("smoke.1", (2.3, -3.9, 2.3))
    b.node("sound.fire.0", (2.3, -3.9, 1.4))
    return b


def _vault_boxes():
    vx, vy = VC
    sx, sy, sz = VS
    front = vy - sy / 2
    side = (sx - AW) / 2
    return [
        box("vault west", (vx - sx / 2 + side / 2, vy, TZ + sz / 2), (side, sy, sz)),
        box("vault east", (vx + sx / 2 - side / 2, vy, TZ + sz / 2), (side, sy, sz)),
        box("vault back", (vx, front + AD + (sy - AD) / 2, TZ + sz / 2), (AW, sy - AD, sz)),
        box("vault lintel", (vx, front + AD / 2, TZ + AH + (sz - AH) / 2), (AW, AD, sz - AH)),
        box("console", (vx, front + AD - 0.35, TZ + 0.5), (1.0, 0.45, 1.0)),
    ]


SPEC = {
    "build": build,
    "name": "Regime relay",
    "color": (1.0, 0.2, 0.2),
    "faction": "regime",
    "body": "bastion",
    "footprint": (12.0, 11.0),
    "footprint_at": (0.0, 1.0),
    "door": (0.0, -1.3, 1.6),
    "size": (13.7, 12.5, 8.9),
    "depth": 0.3,
    "nodes": ["blink.0", "fire.0", "fire.1", "smoke.0", "smoke.1", "sound.hum.0", "sound.fire.0"],
    "boxes": [
        box("terrace", (0, 0.75, TZ / 2), (10.0, 7.5, TZ)),
        slope((0, -4.2, 0), 3.0, 1.2, TZ, 1),
        *_vault_boxes(),
        *[box("buttress", (k * (VS[0] / 2 + 0.7), VC[1], TZ + 1.4), (1.4, 3.6, 2.8)) for k in (-1, 1)],
        box("crag", (0.4, 6.9, 1.6), (8.0, 3.6, 3.2)),
        box("crag", (-4.5, 4.6, 1.0), (2.6, 3.0, 2.0)),
        box("crag", (4.6, 4.8, 0.8), (2.4, 2.8, 1.6)),
        *[box("brazier", (k * 2.3, -3.9, 0.7), (0.75, 0.75, 1.4)) for k in (-1, 1)],
    ],
    "crew": [
        ("zealot", (-1.4, -1.4, TZ), 0.0, []),
        ("acolyte", (-4.2, -2.2, TZ), 0.0, [(4.2, -2.2, TZ), (4.2, -1.0, TZ), (-4.2, -1.0, TZ)]),
    ],
    "view": {"cam": (-22.0, -21.0, 9.0), "look": (0, 1.5, 2.5), "lens": 40},
    "near": {"cam": (3.5, -9.0, 1.7), "look": (0, 0.5, 2.0), "lens": 26},
}
