"""3D models for circuit components, in 'realistic' and 'schematic' styles.

Every builder receives a root empty (already placed/rotated in the world) and
creates its geometry in the component's local frame, where the terminals lie
on the z = 0 plane at the positions given in ``catalog``.  Builders return a
dict of named *parts* used later by the animation layer, e.g.

* ``glow``   - object whose (unique) material emission is animated (LED, bulb)
* ``light``  - point light whose energy is animated
* ``lever``  - moving part of a switch (see ``lever_axis`` / ``open_value``)
* ``display``- text object showing a meter reading
* ``rotor``  - spinning part of a motor, ``cone`` - speaker cone
* ``plate_a``/``plate_b`` - capacitor plates (charge visualisation)
"""

import json
import math

import bpy

from . import bl_utils as U
from . import catalog

LEAD_R = 0.025
INK_R = 0.03

BAND_COLORS = [
    (0.01, 0.01, 0.01), (0.25, 0.1, 0.03), (0.8, 0.02, 0.02), (1.0, 0.3, 0.0), (1.0, 0.85, 0.0),
    (0.0, 0.5, 0.05), (0.02, 0.1, 0.8), (0.4, 0.05, 0.6), (0.35, 0.35, 0.35), (0.95, 0.95, 0.95),
]


# ------------------------------------------------------------------ materials
def M(key):
    """Shared materials."""
    table = {
        "lead": dict(base=(0.8, 0.8, 0.82), metallic=1.0, roughness=0.25),
        "copper": dict(base=(0.95, 0.5, 0.3), metallic=1.0, roughness=0.3),
        "black": dict(base=(0.02, 0.02, 0.025), roughness=0.4),
        "dark": dict(base=(0.08, 0.08, 0.09), roughness=0.5),
        "white": dict(base=(0.9, 0.9, 0.88), roughness=0.5),
        "red": dict(base=(0.8, 0.03, 0.03), roughness=0.35),
        "blue": dict(base=(0.03, 0.15, 0.6), roughness=0.35),
        "beige": dict(base=(0.78, 0.63, 0.42), roughness=0.55),
        "silver": dict(base=(0.75, 0.75, 0.78), metallic=1.0, roughness=0.2),
        "gold": dict(base=(1.0, 0.7, 0.25), metallic=1.0, roughness=0.25),
        "grey": dict(base=(0.3, 0.3, 0.32), roughness=0.5),
        "glass": dict(base=(0.9, 0.95, 1.0), roughness=0.02, transmission=1.0, alpha=0.35),
        "ink": dict(base=(0.92, 0.95, 1.0), roughness=0.6, emission=(0.92, 0.95, 1.0), emission_strength=0.6),
        "ink_accent": dict(base=(1.0, 0.75, 0.2), roughness=0.6, emission=(1.0, 0.75, 0.2), emission_strength=0.8),
        "text_dark": dict(base=(0.02, 0.02, 0.02), roughness=0.6),
        "display": dict(base=(0.05, 0.9, 0.3), emission=(0.05, 0.9, 0.3), emission_strength=2.0),
        "board_green": dict(base=(0.02, 0.2, 0.08), roughness=0.6),
    }
    spec = table[key]
    return U.material("cc_" + key, **spec)


def band_material(i):
    return U.material("cc_band_%d" % i, base=BAND_COLORS[i], roughness=0.4)


def glow_material(name, rgb, glass=False, dim=1.0):
    """Unique emissive material (emission strength animated per component). dim darkens the unlit colour."""
    if glass:
        return U.material(name, base=tuple(0.35 + 0.65 * c for c in rgb), roughness=0.08, transmission=0.6,
                          emission=rgb, emission_strength=0.0, unique=True, alpha=0.9)
    return U.material(name, base=tuple(c * dim for c in rgb), roughness=0.4, emission=rgb, emission_strength=0.0,
                      unique=True)


