"""W2-H83 S-C RBH (tools/coop_test/test_removed_base_holders.py): geoscape popups that hold a partner base the partner removes, or one of
that base's crafts, close first, as their CANCEL does (lead L-H81-2, rulings R-LBH3-1 / R-LT18-1, QH83-5 (a), veto line VL-H83-3).
Spec docs rewrite/prompts/w2h83_removed_base_views.md (common) + rewrite/prompts/w2h83_sc_holders.md (f) RBH with its R-LT18-1 AMENDMENT (Z9);
TASK 0 values in rewrite/w2h83-task0/sc/CONSTANTS.md. In a SEPARATE campaign the client's delete_base handler erases the partner's mirror (and
the mirror's crafts) while a globe target list, a craft's window or a destination confirm still holds it (today: the popup stays on top over a
freed pointer). The green (EC1, W2-H81's coopCloseMirrorHolders) closes those popups right before the delete. Probe popup_mirror_check
(PMC, read-only pointer compares on the client): holders = states holding a target, dangling = those holding one in no live list, mirror =
those holding a live co-op mirror.
ONE boot (key KEY, dirs w2h83_h_*, campaign_mode "coop"): spawn + connect; session.new_campaign; geo_set_speed idx 0 both; the window mapping per
machine (real INTERCEPT + CANCEL); the host's build_new_base HostBase2 at MT_POS = HB + (0.02, 0), HostBase3 at B3, HostBase4 at B4 (the
survivor, so losing HB is no game over), each + real GEOSCAPE, each in mir(client).
  Row MT  client real globe click at MT_POS at zoom ZOOM_MT -> MultipleTargetsState listing HostBase and HostBase2; P0; the host dismantles
          HostBase2 (real BASES, the key of its index, the BaseView lift cell, DismantleFacilityState OK) + real GEOSCAPE; DEL_SETTLE; P1.
          Recovery: MultipleTargetsState on top -> its cancel, the real ESC key (it has no Cancel button, F23061).
  Row GC  host craft_force HB's first craft STR_OUT at GC_POS = HB + (0.30, 0.10), dest a site at GC_POS + (0.6, 0); its mirror under HB's
          mirror on the client; client real globe click on it -> GeoscapeCraftState; P0; host STRIP (get_soldiers, set_soldier_dead on every HB
          soldier, host only); spawn_ufo; trigger_base_defense -> BaseDestroyedState within W_BDS; host real OK; DEL_SETTLE; P1.
          Recovery: GeoscapeCraftState on top -> its real CANCEL.
  Row CD  (LAST) client real INTERCEPT, the first READY STR_INTERCEPTOR row -> SelectDestinationState, a real globe click on HostBase3 ->
          ConfirmDestinationState on HostBase3; P0; the host dismantles HostBase3 + real GEOSCAPE; DEL_SETTLE; P1. No press, end of the boot.
  Cells per row R: R-pre (GUARD) the popup on the client's top holding the doomed object (P0: holders 1, dangling 0, mirror 1); the host's
          delete step reached (MT / CD: the base gone from own(host) after the DismantleFacilityState OK; GC: BaseDestroyedState, HB gone from
          own(host) after the OK).  R-dangle (FIX) P1 dangling 0.  R-closed (FIX) MT / GC: P1 top GeoscapeState and holders 0; CD (Z9): P1 no
          ConfirmDestinationState on the stack, top SelectDestinationState, holders 0.
  END     CRASH (GUARD): no new crash file in the lane's crash folder since the file start; both processes alive until their shutdown.
Red today: MT-dangle, MT-closed, GC-dangle, GC-closed, CD-dangle, CD-closed FAIL (6 of 10); every other cell PASS. Green (EC1): all 10 PASS.
Ruling R-H83-7: once GC has lost the host's first base, the host's BASES opens the partner's mirror and its GEOSCAPE reloads a stale
world; no cell reads the host after CD's removal. mir(gc) = geo_state bases with coopIcon true; own(gc) = coopIcon and coopBase false.
Every press is a real click_widget or inject_input except the logged levers build_new_base, geo_set_speed, globe_point's centre (staging: the
player turns the globe), spawn_mission_site, craft_force, set_soldier_dead, spawn_ufo and trigger_base_defense. One EVIDENCE line per row, one
PASS / FAIL line per cell, then the row verdict; a precondition miss ends its row (CAPTURE line, later cells "not reached") and the file goes on;
a boot miss fails MT-pre with ONE CAPTURE line. ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_removed_base_holders.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402

KEY = "49559"                               # lobby key (CONSTANTS.md; 0 hits in src + tools at 60f182398)
MT_OFF, GC_OFF, SITE_DLON = (0.02, 0.0), (0.30, 0.10), 0.6   # from HB
B3 = (LAND_LON + 0.06, LAND_LAT + 0.03)     # HostBase3: on land
B4 = (LAND_LON + 0.09, LAND_LAT + 0.03)     # HostBase4: on land (TASK 0; S-A's B rule)
LIFT = (80, 80)                             # build_new_base's lift (2, 2), BaseView GRID 32: its centre
KEY_1, SYM_PLUS, SYM_MINUS, SYM_ESC, ZOOM_MT, ZOOM_MIN = 49, 43, 45, 27, 2, 3
DEL_SETTLE, W_BDS, MIRROR_S, BOOT_S = 3.0, 5.0, 30.0, 60.0
SITE = {"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION", "race": "STR_SECTOID", "hours": 240}
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID",
       "trajectory": "P0", "state": "flying"}
NEEDLE = "[coop] removed base: id=%s cache="
LOGN = ("[coop] removed base: ", "[coop] W2-H81", "[coop-session]", "coop-ui] push", "coop-ui] pop")
ROWS = (("MT", ("MT-pre", "MT-dangle", "MT-closed")), ("GC", ("GC-pre", "GC-dangle", "GC-closed")), ("CD", ("CD-pre", "CD-dangle", "CD-closed")),
        ("END", ("CRASH",)))
FIX = ("MT-dangle", "MT-closed", "GC-dangle", "GC-closed", "CD-dangle", "CD-closed")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]


class Stop(Exception):  # a precondition missed: the row ends here
    pass


# ----- probes and real input (copied from docs rewrite/lbh3-cap/cap.py and the W2-H83 / W2-H81 tests, never imported) -----
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
def pmc(gc):
    r = q(gc, {"cmd": "popup_mirror_check"})
    return {k: r.get(k) for k in ("holders", "dangling", "mirror", "queued", "queuedDangling", "error") if k in r}
def pmc3(p): return [p.get("holders"), p.get("dangling"), p.get("mirror")]
def census(gc, crafts=False):
    g = q(gc, {"cmd": "geo_state"})
    bl = []
    for b in g.get("bases", []):
        e = [b.get("coopBaseId"), b.get("name"), bool(b.get("coopIcon")), bool(b.get("coopBase")), round(b.get("lon") or 0, 4),
             round(b.get("lat") or 0, 4)]
        if crafts:
            e.append([[c.get("type"), c.get("id"), c.get("coop"), c.get("status"), round(c.get("lon") or 0, 4), round(c.get("lat") or 0, 4),
                       c.get("name")] for c in b.get("crafts", [])])
        bl.append(e)
    return {"t": now(), "bases": bl, "stack": stk(gc), "selected": g.get("selectedBase"), "error": g.get("error")}
def mir(c): return [b for b in c["bases"] if b[2]]
def mir_ids(c): return [b[0] for b in mir(c)]
def own(c): return [b for b in c["bases"] if not b[2] and not b[3]]
def own_names(c): return [b[1] for b in own(c)]
def names(c): return [b[1] for b in c["bases"]]
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
def texts(gc): return [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
def zoom_to(gc, z):
    """real zoom keys (+ / -) until the globe's zoom is z"""
    zs = [globe(gc).get("zoom")]
    while (zs[-1] or 0) != z and len(zs) < 9:
        key(gc, SYM_PLUS if (zs[-1] or 0) < z else SYM_MINUS)
        time.sleep(0.6)
        zs.append(globe(gc).get("zoom"))
    return zs
