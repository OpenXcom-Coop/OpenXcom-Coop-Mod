"""SEPARATE campaign base list: leaving a base screen or a TRANSFER window must
never empty or truncate a player's base list.

In a SEPARATE campaign each world also holds the partner's bases as `_coopIcon`
mirror markers. A basescape hides them from the live base list while it is open
and must put them back on EVERY way out (GEOSCAPE, BUILD NEW BASE, a right-click
on the access lift). A TRANSFER window opened outside a base screen must leave
the list alone. Without the fix the copy put back lives on the base the screen
was opened with, so a base switch, a base dismantle, the geoscape BASES button
landing on a mirror, BUILD NEW BASE, the lift right-click and a forced "storage
exceeded" TRANSFER all empty or truncate the list (an empty list ends the
campaign in defeat on both machines).

Six boots, nine rows:

  Boot exits (setup):
    transfer_cancel            basescape TRANSFER + Cancel, GEOSCAPE (control)
    build_new_base_exit        BUILD NEW BASE exit from a BASES-button basescape
    key_switch_base            key 2 switches the base, GEOSCAPE (last)
  Boot lift (setup):
    lift_right_click_exit      right-click on the access lift exits
    dismantle_lift_base        dismantle the lift of a lift-only base, GEOSCAPE (last)
  Boot mini_view (setup):
    mini_view_switch_base      mini-view click switches the base, GEOSCAPE
  Boot bases_button (setup):
    bases_button_second_base   geoscape BASES on the second base the setup leaves selected
  Boot storage (setup, storageLimitsEnforced):
    storage_exceeded_transfer  forced "storage exceeded" TRANSFER
  Boot shared (shared_setup):
    shared_control             SHARED control: nothing hidden, key switch + TRANSFER

setup: SEPARATE campaign; the host builds HostBase2 through the real flow and
leaves it through GEOSCAPE. Its preconditions are the base list BASE0 in that
order and the selected base HostBase2 (not the mirror ClientBase).

Without the fix:
  transfer_cancel, shared_control: pass (controls).
  build_new_base_exit, lift_right_click_exit: host bases [HostBase, HostBase2,
      ClientBase], ending 0: the exit leaves the list filtered, then the
      geoscape's baseRequest reply re-creates the ClientBase mirror as a NEW
      object at the end of the list.
  key_switch_base, mini_view_switch_base, bases_button_second_base,
  dismantle_lift_base: host bases [], ending 2 on both machines.
  storage_exceeded_transfer: rows [] and host bases [] at TransferBaseState, []
      after Cancel, ending 2. The step after close_screens is its own stop (it
      pops until the geoscape is on top); without the fix the game ends right
      after it, so no top-state wait follows and the EVIDENCE line comes before
      any later check.

Each row prints ONE "EVIDENCE <row>:" line (both machines' base lists as
(name, coopBase, coopIcon) in list order, both endings, the host's top state)
and then asserts; main() runs every row even after an earlier one failed and
prints "PASS <row>" / "FAIL <row>: <message>". A fixture step that does not
reach its state raises "PRECONDITION <row>: ..." with both machines' stacks and
bases. A boot holds at most one row that ends the campaign without the fix
and it runs last. A new crash log (before/after the boot) fails the boot's last
row.

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
(PORT_EXITS, PORT_LIFT, PORT_MINI_VIEW, PORT_BASES_BUTTON, PORT_STORAGE,
 PORT_SHARED) = "48984", "48986", "48988", "48990", "48992", "48994"

KEY_BASE_SELECT_2 = 50            # Options::keyBaseSelect2 = SDLK_2
BASEVIEW_LIFT_CELL = (80, 80)     # build_new_base default lift (2, 2), BaseView::GRID_SIZE 32: centre
MINI_SLOT1_CENTRE = (24, 8)       # MiniBaseView::MINI_SIZE 14 + 2 per slot: slot 1 centre
STORAGE_ITEM = "STR_ALIEN_ALLOYS"  # measured: stores used 51.0 -> 67.0 (0.1 each) vs available 65
STORAGE_COUNT = 160                # measured: SellState 0.45 s after geo_set_speed 4

HOST_BASE = ("HostBase", False, False)
CLIENT_MIRROR = ("ClientBase", True, True)
HOST_BASE2 = ("HostBase2", False, False)
BASE0 = [HOST_BASE, CLIENT_MIRROR, HOST_BASE2]
HIDDEN = [HOST_BASE, HOST_BASE2]
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


def widget(rid, host, client, type_suffix):
    w = host.cmd({"cmd": "list_widgets"})
    hits = [x for x in w.get("widgets", []) if x.get("type", "").endswith("::" + type_suffix)]
    precondition(rid, len(hits) == 1, "one %s widget on %s: %s" % (type_suffix, w.get("state"), hits),
                 host, client)
    return hits[0]


def inject_click(rid, host, client, ctx, bx, by, button="left"):
    wx, wy = int(bx * ctx["xs"]), int(by * ctx["ys"])
    r = host.cmd({"cmd": "inject_input", "kind": "click", "x": wx, "y": wy, "button": button})
    precondition(rid, bool(r.get("ok")), "inject_input %s click (%d,%d) -> %s" % (button, wx, wy, r),
                 host, client)


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

def setup_separate(host, client, port):
    rid = "setup"
    session.new_campaign(host, client, port=port)
    for gc in (host, client):
        wait_top(rid, gc, "GeoscapeState", host, client, timeout=60)
    r = host.cmd({"cmd": "build_new_base", "lon": LAND_LON + 0.03, "lat": LAND_LAT + 0.03,
                  "name": "HostBase2"})
    precondition(rid, bool(r.get("ok")), "build_new_base HostBase2 -> %s" % r, host, client)
    wait_top(rid, host, "BasescapeState", host, client)
    g = click(rid, host, "GEOSCAPE", host, client)
    xs, ys = g["winX"] / float(g["baseX"]), g["winY"] / float(g["baseY"])
    precondition(rid, g["winX"] == round(g["baseX"] * xs) and g["winY"] == round(g["baseY"] * ys),
                 "window scale from %s" % g, host, client)
    wait_top(rid, host, "GeoscapeState", host, client)
    wait_until(rid, "client HostBase2 mirror", lambda: any(
        isinstance(b, tuple) and b[0] == "HostBase2" for b in blist(client)), host, client, timeout=30)
    hb = blist(host)
    precondition(rid, hb == BASE0, "host bases %s != BASE0 %s" % (hb, BASE0), host, client)
    sel = selected(host)
    precondition(rid, sel == "HostBase2", "host selectedBase %r != 'HostBase2'" % sel, host, client)
    print("setup ready: host bases %s selected %r scale (%.2f, %.2f)" % (hb, sel, xs, ys), flush=True)
    return {"xs": xs, "ys": ys}


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

def row_transfer_cancel(host, client, ctx):
    rid = "transfer_cancel"
    open_basescape(rid, host, client, "HostBase")
    hb = blist(host)
    precondition(rid, hb == HIDDEN, "bases on the basescape %s != %s" % (hb, HIDDEN), host, client)
    click(rid, host, "TRANSFER", host, client)
    wait_top(rid, host, "TransferBaseState", host, client)
    ss = host.cmd({"cmd": "screen_state"})
    precondition(rid, ss.get("top") == "transfer_base", "screen_state %s" % ss, host, client)
    rows = ss.get("rows")
    click(rid, host, "CANCEL", host, client)
    wait_top(rid, host, "BasescapeState", host, client)
    after_cancel = blist(host)
    leave_basescape(rid, host, client)
    wait_top(rid, host, "GeoscapeState", host, client)
    wait_clock(rid, host, client)
    evidence(rid, host, client, rows=rows, basesAfterCancel=after_cancel)
    fails = []
    if rows != ["ClientBase", "HostBase2"]:
        fails.append("rows %s != ['ClientBase', 'HostBase2']" % rows)
    if after_cancel != HIDDEN:
        fails.append("bases after Cancel %s != %s" % (after_cancel, HIDDEN))
    list_ok(rid, host, client, BASE0, fails)
    verdict(rid, fails)


def row_build_new_base_exit(host, client, ctx):
    rid = "build_new_base_exit"
    open_basescape(rid, host, client, "HostBase")
    leave_basescape(rid, host, client)
    wait_top(rid, host, "GeoscapeState", host, client)
    sel = selected(host)
    precondition(rid, sel == "HostBase", "selectedBase %r != 'HostBase'" % sel, host, client)
    click(rid, host, "BASES", host, client)
    wait_top(rid, host, "BasescapeState", host, client)
    hb = blist(host)
    precondition(rid, hb == HIDDEN, "bases on the basescape %s != %s" % (hb, HIDDEN), host, client)
    click(rid, host, "NEW BASE", host, client)
    wait_top(rid, host, "BuildNewBaseState", host, client)
    click(rid, host, "CANCEL", host, client)
    wait_top(rid, host, "GeoscapeState", host, client)
    wait_clock(rid, host, client)
    evidence(rid, host, client, selected=selected(host))
    fails = []
    list_ok(rid, host, client, BASE0, fails)
    verdict(rid, fails)


def row_key_switch_base(host, client, ctx):
    rid = "key_switch_base"
    open_basescape(rid, host, client, "HostBase")
    sel = selected(host)
    precondition(rid, sel == "HostBase", "selectedBase %r != 'HostBase'" % sel, host, client)
    r = host.cmd({"cmd": "inject_input", "kind": "key", "key": KEY_BASE_SELECT_2})
    precondition(rid, bool(r.get("ok")), "inject_input key 50 -> %s" % r, host, client)
    wait_until(rid, "selectedBase == 'HostBase2'", lambda: selected(host) == "HostBase2", host, client,
               timeout=5)
    leave_basescape(rid, host, client)
    wait_clock(rid, host, client)
    evidence(rid, host, client, selected=selected(host))
    fails = []
    list_ok(rid, host, client, BASE0, fails)
    verdict(rid, fails)


def row_lift_right_click_exit(host, client, ctx):
    rid = "lift_right_click_exit"
    open_basescape(rid, host, client, "HostBase2")
    hb = blist(host)
    precondition(rid, hb == HIDDEN, "bases on the basescape %s != %s" % (hb, HIDDEN), host, client)
    v = widget(rid, host, client, "BaseView")
    inject_click(rid, host, client, ctx, v["x"] + BASEVIEW_LIFT_CELL[0], v["y"] + BASEVIEW_LIFT_CELL[1],
                 button="right")
    wait_top(rid, host, "GeoscapeState", host, client)
    wait_clock(rid, host, client)
    evidence(rid, host, client)
    fails = []
    list_ok(rid, host, client, BASE0, fails)
    verdict(rid, fails)


def row_dismantle_lift_base(host, client, ctx):
    rid = "dismantle_lift_base"
    open_basescape(rid, host, client, "HostBase2")
    hb = blist(host)
    precondition(rid, hb == HIDDEN, "bases on the basescape %s != %s" % (hb, HIDDEN), host, client)
    v = widget(rid, host, client, "BaseView")
    inject_click(rid, host, client, ctx, v["x"] + BASEVIEW_LIFT_CELL[0], v["y"] + BASEVIEW_LIFT_CELL[1])
    wait_top(rid, host, "DismantleFacilityState", host, client)
    click(rid, host, "OK", host, client)
    wait_top(rid, host, "BasescapeState", host, client)
    hb = blist(host)
    precondition(rid, hb == [HOST_BASE], "bases after the dismantle %s != %s" % (hb, [HOST_BASE]),
                 host, client)
    sel = selected(host)
    precondition(rid, sel == "HostBase", "selectedBase %r != 'HostBase'" % sel, host, client)
    leave_basescape(rid, host, client)
    wait_clock(rid, host, client)
    cb = blist(client)
    evidence(rid, host, client)
    fails = []
    list_ok(rid, host, client, [HOST_BASE, CLIENT_MIRROR], fails)
    if not isinstance(cb, list) or any(b[0] == "HostBase2" for b in cb):
        fails.append("client still lists the HostBase2 mirror: %s" % (cb,))
    verdict(rid, fails)


def row_mini_view_switch_base(host, client, ctx):
    rid = "mini_view_switch_base"
    open_basescape(rid, host, client, "HostBase")
    sel = selected(host)
    precondition(rid, sel == "HostBase", "selectedBase %r != 'HostBase'" % sel, host, client)
    m = widget(rid, host, client, "MiniBaseView")
    inject_click(rid, host, client, ctx, m["x"] + MINI_SLOT1_CENTRE[0], m["y"] + MINI_SLOT1_CENTRE[1])
    wait_until(rid, "selectedBase == 'HostBase2'", lambda: selected(host) == "HostBase2", host, client,
               timeout=5)
    leave_basescape(rid, host, client)
    wait_clock(rid, host, client)
    evidence(rid, host, client, selected=selected(host))
    fails = []
    list_ok(rid, host, client, BASE0, fails)
    verdict(rid, fails)


def row_bases_button_second_base(host, client, ctx):
    rid = "bases_button_second_base"
    sel = selected(host)
    precondition(rid, sel == "HostBase2", "selectedBase %r != 'HostBase2'" % sel, host, client)
    click(rid, host, "BASES", host, client)
    wait_top(rid, host, "BasescapeState", host, client)
    w = host.cmd({"cmd": "list_widgets"})
    captions = [x.get("text") for x in w.get("widgets", [])
                if x.get("type", "").endswith("::TextButton") and x.get("visible")]
    in_base = blist(host)
    in_sel = selected(host)
    leave_basescape(rid, host, client)
    wait_clock(rid, host, client)
    evidence(rid, host, client, buttons=captions, basesOnBasescape=in_base, selected=in_sel)
    fails = []
    list_ok(rid, host, client, BASE0, fails)
    verdict(rid, fails)


def row_storage_exceeded_transfer(host, client, ctx):
    rid = "storage_exceeded_transfer"
    r = host.cmd({"cmd": "give_items", "item": STORAGE_ITEM, "count": STORAGE_COUNT, "base": "HostBase"})
    precondition(rid, bool(r.get("ok")), "give_items -> %s" % r, host, client)
    rep = host.cmd({"cmd": "base_report", "base": "HostBase"})
    precondition(rid, rep.get("usedStores", 0) > rep.get("availableStores", 0),
                 "HostBase stores used %s available %s" % (rep.get("usedStores"), rep.get("availableStores")),
                 host, client)
    for gc in (host, client):
        gc.cmd({"cmd": "geo_set_speed", "idx": 4})
    deadline = time.time() + 60
    while time.time() < deadline:
        st = stack(host)
        if any("SellState" in s for s in st):
            break
        if st and "ErrorMessageState" in st[-1]:
            host.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.2)
    for gc in (host, client):
        gc.cmd({"cmd": "geo_set_speed", "idx": 0})
    precondition(rid, top(host) == "SellState", "host top SellState within 60s of geo_set_speed 4",
                 host, client)
    w = host.cmd({"cmd": "list_widgets"})
    tbtn = [x for x in w.get("widgets", []) if x.get("type", "").endswith("::TextButton")
            and x.get("visible") and "Transfer" in (x.get("text") or "")]
    precondition(rid, len(tbtn) == 1, "one visible 'Transfer' button on %s: %s" % (w.get("state"), tbtn),
                 host, client)
    click(rid, host, "transfer", host, client)
    wait_top(rid, host, "TransferBaseState", host, client)
    rows = host.cmd({"cmd": "screen_state"}).get("rows")
    at_transfer = blist(host)
    click(rid, host, "CANCEL", host, client)
    wait_top(rid, host, "SellState", host, client)
    at_cancel = blist(host)
    # close_screens' own stop is the step (it pops until the geoscape is on top), no
    # top-state wait after it; the EVIDENCE line comes before any later check.
    r = host.cmd({"cmd": "close_screens"})
    precondition(rid, bool(r.get("ok")) and r.get("popped", 0) >= 1, "close_screens -> %s" % r,
                 host, client)
    at_geoscape = blist(host)
    clock = clock_outcome(host, client)
    evidence(rid, host, client, rows=rows, basesAtTransfer=at_transfer, basesAfterCancel=at_cancel,
             basesAtGeoscape=at_geoscape, closeScreensPopped=r.get("popped"), clock=clock or "ok")
    fails = []
    for what, got in (("at TransferBaseState", at_transfer), ("after Cancel", at_cancel),
                      ("at the geoscape", at_geoscape)):
        if got != BASE0:
            fails.append("host bases %s %s != BASE0" % (what, got))
    if rows != ["ClientBase", "HostBase2"]:
        fails.append("rows %s != ['ClientBase', 'HostBase2'] (the partner's bases are offered too, "
                     "as on the base-screen TRANSFER)" % rows)
    if clock:
        fails.append(clock)
    list_ok(rid, host, client, BASE0, fails)
    verdict(rid, fails)


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
    run_boot("exits", PORT_EXITS, setup_separate, [("transfer_cancel", row_transfer_cancel),
                                                   ("build_new_base_exit", row_build_new_base_exit),
                                                   ("key_switch_base", row_key_switch_base)])
    run_boot("lift", PORT_LIFT, setup_separate, [("lift_right_click_exit", row_lift_right_click_exit),
                                                 ("dismantle_lift_base", row_dismantle_lift_base)])
    run_boot("mini_view", PORT_MINI_VIEW, setup_separate, [("mini_view_switch_base", row_mini_view_switch_base)])
    run_boot("bases_button", PORT_BASES_BUTTON, setup_separate,
             [("bases_button_second_base", row_bases_button_second_base)])
    run_boot("storage", PORT_STORAGE, setup_separate, [("storage_exceeded_transfer", row_storage_exceeded_transfer)],
             host_options={"storageLimitsEnforced": True})
    run_boot("shared", PORT_SHARED, setup_shared, [("shared_control", row_shared_control)])
    if FAILED:
        print("test_old_bases: %d row(s) failed: %s" % (len(FAILED), " ".join(FAILED)), flush=True)
        return 2
    print("ALL test_old_bases ROWS PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