# -------------------------------------------------------------------- helpers
class Builder:
    def __init__(self, cid, root, col):
        self.cid, self.root, self.col = cid, root, col
        self.parts = {}
        self.n = 0

    def name(self, part):
        self.n += 1
        return "%s_%s" % (self.cid, part)

    def lead(self, *points, mat="lead", radius=LEAD_R):
        return U.poly_curve(self.name("lead"), points, radius, M(mat), self.root, self.col)

    def line(self, *points, mat="ink", radius=INK_R, closed=False, part=None):
        m = M(mat) if isinstance(mat, str) else mat
        obj = U.poly_curve(self.name(part or "line"), points, radius, m, self.root, self.col, closed=closed)
        if part:
            self.parts[part] = obj
        return obj

    def box(self, size, loc, mat, part=None, bevel=0.0):
        m = M(mat) if isinstance(mat, str) else mat
        obj = U.box(self.name(part or "box"), size, loc, m, self.root, self.col, bevel=bevel)
        if part:
            self.parts[part] = obj
        return obj

    def cyl(self, r, depth, loc, axis="Z", mat="dark", part=None, r2=None, segments=32):
        m = M(mat) if isinstance(mat, str) else mat
        obj = U.cylinder(self.name(part or "cyl"), r, depth, loc, axis, m, self.root, self.col, segments, r2)
        if part:
            self.parts[part] = obj
        return obj

    def sphere(self, r, loc, mat, part=None, scale=(1, 1, 1)):
        m = M(mat) if isinstance(mat, str) else mat
        obj = U.sphere(self.name(part or "sph"), r, loc, m, self.root, self.col, scale=scale)
        if part:
            self.parts[part] = obj
        return obj

    def text(self, body, size, loc, mat="text_dark", part=None, align="CENTER", rot=(0, 0, 0)):
        m = M(mat) if isinstance(mat, str) else mat
        obj = U.text(self.name(part or "txt"), body, size, loc, m, self.root, self.col, align=align, rotation=rot)
        if part:
            self.parts[part] = obj
        return obj

    def poly(self, points, mat, part=None, thickness=0.0):
        m = M(mat) if isinstance(mat, str) else mat
        obj = U.flat_polygon(self.name(part or "poly"), points, m, self.root, self.col, thickness)
        if part:
            self.parts[part] = obj
        return obj

    def empty(self, loc, part):
        obj = U.empty(self.name(part), loc, self.root, self.col, size=0.15)
        obj.hide_render = True
        self.parts[part] = obj
        return obj

    def light(self, loc, rgb, part="light", radius=0.1):
        data = bpy.data.lights.new(self.name(part), "POINT")
        data.color = rgb
        data.energy = 0.0
        data.shadow_soft_size = radius
        obj = bpy.data.objects.new(self.name(part), data)
        obj.location = loc
        obj.parent = self.root
        U.link(obj, self.col)
        self.parts[part] = obj
        return obj


def _resistor_bands(value):
    value = max(float(value or 0), 0.1)
    exp = int(math.floor(math.log10(value))) - 1
    digits = int(round(value / 10 ** exp))
    if digits >= 100:
        digits //= 10
        exp += 1
    d1, d2 = digits // 10, digits % 10
    mult = exp
    return [d1, d2, mult]


def _zigzag(x0, x1, amp, peaks):
    pts = [(x0, 0, 0)]
    n = peaks * 2
    for i in range(n):
        x = x0 + (x1 - x0) * (i + 0.5) / n
        pts.append((x, amp if i % 2 == 0 else -amp, 0))
    pts.append((x1, 0, 0))
    return pts


def _arrow_head(b, tip, direction, size=0.12, mat="ink", part=None):
    dx, dy = direction
    ln = math.hypot(dx, dy) or 1.0
    dx, dy = dx / ln, dy / ln
    px, py = -dy, dx
    base = (tip[0] - dx * size * 1.6, tip[1] - dy * size * 1.6)
    pts = [(tip[0], tip[1], 0.0), (base[0] + px * size, base[1] + py * size, 0.0),
           (base[0] - px * size, base[1] - py * size, 0.0)]
    return b.poly(pts, mat, part)


# ============================================================ realistic models
def r_resistor(b, p):
    b.lead((-1, 0, 0), (-0.45, 0, 0))
    b.lead((0.45, 0, 0), (1, 0, 0))
    b.cyl(0.15, 0.8, (0, 0, 0), "X", "beige", part="body")
    b.sphere(0.18, (-0.42, 0, 0), "beige", scale=(0.9, 1, 1))
    b.sphere(0.18, (0.42, 0, 0), "beige", scale=(0.9, 1, 1))
    d1, d2, mult = _resistor_bands(p.get("resistance"))
    mats = [band_material(d1), band_material(d2)]
    mats.append(band_material(mult) if 0 <= mult <= 9 else M("gold" if mult == -1 else "silver"))
    for x, m in zip((-0.27, -0.13, 0.01), mats):
        b.cyl(0.155, 0.07, (x, 0, 0), "X", m)
    b.cyl(0.19, 0.06, (0.4, 0, 0), "X", "gold")


