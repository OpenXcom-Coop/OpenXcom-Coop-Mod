"""Separate mission ownership is persistent and inherited by mission sites."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    mission_h = (ROOT / "src/Savegame/AlienMission.h").read_text(encoding="utf-8")
    mission_cpp = (ROOT / "src/Savegame/AlienMission.cpp").read_text(encoding="utf-8")
    site_h = (ROOT / "src/Savegame/MissionSite.h").read_text(encoding="utf-8")
    site_cpp = (ROOT / "src/Savegame/MissionSite.cpp").read_text(encoding="utf-8")
    base_h = (ROOT / "src/Savegame/AlienBase.h").read_text(encoding="utf-8")
    base_cpp = (ROOT / "src/Savegame/AlienBase.cpp").read_text(encoding="utf-8")

    for source in (mission_h, site_h, base_h):
        assert "_ownerPlayerName" in source
        assert "getOwnerPlayerName()" in source
        assert "setOwnerPlayerName(" in source

    for source in (mission_cpp, site_cpp, base_cpp):
        assert 'tryRead("ownerPlayerName", _ownerPlayerName)' in source
        assert 'writer.write("ownerPlayerName", _ownerPlayerName)' in source
        assert "if (!_ownerPlayerName.empty())" in source

    assert "missionSite->setOwnerPlayerName(_ownerPlayerName)" in mission_cpp
    assert "ab->setOwnerPlayerName(_ownerPlayerName)" in mission_cpp

    geo = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")
    tcp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    assert 'ju["ownerPlayerName"] = ufo->getMission()->getOwnerPlayerName()' in geo
    assert 'jm["ownerPlayerName"] = site->getOwnerPlayerName()' in geo
    assert 'root["alienbases"][alienbase_index]["ownerPlayerName"] = alien_base->getOwnerPlayerName()' in geo
    assert 'mission->setOwnerPlayerName(ju.get("ownerPlayerName", "").asString())' in tcp
    assert 'site->setOwnerPlayerName(jm.get("ownerPlayerName", "").asString())' in tcp
    assert 'alienBase->setOwnerPlayerName(ownerPlayerName)' in tcp
    print("PASS Separate mission ownership survives saves and reaches sites and alien bases")


if __name__ == "__main__":
    main()
