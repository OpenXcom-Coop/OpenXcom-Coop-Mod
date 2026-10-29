"""R4-L2 stage S-B (spec rewrite/prompts/r4l2_campaign_rejoin.md (f) row RL, QL2-2 a, AMENDMENT R4-L2-1; TASK 0
rewrite/r4l2-task0/sb/CONSTANTS.md): a rejoiner lost during its rejoin leaves the paused battle with no co-op state. A skirmish client leaves
(drop_client_mid_battle), a fresh client2 rejoins with hold_battle_ready armed (its battle_ready stashed, so the host stays in phase Handshake
under offerRejoinBattle()), and client2 is killed there. disconnectTCP()'s SPEC 16 spare needs phase Active, so the host takes the full reset:
phase Idle, battleId 0, peerAbsent false, dialog 62 kept; offerRejoinBattle()'s guard then refuses every later rejoin
(GUARD +1, client3 on 52 for good). TASK 0 T0-L measured it 2/2, the kill on the -2 path both times.
  Boot L (key "48601", w2r4l2_l_host / _client / _client2 / _client3): row RL. Cells: RL-1 GUARD PAUSE; RL-2 GUARD the rejoin in flight (host
  phase Handshake, client2 held, OFFER +1 reading battleId=B0, client2 CLIENT_ACTIVE +1); RL-3 FIX the pause kept at W (phase Active, peerAbsent
  true, battleId B0, inBattle true, dialog 62 backVisible false, LOST +1; EVIDENCE names the loss path); RL-4 FIX client3's rejoin (OFFER +1
  more, GUARD +0, RESUME within W_ACK, both tops BattlescapeState, phase Active, peerAbsent false, battleId B0 on both); RL-5 FIX SPLIT(host) ==
  SPLIT(client3) == SPLIT0 and HASH(host, client3); RL-6 GUARD CRASH 0.
Definitions (spec (f)): POLL 0.25 s; W 15 s (the host observed at 0.2 s); W_ACK = WATCH_CAP_S (RV-U13 S-D; was 30 s); PAUSE(host)
within 30 s of the leave: phase Active, peerAbsent true, battleId B0, inBattle true, dialog 62 backVisible false, stack [..., BattlescapeState,
CoopState]; SPLIT = sorted (unit id, coop) of faction 0, not isOut; HASH = wait_host_idle + assert_hash_clean(full) + desyncSeen false on both;
REJOIN(client3) = a fresh client3 on its own dir, rejoin_skirmish, wait <= W_ACK for the host's resumeAck true AND peerAbsent false (profile_ok
on any host Profile on top), press_back_when_shown(host, codes=(62,)), both tops BattlescapeState <= 60 s. battle_state is probed only with a
BattlescapeState on the stack or no battle in the world; the killed client2 is never probed. Needles = host log since the row's
baseline (client2: its own log). A WAIT that times out ends the row (later cells "not reached"), except REJOIN's resumeAck wait: RL-4 is
evaluated with the values at the timeout. EVIDENCE before each verdict; a failed row prints ONE CAPTURE line; ONE run; exit 0 iff
every cell passes, else 2.
Red (S-B commit 1): RL FAIL on RL-3, RL-4 and RL-5 "not reached" (RL-1, RL-2, RL-6 PASS).
"""
import json
import os
import sys
import time
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
from test_skirmish_rejoin_battle import drop_client_mid_battle, rejoin_skirmish, start_skirmish_battle  # noqa: E402

WATCH_CAP_S = 135  # REJOIN's wait ends at resumeAck; >= max(120, 2.5 x the loaded rejoin), F11192
POLL, W, W_POLL, W_ACK, W_PAUSE, W_FLIGHT = 0.25, 15.0, 0.2, WATCH_CAP_S, 30.0, 60.0
KEY, TAG = "48601", "w2r4l2_l"
BS, CS, PROFILE = "BattlescapeState", "CoopState", "Profile"
OFFER, GUARD = "rejoin battle_offer sent (battleId=", "offerRejoinBattle() called while the battle is not "
LOST = "the rejoiner was lost during the rejoin - the pause is kept"
FREEZE, DROP, CLIENT_ACTIVE = "[coop-session] freeze (lobbyMode=", "[coop-session] onClientDrop", "CLIENT phase Active (battleId="
NEEDLES = {"OFFER": OFFER, "GUARD": GUARD, "LOST": LOST, "FREEZE": FREEZE, "DROP": DROP}

