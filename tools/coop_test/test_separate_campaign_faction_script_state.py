"""Different factions keep one-time events and script counters independent."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture


def player_map(response):
    return {player["name"]: player for player in response["players"]}


def main():
    js = fixture.bring_up("sep_faction_script_state", (49270, 49271, 48570))
    host = js.host
    try:
        host.ok({"cmd": "separate_profile_set", "player": "HostPlayer",
                 "faction": "difficulty:0", "generatedEvent": "STR_FACTION_EVENT",
                 "missionRun": "factionArc", "missionMarker": "factionMarker"})
        host.ok({"cmd": "separate_profile_set", "player": "ClientPlayer",
                 "faction": "difficulty:3"})

        players = player_map(host.ok({"cmd": "separate_profile_state"}))
        assert players["HostPlayer"]["generatedEvents"] == ["STR_FACTION_EVENT"], players
        assert players["HostPlayer"]["missionRuns"]["factionArc"] == 1, players
        assert players["HostPlayer"]["missionMarkers"]["factionMarker"] == 1, players
        assert players["ClientPlayer"].get("generatedEvents", []) == [], players
        assert players["ClientPlayer"].get("missionRuns", {}) == {}, players

        restored = player_map(host.ok({"cmd": "separate_profile_roundtrip"}))
        assert restored["HostPlayer"]["generatedEvents"] == ["STR_FACTION_EVENT"], restored
        assert restored["HostPlayer"]["missionRuns"]["factionArc"] == 1, restored
        assert restored["HostPlayer"]["missionMarkers"]["factionMarker"] == 1, restored
        assert restored["ClientPlayer"].get("generatedEvents", []) == [], restored
        print("PASS Separate faction script state is player-scoped and persistent")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
