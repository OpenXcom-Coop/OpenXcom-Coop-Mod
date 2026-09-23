"""Focused Separate regression: unified world, economy and global base cap."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture
from harness import LAND_LON, LAND_LAT


def main():
    js = fixture.bring_up("sep_core", (48946, 48947, 48246))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        hm = host.ok({"cmd": "month_report"})
        cm = client.ok({"cmd": "month_report"})
        assert hm["countryFunding"] == cm["countryFunding"]
        assert hm["monthlyIncomeDisplay"] + cm["monthlyIncomeDisplay"] \
            == hm["countryFunding"]

        for i in range(6):
            req = {"cmd": "add_base", "name": f"LimitBase{i}",
                   "lon": 0.4 + i * 0.05, "lat": 0.2,
                   "coopbaseid": 510000 + i,
                   "ownerPlayerName": "HostPlayer" if i % 2 == 0 else "ClientPlayer"}
            host.ok(req); client.ok(req)
        client.ok({"cmd": "shared_reset_stats"})
        client.ok({"cmd": "build_new_base", "lon": LAND_LON, "lat": LAND_LAT,
                   "name": "ForbiddenNinth", "liftX": 2, "liftY": 2})
        client.wait_for(
            "ninth base rejected",
            lambda: (client.ok({"cmd": "shared_stats"})["failCount"] >= 1) or None,
            timeout=30, interval=0.5)
        assert len(fixture.geo(host)["bases"]) == len(fixture.geo(client)["bases"]) == 8
        fixture.assert_same_world(host, client, "Separate core")
        print("PASS Separate core: unified world, income split and global base cap")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()

