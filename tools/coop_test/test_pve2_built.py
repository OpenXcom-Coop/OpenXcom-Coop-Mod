"""test_pve2_built.py: on a night PvE2 boot, the PvE2 aliens' unsaved construction-time fields - the dark-vision
distance and the maximum armor the host built them with - must be the same on the second player's machine and after a
document load, and at night the second player's alien must see an X-COM soldier the host's alien sees (when broken,
the fields differ and the second player's alien does not see the soldier).

Boot (key 48865): test_pve2's bring-up, its steps named as there (the PF lobby to gamemode 4, STR_MEDIUM_SCOUT,
SEED_ROSTER / SEED_MAP 1, both briefings and equip screens, pin_ai_neutral, reactions 0, both Turn 1 screens closed,
the stable settle at side 0 turn 2) with test_light_scope's battle.cfg darkness 15 written into the host's user dir
before it starts; step 9 checks the boot's pins, step 10 is night_precondition (globalShade 15 on both).
  built_fields  `battle_state` on both: every alien's armorCur (built_fields-cur, the saved value), darkVision
      (built_fields-dark) and armorMax (built_fields-armor) equal.
  record_reload  `battle_state {reloadProbe: true}` on both: the host's reload of each alien's own record equals its
      live darkVision / armorMax (record_reload-equal).
  night_sight  C1 (1000000, the client's seat) to C1_TILE facing C1_DIR, X (8, an AI-side X-COM soldier) to X_TILE
      (light_recompute on both after each teleport), the client's turn intents C1 -> C1_DIR + 1 -> C1_DIR: X's tile
      dark and every alien >= 10 tiles from X (night_sight-pre), X in the host's list(C1) and visible there
      (night_sight-host), visible here on the client (night_sight-here) and in its list(C1) (night_sight-list).
Common cell after each row: every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.
Without the fix: built_fields-dark, built_fields-armor (difficulty 0: armor multiplier 0.5), record_reload-equal,
night_sight-here and night_sight-list fail; every other cell passes.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A
boot step past its bound prints ONE CAPTURE boot line and fails every cell "boot"; a staging step past its bound fails
night_sight's cells "staging". run in the foreground to completion. ONE run is the result, no skip path; exit 0 only
when every cell passes, else 2.

Run:  python tools/coop_test/test_pve2_built.py
"""

import contextlib
import io
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import pvp_fixture as PF  # noqa: E402
from test_delta_core import both, tele_both  # noqa: E402
import test_light_scope as LS  # noqa: E402
import test_client_alien_sight as CAS  # noqa: E402  (the per-GameClient lock and the client turn-intent helper)
import test_pve2 as PVE  # noqa: E402
from test_battle_end_rules import wait_until  # noqa: E402
from test_pvp_gm3 import (Miss, stack, top, log_count, capture, guarded, reactions_zero, common, run_row,  # noqa: E402
                             fail_all, shut)

KEY = "48865"                     # this file's lobby key
DARKNESS = 15                     # battle.cfg darkness; test_light_scope writes it
SEED_ROSTER, SEED_MAP = 1, 1
MISSION = "STR_MEDIUM_SCOUT"
GAMEMODE_PVE2 = 4
MAP_FP = 7.136941435423656e+17    # both machines, day and night
DIFFICULTY = 0                    # the host's battle.cfg after newbattle_ok (xcom1 armor multiplier 0.5)
ALIEN_IDS = [1000000, 1000001, 1000002, 1000003, 1000004]   # 3 STR_SECTOID_SOLDIER, 2 STR_SECTOID_NAVIGATOR
SEAT1_IDS = [1000000, 1000001]
SEAT0_IDS = [1000002, 1000003, 1000004]
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]
C1_ID, C1_TILE, C1_DIR, C1_TU = 1000000, (24, 9, 0), 6, 54   # test_pve2's C1 tile (27, 11, 0) is walled in
X_ID, X_TILE = 8, (11, 9, 0)      # the first candidate from C1_TILE: 13 tiles west, dark, >= 13 from every other alien
DARK_MIN_SHADE = 10               # a tile is dark when its shade (15 - its brightest light layer) > 9 (Mod maxDarknessToSeeUnits)
STEP_S = 30                       # each staging / order step's bound
BOOT_S = 60                       # each briefing wait and the stable settle
ROWS = (("built_fields", ("built_fields-cur", "built_fields-dark", "built_fields-armor", "built_fields-common")),
        ("record_reload", ("record_reload-equal", "record_reload-common")),
        ("night_sight",
         ("night_sight-pre", "night_sight-host", "night_sight-here", "night_sight-list", "night_sight-common")))


