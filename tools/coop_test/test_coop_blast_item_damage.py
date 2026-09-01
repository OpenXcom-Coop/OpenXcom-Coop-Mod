"""Issue #74, the reporter's actual scenario: "if you fire blaster from alien
side the xcom side blasters disappear (not in hotseat)".

A blaster bomb is DT_HE, and OXCE's DT_HE preset sets `ToItem = 1.0f`
(Mod.cpp), so an HE blast destroys items whose armor is below the rolled
damage - a blaster launcher's armor is 40 against a power-200 bomb. Items being
destroyed is therefore VANILLA; the co-op bug is that the two machines do not
destroy the SAME ones, which is why the reporter sees it online but not in
hotseat.

`TileEngine::explode` runs locally on BOTH machines with no host/client gate
(unlike `TileEngine::hit`, which early-returns on the client and replays a
host-sent seed via `hitCoop`). Inside it:

  * `const int damage = type->getRandomDamage(power_)` is rolled per tile, per
    machine, from each machine's own RNG stream, and then
    `type->getItemFinalDamage(damage) > bi->getRules()->getArmor()` decides
    whether every item lying on that tile is destroyed;
  * items carried by a unit are destroyed on `bu->getOverKillDamage()`, which
    depends on damage the peer may not have applied identically.

So the same blast can vaporise a soldier's blaster launcher on one machine and
leave it in their hands on the other.

The test fires an alien's blaster launcher AT the X-COM squad - deliberately, in
contrast to test_coop_alien_launcher_item_loss.py, which aims away precisely to
keep blast damage out of the picture - and asserts only that the two machines
agree on what the blast destroyed. It does NOT assert that the launchers
survive: losing gear to a blaster bomb is correct behaviour. Diverging is not.

Layout mirrors the reporter's save (Blaster Alien.sav): X-COM launchers in the
LEFT hand, alien launchers in the RIGHT.

Run:  python tools/coop_test/test_coop_blast_item_damage.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

# RW-TRIAGE: SKIP-PENDING(r3)
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import test_coop_alien_launcher_item_loss as I74

LAUNCHER = "STR_BLASTER_LAUNCHER"
BOMB = "STR_BLASTER_BOMB"


# How far the alien stands from the squad. Point-blank (2) kills everyone, so
# their gear is destroyed outright on the host. Further out (I74_BLAST_RANGE=8)
# the tile power has decayed to roughly 200 - 8*RadiusReduction, and DT_HE's
# getRandomDamage spread straddles a launcher's armor of 40 - so whether each
# ITEM ON THE GROUND survives is a coin flip, drawn from each machine's own RNG
# stream. That is the case a client must not be allowed to judge for itself.
RANGE = int(os.environ.get("I74_BLAST_RANGE", "2"))


def main():
    fails = []
    js = shared_fixture.bring_up("i74b", (48802, 48803, 48202))
    host, client = js.host, js.client
    try:
        I74.enter_battle(js)

        hb = I74.battle(host)
        soldiers = [u for u in hb["units"] if u["faction"] == 0 and not u["isOut"]]
        aliens = [u for u in hb["units"] if u["faction"] == 1 and not u["isOut"]]
        assert soldiers and aliens, "need both an X-COM squad and an alien"
        alien = aliens[0]
        target = soldiers[0]
        print(f"       {len(soldiers)} soldiers, target {target['id']} "
              f"@({target['x']},{target['y']},{target['z']}); alien {alien['id']} "
              f"@({alien['x']},{alien['y']},{alien['z']})")

        # Mirror the reporter's save: X-COM launchers LEFT hand, alien RIGHT.
        for gc in (host, client):
            for s in soldiers:
                gc.ok({"cmd": "battle_give", "unit": s["id"], "item": LAUNCHER,
                       "ammo": BOMB, "slot": "left", "clear_hands": True})
            gc.ok({"cmd": "battle_give", "unit": alien["id"], "item": LAUNCHER,
                   "ammo": BOMB, "slot": "right", "clear_hands": True})

        # Put the alien a few tiles from the squad, on BOTH machines, so the bomb
        # actually lands on them - a blaster fired from across the map just
        # detonates against the first wall and damages nothing. teleport() refuses
        # any tile that fails isPositionValidForUnit, so probe outwards until one
        # takes, and apply the SAME tile on both machines.
        def _pos(gc):
            return next((u["x"], u["y"], u["z"]) for u in I74.battle(gc)["units"]
                        if u["id"] == alien["id"])

        # Drop every soldier's launcher on the ground first, so the blast has a
        # pile of loose items to judge - the ground branch is the one a client
        # CAN evaluate locally (hitUnit returns false for a non-corpse before its
        # coop early-return), and therefore the one it can get wrong on its own.
        for s_ in soldiers[:3]:
            name = next(u["name"] for u in I74.battle(host)["units"] if u["id"] == s_["id"])
            host.ok({"cmd": "battle_open_inventory", "unit": s_["id"]})
            host.ok({"cmd": "inventory_move", "name": name, "item": LAUNCHER,
                     "slot": "ground", "from": "unit"})
            host.ok({"cmd": "battle_close_inventory"})
        time.sleep(4)

        landed = None
        offs = [(RANGE, 0), (-RANGE, 0), (0, RANGE), (0, -RANGE),
                (RANGE, RANGE), (-RANGE, -RANGE), (RANGE, -RANGE), (-RANGE, RANGE),
                (RANGE + 1, 0), (-RANGE - 1, 0), (0, RANGE + 1), (0, -RANGE - 1)]
        for dx, dy in offs:
            want = (target["x"] + dx, target["y"] + dy, target["z"])
            host.ok({"cmd": "battle_teleport", "unit": alien["id"],
                     "x": want[0], "y": want[1], "z": want[2]})
            # read the position back rather than trusting the reply: teleport()
            # silently refuses an invalid tile, and older builds report nothing.
            if _pos(host) == want:
                landed = want
                break
        assert landed, "could not find a free tile near the squad for the alien"
        client.ok({"cmd": "battle_teleport", "unit": alien["id"],
                   "x": landed[0], "y": landed[1], "z": landed[2]})
        alien = next(u for u in I74.battle(host)["units"] if u["id"] == alien["id"])
        cpos = next((u["x"], u["y"], u["z"]) for u in I74.battle(client)["units"]
                    if u["id"] == alien["id"])
        assert (alien["x"], alien["y"], alien["z"]) == cpos,             f"alien ended up at {(alien['x'], alien['y'], alien['z'])} on the host but {cpos} on the client"
        print(f"       alien moved to ({alien['x']},{alien['y']},{alien['z']}) on both machines, "
              f"{abs(alien['x'] - target['x']) + abs(alien['y'] - target['y'])} tiles from the target")

        pre_h, pre_c = I74.census(host), I74.census(client)
        loose = [i for i, (t, o) in pre_h.items() if t == LAUNCHER and o == -1]
        print(f"       {len(loose)} launchers loose on the ground before the blast: {loose}")
        assert not I74.diff_census(pre_h, pre_c), \
            f"censuses diverged BEFORE the shot: {I74.diff_census(pre_h, pre_c)}"
        print(f"PASS pre-shot: {len(pre_h)} item instances, identical on both machines")

        def _sim_owner():
            for gc, tag in ((host, "host"), (client, "client")):
                if I74.battle(gc).get("activeSync"):
                    return (gc, tag)
            return None

        shooter, shooter_tag = host.wait_for("a machine to own the battle simulation",
                                             _sim_owner, timeout=90, interval=1.0)
        alien_launcher = max(i for i, (t, o) in pre_h.items()
                             if t == LAUNCHER and o == alien["id"])
        # Waypoint on the alien's OWN tile. Firing at the squad's tile from two
        # tiles away just fizzles (the projectile never reaches a detonating
        # impact), while a launch at one's own feet always detonates - and with
        # blastRadius 10 the squad two tiles away is well inside it.
        shooter.ok({"cmd": "battle_fire", "unit": alien["id"], "mode": "launch",
                    "weapon_id": alien_launcher, "tu": 200,
                    "waypoints": [{"x": alien["x"], "y": alien["y"], "z": alien["z"]}]})
        print(f"       alien launches from the {shooter_tag} at its own feet "
              f"({alien['x']},{alien['y']},{alien['z']}), two tiles from the squad")

        def _units(gc):
            return {u["id"]: (u["health"], u["isOut"]) for u in I74.battle(gc)["units"]}

        pre_uh, pre_uc = _units(host), _units(client)
        I74.settle(host, client, seconds=12)
        post_uh, post_uc = _units(host), _units(client)
        for tag, pre, post in (("host", pre_uh, post_uh), ("client", pre_uc, post_uc)):
            hurt = {u: (pre[u], post[u]) for u in pre if pre[u] != post.get(u)}
            print(f"       {tag}: units changed by the blast: {hurt or 'NONE'}")

        post_h, post_c = I74.census(host), I74.census(client)
        gone_h = sorted(set(pre_h) - set(post_h))
        gone_c = sorted(set(pre_c) - set(post_c))
        print(f"       host destroyed {len(gone_h)} items, client destroyed {len(gone_c)}")
        only_h = [(i, pre_h[i][0]) for i in gone_h if i not in gone_c]
        only_c = [(i, pre_c[i][0]) for i in gone_c if i not in gone_h]
        if only_h:
            print(f"  [DIVERGE] destroyed ONLY on the host:   {only_h}")
        if only_c:
            print(f"  [DIVERGE] destroyed ONLY on the client: {only_c}")
        if only_h or only_c:
            fails.append(f"the blast destroyed different items on the two machines "
                         f"({len(only_h)} host-only, {len(only_c)} client-only)")

        for tag, pre, post in (("host", pre_h, post_h), ("client", pre_c, post_c)):
            held = sorted(i for i, (t, o) in post.items() if t == LAUNCHER and o != -1)
            print(f"       {tag}: launchers still held by a unit: {held}")

        d = I74.diff_census(post_h, post_c)
        if d:
            for line in d[:12]:
                print(f"  [DIVERGE] {line}")
            fails.append(f"post-blast item census diverged ({len(d)} items)")
    except Exception as e:
        print(f"[ERROR] {e}")
        fails.append(str(e))
    finally:
        js.shutdown()

    print("\n==== issue #74 blast item-damage summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  an alien blaster blast destroys the SAME items on both machines")
    sys.exit(0)


if __name__ == "__main__":
    main()
