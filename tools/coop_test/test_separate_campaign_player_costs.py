"""Separate uses full income, local maintenance display, and no player bonus."""

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
        host_base = host.ok({"cmd": "base_report", "base": "HostBase"})
        client_base = client.ok({"cmd": "base_report", "base": "ClientBase"})
        player_count = 2
        expected_host_funds = ((host_month["countryFunding"]
                                - (host_base["monthlyMaintenance"]
                                   - host_base["personnelMaintenance"]))
                               // player_count)
        expected_client_funds = ((client_month["countryFunding"]
                                  - (client_base["monthlyMaintenance"]
                                     - client_base["personnelMaintenance"]))
                                 // player_count)
        assert host_month["funds"] == expected_host_funds, (host_month, host_base)
        assert client_month["funds"] == expected_client_funds, (client_month, client_base)
        assert host_month["playerFunds"] == client_month["playerFunds"], (
            "host and replica must persist every player wallet", host_month, client_month)
        assert host_month["playerFunds"]["HostPlayer"] == expected_host_funds
        assert host_month["playerFunds"]["ClientPlayer"] == expected_client_funds
        for report in (host_month, client_month):
            assert report["monthlyIncomeDisplay"] == report["countryFunding"], report
            assert "monthlyPlayerBonus" not in report, report
        assert host_month["worldMaintenance"] == client_month["worldMaintenance"], (
            host_month, client_month)
        assert (host_month["monthlyMaintenanceActual"]
                + client_month["monthlyMaintenanceActual"]
                == host_month["worldMaintenance"]), (host_month, client_month)
        for report in (host_month, client_month):
            assert report["monthlyMaintenanceDisplay"] == \
                report["monthlyMaintenanceActual"], report

        # A client purchase spends only the client's wallet, even when the host
        # validates it. Both replicas must persist the same pair of balances.
        before_wallets = dict(host_month["playerFunds"])
        client.ok({"cmd": "buy", "item": "STR_RIFLE", "count": 1,
                   "base": "ClientBase"})
        host.wait_for(
            "client purchase charged its own wallet",
            lambda: (lambda report: report
                     if report["playerFunds"]["ClientPlayer"]
                     < before_wallets["ClientPlayer"] else None)(
                         host.ok({"cmd": "month_report"})),
            timeout=30, interval=0.5)
        after_host = host.ok({"cmd": "month_report"})
        after_client = client.ok({"cmd": "month_report"})
        assert after_host["playerFunds"] == after_client["playerFunds"], (
            after_host, after_client)
        assert after_host["playerFunds"]["HostPlayer"] == \
            before_wallets["HostPlayer"], after_host
        assert after_host["playerFunds"]["ClientPlayer"] < \
            before_wallets["ClientPlayer"], after_host
        assert after_host["funds"] == before_wallets["HostPlayer"], after_host
        assert after_client["funds"] == \
            after_client["playerFunds"]["ClientPlayer"], after_client

        print("PASS Separate economy: undivided single-player income, local-player "
              "maintenance, private wallets, and player-count starting funds")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
