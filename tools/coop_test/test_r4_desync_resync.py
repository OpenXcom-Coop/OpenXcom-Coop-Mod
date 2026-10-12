"""R4-L3 stage S-A (spec rewrite/prompts/r4l3_desync_resync.md (f) `test_r4_desync_resync.py`; owner D232 (a); QL3-1..QL3-11 (a); TASK 0
rewrite/r4l3-task0/sa/CONSTANTS.md): a desync detected in a co-op battle no longer ends it. The host answers the second player's report at
its next quiescent pass behind its waiting screen, re-sends its live battle (offer key `resync`), the second player tears its frozen battle
down in process and loads the host's, and both screens close by themselves once the copy matches; play continues.
  Boot R (key "48752", dirs r4l3_r_host / _client): DC's boot (raw.bring_up_lobby, session.drive_to_battlescape seat_count 2 with set_seed
  SEED_MAP before newbattle_ok, MAP_FP on both, pin_ai_neutral, wait_host_idle, HASH); the pins H, H2, G, G_TILE asserted (a miss = FIXTURE-STOP
  with ONE CAPTURE line, every row FAILs "boot"). Rows in this order:
  DR1 player turn: a client-only `set_stat reactions` +7 on H2 is found at the host's real-UI kneel of H (its bt_action_end, `saveBlob`) and
      repaired. DR1-1 GUARD set_stat ok + the diff ['saveBlob']; DR1-2 RED the desync on both records (client last == {saveBlob, s0 + 2,
      KIND_DR1}, the host's the same); DR1-3 RED offered +1, lastOfferSide 0, the OFFER and RESYNC host lines +1; DR1-4 RED REPAIRED, client
      teardowns / loaded +1, host completed / released +1, CLIENT_ACTIVE +1, host turn T0; DR1-5 RED HASH + H2's reactions equal; DR1-6 RED
      SPLIT == SPLIT0; DR1-7 RED a client walk of G to G_DEST applies on both + HASH; DR1-8 RED the probes after the repair (client desyncSeen
      true, RS frozen false; host desyncSeen true; QL3-4 (a)); DR1-9 GUARD CRASH 0.
  DR4 a second desync in the same battle: tu_both(K4), a client corrupt_bucket {unitsStats} (U), the host's kneel of K4. DR4-1 GUARD the corrupt
      ok, exactly U's client TU moved, U != K4; DR4-2 RED desyncs +1 on both, client last {unitsStats, KIND_DR4}; DR4-3 RED REPAIRED + offered /
      completed / released / teardowns / loaded +1; DR4-4 RED HASH + U's TU equal; DR4-5 RED a client walk of G back to G_TILE + HASH; DR4-6
      GUARD CRASH 0.
  DR2 the alien side: the poke on H, both press END TURN; the desync lands at the boundary (side_transition, saveBlob) and the repair runs on
      the hostile side. DR2-1 GUARD set_stat ok, the client's H reactions r0 + 7; DR2-2 RED the diff ['saveBlob'] before the presses, client
      last {BUCKET_DR2, KIND_DR2}, host lastOfferSide 1; DR2-3 RED REPAIRED + the RS deltas as DR4-3; DR2-4 RED both on turn T1 + 1 side 0 +
      HASH; DR2-5 RED a client walk of G to G_DEST + HASH; DR2-6 GUARD CRASH 0.
Definitions (spec (f)): POLL 0.25 s; RS(gc) = resync_state.resync, counters as deltas from the row's own baseline; HASH = wait_host_idle +
assert_hash_clean(full); SPLIT = sorted (id, coop) of faction 0, not isOut; NOTICE_OK(gc) = a CoopDesyncNoticeState on top is dismissed
(dismiss_popup) and the top is BattlescapeState within 10 s (a no-op before S-C); REPAIRED(b0, n) within W_REPAIR 45 s: host RS released +n,
client RS loaded +n, NOTICE_OK on both, both tops BattlescapeState, both phase Active, battleId b0 on both, host peerAbsent false, client RS
frozen false, no CoopState on the host's stack; CRASH = session._crash_log_snapshot() delta at the row's end, every case. LIVE = client RS
frozen false and both tops BattlescapeState: a row that starts with the battle not LIVE runs only its client-local GUARD, its other cells
"not reached". battle_state is probed only with a BattlescapeState on top (F10980). A WAIT that times out ends the row ("not reached").
EVIDENCE before each verdict; a failed row prints ONE CAPTURE line; ONE run (WV-D95; WV-D99 / WV-D100: no SKIP path); exit 0 iff every cell
passes, else 2.
Red (commit A1: the record has no writers, the base never repairs): DR1-2..DR1-8, DR4-2..DR4-5, DR2-2..DR2-5 FAIL (DR4 / DR2 after DR1's
freeze: "not reached"); DR1-1, DR4-1, DR2-1 and every CRASH cell PASS.
"""
import ctypes
import json
import os
import re
import sys
import time
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import repro_atom_walk as raw  # noqa: E402
import test_w2_delta_core as dc  # noqa: E402
import test_w2_hash_coverage as hcv  # noqa: E402
from test_rw_turn_baton import dismiss_next_turn_if_present  # noqa: E402

