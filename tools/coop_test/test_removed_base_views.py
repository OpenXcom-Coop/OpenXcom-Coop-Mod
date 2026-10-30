"""A base its owner removes is never read by a view of it on the other machine.
Without the fix a SEPARATE client VISITING the host's base keeps its view on the freed base after the host removes it,
and in SHARED the client's BUILD FACILITIES, alien containment and NEW RESEARCH windows stay open on the removed base
and refresh from it. The fix sends the visitor home first (one LEAVE line) and closes the three windows like the eleven
other bound base screens.
TWO boots, each shut down before the next (key KEY). The window mapping per machine: real INTERCEPT + CANCEL.
SEPARATE boot (dirs removed_base_views_separate_*, campaign_mode "coop"): spawn + connect; session.new_campaign;
  geo_set_speed idx 0 both; HB = the host's first base (mir(client) at boot); host build_new_base HostBase2 at
  BASE2_POS and HostBase3 at BASE3_POS (+ real GEOSCAPE each); both in mir(client).
  Row live_visit_stays
          client real globe click on HB's marker (MultipleTargetsState: the HB row) -> the visit (BasescapeState,
          insideCoopBase true, selectedBase HB); the host dismantles HostBase3 (real BASES, the key of its index if not
          shown, the BaseView lift cell, DismantleFacilityState OK) + real GEOSCAPE; DEL_SETTLE; read the client;
          client real GEOSCAPE (the view of HB, a live base) -> its own GeoscapeState within W_BACK; RT_SETTLE; read.
          live_visit_stays-pre (GUARD) HostBase2 / HostBase3 in mir(client); the visit open on HB; the host's OK
          reached.  live_visit_stays-stay (GUARD) after DEL_SETTLE the client's top BasescapeState, insideCoopBase
          true, selectedBase HB, its live bases lack HostBase3.  live_visit_stays-gone (GUARD) after its GEOSCAPE:
          own(client) non-empty and no HostBase3 id in mir(client) after RT_SETTLE.
  Row visit_sent_home
          (LAST) client real globe click on HostBase2 -> the visit (selectedBase HostBase2); MARK; the host
          dismantles HostBase2; poll the client every 0.05 s for W_LEAVE from the host's OK click; host real
          GEOSCAPE; RT_SETTLE; read; WATCH both stacks until W_END after the OK. No client press after the dismantle.
          visit_sent_home-pre (GUARD) the visit open on HostBase2; the host's OK reached.  visit_sent_home-leave
          (FIX) within W_LEAVE of the OK the client's top GeoscapeState and own(client) non-empty.
          visit_sent_home-log (FIX) the client's LEAVE lines since MARK: exactly 1.  visit_sent_home-mir (FIX) after
          RT_SETTLE mir(client) ids == {HB_ID}.  visit_sent_home-end (GUARD) no CutsceneState / StatisticsState /
          SlideshowState on either stack up to W_END.  visit_sent_home-host (GUARD) HostBase2 gone from own(host);
          the host's top GeoscapeState.
SHARED boot (dirs removed_base_views_shared_*, campaign_mode "shared"): as the SEPARATE boot's bring-up; FB = the one
  shared base at boot. Rows build_facilities, alien_containment, new_research (LAST), each on a fresh lift-only
  SharedBaseN built by the host's build_new_base at BASE2_POS / BASE3_POS / BASE4_POS and present on both machines
  (set_funds 2x the cost on the host only if a build is unaffordable). Per row: client real BASES (key 2 if
  SharedBaseN is not shown); open the window (build_facilities: real BUILD FACILITIES; alien_containment: the
  screen_push containment test command, base = SharedBaseN's index, prisonType 0 (a lift-only base has no
  containment); new_research: real RESEARCH, then real New Project); the host dismantles SharedBaseN; poll the client
  every 0.05 s for W_POP from the OK click; host real GEOSCAPE; read. Recovery before the next row: build_facilities
  real OK / alien_containment real Cancel if the window is still on top (the only presses on a window whose base was
  freed), the base view on FB, real GEOSCAPE. new_research: none (LAST).
  Cells of each window row R:
          R-pre (GUARD) SharedBaseN on both machines; the window on the client's top (new_research:
          NewResearchListState over ResearchState); the host's OK reached; SharedBaseN gone from both lists.  R-pop
          (FIX) within W_POP the window is off the client's stack (new_research: NewResearchListState AND
          ResearchState).  R-view (FIX) within W_POP the client's top BasescapeState and geo_state.selectedBase FB.
END       CRASH (GUARD): no new crash file in the lane's crash folder over both boots; every process alive until its
          shutdown.
Without the fix: visit_sent_home-leave, -log and -mir and the -pop and -view cells of the three window rows FAIL (9 of
19); every other cell PASS. With the fix: all 19 PASS. mir(gc) = geo_state bases with coopIcon true; own(gc) =
coopIcon and coopBase false; census rows [coopBaseId, name, coopIcon, coopBase, lon, lat]. LEAVE = engine-log lines
holding "[coop] removed base: the partner removed the base this player views". Every press is a real click_widget or
inject_input except the logged test commands build_new_base, geo_set_speed, screen_push and set_funds. One EVIDENCE
line per row, one PASS / FAIL line per cell, then the row verdict; a precondition miss ends its row (CAPTURE line,
later cells "not reached") and the file goes on; a boot miss fails its first row's -pre cell with ONE CAPTURE line.
ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_removed_base_views.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402

KEY = "49558"                               # lobby key (unused by every other test file)
BASE2_POS = (LAND_LON + 0.03, LAND_LAT + 0.03)     # HostBase2 / SharedBase2: on land
BASE3_POS = (LAND_LON + 0.06, LAND_LAT + 0.03)     # HostBase3 / SharedBase3: on land
BASE4_POS = (LAND_LON + 0.09, LAND_LAT + 0.03)     # SharedBase4: on land
LIFT = (80, 80)                             # build_new_base's lift (2, 2), BaseView GRID 32: its centre
KEY_1, ZOOM_MIN, SYM_PLUS = 49, 3, 43
W_LEAVE, W_POP = 5.0, 2.0
DEL_SETTLE, RT_SETTLE, W_END, W_BACK = 3.0, 3.0, 15.0, 30.0
W_VISIT, BOOT_S = 20.0, 60.0
NEEDLE_A = "[coop] removed base: id=%s cache="
LEAVE = "[coop] removed base: the partner removed the base this player views"
LOGN = ("[coop] removed base: ", "[coop] coopBase3 marker", "the host's own world", "[coop-session]", "coop-ui] push", "coop-ui] pop")
ENDS = ("CutsceneState", "StatisticsState", "SlideshowState")
WIN = {"build_facilities": "BuildFacilitiesState", "alien_containment": "ManageAlienContainmentState",
       "new_research": "NewResearchListState"}
ROWS = (("live_visit_stays", ("live_visit_stays-pre", "live_visit_stays-stay", "live_visit_stays-gone")),
        ("visit_sent_home", ("visit_sent_home-pre", "visit_sent_home-leave", "visit_sent_home-log",
                             "visit_sent_home-mir", "visit_sent_home-end", "visit_sent_home-host")),
        ("build_facilities", ("build_facilities-pre", "build_facilities-pop", "build_facilities-view")),
        ("alien_containment", ("alien_containment-pre", "alien_containment-pop", "alien_containment-view")),
        ("new_research", ("new_research-pre", "new_research-pop", "new_research-view")),
        ("END", ("CRASH",)))
FIX = ("visit_sent_home-leave", "visit_sent_home-log", "visit_sent_home-mir", "build_facilities-pop",
       "build_facilities-view", "alien_containment-pop", "alien_containment-view", "new_research-pop",
       "new_research-view")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]


class Stop(Exception):  # a precondition missed: the row ends here
    pass


# ----- probes and real input -----
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
    return {"t": now(), "bases": bl, "stack": stk(gc), "selected": g.get("selectedBase"), "funds": g.get("funds"), "error": g.get("error")}
def mir(c): return [b for b in c["bases"] if b[2]]
def mir_ids(c): return [b[0] for b in mir(c)]
def own(c): return [b for b in c["bases"] if not b[2] and not b[3]]
def own_names(c): return [b[1] for b in own(c)]
def names(c): return [b[1] for b in c["bases"]]
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
    """a real click_widget on a visible, not hidden widget whose text is `text` (case-insensitive)"""
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
def settle(gc, secs):
    """polls gc's census every 0.25 s for secs: the trace of (mirror ids, base names, top) changes"""
    t0, trace, last = time.time(), [], None
    while time.time() - t0 < secs:
        c = census(gc)
        e = [mir_ids(c), names(c), c["stack"][-1:]]
        if e != last:
            trace.append([round(time.time() - t0, 2)] + e)
            last = e
        time.sleep(0.25)
    return trace
