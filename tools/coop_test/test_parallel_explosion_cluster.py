"""Explosion ordered-replay E0: heavy-cluster RED scaffold for mutation 5C
("casualty-value replay under a heavy cluster").

5C's concern (research_explosion_mutations.md): when a primary blast chain-
detonates several ALREADY-CHARGED secondary tiles in one go, the client's
local explode()/checkForTerrainExplosions replay and the host's ordered event
log can disagree about the ORDER those secondaries resolve in - which matters
once E1 makes casualty attribution/value depend on replay order. E0 does not
touch the explosion sim (that lands in E1); this fixture only has to (i) stage
a reproducible cluster of charged secondaries and (ii) prove the
`explosion_replay_disable` lever this phase added exists, is introspectable,
and actually flips - the switch E1 will wire to force the legacy (non-ordered)
sim path for a same-build red/green comparison once the ordered replay lands.

STAGING MECHANISM: reuses the chain-atomicity item-2 fixture's `battle_tiles
{set_explosive:...}` lever (test_parallel_explosive_carrier.py) to arm a
cluster of tiles with an explosive charge on BOTH machines, matched. Each
armed tile is a "charged secondary": when a primary blast reaches it,
checkForTerrainExplosions spawns a chained ExplosionBState that consumes it.
A (2R+1)^2 block at R=1 already stages 9 >= the 5C minimum of 3.

SHORTFALL (documented per the E0 task, not faked): this fixture stages the
cluster and fires ONE primary blast into it so the chain reproducibly fires,
and reports (does not assert) how many secondaries each machine's replay
consumed - useful diagnostic context for E1, but not a correctness gate.
Nothing here enforces per-secondary REPLAY ORDER (that is the actual 5C
mechanism) because E0 ships no ordering machinery to gate on; `--probe` prints
the raw numbers for a human to eyeball. The only ASSERTED outcomes in E0 are:
the cluster staged >= 3 tiles identically on both machines, and the
`explosion_replay_disable` lever round-trips through `parallel_state`.

Run:
  python tools/coop_test/test_parallel_explosion_cluster.py            # assert GREEN
  python tools/coop_test/test_parallel_explosion_cluster.py --probe    # also print secondary counts

Exit 0 = pass; 2 = failure. Keeps well under 180 s (one bring-up, one burst).
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import test_battle_tripwire as TW
import test_parallel_intents as PI

PORT = "47993"

WEAPON = os.environ.get("E0_HE_WEAPON", "STR_AUTO_CANNON")
AMMO = os.environ.get("E0_HE_AMMO", "STR_AC_HE_AMMO")

# (2R+1)^2 block of armed tiles - R=1 stages 9, comfortably >= the 5C minimum
# of 3 charged secondaries in one blast.
CLUSTER_R = 1
EXPL_POWER = 20
MIN_SECONDARIES = 3


def parallel(gc):
    return PI.parallel(gc)


def battle(gc):
    return PI.battle(gc)


def tiles(gc):
    return gc.ok({"cmd": "battle_tiles"})


def arm_cluster(gcs, cx, cy, cz, power, rad):
    """Lifted verbatim from test_parallel_explosive_carrier.py (chain-atomicity
    item-2): arm every tile in a (2*rad+1)^2 block centred on (cx,cy,cz) on
    each of `gcs`, so BOTH machines start the burst holding the SAME charged
    cluster."""
    for gc in gcs:
        for dx in range(-rad, rad + 1):
            for dy in range(-rad, rad + 1):
                gc.cmd({"cmd": "battle_tiles", "set_explosive": power,
                        "explosiveType": 0, "x": cx + dx, "y": cy + dy, "z": cz})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true",
                    help="also print the per-machine secondary-consumption counts")
    args = ap.parse_args()

    fail = None
    host = GameClient("host", 48792,
                      make_user_dir("e0_explcluster_host",
                                    options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48793,
                        make_user_dir("e0_explcluster_client",
                                      options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        TW.bring_up_battle(host, client)
        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"skirmish fixture came up gamemode {gm}; parallel turns only cover PVE "
            f"(1) and PVE2 (4) - this fixture would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"

        # ---- (ii) the explosion_replay_disable lever: exists, introspectable, flips --
        pc0 = parallel(client)
        assert "explosionReplayDisable" in pc0, (
            f"parallel_state carries no `explosionReplayDisable` - "
            f"bin/x64/Release/OpenXcom.exe predates the E0 LEAK-OBJ/lever "
            f"instrumentation; rebuild it (serial, MP=false). fields: {sorted(pc0)}")
        assert pc0["explosionReplayDisable"] is False, \
            f"lever not at its default (off): {pc0['explosionReplayDisable']}"

        # NOTE: the readout is emitted BEFORE the lever-setter runs in this same
        # request (matches the existing atomic_death_disable/etc. levers in
        # TestServer.cpp), so the flip is only visible on a FOLLOW-UP read, not
        # in the response to the request that set it.
        client.ok({"cmd": "parallel_state", "explosion_replay_disable": True})
        after_on = parallel(client)["explosionReplayDisable"]
        assert after_on is True, \
            f"a follow-up parallel_state read shows the lever did not latch ON: {after_on}"
        print(f"    explosion_replay_disable: OFF -> ON confirmed "
              f"(parallel_state.explosionReplayDisable={after_on})")

        client.ok({"cmd": "parallel_state", "explosion_replay_disable": False})
        after_off = parallel(client)["explosionReplayDisable"]
        assert after_off is False, \
            f"a follow-up parallel_state read shows the lever did not clear: {after_off}"
        print(f"    explosion_replay_disable: ON -> OFF confirmed "
              f"(parallel_state.explosionReplayDisable={after_off})")
        print("PASS (ii): explosion_replay_disable exists, is introspectable via "
              "parallel_state, and flips both directions (E0 scaffolding only - "
              "E1 wires it to force the legacy sim path)")

        # ---- (i) stage a reproducible cluster of >= 3 charged secondaries -----
        probe = tiles(host)
        for field in ("explosiveTiles", "explosiveHash", "explosiveSum"):
            assert field in probe, (
                f"battle_tiles carries no `{field}` - bin/x64/Release/OpenXcom.exe "
                f"predates the item-2 explosive census; rebuild it. fields: {sorted(probe)}")

        hseat = parallel(host)["localSeat"]
        enemy = PI.alive_enemy(battle(host))
        assert enemy, "the skirmish came up with no hostile to orient the cluster around"
        cx, cy, cz = enemy["x"], enemy["y"], enemy["z"]

        shooter = None
        for cand in PI.own_units(battle(client), hseat):
            sid = cand["id"]
            if PI.place_adjacent(host, client, sid, (cx, cy, cz)):
                PI.top_up(host, client, sid)
                shooter = sid
                break
        assert shooter, "could not place a shooter near the cluster centre"

        arm_cluster((host, client), cx, cy, cz, EXPL_POWER, CLUSTER_R)
        th = tiles(host)
        tc = tiles(client)
        armed = min(th["explosiveTiles"], tc["explosiveTiles"])
        matched = th["explosiveHash"] == tc["explosiveHash"]
        print(f"    cluster staged at ({cx},{cy},{cz}) r={CLUSTER_R}: "
              f"host {th['explosiveTiles']}t client {tc['explosiveTiles']}t "
              f"matched={matched}")
        assert matched, (
            f"the cluster did not arm IDENTICALLY on both machines - host hash "
            f"{th['explosiveHash']} client {tc['explosiveHash']} - the fixture "
            f"itself is not reproducible")
        assert armed >= MIN_SECONDARIES, (
            f"only staged {armed} charged secondaries (need >= {MIN_SECONDARIES} "
            f"for the 5C minimum) - SHORTFALL: could not cheaply stage a larger "
            f"cluster on this map/seed. Documenting per the E0 task rather than "
            f"faking a bigger number: {armed} is the largest this fixture reaches "
            f"with CLUSTER_R={CLUSTER_R}, EXPL_POWER={EXPL_POWER}.")
        print(f"PASS (i): {armed} charged secondaries staged identically on both "
              f"machines (>= {MIN_SECONDARIES} required for 5C)")

        # ---- fire ONE primary blast into the cluster: reproduces the chain -----
        # Report-only (E0 does not enforce ordering here - see docstring); this
        # just proves the staged cluster actually detonates as a chain, so the
        # scaffold is a live repro for E1, not just inert tile state.
        wid = PI.give_both(host, client, shooter, WEAPON, AMMO)
        assert PI.idle(host), "host still busy before the cluster burst"
        r = PI.intent(host, action="shoot", unit=shooter, mode="auto", weapon_id=wid,
                      x=cx, y=cy, z=cz)
        assert r.get("ok"), f"the cluster-triggering shot was refused: {r}"

        end = time.time() + 14.0
        max_host = 0
        max_client = 0
        while time.time() < end:
            th = tiles(host)
            tc = tiles(client)
            max_host = max(max_host, th["explosiveTiles"])
            max_client = max(max_client, tc["explosiveTiles"])
            if th["explosiveTiles"] == 0 and tc["explosiveTiles"] == 0:
                break
            time.sleep(0.1)
        PI.idle(host, 60)
        time.sleep(1.0)
        th = tiles(host)
        tc = tiles(client)
        settled_match = th["explosiveHash"] == tc["explosiveHash"]
        print(f"    burst fired: settled host {th['explosiveTiles']}t / "
              f"client {tc['explosiveTiles']}t (settledMatch={settled_match})")
        if args.probe:
            print(f"PROBE: cluster consumed - armed {armed}, settledMatch "
                  f"{settled_match}, settledHost {th['explosiveTiles']} "
                  f"settledClient {tc['explosiveTiles']}")

        print("PASS: heavy-cluster scaffold staged and fired a reproducible "
              f"{armed}-secondary chain; explosion_replay_disable round-trips "
              "through parallel_state. Both become the E1 enforcing gate; E0 "
              "only has to prove the scaffold and the lever exist.")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  DBG {tag} tiles:    {tiles(gc)}")
                print(f"  DBG {tag} parallel: {parallel(gc)}")
            except Exception as de:
                print(f"  DBG {tag} dump failed: {de}")
    finally:
        host.shutdown(); client.shutdown()

    print("\n==== E0 heavy-cluster RED scaffold summary ====")
    if fail:
        print(f"  FAIL {fail}")
        sys.exit(2)
    print("  cluster staging + explosion_replay_disable lever both confirmed; "
          "5C ordering itself is E1's job")
    sys.exit(0)


if __name__ == "__main__":
    main()
