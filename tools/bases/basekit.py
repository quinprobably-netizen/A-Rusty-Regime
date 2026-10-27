"""Site kit for the faction bases, on top of the ship kit (`tools/ships/kit.py`) and its interior kit.

Blender frame as for the ships: +X right, +Y into the site, Z up, the front door on -Y, the origin
at ground level under the building's centre. Every part goes in a group that exports as one mesh:
`hull` (opaque, baked wear), `glass` and `lights` (emissive). Named empties the game looks for:
`lamp.<n>` (a warm point light a few metres across, indoors), `flood.<n>` (a cold floodlight,
outdoors). The SPEC of each base also carries its site and collision boxes, in this frame;
`write_toml` turns them into the game's frame (+X right, +Y up, door on +Z) for `assets/bases.toml`.
"""

import math
import os

import kit  # the ship kit: tools/ships is on sys.path
from kit import block, cyl, join, sphere, wk
from interior import grating
from mathutils import Vector

TRIS_MAX = 90000
TEX = 2048

wk.PALETTE.update({
    "concrete": ((0.42, 0.41, 0.39), (0.55, 0.54, 0.52), 0.0, 0.9, 0.35, 0),
    "canvas": ((0.36, 0.33, 0.26), (0.5, 0.47, 0.4), 0.0, 0.95, 0.2, 0),
    "ice_white": ((0.86, 0.88, 0.9), (0.7, 0.72, 0.75), 0.0, 0.4, 0.3, 0),
    "red_glass": ((0.45, 0.02, 0.02), (0.45, 0.02, 0.02), 0.0, 0.1, 0.0, 1.5),
    "flood": ((1.0, 0.98, 0.92), (1.0, 0.98, 0.92), 0.0, 0.3, 0.0, 8.0),
    "sand": ((0.55, 0.47, 0.33), (0.68, 0.6, 0.45), 0.0, 0.95, 0.3, 0),
})


class Base(kit.Ship):
    """One base being built: the ship class with a bigger texture and wear sized for a building."""

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
            wk.TEX = TEX
            wk.bake_wear(self, objs, scale=90.0)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{self.id}.glb")
        kit.bpy.ops.object.select_all(action="DESELECT")
        for o in kit.bpy.data.objects:
            o.select_set(True)
        kit.bpy.ops.export_scene.gltf(
            filepath=path, export_format="GLB", use_selection=True, export_apply=False, export_animations=False,
            export_skins=False, export_materials="EXPORT", export_image_format="JPEG", export_jpeg_quality=85, export_yup=True,
        )
        tris = sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons)
        print(f"wrote {path}: {os.path.getsize(path) // 1024} KB, {tris} tris, {len(objs)} meshes, {len(self.nodes)} nodes")
        return path


# ---------------------------------------------------------------------------------- structures

FACES = {"-y": (0, -1), "+y": (0, 1), "-x": (-1, 0), "+x": (1, 0)}


def hall(base, name, c, s, material, wall=0.3, openings=(), bevel=0.05, segs=2, roof=True):
    """A hollow building: the outer block minus its cavity, with doorways and windows cut through
    any face. Each opening is (face, offset along the face, width, height, bottom above the floor).
    Without `roof` the cavity opens upward (a yard, a shed with a separate roof)."""
    x, y, z = c
    sx, sy, sz = s
    outer = block(name, c, s, material, bevel=bevel, segs=segs)
    cav_h = sz - 2 * wall + (sz if not roof else 0)
    cav_z = z if roof else z + sz / 2
    cutters = [block("cavity", (x, y, cav_z), (sx - 2 * wall, sy - 2 * wall, cav_h), material, bevel=0)]
    floor = z - sz / 2 + wall
    for face, off, w, h, z0 in openings:
        fx, fy = FACES[face]
        if fy:
            cutters.append(block("opening", (x + off, y + fy * sy / 2, floor + z0 + h / 2), (w, wall * 4, h), material, bevel=0))
        else:
            cutters.append(block("opening", (x + fx * sx / 2, y + off, floor + z0 + h / 2), (wall * 4, w, h), material, bevel=0))
    outer = kit.cut(outer, *cutters)
    base.add(outer)
    return outer


