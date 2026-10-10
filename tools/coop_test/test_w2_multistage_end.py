"""MG-A S-A2 - test_w2_multistage_end.py: a co-op stage change through the abort route, and a final stage that ends
with both debriefs (owner D158 (a), D226 (a), D156 (a); spec docs rewrite/prompts/mga_multistage_handoff.md (f) rows
MS2 and MS3 as AMENDMENT MG-A-1 section 5 restates them for stage S-A2, Q5 (a), Q6 (a), QA2; TASK 0 constants docs
rewrite/mga-task0/a2/CONSTANTS.md).

TWO boots, one per row, each shut down before the next:

  MS2  the abort route, a partner soldier left behind (boot B, lobby PORT_B): the classic skirmish on the stock
       Cydonia landing (STR_MARS_CYDONIA_LANDING), set_seed SEED_B right before newbattle_ok, MAP_FP_B pinned,
       pin_ai_neutral, hash clean. tile_census (one z level per call) reads the floor special type of every tile on
       both machines: the END_POINT (13) tiles are the pinned EXIT_TILES_B (QA2; the exit area is END_POINT, never the
       craft's START_POINT, F9821). battle_teleport_unit (client soldiers first, each applied to the client, then
       the host) puts C1 (8) and the five host soldiers on EXIT_TARGETS_B; C2 (9) stays on its spawn, a START_POINT
       tile. Hash clean. The host presses ABORT (battle_action abort), confirms AbortMissionState and the partner votes
       YES (R4-L1; the pass runs setAborted(true) + finishBattle(true, 6) -> vanilla's next-stage branch). Entry cells as
       MS1: the client shows the stage-2 BriefingState within ENTRY_S of the host's confirm, its missionType is
       STR_MARS_THE_FINAL_ASSAULT, the client's `stage` record applied 1, the host's emitted 1 (read right after the
       confirm). Then the stage-2 spine (session.briefings_to_battlescape) and the green cells: the host's record
       aborted true and inExitArea IN_EXIT_B (the soldiers on the exit; MS1 owns the record's other keys); both
       turn 1 on STR_MARS_THE_FINAL_ASSAULT; the living X-COM ids are STAGE2_LIVING_B on both (C2 9 is not among
       them, C1 8 is; owner V3), seat tags kept; hash_now full all buckets EQUAL; desyncSeen false on both; the
       host is alive; no new crash file.
  MS3  the final stage ends with both debriefs (boot C, lobby PORT_C, the test mod Coop_MultiStage_Test on both
       machines; Q5 (a)): STR_COOP_MULTISTAGE_TEST (stage 1, one alien) -> STR_COOP_MULTISTAGE_TEST_P2 (stage 2, one
       alien, no cutscene, no objective). set_seed SEED_C, MAP_FP_C, pin_ai_neutral, hash clean; both logs name the
       mod active (no invalid-mod line) and derive the stage-1 deployment. Kill-all (as MS1) -> the stage-entry cells
       with missionType STR_COOP_MULTISTAGE_TEST_P2 -> the stage-2 spine -> both turn 1 on _P2, mapSizeXYZ
       STAGE2_TILES, hash clean -> kill-all again -> the host's battle_end (W2-P7): host record emitted 1, reason
       aliensDown, aborted false; the client's applied 1 with the host's seq, resultReceived 1, debriefDisplayOnly 1;
       the host's DebriefingState (shown, on top, not display-only) and the client's display-only DebriefingState
       with the host's seven content fields (W2-P7 S-B1 cells) -> the client presses OK, then the host (D156 (a), the
       W2-P7 E3 order): each OK handled by DebriefingState and each machine reaches the main menu.

RED on S-A2's commit 1 (S-A1's red base: no stage writer; TASK 0 T0-7 / the red pre-walks measured on this build):
each row fails exactly its four stage-entry cells (no client stage-2 briefing within ENTRY_S, client missionType not
the stage-2 mission, client stage.applied 0, host stage.emitted 0); every pre-stage cell passes. The host dies after
the stage change (F5081: died at 16 / 25 / 29 s on MS2's shape, 2 s on MS3's), so host liveness and crash files are
EVIDENCE only until stage 2 is reached; the host's event_state read itself can fault on the freed stage-1 screen
(F10010). battle_state is never probed unless a BattlescapeState is on that machine's stack (F9920).

Each row prints ONE "EVIDENCE <id>:" line before its verdict, then "PASS <id>" or "FAIL <id>: <cells>" and, on a
FAIL, ONE "CAPTURE <id>:" line (both machines' event_state, battle_state, stack and log tail). A bring-up step past
its bound fails the row `boot` with one CAPTURE line. Every row runs after a failure. WV-D95 / WV-D99 / WV-D100: ONE
foreground run, no skip path; exit 0 only when both rows pass, 2 otherwise.

Run:  python tools/coop_test/test_w2_multistage_end.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_w2_multistage import (FixtureMiss, short, rc, stack, has_bstate, eview, evidence, capture, wait_until, step,
                                run_spine, ENTRY_S, IDLE_S, FACTION_PLAYER, FACTION_HOSTILE)
from test_w2_battle_end import (debrief_view, press_ok, left_menu, DEBRIEF_FIELDS, DEBRIEF_S, CLIENT_LEAVE_S,
                                OK_LEAVE_S)

MISSION_LANDING, MISSION_FINAL = "STR_MARS_CYDONIA_LANDING", "STR_MARS_THE_FINAL_ASSAULT"
SEATS = {8: 1, 9: 1, 10: 0, 11: 0, 12: 0, 13: 0, 14: 0}   # X-COM id -> coop seat at bring-up (T0-4, both boots)
END_POINT = 13                                             # src/Mod/MapData.h enum SpecialTileType

# ----- boot B (MS2; TASK 0 T0-4 / T0-7: SEED_B 1, fingerprint 4/4, END_POINT list 3/3, targets 3/3) -----
PORT_B, GC_B = "48572", (49676, 49677)
SEED_B = 1
MAP_FP_B = 2.509715288832488e+18
MAP_B_XYZ = (50, 50, 4)
ALIENS_B = list(range(1000000, 1000012))
EXIT_TILES_B = [(x, y, 0) for y in range(32, 38) for x in range(22, 28)]   # the 36 END_POINT tiles, census order
C1, C2 = 8, 9                                              # the client's soldiers: C1 to the exit, C2 left behind
EXIT_TARGETS_B = [(8, (22, 32, 0)), (10, (23, 32, 0)), (11, (24, 32, 0)), (12, (25, 32, 0)), (13, (26, 32, 0)),
                  (14, (27, 32, 0))]
IN_EXIT_B = 6
STAGE2_LIVING_B = {u: SEATS[u] for u, _ in EXIT_TARGETS_B}  # {8: 1, 10..14: 0}

# ----- boot C (MS3; TASK 0 T0-1m / T0-2m / T0-4: SEED_C 1, fingerprint 4/4) -----
MOD_NAME = "Coop_MultiStage_Test"
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_MultiStage_Test v1.0"
MISSION_C1, MISSION_C2 = "STR_COOP_MULTISTAGE_TEST", "STR_COOP_MULTISTAGE_TEST_P2"
DEPLOYMENT_LINE = 'BriefingState deployment: VANILLA "STR_COOP_MULTISTAGE_TEST"'
PORT_C, GC_C = "48573", (49678, 49679)
SEED_C = 1
MAP_FP_C = 2.509715288832488e+18
ALIENS_C = [1000000]
STAGE2_TILES = 7200                                        # 60x60x2 (T0-2m, 3/3)


def bview(gc):
    """battle_state, only while a BattlescapeState is on the stack (F9920)."""
    st = stack(gc)
    if not has_bstate(st):
        return {"skipped": f"no BattlescapeState on the stack (F9920): {st}"}
    b = battle_state(gc)
    units = b.get("units") or []
    xcom = [u for u in units if u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
    return {"missionType": b.get("missionType"), "mapSizeXYZ": b.get("mapSizeXYZ"),
            "mapFingerprint": b.get("mapFingerprint"), "turn": b.get("turn"), "side": b.get("side"),
            "battleId": (b.get("authority") or {}).get("battleId"), "phase": b.get("phase"),
            "xcom": {u["id"]: u.get("coop") for u in xcom},
            "pos": {u["id"]: (u.get("x"), u.get("y"), u.get("z")) for u in xcom},
            "aliens": sorted(u["id"] for u in units if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")),
            "pendingStates": b.get("pendingStates"), "isBusy": b.get("isBusy")}


def log_has(gc, needle):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return [ln.rstrip("\n").split("\t")[-1] for ln in f if needle in ln]
    except OSError:
        return []


def boot_classic(host, client, port, mission, seed, map_fp, aliens, tag):
    """raw.bring_up_lobby + drive_to_battlescape(seat_count=2, set_seed right before newbattle_ok), the pins,
    pin_ai_neutral, idle, hash clean (S-A1's boot_a shape)."""
    m = [host, client]
    step("bring_up_lobby", lambda: raw.bring_up_lobby(host, client, port), m)
    step("drive_to_battlescape", lambda: session.drive_to_battlescape(
        host, client, {}, mission=mission, seat_count=2, pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": seed})), m)
    hb, cb = bview(host), bview(client)
    bad = []
    if hb.get("mapFingerprint") != map_fp or cb.get("mapFingerprint") != map_fp:
        bad.append(f"mapFingerprint host={hb.get('mapFingerprint')!r} client={cb.get('mapFingerprint')!r} "
                   f"(baked {map_fp!r}, seed {seed})")
    if (hb.get("side"), hb.get("turn")) != (FACTION_PLAYER, 1) or hb.get("missionType") != mission:
        bad.append(f"host (side, turn, mission)={(hb.get('side'), hb.get('turn'), hb.get('missionType'))}")
    if hb.get("xcom") != SEATS or cb.get("xcom") != SEATS:
        bad.append(f"X-COM seats host={hb.get('xcom')} client={cb.get('xcom')} (want {SEATS})")
    if bad:
        raise FixtureMiss("bring-up pins: " + "; ".join(bad))
    pinned = step("pin_ai_neutral", lambda: pin_ai_neutral(host, client, tag=tag), m)
    if sorted(pinned) != aliens:
        raise FixtureMiss(f"pin_ai_neutral pinned {pinned} (want {aliens})")
    step("wait_host_idle", lambda: session.wait_host_idle(host, client, timeout=IDLE_S), m)
    step("hash clean at bring-up", lambda: assert_hash_clean(host, client, full=True, what="bring-up"), m)
    return {"mapFingerprint": hb.get("mapFingerprint"), "pinned": len(pinned), "spawn": hb.get("pos")}


def stage_guards(host, client, ctx, g):
    """Both stage records at zero before the stage; battleId b1 equal and > 0."""
    he, ce = eview(host), eview(client)
    ctx["b1"] = he.get("battleId")
    for name, e in (("host", he), ("client", ce)):
        st = e.get("stage")
        if not isinstance(st, dict) or st.get("emitted") != 0 or st.get("applied") != 0:
            g.append(f"{name} event_state.stage before the stage = {st} (want the record, emitted 0, applied 0)")
        if e.get("desyncSeen") is not False:
            g.append(f"{name} desyncSeen={e.get('desyncSeen')} before the stage (want false)")
    if not isinstance(ctx["b1"], int) or ctx["b1"] <= 0 or ce.get("battleId") != ctx["b1"]:
        g.append(f"battleId host={ctx['b1']} client={ce.get('battleId')} (want equal, > 0)")


def close_end_turn(host, client, g):
    """END TURN client then host; the host's NextTurnState closes (finishBattle runs inside dismiss_popup)."""
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        ok, secs = wait_until(lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", 20, 0.1)
        if not ok:
            g.append(f"host never painted END TURN 1/2 after the client's press ({secs}s)")
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    except Exception as e:
        g.append(f"END TURN presses: {short(e)}")
    ok, secs = wait_until(lambda: "NextTurnState" in host.cmd({"cmd": "list_widgets"}).get("state", ""), 30, 0.1)
    if not ok:
        g.append(f"host NextTurnState not up within {secs}s after both END TURN presses")
    t_close = time.time()
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "NextTurnState->close":
        g.append(f"host dismiss_popup answered {d} (want handled NextTurnState->close)")
    return t_close


def kill_all(host, client, aliens, g, what):
    """Host kill_unit_real faction 1 (the real UnitDieBState chain), the chain settled, hash clean."""
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": FACTION_HOSTILE})
    if not r.get("ok") or (aliens is not None and sorted(r.get("killed") or []) != aliens):
        g.append(f"{what} kill_unit_real faction 1 answered {r} (want ok, killed {aliens})")
    ok, secs = wait_until(lambda: (not bview(host).get("aliens") and bview(host).get("pendingStates") == 0
                                   and not bview(host).get("isBusy") and stack(host)[-1] == "BattlescapeState"),
                          60, 0.2)
    if not ok:
        g.append(f"{what} host kill chain not settled within {secs}s: host stack {stack(host)}")
    try:
        session.wait_host_idle(host, client, timeout=IDLE_S)
        assert_hash_clean(host, client, full=True, what=f"{what} before END TURN")
    except Exception as e:
        g.append(f"{what} settle / hash before END TURN: {short(e, 500)}")
    return r.get("killed")


def entry_cells(host, client, ctx, mission2):
    """The stage-entry cells (RED on commit 1), read after the close / confirm at ctx["t_close"]."""
    seen, _secs = wait_until(lambda: any("BriefingState" in s for s in stack(client)),
                             max(0.0, ENTRY_S - (time.time() - ctx["t_close"])), 0.25)
    ctx["clientBriefingS"] = round(time.time() - ctx["t_close"], 2) if seen else None
    cb, ce = bview(client), eview(client)
    ctx["entry"] = {"clientBriefing": seen, "clientStack": stack(client), "clientMission": cb.get("missionType"),
                    "clientStage": ce.get("stage"), "hostStageAtClose": ctx["hostStageAtClose"],
                    "hostRcAtClose": ctx["hostRcAtClose"], "hostRcAfterWait": rc(host),
                    "clientDesyncSeen": ce.get("desyncSeen"), "clientPhase": ce.get("phase")}
    f = []
    if not seen:
        f.append(f"client never showed the stage-2 BriefingState within {ENTRY_S}s of the host's close "
                 f"(stack {ctx['entry']['clientStack']})")
    if cb.get("missionType") != mission2:
        f.append(f"client missionType={cb.get('missionType')!r} (want {mission2!r})")
    if (ce.get("stage") or {}).get("applied") != 1:
        f.append(f"client stage.applied={(ce.get('stage') or {}).get('applied')} (want 1)")
    hs = ctx["hostStageAtClose"]
    if not isinstance(hs, dict) or hs.get("emitted") != 1:
        f.append(f"host stage.emitted={hs.get('emitted') if isinstance(hs, dict) else hs} at the close (want 1)")
    return f


def record_cells(host, client, ctx, f, want_h):
    """After the stage-2 spine: the host's `stage` record holds `want_h` (the row's own cells; MS1 owns the rest of
    the record), desyncSeen false on both (STOP-IF 5). Returns both event_states for the EVIDENCE line."""
    he, ce = eview(host), eview(client)
    hs = he.get("stage") or {}
    ctx["b2"] = he.get("battleId")
    for k, v in want_h.items():
        if hs.get(k) != v:
            f.append(f"host stage.{k}={hs.get(k)!r} (want {v!r})")
    for name, e in (("host", he), ("client", ce)):
        if e.get("desyncSeen") is not False:
            f.append(f"{name} desyncSeen={e.get('desyncSeen')} after the stage (want false)")
    return {"host": he, "client": ce}


def liveness_cells(host, ctx, crash0, f):
    new_crash = sorted(os.path.basename(p) for p in session._crash_log_snapshot() - crash0)
    ctx["newCrashFiles"] = new_crash
    if ctx.get("inStage2") and rc(host) is not None:
        f.append(f"host process exited rc={rc(host)}")
    if ctx.get("inStage2") and new_crash:
        f.append(f"new crash file(s) {new_crash}")


# ===================== MS2 =====================


def census_exit(gc):
    """Every END_POINT tile of the stage-1 map on this machine (tile_census, one z level per call)."""
    x, y, z = MAP_B_XYZ
    eps = []
    for zz in range(z):
        r = gc.cmd({"cmd": "tile_census", "x0": 0, "x1": x - 1, "y0": 0, "y1": y - 1, "z0": zz, "z1": zz})
        if not r.get("ok"):
            raise FixtureMiss(f"{gc.name} tile_census z {zz}: {r}")
        eps += [(t["x"], t["y"], t["z"]) for t in r.get("tiles") or [] if t and t.get("special") == END_POINT]
    return eps


def tile_special(gc, p):
    r = gc.cmd({"cmd": "tile_census", "x0": p[0], "x1": p[0], "y0": p[1], "y1": p[1], "z0": p[2], "z1": p[2]})
    return ((r.get("tiles") or [{}])[0] or {}).get("special")


def ms2(host, client, ctx, crash0):
    g = []
    stage_guards(host, client, ctx, g)
    eps = {gc.name: census_exit(gc) for gc in (host, client)}
    ctx["exitTiles"] = len(eps["host"])
    for name in ("host", "client"):
        if eps[name] != EXIT_TILES_B:
            g.append(f"{name} END_POINT tiles {eps[name]} (want the pinned {len(EXIT_TILES_B)}: {EXIT_TILES_B})")
    c2_at = bview(host).get("pos", {}).get(C2)
    ctx["c2"] = {"pos": c2_at,
                 "special": {gc.name: tile_special(gc, c2_at) for gc in (host, client)} if c2_at else None}
    if not c2_at or any(s == END_POINT for s in ctx["c2"]["special"].values()):
        g.append(f"C2 {C2} spawn {ctx['c2']} (want a non-END_POINT tile)")
    for uid, tile in EXIT_TARGETS_B:
        for gc in (client, host):                          # client first
            r = gc.cmd({"cmd": "battle_teleport_unit", "unit": uid, "x": tile[0], "y": tile[1], "z": tile[2]})
            if not r.get("ok"):
                g.append(f"{gc.name} battle_teleport_unit {uid} -> {tile}: {r}")
    hp, cp = bview(host).get("pos"), bview(client).get("pos")
    want_pos = {u: t for u, t in EXIT_TARGETS_B}
    want_pos[C2] = c2_at
    if hp != cp or {u: hp.get(u) for u in want_pos} != want_pos:
        g.append(f"X-COM positions host={hp} client={cp} (want {want_pos} on both)")
    try:
        session.wait_host_idle(host, client, timeout=IDLE_S)
        assert_hash_clean(host, client, full=True, what="after the exit teleports")
    except Exception as e:
        g.append(f"settle / hash after the teleports: {short(e, 500)}")
    r = host.cmd({"cmd": "battle_action", "action": "abort"})
    ok, secs = wait_until(lambda: stack(host)[-1] == "AbortMissionState", 10, 0.1)
    texts = [w.get("text") for w in (host.cmd({"cmd": "list_widgets"}).get("widgets") or []) if w.get("text")]
    ctx["abortDialog"] = texts
    if not r.get("ok") or not ok:
        g.append(f"host AbortMissionState not on top within {secs}s ({r}, stack {stack(host)})")
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "AbortMissionState":
        g.append(f"host dismiss_popup answered {d} (want handled AbortMissionState)")
    # R4-L1 S-A (AMENDMENT R4-L1-1 section 4, chain rule A.10): the OK opens the abort vote; the partner's YES passes
    # it and the host applies it at quiescence, so t_close and the two AtClose reads follow the host's stage record
    # newly emitted with aborted true (R-L1-A-3, F10833: stage 2's initBattleAuthority clears the abortVote record).
    try:
        st0 = (eview(host).get("stage") or {}).get("emitted") or 0
        session.abort_vote_yes(host, client)
        ok, secs = wait_until(lambda: ((eview(host).get("stage") or {}).get("emitted") or 0) > st0
                              and (eview(host).get("stage") or {}).get("aborted") is True, 10, 0.1)
        if not ok:
            g.append(f"the host's stage record was not emitted with aborted true within {secs}s of the partner's YES")
    except Exception as e:
        g.append(str(e))
    ctx["t_close"] = time.time()
    ctx["hostStageAtClose"] = eview(host).get("stage")    # finishBattle ran in the vote's apply
    ctx["hostRcAtClose"] = rc(host)
    if g:
        evidence("MS2", {"guards": g, "ctx": ctx})
        return [f"pre-stage: {m}" for m in g]
    fails = entry_cells(host, client, ctx, MISSION_FINAL)
    green = {}
    if not fails:
        ctx["inStage2"] = True
        try:
            _pressed, ctx["spineS"] = run_spine(host, client)
            green = record_cells(host, client, ctx, fails, {"aborted": True, "inExitArea": IN_EXIT_B})
            hb, cb = bview(host), bview(client)
            green["battle"] = {"host": hb, "client": cb}
            for name, b in (("host", hb), ("client", cb)):
                if b.get("turn") != 1 or b.get("missionType") != MISSION_FINAL:
                    fails.append(f"{name} turn/missionType={b.get('turn')}/{b.get('missionType')} "
                                 f"(want 1/{MISSION_FINAL})")
                if b.get("xcom") != STAGE2_LIVING_B:
                    fails.append(f"{name} stage-2 living X-COM id -> seat {b.get('xcom')} (want {STAGE2_LIVING_B}: "
                                 f"C1 {C1} carried, C2 {C2} left behind, V3)")
            try:
                assert_hash_clean(host, client, full=True, what="MS2 stage 2 turn 1")
            except AssertionError as e:
                fails.append(f"hash at stage-2 turn 1: {short(e, 500)}")
        except Exception as e:
            fails.append(f"stage-2 spine / cells: {short(e, 600)}")
    liveness_cells(host, ctx, crash0, fails)
    evidence("MS2", {"b1": ctx.get("b1"), "exitTiles": ctx.get("exitTiles"), "c2": ctx.get("c2"),
                     "abortDialog": ctx.get("abortDialog"), "entry": ctx.get("entry"),
                     "clientBriefingS": ctx.get("clientBriefingS"), "spineS": ctx.get("spineS"), "green": green,
                     "hostRc": rc(host), "newCrashFiles": ctx.get("newCrashFiles")})
    return fails


# ===================== MS3 =====================


def mod_view(gc):
    lines = log_has(gc, MOD_NAME)
    return {"active": [x for x in lines if x.startswith("- ")], "invalid": [x for x in log_has(gc, "Invalid")
                                                                         if "mod" in x],
            "deployment": log_has(gc, DEPLOYMENT_LINE)}


def final_debriefs(host, client, ctx, f):
    """Stage 2's kill-all through W2-P7: battle_end, both debriefs (S-B1), the client's OK then the host's (D156)."""
    g = []
    for name, gc in (("host", host), ("client", client)):
        be = event_state(gc).get("battleEnd") or {}
        if be.get("emitted") != 0 or be.get("applied") != 0:
            g.append(f"{name} battleEnd at stage-2 turn 1 = emitted {be.get('emitted')} applied {be.get('applied')} "
                     f"(want 0, 0: initBattleAuthority reset it at the stage-2 entry)")
    ctx["aliens2"] = bview(host).get("aliens")
    kill_all(host, client, None, g, "stage 2")
    close_end_turn(host, client, g)
    deb_ok, deb_s = wait_until(lambda: any("DebriefingState" in s for s in stack(host)), DEBRIEF_S, 0.1)
    if not deb_ok:
        g.append(f"host DebriefingState not reached within {deb_s}s of the stage-2 close (stack {stack(host)})")
    left_ok, left_s = wait_until(lambda: stack(client)[-1] in ("DebriefingState", "MainMenuState"), CLIENT_LEAVE_S,
                                 0.25)
    hrec, crec = event_state(host).get("battleEnd") or {}, event_state(client).get("battleEnd") or {}
    hdeb, cdeb = host.cmd({"cmd": "debrief_state"}), client.cmd({"cmd": "debrief_state"})
    ctx["final"] = {"hostDebriefS": deb_s, "clientEnd": left_ok, "clientEndS": left_s,
                    "clientTop": stack(client)[-1],
                    "hostRecord": {k: hrec.get(k) for k in ("emitted", "seq", "reason", "aborted", "inExitArea",
                                                            "resultSent", "resultBytes")},
                    "clientRecord": {k: crec.get(k) for k in ("applied", "seq", "reason", "resultReceived",
                                                              "resultBytes", "debriefDisplayOnly")},
                    "hostDebrief": debrief_view(hdeb), "aliens2": ctx["aliens2"], "pre": g}
    f += [f"stage-2 ending: {m}" for m in g]
    if hrec.get("emitted") != 1 or hrec.get("reason") != "aliensDown" or hrec.get("aborted") is not False:
        f.append(f"host battleEnd emitted/reason/aborted={hrec.get('emitted')}/{hrec.get('reason')}/"
                 f"{hrec.get('aborted')} (want 1/aliensDown/False)")
    if crec.get("applied") != 1 or crec.get("seq") != hrec.get("seq"):
        f.append(f"client battleEnd applied/seq={crec.get('applied')}/{crec.get('seq')} (want 1/{hrec.get('seq')})")
    if crec.get("resultReceived") != 1 or crec.get("debriefDisplayOnly") != 1:
        f.append(f"client battleEnd resultReceived/debriefDisplayOnly={crec.get('resultReceived')}/"
                 f"{crec.get('debriefDisplayOnly')} (want 1/1)")
    for name, deb, disp in (("host", hdeb, False), ("client", cdeb, True)):
        for k, want in (("shown", True), ("onTop", True), ("displayOnly", disp)):
            if deb.get(k) is not want:
                f.append(f"{name} debrief_state.{k}={deb.get(k)!r} (want {want!r})")
    for k in DEBRIEF_FIELDS:
        if debrief_view(cdeb).get(k) != debrief_view(hdeb).get(k):
            f.append(f"client debrief_state.{k}={cdeb.get(k)!r} != the host's {hdeb.get(k)!r}")
    leave = {}
    for name, gc in (("client", client), ("host", host)):   # D156 (a): the client leaves first (W2-P7 E3)
        ok = press_ok(gc)
        menu, secs = wait_until(lambda gc=gc: left_menu(gc), OK_LEAVE_S, 0.1) if ok.get("pressed") else (False, 0)
        leave[name] = {"ok": ok, "mainMenu": menu, "secs": secs, "stack": stack(gc)}
        if (ok.get("resp") or {}).get("handled") != "DebriefingState":
            f.append(f"{name} OK not handled by DebriefingState: {ok}")
        if not menu:
            f.append(f"{name} not on the main menu within {OK_LEAVE_S}s of its OK (stack {stack(gc)})")
    ctx["leave"] = leave


def ms3(host, client, ctx, crash0):
    g = []
    stage_guards(host, client, ctx, g)
    kill_all(host, client, ALIENS_C, g, "stage 1")
    ctx["t_close"] = close_end_turn(host, client, g)
    ctx["hostStageAtClose"] = eview(host).get("stage")
    ctx["hostRcAtClose"] = rc(host)
    if g:
        evidence("MS3", {"guards": g, "ctx": ctx})
        return [f"pre-stage: {m}" for m in g]
    fails = entry_cells(host, client, ctx, MISSION_C2)
    green = {}
    if not fails:
        ctx["inStage2"] = True
        try:
            _pressed, ctx["spineS"] = run_spine(host, client)
            green = record_cells(host, client, ctx, fails, {})
            hb, cb = bview(host), bview(client)
            green["battle"] = {"host": hb, "client": cb}
            for name, b in (("host", hb), ("client", cb)):
                if b.get("turn") != 1 or b.get("missionType") != MISSION_C2 or b.get("mapSizeXYZ") != STAGE2_TILES:
                    fails.append(f"{name} turn/missionType/mapSizeXYZ={b.get('turn')}/{b.get('missionType')}/"
                                 f"{b.get('mapSizeXYZ')} (want 1/{MISSION_C2}/{STAGE2_TILES})")
            try:
                assert_hash_clean(host, client, full=True, what="MS3 stage 2 turn 1")
            except AssertionError as e:
                fails.append(f"hash at stage-2 turn 1: {short(e, 500)}")
            final_debriefs(host, client, ctx, fails)
        except Exception as e:
            fails.append(f"stage 2 / the final debriefs: {short(e, 600)}")
    liveness_cells(host, ctx, crash0, fails)
    evidence("MS3", {"b1": ctx.get("b1"), "mod": ctx.get("mod"), "entry": ctx.get("entry"),
                     "clientBriefingS": ctx.get("clientBriefingS"), "spineS": ctx.get("spineS"), "green": green,
                     "final": ctx.get("final"), "leave": ctx.get("leave"), "hostRc": rc(host),
                     "newCrashFiles": ctx.get("newCrashFiles")})
    return fails


def boot_c(host, client):
    info = boot_classic(host, client, PORT_C, MISSION_C1, SEED_C, MAP_FP_C, ALIENS_C, "mga-a2-c")
    mv = {gc.name: mod_view(gc) for gc in (host, client)}
    for name, m in mv.items():
        if MOD_ACTIVE_LINE not in m["active"] or m["invalid"] or not m["deployment"]:
            raise FixtureMiss(f"{name}: {MOD_NAME} not in force (active {m['active']}, invalid {m['invalid']}, "
                              f"deployment {m['deployment']}; want '{MOD_ACTIVE_LINE}', none, '{DEPLOYMENT_LINE}')")
    info["mod"] = mv
    return info


# ===================== main =====================


def run_row(rid, results):
    ports, tag = (GC_B, "b") if rid == "MS2" else (GC_C, "c")
    mods = [] if rid == "MS2" else [MOD_DIR]
    host = GameClient("host", ports[0], make_user_dir(f"mga_ms_{tag}_host", mods=mods))
    client = GameClient("client", ports[1], make_user_dir(f"mga_ms_{tag}_client", mods=mods))
    crash0 = session._crash_log_snapshot()
    ctx = {}
    try:
        try:
            if rid == "MS2":
                info = boot_classic(host, client, PORT_B, MISSION_LANDING, SEED_B, MAP_FP_B, ALIENS_B, "mga-a2-b")
            else:
                info = boot_c(host, client)
                ctx["mod"] = info.get("mod")
            print(f"[mga-a2] boot {tag.upper()} ok: {info}", flush=True)
        except Exception as e:
            results[rid] = False
            print(f"FAIL {rid}: boot (FIXTURE-STOP) {short(e, 600)}", flush=True)
            capture(rid, [host, client], short(e, 600))
            return
        try:
            fails = (ms2 if rid == "MS2" else ms3)(host, client, ctx, crash0)
        except FixtureMiss as e:
            fails = [f"FIXTURE-STOP {e}"]
            evidence(rid, {"fixtureStop": str(e), "ctx": ctx})
        except Exception as e:
            fails = [short(e, 600)]
            evidence(rid, {"exception": short(e, 600), "ctx": ctx})
        results[rid] = not fails
        if fails:
            print(f"FAIL {rid}: {len(fails)} cell(s): " + " | ".join(fails), flush=True)
            capture(rid, [host, client], "row failed")
        else:
            print(f"PASS {rid}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[mga-a2] shutdown {gc.name}: {short(e)}", flush=True)


def main():
    t0 = time.time()
    results = {}
    order = ["MS2", "MS3"]
    for rid in order:
        run_row(rid, results)
    passed = [r for r in order if results.get(r)]
    failed = [r for r in order if not results.get(r)]
    print(f"\ntest_w2_multistage_end: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
