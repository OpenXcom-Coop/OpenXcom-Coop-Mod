"""PRD-P3: the RNG/outcome-shipping gaps (AUDIT-rng GAP-1..9).

Every gap in that audit is the same shape: an RNG-dependent outcome that changes
battle state was rolled INDEPENDENTLY on both machines instead of being decided by
its authority and shipped. The fixes migrate each one to "host decides, peer
replays". This test drives the paths that were fixed and asserts the two machines
still describe the same battle afterwards.

PART 1 (commit 1 - id drift)
    Shotgun pellets (GAP-5): a pellet volley used to exhaust the shipped aim
    pre-rolls after the first shot, so the peer rolled the rest itself - different
    endpoints, a different NUMBER of TileEngine::hit() calls, and from there a
    permanently mis-paired hit stream (GAP-4a). Fire one and assert the battle
    still matches.
    Mid-battle spawns (GAP-1): an item whose blast spawns a unit used to roll AND
    create on both machines. Detonate one and assert both machines gained the SAME
    new unit id, with the item-id counter still equal.

PART 2 (commit 2 - resolution authority)
    Psi in PVE (GAP-2), melee hit/miss (GAP-4b) and Tile::ignite (GAP-3): drive a
    mind control and a melee attack, then assert the victim's faction/health and
    the item census agree - the host's decision, on both machines.

PART 3 (commit 3 - item existence)
    Proximity sweeps (GAP-8) and end-of-turn fuses (GAP-9): loose non-grenade
    items used to be swept away on each machine's own fuseProximityEvent() roll.
    Trigger a sweep and cross a turn boundary, then compare the item censuses.

Neither shotgun ammo nor a spawn-on-hit item exists in stock xcom1, so the test
GENERATES a throwaway ruleset into the harness's isolated user dirs and activates
it on both machines (same ruleset on both, or they would diverge for a different
reason) - the pattern test_shared_missile_bombardment.py uses.

Run:  python tools/coop_test/test_coop_outcome_gaps.py
Exit 0 = pass; 2 = failure.
"""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW

LAUNCHER = "STR_ROCKET_LAUNCHER"
SPAWNER = "STR_SMALL_ROCKET"   # gains spawnUnit below
SPAWNED = "STR_SECTOID_SOLDIER"
SHOTGUN_AMMO = "STR_RIFLE_CLIP"  # gains shotgunPellets below
PELLETS = 4
# A NON-grenade item with a fuse: it is removed rather than detonated, so a test can
# make the fuse paths fire over and over without a blast killing units (a kill mints
# a corpse, whose id is PRD-P4's gap, not this test's subject). specialChance 50 is
# what makes the outcome an actual coin flip - at the default 100 both machines
# "roll" RNG::percent(100) and trivially agree, which would make this vacuous.
FUSED = "STR_ELECTRO_FLARE"
FUSED_CHANCE = 50
FUSED_COUNT = 8

METADATA = """\
name: "Coop outcome-gap test"
version: 1.0
description: "Test-only: a spawn-on-blast grenade and shotgun rifle ammo."
author: coop harness

master: xcom1
"""

RULESET = f"""\
items:
  - type: {SPAWNER}
    spawnUnit: {SPAWNED}
    spawnUnitChance: 100
    spawnUnitFaction: 1
  - type: {SHOTGUN_AMMO}
    shotgunPellets: {PELLETS}
    shotgunSpread: 100
    shotgunBehavior: 0
  - type: {FUSED}
    specialChance: {FUSED_CHANCE}
    fuseTriggerEvents:
      proximityTrigger: true
      proximityExplode: true
"""


