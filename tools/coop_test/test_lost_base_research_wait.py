"""W2-H88 LBR (tools/coop_test/test_lost_base_research_wait.py): after a SEPARATE player loses its first base while it owns another,
a partner's finished research still reaches it at once (ruling R-LH87-2-1, the promise VL-H68-2 "a partner's finished research reaches
you at the next geoscape tick", veto line VL-H88-1). Spec docs rewrite/prompts/w2h88_lost_base_research_wait.md (f) + its ORCHESTRATOR
RULINGS; TASK 0 values in docs rewrite/w2h88-task0/sa/CONSTANTS.md; capture lh87-2-cap F23315-F23334 (docs rewrite/lh87-2-cap/).
Today a partner's research reaches the other player through a memory-only queue that GeoscapeState applies only while the SELECTED base is
an own base. Losing the first base (BaseDestroyedState erases it without re-pointing the index) leaves the selected index on the partner's
mirror that sat after it, so the partner's research waits: no topic, no "Research Completed", for as long as the player stays on the
geoscape. The green (E1-E4, GeoscapeState only) learns the topics at the first own base when the selected base is a partner's base; the
selected index is NOT moved.
TWO boots on key KEY (SEPARATE, Research Sync on, set_seed 1 on both), each shut down before the next:
  boot A (dirs w2h88_a_*): SETUP-A the host builds HB2 (build_new_base at B2, real GEOSCAPE), the client lists it.
    RL-3 (GUARD, RL87-2-3) the client researches T1; the host receives before any loss.
         RL3-pre: start_research ok; KNOWS(client, T1) within ADV_CAP; t0 found; T1 unknown on the host at the row start; host
         selectedBase an own base. RL3-land: LAND(host) <= W_LAND. RL3-popup: exactly 1 RCP(host, n0), at <= t0 + W_LAND.
    RL-1 (RL87-2-1) LOSS-A (the host loses HB: STRIP + spawn_ufo + trigger_base_defense, BaseDestroyedState, its real OK), then the client
         researches T2; the host receives.
         RL1-pre (GUARD): STRIP / UFO / trigger ok; BaseDestroyedState within W_BDS; host own ids == {HB2's id}; host selectedBase == the
         client's first base (the mirror: the defect's precondition); host stack [GeoscapeState]; T2 unknown on the host; KNOWS(client, T2)
         within ADV_CAP; t0 found. RL1-land (RED): LAND(host) <= W_LAND. RL1-popup (RED): exactly 1 RCP(host, n0), at <= t0 + W_LAND.
         RL1-index (GUARD): at the end of WATCH host selectedBase still the mirror and host own ids == {HB2's id} (the index is not moved).
  boot B (dirs w2h88_b_*): SETUP-B the client builds CB2 at B2, the host lists it.
    RL-2 (RL87-2-2, the client mirror image) LOSS-B (the client loses CB), then the host researches T2; the client receives.
         RL2-pre / RL2-land (RED) / RL2-popup (RED) / RL2-index as RL-1 with the roles swapped (client own ids == {CB2's id}; client
         selectedBase == the host's first base).
  END CRASH (GUARD): no new file in harness.CRASH_DIR since the file start; every process alive until its shutdown; shutdown codes in OKRC.
RL-4 (the view guard) is NOT a row: its precondition (the researcher's clock advances while the partner views its base) missed both ways
in TASK 0 (the clock stops while either player is inside a visit), so ruling R-H88-1 / QH88-4 (b) dropped it; the view hold rests on reading.
RESEARCH(r, T, drained): n0 = both logs' line counts; start_research {T, cost 1, scientists 1} on r; every 0.2 s drain `drained`, speed 4
on each machine of drained + r whose top is GeoscapeState, until KNOWS(r, T) (cap ADV_CAP); then speed 0 on the same machines. t0 = the
timestamp of r's first RCP after n0 (the researcher's ResearchCompleteState; its constructor sends the sync, so a receiver may apply a few
ms before it). WATCH(v, T) = read v every 0.5 s for W_WATCH s, draining v and the researcher after each read; LAND(v) = the first read time
with KNOWS(v, T) minus t0. KNOWS(m, T) = T in m's geo_state.discoveredResearch. RCP(m, n0) = m's engine-log lines
"[coop-ui] push class OpenXcom::ResearchCompleteState" after line n0. Every TESTED press is real (click_widget OK on BaseDestroyedState,
GEOSCAPE on the new base's screen); build_new_base, get_soldiers + set_soldier_dead (STRIP), spawn_ufo, trigger_base_defense, start_research,
geo_set_speed and dismiss_popup are setup levers. No row presses BASES and no row builds a base after a loss (either re-points the index).
Red today: RL1-land, RL1-popup, RL2-land, RL2-popup FAIL (4 of 12); every other cell PASS. Green (E1-E4): 12 / 12.
One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; a precondition miss ends its row (later cells "not reached")
with ONE CAPTURE line; a boot miss fails every row of that boot with ONE CAPTURE line. ONE foreground run, no
skip; exit 0 only when every cell passes, else 2. Helpers copied from docs rewrite/lh87-2-cap/cap2.py (never imported).
Run: python tools/coop_test/test_lost_base_research_wait.py   (OXC_HARNESS_SLOT selects the lane)"""
import datetime, json, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT  # noqa: E402

