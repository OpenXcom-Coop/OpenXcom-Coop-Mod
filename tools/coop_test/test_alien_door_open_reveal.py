"""test_alien_door_open_reveal.py: the two machines stay in sync when an alien opens a door in the soldiers' view on
the alien side.

Opening a door recomputes the sight of every unit that can see the doorway (TileEngine::unitOpensDoor ->
calculateFOV), so the soldiers explore the ground behind the door during the alien side. The host sends the acting
(alien) side's new explored tiles with the envelope itself and the soldiers' new explored tiles in their own `reveal`
envelope after it. The alien's action then ends with a bt_action_end whose `saveBlob` hash counts the soldiers' explored
tiles: if the soldiers' tiles left after it, the client would check that hash without them, report a desync and halt.

ONE boot: test_host_combat's terror skirmish (STR_TERROR_MISSION, a Skyranger battle), map seed 5, lobby key 48802,
every alien pinned (none acts), X-COM reactions 0. On turn 1 the soldiers in the Skyranger have explored the floor in
front of the closed door at DOOR (a north-wall door) and not the floor behind it (BEHIND). Replacement rule for DOOR
and the seed: the first closed normal door (west or north wall) whose near floor the soldiers explored on turn 1 and
whose far floor they did not, with the doorway on a soldier's line of sight; the precondition cells say when it no
longer holds. Alien A (1000000) is moved (battle_teleport_unit on both) onto BEHIND facing the door. One END TURN
(the client first, then the host); while the host's alien-side turn screen is up, A gets exactly the closed door's
walking TU cost (base TU 0, so the alien reserve is 0) and the host right-clicks the door with it the way the host's
own click does (battle_action door hostClick: one action, ended by its bt_action_end).

Cells:
  door_open  (precondition) the host sent one `door` envelope on the alien side and the door's north-wall part changed
             on both machines (the door is open).
  new_sight  (precondition) BEHIND was unexplored on both machines before the open and explored on the host after it,
             on the alien side.
  in_sync    the client reported no desync through the cycle (event_state desyncSeen false), the client explored BEHIND
             too, and both machines are back on the player side, turn 2.
  common     hash_now full: every bucket EQUAL; desyncSeen false on both; no new crash file.

One EVIDENCE line, one PASS / FAIL line per cell. One run is the result, no skip path. Exit 0 only when every cell
passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_alien_door_open_reveal.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_host_combat as HC  # noqa: E402
from test_delta_core import both, tele_both  # noqa: E402

KEY = "48802"                     # this file's lobby key
SEED_MAP = 5                      # terror map seed with a closed door the soldiers see on turn 1
DOOR = (44, 7, 0)                 # the north-wall door; its near floor is this tile
BEHIND = (44, 6, 0)               # the floor behind the door, unexplored on turn 1
A_ID = 1000000                    # the alien that opens the door
A_DIR = 4                         # south: facing DOOR from BEHIND
CELLS = ("door_open", "new_sight", "in_sync", "common")


def top(gc):
    return ((gc.cmd({"cmd": "get_state"}).get("states") or [None])[-1] or "").replace("class OpenXcom::", "")


def close_turn_screens(gc):
    for _ in range(4):
        if "NextTurnState" not in top(gc):
            return
        gc.cmd({"cmd": "close_nextturn"})
        time.sleep(0.2)


def explored(gc, t):
    r = gc.cmd({"cmd": "tile_census", "x0": t[0], "x1": t[0], "y0": t[1], "y1": t[1], "z0": t[2], "z1": t[2]})
    return (r.get("tiles") or [{}])[0].get("discoveredHere")


def north_wall(gc):
    r = gc.cmd({"cmd": "tile_info", "x": DOOR[0], "y": DOOR[1], "z": DOOR[2]})
    return (r.get("parts") or {}).get("northwall") or {}


def unit(gc, uid):
    return next((u for u in battle_state(gc)["units"] if u["id"] == uid), {})


def bring_up(host, client):
    HC.bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=HC.MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    pinned = session.pin_ai_neutral(host, client, tag="alien_door_open_reveal")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="alien_door_open_reveal bring-up")
    assert A_ID in pinned, f"pin_ai_neutral pinned {pinned} (want {A_ID} among them)"
    for x in battle_state(host)["units"]:
        if x.get("faction") == 0 and not x.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": x["id"], "stat": "reactions",
                                "value": 0}, ("tu",))
    print(f"[alien_door_open_reveal] boot ok: mapFingerprint {battle_state(host).get('mapFingerprint')!r} seated "
          f"{seated.get('soldierIds')} pinned {len(pinned)}", flush=True)


def common(host, client, crash0):
    try:
        assert_hash_clean(host, client, full=True, what="alien_door_open_reveal common")
        hashed = "all buckets EQUAL"
    except Exception as e:
        hashed = f"{type(e).__name__}: {str(e)[:400]}"
    ds = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash,
            f"hash {hashed}; desyncSeen host/client {ds} (want False/False); new crash files {crash} (want none)")


def run(host, client, crash0):
    turn0 = battle_state(host).get("turn")
    wall0 = [north_wall(gc) for gc in (host, client)]
    ev = {"turn0": turn0, "wall0": [{k: w.get(k) for k in ("isDoor", "mapDataID", "tuWalk")} for w in wall0],
          "nearExplored0": [explored(gc, DOOR) for gc in (host, client)],
          "behindExplored0": [explored(gc, BEHIND) for gc in (host, client)]}
    if not (wall0[0].get("isDoor") and wall0[1].get("isDoor")):
        raise AssertionError(f"precondition: no closed door in DOOR {DOOR}'s north wall: {ev['wall0']}")
    if ev["nearExplored0"] != [True, True] or ev["behindExplored0"] != [False, False]:
        raise AssertionError(f"precondition: DOOR {DOOR} explored {ev['nearExplored0']} and BEHIND {BEHIND} explored "
                             f"{ev['behindExplored0']} (want True/True and False/False)")
    cost = wall0[0].get("tuWalk")
    ev["moved"] = tele_both(host, client, A_ID, BEHIND, A_DIR)
    client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    host.wait_for("host END TURN 1/2", lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None,
                  timeout=20)
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    host.wait_for("alien side on both, the host held on its turn screen",
                  lambda: (battle_state(host).get("side") == 1 and "NextTurnState" in top(host)
                           and battle_state(client).get("side") == 1) or None, timeout=30)
    close_turn_screens(client)
    ev["tuSet"] = both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu",
                                      "value": cost, "refill": True}, ("tu",)).get("tu")
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": 0}, ("tu",))
    doors0 = event_state(host).get("coopDoorEvsEmitted")
    ev["open"] = host.cmd({"cmd": "battle_action", "action": "door", "unit": A_ID, "hostClick": True})
    host.wait_for("the host's door envelope", lambda: (event_state(host).get("coopDoorEvsEmitted") or 0) > doors0 or None,
                  timeout=20)
    ev["sideAtOpen"] = battle_state(host).get("side")
    ev["doorEvs"] = (event_state(host).get("coopDoorEvsEmitted") or 0) - doors0
    ev["behindExploredHost"] = explored(host, BEHIND)
    ev["aTuAfter"] = unit(host, A_ID).get("tu")
    t0 = time.time()
    while time.time() - t0 < 40:
        close_turn_screens(host)
        close_turn_screens(client)
        hs, cs = battle_state(host), battle_state(client)
        if (event_state(client).get("desyncSeen") or (hs.get("side") == 0 and cs.get("side") == 0
                                                       and (hs.get("turn") or 0) > turn0 and (cs.get("turn") or 0) > turn0)):
            break
        time.sleep(0.2)
    time.sleep(0.5)
    wall1 = [north_wall(gc) for gc in (host, client)]
    ces = event_state(client)
    back = [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]
    ev.update(wall1=[{k: w.get(k) for k in ("isDoor", "mapDataID")} for w in wall1],
              behindExplored1=[explored(gc, BEHIND) for gc in (host, client)], back=back,
              clientDesyncSeen=ces.get("desyncSeen"), clientTop=top(client),
              hostResync=event_state(host).get("resync"))
    print(f"EVIDENCE alien_door_open: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    opened = [w.get("mapDataID") for w in wall1] != [w.get("mapDataID") for w in wall0] and \
        wall1[0].get("mapDataID") == wall1[1].get("mapDataID")
    cells = {"door_open": (ev["doorEvs"] == 1 and ev["sideAtOpen"] == 1 and opened,
                           f"host door envelopes {ev['doorEvs']} on side {ev['sideAtOpen']} (want 1 on side 1); "
                           f"north wall {ev['wall0']} -> {ev['wall1']} (want changed and equal on both)"),
             "new_sight": (ev["behindExplored0"] == [False, False] and ev["behindExploredHost"] is True,
                           f"BEHIND explored before {ev['behindExplored0']} (want False/False), on the host after the "
                           f"open {ev['behindExploredHost']} (want True)"),
             "in_sync": (ces.get("desyncSeen") is False and ev["behindExplored1"] == [True, True]
                         and back == [(0, turn0 + 1)] * 2,
                         f"client desyncSeen {ces.get('desyncSeen')} (want False); BEHIND explored host/client "
                         f"{ev['behindExplored1']} (want True/True); side/turn host/client {back} (want "
                         f"0/{turn0 + 1} on both)")}
    session.wait_host_idle(host, client, timeout=30)
    cells["common"] = common(host, client, crash0)
    return cells


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", 49922, make_user_dir("alien_door_open_reveal_host", options={"coopGhostStepper": True}))
    client = GameClient("client", 49923, make_user_dir("alien_door_open_reveal_client",
                                                       options={"coopGhostStepper": True}))
    cells = {}
    try:
        try:
            bring_up(host, client)
            cells = run(host, client, crash0)
        except Exception as e:
            print(f"CAPTURE: {type(e).__name__}: {str(e)[:800]}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[alien_door_open_reveal] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)
    failed = []
    for c in CELLS:
        ok, detail = cells.get(c, (False, "not reached"))
        print(f"{'PASS' if ok else 'FAIL'} alien_door_open-{c}: {detail}", flush=True)
        if not ok:
            failed.append(c)
    print(f"\ntest_alien_door_open_reveal: {len(CELLS) - len(failed)}/{len(CELLS)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
