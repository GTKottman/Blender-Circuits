"""Command registry: every function here is callable over the socket as {"command": name, "params": {...}}."""

import contextlib
import inspect
import io
import json
import math
import traceback

import bpy

from . import animation as A
from . import annotations as N
from . import bl_utils as U
from . import catalog, examples, lab
from . import scene_tools as S
from .circuit import Circuit, summarize

COMMANDS = {}


def command(fn):
    COMMANDS[fn.__name__] = fn
    return fn


class CommandError(Exception):
    pass


def dispatch(name, params=None):
    params = dict(params or {})
    fn = COMMANDS.get(name)
    if fn is None:
        raise CommandError("Unknown command '%s'. Use list_commands to see what is available." % name)
    sig = inspect.signature(fn)
    accepts_kwargs = any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
    if not accepts_kwargs:
        unknown = [k for k in params if k not in sig.parameters]
        if unknown:
            raise CommandError("%s() got unknown parameter(s) %s. Accepted: %s" % (
                name, ", ".join(unknown), ", ".join(sig.parameters)))
    try:
        sig.bind(**params)
    except TypeError as exc:
        raise CommandError("%s(): %s" % (name, exc))
    return fn(**params)


def _json_safe(obj):
    return json.loads(json.dumps(obj, default=lambda o: list(o) if hasattr(o, "__iter__") else str(o)))


# ================================================================= general
@command
def ping():
    """Health check."""
    return {"pong": True, "blender": bpy.app.version_string}


@command
def list_commands():
    """All commands with their parameters and first docstring line."""
    out = {}
    for name, fn in sorted(COMMANDS.items()):
        doc = (inspect.getdoc(fn) or "").split("\n")[0]
        out[name] = {"params": str(inspect.signature(fn)), "doc": doc}
    return out


@command
def list_component_types():
    """Catalog of component types with terminals, default params and descriptions."""
    return catalog.describe_catalog()


@command
def get_scene_info():
    """Summary of the circuit, animation timeline, camera and annotations."""
    circ = lab.load_circuit()
    scene = bpy.context.scene
    comps = {}
    for cid, c in circ.components.items():
        comps[cid] = {"type": c["type"], "position": c["position"], "rotation": c["rotation"],
                      "params": c["params"], "terminals": {k: [round(x, 3) for x in v] for k, v in circ.terminals(cid).items()}}
    wires = {wid: {"from": w["from"], "to": w["to"]} for wid, w in circ.wires.items()}
    results = lab.load_results()
    ann = bpy.data.collections.get(lab.COL_ANNOTATIONS)
    cam = bpy.data.objects.get(S.CAMERA)
    return _json_safe({
        "settings": circ.settings,
        "components": comps,
        "wires": wires,
        "simulations_available": [k for k in results if k in ("dc", "transient")],
        "timeline": {"fps": U.fps(), "frame_start": scene.frame_start, "frame_end": scene.frame_end,
                     "duration_s": (scene.frame_end - scene.frame_start) / U.fps()},
        "camera": {"location": list(cam.location), "lens": cam.data.lens} if cam else None,
        "annotations": sorted(o.name for o in ann.objects if o.parent is None or o.get("cc_hud")) if ann else [],
        "render": {"engine": scene.render.engine, "resolution": [scene.render.resolution_x, scene.render.resolution_y]},
    })


# ================================================================= circuit
@command
def new_circuit(style="realistic", height=0.3, wire_look="copper", show_labels=True, show_values=True,
                clear_annotations=True, clear_animation=True):
    """Start a fresh circuit (removes existing components, wires and optionally annotations/animation)."""
    for name in (lab.COL_COMPONENTS, lab.COL_WIRES, lab.COL_FLOW, lab.COL_EFFECTS):
        U.clear_collection(name)
    if clear_annotations:
        U.clear_collection(lab.COL_ANNOTATIONS)
    S.remove_startup_objects()
    circ = Circuit()
    circ.settings.update({"style": style, "height": height, "wire_look": wire_look, "show_labels": show_labels,
                          "show_values": show_values})
    lab.save_circuit(circ)
    txt = bpy.data.texts.get(lab.RESULTS_TEXT)
    if txt:
        txt.clear()
    if clear_animation:
        for obj in list(bpy.data.objects):
            if obj.name in (S.CAMERA, S.CAMERA_TARGET):
                obj.animation_data_clear()
    return {"settings": circ.settings}


