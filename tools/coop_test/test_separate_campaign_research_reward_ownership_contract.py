"""Contract: private research side effects are fenced by player ownership."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    saved = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")
    event = (ROOT / "src/Geoscape/GeoscapeEventState.cpp").read_text(encoding="utf-8")
    econ = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")

    assert "!otherBase->isOwnedByPlayer(researchOwner)" in saved
    assert "t->setOwnerPlayerName(researchOwner);" in saved
    # Private research: the spawned event belongs to the research owner. Shared
    # research: the event has no owner and its rewards go to the player whose
    # base finished the research.
    assert "if (spawnEvent(spawnedEventRule, researchOwner) && !playerScoped && base && isSeparateCoopCampaign())" in saved
    assert "_geoscapeEvents.back()->setRewardPlayerName(base->getOwnerPlayerName());" in saved
    assert "!xbase->isOwnedByPlayer(_ownerPlayerName)" in event
    assert "candidate->isOwnedByPlayer(owner)" in econ
    print("PASS private research rewards, projects, events, and replica base are owner-scoped")


if __name__ == "__main__":
    main()
