"""Scene state: persists the circuit model in the .blend and (re)builds its 3D objects."""

import json
import math

import bpy

from . import bl_utils as U
from . import catalog, models
from .circuit import Circuit

MODEL_TEXT = "CircuitLab_model.json"
RESULTS_TEXT = "CircuitLab_results.json"

COL_COMPONENTS = "CL Components"
COL_WIRES = "CL Wires"
COL_FLOW = "CL Current Flow"
COL_EFFECTS = "CL Effects"
COL_ANNOTATIONS = "CL Annotations"
COL_ENV = "CL Environment"


# --------------------------------------------------------------- persistence
def _text_block(name):
    txt = bpy.data.texts.get(name)
    if txt is None:
        txt = bpy.data.texts.new(name)
    return txt


def load_circuit():
    txt = bpy.data.texts.get(MODEL_TEXT)
    if txt is None or not txt.as_string().strip():
        return Circuit()
    return Circuit(json.loads(txt.as_string()))


def save_circuit(circ):
    txt = _text_block(MODEL_TEXT)
    txt.clear()
    txt.write(json.dumps(circ.to_dict(), indent=1))


def load_results():
    txt = bpy.data.texts.get(RESULTS_TEXT)
    if txt is None or not txt.as_string().strip():
        return {}
    return json.loads(txt.as_string())


def save_result(result):
    data = load_results()
    data[result["type"]] = result
    data["latest"] = result["type"]
    txt = _text_block(RESULTS_TEXT)
    txt.clear()
    txt.write(json.dumps(data))


def get_result(source="auto"):
    data = load_results()
    if source in (None, "auto", "latest"):
        source = data.get("latest")
    if not source or source not in data:
        raise RuntimeError("No '%s' simulation results yet - run simulate_dc or simulate_transient first." %
                           (source or "any"))
    return data[source]


# ------------------------------------------------------------------ building
def comp_root(cid):
    obj = bpy.data.objects.get(cid)
    if obj is not None and obj.get("cc_id") == cid:
        return obj
    for o in bpy.data.objects:
        if o.get("cc_id") == cid:
            return o
    return None


def wire_object(wid):
    obj = bpy.data.objects.get(wid)
    if obj is not None and obj.get("cc_wire") == wid:
        return obj
    for o in bpy.data.objects:
        if o.get("cc_wire") == wid:
            return o
    return None


def label_material():
    return U.material("cc_label", base=(0.95, 0.95, 0.95), roughness=0.6, emission=(0.95, 0.95, 0.95),
                      emission_strength=0.4)


def wire_material(circ, wire):
    look = circ.settings.get("wire_look", "copper")
    col = wire.get("color")
    if col:
        return U.material("cc_wire_%s" % str(col).replace("#", ""), base=U.color(col), roughness=0.35)
    if look == "glass":
        return U.material("cc_wire_glass", base=(0.8, 0.9, 1.0), roughness=0.05, transmission=1.0, alpha=0.3)
    if look == "insulated":
        return U.material("cc_wire_insulated", base=(0.05, 0.05, 0.05), roughness=0.4)
    if circ.settings.get("style") == "schematic":
        return models.M("ink")
    return models.M("copper")


def build_component(circ, cid):
    old = comp_root(cid)
    if old is not None:
        U.delete_object_tree(old)
    comp = circ.get(cid)
    col = U.collection(COL_COMPONENTS)
    root = models.build(cid, comp, circ.settings, col)
    _build_label(circ, cid, root)
    return root


