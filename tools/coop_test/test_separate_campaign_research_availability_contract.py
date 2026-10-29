"""Research lists must use the base owner's completed tree in Separate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    src = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")
    start = src.index("void SavedGame::getAvailableResearchProjects")
    end = src.index("void SavedGame::getNewlyAvailableResearchProjects", start)
    body = src[start:end]

    assert "base->getOwnerPlayerName()" in body
    assert "_separateCampaign.getPlayer(researchOwner)" in body
    assert "player->completedResearch" in body
    assert "isResearchedForPlayer(topic, researchOwner" in body
    assert "discoverySources = _discovered" in body
    assert "hasPlayerGetOneFree" in body
    assert "hasPlayerProtectedUnlock" in body
    print("PASS Separate research availability uses the base owner's isolated research tree")


if __name__ == "__main__":
    main()
