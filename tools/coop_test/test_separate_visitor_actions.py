"""Separate Campaign: what a visitor does at another player's base (PR #213 RU8).

The client is the visitor at HostBase, where it has hired its own soldiers.
Every row checks the AUTHORITATIVE host world, not only the visitor's screen:

  V1 sack     the visitor sacks its own soldier there -> gone on both machines
  V2 rename   the visitor renames its own soldier there -> the host has the name
  V3 reorder  move-up and sort on the visitor's filtered list leave the roster
              order identical on both machines (a visitor never reorders there)
  V9 armor    RU16: the visitor changes its own soldier's armor there, taking
              it from that base's stores; the partner's soldier stays refused
  V12 transform  the soldier transformation view lists only the local
              player's soldiers, on either machine
  V4 capacity a transfer into HostBase must respect HostBase's alien
              containment and hangars (host validator)
  V5 rearm    craft weapon rearm at HostBase is refused, and the visitor is
              told so (STR_COOP_ACTION_REFUSED) instead of a silent drop
  V6 harness  open_craft_info with an unknown craft id is an error
  V10 transfer  RU17: the visitor transfers its own soldier out of HostBase;
              items, mixed payloads and the partner's soldiers stay refused
  V11 roster  move up / down at the player's own base goes through the host:
              both machines end with the same new order
  V7 order    moving a base in the mini strip goes through the host: both
              machines end with the same new order, and a buy sent right after
              the move still lands in the base it named
  V8 strip    with 10 bases, an own base past index 8 is in the mini strip
              and its on-screen hotkey selects it
  V13 sell    the random production summary's sell goes through the host
  V14 harness craft_rearm / craft_assign take craft_type and refuse an id
              that more than one craft type at the base uses
  V15 warning the month-end economy warning uses each player's own wallet
              and maintenance, and only that player sees it

Exit 0 = every row passed. Any other rc is a failure.
"""

import calendar
import os
import re
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture
from separate_campaign_fixture import soldiers_at

RIFLE = "STR_RIFLE"
LIVE_ALIEN = "STR_SECTOID_SOLDIER"
ARMOR = "STR_PERSONAL_ARMOR_UC"
ARMOR_ITEM = "STR_PERSONAL_ARMOR"
TRANSFORM = "STR_COOP_TEST_TRANSFORM"
KEY_BASE_SELECT_2 = 50  # SDLK_2, the default keyBaseSelect2

MOD_NAME = "coop_visitor_actions"
METADATA = """\
name: "Coop visitor actions test"
version: 1.0
description: "Test-only: a soldier transformation open to every live soldier."
author: coop harness

master: xcom1
"""
RULESET = f"""\
soldierTransformation:
  - name: {TRANSFORM}
    allowsLiveSoldiers: true
    allowsWoundedSoldiers: true
    allowedSoldierTypes:
      - STR_SOLDIER
"""

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


