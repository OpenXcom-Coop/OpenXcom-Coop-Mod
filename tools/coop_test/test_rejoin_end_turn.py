"""A rejoiner's END TURN side-phase counter starts at the host's. TWO boots on test_death_side's default map, each shut
down before the next: parallel (PORT_PARALLEL) and traditional (PORT_TRADITIONAL). Each plays one END TURN cycle, the
client leaves, a fresh process (client2) rejoins, the host presses RESUME. rejoiner_cycle (parallel): an END TURN cycle
with client2 completes. rejoiner_tally (traditional): client2's tally equals the host's. rejoiner_pass (traditional):
client2 holds the baton and its pass completes the cycle. A boot/rejoin step past its bound is a setup failure (one
CAPTURE line; the row FAILs "boot"/"rejoin"). Each row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL
<id>: <msg>"; every row runs. ONE foreground run, no skip path; exit 0 only when every row passes, 2 otherwise."""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import test_host_combat as hc
from test_death_side import (SEED_MAP_DEFAULT, MAP_FP_DEFAULT, A_ID, HOST_SOLDIER_ID, CLIENT_SOLDIER_ID,
                                FACTION_PLAYER, FACTION_HOSTILE, COOP_SEAT_0, COOP_SEAT_1, CYCLE_SIDE_TRANSITIONS)
from test_skirmish_rejoin_battle import (drop_client_mid_battle, rejoin_skirmish, dialog, in_battle_save, top,
                                         states, has, COOP_DLG_WAIT_PLAYERS, COOP_DLG_CLIENT_RESUME_HOLD)
from test_delta_core import end_turn_cycle, settle_on_battlescape, short, desync_record
from test_turn_baton import drive_full_cycle
from test_turn_mode import set_mode, live_mode, TRADITIONAL

PORT_PARALLEL, PORT_TRADITIONAL = "48514", "48523"   # this file's lobby ports (unused by every other test file)
# measured on two boots of each mode, identical
K_PARALLEL = 3                      # parallel: both counters after one END TURN cycle (the host keeps it at the pause)
K_TRADITIONAL = 3                   # traditional: baton 0 -> 1 -> 0 -> 1; both counters after the cycle
SEED_RE = re.compile(r"rejoin END TURN side-phase counter seeded to (-?\d+)")
BATON_NEEDLE = "[coop-baton] battle save carried coopActiveSeat=1"    # keep the =1 suffix
OFFER_NEEDLE = "rejoin battle_offer sent"
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

DROP_RE = re.compile(r"rejoin dropped (\d+) END TURN press")    # the host's drop line

def dropped(gc):
    return [int(m.group(1)) for m in (DROP_RE.search(ln) for ln in log_lines(gc)) if m]

def evidence(rid, obj):
    print(f"EVIDENCE {rid}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)

def miss(name, err, machines):
    """A setup failure: CAPTURE every machine's event_state, battle_state, dialog and stack (whole), then raise."""
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
    """Copy of test_death_side.boot_default on `port`; traditional: pre_ok = set_mode TRADITIONAL, set_seed."""
    hc.bring_up_lobby_roster_pinned(host, client, port)
    session.drive_to_battlescape(host, client, {}, seat_count=2, pre_ok=lambda h: (
        set_mode(h, TRADITIONAL) if traditional else None, h.ok({"cmd": "set_seed", "seed": SEED_MAP_DEFAULT})))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP_DEFAULT and cs.get("mapFingerprint") == MAP_FP_DEFAULT, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} "
        f"(baked {MAP_FP_DEFAULT!r})")
    assert pin_ai_neutral(host, client, tag="rejoin_end_turn"), "pin_ai_neutral pinned no NONE-seat non-player unit"
    ub = session.units_by_id(hs)
    for uid, seat in ((HOST_SOLDIER_ID, COOP_SEAT_0), (CLIENT_SOLDIER_ID, COOP_SEAT_1)):
        u = ub.get(uid) or {}
        assert (u.get("faction") == FACTION_PLAYER and u.get("coop") == seat and not u.get("isOut")
                and u.get("onTile")), f"unit {uid} at bring-up: {u} (want a live player soldier of seat {seat})"
    a = ub.get(A_ID) or {}
    assert a.get("faction") == FACTION_HOSTILE and not a.get("isOut"), f"alien {A_ID} at bring-up: {a}"
    session.wait_host_idle(host, client, timeout=IDLE_S)
    assert_hash_clean(host, client, full=True, what="bring-up")

