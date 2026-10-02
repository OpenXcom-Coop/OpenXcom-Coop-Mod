"""W2-H14b - a rejoin drops the returning player's END TURN press; both screens show the true tally (spec
w2h14b_rejoin_clears_end_turn.md (f); owner D221 (c), ruling H14b-1; F4076). TWO parallel boots on test_w2_death_side's
default map, each shut down before the next, staged with test_w2_rejoin_end_turn's (rej) boot and SPEC 16 leave +
rejoin: B (PORT_B) plays one END TURN cycle, then the CLIENT presses END TURN and leaves; H (PORT_H) plays no cycle,
the HOST presses END TURN and the client leaves. A fresh process (client2) rejoins, the host presses RESUME.
H14b-1 (B): the host's lone press does not end the side on the returning player's pre-leave press, and both screens
show the true tally. H14b-2 (H): client2 shows the host's "END TURN 1/2"; client2's press completes the cycle.
A boot/rejoin step past its bound is a FIXTURE-STOP (one CAPTURE line; the row FAILs "boot"/"rejoin"). Each row prints
ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <msg>"; both rows run. WV-D95/D99/D100: ONE foreground
run, no skip path; exit 0 only when both rows pass, 2 otherwise."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, assert_hash_clean
import test_w2_rejoin_end_turn as rej
from test_w2_death_side import FACTION_PLAYER, CYCLE_SIDE_TRANSITIONS
from test_w2_delta_core import end_turn_cycle, settle_on_battlescape, short, desync_record
from test_rw_turn_baton import drive_full_cycle

PORT_B, PORT_H = "48518", "48519"   # this file's lobby ports (unused by every other test file, F4499)
# TASK 0 (ledger `## W2-H14b TASK 0 DONE`, docs rewrite/w2h14b-task0/CONSTANTS.md; 2/2 boots each, identical):
#   "- K_H = 0 (boot H, lobby 48519: no cycle; both counters 0; client2 seeded 0). 2/2."
#   "- HOLD_S = 6 (= max(6, ceil(3 x 0.101)))."
K_H = 0                             # boot H: both counters at the host's press (no pre-leave cycle); K_P is rej's
HOLD_S = 6                          # a lone host press must NOT end the side within this (red: 0.101 s)
TEXT1, PRESS = "END TURN 1/2", {"cmd": "battle_action", "action": "end_turn_button"}
TK = ("turn", "side", "count", "needed", "ready")
PC, TS = rej.PC, rej.TS


def tally(s, keys=TK):
    t = s["coopEndTurnTally"] or {}
    return [t.get(k) for k in keys]


def stage_b(host, client, ctx, presser, cycle):
    """Boot B (cycle=True, the client presses) or H (cycle=False, the host presses): rej.boot; B: one END TURN cycle
    (notes empty, turn +1 and side player, counters K_P on both, no desync); H: counters K_H on both, no desync; the
    presser's END TURN painted (<= SEAT_S); rej.stage_rejoin (leave, rejoin steps 1-9, S0); the D91 pause
    precondition (red AND green). Returns client2."""
    kind, port, k = ("B", PORT_B, rej.K_P) if cycle else ("H", PORT_H, K_H)
    m = (host, client)
    rej.step(f"boot {kind}", lambda: rej.boot(host, client, port, False), m)
    pre, notes = {"host": rej.snap(host), "client": rej.snap(client)}, []
    if cycle:
        end_turn_cycle(host, client, notes)
    post = {"host": rej.snap(host), "client": rej.snap(client)}
    rej.evidence(f"boot {kind} {'cycle' if cycle else 'entry'}", {"pre": pre, "post": post, "notes": notes})
    bad = [f"notes {notes}"] if notes else []
    for who, gc in (("host", host), ("client", client)):
        a, b = pre[who], post[who]
        if a["turn"] is None or b["turn"] != a["turn"] + int(cycle) or b["side"] != FACTION_PLAYER:
            bad.append(f"{who} turn/side {a['turn']}/{a['side']} -> {b['turn']}/{b['side']} "
                       f"(want +{int(cycle)}, player)")
        if b[PC] != k:
            bad.append(f"{who} {PC} {b[PC]} (want {k})")
        if b["desyncSeen"]:
            bad.append(f"{who} desyncSeen true: {desync_record(gc, True)}")
    rej.check(f"boot {kind} preconditions", bad, m)
    want = (f"host {TEXT1}, client armed" if presser == "client"
            else f"both {TEXT1}, host armed, client not armed")

    def painted():
        hb, cb = battle_state(host), battle_state(client)
        if presser == "client":
            return hb.get("coopEndTurnText") == TEXT1 and cb.get("coopEndTurnArmed") is True
        return (hb.get("coopEndTurnText") == cb.get("coopEndTurnText") == TEXT1
                and hb.get("coopEndTurnArmed") is True and cb.get("coopEndTurnArmed") is False)

    def press():
        r = (client if presser == "client" else host).cmd(dict(PRESS))
        assert r.get("ok"), f"{presser} end_turn_button refused: {r}"
        host.wait_for(want, lambda: painted() or None, timeout=rej.SEAT_S, interval=0.25)
    rej.step(f"{presser} END TURN -> {want}", press, m)
    rej.evidence(f"boot {kind} after the {presser} press", {"host": rej.snap(host), "client": rej.snap(client)})
    ctx["booted"] = True
    c2 = rej.stage_rejoin(host, client, port, kind, ctx)
    p = ctx["pause"]
    if cycle:
        what, got, exp = "(text, count, ready)", [p["coopEndTurnText"]] + tally(p, ("count", "ready")), [TEXT1, 1, [1]]
    else:
        what, got, exp = ("(text, armed, ready)", [p["coopEndTurnText"], p["coopEndTurnArmed"]] + tally(p, ("ready",)),
                          [TEXT1, True, [0]])
    rej.check(f"pause {kind}: the host keeps the {presser}'s press (D91)",
              [f"host {what} {got} (want {exp})"] if got != exp else [], (host, client, c2))
    return c2


def hold(host, c2, turn0):
    """Poll both machines every 0.25 s for HOLD_S: the first sample where either side left player or its turn moved
    (the side committed), else None."""
    t = time.time()
    while time.time() - t < HOLD_S:
        for who, gc in (("host", host), ("client2", c2)):
            b = battle_state(gc)
            if b.get("side") != FACTION_PLAYER or b.get("turn") != turn0:
                return {"who": who, "afterS": round(time.time() - t, 2), "turn": b.get("turn"), "side": b.get("side")}
        time.sleep(0.25)
    return None


def finish(host, c2, turn0, press_c2, notes):
    """client2's END TURN (when press_c2), then the full cycle (<= CYCLE_S), settle, idle; a miss is a note. Returns
    the after snaps and the full hash compare's failure (empty when clean)."""
    try:
        if press_c2:
            r = c2.cmd(dict(PRESS))
            assert r.get("ok"), f"client2 end_turn_button refused: {r}"
        drive_full_cycle(host, c2, turn0, timeout=rej.CYCLE_S)
        settle_on_battlescape(host)
        settle_on_battlescape(c2)
        session.wait_host_idle(host, c2, timeout=rej.IDLE_S)
    except Exception as e:
        notes.append(f"cycle: {short(e)}")
    hashf = []
    try:
        assert_hash_clean(host, c2, full=True, what="after the cycle")
    except AssertionError as e:
        hashf = [f"hash after the cycle: {short(e, 500)}"]
    return {"host": rej.snap(host), "client2": rej.snap(c2)}, hashf


