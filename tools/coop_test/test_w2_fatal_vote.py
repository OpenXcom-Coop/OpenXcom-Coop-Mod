"""W2-P7 S-V-A - test_w2_fatal_vote.py: the fatal-wounds question becomes a vote of every player who owns a bleeding
soldier (owner D159; no timeout, D186; the vote pauses everyone, D214 (a)). Spec: docs
rewrite/prompts/w2p7_sv_fatal_vote_design.md (sections 2 and 4, ORCHESTRATOR RULINGS Q1-Q9 (a), SV-M1..SV-M13) as
re-pinned by rewrite/prompts/w2p7_battle_end.md AMENDMENT P7-5 section 4.2 (P7-5 RULINGS Q5-Q11 (a); P7-5b SV-T1..SV-T4).
Constants: docs rewrite/w2p7-sv-task0/CONSTANTS.md (TASK 0 `w2p7-sv-t0`, F4380-F4396).

With battleAutoEnd on, the last alien's death while an X-COM soldier bleeds asks vanilla's "Mission complete. / N of
us is still fatally wounded / End Mission?" (ConfirmEndMissionState, OK / CANCEL). Before S-V-A.2 only the host is asked
(F3225) and a partner's order runs under the host's question (F3226). After it: the host opens the vote at quiescence,
every owner seat of a bleeding soldier answers vanilla's own question on its own machine (OK = yes, CANCEL = no), the
mission ends only on all yes, the first no closes every question (`continue`: the battle ends at END TURN, no second
question), a host that does not vote (or has answered) sits on `CoopFatalVoteHold` with the existing Wait line naming
the voter, and a partner's order or END TURN press made while the vote is open is held and runs only if the battle
continues. This file: rows V0-V6 on the classic boot (test_w2_battle_end.boot: SEED_MAP 1, MAP_FP, A_ID 1000000 the
only alien, pin_ai_neutral, hash-clean). test_w2_fatal_vote_partner.py holds V9 and E6v (SV-T1).

Staging (stage_v, design section 4): host set_option battleAutoEnd true; WS1 = 8 / WS0 = 10 (the lowest seat-1 /
seat-0 soldier, asserted); battle_set_unit_state fatalWounds [0,1,0,0,0,0] client first then host (F607); both settle;
the pre-ending census (test_w2_battle_end.pre_census: hash clean, desync, both battleEnd records at zero) and both
machines' fatalVote at its zeros. Kill: host battle_action kill_unit_real A. Answers ONLY through click_widget
{match: "OK" | "CANCEL"} on the answering machine, pressed only while its top is ConfirmEndMissionState and the button
shows. dismiss_popup (Q11) is called only on the host's NextTurnState, never while the host's vote is Armed or Open,
and its reply must be handled "NextTurnState->close" (never "generic"). Ending: the host's NextTurnState closes ->
finishBattle -> battle_end, then test_w2_battle_end's E1 assertion set (row_verdict "E1": battle_end aliensDown, both
debriefs = HOST_DEBRIEF["E1"], the client's display-only debriefing, the host hold).

| row | wounds | during the vote | answers | green (the S-V-A.2 product) |
|---|---|---|---|---|
| V0 | none | - | - | no question on either machine, fatalVote armed/opened 0, NextTurnState -> battle_end |
| V1 | WS1 | - | client OK | host top CoopFatalVoteHold + Wait line naming the client, busyOwnerSeat 1; client top the question (N 1); voters [1]; close end |
| V2 | WS0 | client turn intent | host OK | the intent denied busy and held (lastDeny busy, pending, the Wait line naming the host), direction unchanged on both, heldIntents 1; close end; the held order never runs |
| V3 | WS0+WS1 | - | host OK, client OK | voters [0,1]; after the host OK the host top CoopFatalVoteHold; one close end |
| V4 | WS0+WS1 | - | host OK, client CANCEL | close continue; both on BattlescapeState; END TURN client then host -> battle_end; no second question |
| V5 | WS0 | client turn intent + client END TURN | host CANCEL | held as V2; host tally "END TURN 1/2", no NextTurnState, heldCommits >= 1; after continue the held turn applies on both; host END TURN -> battle_end; no second question |
| V6 | WS0+WS1 | - | host CANCEL while the client asks | the client's question closes by itself (questionClosedByClose 1, answerSent ""); continue |

Every vote row also asserts both machines' fatalVote at the open and after the close (the pinned field set: state
Open on both while open, Closed on the host after (the client's neither Open nor Armed), voteId >= 1 and equal on both,
armed 1, opened 1, voters, wounded N, answers, result, openSeq > the kill's last seq, closeSeq > openSeq and < the
battle_end seq (SV-T4: relations only), coveredStepsWhileOpen 0, answersDropped 0, resends and coverWaitPasses 0),
hash_now clean while open (and after a `continue` close), desyncSeen false, the host's hostCovered.steps unchanged
while the question/hold is up, and at most one question per machine per battle.

RED (S-V-A.1 = the tip + the zero-valued probe; one run, exit 2; V1-V6 measured 8/10/10/10/10/6 lines). V0 PASSES
(if red: STOP, the T2 path is broken). Every vote row fails its four fatalVote lines (host and client, at the open
and after the close: the zero record). Beyond those:
  V1  open: host top ConfirmEndMissionState, no Wait line, busyOwnerSeat -1; client top BattlescapeState. answer:
      client OK not pressed. ending: not run.
  V2  held: the turn admitted and applied under the host's question (direction changed on both; no busy deny,
      nothing pending, no Wait line; host intentsReceived admitted 1). covered: hostCovered.steps grew. after close:
      the held order ran. ending: runs and passes; the close-before-battle_end line fails.
  V3  open: client top BattlescapeState. hold: after the host OK the host top NextTurnState (no Wait line,
      busyOwnerSeat -1), the client top not the question, the host's record not Open. answer: client OK not pressed.
      ending: not run.
  V4  as V3 (the host OK ends the battle; the client CANCEL not pressed).
  V5  held and covered as V2; end turn: the host's record not Open, heldCommits 0. ending: runs and passes; the
      close-before-battle_end line fails.
  V6  open: client top BattlescapeState. ending: runs and passes; the close-before-battle_end line fails.

WV-D99 / WV-D100: one run is the result; no skip path, one boot per row. Each row prints ONE "EVIDENCE <id>:" line
before its verdict; main() runs every row and prints "PASS <id>" / "FAIL <id>: <message>". Every wait is bounded.
Exit 0 only when every row passes, 2 otherwise. WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_fatal_vote.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, assert_hash_clean
import repro_atom_walk as raw
import test_w2_battle_end as tbe

# ----- the classic boot (TASK 0 CONSTANTS) -----
A_ID = tbe.A_ID
WS0, WS1 = 10, 8                 # the lowest seat-0 / seat-1 soldier (seat 1 = [8, 9], seat 0 = [10..14])
C_ID = WS1                       # the client's soldier that receives V2/V5's turn order (T0-2)
WOUND = [0, 1, 0, 0, 0, 0]       # one torso fatal wound
ROW_PORT = {"V0": "48540", "V1": "48541", "V2": "48542", "V3": "48543", "V4": "48544", "V5": "48545", "V6": "48546"}
CTRL_PORTS = (49896, 49897)      # GameClient labels (the control sockets are ephemeral)

# ----- the vote -----
QUESTION, HOLD, MAP, NEXT = "ConfirmEndMissionState", "CoopFatalVoteHold", "BattlescapeState", "NextTurnState"
TEXT_N = {1: "1 of us is still fatally wounded", 2: "2 of us are still fatally wounded"}   # en-US OXCE :278-280
TEXT_WAIT_CLIENT = f"Please wait for {raw.CLIENT_PLAYER}'s action to finish"   # STR_COOP_WAIT_FOR_PLAYER_ACTION
TEXT_WAIT_HOST = f"Please wait for {raw.HOST_PLAYER}'s action to finish"
TALLY_1_2 = "END TURN 1/2"
NEXT_CLOSE = "NextTurnState->close"
# AMENDMENT P7-5 4.2: the pinned probe field set and its zeros (both machines carry every key).
FV_ZERO = {"state": "Idle", "voteId": 0, "armed": 0, "opened": 0, "voters": [], "wounded": 0, "answers": {},
           "result": "", "openSeq": 0, "closeSeq": 0, "heldIntents": 0, "heldCommits": 0, "coveredStepsWhileOpen": 0,
           "answersDropped": 0, "resends": 0, "answered": [], "opensApplied": 0, "closesApplied": 0,
           "questionPushed": 0, "questionPushedMs": 0, "ghostWaitPasses": 0, "coverWaitPasses": 0, "answerSent": "",
           "questionClosedByClose": 0}

OPEN_S = 10       # the question / hold after the kill (TASK 0: 0.90 s host kill, +2.00 s partner kill)
STEP_S = 10       # each answer's effect, the client's question, the close (TASK 0: OK -> NextTurnState <= 0.063 s)
SETTLE_S = 15     # the client catches up with the host's stream
BUTTON_S = 5      # the question's button shows (its popup window hides every surface until the popup ends)
HELD_OBS_S = 1.5  # a held order is watched this long (T0-2: an admitted turn applies on both <= 0.1 s)
TALLY_S = 20      # the host paints END TURN 1/2 after the client's press
POLL = 0.05


# ===================== small probes =====================


def short(e):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= 400 else s[:400] + "..."


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def wait_until(pred, timeout, interval=POLL):
    t0 = time.time()
    while True:
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def fv(gc):
    return event_state(gc).get("fatalVote")


def norm(rec):
    """A fatalVote record with voters / answered sorted and answers keyed by int seat."""
    rec = dict(rec) if isinstance(rec, dict) else {}
    for k in ("voters", "answered"):
        if isinstance(rec.get(k), list):
            rec[k] = sorted(rec[k])
    if isinstance(rec.get("answers"), dict):
        rec["answers"] = {int(k): v for k, v in rec["answers"].items()}
    return rec


def mism(rec, want):
    """The mismatches of `rec` against `want` ({key: value | (op, x)}; ops ge / gt / lt / notin), as text."""
    out = []
    for k, w in want.items():
        v = rec.get(k, "<absent>")
        if isinstance(w, tuple):
            op, x = w
            num = isinstance(v, int) and not isinstance(v, bool)
            ok = (num and v >= x) if op == "ge" else (num and v > x) if op == "gt" else \
                (num and v < x) if op == "lt" else (v not in x)
            shown = {"ge": ">=", "gt": ">", "lt": "<", "notin": "not in"}[op] + f" {x!r}"
        else:
            ok, shown = v == w, repr(w)
        if not ok:
            out.append(f"{k}={v!r} (want {shown})")
    return out


def texts(gc):
    """The top state's class (prefix-stripped) and its Text / TextButton captions in order."""
    r = gc.cmd({"cmd": "list_widgets"})
    return ((r.get("state") or "").replace("class OpenXcom::", ""),
            [w.get("text") for w in r.get("widgets") or [] if "text" in w])