@command
def set_circuit_settings(style=None, wire_look=None, show_labels=None, show_values=None, height=None,
                         wire_radius=None, wire_resistance=None):
    """Change global circuit settings and rebuild (style: realistic|schematic, wire_look: copper|insulated|glass)."""
    circ = lab.load_circuit()
    for key, val in (("style", style), ("wire_look", wire_look), ("show_labels", show_labels),
                     ("show_values", show_values), ("height", height), ("wire_radius", wire_radius),
                     ("wire_resistance", wire_resistance)):
        if val is not None:
            circ.settings[key] = val
    lab.save_circuit(circ)
    lab.rebuild_all(circ)
    return {"settings": circ.settings}


@command
def add_component(type, id=None, position=(0, 0), rotation=0.0, params=None, label=None, style=None,
                  show_value=None, label_offset=None, **shorthand):
    """Add a component. Shorthand params allowed, e.g. add_component(type='resistor', resistance='4.7k')."""
    circ = lab.load_circuit()
    cid = circ.add_component(type, id, position, rotation, params, label, style, show_value, label_offset, **shorthand)
    lab.save_circuit(circ)
    lab.build_component(circ, cid)
    return {"id": cid, "type": circ.components[cid]["type"], "terminals": circ.terminals(cid),
            "params": circ.components[cid]["params"]}


@command
def add_components(components):
    """Add many components at once: [{"type":..., "id":..., "position":[x,y], "rotation":deg, ...}, ...]."""
    out = []
    circ = lab.load_circuit()
    for spec in components:
        spec = dict(spec)
        ctype = spec.pop("type")
        cid = circ.add_component(ctype, spec.pop("id", None), spec.pop("position", (0, 0)), spec.pop("rotation", 0.0),
                                 spec.pop("params", None), spec.pop("label", None), spec.pop("style", None),
                                 spec.pop("show_value", None), spec.pop("label_offset", None), **spec)
        out.append(cid)
    lab.save_circuit(circ)
    for cid in out:
        lab.build_component(circ, cid)
    return {"ids": out, "terminals": {cid: circ.terminals(cid) for cid in out}}


@command
def update_component(id, params=None, position=None, rotation=None, label=None, style=None, **shorthand):
    """Change a component's parameters / position / rotation / label and rebuild it (and its wires)."""
    circ = lab.load_circuit()
    circ.update_component(id, params, position, rotation, label, style, **shorthand)
    lab.save_circuit(circ)
    lab.build_component(circ, id)
    for wid in lab.wires_touching(circ, id):
        lab.build_wire(circ, wid)
    return {"id": id, "params": circ.components[id]["params"], "terminals": circ.terminals(id)}


@command
def remove_component(id):
    """Delete a component (and every wire attached to it)."""
    circ = lab.load_circuit()
    removed = circ.remove_component(id)
    lab.save_circuit(circ)
    U.delete_object_tree(lab.comp_root(id))
    for wid in removed:
        U.delete_object_tree(lab.wire_object(wid))
    lab._junction_dots(circ)
    return {"removed": id, "wires_removed": removed}


