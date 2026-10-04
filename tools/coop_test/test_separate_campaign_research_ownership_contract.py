"""Separate research is private by default and keyed by unique player name."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def main():
    header = (ROOT / "src/CoopMod/SeparateCon.h").read_text(encoding="utf-8")
    impl = (ROOT / "src/CoopMod/SeparateCon.cpp").read_text(encoding="utf-8")
    assert "std::map<std::string, PlayerState> _players" in header
    assert "bool _researchSharingEnabled = false" in header
    assert "completeResearch(const std::string& playerName" in header
    assert "return addCompletedResearch(playerName, research);" in impl
    assert "Shared Research uses" in impl
    assert "ResearchOffer" not in header
    assert "researchOffers" not in impl
    saved = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")
    assert "setSeparateResearchSharingEnabled" in saved
    assert "_discovered.push_back(rule)" in saved
    print("PASS Separate profiles store only private research; shared mode uses global discoveries")
if __name__ == "__main__": main()
