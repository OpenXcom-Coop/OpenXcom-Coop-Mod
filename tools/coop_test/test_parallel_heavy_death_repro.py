"""DETERMINISTIC REPRO for BUG-parallel-heavy-alien-death-desync.

WHAT THE BUG IS (see openxcom-coop-agent-docs/parallel/
BUG-parallel-heavy-alien-death-desync.md): in a parallel co-op battle, when an alien
side produces MANY casualties at once, the two machines intermittently drift apart -
UNIT/ITEM CENSUS DRIFT, the PRD-P2 tripwire firing (host itemId=76 vs client itemId=77),
or a never-close RX wedge. It is NOT seed-deterministic in the field (~1 fail per 3-4
soak runs): whether the client's death-carrier backlog drains and HEALS before the side
boundary depends on wall-clock timing, not the RNG seed.

WHY NO EXISTING FIXTURE CATCHES IT: the targeted death tests deliberately steer AROUND
this exact residual. test_parallel_alien_death_decouple.py caps `--pairs 3` ("a bigger
cluster overwhelms the item 4-5 casualty-value replay ... swamps the decouple signal")
and asserts only the side-gated in-game buckets (unitsCore/unitsCombat), NOT the raw
census / itemIdCtr; test_parallel_corpse_mint.py names "the separate casualty-value
residual (item 4-5 residual, NOT asserted)". So NO fixture asserts the raw cross-machine
census under a HEAVY cluster - the field bug lives in that gap.

THIS REPRO closes the gap by combining, in one run:
  * a HEAVY per-side death cluster (--pairs above the targeted tests' cap of 3), staged
    by the same deterministic ambush the targeted tests use (weakened soldiers teleported
    adjacent to live aliens on BOTH machines, so the host alien AI kills a cluster
    in-chain each side);
  * a SLOW client + forced liveness floor (--slow-client, rx_force_floor) so the client's
    alien-side death-carrier backlog is maximally behind - the mid-drain window the heal
    races against is held open;
  * the RAW field check - SOAK.assert_census after EVERY alien side (unit census + strict
    item-id census + assert_battle_synced (the chkBattleItemId 76-vs-77 term) + the
    PRD-P2 desync tripwire + assert_sync_clean + the on-disk desync-report check), run in
    SHIPPED mode (strict-burnin OFF, matching the field: the report reproduces at
    strictBurnIn=False).

DETERMINISM (pinned for repeatable runs):
  * MAP + alien deployment + soldiers' rolled stats: TW.bring_up_battle(seed=SEED) calls
    RNG::setSeed right before the host generates the map (newbattle_ok). Same SEED => same
    battle, run to run. NO fixture re-roll (a re-roll would change the map): a pinned seed
    that comes up short of MIN_HOSTILES fails loudly so the operator picks another.
  * RNG stream: set_seed(SEED) on both machines after bring-up (host alien AI is pinned).
  * SOLDIER POSITIONING: ambush() computes target tiles from the pinned aliens' positions
    with a FIXED neighbour-scan order; teleport/set_stat consume no RNG, so they do not
    shift the stream. Every placement is LOGGED and folded into a scenario digest printed
    each run - an identical digest across runs proves the staged scenario is identical.
  The ONLY thing left non-deterministic is the client's wall-clock drain timing - which is
  exactly what the forcing knobs pin to the failing side.

Run:  python tools/coop_test/test_parallel_heavy_death_repro.py
        [--seed N] [--pairs N] [--sides N] [--hp N] [--slow-client MS]
        [--no-force-floor] [--ghost-off] [--rx-hold] [--drain-disable]

REPRO SEMANTICS (this is a repro, not a guard): the GOAL is to fire the bug.
  exit 0  = REPRO FIRED  (assert_census drifted / tripwire / wedge) - the bug reproduced.
  exit 3  = NO REPRO     (every alien side stayed in census) - tighten the knobs / seed.
  exit 2  = harness/setup error (short seed, boxed placement, mission ended, etc.).
"""
import argparse
import hashlib
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_endturn as PE
import test_parallel_soak as SOAK

