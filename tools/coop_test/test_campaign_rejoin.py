"""R4-L2 stage S-A (spec rewrite/prompts/r4l2_campaign_rejoin.md (f) rows CR1, CR3, QL2-1 a, QL2-5 a; TASK 0
rewrite/r4l2-task0/sa/CONSTANTS.md): a player who leaves a co-op CAMPAIGN battle and rejoins is never offered the battle. The host's
resume_ack battle branch hands the campaign rejoin to offerResumedBattle(), which refuses a live pause: REFUSED +1,
resumeAck never true, the host waits on dialog 62 and the rejoiner on 68 for good (TASK 0 T0-1 / T0-2).
  Boot H (key "48597", shared_fixture.bring_up("w2r4l2_h", (1, 2, 48597)) + bring_up_shared_mixed_battle(js, {0: 0, 1: 1}), client2
  dir w2r4l2_h_client2): row CR1, SHARED, the client leaves gracefully (disconnect_to_menu), a fresh client2 rejoins. Cells: CR1-1 GUARD
  PAUSE, peerLeftByChoice true, title "has left the battle"; CR1-2 GUARD phase 1 served (SHARED_STREAM +1, a client2 poll on 68);
  CR1-3 FIX the live offer (OFFER +1 reading battleId=B0, REFUSED +0); CR1-4 FIX RESUME offered ("All players connected", within
  W_ACK) and pressed; CR1-5 FIX the same battle on both; CR1-6 FIX SPLIT; CR1-7 FIX HASH; CR1-8 FIX one client2 walk of squad[1]
  applied (walk_far, R-L2-A-1), HASH again; CR1-9 GUARD CRASH 0 and client2 zero-disk.
  Boot C (key "48598", w2r4l2_c_host / _client): row CR3, SEPARATE, the host leaves (disconnect_to_menu; aud-I93, MJ-2). Cells: CR3-1
  GUARD the client on 21 "Server connection lost", backVisible, top CoopState within 120 s; CR3-2 GUARD still CoopState 8 s later;
  CR3-3 GUARD OK -> MainMenuState within 60 s, has_save false; CR3-4 GUARD CRASH 0 and client zero-disk.
Definitions (spec (f)): POLL 0.25 s; W_ACK = WATCH_CAP_S (RV-U13 S-D; was max(30 s, 3 x t_world 6.41 s)); PAUSE(host) within 30 s of the leave:
phase Active, peerAbsent true, battleId B0, inBattle true, dialog 62 backVisible false, stack [..., BattlescapeState, CoopState];
SPLIT = sorted (unit id, coop) of faction 0, not isOut; HASH = wait_host_idle + assert_hash_clean(full) + desyncSeen false on both;
REJOIN = a fresh client2 on its own dir, join_tcp from the main menu, wait <= W_ACK for the host's resumeAck true AND peerAbsent false
(profile_ok only on a top-state Profile; client2's only once its load wait 52 is gone, R-L2-A-2), press_back_when_shown(host, codes=(62,)),
both tops BattlescapeState <= 60 s. battle_state is probed only with a BattlescapeState on the stack or no battle in the world
(F10980: the probe dereferences a stale _battleState after a BattlescapeState pop and kills the process). Needles = host log since the
row's baseline (client2: its own log). A WAIT that times out ends the row (later cells "not reached"), except REJOIN's resumeAck wait:
the OFFER / RESUME cells are evaluated with the values at the timeout. EVIDENCE before each verdict; a failed row prints ONE CAPTURE
line; every row runs after a failure; ONE run; exit 0 iff every cell passes, else 2.
Red (S-A commit 1): CR1 FAIL on CR1-3, CR1-4 and CR1-5..CR1-8 "not reached" (CR1-1, CR1-2, CR1-9 PASS); CR3 PASS.
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

WATCH_CAP_S = 135  # REJOIN's wait ends at resumeAck; >= max(120, 2.5 x the loaded rejoin), F11192
POLL, W_ACK, W_PAUSE = 0.25, WATCH_CAP_S, 30.0
KEY_H, KEY_C = "48597", "48598"
BS, CS, MENU, PROFILE = "BattlescapeState", "CoopState", "MainMenuState", "Profile"
OFFER, REFUSED = "rejoin battle_offer sent (battleId=", "offerResumedBattle() called outside a disk resume"
GUARD, RELEASE = "offerRejoinBattle() called while the battle is not ", "restream adopted; released the client hold"
RESTASH = "F3 battle resume: stashed geoscape-only coop_geoscape_return"
SHARED_STREAM, CLIENT_ACTIVE = "[coop-shared] streaming authoritative world to client (", "CLIENT phase Active (battleId="
NEEDLES = {"OFFER": OFFER, "REFUSED": REFUSED, "GUARD": GUARD, "RELEASE": RELEASE, "RESTASH": RESTASH, "SHARED_STREAM": SHARED_STREAM}

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

def pos(gc, uid):
    return next(((u.get("x"), u.get("y"), u.get("z")) for u in bs_raw(gc).get("units") or [] if u.get("id") == uid), None)

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

    def end(self, crash_cid, zd_dir, results, walls):
        """the CRASH + zero-disk cell (every case), ONE CAPTURE line when a cell failed, the row verdict"""
        if crash_cid:
            new = sorted(session._crash_log_snapshot() - self.cr0)
            try:
                zd = "never started" if zd_dir is None else (session.assert_client_zero_disk(zd_dir) or "clean")
            except AssertionError as e:
                zd = short(e, 300)
            self.cell(crash_cid, "GUARD", "CRASH 0 (no new crash_*.log in this lane's crash folder since the row's baseline) and zero-disk "
                      "on %s as it stands" % (os.path.basename(zd_dir) if zd_dir else "the rejoiner's dir"), not new
                      and zd in ("clean", "never started"), {"crash": new, "zero-disk": zd})
        x, walls[self.rid] = self.x, round(time.time() - self.t0, 1)
        if self.fails:
            live = [(n, gc) for n, gc in (("host", x.host), ("client", x.client), ("client2", x.client2)) if alive(gc)]
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
        self.end(None, None, results, walls)

def baseline(r, x, other):
    """B0 (equal non-zero on both), SPLIT0 (host == other), T0, HASH clean; a miss = setup failure"""
    hb, ob = auth(x.host), auth(other)
    x.b0, x.t0, x.split0 = hb.get("battleId"), hb.get("turn"), split(x.host)
    so = split(other)
    hok, hev = hash_ok(x.host, other, r.rid + " baseline")
    ev = {"B0": [x.b0, ob.get("battleId")], "SPLIT0": [x.split0, so], "T0": x.t0, "HASH": hev}
    print("EVIDENCE %s baseline: %s" % (r.rid, json.dumps(ev, sort_keys=True, default=str)), flush=True)
    if not (x.b0 and x.b0 == ob.get("battleId") and x.split0 and x.split0 == so and hok):
        raise Stop("SETUP-FAILURE: baseline (B0 equal non-zero, SPLIT0 host == %s, HASH clean) missed" % other.name)

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

def rejoin(x, key, ev):
    """REJOIN(client2, key, campaign) up to the resumeAck wait -> True when the host's resumeAck is true and peerAbsent false within
    W_ACK; ev collects the values (a join_tcp exception is a value)"""
    h = x.host
    x.client2 = c2 = GameClient("client2", 3, make_user_dir(x.tag + "_client2"))
    c2.spawn(); c2.connect()
    t0, ev["c2 on 68 s"] = time.time(), None
    ev["join_tcp"] = q(c2, {"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": "ClientPlayer"})

    def acked():
        for gc in (h, c2):  # a press while client2's world loads pops the LoadGameState pushed over its Profile
            if top(gc) == PROFILE and (gc is h or dlg(c2).get("code") != 52):
                ev.setdefault("profile_ok", []).append([gc.name, round(time.time() - t0, 2), q(gc, {"cmd": "profile_ok"}).get("ok")])
        if ev["c2 on 68 s"] is None and dlg(c2).get("code") == 68:
            ev["c2 on 68 s"] = round(time.time() - t0, 2)
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

def walk_far(h, c2, uid, wev):
    """client2 walks uid to the free tile at radius 1-3 (its level, one down, one up) with the LARGEST minimum distance to
    any living non-player, farthest first, the pathfinder judging reachability (no iseq = unroutable) -> the host's lastWalk ({}: none)"""
    st = session.battle_state(h)
    u, npc = session.units_by_id(st)[uid], session.living_non_players(st)
    occ, prev = {session.pos_of(v) for v in st["units"] if not v.get("isOut")}, session.walk_action_id(h)
    ring = sorted((-(session.min_dist_to(npc, t) or 0.0), t) for r in (1, 2, 3) for dz in (0, -1, 1) for dx in range(-r, r + 1)
                  for dy in range(-r, r + 1) for t in [(u["x"] + dx, u["y"] + dy, u["z"] + dz)] if max(abs(dx), abs(dy)) == r and t[2] >= 0)
    for nd, t in ring:
        if session.tile_is_open_ground(h, t[0], t[1], t[2], occ) and session.send_walk(c2, uid, t).get("iseq"):
            wev.update(dest=t, minDist=round(-nd, 2), npcs=len(npc))
            session.wait_walk_settled(h, c2, prev)
            session.settle_reveal(h, c2)
            return session.last_walk(h)
    return {}