def r_potentiometer(b, p):
    b.lead((-1, 0, 0), (-0.45, 0, 0))
    b.lead((0.45, 0, 0), (1, 0, 0))
    b.lead((0, 1, 0), (0, 0.45, 0))
    b.cyl(0.55, 0.22, (0, 0, 0), "Z", "blue", part="body")
    knob = b.cyl(0.26, 0.35, (0, 0, 0.28), "Z", "dark", part="knob")
    U.box(b.name("pointer"), (0.05, 0.22, 0.04), (0, 0.12, 0.47), M("white"), knob, b.col)
    pos = float(p.get("position", 0.5))
    knob.rotation_euler.z = math.radians(135 - 270 * pos)
    b.parts["lever"] = knob
    return {"lever_mode": "pot"}


def r_battery(b, p):
    b.lead((-1, 0, 0), (-0.75, 0, 0))
    b.lead((0.84, 0, 0), (1, 0, 0))
    b.cyl(0.32, 1.1, (-0.2, 0, 0), "X", "black", part="body")
    b.cyl(0.321, 0.4, (0.55, 0, 0), "X", "copper")
    b.cyl(0.1, 0.1, (0.8, 0, 0), "X", "silver")
    b.text("+", 0.35, (0.55, 0, 0.33), "white")
    b.text("−", 0.35, (-0.55, 0, 0.33), "white")
    b.text(catalog.format_si(p.get("voltage"), "V"), 0.2, (-0.15, 0, 0.33), "white")


def r_dc_source(b, p):
    b.lead((-1, 0, 0), (-0.82, 0, 0), mat="black")
    b.lead((0.82, 0, 0), (1, 0, 0), mat="red")
    b.box((1.5, 1.1, 0.9), (0, 0, 0.12), "grey", part="body", bevel=0.05)
    b.cyl(0.1, 0.16, (-0.8, 0, 0), "X", "black")
    b.cyl(0.1, 0.16, (0.8, 0, 0), "X", "red")
    b.box((1.0, 0.45, 0.02), (0, 0.1, 0.575), "black")
    b.text(catalog.format_si(p.get("voltage"), "V"), 0.24, (0, 0.1, 0.59), "display", part="display")
    b.text("+", 0.3, (0.55, -0.35, 0.58), "red")
    b.text("−", 0.3, (-0.55, -0.35, 0.58), "white")


def r_ac_source(b, p):
    b.lead((-1, 0, 0), (-0.6, 0, 0))
    b.lead((0.6, 0, 0), (1, 0, 0))
    b.cyl(0.6, 0.3, (0, 0, 0), "Z", "dark", part="body")
    pts = [(-0.4 + 0.8 * i / 40, 0.25 * math.sin(2 * math.pi * i / 40), 0.16) for i in range(41)]
    b.line(*pts, mat="ink_accent", radius=0.035)


def r_current_source(b, p):
    b.lead((-1, 0, 0), (-0.6, 0, 0))
    b.lead((0.6, 0, 0), (1, 0, 0))
    b.cyl(0.6, 0.3, (0, 0, 0), "Z", "dark", part="body")
    b.line((-0.35, 0, 0.16), (0.2, 0, 0.16), mat="ink_accent", radius=0.04)
    tri = [(0.4, 0, 0.16), (0.15, 0.15, 0.16), (0.15, -0.15, 0.16)]
    b.poly(tri, "ink_accent")


def r_capacitor(b, p):
    look = str(p.get("look", "plates")).lower()
    if look == "electrolytic":
        b.lead((-1, 0, 0), (-0.12, 0, 0), (-0.12, 0, -0.05))
        b.lead((1, 0, 0), (0.12, 0, 0), (0.12, 0, -0.05))
        b.cyl(0.32, 0.8, (0, 0, 0.35), "Z", "blue", part="body")
        b.cyl(0.321, 0.8, (0, 0, 0.35), "Z", "grey", segments=32, part="stripe").scale = (0.35, 1.0, 1.0)
        b.parts["stripe"].location.x = 0.21
        b.cyl(0.3, 0.02, (0, 0, 0.76), "Z", "silver")
        b.empty((-0.3, 0, 0.35), "plate_a")
        b.empty((0.3, 0, 0.35), "plate_b")
        return
    b.lead((-1, 0, 0), (-0.16, 0, 0))
    b.lead((0.16, 0, 0), (1, 0, 0))
    b.box((0.07, 0.9, 0.75), (-0.15, 0, 0), "silver", part="plate_a")
    b.box((0.07, 0.9, 0.75), (0.15, 0, 0), "silver", part="plate_b")


