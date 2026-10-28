"""W2-H85 S-B VBS - tools/coop_test/test_view_base_switch.py: a base switch inside a view of the partner's bases keeps the visitor's soldiers
on the partner's craft (lead L-H85-1; ruling R-LH85-1, the same behaviour as R-LH83-2-1; veto line VL-H85-1). A visit (CoopState 55) deep-copies
the guests into EVERY partner base of the view with no craft; BasescapeState::init seats them only for the base on screen (latch _coop_base_init),
so a switch inside the view (keys 1-8, BASE INFORMATION's keys + OK) shows them off the craft and SOLDIERS' OK writes -1 everywhere. Spec docs
rewrite/prompts/w2h85_sb_base_switch.md (f); pins rewrite/w2h85-task0/sb/CONSTANTS.md; helpers copied from docs rewrite/lh85-cap/cap85.py and VLS.
ONE boot (key 49655): SETUP (levers: SEAT the client's guest G on HostBase's Skyranger, host quick save, host builds HostBase2), R2c (guard: direct
real visit of HostBase), R2 (real visit of HostBase2, real key to HostBase, next visit), R2i (SEAT, real visit of HostBase2, real BASE INFORMATION,
real key, its real OK), CRASH. Red today: R2-view/-ok/-blob/-own/-next, R2i-view/-ok/-own (8 of 17). ONE foreground run,
no skip; exit 0 only when every cell passes, else 2.  Run: python tools/coop_test/test_view_base_switch.py   (OXC_HARNESS_SLOT selects the lane)"""
import contextlib, glob, json, os, sys, time  # noqa: E401
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml, geo, harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir  # noqa: E402
KEY, TAG, B2 = "49655", "w2h85b_vbs", "HostBase2"  # lobby key (0 hits at the base); user dirs w2h85b_vbs_*; the partner's second base
OFFSETS = ((0.06, 0.04), (-0.06, 0.04), (0.06, -0.04), (-0.06, -0.04), (0.12, 0.0), (-0.12, 0.0), (0.0, 0.1), (0.0, -0.1))
ZOOM_MIN, SYM_PLUS = 3, 43                         # real '+' presses until globe zoom >= 3 (CAP), at most 7
VISIT, POP, BI, SW, MARK, BLOB, GUEST_S = 60.0, 10.0, 10.0, 2.0, 60.0, 45.0, 40.0
S_VIEW, S_SOLD, S_OK, S_BI, S_BIOK, S_GEO = 1.0, 0.6, 0.5, 0.6, 1.0, 1.0
NOTICE_S = 10.0  # bound: the host's items-received notice (CoopState 150) after the guest transfer (cap-save F23940: it lands 1-16 ms after the reply)
RC_OK, SYNC = (0, 3221226505), "[coop-gift] synced guest craft assignments into own-world blob"
CELLS = {"R2c": ["R2c-pre", "R2c-view", "R2c-ok", "R2c-own"], "R2": ["R2-pre", "R2-exit", "R2-view", "R2-ok", "R2-blob", "R2-own", "R2-next"],
         "R2i": ["R2i-pre", "R2i-exit", "R2i-view", "R2i-ok", "R2i-own"], "CRASH": ["CRASH"]}
T0, RESULTS = time.time(), []
class Stop(Exception):  # a precondition missed: the row ends here
    pass
# ----- probes (copied from docs rewrite/lh85-cap/cap85.py and VLS) -----
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
def gs(gc): return q(gc, {"cmd": "geo_state"})
def names(gc): return [b.get("name") for b in gs(gc).get("bases") or []]
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
    while not (v := pred()) and time.time() - t0 < timeout:
        time.sleep(interval)
    return v or None, round(time.time() - t0, 2)
def need(pred, window, why, interval=0.1):  # wait(pred, window); a miss raises Stop(why())
    v, t = wait(pred, window, interval)
    if not v:
        raise Stop(why())
    return v, t
def need_top(gc, state, window, what, interval=0.1):
    return need(lambda: top(gc) == state, window, lambda: "%s: no %s within %.0f s (stack %s)" % (what, state, window, stack(gc)), interval)[1]
