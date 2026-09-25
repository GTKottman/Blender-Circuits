"""Low level Blender helpers: collections, materials, primitives, curves, text, timing."""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT_COLLECTION = "Circuit Lab"


# ---------------------------------------------------------------- collections
def collection(name, parent=None):
    """Get or create a collection (nested under the root 'Circuit Lab' collection by default)."""
    scene = bpy.context.scene
    if parent is None and name != ROOT_COLLECTION:
        parent = collection(ROOT_COLLECTION)
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    parent_col = parent if parent is not None else scene.collection
    if col.name not in parent_col.children:
        try:
            parent_col.children.link(col)
        except RuntimeError:
            pass
    return col


def link(obj, col):
    if obj.name not in col.objects:
        col.objects.link(obj)
    return obj


def delete_object_tree(obj):
    """Delete an object together with all of its children."""
    if obj is None:
        return
    for child in list(obj.children_recursive):
        _delete_single(child)
    _delete_single(obj)


def _delete_single(obj):
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and getattr(data, "users", 1) == 0:
        try:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)
            elif isinstance(data, bpy.types.Light):
                bpy.data.lights.remove(data)
        except (ReferenceError, RuntimeError):
            pass


def clear_collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        return 0
    objs = list(col.all_objects)
    for obj in objs:
        try:
            _delete_single(obj)
        except ReferenceError:
            pass
    return len(objs)


# ------------------------------------------------------------------- colours
NAMED_COLORS = {
    "red": (0.9, 0.05, 0.05), "green": (0.05, 0.75, 0.15), "blue": (0.05, 0.25, 0.95),
    "yellow": (1.0, 0.8, 0.05), "orange": (1.0, 0.4, 0.02), "purple": (0.5, 0.1, 0.9),
    "white": (0.95, 0.95, 0.95), "black": (0.02, 0.02, 0.02), "gray": (0.4, 0.4, 0.4), "grey": (0.4, 0.4, 0.4),
    "cyan": (0.0, 0.8, 0.9), "magenta": (0.9, 0.05, 0.7), "pink": (1.0, 0.4, 0.6), "brown": (0.35, 0.16, 0.05),
    "gold": (1.0, 0.7, 0.2), "silver": (0.75, 0.75, 0.78), "copper": (0.95, 0.45, 0.25),
    "electron": (0.1, 0.55, 1.0), "positive": (1.0, 0.25, 0.1),
}


