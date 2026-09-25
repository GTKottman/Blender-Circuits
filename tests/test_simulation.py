"""Pure-Python tests: simulator, circuit model, catalog helpers, examples (no Blender needed)."""

import math

import pytest

from blender_circuits import catalog, examples
from blender_circuits.circuit import Circuit, series_value, summarize
from blender_circuits.simulation import Netlist


def test_voltage_divider_dc():
    n = Netlist()
    n.vsource("V1", "in", "0", 9.0)
    n.resistor("R1", "in", "mid", 1000)
    n.resistor("R2", "mid", "0", 2000)
    r = n.dc()
    assert r["voltages"]["mid"] == pytest.approx(6.0, rel=1e-6)
    assert r["currents"]["R1"] == pytest.approx(3e-3, rel=1e-6)
    # source current enters + terminal: negative while delivering power
    assert r["currents"]["V1"] == pytest.approx(-3e-3, rel=1e-6)


def test_led_forward_voltage_and_current():
    c = Circuit()
    b = c.add_component("battery", position=(0, 0), rotation=90, voltage=9)
    r = c.add_component("resistor", position=(3, 2), resistance=330)
    led = c.add_component("led", position=(6, 0), rotation=-90, color="red")
    c.connect(b + ".+", r + ".a")
    c.connect(r + ".b", led + ".anode")
    c.connect(led + ".cathode", b + ".-")
    res = c.simulate_dc()
    i = res["components"][led]["current"]
    assert 0.018 < i < 0.024
    assert 1.8 < res["components"][led]["voltage"] < 2.2
    assert res["components"][led]["lit"]
    # the same current flows through every series element and wire
    assert res["components"][b]["current"] == pytest.approx(i, rel=1e-4)
    for w in res["wires"].values():
        assert abs(w["current"]) == pytest.approx(i, rel=1e-4)


def test_reverse_led_does_not_light():
    c = Circuit()
    b = c.add_component("battery", position=(0, 0), voltage=9)
    led = c.add_component("led", position=(3, 0))
    c.connect(b + ".+", led + ".cathode")
    c.connect(led + ".anode", b + ".-")
    res = c.simulate_dc()
    assert abs(res["components"][led]["current"]) < 1e-9
    assert not res["components"][led]["lit"]


def test_rc_time_constant():
    n = Netlist()
    n.vsource("V", "p", "0", 5.0)
    n.resistor("R", "p", "c", 1000)
    n.capacitor("C", "c", "0", 1e-3)
    snaps = n.transient(5.0, 0.002)
    at_tau = min(snaps, key=lambda s: abs(s["t"] - 1.0))
    assert at_tau["voltages"]["c"] == pytest.approx(5 * (1 - math.exp(-1)), rel=0.01)
    assert snaps[-1]["voltages"]["c"] == pytest.approx(5 * (1 - math.exp(-5)), rel=0.01)


def test_rl_current_rise():
    n = Netlist()
    n.vsource("V", "p", "0", 10.0)
    n.resistor("R", "p", "l", 10.0)
    n.inductor("L", "l", "0", 1.0)
    snaps = n.transient(0.5, 0.0005)
    at_tau = min(snaps, key=lambda s: abs(s["t"] - 0.1))
    assert at_tau["currents"]["L"] == pytest.approx(1.0 * (1 - math.exp(-1)), rel=0.02)


def test_bjt_cutoff_and_saturation():
    def run(rb_to_vcc):
        n = Netlist()
        n.vsource("V", "vcc", "0", 9.0)
        n.resistor("Rc", "vcc", "c", 1000)
        n.resistor("Rb", "vcc" if rb_to_vcc else "0", "b", 10e3)
        n.bjt("Q", "c", "b", "0")
        return n.dc()["devices"]["Q"]
    on, off = run(True), run(False)
    assert on["vce"] < 0.3 and on["ic"] > 8e-3
    assert off["ic"] < 1e-9 and off["vce"] > 8.9


