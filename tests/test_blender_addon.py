"""Integration tests that run the add-on inside Blender (via the `bpy` pip module or Blender's python).

Skipped automatically when bpy is not importable.
"""

import json
import socket
import threading

import pytest

bpy = pytest.importorskip("bpy")

import blender_circuits  # noqa: E402
from blender_circuits import commands as C  # noqa: E402
from blender_circuits import examples, lab, models, server  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def addon():
    blender_circuits.register()
    yield
    blender_circuits.unregister()


def run(_command, **params):
    r = C.run(_command, params)
    assert r["status"] == "ok", r.get("message") + "\n" + r.get("traceback", "")
    return r["result"]


@pytest.mark.parametrize("style", ["realistic", "schematic"])
def test_every_component_type_builds(style):
    run("new_circuit", style=style)
    for i, t in enumerate(sorted(C.catalog.COMPONENTS)):
        out = run("add_component", type=t, position=[(i % 6) * 4, -(i // 6) * 4])
        root = lab.comp_root(out["id"])
        assert root is not None and root.children, t
    assert len(lab.load_circuit().components) == len(C.catalog.COMPONENTS)


@pytest.mark.parametrize("name", sorted(examples.EXAMPLES))
def test_examples_build_simulate_animate(name):
    info = run("build_example", name=name)
    for wid in info["wires"]:
        assert lab.wire_object(wid) is not None
    run("simulate_dc")
    out = run("animate_circuit", start=0, end=2, key_step=2)
    assert out["flow"]["particles"] > 0


def test_led_glows_and_switch_animates():
    run("build_example", name="led_circuit")
    run("update_component", id="S1", params={"closed": False})
    run("simulate_transient", duration=2, events=[{"time": 1.0, "component": "S1", "closed": True}])
    run("animate_circuit", start=0, end=4)
    glow = models.parts_of(lab.comp_root("LED1"))["glow"].active_material
    fc = glow.node_tree.animation_data.action.fcurves[0]
    before, after = fc.evaluate(bpy.context.scene.frame_start + 30), fc.evaluate(bpy.context.scene.frame_start + 110)
    assert before < 0.1 < after
    lever = models.parts_of(lab.comp_root("S1"))["lever"]
    assert lever.animation_data is not None


def test_particles_move_with_current_and_stay_on_wire():
    run("build_example", name="series_bulbs")
    run("simulate_dc")
    run("animate_current_flow", start=0, end=2, include_components=False)
    circ = lab.load_circuit()
    col = bpy.data.collections[lab.COL_FLOW]
    obj = next(o for o in col.objects if o.get("cc_flow") == "W1")
    scene = bpy.context.scene
    scene.frame_set(10)
    p1 = obj.matrix_world.translation.copy()
    scene.frame_set(20)
    p2 = obj.matrix_world.translation.copy()
    assert (p2 - p1).length > 1e-3
    pts = circ.wire_points("W1")
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert min(xs) - 1e-4 <= p2.x <= max(xs) + 1e-4 and min(ys) - 1e-4 <= p2.y <= max(ys) + 1e-4


def test_text_track_updates_meter_display():
    run("build_example", name="rc_charging")
    run("simulate_transient", duration=5, events=[{"time": 0.2, "component": "S1", "closed": True}])
    run("animate_circuit", start=0, end=5)
    disp = models.parts_of(lab.comp_root("VM1"))["display"]
    bpy.context.scene.frame_set(2)
    early = disp.data.body
    bpy.context.scene.frame_set(140)
    late = disp.data.body
    assert early != late and late.endswith("V")


def test_annotations_and_camera():
    run("build_example", name="rc_charging")
    run("setup_scene", theme="dark", engine="cycles", duration=8)
    run("simulate_transient", duration=5, events=[{"time": 0.2, "component": "S1", "closed": True}])
    assert run("add_plot", signals=[{"component": "C1", "quantity": "voltage"},
                                    {"component": "R1", "quantity": "current"}], end=8)["normalized"]
    run("add_readout", component="C1", quantity="voltage", end=8)
    run("add_title", title="Hello", subtitle="world")
    run("add_callout", text="note", target="C1", start=1)
    run("add_arrow", start_point="R1", end_point="C1", time=1, curved=1)
    run("add_label", text="hud", hud=True, position=[0, 0.9])
    run("add_wire_closeup", wire="W2", end=8, electrons=10)
    run("show_voltage_colors", end=8)
    run("add_current_arrows", end=8)
    run("highlight", targets=["C1"], time=1)
    run("build_up_sequence")
    run("frame_circuit", view="iso", time=2)
    run("focus_on", target="C1", time=4)
    run("orbit_camera", start=4, end=6, degrees=45)
    run("camera_path", keys=[{"time": 6.5, "location": [0, -10, 8], "look_at": "B1"}])
    info = run("get_scene_info")
    assert info["timeline"]["duration_s"] >= 8
    assert any(n.startswith("Plot") for n in info["annotations"])
    assert run("clear_annotations")["deleted"] > 0
    run("clear_animation", what="all")


def test_frame_circuit_keeps_every_component_in_view():
    from bpy_extras.object_utils import world_to_camera_view
    run("build_example", name="transistor_switch")
    run("setup_scene", engine="cycles")
    for view in ("front", "iso", "top", "left"):
        run("frame_circuit", view=view)
        bpy.context.view_layer.update()
        scene = bpy.context.scene
        for cid in lab.load_circuit().components:
            co = world_to_camera_view(scene, scene.camera, lab.comp_root(cid).matrix_world.translation)
            assert 0 <= co.x <= 1 and 0 <= co.y <= 1, (view, cid, tuple(co))


def test_error_messages_are_helpful():
    run("new_circuit")
    r = C.run("connect", {"a": "X1.a", "b": "Y1.b"})
    assert r["status"] == "error" and "No component" in r["message"]
    r = C.run("add_component", {"type": "resistor", "bogus": 1, "position": [0, 0]})
    assert r["status"] == "ok"  # unknown shorthand keys become params
    r = C.run("simulate_dc", {"nonsense": 1})
    assert r["status"] == "error" and "unknown parameter" in r["message"]
    r = C.run("not_a_command", {})
    assert r["status"] == "error" and "list_commands" in r["message"]


def test_batch_and_python():
    out = run("batch", commands=[{"command": "new_circuit"},
                                 {"command": "add_component", "params": {"type": "battery", "position": [0, 0]}},
                                 {"command": "does_not_exist"}, {"command": "ping"}])
    assert [r["ok"] for r in out["results"]] == [True, True, False]
    assert run("execute_python", code="result = len(lab.load_circuit().components)")["result"] == 1


def test_socket_server_roundtrip():
    srv = server.CircuitServer("127.0.0.1", 0)
    srv.port = 0
    srv.start(use_timer=False)
    port = srv._sock.getsockname()[1]
    replies = []

    def client():
        with socket.create_connection(("127.0.0.1", port)) as s:
            s.sendall(b'{"id": 7, "command": "ping"}\n{"id": 8, "command": "nope"}\n')
            buf = b""
            while buf.count(b"\n") < 2:
                buf += s.recv(4096)
            replies.extend(json.loads(line) for line in buf.decode().splitlines())

    t = threading.Thread(target=client)
    t.start()
    while t.is_alive():
        srv.process_pending()
        t.join(0.01)
    srv.stop()
    assert replies[0]["id"] == 7 and replies[0]["status"] == "ok" and replies[0]["result"]["pong"]
    assert replies[1]["id"] == 8 and replies[1]["status"] == "error"


def test_save_and_reload_model(tmp_path):
    run("build_example", name="ohms_law")
    path = str(tmp_path / "scene.blend")
    run("save_blend", filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    circ = lab.load_circuit()
    assert "AM1" in circ.components and len(circ.wires) == 5
    assert run("rebuild")["components"] == len(circ.components)
