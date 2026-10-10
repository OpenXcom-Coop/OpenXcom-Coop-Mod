"""Old Separate saves migrate global discoveries to the host only."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    header = (ROOT / "src/CoopMod/SeparateEcon.h").read_text(encoding="utf-8")
    impl = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    saved = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")

    assert "migrateLegacyResearch" in header
    assert "playerNames.front()" in impl
    assert "addCompletedResearch(playerNames.front(), research)" in impl
    assert "addCompletedResearch(playerNames[1]" not in impl
    assert saved.count("migrateLegacyResearch(_coopPlayers, legacyResearch)") == 2
    assert "_campaignType == CoopCampaignType::Separate" in saved
    print("PASS legacy Separate research migrates once to the host profile only")


if __name__ == "__main__":
    main()
