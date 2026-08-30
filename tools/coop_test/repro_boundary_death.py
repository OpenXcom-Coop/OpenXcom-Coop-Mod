"""SESSION F: boundary-death corpse-mint COVERAGE regression test (#74).

Proves the PRODUCT boundary-death corpse mint is COVERED by the after_unit_death
P4 id-manifest and stays in perfect lockstep across the two machines - isolated
from the battle_give harness confound. Units are given a lethal condition with
the mint-FREE set_stat lever (health/fire/fatalWounds - NO BattleItem created),
then a full turn is closed so they bleed/burn to death in prepareNewTurn at a
boundary; each corpse is the SOLE mint in flight.

Asserts, after the boundary:
  - host and client hold IDENTICAL corpse (id, type) censuses
  - their SavedBattleGame::_itemId counters are EQUAL
  - NO items/itemIdCtr straddle was recorded in the host's sync-check ring

Session F finding: this is CLEAN across player/alien, single/multi, bleed/fire,
and a lagging slow client. The residual items/itemIdCtr drift the soak sees is
the ALIEN-side display window (ai/expl), not this boundary path.

OVERKILL NOTE: set_stat/fatalWounds wounds EVERY body part, so `--wounds 6` = 36
total bleed, which drives health past -stats.health*armor.getOverKill() (~-15 for
a rookie) -> UnitDieBState._overKill -> NO corpse minted (the assertions would go
vacuous). Use a GENTLE dose (`--wounds 1` = 6 total) for a corpse-producing death.

Run:  python tools/coop_test/repro_boundary_death.py [--seed N] [--faction 0|1]
                 [--victims N] [--fire N] [--slow-client MS]
Exit 0 = covered (pass); 2 = a boundary-death drift (fail).
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

PORT = "47991"


def bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def corpses(gc):
    return sorted((i["id"], i["type"]) for i in gc.ok({"cmd": "battle_items"})["items"]
                  if "CORPSE" in i["type"].upper())


def snap(tag, host, client):
    h = session.battle_checksum(host)
    c = session.battle_checksum(client)
    print(f"  [{tag}] itemIdCtr host={h[0]} client={c[0]}"
          f"{'  <-- DRIFT' if h[0] != c[0] else ''}")
    print(f"  [{tag}] census   host={h[1]} client={c[1]}"
          f"{'  <-- DRIFT' if h[1] != c[1] else ''}")
    print(f"  [{tag}] corpses host  ={corpses(host)}")
    print(f"  [{tag}] corpses client={corpses(client)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=424242)
    ap.add_argument("--wounds", type=int, default=1)
    ap.add_argument("--victims", type=int, default=4)
    ap.add_argument("--faction", type=int, default=0, help="0=soldiers, 1=aliens")
    ap.add_argument("--fire", type=int, default=0, help="set fire N (burn-out death) instead of wounds")
    ap.add_argument("--slow-client", type=int, default=0,
                    help="ms/frame on the client so its death replay lags past sidestart")
    args = ap.parse_args()

    cspeed = args.slow_client or SOAK.FAST_SPEED
    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": cspeed, "battleAlienSpeed": cspeed,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48880, make_user_dir("bnd_host", options=host_opts))
    client = GameClient("client", 48881, make_user_dir("bnd_client", options=client_opts))
    for gc in (host, client):
        SOAK.write_battle_fixture(gc.user_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT; PE.PORT = PORT
    try:
        TW.bring_up_battle(host, client, seed=args.seed)
        for gc in (host, client):
            gc.ok({"cmd": "set_seed", "seed": args.seed})
        assert bstate(host)["activeSync"] is True and bstate(client)["activeSync"] is False

        # pick N live units of the target faction (all about to die at a boundary)
        pool = [u for u in bstate(host)["units"]
                if u.get("faction") == args.faction and not u.get("isOut")]
        keep = 0 if args.faction == 1 else 1  # keep >=1 soldier alive so battle survives
        victims = pool[:max(1, min(args.victims, len(pool) - keep))]
        print(f"victims: {[v['id'] for v in victims]} (faction {args.faction}, of {len(pool)})")
        print("\n== BEFORE (both machines synced?) ==")
        snap("before", host, client)

        # mint-free lethal condition on BOTH machines, all victims
        for victim in victims:
            req = {"cmd": "battle_action", "action": "set_stat", "unit": victim["id"], "health": 1}
            if args.fire:
                req["fire"] = args.fire
            else:
                req["fatalWounds"] = args.wounds
            for gc, tag in ((host, "host"), (client, "client")):
                r = gc.ok(dict(req))
            print(f"    victim {victim['id']}: health=1 "
                  f"{'fire=%d' % args.fire if args.fire else 'wounds=%d' % r.get('fatalWounds')}")
        victim = victims[0]

        turn0 = bstate(host)["turn"]
        print(f"\n== closing turn {turn0} (soldier bleeds out at neutral->player) ==")
        SOAK.close_side(host, client, 0, 1, turn0)
        # let the (possibly slow) client drain its death replay + report the sidestart hash
        sc = session.sync_check(host)
        deadline = time.time() + (40 if args.slow_client else 6)
        while time.time() < deadline:
            sc = session.sync_check(host)
            if any(m["bucket"] in ("items", "itemIdCtr") for m in sc.get("mismatches", [])):
                break
            time.sleep(1.0)
        print("\n== AFTER the boundary ==")
        snap("after", host, client)
        v = next((u for u in bstate(host)["units"] if u["id"] == victim["id"]), None)
        print(f"  victim isOut host={v.get('isOut') if v else '?'} "
              f"health={v.get('health') if v else '?'}")

        print("\n== host sync-check mismatch ring ==")
        ms = sc.get("mismatches", [])
        for m in ms:
            print(f"    seq={m['seq']}{' boundary' if m.get('boundary') else ''} "
                  f"kind={m['kind']} bucket={m['bucket']}")
        buckets = sc["buckets"]
        for b in ("items", "itemIdCtr", "saveBlob"):
            if b in buckets:
                print(f"  bucket {b}: mismatchCount={buckets[b]['mismatchCount']} "
                      f"compares={buckets[b].get('compares')}")
        straddle = [m for m in ms if m["bucket"] in ("items", "itemIdCtr")]

        h, c = session.battle_checksum(host), session.battle_checksum(client)
        hcorp, ccorp = corpses(host), corpses(client)
        fails = []
        if not hcorp:
            fails.append("no corpse minted (overkill? use a gentler --wounds) - test vacuous")
        if hcorp != ccorp:
            fails.append(f"corpse censuses differ: host {hcorp} vs client {ccorp}")
        if h[0] != c[0]:
            fails.append(f"item-id counters differ: host {h[0]} vs client {c[0]}")
        if straddle:
            fails.append(f"items/itemIdCtr straddled at "
                         f"{[(m['kind'], m.get('boundary')) for m in straddle]}")
        print("\n== VERDICT ==")
        if fails:
            for f in fails:
                print(f"  FAIL {f}")
            rc = 2
        else:
            print("  PASS: boundary-death corpse mint COVERED - corpse ids + counter "
                  "identical on both machines, no items/itemIdCtr straddle")
            rc = 0
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass
    sys.exit(rc)


if __name__ == "__main__":
    main()
