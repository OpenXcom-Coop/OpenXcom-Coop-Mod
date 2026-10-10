"""Static contract for the player-scoped Separate campaign component."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    header = text("src/CoopMod/SeparateEcon.h")
    impl = text("src/CoopMod/SeparateEcon.cpp")
    saved_h = text("src/Savegame/SavedGame.h")
    saved_cpp = text("src/Savegame/SavedGame.cpp")
    cmake = text("src/CMakeLists.txt")

    assert "class CampaignData" in header
    assert "std::map<std::string, PlayerState> _players" in header
    assert "std::set<std::string> completedResearch" in header
    assert "std::vector<int64_t> funds" in header
    assert "ResearchOffer" not in header
    assert "std::string faction" in header
    assert "SeparateEcon::CampaignData _separateCampaign" in saved_h
    assert 'reader["separateCampaign"]' in saved_cpp
    assert 'writer["separateCampaign"]' in saved_cpp
    assert "migrateLegacyResearch(_coopPlayers, legacyResearch)" in saved_cpp
    assert "if (_loadedFromSave || playerNames.empty()" in impl
    assert 'writer.write("version", 3)' in impl
    assert 'playerReader.tryRead("funds", player.funds)' in impl
    assert 'playerWriter.write("funds", entry.second.funds)' in impl
    assert "CoopMod/SeparateCon.cpp" not in cmake
    assert "CoopMod/SeparateEcon.cpp" in cmake
    print("PASS SeparateEcon persists player faction, research and funds state and is in the build")


if __name__ == "__main__":
    main()