def question_texts(n):
    return ["Mission complete.", TEXT_N.get(n, f"{n} of us are still fatally wounded"), "End Mission?", "OK", "CANCEL"]


def snap(gc):
    """One machine's view: stack, top widgets, the fatalVote record and the event / battle fields the rows read."""
    es, bs = event_state(gc), battle_state(gc)
    st = stack(gc)
    wstate, wtexts = texts(gc)
    return {"top": st[-1] if st else None, "stack": st, "widgetsState": wstate, "texts": wtexts,
            "fv": norm(es.get("fatalVote")), "seqE": es.get("lastSeqEmitted"), "seqA": es.get("lastSeqApplied"),
            "qd": es.get("queueDepth"), "busyOwnerSeat": es.get("busyOwnerSeat"), "desyncSeen": es.get("desyncSeen"),
            "covered": (es.get("hostCovered") or {}).get("steps"), "intentsReceived": es.get("intentsReceived"),
            "lastDeny": es.get("lastDeny"), "inFlight": es.get("inFlight"), "wait": bs.get("coopWaitText"),
            "pending": bs.get("coopPendingIntent"), "tally": bs.get("coopEndTurnText"),
            "dirC": (session.units_by_id(bs).get(C_ID) or {}).get("direction")}


def covered(gc):
    return (event_state(gc).get("hostCovered") or {}).get("steps")


