"""Regression test: an equipment layout set on a base inventory screen, and the
Select Squad screen's de-assign buttons, reach the host, which builds every
battle, in both one-world campaigns (PR #213).

Before the fix, closing the base inventory wrote each soldier's layout on the
machine that showed the screen only. A layout the client set never reached the
host, so the host's battle deployed the client's soldiers with their old
equipment, and with "Alternate craft equipment management" ON the client's own
unseat / re-seat around the screen moved gear between its craft and stores on
the client alone (ClientBase rifles: host 3, client 1).

Every row drags an item for real (Inventory::moveItem) and closes the screen:

  SEPARATE (option ON)
    1. client at its own base, on a soldier seated on its Skyranger: the host's
       ClientBase shows the same layouts, crafts' items and stores as the
       client's, the dragged item is in that soldier's layout on BOTH machines,
       and it moved from the stores onto the craft (once, on both).
    2. host at the client's base, on its own soldier transferred there: the
       client sees the same layout and the same ClientBase.
    3. the host seats that soldier on the client's Skyranger, the client presses
       "de-assign craft soldiers" there: the client's own soldiers leave the
       craft, the host's stays (a player unseats only their own soldiers), and
       ClientBase is identical on both machines (the gear moved with the seats).
  SHARED
    4. client at the shared base: the host's report shows the client's layout.
    5. client presses "de-assign all soldiers": every soldier leaves the craft
       on both machines (SHARED keeps main's any-soldier rule).

Run:  python tools/coop_test/test_coop_equip_layout_sync.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import test_coop_transferred_equipment as T
import test_coop_peer_equip_screens as P

DRAG = ("STR_SMALL_ROCKET", "backpack")


def base_view(gc, base):
    """What both machines must agree on at @base: stores, each craft's items and
    crew, and every soldier's layout and seat."""
    r = T.report(gc, base)
    return {
        "storage": dict(sorted(r["storage"].items())),
        "crafts": sorted((c["type"], c["id"], tuple(sorted(c["items"].items())), c["soldiers"])
                         for c in r["crafts"]),
        "soldiers": sorted((s["id"], s["owner"], s["craft"], tuple(sorted(s["layout"])))
                           for s in r["soldiers"]),
    }


def layout_of(gc, base, sid):
    s = T.soldier_at(gc, base, sid)
    return sorted(s["layout"]) if s else None


def drag_and_close(gc, base, name):
    """Open the base inventory at @base, drag one item from the ground into
    soldier @name's backpack (DRAG first, else the first ground item that fits),
    close the screen. Returns the dragged item type."""
    P.open_base_inventory(gc, base)
    g = gc.ok({"cmd": "inventory_ground"})
    candidates = [DRAG[0]] + sorted(t for t, n in g["items"].items() if n > 0 and t != DRAG[0])
    dragged, tried = None, []
    for item in candidates:
        if g["items"].get(item, 0) <= 0:
            continue
        r = gc.cmd({"cmd": "inventory_move", "name": name, "item": item, "slot": DRAG[1]})
        tried.append((item, r))
        if r.get("moved"):
            dragged = item
            break
    P.close_base_inventory(gc)
    assert dragged, f"{gc.name}: no ground item could be dragged onto {name} at {base}: {tried}"
    return dragged


