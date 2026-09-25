"""Circuit model: components, wires, routing and the bridge to the simulator.

Pure Python (no bpy).  The Blender layer stores ``Circuit.to_dict()`` as JSON
inside the .blend file and rebuilds 3D objects from it.
"""

import copy
import math

from . import catalog
from .simulation import Netlist, SimulationError

ID_PREFIX = {
    "resistor": "R", "potentiometer": "RV", "battery": "B", "dc_source": "PSU", "ac_source": "VAC",
    "current_source": "I", "capacitor": "C", "inductor": "L", "diode": "D", "led": "LED", "bulb": "LAMP",
    "switch": "S", "push_button": "PB", "ammeter": "AM", "voltmeter": "VM", "motor": "M", "speaker": "SPK",
    "fuse": "F", "npn": "Q", "pnp": "Q", "ground": "GND", "junction": "J", "chip": "U",
}
SOURCE_TYPES = ("battery", "dc_source", "ac_source", "current_source")
DEFAULT_SETTINGS = {
    "style": "realistic",       # or "schematic"
    "height": 0.3,              # z height of terminals / wires above the board
    "wire_resistance": 1e-3,    # ohms per wire (keeps short circuits finite and gives per-wire currents)
    "wire_radius": 0.035,
    "show_labels": True,
    "show_values": True,
}


def _vec(v, n=3):
    v = list(v or [0, 0, 0])
    while len(v) < n:
        v.append(0.0)
    return [float(x) for x in v[:n]]


