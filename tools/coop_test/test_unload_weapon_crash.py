"""Regression test for issue #29: "Unloading a magazine in the base crashes the
game" (SEH 0xC0000005 access violation).

Root cause: when a weapon is unloaded from the base soldier-equip screen, the
just-removed ammo has its inventory slot cleared (BattleItem::setAmmoForSlot ->
setSlot(nullptr)). The co-op Inventory::moveItem() broadcast path then did
`item->getSlot()->getType()` on that ammo and dereferenced null.

This test drives Inventory::unload() (the exact call btnUnloadClick makes) from
the base equip screen via the TestServer `inventory_unload` command, in three
co-op contexts, and asserts the game process survives each unload:

  A. host unloads a weapon on one of its OWN base soldiers
  B. client unloads a weapon on one of its OWN base soldiers
  C. a soldier is transferred host -> client base; the client opens the equip
     screen at that base and unloads a (freshly reloaded) weapon there.

Before the fix each unload crashes the process -> the next socket command raises
ConnectionError. After the fix the command returns {ok, unloaded:true} and the
process is still alive.

Run:  python tools/coop_test/test_unload_weapon_crash.py
"""

import json
import os
import sys
import time


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session


def _has_state(gc, n):
    return any(n in s for s in gc.cmd({"cmd": "get_state"})["states"])


def own_base(gc):
    s = gc.ok({"cmd": "get_soldiers"})
    return next(b for b in s["bases"]
               if not b["coopBaseFlag"] and not b["coopIcon"] and b["soldiers"])


def assert_alive(gc, where):
    """The process must still be running and responsive after an unload."""
    assert gc.proc.poll() is None, f"{gc.name}: process CRASHED during {where} (rc={gc.proc.returncode})"
    r = gc.cmd({"cmd": "ping"})
    assert r.get("ok") or r.get("pong") or r, f"{gc.name}: unresponsive after {where}: {r}"


def unload_at_base(gc, base_name, where):
    """Open the base equip screen for base_name and unload a loaded weapon.

    Returns the inventory_unload response. Raises ConnectionError if the process
    crashed (the pre-fix behaviour)."""
    gc.ok({"cmd": "open_soldiers", "base": base_name})
    gc.wait_for("soldiers", lambda: _has_state(gc, "SoldiersState") or None, timeout=30)
    r = gc.ok({"cmd": "soldiers_inventory"})
    assert r.get("opened"), f"equip screen did not open: {r}"
    gc.wait_for("inventory", lambda: _has_state(gc, "InventoryState") or None, timeout=30)

    # THE repro: drive Inventory::unload() exactly like the unload button.
    resp = gc.cmd({"cmd": "inventory_unload"})   # raises ConnectionError on crash
    assert_alive(gc, where)
    assert resp.get("ok"), f"{gc.name}: inventory_unload failed at {where}: {resp}"
    assert resp.get("unloaded"), f"{gc.name}: unload did not run at {where}: {resp}"
    print(f"PASS {where}: unloaded {resp.get('weapon')} without crashing ({gc.name})")

    # close the equip screen cleanly
    gc.ok({"cmd": "battle_inventory", "action": "ok"})
    gc.wait_for("closed", lambda: (not _has_state(gc, "InventoryState")) or None, timeout=30)
    gc.ok({"cmd": "soldiers_ok"})
    return resp


def main():
    host = GameClient("host", 47811, make_user_dir("host-user"))
    client = GameClient("client", 47812, make_user_dir("client-user"))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        session.new_campaign(host, client)
        print("fresh coop session established")

        hb = own_base(host)
        cb = own_base(client)

        # A. host unloads on its own base soldier
        unload_at_base(host, hb["name"], "A/host-own-base")

        # B. client unloads on its own base soldier
        unload_at_base(client, cb["name"], "B/client-own-base")

        # C. transfer a host soldier to the client's base, then the client
        #    unloads a reloaded weapon on a soldier at that (foreign-origin) base.
        soldier = next(s for s in hb["soldiers"] if not s.get("craft"))["name"]
        tr = host.ok({"cmd": "transfer_to_coop_base", "name": soldier, "toBase": cb["name"]})
        assert tr.get("transferred"), f"transfer failed: {tr}"

        def client_sees():
            s = client.cmd({"cmd": "get_soldiers"})
            return any(x["name"] == soldier for b in s.get("bases", []) for x in b["soldiers"]) or None
        try:
            client.wait_for("client sees transferred soldier", client_sees, timeout=30)
        except TimeoutError:
            # rare (seen once in 87 full suite runs): the client opened its trade dialog yet never listed the
            # soldier; record what each machine holds, which dialog is up, and whether the soldier shows up late
            def roster(gc):
                r = gc.cmd({"cmd": "get_soldiers"})
                return [[b.get("name"), b.get("coopIcon"), b.get("coopBaseFlag"), [x.get("name") for x in b.get("soldiers", [])]]
                        for b in r.get("bases", [])] or r
            cap = {"soldier": soldier, "transfer": tr, "host": roster(host), "client": roster(client),
                   "clientDialog": client.cmd({"cmd": "coop_dialog_info"}), "clientStack": session.states_stripped(client),
                   "hostStack": session.states_stripped(host)}
            t0 = time.time()
            while time.time() - t0 < 10.0 and not client_sees():
                time.sleep(0.25)
            cap["seenWithin10sMore"] = bool(client_sees())
            print(f"CAPTURE client-sees: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
            raise

        unload_at_base(client, cb["name"], "C/client-transferred-base")

        print("TEST PASSED")
    finally:
        host.shutdown(); client.shutdown()


if __name__ == "__main__":
    main()
