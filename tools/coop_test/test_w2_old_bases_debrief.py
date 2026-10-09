"""W2-H8 (owner D182/D185, D201 = b) - SEPARATE `old_bases`: a TRANSFER opened from
the debriefing's loot page must leave the host's base list alone.

Before the fix the Select Destination Base window swaps the live base list for a
copy stored on the debriefing's base, which is empty when that base's screen was
never opened: the list becomes empty (the campaign ends in defeat once the
geoscape runs). After the fix the list keeps every own base and the partner's
mirror, and the window offers the partner's base too (owner D201 = b).

One boot, one row (spec rewrite/prompts/w2h8_old_bases.md (f)):

  Boot G  D2  a SEPARATE guest battle with HostBase2 built before the mission;
              the host aborts (the guest votes YES, R4-L1), reaches its debriefing, opens page 3 (LOOT),
              TRANSFER, Cancel, then OK back to the geoscape. The base list is
              read at the three points (TransferBaseState, after Cancel, the
              geoscape) and the window's destination rows are read.

The SEPARATE client stays in the battle after the host's abort (F387), so the
host clock is frozen (F2429): the row reads the list at the three points and
asserts no ending.

Named red on the pre-fix build (spec (f) + AMENDMENT H8-1 Q3): rows [] and
host bases [] at TransferBaseState and after Cancel; at the geoscape the list
is all mirrors [ClientBase, HostBase, HostBase2] (coopBase and coopIcon set) -
the client, still in the battle on a copy of the host's world, reports the
host's bases as its own - and the host's ending stays 0 (F2653).

The row prints ONE "EVIDENCE D2:" line and then asserts; a fixture step that
does not reach its state raises "PRECONDITION D2: ..." with both machines'
stacks and bases. A new crash log (before/after the boot) fails the row.

Run:  python tools/coop_test/test_w2_old_bases_debrief.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session

PORT_G = "48996"  # the lobby rendezvous key (harness.py: an in-process key, never a bound port)

HOST_BASE = ("HostBase", False, False)
CLIENT_MIRROR = ("ClientBase", True, True)
HOST_BASE2 = ("HostBase2", False, False)
BASE0 = [HOST_BASE, CLIENT_MIRROR, HOST_BASE2]


def stack(gc):
    try:
        return gc.cmd({"cmd": "get_state"}).get("states", [])
    except Exception as e:  # a dead socket is evidence, not a test error
        return ["<get_state: %s: %s>" % (type(e).__name__, e)]


def top(gc):
    st = stack(gc)
    return st[-1].replace("class OpenXcom::", "") if st else "none"


def geo(gc):
    try:
        return gc.cmd({"cmd": "geo_state"})
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}


def blist(gc):
    g = geo(gc)
    if "bases" not in g:
        return "<%s>" % g.get("error")
    return [(b["name"], bool(b["coopBase"]), bool(b["coopIcon"])) for b in g["bases"]]


def ending(gc):
    try:
        return gc.cmd({"cmd": "ending_state"}).get("ending")
    except Exception as e:
        return "<%s>" % type(e).__name__


def dump(host, client):
    return ("host stack=%s bases=%s | client stack=%s bases=%s"
            % ([s.replace("class OpenXcom::", "") for s in stack(host)[-4:]], blist(host),
               [s.replace("class OpenXcom::", "") for s in stack(client)[-4:]], blist(client)))


def precondition(ok, what, host, client):
    if not ok:
        raise AssertionError("PRECONDITION D2: %s | %s" % (what, dump(host, client)))


def wait_until(what, pred, host, client, timeout=10.0, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(interval)
    precondition(False, "%s not reached in %.0fs" % (what, timeout), host, client)


def wait_top(gc, name, host, client, timeout=10.0):
    wait_until("%s top %s" % (gc.name, name), lambda: top(gc) == name, host, client, timeout)


def click(gc, match, host, client):
    r = gc.cmd({"cmd": "click_widget", "match": match})
    precondition(bool(r.get("ok")), "%s click_widget %r -> %s" % (gc.name, match, r), host, client)
    return r


def build2(host, client):
    """pre_mission_start: the host builds HostBase2 through the real flow and
    leaves it through GEOSCAPE; the client receives its mirror. (The guest
    transfer's CoopState notice may cover the host's geoscape here;
    bring_up_separate_guest_battle drains it right after this call.)"""
    r = host.cmd({"cmd": "build_new_base", "lon": LAND_LON + 0.03, "lat": LAND_LAT + 0.03,
                  "name": "HostBase2"})
    precondition(bool(r.get("ok")), "build_new_base HostBase2 -> %s" % r, host, client)
    wait_top(host, "BasescapeState", host, client)
    click(host, "GEOSCAPE", host, client)
    wait_until("host left the basescape", lambda: top(host) != "BasescapeState", host, client)
    wait_until("client HostBase2 mirror", lambda: any(
        isinstance(b, tuple) and b[0] == "HostBase2" for b in blist(client)), host, client, timeout=30)
    print("build2: host bases %s client bases %s" % (blist(host), blist(client)), flush=True)


def row_d2(host, client):
    session.bring_up_separate_guest_battle(host, client, port=PORT_G, pre_mission_start=build2)
    host.ok({"cmd": "battle_action", "action": "abort"})
    wait_until("host AbortMissionState", lambda: any("AbortMissionState" in s for s in stack(host)),
               host, client, timeout=30)
    r = host.cmd({"cmd": "dismiss_popup"})
    precondition(r.get("handled") == "AbortMissionState", "abort confirm -> %s" % r, host, client)
    try:  # R4-L1 (D231): the OK opened the abort vote; the guest's YES passes it
        session.abort_vote_yes(host, client)
    except Exception as e:
        precondition(False, "abort vote: %s" % e, host, client)
    wait_top(host, "DebriefingState", host, client, timeout=120)
    hb = blist(host)
    precondition(hb == BASE0, "host bases at the debriefing %s != BASE0 %s" % (hb, BASE0), host, client)
    click(host, "STATS", host, client)
    wait_until("debriefing page 2", lambda: any(
        x.get("text") == "LOOT" and x.get("visible")
        for x in host.cmd({"cmd": "list_widgets"}).get("widgets", [])), host, client)
    click(host, "LOOT", host, client)
    wait_until("debriefing page 3 TRANSFER visible",
               lambda: host.cmd({"cmd": "debrief_state"}).get("transferVisible") is True, host, client)
    click(host, "TRANSFER", host, client)
    wait_top(host, "TransferBaseState", host, client)
    ss = host.cmd({"cmd": "screen_state"})
    precondition(ss.get("top") == "transfer_base", "screen_state %s" % ss, host, client)
    rows = ss.get("rows")
    at_transfer = blist(host)
    click(host, "CANCEL", host, client)
    wait_top(host, "DebriefingState", host, client)
    at_cancel = blist(host)
    click(host, "OK", host, client)
    deadline = time.time() + 60
    reached = session.drain_to_geoscape(host, deadline)
    precondition(reached is True, "host back on the geoscape after the debriefing OK", host, client)
    at_geoscape = blist(host)
    print("EVIDENCE D2: hostBases=%s clientBases=%s hostEnding=%s clientEnding=%s hostTop=%s rows=%s "
          "basesAtTransfer=%s basesAfterCancel=%s basesAtGeoscape=%s"
          % (blist(host), blist(client), ending(host), ending(client), top(host), rows,
             at_transfer, at_cancel, at_geoscape), flush=True)
    fails = []
    for what, got in (("at TransferBaseState", at_transfer), ("after Cancel", at_cancel),
                      ("at the geoscape", at_geoscape)):
        if got != BASE0:
            fails.append("host bases %s %s != BASE0" % (what, got))
    if rows != ["ClientBase", "HostBase2"]:
        fails.append("rows %s != ['ClientBase', 'HostBase2'] (D201 = b)" % rows)
    if fails:
        raise AssertionError("%d failure(s): %s" % (len(fails), " | ".join(fails)))


def main():
    crash0 = session._crash_log_snapshot()
    host = client = None
    err = None
    try:
        host = GameClient("host", 1, make_user_dir("w2h8g_host"))
        client = GameClient("client", 2, make_user_dir("w2h8g_client"))
        host.spawn(); client.spawn(); host.connect(); client.connect()
        row_d2(host, client)
    except Exception as e:  # the message is the verdict
        err = e
    finally:
        for gc in (host, client):
            if gc is None:
                continue
            try:
                gc.shutdown()
            except Exception as e:
                print("SHUTDOWN %s: %s" % (gc.name, e), flush=True)
                err = err or AssertionError("%s shutdown failed: %s" % (gc.name, e))
    new_crash = sorted(session._crash_log_snapshot() - crash0)
    if new_crash:
        msg = "new crash log(s): %s" % new_crash
        err = AssertionError(msg if err is None else "%s | %s" % (err, msg))
    if err is None:
        print("PASS D2", flush=True)
        print("ALL W2-H8 old_bases debrief ROWS PASSED", flush=True)
        return 0
    kind = "" if isinstance(err, AssertionError) else "%s: " % type(err).__name__
    print("FAIL D2: %s%s" % (kind, err), flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
