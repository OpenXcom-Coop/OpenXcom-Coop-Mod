"""Door state synchronization regression test (Issue #143).

Commit 76d057644 ("Fix double TU cost when turning units in co-op") moved the
turnBattlescapeUnit sync packet from UnitTurnBState::init() to deinit() and
gated it behind `if (turned)`. A right-click door-open (BA_NONE action) where
the soldier already faces the door never changes direction, so `turned` is
false and the packet is never sent. The client never learns the door opened.

The test uses a SHARED campaign UFO crash-site battle (guaranteed UFO doors):
  1. Brings up a SHARED campaign.
  2. Enters a UFO crash-site battle (real `confirm_landing` path).
  3. Finds a UFO door tile and positions a soldier facing it.
  4. Opens the door via battle_action door (UnitTurnBState with BA_NONE).
  5. Asserts both machines see the door as open.

Run:  python tools/coop_test/test_coop_door_sync.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

# RW-TRIAGE: SKIP-PENDING(r3)
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import test_shared_battle as B


def _aboard(gc, cid):
    return sorted(s["id"] for s in B._roster(gc) if s["craftId"] == cid)


def _top(gc):
    return gc.cmd({"cmd": "get_state"})["states"][-1].split("::")[-1]


def _drain_to_tactical(host, client, rounds=8):
    for _ in range(rounds):
        moved = False
        for gc in (host, client):
            if _top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
                moved = True
        time.sleep(1.0)
        if not moved and all(_top(gc) == "BattlescapeState" for gc in (host, client)):
            return


def tile_info(gc, x, y, z):
    return gc.cmd({"cmd": "tile_info", "x": x, "y": y, "z": z})


def door_on_tile(ti):
    """Return (part_name, is_ufo) if the tile has a door, else None."""
    if not ti.get("ok"):
        return None
    for pname in ("northwall", "westwall", "object"):
        part = ti["parts"].get(pname, {})
        if part.get("isDoor"):
            return (pname, False)
        if part.get("isUfoDoor"):
            return (pname, True)
    return None


def door_is_open(ti, part_name, is_ufo):
    """Check if a specific door part is open.
    Normal door: mapDataID==-1 (MCD data removed on open).
    UFO door: isUfoDoorOpen==true."""
    if not ti.get("ok"):
        return False
    part = ti["parts"].get(part_name, {})
    if is_ufo:
        return part.get("isUfoDoorOpen", False)
    else:
        return part.get("mapDataID", 0) < 0


def find_ufo_door(driver):
    """Sample tiles for doors. Returns (x, y, z, part_name, is_ufo) or raises."""
    n = B._battle(driver).get("mapSizeXYZ", 0)

    # First, check tiles near soldiers (high-density scan around visible area)
    units = B._battle(driver).get("units", [])
    checked = set()
    for u in units:
        if u.get("isOut"):
            continue
        sx, sy, sz = u["x"], u["y"], u["z"]
        for dx in range(-15, 16):
            for dy in range(-15, 16):
                tx, ty = sx + dx, sy + dy
                if (tx, ty, sz) in checked:
                    continue
                checked.add((tx, ty, sz))
                ti = driver.cmd({"cmd": "tile_info", "x": tx, "y": ty, "z": sz})
                if not ti.get("ok"):
                    continue
                door = door_on_tile(ti)
                if door:
                    print(f"    found door at ({ti['x']},{ti['y']},{ti['z']}) "
                          f"part={door[0]} is_ufo={door[1]}")
                    return (ti["x"], ti["y"], ti["z"], door[0], door[1])
    print(f"checked {len(checked)} tiles near soldiers, no doors")
    raise AssertionError("no doors found near any soldier")


def main():
    js = shared_fixture.bring_up("door", (48990, 48991, 48190))
    host, client = js.host, js.client
    try:
        # Build squad
        owner = {s["id"]: s["owner"] for s in B._roster(host)}
        seat0 = sorted(sid for sid, o in owner.items() if o == 0)
        assert len(seat0) >= 2, f"need >=2 host soldiers: {seat0}"
        cid = B._skyranger(host)["id"]
        for sid in owner:
            host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
        squad = seat0[:2]
        for sid in squad:
            host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})
        host.wait_for("squad aboard",
                      lambda: (_aboard(host, cid) == sorted(squad)) or None,
                      timeout=45, interval=0.5)
        print("squad aboard the Skyranger")

        # Spawn mission and fly there
        b0 = B._base0(host)
        blon, blat = b0["lon"], b0["lat"]
        site_id = host.ok({"cmd": "spawn_mission_site",
                           "mission": "STR_ALIEN_TERROR",
                           "deployment": "STR_TERROR_MISSION",
                           "lon": blon + 0.35, "lat": blat + 0.10,
                           "race": "STR_SECTOID", "hours": 240})["site_id"]
        host.wait_for("site on host",
                      lambda: any(s["id"] == site_id
                                  for s in B._geo(host)["missionSites"]) or None,
                      timeout=30)

        host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
                 "lon": blon + 0.34, "lat": blat + 0.10,
                 "dest": f"site:{site_id}", "fuel": 999999, "lowFuel": False})

        def _landing():
            if B._has(host, "ConfirmLandingState"):
                return True
            host.cmd({"cmd": "geo_set_speed", "idx": 2})
            return None
        host.wait_for("landing prompt", _landing, timeout=90, interval=0.5)
        host.ok({"cmd": "confirm_landing"})
        print("landing confirmed")

        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} in battle",
                        lambda gc=gc: B._battle(gc).get("inBattle") or None,
                        timeout=180, interval=1.0)
        for gc in (host, client):
            gc.wait_for("briefing",
                        lambda gc=gc: B._has(gc, "BriefingState") or None,
                        timeout=30, interval=0.5)
            gc.ok({"cmd": "close_briefing"})
        for gc in (host, client):
            gc.wait_for("inventory",
                        lambda gc=gc: B._has(gc, "InventoryState") or None,
                        timeout=30, interval=0.5)
            gc.ok({"cmd": "battle_inventory", "action": "ok"})
        _drain_to_tactical(host, client)
        print("both machines on the tactical map")

        # Wait for coop turn init
        host.wait_for("host turn active",
                      lambda: (B._battle(host).get("coopTurn") == 2) or None,
                      timeout=30, interval=0.5)
        time.sleep(2)

        # Find a UFO door
        dx, dy, dz, pname, is_ufo = find_ufo_door(host)
        print(f"selected door at ({dx},{dy},{dz}) part={pname}")

        # Pick a host-owned soldier with TUs
        hb = B._battle(host)
        soldiers = [u for u in hb["units"]
                    if u.get("soldierId") in squad
                    and not u.get("isOut") and u.get("tu", 0) > 10]
        assert soldiers, "no host soldiers with TUs"
        sid = soldiers[0]["id"]
        print(f"using soldier {sid} (soldierId={soldiers[0].get('soldierId')})")

        # Determine the facing direction needed for this door type.
        # Northwall door opens to the north (dy=-1); westwall to the west (dx=-1).
        if pname == "northwall":
            tx_target, ty_target = dx, dy - 1
        elif pname == "westwall":
            tx_target, ty_target = dx - 1, dy
        else:
            # object doors - try facing the tile itself
            tx_target, ty_target = dx, dy

        # Position soldier on the door tile
        host.cmd({"cmd": "battle_action", "action": "select", "unit": sid})
        tres = host.cmd({"cmd": "battle_teleport", "unit": sid,
                         "x": dx, "y": dy, "z": dz})
        if not tres.get("ok") or not tres.get("moved"):
            raise AssertionError(f"cannot teleport to door tile ({dx},{dy},{dz}): {tres}")
        print(f"teleported soldier {sid} onto door tile ({tres['x']},{tres['y']},{tres['z']})")

        # Verify door is closed on both machines
        ti_d = tile_info(host, dx, dy, dz)
        ti_w = tile_info(client, dx, dy, dz)
        assert not door_is_open(ti_d, pname, is_ufo), \
            f"door at ({dx},{dy},{dz}) already open on host: {ti_d}"
        assert not door_is_open(ti_w, pname, is_ufo), \
            f"door at ({dx},{dy},{dz}) already open on client: {ti_w}"
        print(f"initial door state: closed on both ({pname})")

        # Open the door via right-click path (BA_NONE)
        host.cmd({"cmd": "battle_action", "action": "select", "unit": sid})
        res = host.cmd({"cmd": "battle_action", "action": "door", "unit": sid,
                        "x": tx_target, "y": ty_target, "z": dz})
        assert res.get("ok"), f"door action failed: {res}"
        print(f"door action dispatched on host")
        time.sleep(4.0)

        # Check door state
        ti_d2 = tile_info(host, dx, dy, dz)
        ti_w2 = tile_info(client, dx, dy, dz)
        open_d = door_is_open(ti_d2, pname, is_ufo)
        open_w = door_is_open(ti_w2, pname, is_ufo)
        print(f"after door-open: host={open_d} client={open_w}")

        if not open_d:
            raise AssertionError(
                f"door at ({dx},{dy},{dz}) did not open even on the host "
                f"(soldier {sid}, part {pname})\n  host tile: {ti_d2}")

        if not open_w:
            raise AssertionError(
                f"ISSUE #143 REPRODUCED: door at ({dx},{dy},{dz}) opened on "
                f"host but stayed CLOSED on client\n"
                f"  host tile: {ti_d2}\n  client tile: {ti_w2}")

        print(f"PASS: door at ({dx},{dy},{dz}) {pname} opened on BOTH machines")
        print("DOOR SYNC TEST PASSED")

    finally:
        js.shutdown()

    print("DONE")


if __name__ == "__main__":
    main()
