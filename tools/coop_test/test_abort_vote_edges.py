"""test_abort_vote_edges.py: the abort vote's two edges. A player's drop during an open abort vote
cancels it (the #87 cancel, as in the released game) and after the rejoin either player can ask again at once; an abort
request made while the fatal-wounds vote is open waits for it and opens once that question is cancelled.

Two boots (tbe.boot: the classic parallel skirmish, set_seed SEED_MAP 1, MAP_FP, pin_ai_neutral, hash clean), each shut
down before the next:
  Boot leave (lobby key 48614; abort_vote_leave_host / _client / _client2): leave_cancels_vote: a leave cancels the vote;
         after the rejoin (client2, test_rejoin_end_turn.stage_rejoin's steps copied) a new vote works.
  Boot fatal_vote (lobby key 48616; abort_vote_fatal_vote_host / _client): abort_waits_for_fatal_vote: an abort request
         during the fatal-wounds vote waits for it (test_fatal_vote's stage_v(r, [WS0]) + kill + detect_open: the host is
         the only voter).

Cells (GUARD = passes with or without the wait, FIX = fails without it: the abort VoteMenu then opens over the host's
question at once):
  drop_cancels_vote GUARD the drop cancels the vote: host menuStatus "CONNECTION LOST - VOTE CANCELLED"
        (vote_menu_state with the id read before the drop), menuFinished, vote_state active false, abortVote
        {cancels 1, state Idle}, dialog 62 above the VoteMenu, phase Active, peerAbsent true, battleEnd emitted 0.
  resume_no_vote GUARD after RESUME + the host's CLOSE both on BattlescapeState, no vote on either, all buckets EQUAL.
  rejoined_player_votes GUARD the rejoined player's ABORT opens a new vote (host abortVote opens 2, vote_state
        starterSeat 1) and both YES end the battle (battleEnd reason abort; both DebriefingState).
  abort_held_while_fatal FIX while the fatal vote is open no abort vote opens: no VoteMenu on either stack through W,
        the host's question on top, host abortVote {state Armed, heldWhileFatal >= 1}.
  abort_opens_after_cancel FIX after the host's CANCEL on its question the abort vote opens on both (vote_state
        starterSeat 1, host abortVote opens 1, fatalVote result "continue").
  both_yes_end_battle GUARD-after-open both YES end the battle: battleEnd reason abort, aborted true, both
        debriefings, one fatal question in the battle (host fatalVote armed 1, opened 1).

Flow rule: checks never end a row; a WAIT that times out ends the row (later cells "not reached"). Every row runs after a
failure. Each row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <cells>" and, on a FAIL, ONE
"CAPTURE <id>:" line (every machine's stack, vote_state, abortVote, battleEnd, coop_dialog_info, battle_state phase /
turn / side, the last 15 [coop-vote] / [coop-abort] / [coop-battle-end] log lines). A boot or staging miss fails its row
("boot" / every cell "not reached") with one CAPTURE line. Votes are answered with real clicks (click_widget YES / CLOSE
/ CANCEL); dismiss_popup only on an AbortMissionState.

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

KEY_LEAVE, KEY_FATAL_VOTE = "48614", "48616"
W, POLL = 5.0, 0.1
CANCELLED = "CONNECTION LOST - VOTE CANCELLED"                       # VoteMenu::cancelVote (#87)
QUESTION = fvt.QUESTION                                               # ConfirmEndMissionState
REJOIN_S = 120                                                        # stage_rejoin's bounds (240 / 60 / 120 s)
CELLS = {"leave_cancels_vote": ["drop_cancels_vote", "resume_no_vote", "rejoined_player_votes"],
         "abort_waits_for_fatal_vote": ["abort_held_while_fatal", "abort_opens_after_cancel", "both_yes_end_battle"]}


class Row(rav.Row):
    """test_abort_vote.Row plus the boot's machines (leave_cancels_vote adds client2) and a poll interval for the rejoin waits."""

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


# ===================== boot leave: leave_cancels_vote =====================


