"""R4-L2 stage S-C (spec rewrite/prompts/r4l2_campaign_rejoin.md (f) rows X1, X2, QL2-3 a, QL2-5 a; TASK 0
rewrite/r4l2-task0/sc/CONSTANTS.md): a partner lost on a failed send mid-battle leaves a pause no rejoin can resume. The TEST-ONLY host lever
force_send_failure (L1-L6) makes the host's TCP thread take its real send-failure branch (onConnect -3, the partner's socket closed). The -3
arm never calls disconnectTCP() for a live battle: a campaign host freezes with peerAbsent false and RESUME shown at once,
so offerRejoinBattle()'s guard refuses the rejoin (GUARD +1); a skirmish host gets CoopState(440), which pops the battle and stops serving
(TASK 0 T0-X1 / T0-X2, 2/2 each).
  Boot X1 (key "48602", shared_fixture.bring_up("w2r4l2_x1", (1, 2, 48602)) + bring_up_shared_mixed_battle(js, {0: 0, 1: 1}), client2 dir
  w2r4l2_x1_client2): row X1, SHARED. Cells: X1-1 GUARD the link broke on the host's send (lever armed true, the armed line +1, the client on
  21 within 15 s); X1-2 FIX the pause at W (phase Active, peerAbsent true, battleId B0, dialog 62 backVisible false, SEND_LOST +1, DROP +1);
  X1-3 FIX client2's rejoin (OFFER +1, RESUME within W_ACK, both tops BattlescapeState, phase Active, peerAbsent false, battleId B0 on both,
  client2 CLIENT_ACTIVE +1); X1-4 FIX SPLIT(host) == SPLIT(client2) == SPLIT0 and HASH(host, client2); X1-5 GUARD CRASH 0.
  Boot X2 (key "48603", w2r4l2_x2_host / _client / _client2): row X2, skirmish (start_skirmish_battle, rejoin_skirmish). Cells as X1, and X2-2
  also: no host poll in W shows CoopState 440 or a stack without BattlescapeState.
Definitions (spec (f)): POLL 0.25 s; W 15 s, the host observed at 0.2 s from the arm until W after the client's 21 (every poll's stack
judged); W_ACK 30 s (CONSTANTS: max(30 s, 3 x t_world 2.57 s)); SPLIT = sorted (unit id, coop) of faction 0, not isOut; HASH = wait_host_idle +
assert_hash_clean(full) + desyncSeen false on both; REJOIN = a fresh client2 on its own dir (campaign: join_tcp from the main menu; skirmish:
rejoin_skirmish; an exception is a value), wait <= W_ACK for the host's resumeAck true AND peerAbsent false (profile_ok on a top host Profile,
client2's only once its load wait 52 is gone, R-L2-A-2), press_back_when_shown(host, codes=(62,)), both tops BattlescapeState <= 60 s.
battle_state is probed only with a BattlescapeState on the stack or no battle in the world; the dropped client is probed with
get_state / coop_dialog_info only until it is at the main menu. Needles = host log since the row's baseline (client2: its own log). A WAIT
that times out ends the row (later cells "not reached"), except REJOIN's waits: X-3 is evaluated with the values at the timeout. EVIDENCE
before each verdict; a failed row prints ONE CAPTURE line; every row runs after a failure; ONE run; exit 0 iff every cell passes, else 2.
Red (S-C commit 1): X1 FAIL on X1-2, X1-3, X1-4 "not reached" (X1-1, X1-5 PASS); X2 FAIL on X2-2, X2-3, X2-4 "not reached" (X2-1, X2-5 PASS).
"""
import json
import os
import sys
import time
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
from test_skirmish_rejoin_battle import rejoin_skirmish, start_skirmish_battle  # noqa: E402

POLL, W, W_POLL, W_21, W_ACK = 0.25, 15.0, 0.2, 15.0, 30.0
KEY_X1, KEY_X2 = "48602", "48603"
BS, CS, MENU, PROFILE = "BattlescapeState", "CoopState", "MainMenuState", "Profile"
OFFER, GUARD = "rejoin battle_offer sent (battleId=", "offerRejoinBattle() called while the battle is not "
ARMED, SEND_LOST = "[coop-test] force_send_failure: armed", "the partner was lost on a failed send during the battle"
FREEZE, DROP, CLIENT_ACTIVE = "[coop-session] freeze (lobbyMode=", "[coop-session] onClientDrop", "CLIENT phase Active (battleId="
NEEDLES = {"OFFER": OFFER, "GUARD": GUARD, "ARMED": ARMED, "SEND_LOST": SEND_LOST, "FREEZE": FREEZE, "DROP": DROP}

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
    return pick(q(gc, {"cmd": "get_coop"}), ("onConnect", "coopSession", "lobbyMode", "resumeAck", "coopDialog", "inBattle", "serverOwner",
                                             "error"))

