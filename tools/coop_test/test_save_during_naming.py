"""A co-op host save while the second player names a new base.
In a PvP campaign (gm3, the host on the Alien team) the X-COM client keeps its own world, and its new base sits in its
own base list with the name "" while BaseNameState is open, so
the memory save of the client's answer to a host save request refuses the whole world: the client gets a false 995
over a Disconnect-only "Saving..." (53) that never closes (the base can never be named), the host's "Saving." (54)
waits with no file, and the client's stream thread loopData retries every 10 ms with a crash file each time (~90 / s).
Boot name_open (dirs save_naming_name_open_*) = row naming; boot name_set (dirs save_naming_name_set_*) = row control,
then row key_miss. Each boot: spawn + connect both; pvp_fixture.start_pvp_campaign (key KEY, gm3, tcp);
geo.slow_clock; geo.drain_popups; the client's window mapping from INTERCEPT + its CANCEL (real clicks).
"Growth" = new crash_*.log files in this harness slot's crash folder (harness.CRASH_DIR, both machines) whose text holds
"Error in loopData" (each file read once).
  Row naming  client BASES, BUILD NEW BASE, ONE real globe click at LAND_PICK (globe_point), OK -> BaseNameState, own
         base X ""; host save_game_ui {type: quick} -> 54 within 2 s; the client polled every POLL s for HOLD_S.
    naming_screen_held    (FIX) at +HOLD_S the client's top is BaseNameState, no CoopState over it.
    naming_no_995         (FIX) no client poll of the row saw coop_dialog_info code 995.
    naming_no_flood       (FIX) growth from the trigger to +HOLD_S is 0.
    naming_host_waits     (GUARD) at +HOLD_S the host's top is CoopState 54, pendingHostSaveName non-empty, no
                          _quick_.asav newer than the trigger.
         (precondition naming_screen_held) NEWNAME by real key presses, OK.
    naming_finished       (FIX) the client's top is PlaceLiftState, or a CoopState 53 over it, within 5 s of the OK.
    naming_save_done      (FIX) within DONE_S of the OK the host's top is GeoscapeState and _quick_.asav is newer than
                          the trigger.
    naming_save_has_name  (FIX) that file's client blob (coopClientSaves) lists a base named NEWNAME.
    naming_client_clear   (FIX) within DONE_S of the OK the client has no CoopState in its stack.
    naming_lift_placed    (FIX) (client top PlaceLiftState) a real click on LIFT_TILE gives the client top
                          BasescapeState within 5 s.
    naming_calm           (FIX) growth over the whole row is 0.
  Row control  the row naming construction, NEWNAME, OK, LIFT_TILE, GEOSCAPE (client top GeoscapeState, own list holds
         NEWNAME); host quick save; the client polled for DONE_S.
    control_save_done     (GUARD) within DONE_S the host's top is GeoscapeState and _quick_.asav is newer than the
                          trigger.
    control_save_has_name (GUARD) its client blob lists NEWNAME.
    control_no_995        (GUARD) no 995 on the client during DONE_S.
    control_calm          (GUARD) growth 0.
  Row key_miss  client force_stream_key_miss {on: true} (test-only); host quick save; F_WINDOW; key miss off.
    key_miss_once         (FIX) growth in F_WINDOW is exactly 1.
    key_miss_host_waits   (GUARD) at +F_WINDOW the host's top is CoopState 54.
    key_miss_heals        (GUARD) within DONE_S of the key miss off the host's top is GeoscapeState, _quick_.asav
                          newer than the trigger, no client CoopState.
    key_miss_calm         (FIX) growth over the whole row is exactly 1.
Without the fix: the 11 FIX cells FAIL; the 7 GUARD cells PASS. With the fix: all 18 PASS.
Every press is a real click_widget or inject_input; only the save trigger and force_stream_key_miss are commands; the
client's Disconnect is never pressed; force_stream_key_miss is off before shutdown. One EVIDENCE line per row, one
PASS / FAIL line per cell, then the row verdict; a precondition miss ends its row (later cells "not reached"); a boot
miss fails every row of that boot "boot" with ONE CAPTURE line. The END line counts every new crash file by kind
(loopData, other, Unhandled, .dmp).
ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_save_during_naming.py   (OXC_HARNESS_SLOT selects the harness slot)"""
import base64, glob, json, math, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
import yaml  # noqa: E402
import pvp_fixture as PF  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49235"                               # the lobby key
NEWNAME = "hnew"                            # lowercase: inject_input key = unicode sym
LIFT_TILE = (2, 2)                          # BaseView tile: base (80, 88) in the 192 x 192 view at (0, 8), 32 px tiles
HOLD_S, DONE_S, F_WINDOW, POLL, STATE_S = 5.0, 10.0, 3.0, 0.2, 5.0
QK = "_quick_.asav"
ROWS = (("naming",
         ("naming_screen_held", "naming_no_995", "naming_no_flood", "naming_host_waits", "naming_finished",
          "naming_save_done", "naming_save_has_name", "naming_client_clear", "naming_lift_placed", "naming_calm")),
        ("control", ("control_save_done", "control_save_has_name", "control_no_995", "control_calm")),
        ("key_miss", ("key_miss_once", "key_miss_host_waits", "key_miss_heals", "key_miss_calm")))
