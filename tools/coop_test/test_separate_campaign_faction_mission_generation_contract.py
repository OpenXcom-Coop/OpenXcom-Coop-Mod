"""Separate uses one rotating faction-aware host mission generator."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    con_h = (ROOT / "src/CoopMod/SeparateEcon.h").read_text(encoding="utf-8")
    con = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    geo = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")

    assert "_missionOwnerCursor" in con_h
    assert "nextMissionOwner" in con_h
    assert 'writer.write("missionOwnerCursor"' in con
    assert 'const std::string prefix = "difficulty:"' in con

    determine = geo[geo.index("void GeoscapeState::determineAlienMissions"):]
    determine = determine[:determine.index("bool GeoscapeState::attemptAlienRaceEvolution")]
    assert "nextMissionOwner(save->getCoopPlayers())" in determine
    assert "getFactionDifficulty(" in determine
    assert "isResearchedForPlayer(topic, missionOwner" in determine
    assert "bool factionRestricted = false" in determine
    assert "command->getMinDifficulty() > playerDifficulty" in determine
    assert "command->getMaxDifficulty() < playerDifficulty" in determine
    assert "isResearchedForPlayer(trigger.first, playerName" in determine
    assert "hasFactionResearch(" in determine

    tcp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    assert "setFactionResearch(" in tcp
    assert "coopFile->getDiscoveredResearch()" not in tcp  # captured through the shared helper
    assert "if (factionRestricted) commandOwner = missionOwner" in determine
    assert "processCommand(command, commandOwner)" in determine

    process = geo[geo.index("bool GeoscapeState::processCommand("):]
    assert "mission->setOwnerPlayerName(ownerPlayerName)" in process
    assert process.count("!xbase->isOwnedByPlayer(ownerPlayerName)") >= 2
    print("PASS Separate mission generation rotates one faction owner without multiplying the budget")


if __name__ == "__main__":
    main()
