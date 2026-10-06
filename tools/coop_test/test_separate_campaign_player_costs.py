"""Separate Base Info and Monthly Costs are scoped to the local player."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture


def main():
    js = fixture.bring_up("sep_player_costs", (48992, 48993, 48292))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)

        for gc, own_name, foreign_name in (
                (host, "HostBase", "ClientBase"),
                (client, "ClientBase", "HostBase")):
            own = gc.ok({"cmd": "base_report", "base": own_name})
            foreign = gc.ok({"cmd": "base_report", "base": foreign_name})

            # Fresh Separate bases have no soldier transfers. The displayed
            # roster and vanilla total therefore agree; focused contract
            # coverage below ensures BaseInfo uses residents once a transfer is
            # pending instead of displaying the reservation as a ninth soldier.
            assert own["residentSoldiers"] == own["totalSoldiers"], own
            assert own["localPlayerMaintenance"] == own["monthlyMaintenance"], (
                gc.name, own, foreign)
            assert own["localPlayerMaintenance"] != (
                own["monthlyMaintenance"] + foreign["monthlyMaintenance"]), (
                    "foreign base leaked into local Separate maintenance", gc.name,
                    own, foreign)

        host_month = host.ok({"cmd": "month_report"})
        client_month = client.ok({"cmd": "month_report"})
        assert (host_month["monthlyMaintenanceDisplay"]
                + client_month["monthlyMaintenanceDisplay"]
                == host_month["worldMaintenance"]), (host_month, client_month)
        assert host_month["worldMaintenance"] == client_month["worldMaintenance"], (
            host_month, client_month)

        print("PASS Separate player costs: Monthly Costs and Monthly Report show "
              "only each seat's bases, their sum equals world maintenance, and "
              "Base Info exposes resident soldiers")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