def dir_c(gc):
    return (session.units_by_id(battle_state(gc)).get(C_ID) or {}).get("direction")


class Row:
    """One row's machines, failure lines and evidence."""

    def __init__(self, rid, host, client):
        self.rid, self.host, self.client = rid, host, client
        self.fails, self.ev = [], {}
        self.t0 = time.time()
        self.opened = False      # the host's vote record read Open at the open
        self.ending = None       # why the ending cannot run (None = it runs)
        self.covered_open = self.covered_last = None   # the host's covered steps at the open / before the last answer
        self.crash0 = set()

    def fail(self, phase, msg):
        self.fails.append(f"{phase}: {msg}")

    def line(self, phase, who, mm):
        if mm:
            self.fail(phase, f"{who}: " + "; ".join(mm))


# ===================== the steps =====================


def settle(r, phase):
    """The client has applied everything the host emitted (no busy-owner term: a vote names its pending voter)."""
    h, c = r.host, r.client
    ok, secs = wait_until(lambda: (event_state(c).get("lastSeqApplied", 0) == event_state(h).get("lastSeqEmitted", 0)
                                   and event_state(c).get("queueDepth") == 0
                                   and event_state(h).get("queueDepth") == 0), SETTLE_S, 0.1)
    if not ok:
        r.fail(phase, f"the client did not catch up with the host's stream within {secs}s")


def hash_clean(r, phase, what):
    try:
        assert_hash_clean(r.host, r.client, full=True, what=what)
    except AssertionError as e:
        r.fail(phase, f"hash_now full {what}: {short(e)}")


def stage_v(r, wounded, seat_pins=((0, WS0), (1, WS1))):
    """Design section 4 staging: auto-end on, the seat pins, the wounds (client first), the pre-ending census and
    both machines' fatalVote zeros. Returns the census (b0)."""
    h, c = r.host, r.client
    ae = h.cmd({"cmd": "set_option", "name": "battleAutoEnd", "value": True})
    if ae.get("value") is not True:
        r.fail("pre", f"host set_option battleAutoEnd answered {ae} (want value true)")
    hs = battle_state(h)
    for seat, want in seat_pins:
        ids = sorted(u["id"] for u in hs.get("units", []) if u.get("faction") == 0 and u.get("coop") == seat
                     and not u.get("isOut"))
        if not ids or ids[0] != want:
            r.fail("pre", f"seat {seat} soldiers {ids} (want the lowest = {want})")
    wr = {}
    for uid in wounded:
        for gc in (c, h):
            resp = gc.cmd({"cmd": "battle_set_unit_state", "unit": uid, "fatalWounds": WOUND})
            wr[f"{gc.name}:{uid}"] = resp.get("fatalWounds")
            if resp.get("fatalWounds") != WOUND:
                r.fail("pre", f"{gc.name} battle_set_unit_state {uid} fatalWounds answered {resp} (want {WOUND})")
    try:
        session.wait_host_idle(h, c, timeout=30)
    except Exception as e:
        r.fail("pre", f"wait_host_idle after the wounds: {short(e)}")
    pre = []
    census = tbe.pre_census(h, c, pre)
    for m in pre:
        r.fail("pre", m)
    for gc in (h, c):
        z = norm(fv(gc))
        r.line("pre", f"{gc.name} fatalVote before the kill", mism(z, FV_ZERO))
    r.ev["stage"] = {"autoEnd": ae.get("value"), "wounds": wr, "census": tbe.census_view(census)}
    r.ev["preSeq"] = census["host"]["lastSeqEmitted"]
    r.crash0 = session._crash_log_snapshot()
    return census


