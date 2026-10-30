"""Regression test: a floor drop in the pre-battle inventory must not raise a battle desync.

Player report (2026-10-09, X-Com Files 3.9, nightly 12cfcfb54, SEPARATE campaign,
parallel turns on): "items diverged at action 1: sidestart" on turn 1 of a mission the
client's craft started, twice. Both bundles show the battle host's player re-equipping
in the pre-battle inventory (weapons and ammo dropped on the floor, others picked up).

Cause: dropping an item on the floor through the inventory UI (Inventory::mouseClick)
re-lays out the floor grid (Inventory::arrangeGround), which rewrites the in-slot cell
(slotX/slotY) of every floor item on THAT machine only. The peer applies just the one
mirrored move. The floor layout is per-machine display state (the engine does not even
save it: BattleItem::save writes cells only for INV_SLOT items), but the sync check's
items bucket hashed every item's cell, so the first sidestart compare alarmed.

Rows (parallel turns on, the player's setting):
  S2 SEPARATE, the host's craft lands; its player drops a held item on the floor.
  H1 SHARED, the host's craft lands; each player drops one of their own soldiers' items.
Each row passes when, at turn 1 with both event queues drained, neither machine latched
a desync (event_state.desyncSeen) and a full hash_now snapshot is equal on both machines.
There is no sidestart compare: the client checks the host's hashes on every event it
applies, and the floor cell of a ground item is not hashed. The drop is two real clicks
on the pre-battle equip screen (inventory_click: the hand, then a ground cell). No row
lands the client's craft: a SEPARATE client never starts a battle from its own craft.

  * PASS (exit 0) / FAIL (exit 2: a row failed, a process crashed or a precondition
    never held).

Env (optional): COOP_BSS_MODS = os.pathsep-joined mod folders for both machines (e.g. an
X-Com Files folder named x-com-files), COOP_BSS_SITE = "mission,deployment,race" for the
SEPARATE rows' site, COOP_BSS_ROWS = "S2,H1" subset.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, HERE)
import session  # noqa: E402
import geo  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

MODS = [p for p in os.environ.get("COOP_BSS_MODS", "").split(os.pathsep) if p]
SITE = tuple(os.environ.get("COOP_BSS_SITE",
                            "STR_ALIEN_TERROR,STR_TERROR_MISSION,STR_SECTOID").split(","))
PARALLEL = {"CoopTurnMode": "parallel"}  # the co-op turn-mode option (Options.cpp CoopTurnMode)


class Inconclusive(Exception):
    pass


def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def has(gc, name):
    return any(name in s for s in states(gc))


def top(gc):
    return states(gc)[-1].split("::")[-1]


def base0(gc):
    for b in gc.ok({"cmd": "geo_state"})["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise Inconclusive(gc.name + ": no own base")


# ---- the player's action -----------------------------------------------------

GROUND_XS = (18, 16, 14, 12, 10, 8, 6, 4, 2, 0)  # ground columns tried for the drop (20 columns), right first


def floor_drop(gc, coop):
    """This machine's player drops a held item of the soldier on its pre-battle equip
    screen on the floor with two real clicks (inventory_click: the hand, then a ground
    cell): the mouse path, whose floor re-layout (Inventory::arrangeGround) runs on this
    machine only (the test server refuses inventory_move ui=true in a battle: it is a
    base-screen command). The screen shows this machine's own soldiers;
    NEXT steps to the next one until a coop=`coop` soldier holds an item in a hand.
    Returns (detail, item id)."""
    held, unit = [], None
    for _ in range(8):
        view = gc.ok({"cmd": "inventory_view"})
        units = {u["id"]: u for u in gc.cmd({"cmd": "battle_state"}).get("units", [])}
        unit = units.get(view.get("unitId"))
        if unit and unit.get("faction") == 0 and unit.get("coop") == coop and unit.get("isPlayerSoldier"):
            held = [it for it in gc.ok({"cmd": "battle_items"})["items"] if it["owner"] == unit["id"]
                    and it["slot"] in ("STR_RIGHT_HAND", "STR_LEFT_HAND")]
            if held:
                break
        gc.ok({"cmd": "inventory_click", "widget": "next"})
        time.sleep(0.5)
    if not held:
        raise Inconclusive(f"{gc.name}: no coop={coop} soldier on its equip screen holds an item (last {unit})")
    it = held[0]
    gc.ok({"cmd": "inventory_click", "slot": it["slot"]})
    gc.wait_for(gc.name + " item on the cursor",
                lambda: gc.ok({"cmd": "inventory_view"}).get("selectedItem") == it["id"] or None,
                timeout=5, interval=0.25)
    for x in GROUND_XS:
        gc.ok({"cmd": "inventory_click", "slot": "STR_GROUND", "x": x, "y": 0})
        time.sleep(0.5)
        if gc.ok({"cmd": "inventory_view"}).get("selectedItem") == -1:
            break
    else:
        raise Inconclusive(f"{gc.name}: item {it['id']} stayed on the cursor at every ground column {GROUND_XS}")
    return f"{gc.name} unit {unit['id']} dropped item {it['id']} {it['type']} at ground column {x}", it["id"]


# ---- battle entry --------------------------------------------------------------

def through_inventory(host, client, drops):
    """Both machines: briefing -> pre-battle inventory; run the drops while the dropping
    machines' equip screens are up; then ready on both and settle on the tactical map.
    Returns the dropped item ids. both briefings are up at once and each
    player lands on the pre-battle equip screen for its OWN soldiers; a machine with
    nothing to equip (the SEPARATE second player with no soldier aboard) shows none.
    session.drive_both_to_tactical presses each screen's OK (the player's ready) and drains
    both machines to the battlescape."""
    host.wait_for("host in battle", lambda: host.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                  timeout=180, interval=1.0)
    droppers = [gc for gc, _ in drops]

    def screens_up():
        for gc in (host, client):
            t = top(gc)
            if t == "BriefingState":
                gc.cmd({"cmd": "close_briefing"})
            elif t == "CoopState":
                gc.cmd({"cmd": "coop_dialog_back"})
        return all(top(gc) == "InventoryState" and gc.ok({"cmd": "inventory_view"}).get("preBattle")
                   for gc in droppers) or None

    try:
        host.wait_for("the dropping machines' pre-battle equip screens", screens_up, timeout=120, interval=0.5)
    except TimeoutError as e:
        raise Inconclusive(f"no pre-battle equip screen: host={top(host)} client={top(client)}: {e}")
    dropped = []
    for gc, coop in drops:
        detail, iid = floor_drop(gc, coop)
        print("  " + detail)
        dropped.append(iid)
    time.sleep(1.0)  # the client's order reaches the host and the host's move reaches the client
    if not session.drive_both_to_tactical(host, client):
        raise Inconclusive(f"both machines never settled on the battlescape: host={top(host)} client={top(client)}")
    return dropped


def separate_landing(host, client, lander):
    """Fly the lander's first craft to a fresh site and confirm the coop landing.

    Separate is one host world: the host spawns the site next to the lander's own
    base and simulates the flight, so the craft is forced en route on both machines
    (the replica only mirrors it). The lander, the craft's owner, answers the prompt."""
    owner = "HostPlayer" if lander is host else "ClientPlayer"
    b0 = next((b for b in host.ok({"cmd": "geo_state"})["bases"]
               if b.get("ownerPlayerName") == owner), None)
    if not b0 or not b0["crafts"]:
        raise Inconclusive(lander.name + ": no own base with a craft")
    craft = b0["crafts"][0]
    mission, deployment, race = SITE
    site = host.ok({"cmd": "spawn_mission_site", "mission": mission,
                    "deployment": deployment, "lon": b0["lon"] + 0.35,
                    "lat": b0["lat"] + 0.10, "race": race, "hours": 240})["site_id"]
    client.wait_for("mission site replicated",
                    lambda: any(s["id"] == site for s in
                                client.ok({"cmd": "geo_state"})["missionSites"]) or None,
                    timeout=30, interval=0.3)
    for gc in (client, host):
        gc.ok({"cmd": "craft_force", "base": b0["name"], "craft_id": craft["id"],
               "craft_type": craft["type"], "status": "STR_OUT", "lon": b0["lon"] + 0.34,
               "lat": b0["lat"] + 0.10, "dest": f"site:{site}", "fuel": 999999,
               "lowFuel": False})

    def landing():
        if has(lander, "ConfirmLandingState"):
            return True
        for gc in (host, client):
            t = states(gc)[-1]
            if "CoopState" in t:
                gc.cmd({"cmd": "coop_dialog_back"})
            elif "GeoscapeState" not in t:
                gc.cmd({"cmd": "dismiss_popup"})
        host.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None

    lander.wait_for("landing prompt", landing, timeout=120, interval=0.5)
    lander.ok({"cmd": "coop_mission_start"})