def build_base2(b, gc, name, pos):
    """the harness base-build test command (BuildNewBaseState -> ConfirmNewBaseState -> BaseNameState ->
    PlaceLiftState, real states), then a real GEOSCAPE if the new base's BasescapeState shows; set_funds (a test
    command) 2x the last cost only when the funds are below it"""
    f0, fl = census(gc).get("funds") or 0, None
    if b.cost and f0 < b.cost:
        fl = q(gc, {"cmd": "set_funds", "value": 2 * b.cost})
    r = q(gc, {"cmd": "build_new_base", "lon": pos[0], "lat": pos[1], "name": name})
    b.cost = r.get("cost") or b.cost
    if not r.get("ok"):
        raise Stop("build_new_base %s -> %s (funds %s, set_funds %s)" % (name, r, f0, fl))
    time.sleep(1.0)
    if top(gc) == "BasescapeState":
        must_click(gc, "GEOSCAPE", 10)
    wait_top(gc, "GeoscapeState", 15)
    return {"reply": r, "funds": f0, "setFunds": fl}
def other_has(gc, name, timeout=30):
    v, s = wait(lambda: name in names(census(gc)), timeout, 0.25)
    if not v:
        raise Stop("%s has no base %s within %d s: %s" % (gc.name, name, timeout, census(gc)["bases"]))
    return s
