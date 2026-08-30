"""ITEM 4 (chain-atomicity completion): no-reroll replay-authority regression lock.

THE INVARIANT: on the parallel non-host client the replayed combat path must perform
NO stateful re-roll of a victim's combat outcome. The victim's post-hit health, stun,
fatal wounds, per-side armor (and morale/energy/mana/tu) are HOST ABSOLUTES, carried by
`hit_unit`; the kill/knockout DISPOSITION is carried by `unit_death`/`after_unit_death`.
The client animates (hit flashes, damage popups) but its unit STATE for the chain-authored
`unitsCombat` bucket - kneeled, mind-controller id, and the six per-part fatal-wound
counters w0..w5 - changes only when those appliers land.

WHY IT ALREADY HOLDS (the dead-vs-live path table this test locks in): every client
combat-write entry point early-returns BEFORE it can write victim state on a parallel
non-host client -

  * BattleUnit::damage()        BattleUnit.cpp:1618   (getCoopStatic && !getHost) -> return 1
  * TileEngine::hitUnit()       TileEngine.cpp:3224   (getCoopStatic && !getHost) -> return true
      => TileEngine::explode() (ExplosionBState replay) reaches units ONLY via hitUnit,
         so the whole explosion damage loop is dead on the client too
      => TileEngine::hit()/hitCoop() (direct + reaction fire) likewise route through hitUnit
  * TileEngine::psiAttack()     TileEngine.cpp:5192   (getCoopStatic && !getHost && !PvP) -> return false
  * checkForCasualties() morale BattlescapeGame.cpp   (parallelTurnActive && !getHost) gate (9dadcb160)
  * UnitDieBState ctor          UnitDieBState.cpp:55   (isCoop && !getHost && !_coop_death) -> return
      => checkForCasualties' own UnitDieBState push is a no-op on the client; only the
         unit_death packet (coopDeath, _coop_death=true) drives the client's death.

So the client cannot roll wounds, cannot set the mind-controller id, cannot decide the
death on its display clock. This test forces heavy alien-side casualties - BOTH outright
kills AND wounded-but-alive survivors whose fatal wounds tick - on a deliberately SLOW
client whose replay lags the host, then proves the client never RE-DECIDES a `unitsCombat`
field:

  * HARD ASSERT: at SETTLE (the chain fully converged) a direct host<->client
    unit_stats_full diff shows every kneeled / mc / w0..w5 IDENTICAL. This is the re-roll
    detector: a locally re-decided value is a DISTINCT roll off the client's own RNG that
    PERSISTS past convergence, whereas a mere application lag is the host's own value
    arriving a beat late and has healed by settle.
  * REPORTED, not asserted: the per-alien-turn mid-flight diff and the sync_check
    unitsCombat mismatchCount. A hit_unit / kneel-packet APPLICATION lag (item-5, D-lite
    Option-B) can transiently stale a unitsCombat sample on some seeds and heal - that is a
    DIFFERENT phase's defect, so gating on it would conflate item 4 with item 5.

NON-VACUITY: it asserts the alien AI actually downed several ambushed soldiers AND that at
least one wounded survivor carried fatal wounds the host had rolled (so "wounds identical"
proves the client APPLIED the host wounds, not that no wounds ever existed).

RED (remove either the BattleUnit::damage or TileEngine::hitUnit early-return above, rebuild):
the client runs damage() and re-rolls the victim's wounds off its own RNG stream. This was
OBSERVED to leave a persistent settled divergence (unit w1 host=2 / client=0, unitsCombat
mismatchCount 12 at kind ai) - but note the catch is PROBABILISTIC: hit_unit re-applies the
host's absolute and usually HEALS the re-rolled value by settle, so a re-roll only trips the
settled compare when its last write beats hit_unit. The DETERMINISTIC guarantee is the
early-returns themselves (a re-roll is structurally impossible on a correct build); this
fixture is the CONVERGENCE + non-vacuity lock riding on top of that guarantee, not a
by-itself-deterministic re-roll detector.

The unitsCore (liveness/position) + items/itemIdCtr (corpse-mint) + terrain residuals this
test does NOT assert on are the separate death-display / one-step-behind replay lag =
chain-atomicity item 5. Because a re-roll and that lag both surface as transient, self-healing
unitsCombat straddles, the transient sync_check count cannot separate item 4 from item 5 -
which is exactly why this fixture gates on the DURABLE settled state, not the transient count.

Run:  python tools/coop_test/test_parallel_no_reroll.py [--seed N] [--slow-client MS]
                 [--kill-hp N] [--wound-hp N] [--sides N] [--pairs N]
Exit 0 = no-reroll authority intact (pass); 2 = a combat-value re-roll leaked (fail).
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

# unitsCombat = the chain-authored per-unit field set computeBattleHashes() sums into the
# unitsCombat bucket (SharedEcon.cpp): kneeled, mind-controller id, w0..w5. Health/stun/
# morale moved to unitsRegen (SEAM-9), so they are NOT part of the no-reroll strict compare.
COMBAT_FIELDS = ["kneeled", "mc", "w0", "w1", "w2", "w3", "w4", "w5"]
WOUND_FIELDS = ["w0", "w1", "w2", "w3", "w4", "w5"]


def bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def usf(gc):
    return {u["id"]: u for u in gc.ok({"cmd": "unit_stats_full"})["units"]}


def corpses(gc):
    return sorted((i["id"], i["type"]) for i in gc.ok({"cmd": "battle_items"})["items"]
                  if "CORPSE" in i["type"].upper())


def adj_free(ax, ay, az, occupied):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        p = (ax + dx, ay + dy, az)
        if p not in occupied:
            return p
    return None


def ambush(host, client, side_no, kill_hp, wound_hp, pairs):
    """Teleport weakened own-seat soldiers next to live aliens on BOTH machines so the
    alien AI shoots them during the alien turn. Alternate KILL health (a plasma hit kills)
    and WOUND health (survives the hit carrying fatal wounds) so the run exercises both the
    death appliers and the live-with-wounds hit_unit path. Returns soldiers placed."""
    hb = bstate(host)
    aliens = [u for u in hb["units"] if u.get("faction") == 1 and not u.get("isOut")]
    soldiers = [u for u in hb["units"] if u.get("faction") == 0 and not u.get("isOut")]
    occupied = {(u["x"], u["y"], u["z"]) for u in hb["units"] if not u.get("isOut")}
    placed = 0
    # keep one soldier untouched so the mission cannot end mid-run
    for idx, (alien, sol) in enumerate(list(zip(aliens, soldiers[1:]))[:pairs]):
        p = adj_free(alien["x"], alien["y"], alien["z"], occupied)
        if not p:
            continue
        res = [gc.cmd({"cmd": "battle_teleport", "unit": sol["id"],
                       "x": p[0], "y": p[1], "z": p[2]}) for gc in (host, client)]
        if not all(r.get("moved") for r in res):
            continue
        occupied.add(p)
        hp = kill_hp if (idx % 2 == 0) else wound_hp
        for gc in (host, client):
            gc.ok({"cmd": "battle_action", "action": "set_stat", "unit": sol["id"],
                   "health": hp, "visible": True})
        placed += 1
    print(f"  side {side_no}: {len(aliens)} aliens, ambushed {placed} soldier(s)")
    return placed


def combat_field_diffs(host, client):
    """Direct host<->client per-unit diff of the unitsCombat field set."""
    h, c = usf(host), usf(client)
    diffs = []
    host_max_wounds = 0
    for uid in sorted(set(h) | set(c)):
        hu, cu = h.get(uid), c.get(uid)
        if not hu or not cu:
            continue
        host_max_wounds = max(host_max_wounds, sum(hu.get(f, 0) for f in WOUND_FIELDS))
        for f in COMBAT_FIELDS:
            if hu.get(f) != cu.get(f):
                diffs.append((uid, f, hu.get(f), cu.get(f)))
    return diffs, host_max_wounds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=999983)
    ap.add_argument("--slow-client", type=int, default=300,
                    help="ms/frame on the client so its alien replay lags the host")
    ap.add_argument("--kill-hp", type=int, default=35,
                    help="health for the KILLED half (a plasma hit kills, not overkills)")
    ap.add_argument("--wound-hp", type=int, default=250,
                    help="health for the WOUNDED-ALIVE half (survives carrying fatal wounds)")
    ap.add_argument("--sides", type=int, default=4)
    ap.add_argument("--pairs", type=int, default=8)
    args = ap.parse_args()

    cspeed = args.slow_client or SOAK.FAST_SPEED
    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": cspeed, "battleAlienSpeed": cspeed,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48884, make_user_dir("nrr_host", options=host_opts))
    client = GameClient("client", 48885, make_user_dir("nrr_client", options=client_opts))
    for gc in (host, client):
        SOAK.write_battle_fixture(gc.user_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT
    PE.PORT = PORT

    fails = []
    downed_seen = 0
    host_wounds_seen = 0
    midflight_diffs = []
    try:
        TW.bring_up_battle(host, client, seed=args.seed)
        for gc in (host, client):
            gc.ok({"cmd": "set_seed", "seed": args.seed})
        assert bstate(host)["activeSync"] is True and bstate(client)["activeSync"] is False, \
            "host must own the battle simulation, client must be the replay peer"
        SOAK.enable_strict_burnin(host, client)

        alive0 = len([u for u in bstate(host)["units"]
                      if u.get("faction") == 0 and not u.get("isOut")])
        corpses0 = len(corpses(host))

        for side in range(args.sides):
            ambush(host, client, side, args.kill_hp, args.wound_hp, args.pairs)
            turn0 = bstate(host)["turn"]
            SOAK.close_side(host, client, 0, 1, turn0)
            time.sleep(2)
            # MID-FLIGHT WINDOW (slow client still draining its alien replay): a diff HERE
            # is REPORTED, not failed - a hit_unit/kneel-packet application LAG (item-5,
            # D-lite Option-B) can transiently stale a unitsCombat field here and heal by
            # settle. The re-roll DETECTOR is the SETTLED compare below: a locally re-decided
            # value is a DISTINCT roll off the client's own RNG that PERSISTS past convergence
            # (proven: with the damage()/hitUnit early-return removed the diff survives settle),
            # whereas a lag is the host's own value arriving a beat late.
            diffs, hmax = combat_field_diffs(host, client)
            host_wounds_seen = max(host_wounds_seen, hmax)
            tag = f"mid-turn{turn0}"
            if diffs:
                midflight_diffs.append((tag, diffs))
                print(f"  {tag}: unitsCombat mid-flight lag (heals by settle?) {diffs}")
            else:
                print(f"  {tag}: unitsCombat identical (host max fatal-wound total={hmax})")

        SOAK.settle_display(host, client)
        time.sleep(2)

        # SETTLED compare - the authoritative no-reroll detector. At convergence the client
        # must hold the host's EXACT unitsCombat fields. A re-decided value (distinct local
        # roll) persists here; a mid-flight application lag has healed.
        settled_diffs, hmax = combat_field_diffs(host, client)
        host_wounds_seen = max(host_wounds_seen, hmax)

        downed_seen = (alive0 - len([u for u in bstate(host)["units"]
                                     if u.get("faction") == 0 and not u.get("isOut")]))
        corpses_now = len(corpses(host))

        sc = session.sync_check(host)
        buckets = sc["buckets"]
        assert sc.get("strictBurnIn") is True, "strict-burnin lever not engaged - run vacuous"
        combat_mm = buckets.get("unitsCombat", {}).get("mismatchCount", 0)
        combat_samples = [(m["kind"], m.get("boundary")) for m in sc.get("mismatches", [])
                          if m["bucket"] == "unitsCombat"]

        print("\n== VERDICT ==")
        print(f"  soldiers downed this run   = {downed_seen}")
        print(f"  corpses minted (host)      = {corpses_now - corpses0}")
        print(f"  max host fatal-wound total = {host_wounds_seen} (wounded-alive coverage)")
        print(f"  SETTLED unitsCombat diffs  = {settled_diffs or 'NONE'}   (MUST be empty)")
        print(f"  mid-flight lag diffs seen  = {midflight_diffs or 'none'}   (transient, item-5)")
        print(f"  unitsCombat mismatchCount  = {combat_mm} (report; transient item-5 lag can "
              f"bump this - the settled compare is the re-roll gate) samples={combat_samples}")
        for b in ("unitsCore", "items", "itemIdCtr", "terrain", "saveBlob", "unitsRegen"):
            print(f"  (item-5/carve-out) {b:11s} mismatchCount="
                  f"{buckets.get(b, {}).get('mismatchCount', 0)}")

        # NON-VACUITY
        if downed_seen < 3:
            fails.append(f"VACUOUS: only {downed_seen} soldier(s) downed - the alien AI did "
                         f"not kill enough ambushed soldiers to exercise the death appliers")
        if host_wounds_seen < 1:
            fails.append(f"VACUOUS: no unit ever carried a host-rolled fatal wound - the "
                         f"wounded-alive w0..w5 apply path was never exercised (try --wound-hp)")

        # THE INVARIANT: no PERSISTENT unitsCombat divergence at convergence. A locally
        # re-rolled wound/kneel/mc is a distinct value that survives settle (proven RED by
        # disabling the BattleUnit::damage / TileEngine::hitUnit early-return); the client
        # holding the host's exact values here proves it applied, never re-decided.
        if settled_diffs:
            fails.append(f"unitsCombat FIELD diverged AT SETTLE (uid,field,host,client): "
                         f"{settled_diffs} - a combat value was re-decided locally instead of "
                         f"applied from hit_unit/unit_death and did NOT converge")

        # NOT asserted: the sync_check unitsCombat mismatchCount and the PRD-P2 drift tripwire.
        # A mass ambush drives the client's per-action death-display replay behind the host, so
        # a hit_unit/kneel-packet APPLICATION lag can transiently stale a unitsCombat sample
        # and latch the wire on the item-5 unitsCore(liveness)/items(corpse-mint)/terrain
        # residual - a DIFFERENT phase's defect that HEALS (same reason test_parallel_corpse_mint
        # caps its pairs). This test isolates the no-reroll invariant: the client never holds a
        # re-decided value once the chain converges.
        tw = {t: TW.desync_seen(gc) for gc, t in ((host, "host"), (client, "client"))}
        print(f"  (item-5) P2 drift tripwire (unitsCore/items/terrain lag, not asserted): {tw}")
    except Exception as e:
        fails.append(f"[ERROR] {e}")
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    if fails:
        print("\n==== ITEM 4 no-reroll authority: FAIL ====")
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("\n  PASS: no-reroll authority intact - across every alien-side casualty (kills + "
          "wounded-alive survivors) the parallel replay client CONVERGED to the host's exact "
          "kneeled/mind-controller/w0..w5 (applied from hit_unit/unit_death), leaving no "
          "re-decided combat value in the durable settled state")
    sys.exit(0)


if __name__ == "__main__":
    main()
