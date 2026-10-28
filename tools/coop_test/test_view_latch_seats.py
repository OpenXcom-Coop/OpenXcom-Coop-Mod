"""W2-H85 VLS - tools/coop_test/test_view_latch_seats.py: every visit of the partner's base re-seats the visitor's soldiers on the partner's
craft, however the last base screen was left (L-H83-2; ruling R-LH83-2-1; veto line VL-H85-1).
In a SEPARATE campaign a guest's seat on the partner's craft lives in the visitor's own world (coopCraft); BasescapeState::init re-seats the guests in a
view behind the process-wide latch _coop_base_init, which only the base screen's GEOSCAPE clears. After BUILD NEW BASE, a lift right-click or W2-H73's
drop the next view skips the seat block: the guest shows off the craft (craft -1, crew one short) and SOLDIERS' OK writes -1 into the view, "basehost",
the own world and (client) the own-world blob. Fix (b): CoopState 55 clears the latch before it pushes the view.
Spec docs rewrite/prompts/w2h85_view_latch_seats.md (f); pins rewrite/w2h85-task0/sa/CONSTANTS.md; capture rewrite/lh83-2-cap (helpers copied).
ONE boot (key 49634), in order: SETUP-H (SEAT, levers: the host's guest H on the client's Skyranger), CTL (guard: real GEOSCAPE), L1 (real BUILD NEW BASE
+ CANCEL), L1r (right-click on the own access lift), SETUP-G (SEAT the client's guest G; the host's quick save), L3c (the client, BUILD NEW BASE + CANCEL),
L2 (W2-H73: client.kill() in the host's view, a new client rejoins, real RESUME), CRASH. A row: SEAT (levers), the real exit from the own base screen,
the real globe visit, READ-VIEW, real SOLDIERS / OK, READ-OK, real GEOSCAPE, READ-OWN. Cells -pre, -exit, -view (craft C, crew crewPre), -ok (view and
"basehost" C), -own (C), L3c-blob (own-world blob C), CRASH. Red today: L1 / L1r / L2 -view -ok -own, L3c -view -ok -own -blob (13 of 27) FAIL.
One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; a -pre / -exit miss ends its row with ONE CAPTURE line. WV-D95 / WV-D99 /
WV-D100: ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_view_latch_seats.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, os, sys, time  # noqa: E401
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY, TAG = "49634", "w2h85_vls"                # lobby key (0 hits at the base); user dirs w2h85_vls_*
ZOOM_MIN, SYM_PLUS = 3, 43                     # real '+' presses until globe zoom >= 3 (CAP), at most 7
VISIT, POP, LIFT_S, W62, ACK, HOME, BLOB, GUEST_S = 60.0, 10.0, 5.0, 15.0, 120.0, 30.0, 45.0, 40.0
S_VIEW, S_SOLD, S_OK, S_RESUME, S_EXIT = 1.0, 0.6, 0.5, 3.0, 0.6
NOTICE_S = 10.0  # bound: the host's items-received notice (CoopState 150) after the guest transfer (cap-save F23940: it lands 1-16 ms after the reply)
RC_OK = (0, 3221226505)
W2H73 = "[coop] the partner dropped while the host views its base"
SYNC = "[coop-gift] synced guest craft assignments into own-world blob"
ORDER = ["CTL", "L1", "L1r", "L3c", "L2"]
CELLS = {r: ["%s-%s" % (r, c) for c in ("pre", "exit", "view", "ok", "own")] for r in ORDER}
CELLS["L3c"].append("L3c-blob")
CELLS["CRASH"] = ["CRASH"]
T0 = time.time()
RESULTS = []

class Stop(Exception):  # a precondition missed: the row ends here
    pass

# ----- probes (copied from docs rewrite/lh83-2-cap/capc.py) -----
def now(): return round(time.time() - T0, 2)
def short(e, n=300): return ("%s: %s" % (type(e).__name__, e))[:n]
def js(v): return json.dumps(v, sort_keys=True, default=str)
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001 - a probe failure is a value
        return {"error": short(e, 200)}
def stack(gc): return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]
def top(gc): return (stack(gc) or [None])[-1]
def coop(gc): return {k: v for k, v in q(gc, {"cmd": "get_coop"}).items() if k in ("insideCoopBase", "clientName", "resumeAck")}
def inside(gc): return q(gc, {"cmd": "get_coop"}).get("insideCoopBase")
def dlg(gc): return {k: v for k, v in q(gc, {"cmd": "coop_dialog_info"}).items() if k in ("code", "backText", "backVisible", "saveQuitVisible")}
def gs(gc): return q(gc, {"cmd": "geo_state"})
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "**", "*"), recursive=True))
def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log") if gc else ""
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if p and os.path.exists(p) else []
def tail(gc, n=25): return [ln.split("\t")[-1][:220] for ln in log(gc)[-n:]]
def cpu():
    c = harness.cpu_load()
    return {"cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}
def wait(pred, timeout, interval=0.1):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 2)
        time.sleep(interval)
def guest(soldiers, name): return next((s for s in soldiers or [] if s.get("name") == name), None)

def blob_guest(gc, key, name):
    """dump_coop_file key -> parse the YAML -> the guest's entries [base, coopcraft, coopcrafttype, coopbase] (CAP blob_guest)"""
    d = q(gc, {"cmd": "dump_coop_file", "key": key})
    if not d.get("ok"):
        return {"dump": d.get("error")}
    hits = [p for p in glob.glob(os.path.join(gc.user_dir, "**", key), recursive=True) if os.path.isfile(p)]
    if not hits:
        return {"dump": "no file"}
    p = max(hits, key=os.path.getmtime)
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            docs = [x for x in yaml.load_all(fh, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) if isinstance(x, dict)]
        w = next((x for x in docs if "bases" in x), {})
        return {"guest": [[b.get("name"), s.get("coopcraft"), s.get("coopcrafttype"), s.get("coopbase")] for b in w.get("bases") or []
                          for s in b.get("soldiers") or [] if s.get("name") == name]}
    except Exception as e:  # noqa: BLE001
        return {"parseError": short(e, 200)}
    finally:
        try:
            os.remove(p)
        except OSError:
            pass
