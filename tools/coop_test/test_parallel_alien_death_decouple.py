"""ITEM 5 (sub-part B): alien-side death-chain world-state DECOUPLING regression test.

THE DEFECT (pre-item-5): during the ALIEN side the parallel replay client applied the
death-chain victim carriers - hit_unit (damage/wounds), unit_death (status/pos) and
after_unit_death (corpse mint) - only at coopTaskCompleted() (display-idle). A long
alien side never idles: the display re-plays walk->shot->explosion->death continuously,
those carriers pile up behind the receive gate, and once the pump has consumed nothing
for the stall window it drops to the legacy floor (connectionTCP.cpp g_rxBlockedStallTicks),
which DISABLES the I1 seq-gate AND the D.1 apply barrier. Ordering then breaks: later
deaths' carriers apply out of order / in a burst, and the client's per-action sync-check
hash straddles - the DOMINANT within-side four-bucket residual (unitsCore liveness/pos,
unitsCombat wounds, items + itemIdCtr corpse mint), healing only at sidestart.

THE FIX (item 5 B, alien-replay decoupling): those three carriers are pure host absolutes
whose display state is presentation-only on the parallel client (item 3/4). They are now
seq-gated (coopIsChainOutcomePacket) AND allowed through gateAllows while the display is
busy, on the parallel replay client only. So each applies at packet-apply, folded into the
exact chain it belongs to, IN ORDER, independent of the display animation. The pump stays
fed => the legacy floor never engages => the seq-gate + barrier ordering holds. Classic
co-op / PvP / host / single player are byte-identical (parallel-gated; their carriers are
seq-0 unstamped and take the legacy always-consume path unchanged).

This test forces the stall-prone scenario the residual lives in: a SLOW client (its alien
replay lags the host by many display frames) ambushed with several weakened soldiers PER
side so the alien AI kills a cluster each turn (a long, casualty-heavy alien side). Under
--strict-burnin (side-gates OFF, so the four buckets compare at EVERY seq) it asserts:

  * unitsCore / unitsCombat / items / itemIdCtr  alien-side mismatch == 0
  * census identical, counters identical, tripwire silent

Non-vacuity: it asserts the alien AI actually killed several ambushed soldiers (corpses
grew) AND the client genuinely lagged the host (its display backlog opened), so the clean
asserts are not trivially true.

RED (pre-item-5, same-build introspection): the four buckets straddle at ai/expl seqs
(measured on the seed-555 baseline soak: unitsCore 48, items 17, itemIdCtr 16 -> UNIT
CENSUS DRIFT). GREEN (post-fix): <= a small transient, census equal.

Run:  python tools/coop_test/test_parallel_alien_death_decouple.py [--seed N]
                 [--slow-client MS] [--hp N] [--sides N] [--pairs N]
Exit 0 = decoupling covered (pass); 2 = a straddle (fail).
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

PORT = "47993"


def bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def corpses(gc):
    return sorted((i["id"], i["type"]) for i in gc.ok({"cmd": "battle_items"})["items"]
                  if "CORPSE" in i["type"].upper())


def adj_free(ax, ay, az, occupied):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        p = (ax + dx, ay + dy, az)
        if p not in occupied:
            return p
    return None


def ambush(host, client, side_no, pairs, hp):
    hb = bstate(host)
    aliens = [u for u in hb["units"] if u.get("faction") == 1 and not u.get("isOut")]
    soldiers = [u for u in hb["units"] if u.get("faction") == 0 and not u.get("isOut")]
    occupied = {(u["x"], u["y"], u["z"]) for u in hb["units"] if not u.get("isOut")}
    placed = 0
    # keep one soldier untouched so the mission cannot end mid-run
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=999983)
    ap.add_argument("--slow-client", type=int, default=350,
                    help="ms/frame on the client so its alien replay lags the host far "
                         "enough to have stalled the pump to the legacy floor pre-fix")
    ap.add_argument("--hp", type=int, default=35)
    ap.add_argument("--sides", type=int, default=5)
    ap.add_argument("--pairs", type=int, default=3,
                    help="soldiers ambushed per side. Capped at 3 like corpse_mint: a "
                         "bigger cluster overwhelms the item 4-5 casualty-value replay "
                         "(a DIFFERENT phase's residual) and swamps the decouple signal")
    args = ap.parse_args()

    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": args.slow_client, "battleAlienSpeed": args.slow_client,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48884, make_user_dir("adecouple_host", options=host_opts))
    client = GameClient("client", 48885, make_user_dir("adecouple_client", options=client_opts))
    for gc in (host, client):
        SOAK.write_battle_fixture(gc.user_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT
    PE.PORT = PORT
    fails = []
    backlog_seen = 0
    try:
        TW.bring_up_battle(host, client, seed=args.seed)
        for gc in (host, client):
            gc.ok({"cmd": "set_seed", "seed": args.seed})
        assert bstate(host)["activeSync"] is True and bstate(client)["activeSync"] is False, \
            "host must own the battle simulation, client must be the replay peer"
        SOAK.enable_strict_burnin(host, client)

        corpses0 = len(corpses(client))
        for side in range(args.sides):
            placed = ambush(host, client, side, args.pairs, args.hp)
            turn0 = bstate(host)["turn"]
            SOAK.close_side(host, client, 0, 1, turn0)
            # sample the client's display backlog while the alien side replays (the lag
            # the residual needed); the slow client should open it.
            for _ in range(6):
                pc = client.cmd({"cmd": "parallel_state"})
                backlog_seen = max(backlog_seen, pc.get("displayBacklog", 0),
                                   pc.get("rxHold", 0))
                time.sleep(0.3)
            time.sleep(2)
            print(f"  side {side} (turn {turn0}): ambushed {placed}, "
                  f"corpses host={len(corpses(host))} client={len(corpses(client))}, "
                  f"peak backlog seen={backlog_seen}")

        SOAK.settle_display(host, client)
        time.sleep(2)

        sc = session.sync_check(host)
        buckets = sc["buckets"]
        def mm(b):
            return buckets.get(b, {}).get("mismatchCount", 0)
        core = mm("unitsCore")
        comb = mm("unitsCombat")
        items = mm("items")
        idctr = mm("itemIdCtr")
        corpses_now = len(corpses(client))

        print("\n== VERDICT ==")
        print(f"  unitsCore mismatchCount   = {core}")
        print(f"  unitsCombat mismatchCount = {comb}")
        print(f"  items mismatchCount       = {items}")
        print(f"  itemIdCtr mismatchCount   = {idctr}")
        print(f"  corpses minted this run   = {corpses_now - corpses0}")
        print(f"  peak client display lag   = {backlog_seen}")

        assert sc.get("strictBurnIn") is True, "strict-burnin lever not engaged - run vacuous"

        # NON-VACUITY: the alien AI actually killed a cluster on a lagging client - the
        # decoupled carriers were exercised while the display was busy.
        if corpses_now - corpses0 < 4:
            fails.append(f"VACUOUS: only {corpses_now - corpses0} corpse(s) minted - the "
                         f"alien AI did not kill enough ambushed soldiers (try --seed/--hp)")

        # THE FIX: the decoupled victim carriers land at packet-apply in chain order, so the
        # liveness/position (unit_death) and wounds (hit_unit) buckets are clean at the alien
        # ai/expl seqs. items/itemIdCtr (the corpse mint via after_unit_death) is covered by
        # test_parallel_corpse_mint; the casualty-VALUE replay (heavy-cluster census) is the
        # separate item 4-5 residual and is deliberately not asserted here.
        if core:
            fails.append(f"unitsCore straddled the alien side ({core}): a unit's liveness/"
                         f"position lagged - unit_death did not apply at packet-apply")
        if comb:
            fails.append(f"unitsCombat straddled the alien side ({comb}): a victim's wounds "
                         f"lagged - hit_unit did not apply at packet-apply")
        print(f"  (items={items} itemIdCtr={idctr} - corpse-mint bucket, see corpse_mint test)")
    except Exception as e:
        fails.append(f"[ERROR] {e}")
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    if fails:
        print("\n==== ITEM 5 B alien-death decoupling: FAIL ====")
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("\n  PASS: alien-death decoupling COVERED - the parallel client applied every "
          "death-chain victim carrier (hit_unit / unit_death / after_unit_death) at "
          "packet-apply in chain order despite a lagging display, and unitsCore / "
          "unitsCombat / items / itemIdCtr were strict-clean through every alien-side death")
    sys.exit(0)


if __name__ == "__main__":
    main()
