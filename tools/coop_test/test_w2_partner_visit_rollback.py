"""W2-H65 S-B PVR (tools/coop_test/test_w2_partner_visit_rollback.py): visiting a partner base whose marker is still unnamed shows
"Save failed (MEMORY)" and rolls the visitor's world back (L-LTR61C-1, ruling R-H65-0; F19204, F19205). Spec docs
rewrite/prompts/w2h65_sb_no_rollback.md (f) (stage S-B), bring-up B and the PINNED SETUP VALUES of rewrite/prompts/w2h65_sa_name_follows.md
(f) (stage S-A), and the common file rewrite/prompts/w2h65_mirror_name_rollback.md (probe P0 globe_point); TASK 0 values in
rewrite/w2h65-task0/sb/CONSTANTS.md.
In a SEPARATE campaign the host's marker for a client base built while the client is still naming it keeps the name "". While it exists,
saveCoopToMemory refuses every save of the host's own world (its check reads markers it never writes): the host's click on that marker
(the visit) raises 995 "Save failed (MEMORY), please try again." and leaving the base reloads the session-start "basehost" snapshot.
ONE boot (key K1). Bring-up B: spawn + connect both; session.new_campaign (host base at HOST_POS); geo.slow_clock; geo.drain_popups; the
window mapping per machine from INTERCEPT + its CANCEL (real clicks); TS0 = the host geo_state time.
  Row R-3  client BASES, BUILD NEW BASE, one globe click at PICK (globe_point), OK -> BaseNameState, own base N1 "" [P3-0]; host INTERCEPT +
           CANCEL, WIN_S -> host marker N1 ""; client NAME1 (key presses), OK, lift tile LIFT, GEOSCAPE; READ_S -> host marker N1 still ""
           [P3-1]; host time >= TS0 + GAP_MIN [P3-2]; PRE (F0 host funds, T0 host time, C0 client time, host own bases) on GeoscapeState;
           the host's click on marker N1 (CLICK rule); DLG = every top state and CoopState code until BasescapeState + 3 s; a CoopState on
           top closed by its own button; host GEOSCAPE; session.wait_back_on_geoscape; POST_S; POST (F1, T1, C1, host bases) on GeoscapeState.
    R-3a (RED)   DLG holds no CoopState 995.
    R-3b (RED)   F1 == F0 (the host's funds kept).
    R-3c (RED)   T1 >= T0 (the host's clock never runs back).
    R-3d (RED)   C1 >= C0 (the client's clock never runs back).
    R-3e (GUARD) the host's own bases after == before (ids and names).
    R-3f (GUARD) the host shows exactly one marker with id N1 after.
  END   CRASH (GUARD): no crash file new in the lane's crash folder since the file start; both processes alive until their shutdown.
Red today: R-3a, R-3b, R-3c, R-3d FAIL; R-3e, R-3f, CRASH PASS. Green (EB1: the check skips markers): all PASS.
mirrors = geo_state bases with coopIcon true; own = coopIcon and coopBase false. Every press is a real click_widget or inject_input (key
or click); no visit, leave, dismiss or dialog-back lever. One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict;
a precondition miss ends the row (CAPTURE line, cells "not reached"); a boot miss fails every R-3 cell "boot" with ONE CAPTURE line.
WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_w2_partner_visit_rollback.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, math, os, subprocess, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

K1 = "49233"
K2 = "49234"                                # TASK 0's key (rewrite/w2h65-task0/sb); this file runs on K1 only
HOST_POS = (0.90, -0.60)                    # rad: both bases on land, >= 0.15 rad apart
NAME1 = "ltrnew"                            # lowercase: inject_input key = unicode sym
LIFTS = ((2, 2), (3, 2), (2, 3), (3, 3))    # LIFT, then its replacement tiles in order
WIN_S, READ_S, STEP_CAP_S = 3.0, 2.0, 6.0   # +1 s steps up to STEP_CAP_S when the peer's reply is not handled yet
GAP_MIN, GAP_POLL_S, GAP_STEP_S = 10, 60.0, 30.0
VISIT_S, VISIT_S2 = 20.0, 30.0
POST_S, POST_CAP_S = 2.0, 5.0
ZOOM_MIN, SYM_PLUS, SYM_ESC = 3, 43, 27
NEEDLES = ("coop-ui] push", "coop-ui] pop", "Save failed", "basehost", "LoadGame", "[coop-session]")
ROWS = (("R-3", ("R-3a", "R-3b", "R-3c", "R-3d", "R-3e", "R-3f")), ("END", ("CRASH",)))
RED = ("R-3a", "R-3b", "R-3c", "R-3d")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]

class Stop(Exception):  # a precondition missed: the row ends here
    pass

# ----- probes and real input (copied from the capture rewrite/ltr6-1-cap/cap.py, never imported; ltr_globe -> P0 globe_point) -----
def js(v): return json.dumps(v, sort_keys=True, default=str)
def now(): return round(time.time() - T0[0], 2)
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))
def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001
        return {"error": ("%s: %s" % (type(e).__name__, e))[:200]}
def stk(gc):
    r = q(gc, {"cmd": "get_state"})
    return [s.split("::")[-1] for s in r["states"]] if "states" in r else ["probe failed: %s" % r.get("error")]
def top(gc): return (stk(gc) or [None])[-1]
def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("code", "title", "backText", "backVisible", "error") if k in r}
def census(gc):
    g = q(gc, {"cmd": "geo_state"})
    bl = [[b.get("coopBaseId"), b.get("name"), bool(b.get("coopIcon")), bool(b.get("coopBase")), round(b.get("lon", 0), 5),
           round(b.get("lat", 0), 5)] for b in g.get("bases", [])]
    return {"bases": bl, "funds": g.get("funds"), "time": geo._abs_minutes(g["time"]) if g.get("time") else None, "stack": stk(gc),
            "error": g.get("error")}
def own(c): return [[b[0], b[1]] for b in c["bases"] if not b[2] and not b[3]]
def mirrors(c): return [[b[0], b[1]] for b in c["bases"] if b[2]]
def cpu():
    ps = ("[math]::Round(((Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 2).CounterSamples | "
          "Measure-Object -Property CookedValue -Average).Average, 1); @(Get-Process | Where-Object { $_.ProcessName -like 'Wardogs*' }).Count")
    try:
        v = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout.split()
        return {"t": time.strftime("%H:%M:%S"), "cpu": v[0] if v else None, "wardogs": v[1] if len(v) > 1 else None}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)[:120]}
def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def lines_since(gc, n0): return [ln.split("\t")[0][-13:-1] + " " + ln.split("\t")[-1][:300] for ln in logl(gc)[n0:] if any(n in ln for n in NEEDLES)]
def cw(gc, match, settle=1.0):
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
    return {"match": match, "ok": r.get("ok"), "err": r.get("error"), "base": [r.get("baseX"), r.get("baseY")],
            "win": [r.get("winX"), r.get("winY")], "after": stk(gc)}
def affine(r1, r2):
    """window = s * base + o per axis, from two click_widget replies (base / window centres)"""
    out = [(r1["win"][i] - r2["win"][i]) / (r1["base"][i] - r2["base"][i]) if r1["base"][i] != r2["base"][i] else None for i in (0, 1)]
    sc = round(out[0] or out[1], 3)
    return (sc, r1["win"][0] - sc * r1["base"][0], sc, r1["win"][1] - sc * r1["base"][1])
def key(gc, sym): return q(gc, {"cmd": "inject_input", "kind": "key", "key": sym})
def click_px(gc, bx, by, sc, until_not, offsets=((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2))):
    """real clicks at base pixel (bx, by) + offsets through the window mapping until the top leaves `until_not`"""
    tries = []
    for dx, dy in offsets:
        wx, wy = int(round(sc[0] * (bx + dx) + sc[1])), int(round(sc[2] * (by + dy) + sc[3]))
        q(gc, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy})
        seen, t4 = [], time.time()
        while time.time() - t4 < 1.0:
            t = top(gc)
            e = [t] + ([dlg(gc).get("code")] if t == "CoopState" else [])
            if not seen or seen[-1] != e:
                seen.append(e)
            time.sleep(0.05)
        tries.append({"base": [bx + dx, by + dy], "win": [wx, wy], "seen": seen, "top": top(gc)})
        if tries[-1]["top"] != until_not:
            break
    return tries
def globe(gc, **kw): return q(gc, dict({"cmd": "globe_point"}, **kw))
def dist(a, b): return math.hypot((a[0] - b[0] + math.pi) % (2 * math.pi) - math.pi, a[1] - b[1])
def pick_point(gc, avoid):
    """PICK: nearest land point on the visible globe >= 0.15 rad from every base and marker; rings 0.20-0.50 rad step 0.05 around the
    builder's first base, 16 directions; the point and its 8 neighbours at 0.02 rad land; inside the globe rect (10 px margin)."""
    c = avoid[0]
    for r in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
        for k in range(16):
            p = (c[0] + r * math.cos(2 * math.pi * k / 16), c[1] + r * math.sin(2 * math.pi * k / 16))
            if any(dist(p, b) < 0.15 for b in avoid):
                continue
            pr = globe(gc, lon=p[0], lat=p[1])
            if not pr.get("land"):
                continue
            nb = [globe(gc, lon=p[0] + dx, lat=p[1] + dy).get("land") for dx in (-0.02, 0, 0.02) for dy in (-0.02, 0, 0.02)]
            if all(nb) and 10 < pr["x"] < pr["globeW"] - 10 and 30 < pr["y"] < pr["globeH"] - 10:
                return {"lon": p[0], "lat": p[1], "x": pr["x"], "y": pr["y"], "r": r, "k": k}
    return None
