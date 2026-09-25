"""Animation layer: turns simulation results into motion graphics."""

import json
import math
import random

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

from . import bl_utils as U
from . import catalog, lab, models
from .circuit import series_value

TEXT_TRACK_KEY = "cc_text_track"


# ------------------------------------------------------------------ timing
class Timing:
    """Maps video seconds to simulation values for a DC or transient result."""

    def __init__(self, result, start=0.0, end=None, time_scale=None):
        self.result = result
        self.start = float(start or 0.0)
        self.dc = result["type"] == "dc"
        if self.dc:
            self.scale = 1.0
            self.end = float(end) if end is not None else max(self.start + 5.0, U.frame_to_sec(bpy.context.scene.frame_end))
        else:
            dur = float(result["duration"])
            if time_scale is None:
                time_scale = (float(end) - self.start) / dur if end is not None else 1.0
            self.scale = float(time_scale)
            self.end = float(end) if end is not None else self.start + dur * self.scale
        if self.end <= self.start:
            raise ValueError("end must be after start")

    def sim_time(self, t):
        return (t - self.start) / self.scale

    def value(self, kind, key, field, t, default=0.0):
        if self.dc and t < self.start - 1e-9:
            return default
        return series_value(self.result, kind, key, field, None if self.dc else self.sim_time(t))

    def frames(self, step=1, pre=True):
        f0 = int(math.floor(U.sec_to_frame(self.start)))
        f1 = int(math.ceil(U.sec_to_frame(self.end)))
        frames = list(range(f0, f1 + 1, max(1, int(step))))
        if frames[-1] != f1:
            frames.append(f1)
        if pre and f0 > bpy.context.scene.frame_start:
            frames.insert(0, f0 - 1)
        return frames


def _result_and_timing(source, start, end, time_scale):
    result = lab.get_result(source)
    timing = Timing(result, start, end, time_scale)
    U.ensure_timeline(timing.end)
    return result, timing


def _max_abs_current(result):
    return float(result.get("max_current") or 0.0)


# ------------------------------------------------------------ current flow
def _paths(circ, include_components=True):
    """[(kind, key, points)] for every wire (and, optionally, two-terminal components)."""
    out = []
    for wid in circ.wires:
        out.append(("wires", wid, circ.wire_points(wid)))
    if include_components:
        for cid, comp in circ.components.items():
            t = comp["type"]
            if t in ("capacitor", "ground", "junction", "chip", "npn", "pnp", "potentiometer", "voltmeter"):
                continue
            _, order = catalog.terminals_of(t, comp["params"])
            if len(order) != 2:
                continue
            a = circ.terminal_world("%s.%s" % (cid, order[0]))
            b = circ.terminal_world("%s.%s" % (cid, order[1]))
            out.append(("components", cid, [a, b]))
    return out


def _particle_mesh(radius, charge):
    name = "cc_%s_mesh_%.3f" % (charge, radius)
    me = bpy.data.meshes.get(name)
    if me is None:
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=radius)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for poly in me.polygons:
            poly.use_smooth = True
    return me


def _speed(i, i_ref, speed, scaling, max_speed):
    if i_ref <= 0:
        return 0.0
    x = abs(i) / i_ref
    if scaling == "sqrt":
        x = math.sqrt(x)
    elif scaling == "log":
        x = math.log10(1 + 9 * x)
    v = min(speed * x, max_speed)
    return math.copysign(v, i)