KEY, TAG = "48752", "r4l3_r"
SEED_MAP, MAP_FP = 1, -4.48310638993e+18   # DC's map (CONSTANTS: 5 boots)
H, H2, G = 10, 11, 8                       # the first / second host-seat soldier, the first seat-1 soldier
G_TILE, G_DEST = (14, 19, 1), (14, 17, 0)  # G's start tile; the walk's measured end tile (R-L3-A-4, F11791: (14, 17, 1) has no floor)
U, K4 = 8, 10                              # corrupt_bucket's unit (the first live unit) and the kneeler that does not restate it
KIND_DR1, SEQ_OFF_DR1 = "bt_action_end", 2  # R-L3-A-2: a bt_action_end (no `kind`, F11651) is named by its state; seq = s0 + 2 (Ra, Rd, Re)
BUCKET_DR4, KIND_DR4 = "unitsStats", "kneel"
BUCKET_DR2, KIND_DR2 = "saveBlob", "side_transition"
POKE = 7
POLL, W_REPAIR, W_NOTICE, W_TURN, W_WALK, W_IDLE = 0.25, 45.0, 10.0, 90.0, 30.0, 30.0
BS, CSTATE, NOTICE = "BattlescapeState", "CoopState", "CoopDesyncNoticeState"
OFFER = "SPEC16 M5: rejoin battle_offer sent (battleId="
RESYNC = "[coop-resync] host: automatic repair offered"
RELEASED = "[coop-resync] host: the battle is repaired - the pause is released"
CLIENT_ACTIVE = "CLIENT phase Active (battleId="
LOG_TAGS = ("[coop-resync]", "[coop-handshake]", "[coop-hash]", "[coop-pump]", "coop-session")
TS_RE = re.compile(r"^\[(\d\d)-(\d\d)-(\d{4})_(\d\d)-(\d\d)-(\d\d)\.(\d{3})\]")


class Stop(Exception):
    """a WAIT timed out, the battle is not LIVE, or a probe raised: the row ends here"""


def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]


def js(v):
    return json.dumps(v, sort_keys=True, default=str)


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}


def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]


def top(gc):
    return (stack(gc) or [None])[-1]


def rs(gc):
    r = q(gc, {"cmd": "resync_state"})
    return r.get("resync") or {} if r.get("ok") else {"error": r.get("error") or "resync_state not ok"}


def delta(a, b, k):
    return (b or {}).get(k, 0) - (a or {}).get(k, 0)


def es(gc):
    r = q(gc, {"cmd": "event_state"})
    return {k: r.get(k) for k in ("desyncSeen", "phase", "battleId", "lastSeqEmitted", "lastSeqApplied", "queueDepth", "busyOwnerSeat")}


def bs(gc):
    """battle_state, only with a BattlescapeState on top (F10980); {} otherwise"""
    return q(gc, {"cmd": "battle_state"}) if top(gc) == BS else {}


def auth(gc):
    r = bs(gc)
    if not r:
        return {"skipped": "top %s" % top(gc)}
    a = r.get("authority") or {}
    return {"phase": r.get("phase"), "turn": r.get("turn"), "side": r.get("side"), "battleId": a.get("battleId"),
            "peerAbsent": a.get("peerAbsent"), "desyncFrozen": a.get("desyncFrozen")}


def units(gc):
    return session.units_by_id(bs(gc))


def pos(u):
    return (u.get("x"), u.get("y"), u.get("z")) if u else None


def split(gc):
    return sorted([u.get("id"), u.get("coop")] for u in bs(gc).get("units") or [] if u.get("faction") == 0 and not u.get("isOut"))


def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible", "error")}