def stage_parallel(host, client, ctx):
    """Parallel boot: boot(), one END TURN cycle (notes empty), both counters K_PARALLEL, no desync."""
    m = (host, client)
    step("parallel boot", lambda: boot(host, client, PORT_PARALLEL, False), m)
    ctx["booted"] = True
    pre, notes = {"host": snap(host), "client": snap(client)}, []
    end_turn_cycle(host, client, notes)
    post = {"host": snap(host), "client": snap(client)}
    evidence("parallel boot cycle", {"pre": pre, "post": post, "notes": notes})
    bad = [f"notes {notes}"] if notes else []
    for who, gc in (("host", host), ("client", client)):
        a, b = pre[who], post[who]
        if a["turn"] is None or b["turn"] != a["turn"] + 1 or b["side"] != FACTION_PLAYER:
            bad.append(f"{who} turn/side {a['turn']}/{a['side']} -> {b['turn']}/{b['side']} (want +1, player)")
        if b[PC] != K_PARALLEL:
            bad.append(f"{who} {PC} {b[PC]} (want K_PARALLEL = {K_PARALLEL})")
        if b["desyncSeen"]:
            bad.append(f"{who} desyncSeen true: {desync_record(gc, True)}")
    check("parallel boot cycle preconditions", bad, m)

