"""Parallel battlescape "atomic unit death" rework, Phase 2b: the CLIENT atomic
apply of `unit_casualty` + the pump wiring + the same-build RED lever.

THE MECHANISM UNDER TEST. Phase 2a made the parallel HOST ship one
`unit_casualty` packet per casualty (UnitDieBState::deinit) instead of the
legacy `unit_death` (init) / `after_unit_death` (deinit) pair. Phase 2b makes
the parallel CLIENT actually consume it:

  * connectionTCP.cpp's `unit_casualty` handler: unit lookup, the rank-2
    per-unit state watermark (BattleUnit::coopStateAccept), abortPathCoop, the
    bystander-morale apply, then dispatches to...
  * BattlescapeGame::coopApplyCasualty: the ordered, ATOMIC apply of every
    field on the packet - stats, position, kill attribution, status, the
    corpse/world mutation keyed on the host's corpse-mint mode (0=on-tile,
    1=carried, 2=overKill, 3=none/respawn) - all in ONE pass on the bookkeeping
    clock, so the previous "unit_death now, after_unit_death later" straddle
    (the transient window a mid-chain census could catch the victim standing on
    stale pre-hit stats or fully dead with no corpse yet) cannot happen. A
    CoopDeathGhost STUB is queued at the end (Phase 2c wires the actual death
    ANIMATION off it; here the corpse/kit simply appear complete at apply).

  * The pump: `unit_casualty` joins the seq-gated chain-outcome whitelist
    (coopIsChainOutcomePacket) and the alien/neutral-side decoupled world
    carrier set (coopDecoupledWorldCarrier) exactly like its legacy
    predecessors - so an ALIEN-side casualty applies at packet-apply despite a
    busy display, while a PLAYER-side casualty waits for display idle (the
    ordered gate) and applies after the client's own shot replay.

  * The RED lever (`atomic_death_disable`, same build): the HOST falls back to
    sending the legacy unit_death/after_unit_death trio, and the CLIENT's
    legacy-handler early-returns stand down so it processes the trio again -
    reproducing the pre-atomic transient straddle for comparison.

SCENARIO. Explicit, single-target casualties are staged against SOLDIERS
(never aliens) while it is still the FIRST PLAYER SIDE, so they exercise the
ORDERED (non-decoupled) apply path and never compete with the alien-side
ambush for the fixture's scarce (>=3) hostile population:

  * a PLAYER-SIDE kill    - a weakened soldier shot dead by a squadmate
                             (mode 0, on-tile corpse mint).
  * an OVERKILL            - `kill_unit_real`'s +1000 raw damage on a soldier
                             (mode 2, no corpse - the wire-level effect a
                             blaster/heavy launcher produces is identical:
                             `_overKill` true, no corpse minted. Substituted
                             for a live blaster shot, which is fragile terrain-
                             dependent staging orthogonal to what this phase
                             tests - the atomic apply of the resulting
                             packet, not blast mechanics).
  * a KNOCKOUT              - a stun-rod melee hit (mode 0, corpse mint,
                             STATUS_UNCONSCIOUS instead of DEAD).

Then several ALIEN-side ambush kills (test_parallel_alien_death_decouple's
`ambush` - weakened soldiers placed next to live aliens, killed by the alien
AI during the alien turn) exercise the DECOUPLED apply path under
--strict-burnin (the five buckets compare at EVERY seq, not just side-gated
boundaries).

DEBRIEF-IDENTICAL SUBSTITUTE. A full mission-ending DebriefingState compare
(see test_coop_debrief_sync.py) needs a dedicated custom-ruleset battle and
routinely costs well over a minute on its own - outside this phase's <180s /
2-3-alien-turn budget, and orthogonal to what Phase 2b is responsible for
(coopApplyCasualty applies obj["killedBy"]/["murdererId"] verbatim; it does
not compute DebriefingState's score). DebriefingState's STR_ALIENS_KILLED tally
is `oldFaction==HOSTILE && killedBy()==PLAYER` over each machine's own save, so
identical per-unit (status, killedBy, murdererId) attribution on both machines
for every casualty IS the invariant a debrief compare would be reading -
that is what is asserted here instead.

Asserts (same build, two separate invocations - "ONCE green, ONCE red"):
  GREEN (default, atomic path ON):
    - the five buckets (terrain/unitsCore/items/itemIdCtr/unitsCombat) stay 0
      through the whole run (strict-burnin: every seq, not just boundaries)
    - casualtiesApplied (client) >= midSideDeaths (host) - every MID-SIDE host
      casualty produced an applied `unit_casualty` (midSideDeaths is a floor:
      it deliberately excludes boundary-phase deaths, e.g. a fatally-wounded
      ambush victim bleeding out at the side close, which also ship and must
      apply their own `unit_casualty`) - and casualtiesRejected==0 (the rank-2
      watermark never rejected a live casualty on this clean run)
    - corpse (id, type) census + itemIdCounter/battleCensus identical
    - corpseReplayArmed/corpseRemapArmed on the client are UNCHANGED from their
      pre-battle value (0) - the atomic path never arms those legacy mint-at-
      apply windows
    - per-unit (status, killedBy, murdererId) attribution identical on both
      machines for every casualty (the debrief-identical substitute)
    - the three staged outcomes (player-kill DEAD/mode 0, overkill DEAD/mode 2
      i.e. no corpse, knockout UNCONSCIOUS/mode 0) actually happened
  RED (--red, `atomic_death_disable` on BOTH machines -> legacy trio):
    - casualtiesApplied never moves past its pre-lever baseline (a battle-start
      hidden-explosion casualty, if any, can legitimately apply before the
      lever engages - see the baseline capture in main()) - the new handler
      never runs for anything staged or ambushed after that point
    - the five buckets show a non-zero straddle SOMEWHERE in the run (the
      known pre-atomic transient - retry-tolerant: reported as a sum over the
      whole run rather than asserted at a specific seq)

Run:  python tools/coop_test/test_parallel_atomic_death.py [--seed N]
                 [--slow-client MS] [--hp N] [--pairs N] [--sides N] [--red]
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
import test_parallel_alien_death_decouple as AD

PORT = "48008"
FIVE = ("terrain", "unitsCore", "items", "itemIdCtr", "unitsCombat")

STATUS_DEAD = 6
STATUS_UNCONSCIOUS = 7
FACTION_PLAYER = 0
FACTION_HOSTILE = 1


def bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def parallel(gc):
    return gc.cmd({"cmd": "parallel_state"})


def corpses(gc):
    return sorted((i["id"], i["type"]) for i in gc.ok({"cmd": "battle_items"})["items"]
                  if "CORPSE" in i["type"].upper())


def units_by_id(gc):
    return {u["id"]: u for u in bstate(gc)["units"]}


def attribution(gc):
    """{unit id: (status, killedBy, murdererId)} for every unit that isOut() -
    the per-unit inputs DebriefingState's kill tally reads."""
    return {u["id"]: (u["status"], u.get("killedBy"), u.get("murdererId"))
            for u in bstate(gc)["units"] if u.get("isOut")}


