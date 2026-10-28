"""test_abort_vote_edges.py: the abort vote's two edges. A player's drop during an open abort vote
cancels it (the #87 cancel, as on the release line) and after the rejoin either player can ask again at once; an abort
request made while the fatal-wounds vote is open waits for it and opens once that question is cancelled (owner
design-D8, D231, D244; D214 (a) / SV-M12 for the wait; VL-L1-3, VL-L1-4). Spec: docs rewrite/prompts/r4l1_abort_vote.md
(f) stage S-B with AMENDMENT R4-L1-1, ORCHESTRATOR RULINGS (R-L1-1-1: SV-M12) and AMENDMENT R4-L1-2. TASK 0 constants:
docs rewrite/r4l1-task0/sb/CONSTANTS.md (T0-3, T0-4, the walls).

Two boots (tbe.boot: the classic parallel skirmish, set_seed SEED_MAP 1, MAP_FP, pin_ai_neutral, hash clean), each shut
down before the next:
  Boot C (lobby key 48614; r4l1_c_host / _client / _client2): AV4 a leave cancels the vote; after the rejoin (client2,
         test_rejoin_end_turn.stage_rejoin's steps copied) a new vote works.
  Boot D (lobby key 48616; r4l1_d_host / _client): AV5 an abort request during the fatal-wounds vote waits for it
         (test_fatal_vote's stage_v(r, [WS0]) + kill + detect_open: the host is the only voter).

Cells (GUARD = passes on both builds, RED = fails on the red commit):
  AV4-1 GUARD the drop cancels the vote: host menuStatus "CONNECTION LOST - VOTE CANCELLED" (vote_menu_state with the
        id read before the drop), menuFinished, VS active false, AV {cancels 1, state Idle}, dialog 62 above the
        VoteMenu, phase Active, peerAbsent true, battleEnd emitted 0.
  AV4-2 GUARD after RESUME + the host's CLOSE both on BattlescapeState, no vote on either, all buckets EQUAL.
  AV4-3 GUARD the rejoined player's ABORT opens a new vote (host AV opens 2, VS starterSeat 1) and both YES end the
        battle (battleEnd reason abort; both DebriefingState).
  AV5-1 RED while the fatal vote is open no abort vote opens: no VoteMenu on either stack through W, the host's question
        on top, host AV {state Armed, heldWhileFatal >= 1}.
  AV5-2 RED after the host's CANCEL on its question the abort vote opens on both (VS starterSeat 1, host AV opens 1,
        fatalVote result "continue").
  AV5-3 GUARD-after-open both YES end the battle: battleEnd reason abort, aborted true, both debriefings, one fatal
        question in the battle (host fatalVote armed 1, opened 1).

Flow rule: checks never end a row; a WAIT that times out ends the row (later cells "not reached"). Every row runs after a
failure. Each row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <cells>" and, on a FAIL, ONE
"CAPTURE <id>:" line (every machine's stack, vote_state, abortVote, battleEnd, coop_dialog_info, battle_state phase /
turn / side, the last 15 [coop-vote] / [coop-abort] / [coop-battle-end] log lines). A boot or staging miss fails its row
("boot" / every cell "not reached") with one CAPTURE line. Votes are answered with real clicks (click_widget YES / CLOSE
/ CANCEL); dismiss_popup only on an AbortMissionState.

RED (commit 1 = this file; S-A's green build): exit 2 with AV4 PASS and AV5 FAIL on AV5-1 (the abort VoteMenu opens
over the host's question at once, AV state Open, heldWhileFatal 0) and AV5-2 (the host's CANCEL finds no button under
the VoteMenu; fatalVote result ""); AV5-3 PASS (the host's YES on that VoteMenu ends the battle as an abort; T0-4).
Commit 2 (P9, the fatal-vote term in the abort pump's open step): exit 0.
ONE foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_abort_vote_edges.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state
import test_battle_end as tbe
import test_fatal_vote as fvt
import test_abort_vote as rav
from test_abort_vote import Stop, stack, top, vs, av, be, vote_open, btn_ready, wait_until, hash_eq, short
from test_skirmish_rejoin_battle import (drop_client_mid_battle, rejoin_skirmish, dialog, in_battle_save, has,
                                         COOP_DLG_WAIT_PLAYERS, COOP_DLG_CLIENT_RESUME_HOLD)

KEY_C, KEY_D = "48614", "48616"
W, POLL = 5.0, 0.1
CANCELLED = "CONNECTION LOST - VOTE CANCELLED"                       # VoteMenu::cancelVote (#87)
QUESTION = fvt.QUESTION                                               # ConfirmEndMissionState
REJOIN_S = 120                                                        # stage_rejoin's bounds (240 / 60 / 120 s)
CELLS = {"AV4": ["AV4-1", "AV4-2", "AV4-3"], "AV5": ["AV5-1", "AV5-2", "AV5-3"]}


class Row(rav.Row):
    """test_abort_vote.Row plus the boot's machines (AV4 adds client2) and a poll interval for the rejoin waits."""

    def __init__(self, rid, machines):
        super().__init__(rid)
        self.machines = machines

    def wait(self, cell, desc, pred, timeout, diag=None, interval=POLL):
        ok, secs = wait_until(pred, timeout, interval)
        self.ev[f"wait {desc}"] = secs if ok else f"TIMEOUT {secs}"
        if not ok:
            extra = ""
            if diag:
                try:
                    extra = f" ({diag()})"
                except Exception as e:
                    extra = f" (diag {short(e, 120)})"
            self.res.setdefault(cell, []).append(f"{desc}: not within {timeout}s{extra}")
            raise Stop(cell)
        return secs


