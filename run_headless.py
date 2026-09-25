"""Run the Circuit Lab bridge without the Blender UI (servers, CI, render farms).

    blender -b --python run_headless.py -- --port 9877 [--blend scene.blend]

Also works with the `bpy` pip module:  python run_headless.py --port 9877
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import blender_circuits  # noqa: E402
from blender_circuits import server  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description="Circuit Lab headless MCP bridge")
    parser.add_argument("--host", default=server.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=server.DEFAULT_PORT)
    parser.add_argument("--blend", help="open this .blend file first")
    args = parser.parse_args(argv)
    if args.blend:
        bpy.ops.wm.open_mainfile(filepath=args.blend)
    blender_circuits.register()
    srv = server.CircuitServer(args.host, args.port)
    srv.start(use_timer=False)
    srv.run_forever()


if __name__ == "__main__":
    main()
