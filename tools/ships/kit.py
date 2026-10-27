"""Hull kit for the faction ships, on top of the weapons kit at metre scale.

Blender is Z-up; every ship points its nose down +Y with its centre of mass near the origin and its
right side on +X. The glTF exporter turns +Y into -Z, the ship frame `solar::ship` flies in.
Parts go into three groups that each export as one mesh: `hull` (opaque, baked wear), `glass` and
`lights` (emissive). Named empties (`exhaust.<n>`, `heat`, `light.<n>`) tell the game where glows go.
"""

import math
import os
import sys

import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))


def _weapons_kit():
    """The weapons kit, loaded under its own name so it does not collide with this module."""
    spec = importlib.util.spec_from_file_location("weapons_kit", os.path.join(os.path.dirname(HERE), "weapons", "kit.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["weapons_kit"] = mod
    spec.loader.exec_module(mod)
    return mod


wk = _weapons_kit()
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

block, cut, cyl, join, label, plan, prism, tube, unite = wk.block, wk.cut, wk.cyl, wk.join, wk.label, wk.plan, wk.prism, wk.tube, wk.unite

TRIS_MAX = 12000
MESHES_MAX = 4


def srgb(hex_color, metallic=0.0, roughness=0.55, wear=0.5, lighten=1.25):
    """A palette entry from an sRGB hex colour (Blender wants linear)."""
    h = hex_color.lstrip("#")
    lin = tuple(((int(h[i:i + 2], 16) / 255 + 0.055) / 1.055) ** 2.4 if int(h[i:i + 2], 16) / 255 > 0.04045 else int(h[i:i + 2], 16) / 255 / 12.92 for i in (0, 2, 4))
    worn = tuple(min(1.0, c * lighten + 0.04) for c in lin)
    return (lin, worn, metallic, roughness, wear, 0)


wk.PALETTE.update({
    "slate": ((0.20, 0.22, 0.25), (0.38, 0.40, 0.43), 0.1, 0.55, 0.5, 0),
    "bone": ((0.86, 0.84, 0.78), (0.70, 0.68, 0.62), 0.0, 0.5, 0.45, 0),
    "gold": ((0.79, 0.64, 0.15), (0.9, 0.8, 0.45), 1.0, 0.3, 0.4, 0),
    "leather": ((0.30, 0.18, 0.10), (0.45, 0.32, 0.2), 0.0, 0.8, 0.5, 0),
    "gunmetal": ((0.16, 0.17, 0.19), (0.45, 0.46, 0.48), 0.6, 0.4, 0.5, 0),
    "white": ((0.80, 0.81, 0.82), (0.6, 0.6, 0.62), 0.0, 0.35, 0.4, 0),
    "blue_light": ((0.3, 0.6, 1.0), (0.3, 0.6, 1.0), 0.0, 0.3, 0.0, 6.0),
    "gold_light": ((1.0, 0.75, 0.3), (1.0, 0.75, 0.3), 0.0, 0.3, 0.0, 4.0),
    "deserter_dark": srgb("#141413", metallic=0.3, roughness=0.6, lighten=2.5),
    "deserter_pale": srgb("#F0EEE6", roughness=0.45, lighten=0.85),
    "deserter_orange": srgb("#D97757", roughness=0.5),
    "deserter_tan": srgb("#D4A27F", roughness=0.85, wear=0.3),
})


class Ship:
    """One ship being built: parts by group and the named empties the game looks for."""

    def __init__(self, sid):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        wk._current["gun"] = sid
        self.id = sid
        self.scene = bpy.context.scene
        self.parts = []  # (object, group)
        self.nodes = []

    def add(self, obj, group="hull"):
        self.parts.append((obj, group))
        return obj

    def node(self, name, at):
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = 0.2
        e.location = at
        self.scene.collection.objects.link(e)
        self.nodes.append(e)
        return e

    def finish(self, out_dir, bake=True):
        groups = {}
        for obj, group in self.parts:
            groups.setdefault(group, []).append(obj)
        objs = []
        for group, members in groups.items():
            for o in members:
                wk.apply_modifiers(o)
            objs.append(join(members, group))
        self.objects = objs
        if bake:
            wk.TEX = 1024
            wk.bake_wear(self, objs, scale=40.0)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{self.id}.glb")
        bpy.ops.object.select_all(action="DESELECT")
        for o in bpy.data.objects:
            o.select_set(True)
        bpy.ops.export_scene.gltf(
            filepath=path, export_format="GLB", use_selection=True, export_apply=False, export_animations=False,
            export_skins=False, export_materials="EXPORT", export_image_format="JPEG", export_jpeg_quality=85, export_yup=True,
        )
        tris = sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons)
        print(f"wrote {path}: {os.path.getsize(path) // 1024} KB, {tris} tris, {len(objs)} meshes, {len(self.nodes)} nodes")
        return path


# ------------------------------------------------------------------------------------ hull bits

def plate(name, c, s, material, lines=(), bevel=0.02, depth=0.03, width=0.03):
    """An armour plate: a bevelled block with panel-line grooves. `lines` are (axis, offset) pairs in
    the plate's own frame, the groove running across the plate at that offset along `axis` (x or y)."""
    p = block(name, c, s, material, bevel=bevel)
    cutters = []
    for axis, off in lines:
        if axis == "x":
            cutters.append(block("line", (c[0] + off, c[1], c[2] + s[2] / 2), (width, s[1] + 0.1, depth * 2), material, bevel=0))
        else:
            cutters.append(block("line", (c[0], c[1] + off, c[2] + s[2] / 2), (s[0] + 0.1, width, depth * 2), material, bevel=0))
    return cut(p, *cutters) if cutters else p


def seams(ship, c, s, ys=(), xs=(), material="black", width=0.04, proud=0.012):
    """Panel lines round a box part, as thin dark strips laid on the surface (a boolean groove
    through a bevelled part costs thousands of triangles; a strip costs twelve). A ring at each `y`
    (across the hull) and a line along the top and bottom at each `x`."""
    for y in ys:
        for dz in (-1, 1):
            ship.add(block("seam", (c[0], c[1] + y, c[2] + dz * s[2] / 2), (s[0] - 0.02, width, proud * 2), material, bevel=0))
        for dx in (-1, 1):
            ship.add(block("seam", (c[0] + dx * s[0] / 2, c[1] + y, c[2]), (proud * 2, width, s[2] - 0.02), material, bevel=0))
    for x in xs:
        for dz in (-1, 1):
            ship.add(block("seam", (c[0] + x, c[1], c[2] + dz * s[2] / 2), (width, s[1] - 0.02, proud * 2), material, bevel=0))


def side_plate(name, x, c_yz, s_yz, material, thick=0.1, lines=(), bevel=0.02):
    """A plate stood on a flank at `x` (its grooves cut from the outside)."""
    side = 1 if x > 0 else -1
    p = block(name, (x, c_yz[0], c_yz[1]), (thick, s_yz[0], s_yz[1]), material, bevel=bevel)
    cutters = []
    for axis, off in lines:
        if axis == "y":
            cutters.append(block("line", (x + side * thick / 2, c_yz[0] + off, c_yz[1]), (0.06, 0.03, s_yz[1] + 0.1), material, bevel=0))
        else:
            cutters.append(block("line", (x + side * thick / 2, c_yz[0], c_yz[1] + off), (0.06, s_yz[0] + 0.1, 0.03), material, bevel=0))
    return cut(p, *cutters) if cutters else p


def rivets(name, p0, p1, n, r=0.03, material="steel", axis="x"):
    """A row of `n` domed fasteners from p0 to p1, their heads facing along `axis` (e.g. "-x")."""
    sgn = -1 if axis.startswith("-") else 1
    a = {"x": Vector((1, 0, 0)), "y": Vector((0, 1, 0)), "z": Vector((0, 0, 1))}[axis[-1]] * sgn
    p0, p1 = Vector(p0), Vector(p1)
    out = []
    for i in range(n):
        at = p0.lerp(p1, i / max(1, n - 1))
        out.append(cyl("rivet", at - a * 0.01, at + a * 0.025, r, material, r1=r * 0.6, segs=8, bevel=0))
    return join(out, name)


def stripe(name, c, s, material):
    """A painted band, 5 mm proud of the surface so the bake keeps its edge."""
    return block(name, c, (s[0] + 0.01, s[1] + 0.01, s[2] + 0.01), material, bevel=0.004)


def bell(name, p0, p1, r_throat, r_mouth, material="steel", segs=24):
    """An engine nozzle flaring from the throat at p0 to the mouth at p1, hollow."""
    p0, p1 = Vector(p0), Vector(p1)
    outer = cyl(name, p0, p1, r_throat, material, r1=r_mouth, segs=segs, bevel=0.01)
    inner = cyl("bore", p0 + (p1 - p0) * 0.15, p1 + (p1 - p0) * 0.2, r_throat * 0.8, material, r1=r_mouth * 0.9, segs=segs, bevel=0)
    return cut(outer, inner)


def skid(name, c, length, bottom, top, material="black", bar=0.22):
    """A landing skid: a bar whose underside sits at z=`bottom`, hung from two struts up to z=`top`."""
    x, y = c[0], c[1]
    zc = bottom + bar / 2
    parts = [block(name, (x, y, zc), (bar, length, bar), material, bevel=0.03)]
    for dy in (-length * 0.3, length * 0.3):
        parts.append(block("strut", (x, y + dy, (zc + bar / 2 + top) / 2), (0.14, 0.18, top - zc - bar / 2 + 0.02), material, bevel=0.01))
    return join(parts, name)


def leg(name, c, bottom, top, r=0.18, material="black"):
    """A single landing leg: a piston on a round foot."""
    x, y = c[0], c[1]
    parts = [cyl(name, (x, y, bottom), (x, y, bottom + 0.12), r * 2.2, material, segs=16, bevel=0.01),
             cyl("piston", (x, y, bottom + 0.1), (x, y, top + 0.02), r, material, segs=14, bevel=0.01)]
    return join(parts, name)


def pipe(name, pts, r, material="copper", segs=10):
    """A pipe run through `pts`, with a knuckle at every bend."""
    parts = []
    for a, b in zip(pts, pts[1:]):
        parts.append(cyl(name, a, b, r, material, segs=segs, bevel=0))
    for p in pts[1:-1]:
        parts.append(cyl("knuckle", (p[0], p[1], p[2] - r * 1.2), (p[0], p[1], p[2] + r * 1.2), r * 1.25, material, segs=segs, bevel=0))
    return join(parts, name)


def sphere(name, c, r, material, segs=16):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=segs // 2, radius=r)
    bmesh.ops.translate(bm, vec=Vector(c), verts=bm.verts)
    return wk._obj(name, bm, material, 0.0)


# -------------------------------------------------------------------------------------- preview

def preview(path, cam, look=(0, 0, 0), lens=35, res=(960, 600)):
    """A look-dev render of the whole ship under a dark sky."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = False
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x, scene.render.resolution_y = res
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    cd.clip_start = 0.1
    c = bpy.data.objects.new("cam", cd)
    scene.collection.objects.link(c)
    c.location = cam
    c.rotation_euler = (Vector(look) - Vector(cam)).to_track_quat("-Z", "Y").to_euler()
    scene.camera = c
    for name, energy, rot in (("key", 4.0, (50, 0, -120)), ("rim", 1.8, (60, 0, 60)), ("fill", 0.8, (80, 0, 180))):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        lo = bpy.data.objects.new(name, ld)
        lo.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(lo)
    # A ground plane catches the shadow so the ship reads as sitting on its gear.
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60)
    me = bpy.data.meshes.new("ground")
    bm.to_mesh(me)
    bm.free()
    low = min((o.matrix_world @ Vector(v)).z for o in bpy.data.objects if o.type == "MESH" for v in o.bound_box)
    g = bpy.data.objects.new("ground", me)
    g.location = (0, 0, low)
    gm = bpy.data.materials.new("ground")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.06, 0.06, 0.065, 1)
    gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    me.materials.append(gm)
    scene.collection.objects.link(g)
    scene.world = bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.07, 0.1, 1)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


# --------------------------------------------------------------------------------------- check

def check(path, spec):
    """Verify a ship straight from its glb: triangle budget, size within 10 % of the spec, the named
    nodes present, at most four meshes, and the lowest vertex at -rest (glTF is Y-up)."""
    j, _ = wk.read_glb(path)
    nodes = j["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    names = {n.get("name", "") for n in nodes}
    problems = [f"missing node {n}" for n in spec["nodes"] if n not in names]
    meshes = [n for n in nodes if "mesh" in n]
    if len(meshes) > MESHES_MAX:
        problems.append(f"{len(meshes)} meshes, want at most {MESHES_MAX}")
    tris = sum(j["accessors"][p["indices"]]["count"] // 3 for n in meshes for p in j["meshes"][n["mesh"]]["primitives"])
    if tris >= TRIS_MAX:
        problems.append(f"{tris} triangles, want under {TRIS_MAX}")

    def world(i):
        m = wk._identity()
        while i is not None:
            n = nodes[i]
            m = wk._mul(wk._trs(n.get("translation", [0, 0, 0]), n.get("rotation", [0, 0, 0, 1])), m)
            i = parent.get(i)
        return m

    lo, hi = [1e9] * 3, [-1e9] * 3
    for i, n in enumerate(nodes):
        if "mesh" not in n:
            continue
        w = world(i)
        for p in j["meshes"][n["mesh"]]["primitives"]:
            acc = j["accessors"][p["attributes"]["POSITION"]]
            for c in range(8):
                pt = wk._xform(w, [acc["max"][k] if c >> k & 1 else acc["min"][k] for k in range(3)])
                for k in range(3):
                    lo[k], hi[k] = min(lo[k], pt[k]), max(hi[k], pt[k])
    size = (hi[2] - lo[2], hi[0] - lo[0], hi[1] - lo[1])  # length (Z), span (X), height (Y)
    for got, want, what in zip(size, spec["size"], ("length", "span", "height")):
        if abs(got - want) > 0.1 * want:
            problems.append(f"{what} {got:.2f} m, want {want}")
    if abs(lo[1] + spec["rest"]) > 0.05:
        problems.append(f"lowest point {lo[1]:.2f}, want {-spec['rest']}")
    return problems, {"tris": tris, "size": tuple(round(s, 2) for s in size), "kb": os.path.getsize(path) // 1024}
