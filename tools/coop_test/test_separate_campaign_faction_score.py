"""Separate campaign keeps faction-event score independent for different factions."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import shared_fixture
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA


def profiles(peer):
    state = peer.ok({"cmd": "separate_profile_state"})
    return {player["name"]: player for player in state["players"]}


def main():
    js = shared_fixture.bring_up(
        "sep_rosigma_faction_score", (49170, 49171, 48470),
        mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=0, client_difficulty=3, transport="tcp")
    host = js.host
    try:
        host.ok({"cmd": "separate_profile_set", "player": "HostPlayer",
                 "factionScore": 125})
        host.ok({"cmd": "separate_profile_set", "player": "ClientPlayer",
                 "factionScore": -40})

        current = profiles(host)
        assert current["HostPlayer"]["factionScores"][-1] == 125, current
        assert current["ClientPlayer"]["factionScores"][-1] == -40, current

        roundtrip = host.ok({"cmd": "separate_profile_roundtrip"})
        restored = {player["name"]: player for player in roundtrip["players"]}
        assert restored["HostPlayer"]["factionScores"][-1] == 125, restored
        assert restored["ClientPlayer"]["factionScores"][-1] == -40, restored
        print("PASS ROSIGMA Separate faction scores remain player-scoped and survive serialization")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
