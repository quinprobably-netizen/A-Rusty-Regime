"""Hard-surface modelling kit for the first-person weapons: parts, cuts, rails, screws, markings,
a rigid bone rig, clips, one baked wear texture per weapon, glTF export and a rig checker.

Blender is Z-up; every weapon points down +Y with the trigger near the origin and its left side on -X
(the side the first-person camera sees). The glTF exporter turns +Y into -Z, which is where the
viewmodel points.
"""

import ctypes
import math
import os

import bpy  # first: bpy makes bmesh importable
import bmesh  # noqa: E402
from mathutils import Matrix, Vector

FPS = 60
TEX = 2048
DEVICE = None  # Cycles device for bake_wear: None takes the GPU when Cycles finds one (bake_device), "CPU" forces it

# name: (base color, worn color, metallic, roughness, how much the edges wear 0..1, emission strength)
PALETTE = {
    "olive": ((0.30, 0.31, 0.21), (0.55, 0.55, 0.45), 0.0, 0.62, 0.55, 0),
    "tan": ((0.46, 0.40, 0.29), (0.66, 0.60, 0.50), 0.0, 0.65, 0.5, 0),
    "grey": ((0.19, 0.20, 0.22), (0.42, 0.43, 0.45), 0.0, 0.55, 0.5, 0),
    "black": ((0.035, 0.035, 0.04), (0.22, 0.22, 0.23), 0.0, 0.5, 0.45, 0),
    "steel": ((0.09, 0.09, 0.10), (0.55, 0.55, 0.57), 0.85, 0.38, 0.8, 0),
    "bright": ((0.50, 0.51, 0.53), (0.78, 0.78, 0.80), 1.0, 0.24, 0.3, 0),
    "brass": ((0.62, 0.43, 0.17), (0.85, 0.66, 0.35), 1.0, 0.3, 0.4, 0),
    "copper": ((0.56, 0.30, 0.17), (0.80, 0.52, 0.36), 1.0, 0.35, 0.4, 0),
    "rubber": ((0.025, 0.025, 0.027), (0.08, 0.08, 0.08), 0.0, 0.9, 0.2, 0),
    "red": ((0.55, 0.05, 0.035), (0.35, 0.33, 0.32), 0.0, 0.45, 0.6, 0),
    "yellow": ((0.78, 0.55, 0.09), (0.40, 0.38, 0.35), 0.15, 0.55, 1.0, 0),
    "rust": ((0.30, 0.15, 0.07), (0.45, 0.25, 0.12), 0.3, 0.9, 0.6, 0),
    "glass": ((0.02, 0.03, 0.04), (0.02, 0.03, 0.04), 0.0, 0.05, 0.0, 0),
    "reticle": ((1.0, 0.12, 0.05), (1.0, 0.12, 0.05), 0.0, 0.3, 0.0, 6.0),
    "lamp": ((0.95, 0.93, 0.85), (0.95, 0.93, 0.85), 0.0, 0.1, 0.0, 1.5),
    "cord": ((0.12, 0.11, 0.09), (0.25, 0.23, 0.2), 0.0, 0.95, 0.3, 0),
    "hazard": ((0.85, 0.62, 0.05), (0.3, 0.3, 0.3), 0.0, 0.5, 0.8, 0),
}


