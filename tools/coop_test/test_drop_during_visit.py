"""test_drop_during_visit.py: a partner drop while the HOST views the partner's base.

In a SEPARATE co-op campaign the host who clicks the partner's base on the globe sees the partner's world as its live
world (CoopState 55 parks the host's own world in memory as "basehost"). If the wait window 62 opened over the
partner's base screen with the view still the live world, SAVE & QUIT there would write the partner's base as the
host's world, and a rejoin + RESUME would leave the host on the view under "Save failed (MEMORY)" (995) with no host
base on the partner's globe. So the drop reloads "basehost" as the base screen's GEOSCAPE does and opens the 62 once
the host's own world is back.
Row save_reload (boot drop_visit_save_*, reload pair drop_visit_reload_*): the host's real globe click on the client's
  base (VISIT), the inside read, the baseline, client.kill(), the drop read at the host's first top 62, the real
  SAVE & QUIT -> list -> the save name by key events -> SAVE GAME, the file, a reload pair. Cells save_reload-pre
  (GUARD: the inside read is inside the view), save_reload-stack (FIX: [GeoscapeState, CoopState] 62),
  save_reload-world (FIX: exactly the own base, FUNDS, S0), save_reload-buttons (GUARD), save_reload-log (FIX: UNWIND
  1, LGPUSH >= 1, OPEN 1), save_reload-file (FIX), save_reload-reload (FIX), save_reload-common (GUARD).
Row rejoin_resume (boot drop_visit_rejoin_*, rejoin drop_visit_rejoin_client2): VISIT, the baseline, kill, the 62, a
  fresh client joins as the recorded name, the host's real RESUME, the host watched every 0.05 s for W_AFTER, the
  client's geo_state every 0.25 s for the host's marker (W_MARK). Cells rejoin_resume-pre (GUARD), rejoin_resume-no995
  (FIX), rejoin_resume-home (FIX), rejoin_resume-marker (FIX), rejoin_resume-client (GUARD).
A build that keeps the view live under the 62 fails every FIX cell; every GUARD cell passes either way.
One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; every row runs after a failure; a
precondition miss ends its row (later cells "not reached"); a boot miss fails the row's -pre cell with ONE CAPTURE
line. Real presses only (globe click, SAVE & QUIT, list row, key events, SAVE GAME, OK, RESUME); staging: set_funds
FUNDS. ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_drop_during_visit.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, math, os, sys, time  # noqa: E401
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49265"
HOST_POS = (0.90, -0.60)                       # rad; the host base on land, the client's marker clickable
FUNDS_C = (4111111, 4222222, 4333333)          # FUNDS: the first that differs from the host's and the client's boot funds
NAMES = {"save_reload": "visitdrop"}                          # a taken name gets "x" appended
QUICK, PROBE = "_quick_.asav", "drop_visit_probe.sav"
WAIT_LIST, STABLE_S, BOOT_S = 1.0, 2.0, 60.0
W_62, W_UI, W_VISIT, W_SAVE, W_JOIN, W_AFTER, W_MARK = 10.0, 10.0, 60.0, 60.0, 120.0, 10.0, 15.0
ZOOM = [0.45, 0.60, 0.90, 1.40, 2.25, 3.60]
CLICKS = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2), (2, -2), (-2, 2), (3, 0), (-3, 0), (0, 3), (0, -3)]
RC_OK = (0, 3221226505)
NEEDLES = {"UNWIND": "[coop] the partner dropped while the host views its base",
           "OPEN": "[coop] the host's own world is back",
           "LGPUSH": "[coop-ui] push class OpenXcom::LoadGameState",
           "LISTPUSH": "[coop-ui] push class OpenXcom::ListSaveState"}
CELLS = {"save_reload": ["save_reload-pre", "save_reload-stack", "save_reload-world", "save_reload-buttons",
                         "save_reload-log", "save_reload-file", "save_reload-reload", "save_reload-common"],
         "rejoin_resume": ["rejoin_resume-pre", "rejoin_resume-no995", "rejoin_resume-home", "rejoin_resume-marker",
                           "rejoin_resume-client"]}
T0 = time.time()
RESULTS = []

class Stop(Exception):  # a precondition missed: the row ends here
    pass

# ----- probes -----
def now(): return round(time.time() - T0, 2)
def short(e, n=300): return ("%s: %s" % (type(e).__name__, e))[:n]
def js(v): return json.dumps(v, sort_keys=True, default=str)
def pick(r, keys): return {k: r.get(k) for k in keys}
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001 - a probe failure is a value
        return {"error": short(e, 200)}
def stack(gc): return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]
def top(gc): return (stack(gc) or [None])[-1]
def coop(gc): return pick(q(gc, {"cmd": "get_coop"}), ("insideCoopBase", "resumeAck", "clientName", "onConnect"))
def dlg(gc): return pick(q(gc, {"cmd": "coop_dialog_info"}), ("code", "title", "backText", "backVisible", "saveQuitVisible", "abandonVisible"))
def gs(gc): return q(gc, {"cmd": "geo_state"})
def own_base(g): return next((b for b in g.get("bases", []) if not b.get("coopIcon") and not b.get("coopBase")), None)
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "**", "crash_*"), recursive=True))
def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log") if gc else ""
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if p and os.path.exists(p) else []
def tail(gc, n=40): return [ln.split("\t")[-1][:300] for ln in log(gc)[-n:]]
def needles(gc, n0):
    ls = log(gc)[n0:]
    return {k: sum(1 for ln in ls if v in ln) for k, v in NEEDLES.items()}
def files(gc):
    out = {}
    for p in glob.glob(os.path.join(gc.user_dir, "xcom1", "*")):
        try:
            if os.path.isfile(p):
                out[os.path.basename(p)] = [os.path.getsize(p), os.stat(p).st_mtime_ns]
        except FileNotFoundError:  # renamed after the listing (the save's .bak -> .asav move)
            pass
    return out
def cpu():
    c = harness.cpu_load()
    return {"cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}
def wait(pred, timeout, interval=0.25):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 3)
        time.sleep(interval)
def world(gc):
    """stack, coop flags, the top 62's buttons, geo_state bases [name, coopBase, coopIcon] + funds, get_soldiers ids per base"""
    g, s, st = gs(gc), q(gc, {"cmd": "get_soldiers"}), stack(gc)
    return {"stack": st, "coop": coop(gc), "dlg": dlg(gc) if st[-1:] == ["CoopState"] else None, "funds": g.get("funds"),
            "bases": [[b.get("name"), bool(b.get("coopBase")), bool(b.get("coopIcon"))] for b in g.get("bases", [])],
            "soldiers": [[b.get("name"), bool(b.get("coopIcon")), sorted(z.get("id") for z in b.get("soldiers", []))] for b in s.get("bases", [])]}