@command
def connect(a=None, b=None, id=None, via=None, route="auto", color=None, **kw):
    """Wire two terminals: connect(a='B1.+', b='R1.a'). 'from'/'to' also accepted.
    route: auto | hv (horizontal first) | vh | direct. via: list of [x, y] waypoints."""
    a = a or kw.pop("from", None) or kw.pop("start", None)
    b = b or kw.pop("to", None) or kw.pop("end", None)
    if kw:
        raise CommandError("connect(): unknown parameter(s) %s" % ", ".join(kw))
    if not a or not b:
        raise CommandError("connect() needs two terminal refs, e.g. a='B1.+', b='R1.a'")
    circ = lab.load_circuit()
    wid = circ.connect(a, b, id, via, route, color)
    lab.save_circuit(circ)
    lab.build_wire(circ, wid)
    return {"id": wid, "from": circ.wires[wid]["from"], "to": circ.wires[wid]["to"], "points": circ.wire_points(wid)}


@command
def connect_many(connections, route="auto"):
    """Many wires at once: [["B1.+", "R1.a"], {"from": "R1.b", "to": "LED1.anode", "via": [[6, 2]]}, ...]."""
    circ = lab.load_circuit()
    ids = []
    for c in connections:
        if isinstance(c, (list, tuple)):
            ids.append(circ.connect(c[0], c[1], route=route))
        else:
            ids.append(circ.connect(c.get("a") or c.get("from"), c.get("b") or c.get("to"), c.get("id"), c.get("via"),
                                    c.get("route", route), c.get("color")))
    lab.save_circuit(circ)
    for wid in ids:
        lab.build_wire(circ, wid)
    return {"ids": ids}


@command
def remove_wire(id):
    """Delete a wire."""
    circ = lab.load_circuit()
    circ.remove_wire(id)
    lab.save_circuit(circ)
    U.delete_object_tree(lab.wire_object(id))
    lab._junction_dots(circ)
    return {"removed": id}


@command
def get_circuit():
    """Full circuit model (components, params, wires, settings) plus world terminal positions."""
    circ = lab.load_circuit()
    data = circ.to_dict()
    data["terminal_positions"] = {cid: circ.terminals(cid) for cid in circ.components}
    return _json_safe(data)


@command
def rebuild():
    """Rebuild every component and wire from the stored model."""
    circ = lab.rebuild_all()
    return {"components": len(circ.components), "wires": len(circ.wires)}


@command
def set_switch(id, closed=True, time=None, duration=0.3):
    """Open/close a switch. Updates the model (for DC simulation) and, if time is given, animates the lever."""
    circ = lab.load_circuit()
    comp = circ.get(id)
    if comp["type"] not in ("switch", "push_button"):
        raise CommandError("'%s' is a %s, not a switch" % (id, comp["type"]))
    comp["params"]["closed"] = bool(closed)
    lab.save_circuit(circ)
    if time is None:
        lab.build_component(circ, id)
        return {"id": id, "closed": bool(closed)}
    return {"id": id, "closed": bool(closed), **A.animate_switch(id, bool(closed), time, duration)}


# ============================================================== simulation
@command
def simulate_dc():
    """Solve the DC operating point. Returns voltages/currents/power per component and wire (+ warnings)."""
    circ = lab.load_circuit()
    result = circ.simulate_dc()
    lab.save_result(result)
    return summarize(result)


@command
def simulate_transient(duration, dt=None, events=None, samples=400, start_from_dc=False):
    """Time-domain simulation (capacitors charge, inductors, AC sources, switch events).
    events: [{"time": 0.5, "component": "S1", "closed": true}, {"time": 2, "component": "RV1", "param": "position", "value": 0.2}]"""
    circ = lab.load_circuit()
    result = circ.simulate_transient(duration, dt, events, samples, start_from_dc)
    lab.save_result(result)
    return summarize(result)


