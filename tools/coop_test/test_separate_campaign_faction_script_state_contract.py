from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    header = (ROOT / "src/CoopMod/SeparateEcon.h").read_text(encoding="utf-8")
    econ = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    geoscape = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")
    saved = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")

    for field in ("generatedEvents", "missionRuns", "missionMarkers"):
        assert field in header and field in econ
    assert "eventGenerated(seqEvent)" in geoscape
    assert "eventGenerated(rngEvent)" in geoscape
    assert "missionRuns(command->getVarName())" in geoscape
    assert "itemObtained(triggerItem.first)" in geoscape
    assert "facilityBuilt(triggerFacility.first)" in geoscape
    assert "soldierHired(triggerSoldierType.first)" in geoscape
    assert "getPlayerFunds(missionOwner)" in geoscape
    assert "_separateCampaign.addGeneratedEvent(ownerPlayerName" in saved
    print("PASS Separate faction scripts use player-scoped progression inputs")


if __name__ == "__main__":
    main()
