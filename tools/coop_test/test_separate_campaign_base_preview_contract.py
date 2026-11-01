"""Regression contracts for Separate base-defense previews.

The access-lift preview is local UI, even during a connected campaign. It must
not inherit the real battlescape's host/client turn arbitration: a preview
never offers a co-op battle, and every co-op battle gate needs an offered,
active battle.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    briefing = source("src/Battlescape/BriefingState.cpp")
    tcp = source("src/CoopMod/connectionTCP.cpp")

    ok = briefing.split("void BriefingState::btnOkClick", 1)[1]
    preview = ok.index("if (isPreview)")
    offer = ok.index("CoopHandshake::freezePreBattleEquip(_game)")
    assert preview < offer
    # The preview starts its first turn locally and returns before the co-op battle offer.
    assert "startFirstTurn();\n\t\t\treturn;" in ok[preview:offer].replace("\r\n", "\n")
    # Every co-op battle gate reads isCoopBattle(), which needs the offered battle to be active.
    assert ("bool isCoopBattle()\n{\n\treturn connectionTCP::getCoopStatic() "
            "&& coopBattleAuthority().phase == CoopBattlePhase::Active;") in tcp.replace("\r\n", "\n")

    print("PASS Separate base preview bypasses network turn and ownership gates")


if __name__ == "__main__":
    main()
