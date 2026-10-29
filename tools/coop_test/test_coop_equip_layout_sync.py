"""Regression test: an equipment layout set on a base inventory screen, the
Select Squad screen's de-assign buttons, and the craft armor screen's ctrl-click
seat reach the host, which builds every battle, in both one-world campaigns
(PR #213).

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
    6. the client ctrl-clicks its own soldier on the craft armor screen of its
       Skyranger: seated on both machines, ClientBase identical; a second
       ctrl-click takes it off on both.
    8. the client loads a craft equipment template on its Skyranger (replace):
       the host's craft holds exactly the template's items (one more than the
       base has of one item, so all of that one), the rest went to the stores,
       nothing created or lost, ClientBase identical on both, and the "cannot
       re-equip" report opens on the client only.
    9. guard: the host's template load on the client's Skyranger (a visitor)
       changes nothing on either machine (only the base owner changes a
       craft's items, RU8).
  SHARED
    4. client at the shared base: the host's report shows the client's layout.
    5. client presses "de-assign all soldiers": every soldier leaves the craft
       on both machines (SHARED keeps main's any-soldier rule).
    7. the client's craft armor ctrl-click seats its soldier on the shared
       Skyranger and takes it off again, on both machines.
    10. the client loads a template "on top" of the shared Skyranger's items:
       the host's craft gains exactly the template, HostBase identical on both.

Red: with the ctrl-click's local seat (rows 6 and 7) the host never saw the
soldier on the craft; with the template's local load (rows 8 and 10) the
host's craft kept its old items.

Each part (SEPARATE, SHARED) runs even when the other fails; rc 0 = every row
passed.

Run:  python tools/coop_test/test_coop_equip_layout_sync.py
"""

import os
import sys
import time
import traceback

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


def wait_seat(gcs, base, sid, want, label, timeout=30):
    """Soldier @sid at @base sits on craft id @want (-1 = none) on every machine
    in @gcs, the host first."""
    for gc in gcs:
        try:
            gc.wait_for(f"{gc.name}: {label}",
                        lambda gc=gc: ((T.soldier_at(gc, base, sid) or {}).get("craft") == want)
                        or None, timeout=timeout, interval=0.3)
        except TimeoutError:
            seen = {m.name: (T.soldier_at(m, base, sid) or {}).get("craft") for m in gcs}
            raise AssertionError(f"{label}: soldier {sid}'s craft per machine is {seen}, "
                                 f"want {want}")


# Template items: starting-base gear, first two the base holds at least 2 of.
TEMPLATE_PICKS = ("STR_PISTOL", "STR_RIFLE", "STR_SMALL_ROCKET", "STR_GRENADE",
                  "STR_PISTOL_CLIP", "STR_RIFLE_CLIP")


def craft_items(gc, base, cid):
    return {t: n for t, n in next(c for c in T.report(gc, base)["crafts"]
                                  if c["id"] == cid and c["type"] == T.SKYRANGER)["items"].items()
            if n > 0}


def stock_split(gc, base, cid):
    """{item: (stores, on the craft)} at @base for craft @cid."""
    store = {t: n for t, n in T.report(gc, base)["storage"].items() if n > 0}
    craft = craft_items(gc, base, cid)
    return {t: (store.get(t, 0), craft.get(t, 0)) for t in set(store) | set(craft)}


def pick_template_items(split, key):
    """The first two TEMPLATE_PICKS with key(split[item]) >= 2."""
    picks = [t for t in TEMPLATE_PICKS if key(split.get(t, (0, 0))) >= 2][:2]
    assert len(picks) == 2, f"precondition: two template items with 2+ in {split}"
    return picks


def load_template(gc, host, client, base, cid, template, only_add):
    """Write @template into slot 0 on both machines, then run @gc's real
    template load on craft @cid. Returns the load's response."""
    for m in (host, client):
        m.ok({"cmd": "craft_loadout", "op": "set", "index": 0, "items": template})
    return gc.ok({"cmd": "craft_loadout", "op": "load", "index": 0, "base": base,
                  "craft_id": cid, "craft_type": T.SKYRANGER, "only_add": only_add})


def wait_craft(gcs, base, cid, want, label, timeout=30):
    """Craft @cid at @base carries exactly @want ({item: n > 0}) on every
    machine in @gcs, the host first."""
    for gc in gcs:
        try:
            gc.wait_for(f"{gc.name}: {label}",
                        lambda gc=gc: craft_items(gc, base, cid) == want or None,
                        timeout=timeout, interval=0.3)
        except TimeoutError:
            seen = {m.name: craft_items(m, base, cid) for m in gcs}
            raise AssertionError(f"{label}: the craft's items per machine are {seen}, "
                                 f"want {want}")


def has_state(gc, name):
    return any(name in s for s in gc.cmd({"cmd": "get_state"})["states"])


