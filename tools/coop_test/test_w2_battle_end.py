"""W2-P7 S-A + S-B1 + S-B2 - test_w2_battle_end.py: when a co-op battle ends
on the host, the host sends one terminal `battle_end` event, the skirmish
client leaves the battle with it, the client then shows the host's own
debriefing in a display-only DebriefingState, and each player leaves its own
debriefing with its own OK (spec rewrite/prompts/w2p7_battle_end.md sections
(a), (b)2-7, (b)9, (f), the W2-P7 plan review's section 2 assertion map and
PINNED S-A stage text, AMENDMENT P7-1 rulings ST1-ST8, AMENDMENT P7-2's
rulings G1-G8 and PINNED S-B1 text, AMENDMENT P7-3's pin fixes G9-G14,
AMENDMENT P7-4's PINNED S-B2 text with its gaps H1-H3; owner rulings
D129 = (a), D156 = (a)).

Before W2-P7 only the host left: the host reached its DebriefingState and the
client stayed on the battle map (F387, F431; TASK 0 T0-1 = F1980/F1981).
Stage S-A: the host's one hook at the top of BattlescapeState::finishBattle
emits `battle_end` {reason, aborted, inExitArea, perSeatVerdict, tally, h}
through CoopEmit::sendEv; the client's applier only records it and arms a
latch, and the pump consumer after the drain takes the teardown snapshots and
tears the client's battle down (never from the apply path). Stage S-B1 (G1-G4):
at the end of its own DebriefingState::init the host sends one non-seq
`bt_debrief_result` (the content its vanilla debrief computed); the client
stores it in either arrival order, its consumer keeps the latch armed until
both `battle_end` and the payload are there, and then shows a display-only
DebriefingState filled from the payload (no prepareDebriefing, no world
write, no save; Sell/Transfer hidden). No OK is pressed on either machine in
E1/E2; E3/E3b press both OKs in the two orders (the leave order, S-B2,
D156). Four rows, ONE boot each (one ending per boot):

  E1  T1, the last alien down, battleAutoEnd OFF (the default). The host runs
      battle_action kill_unit_real on A (the default map's only alien; ST7 (a),
      the W2-P2 SB1 lever), then END TURN client then host, then the host
      closes its NextTurnState (dismiss_popup -> NextTurnState::close ->
      finishBattle(false, liveSoldiers)). Expected record (T0-2, F1982):
      reason aliensDown, aborted false, inExitArea 7, verdict win for seats 0
      and 1, tally {liveAliens 0, liveSoldiers 7, inExit 0}.
  E2  T6, the host aborts. battle_action abort -> AbortMissionState ->
      dismiss_popup (AbortMissionState::btnOkClick -> setAborted(true) +
      finishBattle(true, inExit)). Expected record (T0-2, F1983): reason abort,
      aborted true, inExitArea 0, verdict abort for seats 0 and 1, tally
      {liveAliens 1, liveSoldiers 7, inExit 0}.
  E3  S-B2, the client leaves first: E2's ending (the host abort) on its own
      boot with E2's pins, the whole S-A + S-B1 verdict as the precondition
      (both machines on their debriefings), then the CLIENT presses its
      debriefing OK, then the HOST presses its own.
  E3b S-B2, the host leaves first: E1's ending (the last alien down) on its
      own boot with E1's pins, the same precondition, then the HOST presses
      its debriefing OK, then the CLIENT presses its own.
  E3 and E3b are the pre-rewrite contract's two orders
  (test_skirmish_end_main_menu.py :1-45, F2197). Owner D156 (a): each
  debriefing stays until that player presses OK; nobody waits, nobody loses
  a screen.

The `battleEnd` record (event_state.battleEnd, CoopDelta.h) is SESSION-
LIFETIME (ST4 (a), F1895): cleared only by initBattleAuthority(), so it is
still readable after both machines' disconnect resets at a skirmish end.

Pre-ending checks (every row; a failure here is a bring-up or staging failure,
reported with the prefix "pre-ending", never the row's verdict): the pinned
map (MAP_FP), pin_ai_neutral, hash_now {full:true} ALL buckets EQUAL on both
machines right before the ending action, desyncSeen false on both, the host's
coopClientBStatePushes 0, the client's read as b0, both machines' battleEnd
record present with emitted 0 and applied 0. The ending's own steps (END TURN
presses, the host's NextTurnState / AbortMissionState confirm) and the host's
DebriefingState within DEBRIEF_S are reported with the prefix "ending".

Row verdict (the S-A assertion set, review section 2, with AMENDMENT P7-2
R4's re-points a-c and new rows f-k):
  host    battleEnd emitted 1, seq > 0, reason / aborted / inExitArea /
          perSeatVerdict / tally as the row expects, actionIdAtEmit 0,
          evsAfter 0, stageSkips 0, hBuckets = the 9 action-end bucket names
          (8 structured + saveBlob); quiescentAtEmit is recorded only (F1911);
          the host's stack still holds DebriefingState; coopClientBStatePushes
          0 and desyncSeen false. S-B1 (f) the host hold: sampled every 0.25 s
          for HOST_HOLD_S after the client's end state, the host's top stays
          DebriefingState (no CoopState(20) "has left the server", F2011,
          F2055); (g) battleEnd resultSent 1, resultBytes > 0, resultDropped 0,
          debriefDisplayOnly 0; (i) debrief_state shown, on top, not
          display-only, widgets {19 texts, 5 lists, 4 buttons}, page 0,
          parseErrors 0, and title / recoveryHeader / rows / total / rating /
          soldiers / recovered equal to the row's HOST_DEBRIEF pin.
  client  battleEnd applied 1 with the host's seq and the row's reason /
          aborted / inExitArea / perSeatVerdict / tally, skirmish true,
          teardownInDrain false, latchedMs > 0 and tornDownMs >= latchedMs
          (F1909: latch and teardown share one pump pass), desyncAtTeardown
          false, bstatePushesAtTeardown == b0, queueDepthAtTeardown 0,
          lastSeqApplied == the host's seq, hashVerify {seq = the host's seq,
          kind battle_end, buckets = the host's hBuckets}; top DebriefingState
          (the wait ends on DebriefingState or MainMenuState within
          CLIENT_LEAVE_S of the host's DebriefingState), world_state has_save
          true (the skirmish SavedGame lives until S-B2's OK, G4),
          battle_state inBattle false, event_state phase Idle. S-B1 (h)
          battleEnd resultReceived 1, resultBytes == the host's and > 0,
          resultReceivedMs > 0, tornDownMs >= resultReceivedMs (G3: the
          teardown waited for the payload), resultDropped 0,
          debriefDisplayOnly 1; (j) debrief_state shown, on top,
          display-only, the same widget census, page 0, parseErrors 0, and
          every one of the seven content fields equal to the host's.
  E1 only (k) the page walk, client then host: STATS then LOOT (real clicks
          through click_widget, no OK), page 2 reached on both; the client's
          SELL and TRANSFER hidden; the host's SELL shown (the positive
          control) and its TRANSFER == HOST_E1_PAGE2_TRANSFER.
  both    no client save file (assert_client_zero_disk), no new crash log.

S-B2 leave rows (E3 / E3b only, AMENDMENT P7-4 R2; F = the machine that
presses OK first per LEAVE_FIRST, S = the other; every OK is dismiss_popup ->
DebriefingState::btnOkClick, pressed only when that machine's top is
DebriefingState):
  L1  F's OK pressed and handled by DebriefingState.
  L2  F reaches the main menu (top MainMenuState AND coopStatic false: its
      MainMenuState::init ran, F2189) within OK_LEAVE_S; has_save false,
      phase Idle.
  L3  F's battleEnd record: debriefOk 1, debriefOkBranch = F's name,
      phaseAtOk = PHASE_AT_OK, phaseAfterOk Idle, resetAtOk 1 on the host
      only, popupSuppressed 0.
  L4  the client's "[exit] stale SavedGame" log lines (the issue #82 heal,
      MainMenuState.cpp :405) do not grow over the whole leave: the client
      leaves through GoToMainMenuState.
  L5  the leave reaches S within PEER_S (a CoopState on its stack, or its
      record's popupSuppressed >= 1).
  L6  S's top stays DebriefingState for HOST_HOLD_S (sampled every 0.25 s).
  L7  S before its OK: top DebriefingState, no CoopState anywhere on its
      stack, no LobbyMenu, has_save true, phase Idle; the client as S also
      coopStatic false (the host as S keeps listening, F2188: recorded only).
  L8  S's record: popupSuppressed 1, popupSuppressedCode = SUPPRESSED_CODE
      (20 host, 21 client), debriefOk 0.
  L9  S's debrief_state: shown and on top, display-only iff S is the client,
      every content field equal to S's debriefing before F's OK.
  L10 S's OK pressed and handled by DebriefingState.
  L11 S reaches the main menu the same way; has_save false, phase Idle.
  L12 S's record after its OK: debriefOk 1, debriefOkBranch = S's name,
      phaseAtOk = PHASE_AT_OK, phaseAfterOk Idle, resetAtOk 1 on the host
      only, popupSuppressed 1.
  L13 the host's record: debriefHostMarked 1.
  L14 no new crash log over the leave, no client save file.
PHASE_AT_OK: E3's host reads Idle (the client's leave already reset its
battle scope, F2182, H2 (a)); E3b's host reads Ended (its own OK's reset
clears it, Q10 (a)); the client reads Idle in both. Each leave prints ONE
"EVIDENCE <id> leave:" line (both machines' views with their records, S's
debrief_state, both OK responses and waits, S's hold, the stale-save counts
before -> after for both machines) before its verdict. The host's stale-save
delta is evidence only (vanilla's own skirmish exit heals the host, F2183).

The HOST_DEBRIEF pins (R6, AMENDMENT P7-3): each row's host debrief_state
content, copied verbatim from one capture run on the S-B1.1 build, with
`soldiers` pinned as each row's deltas in order (the row count and the stat
gains; soldier names change per boot and are compared host-to-client only,
G10), and E2's `rows` pinned as [] (no page-1 row on an abort with nothing
killed, lost or recovered, G11; E1 needs at least one). HOST_E1_PAGE2_TRANSFER
comes from one scratch capture that closes the host's CoopState(20) before
the host's page walk (G12). The committed red run reproduces every pinned
host value.

RED-THEN-GREEN (spec (d), review section 3 DONE-WHEN, AMENDMENT P7-2
DONE-WHEN). S-A.1 / S-A.2: each row failed on host battleEnd.emitted 0 AND the
client still in battle, then both rows passed. Commit S-B1.1 (this file's
S-B1 rows, the debrief_state probe, the record's result keys - no product
behaviour) is run ONCE and each row fails on exactly the S-B1 red: the client
top MainMenuState and has_save false (S-A's interim end), the host hold and
the host's top showing CoopState (F2011), the host's resultSent / resultBytes
0 and the client's resultReceived / resultBytes / resultReceivedMs /
debriefDisplayOnly 0, and the client's debrief_state not shown (shown, onTop,
displayOnly false, widgets {0, 0, 0}, page -1, and every content field whose
host value is non-empty); E1 also records both page walks as not run. Commit
S-B1.2 (the product) is run ONCE and both rows pass. Commit S-B2.1 (rows
E3/E3b and the record's leave keys - no product behaviour) is run ONCE: E1
and E2 pass, and E3 and E3b pass every S-A / S-B1 assertion and L1, L2, L5,
and fail on exactly the S-B2 red, 15 lines each. E3: the client's
debriefOk / debriefOkBranch / phaseAtOk / phaseAfterOk unset (vanilla's OK
ran), the client's stale-save line (vanilla's OK heals), the host's
CoopState(20) (the hold, its top, one CoopState dialog, debrief_state onTop
false), the host's popupSuppressed / popupSuppressedCode 0, the host's OK not
pressed (its end state and its record after the OK not checked), and the
host's debriefHostMarked 0. E3b: the host's debriefOk / debriefOkBranch /
phaseAtOk / phaseAfterOk / resetAtOk unset, the client's CoopState(21) (the
hold, its top, one CoopState dialog, debrief_state onTop false), the
client's popupSuppressed / popupSuppressedCode 0, the client's OK not pressed
(end state and record not checked), and the host's debriefHostMarked 0.
Commit S-B2.2 (the product) is run ONCE and all four rows pass. Each row
prints ONE "EVIDENCE <id>:" line with both machines' records, tops, host
hold, both debriefs, the page walks and the pre-ending census BEFORE its
verdict is checked (E3/E3b also the "EVIDENCE <id> leave:" line); main() runs
every row even after an earlier one failed and prints "PASS <id>" /
"FAIL <id>: <message>". Every wait is bounded; a wait that runs out is
recorded and fails the row.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot per
row, no alternative map or actor. Exit 0 only when all four rows pass, 2
otherwise.

Run:  python tools/coop_test/test_w2_battle_end.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw

# ----- the default NEW BATTLE map, pinned (W2-P2 TASK 0a round 1; test_w2_delta_items) -----
SEED_MAP = 1
MAP_FP = -4.48310638993e+18      # host battle_state.mapFingerprint on SEED_MAP 1
A_ID = 1000000                   # the only alien: Sectoid Soldier, spawn (27,12,0) dir 5, health 30
STATUS_DEAD = 6                  # src/Mod/Unit.h enum UnitStatus

# ----- W2-P7 constants -----
# The `h` every bt_action_end carries (coopBuildActionEndHash): the 8 structured
# buckets (SharedEcon battleHashBucketName) + saveBlob.
H_BUCKETS = sorted(["terrain", "fire", "smoke", "items", "unitsCore", "unitsStats", "itemIdCtr", "synced",
                    "saveBlob"])
DEBRIEF_S = 30        # host DebriefingState after the ending's confirm (T0-1: <= 0.05 s)
CLIENT_LEAVE_S = 30   # client end state (CLIENT_END_TOPS) after the host's DebriefingState (review section 2)
ROW_EXPECT = {
    # T0-2 (F1982): finishBattle(false, 7) from NextTurnState::close, isAborted() false.
    "E1": {"reason": "aliensDown", "aborted": False, "inExitArea": 7,
           "verdicts": [(0, "win"), (1, "win")],
           "tally": {"liveAliens": 0, "liveSoldiers": 7, "inExit": 0}},
    # T0-2 (F1983): finishBattle(true, 0) from AbortMissionState::btnOkClick, isAborted() true.
    "E2": {"reason": "abort", "aborted": True, "inExitArea": 0,
           "verdicts": [(0, "abort"), (1, "abort")],
           "tally": {"liveAliens": 1, "liveSoldiers": 7, "inExit": 0}},
}
ROW_PORT = {"E1": "48766", "E2": "48767", "E3": "48768", "E3b": "48769"}
IN_BATTLE_TOPS = ("BattlescapeState", "NextTurnState")

# ----- W2-P7 S-B1 constants (AMENDMENT P7-2 R4) -----
CLIENT_END_TOPS = ("DebriefingState", "MainMenuState")   # the client wait ends on either; the row asserts DebriefingState
HOST_HOLD_S = 3       # the host's top sampled every 0.25 s for this long after the client's end state (F2055)
PAGE_S = 10           # each STATS / LOOT page change of E1's page walk
DEBRIEF_WIDGETS = {"texts": 19, "lists": 5, "buttons": 4}   # DebriefingState.cpp :144-174 (F2049)
DEBRIEF_FIELDS = ("title", "recoveryHeader", "rows", "total", "rating", "soldiers", "recovered")
# G11 (F2031): these rows' host page 1 has at least one row; the other rows pin `rows` as [].
ROWS_WITH_PAGE1 = ("E1", "E3b")
# R6: each row's host debrief_state content, copied verbatim from the capture run on the S-B1.1 build
# (pin_view: `soldiers` as each row's deltas, G10).
HOST_DEBRIEF = {
    # R6 capture A (S-B1.1 build): E1 = T1, the last alien down.
    "E1": {"title": "UFO is recovered", "recoveryHeader": "UFO RECOVERY",
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
    # R6 capture A: E2 = T6, the host abort (no page-1 row, G11).
    "E2": {"title": "UFO is not recovered", "recoveryHeader": "", "rows": [], "total": 0, "rating": "RATING> POOR!",
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
# R6 / G12: E1's host page-2 TRANSFER visibility (vanilla :377), from one scratch capture that closed the
# host's CoopState(20) before the host's page walk.
HOST_E1_PAGE2_TRANSFER = False

# ----- W2-P7 S-B2 constants (AMENDMENT P7-4 R2) -----
# E3 / E3b replay E2's / E1's ending on their own boot (the same pins), then press the two OKs in order.
ROW_EXPECT["E3"] = ROW_EXPECT["E2"]
ROW_EXPECT["E3b"] = ROW_EXPECT["E1"]
HOST_DEBRIEF["E3"] = HOST_DEBRIEF["E2"]
HOST_DEBRIEF["E3b"] = HOST_DEBRIEF["E1"]
LEAVE_FIRST = {"E3": "client", "E3b": "host"}   # who presses OK first (owner D156 (a))
# The battle phase each machine's OK reads before any reset. E3's host: Idle - the client's leave already reset its
# battle scope (F2182, H2 (a)). E3b's host: Ended - its own OK's reset clears it (Q10 (a)).
PHASE_AT_OK = {"E3": {"client": "Idle", "host": "Idle"}, "E3b": {"host": "Ended", "client": "Idle"}}
SUPPRESSED_CODE = {"host": 20, "client": 21}     # the dialog each machine would have pushed on the peer's leave
OK_LEAVE_S = 10   # a machine's main menu (top MainMenuState AND coopStatic false) after its own OK
PEER_S = 10       # the other machine handles the leave (a CoopState on its stack, or its record's popupSuppressed >= 1)
STALE_SAVE = "[exit] stale SavedGame reached the main menu"   # MainMenuState.cpp :405, the issue #82 heal


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


def record(gc):
    """This machine's event_state.battleEnd (None when the field is absent)."""
    return event_state(gc).get("battleEnd")


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


