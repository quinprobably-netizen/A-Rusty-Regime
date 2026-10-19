"""Procedural surfaces for the realistic characters, and the bake that turns them into game textures.

Every material kind (the part after the character id in a material's name, as `kit.mat` makes them)
gets a shader network built from Blender nodes: a fabric weave, leather grain, skin pores, polymer
stipple, brushed metal... plus the shared wear and dirt (edge wear on hard parts, cavity dirt, dust on
the lower legs, stitching along garment seams). `bake` evaluates those networks, on each part itself or
on its high-detail version (selected-to-active), into one 2048 atlas per character:

    color   base colour (sRGB), cavity dirt and wear included
    orm     ambient occlusion (R), roughness (G), metalness (B)  (glTF occlusion + metallicRoughness)
    normal  tangent-space normal map: the high mesh's geometry (cloth folds, the body sculpt) and the
            procedural micro-detail together

`final` then gives every material the plain PBR graph the glTF exporter understands.

A kind can name its surface explicitly as "<surface>.<tint>" (say "knit.primary": rib knit, but still a
`.primary` material the game tints); otherwise RECIPE maps the kind to a surface. Patterns are laid
out in the "fabric" UV layer, which `layout` makes in metres from each part's own UVs, so a weave has
the same real size on every part.

Mesh attributes the networks read, when a part has them (all optional):
    seam, seam_u   distance to the nearest garment seam or hem (m) and length along it (m): stitching
    face           (stubble, lips, brows, socket) masks on the skin, from `real`
    eye_r, eye_a   angle from the gaze axis (0..1 = 0..90 degrees) and around it, on eyeballs
"""

import math
import os
import time

import bpy
import bmesh
import numpy as np
from mathutils import Vector

import kit

hs = kit.hs
TEX = 2048
ATLAS = "UVMap"
FABRIC = "fabric"

# kind -> surface recipe (kinds not listed fall back by name, then to "polymer").
RECIPE = {
    "primary": "ripstop", "secondary": "twill", "accent": "cordura",
    "pmc_navy": "cordura", "pmc_velcro": "velcro", "pmc_plate": "polymer", "pmc_navy_hard": "polymer",
    "black": "polymer", "grey": "polymer", "white": "print", "cream": "print", "hazard": "polymer",
    "rubber": "rubber", "gunmetal": "metal", "steel": "metal", "bright": "metal", "brass": "metal",
    "skin": "skin", "skin_pale": "skin", "skin_dark": "skin", "lips": "skin",
    "eye": "eye", "hair": "hair", "glass": "glass", "lens": "glass",
    "leather": "leather", "glove": "glove", "boot": "leather", "webbing": "webbing", "canvas": "canvas",
    "olive": "cordura", "tan": "cordura", "ink": "print", "corp": "polymer",
}
# Soft goods take fabric wear (fading, fraying, stitches); the rest take hard-surface edge wear.
SOFT = {"ripstop", "twill", "cordura", "velcro", "webbing", "canvas", "knit", "print", "glove", "leather"}


def kind_of(m):
    """(surface recipe, palette kind) for a material."""
    full = m.get("surface_kind") or m.get("kind") or m.name.split(".", 1)[-1]
    if "." in full:
        surf, tint = full.split(".", 1)
        return surf, tint
    return RECIPE.get(full, "polymer"), full


# ------------------------------------------------------------------------------------------ nodes

