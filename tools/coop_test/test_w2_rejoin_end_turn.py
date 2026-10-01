"""W2-H14 - a rejoiner's END TURN side-phase counter starts at the host's (spec w2h14_rejoin_endturn_seed.md (f);
SM-2; F4012). TWO boots on test_w2_death_side's default map, each shut down before the next: P (parallel, PORT_P),
T (traditional, PORT_T). Each plays one END TURN cycle, the client leaves, a fresh process (client2) rejoins, the host
presses RESUME (SPEC 16). H14-1 (P): an END TURN cycle with client2 completes. H14-2 (T): client2 holds the baton and
its pass completes the cycle. A boot/rejoin step past its bound is a FIXTURE-STOP (one CAPTURE line; the row FAILs
"boot"/"rejoin"). Each row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <msg>"; both rows run.
WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when both rows pass, 2 otherwise."""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import test_w2_host_combat as hc
from test_w2_death_side import (SEED_MAP_D, MAP_FP_D, A_ID, DS1_ID, DS2_ID, FACTION_PLAYER, FACTION_HOSTILE,
                                COOP_SEAT_0, COOP_SEAT_1, CYCLE_SIDE_TRANSITIONS)
from test_skirmish_rejoin_battle import (drop_client_mid_battle, rejoin_skirmish, dialog, in_battle_save, top,
                                         states, has, COOP_DLG_WAIT_PLAYERS, COOP_DLG_CLIENT_RESUME_HOLD)
from test_w2_delta_core import end_turn_cycle, settle_on_battlescape, short, desync_record
from test_rw_turn_baton import drive_full_cycle
from test_rw_turn_mode import set_mode, live_mode, TRADITIONAL

PORT_P, PORT_T = "48514", "48523"   # this file's lobby ports (unused by every other test file)
# TASK 0 (ledger `## W2-H14 TASK 0 DONE`, docs rewrite/w2h14-task0/CONSTANTS.md; 2/2 boots each, identical)
K_P = 3                             # parallel: both counters after one END TURN cycle (the host keeps it at the pause)
K_T = 3                             # traditional: baton 0 -> 1 -> 0 -> 1; both counters after the cycle
SEED_RE = re.compile(r"W2-H14: rejoin END TURN side-phase counter seeded to (-?\d+)")
BATON_NEEDLE = "[coop-baton] battle save carried coopActiveSeat=1"    # F4058; keep the =1 suffix (F4075)
OFFER_NEEDLE = "SPEC16 M5: rejoin battle_offer sent"
IDLE_S, CYCLE_S, SEAT_S, LOG_FLUSH_S = 30, 60, 15, 3
PC, TS = "coopEndTurnPhaseCounter", "coopEndTurnTalliesSeen"
EK = (PC, TS, "coopEndTurnTally", "coopActiveSeat", "coopPendingTallyTurn", "turnMode", "desyncSeen")
BK = ("turn", "side", "phase", "coopEndTurnText", "coopEndTurnArmed", "coopOffBatonGray")
PROBES = (("event_state", event_state), ("battle_state", battle_state), ("dialog", dialog), ("stack", states))

class FixtureMiss(Exception):
    pass

def snap(gc):
    e, b = event_state(gc), battle_state(gc)
    return dict({k: e.get(k) for k in EK}, **{k: b.get(k) for k in BK})

def log_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except OSError:
        return []

def log_count(gc, needle):
    return sum(1 for ln in log_lines(gc) if needle in ln)

def seeded(gc):
    return [int(m.group(1)) for m in (SEED_RE.search(ln) for ln in log_lines(gc)) if m]

def evidence(rid, obj):
    print(f"EVIDENCE {rid}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)

def miss(name, err, machines):
    """FIXTURE-STOP: CAPTURE every machine's event_state, battle_state, dialog and stack (whole), then raise."""
    cap = {}
    for gc in machines:
        cap[gc.name] = {}
        for k, probe in PROBES:
            try:
                cap[gc.name][k] = probe(gc)
            except Exception as e:
                cap[gc.name][k] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:400]}")

