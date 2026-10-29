"""W2-H83 S-A RBC (tools/coop_test/test_removed_base_cache.py): a partner base removed before the host's next battle does not come back
on the host after that battle, whichever machine presses its debriefing OK first (lead L-H80-1, ruling R-LBH3-1, veto line VL-H83-1;
capture lh80-1-cap rows H1 / H1b, F22277-F22279). Spec docs rewrite/prompts/w2h83_removed_base_views.md (common: rulings, R3, QH83-2 (a),
QH83-7 (a)) + rewrite/prompts/w2h83_sa_delete_paths.md (f) RBC; TASK 0 values in rewrite/w2h83-task0/sa/CONSTANTS.md.
In a SEPARATE campaign the host keeps every partner marker in its cache (j_markers); the client's delete_base erases the live mirror but
never the cache entry, and the host's post-battle rebuild from that cache (updateAllCoopBases) puts the removed base back (today). The
green (EA1-EA4) drops the cache entry in the handler and logs one line.
TWO boots in turn, each shut down before the next: HA (dirs w2h83_ca_*, the HOST presses its debriefing OK first), then HB (dirs
w2h83_cb_*, the CLIENT first); key KEY. Per boot: spawn + connect; the seat levers of session (seat_guest: new_campaign, three host soldiers
and the client's guest seated in the host's Skyranger); geo_set_speed idx 0 both; drain_host_coop_notice; the window mapping per machine
(real INTERCEPT + CANCEL). The client builds a lift-only ClientBase2 at B2 (build_new_base + real GEOSCAPE); CB2_ID and CB_ID (the client's
first base) in mir(host); H-mark; the host's spawn_mission_site at SITE_POS; the client dismantles ClientBase2 (real BASES, key 2 if needed,
the BaseView lift cell, DismantleFacilityState OK) + real GEOSCAPE; 2 s; the host's craft_force (its seated Skyranger, STR_OUT, at SITE_POS
- FLY_OFFSET, to the site) and geo_set_speed idx 2; TOPS = the host's stack every 0.1 s until ConfirmLandingState (W_LAND), no host screen
in between; set_seed SEED; the host's real YES; drive_both_to_tactical; END = battle_action abort, the real AbortMissionState OK, the
client's real VoteMenu YES; both DebriefingState; the first machine's real OKs to its globe, OK_GAP_S, the other's. A0 = both
GeoscapeState calm 1 s; A1h = the host's CYCLE (INTERCEPT, CANCEL) + RT_SETTLE; CLICK (only if CB2_ID in mir(host) at A1h): a real globe
click on its marker, watch W_OPEN, then (if a view opened) the host's real GEOSCAPE.
  Rows HA / HB (X = HA, HB)
          X-pre (GUARD) seat ok; ClientBase2 in mir(host); the client's OK reached and ClientBase2 gone from its own; TOPS [GeoscapeState]
          only until ConfirmLandingState; both on the battlescape; both DebriefingState; both GeoscapeState at A0.  X-a0 (FIX) no CB2_ID in
          mir(host) at A0.  X-rt (FIX) none at A1h.  X-open (FIX) no CLICK, or no BasescapeState with insideCoopBase within W_OPEN.
          X-cache (FIX) the host's LINE(CB2_ID) since H-mark: exactly 1, containing "cache=1".  X-cb (GUARD) CB_ID in mir(host) at A0 and
          A1h (the partner's live base kept, HPM R-7a's purpose).
  END     CRASH (GUARD): no new crash file in the lane's crash folder since the file start (both boots); every process alive until its
          shutdown.
Red today: HA-a0, HA-rt, HA-open, HA-cache, HB-a0, HB-rt, HB-open, HB-cache FAIL (8 of 13); every other cell PASS. Green (EA1-EA4): all
13 PASS. mir(gc) = geo_state bases with coopIcon true; own(gc) = coopIcon and coopBase false; census rows [coopBaseId, name, coopIcon,
coopBase, lon, lat]. LINE(id) = engine-log lines holding "[coop] removed base: id=<id> cache=". Every press is a real click_widget
or inject_input except the logged levers build_new_base, geo_set_speed, the seat levers, drain_host_coop_notice, spawn_mission_site,
craft_force, set_seed, battle_action abort and drive_both_to_tactical's briefing / equip levers. One EVIDENCE line per row, one PASS / FAIL
line per cell, then the row verdict; a boot or precondition miss ends its row (ONE CAPTURE line, later cells "not reached") and the file
goes on to the next boot. ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_removed_base_cache.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402

KEY = "49557"                               # lobby key (CONSTANTS.md; 0 hits in src + tools at 0014f9bf1)
B2 = (LAND_LON + 0.03, LAND_LAT + 0.03)     # ClientBase2: on land
SITE_D = (0.25, 0.10)                       # SITE_POS = HB + SITE_D (CONSTANTS.md SWAP S1: HB + (0.35, 0.10) is not land)
FLY_OFFSET = 0.02                           # rad west of the site: ConfirmLandingState in 5.3-6.2 s
LIFT = (80, 80)                             # build_new_base's lift (2, 2), BaseView GRID 32: its centre
KEY_2, ZOOM_MIN, SYM_PLUS, SEED = 50, 3, 43, 7
OK_GAP_S, RT_SETTLE = 4.0, 3.0
W_OPEN, W_LAND, W_BATTLE, W_DEBRIEF, BOOT_S = 20.0, 60.0, 120.0, 120.0, 60.0
NEEDLE = "[coop] removed base: id=%s cache="
LOGN = ("[coop] removed base: ", "[coop] coopBase3 marker", "[coop-session]", "coop-ui] push", "coop-ui] pop")
ROWS = (("HA", ("HA-pre", "HA-a0", "HA-rt", "HA-open", "HA-cache", "HA-cb")),
        ("HB", ("HB-pre", "HB-a0", "HB-rt", "HB-open", "HB-cache", "HB-cb")), ("END", ("CRASH",)))
FIX = ("HA-a0", "HA-rt", "HA-open", "HA-cache", "HB-a0", "HB-rt", "HB-open", "HB-cache")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]


class Stop(Exception):  # a precondition missed: the row ends here
    pass


# ----- probes and real input (copied from the capture docs rewrite/lbh3-cap/cap.py, never imported) -----
def js(v): return json.dumps(v, sort_keys=True, default=str)
def now(): return round(time.time() - T0[0], 2)
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "**", "crash_*"), recursive=True))
def q(gc, obj):
    if not alive(gc):
        return {"error": "dead rc=%s" % (gc.proc.poll() if gc and gc.proc else None)}
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
def coop(gc):
    r = q(gc, {"cmd": "get_coop"})
    return {k: r.get(k) for k in ("insideCoopBase", "inBattle", "onConnect", "error") if k in r}
def census(gc):
    g = q(gc, {"cmd": "geo_state"})
    bl = [[b.get("coopBaseId"), b.get("name"), bool(b.get("coopIcon")), bool(b.get("coopBase")), round(b.get("lon") or 0, 4),
           round(b.get("lat") or 0, 4)] for b in g.get("bases", [])]
    return {"t": now(), "bases": bl, "stack": stk(gc), "selected": g.get("selectedBase"), "error": g.get("error")}
def mir(c): return [b for b in c["bases"] if b[2]]
def mir_ids(c): return [b[0] for b in mir(c)]
def own(c): return [b for b in c["bases"] if not b[2] and not b[3]]
def own_names(c): return [b[1] for b in own(c)]
def both(b): return {"host": census(b.host), "client": census(b.client)}
def cpu():
    c = harness.cpu_load()
    return {"t": time.strftime("%H:%M:%S"), "cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}
def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def lines_since(gc, n0): return [ln.split("\t")[0][-13:-1] + " " + ln.split("\t")[-1][:200] for ln in logl(gc)[n0:] if any(n in ln for n in LOGN)]
def hits(gc, needle, n0): return [[ln.split("\t")[0][-13:-1], ln.split("\t")[-1][:200]] for ln in logl(gc)[n0:] if needle in ln]
def wait(pred, timeout, interval=0.05):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 2)
        time.sleep(interval)
def real_click(gc, text, timeout=15.0):
    """a real click_widget on a visible, not hidden widget whose text is `text`"""
    t0 = time.time()
    while time.time() - t0 < timeout and alive(gc):
        ws = [w for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if w.get("visible") is True and w.get("hidden") is False and
              (w.get("text") or "").strip().lower() == text.lower()]
        if ws:
            c = q(gc, {"cmd": "click_widget", "match": ws[0].get("text").strip()})
            return {"text": text, "ok": bool(c.get("ok")), "s": round(time.time() - t0, 2), "tc": time.time()}
        time.sleep(0.05)
    return {"text": text, "ok": False, "miss": "not shown within %.0f s" % timeout, "stack": stk(gc)}
def must_click(gc, text, timeout=15.0):
    r = real_click(gc, text, timeout)
    if not r["ok"]:
        raise Stop("%s button %r not clicked: %s %s" % (gc.name, text, r.get("miss"), r.get("stack")))
    return r
def wait_top(gc, name, timeout=15.0):
    v, s = wait(lambda: top(gc) == name, timeout)
    if not v:
        raise Stop("%s top %s not %s within %.0f s" % (gc.name, stk(gc), name, timeout))
    return s
def cw(gc, match, settle=0.8):
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
    return {"base": [r.get("baseX"), r.get("baseY")], "win": [r.get("winX"), r.get("winY")], "ok": r.get("ok")}
def affine(r1, r2):
    out = [(r1["win"][i] - r2["win"][i]) / (r1["base"][i] - r2["base"][i]) if r1["base"][i] != r2["base"][i] else None for i in (0, 1)]
    sc = round(out[0] or out[1], 3)
    return (sc, r1["win"][0] - sc * r1["base"][0], sc, r1["win"][1] - sc * r1["base"][1])
def scale(gc):
    """INTERCEPT -> CANCEL (real clicks, setup): the window affine for injected clicks"""
    a = cw(gc, "INTERCEPT")
    wait(lambda: top(gc) == "InterceptState", 5)
    session.wait_widget_ready(gc, "CANCEL")
    b = cw(gc, "CANCEL")
    if not wait(lambda: top(gc) == "GeoscapeState", 5)[0] and top(gc) == "InterceptState":
        real_click(gc, "CANCEL", 5)
        wait(lambda: top(gc) == "GeoscapeState", 5)
    return affine(a, b)
def inject(gc, sc, bx, by):
    return q(gc, {"cmd": "inject_input", "kind": "click", "x": int(round(sc[0] * bx + sc[1])), "y": int(round(sc[2] * by + sc[3]))})
def key(gc, sym): return q(gc, {"cmd": "inject_input", "kind": "key", "key": sym})
def globe(gc, **kw): return q(gc, dict({"cmd": "globe_point"}, **kw))
def click_marker(gc, sc, lon, lat, name):
    """a real globe click on the marker at (lon, lat): zoom to ZOOM_MIN by key 43, 7 offsets; a MultipleTargetsState picks `name`"""
    globe(gc, centerLon=lon, centerLat=lat)
    zs = [globe(gc).get("zoom")]
    while (zs[-1] or 0) < ZOOM_MIN and len(zs) < 7:
        key(gc, SYM_PLUS)
        time.sleep(0.6)
        zs.append(globe(gc).get("zoom"))
    g, tries = globe(gc, lon=lon, lat=lat), []
    for dx, dy in ((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2)):
        inject(gc, sc, g.get("x") + dx, g.get("y") + dy)
        v, _ = wait(lambda: top(gc) != "GeoscapeState", 1.0)
        tries.append([g.get("x") + dx, g.get("y") + dy, top(gc)])
        if v:
            break
    out = {"zooms": zs, "px": [g.get("x"), g.get("y")], "tries": tries, "tc": time.time()}
    if top(gc) == "MultipleTargetsState":
        out["targets"] = [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
        t = next((t for t in out["targets"] if t.strip() == name), None)
        if t:
            out["pick"] = real_click(gc, t.strip(), 5)
    return out
def watch(b, secs, stop_when):
    """both machines' stack tops (a CoopState's code) every 0.05 s until stop_when() or secs: the trace of changes"""
    t0, trace, last, hit = time.time(), [], None, None
    while time.time() - t0 < secs:
        e = [[s[-3:], dlg(gc).get("code") if s[-1:] == ["CoopState"] else None] for gc in (b.host, b.client) for s in [stk(gc)]]
        if e != last:
            trace.append([round(time.time() - t0, 2)] + e)
            last = e
        if stop_when():
            hit = round(time.time() - t0, 2)
            break
        time.sleep(0.05)
    return {"trace": trace, "hit": hit}
def settle(gc, secs):
    """polls gc's mirrors every 0.25 s for secs: the trace of (mirror ids, top) changes"""
    t0, trace, last = time.time(), [], None
    while time.time() - t0 < secs:
        e = [mir_ids(census(gc)), top(gc)]
        if e != last:
            trace.append([round(time.time() - t0, 2)] + e)
            last = e
        time.sleep(0.25)
    return trace
