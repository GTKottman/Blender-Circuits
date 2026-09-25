"""TCP JSON server that runs inside Blender.

Protocol: newline-delimited JSON.  Request ``{"id": 1, "command": "add_component", "params": {...}}``,
response ``{"id": 1, "status": "ok", "result": {...}}`` or ``{"id": 1, "status": "error", "message": ...}``.

Network I/O happens on background threads; commands are always executed on
Blender's main thread (via ``bpy.app.timers`` in the UI, or ``run_forever`` in
background mode) because bpy is not thread safe.
"""

import json
import queue
import socket
import threading
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9877
REQUEST_TIMEOUT = 3600.0


class CircuitServer:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, handler=None):
        self.host = host
        self.port = int(port)
        self.handler = handler
        self._queue = queue.Queue()
        self._sock = None
        self._thread = None
        self._running = False
        self._timer_registered = False

    # ----------------------------------------------------------- lifecycle
    @property
    def running(self):
        return self._running

    def start(self, use_timer=True):
        if self._running:
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, name="CircuitLabServer", daemon=True)
        self._thread.start()
        if use_timer:
            import bpy
            if not bpy.app.timers.is_registered(self._timer):
                bpy.app.timers.register(self._timer, first_interval=0.05, persistent=True)
            self._timer_registered = True
        print("Circuit Lab MCP bridge listening on %s:%d" % (self.host, self.port))

    def stop(self):
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._timer_registered:
            import bpy
            if bpy.app.timers.is_registered(self._timer):
                bpy.app.timers.unregister(self._timer)
            self._timer_registered = False
        print("Circuit Lab MCP bridge stopped")

    # ----------------------------------------------------------- main thread
    def _timer(self):
        if not self._running:
            return None
        self.process_pending()
        return 0.05

    def process_pending(self, max_items=50):
        """Execute queued commands (must be called on Blender's main thread)."""
        n = 0
        while n < max_items:
            try:
                request, holder, done = self._queue.get_nowait()
            except queue.Empty:
                break
            holder["response"] = self._execute(request)
            done.set()
            n += 1
        return n

    def run_forever(self, poll=0.02):
        """Blocking loop for background (`blender -b`) mode."""
        if not self._running:
            self.start(use_timer=False)
        try:
            while self._running:
                if not self.process_pending():
                    time.sleep(poll)
        except KeyboardInterrupt:
            pass
        finally:
            time.sleep(0.2)  # let the client threads flush their last responses (e.g. to 'shutdown')
            self.stop()

    def _execute(self, request):
        if self.handler is None:
            from . import commands
            handler = commands.run
        else:
            handler = self.handler
        name = request.get("command") or request.get("type")
        params = request.get("params") or {}
        if name == "shutdown":
            self._running = False
            return {"status": "ok", "result": {"shutdown": True}}
        return handler(name, params)

    # ----------------------------------------------------------- networking
    def _accept_loop(self):
        while self._running:
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._client_loop, args=(conn,), daemon=True).start()

    def _client_loop(self, conn):
        conn.settimeout(None)
        buf = b""
        try:
            while self._running:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    response = self._handle_line(line)
                    conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except (ConnectionError, OSError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _handle_line(self, line):
        try:
            request = json.loads(line.decode("utf-8"))
        except ValueError as exc:
            return {"status": "error", "message": "Invalid JSON: %s" % exc}
        holder, done = {}, threading.Event()
        self._queue.put((request, holder, done))
        if not done.wait(REQUEST_TIMEOUT):
            return {"id": request.get("id"), "status": "error", "message": "Timed out waiting for Blender"}
        response = holder["response"]
        response["id"] = request.get("id")
        return response


_server = None


def get_server():
    return _server


def start_server(host=DEFAULT_HOST, port=DEFAULT_PORT, use_timer=True):
    global _server
    if _server is not None and _server.running:
        return _server
    _server = CircuitServer(host, port)
    _server.start(use_timer=use_timer)
    return _server


def stop_server():
    global _server
    if _server is not None:
        _server.stop()
    _server = None
