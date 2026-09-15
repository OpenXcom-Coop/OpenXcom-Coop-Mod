"""SPEC 12 (W1-P13d) - test_rw_nonplayer_think_gate.py: REV E.58 E58.1's gm2
leg - WV-D44 (BLOCKER) / REV E.48 SS.B.1 (landed by SPEC 9, W1-P13a): the
coop guard at the head of BattlescapeGame::think()'s non-player branch
(`coopSuppressNonPlayerThink`, `BattlescapeGame.cpp:233`) means the HOST
NEVER runs AI locally for a human-commanded hostile side, and never
auto-advances a side out from under a connected human seat.

TWO LEGS, each its own boot (LF; each scenario runs exactly once, REV E.48
SS.A.8):

LEG A - gm2 (the RULED leg, REV E.58 E58.1 / REV E.60 E60.3): the CLIENT's
own aliens sit at coop seat 1 (assignSeatsAndFactions(), R5-P1/RB-D23), so
`coopSuppressNonPlayerThink` returns true at `BattlescapeGame.cpp:245` BEFORE
`selectNextPlayerUnit` (or `handleAI`) ever runs for them - no `origin:"ai"`
WALK is minted and the host does not auto-advance the side. Bring-up follows
`repro_atom_side_begin.run_gm2()`'s own steps (= `test_rw_faction_setup.
test_pvp_gm2`'s, plus the STR_SMALL_SCOUT mission pin) - an inline copy, this
tree's own precedent (every repro in this tree carries its own copy of the
lobby dance rather than sharing one, `repro_atom_side_begin.py`'s own module
docstring). `pin_ai_neutral` is called for the same reason every other SPEC
9..15 boundary test calls it, but in gm2 a pinned count of ZERO is LEGAL
(REV E.48 SS.B.4): the client's aliens are seat 1's, not COOP_SEAT_NONE, so
this leg never asserts count > 0.

LEG B - classic (the NON-VACUITY CONTROL: the SAME `event_state.lastWalk`
probe DOES move). M-12's pinned fixture (REV E.48 SS.E.4, seed 1 - PINNED
2026-09-15, wave1-log.md "SPEC 12 TASK 1"), copied byte-for-byte from the
measured scratchpad script (`m12_measure.py`, orch43c/orch43d F262): mission
STR_SMALL_SCOUT, `newbattle_race STR_FLOATER` in `pre_seat`, `set_seed 1` in
`pre_ok`, `battle_strip_unit` + `set_stat {psiSkill:0}` on every live hostile
at t=0 on BOTH machines (no TU pin - this leg needs the AI to move), the
F236/D66=(a) press pair (the client arms through its own `end_turn_button`
first, the driver waits for the host's rendered "END TURN 1/2", then the
host presses), then `sid.dismiss_next_turn_if_present` drives the host back
to the player side.

Cites WV-D44, WV-D45, REV E.48 SS.B.1/SS.B.2/SS.E.1/SS.E.4, REV E.58 E58.1,
REV E.60 E60.3 (F263: 12.1 s / 48 samples / lastWalk None throughout / the
seat-1 alien held 54 unspent TU), M-12 (F262: seed 1 PASS, moved 1, TU 50
-> 3).

Run:  python tools/coop_test/test_rw_nonplayer_think_gate.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import (battle_state, event_state, pin_ai_neutral,
                      FACTION_PLAYER, FACTION_HOSTILE)
import repro_atom_side_transition as sid
from repro_atom_side_begin import row_for as gm2_row_for, drive_side_change

MISSION = "STR_SMALL_SCOUT"
RACE = "STR_FLOATER"
SEED = 1
TALLY_TEXT_1_OF_2 = "END TURN 1/2"
OBSERVATION_WINDOW_S = 10.0
SAMPLE_INTERVAL_S = 0.25


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def drive_to_gm2_battlescape(host, client):
    """`repro_atom_side_begin.run_gm2()`'s own NewBattleState-inline drive
    (gm2 assigns seats automatically via assignSeatsAndFactions() -
    session.drive_to_battlescape's seat_count loop is a CLASSIC-only
    mechanism, it asserts >= 2 stamped soldiers), plus the STR_SMALL_SCOUT
    mission pin."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"
    r = host.cmd({"cmd": "newbattle_mission", "type": MISSION})
    assert r.get("ok"), (
        f"this build's NEW BATTLE screen does not offer {MISSION!r} in gm2 - "
        f"offered: {r.get('missionTypes')}")

    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)
    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape", lambda: session.has_state(host, "BattlescapeState"), timeout=40)
    session.dismiss_battle_start_overlays(host)
    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=90)
    client.wait_for("client entry briefing pushed over BattlescapeState",
                    lambda: session.has_state(client, "BriefingState") or None, timeout=20)
    session.dismiss_client_briefing(client)


