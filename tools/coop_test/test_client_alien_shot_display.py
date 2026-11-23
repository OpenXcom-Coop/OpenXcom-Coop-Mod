"""test_client_alien_shot_display.py: in the alien turn the second player's machine (the client) shows an unseen
alien's shot the way the host does: the projectile drawn once it flies over tiles X-COM sees (the map shown instead of
HIDDEN MOVEMENT), the camera following it, and the HIDDEN MOVEMENT screen's AI progress bar filling.

Vanilla (the host) counts a projectile as in view when the tile it is on is seen by X-COM (Tile::getVisible()); a
client never counts tile sight (TileEngine::calculateTilesInFOV leaves fog authoring to the host), so a client that
reads that counter never sees the projectile of an alien its side does not see: HIDDEN MOVEMENT stays up, nothing is
drawn and the follow camera (which runs only while the projectile is in view) never moves. The progress bar is fed
only by the host's own AI loop, so a client that is not sent its value shows "Thinking..." with no bar.

ONE boot: test_ai_origins' bring-up (default NEW BATTLE map, day, seeds 1/1, lobby key 47723, A = the only alien,
pinned, X-COM reactions 0), then its ai_shot staging (the primed fuse-0 grenade and two clips on (7,3,0); C (soldier 8)
on (15,8,0) facing 4, away from A; A on (15,3,0) facing 3, A tu 54) with the other X-COM soldiers moved so no one sees
A: soldier 9 on (15,24,0) facing 0 (21 tiles from A, 16-20 tiles from the shot's path), soldiers 10-14 on
(2..6,34,0) facing 0. Both cameras centred on (2,38,0), far from the shot. One END TURN cycle, host set_seed 15
right before its press: A turns and fires snap shots at C (measured: three, the third kills C), never seen. A sampler
reads both machines every ~0.1 s through the cycle.

Cells:
  shot        (precondition) the host emitted >= 1 `shot` in the cycle; A was never visible in a host alien-side
              sample; the host drew the projectile in view (drawProbe projInFovFrames grew).
  projectile  the client drew the projectile in view (drawProbe projInFovFrames / projFrames) for at least 0.8 x the
              host's share of its flight frames.
  map         the share of client alien-side samples that show the map (hiddenMovementShown true) is at least 0.75 x
              the host's share.
  camera      the client's projectile follow first moved its camera with the bullet on the same tile as the host's
              first follow move of the cycle (drawProbe followTiles, x/y within 1 tile): the camera picks the shot up
              where it enters X-COM's sight, not only at its target.
  progress    >= 1 client alien-side sample shows a coloured progress bar with a value > 0 (aiProgressColor != 0,
              aiProgress > 0), as >= 1 host sample does (guard).
  common      hash_now full: every bucket EQUAL; desyncSeen false on both; no new crash file.

One EVIDENCE line, one PASS / FAIL line per cell. One run is the result, no skip path. Exit 0 only when every cell
passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_client_alien_shot_display.py
"""

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_client_alien_sight  # noqa: E402,F401  (its per-GameClient lock: the sampler thread shares the sockets)
import test_ai_origins as AO  # noqa: E402
from test_delta_core import both, tele_both  # noqa: E402

KEY = "47723"                     # this file's lobby key
A_ID, C_ID = AO.A_ID, AO.C_ID
VIEWER = (9, (15, 24, 0), 0)      # sees the shot's path (16-20 tiles), not A (21 tiles)
AWAY = ((10, (2, 34, 0)), (11, (3, 34, 0)), (12, (4, 34, 0)), (13, (5, 34, 0)), (14, (6, 34, 0)))
CAMERA = (2, 38, 0)               # both cameras, far from the shot
SEED = AO.SEED_AI_SHOT            # 15
PERIOD = 0.05
CELLS = ("shot", "projectile", "map", "camera", "progress", "common")


def brief(gc):
    bs = battle_state(gc)
    a = session.units_by_id(bs).get(A_ID) or {}
    cam = (event_state(gc).get("camera") or {}).get("offset")
    return {"side": bs.get("side"), "hms": bs.get("hiddenMovementShown"), "aip": bs.get("aiProgress"),
            "aipColor": bs.get("aiProgressColor"), "aVis": a.get("visible"), "cam": cam}


