"""Private Separate research rewards stay with the researching player."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA


def main():
    js = shared_fixture.bring_up(
        "sep_private_research_rewards", (49044, 49045, 48344),
        mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=0, client_difficulty=1, transport="tcp")
    try:
        js.host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": False})
        client_before = set(js.host.ok(
            {"cmd": "available_research", "base": "ClientBase"})["topics"])

        result = js.host.ok(
            {"cmd": "separate_research_side_effects", "base": "HostBase"})
        assert result["baseOwnerPlayerName"] == "HostPlayer", result
        assert result["transfers"], (
            "ROSIGMA probe research did not create its configured item reward", result)
        assert all(row["ownerPlayerName"] == "HostPlayer"
                   for row in result["transfers"]), result

        client_after = set(js.host.ok(
            {"cmd": "available_research", "base": "ClientBase"})["topics"])
        assert client_after == client_before, {
            "topic": result["topic"],
            "removed": sorted(client_before - client_after),
            "added": sorted(client_after - client_before),
        }
        print("PASS private research reward and tree changes remain owner-scoped")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
