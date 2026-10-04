"""Shared Separate research must expose and consume prerequisites campaign-wide."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    saved = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")
    start = saved.index("void SavedGame::getAvailableResearchProjects")
    end = saved.index("void SavedGame::getNewlyAvailableResearchProjects", start)
    available = saved[start:end]

    assert "sharedSeparateResearch" in available
    assert "_separateCampaign.isResearchSharingEnabled()" in available
    assert "? _bases : std::vector<Base*>{base}" in available
    assert "researchBase->getStorageItems()->getItem" in available
    assert "researchBase->getProvidedBaseFunc" in available

    separate = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    consume = separate[separate.index("bool consumeSharedResearchItem("):]
    assert "isSeparateCampaign()" in consume
    assert "_enable_research_sync" in consume
    assert "for (Base* source : *save->getBases())" in consume
    assert "source->getStorageItems()->removeItem" in consume

    shared = (ROOT / "src/CoopMod/SharedEcon.cpp").read_text(encoding="utf-8")
    assert "SeparateEcon::consumeSharedResearchItem(game, base, rule)" in shared

    print("PASS Shared Separate research uses one campaign-wide prerequisite tree")


if __name__ == "__main__":
    main()
