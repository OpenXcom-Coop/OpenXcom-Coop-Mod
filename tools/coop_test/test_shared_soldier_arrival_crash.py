"""Regression: the 2nd player (a SHARED replica) crashes when host-ordered
soldiers ARRIVE and the player opens the base from the arrival popup.

Reported: "When I order soldiers in a shared base as the host, the 2nd player
crashes on arrival of those ordered soldiers."

Root cause (crash dump crash_20260730_224017): the arrival raises
ItemsArrivingState on the replica through SharedEcon::hostAlert (GeoscapeState
does `popup(new ItemsArrivingState); hostAlert("ItemsArrivingState")` when a
transfer lands). On a replica the ItemsArrivingState ctor finds NO hour-0
transfer - a replica's own transfers are frozen (PRD-J04) and the matching one
was already force-delivered + deleted by transfer_arrived - so its `_base` stays
null. Pressing "Go to Base" (bound to keyOk) then does
`new BasescapeState(_base=nullptr, ...)`, and the coop mod's ctor block
`if (_base->_coopBase == true)` dereferences the null base -> 0xC0000005 read at
[null+0x1d0].

Two scenarios, both firing the REAL "Go to Base" handler on the client:
  1) END-TO-END (the reported path): the HOST hires a soldier, time is advanced
     until it arrives, and the client opens the base from the arrival popup.
  2) DETERMINISTIC: raise the arrival popup directly via the hostAlert lane
     (no clock advance) and open the base - the same null-_base popup, isolated.

Pre-fix the client process crashes (its command socket drops); post-fix it
survives and lands on a real base screen.

Run:  python tools/coop_test/test_shared_soldier_arrival_crash.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import geo

SOLDIER = "STR_SOLDIER"


def _wait_popup(gc, name, timeout=20):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = geo.top_state(gc)
        if name in last:
            return last
        time.sleep(0.3)
    raise AssertionError(f"{gc.name}: {name} never appeared (top={last!r})")


def _alive(gc):
    """True iff the instance is still responsive (survived the go-to-base)."""
    try:
        return bool(gc.cmd({"cmd": "ping"}).get("pong"))
    except (ConnectionError, OSError):
        return False


def _incoming_soldiers(gc):
    return gc.ok({"cmd": "incoming_transfers"}).get("soldiers", 0)


def _drive_goto_base(host, client, label):
    """Fire the real "Go to Base" handler on the client's arrival popup and assert
    it neither crashes nor no-ops, then return the client to the geoscape."""
    crashed = False
    try:
        r = client.cmd({"cmd": "items_arriving_goto"})
    except (ConnectionError, OSError) as e:
        crashed = True
        r = {"error": str(e)}

    if crashed or not _alive(client):
        raise AssertionError(
            f"CLIENT CRASHED [{label}] opening the base from the arrival popup "
            f"(null-base BasescapeState ctor deref): {r.get('error')}")

    assert r.get("ok"), f"[{label}] items_arriving_goto did not run: {r}"
    top = _wait_popup(client, "BasescapeState", timeout=10)
    print(f"PASS [{label}] no-crash: client survived and opened the base screen ({top})")

    # Back to the geoscape so the next scenario / world-equality check is clean.
    geo.drain_popups(client)
    try:
        client.cmd({"cmd": "close_screens"})
    except (ConnectionError, OSError):
        pass
    geo.drain_popups(host)


def scenario_hire_arrival(host, client):
    """The reported path end-to-end: HOST hires a soldier, it ARRIVES, the client
    opens the base from the arrival popup."""
    for gc in (host, client):
        geo.drain_popups(gc)

    r = host.ok({"cmd": "buy", "item": SOLDIER, "count": 1, "kind": "soldier"})
    assert r.get("sent"), f"host hire not sent: {r}"
    host.wait_for("host hire en route",
                  lambda: (_incoming_soldiers(host) == 1) or None, timeout=30, interval=0.5)
    client.wait_for("client hire en route",
                    lambda: (_incoming_soldiers(client) == 1) or None, timeout=30, interval=0.5)
    print("PASS hire: 1 soldier en route on both machines")

    # Advance past the personnel transfer time; stop the moment the arrival popup
    # appears (interest leaves it OPEN instead of auto-dismissing it).
    res = geo.skip_ingame_time(host, client, minutes=60 * 24 * 6, speed_idx=5,
                               interest=geo.popup("ItemsArrivingState"),
                               real_timeout=220)
    assert res["hit"], f"arrival popup never appeared while advancing time: {res}"
    _wait_popup(client, "ItemsArrivingState", timeout=20)
    print("PASS arrival: soldier arrived, ItemsArrivingState popped on the client")

    _drive_goto_base(host, client, "hire-arrival")


def scenario_alert(host, client):
    """Deterministic isolation of the null-_base popup: raise ItemsArrivingState on
    the client through the real hostAlert lane with a row whose base index is
    out of range, so the popup cannot resolve _base and "Go to Base" hits the
    null-base path that Fix A/B guard."""
    for gc in (host, client):
        geo.drain_popups(gc)

    host.ok({"cmd": "shared_alert", "cls": "ItemsArrivingState",
             "rows": [{"type": 0, "name": "Ghost Soldier", "qty": 1,
                       "base": "Nowhere", "baseIdx": 999, "ownerSeat": -1}]})
    _wait_popup(client, "ItemsArrivingState")
    print("PASS setup: arrival popup (unresolved base) reached the client via hostAlert")

    _drive_goto_base(host, client, "alert")


def main():
    js = shared_fixture.bring_up("jarrcrash", (48932, 48933, 48232))
    host, client = js.host, js.client
    try:
        scenario_hire_arrival(host, client)
        scenario_alert(host, client)
        js.finish()
        print("SHARED SOLDIER-ARRIVAL CRASH TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
