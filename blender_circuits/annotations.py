"""Teaching annotations: labels, callouts, arrows, titles, live readouts, plots, wire close-ups."""

import math
import random

import bpy
from mathutils import Vector

from . import animation as A
from . import bl_utils as U
from . import catalog, lab
from . import scene_tools as S


def _col():
    return U.collection(lab.COL_ANNOTATIONS)


def _unique(name):
    base, i = name, 1
    while bpy.data.objects.get(name) is not None:
        i += 1
        name = "%s.%d" % (base, i)
    return name


def _text_mat(color, emission=0.6):
    if color is None:
        return lab.label_material()
    rgb = U.color(color)
    return U.material("cc_text_%.3f_%.3f_%.3f" % rgb, base=rgb, emission=rgb, emission_strength=emission)


def _timed(objs, start, end, fade):
    """Fade objects in at start and out at end (seconds, either may be None)."""
    if start is None and end is None:
        return
    fps = U.fps()
    fade = max(float(fade or 0.0), 1.0 / fps)
    for o in objs:
        if o.type not in ("MESH", "CURVE", "FONT"):
            continue
        frames, vals = [], []
        if start is not None:
            f0 = U.sec_to_frame(start)
            frames += [f0, f0 + fade * fps]
            vals += [0.0, 1.0]
        if end is not None:
            f1 = U.sec_to_frame(end)
            frames += [f1 - fade * fps, f1]
            vals += [1.0, 0.0]
        U.set_keys(o, "color", 3, frames, vals, interpolation="BEZIER", replace_range=False)
    if end is not None:
        U.ensure_timeline(end)
    elif start is not None:
        U.ensure_timeline(start + fade)


def _hud_fraction(size, default=0.05):
    """HUD text size is a fraction of screen height; values that look like 3D sizes fall back to a default."""
    return size if size is not None and size <= 0.2 else default


def _place(obj, position, hud, face_camera, rotation=None):
    if hud:
        S.attach_to_hud(obj, position)
        return
    obj.location = position
    if rotation is not None:
        obj.rotation_euler = [math.radians(r) for r in rotation]
    if face_camera:
        cam = S.ensure_camera()
        con = obj.constraints.new("COPY_ROTATION")
        con.target = cam


def add_label(text, position=None, target=None, offset=(0, 0.9, 0.2), size=0.35, color=None, align="CENTER",
              face_camera=False, hud=False, start=None, end=None, fade=0.4, name=None, rotation=None, bold=False):
    """3D text. Give a world position, or a target (component/wire/terminal) plus offset.
    hud=True pins it to the screen: position is then [x, y] in -1..1 screen coordinates."""
    if position is None and target is None and not hud:
        raise ValueError("Give position or target")
    if hud:
        pos = list(position or [0, 0.8])
        size_world = S.hud_size(_hud_fraction(size, 0.06))
    else:
        pos = list(position) if position is not None else [a + b for a, b in zip(lab.target_point(target), offset)]
        size_world = size
    obj = U.text(_unique(name or "Label"), text, size_world, (0, 0, 0), _text_mat(color), None, _col(), align=align,
                 bold=bold)
    obj["cc_annotation"] = "label"
    _place(obj, pos, hud, face_camera, rotation)
    _timed([obj], start, end, fade)
    return {"name": obj.name}


