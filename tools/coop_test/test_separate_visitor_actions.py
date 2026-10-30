"""Separate Campaign: what a visitor does at another player's base.

The client is the visitor at HostBase, where it has hired its own soldiers.
Every row checks the AUTHORITATIVE host world, not only the visitor's screen:

  sack            the visitor sacks its own soldier there -> gone on both machines
  rename          the visitor renames its own soldier there -> the host has the name
  reorder         move-up and sort on the visitor's filtered list leave the roster
                  order identical on both machines (a visitor never reorders there)
  armor           the visitor changes its own soldier's armor there, taking it
                  from that base's stores; the partner's soldier stays refused
  transform view  the soldier transformation view lists only the local player's
                  soldiers, on either machine
  capacity        a transfer into HostBase must respect HostBase's alien
                  containment and hangars (host validator)
  rearm           craft weapon rearm at HostBase is refused, and the visitor is
                  told so (STR_COOP_ACTION_REFUSED) instead of a silent drop
  harness         open_craft_info with an unknown craft id is an error
  transfer        the visitor transfers its own soldier out of HostBase; items,
                  mixed payloads and the partner's soldiers stay refused
  roster          move up / down at the player's own base goes through the host:
                  both machines end with the same new order
  sort            sorting the Soldiers screen at the player's own base (and
                  picking the original order again) goes through the host too
  training sort   a name sort (and the original order) on the martial / psi
                  training screen sorts what the screen shows; both machines keep
                  the same roster order
  training        putting a soldier into martial / psi training goes through the
                  host: the client's own soldier at its base (and the host trains
                  it), the visitor's own soldier at HostBase, the host's own
                  soldier; the partner's soldier stays refused and assign-all
                  changes only the player's own soldiers
  craft armor     the crew armor screen's name sort and original order at the own
                  base reorder both machines the same way; the host sorts its
                  soldiers at HostBase while the visitor's crew armor screen is
                  open there, and the visitor's original order then keeps both
                  machines the same
  craft crew      a move on the craft crew screen at the own base, then the
                  original order, brings the order back on both machines
  transform       a soldier transformation runs on the host: its result and cost
                  reach both machines and the partner's soldier is refused. A
                  visitor transforms its own soldier at the partner base, as it
                  changes its armor there: the visitor's wallet pays, required
                  items come from that base's stores, and the partner's soldier
                  there stays refused
  order           moving a base in the mini strip goes through the host: both
                  machines end with the same new order, and a buy sent right after
                  the move still lands in the base it named
  cydonia         a craft request (separate_cydonia_request) built before a base
                  move still names its craft when the host reads it
  strip           with 10 bases, an own base past index 8 is in the mini strip
                  and its on-screen hotkey selects it
  sell            the random production summary's sell goes through the host
  harness         craft_rearm / craft_assign take craft_type and refuse an id
                  that more than one craft type at the base uses
  warning         the month-end economy warning uses each player's own wallet
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
TRANSFORM_PAID = "STR_COOP_TEST_TRANSFORM_PAID"
TRANSFORM_COST = 20000
TRANSFORM_FIRING = 7
TRANSFORM_KIT = "STR_COOP_TEST_TRANSFORM_KIT"
KIT_ITEM = "STR_MEDI_KIT"
KIT_COST = 30000
KIT_FIRING = 3
KEY_BASE_SELECT_2 = 50  # SDLK_2, the default keyBaseSelect2

MOD_NAME = "coop_visitor_actions"
METADATA = """\
name: "Coop visitor actions test"
version: 1.0
description: "Test-only: a soldier transformation open to every live soldier, and a gym and psi lab in every access lift."
author: coop harness

master: xcom1
"""
TRAINING_STATS = ("tu", "stamina", "health", "firing", "throwing", "melee", "strength")
RULESET = f"""\
facilities:
  - type: STR_ACCESS_LIFT
    trainingRooms: 10
    psiLabs: 10
