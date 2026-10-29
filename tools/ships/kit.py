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
from mathutils import Matrix, Vector  # noqa: E402

block, cut, cyl, join, label, plan, prism, ring, tube, unite = wk.block, wk.cut, wk.cyl, wk.join, wk.label, wk.plan, wk.prism, wk.ring, wk.tube, wk.unite

TRIS_MAX = 60000
MESHES_MAX = 6


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
    "red_light": ((1.0, 0.08, 0.05), (1.0, 0.08, 0.05), 0.0, 0.3, 0.0, 6.0),
    "green_light": ((0.1, 1.0, 0.3), (0.1, 1.0, 0.3), 0.0, 0.3, 0.0, 6.0),
    "screen": ((0.35, 0.9, 0.6), (0.35, 0.9, 0.6), 0.0, 0.3, 0.0, 3.0),
    "lights_amber": ((1.0, 0.55, 0.12), (1.0, 0.55, 0.12), 0.0, 0.3, 0.0, 4.0),
    "deserter_dark": srgb("#141413", metallic=0.3, roughness=0.6, lighten=2.5),
    "deserter_pale": srgb("#F0EEE6", roughness=0.45, lighten=0.85),
    "deserter_orange": srgb("#D97757", roughness=0.5),
    "deserter_tan": srgb("#D4A27F", roughness=0.85, wear=0.3),
    # See-through cockpit glass for the small solid fighters (the big ships' "glass" stays opaque).
    "canopy": ((0.05, 0.11, 0.15), (0.05, 0.11, 0.15), 0.0, 0.05, 0.0, 0),
})
CANOPY_ALPHA = 0.4


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
            o = join(members, group)
            if group == "ramp":
                hinge = next(e for e in self.nodes if e.name == "ramp")
                bpy.context.view_layer.update()
                mw = o.matrix_world.copy()
                o.parent = hinge
                bpy.context.view_layer.update()
                o.matrix_world = mw
            objs.append(o)
        self.objects = objs
        if bake:
            wk.TEX = 1024
            print(f"baking {self.id}")
            wk.bake_wear(self, objs, scale=40.0)
        for m in {m for o in objs for m in o.data.materials if m is not None and m.get("kind") == "canopy"}:
            _see_through(m)
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


def _see_through(m):
    """Make a `canopy` material blend at CANOPY_ALPHA, so the glTF carries alphaMode BLEND."""
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Alpha"].default_value = CANOPY_ALPHA
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    if hasattr(m, "blend_method"):
        m.blend_method = "BLEND"


# ------------------------------------------------------------------------------------ hull bits

def loft(name, sections, material, sides=8, phase=0.0, bevel=0.0, segs=2, cap=True):
    """A hull skinned through cross-sections along Y. Each section is (y, x, z, rx, rz): a
    `sides`-gon of half-width rx and half-height rz centred at (x, z), its first corner `phase`
    degrees up from +X. A section with rx and rz both 0 closes the hull to a point."""
    import bmesh
    bm = bmesh.new()
    rings = []
    for y, cx, cz, rx, rz in sections:
        if rx <= 1e-6 and rz <= 1e-6:
            rings.append([bm.verts.new((cx, y, cz))])
            continue
        angs = [math.radians(phase) + 2 * math.pi * i / sides for i in range(sides)]
        rings.append([bm.verts.new((cx + rx * math.cos(a), y, cz + rz * math.sin(a))) for a in angs])
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1 or len(b) == 1:
            tip, ring_ = (a[0], b) if len(a) == 1 else (b[0], a)
            for i in range(sides):
                bm.faces.new((tip, ring_[i], ring_[(i + 1) % sides]))
            continue
        for i in range(sides):
            j = (i + 1) % sides
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if cap:
        for r in (rings[0], rings[-1]):
            if len(r) > 1:
                bm.faces.new(r)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return wk._obj(name, bm, material, bevel, segs)


def rotate(obj, c, axis, deg):
    """Rotate a part's mesh by `deg` degrees about `axis` ("x", "y" or "z") through the point `c`."""
    t = Matrix.Translation(Vector(c))
    obj.data.transform(t @ Matrix.Rotation(math.radians(deg), 4, axis.upper()) @ t.inverted())
    return obj


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

