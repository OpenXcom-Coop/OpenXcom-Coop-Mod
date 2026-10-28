"""RV-U8b - the client's END TURN count and pressed button clear when the side ends, as the host's do (R-U8-1,
F10885 / F10963; spec docs rewrite/prompts/rvu8b_client_tally_clear.md (f); TASK 0 docs
rewrite/rvu8b-task0/CONSTANTS.md).

THREE rows, each its own boot (test_end_turn_tally.py's recipe: bring_up_lobby, drive_to_battlescape on
STR_SMALL_SCOUT with seat_count 2 and set_seed 1 - plus set_mode(traditional) first for C3 - then pin_ai_neutral),
each shut down before the next. A press is the real END TURN button (battle_action end_turn_button) on the pressing
machine; C2's commit is test_end_turn_unit_out.kill_seat (the host's kill_unit_real {coop_side 1}, victims out).
  C1 (parallel)    the client pressed; the host's press completes the side (commit tally {2, 2, [0, 1]}).
  C2 (parallel)    the host pressed; the client's last soldier goes out and RV-U8's recount commits ({1, 1, [0]}).
  C3 (traditional) the host passed; the client's press is the last pass ({1, 1, [1], activeSeat 1}).
After the commit both machines sit at phase counter +1 on the alien side, each on its NextTurnState (nothing closes a
NextTurnState before cell (2) has read). tPhase = the moment both phase counters read +1. Cells, in order:
  (1) the host at the alien side, as today: phase counter P0 + 1, side ALIEN_SIDE, text '', button up.
  (2) the client clears: within CLEAR_S of tPhase its text is '' and its button up, both machines still at +1.
  (3) presentation only: both machines' tally still equals the commit tally; talliesSeen == seen0 + DS on each.
  (4) the next X-COM side: drive_full_cycle + wait_host_idle; both phase counters +3, text '', button up, the new
      side's tally.
Premise (every row): seat 0 / seat 1 live player units == S0_IDS / S1_IDS on both machines, the live turn mode on
both (C3: coopActiveSeat 0 on both), entry text '' and button up on both. A premise or pre-cell miss = ONE CAPTURE
line and "FAIL <row>: pre-cell (FIXTURE-STOP)". A failed cell ends its row (later cells "not reached"). Guards per
row: no new crash file, both processes alive at the row end. Each row prints ONE "EVIDENCE <row>:" line, one
PASS/FAIL line per cell and guard, then its verdict; every row runs after a failure.
Rulings: R-U8-1 ("as the host does": text and pressed look), design-D1 (the count is persistent WITHIN a side), IR2-4
(readiness clears at every side change; an AI side is INERT, the host emits no tally there), QB-1..QB-4 (a).
WV-D95 / D99 / D100: ONE foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_end_turn_client_clear.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral
from test_end_turn_tally import bring_up_lobby, drive_full_cycle
from test_turn_mode import set_mode, TRADITIONAL, PARALLEL
from test_end_turn_unit_out import (FixtureMiss, short, snap, pc, until, until_by, press, kill_seat, premise,
                                       tally_is, log_tail, MISSION, TEXT1)

# TASK 0 (docs rewrite/rvu8b-task0/CONSTANTS.md; 6/6 boots at 4232a1527, each pair equal on both machines): both
# phase counters +1 0.15-0.25 s after the commit; both machines parked on NextTurnState, side 1, through PARK_S 6;
# the client still shows C1 "END TURN 2/2" armed True, C2 "END TURN 1/1" armed False, C3 "END TURN 1/1" armed True.
PAINT_S, SIDE_S, CLEAR_S = 15, 15, 3   # the spec's windows, never widened (VICTIMS_S 10 is kill_seat's own bound)
DS = 1                                 # talliesSeen from seen0 to the alien side, both machines (the commit tally)
ALIEN_SIDE = 1                         # battle_state.side of the hostile side
COMMIT = {"C1": dict(count=2, needed=2, ready=[0, 1], side="player"),
          "C2": dict(count=1, needed=1, ready=[0], side="player"),
          "C3": dict(count=1, needed=1, ready=[1], side="player", activeSeat=1)}
NEXT = {"C1": dict(count=0, needed=2, ready=[], side="player"),
        "C2": dict(count=0, needed=1, ready=[], side="player"),
        "C3": dict(count=0, needed=1, ready=[], side="player", activeSeat=0)}


def top(gc):
    return gc.cmd({"cmd": "list_widgets"}).get("state", "").replace("class OpenXcom::", "")


def snaps(host, client):
    return {w: dict(snap(gc), top=top(gc)) for w, gc in (("host", host), ("client", client))}


def both_tally(host, client, **want):
    return tally_is(snap(host), **want) and tally_is(snap(client), **want)


def tallies(host, client):
    return f"host tally {snap(host)['tally']}, client tally {snap(client)['tally']}"


def entry(host, client, ctx):
    ctx["entry"] = snaps(host, client)
    bad = [f"{w} text {s['text']!r} armed {s['armed']}" for w, s in ctx["entry"].items()
           if s["text"] != "" or s["armed"] is not False]
    if bad:
        raise FixtureMiss("entry (want text '', armed False on both): " + "; ".join(bad))


def baseline(host, client, ctx):
    """seen0 / P0 / C0 / turn0 - read only after BOTH machines' tallies show the pre-commit press."""
    ctx["seen0"] = {"host": event_state(host).get("coopEndTurnTalliesSeen"),
                    "client": event_state(client).get("coopEndTurnTalliesSeen")}
    ctx["P0"], ctx["C0"], ctx["turn0"] = pc(host), pc(client), battle_state(host).get("turn")