KEY = "49702"                               # lobby key (CONSTANTS.md; 0 hits in src + tools at 82728e215)
B2 = (LAND_LON + 0.06, LAND_LAT + 0.03)     # the second base (CAP2 B2; land, accepted on both machines in TASK 0)
T1, T2 = "STR_LASER_WEAPONS", "STR_MOTION_SCANNER"
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
       "race": "STR_SECTOID", "trajectory": "P0", "state": "flying"}
W_LAND, W_WATCH, ADV_CAP, W_BDS, OTHER_HAS, BOOT_S = 5.0, 10.0, 150.0, 6.0, 30.0, 60.0
S_LOSS, S_BUILD, SPEED = 2.0, 1.0, 4
RCP = "[coop-ui] push class OpenXcom::ResearchCompleteState"
LOGN = ("[coop-ui]", "[coop] removed base: ", "basehost", "delete_base", "LoadGameState")
ROWS = (("RL3", ("RL3-pre", "RL3-land", "RL3-popup")), ("RL1", ("RL1-pre", "RL1-land", "RL1-popup", "RL1-index")),
        ("RL2", ("RL2-pre", "RL2-land", "RL2-popup", "RL2-index")), ("END", ("CRASH",)))
RED = ("RL1-land", "RL1-popup", "RL2-land", "RL2-popup")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]


class Stop(Exception):  # a precondition missed: the row ends here
    pass


# ----- probes, levers and real input (copied from docs rewrite/lh87-2-cap/cap2.py, never imported) -----
def js(v): return json.dumps(v, sort_keys=True, default=str)
def now(): return round(time.time() - T0[0], 3)
def rel(t): return round(t - T0[0], 3) if t else None
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None


def crashes():
    out = set()
    for d, _sub, files in os.walk(harness.CRASH_DIR):
        out.update(os.path.join(d, f) for f in files)
    return out


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


def census(gc):
    """geo_state rows [name, coopBase, coopIcon, lon, lat, coopBaseId], selectedBase, clock, discoveredResearch"""
    g = q(gc, {"cmd": "geo_state"})
    bl = [[b.get("name"), bool(b.get("coopBase")), bool(b.get("coopIcon")), round(b.get("lon") or 0, 4), round(b.get("lat") or 0, 4),
           b.get("coopBaseId")] for b in g.get("bases", [])]
    t = g.get("time") or {}
    return {"bases": bl, "selected": g.get("selectedBase"), "clock": [t.get(k) for k in ("year", "month", "day", "hour", "minute")] if t else None,
            "known": set(g.get("discoveredResearch", []) or []), "error": g.get("error")}


def mir(c): return [b for b in c["bases"] if b[2]]
def own(c): return [b for b in c["bases"] if not b[1] and not b[2]]
def own_ids(c): return sorted(b[5] for b in own(c))
def names(c): return [b[0] for b in c["bases"]]
def known(gc): return census(gc)["known"]


def cpu():
    c = harness.cpu_load()
    return {"t": time.strftime("%H:%M:%S"), "cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}


def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def lts(ln):
    """epoch seconds of an openxcom.log line '[16-10-2026_15-08-43.457]\\t...'"""
    try:
        return datetime.datetime.strptime(ln.split("\t")[0].strip("[]"), "%d-%m-%Y_%H-%M-%S.%f").timestamp()
    except Exception:  # noqa: BLE001
        return None


def lines_since(gc, n0): return ["%s %s" % (rel(lts(ln)), ln.split("\t")[-1][:200]) for ln in logl(gc)[n0:] if any(n in ln for n in LOGN)]
def rcp(gc, n0): return [lts(ln) for ln in logl(gc)[n0:] if RCP in ln]


def wait(pred, timeout, interval=0.05):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 3)
        time.sleep(interval)