@command
def get_results(source="auto", component=None, max_points=50):
    """Detailed simulation data. For transient results the series are downsampled to max_points."""
    result = lab.get_result(source)
    if result["type"] == "dc":
        data = result if component is None else {"components": {component: result["components"].get(component)},
                                                   "wires": {component: result["wires"].get(component)}}
        return _json_safe(data)
    times = result["times"]
    step = max(1, len(times) // int(max_points))
    idx = list(range(0, len(times), step))
    out = {"type": "transient", "duration": result["duration"], "times": [round(times[i], 6) for i in idx],
           "events": result.get("events", [])}
    for kind in ("components", "wires"):
        out[kind] = {}
        for key, series in result[kind].items():
            if component is not None and key != component:
                continue
            out[kind][key] = {f: [round(v[i], 6) if isinstance(v[i], float) else v[i] for i in idx]
                              for f, v in series.items() if f in ("current", "voltage", "power", "brightness", "charge", "reading")}
    return _json_safe(out)


# =============================================================== animation
@command
def animate_circuit(start=0.0, end=None, source="auto", mode="electron", time_scale=None, density=2.5, speed=1.5,
                    scaling="linear", max_speed=6.0, particle_radius=0.06, include_components=True, key_step=1,
                    show_charge=True, glow_strength=12.0, fade_in=0.0):
    """One call to bring the circuit to life: moving charges + glowing LEDs/bulbs, spinning motors,
    meter readouts, switch levers and capacitor charge, all driven by the latest (or chosen) simulation."""
    flow = A.animate_current_flow(start, end, source, mode, density, speed, None, scaling, max_speed, particle_radius,
                                  None, include_components, key_step, time_scale, fade_in=fade_in)
    fx = A.animate_component_effects(start, end, source, time_scale, max(1, key_step), glow_strength,
                                     show_charge=show_charge)
    return {"flow": flow, "effects": fx}


@command
def animate_current_flow(start=0.0, end=None, source="auto", mode="electron", density=2.5, speed=1.5,
                         reference_current=None, scaling="linear", max_speed=6.0, particle_radius=0.06, color=None,
                         include_components=True, key_step=1, time_scale=None, glow=3.0, fade_in=0.0,
                         visible_before_start=False):
    """Charges travelling along wires at a speed proportional to current.
    mode: electron | conventional | both.  scaling: linear | sqrt | log (compress big current ranges)."""
    return A.animate_current_flow(start, end, source, mode, density, speed, reference_current, scaling, max_speed,
                                  particle_radius, color, include_components, key_step, time_scale, glow=glow,
                                  fade_in=fade_in, visible_before_start=visible_before_start)


@command
def animate_component_effects(start=0.0, end=None, source="auto", time_scale=None, key_step=2, glow_strength=12.0,
                              light_power=15.0, show_charge=True):
    """LED/bulb glow, motor spin, speaker, meter displays, fuse, switch events and capacitor charge."""
    return A.animate_component_effects(start, end, source, time_scale, key_step, glow_strength, light_power,
                                       show_charge=show_charge)


@command
def add_current_arrows(start=0.0, end=None, source="auto", size=0.35, color="yellow", time_scale=None):
    """Arrows on each wire showing conventional current direction (size follows |I|)."""
    return A.add_current_arrows(start, end, source, size, color, time_scale=time_scale)


@command
def show_voltage_colors(start=0.0, end=None, source="auto", colormap="thermal", vmin=None, vmax=None,
                        time_scale=None, legend=True, legend_position=None):
    """Colour wires by voltage (colormap: thermal | blue_red | green) with an optional legend."""
    return A.show_voltage_colors(start, end, source, colormap, vmin, vmax, time_scale=time_scale, legend=legend,
                                 legend_position=legend_position)


@command
def animate_switch(id, closed=True, time=0.0, duration=0.3):
    """Animate a switch lever (visual only - use simulate_transient events to change the physics)."""
    return A.animate_switch(id, closed, time, duration)


@command
def animate_visibility(targets, action="appear", time=0.0, duration=0.5, style="fade", stagger=0.0):
    """Reveal / hide things. targets: ids, object names or keywords (all, components, wires, labels, flow,
    annotations, effects). style: fade | pop | grow | drop | draw | instant. stagger: cascade delay (s)."""
    return A.animate_visibility(targets, action, time, duration, style, stagger)


@command
def build_up_sequence(start=0.0, component_interval=0.6, wire_duration=0.5, style="pop", order=None,
                      hide_labels_until_end=False):
    """Classic 'assemble the circuit' reveal: components pop in one by one, then wires draw themselves."""
    circ = lab.load_circuit()
    ids = order or list(circ.order)
    t = float(start)
    for cid in ids:
        if cid in circ.components:
            A.animate_visibility([cid], "appear", t, 0.45, style)
            t += component_interval
    wires = list(circ.wires)
    for wid in wires:
        A.animate_visibility([wid], "appear", t, wire_duration, "draw")
        t += wire_duration * 0.6
    dots = [o.name for o in bpy.data.collections[lab.COL_WIRES].objects if o.get("cc_dot")] \
        if lab.COL_WIRES in bpy.data.collections else []
    if dots:
        A.animate_visibility(dots, "appear", t, 0.3, "fade")
    return {"end_time": t + wire_duration, "components": len(ids), "wires": len(wires)}


@command
def animate_transform(target, time=0.0, duration=1.0, location=None, rotation=None, scale=None, relative=False):
    """Smoothly move/rotate(deg)/scale a component or object (wires don't follow - use for exploded views)."""
    return A.animate_transform(target, time, duration, location, rotation, scale, relative)


@command
def highlight(targets, time=0.0, duration=1.5, color="yellow", pulses=2, radius=None, style="ring"):
    """Pulsing glowing ring around components/points to draw attention (style ring | ring+bounce)."""
    return A.highlight(targets, time, duration, color, pulses, radius, style)


@command
def clear_animation(what="flow"):
    """Remove animation: flow (particles) | effects (arrows, halos, charges) | keyframes (all keyframes on
    circuit objects) | camera | all."""
    out = {}
    if what in ("flow", "all"):
        out["flow"] = U.clear_collection(lab.COL_FLOW)
    if what in ("effects", "all"):
        out["effects"] = U.clear_collection(lab.COL_EFFECTS)
    if what in ("keyframes", "all"):
        n = 0
        for name in (lab.COL_COMPONENTS, lab.COL_WIRES, lab.COL_ANNOTATIONS):
            col = bpy.data.collections.get(name)
            if col:
                for o in col.all_objects:
                    o.animation_data_clear()
                    if o.data is not None and hasattr(o.data, "animation_data_clear"):
                        o.data.animation_data_clear()
                    n += 1
        for mat in bpy.data.materials:
            if mat.node_tree and mat.node_tree.animation_data:
                mat.node_tree.animation_data_clear()
        for light in bpy.data.lights:
            light.animation_data_clear()
        out["keyframes"] = n
    if what in ("camera", "all"):
        for name in (S.CAMERA, S.CAMERA_TARGET):
            o = bpy.data.objects.get(name)
            if o:
                o.animation_data_clear()
                if o.data is not None:
                    o.data.animation_data_clear()
        out["camera"] = True
    return out


# ============================================================= annotations
@command
def add_label(text, position=None, target=None, offset=(0, 0.9, 0.2), size=0.35, color=None, align="CENTER",
              face_camera=False, hud=False, start=None, end=None, fade=0.4, name=None, rotation=None):
    """3D text at a position or next to a target; hud=True pins it on screen ([x,y] in -1..1)."""
    return N.add_label(text, position, target, offset, size, color, align, face_camera, hud, start, end, fade, name,
                       rotation)


@command
def add_arrow(start_point, end_point, color="yellow", thickness=0.05, time=None, draw_duration=0.6, end=None,
              curved=0.0, name=None):
    """Arrow between points/targets; optionally draws itself at `time`; curved = arc height."""
    return N.add_arrow(start_point, end_point, color, thickness, None, time, draw_duration, end, name, curved)


@command
def add_callout(text, target, offset=(1.5, 1.5, 0.8), size=0.4, color=None, line_color="white", start=None,
                end=None, face_camera=False, name=None):
    """Explanatory text with a leader line pointing at a component/terminal/point."""
    return N.add_callout(text, target, offset, size, color, line_color, start, end, 0.4, face_camera, name)


@command
def add_title(title, subtitle=None, time=0.0, duration=3.0, position="center", size=0.09, color=None,
              background=False):
    """Screen-space title card (position center|top|bottom|top_left or [x,y]); fades in and out."""
    return N.add_title(title, subtitle, time, duration, position, size, color, None, 0.5, background)


@command
def add_readout(component, quantity="current", position=None, prefix=None, source="auto", start=0.0, end=None,
                time_scale=None, size=0.3, color=None, hud=False, digits=3, name=None):
    """Live number that follows the simulation (quantity: current|voltage|power|charge|brightness|rpm|reading)."""
    return N.add_readout(component, quantity, position, prefix, source, start, end, time_scale, size, color, hud,
                         digits, name=name)


@command
def add_plot(signals, position=None, width=6.0, height=3.0, source="transient", start=0.0, end=None,
             time_scale=None, title=None, hud=False, rotation=(90, 0, 0), marker=True, name=None):
    """Oscilloscope graph drawn in sync with the animation.
    signals: [{"component":"C1","quantity":"voltage","color":"yellow","label":"V_C"}]."""
    return N.add_plot(signals, position, width, height, source, start, end, time_scale, title, hud, rotation,
                      marker=marker, name=name)


@command
def add_wire_closeup(position=(0, -8, 2), length=6.0, radius=1.0, wire=None, source="auto", start=0.0, end=None,
                     time_scale=None, electrons=60, drift_speed=0.6, thermal=0.15, labels=True, rotation=(0, 0, 0),
                     name=None):
    """Magnified see-through wire: vibrating copper ion lattice + jittering, drifting free electrons."""
    return N.add_wire_closeup(position, length, radius, wire, source, start, end, time_scale, electrons, None,
                              drift_speed, thermal, labels, rotation, name)


@command
def clear_annotations(kind=None):
    """Delete annotations (all or kind: label|arrow|callout|title|readout|plot|closeup)."""
    return N.clear_annotations(kind)


# ================================================================== scene
@command
def setup_scene(theme="dark", engine="eevee", resolution=(1920, 1080), fps=30, duration=None, board=None, glow=True,
                samples=None, transparent=False, style=None, wire_look=None, remove_defaults=True):
    """Theme (dark|blueprint|light|studio|workbench), engine (eevee|cycles|workbench), board
    (grid|pcb|wood|breadboard|plain|none), resolution, fps, duration (s), glow (bloom).
    remove_defaults deletes Blender's startup Cube/Light/Camera."""
    return S.setup_scene(theme, engine, resolution, fps, duration, board, glow, samples, transparent, style, wire_look,
                         remove_defaults)


@command
def set_timeline(duration=None, fps=None, frame_start=1):
    """Set the video length in seconds (and fps)."""
    return S.set_timeline(duration, fps, frame_start)


@command
def set_camera(location=None, look_at=None, lens=None, time=None, transition=1.0):
    """Place camera; look_at may be a point or a component id. With time: animated move arriving at `time`."""
    return S.set_camera(location, look_at, lens, time, transition)


@command
def frame_circuit(view="front", margin=1.15, time=None, transition=1.5, lens=None, targets=None,
                  include_annotations=False):
    """Fit the whole circuit (or targets) in frame. view: top|top_front|front|iso|low|left|right|[az, el]."""
    return S.frame_circuit(view, margin, time, transition, lens, targets, include_annotations)


@command
def focus_on(target, time=None, transition=1.0, distance=4.0, elevation=40.0, azimuth=0.0, lens=None):
    """Move the camera close to a component/terminal/point (animated if time is given)."""
    return S.focus_on(target, time, transition, distance, elevation, azimuth, lens)


@command
def camera_path(keys, smooth=True):
    """Keyframed camera path: [{"time": s, "location": [x,y,z], "look_at": [x,y,z] or id, "lens": mm}, ...]."""
    return S.camera_path(keys, smooth)


@command
def orbit_camera(start=0.0, end=10.0, degrees=360.0, radius=None, height=None, center=None, start_angle=None):
    """Orbit around the circuit (or center) between start and end seconds."""
    return S.orbit_camera(start, end, degrees, radius, height, center, start_angle)


@command
def depth_of_field(enabled=True, focus=None, fstop=2.8):
    """Camera depth of field focusing on a component/object name or distance."""
    return S.depth_of_field(enabled, focus, fstop)


@command
def render_still(filepath, time=None, frame=None, resolution_percentage=None, samples=None):
    """Render one frame to a PNG file."""
    return S.render_still(filepath, time, frame, resolution_percentage, samples)


@command
def render_animation(filepath, start=None, end=None, file_format="mp4", resolution_percentage=None, samples=None):
    """Render the video (mp4|mov|mkv|webm|png sequence). start/end in seconds."""
    return S.render_animation(filepath, start, end, file_format, resolution_percentage, samples)


@command
def preview(time=None, frame=None, width=640, samples=8):
    """Quick low-res render; returns base64 PNG so the AI can check the composition."""
    return S.preview(time, frame, width, samples)


@command
def save_blend(filepath):
    """Save a copy of the current .blend file."""
    return S.save_blend(filepath)


@command
def build_example(name, origin=(0, 0), style=None, replace=True):
    """Build a ready-made teaching circuit. Names: see list_examples."""
    if replace:
        circ = lab.load_circuit()
        new_circuit(style=style or circ.settings.get("style", "realistic"),
                    wire_look=circ.settings.get("wire_look", "copper"), clear_annotations=False)
    circ = lab.load_circuit()
    info = examples.build(circ, name, origin)
    if style:
        circ.settings["style"] = style
    lab.save_circuit(circ)
    for cid in info["ids"].values():
        lab.build_component(circ, cid)
    for wid in info["wires"]:
        lab.build_wire(circ, wid)
    return info


@command
def list_examples():
    """Ready-made example circuits and what they teach."""
    return examples.describe()


@command
def execute_python(code):
    """Run arbitrary Python inside Blender (bpy, lab, anim, ann, scene, U available). Set `result` to return a value."""
    ns = {"bpy": bpy, "lab": lab, "anim": A, "ann": N, "scene": S, "U": U, "math": math, "catalog": catalog}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<ai-code>", "exec"), ns)
    res = ns.get("result")
    try:
        json.dumps(res)
    except (TypeError, ValueError):
        res = repr(res)
    return {"stdout": buf.getvalue()[-20000:], "result": res}


@command
def batch(commands, stop_on_error=True):
    """Run several commands in one round trip: [{"command": "add_component", "params": {...}}, ...]."""
    results = []
    for i, cmd in enumerate(commands):
        try:
            results.append({"command": cmd["command"], "ok": True,
                            "result": dispatch(cmd["command"], cmd.get("params", {}))})
        except Exception as exc:  # noqa: BLE001 - report every failure back to the caller
            results.append({"command": cmd.get("command"), "ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})
            if stop_on_error:
                break
    return {"results": results}


def run(name, params):
    """Entry point used by the socket server; always returns a JSON-able envelope."""
    try:
        result = dispatch(name, params)
        return {"status": "ok", "result": _json_safe(result)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": "%s: %s" % (type(exc).__name__, exc),
                "traceback": traceback.format_exc()[-4000:]}
