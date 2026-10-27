"""Interior kit: the fittings inside the faction ships' cabins, built from the same primitives as
the hulls. Blender frame: +Y nose, Z up, X right. Helpers that return one object go in the hull
group with `ship.add`; helpers that take `ship` add their own parts (lit bits go in `lights`).
`facing=1` faces the nose (+Y); `turn(obj, c, yaw)` swings a finished object round Z about `c`.
"""

import math

from kit import block, cyl, join, label, prism, ring, rivets, seams, side_plate, sphere, tube
from mathutils import Matrix, Vector


def turn(obj, c, yaw):
    """Rotate `obj` about Z by `yaw` degrees around the point `c`."""
    t = Matrix.Translation(Vector(c))
    obj.data.transform(t @ Matrix.Rotation(math.radians(yaw), 4, "Z") @ t.inverted())
    return obj


# --------------------------------------------------------------------------------------- seats

def bucket_seat(name, c, facing=1, material="black", frame="gunmetal", trim=None, w=0.56, harness=True):
    """A flight seat: bolstered cushion, raked back with wings and a headrest, armrests, a
    pedestal on a round base, and a four-point harness."""
    x, y, z = c
    f = facing
    trim = trim or frame
    rake = f * 12
    parts = [block(name, (x, y, z), (w, 0.52, 0.14), material, bevel=0.05, segs=3),
             block("back", (x, y - f * 0.29, z + 0.44), (w, 0.1, 0.8), material, bevel=0.04, segs=3, rot=rake),
             block("head", (x, y - f * 0.38, z + 0.98), (0.32, 0.1, 0.2), material, bevel=0.04, rot=rake),
             cyl("ped", (x, y, z - 0.07), (x, y, z - 0.42), 0.07, frame, segs=12, bevel=0.005),
             cyl("base", (x, y, z - 0.42), (x, y, z - 0.46), 0.26, frame, segs=16, bevel=0.005),
             block("buckle", (x, y + f * 0.05, z + 0.09), (0.12, 0.07, 0.04), "steel", bevel=0.005)]
    for sx in (-1, 1):
        parts.append(block("bolster", (x + sx * (w / 2 - 0.06), y - f * 0.02, z + 0.07), (0.12, 0.42, 0.1), material, bevel=0.03))
        parts.append(block("wing", (x + sx * (w / 2 - 0.05), y - f * 0.33, z + 0.5), (0.1, 0.13, 0.62), material, bevel=0.03, rot=rake))
        parts.append(block("arm", (x + sx * (w / 2 + 0.06), y - f * 0.04, z + 0.31), (0.08, 0.38, 0.05), trim, bevel=0.01))
        parts.append(cyl("armpost", (x + sx * (w / 2 + 0.06), y - f * 0.18, z + 0.29), (x + sx * (w / 2 + 0.06), y - f * 0.18, z + 0.02), 0.02, frame, segs=8, bevel=0))
        if harness:
            parts.append(block("strap", (x + sx * 0.12, y - f * 0.225, z + 0.5), (0.06, 0.015, 0.78), "black", bevel=0, rot=rake))
    return join(parts, name)


def jump_seat(name, c, facing=1, material="olive", frame="gunmetal"):
    """A fold-down troop seat on a wall bracket: cushion on two struts, a back pad behind,
    tube frame and straps. The wall is on the -facing side."""
    x, y, z = c
    f = facing
    parts = [block(name, (x, y, z), (0.5, 0.42, 0.09), material, bevel=0.03, segs=3),
             block("pad", (x, y - f * 0.24, z + 0.4), (0.46, 0.06, 0.55), material, bevel=0.03),
             block("bracket", (x, y - f * 0.2, z - 0.05), (0.42, 0.06, 0.04), frame, bevel=0.005)]
    for sx in (-1, 1):
        parts.append(cyl("tube", (x + sx * 0.25, y + f * 0.2, z - 0.03), (x + sx * 0.25, y - f * 0.22, z - 0.03), 0.018, frame, segs=8, bevel=0))
        parts.append(cyl("strut", (x + sx * 0.2, y + f * 0.18, z - 0.05), (x + sx * 0.2, y - f * 0.22, z - 0.42), 0.015, frame, segs=6, bevel=0))
        parts.append(block("strap", (x + sx * 0.1, y - f * 0.2, z + 0.42), (0.05, 0.012, 0.55), "black", bevel=0))
    return join(parts, name)


def pew(name, c, w=0.9, facing=1, material="leather", frame="gold", wood="slate"):
    """A church pew: bench and raked back between two carved end panels, a kneeler and a rail."""
    x, y, z = c
    f = facing
    pts = [(-0.26, -0.45), (0.3, -0.45), (0.3, 0.02), (0.14, 0.05), (0.1, 0.42), (-0.06, 0.6), (-0.3, 0.64), (-0.3, 0.3), (-0.22, 0.26), (-0.26, -0.1)]
    parts = [block(name, (x, y, z), (w, 0.48, 0.07), material, bevel=0.025, segs=3),
             block("back", (x, y - f * 0.24, z + 0.34), (w, 0.06, 0.6), material, bevel=0.025, rot=f * 8),
             block("rail", (x, y - f * 0.3, z + 0.64), (w + 0.08, 0.06, 0.04), frame, bevel=0.01),
             block("kneel", (x, y + f * 0.45, z - 0.35), (w - 0.1, 0.22, 0.05), material, bevel=0.02),
             block("shelf", (x, y + f * 0.38, z + 0.3), (w - 0.1, 0.1, 0.03), wood, bevel=0.005)]
    for sx in (-1, 1):
        parts.append(prism("end", [(y + f * py, z + pz) for py, pz in pts], 0.06, wood, x=x + sx * (w / 2 + 0.03), bevel=0.008))
        parts.append(block("endtrim", (x + sx * (w / 2 + 0.03), y - f * 0.2, z + 0.62), (0.07, 0.2, 0.04), frame, bevel=0.005))
    return join(parts, name)