def kill(r):
    resp = r.host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": A_ID})
    if not resp.get("ok") or resp.get("killed") != [A_ID]:
        r.fail("pre", f"kill_unit_real answered {resp} (want ok, killed [{A_ID}])")
    r.ev["kill"] = resp


def detect_open(r):
    """The host's question or hold is up (OPEN_S). Returns (ok, the host's top trace)."""
    h = r.host
    trace, last, t0 = [], None, time.time()
    while True:
        t = top(h)
        if t != last:
            trace.append([round(time.time() - t0, 2), t])
            last = t
        if t in (QUESTION, HOLD):
            return True, trace
        if time.time() - t0 >= OPEN_S:
            return False, trace
        time.sleep(POLL)


def check_open(r, voters, n, min_seq, trace):
    """The vote at its open: both machines' tops, the question's text, the Wait line, both fatalVote records, the hash."""
    h, c = r.host, r.client
    r.opened = (fv(h) or {}).get("state") == "Open"
    if r.opened:
        wait_until(lambda: ((fv(c) or {}).get("opensApplied") or 0) >= 1
                   and (1 not in voters or top(c) == QUESTION), STEP_S)
    settle(r, "open")
    hs, cs = snap(h), snap(c)
    r.covered_open = r.covered_last = hs["covered"]
    r.ev["open"] = {"hostTrace": trace, "host": hs, "client": cs}
    hm, cm = [], []
    want_h = QUESTION if 0 in voters else HOLD
    if hs["top"] != want_h:
        hm.append(f"top {hs['top']} (want {want_h})")
    elif want_h == QUESTION and hs["texts"] != question_texts(n):
        hm.append(f"question texts {hs['texts']} (want {question_texts(n)})")
    if want_h == HOLD:
        if hs["wait"] != TEXT_WAIT_CLIENT:
            hm.append(f"Wait line {hs['wait']!r} (want {TEXT_WAIT_CLIENT!r})")
        if hs["busyOwnerSeat"] != 1:
            hm.append(f"busyOwnerSeat {hs['busyOwnerSeat']} (want 1)")
    if hs["stack"].count(QUESTION) > 1:
        hm.append(f"stack {hs['stack']} holds two questions")
    want_c = QUESTION if 1 in voters else MAP
    if cs["top"] != want_c:
        cm.append(f"top {cs['top']} (want {want_c})")
    elif want_c == QUESTION and cs["texts"] != question_texts(n):
        cm.append(f"question texts {cs['texts']} (want {question_texts(n)})")
    r.line("open", "host at the open", hm)
    r.line("open", "client at the open", cm)
    hv = hs["fv"]
    r.line("open", "host fatalVote at the open", mism(hv, {
        "state": "Open", "voteId": ("ge", 1), "armed": 1, "opened": 1, "voters": sorted(voters), "wounded": n,
        "answers": {}, "result": "", "openSeq": ("gt", min_seq), "closeSeq": 0, "coveredStepsWhileOpen": 0,
        "answersDropped": 0, "resends": 0}))
    voter = 1 in voters
    r.line("open", "client fatalVote at the open", mism(cs["fv"], {
        "state": "Open", "voteId": hv.get("voteId") if (hv.get("voteId") or 0) >= 1 else ("ge", 1),
        "voters": sorted(voters), "wounded": n, "answered": [], "opensApplied": 1, "closesApplied": 0,
        "questionPushed": 1 if voter else 0, "questionPushedMs": ("gt", 0) if voter else 0, "answerSent": "",
        "coverWaitPasses": 0, "questionClosedByClose": 0}))
    for name, s in (("host", hs), ("client", cs)):
        if s["desyncSeen"] is not False:
            r.fail("open", f"{name} desyncSeen={s['desyncSeen']} (want false)")
    hash_clean(r, "open", "while the vote is open")


