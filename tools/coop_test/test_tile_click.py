"""RV-U2 rows K1-K5 (boot K): `map_tile_click` probes a battlescape tile and pushes the click on ONE pump pass, so the
click resolves against the camera the pixel was computed for (owner D60, POST-REWRITE-REVISIT rows 2 and 17).

Spec: docs repo rewrite/prompts/rvu2_one_shot_click.md section (f) (QV2-1 (a); orchestrator ruling R-V2-A-1 for K4's staging).
Constants: rewrite/rvu2-task0/sa/CONSTANTS.md (TASK 0 boots Ka' and Kb', every pin equal).

Boot K (key 48696): the host sets SEED_ROSTER before its lobby, STR_TERROR_MISSION, two soldiers seated to the client, map
seed SEED_MAP (test_host_combat's pinned boot), pin_ai_neutral; staging: H on TILE_H facing T_W's direction (hash-gated
place_deterministic), U / C / C2 on their tiles facing 2 (client first), every one at full TU, every bucket EQUAL.
  K1  the host click-selects its own soldier U (H selected first).
  K2  the client click-selects its own soldier C2 (C selected first).
  K3  the client's click on the host's soldier H is refused: "Not one of your soldiers", selection kept.
  K4  the host walks H one tile after the probe had to re-centre a far camera (the row-17 shape). Staging: every
      live hostile to corner NE (hash-gated battle_teleport_all), each at Chebyshev >= 21 from H's tile and T_W.
  K5  a tile the probe cannot verify (-5, -5, 0) is not clicked: nothing changes.
Every click is ONE `map_tile_click` (never `.ok`: an error answer is a FAIL line). Common cell after each row: every hash
bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails every row "boot". No retry, skip or attempt loop (aud-0911-A8).
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when every
cell passes, else 2.

Run:  python tools/coop_test/test_tile_click.py
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
from test_client_shoot import place, set_tu_both  # noqa: E402
from test_seat_pacing import tab_select  # noqa: E402

KEY = "48696"
H, U, C, C2 = 10, 11, 8, 9                 # host seat [10..14] (U = the next host-seat id), client seat [8, 9]
HOST_SEAT, CLIENT_SEAT = [10, 11, 12, 13, 14], [8, 9]
TILE_H, TILE_U, TILE_C, TILE_C2 = (12, 26, 0), (12, 23, 0), (12, 29, 0), (10, 26, 0)   # the first four open STAGE tiles
T_W, DIR_TW = (12, 25, 0), 0               # H's dir-0 neighbour: path_probe reachable, 1 step, tuCost 4
STAGE_DIR = 2                              # U, C, C2 facing
HOSTILE_CORNER, HOSTILE_FACING, MIN_CHEB = "NE", 1, 21   # 13 hostiles to (45..49, 0..4); min Chebyshev 33 (Ka', Kb')
K5_TILE = (-5, -5, 0)                      # never round-trips (Camera clamps, F11091)
NOT_YOURS = "Not one of your soldiers"
STEP_S, SEL_S, WALK_S = 30, 2.0, 20
ANS = ("ok", "verified", "clicked", "centered", "button", "winX", "winY", "baseX", "baseY", "viewLevel", "error")
ROWS = (("K1", ("K1-pre", "K1-click", "K1-effect", "K1-common")),
        ("K2", ("K2-pre", "K2-click", "K2-effect", "K2-common")),
        ("K3", ("K3-pre", "K3-click", "K3-effect", "K3-common")),
        ("K4", ("K4-pre", "K4-click", "K4-effect", "K4-common")),
        ("K5", ("K5-click", "K5-effect", "K5-common")))


class Miss(Exception):
    """A boot step past its bound (its CAPTURE line is already printed)."""


def stack(gc):
    return session.states_stripped(gc)


def log_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for line in f]
    except OSError:
        return []


def bview(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("phase", "inBattle", "side", "turn", "selectedId", "coopWaitText", "mapFingerprint")}


def capture(tag, err, machines):
    """ONE CAPTURE line: each machine's stack, battle_state view, coop_dialog_info, last 40 log lines."""
    cap = {}
    for gc in machines:
        d = {}
        for k, fn in (("stack", stack), ("battle", bview), ("dialog", lambda g: g.cmd({"cmd": "coop_dialog_info"})),
                      ("logTail", lambda g: log_lines(g)[-40:])):
            try:
                d[k] = fn(gc)
            except Exception as e:
                d[k] = f"probe failed: {type(e).__name__}: {e}"
        cap[gc.name] = d
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def guarded(tag, fn, machines):
    try:
        return fn()
    except Exception as e:
        capture(tag, f"{type(e).__name__}: {str(e)[:600]}", machines)
        raise Miss(tag)


