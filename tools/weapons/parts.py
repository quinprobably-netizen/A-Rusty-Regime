"""Shared weapon pieces: gunsmith attachments (optics, muzzle devices, foregrips, stocks), sockets and
clip helpers. Every weapon module in guns/ builds on these and on kit.py."""

import math

from kit import begin, block, cut, cyl, hole_through, join, label, prism, ring, screw, slots, tube  # noqa: F401

MAKER = "RUST REGIME ARMS"


def mirror_x(fn):
    """Build a detail on both sides: fn(side) with side -1 (left) and +1 (right)."""
    return [fn(-1), fn(1)]


# ---------------------------------------------------------------------------------------- optics

def optic_reddot(g, top, bone="root", length=0.05):
    """Enclosed red dot on a rail clamp; `top` is the rail top (x, y, z)."""
    x, y, z = top
    base = block("att.optic.reddot", (x, y, z + 0.004), (0.026, length * 0.8, 0.008), "black", bevel=0.001)
    clamp = block("clamp", (x + 0.014, y, z + 0.003), (0.004, 0.016, 0.01), "steel")
    knob = cyl("knob", (x + 0.016, y, z + 0.004), (x + 0.021, y, z + 0.004), 0.004, "steel", segs=16)
    hood = prism("hood", [(y - length / 2, z + 0.008), (y + length / 2, z + 0.008), (y + length / 2, z + 0.03),
                          (y + length / 2 - 0.006, z + 0.036), (y - length / 2 + 0.006, z + 0.036), (y - length / 2, z + 0.03)],
                 0.03, "black", x=x, bevel=0.0015, segs=3)
    window = block("w", (x, y, z + 0.021), (0.022, length * 1.2, 0.019), "steel", bevel=0)
    cut(hood, window)
    lens = block("lens", (x, y + length / 2 - 0.004, z + 0.021), (0.022, 0.0015, 0.019), "glass", bevel=0)
    dot = cyl("dot", (x, y + length / 2 - 0.0045, z + 0.021), (x, y + length / 2 - 0.0035, z + 0.021), 0.0009, "reticle", segs=10, bevel=0)
    turret = cyl("turret", (x - 0.015, y, z + 0.022), (x - 0.021, y, z + 0.022), 0.006, "black", segs=20)
    cap = cyl("cap", (x - 0.021, y, z + 0.022), (x - 0.023, y, z + 0.022), 0.005, "steel", segs=20)
    o = join([base, clamp, knob, hood, lens, dot, turret, cap, screw((x + 0.016, y - 0.005, z + 0.003), "x", 0.0015)], "att.optic.reddot")
    lens_socket(g, "reddot.lens", (x, y + length / 2 - 0.0048, z + 0.021), (0.011, 1.0, 0.0095), bone)
    return g.add(o, bone)


def lens_socket(g, name, at, scale, bone):
    """The game draws a sight's picture on this socket: `scope.eye` at the eyepiece's centre scaled by
    its radius, `reddot.lens` at the window's centre scaled by its half width and height."""
    e = g.socket(name, at, bone)
    e.scale = scale
    return e


def optic_scope(g, top, bone="root", length=0.17, mag=0.019):
    """Variable scope in two rings; objective faces +Y."""
    x, y, z = top
    zc = z + 0.026
    parts = [tube("scope", (x, y - length * 0.32, zc), (x, y + length * 0.18, zc), 0.0125, 0.010, "black")]
    parts.append(cyl("eyebell", (x, y - length / 2, zc), (x, y - length * 0.32, zc), mag, "black", r1=0.0125, segs=32))
    parts.append(cyl("objbell", (x, y + length * 0.18, zc), (x, y + length / 2, zc), 0.0125, "black", r1=mag + 0.002, segs=32))
    parts.append(cyl("lens_r", (x, y - length / 2 + 0.002, zc), (x, y - length / 2 + 0.003, zc), mag - 0.002, "glass", segs=32, bevel=0))
    parts.append(cyl("lens_f", (x, y + length / 2 - 0.004, zc), (x, y + length / 2 - 0.003, zc), mag, "glass", segs=32, bevel=0))
    parts.append(cyl("turret_t", (x, y, zc + 0.01), (x, y, zc + 0.022), 0.0085, "black", segs=24))
    parts.append(cyl("turret_s", (x + 0.01, y, zc), (x + 0.022, y, zc), 0.0085, "black", segs=24))
    parts.append(cyl("turret_l", (x - 0.01, y, zc), (x - 0.018, y, zc), 0.007, "black", segs=24))
    parts.append(ring("zoom", (x, y - length * 0.36, zc), (0, 1, 0), 0.0165, 0.0125, 0.012, "rubber", segs=32))
    for dy in (-0.035, 0.035):
        parts.append(ring("ring", (x, y + dy, zc), (0, 1, 0), 0.0155, 0.0124, 0.012, "steel", segs=32))
        parts.append(block("ringbase", (x, y + dy, z + 0.007), (0.024, 0.012, 0.014), "steel"))
        parts.append(screw((x + 0.016, y + dy, zc - 0.002), "x", 0.0018))
    parts.append(label("6X", (x - 0.0085, y - length * 0.36, zc + 0.012), 0.004, "bright"))
    o = join(parts, "att.optic.scope")
    o.name = "att.optic.scope"
    r = mag - 0.002
    lens_socket(g, "scope.eye", (x, y - length / 2 + 0.0015, zc), (r, r, r), bone)
    return g.add(o, bone)