def cycle(gc):
    """CYCLE: real INTERCEPT, CANCEL, back on GeoscapeState"""
    must_click(gc, "INTERCEPT", 10)
    wait_top(gc, "InterceptState", 5)
    session.wait_widget_ready(gc, "CANCEL")
    must_click(gc, "CANCEL", 10)
    wait_top(gc, "GeoscapeState", 10)
def build_base2(gc, name, pos):
    """the harness base-build lever (BuildNewBaseState -> ConfirmNewBaseState -> BaseNameState -> PlaceLiftState, real states), then a
    real GEOSCAPE from the new base's BasescapeState"""
    r = q(gc, {"cmd": "build_new_base", "lon": pos[0], "lat": pos[1], "name": name})
    if not r.get("ok"):
        raise Stop("build_new_base %s -> %s" % (name, r))
    time.sleep(1.0)
    if top(gc) == "BasescapeState":
        must_click(gc, "GEOSCAPE", 10)
    wait_top(gc, "GeoscapeState", 15)
    return r
def other_has(gc, name, timeout=30):
    v, s = wait(lambda: any(x[1] == name for x in census(gc)["bases"]), timeout, 0.25)
    if not v:
        raise Stop("%s has no base %s within %d s: %s" % (gc.name, name, timeout, census(gc)["bases"]))
    return s
