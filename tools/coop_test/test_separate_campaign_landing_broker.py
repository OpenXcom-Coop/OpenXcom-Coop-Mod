"""Separate Campaign: one player's landing answer never closes the other's prompt.

The host brokers every landing. In Separate the host holds no dialog copy for a
client craft, so the client's answer must only resolve the client's craft.

  1-2. Both transports reach their sites on the same host tick (the host's own
     dialog stops the host clock, so they must arrive together): the client's
     prompt opens on the client only, and the host's own prompt on the host.
  3. The client declines its landing. The host's prompt must stay open (it asks
     about a different craft) and still answer normally: after the host
     declines too, no landing is left pending, so neither craft is stranded.

Run:  py -3 tools/coop_test/test_separate_campaign_landing_broker.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture


def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def has(gc, name):
    return any(name in s for s in states(gc))


def pending(host):
    return host.ok({"cmd": "shared_landing_state"})["pending"]


def main():
    js = fixture.bring_up("sep_landing_broker", (49720, 49721, 49020))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        geo.slow_clock(host, client)

        fixture.fly_to_new_site(host, client, client, wait=False)
        fixture.fly_to_new_site(host, client, host, wait=False)

        def both_prompts():
            if has(host, "ConfirmLandingState") and has(client, "ConfirmLandingState"):
                return True
            for gc in (host, client):
                if geo.on_geoscape(gc):
                    gc.cmd({"cmd": "geo_set_speed", "idx": 2})
            return None

        host.wait_for("both landing prompts", both_prompts, timeout=90, interval=0.3)
        for gc in (host, client):
            gc.cmd({"cmd": "geo_set_speed", "idx": 0})
        assert sum("ConfirmLandingState" in s for s in states(host)) == 1, states(host)
        assert pending(host) is True
        print("PASS steps 1-2: each owner sees only its own landing prompt")

        client.ok({"cmd": "decline_landing"})
        time.sleep(3.0)
        assert has(host, "ConfirmLandingState"), (
            "the client's answer closed the host's prompt for a different craft",
            states(host))
        host.ok({"cmd": "decline_landing"})
        host.wait_for("no landing left pending",
                      lambda: (not pending(host)) or None, timeout=15, interval=0.5)
        print("PASS step 3: each answer resolves only its own craft; nothing stranded")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
