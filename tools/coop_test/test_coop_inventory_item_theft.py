"""Issue #74, the REPORTED SYMPTOM: an alien firing a blaster launcher ends with
an X-COM soldier's blaster launcher gone from their hands on the peer machine.

This is the full chain, not just the desync that starts it:

  1. An alien fires its blaster launcher with the launcher in a hand the coop
     packet does not name (nobody clicks a hand button for an AI actor, so the
     packet reports `BattlescapeState::_hand`, stuck at its "right" default).
     The peer cannot resolve the weapon and FABRICATES a `new BattleItem`, whose
     id comes from `SavedBattleGame::getCurrentItemId()` - which it
     post-increments. The peer's item-id counter is now one ahead of the
     shooter's, permanently.

  2. From that moment the same logical item has DIFFERENT ids on the two
     machines. When a player then moves an item in the mid-battle inventory,
     `BattlescapeState::moveCoopInventory` looks the item up on the peer by
     (id, name) - and the id now lands on a DIFFERENT blaster launcher, the one
     in another soldier's hands. `TileEngine::itemMoveInventory` then moves THAT
     one into the mover's slot.

  Net effect on the peer: the victim soldier is empty-handed and the mover is
  holding two launchers - "alien shooting blaster launcher removes X-COM blaster
  launcher from soldier inventory".

The test asserts the symptom directly: after the alien's shot and one ordinary
inventory move, the victim soldier must still be holding the launcher instance
it started with, on BOTH machines.

PRD-P4 additionally makes the census assertion STRICT and un-filtered, at both
the shot and the move: the blast kills the firing alien, and a corpse is a Tier-A
spawn (a deterministic set each machine creates for itself), so a corpse id that
differs between the two machines is exactly the drift the id-manifest removes -
not noise to be filtered out. The fixed `time.sleep` that used to precede the
comparison is a `wait_quiesced()` symmetric-poll barrier instead.

Run:  python tools/coop_test/test_coop_inventory_item_theft.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import shared_fixture
import test_shared_battle as B
import test_coop_alien_launcher_item_loss as I74

LAUNCHER = "STR_BLASTER_LAUNCHER"
BOMB = "STR_BLASTER_BOMB"


def held_by(gc, unit_id, itype):
    """Ids of `itype` instances currently owned by `unit_id`."""
    return sorted(i["id"] for i in gc.ok({"cmd": "battle_items"})["items"]
                  if i["type"] == itype and i["owner"] == unit_id)


def where(gc, item_id):
    """(ownerUnitId, slot) of one item instance - a hand swap is corruption too,
    so the test pins the slot, not just the owner."""
    for i in gc.ok({"cmd": "battle_items"})["items"]:
        if i["id"] == item_id:
            return (i["owner"], i["slot"])
    return (None, None)


def soldier_name(gc, unit_id):
    for u in I74.battle(gc)["units"]:
        if u["id"] == unit_id:
            return u["name"]
    raise AssertionError(f"no unit {unit_id}")


def wait_quiesced(host, client, stable_samples=4, max_wait=60, settle=2.0):
    """Symmetric-poll barrier: block until BOTH machines' item censuses have held
    still for `stable_samples` consecutive samples.

    The assertions below compare REAL ids with no filtering, so they must not run
    in the middle of a replay. The alien's blaster shot kills the firing alien, and
    the death/corpse/drop sequence has pauses longer than one sample, so a fixed
    `time.sleep` either flakes (too short - a corpse lands between the two reads)
    or burns a minute on every run. Poll both sides and wait for quiet instead.
    """
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


def assert_census_strict(host, client, what, fails):
    """PRD-P4: full-census equality on real ids - no per-type filter, no "ignore
    the corpses" escape hatch. A corpse whose id differs between the two machines
    IS the drift this PRD removes (the host now names the ids it minted on
    `after_unit_death` and the peer re-stamps its own copies), so hiding it here
    would hide the only symptom the pilot has.
    """
    d = I74.diff_census(I74.census(host), I74.census(client))
    if d:
        for line in d:
            print(f"  [DIVERGE] {line}")
        fails.append(f"host/client item census diverged {what} ({len(d)} items)")
        return False
    # ... and the counter, which a census comparison cannot see: two machines can
    # hold identical item sets while one is primed to mint the next id differently.
    try:
        session.assert_battle_synced(host, client, what)
    except AssertionError as e:
        fails.append(str(e))
        return False
    print(f"       census + item-id counter identical {what}")
    return True


def main():
    fails = []
    js = shared_fixture.bring_up("i74t", (48800, 48801, 48200))
    host, client = js.host, js.client
    try:
        I74.enter_battle(js)

        hb = I74.battle(host)
        soldiers = [u for u in hb["units"] if u["faction"] == 0 and not u["isOut"]]
        aliens = [u for u in hb["units"] if u["faction"] == 1 and not u["isOut"]]
        assert len(soldiers) >= 2, f"need two X-COM soldiers, got {len(soldiers)}"
        assert aliens, "no aliens in this battle"
        victim, mover, alien = soldiers[0], soldiers[1], aliens[0]
        print(f"       victim soldier {victim['id']} ({soldier_name(host, victim['id'])}), "
              f"mover soldier {mover['id']} ({soldier_name(host, mover['id'])}), "
              f"alien {alien['id']}")

        # ---- step 1: the alien's shot, launcher in the UNNAMED hand ---------
        for gc in (host, client):
            I74.arm(gc, alien["id"], "left")
        alien_launcher = I74.census(host)
        alien_launcher = max(i for i, (t, o) in alien_launcher.items()
                             if t == LAUNCHER and o == alien["id"])

        def _sim_owner():
            for gc, tag in ((host, "host"), (client, "client")):
                if session.can_drive(I74.battle(gc)):
                    return (gc, tag)
            return None

        shooter, shooter_tag = host.wait_for("a machine to own the battle simulation",
                                             _sim_owner, timeout=90, interval=1.0)
        shooter.ok({"cmd": "battle_fire", "unit": alien["id"], "mode": "launch",
                    "weapon_id": alien_launcher, "tu": 200,
                    "waypoints": [{"x": alien["x"], "y": alien["y"], "z": alien["z"]}]})
        print(f"       alien launches from the {shooter_tag} with its launcher in the "
              f"LEFT hand (the packet says 'right')")
        I74.settle(host, client)
        # The blast kills the firing alien, so this is where its corpses are minted
        # on each machine independently - PRD-P4's Tier-A case. Assert here as well
        # as at the end, so a corpse-id drift is attributed to the shot rather than
        # to the inventory move that follows.
        assert_census_strict(host, client, "after the alien's shot", fails)

        # ---- step 2: two launchers, created in the same order on both -------
        # If step 1 drifted the id spaces, the SAME logical launcher now carries
        # different ids on the two machines - which is the whole point.
        # Bare launchers, no clips: with a one-step drift, creating the victim's
        # launcher immediately before the mover's makes the mover's HOST id land
        # exactly on the victim's launcher on the CLIENT - so the peer's (id,name)
        # lookup matches the wrong launcher and the reported symptom appears as
        # written. Clips in between would put a blaster bomb at that id instead
        # (still stolen, just a different item).
        given = {}
        for tag, gc in (("host", host), ("client", client)):
            given[tag] = [
                gc.ok({"cmd": "battle_give", "unit": victim["id"], "item": LAUNCHER,
                       "slot": "right", "clear_hands": True}),
                gc.ok({"cmd": "battle_give", "unit": mover["id"], "item": LAUNCHER,
                       "slot": "right", "clear_hands": True}),
            ]
        h_victim, h_mover = (g["weaponId"] for g in given["host"])
        c_victim, c_mover = (g["weaponId"] for g in given["client"])
        drift = (h_victim != c_victim) or (h_mover != c_mover)
        print(f"       victim launcher: host id {h_victim}, client id {c_victim}")
        print(f"       mover  launcher: host id {h_mover}, client id {c_mover}")
        print(f"       item-id spaces {'DRIFTED' if drift else 'in lockstep'} after the shot")

        for gc, tag, vid in ((host, "host", h_victim), (client, "client", c_victim)):
            assert held_by(gc, victim["id"], LAUNCHER) == [vid], \
                f"{tag}: victim is not holding exactly its own launcher before the move"

        # ---- step 3: ONE ordinary inventory action on the mover -------------
        # The mover DROPS its own launcher - about the most mundane thing a
        # player does mid-battle. It has to be a drop rather than a hand swap:
        # `TileEngine::itemMoveInventory` only re-owners an item when the
        # destination is the ground, so that is the move that can actually take
        # an item off a soldier on the peer.
        before = {tag: where(gc, iid) for tag, gc, iid in
                  (("host", host, h_victim), ("client", client, c_victim))}
        mover_name = soldier_name(host, mover["id"])
        host.ok({"cmd": "battle_open_inventory", "unit": mover["id"]})
        moved = host.ok({"cmd": "inventory_move", "name": mover_name,
                         "item": LAUNCHER, "slot": "ground", "from": "unit"})
        print(f"       host DROPPED the MOVER's own launcher "
              f"(landed {moved.get('landedSlot')}, onUnit={moved.get('landedOnUnit')})")
        host.ok({"cmd": "battle_close_inventory"})
        if not wait_quiesced(host, client):
            print("       NOTE: the two machines never went quiet within 60s; "
                  "asserting on the last reading")

        # ---- the symptom ----------------------------------------------------
        for gc, tag, vid in ((host, "host", h_victim), (client, "client", c_victim)):
            now = where(gc, vid)
            got = held_by(gc, victim["id"], LAUNCHER)
            print(f"       {tag}: victim launcher {vid} was {before[tag]}, now {now}; "
                  f"victim holds {got}")
            if now != before[tag]:
                fails.append(f"{tag}: the VICTIM soldier {victim['id']} had its blaster "
                             f"launcher (item {vid}) moved from {before[tag]} to {now} by "
                             f"the peer's replayed inventory action - nobody touched it")
            if got != [vid]:
                fails.append(f"{tag}: the VICTIM soldier {victim['id']} should still hold "
                             f"launcher {vid}, but holds {got}")

        assert_census_strict(host, client, "after the inventory move", fails)
    except Exception as e:
        print(f"[ERROR] {e}")
        fails.append(str(e))
    finally:
        js.shutdown()

    print("\n==== issue #74 inventory-theft summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  after an alien's blaster launcher shot, an ordinary inventory move leaves "
          "every soldier holding its own launcher on both machines")
    sys.exit(0)


if __name__ == "__main__":
    main()