def authority(gc):
    return battle_state(gc).get("authority") or {}


def debrief(r, host, other, cell):
    """DEBRIEF: host top DebriefingState <= 30 s; `other` top in CLIENT_END_TOPS <= 30 s, DebriefingState (display-only)."""
    hd, hsecs = wait_until(lambda: top(host) == "DebriefingState", tbe.DEBRIEF_S)
    cd, csecs = wait_until(lambda: top(other) in tbe.CLIENT_END_TOPS, tbe.CLIENT_LEAVE_S)
    ctop = top(other)
    disp = other.cmd({"cmd": "debrief_state"}).get("displayOnly") if ctop == "DebriefingState" else None
    r.ev["debrief"] = {"host": [hd, hsecs], other.name: [cd, csecs, ctop, disp]}
    r.check(cell, hd and cd and ctop == "DebriefingState" and disp is True,
            f"debriefs: host {hd} ({hsecs}s), {other.name} {cd} ({csecs}s) top {ctop} displayOnly {disp} (want both "
            f"DebriefingState, the {other.name}'s display-only)")


def end_cells(r, host, cell):
    """The ending's battleEnd: reason abort, aborted true (the host's record)."""
    hb = be(host)
    r.ev["be"] = {k: hb.get(k) for k in ("emitted", "reason", "aborted", "inExitArea", "seq")}
    r.check(cell, (hb.get("emitted"), hb.get("reason"), hb.get("aborted")) == (1, "abort", True),
            f"host battleEnd emitted/reason/aborted={hb.get('emitted')}/{hb.get('reason')!r}/{hb.get('aborted')} "
            f"(want 1/'abort'/True)")


# ===================== boot C: AV4 =====================


