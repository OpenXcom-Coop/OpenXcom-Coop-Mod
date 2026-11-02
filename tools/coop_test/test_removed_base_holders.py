"""A destination confirm that holds a partner base the partner removes closes first, as its CANCEL does.
In the one shared SEPARATE world the partner's bases are real bases of the host's world. When the host dismantles one,
the client erases it while its own craft's ConfirmDestinationState may still hold it as the target; without the fix
the popup stays on top over a freed pointer. The fix (coopCloseMirrorHolders) closes those popups right before the
erase. Probe popup_mirror_check (PMC, read-only pointer compares on the client): holders = states holding a target,
dangling = those holding one in no live list.
Two other holders of a partner base cannot open in a SEPARATE campaign: a globe click on a partner base opens its
Basescape directly, never a target list (GeoscapeState::openGlobeTargets), and the partner's crafts in flight are not
drawn on the client's globe (Globe::isCraftFlightVisible). The Basescape of a removed partner base is covered by
test_removed_base_views, the crafts of a destroyed base held by an open list by test_removed_base_holders_shared.
ONE boot (key KEY, dirs removed_base_holders_*, campaign_mode "coop"): spawn + connect; session.new_campaign;
geo_set_speed idx 0 both; the window mapping per machine (real INTERCEPT + CANCEL); the host's build_new_base HostBase3
at BASE3_POS + real GEOSCAPE, then HostBase3 in partner(client). HB = the host's first base.
  Row destination_confirm
          client real INTERCEPT, the first READY STR_INTERCEPTOR row -> SelectDestinationState, a real globe
          click on HostBase3 -> ConfirmDestinationState on HostBase3; P0; the host dismantles HostBase3 (real BASES,
          the key of its index, the BaseView lift cell, DismantleFacilityState OK) + real GEOSCAPE; DEL_SETTLE; P1.
  Cells: destination_confirm-pre (GUARD) the popup on the client's top holding HostBase3 (P0: holders 1, dangling 0);
          the host's delete step reached (HostBase3 gone from own(host) after the DismantleFacilityState OK).
          destination_confirm-dangle (FIX) P1 dangling 0.  destination_confirm-closed (FIX) P1 no
          ConfirmDestinationState on the stack, top SelectDestinationState, holders 0.
  END     CRASH (GUARD): no new crash file in the lane's crash folder since the file start; both processes alive until
          their shutdown.
Without the fix: the -dangle and -closed cells FAIL (2 of 4); every other cell PASS. With the fix: all 4 PASS.
P0 = the client's stack and PMC right before the host's delete; P1 = the last read of the DEL_SETTLE watch after it.
partner(gc) = geo_state bases with coopBase true (the partner's); own(gc) = coopIcon and coopBase false. Every press is
a real click_widget or inject_input except the logged test commands build_new_base, geo_set_speed and globe_point's
centre (staging: the player turns the globe). One EVIDENCE line per row, one PASS / FAIL line per cell, then the row
verdict; a precondition miss ends its row (CAPTURE line, later cells "not reached") and the file goes on; a boot miss
fails destination_confirm-pre with ONE CAPTURE line. ONE foreground run, no skip; exit 0 only when every cell passes,
else 2.
Run: python tools/coop_test/test_removed_base_holders.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402

KEY = "49559"                               # lobby key (unused by every other test file)
BASE3_POS = (LAND_LON + 0.06, LAND_LAT + 0.03)     # HostBase3: on land
LIFT = (80, 80)                             # build_new_base's lift (2, 2), BaseView GRID 32: its centre
KEY_1, SYM_PLUS, SYM_MINUS, ZOOM_MIN = 49, 43, 45, 3
DEL_SETTLE, BOOT_S = 3.0, 60.0
NEEDLE = "[coop] removed base: id=%s cache="
LOGN = ("[coop] removed base: ", "coopCloseMirrorHolders", "[coop-session]", "coop-ui] push", "coop-ui] pop")
ROWS = (("destination_confirm",
         ("destination_confirm-pre", "destination_confirm-dangle", "destination_confirm-closed")),
        ("END", ("CRASH",)))
FIX = ("destination_confirm-dangle", "destination_confirm-closed")
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
def pmc(gc):
    r = q(gc, {"cmd": "popup_mirror_check"})
    return {k: r.get(k) for k in ("holders", "dangling", "mirror", "queued", "queuedDangling", "error") if k in r}
def pmc2(p): return [p.get("holders"), p.get("dangling")]
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
def partner(c): return [b for b in c["bases"] if b[3]]
def partner_ids(c): return [b[0] for b in partner(c)]
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
    """the harness base-build test command (BuildNewBaseState -> ConfirmNewBaseState -> BaseNameState ->
    PlaceLiftState, real states), then a real GEOSCAPE from the new base's BasescapeState"""
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
def view_names(c):
    """the base strip's order (MiniBaseView): the machine's own bases first, then the partner's"""
    return [b[1] for b in c["bases"] if not b[3]] + [b[1] for b in c["bases"] if b[3]]
