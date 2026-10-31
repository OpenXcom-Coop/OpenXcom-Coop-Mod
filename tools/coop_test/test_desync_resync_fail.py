"""test_desync_resync_fail.py: an automatic desync repair whose re-sent battle is refused, or whose copy does not
match, leaves the battle paused for good: no further repair, no RESUME, the host keeps SAVE & QUIT / ABANDON, and the
waiting screen says the battle could not be repaired. Two boots, one row each, each shut down before the next:
  refused_battle (key "48753", dirs resync_fail_refused_host / _client) the re-sent battle is refused: the host arms
      the TEST-ONLY `corrupt_next_blob`, the client pokes H2's reactions (+7, client-only), the host's real-UI kneel
      of H raises the desync; wait <= 30 s for the host's `rejoin refused (corrupt)` line, <= W_TITLE for the 62
      title to leave "Repairing the battle", then HOLD_S. refused_battle-1 GUARD the repair was offered, the test
      hook fired on it, the client refused it (reason=corrupt), client phase Idle, client top CoopStageHold;
      refused_battle-2 FIX host RS failed +1, lastFail "refused"; refused_battle-3 GUARD at every HOLD_S poll: host
      phase Active, peerAbsent true, 62 on top with back hidden and SAVE & QUIT / ABANDON shown, offered unchanged
      (no loop), client top unchanged, client desyncSeen true; refused_battle-4 GUARD the escape: host ABANDON -> host
      MainMenuState <= 60 s, client code 21 <= 30 s, client OK -> MainMenuState <= 60 s; refused_battle-5 FIX the 62
      title at every HOLD_S poll == TITLE_FAILED; refused_battle-6 GUARD CRASH 0.
  copy_mismatch (key "48754", dirs resync_fail_mismatch_host / _client) the re-sent copy does not match: the host
      arms the TEST-ONLY `resync_ready_mismatch`, the same chain; wait <= 30 s for the host's `battle_ready saveBlob
      MISMATCH` line, <= W_TITLE for the 62 title to leave "Repairing the battle", then HOLD_S. copy_mismatch-1 GUARD
      offered +1, client RS loaded +1, host `rejoin desync` +1, client top CoopState 68; copy_mismatch-2 FIX no
      RESUME: back hidden at every HOLD_S poll; copy_mismatch-3 FIX host RS failed +1, lastFail "ready mismatch";
      copy_mismatch-4 GUARD no second offer, host peerAbsent true, the client still on 68 at every poll;
      copy_mismatch-5 FIX as refused_battle-5; copy_mismatch-6 FIX the escape as refused_battle-4 (a refused ABANDON
      fails the cell at once and the row ends with the capture); copy_mismatch-7 GUARD CRASH 0.
Definitions: POLL 0.25 s; HOLD_S 20 s; RS(gc) = resync_state.resync, counters as deltas from the row's own baseline;
the host's battle_state is read while its BattlescapeState is on its stack (it stays live under 62; the client's is
never probed); CRASH = session._crash_log_snapshot() delta at the row's end, every case. EVIDENCE per cell; a failed
row prints ONE CAPTURE line (both machines); a boot miss = setup failure: ONE CAPTURE line and the row FAILs "boot".
ONE run in the foreground, no skip path; exit 0 iff every cell passes, else 2.
A build that has the two test hooks but does not handle a failed repair fails refused_battle-2, refused_battle-5,
copy_mismatch-2, copy_mismatch-3, copy_mismatch-5 and copy_mismatch-6 and passes every other cell. Its 62 then reads
"Waiting for players to load..." after a refused battle and "All players connected" after a copy mismatch, where it
also shows RESUME and hides ABANDON; the title cells print these titles as EVIDENCE (UNHANDLED_TITLE).
"""
import ctypes
import json
import os
import sys
import time
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import repro_atom_walk as raw  # noqa: E402
import test_delta_core as dc  # noqa: E402
import test_hash_coverage as hcv  # noqa: E402