def room(base, name, c, s, material, doors, wall=0.15, trim="gunmetal", windows=()):
    """A small standalone building on the ground: `c` is its centre (x, y), `s` its size (x, y,
    height), `doors` are (face, offset, width, height) doorways, framed and cut through the wall;
    `windows` are (face, offset, width, height, bottom) holes for the caller to glaze.
    The floor's top is `wall` above the ground. Its collision boxes come from `room_boxes`."""
    x, y = c
    hall(base, name, (x, y, s[2] / 2), s, material, wall=wall, openings=[(f, off, w, h, 0) for f, off, w, h in doors] + list(windows), bevel=0.03)
    base.add(block(name + "cap", (x, y, s[2] + 0.05), (s[0] + 0.3, s[1] + 0.3, 0.1), trim, bevel=0.02))
    base.add(block(name + "plinth", (x, y, 0.06), (s[0] + 0.2, s[1] + 0.2, 0.12), "concrete", bevel=0.01))
    for face, off, w, h in doors:
        fx, fy = FACES[face]
        t, d = 0.15, 0.4
        if fy:
            px, py = x + off, y + fy * s[1] / 2
            for sx in (-1, 1):
                base.add(block("jamb", (px + sx * (w / 2 + t / 2), py, wall + h / 2), (t, d, h + t), trim, bevel=0.02))
            base.add(block("lintel", (px, py, wall + h + t / 2), (w + 2 * t, d, t), trim, bevel=0.02))
        else:
            px, py = x + fx * s[0] / 2, y + off
            for sy in (-1, 1):
                base.add(block("jamb", (px, py + sy * (w / 2 + t / 2), wall + h / 2), (d, t, h + t), trim, bevel=0.02))
            base.add(block("lintel", (px, py, wall + h + t / 2), (d, w + 2 * t, t), trim, bevel=0.02))


def room_boxes(name, c, s, doors, wall=0.15):
    """The collision boxes of a `room`: its floor, roof and walls, with the doorways left open."""
    x, y = c
    out = [box(f"{name} floor", (x, y, wall / 2), (s[0], s[1], wall)), box(f"{name} roof", (x, y, s[2] - wall / 2), (s[0], s[1], wall))]
    for face, (fx, fy) in FACES.items():
        length = s[0] if fy else s[1]
        spans, cur = [], -length / 2
        for off, w, h in sorted((o, w, h) for f, o, w, h in doors if f == face):
            spans += [(cur, off - w / 2, 0.0, s[2]), (off - w / 2, off + w / 2, wall + h, s[2])]
            cur = off + w / 2
        spans.append((cur, length / 2, 0.0, s[2]))
        for a, b, z0, z1 in spans:
            if b - a < 0.01 or z1 - z0 < 0.01:
                continue
            size = (b - a, wall, z1 - z0) if fy else (wall, b - a, z1 - z0)
            centre = (x + (a + b) / 2, y + fy * (s[1] / 2 - wall / 2), (z0 + z1) / 2) if fy else (x + fx * (s[0] / 2 - wall / 2), y + (a + b) / 2, (z0 + z1) / 2)
            out.append(box(f"{name} wall", centre, size))
    return out


def band(base, c, s, z, h, material, proud=0.015, front_gap=0.0):
    """A painted band round the outside of a hollow block `c`, `s`: four thin strips at height `z`.
    `front_gap` leaves the middle of the front (-Y) strip out, for a doorway."""
    x, y, _ = c
    sx, sy, _ = s
    for f in (-1, 1):
        if f < 0 and front_gap:
            w = (sx - front_gap) / 2
            for g in (-1, 1):
                base.add(block("band", (x + g * (front_gap / 2 + w / 2), y - (sy / 2 + proud / 2), z), (w + proud, proud, h), material, bevel=0))
        else:
            base.add(block("band", (x, y + f * (sy / 2 + proud / 2), z), (sx + proud, proud, h), material, bevel=0))
        base.add(block("band", (x + f * (sx / 2 + proud / 2), y, z), (proud, sy + proud, h), material, bevel=0))


def column(base, c, r, h, material="bone", trim="gold", segs=16):
    """A round column from `c` (floor) up `h`, with a ring at each end."""
    x, y, z = c
    base.add(cyl("column", (x, y, z), (x, y, z + h), r, material, segs=segs, bevel=0.01))
    for zz in (z + 0.15, z + h - 0.3):
        base.add(cyl("ring", (x, y, zz), (x, y, zz + 0.15), r + 0.08, trim, segs=segs, bevel=0.005))


def slab(base, name, c, s, material, bevel=0.03):
    return base.add(block(name, c, s, material, bevel=bevel))


