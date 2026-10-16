"""W2-H73 DDP - tools/coop_test/test_w2_drop_during_visit_paths.py: the other paths of a partner drop while the HOST views the partner's base.

In a SEPARATE co-op campaign a host visiting the partner's base (CoopState 55: its own world parked as "basehost", the partner's world live)
gets the drop's wait window 62 over the view today. R-TR9-2 fix (m): the host's drop reloads "basehost" as the base screen's GEOSCAPE does,
then opens the 62 over its own geoscape. This file covers the -3 arm, a screen open inside the base, the control and a named ironman campaign.
Spec docs rewrite/prompts/w2h73_drop_during_visit.md (f) (QH73-1 .. QH73-5 (a), R-H73-1); pins docs rewrite/w2h73-task0/sa/CONSTANTS.md;
lead L-TR9-2, capture rewrite/ltr9-2-cap (F20285-F20294).
Row T (H5, E3; boot w2h73_t_*): VISIT, read I, B, the host's TEST-ONLY force_server_error (W2-H59), READ D at the first host top 62.
  T-pre (GUARD: read I inside the view; the lever ok; SERVER +1), T-stack (RED: [GeoscapeState, CoopState] 62), T-world (RED: the own base
  with FUNDS, no view base), T-inside (RED: insideCoopBase false at READ D and 1 s later; ruling R-H73-2), T-common (GUARD).
Row S (a screen open inside the base; boot w2h73_s_*): VISIT, the host's real SOLDIERS click, SoldiersState on top (W_UI), B, kill, READ D.
  S-pre (GUARD), S-stack (RED), S-world (RED: exactly the own base, FUNDS, S0), S-common (GUARD).
Row G (C1-ctl, the control; boot w2h73_g_*): no visit; B; kill; READ D; SAVE & QUIT -> list -> NAME_G -> SAVE GAME; the file.
  G-stack, G-world, G-log (UNWIND 0, OPEN 0), G-file, G-common (all GUARD).
Row I (ironman, T0-I reached it; boot w2h73_i_*): W2-H53 boot G's SEPARATE ironman start (every host list answered NAME_I), FUNDS, VISIT by
  the globe_point route (the spec's replacement for the picker in ironman: CAP's quick save renames the world `_quick_.asav`, CONSTANTS.md),
  B, kill, the 62, SAVE & QUIT; a ListSaveState is answered by list_save_confirm NAME_I2 (the red's way out).
  I-pre (GUARD), I-nolist (RED: no ListSaveState, MainMenuState), I-file (RED: NAME_I.sav rewritten with the host's base and S0, no
  NAME_I2.sav), I-common (GUARD).
Red today: T-stack, T-world, T-inside, S-stack, S-world, I-nolist, I-file FAIL; every other cell PASS. Green (E1-E4): all PASS.
One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; every row runs after a failure; a precondition miss ends its
row (later cells "not reached"); a boot miss fails the row's first cell with ONE CAPTURE line. Real presses only; staging: set_funds FUNDS;
the TEST-ONLY lever force_server_error (row T). Helpers copied (never imported) from the capture's cap.py and test_w2_ironman_save_paths.py.
WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_w2_drop_during_visit_paths.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, math, os, subprocess, sys, time  # noqa: E401
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402

KEY = "49266"
HOST_POS = (0.90, -0.60)                       # rad; the host base on land, the client's marker clickable
FUNDS_C = (4111111, 4222222, 4333333)          # FUNDS: the first that differs from the host's and the client's boot funds
NAMES = {"G": "h73g", "I": "h73iron", "I2": "h73i2"}
QUICK, PROBE = "_quick_.asav", "w2h73_probe.sav"
WAIT_LIST, STABLE_S, BOOT_S, IRON_S, QUIET_S = 1.0, 2.0, 60.0, 150.0, 8.0
W_62, W_UI, W_VISIT, W_SAVE = 10.0, 10.0, 60.0, 60.0
ZOOM = [0.45, 0.60, 0.90, 1.40, 2.25, 3.60]
CLICKS = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2), (2, -2), (-2, 2), (3, 0), (-3, 0), (0, 3), (0, -3)]
RC_OK = (0, 3221226505)
NEEDLES = {"UNWIND": "[coop] W2-H73: the partner dropped while the host views its base",
           "OPEN": "[coop] W2-H73: the host's own world is back",
           "LGPUSH": "[coop-ui] push class OpenXcom::LoadGameState",
           "LISTPUSH": "[coop-ui] push class OpenXcom::ListSaveState",
           "SERVER": "[coop-test] force_server_error: onConnect -3 (main thread)"}
CELLS = {"T": ["T-pre", "T-stack", "T-world", "T-inside", "T-common"], "S": ["S-pre", "S-stack", "S-world", "S-common"],
         "G": ["G-stack", "G-world", "G-log", "G-file", "G-common"], "I": ["I-pre", "I-nolist", "I-file", "I-common"]}
T0 = time.time()
RESULTS = []

class Stop(Exception):  # a precondition missed: the row ends here
    pass

# ----- probes (copied from docs rewrite/ltr9-2-cap/cap.py) -----
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
def has(gc, name): return any(name in s for s in stack(gc))
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
        if os.path.isfile(p):
            out[os.path.basename(p)] = [os.path.getsize(p), os.stat(p).st_mtime_ns]
    return out
def cpu():
    ps = ("[math]::Round((Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 1).CounterSamples[0].CookedValue, 1); "
          "@(Get-Process | Where-Object { $_.ProcessName -like 'Wardogs*' }).Count")
    try:
        v = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30).stdout.split()
        return {"cpu": v[0] if v else None, "wardogs": v[1] if len(v) > 1 else None}
    except Exception as e:  # noqa: BLE001
        return {"error": short(e, 100)}
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

# ----- real presses, the globe picker (cap.py) and the globe_point route (test_w2_partner_visit_rollback :98-:121) -----
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
    """cap.py picker: a quick save + a named probe save (the host's globe view), the window scale from a destination screen's CANCEL"""
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
def visit_clicks(x, pts):
    """real clicks at window pixels until the host's top leaves the geoscape; insideCoopBase + BasescapeState within W_VISIT"""
    h, tries = x.host, []
    for wx, wy in pts:
        q(h, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy})
        seen, _ = wait(lambda: top(h) not in ("GeoscapeState", "MultipleTargetsState"), 0.9, 0.02)
        tries.append([wx, wy, top(h)])
        if seen:
            break
    v, s = wait(lambda: coop(h).get("insideCoopBase") is True and top(h) == "BasescapeState", W_VISIT, 0.02)
    x.ev["visit"] = {"tries": tries, "inside_s": s}
    if not v:
        raise Stop("VISIT: the host not inside the client's base within %.0f s (tries %s, stack %s)" % (W_VISIT, tries, stack(h)))
    time.sleep(1.0)