def n1m(gc, nid): return [m for m in mirrors(census(gc)) if m[0] == nid]
def settle(ev, name, pred, base, cap):
    """wait `base` s, then +1 s steps up to `cap` s until pred() (the pinned wait's replacement rule; a longer wait is logged)"""
    time.sleep(base)
    waited = base
    while not pred() and waited < cap:
        time.sleep(1.0)
        waited += 1.0
    if waited > base:
        ev["swaps"].append("%s %.1f -> %.1f s" % (name, base, waited))
def capture(b):
    """every live machine's probes and log tail (the FIXTURE-STOP dump)"""
    out = {}
    for gc in (b.host, b.client):
        if not alive(gc):
            out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None}
            continue
        w = q(gc, {"cmd": "list_widgets"})
        out[gc.name] = {"get_state": q(gc, {"cmd": "get_state"}), "get_coop": q(gc, {"cmd": "get_coop"}), "dialog": dlg(gc), "geo_state": census(gc),
                        "widgets": [w.get("state")] + [[v.get("text"), v.get("visible")] for v in w.get("widgets", []) if v.get("text")],
                        "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-15:]]}
    return out

# ----- the boot and the row -----
class Boot:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("w2h65b_r3_host"))
        self.client = GameClient("client", None, make_user_dir("w2h65b_r3_client"))
        self.aff, self.ts0 = {}, None