def animate_current_flow(start=0.0, end=None, source="auto", mode="electron", density=2.5, speed=1.5,
                         reference_current=None, scaling="linear", max_speed=6.0, particle_radius=0.06, color=None,
                         include_components=True, key_step=1, time_scale=None, min_current=1e-7, glow=3.0,
                         clear=True, fade_in=0.0, seed=0, visible_before_start=False):
    """Create particles that travel along every wire with speed proportional to the simulated current.

    mode: 'electron' (blue electrons move against conventional current) or 'conventional'
    (red positive charges move with the current) or 'both'.
    Particles are hidden before `start` (fading in over `fade_in` seconds) unless visible_before_start.
    """
    circ = lab.load_circuit()
    result, timing = _result_and_timing(source, start, end, time_scale)
    col = U.collection(lab.COL_FLOW)
    if clear:
        U.clear_collection(lab.COL_FLOW)
    i_ref = float(reference_current) if reference_current else _max_abs_current(result)
    frames = timing.frames(key_step)
    fps = U.fps()
    rng = random.Random(seed)
    modes = ["electron", "conventional"] if mode == "both" else [mode]
    created = 0
    for m in modes:
        sign = -1.0 if m == "electron" else 1.0
        rgb = U.color(color) if color else (U.NAMED_COLORS["electron"] if m == "electron" else U.NAMED_COLORS["positive"])
        mat = U.material("cc_particle_%s_%s" % (m, "%.2f_%.2f_%.2f" % rgb), base=rgb, emission=rgb,
                         emission_strength=glow, roughness=0.3)
        mesh = _particle_mesh(particle_radius, m)
        if not mesh.materials:
            mesh.materials.append(mat)
        else:
            mesh.materials[0] = mat
        for kind, key, pts in _paths(circ, include_components):
            length = U.polyline_length(pts)
            if length < 1e-6:
                continue
            cum = U.cumulative_lengths(pts)
            n = max(1, int(round(length * density)))
            # distance travelled (along the path direction) at each keyed frame
            dists, d = [], 0.0
            prev_t = None
            for f in frames:
                t = U.frame_to_sec(f)
                if prev_t is not None:
                    tm = 0.5 * (t + prev_t)
                    cur = timing.value(kind, key, "current", tm)
                    if abs(cur) < min_current:
                        cur = 0.0
                    d += sign * _speed(cur, i_ref, speed, scaling, max_speed) * (t - prev_t)
                dists.append(d)
                prev_t = t
            phase0 = rng.random() * length / n
            for k in range(n):
                obj = bpy.data.objects.new("%s_%s_%s%d" % ("e" if m == "electron" else "q", key, "", k), mesh)
                U.link(obj, col)
                obj["cc_flow"] = key
                base = phase0 + k * length / n
                xs, ys, zs, interps = [], [], [], []
                last_s = None
                for dd in dists:
                    s = (base + dd) % length
                    p = U.point_along(pts, cum, s)
                    xs.append(p.x)
                    ys.append(p.y)
                    zs.append(p.z)
                    if last_s is not None and abs(s - last_s) > length * 0.5:
                        interps[-1] = "CONSTANT"  # wrapped around: jump instead of sliding back
                    interps.append("LINEAR")
                    last_s = s
                if all(abs(v - dists[0]) < 1e-9 for v in dists):
                    obj.location = (xs[0], ys[0], zs[0])
                else:
                    for axis, vals in enumerate((xs, ys, zs)):
                        U.set_keys(obj, "location", axis, frames, vals, interpolations=interps)
                f0 = U.sec_to_frame(timing.start)
                if fade_in and fade_in > 0:
                    U.set_keys(obj, "color", 3, [f0, f0 + fade_in * fps], [0.0, 1.0])
                elif not visible_before_start and f0 > bpy.context.scene.frame_start:
                    U.set_keys(obj, "color", 3, [f0 - 1, f0], [0.0, 1.0], interpolation="CONSTANT")
                created += 1
    return {"particles": created, "start": timing.start, "end": timing.end, "reference_current": i_ref,
            "time_scale": timing.scale, "mode": mode}


def add_current_arrows(start=0.0, end=None, source="auto", size=0.35, color="yellow", key_step=2, time_scale=None,
                       min_current=1e-7, reference_current=None):
    """Arrow on each wire pointing along conventional current; size follows |I|."""
    circ = lab.load_circuit()
    result, timing = _result_and_timing(source, start, end, time_scale)
    col = U.collection(lab.COL_EFFECTS)
    for obj in list(col.objects):
        if obj.get("cc_arrow"):
            U.delete_object_tree(obj)
    i_ref = float(reference_current) if reference_current else _max_abs_current(result)
    mat = U.material("cc_arrow_%s" % color, base=U.color(color), emission=U.color(color), emission_strength=1.5)
    frames = timing.frames(key_step)
    count = 0
    for wid in circ.wires:
        pts = circ.wire_points(wid)
        cum = U.cumulative_lengths(pts)
        if cum[-1] < 0.3:
            continue
        mid = cum[-1] / 2
        p = U.point_along(pts, cum, mid)
        q = U.point_along(pts, cum, mid + 0.05)
        direction = (q - p).normalized()
        arrow = U.cone("arrow_" + wid, size * 0.45, size, (0, 0, 0), "Z", mat, None, col, segments=16)
        arrow["cc_arrow"] = wid
        arrow.location = p + Vector((0, 0, 0.15))
        fwd = direction.to_track_quat("Z", "Y").to_euler()
        back = (-direction).to_track_quat("Z", "Y").to_euler()
        arrow.rotation_euler = fwd
        scales, rots = [], []
        for f in frames:
            cur = timing.value("wires", wid, "current", U.frame_to_sec(f))
            mag = 0.0 if abs(cur) < min_current or i_ref <= 0 else min(1.0, 0.25 + 0.75 * abs(cur) / i_ref)
            scales.append(mag)
            rots.append(fwd if cur >= 0 else back)
        for axis in range(3):
            U.set_keys(arrow, "scale", axis, frames, scales)
            U.set_keys(arrow, "rotation_euler", axis, frames, [r[axis] for r in rots], interpolation="CONSTANT")
        count += 1
    return {"arrows": count}