# ------------------------------------------------------------------------------------- consoles

def dash(ship, c, w, material="gunmetal", screens=3, screen_mat="screen", facing=1, depth=0.7, trim="black", buttons=True):
    """A flight console at `c` (its floor-level centre): a kick plate, a flat desk with switch
    rows and a keyboard, and a raked bank of bezelled screens. Its face is toward -facing."""
    x, y, z0 = c
    f = facing
    y0, y1 = y - f * depth / 2, y + f * depth / 2  # pilot's edge, far edge
    desk_z, bank_z = z0 + 0.78, z0 + 1.22
    profile = [(y0, z0), (y1, z0), (y1, bank_z), (y0 + f * 0.42, z0 + 1.0), (y0 + f * 0.32, desk_z + 0.02), (y0, desk_z)]
    ship.add(prism("console", profile, w, material, bevel=0.02))
    ship.add(block("kick", (x, y0 + f * 0.03, z0 + 0.2), (w - 0.1, 0.03, 0.3), trim, bevel=0.005))
    ship.add(block("lip", (x, y0 + f * 0.01, desk_z + 0.02), (w, 0.03, 0.04), trim, bevel=0.005))
    # The screen bank slopes from (y0+0.42, 1.0) up to (y1, 1.22): tilt the screens to lie on it.
    run, rise = depth - 0.42, bank_z - (z0 + 1.0)
    tilt = -f * math.degrees(math.atan2(rise, run)) + f * 90
    sw = (w - 0.08 * (screens + 1)) / screens
    for i in range(screens):
        sx = x - w / 2 + 0.08 + sw / 2 + i * (sw + 0.08)
        t = 0.5
        py, pz = y0 + f * (0.42 + run * t), z0 + 1.0 + rise * t
        ship.add(block("bezel", (sx, py - f * 0.02, pz), (sw, 0.03, 0.44), trim, bevel=0.005, rot=tilt))
        ship.add(block("screen", (sx, py - f * 0.036, pz), (sw - 0.05, 0.01, 0.36), screen_mat, bevel=0, rot=tilt), "lights")
    if buttons:
        n = max(3, int((w - 0.5) / 0.09))
        for i in range(n):
            bx = x - (n - 1) * 0.045 + i * 0.09
            on = (i * 7) % 3 == 0
            ship.add(cyl("btn", (bx, y0 + f * 0.1, desk_z), (bx, y0 + f * 0.1, desk_z + 0.02), 0.025, "lights_amber" if on else "black", segs=8, bevel=0), "lights" if on else "hull")
            if i % 2:
                ship.add(cyl("toggle", (bx, y0 + f * 0.2, desk_z), (bx, y0 + f * 0.2 - f * 0.02, desk_z + 0.05), 0.008, "steel", segs=6, bevel=0))
        ship.add(block("keys", (x, y0 + f * 0.17, desk_z + 0.012), (0.42, 0.14, 0.024), trim, bevel=0.004))
        seams(ship, (x, y0 + f * 0.17, desk_z + 0.012), (0.42, 0.14, 0.024), ys=(-0.03, 0.03), xs=(-0.1, 0.0, 0.1), material="grey", width=0.008, proud=0.004)
    return None


def controls(ship, c, facing=1, frame="black", grip="steel"):
    """A flight stick and a throttle quadrant on a plinth between the pilot's knees."""
    x, y, z = c
    f = facing
    ship.add(block("plinth", (x, y, z + 0.17), (0.5, 0.3, 0.34), frame, bevel=0.01))
    ship.add(cyl("stick", (x + 0.1, y, z + 0.34), (x + 0.1, y + f * 0.04, z + 0.68), 0.022, grip, segs=8, bevel=0))
    ship.add(block("grip", (x + 0.1, y + f * 0.04, z + 0.74), (0.06, 0.07, 0.16), frame, bevel=0.015, rot=f * -10))
    ship.add(cyl("trigger", (x + 0.1, y + f * 0.07, z + 0.72), (x + 0.1, y + f * 0.09, z + 0.72), 0.012, "red", segs=6, bevel=0))
    ship.add(block("slot", (x - 0.12, y, z + 0.345), (0.04, 0.22, 0.01), "black", bevel=0))
    ship.add(block("throttle", (x - 0.12, y - f * 0.04, z + 0.42), (0.03, 0.03, 0.14), grip, bevel=0, rot=f * 20))
    ship.add(block("knob", (x - 0.12, y - f * 0.07, z + 0.5), (0.07, 0.06, 0.05), frame, bevel=0.015))
    return None


