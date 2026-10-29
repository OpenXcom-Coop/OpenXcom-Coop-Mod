#!/usr/bin/env python3
"""Static regression contract for Separate soldier equipment layouts.

Separate and Shared campaigns intentionally use the normal Soldier-owned
equipmentLayout.  A second player-profile layout would diverge after transfers,
save/load, or battle hand-off.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_separate_reuses_shared_soldier_layout_storage() -> None:
    soldier_h = read("src/Savegame/Soldier.h")
    soldier_cpp = read("src/Savegame/Soldier.cpp")
    inventory = read("src/Battlescape/InventoryState.cpp")
    generator = read("src/Battlescape/BattlescapeGenerator.cpp")
    separate_h = read("src/CoopMod/SeparateEcon.h")
    separate_cpp = read("src/CoopMod/SeparateEcon.cpp")

    assert "std::vector<EquipmentLayoutItem*> _equipmentLayout" in soldier_h
    assert 'writer.write("equipmentLayout", _equipmentLayout' in soldier_cpp
    assert 'reader["equipmentLayout"].children()' in soldier_cpp
    assert "bu->getGeoscapeSoldier()->getEquipmentLayout()" in inventory
    assert "unit->getGeoscapeSoldier()->getEquipmentLayout()" in generator

    # Never introduce a Separate profile copy: the Soldier is the one source of
    # truth, exactly as in Shared Campaign.
    assert "soldierLayouts" not in separate_h
    assert "soldierLayouts" not in separate_cpp
    assert "equipmentLayout" not in separate_h
    assert "equipmentLayout" not in separate_cpp


if __name__ == "__main__":
    test_separate_reuses_shared_soldier_layout_storage()
    print("PASS: Separate uses Shared's Soldier-owned equipment layout")
