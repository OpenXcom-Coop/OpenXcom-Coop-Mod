"""W2-H83 S-A RBG (tools/coop_test/test_removed_base_ghost.py): a partner base removed while the receiver has its OWN base view open
leaves no ghost marker (lead L-BH3 row G, ruling R-LBH3-1, veto line VL-H83-1; capture lbh3-cap F22265-F22267).
Spec docs rewrite/prompts/w2h83_removed_base_views.md (common: rulings, R3, QH83-1 (a)) + rewrite/prompts/w2h83_sa_delete_paths.md (f) RBG;
TASK 0 values in rewrite/w2h83-task0/sa/CONSTANTS.md. In a SEPARATE campaign the client's own base view moves every partner mirror into the
process-wide stash; the host then dismantles the lift of its lift-only HostBase2; the client's delete_base handler searches only the live list,
so leaving the view puts the HostBase2 mirror back (today). The green (EA1-EA4) deletes the stashed mirror in the handler and logs one line.
ONE boot (key KEY, dirs w2h83_g_*, campaign_mode "coop"): spawn + connect; session.new_campaign; geo_set_speed idx 0 both; the window mapping
per machine (real INTERCEPT + CANCEL). HB_ID = the host's first base id (mir(client) at boot).
  Row G   host build_new_base HostBase2 at B2 (+ real GEOSCAPE); G_ID in mir(client); G-mark; client real BASES (its own base view; key 1 if
          another base shows); the host dismantles HostBase2 (real BASES, key 2 if needed, the BaseView lift cell, DismantleFacilityState OK)
          + real GEOSCAPE; DEL_SETTLE; client real GEOSCAPE; RT_SETTLE; read A; client CYCLE (INTERCEPT, CANCEL) + RT_SETTLE; read B; CLICK
          (only if G_ID in mir(client) at B): a real globe click on its marker, watch W_OPEN, then (if a view opened) real GEOSCAPE.
          G-pre (GUARD) HostBase2 in the host's own and in mir(client); the client's view shows its own base and no G_ID; the host's OK
          reached, HostBase2 gone from its own; the client back on GeoscapeState.  G-a (FIX) no G_ID in mir(client) at A.  G-rt (FIX) none
          at B.  G-open (FIX) no CLICK, or no BasescapeState with insideCoopBase within W_OPEN.  G-stash (FIX) the client's LINE(G_ID) since
          G-mark: exactly 1, ending "stash=1".  G-mir (GUARD) HB_ID in mir(client) at B (the client keeps the host's first-base marker;
          CONSTANTS.md F22520).
  Row C   (G-ctl) host build_new_base HostBase3 at B3; C_ID; the client stays on its globe; C-mark; the host dismantles HostBase3; GONE = poll
          mir(client) every 0.05 s for GONE_S from the host's OK click; host GEOSCAPE; client CYCLE; read.
          C-pre (GUARD) HostBase3 in mir(client); the client's top GeoscapeState throughout; the host's OK reached.  C-gone (GUARD) no C_ID
          in mir(client) within GONE_S of the OK click, and none after the client's CYCLE.
  END     CRASH (GUARD): no new crash file in the lane's crash folder since the file start; both processes alive until their shutdown.
Red today: G-a, G-rt, G-open, G-stash FAIL (4 of 9); every other cell PASS. Green (EA1-EA4): all 9 PASS.
mir(gc) = geo_state bases with coopIcon true; own(gc) = coopIcon and coopBase false; census rows [coopBaseId, name, coopIcon, coopBase,
lon, lat]. LINE(id) = engine-log lines holding "[coop] removed base: id=<id> cache=". Every press is a real click_widget or
inject_input except the logged levers build_new_base and geo_set_speed. One EVIDENCE line per row, one PASS / FAIL line per cell, then the
row verdict; a precondition miss ends its row (CAPTURE line, later cells "not reached") and the file goes on; a boot miss fails G-pre with
ONE CAPTURE line. ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_removed_base_ghost.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402

KEY = "49556"                               # lobby key (CONSTANTS.md; 0 hits in src + tools at 0014f9bf1)
B2 = (LAND_LON + 0.03, LAND_LAT + 0.03)     # HostBase2: on land
B3 = (LAND_LON + 0.06, LAND_LAT + 0.03)     # HostBase3: on land
LIFT = (80, 80)                             # build_new_base's lift (2, 2), BaseView GRID 32: its centre
KEY_1, KEY_2, ZOOM_MIN, SYM_PLUS = 49, 50, 3, 43
DEL_SETTLE, RT_SETTLE, GONE_S = 3.0, 3.0, 2.0
W_OPEN, BOOT_S = 20.0, 60.0
NEEDLE = "[coop] removed base: id=%s cache="
LOGN = ("[coop] removed base: ", "[coop] coopBase3 marker", "[coop-session]", "coop-ui] push", "coop-ui] pop")
ROWS = (("G", ("G-pre", "G-a", "G-rt", "G-open", "G-stash", "G-mir")), ("C", ("C-pre", "C-gone")), ("END", ("CRASH",)))
FIX = ("G-a", "G-rt", "G-open", "G-stash")
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
# ----- the boot and the rows -----
class Boot:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("w2h83_g_host"))
        self.client = GameClient("client", None, make_user_dir("w2h83_g_client"))
        self.sc = {}
class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now(), "cpu": cpu()}
        self.n0 = [len(logl(b.host)), len(logl(b.client))] if b is not None and alive(b.host) and alive(b.client) else [0, 0]
    def cell(self, cid, ok, label): self.res[cid] = (bool(ok), label)
    def need(self, ok, what):
        if not ok: raise Stop(what)  # noqa: E701
    def finish(self, stop=None, capture_it=True):
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
        if stop and capture_it and self.b is not None:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails
def bring_up(b, st):
    for gc in (b.host, b.client):
        gc.spawn()
    for gc in (b.host, b.client):
        gc.connect(timeout=BOOT_S)
    session.new_campaign(b.host, b.client, port=KEY, campaign_mode="coop")
    for gc in (b.host, b.client):
        wait_top(gc, "GeoscapeState", 60)
        q(gc, {"cmd": "geo_set_speed", "idx": 0})
    time.sleep(2.0)
    b.sc = {"host": scale(b.host), "client": scale(b.client)}
    p = both(b)
    st["boot"] = {"sc": b.sc, "host": p["host"]["bases"], "client": p["client"]["bases"], "stacks": [p["host"]["stack"], p["client"]["stack"]]}
    if not (p["host"]["stack"] == ["GeoscapeState"] and p["client"]["stack"] == ["GeoscapeState"] and len(own(p["host"])) == 1 and
            len(own(p["client"])) == 1 and len(mir(p["client"])) == 1):
        raise Stop("boot: stacks %s / %s, host own %s, client own %s, client mirrors %s" % (
            p["host"]["stack"], p["client"]["stack"], own(p["host"]), own(p["client"]), mir(p["client"])))
    st["HB_ID"], st["CB"] = mir_ids(p["client"])[0], own(p["client"])[0][:2]
def row_g(b, r, st):
    h, c, ev = b.host, b.client, r.ev
    ev["ids"] = {"HB_ID": st["HB_ID"], "CB": st["CB"]}
    ev["build"] = build_base2(h, "HostBase2", B2)
    ev["otherHasS"] = other_has(c, "HostBase2")
    time.sleep(1.0)
    p = both(b)
    g2 = [x for x in mir(p["client"]) if x[1] == "HostBase2"]
    ev["G0"] = {"hostOwn": own(p["host"]), "clientMir": mir(p["client"])}
    r.need(len(g2) == 1 and "HostBase2" in own_names(p["host"]), "G0: HostBase2 in the host's own %s and once in mir(client) %s" % (
        own(p["host"]), mir(p["client"])))
    st["G_ID"] = ev["ids"]["G_ID"] = g2[0][0]
    mark = [len(logl(h)), len(logl(c))]  # G-mark
    must_click(c, "BASES", 10)
    wait_top(c, "BasescapeState", 10)
    ev["key1"] = census(c)["selected"] != st["CB"][1]
    if ev["key1"]:
        key(c, KEY_1)
        time.sleep(0.5)
    time.sleep(1.0)
    v = census(c)
    ev["view"] = {"stack": v["stack"], "selected": v["selected"], "bases": v["bases"]}
    r.need(v["stack"][-1:] == ["BasescapeState"] and v["selected"] == st["CB"][1] and st["G_ID"] not in [x[0] for x in v["bases"]],
           "G view: the client's view %s shows %r with bases %s (want its own %r, no G_ID)" % (v["stack"], v["selected"], v["bases"], st["CB"][1]))
    ev["dismantle"] = dismantle(h, b.sc["host"], "HostBase2")
    must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState", 15)
    hp = census(h)
    ev["hostAfter"] = own(hp)
    r.need("HostBase2" not in own_names(hp), "the host's own still holds HostBase2 after its OK: %s" % own(hp))
    ev["delSettle"] = settle(c, DEL_SETTLE)
    must_click(c, "GEOSCAPE", 10)
    wait_top(c, "GeoscapeState", 10)
    ev["rtSettleA"] = settle(c, RT_SETTLE)
    a = census(c)
    ev["A"] = a["bases"]
    r.need(a["stack"] == ["GeoscapeState"], "the client not back on GeoscapeState: %s" % a["stack"])
    r.cell("G-pre", True, "HostBase2 %s built and mirrored; the client's view showed %r only; the host's OK reached (own after %s); client %s" % (
        st["G_ID"], v["selected"], [x[1] for x in ev["hostAfter"]], a["stack"]))
    cycle(c)
    ev["rtSettleB"] = settle(c, RT_SETTLE)
    bb = census(c)
    ev["B"] = bb["bases"]
    ev["click"] = None
    if st["G_ID"] in mir_ids(bb):
        gh = [x for x in mir(bb) if x[0] == st["G_ID"]][0]
        mk = click_marker(c, b.sc["client"], gh[4], gh[5], "HostBase2")
        w = watch(b, W_OPEN, lambda: top(c) == "BasescapeState" and coop(c).get("insideCoopBase") is True)
        opened = top(c) == "BasescapeState" and coop(c).get("insideCoopBase") is True
        g5 = census(c)
        ev["click"] = {"marker": mk, "watch": w, "opened": opened, "selected": g5["selected"], "viewBases": g5["bases"]}
        if opened:
            must_click(c, "GEOSCAPE", 10)
            ev["click"]["back"] = wait(lambda: top(c) == "GeoscapeState", 30, 0.25)
            time.sleep(2.0)
            ev["click"]["after"] = census(c)["bases"]
    ln = ev["lines"] = {"client": hits(c, NEEDLE % st["G_ID"], mark[1]), "host": hits(h, NEEDLE % st["G_ID"], mark[0])}
    ma, mb = mir_ids(a), mir_ids(bb)
    r.cell("G-a", st["G_ID"] not in ma, "mir(client) at A %s; G_ID %s (want absent)" % (ma, st["G_ID"]))
    r.cell("G-rt", st["G_ID"] not in mb, "mir(client) at B %s; G_ID %s (want absent)" % (mb, st["G_ID"]))
    ck = ev["click"]
    r.cell("G-open", ck is None or not ck["opened"], "no CLICK (no ghost at B)" if ck is None else "CLICK opened %s: selectedBase %r, view %s" % (
        ck["opened"], ck["selected"], ck["viewBases"]))
    r.cell("G-stash", len(ln["client"]) == 1 and ln["client"][0][1].endswith("stash=1"),
           "the client's LINE(%s) since G-mark: %d %s (want exactly 1 ending stash=1)" % (st["G_ID"], len(ln["client"]), ln["client"]))
    r.cell("G-mir", st["HB_ID"] in mb, "mir(client) at B %s; HB_ID %s (want present)" % (mb, st["HB_ID"]))
def row_c(b, r, st):
    h, c, ev = b.host, b.client, r.ev
    ev["build"] = build_base2(h, "HostBase3", B3)
    ev["otherHasS"] = other_has(c, "HostBase3")
    time.sleep(1.0)
    p = both(b)
    g3 = [x for x in mir(p["client"]) if x[1] == "HostBase3"]
    ev["C0"] = {"hostOwn": own(p["host"]), "clientMir": mir(p["client"]), "clientStack": p["client"]["stack"]}
    r.need(len(g3) == 1 and p["client"]["stack"] == ["GeoscapeState"], "C0: mir(client) %s, client %s (want HostBase3 once, GeoscapeState)" % (
        mir(p["client"]), p["client"]["stack"]))
    st["C_ID"] = ev["C_ID"] = g3[0][0]
    tops = [p["client"]["stack"][-1]]

    def gone_poll(tc):
        tr, at = [], None
        while time.time() - tc < GONE_S:
            g, tt = census(c), round(time.time() - tc, 3)
            e = [st["C_ID"] in mir_ids(g), g["stack"][-1]]
            tops.append(e[1])
            if not tr or tr[-1][1:] != e:
                tr.append([tt] + e)
            if not e[0] and at is None:
                at = tt
            time.sleep(0.05)
        return {"trace": tr, "goneAt": at}
    d = ev["dismantle"] = dismantle(h, b.sc["host"], "HostBase3", during=gone_poll)
    must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState", 15)
    tops.append(top(c))
    cycle(c)
    ev["rtSettle"] = settle(c, RT_SETTLE)
    a = census(c)
    ev["after"] = a["bases"]
    gone = d["during"]
    r.cell("C-pre", all(t == "GeoscapeState" for t in tops), "HostBase3 %s in mir(client); the client's tops %s; the host's OK reached" % (
        st["C_ID"], sorted(set(tops))))
    r.cell("C-gone", gone["goneAt"] is not None and not gone["trace"][-1][1] and st["C_ID"] not in mir_ids(a),
           "GONE trace %s (gone at +%s s of the OK); mir(client) after the CYCLE %s" % (gone["trace"], gone["goneAt"], mir_ids(a)))
class X:  # the file's run state: failing cells, every process's alive-until-shutdown record
    def __init__(self): self.fails, self.alive = [], []
def run_row(x, b, rid, fn, st):
    r = Row(x, b, rid)
    try:
        fn(b, r, st)
        r.finish()
    except Stop as e:
        r.finish(str(e))
    except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
        r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
def main():
    x, crash0, b, st = X(), crashes(), None, {}
    T0[0] = time.time()
    try:
        b = Boot()
        try:
            bring_up(b, st)
        except Exception as e:  # noqa: BLE001 - a boot miss fails G-pre with ONE CAPTURE line
            r = Row(x, b, "G")
            r.ev["boot"] = st.get("boot")
            r.finish("boot miss: %s: %s" % (type(e).__name__, str(e)[:300]))
            Row(x, None, "C").finish("boot miss", capture_it=False)
        else:
            run_row(x, b, "G", row_g, st)
            run_row(x, b, "C", row_c, st)
    finally:
        for gc in ((b.client, b.host) if b else ()):
            x.alive.append([gc.name, alive(gc)])
            try:
                if gc.proc is not None and alive(gc):
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
    print("SUMMARY W2-H83 S-A RBG: %d/%d cells pass; failing %s; wall %.1f s" % (len(cl) - len(set(x.fails)), len(cl),
                                                                              sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