def r_inductor(b, p):
    b.lead((-1, 0, 0), (-0.62, 0, 0))
    b.lead((0.62, 0, 0), (1, 0, 0))
    turns, n = int(p.get("turns", 8)), 240
    pts = []
    for i in range(n + 1):
        f = i / n
        a = 2 * math.pi * turns * f
        pts.append((-0.62 + 1.24 * f, 0.24 * math.sin(a), -0.24 * math.cos(a) + 0.0))
    pts[0] = (-0.62, 0, 0)
    pts[-1] = (0.62, 0, 0)
    obj = U.poly_curve(b.name("coil"), pts, 0.045, M("copper"), b.root, b.col, smooth=False)
    b.parts["body"] = obj
    if p.get("core", True):
        b.cyl(0.16, 1.4, (0, 0, 0), "X", "grey")


def r_diode(b, p):
    b.lead((-1, 0, 0), (-0.35, 0, 0))
    b.lead((0.35, 0, 0), (1, 0, 0))
    b.cyl(0.14, 0.7, (0, 0, 0), "X", "black", part="body")
    b.cyl(0.145, 0.1, (0.22, 0, 0), "X", "silver")


def r_led(b, p):
    rgb, _ = catalog.led_color(p.get("color", "red"))
    b.lead((-1, 0, 0), (-0.09, 0, 0), (-0.09, 0, 0.05))
    b.lead((1, 0, 0), (0.09, 0, 0), (0.09, 0, 0.05))
    mat = glow_material(b.cid + "_glow", rgb, glass=True)
    body = b.cyl(0.2, 0.36, (0, 0, 0.26), "Z", mat, part="glow")
    b.sphere(0.2, (0, 0, 0.44), mat)
    b.cyl(0.235, 0.06, (0, 0, 0.08), "Z", mat)
    b.light((0, 0, 0.5), rgb)
    body["cc_rgb"] = list(rgb)


def r_bulb(b, p):
    b.lead((-1, 0, 0), (-0.22, 0, 0), (-0.22, 0, 0.05))
    b.lead((1, 0, 0), (0.22, 0, 0), (0.22, 0, 0.05))
    b.box((0.8, 0.6, 0.12), (0, 0, -0.04), "dark", bevel=0.02)
    b.cyl(0.2, 0.35, (0, 0, 0.2), "Z", "silver", part="body")
    b.sphere(0.45, (0, 0, 0.78), "glass")
    b.line((-0.08, 0, 0.38), (-0.12, 0, 0.72), mat="lead", radius=0.012)
    b.line((0.08, 0, 0.38), (0.12, 0, 0.72), mat="lead", radius=0.012)
    rgb = (1.0, 0.72, 0.35)
    mat = glow_material(b.cid + "_glow", rgb)
    fil = [(-0.12 + 0.24 * i / 12, 0, 0.72 + (0.05 if i % 2 else -0.0)) for i in range(13)]
    obj = U.poly_curve(b.name("glow"), fil, 0.015, mat, b.root, b.col)
    b.parts["glow"] = obj
    obj["cc_rgb"] = list(rgb)
    b.light((0, 0, 0.78), rgb, radius=0.3)


def r_switch(b, p):
    b.lead((-1, 0, 0), (-0.65, 0, 0))
    b.lead((0.65, 0, 0), (1, 0, 0))
    b.box((1.7, 0.55, 0.1), (0, 0, -0.08), "white", part="body", bevel=0.02)
    b.cyl(0.08, 0.22, (-0.65, 0, 0.05), "Z", "silver")
    b.box((0.2, 0.05, 0.22), (0.65, 0.06, 0.08), "silver")
    b.box((0.2, 0.05, 0.22), (0.65, -0.06, 0.08), "silver")
    pivot = b.empty((-0.65, 0, 0.14), "lever")
    U.box(b.name("blade"), (1.45, 0.05, 0.1), (0.72, 0, 0), M("silver"), pivot, b.col)
    U.cylinder(b.name("handle"), 0.07, 0.35, (1.35, 0, 0.12), "Z", M("red"), pivot, b.col)
    closed = bool(p.get("closed"))
    pivot.rotation_euler.y = 0.0 if closed else math.radians(-50)
    return {"lever_mode": "rot_y", "open_value": math.radians(-50), "closed_value": 0.0}


