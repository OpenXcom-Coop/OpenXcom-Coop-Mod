"""Foreign Separate bases keep Transfer, and its list offers only the visitor's soldiers."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    source = (ROOT / "src/Basescape/BasescapeState.cpp").read_text(
        encoding="utf-8")
    access = source.split("void BasescapeState::updateBaseAccessButtons()", 1)[1]
    access = access.split("void BasescapeState::btnNewBaseClick", 1)[0]

    own_defaults, foreign = access.split("if (_base->_isForeignBase)", 1)
    assert "_btnTransfer->setVisible(true);" in own_defaults
    assert "_btnTransfer->setVisible(_game->getCoopMod()->isSeparateCampaign());" in foreign

    transfer = (ROOT / "src/Basescape/TransferItemsState.cpp").read_text(
        encoding="utf-8")
    assert "const bool ownSoldiersOnly = _game->getCoopMod()->isSeparateCampaign()" in transfer
    for guard in ("if (_debriefingState || ownSoldiersOnly) break;",
                  "_debriefingState == 0 && !ownSoldiersOnly",
                  "if (qty > 0 && !ownSoldiersOnly)"):
        assert guard in transfer, guard

    print("PASS Separate Transfer is visible at foreign bases and lists only the visitor's soldiers")


if __name__ == "__main__":
    main()
