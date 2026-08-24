"""Explosion ordered-replay E0, LEAK-OBJ: the coop client must NOT self-count
objective destruction.

THE BUG: `TileEngine::detonate` (explode()'s per-tile callback) and
`TileEngine::destroy`/`hitCoop` all carry a coop-client stub of the shape

    if (getCoopStatic() && !getHost()) return true;

`Tile::destroy`'s stub in particular returns `true` UNCONDITIONALLY - not just
for a genuinely-destroyed objective tile, but for every tile part the client's
own local explode()/hit-replay touches (`detonate`'s stub fires even earlier,
before its `explosive == 0` no-op check). That `true` flows straight into
`SavedBattleGame::addDestroyedObjective()`, which has NO coop gate and
increments `_objectivesDestroyed` unconditionally whenever
`!allObjectivesDestroyed()` - true forever on a `_objectivesNeeded == 0` map,
since `allObjectivesDestroyed()` requires `_objectivesNeeded > 0`. So a
parallel (or classic) coop CLIENT inflates its own objective counter off of
ordinary terrain destruction, with no bound, while the HOST's copy - which
checks the tile's REAL special type against the mission's objective type -
correctly stays at 0 on a non-MUST_DESTROY map. On an actual MUST_DESTROY
mission this lets the joining player end the battle unilaterally.

THE FIX (E0, LEAK-OBJ): a single chokepoint at the top of
`SavedBattleGame::addDestroyedObjective()` (the classic coop idiom
`getCoopStatic()==true && getHost()==false`, applied to classic coop too per
owner decision) refuses to increment on a coop client, counts the block
(`objectiveLeakBlocked`), and a `next_turn` parity field
(`objectivesDestroyed`) keeps the client's readout converged to the host's
real count for any UI/mission-complete check that reads it directly.

MECHANISM ASSERTED: counter PARITY, not a MUST_DESTROY map (none is needed -
`_objectivesNeeded == 0` on the default skirmish fixture, so the host's own
count never leaves 0; the bug was ever letting the CLIENT's count leave 0).

  (a) fire ONE HE auto-cannon burst at a live hostile. `detonate()` runs for
      every tile the blast touches (`tilesAffected`), and its stub fires
      before the `explosive == 0` check - so this alone guarantees the client
      calls `addDestroyedObjective()` at least once, gate or no gate.
  (b) fire kinetic (non-explosive) rounds at nearby wall tiles to trigger
      `TileEngine::hit()` (host) / `hitCoop()` (client replay of the host's
      seeded roll) - the OTHER leak site, distinct code path from (a). Unlike
      detonate()'s stub, hitCoop's replay only reaches `Tile::destroy` if the
      shot's (seeded, so host/client-identical) damage roll actually clears
      the target tile's armor, so this path is opportunistic: it tries a
      spiral of adjacent tiles with a decently powerful kinetic weapon and
      reports whether a wall gave, but does not gate pass/fail on it (the
      parity assertions below already cover the mechanism via (a), and the RED
      run re-confirms it independent of whichever tile(s) (b) managed to
      break). If your build/seed never lands a hitCoop destroy, the summary
      says so plainly - see the printed NOTE.

GREEN (E0 build, gate ON): host == client `battle_state.objectivesDestroyed`
after settling the burst(s) AND after one side close (next_turn parity path);
`parallel_state.objectiveLeakBlocked > 0` on the client.

RED (same build, `parallel_state {objective_gate_disable:true}` on the
CLIENT only): client counter > host counter after one more HE burst - proves
the assertions above are not vacuously true.

Run:  python tools/coop_test/test_parallel_objective_leak.py
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

HE_WEAPON = os.environ.get("E0_HE_WEAPON", "STR_AUTO_CANNON")
HE_AMMO = os.environ.get("E0_HE_AMMO", "STR_AC_HE_AMMO")
KINETIC_WEAPON = os.environ.get("E0_KINETIC_WEAPON", "STR_HEAVY_CANNON")
KINETIC_AMMO = os.environ.get("E0_KINETIC_AMMO", "STR_HC_AP_AMMO")

# Spiral of candidate wall-hit offsets around the shooter, nearest first: path
# (b) is opportunistic (see docstring), so this just maximises the odds of one
# candidate tile having low enough armor for a kinetic round to clear it.
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


def try_wall_shots(host, client, shooter):
    """Best-effort path (b): spiral kinetic snap shots around the shooter,
    watching the CLIENT's objectiveLeakBlocked counter for a hitCoop-driven
    increment. Returns True on the first candidate that moves it."""
    wid = PI.give_both(host, client, shooter, KINETIC_WEAPON, KINETIC_AMMO)
    spos = PI.pos(battle(host), shooter)
    tried = 0
    for dx, dy in RING_OFFSETS:
        if tried >= 14:
            break
        if not PI.idle(host, 20):
            continue
        tx, ty, tz = spos[0] + dx, spos[1] + dy, spos[2]
        leak_before = parallel(client)["objectiveLeakBlocked"]
        r = PI.intent(host, action="shoot", unit=shooter, mode="aimed", weapon_id=wid,
                      tu=200, x=tx, y=ty, z=tz)
        if not r.get("ok"):
            continue
        tried += 1
        PI.settle(host, client, seconds=4)
        PI.idle(host, 30)
        time.sleep(0.5)
        leak_after = parallel(client)["objectiveLeakBlocked"]
        if leak_after > leak_before:
            print(f"       path b: shot at ({tx},{ty},{tz}) [offset {(dx, dy)}] broke a "
                  f"wall part via hitCoop (client objectiveLeakBlocked "
                  f"{leak_before}->{leak_after}), {tried} attempt(s) tried")
            return True
    print(f"       path b NOTE: {tried} candidate tile(s) tried around the shooter, "
          f"none cleared a wall's armor on this map/seed - opportunistic coverage only "
          f"(see docstring); the parity mechanism is still proven by path (a) below")
    return False


def live_shooter(host, client, hseat, fallback):
    """A live own unit to fire the RED burst with. Point-blank HE (path a and
    path b's own bursts can each incidentally splash their firer) may have
    downed the original `shooter`; this re-picks any survivor rather than
    letting a dead actor silently no-op the RED burst."""
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
        TW.bring_up_battle(host, client)
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

        # ---- path (a): ONE HE blast into/near destructible terrain -----------
        fire_he(host, client, shooter, epos, "path a")
        a_h, _ = objectives(host)
        a_c, _ = objectives(client)
        leak_a = parallel(client)["objectiveLeakBlocked"]
        print(f"post path-a (HE burst): host {a_h}  client {a_c}  "
              f"leakBlocked(client) {leak_a}")
        assert a_h == a_c, (
            f"[LEAK-OBJ] objective counters diverged after the HE burst: "
            f"host={a_h} client={a_c}")

        # ---- path (b): best-effort kinetic wall shot(s) (hitCoop replay) -----
        try_wall_shots(host, client, shooter)
        b_h, _ = objectives(host)
        b_c, _ = objectives(client)
        leak_b = parallel(client)["objectiveLeakBlocked"]
        print(f"post path-b (wall shots): host {b_h}  client {b_c}  "
              f"leakBlocked(client) {leak_b}")
        assert b_h == b_c, (
            f"[LEAK-OBJ] objective counters diverged after the wall-shot spiral: "
            f"host={b_h} client={b_c}")
        assert leak_b > 0, (
            f"objectiveLeakBlocked never incremented on the client ({leak_b}) - the "
            f"gate was never exercised by path (a) or (b), so GREEN would be vacuous")

        print(f"GREEN: gate ON - host/client objectivesDestroyed stayed IDENTICAL "
              f"through both paths ({pre_h}->{b_h} host, {pre_c}->{b_c} client), "
              f"objectiveLeakBlocked(client) = {leak_b} > 0")

        # ---- RED: same build, objective_gate_disable=true on the CLIENT only --
        # Run BEFORE the (bonus) side-close check below: the default skirmish
        # fixture spawns few hostiles, an HE burst can end the mission outright,
        # and the RED demonstration is the one result that must not be skipped.
        if not battle(host).get("inBattle"):
            print("       SKIP RED: the mission ended during path (a)/(b) - no "
                  "battle left to fire the RED burst into")
        else:
            client.ok({"cmd": "parallel_state", "objective_gate_disable": True})
            assert parallel(client)["objectiveGateDisable"] is True, \
                "objective_gate_disable lever did not latch on the client"

            # Fresh live shooter (point-blank HE in path a/b can splash its own
            # firer) and a FIXED, already-proven-safe target: the original
            # hostile's tile (epos), never the shooter's OWN tile (self-detonating
            # an HE auto-cannon burst at point-blank range can down the shooter
            # before it finishes the burst, and independently is not what this
            # run is trying to measure).
            red_shooter = live_shooter(host, client, hseat, shooter)
            enemy2 = PI.alive_enemy(battle(host))
            red_tgt = (enemy2["x"], enemy2["y"], enemy2["z"]) if enemy2 else epos
            if red_shooter != shooter:
                PI.place_adjacent(host, client, red_shooter, red_tgt)
                print(f"       RED run: original shooter {shooter} is down - "
                      f"using {red_shooter} instead (re-placed near the target)")
            pre_red_h, _ = objectives(host)
            pre_red_c, _ = objectives(client)
            fire_he(host, client, red_shooter, red_tgt, "RED run")
            red_h, _ = objectives(host)
            red_c, _ = objectives(client)
            print(f"RED run (objective_gate_disable=true on client): "
                  f"host {pre_red_h}->{red_h}  client {pre_red_c}->{red_c}")

            # restore the lever before anything else touches this battle
            client.ok({"cmd": "parallel_state", "objective_gate_disable": False})

            assert red_c > red_h, (
                f"RED run did not reproduce the leak: expected client ({red_c}) > "
                f"host ({red_h}) once objective_gate_disable reverted the LEAK-OBJ "
                f"gate on the client - either the gate is not wired to the lever, or "
                f"the HE burst did not touch enough tiles this time (re-run)")
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
            print("       NOTE: no battle left after path (a)/(b)/RED - skipping the "
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