# ---- the verdict -----------------------------------------------------------------

def first_sidestart(host, client, executor, dropped):
    """The row verdict. There is no sidestart compare (the client checks the host's
    hashes on every event it applies): at turn 1, once both event queues are
    drained, neither machine latched a desync (event_state.desyncSeen) and a full hash_now
    snapshot is equal on both machines. Preconditions: the battle runs in parallel turns
    on both machines and every dropped item lies on the floor on both. (clean, detail)."""
    def es(gc):
        return gc.cmd({"cmd": "event_state"})

    modes = {gc.name: es(gc).get("turnMode") for gc in (host, client)}
    if any(m != "parallel" for m in modes.values()):
        raise Inconclusive(f"the battle is not in parallel turns ({modes})")

    def drained():
        eh, ec = es(host), es(client)
        return (eh.get("queueDepth") == 0 and ec.get("queueDepth") == 0
                and ec.get("lastSeqApplied") == eh.get("lastSeqEmitted")) or None

    try:
        host.wait_for("both event queues drained", drained, timeout=30, interval=0.5)
    except TimeoutError as e:
        raise Inconclusive(f"the event queues never drained: {e}")
    time.sleep(2)
    for gc in (host, client):
        items = {it["id"]: it for it in gc.ok({"cmd": "battle_items"})["items"]}
        for iid in dropped:
            it = items.get(iid)
            if not it or it["owner"] != -1 or it["slot"] != "STR_GROUND":
                raise Inconclusive(f"{gc.name}: the dropped item {iid} is not on the floor: {it}")
    desync = {gc.name: bool(es(gc).get("desyncSeen")) for gc in (host, client)}
    try:
        session.assert_hash_clean(host, client, full=True, what="turn 1 after the floor drop")
        mism = []
    except AssertionError as e:
        mism = [str(e)[:600]]
    peer = client if executor is host else host
    diff = placement_diff(executor, peer)
    detail = (f"desyncSeen={desync} hashMismatch={mism} turnMode={modes} "
              f"item placements differing ({executor.name} vs {peer.name}): {diff[:6]} (n={len(diff)})")
    return (not any(desync.values()) and not mism), detail


