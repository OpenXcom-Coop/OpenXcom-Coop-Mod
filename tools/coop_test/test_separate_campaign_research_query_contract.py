"""Separate research queries must resolve through player/base ownership."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    header = (ROOT / "src/Savegame/SavedGame.h").read_text(encoding="utf-8")
    impl = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")

    assert "isResearchedForPlayer" in header
    assert "isResearchedForBase" in header
    assert "_campaignType != CoopCampaignType::Separate" in impl
    assert "_separateCampaign.hasCompletedResearch(playerName, research)" in impl
    assert "base->getOwnerPlayerName()" in impl
    print("PASS Separate research queries use player names and base ownership with non-Separate fallback")


if __name__ == "__main__":
    main()