def dismantle(gc, sc, name):
    """real BASES (the key of `name`'s slot in the base strip if another base shows), the BaseView lift cell,
    DismantleFacilityState, its real OK; then own(gc) (the delete step reached)"""
    must_click(gc, "BASES", 10)
    wait_top(gc, "BasescapeState", 10)
    c = census(gc)
    rec = {"selected": c["selected"], "key": None, "view": view_names(c)}
    if rec["selected"] != name:
        if name not in rec["view"]:
            raise Stop("%s base view list %s lacks %r" % (gc.name, rec["view"], name))
        rec["key"] = KEY_1 + rec["view"].index(name)
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
        e = [p1["stack"][-3:], pmc2(p1["pmc"])]
        if e != last:
            trace.append([round(time.time() - t0, 2)] + e)
            last = e
        time.sleep(0.05)
    return trace, p1
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
        self.host = GameClient("host", None, make_user_dir("removed_base_holders_host"))
        self.client = GameClient("client", None, make_user_dir("removed_base_holders_client"))
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
    if not (h["stack"] == ["GeoscapeState"] and c["stack"] == ["GeoscapeState"] and len(own(h)) == 1 and len(own(c)) == 1 and len(partner(c)) == 1):
        raise Stop("boot: stacks %s / %s, host own %s, client own %s, client partner bases %s" % (h["stack"], c["stack"], own(h), own(c), partner(c)))
    hb = own(h)[0]
    st["HB"] = {"id": partner_ids(c)[0], "name": hb[1], "pos": (hb[4], hb[5])}
    st["builds"] = {"HostBase3": [build_base2(b.host, "HostBase3", BASE3_POS), other_has(b.client, "HostBase3")]}
    time.sleep(1.0)
    m = {x[1]: x[0] for x in partner(census(b.client))}
    if "HostBase3" not in m:
        raise Stop("HostBase3 not in partner(client): %s" % m)
    st["ids"] = m
def row_destination_confirm(b, r, st):
    h, c, ev = b.host, b.client, r.ev
    cc = census(c)
    ev["ids"], ev["boot"] = st["ids"], st.get("boot")
    hb3 = next((m for m in partner(cc) if m[1] == "HostBase3"), None)
    r.need(hb3 and cc["stack"] == ["GeoscapeState"], "destination_confirm: client %s, HostBase3 %s"
           % (cc["stack"], hb3))
    globe(c, centerLon=hb3[4], centerLat=hb3[5])
    ev["zooms"] = zoom_to(c, ZOOM_MIN)
    must_click(c, "INTERCEPT", 10)
    wait_top(c, "InterceptState", 5)
    session.wait_widget_ready(c, "CANCEL")
    rows = q(c, {"cmd": "intercept_list"}).get("rows", [])
    idx = next((i for i, x in enumerate(rows) if x.get("type") == "STR_INTERCEPTOR" and x.get("status") == "STR_READY"), None)
    tl = [w for w in q(c, {"cmd": "list_widgets"}).get("widgets", []) if (w.get("type") or "").endswith("::TextList")]
    ev["rows"], ev["idx"] = [[x.get("craft"), x.get("status")] for x in rows], idx
    r.need(idx is not None and len(tl) == 1, "destination_confirm: no READY interceptor row %s or TextLists %d"
           % (ev["rows"], len(tl)))
    inject(c, b.sc["client"], tl[0]["x"] + 30, tl[0]["y"] + 8 * idx + 4)
    r.need(wait(lambda: top(c) == "SelectDestinationState", 5)[0], "destination_confirm: no SelectDestinationState "
           "after the row click: %s" % stk(c))
    ev["click"] = globe_click(c, b.sc["client"], hb3[4], hb3[5], "SelectDestinationState", pick="HostBase3")
    time.sleep(0.3)
    p0 = ev["P0"] = {"stack": stk(c), "pmc": pmc(c), "texts": texts(c)[:6]}
    r.need(p0["stack"][-2:] == ["SelectDestinationState", "ConfirmDestinationState"] and "TARGET: HostBase3" in p0["texts"] and
           pmc2(p0["pmc"]) == [1, 0], "destination_confirm P0: client %s %s, PMC %s (want ConfirmDestinationState "
           "on HostBase3, PMC holders 1, dangling 0)" % (p0["stack"], p0["texts"], pmc2(p0["pmc"])))
    mark = len(logl(c))
    d = ev["dismantle"] = dismantle(h, b.sc["host"], "HostBase3")
    r.need("HostBase3" not in d["ownAfterOk"], "the host's own still holds HostBase3 after its OK: %s" % d["ownAfterOk"])
    must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState", 15)
    ev["settle"], p1 = settle(c, DEL_SETTLE)
    ev["P1"], ev["line"] = p1, hits(c, NEEDLE % st["ids"]["HostBase3"], mark)
    r.cell("destination_confirm-pre", True, "client %s %s, PMC %s; the host's OK reached (own after %s)"
           % (p0["stack"], p0["texts"][-1:], pmc2(p0["pmc"]), d["ownAfterOk"]))
    r.cell("destination_confirm-dangle", p1["pmc"].get("dangling") == 0,
           "P1 PMC %s (want dangling 0)" % pmc2(p1["pmc"]))
    r.cell("destination_confirm-closed", "ConfirmDestinationState" not in p1["stack"] and
           p1["stack"][-1:] == ["SelectDestinationState"] and p1["pmc"].get("holders") == 0,
           "P1 client %s, PMC holders %s (want no ConfirmDestinationState, top SelectDestinationState, holders 0)"
           % (p1["stack"], p1["pmc"].get("holders")))
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
        except Exception as e:  # noqa: BLE001 - a boot miss fails destination_confirm-pre with ONE CAPTURE line
            r = Row(x, b, "destination_confirm")
            r.ev["boot"] = st.get("boot")
            r.finish("boot miss: %s: %s" % (type(e).__name__, str(e)[:300]))
        else:
            run_row(x, b, "destination_confirm", row_destination_confirm, st)
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
    print("SUMMARY test_removed_base_holders: %d/%d cells pass; failing %s; wall %.1f s"
          % (len(cl) - len(set(x.fails)), len(cl), sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