def page_walk(gc):
    """S-B1 row k (E1 only): on this machine's DebriefingState press STATS, wait
    for page 1, press LOOT, wait for page 2 (real SDL clicks through
    click_widget; no OK is pressed) and keep the page-2 debrief_state."""
    name = gc.name
    t = top(gc)
    if t != "DebriefingState":
        return {"run": False, "note": f"{name} page walk not run: {name} top {t}"}
    out = {"run": True, "steps": [], "reached2": False, "debrief": None}
    for match, want in (("stats", 1), ("loot", 2)):
        r = gc.cmd({"cmd": "click_widget", "match": match})
        ok, secs = wait_until(lambda: gc.cmd({"cmd": "debrief_state"}).get("page") == want, PAGE_S, 0.1)
        out["steps"].append({"match": match, "click": {k: r.get(k) for k in ("ok", "error", "text")},
                             "page": want, "reached": ok, "secs": secs})
        if not ok:
            break
    out["reached2"] = out["steps"][-1]["page"] == 2 and out["steps"][-1]["reached"]
    out["debrief"] = gc.cmd({"cmd": "debrief_state"})
    return out


def pages_view(p):
    """The EVIDENCE form of a page walk: run flag, steps, and page-2 page / SELL / TRANSFER."""
    if not isinstance(p, dict):
        return p
    d = p.get("debrief") or {}
    return {"run": p.get("run"), "note": p.get("note"), "steps": p.get("steps"), "reached2": p.get("reached2"),
            "page": d.get("page"), "sellVisible": d.get("sellVisible"), "transferVisible": d.get("transferVisible")}