def add_arrow(start_point, end_point, color="yellow", thickness=0.05, head_size=None, time=None, draw_duration=0.6,
              end=None, name=None, curved=0.0):
    """3D arrow between two points or targets (component ids / terminal refs / [x,y,z]).
    curved > 0 bends it into an arc (height of the arc)."""
    p0 = Vector(lab.target_point(start_point))
    p1 = Vector(lab.target_point(end_point))
    head = float(head_size or thickness * 4)
    direction = (p1 - p0)
    if direction.length < 1e-6:
        raise ValueError("Arrow start and end are the same point")
    shaft_end = p1 - direction.normalized() * head * 1.5
    pts = []
    n = 24 if curved else 1
    for i in range(n + 1):
        f = i / n
        p = p0.lerp(shaft_end, f)
        p.z += curved * 4 * f * (1 - f)
        pts.append(tuple(p))
    rgb = U.color(color)
    mat = U.material("cc_arrow_%.3f_%.3f_%.3f" % rgb, base=rgb, emission=rgb, emission_strength=1.2)
    nm = _unique(name or "Arrow")
    shaft = U.poly_curve(nm, pts, thickness, mat, None, _col())
    tail_dir = Vector(pts[-1]) - Vector(pts[-2])
    cone = U.cone(nm + "_head", head, head * 1.6, (0, 0, 0), "Z", mat, None, _col(), segments=20)
    cone.location = Vector(pts[-1]) + tail_dir.normalized() * head * 0.8
    cone.rotation_euler = tail_dir.to_track_quat("Z", "Y").to_euler()
    shaft["cc_annotation"] = "arrow"
    cone["cc_annotation"] = "arrow"
    if time is not None:
        f0, f1 = U.sec_to_frame(time), U.sec_to_frame(time + draw_duration)
        U.set_keys(shaft.data, "bevel_factor_end", 0, [f0, f1], [0.0, 1.0], interpolation="BEZIER")
        U.set_keys(cone, "color", 3, [f1 - 2, f1], [0.0, 1.0])
        U.ensure_timeline(time + draw_duration)
    if end is not None:
        _timed([shaft, cone], None, end, 0.3)
    return {"name": shaft.name, "head": cone.name}


def add_callout(text, target, offset=(1.5, 1.5, 0.8), size=0.4, color=None, line_color="white", start=None,
                end=None, fade=0.4, face_camera=False, name=None):
    """Text bubble with a leader line pointing at a component / terminal / point."""
    tp = Vector(lab.target_point(target))
    tpos = tp + Vector(offset)
    nm = _unique(name or "Callout")
    lc = U.color(line_color)
    lmat = U.material("cc_callout_line_%.3f_%.3f_%.3f" % lc, base=lc, emission=lc, emission_strength=1.0)
    txt = U.text(nm, text, size, (0, 0, 0), _text_mat(color), None, _col(), align="LEFT", valign="BOTTOM")
    _place(txt, tuple(tpos + Vector((0.1, 0, 0.05))), False, face_camera)
    line = U.poly_curve(nm + "_line", [tuple(tp), tuple(tp + Vector(offset) * 0.92), tuple(tpos)], 0.015, lmat,
                        None, _col())
    dot = U.sphere(nm + "_dot", 0.06, tuple(tp), lmat, None, _col(), segments=12, rings=6)
    for o in (txt, line, dot):
        o["cc_annotation"] = "callout"
    if start is not None:
        f0 = U.sec_to_frame(start)
        U.set_keys(line.data, "bevel_factor_end", 0, [f0, f0 + fade * U.fps()], [0.0, 1.0], interpolation="BEZIER")
    _timed([txt, dot], start, end, fade)
    if end is not None:
        _timed([line], None, end, fade)
    return {"name": txt.name, "line": line.name}


def add_title(title, subtitle=None, time=0.0, duration=3.0, position="center", size=0.09, color=None,
              subtitle_color=None, fade=0.5, background=False):
    """Screen-space title card (pinned to the camera). position: center/top/bottom or [x, y]."""
    anchors = {"center": [0, 0.08], "top": [0, 0.78], "bottom": [0, -0.7], "top_left": [-0.92, 0.8]}
    pos = anchors.get(position, position) if isinstance(position, str) else list(position)
    align = "LEFT" if position == "top_left" else "CENTER"
    t = U.text(_unique("Title"), title, S.hud_size(size), (0, 0, 0), _text_mat(color, 1.0), None, _col(),
               align=align, bold=True)
    t["cc_annotation"] = "title"
    S.attach_to_hud(t, pos)
    objs = [t]
    if subtitle:
        s = U.text(_unique("Subtitle"), subtitle, S.hud_size(size * 0.5), (0, 0, 0),
                   _text_mat(subtitle_color or (0.75, 0.8, 0.9), 0.6), None, _col(), align=align)
        S.attach_to_hud(s, [pos[0], pos[1] - size * 1.6])
        s["cc_annotation"] = "title"
        objs.append(s)
    if background:
        bg = U.box(_unique("TitleBg"), (1, 1, 0.001), (0, 0, 0), U.material("cc_title_bg", base=(0, 0, 0), alpha=0.6),
                   None, _col())
        S.attach_to_hud(bg, [0, pos[1] - size * 0.5], depth_offset=0.01)
        hw, hh = S.hud_extent()
        bg.scale = (hw * 2, S.hud_size(size) * (4.0 if subtitle else 2.5), 1)
        objs.append(bg)
    _timed(objs, time, time + duration if duration else None, fade)
    return {"names": [o.name for o in objs]}