def r_push_button(b, p):
    b.lead((-1, 0, 0), (-0.45, 0, 0))
    b.lead((0.45, 0, 0), (1, 0, 0))
    b.box((0.9, 0.9, 0.3), (0, 0, 0), "dark", part="body", bevel=0.03)
    cap = b.cyl(0.26, 0.22, (0, 0, 0), "Z", "red", part="lever")
    closed = bool(p.get("closed"))
    cap.location.z = 0.18 if closed else 0.28
    return {"lever_mode": "loc_z", "open_value": 0.28, "closed_value": 0.18}


def _meter(b, p, letter):
    b.lead((-1, 0, 0), (-0.6, 0, 0), mat="red")
    b.lead((0.6, 0, 0), (1, 0, 0), mat="black")
    b.cyl(0.62, 0.35, (0, 0, 0), "Z", "dark", part="body")
    b.cyl(0.54, 0.02, (0, 0, 0.18), "Z", "white")
    b.text(letter, 0.34, (0, 0.24, 0.2), "text_dark")
    b.box((0.8, 0.26, 0.01), (0, -0.14, 0.19), "black")
    b.text("0", 0.15, (0, -0.14, 0.205), "display", part="display")
    b.cyl(0.08, 0.1, (-0.62, 0, 0), "X", "red")
    b.cyl(0.08, 0.1, (0.62, 0, 0), "X", "black")


def r_ammeter(b, p):
    _meter(b, p, "A")


def r_voltmeter(b, p):
    _meter(b, p, "V")


def r_motor(b, p):
    b.lead((-1, 0, 0), (-0.45, 0, 0))
    b.lead((0.45, 0, 0), (1, 0, 0))
    b.cyl(0.45, 0.8, (0, 0, 0.2), "Z", "silver", part="body")
    b.cyl(0.46, 0.12, (0, 0, -0.15), "Z", "copper")
    b.cyl(0.04, 0.35, (0, 0, 0.75), "Z", "lead")
    rotor = b.empty((0, 0, 0.9), "rotor")
    U.box(b.name("blade1"), (0.9, 0.16, 0.03), (0, 0, 0), M("red"), rotor, b.col, bevel=0.01)
    U.box(b.name("blade2"), (0.16, 0.9, 0.03), (0, 0, 0), M("red"), rotor, b.col, bevel=0.01)
    U.cylinder(b.name("hub"), 0.08, 0.08, (0, 0, 0.02), "Z", M("dark"), rotor, b.col)


def r_speaker(b, p):
    b.lead((-1, 0, 0), (-0.5, 0, 0))
    b.lead((0.5, 0, 0), (1, 0, 0))
    b.cyl(0.58, 0.15, (0, 0, 0), "Z", "dark", part="body")
    cone = b.cyl(0.15, 0.25, (0, 0, 0.2), "Z", "grey", part="cone", r2=0.52)
    U.sphere(b.name("dustcap"), 0.13, (0, 0, 0.2), M("dark"), cone, b.col)


def r_fuse(b, p):
    b.lead((-1, 0, 0), (-0.6, 0, 0))
    b.lead((0.6, 0, 0), (1, 0, 0))
    b.cyl(0.15, 1.0, (0, 0, 0), "X", "glass", part="body")
    b.cyl(0.165, 0.2, (-0.5, 0, 0), "X", "silver")
    b.cyl(0.165, 0.2, (0.5, 0, 0), "X", "silver")
    pts = [(-0.42 + 0.84 * i / 16, 0, 0.04 * math.sin(i * math.pi / 2)) for i in range(17)]
    b.line(*pts, mat="lead", radius=0.012, part="element")


def _transistor(b, p, kind):
    b.lead((-1, 0, 0), (-0.14, 0, 0), (-0.14, 0, 0.05))
    b.lead(tuple(catalog.COMPONENTS[kind]["terminals"]["c"]), (0, 0.14 * (1 if kind == "npn" else -1), 0),
           (0, 0.14 * (1 if kind == "npn" else -1), 0.05))
    b.lead(tuple(catalog.COMPONENTS[kind]["terminals"]["e"]), (0, -0.14 * (1 if kind == "npn" else -1), 0),
           (0, -0.14 * (1 if kind == "npn" else -1), 0.05))
    b.cyl(0.3, 0.6, (0, 0, 0.35), "Z", "black", part="body")
    b.box((0.61, 0.02, 0.6), (0, -0.3, 0.35), "black")
    b.text(kind.upper(), 0.14, (0, 0, 0.66), "white")
    for term, (x, y, z) in catalog.COMPONENTS[kind]["terminals"].items():
        b.text(term.upper(), 0.16, (x * 0.6 + (0.18 if x == 0 else 0), y * 0.6 + (0.14 if y == 0 else 0), 0.06), "white")