def real_click(gc, text, timeout=15.0):
    t0 = time.time()
    while time.time() - t0 < timeout and alive(gc):
        ws = [w for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if w.get("visible") is True and w.get("hidden") is False and
              (w.get("text") or "").strip().lower() == text.lower()]
        if ws:
            c = q(gc, {"cmd": "click_widget", "match": ws[0].get("text").strip()})
            return {"text": text, "ok": bool(c.get("ok")), "s": round(time.time() - t0, 2), "tc": now()}
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
    return r.get("ok")


def drain(gc):
    """test_coop_research_sync.drain: close every popup on gc; VIEW REPORTS on research popups"""
    seen = []
    for _ in range(30):
        tp = top(gc)
        if not tp or tp == "GeoscapeState" or tp.startswith("probe failed"):
            break
        if tp == "ResearchCompleteState":
            q(gc, {"cmd": "dismiss_popup", "view_reports": True})
            seen.append([now(), "RC"])
            continue
        r = q(gc, {"cmd": "dismiss_popup"})
        if not r.get("ok"):
            break
        seen.append([now(), "article:" + r["article"] if r.get("article") else r.get("handled", tp)])
    return seen


def press_through(gc, cap=60.0):
    """the real OK on every screen until a bare GeoscapeState (BaseDestroyedState first)"""
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
        w = q(gc, {"cmd": "list_widgets"})
        texts = [z.get("text") for z in w.get("widgets", []) if z.get("visible") and str(z.get("type", "")).endswith("::TextButton")]
        okb = next((m for m in ("OK", "Ok") if any(m.lower() == (tx or "").strip().lower() for tx in texts)), None)
        if okb:
            session.wait_widget_ready(gc, okb, timeout=5)
            steps.append([round(time.time() - t1, 2), t, "OK", cw(gc, okb, 0.8)])
        else:
            steps.append([round(time.time() - t1, 2), t, "no OK", texts[:8]])
            time.sleep(1.0)
            if len(steps) > 3 and all(s[1] == t and s[2] == "no OK" for s in steps[-3:]):
                break
    return {"steps": steps, "secs": round(time.time() - t1, 2)}


def strip(gc, base_name):
    s0 = q(gc, {"cmd": "get_soldiers"})
    hb = [z for z in s0.get("bases", []) if z.get("name") == base_name and not z.get("coopIcon") and not z.get("coopBaseFlag")]
    sids = [s.get("id") for s in (hb[0].get("soldiers", []) if len(hb) == 1 else [])]
    rep = [[sid, (lambda r: [r.get("ok"), r.get("dead"), r.get("error")])(q(gc, {"cmd": "set_soldier_dead", "soldierId": sid}))] for sid in sids]
    after = [len(z.get("soldiers", [])) for z in q(gc, {"cmd": "get_soldiers"}).get("bases", []) if z.get("name") == base_name and not z.get("coopIcon")]
    return {"ids": sids, "replies": rep, "after": after, "entries": len(hb)}


def lose_first_base(loser, base_name):
    """LOSE(m, base): STRIP, spawn_ufo, trigger_base_defense, BaseDestroyedState within W_BDS, the real OK until GeoscapeState, S_LOSS"""
    sp = strip(loser, base_name)
    if not sp["ids"] or sp["after"] != [0] or not all(r[1][0] for r in sp["replies"]):
        raise Stop("%s STRIP of %s: %s" % (loser.name, base_name, sp))
    ufo = q(loser, UFO)
    rep = q(loser, {"cmd": "trigger_base_defense", "ufo_id": ufo.get("ufo_id")})
    if not ufo.get("ufo_id") or not rep.get("ok"):
        raise Stop("%s spawn_ufo %s / trigger_base_defense %s" % (loser.name, ufo, rep))
    v, s = wait(lambda: top(loser) == "BaseDestroyedState", W_BDS)
    st = stk(loser)
    if not v:
        raise Stop("%s: no BaseDestroyedState within %.0f s (stack %s)" % (loser.name, W_BDS, st))
    ok = press_through(loser)
    time.sleep(S_LOSS)
    return {"strip": len(sp["ids"]), "ufo": ufo.get("ufo_id"), "trigger": rep.get("base"), "bdsS": s, "stackAtBds": st, "ok": ok["steps"]}