def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def since(gc, n0, needle):
    return [ln.split("\t")[-1][:220] for ln in log(gc)[n0:] if needle in ln]


def log_dt(gc, n0, needle, t_ref):
    """seconds from t_ref to the first `needle` line since n0, by the line's own timestamp (None when absent)"""
    for ln in log(gc)[n0:]:
        m = TS_RE.match(ln) if needle in ln else None
        if m:
            d, mo, y, hh, mi, s, ms = (int(v) for v in m.groups())
            return round(time.mktime((y, mo, d, hh, mi, s, 0, 0, -1)) + ms / 1000.0 - t_ref, 3)
    return None


def desync_line(gc, n0):
    """the first `[coop-hash] DESYNC:` line since n0 as {bucket, seq, kind}"""
    for ln in log(gc)[n0:]:
        m = dc.DESYNC_RE.search(ln)
        if m:
            return {"bucket": m.group(1), "seq": int(m.group(2)), "kind": m.group(3)}
    return None


def cpu_now():
    from ctypes import wintypes
    ft = [wintypes.FILETIME() for _ in range(3)]
    ctypes.windll.kernel32.GetSystemTimes(*[ctypes.byref(f) for f in ft])
    return [(f.dwHighDateTime << 32) | f.dwLowDateTime for f in ft]


def cpu_pct(a, b):
    idle, total = b[0] - a[0], (b[1] - a[1]) + (b[2] - a[2])
    return round(100.0 * (total - idle) / total, 1) if total > 0 else None


def wait(desc, pred, timeout, interval=POLL):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(interval)
    raise Stop("WAIT %s: timed out after %.0f s" % (desc, timeout))


def notice_ok(gc):
    """NOTICE_OK(gc): a CoopDesyncNoticeState on top is dismissed and the top is BattlescapeState within W_NOTICE -> what happened"""
    if top(gc) != NOTICE:
        return None
    r = q(gc, {"cmd": "dismiss_popup"})
    try:
        return {"dismiss": r, "bs s": wait("%s top BattlescapeState after the notice" % gc.name, lambda: top(gc) == BS, W_NOTICE)}
    except Stop as e:
        return {"dismiss": r, "wait": str(e)}


def hash_ok(h, c, what):
    """HASH(host, client) -> (ok, evidence)"""
    ev = {}
    try:
        session.wait_host_idle(h, c, timeout=W_IDLE)
        hh, _ch = session.assert_hash_clean(h, c, full=True, what=what)
        ev["equal buckets"] = len(hh)
    except Exception as e:
        ev["error"] = short(e, 700)
    return "error" not in ev, ev


def live(x):
    """LIVE: client RS frozen false and both tops BattlescapeState -> (ok, values)"""
    v = {"client frozen": rs(x.client).get("frozen"), "tops": [top(x.host), top(x.client)]}
    return v["client frozen"] is False and v["tops"] == [BS, BS], v


def repaired(x, rh0, rc0, n, t_press, cycle=False):
    """REPAIRED(host, client, B0, n) polled at POLL for <= W_REPAIR (cycle: NextTurnStates closed on both at every poll) -> (ok, evidence:
    the host's stack + 62 title timeline, the values at the pass or the timeout, the repair wall)"""
    h, c, seen, tl, last = x.host, x.client, {}, [], [None]

    def ok():
        for gc in (h, c):
            if cycle:
                try:
                    if dismiss_next_turn_if_present(gc):
                        seen.setdefault("nextturn closed", []).append([gc.name, round(time.time() - t_press, 2)])
                except Exception as e:
                    seen.setdefault("nextturn errors", []).append([gc.name, short(e, 120)])
            nt = notice_ok(gc)
            if nt is not None:
                seen.setdefault("notices", []).append([gc.name, nt])
        hs, cs, d = stack(h), stack(c), dlg(h)
        snap = [hs[-3:], d.get("code"), d.get("title"), cs[-3:]]
        if js(snap) != last[0]:
            last[0] = js(snap)
            tl.append([round(time.time() - t_press, 2)] + snap)
        rh, rc = rs(h), rs(c)
        ah = auth(h) if hs[-1:] == [BS] else {}
        ac = auth(c) if cs[-1:] == [BS] else {}
        seen.update(released=delta(rh0, rh, "released"), loaded=delta(rc0, rc, "loaded"), host=ah, client=ac, clientFrozen=rc.get("frozen"),
                    hostCoopState=CSTATE in hs, tops=[hs[-1:], cs[-1:]])
        return (seen["released"] == n and seen["loaded"] == n and hs[-1:] == [BS] and cs[-1:] == [BS]
                and ah.get("phase") == ac.get("phase") == "Active" and ah.get("battleId") == ac.get("battleId") == x.b0
                and ah.get("peerAbsent") is False and rc.get("frozen") is False and not seen["hostCoopState"])
    try:
        wait("REPAIRED", ok, W_REPAIR)
        seen["repair wall s"], good = round(time.time() - t_press, 2), True
    except Stop as e:
        seen["wait"], good = str(e), False
    seen["timeline"] = tl
    return good, seen