class Stop(Exception):
    """a WAIT timed out or a fixture precondition missed: the row ends here"""

def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]

def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}

def pick(r, keys):
    return {k: r.get(k) for k in keys}

def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None

def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]

def top(gc):
    return (stack(gc) or [None])[-1]

def coop(gc):
    return pick(q(gc, {"cmd": "get_coop"}), ("onConnect", "coopSession", "lobbyMode", "resumeAck", "coopDialog", "inBattle", "error"))

def dlg(gc):
    return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backVisible", "error"))

def held(gc):
    return pick(q(gc, {"cmd": "hold_battle_ready"}), ("ok", "armed", "held", "error"))

def bs_raw(gc):
    """battle_state, only with a BattlescapeState on the stack or no battle in the world; {} otherwise"""
    if BS not in stack(gc) and q(gc, {"cmd": "get_coop"}).get("inBattle") is not False:
        return {}
    return q(gc, {"cmd": "battle_state"})

def auth(gc):
    r = bs_raw(gc)
    if not r:
        return {"skipped": "no BattlescapeState, a battle in the world (F10980)"}
    return dict(pick(r, ("phase", "inBattle", "turn", "error")), **pick(r.get("authority") or {}, ("battleId", "peerAbsent", "peerLeftByChoice")))

def split(gc):
    return sorted([u.get("id"), u.get("coop")] for u in bs_raw(gc).get("units") or [] if u.get("faction") == 0 and not u.get("isOut"))

def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []

def since(gc, n0, needle):
    return [ln.split("\t")[-1][:220] for ln in log(gc)[n0:] if needle in ln]

def counts(gc, n0):
    lines = log(gc)[n0:]
    return {k: sum(1 for ln in lines if v in ln) for k, v in NEEDLES.items()}

def wait(desc, pred, timeout, interval=POLL):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(interval)
    raise Stop("WAIT %s: timed out after %.0f s" % (desc, timeout))

def hash_ok(host, other, what):
    """spec (f) HASH(host, other) -> (ok, evidence)"""
    ev = {}
    try:
        session.wait_host_idle(host, other)
        hh, _ch = session.assert_hash_clean(host, other, full=True, what=what)
        ev["equal buckets"] = len(hh)
    except Exception as e:
        ev["error"] = short(e, 700)
    ev["desyncSeen"] = [q(gc, {"cmd": "event_state"}).get("desyncSeen") for gc in (host, other)]
    return "error" not in ev and ev["desyncSeen"] == [False, False], ev

class Row:
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.t0, self.n_h = rid, cells, x, [], set(), time.time(), 0
        self.cr0 = session._crash_log_snapshot()

    def cell(self, cid, kind, label, ok, ev):
        print("EVIDENCE %s: %s" % (cid, json.dumps(ev, sort_keys=True, default=str)), flush=True)
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        print("EVIDENCE %s stop: %s" % (self.rid, why), flush=True)
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:160]), flush=True)
            self.fails.append(cid)

    def end(self, crash_cid, results, walls):
        """the CRASH cell (every case), ONE CAPTURE line when a cell failed, the row verdict"""
        if crash_cid:
            new = sorted(session._crash_log_snapshot() - self.cr0)
            self.cell(crash_cid, "GUARD", "CRASH 0 (no new crash_*.log in this lane's crash folder since the row's baseline)", not new,
                      {"crash": new})
        x, walls[self.rid] = self.x, round(time.time() - self.t0, 1)
        if self.fails:
            live = [(n, gc) for n, gc in (("host", x.host), ("client", x.client), ("client2", x.client2), ("client3", x.client3)) if alive(gc)]
            cap = {n: {"stack": stack(gc), "battle_state": auth(gc), "get_coop": coop(gc), "coop_dialog_info": dlg(gc)} for n, gc in live}
            if alive(x.host):
                cap["host needle deltas"] = counts(x.host, self.n_h)
                cap["HL"] = [ln.split("\t")[-1][:200] for ln in log(x.host)
                             if "coop-handshake" in ln or "[coop]" in ln or "coop-session" in ln][-15:]
            print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)

    def boot_miss(self, results, walls):
        print("EVIDENCE %s boot: %s\nFAIL %s boot: the boot did not reach the tactical map" % (self.rid, self.x.err, self.rid), flush=True)
        self.fails.append("boot")
        self.end(None, results, walls)

