"""SPEC 12 (W1-P13d) - test_rw_client_nextturn.py: REV E.58 E58.3 (D85 = (d))
as corrected by REV E.59 E59.3 - SPEC 9's guarded call at
`NextTurnState::close()` (`coopSuppressNextTurnLifecycle`, W1-P13a) makes a
CLIENT's own `NextTurnState` dismissal presentation-only: `cleanupDeleted` +
`popState` always run, but the tally / mind-control conversion /
`finishBattle` / autosave tail below them never runs on a client. This unit
does not build that guard (it is SPEC 9's) - it is SPEC 12's ACCEPTANCE of
it.

PROOF METHOD: the HOST's vanilla tail is proven by the real battle autosave
file `NextTurnState::close()` writes (`NextTurnState.cpp:544-587`), not by a
new probe - `_state->autosave(_currentTurn)` fires when `_currentTurn == 1 ||
_currentTurn % Options::autosaveFrequency == 0` and
`_battleGame->getSide() == FACTION_PLAYER`, landing synchronously at
`<user_dir>/xcom1/_autobattle_.asav` (`xcom1` is the hermetic master mod
`harness.make_user_dir` pins). The CLIENT's own dismissal writing NO file is
TRUE BY CONSTRUCTION (`localSavesAllowed()` false swallows every client
save, `SaveGameState.cpp:192`) and is recorded INFORMATIONALLY, never as a
bar.

THE SETUP: a classic seated boot (REV E.48 SS.B.2 pin, mission
STR_SMALL_SCOUT) crossing a full side boundary. `BattlescapeGame::endTurn()`
pushes a `NextTurnState` at EVERY side transition except the one INTO the
neutral side (`BattlescapeGame.cpp:764`: `if ((side != FACTION_NEUTRAL ||
battleComplete) && _endTurnRequested)`), so one full cycle shows TWO of them
per machine: a transient HOSTILE-side one (no autosave - the vanilla `else`
arm's own `side == FACTION_PLAYER` guard) and, after
HOSTILE->NEUTRAL->PLAYER, the PLAYER-side one this file's two legs act on
(F228's lesson: do not assume which NextTurnState is on top). The transient
HOSTILE-side one on each machine is dismissed by this file's own driver
(`drive_to_final_nextturn`) as ordinary setup - via the REAL `close_nextturn`
path, never `dismiss_popup`, which pops a NextTurnState WITHOUT running
close().

WV-D77 (instrumented on the first surprise, captured, then fixed TWICE - a
test bookkeeping bug, not a product one). A `side`-only dismiss loop races
on the CLIENT (with B.2 pinning the whole hostile+neutral phase instantly
inert, the client can apply its ENTIRE event backlog - pushing EVERY
NextTurnState in it - before the first poll ever runs; captured stack
`['...BattlescapeState', 'NextTurnState', 'NextTurnState']`, both already
present). A stack-COUNT-only drain is wrong the OTHER way on the HOST (the
very first NextTurnState pushed, for the transient HOSTILE-side entry, ALSO
reads "exactly one" before anything has dismissed it; captured:
`battle_state` stuck at `side=1, turn=1` after the drain "succeeded" without
ever advancing). `drive_to_final_nextturn` reads BOTH signals - see its own
doc comment for the full trace and why that combination is sound for both
machines.

Cites REV E.48 SS.B.2, REV E.58 E58.3 (D85), REV E.59 E59.3 (F246: the
top-state probe is `list_widgets`'s `resp["state"]`, `TestServer.cpp:7878`
handler / `:7908` field - not `:3634`/`:6847`, unreachable in a battle),
F255 (the measured autosave file BEFORE/AFTER pair).

Run:  python tools/coop_test/test_rw_client_nextturn.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean, FACTION_PLAYER
import repro_atom_side_transition as sid

MISSION = "STR_SMALL_SCOUT"
TALLY_TEXT_1_OF_2 = "END TURN 1/2"
AUTOSAVE_FILENAME = "_autobattle_.asav"
MASTER_MOD_DIR = "xcom1"


def autosave_path(gc):
    return os.path.join(gc.user_dir, MASTER_MOD_DIR, AUTOSAVE_FILENAME)


def autosave_snapshot(gc):
    p = autosave_path(gc)
    if not os.path.exists(p):
        return None
    st = os.stat(p)
    return (st.st_size, st.st_mtime)


def top_state_of(gc):
    return gc.cmd({"cmd": "list_widgets"}).get("state", "")


def count_nextturn(gc):
    return sum(1 for s in gc.cmd({"cmd": "get_state"})["states"] if "NextTurnState" in s)


def drive_to_final_nextturn(gc, target_side, target_turn, timeout=60):
    """Dismisses NextTurnStates (the REAL close() path, never `dismiss_popup`)
    as `gc` passes through this boundary, until `battle_state` reports
    side==target_side and turn==target_turn (GROUND TRUTH - reliable even
    though the NextTurnState push/pop queue can lag behind it or, on a fast
    fully-B.2-pinned cycle, race AHEAD of it), then drains any STILL-EXTRA
    stacked NextTurnState down to exactly ONE - left standing for the caller
    to close as the action under test.

    WV-D77 (instrumented on the first surprise, captured, then fixed - a
    test bookkeeping bug, not a product one). Two captures:
    (1) A `side`-based dismiss loop ("close the current one while
    `battle_state()['side'] != FACTION_PLAYER'") RACES on the CLIENT: with
    `pin_ai_neutral` making the whole hostile+neutral phase instantly inert,
    the client applies its ENTIRE event backlog for this boundary - pushing
    EVERY NextTurnState in it - before the driver's first poll ever runs.
    Captured stack: `['...BattlescapeState', 'NextTurnState',
    'NextTurnState']`, both already present. `side` reflects the CURRENT
    value the instant an event applies, outpacing the state-stack push, so
    a check that stops the instant it merely SEES side==target leaves an
    older, un-dismissed one buried underneath (timed out: "CLIENT leg: never
    returned to BattlescapeState", one `NextTurnState` still on the stack).
    (2) A pure STACK-COUNT drain ("settle at exactly one, regardless of
    `side`") is wrong the OTHER way on the HOST: the very FIRST
    NextTurnState pushed (for the transient HOSTILE-side entry) also reads
    "exactly one" before anything has dismissed it, so a count-only rule
    returns immediately at side=HOSTILE/turn=1 and never drives the cycle
    forward at all (captured: `battle_state` stuck at
    `side=1, turn=1` after the drain "succeeded").
    This function reads BOTH: it only stops closing once the GROUND TRUTH
    side/turn has genuinely been reached, and only then drains the stack
    count down to one - sound for the HOST (which cannot race ahead of its
    own UI: NextTurnState blocks `think()` until dismissed, so nothing is
    ever stacked before `side` reflects it) and for the CLIENT (whose extra,
    already-stacked entries are interchangeable for this purpose - SPEC 9's
    client-side close() tail is presentation-only regardless of which
    transition a given instance nominally represents, so it does not matter
    which of several already-stacked instances ends up being the one left
    standing)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        bs = battle_state(gc)
        reached = bs.get("side") == target_side and bs.get("turn") == target_turn
        n = count_nextturn(gc)
        if reached and n == 1:
            return
        if "NextTurnState" in top_state_of(gc) and not (reached and n <= 1):
            r = gc.cmd({"cmd": "close_nextturn"})
            assert r.get("ok"), f"{gc.name}: close_nextturn failed: {r}"
        time.sleep(0.02)
    raise TimeoutError(
        f"{gc.name}: did not settle to exactly one NextTurnState at "
        f"side={target_side}/turn={target_turn} within {timeout}s - "
        f"battle_state={battle_state(gc)}, "
        f"stack={gc.cmd({'cmd': 'get_state'})['states']}")


def run():
    port = "48173"
    host_dir = make_user_dir("client_nextturn_host")
    client_dir = make_user_dir("client_nextturn_client")
    host = GameClient("host", 49566, host_dir)
    client = GameClient("client", 49567, client_dir)
    seated = {}
    try:
        sid.bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                      pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": 1}))

        pinned = pin_ai_neutral(host, client, tag="client_nextturn")
        assert len(pinned) > 0, (
            f"pin_ai_neutral pinned ZERO NONE-seat non-player units on a "
            f"CLASSIC {MISSION} boot - the premise is unexercised (M9a-3)")

        for gc in (host, client):
            r1 = gc.cmd({"cmd": "set_option", "name": "autosave", "value": True})
            assert r1.get("ok"), f"{gc.name}: set_option autosave failed: {r1}"
            r2 = gc.cmd({"cmd": "set_option", "name": "autosaveFrequency", "value": 1})
            assert r2.get("ok"), f"{gc.name}: set_option autosaveFrequency failed: {r2}"

        before_snap = autosave_snapshot(host)
        print(f"[setup] host {autosave_path(host)} BEFORE: {before_snap}")

        turn0 = battle_state(host)["turn"]

        # ---- F236/D66=(a) press pair: needed==2 in this classic fixture ----
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def _host_shows_1_of_2():
            return True if battle_state(host).get("coopEndTurnText") == TALLY_TEXT_1_OF_2 else None
        host.wait_for("host paints END TURN 1/2 after the client's arm",
                      _host_shows_1_of_2, timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        # ---- drive BOTH machines down to their own single, FINAL
        # PLAYER-side NextTurnState, dismissing each machine's transient
        # HOSTILE-side one along the way (drive_to_final_nextturn's own
        # doc comment carries the WV-D77 trace for both machines) ----
        target_turn = turn0 + 1
        drive_to_final_nextturn(host, FACTION_PLAYER, target_turn, timeout=60)
        drive_to_final_nextturn(client, FACTION_PLAYER, target_turn, timeout=60)

        hs_at_close = battle_state(host)
        assert hs_at_close.get("side") == FACTION_PLAYER, (
            f"HOST leg premise broke: host is not on the PLAYER side at close: "
            f"{hs_at_close}")
        print(f"[HOST leg] closing the PLAYER-side NextTurnState at "
              f"side={hs_at_close.get('side')} turn={hs_at_close.get('turn')} "
              f"(turn0={turn0})")

        # ==== HOST LEG ====
        r = host.cmd({"cmd": "close_nextturn"})
        assert r.get("handled") == "NextTurnState::close", (
            f"HOST leg: close_nextturn did not report the real close() path: {r}")

        def _autosave_written():
            snap = autosave_snapshot(host)
            if snap is None:
                return None
            size, mtime = snap
            if size <= 0:
                return None
            if before_snap is not None and mtime <= before_snap[1]:
                return None
            return snap
        after_snap = host.wait_for(
            "HOST leg: the battle autosave file appears/updates",
            _autosave_written, timeout=30)
        print(f"[HOST leg] {autosave_path(host)} AFTER: {after_snap}")

        host.wait_for("HOST leg: back on BattlescapeState",
                      lambda: ("BattlescapeState" in top_state_of(host)) or None,
                      timeout=30)

        hs_after = battle_state(host)
        assert hs_after.get("inBattle") is True, (
            f"HOST leg: host is not inBattle after the close: {hs_after}")
        assert_hash_clean(host, client, full=True,
                          what="HOST leg after the host's NextTurnState close")
        hd = event_state(host).get("desyncSeen")
        assert hd is False, f"HOST leg: host desyncSeen is not False: {hd}"
        print("[HOST leg] PASS: inBattle=True, all buckets EQUAL, desyncSeen=False")

        # ==== CLIENT LEG ====
        hh_before, ch_before = assert_hash_clean(
            host, client, full=True, what="CLIENT leg BEFORE the client's own close")

        rc = client.cmd({"cmd": "close_nextturn"})
        assert rc.get("handled") == "NextTurnState::close", (
            f"CLIENT leg: close_nextturn did not report the real close() path: {rc}")

        client.wait_for("CLIENT leg: back on BattlescapeState",
                        lambda: ("BattlescapeState" in top_state_of(client)) or None,
                        timeout=30)

        hh_after, ch_after = assert_hash_clean(
            host, client, full=True, what="CLIENT leg AFTER the client's own close")
        assert hh_before == hh_after and ch_before == ch_after, (
            f"CLIENT leg: hash_now changed across the client's own dismissal - "
            f"before host={hh_before} client={ch_before}; "
            f"after host={hh_after} client={ch_after}")

        cs_after = battle_state(client)
        assert cs_after.get("inBattle") is True, (
            f"CLIENT leg: client is not inBattle after its own close: {cs_after}")

        client_wrote = os.path.exists(autosave_path(client))
        print(f"[CLIENT leg] client wrote no autosave (informational, E58.3): "
              f"exists={client_wrote}")

        print(f"[CLIENT leg] PASS: hash_now EQUAL before and after "
              f"({len(hh_before)} buckets), inBattle=True")

        print("PASS: test_rw_client_nextturn")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run()
    print("ALL SPEC 12 test_rw_client_nextturn TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_rw_client_nextturn", e.tracking, str(e))
        print(f"\ntest_rw_client_nextturn: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\ntest_rw_client_nextturn: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_rw_client_nextturn: FAIL\nTimeoutError: {e}")
        sys.exit(2)
