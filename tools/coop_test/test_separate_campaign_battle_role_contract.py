"""Separate single-world battles use server role and the launching craft base."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    battle = (ROOT / "src/Battlescape/BattlescapeState.cpp").read_text(encoding="utf-8")
    landing = (ROOT / "src/Geoscape/ConfirmLandingState.cpp").read_text(encoding="utf-8")
    loader = (ROOT / "src/Menu/LoadGameState.cpp").read_text(encoding="utf-8")

    role = "isSharedCampaign()\n\t\t\t\t\t|| _game->getCoopMod()->isSeparateCampaign()"
    assert role in battle
    assert "setHost(_game->getCoopMod()->getServerOwner())" in battle
    assert "SeparateEcon::baseIndex(_game, _craft->getBase())" in landing
    assert "setSelectedBase(static_cast<size_t>(missionBase))" in landing
    assert "bgame->setBattleOwnerPlayerName(battleOwner)" in landing
    assert "u->getMission()->getOwnerPlayerName()" not in landing[
        landing.index("void ConfirmLandingState::startCoopMission"):
        landing.index("bgame->setBattleOwnerPlayerName(battleOwner)")]
    assert "getBattleOwnerPlayerName()" in loader
    assert "isOwnedByPlayer(battleOwner)" in loader
    assert '== "STR_BASE_DEFENSE" ? selected_base : nullptr' in loader
    assert "new BriefingState(0, briefingBase)" in loader
    print("PASS Separate battle role follows server authority and launching craft base")


if __name__ == "__main__":
    main()
