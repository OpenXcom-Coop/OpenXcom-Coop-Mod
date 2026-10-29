"""Separate Campaign: what a visitor does at another player's base (PR #213 RU8).

The client is the visitor at HostBase, where it has hired its own soldiers.
Every row checks the AUTHORITATIVE host world, not only the visitor's screen:

  V1 sack     the visitor sacks its own soldier there -> gone on both machines
  V2 rename   the visitor renames its own soldier there -> the host has the name
  V3 reorder  move-up and sort on the visitor's filtered list leave the roster
              order identical on both machines (no host command: blocked)
  V4 capacity a transfer into HostBase must respect HostBase's alien
              containment and hangars (host validator)
  V5 rearm    craft weapon rearm at HostBase is refused, and the visitor is
              told so (STR_COOP_ACTION_REFUSED) instead of a silent drop
  V6 harness  open_craft_info with an unknown craft id is an error
  V7 order    moving a base in the mini strip must not reorder the base list
              (commands address bases by index): a later buy lands in the
              right base
  V8 strip    with 10 bases, an own base past index 8 is in the mini strip
              and its on-screen hotkey selects it

Exit 0 = every row passed. Any other rc is a failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture
from separate_campaign_fixture import soldiers_at

RIFLE = "STR_RIFLE"
LIVE_ALIEN = "STR_SECTOID_SOLDIER"
KEY_BASE_SELECT_2 = 50  # SDLK_2, the default keyBaseSelect2

failures = []


def check(row, ok, detail):
    print(("PASS " if ok else "[FAIL] ") + row + ("" if ok else f": {detail}"))
    if not ok:
        failures.append(row)


def poll(fn, timeout=20.0, interval=0.4):
    """Return fn()'s first truthy value, or None after timeout (no raise:
    a row records its own verdict)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(interval)
    return None


def ids_at(gc, base):
    return [s["id"] for s in soldiers_at(gc, base)]


def stats(gc):
    return gc.ok({"cmd": "shared_stats"})


def base_crafts(gc, base):
    return next(b for b in gc.ok({"cmd": "geo_state"})["bases"]
                if b["name"] == base)["crafts"]


def dismiss_fail(gc):
    try:
        gc.ok({"cmd": "coop_dialog_back"})
    except Exception:
        pass


def hire_guests(host, client, count):
    before = {s["id"] for s in soldiers_at(host, "HostBase")}
    client.ok({"cmd": "buy", "item": "STR_SOLDIER", "count": count,
               "kind": "soldier", "base": "HostBase"})
    for gc in (host, client):
        gc.wait_for("visitor recruits en route",
                    lambda gc=gc: (gc.ok({"cmd": "incoming_transfers",
                                         "base": "HostBase"})["soldiers"] == count) or None,
                    timeout=30, interval=0.5)
    host.ok({"cmd": "force_transfer_arrivals", "base": "HostBase"})
    client.wait_for("visitor recruits arrived on the replica",
                    lambda: (client.ok({"cmd": "incoming_transfers",
                                        "base": "HostBase"})["soldiers"] == 0) or None,
                    timeout=30, interval=0.5)
    guests = [s["id"] for s in soldiers_at(host, "HostBase")
              if s["id"] not in before and s["owner"] == 1]
    assert len(guests) == count, (guests, soldiers_at(host, "HostBase"))
    client.wait_for("guests on the replica roster",
                    lambda: set(guests) <= set(ids_at(client, "HostBase")) or None,
                    timeout=30, interval=0.5)
    return guests


def row_sack(host, client, guest):
    client.ok({"cmd": "sack", "base": "HostBase", "soldierId": guest})
    gone = poll(lambda: (guest not in ids_at(host, "HostBase")
                         and guest not in ids_at(client, "HostBase")) or None)
    check("V1 sack: visitor's own soldier at the foreign base leaves the host world",
          bool(gone),
          f"host has={guest in ids_at(host, 'HostBase')} "
          f"client has={guest in ids_at(client, 'HostBase')}")


def row_rename(host, client, guest):
    name = "Visitor Renamed"
    client.ok({"cmd": "soldier_rename", "base": "HostBase", "soldierId": guest,
               "name": name})

    def host_name():
        return next((s["name"] for s in soldiers_at(host, "HostBase")
                     if s["id"] == guest), None)
    ok = poll(lambda: host_name() == name or None)
    check("V2 rename: the host world carries the visitor's rename", bool(ok),
          f"host name={host_name()!r}")