def own_only(x, w):
    """exactly the host's own base (coopBase false, coopIcon false), funds FUNDS, its soldiers S0"""
    sol = [b[2] for b in w["soldiers"] if b[0] == x.HB and not b[1]]
    bad = [] if w["bases"] == [[x.HB, False, False]] else ["bases %s (want [[%s, false, false]])" % (w["bases"], x.HB)]
    bad += [] if w["funds"] == x.FUNDS else ["funds %s (want %s)" % (w["funds"], x.FUNDS)]
    bad += [] if sol == [x.S0] else ["soldiers on %s %s (want %s)" % (x.HB, sol, x.S0)]
    return not bad, "; ".join(bad) or "bases %s, funds %s, soldiers %s" % (w["bases"], w["funds"], x.S0)

# ----- the save file -----
def _world(w):
    return {"bases": [[bb.get("name"), sorted(s.get("id") for s in bb.get("soldiers") or [])] for bb in w.get("bases") or []],
            "funds": (w.get("funds") or [None])[-1] if isinstance(w.get("funds"), list) else w.get("funds")}
def read_save(path):
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with open(path, encoding="utf-8", errors="replace") as fh:
        docs = [d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict)]
    out = {"file": os.path.basename(path), "header": {k: v for k, v in docs[0].items() if not isinstance(v, (list, dict))} if docs else None}
    w = next((d for d in docs if "bases" in d), None)
    out["world"] = _world(w) if w else None
    return out