def add_readout(component, quantity="current", position=None, prefix=None, source="auto", start=0.0, end=None,
                time_scale=None, size=0.3, color=None, hud=False, digits=3, key_step=2, name=None,
                offset=(0, 1.2, 0.3)):
    """Live numeric readout of a simulated quantity (current, voltage, power, charge, brightness, rpm...)."""
    result, timing = A._result_and_timing(source, start, end, time_scale)
    circ = lab.load_circuit()
    kind = "wires" if component in circ.wires else "components"
    units = {"current": "A", "voltage": "V", "power": "W", "charge": "C", "reading": "", "rpm": "rpm",
             "brightness": ""}
    unit = units.get(quantity, "")
    if unit == "" and quantity == "reading":
        unit = "A" if circ.components[component]["type"] == "ammeter" else "V"
    prefix = prefix if prefix is not None else "%s %s = " % (component, {"current": "I", "voltage": "V",
                                                                         "power": "P", "charge": "Q"}.get(quantity, quantity))
    if hud:
        pos = list(position or [0.6, -0.8])
        size_world = S.hud_size(_hud_fraction(size, 0.045))
    else:
        pos = list(position) if position is not None else [a + b for a, b in zip(lab.target_point(component), offset)]
        size_world = size
    obj = U.text(_unique(name or "Readout"), prefix, size_world, (0, 0, 0), _text_mat(color or "yellow", 1.0), None,
                 _col(), align="LEFT" if hud else "CENTER")
    obj["cc_annotation"] = "readout"
    _place(obj, pos, hud, False)
    track = []
    for f in timing.frames(key_step):
        v = timing.value(kind, component, quantity, U.frame_to_sec(f))
        if quantity == "brightness":
            txt = "%d %%" % round(100 * v)
        elif quantity == "rpm":
            txt = "%.0f rpm" % v
        else:
            txt = catalog.format_si(v, unit, digits)
        track.append([f, prefix + txt])
    A.set_text_track(obj, track)
    if timing.start > U.frame_to_sec(bpy.context.scene.frame_start) + 1e-6:
        _timed([obj], timing.start, None, 0.3)
    return {"name": obj.name}