def dlg(gc):
    return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backVisible", "error"))

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
            live = [(n, gc) for n, gc in (("host", x.host), ("client", x.client), ("client2", x.client2)) if alive(gc)]
            cap = {n: {"stack": stack(gc), "get_coop": coop(gc), "coop_dialog_info": dlg(gc)} for n, gc in live}
            for n, gc in live:  # the dropped client: battle_state only once it is at the main menu
                cap[n]["battle_state"] = auth(gc) if gc is not x.client or top(gc) == MENU else {"skipped": "the dropped client"}
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
    """B0 (equal non-zero on both), SPLIT0 (host == client), HASH clean; a miss = FIXTURE-STOP"""
    hb, cb = auth(x.host), auth(x.client)
    x.b0, x.split0 = hb.get("battleId"), split(x.host)
    sc = split(x.client)
    hok, hev = hash_ok(x.host, x.client, r.rid + " baseline")
    ev = {"B0": [x.b0, cb.get("battleId")], "SPLIT0": [x.split0, sc], "T0": hb.get("turn"), "HASH": hev}
    print("EVIDENCE %s baseline: %s" % (r.rid, json.dumps(ev, sort_keys=True, default=str)), flush=True)
    if not (x.b0 and x.b0 == cb.get("battleId") and x.split0 and x.split0 == sc and hok):
        raise Stop("FIXTURE-STOP: baseline (B0 equal non-zero, SPLIT0 host == client, HASH clean) missed")

def lever(r, x):
    """host force_send_failure; the host (stack, dialog, get_coop) and the client (dialog) polled at W_POLL from the arm until W after the
    client's 21 (or W_21 without one), battle_state read once, at W (no probe while a CoopState(440) may pop the battle, F10980); cell
    <rid>-1 -> the host's timeline (state changes) and its values at W"""
    h, c, rid = x.host, x.client, r.rid
    arm = pick(q(h, {"cmd": "force_send_failure"}), ("ok", "armed", "error"))
    ta, t21, tl, last = time.time(), None, [], None
    while time.time() - ta < (W_21 if t21 is None else t21 + W):
        t = round(time.time() - ta, 2)
        s = {"stack": stack(h), "dialog": dlg(h), "coop": coop(h)}
        k = json.dumps(s, sort_keys=True, default=str)
        if k != last:
            last = k
            tl.append(dict(t=t, **s))
        if t21 is None and dlg(c).get("code") == 21:
            t21 = t
            x.c21 = {"t": t21, "dialog": dlg(c), "stack": stack(c)}
        time.sleep(W_POLL)
    seen = {"stack": stack(h), "battle": auth(h), "dialog": dlg(h), "coop": coop(h)}
    n = counts(h, r.n_h)
    r.cell(rid + "-1", "GUARD", "the link broke on the host's send: the lever armed true, host \"%s\" +1, the client on 21 within %.0f s"
           % (ARMED, W_21), arm.get("armed") is True and n["ARMED"] == 1 and t21 is not None,
           {"arm": arm, "ARMED": since(h, r.n_h, ARMED), "client 21": getattr(x, "c21", None) or {"stack": stack(c), "dialog": dlg(c)}})
    if t21 is None:
        raise Stop("WAIT the client's dialog 21: timed out after %.0f s" % W_21)
    return tl, seen

