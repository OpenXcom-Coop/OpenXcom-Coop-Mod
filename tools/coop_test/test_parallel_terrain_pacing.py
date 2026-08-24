"""Chain-atomicity D.3b: a chained-terrain explosion must NEVER wedge the auto-shot
pacing wait.

THE BUG (empirically isolated by the D.3b probe): the client-side auto-shot pacing
signal `coopTaskCompleted` was a FILE-SCOPE GLOBAL shared by every ExplosionBState
instance (ExplosionBState.cpp). A shot's ExplosionBState parks on it + `_hasHitUnit==1`
waiting for the host's flip packet; a chained-terrain ExplosionBState (spawned via
checkForTerrainExplosions, `_explosionCounter>0`, BA_NONE) reads the SAME shared flag
and can either park on it or consume the shot's flip. When that race fires the shot's
wait is never released through its own flip: the ProjectileFlyBState beneath it holds
the receive gate and the client falls arbitrarily far behind, bounded today only by the
force-drain watchdog (`kRxPacingForceDrainTicks=600`, ~10 s).

The rifle control (no terrain explosion) never wedges; the HE auto-cannon (which spawns
chained-terrain explosions) does -> the chained-terrain race is the mechanism.

THE FIX (D.3b): (a) make the pacing signal per-instance (a member, not the file-scope
global) so no ExplosionBState can consume another's flip; (b) gate the park additionally
on `_explosionCounter==0` so a chained-terrain explosion NEVER parks on the shot-pacing
path. The force-drain watchdog stays as belt-and-suspenders.

POST-E2 UPDATE (explosion ordered-replay): the parallel client no longer runs
checkForTerrainExplosions or spawns chained-terrain explosions locally - it replays the
host's chain in the host's scan order via chain_detonation packets. So the client's
chained-terrain explosion is now DECOUPLED from its own shot replay: by the time the
chain_detonation-spawned ExplosionBState runs, the shot's coopPacingWait has already
resolved, so a chained-terrain can no longer even reach a live shot-pacing flag - the
D.3b race is closed STRUCTURALLY by the decoupling, on top of the original per-instance +
_explosionCounter==0 fix. This fixture is therefore reframed: it arms the chain on the
HOST (so the host chains the armed tile and ships chain_detonation), and its non-vacuous
signal is chainDetonationsApplied climbing on the client (a host-ordered chain actually
replayed), not the old terrainPacingDiverted. The wedge assertion (parks/consumes/
forceDrain == 0) is unchanged and is the real invariant. The legacy divert/park signals
stay in the OR so the fixture still arms + asserts on a pre-E2 build.

WHY THIS WAS A STATISTICAL PROBE, NOT A .sav-DETERMINISTIC FIXTURE (pre-E2): the manifestation is a
packet-timing race, not a map-setup condition. Whether a chained-terrain parks/consumes
depends on whether the host's flip lands before or after the chained-terrain's explode()
reaches the pacing decision - a fixed .sav pins the SETUP (explosive terrain + a scripted
HE shot) but cannot pin the RACE, so even a perfect fixture only wedges a fraction of the
time (D.3b measured ~9% forceDrain / ~30% floor engagement on random maps). This probe
maximises the OPPORTUNITY - a pinned-seed parallel battle, an HE auto-cannon fired
point-blank into a hostile so the CLIENT replays a multi-shot that hits a unit AND spills
terrain-chain explosions into the same window - and measures the manifestation rate over
many bursts. Pre-fix the rate is > 0; post-fix it is 0 (the fix closes the race
structurally: a chained-terrain can neither park nor consume the shot's flip).

Signals sampled on the CLIENT (all pre-existing parallel_state fields, so this runs
against an un-instrumented build):
  - forceDrainCount : the RX pump had to force-drain a starved pacing wait (a hard wedge
                      the watchdog rescued). Any climb = a wedge fired.
  - rxLegacyPasses  : liveness-floor engagements, expected 0.
  - coopInitDeath   : the ProjectileFlyBState gate-holder; a sustained run = the shot
                      replay held the receive gate.
  - coopPacingWait  : the ExplosionBState pacing wait; a sustained hold = a stalled wait.

An iteration is WEDGED if forceDrainCount climbed OR rxLegacyPasses climbed OR the
coopInitDeath/coopPacingWait hold ran past STALL_S.

Run:
  python tools/coop_test/test_parallel_terrain_pacing.py            # assert GREEN
  python tools/coop_test/test_parallel_terrain_pacing.py --probe    # report the rate
  python tools/coop_test/test_parallel_terrain_pacing.py --iters 20 --seed 42

Exit 0 = pass (GREEN: zero wedges across the run); 2 = failure (a wedge fired).
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import test_battle_tripwire as TW
import test_parallel_intents as PI
import session

PORT = "47993"
WEAPON = os.environ.get("PROBE_WEAPON", "STR_AUTO_CANNON")
AMMO = os.environ.get("PROBE_AMMO", "STR_AC_HE_AMMO")
MODE = os.environ.get("PROBE_MODE", "auto")

# A shot replay that hits a unit mid-multi-shot parks for a fraction of a second in the
# clean case; anything past this is a stalled/wedged wait, not normal pacing.
STALL_S = 3.0
# How long to watch the client after each host burst.
SAMPLE_S = 12.0
# Explosive power pre-set on the target tile (client only) so the HE blast's replay spawns
# a chained-terrain ExplosionBState. Small - enough to chain once (radius = power/10), not
# to wreck the map. explosiveType 0 = DT_HE.
EXPL_POWER = 60


def parallel(gc):
    return PI.parallel(gc)


def battle(gc):
    return PI.battle(gc)


def give_weapon(host, client, uid, item, ammo):
    """Hand `uid` the weapon+ammo on BOTH machines with matched ids, WITHOUT the full
    battle-sync assert give_both makes - a terrain/casualty residual from a prior HE
    burst (the expected, unrelated drift the D.3b audit calls out) must not abort a
    pacing-probe iteration. Matched ids are still required (else the intent's weapon_id
    would not resolve)."""
    session.wait_sync_loop_closed(host)
    req = {"cmd": "battle_give", "unit": uid, "item": item,
           "slot": "right", "clear_hands": True}
    if ammo:
        req["ammo"] = ammo
    ids = [gc.ok(dict(req)) for gc in (host, client)]
    assert ids[0]["weaponId"] == ids[1]["weaponId"], (
        f"battle_give minted different ids for {item} "
        f"({ids[0]['weaponId']} vs {ids[1]['weaponId']})")
    time.sleep(1)
    return ids[0]["weaponId"]


def sample_client(client, seconds, base):
    """Poll the client's pacing state for `seconds`. Return the peak signals seen. The
    terrainPacing* counters are monotonic globals, so max() == the final value."""
    end = time.time() + seconds
    init_start = None
    pacing_start = None
    out = {"forceDrain": base.get("forceDrainCount", 0),
           "legacy": base.get("rxLegacyPasses", 0),
           "parks": base.get("terrainPacingParks", 0),
           "consumes": base.get("terrainPacingConsumes", 0),
           "diverted": base.get("terrainPacingDiverted", 0),
           # coop (explosion ordered-replay E2): the count of host-ordered chained
           # secondaries this client replayed. Post-E2 THIS is the non-vacuous signal
           # (a terrain chain actually reached the client), replacing the old divert race.
           "chainApplied": base.get("chainDetonationsApplied", 0),
           "maxInitRun": 0.0, "maxPacingRun": 0.0,
           "maxTaskDepth": 0, "pacingSeen": 0, "samples": 0}
    while time.time() < end:
        try:
            pc = parallel(client)
        except Exception:
            continue
        out["samples"] += 1
        out["maxTaskDepth"] = max(out["maxTaskDepth"], pc.get("taskDepth", 0))
        out["forceDrain"] = max(out["forceDrain"], pc.get("forceDrainCount", 0))
        out["legacy"] = max(out["legacy"], pc.get("rxLegacyPasses", 0))
        out["parks"] = max(out["parks"], pc.get("terrainPacingParks", 0))
        out["consumes"] = max(out["consumes"], pc.get("terrainPacingConsumes", 0))
        out["diverted"] = max(out["diverted"], pc.get("terrainPacingDiverted", 0))
        out["chainApplied"] = max(out["chainApplied"], pc.get("chainDetonationsApplied", 0))
        if pc.get("coopInitDeath"):
            if init_start is None:
                init_start = time.time()
        else:
            if init_start is not None:
                out["maxInitRun"] = max(out["maxInitRun"], time.time() - init_start)
                init_start = None
        if pc.get("coopPacingWait"):
            out["pacingSeen"] += 1
            if pacing_start is None:
                pacing_start = time.time()
        else:
            if pacing_start is not None:
                out["maxPacingRun"] = max(out["maxPacingRun"], time.time() - pacing_start)
                pacing_start = None
    if init_start is not None:
        out["maxInitRun"] = max(out["maxInitRun"], time.time() - init_start)
    if pacing_start is not None:
        out["maxPacingRun"] = max(out["maxPacingRun"], time.time() - pacing_start)
    return out


def one_burst(host, client, tag):
    """Stage a host shooter point-blank on a live hostile and fire an HE auto-cannon burst:
    the CLIENT replays a multi-shot that hits a unit (arms the pacing wait), and the target
    tile is pre-armed with explosive so the client's blast replay spawns a chained-terrain
    ExplosionBState into the same window - the race. Returns (base, stats) on a valid burst,
    or (None, None) when the fixture could not stage one."""
    if not PI.idle(host):
        return None, None
    enemy = PI.alive_enemy(battle(host))
    if not enemy:
        return None, None
    eid = enemy["id"]
    # Keep the one hostile the default skirmish spawns usable across as many bursts as it
    # survives: set its health high on BOTH machines so an HE burst hits it (arming the
    # pacing wait) without killing it outright. (A point-blank HE eventually craters the
    # floor and drops it off the map, so a single bring-up yields a few bursts; the report's
    # statistical run stacks several bring-ups.)
    for gc in (host, client):
        gc.cmd({"cmd": "battle_action", "action": "set_stat", "unit": eid,
                "health": 500})
    enemy = PI.unit(battle(host), eid) or enemy
    epos = (enemy["x"], enemy["y"], enemy["z"])
    hseat = parallel(host)["localSeat"]
    shooter = None
    for cand in PI.own_units(battle(client), hseat):
        sid = cand["id"]
        if PI.place_adjacent(host, client, sid, epos):
            PI.top_up(host, client, sid)
            shooter = sid
            break
    if shooter is None:
        return None, None
    try:
        wid = give_weapon(host, client, shooter, WEAPON, AMMO)
    except AssertionError as e:
        print(f"  [{tag}] give skipped: {e}")
        return None, None
    # Arm the terrain chain deterministically. POST-E2 the parallel client no longer runs
    # checkForTerrainExplosions locally (it replays the host's chain via chain_detonation),
    # so the arming tile must be on the HOST: the host's HE blast finds the armed tile,
    # spawns a chained-terrain ExplosionBState (_explosionCounter == 1), and ships one
    # chain_detonation. The client spawns the display-only chained state from that packet and
    # runs the SAME pacing decision (_explosionCounter > 0 -> DIVERT, never park) while the
    # shot's pacing wait is still live. The host destroys the armed terrain and ships the
    # destroy_tile / set_explosive_tile carriers, so the client's terrain converges - no
    # host/client asymmetry, no tripwire compare crossed.
    host.cmd({"cmd": "battle_tiles", "set_explosive": EXPL_POWER, "explosiveType": 0,
              "x": epos[0], "y": epos[1], "z": epos[2]})
    base = dict(parallel(client))
    r = PI.intent(host, action="shoot", unit=shooter, mode=MODE, weapon_id=wid,
                  x=epos[0], y=epos[1], z=epos[2])
    if not r.get("ok"):
        print(f"  [{tag}] shoot intent refused: {r}")
        return None, None
    stats = sample_client(client, SAMPLE_S, base)
    PI.idle(host, 60)
    return base, stats


def is_wedged(base, stats):
    """The FAITHFUL bug signal: a chained-terrain explosion touched the shot-pacing path
    (parked on OR consumed the shot's flip) or the RX pump had to force-drain a starved
    pacing wait. rxLegacyPasses / long coopInitDeath holds are NOT the gate - they also
    climb from generic RX congestion on a busy HE turn, so they are secondary diagnostics
    only (see the pre/post analysis: rxLegacyPasses fires equally with and without the fix,
    the terrainPacing counters do not)."""
    return (stats["parks"] > base.get("terrainPacingParks", 0)
            or stats["consumes"] > base.get("terrainPacingConsumes", 0)
            or stats["forceDrain"] > base.get("forceDrainCount", 0))


def armed_opportunity(base, stats):
    """Did a terrain chain actually reach the client this burst (i.e. is this a non-vacuous
    trial)? POST-E2 the parallel client no longer scans/spawns chained secondaries locally,
    so the old divert race (a client-scan chained state hitting the live shot-pacing flag)
    no longer arms - the host-ordered chain is decoupled from the client's shot replay
    (coopPacingWait is already resolved by the time the chain_detonation-spawned state runs,
    which is exactly why the D.3b wedge can no longer happen this way). The post-E2 non-
    vacuous signal is chainDetonationsApplied climbing: the host chained the armed terrain,
    shipped chain_detonation, and the client replayed it. The legacy park/consume/divert
    signals stay in the OR so this fixture still arms on a pre-E2 build."""
    return (is_wedged(base, stats)
            or stats["chainApplied"] > base.get("chainDetonationsApplied", 0)
            or stats["diverted"] > base.get("terrainPacingDiverted", 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=15,
                    help="target number of valid bursts to measure")
    ap.add_argument("--seed", type=int, default=8675309,
                    help="host map seed (client gets seed+1); pins the fixture")
    ap.add_argument("--probe", action="store_true",
                    help="report the wedge rate instead of asserting GREEN")
    args = ap.parse_args()

    fail = None
    host = GameClient("host", 48792,
                      make_user_dir("terr_pacing_host",
                                    options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48793,
                        make_user_dir("terr_pacing_client",
                                      options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    valid = 0
    wedged = 0
    wedge_rows = []
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        TW.bring_up_battle(host, client, seed=args.seed)
        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"skirmish fixture came up gamemode {gm}; parallel turns only cover PVE "
            f"(1) and PVE2 (4) - this probe would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"
        pc = parallel(client)
        for field in ("coopPacingWait", "forceDrainCount", "rxLegacyPasses",
                      "coopInitDeath", "terrainPacingParks", "terrainPacingConsumes",
                      "terrainPacingDiverted"):
            assert field in pc, (
                f"parallel_state carries no `{field}` - bin/x64/Release/OpenXcom.exe "
                f"predates the D.3b terrain-pacing instrumentation; rebuild it "
                f"(serial, MP=false). fields: {sorted(pc)}")
        print(f"battle up (seed {args.seed}, gm {gm}). weapon={WEAPON} ammo={AMMO} "
              f"mode={MODE}. explPower={EXPL_POWER}. target {args.iters} bursts")

        armed = 0
        empties = 0
        while valid < args.iters and empties < 6:
            base, stats = one_burst(host, client, f"b{valid + 1}")
            if base is None:
                empties += 1
                # No live enemy or could not stage: nudge the turn so units are fresh.
                if not PI.alive_enemy(battle(host)):
                    print("  (no live hostiles remain - stopping)")
                    break
                continue
            empties = 0
            valid += 1
            w = is_wedged(base, stats)
            if armed_opportunity(base, stats):
                armed += 1
            row = (f"burst {valid}: parks {base.get('terrainPacingParks')}->"
                   f"{stats['parks']} consumes {base.get('terrainPacingConsumes')}->"
                   f"{stats['consumes']} diverted {base.get('terrainPacingDiverted')}->"
                   f"{stats['diverted']} forceDrain {base.get('forceDrainCount')}->"
                   f"{stats['forceDrain']} | legacy {base.get('rxLegacyPasses')}->"
                   f"{stats['legacy']} maxInitRun {stats['maxInitRun']:.2f}s "
                   f"pacingSeen {stats['pacingSeen']}  -> {'WEDGE' if w else 'clean'}")
            print("  " + row)
            if w:
                wedged += 1
                wedge_rows.append(row)

        print(f"\n=== {valid} valid bursts, {armed} armed the race, {wedged} WEDGED "
              f"({(100.0 * wedged / valid) if valid else 0:.0f}%) ===")
        for r in wedge_rows:
            print("  WEDGE " + r)

        # the drift tripwire must not have fired from any of this
        tw_fired = TW.desync_seen(host) or TW.desync_seen(client)

        if args.probe:
            print(f"PROBE done: wedgeRate {wedged}/{valid}; armed {armed}/{valid}; "
                  f"tripwire_fired={tw_fired}")
        else:
            assert valid >= 1, "no valid burst staged - fixture failure, not a result"
            assert armed >= 1, (
                f"no terrain chain reached the client across {valid} bursts "
                f"(chainDetonationsApplied never climbed, no legacy park/consume/divert) - "
                f"the fixture did not exercise the path, so a green result would be vacuous. "
                f"The host's HE blast must land on/adjacent to the armed explosive tile so it "
                f"chains and ships chain_detonation. Re-run (map/RNG dependent) or use --seed "
                f"on a map with adjacent explosive terrain.")
            assert wedged == 0, (
                f"{wedged}/{valid} bursts WEDGED the auto-shot pacing wait - a chained-"
                f"terrain explosion is still parking on or consuming the shot's pacing "
                f"flip (the D.3b bug). Rows:\n    " + "\n    ".join(wedge_rows))
            assert not tw_fired, "the drift tripwire fired during the pacing probe"
            print(f"PASS: {valid} HE-auto-cannon bursts, {armed} replayed a host-ordered "
                  f"terrain chain on the client, zero wedges - the chain_detonation replay "
                  f"never parks on, consumes, or force-drains the shot-pacing flip (post-E2 "
                  f"the chain is decoupled from the shot's pacing window, so the D.3b race "
                  f"can no longer form)")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  DBG {tag} parallel: {parallel(gc)}")
            except Exception as de:
                print(f"  DBG {tag} dump failed: {de}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
