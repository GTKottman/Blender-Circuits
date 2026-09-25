# Circuit Lab tool cheat sheet

Generated from the MCP server's tool schemas. Required params are **bold**; the others are optional and show their defaults.

## Inspect

- `get_scene_info()` — Summary of the current circuit (components with terminal positions, wires), available simulation results, timeline, camera, annotations and render settings.
- `get_circuit()` — Full circuit model with parameters, wires and terminal world positions.
- `list_component_types()` — Catalog of every component type: description, terminal names/positions and default parameters.
- `list_examples()` — Ready-made teaching circuits that build_example can create (LED loop, series/parallel bulbs, voltage divider, RC charging, transistor switch, short circuit, Ohm's law bench, motor, AC RC, dimmer).
- `list_blender_commands()` — Every command implemented by the Blender add-on with its full parameter signature.
- `get_results(source='auto', component, max_points=50)` — Numeric simulation data (per component/wire).

## Design

- `new_circuit(style='realistic', wire_look='copper', show_labels=True, show_values=True, clear_annotations=True)` — Start a fresh, empty circuit.
- `build_example(**name**, origin, style, replace=True)` — Build an example circuit.
- `add_component(**type**, **position**, rotation=0.0, id, params, label, style, show_value)` — Add one component at [x, y] (grid units).
- `add_components(**components**)` — Add several components at once.
- `update_component(**id**, params, position, rotation, label, style)` — Change a component (value, position, rotation, label, style).
- `remove_component(**id**)` — Delete a component and the wires attached to it.
- `connect(**a**, **b**, via, route='auto', color, id)` — Draw a wire between two terminals, e.g. a="B1.+", b="R1.a".
- `connect_many(**connections**, route='auto')` — Several wires at once: [["B1.+", "R1.a"], ["R1.b", "LED1.anode"], {"from": "LED1.cathode", "to": "B1.-", "via": [[6, -2]]}].
- `remove_wire(**id**)` — Delete a wire.
- `set_switch(**id**, closed=True, time, duration=0.3)` — Open/close a switch or push button.
- `set_circuit_settings(style, wire_look, show_labels, show_values, wire_radius)` — Change global look (e.g. switch the whole circuit between realistic and schematic) and rebuild.

## Simulate

- `simulate_dc()` — Solve the steady state: voltage, current and power for every component and wire, LED/bulb brightness, meter readings, plus warnings (burnt-out LEDs, short circuits, blown fuses).
- `simulate_transient(**duration**, events, dt, samples=400, start_from_dc=False)` — Simulate over time (in simulated seconds): capacitor charging, inductors, AC sources, switching.

## Animate

- `animate_circuit(start=0.0, end, source='auto', mode='electron', time_scale, density=2.5, speed=1.5, scaling='linear', max_speed=6.0, particle_radius=0.06, include_components=True, show_charge=True, glow_strength=12.0, fade_in=0.0)` — Bring the circuit to life from the latest simulation: charges flow along wires at speed proportional to current, LEDs/bulbs glow with current/power, motors spin, meters display live values, switch levers move at…
- `animate_current_flow(start=0.0, end, source='auto', mode='electron', density=2.5, speed=1.5, reference_current, scaling='linear', max_speed=6.0, particle_radius=0.06, color, include_components=True, time_scale, glow=3.0, fade_in=0.0)` — Only the moving charges (see animate_circuit).
- `animate_component_effects(start=0.0, end, source='auto', time_scale, glow_strength=12.0, light_power=15.0, show_charge=True)` — Only the component reactions (glow, spin, meters, switches, capacitor charge) - see animate_circuit.
- `add_current_arrows(start=0.0, end, source='auto', size=0.35, color='yellow', time_scale)` — Arrow on every wire pointing in the conventional current direction; its size follows the current.
- `show_voltage_colors(start=0.0, end, source='auto', colormap='thermal', vmin, vmax, legend=True, legend_position, time_scale)` — Colour every wire by its voltage (like a heat map: blue = low, red = high) with a legend - great for explaining voltage drops across components.
- `animate_switch(**id**, closed=True, time=0.0, duration=0.3)` — Animate a switch lever/button (visual only).
- `animate_visibility(**targets**, action='appear', time=0.0, duration=0.5, style='fade', stagger=0.0)` — Reveal or hide things at a time.
- `build_up_sequence(start=0.0, component_interval=0.6, wire_duration=0.5, style='pop', order)` — Assemble-the-circuit intro: components appear one by one, then every wire draws itself.
- `animate_transform(**target**, time=0.0, duration=1.0, location, rotation, scale, relative=False)` — Smoothly move/rotate (degrees)/scale a component or object - e.g. lift a part up to inspect it (relative=True, location=[0, 0, 2]).
- `highlight(**targets**, time=0.0, duration=1.5, color='yellow', pulses=2, radius, style='ring')` — Pulsing glowing ring around components (or terminals/points) to direct the viewer's attention.
- `clear_animation(what='flow')` — Remove animation: particles (flow), arrows/halos/charges (effects), keyframes, camera moves, or all.

## Annotate

- `add_title(**title**, subtitle, time=0.0, duration=3.0, position='center', size=0.09, color, background=False)` — Screen-space title card that fades in at `time` and out after `duration` (0 = stays).
- `add_label(**text**, position, target, offset=[0, 0.9, 0.2], size=0.35, color, align='CENTER', face_camera=False, hud=False, start, end, name, rotation)` — 3D text at a position or next to a target (component id / terminal ref).
- `add_callout(**text**, **target**, offset=[1.5, 1.5, 0.8], size=0.4, color, line_color='white', start, end, face_camera=False)` — Explanation bubble: text with a leader line pointing at a component/terminal (e.g. "Current limited to 20 mA by R1").
- `add_arrow(**start_point**, **end_point**, color='yellow', thickness=0.05, time, draw_duration=0.6, end, curved=0.0)` — 3D arrow between two points or targets (ids / terminal refs / [x, y, z]); draws itself at `time`; curved = arc height for a swooping arrow.
- `add_readout(**component**, quantity='current', position, prefix, source='auto', start=0.0, end, time_scale, size=0.3, color, hud=False, digits=3)` — Live number that updates every frame from the simulation, e.g. "I = 20.3 mA"; fades in at start.
- `add_plot(**signals**, position, width=6.0, height=3.0, start=0.0, end, time_scale, title, hud=False, rotation=[90, 0, 0], marker=True)` — Oscilloscope graph that draws itself in sync with the animation (needs simulate_transient).
- `add_wire_closeup(position=[0, -8, 2], length=6.0, radius=1.0, wire, start=0.0, end, electrons=60, drift_speed=0.6, thermal=0.15, labels=True, rotation=[0, 0, 0])` — Magnified see-through wire showing the copper ion lattice (vibrating) and free electrons that jitter randomly while slowly drifting - explains drift velocity.
- `clear_annotations(kind)` — Delete all annotations, or only one kind.

## Scene & camera

- `setup_scene(theme='dark', engine='eevee', resolution=[1920, 1080], fps=30, duration, board, glow=True, samples, transparent=False, style, wire_look)` — Make it look good: world colour, 3-point lighting, a board under the circuit, bloom/glow, render engine, resolution, fps and video duration (seconds).
- `set_timeline(duration, fps)` — Set total video length (seconds) and frame rate.
- `frame_circuit(view='front', margin=1.15, time, transition=1.5, lens, targets, include_annotations=False)` — Aim the camera so the whole circuit (or just `targets`) fills the frame.
- `set_camera(location, look_at, lens, time, transition=1.0)` — Place the camera explicitly (look_at = point or component id).
- `focus_on(**target**, time, transition=1.0, distance=4.0, elevation=40.0, azimuth=0.0, lens)` — Zoom the camera in on a component/terminal/object (animated when time is given).
- `camera_path(**keys**, smooth=True)` — Keyframed camera move: [{"time": 0, "location": [0,-15,10], "look_at": [5,0,0]}, {"time": 4, "location": [...], "look_at": "R1", "lens": 50}].
- `orbit_camera(start=0.0, end=10.0, degrees=360.0, radius, height, center)` — Circle the camera around the circuit (or a target) between start and end seconds, with easing.
- `depth_of_field(enabled=True, focus, fstop=2.8)` — Cinematic background blur focused on a component/object.

## Output & power tools

- `preview(time, width=640, samples=8)` — Render a quick low-resolution frame from the camera at `time` and return it as an image so you can check composition, readability and timing before the final render.
- `render_still(**filepath**, time, resolution_percentage, samples)` — Render a single full-quality frame to a PNG file.
- `render_animation(**filepath**, start, end, file_format='mp4', resolution_percentage, samples)` — Render the video (can take a while).
- `save_blend(**filepath**)` — Save the Blender project (.blend) so a human can tweak it later.
- `run_batch(**commands**, stop_on_error=True)` — Run many Circuit Lab commands in one round trip: [{"command": "add_component", "params": {...}}, ...].
- `execute_blender_python(**code**)` — Escape hatch: run Python inside Blender (bpy is available, plus lab/anim/ann/scene helper modules).
