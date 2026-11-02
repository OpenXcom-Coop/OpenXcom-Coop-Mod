"""Regression guards for mod craft guns spawned as ownerless player units."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    game = read("src/Battlescape/BattlescapeGame.cpp")
    spawn = game.split("void BattlescapeGame::spawnNewUnit", 1)[1]
    spawn = spawn.split("void BattlescapeGame::spawnNewItem", 1)[0]
    assert "newUnit->setCoopSeat(owner->getCoopSeat())" in spawn
    assert "_save->getBattleOwnerPlayerName()" in spawn
    assert "newUnit->setCoopSeat((CoopSeat)seat)" in spawn

    saved = read("src/Savegame/SavedBattleGame.cpp")
    assert "savedGame->isSeparateCoopCampaign()" in saved
    assert "savedGame->getCoopPlayers()" in saved
    assert "unit->isSummonedPlayerUnit()" in saved
    assert "!unit->getPreviousOwner()" in saved
    assert "unit->setCoopSeat((CoopSeat)battleOwnerSeat)" in saved

    # A unit is selectable only by the seat that commands it.
    tcp = read("src/CoopMod/connectionTCP.cpp")
    may_select = tcp.split("bool coopMaySelectUnit(const BattleUnit* u)", 1)[1]
    may_select = may_select.split("\n}", 1)[0]
    assert "coopBattleAuthority().commandsUnit(u)" in may_select

    print("PASS Separate mod craft turret ownership and save-upgrade guards")


if __name__ == "__main__":
    main()
