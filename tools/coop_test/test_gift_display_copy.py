"""Rows host_gives_list, host_visits_list and host_gives_no_screen of the gift display copy (helpers gift_display_helpers.py).

In a SEPARATE co-op campaign a soldier gifted to a player who is viewing the giver's base is queued, and the visit deferral adds a
display-only copy to the view that keeps the GIVER's soldier id. On a build without the fix, SOLDIERS OK inside the visit writes that
copy into "basehost" (the receiver's parked own world); the leave restores "basehost" and the deferred replay adds the soldier again
under a new id, so the receiver keeps two copies, one sharing an id with its own soldier, through a save and a reload. The rows check
that the receiver keeps one copy. One fresh boot pair per row (SEPARATE gm1 tcp, key 49279, dirs gift_copy_*_host / _client, reloads
gift_copy_*r_*):
  host_gives_list  the client visits the host base; the host gifts its first own soldier not in a craft (renamed GIFTNAME) to it; the client's
      GiftNoticeState OK, SOLDIERS (GIFTNAME listed), OK, GEOSCAPE; its replay line; HOLD_L; the host's quick save with no visit open; a
      fresh pair reloads that file. Cells host_gives_list-pre, host_gives_list-live, host_gives_list-ids, host_gives_list-file, host_gives_list-reload, host_gives_list-common.
  host_visits_list  the host visits the client base; the client gifts its first own soldier not in a craft; the host's notice OK, SOLDIERS, OK,
      GEOSCAPE; its replay line; the same save and reload. Cells host_visits_list-pre, host_visits_list-live, host_visits_list-ids, host_visits_list-file, host_visits_list-reload, host_visits_list-common.
  host_gives_no_screen  as host_gives_list without SOLDIERS (the control). Cells host_gives_no_screen-pre, host_gives_no_screen-live, host_gives_no_screen-ids, host_gives_no_screen-file, host_gives_no_screen-common.
live = GIFTNAME once on the receiver's own bases and on no base of the other machine; ids = no id held twice on the receiver's own bases;
file = the quick save's receiver half holds GIFTNAME once and no id twice, the other half none; reload = live and ids again
after the reload; common = both machines alive at the read, no new .dmp since the baseline (just before the gift).
FIX cells fail on a build without the fix: host_gives_list-live, host_gives_list-ids, host_gives_list-file, host_gives_list-reload, host_visits_list-live, host_visits_list-ids, host_visits_list-file, host_visits_list-reload (8 of 17).
Exit 0 only when every cell passes, else 2 (no SKIP). Run:
    python tools/coop_test/test_gift_display_copy.py"""
import sys
from gift_display_helpers import *  # noqa: F401,F403 (gift_display_helpers and gift_helpers)

KEY = "49279"
PRE = ("each construction step met its precondition (boot, picker, the visit, the baseline, the gift and the receiver's deferral line, the notice, "
       "the screen steps, the leave, the replay line, the host's save)")


def cells_client(rid, ev):
    return copy_cells(rid, ev, "client", rid == "host_gives_list", "GUARD" if rid == "host_gives_no_screen" else "FIX")


def cells_host(rid, ev):
    return copy_cells(rid, ev, "host", True)


def row_host_gives_list():
    return run_copy_row("host_gives_list", "gift_copy_list", KEY, lambda x, ev: visit_gift(x, ev, list_ok), ("pre", "live", "ids", "file", "reload", "common"),
                     cells_client, PRE, reloads=True)


def row_host_visits_list():
    return run_copy_row("host_visits_list", "gift_copy_host_visit", KEY, lambda x, ev: host_visit_gift(x, ev, list_ok), ("pre", "live", "ids", "file", "reload", "common"),
                     cells_host, PRE, reloads=True)


def row_host_gives_no_screen():
    return run_copy_row("host_gives_no_screen", "gift_copy_no_screen", KEY, lambda x, ev: visit_gift(x, ev, no_screen), ("pre", "live", "ids", "file", "common"),
                     cells_client, PRE)


if __name__ == "__main__":
    sys.exit(main("test_gift_display_copy", [("host_gives_list", row_host_gives_list), ("host_visits_list", row_host_visits_list), ("host_gives_no_screen", row_host_gives_no_screen)]))