def door_frame(base, c, w, h, material="gunmetal", depth=0.4, thick=0.2, facing=-1):
    """Jambs and a lintel round a doorway centred at `c` (floor level) in a wall facing `facing` Y."""
    x, y, z = c
    for sx in (-1, 1):
        base.add(block("jamb", (x + sx * (w / 2 + thick / 2), y, z + h / 2), (thick, depth, h + thick), material, bevel=0.02))
    base.add(block("lintel", (x, y, z + h + thick / 2), (w + 2 * thick, depth, thick), material, bevel=0.02))


def stair(base, foot, width, run, rise, steps, material="gunmetal", facing=1, stringers=True):
    """Steps rising from `foot` (the bottom front edge's centre, floor level) along `facing` Y:
    `run` long and `rise` high over `steps` treads, with a stringer each side."""
    x, y, z = foot
    f = facing
    tread, riser = run / steps, rise / steps
    for i in range(steps):
        base.add(block("step", (x, y + f * (i + 0.5) * tread, z + (i + 0.5) * riser + riser / 2 - 0.02), (width, tread, riser + 0.04), material, bevel=0.01))
    if stringers:
        a = math.degrees(math.atan2(rise, run))
        length = math.hypot(run, rise)
        for sx in (-1, 1):
            base.add(block("stringer", (x + sx * (width / 2 + 0.03), y + f * run / 2, z + rise / 2 - 0.05), (0.06, length, 0.3), "black", bevel=0, rot=f * a))


def slope(foot, width, run, rise, facing=1, thick=0.2):
    """The collision box for a `stair` with the same arguments: a slab through the step nosings."""
    x, y, z = foot
    a = math.degrees(math.atan2(rise, run))
    return ("stair", (x, y + facing * run / 2, z + rise / 2 - thick / 2 + 0.08), (width, math.hypot(run, rise), thick), (facing * a, 0, 0))


def railing(base, p0, p1, h=1.05, r=0.025, material="steel", spacing=1.5, mid=True):
    """A guard rail from p0 to p1 (floor points): posts every `spacing`, a top rail and a mid rail."""
    a, b = Vector(p0), Vector(p1)
    parts = [cyl("rail", a + Vector((0, 0, h)), b + Vector((0, 0, h)), r, material, segs=8, bevel=0)]
    if mid:
        parts.append(cyl("midrail", a + Vector((0, 0, h * 0.55)), b + Vector((0, 0, h * 0.55)), r * 0.8, material, segs=8, bevel=0))
    n = max(2, int((b - a).length / spacing) + 1)
    for i in range(n):
        p = a.lerp(b, i / (n - 1))
        parts.append(cyl("post", p, p + Vector((0, 0, h)), r * 1.2, material, segs=8, bevel=0))
    return base.add(join(parts, "railing"))


def catwalk(base, c, s, material="gunmetal", rails=("-y", "+y"), rail_mat="steel"):
    """A grating deck with rails on the faces named (the others meet walls or stairs)."""
    x, y, z = c
    sx, sy, sz = s
    grating(base, (x, y, z + sz / 2 - 0.03), (sx, sy), material=material, pitch=0.2)
    base.add(block("deckframe", (x, y, z), (sx, sy, sz), "black", bevel=0.01))
    top = z + sz / 2
    for face in rails:
        fx, fy = FACES[face]
        if fy:
            railing(base, (x - sx / 2, y + fy * (sy / 2 - 0.05), top), (x + sx / 2, y + fy * (sy / 2 - 0.05), top), material=rail_mat)
        else:
            railing(base, (x + fx * (sx / 2 - 0.05), y - sy / 2, top), (x + fx * (sx / 2 - 0.05), y + sy / 2, top), material=rail_mat)


def ladder(base, foot, h, material="steel", w=0.5, facing=-1):
    """A wall ladder up from `foot`, rungs toward `facing` Y."""
    x, y, z = foot
    parts = []
    for sx in (-1, 1):
        parts.append(cyl("rail", (x + sx * w / 2, y, z), (x + sx * w / 2, y, z + h), 0.025, material, segs=8, bevel=0))
    n = int(h / 0.3)
    for i in range(n):
        zz = z + (i + 0.5) * h / n
        parts.append(cyl("rung", (x - w / 2, y, zz), (x + w / 2, y, zz), 0.018, material, segs=6, bevel=0))
    return base.add(join(parts, "ladder"))


