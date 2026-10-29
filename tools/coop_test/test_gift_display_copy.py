"""W2-H70 S-B rows R7, R8, G7 (spec docs rewrite/prompts/w2h70_sb_display_copy.md (f); TASK 0 rewrite/w2h70-task0/sb/CONSTANTS.md;
lead L-TR9-1, F20420-F20425; ruling R-TR9-1; QH70B-1 .. QH70B-8 (a); helpers gift_display_helpers.py, R-H70-2).

In a SEPARATE co-op campaign a soldier gifted to a player who is viewing the giver's base is queued, and the visit deferral adds a
display-only copy to the view that keeps the GIVER's soldier id. SOLDIERS OK inside the visit writes that copy into "basehost" (the
receiver's parked own world); the leave restores "basehost" and the deferred replay adds the soldier again under a new id, so the receiver
keeps two copies, one sharing an id with its own soldier, through a save and a reload. One fresh boot pair per row
(SEPARATE gm1 tcp, key 49279, dirs w2h70b_<row>_*, reloads w2h70b_<row>r_*):
  R7  the client visits the host base; the host gifts its first own soldier not in a craft (renamed GIFTNAME) to it; the client's
      GiftNoticeState OK, SOLDIERS (GIFTNAME listed), OK, GEOSCAPE; its replay line; HOLD_L; the host's quick save with no visit open; a
      fresh pair reloads that file. Cells R7-pre, R7-live, R7-ids, R7-file, R7-reload, R7-common.
  R8  the host visits the client base; the client gifts its first own soldier not in a craft; the host's notice OK, SOLDIERS, OK,
      GEOSCAPE; its replay line; the same save and reload. Cells R8-pre, R8-live, R8-ids, R8-file, R8-reload, R8-common.
  G7  as R7 without SOLDIERS (the control C1-ctl, F20423). Cells G7-pre, G7-live, G7-ids, G7-file, G7-common.
live = GIFTNAME once on the receiver's own bases and on no base of the other machine; ids = no id held twice on the receiver's own bases;
file = the quick save's receiver half holds GIFTNAME once and no id twice, the other half none; reload = live and ids again
after the reload; common = both machines alive at the read, no new .dmp since B.
Red (HEAD, TASK 0 boots a / b): R7-live, R7-ids, R7-file, R7-reload, R8-live, R8-ids, R8-file, R8-reload FAIL (8 of 17); green (EB1-EB7,
boot c): 17 / 17. Exit 0 only when every cell passes, else 2 (WV-D99 / WV-D100; no SKIP). one foreground run per invocation:
    python tools/coop_test/test_gift_display_copy.py"""
import sys
from gift_display_helpers import *  # noqa: F401,F403 (HB, R-H70-2)

KEY = "49279"
PRE = ("each construction step met its precondition (boot, picker, the visit, B, the gift and the receiver's deferral line, the notice, "
       "the screen steps, the leave, the replay line, the host's save)")


def cells_client(rid, ev):
    return cells_b(rid, ev, "client", rid == "R7", "GUARD" if rid == "G7" else "FIX")


def cells_host(rid, ev):
    return cells_b(rid, ev, "host", True)


def row_r7():
    return run_row_b("R7", "w2h70b_r7", KEY, lambda x, ev: visit_gift(x, ev, list_ok), ("pre", "live", "ids", "file", "reload", "common"),
                     cells_client, PRE, reloads=True)


def row_r8():
    return run_row_b("R8", "w2h70b_r8", KEY, lambda x, ev: host_visit_gift(x, ev, list_ok), ("pre", "live", "ids", "file", "reload", "common"),
                     cells_host, PRE, reloads=True)


def row_g7():
    return run_row_b("G7", "w2h70b_g7", KEY, lambda x, ev: visit_gift(x, ev, no_screen), ("pre", "live", "ids", "file", "common"),
                     cells_client, PRE)


if __name__ == "__main__":
    sys.exit(main("test_gift_display_copy", [("R7", row_r7), ("R8", row_r8), ("G7", row_g7)]))