def coop(gc):
    return gc.cmd({"cmd": "get_coop"})


def log_count(gc, literal):
    """Lines of this machine's openxcom.log holding `literal` (0 when unreadable)."""
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for ln in f if literal in ln)
    except OSError:
        return 0


def leave_view(gc):
    """S-B2: one machine's state around a debriefing OK (every field from an existing probe)."""
    c = coop(gc)
    es = event_state(gc)
    ws = gc.cmd({"cmd": "world_state"})
    info = gc.cmd({"cmd": "coop_dialog_info"})
    return {"top": top(gc), "stack": stack(gc),
            "coopDialogs": gc.cmd({"cmd": "coop_dialog_count", "code": -1}).get("count"),
            "dialog": {k: info.get(k) for k in ("present", "code", "title")},
            "onConnect": c.get("onConnect"), "coopStatic": c.get("coopStatic"), "hasSave": ws.get("has_save"),
            "phase": es.get("phase"), "battleEnd": es.get("battleEnd")}


def press_ok(gc):
    """S-B2: press this machine's debriefing OK (dismiss_popup -> DebriefingState::btnOkClick) only when its top is
    DebriefingState; never dismisses anything else."""
    t = top(gc)
    if t != "DebriefingState":
        return {"pressed": False, "note": f"{gc.name} OK not pressed: {gc.name} top {t}"}
    r = gc.cmd({"cmd": "dismiss_popup"})
    return {"pressed": True, "resp": {k: r.get(k) for k in ("ok", "handled", "error")}}