def run_leg_a_gm2():
    """LEG A (REV E.58 E58.1's ruled leg): the gm2 hostile phase mints NO
    origin:"ai" WALK, and the host does not auto-advance out of it."""
    port = "48170"
    host_dir = make_user_dir("think_gate_a_host")
    client_dir = make_user_dir("think_gate_a_client")
    host = GameClient("host", 49560, host_dir)
    client = GameClient("client", 49561, client_dir)
    try:
        sid.bring_up_lobby(host, client, port)

        row = gm2_row_for(host, "ClientPlayer")
        r = host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"})
        assert r.get("gamemode") == 2, (
            f"expected gamemode 2 (PVP, client=Alien), got {r.get('gamemode')}")
        time.sleep(1)  # let the change_team broadcast settle on the client (pvp_fixture.py precedent)

        drive_to_gm2_battlescape(host, client)

        hs0 = battle_state(host)
        cs0 = battle_state(client)
        assert hs0.get("coopGamemode") == 2 and cs0.get("coopGamemode") == 2, (
            f"expected coopGamemode 2 on both machines: host={hs0.get('coopGamemode')} "
            f"client={cs0.get('coopGamemode')}")
        seat1 = [u for u in hs0["units"] if u.get("coop") == 1
                 and u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
        assert seat1, (
            f"non-vacuity gate: gm2 boot has no live seat-1 FACTION_HOSTILE unit: "
            f"{[u for u in hs0['units'] if u.get('coop') == 1]}")
        print(f"[LEG A] non-vacuity gate: coopGamemode==2 on both machines; seat 1 "
              f"holds {len(seat1)} live FACTION_HOSTILE unit(s): "
              f"{[u['id'] for u in seat1]}")

        pinned = pin_ai_neutral(host, client, tag="think-gate-gm2")
        print(f"[LEG A] pin_ai_neutral pinned {len(pinned)} unit(s) - 0 is legal in "
              "gm2 (REV E.48 SS.B.4: the client's aliens sit at seat 1, not NONE)")

        turn0 = battle_state(host)["turn"]
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_side_change(host, client, FACTION_HOSTILE, timeout=30)

        window_lw_h = event_state(host).get("lastWalk")
        window_lw_c = event_state(client).get("lastWalk")
        seat1_snapshot = {u["id"]: (session.unit_pos(u), u["tu"]) for u in
                          [uu for uu in battle_state(host)["units"] if uu.get("coop") == 1]}
        print(f"[LEG A] entered the hostile side (turn={turn0}); lastWalk at window "
              f"start: host={window_lw_h} client={window_lw_c}; seat-1 snapshot: "
              f"{seat1_snapshot}")

        deadline = time.time() + OBSERVATION_WINDOW_S
        samples = 0
        t_start = time.time()
        while time.time() < deadline:
            hs = battle_state(host)
            assert hs.get("side") == FACTION_HOSTILE and hs.get("turn") == turn0, (
                f"[LEG A] STOP-IF: the host auto-advanced off the hostile side "
                f"during the observation window (side={hs.get('side')} "
                f"turn={hs.get('turn')}, expected side={FACTION_HOSTILE} "
                f"turn={turn0})")
            hw = event_state(host).get("lastWalk")
            cw = event_state(client).get("lastWalk")
            assert hw == window_lw_h, (
                f"[LEG A] STOP-IF: host event_state.lastWalk CHANGED during the "
                f"observation window: {window_lw_h} -> {hw}")
            assert cw == window_lw_c, (
                f"[LEG A] STOP-IF: client event_state.lastWalk CHANGED during the "
                f"observation window: {window_lw_c} -> {cw}")
            samples += 1
            time.sleep(SAMPLE_INTERVAL_S)
        elapsed = time.time() - t_start
        print(f"[LEG A] observed {elapsed:.1f} s, {samples} samples: lastWalk "
              f"UNCHANGED on both machines; host stayed on side={FACTION_HOSTILE} "
              f"turn={turn0}")

        # supporting print (not a bar): no seat-1 unit moved / spent a TU
        seat1_now = {u["id"]: (session.unit_pos(u), u["tu"]) for u in
                     [uu for uu in battle_state(host)["units"] if uu["id"] in seat1_snapshot]}
        assert seat1_now == seat1_snapshot, (
            f"[LEG A] SUPPORTING assertion failed: a seat-1 unit moved or spent a "
            f"TU during the window: before={seat1_snapshot} after={seat1_now}")
        print(f"[LEG A] SUPPORTING: no seat-1 unit moved and none spent a TU during "
              f"the window: {seat1_now}")

        # advance the side with the host `battle_action end_turn` LEVER (the
        # button is dead off-side by vanilla design, REV E.48 SS.B.4) -
        # repro_atom_side_begin.run_gm2's own precedent.
        host.ok({"cmd": "battle_action", "action": "end_turn"})
        hs_final, cs_final = drive_side_change(host, client, FACTION_PLAYER, turn0 + 1, timeout=30)
        assert hs_final["side"] == FACTION_PLAYER and hs_final["turn"] == turn0 + 1, (
            f"[LEG A] host did not land at side=PLAYER turn={turn0 + 1}: {hs_final}")
        print(f"[LEG A] host reached side=FACTION_PLAYER turn={hs_final['turn']} via "
              "the end_turn lever")

        print("PASS: test_rw_nonplayer_think_gate LEG A (gm2)")
    finally:
        host.shutdown()
        client.shutdown()


def run_leg_b_classic():
    """LEG B (the NON-VACUITY CONTROL, M-12's pinned fixture, seed 1): the
    SAME lastWalk probe DOES move once the host reaches handleAI for a
    NONE-seat hostile."""
    port = "48171"
    host_dir = make_user_dir("think_gate_b_host")
    client_dir = make_user_dir("think_gate_b_client")
    host = GameClient("host", 49562, host_dir)
    client = GameClient("client", 49563, client_dir)
    seated = {}
    try:
        sid.bring_up_lobby(host, client, port)
        session.drive_to_battlescape(
            host, client, seated, mission=MISSION, seat_count=2,
            pre_seat=lambda h: h.ok({"cmd": "newbattle_race", "race": RACE}),
            pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED}))

        hostiles = [u for u in battle_state(host)["units"]
                    if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
        hostile_ids = [u["id"] for u in hostiles]
        assert hostile_ids, f"LEG B: no live hostile on the pinned seed {SEED}"

        for uid in hostile_ids:
            rh = host.cmd({"cmd": "battle_strip_unit", "unit": uid})
            rc = client.cmd({"cmd": "battle_strip_unit", "unit": uid})
            assert rh.get("ok") and rc.get("ok"), (
                f"LEG B: battle_strip_unit failed for unit {uid}: host={rh} client={rc}")
            assert rh.get("deleted") == rc.get("deleted"), (
                f"LEG B: E.5 - the two machines' deleted item id lists differ for "
                f"unit {uid}: host={rh.get('deleted')} client={rc.get('deleted')}")
            host.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid, "psiSkill": 0})
            client.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid, "psiSkill": 0})

        turn0 = battle_state(host)["turn"]

        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def _host_shows_1_of_2():
            return True if battle_state(host).get("coopEndTurnText") == TALLY_TEXT_1_OF_2 else None
        host.wait_for("host paints END TURN 1/2 after the client's arm",
                      _host_shows_1_of_2, timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        deadline = time.time() + 60
        returned = False
        while time.time() < deadline:
            sid.dismiss_next_turn_if_present(host)
            hs = battle_state(host)
            if hs.get("side") == FACTION_PLAYER and hs.get("turn", -1) >= turn0 + 1:
                returned = True
                break
            time.sleep(0.05)
        assert returned, (
            f"LEG B: host did not return to the player side within 60s: "
            f"{battle_state(host)}")

        lw = event_state(host).get("lastWalk")
        assert lw and lw.get("origin") == "ai", (
            f"LEG B non-vacuity control FAILED: host event_state.lastWalk.origin "
            f"is not 'ai' after a classic alien side - the probe LEG A relies on "
            f"never moved: {lw}")
        assert lw.get("steps"), f"LEG B: lastWalk carries no executed steps: {lw}"
        print(f"[LEG B] non-vacuity control OK: host event_state.lastWalk = {lw}")

        print("PASS: test_rw_nonplayer_think_gate LEG B (classic)")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run_leg_a_gm2()
    run_leg_b_classic()
    print("ALL SPEC 12 test_rw_nonplayer_think_gate TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_rw_nonplayer_think_gate", e.tracking, str(e))
        print(f"\ntest_rw_nonplayer_think_gate: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\ntest_rw_nonplayer_think_gate: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_rw_nonplayer_think_gate: FAIL\nTimeoutError: {e}")
        sys.exit(2)
