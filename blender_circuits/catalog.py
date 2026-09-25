"""Component catalog: terminals, default parameters and descriptions.

This module is pure Python (no ``bpy``) so that the circuit model and the
simulator can be unit-tested outside Blender.

Coordinate conventions
----------------------
Every component lives in its own local frame on the XY plane.  Two-terminal
parts are 2 units long with terminals at x = -1 and x = +1, so placing parts on
an integer grid lines everything up nicely.  ``rotation`` (degrees, about Z)
and ``position`` place the local frame in the world.

The *first* terminal listed in ``order`` is where positive (conventional)
current enters the component; the component's reported current is the current
flowing internally from ``order[0]`` to ``order[1]``.  For sources this means a
positive current while the source is delivering power.
"""

import math

TWO_TERMINAL = {"a": (-1.0, 0.0, 0.0), "b": (1.0, 0.0, 0.0)}
SOURCE_TERMINALS = {"-": (-1.0, 0.0, 0.0), "+": (1.0, 0.0, 0.0)}
SOURCE_ALIASES = {"neg": "-", "negative": "-", "minus": "-", "pos": "+", "positive": "+", "plus": "+",
                  "a": "-", "b": "+"}
TWO_ALIASES = {"1": "a", "2": "b", "left": "a", "right": "b", "in": "a", "out": "b"}

