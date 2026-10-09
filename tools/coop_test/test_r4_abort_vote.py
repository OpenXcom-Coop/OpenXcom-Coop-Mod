"""R4-L1 S-A - test_r4_abort_vote.py: either player's ABORT opens vanilla's abort screen, its OK opens ONE abort vote
on both machines (the asker's YES counted), the vote is unanimous with no deadline, no countdown and no starter
cooldown, one NO fails it and the battle goes on, END TURN waits while it is open, and all YES ends the battle for both
through the host's battle-end path once any running action has finished (owner design-D8, D231, D244; spec docs
rewrite/prompts/r4l1_abort_vote.md (f) stage S-A with AMENDMENT R4-L1-1; TASK 0 constants docs
rewrite/r4l1-task0/CONSTANTS.md: HOST_DLG, the vote texts, the walk pin, AV1b-2's label, the walls).

Two boots (tbe.boot: the classic parallel skirmish, set_seed SEED_MAP 1, MAP_FP, pin_ai_neutral, hash clean), each shut
down before the next:
  Boot A (lobby key 48612): AV0 rules and the host's dialog; AV2 the client's ABORT opens the vote and a NO cancels it;
         AV2b no wait before a new vote (D244); AV1b END TURN waits for the vote.
  Boot B (lobby key 48613): AV1 the host's ABORT opens it, one YES does not abort, no deadline; AV3 a vote passed during
         a running action lands after it and both YES end the battle for both.

Cells (RED = fails on the red commit, GUARD = passes on both builds; AV1b-2 is RED per TASK 0 T0-2 (b): on the unchanged
build the client's END TURN under an open vote commits within 0.2 s):
  AV0-1 RED unanimous abort rules (requiredYes 3, pending after 2 YES, failed after a NO, noDeadline true);
  AV0-2 GUARD other votes keep #87's rules; AV0-3 GUARD the host's AbortMissionState = HOST_DLG, ESC closes, no vote.
  AV2-1 RED the client's dialog (HOST_DLG, no refusal banner, buckets EQUAL, dialogDonor 1); AV2-2 RED the vote on both;
  AV2-3 RED a NO fails it, the battle goes on. AV2b-1 RED the same asker's second vote opens at once (no 558, cooldown
  0, opens 2); AV2b-2 RED it fails on the NO. AV1b-1 RED the host's ABORT after its END TURN opens the vote; AV1b-2 RED
  no END TURN commit while it is open (heldCommits >= 1); AV1b-3 RED the held presses commit once after the failed
  vote's CLOSE. AV1-1 RED the vote opens; AV1-2 RED one YES does not abort; AV1-3 RED no deadline (vote_force_timeout
  refused, no "TIME", the rule line); AV1-4 GUARD-after-open dismiss_popup refuses the VoteMenu; AV1-5 RED the NO fails
  it. AV3-1 GUARD the walk ran under the vote; AV3-2 RED the apply waited for it; AV3-3 RED both end on their debriefing.

Flow rule: checks never end a row; a WAIT that times out ends the row (later cells "not reached"). Every row runs after a
failure. Each row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <cells>" and, on a FAIL, ONE
"CAPTURE <id>:" line (both stacks, vote_state, abortVote, battleEnd, coop_dialog_info, battle_state phase / turn / side,
the last 15 [coop-vote] / [coop-abort] / [coop-battle-end] log lines). A boot miss fails its rows "boot" with one
CAPTURE line. Votes are answered with vote_cast or real clicks (click_widget YES / NO / CLOSE, only once the button is
visible and not hidden); dismiss_popup only on an AbortMissionState (and once, in AV1-4, on the VoteMenu it refuses).

RED (commit 1 = this file, the six re-points and the zero-valued probe plumbing): exit 2 with AV0-1, AV2-1, AV2b-1,
AV1b-1, AV1-1 FAIL (their later cells "not reached": the client's press is refused, the host's OK ends the battle at
once), AV0-2 / AV0-3 PASS, AV3 FAIL "not reached" (boot B's battle ended at AV1). Commit 2: exit 0.
WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_r4_abort_vote.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state
import test_w2_battle_end as tbe

KEY_A, KEY_B = "48612", "48613"
W, POLL = 5.0, 0.1
TITLE, QUESTION = "Abort Mission", "Abort Mission?"                   # en-US STR_ABORT_MISSION / _QUESTION
RULE = "STRICT MAJORITY: 2 OF 2 YES VOTES"
REFUSAL = "Only the host can abort the mission"                       # STR_COOP_ABORT_HOST_ONLY (retired)
VOTEMENU_REFUSAL = "VoteMenu (answer via vote_cast; not dismissable)"
# CONSTANTS T0-1 (a): the host's AbortMissionState non-button texts on the classic boot, in order, with `visible`.
HOST_DLG = [["7 Units in X-Com Craft", True], ["0 Units in Target Exit", False], ["0 Units left outside", True],
            [QUESTION, True]]
WALK_ACTOR, WALK_DEST = 8, (4, 9, 0)                                  # CONSTANTS T0-2 (a): 4.19 s, 9 steps
AV1B2_LABEL = "RED"                                                   # CONSTANTS T0-2 (b)
ENDING_PINS = tbe.ROW_EXPECT["E2"]
COOLDOWN_DLG = 558
CELLS = {"AV0": ["AV0-1", "AV0-2", "AV0-3"], "AV2": ["AV2-1", "AV2-2", "AV2-3"], "AV2b": ["AV2b-1", "AV2b-2"],
         "AV1b": ["AV1b-1", "AV1b-2", "AV1b-3"], "AV1": ["AV1-1", "AV1-2", "AV1-3", "AV1-4", "AV1-5"],
         "AV3": ["AV3-1", "AV3-2", "AV3-3"]}


class Stop(Exception):
    pass


def short(e, n=300):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:
        return [f"<get_state: {short(e, 120)}>"]


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def vs(gc):
    return gc.cmd({"cmd": "vote_state"})


def av(gc):
    return event_state(gc).get("abortVote") or {}


def be(gc):
    return event_state(gc).get("battleEnd") or {}


def vote_open(gc):
    v = vs(gc)
    return bool(v.get("active") and v.get("action") == "abandon_mission" and v.get("menuOpen"))


def widgets(gc):
    r = gc.cmd({"cmd": "list_widgets"})
    ws = [w for w in r.get("widgets") or [] if w.get("text") is not None]
    return {"state": (r.get("state") or "").replace("class OpenXcom::", ""),
            "texts": [[w["text"], w.get("visible")] for w in ws if "TextButton" not in (w.get("type") or "")],
            "buttons": {w["text"]: [w.get("visible"), w.get("hidden")] for w in ws if "TextButton" in (w.get("type") or "")}}


def btn_ready(gc, text):
    return widgets(gc)["buttons"].get(text) == [True, False]


def wait_until(pred, timeout, interval=POLL):
    t0 = time.time()
    while True:
        try:
            if pred():
                return True, round(time.time() - t0, 2)
        except Exception:
            pass
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def hash_eq(host, client, what):
    try:
        session.wait_host_idle(host, client, timeout=30)
        session.assert_hash_clean(host, client, full=True, what=what)
        return True, ""
    except Exception as e:
        return False, short(e, 500)


def log_tags(gc, n=15):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n").split("\t")[-1] for ln in f]
    except OSError:
        return []
    return [ln for ln in lines if any(t in ln for t in ("[coop-vote]", "[coop-abort]", "[coop-battle-end]"))][-n:]


def capture(rid, machines, why):
    cap = {}
    for gc in machines:
        try:
            es = event_state(gc)
            bs = battle_state(gc)
            cap[gc.name] = {"stack": stack(gc), "vote_state": vs(gc), "abortVote": es.get("abortVote"),
                            "battleEnd": es.get("battleEnd"), "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}),
                            "battle": {k: bs.get(k) for k in ("phase", "turn", "side")}, "log": log_tags(gc)}
        except Exception as e:
            cap[gc.name] = {"stack": stack(gc), "probe": short(e), "log": log_tags(gc)}
    print(f"CAPTURE {rid} ({why}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


class Row:
    def __init__(self, rid):
        self.rid, self.res, self.ev, self.gate_msg = rid, {}, {}, ""

    def check(self, cell, ok, msg):
        self.res.setdefault(cell, [])
        if not ok:
            self.res[cell].append(msg)

    def wait(self, cell, desc, pred, timeout, diag=None):
        """A WAIT: its timeout fails `cell` and ends the row (later cells "not reached")."""
        ok, secs = wait_until(pred, timeout)
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

    def gate(self, desc, pred, timeout, diag):
        """The row's precondition: a miss ends the row with every cell "not reached"."""
        ok, secs = wait_until(pred, timeout)
        if not ok:
            self.gate_msg = f" ({desc}: {diag()})"
            self.ev["gate"] = self.gate_msg
            raise Stop(None)


