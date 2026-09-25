---
name: circuit-explainer-video
description: Produce educational motion-graphics videos and stills about electronics using the Circuit Lab Blender MCP tools (build_example, add_components, connect_many, simulate_dc/simulate_transient, animate_circuit, add_title, add_callout, add_plot, frame_circuit, preview, render_animation...). Use this skill whenever the user wants to explain, teach, visualize or animate a circuit or an electricity concept — Ohm's law, current flow, electrons vs conventional current, series vs parallel, voltage dividers, LEDs and resistors, capacitors charging, transistors as switches, short circuits, AC — or asks for a lesson clip, explainer, animation, diagram render or "video about circuits" in Blender, even if they don't mention Circuit Lab or MCP by name.
---

# Circuit explainer videos with Circuit Lab

Circuit Lab is a Blender add-on plus MCP server. You design a circuit, the built-in solver computes real
voltages and currents, and the animation layer turns those numbers into motion: electrons moving at a speed set
by the current, LEDs glowing, capacitors filling with charge, meters and graphs updating. Your job is to be the
director. Pick one clear idea, build a circuit that shows it, simulate it, stage the beats, look at the frames,
and deliver.

Because every visual comes from the simulation, the video is physically honest. Keep it that way. Never fake a
number in a caption. Read it from `simulate_dc`, `simulate_transient` or `get_results`.

## 0. Check the connection first

Call `get_scene_info`. If it fails with "Cannot reach Blender", stop and tell the user how to start the bridge:
open Blender with the add-on enabled, press **N**, open the **Circuit Lab** tab, click **Start MCP Bridge**.
Headless alternative: `blender -b --python run_headless.py`. If a circuit already exists, ask whether to keep
it or start over, rather than silently wiping someone's work.

## 1. Plan before building

Write a short beat sheet and show it to the user. A video that explains one idea well beats one that shows
every feature. Aim for 4–8 beats. Each beat has a time range, what is on screen, and the single sentence the
viewer should take away. Default length is 30–60 s unless the user asks otherwise.

Typical shape:

| Beat | Time | Content |
| --- | --- | --- |
| Hook | 0–4 s | Title card; the circuit assembles itself (`build_up_sequence`) |
| Setup | 4–10 s | Name the parts: callouts, highlight the key component |
| Action | 10–25 s | Switch closes, current flows, LED lights (`animate_circuit` over a transient run) |
| Numbers | 20–35 s | Readout or plot tying the motion to values (I = V/R, V_C rising) |
| Zoom | optional | `focus_on` a part, or `add_wire_closeup` for the microscopic view |
| Takeaway | last 3–5 s | Pull back, one-line summary title |

Also write a **narration script** with timestamps matching the beats, saved as a text/markdown file next to the
render. Circuit Lab produces no audio, and the user will usually want a voice-over. A comfortable narration pace
is about 2.5 words per second, so size each beat to fit its line.

## 2. Build the circuit

Start from `list_examples` / `build_example` when one fits: led_circuit, series_bulbs, parallel_bulbs,
voltage_divider, rc_charging, transistor_switch, short_circuit, ohms_law, motor_circuit, ac_rc, dimmer. These
layouts are tested, and the response gives you the component ids and suggested next steps. Change values with
`update_component` rather than rebuilding.

For custom circuits, read `references/layouts.md`. It explains the grid and rotation conventions and has
verified coordinates for loops, parallel branches and wires routed around parts. Key points:

- Parts are 2 units long (terminals at local x = ±1). Place them on an integer grid 3–4 units apart.
- Terminal refs look like `"B1.+"`, `"R1.a"`, `"LED1.anode"`, `"Q1.b"`, `"J1.n"`.
- Use `junction` parts for branch points in parallel circuits.
- Use `via` waypoints whenever a straight route would cut through a component.
- Use `add_components` and `connect_many` so the whole circuit is built in a few calls.
- `style="schematic"` (standard symbols; pairs well with the `blueprint` theme) is best for diagrams and
  analysis. `realistic` (3D parts) suits "what it looks like on the bench". You can switch mid-project with
  `set_circuit_settings`.
- `wire_look="glass"` shows the electrons inside see-through wires, which suits lessons about current.

## 3. Scene setup

Run `setup_scene(theme, engine, duration, resolution)` after the circuit exists, because it sizes the board to the
circuit. Themes: `dark` (default, glows pop), `blueprint` (schematics), `light` (print/slides), `studio` (PCB),
`workbench` (wood bench).

Engine: `eevee` is fast but needs a GPU. On a headless or server bridge, use `cycles`. If a preview fails with
an EGL/OpenGL error, switch to cycles and continue.

## 4. Simulate, then read the results

- Use `simulate_dc` when nothing changes over time.
- Use `simulate_transient(duration, events=[...])` whenever something happens: a switch closing
  (`{"time": 1, "component": "S1", "closed": true}`), a potentiometer turning
  (`{"param": "position", "value": 0.2}`), a capacitor charging, or an AC source.