# ----- real presses and the globe picker -----
def real_click(gc, text, timeout=15.0):
    t0, ws = time.time(), []
    while time.time() - t0 < timeout:
        ws = [w for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if (w.get("text") or "").strip().lower() == text.lower()]
        w = next((w for w in ws if w.get("visible") is True and w.get("hidden") is False), None)
        if w is not None:
            return q(gc, {"cmd": "click_widget", "match": w.get("text")})
        time.sleep(0.02)
    return {"ok": False, "error": "button %r not shown within %.0f s (%s)" % (text, timeout, ws[:2])}
def project(G, lon, lat, geom):
    cl, ct = G["globeLon"], G["globeLat"]
    R = ZOOM[int(G["globeZoom"])] * geom["H"]
    x = geom["W"] // 2 + math.floor(R * math.cos(lat) * math.sin(lon - cl))
    y = geom["H"] // 2 + math.floor(R * (math.cos(ct) * math.sin(lat) - math.sin(ct) * math.cos(lat) * math.cos(lon - cl)))
    return x, y
def geometry(gc):
    b = next((w for w in gc.ok({"cmd": "list_widgets"}).get("widgets", []) if str(w.get("text") or "").upper().startswith("INTERCEPT")), None)
    sw, sh = (b["x"] + 63, 2 * (b["y"] + 100)) if b else (320, 200)
    return {"W": sw - 64, "H": sh}
def read_globe(path):
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with open(path, encoding="utf-8", errors="replace") as fh:
        d = next((d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict) and "bases" in d), {})
    return {k: d.get(k) for k in ("globeLon", "globeLat", "globeZoom")}
def picker(x):
    """a quick save + a named probe save (the host's globe view), the window scale from a destination screen's
    CANCEL"""
    h = x.host
    qpath, spath = (os.path.join(h.user_dir, "xcom1", f) for f in (QUICK, PROBE))
    tq = time.time()
    q(h, {"cmd": "save_game_ui", "type": "quick"})
    okq, _ = wait(lambda: os.path.exists(qpath) and os.path.getmtime(qpath) >= tq - 1, 30, 0.25)
    tf = time.time()
    wait(lambda: time.time() - tf >= 2.0 and top(h) == "GeoscapeState", 10, 0.25)
    geo.drain_popups(h)
    q(h, {"cmd": "save_game", "file": PROBE})
    okn, _ = wait(lambda: os.path.exists(spath) and os.path.getsize(spath) > 0, 30, 0.25)
    time.sleep(1.0)
    G = read_globe(spath) if okn else {}
    cr = next((k for k in (own_base(gs(h)) or {}).get("crafts", []) if not k.get("coop")), None)
    q(h, {"cmd": "open_select_destination", "craft_id": cr and cr["id"], "craft_type": cr and cr["type"]})
    time.sleep(0.4)
    cw = q(h, {"cmd": "click_widget", "match": "CANCEL"})
    time.sleep(0.5)
    x.pk = {"G": G, "geom": geometry(h), "scale": cw.get("baseX") and {"x": cw["winX"] / cw["baseX"], "y": cw["winY"] / cw["baseY"]}}
    if not okq or not G or None in G.values() or not x.pk["scale"] or top(h) != "GeoscapeState":
        raise Stop("picker: quick %s, probe %s, %s, top %s" % (okq, okn, js(x.pk), stack(h)))

def visit(x):
    """VISIT: the host's real click on the client's base (13 offsets) until CoopState 50 / BasescapeState; inside within W_VISIT"""
    h = x.host
    px, py = project(x.pk["G"], x.cb["lon"], x.cb["lat"], x.pk["geom"])
    tries = []
    for dx, dy in CLICKS:
        q(h, {"cmd": "inject_input", "kind": "click", "x": int((px + dx) * x.pk["scale"]["x"] + 1), "y": int((py + dy) * x.pk["scale"]["y"] + 1)})
        seen, _ = wait(lambda: top(h) not in ("GeoscapeState", "MultipleTargetsState"), 0.9, 0.02)
        tries.append([px + dx, py + dy, top(h)])
        if seen:
            break
    v, s = wait(lambda: coop(h).get("insideCoopBase") is True and top(h) == "BasescapeState", W_VISIT, 0.02)
    x.ev_visit = {"tries": tries, "inside_s": s}
    if not v:
        raise Stop("VISIT: the host not inside the client's base within %.0f s (tries %s, stack %s)" % (W_VISIT, tries, stack(h)))
    time.sleep(1.0)