class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now(), "cpu": cpu(), "swaps": []}
        self.n0 = len(logl(b.host)) if b is not None else 0
    def cell(self, cid, ok, label):
        self.res[cid] = (bool(ok), label)
    def need(self, ok, what):
        if not ok:
            raise Stop(what)
    def finish(self, stop=None):
        self.ev["tEnd"] = now()
        if self.b is not None:
            self.ev["hostLog"] = lines_since(self.b.host, self.n0)
        if stop:
            self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails = []
        for cid in dict(ROWS)[self.rid]:
            ok, label = self.res.get(cid, (False, "not reached (%s)" % stop))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "RED" if cid in RED else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails
def bring_up(b):
    """Bring-up B (S-A stage file (f)): one SEPARATE campaign, both on GeoscapeState, the window mapping per machine"""
    for gc in (b.host, b.client):
        gc.spawn()
        gc.connect(timeout=240)
    session.HOST_LON, session.HOST_LAT = HOST_POS
    session.new_campaign(b.host, b.client, port=K1)
    geo.slow_clock(b.host, b.client)
    time.sleep(2.0)
    ev = {"drain": [str(geo.drain_popups(gc))[:120] for gc in (b.host, b.client)]}
    for gc in (b.host, b.client):
        b.aff[gc.name] = affine(cw(gc, "INTERCEPT", 0.6), cw(gc, "CANCEL", 0.6))
    h, c = census(b.host), census(b.client)
    b.ts0 = h["time"]
    ev.update({"aff": b.aff, "TS0": b.ts0, "host": h, "client": c})
    ok = (h["stack"] == ["GeoscapeState"] and c["stack"] == ["GeoscapeState"] and len(own(h)) == 1 and len(mirrors(h)) == 1
          and len(own(c)) == 1 and b.ts0 is not None)
    return ok, ev