SEED_MAP, MAP_FP = 1, -4.48310638993e+18   # test_delta_core's map and its fingerprint
H, H2 = 10, 11                             # the host-seat soldier the host kneels, the one the client pokes
POKE, POLL, HOLD_S, W_FAIL = 7, 0.25, 20.0, 30.0
W_HOST_MENU, W_CLIENT_21, W_CLIENT_MENU = 60.0, 30.0, 60.0
BS, CSTATE, HOLD, MENU = "BattlescapeState", "CoopState", "CoopStageHold", "MainMenuState"
TITLE_FAILED = "The battle could not be repaired.\nSave and quit, or abandon it."
# the 62's in-flight wording (CoopState::waitingTitle) and the bound for its title to settle
TITLE_REPAIRING, W_TITLE = "Repairing the battle", 5.0
# the 62 title of a build that does not handle a failed repair (EVIDENCE only)
UNHANDLED_TITLE = {"refused_battle": "Waiting for players to load...", "copy_mismatch": "All players connected"}
OFFER = "rejoin battle_offer sent (battleId="
CORRUPT_FIRED = "[coop-resync] TEST-ONLY corrupt_next_blob fired on the repair offer"
MISMATCH_FIRED = "[coop-resync] TEST-ONLY resync_ready_mismatch fired"
REFUSE_RECV = "battle_refuse received (battleId=%s, reason=corrupt)"
SHA_MISMATCH = "battle blob sha MISMATCH (battleId=%s,"
REFUSED = "rejoin refused (corrupt)"
READY_MISMATCH = "battle_ready saveBlob MISMATCH (battleId=%s,"
REJOIN_DESYNC = "rejoin desync"
CLIENT_ACTIVE = "CLIENT phase Active (battleId=%s,"
LOG_TAGS = ("[coop-resync]", "[coop-handshake]", "[coop-hash]", "[coop-pump]", "coop-session")


class Stop(Exception):
    """a WAIT timed out or a probe raised: the row ends here"""


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
    return {k: r.get(k) for k in ("desyncSeen", "phase", "battleId", "lastSeqEmitted", "lastSeqApplied", "busyOwnerSeat")}


def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible", "saveQuitVisible", "abandonVisible", "error")}


def bs_live(gc, st):
    """battle_state while a BattlescapeState is on the stack `st` (the host's stays live under 62); {} otherwise"""
    return q(gc, {"cmd": "battle_state"}) if BS in st else {}


def units(gc):
    return session.units_by_id(bs_live(gc, stack(gc)))


def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def since(gc, n0, needle):
    return [ln.split("\t")[-1][:220] for ln in log(gc)[n0:] if needle in ln]


def cpu_now():
    from ctypes import wintypes
    ft = [wintypes.FILETIME() for _ in range(3)]
    ctypes.windll.kernel32.GetSystemTimes(*[ctypes.byref(f) for f in ft])
    return [(f.dwHighDateTime << 32) | f.dwLowDateTime for f in ft]


def cpu_pct(a, b):
    idle, total = b[0] - a[0], (b[1] - a[1]) + (b[2] - a[2])
    return round(100.0 * (total - idle) / total, 1) if total > 0 else None


def wait_t(pred, timeout, interval=POLL):
    """seconds until pred() holds, None on a timeout"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(interval)
    return None


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

    def end(self, crash_cid, results, walls, cap):
        """the CRASH cell (every case), the row's wall + CPU, ONE CAPTURE line when a cell failed, the row verdict"""
        new = sorted(session._crash_log_snapshot() - self.cr0)
        self.cell(crash_cid, "GUARD", "CRASH 0 (no new crash_*.log in this lane's crash folder since the row's baseline)", not new, {"crash": new})
        walls[self.rid] = round(time.time() - self.t0, 1)
        print("EVIDENCE %s wall: %s s, cpu %s %%" % (self.rid, walls[self.rid], cpu_pct(self.cpu0, cpu_now())), flush=True)
        if self.fails:
            print("CAPTURE %s: %s" % (self.rid, js(cap if cap is not None else capture(self.x))), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)


