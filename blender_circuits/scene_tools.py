"""Scene setup: themes, board, lights, camera moves, HUD overlays and rendering."""

import base64
import math
import os
import tempfile

import bpy
from mathutils import Vector

from . import bl_utils as U
from . import lab

CAMERA = "CL Camera"
CAMERA_TARGET = "CL Camera Target"
HUD_ROOT = "CL HUD"
HUD_DEPTH = 5.0

THEMES = {
    "dark": {"world": (0.004, 0.005, 0.008), "board": "grid", "label": (0.92, 0.95, 1.0), "light": 0.6,
             "grid_bg": (0.012, 0.014, 0.02), "grid_line": (0.05, 0.07, 0.1)},
    "blueprint": {"world": (0.005, 0.02, 0.07), "board": "grid", "label": (0.95, 0.97, 1.0), "light": 0.5,
                  "grid_bg": (0.01, 0.05, 0.16), "grid_line": (0.08, 0.2, 0.45)},
    "light": {"world": (0.8, 0.82, 0.85), "board": "plain", "label": (0.03, 0.03, 0.05), "light": 1.2,
              "grid_bg": (0.9, 0.9, 0.9), "grid_line": (0.75, 0.78, 0.82)},
    "studio": {"world": (0.05, 0.055, 0.065), "board": "pcb", "label": (0.95, 0.95, 0.95), "light": 1.0,
               "grid_bg": (0.02, 0.2, 0.08), "grid_line": (0.05, 0.3, 0.12)},
    "workbench": {"world": (0.06, 0.05, 0.045), "board": "wood", "label": (0.98, 0.95, 0.9), "light": 1.0,
                  "grid_bg": (0.35, 0.2, 0.1), "grid_line": (0.3, 0.17, 0.08)},
}

ENGINES = {
    "eevee": ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"],
    "cycles": ["CYCLES"],
    "workbench": ["BLENDER_WORKBENCH"],
}


def set_engine(name):
    scene = bpy.context.scene
    name = (name or "eevee").lower()
    if name == "cycles":
        try:
            import addon_utils
            addon_utils.enable("cycles", default_set=True)
        except Exception:
            pass
    for candidate in ENGINES.get(name, [name.upper()]):
        try:
            scene.render.engine = candidate
            return candidate
        except TypeError:
            continue
    raise ValueError("Render engine '%s' is not available" % name)


