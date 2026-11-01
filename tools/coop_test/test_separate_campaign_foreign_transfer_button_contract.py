"""Foreign Separate bases hide Transfer while own bases retain the button."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    source = (ROOT / "src/Basescape/BasescapeState.cpp").read_text(
        encoding="utf-8")
    access = source.split("void BasescapeState::updateBaseAccessButtons()", 1)[1]
    access = access.split("void BasescapeState::btnNewBaseClick", 1)[0]

    own_defaults, foreign = access.split("if (_base->_isForeignBase)", 1)
    assert "_btnTransfer->setVisible(true);" in own_defaults
    assert "_btnTransfer->setVisible(false);" in foreign

    print("PASS Separate Transfer is visible at own bases and hidden at foreign bases")


if __name__ == "__main__":
    main()
