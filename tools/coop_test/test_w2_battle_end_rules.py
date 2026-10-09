"""W2-P7 S-D1 + S-B1 + S-D2 - test_w2_battle_end_rules.py: the remaining
battle endings. The turn limit, all X-COM down, a PvP (gm2) elimination and a
PvP host abort each reach the host's one `battle_end` hook at the top of
BattlescapeState::finishBattle, carry the right reason and per-seat verdict,
and the skirmish client leaves the battle with it (spec
rewrite/prompts/w2p7_battle_end.md sections (b)2-7 and (f)
test_w2_battle_end_rules.py; the W2-P7 plan review's section 2 rows E4-E6
and PINNED S-D1 stage text; AMENDMENT P7-1 rulings ST1-ST8; AMENDMENT P7-2
rulings G1-G8 and PINNED S-B1 text, R5; AMENDMENT P7-3's pin fixes G9-G14;
AMENDMENT P7-5 section 3 (S-D2) and its rulings Q2-Q4; owner rulings
D129 = (a) and D157 = (a); V7 for the PvP complement).

S-D1 is the reason / verdict / teardown half of E4-E6 (review scope table):
the S-A product (c8e9a37b1) already covered these endings, so the rows were
DECLARED GREEN-AT-RED. S-B1 (G1, G2) re-points E4 and E5 (DEBRIEF_ROWS): the
X-COM client now ends on the host's debriefing in a display-only
DebriefingState, with the same S-B1 rows as test_w2_battle_end.py E1/E2 (no
page walk here). No OK is pressed. S-D2 (owner D157 (a), AMENDMENT P7-5
section 3) re-points E6 the same way (chain rule A.10): the PvP alien-side
client ends on the host's debriefing, display-only, exactly as the X-COM
second player does (the host sends it the `bt_debrief_result` too), and adds
E6b, a PvP host abort, after which the hostile seat's recorded verdict is
`win` (D157 (a)'s dependency paragraph (a): a record only, no screen shows
it). Every row is a DEBRIEF_ROWS row. Four rows, ONE boot each (one ending
per boot); the Coop_TurnLimit_Test data mod is loaded on E4's boot only:

  E4  T5, the turn limit. Coop_TurnLimit_Test (tools/coop_test/mods/) adds
      STR_COOP_TURN_LIMIT_TEST = the NEW BATTLE default deployment
      (STR_SMALL_SCOUT) with turnLimit 1 and chronoTrigger 0 (FORCE_LOSE);
      newbattle_mission selects it (NEW BATTLE generates it as a mission site,
      TL_MAP_FP on SEED_MAP 1). END TURN client then host; the host closes its
      NextTurnState for the hostile side (side 1, turn 1); the AI's two pinned
      phases end, and BattlescapeGame::endTurn's turn-limit check trips on the
      NEUTRAL -> PLAYER endTurn that makes the turn 2 (TASK 0 T0-4: side
      transitions to hostile, neutral, player+turn 2, then battle_end) ->
      setAborted(true) + finishBattle(false, 0). Expected record: reason
      turnLimit, aborted true, inExitArea 0, verdict lose for seats 0 and 1,
      tally {liveAliens 1, liveSoldiers 7, inExit 0}.
  E5  T3, all X-COM down (the default map, SEED_MAP 1). The host runs
      battle_action kill_unit_real {faction: 0} (all seven soldiers, the
      real UnitDieBState path; battleNotifyDeath is off, so no death box
      opens on the host - T0-3), then battle_action end_turn (the direct
      requestEndTurn(false) lever: no living soldier is left to press the
      button), then closes its NextTurnState -> NextTurnState::close ->
      finishBattle(false, liveSoldiers 0). Expected record: reason
      soldiersDown, aborted false, inExitArea 0, verdict lose for seats 0 and
      1, tally {1, 0, 0}.
  E6  T9, PvP gm2 (the client plays the aliens, seat 1). The host runs
      battle_action kill_unit_real {faction: 1} (A, the client's only alien),
      presses END TURN (gm2: the host's seat alone ends the X-COM side), then
      closes its NextTurnState -> finishBattle(false, liveSoldiers 7).
      Expected record: reason aliensDown, aborted false, inExitArea 7, seat 0
      win and seat 1 lose (V7's complement), tally {0, 7, 0}. D157 (a): the
      alien seat ends on the host's debriefing, display-only, with the S-B1
      rows of E4/E5 (S-D2; the S-A interim tore it down to MainMenuState and
      its host sent it no `bt_debrief_result`). Not asserted:
      battle_state.pvpWin (no writer, F1907).
  E6b PvP gm2 host abort (E6's boot; AMENDMENT P7-5 Q3 (a)). No staging; the
      host runs battle_action abort and confirms its AbortMissionState with
      dismiss_popup (test_w2_battle_end.py end_e2, verbatim; R4-L1: + the alien player's YES) ->
      AbortMissionState::btnOkClick -> setAborted(true) + finishBattle(true,
      inExit). Expected record (E2's analog, pinned from the S-D2.1 R6
      capture): reason abort, aborted true, inExitArea 0, seat 0 abort and
      seat 1 win (D157 (a): the hostile seat takes `win` on an abort), tally
      {1, 7, 0}. The alien seat ends on the host's debriefing as in E6.

The `battleEnd` record (event_state.battleEnd, CoopDelta.h) is SESSION-
LIFETIME (ST4 (a), F1895): still readable after both machines' disconnect
resets at a skirmish end.

Pre-ending checks (every row; a failure here is a bring-up or staging failure,
reported with the prefix "pre-ending", never the row's verdict): the pinned
map, hash_now {full:true} ALL buckets EQUAL on both machines right before the
ending action, desyncSeen false on both, the host's coopClientBStatePushes 0,
the client's read as b0, both machines' battleEnd record present with emitted
0 and applied 0. The ending's own steps and the host's DebriefingState within
DEBRIEF_S are reported with the prefix "ending".

Row verdict = the S-A assertion set (review section 2, as test_w2_battle_end.py
E1/E2):
  host    battleEnd emitted 1, seq > 0, reason / aborted / inExitArea /
          perSeatVerdict / tally as the row expects, actionIdAtEmit 0,
          evsAfter 0 (no trailing reveal or any other host send after the
          envelope - OR1, measured 0 on all three triggers at T0-3/T0-4),
          stageSkips 0, hBuckets = the 9 action-end bucket names; the host's
          stack still holds DebriefingState; coopClientBStatePushes 0 and
          desyncSeen false. Every row (S-B1 rows f, g, i): the host hold (the
          host's top stays DebriefingState for HOST_HOLD_S after the client's
          end state, no CoopState(20), F2011/F2055); battleEnd resultSent 1,
          resultBytes > 0, resultDropped 0, debriefDisplayOnly 0;
          debrief_state shown, on top, not display-only, widgets {19, 5, 4},
          page 0, parseErrors 0, and the seven content fields equal to the
          row's HOST_DEBRIEF pin.
  client  battleEnd applied 1 with the host's seq and the row's reason /
          aborted / inExitArea / perSeatVerdict / tally, skirmish true,
          teardownInDrain false, latchedMs > 0 and tornDownMs >= latchedMs,
          desyncAtTeardown false, bstatePushesAtTeardown == b0,
          queueDepthAtTeardown 0, lastSeqApplied == the host's seq,
          hashVerify {seq = the host's seq, kind battle_end, buckets = the
          host's hBuckets}; the wait ends on DebriefingState or MainMenuState
          within CLIENT_LEAVE_S of the host's DebriefingState. Every row (S-B1
          rows b-d, h, j): top DebriefingState, world_state has_save true,
          battle_state inBattle false, event_state phase Idle; battleEnd
          resultReceived 1, resultBytes == the host's and > 0,
          resultReceivedMs > 0, tornDownMs >= resultReceivedMs,
          resultDropped 0, debriefDisplayOnly 1; debrief_state shown, on top,
          display-only, the same widget census, page 0, parseErrors 0, and
          every content field equal to the host's. E6 and E6b assert these
          on the PvP alien seat (D157 (a), S-D2).
  both    no client save file (assert_client_zero_disk), no new crash log.

The HOST_DEBRIEF pins (AMENDMENT P7-2 R6, P7-3) are each E4/E5 host
debrief_state, copied verbatim from one capture run on the S-B1.1 build, with
`soldiers` pinned as each row's deltas in order (names are compared
host-to-client only, G10) and E4's `rows` pinned as [] (no page-1 row, G11;
E5 needs at least one). E5's page-1 scores and total come from the per-boot
roster (a dead soldier's score is its rank and missions), so its pin holds
each page-1 row as {item, qty, recovery} and no total (G14); row j still
compares both machines' scores and totals. The S-B1.1 red run:
E4 and E5 fail on exactly the S-B1 red (as test_w2_battle_end.py E1/E2,
without the page walk); E6 passes. The E6 and E6b pins (and E6b's reason,
aborted, inExitArea and tally) are copied verbatim from one R6 capture run on
the S-D2.1 build (AMENDMENT P7-5 section 3). The S-D2.1 red run: E4 and E5
pass; E6 and E6b fail on exactly the S-D2 red cells - the alien client's top
MainMenuState (want DebriefingState) and has_save false (want true), the
host's resultSent 0 and the client's resultReceived 0 / debriefDisplayOnly 0
(the result keys of rows g and h), the client's debrief_state not shown (row
j); E6b also perSeatVerdict seat 1 `abort` (want `win`) on both machines.

Each row prints ONE "EVIDENCE <id>:" line with both machines' records, tops,
the host hold, both debriefs and the pre-ending census BEFORE its verdict is
checked; main() runs every row even after an earlier one failed and prints
"PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait that runs
out is recorded and fails the row.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot per
row, no alternative map or actor. Exit 0 only when all four rows pass, 2
otherwise.

Run:  python tools/coop_test/test_w2_battle_end_rules.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_w2_battle_end import debrief_view
from repro_atom_side_begin import row_for as gm2_row_for
from repro_pvp_side_relative import drive_to_gm2_battlescape

# ----- the default NEW BATTLE map, pinned (W2-P2 TASK 0a round 1; test_w2_delta_items; gm2: test_w2_client_pvp) -----
SEED_MAP = 1
MAP_FP = -4.48310638993e+18      # host battle_state.mapFingerprint on SEED_MAP 1 (E5 classic, E6 gm2)
A_ID = 1000000                   # the only alien: Sectoid Soldier, spawn (27,12,0); gm2: the client's (seat 1)
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]   # the seven X-COM soldiers (seat 1: 8, 9; seat 0: 10-14 in the classic boot)
STATUS_DEAD = 6                  # src/Mod/Unit.h enum UnitStatus
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
GAMEMODE_PVP = 2

# ----- E4: the Coop_TurnLimit_Test data mod (TASK 0 T0-4) -----
MOD_NAME = "Coop_TurnLimit_Test"
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_TurnLimit_Test v1.0"
TL_MISSION = "STR_COOP_TURN_LIMIT_TEST"
TL_DEPLOYMENT_LINE = 'BriefingState deployment: VANILLA "STR_COOP_TURN_LIMIT_TEST"'   # both machines' log
TL_MAP_FP = 5.996615470105667e+18   # host and client battle_state.mapFingerprint, TL_MISSION on SEED_MAP 1 (T0-4)
TL_CLOSE_AT = (FACTION_HOSTILE, 1)  # the host's only NextTurnState before the ending: hostile side, turn 1 (T0-4)

# ----- W2-P7 constants (test_w2_battle_end.py) -----
H_BUCKETS = sorted(["terrain", "fire", "smoke", "items", "unitsCore", "unitsStats", "itemIdCtr", "synced",
                    "saveBlob"])
DEBRIEF_S = 30        # host DebriefingState after the ending's last step (T0-3/T0-4: 0.05 s)
CLIENT_LEAVE_S = 30   # client end state (CLIENT_END_TOPS) after the host's DebriefingState (T0-3/T0-4: 0.05 s)
ROW_EXPECT = {
    # T0-4: the turn-limit check trips on the NEUTRAL -> PLAYER endTurn (turn 2); FORCE_LOSE sets
    # aborted and calls finishBattle(false, 0).
    "E4": {"reason": "turnLimit", "aborted": True, "inExitArea": 0,
           "verdicts": [(0, "lose"), (1, "lose")],
           "tally": {"liveAliens": 1, "liveSoldiers": 7, "inExit": 0}},
    # T0-3: finishBattle(false, 0) from NextTurnState::close, isAborted() false.
    "E5": {"reason": "soldiersDown", "aborted": False, "inExitArea": 0,
           "verdicts": [(0, "lose"), (1, "lose")],
           "tally": {"liveAliens": 1, "liveSoldiers": 0, "inExit": 0}},
    # T0-3: finishBattle(false, 7) from NextTurnState::close; seat 1 (FACTION_HOSTILE) takes the complement.
    "E6": {"reason": "aliensDown", "aborted": False, "inExitArea": 7,
           "verdicts": [(0, "win"), (1, "lose")],
           "tally": {"liveAliens": 0, "liveSoldiers": 7, "inExit": 0}},
    # S-D2 (AMENDMENT P7-5 Q3 (a)): finishBattle(true, inExit) from AbortMissionState::btnOkClick in gm2; the
    # verdict pair is D157 (a) (the hostile seat takes `win` on an abort); reason / aborted / inExitArea / tally
    # from the R6 capture (E2's analog, F4334).
    "E6b": {"reason": "abort", "aborted": True, "inExitArea": 0,
            "verdicts": [(0, "abort"), (1, "win")],
            "tally": {"liveAliens": 1, "liveSoldiers": 7, "inExit": 0}},
}
ROW_PORT = {"E4": "48776", "E5": "48777", "E6": "48778", "E6b": "48779"}

# ----- W2-P7 S-B1 constants (AMENDMENT P7-2 R5; as test_w2_battle_end.py) -----
# The client's display-only debrief: the X-COM client (E4, E5, S-B1) and the PvP alien side (E6, E6b; D157 (a), S-D2).
DEBRIEF_ROWS = ("E4", "E5", "E6", "E6b")
CLIENT_END_TOPS = ("DebriefingState", "MainMenuState")   # the client wait ends on either (every row)
HOST_HOLD_S = 3       # the host's top sampled every 0.25 s for this long after the client's end state (F2055)
DEBRIEF_WIDGETS = {"texts": 19, "lists": 5, "buttons": 4}   # DebriefingState.cpp :144-174 (F2049)
DEBRIEF_FIELDS = ("title", "recoveryHeader", "rows", "total", "rating", "soldiers", "recovered")
# G11 (F2031): these rows' host page 1 has at least one row; the other rows pin `rows` as [].
ROWS_WITH_PAGE1 = ("E5", "E6")
# G14 (F2037): these rows' page-1 scores and total come from the per-boot roster (dead soldiers' ranks and
# missions): the pin holds each page-1 row as {item, qty, recovery} and no `total`.
ROSTER_SCORED_ROWS = ("E5",)
# R6: each DEBRIEF_ROWS row's host debrief_state content, copied verbatim from the capture run on the S-B1.1
# build (E4, E5) or on the S-D2.1 build (E6, E6b) (pin_view: `soldiers` as each row's deltas, G10).
HOST_DEBRIEF = {
    # R6 capture B (S-B1.1 build): E4 = T5, the turn limit (no page-1 row, G11).
    "E4": {"title": "Terror continues", "recoveryHeader": "", "rows": [], "total": 0, "rating": "RATING> POOR!",
           "soldiers": [
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        ],
           "recovered": []},
    # R6 capture B: E5 = T3, all X-COM down (roster-scored, G14: rows without score, no total).
    "E5": {"title": "Craft is lost", "recoveryHeader": "",
           "rows": [{"item": "X-COM OPERATIVES KILLED", "qty": 7, "recovery": False},
                    {"item": "X-COM CRAFT LOST", "qty": 1, "recovery": False}],
           "rating": "RATING> TERRIBLE!", "soldiers": [], "recovered": []},
    # R6 capture (S-D2.1 build): E6 = T9, the PvP gm2 elimination (equal to test_w2_battle_end.py's E1 pin, F4334).
    "E6": {"title": "UFO is recovered", "recoveryHeader": "UFO RECOVERY",
           "rows": [{"item": "ALIEN CORPSES RECOVERED", "qty": 1, "recovery": False, "score": 5},
                    {"item": "Alien Alloys", "qty": 1, "recovery": True, "score": 1}],
           "total": 6, "rating": "RATING> OK",
           "soldiers": [
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                        ],
           "recovered": [{"item": "Plasma Pistol", "qty": 1}, {"item": "  Plasma Pistol Clip", "qty": 2},
                         {"item": "Mind Probe", "qty": 1}, {"item": "Sectoid Corpse", "qty": 1},
                         {"item": "Alien Alloys", "qty": 1}]},
    # R6 capture (S-D2.1 build): E6b = the PvP gm2 host abort (no page-1 row, G11; equal to the E2 pin, F4334).
    "E6b": {"title": "UFO is not recovered", "recoveryHeader": "", "rows": [], "total": 0,
            "rating": "RATING> POOR!",
            "soldiers": [
                         [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                         [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                         [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                         [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                         [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                         [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                         [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                         ],
            "recovered": []},
}


# ===================== small probes =====================


def short(e):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= 300 else s[:300] + "..."


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def wait_until(pred, timeout, interval):
    """Poll `pred` until truthy or `timeout` seconds pass. Returns (ok, seconds)."""
    t0 = time.time()
    while True:
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def verdicts(rec):
    pv = (rec or {}).get("perSeatVerdict") or []
    return sorted((e.get("seat"), e.get("verdict")) for e in pv if isinstance(e, dict))


def tally(rec):
    t = (rec or {}).get("tally") or {}
    return {k: t.get(k) for k in ("liveAliens", "liveSoldiers", "inExit")}


def machine_view(gc):
    es = event_state(gc)
    bs = battle_state(gc)
    ws = gc.cmd({"cmd": "world_state"})
    return {"top": top(gc), "stack": stack(gc), "inBattle": bs.get("inBattle"), "phase": es.get("phase"),
            "desyncSeen": es.get("desyncSeen"), "bstatePushes": es.get("coopClientBStatePushes"),
            "lastSeqEmitted": es.get("lastSeqEmitted"), "lastSeqApplied": es.get("lastSeqApplied"),
            "queueDepth": es.get("queueDepth"), "hasSave": ws.get("has_save"), "battleEnd": es.get("battleEnd"),
            "debrief": gc.cmd({"cmd": "debrief_state"})}


def host_hold(host):
    """S-B1 row f (F2055): sample the host's top every 0.25 s for HOST_HOLD_S and
    return the distinct non-DebriefingState tops seen, in first-seen order
    ([] = the host's debrief held the top throughout)."""
    seen = []
    t0 = time.time()
    while True:
        t = top(host)
        if t != "DebriefingState" and t not in seen:
            seen.append(t)
        if time.time() - t0 >= HOST_HOLD_S:
            return seen
        time.sleep(0.25)


def log_lines(gc):
    """This machine's openxcom.log, one string per line ([] when unreadable)."""
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def mod_evidence(gc):
    """The Coop_TurnLimit_Test active-mod lines, every invalid-mod line and the
    BriefingState deployment line naming TL_MISSION in this machine's log."""
    lines = log_lines(gc)
    return {"active": [ln.split("\t")[-1] for ln in lines if MOD_NAME in ln and "- " in ln and "Invalid" not in ln],
            "invalid": [ln.split("\t")[-1] for ln in lines if "Invalid" in ln and "mod" in ln],
            "deployment": [ln.split("\t")[-1] for ln in lines if TL_DEPLOYMENT_LINE in ln]}


def host_chain_done(host, dead_ids):
    """HOST only: every unit in `dead_ids` is DEAD, no BState is queued or
    running, BattlescapeState on top."""
    bs = battle_state(host)
    ub = session.units_by_id(bs)
    return (all((ub.get(u) or {}).get("status") == STATUS_DEAD for u in dead_ids)
            and bs.get("pendingStates") == 0 and not bs.get("isBusy") and top(host) == "BattlescapeState")


def host_next_turn_up(host):
    return "NextTurnState" in host.cmd({"cmd": "list_widgets"}).get("state", "")


# ===================== the rows' staging and endings =====================


def stage_none(host, client, pre):
    """E4 / E6b staging: none (the turn limit or the abort ends the battle as it stands)."""
    return {}


def end_e4(host, client, ending):
    """E4 ending: END TURN client then host; the host closes its hostile-side
    NextTurnState (side 1, turn 1); the AI's pinned hostile and neutral phases
    end and the NEUTRAL -> PLAYER endTurn (turn 2) trips the turn limit."""
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    except Exception as e:
        ending.append(f"client end_turn_button: {short(e)}")
    ok, secs = wait_until(lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", 20, 0.1)
    if not ok:
        ending.append(f"host never painted END TURN 1/2 after the client's press ({secs}s)")
    try:
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    except Exception as e:
        ending.append(f"host end_turn_button: {short(e)}")
    ok, secs = wait_until(lambda: host_next_turn_up(host), 30, 0.1)
    if not ok:
        ending.append(f"host NextTurnState not up within {secs}s after both END TURN presses")
    hs = battle_state(host)
    at = (hs.get("side"), hs.get("turn"))
    if at != TL_CLOSE_AT:
        ending.append(f"host NextTurnState up at (side, turn)={at} (want {TL_CLOSE_AT})")
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "NextTurnState->close":
        ending.append(f"host dismiss_popup answered {d} (want handled NextTurnState->close)")
    return {"closeAt": at, "close": d}


def stage_e5(host, client, pre):
    """E5 staging: the host kills all seven X-COM soldiers through the real
    UnitDieBState chain and both machines settle (no host death box opens:
    battleNotifyDeath is off, T0-3)."""
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": FACTION_PLAYER})
    if not r.get("ok") or sorted(r.get("killed") or []) != XCOM_IDS:
        pre.append(f"kill_unit_real faction {FACTION_PLAYER} answered {r} (want ok, killed {XCOM_IDS})")
    ok, secs = wait_until(lambda: host_chain_done(host, XCOM_IDS), 30, 0.1)
    if not ok:
        pre.append(f"host kill chain not finished (X-COM DEAD, no BState, BattlescapeState on top) within {secs}s: "
                   f"host stack {stack(host)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        pre.append(f"wait_host_idle after the kill: {short(e)}")
    return {"kill": r, "chainS": secs}


def end_e5(host, client, ending):
    """E5 ending: the host's end_turn lever (requestEndTurn(false)) and its
    NextTurnState close (NextTurnState::close -> finishBattle(false, 0))."""
    try:
        host.ok({"cmd": "battle_action", "action": "end_turn"})
    except Exception as e:
        ending.append(f"host battle_action end_turn: {short(e)}")
    ok, secs = wait_until(lambda: host_next_turn_up(host), 30, 0.1)
    if not ok:
        ending.append(f"host NextTurnState not up within {secs}s after the end_turn lever")
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "NextTurnState->close":
        ending.append(f"host dismiss_popup answered {d} (want handled NextTurnState->close)")
    return {"close": d}


def stage_e6(host, client, pre):
    """E6 staging: the host kills A (the client's only alien) through the real
    UnitDieBState chain and both machines settle."""
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": FACTION_HOSTILE})
    if not r.get("ok") or r.get("killed") != [A_ID]:
        pre.append(f"kill_unit_real faction {FACTION_HOSTILE} answered {r} (want ok, killed [{A_ID}])")
    ok, secs = wait_until(lambda: host_chain_done(host, [A_ID]), 30, 0.1)
    if not ok:
        pre.append(f"host kill chain not finished (A DEAD, no BState, BattlescapeState on top) within {secs}s: "
                   f"host stack {stack(host)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        pre.append(f"wait_host_idle after the kill: {short(e)}")
    return {"kill": r, "chainS": secs}


def end_e6(host, client, ending):
    """E6 ending: the host's END TURN (its seat alone ends the X-COM side in
    gm2) and its NextTurnState close (NextTurnState::close ->
    finishBattle(false, 7))."""
    try:
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    except Exception as e:
        ending.append(f"host end_turn_button: {short(e)}")
    ok, secs = wait_until(lambda: host_next_turn_up(host), 30, 0.1)
    if not ok:
        ending.append(f"host NextTurnState not up within {secs}s after the host's END TURN")
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "NextTurnState->close":
        ending.append(f"host dismiss_popup answered {d} (want handled NextTurnState->close)")
    return {"close": d}


def end_e6b(host, client, ending):
    """E6b ending (test_w2_battle_end.py end_e2, verbatim): the host's abort, its
    confirm and the alien player's YES (R4-L1: the confirm opens the abort vote; its
    pass runs setAborted(true) + finishBattle(true, inExit)), on E6's gm2 boot."""
    try:
        host.ok({"cmd": "battle_action", "action": "abort"})
    except Exception as e:
        ending.append(f"host battle_action abort: {short(e)}")
    ok, secs = wait_until(lambda: any("AbortMissionState" in s for s in stack(host)), 30, 0.1)
    if not ok:
        ending.append(f"host AbortMissionState not up within {secs}s")
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "AbortMissionState":
        ending.append(f"host dismiss_popup answered {d} (want handled AbortMissionState)")
    try:
        session.abort_vote_yes(host, client)
    except Exception as e:
        ending.append(str(e))
    return {"confirm": d}


# ===================== one row =====================


def pre_census(host, client, pre):
    """The pre-ending census: hash clean, desync, b0, host pushes, both records at zero."""
    census = {}
    try:
        hh, _ch = assert_hash_clean(host, client, full=True, what="before the ending")
        census["hashBuckets"] = sorted(hh.keys())
    except AssertionError as e:
        pre.append(f"hash_now full before the ending: {e}")
    census["host"] = machine_view(host)
    census["client"] = machine_view(client)
    for name in ("host", "client"):
        v = census[name]
        if v["desyncSeen"] is not False:
            pre.append(f"{name} desyncSeen={v['desyncSeen']} before the ending (want false)")
        rec = v["battleEnd"]
        if not isinstance(rec, dict) or rec.get("emitted") != 0 or rec.get("applied") != 0:
            pre.append(f"{name} battleEnd before the ending = {rec} (want the record with emitted 0, applied 0)")
    if census["host"]["bstatePushes"] != 0:
        pre.append(f"host coopClientBStatePushes={census['host']['bstatePushes']} before the ending (want 0)")
    census["b0"] = census["client"]["bstatePushes"]
    if not isinstance(census["b0"], int):
        pre.append(f"client coopClientBStatePushes={census['b0']!r} before the ending (want an int)")
    return census


def census_view(c):
    return {"hashBuckets": c.get("hashBuckets"), "b0": c.get("b0"),
            **{f"{n}": {k: c[n][k] for k in ("top", "inBattle", "phase", "desyncSeen", "bstatePushes",
                                               "lastSeqEmitted", "lastSeqApplied", "queueDepth")}
               for n in ("host", "client")}}


def pin_fields(rid):
    """The DEBRIEF_FIELDS a row's host pin holds: all seven, less `total` on
    ROSTER_SCORED_ROWS (AMENDMENT P7-3 G14)."""
    return tuple(k for k in DEBRIEF_FIELDS if not (rid in ROSTER_SCORED_ROWS and k == "total"))


def pin_view(deb, rid):
    """The pinned form of a debrief_state (AMENDMENT P7-3 G10, F2030): the seven
    content fields, with `soldiers` reduced to each row's deltas in order (the
    row count and the stat gains) - soldier names change per boot, so they are
    compared host-to-client only (row j), never pinned. G14 (F2037): on
    ROSTER_SCORED_ROWS each page-1 row is {item, qty, recovery} (a dead
    soldier's score comes from its rank and missions, DebriefingState.cpp
    :1494/:1530, BattleUnit.cpp :89-100) and `total` is not pinned; row j still
    compares both machines' scores and totals."""
    deb = deb if isinstance(deb, dict) else {}
    out = {k: deb.get(k) for k in pin_fields(rid)}
    out["soldiers"] = [s.get("deltas") for s in (deb.get("soldiers") or []) if isinstance(s, dict)]
    if rid in ROSTER_SCORED_ROWS:
        out["rows"] = [{k: r.get(k) for k in ("item", "qty", "recovery")}
                       for r in (deb.get("rows") or []) if isinstance(r, dict)]
    return out


def debrief_verdict(rid, hrec, crec, hdeb, cdeb, hold):
    """AMENDMENT P7-2 R4 rows f-j (S-B1, DEBRIEF_ROWS only); returns the list of failures."""
    f = []
    hdeb = hdeb if isinstance(hdeb, dict) else {}
    cdeb = cdeb if isinstance(cdeb, dict) else {}
    # f: the host hold - the host's debrief keeps the top (no CoopState(20), F2011 / F2055)
    if hold != []:
        f.append(f"host hold saw {hold} within {HOST_HOLD_S}s after the client's end state (want [] - the host's "
                 f"top DebriefingState throughout)")
    # g: the host record's result keys
    hbytes = hrec.get("resultBytes")
    if hrec.get("resultSent") != 1:
        f.append(f"host battleEnd.resultSent={hrec.get('resultSent')} (want 1)")
    if not isinstance(hbytes, int) or hbytes <= 0:
        f.append(f"host battleEnd.resultBytes={hbytes} (want an int > 0)")
    if hrec.get("resultDropped") != 0:
        f.append(f"host battleEnd.resultDropped={hrec.get('resultDropped')} (want 0)")
    if hrec.get("debriefDisplayOnly") != 0:
        f.append(f"host battleEnd.debriefDisplayOnly={hrec.get('debriefDisplayOnly')} (want 0)")
    # h: the client record's result keys
    cbytes, rms, tdn = crec.get("resultBytes"), crec.get("resultReceivedMs"), crec.get("tornDownMs")
    if crec.get("resultReceived") != 1:
        f.append(f"client battleEnd.resultReceived={crec.get('resultReceived')} (want 1)")
    if not isinstance(cbytes, int) or cbytes <= 0 or cbytes != hbytes:
        f.append(f"client battleEnd.resultBytes={cbytes} (want the host's {hbytes}, > 0)")
    if not isinstance(rms, int) or rms <= 0:
        f.append(f"client battleEnd.resultReceivedMs={rms} (want an int > 0)")
    if not isinstance(rms, int) or not isinstance(tdn, int) or tdn < rms:
        f.append(f"client battleEnd tornDownMs={tdn} resultReceivedMs={rms} (want tornDownMs >= resultReceivedMs: "
                 f"the teardown waited for the payload, G3)")
    if crec.get("resultDropped") != 0:
        f.append(f"client battleEnd.resultDropped={crec.get('resultDropped')} (want 0)")
    if crec.get("debriefDisplayOnly") != 1:
        f.append(f"client battleEnd.debriefDisplayOnly={crec.get('debriefDisplayOnly')} (want 1)")
    # i: the host's debrief_state against the row's pin
    for k, want in (("shown", True), ("onTop", True), ("displayOnly", False)):
        if hdeb.get(k) is not want:
            f.append(f"host debrief_state.{k}={hdeb.get(k)!r} (want {want!r})")
    if hdeb.get("widgets") != DEBRIEF_WIDGETS:
        f.append(f"host debrief_state.widgets={hdeb.get('widgets')} (want {DEBRIEF_WIDGETS})")
    if hdeb.get("page") != 0:
        f.append(f"host debrief_state.page={hdeb.get('page')} (want 0)")
    if hdeb.get("parseErrors") != 0:
        f.append(f"host debrief_state.parseErrors={hdeb.get('parseErrors')} (want 0)")
    pin = HOST_DEBRIEF.get(rid)
    if pin is None:
        f.append(f"no HOST_DEBRIEF pin for {rid} (R6)")
    else:
        # G11 (F2031): a non-empty title on every row; ROWS_WITH_PAGE1 rows also need a page-1 row
        need_rows = rid in ROWS_WITH_PAGE1
        if pin.get("title") in ("", None) or (need_rows and len(pin.get("rows") or []) < 1):
            f.append(f"HOST_DEBRIEF[{rid}] pin sanity: title={pin.get('title')!r} rows={pin.get('rows')} "
                     f"(want a non-empty title{' and at least one page-1 row' if need_rows else ''})")
        hpin = pin_view(hdeb, rid)
        for k in pin_fields(rid):
            if hpin.get(k) != pin.get(k):
                f.append(f"host debrief_state.{k}={hpin.get(k)!r} (want the pinned {pin.get(k)!r})")
    # j: the client's debrief_state against the host's
    for k, want in (("shown", True), ("onTop", True), ("displayOnly", True)):
        if cdeb.get(k) is not want:
            f.append(f"client debrief_state.{k}={cdeb.get(k)!r} (want {want!r})")
    if cdeb.get("widgets") != DEBRIEF_WIDGETS:
        f.append(f"client debrief_state.widgets={cdeb.get('widgets')} (want {DEBRIEF_WIDGETS})")
    if cdeb.get("page") != 0:
        f.append(f"client debrief_state.page={cdeb.get('page')} (want 0)")
    if cdeb.get("parseErrors") != 0:
        f.append(f"client debrief_state.parseErrors={cdeb.get('parseErrors')} (want 0)")
    for k in DEBRIEF_FIELDS:
        if debrief_view(cdeb).get(k) != debrief_view(hdeb).get(k):
            f.append(f"client debrief_state.{k}={cdeb.get(k)!r} != the host's {hdeb.get(k)!r} "
                     f"(page-2 prefixes stripped, AUD-A07)")
    return f


def row_verdict(rid, expect, hrec, crec, cend, hend, b0, cleft, extra, hold, hdeb, cdeb):
    """Every S-A assertion of the row, with AMENDMENT P7-2 R4's re-points a-c and
    new rows f-j on DEBRIEF_ROWS (every row since S-D2; the S-A MainMenuState
    branch below no longer runs); returns the list of failures (empty = pass)."""
    f = []
    hrec = hrec if isinstance(hrec, dict) else {}
    crec = crec if isinstance(crec, dict) else {}
    debrief_row = rid in DEBRIEF_ROWS
    # --- the host's emission, the client's end state reached ---
    if hrec.get("emitted") != 1:
        f.append(f"host battleEnd.emitted={hrec.get('emitted')} (want 1)")
    if not cleft["ok"] and debrief_row:
        f.append(f"client reached neither DebriefingState nor MainMenuState within {CLIENT_LEAVE_S}s of the "
                 f"host's DebriefingState ({cleft['secs']}s): top={cend['top']} inBattle={cend['inBattle']}")
    elif not cleft["ok"]:
        f.append(f"client still in battle {cleft['secs']}s after the host's DebriefingState: top={cend['top']} "
                 f"inBattle={cend['inBattle']} (want MainMenuState within {CLIENT_LEAVE_S}s)")
    # --- host record ---
    hseq = hrec.get("seq")
    if not isinstance(hseq, int) or hseq <= 0:
        f.append(f"host battleEnd.seq={hseq} (want > 0)")
    for k in ("reason", "aborted", "inExitArea"):
        if hrec.get(k) != expect[k]:
            f.append(f"host battleEnd.{k}={hrec.get(k)!r} (want {expect[k]!r})")
    if verdicts(hrec) != expect["verdicts"]:
        f.append(f"host battleEnd.perSeatVerdict={hrec.get('perSeatVerdict')} (want {expect['verdicts']})")
    if tally(hrec) != expect["tally"]:
        f.append(f"host battleEnd.tally={hrec.get('tally')} (want {expect['tally']})")
    for k, want in (("actionIdAtEmit", 0), ("evsAfter", 0), ("stageSkips", 0)):
        if hrec.get(k) != want:
            f.append(f"host battleEnd.{k}={hrec.get(k)} (want {want})")
    if sorted(hrec.get("hBuckets") or []) != H_BUCKETS:
        f.append(f"host battleEnd.hBuckets={hrec.get('hBuckets')} (want {H_BUCKETS})")
    if not any("DebriefingState" in s for s in hend["stack"]):
        f.append(f"host stack {hend['stack']} holds no DebriefingState")
    if hend["bstatePushes"] != 0:
        f.append(f"host coopClientBStatePushes={hend['bstatePushes']} (want 0)")
    if hend["desyncSeen"] is not False:
        f.append(f"host desyncSeen={hend['desyncSeen']} (want false)")
    # --- client record ---
    if crec.get("applied") != 1:
        f.append(f"client battleEnd.applied={crec.get('applied')} (want 1)")
    if crec.get("seq") != hseq:
        f.append(f"client battleEnd.seq={crec.get('seq')} (want the host's {hseq})")
    for k in ("reason", "aborted", "inExitArea"):
        if crec.get(k) != expect[k]:
            f.append(f"client battleEnd.{k}={crec.get(k)!r} (want {expect[k]!r})")
    if verdicts(crec) != expect["verdicts"]:
        f.append(f"client battleEnd.perSeatVerdict={crec.get('perSeatVerdict')} (want {expect['verdicts']})")
    if tally(crec) != expect["tally"]:
        f.append(f"client battleEnd.tally={crec.get('tally')} (want {expect['tally']})")
    for k, want in (("skirmish", True), ("teardownInDrain", False), ("desyncAtTeardown", False),
                    ("queueDepthAtTeardown", 0)):
        if crec.get(k) != want:
            f.append(f"client battleEnd.{k}={crec.get(k)!r} (want {want!r})")
    lat, tdn = crec.get("latchedMs"), crec.get("tornDownMs")
    if not isinstance(lat, int) or lat <= 0 or not isinstance(tdn, int) or tdn < lat:
        f.append(f"client battleEnd latchedMs={lat} tornDownMs={tdn} (want latchedMs > 0, tornDownMs >= latchedMs)")
    if crec.get("bstatePushesAtTeardown") != b0:
        f.append(f"client battleEnd.bstatePushesAtTeardown={crec.get('bstatePushesAtTeardown')} (want b0 {b0})")
    if crec.get("lastSeqApplied") != hseq:
        f.append(f"client battleEnd.lastSeqApplied={crec.get('lastSeqApplied')} (want the host's seq {hseq})")
    hv = crec.get("hashVerify") if isinstance(crec.get("hashVerify"), dict) else {}
    if (hv.get("seq") != hseq or hv.get("kind") != "battle_end"
            or sorted(hv.get("buckets") or []) != sorted(hrec.get("hBuckets") or [])):
        f.append(f"client battleEnd.hashVerify={crec.get('hashVerify')} (want seq {hseq}, kind battle_end, "
                 f"buckets = the host's hBuckets)")
    # --- client end state ---
    if debrief_row:
        # S-B1 rows b-d (G4): the display-only debrief
        if cend["top"] != "DebriefingState":
            f.append(f"client top={cend['top']} (want DebriefingState)")
        if cend["hasSave"] is not True:
            f.append(f"client world_state.has_save={cend['hasSave']} (want true)")
        if cend["inBattle"] is not False:
            f.append(f"client battle_state.inBattle={cend['inBattle']} (want false)")
        if cend["phase"] != "Idle":
            f.append(f"client event_state.phase={cend['phase']} (want Idle)")
        f += debrief_verdict(rid, hrec, crec, hdeb, cdeb, hold)
    else:
        if cend["top"] != "MainMenuState":
            f.append(f"client top={cend['top']} (want MainMenuState)")
        if cend["hasSave"] is not False:
            f.append(f"client world_state.has_save={cend['hasSave']} (want false)")
        if cend["inBattle"] is not False:
            f.append(f"client battle_state.inBattle={cend['inBattle']} (want false)")
        if cend["phase"] != "Idle":
            f.append(f"client event_state.phase={cend['phase']} (want Idle)")
    f += extra
    return f


def run_row(rid, boot_fn, stage_fn, end_fn, mods, results):
    expect = ROW_EXPECT[rid]
    host = GameClient("host", 49894, make_user_dir(f"w2p7_battle_end_rules_{rid}_host", mods=mods))
    client = GameClient("client", 49895, make_user_dir(f"w2p7_battle_end_rules_{rid}_client", mods=mods))
    try:
        try:
            boot_info = boot_fn(host, client, ROW_PORT[rid])
        except Exception as e:
            results[rid] = False
            print(f"FAIL {rid}: pre-ending (bring-up) {short(e)}", flush=True)
            return
        try:
            pre, ending = [], []
            staging = stage_fn(host, client, pre)
            census = pre_census(host, client, pre)
            crash0 = session._crash_log_snapshot()
            t_end = time.time()
            ending_resp = end_fn(host, client, ending)
            deb_ok, deb_s = wait_until(lambda: any("DebriefingState" in s for s in stack(host)), DEBRIEF_S, 0.1)
            if not deb_ok:
                ending.append(f"host DebriefingState not reached within {deb_s}s of the ending's last step: "
                              f"host stack {stack(host)}")
            deb_after = round(time.time() - t_end, 2)
            left_ok, left_s = wait_until(lambda: top(client) in CLIENT_END_TOPS, CLIENT_LEAVE_S, 0.25)
            cleft = {"ok": left_ok, "secs": left_s}
            hold = host_hold(host) if rid in DEBRIEF_ROWS else None
            hend, cend = machine_view(host), machine_view(client)
            crash1 = session._crash_log_snapshot()
            extra = []
            new_crash = sorted(crash1 - crash0)
            if new_crash:
                extra.append(f"new crash log(s): {new_crash}")
            try:
                session.assert_client_zero_disk(client.user_dir)
            except AssertionError as e:
                extra.append(str(e))
            hrec, crec = hend.pop("battleEnd"), cend.pop("battleEnd")
            hdeb, cdeb = hend.pop("debrief"), cend.pop("debrief")
            print(f"EVIDENCE {rid}: host DebriefingState reached={deb_ok} after {deb_s}s ({deb_after}s from the "
                  f"ending's first step); host battleEnd.emitted={(hrec or {}).get('emitted')}; client at the "
                  f"end of the {CLIENT_LEAVE_S}s window: reached={left_ok} after {left_s}s top={cend['top']} "
                  f"inBattle={cend['inBattle']}; host hold={hold}; pre-ending fails={pre}; ending fails={ending}; "
                  f"boot={boot_info}; staging={staging}; ending={ending_resp}; "
                  f"pre-ending census={census_view(census)}; host battleEnd={hrec}; client battleEnd={crec}; "
                  f"host end={hend}; client end={cend}; host debrief={hdeb}; client debrief={cdeb}; "
                  f"newCrashLogs={new_crash}", flush=True)
            fails = [f"pre-ending: {m}" for m in pre] + [f"ending: {m}" for m in ending]
            fails += row_verdict(rid, expect, hrec, crec, cend, hend, census.get("b0"), cleft, extra,
                                 hold, hdeb, cdeb)
            if fails:
                raise AssertionError(f"{len(fails)} failure(s): " + " | ".join(fails))
            results[rid] = True
            print(f"PASS {rid}", flush=True)
        except Exception as e:
            results[rid] = False
            kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
            print(f"FAIL {rid}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p7-sd1] shutdown {gc.name}: {short(e)}", flush=True)


# ===================== bring-ups =====================


def boot_classic(host, client, port, mission=None, map_fp=MAP_FP):
    """The classic parallel skirmish bring-up (raw.bring_up_lobby +
    session.drive_to_battlescape, seat_count=2), pinned with set_seed SEED_MAP
    right before newbattle_ok, asserted against the baked fingerprint, then
    session.pin_ai_neutral (A cannot act), then hash-clean (W2-P2 SB1's boot)."""
    raw.bring_up_lobby(host, client, port)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=mission, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == map_fp and cs.get("mapFingerprint") == map_fp, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked {map_fp!r} (mission {mission or 'the NEW BATTLE default'}, SEED_MAP {SEED_MAP})")
    assert (hs.get("side"), hs.get("turn")) == (FACTION_PLAYER, 1), (
        f"host (side, turn)={(hs.get('side'), hs.get('turn'))} at bring-up (want ({FACTION_PLAYER}, 1))")
    pinned = pin_ai_neutral(host, client, tag="w2p7-sd1")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (want [{A_ID}])"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    info = {"mission": mission or "default", "mapFingerprint": hs.get("mapFingerprint"), "pinned": pinned}
    print(f"[w2p7-sd1] boot ok: {info}", flush=True)
    return info


def boot_e4(host, client, port):
    """E4: the classic bring-up on TL_MISSION with Coop_TurnLimit_Test active
    on both machines; both machines' logs name the mod as active (no invalid
    mod) and derive the BriefingState deployment TL_MISSION."""
    info = boot_classic(host, client, port, mission=TL_MISSION, map_fp=TL_MAP_FP)
    ml = {gc.name: mod_evidence(gc) for gc in (host, client)}
    for name, m in ml.items():
        assert MOD_ACTIVE_LINE in m["active"] and not m["invalid"] and m["deployment"], (
            f"{name}: {MOD_NAME} not in force (active lines {m['active']}, invalid {m['invalid']}, "
            f"deployment lines {m['deployment']}; want '{MOD_ACTIVE_LINE}', no invalid, '{TL_DEPLOYMENT_LINE}')")
    info["mod"] = ml
    return info


def boot_e5(host, client, port):
    return boot_classic(host, client, port)


def boot_e6(host, client, port):
    """E6: the gm2 bring-up (test_w2_client_pvp's boot): set_seed on the host
    before its NEW BATTLE, the client joins, lobby_set_team puts it on the
    aliens, then repro_pvp_side_relative.drive_to_gm2_battlescape
    (STR_SMALL_SCOUT, set_seed 1 right before newbattle_ok)."""
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    host.ok({"cmd": "set_seed", "seed": SEED_MAP})
    raw.skirmish_host(host, port)
    raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: raw.lobby(host).get("buttonVisible") or None)
    r = host.ok({"cmd": "lobby_set_team", "row": gm2_row_for(host, raw.CLIENT_PLAYER), "team": "Alien"})
    assert r.get("gamemode") == GAMEMODE_PVP, (
        f"lobby_set_team Alien answered gamemode {r.get('gamemode')} (want {GAMEMODE_PVP})")
    time.sleep(1)   # the change_team broadcast settles on the client (repro_pvp_side_relative PHASE 0)
    drive_to_gm2_battlescape(host, client)
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("coopGamemode") == GAMEMODE_PVP and cs.get("coopGamemode") == GAMEMODE_PVP, (
        f"coopGamemode host={hs.get('coopGamemode')} client={cs.get('coopGamemode')} (want {GAMEMODE_PVP})")
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} (STR_SMALL_SCOUT, SEED_MAP {SEED_MAP})")
    ha, ca = hs.get("authority") or {}, cs.get("authority") or {}
    assert (ha.get("localSeat"), ha.get("hostSim"), ca.get("localSeat"), ca.get("hostSim")) == (0, True, 1, False), (
        f"authority host={ha} client={ca} (want host seat 0 hostSim, client seat 1 not hostSim)")
    a = session.units_by_id(hs).get(A_ID) or {}
    assert (a.get("faction"), a.get("coop"), a.get("isOut")) == (FACTION_HOSTILE, 1, False), (
        f"alien {A_ID} at bring-up: faction {a.get('faction')} coop {a.get('coop')} isOut {a.get('isOut')} "
        f"(want a live FACTION_HOSTILE unit of seat 1)")
    pinned = pin_ai_neutral(host, client, tag="w2p7-sd1-gm2")   # 0 is legal in gm2 (REV E.48 SS.B.4)
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="gm2 bring-up")
    info = {"mission": "STR_SMALL_SCOUT gm2", "mapFingerprint": hs.get("mapFingerprint"), "pinned": pinned,
            "authority": {"host": ha, "client": ca}}
    print(f"[w2p7-sd1] boot ok: {info}", flush=True)
    return info


# ===================== main =====================


ROWS = (("E4", boot_e4, stage_none, end_e4, [MOD_DIR]),
        ("E5", boot_e5, stage_e5, end_e5, []),
        ("E6", boot_e6, stage_e6, end_e6, []),
        ("E6b", boot_e6, stage_none, end_e6b, []))


def main():
    t0 = time.time()
    results = {}
    for rid, boot_fn, stage_fn, end_fn, mods in ROWS:
        run_row(rid, boot_fn, stage_fn, end_fn, mods, results)
    order = [r[0] for r in ROWS]
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_battle_end_rules: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