class Gun:
    """One weapon being built: its armature, parts by bone, sockets and clips."""

    def __init__(self, gid, bones):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.id = gid
        self.scene = bpy.context.scene
        self.scene.render.fps = FPS
        self.bones = {"root": ((0, 0, 0), None), **bones}
        self.arm = self._armature()
        self.parts = []  # (object, bone)
        self.clips = {}

    # ------------------------------------------------------------------------------------- rig
    def _armature(self):
        data = bpy.data.armatures.new("rig")
        arm = bpy.data.objects.new("rig", data)
        self.scene.collection.objects.link(arm)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        for name, (head, _) in self.bones.items():
            b = data.edit_bones.new(name)
            b.head = Vector(head)
            b.tail = Vector(head) + Vector((0, 0.02, 0))
            b.roll = 0
        for name, (_, parent) in self.bones.items():
            if name != "root":
                data.edit_bones[name].parent = data.edit_bones[parent or "root"]
        bpy.ops.object.mode_set(mode="OBJECT")
        return arm

    def add(self, obj, bone="root"):
        self.parts.append((obj, bone))
        return obj

    def socket(self, name, at, bone="root"):
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = 0.01
        e.location = at
        self.scene.collection.objects.link(e)
        self._parent(e, bone)
        return e

    def _parent(self, obj, bone):
        bpy.context.view_layer.update()
        mw = obj.matrix_world.copy()
        obj.parent = self.arm
        obj.parent_type = "BONE"
        obj.parent_bone = bone
        bpy.context.view_layer.update()
        obj.matrix_world = mw

    def clip(self, name, length, tracks):
        """tracks: {bone: [(seconds, (x, y, z) metres, (rx, ry, rz) degrees), ...]}; bones left out
        stay at rest, keyed at both ends so no clip inherits another's pose."""
        self.clips[name] = (length, tracks)

    # -------------------------------------------------------------------------------- finishing
    def finish(self, out_dir, bake=True):
        groups = {}
        for obj, bone in self.parts:
            key = obj.name if obj.name.startswith("att.") else f"mesh.{bone}"
            groups.setdefault(key, (bone, []))[1].append(obj)
        objs = []
        for key, (bone, members) in groups.items():
            for o in members:
                apply_modifiers(o)
            o = join(members, key)
            self._parent(o, bone)
            objs.append(o)
        self.objects = objs
        if bake:
            bake_wear(self, objs)
        self._bake_clips()
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{self.id}.glb")
        bpy.ops.object.select_all(action="DESELECT")
        for o in bpy.data.objects:
            o.select_set(True)
        bpy.ops.export_scene.gltf(
            filepath=path, export_format="GLB", use_selection=True, export_apply=False,
            export_animations=True, export_animation_mode="NLA_TRACKS", export_skins=False,
            export_materials="EXPORT", export_image_format="JPEG", export_jpeg_quality=88, export_yup=True,
        )
        tris = sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons)
        print(f"wrote {path}: {os.path.getsize(path) // 1024} KB, {tris} tris, {len(objs)} meshes")
        return path

    def _bake_clips(self):
        arm = self.arm
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="POSE")
        for pb in arm.pose.bones:
            pb.rotation_mode = "XYZ"
        arm.animation_data_create()
        for name, (length, tracks) in self.clips.items():
            action = bpy.data.actions.new(name)
            arm.animation_data.action = action
            if hasattr(arm.animation_data, "action_slot") and len(action.slots) == 0:
                arm.animation_data.action_slot = action.slots.new(arm.id_type, arm.name)
            end = max(1, round(length * FPS))
            for pb in arm.pose.bones:
                keys = list(tracks.get(pb.name, []))
                if not keys or keys[0][0] > 0:
                    keys.insert(0, (0.0, (0, 0, 0), (0, 0, 0)))
                if keys[-1][0] < length:
                    keys.append((length, (0, 0, 0), (0, 0, 0)))
                for t, loc, rot in keys:
                    pb.location = loc
                    pb.rotation_euler = tuple(math.radians(a) for a in rot)
                    f = min(end, round(t * FPS))
                    pb.keyframe_insert("location", frame=f)
                    pb.keyframe_insert("rotation_euler", frame=f)
            action.use_fake_user = True
            arm.animation_data.action = None
            track = arm.animation_data.nla_tracks.new()
            track.name = name
            strip = track.strips.new(name, 0, action)
            if hasattr(strip, "action_slot") and len(action.slots):
                strip.action_slot = action.slots[0]
            track.mute = True
        for pb in arm.pose.bones:
            pb.location = (0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
        bpy.ops.object.mode_set(mode="OBJECT")


# ------------------------------------------------------------------------------------ materials

_current = {"gun": "gun"}


def mat(name):
    full = f"{_current['gun']}.{name}"
    m = bpy.data.materials.get(full)
    if m is None:
        m = bpy.data.materials.new(full)
        m["kind"] = name
        base, _, metal, rough, _, emit = PALETTE[name]
        m.use_nodes = True
        bsdf = m.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*base, 1)
        bsdf.inputs["Metallic"].default_value = metal
        bsdf.inputs["Roughness"].default_value = rough
        if emit:
            bsdf.inputs["Emission Color"].default_value = (*base, 1)
            bsdf.inputs["Emission Strength"].default_value = emit
    return m