def rejoin_tail(r, x, rid, key, actor, cell2):
    """REJOIN + cells <rid>-2 (cell2(ev, n), the row's own) and <rid>-3 .. <rid>-8 (spec (f) CR1-3 .. CR1-8)"""
    h, n_h, ev = x.host, r.n_h, {}
    acked = rejoin(x, key, ev)
    c2 = x.client2
    n = counts(h, n_h)
    cell2(ev, n)
    offer = since(h, n_h, OFFER)
    r.cell(rid + "-3", "FIX", "the live offer: OFFER +1 reading battleId=%s, REFUSED +0 (red today: OFFER +0, REFUSED +1, T0-1 / T0-2)" % x.b0,
           len(offer) == 1 and ("battleId=%s," % x.b0) in offer[0] and n["REFUSED"] == 0,
           {"OFFER": offer, "REFUSED": since(h, n_h, REFUSED), "GUARD": since(h, n_h, GUARD), "needles": n})
    resumed = acked and resume(x, ev)
    title = (ev.get("RESUME dialog") or {}).get("title")
    r.cell(rid + "-4", "FIX", "RESUME offered: host resumeAck true and peerAbsent false within W_ACK %.0f s, dialog 62 backVisible true titled "
           "\"All players connected\", RESUME pressed (red today: resumeAck false at W_ACK)" % W_ACK,
           resumed and title == "All players connected", ev)
    if not resumed:
        raise Stop("REJOIN: no RESUME (resumeAck wait: %s)" % ev.get("ack wait", "passed"))
    wait("both tops BattlescapeState", lambda: top(h) == BS and top(c2) == BS, 60.0)
    hb, cb = auth(h), auth(c2)
    act = [ln for ln in log(c2) if CLIENT_ACTIVE in ln]
    r.cell(rid + "-5", "FIX", "the same battle on both: tops BattlescapeState, phase Active, peerAbsent false, battleId == B0 %s, client2 "
           "CLIENT_ACTIVE +1, host turn == T0 %s" % (x.b0, x.t0),
           top(h) == BS and top(c2) == BS and hb.get("phase") == cb.get("phase") == "Active" and hb.get("peerAbsent") is False
           and cb.get("peerAbsent") is False and hb.get("battleId") == cb.get("battleId") == x.b0 and len(act) == 1
           and hb.get("turn") == x.t0, {"host": hb, "client2": cb, "CLIENT_ACTIVE": [a.split("\t")[-1][:160] for a in act]})
    sh, sc = split(h), split(c2)
    r.cell(rid + "-6", "FIX", "SPLIT(host) == SPLIT(client2) == SPLIT0", sh == sc == x.split0, {"host": sh, "client2": sc, "SPLIT0": x.split0})
    ok, hev = hash_ok(h, c2, rid + " after RESUME")
    r.cell(rid + "-7", "FIX", "HASH(host, client2)", ok, hev)
    wev = {"actor": actor, "start": pos(h, actor)}
    try:
        hw = walk_far(h, c2, actor, wev)
    except Exception as e:
        hw, wev["error"] = {}, short(e, 300)
    steps = hw.get("steps") or []
    last, halted = (steps[-1].get("to") if steps else None), bool((hw.get("restate") or {}).get("halted"))
    wev.update(steps=len(steps), last=last, halted=halted, host=pos(h, actor), client2=pos(c2, actor))
    hok2, wev["HASH"] = hash_ok(h, c2, rid + " after the walk")
    r.cell(rid + "-8", "FIX", "one client2 walk of unit %s applied: >= 1 step, the final tile equal on both and != the start, == the last "
           "step unless a reaction / spotting halted it (R-L2-A-1), HASH again" % actor, bool(steps) and wev["host"] is not None
           and wev["host"] == wev["client2"] != wev["start"] and (halted or wev["host"] == (last["x"], last["y"], last["z"])) and hok2, wev)