def capture(x):
    """both machines: stack, battle_state (host-guarded), event_state, resync_state, coop_dialog_info, get_coop.resumeAck, the co-op log tails"""
    cap = {}
    for n, gc in (("host", x.host), ("client", x.client)):
        if gc is None or gc.proc is None or gc.proc.poll() is not None:
            cap[n] = "not running"
            continue
        st = stack(gc)
        b = bs_live(gc, st) if n == "host" else {}
        cap[n] = {"stack": st, "battle_state": {k: b.get(k) for k in ("phase", "turn", "side", "authority")}, "event_state": es(gc),
                  "resync_state": rs(gc), "coop_dialog_info": dlg(gc), "resumeAck": q(gc, {"cmd": "get_coop"}).get("resumeAck"),
                  "log": [ln.split("\t")[-1][:200] for ln in log(gc) if any(t in ln for t in LOG_TAGS)][-12:]}
    return cap


def provoke(x, hook):
    """the host's test hook, then test_desync_resync's player_turn_repair chain: the client-only +7 reactions on H2,
    the host's real-UI kneel of H -> evidence"""
    h, c = x.host, x.client
    ev = {"hook": q(h, {"cmd": hook})}
    r0 = units(c).get(H2, {}).get("reactions")
    ev["set_stat"] = q(c, {"cmd": "battle_action", "action": "set_stat", "unit": H2, "stat": "reactions", "value": (r0 or 0) + POKE})
    ev["client reactions"], ev["diff"] = [r0, units(c).get(H2, {}).get("reactions")], dc.diff_buckets(h, c)
    ev["tab_select"] = hcv.tab_select(h, H)
    ev["k0"], ev["s0"] = units(h).get(H, {}).get("kneeled"), es(h).get("lastSeqEmitted")
    x.t_press = time.time()
    h.ok({"cmd": "inject_input", "kind": "key", "key": hcv.SDLK_K})
    return ev


def hold(x, rh0):
    """HOLD_S at POLL: the host's 62, phase, peerAbsent, RS; the client's top, 68, desyncSeen -> the per-poll records"""
    h, c, polls, t0 = x.host, x.client, [], time.time()
    while time.time() - t0 < HOLD_S:
        hs = stack(h)
        b, d, rh, ec = bs_live(h, hs), dlg(h), rs(h), es(c)
        cs = stack(c)
        polls.append({"t": round(time.time() - t0, 2), "host top": hs[-1:], "phase": es(h).get("phase"),
                      "peerAbsent": (b.get("authority") or {}).get("peerAbsent"), "62": d, "offered": delta(rh0, rh, "offered"),
                      "client top": cs[-1:], "client code": dlg(c).get("code") if cs[-1:] == [CSTATE] else None,
                      "client desyncSeen": ec.get("desyncSeen")})
        time.sleep(POLL)
    return polls


def distinct(polls, key):
    out = {}
    for p in polls:
        out.setdefault(js(p[key]), [p["t"], 0])[1] += 1
    return out


def escape(x):
    """host ABANDON -> host MainMenuState; client 21 -> its OK -> MainMenuState (a refused ABANDON fails at once)
    -> (ok, ev, cap)"""
    h, c, t0 = x.host, x.client, time.time()
    ev = {"abandon": q(h, {"cmd": "coop_dialog_abandon"})}
    if not ev["abandon"].get("ok"):
        time.sleep(1.0)
        cap = capture(x)  # both machines as the refused ABANDON left them
        ev["after 1 s"] = {"host 62": cap["host"]["coop_dialog_info"] if isinstance(cap["host"], dict) else cap["host"],
                           "host resumeAck": cap["host"].get("resumeAck") if isinstance(cap["host"], dict) else None}
        return False, ev, cap
    ev["host MainMenuState s"] = wait_t(lambda: top(h) == MENU, W_HOST_MENU)
    ev["client 21 s"] = wait_t(lambda: dlg(c).get("code") == 21, W_CLIENT_21)
    ev["client 21"], ev["client stack at 21"] = dlg(c), stack(c)
    ev["back"] = q(c, {"cmd": "coop_dialog_back"})
    ev["client MainMenuState s"] = wait_t(lambda: top(c) == MENU, W_CLIENT_MENU)
    ev["escape s"] = round(time.time() - t0, 2)
    ok = (ev["host MainMenuState s"] is not None and ev["client 21 s"] is not None and ev["back"].get("ok") is True
          and ev["client MainMenuState s"] is not None)
    return ok, ev, None


