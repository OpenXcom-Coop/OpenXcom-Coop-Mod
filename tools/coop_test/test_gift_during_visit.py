"""W2-H70 (spec docs rewrite/prompts/w2h70_gift_during_visit.md (f); TASK 0 rewrite/w2h70-task0/sa/CONSTANTS.md; lead L-H64-2,
ruling R-H70-0; F19740-F19747): in a SEPARATE co-op campaign the second player's own world is parked as "basehost" while it views the
host's base; a soldier it gives away there leaves only the view (both rosters keep it: DUP), a soldier the host gives it is only queued
(LOST on a CANCEL save). Rows (one fresh boot pair each, key "49255", dirs w2h70_<row>_*; new_campaign SEPARATE gm1 tcp; real presses):
  R1 (C1) guest staged, visit, the partner's gift (KP2) inside, the host's notice OK, the 54 + the client's 67, the host's CANCEL writes
     QUICK: R1-file (GIFTNAME once in QUICK's host half, in no coopClientSaves entry), R1-reload (once_host on a fresh pair, w2h70_r1r_*).
  R2 (C1 control) as R1 to the 67; the client leaves, the 54 writes QUICK: R2-live (once_host HOLD_L after the leave), R2-file, R2-reload.
  R3 (C2) the host gives the visitor its own soldier (renamed GIFTNAME), the 54 + 67, CANCEL: R3-file (once in one client entry, not in
     the host half), R3-reload (once_client).
X-pre / X-common GUARD (both alive at the read, no new .dmp, no hash-map crash file). 13 cells; red: RED exactly on R1-file, R1-reload,
R2-live, R2-file, R2-reload, R3-file, R3-reload. The helpers (copied from CAP rewrite/lh64-2-cap/cap.py and T64 rewrite/w2h64-task0/sa/
t0_h64a.py) live in gift_helpers.py, shared with test_gift_during_visit_rejoin.py. ONE EVIDENCE line per row, one
PASS / FAIL line per cell, the row verdict; every row runs; exit 0 only when every cell passes, else 2. one
foreground run per invocation.
Run: python tools/coop_test/test_gift_during_visit.py
"""

import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gift_helpers import *  # noqa: E402,F401,F403 (the helpers, run_row, main; R-H70-2)
KEY = "49255"

def settle_file():
    time.sleep(1.0)

def build_r1(x, ev, leave=False):
    """R1 (C1) / R2 (C1 control): stage, picker, visit, B, the partner's gift inside (insideCoopBase true at the KP2), the host's notice
    OK, the 54 + the client's 67; R1: the host's CANCEL writes QUICK; R2: the client leaves, the 54 writes QUICK by itself, census HOLD_L
    after the client's GeoscapeState"""
    stage_guest(x, ev)
    picker(x, ev)
    visit(x, ev)
    baseline(x, ev)
    partner_gift(x, ev)
    if ev["gift"]["insideAtKP2"] is not True or top(x.host) != "GeoscapeState":
        raise Stop("insideCoopBase not true at the KP2 or the host not on GeoscapeState: %s" % ev["gift"])
    trigger54(x, ev)
    if leave:
        tl = leave_base(x, ev)
        v, s = written(x, W_SAVE)
        ev["deferred write"] = {"written s": s if v else None, "host": stack(x.host)}
        if not v:
            raise Stop("no %s written within %.0f s of the leave" % (QUICK, W_SAVE))
        x.how = "deferred write"
        while time.time() - tl < HOLD_L:
            time.sleep(0.05)
        ev["live"] = census(x)
    else:
        host_cancel(x, ev)
    settle_file()
    read_point(x, ev)
    keep_file(x, ev)

def build_r3(x, ev):
    """R3 (C2): picker, visit, B, the host's gift to the visitor (its deferral line "viewing peer base"), the 54 + 67, the host's
    CANCEL writes QUICK"""
    picker(x, ev)
    visit(x, ev)
    baseline(x, ev)
    host_gift(x, ev, "[coop-gift] RECV deferred (viewing peer base)")
    trigger54(x, ev)
    host_cancel(x, ev)
    settle_file()
    read_point(x, ev)
    keep_file(x, ev)

def cells(rid, ev):
    """R1-R3 cells after the read and the reload: [(cell, kind, label, ok)]"""
    hv, rl, out = ev.get("halves"), reloaded(ev), []
    if rid == "R2":
        out.append(("R2-live", "FIX", "once_host HOLD_L after the leave (red today: the client's own base has it, owner 999, F19742)",
                    once_host(ev["live"])))
    if rid in ("R1", "R2"):
        out.append((rid + "-file", "FIX", "GIFTNAME once in QUICK's host half, in no client entry (red today: both, F19740)", bool(hv) and file_once_host(hv)))
        out.append((rid + "-reload", "FIX", "once_host after the reload (red today: DUP)", bool(rl) and once_host(rl)))
    else:
        out.append(("R3-file", "FIX", "GIFTNAME once in one client entry, not in the host half (red today: neither, F19743)", bool(hv) and file_once_client(hv)))
        out.append(("R3-reload", "FIX", "once_client after the reload (red today: neither)", bool(rl) and once_client(rl)))
    return out + [common(rid, ev.get("read") or {})]

PRE = {"R1": "the guest staged, the visit, insideCoopBase true at the KP2, the host's notice and its OK, the 54 (QUICK) + the client's 67, "
             "the host's CANCEL wrote QUICK within W_SAVE",
       "R2": "the guest staged, the visit, insideCoopBase true at the KP2, the host's notice and its OK, the 54 + the client's 67, the "
             "client's leave (GeoscapeState within W_LEAVE), the 54 wrote QUICK by itself within W_SAVE",
       "R3": "the visit, the host's gift with the client's 'RECV deferred (viewing peer base)' within W_NOTICE, the host back on "
             "GeoscapeState, the 54 + the client's 67, the host's CANCEL wrote QUICK within W_SAVE"}

def row_r1():
    return run_row("R1", "w2h70_r1", KEY, build_r1, ("pre", "file", "reload", "common"), cells, PRE["R1"])

def row_r2():
    return run_row("R2", "w2h70_r2", KEY, lambda x, ev: build_r1(x, ev, leave=True), ("pre", "live", "file", "reload", "common"), cells,
                   PRE["R2"])

def row_r3():
    return run_row("R3", "w2h70_r3", KEY, build_r3, ("pre", "file", "reload", "common"), cells, PRE["R3"])

if __name__ == "__main__":
    sys.exit(main("test_gift_during_visit", (("R1", row_r1), ("R2", row_r2), ("R3", row_r3))))