# -------------------------------------------------------- component effects
def _set_emission_keys(mat, frames, strengths):
    sock = U.bsdf_of(mat).inputs["Emission Strength"]
    U.set_keys(mat.node_tree, sock.path_from_id("default_value"), 0, frames, strengths)


def animate_component_effects(start=0.0, end=None, source="auto", time_scale=None, key_step=2, glow_strength=12.0,
                              light_power=15.0, motor_speed_scale=1.0, show_charge=True, charge_particles=12):
    """Drive LEDs, bulbs, motors, speakers, meters, fuses, switches and capacitor charge from results."""
    circ = lab.load_circuit()
    result, timing = _result_and_timing(source, start, end, time_scale)
    frames = timing.frames(key_step)
    times = [U.frame_to_sec(f) for f in frames]
    done = []
    for cid, comp in circ.components.items():
        root = lab.comp_root(cid)
        if root is None:
            continue
        parts = models.parts_of(root)
        t = comp["type"]
        if t in ("led", "bulb"):
            bright = [max(0.0, min(3.0, timing.value("components", cid, "brightness", tt))) for tt in times]
            glow = parts.get("glow")
            if glow is not None and glow.active_material is not None:
                _set_emission_keys(glow.active_material, frames, [b * glow_strength for b in bright])
            light = parts.get("light")
            if light is not None:
                _keys_scalar(light.data, "energy", frames, [b * light_power for b in bright])
            done.append(cid)
        elif t == "motor" and "rotor" in parts:
            rotor = parts["rotor"]
            ang, angles = rotor.rotation_euler.z, []
            prev = None
            for tt in times:
                if prev is not None:
                    rpm = timing.value("components", cid, "rpm", 0.5 * (tt + prev))
                    ang += rpm / 60.0 * 2 * math.pi * (tt - prev) * motor_speed_scale
                angles.append(ang)
                prev = tt
            U.set_keys(rotor, "rotation_euler", 2, frames, angles)
            done.append(cid)
        elif t == "speaker" and "cone" in parts:
            cone = parts["cone"]
            base = cone.location.z if cone.type != "EMPTY" else 0.0
            i_ref = _max_abs_current(result) or 1.0
            vals = [base + 0.08 * timing.value("components", cid, "current", tt) / i_ref for tt in times]
            if comp.get("style") == "schematic" or root.get("cc_style") == "schematic":
                for axis in (0, 1):
                    U.set_keys(cone, "scale", axis, frames, [1 + 2 * (v - base) for v in vals])
            else:
                U.set_keys(cone, "location", 2, frames, vals)
            done.append(cid)
        elif t in ("ammeter", "voltmeter", "dc_source") and "display" in parts:
            unit = "A" if t == "ammeter" else "V"
            field = "reading" if t != "dc_source" else "voltage"
            track = []
            for f, tt in zip(frames, times):
                v = timing.value("components", cid, field, tt)
                track.append([f, catalog.format_si(v, unit, 3)])
            set_text_track(parts["display"], track)
            done.append(cid)
        elif t == "fuse" and "element" in parts:
            blown_at = None
            for f, tt in zip(frames, times):
                if timing.value("components", cid, "blown", tt, default=False):
                    blown_at = f
                    break
            if blown_at is not None:
                el = parts["element"]
                _keys_scalar(el, "color", [blown_at - 1, blown_at], [1.0, 0.0], index=3, interp="CONSTANT")
                done.append(cid)
        elif t == "capacitor" and show_charge:
            _animate_charge(circ, cid, comp, root, parts, timing, frames, times, charge_particles)
            done.append(cid)
    # switch events from a transient run
    if not timing.dc:
        for ev in result.get("events", []):
            if "closed" in ev:
                cid = ev.get("component") or ev.get("id")
                video_t = timing.start + float(ev["time"]) * timing.scale
                animate_switch(cid, bool(ev["closed"]), max(timing.start, video_t - 0.25), 0.25)
                done.append(cid)
    return {"animated": sorted(set(done)), "start": timing.start, "end": timing.end, "time_scale": timing.scale}