def stage_traditional(host, client, ctx):
    """Traditional boot: traditional on both; baton 0 -> 1 -> cycle (counters K_TRADITIONAL, baton 0) -> 1."""
    m = (host, client)
    step("traditional boot", lambda: boot(host, client, PORT_TRADITIONAL, True), m)
    ctx["booted"] = True
    modes, entry = [live_mode(host), live_mode(client)], {"host": snap(host), "client": snap(client)}
    evidence("traditional boot entry", {"liveMode": modes, "entry": entry})
    seats = [entry["host"]["coopActiveSeat"], entry["client"]["coopActiveSeat"]]
    check("traditional boot entry preconditions", [x for x, ok in (
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
        wait_both(host, client, f"{PC} K_TRADITIONAL, coopActiveSeat 0 and coopPendingTallyTurn -1 on both",
                  lambda e: (e.get(PC) == K_TRADITIONAL and e.get("coopActiveSeat") == 0
                             and e.get("coopPendingTallyTurn") == -1), SEAT_S)
    step("host END TURN -> coopActiveSeat 1 on both", host_pass, m)
    step("client END TURN -> full cycle, settle, idle, counters K_TRADITIONAL, baton 0", client_last_pass, m)
    cyc = {"host": snap(host), "client": snap(client)}
    evidence("traditional boot cycle", cyc)
    check("traditional boot cycle preconditions", [f"{w} turn {c['turn']} (want {turn0} + 1), desyncSeen "
          f"{c['desyncSeen']}" for w, c in cyc.items() if c["turn"] != turn0 + 1 or c["desyncSeen"]], m)
    step("host END TURN again -> coopActiveSeat 1 on both", host_pass, m)

def stage_rejoin(host, client, port, kind, ctx):
    """The leave and rejoin steps 1-9, each bounded; then the afterRejoin snapshot. Returns client2."""
    m = [host, client]
    bid0 = (battle_state(host).get("authority") or {}).get("battleId")
    step("1 drop_client_mid_battle", lambda: drop_client_mid_battle(host, client), m)
    pause = snap(host)
    ctx["pause"] = pause
    evidence(f"pause {kind}", {"host": pause})
    if kind == "traditional" and pause["coopActiveSeat"] != 1:
        miss("host coopActiveSeat 1 at the pause", f"host coopActiveSeat {pause['coopActiveSeat']}", m)
    client2 = ctx["client2"] = GameClient("rejoin", None, make_user_dir(f"rejoin_end_turn_{kind.lower()}_rejoin"))
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
    s0 = ctx["afterRejoin"] = {"host": snap(host), "client2": snap(client2), "client2Seeded": seeded(client2),
                      "client2BatonLines": log_count(client2, BATON_NEEDLE),
                      "hostOfferLines": log_count(host, OFFER_NEEDLE)}
    evidence(f"afterRejoin {kind}", s0)
    got = (s0["client2"]["coopActiveSeat"], s0["client2"]["coopOffBatonGray"], s0["client2BatonLines"])
    if kind == "traditional" and not (got[0] == 1 and got[1] is False and got[2] == 1):
        miss("client2 holds the baton after the rejoin", f"client2 (coopActiveSeat, coopOffBatonGray, "
             f"'{BATON_NEEDLE}' lines) = {got} (want (1, False, 1))", m)
    return client2

def verdict(rid, host, c2, s0, h1, c1, k, notes, stale_msg, stale, ev):
    """EVIDENCE, then the failing cells both rows share (afterRejoin = (k, k), one seed line of k, turn +1, side
    player and counters k + 3 on both, full hash clean, no desync). The shape seen without the fix (afterRejoin =
    (k, 0), host talliesSeen +1 = the stale answer, turn/side unchanged, the row's own `stale` cell) leads as
    `stale_msg`."""
    h0, c0, hashf = s0["host"], s0["client2"], []
    try:
        assert_hash_clean(host, c2, full=True, what=f"after {rid}")
    except AssertionError as e:
        hashf = [f"hash after {rid}: {short(e, 500)}"]
    stale = bool(stale and (h0[PC], c0[PC]) == (k, 0) and h1[TS] - h0[TS] == 1
                 and [(x["turn"], x["side"]) for x in (h1, c1)] == [(x["turn"], x["side"]) for x in (h0, c0)])
    evidence(rid, dict(ev, afterRejoin=s0, after={"host": h1, "client2": c1}, notes=notes, hash=hashf, staleShape=stale,
                       hostTalliesSeenDelta=h1[TS] - h0[TS], client2TalliesSeenDelta=c1[TS] - c0[TS]))
    f = [stale_msg] if stale else []
    if (h0[PC], c0[PC]) != (k, k):
        f.append(f"afterRejoin {PC} (host, client2) = ({h0[PC]}, {c0[PC]}) (want ({k}, {k}))")
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

def row_rejoiner_cycle(host, c2, ctx):
    """Parallel: end_turn_cycle(host, client2); the cell that fails without the fix: client2's tally turn ==
    K_PARALLEL (the host's stale answer)."""
    s0, notes = ctx["afterRejoin"], []
    end_turn_cycle(host, c2, notes)
    h1, c1 = snap(host), snap(c2)
    tally_turn, c0 = (c1["coopEndTurnTally"] or {}).get("turn"), s0["client2"]
    f, tail = verdict("rejoiner_cycle", host, c2, s0, h1, c1, K_PARALLEL, notes,
                      "the rejoiner's press was dropped as stale", tally_turn == K_PARALLEL,
                      {"client2TallyTurn": tally_turn})
    if not c1[TS] > c0[TS]:
        f.append(f"client2 {TS} {c0[TS]} -> {c1[TS]} (want it to grow)")
    return f + tail

def row_rejoiner_pass(host, c2, ctx):
    """Traditional: client2's pass, full cycle, baton 0; the cells that fail without the fix: host baton still 1,
    client2 pending == K_TRADITIONAL."""
    s0, notes, t = ctx["afterRejoin"], [], time.time()
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
    f, tail = verdict("rejoiner_pass", host, c2, s0, h1, c1, K_TRADITIONAL, notes,
                      "the rejoiner's pass was dropped as stale",
                      h1["coopActiveSeat"] == 1 and c1["coopPendingTallyTurn"] == K_TRADITIONAL,
                      {"press": press, "waitedS": waited})
    if [h1["coopActiveSeat"], c1["coopActiveSeat"]] != [0, 0]:
        f.append(f"coopActiveSeat host {h1['coopActiveSeat']} client2 {c1['coopActiveSeat']} (want 0 on both)")
    if c1["coopPendingTallyTurn"] != -1:
        f.append(f"client2 coopPendingTallyTurn {c1['coopPendingTallyTurn']} (want -1)")
    return f + tail

TALLY_KEYS = ("turn", "side", "count", "needed", "ready", "activeSeat")
STATE_KEYS = (TS, "coopEndTurnText", "coopEndTurnArmed", "coopActiveSeat", "coopPendingTallyTurn")

def row_rejoiner_tally(host, c2, ctx):
    """Traditional, display only, on the traditional boot's afterRejoin snapshot before rejoiner_pass (no new
    step). Without the fix no tally rode the rejoin (client2 talliesSeen 0); with it client2's tally equals the
    host's."""
    s0, p, drops = ctx["afterRejoin"], ctx["pause"], dropped(host)
    h0, c0 = s0["host"], s0["client2"]
    ht, ct = ([(x["coopEndTurnTally"] or {}).get(k) for k in TALLY_KEYS] for x in (h0, c0))
    evidence("rejoiner_tally", {"hostTally": ht, "client2Tally": ct, "hostDropped": drops, "pauseTalliesSeen": p[TS],
                        "host": {k: h0[k] for k in STATE_KEYS}, "client2": {k: c0[k] for k in STATE_KEYS}})
    f = [f"no tally rode the rejoin (client2 {TS} 0; host drop lines {drops})"] if c0[TS] == 0 else []
    if c0[TS] not in (0, 1):
        f.append(f"client2 {TS} {c0[TS]} (want 1)")
    if drops != [0]:
        f.append(f"host 'rejoin dropped' counts {drops} (want exactly [0])")
    if ht != [K_TRADITIONAL, "player", 0, 1, [], 1]:
        f.append(f"host tally {TALLY_KEYS} {ht} (want {[K_TRADITIONAL, 'player', 0, 1, [], 1]})")
    if ct != ht:
        f.append(f"client2 tally {TALLY_KEYS} {ct} != host's {ht}")
    if [c0["coopEndTurnText"], h0["coopEndTurnText"], c0["coopEndTurnArmed"]] != ["", "", False]:
        f.append(f"(client2 text, host text, client2 armed) "
                 f"{[c0['coopEndTurnText'], h0['coopEndTurnText'], c0['coopEndTurnArmed']]} (want ['', '', False])")
    if [c0["coopActiveSeat"], c0["coopPendingTallyTurn"]] != [1, -1]:
        f.append(f"client2 (coopActiveSeat, coopPendingTallyTurn) "
                 f"{[c0['coopActiveSeat'], c0['coopPendingTallyTurn']]} (want [1, -1])")
    if h0[TS] != p[TS] + 1:
        f.append(f"host {TS} {h0[TS]} (want pause {p[TS]} + 1)")
    return f

BOOTS = (("parallel", PORT_PARALLEL, stage_parallel, (("rejoiner_cycle", row_rejoiner_cycle),)),
         ("traditional", PORT_TRADITIONAL, stage_traditional,
          (("rejoiner_tally", row_rejoiner_tally), ("rejoiner_pass", row_rejoiner_pass))))
# rejoiner_tally reads afterRejoin before rejoiner_pass moves it

def run_boot(kind, port, stage_fn, rows, results, walls):
    t0, ctx = time.time(), {}
    host = GameClient("host", None, make_user_dir(f"rejoin_end_turn_{kind.lower()}_host"))
    client = GameClient("client", None, make_user_dir(f"rejoin_end_turn_{kind.lower()}_client"))
    try:
        try:
            stage_fn(host, client, ctx)
            c2 = stage_rejoin(host, client, port, kind, ctx)
        except Exception as e:     # a FixtureMiss printed its CAPTURE line; anything else is unexpected, still a FAIL
            for rid, _ in rows:
                print(f"FAIL {rid}: {'rejoin' if ctx.get('booted') else 'boot'} (setup failure) "
                      f"{e if isinstance(e, FixtureMiss) else short(e, 600)}", flush=True)
            return
        for rid, row_fn in rows:
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
                print(f"[rejoin_end_turn] shutdown {gc.name}: {short(e)}", flush=True)
        walls[kind] = round(time.time() - t0, 1)

def main():
    t0, results, walls = time.time(), {}, {}
    for kind, port, stage_fn, rows in BOOTS:
        run_boot(kind, port, stage_fn, rows, results, walls)
    rids = [rid for b in BOOTS for rid, _ in b[3]]
    passed, failed = [r for r in rids if results.get(r)], [r for r in rids if not results.get(r)]
    print(f"\ntest_rejoin_end_turn: {len(passed)}/{len(rids)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
