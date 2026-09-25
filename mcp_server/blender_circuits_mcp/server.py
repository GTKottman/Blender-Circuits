"""MCP server exposing Circuit Lab (Blender) to AI assistants.

Every tool forwards to the Blender add-on over a local socket.  Works with the
MCP Python SDK 1.x (FastMCP) and 2.x (MCPServer).
"""

import base64
from typing import Any, Literal, Optional, Union

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import Image
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp import Image
    from mcp.server.fastmcp.exceptions import ToolError

from .connection import BlenderError, get_connection

Point = list[float]
Target = Union[str, list[float]]

GUIDE = """\
Circuit Lab turns Blender into a 3D electronics classroom. You design a circuit, simulate it with the built-in
SPICE-like solver, then animate the physics (moving electrons, glowing LEDs, charging capacitors, meter readings)
and add camera moves, titles, callouts and graphs to produce an explainer video.

COORDINATES: the circuit lies on the XY plane (Z is up, the camera looks from -Y towards +Y by default).
Two-terminal parts are 2 units long with terminals at local x=-1 and x=+1, so place parts on an integer grid,
typically 3-4 units apart. rotation is in degrees about Z (90 = vertical with terminal 'b'/'+' on top,
-90 = vertical with terminal 'a'/'anode' on top).

TERMINALS are referenced as "<id>.<terminal>": resistor/bulb/switch/capacitor... 'a','b'; battery/sources '+','-';
diode/led 'anode','cathode'; npn/pnp 'b','c','e'; potentiometer 'a','b','w'; ground 'gnd'; junction 'n';
chip 'p1'..'pN'. Use a junction component to branch wires (parallel circuits). Several wires may also share
one terminal.

TIME: every time parameter is in seconds of video. Transient simulations run in *simulated* seconds; the
animation maps them onto video time (time_scale = video seconds per simulated second, chosen automatically
from start/end).

RECOMMENDED WORKFLOW
 1. new_circuit (or build_example to start from a ready-made teaching circuit)
 2. add_components / connect_many (check the returned terminal positions)
 3. setup_scene (theme, engine, resolution, duration) - also sizes the board and creates the camera
 4. simulate_dc  or  simulate_transient(duration, events=[{time, component, closed}])
 5. animate_circuit(start, end)  (+ show_voltage_colors / add_current_arrows)
 6. storytelling: build_up_sequence, add_title, add_callout, add_readout, add_plot, highlight, add_wire_closeup
 7. camera: frame_circuit, focus_on, camera_path, orbit_camera
 8. preview(time=...) to LOOK at frames and fix composition; then render_animation(filepath)

TIPS: run the simulation again after changing the circuit, then re-run animate_circuit (it replaces the old
particles). Use scaling='sqrt' or 'log' when currents differ by orders of magnitude. Electrons move opposite
to conventional current (mode='conventional' shows positive charges, mode='both' shows both).
The 'schematic' style draws standard circuit symbols; 'realistic' draws 3D parts. EEVEE renders fast
but needs a GPU; use engine='cycles' on headless servers.
"""

mcp = _Server("blender-circuits", instructions=GUIDE)


def _call(command, **params):
    clean = {k: v for k, v in params.items() if v is not None}
    try:
        return get_connection().send(command, clean)
    except BlenderError as exc:  # surface Blender's message to the AI instead of a generic failure
        raise ToolError(str(exc)) from exc


# ============================================================ basics
@mcp.tool()
def get_scene_info() -> dict:
    """Summary of the current circuit (components with terminal positions, wires), available simulation
    results, timeline, camera, annotations and render settings. Call this first to see what exists."""
    return _call("get_scene_info")


@mcp.tool()
def list_component_types() -> dict:
    """Catalog of every component type: description, terminal names/positions and default parameters."""
    return _call("list_component_types")


@mcp.tool()
def list_examples() -> dict:
    """Ready-made teaching circuits that build_example can create (LED loop, series/parallel bulbs, voltage
    divider, RC charging, transistor switch, short circuit, Ohm's law bench, motor, AC RC, dimmer)."""
    return _call("list_examples")


@mcp.tool()
def build_example(name: str, origin: Optional[Point] = None, style: Optional[Literal["realistic", "schematic"]] = None,
                  replace: bool = True) -> dict:
    """Build an example circuit. Returns the component ids by role and suggested next steps.
    replace=False adds it next to an existing circuit (use origin=[x, y] to offset it)."""
    return _call("build_example", name=name, origin=origin, style=style, replace=replace)