def globe_click(gc, sc, lon, lat, leave, pick=None):
    """real clicks at (lon, lat)'s pixel + 7 offsets until the top leaves `leave`; a MultipleTargetsState then picks the row `pick`"""
    g, tries = globe(gc, lon=lon, lat=lat), []
    for dx, dy in ((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2)):
        inject(gc, sc, g.get("x") + dx, g.get("y") + dy)
        v, _ = wait(lambda: top(gc) != leave, 1.0)
        tries.append([g.get("x") + dx, g.get("y") + dy, top(gc)])
        if v:
            break
    out = {"px": [g.get("x"), g.get("y")], "tries": tries}
    if pick and top(gc) == "MultipleTargetsState":
        out["targets"] = texts(gc)
        out["pick"] = real_click(gc, pick, 5)
    return out
def build_base2(gc, name, pos):
    """the harness base-build lever (BuildNewBaseState -> ConfirmNewBaseState -> BaseNameState -> PlaceLiftState, real states), then a
    real GEOSCAPE from the new base's BasescapeState"""
    r = q(gc, {"cmd": "build_new_base", "lon": pos[0], "lat": pos[1], "name": name})
    if not r.get("ok"):
        raise Stop("build_new_base %s at %s -> %s" % (name, pos, r))
    time.sleep(1.0)
    if top(gc) == "BasescapeState":
        must_click(gc, "GEOSCAPE", 10)
    wait_top(gc, "GeoscapeState", 15)
    return [round(pos[0], 4), round(pos[1], 4)]
