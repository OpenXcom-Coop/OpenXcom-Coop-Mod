"""W2-H83 S-C RBHS (tools/coop_test/test_w2_removed_base_holders_shared.py): in SHARED co-op the INTERCEPT list that shows a base's crafts
closes, as its Cancel does, when the aliens destroy that base and the host presses OK on its base-destroyed message (ruling R-LT18-1,
R-LBH3-1, QH83-14 (a), veto line VL-H83-3 reworded; leads-triage18 F22661 / F22666).
Spec docs rewrite/prompts/w2h83_removed_base_views.md (common) + rewrite/prompts/w2h83_sc_holders.md, R-LT18-1 AMENDMENT Z8; TASK 0 values in
rewrite/w2h83-task0/sc/CONSTANTS.md. Today the client's baseDestroyedApply deletes the base and its crafts under the open InterceptState (its
rows hold those crafts) and pushes the "undefended base" message over it. The green (EC2-EC12: coopCloseMirrorHolders before the erase, reading
GeoscapeState::coopHeldCrafts) closes the list first, so the message opens over the globe.
ONE SHARED boot (key KEY, dirs w2h83_hs_*, campaign_mode "shared"); row SI, then END.
  1 spawn + connect; session.new_campaign; geo_set_speed idx 0 both; the window mapping per machine (real INTERCEPT + CANCEL); HB = the one
    base, same name on both.  2 SPARE: the host's build_new_base at P_SPARE (land, >= 0.15 rad from HB) + real GEOSCAPE; on both (set_funds on
    BOTH machines only if the funds miss the base: a host-only value is a SHARED funds desync, F22842).  3 STRIP: the host's get_soldiers HB
    ids; set_soldier_dead each on the client, then the host; HB 0 soldiers on both.  4 client real INTERCEPT -> InterceptState; its
    intercept_list rows list >= 1 HB craft; P0.  5 SI-mark; host spawn_ufo; trigger_base_defense -> BaseDestroyedState within W_BDS (no
    BriefingState).  6 host real OK (then real presses to GeoscapeState).  7 poll the client every 0.05 s for DEL_SETTLE until HB leaves its
    list; P1 = its stack.  8 client real OK on ErrorMessageState; W_OK; P2.  9 red recovery: InterceptState on top -> its real CANCEL.
  SI-pre (GUARD) HB and SPARE on both; STRIP every reply ok + dead, HB 0 soldiers on both; P0 top InterceptState over GeoscapeState, HB crafts
         listed; the trigger names HB; BaseDestroyedState on the host within W_BDS, no BriefingState; the host's OK reached GeoscapeState.
  SI-gone (GUARD) within DEL_SETTLE HB gone from both lists, SPARE kept; P1's top ErrorMessageState.
  SI-closed (RED) P1: no InterceptState; the stack ends [GeoscapeState, ErrorMessageState].
  SI-top (RED) P2: no InterceptState; GeoscapeState is the top or directly under it (a notice queued meanwhile may open once the globe shows).
  END CRASH (GUARD): no new crash file in the lane's crash folder since the file start; both processes alive until their shutdown.
Red today: SI-closed, SI-top FAIL (2 of 5); every other cell PASS. Green (EC2-EC12): all 5 PASS.
Every press is a real click_widget or inject_input except the logged levers build_new_base, geo_set_speed, set_funds (only if needed),
set_soldier_dead, spawn_ufo and trigger_base_defense; read-only probes geo_state, get_soldiers, intercept_list, get_state. One EVIDENCE line per
row, one PASS / FAIL line per cell, then the row verdict; a precondition miss ends its row (CAPTURE line, later cells "not reached"); a boot miss
fails SI-pre with ONE CAPTURE line. WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_w2_removed_base_holders_shared.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, math, os, subprocess, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49631"                               # lobby key (CONSTANTS.md; 0 hits in src + tools at 60f182398)
SPARE = "SPARE"
W_BDS, DEL_SETTLE, W_OK, BOOT_S = 2.0, 3.0, 2.0, 60.0
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID",
       "trajectory": "P0", "state": "flying"}
LOGN = ("[coop] W2-H83", "[coop] W2-H81", "[coop-session]", "coop-ui] push", "coop-ui] pop", "shared_resync")
ROWS = (("SI", ("SI-pre", "SI-gone", "SI-closed", "SI-top")), ("END", ("CRASH",)))
RED = ("SI-closed", "SI-top")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]


class Stop(Exception):  # a precondition missed: the row ends here
    pass


# ----- probes and real input (copied from docs rewrite/lbh3-cap/cap.py, test_w2_removed_base_windows.py, test_w2_lost_base_undefended.py) -----
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
def census(gc):
    g = q(gc, {"cmd": "geo_state"})
    return {"t": now(), "bases": [[b.get("coopBaseId"), b.get("name"), round(b.get("lon") or 0, 4), round(b.get("lat") or 0, 4)]
                                  for b in g.get("bases", [])], "stack": stk(gc), "funds": g.get("funds"), "error": g.get("error")}
def names(c): return [b[1] for b in c["bases"]]
def cpu():
    ps = ("[math]::Round(((Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 2).CounterSamples | "
          "Measure-Object -Property CookedValue -Average).Average, 1); @(Get-Process | Where-Object { $_.ProcessName -like 'Wardogs*' }).Count")
    try:
        v = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout.split()
        return {"t": time.strftime("%H:%M:%S"), "cpu": v[0] if v else None, "wardogs": v[1] if len(v) > 1 else None}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)[:120]}
def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def lines_since(gc, n0): return [ln.split("\t")[0][-13:-1] + " " + ln.split("\t")[-1][:200] for ln in logl(gc)[n0:] if any(n in ln for n in LOGN)]
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
def scale(gc):
    """INTERCEPT -> CANCEL (real clicks, setup; the same window mapping the other W2-H83 files measure)"""
    a = cw(gc, "INTERCEPT")
    wait(lambda: top(gc) == "InterceptState", 5)
    session.wait_widget_ready(gc, "CANCEL")
    b = cw(gc, "CANCEL")
    if not wait(lambda: top(gc) == "GeoscapeState", 5)[0] and top(gc) == "InterceptState":
        real_click(gc, "CANCEL", 5)
        wait(lambda: top(gc) == "GeoscapeState", 5)
    return [a, b]
def globe(gc, **kw): return q(gc, dict({"cmd": "globe_point"}, **kw))
def dist(a, b): return math.hypot((a[0] - b[0] + math.pi) % (2 * math.pi) - math.pi, a[1] - b[1])
def pick_point(gc, avoid):
    """P_SPARE (LBU): land >= 0.15 rad from every base; rings 0.20-0.50 rad around the first base, 16 directions; 8 neighbours land"""
    c0 = avoid[0]
    for r in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
        for k in range(16):
            p = (c0[0] + r * math.cos(2 * math.pi * k / 16), c0[1] + r * math.sin(2 * math.pi * k / 16))
            if any(dist(p, b) < 0.15 for b in avoid):
                continue
            pr = globe(gc, lon=p[0], lat=p[1])
            if not pr.get("land"):
                continue
            nb = [globe(gc, lon=p[0] + dx, lat=p[1] + dy).get("land") for dx in (-0.02, 0, 0.02) for dy in (-0.02, 0, 0.02)]
            if all(nb) and 10 < pr["x"] < pr["globeW"] - 10 and 30 < pr["y"] < pr["globeH"] - 10:
                return {"lon": p[0], "lat": p[1], "r": r, "k": k}
    return None
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
            "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-40:]]}
    return out
# ----- the boot and the row -----
class Boot:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("w2h83_hs_host"))
        self.client = GameClient("client", None, make_user_dir("w2h83_hs_client"))
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
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "RED" if cid in RED else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop and capture_it and self.b is not None:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails
def row_si(b, r):
    h, c, ev = b.host, b.client, r.ev
    for gc in (h, c):
        gc.spawn()
    for gc in (h, c):
        gc.connect(timeout=BOOT_S)
    session.new_campaign(h, c, port=KEY, campaign_mode="shared")
    for gc in (h, c):
        wait_top(gc, "GeoscapeState", 60)
        q(gc, {"cmd": "geo_set_speed", "idx": 0})
    time.sleep(2.0)
    ev["scale"] = {"host": scale(h), "client": scale(c)}
    p = {"host": census(h), "client": census(c)}
    ev["boot"] = {"host": p["host"]["bases"], "client": p["client"]["bases"], "stacks": [p["host"]["stack"], p["client"]["stack"]],
                  "funds": [p["host"]["funds"], p["client"]["funds"]]}
    r.need(p["host"]["stack"] == ["GeoscapeState"] and p["client"]["stack"] == ["GeoscapeState"] and len(names(p["host"])) == 1 and
           names(p["host"]) == names(p["client"]), "boot: host %s %s, client %s %s" % (names(p["host"]), p["host"]["stack"], names(p["client"]),
                                                                                        p["client"]["stack"]))
    hb = p["host"]["bases"][0]
    ev["HB"] = hb[:2]
    pk = ev["pick"] = pick_point(h, [(hb[2], hb[3])])
    r.need(pk, "SPARE: no land point for P_SPARE")
    if (p["host"]["funds"] or 0) < 1000000:  # S54 / F22842: never a host-only SHARED funds value; both machines only when needed
        ev["setFunds"] = [q(gc, {"cmd": "set_funds", "value": 4000000}) for gc in (h, c)]
    br = q(h, {"cmd": "build_new_base", "lon": pk["lon"], "lat": pk["lat"], "name": SPARE})
    ev["build"] = br
    r.need(br.get("ok"), "build_new_base SPARE at %s -> %s" % ([pk["lon"], pk["lat"]], br))
    time.sleep(1.0)
    if top(h) == "BasescapeState":
        must_click(h, "GEOSCAPE", 10)
    wait_top(h, "GeoscapeState", 15)
    v, ev["spareS"] = wait(lambda: SPARE in names(census(c)) and SPARE in names(census(h)), 30, 0.25)
    r.need(v and top(c) == "GeoscapeState", "SPARE on both: %s, client %s" % (v, stk(c)))
    s0 = q(h, {"cmd": "get_soldiers"})
    hb0 = [x for x in s0.get("bases", []) if x.get("name") == hb[1]]
    sids = [s.get("id") for s in (hb0[0].get("soldiers", []) if len(hb0) == 1 else [])]
    rep = {gc.name: [[sid, (lambda y: [y.get("ok"), y.get("dead")])(q(gc, {"cmd": "set_soldier_dead", "soldierId": sid}))] for sid in sids]
           for gc in (c, h)}
    after = {gc.name: [len(x.get("soldiers", [])) for x in q(gc, {"cmd": "get_soldiers"}).get("bases", []) if x.get("name") == hb[1]]
             for gc in (c, h)}
    ev["strip"] = {"ids": sids, "replies": rep, "after": after}
    r.need(sids and all(y[1] == [True, True] for v2 in rep.values() for y in v2) and after == {"client": [0], "host": [0]},
           "STRIP: %s" % ev["strip"])
    must_click(c, "INTERCEPT", 10)
    wait_top(c, "InterceptState", 5)
    session.wait_widget_ready(c, "CANCEL")
    rows = q(c, {"cmd": "intercept_list"}).get("rows", [])
    p0 = ev["P0"] = {"stack": stk(c), "hbCrafts": [x.get("craft") for x in rows if x.get("base") == hb[1]], "rows": len(rows)}
    r.need(p0["stack"][-2:] == ["GeoscapeState", "InterceptState"] and p0["hbCrafts"], "P0: client %s, HB crafts %s" % (p0["stack"],
                                                                                                                       p0["hbCrafts"]))
    ufo = q(h, UFO)
    reply = q(h, {"cmd": "trigger_base_defense", "ufo_id": ufo.get("ufo_id")})
    t_trig, htr, bds = time.time(), [], None
    while time.time() - t_trig < W_BDS and bds is None:
        hs = stk(h)
        if not htr or htr[-1][1] != hs[-3:]:
            htr.append([round(time.time() - t_trig, 2), hs[-3:]])
        bds = round(time.time() - t_trig, 2) if hs[-1:] == ["BaseDestroyedState"] else None
        time.sleep(0.05)
    ev["trigger"] = {"ufo": ufo, "reply": reply, "hostTrace": htr, "bdsAt": bds, "client": stk(c)}
    r.need(reply.get("ok") and reply.get("base") == hb[1], "trigger: %s (want ok, base %r)" % (reply, hb[1]))
    r.need(bds is not None and not any("BriefingState" in x[1] for x in htr), "no BaseDestroyedState on the host within W_BDS: %s" % htr)
    session.wait_widget_ready(h, "OK", timeout=5)
    okc = ev["hostOkClick"] = real_click(h, "OK", 5)
    r.need(okc["ok"], "the host's OK on BaseDestroyedState not clicked: %s" % okc)
    t_ok, gone, p1, gone_at = okc["tc"], [], None, None
    while time.time() - t_ok < DEL_SETTLE:
        cc = census(c)
        e = [hb[1] in names(cc), cc["stack"][-4:]]
        if not gone or gone[-1][1:] != e:
            gone.append([round(time.time() - t_ok, 2)] + e)
        if not e[0]:
            gone_at, p1 = round(time.time() - t_ok, 2), cc
            break
        time.sleep(0.05)
    ev["gone"], ev["goneAt"] = gone, gone_at
    ev["hostOk"] = press_through(h)
    r.need(top(h) == "GeoscapeState", "the host not back on GeoscapeState after its OK: %s" % stk(h))
    hc = census(h)
    ev["P1"] = p1 and {"stack": p1["stack"], "bases": names(p1)}
    ev["hostAfter"] = names(hc)
    r.cell("SI-pre", True, "HB %s + SPARE on both; STRIP %d -> %s; P0 %s, HB crafts %s; BaseDestroyedState +%s s; the host's OK reached %s" % (
        hb[1], len(sids), after, p0["stack"], p0["hbCrafts"], bds, stk(h)))
    r.cell("SI-gone", p1 is not None and gone_at <= DEL_SETTLE and SPARE in names(p1) and hb[1] not in names(hc) and SPARE in names(hc) and
           p1["stack"][-1:] == ["ErrorMessageState"], "HB gone from the client at +%s s of the host's OK (trace %s); client %s, host %s" % (
               gone_at, gone, ev["P1"], names(hc)))
    r.need(p1 is not None, "HB still on the client %.0f s after the host's OK" % DEL_SETTLE)
    r.cell("SI-closed", "InterceptState" not in p1["stack"] and p1["stack"][-2:] == ["GeoscapeState", "ErrorMessageState"],
           "P1 client %s (want no InterceptState, ending [GeoscapeState, ErrorMessageState])" % p1["stack"])
    if top(c) == "ErrorMessageState":
        ev["clientOk"] = must_click(c, "OK", 5)["ok"]
    time.sleep(W_OK)
    p2 = ev["P2"] = stk(c)
    r.cell("SI-top", "InterceptState" not in p2 and "GeoscapeState" in p2[-2:], "P2 client %s (want no InterceptState, GeoscapeState the top "
           "or directly under it)" % p2)
    if top(c) == "InterceptState":  # red recovery: its CANCEL pops only
        ev["recovery"] = [real_click(c, "CANCEL", 5)["ok"], wait(lambda: top(c) == "GeoscapeState", 5)]
class X:  # the file's run state: failing cells, every process's alive-until-shutdown record
    def __init__(self): self.fails, self.alive = [], []
def main():
    x, crash0, b = X(), crashes(), None
    T0[0] = time.time()
    try:
        b = Boot()
        r = Row(x, b, "SI")
        try:
            row_si(b, r)
            r.finish()
        except Stop as e:
            r.finish(str(e))
        except Exception as e:  # noqa: BLE001 - an unexpected exception (a boot miss too) ends the row like a precondition miss
            r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
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
    print("SUMMARY W2-H83 S-C RBHS: %d/%d cells pass; failing %s; wall %.1f s" % (len(cl) - len(set(x.fails)), len(cl),
                                                                                sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