class Sampler(threading.Thread):
    def __init__(self, host, client):
        super().__init__(daemon=True)
        self.host, self.client, self.rows, self.errors = host, client, [], []
        self.t0, self.stop_ev = time.time(), threading.Event()

    def run(self):
        while not self.stop_ev.is_set():
            t = round(time.time() - self.t0, 2)
            try:
                self.rows.append({"t": t, "h": brief(self.host), "c": brief(self.client)})
            except Exception as e:  # recorded, never retried
                self.errors.append(f"{t}: {type(e).__name__}: {str(e)[:160]}")
            self.stop_ev.wait(PERIOD)

    def stop(self):
        self.stop_ev.set()
        self.join(timeout=10)


def draw(gc):
    return event_state(gc).get("drawProbe") or {}


def boot(host, client):
    """test_ai_origins.boot with this file's lobby key."""
    AO.bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": AO.SEED_MAP}))
    hs = battle_state(host)
    assert hs.get("mapFingerprint") == AO.MAP_FP and battle_state(client).get("mapFingerprint") == AO.MAP_FP, (
        f"mapFingerprint host {hs.get('mapFingerprint')!r} (baked {AO.MAP_FP!r})")
    assert seated.get("soldierIds") == AO.SEATED, f"seated {seated.get('soldierIds')} (baked {AO.SEATED})"
    pinned = session.pin_ai_neutral(host, client, tag="client_alien_shot_display")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    for uid, u in sorted(session.units_by_id(hs).items()):
        if u.get("faction") == AO.FACTION_PLAYER and not u.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="client_alien_shot_display bring-up")
    print(f"[client_alien_shot_display] boot ok: MAP_FP {AO.MAP_FP!r} seated {AO.SEATED} pinned {pinned}", flush=True)


def stage(host, client):
    both(host, client, {"cmd": "battle_drop", "x": AO.GRENADE_TILE[0], "y": AO.GRENADE_TILE[1],
                        "z": AO.GRENADE_TILE[2], "item": "STR_GRENADE", "prime": True, "fuse": 0}, ("ids",))
    both(host, client, {"cmd": "battle_drop", "x": AO.GRENADE_TILE[0], "y": AO.GRENADE_TILE[1],
                        "z": AO.GRENADE_TILE[2], "item": "STR_RIFLE_CLIP", "count": 2}, ("ids",))
    tele_both(host, client, C_ID, AO.SHOT_C_TILE, AO.SHOT_C_DIR)
    tele_both(host, client, A_ID, AO.SHOT_A_TILE, AO.SHOT_A_DIR)
    tele_both(host, client, VIEWER[0], VIEWER[1], VIEWER[2])
    for uid, tile in AWAY:
        tele_both(host, client, uid, tile, 0)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu",
                        "value": AO.A_TU}, ("tu",))
    for gc in (host, client):
        r = gc.cmd({"cmd": "battle_camera_center", "x": CAMERA[0], "y": CAMERA[1], "z": CAMERA[2]})
        assert r.get("ok"), f"battle_camera_center on {gc.name}: {r}"


def common(host, client, crash0):
    try:
        assert_hash_clean(host, client, full=True, what="client_alien_shot_display common")
        hashed = "all buckets EQUAL"
    except AssertionError as e:
        hashed = str(e)[:400]
    ds = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash,
            f"hash {hashed}; desyncSeen host/client {ds} (want False/False); new crash files {crash} (want none)")


