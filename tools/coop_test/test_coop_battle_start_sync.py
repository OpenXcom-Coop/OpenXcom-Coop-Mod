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
  S1 SEPARATE, resumed save, the client's craft lands; its player drops a held item on
     the floor before the battle starts. (A resumed save, as in the player's second
     report: on a fresh campaign a client-started battle runs without parallel turns,
     so no sync check runs.)
  S2 SEPARATE, the host's craft lands; its player drops a held item on the floor.
  H1 SHARED, the host's craft lands; each player drops one of their own soldiers' items.
Each row passes when the battle host's first sidestart compare ran, no bucket mismatched,
and neither machine latched a desync.

  * PASS (exit 0) / FAIL (exit 2: a row failed or a process crashed) /
    FAIL (exit 3: a precondition never held).

Env (optional): COOP_BSS_MODS = os.pathsep-joined mod folders for both machines (e.g. an
X-Com Files folder named x-com-files), COOP_BSS_SITE = "mission,deployment,race" for the
SEPARATE rows' site, COOP_BSS_ROWS = "S1,S2,H1" subset.
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
import test_shared_parallel_campaign as SPC  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

MODS = [p for p in os.environ.get("COOP_BSS_MODS", "").split(os.pathsep) if p]
SITE = tuple(os.environ.get("COOP_BSS_SITE",
                            "STR_ALIEN_TERROR,STR_TERROR_MISSION,STR_SECTOID").split(","))
PARALLEL = {"EnableCoopParallelTurns": True}


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

def floor_drop(gc, coop):
    """This machine's player drops a held item of one of its soldiers (unit coop flag
    `coop`) on the floor: the real Inventory::moveItem, then the floor re-layout the
    mouse path does (inventory_move ui=true)."""
    bs = gc.cmd({"cmd": "battle_state"})
    units = [u for u in bs.get("units", []) if u.get("faction") == 0 and u.get("coop") == coop
             and u.get("isPlayerSoldier")]
    items = gc.ok({"cmd": "battle_items"})["items"]
    for unit in units:
        held = [it for it in items if it["owner"] == unit["id"]
                and it["slot"] in ("STR_RIGHT_HAND", "STR_LEFT_HAND")]
        if not held:
            continue
        it = held[0]
        r = gc.cmd({"cmd": "inventory_move", "name": unit["name"], "item": it["type"],
                    "slot": "ground", "from": "unit", "ui": True})
        if not r.get("ok") or r.get("landedSlot") != "STR_GROUND":
            raise Inconclusive(f"{gc.name}: the floor drop did not land: {r} (unit {unit['id']})")
        after = {x["id"]: x for x in gc.ok({"cmd": "battle_items"})["items"]}
        if after[it["id"]]["owner"] != -1:
            raise Inconclusive(f"{gc.name}: item {it['id']} still has an owner after the drop")
        return f"{gc.name} unit {unit['id']} dropped item {it['id']} {it['type']}"
    raise Inconclusive(f"{gc.name}: no coop={coop} soldier holds an item: {units}")


# ---- battle entry --------------------------------------------------------------

def through_inventory(host, client, drops):
    """Both machines: briefing -> pre-battle inventory; run the drops while BOTH are in
    the inventory; then OK on both and settle on the tactical map."""
    for gc in (host, client):
        gc.wait_for(gc.name + " in battle",
                    lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc in (host, client):
        gc.wait_for(gc.name + " briefing", lambda gc=gc: has(gc, "BriefingState") or None,
                    timeout=120, interval=0.5)
        gc.ok({"cmd": "close_briefing"})
    for gc in (host, client):
        gc.wait_for(gc.name + " inventory", lambda gc=gc: has(gc, "InventoryState") or None,
                    timeout=120, interval=0.5)
    for gc, coop in drops:
        print("  " + floor_drop(gc, coop))
    time.sleep(1.0)  # the mirrored moves reach the peer
    for gc in (host, client):
        gc.ok({"cmd": "battle_inventory", "action": "ok"})
    for _ in range(20):
        if all(top(gc) == "BattlescapeState" for gc in (host, client)):
            break
        for gc in (host, client):
            if top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(1.0)


def separate_landing(host, client, lander):
    """Fly the lander's first craft to a fresh site and confirm the coop landing."""
    b0 = base0(lander)
    if not b0["crafts"]:
        raise Inconclusive(lander.name + ": no craft")
    cid = b0["crafts"][0]["id"]
    mission, deployment, race = SITE
    site = lander.ok({"cmd": "spawn_mission_site", "mission": mission,
                      "deployment": deployment, "lon": b0["lon"] + 0.35,
                      "lat": b0["lat"] + 0.10, "race": race, "hours": 240})["site_id"]
    lander.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34,
               "lat": b0["lat"] + 0.10, "dest": f"site:{site}", "fuel": 999999, "lowFuel": False})

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

def first_sidestart(host, client, executor):
    """Wait for the battle host's first boundary compare; (clean, detail)."""
    flags = {gc.name: gc.cmd({"cmd": "battle_state"}).get("parallelEnabled") for gc in (host, client)}
    if not all(flags.values()):
        raise Inconclusive(f"parallel turns are off in the battle ({flags}): no sync check runs")

    def compared():
        sc = session.sync_check(executor)
        return sc if sc["lastComparedBoundarySeq"] >= 1 else None

    try:
        executor.wait_for("first boundary compared", compared, timeout=90, interval=1.0)
    except Exception as e:
        raise Inconclusive(f"the first boundary was never compared: {e}")
    time.sleep(2)
    sc = session.sync_check(executor)
    desync = {gc.name: bool(gc.cmd({"cmd": "battle_state"}).get("desyncSeen")) for gc in (host, client)}
    mism = sc.get("mismatches", [])
    peer = client if executor is host else host
    diff = placement_diff(executor, peer)
    detail = (f"desyncSeen={desync} mismatches={mism[:4]} compares={sc['compares']} "
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
        through_inventory(host, client, [(lander, 0)])
        results[row] = first_sidestart(host, client, lander)
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
        SPC.assign_and_fly(host, client)
        host.ok({"cmd": "confirm_landing"})
        # SHARED: host-owned soldiers are coop 0, client-owned coop 1
        through_inventory(host, client, [(host, 0), (client, 1)])
        results[row] = first_sidestart(host, client, host)
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    return alive


def main():
    rows = os.environ.get("COOP_BSS_ROWS", "S1,S2,H1").split(",")
    results = {}
    note = None
    alive = True
    try:
        if "S1" in rows:
            alive = separate_row(results, "S1 SEPARATE, resumed save, client's craft lands, floor drop",
                                 "client", "bss1", (48761, 48762, "47763"), resume=True) and alive
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
        sys.exit(3)
    if not all(ok for ok, _ in results.values()):
        sys.exit(2)
    print("PASS: a pre-battle floor drop leaves the first sidestart sync check clean")
    sys.exit(0)


if __name__ == "__main__":
    main()
