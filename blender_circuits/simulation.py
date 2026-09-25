"""A small SPICE-like circuit simulator (pure Python, optional numpy).

Supports resistors, voltage/current sources (constant or time dependent),
capacitors, inductors, diodes (Shockley model) and BJTs (Ebers-Moll), with
DC operating point and transient (backward Euler) analysis using Modified
Nodal Analysis and Newton-Raphson iteration.

The results feed the Blender animation layer: electron speed follows branch
current, LED/bulb brightness follows power, wire colour follows node voltage.
"""

import math

try:  # Blender always bundles numpy; the fallback keeps the module portable.
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None

VT = 0.025852  # thermal voltage at ~300 K
GMIN = 1e-12
GROUND_NAMES = ("0", "gnd", "GND", "ground")


class SimulationError(Exception):
    pass


class Element:
    __slots__ = ("kind", "name", "nodes", "value", "params", "state")

    def __init__(self, kind, name, nodes, value=None, **params):
        self.kind = kind
        self.name = name
        self.nodes = list(nodes)
        self.value = value
        self.params = params
        self.state = {}


def _value_at(value, t):
    return value(t) if callable(value) else value


def _pnjlim(vnew, vold, vt, vcrit):
    if vnew > vcrit and abs(vnew - vold) > 2 * vt:
        if vold > 0:
            arg = 1 + (vnew - vold) / vt
            vnew = vold + vt * math.log(arg) if arg > 0 else vcrit
        else:
            vnew = vt * math.log(vnew / vt)
    return vnew


def _safe_exp(x):
    if x > 80.0:
        return math.exp(80.0) * (1.0 + x - 80.0)
    return math.exp(x)