def ends(host, client):
    return (f"host top {top(host)}, host battleEnd.emitted {be(host).get('emitted')}, client top {top(client)}, "
            f"client banner {battle_state(client).get('coopWaitText')!r}")


def close(gc, r, cell):
    """CLOSE(gc): click_widget CLOSE while gc's VoteMenu is its top state and the button shows."""
    r.wait(cell, f"{gc.name} VoteMenu CLOSE shown on top", lambda: top(gc) == "VoteMenu" and btn_ready(gc, "CLOSE"), 5)
    resp = gc.cmd({"cmd": "click_widget", "match": "CLOSE"})
    r.ev[f"{gc.name} CLOSE"] = resp.get("text") or resp.get("error")


def both_close(host, client, r, cell):
    close(client, r, cell)
    close(host, r, cell)
    r.wait(cell, "both tops BattlescapeState after CLOSE",
           lambda: top(host) == "BattlescapeState" and top(client) == "BattlescapeState", 5)


def open_dialog_and_ok(gc, r, cell, press):
    """`press` on gc (battle_ui_press / battle_action abort), wait its AbortMissionState, read its texts, OK."""
    r.ev[f"{gc.name} press"] = gc.cmd(press)
    r.wait(cell, f"{gc.name} top AbortMissionState", lambda: top(gc) == "AbortMissionState", 5,
           lambda: f"{gc.name} stack {stack(gc)} banner {battle_state(gc).get('coopWaitText')!r}")
    w = widgets(gc)
    d = gc.cmd({"cmd": "dismiss_popup"})
    r.ev[f"{gc.name} dialog"] = w["texts"]
    r.check(cell, d.get("handled") == "AbortMissionState", f"{gc.name} dismiss_popup answered {d} (want handled "
                                                             f"AbortMissionState)")
    return w


