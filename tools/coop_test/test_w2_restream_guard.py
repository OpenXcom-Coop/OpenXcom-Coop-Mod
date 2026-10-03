"""W2-U7 - test_w2_restream_guard.py: harness dismissals vs a world restream (F5820, F5822; docs
rewrite/prompts/w2u7_harness_restream_guard.md (f)). A SHARED replica's restream pushes a LoadGameState that adopts the
world and pops itself after ~10 frames (~20 ms, F5861); a harness pop of it loses the world, the resync stays pending
(replica request) and the shared-apply hold stays set (F5820). The TEST-ONLY `dismiss_arm` lever fires ONE harness
command in the game thread on the first pump pass whose top is a LoadGameState (Q1 a). Boots (labels 49296/49297): A lobby
47286 (U7-1 replica repair vs dismiss_popup); B 47288 (U7-2 geo.settle vs a pending resync held by the host's
shared_update_defer, F5869; U7-4 guard: ordinary windows close as before); C 47290 (U7-3 host-initiated restream vs
dismiss_popup; U7-5 close_screens / pop_state / geo_run). RED (commit 1): U7-1, U7-2, U7-3 and U7-5's three fires FAIL on
their refusal / adoption / walk cells; U7-4 and every GUARD cell pass. GREEN (commit 2): every row passes. Each row prints
"EVIDENCE <id>:" then "PASS <id>" or "FAIL <id>: ..."; a guard miss (FIXTURE-STOP) adds one "CAPTURE <id>:" line.
WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.
Run:  python tools/coop_test/test_w2_restream_guard.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import shared_fixture

LABELS = (49296, 49297)        # control-socket labels only (ephemeral sockets), F5870
BOOTS = (("A", "w2u7a", 47286, ("U7-1",)), ("B", "w2u7b", 47288, ("U7-2", "U7-4")),
         ("C", "w2u7c", 47290, ("U7-3", "U7-5")))
ARM_MS = 10000                 # dismiss_arm timeoutMs
ADOPT_S = 3.0                  # green: the adoption and the rename land within 3 s
HOLD_S = 3.0                   # U7-2: the host's defer holds the resync serve (F5869)
WALK_S = 2.0                   # U7-2: geo.RESYNC_WAIT_S for its one settle
CLEAN_S = 10.0                 # a clean resync's pending clears within 10 s
OLD, GEO_ONLY, NOTICE = "HostBase", ["GeoscapeState"], "GiftNoticeState"

class GuardMiss(Exception): pass  # a guard cell failed: FIXTURE-STOP

def short(x, n=300):
    s = x if isinstance(x, str) else json.dumps(x, default=str, sort_keys=True)
    return s if len(s) <= n else s[:n] + "..."

def stk(gc): return [s.split("::")[-1] for s in gc.cmd({"cmd": "get_state"}).get("states", [])]
def rs(gc): return gc.cmd({"cmd": "shared_resync_stats"})
def name0(gc): return ((gc.cmd({"cmd": "geo_state"}).get("bases") or [{}])[0]).get("name")
def chk(gc): return {k: v for k, v in gc.cmd({"cmd": "shared_checksum"}).items() if k.startswith("chk")}

def until(pred, timeout, interval=0.1):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v, round(time.time() - t0, 2)
        time.sleep(interval)

def settle_catching(host, client):
    """geo.settle; a ResyncPendingError (absent on the red build) is caught here and reported."""
    t0, st, raised = time.time(), None, None
    try:
        st = geo.settle(host, client)
    except getattr(geo, "ResyncPendingError", ()) as e:
        raised = e
    d, s = (st["dismissed"].get(client.name) if st else None), str(raised or "")
    return {"wall": round(time.time() - t0, 2), "dismissedClient": d, "raised": short(s, 900) if raised else None,
            "namesPending": "pending" in s, "namesNotice": NOTICE in s}

class Row:
    def __init__(self, rid, host, client):
        self.rid, self.host, self.client, self.cells, self.ev = rid, host, client, [], {}
        self.cur = geo._log_cursor(client)

    def cell(self, name, ok, detail, msg=None, guard=False):
        self.cells.append({"cell": name, "guard": guard, "pass": bool(ok)})
        if not ok:
            self.cells[-1]["msg"] = (msg + " | " if msg else "") + short(detail, 700)
            if guard:
                raise GuardMiss(name)

    def guard(self, name, ok, detail):
        self.cell(name, ok, detail, guard=True)
    def chk_eq(self):
        return bool(until(lambda: (lambda a, b: bool(a) and a == b)(chk(self.host), chk(self.client)), 5)[0])

def capture(r):
    """FIXTURE-STOP dump: both stacks, shared_resync_stats, shared_stats, get_coop, the arm record, [coop-ui] tail."""
    out = {}
    for gc in (r.host, r.client):
        co = gc.cmd({"cmd": "get_coop"})
        out[gc.name] = {"stack": stk(gc), "resync": rs(gc), "shared_stats": gc.cmd({"cmd": "shared_stats"}),
                        "coop": {k: co.get(k) for k in ("shared", "lobbyMode", "coopDialog", "onConnect", "isLoadProgress")}}
    out["arm"] = r.client.cmd({"cmd": "dismiss_arm_state"}).get("arm")
    out["clientCoopUiTail"] = geo._read_coop_ui(r.client, r.cur)[0][-20:]
    return out

def s0(r, name):  # section (f) frames: S0, arm, fired, apply probe, clean
    geo.settle(r.host, r.client)
    cs, crs, hrs = stk(r.client), rs(r.client), rs(r.host)
    d = {"stack": cs, "pending": crs.get("pending"), "R0": crs.get("requests"), "H0": hrs.get("requests"),
         "names": [name0(r.host), name0(r.client)], "chkEqual": r.chk_eq()}
    r.ev.setdefault("S0", []).append(d)
    r.guard("S0", cs == GEO_ONLY and d["pending"] is False and d["names"] == [name, name] and d["chkEqual"], d)
    return d["R0"], d["H0"]

def arm(r, fire):
    r.client.ok({"cmd": "show_notice", "message": "U7"})
    t = stk(r.client)
    a = r.client.cmd({"cmd": "dismiss_arm", "type": "LoadGameState", "fire": fire, "timeoutMs": ARM_MS})
    r.guard("arm(%s)" % fire, t[-1:] == [NOTICE] and a.get("ok") and a.get("armed"), {"stack": t, "reply": a})

def fired(r, fire, pend):
    t0, a = time.time(), {}
    while time.time() - t0 < ARM_MS / 1000.0 + 1.0:
        a = r.client.cmd({"cmd": "dismiss_arm_state"}).get("arm") or {}
        if a.get("fired") or a.get("expired"):
            break
        time.sleep(0.1)
    r.ev.setdefault("arm", []).append(a)
    r.guard("fired(%s)" % fire, a.get("fired") is True and a.get("topBefore") == "LoadGameState"
            and a.get("pendingAtFire") is pend, a)
    return json.loads(a.get("response") or "{}")  # execute()'s own JSON reply line

def probe(r, new, secs, pend_false):
    r.host.ok({"cmd": "base_rename", "name": new})
    polls, t0 = [], time.time()
    while True:
        p = {"t": round(time.time() - t0, 2), "stack": stk(r.client), "pending": rs(r.client).get("pending"),
             "applyQueued": r.client.cmd({"cmd": "shared_stats"}).get("applyQueued"), "name": name0(r.client)}
        polls.append(p)
        if p["t"] >= secs:
            break
        time.sleep(0.25)
    hn = name0(r.host)
    r.ev.setdefault("probe", []).append({"new": new, "hostName": hn, "polls": polls})
    r.guard("host rename %s" % new, hn == new, hn)
    if pend_false:
        r.guard("pending false throughout (%s)" % new, all(p["pending"] is False for p in polls),
                [p["pending"] for p in polls])
    return polls

def adopted(r, new, old, polls, pend, notice, red_msg):
    """GREEN: within ADOPT_S [GeoscapeState], not pending, renamed, 0 queued. Red signature: old name, notice, pend, queued."""
    hit = next((p for p in polls if p["stack"] == GEO_ONLY and p["pending"] is False and p["name"] == new
                and p["applyQueued"] == 0), None)
    sig = (all(p["name"] == old and p["pending"] is pend and (not notice or NOTICE in p["stack"]) for p in polls)
           and (polls[-1]["applyQueued"] or 0) >= 1)
    r.cell("adoption(%s)" % new, hit is not None and hit["t"] <= ADOPT_S, {"hit": hit, "redSignature": sig},
           red_msg if sig else "no adoption within %.0f s and the red signature did NOT match" % ADOPT_S)

def clean(r):
    h0 = rs(r.host).get("requests")
    f = r.client.cmd({"cmd": "force_resync"})
    ok, secs = until(lambda: rs(r.client).get("pending") is False, CLEAN_S)
    nm, _ = until(lambda: (lambda a, b: a if a == b else None)(name0(r.host), name0(r.client)), ADOPT_S)
    d = {"sent": f.get("sent"), "pendingClearS": secs, "name": nm, "chkEqual": r.chk_eq(),
         "hostRequests": [h0, rs(r.host).get("requests")]}
    r.ev.setdefault("clean", []).append(d)
    r.guard("clean", f.get("sent") is True and ok and nm and d["chkEqual"] and d["hostRequests"][1] == h0 + 1, d)
    return nm

def refusal_popup(r, resp):
    ok = (resp.get("ok") is False and resp.get("wait") is True and resp.get("refused") == "restream"
          and "LoadGameState" in str(resp.get("type")))
    r.cell("refusal(dismiss_popup)", ok, resp, "dismiss_popup handled %r on the restream's LoadGameState (want refused "
           "'restream', wait true)" % resp.get("handled"))

def tail_cells(r, R0, H0):
    rr, hr = rs(r.client).get("requests"), rs(r.host).get("requests")
    r.guard("host requests H0+1", hr == H0 + 1, [H0, hr])
    r.cell("client requests R0+1", rr == R0 + 1, [R0, rr])
    r.cell("checksum equal", r.chk_eq(), "shared_checksum differs")

def u7_1(r, boot):
    R0, H0 = s0(r, OLD)
    arm(r, "dismiss_popup")
    f = r.client.cmd({"cmd": "force_resync"})
    r.guard("sent", f.get("role") == "replica" and f.get("sent") is True, f)
    refusal_popup(r, fired(r, "dismiss_popup", True))
    adopted(r, "U7A", OLD, probe(r, "U7A", 5.0, False), True, True,
            "the harness popped the restream's LoadGameState: no adoption, resync pending, applies held (F5820)")
    tail_cells(r, R0, H0)

def u7_2(r, boot):
    R0, H0 = s0(r, OLD)
    r.client.ok({"cmd": "show_notice", "message": "U7"})
    d = r.host.cmd({"cmd": "shared_update_defer", "on": True})
    saved = getattr(geo, "RESYNC_WAIT_S", None)
    try:
        r.guard("deferred", d.get("deferred") is True and stk(r.client)[-1:] == [NOTICE], d)
        cur = geo._log_cursor(r.client)
        f = r.client.cmd({"cmd": "force_resync"})
        r.guard("sent", f.get("role") == "replica" and f.get("sent") is True, f)
        hold, t0 = [], time.time()
        while time.time() - t0 < HOLD_S:
            hold.append([rs(r.client).get("pending"), (stk(r.client) or [""])[-1]])
            time.sleep(0.1)
        lgs = [e for e in geo._read_coop_ui(r.client, cur)[0] if e[1] == "LoadGameState"]
        r.ev["hold"] = {"polls": len(hold), "bad": [h for h in hold if h != [True, NOTICE]], "lgsEvents": lgs}
        r.guard("hold 3 s (F5869)", not r.ev["hold"]["bad"] and not lgs, r.ev["hold"])
        geo.RESYNC_WAIT_S = WALK_S
        w = settle_catching(r.host, r.client)
        w["after"] = {"stack": stk(r.client), "pending": rs(r.client).get("pending")}
        r.ev["walk"] = w
        ok = (w["raised"] is not None and WALK_S <= w["wall"] <= 3.5 and w["namesPending"] and w["namesNotice"]
              and w["after"]["stack"][-1:] == [NOTICE])
        red = w["raised"] is None and "generic" in (w["dismissedClient"] or []) and w["after"]["pending"] is True
        r.cell("walk waits (F5822)", ok, w,
               "the client walk dismissed a window while a resync was pending" if red else "unexpected walk outcome")
    finally:  # restore the bound (absent on the red build) and release the host
        geo.__dict__.pop("RESYNC_WAIT_S", None) if saved is None else setattr(geo, "RESYNC_WAIT_S", saved)
        d = r.host.cmd({"cmd": "shared_update_defer", "on": False})
    r.guard("defer off", d.get("deferred") is False, d)
    ok, secs = until(lambda: rs(r.client).get("pending") is False, CLEAN_S)
    st_ok, secs2 = until(lambda: stk(r.client) == GEO_ONLY, ADOPT_S)
    r.ev["release"] = {"pendingClearS": secs, "stackS": secs2, "stack": stk(r.client)}
    r.guard("post-release adoption", ok and st_ok, r.ev["release"])
    w2 = r.ev["settle2"] = settle_catching(r.host, r.client)
    r.cell("second settle", w2["raised"] is None and w2["dismissedClient"] == [], w2)
    tail_cells(r, R0, H0)

def u7_4(r, boot):
    s0(r, OLD)
    r.client.ok({"cmd": "show_notice", "message": "U7"})
    d = r.client.cmd({"cmd": "dismiss_popup"})
    t = stk(r.client)
    r.cell("dismiss_popup ordinary", d.get("handled") == "generic" and t[-1:] == GEO_ONLY, {"reply": d, "stack": t})
    o = r.client.cmd({"cmd": "open_screen", "screen": "stores"})
    t1 = stk(r.client)
    c = r.client.cmd({"cmd": "close_screens"})
    t2 = stk(r.client)
    r.cell("close_screens ordinary", o.get("ok") and (c.get("popped") or 0) >= 1 and "refused" not in c
           and t2[-1:] == GEO_ONLY, {"open": o, "opened": t1, "reply": c, "stack": t2})
    r.client.ok({"cmd": "show_notice", "message": "U7"})
    w = r.ev["settle"] = settle_catching(r.host, r.client)
    r.cell("settle ordinary", w["raised"] is None and w["dismissedClient"] == ["generic"] and w["wall"] < 2.0, w)

def u7_3(r, boot):
    s0(r, OLD)
    arm(r, "dismiss_popup")
    f = r.host.cmd({"cmd": "force_resync"})
    r.guard("role host", f.get("role") == "host" and f.get("ok"), f)
    refusal_popup(r, fired(r, "dismiss_popup", False))
    adopted(r, "U7C", OLD, probe(r, "U7C", 5.0, True), False, True,
            "the harness popped a host-initiated restream's LoadGameState (a pending wait cannot see it)")
    boot["name"] = clean(r)

FIRE_OK = {"close_screens": lambda x: x.get("refused") == "restream" and x.get("popped") == 0
           and "LoadGameState" in str(x.get("stoppedAt")),
           "pop_state": lambda x: x.get("ok") is False and x.get("refused") == "restream",
           "geo_run": lambda x: x.get("drained") is False and x.get("refused") == "restream"}
FIRE_RED = {"close_screens": lambda x: "refused" not in x and (x.get("popped") or 0) >= 1,
            "pop_state": lambda x: x.get("ok") is True,
            "geo_run": lambda x: x.get("drained") is True and "LoadGameState" in str(x.get("topType"))}

def u7_5(r, boot):
    for i, fire in enumerate(("close_screens", "pop_state", "geo_run"), 1):
        old = boot["name"]
        s0(r, old)
        arm(r, fire)
        f = r.host.cmd({"cmd": "force_resync"})
        r.guard("role host (%s)" % fire, f.get("role") == "host" and f.get("ok"), f)
        resp = fired(r, fire, False)
        r.cell("refusal(%s)" % fire, FIRE_OK[fire](resp), resp, "%s popped the restream's LoadGameState" % fire
               if FIRE_RED[fire](resp) else "%s: unexpected reply" % fire)
        adopted(r, "U7E%d" % i, old, probe(r, "U7E%d" % i, 3.0, True), False, False,
                "%s popped the restream's LoadGameState" % fire)
        boot["name"] = clean(r)

ROWS = {"U7-1": u7_1, "U7-2": u7_2, "U7-3": u7_3, "U7-4": u7_4, "U7-5": u7_5}

def run_row(rid, js, boot, results):
    r, t0, err = Row(rid, js.host, js.client), time.time(), None
    try:
        ROWS[rid](r, boot)
    except GuardMiss as e:
        err = "GUARD %s" % e
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, short(str(e), 800))
    r.ev["wall"] = round(time.time() - t0, 1)
    r.ev["cells"] = [[c["cell"], "guard" if c["guard"] else "row", c["pass"]] for c in r.cells]
    print("EVIDENCE %s: %s" % (rid, json.dumps(r.ev, default=str)), flush=True)
    if err:
        try:
            cap = capture(r)
        except Exception as e:
            cap = "capture failed: %s" % short(str(e))
        print("CAPTURE %s: %s" % (rid, json.dumps(cap, default=str)), flush=True)
    fails = ["%s%s: %s" % ("GUARD " if c["guard"] else "", c["cell"], c["msg"]) for c in r.cells if not c["pass"]]
    if err and not err.startswith("GUARD"):
        fails.append(err)
    results[rid] = not fails
    print("PASS %s" % rid if not fails else "FAIL %s: %s" % (rid, " || ".join(fails)), flush=True)

def run_boot(key, tag, lobby, rids, results, walls):
    t0, js, boot = time.time(), None, {"name": OLD}
    try:
        js = shared_fixture.bring_up(tag, LABELS + (lobby,))
    except Exception as e:
        print("CAPTURE boot %s: %s" % (key, short(str(e), 900)), flush=True)
    walls[key] = round(time.time() - t0, 1)
    try:
        for rid in rids:
            if js is None:
                results[rid] = False
                print("FAIL %s: boot" % rid, flush=True)
            else:
                run_row(rid, js, boot, results)
    finally:
        if js is not None:
            js.shutdown()

def main():
    t0, results, walls = time.time(), {}, {}
    for key, tag, lobby, rids in BOOTS:
        run_boot(key, tag, lobby, rids, results, walls)
    order = [rid for b in BOOTS for rid in b[3]]
    passed, failed = [x for x in order if results.get(x)], [x for x in order if not results.get(x)]
    print("\ntest_w2_restream_guard: %d/%d passed (pass=%s fail=%s) in %.1fs (boot walls %s)"
          % (len(passed), len(order), passed, failed, time.time() - t0, walls), flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
