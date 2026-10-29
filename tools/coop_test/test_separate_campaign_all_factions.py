"""ROSIGMA Separate Campaign: exercise every difficulty/faction over 3 months.

Three two-player campaigns cover difficulties 0..4 without synthesizing any
missions. The normal ROSIGMA scripts generate every observed strategic target.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
from test_separate_campaign_three_month_factions import (
    MOD_40K, MOD_ROSIGMA, owner_summary, roll_one_month, snapshot)


PAIRS = ((0, 1), (2, 3), (4, 0))


def run_pair(host_difficulty, client_difficulty, index):
    js = shared_fixture.bring_up(
        f"sep_40k_factions_{host_difficulty}_{client_difficulty}",
        (49010 + index * 3, 49011 + index * 3, 48310 + index),
        mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=host_difficulty, client_difficulty=client_difficulty,
        transport="tcp")
    try:
        host, client = js.host, js.client
        host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": False})
        host.ok({"cmd": "set_seed", "seed": 41000 + index})
        client.ok({"cmd": "set_seed", "seed": 41000 + index})
        initial = snapshot(host)
        factions = {p["name"]: p["faction"] for p in initial["players"]}
        assert factions.get("HostPlayer") == f"difficulty:{host_difficulty}", factions
        assert factions.get("ClientPlayer") == f"difficulty:{client_difficulty}", factions
        research = {
            "HostPlayer": set(host.ok({"cmd": "available_research", "base": "HostBase"})["topics"]),
            "ClientPlayer": set(client.ok({"cmd": "available_research", "base": "ClientBase"})["topics"]),
        }
        assert research["HostPlayer"], research
        assert research["ClientPlayer"], research
        forbidden = ("MONTHLY_SCORE", "SEARCHED_THE_GAME", "IMPOSSIBLE")
        assert not any(any(marker in topic for marker in forbidden)
                       for topics in research.values() for topic in topics), research

        month = initial["monthsPassed"]
        owners = set(owner_summary(initial))
        for _ in range(3):
            month = roll_one_month(host, client, month)
            state = snapshot(host)
            assert state["ending"] == 0, state
            assert snapshot(client)["monthsPassed"] == month
            owners.update(owner_summary(state))
        assert owners, "ROSIGMA produced no strategic targets in three months"
        print(f"PASS factions {host_difficulty}/{client_difficulty}: "
              f"3 months, owners={sorted(owners)}")
    finally:
        js.shutdown()


def main():
    for path in (MOD_40K, MOD_ROSIGMA):
        if not os.path.isdir(path):
            raise SystemExit(f"required mod directory not found: {path}")
    for index, pair in enumerate(PAIRS):
        run_pair(pair[0], pair[1], index)
    print("PASS all ROSIGMA faction difficulties 0..4")


if __name__ == "__main__":
    main()
