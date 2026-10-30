"""Faction target popups identify the owning player or a shared target."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    econ = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    assert "bool showMissionTargetOwner(Game* game)" in econ
    assert "isSeparateCampaign()" in econ
    assert "haveDifferentFactions()" in econ

    for filename in ("UfoDetectedState.cpp", "MissionDetectedState.cpp", "AlienBaseState.cpp"):
        popup = (ROOT / "src/Geoscape" / filename).read_text(encoding="utf-8")
        assert "SeparateEcon::showMissionTargetOwner(_game)" in popup
        assert "SeparateEcon::missionTargetOwner(" in popup
        assert 'tr("STR_COOP_MISSION_OWNER")' in popup
        assert 'tr("STR_COOP_SHARED")' in popup

    for language in ("en-US.yml", "en-GB.yml"):
        text = (ROOT / "bin/common/Language" / language).read_text(encoding="utf-8")
        assert 'STR_COOP_MISSION_OWNER: "Owner: {0}"' in text
        assert 'STR_COOP_SHARED: "Shared"' in text

    print("PASS Separate faction popups show player-name ownership or Shared")


if __name__ == "__main__":
    main()