def the_pause(r, x, tl, s, skirmish):
    """cell <rid>-2: the host's values at W (+ X2: every poll in W kept a BattlescapeState and never showed 440)"""
    h, rid, n = x.host, r.rid, counts(x.host, r.n_h)
    b, d = s.get("battle") or {}, s.get("dialog") or {}
    bad = [e["t"] for e in tl if BS not in (e.get("stack") or []) or (e.get("dialog") or {}).get("code") == 440]
    path = ("SEND_LOST, onClientDrop (the canonical drop)" if n["SEND_LOST"] and n["DROP"] else
            "-3 without disconnectTCP(): %s" % ("CoopState(440)" if bad else "freeze +%d, onClientDrop +%d" % (n["FREEZE"], n["DROP"])))
    ok = (b.get("phase") == "Active" and b.get("peerAbsent") is True and b.get("battleId") == x.b0 and d.get("code") == 62
          and d.get("backVisible") is False and n["SEND_LOST"] == 1 and n["DROP"] == 1 and (not skirmish or not bad))
    r.cell(rid + "-2", "FIX", "the pause: at W host phase Active, peerAbsent true, battleId %s, dialog 62 backVisible false, SEND_LOST +1, DROP +1%s "
           "(red today: %s)" % (x.b0, ", no poll with CoopState 440 or without BattlescapeState" if skirmish else "",
                                "a CoopState 440 over no battle, T0-X2" if skirmish else "peerAbsent false, 62 RESUME shown, FREEZE +1, "
                                "DROP +0, SEND_LOST +0, T0-X1"), ok,
           {"loss path": path, "at W": s, "needles": n, "polls without BattlescapeState or with 440 (t)": bad, "timeline": tl})

def client_back(x):
    """the dropped client acknowledges its 21 (coop_dialog_back) and reaches the main menu <= 60 s"""
    c = x.client
    ev = {"coop_dialog_back": q(c, {"cmd": "coop_dialog_back"})}
    ev["MainMenuState s"] = wait("the client's top MainMenuState", lambda: top(c) == MENU, 60.0)
    print("EVIDENCE %s client back: %s" % (x.rid, json.dumps(ev, sort_keys=True, default=str)), flush=True)

def rejoin(x, key, skirmish, ev):
    """REJOIN(client2, key) up to the resumeAck wait -> True when the host's resumeAck is true and peerAbsent false within W_ACK"""
    h = x.host
    x.client2 = c2 = GameClient("client2", 3, make_user_dir(x.tag + "_client2"))
    c2.spawn(); c2.connect()
    t0 = time.time()
    if skirmish:
        try:
            rejoin_skirmish(c2, key)
            ev["rejoin_skirmish"] = "ok"
        except Exception as e:
            ev["rejoin_skirmish"] = short(e, 300)  # a value: the wait then times out
    else:
        ev["join_tcp"] = q(c2, {"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": "ClientPlayer"})

    def acked():
        for gc in (h, c2):  # client2's Profile only once its load wait 52 is gone
            if top(gc) == PROFILE and (gc is h or dlg(c2).get("code") != 52):
                ev.setdefault("profile_ok", []).append([gc.name, round(time.time() - t0, 2), q(gc, {"cmd": "profile_ok"}).get("ok")])
        return coop(h).get("resumeAck") is True and auth(h).get("peerAbsent") is False
    try:
        ev["ack s"] = wait("host resumeAck true and peerAbsent false", acked, W_ACK)
        return True
    except Stop as e:
        ev["ack wait"] = str(e)
        ev["at the timeout"] = {"host": [coop(h), auth(h), dlg(h), stack(h)], "client2": [stack(c2), dlg(c2)]}
        return False

def resume(x, ev):
    """the host's 62 shows RESUME (the dialog recorded), press_back_when_shown(codes=(62,)) -> True when pressed"""
    h = x.host

    def shown():
        if top(h) == PROFILE:
            ev.setdefault("profile_ok", []).append([h.name, "resume", q(h, {"cmd": "profile_ok"}).get("ok")])
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