def placement_diff(a, b):
    """Items whose placement differs between the two machines (diagnostic readout)."""
    def cell(it):
        return (it["owner"], it["slot"], it.get("slotX"), it.get("slotY"),
                it.get("tx"), it.get("ty"), it.get("tz"), it["fuse"])
    ia = {it["id"]: it for it in a.ok({"cmd": "battle_items"})["items"]}
    ib = {it["id"]: it for it in b.ok({"cmd": "battle_items"})["items"]}
    out = []
    for i in sorted(set(ia) | set(ib)):
        x, y = ia.get(i), ib.get(i)
        if x is None or y is None or cell(x) != cell(y):
            out.append((i, (x or y)["type"], x and cell(x), y and cell(y)))
    return out


# ---- rows --------------------------------------------------------------------------

def separate_row(results, row, lander_role, tag, ports, resume):
    host_dir = make_user_dir(tag + "_host", mods=MODS, options=PARALLEL)
    host = GameClient("host", ports[0], host_dir)
    client = GameClient("client", ports[1], make_user_dir(tag + "_client", mods=MODS, options=PARALLEL))
    host.spawn(); client.spawn()
    host.connect(); client.connect()
    try:
        session.new_campaign(host, client, port=ports[2])
        geo.wait_both_ready(host, client)
        if resume:
            host.ok({"cmd": "save_game_ui", "type": "quick"})
            host.wait_for("host quicksave on disk",
                          lambda: any(os.path.exists(os.path.join(host_dir, m, "_quick_.asav"))
                                      for m in ("xcom1", "x-com-files")) or None,
                          timeout=90)
            time.sleep(2.0)
            host.ok({"cmd": "save_game", "file": tag + ".sav"})
            host.shutdown(); client.shutdown()
            host = GameClient("host", ports[0], host_dir)
            host.spawn(); host.connect()
            client = GameClient("client", ports[1],
                                make_user_dir(tag + "_client2", mods=MODS, options=PARALLEL))
            client.spawn(); client.connect()
            session.resume_campaign(host, client, tag + ".sav", port=ports[2])
            time.sleep(3)
            for gc in (host, client):
                geo.drain_popups(gc)
        lander = client if lander_role == "client" else host
        separate_landing(host, client, lander)
        # SEPARATE: every soldier in the battle is the lander's (coop 0 there)
        dropped = through_inventory(host, client, [(lander, 0)])
        results[row] = first_sidestart(host, client, lander, dropped)
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass
    return alive