# ============================================================ circuit design
@mcp.tool()
def new_circuit(style: Literal["realistic", "schematic"] = "realistic",
                wire_look: Literal["copper", "insulated", "glass"] = "copper", show_labels: bool = True,
                show_values: bool = True, clear_annotations: bool = True) -> dict:
    """Start a fresh, empty circuit. style 'realistic' = 3D parts, 'schematic' = standard symbols.
    wire_look 'glass' makes see-through tubes (great for showing electrons inside)."""
    return _call("new_circuit", style=style, wire_look=wire_look, show_labels=show_labels, show_values=show_values,
                 clear_annotations=clear_annotations)


@mcp.tool()
def set_circuit_settings(style: Optional[Literal["realistic", "schematic"]] = None,
                         wire_look: Optional[Literal["copper", "insulated", "glass"]] = None,
                         show_labels: Optional[bool] = None, show_values: Optional[bool] = None,
                         wire_radius: Optional[float] = None) -> dict:
    """Change global look (e.g. switch the whole circuit between realistic and schematic) and rebuild."""
    return _call("set_circuit_settings", style=style, wire_look=wire_look, show_labels=show_labels,
                 show_values=show_values, wire_radius=wire_radius)


@mcp.tool()
def add_component(type: str, position: Point, rotation: float = 0.0, id: Optional[str] = None,
                  params: Optional[dict[str, Any]] = None, label: Optional[str] = None,
                  style: Optional[Literal["realistic", "schematic"]] = None, show_value: Optional[bool] = None) -> dict:
    """Add one component at [x, y] (grid units). type: resistor, potentiometer, battery, dc_source, ac_source,
    current_source, capacitor, inductor, diode, led, bulb, switch, push_button, ammeter, voltmeter, motor, speaker,
    fuse, npn, pnp, ground, junction, chip.
    params examples: {"resistance": "4.7k"}, {"voltage": 9}, {"capacitance": "100u"}, {"color": "green"},
    {"closed": true}, {"look": "electrolytic"}. Returns id and world terminal positions."""
    return _call("add_component", type=type, position=position, rotation=rotation, id=id, params=params, label=label,
                 style=style, show_value=show_value)


@mcp.tool()
def add_components(components: list[dict[str, Any]]) -> dict:
    """Add several components at once. Each item: {"type", "position": [x, y], "rotation", "id", "params",
    "label"} (shorthand params such as "resistance": 220 are also accepted)."""
    return _call("add_components", components=components)


@mcp.tool()
def update_component(id: str, params: Optional[dict[str, Any]] = None, position: Optional[Point] = None,
                     rotation: Optional[float] = None, label: Optional[str] = None,
                     style: Optional[Literal["realistic", "schematic"]] = None) -> dict:
    """Change a component (value, position, rotation, label, style). Attached wires are re-routed."""
    return _call("update_component", id=id, params=params, position=position, rotation=rotation, label=label,
                 style=style)


@mcp.tool()
def remove_component(id: str) -> dict:
    """Delete a component and the wires attached to it."""
    return _call("remove_component", id=id)


@mcp.tool()
def connect(a: str, b: str, via: Optional[list[Point]] = None,
            route: Literal["auto", "hv", "vh", "direct"] = "auto", color: Optional[str] = None,
            id: Optional[str] = None) -> dict:
    """Draw a wire between two terminals, e.g. a="B1.+", b="R1.a". Wires are routed with right angles;
    route 'hv' goes horizontal first, 'vh' vertical first; via=[[x, y], ...] adds waypoints to steer around parts."""
    return _call("connect", a=a, b=b, via=via, route=route, color=color, id=id)


@mcp.tool()
def connect_many(connections: list[Any], route: Literal["auto", "hv", "vh", "direct"] = "auto") -> dict:
    """Several wires at once: [["B1.+", "R1.a"], ["R1.b", "LED1.anode"], {"from": "LED1.cathode", "to": "B1.-",
    "via": [[6, -2]]}]."""
    return _call("connect_many", connections=connections, route=route)


@mcp.tool()
def remove_wire(id: str) -> dict:
    """Delete a wire."""
    return _call("remove_wire", id=id)


@mcp.tool()
def get_circuit() -> dict:
    """Full circuit model with parameters, wires and terminal world positions."""
    return _call("get_circuit")


