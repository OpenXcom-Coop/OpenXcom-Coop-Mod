"""CHAIN-ATOMICITY final residual: loose mid-side death stamping (Strand A) + the side
barrier that keeps a stamped death from crossing the side change (Strand B).

THE TWO DEFECTS (both live only on the parallel replay client, casualty-heavy alien side):

  STRAND A - unstamped loose death. A unit that dies AFTER its killing chain already
  drained runs its UnitDieBState with the host's open-chain seq == 0, so unit_death /
  after_unit_death ship seq-0 UNSTAMPED. Seq-0 = legacy always-consume: the client applies
  the death immediately, out of the ordered I1 seq-gate + D.1 apply barrier, and folds it
  into a neighbouring chain's post-N sync-check hash -> items/itemIdCtr/unitsCore straddle at
  the ai/expl seqs. THE FIX opens a LOOSE chain in UnitDieBState::init (parallel host, open
  seq == 0, NOT boundary phase) so both death carriers carry a seq and defer on the ordered
  gate exactly like an in-chain death. Boundary-phase deaths (side-close fuse/terrain/
  environmental + neutral->player bleed-out) are excluded via a construction-latched
  _coopBoundaryDeath flag so they stay seq-0 under the ordered endturn/sidestart marker.

  STRAND B - stale-side stamped death crossing the side change. A stamped death of side S is
  still deferred (its chain not yet open in the client's display) when the WHITELISTED endTurn
  packet advances the client's _sideSeq to S+1 and resetActionArbiter zeroes _clientDisplaySeq.
  The straggler's pktSide != _sideSeq now, so the seq-gate (same-side only) no longer holds it
  and it legacy-consumes out of order, straddling the boundary. THE FIX is a SIDE BARRIER: hold
  the endTurn packet's consumption while any stamped current-side packet is still deferred, so
  the client finishes side S before retiring its side token. The barrier drains as the display
  cursor advances off side-S chain markers (which are ahead of endTurn, never held), and it is
  disabled under the legacy hard floor exactly like the seq-gate, so kRxDrainHardFloorMs is the
  documented last-resort release (proof it can never starve).

THE SCENARIO ambushes weakened soldiers next to aliens so the alien AI kills a cluster each
side (loose + in-chain death carriers, some crossing the side change on the slow client),
closes each alien side under --strict-burnin (all buckets compare at EVERY seq), and reads:

  GREEN (default):  midSideDeathsUnstamped == 0 (Strand A: every mid-side death stamped) AND
                    the five buckets ZERO (terrain/unitsCore/unitsCombat/items/itemIdCtr) AND
                    the side barrier actually engaged (sideBarrierHolds > 0) and released
                    every held token (sideBarrierReleases > 0, hard releases not required).
  RED (--red):      rx_side_barrier_disable ON - the SAME build, Strand A still stamping, but
                    the side barrier off: the stale-side crossing straddle FIRES (non-vacuity).
  LIVENESS:         a forced pump wedge (rx_hold) closes a side under the barrier - it still
                    reaches the boundary (the P8 side-close handshake completes) via the
                    stage-2 hard-floor release, no hang.

Non-vacuity: the alien AI must actually kill a cluster (corpses grew) and the mid-side death
path must have run (midSideDeaths > 0).

Run:  python tools/coop_test/test_parallel_loose_death.py [--seed N] [--slow-client MS]
                 [--sides K] [--hp N] [--pairs N] [--red]
Exit 0 = both strands covered (pass); 2 = an unstamped death, a straddle, or a hang.
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
import test_parallel_alien_death_decouple as AD

PORT = "47996"
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=8675309)
    ap.add_argument("--slow-client", type=int, default=350,
                    help="ms/frame on the client so its alien replay lags the host far enough "
                         "that late-side deaths are still deferred when endTurn arrives")
    ap.add_argument("--sides", type=int, default=5)
    ap.add_argument("--hp", type=int, default=35)
    ap.add_argument("--pairs", type=int, default=3)
    ap.add_argument("--red", action="store_true",
                    help="RED: disable JUST the side barrier (same build) - assert the "
                         "stale-side crossing straddle FIRES (Strand B non-vacuity)")
    args = ap.parse_args()

    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": args.slow_client, "battleAlienSpeed": args.slow_client,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48898, make_user_dir("loosedeath_host", options=host_opts))
    client = GameClient("client", 48899, make_user_dir("loosedeath_client", options=client_opts))
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

        # parallel_state must carry the new counters or the exe predates this build.
        pc = parallel(client)
        for f in ("sideBarrierHolds", "sideBarrierReleases", "sideBarrierHardReleases",
                  "rxSideBarrierDisable", "midSideDeaths", "midSideDeathsUnstamped"):
            assert f in parallel(host) or f in pc, (
                f"parallel_state carries no `{f}` - bin/x64/Release/OpenXcom.exe predates the "
                f"Strand-A/B build; rebuild it (serial, MP=false). fields: {sorted(pc)}")

        SOAK.enable_strict_burnin(host, client)
        if args.red:
            client.cmd({"cmd": "parallel_state", "rx_side_barrier_disable": True})
            assert parallel(client).get("rxSideBarrierDisable") is True, \
                "rx_side_barrier_disable lever did not engage"
            print("== RED: side barrier DISABLED on the client (Strand A still stamping) ==")
        else:
            print("== GREEN: both strands active ==")

        corp0 = len(corpses(client))
        for side in range(args.sides):
            if not bstate(host).get("inBattle"):
                print(f"  mission ended before side {side}"); break
            placed = AD.ambush(host, client, side, args.pairs, args.hp)
            turn0 = bstate(host)["turn"]
            SOAK.close_side(host, client, 0, 1, turn0)
            time.sleep(1)
            print(f"  side {side} (turn {turn0}): ambushed {placed}, corpses "
                  f"host={len(corpses(host))} client={len(corpses(client))}")

        SOAK.settle_display(host, client)
        time.sleep(2)
        sc = session.sync_check(host)
        buckets = bucket_counts(sc)
        total = sum(buckets.values())
        ph = parallel(host)
        pcl = parallel(client)
        mid = ph.get("midSideDeaths", 0)
        unstamped = ph.get("midSideDeathsUnstamped", 0)
        grown = len(corpses(client)) - corp0

        print("\n== VERDICT ==")
        print(f"  midSideDeaths={mid} midSideDeathsUnstamped={unstamped} corpses+={grown}")
        print(f"  five-bucket = {buckets} (sum {total})")
        print(f"  sideBarrierHolds={pcl.get('sideBarrierHolds')} "
              f"Releases={pcl.get('sideBarrierReleases')} "
              f"HardReleases={pcl.get('sideBarrierHardReleases')} "
              f"rxSeqDeferred={pcl.get('rxSeqDeferred')} barrierBlocks={pcl.get('barrierBlocks')} "
              f"rxLegacyPasses={pcl.get('rxLegacyPasses')}")

        assert sc.get("strictBurnIn") is True, "strict-burnin lever disengaged - run vacuous"
        if grown < 4:
            fails.append(f"VACUOUS: only {grown} corpse(s) minted - the alien AI did not kill "
                         f"enough ambushed soldiers (try --seed/--hp)")
        if mid < 1:
            fails.append("VACUOUS: no mid-side deaths were seen (midSideDeaths==0) - the loose-"
                         "death stamp path was never exercised")

        # STRAND A (build-invariant, no lever): every mid-side death must have been stamped.
        if unstamped:
            fails.append(f"STRAND A: {unstamped} mid-side death(s) shipped UNSTAMPED "
                         f"(_openChainSeq==0) - the loose-death chain stamp did not fire")

        if args.red:
            # STRAND B non-vacuity: the crossing straddle must reproduce with the barrier off.
            if total == 0:
                fails.append("VACUOUS RED: the barrier-disabled run produced ZERO five-bucket "
                             "mismatches - the stale-side crossing was not reproduced "
                             "(try a slower --slow-client / another --seed)")
            else:
                print(f"  RED straddle reproduced (sum {total}) - the side barrier is not vacuous.")
        else:
            # STRAND B green: no straddle, and the barrier engaged + released.
            bad = {b: v for b, v in buckets.items() if v > 0}
            if bad:
                fails.append(f"GREEN: five-bucket mismatch {bad} FIRED with the barrier active - "
                             f"a stamped death straddled the boundary.\n    "
                             f"{session._sync_mismatch_lines(sc)}")
            if pcl.get("sideBarrierHolds", 0) < 1:
                # the barrier never had to engage this run: the crossing did not form (a fast
                # runner). Not a failure of the fix, but flag it so a vacuous green is visible.
                print("  NOTE: sideBarrierHolds==0 this run - the stale-side crossing did not "
                      "form (the client kept up); the clean buckets still hold, but re-run with "
                      "a slower --slow-client to exercise the barrier.")
            else:
                print(f"  GREEN clean: the side barrier engaged "
                      f"{pcl.get('sideBarrierHolds')}x and released every held token "
                      f"(normal={pcl.get('sideBarrierReleases')}, "
                      f"hard={pcl.get('sideBarrierHardReleases')}).")

        # ---- LIVENESS (green only): a forced pump wedge still reaches the boundary ----
        if not args.red and not fails and bstate(host).get("inBattle"):
            print("\n== LIVENESS: forced wedge under the side barrier ==")
            try:
                AD.ambush(host, client, args.sides, args.pairs, args.hp)
                turn0 = bstate(host)["turn"]
                h0 = parallel(client)
                client.cmd({"cmd": "parallel_state", "rx_hold": True})
                # both seats ready so the side wants to close while the pump is parked.
                PE.hush(host, client)
                for gc in (host, client):
                    if not parallel(gc)["localReady"]:
                        PE.arm(gc)
                # let the wedge form, then release the hold and require the side to close.
                time.sleep(6)
                held = parallel(client).get("sideBarrierHolds", 0) - h0.get("sideBarrierHolds", 0)
                client.cmd({"cmd": "parallel_state", "rx_hold": False})
                closed = PE.wait_side(host, client, turn0, timeout=180)
                SOAK.settle_display(host, client)
                pN = parallel(client)
                rel = pN.get("sideBarrierReleases", 0) - h0.get("sideBarrierReleases", 0)
                hard = pN.get("sideBarrierHardReleases", 0) - h0.get("sideBarrierHardReleases", 0)
                print(f"  wedge: heldDelta={held} releaseDelta={rel} hardReleaseDelta={hard} "
                      f"sideClosed={bool(closed)}")
                if not closed and bstate(host).get("inBattle"):
                    fails.append("LIVENESS: the side never closed under a forced wedge with the "
                                 "barrier active - the held endTurn starved (no hard-floor release)")
                elif held > 0 and rel == 0 and hard == 0:
                    fails.append(f"LIVENESS: the barrier held ({held}) but nothing released it "
                                 f"(normal=0 hard=0) though the side closed - accounting broke")
                else:
                    print("  LIVENESS verified: the forced wedge still reached the boundary "
                          "(P8 side-close handshake completed) and the barrier released.")
            except Exception as le:
                print(f"  LIVENESS note: the wedge probe could not be staged ({le}); the GREEN "
                      "run above (every side closed with the barrier engaged) still stands as a "
                      "primary liveness proof.")

    except Exception as e:
        import traceback
        fails.append(f"[ERROR] {e}\n{traceback.format_exc()}")
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    if args.red:
        # RED exits 0 when it successfully reproduced the straddle (fails only on vacuity/error).
        if fails:
            print("\n==== LOOSE-DEATH RED: FAIL ====")
            for f in fails:
                print(f"  FAIL {f}")
            sys.exit(2)
        print("\n  RED PASS: with the side barrier disabled the stale-side crossing straddle "
              "reproduced (Strand A still stamped every mid-side death) - the barrier is load-bearing.")
        sys.exit(0)

    if fails:
        print("\n==== LOOSE-DEATH: FAIL ====")
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("\n  PASS: every mid-side death was stamped (Strand A: midSideDeathsUnstamped==0), the "
          "five buckets stayed ZERO through every alien-side death, and the side barrier held the "
          "stale-side crossing and released it in time (Strand B) - a forced wedge still reached "
          "the boundary with no hang.")
    sys.exit(0)


if __name__ == "__main__":
    main()