def begin(gid, bones):
    _current["gun"] = gid
    return Gun(gid, bones)


# ------------------------------------------------------------------------------------- geometry

def _obj(name, bm, material, bevel, segs=2):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat(material))
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o["bevel"] = bevel
    o["segs"] = segs
    return o


def prism(name, pts, width, material, x=0.0, bevel=0.0008, segs=2):
    """Extrude a side profile [(y, z), ...] across X, centred on `x`."""
    bm = bmesh.new()
    vs = [bm.verts.new((x - width / 2, y, z)) for y, z in pts]
    face = bm.faces.new(vs)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(width, 0, 0), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, material, bevel, segs)


def plan(name, pts, height, material, z=0.0, bevel=0.0008, segs=2):
    """Extrude a top-down outline [(x, y), ...] up Z, centred on `z`."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z - height / 2)) for x, y in pts]
    face = bm.faces.new(vs)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, height), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj(name, bm, material, bevel, segs)


def block(name, c, s, material, bevel=0.0008, segs=2, taper=None, rot=0.0):
    """Box at centre `c` with size `s`; `taper` scales the top face (x, y); `rot` tilts it about X (degrees)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    tilt = Matrix.Rotation(math.radians(rot), 3, "X")
    for v in bm.verts:
        if taper and v.co.z > 0:
            v.co.x *= taper[0]
            v.co.y *= taper[1]
        v.co = tilt @ Vector((v.co.x * s[0], v.co.y * s[1], v.co.z * s[2])) + Vector(c)
    return _obj(name, bm, material, bevel, segs)


def _orient(bm, p0, p1):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((p0 + p1) / 2) @ rot, verts=bm.verts)


def cyl(name, p0, p1, r, material, r1=None, segs=24, bevel=0.0005, bsegs=2):
    """Cylinder (or cone, with `r1`) from p0 to p1."""
    bm = bmesh.new()
    depth = (Vector(p1) - Vector(p0)).length
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r, radius2=r if r1 is None else r1, depth=depth)
    _orient(bm, p0, p1)
    return _obj(name, bm, material, bevel, bsegs)


def tube(name, p0, p1, r_out, r_in, material, segs=28, bevel=0.0004):
    """Hollow tube: a barrel you can see down."""
    bm = bmesh.new()
    depth = (Vector(p1) - Vector(p0)).length
    rings = []
    for z in (-depth / 2, depth / 2):
        for r in (r_out, r_in):
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / segs), r * math.sin(2 * math.pi * i / segs), z)) for i in range(segs)])
    o0, i0, o1, i1 = rings
    for i in range(segs):
        j = (i + 1) % segs
        bm.faces.new((o0[i], o0[j], o1[j], o1[i]))
        bm.faces.new((i0[j], i0[i], i1[i], i1[j]))
        bm.faces.new((o0[j], o0[i], i0[i], i0[j]))
        bm.faces.new((o1[i], o1[j], i1[j], i1[i]))
    _orient(bm, p0, p1)
    return _obj(name, bm, material, bevel, 2)


def ring(name, c, axis, r_out, r_in, width, material, segs=28):
    c, a = Vector(c), Vector(axis).normalized()
    return tube(name, c - a * width / 2, c + a * width / 2, r_out, r_in, material, segs)