def dismantle(gc, sc, name, during=None):
    """real BASES (key 2 if the shown base is not `name`), the BaseView lift cell, DismantleFacilityState, its real OK; during(t_ok)"""
    must_click(gc, "BASES", 10)
    wait_top(gc, "BasescapeState", 10)
    rec = {"selected": census(gc)["selected"], "key2": False}
    if rec["selected"] != name:
        key(gc, KEY_2)
        time.sleep(0.5)
        rec.update({"selected": census(gc)["selected"], "key2": True})
    if rec["selected"] != name:
        raise Stop("%s basescape shows %r not %r" % (gc.name, rec["selected"], name))
    v = next((z for z in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if (z.get("type") or "").endswith("::BaseView")), None)
    if not v:
        raise Stop("no BaseView on %s" % gc.name)
    rec["lift"] = inject(gc, sc, v["x"] + LIFT[0], v["y"] + LIFT[1])
    rec["dfsS"] = wait_top(gc, "DismantleFacilityState", 5)
    ok = must_click(gc, "OK", 5)
    rec["during"] = during(ok["tc"]) if during else None
    time.sleep(0.5)
    return rec
def capture(b):
    out = {}
    for gc in (b.host, b.client):
        out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None} if not alive(gc) else {
            "get_state": q(gc, {"cmd": "get_state"}), "get_coop": q(gc, {"cmd": "get_coop"}), "dialog": dlg(gc), "geo_state": census(gc),
            "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-40:]]}
    return out
# ----- the boots and the rows -----
class Boot:
    def __init__(self, tag):
        self.host = GameClient("host", None, make_user_dir("w2h83_%s_host" % tag))
        self.client = GameClient("client", None, make_user_dir("w2h83_%s_client" % tag))
        self.sc = {}
class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now(), "cpu": cpu()}
        self.n0 = [0, 0]
    def cell(self, cid, ok, label): self.res[cid] = (bool(ok), label)
    def need(self, ok, what):
        if not ok: raise Stop(what)  # noqa: E701
    def finish(self, stop=None):
        self.ev["tEnd"] = now()
        if self.b is not None:
            self.ev["hostLog"], self.ev["clientLog"] = lines_since(self.b.host, self.n0[0]), lines_since(self.b.client, self.n0[1])
        self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails, cells = [], dict(ROWS)[self.rid]
        for cid in cells:
            miss = "precondition miss: %s" % stop if cid == cells[0] and cid.endswith("-pre") else "not reached (%s)" % stop
            ok, label = self.res.get(cid, (False, miss))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "FIX" if cid in FIX else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop and self.b is not None:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails
def seat_guest(h, c, key):
    """the seat levers (CAP seat_guest): a SEPARATE campaign; three host soldiers and the client's guest seated in the host's Skyranger"""
    session.new_campaign(h, c, port=key)
    hb = session._campaign_own_roster_base(h)
    cid = session._campaign_skyranger(h)["id"]
    rh = sorted(s["id"] for s in hb["soldiers"])
    for sid in rh:
        h.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
    for sid in rh[:3]:
        if not h.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True}).get("seated"):
            raise Stop("host soldier %s not seated" % sid)
    cb = session._campaign_own_roster_base(c)
    spare = next(s for s in cb["soldiers"] if not s.get("craft"))["name"]
    c.ok({"cmd": "rename_soldier", "name": spare, "newName": "Guest Zzz"})
    if not c.ok({"cmd": "transfer_to_coop_base", "name": "Guest", "toBase": hb["name"]}).get("transferred"):
        raise Stop("guest transfer failed")
    c.ok({"cmd": "visit_coop_base", "base": hb["name"]})
    c.wait_for("client inside host base", lambda: c.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None, timeout=60)
    rep = c.wait_for("guest visible at host base", lambda: (lambda r: r if any("Guest" in s["name"] for s in r["soldiers"]) else None)(
        c.ok({"cmd": "base_report", "coop": True})), timeout=40)
    gid = next(s for s in rep["soldiers"] if "Guest" in s["name"])["id"]
    peer = next(k for k in rep["crafts"] if "SKYRANGER" in k["type"])["id"]
    sa = c.ok({"cmd": "craft_assign", "soldier_id": gid, "craft_id": peer, "coop": True, "on": True})
    c.ok({"cmd": "open_soldiers", "base": hb["name"]})
    c.wait_for("client soldiers screen", lambda: session.has_state(c, "SoldiersState") or None, timeout=30)
    c.ok({"cmd": "soldiers_ok"})
    c.ok({"cmd": "leave_base"})
    session.wait_back_on_geoscape(c, "client back on geoscape")
    if not sa.get("seated"):
        raise Stop("the guest not seated: %s" % sa)
    return {"hostBase": hb["name"], "craft": cid, "squad": rh[:3], "guest": gid}
