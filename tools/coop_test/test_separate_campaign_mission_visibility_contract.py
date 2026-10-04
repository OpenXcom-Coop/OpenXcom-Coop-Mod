"""Separate mission markers are shared, but interaction is owner-scoped."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    econ = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    geo = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")
    dest = (ROOT / "src/Geoscape/SelectDestinationState.cpp").read_text(encoding="utf-8")
    owner = econ[econ.index("std::string missionTargetOwner("):]
    own = econ[econ.index("bool ownsMissionTarget("):]
    assert "ufo->getMission()->getOwnerPlayerName()" in owner
    assert "site->getOwnerPlayerName()" in owner
    assert "base->getOwnerPlayerName()" in owner
    assert "missionTargetOwner(target)" in own
    assert "if (owner.empty()) return true" in own
    assert "connectionTCP::seatName(connectionTCP::localSeat())" in own

    # Empty owner is not an error: generic scripts, ordinary UFOs and legacy
    # saves stay cooperative. Only faction-restricted scripts receive an owner.
    generator = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")
    assert "if (factionRestricted) commandOwner = missionOwner" in generator
    assert "processCommand(command, commandOwner)" in generator
    # Detection information is shared: neither local nor replicated popup paths
    # may suppress another faction's target.
    assert "SeparateEcon::ownsMissionTarget(_game, match)" not in geo
    assert "SeparateEcon::ownsMissionTarget(_game, site)" not in geo
    assert "SeparateEcon::ownsMissionTarget(_game, ufo)" not in geo
    assert "SeparateEcon::ownsMissionTarget(_game, msite)" not in geo
    assert "v.erase(std::remove_if" not in geo
    assert "SeparateEcon::ownsMissionTarget(_game, target)" not in dest

    targets = (ROOT / "src/Geoscape/MultipleTargetsState.cpp").read_text(encoding="utf-8")
    assert "if (!SeparateEcon::ownsMissionTarget(_game, target))" in targets
    assert 'tr("STR_COOP_MISSION_BELONGS_TO_PLAYER")' in targets
    assert "SeparateEcon::missionTargetOwner(target)" in targets
    assert "return;" in targets[targets.index("if (!SeparateEcon::ownsMissionTarget"):]

    for name, target in (("UfoDetectedState.cpp", "_ufo"), ("MissionDetectedState.cpp", "_mission")):
        popup = (ROOT / "src/Geoscape" / name).read_text(encoding="utf-8")
        intercept = popup[popup.index("btnInterceptClick"):]
        assert f"!SeparateEcon::ownsMissionTarget(_game, {target})" in intercept
        assert 'tr("STR_COOP_MISSION_BELONGS_TO_PLAYER")' in intercept
        assert f"SeparateEcon::missionTargetOwner({target})" in intercept
        assert "new InterceptState" in intercept

    landing = (ROOT / "src/Geoscape/ConfirmLandingState.cpp").read_text(encoding="utf-8")
    # Target ownership gates who may launch. Once accepted, the battle belongs
    # to the craft/base that actually launched it, including client craft starts.
    start = landing[landing.index("void ConfirmLandingState::startCoopMission"):]
    assert "_craft->getBase()->getOwnerPlayerName()" in start
    assert "u->getMission()->getOwnerPlayerName()" not in start[
        :start.index("bgame->setBattleOwnerPlayerName(battleOwner)")]
    assert "bgame->setBattleOwnerPlayerName(battleOwner)" in landing
    print("PASS Separate shares mission markers/popups but owner-scopes interaction")


if __name__ == "__main__":
    main()