def to_alien_side(host, client, ctx, t_commit):
    """Both phase counters +1 within SIDE_S of the commit -> tPhase, the cells' reference time."""
    if until_by(lambda: pc(host) == ctx["P0"] + 1 and pc(client) == ctx["C0"] + 1, t_commit + SIDE_S) is None:
        raise FixtureMiss(f"phase counters host {pc(host)} client {pc(client)} (P0 {ctx['P0']}, C0 {ctx['C0']}) "
                          f"{SIDE_S} s after the commit (want both +1); {tallies(host, client)}")
    ctx["tPhase"] = time.time()
    ctx["toPhaseS"] = round(ctx["tPhase"] - t_commit, 2)


# ----- the pre-cells: the press before the commit, the baseline, the commit, both counters +1 -----

def c1_pre(host, client, ctx):
    press(client, ctx, "client")
    if until(lambda: battle_state(host).get("coopEndTurnText") == TEXT1
             and battle_state(client).get("coopEndTurnArmed") is True
             and both_tally(host, client, count=1, needed=2, ready=[1]), PAINT_S) is None:
        raise FixtureMiss(f"after the client's press: host text {battle_state(host).get('coopEndTurnText')!r}, client "
                          f"armed {battle_state(client).get('coopEndTurnArmed')}, {tallies(host, client)} (want host "
                          f"{TEXT1!r}, client armed True, both tallies count 1, needed 2, ready [1])")
    baseline(host, client, ctx)
    t = time.time()
    press(host, ctx, "host (commit)")
    to_alien_side(host, client, ctx, t)


def c2_pre(host, client, ctx):
    press(host, ctx, "host")
    if until(lambda: battle_state(host).get("coopEndTurnText") == TEXT1
             and both_tally(host, client, count=1, needed=2, ready=[0]), PAINT_S) is None:
        raise FixtureMiss(f"after the host's press: host text {battle_state(host).get('coopEndTurnText')!r}, "
                          f"{tallies(host, client)} (want {TEXT1!r}, both tallies count 1, needed 2, ready [0])")
    baseline(host, client, ctx)
    kill_seat(host, ctx, 1)
    to_alien_side(host, client, ctx, ctx["tOut"])