def step(name, fn, machines):
    try:
        return fn()
    except Exception as e:
        miss(name, short(e, 800), machines)

def check(name, bad, machines):
    if bad:
        miss(name, "; ".join(bad), machines)

def wait_both(host, other, what, pred, timeout):
    host.wait_for(what, lambda: (pred(event_state(host)) and pred(event_state(other))) or None,
                  timeout=timeout, interval=0.25)

def boot(host, client, port, traditional):
    """Copy of H12's boot() (test_w2_death_side.boot_default) on `port`; T: pre_ok = set_mode TRADITIONAL, set_seed."""
    hc.bring_up_lobby_roster_pinned(host, client, port)
    session.drive_to_battlescape(host, client, {}, seat_count=2, pre_ok=lambda h: (
        set_mode(h, TRADITIONAL) if traditional else None, h.ok({"cmd": "set_seed", "seed": SEED_MAP_D})))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP_D and cs.get("mapFingerprint") == MAP_FP_D, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (baked {MAP_FP_D!r})")
    assert pin_ai_neutral(host, client, tag="w2h14"), "pin_ai_neutral pinned no NONE-seat non-player unit"
    ub = session.units_by_id(hs)
    for uid, seat in ((DS1_ID, COOP_SEAT_0), (DS2_ID, COOP_SEAT_1)):
        u = ub.get(uid) or {}
        assert (u.get("faction") == FACTION_PLAYER and u.get("coop") == seat and not u.get("isOut")
                and u.get("onTile")), f"unit {uid} at bring-up: {u} (want a live player soldier of seat {seat})"
    a = ub.get(A_ID) or {}
    assert a.get("faction") == FACTION_HOSTILE and not a.get("isOut"), f"alien {A_ID} at bring-up: {a}"
    session.wait_host_idle(host, client, timeout=IDLE_S)
    assert_hash_clean(host, client, full=True, what="bring-up")

def stage_p(host, client, ctx):
    """Boot P preconditions: H12's boot, one END TURN cycle (notes empty), both counters K_P, no desync."""
    m = (host, client)
    step("boot P", lambda: boot(host, client, PORT_P, False), m)
    ctx["booted"] = True
    pre, notes = {"host": snap(host), "client": snap(client)}, []
    end_turn_cycle(host, client, notes)
    post = {"host": snap(host), "client": snap(client)}
    evidence("boot P cycle", {"pre": pre, "post": post, "notes": notes})
    bad = [f"notes {notes}"] if notes else []
    for who, gc in (("host", host), ("client", client)):
        a, b = pre[who], post[who]
        if a["turn"] is None or b["turn"] != a["turn"] + 1 or b["side"] != FACTION_PLAYER:
            bad.append(f"{who} turn/side {a['turn']}/{a['side']} -> {b['turn']}/{b['side']} (want +1, player)")
        if b[PC] != K_P:
            bad.append(f"{who} {PC} {b[PC]} (want K_P = {K_P})")
        if b["desyncSeen"]:
            bad.append(f"{who} desyncSeen true: {desync_record(gc, True)}")
    check("boot P cycle preconditions", bad, m)

