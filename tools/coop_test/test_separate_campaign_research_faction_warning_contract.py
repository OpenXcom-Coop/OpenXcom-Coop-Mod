"""Different factions offer a safe choice between private and shared research."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def main():
    con = (ROOT / "src/CoopMod/SeparateCon.cpp").read_text(encoding="utf-8")
    tcp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    coop = (ROOT / "src/CoopMod/CoopState.cpp").read_text(encoding="utf-8")
    warning = (ROOT / "src/CoopMod/SeparateResearchModeWarningState.cpp").read_text(encoding="utf-8")
    cmake = (ROOT / "src/CMakeLists.txt").read_text(encoding="utf-8")
    assert "haveDifferentFactions" in con
    assert "coopFile->getDifficulty()" in tcp
    assert "separate.setFaction(owner" in tcp
    assert "global_state == COOP_DLG_WAIT_BASES" in coop
    assert "Options::EnableResearchSync" in coop
    assert "SeparateResearchModeWarningState" in coop
    assert "You can change this later in Multiplayer Settings" in warning
    assert "Use Separate Research" in warning
    assert "Keep Shared Research" in warning
    assert "Options::EnableResearchSync = false" in warning
    assert "btnUseSeparateClick" in warning
    keep = warning[warning.index("void SeparateResearchModeWarningState::btnKeepSharedClick"):]
    assert "Options::EnableResearchSync = false" not in keep
    assert "SeparateResearchModeWarningState.cpp" in cmake
    print("PASS different factions can choose Separate Research or knowingly keep Shared Research")
if __name__ == "__main__": main()
