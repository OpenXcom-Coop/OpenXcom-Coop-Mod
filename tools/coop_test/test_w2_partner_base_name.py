"""W2-H65 S-A PBN (tools/coop_test/test_w2_partner_base_name.py): a partner base named after its marker appeared shows no name and opens
the partner's first base (L-TR6-1, ruling R-H65-0; F19200-F19210). Spec docs rewrite/prompts/w2h65_sa_name_follows.md (f) (stage S-A),
rewrite/prompts/w2h65_sb_no_rollback.md (stage S-B: the visit's 995 and rollback, never a cell here) and the common file
rewrite/prompts/w2h65_mirror_name_rollback.md (probe P0 globe_point); TASK 0 values in rewrite/w2h65-task0/sa/CONSTANTS.md.
In a SEPARATE campaign, when a player builds a base and the partner's geoscape re-inits while that player is still naming it, the partner's
marker (mirror) gets the name "" and keeps it: an unlabelled marker, a blank transfer-list row, a click that opens the player's FIRST base.
ONE boot (key K1). Bring-up B: spawn + connect both; session.new_campaign (host base at HOST_POS); geo.slow_clock; geo.drain_popups; the
window mapping per machine from INTERCEPT + its CANCEL (real clicks).
  Row R-2  host BASES, BUILD NEW BASE, one globe click at PICK (globe_point), OK -> BaseNameState, own base N2 "" [P2-1]; client INTERCEPT +
           CANCEL, WIN_S -> client mirror N2 "" [P2-2]; host NAME2 (key presses), OK, lift tile LIFT, GEOSCAPE.
    R-2a (RED) client mirror N2 named NAME2 at +READ_S after the lift.  R-2b (RED) the same after one more client INTERCEPT + CANCEL
    and WIN_S.  R-2c (GUARD) exactly one client mirror with id N2.
  Row R-1  both on GeoscapeState [P1-0]; the client builds N1 the same way [P1-1]; host INTERCEPT + CANCEL, WIN_S -> host mirror N1 ""
           [P1-2]; client NAME1, OK, LIFT, GEOSCAPE.
    R-1a (RED) host mirror N1 named NAME1 at +READ_S after the lift.  R-1b (RED) the same after one more host INTERCEPT + CANCEL and
    WIN_S.  R-1e (GUARD) exactly one host mirror with id N1.  R-1c (RED) host BASES, TRANSFER: screen_state rows hold NAME1, no "".
    R-1d (RED) the host's click on marker N1 (CLICK rule) -> BasescapeState within VISIT_S; geo_state.selectedBase (the open basescape's
    base, F19342) is NAME1. Then a CoopState on top closed by its own button, GEOSCAPE, session.wait_back_on_geoscape: EVIDENCE only.
  END   CRASH (GUARD): no crash file new in the lane's crash folder since the file start; both processes alive until their shutdown.
Red today: R-2a, R-2b, R-1a, R-1b, R-1c, R-1d FAIL; R-2c, R-1e, CRASH PASS. Green (EA1-EA4: every in-place mirror refresh takes the
marker's name): all PASS. R-1 runs last (QH65-A2 (a)).
mirrors = bases with coopIcon true; own = coopIcon and coopBase false. Every press is a real click_widget or inject_input (key or
click); no visit, leave, dismiss or dialog-back lever (the wait / LIFT / CLICK replacement rules log their swaps). One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict;
a precondition miss ends its row (CAPTURE line, cells "not reached"); a boot miss fails every cell "boot" with ONE CAPTURE line.
WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_w2_partner_base_name.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, math, os, subprocess, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo, harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir  # noqa: E402

K1 = "49231"
K2 = "49232"                                # TASK 0's key (rewrite/w2h65-task0/sa); this file runs on K1 only
HOST_POS = (0.90, -0.60)                    # rad: both bases on land, >= 0.15 rad apart
NAME1, NAME2 = "ltrnew", "hsnew"            # lowercase: inject_input key = unicode sym
LIFTS = ((2, 2), (3, 2), (2, 3), (3, 3))    # LIFT, then its replacement tiles in order
WIN_S, READ_S, STEP_CAP_S = 3.0, 2.0, 6.0   # +1 s steps up to STEP_CAP_S when the peer's reply is not handled yet
VISIT_S, VISIT_S2 = 20.0, 30.0
ZOOM_MIN, SYM_PLUS, SYM_ESC = 3, 43, 27
NEEDLES = ("coop-ui] push", "coop-ui] pop", "Save failed", "basehost", "LoadGame", "[coop-session]")
ROWS = (("R-2", ("R-2a", "R-2b", "R-2c")), ("R-1", ("R-1a", "R-1b", "R-1e", "R-1c", "R-1d")), ("END", ("CRASH",)))
RED = ("R-2a", "R-2b", "R-1a", "R-1b", "R-1c", "R-1d")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]

class Stop(Exception): pass  # noqa: E701 - a precondition missed: the row ends here

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
            "selectedBase": g.get("selectedBase"), "error": g.get("error")}
def own(c): return [[b[0], b[1]] for b in c["bases"] if not b[2] and not b[3]]
def mirrors(c): return [[b[0], b[1]] for b in c["bases"] if b[2]]
def mid(gc, nid): return [m for m in mirrors(census(gc)) if m[0] == nid]
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
def cw(gc, match, settle=1.0, ready=False):
    if ready:  # W2-U9 (F20796 / F20872): a POPUP window (InterceptState) drops a click on a hidden button
        session.wait_widget_ready(gc, match)
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
    return {"match": match, "ok": r.get("ok"), "err": r.get("error"), "base": [r.get("baseX"), r.get("baseY")],
            "win": [r.get("winX"), r.get("winY")], "after": stk(gc)}
def affine(r1, r2):
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
    """PICK: land >= 0.15 rad from every base / marker; rings 0.20-0.50 rad around the first base, 16 directions; 8 neighbours land"""
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
def settle(ev, name, pred, base, cap):
    time.sleep(base)
    waited = base
    while not pred() and waited < cap:
        time.sleep(1.0)
        waited += 1.0
    if waited > base:
        ev["swaps"].append("%s %.1f -> %.1f s" % (name, base, waited))
def capture(b):
    out = {}
    for gc in (b.host, b.client):
        w = q(gc, {"cmd": "list_widgets"}) if alive(gc) else {}
        out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None} if not alive(gc) else {
            "get_state": q(gc, {"cmd": "get_state"}), "get_coop": q(gc, {"cmd": "get_coop"}), "dialog": dlg(gc), "geo_state": census(gc),
            "screen_state": q(gc, {"cmd": "screen_state"}), "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-15:]],
            "widgets": [w.get("state")] + [[v.get("text"), v.get("visible")] for v in w.get("widgets", []) if v.get("text")]}
    return out
# ----- the boot, the rows and their construction steps -----
class Boot:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("w2h65a_host"))
        self.client = GameClient("client", None, make_user_dir("w2h65a_client"))
        self.aff = {}
class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now(), "cpu": cpu(), "swaps": []}
        self.n0 = [len(logl(b.host)), len(logl(b.client))] if b is not None else [0, 0]
    def cell(self, cid, ok, label): self.res[cid] = (bool(ok), label)
    def need(self, ok, what):
        if not ok: raise Stop(what)  # noqa: E701
    def finish(self, stop=None):
        self.ev["tEnd"] = now()
        if self.b is not None:
            self.ev["hostLog"], self.ev["clientLog"] = lines_since(self.b.host, self.n0[0]), lines_since(self.b.client, self.n0[1])
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
        b.aff[gc.name] = affine(cw(gc, "INTERCEPT", 0.6), cw(gc, "CANCEL", 0.6, ready=True))
    h, c = census(b.host), census(b.client)
    ev.update({"aff": b.aff, "host": h, "client": c})
    ok = (h["stack"] == ["GeoscapeState"] and c["stack"] == ["GeoscapeState"] and len(own(h)) == 1 and len(mirrors(h)) == 1
          and len(own(c)) == 1 and len(mirrors(c)) == 1)
    return ok, ev
def to_name_screen(b, r, gc, p):
    """BASES, BUILD NEW BASE, ONE globe click at PICK's land point, OK -> BaseNameState [p]; returns the new own base's id"""
    ev = r.ev[p] = {"bases": cw(gc, "BASES")["after"], "newBase": cw(gc, "NEW BASE")["after"]}
    r.need(top(gc) == "BuildNewBaseState", "%s: %s top %s after BUILD NEW BASE" % (p, gc.name, top(gc)))
    cc = census(gc)
    ev["pick"] = pick_point(gc, [(x[4], x[5]) for x in cc["bases"] if not x[2]] + [(x[4], x[5]) for x in cc["bases"] if x[2]])
    r.need(ev["pick"], "%s: no land point for PICK" % p)
    ev["globeClick"] = click_px(gc, ev["pick"]["x"], ev["pick"]["y"], b.aff[gc.name], "BuildNewBaseState")[-1]
    r.need(top(gc) == "ConfirmNewBaseState", "%s: %s top %s after the globe click" % (p, gc.name, top(gc)))
    ev["confirmOk"] = cw(gc, "OK")["after"]
    cc = census(gc)
    new = [x for x in own(cc) if x[1] == ""]
    ev.update({"t": now(), "own": own(cc), "stack": cc["stack"]})
    r.need(top(gc) == "BaseNameState" and len(new) == 1, "%s: %s on BaseNameState with one own base named \"\" (%s)" % (p, gc.name, ev))
    return new[0][0]
def cycle(gc): return [cw(gc, "INTERCEPT")["after"][-1:], cw(gc, "CANCEL", ready=True)["after"][-1:]]
def finish_name(b, r, gc, name, p):
    """NAME (key presses), OK -> PlaceLiftState, the lift tile (LIFT rule), GEOSCAPE"""
    for ch in name:
        key(gc, ord(ch))
        time.sleep(0.08)
    time.sleep(0.4)
    ev = r.ev[p] = {"nameOk": cw(gc, "OK")["after"], "lift": []}
    r.need(top(gc) == "PlaceLiftState", "%s: %s top %s after the name's OK" % (p, gc.name, top(gc)))
    for tx, ty in LIFTS:
        ev["lift"].append([tx, ty, click_px(gc, tx * 32 + 16, 8 + ty * 32 + 16, b.aff[gc.name], "PlaceLiftState", offsets=((0, 0),))[-1]["top"]])
        if top(gc) != "PlaceLiftState":
            break
        r.ev["swaps"].append("LIFT (%d, %d) did not leave PlaceLiftState" % (tx, ty))
    r.need(top(gc) != "PlaceLiftState", "%s: PlaceLiftState never left (%s)" % (p, ev["lift"]))
    ev["tLift"], ev["geo"] = now(), cw(gc, "GEOSCAPE")["after"]
    r.need(top(gc) == "GeoscapeState", "%s: %s not back on GeoscapeState (%s)" % (p, gc.name, stk(gc)))
def row_r2(b, r):
    """R-2 (S-A stage file (f)): the host builds a base; the client's mirror"""
    h, c, ev = b.host, b.client, r.ev
    n2 = ev["N2"] = to_name_screen(b, r, h, "P2-1")
    ev["clientCycle"] = cycle(c)
    settle(ev, "WIN_S", lambda: mid(c, n2), WIN_S, STEP_CAP_S)
    m = mid(c, n2)
    ev["P2-2"] = {"t": now(), "clientMirrorN2": m, "client": census(c)["bases"], "host": census(h)["bases"]}
    r.need(m == [[n2, ""]], "P2-2: client mirror N2 \"\" after the client's geoscape init (%s)" % m)
    finish_name(b, r, h, NAME2, "hostName")
    settle(ev, "READ_S", lambda: mid(c, n2), READ_S, STEP_CAP_S)
    m = mid(c, n2)
    ev["R-2a"] = {"t": now(), "clientMirrorN2": m, "client": census(c)["bases"], "host": census(h)["bases"]}
    r.cell("R-2a", m == [[n2, NAME2]], "client mirror N2 %s at +READ_S after the lift: %s (want name %r)" % (n2, m, NAME2))
    ev["clientCycle2"] = cycle(c)
    settle(ev, "WIN_S", lambda: mid(c, n2), WIN_S, STEP_CAP_S)
    m = mid(c, n2)
    ev["R-2b"] = {"t": now(), "clientMirrorN2": m, "client": census(c)["bases"], "host": census(h)["bases"]}
    r.cell("R-2b", m == [[n2, NAME2]], "client mirror N2 %s after one more client geoscape init: %s (want name %r)" % (n2, m, NAME2))
    r.cell("R-2c", len(m) == 1, "client mirrors with id N2 %s: %s (want exactly one)" % (n2, m))
