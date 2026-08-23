"""Parallel battlescape "atomic unit death" rework, Phase 1: per-unit state
watermark fixture.

THE MECHANISM UNDER TEST (BattleUnit::coopStateAccept, connectionTCP.cpp apply
sites for hit_unit/panic_action/psi_result/unit_fall/next_turn): every STAMPED
per-unit state write on the parallel client now carries a (side_seq, action_seq,
rank) tuple, and is applied only if that tuple is >= the unit's own recorded
watermark (lexicographic compare); an UNSTAMPED write bypasses the watermark
entirely, unchanged from before this phase. This closes a real ordering hole: a
STALE absolute snapshot (e.g. a next_turn taken at the alien side's START, rank
0) arriving or being re-applied AFTER a newer chain-carrier write (a hit_unit
rank 1 landed mid-side) must not clobber the fresher value.

This fixture cannot wait for a genuinely reordered network delivery (the harness
has no packet-reordering fault injector), so it uses the SYNTHETIC replay lever
the plan added for exactly this purpose: `parallel_state
{"replay_last_next_turn": true}` re-runs the per-unit bulk-apply loop of the
LAST applied next_turn packet a second time, immediately, on the CLIENT. Since
that packet was stamped when the alien side STARTED (rank 0, action_seq 0), and
the ambushed units keep taking rank-1 hit_unit hits for the rest of that same
side, replaying it is exactly the "stale absolute arrives late" scenario the
watermark exists to reject.

Flow:
  1. Bring up a parallel battle: host EnableCoopParallelTurns, client plain
     (the thin replay peer) and SLOW (--slow-client) so the alien side stays
     open long enough to catch the synthetic replay mid-side.
  2. Ambush several own-seat soldiers next to live aliens (reusing
     test_parallel_alien_death_decouple.ambush) at a HP that survives a hit -
     several stamped hit_unit writes land during the SAME alien side as the
     next_turn snapshot that opened it.
  3. Close the player side; wait for the alien side to start (side flips to 1)
     - this is the next_turn the replay lever will later re-run.
  4. Poll `unit_stats_full` on the client for a unit whose `coopStateRank>=1`
     (a rank-1 hit_unit write was accepted and its watermark recorded).
  5. Fire the lever. GREEN run (default): watermark ON, so the stale rank-0
     replay is rejected for every unit that has since taken a rank-1 hit.
     RED run (--disable-watermark): `parallel_state
     {"death_watermark_disable": true}` is set FIRST, so the check is skipped
     and the stale snapshot overwrites the unit's post-hit state.

Asserts (same build, two separate invocations - "ONCE green, ONCE red"):
  GREEN: stateWatermarkRejects > 0 (the watermark actually rejected something)
         AND the hit unit's unitsCombat fields (kneeled/mc/w0..w5 - the same
         set computeBattleHashes() sums into that bucket) are IDENTICAL between
         host and client (no divergence - the reject was a no-op).
  RED:   stateWatermarkRejects == 0 (the disabled check never ran)
         AND at least one of those unitsCombat fields now DIFFERS between host
         and client (the stale overwrite is a REAL, externally observable
         divergence - exactly the class of bug this phase exists to prevent).
  The diff is read directly (host vs client `unit_stats_full`) rather than
  waiting on the in-game async sync-check ring: that ring only samples a NEW
  compare when the next chain closes, and the alien side's own end-of-side
  absolute (unaffected by this client-local-only corruption) would otherwise
  heal a reverted unit before any such compare could fire.

Non-vacuity: asserts the ambush actually placed soldiers and that at least one
of them took a stamped hit before the lever fires.

Run:  python tools/coop_test/test_parallel_state_watermark.py [--seed N]
                 [--slow-client MS] [--hp N] [--pairs N] [--disable-watermark]
Exit 0 = the expected verdict for the selected mode held; 2 = it did not.
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
import test_parallel_alien_death_decouple as ADD

PORT = "47993"

# unitsCombat = the chain-authored per-unit field set computeBattleHashes() sums
# into the unitsCombat bucket (SharedEcon.cpp) - same list test_parallel_no_reroll
# uses. Health/stun/morale live in unitsRegen instead, so they are read for
# diagnostics (the visible symptom) but not counted toward this mismatch.
COMBAT_FIELDS = ["kneeled", "mc", "w0", "w1", "w2", "w3", "w4", "w5"]


def bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def parallel(gc):
    return gc.cmd({"cmd": "parallel_state"})


def usf(gc):
    return {u["id"]: u for u in gc.ok({"cmd": "unit_stats_full"})["units"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=778899)
    ap.add_argument("--slow-client", type=int, default=300,
                    help="ms/frame on the client so the alien side stays open long "
                         "enough to catch the synthetic replay mid-side")
    ap.add_argument("--hp", type=int, default=45,
                    help="ambushed soldier health - survives a hit, still takes damage")
    ap.add_argument("--pairs", type=int, default=3)
    ap.add_argument("--disable-watermark", action="store_true",
                    help="RED: set parallel_state {death_watermark_disable:true} "
                         "on the client before firing the synthetic replay lever")
    args = ap.parse_args()

    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": args.slow_client, "battleAlienSpeed": args.slow_client,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48886, make_user_dir("watermark_host", options=host_opts))
    client = GameClient("client", 48887, make_user_dir("watermark_client", options=client_opts))
    for gc in (host, client):
        SOAK.write_battle_fixture(gc.user_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT
    PE.PORT = PORT
    fails = []
    rejects = 0
    combat_mm = 0
    try:
        TW.bring_up_battle(host, client, seed=args.seed)
        for gc in (host, client):
            gc.ok({"cmd": "set_seed", "seed": args.seed})
        assert bstate(host)["activeSync"] is True and bstate(client)["activeSync"] is False, \
            "host must own the battle simulation, client must be the replay peer"

        # strict compare so unitsCombat is diffed at every seq, not only at the
        # side-gated boundaries - same lever test_parallel_soak.enable_strict_burnin
        # uses (sync_capture {strict:true}; response carries strictBurnIn).
        for gc, tag in ((host, "host"), (client, "client")):
            r = gc.cmd({"cmd": "sync_capture", "strict": True})
            assert r.get("strictBurnIn") is True, f"{tag}: strict-burnin did not engage: {r}"

        placed = ADD.ambush(host, client, 0, args.pairs, args.hp)
        assert placed > 0, "ambush placed nobody - fixture non-vacuity failed"
        print(f"  ambushed {placed} soldier(s) at hp={args.hp}")

        PE.hush(host, client)
        for gc in (host, client):
            if not parallel(gc)["localReady"]:
                PE.arm(gc)

        # wait for the ALIEN side to start (side flips to 1) - this is the side
        # whose opening next_turn snapshot the replay lever will later re-run.
        got_side = SOAK.poll(lambda: bstate(host).get("side") == 1, 30, 0.2)
        assert got_side, "the alien side never started"
        print(f"  alien side started (turn {bstate(host).get('turn')})")

        # poll for >=1 stamped hit landing on the CLIENT while the side is still
        # open (coopStateRank>=1 = a rank-1 hit_unit write was accepted and its
        # watermark recorded - see BattleUnit::coopStateAccept).
        hit_id = None
        deadline = time.time() + 60
        while time.time() < deadline:
            stats = usf(client)
            hit = next((uid for uid, u in stats.items() if u.get("coopStateRank", 0) >= 1),
                       None)
            if hit is not None:
                hit_id = hit
                break
            if bstate(host).get("side") != 1:
                break
            time.sleep(0.2)
        assert hit_id is not None, (
            "no stamped hit_unit landed on the client during the alien side - "
            "ambush non-vacuous check failed (try --seed/--hp/--pairs)")
        before = usf(client)[hit_id]
        wounds = [before.get(f"w{i}", 0) for i in range(6)]
        print(f"  unit {hit_id} took a stamped hit: coopStateRank={before.get('coopStateRank')} "
              f"health={before.get('health')} wounds={wounds} side={bstate(host).get('side')}")

        if args.disable_watermark:
            # NOTE: like the pre-existing rxSideBarrierDisable lever, a
            # parallel_state response reports state as of BEFORE this same
            # request's own setter runs - so the confirmation needs a follow-up
            # read, not the response to the request that set it.
            client.cmd({"cmd": "parallel_state", "death_watermark_disable": True})
            r = parallel(client)
            assert r.get("deathWatermarkDisable") is True, f"lever did not engage: {r}"
            print("  RED mode: death_watermark_disable=true set on the client")

        # SYNTHETIC RED lever: re-run the last applied next_turn snapshot's
        # per-unit loop once, immediately, against the (possibly since-hit) units.
        client.cmd({"cmd": "parallel_state", "replay_last_next_turn": True})
        p = parallel(client)
        rejects = p.get("stateWatermarkRejects", 0)
        rejects1 = p.get("stateWatermarkRejectsRank1", 0)
        print(f"  after replay: stateWatermarkRejects={rejects} (rank1={rejects1})")

        after = usf(client)[hit_id]
        print(f"  unit {hit_id} post-replay: health={after.get('health')} "
              f"(post-hit was {before.get('health')})")

        # "the next sync_check shows unitsCombat" (the plan's phrasing) needs a
        # NEW chain to close before the host's ring has a fresh compare to make
        # - and the alien side's OWN end-of-side absolute (unaffected by this
        # client-local-only corruption, since it derives from the host's real,
        # never-touched state) would HEAL a reverted unit the moment it lands,
        # before any such compare could fire. So the unitsCombat divergence is
        # read directly and immediately here, instead of waiting on the async
        # ring: the SAME field set computeBattleHashes() sums into the
        # unitsCombat bucket (kneeled, mc, w0..w5 - see
        # test_parallel_no_reroll.COMBAT_FIELDS), diffed host (never touched by
        # the client-local replay) against client (the one the lever just wrote
        # to) for the hit unit, while the side is still open.
        host_u = usf(host)[hit_id]
        client_u = usf(client)[hit_id]
        diffs = [(f, host_u.get(f), client_u.get(f)) for f in COMBAT_FIELDS
                 if host_u.get(f) != client_u.get(f)]
        combat_mm = len(diffs)
        print(f"  unitsCombat field mismatch (host vs client, unit {hit_id}) = "
              f"{combat_mm} {diffs}")

        print("\n== VERDICT ==")
        if args.disable_watermark:
            if rejects != 0:
                fails.append(f"RED: expected stateWatermarkRejects==0 with the lever "
                             f"disabled, got {rejects}")
            if combat_mm <= 0:
                fails.append("RED: expected unitsCombat to diverge (mismatchCount>0) "
                             "once the watermark check was disabled, got 0 - the "
                             "corruption never surfaced (or the watermark held anyway)")
        else:
            if rejects <= 0:
                fails.append(f"GREEN: expected stateWatermarkRejects>0, got {rejects} - "
                             f"the watermark never rejected the stale replay")
            if combat_mm != 0:
                fails.append(f"GREEN: expected unitsCombat mismatchCount==0, got "
                             f"{combat_mm} - the watermark let something through")
    except Exception as e:
        fails.append(f"[ERROR] {e}")
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    mode = "RED (death_watermark_disable)" if args.disable_watermark else "GREEN (watermark ON)"
    if fails:
        print(f"\n==== per-unit state watermark [{mode}]: FAIL ====")
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print(f"\n  PASS [{mode}]: stateWatermarkRejects={rejects} unitsCombat={combat_mm}")
    sys.exit(0)


if __name__ == "__main__":
    main()