def row_cr1(x, results, walls):
    r = Row("CR1", ["CR1-%d" % i for i in range(1, 9)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        baseline(r, x, c)
        r.n_h = len(log(h))
        print("EVIDENCE CR1 leave: %s" % json.dumps(q(c, {"cmd": "disconnect_to_menu"}), default=str), flush=True)
        wait("client top MainMenuState", lambda: top(c) == MENU, 60.0)
        ok, pv = pause(x)
        title = (pv.get("dialog") or {}).get("title") or ""
        r.cell("CR1-1", "GUARD", "PAUSE(host), peerLeftByChoice true, the title contains \"has left the battle\"",
               ok and (pv.get("battle") or {}).get("peerLeftByChoice") is True and "has left the battle" in title, pv)
        if not ok:
            raise Stop("PAUSE(host) not reached within %.0f s" % W_PAUSE)

        def cell2(ev, n):
            r.cell("CR1-2", "GUARD", "phase 1 served: SHARED_STREAM +1 and a client2 poll on dialog 68",
                   n["SHARED_STREAM"] == 1 and ev.get("c2 on 68 s") is not None,
                   {"SHARED_STREAM": since(h, r.n_h, SHARED_STREAM), "c2 on 68 s": ev.get("c2 on 68 s"), "join_tcp": ev.get("join_tcp")})
        rejoin_tail(r, x, "CR1", KEY_H, x.squad[1], cell2)
    except Exception as e:  # Stop, or a probe / spawn that raised: the row ends here
        r.stop(e)
    r.end("CR1-9", x.client2.user_dir if x.client2 is not None else None, results, walls)

def row_cr3(x, results, walls):
    r = Row("CR3", ["CR3-1", "CR3-2", "CR3-3"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        print("EVIDENCE CR3 host leave: %s" % json.dumps(q(h, {"cmd": "disconnect_to_menu"}), default=str), flush=True)
        seen = {}

        def told():  # the dialog first, then the stack, so the stack judged is never older than the dialog
            seen["dialog"] = dlg(c)
            seen["stack"] = stack(c)
            return seen["dialog"].get("code") == 21
        try:
            seen["s"] = wait("the client's dialog 21", told, 120.0)
        except Stop as e:
            seen["wait"] = str(e)
        d = seen.get("dialog") or {}
        r.cell("CR3-1", "GUARD", "within 120 s the client's dialog 21 titled \"Server connection lost\", backVisible true, top CoopState",
               d.get("code") == 21 and d.get("title") == "Server connection lost" and d.get("backVisible") is True
               and seen.get("stack", [])[-1:] == [CS], seen)
        if "wait" in seen:
            raise Stop(seen["wait"])
        time.sleep(8.0)
        st = stack(c)
        r.cell("CR3-2", "GUARD", "8 s later the client's top is still CoopState (no solo play, aud-I93)", st[-1:] == [CS], st)
        ev = {"coop_dialog_back": q(c, {"cmd": "coop_dialog_back"})}
        try:
            ev["MainMenuState s"] = wait("the client's top MainMenuState", lambda: top(c) == MENU, 60.0)
        except Stop as e:
            ev["wait"] = str(e)
        ev.update(stack=stack(c), world_state=pick(q(c, {"cmd": "world_state"}), ("has_save", "has_battle", "error")))
        r.cell("CR3-3", "GUARD", "coop_dialog_back: within 60 s the client's top MainMenuState and world_state.has_save false (MJ-2, #82)",
               ev["coop_dialog_back"].get("ok") is True and ev["stack"][-1:] == [MENU] and ev["world_state"]["has_save"] is False, ev)
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end("CR3-4", c.user_dir, results, walls)

def new_x(tag):
    return SimpleNamespace(tag=tag, js=None, host=None, client=None, client2=None, err=None, squad=None, b0=None, t0=None, split0=None)

def boot_shared(tag, key):
    """boot H: shared_fixture.bring_up + bring_up_shared_mixed_battle(js, {0: 0, 1: 1}) (squad[1] owned by seat 1)"""
    x = new_x(tag)
    try:
        x.js = shared_fixture.bring_up(tag, (1, 2, int(key)))
        x.host, x.client = x.js.host, x.js.client
        _h, _c, x.squad = session.bring_up_shared_mixed_battle(x.js, {0: 0, 1: 1})
    except Exception as e:
        x.err = short(e, 600)
    return x

def boot_separate(tag, key, pre=None):
    """a SEPARATE boot: bring_up_separate_guest_battle (SPEC 19 S1: 3 host soldiers + the client's "Guest Zzz") to tactical"""
    x = new_x(tag)
    try:
        x.host, x.client = GameClient("host", 1, make_user_dir(tag + "_host")), GameClient("client", 2, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        session.bring_up_separate_guest_battle(x.host, x.client, port=key, pre_mission_start=pre)
    except Exception as e:
        x.err = short(e, 600)
    return x

def shut(x):
    """every machine of the boot (a killed client is already reaped) -> the shutdown failures"""
    failed = []
    for gc in (x.client2, x.client, x.host):
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown()
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (x.tag, gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, gc.name))
    return failed

def run(boots, name):
    """each boot, its rows, then its shutdown before the next boot -> exit code"""
    t0, results, walls, failed, order = time.time(), {}, {}, [], []
    for tag, boot, rows in boots:
        tb = time.time()
        x = boot(tag)
        walls[tag + " boot"] = round(time.time() - tb, 1)
        for rid, row in rows:
            order.append(rid)
            row(x, results, walls)
        failed += shut(x)
        walls[tag] = round(time.time() - tb, 1)
    failed += [rid for rid in order if not results.get(rid)]
    print("\n%s: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (name, sum(1 for rid in order if results.get(rid)), len(order), failed,
                                                                 json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

def main():
    return run((("w2r4l2_h", lambda tag: boot_shared(tag, KEY_H), (("CR1", row_cr1),)),
                ("w2r4l2_c", lambda tag: boot_separate(tag, KEY_C), (("CR3", row_cr3),))), "test_campaign_rejoin")

if __name__ == "__main__":
    sys.exit(main())