@mcp.tool()
def set_switch(id: str, closed: bool = True, time: Optional[float] = None, duration: float = 0.3) -> dict:
    """Open/close a switch or push button. Without time it changes the circuit for simulate_dc; with time it
    only animates the lever at that moment (for physics over time use simulate_transient events)."""
    return _call("set_switch", id=id, closed=closed, time=time, duration=duration)


# ============================================================ simulation
@mcp.tool()
def simulate_dc() -> dict:
    """Solve the steady state: voltage, current and power for every component and wire, LED/bulb brightness,
    meter readings, plus warnings (burnt-out LEDs, short circuits, blown fuses)."""
    return _call("simulate_dc")


@mcp.tool()
def simulate_transient(duration: float, events: Optional[list[dict[str, Any]]] = None, dt: Optional[float] = None,
                       samples: int = 400, start_from_dc: bool = False) -> dict:
    """Simulate over time (in simulated seconds): capacitor charging, inductors, AC sources, switching.
    events: [{"time": 0.5, "component": "S1", "closed": true},
             {"time": 2.0, "component": "RV1", "param": "position", "value": 0.2}].
    Capacitors start at their initial_voltage unless start_from_dc is true."""
    return _call("simulate_transient", duration=duration, events=events, dt=dt, samples=samples,
                 start_from_dc=start_from_dc)


@mcp.tool()
def get_results(source: Literal["auto", "dc", "transient"] = "auto", component: Optional[str] = None,
                max_points: int = 50) -> dict:
    """Numeric simulation data (per component/wire). Transient series are downsampled to max_points."""
    return _call("get_results", source=source, component=component, max_points=max_points)


# ============================================================ animation
@mcp.tool()
def animate_circuit(start: float = 0.0, end: Optional[float] = None,
                    source: Literal["auto", "dc", "transient"] = "auto",
                    mode: Literal["electron", "conventional", "both"] = "electron", time_scale: Optional[float] = None,
                    density: float = 2.5, speed: float = 1.5, scaling: Literal["linear", "sqrt", "log"] = "linear",
                    max_speed: float = 6.0, particle_radius: float = 0.06, include_components: bool = True,
                    show_charge: bool = True, glow_strength: float = 12.0, fade_in: float = 0.0) -> dict:
    """Bring the circuit to life from the latest simulation: charges flow along wires at speed proportional to
    current, LEDs/bulbs glow with current/power, motors spin, meters display live values, switch levers move at
    their events, capacitor plates fill with + and - charges. start/end are video seconds (for transient results
    the whole simulation is stretched between them). Re-running replaces the previous flow animation."""
    return _call("animate_circuit", start=start, end=end, source=source, mode=mode, time_scale=time_scale,
                 density=density, speed=speed, scaling=scaling, max_speed=max_speed, particle_radius=particle_radius,
                 include_components=include_components, show_charge=show_charge, glow_strength=glow_strength,
                 fade_in=fade_in)


@mcp.tool()
def animate_current_flow(start: float = 0.0, end: Optional[float] = None,
                         source: Literal["auto", "dc", "transient"] = "auto",
                         mode: Literal["electron", "conventional", "both"] = "electron", density: float = 2.5,
                         speed: float = 1.5, reference_current: Optional[float] = None,
                         scaling: Literal["linear", "sqrt", "log"] = "linear", max_speed: float = 6.0,
                         particle_radius: float = 0.06, color: Optional[str] = None, include_components: bool = True,
                         time_scale: Optional[float] = None, glow: float = 3.0, fade_in: float = 0.0) -> dict:
    """Only the moving charges (see animate_circuit). reference_current = current that moves at `speed` units/s
    (default: the largest current). Use the same reference_current across scenes to compare circuits fairly."""
    return _call("animate_current_flow", start=start, end=end, source=source, mode=mode, density=density, speed=speed,
                 reference_current=reference_current, scaling=scaling, max_speed=max_speed,
                 particle_radius=particle_radius, color=color, include_components=include_components,
                 time_scale=time_scale, glow=glow, fade_in=fade_in)


@mcp.tool()
def animate_component_effects(start: float = 0.0, end: Optional[float] = None,
                              source: Literal["auto", "dc", "transient"] = "auto", time_scale: Optional[float] = None,
                              glow_strength: float = 12.0, light_power: float = 15.0, show_charge: bool = True) -> dict:
    """Only the component reactions (glow, spin, meters, switches, capacitor charge) - see animate_circuit."""
    return _call("animate_component_effects", start=start, end=end, source=source, time_scale=time_scale,
                 glow_strength=glow_strength, light_power=light_power, show_charge=show_charge)