# ----- boot, staging, the drop -----
def spawn_pair(x, tag, saves=()):
    x.host = GameClient("host", None, make_user_dir(tag + "_host", saves=saves))
    x.client = GameClient("client", None, make_user_dir(tag + "_client"))
    x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()  # noqa: E702

def settle(x, limit=BOOT_S):
    t0, last, tch = time.time(), None, time.time()
    while time.time() - t0 < limit:
        s = (tuple(stack(x.host)), tuple(stack(x.client)))
        if s != last:
            last, tch = s, time.time()
        if s[0][-1:] == s[1][-1:] == ("GeoscapeState",) and time.time() - tch >= STABLE_S:
            return round(time.time() - t0, 3)
        time.sleep(0.25)
    raise Stop("both tops GeoscapeState not stable %.0f s within %.0f s: %s" % (STABLE_S, limit, last))

def boot(x, tag):
    """fresh pair, a new SEPARATE campaign (host base at HOST_POS), slow clocks, settle; FUNDS staged; S0, CB, the client's ids SC"""
    spawn_pair(x, tag)
    session.HOST_LON, session.HOST_LAT = HOST_POS
    session.new_campaign(x.host, x.client, port=KEY)
    geo.slow_clock(x.host, x.client)
    settle(x)
    gh, gc_ = gs(x.host), gs(x.client)
    x.hb, x.cb = own_base(gh), own_base(gc_)
    x.FUNDS = next(f for f in FUNDS_C if f not in (gh.get("funds"), gc_.get("funds")))
    x.ev["funds"] = {"boot": [gh.get("funds"), gc_.get("funds")], "FUNDS": x.FUNDS, "set": q(x.host, {"cmd": "set_funds", "value": x.FUNDS}).get("ok")}
    x.HB, x.CB = x.hb.get("name"), x.cb.get("name")
    sh, sc = q(x.host, {"cmd": "get_soldiers"}), q(x.client, {"cmd": "get_soldiers"})
    x.S0 = sorted(z.get("id") for b in sh.get("bases", []) if b.get("name") == x.HB and not b.get("coopIcon") for z in b.get("soldiers", []))
    x.SC = sorted(z.get("id") for b in sc.get("bases", []) if b.get("name") == x.CB and not b.get("coopIcon") for z in b.get("soldiers", []))
    x.ev.update(HB=x.HB, CB=x.CB, S0=x.S0, SC=x.SC)
    picker(x)

def read_inside(x, r, name):
    """the inside read (save_reload-pre): host top BasescapeState, insideCoopBase, every live base coopBase, one named
    CB, funds != FUNDS"""
    w = r.ev["insideRead"] = world(x.host)
    ok = (w["stack"][-1:] == ["BasescapeState"] and w["coop"].get("insideCoopBase") is True and w["bases"]
          and all(b[1] for b in w["bases"]) and [b[0] for b in w["bases"]] == [x.CB] and w["funds"] != x.FUNDS)
    r.cell(name, ok, "inside read: stack %s, inside %s, bases %s, funds %s "
           "(want BasescapeState, true, [[%s, true, *]], != %s)"
           % (w["stack"], w["coop"].get("insideCoopBase"), w["bases"], w["funds"], x.CB, x.FUNDS))
    if not ok:
        raise Stop("inside read")

def baseline(x):
    x.n_h, x.crB, x.filesB = len(log(x.host)), crashes(), files(x.host)
    x.cname = coop(x.host).get("clientName")

