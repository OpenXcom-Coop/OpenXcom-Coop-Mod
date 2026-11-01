"""Regression guards for mod craft guns spawned as ownerless player units."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    game = read("src/Battlescape/BattlescapeGame.cpp")
    spawn = game.split("void BattlescapeGame::spawnNewUnit", 1)[1]
    spawn = spawn.split("void BattlescapeGame::spawnNewItem", 1)[0]
    assert "newUnit->setCoop(owner->getCoop())" in spawn
    assert "_save->getBattleOwnerPlayerName()" in spawn
    assert "connectionTCP::seatCoop(seat)" in spawn

    saved = read("src/Savegame/SavedBattleGame.cpp")
    assert "savedGame->isSeparateCoopCampaign()" in saved
    assert "savedGame->getCoopPlayers()" in saved
    assert "unit->isSummonedPlayerUnit()" in saved
    assert "!unit->getPreviousOwner()" in saved
    assert "unit->setCoop(battleOwnerSeat)" in saved

    selectable = read("src/Savegame/BattleUnit.cpp")
    assert "connectionTCP::isSeparateCampaignStatic()" in selectable
    assert "connectionTCP::unitSeat(this) != connectionTCP::localSeat()" in selectable

    print("PASS Separate mod craft turret ownership and save-upgrade guards")


if __name__ == "__main__":
    main()
