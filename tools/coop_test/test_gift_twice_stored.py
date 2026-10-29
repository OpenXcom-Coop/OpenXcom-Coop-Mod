"""Row gift_twice_stored: the host's stored copy of a visiting client's world keeps every gift (helpers gift_back_helpers.py).

In a SEPARATE co-op campaign a soldier gifted to a client that is viewing the host's base is queued until the leave. The client's stored
own world (the copy the host holds and saves) must hold every soldier received so far, not only the NEWEST gift on top of "basehost":
after a second gift the copy still holds the first, and after the client gives one of its own soldiers away from the view it still holds
every received one, before the leave's push. One fresh boot pair (SEPARATE gm1 tcp, key 49319, its own user dirs), no reload:
  gift_twice_stored   the client's first own soldier not in a craft renamed GUESTNAME and transferred to the host base; the client visits the host base;
        the host gifts two soldiers (GIFTNAME, then GIFTNAME2) to it, each followed by stored("g1") / stored("g2") (the host's copy fnv changed
        after the press, then a named host save); the client gives GUESTNAME to the host from the view (the host's notice OK), then
        stored("send"); the client's OK, OK, GEOSCAPE; both replay lines (a precondition); HOLD_L; the census; the host's quick save.
        Cells gift_twice_stored-pre, gift_twice_stored-g1, gift_twice_stored-g2, gift_twice_stored-send, gift_twice_stored-leave, gift_twice_stored-file, gift_twice_stored-ids, gift_twice_stored-common.
g1 / g2 / send = the named save's client entry holds every soldier received so far once (no GUESTNAME after the send) and every other
(id, name) of the client's own soldiers read before the visit; leave = GIFTNAME and GIFTNAME2 once each on the client's own bases, GUESTNAME on none
and once on the host's; file = QUICK holds GIFTNAME and GIFTNAME2 once each in the client entry only and GUESTNAME once in the host half only;
ids = no id held twice on either machine's own bases; common = both machines alive at the read, no new .dmp since the baseline (just
before the first gift).
FIX cells fail on a build without the fix: gift_twice_stored-g2, gift_twice_stored-send (2 of 8). Exit 0 only when every cell passes, else 2 (no SKIP).
Run:
    python tools/coop_test/test_gift_twice_stored.py"""
import sys
from gift_back_helpers import *  # noqa: F401,F403

KEY = "49319"
PRE = ("each construction step met its precondition (boot, the guest, picker, the visit, the baseline, each host gift: its menu, the client's deferral "
       "line and notice, the host's copy changed, the named save; the client's gift of the guest: the host's notice, the copy changed, the "
       "named save; the leave, both replay lines, the host's save)")


def build_gift_twice_stored(x, ev):
    x.rid = "gift_twice_stored"
    stage_guest_named(x, ev)
    picker(x, ev)
    ev["own0"] = {"host": own_ids(x.host), "client": own_ids(x.client)}
    visit(x, ev)
    baseline(x, ev)
    g2 = next(n for n in GIFTNAMES if n != x.gift)
    x.names = [x.gift, g2, GUESTNAME]
    ev["names"] = {"gift": x.gift, "g2": g2, "guest": GUESTNAME}
    host_gives(x, ev, 1, x.gift)
    host_gives(x, ev, 2, g2)
    client_gives(x, ev, GUESTNAME)
    receiver_path_back(x, ev, x.client, need=2, notice=False)
    host_save(x, ev)
    quick_entries(x, ev)


def row_gift_twice_stored():
    return run_back_row("gift_twice_stored", "gift_twice_stored", KEY, build_gift_twice_stored, ("pre", "g1", "g2", "send", "leave", "file", "ids", "common"), PRE)


if __name__ == "__main__":
    sys.exit(main("test_gift_twice_stored", [("gift_twice_stored", row_gift_twice_stored)]))
