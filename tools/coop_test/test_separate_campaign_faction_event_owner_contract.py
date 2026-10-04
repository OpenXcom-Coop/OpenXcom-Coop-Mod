"""Faction-script events retain their player owner through save and rewards."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    event_h = source("src/Savegame/GeoscapeEvent.h")
    event_cpp = source("src/Savegame/GeoscapeEvent.cpp")
    saved = source("src/Savegame/SavedGame.cpp")
    geo = source("src/Geoscape/GeoscapeState.cpp")
    event_state = source("src/Geoscape/GeoscapeEventState.cpp")
    separate = source("src/CoopMod/SeparateEcon.cpp")
    assert "_ownerPlayerName" in event_h
    assert 'writer.write("ownerPlayerName"' in event_cpp
    assert "newEvent->setOwnerPlayerName(ownerPlayerName)" in saved
    assert "spawnEvent(eventRules, missionOwner)" in geo
    assert "isOwnedByPlayer(_ownerPlayerName)" in event_state
    assert 'msg["ownerPlayerName"] = ownerPlayerName' in separate
    print("PASS Separate faction-event owner/save/reward contract")


if __name__ == "__main__":
    main()