def ok_popups(gc, timeout):
    """real clicks down to the globe: DebriefingState OK, a CoopState's visible back button; until GeoscapeState calm 2 s"""
    clicks, end, calm = [], time.time() + timeout, None
    while time.time() < end and alive(gc):
        t, d = top(gc), dlg(gc)
        if t == "DebriefingState" or t == "CoopState" and d.get("backVisible") and d.get("backText"):
            m = "OK" if t == "DebriefingState" else d.get("backText")
            clicks.append([t, m, now(), real_click(gc, m, 10)["ok"]])
            calm = None
            time.sleep(1.0)
            continue
        if t == "GeoscapeState":
            if calm is None:
                calm = time.time()
                clicks.append([t, None, now(), True])
            elif time.time() - calm >= 2.0:
                break
        else:
            calm = None
        time.sleep(0.2)
    return clicks
def row_h(x, b, r, first):
    """X: the boot, the seat, ClientBase2 built and dismantled by the client, the host's battle (no host screen before
    ConfirmLandingState), END with the `first` machine's OK first, A0 / A1h / CLICK on the host"""
    h, c, ev, rid = b.host, b.client, r.ev, r.rid
    for gc in (h, c):
        gc.spawn()
    for gc in (h, c):
        gc.connect(timeout=BOOT_S)
    ev["seat"] = seat_guest(h, c, KEY)
    for gc in (h, c):
        q(gc, {"cmd": "geo_set_speed", "idx": 0})
    session.drain_host_coop_notice(h)
    time.sleep(1.5)
    b.sc = {"host": scale(h), "client": scale(c)}
    r.n0 = [len(logl(h)), len(logl(c))]
    r.need(top(h) == "GeoscapeState" and top(c) == "GeoscapeState", "after the seat: %s / %s (want both GeoscapeState)" % (stk(h), stk(c)))
    ev["build"] = build_base2(c, "ClientBase2", B2)
    ev["otherHasS"] = other_has(h, "ClientBase2")
    time.sleep(2.0)
    p = both(b)
    cown = [o for o in own(p["client"]) if o[1] != "ClientBase2"]
    cb2 = [m for m in mir(p["host"]) if m[1] == "ClientBase2"]
    cb = [m for m in mir(p["host"]) if cown and m[0] == cown[0][0]]
    ev["H1"] = {"hostMir": mir(p["host"]), "clientOwn": own(p["client"])}
    r.need(len(cb2) == 1 and len(cb) == 1, "H1: mir(host) %s, the client's own %s (want ClientBase2 and the client's first base)" % (
        mir(p["host"]), own(p["client"])))
    ids = ev["ids"] = {"CB2_ID": cb2[0][0], "CB_ID": cb[0][0]}
    b0 = session._campaign_base0(h)
    site_pos = (b0["lon"] + SITE_D[0], b0["lat"] + SITE_D[1])
    mark = [len(logl(h)), len(logl(c))]  # H-mark
    tops = [[now(), "H-mark", stk(h)]]
    site = h.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION", "lon": site_pos[0],
                 "lat": site_pos[1], "race": "STR_SECTOID", "hours": 240})
    h.wait_for("site on host", lambda: any(s["id"] == site["site_id"] for s in h.ok({"cmd": "geo_state"})["missionSites"]) or None, timeout=30)
    ev["site"] = {"reply": site, "pos": site_pos, "land": globe(h, lon=site_pos[0], lat=site_pos[1]).get("land")}
    tops.append([now(), "site", stk(h)])
    ev["dismantle"] = dismantle(c, b.sc["client"], "ClientBase2")
    tops.append([now(), "client OK", stk(h)])
    must_click(c, "GEOSCAPE", 10)
    wait_top(c, "GeoscapeState", 15)
    time.sleep(2.0)
    p = both(b)
    tops.append([now(), "+2 s", stk(h)])
    ev["H3"] = {"hostMir": mir(p["host"]), "clientOwn": own(p["client"])}
    r.need("ClientBase2" not in own_names(p["client"]), "H3: ClientBase2 still in the client's own %s" % own(p["client"]))
    ev["force"] = h.ok({"cmd": "craft_force", "craft_id": ev["seat"]["craft"], "status": "STR_OUT", "lon": site_pos[0] - FLY_OFFSET,
                        "lat": site_pos[1], "dest": "site:%s" % site["site_id"], "fuel": 999999, "lowFuel": False})
    q(h, {"cmd": "geo_set_speed", "idx": 2})
    tf, last = time.time(), None
    while time.time() - tf < W_LAND:
        s = stk(h)
        if s != last:
            tops.append([now(), round(time.time() - tf, 2), s])
            last = s
        if "ConfirmLandingState" in s:
            break
        time.sleep(0.1)
    ev["tops"], ev["hostUi"] = tops, [ln for ln in lines_since(h, mark[0]) if "coop-ui] p" in ln]
    r.need("ConfirmLandingState" in stk(h), "no ConfirmLandingState within W_LAND: %s" % stk(h))
    r.need(all(t[-1] == ["GeoscapeState"] for t in tops[:-1]) and tops[-1][-1] == ["GeoscapeState", "ConfirmLandingState"],
           "TOPS: a host screen before ConfirmLandingState: %s" % tops)
    q(h, {"cmd": "set_seed", "seed": SEED})
    must_click(h, "YES", 10)
    v, s = wait(lambda: q(h, {"cmd": "battle_state"}).get("inBattle") or None, W_BATTLE, 0.25)
    r.need(v, "the host not in battle within W_BATTLE of its YES")
    wait(lambda: session.has_state(h, "BriefingState") or None, 60, 0.25)
    r.need(session.drive_both_to_tactical(h, c), "drive_both_to_tactical timed out: %s / %s" % (stk(h)[-3:], stk(c)[-3:]))
    ev["battle"] = {"inBattleS": s, "tBattlescape": now()}
    e = ev["end"] = {"abort": q(h, {"cmd": "battle_action", "action": "abort"})}
    must_click(h, "OK", 30)
    t1, vs = time.time(), q(c, {"cmd": "vote_state"})
    while time.time() - t1 < 20 and not (vs.get("active") and vs.get("menuOpen")):
        time.sleep(0.1)
        vs = q(c, {"cmd": "vote_state"})
    e["voteState"] = {k: vs.get(k) for k in ("active", "action", "menuOpen", "id")}
    if vs.get("menuOpen") and real_click(c, "YES", 20)["ok"]:
        e["vote"] = "click"
    else:
        e["vote"] = ["vote_cast", q(c, {"cmd": "vote_cast", "id": vs.get("id"), "yes": True})]
    v, e["debriefS"] = wait(lambda: top(h) == "DebriefingState" and top(c) == "DebriefingState", W_DEBRIEF, 0.1)
    r.need(v, "not both DebriefingState within W_DEBRIEF: %s / %s" % (stk(h), stk(c)))
    fg, og = (h, c) if first == "host" else (c, h)
    e["firstOks"] = ok_popups(fg, 60)
    e["otherAtFirst"] = stk(og)
    r.need(top(og) == "DebriefingState", "the second machine not on DebriefingState after the first's OK: %s" % stk(og))
    tg = time.time()
    while time.time() - tg < OK_GAP_S:
        time.sleep(0.25)
    e["otherOks"] = ok_popups(og, 90)
    v, _ = wait(lambda: top(h) == "GeoscapeState" and top(c) == "GeoscapeState", 30, 0.2)
    if v:
        time.sleep(1.0)
    a0 = both(b)
    ev["A0"] = {"host": a0["host"]["bases"], "client": a0["client"]["bases"], "stacks": [a0["host"]["stack"], a0["client"]["stack"]]}
    r.need(a0["host"]["stack"] == ["GeoscapeState"] and a0["client"]["stack"] == ["GeoscapeState"], "A0: not both GeoscapeState calm 1 s")
    r.cell(rid + "-pre", True, "seat %s; ClientBase2 %s mirrored and dismantled; TOPS %s; both battlescape, DebriefingState, GeoscapeState" % (
        ev["seat"], ids["CB2_ID"], [t[-1][-1] for t in tops]))
    cycle(h)
    ev["rtSettle"] = settle(h, RT_SETTLE)
    a1 = census(h)
    ev["A1h"] = a1["bases"]
    ev["click"] = None
    if ids["CB2_ID"] in mir_ids(a1):
        gh = [m for m in mir(a1) if m[0] == ids["CB2_ID"]][0]
        mk = click_marker(h, b.sc["host"], gh[4], gh[5], "ClientBase2")
        w = watch(b, W_OPEN, lambda: top(h) == "BasescapeState" and coop(h).get("insideCoopBase") is True)
        opened = top(h) == "BasescapeState" and coop(h).get("insideCoopBase") is True
        hv = census(h)
        ev["click"] = {"marker": mk, "watch": w, "opened": opened, "selected": hv["selected"], "viewBases": hv["bases"]}
        if opened:
            must_click(h, "GEOSCAPE", 10)
            ev["click"]["back"] = wait(lambda: top(h) == "GeoscapeState", 30, 0.25)
    ln = ev["lines"] = {"host": hits(h, NEEDLE % ids["CB2_ID"], mark[0]), "client": hits(c, NEEDLE % ids["CB2_ID"], mark[1])}
    m0, m1 = mir_ids(a0["host"]), mir_ids(a1)
    r.cell(rid + "-a0", ids["CB2_ID"] not in m0, "mir(host) at A0 %s; CB2_ID %s (want absent)" % (m0, ids["CB2_ID"]))
    r.cell(rid + "-rt", ids["CB2_ID"] not in m1, "mir(host) at A1h %s; CB2_ID %s (want absent)" % (m1, ids["CB2_ID"]))
    ck = ev["click"]
    r.cell(rid + "-open", ck is None or not ck["opened"], "no CLICK (no ghost at A1h)" if ck is None else
           "CLICK opened %s: selectedBase %r, view %s" % (ck["opened"], ck["selected"], ck["viewBases"]))
    r.cell(rid + "-cache", len(ln["host"]) == 1 and "cache=1" in ln["host"][0][1],
           "the host's LINE(%s) since H-mark: %d %s (want exactly 1 with cache=1)" % (ids["CB2_ID"], len(ln["host"]), ln["host"]))
    r.cell(rid + "-cb", ids["CB_ID"] in m0 and ids["CB_ID"] in m1, "mir(host) at A0 %s, at A1h %s; CB_ID %s (want in both)" % (m0, m1, ids["CB_ID"]))