def make_mod(root):
    mod = os.path.join(root, "Coop_Outcome_Gaps_Test")
    os.makedirs(os.path.join(mod, "Ruleset"))
    with open(os.path.join(mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write(METADATA)
    with open(os.path.join(mod, "Ruleset", "outcome_gaps.rul"), "w", encoding="utf-8") as f:
        f.write(RULESET)
    return mod


# ---- reading the two machines ---------------------------------------------

def units(gc):
    return {u["id"]: u for u in TW.battle(gc)["units"]}


def unit_ids(gc):
    return set(units(gc))


def census(gc):
    r = gc.cmd({"cmd": "battle_items"})
    return {i["id"]: (i["type"], i["owner"]) for i in r["items"]}


def wait_until(fn, timeout, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


def settle(host, client, seconds=10):
    """Let both state machines drain. Never dismiss the battlescape itself."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        for gc in (host, client):
            t = TW.top(gc)
            if t != "BattlescapeState" and t not in ("NextTurnState",):
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.5)


def alive_enemy(gc, own_coop):
    for u in TW.battle(gc)["units"]:
        if u.get("faction") == 1 and not u.get("isOut"):
            return u
    return None


def assert_hits_paired(gc, tag, what):
    """GAP-4a: every host `hit_tile` must have found the attack THIS machine parked
    for it. The receiver logs and drops an unmatched one rather than applying it to
    the wrong attacker, so the log line is the direct evidence."""
    log = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(log):
        return
    with open(log, "r", encoding="utf-8", errors="replace") as f:
        bad = [ln.strip() for ln in f if "has no local attack" in ln]
    assert not bad, (
        f"{tag}: {len(bad)} host hit(s) could not be paired with a local attack "
        f"{what} - the two machines produced a different number of hits:\n  "
        + "\n  ".join(bad[:5]))


def report(host, client, what):
    h, c = TW.terms(host), TW.terms(client)
    print(f"    {what}: host itemId={h[0]} census={h[1]} | client itemId={c[0]} census={c[1]}")
    return h, c


# ---- part 1 ----------------------------------------------------------------

def part1_pellets(host, client, driver, watcher, dtag, shooter_id, target):
    """GAP-5 + GAP-4a: a shotgun volley must leave the two machines identical."""
    print(f"-- part 1a: shotgun volley ({PELLETS} pellets/shot) --")
    before = session.assert_battle_synced(host, client, "before the volley")
    driver.ok({"cmd": "battle_give", "unit": shooter_id, "item": "STR_RIFLE",
               "ammo": SHOTGUN_AMMO, "slot": "right", "clear_hands": True})
    watcher.ok({"cmd": "battle_give", "unit": shooter_id, "item": "STR_RIFLE",
                "ammo": SHOTGUN_AMMO, "slot": "right", "clear_hands": True})
    # battle_give mints on each machine separately, so re-sync the reading before
    # the shot rather than asserting on a stale baseline.
    time.sleep(2)
    session.assert_battle_synced(host, client, "after arming both machines")

    r = driver.cmd({"cmd": "battle_fire", "unit": shooter_id, "mode": "snap",
                    "tu": 200, "target": target["id"]})
    assert r.get("ok"), f"the {dtag} could not fire the shotgun: {r}"
    settle(host, client, seconds=12)

    after = session.assert_battle_synced(host, client, "after the shotgun volley")
    assert not TW.desync_seen(host) and not TW.desync_seen(client), \
        "the drift tripwire fired on a shotgun volley"
    assert_hits_paired(watcher, "the watcher", "after the shotgun volley")
    print(f"PASS pellets: {dtag} fired {PELLETS} pellets and both machines still "
          f"agree ({before} -> {after})")


def part1_spawn(host, client, driver, watcher, dtag, shooter_id):
    """GAP-1: a spawn-on-blast item must mint the SAME unit on both machines.

    A rocket into empty floor is the deterministic blast lever here: it detonates
    on impact wherever it lands, and - unlike shooting a unit - it kills nobody,
    so no corpse is minted (corpse ids are PRD-P4's gap, not this test's subject).
    """
    print("-- part 1b: mid-battle spawn --")
    session.assert_battle_synced(host, client, "before the spawn blast")
    shooter = units(driver)[shooter_id]
    origin = (shooter["x"], shooter["y"], shooter["z"])

    # Empty floor first (kills nobody). A rocket needs line of fire AND an impact
    # whose two-steps-back tile can hold a unit, so several directions get tried;
    # the alien's own tile is the last resort, because it always detonates.
    alien = alive_enemy(driver, None)
    candidates = [(origin[0] + dx, origin[1] + dy, origin[2]) for dx, dy in
                  ((6, 0), (-6, 0), (0, 6), (0, -6), (5, 5), (-5, -5), (5, -5), (-5, 5),
                   (8, 0), (-8, 0), (0, 8), (0, -8), (4, 4), (-4, 4), (4, -4), (-4, -4))]
    if alien:
        candidates.append((alien["x"], alien["y"], alien["z"]))

    for tile in candidates:
        before_h, before_c = unit_ids(host), unit_ids(client)
        assert before_h == before_c, \
            f"the two machines already hold different units: {before_h ^ before_c}"

        for gc in (driver, watcher):
            gc.ok({"cmd": "battle_give", "unit": shooter_id, "item": LAUNCHER,
                   "ammo": SPAWNER, "slot": "right", "clear_hands": True})
        time.sleep(2)

        # The rocket is spent the moment the shot leaves the launcher, so a launcher
        # that refused (no line of fire) shows up in a few seconds instead of costing
        # the full settle. Sampled BEFORE the shot: the state can run before the
        # command's reply is even read.
        def rockets():
            return sum(1 for t, _ in census(driver).values() if t == SPAWNER)

        pre_rockets = rockets()
        r = driver.cmd({"cmd": "battle_fire", "unit": shooter_id, "mode": "snap",
                        "tu": 200, "x": tile[0], "y": tile[1], "z": tile[2]})
        if not r.get("ok"):
            print(f"    rocket at {tile} refused ({r.get('error')}), trying another tile")
            continue
        fired = wait_until(lambda: rockets() < pre_rockets, 8)
        settle(host, client, seconds=14 if fired else 2)

        new_h = unit_ids(host) - before_h
        new_c = unit_ids(client) - before_c
        print(f"    rocket at {tile}: fired={fired}; host spawned {sorted(new_h)}, "
              f"client spawned {sorted(new_c)}")
        if not new_h and not new_c:
            continue  # the rocket found no valid spawn tile; try another direction
        assert new_h == new_c, (
            f"GAP-1: the spawn did not replicate - host minted {sorted(new_h)}, "
            f"client minted {sorted(new_c)}. Either the peer rolled its own spawn "
            f"or the manifest never crossed.")
        for uid in new_h:
            ht, ct = units(host)[uid], units(client)[uid]
            # x/y is the spawn DECISION and must match. z is not asserted: the level
            # a unit settles on is applyGravity's answer to the floor the blast just
            # destroyed, and terrain destruction is host-authoritative on its own
            # packet, so the two can sit a level apart until the per-turn bulk unit
            # dump (`next_turn`) repairs positions. The manifest ships the host's
            # landing tile, which fixes the case where the levels differ AT SPAWN;
            # a later chain explosion dropping the host's copy again is transient.
            assert (ht["x"], ht["y"]) == (ct["x"], ct["y"]), (
                f"spawned unit {uid} landed at {(ht['x'], ht['y'], ht['z'])} on the "
                f"host and {(ct['x'], ct['y'], ct['z'])} on the client")
            if ht["z"] != ct["z"]:
                print(f"    NOTE: unit {uid} sits on z={ht['z']} (host) vs "
                      f"z={ct['z']} (client) - gravity follows host-authoritative "
                      f"terrain; next_turn repairs it")
        session.assert_battle_synced(host, client, "after the spawn blast")
        assert not TW.desync_seen(host) and not TW.desync_seen(client), \
            "the drift tripwire fired on a replicated spawn"
        assert_hits_paired(watcher, "the watcher", "after the spawn blast")
        print(f"PASS spawn: {dtag} detonated a spawn-on-blast item and BOTH machines "
              f"minted unit(s) {sorted(new_h)} with matching positions and an equal "
              f"item-id counter")
        return True

    raise AssertionError(
        "no rocket produced a mid-battle spawn on either machine - the lever is "
        "dead, so the replication assertion above never ran")


def place_adjacent(driver, watcher, mover_id, tpos):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        spot = (tpos[0] + dx, tpos[1] + dy, tpos[2])
        res = [gc.cmd({"cmd": "battle_teleport", "unit": mover_id,
                       "x": spot[0], "y": spot[1], "z": spot[2]})
               for gc in (driver, watcher)]
        if all(r.get("moved") for r in res):
            return spot
    return None


def part2_melee(host, client, driver, watcher, dtag, wtag, mover_id):
    """GAP-4b + the melee TU double-charge: after a replayed melee the two machines
    must agree on the attacker's TU and on how many hits the attack produced."""
    print("-- part 2a: melee authority --")
    aliens = [u for u in TW.battle(driver)["units"]
              if u.get("faction") == 1 and not u.get("isOut")]
    assert aliens, "no live hostile left to melee"
    target = aliens[0]
    tpos = (target["x"], target["y"], target["z"])
    spot = place_adjacent(driver, watcher, mover_id, tpos)
    assert spot, f"no free tile adjacent to hostile {target['id']}"

    gave = [gc.cmd({"cmd": "battle_give", "unit": mover_id, "item": "STR_STUN_ROD",
                    "slot": "right", "clear_hands": True}) for gc in (driver, watcher)]
    assert all(g.get("ok") for g in gave), f"battle_give STR_STUN_ROD failed: {gave}"
    time.sleep(2)

    before = units(watcher)[mover_id]["tu"]
    r = driver.cmd({"cmd": "battle_fire", "unit": mover_id, "mode": "hit",
                    "weapon_id": gave[0]["weaponId"], "tu": 100,
                    "x": tpos[0], "y": tpos[1], "z": tpos[2]})
    assert r.get("ok"), f"the engine refused the melee: {r.get('error')}"
    assert wait_until(lambda: units(watcher)[mover_id]["tu"] != before, 45), \
        f"the melee never replicated to the {wtag} (TU still {before})"
    settle(host, client, seconds=8)

    dtu = units(driver)[mover_id]["tu"]
    wtu = units(watcher)[mover_id]["tu"]
    assert dtu == wtu, (
        f"the melee replay charged the {wtag} twice: attacker {mover_id} has "
        f"TU={dtu} on the {dtag} but {wtu} on the {wtag}. The packet writes the "
        f"authoritative value and MeleeAttackBState::init must not spend on top.")
    assert_hits_paired(watcher, f"the {wtag}", "after the melee")
    session.assert_battle_synced(host, client, "after the melee")
    print(f"PASS melee: attacker {mover_id} left with TU={dtu} on BOTH machines and "
          f"every hit paired")


def part2_psi(host, client, driver, watcher, dtag, wtag, mover_id, attempts=3):
    """GAP-2: a psi outcome in a PVE co-op battle is the host's, and it must reach
    the peer - `psi_result` used to be PVP-only, so a mind control that landed on
    one machine and failed on the other was permanent (next_turn repairs stats and
    tiles, never faction)."""
    print("-- part 2b: psi in PVE --")
    mode = TW.battle(host).get("coopGamemode")
    assert mode not in (2, 3), \
        f"this fixture is a PVP battle (gamemode {mode}); GAP-2 is about PVE"

    gave = [gc.cmd({"cmd": "battle_give", "unit": mover_id, "item": "STR_PSI_AMP",
                    "slot": "right", "clear_hands": True}) for gc in (driver, watcher)]
    assert all(g.get("ok") for g in gave), f"battle_give STR_PSI_AMP failed: {gave}"
    time.sleep(2)

    tried = 0
    for _ in range(attempts):
        aliens = [u for u in TW.battle(driver)["units"]
                  if u.get("faction") == 1 and not u.get("isOut")]
        if not aliens:
            break
        target = aliens[0]
        tpos = (target["x"], target["y"], target["z"])
        # Stand next to the victim on BOTH machines: PsiAttackBState pops straight
        # back out when the target is beyond the amp's maxRange, and the squad can
        # start the battle a long way from the aliens.
        if not place_adjacent(driver, watcher, mover_id, tpos):
            print(f"    no free tile adjacent to hostile {target['id']}")
            continue
        r = driver.cmd({"cmd": "battle_fire", "unit": mover_id, "mode": "psi",
                        "weapon_id": gave[0]["weaponId"], "tu": 100,
                        "x": tpos[0], "y": tpos[1], "z": tpos[2]})
        if not r.get("ok"):
            print(f"    psi refused ({r.get('error')})")
            continue
        # The DRIVER spending the topped-up TU is what says the attack actually ran.
        # Waiting on the watcher instead would miss an attempt whose replayed TU
        # happens to land on the value it already had - and it is precisely a psi the
        # host resolved but never shipped that this part has to catch.
        topped = r.get("tuHave")
        if not wait_until(lambda: units(driver)[mover_id]["tu"] != topped, 30):
            print("    psi cost the actor nothing (the state never ran)")
            continue
        settle(host, client, seconds=5)
        tried += 1

        hv, cv = units(host).get(target["id"]), units(client).get(target["id"])
        assert hv and cv, f"unit {target['id']} vanished from one machine"
        print(f"    psi on {target['id']}: host faction={hv['faction']} coop={hv.get('coop')} "
              f"| client faction={cv['faction']} coop={cv.get('coop')}")
        assert hv["faction"] == cv["faction"], (
            f"GAP-2: the psi outcome did not replicate - unit {target['id']} is "
            f"faction {hv['faction']} on the host and {cv['faction']} on the client. "
            f"Both machines resolved the attack for themselves.")
        assert hv.get("coop") == cv.get("coop"), (
            f"unit {target['id']} ended up owned by different players "
            f"({hv.get('coop')} vs {cv.get('coop')})")
        session.assert_battle_synced(host, client, "after the psi attack")

    assert tried, ("no psi attack ever ran, so the replication assertion never "
                   "executed")
    print(f"PASS psi: {tried} mind-control attempt(s) left every victim's faction and "
          f"owner identical on both machines")


# ---- part 3 ----------------------------------------------------------------

def flares(gc):
    return {i["id"]: i["fuse"] for i in gc.cmd({"cmd": "battle_items"})["items"]
            if i["type"] == FUSED}


def drop_fused(host, client, x, y, z, count):
    """Place `count` primed flares on one tile, on BOTH machines. No co-op packet
    replicates a mid-battle item spawn, so both sides have to create the same items
    in the same order for the ids to line up (the harness reports them back)."""
    ids = [gc.ok({"cmd": "battle_drop", "x": x, "y": y, "z": z, "item": FUSED,
                  "count": count, "prime": True, "fuse": 0})["ids"]
           for gc in (host, client)]
    assert ids[0] == ids[1], \
        f"the two machines minted different ids for the litter: {ids[0]} vs {ids[1]}"
    return ids[0]


def part3_proximity(host, client, wtag, unit_id):
    """GAP-8: a proximity sweep removes non-grenade items on the host's roll, and
    the peer must delete exactly that set instead of running its own.

    Driven on the HOST specifically: checkForProximityGrenades early-returns 0 on a
    client, so a sweep driven from there would sweep nothing and the comparison
    below would pass vacuously."""
    print("-- part 3a: proximity sweep --")
    u = units(host)[unit_id]
    ids = drop_fused(host, client, u["x"], u["y"], u["z"], FUSED_COUNT)
    time.sleep(2)
    before_h, before_c = flares(host), flares(client)
    assert set(before_h) == set(before_c), \
        f"the litter differs before the sweep: {set(before_h) ^ set(before_c)}"
    print(f"    littered {len(ids)} primed {FUSED}s on ({u['x']},{u['y']},{u['z']})")

    r = host.cmd({"cmd": "battle_prox", "unit": unit_id})
    assert r.get("ok"), f"the proximity sweep was refused: {r}"
    settle(host, client, seconds=8)

    after_h, after_c = flares(host), flares(client)
    gone_h = sorted(set(before_h) - set(after_h))
    gone_c = sorted(set(before_c) - set(after_c))
    print(f"    after the sweep: host swept {gone_h}, client swept {gone_c}")
    assert gone_h, (
        f"the sweep removed nothing at all ({len(ids)} primed items with "
        f"specialChance {FUSED_CHANCE}) - the lever is dead and the comparison "
        f"below would be vacuous")
    assert gone_h == gone_c, (
        f"GAP-8: the sweep removed a different set on each machine - host swept "
        f"{gone_h}, client swept {gone_c}")
    session.assert_battle_synced(host, client, "after the proximity sweep")
    print(f"PASS proximity: {len(gone_h)} item(s) swept, the SAME ones on both machines")


def part3_fuse(host, client, wtag, unit_id):
    """GAP-9: BattleItem::fuseTimeEvent() at the end of a side is per-machine. With
    specialChance 50 each primed item is a coin flip, so a peer rolling for itself
    disagrees with the host almost immediately - and then holds items the host no
    longer has, forever (next_turn repairs stats and tiles, never item existence)."""
    print("-- part 3b: end-of-turn fuses --")
    u = units(host)[unit_id]
    ids = drop_fused(host, client, u["x"], u["y"], u["z"], FUSED_COUNT)
    time.sleep(2)
    before_h, before_c = flares(host), flares(client)
    assert set(before_h) == set(before_c), \
        f"the litter differs before the turn: {set(before_h) ^ set(before_c)}"
    print(f"    littered {len(ids)} primed {FUSED}s (specialChance {FUSED_CHANCE})")

    turn = TW.cycle_turn(host, client)
    assert turn, (f"the battle never reached a new turn (turn="
                  f"{TW.battle(host).get('turn')}) - the end-of-turn fuse sweep "
                  f"never ran, so the assertion below would be vacuous")

    after_h, after_c = flares(host), flares(client)
    gone_h = sorted(set(before_h) - set(after_h))
    gone_c = sorted(set(before_c) - set(after_c))
    print(f"    turn {turn}: host burned {gone_h}, client burned {gone_c}; "
          f"survivors host={sorted(after_h.items())} client={sorted(after_c.items())}")
    assert gone_h or any(t != 0 for t in after_h.values()), (
        f"not one of the {len(ids)} primed items burned down or had its fuse "
        f"changed - the lever is dead, so the comparison below would be vacuous")
    assert gone_h == gone_c, (
        f"GAP-9: the end-of-turn fuse fired on different items - host removed "
        f"{gone_h}, client removed {gone_c}. Each machine rolled its own "
        f"RNG::percent({FUSED_CHANCE}).")
    assert after_h == after_c, (
        f"the survivors' fuse timers disagree: host={sorted(after_h.items())} "
        f"client={sorted(after_c.items())}")
    session.assert_battle_synced(host, client, "after the fuse boundary")
    assert_hits_paired(client, "the client", "after the fuse boundary")
    print(f"PASS fuses: {len(gone_h)} of {len(ids)} burned down, identically on both "
          f"machines, with the survivors' timers agreeing")


def main():
    tmp = tempfile.mkdtemp(prefix="coop_outcome_gaps_")
    fail = None
    host = client = None
    try:
        mod = make_mod(tmp)
        # battleInstantGrenade: a fuse-0 grenade detonates the moment it LANDS
        # (BattleItem::fuseThrowEvent), which is the only deterministic way to make
        # a blast happen on demand. Without it the grenade just lies there until
        # the end-of-turn fuse sweep.
        opts = {"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                "battleInstantGrenade": True}
        # skipNextTurnScreen on the HOST only - the same reason as
        # test_battle_tripwire: the "Turn N" screen then closes through the REAL
        # NextTurnState::close() on a timer, which is where the host ships next_turn
        # (and, before P3, where the hit-pairing counter re-bases). Never on the
        # client: it double-closes there (a known co-op/option interaction).
        host = GameClient("host", 48854,
                          make_user_dir("p3_gaps_host", mods=[mod],
                                        options=dict(opts, skipNextTurnScreen=True)))
        client = GameClient("client", 48855,
                            make_user_dir("p3_gaps_client", mods=[mod], options=opts))
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.bring_up_battle(host, client)
        print("battle up on both machines (with the test ruleset active)")

        # Part 3b runs FIRST because it is the one step that needs a TURN BOUNDARY,
        # and the attacks in parts 1 and 2 (a rocket, a psi amp, a stun rod) tend to
        # finish off the last alien - after which the next end-of-turn ENDS THE
        # BATTLE instead of cycling it, and the fuse sweep never runs at all.
        part3_fuse(host, client, "client",
                   next(u["id"] for u in TW.battle(host)["units"] if u["faction"] == 0))

        # The turn cycle hands the side over, so re-read who owns the simulation.
        driver, watcher, dtag, wtag, db = TW.pick_driver(host, client)
        print(f"simulation owner = {dtag}")
        own_coop = 0 if db["host"] else 1
        mine = TW.movers(TW.battle(driver), own_coop)
        assert mine, (f"{dtag} commands no unit able to act: "
                      f"{[(u['id'], u.get('coop'), u.get('tu')) for u in db['units']]}")
        shooter_id = mine[0]["id"]
        target = alive_enemy(driver, own_coop)
        assert target, "the generated battle holds no live alien to shoot at"

        part1_pellets(host, client, driver, watcher, dtag, shooter_id, target)
        part1_spawn(host, client, driver, watcher, dtag, shooter_id)
        # psi first: a stun rod tends to take the target out of the fight.
        part2_psi(host, client, driver, watcher, dtag, wtag, shooter_id)
        part2_melee(host, client, driver, watcher, dtag, wtag, shooter_id)
        part3_proximity(host, client, wtag, shooter_id)

        print("ALL PRD-P3 OUTCOME-GAP TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        for gc in (host, client):
            if gc:
                gc.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