def overhead(ship, c, s, material="gunmetal", facing=1, switches=8, light_mat="lights_amber", trim="black"):
    """An overhead switch panel hung from the ceiling, tilted toward the pilot."""
    x, y, z = c
    f = facing
    tilt = f * 25
    ship.add(block("overhead", c, s, material, bevel=0.015, rot=tilt))
    seams(ship, c, s, ys=(0.0,), xs=(-s[0] / 4, s[0] / 4), material=trim, width=0.015, proud=0.008)
    cols = switches // 2
    for i in range(switches):
        row, col = i // cols, i % cols
        sx = x - (cols - 1) * 0.07 + col * 0.14
        sy = y + f * (0.06 - row * 0.12)
        p = Vector((sx, sy, z - s[2] / 2))
        d = Matrix.Rotation(math.radians(tilt), 3, "X") @ Vector((0, 0, -0.045))
        ship.add(cyl("sw", tuple(p), tuple(p + d), 0.009, "steel", segs=6, bevel=0))
        if i % 3 == 0:
            ship.add(cyl("led", (sx + 0.035, sy, z - s[2] / 2), (sx + 0.035, sy, z - s[2] / 2 - 0.01), 0.012, light_mat, segs=6, bevel=0), "lights")
    return None


def wheel(name, c, facing=1, r=0.22, material="black", hub="steel"):
    """A steering wheel on a column, facing the pilot."""
    x, y, z = c
    f = facing
    parts = [ring(name, c, (0, f, 0), r, r - 0.03, 0.04, material, segs=20),
             cyl("hub", (x, y, z), (x, y + f * 0.05, z), 0.06, hub, segs=10, bevel=0.005),
             cyl("column", (x, y, z), (x, y + f * 0.35, z - 0.25), 0.03, hub, segs=8, bevel=0)]
    for a in (90, 210, 330):
        dx, dz = math.cos(math.radians(a)) * r, math.sin(math.radians(a)) * r
        parts.append(cyl("spoke", (x, y, z), (x + dx, y, z + dz), 0.015, hub, segs=6, bevel=0))
    return join(parts, name)


# ------------------------------------------------------------------------------------- storage

def cabinet(name, c, s, material="grey", doors=2, handle="steel", trim="black", vents=True):
    """A storage cabinet: a body with proud door panels, pull handles on brackets, hinge
    knuckles, vent slots and a kick plate. Its doors face -Y."""
    x, y, z = c
    face = y - s[1] / 2
    parts = [block(name, c, s, material, bevel=0.015),
             block("kick", (x, face - 0.004, z - s[2] / 2 + 0.06), (s[0] - 0.04, 0.01, 0.1), trim, bevel=0),
             block("top", (x, y, z + s[2] / 2 + 0.01), (s[0] + 0.02, s[1] + 0.02, 0.02), trim, bevel=0.005)]
    dw = (s[0] - 0.04 * (doors + 1)) / doors
    dh = s[2] - 0.22
    for i in range(doors):
        dx = x - s[0] / 2 + 0.04 + dw / 2 + i * (dw + 0.04)
        side = 1 if i % 2 == 0 else -1  # handles meet in the middle on a pair
        parts.append(block("door", (dx, face - 0.012, z + 0.02), (dw, 0.024, dh), material, bevel=0.012))
        hx = dx + side * (dw / 2 - 0.07)
        parts.append(cyl("handle", (hx, face - 0.06, z - 0.08), (hx, face - 0.06, z + 0.12), 0.012, handle, segs=8, bevel=0))
        for hz in (z - 0.08, z + 0.12):
            parts.append(block("hbrk", (hx, face - 0.04, hz), (0.03, 0.04, 0.03), handle, bevel=0))
        kx = dx - side * (dw / 2 - 0.01)
        for kz in (z + dh / 2 - 0.15, z - dh / 2 + 0.15):
            parts.append(cyl("knuckle", (kx, face - 0.02, kz - 0.05), (kx, face - 0.02, kz + 0.05), 0.012, handle, segs=6, bevel=0))
        if vents:
            for k in range(3):
                parts.append(block("vent", (dx, face - 0.028, z + dh / 2 - 0.12 - k * 0.04), (dw * 0.5, 0.006, 0.016), trim, bevel=0))
        parts.append(block("plate", (dx, face - 0.028, z - dh / 2 + 0.1), (dw * 0.4, 0.004, 0.06), trim, bevel=0))
    return join(parts, name)


def bunk(name, c, s, material="olive", frame="gunmetal", wall=-1):
    """A crew bunk: tube frame, mattress, pillow, a rolled blanket and two straps up to the wall
    on the `wall` side (±X)."""
    x, y, z = c
    w, l, t = s
    parts = [block(name, (x, y, z), (w, l, t), material, bevel=0.04, segs=3),
             block("pillow", (x, y + l / 2 - 0.3, z + t / 2 + 0.05), (w - 0.2, 0.4, 0.1), "deserter_pale", bevel=0.04, segs=3),
             cyl("blanket", (x - w / 2 + 0.15, y - l / 2 + 0.1, z + t / 2 + 0.1), (x + w / 2 - 0.15, y - l / 2 + 0.1, z + t / 2 + 0.1), 0.1, "deserter_tan", segs=10, bevel=0.02)]
    for sy in (-1, 1):
        parts.append(cyl("rail", (x - w / 2, y + sy * l / 2, z - t / 2), (x + w / 2, y + sy * l / 2, z - t / 2), 0.02, frame, segs=8, bevel=0))
    for sx in (-1, 1):
        parts.append(cyl("rail", (x + sx * w / 2, y - l / 2, z - t / 2), (x + sx * w / 2, y + l / 2, z - t / 2), 0.02, frame, segs=8, bevel=0))
    for sy in (-0.35, 0.35):
        parts.append(cyl("strap", (x - wall * w / 2, y + sy * l, z - t / 2), (x + wall * (w / 2 + 0.05), y + sy * l, z + 0.6), 0.012, "black", segs=6, bevel=0))
    return join(parts, name)