def _keys_scalar(id_data, path, frames, values, index=0, interp="LINEAR"):
    return U.set_keys(id_data, path, index, frames, values, interpolation=interp)


def _animate_charge(circ, cid, comp, root, parts, timing, frames, times, n):
    col = U.collection(lab.COL_EFFECTS)
    for obj in list(col.objects):
        if obj.get("cc_charge_of") == cid:
            U.delete_object_tree(obj)
    pa, pb = parts.get("plate_a"), parts.get("plate_b")
    if pa is None or pb is None:
        return
    series = [timing.value("components", cid, "voltage", tt) for tt in times]
    if timing.dc:
        vmax = max(abs(v) for v in series) or 1.0
    else:
        vals = timing.result["components"].get(cid, {}).get("voltage", [0.0])
        vmax = max(abs(v) for v in vals) or 1.0
    schematic = root.get("cc_style") == "schematic"
    xa = -0.24 if schematic else -0.08
    xb = 0.24 if schematic else 0.08
    rows = max(1, int(math.ceil(n / 3.0)))
    pos_mat = U.material("cc_charge_pos", base=U.NAMED_COLORS["positive"], emission=U.NAMED_COLORS["positive"],
                         emission_strength=2.0)
    neg_mat = U.material("cc_charge_neg", base=U.NAMED_COLORS["electron"], emission=U.NAMED_COLORS["electron"],
                         emission_strength=2.0)
    for plate_x, plate_sign in ((xa, 1.0), (xb, -1.0)):
        for charge_sign, mat in ((1.0, pos_mat), (-1.0, neg_mat)):
            for k in range(n):
                row, colm = k % rows, k // rows
                y = -0.35 + 0.7 * (row + 0.5) / rows
                z = (colm - 1) * 0.2 if not schematic else 0.0
                x = plate_x + (0 if not schematic else (colm - 1) * 0.09 * (1 if plate_x > 0 else -1))
                if schematic:
                    y = -0.4 + 0.8 * (row + 0.5) / rows
                obj = U.sphere("%s_q%s%s%d" % (cid, "a" if plate_sign > 0 else "b", "p" if charge_sign > 0 else "n", k),
                               0.045, (0, 0, 0), mat, root, col, segments=12, rings=6)
                obj.location = (x, y, z)
                obj["cc_charge_of"] = cid
                scales = []
                for v in series:
                    frac = v / vmax  # >0: plate a positive
                    want = plate_sign * frac  # >0 means this plate has positive charge
                    visible = (want > 0 and charge_sign > 0 or want < 0 and charge_sign < 0) and k < abs(want) * n - 1e-9
                    scales.append(1.0 if visible else 0.0)
                for axis in range(3):
                    U.set_keys(obj, "scale", axis, frames, scales, interpolation="CONSTANT")


# ------------------------------------------------------------------ switches
def animate_switch(cid, closed, time, duration=0.3):
    """Animate a switch/push button lever to the closed/open position between time and time+duration."""
    root = lab.comp_root(cid)
    if root is None:
        raise KeyError("No component '%s'" % cid)
    parts = models.parts_of(root)
    meta = models.meta_of(root)
    lever = parts.get("lever")
    mode = meta.get("lever_mode")
    if lever is None or mode in (None, "none", "pot"):
        return {"animated": False}
    target = meta["closed_value"] if closed else meta["open_value"]
    other = meta["open_value"] if closed else meta["closed_value"]
    f0, f1 = U.sec_to_frame(time), U.sec_to_frame(time + duration)
    path, idx = {"rot_y": ("rotation_euler", 1), "rot_z": ("rotation_euler", 2), "loc_z": ("location", 2),
                 "loc_y": ("location", 1)}[mode]
    fc = U.fcurve_for(lever, path, idx)
    before = fc.evaluate(f0) if len(fc.keyframe_points) else other
    U.set_keys(lever, path, idx, [f0, f1], [before, target], interpolation="BEZIER", replace_range=True)
    U.ensure_timeline(time + duration)
    return {"animated": True, "frames": [f0, f1]}


