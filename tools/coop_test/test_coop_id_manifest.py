"""PRD-P4: the Tier-A spawn id-manifest.

A "Tier-A" spawn is a set of BattleItems both machines create for THEMSELVES from
data that is identical on both (no RNG picks the set):

  corpses            - the armor's corpse list, size^2 of them
  death traps        - STR_DEATH_TRAP_<floorSpecialTileType>, pure map data
  convertUnit built-ins - the fixed getSpawnUnit() type's built-in weapons

The set matches; the IDS need not. Every id comes off the local counter
SavedBattleGame::_itemId, so as soon as the two machines mint in a different order
(or one of them mints something the other does not), id N denotes a DIFFERENT
instance on the two machines - a transposition. From then on every id-keyed packet
(moveCoopInventory, coopResolveWeapon, the ammo matches in the shooting states)
lands on the wrong item. P4 has the host ship the ids it minted (`minted_ids` on
the action's own carrier packet) and the peer adopt them.

This test drives all three sites in ONE battle and asserts, after each, that:

  * the two machines hold identical (id -> type/owner) item censuses,
  * their `_itemId` counters are equal (session.assert_battle_synced), and
  * the PRD-P2 drift tripwire has not fired on either machine.

Levers, and why they need a throwaway ruleset (the pattern from
test_coop_outcome_gaps.py - the mod is written into both isolated user dirs, so
both machines load the SAME rules or they would diverge for a different reason):

  death trap   stock xcom1 has none. `MCDPatches` marks the Skyranger's PLAIN
               floor tiles (the ones with no specialType of their own - the
               START_POINT floors the soldiers spawn on are deliberately left
               alone, or nobody could be deployed) as specialType 200, and the
               matching STR_DEATH_TRAP_200 item is defined harmless (power 1).
  respawn      no stock unit reachable in this fixture converts on death, so
               STR_SECTOID_SOLDIER gains `spawnUnit: STR_CHRYSSALID_TERRORIST`.
  size-2 corpse the fixture is a SECTOID terror site, whose deployment ranks 6/7
               are STR_CYBERDISC_TERRORIST - a 2x2 unit, so its death mints FOUR
               corpse items and exercises the multi-tile remap.

Both kills are STUN ROD knockouts (see stun_down): a blast aimed at a 2x2 unit's
own tile is fired from inside that unit and often never leaves the muzzle, and a
big blast OVERKILLS (health past -4x max), after which UnitDieBState mints no
corpses and runs no respawn at all - the one outcome that would leave the
assertions here vacuous. Blast-killed corpses are covered by the strict censuses
in test_coop_alien_launcher_item_loss / test_coop_inventory_item_theft, whose
blaster shot kills the firing alien.

Run:  python tools/coop_test/test_coop_id_manifest.py
Exit 0 = pass; 2 = failure.
"""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import shared_fixture
import test_coop_alien_launcher_item_loss as I74

STUN_ROD = "STR_STUN_ROD"
TRAP_TYPE = 200
TRAP_ITEM = "STR_DEATH_TRAP_%d" % TRAP_TYPE
RESPAWNER = "STR_SECTOID_SOLDIER"
RESPAWNED = "STR_CHRYSSALID_TERRORIST"

# MCD objects that are ORDINARY floors: Tile_Type 0 (floor), Target_Type 0 (no
# specialType of their own) and a real floor (No_Floor 0). Anything that already
# carries a specialType is left alone - PLANE index 2 is the START_POINT the
# Skyranger deploys X-COM on, and patching it away would break deployment
# outright. The four urban sets are the ground the terror site is built on, so
# whichever tile the probe below reaches is trapped.
PLAIN_FLOORS = {
    "PLANE": [15, 17, 18, 19, 21, 22, 23, 24, 26, 27, 28, 29, 30, 31, 32,
              33, 34, 35, 36, 37, 52, 53, 54, 55, 56, 60, 61],
    "ROADS": list(range(0, 15)),
    "URBITS": [16, 17, 21, 22],
    "URBAN": [25, 26, 40, 41, 52, 53, 74, 75, 76, 77, 78],
}

METADATA = """\
name: "Coop id-manifest test"
version: 1.0
description: "Test-only: a harmless death trap on the Skyranger floor and a respawning sectoid."
author: coop harness

master: xcom1
"""