@mcp.tool()
def add_current_arrows(start: float = 0.0, end: Optional[float] = None,
                       source: Literal["auto", "dc", "transient"] = "auto", size: float = 0.35, color: str = "yellow",
                       time_scale: Optional[float] = None) -> dict:
    """Arrow on every wire pointing in the conventional current direction; its size follows the current."""
    return _call("add_current_arrows", start=start, end=end, source=source, size=size, color=color,
                 time_scale=time_scale)


@mcp.tool()
def show_voltage_colors(start: float = 0.0, end: Optional[float] = None,
                        source: Literal["auto", "dc", "transient"] = "auto",
                        colormap: Literal["thermal", "blue_red", "green"] = "thermal", vmin: Optional[float] = None,
                        vmax: Optional[float] = None, legend: bool = True, legend_position: Optional[Point] = None,
                        time_scale: Optional[float] = None) -> dict:
    """Colour every wire by its voltage (like a heat map: blue = low, red = high) with a legend - great for
    explaining voltage drops across components. Animated for transient results."""
    return _call("show_voltage_colors", start=start, end=end, source=source, colormap=colormap, vmin=vmin, vmax=vmax,
                 legend=legend, legend_position=legend_position, time_scale=time_scale)


@mcp.tool()
def animate_switch(id: str, closed: bool = True, time: float = 0.0, duration: float = 0.3) -> dict:
    """Animate a switch lever/button (visual only)."""
    return _call("animate_switch", id=id, closed=closed, time=time, duration=duration)


@mcp.tool()
def animate_visibility(targets: list[str], action: Literal["appear", "disappear"] = "appear", time: float = 0.0,
                       duration: float = 0.5, style: Literal["fade", "pop", "grow", "drop", "draw", "instant"] = "fade",
                       stagger: float = 0.0) -> dict:
    """Reveal or hide things at a time. targets: component/wire ids, object names, or keywords 'all',
    'components', 'wires', 'labels', 'flow', 'annotations', 'effects'. 'draw' makes wires/curves draw themselves;
    stagger delays each successive target for cascading reveals. Objects are invisible before an 'appear'."""
    return _call("animate_visibility", targets=targets, action=action, time=time, duration=duration, style=style,
                 stagger=stagger)


@mcp.tool()
def build_up_sequence(start: float = 0.0, component_interval: float = 0.6, wire_duration: float = 0.5,
                      style: Literal["pop", "grow", "fade", "drop"] = "pop", order: Optional[list[str]] = None) -> dict:
    """Assemble-the-circuit intro: components appear one by one, then every wire draws itself. Returns end_time
    so you can start the next beat (e.g. animate_circuit(start=end_time))."""
    return _call("build_up_sequence", start=start, component_interval=component_interval,
                 wire_duration=wire_duration, style=style, order=order)


@mcp.tool()
def animate_transform(target: str, time: float = 0.0, duration: float = 1.0, location: Optional[Point] = None,
                      rotation: Optional[Point] = None, scale: Optional[Union[float, Point]] = None,
                      relative: bool = False) -> dict:
    """Smoothly move/rotate (degrees)/scale a component or object - e.g. lift a part up to inspect it
    (relative=True, location=[0, 0, 2]). Wires do not follow."""
    return _call("animate_transform", target=target, time=time, duration=duration, location=location,
                 rotation=rotation, scale=scale, relative=relative)


@mcp.tool()
def highlight(targets: list[str], time: float = 0.0, duration: float = 1.5, color: str = "yellow", pulses: int = 2,
              radius: Optional[float] = None, style: Literal["ring", "ring+bounce"] = "ring") -> dict:
    """Pulsing glowing ring around components (or terminals/points) to direct the viewer's attention."""
    return _call("highlight", targets=targets, time=time, duration=duration, color=color, pulses=pulses,
                 radius=radius, style=style)


@mcp.tool()
def clear_animation(what: Literal["flow", "effects", "keyframes", "camera", "all"] = "flow") -> dict:
    """Remove animation: particles (flow), arrows/halos/charges (effects), keyframes, camera moves, or all."""
    return _call("clear_animation", what=what)