def title_cell(r, cid, polls, rid):
    titles = distinct([dict(p, title=p["62"].get("title")) for p in polls], "title")
    r.cell(cid, "FIX", "the host's 62 title at every HOLD_S poll == %r" % TITLE_FAILED,
           bool(polls) and all(p["62"].get("title") == TITLE_FAILED for p in polls),
           {"titles seen (first s, polls)": titles, "title without failed-repair handling": UNHANDLED_TITLE[rid]})


def row_refused_battle(x, results, walls):
    r = Row("refused_battle", ["refused_battle-%d" % i for i in range(1, 6)], x)
    h, c, cap = x.host, x.client, None
    try:
        rh0, rc0, nh, nc = rs(h), rs(c), len(log(h)), len(log(c))
        pev = provoke(x, "corrupt_next_blob")
        s = wait_t(lambda: since(h, nh, REFUSED), W_FAIL)
        rh, ec, cst = rs(h), es(c), stack(c)
        print("EVIDENCE refused_battle: %s" % js({"provoke": pev, "refused line s": s, "RS host": rh,
                                                  "RS client": rs(c), "host stack": stack(h), "client stack": cst}),
              flush=True)
        if s is None:
            raise Stop("WAIT the host's %r line: timed out after %.0f s" % (REFUSED, W_FAIL))
        fired, rr, sm = since(h, nh, CORRUPT_FIRED), since(h, nh, REFUSE_RECV % x.b0), since(c, nc, SHA_MISMATCH % x.b0)
        r.cell("refused_battle-1", "GUARD", "the repair offered (host RS offered +1), the test hook fired on it +1, "
               "the client refused it (reason=corrupt), client phase Idle, client top %s" % HOLD,
               delta(rh0, rh, "offered") == 1 and len(fired) == 1 and len(rr) == 1 and len(sm) == 1
               and ec.get("phase") == "Idle" and cst[-1:] == [HOLD],
               {"offered": delta(rh0, rh, "offered"), "hook": fired, "host refuse": rr, "client sha": sm,
                "client phase": ec.get("phase"), "client top": cst[-1:]})
        # the 62 re-words its title on its own 500 ms think gate (CoopState::think), up to 500 ms after the REFUSED
        # line; wait (bounded) until the title has left the repair-in-flight wording, then HOLD_S as written
        tw = wait_t(lambda: not (dlg(h).get("title") or "").startswith(TITLE_REPAIRING), W_TITLE)
        print("EVIDENCE refused_battle title settle: %s" % js({"s": tw, "title": dlg(h).get("title")}), flush=True)
        polls = hold(x, rh0)
        rh = rs(h)
        r.cell("refused_battle-2", "FIX", "host RS failed +1, lastFail 'refused'",
               delta(rh0, rh, "failed") == 1 and rh.get("lastFail") == "refused",
               {"failed": delta(rh0, rh, "failed"), "lastFail": rh.get("lastFail"), "RS host": rh})
        bad = [p for p in polls if not (p["host top"] == [CSTATE] and p["phase"] == "Active" and p["peerAbsent"] is True
                                        and p["62"].get("code") == 62 and p["62"].get("backVisible") is False
                                        and p["62"].get("saveQuitVisible") is True and p["62"].get("abandonVisible") is True
                                        and p["offered"] == 1 and p["client top"] == cst[-1:] and p["client desyncSeen"] is True)]
        r.cell("refused_battle-3", "GUARD", "at every HOLD_S poll: host phase Active, peerAbsent true, 62 on top "
               "(back hidden, SAVE & QUIT / ABANDON shown), offered unchanged (no loop), client top unchanged, "
               "client desyncSeen true", bool(polls) and not bad,
               {"polls": len(polls), "violations": bad[:3], "62 seen": distinct(polls, "62"),
                "client top seen": distinct(polls, "client top")})
        eok, eev, cap = escape(x)
        r.cell("refused_battle-4", "GUARD", "the escape: host ABANDON -> host MainMenuState <= %.0f s; "
               "client 21 <= %.0f s; client OK -> MainMenuState <= %.0f s" % (W_HOST_MENU, W_CLIENT_21, W_CLIENT_MENU),
               eok, eev)
        title_cell(r, "refused_battle-5", polls, "refused_battle")
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end("refused_battle-6", results, walls, cap)