- Close switches with events rather than starting them closed, so the viewer sees cause and effect.
- Read the summary. Check that currents and voltages make sense for the story, and act on `warnings` (burnt
  LED, short circuit). If a warning is the point of the lesson (the short_circuit example), feature it.
  Otherwise fix the values.
- The simulation must be re-run after any circuit change. Animations always use the latest result.

## 5. Animate: time is the core design problem

All tool times are **video seconds**. A transient result is stretched over the `start`–`end` window you give
`animate_circuit`: a 3 s simulation animated over 12 s of video plays at 4× slow motion. An event at simulated
t means video time `start + t × (end − start) / duration`. Place highlights and callouts using that formula, or
they'll fire before or after the moment they describe.

Recommended order:
1. `build_up_sequence(start)` returns `end_time`. Start the physics after it. The intro takes about
   `parts × component_interval + wires × 0.3 s`, so an 8-part, 10-wire circuit needs about 8.5 s at the
   defaults. For bigger circuits or short videos, pass smaller `component_interval` (0.25–0.35) and
   `wire_duration` (0.3), or reveal groups with `animate_visibility(..., stagger=...)`.
2. `animate_circuit(start=end_time, end=...)`. Charges stay hidden until `start`, then flow. Re-running replaces
   the previous flow.
3. Optional layers: `show_voltage_colors` (voltage drops), `add_current_arrows` (direction), `mode="both"`
   (electron vs conventional lesson).
4. If currents differ by orders of magnitude (transistor base vs collector, short circuit), use
   `scaling="sqrt"` or `"log"`. To compare two circuits fairly across scenes, pass the same
   `reference_current`.

## 6. Annotate

- `add_title`: screen-pinned card. Keep titles ≤ 6 words and subtitles ≤ 10.
- `add_callout(text, target)`: a leader line to a part. Keep text short. Default size 0.4 reads well in wide
  shots; use 0.25–0.3 when the camera is close.
- `add_readout(component, quantity)`: live value. With `hud=True`, `size` is a **fraction of screen height**
  (0.04–0.06), not 3D units, and `position` is [x, y] in −1..1.
- `add_label(..., hud=True)`: same sizing rule.
- `add_plot(signals)` (transient only): the graph draws in sync with the animation. Mixed units (V and A) are
  normalised automatically. Place it behind the circuit (`position=[x, y_back, z]`) or flat
  (`rotation=[0,0,0]`), or pin it to the screen with `hud=True`.
- `highlight(targets, time)`: point attention at a part just before the narration names it.
- `add_wire_closeup(wire=...)`: microscopic drift. Pair it with `focus_on(<closeup name>, distance≈8–10)`.

## 7. Camera

- `frame_circuit(view)` (front, iso, top, top_front, left, right, or [azimuth, elevation]) fits the circuit.
  Pass `include_annotations=True` when plots or callouts must stay in shot.
- Give each beat one camera idea: `frame_circuit(..., time=t, transition=1.5)`, `focus_on(part, time=t)`,
  `orbit_camera`, `camera_path`.
- Leave about 0.5 s of stillness after a move before revealing the next thing, so the viewer can settle.
- Close-ups can push callouts and plots out of frame. Re-check with preview.

## 8. Look at your work, every time

Call `preview(time=t)` at every beat's key moment before rendering. Previews are cheap, and re-renders are not.
Check:
- Is the subject in frame and large enough? Are the labels and callouts readable, not cut off or overlapping?
- At that moment, is the right thing happening (switch closed, LED lit, plot drawn up to the marker)?
- Does anything show up too early (text visible before its beat)?

Fix and preview again. If you have shell access on the machine running Blender,
`scripts/contact_sheet.py` renders several times into one image so you can review them in a single view.

## 9. Deliver

- Draft render first: `render_animation(path, resolution_percentage=50, samples=16)` for a fast check. Then render
  the final.
- Also `save_blend` next to the video, so the user can tweak it by hand in Blender.
- Hand back the video path, the .blend path, the narration script, and a one-paragraph recap of the beats.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Electrons don't move | Current ≈ 0: check the switch state and events; run the simulation again after edits |
| Everything in the flow moves at max speed | One huge current (a short) dominates; use `scaling="log"` |
| LED never lights | Reversed (connect `anode` toward +), or the resistor is too big; check `simulate_dc` |
| Text appears too early | Give `start`/`time` to annotations; for readouts, use `start` |
| Wires cross components | Add `via` waypoints (see `references/layouts.md`) |
| "unknown parameter" error | Call `list_blender_commands` for exact signatures |
| Something the tools can't do | `execute_blender_python` (bpy available); keep it small and explain what you did |

`references/tool-cheatsheet.md` lists every tool with the parameters you'll use most.
