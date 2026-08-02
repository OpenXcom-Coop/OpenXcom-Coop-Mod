"""PRD-P7: display flow control under an animation-speed skew.

The executor runs the whole battle and the peer only DISPLAYS it. Nothing in that
loop makes the two machines run at the same rate: `battleXcomSpeed` is a local
preference, so a host on 1 ms/frame and a client on 120 ms/frame drift apart by
one whole chain per action. Left alone the client would end up minutes behind,
watching walks the host finished long ago.

P7 bounds it from both ends:

  * `action_end` (host -> client) marks a chain as fully sent. It rides the
    ordinary receive gate, so the client consumes it exactly when it has finished
    DISPLAYING that chain, and answers `action_done {seq, seat}`.
  * `canAdmitAction()` refuses while `(_actionSeq - peerDisplayAckedSeq) >= 2`, so
    the executor can never be more than two chains ahead of what the peer has
    drawn. (`parallel_state.admitBlocked` reports `display_backlog` when that is
    the term that said no.)
  * the client fast-forwards its own display when an action packet is stuck behind
    the gate and what it is drawing is nothing but locomotion, so the backlog
    COMPRESSES rather than just blocking the host.

This test drives the executor through three walks back to back with the two
instances at opposite ends of the speed range and asserts:

  1. the undisplayed backlog never exceeds 2 (the whole point of the cap);
  2. all three walks execute, and at the end the peer has reported every one of
     them displayed (`peerDisplayAckedSeq == actionSeq`) - i.e. the `action_end`
     / `action_done` loop closes and cannot wedge the arbiter;
  3. both machines end on identical positions and TU;
  4. the PRD-P2 drift tripwire stays quiet - a fast-forwarded display must change
     nothing but how long the animation is on screen.

Run:  python tools/coop_test/test_parallel_speed_skew.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_intents as PI
import test_parallel_introspection as TI

PORT = "47988"

HOST_SPEED = 1     # fastest the option takes
CLIENT_SPEED = 300  # a slideshow, in the same units
WALKS = 3
BACKLOG_CAP = 2


def battle(gc):
    return PI.battle(gc)


def parallel(gc):
    return PI.parallel(gc)


def wait_admit(host, client, watch, timeout=180):
    """Wait for the executor to be ready for another input, SAMPLING all the way.
    If the display backlog is what is holding it, that is the window in which the
    bound has to be checked - a wait that does not sample would step right over
    the only moment the cap is visible."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ph, _ = sample(host, client, watch)
        if ph.get("canAdmit") is True and not ph.get("pendingAdmits"):
            return True
        time.sleep(0.05)
    return False


def sample(host, client, watch):
    """One poll of both machines' flow-control counters."""
    ph, pc = parallel(host), parallel(client)
    watch["backlog"] = max(watch["backlog"], ph.get("displayBacklog", 0))
    if ph.get("admitBlocked") == "display_backlog":
        watch["capped"] += 1
    if ph.get("fastForward"):
        watch["hostFF"] += 1
    if pc.get("fastForward"):
        watch["clientFF"] += 1
    return ph, pc