def run(host, client, crash0):
    stage(host, client)
    d0 = {gc.name: draw(gc) for gc in (host, client)}
    m0 = len((event_state(client).get("camera") or {}).get("moves") or [])
    smp = Sampler(host, client)
    smp.start()
    try:
        rec = AO.run_cycle(host, client, SEED, [])
    finally:
        smp.stop()
    d1 = {gc.name: draw(gc) for gc in (host, client)}
    proj = {m: {k: (d1[m].get(k) or 0) - (d0[m].get(k) or 0) for k in ("projFrames", "projInFovFrames", "followFrames")}
            for m in ("host", "client")}
    shots = [e["seq"] for e in rec["hev"] if e["kind"] == "shot"]
    s1 = {m: [r[m] for r in smp.rows if r[m]["side"] == 1] for m in ("h", "c")}
    moves = [m for m in ((event_state(client).get("camera") or {}).get("moves") or [])[m0 - 32 if m0 > 32 else 0:]
             if m.get("seq") in shots and m.get("reason") == "follow"]
    ev = {"notes": rec["notes"], "hostEvs": [(e["seq"], e["kind"], e["actionId"]) for e in rec["hev"]],
          "proj": proj, "followMoves": [(m.get("seq"), m.get("before"), m.get("after")) for m in moves],
          "sideOneSamples": {m: len(s1[m]) for m in ("h", "c")},
          "clientSide1": [(r["hms"], r["aip"], r["aipColor"]) for r in s1["c"]],
          "hostSide1": [(r["hms"], r["aip"], r["aipColor"], r["aVis"]) for r in s1["h"]],
          "samplerErrors": smp.errors[:5]}
    print(f"EVIDENCE alien_shot: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    a_seen = [r["aVis"] for r in s1["h"] if r["aVis"]]
    cells = {"shot": (bool(shots) and bool(s1["h"]) and not a_seen and proj["host"]["projInFovFrames"] > 0,
                      f"host shot seqs {shots} (want >= 1); host alien-side samples {len(s1['h'])} with A visible "
                      f"{len(a_seen)} (want > 0 and 0); host projInFovFrames +{proj['host']['projInFovFrames']} "
                      f"(want > 0)")}
    share = {m: proj[m]["projInFovFrames"] / proj[m]["projFrames"] if proj[m]["projFrames"] else 0.0
             for m in ("host", "client")}
    cells["projectile"] = (proj["client"]["projInFovFrames"] > 0 and share["client"] >= 0.8 * share["host"],
                           f"client projInFovFrames +{proj['client']['projInFovFrames']} of projFrames "
                           f"+{proj['client']['projFrames']} = {share['client']:.2f}; host "
                           f"+{proj['host']['projInFovFrames']} of +{proj['host']['projFrames']} = {share['host']:.2f} "
                           f"(want client > 0 and >= 0.8 x host)")
    hms_c = [r["hms"] for r in s1["c"]]
    hms_h = [r["hms"] for r in s1["h"]]
    mshare = {m: (sum(1 for v in hv if v is True) / len(hv)) if hv else 0.0 for m, hv in (("c", hms_c), ("h", hms_h))}
    cells["map"] = (bool(hms_c) and mshare["c"] >= 0.75 * mshare["h"] and mshare["h"] > 0,
                    f"alien-side samples showing the map: client {mshare['c']:.2f} of {len(hms_c)}, host "
                    f"{mshare['h']:.2f} of {len(hms_h)} (want client >= 0.75 x host, host > 0)")
    first = {}
    for gc in (host, client):
        n0 = d0[gc.name].get("followFrames") or 0
        new_moves = [t for t in (d1[gc.name].get("followTiles") or []) if t[0] > n0]
        first[gc.name] = new_moves[0][1:] if new_moves else None
    fh, fc = first["host"], first["client"]
    cells["camera"] = (fh is not None and fc is not None and abs(fh[0] - fc[0]) <= 1 and abs(fh[1] - fc[1]) <= 1,
                       f"bullet tile at the first follow move of the cycle: client {fc}, host {fh} (want both, x/y "
                       f"within 1 tile); follow moves client +{proj['client']['followFrames']}, host "
                       f"+{proj['host']['followFrames']}; client `follow` records (seq, before, after) "
                       f"{[(m.get('seq'), m.get('before'), m.get('after')) for m in moves]}")
    bar_c = [(r["aip"], r["aipColor"]) for r in s1["c"] if r["aipColor"] and (r["aip"] or 0) > 0]
    bar_h = [(r["aip"], r["aipColor"]) for r in s1["h"] if r["aipColor"] and (r["aip"] or 0) > 0]
    cells["progress"] = (bool(bar_c) and bool(bar_h),
                         f"client alien-side samples with a coloured bar > 0: {bar_c} (want >= 1); host: {bar_h} "
                         f"(guard: >= 1)")
    cells["common"] = common(host, client, crash0)
    return cells


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", 49906, make_user_dir("client_alien_shot_display_host"))
    client = GameClient("client", 49907, make_user_dir("client_alien_shot_display_client"))
    cells = {}
    try:
        try:
            boot(host, client)
            cells = run(host, client, crash0)
        except Exception as e:
            print(f"CAPTURE: {type(e).__name__}: {str(e)[:800]}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[client_alien_shot_display] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}",
                      flush=True)
    failed = []
    for c in CELLS:
        ok, detail = cells.get(c, (False, "not reached"))
        print(f"{'PASS' if ok else 'FAIL'} alien_shot-{c}: {detail}", flush=True)
        if not ok:
            failed.append(c)
    print(f"\ntest_client_alien_shot_display: {len(CELLS) - len(failed)}/{len(CELLS)} cells passed (fail={failed}) "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