def av4(r, m):
    host, client = m["host"], m["client"]
    rav.open_dialog_and_ok(host, r, "AV4-1", {"cmd": "battle_ui_press", "control": "abort"})
    r.wait("AV4-1", "VOTE_OPEN on both", lambda: vote_open(host) and vote_open(client), 10)
    vid = vs(host).get("id")
    bid0 = authority(host).get("battleId")
    r.ev["vote"] = {"id": vid, "battleId": bid0}
    try:
        drop_client_mid_battle(host, client)
    except Exception as e:
        r.res.setdefault("AV4-1", []).append(f"drop_client_mid_battle: {short(e, 400)}")
        raise Stop("AV4-1")
    r.wait("AV4-1", "host coop_dialog_info code 62", lambda: dialog(host).get("code") == COOP_DLG_WAIT_PLAYERS, 30)
    st, ms, hv, ha, hb = stack(host), host.cmd({"cmd": "vote_menu_state", "id": vid}), vs(host), av(host), be(host)
    phase, absent = event_state(host).get("phase"), authority(host).get("peerAbsent")
    r.ev["drop"] = {"stack": st, "menu": {k: ms.get(k) for k in ("menuOpen", "menuStatus", "menuFinished")},
                    "vsActive": hv.get("active"), "av": {k: ha.get(k) for k in ("cancels", "state", "opens")},
                    "phase": phase, "peerAbsent": absent, "beEmitted": hb.get("emitted")}
    r.check("AV4-1", ms.get("menuStatus") == CANCELLED and ms.get("menuFinished") is True,
            f"host vote_menu_state {r.ev['drop']['menu']} (want menuStatus {CANCELLED!r}, menuFinished true)")
    r.check("AV4-1", hv.get("active") is False, f"host vote_state active={hv.get('active')} (want False)")
    r.check("AV4-1", (ha.get("cancels"), ha.get("state")) == (1, "Idle"),
            f"host abortVote cancels/state={ha.get('cancels')}/{ha.get('state')} (want 1/Idle)")
    r.check("AV4-1", st[-2:] == ["VoteMenu", "CoopState"], f"host stack {st} (want dialog 62 above the VoteMenu)")
    r.check("AV4-1", phase == "Active" and absent is True and hb.get("emitted") == 0,
            f"host phase {phase} peerAbsent {absent} battleEnd.emitted {hb.get('emitted')} (want Active, True, 0)")

    # the rejoin: test_rejoin_end_turn.stage_rejoin's steps 3-8, copied (client2; step 7 = AV4's order)
    c2 = m["client2"] = GameClient("client2", None, make_user_dir("r4l1_c_client2"))
    r.machines.append(c2)
    try:
        c2.spawn()
        c2.connect()
        rejoin_skirmish(c2, KEY_C)
    except Exception as e:
        r.res.setdefault("AV4-2", []).append(f"client2 spawn / connect / rejoin_skirmish: {short(e, 400)}")
        raise Stop("AV4-2")
    r.wait("AV4-2", "client2 back in the battle", lambda: in_battle_save(c2), 240, interval=0.5)
    r.wait("AV4-2", "client2 held on dialog 68 over BattlescapeState",
           lambda: has(c2, "BattlescapeState") and dialog(c2).get("code") == COOP_DLG_CLIENT_RESUME_HOLD, 60,
           interval=0.5)

    def offered():
        if session.has_state(host, "Profile"):        # the join's popup sits over the dialog
            host.cmd({"cmd": "profile_ok"})
            return False
        return bool(dialog(host).get("backVisible"))
    r.wait("AV4-2", "host dialog offers RESUME", offered, REJOIN_S, interval=0.5)
    d = dialog(host)
    r.check("AV4-2", (d.get("code"), d.get("backText")) == (COOP_DLG_WAIT_PLAYERS, "RESUME"),
            f"host dialog code/backText={d.get('code')}/{d.get('backText')!r} (want 62/'RESUME')")
    host.cmd({"cmd": "coop_dialog_back"})
    r.wait("AV4-2", "after RESUME host top the cancelled VoteMenu, client2 top BattlescapeState",
           lambda: top(host) == "VoteMenu" and top(c2) == "BattlescapeState", REJOIN_S,
           lambda: f"host {stack(host)} client2 {stack(c2)}", interval=0.25)
    rav.close(host, r, "AV4-2")
    r.wait("AV4-2", "both tops BattlescapeState after the host's CLOSE",
           lambda: top(host) == "BattlescapeState" and top(c2) == "BattlescapeState", 10)
    ha2, ca2 = authority(host), authority(c2)
    r.ev["resume"] = {"phase": [battle_state(gc).get("phase") for gc in (host, c2)], "peerAbsent": ha2.get("peerAbsent"),
                      "battleId": [ha2.get("battleId"), ca2.get("battleId")],
                      "vsActive": [vs(gc).get("active") for gc in (host, c2)]}
    r.check("AV4-2", r.ev["resume"]["phase"] == ["Active", "Active"] and ha2.get("peerAbsent") is False
            and ha2.get("battleId") == ca2.get("battleId") == bid0,
            f"after RESUME {r.ev['resume']} (want Active on both, peerAbsent false, battleId {bid0} kept)")
    r.check("AV4-2", r.ev["resume"]["vsActive"] == [False, False], f"vote_state active (host, client2) "
                                                                  f"{r.ev['resume']['vsActive']} (want no vote)")
    ok, msg = hash_eq(host, c2, "after the rejoin and the host's CLOSE")
    r.check("AV4-2", ok, msg)

    # the rejoined player's ABORT opens a new vote; the host's YES ends the battle for both
    rav.open_dialog_and_ok(c2, r, "AV4-3", {"cmd": "battle_ui_press", "control": "abort"})
    r.wait("AV4-3", "VOTE_OPEN on host and client2", lambda: vote_open(host) and vote_open(c2), 10)
    hv3, ha3 = vs(host), av(host)
    r.ev["newVote"] = {"starterSeat": hv3.get("starterSeat"), "votes": hv3.get("votes"), "opens": ha3.get("opens")}
    r.check("AV4-3", (hv3.get("starterSeat"), ha3.get("opens")) == (1, 2),
            f"host vote_state starterSeat {hv3.get('starterSeat')}, abortVote.opens {ha3.get('opens')} (want 1, 2)")
    r.wait("AV4-3", "the host's YES shown", lambda: top(host) == "VoteMenu" and btn_ready(host, "YES"), 5)
    r.ev["yes"] = host.cmd({"cmd": "click_widget", "match": "YES"}).get("text")
    debrief(r, host, c2, "AV4-3")
    end_cells(r, host, "AV4-3")