def container(base, c, s, material="rust", band=None, ribs=0.6, doors="-y"):
    """A shipping container: a box with corrugation ribs on its long sides, locking bars on the
    door end and an optional painted band round it."""
    x, y, z = c
    sx, sy, sz = s
    parts = [block("box", c, s, material, bevel=0.03)]
    n = int(sy / ribs)
    for i in range(n):
        yy = y - sy / 2 + (i + 0.5) * sy / n
        for side in (-1, 1):
            parts.append(block("rib", (x + side * (sx / 2 + 0.015), yy, z), (0.03, ribs * 0.35, sz - 0.3), material, bevel=0))
    for sx_ in (-1, 1):
        parts.append(block("corner", (x + sx_ * (sx / 2 - 0.08), y - sy / 2 - 0.02, z), (0.16, 0.06, sz), "black", bevel=0))
        parts.append(block("corner", (x + sx_ * (sx / 2 - 0.08), y + sy / 2 + 0.02, z), (0.16, 0.06, sz), "black", bevel=0))
    fy = -1 if doors == "-y" else 1
    for bx in (-0.35, -0.15, 0.15, 0.35):
        parts.append(cyl("bar", (x + bx * sx, y + fy * (sy / 2 + 0.05), z - sz / 2 + 0.2), (x + bx * sx, y + fy * (sy / 2 + 0.05), z + sz / 2 - 0.2), 0.03, "steel", segs=8, bevel=0))
    if band:
        parts.append(block("band", (x, y, z + sz * 0.1), (sx + 0.05, sy + 0.05, 0.3), band, bevel=0))
    return base.add(join(parts, "container"))


def mast(base, c, h, r=0.08, material="steel", arms=3, light=None):
    """A guyed radio mast: a pole with cross arms and, with `light`, a nav sphere at the top."""
    x, y, z = c
    parts = [cyl("mast", (x, y, z), (x, y, z + h), r, material, segs=10, bevel=0)]
    for i in range(arms):
        zz = z + h * (0.5 + 0.45 * i / max(1, arms - 1))
        parts.append(cyl("arm", (x - 0.6, y, zz), (x + 0.6, y, zz), r * 0.4, material, segs=6, bevel=0))
        parts.append(cyl("arm", (x, y - 0.6, zz), (x, y + 0.6, zz), r * 0.4, material, segs=6, bevel=0))
    base.add(join(parts, "mast"))
    if light:
        base.add(sphere("nav", (x, y, z + h + 0.1), 0.12, light, segs=10), "lights")


def floodlight(base, name, c, h, aim=(0, -1), material="gunmetal"):
    """A floodlight on a pole: the head leans toward `aim`, its lit face in the lights group and a
    `flood.<n>` empty where the game puts the light."""
    x, y, z = c
    ax, ay = aim
    parts = [cyl("pole", (x, y, z), (x, y, z + h), 0.07, material, segs=10, bevel=0),
             block("head", (x + ax * 0.3, y + ay * 0.3, z + h), (0.5 if ay else 0.25, 0.25 if ay else 0.5, 0.4), material, bevel=0.02),
             cyl("bracket", (x, y, z + h - 0.1), (x + ax * 0.3, y + ay * 0.3, z + h - 0.1), 0.03, material, segs=6, bevel=0)]
    base.add(join(parts, "flood"))
    base.add(block("face", (x + ax * 0.44, y + ay * 0.44, z + h), (0.42 if ay else 0.04, 0.04 if ay else 0.42, 0.32), "flood", bevel=0), "lights")
    base.node(name, (x + ax * 0.7, y + ay * 0.7, z + h - 0.3))


def sandbags(base, c, w, rows=3, material="sand", facing=-1):
    """A sandbag parapet `w` wide along X, `rows` courses high, bags staggered."""
    x, y, z = c
    parts = []
    n = max(1, int(w / 0.55))
    for r in range(rows):
        for i in range(n):
            xx = x - w / 2 + (i + 0.5 + (0.5 if r % 2 else 0)) * w / n
            if xx > x + w / 2:
                continue
            parts.append(block("bag", (xx, y, z + 0.12 + r * 0.22), (0.52, 0.34, 0.22), material, bevel=0.07, segs=3))
    return base.add(join(parts, "sandbags"))


