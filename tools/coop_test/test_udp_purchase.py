"""SHARED economy over the REAL UDP transport (issue #124 groundwork).

Reported: on a "Private UDP connected" co-op session, the non-host client crashes
with heap corruption (0xC0000374 on a background thread) after a mission when it
purchases soldiers. The default TCP harness cannot exercise the UDP transport
threads, so this test opts into the direct-LAN UDP transport and hammers the
post-purchase path that the reporter hit.

Scenario A (cheap): a SHARED session over UDP, the client buys soldiers in rapid
bursts (each buy is a shared_cmd -> shared_apply round-trip over UDP, and drives
PONG/heartbeat traffic on the UDP background threads). Assert both machines stay
alive and the world stays consistent.

Run:  python tools/coop_test/test_udp_purchase_crash.py
Exit 0 = pass; 2 = the crash reproduced.
"""

import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture

SOLDIER = "STR_SOLDIER"


def _alive(gc):
    if gc.proc and gc.proc.poll() is not None:
        return False
    try:
        return bool(gc.cmd({"cmd": "ping"}).get("pong"))
    except (ConnectionError, OSError, socket.timeout):
        return False


def _funds(gc):
    return gc.ok({"cmd": "geo_state"})["funds"]


def _incoming_soldiers(gc):
    return gc.ok({"cmd": "incoming_transfers"}).get("soldiers", 0)


def main():
    js = shared_fixture.bring_up("judpbuy", (48962, 48963, 48262), transport="udp")
    host, client = js.host, js.client
    try:
        # keep funds topped up on BOTH (world checksum field) so buys never fail.
        for gc in (host, client):
            gc.ok({"cmd": "set_funds", "value": 900000000})

        ROUNDS, PER = 12, 8
        for r in range(1, ROUNDS + 1):
            for _ in range(PER):
                try:
                    client.ok({"cmd": "buy", "item": SOLDIER, "count": 1, "kind": "soldier"})
                except (ConnectionError, OSError, socket.timeout) as e:
                    raise AssertionError(
                        f"issue #124 REPRODUCED (client died mid-buy, round {r}): {e}")
            # let the shared_apply round-trips + UDP heartbeats churn.
            time.sleep(0.4)
            if not _alive(client):
                raise AssertionError(
                    f"issue #124 REPRODUCED: client crashed after buy burst round {r} "
                    f"(UDP background-thread heap corruption)")
            if not _alive(host):
                raise AssertionError(f"host crashed after buy burst round {r}")
            print(f"PASS round {r}/{ROUNDS}: {PER} soldier buys over UDP, both alive "
                  f"(incoming host={_incoming_soldiers(host)})")

        print("no crash from the plain UDP purchase burst")
        js.finish(timeout=90)
        print("SCENARIO A PASSED (no repro from purchase burst alone)")
    finally:
        js.shutdown()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"[REPRO] {e}")
        sys.exit(2)
