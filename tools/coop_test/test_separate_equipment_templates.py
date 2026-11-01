"""Separate Campaign: every player keeps their own saved equipment templates.

Each player has their own soldier layout slots and craft loadout slots, as in a
two-world campaign where each world held its own. The host keeps its set in its
world's template slots; the client's set is stored in the client's player
profile on the host, so it survives every world the host streams to the client
and every reload of the host's save.

Every save runs the real save dialog body (InventorySaveState /
CraftEquipmentSaveState -> InventoryState::saveGlobalLayout /
CraftEquipmentState::saveGlobalLoadout); the probe reads each machine's own
slots and the sets stored in the player profiles.

  client-save     the client saves layout slot 3 (name, armor, items) at its
                  base inventory and craft loadout slot 2 at its Skyranger: the
                  host's own slots 3 and 2 do not change, and the host's stored
                  client set holds both, exactly as the client saved them
  host-save       the host saves its own layout slot 3 and craft slot 2: the
                  client's slots do not change
  client-load     the client loads its craft slot 2 onto its own Skyranger: the
                  craft carries the template on both machines (existing path)
  restream        a replica drift forces a world restream: both machines keep
                  their own sets exactly
  battle          the client saves layout slot 7 from the pre-battle inventory
                  of its own mission (the host, with no soldier aboard, gets no
                  equip screen); after the battle ends and the client's
                  world is replaced, the client still has it and the host
                  stored it
  reload-rejoin   the host saves the campaign to disk, both go to the main
                  menu, the host reloads it and the client rejoins: both sets
                  are intact

Red (one shared slot set): the host never stores the client's templates, and
every world the host streams replaces the client's slots with the host's.

Exit 0 = every row passed. Any other rc is a failure.
"""

import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import separate_campaign_fixture as fixture  # noqa: E402
import test_coop_client_mission_abort as abort_flow  # noqa: E402
import test_coop_peer_equip_screens as P  # noqa: E402
import test_coop_transferred_equipment as T  # noqa: E402

HB, CB = "HostBase", "ClientBase"
CLIENT_PLAYER = "ClientPlayer"
CLIENT_SOLDIER = "Zzz Client Tmpl"
HOST_SOLDIER = "Zzz Host Tmpl"
LAYOUT_SLOT = 3
CRAFT_SLOT = 2
BATTLE_SLOT = 7
SAVE = "separate_templates.sav"
RESUME_PORT = "49097"
COOP_DLG_CLIENT_RESUME_HOLD = 68
# Ground items a soldier is equipped with before a layout save, first that fits.
DRAGS = (("STR_RIFLE", "right"), ("STR_PISTOL", "left"), ("STR_SMALL_ROCKET", "backpack"),
         ("STR_GRENADE", "belt"))
SPARE = ("STR_RIFLE", "STR_PISTOL")

failures = []


def templates(gc):
    return gc.ok({"cmd": "equipment_templates"})


def local_set(gc):
    t = templates(gc)
    return {"layouts": {s["index"]: s for s in t["layouts"]},
            "crafts": {s["index"]: s for s in t["crafts"]}}


def stored_set(gc, player=CLIENT_PLAYER):
    p = templates(gc)["players"].get(player, {"layouts": [], "crafts": []})
    return {"layouts": {s["index"]: s for s in p["layouts"]},
            "crafts": {s["index"]: s for s in p["crafts"]}}


def world(gc):
    return templates(gc)["world"]


def released(gc):
    return gc.ok({"cmd": "get_coop"})["coopDialog"] != COOP_DLG_CLIENT_RESUME_HOLD


def equip(gc, unit):
    """Drag ground items onto soldier @unit in the open inventory. Returns the
    item types that moved."""
    moved = []
    for item, slot in DRAGS:
        r = gc.cmd({"cmd": "inventory_move", "name": unit, "item": item, "slot": slot})
        if r.get("moved"):
            moved.append(item)
    return moved


def save_layout(gc, index, name, unit, armor):
    r = gc.ok({"cmd": "template_save", "kind": "layout", "index": index, "name": name,
               "unit": unit, "armor": armor})
    assert r["unit"] == unit, f"{gc.name}: the layout save selected {r['unit']}, not {unit}"


def save_craft(gc, base, index, name):
    gc.ok({"cmd": "template_save", "kind": "craft", "base": base,
           "craft_id": T.craft_id(gc, base), "craft_type": T.SKYRANGER,
           "index": index, "name": name})


def craft_items(gc, base):
    cid = T.craft_id(gc, base)
    return {t: n for t, n in next(c for c in T.report(gc, base)["crafts"]
                                  if c["id"] == cid and c["type"] == T.SKYRANGER)["items"].items()
            if n > 0}