FIX = ("naming_screen_held", "naming_no_995", "naming_no_flood", "naming_finished", "naming_save_done",
       "naming_save_has_name", "naming_client_clear", "naming_lift_placed", "naming_calm",
       "key_miss_once", "key_miss_calm")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]

class Stop(Exception):  # a precondition missed: the row ends here
    pass

# ----- probes and real input -----
def js(v): return json.dumps(v, sort_keys=True, default=str)
def now(): return round(time.time() - T0[0], 2)
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
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
    return {k: r.get(k) for k in ("present", "code", "title", "backText", "error") if k in r}
def code(gc): return dlg(gc).get("code")
def census(gc):
    g = q(gc, {"cmd": "geo_state"})
    bl = [[b.get("coopBaseId"), b.get("name"), bool(b.get("coopIcon")), bool(b.get("coopBase")), round(b.get("lon", 0), 5),
           round(b.get("lat", 0), 5)] for b in g.get("bases", [])]
    return {"bases": bl, "funds": g.get("funds"), "stack": stk(gc), "error": g.get("error")}
def own(c): return [[b[0], b[1]] for b in c["bases"] if not b[2] and not b[3]]
def cpu():
    c = harness.cpu_load()
    return {"t": time.strftime("%H:%M:%S"), "cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}
def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def cw(gc, match, settle=1.0, ready=False):
    if ready:  # a POPUP window (InterceptState) drops a click on a hidden button
        session.wait_widget_ready(gc, match)
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
            e = [t] + ([code(gc)] if t == "CoopState" else [])
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
    """LAND_PICK: rings 0.20-0.50 rad step 0.05 x 16 around the client's own base, >= 0.15 rad from every base and marker; the point
    and its 8 neighbours at 0.02 rad on land; inside the globe surface (10 px margin, 30 px top)."""
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
                return {"lon": round(p[0], 5), "lat": round(p[1], 5), "x": pr["x"], "y": pr["y"], "r": r, "k": k}
    return None
def tick(t0, k): time.sleep(max(0.0, t0 + k * POLL - time.time()))

# ----- the crash census (both machines write the slot's folder) -----
CACHE = {}
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))
def kind(p):
    if p.endswith(".dmp"):
        return "dmp"
    if p in CACHE:
        return CACHE[p]
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
    except OSError:
        return "unreadable"
    v = "loop" if "Error in loopData" in txt else ("unhandled" if "Unhandled" in txt else "other")
    if v == "loop" or time.time() - os.path.getmtime(p) > 2.0:  # a file still being written is read again later
        CACHE[p] = v
    return v
def growth(since, every=False):
    out = {"loop": 0, "other": 0, "unhandled": 0, "dmp": 0, "unreadable": 0}
    for p in crashes() - since:
        out[kind(p)] += 1
    return out if every else out["loop"]

