"""Contracts for owner-only Separate purchase and faction-event arrivals."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    transfer_h = source("src/Savegame/Transfer.h")
    transfer_cpp = source("src/Savegame/Transfer.cpp")
    arrivals = source("src/Geoscape/ItemsArrivingState.cpp")
    shared = source("src/CoopMod/SharedEcon.cpp")
    event = source("src/Geoscape/GeoscapeEventState.cpp")
    assert "_ownerPlayerName" in transfer_h
    assert 'writer.write("ownerPlayerName"' in transfer_cpp
    assert "showLocally" in arrivals and "getOwnerPlayerName" in arrivals
    assert "transferOwner = connectionTCP::seatName(seat)" in shared
    assert "setOwnerPlayerName(transferOwner)" in shared
    assert "setOwnerPlayerName(_ownerPlayerName)" in event
    print("PASS Separate owner-only purchase/event arrival contract")


if __name__ == "__main__":
    main()