def crate(name, c, s, material="olive", band="black", stencil=None):
    """A field crate with corner caps, two bands, a lid seam and an optional stencil."""
    x, y, z = c
    parts = [block(name, c, s, material, bevel=0.02)]
    for sx in (-1, 1):
        parts.append(block("band", (x + sx * (s[0] / 2 - 0.1), y, z), (0.05, s[1] + 0.02, s[2] + 0.02), band, bevel=0))
        for sy in (-1, 1):
            parts.append(block("cap", (x + sx * s[0] / 2, y + sy * s[1] / 2, z + s[2] / 2), (0.12, 0.12, 0.05), "steel", bevel=0.005))
            parts.append(block("cap", (x + sx * s[0] / 2, y + sy * s[1] / 2, z - s[2] / 2), (0.12, 0.12, 0.05), "steel", bevel=0.005))
    parts.append(block("lidseam", (x, y, z + s[2] / 2 - 0.08), (s[0] + 0.012, s[1] + 0.012, 0.015), band, bevel=0))
    parts.append(block("latch", (x, y - s[1] / 2 - 0.01, z + s[2] / 2 - 0.14), (0.08, 0.02, 0.1), "steel", bevel=0.003))
    if stencil:
        parts.append(label(stencil, (x - s[0] / 2 - 0.004, y, z), min(0.16, s[2] * 0.3), band, side=-1, depth=0.003))
    return join(parts, name)


def barrel(name, c, r=0.3, h=0.9, material="rust", hoop="steel"):
    """An oil drum: a cylinder with two rolled hoops and a bung."""
    x, y, z = c
    parts = [cyl(name, (x, y, z), (x, y, z + h), r, material, segs=16, bevel=0.015),
             cyl("bung", (x + r * 0.5, y, z + h), (x + r * 0.5, y, z + h + 0.02), 0.04, hoop, segs=8, bevel=0)]
    for k in (0.28, 0.72):
        parts.append(ring("hoop", (x, y, z + h * k), (0, 0, 1), r + 0.02, r - 0.01, 0.05, hoop, segs=16))
    return join(parts, name)


def gas_bottle(name, c, r=0.14, h=1.1, material="olive", valve="brass"):
    """A gas cylinder with a domed top, a valve and a guard ring."""
    x, y, z = c
    parts = [cyl(name, (x, y, z), (x, y, z + h - r), r, material, segs=14, bevel=0.01),
             sphere("dome", (x, y, z + h - r), r, material, segs=12),
             cyl("neck", (x, y, z + h - 0.02), (x, y, z + h + 0.08), 0.03, valve, segs=8, bevel=0),
             cyl("valve", (x - 0.06, y, z + h + 0.06), (x + 0.06, y, z + h + 0.06), 0.015, valve, segs=6, bevel=0),
             ring("guard", (x, y, z + h + 0.04), (0, 0, 1), r * 0.8, r * 0.7, 0.03, "steel", segs=12)]
    return join(parts, name)


def tyre(name, c, axis=(0, 0, 1), r=0.45, w=0.3, material="black", hub="steel"):
    parts = [ring(name, c, axis, r, r * 0.55, w, material, segs=20),
             ring("hubring", c, axis, r * 0.56, r * 0.3, w * 0.6, hub, segs=12)]
    return join(parts, name)


def cargo_net(name, c, s, pitch=0.22, r=0.012, material="olive"):
    """A rope net flat against a wall (plane normal to X), `s` = (height along Z, width along Y)."""
    x, y, z = c
    h, w = s
    parts = []
    nz, ny = max(2, int(h / pitch)), max(2, int(w / pitch))
    for i in range(nz + 1):
        zz = z - h / 2 + i * h / nz
        parts.append(cyl(name, (x, y - w / 2, zz), (x, y + w / 2, zz), r, material, segs=5, bevel=0))
    for i in range(ny + 1):
        yy = y - w / 2 + i * w / ny
        parts.append(cyl("rope", (x, yy, z - h / 2), (x, yy, z + h / 2), r, material, segs=5, bevel=0))
    for sy in (-1, 1):
        for sz in (-1, 1):
            parts.append(sphere("tie", (x, y + sy * w / 2, z + sz * h / 2), 0.03, "steel", segs=6))
    return join(parts, name)


def gun_rack(name, c, facing=1, n=3, material="gunmetal", gun="black"):
    """A wall rack of standing rifles with a shelf, a retaining bar and a padlock."""
    x, y, z = c
    f = facing
    w = 0.3 * n + 0.1
    parts = [block(name, (x, y - f * 0.03, z + 0.5), (w, 0.04, 1.3), material, bevel=0.01),
             block("shelf", (x, y + f * 0.1, z), (w, 0.26, 0.03), material, bevel=0.005),
             cyl("bar", (x - w / 2, y + f * 0.12, z + 0.95), (x + w / 2, y + f * 0.12, z + 0.95), 0.015, "steel", segs=8, bevel=0),
             block("lock", (x + w / 2 - 0.05, y + f * 0.12, z + 0.88), (0.05, 0.03, 0.07), "brass", bevel=0.01)]
    for i in range(n):
        gx = x - w / 2 + 0.2 + i * 0.3
        gy = y + f * 0.1
        parts += [cyl("barrel", (gx, gy, z + 0.5), (gx, gy, z + 1.12), 0.012, gun, segs=6, bevel=0),
                  block("receiver", (gx, gy, z + 0.42), (0.05, 0.1, 0.26), gun, bevel=0.006),
                  block("mag", (gx, gy + f * 0.07, z + 0.28), (0.035, 0.05, 0.16), gun, bevel=0.004, rot=f * 10),
                  block("stock", (gx, gy - f * 0.03, z + 0.18), (0.04, 0.07, 0.3), "olive", bevel=0.008),
                  block("grip", (gx, gy + f * 0.05, z + 0.14), (0.03, 0.05, 0.1), gun, bevel=0.004, rot=f * -15),
                  block("sight", (gx, gy - f * 0.02, z + 0.6), (0.03, 0.04, 0.06), "steel", bevel=0.004)]
    return join(parts, name)