def blob_cc(b):
    g = b.get("guest")
    return g[0][1] if g and len(g) == 1 else ("absent" if g == [] else b)

# ----- real presses (CAP) -----
def real_click(gc, text, timeout=15.0):
    t0, seen = time.time(), []
    while time.time() - t0 < timeout:
        ws = [w for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if (w.get("text") or "").strip().lower() == text.lower()]
        w = next((w for w in ws if w.get("visible") is True and w.get("hidden") is False), None)
        if w is not None:
            c = q(gc, {"cmd": "click_widget", "match": w.get("text")})
            return {"ok": bool(c.get("ok")), "s": round(time.time() - t0, 2)}
        seen = [[w.get("text"), w.get("visible"), w.get("hidden")] for w in ws]
        time.sleep(0.05)
    return {"ok": False, "miss": "%s: button %r not shown within %.0f s (%s)" % (gc.name, text, timeout, seen)}
def must(gc, text, timeout=10.0):
    r = real_click(gc, text, timeout)
    if not r.get("ok"):
        raise Stop("press %s: %s (stack %s)" % (text, r, stack(gc)))
    return r
def cw(gc, match, settle=0.8):
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
    return {"base": [r.get("baseX"), r.get("baseY")], "win": [r.get("winX"), r.get("winY")]}
def affine(r1, r2):
    out = [(r1["win"][i] - r2["win"][i]) / (r1["base"][i] - r2["base"][i]) if r1["base"][i] != r2["base"][i] else None for i in (0, 1)]
    sc = round(out[0] or out[1], 3)
    return (sc, r1["win"][0] - sc * r1["base"][0], sc, r1["win"][1] - sc * r1["base"][1])
def win(sc, bx, by): return int(round(sc[0] * bx + sc[1])), int(round(sc[2] * by + sc[3]))
def aff(V):
    a, b = cw(V, "INTERCEPT"), cw(V, "CANCEL")
    if None in a["base"] + b["base"] or a["base"][0] == b["base"][0] or a["base"][1] == b["base"][1] or top(V) != "GeoscapeState":
        raise Stop("AFF: INTERCEPT %s, CANCEL %s, top %s" % (a, b, top(V)))
    return affine(a, b)