def ruleset():
    patches = ""
    for dataset in sorted(PLAIN_FLOORS):
        patches += "  - type: %s\n    data:\n" % dataset
        patches += "".join("      - MCDIndex: %d\n        specialType: %d\n" % (i, TRAP_TYPE)
                           for i in PLAIN_FLOORS[dataset])
    return """\
items:
  - type: %s
    size: 0.1
    costBuy: 0
    weight: 3
    bigSprite: 21
    floorSprite: 21
    power: 1
    damageType: 3
    battleType: 5
    blastRadius: 1
    recover: false
units:
  - type: %s
    spawnUnit: %s
MCDPatches:
%s""" % (TRAP_ITEM, RESPAWNER, RESPAWNED, patches)


def make_mod(root):
    mod = os.path.join(root, "Coop_Id_Manifest_Test")
    os.makedirs(os.path.join(mod, "Ruleset"))
    with open(os.path.join(mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write(METADATA)
    with open(os.path.join(mod, "Ruleset", "id_manifest.rul"), "w", encoding="utf-8") as f:
        f.write(ruleset())
    return mod


# ---- reading the two machines ----------------------------------------------

def units(gc):
    return {u["id"]: u for u in I74.battle(gc)["units"]}


def corpses(gc):
    """{id: type} for every BT_CORPSE-ish item. `battle_items` reports the OWNER
    unit, which a corpse on the ground does not have, so the corpse's TYPE is what
    identifies which unit it came from - and a 2x2 unit yields four of one type."""
    return {i["id"]: i["type"] for i in gc.ok({"cmd": "battle_items"})["items"]
            if "CORPSE" in i["type"].upper()}


def desync_seen(gc):
    b = I74.battle(gc)
    assert "desyncSeen" in b, "battle_state carries no 'desyncSeen' (PRD-P2 missing)"
    return b["desyncSeen"]


def wait_quiesced(host, client, stable_samples=4, max_wait=90, settle=3.0):
    """Both machines' censuses have to hold still before anything is compared -
    a death runs over many frames and the two are not in step within one."""
    time.sleep(settle)
    prev, same = None, 0
    deadline = time.time() + max_wait
    while time.time() < deadline:
        now = (I74.census(host), I74.census(client))
        same = same + 1 if now == prev else 0
        if same >= stable_samples:
            return True
        prev = now
        time.sleep(1.0)
    return False


def check_synced(host, client, what, fails):
    d = I74.diff_census(I74.census(host), I74.census(client))
    if d:
        for line in d:
            print(f"  [DIVERGE] {line}")
        fails.append(f"{what}: host/client item census diverged ({len(d)} items)")
    try:
        session.assert_battle_synced(host, client, what)
    except AssertionError as e:
        fails.append(str(e))
        d = d or ["counter"]
    for gc, tag in ((host, "host"), (client, "client")):
        if desync_seen(gc):
            fails.append(f"{what}: the PRD-P2 drift tripwire fired on the {tag}")
    if not d:
        print(f"PASS {what}: censuses and item-id counters identical, tripwire quiet")
    return not d


def sim_owner(host, client):
    """The machine allowed to drive a battlescape action (classic co-op: the one
    holding the simulation)."""
    return host.wait_for(
        "a machine to own the battle simulation",
        lambda: next(((gc, tag) for gc, tag in ((host, "host"), (client, "client"))
                      if session.can_drive(I74.battle(gc))), None),
        timeout=90, interval=1.0)


# ---- part 1: death trap -----------------------------------------------------

def part_death_trap(host, client, fails):
    """The host's checkForProximityGrenades creates STR_DEATH_TRAP_200 for the tile
    and ships the packet; the peer's checkForProximityGrenadesCoop creates its own
    copy. Consume-on-create (path a) is what carries the id across."""
    print("\n-- part 1: death trap --")
    soldier = next(u for u in I74.battle(host)["units"]
                   if u["faction"] == 0 and not u["isOut"])
    # The soldiers stand on the craft's START_POINT floors, which are deliberately
    # NOT patched. The deck below them is ordinary PLANE floor, so it is - and
    # `teleport` refuses anything that is not a valid position, which is what makes
    # this a probe rather than an assumption.
    spot = None
    tried = landed = 0
    offsets = sorted(((dx, dy) for dx in range(-6, 7) for dy in range(-10, 11)),
                     key=lambda p: (abs(p[0]) + abs(p[1]), p))
    for dz in (0, -1):
        for dx, dy in offsets:
            want = (soldier["x"] + dx, soldier["y"] + dy, soldier["z"] + dz)
            if want == (soldier["x"], soldier["y"], soldier["z"]):
                continue
            tried += 1
            res = [gc.cmd({"cmd": "battle_teleport", "unit": soldier["id"],
                           "x": want[0], "y": want[1], "z": want[2]})
                   for gc in (host, client)]
            if not all(r.get("moved") for r in res):
                continue
            landed += 1
            r = host.cmd({"cmd": "battle_prox", "unit": soldier["id"]})
            if r.get("change") == 2:
                spot = want
                break
        if spot:
            break
    print(f"       probed {tried} tiles around {(soldier['x'], soldier['y'], soldier['z'])}, "
          f"{landed} of them reachable")
    if not spot:
        # Which half of the lever is dead? The item rule and the MCD patch come
        # from the same throwaway ruleset, so say which one the game actually has.
        probe = host.cmd({"cmd": "battle_give", "unit": soldier["id"],
                          "item": TRAP_ITEM, "slot": "ground"})
        have_rule = bool(probe.get("ok"))
        if have_rule:  # keep the two machines symmetric after the diagnostic mint
            client.cmd({"cmd": "battle_give", "unit": soldier["id"],
                        "item": TRAP_ITEM, "slot": "ground"})
        fails.append(f"no tile under/around the squad triggered a death trap "
                     f"({TRAP_ITEM} rule loaded: {have_rule}) - the lever is dead, "
                     f"so this part asserted nothing")
        return
    print(f"       soldier {soldier['id']} stepped onto a death trap at {spot}")
    wait_quiesced(host, client)
    check_synced(host, client, "after the death trap", fails)


# ---- shared lever: a deterministic knockout ---------------------------------

def place_adjacent(host, client, mover_id, tpos):
    """Put `mover_id` on a free tile next to `tpos`, on BOTH machines."""
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        want = (tpos[0] + dx, tpos[1] + dy, tpos[2])
        res = [gc.cmd({"cmd": "battle_teleport", "unit": mover_id,
                       "x": want[0], "y": want[1], "z": want[2]}) for gc in (host, client)]
        if all(r.get("moved") for r in res):
            return want
    return None


def stun_down(host, client, soldier_id, target, swings, fails, what):
    """Beat `target` down with a stun rod until it is out, from whichever machine
    owns the simulation.

    A stun rod rather than a blast, for two independent reasons:
      * DELIVERY - a blaster bomb aimed at a 2x2 unit's own tile is fired from
        inside that unit and frequently never leaves the muzzle, so "the target
        died" is not something a blast can be relied on to produce;
      * OVERKILL - a big blast drives health past -4x max, and UnitDieBState then
        mints NO corpses and runs NO respawn, which is the one outcome that would
        make the assertions below vacuous. Stun damage cannot overkill.
    Blast-killed corpses are covered elsewhere: the blaster shot in
    test_coop_alien_launcher_item_loss / test_coop_inventory_item_theft kills its
    firing alien, and both assert the census strictly.
    """
    spot = place_adjacent(host, client, soldier_id, (target["x"], target["y"], target["z"]))
    if not spot:
        fails.append(f"{what}: no free tile next to unit {target['id']} for the melee")
        return False
    shooter, _ = sim_owner(host, client)
    for swing in range(1, swings + 1):
        gave = {}
        for gc, name in ((host, "host"), (client, "client")):
            gave[name] = gc.ok({"cmd": "battle_give", "unit": soldier_id, "item": STUN_ROD,
                                "slot": "right", "clear_hands": True})
        time.sleep(1.5)
        r = shooter.cmd({"cmd": "battle_fire", "unit": soldier_id, "mode": "hit",
                         "weapon_id": gave["host" if shooter is host else "client"]["weaponId"],
                         "tu": 100, "x": target["x"], "y": target["y"], "z": target["z"]})
        if not r.get("ok"):
            print(f"       swing {swing} refused ({r.get('error')})")
        wait_quiesced(host, client)
        if units(host)[target["id"]]["isOut"]:
            print(f"       unit {target['id']} went down after {swing} swing(s)")
            return True
    fails.append(f"{what}: unit {target['id']} never went down in {swings} swings - "
                 f"the lever is dead, so this part asserted nothing")
    return False


# ---- part 2: a size-2 unit's corpses ----------------------------------------

def part_corpses(host, client, fails):
    """A 2x2 unit mints FOUR corpse items in one pass of UnitDieBState's size^2
    loop. All four must carry the host's ids on the peer. A Cyberdisc is
    `capturable: false`, so a stun knockout instaKills it and the corpses follow."""
    print("\n-- part 2: the corpses of a 2x2 unit --")
    big = [u for u in I74.battle(host)["units"]
           if u["faction"] == 1 and not u["isOut"] and "CYBERDISC" in u["name"].upper()]
    if not big:
        fails.append("this terror site deployed no Cyberdisc - the 2x2 corpse case "
                     "was not exercised")
        return
    target = big[0]
    soldier = next((u for u in I74.battle(host)["units"]
                    if u["faction"] == 0 and not u["isOut"]), None)
    if not soldier:
        fails.append("no live soldier left to swing a stun rod")
        return
    before = set(corpses(host))
    if not stun_down(host, client, soldier["id"], target, 10, fails, "2x2 corpses"):
        return

    hc, cc = corpses(host), corpses(client)
    fresh_h = {i: t for i, t in hc.items() if i not in before}
    fresh_c = {i: t for i, t in cc.items() if i not in before}
    print(f"       host   new corpses {sorted(fresh_h.items())}")
    print(f"       client new corpses {sorted(fresh_c.items())}")
    if fresh_h != fresh_c:
        fails.append(f"the corpse ids do not match: host {sorted(fresh_h.items())} vs "
                     f"client {sorted(fresh_c.items())} - the id-manifest did not "
                     f"re-stamp them")
    quad = sum(1 for v in fresh_h.values() if "CYBERDISC" in v.upper())
    if quad != 4:
        fails.append(f"the 2x2 unit minted {quad} Cyberdisc corpse item(s), not 4 - "
                     f"the multi-tile corpse loop was not exercised: "
                     f"{sorted(fresh_h.items())}")
    else:
        print(f"PASS 2x2 corpses: all 4 corpse items of the Cyberdisc carry the same "
              f"id on both machines")
    check_synced(host, client, "after the 2x2 unit's death", fails)


# ---- part 3: convertUnit ----------------------------------------------------

def part_convert(host, client, fails):
    """convertUnit's built-ins: the respawned unit's fixed weapons are minted by
    initUnit() on BOTH machines. The kill is a stun rod - a blast overkills a
    sectoid, and UnitDieBState skips the respawn entirely when _overKill is set."""
    print("\n-- part 3: convertUnit respawn --")
    hb = I74.battle(host)
    victims = [u for u in hb["units"]
               if u["faction"] == 1 and not u["isOut"] and "SECTOID" in u["name"].upper()
               and "CYBERDISC" not in u["name"].upper()]
    if not victims:
        fails.append("no live sectoid left to convert")
        return
    victim = victims[0]
    soldier = next((u for u in hb["units"] if u["faction"] == 0 and not u["isOut"]), None)
    if not soldier:
        fails.append("no live soldier left to swing a stun rod")
        return

    before_ids = set(units(host))
    if not stun_down(host, client, soldier["id"], victim, 8, fails, "convertUnit"):
        return

    new_h = set(units(host)) - before_ids
    new_c = set(units(client)) - before_ids
    print(f"       host spawned {sorted(new_h)}, client spawned {sorted(new_c)}")
    if new_h != new_c:
        fails.append(f"the respawn did not replicate: host {sorted(new_h)} vs client "
                     f"{sorted(new_c)}")
    elif not new_h:
        fails.append(f"sectoid {victim['id']} went down but nothing respawned - the "
                     f"`spawnUnit` lever is dead, so this part asserted nothing")
    else:
        print(f"PASS convertUnit: both machines respawned unit(s) {sorted(new_h)}")
    check_synced(host, client, "after the convertUnit respawn", fails)


def main():
    fails = []
    root = tempfile.mkdtemp(prefix="coop_p4_mod_")
    mod = make_mod(root)
    js = shared_fixture.bring_up("p4idm", (48862, 48863, 48262), mods=(mod,))
    host, client = js.host, js.client
    try:
        I74.enter_battle(js)
        check_synced(host, client, "at battle start", fails)
        part_death_trap(host, client, fails)
        part_corpses(host, client, fails)
        part_convert(host, client, fails)
    except Exception as e:
        print(f"[ERROR] {e}")
        fails.append(str(e))
    finally:
        js.shutdown()
        shutil.rmtree(root, ignore_errors=True)

    print("\n==== PRD-P4 id-manifest summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  corpses, death traps and convertUnit respawns all leave the two machines "
          "holding identical item ids and equal item-id counters")
    sys.exit(0)


if __name__ == "__main__":
    main()