def row_reorder(host, client):
    # Compare each machine with itself: an earlier red row can leave the two
    # rosters different, and this row is about the order, not the membership.
    before_host = ids_at(host, "HostBase")
    before_client = ids_at(client, "HostBase")
    client.ok({"cmd": "open_soldiers", "base": "HostBase"})
    client.ok({"cmd": "soldiers_reorder", "action": "move_up", "row": 1})
    after_move = ids_at(client, "HostBase")
    names = {s["id"]: s["name"] for s in soldiers_at(client, "HostBase")}
    by_name = sorted(before_client, key=lambda i: names[i])
    client.ok({"cmd": "soldiers_reorder", "action": "sort", "sort": 2})
    after_sort = ids_at(client, "HostBase")
    client.ok({"cmd": "soldiers_ok"})
    check("V3 reorder: move-up leaves the foreign roster order unchanged",
          after_move == before_client, f"before={before_client} after={after_move}")
    check("V3 reorder: sort leaves the foreign roster order unchanged"
          + ("" if by_name != before_client else " (vacuous: already name order)"),
          after_sort == before_client, f"before={before_client} after={after_sort}")
    check("V3 reorder: host roster order untouched",
          ids_at(host, "HostBase") == before_host,
          f"host={ids_at(host, 'HostBase')}")


def row_capacity(host, client):
    report = host.ok({"cmd": "base_report", "base": "HostBase"})
    free_hangars = report["availableHangars"] - report["usedHangars"]
    assert free_hangars == 0, ("premise: HostBase hangars full", report)

    # Live alien into a base with no alien containment.
    for gc in (host, client):
        gc.ok({"cmd": "give_items", "item": LIVE_ALIEN, "count": 1,
               "base": "ClientBase"})
    host.ok({"cmd": "shared_reset_stats"})
    client.ok({"cmd": "shared_reset_stats"})
    client.ok({"cmd": "shared_transfer", "item": LIVE_ALIEN, "count": 1,
               "fromBase": "ClientBase", "toBase": "HostBase"})
    verdict = poll(lambda: (lambda inc, st:
                   ("accepted" if inc.get(LIVE_ALIEN, 0) else
                    "rejected" if st["failCount"] else None))(
                       host.ok({"cmd": "incoming_transfers", "base": "HostBase"})["items"],
                       stats(client)))
    check("V4 capacity: a live alien is refused at a base without containment",
          verdict == "rejected"
          and stats(client)["lastFail"] == "STR_NO_ALIEN_CONTAINMENT_FOR_TRANSFER",
          f"verdict={verdict} client lastFail={stats(client)['lastFail']!r}")
    dismiss_fail(client)

    # A craft into HostBase, whose hangars are full. shared_transfer finds the
    # craft by id alone: use an interceptor whose id no other craft at the base
    # shares (the host gives the client's starting crafts world-unique ids).
    crafts = base_crafts(client, "ClientBase")
    interceptor = next((c for c in crafts if c["type"] == "STR_INTERCEPTOR"
                        and sum(o["id"] == c["id"] for o in crafts) == 1), None)
    assert interceptor, crafts
    host.ok({"cmd": "shared_reset_stats"})
    client.ok({"cmd": "shared_reset_stats"})
    client.ok({"cmd": "shared_transfer", "craft_id": interceptor["id"],
               "fromBase": "ClientBase", "toBase": "HostBase"})
    verdict = poll(lambda: (lambda inc, st:
                   ("accepted" if inc.get("crafts", 0) else
                    "rejected" if st["failCount"] else None))(
                       host.ok({"cmd": "incoming_transfers", "base": "HostBase"}),
                       stats(client)))
    check("V4 capacity: a craft is refused at a base with no free hangar",
          verdict == "rejected"
          and stats(client)["lastFail"] == "STR_NO_FREE_HANGARS_FOR_TRANSFER",
          f"verdict={verdict} client lastFail={stats(client)['lastFail']!r}")
    dismiss_fail(client)


