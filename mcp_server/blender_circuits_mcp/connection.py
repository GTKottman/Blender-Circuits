"""Socket client that forwards commands to the Circuit Lab add-on running inside Blender."""

import itertools
import json
import os
import socket
import threading

DEFAULT_HOST = os.environ.get("BLENDER_CIRCUITS_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("BLENDER_CIRCUITS_PORT", "9877"))
DEFAULT_TIMEOUT = float(os.environ.get("BLENDER_CIRCUITS_TIMEOUT", "900"))


class BlenderError(RuntimeError):
    """Raised when Blender reports an error for a command."""


class BlenderConnection:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=DEFAULT_TIMEOUT):
        self.host, self.port, self.timeout = host, int(port), float(timeout)
        self._sock = None
        self._buf = b""
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def _connect(self):
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=10)
        except OSError as exc:
            self._sock = None
            raise BlenderError(
                "Cannot reach Blender at %s:%d (%s). Open Blender with the Circuit Lab add-on enabled and press "
                "'Start MCP Bridge' in the 3D View sidebar (N panel > Circuit Lab), or run it headless with "
                "`blender -b --python run_headless.py`." % (self.host, self.port, exc))
        self._sock.settimeout(self.timeout)
        self._buf = b""

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None

    def send(self, command, params=None):
        """Send a command and return its result (raises BlenderError on failure)."""
        with self._lock:
            for attempt in range(2):
                if self._sock is None:
                    self._connect()
                req_id = next(self._ids)
                payload = json.dumps({"id": req_id, "command": command, "params": params or {}}) + "\n"
                try:
                    self._sock.sendall(payload.encode("utf-8"))
                    line = self._readline()
                    break
                except (ConnectionError, BrokenPipeError, OSError) as exc:
                    self.close()
                    if attempt == 1 or isinstance(exc, socket.timeout):
                        raise BlenderError("Lost connection to Blender while running '%s': %s" % (command, exc))
            response = json.loads(line.decode("utf-8"))
        if response.get("status") != "ok":
            raise BlenderError(response.get("message", "Unknown Blender error"))
        return response.get("result")

    def _readline(self):
        while b"\n" not in self._buf:
            chunk = self._sock.recv(1 << 20)
            if not chunk:
                raise ConnectionError("Blender closed the connection")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line


_connection = None


def get_connection():
    global _connection
    if _connection is None:
        _connection = BlenderConnection()
    return _connection