# ----- saves (read_save: the client blobs inside a host save) -----
def read_save(path):
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    out = {"file": os.path.basename(path), "bytes": os.path.getsize(path), "blobs": []}
    with open(path, encoding="utf-8", errors="replace") as fh:
        docs = [d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict)]
    for d in docs:
        for e in d.get("coopClientSaves") or []:
            raw = e.get("blob")
            b = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw or b"")
            w = next((x for x in yaml.load_all(b.decode("utf-8", errors="replace"), Loader=loader) if isinstance(x, dict) and "bases" in x), None)
            out["blobs"].append({"key": e.get("key"), "bytes": len(b), "bases": [[x.get("name"), x.get("coopbaseid")] for x in (w or {}).get("bases") or []]})
    return out
def folder(gc):
    out = {}
    for p in glob.glob(os.path.join(gc.user_dir, "xcom1", "*")):
        try:
            if os.path.isfile(p):
                out[os.path.basename(p)] = os.stat(p).st_mtime_ns
        except FileNotFoundError:  # renamed after the listing (the save's .bak -> .asav move)
            pass
    return out
def newer(gc, before):
    f = folder(gc)
    return QK in f and (QK not in before or f[QK] > before[QK])
def has_name(f): return any(b[0] == NEWNAME for x in f["blobs"] for b in x["bases"])

# ----- boots and rows -----
class Boot:
    def __init__(self, pair):
        self.pair, self.aff = pair, {}
        self.host = GameClient("host", None, make_user_dir("save_naming_%s_host" % pair.lower()))
        self.client = GameClient("client", None, make_user_dir("save_naming_%s_client" % pair.lower()))
class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res, self.s0, self.trig = x, b, rid, {}, crashes(), False
        self.ev = {"t": now(), "cpu": cpu()}
    def cell(self, cid, ok, label):
        self.res[cid] = (bool(ok), label)
    def need(self, ok, what):
        if not ok:
            raise Stop(what)
    def finish(self, stop=None):
        calm = self.rid + "_calm"
        if self.trig and calm not in self.res:  # a whole-row measure, taken once the save was triggered
            g = growth(self.s0, True)
            want = 1 if self.rid == "key_miss" else 0
            self.cell(calm, g["loop"] == want, "growth over the row %s (want loop == %d)" % (js(g), want))
        self.ev["tEnd"] = now()
        if stop:
            self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails = []
        for cid in dict(ROWS)[self.rid]:
            ok, label = self.res.get(cid, (False, "not reached (%s)" % stop))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "FIX" if cid in FIX else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails
def capture(b):
    """every live machine's probes and log tail (the setup failure dump)"""
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
def bring_up(b):
    for gc in (b.host, b.client):
        gc.spawn()
        gc.connect(timeout=240)
    PF.start_pvp_campaign(b.host, b.client, KEY, alien_player="host")
    geo.slow_clock(b.host, b.client)
    time.sleep(2.0)
    ev = {"drain": [str(geo.drain_popups(gc))[:120] for gc in (b.host, b.client)]}
    b.aff["client"] = affine(cw(b.client, "INTERCEPT", 0.6), cw(b.client, "CANCEL", 0.6, ready=True))
    h, c = census(b.host), census(b.client)
    ev.update({"aff": b.aff, "host": h, "client": c})
    ok = h["stack"] == ["GeoscapeState"] and c["stack"] == ["GeoscapeState"] and len(own(h)) == 1 and len(own(c)) == 1
    return ok, ev
def to_name(b, r):
    """client: BASES, BUILD NEW BASE, ONE real globe click at LAND_PICK, OK -> BaseNameState with one own base named "" (id X)"""
    c, ev = b.client, r.ev
    ev["bases"], ev["newBase"] = cw(c, "BASES")["after"], cw(c, "NEW BASE")["after"]
    r.need(top(c) == "BuildNewBaseState", "client top %s after BUILD NEW BASE" % top(c))
    cc = census(c)
    pick = ev["LAND_PICK"] = pick_point(c, [(x[4], x[5]) for x in cc["bases"] if not x[2]] + [(x[4], x[5]) for x in cc["bases"] if x[2]])
    r.need(pick, "no land point for LAND_PICK")
    ev["globeClick"] = [t["top"] for t in click_px(c, pick["x"], pick["y"], b.aff["client"], "BuildNewBaseState")]
    r.need(top(c) == "ConfirmNewBaseState", "client top %s after the globe click" % top(c))
    ev["confirmOk"] = cw(c, "OK")["after"][-1:]
    cc = census(c)
    new = [x for x in own(cc) if x[1] == ""]
    r.need(top(c) == "BaseNameState" and len(new) == 1, "client on BaseNameState with one own base \"\" (%s, %s)" % (top(c), own(cc)))
    ev["X"] = new[0][0]