PORT = "47996"  # the in-game coop TCP rendezvous port (unique per concurrent test)


def bstate(gc):
    return SOAK.battle(gc)


def parallel(gc):
    return SOAK.parallel(gc)


def corpses(gc):
    return sorted((i["id"], i["type"]) for i in gc.ok({"cmd": "battle_items"})["items"]
                  if "CORPSE" in i["type"].upper())


def item_id_counter(gc):
    """The next BattleItem id this machine will mint (chkBattleItemId) - the 76-vs-77 term."""
    return session.sync_check(gc).get("chkBattleItemId")


def write_fixture(user_dir, mission, difficulty):
    """Pin the NEW BATTLE mission + difficulty (SOAK.write_battle_fixture only writes mission).
    mission indexes the coop-filtered new-battle list: 1=MEDIUM_SCOUT, 5=TERROR_SHIP,
    6=BATTLESHIP (see the deployment order; the craft-preview entry is filtered so
    MEDIUM_SCOUT=1). Higher difficulty leans the deployment's alien count to its high end."""
    path = os.path.join(user_dir, "xcom1", "battle.cfg")
    with open(path, "w", encoding="utf-8") as f:
        f.write("mission: %d\n" % mission)
        f.write("difficulty: %d\n" % difficulty)
    return path


def adj_free(ax, ay, az, occupied):
    # FIXED scan order => deterministic placement given the pinned map.
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        p = (ax + dx, ay + dy, az)
        if p not in occupied:
            return p
    return None


def ambush(host, client, pairs, hp, log):
    """Weaken + place up to `pairs` soldiers adjacent to live aliens on BOTH machines so the
    host alien AI shoots them down in-chain (the death carriers whose heavy-cluster replay is
    the bug). Keeps soldier[0] untouched so the mission cannot end mid-run. Returns
    (placed, digest_fragment) - the fragment feeds the run's scenario digest."""
    hb = bstate(host)
    aliens = [u for u in hb["units"] if u.get("faction") == 1 and not u.get("isOut")]
    soldiers = [u for u in hb["units"] if u.get("faction") == 0 and not u.get("isOut")]
    occupied = {(u["x"], u["y"], u["z"]) for u in hb["units"] if not u.get("isOut")}
    placed = 0
    frag = []
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
        frag.append((sol["id"], alien["id"], p[0], p[1], p[2], hp))
        if log:
            print(f"      ambush: soldier {sol['id']} -> ({p[0]},{p[1]},{p[2]}) hp={hp} "
                  f"next to alien {alien['id']} at ({alien['x']},{alien['y']},{alien['z']})")
    return placed, frag


def unit_census_map(gc):
    b = SOAK.battle(gc)
    return {u["id"]: u for u in b["units"]}