COMPONENTS = {
    "resistor": {
        "terminals": TWO_TERMINAL, "order": ["a", "b"], "aliases": TWO_ALIASES,
        "params": {"resistance": 1000.0},
        "description": "Fixed resistor. Realistic model shows colour bands computed from the value.",
    },
    "potentiometer": {
        "terminals": {"a": (-1.0, 0.0, 0.0), "b": (1.0, 0.0, 0.0), "w": (0.0, 1.0, 0.0)},
        "order": ["a", "b", "w"], "aliases": {"wiper": "w", "left": "a", "right": "b"},
        "params": {"resistance": 10000.0, "position": 0.5},
        "description": "Variable resistor. 'position' (0..1) moves the wiper from a to b.",
    },
    "battery": {
        "terminals": SOURCE_TERMINALS, "order": ["-", "+"], "aliases": SOURCE_ALIASES,
        "params": {"voltage": 9.0, "internal_resistance": 0.05},
        "description": "DC battery/cell. Current is positive while the battery is discharging.",
    },
    "dc_source": {
        "terminals": SOURCE_TERMINALS, "order": ["-", "+"], "aliases": SOURCE_ALIASES,
        "params": {"voltage": 5.0, "internal_resistance": 0.001},
        "description": "Ideal-ish bench DC power supply.",
    },
    "ac_source": {
        "terminals": SOURCE_TERMINALS, "order": ["-", "+"], "aliases": SOURCE_ALIASES,
        "params": {"amplitude": 5.0, "frequency": 1.0, "phase": 0.0, "offset": 0.0, "internal_resistance": 0.001},
        "description": "Sinusoidal voltage source: offset + amplitude*sin(2*pi*f*t + phase_deg). Use transient simulation.",
    },
    "current_source": {
        "terminals": SOURCE_TERMINALS, "order": ["-", "+"], "aliases": SOURCE_ALIASES,
        "params": {"current": 0.01},
        "description": "Ideal current source pushing 'current' amps out of its + terminal.",
    },
    "capacitor": {
        "terminals": TWO_TERMINAL, "order": ["a", "b"], "aliases": TWO_ALIASES,
        "params": {"capacitance": 100e-6, "initial_voltage": 0.0},
        "description": "Capacitor (open circuit in DC, charges/discharges in transient simulation). "
                       "initial_voltage is V(a)-V(b) at t=0.",
    },
    "inductor": {
        "terminals": TWO_TERMINAL, "order": ["a", "b"], "aliases": TWO_ALIASES,
        "params": {"inductance": 0.1, "initial_current": 0.0, "series_resistance": 0.01},
        "description": "Inductor (short in DC, resists changes in current in transient simulation).",
    },
    "diode": {
        "terminals": {"anode": (-1.0, 0.0, 0.0), "cathode": (1.0, 0.0, 0.0)}, "order": ["anode", "cathode"],
        "aliases": {"a": "anode", "k": "cathode", "c": "cathode", "+": "anode", "-": "cathode"},
        "params": {"forward_voltage": 0.7},
        "description": "Silicon diode (forward_voltage measured at 10 mA). Current flows anode -> cathode.",
    },
    "led": {
        "terminals": {"anode": (-1.0, 0.0, 0.0), "cathode": (1.0, 0.0, 0.0)}, "order": ["anode", "cathode"],
        "aliases": {"a": "anode", "k": "cathode", "c": "cathode", "+": "anode", "-": "cathode"},
        "params": {"color": "red", "forward_voltage": None, "max_current": 0.02},
        "description": "Light emitting diode. Glows in proportion to current. color: red, green, blue, yellow, "
                       "white, orange, purple or [r,g,b]. forward_voltage defaults by colour (at 20 mA).",
    },
    "bulb": {
        "terminals": TWO_TERMINAL, "order": ["a", "b"], "aliases": TWO_ALIASES,
        "params": {"rated_voltage": 6.0, "rated_power": 3.0, "resistance": None},
        "description": "Incandescent bulb modelled as a resistor (R = V^2/P unless resistance given). "
                       "Brightness follows power.",
    },
    "switch": {
        "terminals": TWO_TERMINAL, "order": ["a", "b"], "aliases": TWO_ALIASES,
        "params": {"closed": False},
        "description": "SPST knife/toggle switch. Toggle with set_switch or transient events.",
    },
    "push_button": {
        "terminals": TWO_TERMINAL, "order": ["a", "b"], "aliases": TWO_ALIASES,
        "params": {"closed": False},
        "description": "Momentary push button (same electrical behaviour as a switch).",
    },
    "ammeter": {
        "terminals": {"+": (-1.0, 0.0, 0.0), "-": (1.0, 0.0, 0.0)}, "order": ["+", "-"],
        "aliases": {"a": "+", "b": "-", "pos": "+", "neg": "-"},
        "params": {"resistance": 0.001},
        "description": "Ammeter (place in series). Displays the current flowing + -> -.",
    },
    "voltmeter": {
        "terminals": {"+": (-1.0, 0.0, 0.0), "-": (1.0, 0.0, 0.0)}, "order": ["+", "-"],
        "aliases": {"a": "+", "b": "-", "pos": "+", "neg": "-"},
        "params": {"resistance": 10e6},
        "description": "Voltmeter (place in parallel). Displays V(+) - V(-).",
    },
    "motor": {
        "terminals": TWO_TERMINAL, "order": ["a", "b"], "aliases": TWO_ALIASES,
        "params": {"resistance": 10.0, "rpm_per_amp": 600.0},
        "description": "DC motor modelled as its winding resistance. Shaft spins in proportion to current.",
    },
    "speaker": {
        "terminals": TWO_TERMINAL, "order": ["a", "b"], "aliases": TWO_ALIASES,
        "params": {"resistance": 8.0},
        "description": "Speaker/buzzer modelled as a resistor; cone vibrates with current.",
    },
    "fuse": {
        "terminals": TWO_TERMINAL, "order": ["a", "b"], "aliases": TWO_ALIASES,
        "params": {"rating": 1.0, "resistance": 0.01},
        "description": "Fuse. Reported as blown in simulation results when |I| exceeds rating.",
    },
    "npn": {
        "terminals": {"b": (-1.0, 0.0, 0.0), "c": (0.0, 1.0, 0.0), "e": (0.0, -1.0, 0.0)},
        "order": ["c", "e", "b"], "aliases": {"base": "b", "collector": "c", "emitter": "e"},
        "params": {"beta": 100.0},
        "description": "NPN bipolar transistor (Ebers-Moll). Reported current is collector current.",
    },
    "pnp": {
        "terminals": {"b": (-1.0, 0.0, 0.0), "c": (0.0, -1.0, 0.0), "e": (0.0, 1.0, 0.0)},
        "order": ["e", "c", "b"], "aliases": {"base": "b", "collector": "c", "emitter": "e"},
        "params": {"beta": 100.0},
        "description": "PNP bipolar transistor (Ebers-Moll). Reported current is emitter current.",
    },
    "ground": {
        "terminals": {"gnd": (0.0, 0.0, 0.0)}, "order": ["gnd"],
        "aliases": {"g": "gnd", "0": "gnd", "a": "gnd"},
        "params": {},
        "description": "Ground reference (0 V).",
    },
    "junction": {
        "terminals": {"n": (0.0, 0.0, 0.0)}, "order": ["n"],
        "aliases": {"a": "n", "node": "n"},
        "params": {},
        "description": "Wire junction dot. Connect several wires to 'J1.n' to branch a circuit.",
    },
    "chip": {
        "terminals": None, "order": None, "aliases": {},
        "params": {"pins": 8, "text": "IC"},
        "description": "Generic DIP integrated circuit / block (visual only, not simulated). "
                       "Pins p1..pN numbered DIP-style (left side top->bottom, right side bottom->top).",
    },
}