def left_menu(gc):
    """Top MainMenuState and the connection closed: MainMenuState::init (and its disconnect) has run (F2189)."""
    return top(gc) == "MainMenuState" and coop(gc).get("coopStatic") is False


def peer_handled(gc):
    """The peer's leave reached this machine: a CoopState on its stack, or its record counted a silent teardown."""
    n = gc.cmd({"cmd": "coop_dialog_count", "code": -1}).get("count") or 0
    return n > 0 or ((record(gc) or {}).get("popupSuppressed") or 0) >= 1


def top_hold(gc):
    """S-B2 (host_hold for either machine): the distinct non-DebriefingState tops seen while sampling this machine's
    top every 0.25 s for HOST_HOLD_S ([] = its debriefing held the top throughout)."""
    seen = []
    t0 = time.time()
    while True:
        t = top(gc)
        if t != "DebriefingState" and t not in seen:
            seen.append(t)
        if time.time() - t0 >= HOST_HOLD_S:
            return seen
        time.sleep(0.25)


def host_chain_done(host):
    """HOST only: A is DEAD, no BState is queued or running, BattlescapeState on top."""
    bs = battle_state(host)
    a = session.units_by_id(bs).get(A_ID) or {}
    return (a.get("status") == STATUS_DEAD and bs.get("pendingStates") == 0 and not bs.get("isBusy")
            and top(host) == "BattlescapeState")