def click_mirror(b, r, m):
    """CLICK rule: right-click the marker's pixel to centre (real input), '+' until zoom >= ZOOM_MIN, left-click its pixel (click_px
    offsets). Replacement: pixel outside the globe rect or no centre -> P0's centerLon / centerLat view move; a MultipleTargetsState
    left on top -> ESC, one more '+', re-click (logged)."""
    h, sc, (lon, lat) = b.host, b.aff["host"], (m[2], m[3])
    out = {"g0": globe(h, lon=lon, lat=lat)}
    g = out["g0"]
    centred = False
    if g.get("ok") and 10 < g["x"] - g["globeX"] < g["globeW"] - 10 and 10 < g["y"] - g["globeY"] < g["globeH"] - 10:
        wx, wy = int(round(sc[0] * g["x"] + sc[1])), int(round(sc[2] * g["y"] + sc[3]))
        out["right"] = [wx, wy, q(h, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy, "button": "right"}).get("ok")]
        time.sleep(0.8)
        g1 = globe(h)
        out["cen"] = [g1.get("cenLon"), g1.get("cenLat")]
        centred = g1.get("cenLon") is not None and dist((g1["cenLon"], g1["cenLat"]), (lon, lat)) < 0.05
    if not centred:
        g1 = globe(h, centerLon=lon, centerLat=lat)
        r.ev["swaps"].append("CLICK: no right-click centre (%s) -> P0 view move to (%s, %s)" % (out.get("cen"), g1.get("cenLon"), g1.get("cenLat")))
    zs = [globe(h).get("zoom")]
    while (zs[-1] or 0) < ZOOM_MIN and len(zs) < 7:
        key(h, SYM_PLUS)
        time.sleep(0.6)
        zs.append(globe(h).get("zoom"))
    g2 = globe(h, lon=lon, lat=lat)
    out.update({"zooms": zs, "px": [g2.get("x"), g2.get("y")], "tClick": now()})
    out["tries"] = click_px(h, g2["x"], g2["y"], sc, "GeoscapeState")
    if top(h) == "MultipleTargetsState":
        for k in (SYM_ESC, SYM_PLUS):
            key(h, k)
            time.sleep(0.6)
        g3 = globe(h, lon=lon, lat=lat)
        r.ev["swaps"].append("CLICK: MultipleTargetsState on top -> ESC, '+' (zoom %s), re-click" % g3.get("zoom"))
        out["tries"] += click_px(h, g3["x"], g3["y"], sc, "GeoscapeState")
    return out