def server_rack(ship, c, s, material="white", trim="black", light_mat="blue_light", rows=6):
    """An equipment rack with a glass door, lit drive rows and a status cluster."""
    x, y, z = c
    face = y - s[1] / 2
    ship.add(block("rack", c, s, material, bevel=0.015))
    ship.add(block("frame", (x, face - 0.01, z), (s[0] - 0.06, 0.02, s[2] - 0.1), trim, bevel=0.005))
    ship.add(block("pane", (x, face - 0.022, z), (s[0] - 0.14, 0.006, s[2] - 0.2), "glass", bevel=0), "glass")
    for i in range(rows):
        rz = z + s[2] / 2 - 0.2 - i * (s[2] - 0.4) / (rows - 1)
        ship.add(block("unit", (x, face - 0.005, rz), (s[0] - 0.18, 0.01, 0.05), trim, bevel=0))
        ship.add(block("ledrow", (x - s[0] / 4, face - 0.012, rz), (s[0] / 3, 0.006, 0.012), light_mat if i % 2 else "lights_amber", bevel=0), "lights")
    ship.add(cyl("handle", (x + s[0] / 2 - 0.08, face - 0.05, z - 0.15), (x + s[0] / 2 - 0.08, face - 0.05, z + 0.15), 0.01, "steel", segs=6, bevel=0))
    return None


def first_aid(name, c, facing=-1, material="white"):
    """A wall first-aid box with a red cross and a latch. Its face is toward `facing`."""
    x, y, z = c
    f = facing
    parts = [block(name, c, (0.36, 0.14, 0.28), material, bevel=0.012),
             block("cross", (x, y + f * 0.075, z), (0.16, 0.01, 0.05), "red", bevel=0),
             block("cross", (x, y + f * 0.075, z), (0.05, 0.01, 0.16), "red", bevel=0),
             block("latch", (x, y + f * 0.075, z - 0.1), (0.05, 0.01, 0.03), "steel", bevel=0)]
    return join(parts, name)


def extinguisher(name, c, material="red", wall=-1):
    """A fire extinguisher on a wall bracket on the `wall` side (±X)."""
    x, y, z = c
    parts = [cyl(name, (x, y, z), (x, y, z + 0.5), 0.08, material, segs=12, bevel=0.01),
             sphere("dome", (x, y, z + 0.5), 0.08, material, segs=10),
             cyl("neck", (x, y, z + 0.56), (x, y, z + 0.64), 0.025, "steel", segs=8, bevel=0),
             block("lever", (x, y + 0.04, z + 0.66), (0.03, 0.14, 0.015), "black", bevel=0, rot=-15),
             cyl("hose", (x, y - 0.08, z + 0.6), (x, y - 0.1, z + 0.2), 0.012, "black", segs=6, bevel=0),
             block("bracket", (x + wall * 0.09, y, z + 0.3), (0.03, 0.14, 0.08), "steel", bevel=0),
             block("ring", (x, y, z + 0.3), (0.19, 0.19, 0.02), "steel", bevel=0.005)]
    return join(parts, name)


# ---------------------------------------------------------------------------------- hard lines

def pipe_run(ship, pts, r=0.04, material="steel", brackets=0.9, bracket_mat="black", valve_at=None):
    """A pipe through `pts` with knuckle elbows, saddle brackets every `brackets` metres and,
    with `valve_at` (a point along it), a hand-wheel valve."""
    from kit import pipe
    ship.add(pipe("pipe", pts, r, material, segs=10))
    for a, b in zip(pts, pts[1:]):
        a, b = Vector(a), Vector(b)
        length = (b - a).length
        n = max(1, int(length / brackets))
        for i in range(n):
            p = a.lerp(b, (i + 0.5) / n)
            ship.add(block("saddle", tuple(p), (r * 2.8, 0.05 if abs((b - a).y) > abs((b - a).x) else r * 2.8, r * 2.8) if abs((b - a).z) < 0.5 else (r * 2.8, r * 2.8, 0.05), bracket_mat, bevel=0.004))
    if valve_at:
        v = Vector(valve_at)
        ship.add(cyl("vbody", tuple(v - Vector((0, 0.06, 0))), tuple(v + Vector((0, 0.06, 0))), r * 1.5, "brass", segs=10, bevel=0.005))
        ship.add(cyl("vstem", tuple(v), tuple(v - Vector((0, 0, r * 3))), r * 0.4, "steel", segs=6, bevel=0))
        ship.add(ring("vwheel", tuple(v - Vector((0, 0, r * 3))), (0, 0, 1), r * 2.2, r * 1.8, 0.02, "red", segs=12))
    return None