def click_px(gc, bx, by, sc, offsets=((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2))):
    tries = []
    for dx, dy in offsets:
        wx, wy = win(sc, bx + dx, by + dy)
        q(gc, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy})
        v, _ = wait(lambda: top(gc) != "GeoscapeState", 1.0, 0.05)
        tries.append([wx, wy, top(gc)])
        if v:
            break
    return tries
def click_marker(gc, sc, lon, lat, name):
    """centre the globe on the base (camera lever), zoom by real '+' keys, real clicks at its pixel, the target row if a list opens"""
    q(gc, {"cmd": "globe_point", "centerLon": lon, "centerLat": lat})
    zs = [q(gc, {"cmd": "globe_point"}).get("zoom")]
    while (zs[-1] or 0) < ZOOM_MIN and len(zs) < 7:
        q(gc, {"cmd": "inject_input", "kind": "key", "key": SYM_PLUS})
        time.sleep(0.6)
        zs.append(q(gc, {"cmd": "globe_point"}).get("zoom"))
    g = q(gc, {"cmd": "globe_point", "lon": lon, "lat": lat})
    out = {"zooms": zs, "px": [g.get("x"), g.get("y")], "tries": click_px(gc, g.get("x"), g.get("y"), sc)}
    if top(gc) == "MultipleTargetsState":
        out["targets"] = [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
        t = next((t for t in out["targets"] if t.strip() == name), None)
        if t:
            out["pick"] = real_click(gc, t.strip(), 5)
    return out

# ----- steps -----
def visit_real(s, ev):
    """the visitor's real click on the partner's base marker; inside + BasescapeState within VISIT"""
    V = s.V
    session.wait_peer_base_shown(V, s.PB)
    pb = next((b for b in gs(V).get("bases", []) if b.get("name") == s.PB), None)
    if not pb:
        raise Stop("no %s marker in the visitor's geo_state" % s.PB)
    c = click_marker(V, s.sc, pb["lon"], pb["lat"], s.PB)
    v, t = wait(lambda: inside(V) is True and top(V) == "BasescapeState", VISIT)
    ev["visit"] = {"targets": c.get("targets"), "tries": len(c["tries"]), "zooms": c["zooms"], "insideS": t}
    if not v:
        raise Stop("real visit: not inside %s within %.0f s (stack %s)" % (s.PB, VISIT, stack(V)))
    time.sleep(S_VIEW)
def lever_visit(V, pb):
    session.wait_peer_base_shown(V, pb)
    q(V, {"cmd": "visit_coop_base", "base": pb})
    v, t = wait(lambda: inside(V) is True and top(V) == "BasescapeState", VISIT)
    if not v:
        raise Stop("lever visit %s: not inside within %.0f s (stack %s)" % (pb, VISIT, stack(V)))
    return t
def lever_leave(V, label):
    q(V, {"cmd": "leave_base"})
    session.wait_back_on_geoscape(V, label)
    time.sleep(1.0)
def read_view(V, s):
    rv = q(V, {"cmd": "base_report", "coop": True})
    g = guest(rv.get("soldiers"), s.name) or {}
    cr = next((c for c in rv.get("crafts") or [] if c.get("id") == s.C and c.get("type") == s.T), {})
    return {"base": rv.get("name"), "craft": g.get("craft"), "coopCraft": g.get("coopCraft"), "crew": cr.get("soldiers"), "listed": bool(g)}
def read_own(V, s):
    ro = q(V, {"cmd": "base_report", "base": s.VB})
    g = guest(ro.get("soldiers"), s.name) or {}
    return {"base": ro.get("name"), "coopCraft": g.get("coopCraft"), "listed": bool(g)}
def own_blob(s):
    fi = q(s.V, {"cmd": "coop_file_info", "role": "own_world"})
    b = blob_guest(s.V, fi.get("key"), s.name) if fi.get("present") else {"present": fi.get("present")}
    return {"key": fi.get("key"), "fnv": fi.get("fnv1a64"), "guest": b.get("guest", b), "coopcraft": blob_cc(b)}
def read_ok(s, n0):
    d = read_view(s.V, s)
    bh = blob_guest(s.V, "basehost", s.name)
    d.update(basehostGuest=bh.get("guest", bh), basehost=blob_cc(bh))
    if s.client:
        d["ownBlob"] = own_blob(s)
        d["syncLines"] = sum(1 for ln in log(s.V)[n0:] if SYNC in ln)
    return d

def seat(x, s):
    """SEAT (SETUP levers, CAP setup): the first time pick + transfer the guest; every time a lever visit, craft_assign, SOLDIERS' OK lever,
    leave_base, a CONFIRM lever visit (guest craft, crewPre), leave_base, the own world's coopCraft"""
    V, d = s.V, {}
    if s.name is None:
        rb = session._campaign_own_roster_base(V)
        s.VB, s.PB = rb["name"], session._campaign_own_roster_base(s.P)["name"]
        s.name = next(z for z in rb["soldiers"] if not z.get("craft"))["name"]
        tr = q(V, {"cmd": "transfer_to_coop_base", "name": s.name, "toBase": s.PB})
        d["transfer"] = [s.name, s.VB, s.PB, tr.get("transferred")]
        if not tr.get("transferred"):
            raise Stop("transfer %s: %s" % (s.name, tr))
        if s.P is x.host:  # SETUP-G: the guest goes to the host's base, so the host shows the notice
            nt, tn = wait(lambda: q(x.host, {"cmd": "coop_dialog_info"}).get("code") == 150, NOTICE_S, 0.02)
            d["notice"] = [bool(nt), tn]
            if not nt:
                raise Stop("transfer %s: no host items-received notice (CoopState 150) within %.0f s (stack %s)" % (s.name, NOTICE_S, stack(x.host)))
        session.drain_host_coop_notice(x.host)
    d["visitS"] = lever_visit(V, s.PB)
    rep, t = wait(lambda: (lambda r: r if guest(r.get("soldiers"), s.name) else None)(q(V, {"cmd": "base_report", "coop": True})), GUEST_S)
    if not rep:
        raise Stop("guest %s not listed at %s within %.0f s" % (s.name, s.PB, GUEST_S))
    if s.C is None:
        k = next((c for c in rep.get("crafts") or [] if "SKYRANGER" in (c.get("type") or "")), None)
        if not k:
            raise Stop("no SKYRANGER at %s: %s" % (s.PB, [[c.get("id"), c.get("type")] for c in rep.get("crafts") or []]))
        s.C, s.T = k["id"], k["type"]
    g = guest(rep["soldiers"], s.name)
    sa = q(V, {"cmd": "craft_assign", "soldier_id": g["id"], "craft_id": s.C, "coop": True, "on": True})
    d.update(viewId=g["id"], before=[g.get("craft"), g.get("coopCraft")], seated=sa.get("seated"), C=[s.C, s.T])
    q(V, {"cmd": "open_soldiers", "base": s.PB})
    if not wait(lambda: top(V) == "SoldiersState", 30)[0]:
        raise Stop("open_soldiers: no SoldiersState (stack %s)" % stack(V))
    q(V, {"cmd": "soldiers_ok"})
    if not wait(lambda: top(V) == "BasescapeState", 30)[0]:
        raise Stop("soldiers_ok: no BasescapeState (stack %s)" % stack(V))
    d["lever"] = read_view(V, s)
    lever_leave(V, "seat leave")
    lever_visit(V, s.PB)
    time.sleep(S_VIEW)
    d["confirm"] = read_view(V, s)
    s.crewPre = d["confirm"]["crew"]
    lever_leave(V, "seat leave 2")
    d["own"] = read_own(V, s)
    return d

def open_own_base(s, ev):
    V = s.V
    must(V, "BASES", 10)
    v, t = wait(lambda: top(V) == "BasescapeState", 10, 0.05)
    time.sleep(S_EXIT)
    sel = gs(V).get("selectedBase")
    ev["bases"] = [top(V), sel, t]
    if not v or sel != s.VB:
        raise Stop("BASES: not on the own base screen (top %s, selectedBase %s, want %s)" % (top(V), sel, s.VB))

def lift_right_click(s, ev):
    V = s.V
    ob = next((b for b in gs(V).get("bases", []) if b.get("name") == s.VB and not b.get("coopIcon")), {})
    lift = next(([f.get("type"), f.get("x"), f.get("y")] for f in ob.get("facilities") or [] if f.get("type") == "STR_ACCESS_LIFT"), None)
    vw = next((w for w in q(V, {"cmd": "list_widgets"}).get("widgets", []) if (w.get("type") or "").endswith("::BaseView")), None)
    if not lift or not vw:
        raise Stop("no lift %s / BaseView %s" % (lift, vw))
    bx, by = vw["x"] + lift[1] * 32 + 16, vw["y"] + lift[2] * 32 + 16
    wx, wy = win(s.sc, bx, by)
    q(V, {"cmd": "inject_input", "kind": "motion", "x": wx, "y": wy})
    time.sleep(0.3)
    r = q(V, {"cmd": "inject_input", "kind": "click", "button": "right", "x": wx, "y": wy})
    v, t = wait(lambda: top(V) == "GeoscapeState", LIFT_S, 0.05)
    ev["lift"] = {"lift": lift, "view": [vw.get("x"), vw.get("y")], "base": [bx, by], "win": [wx, wy], "inject": r.get("ok"), "s": t}
    return bool(v)

class Row:
    def __init__(self, rid, x):
        self.rid, self.cells, self.ev, self.done, self.x = rid, CELLS[rid], {}, {}, x

    def cell(self, name, ok, detail):
        self.done[name] = bool(ok)
        RESULTS.append((name, bool(ok)))
        print("%s %s: %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)

    def capture(self, why):
        d = {"why": why}
        for n in ("host", "client"):
            gc = getattr(self.x, n)
            if not alive(gc):
                d[n] = {"alive": False, "log": tail(gc)}
                continue
            fi = q(gc, {"cmd": "coop_file_info", "role": "own_world"})
            d[n] = {"stack": stack(gc), "coop": coop(gc), "dlg": dlg(gc), "ownWorld": [fi.get("key"), fi.get("fnv1a64")],
                    "view": q(gc, {"cmd": "base_report", "coop": True}) if inside(gc) else None, "log": tail(gc)}
            sd = self.x.sh if gc is self.x.host else self.x.sg
            if sd.VB:
                d[n]["own"] = q(gc, {"cmd": "base_report", "base": sd.VB})
        print("CAPTURE %s: %s" % (self.rid, js(d)), flush=True)

    def close(self, why):
        for n in self.cells:
            if n not in self.done:
                self.cell(n, False, "not reached: %s" % why)
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        bad = [n for n in self.cells if not self.done.get(n)]
        print("ROW %s: %s" % (self.rid, "PASS" if not bad else "FAIL (%d failing: %s)" % (len(bad), bad)), flush=True)

def tail_cells(r, s, n0):
    """ROW's visit, READ-VIEW, real SOLDIERS / OK, READ-OK, real GEOSCAPE, READ-OWN"""
    V, rid = s.V, r.rid
    visit_real(s, r.ev)
    rv = r.ev["view"] = read_view(V, s)
    r.cell(rid + "-view", rv["craft"] == s.C and rv["crew"] == s.crewPre,
           "%s in the view of %s: craft %s, craft (%s, %s) crew %s; coopCraft %s (want craft %s, crew %s = crewPre)"
           % (s.name, s.PB, rv["craft"], s.C, s.T, rv["crew"], rv["coopCraft"], s.C, s.crewPre))
    must(V, "SOLDIERS", 10)
    if not wait(lambda: top(V) == "SoldiersState", 10, 0.05)[0]:
        raise Stop("real SOLDIERS: no SoldiersState (stack %s)" % stack(V))
    time.sleep(S_SOLD)
    must(V, "OK", 10)
    if not wait(lambda: top(V) == "BasescapeState", 10, 0.05)[0]:
        raise Stop("real OK: no BasescapeState (stack %s)" % stack(V))
    time.sleep(S_OK)
    ro = r.ev["ok"] = read_ok(s, n0)
    r.cell(rid + "-ok", ro["coopCraft"] == s.C and ro["basehost"] == s.C,
           "after SOLDIERS' OK: view coopCraft %s, \"basehost\" coopcraft %s (want %s, %s)" % (ro["coopCraft"], ro["basehost"], s.C, s.C))
    if s.client:
        b = ro["ownBlob"]
        r.cell(rid + "-blob", b["coopcraft"] == s.C, "own-world blob %s fnv %s: %s coopcraft %s; synced lines since the row %d (want %s)"
               % (b["key"], b["fnv"], s.name, b["coopcraft"], ro["syncLines"], s.C))
    must(V, "GEOSCAPE", 10)
    session.wait_back_on_geoscape(V, rid + " GEOSCAPE")
    time.sleep(1.0)
    ow = r.ev["own"] = read_own(V, s)
    r.cell(rid + "-own", ow["coopCraft"] == s.C, "own world %s: %s coopCraft %s (want %s)" % (ow["base"], s.name, ow["coopCraft"], s.C))

def run_row(x, rid, s, body):
    r = Row(rid, x)
    try:
        if x.boot_err:
            r.cell(rid + "-pre", False, "boot: %s" % x.boot_err)
            raise Stop("boot")
        r.ev["n0"] = n0 = len(log(s.V))
        body(x, r, s, n0)
        r.close("")
    except Exception as e:  # noqa: BLE001 - a precondition / exit miss ends the row
        r.ev["stop"] = short(e, 500)
        if str(e) != "boot":
            r.capture(short(e))
        r.close(short(e))

def pre_cell(r, s, d, extra=""):
    ok = d.get("seated") is True and d["confirm"]["craft"] == s.C and d["own"]["coopCraft"] == s.C and (s.crewPre or 0) >= 1 and not extra
    r.ev["seat"] = d
    r.cell(r.rid + "-pre", ok, "SEAT %s at %s: seated %s, confirm craft %s, crewPre %s, own coopCraft %s%s (want true, %s, >= 1, %s)"
           % (s.name, s.PB, d.get("seated"), d["confirm"]["craft"], s.crewPre, d["own"]["coopCraft"], extra, s.C, s.C))
    if not ok:
        raise Stop(r.rid + "-pre")

def seat_cell(r, x, s):
    try:
        d = seat(x, s)
    except Exception as e:  # noqa: BLE001 - a SEAT miss is the row's -pre
        r.cell(r.rid + "-pre", False, "SEAT: %s" % short(e))
        raise Stop(r.rid + "-pre: " + short(e))
    pre_cell(r, s, d)

def own_exit(x, r, s, kind):
    V, rid = s.V, r.rid
    open_own_base(s, r.ev)
    if kind == "geoscape":
        must(V, "GEOSCAPE", 10)
        session.wait_back_on_geoscape(V, rid + " exit")
        time.sleep(1.0)
        ok, why = top(V) == "GeoscapeState" and inside(V) is False, "real GEOSCAPE: top %s, insideCoopBase %s" % (top(V), inside(V))
    elif kind == "newbase":
        must(V, "BUILD NEW BASE", 10)
        a, ta = wait(lambda: top(V) == "BuildNewBaseState", POP, 0.05)
        time.sleep(S_EXIT)
        b, tb = (None, None)
        if a:
            must(V, "CANCEL", 10)
            b, tb = wait(lambda: top(V) == "GeoscapeState", POP, 0.05)
            time.sleep(S_EXIT)
        ok, why = bool(a and b), "real BUILD NEW BASE -> BuildNewBaseState %s in %s s, real CANCEL -> GeoscapeState %s in %s s" % (bool(a), ta, bool(b), tb)
    else:
        ok = lift_right_click(s, r.ev)
        time.sleep(S_EXIT)
        why = "LIFT right-click %s -> GeoscapeState %s in %s s (stack %s)" % (r.ev["lift"]["lift"], ok, r.ev["lift"]["s"], stack(V))
    r.ev["exit"] = [ok, why]
    r.cell(rid + "-exit", ok, why)
    if not ok:
        raise Stop(rid + "-exit")

def body_ctl(x, r, s, n0):
    if x.setup_h is None:
        r.cell("CTL-pre", False, "SETUP-H: %s" % x.setup_err)
        raise Stop("CTL-pre")
    pre_cell(r, s, x.setup_h)
    own_exit(x, r, s, "geoscape")
    tail_cells(r, s, n0)

def body_l1(x, r, s, n0, kind="newbase"):
    seat_cell(r, x, s)
    own_exit(x, r, s, kind)
    tail_cells(r, s, n0)

def body_l3c(x, r, s, n0):
    if x.setup_g is None:
        r.cell("L3c-pre", False, "SETUP-G: %s" % x.setup_err)
        raise Stop("L3c-pre")
    b = x.setup_g.get("blob") or {}
    pre_cell(r, s, x.setup_g, "" if b.get("coopcraft") == s.C else "; own-world blob coopcraft %s" % b.get("coopcraft"))
    own_exit(x, r, s, "newbase")
    tail_cells(r, s, n0)

def body_l2(x, r, s, n0):
    h = x.host
    seat_cell(r, x, s)
    visit_real(s, r.ev)
    r.ev["view0"] = read_view(h, s)
    n1, cname = len(log(h)), coop(h).get("clientName")
    x.client.kill()
    t0, trace, last = time.time(), [], None
    while time.time() - t0 < W62:
        st = stack(h)
        c = dlg(h).get("code") if st[-1:] == ["CoopState"] else None
        if (st, c) != last:
            trace.append([round(time.time() - t0, 2), st, c])
            last = (st, c)
        if c == 62:
            break
        time.sleep(0.05)
    got62 = last is not None and last[1] == 62
    ack = tr = home = ack_s = home_s = None
    if got62:
        c2 = x.client = x.sh.P = GameClient("client", None, make_user_dir(TAG + "_client2"))
        c2.spawn()
        c2.connect()
        r.ev["join"] = q(c2, {"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": cname}).get("ok")
        ack, ack_s = wait(lambda: coop(h).get("resumeAck"), ACK, 0.25)
        if ack:
            t1 = time.time()
            while time.time() - t1 < 30 and tr is None:
                st = stack(h)
                if st and "Profile" in st[-1]:
                    real_click(h, "OK", 5)
                elif st[-1:] == ["CoopState"] and dlg(h).get("code") in (60, 62) and dlg(h).get("backVisible"):
                    tr = round(time.time() - t1, 2) if real_click(h, dlg(h).get("backText") or "RESUME", 5).get("ok") else None
                time.sleep(0.05)
        if tr is not None:
            home, home_s = wait(lambda: top(h) == "GeoscapeState" and inside(h) is False, HOME)
    h73 = [ln.split("\t")[-1][:160] for ln in log(h)[n1:] if W2H73 in ln]
    r.ev.update(trace=trace[-6:], clientName=cname, ack=[bool(ack), ack_s], resume=tr, home=[bool(home), home_s], h73=h73)
    ok = got62 and bool(ack) and tr is not None and bool(home) and len(h73) == 1
    r.cell("L2-exit", ok, "host log W2-H73 lines since the kill %d; 62 %s (trace %s); rejoin %s resumeAck %s in %s s; RESUME %s; home %s in %s s "
           "(want 1, true, true, clicked, true)" % (len(h73), got62, trace[-2:], cname, bool(ack), ack_s, tr is not None, bool(home), home_s))
    if not ok:
        raise Stop("L2-exit")
    time.sleep(S_RESUME)
    wait(lambda: any(b.get("name") == s.PB for b in gs(h).get("bases", [])), 20, 0.25)
    geo.slow_clock(h, x.client)
    session.drain_host_coop_notice(h)
    tail_cells(r, s, n0)

def setup_g(x):
    """SETUP-G: SEAT(client, host, G); the host's quick save (lever); BLOB; both tops GeoscapeState; drain_popups(host); AFF-client"""
    s, V = x.sg, x.client
    d = seat(x, s)
    fi0 = q(V, {"cmd": "coop_file_info", "role": "own_world"})
    sv = q(x.host, {"cmd": "save_game_ui", "type": "quick"})

    def blob_has_g():
        fi = q(V, {"cmd": "coop_file_info", "role": "own_world"})
        if not fi.get("present") or fi.get("fnv1a64") == fi0.get("fnv1a64"):
            return None
        b = own_blob(s)
        return b if b["coopcraft"] == s.C else None
    b, tb = wait(blob_has_g, BLOB, 0.5)
    tops, tt = wait(lambda: top(x.host) == "GeoscapeState" and top(V) == "GeoscapeState", 20, 0.25)
    geo.drain_popups(x.host)
    d["blob"] = b or own_blob(s)
    d["save"] = {"ok": sv.get("ok"), "err": sv.get("error"), "before": [fi0.get("key"), fi0.get("fnv1a64")], "s": tb, "topsS": tt}
    if not b or not tops:
        raise Stop("SETUP-G: blob %s in %s s, tops %s / %s" % (d["blob"], tb, stack(x.host), stack(V)))
    s.sc = aff(V)
    d["aff"] = s.sc
    return d

def boot(x):
    x.host = GameClient("host", None, make_user_dir(TAG + "_host"))
    x.client = GameClient("client", None, make_user_dir(TAG + "_client"))
    x.host.spawn()
    x.client.spawn()
    x.host.connect()
    x.client.connect()
    session.new_campaign(x.host, x.client, port=KEY)
    geo.slow_clock(x.host, x.client)
    time.sleep(2.0)
    session.drain_host_coop_notice(x.host)

def shut(gc):
    try:
        if alive(gc):
            gc.shutdown(expected_returncodes=RC_OK)
        return gc.proc.poll() if gc and gc.proc else None
    except Exception as e:  # noqa: BLE001
        return short(e, 200)

def run_all():
    c0 = cpu()
    print("==== W2-H85 VLS (slot %s, key %s, exe %s) CPU %s ====" % (harness.HARNESS_SLOT, KEY, time.ctime(os.path.getmtime(harness.EXE)), c0),
          flush=True)
    x = SimpleNamespace(host=None, client=None, cr0=crashes(), boot_err=None, setup_err=None, setup_h=None, setup_g=None)
    x.sh = SimpleNamespace(V=None, P=None, VB=None, PB=None, name=None, C=None, T=None, crewPre=None, sc=None, client=False)
    x.sg = SimpleNamespace(V=None, P=None, VB=None, PB=None, name=None, C=None, T=None, crewPre=None, sc=None, client=True)
    try:
        boot(x)
        x.sh.V, x.sh.P, x.sg.V, x.sg.P = x.host, x.client, x.client, x.host
    except Exception as e:  # noqa: BLE001 - a boot miss fails every row's -pre
        x.boot_err = short(e, 300)
        print("BOOT MISS: %s" % x.boot_err, flush=True)
    if not x.boot_err:
        try:
            x.setup_h = seat(x, x.sh)
            x.sh.sc = aff(x.host)
            x.setup_h["aff"] = x.sh.sc
        except Exception as e:  # noqa: BLE001 - feeds CTL-pre
            x.setup_h, x.setup_err = None, short(e, 300)
    run_row(x, "CTL", x.sh, body_ctl)
    run_row(x, "L1", x.sh, body_l1)
    run_row(x, "L1r", x.sh, lambda x, r, s, n0: body_l1(x, r, s, n0, "lift"))
    if not x.boot_err:
        try:
            x.setup_g = setup_g(x)
        except Exception as e:  # noqa: BLE001 - feeds L3c-pre
            x.setup_g, x.setup_err = None, short(e, 300)
    run_row(x, "L3c", x.sg, body_l3c)
    run_row(x, "L2", x.sh, body_l2)
    r = Row("CRASH", x)
    al = [alive(x.host), alive(x.client)]
    rc = [shut(x.client), shut(x.host)]
    nc = sorted(crashes() - x.cr0)
    r.ev.update(alive=al, rc=rc, newCrash=nc)
    r.cell("CRASH", al == [True, True] and all(c in RC_OK for c in rc) and not nc,
           "host / client alive before shutdown %s; shutdown rc client %s host %s; new crash files %s (want [true, true], in %s, none)"
           % (al, rc[0], rc[1], nc, list(RC_OK)))
    r.close("")
    fails = [n for n, ok in RESULTS if not ok]
    c1 = cpu()
    print("SUMMARY pass=%d fail=%d" % (len(RESULTS) - len(fails), len(fails)), flush=True)
    print("==== W2-H85 VLS: %d/%d cells PASS, wall %.1f s, CPU %s -> %s ====" % (len(RESULTS) - len(fails), len(RESULTS), now(), c0, c1), flush=True)
    if fails:
        print("FAILING: %s" % fails, flush=True)
    return x, (0 if not fails else 2)

if __name__ == "__main__":
    sys.exit(run_all()[1])
