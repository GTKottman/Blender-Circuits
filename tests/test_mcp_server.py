"""Tests for the MCP forwarding server (needs the `mcp` package; Blender side is faked)."""

import asyncio
import json
import re
import socket
import threading

import pytest

pytest.importorskip("mcp")

from blender_circuits_mcp import connection, server  # noqa: E402


class FakeBlender:
    """Minimal line-JSON server standing in for the Blender add-on."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.requests = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.sock.accept()
        buf = b""
        while True:
            data = conn.recv(65536)
            if not data:
                return
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                req = json.loads(line)
                self.requests.append(req)
                if req["command"] == "fail":
                    resp = {"id": req["id"], "status": "error", "message": "KeyError: No component 'X'"}
                else:
                    resp = {"id": req["id"], "status": "ok", "result": {"echo": req["params"]}}
                conn.sendall((json.dumps(resp) + "\n").encode())


@pytest.fixture()
def fake(monkeypatch):
    fb = FakeBlender()
    monkeypatch.setattr(connection, "_connection", connection.BlenderConnection("127.0.0.1", fb.port, 10))
    return fb


def test_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    for required in ("add_component", "connect", "simulate_dc", "simulate_transient", "animate_circuit", "add_plot",
                     "frame_circuit", "preview", "render_animation", "execute_blender_python"):
        assert required in names
    assert len(names) >= 45


def test_forwarding_strips_none(fake):
    out = server.add_component(type="resistor", position=[1, 2], params={"resistance": 220})
    assert out["echo"] == {"type": "resistor", "position": [1, 2], "rotation": 0.0, "params": {"resistance": 220}}
    assert fake.requests[-1]["command"] == "add_component"


def test_errors_become_tool_errors(fake):
    with pytest.raises(server.ToolError, match="No component"):
        server._call("fail")


def test_every_tool_targets_a_real_blender_command():
    """Static check: each _call("name") in the MCP server exists in the add-on's command registry."""
    pytest.importorskip("bpy")  # the command registry imports bpy
    from blender_circuits import commands
    src = open(server.__file__).read()
    called = set(re.findall(r'_call\("([a-z_]+)"', src))
    missing = called - set(commands.COMMANDS)
    assert not missing, missing