def make_mod(root):
    mod = os.path.join(root, MOD_NAME)
    os.makedirs(os.path.join(mod, "Ruleset"))
    with open(os.path.join(mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write(METADATA)
    with open(os.path.join(mod, "Ruleset", "visitor.rul"), "w", encoding="utf-8") as f:
        f.write(RULESET)
    return mod


def ids_at(gc, base):
    return [s["id"] for s in soldiers_at(gc, base)]


def own_ids_at(gc, base, owner):
    return [s["id"] for s in soldiers_at(gc, base) if s["owner"] == owner]


def soldier(gc, base, sid):
    return next((s for s in soldiers_at(gc, base) if s["id"] == sid), None)


def stats(gc):
    return gc.ok({"cmd": "shared_stats"})


def reset_stats(host, client):
    host.ok({"cmd": "shared_reset_stats"})
    client.ok({"cmd": "shared_reset_stats"})


def stock(gc, base, item):
    return gc.ok({"cmd": "base_report", "base": base})["storage"].get(item, 0)


def owner_funds(gc, base):
    return gc.ok({"cmd": "base_report", "base": base})["ownerFunds"]


def base_crafts(gc, base):
    return next(b for b in gc.ok({"cmd": "geo_state"})["bases"]
                if b["name"] == base)["crafts"]


def base_order(gc):
    return [b["name"] for b in gc.ok({"cmd": "geo_state"})["bases"]]


def dismiss_fail(gc):
    try:
        gc.ok({"cmd": "coop_dialog_back"})
    except Exception:
        pass


def wait_refused(host, client, reason="STR_COOP_ACTION_REFUSED"):
    """The client's last command was refused with <reason> (None on timeout)."""
    seen = poll(lambda: stats(client)["failCount"] or None)
    last = stats(client)["lastFail"]
    dismiss_fail(client)
    return bool(seen) and last == reason, last


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
    time.sleep(1.0)  # a host-routed move would have landed by now
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


def row_armor(host, client, guest):
    """RU16: the visitor's own soldier at HostBase takes armor from HostBase's
    stores through the host; the host's soldier there stays refused."""
    for gc in (host, client):
        gc.ok({"cmd": "give_items", "item": ARMOR_ITEM, "count": 2, "base": "HostBase"})
    before = stock(host, "HostBase", ARMOR_ITEM)
    reset_stats(host, client)
    r = client.cmd({"cmd": "soldier_armor", "base": "HostBase",
                    "soldier_id": guest, "armor": ARMOR})
    worn = poll(lambda: ((soldier(host, "HostBase", guest) or {}).get("armor") == ARMOR
                         and (soldier(client, "HostBase", guest) or {}).get("armor") == ARMOR)
                or None)
    check("V9 armor: the visitor's own soldier wears the new armor on both machines",
          bool(worn),
          f"resp={r} host={(soldier(host, 'HostBase', guest) or {}).get('armor')} "
          f"client={(soldier(client, 'HostBase', guest) or {}).get('armor')} "
          f"client lastFail={stats(client)['lastFail']!r}")
    dismiss_fail(client)
    after = (stock(host, "HostBase", ARMOR_ITEM), stock(client, "HostBase", ARMOR_ITEM))
    check("V9 armor: the armor came out of HostBase's stores on both machines",
          after == (before - 1, before - 1), f"before={before} after(host,client)={after}")

    partner = next(s for s in soldiers_at(host, "HostBase") if s["owner"] == 0)
    reset_stats(host, client)
    client.cmd({"cmd": "soldier_armor", "base": "HostBase",
                "soldier_id": partner["id"], "armor": ARMOR})
    refused, last = wait_refused(host, client, "STR_COOP_NOT_YOUR_SOLDIER")
    check("V9 armor: the partner's soldier at HostBase is refused as not the visitor's",
          refused and soldier(host, "HostBase", partner["id"])["armor"] == partner["armor"],
          f"lastFail={last!r} host armor={soldier(host, 'HostBase', partner['id'])['armor']}")


def row_transform_view(host, client):
    """The transformation view lists only the local player's soldiers."""
    for gc, owner in ((client, 1), (host, 0)):
        gc.ok({"cmd": "open_soldiers", "base": "HostBase"})
        r = gc.cmd({"cmd": "soldiers_view", "action": TRANSFORM})
        gc.ok({"cmd": "soldiers_view", "action": "STR_SOLDIER_INFO"})
        gc.ok({"cmd": "soldiers_ok"})
        owners = {s["id"]: s["owner"] for s in soldiers_at(gc, "HostBase")}
        shown = r.get("ids", [])
        expected = own_ids_at(gc, "HostBase", owner)
        check(f"V12 transform: {gc.name}'s transformation view shows only its own soldiers",
              r.get("ok") and sorted(shown) == sorted(expected),
              f"resp={r} shown owners={[owners.get(i) for i in shown]} expected={expected}")


def row_capacity(host, client):
    report = host.ok({"cmd": "base_report", "base": "HostBase"})
    free_hangars = report["availableHangars"] - report["usedHangars"]
    assert free_hangars == 0, ("premise: HostBase hangars full", report)

    # Live alien into a base with no alien containment.
    for gc in (host, client):
        gc.ok({"cmd": "give_items", "item": LIVE_ALIEN, "count": 1,
               "base": "ClientBase"})
    reset_stats(host, client)
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

    # A craft into HostBase, whose hangars are full.
    crafts = [c for c in base_crafts(client, "ClientBase") if c["id"] == 2]
    assert len(crafts) == 1 and crafts[0]["type"] == "STR_INTERCEPTOR", crafts
    reset_stats(host, client)
    client.ok({"cmd": "shared_transfer", "craft_id": 2,
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
    # An armed interceptor whose id no other craft at the base shares, so the
    # row does not depend on V14's lever fix.
    crafts = base_crafts(host, "HostBase")
    interceptor = next(c for c in crafts
                       if c["type"] == "STR_INTERCEPTOR" and c["weaponLoadout"][0]
                       and sum(o["id"] == c["id"] for o in crafts) == 1)
    craft_id, armed = interceptor["id"], interceptor["weaponLoadout"][0]
    reset_stats(host, client)
    sent = client.cmd({"cmd": "craft_rearm", "weapon": "", "slot": 0,
                       "base": "HostBase", "craft_id": craft_id,
                       "craft_type": "STR_INTERCEPTOR"})
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


def base_index(gc, name):
    return base_order(gc).index(name)


def row_transfer_out(host, client, guest):
    """RU17: only the visitor's own soldiers may leave HostBase on its order."""
    partner = next(s["id"] for s in soldiers_at(host, "HostBase") if s["owner"] == 0)
    for gc in (host, client):
        gc.ok({"cmd": "give_items", "item": RIFLE, "count": 1, "base": "HostBase"})
    rifles = stock(host, "HostBase", RIFLE)
    src, dst = base_index(client, "HostBase"), base_index(client, "ClientBase")

    # Refused: the partner's items, a payload mixing the visitor's soldier with
    # an item, and the partner's soldier (raw commands: the screen lists only
    # the visitor's own soldiers).
    reset_stats(host, client)
    client.ok({"cmd": "shared_transfer", "item": RIFLE, "count": 1,
               "fromBase": "HostBase", "toBase": "ClientBase"})
    refused, last = wait_refused(host, client)
    check("V10 transfer: the partner's items stay at HostBase",
          refused and stock(host, "HostBase", RIFLE) == rifles,
          f"lastFail={last!r} rifles {rifles}->{stock(host, 'HostBase', RIFLE)}")
    for label, payload in (
            ("own soldier plus an item", {"soldiers": [guest],
                                          "items": [{"rule": RIFLE, "qty": 1}]}),
            ("the partner's soldier", {"soldiers": [partner]})):
        reset_stats(host, client)
        payload.update({"toBaseId": dst, "crafts": [], "scientists": 0, "engineers": 0})
        payload.setdefault("items", [])
        client.ok({"cmd": "shared_cmd", "jcmd": "transfer", "baseId": src,
                   "payload": payload})
        refused, last = wait_refused(host, client)
        check(f"V10 transfer: {label} is refused",
              refused and {guest, partner} <= set(ids_at(host, "HostBase")),
              f"lastFail={last!r} host HostBase={ids_at(host, 'HostBase')}")

    reset_stats(host, client)
    before = host.ok({"cmd": "incoming_transfers", "base": "ClientBase"})["soldiers"]
    funds = owner_funds(host, "ClientBase")
    r = client.cmd({"cmd": "shared_transfer", "soldier_id": guest,
                    "fromBase": "HostBase", "toBase": "ClientBase"})
    moved = poll(lambda: (guest not in ids_at(host, "HostBase")
                          and host.ok({"cmd": "incoming_transfers",
                                       "base": "ClientBase"})["soldiers"] == before + 1
                          and guest not in ids_at(client, "HostBase")) or None)
    check("V10 transfer: the visitor's own soldier leaves HostBase for ClientBase",
          bool(moved),
          f"resp={r} host HostBase has={guest in ids_at(host, 'HostBase')} "
          f"client lastFail={stats(client)['lastFail']!r}")
    dismiss_fail(client)
    paid = owner_funds(host, "ClientBase")
    check("V10 transfer: the visitor's wallet pays for it",
          not moved or paid < funds, f"funds {funds}->{paid}")


def row_own_roster(host, client):
    """Move up / down at the player's own base goes through the host."""
    before = own_ids_at(client, "ClientBase", 1)
    assert len(before) >= 3, ("premise: three own soldiers at ClientBase", before)
    client.ok({"cmd": "open_soldiers", "base": "ClientBase"})
    client.ok({"cmd": "soldiers_reorder", "action": "move_up", "row": 2, "max": True})
    want = [before[2]] + before[:2] + before[3:]
    got = poll(lambda: (own_ids_at(host, "ClientBase", 1) == want
                        and own_ids_at(client, "ClientBase", 1) == want) or None)
    check("V11 roster: move-to-top at the own base reorders both machines",
          bool(got), f"want={want} host={own_ids_at(host, 'ClientBase', 1)} "
          f"client={own_ids_at(client, 'ClientBase', 1)}")
    start = own_ids_at(client, "ClientBase", 1)
    client.ok({"cmd": "soldiers_reorder", "action": "move_down", "row": 0, "max": False})
    want = [start[1], start[0]] + start[2:]
    got = poll(lambda: (own_ids_at(host, "ClientBase", 1) == want
                        and own_ids_at(client, "ClientBase", 1) == want) or None)
    client.ok({"cmd": "soldiers_ok"})
    check("V11 roster: move-down one place at the own base reorders both machines",
          bool(got), f"want={want} host={own_ids_at(host, 'ClientBase', 1)} "
          f"client={own_ids_at(client, 'ClientBase', 1)}")
    check("V11 roster: both machines hold the same full roster order",
          ids_at(host, "ClientBase") == ids_at(client, "ClientBase"),
          f"host={ids_at(host, 'ClientBase')} client={ids_at(client, 'ClientBase')}")


def row_base_order(host, client):
    for gc in (host, client):
        gc.ok({"cmd": "add_base", "name": "ClientSecond", "lon": 0.1, "lat": -0.9,
               "coopbaseid": 71200, "ownerPlayerName": "ClientPlayer"})
    start = base_order(host)
    assert start == base_order(client), (start, base_order(client))
    assert start.index("ClientBase") < start.index("ClientSecond"), start

    # A visitor cannot move the partner's base.
    client.ok({"cmd": "open_screen", "screen": "basescape", "base": "HostBase"})
    client.ok({"cmd": "basescape_move_base_left", "base": "HostBase"})
    client.ok({"cmd": "leave_base"})
    time.sleep(1.0)
    check("V7 order: the visitor cannot move the partner's base",
          base_order(host) == start and base_order(client) == start,
          f"start={start} host={base_order(host)} client={base_order(client)}")

    def incoming(gc, base):
        return gc.ok({"cmd": "incoming_transfers", "base": base})["items"].get(RIFLE, 0)
    before = {(gc.name, b): incoming(gc, b) for gc in (host, client)
              for b in ("ClientBase", "ClientSecond")}
    client.ok({"cmd": "open_screen", "screen": "basescape", "base": "ClientSecond"})
    client.ok({"cmd": "basescape_move_base_left", "base": "ClientSecond"})
    # Sent before the move comes back: the buy names ClientBase by its old index.
    client.ok({"cmd": "buy", "item": RIFLE, "count": 1, "base": "ClientBase"})
    client.ok({"cmd": "leave_base"})
    want = [b for b in start if b != "ClientSecond"]
    want.insert(want.index("ClientBase"), "ClientSecond")
    moved = poll(lambda: (base_order(host) == want and base_order(client) == want) or None)
    check("V7 order: moving an own base left reorders both machines the same way",
          bool(moved), f"want={want} host={base_order(host)} client={base_order(client)}")
    landed = poll(lambda: all(incoming(gc, "ClientBase") == before[(gc.name, "ClientBase")] + 1
                              for gc in (host, client)) or None)
    check("V7 order: the buy sent right after the move lands in ClientBase on both machines",
          bool(landed) and all(incoming(gc, "ClientSecond") == before[(gc.name, "ClientSecond")]
                               for gc in (host, client)),
          {f"{gc.name}:{b}": incoming(gc, b) for gc in (host, client)
           for b in ("ClientBase", "ClientSecond")})


def row_strip(host, client):
    # Same extra bases on both machines (no checksum resync): owned by the
    # client, then one owned by the host at index 9.
    count = 9 - len(base_order(host))
    for i in range(count):
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


def row_production_sell(host, client):
    """The random production summary's sell is a host command (no local change)."""
    for gc in (host, client):
        gc.ok({"cmd": "give_items", "item": RIFLE, "count": 3, "base": "ClientBase"})
    stock0 = stock(host, "ClientBase", RIFLE)
    funds0 = owner_funds(host, "ClientBase")
    client.ok({"cmd": "production_complete_sell", "base": "ClientBase",
               "item": RIFLE, "count": 2})
    sold = poll(lambda: (stock(host, "ClientBase", RIFLE) == stock0 - 2
                         and stock(client, "ClientBase", RIFLE) == stock0 - 2) or None)
    check("V13 sell: the sale leaves the host world's stores, and the replica follows",
          bool(sold), f"stock0={stock0} host={stock(host, 'ClientBase', RIFLE)} "
          f"client={stock(client, 'ClientBase', RIFLE)}")
    host_funds, client_funds = owner_funds(host, "ClientBase"), owner_funds(client, "ClientBase")
    check("V13 sell: the proceeds reach the seller's host wallet, the same on both machines",
          host_funds > funds0 and client_funds == host_funds,
          f"funds0={funds0} host={host_funds} client={client_funds}")


def two_weapon_types_share_id(gc):
    crafts = [c for c in base_crafts(gc, "HostBase") if c["weaponLoadout"]]
    ids = [c["id"] for c in crafts]
    return next((i for i in ids if ids.count(i) > 1), None)


def row_craft_levers(host, client):
    """craft_rearm / craft_assign: craft_type selects, an ambiguous id errors."""
    for craft_type in ("STR_FIRESTORM", "STR_AVENGER"):
        for gc in (host, client):
            gc.ok({"cmd": "spawn_craft", "type": craft_type, "base": "HostBase"})
    crafts = base_crafts(host, "HostBase")
    shared = two_weapon_types_share_id(host)
    assert shared is not None, ("premise: two armed types share an id", crafts)
    firestorm = next(c for c in crafts if c["type"] == "STR_FIRESTORM")
    assert firestorm["id"] == shared and firestorm["weaponLoadout"][0], firestorm

    r = host.cmd({"cmd": "craft_rearm", "weapon": "", "slot": 0,
                  "base": "HostBase", "craft_id": shared})
    check("V14 harness: craft_rearm with an id two armed craft types share is an error",
          not r.get("ok") and "ambiguous" in r.get("error", ""), f"resp={r}")
    r = host.cmd({"cmd": "craft_rearm", "weapon": "", "slot": 0, "base": "HostBase",
                  "craft_id": shared, "craft_type": "STR_FIRESTORM"})

    def firestorm_slot():
        return next(c for c in base_crafts(host, "HostBase")
                    if c["type"] == "STR_FIRESTORM")["weaponLoadout"][0]
    emptied = poll(lambda: firestorm_slot() == "" or None, timeout=10)
    check("V14 harness: craft_rearm with craft_type rearms that craft",
          r.get("ok") and bool(emptied), f"resp={r} firestorm slot0={firestorm_slot()!r}")

    sky = next(c for c in base_crafts(host, "HostBase") if c["type"] == "STR_SKYRANGER")
    for _ in range(4):  # the next Avenger id reaches the Skyranger's
        avenger = next((c for c in base_crafts(host, "HostBase")
                        if c["type"] == "STR_AVENGER" and c["id"] == sky["id"]), None)
        if avenger:
            break
        for gc in (host, client):
            gc.ok({"cmd": "spawn_craft", "type": "STR_AVENGER", "base": "HostBase"})
    assert avenger, ("premise: an Avenger shares the Skyranger's id",
                     base_crafts(host, "HostBase"))
    sid = next(s["id"] for s in soldiers_at(host, "HostBase") if s["owner"] == 0)
    r = host.cmd({"cmd": "craft_assign", "base": "HostBase", "craft_id": sky["id"],
                  "soldier_id": sid, "on": True})
    check("V14 harness: craft_assign with an id two transport types share is an error",
          not r.get("ok") and "ambiguous" in r.get("error", ""), f"resp={r}")
    r = host.cmd({"cmd": "craft_assign", "base": "HostBase", "craft_id": avenger["id"],
                  "craft_type": "STR_AVENGER", "soldier_id": sid, "on": True})
    seated = poll(lambda: (soldier(host, "HostBase", sid) or {}).get("craft") == "STR_AVENGER"
                  or None, timeout=10)
    check("V14 harness: craft_assign with craft_type seats on that craft",
          r.get("ok") and bool(seated), f"resp={r} soldier={soldier(host, 'HostBase', sid)}")


def warning_messages(gc):
    return [m for m in gc.ok({"cmd": "craft_error_messages"})["messages"]
            if "funds missing" in m]


def digits(text):
    return re.sub(r"(?<=\d)[^\w\-](?=\d)", "", text)


def last_day_warnings(host, client, host_funds, client_funds):
    """Set both wallets, run the clock into the last day of the month and return
    each machine's economy warnings."""
    for gc in (host, client):
        geo.drain_popups(gc)
        gc.ok({"cmd": "set_funds", "player": "HostPlayer", "value": host_funds})
        gc.ok({"cmd": "set_funds", "player": "ClientPlayer", "value": client_funds})
    t = fixture.geo(host)["time"]
    days = calendar.monthrange(t["year"], t["month"])[1]
    host.ok({"cmd": "set_geo_day", "day": days - 1, "hour": 23})
    for gc in (host, client):
        gc.ok({"cmd": "geo_set_speed", "idx": 3})
    reached = None
    deadline = time.time() + 60
    while time.time() < deadline:
        if fixture.geo(host)["time"]["day"] == days:
            reached = reached or time.time()
            if time.time() - reached > 4:
                break
        time.sleep(0.3)
    for gc in (host, client):
        gc.ok({"cmd": "geo_set_speed", "idx": 0})
    assert reached, ("premise: the clock reached the last day", fixture.geo(host)["time"])
    return warning_messages(host), warning_messages(client)


def row_economy_warning(host, client):
    host_msgs, client_msgs = last_day_warnings(host, client, 900000000, -7123457)
    check("V15 warning: a player in the red sees the warning with their own funds",
          len(client_msgs) == 1 and "7123457" in digits(client_msgs[0]),
          f"client={client_msgs}")
    check("V15 warning: the player in the black sees no warning",
          host_msgs == [], f"host={host_msgs}")
    host_msgs, client_msgs = last_day_warnings(host, client, -3111113, 900000000)
    check("V15 warning: the host in the red sees its own funds",
          len(host_msgs) == 1 and "3111113" in digits(host_msgs[0]), f"host={host_msgs}")
    check("V15 warning: the client in the black is not shown the host's warning",
          client_msgs == [], f"client={client_msgs}")
    for gc in (host, client):
        geo.drain_popups(gc)


def main():
    tmp = tempfile.mkdtemp(prefix="coop_visitor_actions_")
    try:
        mod = make_mod(tmp)
        js = fixture.bring_up("sep_visitor", (49760, 49761, 49060), mods=[mod])
        host, client = js.host, js.client
        try:
            fixture.assert_fresh_named_world(host, client)
            guests = hire_guests(host, client, 3)
            row_sack(host, client, guests[0])
            row_rename(host, client, guests[1])
            row_reorder(host, client)
            row_armor(host, client, guests[1])
            row_transform_view(host, client)
            row_capacity(host, client)
            row_rearm(host, client)
            row_open_craft_info(host)
            row_transfer_out(host, client, guests[2])
            row_own_roster(host, client)
            row_base_order(host, client)
            row_strip(host, client)
            row_production_sell(host, client)
            row_craft_levers(host, client)
            row_economy_warning(host, client)
        finally:
            js.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print(f"FAIL {len(failures)} row(s): {failures}")
        sys.exit(3)
    print("PASS Separate visitor actions at another player's base")


if __name__ == "__main__":
    main()