soldierTransformation:
  - name: {TRANSFORM}
    allowsLiveSoldiers: true
    allowsWoundedSoldiers: true
    allowedSoldierTypes:
      - STR_SOLDIER
  - name: {TRANSFORM_PAID}
    allowsLiveSoldiers: true
    allowsWoundedSoldiers: true
    keepSoldierArmor: true
    allowedSoldierTypes:
      - STR_SOLDIER
    cost: {TRANSFORM_COST}
    flatOverallStatChange:
      firing: {TRANSFORM_FIRING}
  - name: {TRANSFORM_KIT}
    allowsLiveSoldiers: true
    allowsWoundedSoldiers: true
    keepSoldierArmor: true
    allowedSoldierTypes:
      - STR_SOLDIER
    cost: {KIT_COST}
    requiredItems:
      {KIT_ITEM}: 1
    flatOverallStatChange:
      firing: {KIT_FIRING}
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
    check("sack: visitor's own soldier at the foreign base leaves the host world",
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
    check("rename: the host world carries the visitor's rename", bool(ok),
          f"host name={host_name()!r}")


def row_reorder(host, client):
    # Compare each machine with itself: an earlier failing row can leave the two
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
    check("reorder: move-up leaves the foreign roster order unchanged",
          after_move == before_client, f"before={before_client} after={after_move}")
    check("reorder: sort leaves the foreign roster order unchanged"
          + ("" if by_name != before_client else " (vacuous: already name order)"),
          after_sort == before_client, f"before={before_client} after={after_sort}")
    check("reorder: host roster order untouched",
          ids_at(host, "HostBase") == before_host,
          f"host={ids_at(host, 'HostBase')}")


def row_armor(host, client, guest):
    """The visitor's own soldier at HostBase takes armor from HostBase's
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
    check("armor: the visitor's own soldier wears the new armor on both machines",
          bool(worn),
          f"resp={r} host={(soldier(host, 'HostBase', guest) or {}).get('armor')} "
          f"client={(soldier(client, 'HostBase', guest) or {}).get('armor')} "
          f"client lastFail={stats(client)['lastFail']!r}")
    dismiss_fail(client)
    after = (stock(host, "HostBase", ARMOR_ITEM), stock(client, "HostBase", ARMOR_ITEM))
    check("armor: the armor came out of HostBase's stores on both machines",
          after == (before - 1, before - 1), f"before={before} after(host,client)={after}")

    partner = next(s for s in soldiers_at(host, "HostBase") if s["owner"] == 0)
    reset_stats(host, client)
    client.cmd({"cmd": "soldier_armor", "base": "HostBase",
                "soldier_id": partner["id"], "armor": ARMOR})
    refused, last = wait_refused(host, client, "STR_COOP_NOT_YOUR_SOLDIER")
    check("armor: the partner's soldier at HostBase is refused as not the visitor's",
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
        check(f"transform: {gc.name}'s transformation view shows only its own soldiers",
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
    check("capacity: a live alien is refused at a base without containment",
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
    reset_stats(host, client)
    client.ok({"cmd": "shared_transfer", "craft_id": interceptor["id"],
               "fromBase": "ClientBase", "toBase": "HostBase"})
    verdict = poll(lambda: (lambda inc, st:
                   ("accepted" if inc.get("crafts", 0) else
                    "rejected" if st["failCount"] else None))(
                       host.ok({"cmd": "incoming_transfers", "base": "HostBase"}),
                       stats(client)))
    check("capacity: a craft is refused at a base with no free hangar",
          verdict == "rejected"
          and stats(client)["lastFail"] == "STR_NO_FREE_HANGARS_FOR_TRANSFER",
          f"verdict={verdict} client lastFail={stats(client)['lastFail']!r}")
    dismiss_fail(client)


def row_rearm(host, client):
    # An armed interceptor whose id no other craft at the base shares, so the
    # row does not depend on how craft_rearm resolves a shared id.
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
    check("rearm: a visitor's craft weapon change is refused by the host",
          verdict == "rejected", f"verdict={verdict} loadout={loadout()!r}")
    last = stats(client)["lastFail"]
    check("rearm: the visitor is told the action was refused",
          last == "STR_COOP_ACTION_REFUSED", f"client lastFail={last!r}")
    dismiss_fail(client)


def row_open_craft_info(host):
    r = host.cmd({"cmd": "open_craft_info", "base": "HostBase", "craft_id": 999})
    opened = bool(r.get("ok"))
    if opened:
        host.ok({"cmd": "pop_state"})
    check("harness: open_craft_info with an unknown craft id is an error",
          not opened, f"resp={r}")


def base_index(gc, name):
    return base_order(gc).index(name)


def row_transfer_out(host, client, guest):
    """Only the visitor's own soldiers may leave HostBase on its order."""
    partner = next(s["id"] for s in soldiers_at(host, "HostBase") if s["owner"] == 0)
    for gc in (host, client):
        gc.ok({"cmd": "give_items", "item": RIFLE, "count": 1, "base": "HostBase"})
    rifles = stock(host, "HostBase", RIFLE)
    src, dst = base_index(client, "HostBase"), base_index(client, "ClientBase")

    # The visitor's transfer screen at HostBase offers no partner items.
    r = client.cmd({"cmd": "shared_transfer", "item": RIFLE, "count": 1,
                    "fromBase": "HostBase", "toBase": "ClientBase"})
    dismiss_fail(client)
    check("transfer: the visitor's transfer screen lists none of HostBase's items",
          not r.get("ok") and "no transferable row" in r.get("error", ""), f"resp={r}")
    # Refused by the host (raw commands, as a stale or modified client would
    # send them): the partner's items, a payload mixing the visitor's soldier
    # with an item, and the partner's soldier.
    for label, payload in (
            ("the partner's items", {"soldiers": [], "items": [{"rule": RIFLE, "qty": 1}]}),
            ("own soldier plus an item", {"soldiers": [guest],
                                          "items": [{"rule": RIFLE, "qty": 1}]}),
            ("the partner's soldier", {"soldiers": [partner]})):
        reset_stats(host, client)
        payload.update({"toBaseId": dst, "crafts": [], "scientists": 0, "engineers": 0})
        payload.setdefault("items", [])
        client.ok({"cmd": "shared_cmd", "jcmd": "transfer", "baseId": src,
                   "payload": payload})
        refused, last = wait_refused(host, client)
        check(f"transfer: {label} is refused",
              refused and {guest, partner} <= set(ids_at(host, "HostBase"))
              and stock(host, "HostBase", RIFLE) == rifles,
              f"lastFail={last!r} host HostBase={ids_at(host, 'HostBase')} "
              f"rifles {rifles}->{stock(host, 'HostBase', RIFLE)}")

    # Both fixture bases stand on the same spot (the host's first placement falls
    # back to the client's), so a transfer between them costs nothing and this
    # row cannot show whose wallet pays.
    reset_stats(host, client)
    before = host.ok({"cmd": "incoming_transfers", "base": "ClientBase"})["soldiers"]
    r = client.cmd({"cmd": "shared_transfer", "soldier_id": guest,
                    "fromBase": "HostBase", "toBase": "ClientBase"})
    moved = poll(lambda: (guest not in ids_at(host, "HostBase")
                          and host.ok({"cmd": "incoming_transfers",
                                       "base": "ClientBase"})["soldiers"] == before + 1
                          and guest not in ids_at(client, "HostBase")) or None)
    check("transfer: the visitor's own soldier leaves HostBase for ClientBase",
          bool(moved),
          f"resp={r} host HostBase has={guest in ids_at(host, 'HostBase')} "
          f"client lastFail={stats(client)['lastFail']!r}")
    dismiss_fail(client)


def row_own_roster(host, client):
    """Move up / down at the player's own base goes through the host."""
    before = own_ids_at(client, "ClientBase", 1)
    assert len(before) >= 3, ("premise: three own soldiers at ClientBase", before)
    client.ok({"cmd": "open_soldiers", "base": "ClientBase"})
    client.ok({"cmd": "soldiers_reorder", "action": "move_up", "row": 2, "max": True})
    want = [before[2]] + before[:2] + before[3:]
    got = poll(lambda: (own_ids_at(host, "ClientBase", 1) == want
                        and own_ids_at(client, "ClientBase", 1) == want) or None)
    check("roster: move-to-top at the own base reorders both machines",
          bool(got), f"want={want} host={own_ids_at(host, 'ClientBase', 1)} "
          f"client={own_ids_at(client, 'ClientBase', 1)}")
    start = own_ids_at(client, "ClientBase", 1)
    client.ok({"cmd": "soldiers_reorder", "action": "move_down", "row": 0, "max": False})
    want = [start[1], start[0]] + start[2:]
    got = poll(lambda: (own_ids_at(host, "ClientBase", 1) == want
                        and own_ids_at(client, "ClientBase", 1) == want) or None)
    client.ok({"cmd": "soldiers_ok"})
    check("roster: move-down one place at the own base reorders both machines",
          bool(got), f"want={want} host={own_ids_at(host, 'ClientBase', 1)} "
          f"client={own_ids_at(client, 'ClientBase', 1)}")
    check("roster: both machines hold the same full roster order",
          ids_at(host, "ClientBase") == ids_at(client, "ClientBase"),
          f"host={ids_at(host, 'ClientBase')} client={ids_at(client, 'ClientBase')}")


def names_at(gc, base, owner):
    by_id = {s["id"]: s["name"] for s in soldiers_at(gc, base)}
    return [by_id[i] for i in own_ids_at(gc, base, owner)]


def row_sort(host, client):
    """Sorting the Soldiers screen at the player's own base goes through the host."""
    own = own_ids_at(client, "ClientBase", 1)
    assert len(own) >= 3, ("premise: three own soldiers at ClientBase", own)
    renamed = ["Coop Zulu", "Coop Mike", "Coop Alpha"]
    for sid, name in zip(own, renamed):
        client.ok({"cmd": "soldier_rename", "base": "ClientBase", "soldierId": sid,
                   "name": name})
    assert poll(lambda: all(n in names_at(gc, "ClientBase", 1) for gc in (host, client)
                            for n in renamed) or None), \
        ("premise: renames landed", names_at(host, "ClientBase", 1))
    before = own_ids_at(host, "ClientBase", 1)
    assert before == own_ids_at(client, "ClientBase", 1), (before, own_ids_at(client, "ClientBase", 1))
    client.ok({"cmd": "open_soldiers", "base": "ClientBase"})
    client.ok({"cmd": "soldiers_reorder", "action": "sort", "sort": 2})

    def sorted_on(gc):
        names = [n for n in names_at(gc, "ClientBase", 1) if n in renamed]
        return names == sorted(renamed)
    got = poll(lambda: (sorted_on(host) and own_ids_at(host, "ClientBase", 1)
                        == own_ids_at(client, "ClientBase", 1)) or None)
    check("sort: sorting by name at the own base reorders both machines the same way",
          bool(got) and own_ids_at(host, "ClientBase", 1) != before,
          f"before={before} host={names_at(host, 'ClientBase', 1)} "
          f"client={names_at(client, 'ClientBase', 1)}")
    client.ok({"cmd": "soldiers_reorder", "action": "sort", "sort": 0})
    got = poll(lambda: (own_ids_at(host, "ClientBase", 1) == before
                        and own_ids_at(client, "ClientBase", 1) == before) or None)
    client.ok({"cmd": "soldiers_ok"})
    check("sort: the original order comes back on both machines",
          bool(got), f"before={before} host={own_ids_at(host, 'ClientBase', 1)} "
          f"client={own_ids_at(client, 'ClientBase', 1)}")
    check("sort: both machines hold the same full roster order",
          ids_at(host, "ClientBase") == ids_at(client, "ClientBase"),
          f"host={ids_at(host, 'ClientBase')} client={ids_at(client, 'ClientBase')}")


RENAMED = ["Coop Zulu", "Coop Mike", "Coop Alpha"]


def settled_same(host, client, base, seconds=2.0):
    """Both machines' full roster order after a short settle (a host-routed
    order lands well inside it)."""
    time.sleep(seconds)
    return ids_at(host, base) == ids_at(client, base)


def craft_at(gc, base):
    return base_crafts(gc, base)[0]["id"]


def row_training_sort(host, client, screen, row):
    """A name sort on a training screen at the own base sorts what the
    screen shows and leaves both machines with the same roster order."""
    full = ids_at(host, "ClientBase")
    assert full == ids_at(client, "ClientBase"), (full, ids_at(client, "ClientBase"))
    client.ok({"cmd": "open_screen", "screen": screen, "base": "ClientBase"})
    r = client.ok({"cmd": "roster_screen", "action": "sort", "sort": 2})
    by_id = {s["id"]: s["name"] for s in soldiers_at(client, "ClientBase")}
    names_shown = [by_id.get(i) for i in r["displayed"] if by_id.get(i) in RENAMED]
    same = settled_same(host, client, "ClientBase")
    check(f"{row} {screen}: a name sort leaves both machines with the same roster order",
          same, f"host={ids_at(host, 'ClientBase')} client={ids_at(client, 'ClientBase')}")
    check(f"{row} {screen}: the screen shows its soldiers in name order",
          names_shown == sorted(RENAMED) and sorted(r["displayed"]) == sorted(full),
          f"shown={r['displayed']} names={names_shown} roster={full}")
    client.ok({"cmd": "roster_screen", "action": "sort", "sort": 0})
    same = settled_same(host, client, "ClientBase")
    client.ok({"cmd": "close_screens"})
    check(f"{row} {screen}: the original order leaves both machines the same",
          same, f"host={ids_at(host, 'ClientBase')} client={ids_at(client, 'ClientBase')}")


def flag(gc, base, sid, key):
    return (soldier(gc, base, sid) or {}).get(key)


def trained_stats(gc, base, sid):
    s = soldier(gc, base, sid) or {}
    return sum(s.get(k, 0) for k in TRAINING_STATS)


def row_host_trains(host, client, screen, row, flags):
    """The client puts its own soldiers at ClientBase into martial training
    (assign-all) and the host trains them at midnight. One midnight only: the
    clock jumps to 23:00 of the same day, so later rows see the same date."""
    own = own_ids_at(host, "ClientBase", 1)
    client.ok({"cmd": "open_screen", "screen": screen, "base": "ClientBase"})
    client.ok({"cmd": "roster_screen", "action": "assign_all"})
    on = poll(lambda: all(flag(gc, "ClientBase", s, "training") for gc in (host, client)
                          for s in own) or None, timeout=10)
    client.ok({"cmd": "close_screens"})
    before = sum(trained_stats(host, "ClientBase", s) for s in own)
    day = fixture.geo(host)["time"]["day"]
    host.ok({"cmd": "set_geo_day", "day": day, "hour": 23})
    geo.skip_ingame_time(host, client, minutes=90, speed_idx=2, real_timeout=60)
    geo.slow_clock(host, client)
    after = sum(trained_stats(host, "ClientBase", s) for s in own)
    print(f"  {row} trained stats host {before}->{after}, "
          f"client {sum(trained_stats(client, 'ClientBase', s) for s in own)}")
    check(f"{row} {screen}: assign-all puts the client's own soldiers into training and "
          f"the host trains them (their trained stats rise)",
          bool(on) and after > before,
          f"on={bool(on)} before={before} after={after} {flags('ClientBase', own[0])}")
    client.ok({"cmd": "open_screen", "screen": screen, "base": "ClientBase"})
    client.ok({"cmd": "roster_screen", "action": "deassign_all"})
    off = poll(lambda: not any(flag(gc, "ClientBase", s, "training") for gc in (host, client)
                               for s in own) or None, timeout=10)
    client.ok({"cmd": "close_screens"})
    check(f"{row} {screen}: de-assign-all takes them out of training on both machines",
          bool(off), f"{[(s, flag(host, 'ClientBase', s, 'training'), flag(client, 'ClientBase', s, 'training')) for s in own]}")


def row_training(host, client, guest, screen, key, row):
    """The training screens change a soldier's training flag through
    the host, and only for the player's own soldiers."""
    def both(base, sid, want):
        return all(flag(gc, base, sid, key) == want for gc in (host, client))

    def flags(base, sid):
        return f"host={flag(host, base, sid, key)} client={flag(client, base, sid, key)}"

    def toggle(gc, base, sid, want):
        gc.ok({"cmd": "open_screen", "screen": screen, "base": base})
        r = gc.cmd({"cmd": "roster_screen", "action": "toggle", "soldier_id": sid})
        ok = poll(lambda: both(base, sid, want) or None, timeout=10)
        gc.ok({"cmd": "close_screens"})
        return bool(ok) and r.get("ok"), r

    own = own_ids_at(host, "ClientBase", 1)[0]
    ok, r = toggle(client, "ClientBase", own, True)
    check(f"{row} {screen}: the client's own soldier is in training on both machines",
          ok, f"resp={r} {flags('ClientBase', own)}")
    ok, r = toggle(client, "ClientBase", own, False)
    check(f"{row} {screen}: the client takes its soldier out of training on both machines",
          ok, f"resp={r} {flags('ClientBase', own)}")
    if key == "training":
        row_host_trains(host, client, screen, row, flags)

    ok, r = toggle(client, "HostBase", guest, True)
    check(f"{row} {screen}: the visitor's own soldier at HostBase is in training on both machines",
          ok, f"resp={r} {flags('HostBase', guest)}")
    partners = own_ids_at(host, "HostBase", 0)
    ok, r = toggle(host, "HostBase", partners[0], True)
    check(f"{row} {screen}: the host's own soldier at HostBase is in training on both machines",
          ok, f"resp={r} {flags('HostBase', partners[0])}")
    reset_stats(host, client)
    client.ok({"cmd": "open_screen", "screen": screen, "base": "HostBase"})
    client.cmd({"cmd": "roster_screen", "action": "toggle", "soldier_id": partners[0]})
    refused, last = wait_refused(host, client, "STR_COOP_NOT_YOUR_SOLDIER")
    check(f"{row} {screen}: the visitor's click on the partner's soldier is refused; it stays "
          f"in training on both machines",
          refused and both("HostBase", partners[0], True),
          f"lastFail={last!r} {flags('HostBase', partners[0])}")

    # Assign-all / de-assign-all at HostBase change only the visitor's soldiers.
    client.ok({"cmd": "roster_screen", "action": "deassign_all"})
    off = poll(lambda: both("HostBase", guest, False) or None, timeout=10)
    client.ok({"cmd": "roster_screen", "action": "assign_all"})
    on = poll(lambda: both("HostBase", guest, True) or None, timeout=10)
    time.sleep(1.0)  # a stray change to a partner soldier would have landed by now
    partner_flags = {gc.name: [flag(gc, "HostBase", p, key) for p in partners]
                     for gc in (host, client)}
    want = {gc.name: [True] + [False] * (len(partners) - 1) for gc in (host, client)}
    check(f"{row} {screen}: de-assign-all and assign-all at HostBase change only the "
          f"visitor's soldiers",
          bool(off) and bool(on) and partner_flags == want,
          f"off={bool(off)} on={bool(on)} {flags('HostBase', guest)} partners={partner_flags}")
    client.ok({"cmd": "roster_screen", "action": "deassign_all"})
    client.ok({"cmd": "close_screens"})
    ok, r = toggle(host, "HostBase", partners[0], False)
    settled = poll(lambda: both("HostBase", guest, False) or None, timeout=10)
    check(f"{row} {screen}: both machines end with nobody in training at HostBase",
          ok and bool(settled), f"guest {flags('HostBase', guest)} "
          f"partner {flags('HostBase', partners[0])}")


def row_armor_sort(host, client):
    """The crew armor screen's name sort and original order at the own
    base go through the host."""
    before = own_ids_at(host, "ClientBase", 1)
    assert before == own_ids_at(client, "ClientBase", 1), \
        (before, own_ids_at(client, "ClientBase", 1))
    client.ok({"cmd": "open_screen", "screen": "craft_armor", "base": "ClientBase",
               "craft_id": craft_at(client, "ClientBase")})
    client.ok({"cmd": "roster_screen", "action": "sort", "sort": 2})

    def sorted_on(gc):
        return [n for n in names_at(gc, "ClientBase", 1) if n in RENAMED] == sorted(RENAMED)
    got = poll(lambda: (sorted_on(host) and ids_at(host, "ClientBase")
                        == ids_at(client, "ClientBase")) or None, timeout=10)
    check("craft armor: a name sort at the own base reorders both machines the same way",
          bool(got), f"before={before} host={names_at(host, 'ClientBase', 1)} "
          f"client={names_at(client, 'ClientBase', 1)}")
    client.ok({"cmd": "roster_screen", "action": "sort", "sort": 0})
    got = poll(lambda: (own_ids_at(host, "ClientBase", 1) == before
                        and own_ids_at(client, "ClientBase", 1) == before) or None, timeout=10)
    client.ok({"cmd": "close_screens"})
    check("craft armor: the original order comes back on both machines",
          bool(got) and ids_at(host, "ClientBase") == ids_at(client, "ClientBase"),
          f"before={before} host={own_ids_at(host, 'ClientBase', 1)} "
          f"client={own_ids_at(client, 'ClientBase', 1)}")


def row_armor_foreign_original(host, client):
    """The host sorts its soldiers at HostBase while the visitor's crew
    armor screen is open there; the visitor's original order then leaves the
    host's roster order alone."""
    own = own_ids_at(host, "HostBase", 0)
    assert len(own) >= 3, ("premise: three host soldiers at HostBase", own)
    host_names = ["Host Zulu", "Host Mike", "Host Alpha"]
    for sid, name in zip(own, host_names):
        host.ok({"cmd": "soldier_rename", "base": "HostBase", "soldierId": sid, "name": name})
    assert poll(lambda: all(n in names_at(gc, "HostBase", 0) for gc in (host, client)
                            for n in host_names) or None), \
        ("premise: host renames landed", names_at(client, "HostBase", 0))
    client.ok({"cmd": "open_screen", "screen": "craft_armor", "base": "HostBase",
               "craft_id": craft_at(client, "HostBase")})
    host.ok({"cmd": "open_soldiers", "base": "HostBase"})
    host.ok({"cmd": "soldiers_reorder", "action": "sort", "sort": 2})
    moved = poll(lambda: ([n for n in names_at(client, "HostBase", 0) if n in host_names]
                          == sorted(host_names)
                          and ids_at(host, "HostBase") == ids_at(client, "HostBase")) or None)
    host.ok({"cmd": "soldiers_ok"})
    assert moved, ("premise: the host's sort reached both machines",
                   names_at(host, "HostBase", 0), names_at(client, "HostBase", 0))
    client.ok({"cmd": "roster_screen", "action": "sort", "sort": 0})
    same = settled_same(host, client, "HostBase")
    client.ok({"cmd": "close_screens"})
    check("craft armor: the visitor's original order leaves both machines the same",
          same, f"host={names_at(host, 'HostBase', 0)} client={names_at(client, 'HostBase', 0)}")


def row_crew_original(host, client):
    """A move on the craft crew screen at the own base, then the original
    order, keeps both machines the same."""
    before = own_ids_at(host, "ClientBase", 1)
    assert len(before) >= 3, ("premise: three own soldiers at ClientBase", before)
    client.ok({"cmd": "open_screen", "screen": "craft_soldiers", "base": "ClientBase",
               "craft_id": craft_at(client, "ClientBase")})
    client.ok({"cmd": "roster_screen", "action": "move_up", "row": 2})
    want = [before[2]] + before[:2] + before[3:]
    moved = poll(lambda: (own_ids_at(host, "ClientBase", 1) == want
                          and own_ids_at(client, "ClientBase", 1) == want) or None)
    assert moved, ("premise: the crew screen's move reached both machines", want,
                   own_ids_at(host, "ClientBase", 1), own_ids_at(client, "ClientBase", 1))
    client.ok({"cmd": "roster_screen", "action": "sort", "sort": 0})
    got = poll(lambda: (own_ids_at(host, "ClientBase", 1) == before
                        and own_ids_at(client, "ClientBase", 1) == before) or None, timeout=10)
    same = settled_same(host, client, "ClientBase", 0.5)
    client.ok({"cmd": "close_screens"})
    check("craft crew: the original order brings the screen's move back on both machines",
          bool(got) and same, f"before={before} host={own_ids_at(host, 'ClientBase', 1)} "
          f"client={own_ids_at(client, 'ClientBase', 1)}")


def firing(gc, base, sid):
    return (soldier(gc, base, sid) or {}).get("firing")


def transform_lands(host, client, base, sid, want):
    return poll(lambda: (firing(host, base, sid) == want
                         and firing(client, base, sid) == want) or None)


def row_transform(host, client):
    """A soldier transformation runs on the host for both machines."""
    sid = own_ids_at(client, "ClientBase", 1)[0]
    f0 = firing(host, "ClientBase", sid)
    assert f0 == firing(client, "ClientBase", sid), (f0, firing(client, "ClientBase", sid))
    funds0 = owner_funds(host, "ClientBase")
    client.ok({"cmd": "soldier_transform", "base": "ClientBase", "soldierId": sid,
               "rule": TRANSFORM_PAID})
    check("transform: the client's transformation of its own soldier reaches the host world",
          bool(transform_lands(host, client, "ClientBase", sid, f0 + TRANSFORM_FIRING)),
          f"want={f0 + TRANSFORM_FIRING} host={firing(host, 'ClientBase', sid)} "
          f"client={firing(client, 'ClientBase', sid)}")
    paid = poll(lambda: all(owner_funds(gc, "ClientBase") == funds0 - TRANSFORM_COST
                            for gc in (host, client)) or None, timeout=10)
    check("transform: the cost leaves the client's wallet once, the same on both machines",
          bool(paid), f"funds0={funds0} host={owner_funds(host, 'ClientBase')} "
          f"client={owner_funds(client, 'ClientBase')}")

    hsid = own_ids_at(host, "HostBase", 0)[0]
    f0 = firing(host, "HostBase", hsid)
    client.ok({"cmd": "shared_reset_resync_stats"})
    host.ok({"cmd": "soldier_transform", "base": "HostBase", "soldierId": hsid,
             "rule": TRANSFORM_PAID})
    repairs = lambda: client.ok({"cmd": "shared_resync_stats"})["requests"]
    check("transform: the host's transformation reaches the client's replica as a command",
          bool(transform_lands(host, client, "HostBase", hsid, f0 + TRANSFORM_FIRING))
          and repairs() == 0,
          f"want={f0 + TRANSFORM_FIRING} host={firing(host, 'HostBase', hsid)} "
          f"client={firing(client, 'HostBase', hsid)} repairs={repairs()}")

    # The host's own soldier stationed at ClientBase (a visitor buy).
    before = set(ids_at(host, "ClientBase"))

    def incoming(gc):
        return gc.ok({"cmd": "incoming_transfers", "base": "ClientBase"})["soldiers"]
    incoming0 = {gc.name: incoming(gc) for gc in (host, client)}  # the transfer row's soldier may still travel
    reset_stats(host, client)
    host.ok({"cmd": "buy", "item": "STR_SOLDIER", "count": 1, "kind": "soldier",
             "base": "ClientBase"})
    en_route = poll(lambda: all(incoming(gc) == incoming0[gc.name] + 1
                                for gc in (host, client)) or None, timeout=30)
    assert en_route, ("premise: the host's recruit is on its way to ClientBase",
                      stats(host), stats(client), host.ok({"cmd": "get_state"})["states"])
    host.ok({"cmd": "force_transfer_arrivals", "base": "ClientBase"})
    client.wait_for("host recruit arrived on the replica",
                    lambda: (client.ok({"cmd": "incoming_transfers",
                                        "base": "ClientBase"})["soldiers"] == 0) or None,
                    timeout=30, interval=0.5)
    psid = next(s["id"] for s in soldiers_at(host, "ClientBase")
                if s["id"] not in before and s["owner"] == 0)
    client.wait_for("host recruit on the replica roster",
                    lambda: psid in ids_at(client, "ClientBase") or None,
                    timeout=30, interval=0.5)
    f0 = firing(host, "ClientBase", psid)
    reset_stats(host, client)
    client.ok({"cmd": "soldier_transform", "base": "ClientBase", "soldierId": psid,
               "rule": TRANSFORM_PAID})
    refused, last = wait_refused(host, client, "STR_COOP_NOT_YOUR_SOLDIER")
    check("transform: the partner's soldier at the client's base is refused as not its own",
          refused and firing(host, "ClientBase", psid) == f0
          and firing(client, "ClientBase", psid) == f0,
          f"lastFail={last!r} f0={f0} host={firing(host, 'ClientBase', psid)} "
          f"client={firing(client, 'ClientBase', psid)}")

    # At the partner's base (as with armor): the visitor transforms its
    # own soldier there; the visitor's wallet pays, the required item comes
    # from that base's stores, and the partner's soldier stays refused.
    guests = own_ids_at(host, "HostBase", 1)
    assert guests, ("premise: a visitor soldier at HostBase", soldiers_at(host, "HostBase"))
    gsid = guests[0]
    for gc in (host, client):
        gc.ok({"cmd": "give_items", "item": KIT_ITEM, "count": 2, "base": "HostBase"})
    kits0 = stock(host, "HostBase", KIT_ITEM)
    assert kits0 == stock(client, "HostBase", KIT_ITEM) and kits0 >= 1, \
        (kits0, stock(client, "HostBase", KIT_ITEM))
    f0 = firing(host, "HostBase", gsid)
    visitor0 = owner_funds(host, "ClientBase")
    partner0 = owner_funds(host, "HostBase")
    reset_stats(host, client)
    client.ok({"cmd": "soldier_transform", "base": "HostBase", "soldierId": gsid,
               "rule": TRANSFORM_KIT})
    landed = transform_lands(host, client, "HostBase", gsid, f0 + KIT_FIRING)
    last = stats(client)["lastFail"]
    dismiss_fail(client)
    check("transform: the visitor's transformation of its own soldier at the partner base "
          "reaches both machines",
          bool(landed), f"want={f0 + KIT_FIRING} host={firing(host, 'HostBase', gsid)} "
          f"client={firing(client, 'HostBase', gsid)} lastFail={last!r}")
    paid = poll(lambda: all(owner_funds(gc, "ClientBase") == visitor0 - KIT_COST
                            and owner_funds(gc, "HostBase") == partner0
                            for gc in (host, client)) or None, timeout=10)
    check("transform: the visitor's wallet pays at the partner base, the partner's does not",
          bool(paid), f"visitor0={visitor0} partner0={partner0} "
          f"visitor(host,client)=({owner_funds(host, 'ClientBase')},{owner_funds(client, 'ClientBase')}) "
          f"partner(host,client)=({owner_funds(host, 'HostBase')},{owner_funds(client, 'HostBase')})")
    kits = (stock(host, "HostBase", KIT_ITEM), stock(client, "HostBase", KIT_ITEM))
    check("transform: the required item comes from the partner base's stores on both machines",
          kits == (kits0 - 1, kits0 - 1), f"before={kits0} after(host,client)={kits}")

    psid = own_ids_at(host, "HostBase", 0)[0]
    f0 = firing(host, "HostBase", psid)
    reset_stats(host, client)
    client.ok({"cmd": "soldier_transform", "base": "HostBase", "soldierId": psid,
               "rule": TRANSFORM_KIT})
    refused, last = wait_refused(host, client, "STR_COOP_NOT_YOUR_SOLDIER")
    check("transform: the partner's soldier at the partner base stays refused",
          refused and firing(host, "HostBase", psid) == f0
          and firing(client, "HostBase", psid) == f0,
          f"lastFail={last!r} f0={f0} host={firing(host, 'HostBase', psid)} "
          f"client={firing(client, 'HostBase', psid)}")


def row_cydonia_key(host, client):
    """A craft request names the craft's base by its key as well as its index."""
    order = base_order(host)
    assert order.index("ClientSecond") == order.index("ClientBase") - 1, order
    crafts = base_crafts(client, "ClientBase")
    assert crafts, ("premise: a craft at ClientBase", crafts)
    craft = crafts[0]
    msg = client.ok({"cmd": "separate_craft_message", "base": "ClientBase",
                     "craftId": craft["id"]})["message"]
    client.ok({"cmd": "open_screen", "screen": "basescape", "base": "ClientBase"})
    client.ok({"cmd": "basescape_move_base_left", "base": "ClientBase"})
    client.ok({"cmd": "leave_base"})
    moved = poll(lambda: all(base_order(gc).index("ClientBase") < base_order(gc).index("ClientSecond")
                             for gc in (host, client)) or None)
    assert moved, ("premise: ClientBase moved left", base_order(host), base_order(client))
    r = host.ok({"cmd": "separate_resolve_craft", "message": msg})
    check("cydonia: a request built before a base move still names the craft on the host",
          r["found"] and r["base"] == "ClientBase" and r["craftId"] == craft["id"],
          f"msg={msg} resolved={r} order={base_order(host)}")


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
    check("order: the visitor cannot move the partner's base",
          base_order(host) == start and base_order(client) == start,
          f"start={start} host={base_order(host)} client={base_order(client)}")

    def incoming(gc, base):
        return gc.ok({"cmd": "incoming_transfers", "base": base})["items"].get(RIFLE, 0)
    before = {(gc.name, b): incoming(gc, b) for gc in (host, client)
              for b in ("ClientBase", "ClientSecond")}
    client.ok({"cmd": "open_screen", "screen": "basescape", "base": "ClientSecond"})
    # One write: the client runs both in the same frame, so the buy names
    # ClientBase by its index from before the move, which then means ClientSecond.
    resps = client.cmd_together(
        {"cmd": "basescape_move_base_left", "base": "ClientSecond"},
        {"cmd": "buy", "item": RIFLE, "count": 1, "base": "ClientBase"})
    assert all(r.get("ok") for r in resps), resps
    client.ok({"cmd": "leave_base"})
    want = [b for b in start if b != "ClientSecond"]
    want.insert(want.index("ClientBase"), "ClientSecond")
    moved = poll(lambda: (base_order(host) == want and base_order(client) == want) or None)
    check("order: moving an own base left reorders both machines the same way",
          bool(moved), f"want={want} host={base_order(host)} client={base_order(client)}")
    landed = poll(lambda: all(incoming(gc, "ClientBase") == before[(gc.name, "ClientBase")] + 1
                              for gc in (host, client)) or None)
    check("order: the buy sent right after the move lands in ClientBase on both machines",
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
    check("strip: an own base past index 8 has a mini-strip slot",
          slot >= 0, f"slots={menu['miniDisplaySlots']}")
    host.ok({"cmd": "inject_input", "kind": "key", "key": KEY_BASE_SELECT_2})
    selected = poll(lambda: (lambda b: b if b != "HostBase" else None)(
        host.ok({"cmd": "basescape_menu_state"})["base"]), timeout=10)
    check("strip: the second hotkey selects the base in the second slot",
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
    check("sell: the sale leaves the host world's stores, and the replica follows",
          bool(sold), f"stock0={stock0} host={stock(host, 'ClientBase', RIFLE)} "
          f"client={stock(client, 'ClientBase', RIFLE)}")
    host_funds, client_funds = owner_funds(host, "ClientBase"), owner_funds(client, "ClientBase")
    check("sell: the proceeds reach the seller's host wallet, the same on both machines",
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
    check("harness: craft_rearm with an id two armed craft types share is an error",
          not r.get("ok") and "ambiguous" in r.get("error", ""), f"resp={r}")
    r = host.cmd({"cmd": "craft_rearm", "weapon": "", "slot": 0, "base": "HostBase",
                  "craft_id": shared, "craft_type": "STR_FIRESTORM"})

    def firestorm_slot():
        return next(c for c in base_crafts(host, "HostBase")
                    if c["type"] == "STR_FIRESTORM")["weaponLoadout"][0]
    emptied = poll(lambda: firestorm_slot() == "" or None, timeout=10)
    check("harness: craft_rearm with craft_type rearms that craft",
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
    check("harness: craft_assign with an id two transport types share is an error",
          not r.get("ok") and "ambiguous" in r.get("error", ""), f"resp={r}")
    r = host.cmd({"cmd": "craft_assign", "base": "HostBase", "craft_id": avenger["id"],
                  "craft_type": "STR_AVENGER", "soldier_id": sid, "on": True})
    seated = poll(lambda: (soldier(host, "HostBase", sid) or {}).get("craft") == "STR_AVENGER"
                  or None, timeout=10)
    check("harness: craft_assign with craft_type seats on that craft",
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
    check("warning: a player in the red sees the warning with their own funds",
          len(client_msgs) == 1 and "7123457" in digits(client_msgs[0]),
          f"client={client_msgs}")
    check("warning: the player in the black sees no warning",
          host_msgs == [], f"host={host_msgs}")
    host_msgs, client_msgs = last_day_warnings(host, client, -3111113, 900000000)
    check("warning: the host in the red sees its own funds",
          len(host_msgs) == 1 and "3111113" in digits(host_msgs[0]), f"host={host_msgs}")
    check("warning: the client in the black is not shown the host's warning",
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
            row_sort(host, client)
            row_training_sort(host, client, "training", "martial training sort")
            row_training_sort(host, client, "psi_training", "psi training sort")
            row_training(host, client, guests[1], "training", "training", "martial training")
            row_training(host, client, guests[1], "psi_training", "psiTraining", "psi training")
            row_armor_sort(host, client)
            row_armor_foreign_original(host, client)
            row_crew_original(host, client)
            row_transform(host, client)
            row_base_order(host, client)
            row_cydonia_key(host, client)
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
