"""W2-P7 S-V-B - test_w2_fatal_vote_rejoin.py: the fatal-wounds vote across a voter's drop and rejoin (owner D159;
no timeout, D186; the vote pauses everyone, D214 (a); SV-M9 as re-ruled by owner D223 (b)). Spec: docs
rewrite/prompts/w2p7_sv_fatal_vote_design.md 2.7 and section 4 (V7, V8) as re-pinned by rewrite/prompts/
w2p7_battle_end.md AMENDMENT P7-5 4.4 (P7-5 RULINGS Q9 (a), Q10 (a), Q11 (a); P7-5b SV-T1, SV-T4) and ### P7-7 (D223
(b), row V7b). Constants: docs rewrite/w2p7-sv-task0/CONSTANTS.md (T0-4). Bring-up, staging, kill, answers, Q11 and
the shared assertions: test_w2_fatal_vote.py, whose helpers this file runs. This file holds V7 and V8 and the rejoin
helpers; test_w2_fatal_vote_rejoin_answered.py holds V7b (split per SV-T1's pattern: the three rows ran 153.3 s solo
at red, each with its 30 s red window).

A voter client that drops mid-vote keeps the vote open (D186): the host's SPEC 16 dialog 62 (SAVE & QUIT / ABANDON
kept) goes over its question or CoopFatalVoteHold. A fresh process (client2) rejoins with the steps of
test_w2_rejoin_end_turn.stage_rejoin, copied bounded (drop_client_mid_battle, client2, rejoin_skirmish, dialog 68 hold,
host RESUME via coop_dialog_back). S-V-B.2's resend at onReady gives client2 the open ev; client2 shows vanilla's
question once the host's RESUME has taken dialog 68 away (P7-5 V3) and answers it. D223 (b): the rejoining seat's own
earlier answer is dropped (it is asked again); the answers of seats that did not leave stand.

| row | wounds | before the drop | after the rejoin | green (S-V-B.2) |
|---|---|---|---|---|
| V7 | WS1 | - (the client's question open) | client2 OK | host resends 1, answers {}; client2's question (answered []); close end -> battle_end |
| V8 | WS0+WS1 | host OK (host on CoopFatalVoteHold) | client2 CANCEL | the host's yes stands (host answers {0: yes}, client2 answered [0]); close continue; END TURN client2 then host -> battle_end, no second question; client2's H14 seed line exactly once |

Every row asserts: the open as test_w2_fatal_vote V1 / V3; the pause (host stack ends [the question or hold,
CoopState], dialog 62 with SAVE & QUIT and ABANDON, no RESUME; the vote Open with the answers given before the drop);
client2 held on dialog 68 with no question in its stack before RESUME (P7-5 V3, STOP-IF 12); after RESUME the host's
question or hold back on top (a hold shows the Wait line naming the client, busyOwnerSeat 1), phase Active on both,
peerAbsent false, battleId kept (FIXTURE-STOP steps), the stream settled, hash_now clean, desyncSeen false; both
fatalVote records after the rejoin (voteId kept, resends 1, client2 coverWaitPasses >= 1: the resent open waited under
dialog 68); the close (closeSeq > the host's lastSeqEmitted after the rejoin settled: the rejoin restarts the stream,
SV-T4); hostCovered.steps unchanged while the question/hold was up; the ending (test_w2_battle_end's E1 set over
client2, close seq < battle_end seq, evsAfter 0, one vote per battle).
W2-H14b (an END TURN clear + tally re-send at the rejoin) does not change any cell: no row reads a tally after the
rejoin except V8's wait for the host's "END TURN 1/2" after client2's own press.

RED (S-V-B.1 = the S-V-A.2 build with H12b; no resend exists; one run, exit 2). Every precondition passes (the open,
the pre-drop answer, the pause, dialog 68, RESUME, phase, battleId, hash). After RESUME client2 never shows the
question:
  V7  rejoin: host fatalVote resends 0 (want 1); client2 no question within 30 s (host resends 0, client2 opensApplied
      0, the vote still Open); client2 fatalVote at its zeros. answer: client2 OK not pressed. close: host fatalVote
      still Open (result "", answers {}, closeSeq 0, resends 0); client2 fatalVote (result "", opensApplied 0,
      closesApplied 0, answerSent "", questionPushed 0). ending: not run.
  V8  as V7 (the host's {0: yes} stands; client2 CANCEL not pressed); the seed line passes.

WV-D99 / WV-D100: one run is the result; no skip path, one boot per row. Each row prints ONE "EVIDENCE <id>:" line
before its verdict, "PASS <id>" / "FAIL <id>: <message>"; a rejoin step past its bound prints one CAPTURE line (every
machine's probes) and FAILs "rejoin (FIXTURE-STOP)". Exit 0 only when every row passes, 2 otherwise. WV-D95: run in the
foreground to completion.

Run:  python tools/coop_test/test_w2_fatal_vote_rejoin.py
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state
import test_w2_battle_end as tbe
import test_w2_fatal_vote as fvt
from test_skirmish_rejoin_battle import (drop_client_mid_battle, rejoin_skirmish, dialog, in_battle_save, has,
                                         COOP_DLG_WAIT_PLAYERS, COOP_DLG_CLIENT_RESUME_HOLD)

ROW_PORT = {"V7": "48549", "V8": "48550"}
LABEL = "w2p7_fatal_vote_rejoin"
DLG = "CoopState"
Q_S = 30           # client2's question after the host's RESUME (P7-5 4.4: the vote stays Open past 30 s at red)
REJOIN_S = 120     # each bounded rejoin step (test_w2_rejoin_end_turn.stage_rejoin's bounds)
LOG_FLUSH_S = 3    # the H14 seed line reaches client2's log (H14's LOG_FLUSH_S)
# client2 applies the rejoin's evs while still held on dialog 68 (its log: seqs 1-3 applied ~1.2 s before the host's
# RESUME press), so the resent open waits under the co-op dialog (P7-5 Q6 (b)) for at least one pump pass.
COVER_WAIT = ("ge", 1)
SEED_RE = re.compile(r"W2-H14: rejoin END TURN side-phase counter seeded to (-?\d+)")
DIALOG_KEYS = ("present", "code", "title", "backVisible", "backText", "saveQuitVisible", "abandonVisible")


class FixtureStop(Exception):
    pass


class RejoinRow(fvt.Row):
    """test_w2_fatal_vote.Row plus the dropped client, client2 and the stream base after the rejoin."""

    def __init__(self, rid, host, client, port):
        super().__init__(rid, host, client)
        self.port = port
        self.client0, self.client2 = client, None
        self.machines = [host, client]
        self.seq_rj = None


# ===================== the drop and the rejoin =====================


def capture(r, name, err):
    """FIXTURE-STOP: one CAPTURE line with every machine's probes (whole), then the row stops."""
    cap = {}
    for gc in r.machines:
        cap[gc.name] = {}
        for k, probe in (("event_state", event_state), ("battle_state", battle_state), ("dialog", dialog),
                         ("stack", fvt.stack)):
            try:
                cap[gc.name][k] = probe(gc)
            except Exception as e:
                cap[gc.name][k] = f"probe failed: {fvt.short(e)}"
    print(f"CAPTURE {r.rid} {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureStop(f"{name}: {err}")


def step(r, name, fn):
    try:
        return fn()
    except FixtureStop:
        raise
    except Exception as e:
        capture(r, name, fvt.short(e))


def leave(r, under, answers):
    """Step 1 (drop_client_mid_battle), then the pause (SV-M9 / design 2.7): dialog 62 over the host's question or
    hold, SAVE & QUIT and ABANDON kept, the vote Open with the answers given before the drop."""
    h = r.host
    r.ev["battleId0"] = (battle_state(h).get("authority") or {}).get("battleId")
    step(r, "1 drop_client_mid_battle", lambda: drop_client_mid_battle(h, r.client0))
    st, d, hv = fvt.stack(h), dialog(h), fvt.norm(fvt.fv(h))
    r.ev["pause"] = {"stack": st, "dialog": {k: d.get(k) for k in DIALOG_KEYS}, "fv": hv}
    m = []
    if st[-2:] != [under, DLG]:
        m.append(f"stack tail {st[-2:]} (want [{under}, {DLG}])")
    if (d.get("code"), d.get("saveQuitVisible"), d.get("abandonVisible"), d.get("backVisible")) != (
            COOP_DLG_WAIT_PLAYERS, True, True, False):
        m.append(f"dialog {d} (want code {COOP_DLG_WAIT_PLAYERS}, SAVE & QUIT and ABANDON shown, no RESUME)")
    m += fvt.mism(hv, {"state": "Open", "answers": answers, "result": ""})
    r.line("pause", "host after the drop", m)


def rejoin(r, under):
    """test_w2_rejoin_end_turn.stage_rejoin steps 3-8, copied bounded (step 7 waits for the tops RESUME leaves: the
    host's question or hold, client2 off dialog 68). Returns the time of the RESUME press."""
    h = r.host
    c2 = r.client2 = GameClient("client2", None, make_user_dir(f"w2p7_sv_rejoin_{r.rid.lower()}"))
    r.machines.append(c2)
    step(r, "3 client2 spawn and connect", lambda: (c2.spawn(), c2.connect()))
    step(r, "4 rejoin_skirmish", lambda: rejoin_skirmish(c2, r.port))

    def s5():
        c2.wait_for("client2 back in the battle", lambda: in_battle_save(c2) or None, timeout=240)
        c2.wait_for("client2 held on dialog 68 over BattlescapeState",
                    lambda: (has(c2, fvt.MAP) and dialog(c2).get("code") == COOP_DLG_CLIENT_RESUME_HOLD) or None,
                    timeout=60, interval=0.5)

    def s6():
        def offered():
            if session.has_state(h, "Profile"):        # the join's popup sits over the dialog
                return h.cmd({"cmd": "profile_ok"}) and None
            return dialog(h).get("backVisible") or None
        h.wait_for("host dialog offers RESUME", offered, timeout=REJOIN_S, interval=0.5)
        d = dialog(h)
        assert d.get("code") == COOP_DLG_WAIT_PLAYERS and d.get("backText") == "RESUME", f"host dialog {d}"

    def s7():
        h.wait_for(f"host top {under}", lambda: (fvt.top(h) == under) or None, timeout=REJOIN_S, interval=0.25)
        c2.wait_for("client2 off dialog 68", lambda: (fvt.top(c2) in (fvt.MAP, fvt.QUESTION)) or None,
                    timeout=REJOIN_S, interval=0.25)

    def s8():
        for gc in (h, c2):
            gc.wait_for(f"{gc.name} phase Active", lambda gc=gc: (battle_state(gc).get("phase") == "Active") or None,
                        timeout=REJOIN_S, interval=0.5)
        ha, ca = (battle_state(gc).get("authority") or {} for gc in (h, c2))
        assert ha.get("peerAbsent") is False, f"host peerAbsent: {ha}"
        assert ha.get("battleId") == ca.get("battleId") == r.ev["battleId0"], (
            f"battleId before={r.ev['battleId0']} host={ha.get('battleId')} client2={ca.get('battleId')}")

    step(r, "5 client2 in the battle, held on dialog 68", s5)
    step(r, "6 host offers RESUME", s6)
    st2 = fvt.stack(c2)
    r.ev["beforeResume"] = {"client2Stack": st2, "client2Dialog": dialog(c2).get("code"), "hostStack": fvt.stack(h),
                            "client2Fv": fvt.norm(fvt.fv(c2))}
    if st2[-1:] != [DLG] or fvt.QUESTION in st2:
        r.fail("rejoin", f"client2 stack {st2} before RESUME (want dialog 68 on top and no question: P7-5 V3)")
    h.ok({"cmd": "coop_dialog_back"})
    t_res = time.time()
    step(r, "7 RESUME: the host's question/hold back on top, client2 off dialog 68", s7)
    step(r, "8 phase Active on both, peerAbsent false, battleId unchanged", s8)
    r.client = c2
    return t_res


def after_rejoin(r, t_res, voters, n, host_answers, answered):
    """The vote after the rejoin: the stream settled and hash-clean, client2's question within Q_S of RESUME, both
    fatalVote records (D223 (b): host_answers / answered exclude the rejoining seat's earlier answer)."""
    h, c2 = r.host, r.client
    fvt.settle(r, "rejoin")
    r.seq_rj = event_state(h).get("lastSeqEmitted")
    fvt.hash_clean(r, "rejoin", "after the rejoin")
    ok, _ = fvt.wait_until(lambda: fvt.top(c2) == fvt.QUESTION, max(0.0, Q_S - (time.time() - t_res)), 0.25)
    secs = round(time.time() - t_res, 1)
    hs, cs = fvt.snap(h), fvt.snap(c2)
    r.ev["rejoin"] = {"questionUp": ok, "secsFromResume": secs, "seqAfterRejoin": r.seq_rj, "host": hs, "client2": cs}
    vote_id = (((r.ev.get("open") or {}).get("host") or {}).get("fv") or {}).get("voteId")
    want_h = fvt.QUESTION if 0 in voters and 0 not in host_answers else fvt.HOLD
    hm = []
    if hs["top"] != want_h:
        hm.append(f"top {hs['top']} (want {want_h})")
    if want_h == fvt.HOLD and (hs["wait"] != fvt.TEXT_WAIT_CLIENT or hs["busyOwnerSeat"] != 1):
        hm.append(f"Wait line {hs['wait']!r} busyOwnerSeat {hs['busyOwnerSeat']} (want {fvt.TEXT_WAIT_CLIENT!r}, 1)")
    if hs["stack"].count(fvt.QUESTION) + hs["stack"].count(fvt.HOLD) != 1 or DLG in hs["stack"]:
        hm.append(f"stack {hs['stack']} (want one question or hold and no co-op dialog)")
    r.line("rejoin", "host after RESUME", hm)
    hv = hs["fv"]
    r.line("rejoin", "host fatalVote after the rejoin", fvt.mism(hv, {
        "state": "Open", "voteId": vote_id, "armed": 1, "opened": 1, "voters": voters, "wounded": n,
        "answers": host_answers, "result": "", "closeSeq": 0, "heldIntents": 0, "answersDropped": 0, "resends": 1}))
    if not ok:
        r.fail("rejoin", f"client2 never showed the question within {Q_S}s of RESUME: top {cs['top']}, host resends "
                         f"{hv.get('resends')}, client2 opensApplied {cs['fv'].get('opensApplied')}, host "
                         f"fatalVote.state {hv.get('state')!r} after {secs}s")
    elif cs["texts"] != fvt.question_texts(n):
        r.fail("rejoin", f"client2 question texts {cs['texts']} (want {fvt.question_texts(n)})")
    r.line("rejoin", "client2 fatalVote after the rejoin", fvt.mism(cs["fv"], {
        "state": "Open", "voteId": vote_id, "voters": voters, "wounded": n, "answered": answered, "opensApplied": 1,
        "closesApplied": 0, "questionPushed": 1, "questionPushedMs": ("gt", 0), "answerSent": "",
        "questionClosedByClose": 0, "coverWaitPasses": COVER_WAIT}))
    for name, s in (("host", hs), ("client2", cs)):
        if s["desyncSeen"] is not False:
            r.fail("rejoin", f"{name} desyncSeen={s['desyncSeen']} (want false)")


def close(r, pressed, result, answers, client_want, why):
    """test_w2_fatal_vote.check_close with the rejoin's relation (closeSeq > the stream base after the rejoin) and
    resends 1. Nothing answered = no close to wait for: the records are read at once (the vote still Open)."""
    if not pressed:
        r.ending = r.ending or why
        r.opened = False
    fvt.check_close(r, result, answers, dict({"coverWaitPasses": COVER_WAIT}, **client_want),
                    {"closeSeq": ("gt", r.seq_rj or 0), "resends": 1})


def seed_once(r):
    """Q9 (a): client2's H14 seed line exactly once."""
    t0, lines = time.time(), []
    while True:
        try:
            with open(os.path.join(r.client2.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
                lines = [int(m.group(1)) for m in (SEED_RE.search(ln) for ln in f) if m]
        except OSError:
            lines = []
        if lines or time.time() - t0 >= LOG_FLUSH_S:
            break
        time.sleep(0.5)
    r.ev["client2Seeded"] = lines
    if len(lines) != 1:
        r.fail("seed", f"client2's H14 seed lines {lines} (want exactly one)")


# ===================== the rows =====================


def row_v7(r):
    census = fvt.vote_open(r, [fvt.WS1], [1])
    leave(r, fvt.HOLD, {})
    t_res = rejoin(r, fvt.HOLD)
    after_rejoin(r, t_res, [1], 1, {}, [])
    pressed = fvt.answer(r, r.client, "OK", "answer")
    close(r, pressed, "end", {1: True}, {"answerSent": "yes", "questionPushed": 1, "questionClosedByClose": 0},
          "client2's OK was not pressed")
    fvt.ending(r, census, fvt.e1_verdict)


def row_v8(r):
    census = fvt.vote_open(r, [fvt.WS0, fvt.WS1], [0, 1])
    fvt.answer(r, r.host, "OK", "answer")
    fvt.check_hold(r, {0: True})
    leave(r, fvt.HOLD, {0: True})
    t_res = rejoin(r, fvt.HOLD)
    after_rejoin(r, t_res, [0, 1], 2, {0: True}, [0])
    pressed = fvt.answer(r, r.client, "CANCEL", "answer")
    close(r, pressed, "continue", {0: True, 1: False},
          {"answerSent": "no", "questionPushed": 1, "questionClosedByClose": 0}, "client2's CANCEL was not pressed")
    if not r.ending:
        fvt.end_turns(r)
    fvt.ending(r, census, fvt.e1_verdict)
    seed_once(r)


# ===================== runner =====================


def run_row(rid, row_fn, results, port, label):
    host = GameClient("host", None, make_user_dir(f"{label}_{rid}_host"))
    client = GameClient("client", None, make_user_dir(f"{label}_{rid}_client"))
    r = RejoinRow(rid, host, client, port)
    try:
        try:
            tbe.boot(host, client, port)
        except Exception as e:
            results[rid] = False
            print(f"FAIL {rid}: pre (bring-up) {fvt.short(e)}", flush=True)
            return
        r.ev["bootS"] = round(time.time() - r.t0, 1)
        try:
            row_fn(r)
        except FixtureStop as e:
            r.fail("rejoin (FIXTURE-STOP)", str(e))
        except Exception as e:
            r.fail("exception", fvt.short(e))
        r.ev["wallS"] = round(time.time() - r.t0, 1)
        print(f"EVIDENCE {rid}: {r.ev}", flush=True)
        results[rid] = not r.fails
        print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} failure(s): " + " | ".join(r.fails),
              flush=True)
    finally:
        for gc in r.machines:
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p7-svb] shutdown {gc.name}: {fvt.short(e)}", flush=True)


def run_rows(name, rows, ports, label):
    t0, results = time.time(), {}
    for rid, row_fn in rows:
        run_row(rid, row_fn, results, ports[rid], label)
    order = [x[0] for x in rows]
    passed, failed = [n for n in order if results.get(n)], [n for n in order if not results.get(n)]
    print(f"\n{name}: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in {time.time() - t0:.1f}s",
          flush=True)
    return 0 if not failed else 2


ROWS = (("V7", row_v7), ("V8", row_v8))


def main():
    return run_rows("test_w2_fatal_vote_rejoin", ROWS, ROW_PORT, LABEL)


if __name__ == "__main__":
    sys.exit(main())