# ===================== the rows' staging and endings =====================


def stage_e1(host, client, pre):
    """E1 staging: the host kills A (the map's only alien) through the real
    UnitDieBState chain and both machines settle."""
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": A_ID})
    if not r.get("ok") or r.get("killed") != [A_ID]:
        pre.append(f"kill_unit_real answered {r} (want ok, killed [{A_ID}])")
    ok, secs = wait_until(lambda: host_chain_done(host), 30, 0.1)
    if not ok:
        pre.append(f"host kill chain not finished (A DEAD, no BState, BattlescapeState on top) within {secs}s")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        pre.append(f"wait_host_idle after the kill: {short(e)}")
    return {"kill": r, "chainS": secs}


def end_e1(host, client, ending):
    """E1 ending: END TURN client then host; the host's NextTurnState closes
    (NextTurnState::close -> finishBattle)."""
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
    ok, secs = wait_until(lambda: "NextTurnState" in host.cmd({"cmd": "list_widgets"}).get("state", ""), 30, 0.1)
    if not ok:
        ending.append(f"host NextTurnState not up within {secs}s after both END TURN presses")
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "NextTurnState->close":
        ending.append(f"host dismiss_popup answered {d} (want handled NextTurnState->close)")
    return {"close": d}


def stage_e2(host, client, pre):
    """E2 staging: none (the abort ends the battle as it stands)."""
    return {}


def end_e2(host, client, ending):
    """E2 ending: the host's abort and its confirm (AbortMissionState::btnOkClick
    -> setAborted(true) + finishBattle(true, inExit))."""
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


def pin_view(deb):
    """The pinned form of a debrief_state (AMENDMENT P7-3 G10, F2030): the seven
    content fields, with `soldiers` reduced to each row's deltas in order (the
    row count and the stat gains) - soldier names change per boot, so they are
    compared host-to-client only (row j), never pinned."""
    deb = deb if isinstance(deb, dict) else {}
    out = {k: deb.get(k) for k in DEBRIEF_FIELDS}
    out["soldiers"] = [s.get("deltas") for s in (deb.get("soldiers") or []) if isinstance(s, dict)]
    return out


SEAT_PREFIXES = tuple(f"[{n}] " for n in (raw.HOST_PLAYER, raw.CLIENT_PLAYER))   # AUD-A07: the page-2 seat prefixes


def debrief_view(deb):
    """Row j's view (W2-A0712 Q5 a, PR-10): DEBRIEF_FIELDS, each page-2 name's leading SEAT_PREFIXES entry removed."""
    def bare(n):
        return next((n[len(p):] for p in SEAT_PREFIXES if isinstance(n, str) and n.startswith(p)), n)
    out = {k: (deb if isinstance(deb, dict) else {}).get(k) for k in DEBRIEF_FIELDS}
    if isinstance(out["soldiers"], list):
        out["soldiers"] = [dict(s, name=bare(s.get("name"))) if isinstance(s, dict) else s for s in out["soldiers"]]
    return out


def debrief_verdict(rid, hrec, crec, hdeb, cdeb, hold):
    """AMENDMENT P7-2 R4 rows f-j (S-B1); returns the list of failures."""
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
        hpin = pin_view(hdeb)
        for k in DEBRIEF_FIELDS:
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


