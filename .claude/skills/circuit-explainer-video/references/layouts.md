# Circuit layout recipes

Read this when building a circuit that no `build_example` covers. Each recipe below has been checked: it
simulates correctly, and its automatic wire routes don't run through other parts.

## Conventions

- The circuit sits on the XY plane. +X is right, +Y is away from the default camera ("up" on screen in a front
  or top view).
- Two-terminal parts are 2 units long, with terminals at local x = −1 (`a`, `-`, `anode`, `+` for meters) and
  x = +1 (`b`, `+` for sources, `cathode`).
- `rotation` is degrees about Z:
  - `0`: horizontal, first terminal on the left
  - `90`: vertical, second terminal on top. A source at 90° has **+ on top**.
  - `-90`: vertical, first terminal on top. An LED at −90° has **anode on top**; a resistor has `a` on top.
  - `180`: horizontal, reversed. Handy for the bottom rail of a loop, where current flows right to left.
- npn: `b` at local (−1, 0), `c` at (0, +1), `e` at (0, −1). pnp: `c` at (0, −1), `e` at (0, +1).
  potentiometer: `w` (wiper) at (0, +1).
- Space parts about 3 units apart. Anything closer crowds the labels; much further apart wastes the frame.
- Auto routing makes an L-shape and leaves a terminal along the part's own axis first. When an L would clip a
  part, give `via` waypoints: the wire goes straight to each waypoint in order.
- Several wires can share a terminal (a solder dot is drawn automatically). A `junction` part gives a named
  branch point, which reads better in parallel circuits and makes its current easy to highlight.

## A. Series loop (4 slots)

```
         top (3,2) rot 0
  src  ┌───────────────┐
 (0,0) │               │ right (6,0) rot -90
 rot90 │               │
       └───────────────┘
         bottom (3,-2) rot 180
```
```json
{"components": [
  {"type": "battery",  "id": "B1",   "position": [0, 0],  "rotation": 90,  "voltage": 9},
  {"type": "resistor", "id": "R1",   "position": [3, 2],  "rotation": 0,   "resistance": 330},
  {"type": "led",      "id": "LED1", "position": [6, 0],  "rotation": -90, "color": "red"},
  {"type": "switch",   "id": "S1",   "position": [3, -2], "rotation": 180}
],
 "connections": [["B1.+", "R1.a"], ["R1.b", "LED1.anode"], ["LED1.cathode", "S1.a"], ["S1.b", "B1.-"]]}
```
For more parts in series, extend the top rail at x = 3, 6, 9 … and move the right-hand part out to x = last + 3.

## B. Parallel branches (3 branches)

```json
{"components": [
  {"type": "battery",  "id": "B1", "position": [0, 0],  "rotation": 90, "voltage": 6},
  {"type": "junction", "id": "JT1", "position": [3, 2]},  {"type": "junction", "id": "JT2", "position": [6, 2]},
  {"type": "junction", "id": "JB1", "position": [3, -2]}, {"type": "junction", "id": "JB2", "position": [6, -2]},
  {"type": "bulb", "id": "L1", "position": [3, 0], "rotation": -90},
  {"type": "bulb", "id": "L2", "position": [6, 0], "rotation": -90},
  {"type": "bulb", "id": "L3", "position": [9, 0], "rotation": -90}
],
 "connections": [["B1.+", "JT1.n"], ["JT1.n", "JT2.n"], ["JT1.n", "L1.a"], ["JT2.n", "L2.a"], ["JT2.n", "L3.a"],
                 ["L1.b", "JB1.n"], ["L2.b", "JB2.n"], ["L3.b", "JB2.n"], ["JB2.n", "JB1.n"], ["JB1.n", "B1.-"]]}
```
The wire between junctions carries the sum of the branch currents. Pair this with `add_current_arrows` or a
`highlight` on `JT1` to show "current splits here".

## C. Vertical stack with a meter (voltage divider)

```json
{"components": [
  {"type": "battery",   "id": "B1",  "position": [0, 0],    "rotation": 90,  "voltage": 9},
  {"type": "resistor",  "id": "R1",  "position": [4, 1.5],  "rotation": -90, "resistance": 1000},
  {"type": "resistor",  "id": "R2",  "position": [4, -1.5], "rotation": -90, "resistance": 2000},
  {"type": "voltmeter", "id": "VM1", "position": [7, -1.5], "rotation": -90}
],
 "connections": [["B1.+", "R1.a"], ["R1.b", "R2.a"], ["R2.a", "VM1.+"], ["VM1.-", "R2.b"],
                 {"from": "R2.b", "to": "B1.-", "via": [[4, -3], [0, -3]]}]}
```
The `via` is needed. Without it, the return wire from `R2.b` would run back up through R2.

## D. Measurement bench (ammeter in series, voltmeter in parallel)

```json
{"components": [
  {"type": "dc_source", "id": "PSU1", "position": [0, 0],  "rotation": 90, "voltage": 6},
  {"type": "ammeter",   "id": "AM1",  "position": [3, 2]},
  {"type": "resistor",  "id": "R1",   "position": [7, 0],  "rotation": -90, "resistance": 100},
  {"type": "voltmeter", "id": "VM1",  "position": [10, 0], "rotation": -90}
],
 "connections": [["PSU1.+", "AM1.+"], ["AM1.-", "R1.a"], ["R1.b", "PSU1.-"], ["VM1.+", "R1.a"], ["VM1.-", "R1.b"]]}
```

## E. Transistor switch (low-side NPN)

Use `build_example("transistor_switch")`. It places a push button → 10 kΩ → base, an LED + 330 Ω from the +9 V
rail to the collector, and the emitter to battery −. Close and reopen the button with transient events.

## F. Two circuits side by side (comparisons)

Call `build_example(name, replace=False, origin=[16, 0])`, or offset your own coordinates by +16 in x. Both
circuits share one simulation (islands are solved independently). Animate both together with one
`reference_current`, so the speeds are directly comparable, then `frame_circuit(targets=[...])` each one in
turn.

## Value cheat sheet (to hit a target story)

| Want | Values |
| --- | --- |
| Red LED at ~20 mA from 9 V | 330 Ω (red LED ≈ 1.9–2.0 V) |
| Blue/white LED from 9 V | 270–300 Ω (≈ 3 V drop) |
| RC time constant 1 s | 1 kΩ + 1000 µF (use `"1m"` F); simulate 5–6 s |
| Visible AC sloshing | ac_source 1 Hz, 5 V; simulate 2–3 s; animate over ≥ 8 s |
| Bulb bright at 6 V | default bulb (6 V 3 W = 12 Ω) |
| Short circuit drama | a wire straight across the battery, plus a 2 A fuse (`short_circuit` example) |