def visit(x):
    px, py = project(x.pk["G"], x.cb["lon"], x.cb["lat"], x.pk["geom"])
    sc = x.pk["scale"]
    visit_clicks(x, [(int((px + dx) * sc["x"] + 1), int((py + dy) * sc["y"] + 1)) for dx, dy in CLICKS])
def globe_visit(x):
    """row I: the window mapping from the host's real INTERCEPT + CANCEL clicks, globe_point on CB, real clicks (no save written)"""
    h, rr = x.host, []
    for m in ("INTERCEPT", "CANCEL"):
        r = q(h, {"cmd": "click_widget", "match": m})
        rr.append(([r.get("baseX"), r.get("baseY")], [r.get("winX"), r.get("winY")]))
        time.sleep(0.6)
    s = [(rr[0][1][i] - rr[1][1][i]) / (rr[0][0][i] - rr[1][0][i]) if rr[0][0][i] != rr[1][0][i] else None for i in (0, 1)]
    k = round(s[0] or s[1], 3)
    g = q(h, {"cmd": "globe_point", "lon": x.cb["lon"], "lat": x.cb["lat"]})
    x.ev["globe"] = [k, g.get("x"), g.get("y"), g.get("zoom")]
    if g.get("x") is None:
        raise Stop("globe_point: %s" % g)
    o = (rr[0][1][0] - k * rr[0][0][0], rr[0][1][1] - k * rr[0][0][1])
    visit_clicks(x, [(int(round(k * (g["x"] + dx) + o[0])), int(round(k * (g["y"] + dy) + o[1]))) for dx, dy in CLICKS[:7]])