def pages_verdict(pages):
    """AMENDMENT P7-2 R4 row k (E1 only); returns the list of failures."""
    f = []
    for name in ("client", "host"):
        p = pages.get(name) or {}
        if not p.get("run"):
            f.append(p.get("note") or f"{name} page walk not run")
            continue
        d = p.get("debrief") or {}
        if not p.get("reached2"):
            f.append(f"{name} page walk: page 2 not reached (steps {p.get('steps')})")
        if name == "client":
            if d.get("sellVisible") is not False:
                f.append(f"client page 2 sellVisible={d.get('sellVisible')!r} (want False)")
            if d.get("transferVisible") is not False:
                f.append(f"client page 2 transferVisible={d.get('transferVisible')!r} (want False)")
        else:
            if d.get("sellVisible") is not True:
                f.append(f"host page 2 sellVisible={d.get('sellVisible')!r} (want True - vanilla :376 positive control)")
            if d.get("transferVisible") != HOST_E1_PAGE2_TRANSFER:
                f.append(f"host page 2 transferVisible={d.get('transferVisible')!r} "
                         f"(want the pinned {HOST_E1_PAGE2_TRANSFER!r})")
    return f


def leave_row(rid, host, client, hdeb, cdeb):
    """S-B2 (AMENDMENT P7-4 R2 item 4): with both machines on their debriefings, the machine named by LEAVE_FIRST
    presses its OK, the other handles that leave while it keeps reading its debriefing, then presses its own OK.
    Returns (evidence, failures) - failures = rows L1-L13 (run_row adds L14)."""
    first_name = LEAVE_FIRST[rid]
    first, second = (client, host) if first_name == "client" else (host, client)
    stale0 = {"host": log_count(host, STALE_SAVE), "client": log_count(client, STALE_SAVE)}
    ok1 = press_ok(first)
    left1 = wait_until(lambda: left_menu(first), OK_LEAVE_S, 0.1) if ok1["pressed"] else (False, 0)
    seen = wait_until(lambda: peer_handled(second), PEER_S, 0.1)
    hold2 = top_hold(second)
    v1 = leave_view(first)
    v2 = leave_view(second)
    deb2 = second.cmd({"cmd": "debrief_state"})
    ok2 = press_ok(second)
    left2 = wait_until(lambda: left_menu(second), OK_LEAVE_S, 0.1) if ok2["pressed"] else (False, 0)
    v2end = leave_view(second)
    stale1 = {"host": log_count(host, STALE_SAVE), "client": log_count(client, STALE_SAVE)}
    pre_deb = hdeb if second is host else cdeb
    evidence = {"first": first_name, "ok1": ok1, "left1": left1, "seen": seen, "hold2": hold2,
                "v1": v1, "v2": v2, "deb2": deb2, "ok2": ok2, "left2": left2, "v2end": v2end,
                "staleSave": {n: f"{stale0[n]} -> {stale1[n]}" for n in ("host", "client")}}
    failures = leave_verdict(rid, first_name, ok1, left1, v1, stale0, stale1, seen, hold2, v2, deb2, pre_deb,
                             ok2, left2, v2end)
    return evidence, failures


