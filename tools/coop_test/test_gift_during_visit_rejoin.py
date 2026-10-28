"""W2-H70 (spec docs rewrite/prompts/w2h70_gift_during_visit.md (f); TASK 0 rewrite/w2h70-task0/sa/CONSTANTS.md; lead L-H64-2, ruling
R-H70-0; F19740-F19747, F19921): the rejoin and the save-prompt window rows beside test_gift_during_visit.py (R1-R3); both import
gift_helpers.py (R-H70-2). Rows (one fresh boot pair each, key "49256", dirs w2h70_<row>_host / _client, the rejoiner
w2h70_<row>_client2; real presses only):
  R4 (C3) the guest staged, the visit, the partner's gift inside, the host's notice OK, HOLD_P, the client killed and rejoined (the host's
     60 / 62, a fresh client join_tcp by B's clientName, the host's OK on Profile and RESUME): R4-rejoin HOLD_R after the rejoin.
  R5 (C1W) the client on SoldiersState when the host saves: its OK on the 67 clears insideCoopBase while it still views the host's base;
     the partner's gift then, the host's notice OK; QUICK within W_WRITE, else the host's CANCEL: R5-file, R5-reload (w2h70_r5r_*),
     R5-log (no new crash-folder file with the hash-map read error), R5-995 (the client's top dialog is not 995 "Save failed
     (MEMORY)") at the write + 2 s.
  R6 (C2W) as R5 to the 67's OK, the host's CANCEL, then the host's gift to the visitor (its "RECV deferred (no own base in current
     save)"), HOLD_P, the client killed and rejoined: R6-rejoin HOLD_R after the rejoin.
Cells: X-pre GUARD; R4-rejoin RED (once_host), R5-file RED (once in QUICK's host half, no client entry), R5-reload RED (once_host),
R5-log RED, R5-995 RED, R6-rejoin RED (once_client); X-common GUARD (both machines alive at the read, no new .dmp; R4 / R6: no hash-map
file). 12 cells; red (commit R1): RED exactly on R4-rejoin, R5-file, R5-reload, R5-log, R5-995, R6-rejoin. ONE EVIDENCE line per row,
one PASS / FAIL line per cell, the row verdict; every row runs; exit 0 only when every cell passes, else 2 (WV-D99 / WV-D100). WV-D95:
one foreground run per invocation.
Run: python tools/coop_test/test_gift_during_visit_rejoin.py
"""

import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gift_helpers import *  # noqa: E402,F401,F403 (the helpers, run_row, main; R-H70-2)
KEY = "49256"

def build_r4(x, ev):
    """R4 (C3): as R1 to the host's notice OK; HOLD_P; the client killed inside and rejoined; census HOLD_R after the rejoin"""
    stage_guest(x, ev)
    picker(x, ev)
    visit(x, ev)
    baseline(x, ev)
    partner_gift(x, ev)
    if ev["gift"]["insideAtKP2"] is not True or top(x.host) != "GeoscapeState":
        raise Stop("insideCoopBase not true at the KP2 or the host not on GeoscapeState: %s" % ev["gift"])
    time.sleep(HOLD_P)
    kill_rejoin(x, ev)
    ev["live"] = census(x)
    read_point(x, ev)

def build_r5(x, ev):
    """R5 (C1W): stage, picker, visit, the client's SOLDIERS, B, the 54 + the 67 over SoldiersState, the client's OK (insideCoopBase
    false), the partner's gift, the host's notice OK; QUICK written within W_WRITE, else the host's CANCEL; the read 2 s after the write"""
    stage_guest(x, ev)
    picker(x, ev)
    visit(x, ev)
    to_soldiers(x, ev)
    baseline(x, ev)
    trigger54(x, ev)
    ok67(x, ev)
    partner_gift(x, ev)
    if ev["gift"]["insideAtKP2"] is not False:
        raise Stop("insideCoopBase not false at the KP2: %s" % ev["gift"])
    v, s = written(x, W_WRITE)
    ev["deferred write"] = {"written s": s if v else None, "host": stack(x.host), "dlg": dlg(x.host)}
    if v:
        x.how = "deferred write"
    else:
        host_cancel(x, ev)
    time.sleep(2.0)
    read_point(x, ev)
    keep_file(x, ev)

def build_r6(x, ev):
    """R6 (C2W): picker, visit, the client's SOLDIERS, the 54 + the 67 over SoldiersState, the client's OK (insideCoopBase false), the
    host's CANCEL (QUICK written, GeoscapeState), B, the host's gift (deferral "no own base"), HOLD_P, kill + rejoin, census HOLD_R after"""
    picker(x, ev)
    visit(x, ev)
    to_soldiers(x, ev)
    trigger54(x, ev)
    ok67(x, ev)
    host_cancel(x, ev, "CANCEL before the gift")
    if top(x.host) != "GeoscapeState":
        raise Stop("the host not on GeoscapeState after its CANCEL: %s" % stack(x.host))
    baseline(x, ev)
    host_gift(x, ev, "[coop-gift] RECV deferred (no own base in current save)")
    time.sleep(HOLD_P)
    kill_rejoin(x, ev)
    ev["live"] = census(x)
    read_point(x, ev)

def cells_b(rid, ev):
    """R4-R6 cells after the read (R5: and the reload)"""
    rd, hv, rl, out = ev.get("read") or {}, ev.get("halves"), reloaded(ev), []
    if rid == "R5":
        out.append(("R5-file", "RED", "GIFTNAME once in QUICK's host half, in no client entry (red today: both, F19747)", bool(hv) and file_once_host(hv)))
        out.append(("R5-reload", "RED", "once_host after the reload (red today: DUP)", bool(rl) and once_host(rl)))
        out.append(("R5-log", "RED", "no new crash-folder file with \"Failed to read from hash map\" since B (red today: >= 1)",
                    (rd.get("crash") or {}).get("hashlogs") == 0))
        out.append(("R5-995", "RED", "the client's coop_dialog_info code != 995 at the read (red today: 995, F19921)",
                    (rd.get("clientDlg") or {}).get("code") != 995))
    else:
        f = once_host if rid == "R4" else once_client
        out.append((rid + "-rejoin", "RED", "%s HOLD_R after the rejoin (red today: %s)" % (f.__name__, "both, F19745" if rid == "R4" else "neither"),
                    f(ev["live"])))
    return out + [common(rid, rd)]

PRE_B = {"R4": "the guest staged, the visit, insideCoopBase true at the KP2, the notice OK, the kill, the host's 60 / 62, the rejoin",
         "R5": "the guest staged, the visit, SOLDIERS, the 54 + the 67 over SoldiersState, its OK (insideCoopBase false), the gift, the notice "
               "OK, QUICK written (W_WRITE, else the CANCEL)",
         "R6": "the visit, SOLDIERS, the 54 + 67, its OK (insideCoopBase false), the host's CANCEL wrote QUICK, the host's gift with the "
               "client's 'RECV deferred (no own base in current save)', the kill and the rejoin"}

def row_r4():
    return run_row("R4", "w2h70_r4", KEY, build_r4, ("pre", "rejoin", "common"), cells_b, PRE_B["R4"])

def row_r5():
    return run_row("R5", "w2h70_r5", KEY, build_r5, ("pre", "file", "reload", "log", "995", "common"), cells_b, PRE_B["R5"])

def row_r6():
    return run_row("R6", "w2h70_r6", KEY, build_r6, ("pre", "rejoin", "common"), cells_b, PRE_B["R6"])

if __name__ == "__main__":
    sys.exit(main("test_gift_during_visit_rejoin", (("R4", row_r4), ("R5", row_r5), ("R6", row_r6))))