class X:  # the file's run state: failing cells, every process's alive-until-shutdown record
    def __init__(self): self.fails, self.alive = [], []
def main():
    x, crash0 = X(), crashes()
    T0[0] = time.time()
    for tag, rid, first in (("ca", "HA", "host"), ("cb", "HB", "client")):
        b = None
        try:
            b = Boot(tag)
            r = Row(x, b, rid)
            try:
                row_h(x, b, r, first)
                r.finish()
            except Stop as e:
                r.finish(str(e))
            except Exception as e:  # noqa: BLE001 - a boot miss or an unexpected exception ends the row like a precondition miss
                r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
        finally:
            for gc in ((b.client, b.host) if b else ()):
                x.alive.append(["%s %s" % (rid, gc.name), alive(gc)])
                try:
                    if gc.proc is not None and alive(gc):
                        gc.shutdown(expected_returncodes=OKRC)
                except Exception as e:  # noqa: BLE001
                    print("FAIL shutdown %s %s: %s" % (rid, gc.name, str(e)[:300]), flush=True)
                    x.alive[-1][1] = False
    r, new = Row(x, None, "END"), sorted(crashes() - crash0)
    r.ev.update({"newCrash": [os.path.basename(p) for p in new], "aliveUntilShutdown": x.alive, "crashDir": harness.CRASH_DIR})
    r.cell("CRASH", not new and x.alive and all(a[1] for a in x.alive),
           "new crash files %d %s; alive until shutdown %s" % (len(new), r.ev["newCrash"][:3], x.alive))
    r.finish()
    cl = [cid for _r, cs in ROWS for cid in cs]
    print("SUMMARY W2-H83 S-A RBC: %d/%d cells pass; failing %s; wall %.1f s" % (len(cl) - len(set(x.fails)), len(cl),
                                                                              sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
