"""Regression tests for the equipment of a soldier transferred to the other
player's base, in the single host-owned SEPARATE world (PR #213).

There is one world: HostBase (the host's) and ClientBase (the client's) are
real bases on both machines, a transfer is a host command, and a visitor opens
the partner's base screens directly. A layout set on an inventory screen goes
to the host as a command (test_coop_equip_layout_sync); give_layout is a test
shortcut that writes one machine's copy, so this test writes it on both.

  scenario_conservation()   - the host transfers a soldier carrying a rocket in
    its layout to the client's base:
      1. the number of rockets in the whole world (both bases' stores, items en
         route included) is unchanged by the transfer and its arrival;
      2. at the client's base, the equip screen holds no more rocket instances
         than that base's stores, and the host (visiting with the transferred
         soldier) and the client (at home) see the same number.

  scenario_two_screens_agree() - the playtest report. With "Alternate craft
    equipment management" ON, the host's soldier carries a weapon in each hand
    and rockets in the backpack and is transferred to the client's base:
      2b. the transfer settles cleanly: no error dialog on either machine, the
          sender's stores lose the gear once and the receiver's gain it once;
      3.  the host seats the soldier on the client's Skyranger there;
      4.  the soldier equip screen (Soldiers > Inventory) and the craft equip
          screen (Equip craft > Inventory) at that base, on the host, both show
          the soldier wearing the loadout it had before the transfer, slot for
          slot, and hold the same item instances.

Replaced rows (two-world premise gone):
  - "the host visits the peer base" (insideCoopBase) -> the host opens the
    client's base screens directly.
  - "the co-op trade confirms (CoopState 150, never 552)" -> there is no
    cross-player trade confirmation any more; the single-world equivalent is
    2b above (no error dialog, stores debited and credited exactly once).

Run:  python tools/coop_test/test_coop_transferred_equipment.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture

HB, CB = "HostBase", "ClientBase"
PORTS = (47811, 47812, 47900)
ROCKET = "STR_SMALL_ROCKET"
SKYRANGER = "STR_SKYRANGER"
OPT = "oxceAlternateCraftEquipmentManagement"

# A weapon in each hand + rockets in the backpack. All are in a fresh starting
# base's stores (PISTOL 2, RIFLE 2, SMALL_ROCKET 4).
LOADOUT = [
    ("STR_RIFLE", "right", 1),
    ("STR_PISTOL", "left", 1),
    (ROCKET, "backpack", 2),
]
SLOT_ID = {"right": "STR_RIGHT_HAND", "left": "STR_LEFT_HAND",
           "backpack": "STR_BACK_PACK", "belt": "STR_BELT"}


# ---- shared single-world helpers (imported by the other equipment tests) ----

def bring_up(tag):
    return fixture.bring_up(tag, PORTS)


def _has_state(gc, n):
    return any(n in s for s in gc.cmd({"cmd": "get_state"})["states"])


def report(gc, base):
    return gc.ok({"cmd": "base_report", "base": base})


def stored(gc, base, item):
    return report(gc, base)["storage"].get(item, 0)


def incoming(gc, base):
    return gc.ok({"cmd": "incoming_transfers", "base": base})


def soldier_at(gc, base, sid):
    return next((s for s in report(gc, base)["soldiers"] if s["id"] == sid), None)


def craft_id(gc, base, ctype=SKYRANGER):
    return next(c["id"] for c in report(gc, base)["crafts"] if c["type"] == ctype)


def crew(gc, base, cid, ctype=SKYRANGER):
    return next(c["soldiers"] for c in report(gc, base)["crafts"]
                if c["id"] == cid and c["type"] == ctype)


def settle(gc, timeout=10):
    """Close arrival popups until the geoscape is on top."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        top = gc.cmd({"cmd": "get_state"})["states"][-1]
        if "GeoscapeState" in top:
            return
        gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.2)
    raise AssertionError(f"{gc.name}: still not on the geoscape: "
                         f"{gc.cmd({'cmd': 'get_state'})['states']}")


