"""Same-faction Separate players share faction mission access."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    econ = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    geo = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")
    us = (ROOT / "bin/common/Language/en-US.yml").read_text(encoding="utf-8")
    gb = (ROOT / "bin/common/Language/en-GB.yml").read_text(encoding="utf-8")

    owns = econ[econ.index("bool ownsMissionTarget("):]
    assert "!game->getSavedGame()->getSeparateCampaign().haveDifferentFactions()" in owns
    assert "return true;" in owns
    assert "&& save->getSeparateCampaign().haveDifferentFactions()" in geo
    assert 'STR_COOP_MISSION_BELONGS_TO_PLAYER: "This mission belongs to {0}."' in us
    assert 'STR_COOP_MISSION_BELONGS_TO_PLAYER: "This mission belongs to {0}."' in gb

    for filename in ("MultipleTargetsState.cpp", "MissionDetectedState.cpp", "UfoDetectedState.cpp"):
        source = (ROOT / "src/Geoscape" / filename).read_text(encoding="utf-8")
        assert "new CraftErrorState(" in source
        assert "new ErrorMessageState(" not in source

    print("PASS same-faction missions stay shared and foreign-owner errors use readable mission text")


if __name__ == "__main__":
    main()
