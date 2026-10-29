"""W2-H83 S-B2 RBW (tools/coop_test/test_removed_base_windows.py): every co-op window that still shows a base the other player removes
closes before it reads it (lead L-H83-1, rulings R-LBH3-1 / R-H83-2 / R-H83-4, QH83-10 .. QH83-13 (a), veto line VL-H83-4).
Spec docs rewrite/prompts/w2h83_removed_base_views.md (common) + rewrite/prompts/w2h83_sb2_more_guards.md (f) RBW (with its R-LT18-1
amendment); TASK 0 values in rewrite/w2h83-task0/sb2/CONSTANTS.md. Today a window opened on a base keeps it after the other player removes
that base (DISMANTLE, TRANSFER base list, INTERCEPT, MONTHLY COSTS over BASE INFORMATION, the SEPARATE TRANSFER list of shown mirrors), and
BASE INFORMATION under STORES re-reads the freed base (it killed the client in both TASK 0 red boots). The green (F1-F9) closes every such
screen top down right after the co-op drain, one engine line per screen: "[coop] removed base: closed <class> - the base it shows is gone".
TWO boots, each shut down before the next (key KEY). The window mapping per machine: real INTERCEPT + CANCEL.
SHARED boot (dirs w2h83_w_*, campaign_mode "shared"): spawn + connect; session.new_campaign; geo_set_speed idx 0 both; B0 = the one base; the
  host's build_new_base SharedBase2 .. SharedBase7 at P1 .. P6, each on both lists before the next (set_funds on BOTH machines only if the
  funds miss six bases: a host-only value is a SHARED desync the J10 auto-repair re-streams). Per row: R-mark both logs; the receiver opens
  the window; the other machine removes the row's base (real BASES, the key of its index, the BaseView lift cell, DismantleFacilityState OK,
  real GEOSCAPE; ST: the host's fac_dismantle lever); poll the receiver every 0.05 s for W_POP from the OK; read; the red recovery press.
  CTL  client BASES (B0) -> BASE INFORMATION; host removes SharedBase2; client OK, GEOSCAPE.  CTL-pre (GUARD) SharedBase2 on both; the
       client's top BaseInfoState, selectedBase B0; the host's OK reached; SharedBase2 gone from both lists.  CTL-stay (GUARD) every poll
       for W_POP: top BaseInfoState; selectedBase B0; CLOSED(client) empty.
  DF   client BASES, key of SharedBase3, its lift cell -> DismantleFacilityState (no OK); host removes SharedBase3; red recovery CANCEL.
  TB   client BASES (B0) -> TRANSFER -> TransferBaseState listing SharedBase4; host removes SharedBase4; red recovery Cancel.
  IC   client globe click on SharedBase5's marker -> InterceptState; host removes SharedBase5; red recovery Cancel.
  MC   (the HOST receives) host BASES, key of SharedBase6 -> BASE INFORMATION -> Monthly Costs; the CLIENT removes SharedBase6. The host
       stays unpressed for the rest of the boot.
  ST   (LAST) client BASES, key of SharedBase7 -> BASE INFORMATION -> STORES; the host's fac_dismantle lever at its only facility. No
       client press after it.
       R-pre (GUARD) the base on both; the receiver's stack as named; the remover's OK (ST: the lever's reply) reached; the base gone from
       both lists (a dead ST client: a poll without it, or its StoresState pop line - the guard pops only once the base left the list).
       R-pop (FIX) within W_POP none of the row's windows on the receiver's stack.  R-view (FIX) within W_POP the receiver's top is
       BasescapeState with selectedBase B0 (IC: GeoscapeState).  R-log (FIX) CLOSED(receiver, R-mark) == DF [DismantleFacilityState];
       TB [TransferBaseState]; IC [InterceptState]; MC [MonthlyCostsState, BaseInfoState]; ST [StoresState, BaseInfoState].
SEPARATE boot (dirs w2h83_ws_*, campaign_mode "coop"): as above; HB = the host's first base (mir(client)); the host's build_new_base HostBase2
  at P1 + real GEOSCAPE; HostBase2 in mir(client).
  TS   (LAST) client BASES (its own base; key 1 if another shows, W2-H68) -> TRANSFER -> TransferBaseState listing HostBase2 (TS-mark); the
       host removes HostBase2; poll; RT_SETTLE; read. No client press.  TS-pre (GUARD) HostBase2 in mir(client); TransferBaseState over the
       BasescapeState of the client's own base, HostBase2 in its rows; the host's OK reached.  TS-pop (FIX) within W_POP TransferBaseState
       off the client's stack.  TS-view (FIX) within W_POP the client's top BasescapeState, selectedBase its own base.  TS-hide (FIX) after
       RT_SETTLE no coopIcon base in the client's geo_state (the view hides the mirrors again, W2-H8).  TS-log (FIX) CLOSED(client, TS-mark)
       == [TransferBaseState].
END       CRASH (GUARD): no new crash file in the lane's crash folder over both boots; every process alive until its shutdown.
Red today: DF / TB / IC / MC / ST -pop -view -log and TS -pop -view -hide -log FAIL (19 of 28), plus CRASH when the client died inside ST;
every other cell PASS. Green (F1-F9): all 28 PASS. mir(gc) = geo_state bases with coopIcon true; own(gc) = coopIcon and coopBase false;
census rows [coopBaseId, name, coopIcon, coopBase, lon, lat]. CLOSED(gc, since) = the class names of the engine-log lines holding
"[coop] removed base: closed " since the mark, top first. Every press is a real click_widget or inject_input except the logged levers
build_new_base, geo_set_speed, set_funds and fac_dismantle (ST only). One EVIDENCE line per row, one PASS / FAIL line per cell, then the row
verdict; a precondition miss ends its row (CAPTURE line, later cells "not reached") and the file goes on; a boot miss fails its first row's
-pre cell with ONE CAPTURE line. ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_removed_base_windows.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402

KEY = "49587"                               # lobby key (CONSTANTS.md; 0 hits in src + tools at 7a3a61f0f)
P = [(LAND_LON + 0.03 * k, LAND_LAT + 0.03) for k in range(1, 6)] + [(LAND_LON + 0.18, LAND_LAT + 0.09)]  # P6: S54 swap (sea), TASK 0
LIFT = (80, 80)                             # build_new_base's lift (2, 2), BaseView GRID 32: its centre
KEY_1, ZOOM_MIN, SYM_PLUS = 49, 3, 43
W_POP, RT_SETTLE, BOOT_S = 2.0, 3.0, 60.0
CLOSED = "[coop] removed base: closed "
LOGN = ("[coop] removed base: ", "[coop-session]", "coop-ui] push", "coop-ui] pop", "shared_resync")
WIN = {"CTL": ["BaseInfoState"], "DF": ["DismantleFacilityState"], "TB": ["TransferBaseState"], "IC": ["InterceptState"],
       "MC": ["MonthlyCostsState", "BaseInfoState"], "ST": ["StoresState", "BaseInfoState"], "TS": ["TransferBaseState"]}
SHAPE = {"CTL": ["BasescapeState", "BaseInfoState"], "DF": ["BasescapeState", "DismantleFacilityState"],
         "TB": ["BasescapeState", "TransferBaseState"], "IC": ["GeoscapeState", "InterceptState"],
         "MC": ["BasescapeState", "BaseInfoState", "MonthlyCostsState"], "ST": ["BasescapeState", "BaseInfoState", "StoresState"],
         "TS": ["BasescapeState", "TransferBaseState"]}
BASE = {"CTL": "SharedBase2", "DF": "SharedBase3", "TB": "SharedBase4", "IC": "SharedBase5", "MC": "SharedBase6", "ST": "SharedBase7",
        "TS": "HostBase2"}
ROWS = (("CTL", ("CTL-pre", "CTL-stay")),) + tuple((r, tuple("%s-%s" % (r, c) for c in ("pre", "pop", "view", "log")))
                                                  for r in ("DF", "TB", "IC", "MC", "ST")) + \
    (("TS", ("TS-pre", "TS-pop", "TS-view", "TS-hide", "TS-log")), ("END", ("CRASH",)))
FIX = tuple("%s-%s" % (r, c) for r in ("DF", "TB", "IC", "MC", "ST") for c in ("pop", "view", "log")) + \
    ("TS-pop", "TS-view", "TS-hide", "TS-log")
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
def census(gc, raw=False):
    g = q(gc, {"cmd": "geo_state"})
    bl = [[b.get("coopBaseId"), b.get("name"), bool(b.get("coopIcon")), bool(b.get("coopBase")), round(b.get("lon") or 0, 4),
           round(b.get("lat") or 0, 4)] for b in g.get("bases", [])]
    out = {"t": now(), "bases": bl, "stack": stk(gc), "selected": g.get("selectedBase"), "funds": g.get("funds"), "error": g.get("error")}
    if raw:
        out["raw"] = g.get("bases", [])
    return out
def mir(c): return [b for b in c["bases"] if b[2]]
def mir_ids(c): return [b[0] for b in mir(c)]
def own(c): return [b for b in c["bases"] if not b[2] and not b[3]]
def names(c): return [b[1] for b in c["bases"]]
def both(b): return {"host": census(b.host), "client": census(b.client)}
def cpu():
    c = harness.cpu_load()
    return {"t": time.strftime("%H:%M:%S"), "cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}
def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def lines_since(gc, n0): return [ln.split("\t")[0][-13:-1] + " " + ln.split("\t")[-1][:200] for ln in logl(gc)[n0:] if any(n in ln for n in LOGN)]
def closed(gc, n0):
    """CLOSED(gc, since): the class names of the '[coop] removed base: closed ' lines since the mark, in log order (top first)"""
    return [ln.split(CLOSED, 1)[1].split(" - ")[0].replace("class ", "").replace("OpenXcom::", "").strip() for ln in logl(gc)[n0:] if CLOSED in ln]
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
def build_base2(b, gc, name, pos):
    """the harness base-build lever (BuildNewBaseState -> ConfirmNewBaseState -> BaseNameState -> PlaceLiftState, real states), then a
    real GEOSCAPE if the new base's BasescapeState shows"""
    r = q(gc, {"cmd": "build_new_base", "lon": pos[0], "lat": pos[1], "name": name})
    b.cost = r.get("cost") or b.cost
    if not r.get("ok"):
        raise Stop("build_new_base %s at %s -> %s" % (name, pos, r))
    time.sleep(1.0)
    if top(gc) == "BasescapeState":
        must_click(gc, "GEOSCAPE", 10)
    wait_top(gc, "GeoscapeState", 15)
    return {"reply": r, "pos": [round(pos[0], 4), round(pos[1], 4)]}
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
def lift_click(gc, sc):
    v = next((z for z in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if (z.get("type") or "").endswith("::BaseView")), None)
    if not v:
        raise Stop("no BaseView on %s" % gc.name)
    return inject(gc, sc, v["x"] + LIFT[0], v["y"] + LIFT[1])
