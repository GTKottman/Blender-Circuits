# Blender Circuits — Circuit Lab MCP bridge

Circuit Lab turns Blender into a 3D electronics classroom that an AI assistant can drive over the
[Model Context Protocol](https://modelcontextprotocol.io). The AI can design a circuit, **simulate it** with the
built-in SPICE-style solver, and then produce motion-graphics explainer videos about it: electrons flow along
the wires at speeds set by the real currents, LEDs and bulbs glow, capacitors fill with charge, meters show live
readings, and graphs draw themselves. It can also add titles, callouts, camera moves and a zoomed-in view of the
electrons inside a wire.

```
 AI assistant ──MCP (stdio)──▶ blender-circuits-mcp ──TCP :9877 (JSON lines)──▶ Blender + Circuit Lab add-on
 (Claude, …)                    mcp_server/                                     blender_circuits/
```

## Features

| Area | What the AI can do |
| --- | --- |
| **Components** (23 types) | resistor (with correct colour bands), potentiometer, battery, DC supply, AC source, current source, capacitor (plates / electrolytic), inductor, diode, LED (8 colours), bulb, switch, push button, ammeter, voltmeter, motor, speaker, fuse, NPN/PNP transistors, ground, junction, IC chip. Each comes in a **realistic 3D** model and a standard **schematic symbol**. |
| **Wiring** | Terminal-to-terminal wires with automatic right-angle routing, waypoints and solder dots. Wire looks: copper, insulated, or see-through glass. |
| **Simulation** | DC operating point and transient (time-domain) analysis using Modified Nodal Analysis and Newton-Raphson. Handles diodes/LEDs (Shockley model), BJTs (Ebers-Moll), capacitors, inductors, AC sources, switch and potentiometer events. Warns about burnt-out LEDs, short circuits and blown fuses. |
| **Physics animation** | Electron flow (or conventional current, or both) with speed proportional to current. Also: LED/bulb brightness, motor spin, speaker movement, live meter displays, switch levers, capacitor charge build-up, current-direction arrows, and a voltage heat-map on the wires with a legend. |
| **Storytelling** | Build-up intro (parts pop in, wires draw themselves), titles pinned to the screen, 3D labels, callouts with leader lines, arrows, pulsing highlights, live number readouts, oscilloscope-style graphs that draw in sync, a magnified wire showing the ion lattice and drifting electrons, and fade/pop/drop/draw reveals. |
| **Camera & render** | Auto-framing views (front/top/iso/…), focus-on-part, keyframed camera paths, orbits, depth of field, 5 themes (dark, blueprint, light, studio, workbench), bloom, EEVEE/Cycles, low-res **preview images returned to the AI** so it can check its own work, and MP4/MOV/WebM/PNG output. |
| **Escape hatches** | `run_batch` (many commands in one round trip), `execute_blender_python`, `list_blender_commands`. |

## Installation

### 1. Blender add-on (Blender 4.2 or newer)

```bash
python build_addon.py            # -> dist/blender_circuits.zip
```

In Blender: **Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk…**, pick `dist/blender_circuits.zip`, and enable
**Circuit Lab (MCP bridge)**. Then open the 3D View sidebar (**N**) ▸ **Circuit Lab** tab ▸ **Start MCP Bridge**.
To start the bridge every time Blender opens, turn on *Start bridge automatically* in the add-on preferences.
The default port is 9877.

**Headless** (servers, render farms, CI), with no Blender window:

```bash
blender -b --python run_headless.py -- --port 9877            # optional: --blend existing.blend
# or with the bpy pip module (Python 3.11):  pip install bpy && python run_headless.py
```

### 2. MCP server

```bash
pip install ./mcp_server          # provides the `blender-circuits-mcp` command
```

Add it to your MCP client. Claude Code:

```bash
claude mcp add blender-circuits -- blender-circuits-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "blender-circuits": {
      "command": "blender-circuits-mcp",
      "env": { "BLENDER_CIRCUITS_PORT": "9877" }
    }
  }
}
```

Without installing, you can use `"command": "python", "args": ["-m", "blender_circuits_mcp"]` with `"cwd"` or
`PYTHONPATH` pointing at `mcp_server/`. Environment variables: `BLENDER_CIRCUITS_HOST` (default `127.0.0.1`),
`BLENDER_CIRCUITS_PORT` (default `9877`), `BLENDER_CIRCUITS_TIMEOUT` (default 900 seconds, which covers long renders).
The server works with MCP Python SDK 1.x (FastMCP) and 2.x (MCPServer).

## Using it

Ask your assistant something like *"Make a 45-second video explaining why an LED needs a resistor"*. The server
also ships an `explainer_video` prompt and a `circuitlab://guide` resource that walk the AI through the workflow:

1. `build_example` **or** `new_circuit` → `add_components` → `connect_many`
2. `setup_scene(theme, engine, duration)`
3. `simulate_dc` or `simulate_transient(duration, events=[{"time": 0.5, "component": "S1", "closed": true}])`
4. `animate_circuit(start, end)`, plus `show_voltage_colors` / `add_current_arrows` if useful
5. `build_up_sequence`, `add_title`, `add_callout`, `highlight`, `add_readout`, `add_plot`, `add_wire_closeup`
6. `frame_circuit`, `focus_on`, `camera_path`, `orbit_camera`
7. `preview(time)` to look at key frames → `render_animation("renders/video.mp4")`

`examples/led_explainer_video.py` produces a complete 20-second video by calling the same commands directly. It's
also a useful reference for command names and parameters.

### Conventions

* The circuit lies on the **XY plane** (Z up). Two-terminal parts are 2 units long with terminals at local x = ±1,
  so an integer grid with parts 3–4 units apart works well. `rotation` is in degrees about Z.
* Terminals are referenced as `"<id>.<terminal>"`:

  | Part | Terminals |
  | --- | --- |
  | resistor, capacitor, inductor, bulb, switch, motor, … | `a`, `b` |
  | battery, dc_source, ac_source, current_source | `+`, `-` |
  | diode, led | `anode`, `cathode` (aliases `a`, `k`) |
  | npn, pnp | `b`, `c`, `e` |
  | potentiometer | `a`, `b`, `w` (wiper) |
  | ground / junction / chip | `gnd` / `n` / `p1`…`pN` |

* Values accept engineering notation: `"4.7k"`, `"100uF"`, `"2.2M"`, `"10mA"`.
* All animation times are **seconds of video**. Transient simulations run in simulated seconds and are stretched
  onto the `start`–`end` window you give (`time_scale` = video seconds per simulated second).
* Electrons move against conventional current. Use `mode="conventional"` or `"both"` to compare the two, and
  `scaling="sqrt"`/`"log"` when currents differ by orders of magnitude.

### Built-in examples

`led_circuit`, `series_bulbs`, `parallel_bulbs`, `voltage_divider`, `rc_charging`, `transistor_switch`,
`short_circuit`, `ohms_law`, `motor_circuit`, `ac_rc`, `dimmer`. Each returns the component ids and suggested
next steps.

## Tool reference

| Group | Tools |
| --- | --- |
| Inspect | `get_scene_info`, `get_circuit`, `list_component_types`, `list_examples`, `list_blender_commands` |
| Design | `new_circuit`, `build_example`, `add_component(s)`, `update_component`, `remove_component`, `connect`, `connect_many`, `remove_wire`, `set_switch`, `set_circuit_settings` |
| Simulate | `simulate_dc`, `simulate_transient`, `get_results` |
| Animate | `animate_circuit`, `animate_current_flow`, `animate_component_effects`, `add_current_arrows`, `show_voltage_colors`, `animate_switch`, `animate_visibility`, `build_up_sequence`, `animate_transform`, `highlight`, `clear_animation` |
| Annotate | `add_title`, `add_label`, `add_callout`, `add_arrow`, `add_readout`, `add_plot`, `add_wire_closeup`, `clear_annotations` |
| Scene & camera | `setup_scene`, `set_timeline`, `frame_circuit`, `set_camera`, `focus_on`, `camera_path`, `orbit_camera`, `depth_of_field` |
| Output | `preview` (returns an image), `render_still`, `render_animation`, `save_blend` |
| Power tools | `run_batch`, `execute_blender_python` |

The circuit model is stored inside the .blend file (text block `CircuitLab_model.json`), so a saved scene can be
reopened, rebuilt (**Rebuild Circuit** button) and extended later.

## Development

```
blender_circuits/          Blender add-on
  catalog.py, circuit.py,  pure Python: component catalog, circuit model + routing,
  simulation.py, examples  MNA simulator, example circuits (testable without Blender)
  models.py                realistic + schematic 3D models
  lab.py                   persistence, building objects, target lookup
  animation.py             electron flow, component effects, voltage colours, reveals
  annotations.py           labels, callouts, titles, readouts, plots, wire close-up
  scene_tools.py           themes, board, lights, camera, HUD, rendering
  commands.py              command registry used by the socket server
  server.py                threaded TCP server, executes on Blender's main thread
mcp_server/                MCP server (forwards tools to the add-on)
run_headless.py            background-mode bridge
tests/                     pytest suite
```

```bash
pip install pytest mcp           # simulator + MCP tests
pip install bpy                  # (optional, Python 3.11) enables the Blender integration tests
python -m pytest tests
```

## Limitations

* EEVEE needs a GPU/OpenGL context. On headless machines without one, use `engine="cycles"`.
* The simulator is intended for teaching: ideal wires (1 mΩ), a bulb is a fixed resistor, a motor is its winding
  resistance, and transient analysis uses backward Euler. It is not a replacement for a full SPICE simulator.
* Moving a component with `animate_transform` does not drag its wires along. Use it for exploded views and
  reveals, and `update_component` to change the circuit itself.