def _build_label(circ, cid, root):
    comp = circ.get(cid)
    show_labels = circ.settings.get("show_labels", True)
    show_value = comp.get("show_value")
    if show_value is None:
        show_value = circ.settings.get("show_values", True)
    label = comp.get("label")
    if label is False or label == "":
        return None
    lines = []
    if label:
        lines.append(str(label))
    elif show_labels:
        lines.append(cid)
    if show_value and comp["type"] not in ("chip", "junction", "ground"):
        v = catalog.value_text(comp["type"], comp["params"])
        if v:
            lines.append(v)
    if not lines or comp["type"] == "junction":
        return None
    rot = comp.get("rotation", 0.0) % 360
    vertical = 45 < rot < 135 or 225 < rot < 315
    big = comp["type"] in ("dc_source", "motor", "bulb", "potentiometer", "ammeter", "voltmeter", "ac_source",
                           "current_source", "npn", "pnp", "chip", "speaker")
    offset = comp.get("label_offset")
    if offset is None:
        if vertical:
            offset = [0.9 if big else 0.6, 0.0, 0.0]
        else:
            offset = [0.0, -1.1 if big else -0.7, 0.0]
        if comp["type"] == "ground":
            offset = [0.0, -1.0, 0.0]
        elif comp["type"] in ("npn", "pnp"):
            offset = [0.75, 0.0, 0.0]
        elif comp["type"] == "chip":
            _, order = catalog.terminals_of("chip", comp["params"])
            h = (len(order) // 2) * 0.5 + 0.1
            offset = [0.0, -(h / 2 + 0.45), 0.0] if not vertical else [h / 2 + 0.3, 0.0, 0.0]
    align = "CENTER"
    if comp.get("label_offset") is None and (vertical or comp["type"] in ("npn", "pnp")):
        align = "LEFT"
    body = "\n".join(lines)
    obj = U.text(cid + "_label", body, 0.24, (0, 0, 0), label_material(), None, U.collection(COL_COMPONENTS),
                 align=align)
    obj.location = (root.location.x + offset[0], root.location.y + offset[1], root.location.z + 0.02 + offset[2])
    obj.parent = root
    obj.matrix_parent_inverse = U.world_matrix_from(root.location, math.degrees(root.rotation_euler.z)).inverted()
    obj["cc_label_of"] = cid
    return obj


def build_wire(circ, wid):
    old = wire_object(wid)
    if old is not None:
        U.delete_object_tree(old)
    wire = circ.wires[wid]
    pts = circ.wire_points(wid)
    radius = float(circ.settings.get("wire_radius", 0.035))
    if circ.settings.get("wire_look") == "glass":
        radius *= 2.2
    obj = U.poly_curve(wid, pts, radius, wire_material(circ, wire), None, U.collection(COL_WIRES))
    obj.data.bevel_resolution = 3
    obj["cc_wire"] = wid
    obj["cc_points"] = json.dumps(pts)
    _junction_dots(circ)
    return obj


def _junction_dots(circ):
    """Solder dots wherever three or more wire ends meet at the same terminal."""
    col = U.collection(COL_WIRES)
    counts = {}
    for w in circ.wires.values():
        for end in (w["from"], w["to"]):
            counts[end] = counts.get(end, 0) + 1
    wanted = {ref for ref, n in counts.items() if n >= 2 and circ.components.get(ref.split(".")[0], {}).get("type") != "junction"}
    for obj in list(col.objects):
        if obj.get("cc_dot") and obj["cc_dot"] not in wanted:
            U.delete_object_tree(obj)
    mat = models.M("ink") if circ.settings.get("style") == "schematic" else models.M("silver")
    for ref in wanted:
        try:
            p = circ.terminal_world(ref)
        except (KeyError, ValueError):
            continue
        name = "dot_" + ref
        dot = bpy.data.objects.get(name)
        if dot is None:
            dot = U.sphere(name, float(circ.settings.get("wire_radius", 0.035)) * 2.0, (0, 0, 0), mat, None, col)
            dot["cc_dot"] = ref
        dot.location = p


def rebuild_all(circ=None):
    circ = circ or load_circuit()
    for name in (COL_COMPONENTS, COL_WIRES):
        U.clear_collection(name)
    for cid in list(circ.components):
        build_component(circ, cid)
    for wid in list(circ.wires):
        build_wire(circ, wid)
    return circ


def wires_touching(circ, cid):
    return [wid for wid, w in circ.wires.items()
            if w["from"].split(".")[0] == cid or w["to"].split(".")[0] == cid]


# ------------------------------------------------------------ target lookup
def resolve_objects(targets, circ=None, include_children=True):
    """Resolve ids / object names / group keywords to a list of Blender objects.

    Keywords: 'all', 'components', 'wires', 'labels', 'flow', 'annotations', 'effects'.
    """
    circ = circ or load_circuit()
    if isinstance(targets, str):
        targets = [targets]
    out = []

    def add_tree(obj):
        if obj is None:
            return
        out.append(obj)
        if include_children:
            out.extend(obj.children_recursive)

    groups = {"wires": COL_WIRES, "flow": COL_FLOW, "annotations": COL_ANNOTATIONS, "effects": COL_EFFECTS,
              "environment": COL_ENV}
    for t in targets or []:
        t = str(t)
        low = t.lower()
        if low in ("all", "circuit"):
            for cid in circ.components:
                add_tree(comp_root(cid))
            out.extend(bpy.data.collections[COL_WIRES].objects if COL_WIRES in bpy.data.collections else [])
        elif low == "components":
            for cid in circ.components:
                add_tree(comp_root(cid))
        elif low == "labels":
            out.extend(o for o in bpy.data.objects if o.get("cc_label_of"))
        elif low in groups:
            col = bpy.data.collections.get(groups[low])
            if col:
                out.extend(col.all_objects)
        elif t in circ.components:
            add_tree(comp_root(t))
        elif t in circ.wires:
            add_tree(wire_object(t))
        elif bpy.data.objects.get(t) is not None:
            add_tree(bpy.data.objects[t])
        elif bpy.data.collections.get(t) is not None:
            out.extend(bpy.data.collections[t].all_objects)
        else:
            raise KeyError("Unknown target '%s' (component id, wire id, object name, collection or keyword "
                           "all/components/wires/labels/flow/annotations/effects)" % t)
    seen, uniq = set(), []
    for o in out:
        if o.name not in seen:
            seen.add(o.name)
            uniq.append(o)
    return uniq


def target_point(target, circ=None):
    """World position for a component id, terminal ref ('R1.a'), wire id, object name or [x,y,z]."""
    circ = circ or load_circuit()
    if isinstance(target, (list, tuple)):
        v = list(target) + [circ.settings.get("height", 0.3)] * (3 - len(target))
        return [float(x) for x in v[:3]]
    t = str(target)
    if "." in t and t.split(".")[0] in circ.components:
        return circ.terminal_world(t)
    if t in circ.components:
        root = comp_root(t)
        if root is not None:
            return list(root.location)
        c = circ.get(t)
        return [c["position"][0], c["position"][1], circ.settings["height"]]
    if t in circ.wires:
        pts = circ.wire_points(t)
        cum = U.cumulative_lengths(pts)
        return list(U.point_along(pts, cum, cum[-1] / 2))
    obj = bpy.data.objects.get(t)
    if obj is not None:
        bpy.context.view_layer.update()
        return list(obj.matrix_world.translation)
    raise KeyError("Unknown target '%s'" % t)


def _on_hud(obj):
    """True for screen-pinned objects (parented, directly or not, to the camera)."""
    while obj is not None:
        if obj.get("cc_hud") or obj.type == "CAMERA":
            return True
        obj = obj.parent
    return False


def circuit_bounds(circ=None, include_annotations=False):
    circ = circ or load_circuit()
    bpy.context.view_layer.update()
    xs, ys, zs = [], [], []
    names = [COL_COMPONENTS, COL_WIRES] + ([COL_ANNOTATIONS] if include_annotations else [])
    for name in names:
        col = bpy.data.collections.get(name)
        if not col:
            continue
        for obj in col.all_objects:
            if obj.type not in ("MESH", "CURVE", "FONT") or _on_hud(obj):
                continue
            for corner in obj.bound_box:
                w = obj.matrix_world @ U.Vector(corner)
                xs.append(w.x)
                ys.append(w.y)
                zs.append(w.z)
    if not xs:
        for c in circ.components.values():
            xs.append(c["position"][0])
            ys.append(c["position"][1])
            zs.append(0.0)
    if not xs:
        return [-1, -1, 0], [1, 1, 1]
    return [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]