def walk(x, uid, dest, what):
    """the client's walk order (session.send_walk) for uid to dest; a NEW host walk settled, the host idle; uid on dest on both + HASH"""
    h, c = x.host, x.client
    prev = session.walk_action_id(h)
    r = session.send_walk(c, uid, dest)
    ev = {"send_walk": {k: r.get(k) for k in ("ok", "iseq", "error")}}
    try:
        session.wait_walk_settled(h, c, prev, timeout=W_WALK)
    except Exception as e:
        ev["wait"] = short(e, 300)
    ev["pos"] = [pos(units(h).get(uid)), pos(units(c).get(uid))]
    hok, ev["HASH"] = hash_ok(h, c, what)
    return bool(r.get("iseq")) and "wait" not in ev and ev["pos"] == [dest, dest] and hok, ev


class Row:
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.t0 = rid, cells, x, [], set(), time.time()
        self.cr0, self.cpu0 = session._crash_log_snapshot(), cpu_now()

    def cell(self, cid, kind, label, ok, ev):
        print("EVIDENCE %s: %s" % (cid, js(ev)), flush=True)
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        print("EVIDENCE %s stop: %s" % (self.rid, why), flush=True)
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:200]), flush=True)
            self.fails.append(cid)
            self.done.add(cid)

    def end(self, crash_cid, results, walls):
        """the CRASH cell (every case), the row's wall + CPU, ONE CAPTURE line when a cell failed, the row verdict"""
        new = sorted(session._crash_log_snapshot() - self.cr0)
        self.cell(crash_cid, "GUARD", "CRASH 0 (no new crash_*.log in this lane's crash folder since the row's baseline)", not new, {"crash": new})
        walls[self.rid] = round(time.time() - self.t0, 1)
        print("EVIDENCE %s wall: %s s, cpu %s %%" % (self.rid, walls[self.rid], cpu_pct(self.cpu0, cpu_now())), flush=True)
        if self.fails:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.x))), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)


def capture(x):
    """both machines: stack, battle_state (guarded), event_state, resync_state, coop_dialog_info, the co-op log tails"""
    cap = {}
    for n, gc in (("host", x.host), ("client", x.client)):
        if gc is None or gc.proc is None or gc.proc.poll() is not None:
            cap[n] = "not running"
            continue
        cap[n] = {"stack": stack(gc), "battle_state": auth(gc), "event_state": es(gc), "resync_state": rs(gc), "coop_dialog_info": dlg(gc),
                  "log": [ln.split("\t")[-1][:200] for ln in log(gc) if any(t in ln for t in LOG_TAGS)][-12:]}
    return cap


def kneel(x, uid):
    """the host's real-UI kneel of uid (hcv.host_kneel's TAB-select + SDLK_K), reset-safe wait (R-L3-A-4, F11793): the kneel flipped on the
    host, visible on both, the host idle (the repair's CoopPump::reset(false) can keep hcv's `lastSeqEmitted > s0` false) -> (s0, evidence)"""
    h, c, notes, t = x.host, x.client, [], time.time()
    if not hcv.tab_select(h, uid):
        return None, {"kneeled": [None, None], "s0": None, "kneel s": round(time.time() - t, 2), "notes": ["TAB never selected %s" % uid]}
    k0, s0 = units(h).get(uid, {}).get("kneeled"), es(h).get("lastSeqEmitted") or 0
    h.ok({"cmd": "inject_input", "kind": "key", "key": hcv.SDLK_K})
    bs_live = lambda st: st[-1:] == [BS] or st[-2:] == [BS, NOTICE]  # noqa: E731  R-L3-C-1 (F12303): BattlescapeState live under the notice
    kn = lambda gc: (session.units_by_id(q(gc, {"cmd": "battle_state"})) if bs_live(stack(gc)) else {}).get(uid, {}).get("kneeled")  # noqa: E731
    try:
        wait("the kneel on both, the host idle", lambda: kn(h) not in (None, k0) and kn(c) == kn(h) and es(h).get("busyOwnerSeat") == -1, 20.0)
    except Stop as e:
        notes.append(str(e))
    return s0, {"kneeled": [k0, kn(h)], "s0": s0, "kneel s": round(time.time() - t, 2), "notes": notes}