def cut(target, *cutters, solver="EXACT"):
    """Boolean-subtract cutters (deleted afterwards). Several cutters are joined into one first."""
    if not cutters:
        return target
    cutter = join(list(cutters), "_cutter") if len(cutters) > 1 else cutters[0]
    mod = target.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = solver
    if solver == "EXACT":
        mod.use_self = True  # joined cutters may overlap (slot + rounded ends)
    mod.object = cutter
    _apply(target, mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def unite(target, *others):
    for other in others:
        mod = target.modifiers.new("unite", "BOOLEAN")
        mod.operation = "UNION"
        mod.solver = "EXACT"
        mod.object = other
        _apply(target, mod.name)
        bpy.data.objects.remove(other, do_unlink=True)
    return target


def _apply(obj, mod_name):
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod_name)


def join(objs, name):
    """Join parts into one object. Each part's own bevel is applied first, so a joined group keeps
    every member's edge treatment instead of re-bevelling everything with the first one's."""
    objs = [o for o in objs if o is not None]
    if len(objs) > 1 and name != "_cutter":
        for o in objs:
            apply_modifiers(o)
            o["bevel"] = 0.0
    if len(objs) == 1:
        objs[0].name = name
        return objs[0]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    objs[0].name = name
    return objs[0]


def apply_modifiers(obj):
    """Bevel the hard edges and harden the normals, then bake that into the mesh."""
    w = obj.get("bevel", 0.0)
    if w <= 0 and obj.type == "MESH" and not obj.get("shaded"):
        # No bevel: smooth only across soft angles, so boxes stay crisp and cylinders stay round.
        obj.data.set_sharp_from_angle(angle=math.radians(35))
    obj["shaded"] = True
    if w > 0:
        b = obj.modifiers.new("bevel", "BEVEL")
        b.width = w
        b.segments = obj.get("segs", 2)
        b.limit_method = "ANGLE"
        b.angle_limit = math.radians(35)
        b.harden_normals = True
        b.miter_outer = "MITER_ARC"
        b.use_clamp_overlap = True
        obj.modifiers.new("wn", "WEIGHTED_NORMAL").keep_sharp = True
    for m in list(obj.modifiers):
        _apply(obj, m.name)
    obj["bevel"] = 0.0  # applied once; a later join or finish must not bevel it again


# ---------------------------------------------------------------------------------- detail bits

def rail(name, y0, y1, z, material="black", x=0.0, flip=False, width=0.021):
    """Picatinny rail along Y with its teeth facing up (or down with `flip`)."""
    s = -1 if flip else 1
    parts = [block(name, (x, (y0 + y1) / 2, z + s * 0.002), (width * 0.8, y1 - y0, 0.004), material, bevel=0.0004)]
    n = int((y1 - y0) / 0.01)
    start = (y0 + y1) / 2 - (n - 1) * 0.005
    for i in range(n):
        parts.append(block(name, (x, start + i * 0.01, z + s * 0.0058), (width, 0.0052, 0.0036), material, bevel=0.0004,
                           taper=(0.82, 0.9) if not flip else None))
    return join(parts, name)


def screw(at, axis="x", r=0.0022, material="steel", head=0.0012):
    """A socket-head screw facing along +/-axis (`axis` like "x" or "-x")."""
    sgn = -1 if axis.startswith("-") else 1
    a = {"x": Vector((1, 0, 0)), "y": Vector((0, 1, 0)), "z": Vector((0, 0, 1))}[axis[-1]] * sgn
    at = Vector(at)
    s = cyl("screw", at - a * head / 2, at + a * head / 2, r, material, segs=10, bevel=0.0002)
    hexa = cyl("hex", at + a * (head / 2 - 0.0006), at + a * (head / 2 + 0.001), r * 0.45, material, segs=6, bevel=0)
    return cut(s, hexa, solver="FLOAT")