# -------------------------------------------------------------------- world
def _world(rgb, strength=1.0):
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new("CL World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is None:
        bg = world.node_tree.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (*rgb, 1.0)
    bg.inputs["Strength"].default_value = strength
    world.color = rgb


def _grid_material(name, bg, line, emission=0.0, spacing=1.0):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        bpy.data.materials.remove(mat)
    mat = U.material(name, base=bg, roughness=0.9, unique=True)
    nt = mat.node_tree
    bsdf = U.bsdf_of(mat)
    U._set_input(bsdf, ["Specular IOR Level", "Specular"], 0.2)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    outs = []
    for axis in ("X", "Y"):
        div = nt.nodes.new("ShaderNodeMath")
        div.operation = "DIVIDE"
        div.inputs[1].default_value = spacing
        nt.links.new(sep.outputs[axis], div.inputs[0])
        fr = nt.nodes.new("ShaderNodeMath")
        fr.operation = "PINGPONG"
        fr.inputs[1].default_value = 0.5
        nt.links.new(div.outputs[0], fr.inputs[0])
        lt = nt.nodes.new("ShaderNodeMath")
        lt.operation = "LESS_THAN"
        lt.inputs[1].default_value = 0.02
        nt.links.new(fr.outputs[0], lt.inputs[0])
        outs.append(lt)
    mx = nt.nodes.new("ShaderNodeMath")
    mx.operation = "MAXIMUM"
    nt.links.new(outs[0].outputs[0], mx.inputs[0])
    nt.links.new(outs[1].outputs[0], mx.inputs[1])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (*bg, 1)
    mix.inputs["B"].default_value = (*line, 1)
    nt.links.new(mx.outputs[0], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    if emission:
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def fit_board(margin=2.5, style=None, theme=None):
    """(Re)create the board under the circuit, sized to its bounds."""
    scene = bpy.context.scene
    style = style or scene.get("cl_board_style", "grid")
    theme = THEMES.get(theme or scene.get("cl_theme", "dark"), THEMES["dark"])
    old = bpy.data.objects.get("CL Board")
    if old is not None:
        U.delete_object_tree(old)
    if style in (None, "none", False):
        return None
    (x0, y0, _), (x1, y1, _) = lab.circuit_bounds()
    w = max(x1 - x0 + 2 * margin, 12.0)
    h = max(y1 - y0 + 2 * margin, 8.0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if style == "grid":
        mat = _grid_material("cc_board_grid", theme["grid_bg"], theme["grid_line"], emission=0.4)
    elif style == "pcb":
        mat = U.material("cc_board_pcb", base=(0.02, 0.2, 0.08), roughness=0.75)
    elif style == "wood":
        mat = U.material("cc_board_wood", base=(0.35, 0.2, 0.09), roughness=0.6)
    elif style == "breadboard":
        mat = U.material("cc_board_breadboard", base=(0.88, 0.87, 0.82), roughness=0.6)
    else:
        mat = U.material("cc_board_plain_%s" % scene.get("cl_theme", "dark"), base=theme["grid_bg"], roughness=0.8)
    board = U.box("CL Board", (w, h, 0.2), (0, 0, -0.1), mat, None, U.collection(lab.COL_ENV), bevel=0.04)
    board.location = (cx, cy, 0)
    board["cc_board"] = style
    return board


def _lights(power):
    col = U.collection(lab.COL_ENV)
    for obj in list(col.objects):
        if obj.get("cc_env_light"):
            U.delete_object_tree(obj)
    specs = [("CL Key Light", (6, -8, 12), 900, 8.0, (1.0, 0.96, 0.9)),
             ("CL Fill Light", (-10, -4, 8), 350, 10.0, (0.85, 0.9, 1.0)),
             ("CL Rim Light", (0, 12, 9), 500, 8.0, (0.9, 0.95, 1.0))]
    for name, loc, energy, size, rgb in specs:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy * power
        data.size = size
        data.color = rgb
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        obj.rotation_euler = U.look_at_rotation(loc, (0, 0, 0))
        obj["cc_env_light"] = True
        U.link(obj, col)


def _glow_compositor(enable, strength=1.0):
    scene = bpy.context.scene
    try:
        scene.use_nodes = True
        tree = scene.node_tree
    except AttributeError:
        return False
    if tree is None:
        return False
    for node in list(tree.nodes):
        if node.name.startswith("CL "):
            tree.nodes.remove(node)
    rl = next((n for n in tree.nodes if n.type == "R_LAYERS"), None) or tree.nodes.new("CompositorNodeRLayers")
    comp = next((n for n in tree.nodes if n.type == "COMPOSITE"), None) or tree.nodes.new("CompositorNodeComposite")
    if not enable:
        tree.links.new(rl.outputs["Image"], comp.inputs["Image"])
        return True
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.name = "CL Glow"
    glare.glare_type = "FOG_GLOW"
    try:
        glare.quality = "HIGH"
        glare.threshold = 0.8
        glare.size = 8
        glare.mix = -1.0 + min(max(strength, 0.0), 2.0) * 0.5
    except (AttributeError, TypeError):
        pass
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], comp.inputs["Image"])
    return True


def remove_startup_objects():
    """Delete Blender's default startup Cube / Light / Camera if they are still in the scene."""
    removed = []
    for name, kind in (("Cube", "MESH"), ("Light", "LIGHT"), ("Camera", "CAMERA")):
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.type == kind and not obj.get("cc_id"):
            U.delete_object_tree(obj)
            removed.append(name)
    return removed


def setup_scene(theme="dark", engine="eevee", resolution=(1920, 1080), fps=30, duration=None, board=None,
                glow=True, samples=None, transparent=False, style=None, wire_look=None, remove_defaults=True):
    """Prepare a good-looking teaching scene (world, lights, board, camera, render settings)."""
    scene = bpy.context.scene
    if remove_defaults:
        remove_startup_objects()
    th = THEMES.get(theme)
    if th is None:
        raise ValueError("Unknown theme '%s' (use %s)" % (theme, ", ".join(THEMES)))
    scene["cl_theme"] = theme
    scene["cl_board_style"] = board if board is not None else th["board"]
    used = set_engine(engine)
    r = scene.render
    r.resolution_x, r.resolution_y = int(resolution[0]), int(resolution[1])
    r.resolution_percentage = 100
    r.fps = int(fps)
    r.fps_base = 1.0
    r.film_transparent = bool(transparent)
    if used.startswith("BLENDER_EEVEE"):
        scene.eevee.taa_render_samples = int(samples or 64)
        for attr, val in (("use_gtao", True), ("use_bloom", glow)):
            if hasattr(scene.eevee, attr):
                setattr(scene.eevee, attr, val)
    elif used == "CYCLES":
        scene.cycles.samples = int(samples or 128)
        scene.cycles.use_denoising = True
    try:
        scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in
                                                               scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
        scene.view_settings.look = "AgX - Punchy" if theme in ("dark", "blueprint") else "None"
    except (TypeError, KeyError):
        pass
    _world(th["world"])
    _lights(th["light"])
    lm = lab.label_material()
    bsdf = U.bsdf_of(lm)
    bsdf.inputs["Base Color"].default_value = (*th["label"], 1)
    bsdf.inputs["Emission Color"].default_value = (*th["label"], 1)
    circ = lab.load_circuit()
    rebuild = False
    if style and style != circ.settings.get("style"):
        circ.settings["style"] = style
        rebuild = True
    if wire_look and wire_look != circ.settings.get("wire_look"):
        circ.settings["wire_look"] = wire_look
        rebuild = True
    if rebuild:
        lab.save_circuit(circ)
        lab.rebuild_all(circ)
    fit_board()
    _glow_compositor(glow)
    ensure_camera()
    if duration:
        set_timeline(duration)
    return {"theme": theme, "engine": used, "resolution": [r.resolution_x, r.resolution_y], "fps": r.fps,
            "frame_end": scene.frame_end}


def set_timeline(duration=None, fps=None, frame_start=1):
    scene = bpy.context.scene
    if fps:
        scene.render.fps = int(fps)
        scene.render.fps_base = 1.0
    scene.frame_start = int(frame_start)
    if duration:
        scene.frame_end = int(round(scene.frame_start + float(duration) * U.fps()))
    return {"frame_start": scene.frame_start, "frame_end": scene.frame_end, "fps": U.fps(),
            "duration": (scene.frame_end - scene.frame_start) / U.fps()}


# ------------------------------------------------------------------- camera
def ensure_camera():
    scene = bpy.context.scene
    cam = bpy.data.objects.get(CAMERA)
    if cam is None:
        data = bpy.data.cameras.new(CAMERA)
        data.lens = 35
        data.clip_end = 1000
        cam = bpy.data.objects.new(CAMERA, data)
        U.link(cam, U.collection(lab.COL_ENV))
        cam.location = (0, -14, 12)
    target = bpy.data.objects.get(CAMERA_TARGET)
    if target is None:
        target = U.empty(CAMERA_TARGET, (0, 0, 0), None, U.collection(lab.COL_ENV), size=0.3)
        target.hide_render = True
    if not any(c.type == "TRACK_TO" for c in cam.constraints):
        con = cam.constraints.new("TRACK_TO")
        con.target = target
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.up_axis = "UP_Y"
    scene.camera = cam
    return cam


def _cam_target():
    ensure_camera()
    return bpy.data.objects[CAMERA_TARGET]


def _key_camera(location, look_at, lens, frame, interpolation="BEZIER"):
    cam = ensure_camera()
    tgt = _cam_target()
    if location is not None:
        cam.location = location
        for axis in range(3):
            U.set_keys(cam, "location", axis, [frame], [location[axis]], interpolation=interpolation, replace_range=True)
    if look_at is not None:
        tgt.location = look_at
        for axis in range(3):
            U.set_keys(tgt, "location", axis, [frame], [look_at[axis]], interpolation=interpolation, replace_range=True)
    if lens is not None:
        cam.data.lens = lens
        U.set_keys(cam.data, "lens", 0, [frame], [lens], interpolation=interpolation, replace_range=True)


def set_camera(location=None, look_at=None, lens=None, time=None, transition=1.0, ortho_scale=None):
    """Place the camera. With time, keyframes the move so it arrives at `time` (after `transition` s)."""
    cam = ensure_camera()
    look = lab.target_point(look_at) if look_at is not None and not isinstance(look_at, (list, tuple)) else look_at
    if ortho_scale:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho_scale
    if time is None:
        if location is not None:
            cam.location = location
        if look is not None:
            _cam_target().location = look
        if lens is not None:
            cam.data.lens = lens
        return {"location": list(cam.location), "look_at": list(_cam_target().location), "lens": cam.data.lens}
    t0 = max(0.0, float(time) - float(transition or 0))
    f0, f1 = U.sec_to_frame(t0), U.sec_to_frame(time)
    # hold the previous pose until the move starts
    bpy.context.scene.frame_set(int(f0))
    cur_loc, cur_tgt, cur_lens = list(cam.location), list(_cam_target().location), cam.data.lens
    if transition:
        _key_camera(cur_loc if location is not None else None, cur_tgt if look is not None else None,
                    cur_lens if lens is not None else None, f0)
    _key_camera(location, look, lens, f1)
    U.ensure_timeline(time)
    return {"keyed_frames": [f0, f1]}


def _fov_half_extents(distance):
    cam = ensure_camera()
    r = bpy.context.scene.render
    aspect = r.resolution_x / max(r.resolution_y, 1)
    if cam.data.type == "ORTHO":
        hw = cam.data.ortho_scale / 2
    else:
        hw = distance * cam.data.sensor_width / (2 * cam.data.lens)
    if aspect >= 1:
        return hw, hw / aspect
    return hw * aspect, hw


VIEWS = {"top": (0.0, 89.9), "iso": (-35.0, 50.0), "front": (0.0, 35.0), "low": (0.0, 18.0),
         "left": (-70.0, 35.0), "right": (70.0, 35.0), "top_front": (0.0, 65.0)}


def frame_circuit(view="front", margin=1.15, time=None, transition=1.5, lens=None, targets=None,
                  include_annotations=False):
    """Point the camera so the whole circuit (or just `targets`) fills the frame.

    view: top, top_front, front, iso, low, left, right (or [azimuth_deg, elevation_deg]).
    """
    cam = ensure_camera()
    if lens:
        cam.data.lens = lens
    if targets:
        pts = [Vector(lab.target_point(t)) for t in (targets if isinstance(targets, list) else [targets])]
        lo = Vector((min(p.x for p in pts) - 1.2, min(p.y for p in pts) - 1.2, 0))
        hi = Vector((max(p.x for p in pts) + 1.2, max(p.y for p in pts) + 1.2, 1))
    else:
        lo, hi = map(Vector, lab.circuit_bounds(include_annotations=include_annotations))
    center = (lo + hi) / 2
    center.z = max(center.z, 0.3)
    if isinstance(view, (list, tuple)):
        az, el = float(view[0]), float(view[1])
    elif view in VIEWS:
        az, el = VIEWS[view]
    else:
        raise ValueError("Unknown view '%s' (use %s or [azimuth, elevation])" % (view, ", ".join(VIEWS)))
    az, el = math.radians(az), math.radians(el)
    direction = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))).normalized()
    r = bpy.context.scene.render
    aspect = r.resolution_x / max(r.resolution_y, 1)
    lens_now = lens or cam.data.lens
    tan_h = cam.data.sensor_width / (2 * lens_now)
    tan_v = tan_h / aspect
    if aspect < 1:
        tan_v, tan_h = tan_h, tan_h * aspect
    # camera basis: forward points from camera to center
    forward = -direction
    right = forward.cross(Vector((0, 0, 1)))
    if right.length < 1e-6:
        right = Vector((1, 0, 0))
    right.normalize()
    up = right.cross(forward).normalized()
    dist = 3.0
    for cx in (lo.x, hi.x):
        for cy in (lo.y, hi.y):
            for cz in (lo.z, hi.z):
                rel = Vector((cx, cy, cz)) - center
                toward_cam = rel.dot(direction)
                dist = max(dist, toward_cam + abs(rel.dot(right)) * margin / tan_h,
                           toward_cam + abs(rel.dot(up)) * margin / tan_v)
    loc = center + direction * dist
    if view == "top":
        loc = Vector((center.x, center.y - 0.001, center.z + dist))
    res = set_camera(list(loc), list(center), lens, time, transition)
    return {"location": list(loc), "look_at": list(center), "distance": dist, **res}


