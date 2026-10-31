"""Separate single-world battles use server role and the launching craft base."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    tcp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    landing = (ROOT / "src/Geoscape/ConfirmLandingState.cpp").read_text(encoding="utf-8")

    # The machine that serves the campaign runs every battle.
    assert "a.hostSim = connectionTCP::getServerOwner();" in tcp
    assert "SeparateEcon::baseIndex(_game, _craft->getBase())" in landing
    assert "setSelectedBase(static_cast<size_t>(missionBase))" in landing
    assert "bgame->setBattleOwnerPlayerName(battleOwner)" in landing
    assert "u->getMission()->getOwnerPlayerName()" not in landing[
        landing.index("void ConfirmLandingState::startCoopMission"):
        landing.index("bgame->setBattleOwnerPlayerName(battleOwner)")]
    # The client, which loads the battle's world (a fresh battle or a resumed one) starting on
    # its first base, selects the base of the player whose craft started the battle.
    entry = tcp.split("const bool sepGuestEntry", 1)[1].split("CoopIdMaps::rebuildFrom(battle);", 1)[0]
    assert "battle->getBattleOwnerPlayerName()" in entry
    assert "isOwnedByPlayer(battleOwner)" in entry
    assert "newSave->setSelectedBase(i);" in entry
    print("PASS Separate battle role follows server authority and launching craft base")


if __name__ == "__main__":
    main()