def open_base(gc, name):
    """real BASES; if the shown base is not `name`, the real key of its index in the view's live list (keyBaseSelectN)"""
    must_click(gc, "BASES", 10)
    wait_top(gc, "BasescapeState", 10)
    c = census(gc)
    rec = {"selected": c["selected"], "key": None}
    if rec["selected"] != name:
        if name not in names(c):
            raise Stop("%s base view list %s lacks %r" % (gc.name, names(c), name))
        rec["key"] = KEY_1 + names(c).index(name)
        key(gc, rec["key"])
        time.sleep(0.5)
        rec["selected"] = census(gc)["selected"]
    if rec["selected"] != name:
        raise Stop("%s basescape shows %r not %r" % (gc.name, rec["selected"], name))
    return rec
def dismantle(gc, sc, name, during=None):
    """open_base, the BaseView lift cell, DismantleFacilityState, its real OK; during(t_ok) runs right after the OK click"""
    rec = open_base(gc, name)
    v = next((z for z in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if (z.get("type") or "").endswith("::BaseView")), None)
    if not v:
        raise Stop("no BaseView on %s" % gc.name)
    rec["lift"] = inject(gc, sc, v["x"] + LIFT[0], v["y"] + LIFT[1])
    rec["dfsS"] = wait_top(gc, "DismantleFacilityState", 5)
    ok = must_click(gc, "OK", 5)
    rec["tc"] = ok["tc"]
    rec["during"] = during(ok["tc"]) if during else None
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
        self.host = GameClient("host", None, make_user_dir("removed_base_views_%s_host" % tag))
        self.client = GameClient("client", None, make_user_dir("removed_base_views_%s_client" % tag))
        self.sc, self.cost = {}, None
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
        if self.b is not None and alive(self.b.host) and alive(self.b.client):
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
def bring_up(b, mode, st):
    for gc in (b.host, b.client):
        gc.spawn()
    for gc in (b.host, b.client):
        gc.connect(timeout=BOOT_S)
    session.new_campaign(b.host, b.client, port=KEY, campaign_mode=mode)
    for gc in (b.host, b.client):
        wait_top(gc, "GeoscapeState", 60)
        q(gc, {"cmd": "geo_set_speed", "idx": 0})
    time.sleep(2.0)
    b.sc = {"host": scale(b.host), "client": scale(b.client)}
    p = both(b)
    st["boot"] = {"sc": b.sc, "host": p["host"]["bases"], "client": p["client"]["bases"], "stacks": [p["host"]["stack"], p["client"]["stack"]]}
    if p["host"]["stack"] != ["GeoscapeState"] or p["client"]["stack"] != ["GeoscapeState"]:
        raise Stop("boot: stacks %s / %s" % (p["host"]["stack"], p["client"]["stack"]))
    if mode == "shared":
        if len(p["host"]["bases"]) != 1 or names(p["host"]) != names(p["client"]):
            raise Stop("boot: host bases %s, client bases %s (want one shared base)" % (p["host"]["bases"], p["client"]["bases"]))
        st["FB"] = names(p["host"])[0]
        return
    if not (len(own(p["host"])) == 1 and len(own(p["client"])) == 1 and len(mir(p["client"])) == 1):
        raise Stop("boot: host own %s, client own %s, client mirrors %s" % (own(p["host"]), own(p["client"]), mir(p["client"])))
    hb = mir(p["client"])[0]
    st.update({"HB_ID": hb[0], "HB": hb[1], "HB_POS": hb[4:6]})
    st["builds"] = [build_base2(b, b.host, "HostBase2", BASE2_POS), build_base2(b, b.host, "HostBase3", BASE3_POS)]
    other_has(b.client, "HostBase2")
    other_has(b.client, "HostBase3")
    time.sleep(1.0)
    p = both(b)
    m = {x[1]: x for x in mir(p["client"])}
    if not ("HostBase2" in m and "HostBase3" in m and {"HostBase2", "HostBase3"} <= set(own_names(p["host"]))):
        raise Stop("afterBuild: client mirrors %s, host own %s" % (mir(p["client"]), own(p["host"])))
    st.update({"HB2_ID": m["HostBase2"][0], "HB2_POS": m["HostBase2"][4:6], "HB3_ID": m["HostBase3"][0]})