def set_alt(host, client, on):
    for gc in (host, client):
        gc.ok({"cmd": "set_option", "name": OPT, "value": on})


def seat(owner, host, client, base, sid, cid, on):
    """Seat (on) or unseat a soldier through its owner's machine; wait until
    both machines agree."""
    r = owner.ok({"cmd": "craft_assign", "base": base, "soldier_id": sid,
                  "craft_id": cid, "craft_type": SKYRANGER, "on": on})
    want = cid if on else -1
    for gc in (host, client):
        try:
            gc.wait_for(f"{gc.name}: soldier {sid} craft -> {want}",
                        lambda gc=gc: ((soldier_at(gc, base, sid) or {}).get("craft") == want)
                        or None, timeout=30, interval=0.3)
        except TimeoutError:
            seen = {m.name: ((soldier_at(m, base, sid) or {}).get("craft"), crew(m, base, cid))
                    for m in (host, client)}
            raise AssertionError(f"seat {sid} on={on} at {base}: craft_assign resp={r}; "
                                 f"(craft, crew) per machine={seen}")


def free_soldier(owner, host, client, base, owner_seat, exclude=()):
    """A base-resident soldier of owner_seat at base (only those are
    transferable); unseats one from the Skyranger when none is free."""
    r = report(host, base)
    mine = [s for s in r["soldiers"] if s["owner"] == owner_seat and s["id"] not in exclude]
    free = [s for s in mine if s["craft"] == -1]
    if free:
        return free[0]["id"]
    sid = mine[0]["id"]
    seat(owner, host, client, base, sid, mine[0]["craft"], False)
    return sid


def rename(owner, host, client, base, sid, name):
    owner.ok({"cmd": "soldier_rename", "base": base, "soldierId": sid, "name": name})
    for gc in (host, client):
        gc.wait_for(f"{gc.name}: rename to {name}",
                    lambda gc=gc: ((soldier_at(gc, base, sid) or {}).get("name") == name) or None,
                    timeout=30, interval=0.3)


def give_layout(host, client, base, name, item, slot, qty=1):
    """Write a layout entry on both machines (give_layout edits one machine's
    copy only; a real inventory screen sends the layout to the host)."""
    for gc in (host, client):
        g = gc.ok({"cmd": "give_layout", "base": base, "item": item, "slot": slot,
                   "name": name, "count": 1, "qty": qty})
        assert g.get("entries") == qty, f"{gc.name}: give_layout {item} wrote {g}"


def send_soldier(sender, host, client, sid, src, dst):
    """Transfer one soldier src -> dst through the sender's own transfer screen
    (a host command); wait until both machines show it en route."""
    before = {gc.name: incoming(gc, dst)["soldiers"] for gc in (host, client)}
    r = sender.ok({"cmd": "shared_transfer", "soldier_id": sid,
                   "fromBase": src, "toBase": dst})
    assert r.get("sent"), f"transfer of soldier {sid} not sent: {r}"
    for gc in (host, client):
        gc.wait_for(f"{gc.name}: soldier {sid} en route to {dst}",
                    lambda gc=gc: (soldier_at(gc, src, sid) is None
                                   and incoming(gc, dst)["soldiers"] == before[gc.name] + 1)
                    or None, timeout=30, interval=0.3)


def arrive(host, client, dst, sid):
    host.ok({"cmd": "force_transfer_arrivals", "base": dst})
    for gc in (host, client):
        gc.wait_for(f"{gc.name}: soldier {sid} arrived at {dst}",
                    lambda gc=gc: (soldier_at(gc, dst, sid) is not None
                                   and incoming(gc, dst)["soldiers"] == 0) or None,
                    timeout=30, interval=0.3)
        settle(gc)


# ---- the two equip screens ------------------------------------------------

def _read_open_inventory(gc):
    gc.wait_for("inventory", lambda: _has_state(gc, "InventoryState") or None, timeout=30)
    g = gc.ok({"cmd": "inventory_ground"})
    gc.ok({"cmd": "battle_inventory", "action": "ok"})
    gc.wait_for("inventory closed",
                lambda: (not _has_state(gc, "InventoryState")) or None, timeout=30)
    return g