def baseline(r, x):
    """B0 (equal non-zero on both), SPLIT0 (host == client), HASH clean; a miss = setup failure"""
    hb, cb = auth(x.host), auth(x.client)
    x.b0, x.split0 = hb.get("battleId"), split(x.host)
    sc = split(x.client)
    hok, hev = hash_ok(x.host, x.client, r.rid + " baseline")
    ev = {"B0": [x.b0, cb.get("battleId")], "SPLIT0": [x.split0, sc], "T0": hb.get("turn"), "HASH": hev}
    print("EVIDENCE %s baseline: %s" % (r.rid, json.dumps(ev, sort_keys=True, default=str)), flush=True)
    if not (x.b0 and x.b0 == cb.get("battleId") and x.split0 and x.split0 == sc and hok):
        raise Stop("SETUP-FAILURE: baseline (B0 equal non-zero, SPLIT0 host == client, HASH clean) missed")

def pause(x):
    """PAUSE(host) within W_PAUSE of the leave -> (ok, the values at the pass or the timeout)"""
    h, seen = x.host, {}

    def ok():
        seen.update(stack=stack(h), battle=auth(h), dialog=dlg(h))
        b, d = seen["battle"], seen["dialog"]
        return (b.get("phase") == "Active" and b.get("peerAbsent") is True and b.get("battleId") == x.b0 and b.get("inBattle") is True
                and d.get("code") == 62 and d.get("backVisible") is False and seen["stack"][-2:] == [BS, CS])
    try:
        seen["s"] = wait("PAUSE(host)", ok, W_PAUSE)
        return True, seen
    except Stop as e:
        seen["wait"] = str(e)
        return False, seen

def in_flight(r, x):
    """client2 spawn, connect, hold_battle_ready {on: true}, rejoin_skirmish; wait <= W_FLIGHT for the host's phase Handshake, client2 held,
    OFFER +1; cell RL-2"""
    h = x.host
    x.client2 = c2 = GameClient("client2", 3, make_user_dir(TAG + "_client2"))
    c2.spawn(); c2.connect()
    ev = {"arm": pick(q(c2, {"cmd": "hold_battle_ready", "on": True}), ("ok", "armed", "held", "error"))}
    if ev["arm"].get("armed") is not True:
        raise Stop("SETUP-FAILURE: client2 hold_battle_ready {on: true} not armed: %s" % ev["arm"])
    try:
        rejoin_skirmish(c2, KEY)
    except Exception as e:
        ev["rejoin_skirmish"] = short(e, 300)  # a value: the wait below then times out
    seen = {}

    def flying():
        seen.update(phase=auth(h).get("phase"), hold=held(c2), OFFER=since(h, r.n_h, OFFER))
        return seen["phase"] == "Handshake" and seen["hold"].get("held") is True and len(seen["OFFER"]) == 1
    ev["in flight s"] = wait("host phase Handshake, client2 held, OFFER +1", flying, W_FLIGHT)
    act = [ln.split("\t")[-1][:160] for ln in log(c2) if CLIENT_ACTIVE in ln]
    ev.update(seen, CLIENT_ACTIVE=act, client2=[stack(c2), dlg(c2)], host=[stack(h), dlg(h), coop(h)])
    r.cell("RL-2", "GUARD", "the rejoin was in flight: host phase Handshake, client2 held, OFFER +1 reading battleId=%s, client2 CLIENT_ACTIVE "
           "+1" % x.b0, seen["phase"] == "Handshake" and seen["hold"].get("held") is True and len(seen["OFFER"]) == 1
           and ("battleId=%s," % x.b0) in seen["OFFER"][0] and len(act) == 1, ev)