def shared_row(results, row, tag, ports):
    js = shared_fixture.bring_up(tag, ports, mods=MODS,
                                 host_options=dict(PARALLEL, skipNextTurnScreen=True),
                                 client_options=PARALLEL)
    host, client = js.host, js.client
    try:
        # the SHARED mixed bring-up (one host-owned and one client-owned soldier on the
        # shared craft; the host confirms the landing; it returns at the host's briefing).
        session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1}, to_tactical=False)
        # SHARED: host-owned soldiers are coop 0, client-owned coop 1
        dropped = through_inventory(host, client, [(host, 0), (client, 1)])
        results[row] = first_sidestart(host, client, host, dropped)
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    return alive


def main():
    rows = os.environ.get("COOP_BSS_ROWS", "S2,H1").split(",")
    results = {}
    note = None
    alive = True
    try:
        if "S2" in rows:
            alive = separate_row(results, "S2 SEPARATE, host's craft lands, floor drop",
                                 "host", "bss2", (48764, 48765, "47766"), resume=False) and alive
        if "H1" in rows:
            alive = shared_row(results, "H1 SHARED, host's craft lands, a floor drop by each player",
                               "bssh", (48767, 48768, 47769)) and alive
    except Inconclusive as e:
        note = "INCONCLUSIVE: " + str(e)
    except Exception as e:
        note = f"ERROR {type(e).__name__}: {e}"
        alive = False

    print("==== RESULT ====")
    for row, (ok, detail) in results.items():
        print(("PASS " if ok else "FAIL ") + row + ": " + detail)
    print("alive:", alive, "| note:", note)
    if not alive:
        sys.exit(2)
    if note:
        sys.exit(2)  # a precondition miss fails the run
    if not all(ok for ok, _ in results.values()):
        sys.exit(2)
    print("PASS: a pre-battle floor drop leaves the first sidestart sync check clean")
    sys.exit(0)


if __name__ == "__main__":
    main()
