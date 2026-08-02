"""PRD-P9 6: mid-battle RESUME while the parallel player side is live.

The parallel feature adds per-battle state that lives nowhere in the save except
by implication: the executor invariant (`_isActivePlayerSync == getHost()`), the
action/side sequences, the deferred-intent store and the end-turn tally. A resume
that restored the battle but not those would come back either wedged (a stale
`side_seq` denies every client intent `turn_over`) or closed (a seat still
carrying "I am done" commits the new side the instant it opens).

What this asserts:

  1. LIVE. A mid-battle co-op campaign comes up with parallel turns ON: both
     machines hold `coopTurn == 2`, `parallelActive`, and the executor invariant.
  2. STATE. Actions are driven from BOTH seats so `actionSeq`, `sideSeq` and the
     readiness tally are all non-trivial; then the host saves mid-player-side.
  3. RESUME. Both processes are replaced (the client's user dir is EMPTY - the
     standing zero-disk invariant) and the pair resumes the save.
  4. RESTORED. `coop_parallel_turns` survived the save, the mode is live again on
     both machines, the invariant holds, and the arbiter came back RESET rather
     than half-remembered: `actionSeq`/`peerDisplayAckedSeq`/`pendingAdmits`/the
     client's pending slot at 0, the readiness tally empty, `side_seq` agreed.
  5. PLAYABLE. Both seats can act again - the client through an `action_intent`
     the host executes, the host locally - and the two machines stay in step
     (PRD-P2's drift terms).

Fixture: the SEPARATE mixed-ownership campaign battle from
test_coop_resume_battle_control.py, which is the one proven to survive a
save/reload round trip (a skirmish battle has no campaign to reload into).

Run:  python tools/coop_test/test_parallel_resume.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_coop_resume_battle_control as CRBC
import test_parallel_intents as PI

SAVE = "parallel_resume_battle.sav"
PORT = "47962"
RESUME_PORT = "47963"


def battle(gc):
    return PI.battle(gc)


def parallel(gc):
    return PI.parallel(gc)


def assert_parallel_live(host, client, phase):
    for gc, tag in ((host, "host"), (client, "client")):
        b = battle(gc)
        assert b.get("inBattle"), f"[{phase}] {tag} is not in a battle: {b}"
        assert b["parallelEnabled"] is True, (
            f"[{phase}] {tag}: `coop_parallel_turns` did not survive - the option "
            f"mirror is {b['parallelEnabled']}. It is written by SavedGame::save "
            f"and re-read on load; without it the resumed session silently drops "
            f"back to classic alternating sub-turns.")
        assert b["parallelActive"] is True, (
            f"[{phase}] {tag}: the mode is enabled but not LIVE ({b}) - "
            f"parallelTurnActive() also wants a co-op session in gamemode 1/4.")
        assert b["coopTurn"] == 2, (
            f"[{phase}] {tag}: coopTurn is {b['coopTurn']}, not 2. In parallel "
            f"mode BOTH machines hold the player side.")
    assert battle(host)["activeSync"] is True, \
        f"[{phase}] the host is not the executor: {battle(host)}"
    assert battle(client)["activeSync"] is False, (
        f"[{phase}] the CLIENT thinks it is the executor - the PRD-P5 invariant "
        f"`_isActivePlayerSync == getHost()` is what keeps the host the single "
        f"simulation authority: {battle(client)}")
    print(f"PASS [{phase}] parallel mode live on both machines, executor "
          f"invariant intact")


def assert_arbiter_reset(host, client, phase):
    """A resumed battle must come back with a CLEAN arbiter."""
    hp, cp = parallel(host), parallel(client)
    errs = []
    if hp["actionSeq"] != 0:
        errs.append(f"host actionSeq={hp['actionSeq']} (want 0)")
    if hp["peerDisplayAckedSeq"] != 0:
        errs.append(f"host peerDisplayAckedSeq={hp['peerDisplayAckedSeq']} (want 0)")
    if cp["peerDisplayAckedSeq"] != 0:
        errs.append(f"client peerDisplayAckedSeq={cp['peerDisplayAckedSeq']} (want 0)")
    if hp["pendingAdmits"]:
        errs.append(f"host pendingAdmits={hp['pendingAdmits']} (want none)")
    if cp["pendingReqId"] != 0:
        errs.append(f"client pendingReqId={cp['pendingReqId']} (want 0)")
    if hp["readySeats"] or hp["autoSeats"]:
        errs.append(f"host tally ready={hp['readySeats']} auto={hp['autoSeats']} "
                    f"(want both empty - a seat carrying 'I am done' across the "
                    f"resume would close the new side the instant it opened)")
    if cp["readySeats"]:
        errs.append(f"client tally ready={cp['readySeats']} (want empty)")
    if hp["sideSeq"] != cp["sideSeq"]:
        errs.append(f"side_seq disagrees: host {hp['sideSeq']} client "
                    f"{cp['sideSeq']} - every client intent would be denied "
                    f"`turn_over` until the next boundary re-aligned them")
    if hp["sideCommit"]:
        errs.append("host still has a side commit in progress")
    assert not errs, (f"[{phase}] the arbiter did not come back reset:\n    - "
                     + "\n    - ".join(errs)
                     + f"\n  host={hp}\n  client={cp}")
    print(f"PASS [{phase}] arbiter reset: actionSeq/display/pending/tally all "
          f"clear, side_seq {hp['sideSeq']} agreed on both")


def drive_one(host, client, gc, tag, unit_id, tries=3):
    """One action from `gc`, waited out on the executor.

    The claim being tested is "this seat can still ACT and the two machines stay
    in step", so the walk is retried with a fresh destination: a pathfinder answer
    goes stale between the probe and the execution often enough (a squadmate steps
    into the only exit) that a single attempt would make the test about the
    fixture rather than about the resume.
    """
    landed = None
    for attempt in range(tries):
        PI.top_up(host, client, unit_id)
        dest = PI.step_dest(host, client, unit_id)
        assert dest, f"{tag}: soldier {unit_id} cannot step anywhere"
        before = PI.pos(battle(host), unit_id)
        seq = parallel(host)["actionSeq"]
        r = PI.intent(gc, action="move", unit=unit_id,
                      x=dest[0], y=dest[1], z=dest[2])
        assert r.get("ok"), f"{tag}: the lever refused to build the intent: {r}"
        assert PI.wait_until(lambda: parallel(host)["actionSeq"] > seq, 60), (
            f"{tag}: the host never ADMITTED the action (actionSeq still {seq}); "
            f"the client was told {PI.warning_of(client)!r}, "
            f"host={parallel(host)}")
        moved = PI.wait_until(lambda: PI.pos(battle(host), unit_id) != before, 45)
        assert PI.idle(host, timeout=120), f"{tag}: the chain never ended"
        PI.settle(host, client, seconds=4)
        if moved:
            landed = PI.pos(battle(host), unit_id)
            break
        print(f"    ({tag}: the admitted walk of unit {unit_id} to {dest} covered "
              f"no ground - retrying with a fresh destination)")
    assert landed, (
        f"{tag}: three admitted walks in a row moved unit {unit_id} nowhere: "
        f"{parallel(host)}")
    assert PI.wait_until(lambda: PI.pos(battle(client), unit_id) == landed, 60), (
        f"{tag}: the peer never displayed it - host has {unit_id} at {landed}, "
        f"client at {PI.pos(battle(client), unit_id)}")
    print(f"    {tag} drove unit {unit_id} -> {landed} on both machines")
    return landed


def own_unit(gc, seat):
    for u in battle(gc)["units"]:
        if (u.get("faction") == 0 and not u.get("isOut")
                and u.get("coop") == seat and u.get("selectable")):
            return u["id"]
    for u in battle(gc)["units"]:
        if u.get("faction") == 0 and not u.get("isOut") and u.get("coop") == seat:
            return u["id"]
    return None


def main():
    host_dir = make_user_dir("p9_presume_host",
                             options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                      "skipNextTurnScreen": True,
                                      "EnableCoopParallelTurns": True})
    host = GameClient("host", 47871, host_dir)
    client = GameClient("client", 47872,
                        make_user_dir("p9_presume_client",
                                      options={"battleXcomSpeed": 2,
                                               "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    fail = None
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        CRBC.PORT = PORT
        PI.PORT = PORT
        CRBC.bring_up_mixed_battle(host, client)
        CRBC.drain_to_tactical(host, client)
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} co-op battle init",
                        lambda gc=gc: battle(gc).get("battleInit") or None,
                        timeout=120, interval=1.0)

        # --- 1 + 2: live, and driven from both seats before the save ----------
        assert_parallel_live(host, client, "before the save")
        hseat = parallel(host)["localSeat"]
        cseat = parallel(client)["localSeat"]
        hunit, cunit = own_unit(host, hseat), own_unit(client, cseat)
        assert hunit and cunit, (
            f"the mixed-ownership fixture did not give both seats a soldier "
            f"(host seat {hseat} -> {hunit}, client seat {cseat} -> {cunit})")
        drive_one(host, client, host, "host", hunit)
        drive_one(host, client, client, "client", cunit)
        # a non-zero tally at save time, so "the resume forgot it" is observable
        host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        assert PI.wait_until(lambda: parallel(host)["readySeats"] == [hseat], 30), (
            f"the host's END TURN press did not arm its readiness: "
            f"{parallel(host)}")
        pre = parallel(host)
        print(f"before the save: actionSeq={pre['actionSeq']} "
              f"sideSeq={pre['sideSeq']} readySeats={pre['readySeats']}")
        assert pre["actionSeq"] > 0, \
            "nothing was admitted before the save, so the reset assertion is vacuous"
        session.assert_battle_synced(host, client, "before the mid-battle save")

        # --- 3: save mid-player-side and replace both processes ---------------
        host.ok({"cmd": "save_game", "file": SAVE})
        assert os.path.exists(os.path.join(host_dir, "xcom1", SAVE)), \
            "the mid-battle save is not on disk"
        print(f"host saved mid-player-side -> {SAVE}")
        host.shutdown(); client.shutdown()

        host = GameClient("host", 47873, host_dir)
        client = GameClient("client", 47874,
                            make_user_dir("p9_presume_client2",
                                          options={"battleXcomSpeed": 2,
                                                   "battleAlienSpeed": 2,
                                                   "EnableCoopParallelTurns": False}))
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        session.resume_campaign_battle(host, client, SAVE, port=RESUME_PORT)
        CRBC.drain_to_tactical(host, client)
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} co-op battle init (resumed)",
                        lambda gc=gc: battle(gc).get("battleInit") or None,
                        timeout=150, interval=1.0)

        # --- 4: the mode and the arbiter came back -----------------------------
        assert_parallel_live(host, client, "after resume")
        assert_arbiter_reset(host, client, "after resume")

        # --- 5: and both seats can play -----------------------------------------
        hunit, cunit = own_unit(host, hseat), own_unit(client, cseat)
        assert hunit and cunit, (
            f"a seat lost its soldiers across the resume (host {hunit}, "
            f"client {cunit})")
        drive_one(host, client, client, "client", cunit)
        drive_one(host, client, host, "host", hunit)
        session.assert_battle_synced(host, client, "after the resumed actions")
        print("PASS [after resume] both seats act into the same player side again")

        session.assert_client_zero_disk(client.user_dir)
        print("PASS zero-disk: the resumed client wrote no save data")
        print("ALL PARALLEL MID-BATTLE RESUME TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  DBG {tag} parallel: {parallel(gc)}")
                print(f"  DBG {tag} states:   {session.states(gc)[-3:]}")
            except Exception as de:
                print(f"  DBG {tag} dump failed: {de}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
