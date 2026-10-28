"""Regression test: a base keeps counting the partner's guests after a base visit.

SEPARATE campaign. A soldier transferred to the partner's base stays in the
sender's roster (tagged with getCoopBase() = that base's id). The partner holds
no Soldier object for it and counts it in its living quarters through
Base::coop_guests, which it fills from the sender's guest census
(connectionTCP::sendGuestCensus). The census only goes on the wire when it
changes, and coop_guests is not saved.

A visit to the partner's base parks the visitor's own world and swaps in the
partner's; leaving reloads the own world from the parked copy, so every own
base comes back with coop_guests 0. The partner must therefore send its census
again; otherwise the returning player's base houses the partner's guests for
free until the partner's guest count next changes.

Setup: three soldiers transferred each way, so each own base houses three of
the partner's guests and has three of its own away. Every cell reads each own
base on BOTH machines (coopGuests, guestsAway, usedQuarters) and requires the
values from before the visit, waiting a bounded time for the census:

  client_visit_client_base  the client visited the host's base and left: the
                            client's base
  client_visit_host_base    same visit: the host's base (it was never reloaded)
  host_visit_host_base      the host visited the client's base and left: the
                            host's base
  host_visit_client_base    same visit: the client's base

All cells are checked and reported before the verdict.

Run:  python tools/coop_test/test_guest_census_after_visit.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_coop_transferred_equipment as T
from test_coop_quarters_accounting import free_soldier

GUESTS = 3
# Bound for the census to reach a base whose world was just reloaded. A census
# is a few frames' work on each machine; this is far above it even under load.
SETTLE_S = 10


def own_counts(gc, base_name):
    r = gc.ok({"cmd": "base_report", "base": base_name})
    assert not r["coopBaseFlag"], f"{gc.name}: {base_name} is not an own base: {r['coopBaseFlag']}"
    return {"coopGuests": r["coopGuests"], "guestsAway": r["guestsAway"],
            "usedQuarters": r["usedQuarters"]}


def station(sender, receiver, send_base, recv_base, label):
    """Transfer GUESTS soldiers from the sender's base to the receiver's base."""
    for n in range(1, GUESTS + 1):
        soldier = free_soldier(sender, send_base)
        tr = sender.ok({"cmd": "transfer_to_coop_base",
                        "name": soldier["name"], "toBase": recv_base})
        assert tr.get("transferred"), f"{label}: transfer {n} failed: {tr}"
        sender.wait_for(f"{label}: {n} soldier(s) away",
                        lambda n=n: own_counts(sender, send_base)["guestsAway"] == n or None,
                        timeout=30)
        receiver.wait_for(f"{label}: {n} guest(s) counted",
                          lambda n=n: own_counts(receiver, recv_base)["coopGuests"] == n or None,
                          timeout=45)
    print(f"{label}: {GUESTS} soldier(s) stationed at {recv_base}")


def visit_and_leave(visitor, peer_base, label):
    session.wait_peer_base_shown(visitor, peer_base)
    visitor.ok({"cmd": "visit_coop_base", "base": peer_base})
    visitor.wait_for(f"{label}: inside {peer_base}",
                     lambda: visitor.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None,
                     timeout=60)
    visitor.ok({"cmd": "leave_base"})
    session.wait_back_on_geoscape(visitor, f"{label}: back home")
    print(f"{label}: visited {peer_base} and left")


def check_cell(cell, gc, base_name, want, failures):
    seen = {}

    def same():
        seen.clear()
        seen.update(own_counts(gc, base_name))
        return seen == want or None

    t0 = time.monotonic()
    try:
        gc.wait_for(f"{cell}: {gc.name}'s {base_name} as before the visit", same, timeout=SETTLE_S)
        print(f"PASS {cell}: {gc.name}'s {base_name} {json.dumps(seen)} "
              f"({time.monotonic() - t0:.2f} s after the leave settled)")
    except TimeoutError:
        print(f"FAIL {cell}: {gc.name}'s {base_name} want {json.dumps(want)}, "
              f"still {json.dumps(seen)} after {SETTLE_S} s")
        failures.append(cell)


def main():
    host = GameClient("host", 47811, make_user_dir("host-user"))
    client = GameClient("client", 47812, make_user_dir("client-user"))
    failures = []
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        session.new_campaign(host, client)
        hb = T.own_base(host)["name"]
        cb = T.own_base(client)["name"]

        station(host, client, hb, cb, "host -> client")
        station(client, host, cb, hb, "client -> host")

        want_h = own_counts(host, hb)
        want_c = own_counts(client, cb)
        print(f"EVIDENCE before the visits: host {hb} {json.dumps(want_h)}, "
              f"client {cb} {json.dumps(want_c)}")
        for who, want in (("host", want_h), ("client", want_c)):
            assert want["coopGuests"] == GUESTS and want["guestsAway"] == GUESTS, (
                f"setup: the {who}'s base should house {GUESTS} guests and have {GUESTS} "
                f"soldiers away, got {want}")

        visit_and_leave(client, hb, "client visits the host's base")
        check_cell("client_visit_client_base", client, cb, want_c, failures)
        check_cell("client_visit_host_base", host, hb, want_h, failures)

        visit_and_leave(host, cb, "host visits the client's base")
        check_cell("host_visit_host_base", host, hb, want_h, failures)
        check_cell("host_visit_client_base", client, cb, want_c, failures)

        if failures:
            print(f"TEST FAILED: {len(failures)} cell(s): {', '.join(failures)}")
            sys.exit(1)
        print("TEST PASSED")
    finally:
        host.shutdown(); client.shutdown()


if __name__ == "__main__":
    main()