def other_has(gc, name, timeout=30):
    v, s = wait(lambda: name in names(census(gc)), timeout, 0.25)
    if not v:
        raise Stop("%s has no base %s within %d s: %s" % (gc.name, name, timeout, census(gc)["bases"]))
    return s
def dismantle(gc, sc, name):
    """real BASES (the key of `name`'s index in the view's list if another base shows), the BaseView lift cell, DismantleFacilityState,
    its real OK; then own(gc) (the delete step reached)"""
    must_click(gc, "BASES", 10)
    wait_top(gc, "BasescapeState", 10)
    c = census(gc)
    rec = {"selected": c["selected"], "key": None, "view": names(c)}
    if rec["selected"] != name:
        if name not in names(c):
            raise Stop("%s base view list %s lacks %r" % (gc.name, names(c), name))
        rec["key"] = KEY_1 + names(c).index(name)
        key(gc, rec["key"])
        time.sleep(0.5)
        rec["selected"] = census(gc)["selected"]
    if rec["selected"] != name:
        raise Stop("%s basescape shows %r not %r" % (gc.name, rec["selected"], name))
    v = next((z for z in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if (z.get("type") or "").endswith("::BaseView")), None)
    if not v:
        raise Stop("no BaseView on %s" % gc.name)
    rec["lift"] = inject(gc, sc, v["x"] + LIFT[0], v["y"] + LIFT[1])
    rec["dfsS"] = wait_top(gc, "DismantleFacilityState", 5)
    must_click(gc, "OK", 5)
    time.sleep(0.3)
    rec["ownAfterOk"] = own_names(census(gc))
    return rec
def settle(c, secs):
    """the client's (stack tail, PMC) every 0.05 s for secs: the trace of changes; the last read is P1"""
    t0, trace, last, p1 = time.time(), [], None, None
    while time.time() - t0 < secs:
        p1 = {"stack": stk(c), "pmc": pmc(c)}
        e = [p1["stack"][-3:], pmc3(p1["pmc"])]
        if e != last:
            trace.append([round(time.time() - t0, 2)] + e)
            last = e
        time.sleep(0.05)
    return trace, p1