def type_ok(c, ev):
    for ch in NEWNAME:
        key(c, ord(ch))
        time.sleep(0.08)
    time.sleep(0.4)
    t = time.time()
    ev["nameOk"] = cw(c, "OK", 0.0)["after"][-2:]
    return t
def wait_until(pred, timeout, step=0.1):
    t = time.time()
    while time.time() - t < timeout:
        if pred():
            return round(time.time() - t, 2)
        time.sleep(step)
    return None
def lift(b, ev):
    c = b.client
    ev["lift"] = [t["top"] for t in click_px(c, LIFT_TILE[0] * 32 + 16, 8 + LIFT_TILE[1] * 32 + 16, b.aff["client"], "PlaceLiftState", offsets=((0, 0),))]
    return wait_until(lambda: top(c) == "BasescapeState", 5.0)
def trigger(b, r):
    r.ev["before"] = folder(b.host)
    r.s1, r.tTrig, r.trig = crashes(), time.time(), True
    r.ev["trigger"] = q(b.host, {"cmd": "save_game_ui", "type": "quick"}).get("ok")
def watch(b, t0, secs, trace, codes, stop=None):
    """poll both machines every POLL s until t0 + secs (or stop()); trace = changes of [host top, its code, client tail, client code]"""
    k = 0
    while time.time() - t0 < secs and not (stop and stop()):
        k += 1
        tick(t0, k)
        hs, cs = top(b.host), stk(b.client)
        cc = code(b.client) if "CoopState" in cs else None
        codes.add(cc)
        e = [hs, code(b.host) if hs == "CoopState" else None, cs[-2:], cc]
        if not trace or trace[-1][1:] != e:
            trace.append([round(time.time() - t0, 2)] + e)