def r_npn(b, p):
    _transistor(b, p, "npn")


def r_pnp(b, p):
    _transistor(b, p, "pnp")


def r_ground(b, p, mat="lead"):
    b.lead((0, 0, 0), (0, -0.35, 0), mat="lead" if mat == "lead" else mat)
    for i, w in enumerate((0.6, 0.4, 0.2)):
        b.box((w, 0.05, 0.05), (0, -0.37 - 0.12 * i, 0), "silver" if mat == "lead" else mat)


def r_junction(b, p):
    b.sphere(0.08, (0, 0, 0), "silver", part="body")


def r_chip(b, p):
    terms, order = catalog.chip_terminals(p.get("pins", 8))
    half = len(order) // 2
    height = half * 0.5 + 0.1
    b.box((1.3, height, 0.35), (0, 0, 0.1), "black", part="body", bevel=0.03)
    b.cyl(0.07, 0.02, (-0.45, height / 2 - 0.2, 0.28), "Z", "grey")
    for name, (x, y, z) in terms.items():
        b.lead((x, y, 0), (x * 0.66, y, 0), (x * 0.66, y, 0.05), mat="silver", radius=0.03)
    b.text(str(p.get("text", "IC")), 0.22, (0, 0, 0.28), "white", rot=(0, 0, math.radians(90) if height > 1.4 else 0))


# ============================================================ schematic models
def s_two_leads(b, x):
    b.line((-1, 0, 0), (-x, 0, 0))
    b.line((x, 0, 0), (1, 0, 0))


def s_resistor(b, p):
    b.line(*([(-1, 0, 0)] + _zigzag(-0.6, 0.6, 0.2, 3) + [(1, 0, 0)]), part="body")


def s_potentiometer(b, p):
    s_resistor(b, p)
    b.line((0, 1, 0), (0, 0.45, 0), part="lever")
    _arrow_head(b, (0, 0.24), (0, -1))
    return {"lever_mode": "none"}


def s_battery(b, p):
    b.line((-1, 0, 0), (-0.35, 0, 0))
    b.line((0.35, 0, 0), (1, 0, 0))
    for x, h in ((-0.35, 0.22), (-0.12, 0.45), (0.12, 0.22), (0.35, 0.45)):
        b.line((x, -h, 0), (x, h, 0), radius=INK_R * (1.6 if h < 0.3 else 1.0))
    b.text("+", 0.3, (0.6, 0.35, 0), "ink")
    b.text("−", 0.3, (-0.6, 0.35, 0), "ink")


def s_dc_source(b, p):
    s_two_leads(b, 0.5)
    b.line(*U.circle_points((0, 0, 0), 0.5, 48), part="body")
    b.text("+", 0.35, (0.22, 0, 0), "ink")
    b.text("−", 0.35, (-0.22, 0, 0), "ink")


def s_ac_source(b, p):
    s_two_leads(b, 0.5)
    b.line(*U.circle_points((0, 0, 0), 0.5, 48), part="body")
    b.line(*[(-0.3 + 0.6 * i / 30, 0.15 * math.sin(2 * math.pi * i / 30), 0) for i in range(31)])


def s_current_source(b, p):
    s_two_leads(b, 0.5)
    b.line(*U.circle_points((0, 0, 0), 0.5, 48), part="body")
    b.line((-0.28, 0, 0), (0.1, 0, 0))
    _arrow_head(b, (0.3, 0), (1, 0))


def s_capacitor(b, p):
    s_two_leads(b, 0.12)
    b.line((-0.12, -0.42, 0), (-0.12, 0.42, 0), part="plate_a", radius=INK_R * 1.4)
    b.line((0.12, -0.42, 0), (0.12, 0.42, 0), part="plate_b", radius=INK_R * 1.4)


def s_inductor(b, p):
    pts = [(-1, 0, 0), (-0.6, 0, 0)]
    for k in range(4):
        cx = -0.45 + 0.3 * k
        pts += U.circle_points((cx, 0, 0), 0.15, 12, 180, 0)[1:]
    pts.append((1, 0, 0))
    b.line(*pts, part="body")


