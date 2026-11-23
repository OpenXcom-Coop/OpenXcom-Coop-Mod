"""test_client_walk_draw.py: the second player's machine (the client) draws a walking soldier ONCE per frame, at one
screen position, as the host (vanilla) does.

The client shows a walk as a display-only replay (CoopGhost's walk ghost): the soldier is drawn from the tile it walks
to, and a second pass draws it from the tile it leaves so the terrain drawn later does not cover it. A client that
draws that second pass as a unit standing on the level below (and from the wrong tile) shows a stray copy of the
soldier's head and shoulders one tile behind and one level under the walker for the whole walk.

Probe: event_state `drawProbe` (Map::drawUnit, TEST-ONLY): `unitDraws` counts sprite draws, `unitSplitDraws` counts a
one-tile unit drawn again in the same frame at another screen position (`unitSplitLast` keeps the last one).

ONE boot: test_follow_camera's terror skirmish (STR_TERROR_MISSION, map seed 1, night), lobby key 47719, aliens
pinned. Rows, in this order:
  host_walk_east    the host's real-UI walk of H (soldier 10) from (14,24,0) to (17,24,0), facing east (3 steps). The
                    client camera is centred on the walk.
  client_walk_east  the client's walk of C (soldier 8) from (12,26,0) to (15,26,0), facing east (3 steps).
  client_walk_west  C walks back to (13,26,0), facing west (2 steps).
Cells per row:
  <row>-walk     (precondition) the walker reached the destination on both machines and the client enqueued one walk
                 ghost per step.
  <row>-drawn    (precondition) the client drew unit sprites during the walk (unitDraws grew).
  <row>-client   the client's unitSplitDraws did not grow (the walker drawn at one screen position per frame).
  <row>-host     (guard) the host's unitSplitDraws did not grow.
  <row>-common   hash_now full: every bucket EQUAL; desyncSeen false on both; no new crash file.

One EVIDENCE line per row, one PASS / FAIL line per cell. Every row runs after a failure. One run is the result, no
skip path. Exit 0 only when every cell passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_client_walk_draw.py
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
import test_client_shoot as CSH  # noqa: E402
import test_seat_pacing as SPC  # noqa: E402

KEY = "47719"                     # this file's lobby key
H_ID, C_ID = 10, 8                # the host seat's first soldier, the client seat's first soldier
SEATED = [8, 9]
TU_MAX = 255
STEP_S = 30
# (row, walker, start tile, start facing, destination, steps, camera centre)
WALKS = (("host_walk_east", "host", H_ID, (14, 24, 0), 2, (17, 24, 0), 3, (15, 24, 0)),
         ("client_walk_east", "client", C_ID, (12, 26, 0), 2, (15, 26, 0), 3, (13, 26, 0)),
         ("client_walk_west", "client", C_ID, None, None, (13, 26, 0), 2, (14, 26, 0)))
CELLS = ("walk", "drawn", "client", "host", "common")


class Miss(Exception):
    pass


def units(gc):
    return session.units_by_id(battle_state(gc))


def upos(u):
    return (u.get("x"), u.get("y"), u.get("z")) if u else None


def draw(gc):
    return event_state(gc).get("drawProbe") or {}


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True, round(time.time() - t0, 2)
        time.sleep(interval)
    return bool(pred()), round(time.time() - t0, 2)


def common(host, client, crash0):
    try:
        assert_hash_clean(host, client, full=True, what="client_walk_draw common")
        hashed = "all buckets EQUAL"
    except AssertionError as e:
        hashed = str(e)[:400]
    ds = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash,
            f"hash {hashed}; desyncSeen host/client {ds} (want False/False); new crash files {crash} (want none)")


def bring_up(host, client):
    HC.bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=HC.MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": HC.SEED_MAP}))
    pinned = session.pin_ai_neutral(host, client, tag="client_walk_draw")
    session.wait_host_idle(host, client, timeout=STEP_S)
    assert_hash_clean(host, client, full=True, what="client_walk_draw bring-up")
    fps = [battle_state(gc).get("mapFingerprint") for gc in (host, client)]
    assert fps == [HC.MAP_FP, HC.MAP_FP], f"mapFingerprint host/client {fps} (want {HC.MAP_FP})"
    assert seated.get("soldierIds") == SEATED and pinned, f"seated {seated.get('soldierIds')} pinned {pinned}"
    print(f"[client_walk_draw] boot ok: MAP_FP {fps[0]!r} seated {SEATED} pinned {len(pinned)}", flush=True)


def run_walk(host, client, crash0, spec):
    row, who, uid, start, face, dest, steps, cam = spec
    ev = {}
    if start is not None:
        ev["place"] = CSH.place(host, client, uid, start, face)
    ev["tu"] = CSH.set_tu_both(host, client, uid, TU_MAX)
    for gc in (host, client):
        HC.stage_camera(gc, cam)
    d0 = {gc.name: draw(gc) for gc in (host, client)}
    g0 = event_state(client).get("ghostEnqueued") or 0
    if who == "host":
        ev["tab"] = SPC.tab_select(host, uid)
        HC.stage_camera(client, cam)
        SPC.real_click_walk(host, dest)
    else:
        ev["intent"] = session.send_walk(client, uid, dest)
    ok, ev["settleS"] = wait_until(lambda: upos(units(host).get(uid)) == dest and upos(units(client).get(uid)) == dest
                                   and (event_state(client).get("ghostQueueDepth") or 0) == 0, STEP_S)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:300]
    d1 = {gc.name: draw(gc) for gc in (host, client)}
    g1 = event_state(client).get("ghostEnqueued") or 0
    delta = {m: {k: (d1[m].get(k) or 0) - (d0[m].get(k) or 0) for k in ("unitDraws", "unitSplitDraws", "frame")}
             for m in ("host", "client")}
    ev.update(settled=ok, ghosts=g1 - g0, delta=delta, clientSplitLast=d1["client"].get("unitSplitLast"),
              hostSplitLast=d1["host"].get("unitSplitLast"), at=[upos(units(gc).get(uid)) for gc in (host, client)])
    cells = {"walk": (ok and g1 - g0 == steps,
                      f"walker {uid} on {dest} on both {ok} ({ev['settleS']} s); client walk ghosts enqueued "
                      f"{g1 - g0} (want {steps})")}
    cells["drawn"] = (delta["client"]["unitDraws"] > 0,
                      f"client unitDraws +{delta['client']['unitDraws']} over {delta['client']['frame']} frames "
                      f"(want > 0)")
    cells["client"] = (delta["client"]["unitSplitDraws"] == 0,
                       f"client unitSplitDraws +{delta['client']['unitSplitDraws']} (want +0: one screen position per "
                       f"unit per frame); last split {d1['client'].get('unitSplitLast')}")
    cells["host"] = (delta["host"]["unitSplitDraws"] == 0,
                     f"host unitSplitDraws +{delta['host']['unitSplitDraws']} (want +0); last split "
                     f"{d1['host'].get('unitSplitLast')}")
    cells["common"] = common(host, client, crash0)
    return cells, ev


def report(row, cells, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    failed = []
    for c in CELLS:
        ok, detail = cells.get(c, (False, "not reached"))
        print(f"{'PASS' if ok else 'FAIL'} {row}-{c}: {detail}", flush=True)
        if not ok:
            failed.append(f"{row}-{c}")
    print(f"ROW {row}: {'PASS' if not failed else 'FAIL'}", flush=True)
    return failed


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", 49904, make_user_dir("client_walk_draw_host", options={"coopGhostStepper": True}))
    client = GameClient("client", 49905, make_user_dir("client_walk_draw_client", options={"coopGhostStepper": True}))
    failed = []
    try:
        try:
            bring_up(host, client)
            booted = True
        except Exception as e:
            print(f"CAPTURE boot: {type(e).__name__}: {str(e)[:800]}", flush=True)
            booted = False
        for spec in WALKS:
            row = spec[0]
            if not booted:
                failed += report(row, {}, {"error": "boot"})
                continue
            try:
                cells, ev = run_walk(host, client, crash0, spec)
            except Exception as e:  # every row runs after a failure
                cells, ev = {}, {"error": f"{type(e).__name__}: {str(e)[:600]}"}
            failed += report(row, cells, ev)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[client_walk_draw] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)
    total = len(WALKS) * len(CELLS)
    print(f"\ntest_client_walk_draw: {total - len(failed)}/{total} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