def drop_62(x):
    """client.kill(); poll the host every 0.02 s; the drop read at its first top CoopState 62"""
    h = x.host
    x.client.kill()
    t0, trace, last = time.time(), [], None
    while time.time() - t0 < W_62:
        st = stack(h)
        c = dlg(h).get("code") if st[-1:] == ["CoopState"] else None
        if (st, c) != last:
            trace.append([round(time.time() - t0, 3), st, c])
            last = (st, c)
        if c == 62:
            D = world(h)
            D.update(needles=needles(h, x.n_h), t62=round(time.time() - t0, 3), trace=trace)
            return D
        time.sleep(0.02)
    raise Stop("no host top CoopState 62 within %.0f s of the drop (trace %s)" % (W_62, trace[-4:]))

def save_quit(x, name):
    """the host's real SAVE & QUIT -> ListSaveState; WAIT_LIST; the new-slot row (injected click); NAME by key events; SAVE GAME;
    MainMenuState within W_SAVE. Returns the file path or None."""
    h = x.host
    sq = real_click(h, "SAVE & QUIT", 10)
    sc = {"x": sq["winX"] / sq["baseX"], "y": sq["winY"] / sq["baseY"]} if sq.get("baseX") else x.pk["scale"]
    v, _ = wait(lambda: top(h) == "ListSaveState", 10, 0.02)
    tls = [w for w in q(h, {"cmd": "list_widgets"}).get("widgets", []) if "TextList" in str(w.get("type"))]
    if not v or not tls:
        raise Stop("SAVE & QUIT %s: no ListSaveState / TextList (stack %s)" % (sq.get("ok"), stack(h)))
    tl = max(tls, key=lambda w: (w.get("h") or 0))
    time.sleep(WAIT_LIST)
    ed, x.slot = False, None
    for dy in (3, 4, 2, 5):
        q(h, {"cmd": "inject_input", "kind": "click", "x": int((tl["x"] + 20) * sc["x"] + 1), "y": int((tl["y"] + dy) * sc["y"] + 1)})
        time.sleep(0.6)
        ed = any(w.get("visible") for w in q(h, {"cmd": "list_widgets"}).get("widgets", []) if "TextEdit" in str(w.get("type")))
        if ed:
            x.slot = "inject dy %d" % dy
            break
    if ed:
        for ch in name:
            q(h, {"cmd": "inject_input", "kind": "key", "key": ord(ch)})
            time.sleep(0.06)
        time.sleep(0.3)
        real_click(h, "SAVE GAME", 5)
    else:
        x.slot = "fallback list_save_confirm (the injected row click opened no edit)"
        q(h, {"cmd": "list_save_confirm", "name": name})
    p = os.path.join(h.user_dir, "xcom1", name + ".sav")
    v, x.mm_s = wait(lambda: not alive(h) or ("MainMenuState" in stack(h) and os.path.exists(p)), W_SAVE, 0.02)
    x.mm = bool(v) and alive(h)
    time.sleep(1.0)
    return p if os.path.exists(p) else None

def shut(gc):
    try:
        if alive(gc):
            gc.shutdown(expected_returncodes=RC_OK)
        return gc.proc.poll() if gc and gc.proc else None
    except Exception as e:  # noqa: BLE001 - a failed shutdown is a value (save_reload-common / rejoin_resume-client)
        return short(e, 200)