def press_through(gc, cap=60.0):
    """real clicks until GeoscapeState (calm 1 s): an OK screen's 'OK'; a CoopState by its own button (W2-H80 LBU)"""
    steps, t1 = [], time.time()
    while time.time() - t1 < cap:
        t = top(gc)
        if t == "GeoscapeState":
            time.sleep(1.0)
            if top(gc) == "GeoscapeState":
                break
            continue
        if t in ("LoadGameState", "SaveGameState") or (t or "").startswith("probe failed"):
            time.sleep(0.25)
            continue
        if t == "CoopState":
            d = dlg(gc)
            if d.get("backVisible") and d.get("backText"):
                steps.append([round(time.time() - t1, 2), t, d.get("code"), cw(gc, d["backText"], 0.8)["ok"]])
            else:
                time.sleep(0.25)
            continue
        okb = next((x.get("text").strip() for x in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if x.get("visible") and
                    str(x.get("type", "")).endswith("::TextButton") and (x.get("text") or "").strip().lower() == "ok"), None)
        if okb:
            session.wait_widget_ready(gc, okb, timeout=5)
            steps.append([round(time.time() - t1, 2), t, "OK", cw(gc, okb, 0.8)["ok"]])
        else:
            steps.append([round(time.time() - t1, 2), t, "no OK"])
            time.sleep(1.0)
            if len(steps) > 3 and all(s[1] == t and s[2] == "no OK" for s in steps[-3:]):
                break
    return {"steps": steps, "secs": round(time.time() - t1, 2)}
def capture(b):
    out = {}
    for gc in (b.host, b.client):
        out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None} if not alive(gc) else {
            "get_state": q(gc, {"cmd": "get_state"}), "get_coop": q(gc, {"cmd": "get_coop"}), "dialog": dlg(gc), "geo_state": census(gc),
            "pmc": pmc(gc), "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-40:]]}
    return out
# ----- the boot and the rows -----
class Boot:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("w2h83_h_host"))
        self.client = GameClient("client", None, make_user_dir("w2h83_h_client"))
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
    h, c = census(b.host), census(b.client)
    st["boot"] = {"sc": b.sc, "host": h["bases"], "client": c["bases"], "stacks": [h["stack"], c["stack"]]}
    if not (h["stack"] == ["GeoscapeState"] and c["stack"] == ["GeoscapeState"] and len(own(h)) == 1 and len(own(c)) == 1 and len(mir(c)) == 1):
        raise Stop("boot: stacks %s / %s, host own %s, client own %s, client mirrors %s" % (h["stack"], c["stack"], own(h), own(c), mir(c)))
    hb = own(h)[0]
    st["HB"] = {"id": mir_ids(c)[0], "name": hb[1], "pos": (hb[4], hb[5])}
    st["MT_POS"] = (hb[4] + MT_OFF[0], hb[5] + MT_OFF[1])
    st["GC_POS"] = (hb[4] + GC_OFF[0], hb[5] + GC_OFF[1])
    st["builds"] = {}
    for name, pos in (("HostBase2", st["MT_POS"]), ("HostBase3", B3), ("HostBase4", B4)):
        st["builds"][name] = [build_base2(b.host, name, pos), other_has(b.client, name)]
    time.sleep(1.0)
    m = {x[1]: x[0] for x in mir(census(b.client))}
    if not all(n in m for n in ("HostBase2", "HostBase3", "HostBase4")):
        raise Stop("the three bases not all in mir(client): %s" % m)
    st["ids"] = m
