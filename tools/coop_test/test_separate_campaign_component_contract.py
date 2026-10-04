"""Static contract for the player-scoped Separate campaign component."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    header = text("src/CoopMod/SeparateCon.h")
    impl = text("src/CoopMod/SeparateCon.cpp")
    saved_h = text("src/Savegame/SavedGame.h")
    saved_cpp = text("src/Savegame/SavedGame.cpp")
    cmake = text("src/CMakeLists.txt")

    assert "class SeparateCon" in header
    assert "std::map<std::string, PlayerState> _players" in header
    assert "std::set<std::string> completedResearch" in header
    assert "ResearchOffer" not in header
    assert "std::string faction" in header
    assert "SeparateCon _separateCampaign" in saved_h
    assert 'reader["separateCampaign"]' in saved_cpp
    assert 'writer["separateCampaign"]' in saved_cpp
    assert "migrateLegacyResearch(_coopPlayers, legacyResearch)" in saved_cpp
    assert "if (_loadedFromSave || playerNames.empty()" in impl
    assert 'writer.write("version", 3)' in impl
    assert "CoopMod/SeparateCon.cpp" in cmake
    assert "mission" not in header.lower() or "mission turn" in header.lower()
    print("PASS SeparateCon owns the simplified persisted player faction/research state and is in the build")


if __name__ == "__main__":
    main()
