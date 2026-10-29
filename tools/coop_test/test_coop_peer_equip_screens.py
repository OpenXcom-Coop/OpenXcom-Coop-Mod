"""Regression test: a soldier's equipment must survive being looked at from the
other player's base, on BOTH equip screens, in the single host-owned SEPARATE
world.

Reported from a SEPARATE playtest: a soldier equipped with a weapon in each hand
and rockets in the backpack is transferred to another player's base; at that base
"they are missing the weapons in their hands", the craft equip screen disagrees
with the soldier equip screen, and items dropped onto the soldier there "drop
right back down to the ground items lower panel". The root cause was items
sharing one coopID, so a type-only match refused the visitor's own weapons
whenever the base owner had equipped that type on the craft.

WHAT IS ASSERTED, at the host's own base and at the client's base (co-op vs
plain parity: whatever holds at your own base must hold at the partner's):

  0. precondition: the client equips its own crew by hand at its base. The
     two-world craft item manifest (whose type-only match stripped the weapons)
     does not exist in the single world: equipping writes none;
  1. the transferred soldier wears its COMPLETE layout on both screens;
  2. the two screens put the same items in the same slots on that soldier;
  3. the two screens hold the same set of physical item instances (`all`).

Run:  python tools/coop_test/test_coop_peer_equip_screens.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_coop_transferred_equipment as T

GEAR = [("STR_RIFLE", "right", 1), ("STR_PISTOL", "left", 1), ("STR_SMALL_ROCKET", "backpack", 2)]
# what the client equips on its own crew, by hand
PEER_DRAGS = (("STR_RIFLE", "right"), ("STR_PISTOL", "left"), ("STR_SMALL_ROCKET", "backpack"))


def open_base_inventory(gc, base_name):
    gc.ok({"cmd": "open_soldiers", "base": base_name})
    gc.wait_for("soldiers", lambda: T._has_state(gc, "SoldiersState") or None, timeout=30)
    r = gc.ok({"cmd": "soldiers_inventory"})
    assert r.get("opened"), f"base inventory did not open: {r}"
    gc.wait_for("inventory", lambda: T._has_state(gc, "InventoryState") or None, timeout=30)


def close_base_inventory(gc):
    gc.ok({"cmd": "battle_inventory", "action": "ok"})
    gc.wait_for("inventory closed", lambda: (not T._has_state(gc, "InventoryState")) or None,
                timeout=30)
    gc.ok({"cmd": "soldiers_ok"})
    gc.wait_for("soldiers closed", lambda: (not T._has_state(gc, "SoldiersState")) or None,
                timeout=30)


def equip_by_hand(gc, base_name, owner_seat, crew_limit=3):
    """Really drag items onto the local player's own crew, the way a player
    does."""
    own = {s["id"] for s in T.report(gc, base_name)["soldiers"] if s["owner"] == owner_seat}
    open_base_inventory(gc, base_name)
    g = gc.ok({"cmd": "inventory_ground"})
    moved = 0
    for unit in [u for u in g["soldiers"] if u["id"] in own][:crew_limit]:
        for item, slot in PEER_DRAGS:
            r = gc.cmd({"cmd": "inventory_move", "name": unit["name"], "item": item, "slot": slot})
            if r.get("moved"):
                moved += 1
    close_base_inventory(gc)
    return moved


def read_both_screens(gc, base_name, cid, reseat):
    """Soldier equip screen, then craft equip screen, at base_name. With
    alternate craft equipment management ON the base inventory unseats every
    soldier on open, so the seat is re-established before the craft screen."""
    base_g = T.base_equip_screen(gc, base_name)
    reseat()
    craft_g = T.craft_equip_screen(gc, base_name, cid)
    return base_g, craft_g


def assert_screens_agree(base_g, craft_g, sid, label):
    want = T.expected_loadout(GEAR)
    base_lo, craft_lo = T.loadout_of(base_g, sid), T.loadout_of(craft_g, sid)
    assert T.items_only(base_lo) == want, (
        f"{label}: the soldier equip screen STRIPPED equipment - expected {want}, "
        f"got {T.items_only(base_lo)} (ground pane: {base_g['items']})")
    assert T.items_only(craft_lo) == want, (
        f"{label}: the craft equip screen STRIPPED equipment - expected {want}, "
        f"got {T.items_only(craft_lo)}")
    assert base_lo == craft_lo, (
        f"{label}: the two equip screens disagree on the soldier's loadout:\n"
        f"  soldier screen: {base_lo}\n  craft   screen: {craft_lo}")
    assert base_g["all"] == craft_g["all"], (
        f"{label}: the two equip screens hold different item instances:\n"
        f"  soldier screen: {base_g['all']}\n  craft   screen: {craft_g['all']}")
    print(f"PASS {label}: full loadout {T.items_only(base_lo)}, both screens agree")


def main():
    js = T.bring_up("xeqpeer")
    host, client = js.host, js.client
    try:
        T.set_alt(host, client, True)
        HB, CB = T.HB, T.CB

        # 0. the client equips its own crew by hand at its own base
        moved = equip_by_hand(client, CB, 1)
        assert moved > 0, "precondition failed - the client equipped nothing by hand"
        manifest = next(c for c in T.report(client, CB)["crafts"]
                        if c["type"] == T.SKYRANGER)["coopItems"]
        ids = sorted({(e["type"], e["id"]) for e in manifest})
        assert len(ids) == len(manifest), (
            f"the craft item manifest has DUPLICATE (type, id) pairs - a type-only "
            f"match follows: {manifest}")
        assert not manifest, (
            f"equipping by hand wrote a two-world craft item manifest: {manifest}")
        print(f"client crew equipped by hand ({moved} moves); manifest {len(manifest)} "
              f"entries, all (type,id) distinct")

        # the host's target soldier, equipped
        sid = T.free_soldier(host, host, client, HB, 0)
        T.rename(host, host, client, HB, sid, "Zzz Target")
        for item, slot, qty in GEAR:
            T.give_layout(host, client, HB, "Zzz Target", item, slot, qty)

        # (parity) the same two screens at the host's OWN base
        own_craft = T.craft_id(host, HB)
        bench = next(s for s in T.report(host, HB)["soldiers"]
                     if s["craft"] == own_craft and s["owner"] == 0)
        T.seat(host, host, client, HB, bench["id"], own_craft, False)

        def seat_own():
            T.seat(host, host, client, HB, sid, own_craft, True)
        seat_own()
        b, c = read_both_screens(host, HB, own_craft, seat_own)
        assert_screens_agree(b, c, sid, "own base")
        T.seat(host, host, client, HB, sid, own_craft, False)

        # ... and at the client's base, after a transfer there
        T.send_soldier(host, host, client, sid, HB, CB)
        T.arrive(host, client, CB, sid)
        peer_craft = T.craft_id(host, CB)

        def seat_peer():
            T.seat(host, host, client, CB, sid, peer_craft, True)
        seat_peer()
        b, c = read_both_screens(host, CB, peer_craft, seat_peer)
        assert_screens_agree(b, c, sid, "client's base")
        print("TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