def c3_pre(host, client, ctx):
    p, c = pc(host), pc(client)
    press(host, ctx, "host (pass)")
    if until(lambda: event_state(host).get("coopActiveSeat") == 1 and event_state(client).get("coopActiveSeat") == 1
             and both_tally(host, client, count=0, needed=1, ready=[], activeSeat=1), PAINT_S) is None:
        raise FixtureMiss(f"after the host's pass: coopActiveSeat host {snap(host)['active']} client "
                          f"{snap(client)['active']}, {tallies(host, client)} (want 1 on both, both tallies count 0, "
                          "needed 1, ready [], activeSeat 1)")
    if (pc(host), pc(client)) != (p, c):
        raise FixtureMiss(f"the host's pass moved the phase counters {p} / {c} -> {pc(host)} / {pc(client)} "
                          "(a pass is not a side change)")
    baseline(host, client, ctx)
    t = time.time()
    press(client, ctx, "client (last pass)")
    to_alien_side(host, client, ctx, t)


# ----- the cells (each returns a failure string or None) -----

def host_alien(row):
    def cell(host, client, ctx):
        h = snap(host)
        if h["pc"] != ctx["P0"] + 1 or h["side"] != ALIEN_SIDE or h["text"] != "" or h["armed"] is not False:
            return (f"host pc {h['pc']} side {h['side']} text {h['text']!r} armed {h['armed']} (want pc "
                    f"{ctx['P0'] + 1}, side {ALIEN_SIDE}, text '', armed False)")
        return None
    return cell


def client_clears(row):
    def cell(host, client, ctx):
        def clear():
            bs = battle_state(client)
            return bs.get("coopEndTurnText") == "" and bs.get("coopEndTurnArmed") is False
        s = until_by(clear, ctx["tPhase"] + CLEAR_S)
        hp, cp = pc(host), pc(client)
        if s is None:
            c = snap(client)
            return (f"client text {c['text']!r} armed {c['armed']} {CLEAR_S} s after both phase counters reached +1 "
                    f"(want text '', armed False); phase counters host {hp} client {cp}")
        if hp != ctx["P0"] + 1 or cp != ctx["C0"] + 1:
            return (f"the alien side ended before the read: phase counters host {hp} client {cp} (want "
                    f"{ctx['P0'] + 1} / {ctx['C0'] + 1})")
        return None
    return cell


def presentation_only(row):
    def cell(host, client, ctx):
        bad = []
        for w, gc in (("host", host), ("client", client)):
            s = snap(gc)
            if not tally_is(s, **COMMIT[row]) or s["seen"] != ctx["seen0"][w] + DS:
                bad.append(f"{w} tally {s['tally']} talliesSeen {s['seen']} (want {COMMIT[row]}, talliesSeen "
                           f"{ctx['seen0'][w] + DS})")
        return "; ".join(bad) or None
    return cell


def next_side(row):
    def cell(host, client, ctx):
        try:
            drive_full_cycle(host, client, ctx["turn0"])
            session.wait_host_idle(host, client, timeout=30)
        except Exception as e:
            return f"the full cycle did not complete: {short(e)}"
        bad = []
        for w, gc, p0 in (("host", host, ctx["P0"]), ("client", client, ctx["C0"])):
            s = snap(gc)
            if s["pc"] != p0 + 3 or s["text"] != "" or s["armed"] is not False or not tally_is(s, **NEXT[row]):
                bad.append(f"{w} pc {s['pc']} text {s['text']!r} armed {s['armed']} tally {s['tally']} (want pc "
                           f"{p0 + 3}, text '', armed False, tally {NEXT[row]})")
        return "; ".join(bad) or None
    return cell


CELLS = (("(1) host at the alien side", host_alien), ("(2) client clears", client_clears),
         ("(3) presentation only", presentation_only), ("(4) the next X-COM side", next_side))
ROWS = (("C1", "48124", 49624, 49625, PARALLEL, c1_pre),
        ("C2", "48125", 49626, 49627, PARALLEL, c2_pre),
        ("C3", "48126", 49628, 49629, TRADITIONAL, c3_pre))


