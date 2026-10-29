"""Source contract for faction-level final mission completion."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    header = read("src/CoopMod/SeparateEcon.h")
    separate = read("src/CoopMod/SeparateEcon.cpp")
    battle = read("src/Battlescape/BattlescapeState.cpp")
    geoscape = read("src/Geoscape/GeoscapeState.cpp")
    tcp = read("src/CoopMod/connectionTCP.cpp")
    test_server = read("src/CoopMod/TestServer.cpp")
    rosigma_test = read("tools/coop_test/test_separate_campaign_rosigma_faction_finales.py")

    assert "std::set<std::string> _completedFactions" in header
    assert 'tryRead("completedFactions", completedFactions)' in separate
    assert 'writer.write("completedFactions"' in separate
    assert 'tryRead("pendingFactionRechecks", _pendingFactionRechecks)' in separate
    assert 'writer.write("pendingFactionRechecks", _pendingFactionRechecks)' in separate
    assert "_completedFactions.insert(faction)" in separate
    assert "allPlayerFactionsCompleted" in separate
    assert "if (!victory) return true;" in separate
    assert "std::set<std::string> seenFactions" in separate
    assert "!seenFactions.insert(player->faction).second" in separate
    assert "resolveFactionFinalOutcome" in battle
    assert "partialFactionVictory" in battle
    # A partial faction victory opens the faction finale vote, which
    # names the faction, instead of a message box.
    assert "queueFactionFinaleVote(owner)" in battle
    vote = tcp.split("void connectionTCP::tryStartFactionFinaleVote()", 1)[1]
    vote = vote.split("\n}\n", 1)[0]
    assert "SeparateEcon::factionDisplayName(" in vote
    assert '"Vote NO to end with " + factionName' in vote
    assert "Continue the campaign to complete the remaining faction finales?" in vote
    assert '"STR_1_BEGINNER"' in separate
    assert '"STR_5_SUPERHUMAN"' in separate
    assert "SeparateEcon::allowsFactionScript(_game, ownerPlayerName)" in geoscape
    assert "isPlayerFactionCompleted(ownerPlayerName)" in separate
    assert "isPlayerFactionCompleted(name)" in separate
    assert "queueUnfinishedFactionRechecks" in separate
    assert 'resp["remainingOwnerSequence"].append(model.nextMissionOwner(names))' in test_server
    assert '"STR_FINAL_MISSION_MARINES"' in rosigma_test
    assert '"STR_MARS_CYDONIA_LANDING_ADEPTAS"' in rosigma_test
    assert '"action": "finish_victory"' in rosigma_test
    assert '"cmd": "separate_final_outcome"' not in rosigma_test
    assert 'session.has_state(gc, "GeoscapeState")' in rosigma_test
    print("PASS separate faction finales are persisted, gated, and campaign-safe")


if __name__ == "__main__":
    main()