def row_copy_mismatch(x, results, walls):
    r = Row("copy_mismatch", ["copy_mismatch-%d" % i for i in range(1, 7)], x)
    h, c, cap = x.host, x.client, None
    try:
        rh0, rc0, nh, nc = rs(h), rs(c), len(log(h)), len(log(c))
        pev = provoke(x, "resync_ready_mismatch")
        s = wait_t(lambda: since(h, nh, READY_MISMATCH % x.b0), W_FAIL)
        time.sleep(POLL)  # the 68 push follows the load on the client's next frames
        rh, rc, cst, cd = rs(h), rs(c), stack(c), dlg(c)
        print("EVIDENCE copy_mismatch: %s" % js({"provoke": pev, "mismatch line s": s, "RS host": rh, "RS client": rc,
                                                 "host stack": stack(h), "client stack": cst,
                                                 "hook": since(h, nh, MISMATCH_FIRED), "offer": since(h, nh, OFFER),
                                                 "client active": since(c, nc, CLIENT_ACTIVE % x.b0)}), flush=True)
        if s is None:
            raise Stop("WAIT the host's %r line: timed out after %.0f s" % (READY_MISMATCH % x.b0, W_FAIL))
        rd = since(h, nh, REJOIN_DESYNC)
        r.cell("copy_mismatch-1", "GUARD",
               "offered +1; client RS loaded +1; host %r +1; client top CoopState 68" % REJOIN_DESYNC,
               delta(rh0, rh, "offered") == 1 and delta(rc0, rc, "loaded") == 1 and len(rd) == 1 and cst[-1:] == [CSTATE]
               and cd.get("code") == 68, {"offered": delta(rh0, rh, "offered"), "loaded": delta(rc0, rc, "loaded"), "rejoin desync": rd,
                                          "client top": cst[-1:], "client dialog": cd})
        # as in refused_battle: the 62 re-words its title on its own 500 ms think gate (CoopState::think), up to 500 ms
        # after the mismatch line; wait (bounded) until the title has left the repair-in-flight wording, then HOLD_S as
        # written
        tw = wait_t(lambda: not (dlg(h).get("title") or "").startswith(TITLE_REPAIRING), W_TITLE)
        print("EVIDENCE copy_mismatch title settle: %s" % js({"s": tw, "title": dlg(h).get("title")}), flush=True)
        polls = hold(x, rh0)
        rh = rs(h)
        r.cell("copy_mismatch-2", "FIX", "no RESUME: at every HOLD_S poll the host's 62 has backVisible false "
               "(without failed-repair handling: true, 'All players connected')",
               bool(polls) and all(p["62"].get("code") == 62 and p["62"].get("backVisible") is False for p in polls),
               {"polls": len(polls), "62 seen": distinct(polls, "62")})
        r.cell("copy_mismatch-3", "FIX", "host RS failed +1, lastFail 'ready mismatch'",
               delta(rh0, rh, "failed") == 1 and rh.get("lastFail") == "ready mismatch",
               {"failed": delta(rh0, rh, "failed"), "lastFail": rh.get("lastFail"), "RS host": rh})
        bad = [p for p in polls if not (p["offered"] == 1 and p["peerAbsent"] is True and p["client top"] == [CSTATE]
                                        and p["client code"] == 68)]
        r.cell("copy_mismatch-4", "GUARD",
               "no second offer; host peerAbsent true; the client still on 68 (no campaign_begun) at every HOLD_S poll",
               bool(polls) and not bad and delta(rh0, rh, "offered") == 1,
               {"violations": bad[:3], "offered": delta(rh0, rh, "offered"), "peerAbsent seen": distinct(polls, "peerAbsent"),
                "client code seen": distinct(polls, "client code")})
        title_cell(r, "copy_mismatch-5", polls, "copy_mismatch")
        eok, eev, cap = escape(x)
        r.cell("copy_mismatch-6", "FIX", "the escape as refused_battle-4 (without failed-repair handling the 62 shows "
               "RESUME and hides ABANDON: the refused ABANDON fails at once)", eok, eev)
    except Exception as e:
        r.stop(e)
    r.end("copy_mismatch-7", results, walls, cap)


