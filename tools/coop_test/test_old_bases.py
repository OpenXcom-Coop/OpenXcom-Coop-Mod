"""SHARED campaign base list: leaving a base screen or a TRANSFER window keeps the full base list.

The basescape keeps every base in the list while it is open (a SHARED world holds no partner base copies to hide):
the TRANSFER window lists the other base, its Cancel and a key-2 base switch leave the list unchanged on both
machines, and GEOSCAPE returns with the clock running.

One boot, one row:
    shared_control             nothing hidden, TRANSFER + Cancel, key switch, GEOSCAPE

shared_setup: SHARED campaign; the host builds SharedBase2; both machines list [HostBase, SharedBase2].

The row prints ONE "EVIDENCE <row>:" line (both machines' base lists as (name, coopBase, coopIcon) in list order,
both endings, the host's top state) and then asserts, printing "PASS <row>" / "FAIL <row>: <message>". A fixture
step that does not reach its state raises "PRECONDITION <row>: ..." with both machines' stacks and bases. A new
crash log (before/after the boot) fails the row.

Run:  python tools/coop_test/test_old_bases.py
Exit 0 = every row passed; 2 = at least one row failed.
"""

import datetime
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session

# One lobby rendezvous key per boot (harness.py: an in-process key, never a bound port).
PORT_SHARED = "48994"

KEY_BASE_SELECT_2 = 50            # Options::keyBaseSelect2 = SDLK_2

SHARED_BASE0 = [("HostBase", False, False), ("SharedBase2", False, False)]

FAILED = []


# --------------------------------------------------------------------------- probes

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


def blist(gc, g=None):
    g = geo(gc) if g is None else g
    if "bases" not in g:
        return "<%s>" % g.get("error")
    return [(b["name"], bool(b["coopBase"]), bool(b["coopIcon"])) for b in g["bases"]]


def selected(gc):
    return geo(gc).get("selectedBase")


def ending(gc):
    try:
        return gc.cmd({"cmd": "ending_state"}).get("ending")
    except Exception as e:
        return "<%s>" % type(e).__name__


def dump(host, client):
    return ("host stack=%s bases=%s selected=%r | client stack=%s bases=%s"
            % ([s.replace("class OpenXcom::", "") for s in stack(host)[-4:]], blist(host), selected(host),
               [s.replace("class OpenXcom::", "") for s in stack(client)[-4:]], blist(client)))


def evidence(rid, host, client, **extra):
    parts = ["hostBases=%s" % (blist(host),), "clientBases=%s" % (blist(client),),
             "hostEnding=%s" % ending(host), "clientEnding=%s" % ending(client),
             "hostTop=%s" % top(host)]
    for k, v in extra.items():
        parts.append("%s=%s" % (k, v))
    print("EVIDENCE %s: %s" % (rid, " ".join(parts)), flush=True)


# --------------------------------------------------------------------------- steps

def precondition(rid, ok, what, host, client):
    if not ok:
        raise AssertionError("PRECONDITION %s: %s | %s" % (rid, what, dump(host, client)))