def visit(b, r, name, pos):
    c = b.client
    mk = click_marker(c, b.sc["client"], pos[0], pos[1], name)
    v, s = wait(lambda: top(c) == "BasescapeState" and coop(c).get("insideCoopBase") is True, W_VISIT)
    g = census(c)
    r.ev["visit"] = {"marker": mk, "openS": s, "selected": g["selected"], "bases": g["bases"], "stack": g["stack"]}
    r.need(v and g["selected"] == name, "the visit of %s did not open: top %s, selectedBase %r" % (name, g["stack"], g["selected"]))
def row_live_visit_stays(b, r, st):
    h, c, ev = b.host, b.client, r.ev
    ev["ids"] = {"HB_ID": st["HB_ID"], "HB": st["HB"], "HB2_ID": st["HB2_ID"], "HB3_ID": st["HB3_ID"]}
    visit(b, r, st["HB"], st["HB_POS"])
    ev["dismantle"] = dismantle(h, b.sc["host"], "HostBase3")
    must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState", 15)
    ev["delSettle"] = settle(c, DEL_SETTLE)
    d = census(c)
    ins = coop(c).get("insideCoopBase")
    ev["afterDel"] = {"stack": d["stack"], "selected": d["selected"], "inside": ins, "bases": d["bases"], "hostOwn": own_names(census(h))}
    r.cell("live_visit_stays-pre", True,
           "HostBase2 %s / HostBase3 %s in mir(client); the visit opened on %r; the host's OK reached" % (
               st["HB2_ID"], st["HB3_ID"], ev["visit"]["selected"]))
    r.cell("live_visit_stays-stay", d["stack"][-1:] == ["BasescapeState"] and ins is True and
           d["selected"] == st["HB"] and st["HB3_ID"] not in [x[0] for x in d["bases"]],
           "after DEL_SETTLE: top %s, insideCoopBase %s, selectedBase %r, live bases %s" % (
               d["stack"][-1:], ins, d["selected"], [x[:2] for x in d["bases"]]))
    r.need(d["stack"][-1:] == ["BasescapeState"] and d["selected"] == st["HB"], "the client's view no longer shows HB: no GEOSCAPE press")
    must_click(c, "GEOSCAPE", 10)
    ev["backS"] = wait(lambda: top(c) == "GeoscapeState" and coop(c).get("insideCoopBase") is False, W_BACK)
    r.need(ev["backS"][0], "the client not back on its own GeoscapeState within W_BACK: %s" % stk(c))
    ev["rtSettle"] = settle(c, RT_SETTLE)
    a = census(c)
    ev["after"] = a["bases"]
    r.cell("live_visit_stays-gone", len(own(a)) > 0 and st["HB3_ID"] not in mir_ids(a),
           "after RT_SETTLE: own(client) %s, mir(client) %s; HB3_ID %s" % (own_names(a), mir_ids(a), st["HB3_ID"]))