def row_dr1(x, results, walls):
    r = Row("DR1", ["DR1-%d" % i for i in range(1, 9)], x)
    h, c = x.host, x.client
    try:
        t0, rh0, rc0, nh, nc = auth(h).get("turn"), rs(h), rs(c), len(log(h)), len(log(c))
        r0 = units(c).get(H2, {}).get("reactions")
        rset = q(c, {"cmd": "battle_action", "action": "set_stat", "unit": H2, "stat": "reactions", "value": (r0 or 0) + POKE})
        r1, diff = units(c).get(H2, {}).get("reactions"), dc.diff_buckets(h, c)
        r.cell("DR1-1", "GUARD", "client set_stat H2 %d reactions r0 + %d ok; the hash diff before the kneel == ['saveBlob'] (CONSTANTS)" % (H2, POKE),
               rset.get("ok") is True and r1 == (r0 or 0) + POKE and diff == ["saveBlob"],
               {"set_stat": rset, "client reactions": [r0, r1], "host reactions": units(h).get(H2, {}).get("reactions"), "diff": diff})
        t_press = time.time()
        s0, kev = kneel(x, H)
        kev["action_end_of"] = hcv.action_end_of(h, (s0 or 0) + 1, "kneel")
        good, rev = repaired(x, rh0, rc0, 1, t_press)
        rh, rc = rs(h), rs(c)
        clast, hlast = rc.get("last") or {}, rh.get("last") or {}
        want = {"bucket": "saveBlob", "seq": (s0 or 0) + SEQ_OFF_DR1, "kind": KIND_DR1, "battleId": x.b0}
        print("EVIDENCE DR1: %s" % js({"kneel": kev, "repair": rev, "repair wall (host log) s": log_dt(h, nh, RELEASED, t_press),
                                       "client DESYNC": desync_line(c, nc), "RS host": rh, "RS client": rc}), flush=True)
        r.cell("DR1-2", "RED", "the desync on both records: client RS desyncs +1, last == %s; host RS desyncs +1 with the same last" % want,
               delta(rc0, rc, "desyncs") == 1 and clast == want and delta(rh0, rh, "desyncs") == 1 and hlast == clast,
               {"client": [delta(rc0, rc, "desyncs"), clast], "host": [delta(rh0, rh, "desyncs"), hlast], "want": want,
                "client DESYNC line": desync_line(c, nc)})
        offers, resyncs = since(h, nh, OFFER), since(h, nh, RESYNC)
        r.cell("DR1-3", "RED", "the repair: host RS offered +1, lastOfferSide 0; host log OFFER (battleId=%s) +1 and RESYNC +1" % x.b0,
               delta(rh0, rh, "offered") == 1 and rh.get("lastOfferSide") == 0 and len(offers) == 1
               and ("battleId=%s," % x.b0) in offers[0] and len(resyncs) == 1,
               {"offered": delta(rh0, rh, "offered"), "lastOfferSide": rh.get("lastOfferSide"), "OFFER": offers, "RESYNC": resyncs})
        act, ah = since(c, nc, CLIENT_ACTIVE), auth(h)
        r.cell("DR1-4", "RED", "REPAIRED within %.0f s; client RS teardowns / loaded +1; host RS completed / released +1; client CLIENT_ACTIVE "
               "(battleId=%s) +1; host turn == T0 %s" % (W_REPAIR, x.b0, t0),
               good and delta(rc0, rc, "teardowns") == 1 and delta(rc0, rc, "loaded") == 1 and delta(rh0, rh, "completed") == 1
               and delta(rh0, rh, "released") == 1 and len(act) == 1 and ("battleId=%s," % x.b0) in act[0] and ah.get("turn") == t0,
               {"REPAIRED": good, "deltas": {k: [delta(rh0, rh, k), delta(rc0, rc, k)] for k in ("teardowns", "loaded", "completed", "released")},
                "CLIENT_ACTIVE": act, "host": ah, "T0": t0})
        eh, ec = es(h), es(c)
        r.cell("DR1-8", "RED", "the probes after the repair: client event_state.desyncSeen true and RS frozen false; host desyncSeen true",
               ec.get("desyncSeen") is True and rc.get("frozen") is False and eh.get("desyncSeen") is True,
               {"client desyncSeen": ec.get("desyncSeen"), "client RS frozen": rc.get("frozen"), "host desyncSeen": eh.get("desyncSeen")})
        if not good:
            raise Stop("REPAIRED not reached within %.0f s (%s)" % (W_REPAIR, rev.get("wait")))
        hok, hev = hash_ok(h, c, "DR1 after the repair")
        rr = [units(h).get(H2, {}).get("reactions"), units(c).get(H2, {}).get("reactions")]
        r.cell("DR1-5", "RED", "HASH (every bucket EQUAL); H2's reactions equal on both (the poke undone)", hok and rr[0] == rr[1] is not None,
               {"HASH": hev, "H2 reactions host/client": rr})
        sh, sc = split(h), split(c)
        r.cell("DR1-6", "RED", "SPLIT(host) == SPLIT(client) == SPLIT0", sh == sc == x.split0, {"host": sh, "client": sc, "SPLIT0": x.split0})
        wok, wev = walk(x, G, G_DEST, "DR1-7")
        r.cell("DR1-7", "RED", "play continues: a client walk of G %d to %s applies on both; HASH" % (G, G_DEST), wok, wev)
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end("DR1-9", results, walls)