# ----- boot, staging, the drop -----
def spawn_pair(x, tag):
    x.host = GameClient("host", None, make_user_dir(tag + "_host"))
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
def ironman_start(x):
    """W2-H53 boot G (test_w2_ironman_save_paths.py start / drive, copied): NewGameState IRONMAN toggle, co-op lobby, START; bases placed,
    every host ListSaveState answered NAME_I, a client 123 dismissed, BEGIN on the host's 60 / 62; both GeoscapeState quiet QUIET_S"""
    h, c = x.host, x.client
    h.ok({"cmd": "open_new_game", "mode": "coop"})
    h.wait_for("difficulty", lambda: has(h, "NewGameState"))
    if not wait(lambda: all(w.get("hidden") is False for w in q(h, {"cmd": "list_widgets"}).get("widgets", []) if w.get("interactive")), 10, 0.1)[0]:
        raise Stop("NewGameState widgets never settled")
    time.sleep(0.2)
    x.ev["ironmanClick"] = q(h, {"cmd": "click_widget", "match": "ironman"}).get("ok")
    time.sleep(0.3)
    h.ok({"cmd": "newgame_ok"})
    h.wait_for("host window", lambda: has(h, "HostMenu"))
    h.ok({"cmd": "host_tcp", "server": "TestSrv", "port": KEY, "player": "HostPlayer"})
    h.wait_for("host lobby", lambda: has(h, "LobbyMenu"))
    c.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    c.wait_for("client lobby", lambda: has(c, "LobbyMenu"), timeout=120)
    for gc in (h, c):
        gc.wait_for("join popup", lambda gc=gc: has(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})
    h.wait_for("start eligible", lambda: h.cmd({"cmd": "lobby_state"}).get("startEligible") or None)
    h.wait_for("START CAMPAIGN shown", lambda: h.cmd({"cmd": "lobby_state"}).get("buttonVisible") or None, timeout=10)
    session.start_campaign_via_button(h)
    t0, last, placed, begun, lists = time.time(), time.time(), {"host": False, "client": False}, False, []
    while time.time() - t0 < IRON_S:
        for who, gc in (("host", h), ("client", c)):
            t = top(gc) or ""
            if t == "BuildNewBaseState" and not placed[who]:
                lon, lat = HOST_POS if who == "host" else (LAND_LON, LAND_LAT)
                placed[who] = bool(q(gc, {"cmd": "place_first_base", "lon": lon, "lat": lat, "name": "HostBase" if who == "host" else "ClientBase"}).get("ok"))
                last = time.time()
            elif t == "ListSaveState" and who == "host" and len(lists) < 4:
                wait(lambda: all(w.get("hidden") is False for w in q(h, {"cmd": "list_widgets"}).get("widgets", []) if w.get("interactive")), 5, 0.1)
                lists.append(q(h, {"cmd": "list_save_confirm", "name": NAMES["I"]}).get("ok"))
                last = time.time()
            elif t == "CoopState" and who == "client" and dlg(c).get("code") == 123 and dlg(c).get("backVisible") is True:
                q(c, {"cmd": "coop_dialog_back"})
                last = time.time()
        if not begun and top(h) == "CoopState" and dlg(h).get("code") in (60, 62) and dlg(h).get("backVisible") is True:
            begun, last = bool(q(h, {"cmd": "coop_dialog_back"}).get("ok")), time.time()
        if begun and all(placed.values()) and top(h) == top(c) == "GeoscapeState" and time.time() - last >= QUIET_S:
            x.ev["start"] = {"lists": lists, "s": round(time.time() - t0, 2)}
            return
        time.sleep(0.1)
    raise Stop("ironman start not over in %.0f s: host %s client %s" % (IRON_S, stack(h), stack(c)))