def rejoin_cells(r, x, key, skirmish):
    """REJOIN + cells <rid>-3 (the rejoin) and <rid>-4 (SPLIT + HASH)"""
    h, rid, ev = x.host, r.rid, {}
    acked = rejoin(x, key, skirmish, ev)
    c2 = x.client2
    resumed, tops = acked and resume(x, ev), False
    try:
        if resumed:
            ev["tops s"], tops = wait("both tops BattlescapeState", lambda: top(h) == BS and top(c2) == BS, 60.0), True
    except Stop as e:
        ev["tops wait"] = str(e)
    hb, cb, n = auth(h), auth(c2), counts(h, r.n_h)
    offer, act = since(h, r.n_h, OFFER), [ln.split("\t")[-1][:160] for ln in log(c2) if CLIENT_ACTIVE in ln]
    ev.update(OFFER=offer, GUARD=since(h, r.n_h, GUARD), needles=n, host=hb, client2=cb, tops=[stack(h), stack(c2)], CLIENT_ACTIVE=act)
    r.cell(rid + "-3", "FIX", "client2's rejoin: OFFER +1 reading battleId=%s, RESUME within W_ACK %.0f s, both tops BattlescapeState, phase Active, "
           "peerAbsent false, battleId %s on both, client2 CLIENT_ACTIVE +1 (red today: %s)" % (x.b0, W_ACK, x.b0, "the join refused, the host "
           "not serving (T0-X2)" if skirmish else "GUARD +1, OFFER +0, client2 on 68 (T0-X1)"),
           len(offer) == 1 and ("battleId=%s," % x.b0) in offer[0] and resumed and tops and hb.get("phase") == cb.get("phase") == "Active"
           and hb.get("peerAbsent") is False and cb.get("peerAbsent") is False and hb.get("battleId") == cb.get("battleId") == x.b0
           and len(act) == 1, ev)
    if not (resumed and tops):
        raise Stop("REJOIN: no RESUME or the tops wait failed (resumeAck wait: %s)" % ev.get("ack wait", "passed"))
    sh, sc = split(h), split(c2)
    hok, hev = hash_ok(h, c2, rid + " after RESUME")
    r.cell(rid + "-4", "FIX", "SPLIT(host) == SPLIT(client2) == SPLIT0 and HASH(host, client2)", sh == sc == x.split0 and hok,
           {"host": sh, "client2": sc, "SPLIT0": x.split0, "HASH": hev})

def row_x(x, results, walls, key, skirmish):
    r = Row(x.rid, ["%s-%d" % (x.rid, i) for i in range(1, 5)], x)
    if x.err:
        return r.boot_miss(results, walls)
    try:
        baseline(r, x)
        r.n_h = len(log(x.host))
        tl, s = lever(r, x)
        the_pause(r, x, tl, s, skirmish)
        client_back(x)
        rejoin_cells(r, x, key, skirmish)
    except Exception as e:  # Stop, or a probe / spawn that raised: the row ends here
        r.stop(e)
    r.end(x.rid + "-5", results, walls)

def new_x(rid, tag):
    return SimpleNamespace(rid=rid, tag=tag, js=None, host=None, client=None, client2=None, err=None, b0=None, split0=None, c21=None)

def boot_x1(tag):
    """boot X1: shared_fixture.bring_up + bring_up_shared_mixed_battle(js, {0: 0, 1: 1}) (squad[1] owned by seat 1)"""
    x = new_x("X1", tag)
    try:
        x.js = shared_fixture.bring_up(tag, (1, 2, int(KEY_X1)))
        x.host, x.client = x.js.host, x.js.client
        session.bring_up_shared_mixed_battle(x.js, {0: 0, 1: 1})
    except Exception as e:
        x.err = short(e, 600)
    return x

def boot_x2(tag):
    """boot X2: host and client spawn, connect, start_skirmish_battle(host, client, KEY_X2) (both on BattlescapeState)"""
    x = new_x("X2", tag)
    try:
        x.host, x.client = GameClient("host", 1, make_user_dir(tag + "_host")), GameClient("client", 2, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        start_skirmish_battle(x.host, x.client, KEY_X2)
    except Exception as e:
        x.err = short(e, 600)
    return x

def shut(x):
    """every machine of the boot -> the shutdown failures"""
    failed = []
    for gc in (x.client2, x.client, x.host):
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown()
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (x.tag, gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, gc.name))
    return failed

def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for tag, boot, key, skirmish in (("w2r4l2_x1", boot_x1, KEY_X1, False), ("w2r4l2_x2", boot_x2, KEY_X2, True)):
        tb = time.time()
        x = boot(tag)
        walls[tag + " boot"] = round(time.time() - tb, 1)
        row_x(x, results, walls, key, skirmish)
        failed += shut(x)
        walls[tag] = round(time.time() - tb, 1)
    failed += [rid for rid in ("X1", "X2") if not results.get(rid)]
    print("\ntest_rejoin_send_failure: %d/2 rows passed (fail=%s) walls %s in %.1fs" % (sum(1 for rid in ("X1", "X2") if results.get(rid)),
                                                                                       failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