def failed_cells(r, host, client, cell, fails):
    """The vote failed on both (AV2-3 / AV2b-2 / AV1-5 shape): finished, not passed, VOTE FAILED, host AV fails."""
    r.wait(cell, "both vote_state finished", lambda: vs(host).get("finished") and vs(client).get("finished"), 10)
    for gc in (host, client):
        v = vs(gc)
        r.ev[f"{gc.name} vs after"] = {k: v.get(k) for k in ("finished", "passed", "votes", "menuStatus")}
        r.check(cell, v.get("passed") is False and v.get("menuStatus") == "VOTE FAILED",
                f"{gc.name} vote_state passed={v.get('passed')} menuStatus={v.get('menuStatus')!r} (want False, "
                f"'VOTE FAILED')")
    if fails is not None:
        r.check(cell, av(host).get("fails") == fails, f"host abortVote.fails={av(host).get('fails')} (want {fails})")


# ===================== boot A rows =====================


def av0(host, client, r):
    p1 = host.cmd({"cmd": "vote_session_probe", "action": "abandon_mission", "players": 3,
                   "casts": [{"seat": 1, "yes": True}]})
    p2 = host.cmd({"cmd": "vote_session_probe", "action": "abandon_mission", "players": 3,
                   "casts": [{"seat": 1, "yes": True}, {"seat": 2, "yes": False}]})
    p3 = host.cmd({"cmd": "vote_session_probe", "action": "probe", "players": 3, "casts": [{"seat": 1, "yes": True}]})
    r.ev["probes"] = [{k: p.get(k) for k in ("requiredYes", "decision", "votes", "noDeadline")} for p in (p1, p2, p3)]
    r.check("AV0-1", p1.get("requiredYes") == 3 and p1.get("decision") == "pending" and p2.get("decision") == "failed"
            and p1.get("noDeadline") is True, f"abandon_mission probe {r.ev['probes'][:2]} (want requiredYes 3, "
                                              f"pending after 2 YES, failed after a NO, noDeadline true)")
    r.check("AV0-2", p3.get("requiredYes") == 2 and p3.get("decision") == "passed" and p3.get("noDeadline") is False,
            f"probe {r.ev['probes'][2]} (want requiredYes 2, passed, noDeadline false)")
    r.ev["press"] = host.cmd({"cmd": "battle_ui_press", "control": "abort"})
    r.wait("AV0-3", "host top AbortMissionState", lambda: top(host) == "AbortMissionState", 5)
    w = widgets(host)
    r.ev["dialog"] = w["texts"]
    r.check("AV0-3", w["texts"] == HOST_DLG, f"host dialog texts {w['texts']} (want HOST_DLG {HOST_DLG})")
    host.cmd({"cmd": "inject_input", "kind": "key", "key": 27})
    r.wait("AV0-3", "ESC closes the host's dialog", lambda: top(host) == "BattlescapeState", 5)
    for gc in (host, client):
        r.check("AV0-3", vs(gc).get("active") is False, f"{gc.name} vote_state active={vs(gc).get('active')} (want "
                                                        f"False: no vote)")


