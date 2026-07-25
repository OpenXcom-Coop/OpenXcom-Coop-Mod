"""Issue #74 follow-up: does the explosion item-damage divergence exist in
SHARED too, or only in PvP?

test_coop_blast_item_damage.py could not settle this. A blaster bomb (power 200)
is so far above a blaster launcher's armor 40 that every item in radius dies on
any roll, and point-blank it kills the whole squad, after which the death path
converges both machines anyway. Both builds passed, so it proved nothing.

This picks the one case where the two machines can legitimately disagree:

  * a plain STR_GRENADE is power 50, DT_HE, blastRadius 5, and DT_HE's
    RadiusReduction is 10 with Mod::EXPLOSIVE_DAMAGE_RANGE 50 - so
    `type->getRandomDamage(power_)` at the centre tile lands in [25, 75];
  * STR_BLASTER_LAUNCHER's armor is 40, right in the middle of that spread.

So `type->getItemFinalDamage(damage) > bi->getRules()->getArmor()` is marginal
rather than a foregone conclusion. Loose launchers are used because the GROUND
branch of `TileEngine::explode` is the one a client can even evaluate for itself
(`hitUnit` returns false for a non-corpse before its co-op early-return).

Measured with the `explode_items` fix backed out, twice:

    host destroyed 8/8 loose launchers, client destroyed 0/8

So the divergence is NOT PvP-specific - SHARED had it too, and the earlier
blaster-bomb test simply could not show it. The client destroying zero rather
than a different subset says it never reaches the item loop at all, so this is
not just the RNG disagreeing.

Run:  python tools/coop_test/test_coop_shared_blast_ground_items.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import test_coop_alien_launcher_item_loss as I74

LAUNCHER = "STR_BLASTER_LAUNCHER"
GRENADE = "STR_GRENADE"
# NOTE: `damage` is rolled once per TILE, not per item, so every item on the pile
# shares one outcome - these are not independent trials. The count is still worth
# having: it makes the divergence unmissable in the output (8 destroyed vs 0) and
# leaves room to spread items over several tiles later, which WOULD give
# independent rolls.
LOOSE = int(os.environ.get("I74_LOOSE_ITEMS", "8"))


def main():
    fails = []
    js = shared_fixture.bring_up("i74g", (48806, 48807, 48206))
    host, client = js.host, js.client
    try:
        I74.enter_battle(js)

        hb = I74.battle(host)
        soldiers = [u for u in hb["units"] if u["faction"] == 0 and not u["isOut"]]
        assert len(soldiers) >= 2, f"need two soldiers, got {len(soldiers)}"
        holder, thrower = soldiers[0], soldiers[1]
        print(f"       holder soldier {holder['id']} @({holder['x']},{holder['y']},{holder['z']}), "
              f"thrower soldier {thrower['id']} @({thrower['x']},{thrower['y']},{thrower['z']})")

        # Loose launchers on the holder's tile, created identically on both.
        ids = {}
        for tag, gc in (("host", host), ("client", client)):
            ids[tag] = [gc.ok({"cmd": "battle_give", "unit": holder["id"], "item": LAUNCHER,
                               "slot": "ground"})["weaponId"] for _ in range(LOOSE)]
        assert ids["host"] == ids["client"], \
            f"item ids diverged while seeding: {ids['host']} vs {ids['client']}"
        print(f"       {LOOSE} loose launchers on the ground at the holder's tile: {ids['host']}")

        # A primed grenade only detonates on impact with this on - otherwise
        # BattleItem::fuseThrowEvent lets it land and wait for the turn to tick.
        for gc in (host, client):
            gc.ok({"cmd": "set_option", "name": "battleInstantGrenade", "value": True})

        # A primed grenade in the thrower's hand, on both machines.
        gren = {}
        for tag, gc in (("host", host), ("client", client)):
            gren[tag] = gc.ok({"cmd": "battle_give", "unit": thrower["id"], "item": GRENADE,
                               "slot": "right", "clear_hands": True, "fuse": 0})["weaponId"]
        assert gren["host"] == gren["client"], f"grenade ids diverged: {gren}"

        pre_h, pre_c = I74.census(host), I74.census(client)
        d0 = I74.diff_census(pre_h, pre_c)
        assert not d0, f"censuses diverged BEFORE the throw: {d0}"
        print(f"PASS pre-throw: {len(pre_h)} item instances, identical on both machines")

        def _sim_owner():
            for gc, tag in ((host, "host"), (client, "client")):
                if I74.battle(gc).get("activeSync"):
                    return (gc, tag)
            return None

        shooter, shooter_tag = host.wait_for("a machine to own the battle simulation",
                                             _sim_owner, timeout=90, interval=1.0)
        r = shooter.ok({"cmd": "battle_fire", "unit": thrower["id"], "mode": "throw",
                        "weapon_id": gren["host"], "tu": 200,
                        "x": holder["x"], "y": holder["y"], "z": holder["z"]})
        print(f"       thrower lobs a primed grenade onto the pile from the {shooter_tag} "
              f"(tu cost {r['tuCost']})")

        I74.settle(host, client, seconds=10)

        post_h, post_c = I74.census(host), I74.census(client)
        gone_h = [i for i in ids["host"] if i not in post_h]
        gone_c = [i for i in ids["client"] if i not in post_c]
        print(f"       host destroyed {len(gone_h)}/{LOOSE} loose launchers: {gone_h}")
        print(f"       client destroyed {len(gone_c)}/{LOOSE} loose launchers: {gone_c}")
        if gone_h != gone_c:
            fails.append(f"the two machines destroyed DIFFERENT loose launchers - "
                         f"host {gone_h}, client {gone_c}")
        if not gone_h and not gone_c:
            fails.append("the grenade destroyed nothing on either machine - the blast "
                         "never reached the pile, so this run proves nothing")

        d = I74.diff_census(post_h, post_c)
        if d:
            for line in d[:15]:
                print(f"  [DIVERGE] {line}")
            fails.append(f"post-blast item census diverged ({len(d)} items)")
    except Exception as e:
        print(f"[ERROR] {e}")
        fails.append(str(e))
    finally:
        js.shutdown()

    print("\n==== issue #74 SHARED ground-item blast summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  in a SHARED battle, a marginal-damage blast destroys the SAME loose items "
          "on both machines")
    sys.exit(0)


if __name__ == "__main__":
    main()