def preview(path, cam, look=(0, 0, 0), lens=35, res=(960, 600), fresh=False):
    """A look-dev render of the whole ship under a dark sky. `fresh` first clears the camera,
    lights and ground an earlier preview of the same scene added, so they do not stack."""
    scene = bpy.context.scene
    if fresh:
        for o in [o for o in bpy.data.objects if o.get("preview")]:
            bpy.data.objects.remove(o, do_unlink=True)
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
    c["preview"] = True
    c.location = cam
    c.rotation_euler = (Vector(look) - Vector(cam)).to_track_quat("-Z", "Y").to_euler()
    scene.camera = c
    for name, energy, rot in (("key", 4.0, (50, 0, -120)), ("rim", 1.8, (60, 0, 60)), ("fill", 0.8, (80, 0, 180))):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        lo = bpy.data.objects.new(name, ld)
        lo.rotation_euler = tuple(math.radians(a) for a in rot)
        lo["preview"] = True
        scene.collection.objects.link(lo)
    # Every `lamp.<n>` empty lights the cabin in the render as it does in the game.
    for e in [o for o in bpy.data.objects if o.type == "EMPTY" and o.name.startswith("lamp.")]:
        ld = bpy.data.lights.new(e.name, "POINT")
        ld.energy = 120.0
        ld.color = (1.0, 0.9, 0.75)
        ld.shadow_soft_size = 0.15
        lo = bpy.data.objects.new(e.name, ld)
        lo.location = e.matrix_world.translation - Vector((0, 0, 0.05))
        lo["preview"] = True
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
    g["preview"] = True
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
    if "cabin" in spec:
        floor, ceiling, half = spec["cabin"]
        if ceiling - floor < 2.2:
            problems.append(f"cabin only {ceiling - floor:.2f} m tall, want 2.2")
        if half < 0.9:
            problems.append(f"cabin only {2 * half:.2f} m wide, want 1.8")
        if "ramp" not in names:
            problems.append("missing node ramp")
    return problems, {"tris": tris, "size": tuple(round(s, 2) for s in size), "kb": os.path.getsize(path) // 1024}


# ------------------------------------------------------------------------------------ interiors

def cabin(ship, c, s, material, wall=0.12, opening=None, bevel=0.06, segs=3):
    """A hollow box: the outer block minus a cavity `wall` thick, with, when `opening=(w, h)` is
    given, a doorway that wide and tall cut in the back (-Y) face from the floor up."""
    outer = block("cabin", c, s, material, bevel=bevel, segs=segs)
    inner = block("cavity", c, (s[0] - 2 * wall, s[1] - 2 * wall, s[2] - 2 * wall), material, bevel=0)
    cutters = [inner]
    if opening:
        w, h = opening
        floor = c[2] - s[2] / 2 + wall
        cutters.append(block("door", (c[0], c[1] - s[1] / 2, floor + h / 2 + 0.01), (w, wall * 4, h), material, bevel=0))
    outer = cut(outer, *cutters)
    ship.add(outer)
    return outer


def ramp(ship, hinge, width, length, drop, material="gunmetal", thick=0.08):
    """A boarding ramp hinged at its top edge (`hinge`, Blender coords, the cabin's floor edge at
    the back), lying open: `length` aft and `drop` down to the ground. The plate, its tread bars
    and chevrons go in the `ramp` group under a `ramp` empty at the hinge, so the game can swing
    it shut in flight. Returns the slope in degrees."""
    import math as m
    slope = m.degrees(m.atan2(drop, m.sqrt(max(1e-6, length * length - drop * drop))))
    run = m.sqrt(max(1e-6, length * length - drop * drop))
    hx, hy, hz = hinge
    e = ship.node("ramp", hinge)
    e.empty_display_size = 0.3
    # Build flat along -Y, then tilt about X by the slope (nose-down toward the ground).
    parts = [block("plate", (hx, hy - length / 2, hz - thick / 2), (width, length, thick), material, bevel=0.015)]
    n = max(3, int(length / 0.35))
    for i in range(n):
        y = hy - (i + 0.5) * length / n
        parts.append(block("tread", (hx, y, hz + 0.015), (width - 0.2, 0.05, 0.03), "black", bevel=0))
    for sx in (-1, 1):
        parts.append(block("chev", (hx + sx * (width / 2 - 0.08), hy - length / 2, hz + 0.005), (0.1, length - 0.1, 0.012), "hazard", bevel=0))
    rot = Matrix.Rotation(m.radians(-slope), 4, "X")
    for o in parts:
        o.data.transform(Matrix.Translation((-hx, -hy, -hz)))
        o.data.transform(rot)
        o.data.transform(Matrix.Translation((hx, hy, hz)))
        ship.add(o, "ramp")
    return slope


def seat(name, c, facing=1, material="black", frame="gunmetal", w=0.55):
    """A crew seat at `c` (the cushion's centre), facing +Y (`facing=1`) or -Y."""
    x, y, z = c
    parts = [block(name, (x, y, z), (w, 0.5, 0.12), material, bevel=0.03),
             block("back", (x, y - facing * 0.26, z + 0.35), (w, 0.08, 0.7), material, bevel=0.03),
             block("ped", (x, y, z - 0.22), (0.14, 0.14, 0.4), frame, bevel=0.01),
             block("foot", (x, y, z - 0.42), (0.4, 0.4, 0.04), frame, bevel=0.01)]
    return join(parts, name)


def console(ship, c, s, material="gunmetal", screens=2, screen_mat="blue_light", facing=-1):
    """A sloped console with lit screens on its face toward `facing` (+1 = toward the nose)."""
    x, y, z = c
    ship.add(block("console", c, s, material, bevel=0.02, taper=(1.0, 0.7)))
    sw = (s[0] - 0.1 * (screens + 1)) / screens
    for i in range(screens):
        sx = x - s[0] / 2 + 0.1 + sw / 2 + i * (sw + 0.1)
        ship.add(block("screen", (sx, y - facing * s[1] * 0.28, z + s[2] * 0.42), (sw, 0.02, s[2] * 0.5), screen_mat, bevel=0), "lights")
    return None


def crate(name, c, s, material="olive"):
    x, y, z = c
    parts = [block(name, c, s, material, bevel=0.02)]
    for sx in (-1, 1):
        parts.append(block("band", (x + sx * (s[0] / 2 - 0.08), y, z), (0.05, s[1] + 0.02, s[2] + 0.02), "black", bevel=0))
    return join(parts, name)


def locker(name, c, s, material="grey", doors=2):
    x, y, z = c
    parts = [block(name, c, s, material, bevel=0.015)]
    dw = s[0] / doors
    for i in range(doors):
        dx = x - s[0] / 2 + dw * (i + 0.5)
        parts.append(block("handle", (dx + dw * 0.3, y - s[1] / 2 - 0.02, z), (0.03, 0.04, 0.18), "steel", bevel=0))
        parts.append(block("vent", (dx, y - s[1] / 2 - 0.005, z + s[2] * 0.3), (dw * 0.5, 0.01, 0.12), "black", bevel=0))
    return join(parts, name)


def light_strip(ship, p0, p1, w=0.12, material="lamp"):
    """A ceiling light strip from p0 to p1 (same z), in the lights group."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    ship.add(block("strip", ((x0 + x1) / 2, (y0 + y1) / 2, z0), (abs(x1 - x0) + w, abs(y1 - y0) + w, 0.03), material, bevel=0), "lights")


def handrail(name, p0, p1, r=0.025, material="steel", posts=2):
    """A rail from p0 to p1 with posts down 0.9 m."""
    parts = [cyl(name, p0, p1, r, material, segs=8, bevel=0)]
    a, b = Vector(p0), Vector(p1)
    for i in range(posts):
        p = a.lerp(b, (i + 0.5) / posts)
        parts.append(cyl("post", p, p - Vector((0, 0, 0.9)), r, material, segs=8, bevel=0))
    return join(parts, name)


def hinge(name, c, axis="y", length=0.3, r=0.035, material="steel"):
    """A barrel hinge with two knuckles along `axis`."""
    a = {"x": Vector((1, 0, 0)), "y": Vector((0, 1, 0)), "z": Vector((0, 0, 1))}[axis]
    c = Vector(c)
    parts = [cyl(name, c - a * length / 2, c + a * length / 2, r, material, segs=10, bevel=0)]
    for k in (-1, 1):
        parts.append(block("leaf", tuple(c + a * k * length * 0.3), (r * 2.4, r * 2.4, r * 2.4), material, bevel=0))
    return join(parts, name)


def nav_light(ship, name, c, material, r=0.07):
    ship.add(sphere("nav", c, r, material, segs=10), "lights")
    ship.node(name, c)


def chain(name, p0, p1, links=8, r=0.03, material="steel"):
    """A hanging chain: alternating short cylinders along p0->p1."""
    a, b = Vector(p0), Vector(p1)
    parts = []
    for i in range(links):
        q0 = a.lerp(b, i / links)
        q1 = a.lerp(b, (i + 0.8) / links)
        parts.append(cyl(name, q0, q1, r if i % 2 else r * 0.7, material, segs=6, bevel=0))
    return join(parts, name)