def focus_on(target, time=None, transition=1.0, distance=4.0, elevation=40.0, azimuth=0.0, lens=None):
    """Move the camera close to a component / terminal / point."""
    p = Vector(lab.target_point(target))
    az, el = math.radians(azimuth), math.radians(elevation)
    direction = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    loc = p + direction * distance
    return set_camera(list(loc), list(p), lens, time, transition)


def camera_path(keys, smooth=True):
    """keys: [{"time": s, "location": [...], "look_at": [...] or target id, "lens": mm}, ...]"""
    interp = "BEZIER" if smooth else "LINEAR"
    for k in sorted(keys, key=lambda k: k["time"]):
        look = k.get("look_at")
        if look is not None and not isinstance(look, (list, tuple)):
            look = lab.target_point(look)
        _key_camera(k.get("location"), look, k.get("lens"), U.sec_to_frame(k["time"]), interp)
        U.ensure_timeline(k["time"])
    return {"keys": len(keys)}


def orbit_camera(start=0.0, end=10.0, degrees=360.0, radius=None, height=None, center=None, start_angle=None,
                 key_step=4):
    """Circle the camera around the circuit between start and end (seconds)."""
    cam = ensure_camera()
    if center is None:
        lo, hi = map(Vector, lab.circuit_bounds())
        c = (lo + hi) / 2
        center = [c.x, c.y, 0.3]
    elif not isinstance(center, (list, tuple)):
        center = lab.target_point(center)
    center = Vector(center)
    bpy.context.scene.frame_set(int(U.sec_to_frame(start)))
    rel = cam.location - center
    if radius is None:
        radius = max(math.hypot(rel.x, rel.y), 4.0)
    if height is None:
        height = max(rel.z, 2.0)
    a0 = math.radians(start_angle) if start_angle is not None else math.atan2(rel.y, rel.x)
    f0, f1 = U.sec_to_frame(start), U.sec_to_frame(end)
    frames = []
    f = f0
    while f < f1:
        frames.append(f)
        f += key_step
    frames.append(f1)
    xs, ys, zs = [], [], []
    for f in frames:
        u = (f - f0) / (f1 - f0)
        u = u * u * (3 - 2 * u)  # ease in/out
        a = a0 + math.radians(degrees) * u
        xs.append(center.x + radius * math.cos(a))
        ys.append(center.y + radius * math.sin(a))
        zs.append(center.z + height)
    for axis, vals in enumerate((xs, ys, zs)):
        U.set_keys(cam, "location", axis, frames, vals)
    tgt = _cam_target()
    for axis in range(3):
        U.set_keys(tgt, "location", axis, [f0, f1], [center[axis], center[axis]])
    U.ensure_timeline(end)
    return {"frames": [f0, f1], "radius": radius, "height": height}


