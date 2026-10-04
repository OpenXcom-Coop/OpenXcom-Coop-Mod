"""ROSIGMA Separate: identical factions receive identical starting trees."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA, snapshot


def main():
    for path in (MOD_40K, MOD_ROSIGMA):
        if not os.path.isdir(path):
            raise SystemExit(f"required mod directory not found: {path}")
    js = shared_fixture.bring_up(
        "sep_40k_same_faction_research", (49040, 49041, 48340),
        mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=0, client_difficulty=0, transport="tcp")
    try:
        js.host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": False})
        state = snapshot(js.host)
        players = {p["name"]: p for p in state["players"]}
        assert players["HostPlayer"]["faction"] == "difficulty:0", players
        assert players["ClientPlayer"]["faction"] == "difficulty:0", players
        host = set(js.host.ok({"cmd": "available_research", "base": "HostBase"})["topics"])
        client = set(js.client.ok({"cmd": "available_research", "base": "ClientBase"})["topics"])
        assert host, "host research menu unexpectedly empty"
        assert client == host, {"host": sorted(host), "client": sorted(client)}
        assert any("STRATEGY" in topic for topic in client), sorted(client)
        forbidden = ("MONTHLY_SCORE", "SEARCHED_THE_GAME", "IMPOSSIBLE")
        assert not any(any(marker in topic for marker in forbidden) for topic in client), sorted(client)
        print("PASS same-faction ROSIGMA Separate profiles start with identical research trees")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