def stage_t(host, client, ctx):
    """Boot T preconditions: traditional on both; baton 0 -> 1 -> cycle (counters K_T, baton 0) -> 1."""
    m = (host, client)
    step("boot T", lambda: boot(host, client, PORT_T, True), m)
    ctx["booted"] = True
    modes, entry = [live_mode(host), live_mode(client)], {"host": snap(host), "client": snap(client)}
    evidence("boot T entry", {"liveMode": modes, "entry": entry})
    seats = [entry["host"]["coopActiveSeat"], entry["client"]["coopActiveSeat"]]
    check("boot T entry preconditions", [x for x, ok in (
        (f"live_mode {modes} (want traditional on both)", modes == [TRADITIONAL, TRADITIONAL]),
        (f"entry coopActiveSeat (host, client) {seats} (want [0, 0])", seats == [0, 0])) if not ok], m)
    turn0 = entry["host"]["turn"]

    def host_pass():
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        wait_both(host, client, "coopActiveSeat 1 on both", lambda e: e.get("coopActiveSeat") == 1, SEAT_S)

    def client_last_pass():
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_full_cycle(host, client, turn0, timeout=CYCLE_S)
        settle_on_battlescape(host)
        settle_on_battlescape(client)
        session.wait_host_idle(host, client, timeout=IDLE_S)
        wait_both(host, client, f"{PC} K_T, coopActiveSeat 0 and coopPendingTallyTurn -1 on both",
                  lambda e: (e.get(PC) == K_T and e.get("coopActiveSeat") == 0
                             and e.get("coopPendingTallyTurn") == -1), SEAT_S)
    step("T1 host END TURN -> coopActiveSeat 1 on both", host_pass, m)
    step("T2 client END TURN -> full cycle, settle, idle, counters K_T, baton 0", client_last_pass, m)
    cyc = {"host": snap(host), "client": snap(client)}
    evidence("boot T cycle", cyc)
    check("boot T cycle preconditions", [f"{w} turn {c['turn']} (want {turn0} + 1), desyncSeen {c['desyncSeen']}"
                                         for w, c in cyc.items() if c["turn"] != turn0 + 1 or c["desyncSeen"]], m)
    step("T3 host END TURN -> coopActiveSeat 1 on both", host_pass, m)

def stage_rejoin(host, client, port, kind, ctx):
    """H12's leave + rejoin steps 1-9 (copied), each bounded; then S0. Returns client2."""
    m = [host, client]
    bid0 = (battle_state(host).get("authority") or {}).get("battleId")
    step("1 drop_client_mid_battle", lambda: drop_client_mid_battle(host, client), m)
    pause = snap(host)
    evidence(f"pause {kind}", {"host": pause})
    if kind == "T" and pause["coopActiveSeat"] != 1:
        miss("host coopActiveSeat 1 at the pause (D91)", f"host coopActiveSeat {pause['coopActiveSeat']}", m)
    client2 = ctx["client2"] = GameClient("rejoin", None, make_user_dir(f"w2h14_end_turn_{kind.lower()}_rejoin"))
    m.append(client2)
    step("3 client2 spawn and connect", lambda: (client2.spawn(), client2.connect()), m)
    step("4 rejoin_skirmish", lambda: rejoin_skirmish(client2, port), m)

    def s5():
        client2.wait_for("client2 back in the battle", lambda: in_battle_save(client2) or None, timeout=240)
        client2.wait_for("client2 held on dialog 68 over BattlescapeState",
                         lambda: (has(client2, "BattlescapeState")
                                  and dialog(client2).get("code") == COOP_DLG_CLIENT_RESUME_HOLD) or None,
                         timeout=60, interval=0.5)

    def s6():
        def offered():
            if session.has_state(host, "Profile"):        # the join's popup sits over the dialog
                return host.cmd({"cmd": "profile_ok"}) and None
            return dialog(host).get("backVisible") or None
        host.wait_for("host dialog offers RESUME", offered, timeout=120, interval=0.5)
        d = dialog(host)
        assert d.get("code") == COOP_DLG_WAIT_PLAYERS and d.get("backText") == "RESUME", f"host dialog {d}"

    def s7():
        host.ok({"cmd": "coop_dialog_back"})
        for gc in (host, client2):
            gc.wait_for(f"{gc.name} top BattlescapeState", lambda gc=gc: (top(gc) == "BattlescapeState") or None,
                        timeout=120, interval=0.5)

    def s8():
        for gc in (host, client2):
            gc.wait_for(f"{gc.name} phase Active", lambda gc=gc: (battle_state(gc).get("phase") == "Active") or None,
                        timeout=120, interval=0.5)
        ha, ca = (battle_state(gc).get("authority") or {} for gc in (host, client2))
        assert ha.get("peerAbsent") is False, f"host peerAbsent: {ha}"
        assert ha.get("battleId") == ca.get("battleId") == bid0, (
            f"battleId before={bid0} host={ha.get('battleId')} client2={ca.get('battleId')}")
    step("5 client2 in the battle, held on dialog 68", s5, m)
    step("6 host offers RESUME", s6, m)
    step("7 RESUME, both tops BattlescapeState", s7, m)
    step("8 phase Active on both, peerAbsent false, battleId unchanged", s8, m)
    step("9 wait_host_idle(host, client2)", lambda: session.wait_host_idle(host, client2, timeout=IDLE_S), m)
    time.sleep(LOG_FLUSH_S)
    s0 = ctx["S0"] = {"host": snap(host), "client2": snap(client2), "client2Seeded": seeded(client2),
                      "client2BatonLines": log_count(client2, BATON_NEEDLE),
                      "hostOfferLines": log_count(host, OFFER_NEEDLE)}
    evidence(f"S0 {kind}", s0)
    got = (s0["client2"]["coopActiveSeat"], s0["client2"]["coopOffBatonGray"], s0["client2BatonLines"])
    if kind == "T" and not (got[0] == 1 and got[1] is False and got[2] == 1):
        miss("client2 holds the baton after the rejoin (F4058)", f"client2 (coopActiveSeat, coopOffBatonGray, "
             f"'{BATON_NEEDLE}' lines) = {got} (want (1, False, 1))", m)
    return client2

