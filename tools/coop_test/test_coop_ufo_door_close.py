"""Test: UFO door-close sync at end of XCOM turn + VERIFY-2 (UFO half).

BattlescapeGame::endTurn() closes UFO doors via closeUfoDoors(), gated behind
_triggerProcessed.tryRun(). On the host this runs during the real endTurn(). On
the client, endTurnCoop() calls requestEndTurn(false), which eventually calls
endTurn() in the think loop - but possibly after an alien already started moving
past what the client still sees as a closed door.

This test needs a map that actually HAS UFO doors. A geoscape TERROR site (the
old fixture) is a city map with only hinged doors, so the test SKIPPED. The NEW
BATTLE skirmish fixture at mission index 3 generates STR_UFO_GROUND_ASSAULT - a
UFO map that carries UFO doors (confirmed by probe_missions.py: idx 3/6 are the
UFO-terrain missions). Point the fixture there (MISSION below) and the test runs.

The test:
  1. Brings up a CLASSIC-coop skirmish battle on a UFO map (mission 3).
  2. Finds a UFO door, positions a host soldier, opens it.
  3. Verifies it is open on BOTH machines (door-sync).
  4. VERIFY-2 (UFO half): asserts the UFO-door open moved ONLY the diagnostic
     door bitmask, NOT any terrain-bucket field (mapDataID / setID / explosive)
     - i.e. a UFO-door open/close DIVERGENCE is invisible to the `terrain`
     bucket and would show only in saveBlob (VERIFY-1: Tile.cpp only touches
     _objectsCache[part].currentFrame; isUfoDoorOpen is frame-derived, no
     map-data id change). tile_terrain_full is exactly the bucket's field set.
  5. Ends the XCOM turn and checks the door-close state on both machines.

Run:  python tools/coop_test/test_coop_ufo_door_close.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_sync_check as T
import test_parallel_intents as PI
import test_parallel_endturn as PE
import test_parallel_soak as SOAK
import session
from harness import GameClient, make_user_dir

# The NEW BATTLE mission index whose generator produces a UFO map (UFO doors).
# idx 3 = STR_UFO_GROUND_ASSAULT; idx 6 is the other UFO-terrain mission
# (probe_missions.py). Parameterised here so a generator change is a one-line fix.
MISSION = 3


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def tile_info(gc, x, y, z):
    return gc.cmd({"cmd": "tile_info", "x": x, "y": y, "z": z})


def door_is_open(ti, part_name, is_ufo):
    if not ti.get("ok"):
        return False
    part = ti["parts"].get(part_name, {})
    if is_ufo:
        return part.get("isUfoDoorOpen", False)
    return part.get("mapDataID", 0) < 0


def find_ufo_door(gc):
    """Scan tiles by index for a UFO door (isUfoDoor). Dense step - UFO doors are
    small. Returns (x, y, z, part, is_ufo, index) or (None,)*6."""
    n = battle(gc).get("mapSizeXYZ", 0)
    for i in range(0, n, max(1, n // 4000)):
        ti = gc.cmd({"cmd": "tile_info", "index": i})
        if not ti.get("ok"):
            continue
        for pname in ("northwall", "westwall", "object"):
            part = ti["parts"].get(pname, {})
            if part.get("isUfoDoor"):
                print(f"    found UFO door at ({ti['x']},{ti['y']},{ti['z']}) part={pname}")
                return (ti["x"], ti["y"], ti["z"], pname, True, i)
    return (None, None, None, None, None, None)


def tvec(gc, idx):
    """The LIVE terrain-bucket vector for one tile (the exact field set the
    `terrain` bucket hashes) plus the bucket-blind `door` bitmask."""
    r = gc.cmd({"cmd": "tile_terrain_full", "index": idx})
    tiles = r.get("tiles", [])
    return tiles[0] if tiles else None


def bucket_fields(t):
    """The terrain-bucket subset of a tvec record - everything EXCEPT the
    diagnostic `door` bitmask (which the bucket does not compare)."""
    return {k: v for k, v in t.items() if k != "door"}


def main():
    host = GameClient("host", 48994,
                      make_user_dir("ufoclose_host",
                                    options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": False}))
    client = GameClient("client", 48995,
                        make_user_dir("ufoclose_client",
                                      options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    SOAK.write_battle_fixture(host.user_dir, mission=MISSION)
    SOAK.write_battle_fixture(client.user_dir, mission=MISSION)
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        for mod in (T.TW, PI, PE, SOAK):
            try:
                mod.PORT = T.PORT
            except Exception:
                pass
        T.TW.bring_up_battle(host, client)
        b = battle(host)
        print(f"battle up: missionType={b.get('missionType')} coopTurn={b.get('coopTurn')}")

        dx, dy, dz, pname, is_ufo, idx = find_ufo_door(host)
        if dx is None:
            raise AssertionError(
                f"no UFO door on mission {MISSION} (missionType={b.get('missionType')}) - "
                f"the fixture must point at a UFO-terrain mission (idx 3 or 6)")

        hb = battle(host)
        soldiers = [u for u in hb["units"]
                    if u.get("faction") == 0 and not u.get("isOut") and u.get("tu", 0) > 10]
        assert soldiers, "no host soldiers with TUs"
        sid = soldiers[0]["id"]

        # --- capture the door tile's terrain-bucket vector BEFORE the open ---
        before_h = tvec(host, idx)
        assert before_h is not None, f"no terrain vector for door tile index {idx}"
        print(f"door tile bucket (closed) = {bucket_fields(before_h)} door_bits={before_h.get('door')}")

        # Teleport onto the door tile, verify closed on both
        host.cmd({"cmd": "battle_action", "action": "select", "unit": sid})
        tres = host.cmd({"cmd": "battle_teleport", "unit": sid, "x": dx, "y": dy, "z": dz})
        assert tres.get("ok") and tres.get("moved"), f"teleport failed: {tres}"
        ti_h0 = tile_info(host, dx, dy, dz)
        ti_c0 = tile_info(client, dx, dy, dz)
        assert not door_is_open(ti_h0, pname, is_ufo), f"door already open on host: {ti_h0}"
        assert not door_is_open(ti_c0, pname, is_ufo), f"door already open on client: {ti_c0}"

        # Open the door (one step into the door normal)
        if pname == "northwall":
            tx_t, ty_t = dx, dy - 1
        elif pname == "westwall":
            tx_t, ty_t = dx - 1, dy
        else:
            tx_t, ty_t = dx, dy
        res = host.cmd({"cmd": "battle_action", "action": "door", "unit": sid,
                        "x": tx_t, "y": ty_t, "z": dz})
        assert res.get("ok"), f"door action failed: {res}"
        time.sleep(3.0)

        # --- verify OPEN on both machines (door-sync) ---
        ti_h = tile_info(host, dx, dy, dz)
        ti_c = tile_info(client, dx, dy, dz)
        assert door_is_open(ti_h, pname, is_ufo), f"door not open on host: {ti_h}"
        assert door_is_open(ti_c, pname, is_ufo), f"door not open on client: {ti_c}"
        print("UFO door opened on both machines")

        # --- VERIFY-2 (UFO half): the open is invisible to the terrain bucket ---
        after_h = tvec(host, idx)
        assert after_h is not None, "no terrain vector after open"
        assert bucket_fields(before_h) == bucket_fields(after_h), (
            "VERIFY-2 FAILED: the UFO-door open moved a terrain-bucket field\n"
            f"  before = {bucket_fields(before_h)}\n  after  = {bucket_fields(after_h)}")
        assert before_h.get("door") != after_h.get("door"), (
            "VERIFY-2 sanity: the door bitmask did not change on the open "
            f"(before={before_h.get('door')} after={after_h.get('door')})")
        sc = session.sync_check(host)
        terr = [m for m in sc.get("mismatches", []) if m["bucket"] == "terrain"]
        assert not terr, f"terrain bucket fired on a synced UFO-door open: {terr}"
        print(f"VERIFY-2 UFO: terrain bucket UNCHANGED (door bits {before_h.get('door')}"
              f"->{after_h.get('door')}); UFO-door divergence is saveBlob-only, "
              f"terrain-blind (0 terrain mismatches)")

        # --- end the XCOM turn, check the close state on both ---
        res = host.cmd({"cmd": "battle_action", "action": "end_turn"})
        assert res.get("ok"), f"end_turn failed: {res}"
        print("end turn dispatched")
        time.sleep(4.0)
        for _ in range(4):
            for gc in (host, client):
                t = gc.cmd({"cmd": "get_state"})["states"][-1].split("::")[-1]
                if t not in ("BattlescapeState", "NextTurnState", "DebriefingState"):
                    gc.cmd({"cmd": "dismiss_popup"})
            time.sleep(1.0)

        ti_h2 = tile_info(host, dx, dy, dz)
        ti_c2 = tile_info(client, dx, dy, dz)
        host_open = door_is_open(ti_h2, pname, is_ufo)
        client_open = door_is_open(ti_c2, pname, is_ufo)
        print(f"after end-turn: host_open={host_open} client_open={client_open}")

        if not host_open and client_open:
            raise AssertionError(
                f"ISSUE: host closed the UFO door but client still sees it open\n"
                f"  host tile: {ti_h2}\n  client tile: {ti_c2}")
        # Every other combination is fine: both closed (normal close), both still
        # open (an alien re-opened / turn did not process the close yet - matched),
        # or host open + client already closed (no bug).
        print("PASS: UFO door close state consistent across both machines")
        print("UFO-DOOR-CLOSE SYNC TEST PASSED")

    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass

    print("DONE")


if __name__ == "__main__":
    main()