def s_diode(b, p, led=False):
    s_two_leads(b, 0.25)
    b.line((-0.25, 0, 0), (0.25, 0, 0))
    tri = [(-0.25, 0.3, 0), (-0.25, -0.3, 0), (0.25, 0, 0)]
    if led:
        rgb, _ = catalog.led_color(p.get("color", "red"))
        mat = glow_material(b.cid + "_glow", rgb)
        obj = b.poly(tri, mat, part="glow")
        obj["cc_rgb"] = list(rgb)
        for dx in (-0.05, 0.15):
            b.line((dx, 0.35, 0), (dx + 0.22, 0.6, 0), radius=INK_R * 0.7)
            _arrow_head(b, (dx + 0.3, 0.69), (1, 1.1), size=0.07)
        b.light((0, 0, 0.3), rgb)
    else:
        b.poly(tri, "ink", part="body")
    b.line((0.25, -0.3, 0), (0.25, 0.3, 0))


def s_led(b, p):
    s_diode(b, p, led=True)


def s_bulb(b, p):
    s_two_leads(b, 0.45)
    rgb = (1.0, 0.72, 0.35)
    mat = glow_material(b.cid + "_glow", rgb, dim=0.12)
    disc = b.poly(U.circle_points((0, 0, -0.02), 0.44, 40)[:-1], mat, part="glow")
    disc["cc_rgb"] = list(rgb)
    b.line(*U.circle_points((0, 0, 0), 0.45, 48), part="body")
    d = 0.45 / math.sqrt(2)
    b.line((-d, -d, 0), (d, d, 0))
    b.line((-d, d, 0), (d, -d, 0))
    b.light((0, 0, 0.3), rgb, radius=0.3)


def s_switch(b, p):
    s_two_leads(b, 0.5)
    b.sphere(0.07, (-0.5, 0, 0), "ink")
    b.sphere(0.07, (0.5, 0, 0), "ink")
    pivot = b.empty((-0.5, 0, 0), "lever")
    U.poly_curve(b.name("blade"), [(0, 0, 0), (1.0, 0, 0)], INK_R, M("ink"), pivot, b.col)
    pivot.rotation_euler.z = 0.0 if p.get("closed") else math.radians(30)
    return {"lever_mode": "rot_z", "open_value": math.radians(30), "closed_value": 0.0}


def s_push_button(b, p):
    s_two_leads(b, 0.4)
    b.sphere(0.07, (-0.4, 0, 0), "ink")
    b.sphere(0.07, (0.4, 0, 0), "ink")
    cap = b.empty((0, 0.3, 0), "lever")
    U.poly_curve(b.name("bar"), [(-0.45, 0, 0), (0.45, 0, 0)], INK_R, M("ink"), cap, b.col)
    U.poly_curve(b.name("stem"), [(0, 0, 0), (0, 0.3, 0)], INK_R, M("ink"), cap, b.col)
    cap.location.y = 0.08 if p.get("closed") else 0.3
    return {"lever_mode": "loc_y", "open_value": 0.3, "closed_value": 0.08}


def _s_meter(b, p, letter):
    s_two_leads(b, 0.5)
    b.line(*U.circle_points((0, 0, 0), 0.5, 48), part="body")
    b.text(letter, 0.45, (0, 0, 0), "ink")
    b.text("0", 0.22, (0, 0.75, 0), "ink_accent", part="display")
    b.text("+", 0.22, (-0.7, 0.22, 0), "ink")


def s_ammeter(b, p):
    _s_meter(b, p, "A")


def s_voltmeter(b, p):
    _s_meter(b, p, "V")


def s_motor(b, p):
    s_two_leads(b, 0.5)
    b.line(*U.circle_points((0, 0, 0), 0.5, 48), part="body")
    b.text("M", 0.42, (0, 0, 0), "ink")
    rotor = b.empty((0, 0, 0), "rotor")
    U.sphere(b.name("dot"), 0.06, (0.62, 0, 0), M("ink_accent"), rotor, b.col)


def s_speaker(b, p):
    s_two_leads(b, 0.2)
    b.line((-0.2, -0.2, 0), (0.1, -0.2, 0), (0.1, 0.2, 0), (-0.2, 0.2, 0), closed=True, part="body")
    cone = b.empty((0, 0, 0), "cone")
    U.poly_curve(b.name("cone_line"), [(0.1, 0.2, 0), (0.4, 0.45, 0), (0.4, -0.45, 0), (0.1, -0.2, 0)], INK_R,
                 M("ink"), cone, b.col)


