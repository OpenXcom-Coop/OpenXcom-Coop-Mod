"""Static guards for Separate vehicle sync and deployment-inventory safety."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    equipment = (ROOT / "src/Basescape/CraftEquipmentState.cpp").read_text(
        encoding="utf-8")
    equipment_header = (ROOT / "src/Basescape/CraftEquipmentState.h").read_text(
        encoding="utf-8")
    shared = (ROOT / "src/CoopMod/SharedEcon.cpp").read_text(encoding="utf-8")
    separate = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(
        encoding="utf-8")
    separate_con = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(
        encoding="utf-8")
    battle = (ROOT / "src/Savegame/SavedBattleGame.cpp").read_text(encoding="utf-8")
    craft = (ROOT / "src/Savegame/Craft.cpp").read_text(encoding="utf-8")
    harness = (ROOT / "src/CoopMod/TestServer.cpp").read_text(encoding="utf-8")
    landing = (ROOT / "src/Geoscape/ConfirmLandingState.cpp").read_text(
        encoding="utf-8")

    submit = equipment.split("void CraftEquipmentState::submitSharedCraftEquip", 1)[1]
    submit = submit.split("void CraftEquipmentState::moveLeftByValue", 1)[0]
    assert "getVehicleCount" in submit
    assert "submitCraftEquip" in submit
    vehicle_gate = (
        "(!item->getVehicleUnit() || "
        "_game->getCoopMod()->isSeparateCampaign())"
    )
    assert equipment.count(vehicle_gate) >= 2
    assert equipment.count("SeparateEcon::vehicleSelectionCount") >= 3
    assert "physicalVehicleQty = c->getVehicleCount(itemType)" in equipment
    assert "physicalVehicleQty > 0" in equipment

    apply = separate.split("void applyVehicleEquip", 1)[1].split(
        "void submitCraftEquip", 1)[0]
    assert "item->getVehicleUnit()" in apply
    assert "validateAddingVehicles" in apply
    assert "new Vehicle(" in apply
    assert "vehicle->setOwnerPlayerName(playerName)" in apply
    assert "vehicle->setCoop(seat)" in apply
    assert "seat == ownerSeat" in apply
    assert "vehicle->setOwnerPlayerName(ownerPlayerName)" in apply
    assert "vehicle->setCoop(ownerSeat)" in apply
    assert "vehicle->getOwnerPlayerName() == playerName" in apply
    assert "validateAddingVehicles(size, seat)" in apply
    assert 'payload["vehicleOwners"] = owners' in apply
    assert "vehicleSelectionCount(game, craft" in apply
    assert "Only the base owner can change craft equipment" in separate
    assert 'playerReader["vehicleSelections"]' not in separate_con
    assert 'playerWriter["vehicleSelections"]' not in separate_con
    vehicle_h = read("src/Savegame/Vehicle.h")
    vehicle_cpp = read("src/Savegame/Vehicle.cpp")
    assert "std::string _ownerPlayerName" in vehicle_h
    assert 'reader.tryRead("ownerPlayerName", _ownerPlayerName)' in vehicle_cpp
    assert 'writer.write("ownerPlayerName", _ownerPlayerName)' in vehicle_cpp
    generator = read("src/Battlescape/BattlescapeGenerator.cpp")
    assert "SeparateEcon::synchronizeVehicleOwners(_game)" in generator
    tcp = read("src/CoopMod/connectionTCP.cpp")
    refresh = tcp.split("void connectionTCP::refreshSeparateBaseOwnership", 1)[1]
    assert "SeparateEcon::synchronizeVehicleOwners(_game)" in refresh
    # The landing stamps the craft's seats before the battle is generated: a Shared campaign's
    # vehicles go to the first seat, a Separate campaign's keep their owners' seats.
    assert "coopStampCraftSeats(_craft);" in landing
    stamp = read("src/CoopMod/CoopState.cpp").split("void coopStampCraftSeats(Craft* craft)", 1)[1]
    stamp = stamp.split("CoopDesyncNoticeState", 1)[0]
    separate_return = stamp.index("if (connectionTCP::isSeparateCampaignStatic())")
    assert "vehicle->setCoop(0);" in stamp[separate_return:]
    assert "unit->setCoopSeat((CoopSeat)v->getCoop());" in generator
    assert 'payload["count"] = vehicleSelectionCount' in apply
    # SharedEcon owns the common command registry only. Separate-specific
    # vehicle behavior must be delegated, while Shared keeps its old rejection.
    assert "SeparateEcon::validateCraftEquip" in shared
    assert "SeparateEcon::applyVehicleEquip" in shared
    # A Shared campaign routes a vehicle move through the same command; the host resolves the count.
    assert "void craftEquipVehicles(Json::Value& payload, Base* base, Craft* craft, const RuleItem* item)" in shared
    vehicle_capacity = craft.split("int Craft::validateAddingVehicles", 1)[1]
    assert "getSpaceUsedByOwner(ownerSeat)" in vehicle_capacity
    assert "vehicle->getOwnerPlayerName() == ownerPlayerName" in craft

    randomize = battle.split("void SavedBattleGame::randomizeItemLocations", 1)[1]
    randomize = randomize.split("void SavedBattleGame::deleteList", 1)[0]
    assert "if (!bi)" in randomize
    assert "erase(iter)" in randomize
    start = battle.split("void SavedBattleGame::startFirstTurn", 1)[1].split(
        "void SavedBattleGame::newTurnUpdateScripts", 1)[0]
    assert "std::remove(_items.begin(), _items.end(), nullptr)" in start
    new_turn = battle.split("void SavedBattleGame::newTurnUpdateScripts", 1)[1]
    assert "if (!item)" in new_turn
    assert "if (!getSelectedUnit())" in start
    assert 'act == "previous"' in harness
    assert 'resp["inventoryOpen"]' in harness
    assert 'cj["vehicles"]' in harness
    assert 'cj["vehicleOwners"]' in harness
    assert "SharedEcon::ScreenRefresh _sharedRefresh" in equipment_header
    assert "_sharedRefresh.consume()" in equipment
    assert "harnessDisplayedItem" in harness
    print("PASS Separate vehicle sync and inventory Previous crash guards")


if __name__ == "__main__":
    main()