def verdict(rid, host, c2, s0, h1, c1, k, notes, stale_msg, stale, ev):
    """EVIDENCE, then the failing GREEN cells both rows share (S0 = (k, k), one seed line of k, turn +1, side player
    and counters k + 3 on both, full hash clean, no desync). The RED shape (TASK 0's negative control: S0 = (k, 0), host
    talliesSeen +1 = the stale answer, turn/side unchanged, the row's own `stale` cell) leads as `stale_msg`."""
    h0, c0, hashf = s0["host"], s0["client2"], []
    try:
        assert_hash_clean(host, c2, full=True, what=f"after {rid}")
    except AssertionError as e:
        hashf = [f"hash after {rid}: {short(e, 500)}"]
    stale = bool(stale and (h0[PC], c0[PC]) == (k, 0) and h1[TS] - h0[TS] == 1
                 and [(x["turn"], x["side"]) for x in (h1, c1)] == [(x["turn"], x["side"]) for x in (h0, c0)])
    evidence(rid, dict(ev, S0=s0, after={"host": h1, "client2": c1}, notes=notes, hash=hashf, staleShape=stale,
                       hostTalliesSeenDelta=h1[TS] - h0[TS], client2TalliesSeenDelta=c1[TS] - c0[TS]))
    f = [stale_msg] if stale else []
    if (h0[PC], c0[PC]) != (k, k):
        f.append(f"S0 {PC} (host, client2) = ({h0[PC]}, {c0[PC]}) (want ({k}, {k}))")
    if s0["client2Seeded"] != [k]:
        f.append(f"client2 seeded lines {s0['client2Seeded']} (want exactly [{k}])")
    if notes:
        f.append(f"notes {notes}")
    for who, a, b in (("host", h0, h1), ("client2", c0, c1)):
        if a["turn"] is None or b["turn"] != a["turn"] + 1 or b["side"] != FACTION_PLAYER:
            f.append(f"{who} turn/side {a['turn']}/{a['side']} -> {b['turn']}/{b['side']} (want +1, player)")
        if b[PC] != k + CYCLE_SIDE_TRANSITIONS:
            f.append(f"{who} {PC} {b[PC]} (want {k} + {CYCLE_SIDE_TRANSITIONS})")
    return f, hashf + [f"desyncSeen true on {gc.name}: {desync_record(gc, True)}"
                       for gc in (host, c2) if event_state(gc).get("desyncSeen")]

def h14_1(host, c2, ctx):
    """Parallel: end_turn_cycle(host, client2); RED cell: client2's tally turn == K_P (the host's stale answer)."""
    s0, notes = ctx["S0"], []
    end_turn_cycle(host, c2, notes)
    h1, c1 = snap(host), snap(c2)
    tally_turn, c0 = (c1["coopEndTurnTally"] or {}).get("turn"), s0["client2"]
    f, tail = verdict("H14-1", host, c2, s0, h1, c1, K_P, notes, "the rejoiner's press was dropped as stale",
                      tally_turn == K_P, {"client2TallyTurn": tally_turn})
    if not c1[TS] > c0[TS]:
        f.append(f"client2 {TS} {c0[TS]} -> {c1[TS]} (want it to grow)")
    return f + tail

