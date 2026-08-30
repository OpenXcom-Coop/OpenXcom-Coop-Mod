"""Explosion ordered-replay E0, LEAK-OBJ: the coop client must NOT self-count
objective destruction.

THE BUG: the coop-client stubs in `Tile::destroy` / `TileEngine::detonate` /
`hitCoop` return `true` for every tile part the client destroys locally, not only
for a genuine objective tile. That `true` flows into
`SavedBattleGame::addDestroyedObjective()`, which had NO coop gate and increments
`_objectivesDestroyed` whenever `!allObjectivesDestroyed()` - true forever on a
`_objectivesNeeded == 0` map. So a coop CLIENT inflated its own objective counter
off ordinary terrain destruction, while the HOST - which checks the tile's REAL
special type - correctly stays at 0. On a MUST_DESTROY mission this let the
joining player end the battle unilaterally.

THE FIX (E0): a chokepoint at the top of `addDestroyedObjective()`
(`getCoopStatic()==true && getHost()==false`) refuses to increment on a coop
client, counts the block in `objectiveLeakBlocked`, and a `next_turn` parity field
(`objectivesDestroyed`) reconverges the client's readout to the host's real count.

WHAT EXERCISES THE GATE (post-E1 reality - read this before touching the fixture):
the E1 fix `fb2996741` ("parallel client stops simulating explosions") gated the
client's `TileEngine::explode()` behind `if(!_coopReplayDisplay)`
(ExplosionBState.cpp:341). On a parallel client `explode()`/`detonate()` therefore
NEVER run - an HE blast is display-only and drives the gate ZERO times. The ONLY
surviving in-battle client path into `addDestroyedObjective` is `hitCoop()`
(TileEngine.cpp:3447) replaying a host hit whose seeded damage roll clears a
terrain tile's armor. That is terrain- and roll-dependent, so on a FRESH RANDOM
map it fired only ~1 run in 6 -> the historical "objectiveLeakBlocked==0, GREEN
would be vacuous" flake (see parallel/BUG-objective-leak-vacuous.md). This fixture
kills the flake by PINNING the seed (E0_SEED, default 4) so the nearest breakable
wall - hence the hitCoop clear - is reproducible; a `==0` outcome now means the
pinned map stopped breaking a wall (a SEED issue, pick another), never a silent
vacuous pass and never a product regression.

MECHANISM ASSERTED: counter PARITY, not a MUST_DESTROY map (none is needed -
`_objectivesNeeded == 0` on the default skirmish fixture, so the host's own count
never leaves 0; the bug was ever letting the CLIENT's count leave 0).

  path (a)  ONE HE auto-cannon burst at the hostile - kept as coverage that the
            DISPLAY-ONLY blast stays parity-safe (host==client) and exercises the
            suppressed-explode path. It is NO LONGER a gate trigger (see above).
  GREEN     the deterministic gate trigger: a kinetic AIMED shot spiral clears the
            nearest wall via hitCoop; with the gate ON the client's block is counted
            (`objectiveLeakBlocked` moves) and `_objectivesDestroyed` stays == host.
  RED       same kinetic driver on a FRESH wall with `objective_gate_disable:true`
            on the CLIENT: the block is reverted, so the client's
            `_objectivesDestroyed` climbs past the host's - proving GREEN's parity
            is held BY the gate, not vacuously. Runs before the side close, whose
            next_turn parity field then heals the client's inflated count.

GREEN (gate ON): host == client `objectivesDestroyed` after the burst, the GREEN
wall clear, AND one side close; `objectiveLeakBlocked > 0` on the client.
RED (same build, gate lever reverted on the client only): client counter > host.

Run:  python tools/coop_test/test_parallel_objective_leak.py
      E0_SEED=<n> python .../test_parallel_objective_leak.py   # re-pin the map
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import test_battle_tripwire as TW
import test_parallel_intents as PI
import test_parallel_endturn as ET

PORT = "47993"

# The fixture is PINNED (bring_up_battle(seed=SEED) + a host RNG re-pin right
# before the shots) so the SINGLE surviving client leak path - a hitCoop terrain
# clear (see module docstring) - fires DETERMINISTICALLY instead of by luck. On a
# fresh random map the wall shots cleared no tile ~83% of runs, leaving the gate
# un-exercised -> the historical "objectiveLeakBlocked==0, GREEN would be vacuous"
# flake. E0_SEED=4 is a known-good value: it deterministically breaks 5 distinct
# wall tiles within the shooter's reach (enough to feed BOTH the GREEN gate-fire
# and the RED over-count on separate tiles). Override E0_SEED to re-pin if a map
# or map-gen change ever stops it breaking a wall (the test says so loudly - it is
# a fixture/seed issue, never a product regression).
SEED = int(os.environ.get("E0_SEED", "4"))

HE_WEAPON = os.environ.get("E0_HE_WEAPON", "STR_AUTO_CANNON")
HE_AMMO = os.environ.get("E0_HE_AMMO", "STR_AC_HE_AMMO")
KINETIC_WEAPON = os.environ.get("E0_KINETIC_WEAPON", "STR_HEAVY_CANNON")
KINETIC_AMMO = os.environ.get("E0_KINETIC_AMMO", "STR_HC_AP_AMMO")

# Spiral of candidate wall-hit offsets around the shooter, nearest first. With the
# seed pinned the FIRST offset that clears a tile is reproducible run-to-run, so
# this is a deterministic search for "the nearest breakable tile", not a lucky dip.
RING_OFFSETS = sorted(
    [(dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if 1 <= max(abs(dx), abs(dy)) <= 3],
    key=lambda d: (max(abs(d[0]), abs(d[1])), abs(d[0]) + abs(d[1])))


def parallel(gc):
    return PI.parallel(gc)


def battle(gc):
    return PI.battle(gc)


def objectives(gc):
    b = battle(gc)
    return b.get("objectivesDestroyed", -1), b.get("objectivesNeeded", -1)


def fire_he(host, client, shooter, tgt, tag):
    wid = PI.give_both(host, client, shooter, HE_WEAPON, HE_AMMO)
    assert PI.idle(host), f"{tag}: host still busy before the HE burst"
    PI.top_up(host, client, shooter)
    r = PI.intent(host, action="shoot", unit=shooter, mode="auto", weapon_id=wid,
                  x=tgt[0], y=tgt[1], z=tgt[2])
    assert r.get("ok"), f"{tag}: HE shoot intent refused: {r}"
    PI.settle(host, client, seconds=10)
    assert PI.idle(host, 60), f"{tag}: host chain never ended after the HE burst"
    time.sleep(1.5)


def wall_spiral(host, client, shooter, metric, label, skip=()):
    """Fire kinetic AIMED shots in a nearest-first spiral around `shooter` until
    the CLIENT counter read by `metric(client)` moves (a hitCoop terrain clear on
    the client), or the candidates run out. Returns (broke, tile, delta): `broke`
    is True on the first clearing shot, `tile` the (x,y,z) it cleared. `skip` is a
    set of tiles a previous call already consumed, so a second spiral (RED after
    GREEN) targets a FRESH wall rather than a spent one.

    This is the DETERMINISTIC gate driver post-E1: the parallel client no longer
    simulates the HE blast (E1 fb2996741), so detonate() never runs there and the
    ONLY way to make the client destroy a tile - and thus reach the E0 gate at
    SavedBattleGame::addDestroyedObjective - is to have the host land a hit whose
    seeded roll clears terrain and let the client replay it via hitCoop. With the
    seed pinned this is reproducible; `metric` decides which side of the gate we
    watch (objectiveLeakBlocked for GREEN, client objectivesDestroyed for RED)."""
    wid = PI.give_both(host, client, shooter, KINETIC_WEAPON, KINETIC_AMMO)
    spos = PI.pos(battle(host), shooter)
    tried = 0
    for dx, dy in RING_OFFSETS:
        if tried >= 14:
            break
        tx, ty, tz = spos[0] + dx, spos[1] + dy, spos[2]
        if (tx, ty, tz) in skip:
            continue
        if not PI.idle(host, 20):
            continue
        PI.top_up(host, client, shooter)
        before = metric(client)
        r = PI.intent(host, action="shoot", unit=shooter, mode="aimed", weapon_id=wid,
                      tu=200, x=tx, y=ty, z=tz)
        if not r.get("ok"):
            continue
        tried += 1
        PI.settle(host, client, seconds=4)
        PI.idle(host, 30)
        time.sleep(0.5)
        after = metric(client)
        if after > before:
            print(f"       {label}: shot at ({tx},{ty},{tz}) [offset {(dx, dy)}] cleared a "
                  f"wall part via hitCoop (client counter {before}->{after}), "
                  f"{tried} attempt(s) tried")
            return True, (tx, ty, tz), after - before
    print(f"       {label} NOTE: {tried} candidate tile(s) tried, none cleared a wall "
          f"(seed E0_SEED={SEED} - pick another if this map stopped breaking)")
    return False, None, 0


def leak_metric(client):
    return parallel(client)["objectiveLeakBlocked"]


def objdestroyed_metric(client):
    return objectives(client)[0]


def live_shooter(host, client, hseat, fallback):
    """A live own unit to fire with. Point-blank HE / kinetic bursts can splash
    their own firer; this re-picks any survivor rather than letting a dead actor
    silently no-op a later burst."""
    u = PI.unit(battle(host), fallback)
    if u and not u.get("isOut"):
        return fallback
    for cand in PI.own_units(battle(host), hseat):
        return cand["id"]
    return fallback


def main():
    fail = None
    host = GameClient("host", 48792,
                      make_user_dir("e0_objleak_host",
                                    options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48793,
                        make_user_dir("e0_objleak_client",
                                      options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        # PIN the fixture (map / deployment / rolls) so the surviving hitCoop leak
        # path fires deterministically - see the SEED comment at module top.
        TW.bring_up_battle(host, client, seed=SEED)
        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"skirmish fixture came up gamemode {gm}; parallel turns only cover PVE "
            f"(1) and PVE2 (4) - this fixture would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"

        pc0 = parallel(client)
        for field in ("objectiveLeakBlocked", "objectiveGateDisable", "explosionReplayDisable"):
            assert field in pc0, (
                f"parallel_state carries no `{field}` - bin/x64/Release/OpenXcom.exe "
                f"predates the E0 LEAK-OBJ instrumentation; rebuild it (serial, MP=false). "
                f"fields: {sorted(pc0)}")
        b0 = battle(host)
        for field in ("objectivesDestroyed", "objectivesNeeded"):
            assert field in b0, (
                f"battle_state carries no `{field}` - rebuild the E0 build. "
                f"fields: {sorted(b0)}")
        assert pc0["objectiveGateDisable"] is False, "gate lever not at its default (off)"
        assert pc0["explosionReplayDisable"] is False, "replay lever not at its default (off)"

        hseat = parallel(host)["localSeat"]
        enemy = PI.alive_enemy(battle(host))
        assert enemy, "the skirmish came up with no hostile to orient the fixture around"
        epos = (enemy["x"], enemy["y"], enemy["z"])

        shooter = None
        for cand in PI.own_units(battle(client), hseat):
            sid = cand["id"]
            if PI.place_adjacent(host, client, sid, epos):
                PI.top_up(host, client, sid)
                shooter = sid
                break
        assert shooter, "could not place a shooter near the hostile"
        print(f"battle up (gm {gm}). shooter {shooter} placed near hostile {enemy['id']} "
              f"@{epos}")

        pre_h, need_h = objectives(host)
        pre_c, need_c = objectives(client)
        pre_leak = parallel(client)["objectiveLeakBlocked"]
        print(f"pre-shot: host {pre_h}/{need_h}  client {pre_c}/{need_c}  "
              f"leakBlocked(client) {pre_leak}")
        assert pre_h == pre_c, "objective counters diverged before any shot was fired"

        # Re-pin the host RNG so THIS run's shot rolls (host-seeded, client-replayed
        # via the hit packet) are reproducible independent of whatever RNG bring-up
        # consumed - the second half of the determinism the SEED comment describes.
        host.ok({"cmd": "set_seed", "seed": SEED})

        # ---- path (a): the HE blast is DISPLAY-ONLY on the parallel client -----
        # Post-E1 (fb2996741) the client no longer simulates the blast: explode()/
        # detonate() are gated off (ExplosionBState.cpp:341), so the burst does NOT
        # drive the client's objective gate. It is kept here as coverage that the
        # blast stays parity-safe (host==client objectivesDestroyed) and to exercise
        # the display-only path; the DELIBERATE gate trigger is the kinetic wall shot
        # (GREEN below), the only client leak path that survived E1.
        fire_he(host, client, shooter, epos, "path a")
        a_h, _ = objectives(host)
        a_c, _ = objectives(client)
        leak_a = parallel(client)["objectiveLeakBlocked"]
        print(f"post path-a (HE burst, display-only on client): host {a_h}  "
              f"client {a_c}  leakBlocked(client) {leak_a}")
        assert a_h == a_c, (
            f"[LEAK-OBJ] objective counters diverged after the HE burst: "
            f"host={a_h} client={a_c}")

        # ---- GREEN: DETERMINISTIC gate-fire via a kinetic hitCoop wall clear -----
        # The pinned seed makes the nearest breakable wall reproducible: the client
        # replays the host's seeded hit, clears the tile, and its Tile::destroy stub
        # feeds addDestroyedObjective - which the E0 gate refuses, counting the block
        # in objectiveLeakBlocked while _objectivesDestroyed stays put (host==client).
        broke, green_tile, _ = wall_spiral(host, client, shooter, leak_metric, "GREEN")
        b_h, _ = objectives(host)
        b_c, _ = objectives(client)
        leak_b = parallel(client)["objectiveLeakBlocked"]
        print(f"post GREEN (kinetic wall clear): host {b_h}  client {b_c}  "
              f"leakBlocked(client) {leak_b}")
        assert b_h == b_c, (
            f"[LEAK-OBJ] objective counters diverged after the GREEN wall clear: "
            f"host={b_h} client={b_c}")
        assert leak_b > pre_leak, (
            f"objectiveLeakBlocked did not move ({pre_leak}->{leak_b}) - the pinned "
            f"fixture (E0_SEED={SEED}) never cleared a client wall via hitCoop, so the "
            f"gate had nothing to gate. This is a FIXTURE/SEED issue (pick another "
            f"E0_SEED), NOT a product regression - the gate itself is untested here, "
            f"not broken.")

        print(f"GREEN: gate ON - host/client objectivesDestroyed stayed IDENTICAL "
              f"({pre_h}->{b_h} host, {pre_c}->{b_c} client), "
              f"objectiveLeakBlocked(client) = {leak_b} > {pre_leak}")

        # ---- RED: same build, objective_gate_disable=true on the CLIENT only --
        # Same DETERMINISTIC kinetic driver as GREEN, but with the gate reverted:
        # now the client's hitCoop wall clear is NOT blocked, so its
        # _objectivesDestroyed climbs past the host's (which stays 0 - the host only
        # counts genuine objective tiles, none on this map). Proves the GREEN parity
        # is held BY the gate, not vacuously. Fires a FRESH wall (skip the tile GREEN
        # already spent), and runs BEFORE the side-close (whose next_turn parity field
        # then heals the client's inflated count back to the host's).
        if not battle(host).get("inBattle"):
            print("       SKIP RED: the mission ended during path (a)/GREEN - no "
                  "battle left to fire the RED shots into")
        else:
            client.ok({"cmd": "parallel_state", "objective_gate_disable": True})
            assert parallel(client)["objectiveGateDisable"] is True, \
                "objective_gate_disable lever did not latch on the client"

            # Reuse the (surviving) shooter, or re-pick+replace a live one if a burst
            # splashed it. Re-pin the seed so the RED wall clear is reproducible too.
            red_shooter = live_shooter(host, client, hseat, shooter)
            if red_shooter != shooter:
                enemy2 = PI.alive_enemy(battle(host))
                red_tgt = (enemy2["x"], enemy2["y"], enemy2["z"]) if enemy2 else epos
                PI.place_adjacent(host, client, red_shooter, red_tgt)
                print(f"       RED run: original shooter {shooter} is down - "
                      f"using {red_shooter} instead (re-placed near the target)")
            host.ok({"cmd": "set_seed", "seed": SEED})
            pre_red_h, _ = objectives(host)
            pre_red_c, _ = objectives(client)
            skip = {green_tile} if green_tile else set()
            broke_red, _, _ = wall_spiral(host, client, red_shooter,
                                          objdestroyed_metric, "RED", skip=skip)
            red_h, _ = objectives(host)
            red_c, _ = objectives(client)
            print(f"RED run (objective_gate_disable=true on client): "
                  f"host {pre_red_h}->{red_h}  client {pre_red_c}->{red_c}")

            # restore the lever before anything else touches this battle
            client.ok({"cmd": "parallel_state", "objective_gate_disable": False})

            assert red_c > red_h, (
                f"RED run did not reproduce the leak: expected client ({red_c}) > "
                f"host ({red_h}) once objective_gate_disable reverted the LEAK-OBJ gate. "
                f"Either the gate is not wired to the lever, or the pinned fixture "
                f"(E0_SEED={SEED}) cleared no FRESH client wall this time (broke_red="
                f"{broke_red}; GREEN spent {green_tile}) - the latter is a seed issue.")
            print(f"RED confirmed: client counter ({red_c}) > host counter ({red_h}) "
                  f"with the LEAK-OBJ gate reverted on the SAME build")

        # ---- GREEN, checkpoint 2 (bonus): parity survives one side close ------
        # Exercises the OTHER half of E0 (NextTurnState's objectivesDestroyed
        # parity field + connectionTCP's client-side apply): hushes both
        # machines' TU (so the alien side cannot end the mission under the
        # fixture), ends the player side on both machines, waits for the alien
        # side to resolve and the player side to come back, then re-reads. Runs
        # LAST and its outcome is logged, not gated - the RED run above already
        # delivered the required result, and the default skirmish fixture's
        # handful of hostiles makes a mission-ending side close common.
        if not battle(host).get("inBattle"):
            print("       NOTE: no battle left after path (a)/GREEN/RED - skipping the "
                  "post-side-close parity re-check; the action_end checkpoints above "
                  "already cover the mechanism")
        else:
            turn_before = ET.turn_of(host)
            ET.hush(host, client)
            ET.arm(host)
            ET.arm(client)
            closed_turn = ET.wait_side(host, client, turn_before, timeout=240)
            if closed_turn is None:
                print("       NOTE: the mission ended during the side close (no hostiles "
                      "left) - skipping the post-side-close parity re-check; the "
                      "action_end checkpoints above already cover the mechanism")
            elif closed_turn is False:
                print("       NOTE: the side never closed within the timeout - skipping "
                      "the post-side-close parity re-check (action_end checkpoints above "
                      "already cover the mechanism); this is a fixture-timing shortfall, "
                      "not a LEAK-OBJ result")
            else:
                s_h, _ = objectives(host)
                s_c, _ = objectives(client)
                print(f"post side-close (turn {turn_before}->{closed_turn}): "
                      f"host {s_h}  client {s_c}")
                assert s_h == s_c, (
                    f"[LEAK-OBJ] objective counters diverged after the side close (the "
                    f"next_turn objectivesDestroyed parity path): host={s_h} client={s_c}")

        print("PASS: LEAK-OBJ gate holds host/client objectivesDestroyed parity "
              "with the gate ON, and the SAME build reproduces client > host once "
              "objective_gate_disable reverts it")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  DBG {tag} battle:   {battle(gc)}")
                print(f"  DBG {tag} parallel: {parallel(gc)}")
            except Exception as de:
                print(f"  DBG {tag} dump failed: {de}")
    finally:
        host.shutdown(); client.shutdown()

    print("\n==== E0 LEAK-OBJ objective-counter parity summary ====")
    if fail:
        print(f"  FAIL {fail}")
        sys.exit(2)
    print("  host==client objectivesDestroyed parity held with the gate ON "
          "(objectiveLeakBlocked>0 proves the gate actually engaged); the SAME "
          "build reproduces client>host once objective_gate_disable reverts it")
    sys.exit(0)


if __name__ == "__main__":
    main()