def duct(name, p0, p1, s, material="grey", flange=1.0):
    """A rectangular duct from p0 to p1 (along one axis) with flanges every `flange` metres."""
    a, b = Vector(p0), Vector(p1)
    d = b - a
    size = (s[0] + abs(d.x), s[1] + abs(d.y), s[2] + abs(d.z))
    parts = [block(name, tuple((a + b) / 2), size, material, bevel=0.015)]
    n = max(1, int(d.length / flange))
    for i in range(n + 1):
        p = a.lerp(b, i / n)
        fs = (s[0] + 0.03 if abs(d.x) < 0.01 else 0.04, s[1] + 0.03 if abs(d.y) < 0.01 else 0.04, s[2] + 0.03 if abs(d.z) < 0.01 else 0.04)
        parts.append(block("flange", tuple(p), fs, "black", bevel=0.004))
    return join(parts, name)


def cable_bundle(name, pts, n=3, r=0.015, material="black", spread=0.035):
    """A few cables run together through `pts`, sagging a little between fixings."""
    from kit import pipe
    parts = []
    for k in range(n):
        off = Vector((((k % 2) - 0.5) * spread, 0, -(k // 2) * spread))
        run = [tuple(Vector(p) + off) for p in pts]
        parts.append(pipe(name, run, r, material, segs=6))
    for p in pts[1:-1]:
        parts.append(block("clip", p, (spread * 2.2, 0.04, spread * 1.6), "steel", bevel=0.003))
    return join(parts, name)


def grating(ship, c, s, material="gunmetal", pitch=0.14, rim="black", cross=0.7):
    """A floor of open grating: a rim, long bars along Y and cross bars every `cross` metres."""
    x, y, z = c
    w, l = s
    ship.add(block("subfloor", (x, y, z - 0.02), (w, l, 0.02), "black", bevel=0))
    for sx in (-1, 1):
        ship.add(block("rim", (x + sx * (w / 2 - 0.03), y, z), (0.06, l, 0.03), rim, bevel=0))
    for sy in (-1, 1):
        ship.add(block("rim", (x, y + sy * (l / 2 - 0.03), z), (w, 0.06, 0.03), rim, bevel=0))
    n = int((w - 0.12) / pitch)
    for i in range(n + 1):
        bx = x - (w - 0.12) / 2 + i * (w - 0.12) / n
        ship.add(block("bar", (bx, y, z), (0.02, l - 0.12, 0.03), material, bevel=0))
    m = int(l / cross)
    for i in range(1, m):
        by = y - l / 2 + i * l / m
        ship.add(block("cross", (x, by, z - 0.005), (w - 0.12, 0.03, 0.02), material, bevel=0))
    return None


def wall_panels(ship, x, y0, y1, z0, z1, material, n=4, bolts=True, bolt_mat="steel", gap=0.06, thick=0.04):
    """Lining panels stood against a wall at `x` (the wall's inner face), between y0..y1 and
    z0..z1, with a bolt at each corner."""
    side = -1 if x < 0 else 1
    w = (y1 - y0 - gap * (n + 1)) / n
    for i in range(n):
        yc = y0 + gap + w / 2 + i * (w + gap)
        ship.add(side_plate("panel", x - side * thick / 2, (yc, (z0 + z1) / 2), (w, z1 - z0 - 2 * gap), material, thick=thick, bevel=0.012))
        if bolts:
            for sy in (-1, 1):
                for sz in (-1, 1):
                    ship.add(rivets("bolt", (x - side * thick, yc + sy * (w / 2 - 0.08), (z0 + z1) / 2 + sz * ((z1 - z0) / 2 - gap - 0.08)),
                                    (x - side * thick, yc + sy * (w / 2 - 0.08), (z0 + z1) / 2 + sz * ((z1 - z0) / 2 - gap - 0.08)), 1, r=0.022, material=bolt_mat, axis="-x" if side > 0 else "x"))
    return None


def lamp(ship, name, c, material="lamp", rim="gunmetal", r=0.16, cage=False):
    """A round ceiling fitting: a rim, a lit lens and the `lamp.<n>` node the game lights the
    cabin from. `cage=True` adds a wire guard."""
    x, y, z = c
    ship.add(ring("rim", (x, y, z - 0.02), (0, 0, 1), r + 0.03, r, 0.05, rim, segs=16))
    ship.add(cyl("lens", (x, y, z - 0.005), (x, y, z - 0.04), r, material, segs=16, bevel=0), "lights")
    if cage:
        for a in range(0, 180, 45):
            dx, dy = math.cos(math.radians(a)) * (r + 0.02), math.sin(math.radians(a)) * (r + 0.02)
            ship.add(cyl("wire", (x - dx, y - dy, z - 0.06), (x + dx, y + dy, z - 0.06), 0.006, rim, segs=4, bevel=0))
        ship.add(ring("cagering", (x, y, z - 0.09), (0, 0, 1), r + 0.02, r + 0.01, 0.012, rim, segs=12))
    ship.node(name, (x, y, z - 0.12))
    return None


def hatch(name, c, facing=1, r=0.38, material="gunmetal", wheel_mat="steel"):
    """A round pressure hatch on a bulkhead, with a locking wheel and hinge lugs. Its face is
    toward -facing."""
    x, y, z = c
    f = facing
    parts = [cyl(name, (x, y, z), (x, y - f * 0.06, z), r, material, segs=24, bevel=0.015),
             ring("rim", (x, y - f * 0.02, z), (0, 1, 0), r + 0.06, r - 0.02, 0.05, "black", segs=24),
             ring("wheel", (x, y - f * 0.14, z), (0, 1, 0), r * 0.5, r * 0.42, 0.03, wheel_mat, segs=16),
             cyl("stem", (x, y - f * 0.06, z), (x, y - f * 0.14, z), 0.03, wheel_mat, segs=8, bevel=0)]
    for a in (0, 120, 240):
        dx, dz = math.cos(math.radians(a)) * r * 0.46, math.sin(math.radians(a)) * r * 0.46
        parts.append(cyl("spoke", (x, y - f * 0.14, z), (x + dx, y - f * 0.14, z + dz), 0.012, wheel_mat, segs=6, bevel=0))
    for sz in (-1, 1):
        parts.append(block("lug", (x + r + 0.04, y - f * 0.03, z + sz * r * 0.5), (0.08, 0.1, 0.1), "black", bevel=0.01))
    return join(parts, name)


# ----------------------------------------------------------------------------------- workshop

def workbench(name, c, s, top="steel", frame="rust", vice=True):
    """A workbench: plate top on angle legs, a lower shelf, a vice and a few tools."""
    x, y, z = c
    w, l, h = s
    parts = [block(name, (x, y, z + h), (w, l, 0.06), top, bevel=0.005),
             block("shelf", (x, y, z + 0.25), (w - 0.1, l - 0.1, 0.03), frame, bevel=0.004),
             block("apron", (x - w / 2 + 0.02, y, z + h - 0.09), (0.04, l, 0.12), frame, bevel=0.004)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(block("leg", (x + sx * (w / 2 - 0.05), y + sy * (l / 2 - 0.05), z + h / 2), (0.06, 0.06, h), frame, bevel=0.004))
    if vice:
        vx, vy = x - w / 2 + 0.22, y + l / 2 - 0.35
        parts += [block("vbase", (vx, vy, z + h + 0.08), (0.2, 0.16, 0.1), "black", bevel=0.01),
                  block("vjaw", (vx, vy + 0.12, z + h + 0.1), (0.18, 0.06, 0.12), "black", bevel=0.01),
                  cyl("vscrew", (vx, vy + 0.15, z + h + 0.08), (vx, vy + 0.4, z + h + 0.08), 0.02, "steel", segs=8, bevel=0),
                  cyl("vhandle", (vx - 0.12, vy + 0.4, z + h + 0.08), (vx + 0.12, vy + 0.4, z + h + 0.08), 0.012, "steel", segs=6, bevel=0)]
    parts += [cyl("hhandle", (x + 0.1, y - 0.3, z + h + 0.03), (x + 0.4, y - 0.25, z + h + 0.03), 0.015, "leather", segs=6, bevel=0),
              block("hhead", (x + 0.43, y - 0.245, z + h + 0.05), (0.1, 0.05, 0.05), "steel", bevel=0.006),
              cyl("can", (x + 0.2, y + 0.1, z + h + 0.03), (x + 0.2, y + 0.1, z + h + 0.2), 0.05, "red", segs=10, bevel=0.005),
              cyl("can2", (x + 0.32, y + 0.05, z + h + 0.03), (x + 0.32, y + 0.05, z + h + 0.16), 0.04, "olive", segs=10, bevel=0.005),
              block("wrench", (x - 0.1, y + 0.4, z + h + 0.04), (0.3, 0.04, 0.012), "steel", bevel=0.003),
              block("rag", (x + 0.05, y - 0.05, z + h + 0.04), (0.25, 0.2, 0.03), "deserter_tan", bevel=0.012)]
    return join(parts, name)


def hoist(ship, c, length, drop, material="steel", chain_mat="steel"):
    """An overhead hoist: an I-beam rail along Y at `c` (its underside), a trolley, a chain
    block and a hook hanging `drop` metres."""
    from kit import chain
    x, y, z = c
    ship.add(block("rail", (x, y, z + 0.08), (0.12, length, 0.16), material, bevel=0.006))
    ship.add(block("railflange", (x, y, z + 0.01), (0.22, length, 0.03), material, bevel=0.004))
    ship.add(block("trolley", (x, y, z - 0.08), (0.3, 0.26, 0.14), "black", bevel=0.01))
    for sx in (-1, 1):
        for sy in (-1, 1):
            ship.add(cyl("wheel", (x + sx * 0.1, y + sy * 0.1, z + 0.02), (x + sx * 0.14, y + sy * 0.1, z + 0.02), 0.05, "black", segs=10, bevel=0.004))
    ship.add(cyl("blockbody", (x, y, z - 0.15), (x, y, z - 0.42), 0.11, material, segs=12, bevel=0.01))
    ship.add(chain("chain", (x, y, z - 0.42), (x, y, z - 0.42 - drop), links=max(6, int(drop / 0.14)), r=0.025, material=chain_mat))
    ship.add(chain("handchain", (x + 0.1, y, z - 0.42), (x + 0.1, y, z - 0.42 - drop * 1.3), links=max(8, int(drop * 1.3 / 0.12)), r=0.015, material=chain_mat))
    hz = z - 0.42 - drop
    ship.add(cyl("hookstem", (x, y, hz), (x, y, hz - 0.12), 0.03, material, segs=8, bevel=0))
    ship.add(ring("hook", (x, y + 0.06, hz - 0.18), (1, 0, 0), 0.08, 0.05, 0.035, material, segs=12))
    return None


# -------------------------------------------------------------------------------- the Regime

def candelabra(ship, c, material="gold", arms=3, h=1.2, flame="gold_light"):
    """A floor candelabra: a weighted base, a stem, arms with cups, candles and flames."""
    x, y, z = c
    ship.add(cyl("base", (x, y, z), (x, y, z + 0.05), 0.22, material, r1=0.16, segs=14, bevel=0.005))
    ship.add(cyl("stem", (x, y, z + 0.05), (x, y, z + h), 0.025, material, segs=8, bevel=0))
    ship.add(sphere("knop", (x, y, z + h * 0.55), 0.05, material, segs=8))
    for i in range(arms):
        a = math.radians(90 + i * 360 / arms)
        dx, dy = math.cos(a) * 0.22, math.sin(a) * 0.22
        ship.add(cyl("arm", (x, y, z + h - 0.25), (x + dx, y + dy, z + h - 0.05), 0.015, material, segs=6, bevel=0))
        ship.add(cyl("cup", (x + dx, y + dy, z + h - 0.06), (x + dx, y + dy, z + h), 0.05, material, r1=0.035, segs=10, bevel=0))
        ship.add(cyl("candle", (x + dx, y + dy, z + h), (x + dx, y + dy, z + h + 0.22), 0.025, "bone", segs=8, bevel=0))
        ship.add(sphere("flame", (x + dx, y + dy, z + h + 0.27), 0.035, flame, segs=6), "lights")
    ship.add(cyl("topcup", (x, y, z + h), (x, y, z + h + 0.06), 0.05, material, r1=0.035, segs=10, bevel=0))
    ship.add(cyl("topcandle", (x, y, z + h + 0.06), (x, y, z + h + 0.3), 0.025, "bone", segs=8, bevel=0))
    ship.add(sphere("flame", (x, y, z + h + 0.35), 0.035, flame, segs=6), "lights")
    return None


def censer(ship, c, drop, material="gold", glow="gold_light"):
    """A censer hung from the ceiling at `c` on a chain, swinging over the aisle."""
    from kit import chain
    x, y, z = c
    ship.add(chain("chain", (x, y, z), (x, y, z - drop), links=max(6, int(drop / 0.1)), r=0.012, material=material))
    bz = z - drop
    ship.add(sphere("bowl", (x, y, bz - 0.12), 0.14, material, segs=12))
    ship.add(cyl("lid", (x, y, bz - 0.02), (x, y, bz + 0.08), 0.1, material, r1=0.03, segs=10, bevel=0))
    ship.add(ring("band", (x, y, bz - 0.1), (0, 0, 1), 0.15, 0.13, 0.03, "slate", segs=12))
    ship.add(sphere("ember", (x, y, bz - 0.05), 0.07, glow, segs=8), "lights")
    return None


def altar(ship, c, s, material="bone", cloth="red", trim="gold"):
    """An altar table under a fringed cloth, with a chalice, a candle pair and an open book."""
    x, y, z = c
    w, l, h = s
    ship.add(block("altar", (x, y, z + h / 2), (w, l, h), material, bevel=0.02))
    ship.add(block("cloth", (x, y, z + h + 0.015), (w + 0.2, l + 0.1, 0.03), cloth, bevel=0.012))
    for sx in (-1, 1):
        ship.add(block("drape", (x + sx * (w / 2 + 0.09), y, z + h - 0.25), (0.03, l + 0.1, 0.5), cloth, bevel=0.008))
        ship.add(block("fringe", (x + sx * (w / 2 + 0.09), y, z + h - 0.5), (0.035, l + 0.1, 0.03), trim, bevel=0))
    seams(ship, (x, y, z + h / 2), (w, l, h), ys=(-l / 4, l / 4), material=trim, width=0.03, proud=0.01)
    ship.add(cyl("cstem", (x, y, z + h + 0.03), (x, y, z + h + 0.18), 0.02, trim, segs=8, bevel=0))
    ship.add(cyl("cup", (x, y, z + h + 0.18), (x, y, z + h + 0.3), 0.045, trim, r1=0.07, segs=12, bevel=0))
    for sx in (-1, 1):
        ship.add(cyl("candle", (x + sx * (w / 2 - 0.15), y, z + h + 0.03), (x + sx * (w / 2 - 0.15), y, z + h + 0.35), 0.03, "bone", segs=8, bevel=0))
        ship.add(sphere("flame", (x + sx * (w / 2 - 0.15), y, z + h + 0.4), 0.035, "gold_light", segs=6), "lights")
    ship.add(block("book", (x, y - l / 2 + 0.2, z + h + 0.05), (0.42, 0.3, 0.05), material, bevel=0.005, rot=-12))
    ship.add(block("spine", (x, y - l / 2 + 0.2, z + h + 0.08), (0.02, 0.3, 0.02), trim, bevel=0, rot=-12))
    return None


def font(name, c, material="bone", trim="gold"):
    """A holy-water font: a pedestal and a bowl."""
    x, y, z = c
    parts = [cyl(name, (x, y, z), (x, y, z + 0.06), 0.3, material, r1=0.14, segs=14, bevel=0.01),
             cyl("pillar", (x, y, z + 0.06), (x, y, z + 0.8), 0.1, material, segs=10, bevel=0.01),
             cyl("bowl", (x, y, z + 0.8), (x, y, z + 1.0), 0.18, material, r1=0.32, segs=16, bevel=0.01),
             cyl("water", (x, y, z + 0.98), (x, y, z + 0.995), 0.28, "glass", segs=16, bevel=0),
             ring("lip", (x, y, z + 1.0), (0, 0, 1), 0.33, 0.3, 0.03, trim, segs=16)]
    return join(parts, name)