def build_base(gc, name, pos):
    land = q(gc, {"cmd": "globe_point", "lon": pos[0], "lat": pos[1]}).get("land")
    r = q(gc, {"cmd": "build_new_base", "lon": pos[0], "lat": pos[1], "name": name})
    if not r.get("ok"):
        raise Stop("build %s at %s: %s (land %s)" % (name, pos, r, land))
    time.sleep(1.0)
    rec = {"reply": r, "pos": [round(pos[0], 4), round(pos[1], 4)], "land": land, "stack": stk(gc)}
    if top(gc) == "BasescapeState":
        rec["geoscape"] = must_click(gc, "GEOSCAPE", 10)["ok"]
    wait_top(gc, "GeoscapeState", 15)
    return rec


def other_has(gc, name, timeout=OTHER_HAS):
    v, s = wait(lambda: name in names(census(gc)), timeout, 0.25)
    if not v:
        raise Stop("%s has no base %s within %d s: %s" % (gc.name, name, timeout, census(gc)["bases"]))
    return s


def research(b, r, topic):
    """RESEARCH(r, T, {host, client}): returns n0, the start reply and when r knew T"""
    drained = (b.host, b.client)
    n0 = {gc.name: len(logl(gc)) for gc in drained}
    rec = {"r": r.name, "topic": topic, "n0": n0, "tStart": time.time()}
    rec["start"] = q(r, {"cmd": "start_research", "topic": topic, "cost": 1, "scientists": 1})
    kr = None
    while rec["start"].get("ok") and time.time() - rec["tStart"] < ADV_CAP and alive(r):
        for gc in drained:
            drain(gc)
        if topic in known(r):
            kr = time.time()
            break
        for gc in drained:
            if top(gc) == "GeoscapeState":
                q(gc, {"cmd": "geo_set_speed", "idx": SPEED})
        time.sleep(0.2)
    for _ in range(2):
        for gc in drained:
            q(gc, {"cmd": "geo_set_speed", "idx": 0})
        time.sleep(0.3)
    rec.update({"knowsS": round(kr - rec["tStart"], 3) if kr else None, "tStart": rel(rec["tStart"])})
    return rec


def watch(b, v, topic):
    """WATCH(v, T): read v every 0.5 s for W_WATCH s, draining both machines after each read"""
    reads, first, t1, i = [], None, time.time(), 0
    while True:
        dt = t1 + 0.5 * i - time.time()
        if dt > 0:
            time.sleep(dt)
        if time.time() - t1 > W_WATCH + 0.01:
            break
        c = census(v)
        tr = time.time()
        k = topic in c["known"]
        reads.append([rel(tr), k, c["selected"], own_ids(c), stk(v)[-1:]])
        if k and first is None:
            first = tr
        for gc in (v, b.client if v is b.host else b.host):
            drain(gc)
        i += 1
    return reads, first


def capture(b):
    out = {}
    for gc in (b.host, b.client):
        out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None} if not alive(gc) else {
            "stack": stk(gc), "get_coop": {k: v for k, v in q(gc, {"cmd": "get_coop"}).items() if k in ("insideCoopBase", "onConnect", "coopDialog")},
            "geo": (lambda c: {"bases": c["bases"], "selected": c["selected"], "clock": c["clock"]})(census(gc)),
            "widgets": [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if w.get("visible") and w.get("text")][:20],
            "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-40:]]}
    return out


# ----- the boots and the rows -----
class Boot:
    def __init__(self, tag):
        self.tag = tag
        self.host = GameClient("host", None, make_user_dir("w2h88_%s_host" % tag))
        self.client = GameClient("client", None, make_user_dir("w2h88_%s_client" % tag))


class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now()}
        self.n0 = [len(logl(b.host)), len(logl(b.client))] if b is not None and alive(b.host) and alive(b.client) else [0, 0]

    def cell(self, cid, ok, label): self.res[cid] = (bool(ok), label)

    def need(self, ok, what):
        if not ok:
            raise Stop(what)

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