def answer(r, gc, match, phase):
    """Press `match` on gc's question (click_widget, a real SDL click) once its button shows. False = not pressed.
    First samples the host's covered steps while its question / hold is still up (the 'while open' end point)."""
    if top(r.host) in (QUESTION, HOLD):
        r.covered_last = covered(r.host)
    t = top(gc)
    if t != QUESTION:
        r.fail(phase, f"{gc.name} {match} not pressed: {gc.name} top {t} (want {QUESTION})")
        return False

    def shown():
        w = gc.cmd({"cmd": "list_widgets"}).get("widgets") or []
        return any(x.get("text") == match and x.get("visible") and not x.get("hidden") for x in w)
    ok, secs = wait_until(shown, BUTTON_S)
    resp = gc.cmd({"cmd": "click_widget", "match": match})
    r.ev.setdefault("answers", []).append({"who": gc.name, "match": match, "shownS": secs,
                                           "resp": {k: resp.get(k) for k in ("ok", "error", "text")}})
    if not ok or not resp.get("ok") or resp.get("text") != match:
        r.fail(phase, f"{gc.name} {match}: button shown={ok} after {secs}s, click_widget answered {resp}")
    return True


def check_hold(r, n_answers):
    """After the host's yes with the client still deciding: the host's hold and Wait line, the client's question."""
    h, c = r.host, r.client
    wait_until(lambda: top(h) != QUESTION, STEP_S)
    hs, cs = snap(h), snap(c)
    r.ev["hold"] = {"host": hs, "client": cs}
    hm = []
    if hs["top"] != HOLD:
        hm.append(f"top {hs['top']} (want {HOLD})")
    if QUESTION in hs["stack"]:
        hm.append(f"stack {hs['stack']} still holds the question")
    if hs["wait"] != TEXT_WAIT_CLIENT:
        hm.append(f"Wait line {hs['wait']!r} (want {TEXT_WAIT_CLIENT!r})")
    if hs["busyOwnerSeat"] != 1:
        hm.append(f"busyOwnerSeat {hs['busyOwnerSeat']} (want 1)")
    r.line("hold", "host after its OK", hm)
    if cs["top"] != QUESTION:
        r.fail("hold", f"client top {cs['top']} after the host's OK (want {QUESTION})")
    r.line("hold", "host fatalVote after its OK", mism(hs["fv"], {"state": "Open", "answers": n_answers}))


def check_close(r, result, answers, client_want, host_want=None):
    """The decision: both machines' records after the close; continue rows also both tops and the hash."""
    h, c = r.host, r.client
    cov_last = r.covered_last
    if cov_last != r.covered_open:
        r.fail("covered", f"host hostCovered.steps {r.covered_open} -> {cov_last} while the question/hold was up "
                          f"(want unchanged)")
    if r.opened:
        wait_until(lambda: (fv(h) or {}).get("state") == "Closed", STEP_S)
        if result == "end":
            wait_until(lambda: top(h) == NEXT, STEP_S)
        else:
            wait_until(lambda: top(h) == MAP and top(c) == MAP, STEP_S)
    settle(r, "close")
    hs, cs = snap(h), snap(c)
    r.ev["close"] = {"host": hs, "client": cs}
    hv = hs["fv"]
    want = {"state": "Closed", "result": result, "answers": answers, "armed": 1, "opened": 1,
            "closeSeq": ("gt", hv.get("openSeq") or 0), "heldIntents": 0, "heldCommits": 0,
            "coveredStepsWhileOpen": 0, "answersDropped": 0, "resends": 0}
    want.update(host_want or {})
    r.line("close", "host fatalVote after the close", mism(hv, want))
    cw = {"state": ("notin", ("Open", "Armed")), "result": result, "opensApplied": 1, "closesApplied": 1,
          "coverWaitPasses": 0}
    cw.update(client_want)
    r.line("close", "client fatalVote after the close", mism(cs["fv"], cw))
    if not r.opened:
        return   # the tops and the hash below belong to a vote that closed
    if QUESTION in cs["stack"] or QUESTION in hs["stack"] or HOLD in hs["stack"]:
        r.fail("close", f"a question or hold survives the close: host {hs['stack']} client {cs['stack']}")
    if result == "continue":
        if hs["top"] != MAP or cs["top"] != MAP:
            r.fail("close", f"tops after continue host {hs['top']} client {cs['top']} (want {MAP} on both)")
        hash_clean(r, "close", "after the close")
    elif hs["top"] != NEXT:
        r.fail("close", f"host top {hs['top']} after the close end (want {NEXT})")
    for name, s in (("host", hs), ("client", cs)):
        if s["desyncSeen"] is not False:
            r.fail("close", f"{name} desyncSeen={s['desyncSeen']} (want false)")


def turn_order(r):
    """The client orders C to turn two octants (battle_intent turn). Returns (dir0, toDir, iseq)."""
    d0 = dir_c(r.client)
    to_dir = (d0 + 2) % 8 if isinstance(d0, int) else 0
    resp = r.client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": C_ID, "toDir": to_dir})
    if not resp.get("ok"):
        r.fail("held", f"client battle_intent turn answered {resp}")
    r.ev["intent"] = {"dir0": d0, "toDir": to_dir, "resp": resp}
    return d0, to_dir, resp.get("iseq")