def pin(at, axis="x", r=0.0014, length=0.026, material="bright"):
    a = {"x": Vector((1, 0, 0)), "y": Vector((0, 1, 0)), "z": Vector((0, 0, 1))}[axis]
    at = Vector(at)
    return cyl("pin", at - a * length / 2, at + a * length / 2, r, material, segs=12, bevel=0.0002)


def slots(name, y0, y1, count, z0, z1, x0, x1, angle=0.0):
    """Cutters for serrations or grooves: `count` thin boxes between y0 and y1, tilted `angle` about X."""
    step = (y1 - y0) / max(1, count - 1)
    return [block(name, ((x0 + x1) / 2, y0 + i * step, (z0 + z1) / 2), (x1 - x0, step * 0.45, z1 - z0), "steel", bevel=0, rot=angle)
            for i in range(count)]


def mlok(name, y0, y1, count, z, x, depth=0.01, h=0.007):
    """Rounded M-LOK slot cutters along a handguard side at height z."""
    out = []
    step = (y1 - y0) / count
    for i in range(count):
        yc = y0 + step * (i + 0.5)
        L = step * 0.62
        out.append(block(name, (x, yc, z), (depth, L - h, h), "steel", bevel=0))
        out.append(cyl(name, (x - depth / 2, yc - (L - h) / 2, z), (x + depth / 2, yc - (L - h) / 2, z), h / 2, "steel", segs=12, bevel=0))
        out.append(cyl(name, (x - depth / 2, yc + (L - h) / 2, z), (x + depth / 2, yc + (L - h) / 2, z), h / 2, "steel", segs=12, bevel=0))
    return out


def dimples(name, y0, y1, z0, z1, x, nx, nz, r=0.0011, depth=0.002, side=-1):
    """Stippling: a staggered grid of shallow round cutters on a side face at `x`."""
    out = []
    for i in range(nx):
        for j in range(nz):
            y = y0 + (y1 - y0) * (i + (0.5 if j % 2 else 0.0)) / nx
            z = z0 + (z1 - z0) * j / max(1, nz - 1)
            out.append(cyl(name, (x - side * depth, y, z), (x + side * depth, y, z), r, "steel", segs=8, bevel=0))
    return out


def label(text, at, size, material, side=-1, depth=0.0003):
    """Raised lettering on a side face (left side by default), reading toward the muzzle's back."""
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = depth
    cu.resolution_u = 3  # small raised lettering: coarse curves are plenty
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    o = bpy.data.objects.new("label", cu)
    bpy.context.scene.collection.objects.link(o)
    o.location = at
    o.rotation_euler = (math.pi / 2, 0, -math.pi / 2 if side < 0 else math.pi / 2)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    mw = o.matrix_world.copy()
    bpy.data.objects.remove(o, do_unlink=True)
    me.transform(mw)
    me.materials.clear()
    me.materials.append(mat(material))
    out = bpy.data.objects.new("label", me)
    bpy.context.scene.collection.objects.link(out)
    out["bevel"] = 0.0
    return out


def hole_through(name, c, r, axis="x", length=0.06, segs=16):
    a = {"x": Vector((1, 0, 0)), "y": Vector((0, 1, 0)), "z": Vector((0, 0, 1))}[axis]
    c = Vector(c)
    return cyl(name, c - a * length / 2, c + a * length / 2, r, "steel", segs=segs, bevel=0)


# ---------------------------------------------------------------------------------- wear bake

def _loads(lib):
    try:
        ctypes.CDLL(lib)
        return True
    except OSError:
        return False