# ============================================================ annotations
@mcp.tool()
def add_label(text: str, position: Optional[Point] = None, target: Optional[str] = None,
              offset: Point = (0, 0.9, 0.2), size: float = 0.35, color: Optional[str] = None,
              align: Literal["LEFT", "CENTER", "RIGHT"] = "CENTER", face_camera: bool = False, hud: bool = False,
              start: Optional[float] = None, end: Optional[float] = None, name: Optional[str] = None,
              rotation: Optional[Point] = None) -> dict:
    """3D text at a position or next to a target (component id / terminal ref). face_camera keeps it readable
    during camera moves. hud=True pins it to the screen (position=[x, y] in -1..1, size = fraction of screen
    height, e.g. 0.05). start/end fade it in/out."""
    return _call("add_label", text=text, position=position, target=target, offset=offset, size=size, color=color,
                 align=align, face_camera=face_camera, hud=hud, start=start, end=end, name=name, rotation=rotation)


@mcp.tool()
def add_callout(text: str, target: str, offset: Point = (1.5, 1.5, 0.8), size: float = 0.4,
                color: Optional[str] = None, line_color: str = "white", start: Optional[float] = None,
                end: Optional[float] = None, face_camera: bool = False) -> dict:
    """Explanation bubble: text with a leader line pointing at a component/terminal (e.g. "Current limited to
    20 mA by R1"). The line draws itself at start."""
    return _call("add_callout", text=text, target=target, offset=offset, size=size, color=color,
                 line_color=line_color, start=start, end=end, face_camera=face_camera)


@mcp.tool()
def add_arrow(start_point: Target, end_point: Target, color: str = "yellow", thickness: float = 0.05,
              time: Optional[float] = None, draw_duration: float = 0.6, end: Optional[float] = None,
              curved: float = 0.0) -> dict:
    """3D arrow between two points or targets (ids / terminal refs / [x, y, z]); draws itself at `time`;
    curved = arc height for a swooping arrow."""
    return _call("add_arrow", start_point=start_point, end_point=end_point, color=color, thickness=thickness,
                 time=time, draw_duration=draw_duration, end=end, curved=curved)


@mcp.tool()
def add_title(title: str, subtitle: Optional[str] = None, time: float = 0.0, duration: float = 3.0,
              position: Union[Literal["center", "top", "bottom", "top_left"], Point] = "center", size: float = 0.09,
              color: Optional[str] = None, background: bool = False) -> dict:
    """Screen-space title card that fades in at `time` and out after `duration` (0 = stays)."""
    return _call("add_title", title=title, subtitle=subtitle, time=time, duration=duration, position=position,
                 size=size, color=color, background=background)


@mcp.tool()
def add_readout(component: str, quantity: str = "current", position: Optional[Point] = None,
                prefix: Optional[str] = None, source: Literal["auto", "dc", "transient"] = "auto", start: float = 0.0,
                end: Optional[float] = None, time_scale: Optional[float] = None, size: float = 0.3,
                color: Optional[str] = None, hud: bool = False, digits: int = 3) -> dict:
    """Live number that updates every frame from the simulation, e.g. "I = 20.3 mA"; fades in at start.
    quantity: current | voltage | power | charge | brightness | rpm | reading (meters).
    hud=True pins it to the screen: position=[x, y] in -1..1 and size = fraction of screen height (e.g. 0.045)."""
    return _call("add_readout", component=component, quantity=quantity, position=position, prefix=prefix,
                 source=source, start=start, end=end, time_scale=time_scale, size=size, color=color, hud=hud,
                 digits=digits)


@mcp.tool()
def add_plot(signals: list[dict[str, Any]], position: Optional[Point] = None, width: float = 6.0, height: float = 3.0,
             start: float = 0.0, end: Optional[float] = None, time_scale: Optional[float] = None,
             title: Optional[str] = None, hud: bool = False, rotation: Point = (90, 0, 0), marker: bool = True) -> dict:
    """Oscilloscope graph that draws itself in sync with the animation (needs simulate_transient).
    signals: [{"component": "C1", "quantity": "voltage", "color": "yellow", "label": "V(C1)"}, ...].
    Default: stands upright behind the circuit; rotation=[0,0,0] lays it flat; hud=True pins it on screen."""
    return _call("add_plot", signals=signals, position=position, width=width, height=height, start=start, end=end,
                 time_scale=time_scale, title=title, hud=hud, rotation=rotation, marker=marker)