def row_mt(b, r, st):
    h, c, ev = b.host, b.client, r.ev
    ev["ids"], ev["boot"] = st["ids"], st.get("boot")
    globe(c, centerLon=st["MT_POS"][0], centerLat=st["MT_POS"][1])
    ev["zooms"] = zoom_to(c, ZOOM_MT)
    ev["click"] = globe_click(c, b.sc["client"], st["MT_POS"][0], st["MT_POS"][1], "GeoscapeState")
    time.sleep(0.3)
    p0 = ev["P0"] = {"stack": stk(c), "pmc": pmc(c), "targets": texts(c)}
    r.need(p0["stack"][-1:] == ["MultipleTargetsState"] and {"HostBase", "HostBase2"} <= set(t.strip() for t in p0["targets"]) and
           pmc3(p0["pmc"]) == [1, 0, 1], "MT P0: client %s, targets %s, PMC %s (want MultipleTargetsState listing HostBase and HostBase2, "
           "PMC [1, 0, 1])" % (p0["stack"], p0["targets"], pmc3(p0["pmc"])))
    mark = len(logl(c))
    d = ev["dismantle"] = dismantle(h, b.sc["host"], "HostBase2")
    r.need("HostBase2" not in d["ownAfterOk"], "the host's own still holds HostBase2 after its OK: %s" % d["ownAfterOk"])
    must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState", 15)
    ev["settle"], p1 = settle(c, DEL_SETTLE)
    ev["P1"], ev["line"] = p1, hits(c, NEEDLE % st["ids"]["HostBase2"], mark)
    r.cell("MT-pre", True, "client MultipleTargetsState %s, PMC %s; the host's OK reached (own after %s)" % (
        p0["targets"], pmc3(p0["pmc"]), d["ownAfterOk"]))
    r.cell("MT-dangle", p1["pmc"].get("dangling") == 0, "P1 PMC %s (want dangling 0)" % pmc3(p1["pmc"]))
    r.cell("MT-closed", p1["stack"][-1:] == ["GeoscapeState"] and p1["pmc"].get("holders") == 0,
           "P1 client %s, PMC holders %s (want top GeoscapeState, holders 0)" % (p1["stack"], p1["pmc"].get("holders")))
    if top(c) == "MultipleTargetsState":  # red recovery: its cancel is keyCancel (ESC) on its first button; it pops only
        ev["recovery"] = [key(c, SYM_ESC), wait(lambda: top(c) == "GeoscapeState", 5)]