# ===================== boot D: AV5 =====================


def av5(r, m):
    host, client = m["host"], m["client"]
    fr = fvt.Row("AV5", host, client)
    fvt.stage_v(fr, [fvt.WS0])
    fvt.kill(fr)
    ok, trace = fvt.detect_open(fr)
    r.ev["stage"] = {"fails": fr.fails, "hostTrace": trace}
    if fr.fails or not ok or top(host) != QUESTION:
        r.gate_msg = f" (staging: fails {fr.fails}, the host's question up {ok}, host top {top(host)})"
        raise Stop(None)
    rav.open_dialog_and_ok(client, r, "AV5-1", {"cmd": "battle_ui_press", "control": "abort"})
    seen = set()
    t0 = time.time()
    while time.time() - t0 < W:
        for gc in (host, client):
            if "VoteMenu" in stack(gc):
                seen.add(f"{gc.name} VoteMenu at {round(time.time() - t0, 2)}s: {stack(gc)}")
        if top(host) != QUESTION:
            seen.add(f"host top {top(host)}")
        time.sleep(POLL)
    ha = av(host)
    r.ev["W"] = {"seen": sorted(seen)[:4], "av": {k: ha.get(k) for k in ("state", "heldWhileFatal", "arms", "opens")},
                 "fatal": (event_state(host).get("fatalVote") or {}).get("state")}
    r.check("AV5-1", not seen, f"through W: {sorted(seen)[:4]} (want no VoteMenu on either stack, the host's question "
                               f"on top)")
    r.check("AV5-1", ha.get("state") == "Armed" and (ha.get("heldWhileFatal") or 0) >= 1,
            f"host abortVote state={ha.get('state')!r} heldWhileFatal={ha.get('heldWhileFatal')} (want 'Armed', >= 1)")
    # click_widget acts on the TOP state only: the press is a step (its answer is AV5-2's check), never a row-ending wait
    wait_until(lambda: top(host) != QUESTION or btn_ready(host, "CANCEL"), 5)
    cancel = host.cmd({"cmd": "click_widget", "match": "CANCEL"})
    r.ev["cancel"] = {k: cancel.get(k) for k in ("ok", "text", "error")}
    r.check("AV5-2", cancel.get("ok") and cancel.get("text") == "CANCEL",
            f"the host's CANCEL on its question: click_widget answered {r.ev['cancel']} (host top {top(host)})")
    r.wait("AV5-2", "VOTE_OPEN on both", lambda: vote_open(host) and vote_open(client), 10)
    hv, ha2 = vs(host), av(host)
    fv = event_state(host).get("fatalVote") or {}
    r.ev["open"] = {"starterSeat": hv.get("starterSeat"), "opens": ha2.get("opens"),
                    "fatal": {k: fv.get(k) for k in ("state", "result", "answers")}}
    r.check("AV5-2", (hv.get("starterSeat"), ha2.get("opens")) == (1, 1),
            f"host vote_state starterSeat {hv.get('starterSeat')}, abortVote.opens {ha2.get('opens')} (want 1, 1)")
    r.check("AV5-2", (fv.get("state"), fv.get("result")) == ("Closed", "continue"),
            f"host fatalVote state/result={fv.get('state')!r}/{fv.get('result')!r} (want 'Closed'/'continue': the "
            f"abort vote opens after the question's CANCEL)")
    r.wait("AV5-3", "the host's YES shown", lambda: top(host) == "VoteMenu" and btn_ready(host, "YES"), 5)
    r.ev["yes"] = host.cmd({"cmd": "click_widget", "match": "YES"}).get("text")
    debrief(r, host, client, "AV5-3")
    end_cells(r, host, "AV5-3")
    fv2 = event_state(host).get("fatalVote") or {}
    r.ev["fatalEnd"] = {k: fv2.get(k) for k in ("armed", "opened", "state", "result")}
    r.check("AV5-3", (fv2.get("armed"), fv2.get("opened")) == (1, 1),
            f"host fatalVote armed/opened={fv2.get('armed')}/{fv2.get('opened')} (want 1/1: one question)")