@mcp.tool()
def add_wire_closeup(position: Point = (0, -8, 2), length: float = 6.0, radius: float = 1.0,
                     wire: Optional[str] = None, start: float = 0.0, end: Optional[float] = None,
                     electrons: int = 60, drift_speed: float = 0.6, thermal: float = 0.15, labels: bool = True,
                     rotation: Point = (0, 0, 0)) -> dict:
    """Magnified see-through wire showing the copper ion lattice (vibrating) and free electrons that jitter
    randomly while slowly drifting - explains drift velocity. With wire=<id> the drift follows that wire's
    simulated current. Combine with focus_on(<closeup name>) to zoom in."""
    return _call("add_wire_closeup", position=position, length=length, radius=radius, wire=wire, start=start,
                 end=end, electrons=electrons, drift_speed=drift_speed, thermal=thermal, labels=labels,
                 rotation=rotation)


@mcp.tool()
def clear_annotations(kind: Optional[Literal["label", "arrow", "callout", "title", "readout", "plot", "closeup"]] = None) -> dict:
    """Delete all annotations, or only one kind."""
    return _call("clear_annotations", kind=kind)


# ============================================================ scene, camera, render
@mcp.tool()
def setup_scene(theme: Literal["dark", "blueprint", "light", "studio", "workbench"] = "dark",
                engine: Literal["eevee", "cycles", "workbench"] = "eevee", resolution: list[int] = (1920, 1080),
                fps: int = 30, duration: Optional[float] = None,
                board: Optional[Literal["grid", "pcb", "wood", "breadboard", "plain", "none"]] = None, glow: bool = True,
                samples: Optional[int] = None, transparent: bool = False,
                style: Optional[Literal["realistic", "schematic"]] = None,
                wire_look: Optional[Literal["copper", "insulated", "glass"]] = None) -> dict:
    """Make it look good: world colour, 3-point lighting, a board under the circuit, bloom/glow, render engine,
    resolution, fps and video duration (seconds). Call again after the circuit grows to refit the board."""
    return _call("setup_scene", theme=theme, engine=engine, resolution=list(resolution), fps=fps, duration=duration,
                 board=board, glow=glow, samples=samples, transparent=transparent, style=style, wire_look=wire_look)


@mcp.tool()
def set_timeline(duration: Optional[float] = None, fps: Optional[int] = None) -> dict:
    """Set total video length (seconds) and frame rate."""
    return _call("set_timeline", duration=duration, fps=fps)


@mcp.tool()
def frame_circuit(view: Union[Literal["top", "top_front", "front", "iso", "low", "left", "right"], Point] = "front",
                  margin: float = 1.15, time: Optional[float] = None, transition: float = 1.5,
                  lens: Optional[float] = None, targets: Optional[list[str]] = None,
                  include_annotations: bool = False) -> dict:
    """Aim the camera so the whole circuit (or just `targets`) fills the frame. view can be [azimuth, elevation]
    in degrees. With time, the camera glides there, arriving at `time` after `transition` seconds."""
    return _call("frame_circuit", view=view, margin=margin, time=time, transition=transition, lens=lens,
                 targets=targets, include_annotations=include_annotations)


@mcp.tool()
def set_camera(location: Optional[Point] = None, look_at: Optional[Target] = None, lens: Optional[float] = None,
               time: Optional[float] = None, transition: float = 1.0) -> dict:
    """Place the camera explicitly (look_at = point or component id). With time it is keyframed."""
    return _call("set_camera", location=location, look_at=look_at, lens=lens, time=time, transition=transition)


@mcp.tool()
def focus_on(target: str, time: Optional[float] = None, transition: float = 1.0, distance: float = 4.0,
             elevation: float = 40.0, azimuth: float = 0.0, lens: Optional[float] = None) -> dict:
    """Zoom the camera in on a component/terminal/object (animated when time is given)."""
    return _call("focus_on", target=target, time=time, transition=transition, distance=distance,
                 elevation=elevation, azimuth=azimuth, lens=lens)


@mcp.tool()
def camera_path(keys: list[dict[str, Any]], smooth: bool = True) -> dict:
    """Keyframed camera move: [{"time": 0, "location": [0,-15,10], "look_at": [5,0,0]}, {"time": 4,
    "location": [...], "look_at": "R1", "lens": 50}]."""
    return _call("camera_path", keys=keys, smooth=smooth)


