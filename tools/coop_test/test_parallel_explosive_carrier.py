"""Chain-atomicity item-2: the tile explosive-charge CONSUMPTION must be host-shipped
data, not a client display-side mutation.

THE BUG (chain-atomicity audit A.1 / D.3 report): when a chained-terrain ExplosionBState
starts, ExplosionBState::init reads the tile's explosive charge into _power and ZEROES it
(`_tile->setExplosive(0,0,true)`). The ARM side of a tile's explosive charge already ships
(the destroy_tile carrier), but this CONSUMPTION/zero was never shipped: the parallel
replay client derived it from its own display loop instead. So the two machines' explosive-
charge state (a saveBlob/terrain hash term) races the destroy_tile ARM carrier and diverges,
and chained-explosion behaviour derives from it. Default skirmish maps carry ZERO explosive
terrain (why soaks never showed it), so the fixture arms a tile CLUSTER on BOTH machines and
fires an HE into it: the host consumes the cluster at sim rate while the pre-fix client
consumes it at ANIMATION rate, so the client falls many tiles behind the host for seconds.

THE FIX (item-2): the host ships every explosive-charge consumption as a stamped
`set_explosive_tile` carrier (rides the ordered gate + D.1 action_end apply barrier exactly
like destroy_tile); the parallel replay client stops zeroing locally and applies the packet
instead. Classic co-op / PvP / single-player are byte-identical (the ship + the suppression
are both parallel-PvE + host/replay-gated).

METRIC (introspected via the `battle_tiles` explosive census this fixture's commit added -
present in both the pre-fix and post-fix build): after the HE burst, sample both machines'
armed-tile count rapidly.
  maxLag = max(host_armed - client_armed) over the burst.
Pre-fix the client zeroes at ANIMATION rate -> it lags the host by an animation-scale
backlog (order of the cluster size). Post-fix the client zeroes at PACKET rate off the
ordered carrier -> it tracks the host within a couple of in-flight packets. Both machines
settle IDENTICAL (0) at quiescence either way, so the signal is the transient lag, not the
settled state (which never distinguished the bug).

An iteration is a valid trial only if the cluster armed IDENTICALLY on both machines
pre-shot (else the shot had nothing to consume and the run would be vacuous).

Run:
  python tools/coop_test/test_parallel_explosive_carrier.py            # assert GREEN
  python tools/coop_test/test_parallel_explosive_carrier.py --probe    # report maxLag
  python tools/coop_test/test_parallel_explosive_carrier.py --iters 5 --seed 42

Exit 0 = pass (GREEN: the client tracked the host's explosive state within LAG_TOL every
burst); 2 = failure (the client fell an animation-scale backlog behind = the display-driven
zero is still mutating explosive state locally).
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

# Explosive power pre-set on each cluster tile (radius = power/10). Kept LOW: the tiles are
# pre-armed so any HE trigger cascades through the whole block regardless of per-tile power,
# and a low power keeps the chained blasts from cratering the floor out from under the one
# hostile the default skirmish spawns (so a single bring-up yields several bursts). The lag
# signal is the tile COUNT (one animation per armed tile), not the power.
EXPL_POWER = 20
# Cluster half-width: a (2R+1)^2 block of armed tiles centred on the target.
CLUSTER_R = 2
# How many armed tiles the client may still hold at the instant the host reaches zero. The
# ordered carrier lets the client trail the host by only a packet or two of RX in-flight;
# the pre-fix animation backlog is an order of magnitude larger (~half the cluster).
REMAIN_TOL = 6
# How long to watch the two machines drain the cluster after the burst.
SAMPLE_S = 14.0
# A burst is a valid trial only if at least this many tiles armed IDENTICALLY on both
# machines pre-shot (else the shot consumes nothing and the run is vacuous).
MIN_CLUSTER = 9


def parallel(gc):
    return PI.parallel(gc)


def battle(gc):
    return PI.battle(gc)


def tiles(gc):
    return gc.ok({"cmd": "battle_tiles"})


def arm_cluster(gcs, cx, cy, cz, power, rad):
    for gc in gcs:
        for dx in range(-rad, rad + 1):
            for dy in range(-rad, rad + 1):
                gc.cmd({"cmd": "battle_tiles", "set_explosive": power,
                        "explosiveType": 0, "x": cx + dx, "y": cy + dy, "z": cz})


def align_item_counter(host, client):
    """Force both machines' SavedBattleGame item-id counter to a common value so the next
    battle_give mints a MATCHED weapon id. The HE bursts mint corpses/items at diverging
    counters (the expected item 3-5 casualty/corpse residual this fixture does NOT fix), which
    would otherwise make give ids drift apart and starve the run of trials. Purely a fixture
    lever - it re-aligns the id CURSOR, it does not touch the explosive-charge state under
    test."""
    ch = host.ok({"cmd": "save_blob"}).get("itemCounter", 0)
    cc = client.ok({"cmd": "save_blob"}).get("itemCounter", 0)
    target = max(ch, cc) + 4
    for gc in (host, client):
        gc.ok({"cmd": "save_blob", "set_item_counter": target})


def give_weapon(host, client, uid, item, ammo):
    """Matched-id hand-off on BOTH machines without the full battle-sync assert (a terrain
    residual from a prior HE burst - the expected item 3-5 drift - must not abort a trial)."""
    session.wait_sync_loop_closed(host)
    align_item_counter(host, client)
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


def one_burst(host, client, tag, base_pos, idx):
    """Arm an explosive cluster on BOTH machines around a FRESH ground tile and fire an HE
    into it with any live own soldier. Deliberately hostile-INDEPENDENT: the trigger only has
    to run an ExplosionBState (checkForTerrainExplosions is whole-map, so the whole armed
    block cascades regardless of what the shot hit), and the target shifts each burst so one
    bring-up yields several trials instead of one crater that drops the lone skirmish hostile
    off the map. Returns a dict of metrics on a valid trial, or None."""
    if not PI.idle(host):
        return None
    # a fresh target tile each burst (walk it along x so successive craters do not overlap)
    tgt = (base_pos[0] + idx * 2, base_pos[1], base_pos[2])
    hseat = parallel(host)["localSeat"]
    shooter = None
    for cand in PI.own_units(battle(client), hseat):
        sid = cand["id"]
        if PI.place_adjacent(host, client, sid, tgt):
            PI.top_up(host, client, sid)
            shooter = sid
            break
    if shooter is None:
        return None
    try:
        wid = give_weapon(host, client, shooter, WEAPON, AMMO)
    except AssertionError as e:
        print(f"  [{tag}] give skipped: {e}")
        return None

    # Arm the explosive cluster on BOTH machines (matched) so the host's zero carrier has a
    # peer tile to converge, and verify they armed identically before the shot.
    arm_cluster((host, client), tgt[0], tgt[1], tgt[2], EXPL_POWER, CLUSTER_R)
    th = tiles(host)
    tc = tiles(client)
    armed = min(th["explosiveTiles"], tc["explosiveTiles"])
    matched_pre = (th["explosiveHash"] == tc["explosiveHash"])
    if not matched_pre or armed < MIN_CLUSTER:
        print(f"  [{tag}] cluster not matched/large enough pre-shot "
              f"(host {th['explosiveTiles']}t client {tc['explosiveTiles']}t "
              f"match={matched_pre}) - skipping")
        return None

    r = PI.intent(host, action="shoot", unit=shooter, mode=MODE, weapon_id=wid,
                  x=tgt[0], y=tgt[1], z=tgt[2])
    if not r.get("ok"):
        print(f"  [{tag}] shoot intent refused: {r}")
        return None

    # Rapidly sample both machines' armed-tile count while the cluster drains.
    # THE DETERMINISTIC SIGNAL: the client's armed-tile count at the instant the HOST first
    # reaches zero (has consumed the whole cluster). Pre-fix the client zeroes off its own
    # ANIMATION loop, which lags the host's sim, so it is still holding a backlog of armed
    # tiles when the host is already done. Post-fix the client zeroes off the ordered
    # set_explosive_tile carrier, which the RX pump applies far faster than an explosion
    # animates, so it finishes with (or a packet or two behind) the host - clientAtHostZero
    # ~ 0. Deterministic and direction-stable, unlike the jittery mid-burst peak lag.
    end = time.time() + SAMPLE_S
    max_lag = 0            # host had MORE armed than client (client ran ahead)
    max_behind = 0         # client had MORE armed than host (client lagging - the pre-fix bug)
    divergent = 0
    samples = 0
    both_zero = False
    host_zero_seen = False
    client_at_host_zero = None
    while time.time() < end:
        th = tiles(host)
        tc = tiles(client)
        samples += 1
        ht = th["explosiveTiles"]
        ct = tc["explosiveTiles"]
        max_lag = max(max_lag, ht - ct)
        max_behind = max(max_behind, ct - ht)
        if th["explosiveHash"] != tc["explosiveHash"]:
            divergent += 1
        if not host_zero_seen and ht == 0:
            host_zero_seen = True
            client_at_host_zero = ct
        if ht == 0 and ct == 0 and th["explosiveHash"] == tc["explosiveHash"]:
            both_zero = True
            break
        time.sleep(0.08)

    PI.idle(host, 60)
    time.sleep(1.5)
    th = tiles(host)
    tc = tiles(client)
    settled_match = (th["explosiveHash"] == tc["explosiveHash"])
    # If the host never hit zero in-window (very slow run) fall back to the final client count.
    if client_at_host_zero is None:
        client_at_host_zero = tc["explosiveTiles"]
    return {"armed": armed, "clientAtHostZero": client_at_host_zero,
            "maxLag": max_lag, "maxBehind": max_behind,
            "divergent": divergent, "samples": samples, "bothZero": both_zero,
            "settledMatch": settled_match,
            "settledHost": th["explosiveTiles"], "settledClient": tc["explosiveTiles"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=5,
                    help="target number of valid bursts to measure")
    ap.add_argument("--seed", type=int, default=8675309,
                    help="host map seed (client gets seed+1); pins the fixture")
    ap.add_argument("--probe", action="store_true",
                    help="report the lag metric instead of asserting GREEN")
    args = ap.parse_args()

    fail = None
    host = GameClient("host", 48792,
                      make_user_dir("expl_carrier_host",
                                    options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48793,
                        make_user_dir("expl_carrier_client",
                                      options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    valid = 0
    rows = []
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        TW.bring_up_battle(host, client, seed=args.seed)
        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"skirmish fixture came up gamemode {gm}; parallel turns only cover PVE "
            f"(1) and PVE2 (4) - this fixture would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"
        probe = tiles(host)
        for field in ("explosiveTiles", "explosiveHash", "explosiveSum"):
            assert field in probe, (
                f"battle_tiles carries no `{field}` - bin/x64/Release/OpenXcom.exe "
                f"predates the item-2 explosive census; rebuild it (serial, MP=false). "
                f"fields: {sorted(probe)}")
        enemy0 = PI.alive_enemy(battle(host))
        assert enemy0, "the skirmish came up with no hostile to orient the fixture around"
        base_pos = (enemy0["x"], enemy0["y"], enemy0["z"])
        print(f"battle up (seed {args.seed}, gm {gm}). weapon={WEAPON} ammo={AMMO} "
              f"mode={MODE}. cluster r={CLUSTER_R} power={EXPL_POWER}. base {base_pos}. "
              f"target {args.iters} bursts")

        empties = 0
        maxlags = []
        tried = 0
        while valid < args.iters and empties < 10:
            m = one_burst(host, client, f"b{valid + 1}", base_pos, tried)
            tried += 1
            if m is None:
                empties += 1
                continue
            empties = 0
            valid += 1
            maxlags.append(m["clientAtHostZero"])
            row = (f"burst {valid}: armed {m['armed']}t  clientAtHostZero "
                   f"{m['clientAtHostZero']}  maxBehind {m['maxBehind']}  maxLag {m['maxLag']}  "
                   f"divergentSamples {m['divergent']}/{m['samples']}  "
                   f"bothZero={m['bothZero']}  settledMatch={m['settledMatch']} "
                   f"(host {m['settledHost']}t/client {m['settledClient']}t)")
            print("  " + row)
            rows.append((row, m))

        worst = max(maxlags) if maxlags else 0
        print(f"\n=== {valid} valid bursts; worst clientAtHostZero {worst} "
              f"(REMAIN_TOL {REMAIN_TOL}) ===")

        # The tripwire is EXPECTED to fire here: point-blank HE bursts mint corpses/items at
        # diverging counters (the item 3-5 casualty/corpse residual this fixture does NOT
        # address). It is NOT a verdict on the explosive carrier - the per-burst settledMatch
        # below proves the tile explosive-charge term itself converged. Reported, not asserted.
        tw_fired = TW.desync_seen(host) or TW.desync_seen(client)

        if args.probe:
            print(f"PROBE done: worstClientAtHostZero {worst}; perBurst {maxlags}; "
                  f"tripwire_fired={tw_fired} (expected: item 3-5 casualty residual)")
        else:
            assert valid >= 1, "no valid burst staged - fixture failure, not a result"
            # coop (explosion ordered-replay E5a re-arm): clientAtHostZero is now
            # ENFORCING. It was REPORT-ONLY (owner decision 2026-08-23, thin-client
            # divergence audit rec 5 + END-STATE A step 4) pending the explosion
            # ordered-replay rewrite - the client used to SIMULATE the blast on its own
            # animation clock while the host's ordered set_explosive_tile carrier arrived
            # on the bookkeeping clock, so a mid-transient trail was expected (item-2).
            # E1 (client stops running explode()/checkForTerrainExplosions and zeroes
            # armed tiles off the ordered carrier instead) closed that transient - RE-ARMED
            # here per the E5 phase block. settledMatch below remains the separate
            # quiescence correctness guard.
            bad = [(r, m) for (r, m) in rows if m["clientAtHostZero"] > REMAIN_TOL]
            assert not bad, (
                f"item-2 regression: {len(bad)}/{valid} bursts left the client holding "
                f"> {REMAIN_TOL} armed tiles at the instant the host reached zero - the "
                f"client is zeroing explosive charge off its own display loop again "
                f"instead of the host's ordered set_explosive_tile carrier (E1 should "
                f"have closed this transient). Rows:\n    "
                + "\n    ".join(r for r, _ in bad))
            settle_bad = [r for (r, m) in rows if not m["settledMatch"]]
            assert not settle_bad, (
                "explosive-charge state did not converge IDENTICAL at quiescence (the tile "
                "term the carrier owns must match even though casualty/item terms may drift):"
                "\n    " + "\n    ".join(settle_bad))
            print(f"PASS: {valid} HE bursts into an armed cluster; explosive charge "
                  f"CONVERGED IDENTICAL at quiescence on both machines, AND the client "
                  f"tracked the host's mid-transient armed-tile count within REMAIN_TOL "
                  f"{REMAIN_TOL} on every burst (worst clientAtHostZero {worst}) - both "
                  f"now asserted correctness guards post explosion-ordered-replay (E5a "
                  f"re-arm). (drift tripwire fired={tw_fired}: the orthogonal item 3-5 "
                  f"casualty residual)")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  DBG {tag} tiles: {tiles(gc)}")
            except Exception as de:
                print(f"  DBG {tag} dump failed: {de}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