def row_rearm(host, client):
    # craft_rearm finds a craft by id alone, and craft ids are per type: use an
    # armed interceptor whose id no other craft at the base shares.
    crafts = base_crafts(host, "HostBase")
    interceptor = next(c for c in crafts
                       if c["type"] == "STR_INTERCEPTOR" and c["weaponLoadout"][0]
                       and sum(o["id"] == c["id"] for o in crafts) == 1)
    craft_id, armed = interceptor["id"], interceptor["weaponLoadout"][0]
    host.ok({"cmd": "shared_reset_stats"})
    client.ok({"cmd": "shared_reset_stats"})
    sent = client.cmd({"cmd": "craft_rearm", "weapon": "", "slot": 0,
                       "base": "HostBase", "craft_id": craft_id})
    assert sent.get("moved"), sent

    def loadout():
        return next(c for c in base_crafts(host, "HostBase")
                    if c["id"] == craft_id and c["type"] == "STR_INTERCEPTOR"
                    )["weaponLoadout"][0]
    verdict = poll(lambda: ("applied" if loadout() != armed else
                            "rejected" if stats(client)["failCount"] else None))
    check("V5 rearm: a visitor's craft weapon change is refused by the host",
          verdict == "rejected", f"verdict={verdict} loadout={loadout()!r}")
    last = stats(client)["lastFail"]
    check("V5 rearm: the visitor is told the action was refused",
          last == "STR_COOP_ACTION_REFUSED", f"client lastFail={last!r}")
    dismiss_fail(client)


def row_open_craft_info(host):
    r = host.cmd({"cmd": "open_craft_info", "base": "HostBase", "craft_id": 999})
    opened = bool(r.get("ok"))
    if opened:
        host.ok({"cmd": "pop_state"})
    check("V6 harness: open_craft_info with an unknown craft id is an error",
          not opened, f"resp={r}")


def base_order(gc):
    return [b["name"] for b in gc.ok({"cmd": "geo_state"})["bases"]]


def row_base_order(host, client):
    host_order = base_order(host)
    assert host_order == base_order(client), (host_order, base_order(client))
    client.ok({"cmd": "open_screen", "screen": "basescape", "base": "ClientBase"})
    client.ok({"cmd": "basescape_move_base_left", "base": "ClientBase"})
    client_order = base_order(client)
    client.ok({"cmd": "leave_base"})
    check("V7 order: moving a base in the strip keeps both machines' base order",
          client_order == base_order(host),
          f"host={base_order(host)} client={client_order}")

    def incoming(base):
        return host.ok({"cmd": "incoming_transfers", "base": base})["items"].get(RIFLE, 0)
    before = {b: incoming(b) for b in ("HostBase", "ClientBase")}
    client.ok({"cmd": "buy", "item": RIFLE, "count": 1, "base": "ClientBase"})
    landed = poll(lambda: next((b for b in before if incoming(b) == before[b] + 1), None))
    check("V7 order: the visitor's buy for ClientBase lands in ClientBase",
          landed == "ClientBase", f"landed in {landed}")


def row_strip(host, client):
    # Same eight extra bases on both machines (no checksum resync): seven owned
    # by the client, then one owned by the host at index 9.
    for i in range(7):
        for gc in (host, client):
            gc.ok({"cmd": "add_base", "name": f"ClientExtra{i}",
                   "lon": 0.2 + 0.3 * i, "lat": -0.4, "coopbaseid": 71000 + i,
                   "ownerPlayerName": "ClientPlayer"})
    for gc in (host, client):
        r = gc.ok({"cmd": "add_base", "name": "HostLate", "lon": 2.9, "lat": 0.5,
                   "coopbaseid": 71100, "ownerPlayerName": "HostPlayer"})
    assert r["baseCount"] == 10, r
    host.ok({"cmd": "open_screen", "screen": "basescape", "base": "HostBase"})
    menu = host.ok({"cmd": "basescape_menu_state"})
    slot = menu["miniDisplaySlots"].get("HostLate", -1)
    check("V8 strip: an own base past index 8 has a mini-strip slot",
          slot >= 0, f"slots={menu['miniDisplaySlots']}")
    host.ok({"cmd": "inject_input", "kind": "key", "key": KEY_BASE_SELECT_2})
    selected = poll(lambda: (lambda b: b if b != "HostBase" else None)(
        host.ok({"cmd": "basescape_menu_state"})["base"]), timeout=10)
    check("V8 strip: the second hotkey selects the base in the second slot",
          selected == "HostLate" and slot == 1,
          f"selected={selected} HostLate slot={slot}")
    host.ok({"cmd": "leave_base"})


def main():
    js = fixture.bring_up("sep_visitor", (49760, 49761, 49060))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        guests = hire_guests(host, client, 3)
        row_sack(host, client, guests[0])
        row_rename(host, client, guests[1])
        row_reorder(host, client)
        row_capacity(host, client)
        row_rearm(host, client)
        row_open_craft_info(host)
        row_base_order(host, client)
        row_strip(host, client)
    finally:
        js.shutdown()
    if failures:
        print(f"FAIL {len(failures)} row(s): {failures}")
        sys.exit(3)
    print("PASS Separate visitor actions at another player's base")


if __name__ == "__main__":
    main()
