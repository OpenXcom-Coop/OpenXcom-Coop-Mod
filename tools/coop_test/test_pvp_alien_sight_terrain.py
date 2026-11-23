"""test_pvp_alien_sight_terrain.py: in PvP the alien player's map shows ground an alien comes to see because terrain in
its view was destroyed, without the alien having to move or turn.

The alien side's explored map (its fog) is the host's sweep of every alien's tile sight (CoopFog::authorHostilePass),
cached per alien by position and facing. Vanilla re-derives X-COM's sight of tiles whenever terrain changes (a hit, an
explosion, a door: TileEngine::calculateFOV(position, radius, true, ...)); an alien whose view such an event opens
must be swept again too, or the ground it now sees stays black on the alien player's map until it moves or turns.

Probes: tile_census rows' `hostileBits` (the alien side's reveal bits on that machine: 4 = floor) and `discoveredHere`
(what that machine draws); reveal_hostile_pass {force: true} (HOST: sweep every alien now, return the tile parts that
were missing).

ONE boot: test_battle_end_rules.boot_pvp (STR_SMALL_SCOUT, map seed 1, gamemode 2: the second player plays the aliens),
lobby key 47751. The alien A (1000000) stands on (27,12,0) facing 5 and looks west into a building whose west wall
(the west wall of the tiles x = 20) hides the ground beyond it. A primed fuse-0 STR_HIGH_EXPLOSIVE on (21,13,0), against
that wall (battle_drop on both); the host's END TURN sets it off at the end of the X-COM side; the alien side's
turn screens closed, every ev applied.

Cells:
  setup      (precondition) before: the WEST tiles (18..19, 12..15) unexplored by the alien side on both machines and the
             wall intact (west wall map data 11 on (20,13)); after: that wall part changed on both machines.
  explored   on the alien player's machine every WEST tile's floor is explored by the alien side (hostileBits & 4) and
             drawn as explored (discoveredHere), and the host holds the same bits.
  current    a forced sweep of every alien on the host finds no tile part the alien side's map is missing.
  common     hash_now full: every bucket EQUAL; desyncSeen false on both; no new crash file.

One EVIDENCE line, one PASS / FAIL line per cell. One run is the result, no skip path. Exit 0 only when every cell
passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_pvp_alien_sight_terrain.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
from test_delta_core import both  # noqa: E402

KEY = "47751"
CHARGE = (21, 13, 0)
WALL = (20, 13)
WALL_INTACT = 11                  # the west wall part's map data id before the blast
WEST = [(x, y) for y in range(12, 16) for x in (18, 19)]
BOX = {"x0": 18, "x1": 20, "y0": 12, "y1": 15, "z0": 0, "z1": 0}
CELLS = ("setup", "explored", "current", "common")


def top(gc):
    return ((gc.cmd({"cmd": "get_state"}).get("states") or [None])[-1] or "").replace("class OpenXcom::", "")


def census(gc):
    r = gc.cmd(dict({"cmd": "tile_census"}, **BOX))
    return {(t["x"], t["y"]): {"west": t["parts"]["westwall"]["mapDataID"], "bits": t.get("hostileBits"),
                               "drawn": t.get("discoveredHere")} for t in (r.get("tiles") or []) if t}


def common(host, client, crash0):
    try:
        assert_hash_clean(host, client, full=True, what="pvp_alien_sight_terrain common")
        hashed = "all buckets EQUAL"
    except Exception as e:
        hashed = f"{type(e).__name__}: {str(e)[:400]}"
    ds = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash,
            f"hash {hashed}; desyncSeen host/client {ds} (want False/False); new crash files {crash} (want none)")


def run(host, client, crash0):
    BER.boot_pvp(host, client, KEY)
    session.wait_host_idle(host, client, timeout=30)
    pre = {gc.name: census(gc) for gc in (host, client)}
    both(host, client, {"cmd": "battle_drop", "x": CHARGE[0], "y": CHARGE[1], "z": CHARGE[2],
                        "item": "STR_HIGH_EXPLOSIVE", "prime": True, "fuse": 0}, ("ids",))
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    t0 = time.time()
    while time.time() - t0 < 30 and not (battle_state(host).get("side") == 1 and battle_state(client).get("side") == 1):
        time.sleep(0.1)
    for _ in range(6):
        for gc in (client, host):
            if "NextTurnState" in top(gc):
                gc.cmd({"cmd": "close_nextturn"})
        time.sleep(0.3)
    session.wait_seq_barrier(host, client, timeout=30)
    session.wait_host_idle(host, client, timeout=30)
    post = {gc.name: census(gc) for gc in (host, client)}
    forced = host.cmd({"cmd": "reveal_hostile_pass", "force": True})
    ev = {"sides": [battle_state(gc).get("side") for gc in (host, client)],
          "pre": {m: {f"{k[0]},{k[1]}": v for k, v in pre[m].items()} for m in pre},
          "post": {m: {f"{k[0]},{k[1]}": v for k, v in post[m].items()} for m in post},
          "forced": {k: forced.get(k) for k in ("discovered", "swept", "candidates")}}
    print(f"EVIDENCE alien_sight_terrain: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    pre_unexplored = all(not ((pre[m][t]["bits"] or 0) & 4) for m in pre for t in WEST)
    wall_pre = [pre[m][WALL]["west"] for m in ("host", "client")]
    wall_post = [post[m][WALL]["west"] for m in ("host", "client")]
    cells = {"setup": (pre_unexplored and wall_pre == [WALL_INTACT] * 2 and all(w != WALL_INTACT for w in wall_post),
                       f"WEST unexplored by the alien side before on both {pre_unexplored}; wall {WALL} west part "
                       f"before {wall_pre} (want {WALL_INTACT}) after {wall_post} (want changed)")}
    cb = {t: post["client"][t]["bits"] for t in WEST}
    hb = {t: post["host"][t]["bits"] for t in WEST}
    cd = {t: post["client"][t]["drawn"] for t in WEST}
    cells["explored"] = (all((cb[t] or 0) & 4 for t in WEST) and all(cd[t] for t in WEST) and cb == hb,
                         f"alien player: WEST floor explored {[(t, cb[t]) for t in WEST]}, drawn explored "
                         f"{[cd[t] for t in WEST]} (want every one), host bits equal {cb == hb}")
    cells["current"] = (forced.get("discovered") == 0,
                        f"forced sweep of every alien found {forced.get('discovered')} missing tile part(s) (want 0)")
    cells["common"] = common(host, client, crash0)
    return cells


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", 49920, make_user_dir("pvp_alien_sight_terrain_host"))
    client = GameClient("client", 49921, make_user_dir("pvp_alien_sight_terrain_client"))
    cells = {}
    try:
        try:
            cells = run(host, client, crash0)
        except Exception as e:
            print(f"CAPTURE: {type(e).__name__}: {str(e)[:800]}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[pvp_alien_sight_terrain] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)
    failed = []
    for c in CELLS:
        ok, detail = cells.get(c, (False, "not reached"))
        print(f"{'PASS' if ok else 'FAIL'} alien_sight_terrain-{c}: {detail}", flush=True)
        if not ok:
            failed.append(c)
    print(f"\ntest_pvp_alien_sight_terrain: {len(CELLS) - len(failed)}/{len(CELLS)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