def base_equip_screen(gc, base_name):
    """Bases > Soldiers > Inventory, for base_name."""
    gc.ok({"cmd": "open_soldiers", "base": base_name})
    gc.wait_for("soldiers", lambda: _has_state(gc, "SoldiersState") or None, timeout=30)
    r = gc.ok({"cmd": "soldiers_inventory"})
    assert r.get("opened"), f"{gc.name}: base equip screen did not open at {base_name}: {r}"
    g = _read_open_inventory(gc)
    gc.ok({"cmd": "soldiers_ok"})
    gc.wait_for("soldiers closed",
                lambda: (not _has_state(gc, "SoldiersState")) or None, timeout=30)
    return g


def craft_equip_screen(gc, base_name, cid):
    """Bases > Equip craft > <craft> > Equipment > Inventory."""
    gc.ok({"cmd": "open_craft_equipment", "craft_id": cid, "base": base_name})
    gc.wait_for("craft equipment",
                lambda: _has_state(gc, "CraftEquipmentState") or None, timeout=30)
    r = gc.ok({"cmd": "craft_inventory"})
    assert r.get("opened"), f"{gc.name}: craft equip screen did not open the inventory: {r}"
    g = _read_open_inventory(gc)
    gc.ok({"cmd": "craft_equipment_ok"})
    gc.wait_for("craft equipment closed",
                lambda: (not _has_state(gc, "CraftEquipmentState")) or None, timeout=30)
    return g


def loadout_of(ground, sid):
    """{slot -> sorted [(item, x, y, ammo...)]} for soldier sid in an
    inventory_ground dump; {} if that soldier is not in the screen."""
    for u in ground["soldiers"]:
        if u["id"] == sid:
            return {slot: sorted((e["item"], e["x"], e["y"], tuple(e["ammo"]))
                                 for e in entries)
                    for slot, entries in u["slots"].items()}
    return {}


def expected_loadout(gear=LOADOUT):
    out = {}
    for item, slot, qty in gear:
        out.setdefault(SLOT_ID[slot], []).extend([item] * qty)
    return {k: sorted(v) for k, v in out.items()}


def items_only(lo):
    return {slot: sorted(e[0] for e in entries) for slot, entries in lo.items()}


def dialogs(gc):
    return [s for s in gc.cmd({"cmd": "get_state"})["states"]
            if "CoopState" in s or "ErrorMessageState" in s]


# ---- scenario 1: no duplication -------------------------------------------

def world_rockets(gc):
    return (stored(gc, HB, ROCKET) + stored(gc, CB, ROCKET)
            + incoming(gc, HB)["items"].get(ROCKET, 0)
            + incoming(gc, CB)["items"].get(ROCKET, 0))


def scenario_conservation(host, client):
    before = {gc.name: world_rockets(gc) for gc in (host, client)}
    client_stock = stored(host, CB, ROCKET)
    assert client_stock > 0, "client base has no rockets to reason about"

    sid = free_soldier(host, host, client, HB, 0)
    rename(host, host, client, HB, sid, "Zzz Cons")
    give_layout(host, client, HB, "Zzz Cons", ROCKET, "left")
    send_soldier(host, host, client, sid, HB, CB)
    for gc in (host, client):
        assert world_rockets(gc) == before[gc.name], (
            f"{gc.name}: item DUPLICATION on send: world rockets "
            f"{before[gc.name]} -> {world_rockets(gc)}")
    arrive(host, client, CB, sid)
    for gc in (host, client):
        assert world_rockets(gc) == before[gc.name], (
            f"{gc.name}: item DUPLICATION on arrival: world rockets "
            f"{before[gc.name]} -> {world_rockets(gc)}")
    print(f"PASS no-world-duplication: world rockets still {before['host']} on both machines")

    client_stock = stored(host, CB, ROCKET)
    host_g = base_equip_screen(host, CB)      # the visitor, through its own soldier
    cli_g = base_equip_screen(client, CB)     # the owner, at home
    host_all, cli_all = host_g["all"].get(ROCKET, 0), cli_g["all"].get(ROCKET, 0)
    print(f"HOST visiting: rocket instances={host_all} CLIENT home: {cli_all} "
          f"(ClientBase stock {client_stock})")
    assert host_all <= client_stock, (
        f"host equip screen shows {host_all} rocket instances > stock {client_stock}")
    assert cli_all <= client_stock, (
        f"client equip screen shows {cli_all} rocket instances > stock {client_stock}")
    assert host_all == cli_all, (
        f"host and client disagree on rocket instances at the client base: "
        f"host={host_all} client={cli_all}")
    print(f"PASS equip-view-conservation: both see {host_all} rocket instances "
          f"(stock {client_stock})")