def guest(soldiers, name): return next((s for s in soldiers or [] if s.get("name") == name), None)
def brief(r):  # a base_report reduced to its name, the soldiers' [name, id, craft, coopCraft] and the crafts' [id, type, soldiers]
    return {"name": r.get("name"), "error": r.get("error"), "soldiers": [[z.get("name"), z.get("id"), z.get("craft"), z.get("coopCraft")]
            for z in r.get("soldiers") or []], "crafts": [[c.get("id"), c.get("type"), c.get("soldiers")] for c in r.get("crafts") or []]}
def blob_guest(gc, key, name):
    """dump_coop_file key -> parse the YAML -> the guest's entries [base, coopcraft, coopcrafttype, coopbase] (CAP parse_blob)"""
    d = q(gc, {"cmd": "dump_coop_file", "key": key})
    hits = [p for p in glob.glob(os.path.join(gc.user_dir, "**", key), recursive=True) if os.path.isfile(p)] if d.get("ok") else []
    if not hits:
        return {"dump": "no file" if d.get("ok") else d.get("error")}
    p = max(hits, key=os.path.getmtime)
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            w = next((x for x in yaml.load_all(fh, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) if isinstance(x, dict) and "bases" in x), {})
        return {"guest": [[b.get("name"), s.get("coopcraft"), s.get("coopcrafttype"), s.get("coopbase")] for b in w.get("bases") or []
                          for s in b.get("soldiers") or [] if s.get("name") == name]}
    except Exception as e:  # noqa: BLE001
        return {"parseError": short(e, 200)}
    finally:
        with contextlib.suppress(OSError):
            os.remove(p)
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
            return {"ok": bool(q(gc, {"cmd": "click_widget", "match": w.get("text")}).get("ok")), "s": round(time.time() - t0, 2)}
        seen = [[w.get("text"), w.get("visible"), w.get("hidden")] for w in ws]
        time.sleep(0.05)
    return {"ok": False, "miss": "%s: button %r not shown within %.0f s (%s)" % (gc.name, text, timeout, seen)}
def must(gc, text, timeout=10.0):
    r = real_click(gc, text, timeout)
    if not r.get("ok"):
        raise Stop("press %s: %s (stack %s)" % (text, r, stack(gc)))
    return r