def run_row(row, results, walls):
    rid, key, lh, lc, mode, pre = row
    t0, ctx, lines = time.time(), {"row": rid}, []
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", lh, make_user_dir(f"rvu8b_{rid}_host"))
    client = GameClient("client", lc, make_user_dir(f"rvu8b_{rid}_client"))
    failed, verdict = [], None
    try:
        try:
            bring_up_lobby(host, client, key)

            def pre_ok(h):
                if mode == TRADITIONAL:
                    set_mode(h, TRADITIONAL)
                h.ok({"cmd": "set_seed", "seed": 1})
            session.drive_to_battlescape(host, client, {}, mission=MISSION, seat_count=2, pre_ok=pre_ok)
            ctx["pinned"] = pin_ai_neutral(host, client, tag=f"rvu8b-{rid}")
            premise(host, client, mode, ctx)
            entry(host, client, ctx)
            pre(host, client, ctx)
        except Exception as e:
            cap = {}
            for w, gc in (("host", host), ("client", client)):
                try:
                    cap[w] = {"battle_state": {k: battle_state(gc).get(k) for k in
                                               ("ok", "inBattle", "turn", "side", "phase", "coopEndTurnText",
                                                "coopEndTurnArmed")},
                              "event_state": snap(gc), "top": top(gc), "log": log_tail(gc)}
                except Exception as e2:
                    cap[w] = {"error": short(e2), "log": log_tail(gc)}
            print(f"CAPTURE {rid}: {type(e).__name__}: {short(e, 600)} | {json.dumps(cap, default=str)}", flush=True)
            verdict = "pre-cell (FIXTURE-STOP)"
            return
        reached = True
        for name, mk in CELLS:
            if not reached:
                lines.append(f"{rid} {name}: not reached")
                continue
            try:
                f = mk(rid)(host, client, ctx)
            except Exception as e:
                f = f"{type(e).__name__}: {short(e, 500)}"
            ctx.setdefault("cells", {})[name] = dict(snaps(host, client), atS=round(time.time() - ctx["tPhase"], 2))
            if f:
                lines.append(f"FAIL {rid} {name}: {f}")
                failed.append("cell " + name.split(")")[0] + ")")
                reached = False
            else:
                lines.append(f"PASS {rid} {name}")
    finally:
        alive = {gc.name: (gc.proc is not None and gc.proc.poll() is None) for gc in (host, client)}
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[rvu8b] shutdown {gc.name}: {short(e)}", flush=True)
        new_crash = sorted(session._crash_log_snapshot() - crash0)
        ctx["crash"], ctx["alive"] = new_crash, alive
        if verdict is None:
            lines.append(f"PASS {rid} guard crash" if not new_crash else f"FAIL {rid} guard crash: new {new_crash}")
            lines.append(f"PASS {rid} guard alive" if all(alive.values())
                         else f"FAIL {rid} guard alive: {alive}")
            if new_crash:
                failed.append("guard crash")
            if not all(alive.values()):
                failed.append("guard alive")
        ev = {k: v for k, v in ctx.items() if k not in ("tOut", "tPhase")}
        print(f"EVIDENCE {rid}: {json.dumps(ev, default=str)}", flush=True)
        if verdict is None:
            for ln in lines:
                print(ln, flush=True)
            verdict = ", ".join(failed)
        results[rid] = verdict == ""
        print(f"PASS {rid}" if verdict == "" else f"FAIL {rid}: {verdict}", flush=True)
        walls[rid] = round(time.time() - t0, 1)


def main():
    t0, results, walls = time.time(), {}, {}
    for row in ROWS:
        run_row(row, results, walls)
    rids = [r[0] for r in ROWS]
    passed, failed = [r for r in rids if results.get(r)], [r for r in rids if not results.get(r)]
    print(f"\ntest_end_turn_client_clear: {len(passed)}/{len(rids)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
