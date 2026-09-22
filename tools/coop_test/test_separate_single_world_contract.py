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

    # A Separate player may mutate only named-owned bases, except for the two
    # explicitly requested foreign-base services: buy and equip/rearm craft.
    ownership = econ.split("Schema-3 SEPARATE policy", 1)[1]
    ownership = ownership.split("int64_t cost", 1)[0]
    assert "base->isOwnedByPlayer(playerName)" in ownership
    assert 'pc.cmd == "buy"' in ownership
    assert 'pc.cmd == "craft_equip"' in ownership
    assert 'pc.cmd == "craft_rearm"' in ownership
    assert 'pc.cmd == "fac_build"' not in ownership
    assert "save->getBases()->size() >= 8" in econ
    assert "getBases()->size() < MiniBaseView::MAX_BASES" in basescape
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

    funding = save.split("int SavedGame::getPlayerFundingShare", 1)[1]
    funding = funding.split("int SavedGame::getCountryFunding", 1)[0] \
        if "int SavedGame::getCountryFunding" in funding else funding
    assert "_coopPlayers.size()" in funding
    assert "CoopCampaignType::Separate" in funding
    assert "getOwnerPlayerName().empty()" in funding
    assert "globalFunding / players" in funding

    print("PASS: single-world SEPARATE battle authority stays on the server host")
    print("PASS: client landing answers use the broker; legacy blob merge is bypassed")
    print("PASS: battle ownership persists by the craft base owner's player name")
    print("PASS: legacy SEPARATE funding is divided; schema-3 single-world funding is not")
    print("PASS: SEPARATE wire protocol and foreign-base command allow-list are isolated")
    print("PASS: the eight-base ceiling is global in UI and host validation")
    print("PASS: legacy per-player world/base/save packets are blocked in schema-3")


if __name__ == "__main__":
    main()