LED_COLORS = {
    "red": ((1.0, 0.05, 0.02), 1.9),
    "orange": ((1.0, 0.35, 0.0), 2.0),
    "yellow": ((1.0, 0.8, 0.0), 2.1),
    "green": ((0.05, 1.0, 0.1), 2.2),
    "blue": ((0.05, 0.25, 1.0), 3.0),
    "white": ((1.0, 1.0, 1.0), 3.1),
    "purple": ((0.6, 0.1, 1.0), 3.2),
    "uv": ((0.45, 0.0, 1.0), 3.3),
}

UNIT_OF_PARAM = {
    "resistance": "Ω", "voltage": "V", "capacitance": "F", "inductance": "H", "current": "A",
    "amplitude": "V", "frequency": "Hz",
}


def canonical_type(ctype):
    t = str(ctype).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "r": "resistor", "res": "resistor", "pot": "potentiometer", "variable_resistor": "potentiometer",
        "cell": "battery", "power_supply": "dc_source", "voltage_source": "dc_source", "vsource": "dc_source",
        "ac": "ac_source", "isource": "current_source", "c": "capacitor", "cap": "capacitor",
        "l": "inductor", "coil": "inductor", "d": "diode", "lamp": "bulb", "light_bulb": "bulb",
        "button": "push_button", "pushbutton": "push_button", "gnd": "ground", "node": "junction",
        "ic": "chip", "block": "chip", "transistor": "npn", "buzzer": "speaker", "q": "npn",
    }
    t = aliases.get(t, t)
    if t not in COMPONENTS:
        raise ValueError("Unknown component type '%s'. Known: %s" % (ctype, ", ".join(sorted(COMPONENTS))))
    return t


def chip_terminals(pins):
    pins = max(2, int(pins) + (int(pins) % 2))
    half = pins // 2
    height = (half - 1) * 0.5
    terms = {}
    for i in range(half):
        terms["p%d" % (i + 1)] = (-1.0, height / 2 - i * 0.5, 0.0)
        terms["p%d" % (pins - i)] = (1.0, height / 2 - i * 0.5, 0.0)
    order = ["p%d" % (i + 1) for i in range(pins)]
    return terms, order


def terminals_of(ctype, params=None):
    """Return (terminals dict, order list) for a component type."""
    ctype = canonical_type(ctype)
    spec = COMPONENTS[ctype]
    if ctype == "chip":
        return chip_terminals((params or {}).get("pins", 8))
    return dict(spec["terminals"]), list(spec["order"])


def resolve_terminal(ctype, name, params=None):
    terms, order = terminals_of(ctype, params)
    key = str(name)
    if key in terms:
        return key
    low = key.lower()
    if low in terms:
        return low
    aliases = COMPONENTS[canonical_type(ctype)]["aliases"]
    if low in aliases:
        return aliases[low]
    if low.isdigit():
        idx = int(low) - 1
        if 0 <= idx < len(order):
            return order[idx]
    raise ValueError("Component type '%s' has no terminal '%s' (terminals: %s)" % (ctype, name, ", ".join(order)))