def row_dr4(x, results, walls):
    r = Row("DR4", ["DR4-%d" % i for i in range(1, 6)], x)
    h, c = x.host, x.client
    try:
        lv, lev = live(x)
        tu = dc.tu_both(h, c, K4) if lv else "not run (the battle is not LIVE)"
        rh0, rc0, nh, nc = rs(h), rs(c), len(log(h)), len(log(c))
        before = {u["id"]: u.get("tu") for u in bs(c).get("units") or []}
        rcor = q(c, {"cmd": "corrupt_bucket", "name": "unitsStats"})
        after = {u["id"]: u.get("tu") for u in bs(c).get("units") or []}
        moved = [uid for uid in after if before.get(uid) != after.get(uid)]
        r.cell("DR4-1", "GUARD", "client corrupt_bucket {unitsStats} ok; exactly one unit's client TU moved, U == %d (CONSTANTS), U != K4 %d" % (U, K4),
               rcor.get("ok") is True and moved == [U] and U != K4,
               {"LIVE": [lv, lev], "tu_both K4": tu, "corrupt": rcor, "moved": moved, "client TU": [before.get(U), after.get(U)]})
        if not lv:
            raise Stop("not reached: the battle is not LIVE at the row's start (%s)" % js(lev))
        t_press = time.time()
        s0, kev = kneel(x, K4)
        good, rev = repaired(x, rh0, rc0, 1, t_press)
        rh, rc = rs(h), rs(c)
        clast = rc.get("last") or {}
        print("EVIDENCE DR4: %s" % js({"kneel": kev, "repair": rev, "repair wall (host log) s": log_dt(h, nh, RELEASED, t_press),
                                       "client DESYNC": desync_line(c, nc), "RS host": rh, "RS client": rc}), flush=True)
        r.cell("DR4-2", "RED", "client RS desyncs +1, last.bucket %s, kind %s; host RS desyncs +1" % (BUCKET_DR4, KIND_DR4),
               delta(rc0, rc, "desyncs") == 1 and clast.get("bucket") == BUCKET_DR4 and clast.get("kind") == KIND_DR4
               and delta(rh0, rh, "desyncs") == 1, {"client": [delta(rc0, rc, "desyncs"), clast], "host": [delta(rh0, rh, "desyncs"), rh.get("last")]})
        dd = {k: [delta(rh0, rh, k), delta(rc0, rc, k)] for k in ("offered", "completed", "released", "teardowns", "loaded")}
        r.cell("DR4-3", "RED", "REPAIRED; host RS offered / completed / released +1 each; client teardowns / loaded +1 each",
               good and all(dd[k][0] == 1 for k in ("offered", "completed", "released")) and all(dd[k][1] == 1 for k in ("teardowns", "loaded")),
               {"REPAIRED": good, "deltas host/client": dd})
        if not good:
            raise Stop("REPAIRED not reached within %.0f s (%s)" % (W_REPAIR, rev.get("wait")))
        hok, hev = hash_ok(h, c, "DR4 after the repair")
        tus = [units(h).get(U, {}).get("tu"), units(c).get(U, {}).get("tu")]
        r.cell("DR4-4", "RED", "HASH; U %d's TU equal on both" % U, hok and tus[0] == tus[1] is not None, {"HASH": hev, "U TU host/client": tus})
        wok, wev = walk(x, G, G_TILE, "DR4-5")
        r.cell("DR4-5", "RED", "a client walk of G %d back to its DR1 tile %s applies on both; HASH" % (G, G_TILE), wok, wev)
    except Exception as e:
        r.stop(e)
    r.end("DR4-6", results, walls)


