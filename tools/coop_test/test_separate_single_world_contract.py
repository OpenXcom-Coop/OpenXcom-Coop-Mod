"""Static harness contract for the schema-3 SEPARATE single-world campaign.

This test intentionally needs no freshly compiled executable.  The live campaign
test exercises the same landing broker after a build; this guard makes the source
contract fail immediately if SEPARATE is accidentally routed back through the
legacy blob merge or host-role handoff.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    tcp = source("src/CoopMod/connectionTCP.cpp")
    tcp_header = source("src/CoopMod/connectionTCP.h")
    coop_state = source("src/CoopMod/CoopState.cpp")
    landing = source("src/Geoscape/ConfirmLandingState.cpp")
    geo = source("src/Geoscape/GeoscapeState.cpp")
    econ = source("src/CoopMod/SharedEcon.cpp")
    separate = source("src/CoopMod/SeparateEcon.cpp")
    battle = source("src/Savegame/SavedBattleGame.cpp")
    save = source("src/Savegame/SavedGame.cpp")
    basescape = source("src/Basescape/BasescapeState.cpp")
    craft_info = source("src/Basescape/CraftInfoState.cpp")
    craft = source("src/Savegame/Craft.cpp")
    cmake = source("src/CMakeLists.txt")
    save_ui = source("src/Menu/SaveGameState.cpp")

    assert "bool connectionTCP::isSeparateCampaign()" in tcp
    assert "bool isSeparateCampaign();" in tcp_header
    assert "isSingleWorld" + "Campaign()" not in tcp
    assert "isSingleWorld" + "Campaign();" not in tcp_header
    assert "!isSharedCampaign()" in tcp
    assert "solo games, PvP/custom battles" in tcp
    set_client = tcp.split("void connectionTCP::setClientSoldiers()", 1)[1]
    set_client = set_client.split("void connectionTCP::deleteAllCoopBases()", 1)[0]
    assert "if ((isSharedCampaign() || isSeparateCampaign()))" in set_client
    assert "loadWorld()" in set_client  # legacy path remains only after the guard

    yes = landing.split("void ConfirmLandingState::btnYesClick", 1)[1]
    yes = yes.split("void ConfirmLandingState::startCoopMission", 1)[0]
    single = yes.split("if ((_game->getCoopMod()->isSharedCampaign() || _game->getCoopMod()->isSeparateCampaign()))", 1)[1]
    single = single.split("if (_game->getCoopMod()->getHost()", 1)[0]
    assert "startCoopMission();" in single
    assert 'root["state"] = "changeHost"' not in single

    broker = geo.split("bool GeoscapeState::brokerSharedLanding", 1)[1]
    broker = broker.split("void GeoscapeState::sharedLandingReply", 1)[0]
    assert "isSharedCampaign()" in broker
    assert "isSeparateCampaign()" in broker
    assert "getServerOwner()" in broker

    assert 'state == "separate_land_prompt"' in separate
    assert 'state == "separate_land_reply"' in separate
    assert 'state == "separate_land_close"' in separate
    assert '"shared_cmd"' not in separate and '"shared_apply"' not in separate

    # Separate has its own public protocol names even though the validated
    # command registry/applier is deliberately shared as an internal engine.
    assert 'state == "shared_cmd" || state == "separate_cmd"' in econ
    assert 'state == "shared_apply" || state == "separate_apply"' in econ
    assert 'pc.separateProtocol ? "separate_fail" : "shared_fail"' in econ
    assert 'pc.separateProtocol ? "separate_apply" : "shared_apply"' in econ
    assert 'pc.separateProtocol ? "separate_ok" : "shared_ok"' in econ

    # The common command engine delegates Separate's foreign-base policy to the
    # Separate module; the policy itself must not spread through SharedEcon.
    ownership = econ.split("Schema-3 SEPARATE policy", 1)[1]
    ownership = ownership.split("int64_t cost", 1)[0]
    assert "base->isOwnedByPlayer(playerName)" in ownership
    assert "SeparateEcon::allowsForeignBaseCommand" in ownership
    assert 'pc.cmd == "fac_build"' not in ownership
    separate_policy = separate.split("bool allowsForeignBaseCommand", 1)[1].split(
        "bool validateCraftAssign", 1)[0]
    assert 'cmd == "buy"' in separate_policy
    assert 'cmd == "craft_equip"' in separate_policy
    assert 'cmd == "craft_rearm"' in separate_policy
    assert 'cmd == "craft_assign"' in separate_policy
    assert 'cmd == "transfer_arrived"' in separate_policy
    assert "!remote" in separate_policy
    assert "save->getBases()->size() >= 8" in econ
    assert "getBases()->size() < MiniBaseView::MAX_BASES" in basescape
    assert "SharedEcon::ownsSoldier(_game, soldier)" in craft_info
    separate_capacity = craft.split("if (connectionTCP::isSeparateCampaignStatic())", 1)[1]
    separate_capacity = separate_capacity.split("// coop", 1)[0]
    assert "getMaxUnitsClamped() / 2" in separate_capacity
    assert "getSpaceUsedByOwner(connectionTCP::localSeat())" in separate_capacity
    separate_validation = separate.split("bool validateCraftAssign", 1)[1].split(
        "void submitCraftEquip", 1)[0]
    assert "getMaxUnitsClamped() / 2" in separate_validation
    assert "getSpaceUsedByOwner(seat)" in separate_validation
    assert "soldier->getOwnerPlayerId() != seat" in separate_validation
    separate_assign = separate.split("void submitCraftAssign", 1)[1].split(
        "void submitSoldierArmor", 1)[0]
    assert 'p["onOff"] = onOff' in separate_assign
    assert 'p["soldierOwner"] = soldier->getOwnerPlayerId()' in separate_assign
    assert "CoopMod/SeparateEcon.cpp" in cmake
    assert "Savegame/Upgrade/SchemaStep2to3.cpp" in cmake

    legacy_gate = tcp.split("legacyWorldPackets =", 1)[1]
    legacy_gate = legacy_gate.split("};", 1)[0]
    for packet in ("coopBase", "coopBase2", "coopBase3", "baseRequest",
                   "sendProgressSaveRequest", "SEND_FILE_HOST_SAVE_PROGRESS",
                   "sendCraft", "changeHost"):
        assert f'"{packet}"' in legacy_gate
    for removed_packet in ("SEND_FILE_HOST_BASE", "SEND_FILE_CLIENT_BASE",
                           "MAP_RESULT_CLIENT_BASE", "MAP_RESULT_HOST_BASE"):
        assert removed_packet not in tcp
    assert '"basehost"' not in tcp
    assert "sendFileBase" not in tcp
    assert "sendBaseFile" not in tcp
    assert "hostBlobKey" not in tcp and "clientBlobKey" not in tcp
    assert "authoritative_campaign_world" in tcp
    assert "initialSeparateBootstrap" in tcp
    assert "getMonthsPassed() == -1" in tcp
    assert "bootstrapProgressPacket" in tcp
    assert "void connectionTCP::sendInitialSeparateBaseToHost()" in tcp
    assert '"separate_initial_base_transfer"' in tcp
    assert "campaignBootstrap ? !base->_coopIcon : !base->_coopBase" in tcp
    assert "base->_coopBase = !base->isOwnedByPlayer(" in tcp
    assert "sendInitialSeparateBaseToHost();" in source("src/Geoscape/BaseNameState.cpp")
    assert "!(_game->getCoopMod()->isSharedCampaign() || _game->getCoopMod()->isSeparateCampaign())" in save_ui

    soldier = source("src/Savegame/Soldier.cpp")
    assert "base->_coopBase == true && base->getOwnerPlayerName().empty()" in soldier
    assert "coop->isSharedCampaign() || coop->isSeparateCampaign()" in econ
    separate_ownership = tcp.split("void connectionTCP::refreshSeparateBaseOwnership", 1)[1]
    separate_ownership = separate_ownership.split("void connectionTCP::setCoopCampaign", 1)[0]
    assert "soldier->getOwnerPlayerId() == 999" in separate_ownership
    assert "soldier->setOwnerPlayerId(ownerSeat)" in separate_ownership
    assert "seatName(seat) == base->getOwnerPlayerName()" in separate_ownership
    lobby = source("src/CoopMod/LobbyMenu.cpp")
    host_initial = lobby.split("setOwnerPlayerName(_game->getCoopMod()->getHostName())", 1)[1]
    assert "refreshSeparateBaseOwnership();" in host_initial
    saved_game = source("src/Savegame/SavedGame.cpp")
    maintenance = saved_game.split("int SavedGame::getBaseMaintenance() const", 1)[1].split(
        "std::vector<Ufo*> *SavedGame::getUfos", 1)[0]
    assert "xbase->getOwnerPlayerName().empty()" in maintenance
    memory_save = saved_game.split("void SavedGame::saveCoopToMemory", 1)[1].split(
        "buildCoopStub", 1)[0]
    assert "_campaignType == CoopCampaignType::Separate" in memory_save
    server_role = tcp.split("void connectionTCP::setServerOwner", 1)[1].split(
        "void connectionTCP::setCoopCampaign", 1)[0]
    assert "base->_coopBase = !base->isOwnedByPlayer(localName)" in server_role
    load_game = source("src/Menu/LoadGameState.cpp")
    adoption = load_game.split("connectionTCP::coop_save_owner_player_id = 1", 1)[1].split(
        "SharedEcon::notifyWorldAdopted", 1)[0]
    assert "refreshSeparateBaseOwnership();" in adoption

    assert "merged bootstrap base(s)" in tcp
    assert "no client blob retained" in tcp
    wait_bases_release = coop_state.split("void CoopState::previous", 1)[1].split(
        "if (global_state == COOP_DLG_CLIENT_RESUME_HOLD)", 1)[0]
    assert "streamSharedWorldToClient();" not in wait_bases_release
    geoscape = source("src/Geoscape/GeoscapeState.cpp")
    settled_start = geoscape.split("PRD-J02: host-authoritative campaign start", 1)[1].split(
        "void GeoscapeState::think", 1)[0]
    assert "isSharedCampaign() || _game->getCoopMod()->isSeparateCampaign()" in settled_start
    assert "streamSharedWorldToClient();" in settled_start

    prompt = econ.split("void hostLandingPrompt", 1)[1].split("void hostPatrolPrompt", 1)[0]
    close = econ.split("void broadcastLandClose", 1)[1].split("bool ownsSoldier", 1)[0]
    assert "sharedHost(game)" in prompt
    assert "sharedHost(game)" in close

    assert 'reader.tryRead("battleOwnerPlayerName"' in battle
    assert 'writer.write("battleOwnerPlayerName"' in battle
    assert "setBattleOwnerPlayerName(_craft->getBase()->getOwnerPlayerName())" in landing

    country_funding = save.split("int SavedGame::getCountryFunding", 1)[1].split(
        "int SavedGame::getPlayerIncomeShare", 1)[0]
    assert "country->getFunding().back()" in country_funding
    assert "getPlayerIncomeShare" not in country_funding
    income_share = save.split("int SavedGame::getPlayerIncomeShare", 1)[1].split(
        "std::vector<Region*> *SavedGame::getRegions", 1)[0]
    assert "_coopPlayers.size()" in income_share
    assert "CoopCampaignType::Separate" in income_share
    assert "globalIncome / players" in income_share
    funding_ui = source("src/Geoscape/FundingState.cpp")
    assert "getPlayerIncomeShare" not in funding_ui
    monthly = source("src/Geoscape/MonthlyReportState.cpp")
    assert "getPlayerIncomeShare(_game->getSavedGame()->getCountryFunding())" in monthly
    settled_start = source("src/Geoscape/GeoscapeState.cpp").split(
        "PRD-J02: host-authoritative campaign start", 1)[1].split(
        "void GeoscapeState::think", 1)[0]
    assert "if (_game->getCoopMod()->isSharedCampaign())" in settled_start
    assert "new CoopState(COOP_DLG_WAIT_PLAYERS)" in settled_start
    session_source = source("tools/coop_test/session.py")
    separate_start = session_source.split("# SEPARATE: the client contributes", 1)[1].split(
        "# session up:", 1)[0]
    assert '"single Separate wait dialog only"' in separate_start
    assert 'host.ok({"cmd": "coop_dialog_back"})' not in separate_start.split(
        '"client settled-world ack"', 1)[1]

    # Basescape must recompute foreign access after a mini-base switch, not
    # merely once in its constructor. A foreign globe marker bypasses the
    # craft/intercept menu and opens the restricted Basescape view directly.
    assert "void BasescapeState::updateBaseAccessButtons()" in basescape
    assert "connectionTCP::seatName(connectionTCP::localSeat())" in basescape
    assert "_btnFacilities->setVisible(false);" in basescape
    assert "_btnCrafts->setVisible(true);" in basescape
    targets = source("src/Geoscape/MultipleTargetsState.cpp")
    foreign_route = targets.split(
        "Shared and Separate campaigns keep every real base", 1)[1].split(
        "else if (c != 0)", 1)[0]
    assert "isSeparateCampaign()" in foreign_route
    assert "isOwnedByPlayer" in foreign_route
    assert "new BasescapeState" in foreign_route
    assert "new InterceptState" in foreign_route
    mini = source("src/Basescape/MiniBaseView.cpp")
    assert "Uint8 MiniBaseView::getBaseBorderColor" in mini
    assert "_bases->at(base)->_coopBase" in mini
    assert "_foreignBorder(247)" in mini
    assert "if (base == _base)" in mini
    bases_button = geoscape.split("void GeoscapeState::btnBasesClick", 1)[1].split(
        "void GeoscapeState::btnGraphsClick", 1)[0]
    assert "isSeparateCampaign()" in bases_button
    assert "isOwnedByPlayer(localName)" in bases_button
    assert "selectableBases.front()" in bases_button

    craft_info = source("src/Geoscape/GeoscapeCraftState.cpp")
    assert "foreignSeparateCraft" in craft_info
    assert "craftBase->isOwnedByPlayer" in craft_info
    globe = source("src/Geoscape/Globe.cpp")
    assert "bool Globe::isCraftFlightVisible" in globe
    assert "bool Globe::isWaypointVisible" in globe
    flight_draw = globe.split("void Globe::drawFlights()", 1)[1].split(
        "void Globe::drawDetail", 1)[0]
    assert "isCraftFlightVisible(xcraft)" in flight_draw
    marker_draw = globe.split("void Globe::drawMarkers()", 1)[1].split(
        "bool Globe::isCraftFlightVisible", 1)[0]
    assert "isWaypointVisible(wp)" in marker_draw
    waypoint_clicks = globe.split("std::vector<Target*> Globe::getTargets", 1)[1].split(
        "void Globe::cachePolygons", 1)[0]
    assert "isWaypointVisible(wp)" in waypoint_clicks

    soldiers_ui = source("src/Basescape/SoldiersState.cpp")
    craft_soldiers_ui = source("src/Basescape/CraftSoldiersState.cpp")
    for roster_ui in (soldiers_ui, craft_soldiers_ui):
        assert "legacyMirrorRoster" not in roster_ui
        assert "base_oldsoldiers" not in roster_ui
    base_header = source("src/Savegame/Base.h")
    assert "base_oldsoldiers" not in base_header
    assert "base_oldsoldiers" not in tcp
    arriving = source("src/Geoscape/ItemsArrivingState.cpp")
    assert "transfer->getHours() <= 0" in arriving
    transfer = source("src/Savegame/Transfer.cpp")
    advance = transfer.split("void Transfer::advance", 1)[1].split(
        "Soldier *Transfer::getSoldier", 1)[0]
    assert "if (_delivered)" in advance

    print("PASS: single-world SEPARATE battle authority stays on the server host")
    print("PASS: client landing answers use the broker; legacy blob merge is bypassed")
    print("PASS: battle ownership persists by the craft base owner's player name")
    print("PASS: Monthly Report income is split while country funding stays unchanged")
    print("PASS: SEPARATE wire protocol and foreign-base command allow-list are isolated")
    print("PASS: the eight-base ceiling is global in UI and host validation")
    print("PASS: legacy per-player world/base/save packets are blocked in schema-3")
    print("PASS: BASES selects an own base and foreign mini-base borders stay purple")
    print("PASS: foreign bases refresh restricted menus and globe clicks open Basescape")
    print("PASS: foreign craft info is read-only and its route remains private")
    print("PASS: foreign-base personnel arrivals leave transit and remain visible")


if __name__ == "__main__":
    main()