def default_params(ctype):
    return dict(COMPONENTS[canonical_type(ctype)]["params"])


def led_color(color):
    if isinstance(color, (list, tuple)):
        return tuple(float(c) for c in color[:3]), 2.0
    return LED_COLORS.get(str(color).lower(), LED_COLORS["red"])


def rotate_z(vec, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    x, y, z = vec
    return (x * c - y * s, x * s + y * c, z)


# ---------------------------------------------------------------------------
# Engineering number formatting / parsing
# ---------------------------------------------------------------------------
_PREFIXES = [(1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"),
             (1e-9, "n"), (1e-12, "p")]
_PARSE_PREFIX = {"T": 1e12, "G": 1e9, "M": 1e6, "meg": 1e6, "k": 1e3, "K": 1e3, "m": 1e-3, "u": 1e-6,
                 "µ": 1e-6, "μ": 1e-6, "n": 1e-9, "p": 1e-12}


def format_si(value, unit="", digits=3):
    if value is None:
        return "-"
    v = float(value)
    if abs(v) < 1e-13:
        return "0 %s" % unit if unit else "0"
    for scale, prefix in _PREFIXES:
        if abs(v) >= scale * 0.9995:
            num = v / scale
            text = ("%." + str(digits) + "g") % num
            return "%s %s%s" % (text, prefix, unit) if (prefix or unit) else text
    scale, prefix = _PREFIXES[-1]
    return ("%." + str(digits) + "g %s%s") % (v / scale, prefix, unit)


def parse_value(value):
    """Accept numbers or strings like '4.7k', '100uF', '2.2 MΩ', '10mA', '1meg'."""
    if value is None or isinstance(value, (int, float, bool)):
        return value
    s = str(value).strip().replace("Ω", "").replace("ohm", "").replace("Ohm", "")
    for unit in ("F", "H", "V", "A", "Hz", "W", "s"):
        if s.endswith(unit) and len(s) > len(unit):
            s = s[: -len(unit)]
            break
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        pass
    if s.lower().endswith("meg"):
        return float(s[:-3]) * 1e6
    for suffix, mult in _PARSE_PREFIX.items():
        if s.endswith(suffix):
            try:
                return float(s[: -len(suffix)]) * mult
            except ValueError:
                continue
    raise ValueError("Cannot parse value '%s'" % value)


def value_text(ctype, params):
    """Short human readable value label for a component."""
    ctype = canonical_type(ctype)
    p = params
    if ctype in ("resistor", "potentiometer", "motor", "speaker"):
        return format_si(p.get("resistance"), "Ω")
    if ctype in ("battery", "dc_source"):
        return format_si(p.get("voltage"), "V")
    if ctype == "ac_source":
        return "%s ~ %s" % (format_si(p.get("amplitude"), "V"), format_si(p.get("frequency"), "Hz"))
    if ctype == "current_source":
        return format_si(p.get("current"), "A")
    if ctype == "capacitor":
        return format_si(p.get("capacitance"), "F")
    if ctype == "inductor":
        return format_si(p.get("inductance"), "H")
    if ctype == "bulb":
        return "%s %s" % (format_si(p.get("rated_voltage"), "V"), format_si(p.get("rated_power"), "W"))
    if ctype == "fuse":
        return format_si(p.get("rating"), "A")
    if ctype == "led":
        c = p.get("color")
        return c if isinstance(c, str) else "LED"
    if ctype == "chip":
        return str(p.get("text", ""))
    return ""


def describe_catalog():
    out = {}
    for name, spec in COMPONENTS.items():
        terms, order = terminals_of(name, spec["params"])
        out[name] = {
            "description": spec["description"],
            "terminals": order,
            "terminal_positions": {k: list(terms[k]) for k in order},
            "params": spec["params"],
        }
    return out