def live_soldiers(gc):
    return [u for u in bstate(gc)["units"]
            if u.get("faction") == FACTION_PLAYER and not u.get("isOut")]


def find_adjacent_pair(units):
    """Two units from `units` already standing next to each other (Chebyshev
    distance 1, same z), or None. The starting squad is cramped around the
    dropship, so a melee scenario is staged against an EXISTING neighbour
    rather than by teleporting one in - trying to free up an adjacent tile in
    that cluster routinely fails (every neighbour already occupied)."""
    for i, a in enumerate(units):
        for b in units[i + 1:]:
            if a["z"] == b["z"] and max(abs(a["x"] - b["x"]), abs(a["y"] - b["y"])) == 1:
                return a["id"], b["id"]
    return None


def give_both(host, client, uid, item, ammo=None):
    wid = None
    for gc in (host, client):
        req = {"cmd": "battle_give", "unit": uid, "item": item,
               "slot": "right", "clear_hands": True}
        if ammo:
            req["ammo"] = ammo
        r = gc.ok(req)
        wid = r["weaponId"]
    return wid


def poll(fn, timeout, interval=0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = fn()
        if v:
            return v
        time.sleep(interval)
    return fn()


# ---- the three explicit, single-target casualties (all against SOLDIERS, all
# staged while it is still the FIRST PLAYER SIDE - see module docstring) ------

def stage_player_kill(host, client, used, tries=3):
    """A soldier shot dead by a squadmate: an ordinary death, applied on the
    ORDERED (non-decoupled) gate because it happens while side==FACTION_PLAYER
    (whether or not the shot happens to overkill does not matter here - the
    overkill code path is exercised deterministically, and separately, by
    stage_overkill). No teleport: the starting squad is clustered near the
    dropship, well within a heavy plasma's range/LOS of itself; a single aimed
    shot is decisive so no rapid re-fire into a chain still closing is needed
    (each retry - only for a miss - waits for both machines to fully settle
    first). `used` is a set of unit ids already claimed by another staged
    scenario - never reused. Returns the victim's unit id, or None if the
    fixture could not stage it."""
    live = [u for u in live_soldiers(host) if u["id"] not in used]
    if len(live) < 2:
        return None
    shooter, victim = live[0]["id"], live[1]["id"]
    used.add(shooter); used.add(victim)
    wid = give_both(host, client, shooter, "STR_HEAVY_PLASMA", "STR_HEAVY_PLASMA_CLIP")
    for _ in range(tries):
        vu = next((u for u in bstate(host)["units"] if u["id"] == victim), None)
        if vu is None or vu.get("isOut"):
            return victim
        host.cmd({"cmd": "battle_action", "action": "set_stat", "unit": shooter,
                  "stat": "tu", "value": 200})
        r = host.cmd({"cmd": "battle_fire", "unit": shooter, "mode": "aimed",
                      "weapon_id": wid, "tu": 200, "target": victim})
        if not r.get("ok"):
            print(f"  DEBUG player-kill: shot failed: {r.get('error')}")
        SOAK.settle_display(host, client, timeout=30)
    vu = next((u for u in bstate(host)["units"] if u["id"] == victim), None)
    return victim if (vu and vu.get("isOut")) else None


def stage_overkill(host, used):
    """`kill_unit_real` on a soldier: +1000 raw AP damage always overkills
    (mode 2, no corpse) - the wire-level effect a blaster/heavy launcher
    produces on the victim's `unit_casualty` is identical; see module
    docstring for why a live blast is not staged here. Returns the victim id,
    or None."""
    live = [u for u in live_soldiers(host) if u["id"] not in used]
    if len(live) < 1:
        return None
    victim = live[0]["id"]
    used.add(victim)
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": victim})
    if victim not in r.get("killed", []):
        return None
    return victim


def stage_knockout(host, client, used, tries=5):
    """A stun-rod melee hit against an EXISTING neighbour in the starting
    cluster (see find_adjacent_pair): STR_STUN_ROD deals ~0 real damage, only
    stun, so the victim goes UNCONSCIOUS (mode 0, corpse mint) rather than
    DEAD. Returns the victim id, or None."""
    pair = find_adjacent_pair([u for u in live_soldiers(host) if u["id"] not in used])
    if not pair:
        return None
    striker, victim = pair
    used.add(striker); used.add(victim)
    wid = give_both(host, client, striker, "STR_STUN_ROD")
    for _ in range(tries):
        vu = next((u for u in bstate(host)["units"] if u["id"] == victim), None)
        if vu is None or vu.get("isOut"):
            break
        host.cmd({"cmd": "battle_action", "action": "set_stat", "unit": striker,
                  "stat": "tu", "value": 100})
        r = host.cmd({"cmd": "battle_fire", "unit": striker, "mode": "hit",
                      "weapon_id": wid, "tu": 100, "target": victim})
        if not r.get("ok"):
            print(f"  DEBUG knockout: hit failed: {r.get('error')}")
            break
        SOAK.settle_display(host, client, timeout=30)
        vu2 = next((u for u in bstate(host)["units"] if u["id"] == victim), None)
        if vu2 and vu2.get("isOut"):
            return victim
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=13371337)
    ap.add_argument("--slow-client", type=int, default=300,
                    help="ms/frame on the client so its alien replay lags the host far "
                         "enough to exercise the decoupled apply while the display is busy. "
                         "NOTE for --red: a bigger cluster (higher --pairs/--sides) or a "
                         "slower client reproduces the pre-atomic straddle more reliably, but "
                         "far enough over and it also opens the SEPARATE, already-documented "
                         "'casualty-value replay under a heavy cluster' residual (see "
                         "test_parallel_alien_death_decouple.py / test_parallel_corpse_mint.py) "
                         "- a different, pre-existing defect this phase does not touch. The "
                         "GREEN defaults below are chosen to stay clear of that residual; a RED "
                         "run can safely turn the intensity up (e.g. --slow-client 900 --pairs "
                         "3 --sides 3) since RED does not need bucket-clean, only non-vacuous.")
    ap.add_argument("--hp", type=int, default=35,
                    help="ambushed-soldier health (moderate: killed, not overkilled)")
    ap.add_argument("--pairs", type=int, default=2,
                    help="soldiers ambushed per alien side")
    ap.add_argument("--sides", type=int, default=2,
                    help="alien sides to run the ambush through")
    ap.add_argument("--red", action="store_true",
                    help="RED: set parallel_state {atomic_death_disable:true} on BOTH "
                         "machines - the host falls back to unit_death/after_unit_death "
                         "and the client processes the legacy trio again")
    args = ap.parse_args()

    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": args.slow_client, "battleAlienSpeed": args.slow_client,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48940, make_user_dir("atomicdeath_host", options=host_opts))
    client = GameClient("client", 48941, make_user_dir("atomicdeath_client", options=client_opts))
    for gc in (host, client):
        SOAK.write_battle_fixture(gc.user_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT
    PE.PORT = PORT
    fails = []
    cas_applied = cas_rejected = 0
    mid_deaths = 0
    try:
        TW.bring_up_battle(host, client, seed=args.seed)
        for gc in (host, client):
            gc.ok({"cmd": "set_seed", "seed": args.seed})
        assert bstate(host)["activeSync"] is True and bstate(client)["activeSync"] is False, \
            "host must own the battle simulation, client must be the replay peer"

        # parallel_state must carry the Phase 2b fields or the exe predates this build.
        pc = parallel(client)
        for f in ("casualtiesApplied", "casualtiesRejected", "atomicDeathDisable"):
            assert f in pc, (
                f"parallel_state carries no `{f}` - bin/x64/Release/OpenXcom.exe predates "
                f"the Phase 2b build; rebuild it (serial, MP=false). fields: {sorted(pc)}")

        SOAK.enable_strict_burnin(host, client)

        if args.red:
            for gc, tag in ((host, "host"), (client, "client")):
                gc.cmd({"cmd": "parallel_state", "atomic_death_disable": True})
                r = parallel(gc)
                assert r.get("atomicDeathDisable") is True, f"{tag}: lever did not engage: {r}"
            print("== RED: atomic_death_disable ON on BOTH machines (legacy trio) ==")
        else:
            print("== GREEN: atomic unit_casualty path ON ==")

        # Baseline AFTER the lever engages (RED) / at the same point (GREEN): a
        # battle's ctor runs its own boundary-phase checkForCasualties pass for
        # battle-start hidden explosions (UFO power source etc.) during bring-up,
        # BEFORE the harness has a chance to touch the lever - so on a RED run that
        # one casualty can legitimately apply via the (still default-on) atomic path.
        # The RED assertion below reads the DELTA from this baseline, not the raw
        # counter, so that harmless pre-existing casualty never pollutes it.
        cas_baseline = parallel(client).get("casualtiesApplied", 0)

        b0 = bstate(client)
        corpse_arm0 = b0.get("corpseReplayArmed"), b0.get("corpseRemapArmed")
        corp0 = len(corpses(client))
        assert b0.get("corpseRemapArmed") is not None, \
            "battle_state carries no corpseRemapArmed - the item-3 introspection is missing"

        print("\n-- staging the three explicit player-side casualties (side==PLAYER) --")
        used_soldiers = set()
        pk_id = stage_player_kill(host, client, used_soldiers)
        ok_id = stage_overkill(host, used_soldiers)
        SOAK.settle_display(host, client, timeout=30)
        ko_id = stage_knockout(host, client, used_soldiers)
        print(f"  player-kill victim={pk_id} overkill victim={ok_id} knockout victim={ko_id}")

        SOAK.settle_display(host, client, timeout=30)
        time.sleep(2)
        outcomes = {}
        for tag, uid, want_status in (("player-kill", pk_id, STATUS_DEAD),
                                       ("overkill", ok_id, STATUS_DEAD),
                                       ("knockout", ko_id, STATUS_UNCONSCIOUS)):
            if uid is None:
                outcomes[tag] = None
                continue
            hu = units_by_id(host).get(uid, {})
            cu = poll(lambda: units_by_id(client).get(uid) if
                      units_by_id(client).get(uid, {}).get("isOut") else None, 30)
            cu = cu or units_by_id(client).get(uid, {})
            outcomes[tag] = (hu.get("status"), cu.get("status"))
            print(f"  {tag}: unit {uid} status host={hu.get('status')} "
                  f"client={cu.get('status')} (want {want_status})")

        print("\n-- alien-side ambush (decoupled apply path) --")
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
        buckets = {n: sc["buckets"].get(n, {}).get("mismatchCount", 0) for n in FIVE}
        total = sum(buckets.values())
        ph = parallel(host)
        pcl = parallel(client)
        cas_applied = pcl.get("casualtiesApplied", 0)
        cas_rejected = pcl.get("casualtiesRejected", 0)
        mid_deaths = ph.get("midSideDeaths", 0)
        cb = bstate(client)
        corpse_arm1 = cb.get("corpseReplayArmed"), cb.get("corpseRemapArmed")
        ah, ac = attribution(host), attribution(client)
        attr_bad = {uid: (ah.get(uid), ac.get(uid)) for uid in set(ah) | set(ac)
                    if ah.get(uid) != ac.get(uid)}

        print("\n== VERDICT ==")
        print(f"  five-bucket = {buckets} (sum {total})")
        print(f"  casualtiesApplied={cas_applied} (pre-lever baseline={cas_baseline}) "
              f"casualtiesRejected={cas_rejected} midSideDeaths(host)={mid_deaths}")
        print(f"  corpseReplayArmed/RemapArmed: pre-battle={corpse_arm0} now={corpse_arm1}")
        print(f"  corpses grown by {len(corpses(client)) - corp0}")
        if attr_bad:
            print(f"  attribution mismatches: {attr_bad}")

        if args.red:
            if total == 0:
                fails.append("VACUOUS RED: the legacy-trio run produced ZERO five-bucket "
                             "mismatches - the pre-atomic straddle was not reproduced "
                             "(try a slower --slow-client / another --seed)")
            else:
                print(f"  RED straddle reproduced (sum {total}) over the whole run.")
            if cas_applied != cas_baseline:
                fails.append(f"RED: expected casualtiesApplied to stay at its pre-lever "
                             f"baseline ({cas_baseline}) - the atomic handler must never run "
                             f"under atomic_death_disable - got {cas_applied}")
        else:
            for tag, uid, want_status in (("player-kill", pk_id, STATUS_DEAD),
                                           ("overkill", ok_id, STATUS_DEAD),
                                           ("knockout", ko_id, STATUS_UNCONSCIOUS)):
                if uid is None:
                    fails.append(f"VACUOUS: could not stage the {tag} scenario "
                                 f"(too few live soldiers in the fixture)")
                    continue
                hs, cs = outcomes[tag]
                if hs != want_status or cs != want_status:
                    fails.append(f"{tag}: expected status {want_status} on both machines, "
                                 f"got host={hs} client={cs}")

            if mid_deaths < 3:
                fails.append(f"VACUOUS: only {mid_deaths} host death(s) - the ambush and/or "
                             f"the staged casualties did not produce enough deaths to "
                             f"exercise the atomic apply (try --seed/--hp/--pairs)")
            # `midSideDeaths` is a FLOOR, not the total: it deliberately excludes
            # boundary-phase deaths (a fatally-wounded ambush victim bleeding out at
            # the side close, still seq-0/bnd:true - see UnitDieBState::init), and
            # those ALSO ship (and must apply) a `unit_casualty`. So every mid-side
            # death must have been applied, but casualtiesApplied can legitimately
            # exceed midSideDeaths by however many boundary deaths this run had.
            if cas_applied < mid_deaths:
                fails.append(f"casualtiesApplied ({cas_applied}) < host mid-side death count "
                             f"midSideDeaths ({mid_deaths}) - the client did not apply every "
                             f"mid-side unit_casualty")
            if cas_rejected:
                fails.append(f"casualtiesRejected={cas_rejected} on the atomic path - the "
                             f"rank-2 watermark rejected a live casualty (should be 0 on a "
                             f"clean, non-duplicated run)")
            bad = {b: v for b, v in buckets.items() if v > 0}
            if bad:
                fails.append(f"five-bucket mismatch {bad} FIRED on the atomic path.\n    "
                             f"{session._sync_mismatch_lines(sc)}")
            hc, cc = corpses(host), corpses(client)
            if hc != cc:
                fails.append(f"corpse censuses differ: host {hc} vs client {cc}")
            h, c = session.battle_checksum(host), session.battle_checksum(client)
            if h[0] != c[0]:
                fails.append(f"item-id counters differ: host {h[0]} vs client {c[0]}")
            if h[1] != c[1]:
                fails.append(f"battle censuses differ: host {h[1]} vs client {c[1]}")
            if corpse_arm1 != corpse_arm0:
                fails.append(f"corpseReplayArmed/corpseRemapArmed moved from {corpse_arm0} "
                             f"to {corpse_arm1} - the atomic path armed a legacy mint-at-"
                             f"apply window it should never touch")
            if attr_bad:
                fails.append(f"kill attribution diverged (the debrief-identical substitute): "
                             f"{attr_bad}")
            for gc, tag in ((host, "host"), (client, "client")):
                if TW.desync_seen(gc):
                    fails.append(f"the PRD-P2 drift tripwire FIRED on the {tag}")
    except Exception as e:
        import traceback
        fails.append(f"[ERROR] {e}\n{traceback.format_exc()}")
    finally:
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    mode = "RED (atomic_death_disable)" if args.red else "GREEN (atomic path ON)"
    if fails:
        print(f"\n==== atomic unit death Phase 2b [{mode}]: FAIL ====")
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print(f"\n  PASS [{mode}]: casualtiesApplied={cas_applied} casualtiesRejected="
          f"{cas_rejected} midSideDeaths={mid_deaths}")
    sys.exit(0)


if __name__ == "__main__":
    main()