def wait_stored(host, want_layouts, want_crafts, label, timeout=30):
    """The host's stored client set holds every slot in @want_* exactly."""
    def holds():
        s = stored_set(host)
        return all(s["layouts"].get(i) == v for i, v in want_layouts.items()) and \
            all(s["crafts"].get(i) == v for i, v in want_crafts.items())
    try:
        host.wait_for(label, lambda: holds() or None, timeout=timeout, interval=0.5)
    except TimeoutError:
        raise AssertionError(f"{label}: the host's stored client set is {stored_set(host)}, "
                             f"want layouts {want_layouts} and crafts {want_crafts}")


def drain_to_geoscape(gc, timeout=90):
    """Close the post-battle popups on @gc down to the geoscape. A world load
    (LoadGameState) and a coop wait dialog close themselves and are never
    dismissed: popping the load would drop the world the host just sent. A
    finished vote menu left open for 5 s is closed with its Close button."""
    deadline = time.time() + timeout
    finished_since = None
    while time.time() < deadline:
        top = abort_flow.top(gc)
        if top == "GeoscapeState":
            return
        if top == "VoteMenu":
            if gc.cmd({"cmd": "vote_state"}).get("finished"):
                finished_since = finished_since or time.time()
                if time.time() - finished_since >= 5:
                    gc.cmd({"cmd": "vote_close"})
                    finished_since = None
        elif top not in ("BattlescapeState", "LoadGameState", "CoopState"):
            gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.4)
    raise AssertionError(f"{gc.name}: not back on the geoscape after the battle "
                         f"(top {abort_flow.top(gc)})")


def row(name, fn, *args):
    try:
        fn(*args)
        print(f"PASS {name}")
    except Exception as e:  # noqa: BLE001 - report every row, then fail
        traceback.print_exc()
        print(f"FAIL {name}: {e}")
        failures.append(name)


def setup(host, client):
    geo.slow_clock(host, client)
    for gc in (host, client):
        gc.ok({"cmd": "geo_set_speed", "idx": 0})
    # Spare stock at both bases, on both machines, so the layout drags, the
    # craft equips and the mission's rifle never run a store dry.
    for base in (HB, CB):
        for item in SPARE:
            for gc in (host, client):
                gc.ok({"cmd": "give_items", "base": base, "item": item, "count": 4})
    for base in (HB, CB):
        client.wait_for(f"spare stock at {base} on both machines",
                        lambda base=base: all(T.stored(client, base, i) == T.stored(host, base, i)
                                              for i in SPARE) or None,
                        timeout=30, interval=0.3)
    csid = next(s["id"] for s in T.report(client, CB)["soldiers"] if s["owner"] == 1)
    T.rename(client, host, client, CB, csid, CLIENT_SOLDIER)
    hsid = next(s["id"] for s in T.report(host, HB)["soldiers"] if s["owner"] == 0)
    T.rename(host, host, client, HB, hsid, HOST_SOLDIER)


def row_client_save(host, client, state):
    host_before = local_set(host)
    P.open_base_inventory(client, CB)
    moved = equip(client, CLIENT_SOLDIER)
    save_layout(client, LAYOUT_SLOT, "Client layout", CLIENT_SOLDIER, True)
    P.close_base_inventory(client)
    layout = local_set(client)["layouts"].get(LAYOUT_SLOT)
    assert layout and layout["name"] == "Client layout" and layout["armor"] and layout["entries"], (
        f"precondition: the client's saved layout slot {LAYOUT_SLOT} is {layout} "
        f"(items dragged: {moved})")

    cid = T.craft_id(host, CB)
    before = craft_items(host, CB).get("STR_RIFLE", 0)
    client.ok({"cmd": "craft_equip", "base": CB, "craft_id": cid, "item": "STR_RIFLE", "count": 1})
    host.wait_for("rifle on the client's Skyranger",
                  lambda: craft_items(host, CB).get("STR_RIFLE", 0) > before or None,
                  timeout=30, interval=0.3)
    client.wait_for("rifle on the client's Skyranger (client)",
                    lambda: craft_items(client, CB) == craft_items(host, CB) or None,
                    timeout=30, interval=0.3)
    save_craft(client, CB, CRAFT_SLOT, "Client loadout")
    craft = local_set(client)["crafts"].get(CRAFT_SLOT)
    assert craft and craft["name"] == "Client loadout" and craft["items"], (
        f"precondition: the client's saved craft slot {CRAFT_SLOT} is {craft}")
    state["client"] = local_set(client)

    wait_stored(host, {LAYOUT_SLOT: layout}, {CRAFT_SLOT: craft},
                "the client's layout and loadout stored on the host")
    host_after = local_set(host)
    assert host_after == host_before, (
        f"the client's save changed the host's own slots:\n  before={host_before}\n"
        f"  after ={host_after}")