# ---- scenario 2: the two equip screens must agree -------------------------

def scenario_two_screens_agree(host, client):
    set_alt(host, client, True)
    sid = free_soldier(host, host, client, HB, 0)
    rename(host, host, client, HB, sid, "Zzz Xfer")
    for item, slot, qty in LOADOUT:
        assert stored(host, HB, item) >= qty, f"HostBase needs {qty}x {item}"
        give_layout(host, client, HB, "Zzz Xfer", item, slot, qty)
    want = expected_loadout()
    gear = {}
    for item, _slot, qty in LOADOUT:
        gear[item] = gear.get(item, 0) + qty
    send0 = {gc.name: {i: stored(gc, HB, i) for i in gear} for gc in (host, client)}
    recv0 = {gc.name: {i: stored(gc, CB, i) for i in gear} for gc in (host, client)}

    send_soldier(host, host, client, sid, HB, CB)
    arrive(host, client, CB, sid)
    for gc in (host, client):
        bad = dialogs(gc)
        assert not bad, f"{gc.name}: the transfer left an error dialog: {bad}"
        for i, q in gear.items():
            assert stored(gc, HB, i) == send0[gc.name][i] - q, (
                f"{gc.name}: sender {i} {send0[gc.name][i]} -> {stored(gc, HB, i)}, expected -{q}")
            assert stored(gc, CB, i) == recv0[gc.name][i] + q, (
                f"{gc.name}: receiver {i} {recv0[gc.name][i]} -> {stored(gc, CB, i)}, expected +{q}")
    print(f"PASS transfer-settles-cleanly: no error dialog, gear {gear} left HostBase "
          f"and reached ClientBase once, on both machines")

    guest = soldier_at(host, CB, sid)
    assert guest["layout"], "transferred soldier arrived with an EMPTY layout (alt ON)"
    cid = craft_id(host, CB)
    seat(host, host, client, CB, sid, cid, True)
    print(f"seated 'Zzz Xfer' on the client's Skyranger {cid}")

    base_g = base_equip_screen(host, CB)
    seat(host, host, client, CB, sid, cid, True)  # alt ON: the base screen unseats on open
    craft_g = craft_equip_screen(host, CB, cid)
    base_lo, craft_lo = loadout_of(base_g, sid), loadout_of(craft_g, sid)
    print(f"soldier equip screen: soldier={items_only(base_lo)}")
    print(f"craft  equip screen: soldier={items_only(craft_lo)}")
    assert items_only(base_lo) == want, (
        f"soldier equip screen at the client base LOST equipment: expected {want}, "
        f"got {items_only(base_lo)}")
    print("PASS soldier-screen-keeps-loadout")
    assert base_lo == craft_lo, (
        f"the two equip screens DISAGREE on the soldier's loadout:\n"
        f"  soldier screen: {base_lo}\n  craft   screen: {craft_lo}")
    print("PASS screens-agree-on-soldier")
    assert base_g["all"] == craft_g["all"], (
        f"the two equip screens hold DIFFERENT items:\n"
        f"  soldier screen: {base_g['all']}\n  craft   screen: {craft_g['all']}")
    print("PASS screens-agree-on-item-instances")


def main():
    js = bring_up("xeqxfer")
    try:
        scenario_conservation(js.host, js.client)
        scenario_two_screens_agree(js.host, js.client)
        print("TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