def row_visit_sent_home(b, r, st):
    h, c, ev = b.host, b.client, r.ev
    ev["ids"] = {"HB_ID": st["HB_ID"], "HB2_ID": st["HB2_ID"]}
    visit(b, r, "HostBase2", st["HB2_POS"])
    mark = [len(logl(h)), len(logl(c))]  # MARK
    tops = []  # [t from the OK, client stack, host stack]: the WATCH up to W_END

    def leave_poll(tc):
        tr, last, at = [], None, None
        while time.time() - tc < W_LEAVE:
            sc_, g, sh = stk(c), census(c), stk(h)
            tt = round(time.time() - tc, 3)
            tops.append([tt, sc_, sh])
            e = [sc_[-2:], own_names(g), g["selected"]]
            if e != last:
                tr.append([tt] + e)
                last = e
            if at is None and sc_[-1:] == ["GeoscapeState"] and own(g):
                at = tt
            time.sleep(0.05)
        return {"trace": tr, "leaveAt": at}
    d = ev["dismantle"] = dismantle(h, b.sc["host"], "HostBase2", during=leave_poll)
    r.cell("visit_sent_home-pre", True, "the visit opened on %r; the host's OK reached" % ev["visit"]["selected"])
    must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState", 15)
    t0, rt, last = time.time(), [], None
    while time.time() - t0 < RT_SETTLE:
        g = census(c)
        tops.append([round(time.time() - d["tc"], 3), g["stack"], stk(h)])
        if [mir_ids(g), g["stack"][-1:]] != last:
            last = [mir_ids(g), g["stack"][-1:]]
            rt.append([round(time.time() - t0, 2)] + last)
        time.sleep(0.25)
    a, ha = census(c), census(h)
    ev["rtSettle"], ev["after"] = rt, {"client": a["bases"], "clientStack": a["stack"], "host": ha["bases"], "hostStack": ha["stack"]}
    while time.time() - d["tc"] < W_END:
        tops.append([round(time.time() - d["tc"], 3), stk(c), stk(h)])
        time.sleep(0.05)
    ends = [t for t in tops if any(s in ENDS for s in t[1] + t[2])]
    ln = ev["lines"] = {"leave": hits(c, LEAVE, mark[1]), "leaveHost": hits(h, LEAVE, mark[0]), "removed": hits(c, NEEDLE_A % st["HB2_ID"], mark[1])}
    ev["watch"] = {"n": len(tops), "clientTops": sorted(set(t[1][-1] for t in tops if t[1])), "hostTops": sorted(set(t[2][-1] for t in tops if t[2])),
                   "ends": ends[:3]}
    lv = d["during"]
    r.cell("visit_sent_home-leave", lv["leaveAt"] is not None,
           "within W_LEAVE: GeoscapeState with own(client) at +%s s; trace %s" % (lv["leaveAt"], lv["trace"]))
    r.cell("visit_sent_home-log", len(ln["leave"]) == 1, "the client's LEAVE lines since MARK: %d %s (want exactly 1)"
           % (len(ln["leave"]), ln["leave"]))
    r.cell("visit_sent_home-mir", sorted(mir_ids(a)) == [st["HB_ID"]],
           "after RT_SETTLE: mir(client) %s, stack %s (want [%s])" % (mir_ids(a), a["stack"], st["HB_ID"]))
    r.cell("visit_sent_home-end", not ends, "%d polls up to W_END; client tops %s, host tops %s; end states %s" % (
        len(tops), ev["watch"]["clientTops"], ev["watch"]["hostTops"], ends[:2]))
    r.cell("visit_sent_home-host", "HostBase2" not in own_names(ha) and ha["stack"][-1:] == ["GeoscapeState"],
           "host own %s, host stack %s" % (own_names(ha), ha["stack"]))