def bring_up(b, st):
    """Boot(KEY, tag): spawn + connect, set_seed 1 on both, a SEPARATE campaign, speed 0, one own base and one mirror each, sync on"""
    st["cpu"] = cpu()
    for gc in (b.host, b.client):
        gc.spawn()
    for gc in (b.host, b.client):
        gc.connect(timeout=BOOT_S)
    st["seed"] = [q(gc, {"cmd": "set_seed", "seed": 1}).get("seed") for gc in (b.host, b.client)]
    session.new_campaign(b.host, b.client, port=KEY, campaign_mode="coop")
    for gc in (b.host, b.client):
        wait_top(gc, "GeoscapeState", 60)
        q(gc, {"cmd": "geo_set_speed", "idx": 0})
    wait(lambda: len(mir(census(b.host))) == 1 and len(mir(census(b.client))) == 1, 20, 0.25)
    h, c = census(b.host), census(b.client)
    st["sync"] = [(q(gc, {"cmd": "event_state"}).get("researchMode") or {}).get("sync") for gc in (b.host, b.client)]
    st["bases"] = {"host": h["bases"], "client": c["bases"]}
    if st["seed"] != [1, 1] or st["sync"] != [True, True]:
        raise Stop("boot: seed %s, research sync %s" % (st["seed"], st["sync"]))
    if not (stk(b.host) == ["GeoscapeState"] and stk(b.client) == ["GeoscapeState"] and len(own(h)) == 1 and len(own(c)) == 1
            and len(mir(h)) == 1 and len(mir(c)) == 1):
        raise Stop("boot: host %s, client %s" % (h["bases"], c["bases"]))
    b.HB, b.CB = own(h)[0], own(c)[0]
    b.HBm, b.CBm = mir(c)[0][0], mir(h)[0][0]   # the partner's first base, as each machine names it
    builder, other, name = (b.host, b.client, "HostBase2") if b.tag == "a" else (b.client, b.host, "ClientBase2")
    st["setup"] = build_base(builder, name, B2)
    st["setup"]["otherHasS"] = other_has(other, name)
    time.sleep(S_BUILD)
    bc = census(builder)
    nb = [z for z in own(bc) if z[0] == name]
    if len(nb) != 1:
        raise Stop("%s's own bases %s lack %s" % (builder.name, bc["bases"], name))
    b.B2 = nb[0]
    st["after"] = {"bases": bc["bases"], "selected": bc["selected"]}


def row_receive(b, r, researcher, receiver, topic, pre_ok, lose=None):
    """RL-3 / RL-1 / RL-2: (LOSE(receiver, its first base)), read the receiver (pre_ok(p) or the row ends), RESEARCH(researcher, topic),
    WATCH(receiver, topic)"""
    ev = r.ev
    if lose:
        ev["loss"] = lose_first_base(receiver, lose)
    c = census(receiver)
    ev["pre"] = p = {"selected": c["selected"], "ownIds": own_ids(c), "bases": c["bases"], "stack": stk(receiver), "knows": topic in c["known"]}
    pre_ok(p)
    res = research(b, researcher, topic)
    ev["research"] = res
    r.need(res["start"].get("ok") and res["knowsS"] is not None, "start_research %s; KNOWS(%s, %s) within %.0f s: %s" % (
        res["start"], researcher.name, topic, ADV_CAP, res["knowsS"]))
    reads, first = watch(b, receiver, topic)
    ev["watch"] = reads
    rr = rcp(researcher, res["n0"][researcher.name])
    vr = [z for z in rcp(receiver, res["n0"][receiver.name]) if z]
    t0 = rr[0] if rr else None
    ev.update({"t0": rel(t0), "rcp": [rel(z) for z in vr], "land": round(first - t0, 3) if (first and t0) else None})
    r.need(t0, "t0: no RCP(%s) line after its row cursor" % researcher.name)
    ev["rcpMinusT0"] = [round(z - t0, 3) for z in vr]
    return ev, reads