def row_host_save(host, client, state):
    client_before = local_set(client)
    stored_before = stored_set(host)
    P.open_base_inventory(host, HB)
    equip(host, HOST_SOLDIER)
    save_layout(host, LAYOUT_SLOT, "Host layout", HOST_SOLDIER, False)
    P.close_base_inventory(host)
    save_craft(host, HB, CRAFT_SLOT, "Host loadout")
    mine = local_set(host)
    state["host"] = mine
    assert mine["layouts"].get(LAYOUT_SLOT, {}).get("name") == "Host layout", mine
    assert mine["crafts"].get(CRAFT_SLOT, {}).get("name") == "Host loadout", mine
    assert stored_set(host, "HostPlayer") == {"layouts": {}, "crafts": {}}, (
        f"the host's own save went into its profile: {stored_set(host, 'HostPlayer')}")
    # A later command from the host reaches the client after anything the
    # saves might have sent.
    T.rename(host, host, client, HB, next(s["id"] for s in T.report(host, HB)["soldiers"]
                                          if s["name"] == HOST_SOLDIER), HOST_SOLDIER + " B")
    client_after = local_set(client)
    assert client_after == client_before, (
        f"the host's save changed the client's slots:\n  before={client_before}\n"
        f"  after ={client_after}")
    assert stored_set(host) == stored_before, (
        f"the host's save changed its stored client set:\n  before={stored_before}\n"
        f"  after ={stored_set(host)}")


def row_client_load(host, client, state):
    template = state["client"]["crafts"][CRAFT_SLOT]["items"]
    cid = T.craft_id(host, CB)
    # One more of an item the stores hold, so the load has something to undo.
    extra = next(t for t in SPARE if T.stored(host, CB, t) >= 1)
    client.ok({"cmd": "craft_equip", "base": CB, "craft_id": cid, "item": extra, "count": 1})
    host.wait_for("extra pistol on the client's Skyranger",
                  lambda: craft_items(host, CB).get(extra, 0) == template.get(extra, 0) + 1 or None,
                  timeout=30, interval=0.3)
    r = client.ok({"cmd": "craft_loadout", "op": "load", "index": CRAFT_SLOT, "base": CB,
                   "craft_id": cid, "craft_type": T.SKYRANGER})
    listed = set(r["listed"])
    assert set(template) <= listed, f"precondition: {template} not all listed in {sorted(listed)}"
    for gc in (host, client):
        gc.wait_for(f"{gc.name}: the template's items on the Skyranger",
                    lambda gc=gc: all(craft_items(gc, CB).get(t, 0) == template.get(t, 0)
                                      for t in listed) or None,
                    timeout=30, interval=0.3)
    T.settle(client)


def row_restream(host, client, state):
    stored_before = stored_set(host)
    world_before = world(client)
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_resync_stats"})
    client.ok({"cmd": "give_items", "item": "STR_MEDI_KIT", "count": 1, "base": CB})
    client.wait_for("replica asked for a resync",
                    lambda: client.ok({"cmd": "shared_resync_stats"})["requests"] >= 1 or None,
                    timeout=90, interval=0.5)
    client.wait_for("restreamed world adopted",
                    lambda: (world(client) != world_before
                             and T.stored(client, CB, "STR_MEDI_KIT")
                             == T.stored(host, CB, "STR_MEDI_KIT")) or None,
                    timeout=90, interval=0.5)
    client.wait_for("client released", lambda: released(client) or None, timeout=60, interval=0.5)
    assert host.ok({"cmd": "shared_resync_stats"})["requests"] >= 1, "the host served no restream"
    client_after, host_after = local_set(client), local_set(host)
    assert client_after == state["client"], (
        f"after the restream the client's slots are\n  {client_after}\n  want {state['client']}")
    assert host_after == state["host"], (
        f"after the restream the host's slots are\n  {host_after}\n  want {state['host']}")
    assert stored_set(host) == stored_before, (
        f"the restream changed the host's stored client set: {stored_set(host)}")