def boot(x, tag, ironman=False):
    """fresh pair, a new SEPARATE campaign (host base at HOST_POS), slow clocks, settle; FUNDS staged; S0, CB; the picker (not row I)"""
    spawn_pair(x, tag)
    session.HOST_LON, session.HOST_LAT = HOST_POS
    if ironman:
        ironman_start(x)
    else:
        session.new_campaign(x.host, x.client, port=KEY)
    geo.slow_clock(x.host, x.client)
    settle(x)
    gh, gc_ = gs(x.host), gs(x.client)
    x.hb, x.cb = own_base(gh), own_base(gc_)
    x.FUNDS = next(f for f in FUNDS_C if f not in (gh.get("funds"), gc_.get("funds")))
    x.ev["funds"] = {"boot": [gh.get("funds"), gc_.get("funds")], "FUNDS": x.FUNDS, "set": q(x.host, {"cmd": "set_funds", "value": x.FUNDS}).get("ok")}
    x.HB, x.CB = x.hb.get("name"), x.cb.get("name")
    sh = q(x.host, {"cmd": "get_soldiers"})
    x.S0 = sorted(z.get("id") for b in sh.get("bases", []) if b.get("name") == x.HB and not b.get("coopIcon") for z in b.get("soldiers", []))
    x.ev.update(HB=x.HB, CB=x.CB, S0=x.S0)
    if not ironman:
        picker(x)
def read_i(x, r):
    """read I: host top BasescapeState, insideCoopBase, every live base coopBase, one named CB, funds != FUNDS -> (ok, detail)"""
    w = r.ev["readI"] = world(x.host)
    ok = (w["stack"][-1:] == ["BasescapeState"] and w["coop"].get("insideCoopBase") is True and w["bases"]
          and all(b[1] for b in w["bases"]) and [b[0] for b in w["bases"]] == [x.CB] and w["funds"] != x.FUNDS)
    return ok, "read I: stack %s, inside %s, bases %s, funds %s (want BasescapeState, true, [[%s, true, *]], != %s)" % (
        w["stack"], w["coop"].get("insideCoopBase"), w["bases"], w["funds"], x.CB, x.FUNDS)
def baseline(x):
    x.n_h, x.crB, x.filesB = len(log(x.host)), crashes(), files(x.host)
def drop_62(x, how="kill"):
    """client.kill() or the host's force_server_error; poll the host every 0.02 s; READ D at its first top CoopState 62"""
    h = x.host
    if how == "kill":
        x.client.kill()
        x.ev["lever"] = None
    else:
        x.ev["lever"] = pick(q(h, {"cmd": "force_server_error"}), ("ok", "error"))
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
        x.slot = "SWAP list_save_confirm (the injected row click opened no edit)"
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
    except Exception as e:  # noqa: BLE001 - a failed shutdown is a value (the -common cells)
        return short(e, 200)

# ----- rows -----
class Row:
    def __init__(self, rid):
        self.rid, self.cells, self.ev, self.done = rid, CELLS[rid], {}, {}
        self.x = SimpleNamespace(host=None, client=None, ev=self.ev, n_h=0, crB=crashes(), mm=False, mm_s=None, pk=None)

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

    def run(self, body, tag, ironman=False, visit_fn=None):
        x = self.x
        try:
            try:
                boot(x, tag, ironman)
                if visit_fn:
                    visit_fn(x)
            except Exception as e:  # noqa: BLE001 - a boot miss fails the row's first cell with ONE CAPTURE line
                self.capture(short(e))
                self.cell(self.cells[0], False, "boot / VISIT: %s" % short(e))
                raise Stop("boot")
            body(self, x)
            why = ""
        except Exception as e:  # noqa: BLE001 - a precondition miss ends the row
            why = self.ev["stop"] = short(e, 500)
            if not isinstance(e, Stop):
                self.capture(why)
        finally:
            self.ev["rc"] = [shut(x.client), shut(x.host)]
        for n in self.cells:
            if n not in self.done:
                self.cell(n, False, "not reached: %s" % why)
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        bad = [n for n in self.cells if not self.done.get(n)]
        print("ROW %s: %s" % (self.rid, "PASS" if not bad else "FAIL (%d failing: %s)" % (len(bad), bad)), flush=True)

def stack_cell(r, name, D, extra=True, more=""):
    d = D["dlg"] or {}
    r.cell(name, D["stack"] == ["GeoscapeState", "CoopState"] and d.get("code") == 62 and extra,
           "READ D host stack %s, top code %s at %.3f s%s (want [GeoscapeState, CoopState], 62)" % (D["stack"], d.get("code"), D["t62"], more))