def add_plot(signals, position=None, width=6.0, height=3.0, source="transient", start=0.0, end=None,
             time_scale=None, title=None, hud=False, rotation=(90, 0, 0), samples=200, marker=True,
             show_axes_labels=True, name=None, background=True, line_width=0.04, normalize=None):
    """Oscilloscope-style graph that draws itself in sync with the animation.

    signals: [{"component": "C1", "quantity": "voltage", "color": "yellow", "label": "V(C1)"}, ...]
    (a wire id can be used as component).  Requires a transient result.
    normalize: scale every trace to its own range (default: automatically when units differ).
    hud=True pins the plot to the screen with position = [x, y] of its lower-left corner (-1..1).
    """
    result, timing = A._result_and_timing(source, start, end, time_scale)
    if result["type"] != "transient":
        raise ValueError("add_plot needs a transient simulation (run simulate_transient first)")
    circ = lab.load_circuit()
    col = _col()
    nm = _unique(name or "Plot")
    root = U.empty(nm, (0, 0, 0), None, col, display="PLAIN_AXES", size=0.2)
    root["cc_annotation"] = "plot"
    if isinstance(signals, dict):
        signals = [signals]
    unit_of = {"voltage": "V", "current": "A", "power": "W", "charge": "C", "reading": "", "rpm": "rpm"}
    duration = result["duration"]
    series = []
    for sig in signals:
        cid = sig["component"]
        kind = "wires" if cid in circ.wires else "components"
        q = sig.get("quantity", "voltage")
        vals = [A.series_value(result, kind, cid, q, duration * i / (samples - 1)) for i in range(samples)]
        series.append((sig, vals, kind, q))
    units = {unit_of.get(q, q) for _, _, _, q in series}
    if normalize is None:
        normalize = len(units) > 1

    def rng(vals):
        lo, hi = min(0.0, min(vals)), max(0.0, max(vals))
        if hi - lo < 1e-15:
            hi = lo + 1.0
        pad = 0.08 * (hi - lo)
        return (lo - pad if lo < 0 else lo), hi + pad

    if normalize:
        ranges = [rng(vals) for _, vals, _, _ in series]
    else:
        allv = [v for _, vals, _, _ in series for v in vals]
        ranges = [rng(allv)] * len(series)
    axis_mat = lab.label_material()
    if background:
        U.box(nm + "_bg", (width + 1.0, height + 0.9, 0.02), (width / 2 - 0.1, height / 2 + 0.1, -0.03),
              U.material("cc_plot_bg", base=(0.01, 0.015, 0.03), roughness=0.8, alpha=0.85), root, col)
    lo0, hi0 = ranges[0]
    zero_y = height * (0 - lo0) / (hi0 - lo0) if lo0 < 0 and not normalize else 0.0
    U.poly_curve(nm + "_xaxis", [(0, zero_y, 0), (width, zero_y, 0)], 0.012, axis_mat, root, col)
    U.poly_curve(nm + "_yaxis", [(0, 0, 0), (0, height, 0)], 0.012, axis_mat, root, col)
    grid_mat = U.material("cc_plot_grid", base=(0.3, 0.35, 0.45), emission=(0.3, 0.35, 0.45), emission_strength=0.3)
    for k in range(1, 5):
        y = height * k / 4
        U.poly_curve(nm + "_grid%d" % k, [(0, y, -0.01), (width, y, -0.01)], 0.005, grid_mat, root, col)
    ts = 0.22
    if show_axes_labels:
        if normalize:
            U.text(nm + "_hi", "max", ts, (-0.12, height, 0), axis_mat, root, col, align="RIGHT")
            U.text(nm + "_lo", "min" if any(r[0] < 0 for r in ranges) else "0", ts, (-0.12, 0, 0), axis_mat, root,
                   col, align="RIGHT")
        else:
            u = unit_of.get(series[0][3], "")
            U.text(nm + "_hi", catalog.format_si(hi0, u), ts, (-0.12, height, 0), axis_mat, root, col, align="RIGHT")
            U.text(nm + "_lo", catalog.format_si(lo0, u), ts, (-0.12, 0, 0), axis_mat, root, col, align="RIGHT")
        U.text(nm + "_t0", "0", ts, (0, -0.25, 0), axis_mat, root, col)
        U.text(nm + "_t1", catalog.format_si(duration, "s"), ts, (width, -0.25, 0), axis_mat, root, col)
    if title:
        U.text(nm + "_title", title, ts * 1.4, (width / 2, height + 0.35, 0), axis_mat, root, col)
    frames = timing.frames(2, pre=False)
    sim_ts = [min(max(timing.sim_time(U.frame_to_sec(f)), 0.0), duration) for f in frames]
    ly = height + 0.05
    for idx, (sig, vals, kind, q) in enumerate(series):
        lo2, hi2 = ranges[idx]
        rgb = U.color(sig.get("color") or ["yellow", "cyan", "magenta", "green"][idx % 4])
        mat = U.material("cc_trace_%.3f_%.3f_%.3f" % rgb, base=rgb, emission=rgb, emission_strength=2.0)
        pts = [(width * i / (samples - 1), height * (v - lo2) / (hi2 - lo2), 0.0) for i, v in enumerate(vals)]
        trace = U.poly_curve("%s_trace%d" % (nm, idx), pts, line_width, mat, root, col)
        trace.data.bevel_factor_mapping_end = "SPLINE"  # factor = fraction of arc length
        # reveal the trace so that its tip is always at the current simulation time
        cum = U.cumulative_lengths(pts)
        total = cum[-1] or 1.0
        fracs = []
        for st in sim_ts:
            fi = st / duration * (samples - 1)
            i0 = min(int(fi), samples - 2)
            fracs.append((cum[i0] + (cum[i0 + 1] - cum[i0]) * (fi - i0)) / total)
        U.set_keys(trace.data, "bevel_factor_end", 0, frames, fracs)
        if marker:
            dot = U.sphere("%s_marker%d" % (nm, idx), line_width * 2.5, (0, 0, 0), mat, root, col, segments=12,
                           rings=6)
            xs = [width * st / duration for st in sim_ts]
            ys = [height * (A.series_value(result, kind, sig["component"], q, st) - lo2) / (hi2 - lo2) for st in sim_ts]
            U.set_keys(dot, "location", 0, frames, xs)
            U.set_keys(dot, "location", 1, frames, ys)
        label = sig.get("label") or "%s %s" % (sig["component"], q)
        if normalize:
            label += " (max %s)" % catalog.format_si(max(abs(v) for v in vals), unit_of.get(q, ""))
        U.text("%s_legend%d" % (nm, idx), label, ts, (width + 0.15, ly - 0.35 * idx - 0.2, 0), mat, root, col,
               align="LEFT")
    if hud:
        S.attach_to_hud(root, list(position or [-0.95, -0.95]))
        hw, hh = S.hud_extent()
        sc = (hh * 0.7) / (height + 1.0)
        root.scale = (sc, sc, sc)
    else:
        if position is None:
            (x0, y0, _), (x1, y1, _) = lab.circuit_bounds(circ)
            position = [x1 + 1.5, y1, 0.5]
        root.location = position
        root.rotation_euler = [math.radians(r) for r in rotation]
    return {"name": root.name, "ranges": ranges, "normalized": bool(normalize)}


