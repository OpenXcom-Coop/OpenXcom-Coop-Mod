"""Separate Campaign: host-authoritative facility damage reaches the replica."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture


def facilities(gc, base_name):
    base = next(b for b in fixture.geo(gc)["bases"] if b["name"] == base_name)
    return sorted((f["type"], f["x"], f["y"], f.get("buildTime", 0))
                  for f in base["facilities"])


def main():
    js = fixture.bring_up("sep_fac_damage", (48974, 48975, 48274))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        before = facilities(host, "HostBase")
        assert facilities(client, "HostBase") == before

        damaged = host.ok({"cmd": "host_base_damaged",
                           "base": "HostBase", "count": 1})
        assert damaged["removed"] == 1, damaged
        host_after = facilities(host, "HostBase")
        assert host_after != before
        client.wait_for(
            "Separate facility damage replicated",
            lambda: facilities(client, "HostBase") == host_after or None,
            timeout=30, interval=0.3)
        assert len(host_after) == len(before) - 1
        for gc in (host, client):
            geo.drain_popups(gc)
        print("PASS Separate facility damage: host and client adopted the same layout")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
