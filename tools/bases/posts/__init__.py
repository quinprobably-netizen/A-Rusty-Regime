"""The posts, one module each (`<id>.py`, with `build()` and `SPEC`), and the few parts they share
that the base kit does not have at a post's budget: cheap sandbags, smooth mounds (sand) and
faceted ones (rock, ice) cut off at the ground, tongues of fire, and turning a part in place. Built by `tools/bases/posts.py`."""

import kit
from kit import block, cut, cyl, sphere, wk
from mathutils import Vector

srgb = kit.srgb
wk.PALETTE.update({
    # Haven, the Deserters: warm timber, a bold orange tarp, painted ply.
    "timber": srgb("#8A5A2E", roughness=0.85, wear=0.4),
    "timber_dark": srgb("#4E321C", roughness=0.9, wear=0.3),
    "tarp": srgb("#E0662E", roughness=0.8, wear=0.25),
    "deserter_green": srgb("#3FCF6A", roughness=0.7, wear=0.2),
    "sandbag": srgb("#C9AE7C", roughness=0.95, wear=0.2),
    # Bastion, the Regime: slate rock, the black vault, red seam light.
    "rock": srgb("#3A3D42", roughness=0.95, wear=0.35),
    "vault": srgb("#0E0E10", metallic=0.4, roughness=0.35, wear=0.25, lighten=3.0),
    "seam": ((1.0, 0.04, 0.02), (1.0, 0.04, 0.02), 0.0, 0.3, 0.0, 8.0),
    "banner": srgb("#8E1010", roughness=0.8, wear=0.2),
    # Cinder, the Scrappers: the dune, a hazard sail.
    "dune": srgb("#D9955C", roughness=1.0, wear=0.2, lighten=1.1),
    "fire_light": ((1.0, 0.36, 0.06), (1.0, 0.36, 0.06), 0.0, 0.3, 0.0, 5.0),
    # Frost, the PMC: blue ice, white hab.
    "ice": srgb("#CFE0EE", roughness=0.4, wear=0.3, lighten=1.05),
    "pmc_blue": srgb("#2F6FD0", roughness=0.45, wear=0.3),
    "pmc_white": srgb("#E8ECEF", roughness=0.4, wear=0.35, lighten=0.9),
})


def bags(base, c, length, rows=2, axis="x", material="sandbag", bag=(0.56, 0.34, 0.2)):
    """A sandbag wall `length` long along `axis`, `rows` courses, every other course staggered.
    Chamfered rather than rounded: a post cannot afford the base kit's bevelled bags."""
    x, y, z = c
    n = max(1, round(length / bag[0]))
    step = length / n
    for r in range(rows):
        for i in range(n - (r % 2)):
            u = -length / 2 + (i + 0.5 + 0.5 * (r % 2)) * step
            s = (step * 0.98, bag[1], bag[2]) if axis == "x" else (bag[1], step * 0.98, bag[2])
            p = (x + u, y, z + bag[2] / 2 + r * bag[2] * 0.92) if axis == "x" else (x, y + u, z + bag[2] / 2 + r * bag[2] * 0.92)
            base.add(block("bag", p, s, material, bevel=0.06, segs=1))


def mound(base, name, c, s, material, floor=-0.3, segs=14, group="hull"):
    """A rounded heap (a squashed sphere at `c` with radii `s`) with everything under `floor` cut
    away, so it sinks into the ground without a buried belly."""
    o = sphere(name, (0, 0, 0), 1.0, material, segs=segs)
    o.scale = s
    o.location = c
    kit.bpy.context.view_layer.update()
    o.data.transform(o.matrix_world)
    o.matrix_world = kit.Matrix.Identity(4)
    span = max(s) * 4
    o = cut(o, block("under", (c[0], c[1], floor - span / 2), (span, span, span), material, bevel=0))
    wk.apply_modifiers(o)
    return base.add(o, group)


def rock(base, name, c, s, material="rock", seed=1, subdiv=2, jitter=0.2, floor=-0.3, flat=0.35):
    """A boulder or crag: an icosphere with radii `s` at `c`, every vertex pushed in or out at random
    (seeded) and the top flattened by `flat`, cut off at `floor`. Facets, not smooth: it reads as
    split stone under the toon bands."""
    import bmesh
    import random
    rnd = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
    for v in bm.verts:
        k = 1.0 + rnd.uniform(-jitter, jitter)
        z = v.co.z * k
        if z > 1.0 - flat:
            z = 1.0 - flat + (z - 1.0 + flat) * 0.3
        v.co = Vector((v.co.x * k * s[0] + c[0], v.co.y * k * s[1] + c[1], z * s[2] + c[2]))
    o = wk._obj(name, bm, material, 0.0)
    for p in o.data.polygons:
        p.use_smooth = False
    span = max(s) * 4
    o = cut(o, block("under", (c[0], c[1], floor - span / 2), (span, span, span), material, bevel=0))
    wk.apply_modifiers(o)
    return base.add(o)


def turned(obj, c, deg, axis="z"):
    """Rotate a part's mesh by `deg` about `axis` through `c`, in place."""
    kit.rotate(obj, c, axis, deg)
    return obj


def flames(base, c, r, material="fire_light", n=3):
    """Tongues of fire: `n` thin cones of different heights in a bed `r` across, lit."""
    x, y, z = c
    for i, (dx, dy, h) in enumerate(((0.0, 0.0, 0.55), (0.35, 0.2, 0.36), (-0.3, 0.25, 0.42), (0.1, -0.35, 0.3))[:n]):
        base.add(cyl("flame", (x + dx * r, y + dy * r, z), (x + dx * r, y + dy * r, z + h), r * 0.42, material, r1=0.01, segs=5, bevel=0), "lights")