def test_transient_switch_event_and_ac_source():
    info_c = Circuit()
    examples.build(info_c, "rc_charging")
    res = info_c.simulate_transient(6, events=[{"time": 0.5, "component": "S1", "closed": True}])
    v = res["components"]["C1"]["voltage"]
    assert v[0] == pytest.approx(0.0, abs=1e-6)
    assert series_value(res, "components", "C1", "voltage", 0.4) == pytest.approx(0.0, abs=1e-3)
    assert series_value(res, "components", "C1", "voltage", 1.5) == pytest.approx(5 * (1 - math.exp(-1)), rel=0.02)
    ac = Circuit()
    examples.build(ac, "ac_rc")
    r = ac.simulate_transient(2.0)
    cur = r["components"]["R1"]["current"]
    assert max(cur) > 1e-3 and min(cur) < -1e-3  # current reverses


def test_potentiometer_event():
    c = Circuit()
    examples.build(c, "dimmer")
    res = c.simulate_transient(3, events=[{"time": 1, "component": "RV1", "param": "position", "value": 0.05}])
    early = series_value(res, "components", "LAMP1", "brightness", 0.5)
    late = series_value(res, "components", "LAMP1", "brightness", 2.5)
    assert late > early * 2


def test_short_circuit_warning_and_fuse():
    c = Circuit()
    examples.build(c, "short_circuit")
    res = c.simulate_dc()
    assert res["components"]["F1"]["blown"]
    assert any("short" in w for w in res["warnings"])


@pytest.mark.parametrize("name", sorted(examples.EXAMPLES))
def test_every_example_simulates(name):
    c = Circuit()
    info = examples.build(c, name)
    assert info["ids"] and info["wires"]
    res = c.simulate_dc()
    summary = summarize(res)
    assert set(summary["components"]) == set(c.components)
    for comp in res["components"].values():
        assert math.isfinite(comp["current"])


def test_rotation_and_routing():
    c = Circuit()
    b = c.add_component("battery", position=(0, 0), rotation=90)
    r = c.add_component("resistor", position=(3, 2))
    assert [round(x, 6) for x in c.terminal_world(b + ".+")[:2]] == [0.0, 1.0]
    assert [round(x, 6) for x in c.terminal_world(b + ".-")[:2]] == [0.0, -1.0]
    w = c.connect(b + ".+", r + ".a")
    pts = [[round(v, 6) for v in p[:2]] for p in c.wire_points(w)]
    assert pts == [[0.0, 1.0], [0.0, 2.0], [2.0, 2.0]]  # vertical first, then horizontal
    for p1, p2 in zip(pts, pts[1:]):
        assert p1[0] == p2[0] or p1[1] == p2[1]  # right angles only


def test_terminal_aliases_and_errors():
    c = Circuit()
    d = c.add_component("led", position=(0, 0))
    assert c.parse_ref(d + ".k") == (d, "cathode")
    assert c.parse_ref(d + ".1") == (d, "anode")
    with pytest.raises(ValueError):
        c.parse_ref(d + ".x")
    with pytest.raises(KeyError):
        c.parse_ref("nope.a")
    with pytest.raises(ValueError):
        c.add_component("flux_capacitor")


def test_remove_component_removes_wires():
    c = Circuit()
    examples.build(c, "led_circuit")
    removed = c.remove_component("R1")
    assert len(removed) == 2 and len(c.wires) == 2


@pytest.mark.parametrize("text,value", [("4.7k", 4700), ("100uF", 100e-6), ("2.2 MΩ", 2.2e6), ("10mA", 0.01),
                                        ("1meg", 1e6), (330, 330), ("0.5", 0.5)])
def test_parse_value(text, value):
    assert catalog.parse_value(text) == pytest.approx(value)


def test_format_si():
    assert catalog.format_si(0.0203, "A") == "20.3 mA"
    assert catalog.format_si(4700, "Ω") == "4.7 kΩ"
    assert catalog.format_si(0, "V") == "0 V"
    assert catalog.format_si(1e-16, "V") == "0 V"


def test_chip_terminals_dip_numbering():
    terms, order = catalog.chip_terminals(8)
    assert order == ["p%d" % i for i in range(1, 9)]
    assert terms["p1"][0] < 0 and terms["p8"][0] > 0
    assert terms["p1"][1] == terms["p8"][1]  # pin 1 opposite pin 8
