"""test_client_walk_diagonal.py: on the second player's machine (the client) a soldier stays drawn through a diagonal step
to the north-east or south-west, as on the host.

Vanilla draws a walking unit into the pass of every tile its sprite overlaps, each pass clipped to that tile
(UnitWalkBState registers the walker with TileEngine::addMovingUnit; Map::drawTerrain draws it from the neighbouring
tiles). A north-east or south-west step moves the sprite sideways across the screen, through a third tile beside the
two of the step, and that tile's pass is the one that shows the sprite mid-step. The client replays a walk for display
only and draws it into the two tiles of the step alone: mid-step the soldier vanishes.

Probe: event_state `drawProbe.movingCover` (TEST-ONLY): per frame and moving one-tile unit, the share (permille) of its
32x40 sprite box that lies inside the masks of the passes that drew it.

ONE boot: test_host_combat's roster-pinned terror skirmish (STR_TERROR_MISSION, map seed 1), lobby key 47743, aliens
pinned, both cameras centred on each step. Rows, in this order (one walk_step each):
  client_ne  the client's soldier C (8) from (13,26,0) facing 1 to (14,25,0) (north-east).
  client_sw  C back to (13,26,0) (south-west).
  host_ne    the host's soldier H (10) from (13,26,0) facing 1 to (14,25,0), its real-UI walk (C moved aside first).
Cells per row:
  <row>-walk    (precondition) the walker reached the destination on both machines; the client enqueued 1 walk ghost.
  <row>-cover   the client's lowest per-frame coverage of the walker during the step is at least 0.8 x the host's (and
                the host drew the walker in >= 1 frame).
  <row>-common  hash_now full: every bucket EQUAL; desyncSeen false on both; no new crash file.

One EVIDENCE line per row, one PASS / FAIL line per cell. Every row runs after a failure. One run is the result, no
skip path. Exit 0 only when every cell passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_client_walk_diagonal.py
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

KEY = "47743"
H_ID, C_ID = 10, 8
TU_MAX = 255
STEP_S = 30
NE_FROM, NE_TO = (13, 26, 0), (14, 25, 0)
ASIDE = (12, 24, 0)
# (row, walker, unit, start tile (None = stays), start facing, destination)
WALKS = (("client_ne", "client", C_ID, NE_FROM, 1, NE_TO),
         ("client_sw", "client", C_ID, None, None, NE_FROM),
         ("host_ne", "host", H_ID, NE_FROM, 1, NE_TO))
CELLS = ("walk", "cover", "common")


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
        assert_hash_clean(host, client, full=True, what="client_walk_diagonal common")
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
    pinned = session.pin_ai_neutral(host, client, tag="client_walk_diagonal")
    session.wait_host_idle(host, client, timeout=STEP_S)
    assert_hash_clean(host, client, full=True, what="client_walk_diagonal bring-up")
    fps = [battle_state(gc).get("mapFingerprint") for gc in (host, client)]
    assert fps == [HC.MAP_FP, HC.MAP_FP], f"mapFingerprint host/client {fps} (want {HC.MAP_FP})"
    assert seated.get("soldierIds") == [C_ID, 9] and pinned, f"seated {seated.get('soldierIds')} pinned {pinned}"


def covers(d0, d1, uid):
    f0 = d0.get("frame") or 0
    return [c[2] for c in (d1.get("movingCover") or []) if c[0] >= f0 and c[1] == uid]


def run_walk(host, client, crash0, spec):
    row, who, uid, start, face, dest = spec
    ev = {}
    if who == "host":
        ev["aside"] = CSH.place(host, client, C_ID, ASIDE, 2)
    if start is not None:
        ev["place"] = CSH.place(host, client, uid, start, face)
    ev["tu"] = CSH.set_tu_both(host, client, uid, TU_MAX)
    for gc in (host, client):
        HC.stage_camera(gc, NE_TO)
    time.sleep(0.3)
    d0 = {gc.name: draw(gc) for gc in (host, client)}
    g0 = event_state(client).get("ghostEnqueued") or 0
    if who == "host":
        ev["tab"] = SPC.tab_select(host, uid)
        host.cmd({"cmd": "map_tile_click", "x": dest[0], "y": dest[1], "z": dest[2]})
    else:
        ev["intent"] = session.send_walk(client, uid, dest)
    ok, ev["settleS"] = wait_until(lambda: upos(units(host).get(uid)) == dest and upos(units(client).get(uid)) == dest
                                   and (event_state(client).get("ghostQueueDepth") or 0) == 0, STEP_S)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:300]
    time.sleep(0.2)
    d1 = {gc.name: draw(gc) for gc in (host, client)}
    g1 = event_state(client).get("ghostEnqueued") or 0
    cov = {m: covers(d0[m], d1[m], uid) for m in ("host", "client")}
    ev.update(settled=ok, ghosts=g1 - g0, cover=cov, at=[upos(units(gc).get(uid)) for gc in (host, client)])
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    cells = {"walk": (ok and g1 - g0 == 1, f"walker {uid} on {dest} on both {ok} ({ev['settleS']} s); client walk "
                                            f"ghosts {g1 - g0} (want 1)")}
    hmin = min(cov["host"]) if cov["host"] else None
    cmin = min(cov["client"]) if cov["client"] else None
    cells["cover"] = (hmin is not None and cmin is not None and cmin >= 0.8 * hmin,
                      f"lowest per-frame coverage of the walker (permille): client {cmin} over {len(cov['client'])} "
                      f"frames, host {hmin} over {len(cov['host'])} frames (want client >= 0.8 x host)")
    cells["common"] = common(host, client, crash0)
    return cells


def report(row, cells):
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
    host = GameClient("host", 49914, make_user_dir("client_walk_diagonal_host", options={"coopGhostStepper": True}))
    client = GameClient("client", 49915, make_user_dir("client_walk_diagonal_client",
                                                       options={"coopGhostStepper": True}))
    failed = []
    try:
        try:
            bring_up(host, client)
            booted = True
        except Exception as e:
            print(f"CAPTURE boot: {type(e).__name__}: {str(e)[:800]}", flush=True)
            booted = False
        for spec in WALKS:
            if not booted:
                failed += report(spec[0], {})
                continue
            try:
                cells = run_walk(host, client, crash0, spec)
            except Exception as e:  # every row runs after a failure
                print(f"EVIDENCE {spec[0]}: row raised {type(e).__name__}: {str(e)[:600]}", flush=True)
                cells = {}
            failed += report(spec[0], cells)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[client_walk_diagonal] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)
    total = len(WALKS) * len(CELLS)
    print(f"\ntest_client_walk_diagonal: {total - len(failed)}/{total} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