def armor_ctrl_click(gc, host, client, base, cid, sid, want, label):
    """Ctrl-click soldier @sid on the craft armor screen of craft @cid at @base
    (on @gc), then wait until both machines seat it at @want."""
    r = gc.cmd({"cmd": "craft_armor_seat", "base": base, "craft_id": cid,
                "craft_type": T.SKYRANGER, "soldier_id": sid})
    assert r.get("ok"), f"{gc.name}: craft armor ctrl-click on soldier {sid}: {r}"
    wait_seat((host, client), base, sid, want, label)


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

        # 6. the client's ctrl-click on the craft armor screen seats and unseats
        csid = mine[0]
        armor_ctrl_click(client, host, client, CB, cid, csid, cid,
                         "craft armor ctrl-click seat (Separate)")
        wait_same_base(host, client, CB, "craft armor ctrl-click seat")
        armor_ctrl_click(client, host, client, CB, cid, csid, -1,
                         "craft armor ctrl-click unseat (Separate)")
        wait_same_base(host, client, CB, "craft armor ctrl-click unseat")
        print(f"PASS separate-armor-seat: the client's ctrl-click seated soldier {csid} on "
              f"its Skyranger and took it off, on both machines; ClientBase identical")

        # 8. the client loads a craft equipment template on its Skyranger (replace)
        split = stock_split(host, CB, cid)
        a, b = pick_template_items(split, lambda sc: sc[0] + sc[1])
        total_b = sum(split[b])
        template = {a: 1, b: total_b + 1}
        r = load_template(client, host, client, CB, cid, template, False)
        listed = set(r["listed"])
        assert {a, b} <= listed, (
            f"precondition: {a} / {b} not on the client's craft equipment list {sorted(listed)}")
        want = {t: c for t, (s, c) in split.items() if t not in listed and c > 0}
        want.update({a: 1, b: total_b})
        wait_craft((host, client), CB, cid, want, "client's template load (Separate)")
        wait_same_base(host, client, CB, "client's template load")
        after = stock_split(host, CB, cid)
        for t in set(split) | set(after):
            assert sum(after.get(t, (0, 0))) == sum(split.get(t, (0, 0))), (
                f"{t} at ClientBase (stores, craft) {split.get(t)} -> {after.get(t)}: "
                f"the template load created or lost items")
        if not any("CannotReequipState" in d for d in r["dialogs"]):
            client.wait_for("client: the cannot re-equip report",
                            lambda: has_state(client, "CannotReequipState") or None,
                            timeout=15, interval=0.3)
        assert not has_state(host, "CannotReequipState"), (
            "the host shows the client's cannot re-equip report")
        T.settle(client)
        print(f"PASS separate-template: the client's template ({template}) reached the "
              f"host's Skyranger as {want}; ClientBase identical, nothing created or lost; "
              f"the missing {b} reported on the client only")

        # 9. guard: a visitor's template load changes nothing (RU8)
        view0 = wait_same_base(host, client, CB, "before the visitor's template load")
        load_template(host, host, client, CB, cid, {a: 2}, False)
        T.rename(host, host, client, CB, hsid, "Zzz Barrier")  # a later host command
        view1 = wait_same_base(host, client, CB, "after the visitor's template load")
        assert view1["crafts"] == view0["crafts"] and view1["storage"] == view0["storage"], (
            f"the host's template load at ClientBase changed it:\n  before={view0}\n  after ={view1}")
        print("PASS separate-visitor-template: the host's template load on the client's "
              "Skyranger changed nothing on either machine")
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

        # 7. the client's craft armor ctrl-click on its own soldier
        armor_ctrl_click(client, host, client, base, cid, sid, cid,
                         "craft armor ctrl-click seat (SHARED)")
        armor_ctrl_click(client, host, client, base, cid, sid, -1,
                         "craft armor ctrl-click unseat (SHARED)")
        print(f"PASS shared-armor-seat: the client's ctrl-click seated soldier {sid} on the "
              f"shared Skyranger and took it off, on both machines")

        # 10. the client loads a template "on top" of the shared Skyranger's items
        split = stock_split(host, base, cid)
        a, b = pick_template_items(split, lambda sc: sc[0])
        template = {a: 1, b: 2}
        r = load_template(client, host, client, base, cid, template, True)
        assert {a, b} <= set(r["listed"]), (
            f"precondition: {a} / {b} not on the client's craft equipment list {r['listed']}")
        want = {t: c for t, (s, c) in split.items() if c > 0}
        for t, n in template.items():
            want[t] = want.get(t, 0) + n
        wait_craft((host, client), base, cid, want, "client's template load on top (SHARED)")
        wait_same_base(host, client, base, "SHARED client's template load")
        print(f"PASS shared-template: the client's template on top ({template}) reached the "
              f"host's Skyranger; HostBase identical on both")
    finally:
        js.shutdown()


def main():
    failures = []
    for part in (separate_rows, shared_row):
        try:
            part()
        except Exception as e:  # noqa: BLE001 - report every part, then fail
            traceback.print_exc()
            failures.append(f"{part.__name__}: {e}")
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        sys.exit(1)
    print("TEST PASSED")


if __name__ == "__main__":
    main()
