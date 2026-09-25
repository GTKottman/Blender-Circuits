"""Ready-made teaching circuits (pure Python, operate on a Circuit model)."""

EXAMPLES = {}


def example(description, next_steps):
    def deco(fn):
        EXAMPLES[fn.__name__] = {"fn": fn, "description": description, "next_steps": next_steps}
        return fn
    return deco


class _Ctx:
    def __init__(self, circ, origin):
        self.c = circ
        self.ox, self.oy = float(origin[0]), float(origin[1])
        self.ids = {}
        self.wires = []

    def add(self, role, ctype, pos, rot=0.0, **params):
        cid = self.c.add_component(ctype, None, (pos[0] + self.ox, pos[1] + self.oy), rot, params)
        self.ids[role] = cid
        return cid

    def wire(self, a, b, via=None, route="auto"):
        ra, ta = a.split(".")
        rb, tb = b.split(".")
        v = [(p[0] + self.ox, p[1] + self.oy) for p in via] if via else None
        self.wires.append(self.c.connect("%s.%s" % (self.ids[ra], ta), "%s.%s" % (self.ids[rb], tb), via=v,
                                         route=route))


@example("Battery, resistor, LED and switch in a loop: the 'hello world' of electronics.",
         ["simulate_transient(duration=3, events=[{time:0.5, component:<switch>, closed:true}])",
          "animate_circuit(start=1, end=10)"])
def led_circuit(x):
    x.add("battery", "battery", (0, 0), 90, voltage=9)
    x.add("resistor", "resistor", (3, 2), 0, resistance=330)
    x.add("led", "led", (6, 0), -90, color="red")
    x.add("switch", "switch", (3, -2), 180, closed=True)
    x.wire("battery.+", "resistor.a")
    x.wire("resistor.b", "led.anode")
    x.wire("led.cathode", "switch.a")
    x.wire("switch.b", "battery.-")


@example("Two bulbs in series share the battery voltage - both glow dimly and the same current flows everywhere.",
         ["simulate_dc()", "animate_circuit()", "add_readout(<bulb>, 'current')"])
def series_bulbs(x):
    x.add("battery", "battery", (0, 0), 90, voltage=6)
    x.add("bulb1", "bulb", (3, 2), 0)
    x.add("bulb2", "bulb", (6, 0), -90)
    x.wire("battery.+", "bulb1.a")
    x.wire("bulb1.b", "bulb2.a")
    x.wire("bulb2.b", "battery.-")


@example("Two bulbs in parallel each get the full voltage - current splits at the junction and recombines.",
         ["simulate_dc()", "animate_circuit()", "add_current_arrows()"])
def parallel_bulbs(x):
    x.add("battery", "battery", (0, 0), 90, voltage=6)
    x.add("j_top", "junction", (3, 2))
    x.add("j_bottom", "junction", (3, -2))
    x.add("bulb1", "bulb", (3, 0), -90)
    x.add("bulb2", "bulb", (6, 0), -90)
    x.wire("battery.+", "j_top.n")
    x.wire("j_top.n", "bulb1.a")
    x.wire("j_top.n", "bulb2.a")
    x.wire("bulb1.b", "j_bottom.n")
    x.wire("bulb2.b", "j_bottom.n")
    x.wire("j_bottom.n", "battery.-")


@example("Voltage divider: two resistors split 9 V in proportion to their resistance; a voltmeter reads the middle.",
         ["simulate_dc()", "show_voltage_colors()", "animate_circuit()"])
def voltage_divider(x):
    x.add("battery", "battery", (0, 0), 90, voltage=9)
    x.add("r_top", "resistor", (4, 1.5), -90, resistance=1000)
    x.add("r_bottom", "resistor", (4, -1.5), -90, resistance=2000)
    x.add("voltmeter", "voltmeter", (7, -1.5), -90)
    x.add("ground", "ground", (-2, -1.5))
    x.wire("battery.+", "r_top.a")
    x.wire("r_top.b", "r_bottom.a")
    x.wire("r_bottom.a", "voltmeter.+")
    x.wire("voltmeter.-", "r_bottom.b")
    x.wire("r_bottom.b", "battery.-", via=[(4, -3), (0, -3)])
    x.wire("battery.-", "ground.gnd")


@example("RC charging: close the switch and watch the capacitor charge (fast at first, then slower). tau = R*C = 1 s.",
         ["simulate_transient(duration=6, events=[{time:0.3, component:<switch>, closed:true}])",
          "animate_circuit(start=0, end=12)",
          "add_plot(signals=[{component:<capacitor>, quantity:'voltage'}, {component:<resistor>, quantity:'current'}], end=12)"])
def rc_charging(x):
    x.add("battery", "battery", (0, 0), 90, voltage=5)
    x.add("switch", "switch", (3, 2), 0, closed=False)
    x.add("resistor", "resistor", (7, 2), 0, resistance=1000)
    x.add("capacitor", "capacitor", (10, 0), -90, capacitance=1e-3)
    x.add("voltmeter", "voltmeter", (13, 0), -90)
    x.wire("battery.+", "switch.a")
    x.wire("switch.b", "resistor.a")
    x.wire("resistor.b", "capacitor.a")
    x.wire("capacitor.b", "battery.-")
    x.wire("voltmeter.+", "capacitor.a")
    x.wire("voltmeter.-", "capacitor.b")