def depth_of_field(enabled=True, focus=None, fstop=2.8):
    cam = ensure_camera()
    cam.data.dof.use_dof = bool(enabled)
    if focus is not None:
        obj = bpy.data.objects.get(focus) if isinstance(focus, str) else None
        if obj is None and isinstance(focus, str):
            obj = lab.comp_root(focus)
        if obj is not None:
            cam.data.dof.focus_object = obj
        else:
            cam.data.dof.focus_distance = float(focus)
    cam.data.dof.aperture_fstop = fstop
    return {"dof": cam.data.dof.use_dof}


# ---------------------------------------------------------------------- HUD
def hud_extent():
    return _fov_half_extents(HUD_DEPTH)


def hud_size(fraction):
    """World size for text that should be `fraction` of the screen height."""
    hw, hh = hud_extent()
    return 2 * hh * float(fraction)


def attach_to_hud(obj, position, depth_offset=0.0):
    """Parent an object to the camera so it stays fixed on screen. position: [x, y] in -1..1."""
    cam = ensure_camera()
    hw, hh = hud_extent()
    obj.parent = cam
    obj.matrix_parent_inverse.identity()
    obj.location = (float(position[0]) * hw, float(position[1]) * hh, -HUD_DEPTH - depth_offset)
    obj.rotation_euler = (0, 0, 0)
    obj["cc_hud"] = True
    return obj