def main():
    fail = None
    host_dir = make_user_dir("p7_skew_host",
                             options={"battleXcomSpeed": HOST_SPEED,
                                      "battleAlienSpeed": 2,
                                      "skipNextTurnScreen": True,
                                      "EnableCoopParallelTurns": True})
    client_dir = make_user_dir("p7_skew_client",
                               options={"battleXcomSpeed": CLIENT_SPEED,
                                        "battleAlienSpeed": 2,
                                        "EnableCoopParallelTurns": False})
    # PRD-P7 asks for the two instances at OPPOSITE ends of the speed range, and
    # per-instance means the options.cfg splice, not set_option: the skew has to
    # be in force from the first frame of the battle.
    TI.assert_options_spliced(host_dir, {"battleXcomSpeed": HOST_SPEED})
    TI.assert_options_spliced(client_dir, {"battleXcomSpeed": CLIENT_SPEED})
    host = GameClient("host", 48876, host_dir)
    client = GameClient("client", 48877, client_dir)
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        TW.bring_up_battle(host, client)
        print("battle up on both machines")

        print(f"speed skew live: host {HOST_SPEED} ms/frame, client "
              f"{CLIENT_SPEED} ms/frame")

        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"the skirmish fixture came up in gamemode {gm}; parallel turns only "
            f"cover PVE (1) and PVE2 (4), so this test would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"
        ps = parallel(host)
        assert "displayBacklog" in ps and "peerDisplayAckedSeq" in ps, (
            f"parallel_state carries no display-flow counters, so the bound below "
            f"would be vacuous: {sorted(ps)}")

        mover = PI.pick_driver(host, client, 0, "host")
        # The skew only bites while the walker is ON SCREEN AND VISIBLE:
        # UnitWalkBState runs an off-screen walk at interval 0 whatever the option
        # says, and the fixture's teleported driver is seen by nobody on the
        # machine that does not own it. Without both, the "slow" client would
        # display at frame rate and never fall behind at all.
        aim = client.ok({"cmd": "battle_camera", "unit": mover, "visible": True})
        assert aim["onScreen"] and aim["visible"], \
            f"the client cannot actually watch the walker: {aim}"
        watch = {"backlog": 0, "capped": 0, "hostFF": 0, "clientFF": 0}
        start_seq = parallel(host)["actionSeq"]
        origin = PI.pos(battle(host), mover)

        # Topped up ONCE, before anything is in flight. Doing it per walk would
        # write raw TU onto a client that is still displaying the previous chain,
        # which is a harness-made divergence, not one P7 could cause.
        PI.top_up(host, client, mover, amount=250)

        admitted = 0
        for step in range(WALKS):
            # probe_step refuses mid-chain (singleton Pathfinding), so resolve the
            # destination while the executor's own queue is empty. The CLIENT is
            # deliberately not waited for - being behind is the point.
            assert wait_admit(host, client, watch), (
                f"walk {step}: the executor never freed up: {parallel(host)}")
            assert watch["backlog"] <= BACKLOG_CAP, (
                f"walk {step}: the executor ran {watch['backlog']} chains ahead "
                f"of what the peer had displayed while waiting to be free")
            client.cmd({"cmd": "battle_camera", "unit": mover, "visible": True})
            # Two tiles, not one: a one-tile step is over on the client before the
            # host's next input can be prepared, and no backlog ever forms.
            dest = PI.far_step(host, mover, radius=2) or PI.free_step(host, mover)
            if not dest:
                print(f"    (walk {step}: the mover can path nowhere - stopping "
                      f"after {admitted} walk(s))")
                break
            seq_before = parallel(host)["actionSeq"]
            r = PI.intent(host, action="move", unit=mover,
                          x=dest[0], y=dest[1], z=dest[2])
            assert r.get("ok"), f"walk {step}: the lever refused: {r}"

            # Poll hard while the chain runs: the backlog bound is an invariant,
            # not an end state, so it has to be sampled continuously.
            deadline = time.time() + 120
            while time.time() < deadline:
                ph, _ = sample(host, client, watch)
                assert watch["backlog"] <= BACKLOG_CAP, (
                    f"walk {step}: the executor ran {watch['backlog']} chains "
                    f"ahead of what the peer had displayed; canAdmitAction() must "
                    f"refuse at {BACKLOG_CAP}. host={ph}")
                if ph.get("actionSeq", 0) > seq_before and ph.get("canAdmit") is True:
                    break
                time.sleep(0.05)
            if parallel(host)["actionSeq"] > seq_before:
                admitted += 1
            print(f"    walk {step}: actionSeq {seq_before} -> "
                  f"{parallel(host)['actionSeq']}, backlog high-water "
                  f"{watch['backlog']}")

        assert admitted >= 2, (
            f"only {admitted} of {WALKS} walks were admitted - the executor was "
            f"blocked, not merely paced: {parallel(host)}")

        # Let the slow machine catch up, then prove the loop CLOSED.
        assert PI.wait_until(
            lambda: parallel(host)["peerDisplayAckedSeq"]
            == parallel(host)["actionSeq"], 180, interval=0.5), (
            f"the peer never reported the last chain displayed: host="
            f"{parallel(host)} client={parallel(client)}. `action_end` /"
            f"`action_done` is the only thing that moves peerDisplayAckedSeq, and "
            f"if it stalls the arbiter refuses every further action for the rest "
            f"of the side.")
        PI.settle(host, client, seconds=8)

        # Re-base the peer's TU before comparing it. The walk's teleport-correct
        # (`abortPath`) carries POSITION and facing but no TU, so after the LAST
        # walk of a run the peer's TU is whatever its own partial animation had
        # spent when the abort cut it off - a pre-existing co-op gap that a
        # deliberately slow peer is simply very good at exposing (P7's client
        # fast-forward narrows it, it does not cause it: an interval-0 display
        # spends MORE of the path before the abort lands). A turn's replay packet
        # carries the authoritative value and does not re-charge, so one turn
        # re-bases it. Two directions, because a turn that turns nothing ships no
        # packet at all.
        here = PI.pos(battle(host), mover)
        for dx in (1, -1):
            PI.intent(host, action="turn", unit=mover,
                      x=here[0] + dx, y=here[1] + dx, z=here[2])
            wait_admit(host, client, watch)
            PI.settle(host, client, seconds=3)
        assert PI.wait_until(
            lambda: parallel(host)["peerDisplayAckedSeq"]
            == parallel(host)["actionSeq"], 180, interval=0.5), (
            f"the peer fell behind again on the re-basing turns: host="
            f"{parallel(host)} client={parallel(client)}")
        sample(host, client, watch)

        ph, pc = parallel(host), parallel(client)
        assert ph["actionSeq"] >= start_seq + admitted, (
            f"action_seq did not advance once per admitted walk "
            f"({start_seq} -> {ph['actionSeq']} over {admitted})")
        assert pc["displaySeq"] == ph["actionSeq"], (
            f"the client thinks it has displayed chain {pc['displaySeq']} while "
            f"the host has admitted {ph['actionSeq']}")
        assert watch["backlog"] <= BACKLOG_CAP, \
            f"backlog high-water {watch['backlog']} exceeded the cap"

        hb, cb = battle(host), battle(client)
        assert PI.pos(hb, mover) == PI.pos(cb, mover), (
            f"the two machines disagree about unit {mover} after the skewed run: "
            f"host {PI.pos(hb, mover)} client {PI.pos(cb, mover)}")
        assert PI.pos(hb, mover) != origin, "the mover never actually moved"
        assert PI.tu(hb, mover) == PI.tu(cb, mover), (
            f"TU diverged: host {PI.tu(hb, mover)} client {PI.tu(cb, mover)}")
        session.assert_battle_synced(host, client, "after the speed-skewed run")
        assert not TW.desync_seen(host) and not TW.desync_seen(client), \
            "the PRD-P2 drift tripwire fired during the speed-skewed run"

        print(f"PASS: {admitted} walk(s) at a {HOST_SPEED}:{CLIENT_SPEED} speed "
              f"skew - backlog high-water {watch['backlog']} (cap {BACKLOG_CAP}), "
              f"cap engaged {watch['capped']}x, host fast-forward seen "
              f"{watch['hostFF']}x, client display fast-forward seen "
              f"{watch['clientFF']}x; both machines identical at "
              f"{PI.pos(hb, mover)}, tripwire quiet")
        print("ALL SPEED-SKEW FLOW-CONTROL TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