def row_gc(b, r, st):
    h, c, ev = b.host, b.client, r.ev
    r.need(top(c) == "GeoscapeState", "GC: the client not on GeoscapeState: %s" % stk(c))
    gp = st["GC_POS"]
    site = q(h, dict(SITE, lon=gp[0] + SITE_DLON, lat=gp[1]))
    hc = [k for x in census(h, True)["bases"] if x[1] == st["HB"]["name"] and not x[2] for k in x[6]]
    r.need(site.get("ok") and hc, "GC: site %s, HB crafts %s" % (site, hc))
    ev["force"] = q(h, {"cmd": "craft_force", "craft_id": hc[0][1], "status": "STR_OUT", "lon": gp[0], "lat": gp[1],
                        "dest": "site:%s" % site.get("site_id"), "fuel": 999999, "lowFuel": False})
    q(h, {"cmd": "geo_set_speed", "idx": 0})

    def mirror_craft():
        return next((k for x in census(c, True)["bases"] if x[0] == st["HB"]["id"] and x[2] for k in x[6]
                     if k[3] == "STR_OUT" and abs(k[4] - gp[0]) < 0.02 and abs(k[5] - gp[1]) < 0.02), None)
    mc, ev["mirrorS"] = wait(mirror_craft, MIRROR_S, 0.25)
    ev["craft"], ev["mirrorCraft"] = hc[0], mc
    r.need(mc, "GC: no STR_OUT craft mirror near GC_POS under HB's mirror on the client within %.0f s" % MIRROR_S)
    globe(c, centerLon=mc[4], centerLat=mc[5])
    ev["zooms"] = zoom_to(c, ZOOM_MIN)
    ev["click"] = globe_click(c, b.sc["client"], mc[4], mc[5], "GeoscapeState", pick=mc[6])
    time.sleep(0.3)
    p0 = ev["P0"] = {"stack": stk(c), "pmc": pmc(c)}
    r.need(p0["stack"][-1:] == ["GeoscapeCraftState"] and pmc3(p0["pmc"]) == [1, 0, 1],
           "GC P0: client %s, PMC %s (want GeoscapeCraftState, PMC [1, 0, 1])" % (p0["stack"], pmc3(p0["pmc"])))
    s0 = q(h, {"cmd": "get_soldiers"})
    hb0 = [x for x in s0.get("bases", []) if x.get("name") == st["HB"]["name"] and not x.get("coopIcon") and not x.get("coopBaseFlag")]
    sids = [s.get("id") for s in (hb0[0].get("soldiers", []) if len(hb0) == 1 else [])]
    rep = [[sid, q(h, {"cmd": "set_soldier_dead", "soldierId": sid})] for sid in sids]
    after = [len(x.get("soldiers", [])) for x in q(h, {"cmd": "get_soldiers"}).get("bases", []) if x.get("name") == st["HB"]["name"]
             and not x.get("coopIcon")]
    ev["strip"] = {"ids": sids, "replies": [[x[0], x[1].get("ok"), x[1].get("dead")] for x in rep], "after": after}
    r.need(sids and all(x[1].get("ok") and x[1].get("dead") for x in rep) and after == [0], "STRIP: %s" % ev["strip"])
    mark = len(logl(c))
    ufo = q(h, UFO)
    reply = q(h, {"cmd": "trigger_base_defense", "ufo_id": ufo.get("ufo_id")})
    t_trig, htr, bds = time.time(), [], None
    while time.time() - t_trig < W_BDS and bds is None:
        hs = stk(h)
        if not htr or htr[-1][1] != hs[-3:]:
            htr.append([round(time.time() - t_trig, 2), hs[-3:]])
        bds = round(time.time() - t_trig, 2) if hs[-1:] == ["BaseDestroyedState"] else None
        time.sleep(0.05)
    ev["trigger"] = {"ufo": ufo, "reply": reply, "hostTrace": htr, "bdsAt": bds}
    r.need(reply.get("ok") and reply.get("base") == st["HB"]["name"], "trigger: %s (want ok, base %r)" % (reply, st["HB"]["name"]))
    r.need(bds is not None and not any("BriefingState" in x[1] for x in htr), "no BaseDestroyedState on the host within W_BDS: %s" % htr)
    ev["hostOk"] = press_through(h)
    ho = own_names(census(h))
    r.need(st["HB"]["name"] not in ho and top(h) == "GeoscapeState", "the host after its OK: own %s, %s" % (ho, stk(h)))
    ev["settle"], p1 = settle(c, DEL_SETTLE)
    ev["P1"], ev["line"] = p1, hits(c, NEEDLE % st["HB"]["id"], mark)
    r.cell("GC-pre", True, "client GeoscapeCraftState on %s, PMC %s; STRIP %d; BaseDestroyedState at +%s s; the host's OK reached (own %s)" % (
        mc[6], pmc3(p0["pmc"]), len(sids), bds, ho))
    r.cell("GC-dangle", p1["pmc"].get("dangling") == 0, "P1 PMC %s (want dangling 0)" % pmc3(p1["pmc"]))
    r.cell("GC-closed", p1["stack"][-1:] == ["GeoscapeState"] and p1["pmc"].get("holders") == 0,
           "P1 client %s, PMC holders %s (want top GeoscapeState, holders 0)" % (p1["stack"], p1["pmc"].get("holders")))
    if top(c) == "GeoscapeCraftState":  # red recovery: its CANCEL pops only (no waypoint)
        ev["recovery"] = [real_click(c, "CANCEL", 5)["ok"], wait(lambda: top(c) == "GeoscapeState", 5)]