def row_naming(b, r):
    h, c, ev = b.host, b.client, r.ev
    to_name(b, r)
    trigger(b, r)
    t54 = wait_until(lambda: top(h) == "CoopState" and code(h) == 54, 2.0, 0.05)
    ev["t54"] = t54
    r.need(t54 is not None, "host top %s (code %s) 2 s after the quick save" % (top(h), code(h)))
    trace, codes = [], set()
    watch(b, r.tTrig, HOLD_S, trace, codes)
    cs, gro, hd, gco = stk(c), growth(r.s1, True), dlg(h), q(h, {"cmd": "get_coop"})
    ev["hold"] = {"trace": trace, "clientStack": cs[-3:], "growth": gro, "hostDlg": hd, "pending": gco.get("pendingHostSaveName"),
                  "saveID": gco.get("saveID"), "coopSave": [ln.split("\t")[-1] for ln in logl(c) if "[coop-save]" in ln]}
    r.cell("naming_screen_held", cs[-1:] == ["BaseNameState"] and "CoopState" not in cs, "client stack at +HOLD_S %s "
           "(want BaseNameState on top)" % cs[-3:])
    r.cell("naming_no_flood", gro["loop"] == 0, "growth trigger -> +HOLD_S %s (want loop 0)" % js(gro))
    nf = newer(h, ev["before"])
    r.cell("naming_host_waits", top(h) == "CoopState" and hd.get("code") == 54 and gco.get("pendingHostSaveName")
           and not nf,
           "host top %s code %s, pendingHostSaveName %r, %s newer than the trigger %s" % (top(h), hd.get("code"), gco.get("pendingHostSaveName"), QK, nf))
    if r.res["naming_screen_held"][0]:
        t_ok = type_ok(c, ev)
        ev["tNamed"] = wait_until(lambda: (lambda s: s[-1:] == ["PlaceLiftState"] or (s[-2:] == ["PlaceLiftState", "CoopState"] and code(c) == 53))(stk(c)), 5.0)
        r.cell("naming_finished", ev["tNamed"] is not None, "client top PlaceLiftState (or a 53 over it) %s s after "
               "the OK (want <= 5)" % ev["tNamed"])
        done, trace2 = {}, []
        def check():
            el = round(time.time() - t_ok, 2)
            if "done" not in done and top(h) == "GeoscapeState" and newer(h, ev["before"]):
                done["done"] = el
            if "close" not in done and "CoopState" not in stk(c):
                done["close"] = el
            return len(done) == 2
        watch(b, t_ok, DONE_S, trace2, codes, check)
        ev["afterOk"] = {"done": done, "trace": trace2, "coopSave": [ln.split("\t")[-1] for ln in logl(c) if "[coop-save]" in ln]}
        r.cell("naming_save_done", "done" in done, "host GeoscapeState with %s newer than the trigger %s s after the "
               "OK (want <= %s)" % (QK, done.get("done"), DONE_S))
        f = read_save(os.path.join(h.user_dir, "xcom1", QK)) if "done" in done else None
        ev["file"] = f
        r.cell("naming_save_has_name", f is not None and has_name(f), "the file's client blob bases %s (want %r)"
               % ([x["bases"] for x in (f or {}).get("blobs", [])], NEWNAME))
        r.cell("naming_client_clear", "close" in done, "client stack free of CoopState %s s after the OK (want <= %s); "
               "now %s" % (done.get("close"), DONE_S, stk(c)[-2:]))
        if top(c) == "PlaceLiftState":
            ev["tLift"] = lift(b, ev)
            r.cell("naming_lift_placed", ev["tLift"] is not None, "client top BasescapeState %s s after the lift click "
                   "(want <= 5)" % ev["tLift"])
        else:
            r.cell("naming_lift_placed", False, "not reached: client top %s, not PlaceLiftState" % top(c))
    r.cell("naming_no_995", 995 not in codes, "client CoopState codes seen in the row %s (want no 995)"
           % sorted(x for x in codes if x))
    if not r.res["naming_screen_held"][0]:
        raise Stop("naming_screen_held failed: no NEWNAME typed (the client's top is %s)" % top(c))
def row_control(b, r):
    h, c, ev = b.host, b.client, r.ev
    to_name(b, r)
    type_ok(c, ev)
    r.need(wait_until(lambda: top(c) == "PlaceLiftState", STATE_S) is not None, "client top %s after the name's OK" % top(c))
    r.need(lift(b, ev) is not None, "client top %s after the lift click" % top(c))
    ev["geo"] = cw(c, "GEOSCAPE")["after"]
    cc = census(c)
    ev["pre"] = {"stack": cc["stack"], "own": own(cc)}
    r.need(cc["stack"] == ["GeoscapeState"] and any(x[1] == NEWNAME for x in own(cc)), "client on GeoscapeState with %s (%s)" % (NEWNAME, ev["pre"]))
    trigger(b, r)
    trace, codes, done = [], set(), {}
    def check():
        if "done" not in done and top(h) == "GeoscapeState" and newer(h, r.ev["before"]):
            done["done"] = round(time.time() - r.tTrig, 2)
        return False  # control_no_995 watches the whole DONE_S
    watch(b, r.tTrig, DONE_S, trace, codes, check)
    ev["save"] = {"done": done, "trace": trace}
    r.cell("control_save_done", "done" in done, "host GeoscapeState with %s newer than the trigger %s s after it (want "
           "<= %s)" % (QK, done.get("done"), DONE_S))
    f = ev["file"] = read_save(os.path.join(h.user_dir, "xcom1", QK)) if newer(h, r.ev["before"]) else None
    r.cell("control_save_has_name", f is not None and has_name(f), "the file's client blob bases %s (want %r)"
           % ([x["bases"] for x in (f or {}).get("blobs", [])], NEWNAME))
    r.cell("control_no_995", 995 not in codes, "client CoopState codes during DONE_S %s (want no 995)"
           % sorted(x for x in codes if x))