def press_to(gc, text, state, window, settle):  # a real press on `text`, then `state` on top within `window`, then the settle
    must(gc, text, 10)
    t = need_top(gc, state, window, "real " + text, 0.05)
    time.sleep(settle)
    return t
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
    out = {"zooms": zs, "tries": click_px(gc, g.get("x"), g.get("y"), sc)}
    if top(gc) == "MultipleTargetsState":
        out["targets"] = [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
        t = next((t for t in out["targets"] if t.strip() == name), None)
        if t:
            out["pick"] = real_click(gc, t.strip(), 5)
    return out
# ----- steps -----
def visit_real(s, ev, base, label):
    """VISIT(B): the visitor's real click on B's globe marker; inside + BasescapeState within VISIT, 1.0 s"""
    V = s.V
    pb = next((b for b in gs(V).get("bases", []) if b.get("name") == base), None)
    if not pb:
        raise Stop("no %s marker in the visitor's geo_state" % base)
    c = click_marker(V, s.sc, pb["lon"], pb["lat"], base)
    ev[label] = {"base": base, "targets": c.get("targets"), "tries": c["tries"], "zooms": c["zooms"]}
    ev[label]["insideS"] = need(lambda: inside(V) is True and top(V) == "BasescapeState", VISIT,
                                lambda: "real visit: not inside %s within %.0f s (stack %s)" % (base, VISIT, stack(V)))[1]
    time.sleep(S_VIEW)
    ev[label].update(selectedBase=gs(V).get("selectedBase"), bases=names(V))
def lever_visit(V, pb):
    q(V, {"cmd": "visit_coop_base", "base": pb})
    return need(lambda: inside(V) is True and top(V) == "BasescapeState", VISIT,
                lambda: "lever visit %s: not inside within %.0f s (stack %s)" % (pb, VISIT, stack(V)))[1]
def lever_leave(V, label):
    q(V, {"cmd": "leave_base"})
    session.wait_back_on_geoscape(V, label)
    time.sleep(1.0)
def read_view(V, s, base=None):  # base_report of PB (or `base`): G's craft and coopCraft, craft (C, T)'s crew
    rv =q(V, {"cmd": "base_report", "base": base or s.PB})
    g = guest(rv.get("soldiers"), s.name) or {}
    cr = next((c for c in rv.get("crafts") or [] if c.get("id") == s.C and c.get("type") == s.T), {})
    return {"base": rv.get("name"), "craft": g.get("craft"), "coopCraft": g.get("coopCraft"), "crew": cr.get("soldiers"), "listed": bool(g)}
def own_blob(s):
    fi = q(s.V, {"cmd": "coop_file_info", "role": "own_world"})
    b = blob_guest(s.V, fi.get("key"), s.name) if fi.get("present") else {"present": fi.get("present")}
    return {"key": fi.get("key"), "fnv": fi.get("fnv1a64"), "guest": b.get("guest", b), "coopcraft": blob_cc(b)}
def read_ok(s, n0):
    d = read_view(s.V, s)
    bh = blob_guest(s.V, "basehost", s.name)
    d.update(basehostGuest=bh.get("guest", bh), basehost=blob_cc(bh), ownBlob=own_blob(s), syncLines=sum(1 for ln in log(s.V)[n0:] if SYNC in ln))
    return d
def geo_real(s, label):
    must(s.V, "GEOSCAPE", 10)
    session.wait_back_on_geoscape(s.V, label)
    time.sleep(S_GEO)
def seat(x, s):
    """SEAT (levers): the first time pick + transfer G; a visit, craft_assign, SOLDIERS' OK, leave, a CONFIRM visit (crewPre), leave, own"""
    V, d = s.V, {}
    if s.name is None:
        rb = session._campaign_own_roster_base(V)
        s.VB, s.PB = rb["name"], session._campaign_own_roster_base(x.host)["name"]
        s.name = next(z for z in rb["soldiers"] if not z.get("craft"))["name"]
        tr = q(V, {"cmd": "transfer_to_coop_base", "name": s.name, "toBase": s.PB})
        d["transfer"] = [s.name, s.VB, s.PB, tr.get("transferred")]
        if not tr.get("transferred"):
            raise Stop("transfer %s: %s" % (s.name, tr))
        nt, tn = wait(lambda: q(x.host, {"cmd": "coop_dialog_info"}).get("code") == 150, NOTICE_S, 0.02)
        d["notice"] = [bool(nt), tn]
        if not nt:
            raise Stop("transfer %s: no host items-received notice (CoopState 150) within %.0f s (stack %s)" % (s.name, NOTICE_S, stack(x.host)))
        session.drain_host_coop_notice(x.host)
    d["visitS"] = lever_visit(V, s.PB)
    rep, t = need(lambda: (lambda r: r if guest(r.get("soldiers"), s.name) else None)(q(V, {"cmd": "base_report", "coop": True})), GUEST_S,
                  lambda: "guest %s not listed at %s within %.0f s" % (s.name, s.PB, GUEST_S))
    if s.C is None:
        k = next((c for c in rep.get("crafts") or [] if "SKYRANGER" in (c.get("type") or "")), None)
        if not k:
            raise Stop("no SKYRANGER at %s: %s" % (s.PB, [[c.get("id"), c.get("type")] for c in rep.get("crafts") or []]))
        s.C, s.T = k["id"], k["type"]
    g = guest(rep["soldiers"], s.name)
    sa = q(V, {"cmd": "craft_assign", "soldier_id": g["id"], "craft_id": s.C, "coop": True, "on": True})
    d.update(guestS=t, viewId=g["id"], before=[g.get("craft"), g.get("coopCraft")], seated=sa.get("seated"), C=[s.C, s.T])
    q(V, {"cmd": "open_soldiers", "base": s.PB})
    need_top(V, "SoldiersState", 30, "open_soldiers")
    q(V, {"cmd": "soldiers_ok"})
    need_top(V, "BasescapeState", 30, "soldiers_ok")
    d["lever"] = read_view(V, s)
    lever_leave(V, "seat leave")
    lever_visit(V, s.PB)
    time.sleep(S_VIEW)
    d["confirm"] = read_view(V, s)
    s.crewPre = d["confirm"]["crew"]
    lever_leave(V, "seat leave 2")
    d["own"] = read_view(V, s, s.VB)
    return d
def seat_ok(d, s): return d.get("seated") is True and d["confirm"]["craft"] == s.C and d["own"]["coopCraft"] == s.C and (s.crewPre or 0) >= 1
def build2(x):
    """BUILD2 (lever): HostBase2 at the first ok offset; 1.0 s; the host's real GEOSCAPE off its new base; drain; HostBase2 on the client"""
    H, V = x.host, x.client
    b0 = session._campaign_base0(H)
    tries, res = [], {}
    for dlon, dlat in OFFSETS:
        res = q(H, {"cmd": "build_new_base", "lon": b0["lon"] + dlon, "lat": b0["lat"] + dlat, "name": B2})
        if not res.get("ok") and "money" in (res.get("error") or "") and res.get("cost"):
            tries.append([dlon, dlat, "set_funds", q(H, {"cmd": "set_funds", "value": 2 * res["cost"]}).get("ok")])
            res = q(H, {"cmd": "build_new_base", "lon": b0["lon"] + dlon, "lat": b0["lat"] + dlat, "name": B2})
        tries.append([dlon, dlat, res.get("ok"), res.get("error"), res.get("cost")])
        if res.get("ok"):
            break
    if not res.get("ok"):
        raise Stop("BUILD2: no offset built %s: %s" % (B2, tries))
    time.sleep(1.0)
    t1 = stack(H)
    if t1[-1:] == ["BasescapeState"]:
        must(H, "GEOSCAPE", 10)
    v, tg = wait(lambda: top(H) == "GeoscapeState", POP)
    dr = geo.drain_popups(H)
    m, tm = wait(lambda: B2 in names(V), MARK, 0.5)
    d = {"tries": tries, "hostAfterLever": t1, "hostGeoS": tg, "drained": dr, "markS": tm, "hostStack": stack(H), "clientBases": names(V)}
    if not v or not m:
        raise Stop("BUILD2: host GeoscapeState %s, client marker %s (%s)" % (bool(v), bool(m), d))
    return d
def setup(x):
    """SETUP: SEAT; the host's quick save (lever) + BLOB; BUILD2; AFF-client"""
    s, V = x.s, x.client
    d = seat(x, s)
    fi0 = q(V, {"cmd": "coop_file_info", "role": "own_world"})
    sv = q(x.host, {"cmd": "save_game_ui", "type": "quick"})
    def blob_has_g():  # the own-world fnv changed AND its blob lists G with coopcraft C
        fi = q(V, {"cmd": "coop_file_info", "role": "own_world"})
        b = own_blob(s) if fi.get("present") and fi.get("fnv1a64") != fi0.get("fnv1a64") else None
        return b if b and b["coopcraft"] == s.C else None
    b, tb = wait(blob_has_g, BLOB, 0.5)
    tops, tt = wait(lambda: top(x.host) == "GeoscapeState" and top(V) == "GeoscapeState", 20, 0.25)
    geo.drain_popups(x.host)
    d["blob"] = b or own_blob(s)
    d["save"] = {"ok": sv.get("ok"), "err": sv.get("error"), "before": [fi0.get("key"), fi0.get("fnv1a64")], "s": tb, "topsS": tt}
    if not b or not tops:
        raise Stop("quick save: blob %s in %s s, tops %s / %s" % (d["blob"], tb, stack(x.host), stack(V)))
    d["build2"] = build2(x)
    s.sc = d["aff"] = aff(V)
    return d
# ----- rows -----
class Row:
    def __init__(self, rid, x):
        self.rid, self.cells, self.ev, self.done, self.x = rid, CELLS[rid], {}, {}, x
    def cell(self, name, ok, detail):
        self.done[name] = bool(ok)
        RESULTS.append((name, bool(ok)))
        print("%s %s: %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    def capture(self, why):
        d, s = {"why": why}, self.x.s
        for n in ("host", "client"):
            gc = getattr(self.x, n)
            if not alive(gc):
                d[n] = {"alive": False, "log": tail(gc)}
                continue
            g, fi = gs(gc), q(gc, {"cmd": "coop_file_info", "role": "own_world"})
            d[n] = {"stack": stack(gc), "coop": coop(gc), "selectedBase": g.get("selectedBase"), "bases": [b.get("name") for b in g.get("bases") or []],
                    "ownWorld": [fi.get("key"), fi.get("fnv1a64")], "pb": brief(q(gc, {"cmd": "base_report", "base": s.PB})) if s.PB else None,
                    "log": tail(gc)}
        print("CAPTURE %s: %s" % (self.rid, js(d)), flush=True)
    def close(self, why):
        for n in self.cells:
            if n not in self.done:
                self.cell(n, False, "not reached: %s" % why)
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        bad = [n for n in self.cells if not self.done.get(n)]
        print("ROW %s: %s" % (self.rid, "PASS" if not bad else "FAIL (%d failing: %s)" % (len(bad), bad)), flush=True)
def run_row(x, rid, body):
    r, s = Row(rid, x), x.s
    try:
        if x.boot_err or x.setup is None:  # a boot or SETUP miss fails every row's -pre
            r.cell(rid + "-pre", False, "boot: %s" % x.boot_err if x.boot_err else "SETUP: %s" % x.setup_err)
            raise Stop("boot" if x.boot_err else rid + "-pre")
        r.ev["n0"] = n0 = len(log(s.V))
        body(x, r, s, n0)
        r.close("")
    except Exception as e:  # noqa: BLE001 - a precondition / exit miss ends the row
        r.ev["stop"] = short(e, 500)
        if str(e) != "boot":
            r.capture(short(e))
        r.close(short(e))
def read_cells(r, s, n0, ok_blob=False, blob_cell=False):
    """READ-VIEW; OKS (real SOLDIERS, real OK); READ-OK; GEO; READ-OWN - with the row's -view / -ok (/ -blob) / -own cells"""
    V, rid = s.V, r.rid
    rv = r.ev["view"] = read_view(V, s)
    r.cell(rid + "-view", rv["craft"] == s.C and rv["crew"] == s.crewPre, "%s in the view at %s: craft %s, craft (%s, %s) crew %s; coopCraft %s "
           "(want craft %s, crew %s = crewPre)" % (s.name, s.PB, rv["craft"], s.C, s.T, rv["crew"], rv["coopCraft"], s.C, s.crewPre))
    r.ev["oksS"] = [press_to(V, "SOLDIERS", "SoldiersState", POP, S_SOLD), press_to(V, "OK", "BasescapeState", POP, S_OK)]
    ro = r.ev["ok"] = read_ok(s, n0)
    b = ro["ownBlob"]
    okv = ro["coopCraft"] == s.C and ro["basehost"] == s.C and (b["coopcraft"] == s.C or not ok_blob)
    r.cell(rid + "-ok", okv, "after SOLDIERS' OK: view coopCraft %s, \"basehost\" coopcraft %s%s (want %s); synced lines since the row %d"
           % (ro["coopCraft"], ro["basehost"], ", own-world blob coopcraft %s" % b["coopcraft"] if ok_blob else "", s.C, ro["syncLines"]))
    if blob_cell:
        r.cell(rid + "-blob", b["coopcraft"] == s.C, "own-world blob %s fnv %s: %s coopcraft %s; synced lines since the row %d (want %s)"
               % (b["key"], b["fnv"], s.name, b["coopcraft"], ro["syncLines"], s.C))
    geo_real(s, rid + " GEOSCAPE")
    ow = r.ev["own"] = read_view(V, s, s.VB)
    r.cell(rid + "-own", ow["coopCraft"] == s.C, "own world %s: %s coopCraft %s (want %s)" % (ow["base"], s.name, ow["coopCraft"], s.C))
def body_r2c(x, r, s, n0):
    d = r.ev["setup"] = x.setup
    visit_real(s, r.ev, s.PB, "visit")
    sel, bc, mk = r.ev["visit"]["selectedBase"], d["blob"]["coopcraft"], B2 in d["build2"]["clientBases"]
    ok = seat_ok(d, s) and bc == s.C and mk and sel == s.PB and inside(s.V) is True
    r.cell("R2c-pre", ok, "SEAT %s at %s: seated %s, confirm craft %s, crewPre %s, own %s; blob %s; %s on the client %s; view selectedBase %s (want "
           "true, %s, >= 1, %s; %s; true; %s)" % (s.name, s.PB, d.get("seated"), d["confirm"]["craft"], s.crewPre, d["own"]["coopCraft"], bc, B2, mk,
                                                 sel, s.C, s.C, s.C, s.PB))
    if not ok:
        raise Stop("R2c-pre")
    read_cells(r, s, n0, ok_blob=True)
def view_of_b2(s, r):
    """VISIT(PB2); IDX = PB's index in the view's geo_state bases"""
    visit_real(s, r.ev, B2, "visit2")
    vb, sel = r.ev["visit2"]["bases"], r.ev["visit2"]["selectedBase"]
    idx = r.ev["idx"] = vb.index(s.PB) if s.PB in vb else None
    r.ev["pbBeforeKey"] = read_view(s.V, s)
    return inside(s.V) is True and top(s.V) == "BasescapeState" and sel == B2 and idx is not None and idx <= 7, vb, sel, idx
def body_r2(x, r, s, n0):
    V = s.V
    ok, vb, sel, idx = view_of_b2(s, r)
    r.cell("R2-pre", ok, "inside the view of %s: selectedBase %s, bases %s, %s at IDX %s (want %s, IDX <= 7)" % (B2, sel, vb, s.PB, idx, B2))
    if not ok:
        raise Stop("R2-pre")
    q(V, {"cmd": "inject_input", "kind": "key", "key": 49 + idx})
    v, t = wait(lambda: gs(V).get("selectedBase") == s.PB, SW, 0.05)
    sw = r.ev["switch"] = {"key": 49 + idx, "s": t, "selectedBase": gs(V).get("selectedBase"), "top": top(V), "inside": inside(V), "bases": names(V)}
    ok = bool(v) and sw["top"] == "BasescapeState" and sw["inside"] is True
    r.cell("R2-exit", ok, "real key %d: selectedBase %s in %s s, top %s, insideCoopBase %s, bases %s (want %s, BasescapeState, true)"
           % (49 + idx, sw["selectedBase"], t, sw["top"], sw["inside"], sw["bases"], s.PB))
    if not ok:
        raise Stop("R2-exit")
    read_cells(r, s, n0, blob_cell=True)
    visit_real(s, r.ev, s.PB, "visitNext")
    rv = r.ev["next"] = read_view(V, s)
    r.cell("R2-next", rv["craft"] == s.C and rv["crew"] == s.crewPre, "next visit of %s: %s craft %s, craft (%s, %s) crew %s; coopCraft %s "
           "(want craft %s, crew %s)" % (s.PB, s.name, rv["craft"], s.C, s.T, rv["crew"], rv["coopCraft"], s.C, s.crewPre))
    geo_real(s, "R2 next GEOSCAPE")
def body_r2i(x, r, s, n0):
    V = s.V
    try:
        d = r.ev["seat"] = seat(x, s)
    except Exception as e:  # noqa: BLE001 - a SEAT miss is the row's -pre
        r.cell("R2i-pre", False, "SEAT: %s" % short(e))
        raise Stop("R2i-pre: " + short(e))
    ok, vb, sel, idx = view_of_b2(s, r)
    ok = ok and seat_ok(d, s)
    r.cell("R2i-pre", ok, "SEAT %s: seated %s (before %s), confirm craft %s, crewPre %s, own %s; the view of %s: selectedBase %s, bases %s, %s at IDX "
           "%s (want true, %s, >= 1, %s; %s, IDX <= 7)" % (s.name, d.get("seated"), d.get("before"), d["confirm"]["craft"], s.crewPre,
                                                         d["own"]["coopCraft"], B2, sel, vb, s.PB, idx, s.C, s.C, B2))
    if not ok:
        raise Stop("R2i-pre")
    tb = press_to(V, "BASE INFORMATION", "BaseInfoState", BI, S_BI)
    q(V, {"cmd": "inject_input", "kind": "key", "key": 49 + idx})
    k, tk = wait(lambda: gs(V).get("selectedBase") == s.PB, SW, 0.05)
    bis = r.ev["bis"] = {"biS": tb, "key": 49 + idx, "keyS": tk, "selectedBase": gs(V).get("selectedBase"), "top": top(V), "bases": names(V)}
    must(V, "OK", 10)
    o, to = wait(lambda: top(V) == "BasescapeState", POP, 0.05)
    time.sleep(S_BIOK)
    bis.update(okS=to, afterOk=[top(V), gs(V).get("selectedBase"), inside(V)])
    ok = bool(k) and bis["top"] == "BaseInfoState" and bool(o) and bis["afterOk"] == ["BasescapeState", s.PB, True]
    r.cell("R2i-exit", ok, "BASE INFORMATION in %s s; real key %d: selectedBase %s in %s s on %s, bases %s; its real OK: [top, selectedBase, inside] "
           "%s in %s s (want %s on BaseInfoState; [BasescapeState, %s, true])" % (tb, 49 + idx, bis["selectedBase"], tk, bis["top"], bis["bases"],
                                                                                 bis["afterOk"], to, s.PB, s.PB))
    if not ok:
        raise Stop("R2i-exit")
    read_cells(r, s, n0)
# ----- boot / run -----
def boot(x):
    x.host = GameClient("host", None, make_user_dir(TAG + "_host"))
    x.client = x.s.V = GameClient("client", None, make_user_dir(TAG + "_client"))
    x.host.spawn(), x.client.spawn(), x.host.connect(), x.client.connect()
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
    print("==== W2-H85 S-B VBS (slot %s, key %s, exe %s) CPU %s ====" % (harness.HARNESS_SLOT, KEY, time.ctime(os.path.getmtime(harness.EXE)), c0), flush=True)
    x = SimpleNamespace(host=None, client=None, cr0=crashes(), boot_err=None, setup_err=None, setup=None)
    x.s = SimpleNamespace(V=None, VB=None, PB=None, name=None, C=None, T=None, crewPre=None, sc=None)
    try:
        boot(x)
    except Exception as e:  # noqa: BLE001 - a boot miss fails every row's -pre
        x.boot_err = short(e, 300)
        print("BOOT MISS: %s" % x.boot_err, flush=True)
    if not x.boot_err:
        try:
            x.setup = setup(x)
        except Exception as e:  # noqa: BLE001 - a SETUP miss fails every row's -pre
            x.setup_err = short(e, 300)
            print("SETUP MISS: %s" % x.setup_err, flush=True)
    run_row(x, "R2c", body_r2c)
    run_row(x, "R2", body_r2)
    run_row(x, "R2i", body_r2i)
    r = Row("CRASH", x)
    al, rc = [alive(x.host), alive(x.client)], [shut(x.client), shut(x.host)]
    nc = sorted(crashes() - x.cr0)
    r.ev.update(alive=al, rc=rc, newCrash=nc)
    r.cell("CRASH", al == [True, True] and all(c in RC_OK for c in rc) and not nc, "host / client alive before shutdown %s; shutdown rc client %s "
           "host %s; new crash files %s (want [true, true], in %s, none)" % (al, rc[0], rc[1], nc, list(RC_OK)))
    r.close("")
    fails = [n for n, ok in RESULTS if not ok]
    print("SUMMARY pass=%d fail=%d" % (len(RESULTS) - len(fails), len(fails)), flush=True)
    print("==== W2-H85 S-B VBS: %d/%d cells PASS, wall %.1f s, CPU %s -> %s ====" % (len(RESULTS) - len(fails), len(RESULTS), now(), c0, cpu()), flush=True)
    if fails:
        print("FAILING: %s" % fails, flush=True)
    return x, (0 if not fails else 2)

if __name__ == "__main__":
    sys.exit(run_all()[1])