def bake_device():
    """("GPU", names) when Cycles finds a GPU (ONEAPI for Q's Arc first, then OPTIX, CUDA, HIP,
    METAL), else ("CPU", "CPU"). Never fails: a missing runtime just means the CPU. Only official
    Blender builds see the Arc; the pip bpy wheel lacks oneAPI's Level Zero adapter (tools/blender.sh).
    Probes on every call, since read_factory_settings resets the device preferences."""
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except (KeyError, AttributeError):
        return "CPU", "CPU"
    for kind in ("ONEAPI", "OPTIX", "CUDA", "HIP", "METAL"):
        try:
            prefs.compute_device_type = kind
            gpus = [d for d in prefs.get_devices_for_type(kind) if d.type != "CPU"]
        except (TypeError, AttributeError, RuntimeError):
            continue
        if gpus:
            for d in prefs.devices:
                d.use = d.type != "CPU"
            rt = ""
            if kind == "ONEAPI" and hasattr(prefs, "use_oneapirt"):
                # Embree on the GPU needs Intel's level-zero-raytracing-support library; without it
                # every bake fails, so trace in software instead.
                prefs.use_oneapirt = _loads("libze_intel_gpu_raytracing.so")
                rt = ", hardware ray tracing" if prefs.use_oneapirt else ", software ray tracing"
            return "GPU", f"GPU ({kind}: {', '.join(d.name for d in gpus)}{rt})"
    try:
        prefs.compute_device_type = "NONE"
    except TypeError:
        pass
    return "CPU", "CPU"


def bake_wear(gun, objs, scale=1.0):
    """Unwrap every part into one atlas and bake colour, edge wear and cavity dirt into it. `scale`
    grows the wear, dirt and occlusion sizes for bigger models (characters use 8)."""
    scene = gun.scene
    scene.render.engine = "CYCLES"
    device, used = (DEVICE, DEVICE) if DEVICE else bake_device()
    print(f"  wear bake on {used}")
    scene.cycles.device = device
    scene.cycles.samples = 12
    scene.cycles.use_denoising = False
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.003, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(margin=0.004, rotate=True)
    bpy.ops.object.mode_set(mode="OBJECT")

    img = bpy.data.images.new(f"{gun.id}_color", TEX, TEX, alpha=False)
    mats = {m for o in objs for m in o.data.materials if m is not None}
    for m in mats:
        _bake_tree(m, img, scale)
    scene.render.bake.margin = 6
    scene.render.bake.use_clear = True
    bpy.ops.object.bake(type="EMIT")
    tmp = os.path.join(bpy.app.tempdir or "/tmp", f"{gun.id}_color.png")
    img.filepath_raw = tmp
    img.file_format = "PNG"
    img.save()
    for m in mats:
        _final_tree(m, img)