def row_leave_cancels_vote(r, m):
    host, client = m["host"], m["client"]
    rav.open_dialog_and_ok(host, r, "drop_cancels_vote", {"cmd": "battle_ui_press", "control": "abort"})
    r.wait("drop_cancels_vote", "VOTE_OPEN on both", lambda: vote_open(host) and vote_open(client), 10)
    vid = vs(host).get("id")
    bid0 = authority(host).get("battleId")
    r.ev["vote"] = {"id": vid, "battleId": bid0}
    try:
        drop_client_mid_battle(host, client)
    except Exception as e:
        r.res.setdefault("drop_cancels_vote", []).append(f"drop_client_mid_battle: {short(e, 400)}")
        raise Stop("drop_cancels_vote")
    r.wait("drop_cancels_vote", "host coop_dialog_info code 62", lambda: dialog(host).get("code") == COOP_DLG_WAIT_PLAYERS, 30)
    st, ms, hv, ha, hb = stack(host), host.cmd({"cmd": "vote_menu_state", "id": vid}), vs(host), av(host), be(host)
    phase, absent = event_state(host).get("phase"), authority(host).get("peerAbsent")
    r.ev["drop"] = {"stack": st, "menu": {k: ms.get(k) for k in ("menuOpen", "menuStatus", "menuFinished")},
                    "vsActive": hv.get("active"), "av": {k: ha.get(k) for k in ("cancels", "state", "opens")},
                    "phase": phase, "peerAbsent": absent, "beEmitted": hb.get("emitted")}
    r.check("drop_cancels_vote", ms.get("menuStatus") == CANCELLED and ms.get("menuFinished") is True,
            f"host vote_menu_state {r.ev['drop']['menu']} (want menuStatus {CANCELLED!r}, menuFinished true)")
    r.check("drop_cancels_vote", hv.get("active") is False, f"host vote_state active={hv.get('active')} (want False)")
    r.check("drop_cancels_vote", (ha.get("cancels"), ha.get("state")) == (1, "Idle"),
            f"host abortVote cancels/state={ha.get('cancels')}/{ha.get('state')} (want 1/Idle)")
    r.check("drop_cancels_vote", st[-2:] == ["VoteMenu", "CoopState"], f"host stack {st} (want dialog 62 above the VoteMenu)")
    r.check("drop_cancels_vote", phase == "Active" and absent is True and hb.get("emitted") == 0,
            f"host phase {phase} peerAbsent {absent} battleEnd.emitted {hb.get('emitted')} (want Active, True, 0)")

    # the rejoin: test_rejoin_end_turn.stage_rejoin's steps 3-8, copied (client2; step 7 = leave_cancels_vote's order)
    c2 = m["client2"] = GameClient("client2", None, make_user_dir("abort_vote_leave_client2"))
    r.machines.append(c2)
    try:
        c2.spawn()
        c2.connect()
        rejoin_skirmish(c2, KEY_LEAVE)
    except Exception as e:
        r.res.setdefault("resume_no_vote", []).append(f"client2 spawn / connect / rejoin_skirmish: {short(e, 400)}")
        raise Stop("resume_no_vote")
    r.wait("resume_no_vote", "client2 back in the battle", lambda: in_battle_save(c2), 240, interval=0.5)
    r.wait("resume_no_vote", "client2 held on dialog 68 over BattlescapeState",
           lambda: has(c2, "BattlescapeState") and dialog(c2).get("code") == COOP_DLG_CLIENT_RESUME_HOLD, 60,
           interval=0.5)

    def offered():
        if session.has_state(host, "Profile"):        # the join's popup sits over the dialog
            host.cmd({"cmd": "profile_ok"})
            return False
        return bool(dialog(host).get("backVisible"))
    r.wait("resume_no_vote", "host dialog offers RESUME", offered, REJOIN_S, interval=0.5)
    d = dialog(host)
    r.check("resume_no_vote", (d.get("code"), d.get("backText")) == (COOP_DLG_WAIT_PLAYERS, "RESUME"),
            f"host dialog code/backText={d.get('code')}/{d.get('backText')!r} (want 62/'RESUME')")
    host.cmd({"cmd": "coop_dialog_back"})
    r.wait("resume_no_vote", "after RESUME host top the cancelled VoteMenu, client2 top BattlescapeState",
           lambda: top(host) == "VoteMenu" and top(c2) == "BattlescapeState", REJOIN_S,
           lambda: f"host {stack(host)} client2 {stack(c2)}", interval=0.25)
    rav.close(host, r, "resume_no_vote")
    r.wait("resume_no_vote", "both tops BattlescapeState after the host's CLOSE",
           lambda: top(host) == "BattlescapeState" and top(c2) == "BattlescapeState", 10)
    ha2, ca2 = authority(host), authority(c2)
    r.ev["resume"] = {"phase": [battle_state(gc).get("phase") for gc in (host, c2)], "peerAbsent": ha2.get("peerAbsent"),
                      "battleId": [ha2.get("battleId"), ca2.get("battleId")],
                      "vsActive": [vs(gc).get("active") for gc in (host, c2)]}
    r.check("resume_no_vote", r.ev["resume"]["phase"] == ["Active", "Active"] and ha2.get("peerAbsent") is False
            and ha2.get("battleId") == ca2.get("battleId") == bid0,
            f"after RESUME {r.ev['resume']} (want Active on both, peerAbsent false, battleId {bid0} kept)")
    r.check("resume_no_vote", r.ev["resume"]["vsActive"] == [False, False], f"vote_state active (host, client2) "
                                                                  f"{r.ev['resume']['vsActive']} (want no vote)")
    ok, msg = hash_eq(host, c2, "after the rejoin and the host's CLOSE")
    r.check("resume_no_vote", ok, msg)

    # the rejoined player's ABORT opens a new vote; the host's YES ends the battle for both
    rav.open_dialog_and_ok(c2, r, "rejoined_player_votes", {"cmd": "battle_ui_press", "control": "abort"})
    r.wait("rejoined_player_votes", "VOTE_OPEN on host and client2", lambda: vote_open(host) and vote_open(c2), 10)
    hv3, ha3 = vs(host), av(host)
    r.ev["newVote"] = {"starterSeat": hv3.get("starterSeat"), "votes": hv3.get("votes"), "opens": ha3.get("opens")}
    r.check("rejoined_player_votes", (hv3.get("starterSeat"), ha3.get("opens")) == (1, 2),
            f"host vote_state starterSeat {hv3.get('starterSeat')}, abortVote.opens {ha3.get('opens')} (want 1, 2)")
    r.wait("rejoined_player_votes", "the host's YES shown", lambda: top(host) == "VoteMenu" and btn_ready(host, "YES"), 5)
    r.ev["yes"] = host.cmd({"cmd": "click_widget", "match": "YES"}).get("text")
    debrief(r, host, c2, "rejoined_player_votes")
    end_cells(r, host, "rejoined_player_votes")


