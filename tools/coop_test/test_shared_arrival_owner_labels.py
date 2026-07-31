"""SHARED arrival popup shows OWNER-PREFIXED row labels on the peer machine.

When ordered personnel arrive in a SHARED campaign, the ItemsArrivingState popup
lists each incoming line item. The owner of the arrival sees a bare label
("Sergey Moronova"); every OTHER machine sees the same label prefixed with the
owner's player name ("[HostPlayer] Sergey Moronova"), so a player can tell whose
soldiers just landed in the shared base.

This drives the real end-to-end path: hire a soldier, advance the clock until the
arrival popup fires on both machines (leaving it open), then read the popup's
displayed row labels via the items_arriving_rows harness command and assert the
owner sees an unprefixed row while the peer sees the owner-prefixed form.

  Scenario A  HOST hires  -> host row bare, client row "[<host player>] ...".
  Scenario B  CLIENT hires -> client row bare, host row "[<client player>] ...".

The player names are read from the coopPlayers roster the command returns (seat 0
= host, seat 1 = client), never hardcoded.

Run:  python tools/coop_test/test_shared_arrival_owner_labels.py
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


def _incoming_soldiers(gc):
    return gc.ok({"cmd": "incoming_transfers"}).get("soldiers", 0)


def _rows(gc):
    """Read the arrival popup's displayed row labels + seat + roster."""
    return gc.ok({"cmd": "items_arriving_rows"})


def hire_and_wait(buyer, host, client):
    """Hire one soldier on `buyer`, advance the clock until the arrival popup fires
    on BOTH machines (leaving it open), and leave both sitting on it."""
    # Stop the world first: a prior scenario's skip_ingame_time leaves the clock at
    # speed 5 (one tick = a game day), so the hire + en-route wait would otherwise
    # race a free-running sim and the arrival could fire before the deliberate skip.
    geo.slow_clock(host, client)
    for gc in (host, client):
        geo.drain_popups(gc)

    r = buyer.ok({"cmd": "buy", "item": SOLDIER, "count": 1, "kind": "soldier"})
    assert r.get("sent"), f"{buyer.name} hire not sent: {r}"
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
    _wait_popup(host, "ItemsArrivingState", timeout=20)
    _wait_popup(client, "ItemsArrivingState", timeout=20)
    print("PASS arrival: ItemsArrivingState popped on both machines")


def scenario_host_hires(host, client):
    """HOST hires: the host (owner) sees a bare row; the client sees it prefixed
    with the host player's name."""
    hire_and_wait(host, host, client)

    h = _rows(host)
    assert h["ok"], f"host items_arriving_rows not ok: {h}"
    assert len(h["rows"]) == 1, f"host expected exactly 1 row: {h['rows']}"
    assert not h["rows"][0].startswith("["), \
        f"host owns the soldier, its row must be unprefixed: {h['rows'][0]!r}"

    c = _rows(client)
    assert len(c["rows"]) == 1, f"client expected exactly 1 row: {c['rows']}"
    host_owner_name = c["coopPlayers"][0]
    assert c["rows"][0].startswith("[" + host_owner_name + "] "), \
        f"client row not owner-prefixed for host: {c['rows'][0]!r} (owner {host_owner_name!r})"
    print(f"PASS host-hires: host row bare, client row '[{host_owner_name}] ...'")

    for gc in (host, client):
        geo.drain_popups(gc)


def scenario_client_hires(host, client):
    """CLIENT hires: the client (owner) sees a bare row; the host sees it prefixed
    with the client player's name."""
    hire_and_wait(client, host, client)

    c = _rows(client)
    assert len(c["rows"]) == 1, f"client expected exactly 1 row: {c['rows']}"
    assert not c["rows"][0].startswith("["), \
        f"client owns the soldier, its row must be unprefixed: {c['rows'][0]!r}"

    h = _rows(host)
    assert len(h["rows"]) == 1, f"host expected exactly 1 row: {h['rows']}"
    client_owner_name = h["coopPlayers"][1]
    assert h["rows"][0].startswith("[" + client_owner_name + "] "), \
        f"host row not owner-prefixed for client: {h['rows'][0]!r} (owner {client_owner_name!r})"
    print(f"PASS client-hires: client row bare, host row '[{client_owner_name}] ...'")

    for gc in (host, client):
        geo.drain_popups(gc)


def main():
    js = shared_fixture.bring_up("jarrlabel", (48934, 48935, 48234))
    host, client = js.host, js.client
    try:
        scenario_host_hires(host, client)
        scenario_client_hires(host, client)
        js.finish()
        print("SHARED ARRIVAL OWNER-LABEL TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