def _solve_dense(a, b):
    n = len(b)
    if _np is not None:
        try:
            return [float(v) for v in _np.linalg.solve(_np.array(a, dtype=float), _np.array(b, dtype=float))]
        except _np.linalg.LinAlgError as exc:
            raise SimulationError("Singular circuit matrix (check for loops of ideal sources or "
                                  "floating parts): %s" % exc)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-300:
            raise SimulationError("Singular circuit matrix (check for loops of ideal sources or floating parts)")
        m[col], m[piv] = m[piv], m[col]
        pivot = m[col][col]
        for r in range(col + 1, n):
            f = m[r][col] / pivot
            if f:
                row_r, row_c = m[r], m[col]
                for c in range(col, n + 1):
                    row_r[c] -= f * row_c[c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / m[r][r]
    return x


class Netlist:
    """Collection of circuit elements connected between named nodes."""

    def __init__(self):
        self.elements = []
        self._names = set()
        self.preferred_refs = []

    # -- element constructors ---------------------------------------------
    def _add(self, el):
        if el.name in self._names:
            raise SimulationError("Duplicate element name '%s'" % el.name)
        self._names.add(el.name)
        self.elements.append(el)
        return el

    def resistor(self, name, n1, n2, r):
        r = float(r)
        if r <= 0:
            r = 1e-9
        return self._add(Element("R", name, (n1, n2), r))

    def vsource(self, name, npos, nneg, v):
        """Voltage source; element current is the current entering npos through the source."""
        return self._add(Element("V", name, (npos, nneg), v))

    def isource(self, name, n1, n2, i):
        """Current source pushing i amps from n1 through itself to n2."""
        return self._add(Element("I", name, (n1, n2), i))

    def capacitor(self, name, n1, n2, c, v0=0.0):
        return self._add(Element("C", name, (n1, n2), float(c), v0=float(v0 or 0.0)))

    def inductor(self, name, n1, n2, l, i0=0.0):
        return self._add(Element("L", name, (n1, n2), float(l), i0=float(i0 or 0.0)))

    def diode(self, name, anode, cathode, i_s=1e-14, n=1.0):
        return self._add(Element("D", name, (anode, cathode), None, i_s=float(i_s), n=float(n)))

    def bjt(self, name, c, b, e, polarity=1, beta=100.0, beta_r=1.0, i_s=1e-14):
        return self._add(Element("Q", name, (c, b, e), None, polarity=polarity, bf=float(beta),
                                 br=float(beta_r), i_s=float(i_s)))

    # -- analysis ------------------------------------------------------------
    def _build_index(self):
        parent = {}

        def find(x):
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        nodes = []
        for el in self.elements:
            for n in el.nodes:
                if n not in parent:
                    nodes.append(n)
                find(n)
            for n in el.nodes[1:]:
                union(el.nodes[0], n)
        grounds = [n for n in nodes if str(n) in GROUND_NAMES]
        islands = {}
        for n in nodes:
            islands.setdefault(find(n), []).append(n)
        ground_alias = set(grounds)
        for root, members in islands.items():
            if any(m in ground_alias for m in members):
                continue
            ref = next((p for p in self.preferred_refs if p in members), members[0])
            ground_alias.add(ref)
        index = {}
        k = 0
        for n in nodes:
            if n in ground_alias:
                index[n] = -1
            else:
                index[n] = k
                k += 1
        return index, k, nodes

    def _assemble(self, index, nnodes, branch_idx, x, t, dt, mode, limit_state, source_scale):
        size = nnodes + len(branch_idx)
        a = [[0.0] * size for _ in range(size)]
        b = [0.0] * size

        def g_stamp(i, j, g):
            if i >= 0:
                a[i][i] += g
            if j >= 0:
                a[j][j] += g
            if i >= 0 and j >= 0:
                a[i][j] -= g
                a[j][i] -= g

        def i_inject(i, j, cur):
            # current `cur` flows out of node i (into the element) and into node j
            if i >= 0:
                b[i] -= cur
            if j >= 0:
                b[j] += cur

        def volt(i):
            return x[i] if i >= 0 else 0.0

        for k in range(nnodes):
            a[k][k] += GMIN

        for el in self.elements:
            idx = [index[n] for n in el.nodes]
            if el.kind == "R":
                g_stamp(idx[0], idx[1], 1.0 / el.value)
            elif el.kind == "V":
                row = branch_idx[el.name]
                p, n = idx
                if p >= 0:
                    a[p][row] += 1
                    a[row][p] += 1
                if n >= 0:
                    a[n][row] -= 1
                    a[row][n] -= 1
                b[row] = _value_at(el.value, t) * source_scale
            elif el.kind == "I":
                i_inject(idx[0], idx[1], _value_at(el.value, t) * source_scale)
            elif el.kind == "C":
                if mode == "tran":
                    g = el.value / dt
                    g_stamp(idx[0], idx[1], g)
                    vprev = el.state.get("v", el.params["v0"])
                    i_inject(idx[0], idx[1], -g * vprev)
            elif el.kind == "L":
                row = branch_idx[el.name]
                p, n = idx
                if p >= 0:
                    a[p][row] += 1
                    a[row][p] += 1
                if n >= 0:
                    a[n][row] -= 1
                    a[row][n] -= 1
                if mode == "tran":
                    req = el.value / dt
                    a[row][row] -= req
                    b[row] = -req * el.state.get("i", el.params["i0"])
            elif el.kind == "D":
                an, ca = idx
                nvt = el.params["n"] * VT
                i_s = el.params["i_s"]
                vd = volt(an) - volt(ca)
                vold = limit_state.get(el.name, 0.0)
                vcrit = nvt * math.log(nvt / (math.sqrt(2) * i_s))
                vlim = _pnjlim(vd, vold, nvt, vcrit)
                if abs(vlim - vd) > 1e-9:
                    limit_state["_limited"] = True
                vd = vlim
                limit_state[el.name] = vd
                e = _safe_exp(vd / nvt)
                cur = i_s * (e - 1.0)
                gd = i_s / nvt * e + GMIN
                g_stamp(an, ca, gd)
                i_inject(an, ca, cur - gd * vd)
            elif el.kind == "Q":
                c, bb, e = idx
                p = el.params["polarity"]
                i_s, bf, br = el.params["i_s"], el.params["bf"], el.params["br"]
                vbe = p * (volt(bb) - volt(e))
                vbc = p * (volt(bb) - volt(c))
                vcrit = VT * math.log(VT / (math.sqrt(2) * i_s))
                old = limit_state.get(el.name, (0.0, 0.0))
                vbe_l = _pnjlim(vbe, old[0], VT, vcrit)
                vbc_l = _pnjlim(vbc, old[1], VT, vcrit)
                if abs(vbe_l - vbe) > 1e-9 or abs(vbc_l - vbc) > 1e-9:
                    limit_state["_limited"] = True
                vbe, vbc = vbe_l, vbc_l
                limit_state[el.name] = (vbe, vbc)
                ef, er = _safe_exp(vbe / VT), _safe_exp(vbc / VT)
                i_f, i_r = i_s * (ef - 1), i_s * (er - 1)
                gf, gr = i_s / VT * ef + GMIN, i_s / VT * er + GMIN
                f = {"c": i_f - i_r - i_r / br, "b": i_f / bf + i_r / br}
                da = {"c": gf, "b": gf / bf}
                db = {"c": -gr - gr / br, "b": gr / br}
                f["e"] = -(f["c"] + f["b"])
                da["e"] = -(da["c"] + da["b"])
                db["e"] = -(db["c"] + db["b"])
                term_idx = {"c": c, "b": bb, "e": e}
                for k, row in term_idx.items():
                    if row < 0:
                        continue
                    ak, bk = da[k], db[k]
                    if bb >= 0:
                        a[row][bb] += ak + bk
                    if e >= 0:
                        a[row][e] -= ak
                    if c >= 0:
                        a[row][c] -= bk
                    const = p * (f[k] - ak * vbe - bk * vbc)
                    b[row] -= const
        return a, b

    def _newton(self, index, nnodes, branch_idx, x0, t, dt, mode, max_iter=200):
        x = list(x0)
        nonlinear = any(el.kind in ("D", "Q") for el in self.elements)
        limit_state = {}
        for el in self.elements:
            if el.kind == "D":
                limit_state[el.name] = el.state.get("vd", 0.0)
            elif el.kind == "Q":
                limit_state[el.name] = el.state.get("vj", (0.0, 0.0))
        for it in range(max_iter):
            limit_state["_limited"] = False
            a, b = self._assemble(index, nnodes, branch_idx, x, t, dt, mode, limit_state, 1.0)
            xn = _solve_dense(a, b)
            if not nonlinear:
                return xn
            delta = max((abs(xn[i] - x[i]) for i in range(len(x))), default=0.0)
            tol = max((abs(v) for v in xn), default=0.0) * 1e-6 + 1e-9
            x = xn
            if delta < tol and it > 0 and not limit_state["_limited"]:
                return x
        # Fallback: source stepping for hard nonlinear circuits.
        x = [0.0] * len(x0)
        limit_state = {}
        for step in range(1, 21):
            scale = step / 20.0
            for it in range(max_iter):
                limit_state["_limited"] = False
                a, b = self._assemble(index, nnodes, branch_idx, x, t, dt, mode, limit_state, scale)
                xn = _solve_dense(a, b)
                delta = max((abs(xn[i] - x[i]) for i in range(len(x))), default=0.0)
                x = xn
                if delta < max(abs(v) for v in xn) * 1e-6 + 1e-9 and not limit_state["_limited"]:
                    break
        return x

    def _results(self, index, nnodes, branch_idx, x, nodes, dt, mode):
        volts = {}
        for n in nodes:
            i = index[n]
            volts[n] = x[i] if i >= 0 else 0.0
        currents = {}
        extra = {}
        for el in self.elements:
            v = [volts[n] for n in el.nodes]
            if el.kind == "R":
                cur = (v[0] - v[1]) / el.value
            elif el.kind in ("V", "L"):
                cur = x[branch_idx[el.name]]
            elif el.kind == "I":
                cur = _value_at(el.value, self._t)
            elif el.kind == "C":
                if mode == "tran":
                    cur = el.value / dt * ((v[0] - v[1]) - el.state.get("v", el.params["v0"]))
                else:
                    cur = 0.0
            elif el.kind == "D":
                nvt = el.params["n"] * VT
                vd = v[0] - v[1]
                cur = el.params["i_s"] * (_safe_exp(vd / nvt) - 1.0)
            elif el.kind == "Q":
                p = el.params["polarity"]
                vbe, vbc = p * (v[1] - v[2]), p * (v[1] - v[0])
                i_s, bf, br = el.params["i_s"], el.params["bf"], el.params["br"]
                i_f, i_r = i_s * (_safe_exp(vbe / VT) - 1), i_s * (_safe_exp(vbc / VT) - 1)
                ic = p * (i_f - i_r - i_r / br)
                ib = p * (i_f / bf + i_r / br)
                cur = ic
                extra[el.name] = {"ic": ic, "ib": ib, "ie": -(ic + ib), "vbe": p * vbe, "vce": v[0] - v[2]}
            else:
                cur = 0.0
            currents[el.name] = cur
        return volts, currents, extra

    def _commit_state(self, volts, currents):
        for el in self.elements:
            v = [volts[n] for n in el.nodes]
            if el.kind == "C":
                el.state["v"] = v[0] - v[1]
            elif el.kind == "L":
                el.state["i"] = currents[el.name]
            elif el.kind == "D":
                el.state["vd"] = v[0] - v[1]
            elif el.kind == "Q":
                p = el.params["polarity"]
                el.state["vj"] = (p * (v[1] - v[2]), p * (v[1] - v[0]))

    def _prepare(self):
        index, nnodes, nodes = self._build_index()
        branch_idx = {}
        for el in self.elements:
            if el.kind in ("V", "L"):
                branch_idx[el.name] = nnodes + len(branch_idx)
        return index, nnodes, nodes, branch_idx

    def dc(self, t=0.0):
        """DC operating point. Returns {'voltages', 'currents', 'devices'}."""
        if not self.elements:
            return {"voltages": {}, "currents": {}, "devices": {}}
        for el in self.elements:
            el.state = {}
        self._t = t
        index, nnodes, nodes, branch_idx = self._prepare()
        x = self._newton(index, nnodes, branch_idx, [0.0] * (nnodes + len(branch_idx)), t, 1.0, "dc")
        volts, currents, extra = self._results(index, nnodes, branch_idx, x, nodes, 1.0, "dc")
        return {"voltages": volts, "currents": currents, "devices": extra}

    def transient(self, t_stop, dt=None, events=None, record_every=1, start_from_dc=False, on_event=None):
        """Backward-Euler transient analysis.

        events: list of (time, callable) executed before the step that reaches ``time``
        (use them to flip switches by changing a resistor value).
        Returns a list of snapshots {'t', 'voltages', 'currents', 'devices'}.
        """
        t_stop = float(t_stop)
        if dt is None:
            dt = t_stop / 1000.0
        dt = float(dt)
        if dt <= 0 or t_stop <= 0:
            raise SimulationError("t_stop and dt must be positive")
        events = sorted(events or [], key=lambda e: e[0])
        ev_i = 0
        while ev_i < len(events) and events[ev_i][0] <= 0.0:
            events[ev_i][1]()
            ev_i += 1
        index, nnodes, nodes, branch_idx = self._prepare()
        size = nnodes + len(branch_idx)
        for el in self.elements:
            el.state = {}
        if start_from_dc:
            op = self.dc(0.0)
            self._commit_state(op["voltages"], op["currents"])
        # t = 0 snapshot: a tiny step keeps capacitor voltages / inductor currents at their initial values.
        self._t = 0.0
        x = self._newton(index, nnodes, branch_idx, [0.0] * size, 0.0, dt * 1e-6, "tran")
        volts, currents, extra = self._results(index, nnodes, branch_idx, x, nodes, dt * 1e-6, "tran")
        out = [{"t": 0.0, "voltages": volts, "currents": currents, "devices": extra}]
        steps = int(math.ceil(t_stop / dt - 1e-9))
        t = 0.0
        for k in range(1, steps + 1):
            t_new = min(k * dt, t_stop)
            h = t_new - t
            while ev_i < len(events) and events[ev_i][0] <= t_new + 1e-15:
                events[ev_i][1]()
                ev_i += 1
            self._t = t_new
            x = self._newton(index, nnodes, branch_idx, x, t_new, h, "tran")
            volts, currents, extra = self._results(index, nnodes, branch_idx, x, nodes, h, "tran")
            self._commit_state(volts, currents)
            t = t_new
            if k % max(1, int(record_every)) == 0 or k == steps:
                out.append({"t": t, "voltages": volts, "currents": currents, "devices": extra})
        return out