# --------------------------------------------------------------- text tracks
def set_text_track(obj, track):
    """track: [[frame, text], ...] - body is swapped by a frame-change handler (text can't be keyframed)."""
    track = sorted(track, key=lambda x: x[0])
    compact = []
    for f, txt in track:
        if not compact or compact[-1][1] != txt:
            compact.append([f, txt])
    obj[TEXT_TRACK_KEY] = json.dumps(compact)
    update_text_tracks(bpy.context.scene)


@persistent
def update_text_tracks(scene, *_args):
    frame = scene.frame_current
    for obj in scene.objects:
        raw = obj.get(TEXT_TRACK_KEY)
        if raw is None or obj.type != "FONT":
            continue
        try:
            track = json.loads(raw)
        except ValueError:
            continue
        body = track[0][1] if track else ""
        for f, txt in track:
            if f <= frame:
                body = txt
            else:
                break
        if obj.data.body != body:
            obj.data.body = body


# ---------------------------------------------------------- voltage colours
def _colormap(x, name="thermal"):
    x = min(max(x, 0.0), 1.0)
    maps = {
        "thermal": [(0.0, (0.05, 0.15, 1.0)), (0.35, (0.0, 0.85, 0.9)), (0.6, (0.2, 1.0, 0.1)),
                    (0.8, (1.0, 0.85, 0.0)), (1.0, (1.0, 0.08, 0.02))],
        "blue_red": [(0.0, (0.05, 0.2, 1.0)), (1.0, (1.0, 0.05, 0.05))],
        "green": [(0.0, (0.02, 0.1, 0.02)), (1.0, (0.2, 1.0, 0.2))],
    }
    stops = maps.get(name, maps["thermal"])
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if x <= x1:
            f = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            return tuple(a + (b - a) * f for a, b in zip(c0, c1))
    return stops[-1][1]


def show_voltage_colors(start=0.0, end=None, source="auto", colormap="thermal", vmin=None, vmax=None, key_step=3,
                        time_scale=None, emission=1.5, legend=True, legend_position=None):
    """Colour each wire by its voltage (blue = low, red = high) - animated for transient results."""
    circ = lab.load_circuit()
    result, timing = _result_and_timing(source, start, end, time_scale)
    lo = float(vmin) if vmin is not None else float(result.get("min_voltage", 0.0))
    hi = float(vmax) if vmax is not None else float(result.get("max_voltage", 1.0))
    if timing.dc:
        vals = [w["voltage"] for w in result["wires"].values()]
        if vmin is None:
            lo = min(vals + [0.0])
        if vmax is None:
            hi = max(vals + [lo + 1e-9])
    span = (hi - lo) or 1.0
    frames = timing.frames(key_step, pre=not timing.dc)
    for wid in circ.wires:
        obj = lab.wire_object(wid)
        if obj is None:
            continue
        mat = U.material("cc_vwire_" + wid, base=(1, 1, 1), roughness=0.35, emission=(1, 1, 1),
                         emission_strength=emission, unique=True)
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        bsdf = U.bsdf_of(mat)
        base_path = bsdf.inputs["Base Color"].path_from_id("default_value")
        em_path = bsdf.inputs["Emission Color"].path_from_id("default_value")
        cols = [_colormap((timing.value("wires", wid, "voltage", U.frame_to_sec(f)) - lo) / span, colormap)
                for f in frames]
        if timing.dc:
            # fade from the normal wire colour to the voltage colour at `start`
            f0 = U.sec_to_frame(timing.start)
            f1 = f0 + 0.6 * U.fps()
            neutral = (0.95, 0.5, 0.3)
            for ch in range(3):
                U.set_keys(mat.node_tree, base_path, ch, [f0, f1], [neutral[ch], cols[-1][ch]])
                U.set_keys(mat.node_tree, em_path, ch, [f0, f1], [neutral[ch], cols[-1][ch]])
            strength = bsdf.inputs["Emission Strength"].path_from_id("default_value")
            U.set_keys(mat.node_tree, strength, 0, [f0, f1], [0.0, emission])
            continue
        for ch in range(3):
            vals = [c[ch] for c in cols]
            U.set_keys(mat.node_tree, base_path, ch, frames, vals)
            U.set_keys(mat.node_tree, em_path, ch, frames, vals)
    info = {"vmin": lo, "vmax": hi, "wires": len(circ.wires)}
    if legend:
        info["legend"] = _voltage_legend(circ, lo, hi, colormap, legend_position)
        f0 = U.sec_to_frame(timing.start)
        for obj in bpy.data.objects[info["legend"]].children:
            U.set_keys(obj, "color", 3, [f0, f0 + 0.6 * U.fps()], [0.0, 1.0])
    return info