def click_mirror(b, r, m):
    """CLICK rule: right-click the marker to centre, '+' to ZOOM_MIN, left-click it; else P0's view move / ESC, '+', re-click (logged)"""
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
def row_r1(b, r):
    """R-1 (S-A stage file (f)): the client builds a base; the host's mirror, transfer list and click"""
    h, c, ev = b.host, b.client, r.ev
    r.need(stk(h) == ["GeoscapeState"] and stk(c) == ["GeoscapeState"], "P1-0: both on GeoscapeState (%s, %s)" % (stk(h), stk(c)))
    n1 = ev["N1"] = to_name_screen(b, r, c, "P1-1")
    ev["hostCycle"] = cycle(h)
    settle(ev, "WIN_S", lambda: mid(h, n1), WIN_S, STEP_CAP_S)
    m = mid(h, n1)
    ev["P1-2"] = {"t": now(), "hostMirrorN1": m, "host": census(h)["bases"], "client": census(c)["bases"]}
    r.need(m == [[n1, ""]], "P1-2: host mirror N1 \"\" after the host's geoscape init (%s)" % m)
    finish_name(b, r, c, NAME1, "clientName")
    settle(ev, "READ_S", lambda: mid(h, n1), READ_S, STEP_CAP_S)
    m = mid(h, n1)
    ev["R-1a"] = {"t": now(), "hostMirrorN1": m, "host": census(h)["bases"], "client": census(c)["bases"]}
    r.cell("R-1a", m == [[n1, NAME1]], "host mirror N1 %s at +READ_S after the lift: %s (want name %r)" % (n1, m, NAME1))
    ev["hostCycle2"] = cycle(h)
    settle(ev, "WIN_S", lambda: mid(h, n1), WIN_S, STEP_CAP_S)
    hc = census(h)
    m = [x for x in mirrors(hc) if x[0] == n1]
    ev["R-1b"] = {"t": now(), "hostMirrorN1": m, "host": hc["bases"], "selectedBase": hc["selectedBase"], "client": census(c)["bases"]}
    r.cell("R-1b", m == [[n1, NAME1]], "host mirror N1 %s after one more host geoscape init: %s (want name %r)" % (n1, m, NAME1))
    r.cell("R-1e", len(m) == 1, "host mirrors with id N1 %s: %s (want exactly one)" % (n1, m))
    tr = ev["R-1c"] = {"bases": cw(h, "BASES")["after"]}
    r.need(top(h) == "BasescapeState", "R-1c: host top %s after BASES" % top(h))
    tr["transfer"] = cw(h, "TRANSFER")["after"]
    tr["screen"] = {k: v for k, v in q(h, {"cmd": "screen_state"}).items() if k in ("top", "rows", "error")}
    r.need(tr["screen"].get("top") == "transfer_base", "R-1c: the host's TRANSFER list not on top (%s)" % tr)
    rows = tr["screen"].get("rows") or []
    r.cell("R-1c", NAME1 in rows and "" not in rows, "host transfer rows %s (want %r in, \"\" not in)" % (rows, NAME1))
    tr["cancel"], tr["geo"] = cw(h, "CANCEL")["after"], cw(h, "GEOSCAPE")["after"]
    ph, pc = census(h), census(c)
    mm = [x for x in ph["bases"] if x[0] == n1 and x[2]]
    pre = ev["PRE"] = {"t": now(), "F0": ph["funds"], "T0": ph["time"], "C0": pc["time"], "hostOwn": own(ph), "hostMirrors": mirrors(ph),
                       "selectedBase": ph["selectedBase"], "stacks": [ph["stack"], pc["stack"]]}
    r.need(ph["stack"] == ["GeoscapeState"] and len(mm) == 1, "R-1d: host on GeoscapeState with marker N1 shown (%s)" % pre)
    ev["click"] = click_mirror(b, r, [mm[0][0], mm[0][1], mm[0][4], mm[0][5]])
    trace, t1, bs_at, sel = [], time.time(), None, []
    while time.time() - t1 < VISIT_S2 + 3.0:
        st = stk(h)
        e = [st[-1] if st else None] + ([dlg(h).get("code")] if st[-1:] == ["CoopState"] else [])
        if not trace or trace[-1][1:] != e:
            trace.append([round(time.time() - t1, 2)] + e)
        if bs_at is None and "BasescapeState" in st:
            bs_at = time.time()
            sel.append(["first", q(h, {"cmd": "geo_state"}).get("selectedBase")])
        if (bs_at and time.time() - bs_at >= 3.0) or (bs_at is None and time.time() - t1 >= VISIT_S2):
            break
        time.sleep(0.1)
    g = q(h, {"cmd": "geo_state"})
    sel.append(["+3s", g.get("selectedBase"), stk(h)])  # the cell's read: BasescapeState + 3 s
    seen = [e for t in ev["click"]["tries"] for e in t["seen"]]
    ev["visit"] = {"trace": trace, "bsAt": round(bs_at - t1, 2) if bs_at else None, "selectedBase": sel,
                   "codes": sorted(set(e[1] for e in seen + [x[1:] for x in trace] if len(e) > 1 and e[1] is not None)),
                   "visitBases": [[x.get("coopBaseId"), x.get("name"), x.get("coopIcon"), x.get("coopBase")] for x in g.get("bases", [])],
                   "insideCoopBase": q(h, {"cmd": "get_coop"}).get("insideCoopBase")}
    ev["swaps"] += ["VISIT_S %.0f -> %.0f s" % (VISIT_S, VISIT_S2)] if bs_at and bs_at - t1 > VISIT_S else []
    r.need(bs_at is not None, "R-1d: no BasescapeState within VISIT_S (%s)" % trace)
    r.cell("R-1d", "BasescapeState" in sel[-1][2] and sel[-1][1] == NAME1,
           "host selectedBase with BasescapeState in the stack: %s (want %r)" % (sel[-1][1], NAME1))
    back = ev["back"] = {"close": []}  # EVIDENCE only from here (S-B's subject: the 995, the funds / time after the visit)
    while top(h) == "CoopState" and len(back["close"]) < 3:
        d = dlg(h)
        r.need(d.get("backText"), "R-1d: a CoopState on top without a button (%s)" % d)
        back["close"].append([d.get("code"), d.get("backText"), cw(h, d["backText"])["after"]])
    back["geo"] = cw(h, "GEOSCAPE")["after"]
    try:
        back["back"] = bool(session.wait_back_on_geoscape(h, "host back on its own geoscape"))
    except Exception as e:  # noqa: BLE001
        back["back"] = "%s: %s" % (type(e).__name__, str(e)[:300])
    time.sleep(2.0)
    qh, qc = census(h), census(c)
    back.update({"t": now(), "F1": qh["funds"], "T1": qh["time"], "C1": qc["time"], "host": qh["bases"], "stacks": [qh["stack"], qc["stack"]]})
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
            for cid in ROWS[0][1] + ROWS[1][1]:
                print("FAIL %s %s: boot" % (cid, "RED" if cid in RED else "GUARD"), flush=True)
                x.fails.append(cid)
        else:
            for rid, fn in (("R-2", row_r2), ("R-1", row_r1)):
                r = Row(x, b, rid)
                try:
                    fn(b, r)
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
    print("SUMMARY W2-H65 S-A PBN: %d/%d cells pass; failing %s; wall %.1f s" % (len(cl) - len(set(x.fails)), len(cl),
                                                                               sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
