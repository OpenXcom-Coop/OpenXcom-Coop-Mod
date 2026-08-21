"""ITEM 3 (chain-atomicity completion): corpse mint-at-apply regression test.

THE DEFECT (pre-item-3): when a unit dies during the ALIEN side, the parallel
replay client used to create that unit's corpse + spill its kit on its own death
ANIMATION clock (UnitDieBState::convertUnitToCorpse), a beat out of step with the
host's authoritative resolution. The P4 id-manifest then reconciled the ids "a beat
late" at the after_unit_death apply. In that mid-flight window the client's item-id
COUNTER was bumped at a different point than the host's, so a per-action sync-check
hash that sampled the ai/expl chain straddled it - the alien-side items/itemIdCtr
burn-in residual (seeds 8675309/555/999983, 2-12 per soak run).

THE FIX (mint-at-apply): the parallel replay client now creates the corpse + spills
the inventory + unlinks the tile at the after_unit_death PACKET APPLY (ordered
bookkeeping clock), adopting the host's manifest ids AT CREATE. after_unit_death
rides the ordered gate + the D.1 action_end apply barrier, so the corpse exists with
the host's exact ids by the time the chain's action_end hash samples. The animation's
convertUnitToCorpse is display-only on the parallel client. Non-parallel paths (host,
classic co-op, PvP, single player) are byte-identical.

This test forces DETERMINISTIC alien-side in-chain deaths: it ambushes disarmed,
weakened soldiers onto tiles adjacent to the aliens, then closes the player side so
the alien AI shoots them down DURING the alien turn (an `ai`/`expl` chain, not a
boundary bleed-out). A slow client makes its replay lag past the host, which is what
armed the drift window. Under the strict-burnin lever (side-gates + corpsePending
skips OFF, so items/itemIdCtr compare at EVERY seq) it asserts, after the run:

  * corpseRemapArmed == 0            (window 2 - the corpseRemapPending mint->reconcile
                                      drift - NEVER arms on the new path: every corpse
                                      adopted the host ids AT CREATE)
  * items / itemIdCtr mismatch == 0  (no ai/expl straddle in the host's sync ring)
  * corpse (id, type) census identical on both machines
  * _itemId counters equal, full battle census equal

Non-vacuity: it asserts the alien AI actually minted several corpses during the
alien side (window 1 corpseReplayArmed grew, corpse count grew) - otherwise the
clean asserts would be trivially true.

RED (pre-item-3, same build's introspection): corpseRemapArmed>0 and items/itemIdCtr
mismatchCount>0 at kind ai/expl (measured: corpseRemapArmed=1, items=6, itemIdCtr=6).
The `unitsCore` residual this test does NOT assert on is the separate casualty-value
replay lag (chain-atomicity items 4-5), unaffected by mint-at-apply.

Run:  python tools/coop_test/test_parallel_corpse_mint.py [--seed N] [--slow-client MS]
                 [--hp N] [--sides N]
Exit 0 = corpse mint-at-apply covered (pass); 2 = a mint drift (fail).
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


def ambush(host, client, side_no):
    """Teleport a few weakened own-seat soldiers onto tiles adjacent to live aliens on
    BOTH machines, so the alien AI shoots them down during the alien turn (an in-chain
    `ai` death, not a boundary bleed-out). Capped at PAIRS per side: a mass ambush
    overwhelms the client's per-action casualty-value replay (the item 4-5 unitsCore
    residual) and latches the P2 tripwire on that, which is a DIFFERENT phase's defect;
    a handful of kills a side keeps the corpse-mint (item 3) signal clean of it.
    Returns the number of soldiers actually placed."""
    hb = bstate(host)
    aliens = [u for u in hb["units"] if u.get("faction") == 1 and not u.get("isOut")]
    soldiers = [u for u in hb["units"] if u.get("faction") == 0 and not u.get("isOut")]
    occupied = {(u["x"], u["y"], u["z"]) for u in hb["units"] if not u.get("isOut")}
    placed = 0
    # keep one soldier untouched so the mission cannot end mid-run
    for alien, sol in list(zip(aliens, soldiers[1:]))[:PAIRS]:
        p = adj_free(alien["x"], alien["y"], alien["z"], occupied)
        if not p:
            continue
        res = [gc.cmd({"cmd": "battle_teleport", "unit": sol["id"],
                       "x": p[0], "y": p[1], "z": p[2]}) for gc in (host, client)]
        if not all(r.get("moved") for r in res):
            continue
        occupied.add(p)
        for gc in (host, client):
            # HP moderate so a plasma hit KILLS but does not OVERKILL (an overkilled
            # unit mints no corpse - the assertions would go vacuous). visible so the
            # alien AI reliably engages it.
            gc.ok({"cmd": "battle_action", "action": "set_stat", "unit": sol["id"],
                   "health": HP, "visible": True})
        placed += 1
    print(f"  side {side_no}: {len(aliens)} aliens, ambushed {placed} soldier(s)")
    return placed


HP = 35
PAIRS = 3


def main():
    global HP, PAIRS
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=999983)
    ap.add_argument("--slow-client", type=int, default=300,
                    help="ms/frame on the client so its alien replay lags the host")
    ap.add_argument("--hp", type=int, default=35,
                    help="ambushed-soldier health (moderate: killed, not overkilled)")
    ap.add_argument("--sides", type=int, default=4)
    ap.add_argument("--pairs", type=int, default=3,
                    help="soldiers ambushed per side (kept small so item 4-5 casualty "
                         "noise does not swamp the item-3 corpse-mint signal)")
    args = ap.parse_args()
    HP = args.hp
    PAIRS = args.pairs

    cspeed = args.slow_client or SOAK.FAST_SPEED
    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": cspeed, "battleAlienSpeed": cspeed,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48884, make_user_dir("cmint_host", options=host_opts))
    client = GameClient("client", 48885, make_user_dir("cmint_client", options=client_opts))
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
        SOAK.enable_strict_burnin(host, client)

        b0 = bstate(client)
        remap0 = b0.get("corpseReplayArmed"), b0.get("corpseRemapArmed")
        corpses0 = len(corpses(client))
        assert b0.get("corpseRemapArmed") is not None, \
            "battle_state carries no corpseRemapArmed - the item-3 introspection is missing"
        print(f"  before: client corpseReplayArmed={remap0[0]} corpseRemapArmed={remap0[1]} "
              f"corpses={corpses0}")

        for side in range(args.sides):
            ambush(host, client, side)
            turn0 = bstate(host)["turn"]
            SOAK.close_side(host, client, 0, 1, turn0)
            time.sleep(3)
            cb = bstate(client)
            print(f"    -> after alien turn {turn0}: client corpseReplayArmed="
                  f"{cb.get('corpseReplayArmed')} corpseRemapArmed={cb.get('corpseRemapArmed')} "
                  f"corpses host={len(corpses(host))} client={len(corpses(client))}")

        # let the slow client fully drain before the final compare
        SOAK.settle_display(host, client)
        time.sleep(2)

        cb = bstate(client)
        sc = session.sync_check(host)
        buckets = sc["buckets"]
        straddle = [(m["kind"], m["bucket"], m.get("boundary"))
                    for m in sc.get("mismatches", []) if m["bucket"] in ("items", "itemIdCtr")]

        replay_arm = cb.get("corpseReplayArmed", 0)
        remap_arm = cb.get("corpseRemapArmed", 0)
        corpses_now = len(corpses(client))
        items_mm = buckets.get("items", {}).get("mismatchCount", 0)
        idctr_mm = buckets.get("itemIdCtr", {}).get("mismatchCount", 0)
        core_mm = buckets.get("unitsCore", {}).get("mismatchCount", 0)

        print("\n== VERDICT ==")
        print(f"  window-1 corpseReplayArmed = {replay_arm} (deaths queued this battle)")
        print(f"  window-2 corpseRemapArmed  = {remap_arm} (MUST be 0: mint adopts at create)")
        print(f"  items mismatchCount        = {items_mm}")
        print(f"  itemIdCtr mismatchCount    = {idctr_mm}")
        print(f"  unitsCore mismatchCount    = {core_mm}  (item 4-5 residual, NOT asserted)")
        print(f"  corpses minted this run    = {corpses_now - corpses0}")
        if straddle:
            print(f"  items/itemIdCtr STRADDLE   = {straddle}")

        assert sc.get("strictBurnIn") is True, "strict-burnin lever not engaged - run vacuous"

        # NON-VACUITY: the alien AI has to have actually minted corpses during the
        # alien side, or the clean asserts below are trivially true.
        if corpses_now - corpses0 < 3 or replay_arm < 3:
            fails.append(f"VACUOUS: only {corpses_now - corpses0} corpse(s) minted / "
                         f"{replay_arm} death(s) queued - the alien AI did not kill enough "
                         f"ambushed soldiers to exercise the mint (try --seed / --hp)")

        # THE FIX: window 2 never arms + no ai/expl straddle.
        if remap_arm != 0:
            fails.append(f"corpseRemapArmed={remap_arm} (expected 0): a corpse was minted "
                         f"with LOCAL ids on the parallel client - mint-at-apply did not run")
        if items_mm or idctr_mm:
            fails.append(f"items/itemIdCtr straddled the alien-side chain "
                         f"(items={items_mm}, itemIdCtr={idctr_mm}): {straddle}")

        # corpse ids + counters + census identical across machines.
        hc, cc = corpses(host), corpses(client)
        if hc != cc:
            fails.append(f"corpse censuses differ: host {hc} vs client {cc}")
        h, c = session.battle_checksum(host), session.battle_checksum(client)
        if h[0] != c[0]:
            fails.append(f"item-id counters differ: host {h[0]} vs client {c[0]}")
        if h[1] != c[1]:
            fails.append(f"battle censuses differ: host {h[1]} vs client {c[1]}")
        for gc, tag in ((host, "host"), (client, "client")):
            if TW.desync_seen(gc):
                fails.append(f"the PRD-P2 drift tripwire FIRED on the {tag}")
    except Exception as e:
        fails.append(f"[ERROR] {e}")
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    if fails:
        print("\n==== ITEM 3 corpse mint-at-apply: FAIL ====")
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("\n  PASS: corpse mint-at-apply COVERED - the parallel client minted every "
          "alien-side corpse from the host manifest at the after_unit_death apply, the "
          "corpseRemap drift window never armed, and items/itemIdCtr were strict-clean "
          "through every death; corpse ids + counters + census identical on both machines")
    sys.exit(0)


if __name__ == "__main__":
    main()
