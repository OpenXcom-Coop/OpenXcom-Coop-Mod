"""W2-H70 S-B rows R9, R10 (spec docs rewrite/prompts/w2h70_sb_display_copy.md (f); TASK 0 rewrite/w2h70-task0/sb/CONSTANTS.md; lead
L-TR9-1, F20420-F20425, F20573, F20581; ruling R-TR9-1; QH70B-2 and QH70B-8 (a); helpers gift_display_helpers.py, R-H70-2).

The other two write-backs of a co-op base view into "basehost": a craft's OK (CraftInfoState) and MOVE (the coop label of SACK;
SackSoldierState). Pressed inside the visit on a received gift's display copy (it keeps the giver's id) they write it into "basehost", so
after the leave and the deferred replay the receiver keeps two copies, one sharing an id with its own soldier. One fresh boot pair per row
(SEPARATE gm1 tcp, key 49280, dirs w2h70b_<row>_*):
  R9  one guest staged first (GUESTNAME: the client's first own soldier not in a craft, transferred to the host base, QH70B-8); the client
      visits the host base; the host gifts GIFTNAME; the client's notice OK, the craft button, craft row 0 (CraftInfoState), OK, OK on
      CraftsState, GEOSCAPE; its replay line; HOLD_L; the host's quick save with no visit open. Cells R9-pre, R9-guest, R9-live, R9-ids,
      R9-file, R9-common.
  R10 as R9 without the guest: SOLDIERS, GIFTNAME's row (SoldierInfoState), the SACK button (SackSoldierState naming GIFTNAME), OK
      (SoldiersState: SoldierInfoState pops itself on the empty list, F20581), OK, GEOSCAPE. Cells R10-pre, R10-live, R10-ids, R10-file,
      R10-common.
guest = GUESTNAME once on the client's own bases with coopBase = the host base's coop id after the leave (the craft's OK keeps a real
guest); live / ids / file / common as test_gift_display_copy.py.
Red (HEAD, TASK 0 boots a / b): R9-live, R9-ids, R9-file, R10-live, R10-ids, R10-file FAIL (6 of 11); green (EB1-EB7, boot c): 11 / 11.
Exit 0 only when every cell passes, else 2 (WV-D99 / WV-D100; no SKIP). one foreground run per invocation:
    python tools/coop_test/test_gift_display_copy_screens.py"""
import sys
from gift_display_helpers import *  # noqa: F401,F403 (HB, R-H70-2)

KEY = "49280"
PRE = ("each construction step met its precondition (boot, the guest (R9), picker, the visit, B, the gift and the client's deferral line, "
       "the notice, the screen steps, the leave, the replay line, the host's save)")


def cells_r9(rid, ev):
    hb = (ev.get("guest") or {}).get("hostBase") or [None, None]
    g = [s for s in (ev.get("live") or {}).get("recvIds") or [] if s[1] == GUESTNAME]
    return [(rid + "-guest", "GUARD", "%s once on the client's own bases with coopBase %s after the leave: %s" % (GUESTNAME, hb[1], g),
             len(g) == 1 and g[0][2] == hb[1])] + cells_b(rid, ev, "client", False)


def cells_r10(rid, ev):
    return cells_b(rid, ev, "client", False)


def row_r9():
    return run_row_b("R9", "w2h70b_r9", KEY, lambda x, ev: visit_gift(x, ev, lambda y, e, r: craft_ok(y, e, r, "EQUIP CRAFT"), guest=True),
                     ("pre", "guest", "live", "ids", "file", "common"), cells_r9, PRE)


def row_r10():
    return run_row_b("R10", "w2h70b_r10", KEY, lambda x, ev: visit_gift(x, ev, lambda y, e, r: move_home(y, e, r, "MOVE")),
                     ("pre", "live", "ids", "file", "common"), cells_r10, PRE)


if __name__ == "__main__":
    sys.exit(main("test_gift_display_copy_screens", [("R9", row_r9), ("R10", row_r10)]))