def capture_mechanism(host, client, tag):
    """RCA ground-truth dump at (or just after) tripwire fire. Grabs the persisted rings
    (fieldDiffs / mismatches / rxTrace survive the heal) so we can pin the micro-mechanism:
    which unit+field diverged, host value vs client (peer) value, and the client apply order
    (did an action_end marker land before that unit's unit_casualty/hit_unit?)."""
    hp = host.cmd({"cmd": "parallel_state"})
    hsc = hp.get("syncCheck", {})
    cp = client.cmd({"cmd": "parallel_state", "trace": True, "traceLimit": 256, "dump_hold": True})
    # divergent units = census diff + any unit named in the host's field diffs.
    hu, cu = unit_census_map(host), unit_census_map(client)
    diverg = set()
    for uid in set(hu) | set(cu):
        a, b = hu.get(uid), cu.get(uid)
        if not a or not b:
            diverg.add(uid); continue
        if (a.get("health"), a.get("stun"), a.get("status"), a.get("wounds"),
                a.get("x"), a.get("y"), a.get("z")) != \
           (b.get("health"), b.get("stun"), b.get("status"), b.get("wounds"),
                b.get("x"), b.get("y"), b.get("z")):
            diverg.add(uid)
    for d in hsc.get("fieldDiffs", []):
        diverg.add(d.get("unitId", d.get("unit")))
    stats = {}
    for uid in sorted(x for x in diverg if isinstance(x, int)):
        try:
            stats[uid] = {
                "host": host.cmd({"cmd": "unit_stats_full", "id": uid}).get("units"),
                "client": client.cmd({"cmd": "unit_stats_full", "id": uid}).get("units"),
            }
        except Exception as e:
            stats[uid] = {"error": str(e)}
    return {
        "tag": tag,
        "host_desyncSeen": TW.desync_seen(host),
        "client_desyncSeen": TW.desync_seen(client),
        "fieldDiffs": hsc.get("fieldDiffs", []),
        "mismatches": hsc.get("mismatches", []),
        "buckets": hsc.get("buckets", {}),
        "lastSeq": hsc.get("lastSeq"), "lastComparedSeq": hsc.get("lastComparedSeq"),
        "host_turn_side": (SOAK.battle(host).get("turn"), SOAK.battle(host).get("side")),
        "client_turn_side": (SOAK.battle(client).get("turn"), SOAK.battle(client).get("side")),
        "client_rxTrace": cp.get("rxTrace", []),
        "client_holdDump": cp.get("holdDump", []),
        "client_rxSeqDeferred": cp.get("rxSeqDeferred"),
        "client_rxLegacyPasses": cp.get("rxLegacyPasses"),
        "client_rxHardFloorPasses": cp.get("rxHardFloorPasses"),
        "divergent_units": sorted(x for x in diverg if isinstance(x, int)),
        "unit_stats_full": stats,
    }


def diag(host, client, tag):
    """Full divergence dump - printed when the repro fires (or on any error)."""
    print(f"    ==== DIVERGENCE DUMP ({tag}) ====")
    for name, gc in (("host", host), ("client", client)):
        try:
            p = parallel(gc)
            print(f"    {name}: itemIdCtr={item_id_counter(gc)} corpses={len(corpses(gc))} "
                  f"rxHold={p.get('rxHold')} rxRotates={p.get('rxRotates')} "
                  f"rxSeqDeferred={p.get('rxSeqDeferred')} barrierBlocks={p.get('barrierBlocks')} "
                  f"rxHardFloorPasses={p.get('rxHardFloorPasses')} rxLegacyPasses={p.get('rxLegacyPasses')} "
                  f"displayBacklog={p.get('displayBacklog')} desyncSeen={TW.desync_seen(gc)} "
                  f"casualtiesApplied={p.get('casualtiesApplied')}")
        except Exception as de:
            print(f"    {name}: dump failed: {de}")
    for name, gc in (("host", host), ("client", client)):
        d = os.path.join(gc.user_dir, "desync-reports")
        wrote = sorted(os.listdir(d)) if os.path.isdir(d) else []
        if wrote:
            print(f"    {name} desync-reports on disk: {wrote} in {d}")


def _wireorder_unit_drift(hb, cb):
    """Alien-side-boundary unit census, SCOPED to what the protocol replicates there.

    Same principle SOAK.unit_census (test_parallel_soak.py:184-196) already applies to
    NON-PLAYER TU: "asserting a term the protocol does not replicate makes a permanent red
    rather than a detector." Two terms are not replicated AT THE ALIEN-SIDE BOUNDARY and
    so are NOT asserted here (they reconcile at the next sidestart, and the in-game
    sync-check gates them until then):

      * a unit's TU: when it is spent by host-resolved PANIC during the alien side it is
        "spent by executor AI, the peer applies the outcome" - identical to the non-player
        -TU rationale unit_census already excludes. (Player-turn TU is still strict; this
        repro only censuses at the ALIEN boundary.)
      * a DEAD unit's residual health/stun: for a unit that is isOut on BOTH machines, the
        exact leftover health/stun is a corpse number the protocol does not re-slave. The
        machines AGREE it is out (isOut is asserted); only the residual number differs.

    ALWAYS asserted (the real desync surface): position (x,y,z), wounds, isOut, and - for
    any unit NOT out on both machines - health/stun. So a live-unit health drift, a
    position drift, a wound drift, or an isOut (dead-vs-alive) disagreement STILL fails.
    Returns {id: (host_key, client_key)} for drifting units, or {} when clean."""
    hu = {u["id"]: u for u in hb["units"]}
    cu = {u["id"]: u for u in cb["units"]}

    def key(u, both_out):
        base = [u["x"], u["y"], u["z"], u.get("wounds"), bool(u["isOut"])]
        if not both_out:                 # a live/one-sided unit: health & stun are strict
            base += [u["health"], u["stun"]]
        return tuple(base)

    drift = {}
    for uid in set(hu) | set(cu):
        h, c = hu.get(uid), cu.get(uid)
        if h is None or c is None:
            drift[uid] = (h, c)
            continue
        both_out = bool(h["isOut"]) and bool(c["isOut"])
        if key(h, both_out) != key(c, both_out):
            drift[uid] = (key(h, both_out), key(c, both_out))
    return drift