def add_wire_closeup(position=(0, -8, 2), length=6.0, radius=1.0, wire=None, source="auto", start=0.0, end=None,
                     time_scale=None, electrons=60, ions=None, drift_speed=0.6, thermal=0.15, labels=True,
                     rotation=(0, 0, 0), name=None, key_step=2, seed=1):
    """A magnified, see-through piece of wire: a copper ion lattice (vibrating) and free electrons that
    jitter randomly (thermal motion) while slowly drifting.  If `wire` is given, the drift follows that
    wire's simulated current (direction and magnitude)."""
    rng = random.Random(seed)
    col = _col()
    nm = _unique(name or "WireCloseup")
    root = U.empty(nm, position, None, col)
    root.rotation_euler = [math.radians(r) for r in rotation]
    root["cc_annotation"] = "closeup"
    glass = U.material("cc_closeup_glass", base=(0.85, 0.6, 0.4), roughness=0.1, transmission=0.9, alpha=0.18)
    U.cylinder(nm + "_tube", radius, length, (0, 0, 0), "X", glass, root, col, segments=48)
    ion_mat = U.material("cc_ion", base=(0.8, 0.42, 0.22), metallic=0.5, roughness=0.45)
    e_mat = U.material("cc_particle_closeup", base=U.NAMED_COLORS["electron"], emission=U.NAMED_COLORS["electron"],
                       emission_strength=6.0)
    spacing = 0.7 * radius
    nx = max(2, int(length / spacing))
    ion_objs = []
    for i in range(nx):
        for j in range(-2, 3):
            for k in range(-2, 3):
                y, z = (j + 0.5 * (i % 2)) * spacing, k * spacing
                if y * y + z * z > (radius * 0.8) ** 2:
                    continue
                x = -length / 2 + (i + 0.5) * length / nx
                ion_objs.append((x, y, z))
    if ions is not None:
        ion_objs = ion_objs[: int(ions)]
    ion_mesh = _shared_sphere("cc_ion_mesh", 0.13 * radius, ion_mat)
    for n, p in enumerate(ion_objs):
        o = bpy.data.objects.new("%s_ion%d" % (nm, n), ion_mesh)
        o.parent = root
        o.location = p
        U.link(o, col)
        _noise(o, 0.03, rng)
    e_mesh = _shared_sphere("cc_closeup_e_mesh", 0.08 * radius, e_mat)
    if wire is not None:
        result, timing = A._result_and_timing(source, start, end, time_scale)
        i_ref = float(result.get("max_current") or 1.0)
    else:
        timing = None
        U.ensure_timeline(end if end is not None else start + 10)
    t_end = timing.end if timing else (end if end is not None else U.frame_to_sec(bpy.context.scene.frame_end))
    f0 = int(U.sec_to_frame(start))
    f1 = int(math.ceil(U.sec_to_frame(t_end)))
    frames = list(range(f0, f1 + 1, key_step))
    dists, d, prev = [], 0.0, None
    for f in frames:
        t = U.frame_to_sec(f)
        if prev is not None:
            if timing:
                cur = timing.value("wires", wire, "current", 0.5 * (t + prev))
                v = -drift_speed * cur / i_ref  # electrons drift against conventional current
            else:
                v = drift_speed
            d += v * (t - prev)
        dists.append(d)
        prev = t
    for n in range(int(electrons)):
        r = radius * 0.85 * math.sqrt(rng.random())
        a = rng.random() * 2 * math.pi
        x0 = rng.uniform(-length / 2, length / 2)
        o = bpy.data.objects.new("%s_e%d" % (nm, n), e_mesh)
        o.parent = root
        o.location = (x0, r * math.cos(a), r * math.sin(a))
        U.link(o, col)
        xs, interps, last = [], [], None
        for dd in dists:
            x = (x0 + dd + length / 2) % length - length / 2
            if last is not None and abs(x - last) > length / 2:
                interps[-1] = "CONSTANT"
            xs.append(x)
            interps.append("LINEAR")
            last = x
        U.set_keys(o, "location", 0, frames, xs, interpolations=interps)
        _noise(o, thermal, rng, axes=(1, 2), extra_x=True)
    if labels:
        # lying on the local XY plane just above the tube (rotate the whole close-up to aim it at the camera)
        lm = lab.label_material()
        U.text(nm + "_lbl1", "copper ions (fixed, vibrating)", 0.3, (-length / 2, radius + 0.35, 0), lm, root, col,
               align="LEFT")
        U.text(nm + "_lbl2", "free electrons (drifting)", 0.3, (-length / 2, radius + 0.8, 0),
               _text_mat(U.NAMED_COLORS["electron"]), root, col, align="LEFT")
    return {"name": root.name, "ions": len(ion_objs), "electrons": int(electrons)}