def row_battle(host, client, state):
    fixture.fly_to_new_site(host, client, client)
    client.ok({"cmd": "confirm_landing"})
    for gc in (host, client):
        gc.wait_for(gc.name + " in battle",
                    lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc in (host, client):
        gc.wait_for(gc.name + " briefing",
                    lambda gc=gc: abort_flow.has(gc, "BriefingState") or None,
                    timeout=120, interval=0.5)
        gc.ok({"cmd": "close_briefing"})
    # Only the client has soldiers on its craft: it gets the pre-battle equip
    # screen, and the host, with nothing to equip, skips it and waits on the
    # Turn 1 screen until the client presses OK.
    client.wait_for("client inventory",
                    lambda: abort_flow.has(client, "InventoryState") or None,
                    timeout=120, interval=0.5)
    host.wait_for("host on the Turn 1 screen with no equip screen",
                  lambda: (abort_flow.top(host) == "NextTurnState"
                           and not abort_flow.has(host, "InventoryState")) or None,
                  timeout=60, interval=0.5)

    units = client.ok({"cmd": "inventory_ground"})["soldiers"]
    assert units, "precondition: no soldier in the client's pre-battle inventory"
    unit = units[0]["name"]
    equip(client, unit)
    save_layout(client, BATTLE_SLOT, "Battle layout", unit, True)
    battle_world = world(client)
    saved = local_set(client)["layouts"].get(BATTLE_SLOT)
    assert saved and saved["name"] == "Battle layout" and saved["armor"], (
        f"precondition: the client's battle layout slot {BATTLE_SLOT} is {saved}")
    expected = {"layouts": dict(state["client"]["layouts"]),
                "crafts": dict(state["client"]["crafts"])}
    expected["layouts"][BATTLE_SLOT] = saved
    state["client"] = expected

    client.ok({"cmd": "battle_inventory", "action": "ok"})
    for _ in range(20):
        if all(abort_flow.top(gc) == "BattlescapeState" for gc in (host, client)):
            break
        for gc in (host, client):
            if abort_flow.top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(1.0)
    deadline = time.time() + 90
    while time.time() < deadline:
        turns = [gc.cmd({"cmd": "battle_state"}).get("coopTurn") for gc in (host, client)]
        if all(turns) and (2 in turns or 4 in turns):
            break
        time.sleep(0.5)
    time.sleep(2)
    abort_flow.vote_abort(host, client, host)
    for gc in (host, client):
        drain_to_geoscape(gc)
    for gc in (host, client):
        gc.ok({"cmd": "geo_set_speed", "idx": 0})
    client.wait_for("the client's battle world replaced",
                    lambda: (world(client) != battle_world and released(client)) or None,
                    timeout=120, interval=0.5)
    fixture.assert_same_world(host, client, "after the battle")

    client_after = local_set(client)
    assert client_after == expected, (
        f"after the battle the client's slots are\n  {client_after}\n  want {expected}")
    wait_stored(host, {BATTLE_SLOT: saved}, {}, "the battle layout stored on the host")
    assert local_set(host) == state["host"], (
        f"after the battle the host's slots are\n  {local_set(host)}\n  want {state['host']}")


def row_reload_rejoin(host, client, state):
    host.ok({"cmd": "save_game", "file": SAVE})
    for gc in (client, host):
        gc.ok({"cmd": "disconnect_to_menu"})
        gc.wait_for(gc.name + " main menu",
                    lambda gc=gc: (session.states(gc)
                                   and "MainMenuState" in session.states(gc)[-1]) or None,
                    timeout=60, interval=0.25)
    assert not client.ok({"cmd": "world_state"})["has_save"], "the client kept a world at the main menu"
    session.resume_campaign(host, client, SAVE, port=RESUME_PORT)
    client.wait_for("client released after the rejoin", lambda: released(client) or None,
                    timeout=60, interval=0.5)
    client_after, host_after = local_set(client), local_set(host)
    assert client_after == state["client"], (
        f"after the reload and rejoin the client's slots are\n  {client_after}\n"
        f"  want {state['client']}")
    assert host_after == state["host"], (
        f"after the reload the host's slots are\n  {host_after}\n  want {state['host']}")
    assert stored_set(host) == state["client"], (
        f"after the reload the host's stored client set is\n  {stored_set(host)}\n"
        f"  want {state['client']}")


def main():
    js = fixture.bring_up("sep_templates", (49796, 49797, 49096))
    host, client = js.host, js.client
    state = {}
    try:
        setup(host, client)
        row("client-save", row_client_save, host, client, state)
        row("host-save", row_host_save, host, client, state)
        if "client" in state:
            row("client-load", row_client_load, host, client, state)
        row("restream", row_restream, host, client, state)
        if "host" in state and "client" in state:
            row("battle", row_battle, host, client, state)
        row("reload-rejoin", row_reload_rejoin, host, client, state)
    finally:
        js.shutdown()
    if failures:
        print("FAIL rows: " + ", ".join(failures))
        sys.exit(1)
    print("TEST PASSED")


if __name__ == "__main__":
    main()