def leave_verdict(rid, first_name, ok1, left1, v1, stale0, stale1, seen, hold2, v2, deb2, pre_deb, ok2, left2,
                  v2end):
    """AMENDMENT P7-4 R2 item 5, rows L1-L13 (F = the machine that pressed OK first, S = the other); one failure
    line per failing field, both values printed. Returns the list of failures."""
    f = []
    F = first_name
    S = "host" if F == "client" else "client"
    rec1 = v1.get("battleEnd") if isinstance(v1.get("battleEnd"), dict) else {}
    rec2 = v2.get("battleEnd") if isinstance(v2.get("battleEnd"), dict) else {}
    rec2end = v2end.get("battleEnd") if isinstance(v2end.get("battleEnd"), dict) else {}
    deb2 = deb2 if isinstance(deb2, dict) else {}
    pre_deb = pre_deb if isinstance(pre_deb, dict) else {}
    # L1: F's OK
    if not ok1.get("pressed"):
        f.append(ok1.get("note"))
    elif (ok1.get("resp") or {}).get("handled") != "DebriefingState":
        f.append(f"{F} OK answered {ok1.get('resp')} (want handled DebriefingState)")
    # L2: F left for the main menu
    if not left1[0]:
        f.append(f"{F} did not reach the main menu (top MainMenuState, coopStatic false) within {OK_LEAVE_S}s of its "
                 f"OK ({left1[1]}s): top={v1.get('top')} coopStatic={v1.get('coopStatic')}")
    if v1.get("hasSave") is not False:
        f.append(f"{F} world_state.has_save={v1.get('hasSave')!r} after its OK (want False)")
    if v1.get("phase") != "Idle":
        f.append(f"{F} event_state.phase={v1.get('phase')!r} after its OK (want 'Idle')")
    # L3: F's record after its OK
    want1 = (("debriefOk", 1), ("debriefOkBranch", F), ("phaseAtOk", PHASE_AT_OK[rid][F]), ("phaseAfterOk", "Idle"),
             ("resetAtOk", 1 if F == "host" else 0), ("popupSuppressed", 0))
    for k, want in want1:
        if rec1.get(k) != want:
            f.append(f"{F} battleEnd.{k}={rec1.get(k)!r} after its OK (want {want!r})")
    # L4: the client's stale-save lines over the whole leave (the issue #82 heal never fires on the client's route)
    grew = stale1["client"] - stale0["client"]
    if grew != 0:
        f.append(f"client stale-save lines grew by {grew} over the leave ({stale0['client']} -> {stale1['client']}; "
                 f"want 0: the client leaves through GoToMainMenuState)")
    # L5: the leave reached S
    if not seen[0]:
        f.append(f"the leave never reached {S} within {PEER_S}s: no CoopState and popupSuppressed 0")
    # L6: S's debriefing keeps the top
    if hold2 != []:
        f.append(f"{S} hold saw {hold2} within {HOST_HOLD_S}s after {F}'s OK (want [] - {S}'s top DebriefingState "
                 f"throughout)")
    # L7: S before its OK
    if v2.get("top") != "DebriefingState":
        f.append(f"{S} top={v2.get('top')} before its OK (want DebriefingState)")
    if v2.get("coopDialogs") != 0:
        f.append(f"{S} coop_dialog_count={v2.get('coopDialogs')} before its OK (want 0; dialog {v2.get('dialog')})")
    if any("LobbyMenu" in s for s in (v2.get("stack") or [])):
        f.append(f"{S} stack {v2.get('stack')} holds LobbyMenu before its OK")
    if v2.get("hasSave") is not True:
        f.append(f"{S} world_state.has_save={v2.get('hasSave')!r} before its OK (want True)")
    if v2.get("phase") != "Idle":
        f.append(f"{S} event_state.phase={v2.get('phase')!r} before its OK (want 'Idle')")
    if S == "client" and v2.get("coopStatic") is not False:
        f.append(f"client coopStatic={v2.get('coopStatic')!r} before its OK (want False - its host left)")
    # L8: S's record before its OK
    for k, want in (("popupSuppressed", 1), ("popupSuppressedCode", SUPPRESSED_CODE[S]), ("debriefOk", 0)):
        if rec2.get(k) != want:
            f.append(f"{S} battleEnd.{k}={rec2.get(k)!r} before its OK (want {want!r})")
    # L9: S's debriefing (nobody loses a screen)
    for k, want in (("shown", True), ("onTop", True), ("displayOnly", S == "client")):
        if deb2.get(k) is not want:
            f.append(f"{S} debrief_state.{k}={deb2.get(k)!r} before its OK (want {want!r})")
    for k in DEBRIEF_FIELDS:
        if deb2.get(k) != pre_deb.get(k):
            f.append(f"{S} debrief_state.{k}={deb2.get(k)!r} != its debriefing before {F}'s OK {pre_deb.get(k)!r}")
    # L10: S's OK
    if not ok2.get("pressed"):
        f.append(ok2.get("note"))
    elif (ok2.get("resp") or {}).get("handled") != "DebriefingState":
        f.append(f"{S} OK answered {ok2.get('resp')} (want handled DebriefingState)")
    # L11: S left for the main menu
    if not ok2.get("pressed"):
        f.append(f"{S} end state not checked: OK not pressed")
    else:
        if not left2[0]:
            f.append(f"{S} did not reach the main menu (top MainMenuState, coopStatic false) within {OK_LEAVE_S}s of "
                     f"its OK ({left2[1]}s): top={v2end.get('top')} coopStatic={v2end.get('coopStatic')}")
        if v2end.get("hasSave") is not False:
            f.append(f"{S} world_state.has_save={v2end.get('hasSave')!r} after its OK (want False)")
        if v2end.get("phase") != "Idle":
            f.append(f"{S} event_state.phase={v2end.get('phase')!r} after its OK (want 'Idle')")
    # L12: S's record after its OK
    if not ok2.get("pressed"):
        f.append(f"{S} record after the OK not checked: OK not pressed")
    else:
        want2 = (("debriefOk", 1), ("debriefOkBranch", S), ("phaseAtOk", PHASE_AT_OK[rid][S]),
                 ("phaseAfterOk", "Idle"), ("resetAtOk", 1 if S == "host" else 0), ("popupSuppressed", 1))
        for k, want in want2:
            if rec2end.get(k) != want:
                f.append(f"{S} battleEnd.{k}={rec2end.get(k)!r} after its OK (want {want!r})")
    # L13: the host's battle-end debriefing was marked (the host's latest view)
    hrec = rec1 if F == "host" else rec2end
    if hrec.get("debriefHostMarked") != 1:
        f.append(f"host battleEnd.debriefHostMarked={hrec.get('debriefHostMarked')!r} (want 1)")
    return f


