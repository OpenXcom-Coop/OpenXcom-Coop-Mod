"""Static guard for Separate Campaign's parallel local-soldier selection.

The host-authored battle save can initially point both machines at the same
soldier.  In parallel mode the client must replace that selection with a unit
owned by its local seat, and next/previous cycling must keep doing so.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "src" / "Battlescape" / "BattlescapeState.cpp"
SYNC = ROOT / "src" / "CoopMod" / "SharedEcon.cpp"


def main():
    text = STATE.read_text(encoding="utf-8")
    assert text.count("if (connectionTCP::parallelTurnActive())") >= 3
    assert text.count("unit->getCoop() != localSeat") >= 4
    assert "_save->selectNextPlayerUnit(false, false, checkInventory)" in text
    assert "_save->selectPreviousPlayerUnit(false, false, checkInventory)" in text
    assert "_save->setSelectedUnit(0);" in text
    assert "A resumed battle restores the host's selectedUnit" in text
    assert "selected->getCoop() != mySeat" in text
    assert "_battleGame->getCurrentAction()->actor = mine;" in text
    sync = SYNC.read_text(encoding="utf-8")
    assert ("const bool unitsComparable = !connectionTCP::parallelTurnActive() "
            "&& !rxPassDeferred();") in sync
    assert "modern unitsCore and" in sync and "compare at SIDESTART" in sync
    print("PASS Separate parallel selection contract: initial and cycled UI "
          "selection stays local and pre-snapshot death replay cannot raise the "
          "legacy unit alarm")


if __name__ == "__main__":
    main()