def _shared_sphere(name, r, mat):
    me = bpy.data.meshes.get(name)
    if me is None:
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=r)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        me.materials.append(mat)
    return me


def _noise(obj, strength, rng, axes=(0, 1, 2), extra_x=False):
    """Procedural jitter via F-curve noise modifiers (no keyframes needed)."""
    use = list(axes) + ([0] if extra_x and 0 not in axes else [])
    for axis in use:
        fc = U.fcurve_for(obj, "location", axis)
        if not len(fc.keyframe_points):
            fc.keyframe_points.insert(bpy.context.scene.frame_start, obj.location[axis])
        mod = fc.modifiers.new("NOISE")
        mod.scale = 3.0 + rng.random() * 3
        mod.strength = strength * 2
        mod.phase = rng.random() * 100
        mod.blend_type = "ADD"


def clear_annotations(kind=None):
    """Delete annotations (all, or only one kind: label/arrow/callout/title/readout/plot/closeup)."""
    col = bpy.data.collections.get(lab.COL_ANNOTATIONS)
    if col is None:
        return {"deleted": 0}
    n = 0
    for obj in list(col.objects):
        try:
            if obj.parent is not None and obj.parent.name in col.objects:
                continue
            if kind is None or obj.get("cc_annotation") == kind:
                U.delete_object_tree(obj)
                n += 1
        except ReferenceError:
            pass
    return {"deleted": n}
