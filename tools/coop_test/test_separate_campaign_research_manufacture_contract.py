"""Separate manufacture unlocks must use the base owner's research profile."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


def main():
    saved = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")

    available = function_body(
        saved,
        "void SavedGame::getAvailableProductions",
        "void SavedGame::getDependableManufacture",
    )
    dependable = function_body(
        saved,
        "void SavedGame::getDependableManufacture",
        "void SavedGame::getAvailableTransformations",
    )

    for body in (available, dependable):
        assert "CoopCampaignType::Separate" in body
        assert "base->getOwnerPlayerName()" in body
        assert "isResearchedForPlayer(requirement->getName(), researchOwner" in body
        assert "researchOwner.empty()" in body

    print("PASS Separate manufacture unlocks follow each base owner's research")


if __name__ == "__main__":
    main()