def row_r3(b, r):
    """R-3 (S-B stage file (f)): the client builds a base, the host visits its unnamed marker"""
    h, c, ev = b.host, b.client, r.ev
    ev["clientBases"], ev["clientNewBase"] = cw(c, "BASES")["after"], cw(c, "NEW BASE")["after"]
    r.need(top(c) == "BuildNewBaseState", "P3-0: client top %s after BUILD NEW BASE" % top(c))
    cc = census(c)
    pick = ev["pick"] = pick_point(c, [(x[4], x[5]) for x in cc["bases"] if not x[2]] + [(x[4], x[5]) for x in cc["bases"] if x[2]])
    r.need(pick, "P3-0: no land point for PICK")
    ev["globeClick"] = click_px(c, pick["x"], pick["y"], b.aff["client"], "BuildNewBaseState")
    r.need(top(c) == "ConfirmNewBaseState", "P3-0: client top %s after the globe click" % top(c))
    ev["confirmOk"] = cw(c, "OK")["after"]
    cc = census(c)
    new = [x for x in own(cc) if x[1] == ""]
    ev["P3-0"] = {"t": now(), "clientOwn": own(cc), "stack": cc["stack"]}
    r.need(top(c) == "BaseNameState" and len(new) == 1, "P3-0: client on BaseNameState with one own base named \"\" (%s, %s)" % (top(c), own(cc)))
    n1 = ev["N1"] = new[0][0]
    ev["hostCycle"] = [cw(h, "INTERCEPT")["after"][-1:], cw(h, "CANCEL")["after"][-1:]]
    settle(ev, "WIN_S", lambda: n1m(h, n1), WIN_S, STEP_CAP_S)
    m = n1m(h, n1)
    ev["window"] = {"t": now(), "mirrorN1": m, "hostMirrors": mirrors(census(h))}
    r.need(m == [[n1, ""]], "host marker N1 \"\" after the host's geoscape init (%s)" % m)
    for ch in NAME1:
        key(c, ord(ch))
        time.sleep(0.08)
    time.sleep(0.4)
    ev["nameOk"] = cw(c, "OK")["after"]
    r.need(top(c) == "PlaceLiftState", "client top %s after the name's OK" % top(c))
    ev["lift"] = []
    for tx, ty in LIFTS:
        ev["lift"].append([tx, ty, click_px(c, tx * 32 + 16, 8 + ty * 32 + 16, b.aff["client"], "PlaceLiftState", offsets=((0, 0),))[-1]["top"]])
        if top(c) != "PlaceLiftState":
            break
        ev["swaps"].append("LIFT (%d, %d) did not leave PlaceLiftState" % (tx, ty))
    r.need(top(c) != "PlaceLiftState", "PlaceLiftState never left (%s)" % ev["lift"])
    ev["clientGeo"] = cw(c, "GEOSCAPE")["after"]
    r.need(top(c) == "GeoscapeState", "client not back on GeoscapeState (%s)" % stk(c))
    settle(ev, "READ_S", lambda: n1m(h, n1), READ_S, STEP_CAP_S)
    m = n1m(h, n1)
    ev["P3-1"] = {"t": now(), "mirrorN1": m, "clientOwn": own(census(c))}
    r.need(m == [[n1, ""]], "P3-1: host marker N1 still \"\" after the lift (%s)" % m)
    t0w, gap, stepped = time.time(), [], False
    while time.time() - t0w < GAP_POLL_S + GAP_STEP_S:
        gap.append([round(time.time() - t0w, 1), census(h)["time"]])
        if gap[-1][1] is not None and gap[-1][1] >= b.ts0 + GAP_MIN:
            break
        if not stepped and time.time() - t0w >= GAP_POLL_S:  # GAP_MIN's rule: one speed step up, back to the slow clock before the click
            stepped = [q(gc, {"cmd": "geo_set_speed", "idx": 1}) for gc in (h, c)]
            ev["swaps"].append("GAP_MIN not met at the slow clock in %.0f s -> speed idx 1" % GAP_POLL_S)
        time.sleep(1.0)
    if stepped:
        geo.slow_clock(h, c)
    ev["P3-2"] = {"TS0": b.ts0, "polls": len(gap), "last": gap[-1]}
    r.need(gap[-1][1] is not None and gap[-1][1] >= b.ts0 + GAP_MIN, "P3-2: host time %s < TS0 %s + GAP_MIN" % (gap[-1][1], b.ts0))
    ph, pc = census(h), census(c)
    m = [x for x in ph["bases"] if x[0] == n1 and x[2]]
    ev["PRE"] = {"t": now(), "F0": ph["funds"], "T0": ph["time"], "C0": pc["time"], "hostOwn": own(ph), "hostMirrors": mirrors(ph),
                 "stacks": [ph["stack"], pc["stack"]]}
    r.need(ph["stack"] == ["GeoscapeState"] and pc["stack"] == ["GeoscapeState"] and len(m) == 1, "PRE: both on GeoscapeState, marker N1 shown")
    ev["click"] = click_mirror(b, r, [m[0][0], m[0][1], m[0][4], m[0][5]])
    trace, t1, bs_at = [], time.time(), None
    while time.time() - t1 < VISIT_S2 + 3.0:
        st = stk(h)
        e = [st[-1] if st else None] + ([dlg(h).get("code")] if st[-1:] == ["CoopState"] else [])
        if not trace or trace[-1][1:] != e:
            trace.append([round(time.time() - t1, 2)] + e)
        if bs_at is None and "BasescapeState" in st:
            bs_at = time.time()
        if (bs_at and time.time() - bs_at >= 3.0) or (bs_at is None and time.time() - t1 >= VISIT_S2):
            break
        time.sleep(0.1)
    seen = [e for t in ev["click"]["tries"] for e in t["seen"]]
    codes = sorted(set(e[1] for e in seen + [x[1:] for x in trace] if len(e) > 1 and e[1] is not None))
    ev["DLG"] = {"seen": seen, "trace": trace, "codes": codes, "bsAt": round(bs_at - t1, 2) if bs_at else None, "stack": stk(h),
                 "insideCoopBase": q(h, {"cmd": "get_coop"}).get("insideCoopBase")}
    if bs_at and bs_at - t1 > VISIT_S:
        ev["swaps"].append("VISIT_S %.0f -> %.0f s" % (VISIT_S, VISIT_S2))
    r.need(bs_at is not None, "no BasescapeState within VISIT_S (%s)" % trace)
    ev["close"] = []
    for _ in range(3):
        if top(h) != "CoopState":
            break
        d = dlg(h)
        r.need(d.get("backText"), "a CoopState on top without a button (%s)" % d)
        ev["close"].append([d.get("code"), d.get("backText"), cw(h, d["backText"])["after"]])
    ev["hostGeo"] = cw(h, "GEOSCAPE")["after"]
    try:
        session.wait_back_on_geoscape(h, "host back on its own geoscape")
    except Exception as e:  # noqa: BLE001
        raise Stop("host not back on its own geoscape: %s" % str(e)[:300])
    settle(ev, "POST_S", lambda: mirrors(census(h)), POST_S, POST_CAP_S)  # the reload and the next coopBase3 handled
    qh, qc = census(h), census(c)
    ev["POST"] = {"t": now(), "F1": qh["funds"], "T1": qh["time"], "C1": qc["time"], "hostOwn": own(qh), "hostMirrors": mirrors(qh),
                  "stacks": [qh["stack"], qc["stack"]]}
    r.need(qh["stack"] == ["GeoscapeState"] and qc["stack"] == ["GeoscapeState"], "POST: both on GeoscapeState (%s)" % ev["POST"]["stacks"])
    pre, post = ev["PRE"], ev["POST"]
    r.cell("R-3a", 995 not in codes, "CoopState codes from the click to BasescapeState + 3 s: %s (want no 995)" % codes)
    r.cell("R-3b", post["F1"] == pre["F0"], "host funds F0 %s -> F1 %s (want equal)" % (pre["F0"], post["F1"]))
    r.cell("R-3c", post["T1"] is not None and pre["T0"] is not None and post["T1"] >= pre["T0"],
           "host time T0 %s -> T1 %s (want T1 >= T0; TS0 %s)" % (pre["T0"], post["T1"], b.ts0))
    r.cell("R-3d", post["C1"] is not None and pre["C0"] is not None and post["C1"] >= pre["C0"],
           "client time C0 %s -> C1 %s (want C1 >= C0)" % (pre["C0"], post["C1"]))
    r.cell("R-3e", post["hostOwn"] == pre["hostOwn"], "host own bases before %s, after %s (want equal)" % (pre["hostOwn"], post["hostOwn"]))
    n1_after = [x for x in post["hostMirrors"] if x[0] == n1]
    r.cell("R-3f", len(n1_after) == 1, "host markers with id N1 %s after: %s (want exactly one)" % (n1, n1_after))