def av2(host, client, r):
    r.ev["press"] = client.cmd({"cmd": "battle_ui_press", "control": "abort"})
    time.sleep(0.3)
    r.ev["banner"] = battle_state(client).get("coopWaitText")
    r.wait("AV2-1", "client top AbortMissionState (red: refused)", lambda: top(client) == "AbortMissionState", 5,
           lambda: ends(host, client))
    w = widgets(client)
    r.ev["dialog"] = w["texts"]
    r.check("AV2-1", w["texts"] == HOST_DLG, f"client dialog texts {w['texts']} (want HOST_DLG {HOST_DLG})")
    banner = battle_state(client).get("coopWaitText")
    r.check("AV2-1", banner != REFUSAL, f"client banner {banner!r} (the retired refusal)")
    ok, msg = hash_eq(host, client, "with the client's abort dialog open")
    r.check("AV2-1", ok, f"hash with the client's dialog open: {msg}")
    r.check("AV2-1", av(client).get("dialogDonor") == 1, f"client abortVote.dialogDonor={av(client).get('dialogDonor')}"
                                                         f" (want 1)")
    d = client.cmd({"cmd": "dismiss_popup"})
    r.check("AV2-1", d.get("handled") == "AbortMissionState", f"client dismiss_popup answered {d}")
    r.wait("AV2-2", "VOTE_OPEN on both", lambda: vote_open(host) and vote_open(client), 10)
    r.wait("AV2-2", "the host's NO shown", lambda: btn_ready(host, "NO"), 5)
    hv, wh, wc = vs(host), widgets(host), widgets(client)
    r.ev["vs"] = {k: hv.get(k) for k in ("starterSeat", "totalPlayers", "requiredYes", "votes", "noDeadline")}
    r.ev["widgets"] = {"host": wh, "client": wc}
    r.check("AV2-2", r.ev["vs"] == {"starterSeat": 1, "totalPlayers": 2, "requiredYes": 2, "votes": [-1, 1],
                                    "noDeadline": True}, f"host vote_state {r.ev['vs']} (want starter 1, 2 players, "
                                                         f"requiredYes 2, votes [-1, 1], noDeadline true)")
    for name, w, want in (("client", wc, False), ("host", wh, True)):
        for b in ("YES", "NO"):
            vis = (w["buttons"].get(b) or [None])[0]
            r.check("AV2-2", vis is want, f"{name} {b} button visible={vis} (want {want})")
        r.check("AV2-2", [t for t, _v in w["texts"][:2]] == [TITLE, QUESTION],
                f"{name} vote title / question {w['texts'][:2]} (want {TITLE!r} / {QUESTION!r})")
    ha, ca = av(host), av(client)
    r.ev["av"] = {"host": ha, "client": {k: ca.get(k) for k in ("requests", "dialogDonor")}}
    r.check("AV2-2", (ha.get("arms"), ha.get("opens"), ha.get("state")) == (1, 1, "Open"),
            f"host abortVote arms/opens/state={ha.get('arms')}/{ha.get('opens')}/{ha.get('state')} (want 1/1/Open)")
    r.check("AV2-2", ca.get("requests") == 1, f"client abortVote.requests={ca.get('requests')} (want 1)")
    r.ev["no"] = host.cmd({"cmd": "click_widget", "match": "NO"}).get("text")
    failed_cells(r, host, client, "AV2-3", 1)
    both_close(host, client, r, "AV2-3")
    seen = set()
    t0 = time.time()
    while time.time() - t0 < W:
        for gc in (host, client):
            e = event_state(gc)
            if top(gc) != "BattlescapeState" or e.get("phase") != "Active" or (e.get("battleEnd") or {}).get("emitted"):
                seen.add(f"{gc.name}: top {top(gc)} phase {e.get('phase')}")
        time.sleep(POLL)
    r.check("AV2-3", not seen, f"through W after CLOSE: {sorted(seen)} (want BattlescapeState, Active, no battle_end)")
    ok, msg = hash_eq(host, client, "after the failed vote")
    r.check("AV2-3", ok, msg)
    for gc in (host, client):
        r.check("AV2-3", event_state(gc).get("desyncSeen") is False, f"{gc.name} desyncSeen")