def assert_census_wireorder(host, client, what):
    """The --wire-order acceptance: the scoped unit census (above) PLUS every strict
    detector SOAK.assert_census runs unchanged (item id census, tile hazards, the PRD-P2
    tripwire, the in-game sync-check, and the on-disk desync-report silence check). Only
    the unit-tuple's two protocol-non-replicated terms are dropped; a real desync in any
    other term - or the tripwire firing - still fails exactly as in shipped mode."""
    SOAK.settle_display(host, client)
    hb, cb = SOAK.battle(host), SOAK.battle(client)
    assert hb.get("inBattle") and cb.get("inBattle"), (
        f"the fixture's mission ENDED before the census {what}")
    drift = _wireorder_unit_drift(hb, cb)
    if drift:
        hs = {u["id"]: (u["status"], u.get("energy"), u.get("tu")) for u in hb["units"]}
        cs = {u["id"]: (u["status"], u.get("energy"), u.get("tu")) for u in cb["units"]}
        lines = "\n".join(
            f"      {k}: host={drift[k][0]} client={drift[k][1]}  "
            f"(status/energy/tu host={hs.get(k)} client={cs.get(k)})"
            for k in sorted(drift))
        raise AssertionError(
            f"SCOPED UNIT CENSUS DRIFT {what}: the two machines disagree on a replicated "
            f"term\n    (x, y, z, wounds, isOut [, health, stun if not both-out])\n{lines}")
    hi, ci = SOAK.item_census(host), SOAK.item_census(client)
    assert hi == ci, (
        f"ITEM CENSUS DRIFT {what}: strict id census differs "
        f"(host {len(hi)} items, client {len(ci)})\n{SOAK.first_diff(hi, ci)}")
    hh, ch = SOAK.hazard_census(host), SOAK.hazard_census(client)
    assert hh == ch, (
        f"TILE HAZARD DRIFT {what}: host={hh} client={ch}")
    session.assert_battle_synced(host, client, what)
    assert not TW.desync_seen(host) and not TW.desync_seen(client), (
        f"the PRD-P2 drift tripwire FIRED {what} - a release blocker")
    session.assert_sync_clean(host, client, what)
    for tag, gc in (("host", host), ("client", client)):
        d = os.path.join(gc.user_dir, "desync-reports")
        wrote = sorted(os.listdir(d)) if os.path.isdir(d) else []
        assert not wrote, (
            f"{tag} wrote a desync diagnostic bundle {what} in a CLEAN battle: {wrote}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260802,
                    help="pins map+deployment+stats (bring_up_battle) AND the RNG stream")
    ap.add_argument("--pairs", type=int, default=8,
                    help="soldiers ambushed per side; ABOVE the targeted tests' cap of 3 so "
                         "the heavy-cluster casualty-value replay is exercised")
    ap.add_argument("--sides", type=int, default=5, help="alien sides to drive (census after each)")
    ap.add_argument("--hp", type=int, default=25, help="ambushed soldiers' health (low => one-shot kills)")
    ap.add_argument("--slow-client", type=int, default=SOAK.SLOW_SPEED,
                    help="ms/frame on the client so its alien-side replay lags far behind the host")
    ap.add_argument("--no-force-floor", action="store_true",
                    help="do NOT force the liveness floor (default forces it: the reorder window)")
    ap.add_argument("--ghost-off", action="store_true",
                    help="disable the Phase-2c death ghost on the client (the report reproduces both ways)")
    ap.add_argument("--rx-hold", action="store_true",
                    help="ESCALATION: park the client pump during each alien side, release at the "
                         "boundary (stages the hard RX-wedge form of the bug)")
    ap.add_argument("--drain-disable", action="store_true",
                    help="ESCALATION: legacy full-disable drain (the pre-fix out-of-order burst)")
    ap.add_argument("--mission", type=int, default=1,
                    help="new-battle mission index (1=MEDIUM_SCOUT 3-6 aliens; 5=TERROR_SHIP "
                         "~10-18; 6=BATTLESHIP ~9-22 - a HEAVY single-side death cluster)")
    ap.add_argument("--difficulty", type=int, default=0,
                    help="new-battle difficulty 0..4 (higher => the deployment's alien count "
                         "leans to its high end)")
    ap.add_argument("--heavy-floor", type=int, default=0,
                    help="fail if fewer than this many live hostiles came up (catches a wrong "
                         "--mission index that silently fell back to a light map); 0 = MIN_HOSTILES")
    ap.add_argument("--trace-mechanism", action="store_true",
                    help="RCA: arm SEAM-7 field capture, and on tripwire fire dump the exact "
                         "(unit, field, host, peer) diffs + client apply-order trace + per-unit "
                         "stats to <scratch>/mechanism_trace.json (pins which micro-mechanism)")
    ap.add_argument("--wire-order", action="store_true",
                    help="FIX LEVER: engage wire_order_state on both machines - the client applies "
                         "hash-relevant state at RX arrival in stream order and samples the per-action "
                         "sync-check at the marker's wire-order first sight (sync_report). Uses the "
                         "scoped alien-side-boundary census (drops the two protocol-non-replicated "
                         "residuals). Expect the repro to STOP firing (exit 3) with the lever on.")
    ap.add_argument("--scoped-census", action="store_true",
                    help="ORACLE-VALIDITY: use the scoped alien-side-boundary census WITHOUT engaging "
                         "the fix lever. Proves the scoped census still catches the real bug (position/"
                         "tripwire/hazard/live-unit health) lever-off: expect it to STILL fire (exit 0).")
    args = ap.parse_args()

    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": args.slow_client, "battleAlienSpeed": args.slow_client,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48900, make_user_dir("heavydeath_host", options=host_opts))
    client = GameClient("client", 48901, make_user_dir("heavydeath_client", options=client_opts))
    for gc in (host, client):
        write_fixture(gc.user_dir, args.mission, args.difficulty)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT
    PE.PORT = PORT

    repro_fired = None      # the AssertionError text, once it fires
    setup_error = None
    scenario_digest = None
    mechanism_capture = None  # RCA ground-truth bundle, grabbed when the tripwire flips
    corpses0 = 0
    corpses_grew = 0        # captured BEFORE quit (the socket is dead after)
    peak_backlog = 0
    started = time.time()
    try:
        # --- pinned bring-up (map/deployment/stats) + pinned RNG stream ---
        TW.bring_up_battle(host, client, seed=args.seed)
        for gc in (host, client):
            gc.ok({"cmd": "set_seed", "seed": args.seed})
        assert bstate(host)["activeSync"] is True and bstate(client)["activeSync"] is False, \
            "host must own the sim, client must be the replay peer (executor invariant)"

        foes = [u for u in bstate(host)["units"] if u.get("faction") == 1 and not u.get("isOut")]
        soldiers = [u for u in bstate(host)["units"] if u.get("faction") == 0 and not u.get("isOut")]
        floor = args.heavy_floor or SOAK.MIN_HOSTILES
        assert len(foes) >= floor, (
            f"pinned seed {args.seed} / mission {args.mission} came up with only {len(foes)} live "
            f"hostiles (< {floor}) - a wrong --mission index that fell back to a light map, or a "
            f"short seed. Pick another --seed/--mission (NO re-roll: it would change the map).")
        # scenario digest seed: the pinned rosters (positions/ids) the whole run derives from.
        roster = sorted((u["id"], u.get("faction"), u["x"], u["y"], u["z"]) for u in bstate(host)["units"])
        print(f"pinned seed {args.seed}: {len(foes)} aliens, {len(soldiers)} soldiers "
              f"({time.time() - started:.0f}s)")

        # forcing knobs (failure reliability) - SHIPPED compare mode (no strict-burnin).
        if args.ghost_off:
            client.cmd({"cmd": "parallel_state", "death_ghost_disable": True})
            assert parallel(client).get("deathGhostDisable") is True, "ghost-off lever did not engage"
        if not args.no_force_floor:
            client.cmd({"cmd": "parallel_state", "rx_force_floor": True})
            assert parallel(client).get("rxForceFloor") is True, "rx_force_floor lever did not engage"
        if args.wire_order:
            # FIX LEVER: wire-order state-apply + report on both machines (the fix under test).
            for gc in (host, client):
                gc.cmd({"cmd": "parallel_state", "wire_order_state": True})
                assert parallel(gc).get("wireOrderState") is True, "wire_order_state lever did not engage"
        if args.drain_disable:
            for gc in (host, client):
                gc.cmd({"cmd": "parallel_state", "rx_drain_disable": True})
        if args.trace_mechanism:
            for gc in (host, client):
                r = gc.cmd({"cmd": "sync_capture", "on": True})
                assert r.get("fieldCapture") is True, f"SEAM-7 field capture did not arm: {r}"
            print("    SEAM-7 field capture ARMED on both (mechanism trace)")
        knobs = (f"slow-client={args.slow_client} force-floor={not args.no_force_floor} "
                 f"ghost-off={args.ghost_off} rx-hold={args.rx_hold} drain-disable={args.drain_disable} "
                 f"wire-order={args.wire_order} "
                 f"pairs={args.pairs} sides={args.sides} hp={args.hp}")
        print(f"knobs: {knobs}")

        corpses0 = len(corpses(client))
        digest_frags = [("roster", roster)]

        for side in range(1, args.sides + 1):
            if not bstate(host).get("inBattle"):
                setup_error = f"mission ended before alien side {side} (fixture exhausted)"
                break
            placed, frag = ambush(host, client, args.pairs, args.hp, log=(side == 1))
            digest_frags.append((f"side{side}", placed, frag))
            turn0 = bstate(host)["turn"]

            if args.rx_hold:
                # ESCALATION: park the client pump across the alien side, release at the boundary.
                client.cmd({"cmd": "parallel_state", "rx_hold": True})
                PE.hush(host, client)
                for gc in (host, client):
                    if not parallel(gc)["localReady"]:
                        PE.arm(gc)
                end = time.time() + 12.0
                while time.time() < end:
                    peak_backlog = max(peak_backlog, parallel(client).get("rxHold", 0))
                    time.sleep(0.5)
                client.cmd({"cmd": "parallel_state", "rx_hold": False})
                PE.wait_side(host, client, turn0, timeout=180)
            else:
                # sample the client's backlog while the alien side replays (the lag the bug needs).
                SOAK.close_side(host, client, 0, 1, turn0)
                # RCA: poll the host sync-check HARD right after the side closes - the
                # unitsCombat mismatch + SEAM-7 fieldDiffs land in their persisted rings the
                # instant they fire; grab the moment either is non-empty (before it heals /
                # the peer goes silent). Also catch the P2 tripwire flip.
                for _ in range(40):
                    pc = parallel(client)
                    peak_backlog = max(peak_backlog, pc.get("displayBacklog", 0), pc.get("rxHold", 0))
                    if args.trace_mechanism and mechanism_capture is None:
                        sc = parallel(host).get("syncCheck", {})
                        if sc.get("mismatches") or sc.get("fieldDiffs") \
                                or TW.desync_seen(host) or TW.desync_seen(client):
                            mechanism_capture = capture_mechanism(host, client,
                                                                  f"fire on alien side {side}")
                            print(f"    *** mismatch/tripwire seen - captured "
                                  f"(units {mechanism_capture['divergent_units']}, "
                                  f"{len(mechanism_capture['fieldDiffs'])} fieldDiffs, "
                                  f"{len(mechanism_capture['mismatches'])} mismatches) ***")
                            break
                    time.sleep(0.2)

            print(f"  alien side {side} (turn {turn0}): ambushed {placed}, corpses "
                  f"host={len(corpses(host))} client={len(corpses(client))}, "
                  f"peak client lag={peak_backlog} ({time.time() - started:.0f}s)")

            # THE RAW FIELD CHECK - settle then compare (unit/item census + battle-synced +
            # tripwire + sync-clean + on-disk desync-report). This is what fires in the field.
            try:
                # --wire-order: the fix aligns the sync-check REPORT; the two protocol-
                # non-replicated residuals (panic-spent TU, dead-unit residual health)
                # reconcile at the next sidestart and are dropped from the unit tuple only
                # (every strict detector stays). Shipped/baseline runs keep the full census.
                census = (assert_census_wireorder
                          if (args.wire_order or args.scoped_census) else SOAK.assert_census)
                census(host, client, f"after the alien side of turn {turn0}")
            except AssertionError as ae:
                repro_fired = str(ae)
                print(f"\n  *** REPRO FIRED after alien side {side} (turn {turn0}) ***")
                print(f"  {repro_fired}")
                if args.trace_mechanism and mechanism_capture is None:
                    mechanism_capture = capture_mechanism(host, client, f"post-settle side {side}")
                diag(host, client, f"alien side {side}")
                break

        try:
            corpses_grew = len(corpses(client)) - corpses0
        except Exception:
            pass
        scenario_digest = hashlib.sha256(
            json.dumps(digest_frags, sort_keys=True, default=str).encode()).hexdigest()[:16]

    except AssertionError as ae:
        setup_error = f"setup assertion: {ae}"
    except Exception as e:
        setup_error = f"{e}\n{traceback.format_exc()}"
    finally:
        try:
            if scenario_digest:
                print(f"\nscenario digest (identical across deterministic runs): {scenario_digest}")
            print(f"non-vacuity: corpses minted this run = {corpses_grew}, "
                  f"peak client lag = {peak_backlog}")
            if args.trace_mechanism:
                out = os.environ.get("MECH_TRACE_OUT") or os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "mechanism_trace.json")
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(mechanism_capture or {"note": "tripwire never flipped this run"},
                              f, indent=1, default=str)
                print(f"mechanism trace written -> {out}")
        except Exception as we:
            print(f"mechanism-trace write failed: {we}")
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    print("\n==== HEAVY-DEATH REPRO VERDICT ====")
    if setup_error:
        print(f"  SETUP ERROR (not a repro result): {setup_error}")
        sys.exit(2)
    if repro_fired:
        print("  REPRO FIRED - the heavy-alien-death desync reproduced under the pinned scenario.")
        print("  (assert_census drifted / tripwire fired / wedge - see the DIVERGENCE DUMP above)")
        sys.exit(0)
    if corpses_grew < 4:
        print(f"  INCONCLUSIVE: only {corpses_grew} corpse(s) minted - the alien AI did not kill a "
              f"heavy cluster (raise --pairs, lower --hp, or try another --seed). NOT a clean result.")
        sys.exit(2)
    print(f"  NO REPRO - {args.sides} heavy alien sides ({corpses_grew} corpses) stayed in census. "
          f"Tighten the knobs (--rx-hold, --drain-disable, higher --slow-client) or sweep --seed.")
    sys.exit(3)


if __name__ == "__main__":
    main()
