"""Rows client_gives_back and host_gives_back: a received display copy given straight back (helpers gift_back_helpers.py).

In a SEPARATE co-op campaign a soldier gifted to a player who is viewing the giver's base is queued until the leave and shown in the view as
a display copy that keeps the GIVER's soldier id. Giving that copy straight back before the leave must reach the giver (who gets its soldier
back) without the queued receive replaying after the leave (both players would hold the soldier), and a client receiver must keep its OWN
soldier that shares the giver's id in its parked own world (else it loses one of its soldiers and the host's stored copy of its world
loses it at once). One fresh boot pair per row (SEPARATE gm1 tcp, key 49318, its own user dirs), no reload:
  client_gives_back   the client visits the host base; the host gifts its first own soldier not in a craft (renamed GIFTNAME; its id is held by one of
        the client's own soldiers) to it; the client's GiftNoticeState OK; SOLDIERS, GIFTNAME's row, KP2, the host's button (the display
        copy given back); the host's GiftNoticeState OK; stored("back") = the host's copy fnv changed, then a named host save; the client's
        OK, OK, GEOSCAPE; the replay line recorded (never awaited); HOLD_L; the census; the host's quick save with no visit open.
        Cells client_gives_back-pre, client_gives_back-stored, client_gives_back-own, client_gives_back-client, client_gives_back-host, client_gives_back-ids, client_gives_back-file, client_gives_back-common.
  host_gives_back  the host visits the client base; the client gifts its first own soldier not in a craft (its id held by one of the host's own
        soldiers); the host's notice OK; the host gives the display copy back (SOLDIERS, row, KP2, the client's button); the client's notice
        OK; the host's OK, OK, GEOSCAPE; the same record, census and save. Cells host_gives_back-pre, host_gives_back-host, host_gives_back-own, host_gives_back-client, host_gives_back-ids,
        host_gives_back-file, host_gives_back-common.
stored = the named save's client entry holds every (id, name) of the client's own soldiers read before the visit (own0) and no GIFTNAME;
own = after the leave every own0 pair of the receiver on its own bases; client / host = GIFTNAME on none of the receiver's own bases; the
giver's guard = GIFTNAME once on the giver's own bases under its own id and the giver's ids those of own0; ids = no id held twice on either
machine's own bases; file = QUICK holds GIFTNAME only in the giver's half (and, client_gives_back, every own0(client) pair in the client entry); common =
both machines alive at the read, no new .dmp since B.
RED cells fail on a build without the fix: client_gives_back-stored, client_gives_back-own, client_gives_back-client, client_gives_back-file, host_gives_back-host, host_gives_back-file (6 of 15). Exit 0 only when
every cell passes, else 2 (no SKIP). one foreground run per invocation:
    python tools/coop_test/test_gift_back.py"""
import sys
from gift_back_helpers import *  # noqa: F401,F403

KEY = "49318"
PRE = ("each construction step met its precondition (boot, picker, the visit, B, the gift and the receiver's deferral line, the giver's id "
       "on one of the receiver's own soldiers, the notice, the gift-back's screens and the giver's notice, %sthe leave, the host's save)")


def own0(x, ev):
    ev["own0"] = {"host": own_ids(x.host), "client": own_ids(x.client)}


def held_by(ev, who):
    """the giver's soldier id is held by one of the receiver's own soldiers read before the visit (the rows' purpose)"""
    gid = ev["gift"]["soldier"][1]
    if gid not in [s[0] for s in ev["own0"][who]]:
        raise Stop("the giver's id %s is held by none of the %s's own soldiers: %s" % (gid, who, ev["own0"][who]))


def build_client_gives_back(x, ev):
    x.rid = "client_gives_back"
    picker(x, ev)
    own0(x, ev)
    visit(x, ev)
    baseline(x, ev)
    x.names = [x.gift]
    ev["names"] = {"gift": x.gift}
    host_gift(x, ev, DEFERRED)
    held_by(ev, "client")
    receiver_path_back(x, ev, x.client, gift_back_client)
    host_save(x, ev)
    quick_entries(x, ev)


def build_host_gives_back(x, ev):
    x.rid = "host_gives_back"
    picker(x, ev)
    host_picker(x, ev)
    own0(x, ev)
    host_visit(x, ev)
    baseline(x, ev)
    x.names = [x.gift]
    ev["names"] = {"gift": x.gift}
    gift_from(x, ev)
    held_by(ev, "host")
    receiver_path_back(x, ev, x.host, gift_back_host)
    host_save(x, ev)
    quick_entries(x, ev)


def row_client_gives_back():
    return run_back_row("client_gives_back", "gift_back_client", KEY, build_client_gives_back, ("pre", "stored", "own", "client", "host", "ids", "file", "common"),
                 PRE % "the host's copy changed after the gift and after the gift-back, the named save, ")


def row_host_gives_back():
    return run_back_row("host_gives_back", "gift_back_host", KEY, build_host_gives_back, ("pre", "host", "own", "client", "ids", "file", "common"), PRE % "")


if __name__ == "__main__":
    sys.exit(main("test_gift_back", [("client_gives_back", row_client_gives_back), ("host_gives_back", row_host_gives_back)]))