def av2b(host, client, r):
    r.wait("AV2b-1", "host abortVote state Idle", lambda: av(host).get("state") == "Idle", 2)
    open_dialog_and_ok(client, r, "AV2b-1", {"cmd": "battle_ui_press", "control": "abort"})
    r.wait("AV2b-1", "VOTE_OPEN on both", lambda: vote_open(host) and vote_open(client), 10)
    dlg = {gc.name: gc.cmd({"cmd": "coop_dialog_info"}) for gc in (host, client)}
    cd = host.cmd({"cmd": "vote_cooldown_state", "seat": 1})
    r.ev.update({"dialogs": {n: [d.get("present"), d.get("code")] for n, d in dlg.items()},
                 "cooldown": cd.get("remainingMs"), "hostOpens": av(host).get("opens")})
    for n, d in dlg.items():
        r.check("AV2b-1", d.get("code") != COOLDOWN_DLG, f"{n} coop_dialog_info code {d.get('code')} (the cooldown box)")
    r.check("AV2b-1", cd.get("remainingMs") == 0, f"vote_cooldown_state seat 1 remainingMs={cd.get('remainingMs')}")
    r.check("AV2b-1", av(host).get("opens") == 2, f"host abortVote.opens={av(host).get('opens')} (want 2)")
    r.ev["cast"] = host.cmd({"cmd": "vote_cast", "yes": False})
    failed_cells(r, host, client, "AV2b-2", 2)
    both_close(host, client, r, "AV2b-2")