def end_turn_presses(x):
    """the client presses END TURN, the host paints END TURN 1/2, the host presses -> the host press time"""
    h, c = x.host, x.client
    c.ok({"cmd": "battle_action", "action": "end_turn_button"})
    wait("host paints END TURN 1/2", lambda: bs(h).get("coopEndTurnText") == "END TURN 1/2", 20.0)
    t = time.time()
    h.ok({"cmd": "battle_action", "action": "end_turn_button"})
    return t


def row_dr2(x, results, walls):
    r = Row("DR2", ["DR2-%d" % i for i in range(1, 6)], x)
    h, c = x.host, x.client
    try:
        lv, lev = live(x)
        rh0, rc0, nh, nc, t1 = rs(h), rs(c), len(log(h)), len(log(c)), auth(h).get("turn")
        r0 = units(c).get(H, {}).get("reactions")
        rset = q(c, {"cmd": "battle_action", "action": "set_stat", "unit": H, "stat": "reactions", "value": (r0 or 0) + POKE})
        r1 = units(c).get(H, {}).get("reactions")
        r.cell("DR2-1", "GUARD", "client set_stat H %d reactions ok; the client's H reactions == r0 + %d (client-local read)" % (H, POKE),
               rset.get("ok") is True and r0 is not None and r1 == r0 + POKE, {"set_stat": rset, "client reactions": [r0, r1], "LIVE": [lv, lev]})
        diff = dc.diff_buckets(h, c)
        print("EVIDENCE DR2 pre: %s" % js({"diff before the presses": diff, "T1": t1}), flush=True)
        if not lv:
            raise Stop("not reached: the battle is not LIVE at the row's start (%s); diff %s" % (js(lev), diff))
        t_press = end_turn_presses(x)
        good, rev = repaired(x, rh0, rc0, 1, t_press, cycle=True)
        rh, rc = rs(h), rs(c)
        clast = rc.get("last") or {}
        print("EVIDENCE DR2: %s" % js({"repair": rev, "repair wall (host log) s": log_dt(h, nh, RELEASED, t_press),
                                       "client DESYNC": desync_line(c, nc), "RS host": rh, "RS client": rc}), flush=True)
        r.cell("DR2-2", "RED", "the diff before the END TURN presses == ['saveBlob']; client RS last {bucket %s, kind %s}; host RS lastOfferSide 1"
               % (BUCKET_DR2, KIND_DR2), diff == ["saveBlob"] and clast.get("bucket") == BUCKET_DR2 and clast.get("kind") == KIND_DR2
               and rh.get("lastOfferSide") == 1, {"diff": diff, "client last": clast, "host lastOfferSide": rh.get("lastOfferSide")})
        dd = {k: [delta(rh0, rh, k), delta(rc0, rc, k)] for k in ("offered", "completed", "released", "teardowns", "loaded")}
        r.cell("DR2-3", "RED", "REPAIRED; the RS deltas as DR4-3",
               good and all(dd[k][0] == 1 for k in ("offered", "completed", "released")) and all(dd[k][1] == 1 for k in ("teardowns", "loaded")),
               {"REPAIRED": good, "deltas host/client": dd})
        if not good:
            raise Stop("REPAIRED not reached within %.0f s (%s)" % (W_REPAIR, rev.get("wait")))
        seen = {}

        def back():
            for gc in (h, c):
                dismiss_next_turn_if_present(gc)
                notice_ok(gc)
            seen.update(host=auth(h), client=auth(c))
            return all(seen[n].get("turn") == (t1 or 0) + 1 and seen[n].get("side") == 0 for n in ("host", "client"))
        try:
            seen["s"] = wait("both on turn T1 + 1, side 0", back, max(1.0, W_TURN - (time.time() - t_press)))
        except Stop as e:
            seen["wait"] = str(e)
        hok, hev = hash_ok(h, c, "DR2 after the cycle")
        r.cell("DR2-4", "RED", "both on turn T1 + 1 = %s, side 0 within %.0f s of the press; HASH" % ((t1 or 0) + 1, W_TURN),
               "wait" not in seen and hok, {"turn/side": seen, "HASH": hev})
        if "wait" in seen:
            raise Stop(seen["wait"])
        wok, wev = walk(x, G, G_DEST, "DR2-5")
        r.cell("DR2-5", "RED", "a client walk of G %d to %s applies on both; HASH" % (G, G_DEST), wok, wev)
    except Exception as e:
        r.stop(e)
    r.end("DR2-6", results, walls)