def color(value, default=(1, 1, 1)):
    """Parse a colour: name, '#rrggbb', or [r,g,b(,a)] -> (r,g,b)."""
    if value is None:
        return tuple(default)
    if isinstance(value, str):
        s = value.strip().lower()
        if s.startswith("#") and len(s) in (7, 9):
            vals = [int(s[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
            # sRGB -> linear
            return tuple(((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in vals)
        if s in NAMED_COLORS:
            return NAMED_COLORS[s]
        raise ValueError("Unknown colour '%s'" % value)
    vals = list(value)[:3]
    return tuple(float(v) for v in vals)


# ----------------------------------------------------------------- materials
def _set_input(node, names, value):
    for name in names if isinstance(names, (list, tuple)) else [names]:
        if name in node.inputs:
            node.inputs[name].default_value = value
            return True
    return False


def material(name, base=(0.8, 0.8, 0.8), metallic=0.0, roughness=0.5, emission=None, emission_strength=0.0,
             transmission=0.0, alpha=1.0, unique=False, coat=0.0):
    """Principled material whose alpha is multiplied by the object's colour alpha.

    That lets any object be faded in/out by animating ``obj.color[3]``.
    Materials are cached by name unless ``unique`` is set.
    """
    if not unique:
        mat = bpy.data.materials.get(name)
        if mat is not None:
            return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    base = color(base)
    _set_input(bsdf, "Base Color", (*base, 1.0))
    _set_input(bsdf, "Metallic", metallic)
    _set_input(bsdf, "Roughness", roughness)
    _set_input(bsdf, ["Transmission Weight", "Transmission"], transmission)
    _set_input(bsdf, ["Coat Weight", "Clearcoat"], coat)
    if emission is not None:
        _set_input(bsdf, ["Emission Color", "Emission"], (*color(emission), 1.0))
        _set_input(bsdf, "Emission Strength", emission_strength)
    info = nt.nodes.new("ShaderNodeObjectInfo")
    info.location = (-500, -300)
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = alpha
    mul.location = (-300, -300)
    mul.name = "AlphaMul"
    nt.links.new(info.outputs["Alpha"], mul.inputs[0])
    nt.links.new(mul.outputs[0], bsdf.inputs["Alpha"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    if hasattr(mat, "blend_method"):
        try:
            mat.blend_method = "HASHED"
        except TypeError:
            pass
    mat.diffuse_color = (*base, 1.0)
    return mat


def bsdf_of(mat):
    return mat.node_tree.nodes.get("Principled BSDF")


def assign(obj, mat):
    if obj.data is None:
        return obj
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


# ---------------------------------------------------------------- primitives
def _mesh_object(name, bm, mat=None, parent=None, col=None, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for poly in me.polygons:
            poly.use_smooth = True
    obj = bpy.data.objects.new(name, me)
    if col is not None:
        link(obj, col)
    if parent is not None:
        obj.parent = parent
    if mat is not None:
        assign(obj, mat)
    return obj


def _axis_matrix(axis):
    axis = axis.upper() if isinstance(axis, str) else axis
    if axis == "X":
        return Matrix.Rotation(math.radians(90), 4, "Y")
    if axis == "Y":
        return Matrix.Rotation(math.radians(-90), 4, "X")
    return Matrix.Identity(4)


def box(name, size, location=(0, 0, 0), mat=None, parent=None, col=None, bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect="EDGES")
    bmesh.ops.translate(bm, vec=Vector(location), verts=bm.verts)
    return _mesh_object(name, bm, mat, parent, col, smooth=bevel > 0)


def cylinder(name, radius, depth, location=(0, 0, 0), axis="Z", mat=None, parent=None, col=None, segments=32,
             radius2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius,
                          radius2=radius if radius2 is None else radius2, depth=depth)
    bmesh.ops.transform(bm, matrix=_axis_matrix(axis), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(location), verts=bm.verts)
    obj = _mesh_object(name, bm, mat, parent, col)
    _flat_caps(obj)
    return obj


def _flat_caps(obj):
    try:
        obj.data.set_sharp_from_angle(angle=math.radians(40))
    except AttributeError:
        pass


def sphere(name, radius, location=(0, 0, 0), mat=None, parent=None, col=None, segments=24, rings=12,
           scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    bmesh.ops.scale(bm, vec=Vector(scale), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(location), verts=bm.verts)
    return _mesh_object(name, bm, mat, parent, col)


def cone(name, radius, depth, location=(0, 0, 0), axis="Z", mat=None, parent=None, col=None, segments=24):
    return cylinder(name, radius, depth, location, axis, mat, parent, col, segments, radius2=0.0)


def torus(name, major, minor, location=(0, 0, 0), mat=None, parent=None, col=None, segments=48, ring=12):
    bm = bmesh.new()
    verts = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        row = []
        for j in range(ring):
            b = 2 * math.pi * j / ring
            r = major + minor * math.cos(b)
            row.append(bm.verts.new((r * math.cos(a), r * math.sin(a), minor * math.sin(b))))
        verts.append(row)
    for i in range(segments):
        for j in range(ring):
            bm.faces.new((verts[i][j], verts[(i + 1) % segments][j], verts[(i + 1) % segments][(j + 1) % ring],
                          verts[i][(j + 1) % ring]))
    bmesh.ops.translate(bm, vec=Vector(location), verts=bm.verts)
    return _mesh_object(name, bm, mat, parent, col)


def flat_polygon(name, points, mat=None, parent=None, col=None, thickness=0.0):
    """Filled polygon on the XY plane (optionally extruded by thickness)."""
    bm = bmesh.new()
    verts = [bm.verts.new((p[0], p[1], p[2] if len(p) > 2 else 0.0)) for p in points]
    face = bm.faces.new(verts)
    if thickness:
        res = bmesh.ops.extrude_face_region(bm, geom=[face])
        moved = [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, vec=Vector((0, 0, thickness)), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _mesh_object(name, bm, mat, parent, col, smooth=False)


def empty(name, location=(0, 0, 0), parent=None, col=None, display="PLAIN_AXES", size=0.3):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = display
    obj.empty_display_size = size
    obj.location = location
    if col is not None:
        link(obj, col)
    if parent is not None:
        obj.parent = parent
    return obj


# -------------------------------------------------------------------- curves
def poly_curve(name, points, radius=0.03, mat=None, parent=None, col=None, closed=False, smooth=False,
               resolution=4, caps=True):
    """A tube following a polyline (or smooth path when smooth=True)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = resolution
    cu.use_fill_caps = caps
    add_spline(cu, points, closed, smooth)
    obj = bpy.data.objects.new(name, cu)
    if col is not None:
        link(obj, col)
    if parent is not None:
        obj.parent = parent
    if mat is not None:
        assign(obj, mat)
    return obj


def add_spline(cu, points, closed=False, smooth=False):
    pts = [tuple(p) + (0.0,) * (3 - len(p)) for p in points]
    if smooth:
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(len(pts) - 1)
        for bp, p in zip(sp.bezier_points, pts):
            bp.co = p
            bp.handle_left_type = bp.handle_right_type = "AUTO"
    else:
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for sp_pt, p in zip(sp.points, pts):
            sp_pt.co = (p[0], p[1], p[2], 1.0)
    sp.use_cyclic_u = closed
    return sp


def circle_points(center, radius, n=32, start=0.0, end=360.0, plane="XY"):
    pts = []
    for i in range(n + 1):
        a = math.radians(start + (end - start) * i / n)
        c, s = radius * math.cos(a), radius * math.sin(a)
        if plane == "XY":
            pts.append((center[0] + c, center[1] + s, center[2] if len(center) > 2 else 0.0))
        elif plane == "XZ":
            pts.append((center[0] + c, center[1], center[2] + s))
        else:
            pts.append((center[0], center[1] + c, center[2] + s))
    return pts


# ---------------------------------------------------------------------- text
def text(name, body, size=0.3, location=(0, 0, 0), mat=None, parent=None, col=None, align="CENTER",
         valign="CENTER", extrude=0.0, rotation=(0, 0, 0), bold=False):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = str(body)
    cu.size = size
    cu.align_x = align
    cu.align_y = valign
    cu.extrude = extrude
    if bold:
        cu.offset = 0.01 * size
    obj = bpy.data.objects.new(name, cu)
    obj.location = location
    obj.rotation_euler = rotation
    if col is not None:
        link(obj, col)
    if parent is not None:
        obj.parent = parent
    if mat is not None:
        assign(obj, mat)
    return obj


# -------------------------------------------------------------------- timing
def fps():
    r = bpy.context.scene.render
    return r.fps / (r.fps_base or 1.0)


def sec_to_frame(t):
    return bpy.context.scene.frame_start + float(t) * fps()


def frame_to_sec(f):
    return (f - bpy.context.scene.frame_start) / fps()


def ensure_timeline(end_seconds):
    """Grow the scene frame range so it covers end_seconds."""
    scene = bpy.context.scene
    end = int(math.ceil(sec_to_frame(end_seconds)))
    if end > scene.frame_end:
        scene.frame_end = end


# ---------------------------------------------------------------- keyframes
def fcurve_for(id_data, data_path, index=-1, action_group=None):
    anim = id_data.animation_data or id_data.animation_data_create()
    if anim.action is None:
        anim.action = bpy.data.actions.new(id_data.name + "Action")
    action = anim.action
    fcurves = getattr(action, "fcurves", None)
    if fcurves is None:  # Blender 5 layered actions
        id_data.keyframe_insert(data_path, index=max(index, 0))
        return _find_fcurve(id_data, data_path, max(index, 0))
    fc = fcurves.find(data_path, index=max(index, 0))
    if fc is None:
        fc = fcurves.new(data_path, index=max(index, 0), action_group=action_group or "")
    return fc


def _find_fcurve(id_data, data_path, index):
    action = id_data.animation_data.action
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    if fc.data_path == data_path and fc.array_index == index:
                        return fc
    return None


_INTERP_CODE = {"CONSTANT": 0, "LINEAR": 1, "BEZIER": 2}


def set_keys(id_data, data_path, index, frames, values, interpolation="LINEAR", replace_range=True,
             interpolations=None):
    """Fast bulk keyframe insertion.

    frames/values are equal-length sequences.  ``interpolations`` optionally gives a per-key
    interpolation name (overriding ``interpolation``).
    """
    fc = fcurve_for(id_data, data_path, index)
    if fc is None or not len(frames):
        return fc
    kps = fc.keyframe_points
    if replace_range:
        lo, hi = min(frames), max(frames)
        for i in range(len(kps) - 1, -1, -1):
            if lo - 1e-6 <= kps[i].co[0] <= hi + 1e-6:
                kps.remove(kps[i], fast=True)
    interp = interpolations or [interpolation] * len(frames)
    start = len(kps)
    kps.add(len(frames))
    if start == 0:
        flat = []
        for f, v in zip(frames, values):
            flat.extend((f, v))
        kps.foreach_set("co", flat)
        try:
            kps.foreach_set("interpolation", [_INTERP_CODE.get(i, 1) for i in interp])
        except (TypeError, AttributeError):
            for kp, i in zip(kps, interp):
                kp.interpolation = i
    else:
        for i, (f, v) in enumerate(zip(frames, values)):
            kp = kps[start + i]
            kp.co = (f, v)
            kp.interpolation = interp[i]
    for kp in kps:
        kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
    fc.update()
    return fc


def key(id_data, data_path, frame, value=None, index=-1, interpolation=None):
    """Set a property (optionally) and insert a keyframe."""
    if value is not None:
        target, attr = _resolve(id_data, data_path)
        if index >= 0:
            getattr(target, attr)[index] = value
        else:
            setattr(target, attr, value)
    id_data.keyframe_insert(data_path, frame=frame, index=index)
    if interpolation:
        fc = None
        anim = id_data.animation_data
        if anim and anim.action and getattr(anim.action, "fcurves", None) is not None:
            for fc in anim.action.fcurves:
                if fc.data_path == data_path and (index < 0 or fc.array_index == index):
                    for kp in fc.keyframe_points:
                        if abs(kp.co[0] - frame) < 1e-4:
                            kp.interpolation = interpolation


def _resolve(id_data, data_path):
    if "." in data_path and not data_path.startswith("["):
        head, attr = data_path.rsplit(".", 1)
        return id_data.path_resolve(head), attr
    return id_data, data_path


# ------------------------------------------------------------------- misc
def world_matrix_from(position, rotation_deg):
    return Matrix.Translation(Vector(position)) @ Matrix.Rotation(math.radians(rotation_deg), 4, "Z")


def look_at_rotation(location, target):
    direction = Vector(target) - Vector(location)
    return direction.to_track_quat("-Z", "Y").to_euler()


def polyline_length(points):
    return sum((Vector(points[i + 1]) - Vector(points[i])).length for i in range(len(points) - 1))


def point_along(points, cumulative, s):
    """Position at arc length s along a polyline with precomputed cumulative lengths."""
    if s <= 0:
        return Vector(points[0])
    if s >= cumulative[-1]:
        return Vector(points[-1])
    lo, hi = 0, len(cumulative) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if cumulative[mid] <= s:
            lo = mid
        else:
            hi = mid
    seg = cumulative[hi] - cumulative[lo]
    f = (s - cumulative[lo]) / seg if seg > 0 else 0.0
    return Vector(points[lo]).lerp(Vector(points[hi]), f)


def cumulative_lengths(points):
    out = [0.0]
    for i in range(len(points) - 1):
        out.append(out[-1] + (Vector(points[i + 1]) - Vector(points[i])).length)
    return out