class G:
    """A tiny builder for shader node graphs: every helper takes sockets or plain numbers and returns
    an output socket."""

    def __init__(self, nt):
        self.nt = nt
        self._cache = {}

    def node(self, kind, **props):
        n = self.nt.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def link(self, value, inp):
        if isinstance(value, bpy.types.NodeSocket):
            self.nt.links.new(value, inp)
        elif value is not None:
            inp.default_value = value

    def math(self, op, a, b=None, c=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self.link(v, n.inputs[i])
        return n.outputs[0]

    def add(self, a, b):
        return self.math("ADD", a, b)

    def mul(self, a, b, clamp=False):
        return self.math("MULTIPLY", a, b, clamp=clamp)

    def sub(self, a, b):
        return self.math("SUBTRACT", a, b)

    def vec(self, op, a, b=None, scale=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self.link(a, n.inputs[0])
        if b is not None:
            self.link(b, n.inputs[1])
        if scale is not None:
            self.link(scale, n.inputs[3])
        return n.outputs["Value" if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else "Vector"]

    def xyz(self, v):
        n = self.node("ShaderNodeSeparateXYZ")
        self.link(v, n.inputs[0])
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def combine(self, x, y, z):
        n = self.node("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self.link(v, n.inputs[i])
        return n.outputs[0]

    def rgb(self, r, g, b):
        n = self.node("ShaderNodeCombineColor")
        for i, v in enumerate((r, g, b)):
            self.link(v, n.inputs[i])
        return n.outputs[0]

    def remap(self, v, a, b, lo=0.0, hi=1.0, smooth=True):
        """v mapped from [a, b] to [lo, hi], clamped (smoothstep by default)."""
        n = self.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP" if smooth else "LINEAR", clamp=True)
        self.link(v, n.inputs[0])
        for i, x in enumerate((a, b, lo, hi)):
            n.inputs[1 + i].default_value = x
        return n.outputs[0]

    def mix(self, fac, a, b, blend="MIX"):
        """Colour mix (a -> b by fac)."""
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_factor=True)
        self.link(fac, n.inputs[0])
        self.link(_rgba(a), n.inputs[6])
        self.link(_rgba(b), n.inputs[7])
        return n.outputs[2]

    def lerp(self, fac, a, b):
        """Float mix (a -> b by fac)."""
        n = self.node("ShaderNodeMix", data_type="FLOAT", clamp_factor=True)
        self.link(fac, n.inputs[0])
        self.link(a, n.inputs[2])
        self.link(b, n.inputs[3])
        return n.outputs[0]

    def noise(self, v, scale, detail=2.0, rough=0.5, distort=0.0, color=False):
        n = self.node("ShaderNodeTexNoise")
        self.link(v, n.inputs["Vector"])
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        n.inputs["Distortion"].default_value = distort
        return n.outputs[1 if color else 0]

    def voronoi(self, v, scale, feature="F1", out="Distance", rand=1.0):
        n = self.node("ShaderNodeTexVoronoi", feature=feature)
        self.link(v, n.inputs["Vector"])
        n.inputs["Scale"].default_value = scale
        n.inputs["Randomness"].default_value = rand
        return n.outputs[out]

    def lines(self, coord, pitch, width):
        """1 on lines every `pitch` along a coordinate (m), falling to 0 `width` away."""
        t = self.math("FRACT", self.math("DIVIDE", coord, pitch))
        d = self.mul(self.math("MINIMUM", t, self.sub(1.0, t)), pitch)
        return self.remap(d, width, 0.0)

    def uv(self, name=FABRIC):
        if name not in self._cache:
            self._cache[name] = self.node("ShaderNodeUVMap", uv_map=name).outputs[0]
        return self._cache[name]

    def geo(self, out):
        if "geo" not in self._cache:
            self._cache["geo"] = self.node("ShaderNodeNewGeometry")
        return self._cache["geo"].outputs[out]

    def attr(self, name, out="Factor"):
        key = "attr." + name
        if key not in self._cache:
            self._cache[key] = self.node("ShaderNodeAttribute", attribute_name=name, attribute_type="GEOMETRY")
        return self._cache[key].outputs[out]

    def ao(self, dist, samples=3):
        n = self.node("ShaderNodeAmbientOcclusion", samples=samples, only_local=False)
        n.inputs["Distance"].default_value = dist
        return n.outputs["AO"]

    def edge(self, radius, lo=0.997, hi=0.94):
        """0 on flat faces, rising toward 1 along convex and concave edges within `radius`."""
        bev = self.node("ShaderNodeBevel", samples=4)
        bev.inputs["Radius"].default_value = radius
        d = self.vec("DOT_PRODUCT", bev.outputs[0], self.geo("Normal"))
        return self.remap(d, lo, hi)


def _rgba(c):
    if isinstance(c, bpy.types.NodeSocket):
        return c
    c = tuple(c)
    return c + (1.0,) if len(c) == 3 else c


def _scale(c, k):
    return tuple(min(1.0, x * k) for x in c)


# ------------------------------------------------------------------------------------- recipes
# Each takes (g, palette entry) and returns a dict: color, rough, metal, height (0..1 sockets or
# numbers) and bump (the height's depth in metres). Sizes are real: a 5 mm ripstop grid is 5 mm.

def _fibres(g, uv, k=1.0):
    """Fine fibre noise for any fabric (mostly below a texel: it breaks up flat colour)."""
    return g.noise(uv, 900.0 / k, detail=3, rough=0.6)


def ripstop(g, pal):
    base = pal[0]
    uv = g.uv()
    u, v, _ = g.xyz(uv)
    grid = g.math("MAXIMUM", g.lines(u, 0.0055, 0.0006), g.lines(v, 0.0055, 0.0006))
    weave = g.mul(g.add(g.math("SINE", g.mul(u, 2 * math.pi / 0.0011)), g.math("SINE", g.mul(v, 2 * math.pi / 0.0011))), 0.25)
    fib = _fibres(g, uv)
    h = g.add(g.add(g.mul(grid, 0.45), g.mul(weave, 0.1)), g.mul(fib, 0.45))
    shade = g.remap(fib, 0.3, 0.7, 0.96, 1.03, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    col = g.mix(g.mul(grid, 0.2), col, _scale(base, 1.04))
    return dict(color=col, rough=g.lerp(grid, 0.80, 0.74), metal=0.0, height=h, bump=0.00025)


def twill(g, pal):
    base = pal[0]
    uv = g.uv()
    u, v, _ = g.xyz(uv)
    diag = g.mul(g.add(u, g.mul(v, 0.75)), 0.8)
    rib = g.lines(diag, 0.0024, 0.0008)
    slub = g.noise(g.combine(g.mul(u, 1.0), g.mul(v, 0.08), 0.0), 140.0, detail=2)
    fib = _fibres(g, uv)
    h = g.add(g.mul(rib, 0.6), g.mul(fib, 0.4))
    shade = g.remap(g.add(g.mul(slub, 0.6), g.mul(fib, 0.4)), 0.3, 0.7, 0.94, 1.04, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    return dict(color=col, rough=0.84, metal=0.0, height=h, bump=0.0005)


def cordura(g, pal):
    """Heavy nylon (1000D Cordura): a coarse basket weave with a faint sheen."""
    base = pal[0]
    uv = g.uv()
    u, v, _ = g.xyz(uv)
    p = 0.0021
    a = g.math("SINE", g.mul(u, 2 * math.pi / p))
    b = g.math("SINE", g.mul(v, 2 * math.pi / p))
    basket = g.add(0.5, g.mul(g.mul(a, b), 0.5))
    fib = _fibres(g, uv, 1.4)
    mottle = g.noise(uv, 60.0, detail=3)
    h = g.add(g.mul(basket, 0.6), g.mul(fib, 0.4))
    shade = g.remap(g.add(g.mul(mottle, 0.5), g.mul(fib, 0.5)), 0.3, 0.7, 0.93, 1.05, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    return dict(color=col, rough=g.lerp(basket, 0.62, 0.74), metal=0.0, height=h, bump=0.00045)


def velcro(g, pal):
    base = pal[0]
    uv = g.uv()
    loops = g.voronoi(uv, 700.0, "F1")
    fuzz = g.noise(uv, 1400.0, detail=4, rough=0.7)
    h = g.add(g.mul(g.remap(loops, 0.0, 0.5, 1.0, 0.0), 0.5), g.mul(fuzz, 0.5))
    shade = g.remap(fuzz, 0.3, 0.7, 0.85, 1.12, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    return dict(color=col, rough=0.96, metal=0.0, height=h, bump=0.0006)


def webbing(g, pal):
    base = pal[0]
    uv = g.uv()
    u, v, _ = g.xyz(uv)
    rib = g.lines(u, 0.0018, 0.0006)
    fib = _fibres(g, uv)
    h = g.add(g.mul(rib, 0.6), g.mul(fib, 0.4))
    shade = g.remap(fib, 0.3, 0.7, 0.93, 1.06, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    return dict(color=col, rough=0.78, metal=0.0, height=h, bump=0.0004)


def canvas(g, pal):
    base = pal[0]
    uv = g.uv()
    u, v, _ = g.xyz(uv)
    p = 0.0016
    w = g.add(g.math("SINE", g.mul(u, 2 * math.pi / p)), g.math("SINE", g.mul(v, 2 * math.pi / p)))
    slub = g.noise(uv, 90.0, detail=3)
    h = g.add(g.mul(w, 0.25), g.add(0.5, g.mul(slub, 0.3)))
    shade = g.remap(slub, 0.3, 0.7, 0.92, 1.06, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    return dict(color=col, rough=0.9, metal=0.0, height=h, bump=0.0005)


def knit(g, pal):
    """Rib knit (collars, cuffs): raised wales 2.5 mm apart."""
    base = pal[0]
    uv = g.uv()
    u, v, _ = g.xyz(uv)
    rib = g.lines(u, 0.0025, 0.0009)
    loops = g.lines(v, 0.0012, 0.0004)
    fib = _fibres(g, uv)
    h = g.add(g.mul(rib, 0.65), g.mul(g.mul(loops, rib), 0.15))
    h = g.add(h, g.mul(fib, 0.2))
    col = g.mix(g.mul(g.sub(1.0, rib), 0.5), base, _scale(base, 0.9))
    return dict(color=col, rough=0.9, metal=0.0, height=h, bump=0.0007)


def print_(g, pal):
    """Patch base: a woven/embroidered label."""
    base = pal[0]
    uv = g.uv()
    u, v, _ = g.xyz(uv)
    rows = g.lines(v, 0.0009, 0.0003)
    fib = _fibres(g, uv, 0.7)
    h = g.add(g.mul(rows, 0.5), g.mul(fib, 0.5))
    shade = g.remap(fib, 0.3, 0.7, 0.95, 1.03, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    return dict(color=col, rough=0.7, metal=0.0, height=h, bump=0.0003)


def leather(g, pal, grain=1.0):
    base = pal[0]
    pos = g.geo("Position")
    pebble = g.voronoi(pos, 520.0 / grain, "F1")
    creases = g.noise(pos, 45.0, detail=4, rough=0.6, distort=0.4)
    crease = g.remap(g.math("ABSOLUTE", g.sub(creases, 0.5)), 0.0, 0.04, 1.0, 0.0)
    h = g.sub(g.add(g.mul(g.remap(pebble, 0.0, 0.6, 1.0, 0.0), 0.6), 0.3), g.mul(crease, 0.35))
    shade = g.remap(g.noise(pos, 18.0, detail=3), 0.3, 0.7, 0.9, 1.08, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    col = g.mix(g.mul(crease, 0.5), col, _scale(base, 0.75))
    return dict(color=col, rough=g.lerp(crease, 0.55, 0.7), metal=0.0, height=h, bump=0.0004)


def glove(g, pal):
    """Synthetic-leather palm and fingers with a stretch-nylon feel: fine grain, light creases."""
    r = leather(g, pal, grain=0.7)
    r["rough"] = g.lerp(g.noise(g.geo("Position"), 30.0), 0.5, 0.68)
    return r


def rubber(g, pal):
    base = pal[0]
    pos = g.geo("Position")
    n = g.noise(pos, 600.0, detail=2)
    shade = g.remap(g.noise(pos, 25.0, detail=3), 0.3, 0.7, 0.9, 1.1, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    return dict(color=col, rough=0.78, metal=0.0, height=n, bump=0.0002)


def polymer(g, pal):
    """Moulded plastic: a fine stipple and faint flow marks."""
    base = pal[0]
    pos = g.geo("Position")
    stip = g.voronoi(pos, 1500.0, "F1")
    flow = g.noise(pos, 40.0, detail=2)
    h = g.add(g.mul(g.remap(stip, 0.0, 0.5, 1.0, 0.0), 0.7), g.mul(flow, 0.3))
    shade = g.remap(flow, 0.3, 0.7, 0.96, 1.04, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    return dict(color=col, rough=g.lerp(stip, pal[3] - 0.05, pal[3] + 0.08), metal=pal[2], height=h, bump=0.00015)


def metal(g, pal):
    base = pal[0]
    pos = g.geo("Position")
    x, y, z = g.xyz(pos)
    brush = g.noise(g.combine(g.mul(x, 0.05), y, z), 900.0, detail=2)
    blot = g.noise(pos, 30.0, detail=3)
    shade = g.remap(blot, 0.3, 0.7, 0.85, 1.12, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    return dict(color=col, rough=g.lerp(brush, pal[3] - 0.08, pal[3] + 0.08), metal=pal[2], height=brush, bump=0.00008)


def glass(g, pal):
    return dict(color=pal[0], rough=0.06, metal=0.3, height=0.0, bump=0.0)


def hair(g, pal):
    """Short hair: strands running down the head; the skin shows through at the hairline."""
    base = pal[0]
    pos = g.geo("Position")
    x, y, z = g.xyz(pos)
    strands = g.noise(g.combine(g.mul(x, 1.0), g.mul(y, 1.0), g.mul(z, 0.12)), 1100.0, detail=2, rough=0.5)
    clumps = g.noise(g.combine(x, y, g.mul(z, 0.3)), 160.0, detail=2)
    shade = g.remap(g.add(g.mul(strands, 0.7), g.mul(clumps, 0.3)), 0.25, 0.75, 0.6, 1.5, smooth=False)
    col = g.mix(1.0, base, g.rgb(shade, shade, shade), "MULTIPLY")
    # Cropped hair: the scalp shows through everywhere a little, and more toward the hairline (the
    # shell's edge), where the hairs thin out.
    edge = g.remap(g.attr("seam"), 0.0, 0.008)
    skin_c = _scale(hs.PALETTE["skin"][0], 0.8)
    sparse = g.remap(g.sub(strands, g.mul(g.sub(1.0, edge), 0.45)), 0.3, 0.5)
    col = g.mix(g.add(0.12, g.mul(g.sub(1.0, sparse), 0.85)), col, skin_c)
    return dict(color=col, rough=g.lerp(strands, 0.75, 0.55), metal=0.0, height=strands, bump=0.0006)


def skin(g, pal):
    """Skin: colour variation (warmer cheeks, ears and knuckles, cooler shaved jaw), pores, fine
    wrinkles; stubble, lips, brows and eye-socket shading come from the `face` mask."""
    base = pal[0]
    pos = g.geo("Position")
    face = g.attr("face", "Color")
    fr, fg, fb = g.xyz(face)                     # stubble, lips, brows
    sock = g.attr("face", "Alpha")               # eye socket shading
    pores = g.voronoi(pos, 950.0, "F1")
    pore = g.remap(pores, 0.0, 0.22, 1.0, 0.0)
    fine = g.noise(pos, 260.0, detail=4, rough=0.65)
    blotch = g.noise(pos, 22.0, detail=3)
    red = g.remap(g.noise(pos, 9.0, detail=2), 0.4, 0.7)
    col = g.mix(1.0, base, g.rgb(g.remap(fine, 0.3, 0.7, 0.94, 1.05, smooth=False), g.remap(fine, 0.3, 0.7, 0.95, 1.04, smooth=False), 1.0), "MULTIPLY")
    col = g.mix(g.mul(red, 0.35), col, (base[0] * 1.08, base[1] * 0.86, base[2] * 0.84))
    col = g.mix(g.mul(g.remap(blotch, 0.45, 0.75), 0.25), col, (base[0] * 0.92, base[1] * 0.85, base[2] * 0.8))
    col = g.mix(g.mul(pore, 0.25), col, _scale(base, 0.78))
    # Stubble: a blue-grey shadow and dark specks of cut hair.
    specks = g.remap(g.voronoi(pos, 2200.0, "F1"), 0.12, 0.0)
    col = g.mix(g.mul(fr, 0.3), col, (base[0] * 0.66, base[1] * 0.64, base[2] * 0.66))
    col = g.mix(g.mul(g.mul(fr, specks), 0.5), col, (0.05, 0.04, 0.035))
    # Lips: redder, a little darker; brows: dark strokes along the brow line.
    col = g.mix(g.mul(fg, 0.85), col, (base[0] * 0.88, base[1] * 0.56, base[2] * 0.55))
    x, y, z = g.xyz(pos)
    brow = g.noise(g.combine(g.mul(x, 0.18), y, z), 2600.0, detail=1)
    brow_ink = g.mul(fb, g.remap(brow, 0.42, 0.58))
    col = g.mix(g.mul(brow_ink, 0.95), col, (0.035, 0.026, 0.02))
    col = g.mix(g.mul(sock, 0.4), col, (base[0] * 0.7, base[1] * 0.58, base[2] * 0.58))
    h = g.add(g.mul(g.sub(1.0, pore), 0.55), g.mul(fine, 0.45))
    h = g.add(h, g.mul(brow_ink, 0.2))
    rough = g.lerp(fg, g.lerp(pore, 0.52, 0.62), 0.38)
    rough = g.lerp(fr, rough, 0.62)
    return dict(color=col, rough=rough, metal=0.0, height=h, bump=0.00025)


def eye(g, pal):
    """Eyeball: wet sclera with faint veins at the edges, a fibrous iris, a dark pupil."""
    r = g.attr("eye_r")      # 0 at the pupil centre, 1 at 90 degrees from it
    a = g.attr("eye_a")      # 0..1 around the gaze axis
    pos = g.geo("Position")
    sclera = (0.78, 0.74, 0.70)
    veins = g.remap(g.noise(pos, 900.0, detail=3, distort=0.6), 0.62, 0.7)
    sc = g.mix(g.mul(g.mul(veins, g.remap(r, 0.4, 0.9)), 0.6), sclera, (0.7, 0.32, 0.28))
    sc = g.mix(g.remap(r, 0.55, 1.0), sc, (0.62, 0.5, 0.46))
    fib = g.noise(g.combine(g.mul(a, 60.0), g.mul(r, 8.0), 0.0), 3.0, detail=3)
    iris_col = g.mix(g.remap(fib, 0.3, 0.7), (0.07, 0.045, 0.025), (0.22, 0.14, 0.07))
    iris_col = g.mix(g.remap(r, 0.30, 0.355), iris_col, (0.02, 0.015, 0.012))      # limbal ring
    col = g.mix(g.remap(r, 0.355, 0.375), iris_col, sc)
    col = g.mix(g.remap(r, 0.13, 0.11), col, (0.006, 0.006, 0.006))               # pupil
    return dict(color=col, rough=0.05, metal=0.0, height=0.0, bump=0.0)


RECIPES = {"ripstop": ripstop, "twill": twill, "cordura": cordura, "velcro": velcro, "webbing": webbing,
           "canvas": canvas, "knit": knit, "print": print_, "leather": leather, "glove": glove,
           "rubber": rubber, "polymer": polymer, "metal": metal, "glass": glass, "hair": hair,
           "skin": skin, "eye": eye}


# ------------------------------------------------------------------------------- shared wear

def _wear(g, surf, pal, r):
    """Wear and dirt over a recipe: stitching and frayed hems on soft goods, edge wear on hard ones,
    cavity dirt everywhere, dust low on the legs. Returns (color, rough, metal, height, ao)."""
    base, worn, metal_, rough_, amount, _ = pal
    col, rough, metal, h = r["color"], r["rough"], r["metal"], r["height"]
    pos = g.geo("Position")
    ao = g.ao(0.02)
    if surf in ("eye", "glass"):
        return col, rough, metal, h, g.remap(ao, 0.0, 1.0, 0.6, 1.0, smooth=False)
    big = g.noise(pos, 7.0, detail=3)
    grime = g.remap(big, 0.3, 0.75, 0.94, 1.03, smooth=False) if surf in SOFT else g.remap(big, 0.3, 0.75, 0.9, 1.04, smooth=False)
    col = g.mix(1.0, col, g.rgb(grime, grime, grime), "MULTIPLY")
    if surf in SOFT:
        # Stitching: two rows along every seam and hem, dashed.
        seam = g.attr("seam")
        su = g.attr("seam_u")
        row = g.math("MAXIMUM", g.remap(g.math("ABSOLUTE", g.sub(seam, 0.0035)), 0.0007, 0.0),
                     g.remap(g.math("ABSOLUTE", g.sub(seam, 0.0085)), 0.0007, 0.0))
        dash = g.remap(g.math("FRACT", g.math("DIVIDE", su, 0.0032)), 0.72, 0.62)
        stitch = g.mul(row, dash)
        col = g.mix(g.mul(stitch, 0.7), col, _scale(base, 1.18))
        rough = g.lerp(stitch, rough, 0.6)
        h = g.add(h, g.mul(stitch, 0.9))
        # The fold of a hem: a raised roll right at the edge, frayed and faded.
        hem = g.remap(seam, 0.0025, 0.0)
        h = g.add(h, g.mul(hem, 0.6))
        fray = g.mul(hem, g.remap(g.noise(pos, 400.0), 0.4, 0.6))
        col = g.mix(g.mul(fray, amount), col, worn)
        # Exposed folds fade and scuff; hollows collect dirt.
        expo = g.remap(ao, 0.92, 1.0)
        col = g.mix(g.mul(g.mul(expo, g.remap(big, 0.5, 0.8)), 0.12 * amount), col, worn)
    else:
        # Edge wear: chips along convex edges, broken up by noise.
        edge = g.edge(0.0016)
        chip = g.mul(edge, g.remap(g.noise(pos, 260.0, detail=6), 0.48, 0.62))
        chip = g.mul(chip, g.remap(ao, 0.8, 0.95), clamp=True)  # concave corners do not chip
        wear = g.mul(chip, amount, clamp=True)
        col = g.mix(wear, col, worn)
        # Worn metal polishes; scuffed plastic and paint go rougher.
        rough = g.lerp(wear, rough, max(0.15, rough_ - 0.2) if metal_ > 0.5 else min(1.0, rough_ + 0.1))
        h = g.sub(h, g.mul(wear, 0.4))
    dirt = g.remap(ao, 0.35, 0.95, 0.55, 1.0)
    col = g.mix(1.0, col, g.rgb(dirt, dirt, g.mul(dirt, 0.97)), "MULTIPLY")
    if surf not in ("skin", "hair"):
        # Dust: the lower legs and boots pick up a dry grey-brown film.
        _, _, z = g.xyz(pos)
        dust = g.mul(g.remap(z, 0.55, 0.04), g.remap(g.noise(pos, 14.0, detail=4), 0.35, 0.7, 0.3, 1.0, smooth=False))
        col = g.mix(g.mul(dust, 0.32), col, (0.36, 0.33, 0.29))
        rough = g.lerp(g.mul(dust, 0.5), rough, 0.95)
    occl = g.remap(ao, 0.0, 1.0, 0.35, 1.0, smooth=False)
    return col, rough, metal, h, occl


# ------------------------------------------------------------------------------- material graphs

def build(m, imgs):
    """Give material `m` its procedural network, an emission output per baked pass and an image node
    per pass (so any object using it can be the bake target). Returns nothing; `set_pass` switches."""
    surf, kind = kind_of(m)
    pal = hs.PALETTE.get(kind) or hs.PALETTE["grey"]
    nt = m.node_tree
    nt.nodes.clear()
    g = G(nt)
    out = g.node("ShaderNodeOutputMaterial", name="out")
    r = RECIPES.get(surf, polymer)(g, pal)
    col, rough, metal, h, occl = _wear(g, surf, pal, r)
    e_col = g.node("ShaderNodeEmission", name="pass_color")
    g.link(_rgba(col), e_col.inputs["Color"])
    e_orm = g.node("ShaderNodeEmission", name="pass_orm")
    g.link(g.rgb(occl, rough, metal), e_orm.inputs["Color"])
    bsdf = g.node("ShaderNodeBsdfPrincipled", name="pass_normal")
    if r["bump"]:
        bump = g.node("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 1.0
        bump.inputs["Distance"].default_value = r["bump"]
        g.link(h, bump.inputs["Height"])
        g.link(bump.outputs[0], bsdf.inputs["Normal"])
    for name, img in imgs.items():
        t = g.node("ShaderNodeTexImage", name="img_" + name, image=img)
        t.label = name
    nt.links.new(e_col.outputs[0], out.inputs["Surface"])


def set_pass(mats, name):
    for m in mats:
        nt = m.node_tree
        src = nt.nodes["pass_" + name]
        nt.links.new(src.outputs[0], nt.nodes["out"].inputs["Surface"])
        nt.nodes.active = nt.nodes["img_" + name]


def _gltf_group():
    ng = bpy.data.node_groups.get("glTF Material Output")
    if ng is None:
        ng = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        ng.interface.new_socket(name="Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        ng.interface.new_socket(name="Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
    return ng


def final(m, imgs=None):
    """The material as the game gets it: Principled BSDF fed by the atlas (or flat palette values
    without a bake). Emissive kinds stay flat and glowing."""
    surf, kind = kind_of(m)
    base, _, metal, rough, _, emit = hs.PALETTE.get(kind) or hs.PALETTE["grey"]
    nt = m.node_tree
    nt.nodes.clear()
    g = G(nt)
    out = g.node("ShaderNodeOutputMaterial")
    bsdf = g.node("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Base Color"].default_value = (*base, 1)
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*base, 1)
        bsdf.inputs["Emission Strength"].default_value = emit
        return
    if not imgs:
        return
    tc = g.node("ShaderNodeTexImage", image=imgs["color"])
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    to = g.node("ShaderNodeTexImage", image=imgs["orm"])
    sep = g.node("ShaderNodeSeparateColor")
    nt.links.new(to.outputs["Color"], sep.inputs[0])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    grp = g.node("ShaderNodeGroup")
    grp.node_tree = _gltf_group()
    nt.links.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    tn = g.node("ShaderNodeTexImage", image=imgs["normal"])
    nm = g.node("ShaderNodeNormalMap", space="TANGENT", uv_map=ATLAS)
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])


# ------------------------------------------------------------------------------------ UV layout

def _uv_area(me, layer):
    uv = np.zeros(len(me.loops) * 2)
    me.uv_layers[layer].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    tot = 0.0
    for p in me.polygons:
        idx = range(p.loop_start, p.loop_start + p.loop_total)
        pts = uv[list(idx)]
        x, y = pts[:, 0], pts[:, 1]
        tot += 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
    return tot


def fabric_uvs(obj):
    """Add the "fabric" UV layer: the object's atlas UVs scaled to metres (its own islands, before
    packing), so patterns keep their real size."""
    me = obj.data
    if ATLAS not in me.uv_layers:
        return
    a3 = sum(p.area for p in me.polygons)
    auv = _uv_area(me, ATLAS)
    k = math.sqrt(a3 / auv) if auv > 1e-12 else 1.0
    uv = np.zeros(len(me.loops) * 2)
    me.uv_layers[ATLAS].data.foreach_get("uv", uv)
    if FABRIC in me.uv_layers:
        me.uv_layers.remove(me.uv_layers[FABRIC])
    lay = me.uv_layers.new(name=FABRIC)
    lay.data.foreach_set("uv", uv * k)
    me.uv_layers.active = me.uv_layers[ATLAS]
    me.uv_layers[ATLAS].active_render = True


def unwrap(objs):
    """Smart-project the parts that have no UVs of their own (hard-surface parts)."""
    objs = [o for o in objs if ATLAS not in o.data.uv_layers or o.get("unwrap")]
    if not objs:
        return
    for o in objs:
        if ATLAS not in o.data.uv_layers:
            o.data.uv_layers.new(name=ATLAS)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(55), island_margin=0.002, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def _islands(bm, uv):
    """Faces grouped into UV islands (connected through shared vertices with matching UVs)."""
    parent = {f.index: f.index for f in bm.faces}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) != 2:
            continue
        f0, f1 = lf
        ok = True
        for v in e.verts:
            u0 = next(l[uv].uv for l in f0.loops if l.vert == v)
            u1 = next(l[uv].uv for l in f1.loops if l.vert == v)
            if (u0 - u1).length > 1e-5:
                ok = False
        if ok:
            parent[find(f0.index)] = find(f1.index)
    out = {}
    for f in bm.faces:
        out.setdefault(find(f.index), []).append(f)
    return list(out.values())


def scale_islands(obj, factor_of):
    """Scale each UV island of `obj` about its centre by factor_of(faces) (texel density per region:
    the face gets more pixels than the back)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    uv = bm.loops.layers.uv[ATLAS]
    for isl in _islands(bm, uv):
        k = factor_of(isl)
        if abs(k - 1.0) < 1e-3:
            continue
        loops = [l for f in isl for l in f.loops]
        c = sum((l[uv].uv for l in loops), Vector((0, 0))) / len(loops)
        for l in loops:
            l[uv].uv = c + (l[uv].uv - c) * k
    bm.to_mesh(obj.data)
    bm.free()


def layout(objs, margin=0.0025):
    """Lay every part's UVs into one atlas: equal texel density (then each object's "texel" factor and
    each island's own, see scale_islands), packed together. Call fabric_uvs first."""
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        k = o.get("texel", 1.0)
        fn = _TEXEL_FN.get(o.name)
        fn = fn(o) if fn else None
        if k != 1.0 or fn:
            scale_islands(o, (lambda isl, k=k, fn=fn: k * (fn(isl) if fn else 1.0)))
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=margin, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")


_TEXEL_FN = {}  # object name -> (object -> (island faces -> texel factor)): the face gets more texels


# ---------------------------------------------------------------------------------------- bake

def _images(cid, size):
    imgs = {}
    for name, cs in (("color", "sRGB"), ("orm", "Non-Color"), ("normal", "Non-Color")):
        img = bpy.data.images.new(f"{cid}_{name}", size, size, alpha=True)
        img.colorspace_settings.name = cs
        px = np.zeros(size * size * 4, dtype=np.float32)
        img.pixels.foreach_set(px)
        imgs[name] = img
    return imgs


def _dilate(img, steps=12):
    """Grow the baked islands into the empty gutters (so mip-maps and bilinear filtering do not pull
    in black), then make the image opaque."""
    w, h = img.size
    px = np.zeros(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    filled = px[:, :, 3] > 0.5
    rgb = px[:, :, :3] * filled[:, :, None]
    for _ in range(steps):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(filled.shape, dtype=np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            f = np.roll(np.roll(filled, dy, 0), dx, 1)
            acc += np.roll(np.roll(rgb, dy, 0), dx, 1) * f[:, :, None]
            cnt += f
        grow = (~filled) & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow][:, None]
        filled = filled | grow
    if not filled.all():
        mean = rgb[filled].mean(axis=0) if filled.any() else np.array([0.5, 0.5, 1.0])
        rgb[~filled] = mean
    px[:, :, :3] = rgb
    px[:, :, 3] = 1.0
    img.pixels.foreach_set(px.ravel())


def _pixels(img):
    px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(-1, 4)


def _keep_facing(img, before, safe):
    """Where the full-cage normal bake turned normals away from the surface (its rays started past
    a nearby part of the same high mesh, the other thigh or the torso beside a sleeve, and hit it
    from behind), take the bake whose rays started just outside the surface; flat if that failed too.
    Returns how many pixels it replaced."""
    full = _pixels(img)
    changed = (np.abs(full - before).sum(1) > 0) | (np.abs(safe - before).sum(1) > 0)
    bad = changed & (full[:, 2] < 0.6)  # tangent-space z under 0.2: tipped past 78 degrees
    ok = safe[:, 2] >= 0.6
    full[bad & ok] = safe[bad & ok]
    full[bad & ~ok] = (0.5, 0.5, 1.0, 1.0)
    img.pixels.foreach_set(full.ravel())
    return int(bad.sum())


def _visible(obj, on):
    for a in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_shadow", "visible_transmission", "visible_volume_scatter"):
        setattr(obj, a, on)


def bake(cid, groups, size=TEX, tmpdir=None, samples=10):
    """Bake every material's network into the atlas. `groups`: [(lows, highs)] where lows are the game
    parts and highs (or None) the detailed meshes they take colour and normals from (selected-to-
    active; `ext` = cage extrusion, `ray` = max ray distance in each group's third item, optional).
    Returns {"color", "orm", "normal"} images, saved as files in tmpdir."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.use_denoising = False
    imgs = _images(cid, size)
    lows = [o for gr in groups for o in gr[0]]
    highs = [o for gr in groups for o in (gr[1] or [])]
    mats = {m for o in lows + highs for m in o.data.materials if m is not None}
    for m in mats:
        build(m, imgs)
    for h in highs:
        h.hide_render = True
    for name, kind, smp in (("color", "EMIT", samples), ("orm", "EMIT", samples), ("normal", "NORMAL", 1)):
        sc.cycles.samples = smp
        set_pass(mats, name)
        for gr in groups:
            t0 = time.time()
            lo, hi = gr[0], gr[1]
            opt = gr[2] if len(gr) > 2 else {}
            bpy.ops.object.select_all(action="DESELECT")
            if hi:
                for h in hi:
                    h.hide_render = False
                    h.select_set(True)
                for o in lo:
                    _visible(o, False)  # its surface must not shadow the high mesh's occlusion

                def s2a(ext):
                    for o in lo:
                        o.select_set(True)
                        bpy.context.view_layer.objects.active = o
                        bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=ext,
                                            max_ray_distance=opt.get("ray", 0.03), margin=0, use_clear=False,
                                            normal_space="TANGENT", uv_layer=ATLAS, target="IMAGE_TEXTURES")
                        o.select_set(False)
                ext = opt.get("ext", 0.01)
                if name == "normal":
                    before = _pixels(imgs["normal"])
                    s2a(min(0.002, ext))
                    safe = _pixels(imgs["normal"])
                s2a(ext)
                if name == "normal":
                    fixed = _keep_facing(imgs["normal"], before, safe)
                    if fixed and os.environ.get("REAL_TIMING"):
                        print(f"    normal {lo[0].name}: {fixed} px faced away, re-baked from the surface", flush=True)
                for o in lo:
                    _visible(o, True)
                for h in hi:
                    h.hide_render = True
            else:
                for o in lo:
                    o.select_set(True)
                bpy.context.view_layer.objects.active = lo[0]
                bpy.ops.object.bake(type=kind, use_selected_to_active=False, margin=0, use_clear=False,
                                    normal_space="TANGENT", uv_layer=ATLAS, target="IMAGE_TEXTURES")
            if os.environ.get("REAL_TIMING"):
                print(f"    {name} {lo[0].name}{'+' if len(lo) > 1 else ''}: {time.time() - t0:.0f}s", flush=True)
        print(f"  baked {name}", flush=True)
    tmpdir = tmpdir or os.environ.get("REAL_MAPS") or bpy.app.tempdir or "/tmp"
    for name, img in imgs.items():
        _dilate(img)
        img.filepath_raw = os.path.join(tmpdir, f"{cid}_{name}.png")
        img.file_format = "PNG"
        img.save()
    return imgs
