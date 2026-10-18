"""Smite pistol: a long-slide 1911 with a stabilizer, rail light and stippled grip panels."""

import math

from kit import begin, block, cut, cyl, dimples, hole_through, join, label, pin, prism, rail, ring, screw, slots, tube
from parts import MAKER, SLOT_ATTS, attachments, common_clips, mag_drop


def build():
    """Smite: a long-slide 1911 with a stabilizer, rail light and a stippled grip."""
    bore = 0.030
    g = begin("pistol", {
        "slide": ((0, 0, bore), None),
        "hammer": ((0, -0.079, 0.014), None),
        "trigger": ((0, 0.012, -0.004), None),
        "mag": ((0, -0.06, -0.04), None),
        "stop": ((0, 0.012, 0.008), None),
    })
    # Slide: long, flat-topped, with lightening windows, serrations and an ejection port.
    sl = prism("slide", [(-0.077, 0.013), (0.150, 0.013), (0.150, 0.036), (0.145, 0.043), (-0.070, 0.043), (-0.077, 0.037)], 0.024, "steel", bevel=0.0007)
    cuts = slots("ser", -0.071, -0.040, 10, 0.016, 0.042, -0.0135, -0.0115) + slots("ser", -0.071, -0.040, 10, 0.016, 0.042, 0.0115, 0.0135)
    cuts += slots("ser", 0.118, 0.142, 7, 0.016, 0.042, -0.0135, -0.0115) + slots("ser", 0.118, 0.142, 7, 0.016, 0.042, 0.0115, 0.0135)
    cuts += [block("port", (0.008, 0.012, 0.037), (0.012, 0.034, 0.016), "steel", bevel=0)]
    cuts += [block("win", (0, 0.068 + i * 0.02, 0.0245), (0.03, 0.013, 0.0075), "steel", bevel=0) for i in range(3)]
    cuts += [block("top", (0, 0.06 + i * 0.016, 0.045), (0.008, 0.009, 0.006), "steel", bevel=0) for i in range(4)]
    cuts += [hole_through("bore", (0, 0.15, bore), 0.0072, "y", 0.03, segs=24)]
    sl = cut(sl, *cuts)
    rear = prism("rsight", [(-0.072, 0.043), (-0.058, 0.043), (-0.060, 0.050), (-0.071, 0.051)], 0.02, "black", bevel=0.0005)
    rear = cut(rear, block("notch", (0, -0.065, 0.05), (0.0035, 0.03, 0.006), "steel", bevel=0))
    front = prism("fsight", [(0.132, 0.043), (0.142, 0.043), (0.141, 0.050), (0.135, 0.050)], 0.004, "black", bevel=0.0003)
    fiber = cyl("fiber", (0, 0.1335, 0.0475), (0, 0.1405, 0.0475), 0.0011, "reticle", segs=10, bevel=0)
    dots = [cyl("dot", (s * 0.006, -0.0715, 0.047), (s * 0.006, -0.0725, 0.047), 0.0008, "lamp", segs=8, bevel=0) for s in (-1, 1)]
    g.add(join([sl, rear, front, fiber, *dots, label("SMITE", (-0.0122, 0.03, 0.033), 0.0065, "bright"),
                label(".460 SMITE  1891EX", (-0.0122, 0.03, 0.019), 0.0028, "bright"),
                label(MAKER, (0.0122, 0.09, 0.019), 0.0026, "bright", side=1)], "slide"), "slide")
    # Barrel and bushing, visible through the windows and the port.
    g.add(tube("barrel", (0, -0.02, bore), (0, 0.149, bore), 0.0068, 0.0046, "bright"), "slide")
    g.add(ring("bushing", (0, 0.146, bore), (0, 1, 0), 0.0098, 0.0069, 0.006, "bright"), "slide")
    g.add(block("hood", (0, 0.012, bore + 0.006), (0.0118, 0.03, 0.004), "bright", bevel=0.0004), "slide")
    g.add(block("extractor", (0.0118, -0.03, 0.036), (0.002, 0.045, 0.004), "steel", bevel=0.0003), "slide")
    # Frame: dust cover with a rail, trigger guard, grip, beavertail.
    frame = prism("frame", [(-0.083, 0.013), (0.108, 0.013), (0.108, -0.001), (0.032, -0.001), (0.026, -0.006), (-0.035, -0.006),
                            (-0.068, -0.002), (-0.086, 0.004)], 0.0225, "steel")
    frame = cut(frame, *slots("rs", 0.035, 0.10, 6, -0.002, 0.004, -0.02, 0.02))
    guard = prism("guard", [(-0.006, -0.004), (0.036, -0.004), (0.039, -0.012), (0.036, -0.031), (0.030, -0.034), (0.002, -0.034),
                            (-0.012, -0.028), (-0.016, -0.012)], 0.012, "steel", bevel=0.0009)
    guard = cut(guard, prism("gh", [(-0.004, -0.007), (0.031, -0.007), (0.033, -0.012), (0.031, -0.028), (0.004, -0.029), (-0.008, -0.024),
                                    (-0.008, -0.009)], 0.03, "steel", bevel=0))
    guard = cut(guard, *slots("gs", 0.038, 0.038, 1, -0.03, -0.012, -0.007, 0.007))
    grip = prism("grip", [(-0.066, 0.0), (-0.022, 0.0), (-0.032, -0.06), (-0.052, -0.108), (-0.096, -0.108), (-0.086, -0.045), (-0.083, -0.004)],
                 0.029, "steel", bevel=0.0012)
    beaver = prism("beaver", [(-0.083, 0.013), (-0.074, 0.006), (-0.083, -0.004), (-0.099, 0.002), (-0.104, 0.008), (-0.098, 0.012)],
                   0.022, "steel", bevel=0.0012, segs=3)
    bump = block("bump", (0, -0.088, -0.032), (0.022, 0.012, 0.02), "steel", bevel=0.003, segs=3, rot=-18)
    rail_under = rail("rail", 0.045, 0.104, -0.001, "steel", flip=True, width=0.02)
    pins = [pin((0, y, z), "x", 0.0013, 0.025) for y, z in ((-0.078, 0.008), (0.012, 0.004), (0.062, 0.006))]
    safety = prism("safety", [(-0.074, 0.016), (-0.052, 0.016), (-0.05, 0.02), (-0.074, 0.021)], 0.003, "steel", x=-0.0128, bevel=0.0003)
    g.add(join([frame, guard, grip, beaver, bump, rail_under, *pins, safety,
                label("MADE ON THE ISLAND", (-0.0115, 0.075, 0.006), 0.0024, "bright")], "frame"), "root")
    # Grip panels: stippled, two screws a side, a red medallion on the left.
    for side in (-1, 1):
        x = side * 0.0158
        panel = prism("panel", [(-0.066, -0.008), (-0.034, -0.008), (-0.044, -0.06), (-0.054, -0.098), (-0.088, -0.098), (-0.080, -0.04),
                                (-0.077, -0.01)], 0.004, "black", x=x, bevel=0.0007)
        panel = cut(panel, *dimples("st", -0.082, -0.042, -0.03, -0.09, x + side * 0.002, 7, 8, r=0.0011, side=side))
        g.add(join([panel, screw((x + side * 0.0022, -0.054, -0.016), "x" if side > 0 else "-x", 0.0024),
                    screw((x + side * 0.0022, -0.07, -0.088), "x" if side > 0 else "-x", 0.0024)], "panel"), "root")
    g.add(cyl("medal", (-0.0182, -0.065, -0.05), (-0.0172, -0.065, -0.05), 0.005, "red", segs=20), "root")
    # Slide stop (rides the slide as it locks back) and the skeleton hammer.
    stop = prism("stop", [(-0.004, 0.014), (0.03, 0.014), (0.032, 0.018), (0.0, 0.02)], 0.003, "steel", x=-0.0128, bevel=0.0003)
    g.add(join([stop, cyl("stopknob", (-0.0145, 0.026, 0.017), (-0.0128, 0.026, 0.017), 0.003, "steel", segs=14)], "stop"), "stop")
    hammer = prism("hammer", [(-0.081, 0.012), (-0.074, 0.012), (-0.082, 0.03), (-0.092, 0.034), (-0.096, 0.028), (-0.088, 0.016)],
                   0.008, "steel", bevel=0.0005)
    hammer = cut(hammer, hole_through("hh", (0, -0.088, 0.027), 0.0028, "x"))
    g.add(hammer, "hammer")
    trig = prism("trigger", [(0.008, -0.005), (0.014, -0.005), (0.014, -0.024), (0.011, -0.025), (0.008, -0.022)], 0.006, "bright", bevel=0.0004)
    trig = cut(trig, *[hole_through("th", (0, 0.011, z), 0.0011, "x") for z in (-0.009, -0.014, -0.019)])
    g.add(join([trig, block("bow", (0, -0.01, -0.004), (0.004, 0.036, 0.003), "bright", bevel=0.0002)], "trigger"), "trigger")
    # Magazine: body follows the grip angle so it can drop out; base pad, witness holes, top round.
    ax = (-math.sin(math.radians(18)), -math.cos(math.radians(18)))
    mag = prism("mag", [(-0.064, 0.0), (-0.034, 0.0), (-0.052, -0.1), (-0.084, -0.1)], 0.016, "steel", bevel=0.0005)
    mag = cut(mag, *[hole_through("wh", (-0.0, -0.05 - 0.016 * i * 0.31, -0.03 - i * 0.016), 0.0018, "x") for i in range(4)])
    pad = prism("pad", [(-0.054, -0.104), (-0.096, -0.104), (-0.1, -0.116), (-0.05, -0.116)], 0.027, "black", bevel=0.0018, segs=3)
    rnd = cyl("round", (0, -0.062, 0.006), (0, -0.04, 0.006), 0.0058, "brass", segs=18)
    tip = cyl("tip", (0, -0.04, 0.006), (0, -0.034, 0.006), 0.0058, "copper", r1=0.003, segs=18)
    g.add(join([mag, pad, rnd, tip], "mag"), "mag")
    # Gunsmith parts: optic on the slide, comp/suppressor on the barrel, light/laser on the rail,
    # extended base pads in the stock slot.
    attachments(g, (0, -0.012, 0.043), (0, 0.151, bore), (0, 0.075, -0.007), None, optic_bone="slide", muzzle_r=0.0068, scope=False,
                stock_socket=((0, -0.075, -0.116), "mag"))
    # A pistol "scope" is a long eye relief prism sight.
    prism_sight = block("att.optic.scope", (0, -0.012, 0.055), (0.024, 0.06, 0.022), "black", bevel=0.002, segs=3)
    prism_sight = join([prism_sight, cyl("l", (0, 0.018, 0.057), (0, 0.019, 0.057), 0.009, "glass", segs=24, bevel=0),
                        cyl("r", (0, -0.042, 0.057), (0, -0.043, 0.057), 0.008, "glass", segs=24, bevel=0),
                        cyl("t", (-0.012, -0.012, 0.058), (-0.018, -0.012, 0.058), 0.006, "black", segs=18)], "att.optic.scope")
    prism_sight.name = "att.optic.scope"
    g.add(prism_sight, "slide")
    for name, depth in (("att.stock.light", 0.012), ("att.stock.heavy", 0.024)):
        ext = prism(name, [(-0.05, -0.116), (-0.1, -0.116), (-0.103, -0.116 - depth), (-0.048, -0.116 - depth)], 0.028, "red" if depth < 0.02 else "black",
                    bevel=0.0015, segs=3)
        ext.name = name
        g.add(ext, "mag")
    g.socket("eject", (0.012, 0.012, 0.04), "slide")
    # Clips.
    g.clip("fire", 0.14, {
        "slide": [(0, (0, 0, 0), (0, 0, 0)), (0.025, (0, -0.047, 0), (0, 0, 0)), (0.1, (0, 0, 0), (0, 0, 0))],
        "hammer": [(0, (0, 0, 0), (0, 0, 0)), (0.006, (0, 0, 0), (38, 0, 0)), (0.025, (0, 0, 0), (0, 0, 0))],
        "trigger": [(0, (0, 0, 0), (0, 0, 0)), (0.008, (0, -0.003, 0), (0, 0, 0)), (0.09, (0, 0, 0), (0, 0, 0))],
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.03, (0, -0.006, 0.002), (7, 0, 1)), (0.14, (0, 0, 0), (0, 0, 0))],
    })
    common_clips(g, 1.5, {
        "root": [(0, (0, 0, 0), (0, 0, 0)), (0.25, (0.01, 0.0, 0.03), (12, 28, 0)), (1.1, (0.01, 0.0, 0.03), (14, 30, 0)),
                 (1.3, (0, 0, 0.01), (6, 6, 0)), (1.5, (0, 0, 0), (0, 0, 0))],
        "mag": mag_drop(ax, 0.3, 0.85, 0.98),
        "slide": [(0, (0, 0, 0), (0, 0, 0)), (0.2, (0, -0.047, 0), (0, 0, 0)), (1.12, (0, -0.047, 0), (0, 0, 0)), (1.16, (0, 0, 0), (0, 0, 0))],
        "stop": [(0, (0, 0, 0), (0, 0, 0)), (0.2, (0, 0, 0), (8, 0, 0)), (1.1, (0, 0, 0), (8, 0, 0)), (1.14, (0, 0, 0), (0, 0, 0))],
    })
    return g


SPEC = {"build": build, "length": (0.18, 0.28), "tris": (8000, 80000),
               "bones": ["root", "slide", "hammer", "trigger", "mag", "stop"],
               "sockets": ["muzzle", "eject", "optic", "under", "stock"], "attachments": SLOT_ATTS,
               "parts": {"mesh.slide": "slide", "mesh.root": "root", "mesh.mag": "mag", "mesh.hammer": "hammer", "mesh.trigger": "trigger"},
               "moves": {"fire": ["slide", "hammer", "trigger"], "reload": ["mag", "slide", "root"], "draw": ["root"], "inspect": ["root"]},
               "view": {"cam": (-0.42, 0.16, 0.13), "look": (0, 0.03, -0.02)}}