class Circuit:
    def __init__(self, data=None):
        data = copy.deepcopy(data or {})
        self.components = data.get("components", {})
        self.wires = data.get("wires", {})
        self.settings = dict(DEFAULT_SETTINGS)
        self.settings.update(data.get("settings", {}))
        self.order = data.get("order", list(self.components))

    def to_dict(self):
        return {"components": self.components, "wires": self.wires, "settings": self.settings, "order": self.order}

    # ------------------------------------------------------------------ ids
    def _new_id(self, prefix, taken):
        i = 1
        while "%s%d" % (prefix, i) in taken:
            i += 1
        return "%s%d" % (prefix, i)

    # ------------------------------------------------------------ components
    def add_component(self, ctype, cid=None, position=(0, 0), rotation=0.0, params=None, label=None,
                      style=None, show_value=None, label_offset=None, **extra):
        ctype = catalog.canonical_type(ctype)
        if cid is None:
            cid = self._new_id(ID_PREFIX[ctype], set(self.components) | set(self.wires))
        cid = str(cid)
        if cid in self.components or cid in self.wires:
            raise ValueError("An element with id '%s' already exists" % cid)
        merged = catalog.default_params(ctype)
        for key, val in (params or {}).items():
            merged[key] = catalog.parse_value(val) if key not in ("color", "text", "look") else val
        # Allow common shorthand params passed at top level (e.g. resistance=220)
        for key, val in extra.items():
            if val is not None:
                merged[key] = catalog.parse_value(val) if key not in ("color", "text", "look") else val
        pos = _vec(position)
        comp = {
            "type": ctype,
            "params": merged,
            "position": pos,
            "rotation": float(rotation or 0.0),
            "label": label,
            "style": style,
            "show_value": show_value,
        }
        if label_offset is not None:
            comp["label_offset"] = _vec(label_offset)
        self.components[cid] = comp
        self.order.append(cid)
        return cid

    def get(self, cid):
        if cid not in self.components:
            raise KeyError("No component '%s' (have: %s)" % (cid, ", ".join(self.components) or "none"))
        return self.components[cid]

    def update_component(self, cid, params=None, position=None, rotation=None, label=None, style=None, **extra):
        comp = self.get(cid)
        for key, val in (params or {}).items():
            comp["params"][key] = catalog.parse_value(val) if key not in ("color", "text", "look") else val
        for key, val in extra.items():
            if val is not None:
                comp["params"][key] = catalog.parse_value(val) if key not in ("color", "text", "look") else val
        if position is not None:
            comp["position"] = _vec(position)
        if rotation is not None:
            comp["rotation"] = float(rotation)
        if label is not None:
            comp["label"] = label
        if style is not None:
            comp["style"] = style
        return comp

    def remove_component(self, cid):
        self.get(cid)
        del self.components[cid]
        self.order = [c for c in self.order if c != cid]
        removed = [w for w, d in self.wires.items() if d["from"].split(".")[0] == cid or d["to"].split(".")[0] == cid]
        for w in removed:
            del self.wires[w]
        return removed

    # ----------------------------------------------------------- terminals
    def parse_ref(self, ref):
        """'R1.a' -> ('R1', 'a').  A bare id is allowed for single-terminal parts."""
        ref = str(ref)
        if "." in ref:
            cid, term = ref.split(".", 1)
        else:
            cid, term = ref, None
        comp = self.get(cid)
        terms, order = catalog.terminals_of(comp["type"], comp["params"])
        if term is None:
            if len(order) != 1:
                raise ValueError("'%s' has several terminals (%s); use '%s.<terminal>'" % (cid, ", ".join(order), cid))
            term = order[0]
        return cid, catalog.resolve_terminal(comp["type"], term, comp["params"])

    def terminal_local(self, cid, term):
        comp = self.get(cid)
        terms, _ = catalog.terminals_of(comp["type"], comp["params"])
        return terms[term]

    def terminal_world(self, ref):
        cid, term = self.parse_ref(ref)
        comp = self.get(cid)
        local = self.terminal_local(cid, term)
        rx, ry, rz = catalog.rotate_z(local, comp["rotation"])
        px, py, pz = comp["position"]
        return [px + rx, py + ry, pz + rz + self.settings["height"]]

    def terminal_direction(self, ref):
        cid, term = self.parse_ref(ref)
        comp = self.get(cid)
        local = self.terminal_local(cid, term)
        d = catalog.rotate_z(local, comp["rotation"])
        length = math.hypot(d[0], d[1])
        if length < 1e-9:
            return [0.0, 0.0]
        return [d[0] / length, d[1] / length]

    def terminals(self, cid):
        comp = self.get(cid)
        _, order = catalog.terminals_of(comp["type"], comp["params"])
        return {t: self.terminal_world("%s.%s" % (cid, t)) for t in order}

    # --------------------------------------------------------------- wires
    def connect(self, a, b, wid=None, via=None, route="auto", color=None):
        ca, ta = self.parse_ref(a)
        cb, tb = self.parse_ref(b)
        if wid is None:
            wid = self._new_id("W", set(self.components) | set(self.wires))
        if wid in self.wires or wid in self.components:
            raise ValueError("An element with id '%s' already exists" % wid)
        self.wires[wid] = {"from": "%s.%s" % (ca, ta), "to": "%s.%s" % (cb, tb),
                           "via": [_vec(p, 2) for p in (via or [])], "route": route or "auto", "color": color}
        return wid

    def remove_wire(self, wid):
        if wid not in self.wires:
            raise KeyError("No wire '%s'" % wid)
        del self.wires[wid]

    def wire_points(self, wid):
        w = self.wires[wid]
        h = self.settings["height"]
        pa = self.terminal_world(w["from"])
        pb = self.terminal_world(w["to"])
        route = w.get("route", "auto")
        pts = [pa]
        waypoints = [[p[0], p[1], h if len(p) < 3 else p[2]] for p in w.get("via") or []]
        targets = waypoints + [pb]
        cur = pa
        for i, tgt in enumerate(targets):
            if route == "direct" or (abs(cur[0] - tgt[0]) < 1e-6 or abs(cur[1] - tgt[1]) < 1e-6):
                pts.append(tgt)
            else:
                mode = route
                if mode == "auto":
                    ref_dir = self.terminal_direction(w["from"]) if i == 0 else None
                    if ref_dir is not None and abs(ref_dir[1]) > abs(ref_dir[0]):
                        mode = "vh"
                    elif ref_dir is not None:
                        mode = "hv"
                    else:
                        mode = "hv" if abs(tgt[0] - cur[0]) >= abs(tgt[1] - cur[1]) else "vh"
                if mode == "vh":
                    corner = [cur[0], tgt[1], h]
                else:
                    corner = [tgt[0], cur[1], h]
                pts.append(corner)
                pts.append(tgt)
            cur = tgt
        # drop consecutive duplicates
        clean = [pts[0]]
        for p in pts[1:]:
            if max(abs(p[k] - clean[-1][k]) for k in range(3)) > 1e-6:
                clean.append(p)
        if len(clean) == 1:
            clean.append(list(clean[0]))
        return clean

    # --------------------------------------------------------- simulation
    def _node(self, cid, term):
        comp = self.components[cid]
        if comp["type"] == "ground":
            return "0"
        return "%s.%s" % (cid, term)

    def build_netlist(self):
        """Return (netlist, probes, switches).

        probes: cid -> (element name, sign) giving the component current in its terminal order.
        switches: cid -> element whose resistance toggles the switch.
        """
        net = Netlist()
        probes, switches = {}, {}
        for cid in self.order:
            if cid not in self.components:
                continue
            comp = self.components[cid]
            t = comp["type"]
            p = comp["params"]
            _, order = catalog.terminals_of(t, p)
            n = {term: self._node(cid, term) for term in order}
            if t in ("resistor", "bulb", "ammeter", "voltmeter", "motor", "speaker", "fuse"):
                r = p.get("resistance")
                if t == "bulb" and not r:
                    r = float(p["rated_voltage"]) ** 2 / max(float(p["rated_power"]), 1e-9)
                net.resistor(cid, n[order[0]], n[order[1]], r)
                probes[cid] = (cid, 1)
            elif t == "potentiometer":
                r = float(p["resistance"])
                pos = min(max(float(p.get("position", 0.5)), 0.0), 1.0)
                net.resistor(cid + ":aw", n["a"], n["w"], max(r * pos, 1e-3))
                net.resistor(cid + ":wb", n["w"], n["b"], max(r * (1 - pos), 1e-3))
                probes[cid] = (cid + ":aw", 1)
            elif t in ("battery", "dc_source", "ac_source"):
                internal = cid + "#int"
                if t == "ac_source":
                    amp, f = float(p["amplitude"]), float(p["frequency"])
                    ph, off = math.radians(float(p.get("phase", 0.0))), float(p.get("offset", 0.0))
                    value = (lambda tt, amp=amp, f=f, ph=ph, off=off: off + amp * math.sin(2 * math.pi * f * tt + ph))
                else:
                    value = float(p["voltage"])
                net.vsource(cid + ":v", internal, n["-"], value)
                net.resistor(cid, internal, n["+"], max(float(p.get("internal_resistance") or 1e-6), 1e-6))
                net.preferred_refs.append(n["-"])
                probes[cid] = (cid, 1)
            elif t == "current_source":
                net.isource(cid, n["-"], n["+"], float(p["current"]))
                net.preferred_refs.append(n["-"])
                probes[cid] = (cid, 1)
            elif t == "capacitor":
                net.capacitor(cid, n["a"], n["b"], p["capacitance"], p.get("initial_voltage", 0.0))
                probes[cid] = (cid, 1)
            elif t == "inductor":
                internal = cid + "#int"
                net.inductor(cid, n["a"], internal, p["inductance"], p.get("initial_current", 0.0))
                net.resistor(cid + ":rs", internal, n["b"], max(float(p.get("series_resistance") or 1e-6), 1e-6))
                probes[cid] = (cid, 1)
            elif t == "diode":
                vf = float(p.get("forward_voltage") or 0.7)
                i_s = 0.01 / math.exp(vf / 0.025852)
                net.diode(cid, n["anode"], n["cathode"], i_s=i_s, n=1.0)
                probes[cid] = (cid, 1)
            elif t == "led":
                color, vf_default = catalog.led_color(p.get("color", "red"))
                vf = float(p.get("forward_voltage") or vf_default)
                n_ideal = 2.0
                i_s = 0.02 / math.exp((vf - 0.02 * 5.0) / (n_ideal * 0.025852))
                internal = cid + "#int"
                net.diode(cid, n["anode"], internal, i_s=i_s, n=n_ideal)
                net.resistor(cid + ":rs", internal, n["cathode"], 5.0)
                probes[cid] = (cid, 1)
            elif t in ("switch", "push_button"):
                el = net.resistor(cid, n["a"], n["b"], 1e-3 if p.get("closed") else 1e12)
                probes[cid] = (cid, 1)
                switches[cid] = el
            elif t in ("npn", "pnp"):
                el = net.bjt(cid, n["c"], n["b"], n["e"], polarity=1 if t == "npn" else -1, beta=float(p.get("beta", 100)))
                probes[cid] = (cid, 1 if t == "npn" else -1)
            # ground, junction, chip: no electrical element
        wr = float(self.settings.get("wire_resistance", 1e-3))
        for wid, w in self.wires.items():
            ca, ta = w["from"].split(".", 1)
            cb, tb = w["to"].split(".", 1)
            net.resistor(wid, self._node(ca, ta), self._node(cb, tb), wr)
        return net, probes, switches

    def _component_reading(self, cid, volts, currents, devices):
        comp = self.components[cid]
        t = comp["type"]
        _, order = catalog.terminals_of(t, comp["params"])
        v = {term: volts.get(self._node(cid, term), 0.0) for term in order}
        info = {}
        if len(order) >= 2:
            if t in SOURCE_TYPES:
                info["voltage"] = v[order[1]] - v[order[0]]
            else:
                info["voltage"] = v[order[0]] - v[order[1]]
        info["terminal_voltages"] = v
        return info

    def _format_snapshot(self, snap, probes):
        volts, currents, devices = snap["voltages"], snap["currents"], snap["devices"]
        comps = {}
        for cid, comp in self.components.items():
            info = self._component_reading(cid, volts, currents, devices)
            if cid in probes:
                name, sign = probes[cid]
                cur = sign * currents.get(name, 0.0)
                if comp["type"] == "npn" or comp["type"] == "pnp":
                    dev = devices.get(cid, {})
                    info.update({k: dev.get(k) for k in ("ic", "ib", "ie", "vbe", "vce")})
                    cur = dev.get("ic", 0.0) if comp["type"] == "npn" else -dev.get("ie", 0.0)
                    info["voltage"] = dev.get("vce", 0.0)
                info["current"] = cur
                if "voltage" in info:
                    info["power"] = info["voltage"] * cur
                if comp["type"] == "potentiometer":
                    info["current_wb"] = currents.get(cid + ":wb", 0.0)
            else:
                info["current"] = 0.0
            ctype = comp["type"]
            if ctype == "led":
                imax = float(comp["params"].get("max_current") or 0.02)
                info["brightness"] = max(0.0, info["current"]) / imax
                info["lit"] = info["current"] > imax * 0.02
            elif ctype == "bulb":
                pr = float(comp["params"].get("rated_power") or 1.0)
                info["brightness"] = max(0.0, info.get("power", 0.0)) / pr
                info["lit"] = info["brightness"] > 0.02
            elif ctype == "fuse":
                info["blown"] = abs(info["current"]) > float(comp["params"].get("rating") or 1.0)
            elif ctype == "motor":
                info["rpm"] = info["current"] * float(comp["params"].get("rpm_per_amp") or 600.0)
            elif ctype == "ammeter":
                info["reading"] = info["current"]
            elif ctype == "voltmeter":
                info["reading"] = info.get("voltage", 0.0)
            elif ctype == "capacitor":
                info["charge"] = info.get("voltage", 0.0) * float(comp["params"]["capacitance"])
            comps[cid] = info
        wires = {}
        for wid, w in self.wires.items():
            ca, ta = w["from"].split(".", 1)
            cb, tb = w["to"].split(".", 1)
            va = volts.get(self._node(ca, ta), 0.0)
            vb = volts.get(self._node(cb, tb), 0.0)
            wires[wid] = {"current": currents.get(wid, 0.0), "voltage": 0.5 * (va + vb)}
        return comps, wires

    def simulate_dc(self):
        net, probes, _ = self.build_netlist()
        snap = net.dc()
        comps, wires = self._format_snapshot(snap, probes)
        max_i = max([abs(w["current"]) for w in wires.values()] + [abs(c.get("current", 0.0)) for c in comps.values()] + [0.0])
        volts = [v for v in snap["voltages"].values()]
        return {
            "type": "dc",
            "components": comps,
            "wires": wires,
            "max_current": max_i,
            "min_voltage": min(volts) if volts else 0.0,
            "max_voltage": max(volts) if volts else 0.0,
            "warnings": self._warnings(comps, wires),
        }

    def _warnings(self, comps, wires):
        out = []
        for cid, info in comps.items():
            t = self.components[cid]["type"]
            if t == "led" and info["current"] > 1.5 * float(self.components[cid]["params"].get("max_current") or 0.02):
                out.append("%s: LED current %s exceeds its rating - it would burn out (add a resistor)." % (
                    cid, catalog.format_si(info["current"], "A")))
            if t in ("battery", "dc_source") and abs(info["current"]) > 5:
                out.append("%s: %s drawn - this looks like a short circuit!" % (cid, catalog.format_si(info["current"], "A")))
            if t == "fuse" and info.get("blown"):
                out.append("%s: fuse would blow (%s > rating)." % (cid, catalog.format_si(abs(info["current"]), "A")))
        return out

    def simulate_transient(self, duration, dt=None, events=None, samples=None, start_from_dc=False):
        """events: list of {"time": s, "component": id, "closed": bool} or
        {"time": s, "component": id, "param": name, "value": v} (e.g. potentiometer position)."""
        net, probes, switches = self.build_netlist()
        duration = float(duration)
        if dt is None:
            dt = duration / 2000.0
        samples = int(samples or 400)
        ev_calls = []
        for ev in events or []:
            cid = ev.get("component") or ev.get("id")
            tev = float(ev.get("time", 0.0))
            if "closed" in ev:
                if cid not in switches:
                    raise ValueError("Event component '%s' is not a switch" % cid)
                el = switches[cid]
                val = 1e-3 if ev["closed"] else 1e12
                ev_calls.append((tev, (lambda el=el, val=val: setattr(el, "value", val))))
            elif ev.get("param") == "position" and self.get(cid)["type"] == "potentiometer":
                r = float(self.get(cid)["params"]["resistance"])
                pos = min(max(float(ev["value"]), 0.0), 1.0)
                els = {e.name: e for e in net.elements}

                def set_pot(els=els, cid=cid, r=r, pos=pos):
                    els[cid + ":aw"].value = max(r * pos, 1e-3)
                    els[cid + ":wb"].value = max(r * (1 - pos), 1e-3)
                ev_calls.append((tev, set_pot))
            else:
                raise ValueError("Unsupported event %r (use 'closed' for switches or param='position' for pots)" % ev)
        steps = max(1, int(math.ceil(duration / dt)))
        record_every = max(1, steps // samples)
        snaps = net.transient(duration, dt, events=ev_calls, record_every=record_every, start_from_dc=start_from_dc)
        times = [s["t"] for s in snaps]
        comp_series, wire_series = {}, {}
        for snap in snaps:
            comps, wires = self._format_snapshot(snap, probes)
            for cid, info in comps.items():
                d = comp_series.setdefault(cid, {})
                for k, v in info.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        d.setdefault(k, []).append(v)
                    elif isinstance(v, bool):
                        d.setdefault(k, []).append(v)
            for wid, info in wires.items():
                d = wire_series.setdefault(wid, {})
                for k, v in info.items():
                    d.setdefault(k, []).append(v)
        all_i = [abs(x) for d in wire_series.values() for x in d["current"]]
        all_v = [x for d in wire_series.values() for x in d["voltage"]]
        return {
            "type": "transient",
            "duration": duration,
            "times": times,
            "events": list(events or []),
            "components": comp_series,
            "wires": wire_series,
            "max_current": max(all_i) if all_i else 0.0,
            "min_voltage": min(all_v) if all_v else 0.0,
            "max_voltage": max(all_v) if all_v else 0.0,
        }


def series_value(result, kind, key, field, t=None):
    """Read a value from a DC or transient result at simulation time t (linear interpolation)."""
    entry = result[kind].get(key)
    if entry is None:
        return 0.0
    val = entry.get(field)
    if result["type"] == "dc":
        return float(val or 0.0) if not isinstance(val, bool) else val
    if val is None:
        return 0.0
    times = result["times"]
    if t is None or t <= times[0]:
        return val[0]
    if t >= times[-1]:
        return val[-1]
    lo, hi = 0, len(times) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if times[mid] <= t:
            lo = mid
        else:
            hi = mid
    t0, t1 = times[lo], times[hi]
    v0, v1 = val[lo], val[hi]
    if isinstance(v0, bool):
        return v0
    f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
    return v0 + (v1 - v0) * f


def summarize(result, digits=4):
    """Compact human/AI readable summary of a simulation result."""
    fmt = catalog.format_si
    out = {"type": result["type"]}
    if result["type"] == "dc":
        comps = {}
        for cid, info in result["components"].items():
            entry = {}
            if "voltage" in info:
                entry["voltage"] = fmt(info["voltage"], "V", digits)
            entry["current"] = fmt(info.get("current", 0.0), "A", digits)
            if "power" in info:
                entry["power"] = fmt(info["power"], "W", digits)
            for k in ("brightness", "lit", "blown", "rpm", "charge", "ib", "vce"):
                if k in info and info[k] is not None:
                    entry[k] = round(info[k], 4) if isinstance(info[k], float) else info[k]
            comps[cid] = entry
        out["components"] = comps
        out["wires"] = {w: {"current": fmt(i["current"], "A", digits), "voltage": fmt(i["voltage"], "V", digits)}
                        for w, i in result["wires"].items()}
        out["warnings"] = result.get("warnings", [])
    else:
        out["duration"] = result["duration"]
        out["samples"] = len(result["times"])
        comps = {}
        for cid, series in result["components"].items():
            entry = {}
            for field in ("voltage", "current"):
                if field in series:
                    vals = series[field]
                    unit = "V" if field == "voltage" else "A"
                    entry[field] = {"start": fmt(vals[0], unit, digits), "end": fmt(vals[-1], unit, digits),
                                    "min": fmt(min(vals), unit, digits), "max": fmt(max(vals), unit, digits)}
            comps[cid] = entry
        out["components"] = comps
    out["max_current"] = fmt(result.get("max_current", 0.0), "A", digits)
    return out


__all__ = ["Circuit", "SimulationError", "series_value", "summarize"]