# ----- rows -----
class Row:
    def __init__(self, rid):
        self.rid, self.cells, self.ev, self.done = rid, CELLS[rid], {}, {}
        self.x = SimpleNamespace(host=None, client=None, ev=self.ev, n_h=0, crB=crashes(), mm=False, mm_s=None)

    def cell(self, name, ok, detail):
        self.done[name] = bool(ok)
        RESULTS.append((name, bool(ok)))
        print("%s %s: %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)

    def capture(self, why):
        d = {"why": why}
        for n in ("host", "client"):
            gc = getattr(self.x, n)
            d[n] = ({"alive": True, "stack": stack(gc), "dlg": dlg(gc), "coop": coop(gc), "log": tail(gc)} if alive(gc)
                    else {"alive": False, "log": tail(gc)})
        print("CAPTURE %s: %s" % (self.rid, js(d)), flush=True)

    def close(self, why):
        for n in self.cells:
            if n not in self.done:
                self.cell(n, False, "not reached: %s" % why)
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        bad = [n for n in self.cells if not self.done.get(n)]
        print("ROW %s: %s" % (self.rid, "PASS" if not bad else "FAIL (%d failing: %s)" % (len(bad), bad)), flush=True)

def reload_pair(r, src):
    """a fresh pair with the file in the host's user dir: the menu load, host_tcp, join, lobby_action, resumeAck, RESUME, settle; census"""
    y = SimpleNamespace(host=None, client=None)
    ev = r.ev["reload"] = {}
    try:
        spawn_pair(y, "drop_visit_reload", saves=(src,))
        h, c = y.host, y.client
        q(h, {"cmd": "load_save_menu", "file": os.path.basename(src)})
        if not wait(lambda: not alive(h) or "HostMenu" in stack(h), 60, 0.25)[0] or not alive(h):
            raise Stop("reload: no HostMenu (%s)" % stack(h))
        q(h, {"cmd": "host_tcp", "server": "TestSrv", "port": KEY, "player": "HostPlayer"})
        if not wait(lambda: "LobbyMenu" in stack(h), 30, 0.25)[0]:
            raise Stop("reload: no LobbyMenu (%s)" % stack(h))
        q(c, {"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
        if not wait(lambda: coop(h).get("clientName") == "ClientPlayer", 60, 0.25)[0]:
            raise Stop("reload: the client not registered in the resume lobby")
        treg = time.time()
        ev["eligible"] = wait(lambda: time.time() - treg >= 2.0 and q(h, {"cmd": "lobby_state"}).get("startEligible"), 10, 0.25)
        q(h, {"cmd": "lobby_action"})
        if not wait(lambda: not alive(h) or coop(h).get("resumeAck"), 120, 0.25)[0] or not alive(h):
            raise Stop("reload: no resumeAck within 120 s")
        d, _ = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") in (60, 62) and dlg(h).get("backVisible") and dlg(h), 30, 0.25)
        ev["resume"] = real_click(h, (d or {}).get("backText") or "RESUME", 5).get("ok")
        ev["settle"] = settle(y, 90)
        ev["host"] = world(h)
        return ev["host"]
    finally:
        ev["rc"] = [shut(y.client), shut(y.host)]

def row_save_reload():
    r = Row("save_reload")
    x = r.x
    try:
        try:
            boot(x, "drop_visit_save")
            visit(x)
        except Exception as e:  # noqa: BLE001 - a boot miss
            r.capture(short(e))
            r.cell("save_reload-pre", False, "boot / VISIT: %s" % short(e))
            raise Stop("boot")
        r.ev["visit"] = x.ev_visit
        read_inside(x, r, "save_reload-pre")
        baseline(x)
        D = r.ev["dropRead"] = drop_62(x)
        d = D["dlg"] or {}
        r.cell("save_reload-stack", D["stack"] == ["GeoscapeState", "CoopState"] and d.get("code") == 62,
               "drop read host stack %s, top code %s at %.3f s (want [GeoscapeState, CoopState], 62)"
               % (D["stack"], d.get("code"), D["t62"]))
        ok, why = own_only(x, D)
        r.cell("save_reload-world", ok, "drop read: " + why)
        r.cell("save_reload-buttons", d.get("saveQuitVisible") is True and d.get("abandonVisible") is True
               and d.get("backVisible") is False,
               "SAVE & QUIT %s, ABANDON %s, RESUME %s (want true, true, false)" % (d.get("saveQuitVisible"), d.get("abandonVisible"), d.get("backVisible")))
        n = D["needles"]
        r.cell("save_reload-log", n["UNWIND"] == 1 and n["LGPUSH"] >= 1 and n["OPEN"] == 1,
               "host log since the baseline: UNWIND %d, LGPUSH %d, OPEN %d (want 1, >= 1, 1)"
               % (n["UNWIND"], n["LGPUSH"], n["OPEN"]))
        name = NAMES["save_reload"]
        while os.path.exists(os.path.join(x.host.user_dir, "xcom1", name + ".sav")):
            name += "x"
        p = save_quit(x, name)
        r.ev.update(slot=x.slot, mainMenu=[x.mm, x.mm_s], newFiles=sorted(k for k, v in files(x.host).items() if x.filesB.get(k) != v))
        if not p:
            raise Stop("no %s.sav after SAVE GAME (main menu %s)" % (name, x.mm))
        f = r.ev["file"] = read_save(p)
        fw = f["world"] or {}
        r.cell("save_reload-file", fw.get("bases") == [[x.HB, x.S0]] and fw.get("funds") == x.FUNDS,
               "%s.sav world bases %s, funds %s (want [[%s, %s]], %s; no %s)" % (name, fw.get("bases"), fw.get("funds"), x.HB, x.S0, x.FUNDS, x.CB))
        r.ev["rc_save_reload"] = [shut(x.client), shut(x.host)]
        w = reload_pair(r, p)
        own = [b[0] for b in w["bases"] if not b[1] and not b[2]]
        sol = [b[2] for b in w["soldiers"] if b[0] == x.HB and not b[1]]
        r.cell("save_reload-reload", own == [x.HB] and sol == [x.S0] and w["funds"] == x.FUNDS,
               "reloaded host: own bases %s, soldiers on %s %s, funds %s (want [%s], %s, %s)" % (own, x.HB, sol, w["funds"], x.HB, x.S0, x.FUNDS))
        nc = sorted(crashes() - x.crB)
        rcs = r.ev["rc_save_reload"][1:] + r.ev["reload"]["rc"]
        r.cell("save_reload-common", x.mm and all(rc in RC_OK for rc in rcs) and not nc,
               "MainMenuState %s in %s s; host / reload client / reload host exit %s; new crash files %s (want true <= %.0f s, %s, none)"
               % (x.mm, x.mm_s, rcs, nc, W_SAVE, list(RC_OK)))
        r.close("")
    except Exception as e:  # noqa: BLE001 - a precondition miss ends the row
        r.ev["stop"] = short(e, 500)
        if not isinstance(e, Stop):
            r.capture(short(e))
        r.close(short(e))
    finally:
        r.ev.setdefault("rc_save_reload", [shut(x.client), shut(x.host)])

def row_rejoin_resume():
    r = Row("rejoin_resume")
    x = r.x
    c2 = None
    try:
        try:
            boot(x, "drop_visit_rejoin")
            visit(x)
        except Exception as e:  # noqa: BLE001 - a boot miss
            r.capture(short(e))
            r.cell("rejoin_resume-pre", False, "boot / VISIT: %s" % short(e))
            raise Stop("boot")
        r.ev["visit"] = x.ev_visit
        baseline(x)
        h = x.host
        D = r.ev["dropRead"] = drop_62(x)
        d62 = (D["dlg"] or {}).get("saveQuitVisible") is True
        if not d62:
            d62 = bool(wait(lambda: dlg(h).get("code") == 62 and dlg(h).get("saveQuitVisible"), W_62, 0.02)[0])
        c2 = x.client = GameClient("client", None, make_user_dir("drop_visit_rejoin_client2"))
        c2.spawn()
        c2.connect()
        codes, tj = [], time.time()

        def seen():
            st = stack(h)
            c = dlg(h).get("code") if st[-1:] == ["CoopState"] else None
            if c is not None and (not codes or codes[-1] != c):
                codes.append(c)
            return st
        r.ev["join"] = q(c2, {"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": x.cname}).get("ok")
        ack, ack_s = wait(lambda: seen() and coop(h).get("resumeAck"), W_JOIN, 0.25)
        tr = None
        if ack:
            t0 = time.time()
            while time.time() - t0 < 30 and tr is None:
                st = seen()
                if st and "Profile" in st[-1]:
                    real_click(h, "OK", 5)
                elif st[-1:] == ["CoopState"] and dlg(h).get("code") in (60, 62) and dlg(h).get("backVisible"):
                    tr = time.time() if real_click(h, dlg(h).get("backText") or "RESUME", 5).get("ok") else None
                time.sleep(0.05)
        r.ev.update(ack=[bool(ack), ack_s], resumeAfterJoin=round(tr - tj, 3) if tr else None)
        r.cell("rejoin_resume-pre", d62 and bool(ack) and tr is not None,
               "62 with SAVE & QUIT %s at %.3f s; resumeAck %s in %s s; RESUME clicked %s (want all true)"
               % (d62, D["t62"], bool(ack), ack_s, tr is not None))
        if tr is None:
            raise Stop("rejoin_resume-pre")
        trace, last, marker, tcl = [], None, None, 0.0
        while True:
            el = time.time() - tr
            if el < W_AFTER:
                st = seen()
                s = (st, coop(h).get("insideCoopBase"), codes[-1:] if st[-1:] == ["CoopState"] else None)
                if s != last:
                    trace.append([round(el, 3)] + list(s))
                    last = s
            if marker is None and el < W_MARK and time.time() - tcl >= 0.25:
                tcl = time.time()
                m = [b for b in gs(c2).get("bases", []) if b.get("coopIcon") and b.get("name") == x.HB]
                marker = round(el, 3) if m else None
            if el >= W_AFTER and (marker is not None or el >= W_MARK):
                break
            time.sleep(0.05)
        H, C = world(h), world(c2)
        r.ev.update(codes=codes, trace=trace, marker_s=marker, hostAfter=H, clientAfter=C)
        r.cell("rejoin_resume-no995", 995 not in codes and H["stack"] == ["GeoscapeState"],
               "host top codes from the join %s; stack at RESUME + %.0f s %s (want no 995, [GeoscapeState])" % (codes, W_AFTER, H["stack"]))
        sol = [b[2] for b in H["soldiers"] if b[0] == x.HB and not b[1]]
        home = H["coop"].get("insideCoopBase") is False and [x.HB, False, False] in H["bases"] and sol == [x.S0]
        r.cell("rejoin_resume-home", home, "insideCoopBase %s, host bases %s, soldiers on %s %s "
               "(want false, own [%s, false, false], %s)"
               % (H["coop"].get("insideCoopBase"), H["bases"], x.HB, sol, x.HB, x.S0))
        r.cell("rejoin_resume-marker", marker is not None,
               "the client's %s marker (coopIcon true) at %s s after the RESUME (want within %.0f s); client bases %s"
               % (x.HB, marker, W_MARK, C["bases"]))
        csol = [b[2] for b in C["soldiers"] if b[0] == x.CB and not b[1]]
        nc = sorted(crashes() - x.crB)
        r.cell("rejoin_resume-client", [x.CB, False, False] in C["bases"] and csol == [x.SC] and alive(h) and alive(c2)
               and not nc,
               "client own %s in %s, soldiers %s (want %s); host / client alive %s / %s; new crash files %s"
               % (x.CB, C["bases"], csol, x.SC, alive(h), alive(c2), nc))
        r.close("")
    except Exception as e:  # noqa: BLE001 - a precondition miss ends the row
        r.ev["stop"] = short(e, 500)
        if not isinstance(e, Stop):
            r.capture(short(e))
        r.close(short(e))
    finally:
        r.ev["rc"] = [shut(c2), shut(x.client), shut(x.host)]

def main():
    c0 = cpu()
    print("==== test_drop_during_visit (slot %s, key %s, exe %s) CPU %s ===="
          % (harness.HARNESS_SLOT, KEY, time.ctime(os.path.getmtime(harness.EXE)), c0), flush=True)
    for fn in (row_save_reload, row_rejoin_resume):
        fn()
    fails = [n for n, ok in RESULTS if not ok]
    print("\n==== test_drop_during_visit: %d/%d cells PASS, wall %.1f s, CPU %s -> %s ===="
          % (len(RESULTS) - len(fails), len(RESULTS), time.time() - T0, c0, cpu()),
          flush=True)
    if fails:
        print("FAILING: %s" % fails, flush=True)
    return 0 if not fails else 2

if __name__ == "__main__":
    sys.exit(main())