def dismantle(gc, sc, name, during=None):
    """open_base, the BaseView lift cell, DismantleFacilityState, its real OK; during(t_ok) runs right after the OK click"""
    rec = open_base(gc, name)
    rec["lift"] = lift_click(gc, sc)
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
        self.host = GameClient("host", None, make_user_dir("w2h83_%s_host" % tag))
        self.client = GameClient("client", None, make_user_dir("w2h83_%s_client" % tag))
        self.sc, self.cost = {}, None
class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now()}
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
def bring_up(b, mode, st):
    st["cpu"] = cpu()
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
        st["B0"], st["builds"], st["funds0"] = names(p["host"])[0], [], p["host"]["funds"]
        for k in range(6):
            bn = "SharedBase%d" % (k + 2)
            st["builds"].append(build_base2(b, b.host, bn, P[k]))
            if not wait(lambda: bn in names(census(b.client)) and bn in names(census(b.host)), 30, 0.25)[0]:
                raise Stop("%s not on both machines within 30 s" % bn)
            if k == 0 and b.cost and (census(b.host)["funds"] or 0) < 5 * b.cost:   # both machines: never a host-only SHARED funds value
                st["setFunds"] = [q(gc, {"cmd": "set_funds", "value": 12 * b.cost}) for gc in (b.host, b.client)]
        time.sleep(1.0)
        p, want = both(b), [st["B0"]] + ["SharedBase%d" % k for k in range(2, 8)]
        st["built"] = {"host": names(p["host"]), "client": names(p["client"]), "funds": [p["host"]["funds"], p["client"]["funds"]]}
        if names(p["host"]) != want or names(p["client"]) != want or p["host"]["stack"] != ["GeoscapeState"] or \
                p["client"]["stack"] != ["GeoscapeState"]:
            raise Stop("six bases: host %s %s, client %s %s" % (names(p["host"]), p["host"]["stack"], names(p["client"]), p["client"]["stack"]))
        return
    if not (len(own(p["host"])) == 1 and len(own(p["client"])) == 1 and len(mir(p["client"])) == 1):
        raise Stop("boot: host own %s, client own %s, client mirrors %s" % (own(p["host"]), own(p["client"]), mir(p["client"])))
    st.update({"HB_ID": mir(p["client"])[0][0], "CB": own(p["client"])[0][1]})
    st["builds"] = [build_base2(b, b.host, "HostBase2", P[0])]
    if not wait(lambda: "HostBase2" in names(census(b.client)), 30, 0.25)[0]:
        raise Stop("HostBase2 not in the client's list within 30 s")
    time.sleep(1.0)
    m = {x[1]: x for x in mir(census(b.client))}
    if "HostBase2" not in m:
        raise Stop("HostBase2 not in mir(client): %s" % list(m))
    st["HB2_ID"] = m["HostBase2"][0]
