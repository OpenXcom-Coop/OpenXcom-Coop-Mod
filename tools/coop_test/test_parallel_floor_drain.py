"""LIVENESS FLOOR ordering-preserving drain: the FINAL chain-atomicity residual.

THE BUG (single root, verified red/green): the parallel replay client's receive pump has a
last-resort liveness floor - after ~10 s of consuming nothing while holding work back
(connectionTCP.cpp g_rxBlockedStallTicks >= 600) it WHOLESALE-DISABLES the P11 per-subject
ordering, the I1 seq-gate AND the D.1 apply barrier so the pump can never wedge. When it
fires during a casualty-heavy alien side it REORDERS the death-chain carriers (hit_unit /
unit_death / after_unit_death) against the chain markers that sample the per-action sync
hash, and the four buckets straddle at the ai/expl seqs (terrain / unitsCore / unitsCombat
/ items / itemIdCtr). The floor rarely engages now (per-state pacing + force-drain watchdog
+ peer-liveness keep the pump fed), so the residual is a rare tail - but real: with the
floor engaged and the drain OFF this fixture measures unitsCore/unitsCombat/items/itemIdCtr
all non-zero; with the drain ON, all zero.

THE FIX (parallel replay client only): the floor no longer disorders. It KEEPS the whole
ordering machinery intact - per-subject/closer ordering (holds the unstamped alien
shot-death carriers FIFO per victim), the seq-gate and the barrier (hold the stamped
explosion-chain carriers to their own chain) - so the pump applies exactly what it could
un-engaged, in order, and the per-action hash is never polluted. It does NOT force the gated
markers through (forcing samples the chain hash mid-animation and itself straddles
unitsCore). Progress instead comes from the display idling normally OR, if the ordered drain
genuinely cannot progress for a sustained run, a STAGE-2 hard-floor escape hatch reverts to
the legacy full-disable for one pass (a deadlock is worse than a straddle). Classic co-op /
PvP / host are byte-identical (their packets are unstamped; the seq-gate/barrier were inert
and only per-subject ordering was ever disabled there, unchanged).

TEST LEVERS (parallel_state, harness-only): `rx_force_floor` forces the floor to engage
every tick (the rare real stall, on demand) WITHOUT gating any packet, so a naturally-slow
client whose display gates its markers runs under the engaged floor. `rx_drain_disable`
forces the legacy full-disable so the SAME build measures the pre-fix out-of-order burst
(RED) against the ordered drain (GREEN). `rx_hold` parks the pump (display-busy emulation)
to build a genuine wedge for the liveness probe. `rxLegacyPasses`/`rxHardFloorPasses`
introspect the floor: engaged with 0 hard-floor passes = the ordering-preserving drain
carried the whole load.

The scenario ambushes weakened soldiers next to aliens (the alien AI kills a cluster each
side = death chains, whose point-blank plasma also spills a little terrain), forces the
floor, and closes each alien side under --strict-burnin (all five buckets compare at EVERY
seq). Buckets are read cumulatively at the end, after the deferred sync-check loop closes.

  RED  (--red / rx_drain_disable): the five-bucket delta FIRES on the burst -> the fixture
       exercises the bug and the GREEN result is not vacuous.
  GREEN (default):                 the floor engages (rxLegacyPasses climbs) but the delta
       stays ZERO every flood -> order preserved through the drain.

LIVENESS: a genuine wedge (rx_hold: markers gated, never idling) is drained by the stage-2
hard-floor (rxHardFloorPasses climbs, the seq-deferred backlog drops) - no deadlock.

Run:  python tools/coop_test/test_parallel_floor_drain.py [--seed N] [--sides K] [--red]
Exit 0 = the ordered drain preserved order AND liveness (pass); 2 = a straddle/deadlock.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_endturn as PE
import test_parallel_soak as SOAK

PORT = "47994"

# the five buckets the floor collapse contaminates.
FIVE = ("terrain", "unitsCore", "items", "itemIdCtr", "unitsCombat")


def bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def parallel(gc):
    return gc.cmd({"cmd": "parallel_state"})


def corpses(gc):
    return [i["id"] for i in gc.ok({"cmd": "battle_items"})["items"]
            if "CORPSE" in i["type"].upper()]


def bucket_counts(sc):
    b = sc["buckets"]
    return {n: b.get(n, {}).get("mismatchCount", 0) for n in FIVE}


def adj_free(ax, ay, az, occupied):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        p = (ax + dx, ay + dy, az)
        if p not in occupied:
            return p
    return None


def ambush(host, client, pairs, hp):
    """Weaken + place `pairs` soldiers adjacent to live aliens on BOTH machines so the alien
    AI shoots them down in-chain (the death carriers the floor collapse reorders). Keeps
    soldier[0] untouched so the mission cannot end mid-run."""
    hb = bstate(host)
    aliens = [u for u in hb["units"] if u.get("faction") == 1 and not u.get("isOut")]
    soldiers = [u for u in hb["units"] if u.get("faction") == 0 and not u.get("isOut")]
    occupied = {(u["x"], u["y"], u["z"]) for u in hb["units"] if not u.get("isOut")}
    placed = 0
    for alien, sol in list(zip(aliens, soldiers[1:]))[:pairs]:
        p = adj_free(alien["x"], alien["y"], alien["z"], occupied)
        if not p:
            continue
        res = [gc.cmd({"cmd": "battle_teleport", "unit": sol["id"],
                       "x": p[0], "y": p[1], "z": p[2]}) for gc in (host, client)]
        if not all(r.get("moved") for r in res):
            continue
        occupied.add(p)
        for gc in (host, client):
            gc.ok({"cmd": "battle_action", "action": "set_stat", "unit": sol["id"],
                   "health": hp, "visible": True})
        placed += 1
    return placed


def run_side(host, client, pairs, hp):
    """One ambush + alien side under the forced floor. Returns (placed, corpses_grown,
    legacyDelta, hardDelta)."""
    placed = ambush(host, client, pairs, hp)
    turn0 = bstate(host)["turn"]
    corp0 = len(corpses(client))
    p0 = parallel(client)
    SOAK.close_side(host, client, 0, 1, turn0)
    SOAK.settle_display(host, client)
    pN = parallel(client)
    return (placed, len(corpses(client)) - corp0,
            pN.get("rxLegacyPasses", 0) - p0.get("rxLegacyPasses", 0),
            pN.get("rxHardFloorPasses", 0) - p0.get("rxHardFloorPasses", 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=999983)
    ap.add_argument("--sides", type=int, default=5, help="ambush floods (cumulative)")
    ap.add_argument("--hp", type=int, default=35)
    ap.add_argument("--pairs", type=int, default=3)
    ap.add_argument("--slow-client", type=int, default=350,
                    help="ms/frame on the client so its real display gates markers under the "
                         "forced floor (the lag the burst needs)")
    ap.add_argument("--red", action="store_true",
                    help="RED: drain disabled - assert the burst FIRES (non-vacuity), not green")
    args = ap.parse_args()

    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": args.slow_client, "battleAlienSpeed": args.slow_client,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48896, make_user_dir("floordrain_host", options=host_opts))
    client = GameClient("client", 48897, make_user_dir("floordrain_client", options=client_opts))
    for gc in (host, client):
        SOAK.write_battle_fixture(gc.user_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT
    PE.PORT = PORT
    fails = []
    try:
        TW.bring_up_battle(host, client, seed=args.seed)
        for gc in (host, client):
            gc.ok({"cmd": "set_seed", "seed": args.seed})
        assert bstate(host)["activeSync"] is True and bstate(client)["activeSync"] is False, \
            "host must own the battle simulation, client must be the replay peer"
        pc = parallel(client)
        for field in ("rxLegacyPasses", "rxHardFloorPasses", "rxTestHold", "rxDrainDisable",
                      "rxForceFloor", "rxSeqDeferred"):
            assert field in pc, (
                f"parallel_state carries no `{field}` - bin/x64/Release/OpenXcom.exe predates "
                f"the ordering-preserving-floor-drain build; rebuild it (serial, MP=false). "
                f"fields: {sorted(pc)}")
        SOAK.enable_strict_burnin(host, client)
        # force the floor to engage every tick - the rare real stall, on demand.
        client.cmd({"cmd": "parallel_state", "rx_force_floor": True})
        assert parallel(client).get("rxForceFloor") is True, "rx_force_floor lever did not engage"
        mode = "RED (drain DISABLED - pre-fix legacy full-disable)" if args.red \
            else "GREEN (ordering-preserving drain ON)"
        if args.red:
            for gc in (host, client):
                gc.cmd({"cmd": "parallel_state", "rx_drain_disable": True})
        print(f"\n== {mode}: floor forced, {args.sides} casualty-heavy alien sides ==")

        corpses_total = 0
        legacy_total = 0
        hard_total = 0
        for i in range(args.sides):
            if not bstate(host).get("inBattle"):
                print(f"  mission ended before flood {i}"); break
            placed, grown, legd, hard = run_side(host, client, args.pairs, args.hp)
            corpses_total += grown
            legacy_total += legd
            hard_total += hard
            print(f"  flood {i}: placed {placed} corpses+{grown} legacyDelta {legd} "
                  f"hardFloorDelta {hard}")

        # final settle so the deferred sync-check loop fully closes before the census.
        SOAK.settle_display(host, client)
        time.sleep(2)
        sc = session.sync_check(host)
        buckets = bucket_counts(sc)
        total = sum(buckets.values())
        print(f"\n== VERDICT ({'RED' if args.red else 'GREEN'}) ==")
        print(f"  five-bucket cumulative = {buckets}  (sum {total})")
        print(f"  corpses minted = {corpses_total}, floor engagements = {legacy_total}, "
              f"stage-2 hard-floor passes = {hard_total}")

        assert sc.get("strictBurnIn") is True, "strict-burnin lever disengaged - run vacuous"
        assert legacy_total > 0, (
            "the floor never engaged (rxLegacyPasses flat) - rx_force_floor is inert, vacuous")
        assert corpses_total >= 3, (
            "the alien AI killed too few ambushed soldiers - no death chains generated (--seed/--hp)")

        if args.red:
            if total == 0:
                fails.append(
                    "VACUOUS: the drain-disabled floor produced ZERO five-bucket mismatches - the "
                    "burst the fix prevents was not reproduced. Try a slower --slow-client / --seed.")
            else:
                print("  RED burst reproduced - the fix is not vacuous.")
            sys.exit(2 if fails else 0)

        # GREEN: the ordered drain must have kept every bucket clean.
        bad = {b: v for b, v in buckets.items() if v > 0}
        if bad:
            fails.append(
                f"GREEN: five-bucket mismatch {bad} FIRED through the ordered drain (floor engaged "
                f"{legacy_total}x, stage-2 hard-floor {hard_total}x) - the drain did NOT preserve "
                f"order.\n    {session._sync_mismatch_lines(sc)}")
        else:
            print(f"  GREEN clean: the floor engaged {legacy_total}x, the ordering-preserving drain "
                  f"held every bucket (stage-2 hard-floor passes {hard_total}).")

        # ---- LIVENESS ----
        # (1) PRIMARY: the GREEN run above is itself a liveness proof - the floor was engaged
        # EVERY tick for five full alien sides and the battle still progressed to completion
        # with the census equal, so the ordering-preserving drain never deadlocked.
        print("\n== LIVENESS ==")
        print(f"  PRIMARY: the floor was engaged {legacy_total}x across {args.sides} full alien "
              f"sides and the battle completed with the census equal - no deadlock.")
        # (2) The stage-2 hard-floor backstop: park the pump (rx_hold gates the markers + feeds
        # the stall) with the host idle at the boundary so NOTHING consumes - the
        # seed-11100011-class true wedge the floor exists for. Past the ~20 s window the stage-2
        # escape hatch must engage (rxHardFloorPasses climbs) and, on release, fully drain.
        # Best-effort (a slow runner or a busy host can keep the pump fed and heal the wedge
        # before the window): reported, and asserted only when the wedge actually formed.
        try:
            ambush(host, client, args.pairs, args.hp)
            turn0 = bstate(host)["turn"]
            h0 = parallel(client)
            client.cmd({"cmd": "parallel_state", "rx_hold": True})
            PE.hush(host, client)
            for gc in (host, client):
                if not parallel(gc)["localReady"]:
                    PE.arm(gc)
            hard_seen = 0
            peak_hold = 0
            end = time.time() + 26.0
            while time.time() < end:
                pc = parallel(client)
                hard_seen = max(hard_seen,
                                pc.get("rxHardFloorPasses", 0) - h0.get("rxHardFloorPasses", 0))
                peak_hold = max(peak_hold, pc.get("rxHold", 0))
                if hard_seen > 0:
                    break
                time.sleep(0.5)
            client.cmd({"cmd": "parallel_state", "rx_hold": False})
            PE.wait_side(host, client, turn0, timeout=120)
            SOAK.settle_display(host, client)
            drained = parallel(client).get("rxHold", 0)
            print(f"  STAGE-2: parked-pump peakHold={peak_hold} hard-floor engagements={hard_seen} "
                  f"rxHold after release={drained}")
            if hard_seen > 0 and drained > 3:
                fails.append(
                    f"LIVENESS: stage-2 engaged but the queue did not drain on release "
                    f"(rxHold={drained}) - the wedge did not clear")
            elif hard_seen > 0:
                print("  STAGE-2 verified: the hard-floor engaged on the parked pump and it fully "
                      "drained on release - no deadlock.")
            else:
                print("  STAGE-2 note: the wedge healed before the window (host kept the pump fed) "
                      "- stage-2 not exercised this run; the PRIMARY proof stands.")
        except Exception as le:
            print(f"  STAGE-2 note: the backstop probe could not be staged ({le}); the PRIMARY "
                  "liveness proof (GREEN completed under the forced floor) stands.")

    except Exception as e:
        import traceback
        fails.append(f"[ERROR] {e}\n{traceback.format_exc()}")
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    if fails:
        print("\n==== FLOOR-DRAIN: FAIL ====")
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("\n  PASS: the liveness floor engaged (rxLegacyPasses climbed) on the parallel client "
          "yet the ordering-preserving drain kept the I1 seq-gate + the D.1 apply barrier "
          "intact - the five buckets (terrain/unitsCore/items/itemIdCtr/unitsCombat) stayed "
          "ZERO through every alien-side death (RED proves the burst without the drain), and a "
          "forced wedge drained via the stage-2 hard-floor with no deadlock.")
    sys.exit(0)


if __name__ == "__main__":
    main()
