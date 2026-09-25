"""Scripted example: produce a ~20 s explainer video without an AI in the loop.

It talks to the Circuit Lab bridge exactly like the MCP server does, so it is also a handy reference for the
command names and parameters the AI uses.

    1. start Blender with the add-on and press "Start MCP Bridge" (or: blender -b --python run_headless.py)
    2. python examples/led_explainer_video.py [output.mp4]
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp_server"))

from blender_circuits_mcp.connection import BlenderConnection  # noqa: E402

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "renders/led_explainer.mp4")


def main():
    b = BlenderConnection()
    call = b.send
    ids = call("build_example", {"name": "led_circuit"})["ids"]
    resistor, led, switch = ids["resistor"], ids["led"], ids["switch"]
    call("update_component", {"id": switch, "params": {"closed": False}})
    call("setup_scene", {"theme": "dark", "engine": "eevee", "duration": 20})

    # Physics: the switch closes 1 s into a 3 s simulation.
    print(call("simulate_transient", {"duration": 3, "events": [{"time": 1.0, "component": switch, "closed": True}]}))

    # Beat 1 (0-4 s): title + the circuit assembles itself.
    call("add_title", {"title": "How an LED circuit works", "subtitle": "follow the electrons", "time": 0,
                       "duration": 3.5})
    call("build_up_sequence", {"start": 0.5})  # returns end_time (~4 s) for chaining the next beat
    call("frame_circuit", {"view": "front"})

    # Beat 2 (5-17 s): simulation stretched over 12 s of video -> switch closes at 9 s.
    call("animate_circuit", {"start": 5, "end": 17})
    call("frame_circuit", {"view": "iso", "time": 6, "transition": 2})
    call("add_callout", {"text": "Closing the switch completes the loop", "target": switch, "start": 8.5, "end": 12})
    call("highlight", {"targets": [switch], "time": 8.5})
    call("add_readout", {"component": led, "quantity": "current", "start": 5, "end": 17, "hud": True,
                         "position": [0.45, -0.85], "prefix": "LED current: "})
    call("focus_on", {"target": resistor, "time": 13, "transition": 1.5, "distance": 5})
    call("add_callout", {"text": "The resistor limits the current to ~20 mA", "target": resistor, "start": 13,
                         "end": 16.5})

    # Beat 3 (17-20 s): pull back.
    call("frame_circuit", {"view": "front", "time": 18.5, "transition": 1.5})
    call("add_title", {"title": "No resistor = burnt LED!", "time": 17.5, "duration": 2.5, "position": "top"})

    call("save_blend", {"filepath": OUT.replace(".mp4", ".blend")})
    print(call("render_animation", {"filepath": OUT}))


if __name__ == "__main__":
    main()
