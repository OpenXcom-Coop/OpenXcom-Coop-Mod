"""W2-P7 S-V-B - test_w2_fatal_vote_rejoin_answered.py: a voter who answered, then left and rejoined, is asked again
(owner D223 (b), docs rewrite/prompts/w2p7_battle_end.md ### P7-7, row V7b). Spec, staging, the drop, the rejoin and
the shared assertions: test_w2_fatal_vote_rejoin.py (whose helpers this file runs), and through it
test_w2_fatal_vote.py. The split from test_w2_fatal_vote_rejoin.py is SV-T1's pattern (P7-7: the file stays <= 150 s
solo; V7, V8 and V7b together ran 153.3 s at red).

  V7b WS0 + WS1 wounded; the vote opens with the host's own question and the client's. The client answers OK while
      the host's question is still unanswered (host answers {1: yes}, host top the question, client top the map); the
      client drops (dialog 62 over the host's question, the vote Open, {1: yes} kept); client2 rejoins; the host's
      RESUME. Green (S-V-B.2 + D223 (b)): the host drops the rejoining seat's stored answer before the resend, so
      after the rejoin the host's answers are {} and client2's answered [] (resends 1); client2 shows the question
      (N 2); client2 OK (host answers {1: yes}), then the host's OK -> close end {0: yes, 1: yes} -> NextTurnState ->
      battle_end with test_w2_battle_end's E1 set over client2.

RED (S-V-B.1 = the S-V-A.2 build with H12b; no resend exists; one run, exit 2). Every precondition passes (the open,
the client's OK, the pause, dialog 68, RESUME, phase, battleId, hash). rejoin: host fatalVote resends 0 and answers
{1: yes} (want {}); client2 no question within 30 s of RESUME (host resends 0, client2 opensApplied 0, the vote still
Open); client2 fatalVote at its zeros. answer: client2 OK not pressed; the host's OK then decides end on the stale yes.
close: host resends 0; client2 opensApplied 0, answerSent "", questionPushed 0. ending: runs and passes.

WV-D99 / WV-D100: one run is the result; no skip path, one boot. The row prints ONE "EVIDENCE V7b:" line, then
"PASS V7b" / "FAIL V7b: <message>"; a rejoin step past its bound prints one CAPTURE line and FAILs "rejoin
(FIXTURE-STOP)". Exit 0 only when the row passes, 2 otherwise. WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_fatal_vote_rejoin_answered.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_w2_fatal_vote as fvt
import test_w2_fatal_vote_rejoin as rj

ROW_PORT = {"V7b": "48551"}   # the next unused lobby key after 48550 (0 matches in the tree and REGRESSION-BATCHES.md)
LABEL = "w2p7_fatal_vote_rejoin_answered"


def row_v7b(r):
    h, c = r.host, r.client
    census = fvt.vote_open(r, [fvt.WS0, fvt.WS1], [0, 1])
    fvt.answer(r, c, "OK", "answer")   # the client's yes while the host's own question is unanswered
    fvt.wait_until(lambda: fvt.norm(fvt.fv(h)).get("answers") == {1: True} and fvt.top(c) == fvt.MAP, fvt.STEP_S)
    hs, cs = fvt.snap(h), fvt.snap(c)
    r.ev["clientYes"] = {"host": hs, "client": cs}
    if hs["top"] != fvt.QUESTION or cs["top"] != fvt.MAP:
        r.fail("answer", f"tops after the client's OK host {hs['top']} client {cs['top']} (want {fvt.QUESTION}, "
                         f"{fvt.MAP})")
    r.line("answer", "host fatalVote after the client's OK", fvt.mism(hs["fv"], {"state": "Open", "answers": {1: True},
                                                                               "result": ""}))
    r.line("answer", "client fatalVote after its OK", fvt.mism(cs["fv"], {"state": "Open", "answerSent": "yes"}))
    rj.leave(r, fvt.QUESTION, {1: True})
    t_res = rj.rejoin(r, fvt.QUESTION)
    rj.after_rejoin(r, t_res, [0, 1], 2, {}, [])   # D223 (b): the rejoining seat's earlier yes is dropped
    if fvt.answer(r, r.client, "OK", "answer"):
        fvt.wait_until(lambda: fvt.norm(fvt.fv(h)).get("answers") == {1: True}, fvt.STEP_S)
    if not fvt.answer(r, h, "OK", "answer"):
        r.ending = "the host's OK was not pressed"
    rj.close(r, True, "end", {0: True, 1: True},
             {"answerSent": "yes", "questionPushed": 1, "questionClosedByClose": 0}, "")
    fvt.ending(r, census, fvt.e1_verdict)


ROWS = (("V7b", row_v7b),)


def main():
    return rj.run_rows("test_w2_fatal_vote_rejoin_answered", ROWS, ROW_PORT, LABEL)


if __name__ == "__main__":
    sys.exit(main())
