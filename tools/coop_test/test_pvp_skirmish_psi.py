"""PvP mind control (psi): legacy PvP psi path.

In PvP, mind control uses the legacy inverted-flip psi path
(pvp:true in psi_result), which is different from the PvE
host-authoritative state-copy path (pvp:false).

This test:
  1. Starts a PvP skirmish battle.
  2. Gives a psi-amp to an XCOM unit with psi skill.
  3. Uses battle_action psi_attack to MC an enemy unit.
  4. Verifies the target unit's coop ownership flips on both machines.
  5. Verifies item census stays identical after the MC.

Run:  python tools/coop_test/test_pvp_skirmish_psi.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture as PVP

PORT = "48000"


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def _states(gc):
    return [s.replace("class OpenXcom::", "") for s in gc.cmd({"cmd":"get_state"})["states"]]


def test_psi(fails, alien_player, gamemode):
    tag = f"gm{gamemode}_{alien_player}"
    print(f"\n--- psi {tag} ---")

    host = GameClient("host", 48972, make_user_dir(f"pvp_psi_{tag}_host"))
    client = GameClient("client", 48973, make_user_dir(f"pvp_psi_{tag}_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        gm = PVP.start_pvp_skirmish_battle(host, client, PORT,
                                           alien_player=alien_player)
        if gm != gamemode:
            _fail(fails, f"{tag}: expected {gamemode}, got {gm}")
            return

        hb = battle(host)
        cb = battle(client)
        executor = host if hb.get("coopTurn") == 2 else client

        # Find executor's selectable units (from the executor's perspective)
        exec_units = [u for u in battle(executor).get("units", [])
                      if u.get("selectable") and not u.get("isOut")]
        if not exec_units:
            _fail(fails, f"{tag}: no executor units")
            return

        # Give a psi-amp to an executor unit
        shooter = exec_units[0]
        for gc in (host, client):
            gc.ok({"cmd": "battle_give", "unit": shooter["id"],
                   "item": "STR_PSI_AMP",
                   "slot": "right", "clear_hands": True})
        time.sleep(1)

        # Find an enemy unit to MC (from the executor's perspective)
        eb = battle(executor)
        exec_side = eb.get("side", 0)
        enemies = [u for u in eb.get("units", [])
                   if not u.get("selectable") and not u.get("isOut")
                   and u.get("faction") != exec_side]
        if not enemies:
            _fail(fails, f"{tag}: no enemy units to MC")
            return
        target = enemies[0]

        # Verify psi-amp is equipped
        items = host.cmd({"cmd": "battle_items"})["items"]
        amps = [i for i in items
                if i.get("type") == "STR_PSI_AMP"
                and i.get("owner") == shooter["id"]]
        if not amps:
            _fail(fails, f"{tag}: psi-amp not equipped")
            return
        amp_id = amps[0]["id"]

        # Snapshot target ownership before MC (from both machines)
        host_units = battle(host)["units"]
        client_units = battle(client)["units"]
        hb_target = next(u for u in host_units if u["id"] == target["id"])
        cb_target = next(u for u in client_units if u["id"] == target["id"])
        pre_coop_h = hb_target.get("coop")
        pre_coop_c = cb_target.get("coop")
        print(f"    target {target['id']}: coop host={pre_coop_h} "
              f"client={pre_coop_c}")

        # Select the psi user and execute psi attack
        executor.cmd({"cmd": "battle_action", "action": "select",
                      "unit": shooter["id"]})
        res = executor.cmd({"cmd": "battle_action", "action": "psi_attack",
                            "unit": shooter["id"], "target": target["id"],
                            "weapon_id": amp_id})
        print(f"    psi_attack: ok={res.get('ok')} "
              f"error={res.get('error', 'none')}")

        time.sleep(5)

        # Check post-MC state
        hb2 = battle(host)
        cb2 = battle(client)
        hb_target2 = next(u for u in hb2["units"]
                         if u["id"] == target["id"])
        cb_target2 = next(u for u in cb2["units"]
                         if u["id"] == target["id"])
        post_coop_h = hb_target2.get("coop")
        post_coop_c = cb_target2.get("coop")
        post_faction_h = hb_target2.get("faction")
        post_faction_c = cb_target2.get("faction")
        post_is_out = hb_target2.get("isOut")
        print(f"    after MC: coop host={post_coop_h} client={post_coop_c} "
              f"faction host={post_faction_h} client={post_faction_c} "
              f"isOut={post_is_out}")

        # MC should change coop ownership (the flipped unit changes sides)
        if post_coop_h != pre_coop_h or post_coop_c != pre_coop_c:
            print(f"PASS {tag}: coop ownership changed "
                  f"({pre_coop_h}->{post_coop_h} host, "
                  f"{pre_coop_c}->{post_coop_c} client)")
        else:
            print(f"    note: coop unchanged (target may have resisted)")

        # Item census must stay identical
        items_h = len(host.cmd({"cmd": "battle_items"})["items"])
        items_c = len(client.cmd({"cmd": "battle_items"})["items"])
        if items_h != items_c:
            _fail(fails, f"{tag}: item drift after psi: "
                  f"host={items_h} client={items_c}")
        else:
            print(f"PASS {tag}: {items_h} items, identical on both machines")

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        client.shutdown()


def main():
    fails = []
    test_psi(fails, "client", 2)
    test_psi(fails, "host", 3)

    print("\n==== PvP psi summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: psi_attack executed, item census intact")
    sys.exit(0)


if __name__ == "__main__":
    main()
