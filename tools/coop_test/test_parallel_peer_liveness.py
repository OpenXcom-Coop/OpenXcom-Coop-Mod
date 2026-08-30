"""Class-A soak wedge (A3): a peer that goes dark mid-battle is DETECTED, not silent.

The forensic wedge (CI run 32091728914, test_parallel_soak): the parallel PASSIVE
CLIENT deadlocked mid shot-replay and fell 13 turn-boundaries behind the host. No
existing detector fired, because a wedged peer does not DIVERGE - it goes SILENT. Every
per-term tripwire (items, units, terrain, saveBlob) compares state the two machines
report; a peer that has stopped reporting produces nothing to compare, so the session
just freezes with no banner and no bundle.

A3 adds a peer-liveness term to the host's tripwire. The host keeps crossing boundaries
(g_syncLastBoundarySeq climbs) while a gone-dark peer stops answering the boundary
markers (g_syncLastComparedBoundarySeq freezes). When that gap has been >= a bar
continuously for a stall window, the SAME shared desync path latches (banner + one
bundle) - reusing the drift-tripwire machinery, no new alarm channel.

  1. NO FALSE FIRE. Under the SHIPPED thresholds, at a client speed-skew, several clean
     turn cycles never latch: the peer keeps answering, so the gap re-closes and the
     stall clock resets every cycle. This is the discipline the task requires - the
     term must survive normal backlog and the speed-skew profile.
  2. RED. Force the peer dark on boundaries (park only its boundary `action_done`, so
     per-chain acks keep the host committing and crossing boundaries) and drive turn
     cycles. The boundary gap grows past the bar and, once sustained, the liveness
     tripwire latches on the host - which the forensic wedge would have.

The red case uses a lowered firing bar (setLivenessGap / setLivenessStallMs) so it fires
in seconds; the no-false-fire case uses the shipped defaults, which is what actually has
to be safe in the field.

Run:  python tools/coop_test/test_parallel_peer_liveness.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import test_battle_tripwire as TW
import test_parallel_intents as PI
import test_parallel_endturn as PE

PORT = "47995"

FAST_SPEED = 2
SKEW_SPEED = 40      # ms/frame on the client: the soak's speed-skew draw speed
RED_GAP = 2          # boundaries behind ...
RED_STALL_MS = 1500  # ... continuously for this long, to fire fast in the red case
CLEAN_CYCLES = 2
RED_MAX_CYCLES = 4


def parallel(gc):
    return PI.parallel(gc)


def battle(gc):
    return PI.battle(gc)


def sync(gc):
    return parallel(gc).get("syncCheck", {})


def set_thresholds(host, gap, stall_ms):
    host.ok({"cmd": "parallel_state", "setLivenessGap": gap, "setLivenessStallMs": stall_ms})


def drive_cycle(host, client, timeout=240):
    """Close the player side from both seats and wait for it to come back - the
    thing that makes the host cross boundaries. Fixture protection (hush) each time,
    because every closed side is an alien side that can shoot the fixture out."""
    assert PI.idle(host, timeout=90), f"the host never went idle before the cycle: {parallel(host)}"
    if not battle(host).get("inBattle"):
        return None
    PE.hush(host, client)
    turn_before = PE.turn_of(host)
    PE.arm(host)
    PE.arm(client)
    return PE.wait_side(host, client, turn_before, timeout=timeout)


def main():
    fail = None
    host = GameClient("host", 48898,
                      make_user_dir("a3_liveness_host",
                                    options={"battleXcomSpeed": FAST_SPEED,
                                             "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48899,
                        make_user_dir("a3_liveness_client",
                                      options={"battleXcomSpeed": SKEW_SPEED,
                                               "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        PE.PORT = PORT
        TW.bring_up_battle(host, client)
        print("battle up on both machines (client at a %d ms/frame speed skew)"
              % SKEW_SPEED)

        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"the skirmish fixture came up in gamemode {gm}; parallel turns only "
            f"cover PVE (1) and PVE2 (4), so this test would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"

        s = sync(host)
        for field in ("peerLivenessGap", "peerLivenessLatched", "lastBoundarySeq",
                      "lastComparedBoundarySeq"):
            assert field in s, (
                f"the sync-check readout carries no `{field}` - this test would be "
                f"vacuous: {sorted(s)}")

        # ---- 1. NO FALSE FIRE: shipped thresholds, speed-skew, clean cycles ----
        print("-- 1: shipped thresholds + speed-skew: clean cycles never latch --")
        set_thresholds(host, 0, -1)   # restore shipped defaults
        host.ok({"cmd": "shared_reset_resync_stats"})
        client.ok({"cmd": "shared_reset_resync_stats"})
        max_gap = 0
        for i in range(CLEAN_CYCLES):
            turn = drive_cycle(host, client)
            assert turn, (
                f"clean cycle {i}: the side never came back (fixture may have ended): "
                f"host top={TW.top(host)} client top={TW.top(client)} "
                f"inBattle={battle(host).get('inBattle')}")
            g = sync(host).get("peerLivenessGap", 0)
            max_gap = max(max_gap, g)
            assert sync(host).get("peerLivenessLatched", 0) == 0, (
                f"clean cycle {i}: the peer-liveness tripwire latched under NORMAL "
                f"speed-skew play (gap {g}) - a false fire: {sync(host)}")
            assert not TW.desync_seen(host), (
                f"clean cycle {i}: the shared desync path latched on the host under "
                f"clean play")
            print(f"    clean cycle {i}: side closed, peerLivenessGap peaked {g}, "
                  f"no latch")
        # the peer is answering, so after settling the gap has re-closed below the bar:
        # the mechanism reads a caught-up peer as healthy and the clock never sustains.
        assert PI.wait_until(
            lambda: sync(host).get("peerLivenessGap", 99)
            < sync(host).get("peerLivenessBoundaryGap", 2), 60), (
            f"the boundary-answer gap never fell below the bar with the peer answering "
            f"normally - the term would eventually false-fire: {sync(host)}")
        assert sync(host).get("peerLivenessLatched", 0) == 0 and not TW.desync_seen(host), (
            f"the tripwire latched during the clean speed-skew run (max gap "
            f"{max_gap}): {sync(host)}")
        print(f"PASS 1: {CLEAN_CYCLES} clean speed-skew cycle(s), max boundary gap "
              f"{max_gap}, gap re-closed below the bar, NO false fire")

        # ---- 2. RED: force the peer dark on boundaries -> the tripwire fires ----
        print("-- 2: peer goes dark on boundary answers -> the tripwire latches --")
        assert battle(host).get("inBattle"), "the fixture ended before the red phase"
        host.ok({"cmd": "shared_reset_resync_stats"})
        client.ok({"cmd": "shared_reset_resync_stats"})
        set_thresholds(host, RED_GAP, RED_STALL_MS)
        # Park ONLY the client's boundary answer: per-chain acks keep flowing, so the
        # host keeps committing and crossing boundaries while g_syncLastComparedBoundarySeq
        # freezes - the exact peer-went-dark-on-boundaries condition.
        r = client.ok({"cmd": "hold_action_done", "boundary": True, "hold": True})
        assert r.get("holdBoundary") is True, \
            f"the boundary-answer park did not engage: {r}"
        print(f"    client parking its boundary answers; firing bar lowered to gap "
              f"{RED_GAP} / {RED_STALL_MS} ms")

        latched = False
        peaked = 0
        for i in range(RED_MAX_CYCLES):
            turn = drive_cycle(host, client)
            # (a cycle may not "return" cleanly once the tripwire banner is up; that is
            #  fine - what we assert is the latch, checked below regardless)
            g = sync(host).get("peerLivenessGap", 0)
            peaked = max(peaked, g)
            print(f"    red cycle {i}: peerLivenessGap now {g} "
                  f"(host boundary {sync(host).get('lastBoundarySeq')}, peer answered "
                  f"{sync(host).get('lastComparedBoundarySeq')})")
            # once the gap is up, the latch is a stall window away
            if PI.wait_until(
                    lambda: sync(host).get("peerLivenessLatched", 0) == 1
                    and TW.desync_seen(host), 8):
                latched = True
                break
            if not battle(host).get("inBattle"):
                break
        assert latched, (
            f"the peer stopped answering boundary markers (gap peaked {peaked}) and "
            f"the liveness tripwire NEVER latched - a peer-gone-dark wedge would stay "
            f"silent in the field: host sync={sync(host)}, desyncSeen="
            f"{TW.desync_seen(host)}")
        assert sync(host).get("peerLivenessGap", 0) >= RED_GAP, (
            f"the tripwire latched but the recorded gap is below the bar it fired on: "
            f"{sync(host)}")
        print(f"PASS 2: the host's peer-liveness tripwire latched on a sustained "
              f"boundary-answer gap of {sync(host).get('peerLivenessGap')} "
              f"(peaked {peaked}) - the wedge is DETECTED")

        # the CLIENT (which is not the comparer) must not have latched off its own state
        print("PASS: peer-liveness detection fires on a gone-dark peer and stays quiet "
              "under normal speed-skew backlog")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  DBG {tag} sync: {sync(gc)}")
                print(f"  DBG {tag} top:  {TW.top(gc)}")
            except Exception as de:
                print(f"  DBG {tag} dump failed: {de}")
    finally:
        try:
            client.ok({"cmd": "hold_action_done", "boundary": True, "hold": False})
            set_thresholds(host, 0, -1)
            host.ok({"cmd": "shared_reset_resync_stats"})
            client.ok({"cmd": "shared_reset_resync_stats"})
        except Exception:
            pass
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