def row_verdict(rid, expect, hrec, crec, cend, hend, b0, cleft, extra, hold, hdeb, cdeb, pages):
    """Every S-A assertion of the row with AMENDMENT P7-2 R4's re-points a-c and
    new rows f-k; returns the list of failures (empty = pass)."""
    f = []
    hrec = hrec if isinstance(hrec, dict) else {}
    crec = crec if isinstance(crec, dict) else {}
    # --- the host's emission, the client's end state reached (row a) ---
    if hrec.get("emitted") != 1:
        f.append(f"host battleEnd.emitted={hrec.get('emitted')} (want 1)")
    if not cleft["ok"]:
        f.append(f"client reached neither DebriefingState nor MainMenuState within {CLIENT_LEAVE_S}s of the "
                 f"host's DebriefingState ({cleft['secs']}s): top={cend['top']} inBattle={cend['inBattle']}")
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
    # --- client end state (rows b-d: the display-only debrief, G4) ---
    if cend["top"] != "DebriefingState":
        f.append(f"client top={cend['top']} (want DebriefingState)")
    if cend["hasSave"] is not True:
        f.append(f"client world_state.has_save={cend['hasSave']} (want true)")
    if cend["inBattle"] is not False:
        f.append(f"client battle_state.inBattle={cend['inBattle']} (want false)")
    if cend["phase"] != "Idle":
        f.append(f"client event_state.phase={cend['phase']} (want Idle)")
    # --- S-B1 rows f-j, and k for E1 ---
    f += debrief_verdict(rid, hrec, crec, hdeb, cdeb, hold)
    if pages is not None:
        f += pages_verdict(pages)
    f += extra
    return f


def run_row(rid, stage_fn, end_fn, results):
    expect = ROW_EXPECT[rid]
    host = GameClient("host", 49892, make_user_dir(f"w2p7_battle_end_{rid}_host"))
    client = GameClient("client", 49893, make_user_dir(f"w2p7_battle_end_{rid}_client"))
    try:
        try:
            boot(host, client, ROW_PORT[rid])
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
                ending.append(f"host DebriefingState not reached within {deb_s}s of the ending's confirm")
            deb_after = round(time.time() - t_end, 2)
            left_ok, left_s = wait_until(lambda: top(client) in CLIENT_END_TOPS, CLIENT_LEAVE_S, 0.25)
            cleft = {"ok": left_ok, "secs": left_s}
            hold = host_hold(host)
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
            pages = None
            if rid == "E1":
                pages = {"client": page_walk(client), "host": page_walk(host)}
            pages_ev = {k: pages_view(v) for k, v in pages.items()} if pages else None
            print(f"EVIDENCE {rid}: host DebriefingState reached={deb_ok} after {deb_s}s ({deb_after}s from the "
                  f"ending's first step); host battleEnd.emitted={(hrec or {}).get('emitted')}; client at the "
                  f"end of the {CLIENT_LEAVE_S}s window: reached={left_ok} after {left_s}s top={cend['top']} "
                  f"inBattle={cend['inBattle']}; host hold={hold}; pre-ending fails={pre}; ending fails={ending}; "
                  f"staging={staging}; ending={ending_resp}; pre-ending census={census_view(census)}; "
                  f"host battleEnd={hrec}; client battleEnd={crec}; host end={hend}; client end={cend}; "
                  f"host debrief={hdeb}; client debrief={cdeb}; "
                  f"pages={pages_ev}; "
                  f"newCrashLogs={new_crash}", flush=True)
            fails = [f"pre-ending: {m}" for m in pre] + [f"ending: {m}" for m in ending]
            fails += row_verdict(rid, expect, hrec, crec, cend, hend, census.get("b0"), cleft, extra,
                                 hold, hdeb, cdeb, pages)
            if rid in LEAVE_FIRST:
                # S-B2 (AMENDMENT P7-4 R2 item 6): the leave order, then L14 over the leave.
                lev, lfails = leave_row(rid, host, client, hdeb, cdeb)
                crash2 = session._crash_log_snapshot()
                new_crash2 = sorted(crash2 - crash1)
                if new_crash2:
                    lfails.append(f"new crash log(s) over the leave: {new_crash2}")
                try:
                    session.assert_client_zero_disk(client.user_dir)
                except AssertionError as e:
                    lfails.append(f"after the leave: {e}")
                print(f"EVIDENCE {rid} leave: {lev}; newCrashLogs={new_crash2}", flush=True)
                fails += [f"leave: {m}" for m in lfails]
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
                print(f"[w2p7-sa] shutdown {gc.name}: {short(e)}", flush=True)


# ===================== bring-up =====================


def boot(host, client, port):
    """The classic parallel skirmish bring-up (raw.bring_up_lobby +
    session.drive_to_battlescape, seat_count=2), pinned with set_seed SEED_MAP
    right before newbattle_ok, asserted against the baked MAP_FP, then
    session.pin_ai_neutral (A cannot act), then hash-clean (W2-P2 SB1's boot)."""
    raw.bring_up_lobby(host, client, port)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} (SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p7-sa")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p7-sa] boot ok: MAP_FP={MAP_FP!r} turn={hs.get('turn')} pinned={pinned}", flush=True)


# ===================== main =====================


ROWS = (("E1", stage_e1, end_e1), ("E2", stage_e2, end_e2), ("E3", stage_e2, end_e2),
        ("E3b", stage_e1, end_e1))


def main():
    t0 = time.time()
    results = {}
    for rid, stage_fn, end_fn in ROWS:
        run_row(rid, stage_fn, end_fn, results)
    order = [r[0] for r in ROWS]
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_battle_end: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