def _voltage_legend(circ, lo, hi, colormap, position):
    col = U.collection(lab.COL_ANNOTATIONS)
    for obj in list(col.objects):
        if obj.get("cc_legend"):
            U.delete_object_tree(obj)
    (x0, y0, _), (x1, y1, _) = lab.circuit_bounds(circ)
    pos = position or [x1 + 1.2, (y0 + y1) / 2 - 1.5, circ.settings.get("height", 0.3)]
    root = U.empty("VoltageLegend", pos, None, col)
    root["cc_legend"] = True
    steps = 12
    for i in range(steps):
        c = _colormap(i / (steps - 1), colormap)
        mat = U.material("cc_legend_%s_%d" % (colormap, i), base=c, emission=c, emission_strength=1.5)
        U.box("VoltageLegend_%d" % i, (0.35, 3.0 / steps, 0.05), (0, i * 3.0 / steps, 0), mat, root, col)
    lm = lab.label_material()
    U.text("VoltageLegend_hi", catalog.format_si(hi, "V"), 0.25, (0.35, 3.0 - 0.1, 0), lm, root, col, align="LEFT")
    U.text("VoltageLegend_lo", catalog.format_si(lo, "V"), 0.25, (0.35, 0.0, 0), lm, root, col, align="LEFT")
    U.text("VoltageLegend_t", "Voltage", 0.25, (0, 3.35, 0), lm, root, col)
    return root.name


# ------------------------------------------------------- appear / disappear
def _renderables(objs):
    return [o for o in objs if o.type in ("MESH", "CURVE", "FONT")]


def animate_visibility(targets, action="appear", time=0.0, duration=0.5, style="fade", stagger=0.0, overshoot=1.15):
    """Make objects appear/disappear.

    style: 'fade' (alpha), 'pop' (scale with overshoot), 'grow' (scale), 'drop' (fall from above),
    'draw' (wires/curves draw themselves along their length), 'instant'.
    stagger: extra delay (s) between consecutive targets for cascading reveals.
    """
    circ = lab.load_circuit()
    if isinstance(targets, str):
        targets = [targets]
    appear = action in ("appear", "in", "show")
    total = 0
    for n, target in enumerate(targets):
        t0 = float(time) + n * float(stagger or 0.0)
        f0, f1 = U.sec_to_frame(t0), U.sec_to_frame(t0 + duration)
        objs = lab.resolve_objects(target, circ)
        tops = [o for o in objs if o.parent is None or o.parent not in objs]
        if style == "fade" or style == "instant":
            for o in _renderables(objs):
                if style == "instant":
                    U.set_keys(o, "color", 3, [f0 - 1, f0], [0.0, 1.0] if appear else [1.0, 0.0],
                               interpolation="CONSTANT")
                else:
                    U.set_keys(o, "color", 3, [f0, f1], [0.0, 1.0] if appear else [1.0, 0.0], interpolation="BEZIER")
                o.color[3] = 1.0
        elif style == "draw":
            for o in objs:
                if o.type == "CURVE":
                    U.set_keys(o.data, "bevel_factor_end", 0, [f0, f1], [0.0, 1.0] if appear else [1.0, 0.0],
                               interpolation="BEZIER")
                elif o.type in ("MESH", "FONT"):
                    U.set_keys(o, "color", 3, [f0, f1], [0.0, 1.0] if appear else [1.0, 0.0], interpolation="BEZIER")
        elif style in ("pop", "grow"):
            for o in tops:
                if o.type == "CURVE" and o.get("cc_wire"):
                    U.set_keys(o.data, "bevel_factor_end", 0, [f0, f1], [0.0, 1.0] if appear else [1.0, 0.0])
                    continue
                s = list(o.scale)
                if appear:
                    fm = f0 + 0.7 * (f1 - f0)
                    for axis in range(3):
                        if style == "pop":
                            U.set_keys(o, "scale", axis, [f0, fm, f1], [0.0, s[axis] * overshoot, s[axis]],
                                       interpolation="BEZIER")
                        else:
                            U.set_keys(o, "scale", axis, [f0, f1], [0.0, s[axis]], interpolation="BEZIER")
                else:
                    for axis in range(3):
                        U.set_keys(o, "scale", axis, [f0, f1], [s[axis], 0.0], interpolation="BEZIER")
        elif style == "drop":
            for o in tops:
                z = o.location.z
                vals = [z + 4.0, z] if appear else [z, z + 4.0]
                U.set_keys(o, "location", 2, [f0, f1], vals, interpolation="BEZIER")
                for rend in _renderables([o] + list(o.children_recursive)):
                    U.set_keys(rend, "color", 3, [f0, f0 + 0.3 * (f1 - f0)], [0.0, 1.0] if appear else [1.0, 1.0])
        else:
            raise ValueError("Unknown style '%s'" % style)
        total += len(objs)
        U.ensure_timeline(t0 + duration)
    return {"objects": total}