def _bake_tree(m, img, scale=1.0):
    base, wear, _, _, amount, _ = PALETTE[m["kind"]]
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes.new
    L = nt.links.new
    out = N("ShaderNodeOutputMaterial")
    emit = N("ShaderNodeEmission")
    L(emit.outputs[0], out.inputs["Surface"])
    geo = N("ShaderNodeNewGeometry")
    bev = N("ShaderNodeBevel")
    bev.samples = 8
    bev.inputs["Radius"].default_value = 0.0012 * scale
    dot = N("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    L(bev.outputs[0], dot.inputs[0])
    L(geo.outputs["Normal"], dot.inputs[1])
    edge = N("ShaderNodeMapRange")
    edge.inputs["From Min"].default_value = 0.995
    edge.inputs["From Max"].default_value = 0.93
    L(dot.outputs["Value"], edge.inputs["Value"])
    noise = N("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 260.0 / scale
    noise.inputs["Detail"].default_value = 6.0
    L(geo.outputs["Position"], noise.inputs["Vector"])
    chip = N("ShaderNodeMath")
    chip.operation = "MULTIPLY"
    L(edge.outputs[0], chip.inputs[0])
    nmap = N("ShaderNodeMapRange")
    nmap.inputs["From Min"].default_value = 0.5
    nmap.inputs["From Max"].default_value = 0.66
    L(noise.outputs["Fac"], nmap.inputs["Value"])
    L(nmap.outputs[0], chip.inputs[1])
    amt = N("ShaderNodeMath")
    amt.operation = "MULTIPLY"
    amt.use_clamp = True
    amt.inputs[1].default_value = amount
    L(chip.outputs[0], amt.inputs[0])
    mix = N("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (*base, 1)
    mix.inputs[7].default_value = (*wear, 1)
    L(amt.outputs[0], mix.inputs[0])
    # Big soft blotches so flat panels are not one flat colour.
    grime = N("ShaderNodeTexNoise")
    grime.inputs["Scale"].default_value = 18.0 / scale
    grime.inputs["Detail"].default_value = 3.0
    L(geo.outputs["Position"], grime.inputs["Vector"])
    gmap = N("ShaderNodeMapRange")
    gmap.inputs["To Min"].default_value = 0.86
    gmap.inputs["To Max"].default_value = 1.06
    L(grime.outputs["Fac"], gmap.inputs["Value"])
    ao = N("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.012 * scale
    ao.samples = 8
    amap = N("ShaderNodeMapRange")
    amap.inputs["To Min"].default_value = 0.45
    L(ao.outputs["AO"], amap.inputs["Value"])
    shade = N("ShaderNodeMath")
    shade.operation = "MULTIPLY"
    L(gmap.outputs[0], shade.inputs[0])
    L(amap.outputs[0], shade.inputs[1])
    final = N("ShaderNodeMix")
    final.data_type = "RGBA"
    final.blend_type = "MULTIPLY"
    final.inputs[0].default_value = 1.0
    L(mix.outputs[2], final.inputs[6])
    L(shade.outputs[0], final.inputs[7])
    L(final.outputs[2], emit.inputs["Color"])
    tex = N("ShaderNodeTexImage")
    tex.image = img
    nt.nodes.active = tex


def _final_tree(m, img):
    _, _, metal, rough, _, emit = PALETTE[m["kind"]]
    base = PALETTE[m["kind"]][0]
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    if emit:
        bsdf.inputs["Base Color"].default_value = (*base, 1)
        bsdf.inputs["Emission Color"].default_value = (*base, 1)
        bsdf.inputs["Emission Strength"].default_value = emit
        return
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])


# ------------------------------------------------------------------------------------ preview

def preview(path, cam=(-0.55, 0.25, 0.22), look=(0, 0.05, 0.0), lens=50, res=(960, 600), show=()):
    """Render a look-dev image from the left, where the first-person camera sees the weapon. Gunsmith
    parts are hidden unless named in `show`."""
    scene = bpy.context.scene
    for o in bpy.data.objects:
        if o.name.startswith("att.") and o.name not in show:
            o.hide_render = True
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x, scene.render.resolution_y = res
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    cd.clip_start = 0.01
    c = bpy.data.objects.new("cam", cd)
    scene.collection.objects.link(c)
    c.location = cam
    c.rotation_euler = (Vector(look) - Vector(cam)).to_track_quat("-Z", "Y").to_euler()
    scene.camera = c
    for name, kind, energy, rot in (("key", "SUN", 3.5, (50, 0, -120)), ("rim", "SUN", 1.5, (60, 0, 60))):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        lo = bpy.data.objects.new(name, ld)
        lo.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(lo)
    scene.world = bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.44, 0.46, 1)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


# --------------------------------------------------------------------------------------- check

def read_glb(path):
    """The glTF JSON and binary chunk of a .glb, plus a reader for float accessors."""
    import json
    import struct
    data = open(path, "rb").read()
    jlen = struct.unpack("<I", data[12:16])[0]
    j = json.loads(data[20:20 + jlen])
    blob = data[20 + jlen + 8:]
    sizes = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def floats(index):
        acc = j["accessors"][index]
        view = j["bufferViews"][acc["bufferView"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        n = acc["count"] * sizes[acc["type"]]
        vals = struct.unpack_from(f"<{n}f", blob, start)
        k = sizes[acc["type"]]
        return [vals[i:i + k] for i in range(0, n, k)]
    return j, floats


def check(path, spec):
    """Verify a weapon's rig straight from the glb: bones, sockets, parts riding the right bones, clips
    that really move the bones they should, a sane length and triangle budget."""
    j, floats = read_glb(path)
    nodes = j["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    by_name = {}
    for i, n in enumerate(nodes):
        by_name.setdefault(n.get("name", ""), []).append(i)
    problems = []
    for name in spec["bones"] + spec["sockets"] + spec.get("attachments", []):
        if name not in by_name:
            problems.append(f"missing {name}")
    for name in by_name:
        if name.split(".")[-1].isdigit():
            problems.append(f"duplicate node name {name}")
    for part, bone in spec["parts"].items():
        if part not in by_name:
            problems.append(f"missing part {part}")
            continue
        p = parent.get(by_name[part][0])
        if p is None or nodes[p].get("name") != bone:
            problems.append(f"part {part} rides {nodes[p].get('name') if p is not None else None}, want {bone}")

    def tris(mesh):
        return sum(j["accessors"][p["indices"]]["count"] // 3 for p in j["meshes"][mesh]["primitives"])
    body = sum(tris(n["mesh"]) for n in nodes if "mesh" in n and not n["name"].startswith("att."))
    atts = sum(tris(n["mesh"]) for n in nodes if "mesh" in n and n["name"].startswith("att."))
    lo, hi = spec.get("tris", (4000, 90000))
    if not lo <= body <= hi:
        problems.append(f"{body} triangles, want {lo}..{hi}")
    # Length along the barrel: mesh bounds in glTF space, where -Z is forward.
    def world(i):
        m = _identity()
        while i is not None:
            n = nodes[i]
            m = _mul(_trs(n.get("translation", [0, 0, 0]), n.get("rotation", [0, 0, 0, 1])), m)
            i = parent.get(i)
        return m
    zs = []
    for i, n in enumerate(nodes):
        if "mesh" in n and not n["name"].startswith("att."):
            w = world(i)
            for p in j["meshes"][n["mesh"]]["primitives"]:
                acc = j["accessors"][p["attributes"]["POSITION"]]
                for c in range(8):
                    pt = [acc["max"][k] if c >> k & 1 else acc["min"][k] for k in range(3)]
                    zs.append(_xform(w, pt)[2])
    length = max(zs) - min(zs)
    lo, hi = spec["length"]
    if not lo <= length <= hi:
        problems.append(f"length {length:.3f} m, want {lo}..{hi}")
    if "muzzle" in by_name and spec.get("muzzle_front", True):
        mz = _xform(world(by_name["muzzle"][0]), [0, 0, 0])[2]
        if mz > min(zs) + 0.03:
            problems.append(f"muzzle {mz:.3f} sits behind the front {min(zs):.3f}")
    anims = {a["name"]: a for a in j.get("animations", [])}
    for clip, moving in spec["moves"].items():
        a = anims.get(clip)
        if a is None:
            problems.append(f"missing clip {clip}")
            continue
        moved = set()
        for ch in a["channels"]:
            if ch["target"]["path"] == "scale":
                continue
            out = floats(a["samplers"][ch["sampler"]]["output"])
            if any(max(v[k] for v in out) - min(v[k] for v in out) > 1e-4 for k in range(len(out[0]))):
                moved.add(nodes[ch["target"]["node"]].get("name"))
        for b in moving:
            if b not in moved:
                problems.append(f"clip {clip} never moves {b}")
    for clip in ("idle", "fire", "reload", "draw", "inspect"):
        if clip not in anims:
            problems.append(f"missing clip {clip}")
    return problems, {"tris": body, "att_tris": atts, "length": round(length, 3)}


def _identity():
    return [[float(i == k) for k in range(4)] for i in range(4)]


def _trs(t, q):
    x, y, z, w = q
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [r[0] + [t[0]], r[1] + [t[1]], r[2] + [t[2]], [0, 0, 0, 1]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _xform(m, p):
    return [sum(m[i][k] * p[k] for k in range(3)) + m[i][3] for i in range(3)]
