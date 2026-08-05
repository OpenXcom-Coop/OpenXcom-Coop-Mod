"""PvP skirmish item census: both machines hold identical items after combat.

After a weapon is fired in PvP, the item census (id, type, owner) must match
on both machines. This is the same invariant tested by the Issue #74 blaster
test, generalized to other weapons and both gamemodes.

Run:  python tools/coop_test/test_pvp_skirmish_census.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture as PVP

PORT = "47998"


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def census(gc):
    return {i["id"]: (i["type"], i["owner"])
            for i in gc.ok({"cmd": "battle_items"})["items"]}


def diff_census(h, c):
    out = []
    for iid in sorted(set(h) | set(c)):
        a, b = h.get(iid), c.get(iid)
        if a == b:
            continue
        if a is None:
            out.append(f"item {iid} {b[0]} ONLY on client (owner {b[1]})")
        elif b is None:
            out.append(f"item {iid} {a[0]} ONLY on host (owner {a[1]})")
        else:
            out.append(f"item {iid} {a[0]}: host owner {a[1]} vs "
                       f"client owner {b[1]}")
    return out


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def test_census(fails, alien_player, gamemode):
    tag = f"gm{gamemode}_{alien_player}"
    print(f"\n--- census {tag} ---")
    host = GameClient("host", 48914, make_user_dir(f"pvp_cen_{tag}_host"))
    client = GameClient("client", 48915, make_user_dir(f"pvp_cen_{tag}_client"))
    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        gm = PVP.start_pvp_skirmish_battle(host, client, PORT,
                                           alien_player=alien_player)
        if gm != gamemode:
            _fail(fails, f"{tag}: expected {gamemode}, got {gm}")
            return

        pre_h, pre_c = census(host), census(client)
        d0 = diff_census(pre_h, pre_c)
        if d0:
            _fail(fails, f"{tag}: pre-shot census diverged: {d0}")
            return
        print(f"    pre-shot: {len(pre_h)} items, identical on both machines")

        # Find the executor and give weapons
        hb = battle(host)
        cb = battle(client)
        executor = host if hb.get("coopTurn") == 2 else client

        # Find executor's and enemy's units. In PvP, factions are remapped
        # per machine: on the executor the enemy appears as the opposite
        # faction. The executor's selectable units are the correct side.
        eb = battle(executor)
        executor_sel = [u for u in eb.get("units", [])
                        if u.get("selectable") and not u.get("isOut")]
        enemy = [u for u in eb.get("units", [])
                 if not u.get("selectable") and not u.get("isOut")
                 and u["faction"] != eb.get("side", -1)]

        if not executor_sel or not enemy:
            _fail(fails, f"{tag}: need both sides with units "
                  f"(sel={len(executor_sel)} enemy={len(enemy)})")
            return

        # Give rifles to executor's units
        for gc in (host, client):
            for s in executor_sel[:2]:
                gc.ok({"cmd": "battle_give", "unit": s["id"],
                       "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP",
                       "slot": "right", "clear_hands": True})

        pre2_h, pre2_c = census(host), census(client)
        time.sleep(1)
        d1 = diff_census(pre2_h, pre2_c)
        if d1:
            _fail(fails, f"{tag}: post-give census diverged: {d1}")
            return
        print(f"    post-give: {len(pre2_h)} items, still identical")

        # Fire a rifle from executor at the enemy
        shooter = executor_sel[0]
        rifle_id = next(i for i, (t, o) in pre2_h.items()
                        if t == "STR_RIFLE" and o == shooter["id"])
        executor.cmd({"cmd": "battle_action", "action": "select",
                      "unit": shooter["id"]})
        target = enemy[0]
        res = executor.cmd({"cmd": "battle_action", "action": "fire",
                            "unit": shooter["id"], "target": target["id"],
                            "weapon_id": rifle_id, "mode": "snap"})
        print(f"    fire result: ok={res.get('ok')} "
              f"hit={res.get('hit', '?')}")

        time.sleep(3)

        post_h, post_c = census(host), census(client)
        d2 = diff_census(post_h, post_c)
        if d2:
            _fail(fails, f"{tag}: post-shot census diverged ({len(d2)}): "
                  f"{d2[:5]}")
        else:
            print(f"PASS {tag}: post-shot {len(post_h)} items, "
                  f"identical on both machines")

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        client.shutdown()


def main():
    fails = []
    test_census(fails, "client", 2)
    test_census(fails, "host", 3)

    print("\n==== PvP skirmish census summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: item census matches after weapon fire")
    sys.exit(0)


if __name__ == "__main__":
    main()