def h14_2(host, c2, ctx):
    """Traditional: client2's pass, full cycle, baton 0; RED cells: host baton still 1, client2 pending == K_T."""
    s0, notes, t = ctx["S0"], [], time.time()
    press = c2.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    try:
        assert press.get("ok"), f"client2 end_turn_button refused: {press}"
        drive_full_cycle(host, c2, s0["host"]["turn"], timeout=CYCLE_S)
        settle_on_battlescape(host)
        settle_on_battlescape(c2)
        session.wait_host_idle(host, c2, timeout=IDLE_S)
        host.wait_for("coopActiveSeat 0 on both and client2 coopPendingTallyTurn -1", lambda: (
            event_state(host).get("coopActiveSeat") == 0
            and [event_state(c2).get(x) for x in ("coopActiveSeat", "coopPendingTallyTurn")] == [0, -1]) or None,
            timeout=SEAT_S, interval=0.25)
    except Exception as e:
        notes.append(f"client2 pass cycle: {short(e)}")
    waited = round(time.time() - t, 1)
    h1, c1 = snap(host), snap(c2)
    f, tail = verdict("H14-2", host, c2, s0, h1, c1, K_T, notes, "the rejoiner's pass was dropped as stale",
                      h1["coopActiveSeat"] == 1 and c1["coopPendingTallyTurn"] == K_T,
                      {"press": press, "waitedS": waited})
    if [h1["coopActiveSeat"], c1["coopActiveSeat"]] != [0, 0]:
        f.append(f"coopActiveSeat host {h1['coopActiveSeat']} client2 {c1['coopActiveSeat']} (want 0 on both)")
    if c1["coopPendingTallyTurn"] != -1:
        f.append(f"client2 coopPendingTallyTurn {c1['coopPendingTallyTurn']} (want -1)")
    return f + tail

BOOTS = (("P", PORT_P, stage_p, "H14-1", h14_1), ("T", PORT_T, stage_t, "H14-2", h14_2))

def run_boot(kind, port, stage_fn, rid, row_fn, results, walls):
    t0, ctx = time.time(), {}
    host = GameClient("host", None, make_user_dir(f"w2h14_end_turn_{kind.lower()}_host"))
    client = GameClient("client", None, make_user_dir(f"w2h14_end_turn_{kind.lower()}_client"))
    try:
        try:
            stage_fn(host, client, ctx)
            c2 = stage_rejoin(host, client, port, kind, ctx)
        except Exception as e:     # a FixtureMiss printed its CAPTURE line; anything else is unexpected, still a FAIL
            print(f"FAIL {rid}: {'rejoin' if ctx.get('booted') else 'boot'} (FIXTURE-STOP) "
                  f"{e if isinstance(e, FixtureMiss) else short(e, 600)}", flush=True)
            return
        try:
            f = row_fn(host, c2, ctx)
        except Exception as e:
            f = [f"{type(e).__name__}: {short(e, 600)}"]
        results[rid] = not f
        print(f"PASS {rid}" if not f else f"FAIL {rid}: " + "; ".join(f), flush=True)
    finally:
        for gc in [g for g in (host, client, ctx.get("client2")) if g is not None]:
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2h14] shutdown {gc.name}: {short(e)}", flush=True)
        walls[kind] = round(time.time() - t0, 1)

def main():
    t0, results, walls = time.time(), {}, {}
    for kind, port, stage_fn, rid, row_fn in BOOTS:
        run_boot(kind, port, stage_fn, rid, row_fn, results, walls)
    rids = [b[3] for b in BOOTS]
    passed, failed = [r for r in rids if results.get(r)], [r for r in rids if not results.get(r)]
    print(f"\ntest_w2_rejoin_end_turn: {len(passed)}/{len(rids)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
