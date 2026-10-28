"""W2-H70 S-D rows R16 and R16H (spec docs rewrite/prompts/w2h70_sd_gift_back.md (f); TASK 0 rewrite/w2h70-task0/sd/CONSTANTS.md; lead
L-H70B-1, F20714; ruling R-H70D-0; QH70D-1 .. QH70D-8 (a); helpers gift_back_helpers.py, R-H70-2).

In a SEPARATE co-op campaign a soldier gifted to a player who is viewing the giver's base is queued until the leave and shown in the view as
a display copy that keeps the GIVER's soldier id. Giving that copy straight back before the leave reaches the giver (who gets its soldier
back), but the queued receive still replays after the leave, so both players hold the soldier; a client receiver also erases its OWN soldier
that shares the giver's id from its parked own world, so it loses one of its soldiers and the host's stored copy of its world loses it at
once (F20714, F20911, F20912, F20927). One fresh boot pair per row (SEPARATE gm1 tcp, key 49318, dirs w2h70d_<row>_*), no reload:
  R16   the client visits the host base; the host gifts its first own soldier not in a craft (renamed GIFTNAME; its id is held by one of
        the client's own soldiers) to it; the client's GiftNoticeState OK; SOLDIERS, GIFTNAME's row, KP2, the host's button (the display
        copy given back); the host's GiftNoticeState OK; stored("back") = the host's copy fnv changed, then a named host save; the client's
        OK, OK, GEOSCAPE; the replay line recorded (never awaited); HOLD_L; the census; the host's quick save with no visit open.
        Cells R16-pre, R16-stored, R16-own, R16-client, R16-host, R16-ids, R16-file, R16-common.
  R16H  the host visits the client base; the client gifts its first own soldier not in a craft (its id held by one of the host's own
        soldiers); the host's notice OK; the host gives the display copy back (SOLDIERS, row, KP2, the client's button); the client's notice
        OK; the host's OK, OK, GEOSCAPE; the same record, census and save. Cells R16H-pre, R16H-host, R16H-own, R16H-client, R16H-ids,
        R16H-file, R16H-common.
stored = the named save's client entry holds every (id, name) of the client's own soldiers read before the visit (own0) and no GIFTNAME;
own = after the leave every own0 pair of the receiver on its own bases; client / host = GIFTNAME on none of the receiver's own bases; the
giver's guard = GIFTNAME once on the giver's own bases under its own id and the giver's ids those of own0; ids = no id held twice on either
machine's own bases; file = QUICK holds GIFTNAME only in the giver's half (and, R16, every own0(client) pair in the client entry); common =
both machines alive at the read, no new .dmp since B.
Red (HEAD, TASK 0 boots a / b): R16-stored, R16-own, R16-client, R16-file, R16H-host, R16H-file FAIL (6 of 15); green (ED1-ED6, boot c):
15 / 15. Exit 0 only when every cell passes, else 2 (WV-D99 / WV-D100; no SKIP). WV-D95: one foreground run per invocation:
    python tools/coop_test/test_gift_back.py"""
import sys
from gift_back_helpers import *  # noqa: F401,F403 (HD, R-H70-2)

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


def build_r16(x, ev):
    x.rid = "r16"
    picker(x, ev)
    own0(x, ev)
    visit(x, ev)
    baseline(x, ev)
    x.names = [x.gift]
    ev["names"] = {"gift": x.gift}
    host_gift(x, ev, DEFERRED)
    held_by(ev, "client")
    receiver_path_d(x, ev, x.client, gift_back_client)
    host_save(x, ev)
    quick_d(x, ev)


def build_r16h(x, ev):
    x.rid = "r16h"
    picker(x, ev)
    host_picker(x, ev)
    own0(x, ev)
    host_visit(x, ev)
    baseline(x, ev)
    x.names = [x.gift]
    ev["names"] = {"gift": x.gift}
    gift_from(x, ev)
    held_by(ev, "host")
    receiver_path_d(x, ev, x.host, gift_back_host)
    host_save(x, ev)
    quick_d(x, ev)


def row_r16():
    return run_d("R16", "w2h70d_r16", KEY, build_r16, ("pre", "stored", "own", "client", "host", "ids", "file", "common"),
                 PRE % "the host's copy changed after the gift and after the gift-back, the named save, ")


def row_r16h():
    return run_d("R16H", "w2h70d_r16h", KEY, build_r16h, ("pre", "host", "own", "client", "ids", "file", "common"), PRE % "")


if __name__ == "__main__":
    sys.exit(main("test_gift_back", [("R16", row_r16), ("R16H", row_r16h)]))
