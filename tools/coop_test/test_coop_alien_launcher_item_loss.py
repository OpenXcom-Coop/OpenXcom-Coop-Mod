"""Issue #74 - an alien firing a blaster launcher must not disturb the X-COM
soldier's blaster launcher on the peer machine.

The invariant asserted here is wider than the report, and stronger: after a
replicated shot, the two machines' FULL BattleItem censuses (every instance's
id, type and owning unit) must still be identical, no item may change hands,
and the two item-id spaces must still be in lockstep. A co-op battle is
lockstep, so any per-instance divergence is a bug - and "the soldier's launcher
is gone on one side" is exactly such a divergence.

What was wrong
--------------
The shooter's packet named the firing weapon by TYPE plus
`BattlescapeState::_hand` - a sticky string only ever written when the LOCAL
player clicks a hand button. Nobody clicks anything for an AI alien, so the
hand was whatever the sender's player last used. The peer read that hand, found
the wrong item (or nothing), and then FABRICATED a `new BattleItem` to shoot
with. Two consequences:

  * the fabricated weapon has no ammo, so the peer never spends the blaster
    bomb the shooter spent - the machines' item sets diverge on the spot;
  * `new BattleItem` takes its id from `SavedBattleGame::getCurrentItemId()`,
    which post-increments it - so the receiver's item-id counter runs ahead of
    the sender's forever. From then on every id in the coop protocol denotes a
    different instance on the two machines, and the protocol's by-type
    fallbacks start selecting other players' identical gear.

Scenarios: the alien's launcher sits in the hand the packet claims
(`right_hand`) and in the other one (`left_hand`, the AI case).

PRD-P4 keeps the census assertion strict and adds the two drift-tripwire terms
to it: the blast kills the firing alien, and its CORPSES are a Tier-A spawn
whose ids the host now names on `after_unit_death`. A corpse id that differs
between the machines is a real divergence, so it is asserted rather than
filtered; the item-id counter is asserted too, because a census comparison
cannot see it.

Run:  python tools/coop_test/test_coop_alien_launcher_item_loss.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import shared_fixture
import test_shared_battle as B

LAUNCHER = "STR_BLASTER_LAUNCHER"
BOMB = "STR_BLASTER_BOMB"


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def top(gc):
    return gc.cmd({"cmd": "get_state"})["states"][-1].split("::")[-1]


def census(gc):
    """{itemId: (type, ownerUnitId)} for every BattleItem instance."""
    return {i["id"]: (i["type"], i["owner"]) for i in gc.ok({"cmd": "battle_items"})["items"]}


def diff_census(h, c):
    out = []
    for iid in sorted(set(h) | set(c)):
        a, b = h.get(iid), c.get(iid)
        if a == b:
            continue
        if a is None:
            out.append(f"item {iid} {b[0]} exists ONLY on the client (owner {b[1]})")
        elif b is None:
            out.append(f"item {iid} {a[0]} exists ONLY on the host (owner {a[1]})")
        else:
            out.append(f"item {iid} {a[0]}: host owner {a[1]} vs client owner {b[1]}")
    return out


def owners_of(cen, itype):
    return sorted((iid, own) for iid, (t, own) in cen.items() if t == itype)


def enter_battle(js):
    """Fly the shared craft to a terror site and take BOTH machines all the way
    to the tactical map with the coop turn initialised."""
    host, client = js.host, js.client
    b0 = B._base0(host)
    blon, blat = b0["lon"], b0["lat"]
    cid = B._skyranger(host)["id"]
    roster = sorted(s["id"] for s in B._roster(host))
    squad = roster[:3]
    for sid in roster:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
    for sid in squad:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})
    for gc in (host, client):
        gc.wait_for("squad aboard",
                    lambda gc=gc: (sorted(s["id"] for s in B._roster(gc)
                                          if s["craftId"] == cid) == squad) or None,
                    timeout=45, interval=0.5)

    site_id = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                       "deployment": "STR_TERROR_MISSION", "lon": blon + 0.35,
                       "lat": blat + 0.10, "race": "STR_SECTOID", "hours": 240})["site_id"]
    host.wait_for("site on host",
                  lambda: any(s["id"] == site_id for s in B._geo(host)["missionSites"]) or None,
                  timeout=30)
    host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
             "lon": blon + 0.34, "lat": blat + 0.10, "dest": f"site:{site_id}",
             "fuel": 999999, "lowFuel": False})

    def _landing_prompt():
        if B._has(host, "ConfirmLandingState"):
            return True
        host.cmd({"cmd": "geo_set_speed", "idx": 2})   # not geo_run: it auto-declines
        return None

    host.wait_for("ConfirmLandingState on host", _landing_prompt, timeout=90, interval=0.5)
    host.ok({"cmd": "confirm_landing"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} entered the battle",
                    lambda gc=gc: battle(gc).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc in (host, client):
        gc.wait_for("briefing", lambda gc=gc: B._has(gc, "BriefingState") or None,
                    timeout=60, interval=0.5)
        gc.ok({"cmd": "close_briefing"})
    for gc in (host, client):
        gc.wait_for("pre-battle inventory",
                    lambda gc=gc: B._has(gc, "InventoryState") or None, timeout=60, interval=0.5)
        gc.ok({"cmd": "battle_inventory", "action": "ok"})
    for _ in range(10):
        if all(top(gc) == "BattlescapeState" for gc in (host, client)):
            break
        for gc in (host, client):
            if top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(1.0)
    # Control only splits - and a machine only owns the simulation - once the
    # coop turn-init handshake has run on both sides.
    host.wait_for("the coop turn to initialise",
                  lambda: (battle(host).get("coopTurn") == 2) or None,
                  timeout=90, interval=1.0)
    time.sleep(2)


def arm(gc, unit_id, slot):
    return gc.ok({"cmd": "battle_give", "unit": unit_id, "item": LAUNCHER,
                  "ammo": BOMB, "slot": slot, "clear_hands": True})


def settle(host, client, seconds=8, stable_samples=4, max_wait=60):
    """Let the projectile fly, explode and the packets round-trip.

    Both censuses must hold still for several consecutive samples: the blast
    kills the firing alien, and the death/corpse/drop sequence has pauses longer
    than one sample, so a two-sample "stable" check reads a mid-sequence lull as
    settled and the assertions below flake.
    """
    time.sleep(seconds)
    prev, same = None, 0
    deadline = time.time() + max_wait
    while time.time() < deadline:
        now = (census(host), census(client))
        same = same + 1 if now == prev else 0
        if same >= stable_samples:
            return
        prev = now
        time.sleep(1.0)


def run_scenario(label, alien_slot, ports, fails):
    print(f"\n===== scenario '{label}' =====")
    js = shared_fixture.bring_up(f"i74{label[:1]}", ports)
    host, client = js.host, js.client
    try:
        enter_battle(js)

        hb, cb = battle(host), battle(client)
        assert [u["id"] for u in hb["units"]] == [u["id"] for u in cb["units"]], \
            "the two machines do not share a unit list"
        soldier = next(u for u in hb["units"] if u["faction"] == 0 and not u["isOut"])
        aliens = [u for u in hb["units"] if u["faction"] == 1 and not u["isOut"]]
        assert aliens, "no aliens in this battle"
        alien = aliens[0]
        print(f"       soldier {soldier['id']} @({soldier['x']},{soldier['y']},{soldier['z']}), "
              f"alien {alien['id']} @({alien['x']},{alien['y']},{alien['z']})")

        # Arm identically, in the same order, on BOTH machines - nothing in the
        # protocol replicates a mid-battle item spawn.
        given = {}
        for tag, gc in (("host", host), ("client", client)):
            given[tag] = [arm(gc, soldier["id"], "right"), arm(gc, alien["id"], alien_slot)]
        for i in range(2):
            hw, cw = given["host"][i], given["client"][i]
            assert (hw["weaponId"], hw["ammoId"]) == (cw["weaponId"], cw["ammoId"]), \
                f"item-id spaces diverged while arming: host {hw} vs client {cw}"
        soldier_launcher = given["host"][0]["weaponId"]
        alien_launcher = given["host"][1]["weaponId"]
        print(f"PASS arm: soldier launcher {soldier_launcher}, alien launcher "
              f"{alien_launcher} (in its {alien_slot} hand); both machines agree on the ids")

        pre_h, pre_c = census(host), census(client)
        assert not diff_census(pre_h, pre_c), \
            f"censuses diverged BEFORE the shot: {diff_census(pre_h, pre_c)}"
        print(f"PASS pre-shot: {len(pre_h)} item instances, identical on both machines")

        # The shot must be driven from a machine that may drive it: in classic
        # coop the battle states only emit their packet when _isActivePlayerSync
        # is true, so firing from the passive side would never reach the peer.
        # session.can_drive() also covers parallel turns (PRD-P5+), where both
        # machines may drive.
        def _sim_owner():
            for gc, tag in ((host, "host"), (client, "client")):
                if session.can_drive(battle(gc)):
                    return (gc, tag)
            return None

        shooter, shooter_tag = host.wait_for("a machine to own the battle simulation",
                                             _sim_owner, timeout=90, interval=1.0)
        # Waypoint on the alien's OWN tile: guaranteed valid, and it keeps the
        # blast away from the soldier, so "the soldier lost its launcher" can
        # only mean the replay took it - not that the soldier was blown up and
        # dropped it.
        shot = shooter.ok({"cmd": "battle_fire", "unit": alien["id"], "mode": "launch",
                           "weapon_id": alien_launcher, "tu": 200,
                           "waypoints": [{"x": alien["x"], "y": alien["y"], "z": alien["z"]}]})
        print(f"       alien {alien['id']} launches from the {shooter_tag} "
              f"(weapon {shot['weaponId']}, ammo {shot['ammoId']}, tu cost {shot['tuCost']})")

        settle(host, client)

        h, c = census(host), census(client)
        d = diff_census(h, c)
        if d:
            for line in d:
                print(f"  [DIVERGE] {line}")
            fails.append(f"{label}: host/client item census diverged ({len(d)} items)")
        # PRD-P4: the census stays STRICT - no per-type filter and no "ignore the
        # corpses" escape hatch. The blast kills the firing alien, and a corpse is a
        # Tier-A spawn (a deterministic set each machine creates for itself), so a
        # corpse whose id differs between the two machines is precisely the drift the
        # id-manifest removes - not noise to filter out. The two tripwire terms go
        # with it: the item-id COUNTER is invisible to a census comparison, and two
        # machines can hold identical item sets while one is primed to mint the next
        # id differently.
        try:
            session.assert_battle_synced(host, client, f"after the {label} shot")
        except AssertionError as e:
            fails.append(f"{label}: {e}")
        for gc, tag in ((host, "host"), (client, "client")):
            if battle(gc).get("desyncSeen"):
                fails.append(f"{label}: the PRD-P2 drift tripwire fired on the {tag}")
        for tag, cen in (("host", h), ("client", c)):
            if soldier_launcher not in cen:
                fails.append(f"{label}/{tag}: the soldier's blaster launcher (item "
                             f"{soldier_launcher}) was DELETED by the alien's shot")
            elif cen[soldier_launcher][1] != soldier["id"]:
                fails.append(f"{label}/{tag}: the soldier's blaster launcher (item "
                             f"{soldier_launcher}) left unit {soldier['id']} -> owner "
                             f"{cen[soldier_launcher][1]}")
        print(f"       host   launchers {owners_of(h, LAUNCHER)}")
        print(f"       client launchers {owners_of(c, LAUNCHER)}")

        # Spawning one more item on each machine must still yield the SAME id: a
        # receiver that fabricated a BattleItem for the replayed shot has bumped
        # its own counter, and the id spaces stay apart for the rest of the battle.
        hp = host.ok({"cmd": "battle_give", "unit": soldier["id"], "item": "STR_PISTOL",
                      "slot": "belt"})
        cp = client.ok({"cmd": "battle_give", "unit": soldier["id"], "item": "STR_PISTOL",
                        "slot": "belt"})
        if hp["weaponId"] != cp["weaponId"]:
            fails.append(f"{label}: item-id spaces drifted apart during the shot (next id: "
                         f"host {hp['weaponId']}, client {cp['weaponId']}) - the peer "
                         f"fabricated a BattleItem for the replayed action")
        else:
            print(f"       item-id spaces still in lockstep (next id {hp['weaponId']})")

        if not any(f.startswith(label) for f in fails):
            print(f"PASS {label}: the alien's blaster launcher shot left every other unit's "
                  f"items alone, identically on both machines")
    except Exception as e:
        print(f"[ERROR] {label}: {e}")
        fails.append(f"{label}: {e}")
    finally:
        js.shutdown()


def main():
    fails = []
    only = os.environ.get("I74_ONLY")
    if only in (None, "right_hand"):
        run_scenario("right_hand", "right", (48796, 48797, 48196), fails)
    if only in (None, "left_hand"):
        run_scenario("left_hand", "left", (48798, 48799, 48198), fails)

    print("\n==== issue #74 summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  an alien's blaster launcher shot replicates without disturbing anyone else's "
          "items and without drifting the two machines' item-id spaces")
    sys.exit(0)


if __name__ == "__main__":
    main()
