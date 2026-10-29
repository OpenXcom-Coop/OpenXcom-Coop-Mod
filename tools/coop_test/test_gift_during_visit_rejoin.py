"""A soldier gifted during a co-op base visit, the rejoin and save-prompt window rows beside test_gift_during_visit.py (rows
visitor_gives_cancel, visitor_gives_leave, host_gives_cancel); both import gift_helpers.py. Rows (one fresh boot pair each, key
"49256", dirs gift_visit_rejoin_*, gift_visit_window_*, gift_host_rejoin_* (host / client), the rejoiner <dir>_client2; real presses
only):
  visitor_gives_rejoin the guest staged, the visit, the partner's gift inside, the host's notice OK, HOLD_P, the client killed and rejoined (the host's
     60 / 62, a fresh client join_tcp by the baseline's clientName, the host's OK on Profile and RESUME): visitor_gives_rejoin-rejoin HOLD_R after the
     rejoin.
  visitor_gives_in_window the client on SoldiersState when the host saves: its OK on the 67 clears insideCoopBase while it still views the host's base;
     the partner's gift then, the host's notice OK; QUICK within W_WRITE, else the host's CANCEL: visitor_gives_in_window-file, visitor_gives_in_window-reload
     (gift_visit_windowr_*), visitor_gives_in_window-log (no new crash-folder file with the hash-map read error), visitor_gives_in_window-995 (the client's top dialog is not
     995 "Save failed (MEMORY)") at the write + 2 s.
  host_gives_rejoin as visitor_gives_in_window to the 67's OK, the host's CANCEL, then the host's gift to the visitor (its "RECV deferred (no own base in current
     save)"), HOLD_P, the client killed and rejoined: host_gives_rejoin-rejoin HOLD_R after the rejoin.
Cells: <row>-pre GUARD; visitor_gives_rejoin-rejoin FIX (once_host), visitor_gives_in_window-file FIX (once in QUICK's host half, no client entry), visitor_gives_in_window-reload FIX (once_host),
visitor_gives_in_window-log FIX, visitor_gives_in_window-995 FIX, host_gives_rejoin-rejoin FIX (once_client); <row>-common GUARD (both machines alive at the read, no new .dmp; visitor_gives_rejoin / host_gives_rejoin: no
hash-map file). 12 cells; on a build without the fix exactly the six FIX cells fail. ONE EVIDENCE line per row, one PASS / FAIL line
per cell, the row verdict; every row runs; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_gift_during_visit_rejoin.py
"""

import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gift_helpers import *  # noqa: E402,F401,F403 (the helpers, run_row, main)
KEY = "49256"

def build_visitor_gives_rejoin(x, ev):
    """visitor_gives_rejoin: as visitor_gives_cancel to the host's notice OK; HOLD_P; the client killed inside and rejoined; census HOLD_R after the rejoin"""
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

def build_visitor_gives_in_window(x, ev):
    """visitor_gives_in_window: stage, picker, visit, the client's SOLDIERS, the baseline, the 54 + the 67 over SoldiersState, the client's OK (insideCoopBase
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

def build_host_gives_rejoin(x, ev):
    """host_gives_rejoin: picker, visit, the client's SOLDIERS, the 54 + the 67 over SoldiersState, the client's OK (insideCoopBase false), the
    host's CANCEL (QUICK written, GeoscapeState), the baseline, the host's gift (deferral "no own base"), HOLD_P, kill + rejoin, census
    HOLD_R after"""
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

def cells_rejoin(rid, ev):
    """the cells of visitor_gives_rejoin, visitor_gives_in_window and host_gives_rejoin after the read (visitor_gives_in_window: and the reload)"""
    rd, hv, rl, out = ev.get("read") or {}, ev.get("halves"), reloaded(ev), []
    if rid == "visitor_gives_in_window":
        out.append(("visitor_gives_in_window-file", "FIX", "GIFTNAME once in QUICK's host half, in no client entry (without the fix: both)", bool(hv) and file_once_host(hv)))
        out.append(("visitor_gives_in_window-reload", "FIX", "once_host after the reload (without the fix: DUP)", bool(rl) and once_host(rl)))
        out.append(("visitor_gives_in_window-log", "FIX", "no new crash-folder file with \"Failed to read from hash map\" since the baseline (without the fix: >= 1)",
                    (rd.get("crash") or {}).get("hashlogs") == 0))
        out.append(("visitor_gives_in_window-995", "FIX", "the client's coop_dialog_info code != 995 at the read (without the fix: 995)",
                    (rd.get("clientDlg") or {}).get("code") != 995))
    else:
        f = once_host if rid == "visitor_gives_rejoin" else once_client
        out.append((rid + "-rejoin", "FIX", "%s HOLD_R after the rejoin (without the fix: %s)" % (f.__name__, "both" if rid == "visitor_gives_rejoin" else "neither"),
                    f(ev["live"])))
    return out + [common(rid, rd)]

PRE_REJOIN = {"visitor_gives_rejoin": "the guest staged, the visit, insideCoopBase true at the KP2, the notice OK, the kill, the host's 60 / 62, the rejoin",
         "visitor_gives_in_window": "the guest staged, the visit, SOLDIERS, the 54 + the 67 over SoldiersState, its OK (insideCoopBase false), the gift, the notice "
               "OK, QUICK written (W_WRITE, else the CANCEL)",
         "host_gives_rejoin": "the visit, SOLDIERS, the 54 + 67, its OK (insideCoopBase false), the host's CANCEL wrote QUICK, the host's gift with the "
               "client's 'RECV deferred (no own base in current save)', the kill and the rejoin"}

def row_visitor_gives_rejoin():
    return run_row("visitor_gives_rejoin", "gift_visit_rejoin", KEY, build_visitor_gives_rejoin, ("pre", "rejoin", "common"), cells_rejoin, PRE_REJOIN["visitor_gives_rejoin"])

def row_visitor_gives_in_window():
    return run_row("visitor_gives_in_window", "gift_visit_window", KEY, build_visitor_gives_in_window, ("pre", "file", "reload", "log", "995", "common"), cells_rejoin, PRE_REJOIN["visitor_gives_in_window"])

def row_host_gives_rejoin():
    return run_row("host_gives_rejoin", "gift_host_rejoin", KEY, build_host_gives_rejoin, ("pre", "rejoin", "common"), cells_rejoin, PRE_REJOIN["host_gives_rejoin"])

if __name__ == "__main__":
    sys.exit(main("test_gift_during_visit_rejoin", (("visitor_gives_rejoin", row_visitor_gives_rejoin), ("visitor_gives_in_window", row_visitor_gives_in_window), ("host_gives_rejoin", row_host_gives_rejoin))))