def wait_same_base(host, client, base, label, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        h, c = base_view(host, base), base_view(client, base)
        if h == c:
            return h
        time.sleep(0.3)
    raise AssertionError(f"{label}: {base} differs between the machines\n"
                         f"  host  ={base_view(host, base)}\n  client={base_view(client, base)}")


def wait_layout_has(gcs, base, sid, item, before, label, timeout=30):
    for gc in gcs:
        try:
            gc.wait_for(f"{gc.name}: {label}",
                        lambda gc=gc: ((layout_of(gc, base, sid) or []).count(item)
                                       > before.count(item)) or None,
                        timeout=timeout, interval=0.3)
        except TimeoutError:
            raise AssertionError(f"{label}: soldier {sid}'s layout on {gc.name} is "
                                 f"{layout_of(gc, base, sid)} (before {before}); the {item} "
                                 f"dragged on the screen never reached it")


def separate_rows():
    js = T.bring_up("xeqsync")
    host, client = js.host, js.client
    try:
        T.set_alt(host, client, True)
        HB, CB = T.HB, T.CB

        # 1. the client equips its own seated soldier at its own base
        cid = T.craft_id(host, CB)
        sid = next(s["id"] for s in T.report(client, CB)["soldiers"]
                   if s["owner"] == 1 and s["craft"] == cid)
        T.rename(client, host, client, CB, sid, "Zzz Sync")
        before = layout_of(host, CB, sid)

        def stock(gc, item):
            craft = next(c for c in T.report(gc, CB)["crafts"]
                         if c["id"] == cid and c["type"] == T.SKYRANGER)
            return T.stored(gc, CB, item), craft["items"].get(item, 0)
        rows0 = {gc.name: {t: stock(gc, t) for t in T.report(gc, CB)["storage"]}
                 for gc in (host, client)}
        item = drag_and_close(client, CB, "Zzz Sync")
        wait_layout_has((host, client), CB, sid, item, before,
                        "client's layout edit at its own base")
        view = wait_same_base(host, client, CB, "client's layout edit at its own base")
        for gc in (host, client):
            store, onCraft = stock(gc, item)
            store0, craft0 = rows0[gc.name].get(item, (0, 0))
            assert store + onCraft == store0 + craft0, (
                f"{gc.name}: {item} at ClientBase (stores, craft) {(store0, craft0)} -> "
                f"{(store, onCraft)}: the layout edit created or lost items")
            assert onCraft >= craft0 + 1, (
                f"{gc.name}: the {item} in the seated soldier's new layout is not on its "
                f"craft (craft {craft0} -> {onCraft}, option ON)")
        print(f"PASS separate-own-base: the client's {item} layout edit reached the host; "
              f"ClientBase identical on both ({len(view['soldiers'])} soldiers); the {item} "
              f"moved from the stores onto the craft, none created or lost")

        # 2. the host equips its own soldier at the client's base (a visitor)
        hsid = T.free_soldier(host, host, client, HB, 0)
        T.rename(host, host, client, HB, hsid, "Zzz Visit")
        T.send_soldier(host, host, client, hsid, HB, CB)
        T.arrive(host, client, CB, hsid)
        before = layout_of(client, CB, hsid)
        item = drag_and_close(host, CB, "Zzz Visit")
        wait_layout_has((host, client), CB, hsid, item, before,
                        "host's layout edit at the client's base")
        wait_same_base(host, client, CB, "host's layout edit at the client's base")
        print("PASS separate-visitor: the visitor's layout edit reached the client; "
              "ClientBase identical on both")

        # 3. the client empties its Skyranger, which carries the host's soldier too
        T.seat(host, host, client, CB, hsid, cid, True)
        mine = [s["id"] for s in T.report(client, CB)["soldiers"]
                if s["owner"] == 1 and s["craft"] == cid]
        assert mine, "precondition: the client has no soldier on its Skyranger"
        client.ok({"cmd": "craft_deassign", "base": CB, "craft_id": cid})
        for gc in (host, client):
            try:
                gc.wait_for(f"{gc.name}: the client's soldiers off its Skyranger",
                            lambda gc=gc: all((T.soldier_at(gc, CB, i) or {}).get("craft") == -1
                                              for i in mine) or None, timeout=30, interval=0.3)
            except TimeoutError:
                raise AssertionError(
                    f"de-assign craft soldiers: on {gc.name} the client's soldiers sit at "
                    f"{[(i, (T.soldier_at(gc, CB, i) or {}).get('craft')) for i in mine]}")
        view = wait_same_base(host, client, CB, "de-assign craft soldiers")
        for gc in (host, client):
            assert (T.soldier_at(gc, CB, hsid) or {}).get("craft") == cid, (
                f"{gc.name}: the client's de-assign unseated the host's soldier {hsid}")
        print(f"PASS separate-deassign: {len(mine)} client soldier(s) off the Skyranger, "
              f"the host's soldier still on it, ClientBase identical on both")
    finally:
        js.shutdown()


def shared_row():
    js = shared_fixture.bring_up("jeqsync", T.PORTS)
    host, client = js.host, js.client
    try:
        base = "HostBase"
        sid = next(s["id"] for s in T.report(client, base)["soldiers"] if s["owner"] == 1)
        T.rename(client, host, client, base, sid, "Zzz Shsync")
        before = layout_of(host, base, sid)
        item = drag_and_close(client, base, "Zzz Shsync")
        wait_layout_has((host, client), base, sid, item, before,
                        "SHARED client's layout edit")
        h, c = layout_of(host, base, sid), layout_of(client, base, sid)
        assert h == c, f"SHARED: soldier {sid}'s layout host={h} client={c}"
        print(f"PASS shared-client-layout: the host holds the client's layout {h}")

        # 5. the client's "de-assign all soldiers" reaches the host
        cid = T.craft_id(host, base)
        seated = [s["id"] for s in T.report(host, base)["soldiers"] if s["craft"] == cid]
        assert seated, "precondition: nobody on the shared Skyranger"
        client.ok({"cmd": "craft_deassign", "base": base, "craft_id": cid, "all": True})
        for gc in (host, client):
            try:
                gc.wait_for(f"{gc.name}: everyone off the shared Skyranger",
                            lambda gc=gc: all((T.soldier_at(gc, base, i) or {}).get("craft") == -1
                                              for i in seated) or None, timeout=30, interval=0.3)
            except TimeoutError:
                raise AssertionError(
                    f"SHARED de-assign all: on {gc.name} the crew sits at "
                    f"{[(i, (T.soldier_at(gc, base, i) or {}).get('craft')) for i in seated]}")
        print(f"PASS shared-deassign-all: {len(seated)} soldier(s) off the Skyranger on both machines")
    finally:
        js.shutdown()


def main():
    separate_rows()
    shared_row()
    print("TEST PASSED")


if __name__ == "__main__":
    main()
