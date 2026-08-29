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


# The LIVE pending-to-APPLY depths that prove "nothing left to apply for this side".
# rxPark is DELIBERATELY excluded: g_rxPark holds ONLY the `endPlayerTurn` handshake packet,
# set aside by the `_coopEnd == 1` exclusion and un-parked only at the NEXT side transition
# (connectionTCP.cpp:3149,3699). It is a coop turn-handshake, not an un-applied residual for
# the current side - measured rxPark == 1 at EVERY alien-side boundary on BOTH clean (census
# passes) and drifting (census fires) runs, so including it would time the settle out every
# run without discriminating anything. The four below ARE current-side apply queues.
_LIVE_DEPTHS = ("rxHold", "rxQDepth", "snapPending", "displayBacklog")


def _drained(gc):
    """True iff this machine has NOTHING left to apply for the current side: every LIVE
    pending-to-apply queue depth is 0 (rxHold + raw rxQ + dirty conflation slots) AND the
    display cursor has caught up (displayBacklog). LIVE depths, not the cumulative counters;
    rxPark (the endPlayerTurn handshake) is excluded - see _LIVE_DEPTHS."""
    p = parallel(gc)
    return all((p.get(k, 0) or 0) == 0 for k in _LIVE_DEPTHS)


def settle_wire_order(host, client, timeout=60.0):
    """coop (option 3B, §2): wait until BOTH machines have fully drained every LIVE
    pending-apply queue (rxHold, rxPark, rxQ, dirty snapshot slots) AND displayBacklog == 0,
    so the FULLY-STRICT census measures the settled steady state. Bounded (60 s): on timeout
    print a loud SETTLE TIMEOUT with the offending depths and return, so the census still
    runs (a genuinely wedged drain FAILS the run RED rather than hanging the harness)."""
    end = time.time() + timeout
    while time.time() < end:
        if _drained(host) and _drained(client):
            return True
        time.sleep(0.25)
    hp, cp = parallel(host), parallel(client)
    hd = {k: hp.get(k) for k in _LIVE_DEPTHS}
    cd = {k: cp.get(k) for k in _LIVE_DEPTHS}
    print(f"    *** SETTLE TIMEOUT ({timeout:.0f}s): live drain queues never reached 0 - "
          f"host={hd} client={cd} - proceeding to census anyway (a wedged drain must fail RED) ***")
    return False


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
        "client_diagTrace": cp.get("diagTrace", []),  # three-class RCA: tagged write log
        "host_diagTrace": hp.get("diagTrace", []),    # three-class RCA: host-side lifecycle
        "client_holdDump": cp.get("holdDump", []),
        "client_rxSeqDeferred": cp.get("rxSeqDeferred"),
        "client_rxLegacyPasses": cp.get("rxLegacyPasses"),
        "client_rxHardFloorPasses": cp.get("rxHardFloorPasses"),
        # Task-A precondition disambiguator (owner 2026-08-26): rank-0 = the next_turn
        # snapshot. Rank0==0 => the panic-spent unit's next_turn TU write was APPLIED, so
        # the client's stale TU == the next_turn payload (pre-regen) => host-emit-order
        # branch. Rank0>0 (unit rejected) => payload was post-regen but dropped => watermark
        # branch. (coopApplyNextTurnUnitStates rank-0 watermark, connectionTCP.cpp:13426.)
        "client_stateWatermarkRejects": cp.get("stateWatermarkRejects"),
        "client_stateWatermarkRejectsRank0": cp.get("stateWatermarkRejectsRank0"),
        "client_nextTurnRejects": cp.get("nextTurnRejects"),
        "client_stateWatermarkRejectsRank1": cp.get("stateWatermarkRejectsRank1"),
        "client_stateWatermarkRejectsRank2": cp.get("stateWatermarkRejectsRank2"),
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
      * a TRULY-DEAD unit's residual health/stun: EXCLUDED ONLY when the unit is dead -
        health <= 0 - on BOTH machines (owner ruling 2026-08-26). A corpse's exact leftover
        health/stun is a number the protocol does not re-slave, and both machines already
        agree it is dead. A STUNNED-OUT unit (isOut but health > 0) stays FULLY asserted:
        it can WAKE, so a health/stun divergence there is a real future desync, not a
        residual. A host-dead / client-stunned split (health<=0 vs >0) also stays asserted
        and STILL fails - only both-dead is dropped.

    ALWAYS asserted (the real desync surface): position (x,y,z), wounds, isOut, and - unless
    the unit is dead (health<=0) on BOTH machines - health/stun. So a live-unit health drift,
    a stunned-out health/stun drift, a position drift, a wound drift, or an isOut
    (dead-vs-alive) disagreement STILL fails. Returns {id: (host_key, client_key)} for
    drifting units, or {} when clean."""
    hu = {u["id"]: u for u in hb["units"]}
    cu = {u["id"]: u for u in cb["units"]}

    def key(u, both_dead):
        base = [u["x"], u["y"], u["z"], u.get("wounds"), bool(u["isOut"])]
        if not both_dead:                # live / stunned-out / one-sided: health & stun strict
            base += [u["health"], u["stun"]]
        return tuple(base)

    drift = {}
    for uid in set(hu) | set(cu):
        h, c = hu.get(uid), cu.get(uid)
        if h is None or c is None:
            drift[uid] = (h, c)
            continue
        both_dead = (h["health"] <= 0 and c["health"] <= 0)   # truly-dead on BOTH (ruling)
        if key(h, both_dead) != key(c, both_dead):
            drift[uid] = (key(h, both_dead), key(c, both_dead))
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


# ---- bleed-out discrimination experiment (owner ruling 2026-08-29) ------------------
def _bleed_candidates(gc):
    """{uid: (health, stun, wounds, isOut, status)} for units that are bleed-out
    candidates on THIS machine - a fatal wound present (wounds>0) or already down
    (isOut). getFatalWounds() is host-resolved damage; both machines then bleed it in
    their OWN prepareNewTurn, so a per-turn host-vs-client read tells a heal from a freeze."""
    out = {}
    for u in SOAK.battle(gc)["units"]:
        if (u.get("wounds") or 0) > 0 or u.get("isOut"):
            out[u["id"]] = (u.get("health"), u.get("stun"), u.get("wounds"),
                            bool(u.get("isOut")), u.get("status"))
    return out


def _bleed_snapshot(host, client):
    hc, cc = _bleed_candidates(host), _bleed_candidates(client)
    return {uid: (hc.get(uid), cc.get(uid)) for uid in sorted(set(hc) | set(cc))}


def _print_bleed(label, snap):
    print(f"    [bleed-out] {label}: (health, stun, wounds, isOut, status)")
    if not snap:
        print("      (no bleed-out candidates)")
    for uid, (h, c) in snap.items():
        print(f"      unit {uid}: host={h} client={c}" + ("" if h == c else "   <<< DIFF"))


def _regen_latch(gc):
    """Non-diag unitsRegen latch view from parallel_state: the aggregate pending/heal/
    promote counters plus whether unitsRegen currently appears in the mismatch ring."""
    p = parallel(gc)
    sc = p.get("syncCheck", {}) or {}
    regen_mm = [m for m in (sc.get("mismatches", []) or []) if m.get("bucket") == "unitsRegen"]
    return (f"pending={p.get('syncBoundaryPending')} healed={p.get('syncBoundaryHealed')} "
            f"persistAlarms={p.get('syncBoundaryPersistAlarms')} "
            f"unitsRegenMismatches={len(regen_mm)}"
            + (f" last={regen_mm[-1]}" if regen_mm else ""))


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
    ap.add_argument("--rca-trace", action="store_true",
                    help="RCA: arm ONLY the lightweight diag write-log (diag_capture) on both "
                         "machines (NOT the heavy SEAM-7 sync_capture, so the quiet side still "
                         "closes) and dump both diagTraces at the final census -> MECH_TRACE_OUT")
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
    ap.add_argument("--strict-burnin", action="store_true",
                    help="INVESTIGATION (task D): engage strict capture on both machines (report-only "
                         "ALL buckets, alien-side skips stripped, ghost off) so a per-action mismatch is "
                         "COUNTED but never routes to the tripwire. Combined with --wire-order it proves "
                         "the per-action report is genuinely clean (not merely hidden behind the "
                         "report-only gate). Prints the host sync-check per-action vs boundary mismatch "
                         "breakdown at the end.")
    ap.add_argument("--quiet-sides", type=int, default=1,
                    help="BLEED-OUT DISCRIMINATION experiment (owner ruling 2026-08-29): drive N "
                         "consecutive quiet sides after the last ambush side (default 1 = committed "
                         "behaviour, byte-identical). With N>1 it arms the lightweight diag write-log, "
                         "censuses after EACH quiet boundary (diagnostic - only the FIRST still gates "
                         "the exit code, committed semantics unchanged), and captures every bleed-out "
                         "candidate (wounds>0 or isOut) host vs client plus the unitsRegen latch state "
                         "per boundary - so a FROZEN (persistent, missed alarm) face can be told apart "
                         "from a CONVERGING (transient, census sampled before the bleed tick settled).")
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
        if args.strict_burnin:
            # INVESTIGATION task D: strict capture, report-only ALL buckets, ghost off - so a
            # per-action mismatch is counted but never routes. Proves the per-action report is
            # clean rather than hidden behind the SharedEcon.cpp:6186 report-only gate.
            SOAK.enable_strict_burnin(host, client)
        if args.drain_disable:
            for gc in (host, client):
                gc.cmd({"cmd": "parallel_state", "rx_drain_disable": True})
        if args.trace_mechanism:
            for gc in (host, client):
                r = gc.cmd({"cmd": "sync_capture", "on": True})
                assert r.get("fieldCapture") is True, f"SEAM-7 field capture did not arm: {r}"
            # coop (three-class RCA DIAGNOSTIC): arm the capture-gated tagged write log on
            # BOTH machines (item lifecycle needs the host vs client compare). Lever-off inert.
            for gc in (host, client):
                gc.cmd({"cmd": "parallel_state", "diag_capture": True, "diag_heavy": True})
                assert parallel(gc).get("diagCapture") is True, "diag_capture did not arm"
            print("    SEAM-7 field capture + diag write-log (heavy) ARMED both (mechanism trace)")
        if args.rca_trace and not args.trace_mechanism:
            # RCA (TRACE A/B): arm ONLY the lightweight diag write-log (no heavy sync_capture),
            # so the quiet side still closes and the EXPL_TX/RX + TRACEB lifecycle is captured.
            for gc in (host, client):
                gc.cmd({"cmd": "parallel_state", "diag_capture": True})
                assert parallel(gc).get("diagCapture") is True, "diag_capture did not arm"
            print("    RCA diag write-log ARMED both (lightweight, no sync_capture)")
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
                # coop (Investigation B, executor 2026-08-26): the sidestart boundary residual
                # fires HERE (client released deeply behind at the boundary). Grab the SEAM-7
                # fieldDiff immediately - deterministic and non-wedging (rx-hold uses wait_side,
                # not close_side), so the unitsRegen polarity is captured before any heal.
                if args.trace_mechanism and mechanism_capture is None:
                    for _ in range(40):
                        sc = parallel(host).get("syncCheck", {})
                        if sc.get("mismatches") or sc.get("fieldDiffs") \
                                or TW.desync_seen(host) or TW.desync_seen(client):
                            mechanism_capture = capture_mechanism(host, client,
                                                                  f"rx-hold fire on alien side {side}")
                            mm = mechanism_capture.get("mismatches", [])
                            fd = mechanism_capture.get("fieldDiffs", [])
                            print(f"    *** INVESTIGATION-B rx-hold capture: "
                                  f"{len(fd)} fieldDiffs, mismatches={mm} ***")
                            for d in fd:
                                print(f"      fieldDiff: unit={d.get('unitId', d.get('unit'))} "
                                      f"field={d.get('field')} host={d.get('host')} client={d.get('client')}")
                            for uid, st in (mechanism_capture.get("unit_stats_full") or {}).items():
                                print(f"      unit {uid} host={st.get('host')} client={st.get('client')}")
                            break
                        time.sleep(0.2)
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
                # coop (option 3, §4 harness settle): under --wire-order the census must
                # measure the HEALED steady state (transient display-lane lag heals within
                # a boundary). Wait until BOTH machines are display-drained before comparing;
                # on timeout print a loud SETTLE TIMEOUT and proceed anyway (a genuinely
                # wedged client must still FAIL the run, not hang the harness).
                if args.wire_order:
                    settle_wire_order(host, client, timeout=60.0)
                    _hi, _ci = len(SOAK.item_census(host)), len(SOAK.item_census(client))
                    print(f"    [item-census] after side {side}: host={_hi} client={_ci}"
                          + (f"  <<< DIFF {_ci - _hi}" if _hi != _ci else "  (agree)"))
                census = (assert_census_wireorder
                          if (args.wire_order or args.scoped_census) else SOAK.assert_census)
                census(host, client, f"after the alien side of turn {turn0}")
            except AssertionError as ae:
                if args.wire_order:
                    # coop (option A, owner ruling 2026-08-29): during the AMBUSH sides the
                    # per-side census is DIAGNOSTIC ONLY - the deferred-authored residuals
                    # (stun/position/item-removal) reconcile over the NEXT side (each ambush
                    # side injects fresh ones the client is still replaying), so an alien-
                    # boundary census is a mid-flight snapshot, not a verdict. Print it, keep
                    # driving; the QUIET-SIDE census after the last ambush side is the gate.
                    # Lever-off (scoped/shipped) still GATES per-side (baseline preserved).
                    print(f"\n  [diagnostic] per-side census drift after alien side {side} "
                          f"(turn {turn0}) - NOT gating (reconciles over the next side):\n  {ae}")
                else:
                    repro_fired = str(ae)
                    print(f"\n  *** REPRO FIRED after alien side {side} (turn {turn0}) ***")
                    print(f"  {repro_fired}")
                    if args.trace_mechanism and mechanism_capture is None:
                        mechanism_capture = capture_mechanism(host, client, f"post-settle side {side}")
                    diag(host, client, f"alien side {side}")
                    break

        # coop (option A, owner ruling 2026-08-29): after the LAST ambush side, drive ONE
        # QUIET side - no ambush, no set_stat, no interference - so the next sidestart's
        # next_turn reconciles the deferred-authored residuals the ambush sides left in
        # flight. THEN run the FINAL census: FULLY STRICT (assert_census_wireorder keeps
        # every existing term - raw unit census incl. live-unit stun/position, strict item-id
        # census, assert_battle_synced, tripwire, sync-clean, on-disk report check; only the
        # two prior-ruled protocol-non-replicated drops remain, NO new exclusions). This is
        # the GATING assertion under --wire-order. The Option-B drain-wait runs before it.
        if args.wire_order and repro_fired is None and setup_error is None:
            if not bstate(host).get("inBattle"):
                setup_error = "mission ended before the quiet reconciliation side"
            else:
                # coop (bleed-out discrimination experiment, owner ruling 2026-08-29): in
                # multi-quiet-side mode arm the lightweight diag write-log (unitsRegen is
                # diag-robust) and snapshot the bleed-out candidates at the LAST AMBUSH SIDE,
                # before ANY quiet reconciliation - the tick-0 ground truth. Default
                # (--quiet-sides 1) skips all of this and is byte-identical.
                if args.quiet_sides > 1:
                    if not (args.trace_mechanism or args.rca_trace):
                        for gc in (host, client):
                            gc.cmd({"cmd": "parallel_state", "diag_capture": True})
                        print("    [experiment] diag write-log ARMED (bleed-out discrimination)")
                    _print_bleed(f"last ambush side, pre-quiet (turn {bstate(host)['turn']})",
                                 _bleed_snapshot(host, client))
                    print(f"      unitsRegen latch(host) {_regen_latch(host)}")
                qturn = bstate(host)["turn"]
                print(f"\n  -- OPTION A: driving ONE QUIET side (turn {qturn}, no ambush) for "
                      f"next_turn reconciliation, then the FINAL strict census --")
                SOAK.close_side(host, client, 0, 1, qturn)
                settle_wire_order(host, client, timeout=60.0)
                _hi, _ci = len(SOAK.item_census(host)), len(SOAK.item_census(client))
                print(f"    [item-census] after QUIET side: host={_hi} client={_ci}"
                      + (f"  <<< DIFF {_ci - _hi}" if _hi != _ci else "  (agree)"))
                try:
                    assert_census_wireorder(host, client,
                                            f"QUIET-SIDE FINAL census (after quiet turn {qturn})")
                    print("  -- QUIET-SIDE FINAL census CLEAN - the residuals reconciled --")
                except AssertionError as ae:
                    repro_fired = str(ae)
                    print(f"\n  *** REPRO FIRED at the QUIET-SIDE FINAL census (turn {qturn}) - "
                          f"a GENUINE unhealed divergence after a quiet reconciliation side ***")
                    print(f"  {repro_fired}")
                    if args.trace_mechanism and mechanism_capture is None:
                        mechanism_capture = capture_mechanism(host, client, "quiet-side final census")
                    diag(host, client, "quiet-side final census")
                # coop (G3 DETECTOR FIDELITY, owner ruling 2026-08-29): the in-game
                # tripwire (desyncSeen) must AGREE with the quiet-side census verdict -
                # census FIRES on a persistent divergence => desyncSeen True (the unmasked
                # alarm caught it, a TRUE positive); census CLEAN => desyncSeen False (no
                # false alarm from an unmasked pend-and-heal transient). A census-fires /
                # desyncSeen-False split (or the reverse) is the gate failure. Measured
                # independently of WHICH term the census raised on.
                qs_desync_host = TW.desync_seen(host)
                qs_desync_client = TW.desync_seen(client)
                _g3_verdict = "FIRED" if repro_fired else "CLEAN"
                _g3_agree = (bool(repro_fired) == bool(qs_desync_host))
                print(f"    [G3 detector-fidelity] quiet-side census={_g3_verdict}  "
                      f"desyncSeen host={qs_desync_host} client={qs_desync_client}  "
                      f"=> {'AGREE' if _g3_agree else 'DISAGREE <<< GATE FAILURE'}")
                if args.rca_trace:
                    rca_out = os.environ.get("MECH_TRACE_OUT") or os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), "rca_trace.json")
                    with open(rca_out, "w", encoding="utf-8") as _f:
                        json.dump({
                            "quiet_turn": qturn,
                            "repro_fired": repro_fired,
                            "item_census_after_quiet": {"host": _hi, "client": _ci},
                            "host_diagTrace": parallel(host).get("diagTrace", []),
                            "client_diagTrace": parallel(client).get("diagTrace", []),
                        }, _f, indent=1, default=str)
                    print(f"    RCA diag traces written -> {rca_out}")

        # coop (bleed-out discrimination experiment): the committed block above drove +
        # gated the FIRST quiet side. Drive the REMAINING quiet sides (diagnostic only -
        # they do NOT set repro_fired, so the exit code / committed gating is unchanged) and
        # capture, per boundary: bleed-out candidates host vs client, the unitsRegen latch
        # state, and census-vs-desyncSeen. DISCRIMINATION: a candidate whose host value
        # CONVERGES to the client's (or both converge) by boundary 2/3 => TRANSIENT (the
        # one-quiet-side census sampled before the bleed tick settled). A candidate FROZEN
        # apart across >=2 quiet boundaries at true drain => PERSISTENT (missed alarm).
        if args.wire_order and setup_error is None and args.quiet_sides > 1:
            _print_bleed(f"after quiet boundary 1 (turn {qturn})",
                         _bleed_snapshot(host, client))
            print(f"      unitsRegen latch(host) {_regen_latch(host)}")
            for _qi in range(2, args.quiet_sides + 1):
                if not bstate(host).get("inBattle"):
                    print(f"  [experiment] mission ended before quiet side {_qi} - stopping")
                    break
                _qt = bstate(host)["turn"]
                print(f"\n  -- quiet side {_qi}/{args.quiet_sides} (turn {_qt}, no ambush) --")
                SOAK.close_side(host, client, 0, 1, _qt)
                settle_wire_order(host, client, timeout=60.0)
                _hi2, _ci2 = len(SOAK.item_census(host)), len(SOAK.item_census(client))
                print(f"    [item-census] after quiet side {_qi}: host={_hi2} client={_ci2}"
                      + (f"  <<< DIFF {_ci2 - _hi2}" if _hi2 != _ci2 else "  (agree)"))
                _print_bleed(f"after quiet boundary {_qi} (turn {_qt})",
                             _bleed_snapshot(host, client))
                print(f"      unitsRegen latch(host) {_regen_latch(host)}")
                try:
                    assert_census_wireorder(host, client, f"quiet boundary {_qi} (turn {_qt})")
                    _cf = False
                    print(f"    [census] quiet boundary {_qi}: CLEAN")
                except AssertionError as _ae:
                    _cf = True
                    print(f"    [census] quiet boundary {_qi}: DRIFT:\n      {_ae}")
                _dh = TW.desync_seen(host)
                print(f"    [detector-fidelity] quiet boundary {_qi}: "
                      f"census={'FIRED' if _cf else 'CLEAN'} desyncSeen={_dh} => "
                      f"{'AGREE' if bool(_cf) == bool(_dh) else 'DISAGREE'}")
            # full unitsRegen latch transition history (diag TRACEB), laid beside ground truth
            _tb = [l.split('TRACEB', 1)[-1].strip()
                   for l in (parallel(host).get("diagTrace", []) or [])
                   if "TRACEB pending" in l and "unitsRegen" in l]
            print(f"\n  == unitsRegen latch TRACEB transition history (host, {len(_tb)} entries) ==")
            for _l in _tb:
                print(f"    {_l}")

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
            # Owner policy (2026-08-26): FLAG any natural liveness-floor engagement every run -
            # fail-loud beats silent out-of-order healing. Captured before the sockets close.
            floor = {}
            for _n, _gc in (("host", host), ("client", client)):
                try:
                    _p = parallel(_gc)
                    floor[_n] = (_p.get("rxLegacyPasses"), _p.get("rxHardFloorPasses"))
                except Exception:
                    floor[_n] = None
            _engaged = any(v and (v[0] or v[1]) for v in floor.values() if v)
            print(f"floor engagement (rxLegacyPasses, rxHardFloorPasses): host={floor.get('host')} "
                  f"client={floor.get('client')}  "
                  f"{'<<< FLOOR ENGAGED - a liveness heal occurred this run' if _engaged else '(none - clean)'}")
            # coop (wire-order Increment 7, SHAPE A diagnostic): host regen-carry emitted
            # vs client applied. emitted>0 & applied>0 => the carry mechanism runs.
            try:
                print(f"SHAPE-A regen carry: host emitted={parallel(host).get('regenEmitted')} "
                      f"client applied={parallel(client).get('regenApplied')}")
            except Exception as _re:
                print(f"SHAPE-A regen carry: <unavailable: {_re}>")
            # Boundary epoch-reset gate (owner ruling 2026-08-26): print the client's
            # rank-0 (next_turn snapshot) watermark-reject counter every run - the fix
            # gate demands it be 0 lever-on in all gate runs.
            try:
                _r0 = parallel(client).get("stateWatermarkRejectsRank0")
                print(f"rank0 next_turn watermark rejects (client): {_r0}  "
                      f"{'(gate: must be 0 lever-on)' if args.wire_order else '(lever-off, informational)'}")
            except Exception:
                print("rank0 next_turn watermark rejects (client): <unavailable>")
            if args.strict_burnin:
                try:
                    sc = parallel(host).get("syncCheck", {})
                    mm = sc.get("mismatches", [])
                    per_action = [m for m in mm if not m.get("boundary")]
                    boundary = [m for m in mm if m.get("boundary")]
                    def _brk(lst):
                        d = {}
                        for m in lst:
                            k = f"{m.get('bucket')}/{m.get('kind')}"
                            d[k] = d.get(k, 0) + 1
                        return d
                    print(f"STRICT-BURNIN (task D): host sync-check breakdown "
                          f"(strictBurnIn={sc.get('strictBurnIn')}, compares={sc.get('compares')}):")
                    print(f"  PER-ACTION (non-boundary) mismatches = {len(per_action)}  {_brk(per_action)}")
                    print(f"  BOUNDARY mismatches                  = {len(boundary)}  {_brk(boundary)}")
                    print("  => PER-ACTION CLEAN (report not hidden by report-only gate)"
                          if not per_action else "  => PER-ACTION NOT CLEAN - investigate")
                except Exception as se:
                    print(f"  STRICT-BURNIN dump failed: {se}")
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