def open_window(b, r, st, rid, bn):
    h, c = b.host, b.client
    if rid in ("CTL", "TB"):
        r.ev["open"] = open_base(c, st["B0"])
        must_click(c, "BASE INFORMATION" if rid == "CTL" else "TRANSFER", 10)
        wait_top(c, WIN[rid][0], 10)
    elif rid == "DF":
        r.ev["open"] = open_base(c, bn)
        r.ev["lift"] = lift_click(c, b.sc["client"])
        wait_top(c, "DismantleFacilityState", 5)
    elif rid == "IC":
        sb = next(x for x in census(c)["bases"] if x[1] == bn)
        r.ev["marker"] = click_marker(c, b.sc["client"], sb[4], sb[5], bn)
        wait_top(c, "InterceptState", 20)
    elif rid in ("MC", "ST"):
        gc = h if rid == "MC" else c
        r.ev["open"] = open_base(gc, bn)
        must_click(gc, "BASE INFORMATION", 10)
        wait_top(gc, "BaseInfoState", 10)
        must_click(gc, "Monthly Costs" if rid == "MC" else "STORES", 10)
        wait_top(gc, WIN[rid][0], 10)
    else:  # TS: the client's own base view (W2-H68: selectedBase its own, else key 1)
        must_click(c, "BASES", 10)
        wait_top(c, "BasescapeState", 10)
        g = census(c)
        r.ev["open"] = {"selected": g["selected"], "key": None}
        if g["selected"] != st["CB"]:
            r.ev["open"]["key"] = KEY_1
            key(c, KEY_1)
            time.sleep(0.5)
        must_click(c, "TRANSFER", 10)
        wait_top(c, "TransferBaseState", 10)
    time.sleep(1.0)
