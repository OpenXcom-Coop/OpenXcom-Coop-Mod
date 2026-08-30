"""Class-A soak wedge (A1): the auto-shot pacing wait can never starve the receive
gate forever.

The forensic wedge (CI run 32091728914, test_parallel_soak): the parallel PASSIVE
CLIENT deadlocked mid shot-replay and never recovered. A multi-shot ExplosionBState
replay parked on `_hasHitUnit == 1` (ExplosionBState.cpp) waiting for the host's flip
packet; the flip never came (a host/client shot-count divergence, likeliest on
hazard-heavy turns where a terrain-chain ExplosionBState reads the same shared pacing
flag). The ProjectileFlyBState beneath it (`_coopInitDeath`, gate depth 1) then held
the receive gate for the rest of the battle: taskDepth stuck at 1, rxRotates in the
millions, the client 13 turn-boundaries behind the host. The existing per-subject/seq
liveness floor (`kRxBlockedStallTicks`) does NOT cover it - a gate held with only
gate-rotated (non-whitelisted) traffic leaves `blockedSomething` false, so it never
counts.

The fix adds a SEPARATE floor for the pacing wait itself: updateCoopTask counts the
consecutive game-loop ticks `_coopPacingWait` has been held and, past
`kRxPacingForceDrainTicks` (~10 s of wall time, counted at the game-loop rate so it is
bounded regardless of the client's draw speed), raises `_coopForceDrainReplay`, which
ExplosionBState::think() consumes to end the wait AS IF the flip had landed. That drains
the ProjectileFlyBState and reopens the gate.

Staging a REAL ExplosionBState wait deterministically would need a shot that hits a unit
mid-multi-shot with the host's flip withheld - no fixture can arrange that reliably. So
this exercises the RX-pump floor directly through the `armPacingWait` lever, which sets
`_coopPacingWait` on the client the way ExplosionBState::explode() would:

  1. CONTROL. A quiescent parallel battle never arms the wait and never force-drains:
     `coopPacingWait` False, `forceDrainCount` 0, held for several seconds.
  2. RED->GREEN. Arm the wait and leave it armed (no flip ever comes). WITHOUT the
     floor this is the permanent wedge; WITH it the pump raises the escape within the
     bounded window and `forceDrainCount` climbs. That is the capability under test:
     a pacing wait that never gets its flip is broken, not tolerated forever.
  3. CLEAR. Disarming clears the wait and the raised escape flag, so nothing leaks onto
     a later real shot.

Run:  python tools/coop_test/test_parallel_pacing_escape.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import test_battle_tripwire as TW
import test_parallel_intents as PI

PORT = "47994"
FAST_SPEED = 2

# The floor is kRxPacingForceDrainTicks == 600 game-loop ticks (~10 s at 60/s). Give
# the headless loop generous headroom before calling a non-fire a failure.
ESCAPE_WAIT = 30.0


def parallel(gc):
    return PI.parallel(gc)


def battle(gc):
    return PI.battle(gc)


def arm_wait(gc, on):
    r = gc.ok({"cmd": "parallel_state", "armPacingWait": bool(on)})
    return r


def main():
    fail = None
    host = GameClient("host", 48896,
                      make_user_dir("a1_pacing_host",
                                    options={"battleXcomSpeed": FAST_SPEED,
                                             "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48897,
                        make_user_dir("a1_pacing_client",
                                      options={"battleXcomSpeed": FAST_SPEED,
                                               "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        TW.bring_up_battle(host, client)
        print("battle up on both machines")

        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"the skirmish fixture came up in gamemode {gm}; parallel turns only "
            f"cover PVE (1) and PVE2 (4), so this test would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"

        pc = parallel(client)
        for field in ("coopPacingWait", "forceDrainReplay", "forceDrainCount"):
            assert field in pc, (
                f"parallel_state carries no `{field}` - this test would be vacuous: "
                f"{sorted(pc)}")

        # ---- 1. CONTROL: a quiescent battle never force-drains --------------
        print("-- 1: a quiescent parallel battle never arms the pacing wait --")
        base = parallel(client)["forceDrainCount"]
        assert parallel(client)["coopPacingWait"] is False, \
            f"the client is already in a pacing wait at rest: {parallel(client)}"
        t_end = time.time() + 4.0
        while time.time() < t_end:
            assert parallel(client)["forceDrainCount"] == base, (
                f"the RX pump force-drained with NO pacing wait armed "
                f"(count {base} -> {parallel(client)['forceDrainCount']}) - the floor "
                f"is firing spuriously")
            time.sleep(0.25)
        print(f"    forceDrainCount steady at {base}, coopPacingWait False for 4 s")

        # ---- 2. RED->GREEN: an armed-and-never-released wait is force-drained -
        print("-- 2: an unreleased pacing wait is force-drained, not starved forever --")
        r = arm_wait(client, True)
        assert r.get("ok"), f"the armPacingWait lever did not take: {r}"
        assert PI.wait_until(
            lambda: parallel(client)["coopPacingWait"] is True, 5), (
            f"the pacing wait did not arm: {parallel(client)}")
        print("    pacing wait armed (the wedged-forever state); no flip will ever come")

        deadline = time.time() + ESCAPE_WAIT
        fired = False
        while time.time() < deadline:
            pcs = parallel(client)
            if pcs["forceDrainCount"] > base:
                fired = True
                break
            time.sleep(0.2)
        assert fired, (
            f"the RX pump never force-drained an armed pacing wait within "
            f"{ESCAPE_WAIT:.0f} s (forceDrainCount stuck at {base}) - WITHOUT this "
            f"floor the receive gate stays held for the rest of the battle, which is "
            f"the Class-A soak wedge: {parallel(client)}")
        print(f"    the floor fired: forceDrainCount {base} -> "
              f"{parallel(client)['forceDrainCount']} "
              f"(forceDrainReplay was raised for ExplosionBState::think to consume)")

        # ---- 3. CLEAR: disarming clears the wait and the raised escape flag --
        print("-- 3: disarming clears the wait and the escape flag (no leak) --")
        arm_wait(client, False)
        assert PI.wait_until(
            lambda: parallel(client)["coopPacingWait"] is False
            and parallel(client)["forceDrainReplay"] is False, 5), (
            f"disarming left a stale pacing/escape flag that would fire on a later "
            f"real shot: {parallel(client)}")
        after = parallel(client)["forceDrainCount"]
        time.sleep(2.0)
        assert parallel(client)["forceDrainCount"] == after, (
            f"the floor kept firing after the wait was cleared "
            f"({after} -> {parallel(client)['forceDrainCount']})")
        print(f"    cleared: coopPacingWait False, forceDrainReplay False, "
              f"count steady at {after}")

        # the drift tripwire must not have fired from any of this
        assert not TW.desync_seen(host) and not TW.desync_seen(client), \
            "the drift tripwire fired during the pacing-escape test"
        print("PASS: the auto-shot pacing wait is bounded - a wait that never gets its "
              "flip is force-drained instead of holding the receive gate forever")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  DBG {tag} parallel: {parallel(gc)}")
            except Exception as de:
                print(f"  DBG {tag} dump failed: {de}")
    finally:
        try:
            arm_wait(client, False)
        except Exception:
            pass
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