def row_window(b, r, st, rid, n, pos):
    h, c, ev, win = b.host, b.client, r.ev, WIN[rid]
    bn = ev["base"] = "SharedBase%d" % n
    ev["build"] = build_base2(b, h, bn, pos)
    ev["bothS"] = wait(lambda: bn in names(census(c)) and bn in names(census(h)), 30, 0.25)
    if top(h) == "BasescapeState":
        must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState", 15)
    time.sleep(1.0)
    p = both(b)
    ev["built"] = {"host": names(p["host"]), "client": names(p["client"])}
    r.need(bn in names(p["host"]) and bn in names(p["client"]), "%s not on both machines: %s" % (bn, ev["built"]))
    ev["open"] = open_base(c, bn)
    if rid == "build_facilities":
        must_click(c, "BUILD FACILITIES", 10)
    elif rid == "alien_containment":
        ev["screenPush"] = q(c, {"cmd": "screen_push", "screen": "containment", "base": names(census(c)).index(bn),
                                 "prisonType": 0})
        r.need(ev["screenPush"].get("ok"), "screen_push containment refused: %s" % ev["screenPush"])
    else:
        must_click(c, "RESEARCH", 10)
        wait_top(c, "ResearchState", 10)
        session.wait_widget_ready(c, "New Project")
        must_click(c, "New Project", 10)
    wait_top(c, win, 10)
    if rid == "alien_containment":
        session.wait_widget_ready(c, "Cancel")
    time.sleep(1.0)
    w0 = ev["window"] = stk(c)
    r.need(w0[-1:] == [win] and (rid != "new_research" or w0[-2:-1] == ["ResearchState"]),
           "the client's window not on top: %s" % w0)

    def pop_poll(tc):
        tr, last, pop_at, view_at = [], None, None, None
        while time.time() - tc < W_POP:
            sc_, g = stk(c), census(c)
            tt = round(time.time() - tc, 3)
            e = [sc_[-3:], g["selected"]]
            if e != last:
                tr.append([tt] + e)
                last = e
            if pop_at is None and win not in sc_ and (rid != "new_research" or "ResearchState" not in sc_):
                pop_at = tt
            if view_at is None and sc_[-1:] == ["BasescapeState"] and g["selected"] == st["FB"]:
                view_at = tt
            time.sleep(0.05)
        return {"trace": tr, "popAt": pop_at, "viewAt": view_at}
    d = ev["dismantle"] = dismantle(h, b.sc["host"], bn, during=pop_poll)
    must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState", 15)
    a = both(b)
    ev["after"] = {"client": a["client"]["stack"], "clientBases": names(a["client"]), "hostBases": names(a["host"])}
    pp = d["during"]
    r.cell(rid + "-pre", bn not in names(a["client"]) and bn not in names(a["host"]),
           "%s built on both; window %s; the host's OK reached; after: client bases %s, host bases %s" % (bn, w0[-2:], names(a["client"]),
                                                                                                      names(a["host"])))
    r.cell(rid + "-pop", pp["popAt"] is not None, "within W_POP the window off the stack at +%s s; trace %s" % (pp["popAt"], pp["trace"]))
    r.cell(rid + "-view", pp["viewAt"] is not None, "within W_POP BasescapeState with selectedBase %r at +%s s" % (st["FB"], pp["viewAt"]))
    if rid == "new_research":
        return  # LAST: no press
    # recovery: build_facilities's OK / alien_containment's Cancel, the only presses on a window whose base was freed
    # (both pop only)
    if top(c) == win:
        ev["recovery"] = must_click(c, "OK" if rid == "build_facilities" else "Cancel", 5)
    v, s = wait(lambda: top(c) == "BasescapeState" and census(c)["selected"] == st["FB"], 5)
    r.need(v, "recovery: the client's base view not on %r: %s" % (st["FB"], stk(c)))
    must_click(c, "GEOSCAPE", 10)
    wait_top(c, "GeoscapeState", 15)
    time.sleep(0.5)
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
def run_boot(x, tag, mode, rows):
    b, st = Boot(tag), {}
    try:
        try:
            bring_up(b, mode, st)
        except Exception as e:  # noqa: BLE001 - a boot miss fails the first row's -pre cell with ONE CAPTURE line
            r = Row(x, b, rows[0][0])
            r.ev["boot"] = st
            r.finish("boot miss: %s: %s" % (type(e).__name__, str(e)[:300]))
            for rid, _fn in rows[1:]:
                Row(x, None, rid).finish("boot miss", capture_it=False)
        else:
            for rid, fn in rows:
                run_row(x, b, rid, fn, st)
    finally:
        for gc in (b.client, b.host):
            x.alive.append(["%s_%s" % (tag, gc.name), alive(gc)])
            try:
                if gc.proc is not None and alive(gc):
                    gc.shutdown(expected_returncodes=OKRC)
            except Exception as e:  # noqa: BLE001
                print("FAIL shutdown %s %s: %s" % (tag, gc.name, str(e)[:300]), flush=True)
                x.alive[-1][1] = False
