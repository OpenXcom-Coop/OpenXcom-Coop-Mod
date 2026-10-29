"""test_fatal_vote_rejoin_answered.py: a voter who answered, then left and rejoined, is asked again. Staging, the
drop, the rejoin and the shared assertions: test_fatal_vote_rejoin.py (whose helpers this file runs), and through it
test_fatal_vote.py. This row has its own file to keep each file's wall short (the three rejoin rows ran 153.3 s
together on a build without the resend).

  answer_dropped_on_rejoin  HOST_SOLDIER + CLIENT_SOLDIER wounded; the vote opens with the host's own question and the
      client's. The client answers OK while the host's question is still unanswered (host answers {1: yes}, host top
      the question, client top the map); the client drops (dialog 62 over the host's question, the vote Open, {1: yes}
      kept); client2 rejoins; the host's RESUME. Expected: the host drops the rejoining seat's stored answer before
      the resend, so after the rejoin the host's answers are {} and client2's answered [] (resends 1); client2 shows
      the question (N 2); client2 OK (host answers {1: yes}), then the host's OK -> close end {0: yes, 1: yes} ->
      NextTurnState -> battle_end with test_battle_end's last_alien_down set over client2.

A build without the resend (one run, exit 2) passes every precondition (the open, the client's OK, the pause, dialog
68, RESUME, phase, battleId, hash). rejoin: host fatalVote resends 0 and answers {1: yes} (want {}); client2 no
question within 30 s of RESUME (host resends 0, client2 opensApplied 0, the vote still Open); client2 fatalVote at its
zeros. answer: client2 OK not pressed; the host's OK then decides end on the stale yes. close: host resends 0; client2
opensApplied 0, answerSent "", questionPushed 0. ending: runs and passes.

one run is the result; no skip path, one boot. The row prints ONE "EVIDENCE answer_dropped_on_rejoin:" line, then
"PASS answer_dropped_on_rejoin" / "FAIL answer_dropped_on_rejoin: <message>"; a rejoin step past its bound prints one
CAPTURE line and FAILs "rejoin (setup failure)". Exit 0 only when the row passes, 2 otherwise. run in the foreground to
completion.

Run:  python tools/coop_test/test_fatal_vote_rejoin_answered.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_fatal_vote as fvt
import test_fatal_vote_rejoin as rj

ROW_PORT = {"answer_dropped_on_rejoin": "48551"}   # the lobby key after test_fatal_vote_rejoin's 48550
LABEL = "fatal_vote_rejoin_answered"


def row_answer_dropped_on_rejoin(r):
    h, c = r.host, r.client
    census = fvt.vote_open(r, [fvt.HOST_SOLDIER, fvt.CLIENT_SOLDIER], [0, 1])
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
    rj.after_rejoin(r, t_res, [0, 1], 2, {}, [])   # the rejoining seat's earlier yes is dropped
    if fvt.answer(r, r.client, "OK", "answer"):
        fvt.wait_until(lambda: fvt.norm(fvt.fv(h)).get("answers") == {1: True}, fvt.STEP_S)
    if not fvt.answer(r, h, "OK", "answer"):
        r.ending = "the host's OK was not pressed"
    rj.close(r, True, "end", {0: True, 1: True},
             {"answerSent": "yes", "questionPushed": 1, "questionClosedByClose": 0}, "")
    fvt.ending(r, census, fvt.last_alien_down_verdict)


ROWS = (("answer_dropped_on_rejoin", row_answer_dropped_on_rejoin),)


def main():
    return rj.run_rows("test_fatal_vote_rejoin_answered", ROWS, ROW_PORT, LABEL)


if __name__ == "__main__":
    sys.exit(main())
