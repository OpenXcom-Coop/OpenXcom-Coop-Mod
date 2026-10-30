"""test_mc_side_ends.py: a side a human plays ends by itself when none of its seats has a unit left to command, as in
vanilla, where a side with no unit to move ends at once. The battle-end tally is vanilla's: the aliens' hold is released
at their side's start, before the tally, so the battle goes on.

The gm3 boot (gm3 parallel, key 48786; the host plays the aliens, seat 0): G3F.bring_up, gm3_census-mode and
gm3_census-seats must pass, every unit's reactions 0, the open-ground staging (MCT.stage_open_ground).
  alien_side_held  the partner's X-COM S holds the host's only alien A (the host's psi_attack test command on S,
      SEED_TAKE_A):
      alien_side_held-held                (precondition) A faction 0, mcId S, coop 0 on both; both tops
                                          BattlescapeState
      alien_side_held-partner_ends        the partner's END TURN alone: the host's side-phase counter +1 within SIDE_S
      alien_side_held-side_skipped        with no further press both machines on side 0 turn 2 within SIDE_S, and
                                          exactly one '[coop-endturn] no seat has a live unit on the active side' host
                                          log line (the host's side had no live seat)
      alien_side_held-released            A faction 1, coop 0 on both at side 0 turn 2 (released at its controller
                                          side's start)
      alien_side_held-alien_side_returns  the partner's press: side 1 turn 2; host tally {count 0, needed 1} within
                                          PAINT_S; the host's press alone: side 0 turn 3
      alien_side_held-common              every bucket EQUAL right before the partner's alien_side_held-partner_ends
                                          press, desyncSeen false, no new crash file
The classic boot (classic co-op parallel, key 48787): MCC.boot_seated (X 1000000 pinned AI-neutral; seat 0 [10..14],
seat 1 [8, 9]), reactions 0, MCC.stage_tiles.
  xcom_side_wiped  X holds the partner's 8 and 9 (as in test_mc_seat_coop's ai_mind_control row), the host's five
      soldiers die mid-side:
      xcom_side_wiped-held              (precondition) 8 and 9 faction 1, mcId X, coop 1 on both
      xcom_side_wiped-soldiers_dead     (precondition) host kill_unit_real {coop_side 0}: killed [10..14], DEAD on both;
                                        the wait ends at the observed deaths, capped at WATCH_CAP_S (boxes dismissed on
                                        their own machine; no turn screen closed, no settle)
      xcom_side_wiped-side_ends_itself  with no press the host's NextTurnState is up within SIDE_S of the kill, and
                                        exactly one self-end line
      xcom_side_wiped-battle_goes_on    the alien side's turn screen: both machines on side 1 turn 1, 8 / 9 back at
                                        faction 0 (coop 1) on both, no battleEnd (emitted 0, applied 0 on both); the
                                        host's close runs vanilla's tally and the battle goes on: the host's side 0 turn
                                        2 turn screen with no DebriefingState, the partner on side 0 turn 2, both
                                        records still 0 / 0 (vanilla: SavedBattleGame.cpp:1742 releases the hold before
                                        the tally, BattlescapeGame.cpp:749)
      xcom_side_wiped-common            every bucket EQUAL right before the kill, desyncSeen false, no new crash file
Every InfoboxState is dismissed on its own machine before any END TURN press (only the top state thinks).

One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails that boot's row "boot"; a staging step fails it "staging"; a cell
whose precondition failed fails "not reached (<cell> failed)"; each row's -common cell is evaluated in every case.
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_mc_side_ends.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import event_state  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
from test_pvp_gm3 import Miss, units, es, top, stack, log_count, fail_all, shut  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_client_shoot import set_tu_both  # noqa: E402
import test_mc_seat_tally as MCT  # noqa: E402
from test_mc_seat_tally import (mcv, poll_box, tally_view, unit_rows, turn_side, A_ID, S_ID,  # noqa: E402
                                   STEP_S, SIDE_S, HOLD_S, PAINT_S, FACTION_PLAYER, FACTION_HOSTILE)
import test_mc_seat_coop as MCC  # noqa: E402
from test_mc_seat_coop import X_ID, S0_IDS, S1_IDS, X_TU, DEAD  # noqa: E402

KEY_GM3, KEY_CLASSIC = "48786", "48787"
SEED_TAKE_A = 1                   # the host's psi_attack test command {8, 1000000} converts A with seed 1
NO_LIVE_SEAT_N = "[coop-endturn] no seat has a live unit on the active side"   # the host's one line per self-ended
#                                                                                side
WATCH_CAP_S = 135                 # xcom_side_wiped-soldiers_dead ends at the observed deaths; >= max(120, 2.5 x 7.26 s)
GM3_ROWS = (("alien_side_held", ("alien_side_held-held", "alien_side_held-partner_ends", "alien_side_held-side_skipped",
                                 "alien_side_held-released", "alien_side_held-alien_side_returns",
                                 "alien_side_held-common")),)
CLASSIC_ROWS = (("xcom_side_wiped", ("xcom_side_wiped-held", "xcom_side_wiped-soldiers_dead",
                                     "xcom_side_wiped-side_ends_itself", "xcom_side_wiped-battle_goes_on",
                                     "xcom_side_wiped-common")),)


# ===================== probes and steps =====================


def capture(tag, err, machines):
    """ONE CAPTURE line: each machine's stack, battle_state side / turn, event_state tally / activeSeat / turnMode, the
    last 40 engine log lines."""
    cap = {}
    for gc in machines:
        d = {}
        for k, fn in (("stack", stack), ("turnSide", turn_side),
                      ("event", lambda g: {k2: event_state(g).get(k2) for k2 in (
                          "coopEndTurnTally", "coopActiveSeat", "turnMode", "coopEndTurnPhaseCounter")}),
                      ("logTail", lambda g: G3F.log_lines(g)[-40:])):
            try:
                d[k] = fn(gc)
            except Exception as e:
                d[k] = f"probe failed: {type(e).__name__}: {e}"
        cap[gc.name] = d
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def once(tag, fn, machines):
    """G3F.guarded, except that a step which already printed its CAPTURE line (G3F.bring_up's Miss) is not captured
    twice."""
    try:
        return fn()
    except Miss:
        raise
    except Exception as e:
        capture(tag, f"{type(e).__name__}: {str(e)[:600]}", machines)
        raise Miss(tag)


def views(host, client):
    return {"tally": [tally_view(host), tally_view(client)], "units": [unit_rows(host), unit_rows(client)]}


def boxes(host, client, rec, where):
    """Both machines' boxes polled and dismissed on their own machine (never a turn screen). Always True."""
    poll_box(host, rec, where)
    poll_box(client, rec, where)
    return True


def tally_is(gc, want):
    return {k: (es(gc, "coopEndTurnTally") or {}).get(k) for k in want} == want


def record(gc):
    r = es(gc, "battleEnd") or {}
    return (r.get("emitted"), r.get("applied"))


def debrief(gc):
    return any("DebriefingState" in s for s in stack(gc))


def self_end_lines(host):
    """The self-end line check: a bounded HOLD_S wait for the count to reach 1, then the count (want exactly 1)."""
    BER.wait_until(lambda: log_count(host, NO_LIVE_SEAT_N) >= 1, HOLD_S, 0.25)
    return log_count(host, NO_LIVE_SEAT_N)


def to_side0_turn2(host, client):
    """No press: both machines on side 0 turn >= 2 within SIDE_S (drive_side_change closes every turn screen).
    Returns (ok, seconds or the reason)."""
    t0 = time.time()
    try:
        drive_side_change(host, client, FACTION_PLAYER, want_turn_min=2, timeout=SIDE_S)
    except TimeoutError:
        return False, f"timed out; (turn, side) host/client {[turn_side(host), turn_side(client)]}"
    return True, round(time.time() - t0, 2)


def common_cell(host, client, crash0, hashed, at):
    ok, detail = G3F.common(host, client, crash0, hashed[0] if hashed else None)
    return ok, f"{detail} (hash taken {at if hashed else 'at the row end: its point was not reached'})"


# ===================== the gm3 boot and row alien_side_held =====================


def boot_gm3(host, client, key):
    """G3F.bring_up (its own CAPTURE line on a miss); gm3_census-mode and gm3_census-seats must pass."""
    boot, _crash = G3F.bring_up(host, client, key, "gm3")
    cells, _ev = G3F.census_cells(host, client, boot)
    bad = {n: cells[n][1] for n in ("gm3_census-mode", "gm3_census-seats") if not cells[n][0]}
    assert not bad, f"gm3_census cells {bad}"
    return {"boot": boot, "turnMode": [es(host, "turnMode"), es(client, "turnMode")]}


def row_alien_side_held(host, client, crash0, rec):
    ev, cells, hashed = {}, {}, []
    gate = MCC.gate_runner(cells)
    amp = MCT.give_amp(host, client, S_ID)
    MCT.set_stat_both(host, client, S_ID, "psiSkill", 100)
    MCT.set_stat_both(host, client, A_ID, "psiStrength", 0)
    ev.update(amp=amp, sTu=set_tu_both(host, client, S_ID, 255))
    ev.update(MCT.psi_attack_seeded(host, client, S_ID, A_ID, amp, SEED_TAKE_A, FACTION_PLAYER, rec, "alien_side_held"))
    a = [mcv(host, A_ID), mcv(client, A_ID)]
    tops = MCT.tops_ready((host, client), rec, "before alien_side_held-partner_ends press")
    want_a = (FACTION_PLAYER, S_ID, 0, False, 0)
    gate("alien_side_held-held", lambda: (a == [want_a] * 2 and tops,
                            f"A host/client {a} (want {want_a}); both tops BattlescapeState {tops}"))

    def partner_ends():
        ev["preEnd"] = views(host, client)
        hashed.append(G3F.hash_now(host, client))
        ok, s, p0 = MCC.press_ends(host, client, client, rec, "before alien_side_held-partner_ends press")
        ev["topsAfterEnd"] = [stack(host), stack(client)]
        return ok, (f"the partner's END TURN alone: host side-phase counter {p0} -> {MCC.pc(host)} within {SIDE_S} s: "
                    f"{ok} ({s} s)")

    def side_skipped():
        ok, s = to_side0_turn2(host, client)
        n = self_end_lines(host)
        ev["skip"] = {"tally": [tally_view(host), tally_view(client)], "lines": n}
        return ok and n == 1, (f"no further press: both machines on side 0 turn 2 within {SIDE_S} s: {ok} ({s}); host "
                               f"'{NO_LIVE_SEAT_N}' lines {n} (want exactly 1); host tally {tally_view(host)}")

    def alien_released():
        MCT.settle(host, client, rec, "alien_side_held side 0 turn 2")
        v = [mcv(host, A_ID)[:3:2], mcv(client, A_ID)[:3:2]]
        return v == [(FACTION_HOSTILE, 0)] * 2, f"A (faction, coop) at side 0 turn 2 host/client {v} (want (1, 0))"

    def alien_side_returns():
        want = {"count": 0, "needed": 1}
        ev["preAlien"] = views(host, client)
        ok1, s1 = MCT.press_to(host, client, client, FACTION_HOSTILE, 2, rec, SIDE_S)
        pt, sp = BER.wait_until(lambda: tally_is(host, want), PAINT_S, 0.1) if ok1 else (False, None)
        ev["preHost"] = views(host, client)
        ok2, s2 = MCT.press_to(host, client, host, FACTION_PLAYER, 3, rec, SIDE_S) if pt else (False, "not pressed")
        return ok1 and pt and ok2, (f"the partner's END TURN -> side 1 turn 2: {ok1} ({s1}); host tally {want} within "
                                    f"{PAINT_S} s: {pt} ({sp} s; {tally_view(host)['tally']}); the host's END TURN "
                                    f"alone -> side 0 turn 3: {ok2} ({s2})")

    for name, fn in (("alien_side_held-partner_ends", partner_ends), ("alien_side_held-side_skipped", side_skipped),
                     ("alien_side_held-released", alien_released),
                     ("alien_side_held-alien_side_returns", alien_side_returns)):
        gate(name, fn)
    ev.update(turnSide=[turn_side(host), turn_side(client)], lines=log_count(host, NO_LIVE_SEAT_N),
              boxes=rec.get("boxes"))
    cells["alien_side_held-common"] = common_cell(host, client, crash0, hashed,
                                                  "right before the partner's alien_side_held-partner_ends press")
    return cells, ev


# ===================== the classic boot and row xcom_side_wiped =====================


def row_xcom_side_wiped(host, client, crash0, rec):
    ev, cells, hashed, t_kill = {}, {}, [], []
    gate = MCC.gate_runner(cells)
    amp = MCT.give_amp(host, client, X_ID)
    MCT.set_stat_both(host, client, X_ID, "psiSkill", 100)
    for uid in S1_IDS:
        MCT.set_stat_both(host, client, uid, "psiStrength", 0)
    ev["ampX"] = amp
    for tag, tgt, seed in (("take_8", 8, MCC.SEED_TAKE_8), ("take_9", 9, MCC.SEED_TAKE_9)):
        reply = MCT.set_stat_both(host, client, X_ID, "tu", X_TU, refill=True)["tu"]
        back = [(units(gc).get(X_ID) or {}).get("tu") for gc in (host, client)]
        ev[tag] = {"xTu": {"reply": reply, "readBack": back}}
        ev[tag].update(MCT.psi_attack_seeded(host, client, X_ID, tgt, amp, seed, FACTION_HOSTILE, rec, tag))
    MCT.set_stat_both(host, client, X_ID, "psiSkill", 0)
    MCT.set_stat_both(host, client, X_ID, "tu", 0, refill=True)
    held = {i: [mcv(host, i)[:3], mcv(client, i)[:3]] for i in S1_IDS}
    want = (FACTION_HOSTILE, X_ID, 1)
    gate("xcom_side_wiped-held", lambda: (all(v == [want, want] for v in held.values()),
                           f"8 / 9 (faction, mcId, coop) host/client {held} (want {want})"))

    def soldiers_dead():
        ev["preKill"] = {"tally": [tally_view(host), tally_view(client)],
                         "liveChanged": MCC.live_units_changed_count(host)}
        hashed.append(G3F.hash_now(host, client))
        t_kill.append(time.time())
        k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "coop_side": 0})
        ok, s = BER.wait_until(lambda: boxes(host, client, rec, "xcom_side_wiped kill")
                               and all((units(gc).get(i) or {}).get("status") == DEAD
                                       for gc in (host, client) for i in S0_IDS), WATCH_CAP_S, 0.1)
        ev["kill"] = k
        return (ok and sorted(k.get("killed") or []) == S0_IDS,
                f"kill_unit_real coop_side 0 {k} (want killed {S0_IDS}); DEAD on both (the wait capped at "
                f"{WATCH_CAP_S} s): {ok} ({s} s)")

    def side_ends_itself():
        tops = []

        def up():
            boxes(host, client, rec, "xcom_side_wiped-side_ends_itself")
            t = [top(host), top(client)]
            if not tops or tops[-1][1] != t:
                tops.append((round(time.time() - t_kill[0], 2), t))
            return BER.host_next_turn_up(host)
        ok, _s = BER.wait_until(up, max(0.0, SIDE_S - (time.time() - t_kill[0])), 0.1)
        at = round(time.time() - t_kill[0], 2)
        n = self_end_lines(host)
        ev["endWait"] = {"tops": tops, "liveChanged": MCC.live_units_changed_count(host),
                         "tally": [tally_view(host), tally_view(client)]}
        return ok and n == 1, (f"no press: host NextTurnState up within {SIDE_S} s of the kill: {ok} ({at} s after the "
                               f"kill; host top {top(host)}, (turn, side) {turn_side(host)}); host "
                               f"'{NO_LIVE_SEAT_N}' lines {n} (want exactly 1)")

    def battle_goes_on():
        ok1, s1 = BER.wait_until(lambda: turn_side(host) == (1, 1) and turn_side(client) == (1, 1), STEP_S, 0.1)
        fc = {i: [mcv(host, i)[:3:2], mcv(client, i)[:3:2]] for i in S1_IDS}
        r0 = [record(host), record(client)]
        d = host.cmd({"cmd": "dismiss_popup"})
        ok2, s2 = BER.wait_until(lambda: debrief(host) or (turn_side(host) == (2, 0) and BER.host_next_turn_up(host)),
                                 STEP_S, 0.1)
        ok3, s3 = BER.wait_until(lambda: turn_side(client) == (2, 0), STEP_S, 0.1)
        deb, r1 = debrief(host), [record(host), record(client)]
        ev["ends"] = {"fc": fc, "records": [r0, r1], "stacks": [stack(host), stack(client)],
                      "turnSide": [turn_side(host), turn_side(client)]}
        good = (ok1 and all(v == [(FACTION_PLAYER, 1)] * 2 for v in fc.values()) and r0 == [(0, 0)] * 2
                and d.get("handled") == "NextTurnState->close" and ok2 and not deb and ok3 and r1 == [(0, 0)] * 2)
        return good, (f"the alien side's turn screen, both machines on side 1 turn 1: {ok1} ({s1} s); 8 / 9 (faction, "
                      f"coop) host/client {fc} (want (0, 1): released at the alien side's start); battleEnd (emitted, "
                      f"applied) host/client {r0} (want (0, 0)); host dismiss_popup {d.get('handled')!r} (want "
                      f"'NextTurnState->close'); then the host's side 0 turn 2 turn screen and no DebriefingState: "
                      f"{ok2 and not deb} ({s2} s), the partner on side 0 turn 2: {ok3} ({s3} s); battleEnd {r1} (want "
                      f"(0, 0): the battle goes on)")

    for name, fn in (("xcom_side_wiped-soldiers_dead", soldiers_dead),
                     ("xcom_side_wiped-side_ends_itself", side_ends_itself),
                     ("xcom_side_wiped-battle_goes_on", battle_goes_on)):
        gate(name, fn)
    ev.update(turnSide=[turn_side(host), turn_side(client)], lines=log_count(host, NO_LIVE_SEAT_N),
              boxes=rec.get("boxes"))
    cells["xcom_side_wiped-common"] = common_cell(host, client, crash0, hashed, "right before the kill")
    return cells, ev


