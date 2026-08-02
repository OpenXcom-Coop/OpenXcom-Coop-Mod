"""Smoke test: a SHARED campaign brought up over the REAL UDP transport.

Validates the per-test transport selector (issue #124 groundwork): the coop
harness can now opt a test into the direct-LAN connectionUDP path on 127.0.0.1
(host_udp/join_udp), instead of the default TCP. Both machines must reach the
geoscape with one identical shared world, exactly as the TCP bring-up does -
proving the UDP background transport threads carry the full coop protocol.

Run:  python tools/coop_test/test_udp_bringup.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture


def _funds(gc):
    return gc.ok({"cmd": "geo_state"})["funds"]


def main():
    js = shared_fixture.bring_up("judp", (48960, 48961, 48260), transport="udp")
    host, client = js.host, js.client
    try:
        assert host.cmd({"cmd": "ping"}).get("pong"), "host unresponsive"
        assert client.cmd({"cmd": "ping"}).get("pong"), "client unresponsive"
        # bootstrap invariant: identical funds across the streamed shared world.
        host.wait_for("funds agree over UDP",
                      lambda: (_funds(host) == _funds(client)) or None,
                      timeout=30, interval=0.5)
        print(f"PASS UDP bring-up: both on geoscape, funds agree ({_funds(host)})")
        js.finish()
        print("UDP BRING-UP SMOKE TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