def row(b, r, st, rid):
    h, c, ev, bn = b.host, b.client, r.ev, BASE[rid]
    recv, rem = (h, c) if rid == "MC" else (c, h)
    p0 = both(b)
    ev["before"] = {"host": names(p0["host"]), "client": names(p0["client"]), "clientMir": mir_ids(p0["client"])}
    r.need(bn in names(p0["client"]) and (rid == "TS" or bn in names(p0["host"])), "%s not on both machines: %s" % (bn, ev["before"]))
    if rid == "TS":
        r.need(st["HB2_ID"] in mir_ids(p0["client"]), "HostBase2 %s not in mir(client) %s" % (st["HB2_ID"], mir_ids(p0["client"])))
    mark = [len(logl(h)), len(logl(c))]  # R-mark
    open_window(b, r, st, rid, bn)
    w0 = census(recv)
    ev["window"] = {"stack": w0["stack"], "selected": w0["selected"]}
    if rid in ("TB", "TS"):
        ev["window"]["rows"] = q(c, {"cmd": "screen_state"}).get("rows")
    r.need(w0["stack"][-len(SHAPE[rid]):] == SHAPE[rid], "the %s's stack %s, want ...%s" % (recv.name, w0["stack"], SHAPE[rid]))
    if rid in ("CTL", "TB"):
        r.need(w0["selected"] == st["B0"], "the client's selectedBase %r, want %r" % (w0["selected"], st["B0"]))
    if rid == "TS":
        r.need(w0["selected"] == st["CB"], "the client's selectedBase %r, want its own %r" % (w0["selected"], st["CB"]))
    if rid in ("TB", "TS"):
        r.need(bn in (ev["window"]["rows"] or []), "%s not in the TRANSFER rows %s" % (bn, ev["window"]["rows"]))
    if rid == "TS":
        mark = [len(logl(h)), len(logl(c))]  # TS-mark
    view = ("GeoscapeState", None) if rid == "IC" else ("BaseInfoState", st["B0"]) if rid == "CTL" else \
        ("BasescapeState", st["CB"] if rid == "TS" else st["B0"])

    def pop_poll(tc):
        tr, last, pop_at, view_at, n = [], None, None, None, 0
        while time.time() - tc < W_POP:
            sc_ = stk(recv)
            ok = alive(recv) and bool(sc_) and not sc_[0].startswith("probe failed")
            g = census(recv) if ok else {"selected": None, "bases": []}
            tt, n = round(time.time() - tc, 3), n + 1
            e = [sc_[-4:], g["selected"], names(g)]
            if e != last:
                tr.append([tt] + e)
                last = e
            if pop_at is None and ok and not any(w in sc_ for w in WIN[rid]):
                pop_at = tt
            if view_at is None and ok and sc_[-1:] == [view[0]] and (view[1] is None or g["selected"] == view[1]):
                view_at = tt
            time.sleep(0.05)
        return {"trace": tr, "popAt": pop_at, "viewAt": view_at, "polls": n}
    if rid == "ST":
        sb = next((x for x in census(h, raw=True)["raw"] if x.get("name") == bn), {})
        facs = sb.get("facilities") or []
        ev["facilities"] = facs
        r.need(len(facs) == 1, "%s facilities %s (want its one lift)" % (bn, facs))
        ev["lever"] = q(h, {"cmd": "fac_dismantle", "base": bn, "x": facs[0]["x"], "y": facs[0]["y"]})
        tc = time.time()
        r.need(ev["lever"].get("ok"), "fac_dismantle refused: %s" % ev["lever"])
        d = ev["remove"] = {"lever": True, "during": pop_poll(tc)}
    else:
        d = ev["remove"] = dismantle(rem, b.sc[rem.name], bn, during=pop_poll)
        must_click(rem, "GEOSCAPE", 10)
        wait_top(rem, "GeoscapeState", 15)
    pp = d["during"]
    if rid == "TS":
        t1, rt, last = time.time(), [], None
        while time.time() - t1 < RT_SETTLE:
            g = census(c)
            if [mir_ids(g), g["stack"][-2:]] != last:
                last = [mir_ids(g), g["stack"][-2:]]
                rt.append([round(time.time() - t1, 2)] + last)
            time.sleep(0.25)
        ev["rtSettle"] = rt
    a = both(b)
    cl = ev["closed"] = {"host": closed(h, mark[0]), "client": closed(c, mark[1])}
    ev["after"] = {"host": a["host"]["stack"], "client": a["client"]["stack"], "hostBases": names(a["host"]), "clientBases": names(a["client"]),
                   "clientMir": mir_ids(a["client"]), "selected": a[recv.name]["selected"], "clientAlive": alive(c),
                   "clientRc": c.proc.poll() if c.proc else None}
    # the base left the receiver's list: its census; a dead ST client: a poll without it, or its StoresState pop line (the guard pops only
    # once the base left the list)
    seen = any(t[3] and bn not in t[3] for t in pp["trace"])
    popl = any("pop  class OpenXcom::StoresState" in ln for ln in lines_since(c, mark[1]))
    c_gone = (bn not in names(a["client"])) if alive(c) else (seen or (rid == "ST" and popl))
    gone = c_gone and (rid == "TS" or bn not in names(a["host"]))
    ev["gone"] = {"clientCensus": alive(c), "seenInPoll": seen, "storesPopLine": popl}
    rc = cl[recv.name]
    if rid == "CTL":
        stay = bool(pp["trace"]) and all(t[1][-1:] == ["BaseInfoState"] for t in pp["trace"])
        r.cell("CTL-pre", gone, "SharedBase2 on both %s; window %s, selectedBase %r; the host's OK reached; after: client %s, host %s" % (
            ev["before"]["client"], ev["window"]["stack"][-2:], ev["window"]["selected"], names(a["client"]), names(a["host"])))
        r.cell("CTL-stay", stay and a["client"]["stack"][-1:] == ["BaseInfoState"] and a["client"]["selected"] == st["B0"] and not rc,
               "%d polls: trace %s; after: top %s, selectedBase %r; CLOSED(client) %s" % (pp["polls"], pp["trace"], a["client"]["stack"][-1:],
                                                                                         a["client"]["selected"], rc))
        must_click(c, "OK", 5)
        wait_top(c, "BasescapeState", 5)
        must_click(c, "GEOSCAPE", 10)
        wait_top(c, "GeoscapeState", 15)
        time.sleep(0.5)
        return
    r.cell(rid + "-pre", gone, "%s on both; %s's window %s; the %s reached; after: client %s (gone by %s), host %s" % (
        bn, recv.name, ev["window"]["stack"][-len(SHAPE[rid]):], "lever's reply" if rid == "ST" else "remover's OK", names(a["client"]),
        "census" if alive(c) else ("poll" if seen else "StoresState pop line" if popl else "none"), names(a["host"])))
    r.cell(rid + "-pop", pp["popAt"] is not None, "within W_POP %s off the %s's stack at +%s s; trace %s" % (
        WIN[rid], recv.name, pp["popAt"], pp["trace"]))
    r.cell(rid + "-view", pp["viewAt"] is not None, "within W_POP top %s%s at +%s s" % (
        view[0], "" if view[1] is None else " with selectedBase %r" % view[1], pp["viewAt"]))
    if rid == "TS":
        r.cell("TS-hide", alive(c) and not mir(a["client"]), "after RT_SETTLE coopIcon bases in the client's geo_state %s (want none); trace %s" % (
            mir_ids(a["client"]), ev["rtSettle"]))
    r.cell(rid + "-log", rc == WIN[rid], "CLOSED(%s) %s, want %s; CLOSED(%s) %s" % (
        recv.name, rc, WIN[rid], rem.name, cl[rem.name]))
    if rid in ("DF", "TB", "IC"):  # the red recovery: CANCEL, the only press on a window whose base was freed (pops one screen, reads nothing)
        if top(c) == WIN[rid][0]:
            ev["recovery"] = must_click(c, "CANCEL", 5)
        if rid == "IC":
            wait_top(c, "GeoscapeState", 5)
        else:
            v, s = wait(lambda: top(c) == "BasescapeState" and census(c)["selected"] == st["B0"], 5)
            r.need(v, "recovery: the client's base view not on %r: %s" % (st["B0"], stk(c)))
            must_click(c, "GEOSCAPE", 10)
            wait_top(c, "GeoscapeState", 15)
        time.sleep(0.5)
