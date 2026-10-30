"""One real Separate month settles each private wallet like solo play."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture


def roll_one_month(host, client, old_month):
    host.ok({"cmd": "set_geo_day", "day": 28, "hour": 0})
    deadline = time.time() + 120
    while time.time() < deadline:
        for gc in (host, client):
            if gc.proc.poll() is not None:
                raise AssertionError(f"{gc.name} exited during month roll")
            geo.drain_popups(gc)
            if geo.on_geoscape(gc):
                gc.ok({"cmd": "geo_set_speed", "idx": 5})
        current = fixture.geo(host)["monthsPassed"]
        if current > old_month:
            client.wait_for(
                "client received month roll",
                lambda: fixture.geo(client)["monthsPassed"] >= current or None,
                timeout=30, interval=0.5)
            for gc in (host, client):
                geo.drain_popups(gc)
                if geo.on_geoscape(gc):
                    gc.ok({"cmd": "geo_set_speed", "idx": 0})
            return
        time.sleep(0.25)
    raise AssertionError("Separate month did not advance")


def main():
    js = fixture.bring_up("sep_private_funds_month", (49042, 49043, 48342))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        before_h = host.ok({"cmd": "month_report"})
        before_c = client.ok({"cmd": "month_report"})
        before = dict(before_h["playerFunds"])
        assert before == before_c["playerFunds"]
        maintenance = {
            "HostPlayer": before_h["monthlyMaintenanceActual"],
            "ClientPlayer": before_c["monthlyMaintenanceActual"],
        }
        # Vanilla settles the ending month with the funding that was in force
        # before country->newMonth updates the report for the coming month.
        settled_income = before_h["countryFunding"]

        roll_one_month(host, client, fixture.geo(host)["monthsPassed"])

        after_h = host.ok({"cmd": "month_report"})
        after_c = client.ok({"cmd": "month_report"})
        after = dict(after_h["playerFunds"])
        assert after == after_c["playerFunds"], (after_h, after_c)
        income = settled_income
        player_count = 2
        host_net = income - maintenance["HostPlayer"]
        client_net = income - maintenance["ClientPlayer"]
        host_delta = int(host_net / player_count)
        client_delta = int(client_net / player_count)
        assert after["HostPlayer"] == before["HostPlayer"] + host_delta, (
            before, after, income, maintenance)
        assert after["ClientPlayer"] == before["ClientPlayer"] + client_delta, (
            before, after, income, maintenance)
        assert after_h["monthlyPlayerCosts"] == host_net - host_delta, after_h
        assert after_c["monthlyPlayerCosts"] == client_net - client_delta, after_c
        assert after_h["funds"] == after["HostPlayer"], after_h
        assert after_c["funds"] == after["ClientPlayer"], after_c
        print("PASS Separate month: full income and own maintenance stay visible; "
              "Player Costs withholds the player-count share from Balance")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