def check_held(r, d0, iseq):
    """D214 (a): the order is denied busy and held on the client; nothing turns on either machine (HELD_OBS_S)."""
    h, c = r.host, r.client
    seen, t0 = set(), time.time()
    while time.time() - t0 < HELD_OBS_S:
        seen.add((dir_c(h), dir_c(c)))
        time.sleep(0.1)
    hs, cs = snap(h), snap(c)
    r.ev["held"] = {"dirsSeen": sorted(seen, key=str), "host": hs, "client": cs}
    if seen != {(d0, d0)}:
        r.fail("held", f"C's direction (host, client) seen {sorted(seen, key=str)} (want only ({d0}, {d0}): held)")
    cm = []
    if cs["lastDeny"] != {"iseq": iseq, "reason": "busy"}:
        cm.append(f"lastDeny {cs['lastDeny']} (want {{iseq {iseq}, reason busy}})")
    if cs["pending"] is None:
        cm.append("coopPendingIntent None (want the held turn)")
    if cs["wait"] != TEXT_WAIT_HOST:
        cm.append(f"Wait line {cs['wait']!r} (want {TEXT_WAIT_HOST!r})")
    if cs["top"] != MAP:
        cm.append(f"top {cs['top']} (want {MAP})")
    r.line("held", "client", cm)
    turn = (hs["intentsReceived"] or {}).get("turn") or {}
    if (turn.get("admitted"), turn.get("denied")) != (0, 1):
        r.fail("held", f"host intentsReceived.turn {turn} (want admitted 0, denied 1)")


def never_runs(r, d0):
    """V2 after the close end: the held order never runs (C keeps d0 on both for HELD_OBS_S)."""
    seen, t0 = set(), time.time()
    while time.time() - t0 < HELD_OBS_S:
        seen.add((dir_c(r.host), dir_c(r.client)))
        time.sleep(0.1)
    r.ev["afterClose"] = sorted(seen, key=str)
    if seen != {(d0, d0)}:
        r.fail("after close", f"the held order ran: C's direction (host, client) seen {sorted(seen, key=str)} "
                              f"(want only ({d0}, {d0}))")


def end_turns(r, client_too=True):
    """Continue rows: END TURN client (unless pressed during the vote) then host, once both stand on the map."""
    h, c = r.host, r.client
    if top(h) != MAP or top(c) != MAP:
        r.ending = f"END TURN not pressed: host top {top(h)} client top {top(c)} (want {MAP} on both)"
        return
    if client_too:
        c.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        ok, secs = wait_until(lambda: battle_state(h).get("coopEndTurnText") == TALLY_1_2, TALLY_S, 0.1)
        if not ok:
            r.fail("ending", f"host never painted {TALLY_1_2} after the client's END TURN ({secs}s)")
    h.cmd({"cmd": "battle_action", "action": "end_turn_button"})


def dismiss_next(r):
    """Q11: the ONLY dismiss_popup call - the host's NextTurnState, never while its vote is Armed or Open."""
    h = r.host
    st = (fv(h) or {}).get("state")
    if top(h) != NEXT or st in ("Armed", "Open"):
        r.fail("ending", f"dismiss_popup not sent: host top {top(h)} fatalVote.state {st!r}")
        return None
    d = h.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") == "generic" or d.get("handled") != NEXT_CLOSE:
        r.fail("ending", f"host dismiss_popup answered {d} (want handled {NEXT_CLOSE!r}, never 'generic')")
    return d