class X:  # the file's run state: failing cells, every process's alive-until-shutdown record
    def __init__(self): self.fails, self.alive = [], []
def run_boot(x, tag, mode, rows):
    b, st = Boot(tag), {}
    try:
        try:
            bring_up(b, mode, st)
        except Exception as e:  # noqa: BLE001 - a boot miss fails the first row's -pre cell with ONE CAPTURE line
            r = Row(x, b, rows[0])
            r.ev["boot"] = st
            r.finish("boot miss: %s: %s" % (type(e).__name__, str(e)[:300]))
            for rid in rows[1:]:
                Row(x, None, rid).finish("boot miss", capture_it=False)
        else:
            for i, rid in enumerate(rows):
                r = Row(x, b, rid)
                if i == 0:
                    r.ev["boot"] = st
                try:
                    row(b, r, st, rid)
                    r.finish()
                except Stop as e:
                    r.finish(str(e))
                except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
                    r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        for gc in (b.client, b.host):
            x.alive.append(["%s_%s" % (tag, gc.name), alive(gc), gc.proc.poll() if gc.proc else None])
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
        run_boot(x, "w", "shared", ("CTL", "DF", "TB", "IC", "MC", "ST"))
        run_boot(x, "ws", "coop", ("TS",))
    finally:
        r, new = Row(x, None, "END"), sorted(crashes() - crash0)
        r.ev.update({"newCrash": [os.path.basename(p) for p in new], "aliveUntilShutdown": x.alive, "crashDir": harness.CRASH_DIR, "cpu": cpu()})
        r.cell("CRASH", not new and x.alive and all(a[1] for a in x.alive),
               "new crash files %d %s; alive until shutdown %s" % (len(new), r.ev["newCrash"][:3], x.alive))
        r.finish()
    cl = [cid for _r, cs in ROWS for cid in cs]
    print("SUMMARY W2-H83 S-B2 RBW: %d/%d cells pass; failing %s; wall %.1f s" % (len(cl) - len(set(x.fails)), len(cl),
                                                                               sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