def animate_transform(target, time=0.0, duration=1.0, location=None, rotation=None, scale=None, relative=False):
    """Keyframe a smooth move/rotate/scale of a component or object (degrees for rotation)."""
    objs = lab.resolve_objects(target, include_children=False)
    f0, f1 = U.sec_to_frame(time), U.sec_to_frame(time + duration)
    for o in objs:
        if location is not None:
            for axis in range(3):
                start = o.location[axis]
                end = start + location[axis] if relative else location[axis]
                U.set_keys(o, "location", axis, [f0, f1], [start, end], interpolation="BEZIER")
        if rotation is not None:
            for axis in range(3):
                start = o.rotation_euler[axis]
                end = start + math.radians(rotation[axis]) if relative else math.radians(rotation[axis])
                U.set_keys(o, "rotation_euler", axis, [f0, f1], [start, end], interpolation="BEZIER")
        if scale is not None:
            sc = [scale] * 3 if isinstance(scale, (int, float)) else scale
            for axis in range(3):
                start = o.scale[axis]
                end = start * sc[axis] if relative else sc[axis]
                U.set_keys(o, "scale", axis, [f0, f1], [start, end], interpolation="BEZIER")
    U.ensure_timeline(time + duration)
    return {"objects": [o.name for o in objs]}


def highlight(targets, time=0.0, duration=1.5, color="yellow", pulses=2, radius=None, style="ring"):
    """Draw attention to components: a glowing ring pulses around each target (and the part bounces)."""
    circ = lab.load_circuit()
    if isinstance(targets, str):
        targets = [targets]
    col = U.collection(lab.COL_EFFECTS)
    rgb = U.color(color)
    mat = U.material("cc_halo_%s" % str(color), base=rgb, emission=rgb, emission_strength=6.0)
    made = []
    for n, target in enumerate(targets):
        pos = lab.target_point(target, circ)
        r = float(radius) if radius else (1.25 if target in circ.components else 0.6)
        halo = U.torus("halo_%s_%d" % (target, int(time * 100)), r, 0.04, (0, 0, 0), mat, None, col)
        halo.location = pos
        halo["cc_highlight"] = target
        f0 = U.sec_to_frame(time)
        f1 = U.sec_to_frame(time + duration)
        frames, alphas, scales = [], [], []
        for i in range(pulses * 8 + 1):
            f = f0 + (f1 - f0) * i / (pulses * 8)
            phase = (i % 8) / 8.0
            frames.append(f)
            alphas.append(0.0 if i in (0, pulses * 8) else 0.4 + 0.6 * math.sin(math.pi * phase))
            scales.append(0.9 + 0.2 * phase)
        U.set_keys(halo, "color", 3, frames, alphas)
        for axis in range(3):
            U.set_keys(halo, "scale", axis, frames, scales)
        if style == "ring+bounce" and target in circ.components:
            root = lab.comp_root(target)
            s = list(root.scale)
            for axis in range(3):
                U.set_keys(root, "scale", axis, [f0, f0 + 5, f0 + 10], [s[axis], s[axis] * 1.2, s[axis]],
                           interpolation="BEZIER")
        made.append(halo.name)
    U.ensure_timeline(time + duration)
    return {"highlights": made}