def s0_cells(ctx, drops, n):
    """The S0 GREEN cells both rows share: one host drop line of n, client2's tally == the host's, client2 not armed,
    client2 talliesSeen 1, host talliesSeen == pause + 1."""
    h0, c0, p = ctx["S0"]["host"], ctx["S0"]["client2"], ctx["pause"]
    f = [f"host 'W2-H14b: rejoin dropped' counts {drops} (want exactly [{n}])"] if drops != [n] else []
    if tally(c0) != tally(h0):
        f.append(f"S0 client2 tally {TK} {tally(c0)} != host's {tally(h0)}")
    if c0["coopEndTurnArmed"] is not False:
        f.append(f"S0 client2 coopEndTurnArmed {c0['coopEndTurnArmed']} (want false)")
    if c0[TS] != 1:
        f.append(f"S0 client2 {TS} {c0[TS]} (want 1)")
    if h0[TS] != p[TS] + 1:
        f.append(f"S0 host {TS} {h0[TS]} (want pause {p[TS]} + 1)")
    return f


def after_cells(ctx, after, k, notes, hashf, machines):
    """The after-cycle GREEN cells: turn +1 and side player on both, counters k + 3 on both, hash clean full, no
    desync."""
    f = [f"notes {notes}"] if notes else []
    for who, gc in machines:
        a, b = ctx["S0"][who], after[who]
        if a["turn"] is None or b["turn"] != a["turn"] + 1 or b["side"] != FACTION_PLAYER:
            f.append(f"{who} turn/side {a['turn']}/{a['side']} -> {b['turn']}/{b['side']} (want +1, player)")
        if b[PC] != k + CYCLE_SIDE_TRANSITIONS:
            f.append(f"{who} {PC} {b[PC]} (want {k} + {CYCLE_SIDE_TRANSITIONS})")
        if b["desyncSeen"]:
            f.append(f"desyncSeen true on {who}: {desync_record(gc, True)}")
    return f + hashf