def lost(r, x):
    """client2.kill(), the host observed for W at W_POLL; cell RL-3 (EVIDENCE: the loss path) -> the host log size at the kill"""
    h, c2 = x.host, x.client2
    n_k, kev = len(log(h)), {}
    try:
        c2.kill()
        kev["rc"] = c2.proc.returncode
    except Exception as e:
        raise Stop("client2.kill(): %s" % short(e, 300))
    tl, last, tw = [], None, time.time()
    while time.time() - tw < W:
        s = {"stack": stack(h), "battle": auth(h), "dialog": dlg(h), "coop": coop(h)}
        k = json.dumps(s, sort_keys=True, default=str)
        if k != last:
            last = k
            tl.append(dict(t=round(time.time() - tw, 2), **s))
        time.sleep(W_POLL)
    b, d, n = auth(h), dlg(h), counts(h, n_k)
    first = (tl[0]["battle"] if tl else {}).get("phase")
    path = "-2" if n["DROP"] >= 1 and n["FREEZE"] == 0 else ("-3" if n["FREEZE"] >= 1 and n["DROP"] == 0 else "unclear")
    ev = {"loss path": "%s (first poll phase %s; onClientDrop +%d, freeze +%d)" % (path, first, n["DROP"], n["FREEZE"]), "kill": kev,
          "needles since the kill": n, "LOST": since(h, n_k, LOST), "at W": {"battle": b, "dialog": d, "stack": stack(h)}, "timeline": tl}
    r.cell("RL-3", "FIX", "the pause is kept: at W host phase Active, peerAbsent true, battleId %s, inBattle true, dialog 62 backVisible false, "
           "LOST +1 (red today: Idle, battleId 0, peerAbsent false, LOST +0, T0-L)" % x.b0,
           b.get("phase") == "Active" and b.get("peerAbsent") is True and b.get("battleId") == x.b0 and b.get("inBattle") is True
           and d.get("code") == 62 and d.get("backVisible") is False and n["LOST"] == 1, ev)
    return n_k

def rejoin3(x, ev):
    """REJOIN(client3, KEY, skirmish) up to the resumeAck wait -> True when the host's resumeAck is true and peerAbsent false within W_ACK"""
    h = x.host
    x.client3 = c3 = GameClient("client3", 4, make_user_dir(TAG + "_client3"))
    c3.spawn(); c3.connect()
    t0, ev["c3 on 52 s"] = time.time(), None
    try:
        rejoin_skirmish(c3, KEY)
    except Exception as e:
        ev["rejoin_skirmish"] = short(e, 300)  # a join_tcp exception is a value; the wait then times out

    def acked():
        if top(h) == PROFILE:
            ev.setdefault("profile_ok", []).append([round(time.time() - t0, 2), q(h, {"cmd": "profile_ok"}).get("ok")])
        if ev["c3 on 52 s"] is None and dlg(c3).get("code") == 52:
            ev["c3 on 52 s"] = round(time.time() - t0, 2)
        return coop(h).get("resumeAck") is True and auth(h).get("peerAbsent") is False
    try:
        ev["ack s"] = wait("host resumeAck true and peerAbsent false", acked, W_ACK)
        return True
    except Stop as e:
        ev["ack wait"] = str(e)
        ev["at the timeout"] = {"host": [coop(h), auth(h), dlg(h), stack(h)], "client3": [stack(c3), dlg(c3)]}
        return False

def resume(x, ev):
    """the host's 62 shows RESUME (the dialog recorded), press_back_when_shown(codes=(62,)) -> True when pressed"""
    h = x.host

    def shown():
        if top(h) == PROFILE:
            ev.setdefault("profile_ok", []).append(["resume", q(h, {"cmd": "profile_ok"}).get("ok")])
        d = dlg(h)
        if top(h) == CS and d.get("code") == 62 and d.get("backVisible") is True:
            ev["RESUME dialog"] = d
            return True
    try:
        wait("host 62 shows RESUME", shown, 60.0)
        ev["RESUME"] = session.press_back_when_shown(h, "host RESUME", codes=(62,))
    except Exception as e:
        ev["RESUME"] = {"error": short(e, 300)}
    return (ev.get("RESUME") or {}).get("ok") is True

