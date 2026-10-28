"""Different-faction finales remain faction-scoped until every faction wins."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA


END_NONE = 0
END_WIN = 1
END_LOSE = 2


def bring_up(tag, ports):
    return shared_fixture.bring_up(
        tag, ports, mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=0, client_difficulty=3, transport="tcp")


def test_loss_is_campaign_wide():
    js = bring_up("sep_rosigma_finale_loss", (49470, 49471, 48770))
    try:
        result = js.host.ok({"cmd": "separate_final_outcome",
                             "owner": "HostPlayer", "victory": False})
        assert result["globalEnding"] is True, result
        assert result["ending"] == END_LOSE, result
        assert not result.get("completedFactions"), result
        print("PASS faction finale loss keeps the campaign-wide defeat")
    finally:
        js.shutdown()


def test_wins_wait_for_every_distinct_faction():
    js = bring_up("sep_rosigma_finale_wins", (49480, 49481, 48780))
    try:
        first = js.host.ok({"cmd": "separate_final_outcome",
                            "owner": "HostPlayer", "victory": True})
        assert first["globalEnding"] is False, first
        assert first["ending"] == END_NONE, first
        assert first["showFactionVictoryNotice"] is True, first
        assert first["completedFactions"] == ["difficulty:0"], first
        assert first["nextMissionOwner"] == "ClientPlayer", first
        assert first["pendingFactionRechecks"] == ["ClientPlayer"], first

        roundtrip = js.host.ok({"cmd": "separate_profile_roundtrip"})
        assert roundtrip["completedFactions"] == ["difficulty:0"], roundtrip
        assert roundtrip["pendingFactionRechecks"] == ["ClientPlayer"], roundtrip

        second = js.host.ok({"cmd": "separate_final_outcome",
                             "owner": "ClientPlayer", "victory": True})
        assert second["globalEnding"] is True, second
        assert second["ending"] == END_WIN, second
        assert second["showFactionVictoryNotice"] is False, second
        assert set(second["completedFactions"]) == {
            "difficulty:0", "difficulty:3"
        }, second
        print("PASS only the last distinct faction victory ends the campaign")
    finally:
        js.shutdown()


def test_duplicate_faction_needs_one_finale():
    js = bring_up("sep_rosigma_finale_duplicate", (49490, 49491, 48790))
    try:
        one_b = js.host.ok({
            "cmd": "separate_faction_completion_model",
            "factions": ["faction:A", "faction:B", "faction:B"],
            "winners": [1],
        })
        assert one_b["allCompleted"] is False, one_b
        assert one_b["completedFactions"] == ["faction:B"], one_b
        assert one_b["ownerSequence"] == [
            "Player1", "Player2", "Player1", "Player2"
        ], one_b
        assert one_b["remainingOwnerSequence"] == [
            "Player1", "Player1", "Player1", "Player1"
        ], one_b

        b_and_a = js.host.ok({
            "cmd": "separate_faction_completion_model",
            "factions": ["faction:A", "faction:B", "faction:B"],
            "winners": [1, 0],
        })
        assert b_and_a["allCompleted"] is True, b_and_a
        assert set(b_and_a["completedFactions"]) == {
            "faction:A", "faction:B"
        }, b_and_a
        assert b_and_a["remainingOwnerSequence"] == ["", "", "", ""], b_and_a
        print("PASS two players sharing faction B require only one B finale")
    finally:
        js.shutdown()


def main():
    test_loss_is_campaign_wide()
    test_wins_wait_for_every_distinct_faction()
    test_duplicate_faction_needs_one_finale()


if __name__ == "__main__":
    main()