def tank(base, c, r, h, material="steel", legs=4, band=None, ground=0.0):
    """A storage tank on legs: a drum with a domed top, a pipe stub, legs down to `ground`."""
    x, y, z = c
    parts = [cyl("drum", (x, y, z), (x, y, z + h), r, material, segs=24, bevel=0.02),
             sphere("dome", (x, y, z + h - r * 0.3), r * 0.98, material, segs=16),
             cyl("stub", (x + r, y, z + 0.3), (x + r + 0.5, y, z + 0.3), 0.06, "black", segs=8, bevel=0)]
    for i in range(legs):
        a = i / legs * math.tau
        lx, ly = x + math.cos(a) * r * 0.8, y + math.sin(a) * r * 0.8
        parts.append(block("leg", (lx, ly, (z + ground) / 2 - 0.02), (0.12, 0.12, z - ground + 0.04), "black", bevel=0))
    if band:
        parts.append(cyl("band", (x, y, z + h * 0.5), (x, y, z + h * 0.5 + 0.3), r + 0.02, band, segs=24, bevel=0))
    return base.add(join(parts, "tank"))


def dish(base, c, r, h, material="white", facing=-1):
    """A radar dish on a pedestal, tilted up and toward `facing` Y."""
    x, y, z = c
    parts = [cyl("pedestal", (x, y, z), (x, y, z + h), 0.18, "gunmetal", segs=12, bevel=0.01),
             block("yoke", (x, y, z + h + 0.2), (0.5, 0.3, 0.4), "gunmetal", bevel=0.02)]
    tilt = Vector((0, facing * 0.5, 0.86)).normalized()
    centre = Vector((x, y, z + h + 0.5))
    parts.append(cyl("dish", centre - tilt * 0.1, centre + tilt * 0.35, r * 0.2, material, r1=r, segs=24, bevel=0.01))
    parts.append(cyl("feed", centre + tilt * 0.3, centre + tilt * (r * 0.9), 0.03, "black", segs=6, bevel=0))
    parts.append(sphere("horn", centre + tilt * (r * 0.9), 0.08, "black", segs=8))
    return base.add(join(parts, "dish"))


def truss(base, p0, p1, s=0.5, material="steel", bay=1.0):
    """A box-section lattice beam from p0 to p1: four chords and diagonals in every bay."""
    a, b = Vector(p0), Vector(p1)
    d = b - a
    n = max(1, int(d.length / bay))
    up = Vector((0, 0, 1))
    side = d.normalized().cross(up).normalized() if abs(d.normalized().z) < 0.99 else Vector((1, 0, 0))
    parts = []
    for u in (-1, 1):
        for v in (-1, 1):
            off = side * u * s / 2 + up * v * s / 2
            parts.append(cyl("chord", a + off, b + off, 0.03, material, segs=6, bevel=0))
    for i in range(n):
        q0, q1 = a + d * (i / n), a + d * ((i + 1) / n)
        for u in (-1, 1):
            parts.append(cyl("diag", q0 + side * u * s / 2 - up * s / 2, q1 + side * u * s / 2 + up * s / 2, 0.02, material, segs=5, bevel=0))
            parts.append(cyl("vert", q1 + side * u * s / 2 - up * s / 2, q1 + side * u * s / 2 + up * s / 2, 0.02, material, segs=5, bevel=0))
        for v in (-1, 1):
            parts.append(cyl("diag", q0 - side * s / 2 + up * v * s / 2, q1 + side * s / 2 + up * v * s / 2, 0.02, material, segs=5, bevel=0))
    return base.add(join(parts, "truss"))


def window(base, c, s, frame="gunmetal", glass="glass", bars=0):
    """A window: a glass pane in a proud frame, optional vertical bars."""
    x, y, z = c
    sx, sy, sz = s
    base.add(block("pane", c, s, glass, bevel=0), "glass")
    thin = min(sx, sy)
    if sy < sx:
        base.add(block("frame", (x, y, z + sz / 2 + 0.04), (sx + 0.16, thin + 0.08, 0.08), frame, bevel=0.01))
        base.add(block("frame", (x, y, z - sz / 2 - 0.04), (sx + 0.16, thin + 0.08, 0.08), frame, bevel=0.01))
        for sx_ in (-1, 1):
            base.add(block("frame", (x + sx_ * (sx / 2 + 0.04), y, z), (0.08, thin + 0.08, sz), frame, bevel=0.01))
        for i in range(bars):
            base.add(block("bar", (x - sx / 2 + (i + 1) * sx / (bars + 1), y, z), (0.05, thin + 0.1, sz), frame, bevel=0))
    else:
        base.add(block("frame", (x, y, z + sz / 2 + 0.04), (thin + 0.08, sy + 0.16, 0.08), frame, bevel=0.01))
        base.add(block("frame", (x, y, z - sz / 2 - 0.04), (thin + 0.08, sy + 0.16, 0.08), frame, bevel=0.01))
        for sy_ in (-1, 1):
            base.add(block("frame", (x, y + sy_ * (sy / 2 + 0.04), z), (thin + 0.08, 0.08, sz), frame, bevel=0.01))
        for i in range(bars):
            base.add(block("bar", (x, y - sy / 2 + (i + 1) * sy / (bars + 1), z), (thin + 0.1, 0.05, sz), frame, bevel=0))