# ===================== runner =====================


def run_row(rid, fn, m, results):
    r = Row(rid, [m["host"], m["client"]])
    t0 = time.time()
    try:
        fn(r, m)
    except Stop:
        pass
    except Exception as e:
        cur = next((c for c in CELLS[rid] if c not in r.res or r.res[c]), CELLS[rid][-1])
        r.res.setdefault(cur, []).append(f"exception {short(e, 500)}")
    r.ev["rowS"] = round(time.time() - t0, 1)
    verdict, ok = [], True
    for c in CELLS[rid]:
        if c not in r.res:
            verdict.append(f"{c} not reached{r.gate_msg}")
            ok = False
        elif r.res[c]:
            verdict.append(f"{c}: " + " ; ".join(r.res[c]))
            ok = False
    cells = {c: ("PASS" if c in r.res and not r.res[c] else "FAIL") for c in CELLS[rid]}
    print(f"EVIDENCE {rid}: {json.dumps({'cells': cells, 'ev': r.ev}, sort_keys=True, default=str)}", flush=True)
    results[rid] = ok
    if ok:
        print(f"PASS {rid}", flush=True)
    else:
        print(f"FAIL {rid}: " + " | ".join(verdict), flush=True)
        rav.capture(rid, r.machines, "row failed")
    return r.machines


def run_boot(tag, key, rid, fn, results):
    m = {"host": GameClient("host", None, make_user_dir(f"r4l1_{tag}_host")),
         "client": GameClient("client", None, make_user_dir(f"r4l1_{tag}_client"))}
    machines = [m["host"], m["client"]]
    try:
        try:
            tbe.boot(m["host"], m["client"], key)
        except Exception as e:
            results[rid] = False
            print(f"FAIL {rid}: boot: {short(e, 600)}", flush=True)
            rav.capture(f"boot {tag}", machines, "boot")
            return
        machines = run_row(rid, fn, m, results)
    finally:
        for gc in machines:
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[r4l1] shutdown {gc.name}: {short(e)}", flush=True)


def main():
    t0 = time.time()
    results = {}
    run_boot("c", KEY_C, "AV4", av4, results)
    run_boot("d", KEY_D, "AV5", av5, results)
    order = ["AV4", "AV5"]
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_abort_vote_edges: {len(passed)}/{len(order)} rows passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
