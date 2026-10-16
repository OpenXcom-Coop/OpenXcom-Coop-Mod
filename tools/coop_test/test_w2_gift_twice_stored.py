"""W2-H70 S-D row R17 (spec docs rewrite/prompts/w2h70_sd_gift_back.md (f); TASK 0 rewrite/w2h70-task0/sd/CONSTANTS.md; lead L-H70-3,
F20715; ruling R-H70D-0; QH70D-1 .. QH70D-8 (a); helpers w2h70d_helpers.py, R-H70-2).

In a SEPARATE co-op campaign a soldier gifted to a client that is viewing the host's base is queued until the leave, and the client's
stored own world (the copy the host holds and saves) is rebuilt from "basehost" plus the NEWEST gift only: after a second gift the host's
copy lacks the first, and after the client gives one of its own soldiers away from the view it lacks every received one, until the leave's
push (F20715, F20913, F20914). One fresh boot pair (SEPARATE gm1 tcp, key 49319, dirs w2h70d_r17_*), no reload:
  R17   the client's first own soldier not in a craft renamed GUESTNAME and transferred to the host base; the client visits the host base;
        the host gifts two soldiers (GIFTNAME, then G2) to it, each followed by stored("g1") / stored("g2") (the host's copy fnv changed
        after the press, then a named host save); the client gives GUESTNAME to the host from the view (the host's notice OK), then
        stored("send"); the client's OK, OK, GEOSCAPE; both replay lines (a precondition); HOLD_L; the census; the host's quick save.
        Cells R17-pre, R17-g1, R17-g2, R17-send, R17-leave, R17-file, R17-ids, R17-common.
g1 / g2 / send = the named save's client entry holds every soldier received so far once (no GUESTNAME after the send) and every other
(id, name) of the client's own soldiers read before the visit; leave = GIFTNAME and G2 once each on the client's own bases, GUESTNAME on none
and once on the host's; file = QUICK holds GIFTNAME and G2 once each in the client entry only and GUESTNAME once in the host half only;
ids = no id held twice on either machine's own bases; common = both machines alive at the read, no new .dmp since B.
Red (HEAD, TASK 0 boots a / b): R17-g2, R17-send FAIL (2 of 8); green (ED1-ED6, boot c): 8 / 8. Exit 0 only when every cell passes, else
2 (WV-D99 / WV-D100; no SKIP). WV-D95: one foreground run per invocation:
    python tools/coop_test/test_w2_gift_twice_stored.py"""
import sys
from w2h70d_helpers import *  # noqa: F401,F403 (HD, R-H70-2)

KEY = "49319"
PRE = ("each construction step met its precondition (boot, the guest, picker, the visit, B, each host gift: its menu, the client's deferral "
       "line and notice, the host's copy changed, the named save; the client's gift of the guest: the host's notice, the copy changed, the "
       "named save; the leave, both replay lines, the host's save)")


def build_r17(x, ev):
    x.rid = "r17"
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
    receiver_path_d(x, ev, x.client, need=2, notice=False)
    host_save(x, ev)
    quick_d(x, ev)


def row_r17():
    return run_d("R17", "w2h70d_r17", KEY, build_r17, ("pre", "g1", "g2", "send", "leave", "file", "ids", "common"), PRE)


if __name__ == "__main__":
    sys.exit(main("test_w2_gift_twice_stored", [("R17", row_r17)]))