def h14b_1(host, c2, ctx):
    """Parallel, the returning player pressed before leaving (boot B). RED cell: the host's lone press ends the side
    within HOLD_S (the pre-leave press still counted). GREEN: the press was dropped, both screens show the true tally,
    the host's press paints END TURN 1/2 on both, client2's own press completes the cycle."""
    s0, notes, drops = ctx["S0"], [], rej.dropped(host)
    h0, c0 = s0["host"], s0["client2"]
    r = host.cmd(dict(PRESS))
    committed = hold(host, c2, h0["turn"])
    if r.get("ok") and not committed:
        try:
            host.wait_for(f"both {TEXT1}, host armed, client2 not", lambda: (
                [battle_state(gc).get(x) for gc in (host, c2) for x in ("coopEndTurnText", "coopEndTurnArmed")]
                == [TEXT1, True, TEXT1, False]) or None, timeout=rej.SEAT_S, interval=0.25)
        except TimeoutError:
            pass                                  # the pressed snaps below carry the cell
    pressed = {"host": rej.snap(host), "client2": rej.snap(c2)}
    after, hashf = finish(host, c2, h0["turn"], not committed, notes)
    rej.evidence("H14b-1", {"S0": s0, "pause": ctx["pause"], "hostDropped": drops, "hostPress": r,
                            "committed": committed, "pressed": pressed, "after": after, "notes": notes, "hash": hashf})
    f = [f"the host still counted the returning player's pre-leave press (its lone END TURN ended the side within "
         f"HOLD_S {HOLD_S} s with no client2 press: {committed})"] if committed else []
    if not r.get("ok"):
        f.append(f"host end_turn_button refused: {r}")
    f += s0_cells(ctx, drops, 1)
    got = tally(h0, ("turn", "count", "needed", "ready"))
    if got != [rej.K_P, 0, 2, []]:
        f.append(f"S0 host tally (turn, count, needed, ready) {got} (want {[rej.K_P, 0, 2, []]})")
    if [h0["coopEndTurnText"], h0["coopEndTurnArmed"]] != ["", False]:
        f.append(f"S0 host (text, armed) {[h0['coopEndTurnText'], h0['coopEndTurnArmed']]} (want ['', False])")
    if c0["coopEndTurnText"] != h0["coopEndTurnText"]:
        f.append(f"S0 client2 text {c0['coopEndTurnText']!r} != host text {h0['coopEndTurnText']!r}")
    ph, pc = pressed["host"], pressed["client2"]
    got = [ph["coopEndTurnText"], ph["coopEndTurnArmed"], pc["coopEndTurnText"], pc["coopEndTurnArmed"]]
    if got != [TEXT1, True, TEXT1, False]:
        f.append(f"after the host press (host text, armed, client2 text, armed) {got} "
                 f"(want {[TEXT1, True, TEXT1, False]})")
    return f + after_cells(ctx, after, rej.K_P, notes, hashf, (("host", host), ("client2", c2)))