def s_fuse(b, p):
    b.line((-1, 0, 0), (1, 0, 0), part="element")
    b.line((-0.5, -0.17, 0), (0.5, -0.17, 0), (0.5, 0.17, 0), (-0.5, 0.17, 0), closed=True, part="body")


def _s_transistor(b, p, kind):
    npn = kind == "npn"
    b.line((-1, 0, 0), (-0.25, 0, 0))
    b.line((-0.25, -0.35, 0), (-0.25, 0.35, 0), radius=INK_R * 1.5)
    b.line((-0.25, 0.15, 0), (0.05, 0.45, 0), (0, 1, 0))
    b.line((-0.25, -0.15, 0), (0.05, -0.45, 0), (0, -1, 0))
    if npn:  # arrow on emitter (bottom) pointing out
        _arrow_head(b, (0.03, -0.43), (1, -1), size=0.09)
    else:    # PNP: emitter at top, arrow pointing in
        _arrow_head(b, (-0.2, 0.2), (-1, -1), size=0.09)
    b.line(*U.circle_points((-0.08, 0, 0), 0.62, 48), part="body")


def s_npn(b, p):
    _s_transistor(b, p, "npn")


def s_pnp(b, p):
    _s_transistor(b, p, "pnp")


def s_ground(b, p):
    b.line((0, 0, 0), (0, -0.35, 0))
    for i, w in enumerate((0.6, 0.4, 0.2)):
        b.line((-w / 2, -0.35 - 0.12 * i, 0), (w / 2, -0.35 - 0.12 * i, 0))


def s_junction(b, p):
    b.poly(U.circle_points((0, 0, 0), 0.09, 20)[:-1], "ink", part="body")


def s_chip(b, p):
    terms, order = catalog.chip_terminals(p.get("pins", 8))
    half = len(order) // 2
    h = half * 0.5 + 0.1
    b.line((-0.65, -h / 2, 0), (0.65, -h / 2, 0), (0.65, h / 2, 0), (-0.65, h / 2, 0), closed=True, part="body")
    for name, (x, y, z) in terms.items():
        b.line((x, y, 0), (x * 0.65, y, 0))
        b.text(name[1:], 0.13, (x * 0.5, y, 0), "ink")
    b.text(str(p.get("text", "IC")), 0.25, (0, 0, 0), "ink")


# ================================================================== dispatcher
def build(cid, comp, settings, col):
    """Create the 3D object hierarchy for a component. Returns the root empty."""
    style = comp.get("style") or settings.get("style", "realistic")
    ctype = comp["type"]
    root = U.empty(cid, (0, 0, 0), None, col, display="PLAIN_AXES", size=0.2)
    pos = comp["position"]
    root.location = (pos[0], pos[1], pos[2] + settings.get("height", 0.3))
    root.rotation_euler.z = math.radians(comp.get("rotation", 0.0))
    b = Builder(cid, root, col)
    prefix = "s_" if style == "schematic" else "r_"
    fn = globals().get(prefix + ctype) or globals().get("r_" + ctype)
    meta = fn(b, comp["params"]) or {}
    # keep text upright/readable whatever the component rotation
    for child in root.children_recursive:
        if child.type == "FONT" and child.parent is root:
            child.rotation_euler.z -= root.rotation_euler.z
    if style == "schematic" and "display" in b.parts:
        # schematic meter readings sit above horizontal symbols, left of vertical ones (label is on the right)
        rot = comp.get("rotation", 0.0) % 360
        disp = b.parts["display"]
        if 45 < rot < 135 or 225 < rot < 315:
            disp.location = catalog.rotate_z((-0.62, 0.0, 0.0), -rot)
            disp.data.align_x = "RIGHT"
        else:
            disp.location = catalog.rotate_z((0.0, 0.8, 0.0), -rot)
    root["cc_id"] = cid
    root["cc_type"] = ctype
    root["cc_style"] = style
    root["cc_parts"] = json.dumps({k: v.name for k, v in b.parts.items()})
    root["cc_meta"] = json.dumps(meta)
    return root


def parts_of(root):
    try:
        names = json.loads(root.get("cc_parts", "{}"))
    except ValueError:
        names = {}
    return {k: bpy.data.objects.get(v) for k, v in names.items() if bpy.data.objects.get(v) is not None}


def meta_of(root):
    try:
        return json.loads(root.get("cc_meta", "{}"))
    except ValueError:
        return {}