@mcp.tool()
def orbit_camera(start: float = 0.0, end: float = 10.0, degrees: float = 360.0, radius: Optional[float] = None,
                 height: Optional[float] = None, center: Optional[Target] = None) -> dict:
    """Circle the camera around the circuit (or a target) between start and end seconds, with easing."""
    return _call("orbit_camera", start=start, end=end, degrees=degrees, radius=radius, height=height, center=center)


@mcp.tool()
def depth_of_field(enabled: bool = True, focus: Optional[str] = None, fstop: float = 2.8) -> dict:
    """Cinematic background blur focused on a component/object."""
    return _call("depth_of_field", enabled=enabled, focus=focus, fstop=fstop)


@mcp.tool()
def preview(time: Optional[float] = None, width: int = 640, samples: int = 8):
    """Render a quick low-resolution frame from the camera at `time` and return it as an image so you can
    check composition, readability and timing before the final render."""
    result = _call("preview", time=time, width=width, samples=samples)
    return Image(data=base64.b64decode(result["image_base64"]), format="png")


@mcp.tool()
def render_still(filepath: str, time: Optional[float] = None, resolution_percentage: Optional[int] = None,
                 samples: Optional[int] = None) -> dict:
    """Render a single full-quality frame to a PNG file."""
    return _call("render_still", filepath=filepath, time=time, resolution_percentage=resolution_percentage,
                 samples=samples)


@mcp.tool()
def render_animation(filepath: str, start: Optional[float] = None, end: Optional[float] = None,
                     file_format: Literal["mp4", "mov", "mkv", "webm", "png"] = "mp4",
                     resolution_percentage: Optional[int] = None, samples: Optional[int] = None) -> dict:
    """Render the video (can take a while). start/end in seconds default to the whole timeline."""
    return _call("render_animation", filepath=filepath, start=start, end=end, file_format=file_format,
                 resolution_percentage=resolution_percentage, samples=samples)


@mcp.tool()
def save_blend(filepath: str) -> dict:
    """Save the Blender project (.blend) so a human can tweak it later."""
    return _call("save_blend", filepath=filepath)


# ============================================================ power tools
@mcp.tool()
def run_batch(commands: list[dict[str, Any]], stop_on_error: bool = True) -> dict:
    """Run many Circuit Lab commands in one round trip: [{"command": "add_component", "params": {...}}, ...].
    Command names/params are those of the tools above (see list_blender_commands)."""
    return _call("batch", commands=commands, stop_on_error=stop_on_error)


@mcp.tool()
def list_blender_commands() -> dict:
    """Every command implemented by the Blender add-on with its full parameter signature."""
    return _call("list_commands")


@mcp.tool()
def execute_blender_python(code: str) -> dict:
    """Escape hatch: run Python inside Blender (bpy is available, plus lab/anim/ann/scene helper modules).
    Set a variable named `result` to return data; printed output is returned too."""
    return _call("execute_python", code=code)


# ============================================================ prompts / resources
@mcp.resource("circuitlab://guide")
def guide() -> str:
    """How to use Circuit Lab (coordinates, terminals, workflow, tips)."""
    return GUIDE


@mcp.prompt()
def explainer_video(topic: str, audience: str = "high-school students", length_seconds: int = 45) -> str:
    """Plan and produce a short explainer video about a circuit topic."""
    return (
        "Create a {length}-second motion-graphics video in Blender that explains '{topic}' to {audience} using the "
        "Circuit Lab tools.\n\n"
        "1. Write a short beat sheet (5-8 beats with start/end seconds and what the viewer should learn).\n"
        "2. Build the circuit (build_example if one fits, otherwise new_circuit + add_components + connect_many).\n"
        "3. setup_scene(duration={length}) and simulate (simulate_transient with switch events if something "
        "changes over time, otherwise simulate_dc; read the warnings).\n"
        "4. Animate each beat: build_up_sequence for the intro, add_title, animate_circuit, highlight / "
        "add_callout for key parts, add_readout or add_plot for numbers, show_voltage_colors for voltage drops, "
        "add_wire_closeup for microscopic views.\n"
        "5. Direct the camera per beat with frame_circuit / focus_on / camera_path.\n"
        "6. preview() several key moments, fix anything unreadable or off-screen, then render_animation."
    ).format(topic=topic, audience=audience, length=length_seconds)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