def wait_until(rid, what, pred, host, client, timeout=10.0, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(interval)
    precondition(rid, False, "%s not reached in %.0fs" % (what, timeout), host, client)


def wait_top(rid, gc, name, host, client, timeout=10.0):
    wait_until(rid, "%s top %s" % (gc.name, name), lambda: top(gc) == name, host, client, timeout)


def click(rid, gc, match, host, client):
    r = gc.cmd({"cmd": "click_widget", "match": match})
    precondition(rid, bool(r.get("ok")), "%s click_widget %r -> %s" % (gc.name, match, r), host, client)
    return r


def leave_basescape(rid, host, client):
    """GEOSCAPE on the host's basescape; waits until the click has been processed
    (the basescape is no longer on top), not for any particular next state."""
    click(rid, host, "GEOSCAPE", host, client)
    wait_until(rid, "host left the basescape", lambda: top(host) != "BasescapeState", host, client)


def open_basescape(rid, host, client, base):
    r = host.cmd({"cmd": "open_screen", "screen": "basescape", "base": base})
    precondition(rid, bool(r.get("ok")), "open_screen basescape %s -> %s" % (base, r), host, client)
    wait_top(rid, host, "BasescapeState", host, client)


def minutes(g):
    t = g.get("time")
    if not t:
        return None
    d = datetime.datetime(t["year"], t["month"], t["day"], t["hour"], t["minute"])
    return int(d.timestamp() // 60)


def clock_outcome(host, client, timeout=20.0):
    """Proof that the geoscape runs on (rows asserting ending == 0): 5-second speed
    on BOTH machines, then the host's clock must advance >= 2 minutes, or the host's
    ending turn non-zero, within the timeout. None when proven, else the failure text."""
    for gc in (host, client):
        gc.cmd({"cmd": "geo_set_speed", "idx": 0})
    m0 = minutes(geo(host))
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ending(host) not in (0, None):
            return None
        m = minutes(geo(host))
        if m0 is not None and m is not None and m - m0 >= 2:
            return None
        time.sleep(0.25)
    return "clock did not advance (host time %s, start %s min)" % (geo(host).get("time"), m0)


def wait_clock(rid, host, client, timeout=20.0):
    err = clock_outcome(host, client, timeout)
    if err:
        raise AssertionError("%s: %s | %s" % (rid, err, dump(host, client)))


def list_ok(rid, host, client, expected, fails):
    hb = blist(host)
    if hb != expected:
        fails.append("host bases %s != %s" % (hb, expected))
    for gc in (host, client):
        e = ending(gc)
        if e != 0:
            fails.append("%s ending %s != 0" % (gc.name, e))
    t = top(host)
    if t != "GeoscapeState":
        fails.append("host top %s != GeoscapeState" % t)


def verdict(rid, fails):
    if fails:
        raise AssertionError("%d failure(s): %s" % (len(fails), " | ".join(fails)))


# --------------------------------------------------------------------------- setup

def setup_shared(host, client, port):
    rid = "shared_setup"
    session.new_campaign(host, client, port=port, campaign_mode="shared")
    for gc in (host, client):
        wait_top(rid, gc, "GeoscapeState", host, client, timeout=60)
    r = host.cmd({"cmd": "build_new_base", "lon": LAND_LON + 0.03, "lat": LAND_LAT + 0.03,
                  "name": "SharedBase2"})
    precondition(rid, bool(r.get("ok")), "build_new_base SharedBase2 -> %s" % r, host, client)
    wait_until(rid, "both lists == SHARED_BASE0",
               lambda: blist(host) == SHARED_BASE0 and blist(client) == SHARED_BASE0,
               host, client, timeout=30)
    wait_top(rid, host, "GeoscapeState", host, client)
    print("shared_setup ready: both bases %s" % (SHARED_BASE0,), flush=True)
    return {}


# --------------------------------------------------------------------------- rows

def row_shared_control(host, client, ctx):
    rid = "shared_control"
    open_basescape(rid, host, client, "HostBase")
    hb = blist(host)
    precondition(rid, hb == SHARED_BASE0, "bases on the basescape %s != SHARED_BASE0 %s" % (hb, SHARED_BASE0),
                 host, client)
    click(rid, host, "TRANSFER", host, client)
    wait_top(rid, host, "TransferBaseState", host, client)
    rows = host.cmd({"cmd": "screen_state"}).get("rows")
    click(rid, host, "CANCEL", host, client)
    wait_top(rid, host, "BasescapeState", host, client)
    after_cancel = blist(host)
    r = host.cmd({"cmd": "inject_input", "kind": "key", "key": KEY_BASE_SELECT_2})
    precondition(rid, bool(r.get("ok")), "inject_input key 50 -> %s" % r, host, client)
    wait_until(rid, "selectedBase == 'SharedBase2'", lambda: selected(host) == "SharedBase2", host, client,
               timeout=5)
    leave_basescape(rid, host, client)
    wait_top(rid, host, "GeoscapeState", host, client)
    wait_clock(rid, host, client)
    evidence(rid, host, client, rows=rows, basesAfterCancel=after_cancel, selected=selected(host))
    fails = []
    if rows != ["SharedBase2"]:
        fails.append("rows %s != ['SharedBase2']" % rows)
    if after_cancel != SHARED_BASE0:
        fails.append("bases after Cancel %s != SHARED_BASE0" % (after_cancel,))
    cb = blist(client)
    if cb != SHARED_BASE0:
        fails.append("client bases %s != SHARED_BASE0" % (cb,))
    list_ok(rid, host, client, SHARED_BASE0, fails)
    verdict(rid, fails)


# --------------------------------------------------------------------------- boots

def run_boot(tag, port, setup, rows, host_options=None):
    crash0 = session._crash_log_snapshot()
    host = client = None
    pending = [rid for rid, _ in rows]
    last_rid = rows[-1][0]
    last_err = None

    def report(rid, err):
        pending.remove(rid)
        if err is None:
            print("PASS %s" % rid, flush=True)
        else:
            FAILED.append(rid)
            kind = "" if isinstance(err, AssertionError) else "%s: " % type(err).__name__
            print("FAIL %s: %s%s" % (rid, kind, err), flush=True)

    try:
        host = GameClient("host", 1, make_user_dir("old_bases_%s_host" % tag, options=host_options))
        client = GameClient("client", 2, make_user_dir("old_bases_%s_client" % tag))
        host.spawn(); client.spawn(); host.connect(); client.connect()
        ctx = setup(host, client, port)
        for rid, fn in rows:
            err = None
            try:
                fn(host, client, ctx)
            except Exception as e:  # every row runs; the message is the verdict
                err = e
            if rid == last_rid:
                last_err = err
            else:
                report(rid, err)
    except Exception as e:
        for rid in list(pending):
            if rid == last_rid:
                last_err = last_err or e
            else:
                report(rid, e)
    finally:
        for gc in (host, client):
            if gc is None:
                continue
            try:
                gc.shutdown()
            except Exception as e:
                print("SHUTDOWN %s boot %s: %s" % (gc.name, tag, e), flush=True)
                last_err = last_err or AssertionError("%s shutdown failed: %s" % (gc.name, e))
        new_crash = sorted(session._crash_log_snapshot() - crash0)
        if new_crash:
            msg = "new crash log(s) in boot %s: %s" % (tag, new_crash)
            last_err = AssertionError(msg if last_err is None else "%s | %s" % (last_err, msg))
        report(last_rid, last_err)


def main():
    run_boot("shared", PORT_SHARED, setup_shared, [("shared_control", row_shared_control)])
    if FAILED:
        print("test_old_bases: %d row(s) failed: %s" % (len(FAILED), " ".join(FAILED)), flush=True)
        return 2
    print("ALL test_old_bases ROWS PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