def row(b, r, st, rid):
    h, c = b.host, b.client
    if rid == "RL3":
        def pre3(p):
            r.need(not p["knows"] and any(z[0] == p["selected"] and not z[1] and not z[2] for z in p["bases"]),
                   "host knew T1 before (%s) or its selectedBase %r is not an own base: %s" % (p["knows"], p["selected"], p["bases"]))
        ev, reads = row_receive(b, r, c, h, T1, pre3)
        r.cell("RL3-pre", True, "start ok; client knows T1 +%s s; t0 %s; T1 unknown on the host before; host selectedBase %r (own)" % (
            ev["research"]["knowsS"], ev["t0"], ev["pre"]["selected"]))
    else:
        recv, rsch, first, loser_mirror = (h, c, b.HB, b.CBm) if rid == "RL1" else (c, h, b.CB, b.HBm)

        def pre12(p):
            r.need(p["ownIds"] == [b.B2[5]] and p["selected"] == loser_mirror and p["stack"] == ["GeoscapeState"] and not p["knows"],
                   "after the loss %s own ids %s (want [%s]), selectedBase %r (want %r), stack %s, T2 known %s" % (
                       recv.name, p["ownIds"], b.B2[5], p["selected"], loser_mirror, p["stack"], p["knows"]))
        ev, reads = row_receive(b, r, rsch, recv, T2, pre12, lose=first[0])
        p = ev["pre"]
        r.cell(rid + "-pre", True, "%s lost %s (%s); own ids %s; selectedBase %r (the partner's mirror); stack %s; %s knows T2 +%s s; t0 %s" % (
            recv.name, first[0], ev["loss"], p["ownIds"], p["selected"], p["stack"], rsch.name, ev["research"]["knowsS"], ev["t0"]))
    recv_name = "host" if rid in ("RL3", "RL1") else "client"
    r.cell(rid + "-land", ev["land"] is not None and ev["land"] <= W_LAND, "LAND(%s) %s s (W_LAND %.0f s); %d of %d WATCH reads know the topic" % (
        recv_name, ev["land"], W_LAND, sum(1 for z in reads if z[1]), len(reads)))
    r.cell(rid + "-popup", len(ev["rcpMinusT0"]) == 1 and ev["rcpMinusT0"][0] <= W_LAND, "RCP(%s, n0) at t0 + %s s (want exactly 1, <= %.0f s)" % (
        recv_name, ev["rcpMinusT0"], W_LAND))
    if rid != "RL3":
        last = reads[-1] if reads else [None, None, None, None]
        want = b.CBm if rid == "RL1" else b.HBm
        r.cell(rid + "-index", last[2] == want and last[3] == [b.B2[5]], "end of WATCH: %s selectedBase %r (want %r), own ids %s (want [%s])" % (
            recv_name, last[2], want, last[3], b.B2[5]))


class X:  # the file's run state: failing cells, every process's alive-until-shutdown record
    def __init__(self): self.fails, self.alive = [], []


def run_boot(x, tag, rows):
    b, st = Boot(tag), {}
    try:
        try:
            bring_up(b, st)
        except Exception as e:  # noqa: BLE001 - a boot miss fails every row of the boot with ONE CAPTURE line
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
            x.alive.append(["%s_%s" % (tag, gc.name), alive(gc), None])
            try:
                if gc.proc is not None and alive(gc):
                    gc.shutdown(expected_returncodes=OKRC)
                x.alive[-1][2] = gc.proc.poll() if gc.proc else None
            except Exception as e:  # noqa: BLE001
                print("FAIL shutdown %s %s: %s" % (tag, gc.name, str(e)[:300]), flush=True)
                x.alive[-1][1] = False


def main():
    x, crash0 = X(), crashes()
    T0[0] = time.time()
    try:
        run_boot(x, "a", ("RL3", "RL1"))
        run_boot(x, "b", ("RL2",))
    finally:
        r, new = Row(x, None, "END"), sorted(crashes() - crash0)
        r.ev.update({"newCrash": [os.path.basename(p) for p in new], "aliveUntilShutdownRc": x.alive, "crashDir": harness.CRASH_DIR, "cpu": cpu()})
        r.cell("CRASH", not new and x.alive and all(a[1] and a[2] in OKRC for a in x.alive),
               "new crash files %d %s; [process, alive until shutdown, rc] %s" % (len(new), r.ev["newCrash"][:3], x.alive))
        r.finish()
    cl = [cid for _r, cs in ROWS for cid in cs]
    print("SUMMARY pass=%d fail=%d (W2-H88 LBR; failing %s; wall %.1f s)" % (len(cl) - len(set(x.fails)), len(set(x.fails)),
                                                                            sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2


if __name__ == "__main__":
    sys.exit(main())