def av1b(host, client, r):
    host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    r.wait("AV1b-1", "host END TURN 1/2", lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", 20)
    open_dialog_and_ok(host, r, "AV1b-1", {"cmd": "battle_action", "action": "abort"})
    r.wait("AV1b-1", "VOTE_OPEN on both (red: the host's OK ended the battle)",
           lambda: vote_open(host) and vote_open(client), 10, lambda: ends(host, client))
    hv = vs(host)
    r.check("AV1b-1", (hv.get("starterSeat"), hv.get("votes")) == (0, [1, -1]),
            f"host vote_state starter/votes={hv.get('starterSeat')}/{hv.get('votes')} (want 0/[1, -1])")
    turn0 = battle_state(host).get("turn")
    r.ev["clientEndTurn"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    seen = set()
    t0 = time.time()
    while time.time() - t0 < W:
        for gc in (host, client):
            if "NextTurnState" in stack(gc) or battle_state(gc).get("turn") != turn0:
                seen.add(f"{gc.name}: {stack(gc)} turn {battle_state(gc).get('turn')}")
        time.sleep(POLL)
    r.ev["heldCommits"] = av(host).get("heldCommits")
    r.check("AV1b-2", not seen, f"an END TURN commit under the open vote: {sorted(seen)}")
    r.check("AV1b-2", (r.ev["heldCommits"] or 0) >= 1, f"host abortVote.heldCommits={r.ev['heldCommits']} (want >= 1)")
    r.ev["cast"] = client.cmd({"cmd": "vote_cast", "yes": False})
    r.wait("AV1b-3", "both vote_state finished", lambda: vs(host).get("finished") and vs(client).get("finished"), 10)
    close(client, r, "AV1b-3")
    close(host, r, "AV1b-3")
    r.wait("AV1b-3", "the host's NextTurnState after the CLOSE", lambda: "NextTurnState" in stack(host), 15)

    def cycled():
        for gc in (host, client):
            if top(gc) == "NextTurnState":
                gc.cmd({"cmd": "close_nextturn"})
        bs = [battle_state(gc) for gc in (host, client)]
        return (all(b.get("side") == 0 and b.get("turn") == turn0 + 1 for b in bs)
                and top(host) == "BattlescapeState" and top(client) == "BattlescapeState")
    r.wait("AV1b-3", "both on the player side of turn +1", cycled, 60)
    ok, msg = hash_eq(host, client, "after the held turn")
    r.check("AV1b-3", ok, msg)
    for gc in (host, client):
        r.check("AV1b-3", event_state(gc).get("desyncSeen") is False, f"{gc.name} desyncSeen")


# ===================== boot B rows =====================


def av1(host, client, r):
    open_dialog_and_ok(host, r, "AV1-1", {"cmd": "battle_action", "action": "abort"})
    r.wait("AV1-1", "VOTE_OPEN on both (red: the host's OK ended the battle)",
           lambda: vote_open(host) and vote_open(client), 10, lambda: ends(host, client))
    hv = vs(host)
    r.check("AV1-1", (hv.get("starterSeat"), hv.get("votes")) == (0, [1, -1]),
            f"host vote_state starter/votes={hv.get('starterSeat')}/{hv.get('votes')} (want 0/[1, -1])")
    seen = set()
    t0 = time.time()
    while time.time() - t0 < W:
        for gc in (host, client):
            e = event_state(gc)
            if (e.get("phase") != "Active" or (e.get("battleEnd") or {}).get("emitted") or "DebriefingState" in stack(gc)
                    or not vs(gc).get("active")):
                seen.add(f"{gc.name}: phase {e.get('phase')} stack {stack(gc)} vote active {vs(gc).get('active')}")
        time.sleep(POLL)
    r.check("AV1-2", not seen, f"one YES aborted or closed the vote: {sorted(seen)}")
    ft = host.cmd({"cmd": "vote_force_timeout"})
    hv = vs(host)
    wh, wc = widgets(host), widgets(client)
    r.ev.update({"forceTimeout": ft, "vsAfter": {k: hv.get(k) for k in ("active", "remainingMs", "noDeadline")},
                 "status": [vs(gc).get("menuStatus") for gc in (host, client)], "widgets": {"host": wh, "client": wc}})
    r.check("AV1-3", ft.get("accepted") is False and hv.get("active") is True,
            f"vote_force_timeout {ft}, host active {hv.get('active')} (want accepted false, still active)")
    r.check("AV1-3", hv.get("remainingMs") == 0 and hv.get("noDeadline") is True,
            f"host remainingMs={hv.get('remainingMs')} noDeadline={hv.get('noDeadline')} (want 0, true)")
    for n, s in zip(("host", "client"), r.ev["status"]):
        r.check("AV1-3", "TIME" not in (s or ""), f"{n} menuStatus {s!r} (no countdown)")
    for n, w in (("host", wh), ("client", wc)):
        r.check("AV1-3", [RULE, True] in w["texts"], f"{n} VoteMenu texts {w['texts']} (want the rule {RULE!r})")
    d = host.cmd({"cmd": "dismiss_popup"})
    r.ev["dismiss"] = d
    r.check("AV1-4", d.get("error") == VOTEMENU_REFUSAL and top(host) == "VoteMenu",
            f"host dismiss_popup {d}, top {top(host)} (want the VoteMenu refusal, VoteMenu on top)")
    r.ev["cast"] = client.cmd({"cmd": "vote_cast", "yes": False})
    failed_cells(r, host, client, "AV1-5", None)
    both_close(host, client, r, "AV1-5")
    ok, msg = hash_eq(host, client, "after AV1's failed vote")
    r.check("AV1-5", ok, msg)


def av3(host, client, r):
    crash0 = session._crash_log_snapshot()
    r.gate("boot B's battle still running", lambda: (top(host) == "BattlescapeState" and top(client) == "BattlescapeState"
                                                  and event_state(host).get("phase") == "Active"), 5,
           lambda: ends(host, client))
    open_dialog_and_ok(host, r, "AV3-1", {"cmd": "battle_action", "action": "abort"})
    r.wait("AV3-1", "VOTE_OPEN on both", lambda: vote_open(host) and vote_open(client), 10)
    cov0 = (event_state(host).get("hostCovered") or {}).get("steps", 0)
    walk = session.send_walk(client, WALK_ACTOR, WALK_DEST)
    r.ev["walk"] = {k: walk.get(k) for k in ("ok", "iseq", "error")}
    r.wait("AV3-1", "the host runs the walk (busyOwnerSeat != -1)", lambda: event_state(host).get("busyOwnerSeat") != -1, 5)
    r.wait("AV3-1", "the client's YES shown", lambda: btn_ready(client, "YES"), 5)
    t_yes = time.time()
    r.ev["yes"] = client.cmd({"cmd": "click_widget", "match": "YES"}).get("text")
    hd, hsecs = wait_until(lambda: top(host) == "DebriefingState", 30)
    cd, csecs = wait_until(lambda: top(client) in tbe.CLIENT_END_TOPS, 30)
    ha, ca, hb, cb = av(host), av(client), be(host), be(client)
    cover = (event_state(host).get("hostCovered") or {}).get("steps", 0) - cov0
    r.ev.update({"debrief": {"host": [hd, hsecs], "client": [cd, csecs], "fromYes": round(time.time() - t_yes, 2)},
                 "coveredDelta": cover, "av": {"host": ha, "client": ca},
                 "be": {"host": hb, "client": {k: cb.get(k) for k in ("applied", "seq", "reason", "aborted")}},
                 "stacks": {"host": stack(host), "client": stack(client)}})
    r.check("AV3-1", cover > 0 and (ha.get("actionIdAtPass") or 0) != 0,
            f"hostCovered steps delta {cover}, abortVote.actionIdAtPass {ha.get('actionIdAtPass')} (want > 0, != 0)")
    want = {"passes": 1, "applies": 1, "quiescentAtApply": True, "appliedInExit": 0, "state": "Applied"}
    got = {k: ha.get(k) for k in want}
    r.check("AV3-2", got == want and (ha.get("waitPasses") or 0) >= 1,
            f"host abortVote {got} waitPasses {ha.get('waitPasses')} (want {want}, waitPasses >= 1)")
    r.check("AV3-2", (hb.get("quiescentAtEmit"), hb.get("actionIdAtEmit"), hb.get("evsAfter")) == (True, 0, 0),
            f"host battleEnd quiescentAtEmit/actionIdAtEmit/evsAfter={hb.get('quiescentAtEmit')}/"
            f"{hb.get('actionIdAtEmit')}/{hb.get('evsAfter')} (want True/0/0)")
    for k in ("reason", "aborted", "inExitArea"):
        r.check("AV3-3", hb.get(k) == ENDING_PINS[k], f"host battleEnd.{k}={hb.get(k)!r} (want {ENDING_PINS[k]!r})")
    r.check("AV3-3", tbe.verdicts(hb) == ENDING_PINS["verdicts"] and tbe.tally(hb) == ENDING_PINS["tally"],
            f"host battleEnd verdicts {tbe.verdicts(hb)} tally {tbe.tally(hb)} (want the E2 pins)")
    r.check("AV3-3", (cb.get("applied"), cb.get("seq"), cb.get("reason")) == (1, hb.get("seq"), "abort"),
            f"client battleEnd applied/seq/reason={cb.get('applied')}/{cb.get('seq')}/{cb.get('reason')} "
            f"(want 1/{hb.get('seq')}/abort)")
    r.check("AV3-3", hd and cd and top(client) == "DebriefingState"
            and client.cmd({"cmd": "debrief_state"}).get("displayOnly") is True,
            f"debriefs: host {hd} ({hsecs}s), client {cd} ({csecs}s) top {top(client)} (want both DebriefingState, the "
            f"client's display-only)")
    r.check("AV3-3", ca.get("menuPopped") == 1 and "VoteMenu" not in stack(client),
            f"client abortVote.menuPopped={ca.get('menuPopped')} stack {stack(client)} (want 1, no VoteMenu)")
    for gc in (host, client):
        r.check("AV3-3", event_state(gc).get("desyncSeen") is False, f"{gc.name} desyncSeen")
    new_crash = sorted(session._crash_log_snapshot() - crash0)
    r.check("AV3-3", not new_crash, f"new crash log(s): {new_crash}")
    try:
        session.assert_client_zero_disk(client.user_dir)
    except AssertionError as e:
        r.check("AV3-3", False, str(e))


# ===================== runner =====================


def run_row(rid, fn, host, client, results):
    r = Row(rid)
    try:
        fn(host, client, r)
    except Stop:
        pass
    except Exception as e:
        cur = next((c for c in CELLS[rid] if c not in r.res or r.res[c]), CELLS[rid][-1])
        r.res.setdefault(cur, []).append(f"exception {short(e, 500)}")
    verdict, ok = [], True
    for c in CELLS[rid]:
        if c not in r.res:
            verdict.append(f"{c} not reached{r.gate_msg}")
            ok = False
        elif r.res[c]:
            verdict.append(f"{c}: " + " ; ".join(r.res[c]))
            ok = False
    print(f"EVIDENCE {rid}: {json.dumps({'cells': {c: ('PASS' if c in r.res and not r.res[c] else 'FAIL') for c in CELLS[rid]}, 'ev': r.ev}, sort_keys=True, default=str)}", flush=True)
    results[rid] = ok
    if ok:
        print(f"PASS {rid}", flush=True)
    else:
        print(f"FAIL {rid}: " + " | ".join(verdict), flush=True)
        capture(rid, (host, client), "row failed")


def run_boot(tag, key, rows, results):
    host = GameClient("host", 49612, make_user_dir(f"r4l1_{tag}_host"))
    client = GameClient("client", 49613, make_user_dir(f"r4l1_{tag}_client"))
    try:
        try:
            tbe.boot(host, client, key)
        except Exception as e:
            for rid, _fn in rows:
                results[rid] = False
                print(f"FAIL {rid}: boot: {short(e, 600)}", flush=True)
            capture(f"boot {tag}", (host, client), "boot")
            return
        for rid, fn in rows:
            run_row(rid, fn, host, client, results)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[r4l1] shutdown {gc.name}: {short(e)}", flush=True)


def main():
    t0 = time.time()
    results = {}
    run_boot("a", KEY_A, (("AV0", av0), ("AV2", av2), ("AV2b", av2b), ("AV1b", av1b)), results)
    run_boot("b", KEY_B, (("AV1", av1), ("AV3", av3)), results)
    order = ["AV0", "AV2", "AV2b", "AV1b", "AV1", "AV3"]
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_r4_abort_vote: {len(passed)}/{len(order)} rows passed (pass={passed} fail={failed}; AV1b-2 label "
          f"{AV1B2_LABEL}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
