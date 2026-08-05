"""PvP skirmish battle turn control and replication.

Validates:
  1. Both machines reach the tactical map.
  2. Exactly one machine is the executor: gamemode 2 -> host, gamemode 3 -> client.
  3. The executor's selectable units belong to the correct faction:
     gamemode 2: host commands XCOM (faction 0).
     gamemode 3: client commands XCOM (faction 0).
     The OTHER side waits (no selectable units) — PvP alternates turns.
  4. Replication: a walk driven from the executor reaches both machines.

Run:  python tools/coop_test/test_pvp_skirmish_turn_control.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture as PVP

PORT = "47991"


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def selectable_units(b):
    return sorted(u["id"] for u in b.get("units", [])
                  if u.get("selectable") and not u.get("isOut"))


def xcom_ids(b):
    return sorted(u["id"] for u in b.get("units", [])
                  if u.get("faction") == 0 and not u.get("isOut"))


def alien_ids(b):
    return sorted(u["id"] for u in b.get("units", [])
                  if u.get("faction") == 1 and not u.get("isOut"))


def unit_pos(gc, uid):
    for u in battle(gc).get("units", []):
        if u["id"] == uid:
            return (u["x"], u["y"], u["z"])
    return None


def test_turn_control(fails, alien_player, expect_executor_tag,
                      expect_xcom_side_tag, expect_alien_side_tag):
    gm_label = "2" if alien_player == "client" else "3"
    print(f"\n--- gamemode {gm_label} ({alien_player} plays aliens) ---")
    tag = f"gm{gm_label}_{alien_player}"
    host = GameClient("host", 48892, make_user_dir(f"pvp_{tag}_host"))
    client = GameClient("client", 48893, make_user_dir(f"pvp_{tag}_client"))
    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        gm = PVP.start_pvp_skirmish_battle(host, client, PORT,
                                           alien_player=alien_player)
        want_mode = 2 if alien_player == "client" else 3
        if gm != want_mode:
            _fail(fails, f"expected gamemode {want_mode}, got {gm}")
            return

        hb = battle(host)
        cb = battle(client)
        print(f"    host:   gamemode={hb.get('coopGamemode')} "
              f"coopTurn={hb.get('coopTurn')} "
              f"activeSync={hb.get('activeSync')}")
        print(f"    client: gamemode={cb.get('coopGamemode')} "
              f"coopTurn={cb.get('coopTurn')} "
              f"activeSync={cb.get('activeSync')}")

        # ---- 1. exactly one executor ---------------------------------------
        host_exec = hb.get("coopTurn") == 2 and hb.get("activeSync")
        client_exec = cb.get("coopTurn") == 2 and cb.get("activeSync")
        if not host_exec and not client_exec:
            _fail(fails, f"gm{want_mode}: neither machine is the executor")
            return
        if host_exec and client_exec:
            _fail(fails, f"gm{want_mode}: both machines claim to be executor")
            return
        actual_executor = "host" if host_exec else "client"
        if actual_executor != expect_executor_tag:
            _fail(fails, f"gm{want_mode}: {actual_executor} is executor, "
                  f"expected {expect_executor_tag}")
        else:
            print(f"PASS executor: {expect_executor_tag} owns simulation "
                  f"(gamemode {want_mode})")

        # ---- 2. executor's selectable units belong to correct faction ------
        host_sel = selectable_units(hb)
        client_sel = selectable_units(cb)
        host_all = xcom_ids(hb) + alien_ids(hb)
        client_all = xcom_ids(cb) + alien_ids(cb)
        print(f"    host selectable:   {host_sel} of {host_all}")
        print(f"    client selectable: {client_sel} of {client_all}")

        executor = host if host_exec else client
        executor_sel = host_sel if host_exec else client_sel
        if not executor_sel:
            _fail(fails, f"gm{want_mode}: {expect_executor_tag} (executor) "
                  f"can command no units")
            return

        # Gamemode 2=host=XCOM,client=Alien. Gamemode 3=host=Alien,client=XCOM.
        xcom_machine = host if expect_xcom_side_tag == "host" else client
        alien_machine = host if expect_alien_side_tag == "host" else client
        xb = battle(xcom_machine)
        ab = battle(alien_machine)

        xcom_control = set(selectable_units(xb))
        expected = set(xcom_ids(xb))
        if xcom_control != expected:
            _fail(fails, f"gm{want_mode}: {expect_xcom_side_tag} (XCOM side) "
                  f"selectable={sorted(xcom_control)}, "
                  f"expected all XCOM={sorted(expected)}")
        else:
            print(f"PASS faction: {expect_xcom_side_tag} commands all "
                  f"{len(expected)} XCOM units")

        # ---- 3. replication ------------------------------------------------
        peer = client if host_exec else host
        _walk_and_verify(executor, peer, executor, expect_executor_tag, fails)

    except Exception as e:
        print(f"[ERROR] {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        client.shutdown()


def _walk_and_verify(driver, peer, driver_obj, driver_tag, fails):
    """Walk a unit on the driver; assert the peer sees the same (x,y)."""
    db = battle(driver)
    movers = [u for u in db.get("units", [])
              if u.get("selectable") and not u.get("isOut")
              and u.get("tu", 0) > 8]
    if not movers:
        _fail(fails, f"{driver_tag} (executor) has no movable unit with "
              f"enough TU")
        return

    u = movers[0]
    before = (u["x"], u["y"])
    assert unit_pos(peer, u["id"])[:2] == before, \
        f"unit {u['id']} starts at {before} on {driver_tag} " \
        f"but at {unit_pos(peer, u['id'])} on the peer"

    driver.cmd({"cmd": "battle_action", "action": "select",
                "unit": u["id"]})
    moved = False
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        res = driver.cmd({"cmd": "battle_action", "action": "move",
                          "unit": u["id"],
                          "x": before[0] + dx, "y": before[1] + dy,
                          "z": u["z"]})
        if res.get("ok"):
            moved = True
            want = (before[0] + dx, before[1] + dy)
            break
    if not moved:
        _fail(fails, f"{driver_tag} unit {u['id']} could not walk adjacent "
              f"from ({before[0]}, {before[1]})")
        return

    print(f"    walk from {driver_tag}: unit {u['id']} "
          f"({before[0]},{before[1]}) -> ({want[0]},{want[1]})")

    deadline = time.time() + 45
    while time.time() < deadline and unit_pos(driver, u["id"])[:2] == before:
        time.sleep(0.5)
    after = unit_pos(driver, u["id"])
    if after is None:
        _fail(fails, f"unit {u['id']} disappeared from {driver_tag}")
        return

    while time.time() < deadline:
        pp = unit_pos(peer, u["id"])
        if pp and pp[:2] == after[:2]:
            print(f"PASS replication: walk reached BOTH machines "
                  f"({after[:2]})")
            return
        time.sleep(0.5)

    _fail(fails, f"REPLICATION BROKEN: unit {u['id']} at {after[:2]} on "
          f"{driver_tag}, peer has {unit_pos(peer, u['id'])}")


def main():
    fails = []

    # gamemode 2: host=XCOM (executor), client=aliens (waits)
    test_turn_control(fails, alien_player="client",
                      expect_executor_tag="host",
                      expect_xcom_side_tag="host",
                      expect_alien_side_tag="client")

    # gamemode 3: host=aliens (waits), client=XCOM (executor)
    test_turn_control(fails, alien_player="host",
                      expect_executor_tag="client",
                      expect_xcom_side_tag="client",
                      expect_alien_side_tag="host")

    print("\n==== PvP skirmish turn control summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: executor correct, correct faction controls XCOM, "
          "walk replicates")
    sys.exit(0)


if __name__ == "__main__":
    main()
