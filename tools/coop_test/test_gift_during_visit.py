"""A soldier gifted during a co-op base visit: in a SEPARATE co-op campaign the second player's own world is parked as "basehost"
while it views the host's base. On a build without the fix, a soldier it gives away there leaves only the view (both rosters keep it:
DUP), and a soldier the host gives it is only queued (LOST on a CANCEL save). Rows (one fresh boot pair each, key "49255", dirs
gift_visit_cancel_*, gift_visit_leave_*,
gift_host_cancel_*; new_campaign SEPARATE gm1 tcp; real presses):
  visitor_gives_cancel guest staged, visit, the partner's gift (KP2) inside, the host's notice OK, the 54 + the client's 67, the host's CANCEL writes
     QUICK: visitor_gives_cancel-file (GIFTNAME once in QUICK's host half, in no coopClientSaves entry), visitor_gives_cancel-reload (once_host on a fresh pair, gift_visit_cancelr_*).
  visitor_gives_leave (control) as visitor_gives_cancel to the 67; the client leaves, the 54 writes QUICK: visitor_gives_leave-live (once_host HOLD_L after the leave), visitor_gives_leave-file, visitor_gives_leave-reload.
  host_gives_cancel the host gives the visitor its own soldier (renamed GIFTNAME), the 54 + 67, CANCEL: host_gives_cancel-file (once in one client entry, not in
     the host half), host_gives_cancel-reload (once_client).
<row>-pre / <row>-common GUARD (both alive at the read, no new .dmp, no hash-map crash file). 13 cells; on a build without the fix
exactly visitor_gives_cancel-file, visitor_gives_cancel-reload, visitor_gives_leave-live, visitor_gives_leave-file, visitor_gives_leave-reload, host_gives_cancel-file and host_gives_cancel-reload fail. The helpers live in gift_helpers.py, shared with
test_gift_during_visit_rejoin.py. ONE EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; every row runs; exit 0
only when every cell passes, else 2.
Run: python tools/coop_test/test_gift_during_visit.py
"""

import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gift_helpers import *  # noqa: E402,F401,F403 (the helpers, run_row, main)
KEY = "49255"

def settle_file():
    time.sleep(1.0)

def build_visitor_gives(x, ev, leave=False):
    """visitor_gives_cancel / visitor_gives_leave (control): stage, picker, visit, the baseline, the partner's gift inside (insideCoopBase true at the KP2), the host's notice
    OK, the 54 + the client's 67; visitor_gives_cancel: the host's CANCEL writes QUICK; visitor_gives_leave: the client leaves, the 54 writes QUICK by itself, census HOLD_L
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

def build_host_gives_cancel(x, ev):
    """host_gives_cancel: picker, visit, the baseline, the host's gift to the visitor (its deferral line "viewing peer base"), the 54 + 67, the host's
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
    """the cells of visitor_gives_cancel, visitor_gives_leave and host_gives_cancel after the read and the reload: [(cell, kind, label, ok)]"""
    hv, rl, out = ev.get("halves"), reloaded(ev), []
    if rid == "visitor_gives_leave":
        out.append(("visitor_gives_leave-live", "FIX", "once_host HOLD_L after the leave (without the fix: the client's own base has it, owner 999)",
                    once_host(ev["live"])))
    if rid in ("visitor_gives_cancel", "visitor_gives_leave"):
        out.append((rid + "-file", "FIX", "GIFTNAME once in QUICK's host half, in no client entry (without the fix: both)", bool(hv) and file_once_host(hv)))
        out.append((rid + "-reload", "FIX", "once_host after the reload (without the fix: DUP)", bool(rl) and once_host(rl)))
    else:
        out.append(("host_gives_cancel-file", "FIX", "GIFTNAME once in one client entry, not in the host half (without the fix: neither)", bool(hv) and file_once_client(hv)))
        out.append(("host_gives_cancel-reload", "FIX", "once_client after the reload (without the fix: neither)", bool(rl) and once_client(rl)))
    return out + [common(rid, ev.get("read") or {})]

PRE = {"visitor_gives_cancel": "the guest staged, the visit, insideCoopBase true at the KP2, the host's notice and its OK, the 54 (QUICK) + the client's 67, "
             "the host's CANCEL wrote QUICK within W_SAVE",
       "visitor_gives_leave": "the guest staged, the visit, insideCoopBase true at the KP2, the host's notice and its OK, the 54 + the client's 67, the "
             "client's leave (GeoscapeState within W_LEAVE), the 54 wrote QUICK by itself within W_SAVE",
       "host_gives_cancel": "the visit, the host's gift with the client's 'RECV deferred (viewing peer base)' within W_NOTICE, the host back on "
             "GeoscapeState, the 54 + the client's 67, the host's CANCEL wrote QUICK within W_SAVE"}

def row_visitor_gives_cancel():
    return run_row("visitor_gives_cancel", "gift_visit_cancel", KEY, build_visitor_gives, ("pre", "file", "reload", "common"), cells, PRE["visitor_gives_cancel"])

def row_visitor_gives_leave():
    return run_row("visitor_gives_leave", "gift_visit_leave", KEY, lambda x, ev: build_visitor_gives(x, ev, leave=True), ("pre", "live", "file", "reload", "common"), cells,
                   PRE["visitor_gives_leave"])

def row_host_gives_cancel():
    return run_row("host_gives_cancel", "gift_host_cancel", KEY, build_host_gives_cancel, ("pre", "file", "reload", "common"), cells, PRE["host_gives_cancel"])

if __name__ == "__main__":
    sys.exit(main("test_gift_during_visit", (("visitor_gives_cancel", row_visitor_gives_cancel), ("visitor_gives_leave", row_visitor_gives_leave), ("host_gives_cancel", row_host_gives_cancel))))
