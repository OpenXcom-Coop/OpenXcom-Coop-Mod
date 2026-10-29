"""Different factions keep one-time events and script counters independent."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
from test_separate_campaign_three_month_factions import (
    MOD_40K, MOD_ROSIGMA, require_mods)


def player_map(response):
    return {player["name"]: player for player in response["players"]}


def main():
    require_mods()
    js = shared_fixture.bring_up(
        "sep_rosigma_faction_script_state", (49270, 49271, 48570),
        mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=0, client_difficulty=3, transport="tcp")
    host = js.host
    try:
        host.ok({"cmd": "separate_profile_set", "player": "HostPlayer",
                 "generatedEvent": "STR_FACTION_EVENT",
                 "missionRun": "factionArc", "missionMarker": "factionMarker"})

        players = player_map(host.ok({"cmd": "separate_profile_state"}))
        assert "STR_FACTION_EVENT" in players["HostPlayer"]["generatedEvents"], players
        assert players["HostPlayer"]["missionRuns"]["factionArc"] == 1, players
        assert players["HostPlayer"]["missionMarkers"]["factionMarker"] == 1, players
        assert "STR_FACTION_EVENT" not in players["ClientPlayer"].get("generatedEvents", []), players
        assert "factionArc" not in players["ClientPlayer"].get("missionRuns", {}), players

        restored = player_map(host.ok({"cmd": "separate_profile_roundtrip"}))
        assert "STR_FACTION_EVENT" in restored["HostPlayer"]["generatedEvents"], restored
        assert restored["HostPlayer"]["missionRuns"]["factionArc"] == 1, restored
        assert restored["HostPlayer"]["missionMarkers"]["factionMarker"] == 1, restored
        assert "STR_FACTION_EVENT" not in restored["ClientPlayer"].get("generatedEvents", []), restored
        print("PASS ROSIGMA Separate faction script state is player-scoped and persistent")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