def main():
    x, crash0 = X(), crashes()
    T0[0] = time.time()
    try:
        run_boot(x, "separate", "coop",
                 (("live_visit_stays", row_live_visit_stays), ("visit_sent_home", row_visit_sent_home)))
        run_boot(x, "shared", "shared",
                 tuple((rid, (lambda rid, n, pos: lambda b, r, st: row_window(b, r, st, rid, n, pos))(rid, n, pos))
                       for rid, n, pos in (("build_facilities", 2, BASE2_POS), ("alien_containment", 3, BASE3_POS),
                                           ("new_research", 4, BASE4_POS))))
    finally:
        r, new = Row(x, None, "END"), sorted(crashes() - crash0)
        r.ev.update({"newCrash": [os.path.basename(p) for p in new], "aliveUntilShutdown": x.alive, "crashDir": harness.CRASH_DIR})
        r.cell("CRASH", not new and x.alive and all(a[1] for a in x.alive),
               "new crash files %d %s; alive until shutdown %s" % (len(new), r.ev["newCrash"][:3], x.alive))
        r.finish()
    cl = [cid for _r, cs in ROWS for cid in cs]
    print("SUMMARY test_removed_base_views: %d/%d cells pass; failing %s; wall %.1f s"
          % (len(cl) - len(set(x.fails)), len(cl), sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