def common(r, name, x, killed, extra=(), ok0=True):
    """the -common cells: every game the row did not kill alive until its shutdown; no new crash file since B"""
    rc = r.ev["rc"] = [shut(x.client) if not killed else "killed", shut(x.host)]
    nc = sorted(crashes() - x.crB)
    r.cell(name, ok0 and all(v in RC_OK for v in rc if v != "killed") and not nc,
           "%sexit codes (client, host) %s; new crash files %s (want %s, none)" % ("".join(e + "; " for e in extra), rc, nc, list(RC_OK)))

def body_t(r, x):
    ok, why = read_i(x, r)
    if not ok:
        r.cell("T-pre", False, why)
        raise Stop("read I")
    baseline(x)
    D = r.ev["readD"] = drop_62(x, "server")
    lv = x.ev["lever"]
    r.cell("T-pre", lv.get("ok") is True and D["needles"]["SERVER"] == 1, "%s; lever %s, SERVER %d (want ok, 1)" % (why, lv, D["needles"]["SERVER"]))
    stack_cell(r, "T-stack", D)
    own = [b for b in D["bases"] if not b[1] and not b[2] and b[0] == x.HB]
    view = [b for b in D["bases"] if b[1] and not b[2]]
    r.cell("T-world", own and not view and D["funds"] == x.FUNDS,
           "READ D bases %s, funds %s (want own [%s, false, false], no [*, true, false], %s)" % (D["bases"], D["funds"], x.HB, x.FUNDS))
    time.sleep(1.0)
    i1 = r.ev["inside1s"] = [coop(x.host).get("insideCoopBase"), stack(x.host)]
    r.cell("T-inside", D["coop"].get("insideCoopBase") is False and i1[0] is False,
           "insideCoopBase at READ D %s, 1 s later %s over %s (want false, false: the host's own geoscape, R-H73-2)" % (
               D["coop"].get("insideCoopBase"), i1[0], i1[1]))
    al = alive(x.host) and alive(x.client)
    common(r, "T-common", x, False, ["both alive %s" % al], al)

def body_s(r, x):
    r.ev["readI"] = world(x.host)
    sr = real_click(x.host, "SOLDIERS", W_UI)
    v, s = wait(lambda: top(x.host) == "SoldiersState", W_UI, 0.02)
    st = stack(x.host)
    r.cell("S-pre", bool(sr.get("ok")) and st == ["GeoscapeState", "BasescapeState", "SoldiersState"],
           "SOLDIERS click %s, host stack %s in %s s (want [GeoscapeState, BasescapeState, SoldiersState] within %.0f s)" % (sr.get("ok"), st, s, W_UI))
    if not v:
        raise Stop("S-pre")
    baseline(x)
    D = r.ev["readD"] = drop_62(x)
    stack_cell(r, "S-stack", D)
    ok, why = own_only(x, D)
    r.cell("S-world", ok, "READ D: " + why)
    common(r, "S-common", x, True, ["host alive %s" % alive(x.host)], alive(x.host))

def body_g(r, x):
    baseline(x)
    D = r.ev["readD"] = drop_62(x)
    sq = (D["dlg"] or {}).get("saveQuitVisible")
    stack_cell(r, "G-stack", D, sq is True, ", SAVE & QUIT shown %s" % sq)
    ok, why = own_only(x, D)
    r.cell("G-world", ok, "READ D: " + why)
    n = D["needles"]
    r.cell("G-log", n["UNWIND"] == 0 and n["OPEN"] == 0, "host log since B: UNWIND %d, OPEN %d (want 0, 0)" % (n["UNWIND"], n["OPEN"]))
    name = NAMES["G"]
    while os.path.exists(os.path.join(x.host.user_dir, "xcom1", name + ".sav")):
        name += "x"
    p = save_quit(x, name)
    r.ev.update(slot=x.slot, mainMenu=[x.mm, x.mm_s])
    fw = (read_save(p)["world"] or {}) if p else {}
    r.cell("G-file", fw.get("bases") == [[x.HB, x.S0]] and fw.get("funds") == x.FUNDS,
           "%s.sav world bases %s, funds %s (want [[%s, %s]], %s)" % (name, fw.get("bases"), fw.get("funds"), x.HB, x.S0, x.FUNDS))
    common(r, "G-common", x, True, ["MainMenuState %s in %s s" % (x.mm, x.mm_s)], x.mm)

