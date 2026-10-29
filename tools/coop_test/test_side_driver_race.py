"""RV-U13 S-A red - test_side_driver_race.py: the four side-change drivers leave the change's NextTurnState
open. Pure Python: no game, no port, no lobby key.

Each row replays four interleavings against ONE shared side-change driver with two scripted fake machines
(`Fake`, the spec's Appendix C, copied verbatim below) and checks which NextTurnStates the driver left open.

Rows (each driver is called with timeout=5):
  SD1  repro_atom_side_begin.drive_side_change(host, client, 0, 5)
  SD2  test_turn_baton.drive_full_cycle(host, client, 4)
  SD3  test_end_turn_tally.drive_full_cycle(host, client, 4)
  SD4  repro_atom_side_transition.drive_full_cycle(host, client, 4, check_client_screen=False)
Cells per row (x = 1..4):
  SDx-ctrl   GUARD  both machines already on side 0 turn 5 with one NextTurnState each: the driver returns, no
                    exception; no NextTurnState left on either.
  SDx-race   FIX    both on side 1 turn 4, none open; each machine changes to side 0 turn 5 and pushes one
                    NextTurnState at its FIRST battle_state read (R5-U3 TASK 0 Ae): the driver returns; none left.
  SDx-stack  FIX    both on side 0 turn 5 with TWO NextTurnStates stacked (the Ae second cycle): returns; none left.
  SDx-held   GUARD  both on side 0 turn 5 with one NextTurnState that a close does not pop (the W2-P8b hold): the
                    driver returns inside its timeout, no exception; exactly that one left on each.
RED at A1 (the unchanged drivers): SD1..SD4 -race and -stack FAIL, each "left (1, 1)"; every -ctrl and -held
PASS. A driver exception (TimeoutError, an assertion) FAILs its cell with its text; the next cell runs.

The engine order the model rests on (F11354, TRACE, re-read at 84026129f):
  - the host changes side (BattlescapeGame.cpp :705), emits side_transition (:731) and pushes its NextTurnState
    (:800) inside ONE BattlescapeGame::endTurn call; a client changes side and pushes its NextTurnState in ONE
    side_transition apply (connectionTCP.cpp :24637-:24641);
  - TestServer serves a probe at the start of a frame (Engine/Game.cpp :177), so a probe never sees a side
    change without its screen; once both reads show the new side, every screen of that change is up.
A held turn screen: NextTurnState::close returns before its popState under the W2-P8b hold
(NextTurnState.cpp :536 / :538) and TestServer close_nextturn still answers ok.

Spec: docs repo rewrite/prompts/rvu13_harness_hardening.md, sections (d) Stage S-A and (f).
docs repo rewrite/rvu13-task0/sa/CONSTANTS.md (the model check, the Ae push / pop times).
run to completion in the foreground. ONE run per bar.
exit 0 only when every cell passes, else 2; no SKIP; every cell runs after a failure.

Run:  python tools/coop_test/test_side_driver_race.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repro_atom_side_begin as SB  # noqa: E402
import test_turn_baton as TB  # noqa: E402
import test_end_turn_tally as ET  # noqa: E402
import repro_atom_side_transition as ST  # noqa: E402

# ---- the spec's Appendix C (fake_model.py), verbatim: P, OLD / WANT / T0, Fake, CASES, LEFT_WANTED, DRIVERS ----
P = "class OpenXcom::"
OLD, WANT, T0 = 1, 0, 4          # old side (hostile), wanted side (FACTION_PLAYER), turn before the change


class Fake:
    """One machine: a state stack, a side / turn, and an optional flip at its FIRST battle_state read
    (side, turn, NextTurnStates pushed). held=True: close_nextturn answers ok but pops nothing (W2-P8b hold)."""

    def __init__(self, name, side, turn, nts, flip=None, held=False):
        self.name, self.side, self.turn, self.held = name, side, turn, held
        self.stack = ["GeoscapeState", "BattlescapeState"] + ["NextTurnState"] * nts
        self.flip = flip
        self.calls = []

    def cmd(self, req):
        c = req.get("cmd")
        self.calls.append(c)
        if c == "battle_state":
            if self.flip:
                self.side, self.turn = self.flip[0], self.flip[1]
                self.stack += ["NextTurnState"] * self.flip[2]
                self.flip = None
            return {"ok": True, "inBattle": True, "side": self.side, "turn": self.turn, "units": [], "selectedId": -1}
        if c == "list_widgets":
            return {"ok": True, "state": P + self.stack[-1], "widgets": []}
        if c == "get_state":
            return {"ok": True, "states": [P + s for s in self.stack]}
        if c == "close_nextturn":
            if self.stack[-1] == "NextTurnState":
                if not self.held:
                    self.stack.pop()
                return {"ok": True, "handled": "NextTurnState::close"}
            return {"error": "no NextTurnState on top"}
        raise AssertionError("unexpected cmd " + str(c))

    def ok(self, req):
        r = self.cmd(req)
        assert r.get("ok"), r
        return r


CASES = {
    # the ordinary case: the change already happened, one screen up on each machine
    "ctrl": lambda: (Fake("host", WANT, T0 + 1, 1), Fake("client", WANT, T0 + 1, 1)),
    # F11011 Ae: the change lands between the driver's close pass and its side read
    "race": lambda: (Fake("host", OLD, T0, 0, (WANT, T0 + 1, 1)), Fake("client", OLD, T0, 0, (WANT, T0 + 1, 1))),
    # the Ae second cycle: two screens stacked on each machine
    "stack": lambda: (Fake("host", WANT, T0 + 1, 2), Fake("client", WANT, T0 + 1, 2)),
    # a held turn screen: close answers ok, pops nothing
    "held": lambda: (Fake("host", WANT, T0 + 1, 1, held=True), Fake("client", WANT, T0 + 1, 1, held=True)),
}
LEFT_WANTED = {"ctrl": (0, 0), "race": (0, 0), "stack": (0, 0), "held": (1, 1)}
DRIVERS = {
    "SD1": lambda h, c: SB.drive_side_change(h, c, WANT, T0 + 1, timeout=5),
    "SD2": lambda h, c: TB.drive_full_cycle(h, c, T0, timeout=5),
    "SD3": lambda h, c: ET.drive_full_cycle(h, c, T0, timeout=5),
    "SD4": lambda h, c: ST.drive_full_cycle(h, c, T0, timeout=5, check_client_screen=False),
}
# ---- end of Appendix C ----

ROWS = {
    "SD1": "repro_atom_side_begin.drive_side_change",
    "SD2": "test_turn_baton.drive_full_cycle",
    "SD3": "test_end_turn_tally.drive_full_cycle",
    "SD4": "repro_atom_side_transition.drive_full_cycle (check_client_screen=False)",
}
KIND = {"ctrl": "GUARD", "race": "FIX", "stack": "FIX", "held": "GUARD"}


def run_cell(row, case):
    """One cell: fresh fakes, the driver once, then EVIDENCE and the PASS / FAIL line. Returns True on PASS."""
    host, client = CASES[case]()
    err = None
    t = time.time()
    try:
        DRIVERS[row](host, client)
    except Exception as e:  # a TimeoutError or an assertion inside the driver FAILs this cell only
        err = f"{type(e).__name__}: {e}"
    secs = time.time() - t
    left = (host.stack.count("NextTurnState"), client.stack.count("NextTurnState"))
    want = LEFT_WANTED[case]
    print(f"EVIDENCE {row}-{case}: {secs:.2f} s; host calls={host.calls} stack={host.stack}; "
          f"client calls={client.calls} stack={client.stack}; err={err}")
    if err is not None:
        print(f"{row}-{case} {KIND[case]}: FAIL driver raised {err[:300]}; left {left}, want {want}")
        return False
    if left != want:
        print(f"{row}-{case} {KIND[case]}: FAIL left {left}, want {want}")
        return False
    print(f"{row}-{case} {KIND[case]}: PASS left {left}")
    return True


def main():
    t0 = time.time()
    failed = []
    for row, label in ROWS.items():
        print(f"--- ROW {row}: {label}")
        row_failed = [f"{row}-{case}" for case in CASES if not run_cell(row, case)]
        failed += row_failed
        print(f"ROW {row}: {'PASS' if not row_failed else 'FAIL'} "
              f"({len(CASES) - len(row_failed)}/{len(CASES)} cells; failing: {', '.join(row_failed) or 'none'})")
    total = len(ROWS) * len(CASES)
    print(f"SUMMARY test_side_driver_race: {total - len(failed)}/{total} cells PASS; "
          f"failing: {', '.join(failed) or 'none'}; wall {time.time() - t0:.2f} s")
    sys.exit(0 if not failed else 2)


if __name__ == "__main__":
    main()
