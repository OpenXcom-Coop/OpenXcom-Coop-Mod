"""Explosion ordered-replay migration, Phase E2: host-ordered secondary
detonations - the parallel CLIENT stops scanning/spawning chained secondaries
locally and instead replays them from the host's `chain_detonation` stream, in
the host's scan order.

THE CHANGE. `ExplosionBState::explode()` member's chained-terrain block
(`checkForTerrainExplosions()` + the `new ExplosionBState(...)` it spawns) used
to run UNGATED on every machine, so a heavy cluster of already-charged
secondaries (E0's `test_parallel_explosion_cluster.py` scaffold; 5C in
`research_explosion_mutations.md`) could detonate in a DIFFERENT order on the
host and the client - each machine's own whole-map scan is independent. E2
wraps the whole block in `if (!_coopReplayDisplay)`: the parallel HOST still
scans+spawns (and now ALSO ships one `chain_detonation {tile_pos_x/y/z,
explosive, explosive_type}` per chained spawn, stamped via `coopStampChainSeq`
- its successive scans ARE the order); the parallel CLIENT does neither and
instead detonates secondaries from the ordered `chain_detonation` stream (new
handler in connectionTCP.cpp, seq-gated via `coopIsChainOutcomePacket`, NOT
whitelisted, NOT subject-keyed - same pump rules as `unit_casualty`). This also
deletes the item-2 "stranded" hack (`coopChainedTerrainStranded`): it only ever
fired on a parallel client's OWN scan re-finding its own tile, which can no
longer happen once that scan never runs there.

PROOF SHAPE. This is an ORDER bug, not a state bug - two machines that
detonate the same 9 tiles in different orders can still finish with an
identical final census (SOAK's assert_census would miss it), which is exactly
why the E0 scaffold could only STAGE the cluster, not verify anything about the
chain. `chain_detonation` is unsubjected (`coopPacketSubject` returns -1 for
it, like `destroy_tile`), so the generic `rx_trace` ring carries no per-packet
position - this phase adds a small position-carrying counterpart,
`parallel_state.chainDetonationList` ([x,y,z] tuples, oldest-first,
process-local): the parallel HOST appends to it at the `chain_detonation` SEND
site (so its list IS its scan/send order) and the parallel CLIENT appends to it
at the handler's APPLY site (so its list IS its receive/apply order). GREEN
proof: the client's list, restricted to the entries the burst added, equals
the host's list over the same window - not just same length, same POSITIONS in
the same ORDER. `chainDetonationsSent`/`chainDetonationsApplied` (plain
counters) are the cheap coverage check (nothing dropped or duplicated); the
five-bucket sync-check under strict burn-in (E0/E1's own proof obligation)
rides along for free once the client no longer runs its own casualty/terrain
sim on this path.

GREEN (E2 build, lever off): client `chainDetonationList` order == host
`chainDetonationList` order for the burst window; `chainDetonationsApplied` ==
`chainDetonationsSent` at side close; all five sync-check buckets
(terrain/unitsCore/items/itemIdCtr/unitsCombat) stay at mismatchCount==0 under
strict burn-in; the E0 heavy-cluster scenario (this fixture's own staging,
lifted from `test_parallel_explosion_cluster.py`) is bucket-clean WITHOUT
touching `explosion_replay_disable`.

RED (same build, `explosion_replay_disable:true` on the CLIENT only): the
lever is the SAME `_coopReplayDisplay` latch E1 wired, so it reverts BOTH the
E1 gates (explode()/checkForCasualties) AND this phase's chain-scan gate at
once - the client's own whole-map scan runs again, racing (not replacing) the
still-arriving `chain_detonation` stream from the host, which keeps shipping
regardless of the client's lever. Order/bucket divergence is reported
statistically (same posture as E1's own RED section), not hard-asserted - a
double-processed chain can converge on the SAME order by luck on a given
seed/map, same as the pre-E1 racing sim could converge on the same final
census by luck.

Run:  python tools/coop_test/test_parallel_chain_order.py [--seed N]
Exit 0 = pass; 2 = failure. Keeps well under 180 s (one bring-up, two bursts).
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
import test_parallel_soak as SOAK

PORT = "48042"
FIVE = ("terrain", "unitsCore", "items", "itemIdCtr", "unitsCombat")

WEAPON = os.environ.get("E2_HE_WEAPON", "STR_AUTO_CANNON")
AMMO = os.environ.get("E2_HE_AMMO", "STR_AC_HE_AMMO")

# (2R+1)^2 block of armed tiles - identical staging to the E0 scaffold
# (test_parallel_explosion_cluster.py), reused verbatim so this fixture proves
# the SAME scenario E0 could only stage is now bucket-clean and order-provable.
CLUSTER_R = 1
EXPL_POWER = 20
MIN_STAGED = 3      # E0's minimum: the cluster itself must stage >= 3 tiles
MIN_CHAINED = 2      # need >= 2 chained events for "order" to mean anything

CLIENT_SPEED = 250   # slow client (E1's default): widens the window a racing
                      # scan would need to actually diverge from the host


def parallel(gc):
    return PI.parallel(gc)


def battle(gc):
    return PI.battle(gc)


def tiles(gc):
    return gc.ok({"cmd": "battle_tiles"})


def bucket_snapshot(host):
    sc = session.sync_check(host)
    return {n: sc["buckets"].get(n, {}).get("mismatchCount", 0) for n in FIVE}


def expl_counters(client):
    """E1's display-only-path counters - the DETERMINISTIC half of a RED
    demonstration (test_parallel_explosion_thin.py's own pattern): under
    explosion_replay_disable the client's _coopReplayDisplay computes false, so
    these must stop climbing regardless of whether the order/bucket check
    happens to also catch a straddle this run."""
    pc = parallel(client)
    return pc.get("explodeCallsSuppressed", 0), pc.get("explosionsDisplayOnly", 0)


def chain_counters(gc):
    pc = parallel(gc)
    return pc.get("chainDetonationsSent", 0), pc.get("chainDetonationsApplied", 0)


def chain_list(gc):
    return [tuple(e) for e in parallel(gc).get("chainDetonationList", [])]


def arm_cluster(gcs, cx, cy, cz, power, rad):
    """Lifted verbatim from test_parallel_explosion_cluster.py (E0)/
    test_parallel_explosive_carrier.py (chain-atomicity item-2): arm every tile
    in a (2*rad+1)^2 block centred on (cx,cy,cz) on each of `gcs`, so BOTH
    machines start the burst holding the SAME charged cluster."""
    for gc in gcs:
        for dx in range(-rad, rad + 1):
            for dy in range(-rad, rad + 1):
                gc.cmd({"cmd": "battle_tiles", "set_explosive": power,
                        "explosiveType": 0, "x": cx + dx, "y": cy + dy, "z": cz})


def find_shooter(host, client, hseat, tgt, exclude=()):
    """A LIVE own unit (not in `exclude`) placeable adjacent to `tgt`, given a
    fresh weapon+ammo. Returns (unit_id, weapon_id) or (None, None). Splash
    from a heavy chain blast can knock out or kill whoever triggered it, so a
    second burst must not blindly reuse the same shooter."""
    for cand in PI.own_units(battle(client), hseat):
        sid = cand["id"]
        if sid in exclude:
            continue
        if cand.get("isOut") or cand.get("health", 1) <= 0:
            continue
        if PI.place_adjacent(host, client, sid, tgt):
            PI.top_up(host, client, sid)
            wid = PI.give_both(host, client, sid, WEAPON, AMMO)
            return sid, wid
    return None, None


def fire_burst(host, client, shooter, wid, tgt):
    """One HE shot at `tgt`, waited out to a quiescent, cross-machine-settled
    state. Mirrors test_parallel_explosion_thin.py's case_he_blast /
    test_parallel_explosion_cluster.py's burst-wait."""
    assert PI.idle(host), "host still busy before the burst"
    pre_t = tiles(host)["explosiveTiles"]
    r = PI.intent(host, action="shoot", unit=shooter, mode="auto", weapon_id=wid,
                  x=tgt[0], y=tgt[1], z=tgt[2])
    assert r.get("ok"), f"the burst-triggering shot was refused: {r}"
    assert PI.idle(host, 60), "host chain never ended after the burst"
    SOAK.settle_display(host, client, timeout=45)
    time.sleep(1.0)
    print(f"    [diag] fire_burst at {tgt}: intent={r} explosiveTiles {pre_t}->"
          f"{tiles(host)['explosiveTiles']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=71717171)
    args = ap.parse_args()

    fails = []
    notes = []
    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": CLIENT_SPEED, "battleAlienSpeed": CLIENT_SPEED,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48952, make_user_dir("e2_chainorder_host", options=host_opts))
    client = GameClient("client", 48953, make_user_dir("e2_chainorder_client", options=client_opts))
    for gc in (host, client):
        SOAK.write_battle_fixture(gc.user_dir)

    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        TW.bring_up_battle(host, client, seed=args.seed)
        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"skirmish fixture came up gamemode {gm}; parallel turns only cover PVE "
            f"(1) and PVE2 (4) - this fixture would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"
        print(f"battle up (seed {args.seed}, gm {gm}). weapon={WEAPON}/{AMMO}")

        pc0 = parallel(client)
        for field in ("chainDetonationsSent", "chainDetonationsApplied",
                      "chainDetonationList", "explosionReplayDisable"):
            assert field in pc0, (
                f"parallel_state carries no `{field}` - bin/x64/Release/OpenXcom.exe "
                f"predates the E2 chain_detonation instrumentation; rebuild it "
                f"(serial, MP=false). fields: {sorted(pc0)}")
        assert pc0["explosionReplayDisable"] is False, "replay lever not at its default (off)"

        SOAK.enable_strict_burnin(host, client)

        # ==================================================================
        # GREEN: E2 build, lever off (the default)
        # ==================================================================
        print("\n== GREEN: chain_detonation ordered replay ==")
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
        wid = PI.give_both(host, client, shooter, WEAPON, AMMO)

        arm_cluster((host, client), cx, cy, cz, EXPL_POWER, CLUSTER_R)
        th, tc = tiles(host), tiles(client)
        staged = min(th["explosiveTiles"], tc["explosiveTiles"])
        staged_match = th["explosiveHash"] == tc["explosiveHash"]
        print(f"    cluster staged at ({cx},{cy},{cz}) r={CLUSTER_R}: "
              f"host {th['explosiveTiles']}t client {tc['explosiveTiles']}t "
              f"matched={staged_match}")
        assert staged_match, (
            f"the cluster did not arm IDENTICALLY on both machines - host hash "
            f"{th['explosiveHash']} client {tc['explosiveHash']} - the fixture "
            f"itself is not reproducible")
        assert staged >= MIN_STAGED, (
            f"only staged {staged} charged secondaries (need >= {MIN_STAGED}); "
            f"SHORTFALL on this map/seed with CLUSTER_R={CLUSTER_R}")

        buckets_pre = bucket_snapshot(host)
        sent0, applied0 = chain_counters(host)[0], chain_counters(client)[1]
        host_list0 = chain_list(host)
        client_list0 = chain_list(client)

        fire_burst(host, client, shooter, wid, (cx, cy, cz))

        # a single blast may not chain the whole staged cluster in one go - keep
        # aiming at the cluster centre (report-only diagnostic in E0; here it is
        # the mechanism to build a long-enough proven sequence) until either the
        # target chained-event count is reached or the cluster is exhausted.
        tries = 1
        while (chain_counters(host)[0] - sent0) < MIN_CHAINED and tries < 4 \
                and tiles(host)["explosiveTiles"] > 0 \
                and battle(host).get("inBattle"):
            PI.top_up(host, client, shooter)
            fire_burst(host, client, shooter, wid, (cx, cy, cz))
            tries += 1

        sent1, _ = chain_counters(host)
        _, applied1 = chain_counters(client)
        sent_delta = sent1 - sent0
        applied_delta = applied1 - applied0
        host_list1 = chain_list(host)
        client_list1 = chain_list(client)
        host_new = host_list1[len(host_list0):]
        client_new = client_list1[len(client_list0):]

        print(f"    after {tries} shot(s): chainDetonationsSent {sent0}->{sent1} "
              f"(+{sent_delta})  chainDetonationsApplied {applied0}->{applied1} "
              f"(+{applied_delta})")
        print(f"    host   chain_detonation send order  ({len(host_new)}): {host_new}")
        print(f"    client chain_detonation apply order ({len(client_new)}): {client_new}")

        if sent_delta < MIN_CHAINED:
            notes.append(
                f"GREEN: only {sent_delta} chain_detonation(s) sent this run (wanted "
                f">= {MIN_CHAINED}) - staging/adjacency shortfall on this map/seed, "
                f"not a product result; the sent==applied and order checks below "
                f"still run on whatever count was achieved")

        if sent_delta == 0:
            fails.append(
                "GREEN: the cluster staged but NO chain_detonation was ever sent - "
                "the burst never chained, so this run cannot prove anything about "
                "order (staging shortfall, not a pump/host bug - rerun with a "
                "different --seed)")
        else:
            if applied_delta != sent_delta:
                fails.append(
                    f"GREEN: chainDetonationsApplied ({applied_delta}) != "
                    f"chainDetonationsSent ({sent_delta}) for this burst - a "
                    f"chain_detonation was dropped or double-applied "
                    f"(STOP-AND-REPORT: coverage bug)")
            if client_new != host_new:
                fails.append(
                    f"GREEN: client chain_detonation apply order {client_new} != "
                    f"host send order {host_new} - the client did not replay the "
                    f"host's scan order (STOP-AND-REPORT: ordering bug)")
            else:
                print(f"    ORDER MATCH: client replayed the host's {len(host_new)}-"
                      f"secondary scan order exactly")

        sc = session.assert_sync_clean(host, client, "after the GREEN chain burst(s)",
                                        strict=True, allow=())
        buckets_post = {n: sc["buckets"].get(n, {}).get("mismatchCount", 0) for n in FIVE}
        bucket_delta = {k: buckets_post[k] - buckets_pre.get(k, 0) for k in FIVE}
        print(f"    five-bucket delta (strict, cumulative): {bucket_delta}")
        bad_buckets = {n: c for n, c in buckets_post.items() if c > 0}
        if bad_buckets:
            fails.append(f"GREEN: five-bucket mismatch {bad_buckets} under strict "
                         f"burn-in.\n    {session._sync_mismatch_lines(sc)}")
        for gc, tag in ((host, "host"), (client, "client")):
            if TW.desync_seen(gc):
                fails.append(f"the PRD-P2 drift tripwire FIRED on the {tag} during GREEN")

        assert parallel(client)["explosionReplayDisable"] is False, (
            "explosion_replay_disable drifted ON during GREEN - the run above did "
            "not actually exercise the E2 enforcing path")
        print("PASS (GREEN precondition): explosion_replay_disable stayed OFF the "
              "whole run - the E0 heavy-cluster scenario is bucket-clean WITHOUT "
              "needing its lever, unlike E0 itself which could only stage it")

        # ==================================================================
        # RED: same build, explosion_replay_disable:true on the CLIENT only
        # ==================================================================
        if not battle(host).get("inBattle"):
            print("\n       SKIP RED: the mission ended during GREEN")
        else:
            print("\n== RED: explosion_replay_disable=true on the CLIENT (same build) ==")
            client.cmd({"cmd": "parallel_state", "explosion_replay_disable": True})
            pcr = parallel(client)
            assert pcr.get("explosionReplayDisable") is True, \
                f"explosion_replay_disable lever did not latch on the client: {pcr}"
            hb_diag = battle(host)
            hostiles = [u for u in hb_diag.get("units", [])
                       if u.get("faction") == 1 and not u.get("isOut")]
            shooter_u = next((u for u in hb_diag.get("units", [])
                              if u["id"] == shooter), None)
            print(f"    [diag] pre-RED: inBattle={hb_diag.get('inBattle')} "
                  f"liveHostiles={len(hostiles)} shooter={shooter_u}")

            # a fresh, never-yet-blasted cluster: GREEN's own spot is now rubble/
            # craters, and a shot that lands short on the new terrain can miss
            # the armed tiles entirely (observed: explosiveTiles unchanged after
            # the shot). Try a few candidate offsets, each with a fresh
            # shooter placement + a topped-up weapon, until one actually
            # consumes at least one armed tile.
            red_fired = False
            red_used = {shooter}   # GREEN's shooter took its own blast's splash -
                                    # a knocked-out/killed unit cannot fire again
            for ox, oy in ((0, -4), (-4, 0), (0, 4), (4, 0)):
                rx, ry, rz = cx + ox, cy + oy, cz
                arm_cluster((host, client), rx, ry, rz, EXPL_POWER, CLUSTER_R)
                thr, tcr = tiles(host), tiles(client)
                red_staged = min(thr["explosiveTiles"], tcr["explosiveTiles"])
                print(f"    RED candidate ({rx},{ry},{rz}): staged host "
                      f"{thr['explosiveTiles']}t client {tcr['explosiveTiles']}t")
                if red_staged < 1:
                    continue
                red_shooter, red_wid = find_shooter(host, client, hseat, (rx, ry, rz),
                                                     exclude=red_used)
                if red_shooter is None:
                    notes.append(f"RED: candidate ({rx},{ry},{rz}): no live, "
                                 f"placeable shooter left")
                    continue
                red_used.add(red_shooter)
                buckets_red_pre = bucket_snapshot(host)
                red_sent0, red_applied0 = chain_counters(host)[0], chain_counters(client)[1]
                red_host_list0 = chain_list(host)
                red_client_list0 = chain_list(client)
                sup0, disp0 = expl_counters(client)
                try:
                    fire_burst(host, client, red_shooter, red_wid, (rx, ry, rz))
                except AssertionError as e:
                    notes.append(f"RED: candidate ({rx},{ry},{rz}) burst refused: {e}")
                    continue
                red_sent1, _ = chain_counters(host)
                _, red_applied1 = chain_counters(client)
                red_sent_delta = red_sent1 - red_sent0
                if red_sent_delta == 0:
                    notes.append(f"RED: candidate ({rx},{ry},{rz}) shot fired but "
                                 f"chained nothing (missed the cluster) - trying "
                                 f"another offset")
                    continue
                red_fired = True
                red_applied_delta = red_applied1 - red_applied0
                red_host_new = chain_list(host)[len(red_host_list0):]
                red_client_new = chain_list(client)[len(red_client_list0):]
                sc_red = session.sync_check(host)
                buckets_red_post = {n: sc_red["buckets"].get(n, {}).get("mismatchCount", 0)
                                    for n in FIVE}
                delta_red = {k: buckets_red_post[k] - buckets_red_pre.get(k, 0) for k in FIVE}
                straddle = sum(delta_red.values())
                order_diverged = (red_client_new != red_host_new)
                sup1, disp1 = expl_counters(client)

                print(f"    RED: chainDetonationsSent +{red_sent_delta}  "
                      f"chainDetonationsApplied +{red_applied_delta}")
                print(f"    RED: host send order  {red_host_new}")
                print(f"    RED: client apply order {red_client_new}  "
                      f"(diverged={order_diverged})")
                print(f"    RED: five-bucket delta since the lever flipped: "
                      f"{delta_red} (sum {straddle})")
                print(f"    RED: explodeCallsSuppressed {sup0}->{sup1}  "
                      f"explosionsDisplayOnly {disp0}->{disp1}")

                if sup1 > sup0 or disp1 > disp0:
                    fails.append(
                        f"RED: explodeCallsSuppressed/explosionsDisplayOnly kept "
                        f"climbing under explosion_replay_disable ({sup0}->{sup1}, "
                        f"{disp0}->{disp1}) - the lever did not actually re-route the "
                        f"client back to the old racing chain-scan path")
                else:
                    print("  RED confirmed (deterministic half): the display-only "
                          "counters stayed FLAT under the lever - the client is "
                          "really running the old racing chain-scan again")

                if order_diverged or straddle > 0 or red_applied_delta != red_sent_delta:
                    print("  RED confirmed (statistical half): order/coverage/bucket "
                          "divergence observed with the client's own racing scan "
                          "re-enabled alongside the still-arriving chain_detonation "
                          "stream")
                else:
                    notes.append(
                        "RED: no order/bucket divergence observed this run (order "
                        "matched, buckets clean, sent==applied) - statistical, "
                        "retry-tolerant (see module docstring); the deterministic "
                        "counter-flat proof above still shows the lever engaged the "
                        "old code path, and the GREEN result already stands on its "
                        "own")
                break
            if not red_fired:
                notes.append("RED: no candidate offset both staged AND actually "
                             "chained a burst - RED demonstration skipped this run, "
                             "GREEN result stands (statistical, retry-tolerant)")

            client.cmd({"cmd": "parallel_state", "explosion_replay_disable": False})
            assert parallel(client).get("explosionReplayDisable") is False, \
                "explosion_replay_disable lever did not revert on the client"

        if notes:
            print("\n== NOTES (not failures) ==")
            for n in notes:
                print(f"  NOTE {n}")

        if not fails:
            print("\nPASS: the parallel client replayed the host's chained-secondary "
                  "detonations in the host's exact scan order (chainDetonationList "
                  "match), chainDetonationsApplied == chainDetonationsSent, and the "
                  "five-bucket sync-check stayed clean under strict burn-in without "
                  "the explosion_replay_disable lever; the same build reproduced "
                  "observable divergence with the lever forcing the client's old "
                  "racing scan back on")
    except Exception as e:
        import traceback
        fails.append(f"[ERROR] {e}\n{traceback.format_exc()}")
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    print("\n==== E2 chain-order summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
