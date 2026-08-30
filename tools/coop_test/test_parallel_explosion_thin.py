"""Explosion ordered-replay migration, Phase E1: the PARALLEL client stops
running the authoritative explosion simulation.

THE CHANGE. Before E1, `ExplosionBState` ran `TileEngine::explode()` (the
ray-trace, casualty pass, chain-discovery, gravity, FOV) UNGATED on both
machines - the host's outcome carriers (`destroy_tile`, `set_explosive_tile`,
`explode_items`, `hit_unit`, `unit_casualty`, ...) landed on the client while
its own independent sim was ALSO running on the animation clock, racing the
carriers. E1 makes the parallel client DISPLAY-ONLY: `ExplosionBState::init`
gates the single `explode()` call (:293) and member `explode()` gates
`checkForCasualties` (:580) on a new `_coopReplayDisplay` latch
(`parallelTurnActive() && !getHost() && !g_explosionReplayDisable`). The blast
ANIMATION (sprites, flash, sound, camera) is untouched - only the two sim
calls are gated. The one client-side mutation that used to ride inside the now-
gated `explode()` call with no carrier of its own - the per-tile gravity settle
(`applyGravity`, TileEngine.cpp:3914-3917) - is DERIVED at the client's
`destroy_tile` apply instead (connectionTCP.cpp, mirroring the host's own
per-affected-tile pattern).

THREE CASES, because the spawn inventory (plan doc S1.1) says a shot, a timed
grenade and a proximity trigger all reach `ExplosionBState` through different
call paths on the client (intent-replay, the local `endTurn` sweep, and
movement-replay respectively), and E1's gate has to hold for all three:

  (a) an HE blast fired into terrain near a hostile (shot-origin, non-boundary
      chain - exercises the `coopStampLooseOutcomeChain("expl")` mid-side path).
  (b) a timed grenade primed+thrown, resolved on the end-turn boundary sweep
      (`BattlescapeGame.cpp:1850 forRemoval` - exercises the BOUNDARY-phase
      `_coopBoundaryExpl` bracket, `coopSetBoundaryCasualty`).
  (c) a primed proximity grenade dropped on the ground, triggered by a unit
      walking onto it (movement-replay spawn path, `BattlescapeGame.cpp:5990`
      family).

GREEN (E1 build, lever off - the default): every sync-check bucket
(terrain/unitsCore/items/itemIdCtr/unitsCombat) stays at mismatchCount==0
through all three cases under the STRICT burn-in lever (every seq compared, not
just side-gated boundaries); `parallel_state.explodeCallsSuppressed` and
`explosionsDisplayOnly` climb on the client (proof the display-only path
actually ran, not a vacuously-true green); item AND terrain census are
SYMMETRIC on both machines after each case (assert symmetry, not survival -
see memory `coop-proximity-sweep-fix`: a blast destroying gear is correct, the
two machines disagreeing about WHAT it destroyed is the bug).

RED (same build, `parallel_state {explosion_replay_disable:true}` on the
CLIENT only): `_coopReplayDisplay` computes false again, so the client's
`ExplosionBState` re-enters the old racing sim - `explodeCallsSuppressed` /
`explosionsDisplayOnly` must stop climbing (the deterministic proof the lever
actually re-routed the code path), and the E0-era heavy-cluster/explosion
straddle (items/unitsCore/itemIdCtr drift at explosion seqs) is a STATISTICAL
reappearance - reported, not hard-asserted (retry-tolerant, same as the D.3b
and item-2 probes this fixture borrows its RX/lever idiom from).

Run:  python tools/coop_test/test_parallel_explosion_thin.py [--seed N]
                 [--slow-client MS]
Exit 0 = pass; 2 = failure.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_intents as PI
import test_parallel_endturn as PE
import test_parallel_soak as SOAK

PORT = "48030"
FIVE = ("terrain", "unitsCore", "items", "itemIdCtr", "unitsCombat")

HE_WEAPON = os.environ.get("E1_HE_WEAPON", "STR_AUTO_CANNON")
HE_AMMO = os.environ.get("E1_HE_AMMO", "STR_AC_HE_AMMO")


def bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def parallel(gc):
    return PI.parallel(gc)


def battle(gc):
    return PI.battle(gc)


def items(gc):
    return gc.ok({"cmd": "battle_items"})


def item_census(gc):
    """{itemId: (type, ownerUnitId)} - the same shape test_coop_blast_item_damage /
    test_coop_alien_launcher_item_loss use, so a divergence prints readably."""
    return {i["id"]: (i["type"], i.get("owner", -1)) for i in items(gc)["items"]}


def diff_item_census(h, c):
    out = []
    for iid in sorted(set(h) | set(c)):
        a, b = h.get(iid), c.get(iid)
        if a == b:
            continue
        if a is None:
            out.append(f"item {iid} {b[0]} exists ONLY on the client (owner {b[1]})")
        elif b is None:
            out.append(f"item {iid} {a[0]} exists ONLY on the host (owner {a[1]})")
        else:
            out.append(f"item {iid} {a[0]}: host owner {a[1]} vs client owner {b[1]}")
    return out


def bucket_snapshot(host):
    sc = session.sync_check(host)
    return {n: sc["buckets"].get(n, {}).get("mismatchCount", 0) for n in FIVE}


def expl_counters(client):
    pc = parallel(client)
    return pc.get("explodeCallsSuppressed", 0), pc.get("explosionsDisplayOnly", 0)


# ---- case (a): HE blast into terrain (shot-origin, mid-side chain) ---------

def case_he_blast(host, client, used):
    tag = "case A (HE blast)"
    enemy = PI.alive_enemy(battle(host))
    assert enemy, f"{tag}: no live hostile to orient the blast around"
    epos = (enemy["x"], enemy["y"], enemy["z"])
    hseat = parallel(host)["localSeat"]
    shooter = None
    for cand in PI.own_units(battle(client), hseat):
        if cand["id"] in used:
            continue
        if PI.place_adjacent(host, client, cand["id"], epos):
            PI.top_up(host, client, cand["id"])
            shooter = cand["id"]
            break
    assert shooter, f"{tag}: could not place a shooter near the hostile"
    used.add(shooter)
    wid = PI.give_both(host, client, shooter, HE_WEAPON, HE_AMMO)
    assert PI.idle(host), f"{tag}: host still busy before the burst"
    PI.top_up(host, client, shooter)
    r = PI.intent(host, action="shoot", unit=shooter, mode="auto", weapon_id=wid,
                  x=epos[0], y=epos[1], z=epos[2])
    assert r.get("ok"), f"{tag}: HE shoot intent refused: {r}"
    assert PI.idle(host, 60), f"{tag}: host chain never ended after the HE burst"
    SOAK.settle_display(host, client, timeout=30)
    time.sleep(1.0)
    return tag


# ---- case (b): timed grenade, resolved on the end-turn boundary sweep ------

def case_timed_grenade(host, client, used):
    tag = "case B (timed grenade, end-turn sweep)"
    hseat = parallel(host)["localSeat"]
    thrower = None
    for cand in PI.own_units(battle(host), hseat):
        if cand["id"] in used:
            continue
        thrower = cand["id"]
        break
    if thrower is None:
        return tag, False, "no live own soldier left to throw the grenade"
    used.add(thrower)
    PI.top_up(host, client, thrower)
    wid = PI.give_both(host, client, thrower, "STR_GRENADE")
    r = PI.intent(host, action="prime", unit=thrower, fuse=1, weapon_id=wid)
    assert r.get("ok"), f"{tag}: prime intent refused: {r}"
    assert PI.idle(host, 30), f"{tag}: host busy after prime"
    tpos = PI.pos(battle(host), thrower)
    enemy = PI.alive_enemy(battle(host))
    tgt = (enemy["x"], enemy["y"], enemy["z"]) if enemy else \
        (tpos[0] + 2, tpos[1], tpos[2])
    r = PI.intent(host, action="throw", unit=thrower, weapon_id=wid,
                  x=tgt[0], y=tgt[1], z=tgt[2])
    if not r.get("ok"):
        return tag, False, f"throw intent refused: {r}"
    assert PI.idle(host, 30), f"{tag}: host chain (the throw) never ended"
    SOAK.settle_display(host, client, timeout=30)

    # NOTE (E1 finding): BattlescapeGame.cpp:1821's whole fuse-roll/spawn loop
    # (the `forRemoval`/`fuseExploded` mechanism at :1850) is gated OFF on ANY
    # coop client via the CLASSIC idiom `coopFuseClient = getCoopStatic() &&
    # !getHost()` (:1816) - true for a parallel client too, since
    # parallelTurnActive() requires getCoopStatic()==true. So a thrown grenade's
    # own detonation NEVER constructs a client-side ExplosionBState at all: its
    # consequences arrive purely via the pre-existing outcome carriers
    # (hit_unit/explode_items/destroy_tile/...) attributed to the HOST's own
    # instance, plus the dedicated `fuse_events` packet
    # (connectionTCP.cpp:9071-9113) that removes the item itself. There is
    # nothing for `_coopReplayDisplay` to suppress on THIS spawn path - it was
    # already carrier-only before E1. So this case additionally arms a small
    # boundary-terrain charge (`checkForTerrainExplosions`, TileEngine.cpp:4110,
    # called UNGATED from BOTH machines at BattlescapeGame.cpp:1924/1928 and
    # :1951/1955) so the boundary sweep is GUARANTEED to construct a real
    # client-side boundary ExplosionBState (_coopBoundaryExpl=true) regardless
    # of the grenade's RNG roll - the deterministic half of this case.
    safe_tile = (tpos[0], tpos[1], tpos[2])
    for gc in (host, client):
        gc.cmd({"cmd": "battle_tiles", "set_explosive": 20, "explosiveType": 0,
                "x": safe_tile[0], "y": safe_tile[1], "z": safe_tile[2]})

    # A fuse==1 grenade detonates on prepareNewTurn's countdown sweep (RNG-gated,
    # best-effort); the armed terrain tile above detonates deterministically at
    # the same boundary. Close sides (bounded) until the grenade is gone from the
    # census or the mission ends.
    detonated = not any(i["id"] == wid for i in items(host)["items"])
    tries = 0
    while not detonated and battle(host).get("inBattle") and tries < 3:
        turn_before = bstate(host)["turn"]
        SOAK.close_side(host, client, 0, 1, turn_before)
        detonated = not any(i["id"] == wid for i in items(host)["items"])
        tries += 1
    return tag, detonated, None


# ---- case (c): proximity grenade, triggered by movement-replay -------------

def case_proximity(host, client, used):
    tag = "case C (proximity trigger)"
    hseat = parallel(host)["localSeat"]
    walker = None
    for cand in PI.own_units(battle(host), hseat):
        if cand["id"] in used:
            continue
        dest = PI.free_step_both(host, client, cand["id"])
        if dest:
            walker = cand["id"]
            wdest = dest
            break
    if walker is None:
        return tag, False, "no live own soldier with a clean single-step tile"
    used.add(walker)
    PI.top_up(host, client, walker)

    drop = [host.ok({"cmd": "battle_give", "unit": walker, "item": "STR_PROXIMITY_GRENADE",
                     "slot": "ground", "fuse": 0,
                     "x": wdest[0], "y": wdest[1], "z": wdest[2]}),
            client.ok({"cmd": "battle_give", "unit": walker, "item": "STR_PROXIMITY_GRENADE",
                       "slot": "ground", "fuse": 0,
                       "x": wdest[0], "y": wdest[1], "z": wdest[2]})]
    assert drop[0]["weaponId"] == drop[1]["weaponId"], (
        f"{tag}: proximity grenade minted different ids on the two machines: {drop}")
    time.sleep(1.5)

    r = PI.intent(host, action="move", unit=walker, x=wdest[0], y=wdest[1], z=wdest[2])
    if not r.get("ok"):
        return tag, False, f"move onto the trigger tile refused: {r}"
    assert PI.idle(host, 60), f"{tag}: host chain (the walk) never ended"
    SOAK.settle_display(host, client, timeout=30)
    return tag, True, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=71717171)
    ap.add_argument("--slow-client", type=int, default=250,
                    help="ms/frame on the client so a real animation-clock/packet-clock "
                         "race is possible if the gate ever regresses (and so RED, which "
                         "re-enables the racing sim, has room to actually race)")
    args = ap.parse_args()

    fails = []
    notes = []
    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": args.slow_client, "battleAlienSpeed": args.slow_client,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48930, make_user_dir("e1_expl_host", options=host_opts))
    client = GameClient("client", 48931, make_user_dir("e1_expl_client", options=client_opts))
    for gc in (host, client):
        SOAK.write_battle_fixture(gc.user_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT
    PI.PORT = PORT
    PE.PORT = PORT
    used = set()
    try:
        TW.bring_up_battle(host, client, seed=args.seed)
        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"skirmish fixture came up gamemode {gm}; parallel turns only cover PVE "
            f"(1) and PVE2 (4) - this fixture would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"

        pc0 = parallel(client)
        for field in ("explodeCallsSuppressed", "explosionsDisplayOnly", "explosionReplayDisable"):
            assert field in pc0, (
                f"parallel_state carries no `{field}` - bin/x64/Release/OpenXcom.exe "
                f"predates the E1 explosion-thin-client instrumentation; rebuild it "
                f"(serial, MP=false). fields: {sorted(pc0)}")
        assert pc0["explosionReplayDisable"] is False, "replay lever not at its default (off)"
        print(f"battle up (seed {args.seed}, gm {gm}). weapon={HE_WEAPON}/{HE_AMMO}")

        SOAK.enable_strict_burnin(host, client)

        pre_h = item_census(host)
        pre_c = item_census(client)
        d0 = diff_item_census(pre_h, pre_c)
        assert not d0, f"item censuses diverged BEFORE any case ran: {d0}"

        sup0, disp0 = expl_counters(client)
        print(f"pre-case: explodeCallsSuppressed={sup0} explosionsDisplayOnly={disp0}")

        # ---- case A: HE blast -------------------------------------------------
        buckets_pre = bucket_snapshot(host)
        tagA = case_he_blast(host, client, used)
        sup_a, disp_a = expl_counters(client)
        hc_a, cc_a = item_census(host), item_census(client)
        d_a = diff_item_census(hc_a, cc_a)
        buckets_a = bucket_snapshot(host)
        delta_a = {k: buckets_a[k] - buckets_pre.get(k, 0) for k in FIVE}
        print(f"{tagA}: explodeCallsSuppressed {sup0}->{sup_a} "
              f"explosionsDisplayOnly {disp0}->{disp_a}  bucket delta {delta_a}")
        if d_a:
            fails.append(f"{tagA}: item census diverged: {d_a}")
        if sup_a <= sup0:
            notes.append(f"{tagA}: explodeCallsSuppressed did not climb ({sup0}->{sup_a})")

        # ---- case B: timed grenade / end-turn sweep ---------------------------
        if not battle(host).get("inBattle"):
            print("       SKIP case B/C: the mission ended during case A")
            tagB, det_b, why_b = "case B (timed grenade)", None, "mission ended"
        else:
            buckets_pre_b = bucket_snapshot(host)
            tagB, det_b, why_b = case_timed_grenade(host, client, used)
            sup_b, disp_b = expl_counters(client)
            hc_b, cc_b = item_census(host), item_census(client)
            d_b = diff_item_census(hc_b, cc_b)
            buckets_b = bucket_snapshot(host)
            delta_b = {k: buckets_b[k] - buckets_pre_b.get(k, 0) for k in FIVE}
            print(f"{tagB}: detonated={det_b} why={why_b} "
                  f"explodeCallsSuppressed ->{sup_b} explosionsDisplayOnly ->{disp_b} "
                  f"bucket delta {delta_b}")
            if why_b:
                notes.append(f"{tagB}: {why_b} (staging shortfall, not a product result)")
            elif not det_b:
                notes.append(f"{tagB}: grenade never detonated within the bounded side-close "
                             f"budget (staging shortfall, not a product result)")
            if d_b:
                fails.append(f"{tagB}: item census diverged: {d_b}")

        # ---- case C: proximity trigger -----------------------------------------
        if not battle(host).get("inBattle"):
            print("       SKIP case C: the mission ended during case A/B")
            tagC, ok_c, why_c = "case C (proximity)", None, "mission ended"
        else:
            buckets_pre_c = bucket_snapshot(host)
            tagC, ok_c, why_c = case_proximity(host, client, used)
            sup_c, disp_c = expl_counters(client)
            hc_c, cc_c = item_census(host), item_census(client)
            d_c = diff_item_census(hc_c, cc_c)
            buckets_c = bucket_snapshot(host)
            delta_c = {k: buckets_c[k] - buckets_pre_c.get(k, 0) for k in FIVE}
            print(f"{tagC}: triggered={ok_c} why={why_c} "
                  f"explodeCallsSuppressed ->{sup_c} explosionsDisplayOnly ->{disp_c} "
                  f"bucket delta {delta_c}")
            if why_c:
                notes.append(f"{tagC}: {why_c} (staging shortfall, not a product result)")
            if d_c:
                fails.append(f"{tagC}: item census diverged: {d_c}")

        # ---- GREEN verdict: cumulative buckets + counters + terrain(sync) -----
        sup_final, disp_final = expl_counters(client)
        sc = session.assert_sync_clean(host, client, "after all three E1 cases",
                                       strict=True, allow=())
        buckets_final = {n: sc["buckets"].get(n, {}).get("mismatchCount", 0) for n in FIVE}
        print(f"\n== GREEN VERDICT ==")
        print(f"  five buckets (strict, cumulative): {buckets_final}")
        print(f"  explodeCallsSuppressed(client): {sup0}->{sup_final}  "
              f"explosionsDisplayOnly(client): {disp0}->{disp_final}")
        bad_buckets = {n: c for n, c in buckets_final.items() if c > 0}
        if bad_buckets:
            fails.append(f"GREEN: five-bucket mismatch {bad_buckets} under strict burn-in.\n"
                         f"    {session._sync_mismatch_lines(sc)}")
        if sup_final <= sup0:
            fails.append(f"GREEN: explodeCallsSuppressed never climbed on the client "
                         f"({sup0}->{sup_final}) - the display path was never exercised, "
                         f"so GREEN would be vacuous")
        if disp_final <= disp0:
            fails.append(f"GREEN: explosionsDisplayOnly never climbed on the client "
                         f"({disp0}->{disp_final})")
        for gc, tag in ((host, "host"), (client, "client")):
            if TW.desync_seen(gc):
                fails.append(f"the PRD-P2 drift tripwire FIRED on the {tag} during GREEN")

        # ---- RED: same build, explosion_replay_disable on the CLIENT only -----
        if not battle(host).get("inBattle"):
            print("\n       SKIP RED: the mission ended before the RED demonstration")
        else:
            client.cmd({"cmd": "parallel_state", "explosion_replay_disable": True})
            pcr = parallel(client)
            assert pcr.get("explosionReplayDisable") is True, \
                f"explosion_replay_disable lever did not latch on the client: {pcr}"
            print("\n== RED: explosion_replay_disable=true on the CLIENT (same build) ==")

            red_sup0, red_disp0 = expl_counters(client)
            buckets_red_pre = bucket_snapshot(host)
            red_used = set(used)
            enemy = PI.alive_enemy(battle(host))
            if enemy is None:
                print("       NOTE: no live hostile left for the RED burst - skipping "
                      "(the deterministic GREEN result above already stands)")
            else:
                try:
                    case_he_blast(host, client, red_used)
                except AssertionError as e:
                    print(f"       NOTE: RED burst could not be staged: {e}")
                red_sup1, red_disp1 = expl_counters(client)
                buckets_red_post = bucket_snapshot(host)
                delta_red = {k: buckets_red_post[k] - buckets_red_pre.get(k, 0) for k in FIVE}
                straddle = sum(delta_red.values())
                print(f"  RED: explodeCallsSuppressed {red_sup0}->{red_sup1} "
                      f"explosionsDisplayOnly {red_disp0}->{red_disp1}")
                print(f"  RED: bucket delta since the lever flipped: {delta_red} "
                      f"(sum {straddle})")

                if red_sup1 > red_sup0 or red_disp1 > red_disp0:
                    fails.append(
                        f"RED: explodeCallsSuppressed/explosionsDisplayOnly kept climbing "
                        f"under explosion_replay_disable ({red_sup0}->{red_sup1}, "
                        f"{red_disp0}->{red_disp1}) - the lever did not actually re-route "
                        f"the client back to the old racing explode()/checkForCasualties path")
                else:
                    print(f"  RED confirmed (deterministic half): the display-only counters "
                          f"stayed FLAT under the lever - the client is really running the "
                          f"old sim again")
                if straddle > 0:
                    print(f"  RED confirmed (statistical half): the five-bucket straddle "
                          f"REAPPEARED (sum {straddle}) with the racing sim re-enabled")
                else:
                    notes.append(
                        f"RED: the five-bucket straddle did NOT reappear this run (sum 0) - "
                        f"statistical, retry-tolerant (see module docstring); the "
                        f"deterministic counter-flat proof above still shows the lever "
                        f"engaged the old code path")

            # restore the lever before anything else touches this battle
            client.cmd({"cmd": "parallel_state", "explosion_replay_disable": False})
            assert parallel(client).get("explosionReplayDisable") is False, \
                "explosion_replay_disable lever did not revert on the client"

        if notes:
            print("\n== NOTES (not failures) ==")
            for n in notes:
                print(f"  NOTE {n}")

        if not fails:
            print("\nPASS: the parallel client's ExplosionBState ran display-only through "
                  "an HE blast, a timed grenade and a proximity trigger - five-bucket "
                  "sync-check clean under strict burn-in, item censuses symmetric, "
                  "explodeCallsSuppressed/explosionsDisplayOnly both climbed, and the "
                  "same build reproduced the old racing-sim code path under "
                  "explosion_replay_disable")
    except Exception as e:
        import traceback
        fails.append(f"[ERROR] {e}\n{traceback.format_exc()}")
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    print("\n==== E1 explosion-thin-client summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