def muzzle_parts(g, at, r=0.0085, bone="root", comp_len=0.045, supp_len=0.15, supp_r=0.019):
    x, y, z = at
    comp = cyl("att.muzzle.comp", (x, y, z), (x, y + comp_len, z), r * 1.35, "steel", segs=24)
    bore = hole_through("b", (x, y + comp_len / 2, z), r * 0.6, "y", comp_len * 1.4)
    ports = [block("p", (x, y + comp_len * f, z + r), (r * 1.6, comp_len * 0.12, r * 1.4), "steel", bevel=0) for f in (0.3, 0.5, 0.7)]
    side = [block("p", (x, y + comp_len * f, z), (r * 3, comp_len * 0.1, r * 0.9), "steel", bevel=0) for f in (0.4, 0.65)]
    comp = cut(comp, bore, *ports, *side)
    comp.name = "att.muzzle.comp"
    g.add(comp, bone)
    supp = tube("att.muzzle.supp", (x, y, z), (x, y + supp_len, z), supp_r, r * 0.55, "black", segs=36)
    cap = ring("cap", (x, y + supp_len - 0.004, z), (0, 1, 0), supp_r + 0.001, r * 0.6, 0.008, "steel", segs=36)
    mount = ring("mount", (x, y + 0.008, z), (0, 1, 0), supp_r + 0.0012, r * 0.9, 0.016, "steel", segs=36)
    grooves = [ring("gr", (x, y + 0.03 + i * 0.008, z), (0, 1, 0), supp_r + 0.0006, supp_r - 0.001, 0.003, "steel", segs=36) for i in range(4)]
    supp = join([supp, cap, mount, *grooves, label(MAKER, (x - supp_r - 0.0002, y + supp_len * 0.62, z), 0.0038, "bright")], "att.muzzle.supp")
    supp.name = "att.muzzle.supp"
    g.add(supp, bone)


def grip_parts(g, under, bone="root"):
    """Vertical and angled foregrips hanging under a rail at `under` (x, y, z of the rail face)."""
    x, y, z = under
    v_body = cyl("att.grip.vertical", (x, y, z - 0.008), (x, y, z - 0.085), 0.0135, "black", r1=0.0125, segs=24)
    v_grooves = [ring("g", (x, y, z - 0.03 - i * 0.012), (0, 0, 1), 0.0142, 0.0118, 0.004, "rubber", segs=24) for i in range(4)]
    v_cap = cyl("cap", (x, y, z - 0.085), (x, y, z - 0.09), 0.0115, "steel", r1=0.009, segs=24)
    v_clamp = block("clamp", (x, y, z - 0.005), (0.026, 0.03, 0.01), "black", bevel=0.0012)
    v = join([v_body, *v_grooves, v_cap, v_clamp, screw((x + 0.013, y, z - 0.005), "x", 0.0016)], "att.grip.vertical")
    v.name = "att.grip.vertical"
    g.add(v, bone)
    a = prism("att.grip.angled", [(y - 0.03, z), (y + 0.03, z), (y + 0.012, z - 0.03), (y - 0.006, z - 0.03)], 0.022, "black", x=x, bevel=0.002, segs=3)
    a = cut(a, *slots("s", y - 0.012, y + 0.008, 4, z - 0.032, z - 0.024, x - 0.02, x + 0.02))
    a.name = "att.grip.angled"
    g.add(a, bone)