class X:  # the file's run state: failing cells, every process's alive-until-shutdown record
    def __init__(self): self.fails, self.alive = [], []
def main():
    x, crash0, b = X(), crashes(), None
    T0[0] = time.time()
    try:
        b = Boot()
        ev = {"key": K1, "slot": harness.HARNESS_SLOT, "cpu": cpu(), "t": now()}
        try:
            ok, bev = bring_up(b)
            ev.update(bev)
        except Exception as e:  # noqa: BLE001 - a boot that raises is a boot miss
            ok, ev["error"] = False, ("%s: %s" % (type(e).__name__, e))[:400]
        print("EVIDENCE boot: %s" % js(ev), flush=True)
        if not ok:
            print("CAPTURE boot: %s" % js(capture(b)), flush=True)
            for cid in dict(ROWS)["R-3"]:
                print("FAIL %s %s: boot" % (cid, "RED" if cid in RED else "GUARD"), flush=True)
                x.fails.append(cid)
        else:
            r = Row(x, b, "R-3")
            try:
                row_r3(b, r)
                r.finish()
            except Stop as e:
                r.finish(str(e))
            except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
                r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        for gc in ((b.client, b.host) if b else ()):
            x.alive.append([gc.name, alive(gc)])
            try:
                if alive(gc):
                    gc.shutdown(expected_returncodes=OKRC)
            except Exception as e:  # noqa: BLE001
                print("FAIL shutdown %s: %s" % (gc.name, str(e)[:300]), flush=True)
                x.alive[-1][1] = False
        r, new = Row(x, None, "END"), sorted(crashes() - crash0)
        r.ev.update({"newCrash": [os.path.basename(p) for p in new], "aliveUntilShutdown": x.alive, "crashDir": harness.CRASH_DIR})
        r.cell("CRASH", not new and x.alive and all(a[1] for a in x.alive),
               "new crash files %d %s; alive until shutdown %s" % (len(new), r.ev["newCrash"][:3], x.alive))
        r.finish()
    cl = [cid for _r, cs in ROWS for cid in cs]
    print("SUMMARY W2-H65 S-B PVR: %d/%d cells pass; failing %s; wall %.1f s" % (len(cl) - len(set(x.fails)), len(cl),
                                                                               sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
