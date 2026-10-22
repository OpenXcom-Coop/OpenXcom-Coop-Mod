"""Separate campaign keeps faction-event score independent for different factions."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import separate_campaign_fixture as fixture


def profiles(peer):
    state = peer.ok({"cmd": "separate_profile_state"})
    return {player["name"]: player for player in state["players"]}


def main():
    js = fixture.bring_up("sep_faction_score", (49170, 49171, 48470))
    host = js.host
    try:
        host.ok({"cmd": "separate_profile_set", "player": "HostPlayer",
                 "faction": "difficulty:0", "factionScore": 125})
        host.ok({"cmd": "separate_profile_set", "player": "ClientPlayer",
                 "faction": "difficulty:3", "factionScore": -40})

        current = profiles(host)
        assert current["HostPlayer"]["factionScores"][-1] == 125, current
        assert current["ClientPlayer"]["factionScores"][-1] == -40, current

        roundtrip = host.ok({"cmd": "separate_profile_roundtrip"})
        restored = {player["name"]: player for player in roundtrip["players"]}
        assert restored["HostPlayer"]["factionScores"][-1] == 125, restored
        assert restored["ClientPlayer"]["factionScores"][-1] == -40, restored
        print("PASS Separate faction scores remain player-scoped and survive serialization")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