def stock_parts(g, at, bone="root", height=0.0):
    """Light (skeleton) and heavy (padded) stocks bolted on behind `at` (x, y, z of the buffer)."""
    x, y, z = at
    light = prism("att.stock.light", [(y, z + 0.012), (y - 0.2, z + 0.006), (y - 0.21, z - 0.07), (y - 0.195, z - 0.075),
                                       (y - 0.175, z - 0.03), (y, z - 0.012)], 0.012, "black", x=x, bevel=0.0015, segs=3)
    light = cut(light, prism("h", [(y - 0.03, z + 0.002), (y - 0.17, z - 0.0), (y - 0.18, z - 0.035), (y - 0.04, z - 0.006)], 0.05, "steel", x=x, bevel=0))
    lpad = block("pad", (x, y - 0.212, z - 0.032), (0.03, 0.014, 0.085), "rubber", bevel=0.003, segs=3)
    light = join([light, lpad], "att.stock.light")
    light.name = "att.stock.light"
    g.add(light, bone)
    heavy = prism("att.stock.heavy", [(y, z + 0.016), (y - 0.18, z + 0.012), (y - 0.2, z + 0.004), (y - 0.205, z - 0.085),
                                       (y - 0.14, z - 0.06), (y - 0.06, z - 0.03), (y, z - 0.02)], 0.036, "black", x=x, bevel=0.003, segs=3)
    cheek = block("cheek", (x, y - 0.11, z + 0.02), (0.032, 0.09, 0.012), "rubber", bevel=0.003, segs=3)
    hpad = block("pad", (x, y - 0.212, z - 0.035), (0.04, 0.018, 0.1), "rubber", bevel=0.004, segs=3)
    qd = cyl("qd", (x - 0.02, y - 0.17, z - 0.03), (x - 0.017, y - 0.17, z - 0.03), 0.006, "steel", segs=16)
    heavy = join([heavy, cheek, hpad, qd], "att.stock.heavy")
    heavy.name = "att.stock.heavy"
    g.add(heavy, bone)


def attachments(g, top, muzzle, under, stock, optic_bone="root", muzzle_r=0.0085, scope=True, stock_socket=None):
    optic_reddot(g, top, optic_bone)
    if scope:
        optic_scope(g, top, optic_bone)
    muzzle_parts(g, muzzle, muzzle_r)
    grip_parts(g, under)
    if stock:
        stock_parts(g, stock)
    for name, at in (("optic", top), ("muzzle", muzzle), ("under", under)):
        g.socket(name, at, optic_bone if name == "optic" else "root")
    at, bone = stock_socket or (stock, "root")
    g.socket("stock", at, bone)


SLOT_ATTS = ["att.optic.reddot", "att.optic.scope", "att.muzzle.comp", "att.muzzle.supp", "att.grip.vertical", "att.grip.angled",
             "att.stock.light", "att.stock.heavy"]


# --------------------------------------------------------------------------------------- shared clips

def common_clips(g, reload_len, reload_tracks, inspect_roll=35, draw_len=0.45):
    g.clip("idle", 1.0, {})
    g.clip("draw", draw_len, {"root": [(0, (0, -0.04, -0.12), (-55, 0, 10)), (draw_len * 0.7, (0, 0.004, 0.004), (4, 0, 0)), (draw_len, (0, 0, 0), (0, 0, 0))]})
    g.clip("inspect", 2.6, {"root": [(0, (0, 0, 0), (0, 0, 0)), (0.5, (-0.03, 0.02, 0.03), (10, -inspect_roll, 25)), (1.3, (-0.03, 0.02, 0.03), (12, -inspect_roll - 5, 30)),
                                     (1.8, (0.02, 0.0, 0.02), (-8, 30, -20)), (2.3, (0.0, 0.0, 0.0), (0, 0, 0))]})
    g.clip("reload", reload_len, reload_tracks)


def mag_drop(axis, t_out, t_in, t_seat, drop=0.25):
    """Mag track: pull out along `axis` (unit (y, z) toward the mag's bottom), fall, swap, seat."""
    ay, az = axis
    return [(0, (0, 0, 0), (0, 0, 0)), (t_out, (0, ay * 0.02, az * 0.02), (0, 0, 0)), (t_out + 0.18, (0, ay * drop, az * drop), (-25, 0, 0)),
            (t_out + 0.18 + 2 / 60, (0, ay * 0.14, az * 0.14), (0, 0, 0)), (t_in, (0, ay * 0.03, az * 0.03), (0, 0, 0)), (t_seat, (0, 0, 0), (0, 0, 0))]