def boot(key, tag):
    """test_delta_core's boot on the row's own lobby key -> x (x.err set on a miss: setup failure)"""
    x = SimpleNamespace(host=None, client=None, err=None, b0=None, t_press=None)
    try:
        x.host, x.client = GameClient("host", 1, make_user_dir(tag + "_host")), GameClient("client", 2, make_user_dir(tag + "_client"))
        raw.bring_up_lobby(x.host, x.client, key)
        session.drive_to_battlescape(x.host, x.client, {}, seat_count=2, pre_ok=lambda gc: gc.ok({"cmd": "set_seed", "seed": SEED_MAP}))
        hs, cs = session.battle_state(x.host), session.battle_state(x.client)
        fp = [hs.get("mapFingerprint"), cs.get("mapFingerprint")]
        assert fp == [MAP_FP, MAP_FP], "SETUP-FAILURE: mapFingerprint %s (MAP_FP %r, SEED_MAP %d)" % (fp, MAP_FP, SEED_MAP)
        pinned = session.pin_ai_neutral(x.host, x.client, tag=tag)
        assert pinned, "SETUP-FAILURE: pin_ai_neutral pinned no NONE-seat non-player unit"
        session.wait_host_idle(x.host, x.client, timeout=30)
        session.assert_hash_clean(x.host, x.client, full=True, what="boot " + tag)
        s0 = sorted(u["id"] for u in hs.get("units") or [] if u.get("faction") == 0 and not u.get("isOut") and u.get("coop") == 0)
        assert s0[:2] == [H, H2], "SETUP-FAILURE: seat-0 soldiers %s (want H %d, H2 %d)" % (s0, H, H2)
        b = [(session.battle_state(gc).get("authority") or {}).get("battleId") for gc in (x.host, x.client)]
        assert b[0] and b[0] == b[1], "SETUP-FAILURE: battleId %s" % b
        x.b0 = b[0]
        print("[test_desync_resync_fail] boot %s ok: key %s, MAP_FP %r, pinned %s, B0 %s"
              % (tag, key, MAP_FP, pinned, x.b0), flush=True)
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


ROWS = (("refused_battle", "48753", "resync_fail_refused", row_refused_battle),
        ("copy_mismatch", "48754", "resync_fail_mismatch", row_copy_mismatch))


def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for rid, key, tag, fn in ROWS:
        tb = time.time()
        x = boot(key, tag)
        walls["boot " + rid] = round(time.time() - tb, 1)
        if x.err:
            print("EVIDENCE %s boot: %s\nCAPTURE %s boot: %s" % (rid, x.err, rid, js(capture(x))), flush=True)
            print("FAIL %s boot: the boot did not reach the tactical map with its pins" % rid, flush=True)
            results[rid] = False
        else:
            fn(x, results, walls)
        failed += shut(x)
    failed += [rid for rid, _k, _t, _fn in ROWS if not results.get(rid)]
    print("\ntest_desync_resync_fail: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid, _k, _t, _fn in ROWS if results.get(rid)), len(ROWS), failed, js(walls), time.time() - t0), flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
