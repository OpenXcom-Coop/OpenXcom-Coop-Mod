"""Separate completion must remain owner-scoped and replicate by base ownership."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    saved = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")
    geo = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")
    shared = (ROOT / "src/CoopMod/SharedEcon.cpp").read_text(encoding="utf-8")

    start = saved.index("void SavedGame::addFinishedResearch(")
    end = saved.index("void SavedGame::addResearchDiaryEntry", start)
    body = saved[start:end]
    assert "base->getOwnerPlayerName()" in body
    assert "_separateCampaign.completeResearch(researchOwner" in body
    assert "_discovered.push_back(currentQueueItem)" in body
    assert "if (playerScoped)" in body
    assert "_separateCampaign.removeCompletedResearch" in body
    assert "selectGetOneFree(const RuleResearch* research, const Base* base)" in saved
    assert "selectGetOneFree(research, xbase)" in geo
    assert 'submitLocalCmd(game, "research_done", baseId, p)' in shared
    separate = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    complete = separate[separate.index("bool CampaignData::completeResearch("):]
    complete = complete[:complete.index("bool CampaignData::hasCompletedResearch")]
    assert "return addCompletedResearch(playerName, research);" in complete
    assert "applySharedResearchCompletion" not in shared
    print("PASS Separate completion is base-owner scoped and uses the replicated completion path")


if __name__ == "__main__":
    main()