# ===================== boot fatal_vote: abort_waits_for_fatal_vote =====================


def row_abort_waits_for_fatal_vote(r, m):
    host, client = m["host"], m["client"]
    fr = fvt.Row("abort_waits_for_fatal_vote", host, client)
    fvt.stage_v(fr, [fvt.WS0])
    fvt.kill(fr)
    ok, trace = fvt.detect_open(fr)
    r.ev["stage"] = {"fails": fr.fails, "hostTrace": trace}
    if fr.fails or not ok or top(host) != QUESTION:
        r.gate_msg = f" (staging: fails {fr.fails}, the host's question up {ok}, host top {top(host)})"
        raise Stop(None)
    rav.open_dialog_and_ok(client, r, "abort_held_while_fatal", {"cmd": "battle_ui_press", "control": "abort"})
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
    r.check("abort_held_while_fatal", not seen, f"through W: {sorted(seen)[:4]} (want no VoteMenu on either stack, the host's question "
                               f"on top)")
    r.check("abort_held_while_fatal", ha.get("state") == "Armed" and (ha.get("heldWhileFatal") or 0) >= 1,
            f"host abortVote state={ha.get('state')!r} heldWhileFatal={ha.get('heldWhileFatal')} (want 'Armed', >= 1)")
    # click_widget acts on the TOP state only: the press is a step (its answer is abort_opens_after_cancel's check), never a row-ending wait
    wait_until(lambda: top(host) != QUESTION or btn_ready(host, "CANCEL"), 5)
    cancel = host.cmd({"cmd": "click_widget", "match": "CANCEL"})
    r.ev["cancel"] = {k: cancel.get(k) for k in ("ok", "text", "error")}
    r.check("abort_opens_after_cancel", cancel.get("ok") and cancel.get("text") == "CANCEL",
            f"the host's CANCEL on its question: click_widget answered {r.ev['cancel']} (host top {top(host)})")
    r.wait("abort_opens_after_cancel", "VOTE_OPEN on both", lambda: vote_open(host) and vote_open(client), 10)
    hv, ha2 = vs(host), av(host)
    fv = event_state(host).get("fatalVote") or {}
    r.ev["open"] = {"starterSeat": hv.get("starterSeat"), "opens": ha2.get("opens"),
                    "fatal": {k: fv.get(k) for k in ("state", "result", "answers")}}
    r.check("abort_opens_after_cancel", (hv.get("starterSeat"), ha2.get("opens")) == (1, 1),
            f"host vote_state starterSeat {hv.get('starterSeat')}, abortVote.opens {ha2.get('opens')} (want 1, 1)")
    r.check("abort_opens_after_cancel", (fv.get("state"), fv.get("result")) == ("Closed", "continue"),
            f"host fatalVote state/result={fv.get('state')!r}/{fv.get('result')!r} (want 'Closed'/'continue': the "
            f"abort vote opens after the question's CANCEL)")
    r.wait("both_yes_end_battle", "the host's YES shown", lambda: top(host) == "VoteMenu" and btn_ready(host, "YES"), 5)
    r.ev["yes"] = host.cmd({"cmd": "click_widget", "match": "YES"}).get("text")
    debrief(r, host, client, "both_yes_end_battle")
    end_cells(r, host, "both_yes_end_battle")
    fv2 = event_state(host).get("fatalVote") or {}
    r.ev["fatalEnd"] = {k: fv2.get(k) for k in ("armed", "opened", "state", "result")}
    r.check("both_yes_end_battle", (fv2.get("armed"), fv2.get("opened")) == (1, 1),
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
    m = {"host": GameClient("host", None, make_user_dir(f"abort_vote_{tag}_host")),
         "client": GameClient("client", None, make_user_dir(f"abort_vote_{tag}_client"))}
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
                print(f"[test_abort_vote_edges] shutdown {gc.name}: {short(e)}", flush=True)


def main():
    t0 = time.time()
    results = {}
    run_boot("leave", KEY_LEAVE, "leave_cancels_vote", row_leave_cancels_vote, results)
    run_boot("fatal_vote", KEY_FATAL_VOTE, "abort_waits_for_fatal_vote", row_abort_waits_for_fatal_vote, results)
    order = ["leave_cancels_vote", "abort_waits_for_fatal_vote"]
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_abort_vote_edges: {len(passed)}/{len(order)} rows passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