def ending(r, census, verdict, vote=True):
    """NextTurnState -> close -> battle_end, then `verdict` (the E1 / E6 assertion set) and the vote's relations."""
    h, c = r.host, r.client
    if r.ending:
        r.fail("ending", f"not run: {r.ending}")
        return
    trace, last, t0 = [], None, time.time()
    while time.time() - t0 < STEP_S:
        th, tc = top(h), top(c)
        if (th, tc) != last:
            trace.append([round(time.time() - t0, 2), th, tc])
            last = (th, tc)
        if th == NEXT:
            break
        time.sleep(POLL)
    r.ev["toNext"] = trace
    if any(QUESTION in (x[1], x[2]) for x in trace):
        r.fail("ending", f"a second question on the way to NextTurnState: {trace}")
    if top(h) != NEXT:
        r.fail("ending", f"host NextTurnState not up within {STEP_S}s (top trace {trace})")
        return
    r.ev["dismiss"] = dismiss_next(r)
    deb_ok, deb_s = wait_until(lambda: any("DebriefingState" in s for s in stack(h)), tbe.DEBRIEF_S, 0.1)
    if not deb_ok:
        r.fail("ending", f"host DebriefingState not reached within {deb_s}s")
    left_ok, left_s = wait_until(lambda: top(c) in tbe.CLIENT_END_TOPS, tbe.CLIENT_LEAVE_S, 0.25)
    hold = tbe.host_hold(h)
    hend, cend = tbe.machine_view(h), tbe.machine_view(c)
    extra = []
    new_crash = sorted(session._crash_log_snapshot() - r.crash0)
    if new_crash:
        extra.append(f"new crash log(s): {new_crash}")
    try:
        session.assert_client_zero_disk(c.user_dir)
    except AssertionError as e:
        extra.append(str(e))
    hrec, crec = hend.pop("battleEnd"), cend.pop("battleEnd")
    hdeb, cdeb = hend.pop("debrief"), cend.pop("debrief")
    for m in verdict(hrec, crec, cend, hend, census.get("b0"), {"ok": left_ok, "secs": left_s}, extra, hold,
                     hdeb, cdeb):
        r.fail("ending", m)
    hv, cv = norm(fv(h)), norm(fv(c))
    r.ev["end"] = {"hostBattleEnd": hrec, "clientBattleEnd": crec, "hostEnd": {k: hend[k] for k in ("top", "stack")},
                   "clientEnd": {k: cend[k] for k in ("top", "stack")}, "hold": hold, "hostDebrief": hdeb,
                   "clientDebrief": cdeb, "fvHost": hv, "fvClient": cv, "newCrash": new_crash}
    if not vote:
        r.line("ending", "host fatalVote at the end", mism(hv, {"armed": 0, "opened": 0}))
        r.line("ending", "client fatalVote at the end", mism(cv, {"opensApplied": 0, "questionPushed": 0}))
        return
    cs_ = hv.get("closeSeq") or 0
    bseq = (hrec or {}).get("seq")
    if not cs_ or not isinstance(bseq, int) or not cs_ < bseq:
        r.fail("ending", f"close seq {cs_} vs battle_end seq {bseq} (want 0 < close < battle_end)")
    if r.opened:
        r.line("ending", "host fatalVote at the end (one vote per battle)", mism(hv, {"armed": 1, "opened": 1}))
        pushed = ((r.ev.get("close") or {}).get("client") or {}).get("fv", {}).get("questionPushed")
        r.line("ending", "client fatalVote at the end", mism(cv, {"questionPushed": pushed, "closesApplied": 1}))


def e1_verdict(hrec, crec, cend, hend, b0, cleft, extra, hold, hdeb, cdeb):
    """test_w2_battle_end's E1 assertion set (TASK 0: every V0-V6 ending equals E1's pins, F4382)."""
    return tbe.row_verdict("E1", tbe.ROW_EXPECT["E1"], hrec, crec, cend, hend, b0, cleft, extra, hold, hdeb, cdeb,
                           None)


# ===================== the rows =====================


def row_v0(r):
    census = stage_v(r, [])
    kill(r)
    trace, last, t0 = [], None, time.time()
    while time.time() - t0 < OPEN_S:
        th, tc = top(r.host), top(r.client)
        if (th, tc) != last:
            trace.append([round(time.time() - t0, 2), th, tc])
            last = (th, tc)
        if th == NEXT:
            break
        time.sleep(POLL)
    r.ev["open"] = {"trace": trace}
    if any(QUESTION in (x[1], x[2]) for x in trace):
        r.fail("open", f"a question appeared without a wounded soldier: {trace}")
    for gc in (r.host, r.client):
        r.line("open", f"{gc.name} fatalVote", mism(norm(fv(gc)), {"state": "Idle", "armed": 0, "opened": 0,
                                                                     "opensApplied": 0, "questionPushed": 0}))
    ending(r, census, e1_verdict, vote=False)


def vote_open(r, wounded, voters):
    census = stage_v(r, wounded)
    kill(r)
    ok, trace = detect_open(r)
    if not ok:
        r.fail("open", f"host top neither {QUESTION} nor {HOLD} within {OPEN_S}s of the kill: {trace}")
    check_open(r, voters, len(wounded), r.ev["preSeq"] or 0, trace)
    return census


def row_v1(r):
    census = vote_open(r, [WS1], [1])
    r.covered_last = covered(r.host)
    if not answer(r, r.client, "OK", "answer"):
        r.ending = "the client's OK was not pressed"
    check_close(r, "end", {1: True}, {"answerSent": "yes", "questionPushed": 1, "questionClosedByClose": 0})
    ending(r, census, e1_verdict)


def row_v2(r):
    census = vote_open(r, [WS0], [0])
    d0, _to, iseq = turn_order(r)
    check_held(r, d0, iseq)
    r.covered_last = covered(r.host)
    if not answer(r, r.host, "OK", "answer"):
        r.ending = "the host's OK was not pressed"
    check_close(r, "end", {0: True}, {"answerSent": "", "questionPushed": 0, "questionClosedByClose": 0},
                {"heldIntents": 1})
    never_runs(r, d0)
    ending(r, census, e1_verdict)


def both_yes_or_no(r, client_match):
    census = vote_open(r, [WS0, WS1], [0, 1])
    pressed = answer(r, r.host, "OK", "answer")
    check_hold(r, {0: True})
    r.covered_last = covered(r.host)
    pressed = answer(r, r.client, client_match, "answer") and pressed
    if not pressed:
        r.ending = "an answer was not pressed"
    return census