def live(gc):
    return {u["id"]: u for u in battle_state(gc).get("units", []) if not u.get("isOut")}


def pos(gc, uid):
    u = live(gc).get(uid) or {}
    return (u.get("x"), u.get("y"), u.get("z"))


def sel(gc):
    return battle_state(gc).get("selectedId")


def es(gc, key):
    return event_state(gc).get(key)


def cam(gc):
    o = (es(gc, "camera") or {}).get("offset") or {}
    return (o.get("x"), o.get("y"), o.get("z"))


def cams(host, client):
    return {"host": cam(host), "client": cam(client)}


def click(gc, t, button="left"):
    """ONE map_tile_click; returns the answer's evidence fields (an error answer stays an answer)."""
    r = gc.cmd({"cmd": "map_tile_click", "x": t[0], "y": t[1], "z": t[2], "button": button})
    return {k: r.get(k) for k in ANS if k in r}


def clicked(a, centered=None):
    ok = a.get("ok") is True and a.get("verified") is True and a.get("clicked") is True
    return ok and (centered is None or a.get("centered") is centered)


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True, round(time.time() - t0, 2)
        time.sleep(interval)
    return bool(pred()), round(time.time() - t0, 2)


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def common(host, client, crash0):
    try:
        assert_hash_clean(host, client, full=True, what="common")
        hashed = "all buckets EQUAL"
    except AssertionError as e:
        hashed = str(e)[:400]
    ds = [es(host, "desyncSeen"), es(client, "desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash,
            f"common: hash {hashed}; desyncSeen host/client {ds} (want False/False); new crash files {crash} (want none)")


def verdict(row, order, cells, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    fails = 0
    for name in order:
        ok, detail = cells.get(name, (False, f"not reached: {ev.get('error')}"))
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)
    print(f"{row} {'PASS' if not fails else 'FAIL'} ({fails} of {len(order)} cells failed)", flush=True)
    return fails


def run_row(row, order, fn):
    """One row: `fn()` returns (cells, ev); an exception fails every cell it did not reach."""
    try:
        cells, ev = fn()
    except Exception as e:
        cells, ev = {}, {"error": f"{type(e).__name__}: {str(e)[:600]}"}
    return verdict(row, order, cells, ev)


def shut(*gcs):
    for gc in gcs:
        try:
            if gc is not None and gc.proc is not None and gc.proc.poll() is None:
                gc.shutdown()
        except Exception as e:
            print(f"[rvu2] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)


# ===================== boot K =====================


def boot(host, client):
    m = (host, client)
    guarded("K", lambda: HC.bring_up_lobby_roster_pinned(host, client, KEY), m)
    guarded("K", lambda: session.drive_to_battlescape(host, client, {}, mission=HC.MISSION, seat_count=2,
                                                      pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": HC.SEED_MAP})), m)

    def census():
        for gc in m:
            b = battle_state(gc)
            seats = [sorted(u["id"] for u in b["units"] if u.get("coop") == s and u.get("faction") == 0
                            and not u.get("isOut")) for s in (0, 1)]
            assert b.get("mapFingerprint") == HC.MAP_FP and seats == [HOST_SEAT, CLIENT_SEAT], (
                f"{gc.name} mapFingerprint {b.get('mapFingerprint')} (want {HC.MAP_FP}), seats {seats} "
                f"(want {[HOST_SEAT, CLIENT_SEAT]})")
    guarded("K", census, m)
    pinned = guarded("K", lambda: session.pin_ai_neutral(host, client, tag="rvu2"), m)
    if not pinned:
        capture("K", "pin_ai_neutral pinned no unit", m)
        raise Miss("K")
    guarded("K", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)

    def stage():
        session.place_deterministic(host, client, [{"lever": "battle_teleport_unit", "unit": H, "x": TILE_H[0],
                                                    "y": TILE_H[1], "z": TILE_H[2], "dir": DIR_TW}], what="rvu2 H")
        for uid, t in ((U, TILE_U), (C, TILE_C), (C2, TILE_C2)):
            place(host, client, uid, t, STAGE_DIR)
        for uid in (H, U, C, C2):
            set_tu_both(host, client, uid, HC.TU_MAX)
        session.wait_host_idle(host, client, timeout=STEP_S)
        got = {uid: [pos(host, uid), pos(client, uid)] for uid in (H, U, C, C2)}
        want = {uid: [t, t] for uid, t in ((H, TILE_H), (U, TILE_U), (C, TILE_C), (C2, TILE_C2))}
        assert got == want, f"staged positions host/client {got} (want {want})"
        assert_hash_clean(host, client, full=True, what="rvu2 staging")
        return got
    staged = guarded("K", stage, m)
    print(f"[rvu2] boot K ok: MAP_FP {HC.MAP_FP} seats {HOST_SEAT}/{CLIENT_SEAT} pinned {len(pinned)} staged {staged}",
          flush=True)


# ===================== rows =====================


def row_select(gc, actor, target_tile, want_sel, row, host, client, crash0):
    """K1 / K2: `gc` selects `actor` by TAB, then ONE map_tile_click on its own soldier's tile selects `want_sel`."""
    ev = {"tab": tab_select(gc, actor), "sel0": sel(gc), "arm0": es(gc, "coopWalkArmEntered"), "cam0": cams(host, client)}
    ev["answer"] = a = click(gc, target_tile)
    ok, ev["selS"] = wait_until(lambda: sel(gc) == want_sel, SEL_S)
    ev.update(sel1=sel(gc), arm1=es(gc, "coopWalkArmEntered"), cam1=cams(host, client))
    return {f"{row}-pre": (ev["sel0"] == actor, f"{gc.name} selectedId {ev['sel0']} (want {actor})"),
            f"{row}-click": (clicked(a), f"{gc.name} map_tile_click {target_tile}: {a} (want ok, verified, clicked)"),
            f"{row}-effect": (ok and ev["arm1"] == ev["arm0"],
                              f"{gc.name} selectedId {ev['sel1']} after {ev['selS']} s (want {want_sel} within {SEL_S} s); "
                              f"coopWalkArmEntered {ev['arm0']} -> {ev['arm1']} (want unchanged)"),
            f"{row}-common": common(host, client, crash0)}, ev


def row_k3(host, client, crash0):
    ev = {"tab": tab_select(client, C2), "sel0": sel(client), "arm0": es(client, "coopWalkArmEntered"),
          "blocked0": es(client, "coopLocalExecBlocked"), "cam0": cams(host, client)}
    ev["answer"] = a = click(client, TILE_H)
    ok, ev["bannerS"] = wait_until(lambda: battle_state(client).get("coopWaitText") == NOT_YOURS, SEL_S)
    ev.update(banner=battle_state(client).get("coopWaitText"), sel1=sel(client), arm1=es(client, "coopWalkArmEntered"),
              blocked1=es(client, "coopLocalExecBlocked"), cam1=cams(host, client))
    return {"K3-pre": (ev["sel0"] == C2, f"client selectedId {ev['sel0']} (want {C2})"),
            "K3-click": (clicked(a), f"client map_tile_click {TILE_H}: {a} (want ok, verified, clicked)"),
            "K3-effect": (ok and ev["sel1"] == C2 and ev["arm1"] == ev["arm0"] and ev["blocked1"] == ev["blocked0"],
                          f"client banner {ev['banner']!r} after {ev['bannerS']} s (want {NOT_YOURS!r} within {SEL_S} s); "
                          f"selectedId {ev['sel1']} (want {C2}); coopWalkArmEntered {ev['arm0']} -> {ev['arm1']}, "
                          f"coopLocalExecBlocked {ev['blocked0']} -> {ev['blocked1']} (want both unchanged)"),
            "K3-common": common(host, client, crash0)}, ev


def row_k4(host, client, crash0):
    ev = {"tab": tab_select(host, H), "sel0": sel(host), "Hdir": (live(host).get(H) or {}).get("direction")}
    r = session.place_deterministic(host, client, [{"lever": "battle_teleport_all", "faction": "hostile",
                                                    "corner": HOSTILE_CORNER, "facing": HOSTILE_FACING}],
                                    what="rvu2 K4 hostiles")
    hostiles = sorted((i, (u["x"], u["y"], u["z"])) for i, u in live(host).items() if u.get("faction") == 1)
    ev["hostiles"] = {"count": r[0][0].get("count"), "minCheb": min((min(cheb(p, TILE_H), cheb(p, T_W))
                                                                     for _, p in hostiles), default=None)}
    cc = host.cmd({"cmd": "battle_camera_center", "x": HC.K_FAR_TERROR[0], "y": HC.K_FAR_TERROR[1],
                   "z": HC.K_FAR_TERROR[2]})
    ev["center"] = {k: cc.get(k) for k in ("ok", "centerX", "centerY", "viewLevel", "error")}
    prev = ev["prev"] = session.walk_action_id(host)
    ev["cam0"] = cams(host, client)
    ev["answer"] = a = click(host, T_W)
    try:
        session.wait_walk_settled(host, client, prev, WALK_S)
        ev["settled"] = True
    except Exception as e:
        ev["settled"] = f"{type(e).__name__}: {str(e)[:200]}"
    hw, cw = session.last_walk(host), session.last_walk(client)
    tos = lambda w: [(s["to"]["x"], s["to"]["y"], s["to"]["z"]) for s in (w.get("steps") or [])]
    ev.update(hostWalk={"actionId": hw.get("actionId"), "unit": hw.get("unit"), "origin": hw.get("origin"),
                        "to": tos(hw), "halted": hw.get("halted"), "reason": hw.get("reason")},
              clientWalk={"actionId": cw.get("actionId"), "to": tos(cw)}, H=[pos(host, H), pos(client, H)],
              cam1=cams(host, client))
    hk, ck = ev["hostWalk"], ev["clientWalk"]
    pre_ok = (ev["sel0"] == H and cc.get("ok") is True and ev["Hdir"] == DIR_TW and hostiles
              and ev["hostiles"]["minCheb"] >= MIN_CHEB)
    return {"K4-pre": (pre_ok, f"host selectedId {ev['sel0']} (want {H}); battle_camera_center {ev['center']} (want ok); "
                               f"H facing {ev['Hdir']} (want {DIR_TW}); {len(hostiles)} live hostiles, min Chebyshev "
                               f"{ev['hostiles']['minCheb']} from H / T_W (want >= {MIN_CHEB})"),
            "K4-click": (clicked(a, centered=True),
                         f"host map_tile_click {T_W}: {a} (want ok, verified, clicked, centered true)"),
            "K4-effect": (ev["settled"] is True and hk["actionId"] not in (None, prev) and hk["unit"] == H
                          and hk["origin"] == "host" and hk["to"] == [T_W] and ck["actionId"] == hk["actionId"]
                          and ck["to"] == [T_W] and ev["H"] == [T_W, T_W],
                          f"settled {ev['settled']}; host lastWalk {hk} (want a new actionId, unit {H}, origin host, one "
                          f"step to {T_W}); client lastWalk {ck} (want the same actionId and step); H host/client "
                          f"{ev['H']} (want {T_W} on both)"),
            "K4-common": common(host, client, crash0)}, ev


def row_k5(host, client, crash0):
    ev = {"sel0": sel(host), "wa0": session.walk_action_id(host), "cam0": cams(host, client)}
    ev["answer"] = a = click(host, K5_TILE)
    time.sleep(1.0)
    ev.update(sel1=sel(host), wa1=session.walk_action_id(host), cam1=cams(host, client))
    return {"K5-click": (a.get("ok") is True and a.get("verified") is False and a.get("clicked") is False,
                         f"host map_tile_click {K5_TILE}: {a} (want ok true, verified false, clicked false)"),
            "K5-effect": ((ev["sel1"], ev["wa1"]) == (ev["sel0"], ev["wa0"]),
                          f"host selectedId {ev['sel0']} -> {ev['sel1']}, walk actionId {ev['wa0']} -> {ev['wa1']} after "
                          f"1.0 s (want both unchanged)"),
            "K5-common": common(host, client, crash0)}, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("rvu2_k_host"))
    client = GameClient("client", None, make_user_dir("rvu2_k_client"))
    crash0 = session._crash_log_snapshot()
    fails = 0
    try:
        try:
            boot(host, client)   # bring_up_lobby_roster_pinned spawns and connects both machines
        except Miss:
            fails = sum(verdict(row, order, {n: (False, "boot (FIXTURE-STOP, see the CAPTURE K line)") for n in order},
                                {"error": "boot"}) for row, order in ROWS)
        else:
            rows = dict(ROWS)
            fails += run_row("K1", rows["K1"], lambda: row_select(host, H, TILE_U, U, "K1", host, client, crash0))
            fails += run_row("K2", rows["K2"], lambda: row_select(client, C, TILE_C2, C2, "K2", host, client, crash0))
            fails += run_row("K3", rows["K3"], lambda: row_k3(host, client, crash0))
            fails += run_row("K4", rows["K4"], lambda: row_k4(host, client, crash0))
            fails += run_row("K5", rows["K5"], lambda: row_k5(host, client, crash0))
    finally:
        shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_tile_click: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
