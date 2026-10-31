"""test_mc_seat_coop.py (classic co-op): END TURN counts a mind-controlled unit for the seat that commands it now, so
the side ends on "a live COMMANDABLE unit" of each seat.

The boot (key 48739): BER.boot_classic (the one alien X 1000000 pinned AI-neutral); seat 0 live [10..14], seat 1 [8, 9]
on both, turnMode parallel; every unit's reactions 0; X, 8, 9 placed on their TILES; every bucket EQUAL.
  ai_mind_control  (control) a soldier an AI alien mind-controls counts for no seat while held, and for its owner once
      released: X (psi amp, psiSkill 100, TU 54 by set_stat) takes 8 (SEED_TAKE_8) and 9 (SEED_TAKE_9) by the host's
      psi_attack test command; X re-pinned (psiSkill 0, TU 0).
      ai_mind_control-held             (precondition) 8 and 9 faction 1, mcId X, coop 1 on both
      ai_mind_control-host_ends_alone  the host's press alone: the host's phase counter +1 within SIDE_S; the cycle to
                                       side 0 turn 2
      ai_mind_control-released_counts  8 and 9 faction 0, coop 1 on both; the host's press: host tally {count 1,
                                       needed 2, ready [0]} within PAINT_S and the phase counter held HOLD_S
      ai_mind_control-client_ends      the client's press ends the side within SIDE_S; the cycle to side 0 turn 3
      ai_mind_control-common           every bucket EQUAL after ai_mind_control-client_ends's cycle, desyncSeen false,
                                       no new crash file
  partner_mind_control  a partner whose soldiers are all down but who commands a mind-controlled alien keeps its END
      TURN: 8 (psi amp, psiSkill 100) takes X (SEED_TAKE_X); host kill_unit_real {coop_side 1}.
      partner_mind_control-alien_held        (precondition) X faction 0, mcId 8 on both, read before the kill
      partner_mind_control-soldiers_dead     (precondition) 8 and 9 DEAD on both; the wait ends at the observed
                                             deaths, capped at WATCH_CAP_S; X not out, faction 0 on both
      partner_mind_control-host_press_holds  the host's press: host tally {count 1, needed 2, ready [0]} within
                                             PAINT_S, phase counter held HOLD_S
      partner_mind_control-client_ends       the client's press ends the side within SIDE_S
      partner_mind_control-common            every bucket EQUAL right before the host's press, desyncSeen false, no new
                                             crash file
Every InfoboxState is dismissed on its own machine before any END TURN press (only the top state thinks).

One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails both rows "boot"; a staging step fails them "staging".
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_mc_seat_coop.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
from test_pvp_gm3 import units, es, log_lines  # noqa: E402
from test_client_shoot import set_tu_both, place  # noqa: E402
from test_end_turn_tally import drive_full_cycle  # noqa: E402
from test_mc_seat_tally import (mcv, unit_rows, tally_view, msgs, turn_side, poll_box, tops_ready, settle,  # noqa: E402
                                   set_stat_both, give_amp, psi_attack_seeded, common, run_boot, STEP_S, SIDE_S, HOLD_S,
                                   PAINT_S, PRESS, FACTION_PLAYER, FACTION_HOSTILE)

KEY = "48739"
X_ID = 1000000                    # the one alien, pinned AI-neutral (coop -1)
S0_IDS, S1_IDS = [10, 11, 12, 13, 14], [8, 9]   # the live soldier ids of seat 0 and seat 1 in a classic boot
TILES = {X_ID: ((15, 2, 0), 4), 8: ((14, 5, 0), 0), 9: ((16, 5, 0), 0)}   # X, 8, 9 (open ground, z 0)
X_TU = 54                         # set_stat {X, tu, 54, refill} before each psi attack (the pin made its base 0)
SEED_TAKE_8, SEED_TAKE_9, SEED_TAKE_X = 1, 1, 2   # seed 1 fails the roll that takes X
DEAD = 6
WATCH_CAP_S = 135                 # the cap: partner_mind_control-soldiers_dead ends at the observed deaths
LIVE_UNITS_N = "[coop-endturn] a seat's live units changed at quiescence"
ROWS = (("ai_mind_control", ("ai_mind_control-held", "ai_mind_control-host_ends_alone",
                             "ai_mind_control-released_counts", "ai_mind_control-client_ends",
                             "ai_mind_control-common")),
        ("partner_mind_control", ("partner_mind_control-alien_held", "partner_mind_control-soldiers_dead",
                                  "partner_mind_control-host_press_holds", "partner_mind_control-client_ends",
                                  "partner_mind_control-common")))
WANT_HOLD = {"count": 1, "needed": 2, "ready": [0]}


def live_ids(gc, seat):
    return sorted(u["id"] for u in battle_state(gc).get("units", [])
                  if u.get("coop") == seat and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))


def boot_seated(host, client, key):
    info = BER.boot_classic(host, client, key)
    seats = {gc.name: [live_ids(gc, 0), live_ids(gc, 1)] for gc in (host, client)}
    assert all(v == [S0_IDS, S1_IDS] for v in seats.values()), f"seat ids {seats} (want {[S0_IDS, S1_IDS]})"
    mode = [es(host, "turnMode"), es(client, "turnMode")]
    assert mode == ["parallel", "parallel"], f"turnMode host/client {mode}"
    return info


def stage_tiles(host, client, rec):
    th = {(t["x"], t["y"]): t for t in host.ok({"cmd": "tile_census", "x0": 10, "x1": 20, "y0": 0, "y1": 10,
                                                 "z0": 0, "z1": 0})["tiles"] if t}
    tc = {(t["x"], t["y"]): t for t in client.ok({"cmd": "tile_census", "x0": 10, "x1": 20, "y0": 0, "y1": 10,
                                                   "z0": 0, "z1": 0})["tiles"] if t}
    parts = lambda t: tuple((t or {}).get("parts", {}).get(p, {}).get("mapDataID")
                            for p in ("floor", "westwall", "northwall", "object"))
    occ = {(u.get("x"), u.get("y"), u.get("z")): i for i, u in units(host).items()}
    for uid, (t, d) in TILES.items():
        ph, pc = parts(th.get(t[:2])), parts(tc.get(t[:2]))
        assert ph == pc and ph[0] not in (None, -1) and ph[3] == -1 and occ.get(t) in (None, uid), (
            f"unit {uid} tile {t} parts host {ph} client {pc} occupant {occ.get(t)}")
        place(host, client, uid, t, d)
    assert_hash_clean(host, client, full=True, what="classic boot staging")


def pc(gc):
    return event_state(gc).get("coopEndTurnPhaseCounter")


def press_ends(host, client, presser, rec, where):
    """Boxes dismissed, `presser`'s END TURN; (ok, seconds) for the host's phase counter +1 within SIDE_S."""
    tops_ready((host, client), rec, where)
    p0 = pc(host)
    presser.cmd(dict(PRESS))
    ok, s = BER.wait_until(lambda: (pc(host) or 0) >= (p0 or 0) + 1, SIDE_S, 0.1)
    return ok, s, p0


def press_holds(host, client, presser, rec, where):
    """Boxes dismissed, `presser`'s END TURN; the host tally reads WANT_HOLD within PAINT_S and the host's phase counter
    holds for HOLD_S. Returns (ok, detail)."""
    tops_ready((host, client), rec, where)
    p0 = pc(host)
    presser.cmd(dict(PRESS))
    painted, s = BER.wait_until(lambda: {k: (es(host, "coopEndTurnTally") or {}).get(k) for k in WANT_HOLD} == WANT_HOLD,
                                PAINT_S, 0.1)
    moved, t0 = None, time.time()
    while time.time() - t0 < HOLD_S:
        if pc(host) != p0:
            moved = round(time.time() - t0, 2)
            break
        time.sleep(0.25)
    ok = painted and moved is None and pc(host) == p0
    return ok, (f"host tally {tally_view(host)['tally']} (want {WANT_HOLD} within {PAINT_S} s: {painted}, {s} s); "
                f"phase counter {p0} -> {pc(host)} (moved at {moved} s; want held {HOLD_S} s)")


def cycle_to(host, client, rec, turn0):
    try:
        drive_full_cycle(host, client, turn0, timeout=STEP_S)
    except TimeoutError as e:
        return False, str(e)[:160]
    settle(host, client, rec, f"side 0 turn {turn0 + 1}")
    return True, [turn_side(host), turn_side(client)]


def gate_runner(cells):
    state = {"first": None}

    def gate(name, fn):
        if state["first"]:
            cells[name] = (False, f"not reached ({state['first']} failed)")
            return
        try:
            cells[name] = fn()
        except Exception as e:
            cells[name] = (False, f"{type(e).__name__}: {str(e)[:300]}")
        if not cells[name][0]:
            state["first"] = name
    return gate


def row_ai_mind_control(host, client, crash0, rec):
    ev, cells = {}, {}
    gate = gate_runner(cells)
    amp = give_amp(host, client, X_ID)
    set_stat_both(host, client, X_ID, "psiSkill", 100)
    for uid in S1_IDS:
        set_stat_both(host, client, uid, "psiStrength", 0)
    ev["ampX"] = amp
    for tag, tgt, seed in (("take_8", 8, SEED_TAKE_8), ("take_9", 9, SEED_TAKE_9)):
        reply = set_stat_both(host, client, X_ID, "tu", X_TU, refill=True)["tu"]
        ev[tag] = {"xTu": {"reply": reply, "readBack": [(units(gc).get(X_ID) or {}).get("tu") for gc in (host, client)]}}
        ev[tag].update(psi_attack_seeded(host, client, X_ID, tgt, amp, seed, FACTION_HOSTILE, rec, tag))
    set_stat_both(host, client, X_ID, "psiSkill", 0)
    set_stat_both(host, client, X_ID, "tu", 0, refill=True)
    held = {i: [mcv(host, i)[:3], mcv(client, i)[:3]] for i in S1_IDS}
    want = (FACTION_HOSTILE, X_ID, 1)
    tus = [ev[t]["xTu"]["readBack"] for t in ("take_8", "take_9")]
    gate("ai_mind_control-held", lambda: (all(v == [want, want] for v in held.values()) and tus == [[X_TU, X_TU]] * 2,
                                          f"8 / 9 (faction, mcId, coop) host/client {held} (want {want}); X TU read "
                                          f"back before each psi attack host/client {tus} (want {X_TU})"))

    def ends_host_alone():
        ev["preEnd"] = {"tally": [tally_view(host), tally_view(client)], "units": [unit_rows(host), unit_rows(client)],
                        "msgs": [msgs(host), msgs(client)]}
        ok, s, p0 = press_ends(host, client, host, rec, "before ai_mind_control-host_ends_alone press")
        cyc = cycle_to(host, client, rec, 1) if ok else (False, "no side end")
        return ok and cyc[0], (f"host press alone: phase counter {p0} -> {pc(host)} within {SIDE_S} s: {ok} ({s} s); "
                               f"cycle to side 0 turn 2: {cyc}")

    def released_counts():
        v = {i: [mcv(host, i)[:3:2], mcv(client, i)[:3:2]] for i in S1_IDS}
        ev["preBack"] = {"tally": [tally_view(host), tally_view(client)], "units": [unit_rows(host), unit_rows(client)]}
        rel = all(x == [(FACTION_PLAYER, 1)] * 2 for x in v.values())
        ok, detail = (press_holds(host, client, host, rec, "before ai_mind_control-released_counts press") if rel
                      else (False, "no press"))
        return rel and ok, f"8 / 9 (faction, coop) host/client {v} (want (0, 1)); {detail}"

    def ends_by_client():
        ok, s, p0 = press_ends(host, client, client, rec, "before ai_mind_control-client_ends press")
        cyc = cycle_to(host, client, rec, 2) if ok else (False, "no side end")
        return ok and cyc[0], (f"client press: phase counter {p0} -> {pc(host)} within {SIDE_S} s: {ok} ({s} s); "
                               f"cycle to side 0 turn 3: {cyc}")

    for name, fn in (("ai_mind_control-host_ends_alone", ends_host_alone),
                     ("ai_mind_control-released_counts", released_counts),
                     ("ai_mind_control-client_ends", ends_by_client)):
        gate(name, fn)
    ev["turnSide"] = [turn_side(host), turn_side(client)]
    cells["ai_mind_control-common"] = common(host, client, crash0,
                                             f"after ai_mind_control-client_ends's cycle at {ev['turnSide']}")
    ev["boxes"] = rec.get("boxes")
    return cells, ev


def live_units_changed_count(gc):
    return sum(1 for ln in log_lines(gc) if LIVE_UNITS_N in ln)


def row_partner_mind_control(host, client, crash0, rec):
    ev, cells = {}, {}
    gate = gate_runner(cells)
    amp = give_amp(host, client, 8)
    set_stat_both(host, client, 8, "psiSkill", 100)
    set_stat_both(host, client, X_ID, "psiStrength", 0)
    ev["amp8"] = amp
    ev["tu8"] = set_tu_both(host, client, 8, 255)
    ev.update(psi_attack_seeded(host, client, 8, X_ID, amp, SEED_TAKE_X, FACTION_PLAYER, rec, "partner_mind_control"))
    x = [mcv(host, X_ID), mcv(client, X_ID)]
    ev["x"] = x
    gate("partner_mind_control-alien_held", lambda: ([v[:2] for v in x] == [(FACTION_PLAYER, 8)] * 2,
                           f"X (faction, mcId, coop, isOut, status) host/client {x} (want faction 0, mcId 8)"))

    def soldiers_dead():
        ev["liveChangedBefore"] = live_units_changed_count(host)
        ev["tallyBeforeKill"] = [tally_view(host), tally_view(client)]
        k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "coop_side": 1})
        ok, s = BER.wait_until(lambda: (poll_box(host, rec, "partner_mind_control kill") or True)
                               and (poll_box(client, rec, "partner_mind_control kill") or True)
                               and all((units(gc).get(i) or {}).get("status") == DEAD for gc in (host, client)
                                       for i in S1_IDS), WATCH_CAP_S, 0.1)
        settle(host, client, rec, "partner_mind_control kill")
        ev["liveChangedAfter"] = live_units_changed_count(host)
        ev["tallyAfterKill"] = [tally_view(host), tally_view(client)]
        xs = [mcv(host, X_ID), mcv(client, X_ID)]
        good = ok and sorted(k.get("killed") or []) == S1_IDS and all(v[0] == FACTION_PLAYER and not v[3] for v in xs)
        return good, (f"kill_unit_real coop_side 1 {k} (want killed {S1_IDS}); 8 / 9 DEAD on both (the wait capped at "
                      f"{WATCH_CAP_S} s): {ok} ({s} s); X host/client {xs} (want faction 0, not out)")

    def host_press_holds():
        ev["preHold"] = {"tally": [tally_view(host), tally_view(client)], "units": [unit_rows(host), unit_rows(client)],
                         "msgs": [msgs(host), msgs(client)]}
        cells["partner_mind_control-common"] = common(host, client, crash0, "right before the host's press")
        return press_holds(host, client, host, rec, "before partner_mind_control-host_press_holds press")

    def client_press_ends():
        ok, s, p0 = press_ends(host, client, client, rec, "before partner_mind_control-client_ends press")
        return ok, f"client press: phase counter {p0} -> {pc(host)} within {SIDE_S} s: {ok} ({s} s)"

    for name, fn in (("partner_mind_control-soldiers_dead", soldiers_dead),
                     ("partner_mind_control-host_press_holds", host_press_holds),
                     ("partner_mind_control-client_ends", client_press_ends)):
        gate(name, fn)
    if "partner_mind_control-common" not in cells:
        cells["partner_mind_control-common"] = common(host, client, crash0, "after the row's last reached step")
    ev["turnSide"] = [turn_side(host), turn_side(client)]
    ev["boxes"] = rec.get("boxes")
    return cells, ev


def main():
    t0 = time.time()
    fails = run_boot("classic", KEY, boot_seated, stage_tiles, ROWS, (row_ai_mind_control, row_partner_mind_control))
    print(f"test_mc_seat_coop: {'PASS' if not fails else 'FAIL'} ({fails} failing cell(s)) wall "
          f"{time.time() - t0:.1f} s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