# ===================== main =====================


def run_boot(tag, key, boot_fn, staging_fn, rows, row_fns):
    """MCT.run_boot with the dir prefix mc_side_ends_ and ONE CAPTURE line per missed boot step."""
    host = GameClient("host", None, make_user_dir(f"mc_side_ends_{tag}_host"))
    client = GameClient("client", None, make_user_dir(f"mc_side_ends_{tag}_client"))
    m, rec, fails = (host, client), {"boxes": []}, 0
    try:
        try:
            once(f"boot {tag.upper()}", lambda: (boot_fn(host, client, key), G3F.reactions_zero(host, client)), m)
        except Miss:
            return fail_all(rows, "boot")
        crash0 = session._crash_log_snapshot()
        try:
            once(f"staging {tag.upper()}", lambda: staging_fn(host, client, rec), m)
        except Miss:
            return fail_all(rows, "staging")
        for (row, order), fn in zip(rows, row_fns):
            fails += MCT.run_row(row, order, fn, host, client, crash0, rec)
        return fails
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot("gm3", KEY_GM3, boot_gm3, lambda h, c, rec: MCT.stage_open_ground(h, c), GM3_ROWS,
                     (row_alien_side_held,))
    fails += run_boot("classic", KEY_CLASSIC, MCC.boot_seated, MCC.stage_tiles, CLASSIC_ROWS, (row_xcom_side_wiped,))
    print(f"test_mc_side_ends: {'PASS' if not fails else 'FAIL'} ({fails} failing cell(s)) wall "
          f"{time.time() - t0:.1f} s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