def boot():
    """boot R -> x (x.err set on a miss: FIXTURE-STOP)"""
    x = SimpleNamespace(host=None, client=None, err=None, b0=None, split0=None)
    try:
        x.host, x.client = GameClient("host", 1, make_user_dir(TAG + "_host")), GameClient("client", 2, make_user_dir(TAG + "_client"))
        raw.bring_up_lobby(x.host, x.client, KEY)
        session.drive_to_battlescape(x.host, x.client, {}, seat_count=2, pre_ok=lambda gc: gc.ok({"cmd": "set_seed", "seed": SEED_MAP}))
        hs, cs = session.battle_state(x.host), session.battle_state(x.client)
        fp = [hs.get("mapFingerprint"), cs.get("mapFingerprint")]
        assert fp == [MAP_FP, MAP_FP], "FIXTURE-STOP: mapFingerprint %s (MAP_FP %r, SEED_MAP %d)" % (fp, MAP_FP, SEED_MAP)
        pinned = session.pin_ai_neutral(x.host, x.client, tag=TAG)
        assert pinned, "FIXTURE-STOP: pin_ai_neutral pinned no NONE-seat non-player unit"
        session.wait_host_idle(x.host, x.client, timeout=W_IDLE)
        session.assert_hash_clean(x.host, x.client, full=True, what="boot R")
        live_us = [u for u in hs.get("units") or [] if u.get("faction") == 0 and not u.get("isOut")]
        s0 = sorted(u["id"] for u in live_us if u.get("coop") == 0)
        s1 = sorted(u["id"] for u in live_us if u.get("coop") == 1)
        gt = pos(session.units_by_id(hs).get(G))
        assert s0[:2] == [H, H2] and s1[:1] == [G] and gt == G_TILE, (
            "FIXTURE-STOP: pins seat0 %s seat1 %s G at %s (CONSTANTS H %d, H2 %d, G %d at %s)" % (s0, s1, gt, H, H2, G, G_TILE))
        ah, ac = auth(x.host), auth(x.client)
        x.b0, x.split0 = ah.get("battleId"), split(x.host)
        assert x.b0 and x.b0 == ac.get("battleId") and x.split0 == split(x.client), (
            "FIXTURE-STOP: B0 %s / %s, SPLIT0 %s / %s" % (x.b0, ac.get("battleId"), x.split0, split(x.client)))
        print("[r4l3-r] boot ok: MAP_FP %r, pinned %s, B0 %s, turn %s, SPLIT0 %s" % (MAP_FP, pinned, x.b0, ah.get("turn"), x.split0), flush=True)
    except Exception as e:
        x.err = short(e, 800)
    return x


def shut(x):
    failed = []
    for gc in (x.client, x.host):
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown()
        except Exception as e:
            print("FAIL shutdown (%s): %s" % (gc.name, short(e, 300)), flush=True)
            failed.append("shutdown %s" % gc.name)
    return failed


ROWS = (("DR1", row_dr1), ("DR4", row_dr4), ("DR2", row_dr2))


def main():
    t0, results, walls = time.time(), {}, {}
    x = boot()
    walls["boot"] = round(time.time() - t0, 1)
    if x.err:
        print("EVIDENCE boot: %s\nCAPTURE boot: %s" % (x.err, js(capture(x))), flush=True)
        for rid, _fn in ROWS:
            print("FAIL %s boot: the boot did not reach the tactical map with its pins" % rid, flush=True)
            results[rid] = False
    else:
        for _rid, fn in ROWS:
            fn(x, results, walls)
    failed = shut(x) + [rid for rid, _fn in ROWS if not results.get(rid)]
    print("\ntest_r4_desync_resync: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid, _fn in ROWS if results.get(rid)), len(ROWS), failed, js(walls), time.time() - t0), flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
