from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_faction_score_is_persisted_per_player():
    header = read("src/CoopMod/SeparateEcon.h")
    source = read("src/CoopMod/SeparateEcon.cpp")

    assert "std::vector<int> factionScores" in header
    assert 'tryRead("factionScores", player.factionScores)' in source
    assert 'write("factionScores", entry.second.factionScores)' in source


def test_only_different_factions_receive_private_event_score():
    event = read("src/Geoscape/GeoscapeEventState.cpp")

    assert "save->getSeparateCampaign().haveDifferentFactions()" in event
    assert "addFactionScore(_ownerPlayerName, rule.getPoints())" in event
    assert event.index("if (playerFactionScore)") < event.index("else if (regionRule)")


def test_faction_scripts_use_common_score_plus_owner_score():
    geoscape = read("src/Geoscape/GeoscapeState.cpp")

    assert "currentScore += save->getSeparateCampaign().getFactionScore(" in geoscape
    assert "missionOwner, scoreIndex" in geoscape
    assert "!missionOwner.empty() && save->getSeparateCampaign().haveDifferentFactions()" in geoscape


def test_same_faction_keeps_the_existing_common_score_path():
    event = read("src/Geoscape/GeoscapeEventState.cpp")
    geoscape = read("src/Geoscape/GeoscapeState.cpp")

    assert "else if (regionRule)" in event
    assert "save->addResearchScore(rule.getPoints())" in event
    assert "haveDifferentFactions()" in geoscape


def test_monthly_report_shows_only_the_local_effective_faction_score():
    report = read("src/Geoscape/MonthlyReportState.cpp")
    separate = read("src/CoopMod/SeparateEcon.cpp")

    assert "displayedRatingTotal += SeparateEcon::localFactionScore" in report
    assert 'arg(displayedRatingTotal).arg(rating)' in report
    assert "if (!campaign.haveDifferentFactions()) return 0;" in separate
    assert "getPerformanceBonus(_ratingTotal)" in report


def test_private_score_history_rolls_with_the_month():
    saved_game = read("src/Savegame/SavedGame.cpp")

    assert "newFactionScoreMonth(" in saved_game
    assert "std::min<size_t>(_researchScores.size(), 12)" in saved_game


def test_faction_mission_score_uses_target_owner_not_craft_owner():
    landing = read("src/Geoscape/ConfirmLandingState.cpp")
    battle_h = read("src/Savegame/SavedBattleGame.h")
    battle_cpp = read("src/Savegame/SavedBattleGame.cpp")
    debrief = read("src/Battlescape/DebriefingState.cpp")

    assert "setFactionScoreOwnerPlayerName(factionScoreOwner)" in landing
    assert "getFactionScoreOwnerPlayerName" in battle_h
    assert 'write("factionScoreOwnerPlayerName"' in battle_cpp
    assert "separate.addFactionScore(factionScoreOwner, total)" in debrief
    # The score block only: later code reads the battle owner for other things
    # (mission research credit, the success / failure event).
    score = debrief[debrief.index("// A faction-specific target"):]
    score = score[:score.index("// Resize (if needed)")]
    assert "getBattleOwnerPlayerName" not in score


if __name__ == "__main__":
    test_faction_score_is_persisted_per_player()
    test_only_different_factions_receive_private_event_score()
    test_faction_scripts_use_common_score_plus_owner_score()
    test_same_faction_keeps_the_existing_common_score_path()
    test_monthly_report_shows_only_the_local_effective_faction_score()
    test_private_score_history_rolls_with_the_month()
    test_faction_mission_score_uses_target_owner_not_craft_owner()
    print("separate campaign faction score contract: PASS")