def wall_lamp(base, name, c, material="lamp", rim="gunmetal"):
    """A caged bulkhead light on a wall, and its `lamp.<n>` empty."""
    x, y, z = c
    base.add(cyl("lampbase", (x, y, z), (x, y + 0.1, z), 0.12, rim, segs=12, bevel=0.005))
    base.add(sphere("bulb", (x, y + 0.12, z), 0.07, material, segs=10), "lights")
    base.node(name, (x, y + 0.3, z))


def box(name, c, s, rot=(0, 0, 0)):
    """A collision box for a SPEC, in the Blender frame."""
    return (name, tuple(c), tuple(s), tuple(rot))


# ------------------------------------------------------------------------------------- check

def check(path, spec):
    """The ship checker with the base budget: triangles, size, nodes, meshes, and the lowest
    vertex at `depth` below ground level."""
    kit.TRIS_MAX = TRIS_MAX
    return kit.check(path, {"size": spec["size"], "rest": spec["depth"], "nodes": spec["nodes"]})


preview = kit.preview


# -------------------------------------------------------------------------------------- toml

def _game(p):
    """A Blender point or size to the game's frame: (x, y, z) -> (x, z, -y)."""
    return (p[0], p[2], -p[1])


def _fmt(v):
    return ", ".join(f"{x:g}" for x in v)


def write_toml(path, specs):
    """`assets/bases.toml` from the SPECs: everything the game needs, in its own frame."""
    lines = [
        "# The faction bases: where each stands, its landing pad, its doorway and its collision boxes,",
        "# for `models/bases/<id>.glb` (built by tools/bases). GENERATED by `tools/bases/build.sh --toml`",
        "# from the SPEC in `tools/bases/bases/<id>.py`: edit that, not this. Frame: +X right, +Y up,",
        "# the front door on +Z; metres. `footprint` is the buried foundation slab (x, z) whose top is",
        "# the ground the base stands on; `pad` is the landing pad's centre (x, z) in the base frame, if",
        "# the base has its own; `near_pad` places a base in Haven's pad frame (x, z), otherwise `lat`",
        "# and `lon` (degrees) are snapped to the flattest ground near there on `body`; `yaw` turns the",
        "# base on its site (degrees, 0 = door to the south). `door` is a",
        "# point in the doorway, for the tests. `color` is the faction's waypoint and beam colour (rgb). Hulls are hollow: the boxes are the floors, walls, roofs",
        "# and stairs (`rot` in degrees) the player walks between; fittings do not collide.",
        "",
    ]
    for bid, s in specs:
        lines += [f"[[base]]", f'id = "{bid}"', f'name = "{s["name"]}"', f'faction = "{s["faction"]}"', f'body = "{s["body"]}"', f"color = [{_fmt(s['color'])}]"]
        if "near_pad" in s:
            lines.append(f"near_pad = [{_fmt(s['near_pad'])}]")
        else:
            lines += [f"lat = {s['lat']:g}", f"lon = {s['lon']:g}"]
        if s.get("yaw"):
            lines.append(f"yaw = {s['yaw']:g}")
        lines.append(f"footprint = [{_fmt(s['footprint'])}]")
        if "footprint_at" in s:
            fx, fy = s["footprint_at"]
            lines.append(f"footprint_at = [{_fmt((fx, -fy))}]")
        if "pad" in s:
            px, py = s["pad"]
            lines.append(f"pad = [{_fmt((px, -py))}]")
        lines.append(f"door = [{_fmt(_game(s['door']))}]")
        lines.append("collider = [")
        for name, c, sz, rot in s["boxes"]:
            gc, gs = _game(c), (sz[0], sz[2], sz[1])
            entry = f"    {{ center = [{_fmt(gc)}], size = [{_fmt(gs)}]"
            if any(rot):
                entry += f", rot = [{_fmt((rot[0], rot[2], -rot[1]))}]"
            lines.append(entry + f" }},  # {name}")
        lines += ["]"]
        for kind, c, label in s.get("stations", []):
            lines.append(f'[[base.stations]]\nkind = "{kind}"\nat = [{_fmt(_game(c))}]\nlabel = "{label}"')
        lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {path}")
