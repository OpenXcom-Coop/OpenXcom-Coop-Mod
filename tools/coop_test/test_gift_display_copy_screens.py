"""Rows host_gives_craft_ok and host_gives_move of the gift display copy (helpers gift_display_helpers.py).

The other two write-backs of a co-op base view into "basehost": a craft's OK (CraftInfoState) and MOVE (the coop label of SACK;
SackSoldierState). On a build without the fix, pressed inside the visit on a received gift's display copy (it keeps the giver's id) they
write it into "basehost", so after the leave and the deferred replay the receiver keeps two copies, one sharing an id with its own
soldier. The rows check that the receiver keeps one copy. One fresh boot pair per row (SEPARATE gm1 tcp, key 49280, dirs
gift_copy_*_host / _client):
  host_gives_craft_ok  one guest staged first (GUESTNAME: the client's first own soldier not in a craft, transferred to the host base); the client
      visits the host base; the host gifts GIFTNAME; the client's notice OK, the craft button, craft row 0 (CraftInfoState), OK, OK on
      CraftsState, GEOSCAPE; its replay line; HOLD_L; the host's quick save with no visit open. Cells host_gives_craft_ok-pre, host_gives_craft_ok-guest, host_gives_craft_ok-live, host_gives_craft_ok-ids,
      host_gives_craft_ok-file, host_gives_craft_ok-common.
  host_gives_move as host_gives_craft_ok without the guest: SOLDIERS, GIFTNAME's row (SoldierInfoState), the SACK button (SackSoldierState naming GIFTNAME), OK
      (SoldiersState: SoldierInfoState pops itself on the empty list), OK, GEOSCAPE. Cells host_gives_move-pre, host_gives_move-live, host_gives_move-ids, host_gives_move-file,
      host_gives_move-common.
guest = GUESTNAME once on the client's own bases with coopBase = the host base's coop id after the leave (the craft's OK keeps a real
guest); live / ids / file / common as test_gift_display_copy.py.
FIX cells fail on a build without the fix: host_gives_craft_ok-live, host_gives_craft_ok-ids, host_gives_craft_ok-file, host_gives_move-live, host_gives_move-ids, host_gives_move-file (6 of 11).
Exit 0 only when every cell passes, else 2 (no SKIP). Run:
    python tools/coop_test/test_gift_display_copy_screens.py"""
import sys
from gift_display_helpers import *  # noqa: F401,F403 (gift_display_helpers and gift_helpers)

KEY = "49280"
PRE = ("each construction step met its precondition (boot, the guest (host_gives_craft_ok), picker, the visit, the baseline, the gift and the client's deferral line, "
       "the notice, the screen steps, the leave, the replay line, the host's save)")


def cells_craft_ok(rid, ev):
    hb = (ev.get("guest") or {}).get("hostBase") or [None, None]
    g = [s for s in (ev.get("live") or {}).get("recvIds") or [] if s[1] == GUESTNAME]
    return [(rid + "-guest", "GUARD", "%s once on the client's own bases with coopBase %s after the leave: %s" % (GUESTNAME, hb[1], g),
             len(g) == 1 and g[0][2] == hb[1])] + copy_cells(rid, ev, "client", False)


def cells_move(rid, ev):
    return copy_cells(rid, ev, "client", False)


def row_host_gives_craft_ok():
    return run_copy_row("host_gives_craft_ok", "gift_copy_craft", KEY, lambda x, ev: visit_gift(x, ev, lambda y, e, r: craft_ok(y, e, r, "EQUIP CRAFT"), guest=True),
                     ("pre", "guest", "live", "ids", "file", "common"), cells_craft_ok, PRE)


def row_host_gives_move():
    return run_copy_row("host_gives_move", "gift_copy_move", KEY, lambda x, ev: visit_gift(x, ev, lambda y, e, r: move_home(y, e, r, "MOVE")),
                     ("pre", "live", "ids", "file", "common"), cells_move, PRE)


if __name__ == "__main__":
    sys.exit(main("test_gift_display_copy_screens", [("host_gives_craft_ok", row_host_gives_craft_ok), ("host_gives_move", row_host_gives_move)]))