def h14b_2(host, c2, ctx):
    """Parallel, the host pressed before the leave (boot H). RED cell: client2 does not show the host's END TURN 1/2
    at S0 (the cycle then completes: red at S0 only). GREEN: both show the host's tally; client2's press completes the
    cycle."""
    s0, notes, drops = ctx["S0"], [], rej.dropped(host)
    h0, c0 = s0["host"], s0["client2"]
    after, hashf = finish(host, c2, h0["turn"], True, notes)
    rej.evidence("H14b-2", {"S0": s0, "pause": ctx["pause"], "hostDropped": drops, "after": after, "notes": notes,
                            "hash": hashf})
    f = [f"the rejoiner does not show the host's END TURN tally (S0 client2 text {c0['coopEndTurnText']!r} != host "
         f"text {h0['coopEndTurnText']!r})"] if c0["coopEndTurnText"] != h0["coopEndTurnText"] else []
    f += s0_cells(ctx, drops, 0)
    got = [h0["coopEndTurnText"], h0["coopEndTurnArmed"]] + tally(h0, ("count", "needed", "ready"))
    if got != [TEXT1, True, 1, 2, [0]]:
        f.append(f"S0 host (text, armed, count, needed, ready) {got} (want {[TEXT1, True, 1, 2, [0]]})")
    return f + after_cells(ctx, after, K_H, notes, hashf, (("host", host), ("client2", c2)))


BOOTS = (("B", "H14b-1", lambda h, c, ctx: stage_b(h, c, ctx, "client", True), h14b_1),
         ("H", "H14b-2", lambda h, c, ctx: stage_b(h, c, ctx, "host", False), h14b_2))


def run_boot(kind, rid, stage_fn, row_fn, results, walls):
    t0, ctx = time.time(), {}
    host = GameClient("host", None, make_user_dir(f"w2h14_end_turn_{kind.lower()}_host"))
    client = GameClient("client", None, make_user_dir(f"w2h14_end_turn_{kind.lower()}_client"))
    try:
        try:
            c2 = stage_fn(host, client, ctx)
        except Exception as e:     # a FixtureMiss printed its CAPTURE line; anything else is unexpected, still a FAIL
            print(f"FAIL {rid}: {'rejoin' if ctx.get('booted') else 'boot'} (FIXTURE-STOP) "
                  f"{e if isinstance(e, rej.FixtureMiss) else short(e, 600)}", flush=True)
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
                print(f"[w2h14b] shutdown {gc.name}: {short(e)}", flush=True)
        walls[kind] = round(time.time() - t0, 1)


def main():
    t0, results, walls = time.time(), {}, {}
    for kind, rid, stage_fn, row_fn in BOOTS:
        run_boot(kind, rid, stage_fn, row_fn, results, walls)
    rids = [b[1] for b in BOOTS]
    passed, failed = [r for r in rids if results.get(r)], [r for r in rids if not results.get(r)]
    print(f"\ntest_w2_rejoin_end_turn_clear: {len(passed)}/{len(rids)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