def bs(gc, reload=False):
    return gc.cmd({"cmd": "battle_state", "reloadProbe": True} if reload else {"cmd": "battle_state"})


def ub(b):
    return {u["id"]: u for u in b.get("units", [])}


def p3(u):
    return (u.get("x"), u.get("y"), u.get("z"))


def rnd(x):
    return int(math.floor(x + 0.5))


def cfg_line(gc, key):
    try:
        with open(os.path.join(gc.user_dir, "xcom1", "battle.cfg"), encoding="utf-8", errors="replace") as f:
            return next((ln.strip() for ln in f if ln.startswith(key + ":")), f"no {key} key")
    except OSError as e:
        return f"unreadable: {e}"


def miss(err, machines):
    capture("boot", err, machines)
    raise Miss("boot")


# ========== the night PvE2 bring-up (test_pve2.bring_up, this file's key, no Alien Bleeding option sequence) ==========


def bring_up(host, client):
    m, boot = (host, client), {}
    boot["nightCfg"] = LS.write_night_cfg(host.user_dir)
    guarded("boot", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    guarded("boot", lambda: host.ok({"cmd": "set_seed", "seed": SEED_ROSTER}), m)
    boot["gm2"] = guarded("boot", lambda: PF.start_pvp_skirmish_lobby(host, client, KEY, alien_player="client"), m)[0]
    row = guarded("boot", lambda: PF.row_for(host, "HostPlayer"), m)
    boot["lobbyGamemode"] = guarded("boot", lambda: host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"}),
                                    m).get("gamemode")
    ok, secs = wait_until(lambda: PF._lobby(host).get("playerTeams") == ["Alien", "Alien"]
                          and PF._lobby(client).get("playerTeams") == ["Alien", "Alien"], 10, 0.25)
    if not ok:
        miss(f"step 3: both lobby rows Alien not shown in {secs} s", m)
    guarded("boot", lambda: host.ok({"cmd": "lobby_action"}), m)
    guarded("boot", lambda: host.wait_for("host at battle settings",
                                       lambda: (not session.has_state(host, "LobbyMenu")) or None), m)
    if top(host) != "NewBattleState":
        miss(f"step 4: host stack {stack(host)} (want NewBattleState on top)", m)
    guarded("boot", lambda: host.ok({"cmd": "newbattle_mission", "type": MISSION}), m)
    guarded("boot", lambda: host.ok({"cmd": "set_seed", "seed": SEED_MAP}), m)
    guarded("boot", lambda: host.ok({"cmd": "newbattle_ok"}), m)
    boot["difficulty"], boot["darkness"] = cfg_line(host, "difficulty"), cfg_line(host, "darkness")
    for gc in m:
        ok, secs = wait_until(lambda gc=gc: session.has_state(gc, "BriefingState")
                              or log_count(host, PVE.N_REFUSE_RX) > 0, BOOT_S, 0.1)
        if not ok or log_count(host, PVE.N_REFUSE_RX) > 0:
            miss(f"step 5: {gc.name} BriefingState {ok} after {secs} s; host refusal lines "
                 f"{log_count(host, PVE.N_REFUSE_RX)}", m)
    guarded("boot", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)
    guarded("boot", lambda: session.dismiss_client_briefing(client), m)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            session.equip_both_ready(host, client)
    except Exception as e:
        print(buf.getvalue(), end="", flush=True)
        miss(f"step 6: equip_both_ready: {type(e).__name__}: {str(e)[:500]}", m)
    boot["pinned"] = guarded("boot", lambda: session.pin_ai_neutral(host, client, tag="pve2_built"), m)
    guarded("boot", lambda: reactions_zero(host, client), m)
    guarded("boot", lambda: session.dismiss_battle_start_overlays(client), m)
    guarded("boot", lambda: session.dismiss_battle_start_overlays(host), m)
    boot["settle"] = PVE.settle(host, client)   # its own CAPTURE line and Miss on a missed settle
    hb, cb = bs(host), bs(client)
    pins = {"equal": log_count(host, PVE.N_EQUAL), "mismatch": log_count(host, PVE.N_MISMATCH),
            "mode": [hb.get("coopGamemode"), cb.get("coopGamemode")], "map": [hb.get("mapFingerprint"), cb.get("mapFingerprint")],
            "ids": [sorted(ub(hb)), sorted(ub(cb))]}
    if (pins["equal"], pins["mismatch"], pins["mode"], pins["map"]) != (1, 0, [GAMEMODE_PVE2] * 2, [MAP_FP] * 2) \
            or pins["ids"] != [sorted(ALIEN_IDS + XCOM_IDS)] * 2:
        miss(f"step 9: pins {pins} (want saveBlob EQUAL 1 / MISMATCH 0, gamemode 4, MAP_FP {MAP_FP}, ids "
             f"{sorted(ALIEN_IDS + XCOM_IDS)})", m)
    nerr = LS.night_precondition(host, client)
    if nerr:
        miss(f"step 10: {nerr}", m)
    boot["pins"] = pins
    return boot, session._crash_log_snapshot()


# ===================== the rows =====================


def row_built_fields(host, client, boot, crash0):
    uh, uc = ub(bs(host)), ub(bs(client))

    def per(key):
        return {i: [uh[i].get(key), uc[i].get(key)] for i in ALIEN_IDS}

    cur, dark, mx = per("armorCur"), per("darkVision"), per("armorMax")
    off = {k: {i: v for i, v in t.items() if v[0] != v[1] or v[0] is None} for k, t in
           (("cur", cur), ("dark", dark), ("max", mx))}
    ev = {"difficulty": boot["difficulty"], "darkness": boot["darkness"], "settle": boot["settle"], "pinned": boot["pinned"],
          "aliens": {i: {"host": [uh[i].get(k) for k in ("type", "darkVision", "armorMax", "armorCur", "pickUpActively")],
                         "client": [uc[i].get(k) for k in ("type", "darkVision", "armorMax", "armorCur", "pickUpActively")]}
                     for i in ALIEN_IDS},
          "xcomDark": {i: [uh[i].get("darkVision"), uc[i].get("darkVision")] for i in XCOM_IDS}}
    return {"built_fields-cur": (not off["cur"],
                                 f"armorCur host/client differing or absent {off['cur']} (want none; the saved value)"),
            "built_fields-dark": (not off["dark"],
                                  f"darkVision host/client differing {off['dark']} (want every alien equal on both)"),
            "built_fields-armor": (not off["max"],
                                   f"armorMax host/client differing {off['max']} (want every alien equal on both; "
                                   f"host {boot['difficulty']})"),
            "built_fields-common": common(host, client, crash0)}, ev


def row_record_reload(host, client, crash0):
    uh, uc = ub(bs(host, True)), ub(bs(client, True))
    keys = ("darkVision", "armorMax", "reloadDarkVision", "reloadArmorMax", "reloadArmorCur")
    off = {i: [uh[i].get(k) for k in keys] for i in ALIEN_IDS
           if "reloadDarkVision" not in uh[i] or (uh[i].get("reloadDarkVision"), uh[i].get("reloadArmorMax"))
           != (uh[i].get("darkVision"), uh[i].get("armorMax"))}
    ev = {"keys": keys, "host": {i: [uh[i].get(k) for k in keys] for i in ALIEN_IDS},
          "client": {i: [uc[i].get(k) for k in keys] for i in ALIEN_IDS}}
    return {"record_reload-equal": (not off,
                                    f"host aliens whose reload differs from the live value [darkVision, armorMax, "
                                    f"reloadDarkVision, reloadArmorMax, reloadArmorCur] {off} (want none)"),
            "record_reload-common": common(host, client, crash0)}, ev


def light(host, client, tiles):
    ch, cc = LS.census(host, "night_sight_host"), LS.census(client, "night_sight_client")
    return {t: [LS.tile_light(ch, t), LS.tile_light(cc, t)] for t in tiles}, LS.census_mismatch(ch, cc)


def stage_night_sight(host, client, ev):
    """C1 to C1_TILE facing C1_DIR (TU C1_TU), X to X_TILE (its facing kept); light_recompute on both after each teleport."""
    m = (host, client)
    ev["c1"] = guarded("staging", lambda: tele_both(host, client, C1_ID, C1_TILE, C1_DIR).get("to"), m)
    guarded("staging", lambda: both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": C1_ID,
                                                      "stat": "tu", "value": C1_TU, "refill": True}, ("tu",)), m)
    ev["rc1"] = [client.cmd({"cmd": "light_recompute"}).get("ok"), host.cmd({"cmd": "light_recompute"}).get("ok")]
    xd = ub(bs(host))[X_ID].get("direction")
    ev["x"] = guarded("staging", lambda: tele_both(host, client, X_ID, X_TILE, xd).get("to"), m)
    ev["rc2"] = [client.cmd({"cmd": "light_recompute"}).get("ok"), host.cmd({"cmd": "light_recompute"}).get("ok")]
    guarded("staging", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    uh, uc = ub(bs(host)), ub(bs(client))
    at = [p3(uh[C1_ID]), uh[C1_ID].get("direction"), p3(uc[C1_ID]), uc[C1_ID].get("direction"), p3(uh[X_ID]), p3(uc[X_ID])]
    if at != [C1_TILE, C1_DIR, C1_TILE, C1_DIR, X_TILE, X_TILE] or not all(ev["rc1"] + ev["rc2"]):
        capture("staging", f"C1 / X host / client {at}, light_recompute {ev['rc1']} {ev['rc2']}", m)
        raise Miss("staging")


def row_night_sight(host, client, staged, crash0):
    ev = dict(staged)
    lt, mm = light(host, client, [X_TILE, C1_TILE])
    uh = ub(bs(host))
    adist = {i: rnd(math.hypot(p3(uh[i])[0] - X_TILE[0], p3(uh[i])[1] - X_TILE[1])) for i in ALIEN_IDS}
    shade = [max(0, 15 - max(v)) for v in lt[X_TILE]]
    s0 = CAS.snap(host, client)
    ra, sa = CAS.client_turn(host, client, C1_ID, (C1_DIR + 1) % 8)
    rb, s1 = CAS.client_turn(host, client, C1_ID, C1_DIR)
    hl, cl = CAS.ua(s1["h"], C1_ID).get("sees") or [], CAS.ua(s1["c"], C1_ID).get("sees") or []
    hv, here_c = CAS.ua(s1["h"], X_ID).get("vis"), CAS.ua(s1["c"], X_ID).get("here")
    dirs = [CAS.ua(s1["h"], C1_ID).get("dir"), CAS.ua(s1["c"], C1_ID).get("dir")]
    ev.update(light={f"{t[0]},{t[1]},{t[2]}": v for t, v in lt.items()}, censusMismatch=mm, shade=shade, alienDist=adist,
              c1Dark=[uh[C1_ID].get("darkVision"), ub(bs(client))[C1_ID].get("darkVision")],
              distance=round(math.hypot(C1_TILE[0] - X_TILE[0], C1_TILE[1] - X_TILE[1]), 3), turns=[ra, rb],
              before={"host": CAS.ua(s0["h"], C1_ID).get("sees"), "client": CAS.ua(s0["c"], C1_ID).get("sees")},
              away={"host": CAS.ua(sa["h"], C1_ID).get("sees"), "client": CAS.ua(sa["c"], C1_ID).get("sees")},
              dirs=dirs, visHere={"host": [hv, CAS.ua(s1["h"], X_ID).get("here")],
                                  "client": [CAS.ua(s1["c"], X_ID).get("vis"), here_c]})
    return {"night_sight-pre": (
                all(s >= DARK_MIN_SHADE for s in shade) and not mm and all(d >= 10 for d in adist.values())
                and dirs == [C1_DIR, C1_DIR],
                f"X's tile shade host/client {shade} (want > 9 on both); census mismatch {mm} (want none); "
                f"Round(distance) alien -> X {adist} (want every >= 10); C1 facing host/client {dirs} (want {C1_DIR})"),
            "night_sight-host": (X_ID in hl and hv is True,
                                 f"host list(C1) {hl}, vis(host, X) {hv} (precondition: X in it, True)"),
            "night_sight-here": (here_c is True, f"here(client, X) {here_c} (want True)"),
            "night_sight-list": (X_ID in cl, f"client list(C1) {cl} (want {X_ID} in it)"),
            "night_sight-common": common(host, client, crash0)}, ev


def run_boot():
    host = GameClient("host", None, make_user_dir("pve2_built_host"))
    client = GameClient("client", None, make_user_dir("pve2_built_client"))
    try:
        try:
            boot, crash0 = bring_up(host, client)
        except Miss:
            return fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        rows = dict(ROWS)
        fails = run_row("built_fields", rows["built_fields"], lambda: row_built_fields(host, client, boot, crash0))
        fails += run_row("record_reload", rows["record_reload"], lambda: row_record_reload(host, client, crash0))
        staged = {}
        try:
            stage_night_sight(host, client, staged)
        except Miss:
            staged = None
        fails += (run_row("night_sight", rows["night_sight"],
                          lambda: row_night_sight(host, client, staged, crash0)) if staged is not None
                  else fail_all((("night_sight", rows["night_sight"]),), "staging (see the CAPTURE staging line)"))
        return fails
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pve2_built: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