def row_cd(b, r, st):
    h, c, ev = b.host, b.client, r.ev
    cc = census(c)
    hb3 = next((m for m in mir(cc) if m[1] == "HostBase3"), None)
    r.need(hb3 and cc["stack"] == ["GeoscapeState"], "CD: client %s, HostBase3 mirror %s" % (cc["stack"], hb3))
    globe(c, centerLon=hb3[4], centerLat=hb3[5])
    ev["zooms"] = zoom_to(c, ZOOM_MIN)
    must_click(c, "INTERCEPT", 10)
    wait_top(c, "InterceptState", 5)
    session.wait_widget_ready(c, "CANCEL")
    rows = q(c, {"cmd": "intercept_list"}).get("rows", [])
    idx = next((i for i, x in enumerate(rows) if x.get("type") == "STR_INTERCEPTOR" and x.get("status") == "STR_READY"), None)
    tl = [w for w in q(c, {"cmd": "list_widgets"}).get("widgets", []) if (w.get("type") or "").endswith("::TextList")]
    ev["rows"], ev["idx"] = [[x.get("craft"), x.get("status")] for x in rows], idx
    r.need(idx is not None and len(tl) == 1, "CD: no READY interceptor row %s or TextLists %d" % (ev["rows"], len(tl)))
    inject(c, b.sc["client"], tl[0]["x"] + 30, tl[0]["y"] + 8 * idx + 4)
    r.need(wait(lambda: top(c) == "SelectDestinationState", 5)[0], "CD: no SelectDestinationState after the row click: %s" % stk(c))
    ev["click"] = globe_click(c, b.sc["client"], hb3[4], hb3[5], "SelectDestinationState", pick="HostBase3")
    time.sleep(0.3)
    p0 = ev["P0"] = {"stack": stk(c), "pmc": pmc(c), "texts": texts(c)[:6]}
    r.need(p0["stack"][-2:] == ["SelectDestinationState", "ConfirmDestinationState"] and "TARGET: HostBase3" in p0["texts"] and
           pmc3(p0["pmc"]) == [1, 0, 1], "CD P0: client %s %s, PMC %s (want ConfirmDestinationState on HostBase3, PMC [1, 0, 1])" % (
               p0["stack"], p0["texts"], pmc3(p0["pmc"])))
    mark = len(logl(c))
    d = ev["dismantle"] = dismantle(h, b.sc["host"], "HostBase3")
    r.need("HostBase3" not in d["ownAfterOk"], "the host's own still holds HostBase3 after its OK: %s" % d["ownAfterOk"])
    must_click(h, "GEOSCAPE", 10)  # the host reloads a stale world here (HB lost in GC); no cell reads the host after it
    wait_top(h, "GeoscapeState", 15)
    ev["settle"], p1 = settle(c, DEL_SETTLE)
    ev["P1"], ev["line"] = p1, hits(c, NEEDLE % st["ids"]["HostBase3"], mark)
    r.cell("CD-pre", True, "client %s %s, PMC %s; the host's OK reached (own after %s)" % (p0["stack"], p0["texts"][-1:], pmc3(p0["pmc"]),
                                                                                          d["ownAfterOk"]))
    r.cell("CD-dangle", p1["pmc"].get("dangling") == 0, "P1 PMC %s (want dangling 0)" % pmc3(p1["pmc"]))
    r.cell("CD-closed", "ConfirmDestinationState" not in p1["stack"] and p1["stack"][-1:] == ["SelectDestinationState"] and
           p1["pmc"].get("holders") == 0, "P1 client %s, PMC holders %s (want no ConfirmDestinationState, top SelectDestinationState, "
           "holders 0)" % (p1["stack"], p1["pmc"].get("holders")))
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
        except Exception as e:  # noqa: BLE001 - a boot miss fails MT-pre with ONE CAPTURE line
            r = Row(x, b, "MT")
            r.ev["boot"] = st.get("boot")
            r.finish("boot miss: %s: %s" % (type(e).__name__, str(e)[:300]))
            for rid in ("GC", "CD"):
                Row(x, None, rid).finish("boot miss", capture_it=False)
        else:
            run_row(x, b, "MT", row_mt, st)
            run_row(x, b, "GC", row_gc, st)
            run_row(x, b, "CD", row_cd, st)
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
    print("SUMMARY W2-H83 S-C RBH: %d/%d cells pass; failing %s; wall %.1f s" % (len(cl) - len(set(x.fails)), len(cl),
                                                                               sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
