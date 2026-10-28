"""Bits shared by the small solid fighters (censer, welder, sentry, jackal): a cockpit cut into a
hull, with a pilot seat, stick and dash under a see-through canopy. No walkable interior.
Blender frame as in kit: +Y nose, Z up, X right."""

from kit import block, cut, cyl, loft


def seat(ship, c, material="black", frame="gunmetal", trim=None):
    """A compact fighter seat facing +Y: cushion at `c`, a raked back, a headrest, harness straps
    and side rails (trim), standing on a short frame. About 1 m tall from its frame foot."""
    x, y, z = c
    trim = trim or frame
    ship.add(block("seat", (x, y, z), (0.5, 0.48, 0.12), material, bevel=0.03))
    ship.add(block("back", (x, y - 0.27, z + 0.38), (0.5, 0.1, 0.72), material, bevel=0.03, rot=12))
    ship.add(block("head", (x, y - 0.36, z + 0.82), (0.3, 0.1, 0.2), material, bevel=0.03, rot=12))
    ship.add(block("frame", (x, y - 0.05, z - 0.2), (0.4, 0.4, 0.28), frame, bevel=0.01))
    for sx in (-1, 1):
        ship.add(block("rail", (x + sx * 0.28, y - 0.12, z + 0.25), (0.05, 0.5, 0.06), trim, bevel=0.005))
        ship.add(block("strap", (x + sx * 0.11, y - 0.205, z + 0.4), (0.05, 0.015, 0.7), "black", bevel=0, rot=12))
    ship.add(block("buckle", (x, y + 0.04, z + 0.08), (0.1, 0.06, 0.04), "steel", bevel=0))


def cockpit(ship, hull, well, canopy, seat_at, sides=8, phase=0.0, hull_mat="gunmetal", seat_mat="black", frame="gunmetal",
            trim=None, screen="screen", hoops=()):
    """Cut a cockpit well (`well` = (centre, size) of a box) into `hull`, sit a seat, stick and dash in
    it and close it with a `canopy` (loft sections, see-through glass). `hoops` are y stations
    where a hollow frame ring hoops the canopy. Returns the hull."""
    (cx, cy, cz), (sx, sy, sz) = well
    hull = cut(hull, block("well", (cx, cy, cz), (sx, sy, sz), hull_mat, bevel=0))
    floor = cz - sz / 2
    ship.add(block("tub", (cx, cy, floor + 0.02), (sx - 0.02, sy - 0.02, 0.04), "black", bevel=0))
    seat(ship, seat_at, material=seat_mat, frame=frame, trim=trim)
    x, y, z = seat_at
    ship.add(cyl("stick", (x, y + 0.42, floor), (x, y + 0.42, z + 0.3), 0.025, "black", segs=8, bevel=0))
    ship.add(block("grip", (x, y + 0.42, z + 0.34), (0.05, 0.06, 0.1), "black", bevel=0.01))
    front = cy + sy / 2
    ship.add(block("dash", (cx, front - 0.14, z + 0.32), (sx - 0.04, 0.26, 0.2), frame, bevel=0.01, rot=-25))
    ship.add(block("screen", (cx, front - 0.27, z + 0.36), (sx * 0.6, 0.02, 0.1), screen, bevel=0, rot=-25), "lights")
    ship.add(loft("canopy", canopy, "canopy", sides=sides, phase=phase), "glass")
    for hy in hoops:
        # A hollow frame ring: the band less a slightly smaller, longer one.
        ring = band("hoop", canopy, hy, 0.06, frame, grow=1.03, sides=sides, phase=phase)
        ship.add(cut(ring, band("bore", canopy, hy, 0.2, frame, grow=0.93, pad=0.0, sides=sides, phase=phase)))
    return hull


def band(name, sections, y, width, material, grow=1.03, sides=8, phase=0.0, pad=0.008):
    """A painted or plated ring round a lofted hull at station `y`, sized from the hull's own
    sections so it hugs the surface."""
    _, x, z, rx, rz = at(sections, y)
    ring = (x, z, rx * grow + pad, rz * grow + pad)
    return loft(name, [(y - width / 2, *ring), (y + width / 2, *ring)], material, sides=sides, phase=phase)


def at(sections, y):
    """The hull section (y, x, z, rx, rz) interpolated at station `y`."""
    for a, b in zip(sections, sections[1:]):
        if a[0] <= y <= b[0] or b[0] <= y <= a[0]:
            t = (y - a[0]) / ((b[0] - a[0]) or 1)
            return tuple(a[k] + (b[k] - a[k]) * t for k in range(5))
    raise ValueError(f"y={y} is off the hull")