@example("Transistor as a switch: a tiny base current (push button) controls a much larger collector current (LED).",
         ["simulate_transient(duration=4, events=[{time:1, component:<button>, closed:true}, {time:3, component:<button>, closed:false}])",
          "animate_circuit(end=12, scaling='sqrt')"])
def transistor_switch(x):
    x.add("battery", "battery", (0, 0), 90, voltage=9)
    x.add("j_rail", "junction", (1, 3.5))
    x.add("r_led", "resistor", (5, 3.5), 0, resistance=330)
    x.add("led", "led", (8, 2.5), -90, color="green")
    x.add("button", "push_button", (2, 0), 0)
    x.add("r_base", "resistor", (5, 0), 0, resistance=10000)
    x.add("transistor", "npn", (8, 0), 0)
    x.wire("battery.+", "j_rail.n")
    x.wire("j_rail.n", "r_led.a")
    x.wire("r_led.b", "led.anode")
    x.wire("led.cathode", "transistor.c")
    x.wire("j_rail.n", "button.a")
    x.wire("button.b", "r_base.a")
    x.wire("r_base.b", "transistor.b")
    x.wire("transistor.e", "battery.-")


@example("Short circuit: a wire straight across the battery draws a huge current until the fuse blows.",
         ["simulate_dc()  (see warnings)", "animate_circuit(scaling='log')", "highlight(<fuse>)"])
def short_circuit(x):
    x.add("battery", "battery", (0, 0), 90, voltage=9)
    x.add("fuse", "fuse", (3, 2), 0, rating=2.0)
    x.wire("battery.+", "fuse.a")
    x.wire("fuse.b", "battery.-", via=[(5, 2), (5, -1)])


@example("Ohm's law bench: power supply, ammeter in series, voltmeter in parallel with a 100 ohm resistor.",
         ["simulate_dc()", "animate_circuit()", "add_callout('I = V / R', <resistor>)"])
def ohms_law(x):
    x.add("supply", "dc_source", (0, 0), 90, voltage=6)
    x.add("ammeter", "ammeter", (3, 2), 0)
    x.add("resistor", "resistor", (7, 0), -90, resistance=100)
    x.add("voltmeter", "voltmeter", (10, 0), -90)
    x.wire("supply.+", "ammeter.+")
    x.wire("ammeter.-", "resistor.a")
    x.wire("resistor.b", "supply.-")
    x.wire("voltmeter.+", "resistor.a")
    x.wire("voltmeter.-", "resistor.b")


@example("Battery, switch and DC motor: the motor spins faster with more current.",
         ["simulate_transient(duration=4, events=[{time:0.5, component:<switch>, closed:true}])", "animate_circuit(end=8)"])
def motor_circuit(x):
    x.add("battery", "battery", (0, 0), 90, voltage=6)
    x.add("switch", "switch", (3, 2), 0, closed=False)
    x.add("motor", "motor", (6, 0), -90)
    x.wire("battery.+", "switch.a")
    x.wire("switch.b", "motor.a")
    x.wire("motor.b", "battery.-")


@example("AC source driving a resistor and capacitor: current reverses direction every half cycle.",
         ["simulate_transient(duration=3)", "animate_circuit(end=12, mode='electron')",
          "add_plot(signals=[{component:<source>, quantity:'voltage'}, {component:<capacitor>, quantity:'voltage'}])"])
def ac_rc(x):
    x.add("source", "ac_source", (0, 0), 90, amplitude=5, frequency=1)
    x.add("resistor", "resistor", (3, 2), 0, resistance=1000)
    x.add("capacitor", "capacitor", (6, 0), -90, capacitance=100e-6)
    x.wire("source.+", "resistor.a")
    x.wire("resistor.b", "capacitor.a")
    x.wire("capacitor.b", "source.-")


@example("Dimmer: a potentiometer controls the brightness of a bulb.",
         ["simulate_transient(duration=4, events=[{time:1, component:<pot>, param:'position', value:0.2}, {time:2.5, component:<pot>, param:'position', value:0.95}])",
          "animate_circuit(end=10)"])
def dimmer(x):
    x.add("battery", "battery", (0, 0), 90, voltage=9)
    x.add("pot", "potentiometer", (3, 2), 0, resistance=100, position=0.95)
    x.add("bulb", "bulb", (6, 0), -90, rated_voltage=9, rated_power=3)
    x.wire("battery.+", "pot.a")
    x.wire("pot.w", "bulb.a", via=[(3, 3.5), (6, 3.5)])
    x.wire("bulb.b", "battery.-")


def build(circ, name, origin=(0, 0)):
    spec = EXAMPLES.get(name)
    if spec is None:
        raise KeyError("Unknown example '%s'. Available: %s" % (name, ", ".join(EXAMPLES)))
    ctx = _Ctx(circ, origin)
    spec["fn"](ctx)
    steps = [s for s in spec["next_steps"]]
    for role, cid in ctx.ids.items():
        steps = [s.replace("<%s>" % role, repr(cid)) for s in steps]
    return {"example": name, "ids": ctx.ids, "wires": ctx.wires, "description": spec["description"],
            "suggested_next_steps": steps}


def describe():
    return {name: spec["description"] for name, spec in EXAMPLES.items()}