def row_rl(x, results, walls):
    r = Row("RL", ["RL-%d" % i for i in range(1, 6)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h = x.host
    try:
        baseline(r, x)
        r.n_h = len(log(h))
        drop_client_mid_battle(h, x.client)
        ok, pv = pause(x)
        r.cell("RL-1", "GUARD", "PAUSE(host) within %.0f s of the leave" % W_PAUSE, ok, pv)
        if not ok:
            raise Stop("PAUSE(host) not reached within %.0f s" % W_PAUSE)
        in_flight(r, x)
        n_k = lost(r, x)
        ev = {}
        acked = rejoin3(x, ev)
        c3, n = x.client3, counts(h, n_k)
        resumed = acked and resume(x, ev)
        tops = False
        try:
            if resumed:
                ev["tops s"], tops = wait("both tops BattlescapeState", lambda: top(h) == BS and top(c3) == BS, 60.0), True
        except Stop as e:
            ev["tops wait"] = str(e)
        hb, cb = auth(h), auth(c3)
        ev.update(OFFER=since(h, n_k, OFFER), GUARD=since(h, n_k, GUARD), needles=n, host=hb, client3=cb, tops=[top(h), top(c3)])
        r.cell("RL-4", "FIX", "client3's rejoin: OFFER +1 more, GUARD +0, RESUME within W_ACK %.0f s, both tops BattlescapeState, phase Active, "
               "peerAbsent false, battleId %s on both (red today: GUARD +1, client3 on 52, the wait times out, T0-L)" % (W_ACK, x.b0),
               n["OFFER"] == 1 and n["GUARD"] == 0 and resumed and tops and hb.get("phase") == cb.get("phase") == "Active"
               and hb.get("peerAbsent") is False and cb.get("peerAbsent") is False and hb.get("battleId") == cb.get("battleId") == x.b0, ev)
        if not (resumed and tops):
            raise Stop("REJOIN: no RESUME or the tops wait failed (resumeAck wait: %s)" % ev.get("ack wait", "passed"))
        sh, sc = split(h), split(c3)
        hok, hev = hash_ok(h, c3, "RL after RESUME")
        r.cell("RL-5", "FIX", "SPLIT(host) == SPLIT(client3) == SPLIT0 and HASH(host, client3)", sh == sc == x.split0 and hok,
               {"host": sh, "client3": sc, "SPLIT0": x.split0, "HASH": hev})
    except Exception as e:  # Stop, or a probe / spawn that raised: the row ends here
        r.stop(e)
    r.end("RL-6", results, walls)

def boot(tag):
    """boot L: host and client spawn, connect, start_skirmish_battle(host, client, KEY) (both on BattlescapeState)"""
    x = SimpleNamespace(tag=tag, host=None, client=None, client2=None, client3=None, err=None, b0=None, split0=None)
    try:
        x.host, x.client = GameClient("host", 1, make_user_dir(tag + "_host")), GameClient("client", 2, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        start_skirmish_battle(x.host, x.client, KEY)
    except Exception as e:
        x.err = short(e, 600)
    return x

def shut(x):
    """every machine of the boot (the killed client2 is already reaped) -> the shutdown failures"""
    failed = []
    for gc in (x.client3, x.client2, x.client, x.host):
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown()
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (x.tag, gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, gc.name))
    return failed

def main():
    t0, results, walls, x = time.time(), {}, {}, boot(TAG)
    walls[TAG + " boot"] = round(time.time() - t0, 1)
    row_rl(x, results, walls)
    failed = shut(x) + [rid for rid in ("RL",) if not results.get(rid)]
    walls[TAG] = round(time.time() - t0, 1)
    print("\ntest_rejoin_lost_restream: %d/1 rows passed (fail=%s) walls %s in %.1fs" % (sum(1 for v in results.values() if v), failed,
                                                                                         json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
