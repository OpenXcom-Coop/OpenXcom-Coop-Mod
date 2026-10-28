"""R5-U8b (CAP-2) rows B1, B3, B2 (night PvE2 boot): the PvE2 aliens' unsaved construction-time fields - the dark-vision distance
and the maximum armor the host built them with - differ on the second player's machine and after a document load, and at night the
second player's alien does not see an X-COM soldier the host's alien sees.

Spec: docs repo rewrite/prompts/w2h35c_r5u8b_captures.md (f) test_pve2_built.py, with ruling R-CAP2-1 RN-1 (B2's C1 tile). Constants:
rewrite/r5u8bf-task0/CONSTANTS.md (TASK 0 boots Pp / Pa / Pb, Pc / Pd on the base + TP1 build). TASK 0 verdicts: B1 CONFIRMED, B3
CONFIRMED, B2 CONFIRMED (after R-CAP2-1: C1 on (24, 9, 0) facing 6, X on (11, 9, 0)), B4 CONFIRMED (test_pve2_armor_mod.py).

Boot (key 48865): test_pve2's bring-up (the PF lobby to gamemode 4, STR_MEDIUM_SCOUT, SEED_ROSTER / SEED_MAP 1, both briefings and
equip screens, pin_ai_neutral, reactions 0, both Turn 1 screens closed, the stable settle at side 0 turn 2) with test_light_scope's
battle.cfg darkness 15 written into the host's user dir before it starts, then night_precondition (globalShade 15 on both).
  B1  `battle_state` on both: every alien's armorCur (B1-cur, the saved value), darkVision (B1-dark) and armorMax (B1-armor) equal.
  B3  `battle_state {reloadProbe: true}` (TP1) on both: the host's reload of each alien's own record equals its live darkVision /
      armorMax (B3-reload).
  B2  C1 (1000000, the client's seat) to C1_TILE facing C1_DIR, X (8, an AI-side X-COM soldier) to X_TILE (light_recompute on both
      after each teleport), the client's turn intents C1 -> C1_DIR + 1 -> C1_DIR: X's tile dark and every alien >= 10 tiles from X
      (B2-pre), X in the host's list(C1) and visible there (B2-host), visible here on the client (B2-here) and in its list(C1) (B2-list).
Common cell after each row: every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.
RED at 2R: B1-dark, B1-armor (difficulty 0: armor multiplier 0.5), B3-reload, B2-here, B2-list; every other cell PASS.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its
bound prints ONE CAPTURE B line and fails every cell "boot"; a staging step past its bound fails B2's cells "staging". run in the
foreground to completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

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

KEY = "48865"                     # this file's lobby key (spec (G))
DARKNESS = 15                     # battle.cfg darkness; test_light_scope writes it
SEED_ROSTER, SEED_MAP = 1, 1
MISSION = "STR_MEDIUM_SCOUT"
GAMEMODE_PVE2 = 4
MAP_FP = 7.136941435423656e+17    # both machines, day and night (Pp / Pa / Pb / Pc / Pd)
DIFFICULTY = 0                    # the host's battle.cfg after newbattle_ok (P-8; xcom1 armor multiplier 0.5)
ALIEN_IDS = [1000000, 1000001, 1000002, 1000003, 1000004]   # 3 STR_SECTOID_SOLDIER, 2 STR_SECTOID_NAVIGATOR
SEAT1_IDS = [1000000, 1000001]
SEAT0_IDS = [1000002, 1000003, 1000004]
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]
C1_ID, C1_TILE, C1_DIR, C1_TU = 1000000, (24, 9, 0), 6, 54   # R-CAP2-1 RN-1 (Pc / Pd; the spec's (27, 11, 0) is walled in)
X_ID, X_TILE = 8, (11, 9, 0)      # the B2 rule's first candidate from C1_TILE (13 tiles west, dark, >= 13 from every other alien)
DARK_MIN_SHADE = 10               # a tile is dark when its shade (15 - its brightest light layer) > 9 (Mod maxDarknessToSeeUnits)
STEP_S = 30                       # each staging / order step's bound
BOOT_S = 60                       # each briefing wait and the stable settle
ROWS = (("B1", ("B1-cur", "B1-dark", "B1-armor", "B1-common")), ("B3", ("B3-reload", "B3-common")),
        ("B2", ("B2-pre", "B2-host", "B2-here", "B2-list", "B2-common")))


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
    capture("B", err, machines)
    raise Miss("B")


# ===================== the night PvE2 bring-up (test_pve2.bring_up, this file's key; no A1-bleed phases) =====================


def bring_up(host, client):
    m, boot = (host, client), {}
    boot["nightCfg"] = LS.write_night_cfg(host.user_dir)
    guarded("B", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    guarded("B", lambda: host.ok({"cmd": "set_seed", "seed": SEED_ROSTER}), m)
    boot["gm2"] = guarded("B", lambda: PF.start_pvp_skirmish_lobby(host, client, KEY, alien_player="client"), m)[0]
    row = guarded("B", lambda: PF.row_for(host, "HostPlayer"), m)
    boot["lobbyGamemode"] = guarded("B", lambda: host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"}),
                                    m).get("gamemode")
    ok, secs = wait_until(lambda: PF._lobby(host).get("playerTeams") == ["Alien", "Alien"]
                          and PF._lobby(client).get("playerTeams") == ["Alien", "Alien"], 10, 0.25)
    if not ok:
        miss(f"step 3: both lobby rows Alien not shown in {secs} s", m)
    guarded("B", lambda: host.ok({"cmd": "lobby_action"}), m)
    guarded("B", lambda: host.wait_for("host at battle settings",
                                       lambda: (not session.has_state(host, "LobbyMenu")) or None), m)
    if top(host) != "NewBattleState":
        miss(f"step 4: host stack {stack(host)} (want NewBattleState on top)", m)
    guarded("B", lambda: host.ok({"cmd": "newbattle_mission", "type": MISSION}), m)
    guarded("B", lambda: host.ok({"cmd": "set_seed", "seed": SEED_MAP}), m)
    guarded("B", lambda: host.ok({"cmd": "newbattle_ok"}), m)
    boot["difficulty"], boot["darkness"] = cfg_line(host, "difficulty"), cfg_line(host, "darkness")
    for gc in m:
        ok, secs = wait_until(lambda gc=gc: session.has_state(gc, "BriefingState")
                              or log_count(host, PVE.N_REFUSE_RX) > 0, BOOT_S, 0.1)
        if not ok or log_count(host, PVE.N_REFUSE_RX) > 0:
            miss(f"step 5: {gc.name} BriefingState {ok} after {secs} s; host refusal lines "
                 f"{log_count(host, PVE.N_REFUSE_RX)}", m)
    guarded("B", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)
    guarded("B", lambda: session.dismiss_client_briefing(client), m)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            session.equip_both_ready(host, client)
    except Exception as e:
        print(buf.getvalue(), end="", flush=True)
        miss(f"step 6: equip_both_ready: {type(e).__name__}: {str(e)[:500]}", m)
    boot["pinned"] = guarded("B", lambda: session.pin_ai_neutral(host, client, tag="r5u8bf"), m)
    guarded("B", lambda: reactions_zero(host, client), m)
    guarded("B", lambda: session.dismiss_battle_start_overlays(client), m)
    guarded("B", lambda: session.dismiss_battle_start_overlays(host), m)
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


def row_b1(host, client, boot, crash0):
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
    return {"B1-cur": (not off["cur"], f"armorCur host/client differing or absent {off['cur']} (want none; the saved value)"),
            "B1-dark": (not off["dark"], f"darkVision host/client differing {off['dark']} (want every alien equal on both)"),
            "B1-armor": (not off["max"], f"armorMax host/client differing {off['max']} (want every alien equal on both; "
                                         f"host {boot['difficulty']})"),
            "B1-common": common(host, client, crash0)}, ev


def row_b3(host, client, crash0):
    uh, uc = ub(bs(host, True)), ub(bs(client, True))
    keys = ("darkVision", "armorMax", "reloadDarkVision", "reloadArmorMax", "reloadArmorCur")
    off = {i: [uh[i].get(k) for k in keys] for i in ALIEN_IDS
           if "reloadDarkVision" not in uh[i] or (uh[i].get("reloadDarkVision"), uh[i].get("reloadArmorMax"))
           != (uh[i].get("darkVision"), uh[i].get("armorMax"))}
    ev = {"keys": keys, "host": {i: [uh[i].get(k) for k in keys] for i in ALIEN_IDS},
          "client": {i: [uc[i].get(k) for k in keys] for i in ALIEN_IDS}}
    return {"B3-reload": (not off, f"host aliens whose reload differs from the live value [darkVision, armorMax, "
                                   f"reloadDarkVision, reloadArmorMax, reloadArmorCur] {off} (want none)"),
            "B3-common": common(host, client, crash0)}, ev


def light(host, client, tiles):
    ch, cc = LS.census(host, "r5u8bf_b2_h"), LS.census(client, "r5u8bf_b2_c")
    return {t: [LS.tile_light(ch, t), LS.tile_light(cc, t)] for t in tiles}, LS.census_mismatch(ch, cc)


def stage_b2(host, client, ev):
    """C1 to C1_TILE facing C1_DIR (TU C1_TU), X to X_TILE (its facing kept); light_recompute on both after each teleport."""
    m = (host, client)
    ev["c1"] = guarded("B2 staging", lambda: tele_both(host, client, C1_ID, C1_TILE, C1_DIR).get("to"), m)
    guarded("B2 staging", lambda: both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": C1_ID,
                                                      "stat": "tu", "value": C1_TU, "refill": True}, ("tu",)), m)
    ev["rc1"] = [client.cmd({"cmd": "light_recompute"}).get("ok"), host.cmd({"cmd": "light_recompute"}).get("ok")]
    xd = ub(bs(host))[X_ID].get("direction")
    ev["x"] = guarded("B2 staging", lambda: tele_both(host, client, X_ID, X_TILE, xd).get("to"), m)
    ev["rc2"] = [client.cmd({"cmd": "light_recompute"}).get("ok"), host.cmd({"cmd": "light_recompute"}).get("ok")]
    guarded("B2 staging", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    uh, uc = ub(bs(host)), ub(bs(client))
    at = [p3(uh[C1_ID]), uh[C1_ID].get("direction"), p3(uc[C1_ID]), uc[C1_ID].get("direction"), p3(uh[X_ID]), p3(uc[X_ID])]
    if at != [C1_TILE, C1_DIR, C1_TILE, C1_DIR, X_TILE, X_TILE] or not all(ev["rc1"] + ev["rc2"]):
        capture("B2 staging", f"C1 / X host / client {at}, light_recompute {ev['rc1']} {ev['rc2']}", m)
        raise Miss("B2 staging")


def row_b2(host, client, staged, crash0):
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
    return {"B2-pre": (all(s >= DARK_MIN_SHADE for s in shade) and not mm and all(d >= 10 for d in adist.values())
                       and dirs == [C1_DIR, C1_DIR],
                       f"X's tile shade host/client {shade} (want > 9 on both); census mismatch {mm} (want none); "
                       f"Round(distance) alien -> X {adist} (want every >= 10); C1 facing host/client {dirs} (want {C1_DIR})"),
            "B2-host": (X_ID in hl and hv is True, f"host list(C1) {hl}, vis(host, X) {hv} (precondition: X in it, True)"),
            "B2-here": (here_c is True, f"here(client, X) {here_c} (want True)"),
            "B2-list": (X_ID in cl, f"client list(C1) {cl} (want {X_ID} in it)"),
            "B2-common": common(host, client, crash0)}, ev


def boot_b():
    host = GameClient("host", None, make_user_dir("r5u8bf_n_host"))
    client = GameClient("client", None, make_user_dir("r5u8bf_n_client"))
    try:
        try:
            boot, crash0 = bring_up(host, client)
        except Miss:
            return fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE B line)")
        rows = dict(ROWS)
        fails = run_row("B1", rows["B1"], lambda: row_b1(host, client, boot, crash0))
        fails += run_row("B3", rows["B3"], lambda: row_b3(host, client, crash0))
        staged = {}
        try:
            stage_b2(host, client, staged)
        except Miss:
            staged = None
        fails += (run_row("B2", rows["B2"], lambda: row_b2(host, client, staged, crash0)) if staged is not None
                  else fail_all((("B2", rows["B2"]),), "staging (see the CAPTURE B2 staging line)"))
        return fails
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = boot_b()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pve2_built: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
