"""Static regression guard for Separate Campaign's global Soldier id space."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    econ_h = (ROOT / "src/CoopMod/SeparateEcon.h").read_text(encoding="utf-8")
    econ = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    tcp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    generator = (ROOT / "src/Battlescape/BattlescapeGenerator.cpp").read_text(
        encoding="utf-8")
    craft_h = (ROOT / "src/Savegame/Craft.h").read_text(encoding="utf-8")
    craft = (ROOT / "src/Savegame/Craft.cpp").read_text(encoding="utf-8")

    assert "int normalizeSoldierIds(Game* game);" in econ_h
    assert "save->getCampaignType() != CoopCampaignType::Separate" in econ
    assert "if (used.insert(oldId).second) continue;" in econ
    assert "while (reserved.count(nextId)) ++nextId;" in econ
    assert "soldier->setId(newId);" in econ
    assert 'ids["STR_SOLDIER"] = highestId + 1;' in econ
    assert "craft->remapPilotId(oldId, newId);" in econ
    assert "void remapPilotId(int oldId, int newId);" in craft_h
    assert "void Craft::remapPilotId(int oldId, int newId)" in craft
    assert "SeparateEcon::normalizeSoldierIds(_game);" in tcp
    assert "SeparateEcon::normalizeSoldierIds(_game);" in generator
    print("PASS Separate Soldier IDs: legacy/player-local collisions are upgraded "
          "before BattleUnit creation and pilot references follow the new id")


if __name__ == "__main__":
    main()