def row_key_miss(b, r):
    h, c, ev = b.host, b.client, r.ev
    on = q(c, {"cmd": "force_stream_key_miss", "on": True})
    ev["keyMissOn"] = on
    r.need(on.get("ok") and on.get("on") is True, "force_stream_key_miss on: %s" % on)
    trigger(b, r)
    trace, codes = [], set()
    watch(b, r.tTrig, F_WINDOW, trace, codes)
    gro, ht, hc = growth(r.s1, True), top(h), code(h)
    ev["window"] = {"trace": trace, "growth": gro}
    r.cell("key_miss_once", gro["loop"] == 1, "growth in F_WINDOW %s (want loop == 1)" % js(gro))
    r.cell("key_miss_host_waits", ht == "CoopState" and hc == 54, "host top %s code %s at +F_WINDOW (want CoopState "
           "54)" % (ht, hc))
    t_off = time.time()
    off = ev["keyMissOff"] = q(c, {"cmd": "force_stream_key_miss", "on": False})
    r.need(off.get("ok") and off.get("on") is False, "force_stream_key_miss off: %s" % off)
    ev["tHeal"] = wait_until(lambda: top(h) == "GeoscapeState" and newer(h, ev["before"]) and "CoopState" not in stk(c), DONE_S, POLL)
    r.cell("key_miss_heals", ev["tHeal"] is not None, "host GeoscapeState, %s newer than the trigger, no client "
           "CoopState %s s after the key miss is off (want <= %s); now %s / %s"
           % (QK, ev["tHeal"], DONE_S, stk(h)[-1:], stk(c)[-2:]))
    time.sleep(1.0)

class X:  # the file's run state: failing cells, every process's alive-until-shutdown record
    def __init__(self): self.fails, self.alive = [], []
def run_pair(x, pair, rows):
    b = Boot(pair)
    try:
        ev = {"key": KEY, "slot": harness.HARNESS_SLOT, "cpu": cpu(), "t": now()}
        try:
            ok, bev = bring_up(b)
            ev.update(bev)
        except Exception as e:  # noqa: BLE001 - a boot that raises is a boot miss
            ok, ev["error"] = False, ("%s: %s" % (type(e).__name__, e))[:400]
        print("EVIDENCE boot %s: %s" % (pair, js(ev)), flush=True)
        if not ok:
            print("CAPTURE boot %s: %s" % (pair, js(capture(b))), flush=True)
            for rid, fn in rows:
                for cid in dict(ROWS)[rid]:
                    print("FAIL %s %s: boot" % (cid, "FIX" if cid in FIX else "GUARD"), flush=True)
                    x.fails.append(cid)
                print("FAIL %s: boot" % rid, flush=True)
            return
        for rid, fn in rows:
            r = Row(x, b, rid)
            try:
                fn(b, r)
                r.finish()
            except Stop as e:
                r.finish(str(e))
            except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
                r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        miss_off = q(b.client, {"cmd": "force_stream_key_miss", "on": False}).get("ok") if alive(b.client) else None
        for gc in (b.client, b.host):
            rec = [pair, gc.name, alive(gc)] + (["keyMissOff %s" % miss_off] if gc is b.client else [])
            try:
                if alive(gc):
                    gc.shutdown(expected_returncodes=OKRC)
                rec.append(gc.proc.poll() if gc.proc else None)
            except Exception as e:  # noqa: BLE001
                rec.append(str(e)[:200])
            x.alive.append(rec)
def main():
    x, crash0 = X(), crashes()
    T0[0] = time.time()
    run_pair(x, "name_open", (("naming", row_naming),))
    run_pair(x, "name_set", (("control", row_control), ("key_miss", row_key_miss)))
    new = crashes() - crash0
    kinds = {}
    for p in new:
        kinds[kind(p)] = kinds.get(kind(p), 0) + 1
    print("EVIDENCE END: %s" % js({"newCrashByKind": kinds, "dmp": sorted(os.path.basename(p) for p in new if p.endswith(".dmp")),
                                   "aliveAndShutdownRc": x.alive, "crashDir": harness.CRASH_DIR, "cpu": cpu()}), flush=True)
    cl = [cid for _r, cs in ROWS for cid in cs]
    print("SUMMARY test_save_during_naming: %d/%d cells pass; failing %s; wall %.1f s"
          % (len(cl) - len(set(x.fails)), len(cl), sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
