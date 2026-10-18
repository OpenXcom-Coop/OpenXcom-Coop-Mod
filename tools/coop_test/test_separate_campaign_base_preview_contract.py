"""Regression contracts for Separate base-defense previews.

The access-lift preview is local UI, even during a connected campaign. It must
not inherit the real battlescape's host/client turn arbitration.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    state = source("src/Battlescape/BattlescapeState.cpp")
    game = source("src/Battlescape/BattlescapeGame.cpp")
    walk = source("src/Battlescape/UnitWalkBState.cpp")

    assert "setPlayerTurn(0);" in state
    assert "_battleGame->isYourTurn = 0;" in state
    assert "if (_save->isPreview())\n\t\treturn _save->getSelectedUnit() != 0 && allowButtons();" in state
    assert state.count("!_save->isPreview() && (_battleGame->isYourTurn == 1") >= 3
    assert "if (_save->isPreview() || !connectionTCP::parallelTurnActive())" in game
    assert "bool coopReplayDoor = !_parent->getSave()->isPreview()" in walk

    print("PASS Separate base preview bypasses network turn and ownership gates")


if __name__ == "__main__":
    main()