def row_v3(r):
    census = both_yes_or_no(r, "OK")
    check_close(r, "end", {0: True, 1: True}, {"answerSent": "yes", "questionPushed": 1, "questionClosedByClose": 0})
    ending(r, census, e1_verdict)


def row_v4(r):
    census = both_yes_or_no(r, "CANCEL")
    check_close(r, "continue", {0: True, 1: False},
                {"answerSent": "no", "questionPushed": 1, "questionClosedByClose": 0})
    if not r.ending:
        end_turns(r)
    ending(r, census, e1_verdict)


def row_v5(r):
    census = vote_open(r, [WS0], [0])
    d0, to_dir, iseq = turn_order(r)
    check_held(r, d0, iseq)
    r.client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    ok, secs = wait_until(lambda: battle_state(r.host).get("coopEndTurnText") == TALLY_1_2, TALLY_S, 0.1)
    hs = snap(r.host)
    r.ev["endTurnWhileOpen"] = {"tallyS": secs, "host": hs}
    if not ok:
        r.fail("end turn", f"host never painted {TALLY_1_2} after the client's END TURN ({secs}s)")
    if NEXT in hs["stack"] or hs["top"] != QUESTION:
        r.fail("end turn", f"host stack {hs['stack']} after the client's END TURN (want the question on top, no "
                           f"{NEXT})")
    r.line("end turn", "host fatalVote after the client's END TURN", mism(hs["fv"], {"state": "Open",
                                                                                     "heldCommits": ("ge", 1)}))
    r.covered_last = covered(r.host)
    if not answer(r, r.host, "CANCEL", "answer"):
        r.ending = "the host's CANCEL was not pressed"
    check_close(r, "continue", {0: False}, {"answerSent": "", "questionPushed": 0, "questionClosedByClose": 0},
                {"heldIntents": 1, "heldCommits": ("ge", 1)})
    ok, secs = wait_until(lambda: (dir_c(r.host), dir_c(r.client)) == (to_dir, to_dir), STEP_S, 0.1)
    r.ev["resubmit"] = {"ok": ok, "secs": secs}
    if not ok:
        r.fail("after close", f"the held turn did not apply on both within {secs}s: C's direction host "
                              f"{dir_c(r.host)} client {dir_c(r.client)} (want {to_dir})")
    try:
        session.wait_host_idle(r.host, r.client, timeout=30)
    except Exception as e:
        r.fail("after close", f"wait_host_idle: {short(e)}")
    if not r.ending:
        hash_clean(r, "after close", "after the held turn")
        end_turns(r, client_too=False)
    ending(r, census, e1_verdict)


def row_v6(r):
    census = vote_open(r, [WS0, WS1], [0, 1])
    r.covered_last = covered(r.host)
    if not answer(r, r.host, "CANCEL", "answer"):
        r.ending = "the host's CANCEL was not pressed"
    check_close(r, "continue", {0: False}, {"answerSent": "", "questionPushed": 1, "questionClosedByClose": 1})
    if not r.ending:
        end_turns(r)
    ending(r, census, e1_verdict)


# ===================== runner =====================


def run_row(rid, boot_fn, row_fn, results, port, label):
    host = GameClient("host", CTRL_PORTS[0], make_user_dir(f"{label}_{rid}_host"))
    client = GameClient("client", CTRL_PORTS[1], make_user_dir(f"{label}_{rid}_client"))
    r = Row(rid, host, client)
    try:
        try:
            r.ev["boot"] = boot_fn(host, client, port)
        except Exception as e:
            results[rid] = False
            print(f"FAIL {rid}: pre (bring-up) {short(e)}", flush=True)
            return
        r.ev["bootS"] = round(time.time() - r.t0, 1)
        try:
            row_fn(r)
        except Exception as e:
            r.fail("exception", short(e))
        r.ev["wallS"] = round(time.time() - r.t0, 1)
        print(f"EVIDENCE {rid}: {r.ev}", flush=True)
        if r.fails:
            results[rid] = False
            print(f"FAIL {rid}: {len(r.fails)} failure(s): " + " | ".join(r.fails), flush=True)
        else:
            results[rid] = True
            print(f"PASS {rid}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p7-sv] shutdown {gc.name}: {short(e)}", flush=True)


def run_rows(name, rows, ports, label):
    t0 = time.time()
    results = {}
    for rid, boot_fn, row_fn in rows:
        run_row(rid, boot_fn, row_fn, results, ports[rid], label)
    order = [r[0] for r in rows]
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\n{name}: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in {time.time() - t0:.1f}s",
          flush=True)
    return 0 if not failed else 2


ROWS = (("V0", tbe.boot, row_v0), ("V1", tbe.boot, row_v1), ("V2", tbe.boot, row_v2), ("V3", tbe.boot, row_v3),
        ("V4", tbe.boot, row_v4), ("V5", tbe.boot, row_v5), ("V6", tbe.boot, row_v6))


def main():
    return run_rows("test_w2_fatal_vote", ROWS, ROW_PORT, "w2p7_fatal_vote")


if __name__ == "__main__":
    sys.exit(main())