def body_i(r, x):
    h = x.host
    sp = os.path.join(h.user_dir, "xcom1", NAMES["I"] + ".sav")
    hd = (read_save(sp)["header"] or {}) if os.path.exists(sp) else {}
    ok, why = read_i(x, r)
    r.cell("I-pre", ok and hd.get("name") == NAMES["I"] and hd.get("ironman") is True,
           "start file %s name %s ironman %s (want %s, true); %s" % (os.path.basename(sp), hd.get("name"), hd.get("ironman"), NAMES["I"], why))
    if not r.done["I-pre"]:
        raise Stop("I-pre")
    baseline(x)
    D = r.ev["readD"] = drop_62(x)
    if not wait(lambda: dlg(h).get("code") == 62 and dlg(h).get("saveQuitVisible"), W_62, 0.02)[0]:
        raise Stop("no SAVE & QUIT on the host's 62 (%s)" % D["stack"])
    n0, seen, lists, t0 = len(log(h)), [], [], time.time()
    r.ev["click"] = real_click(h, "SAVE & QUIT", 10).get("ok")
    while time.time() - t0 < W_SAVE and alive(h):
        st = stack(h)
        if not seen or seen[-1][1] != st:
            seen.append([round(time.time() - t0, 2), st])
        if st[-1:] == ["ListSaveState"] and not lists:
            wait(lambda: all(w.get("hidden") is False for w in q(h, {"cmd": "list_widgets"}).get("widgets", []) if w.get("interactive")), 5, 0.1)
            lists.append(q(h, {"cmd": "list_save_confirm", "name": NAMES["I2"]}).get("ok"))
        if "MainMenuState" in st:
            break
        time.sleep(0.02)
    mm = alive(h) and "MainMenuState" in stack(h)
    time.sleep(1.0)
    n = needles(h, n0)
    r.ev.update(seen=seen, lists=lists, mainMenu=[mm, round(time.time() - t0, 2)])
    r.cell("I-nolist", n["LISTPUSH"] == 0 and mm, "LISTPUSH since the SAVE & QUIT click %d, stacks %s, MainMenuState %s (want 0, true within %.0f s)"
           % (n["LISTPUSH"], seen[:3], mm, W_SAVE))
    fb, fa = x.filesB.get(NAMES["I"] + ".sav"), files(h).get(NAMES["I"] + ".sav")
    fw = (read_save(sp)["world"] or {}) if fa else {}
    i2 = os.path.exists(os.path.join(h.user_dir, "xcom1", NAMES["I2"] + ".sav"))
    r.cell("I-file", fa is not None and fb != fa and [x.HB, x.S0] in fw.get("bases", []) and not i2,
           "%s.sav moved %s, bases %s; %s.sav exists %s (want true, [%s, %s], false)" % (NAMES["I"], fb != fa, fw.get("bases"), NAMES["I2"], i2, x.HB, x.S0))
    common(r, "I-common", x, True, ["host alive %s" % alive(h)], alive(h))

def main():
    c0 = cpu()
    print("==== W2-H73 DDP (slot %s, key %s, exe %s) CPU %s ====" % (harness.HARNESS_SLOT, KEY, time.ctime(os.path.getmtime(harness.EXE)), c0), flush=True)
    Row("T").run(body_t, "w2h73_t", visit_fn=visit)
    Row("S").run(body_s, "w2h73_s", visit_fn=visit)
    Row("G").run(body_g, "w2h73_g")
    Row("I").run(body_i, "w2h73_i", ironman=True, visit_fn=globe_visit)
    fails = [n for n, ok in RESULTS if not ok]
    print("\n==== W2-H73 DDP: %d/%d cells PASS, wall %.1f s, CPU %s -> %s ====" % (len(RESULTS) - len(fails), len(RESULTS), time.time() - T0, c0, cpu()),
          flush=True)
    if fails:
        print("FAILING: %s" % fails, flush=True)
    return 0 if not fails else 2

if __name__ == "__main__":
    sys.exit(main())