# ------------------------------------------------------------------ render
def _abs(path):
    return bpy.path.abspath(path) if path.startswith("//") else os.path.abspath(os.path.expanduser(path))


def render_still(filepath, time=None, frame=None, resolution_percentage=None, samples=None):
    scene = bpy.context.scene
    ensure_camera()
    if frame is None:
        frame = int(round(U.sec_to_frame(time))) if time is not None else scene.frame_current
    scene.frame_set(int(frame))
    old_pct = scene.render.resolution_percentage
    if resolution_percentage:
        scene.render.resolution_percentage = int(resolution_percentage)
    _apply_samples(samples)
    path = _abs(filepath)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    scene.render.resolution_percentage = old_pct
    return {"filepath": path, "frame": frame}


def _apply_samples(samples):
    if not samples:
        return
    scene = bpy.context.scene
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = int(samples)
    elif scene.render.engine.startswith("BLENDER_EEVEE"):
        scene.eevee.taa_render_samples = int(samples)


def render_animation(filepath, start=None, end=None, file_format="mp4", resolution_percentage=None, samples=None):
    """Render the animation. file_format: mp4 (H.264), png (image sequence) or gif-like 'webm'."""
    scene = bpy.context.scene
    ensure_camera()
    old = (scene.frame_start, scene.frame_end, scene.render.resolution_percentage)
    f_start = int(round(U.sec_to_frame(start))) if start is not None else None
    f_end = int(round(U.sec_to_frame(end))) if end is not None else None  # before frame_start moves
    if f_start is not None:
        scene.frame_start = f_start
    if f_end is not None:
        scene.frame_end = f_end
    if resolution_percentage:
        scene.render.resolution_percentage = int(resolution_percentage)
    _apply_samples(samples)
    path = _abs(filepath)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fmt = file_format.lower()
    if fmt in ("mp4", "mov", "mkv", "webm"):
        scene.render.image_settings.file_format = "FFMPEG"
        ff = scene.render.ffmpeg
        ff.format = {"mp4": "MPEG4", "mov": "QUICKTIME", "mkv": "MKV", "webm": "WEBM"}[fmt]
        ff.codec = "WEBM" if fmt == "webm" else "H264"
        ff.constant_rate_factor = "HIGH"
        ff.ffmpeg_preset = "GOOD"
        if not path.lower().endswith("." + fmt):
            path += "." + fmt
    else:
        scene.render.image_settings.file_format = "PNG"
        if not path.endswith(("/", os.sep)) and "#" not in path:
            path += "_####"
    scene.render.filepath = path
    bpy.ops.render.render(animation=True)
    frames = [scene.frame_start, scene.frame_end]
    scene.frame_start, scene.frame_end, scene.render.resolution_percentage = old
    return {"filepath": path, "frames": frames}


def preview(time=None, frame=None, width=640, samples=8, filepath=None):
    """Quick low-res render of the camera view; returns a base64 PNG so an AI can look at the result."""
    scene = bpy.context.scene
    r = scene.render
    old = (r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath, r.image_settings.file_format)
    old_samples = None
    if r.engine == "CYCLES":
        old_samples = scene.cycles.samples
    elif r.engine.startswith("BLENDER_EEVEE"):
        old_samples = scene.eevee.taa_render_samples
    aspect = r.resolution_y / max(r.resolution_x, 1)
    r.resolution_percentage = 100
    r.resolution_x = int(width)
    r.resolution_y = int(round(width * aspect))
    path = filepath or os.path.join(tempfile.gettempdir(), "circuit_lab_preview.png")
    try:
        _apply_samples(samples)
        render_still(path, time=time, frame=frame)
    finally:
        r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath, r.image_settings.file_format = old
        if old_samples is not None:
            _apply_samples(old_samples)
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode("ascii")
    return {"image_base64": data, "format": "png", "filepath": path}


def save_blend(filepath):
    path = _abs(filepath)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    return {"filepath": path}
