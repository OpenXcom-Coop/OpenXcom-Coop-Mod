/*
 * Copyright 2010-2016 OpenXcom Developers.
 * Copyright 2023-2026 XComCoopTeam (https://www.moddb.com/mods/openxcom-coop-mod)
 *
 * This file is part of OpenXcom.
 *
 * OpenXcom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * OpenXcom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with OpenXcom.  If not, see <http://www.gnu.org/licenses/>. 
 */

#include "connectionTCP.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <memory>
#include <sstream>
#include <unordered_set>

#include "../Engine/Game.h"
#include "../Engine/Language.h"
#include "../Engine/RNG.h"
#include "../Menu/MainMenuState.h"

#include "../Basescape/CraftSoldiersState.h"
#include "../Mod/AlienDeployment.h"
#include "../Menu/CutsceneState.h"

#include "../Savegame/AlienMission.h"
#include "../Mod/UfoTrajectory.h"
#include "../Savegame/Ufo.h"
#include "../Battlescape/DebriefingState.h"
#include "../Battlescape/BattlescapeState.h"
#include "../Battlescape/BriefingState.h"
#include "../Battlescape/BattlescapeGame.h"
#include "../Battlescape/UnitTurnBState.h"
#include "../Battlescape/Pathfinding.h"
#include "../Battlescape/TileEngine.h"

#include "../Savegame/Country.h"
#include "../Mod/RuleCountry.h"
#include "../Mod/RuleRegion.h"
#include "../Savegame/Region.h"

#include "../Mod/RuleCraftWeapon.h"
#include "../Savegame/Craft.h"
#include "../Savegame/CraftWeapon.h"

#include "../Menu/NewGameState.h"
#include "../Menu/LoadGameState.h"
#include "../Geoscape/GeoscapeState.h"
#include "../Geoscape/ConfirmCydoniaState.h"
#include "../Geoscape/Globe.h"
#include "../Geoscape/BaseNameState.h"
#include "../Geoscape/BuildNewBaseState.h"
#include "../Basescape/PlaceLiftState.h"

#include "./connectionUDP/connection_rendezvous_glue.h"

#include "PasswordCheckMenu.h"
#include "ModCheckMenu.h"
#include "GiftNoticeState.h"
#include "SharedEcon.h"
#include "BattleWire.h"
#include "BattlePump.h"
#include "BattleAuthority.h"
#include "CoopIdMaps.h"
#include "CoopArbiter.h"
#include "CoopBattleUi.h"
#include "CoopHandshake.h"
#include "CoopBattleSetup.h"
#include "CoopApply.h"
#include "CoopReveal.h"
#include "VoteMenu.h"
#include "connectionUDP/connection_udp_glue.h"

#include "../Savegame/BaseFacility.h"
#include "../Engine/Logger.h"
#include "../Engine/Yaml.h"
#include "../Mod/Mod.h"
#include "../Savegame/Base.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/Transfer.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/BattleItem.h"
#include "../Mod/RuleItem.h"

// R4-P1 (SPIKE-RUNBOOK.md SS2.7/IR-6): CoopHandshake needs the full SavedGame
// (loadCoopSaveFromMemory/saveCoopToMemory), Options/Screen (battlescape
// resolution switch, matching LoadGameState.cpp's own load-with-live-battle
// precedent), and libsodium crypto_hash_sha256 - never a hand-rolled hash
// (IR-6). sodium.h is already linked (connectionUDP uses it, e.g.
// connectionUDP.h:19).
#include "../Savegame/SavedGame.h"
#include "../Engine/Options.h"
#include "../Engine/Screen.h"
#include <sodium.h>

namespace OpenXcom
{

/**
 * Issue #93: is a tactical mission actually running on this machine?
 *
 * The drop handling branches on it: a peer vanishing mid-battle is a freeze to
 * wait out (or leave via SAVE & QUIT / ABANDON GAME), exactly like the campaign
 * geoscape case - never a lobby popped over the battle. Reads the WORLD, not the
 * state stack, so it is true from the moment the battle exists.
 */
static bool coopBattleLive(Game* game)
{
	return game && game->getSavedGame()
		&& game->getSavedGame()->getSavedBattle() != nullptr;
}

// COOP VARIABLES
// is the session created?
bool coopSession = false;
// allow sending a file to the client
bool sendFileClient = false;
// is the file to be sent a base?
bool sendFileBase = false;
// allow sending a file to the host
bool sendFileHost = false;
// allow sending a file to the host
bool sendProgressSaveFileToHost = false;
std::string sendProgressLoadFileToClient = "";
// Snapshot of the resume blob, copied on the main thread when a
// request_load_progress arrives so the streamer thread never touches the
// shared blob maps for it.
std::string sendProgressLoadBlob = "";
// is the file to be sent a saved file?
bool sendFileSave = false;
// map data
std::string mapData = "";
// how much space does the host have in the craft?
int _hostSpace;

ConfirmLandingState* _landing;
ConfirmCydoniaState* _cydonia;
NewBattleState* _battleState;
GeoscapeState* _geo;
Craft* _selectedCraft;
Pathfinding* _selectedPath;

// ip address
std::string ipAddress = "";

// port (default: 3000)
int tcp_port = 3000;

// is it the host?
bool onTcpHost = false;

// is the server owner the one who creates the server?

// the local server name
std::string sendTcpServerName = "Server";

// the recipient player's name
std::string tcpServerName = "Server";

// the local player's name
std::string sendTcpPlayer = "Player";

// the recipient player's name
std::string tcpPlayerName = "Player";

int onConnect = -1; // -1 = connect lost, 0 = client cant connect, -2 = disconnect, 1 = connected, -3 = server error, 2 = waiting for player

bool clearPackets = false;

// trigger the event once
bool onceTime = false;

// base markers
std::string j_markers;

// has the map data arrived?
bool isWaitMap = true;

// trading
Json::Value waitedTrades;

int connectionTCP::_coopGamemode = 0;

int connectionTCP::coop_save_owner_player_id = 0; 

// PRD-J01: economy model shown in the lobby to a joining client (0=Sep,1=Shared).
int connectionTCP::_lobbyCampaignType = 0;

// PRD-J01: set once in the ctor; lets the static seat accessors reach the roster.
Game* connectionTCP::_staticGame = nullptr;

bool connectionTCP::_isChatActiveStatic = false;

bool connectionTCP::_isActiveAISync = false;

bool connectionTCP::_isActivePlayerSync = false; 

bool connectionTCP::_enable_time_sync = true;

bool connectionTCP::_enable_reaction_shoot = true;

bool connectionTCP::_enable_other_player_footsteps = true;

bool connectionTCP::_enable_host_only_time_speed = false;

bool connectionTCP::_enable_xcom_equipment_aliens_pvp = true;

bool connectionTCP::_unbalanced_craft_soldiers_limit = false;

bool connectionTCP::_coopCampaign = false;

bool connectionTCP::_battleInit = false;

bool connectionTCP::playerInsideCoopBase = false;

bool connectionTCP::coopInventory = false;

bool connectionTCP::moveCoopItems = false;

bool connectionTCP::no_bases = false;

bool connectionTCP::isCoopBaseLoading = false;

bool connectionTCP::_isHotseatActive = false;

bool connectionTCP::_isHotseatReactionFireEnabled = false;

bool connectionTCP::show_inactive_player_inventory = false;

bool connectionTCP::pauseSound = false;

bool connectionTCP::saveError = false;

CoopSession connectionTCP::session;

std::string connectionTCP::joinRefusalReason = "";
std::string connectionTCP::sharedFailReason = "";

// --- CoopSession transitions: every lifecycle change is logged. The mirrored
// --- booleans ARE the encoding (PRD-12 S4 deleted the write-only phase enum);
// --- every multi-field / cross-file write funnels through a named method here.

void CoopSession::beginHosting()
{
	role = CoopRole::Host;
	Log(LOG_INFO) << "[coop-session] beginHosting (role=Host)";
}

void CoopSession::beginJoining()
{
	role = CoopRole::Client;
	Log(LOG_INFO) << "[coop-session] beginJoining (role=Client)";
}

void CoopSession::clientAttached()
{
	clientInLobby = true;
	Log(LOG_INFO) << "[coop-session] clientAttached (clientInLobby=1)";
}

void CoopSession::campaignStarted()
{
	sessionLocked = true;
	Log(LOG_INFO) << "[coop-session] campaignStarted (sessionLocked=1)";
}

void CoopSession::sessionLive()
{
	// waiting dialogs released; play begins/resumes. No boolean of its own -
	// the surrounding flow already set lobbyClosed/campaignBegun; this is the
	// lifecycle marker in the log.
	Log(LOG_INFO) << "[coop-session] sessionLive";
}

void CoopSession::freeze()
{
	// a registered player dropped mid-session (D5). The freeze dialog + the
	// preserved lobby/campaign booleans carry the state; this marks it in the log.
	Log(LOG_INFO) << "[coop-session] freeze (lobbyMode=" << lobbyMode
		<< " locked=" << sessionLocked << ")";
}

void CoopSession::setRole(CoopRole r)
{
	role = r;
	Log(LOG_INFO) << "[coop-session] setRole -> "
		<< (r == CoopRole::Host ? "Host" : r == CoopRole::Client ? "Client" : "None");
}

void CoopSession::adoptResumeSave()
{
	lobbyMode = 2;
	sessionLocked = false;
	resumeAck = false;
	Log(LOG_INFO) << "[coop-session] adoptResumeSave (lobbyMode=2, unlocked, ack cleared)";
}

void CoopSession::armResumeHandshake(bool hasBattle)
{
	resumeAck = false;
	resumeBattlePending = hasBattle;
	Log(LOG_INFO) << "[coop-session] armResumeHandshake (battlePending=" << hasBattle << ")";
}

void CoopSession::markLobbyOpen()
{
	lobbyClosed = false;
	Log(LOG_INFO) << "[coop-session] markLobbyOpen (lobbyClosed=0)";
}

void CoopSession::markLobbyClosed()
{
	lobbyClosed = true;
	Log(LOG_INFO) << "[coop-session] markLobbyClosed (lobbyClosed=1)";
}

void CoopSession::armDeferredSave(const std::string& name)
{
	pendingHostSaveName = name;
	Log(LOG_INFO) << "[coop-session] armDeferredSave ('" << name << "')";
}

void CoopSession::clearDeferredSave()
{
	pendingHostSaveName.clear();
	Log(LOG_INFO) << "[coop-session] clearDeferredSave";
}

void CoopSession::signalCampaignBegun()
{
	campaignBegun = true;
	Log(LOG_INFO) << "[coop-session] signalCampaignBegun (campaignBegun=1)";
}

void CoopSession::consumeCampaignBegun()
{
	campaignBegun = false;
	Log(LOG_INFO) << "[coop-session] consumeCampaignBegun (campaignBegun=0)";
}

void CoopSession::lockCustomBattleCraft(int craftId)
{
	customBattleCraftLocked = true;
	customBattleCraftId = craftId;
	Log(LOG_INFO) << "[coop-session] lockCustomBattleCraft (craftId=" << craftId << ")";
}

void CoopSession::resetSession()
{
	Log(LOG_INFO) << "[coop-session] resetSession";
	role = CoopRole::None;
	lobbyMode = 0;
	clientInLobby = false;
	sessionLocked = false;
	lobbyClosed = true;
	resumeAck = false;
	resumeBattlePending = false;
	resumeBattleEligible.clear();
	campaignBegun = false;
	customBattleCraftLocked = false;
	customBattleCraftId = -1;
	skirmishRejoinPending = false;
	pendingHostSaveName.clear();

	// Full teardown returns the process to a pristine coop identity so a later
	// solo save (or a second campaign) does not inherit this session's saveID or
	// its stale world blobs (fixes C1/C2). This is the ONLY teardown path;
	// onClientDrop deliberately keeps both so the host can serve a rejoin (D5).
	connectionTCP::saveID = 0;

	// The client-side time mirror is process-static and is applied to every live
	// SavedGame while time sync is enabled. If a campaign is followed by a
	// skirmish in the same process, retaining the campaign year makes think()
	// overwrite the skirmish's monthsPassed == -1 with the old campaign value.
	// DebriefingState then mistakes the skirmish for a campaign and returns to
	// the geoscape. A full teardown must discard the old world's clock too.
	connectionTCP::_weekday = 0;
	connectionTCP::_day = 0;
	connectionTCP::_month = 0;
	connectionTCP::_year = 0;
	connectionTCP::_hour = 0;
	connectionTCP::_minute = 0;
	connectionTCP::_second = 0;
	connectionTCP::monthsPassed = 0;
	connectionTCP::daysPassed = 0;

	{
		std::lock_guard<std::mutex> lock(connectionTCP::coopFilesMutex);
		connectionTCP::coopFilesHost.clear();
		connectionTCP::coopFilesClient.clear();
	}
}

void CoopSession::onClientDrop()
{
	Log(LOG_INFO) << "[coop-session] onClientDrop";
	clientInLobby = false;
	resumeAck = false;
	resumeBattlePending = false;
	resumeBattleEligible.clear();
	campaignBegun = false;
	pendingHostSaveName.clear();
	// role/lobbyMode/sessionLocked/lobbyClosed survive: the campaign context
	// outlives a peer drop (D5) - the freeze dialog or waiting lobby takes
	// over. The legacy new-battle lobby (mode 0) instead restarts its ready
	// dance, so its lock is released here.
	if (lobbyMode == 0)
	{
		sessionLocked = false;
		// Custom Battle craft locking is only valid while the multiplayer
		// connection is alive. After the peer leaves, the host returns to the
		// Battle Generator and may select or randomize another craft normally.
		customBattleCraftLocked = false;
		customBattleCraftId = -1;
	}
}

bool connectionTCP::isPasswordRequired = false;
std::string connectionTCP::password = "";

bool connectionTCP::isPlayerReady = false;

bool connectionTCP::isPlayersReady = false;

int connectionTCP::LobbyFileStatus = -1;

int connectionTCP::lobby_timer = -1;

bool connectionTCP::loadProgressBusy = false;

bool connectionTCP::forceCloseCoopStateMenu = false;

bool connectionTCP::forceClosePasswordCheckMenu = false;

int connectionTCP::manuallyAddedServerRemoveID = -1;

bool connectionTCP::canRemoveManuallyAddedServer = false;

bool connectionTCP::isInfoboxClosed = true;

// saveID is only used when the host saves each player's progress. This ensures that players load the correct save data.
long long connectionTCP::saveID = 0;

int connectionTCP::_weekday = 0;
int connectionTCP::_day = 0;
int connectionTCP::_month = 0;
int connectionTCP::_year = 0;
int connectionTCP::_hour = 0;
int connectionTCP::_minute = 0;
int connectionTCP::_second = 0;

int connectionTCP::monthsPassed = 0;
int connectionTCP::daysPassed = 0;

std::unordered_map<std::string, std::string> OpenXcom::connectionTCP::coopFilesHost{};
std::unordered_map<std::string, std::string> OpenXcom::connectionTCP::coopFilesClient{};
std::mutex OpenXcom::connectionTCP::coopFilesMutex;

std::string current_ping = "";

connectionTCP::connectionTCP(Game* game) : _game(game)
{
	// PRD-J01: publish the process-single Game for the static seat accessors.
	_staticGame = game;
	// PRD-J03: register the SHARED economy command handlers (idempotent).
	SharedEcon::init();

	// R2-P1 self-test (SPIKE-RUNBOOK.md IR-16b): round-trip every CoopWire
	// maker plus the two routing predicates. Gated on OXC_TEST_PORT (same
	// env var TestServer::startFromEnvironment reads) so it is inert outside
	// the harness; connectionTCP's ctor runs well before Game::run() starts
	// TestServer, so this is the earliest coop-side hook that can see it.
	if (std::getenv("OXC_TEST_PORT"))
	{
		auto fail = [](const char* what) { Log(LOG_ERROR) << "[coopwire-selftest] FAIL: " << what; };
		bool ok = true;
		Json::Value v;

		v = CoopWire::makeIntent(7u, 2, 42, "turn");
		if (!(v["state"] == "bt_intent" && v["iseq"].asUInt() == 7u && v["seat"].asInt() == 2 &&
			v["actorId"].asInt() == 42 && v["kind"] == "turn")) { fail("makeIntent"); ok = false; }

		v = CoopWire::makeAck(9u, 100u);
		if (!(v["state"] == "bt_ack" && v["iseq"].asUInt() == 9u && v["actionId"].asUInt() == 100u))
		{ fail("makeAck"); ok = false; }

		v = CoopWire::makeDeny(11u, "busy");
		if (!(v["state"] == "bt_deny" && v["iseq"].asUInt() == 11u && v["reason"] == "busy"))
		{ fail("makeDeny"); ok = false; }

		v = CoopWire::makeEv(3u, 55u, "turn");
		if (!(v["state"] == "bt_ev" && v["seq"].asUInt() == 3u && v["actionId"].asUInt() == 55u &&
			v["kind"] == "turn" && v["payload"].isObject() && v["payload"].empty()))
		{ fail("makeEv"); ok = false; }

		v = CoopWire::makeActionEnd(4u, 56u);
		if (!(v["state"] == "bt_action_end" && v["seq"].asUInt() == 4u && v["actionId"].asUInt() == 56u))
		{ fail("makeActionEnd"); ok = false; }

		if (!(CoopWire::isBattleKind("bt_intent") && CoopWire::isBattleKind("bt_ev") &&
			CoopWire::isBattleKind("battle_offer") && CoopWire::isBattleKind("battle_ready") &&
			!CoopWire::isBattleKind("chat_message") && !CoopWire::isBattleKind("time") &&
			!CoopWire::isBattleKind("vote_cast"))) { fail("isBattleKind"); ok = false; }

		if (!(CoopWire::isSeqOrdered("bt_ev") && CoopWire::isSeqOrdered("bt_action_end") &&
			!CoopWire::isSeqOrdered("bt_intent"))) { fail("isSeqOrdered"); ok = false; }

		if (ok)
			Log(LOG_INFO) << "CoopWire self-test OK";
	}

	// R2-P2 self-test (SPIKE-RUNBOOK.md acceptance item 4): prove the client
	// apply queue detects an out-of-order seq and freezes instead of silently
	// applying it. Same OXC_TEST_PORT gate as the CoopWire self-test above
	// (kept as a separate block per the packet's "add a second gated block"
	// option, so a failure here is unambiguous about which layer broke).
	if (std::getenv("OXC_TEST_PORT"))
	{
		auto fail = [](const char* what) { Log(LOG_ERROR) << "[cooppump-selftest] FAIL: " << what; };
		bool ok = true;

		CoopPump::reset(); // isolate from anything else that ran this session

		// nextSeq()/reset() sanity: mint 1, 2, then reset should rewind to 1.
		uint32_t s1 = CoopEmit::nextSeq();
		uint32_t s2 = CoopEmit::nextSeq();
		if (!(s1 == 1u && s2 == 2u)) { fail("nextSeq sequence"); ok = false; }
		CoopPump::reset();
		uint32_t s3 = CoopEmit::nextSeq();
		if (s3 != 1u) { fail("nextSeq reset"); ok = false; }
		CoopPump::reset(); // also rewinds the mint counter back to 1 for the enqueue test below

		// Enqueue OUT OF ORDER: seq 1, then 3, then 2 (acceptance item 4's exact case).
		CoopPump::enqueue(CoopWire::makeEv(1u, 201u, "turn"));
		CoopPump::enqueue(CoopWire::makeEv(3u, 203u, "turn"));
		CoopPump::enqueue(CoopWire::makeEv(2u, 202u, "turn"));

		// Drain once: seq 1 applies, then seq 3 (expected 2) is a gap - the
		// drain must log it and freeze, leaving both unresolved entries queued.
		CoopPump::drainApplyQueue();

		if (CoopPump::lastSeqApplied() != 1u) { fail("lastSeqApplied after gap"); ok = false; }
		if (CoopPump::queueDepth() != 2u) { fail("queueDepth after gap"); ok = false; }
		if (!g_battleFrozen.load()) { fail("g_battleFrozen not set"); ok = false; }

		// A frozen queue must not silently resume even though the very next
		// entry (seq 2) would now be resolvable - draining again must be a no-op.
		CoopPump::drainApplyQueue();
		if (CoopPump::queueDepth() != 2u || CoopPump::lastSeqApplied() != 1u)
		{ fail("drain resumed while frozen"); ok = false; }

		CoopPump::reset(); // leave a clean slate for real play in this process

		if (ok)
			Log(LOG_INFO) << "CoopPump self-test OK";
	}

	// R2-P3 self-test (SPIKE-RUNBOOK.md RB-D6): prove the BattleAuthority
	// singleton's init/reset round-trip and the interim seat->faction store
	// behave as spec'd, without needing a live battle. Same OXC_TEST_PORT
	// gate, kept as its own block for the same reason as the CoopWire/
	// CoopPump blocks above - an unambiguous failure signal per layer.
	if (std::getenv("OXC_TEST_PORT"))
	{
		auto fail = [](const char* what) { Log(LOG_ERROR) << "[battleauthority-selftest] FAIL: " << what; };
		bool ok = true;

		resetBattleAuthority();
		BattleAuthority& a = coopBattleAuthority();

		if (!(a.hostSim == false && a.localSeat == -1 && a.phase == CoopBattlePhase::Idle
			&& a.battleId == 0u)) { fail("reset defaults"); ok = false; }
		if (a.factionOf(0) != (int)FACTION_PLAYER) { fail("factionOf default"); ok = false; }
		if (a.commandsUnit(nullptr) != false) { fail("commandsUnit(null)"); ok = false; }
		if (a.mySideActive(nullptr) != false) { fail("mySideActive(null)"); ok = false; }

		initBattleAuthority(777u);
		if (!(a.hostSim == connectionTCP::getServerOwner()
			&& a.localSeat == connectionTCP::localSeat()
			&& a.phase == CoopBattlePhase::Handshake
			&& a.battleId == 777u)) { fail("initBattleAuthority sets hostSim/localSeat/phase/battleId"); ok = false; }

		a.setSeatFaction(0, (int)FACTION_HOSTILE);
		if (a.factionOf(0) != (int)FACTION_HOSTILE) { fail("setSeatFaction"); ok = false; }
		if (a.factionOf(1) != (int)FACTION_PLAYER) { fail("factionOf still-unmapped seat"); ok = false; }
		if (a.factionOf(99) != (int)FACTION_PLAYER) { fail("factionOf out-of-range seat"); ok = false; }

		a.resetSeatFactions();
		if (a.factionOf(0) != (int)FACTION_PLAYER) { fail("resetSeatFactions"); ok = false; }

		if (isCoopBattle()) { fail("isCoopBattle true outside Active phase"); ok = false; }

		resetBattleAuthority(); // leave a clean slate for real play in this process
		if (!(a.phase == CoopBattlePhase::Idle && a.localSeat == -1))
		{ fail("final reset"); ok = false; }

		if (ok)
			Log(LOG_INFO) << "BattleAuthority self-test OK";
	}

	// R2-P4 self-test (SPIKE-RUNBOOK.md RB-D7): prove the id-map lookups and
	// the nullptr/unmapped-id edge cases behave as spec'd. Same OXC_TEST_PORT
	// gate as the blocks above. Deliberately does NOT exercise the real
	// full-scan path in rebuildFrom(save) (registerItem/registerUnit either)
	// - that needs a live SavedBattleGame with real BattleUnit/BattleItem
	// objects, which do not exist this early (connectionTCP's ctor runs
	// before any battle is loaded); it covers every path reachable without
	// one: rebuildFrom(nullptr), empty-map lookups, no-op forget on unmapped
	// ids, and reset().
	if (std::getenv("OXC_TEST_PORT"))
	{
		auto fail = [](const char* what) { Log(LOG_ERROR) << "[coopidmaps-selftest] FAIL: " << what; };
		bool ok = true;

		CoopIdMaps::reset(); // isolate from anything else that ran this session

		if (CoopIdMaps::unit(1) != nullptr) { fail("unit() on empty map"); ok = false; }
		if (CoopIdMaps::item(1) != nullptr) { fail("item() on empty map"); ok = false; }

		CoopIdMaps::rebuildFrom(nullptr); // must not crash; leaves both maps empty
		if (CoopIdMaps::unit(1) != nullptr) { fail("rebuildFrom(nullptr) left a unit"); ok = false; }
		if (CoopIdMaps::item(1) != nullptr) { fail("rebuildFrom(nullptr) left an item"); ok = false; }

		CoopIdMaps::forget(1);     // no-op on an unmapped id - must not crash
		CoopIdMaps::forgetUnit(1); // same
		if (CoopIdMaps::unit(1) != nullptr) { fail("forgetUnit no-op corrupted map"); ok = false; }
		if (CoopIdMaps::item(1) != nullptr) { fail("forget no-op corrupted map"); ok = false; }

		CoopIdMaps::reset(); // leave a clean slate for real play in this process

		if (ok)
			Log(LOG_INFO) << "CoopIdMaps self-test OK";
	}
}

connectionTCP::~connectionTCP()
{

	 _stop = true;
	 _clientStop = true;
	 _hostStop = true;

	if (_loopThread.joinable())
		_loopThread.join();   

	if (_clientThread.joinable())
		_clientThread.join();

	if (_hostThread.joinable())
		_hostThread.join();   

}

SPSCQueue<1024> g_txQ{};
SPSCQueue<1024> g_rxQ{};

// Main-thread hold queue used by updateCoopTask(). Keep it outside the
// function so disconnect/reconnect cleanup can reset it fully between sessions.
static std::mutex g_rxHoldMutex;
static std::deque<std::string> g_rxHold;

// TX-queue drop counter (test harness diagnostic; see connectionTCP.h).
std::atomic<uint64_t> g_txDropCount{0};

// ===== R2-P2: battle seq-ordered apply queue + seq mint (BattlePump.h) =====
// SPIKE-RUNBOOK.md RB-D5/SS2.2. Storage lives here, next to the other coop
// queue globals, exactly like g_rxHold above; CoopPump/CoopEmit (declared in
// BattlePump.h) are implemented directly below.
static std::mutex g_battleApplyQueueMutex;
static std::deque<Json::Value> g_battleApplyQueue;
static std::atomic<uint32_t> g_battleLastSeqApplied{0}; // 0 = none applied yet (SS2.2)
static uint32_t g_battleNextSeqMint = 1; // host mint counter (SS2.2: starts at 1 per battle)

// R2-P11: MN-8 backpressure counter - how many battle-lane sends have hit the
// g_txQ-overflow blocking-wait bypass (coopEmitBlockingPush() below) at least
// once, this battle. event_state's "txDrains" field (the re-labeled successor
// of the pre-rewrite battle_state's rxHold/rxRotates counters, per this
// packet's own runbook text). Atomic: coopEmitBlockingPush() runs on whatever
// thread calls CoopEmit::sendBattle()/sendEv() - main/pump thread for every
// real call site today, but TestServer's introspection reads it from the same
// thread anyway; kept atomic defensively, same reasoning as g_battleFrozen.
std::atomic<uint32_t> g_battleTxDrainEvents{0};

// R2-P2/IR-16c: seq-gap freeze flag (BattlePump.h). Extern linkage so a
// later packet (R2-P9's desync report, or R2-P3's BattleAuthority) can read
// (and eventually clear) it without going through a function call.
std::atomic<bool> g_battleFrozen{false};

// R2-P5 forward declaration: CoopPump::reset() below (RB-D5's established
// single battle-teardown chokepoint, R2-P8 wires its call site) also clears
// CoopArbiter's own battle-scoped statics (defined further down this file,
// after CoopIdMaps) - see resetCoopArbiterState()'s own doc comment.
static void resetCoopArbiterState();

// RW-REVEAL-SYNC forward declaration: defined further down, next to CoopArbiter
// (its body needs SharedEcon::computeBattleHashes, whose only other callers live
// there). Declared here so CoopReveal::flushQuiescent() below can stamp RB-D14's
// h:{unitsStats} on the standalone reveal ev without splitting the CoopReveal
// namespace across the file.
static Json::Value coopBuildUnitsStatsHash(SavedBattleGame* save);

// SS2.8's mismatch path (freeze -> bt_desync -> bundle -> banner), factored out
// of CoopHashCheck::verify() (this file) so the SS2.4a reveal `base` n-mismatch
// raises the IDENTICAL desync through the IDENTICAL code. Latches on
// BattleAuthority::desyncFrozen: a battle that already desynced never reports a
// second time (SS2.8 "NO partial repair").
static void coopRaiseBattleDesync(const char* bucket, const std::string& expect,
	const std::string& got, std::uint32_t seq, const std::string& kind)
{
	if (coopBattleAuthority().desyncFrozen.exchange(true))
		return; // already latched, or lost a race with another envelope this tick

	Log(LOG_ERROR) << "[coop-hash] DESYNC: bucket=" << bucket << " seq=" << seq
		<< " kind=" << kind << " expect=" << expect << " got=" << got
		<< " - freezing battle input (SS2.8, no partial repair)";

	g_battleFrozen.store(true); // halts the R2-P2 apply queue too (BattlePump.h)

	const std::string bundlePath = SharedEcon::writeDesyncBundle(bucket, expect, got, seq, kind);

	Json::Value rep = CoopWire::makeDesync(coopBattleAuthority().battleId.load(), seq,
		bucket, expect, got);
	if (!bundlePath.empty())
		rep["bundlePath"] = bundlePath;
	CoopEmit::sendBattle(rep);

	CoopBattleUi::showDesyncHalted();
}

// ===== RW-REVEAL-SYNC (SPIKE-RUNBOOK.md SS2.4a): host-authored fog of war =====
// See CoopReveal.h for the full contract (wire shape, monotonicity, the client
// authority rule, and why attachment lives at the CoopEmit::sendEv choke).
namespace CoopReveal
{

namespace
{

// The HOST's published bitmap: 1 byte per tile, index order =
// SavedBattleGame::getTileIndex, bits = Tile::saveBinary's boolFields low three
// (1 = O_WESTWALL, 2 = O_NORTHWALL, 4 = O_FLOOR; Tile.cpp:207 - NOT the
// makeDiscoveredScript order at Tile.cpp:1183, which is floor=1/west=2/north=4).
//
// TODO (RW-REVEAL-SYNC open risk 3 - MULTI-STAGE, POST-SPIKE): reveal is monotone
// only WITHIN one battle stage. SavedBattleGame::resetTiles() is the only path
// that CLEARS discovered bits and it runs at a stage transition, after which this
// bitmap is stale-HIGH and every later sparse `add` would under-report. The stage
// atom MUST, in this order: (1) reset this bitmap against the new stage's tiles
// (seedPublished()), and (2) ship a fresh ABSOLUTE `base` restate, because a
// client NEVER clears a bit on its own (SS2.4a) and would otherwise keep the
// previous stage's reveals forever.
std::vector<std::uint8_t> g_publishedReveal;

// RB-D26 one-shot test levers - see CoopReveal.h.
bool g_revealDropNext = false;
bool g_revealBaseNext = false;
bool g_revealBaseBadN = false;

// Guards g_publishedReveal + the lever flags. Same reasoning as CoopIdMaps'
// own g_coopIdMapsMutex (BattleAuthority.h's R4-P1 cross-thread note): the
// battle-teardown chokepoint clearNetworkSessionQueues() -> CoopPump::reset()
// -> CoopReveal::reset() is reachable from the UDP monitor thread, while every
// other access here is main/pump-thread. The container cannot be made atomic,
// so it gets a mutex taken INSIDE each public function - zero call-site changes.
std::mutex g_revealMutex;

inline std::uint8_t liveBits(const Tile* t)
{
	return (std::uint8_t)((t->isDiscovered(O_WESTWALL) ? 1 : 0)
		| (t->isDiscovered(O_NORTHWALL) ? 2 : 0)
		| (t->isDiscovered(O_FLOOR) ? 4 : 0));
}

/// Applies @a bits to @a t; returns how many parts actually flipped to
/// discovered (log/introspection only). Never clears a bit (SS2.4a monotone).
int applyBitsToTile(Tile* t, std::uint8_t bits)
{
	if (!t || !bits)
		return 0;
	int changed = 0;
	if ((bits & 1) && !t->isDiscovered(O_WESTWALL))  { t->setDiscovered(true, O_WESTWALL);  ++changed; }
	if ((bits & 2) && !t->isDiscovered(O_NORTHWALL)) { t->setDiscovered(true, O_NORTHWALL); ++changed; }
	// Last on purpose: O_FLOOR cascades WESTWALL+NORTHWALL true (Tile.cpp:433-438),
	// so doing it last keeps `changed` an honest count of what this delta added.
	if ((bits & 4) && !t->isDiscovered(O_FLOOR))     { t->setDiscovered(true, O_FLOOR);     ++changed; }
	return changed;
}

const char kB64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

std::string b64Encode(const std::vector<std::uint8_t>& in)
{
	std::string out;
	out.reserve(((in.size() + 2u) / 3u) * 4u);
	std::size_t i = 0;
	for (; i + 3u <= in.size(); i += 3u)
	{
		const std::uint32_t v = ((std::uint32_t)in[i] << 16) | ((std::uint32_t)in[i + 1] << 8) | in[i + 2];
		out += kB64[(v >> 18) & 63]; out += kB64[(v >> 12) & 63];
		out += kB64[(v >> 6) & 63];  out += kB64[v & 63];
	}
	if (i + 1u == in.size())
	{
		const std::uint32_t v = (std::uint32_t)in[i] << 16;
		out += kB64[(v >> 18) & 63]; out += kB64[(v >> 12) & 63]; out += "==";
	}
	else if (i + 2u == in.size())
	{
		const std::uint32_t v = ((std::uint32_t)in[i] << 16) | ((std::uint32_t)in[i + 1] << 8);
		out += kB64[(v >> 18) & 63]; out += kB64[(v >> 12) & 63];
		out += kB64[(v >> 6) & 63];  out += '=';
	}
	return out;
}

bool b64Decode(const std::string& in, std::vector<std::uint8_t>& out)
{
	out.clear();
	out.reserve((in.size() / 4u) * 3u);
	std::uint32_t acc = 0;
	int bits = 0;
	for (char c : in)
	{
		if (c == '=')
			break;
		if (c == '\n' || c == '\r' || c == ' ' || c == '\t')
			continue;
		const char* p = (c == '\0') ? nullptr : std::strchr(kB64, c);
		if (!p)
			return false;
		acc = (acc << 6) | (std::uint32_t)(p - kB64);
		bits += 6;
		if (bits >= 8)
		{
			bits -= 8;
			out.push_back((std::uint8_t)((acc >> bits) & 0xFFu));
		}
	}
	return true;
}

/// Walks live-vs-published. ASSUMES g_revealMutex is held. With @a out == null
/// this is a pure probe: it returns on the FIRST difference and publishes
/// nothing. With @a out non-null it fills out["add"] with SS2.4a's flat
/// [index, bits, ...] array and marks every reported bit published.
bool computeDelta(SavedBattleGame* battle, Json::Value* out)
{
	if (!battle)
		return false;
	const int n = battle->getMapSizeXYZ();
	if (n <= 0)
		return false;
	if (g_publishedReveal.size() != (std::size_t)n)
	{
		// Unseeded (or a differently-sized battle): publish nothing, so the very
		// next delta carries the WHOLE live set. Bigger on the wire, still
		// correct - reveal is monotone and idempotent (SS2.4a) - and the only
		// way this fires is a missing seedPublished(), which must not silently
		// desync the two machines.
		g_publishedReveal.assign((std::size_t)n, 0u);
	}

	bool any = false;
	Json::Value add(Json::arrayValue);
	for (int i = 0; i < n; ++i)
	{
		const std::uint8_t live = liveBits(battle->getTile(i));
		const std::uint8_t added = (std::uint8_t)(live & (std::uint8_t)~g_publishedReveal[i]);
		if (!added)
			continue;
		any = true;
		if (!out)
			return true; // probe: one difference is the whole answer
		add.append(i);
		add.append((int)added);
		g_publishedReveal[i] = (std::uint8_t)(g_publishedReveal[i] | added);
	}
	if (out && any)
		(*out)["add"] = add;
	return any;
}

/// HOST: ship an ABSOLUTE `base` restate of the whole live bitmap (SS2.4a).
/// Test-lever-only in the spike (the stage atom is its future real caller).
/// MUST be called WITHOUT g_revealMutex held - it goes through CoopEmit::sendEv,
/// which re-enters attachDelta().
void emitBaseRestate(SavedBattleGame* battle, bool badN)
{
	const int n = battle->getMapSizeXYZ();
	if (n <= 0)
		return;
	std::vector<std::uint8_t> bytes((std::size_t)n, 0u);
	for (int i = 0; i < n; ++i)
		bytes[(std::size_t)i] = liveBits(battle->getTile(i));

	Json::Value delta(Json::objectValue);
	delta["base"] = b64Encode(bytes);
	delta["n"] = badN ? (n + 1) : n;

	Json::Value ev = CoopWire::makeEv(0u, 0u, "reveal");
	ev["h"] = coopBuildUnitsStatsHash(battle); // RB-D14
	// Set BEFORE sendEv: attachDelta() leaves an envelope that already carries
	// an explicit restate alone.
	ev["reveal"] = delta;
	CoopEmit::sendEv(ev);

	Log(LOG_WARNING) << "[coop-reveal] reveal_base lever fired: absolute base restate sent ("
		<< n << " tiles, advertised n=" << (badN ? (n + 1) : n)
		<< (badN ? " - DELIBERATELY WRONG, the client must desync" : "") << ")";

	// A restate publishes everything - nothing is outstanding afterwards.
	{
		std::lock_guard<std::mutex> lock(g_revealMutex);
		g_publishedReveal.swap(bytes);
	}
}

} // namespace

void seedPublished(SavedBattleGame* battle)
{
	std::lock_guard<std::mutex> lock(g_revealMutex);
	g_publishedReveal.clear();
	if (!battle)
		return;
	const int n = battle->getMapSizeXYZ();
	if (n <= 0)
		return;
	g_publishedReveal.resize((std::size_t)n, 0u);
	int floors = 0;
	int voidCarried = 0;
	for (int i = 0; i < n; ++i)
	{
		Tile* t = battle->getTile(i);
		// TRACED 2026-09-02 (first RW-REVEAL-SYNC harness run: host live 1892
		// discovered floors vs client 1242 after a clean apply): "published"
		// means "the client already has it", and the client gets its baseline
		// from the BLOB - which does NOT carry every live bit. SavedBattleGame::
		// save() SKIPS void tiles entirely (SavedBattleGame.cpp:568-580, guard
		// `!_tiles[i].isVoid()`), and TileEngine::calculateTilesInFOV happily
		// marks empty AIR tiles along a line of sight discovered
		// (TileEngine.cpp:1645). Seeding those as published would strand them
		// forever: they are not in the blob and no later delta would report
		// them, because reveal is monotone (a bit already published is never
		// re-sent). Seed void tiles as ZERO instead - the host's very first
		// delta then re-ships them, and the two machines' live discovered sets
		// converge exactly. (Void tiles are also invisible to the saveBlob
		// hash for the same serialization reason, so this divergence class was
		// NOT hash-detectable - mapDiscoveredFloor equality is.)
		const std::uint8_t bits = t->isVoid() ? (std::uint8_t)0 : liveBits(t);
		g_publishedReveal[i] = bits;
		if (bits & 4)
			++floors;
		if (t->isVoid() && liveBits(t))
			++voidCarried;
	}
	Log(LOG_INFO) << "[coop-reveal] published bitmap seeded at the handshake blob snapshot ("
		<< n << " tiles, " << floors << " serialized floors already discovered, "
		<< voidCarried << " discovered VOID tiles deliberately left unpublished - the blob "
		"does not carry them, so the first delta must)";
}

bool hasUnpublished(SavedBattleGame* battle)
{
	std::lock_guard<std::mutex> lock(g_revealMutex);
	return computeDelta(battle, nullptr);
}

bool attachDelta(SavedBattleGame* battle, Json::Value& env)
{
	if (env.isMember("reveal"))
		return false; // an explicit restate the caller built (emitBaseRestate)

	std::lock_guard<std::mutex> lock(g_revealMutex);

	Json::Value delta(Json::objectValue);
	if (!computeDelta(battle, &delta))
		return false;

	if (g_revealDropNext)
	{
		// RB-D26 reveal_drop: the delta was computed AND published (so it is
		// never re-sent) but deliberately not attached. The client is then
		// permanently missing those bits - which, with the binTiles fog mask
		// removed, is exactly what the saveBlob bucket must now catch.
		g_revealDropNext = false;
		Log(LOG_WARNING) << "[coop-reveal] reveal_drop lever fired: dropped one reveal delta ("
			<< (delta["add"].size() / 2) << " tiles) - the client will never receive it";
		return false;
	}

	Log(LOG_INFO) << "[coop-reveal] attached reveal delta (" << (delta["add"].size() / 2u)
		<< " tiles) to " << env.get("state", "?").asString() << " kind="
		<< env.get("kind", "-").asString();

	env["reveal"] = delta;
	return true;
}

void flushQuiescent()
{
	if (!isCoopBattle())
		return;
	if (!coopBattleAuthority().hostSim)
		return;

	SavedBattleGame* battle = connectionTCP::getStaticBattle();
	if (!battle)
		return;

	// No coop action context open: SS2.4a's standalone ev is the carrier for
	// reveals OUTSIDE an action; an in-context reveal rides that action's own
	// ev/action_end through attachDelta() at the emit choke.
	if (CoopArbiter::currentActionId() != 0)
		return;

	// Chain quiescent. NOTE the null check is on getBattleState(), never on
	// getBattleGame(): SavedBattleGame::getBattleGame() dereferences
	// _battleState unconditionally (SavedBattleGame.cpp:1724-1727), and the HOST
	// legitimately sits in BriefingState - battle generated, phase already
	// Active (onReady), NO BattlescapeState - for the whole window between
	// battle_ready and its own OK click.
	BattlescapeGame* bg = battle->getBattleState() ? battle->getBattleGame() : nullptr;
	if (bg && bg->isBusy())
		return;

	bool wantBase = false;
	bool badN = false;
	{
		std::lock_guard<std::mutex> lock(g_revealMutex);
		if (g_revealBaseNext)
		{
			wantBase = true;
			badN = g_revealBaseBadN;
			g_revealBaseNext = false;
			g_revealBaseBadN = false;
		}
	}
	if (wantBase)
	{
		emitBaseRestate(battle, badN); // fires even with nothing unpublished
		return;
	}

	if (!hasUnpublished(battle))
		return; // idempotent: a second quiescent tick emits no second ev

	Json::Value ev = CoopWire::makeEv(0u, 0u, "reveal"); // actionId 0: no action chain
	ev["h"] = coopBuildUnitsStatsHash(battle); // RB-D14
	CoopEmit::sendEv(ev); // stamps the real seq AND attaches the delta at the choke
}

void applyFrom(SavedBattleGame* battle, const Json::Value& env)
{
	if (!battle || !env.isMember("reveal") || !env["reveal"].isObject())
		return;

	const Json::Value& d = env["reveal"];
	const int n = battle->getMapSizeXYZ();
	const std::uint32_t seq = env.get("seq", 0u).asUInt();
	const std::string kind = env.isMember("kind")
		? env.get("kind", "?").asString()
		: env.get("state", "?").asString();

	if (d.isMember("base"))
	{
		const int advertised = d.get("n", -1).asInt();
		if (advertised != n)
		{
			// SS2.4a: "n MUST equal the receiver's getMapSizeXYZ(); mismatch =
			// desync (freeze + bt_desync), never partial apply."
			Log(LOG_ERROR) << "[coop-reveal] base restate advertises n=" << advertised
				<< " but this machine's map is " << n << " tiles - DESYNC, nothing applied";
			coopRaiseBattleDesync("reveal", std::to_string(advertised), std::to_string(n), seq, kind);
			return;
		}
		std::vector<std::uint8_t> bytes;
		if (!b64Decode(d["base"].asString(), bytes) || (int)bytes.size() != n)
		{
			Log(LOG_ERROR) << "[coop-reveal] base restate payload decoded to "
				<< bytes.size() << " bytes, expected " << n << " - DESYNC, nothing applied";
			coopRaiseBattleDesync("reveal", std::to_string(n),
				std::to_string((int)bytes.size()), seq, kind);
			return;
		}
		int applied = 0;
		for (int i = 0; i < n; ++i)
			applied += applyBitsToTile(battle->getTile(i), bytes[(std::size_t)i]);
		Log(LOG_INFO) << "[coop-reveal] applied base restate at seq " << seq << " ("
			<< n << " tiles, " << applied << " parts newly discovered)";
		return;
	}

	if (!d.isMember("add") || !d["add"].isArray())
		return;

	const Json::Value& add = d["add"];
	if ((add.size() % 2u) != 0u)
	{
		Log(LOG_ERROR) << "[coop-reveal] malformed reveal add[] (odd length " << add.size()
			<< ") at seq " << seq << " - ignored";
		return;
	}

	int applied = 0;
	int skipped = 0;
	for (Json::ArrayIndex k = 0; k + 1u < add.size(); k += 2u)
	{
		const int idx = add[k].asInt();
		const int bits = add[k + 1u].asInt();
		if (idx < 0 || idx >= n)
		{
			++skipped;
			continue;
		}
		applied += applyBitsToTile(battle->getTile(idx), (std::uint8_t)bits);
	}
	if (skipped > 0)
	{
		Log(LOG_ERROR) << "[coop-reveal] " << skipped << " reveal index/indices out of range "
			"(this machine's map is " << n << " tiles) at seq " << seq
			<< " - the two machines' maps differ";
	}
	if (add.size() > 0)
	{
		Log(LOG_INFO) << "[coop-reveal] applied add delta at seq " << seq << " ("
			<< (add.size() / 2u) << " tiles, " << applied << " parts newly discovered)";
	}
}

void reset()
{
	std::lock_guard<std::mutex> lock(g_revealMutex);
	g_publishedReveal.clear();
	g_revealDropNext = false;
	g_revealBaseNext = false;
	g_revealBaseBadN = false;
}

void requestDropNextDelta()
{
	std::lock_guard<std::mutex> lock(g_revealMutex);
	g_revealDropNext = true;
}

void requestBaseRestate(bool badN)
{
	std::lock_guard<std::mutex> lock(g_revealMutex);
	g_revealBaseNext = true;
	g_revealBaseBadN = badN;
}

} // namespace CoopReveal

namespace CoopPump
{

void enqueue(const Json::Value& evOrEnd)
{
	std::lock_guard<std::mutex> lock(g_battleApplyQueueMutex);
	g_battleApplyQueue.push_back(evOrEnd);
}

void drainApplyQueue()
{
	for (;;)
	{
		Json::Value ev;
		bool gap = false;
		uint32_t seq = 0;
		uint32_t expected = 0;

		{
			std::lock_guard<std::mutex> lock(g_battleApplyQueueMutex);

			if (g_battleFrozen.load())
				return; // frozen: a later packet (R2-P9/BattleAuthority) clears this

			if (g_battleApplyQueue.empty())
				return;

			seq = g_battleApplyQueue.front().get("seq", 0u).asUInt();
			expected = g_battleLastSeqApplied.load() + 1;

			if (seq != expected)
			{
				// Leave the offending entry queued (peek, not pop) - a later
				// packet's desync report may want its payload. Never applied.
				// Copy (not move) it into ev purely so the log line below can
				// report its kind.
				gap = true;
				ev = g_battleApplyQueue.front();
				g_battleFrozen.store(true);
			}
			else
			{
				ev = std::move(g_battleApplyQueue.front());
				g_battleApplyQueue.pop_front();
			}
		}

		if (gap)
		{
			Log(LOG_ERROR) << "[coop-pump] SEQ GAP: expected " << expected << " got " << seq
				<< " (kind=" << ev.get("kind", "?").asString()
				<< ") - freezing battle input (protocol bug; RB-D5/SS2.2 strict in-order apply)";
			return;
		}

		g_battleLastSeqApplied.store(seq);

		// R2-P11 (RB-D32): CLIENT-side event-ring record point - see
		// BattlePump.h's CoopEventLog doc comment for why this call site
		// (post seq-order-check, pre-apply) is the client's half of the
		// ring's "populated at emit/apply" split.
		CoopEventLog::record(ev);

		// R3-P1 applies payload here.
		CoopDisplayQueue::onApplied(ev);

		// R2-P9 (SS2.8): post-apply hash verify - the correct call site
		// whether or not R3-P1's applier above has landed yet (its body is
		// currently a no-op; BattlePump.h's own doc comment on verify()
		// covers why this positioning is still correct once it does).
		CoopHashCheck::verify(ev);
	}
}

uint32_t lastSeqApplied()
{
	return g_battleLastSeqApplied.load();
}

uint32_t queueDepth()
{
	std::lock_guard<std::mutex> lock(g_battleApplyQueueMutex);
	return static_cast<uint32_t>(g_battleApplyQueue.size());
}

void reset()
{
	std::lock_guard<std::mutex> lock(g_battleApplyQueueMutex);
	g_battleApplyQueue.clear();
	g_battleLastSeqApplied.store(0u);
	g_battleFrozen.store(false);
	g_battleNextSeqMint = 1; // CoopEmit's host mint counter (SS2.2: reset by a new battle)
	g_battleTxDrainEvents.store(0); // R2-P11
	resetCoopArbiterState(); // R2-P5: action-context stack, actionId mint, deny-tick map
	CoopEventLog::reset(); // R2-P11
	CoopReveal::reset(); // RW-REVEAL-SYNC: published fog bitmap + its one-shot test levers
}

} // namespace CoopPump

namespace CoopEmit
{

uint32_t nextSeq()
{
	return g_battleNextSeqMint++;
}

uint32_t lastSeqEmitted()
{
	// g_battleNextSeqMint starts at 1 (SS2.2) and is the NEXT value nextSeq()
	// will hand out - so "the last one it actually handed out" is one less,
	// which is also 0 (SS2.2's "none yet") exactly when nothing has minted.
	return g_battleNextSeqMint - 1;
}

uint32_t txDrainEvents()
{
	return g_battleTxDrainEvents.load();
}

// MN-8: on g_txQ overflow for a battle message, BLOCK (bounded wait +
// watchdog log) instead of dropping - bypasses enqueueTx()'s drop-newest
// behavior (defined further below). Only ever pushes the raw (unframed)
// payload into the SAME g_txQ the socket threads already drain via their
// own g_txQ.pop + sendAll loops, so framing/sending stays exactly where it
// already lives (REVIEW3 F3: never call sendAll from the pump/emit thread).
static void coopEmitBlockingPush(std::string payload)
{
	using namespace std::chrono;
	const auto start = steady_clock::now();
	bool warned = false;
	bool drained = false;

	while (!g_txQ.push(std::move(payload)))
	{
		if (!drained)
		{
			drained = true;
			g_battleTxDrainEvents.fetch_add(1); // R2-P11: event_state's "txDrains"
		}
		if (onConnect < 0)
		{
			// Genuine transport death (connect lost / disconnect / server
			// error) - nothing will ever drain g_txQ again. Drop and log
			// instead of blocking the pump thread forever.
			Log(LOG_ERROR) << "[coop-emit] battle message dropped: transport is down"
				" (onConnect=" << onConnect << ")";
			return;
		}

		const auto elapsedMs = duration_cast<milliseconds>(steady_clock::now() - start).count();
		if (!warned && elapsedMs >= 250)
		{
			Log(LOG_WARNING) << "[coop-emit] TX queue full, battle emitter blocking"
				" (MN-8 bypass) - waited " << elapsedMs << "ms so far";
			warned = true;
		}

		std::this_thread::sleep_for(std::chrono::milliseconds(2));
	}
}

void sendBattle(Json::Value& msg)
{
	// Stamps nothing (SS2.2): the caller already set iseq/reason/etc. via
	// CoopWire's makers.
	Json::StreamWriterBuilder wb;
	wb["indentation"] = "";
	std::string s = Json::writeString(wb, msg);
	coopEmitBlockingPush(std::move(s));
}

void sendEv(Json::Value ev)
{
	// RW-REVEAL-SYNC (SS2.4a): THE single attachment point for host-authored fog
	// of war. Because every host emit - bt_ev of ANY kind and bt_action_end
	// alike - funnels through this one function, diffing here absorbs every
	// reveal writer (present and future, in-action or not) with zero per-atom
	// code. Host-only: a client never authors discovered bits (CoopReveal.h's
	// client authority rule).
	if (isCoopBattle() && coopBattleAuthority().hostSim)
		CoopReveal::attachDelta(connectionTCP::getStaticBattle(), ev);

	ev["seq"] = nextSeq();

	// R2-P11 (RB-D32): HOST-side event-ring record point - see BattlePump.h's
	// CoopEventLog doc comment for why this (post seq-mint, every host emit
	// path already funnels through this one function) is the host's half of
	// the "populated at emit/apply" split.
	CoopEventLog::record(ev);

	Json::StreamWriterBuilder wb;
	wb["indentation"] = "";
	std::string s = Json::writeString(wb, ev);
	coopEmitBlockingPush(std::move(s));
}

} // namespace CoopEmit

// R3-P1 fills CoopDisplayQueue::onApplied() below, after CoopApply/
// CoopArbiter (it needs CoopArbiter::onActionEndApplied() and the
// actionId->actorId correlation map, both defined further down this file) -
// see the "===== R3-P1: CoopApply" section near coopOnUnitTurnFinished.

// ===== R2-P11: flat event ring (BattlePump.h's CoopEventLog) =====
// SPIKE-RUNBOOK.md RB-D32/DESIGN sec 6 journaling guardrail 6. Storage is a
// plain fixed-size C array (never a std::vector/std::string) - see
// BattlePump.h's CoopEventLog doc comment for the "crash-handler-dumpable"
// rationale and which machine calls record() from where.

namespace CoopEventLog
{

namespace
{
Entry g_ring[kCapacity];
std::size_t g_head = 0;  // next write index
std::size_t g_count = 0; // entries currently held, capped at kCapacity
}

void record(const Json::Value& evOrEnd)
{
	Entry& e = g_ring[g_head];
	e.seq = evOrEnd.get("seq", 0u).asUInt();
	e.actionId = evOrEnd.get("actionId", 0u).asUInt();

	// bt_ev carries its own "kind" (turn/kneel/...); bt_action_end carries no
	// "kind" of its own (SS2.3) - fall back to "state" (e.g. "bt_action_end")
	// so every ring entry still has SOME distinguishing label.
	const std::string kindStr = evOrEnd.isMember("kind")
		? evOrEnd.get("kind", "").asString()
		: evOrEnd.get("state", "?").asString();
	std::strncpy(e.kind, kindStr.c_str(), sizeof(e.kind) - 1);
	e.kind[sizeof(e.kind) - 1] = '\0';

	e.hasHash = evOrEnd.isMember("h") && evOrEnd["h"].isObject() && evOrEnd["h"].size() > 0;

	g_head = (g_head + 1) % kCapacity;
	if (g_count < kCapacity)
		++g_count;
}

std::size_t size()
{
	return g_count;
}

const Entry& at(std::size_t indexFromOldest)
{
	const std::size_t oldest = (g_head + kCapacity - g_count) % kCapacity;
	return g_ring[(oldest + indexFromOldest) % kCapacity];
}

void reset()
{
	g_head = 0;
	g_count = 0;
}

} // namespace CoopEventLog

// ===== R2-P3: BattleAuthority (BattleAuthority.h) =====
// SPIKE-RUNBOOK.md RB-D6/RB-D17. The single global instance is defined here
// (function-local static, RB-D6) - not a file-scope global like the queues
// above, since coopBattleAuthority() is its only accessor and a
// function-local static gives the same one-instance guarantee with
// guaranteed zero-init ordering relative to other TUs' static init.

// Forward declaration: CoopArbiter::findUnitById() is R2-P5's internal
// actorId-resolution helper, defined further down inside `namespace
// CoopArbiter` (this file's CoopArbiter section) as a static (internal-
// linkage) function - reopening the namespace here only forward-declares
// it, it is NOT redefined. R5-P2's commandsUnit() MC override (below)
// reuses it (fully qualified as CoopArbiter::findUnitById, since this
// section sits at OpenXcom scope, outside namespace CoopArbiter) rather
// than duplicating a second unit-by-id linear scan - it already works
// identically on host and client (both own a live SavedBattleGame with
// every unit pointer), unlike CoopIdMaps.h's client-only id maps (RB-D7).
namespace CoopArbiter { static BattleUnit* findUnitById(SavedBattleGame* save, int id); }

BattleAuthority& coopBattleAuthority()
{
	static BattleAuthority instance;
	return instance;
}

int BattleAuthority::factionOf(int seat) const
{
	if (seat >= 0 && seat < kMaxSeats && _seatFaction[seat] != kUnmapped)
		return _seatFaction[seat];

	// R5-P1 real seatMap: RB-D18's interim classic/SHARED map has no
	// non-player seats, so every unmapped/out-of-range seat safely defaults
	// to FACTION_PLAYER in the spike; gm2/gm3/gm4 land their own map here.
	return (int)FACTION_PLAYER;
}

bool BattleAuthority::mySideActive(const SavedBattleGame* s) const
{
	if (!s)
		return false;
	return (int)s->getSide() == factionOf(localSeat);
}

bool BattleAuthority::commandsUnit(const BattleUnit* u) const
{
	if (!u)
		return false;

	// R5-P2 mcId override (see BattleAuthority.h doc comment, ADDENDUM MJ-8/
	// R2-M4): "controlled" is faction != originalFaction, not a raw mcId
	// check. When controlled, resolve the mcId unit (CoopArbiter::
	// findUnitById works on both host and client, unlike CoopIdMaps.h's
	// client-only maps) and use ITS seat tag; if it doesn't resolve,
	// ownership falls to host/AI (seat 0 only).
	if (u->getFaction() != u->getOriginalFaction())
	{
		BattleUnit* controller = CoopArbiter::findUnitById(connectionTCP::getStaticBattle(), u->getMindControllerId());
		if (controller)
			return (int)controller->getCoopSeat() == localSeat;
		return localSeat == 0; // host/AI fallback (seat 0 = host, SS2.2)
	}

	return (int)u->getCoopSeat() == localSeat;
}

bool BattleAuthority::isSpectator() const
{
	return localSeat < 0 || factionOf(localSeat) != (int)FACTION_PLAYER;
}

void BattleAuthority::setSeatFaction(int seat, int faction)
{
	if (seat >= 0 && seat < kMaxSeats)
		_seatFaction[seat] = faction;
}

void BattleAuthority::resetSeatFactions()
{
	for (int i = 0; i < kMaxSeats; ++i)
		_seatFaction[i] = kUnmapped;
}

void initBattleAuthority(std::uint32_t battleId)
{
	BattleAuthority& a = coopBattleAuthority();
	// RB-D6: hostSim is a ONE-TIME read of getServerOwner() here - immutable
	// for the rest of the battle after this call. Never read getServerOwner()
	// (or getHost()) again for battle-logic decisions; read a.hostSim.
	a.hostSim = connectionTCP::getServerOwner();
	a.localSeat = connectionTCP::localSeat();
	a.phase = CoopBattlePhase::Handshake;
	a.battleId = battleId;
	a.desyncFrozen = false; // R2-P9: a fresh battle always starts unfrozen
	a.resetSeatFactions();
}

void resetBattleAuthority()
{
	BattleAuthority& a = coopBattleAuthority();
	a.hostSim = false;
	a.localSeat = -1;
	a.phase = CoopBattlePhase::Idle;
	a.battleId = 0;
	a.desyncFrozen = false; // R2-P9
	a.resetSeatFactions();
}

bool isCoopBattle()
{
	return connectionTCP::getCoopStatic() && coopBattleAuthority().phase == CoopBattlePhase::Active;
}

// R5-P2 (SPIKE-RUNBOOK.md R5-P2 packet text): the input-gating combinators.
// Self-guarded (permissive outside an active coop battle) so every vanilla
// thin-hook call site stays a single unconditional call.
bool coopMayCommand(const BattleUnit* u, const SavedBattleGame* s)
{
	if (!isCoopBattle())
		return true;
	return coopBattleAuthority().commandsUnit(u) && coopBattleAuthority().mySideActive(s);
}

bool coopMaySelectUnit(const BattleUnit* u)
{
	if (!isCoopBattle())
		return true;
	return coopBattleAuthority().commandsUnit(u);
}

// ===== R2-P4: CLIENT-side id -> pointer maps (CoopIdMaps.h) =====
// SPIKE-RUNBOOK.md RB-D7. Storage lives here, next to the other coop
// singletons (BattleAuthority above, CoopPump/CoopEmit further up) - file-
// scope globals, same reasoning as g_battleApplyQueue etc: CoopIdMaps::reset()
// (R2-P8 teardown wiring) needs to clear them from outside this TU's ctor.
//
// R4-P1 cross-thread fix (see BattleAuthority.h's note above CoopBattlePhase):
// handleUdpRemotePeerLost() can call CoopIdMaps::reset() from the UDP-monitor
// thread while the main/pump thread reads/writes these maps (rebuildFrom() at
// battle-blob load, forget()/registerUnit() etc. once R3's appliers land).
// g_coopIdMapsMutex guards every CoopIdMaps:: function body below - since
// g_coopUnitById/g_coopItemById are `static` (this TU only) and reached ONLY
// through these functions, this closes the race for every existing and future
// call site without any call site needing to change.
static std::mutex g_coopIdMapsMutex;
static std::unordered_map<int, BattleUnit*> g_coopUnitById;
static std::unordered_map<int, BattleItem*> g_coopItemById;

namespace CoopIdMaps
{

// R4-P1 calls rebuildFrom here: at the point in the new client battle-blob
// load path (SPIKE-RUNBOOK.md SS2.7 battle_ready sequence, after sha verify
// and the blob is loaded into a live SavedBattleGame) where the client's
// SavedBattleGame first becomes valid, immediately before the authority
// {hostSim:false, localSeat, phase:Active} stamp. Landed this packet -
// CoopHandshake::onBlobChunkAppended()'s finishLoad step (connectionTCP.cpp,
// CoopHandshake implementation below) is that call site.
void rebuildFrom(SavedBattleGame* save)
{
	std::lock_guard<std::mutex> lock(g_coopIdMapsMutex);

	g_coopUnitById.clear();
	g_coopItemById.clear();

	if (!save)
		return; // matches reset() - callable defensively before a battle exists

	// RB-D24 counter-parity finding (R2-P4, verified against
	// SavedBattleGame.cpp @911ca487f): vanilla SavedBattleGame::load() does
	// NOT persist _itemId as a document field at all (BattleItem::save only
	// ever writes the per-item "id", BattleItem.cpp:139) - instead load()
	// RE-DERIVES it unconditionally, every time, as it scans the loaded
	// items: "_itemId = std::max(_itemId, item->getId())" per item
	// (SavedBattleGame.cpp:342) followed by a single "_itemId++"
	// (SavedBattleGame.cpp:347). That derivation already equals exactly the
	// max(item id)+1 RB-D24 would otherwise ask this function to compute.
	// So: for any SavedBattleGame that reached this point via vanilla
	// load() (the only battle-load path that will exist once R4-P1 lands -
	// see the file-level "R4-P1 calls rebuildFrom here" marker below),
	// _itemId is ALREADY correct by construction and this function does not
	// need to touch it. No CoopMod-side re-derivation is added here (and
	// per RB-D24, none would ever be added to the vanilla load() itself) -
	// this comment IS the disposition, not a placeholder for one.

	std::vector<BattleUnit*>* units = save->getUnits();
	if (units)
	{
		for (BattleUnit* u : *units)
		{
			if (u)
				g_coopUnitById[u->getId()] = u;
		}
	}

	std::vector<BattleItem*>* items = save->getItems();
	if (items)
	{
		for (BattleItem* i : *items)
		{
			if (i)
				g_coopItemById[i->getId()] = i;
		}
	}
}

BattleUnit* unit(int id)
{
	std::lock_guard<std::mutex> lock(g_coopIdMapsMutex);
	auto it = g_coopUnitById.find(id);
	return it != g_coopUnitById.end() ? it->second : nullptr;
}

BattleItem* item(int id)
{
	std::lock_guard<std::mutex> lock(g_coopIdMapsMutex);
	auto it = g_coopItemById.find(id);
	return it != g_coopItemById.end() ? it->second : nullptr;
}

void registerItem(BattleItem* i)
{
	std::lock_guard<std::mutex> lock(g_coopIdMapsMutex);
	if (i)
		g_coopItemById[i->getId()] = i;
}

void registerUnit(BattleUnit* u)
{
	std::lock_guard<std::mutex> lock(g_coopIdMapsMutex);
	if (u)
		g_coopUnitById[u->getId()] = u;
}

void forget(int itemId)
{
	std::lock_guard<std::mutex> lock(g_coopIdMapsMutex);
	g_coopItemById.erase(itemId);
}

void forgetUnit(int unitId)
{
	std::lock_guard<std::mutex> lock(g_coopIdMapsMutex);
	g_coopUnitById.erase(unitId);
}

void reset()
{
	std::lock_guard<std::mutex> lock(g_coopIdMapsMutex);
	g_coopUnitById.clear();
	g_coopItemById.clear();
}

} // namespace CoopIdMaps

// ===== R2-P5: admission arbiter (CoopArbiter.h) =====
// SPIKE-RUNBOOK.md RB-D9/RB-D10/RB-D11/RB-D12/RB-D13/RB-D19, SS2.3/SS2.5/
// SS2.6. Storage lives here, next to BattleAuthority/CoopIdMaps/CoopPump/
// CoopEmit above - same file-scope-global pattern (RB-D6/RB-D7).

// RB-D12: the action-context stack. In spike scope at most one entry is ever
// on it at a time (the "busy" check below denies everything else while an
// entry is present) - a real vector-backed stack anyway, matching the given
// push/current API shape, so a later packet admitting overlapping actions
// does not need a new data structure.
struct CoopActionContextEntry
{
	std::uint32_t actionId;
	std::string origin;
};
static std::vector<CoopActionContextEntry> g_coopActionContextStack;

// Host mint counter for actionId (SS2.2: uint32, starts at 1 per battle,
// monotonic, never reused - a DEDICATED counter, separate from CoopEmit's
// own seq mint, per the R2-P5 packet text).
static std::uint32_t g_coopActionIdMint = 1;

// Which actor a chain-ful (turn) action in flight belongs to, so
// CoopArbiter::onChainQuiesced() can read its post-chain state for
// bt_action_end.final. NOT part of the public {actionId, origin} stack
// above (RB-D12's shape has no room for an actor id) - CoopArbiter's own
// internal bookkeeping only, maintained 1:1 alongside the stack's top entry.
static int g_coopPendingChainActorId = -1;

// Oldest-denied-seat-first bookkeeping (SS2.5): per-seat tick of the most
// recent deny, written by CoopArbiter's deny() helper and consulted (read,
// never reordered - the spike is deny-only, no host-side queue, SS2.5/the
// SEAM note in CoopArbiter.h) at CoopArbiter::onChainQuiesced(). A
// ready-made fairness signal for a future post-v1 host-side queue; inert
// today.
static std::map<int, std::uint32_t> g_coopLastDenyTick;

// R2-P11 (RB-D32): the CLIENT-side iseq mint sendClientIntent() uses - a
// DEDICATED counter, separate from the HOST-side actionId mint above (SS2.2:
// iseq is "client-local monotonic per battle", a different id space than
// actionId's host-minted one). Main/pump-thread only, same as every other
// CoopArbiter static here.
static std::uint32_t g_coopClientNextIseq = 1;

// R3-P1: the turn atom's "before" state, captured at admission
// (CoopArbiter::onIntent()'s turn branch) or at a host-local turn's begin
// (CoopArbiter::beginHostLocalTurn()), read back by the THIN
// UnitTurnBState::think() completion/abort hook (coopOnUnitTurnFinished,
// below) to build the bt_ev turn payload's fromDir/turretFrom/turretOnly
// fields. Not part of the public {actionId, origin} action-context stack
// above (RB-D12's shape has no room for it) - valid only while
// g_coopPendingChainActorId (above) names the SAME unit; at most one coop
// turn/kneel chain is ever in flight at a time (SS2.5 deny-only
// serialization), so a single slot (never cleared explicitly - always
// overwritten by the next chain's begin before its own read) is correct.
struct CoopPendingTurnInfo
{
	int fromDir = -1;
	int fromTurretDir = -1;
	bool turretOnly = false;
};
static CoopPendingTurnInfo g_coopPendingTurnInfo;

// R3-P1 (REVIEW4 IR-2): this CLIENT's own intent lifecycle tracker. The
// packet text's ClientIntentState.inFlight shape, given its own struct/
// counter here rather than a second, redundant iseq mint - nextIseq is
// already g_coopClientNextIseq above (sendClientIntent()'s own counter);
// actionId is added to the given shape (needed so onActionEndApplied() can
// recognize "my own" bt_action_end, which carries no iseq of its own,
// SS2.3 - the packet text's "bt_ack records actionId" line requires
// somewhere to put it).
struct CoopClientInFlight
{
	std::uint32_t iseq = 0;
	std::string kind;
	int actorId = -1;
	std::uint32_t actionId = 0;
	bool active = false;
	// R2-P7: the concrete PLAN fields (SS2.3), added so a busy deny can move
	// this intent into the pending slot below and resubmit it later. Only the
	// plan is kept - never tuBasis: the packet text requires a resubmit to
	// RECOMPUTE the preview + basis against current client state, which
	// sendClientIntent() already does whenever no override is passed.
	int toDir = -1;
	bool turret = false;
	bool kneel = false;
};
static CoopClientInFlight g_coopClientInFlight;

// R2-P7 (SPIKE-RUNBOOK.md R2-P7 packet text, "Common core"): the PENDING slot
// - a busy-denied intent held for auto-resubmit instead of R3-P1's
// banner-and-drop. One slot, mirroring the single in-flight slot above (the
// admission model is deny-only serialization, SS2.5: there is never more than
// one thing this client can usefully be waiting to land). Cleared by an
// admitted resubmit, by the info-cancel policy, by the user cancel control,
// or at battle teardown.
struct CoopClientPending
{
	bool active = false;
	std::string kind;
	int actorId = -1;
	int toDir = -1;
	bool turret = false;
	bool kneel = false;
	std::uint32_t deniedIseq = 0; // the iseq whose deny("busy") created this
};
static CoopClientPending g_coopClientPending;

// R2-P7 (RB-D26/RB-D32 family, owner-approved 2026-09-02): the hold_chain
// test lever's state.
// TEST-ONLY STOPGAP (owner 2026-09-02): delete/replace with a real shot-based busy once the shot atom lands (r3 fan-out) - a slow auto-shot is the natural long chain.
static std::uint32_t g_coopHoldChainMs = 0;   // armed duration; 0 = disarmed
static bool g_coopHoldChainHolding = false;   // a chain is currently held open
static std::chrono::steady_clock::time_point g_coopHoldChainUntil;

// R3-P1 (IR-2): ClientIntentState.lastDeny - the {iseq,reason} object from
// the most recent bt_deny this CLIENT received, or null (Json::Value()'s
// default) if none yet this battle. event_state's own field (R2-P11's
// RW-TODO(R3-P1) marker in TestServer.cpp).
static Json::Value g_coopClientLastDeny;

// R3-P1: purely client-side actionId -> actorId correlation. Neither
// bt_ev's "unit" field nor bt_action_end carry both together on the wire
// (SS2.3/SS2.4 - bt_action_end has no "unit" field at all), so a client
// that is not the acting seat still needs a way to know which unit a later
// bt_action_end (same actionId) belongs to. Populated by
// CoopDisplayQueue::onApplied() when it applies a bt_ev carrying a "unit"
// payload field; consumed (and erased) when the matching bt_action_end
// applies.
static std::map<std::uint32_t, int> g_coopClientActionActor;

// CoopPump::reset() (BattlePump.h/R2-P2) is the established single
// battle-teardown reset chokepoint (R2-P8 wires its call site); extending
// its body here keeps CoopArbiter's own battle-scoped statics from leaking
// into a following battle without adding new public API surface.
static void resetCoopArbiterState()
{
	g_coopActionContextStack.clear();
	g_coopActionIdMint = 1;
	g_coopPendingChainActorId = -1;
	g_coopLastDenyTick.clear();
	g_coopClientNextIseq = 1;
	g_coopPendingTurnInfo = CoopPendingTurnInfo();
	g_coopClientInFlight = CoopClientInFlight();
	g_coopClientLastDeny = Json::Value();
	g_coopClientActionActor.clear();
	// R2-P7: the pending slot + the hold_chain lever are battle-scoped too.
	g_coopClientPending = CoopClientPending();
	g_coopHoldChainMs = 0;
	g_coopHoldChainHolding = false;
}

// R2-P9 (SPIKE-RUNBOOK.md SS2.8): render a bucket's uint64 as the 16-
// lowercase-hex-char string the wire's "h" object carries (SS2.2's `h` type:
// "JSON cannot carry uint64"). File-scope (not CoopArbiter-internal): also
// used by CoopHandshake's saveBlob field and by CoopHashCheck::verify's own
// recompute-and-compare below.
static std::string coopHex64(std::uint64_t v)
{
	char buf[17];
	std::snprintf(buf, sizeof(buf), "%016llx", (unsigned long long)v);
	return std::string(buf);
}

// R2-P9 (RB-D14): the `h:{unitsStats}` bucket every spike turn/kneel ev and
// action_end carries. One bucket only (RB-D14's own rationale: "one cheap
// bucket buys per-event divergence attribution during the calibration
// spike" - walk/shot/etc. atoms are post-spike and may carry more). Built
// via SharedEcon::computeBattleHashes() - the ported SS2.8 sweep - never a
// second hand-rolled hasher.
static Json::Value coopBuildUnitsStatsHash(SavedBattleGame* save)
{
	Json::Value h(Json::objectValue);
	SharedEcon::BattleHashSet buckets;
	if (SharedEcon::computeBattleHashes(save, buckets))
	{
		h["unitsStats"] = coopHex64(buckets.unitsStats);
	}
	return h;
}

namespace CoopArbiter
{

// ----- internal helpers (file-scope; not part of the CoopArbiter.h API) -----

static BattleUnit* findUnitById(SavedBattleGame* save, int id)
{
	if (!save || id < 0)
		return nullptr;
	std::vector<BattleUnit*>* units = save->getUnits();
	if (!units)
		return nullptr;
	for (BattleUnit* u : *units)
	{
		if (u && u->getId() == id)
			return u;
	}
	return nullptr;
}

// UnitFallBState.cpp:96-99's own "falling" predicate, reproduced purely from
// BattleUnit accessors (no SavedBattleGame needed) so it fits inside
// validateTurn()/validateKneel()'s frozen (no-save-param) signatures.
static bool isUnitFalling(const BattleUnit* u)
{
	return u->haveNoFloorBelow()
		&& u->getPosition().z != 0
		&& u->getMovementType() != MT_FLY
		&& u->getWalkingPhase() == 0;
}

static void popActionContext()
{
	if (!g_coopActionContextStack.empty())
		g_coopActionContextStack.pop_back();
}

static std::uint32_t mintActionId()
{
	return g_coopActionIdMint++;
}

static void recordDeny(int seat)
{
	if (seat >= 0)
		g_coopLastDenyTick[seat] = SDL_GetTicks();
}

static void clearDeny(int seat)
{
	g_coopLastDenyTick.erase(seat);
}

static void deny(std::uint32_t iseq, const char* reason, int seat)
{
	Json::Value msg = CoopWire::makeDeny(iseq, reason);
	CoopEmit::sendBattle(msg);
	recordDeny(seat);
}

static Json::Value buildFinal(const BattleUnit* u)
{
	Json::Value pos(Json::objectValue);
	pos["x"] = u->getPosition().x;
	pos["y"] = u->getPosition().y;
	pos["z"] = u->getPosition().z;

	Json::Value final(Json::objectValue);
	final["pos"] = pos;
	final["dir"] = u->getDirection();
	final["tu"] = u->getTimeUnits();
	final["energy"] = u->getEnergy();
	final["kneeled"] = u->isKneeled();
	return final;
}

// ----- CoopArbiter.h API -----

void pushActionContext(std::uint32_t actionId, const char* origin)
{
	g_coopActionContextStack.push_back(CoopActionContextEntry{ actionId, origin ? origin : "" });
}

std::uint32_t currentActionId()
{
	return g_coopActionContextStack.empty() ? 0u : g_coopActionContextStack.back().actionId;
}

const char* validateTurn(const BattleUnit* unit, int toDir, bool turret, int tuBasis)
{
	// Well-formedness (SS2.5's "turn well-formedness" bullet: actor exists,
	// alive, not falling; toDir in 0..7). None of these has a dedicated
	// SS2.2 deny reason of its own - mapped to cost_changed, the closest
	// existing enum meaning ("the intent's basis no longer matches host
	// reality") - see this packet's final report for the gap.
	if (!unit)
		return "cost_changed";
	if (unit->isOut())
		return "cost_changed";
	if (isUnitFalling(unit))
		return "cost_changed";
	if (toDir < 0 || toDir > 7)
		return "cost_changed";

	// cost_changed (SS2.3): recompute the SAME per-tick cost
	// UnitTurnBState::think() charges (UnitTurnBState.cpp:100:
	// "turret ? 1 : _unit->getTurnCost()") over the shortest-arc tick count
	// BattleUnit::turn() actually walks (BattleUnit.cpp:1286-1358's a<=4
	// branch - circular distance; the a==4 tie costs the same either way).
	const int fromDir = turret ? unit->getTurretDirection() : unit->getDirection();
	const int perTick = turret ? 1 : unit->getTurnCost();
	const int delta = ((toDir - fromDir) % 8 + 8) % 8;
	const int ticks = (delta <= 4) ? delta : (8 - delta);
	const int recomputed = ticks * perTick;

	if (recomputed != tuBasis)
		return "cost_changed";
	if (unit->getTimeUnits() < recomputed)
		return "cost_changed"; // basis matched but TU are short (SS2.3)

	return nullptr;
}

const char* validateKneel(const BattleUnit* unit, bool kneel, int tuBasis)
{
	if (!unit)
		return "cost_changed";
	if (unit->isOut())
		return "cost_changed";
	if (isUnitFalling(unit))
		return "cost_changed";

	// Kneel-capable precondition, replicated (not reimplemented) from
	// BattlescapeGame::kneel()'s own gate (BattlescapeGame.cpp:485) - only
	// the "can this unit kneel at all" half. The TU-reservation half of that
	// same vanilla condition ((!isKneeled && kneelReserved) ||
	// checkReservedTU(...)) is deliberately NOT replicated (see this
	// packet's final report): tuBasis/getTimeUnits() below already cover
	// the TU-sufficiency question this packet's validators own.
	if (!unit->getArmor()->allowsKneeling(unit->getType() == "SOLDIER") || unit->isFloating())
		return "cost_changed";

	// The requested end-state already holds - the client's basis was built
	// against a state that has since moved (someone else toggled this unit).
	if (kneel == unit->isKneeled())
		return "cost_changed";

	const int recomputed = unit->getKneelChangeCost(); // BattleUnit.h:788
	if (recomputed != tuBasis)
		return "cost_changed";
	if (unit->getTimeUnits() < recomputed)
		return "cost_changed";

	return nullptr;
}

void onIntent(const Json::Value& intent)
{
	if (!isCoopBattle())
	{
		Log(LOG_WARNING) << "[coop-arbiter] bt_intent received outside an active coop battle - dropped";
		return;
	}

	const std::uint32_t iseq = intent.get("iseq", 0u).asUInt();
	const int seat = intent.get("seat", -1).asInt();
	const int actorId = intent.get("actorId", -1).asInt();
	const std::string kind = intent.get("kind", "").asString();

	SavedBattleGame* save = connectionTCP::getStaticBattle();
	BattlescapeGame* bg = save ? save->getBattleGame() : nullptr;
	if (!save || !bg)
	{
		Log(LOG_WARNING) << "[coop-arbiter] bt_intent with no live battle - dropped";
		return;
	}

	BattleUnit* actor = findUnitById(save, actorId);

	// not_your_unit (SS2.3/SS2.5: "seat tag != intent seat"). Deliberately a
	// direct comparison, NOT coopBattleAuthority().commandsUnit(actor) - see
	// this packet's final report for why commandsUnit() (which compares
	// against THIS machine's own localSeat) is the wrong check for the host
	// validating a REMOTE seat's intent.
	if (!actor || (int)actor->getCoopSeat() != seat)
	{
		deny(iseq, "not_your_unit", seat);
		return;
	}

	// turn_over (SS2.3/SS2.5). Safe to use mySideActive() as-is (unlike
	// commandsUnit() above): RB-D16/RB-D18 mean every valid seat maps to
	// FACTION_PLAYER in the spike's classic/SHARED fixtures, so
	// factionOf(localSeat) == factionOf(seat) for any seat - the check is
	// seat-invariant in spike scope.
	if (!coopBattleAuthority().mySideActive(save))
	{
		deny(iseq, "turn_over", seat);
		return;
	}

	// busy (SS2.5): a BState chain active, OR this arbiter's own action
	// context is still on the stack awaiting its bt_action_end (covers the
	// same-tick edge where _states has just emptied but onChainQuiesced()
	// has not run yet).
	if (bg->isBusy() || currentActionId() != 0)
	{
		deny(iseq, "busy", seat);
		return;
	}

	if (kind == "turn")
	{
		const int toDir = intent.get("toDir", -1).asInt();
		const bool turret = intent.get("turret", false).asBool();
		const int tuBasis = intent.get("tuBasis", -1).asInt();

		const char* reason = validateTurn(actor, toDir, turret, tuBasis);
		if (reason)
		{
			deny(iseq, reason, seat);
			return;
		}

		const std::uint32_t actionId = mintActionId();
		Json::Value ack = CoopWire::makeAck(iseq, actionId);
		CoopEmit::sendBattle(ack);
		clearDeny(seat);
		pushActionContext(actionId, "intent"); // SS2.W7 / WV-D15
		g_coopPendingChainActorId = actor->getId();
		// R3-P1: capture the "before" state UnitTurnBState::think()'s
		// completion/abort hook (coopOnUnitTurnFinished) needs to build the
		// bt_ev turn payload's fromDir/turretFrom/turretOnly fields - BEFORE
		// the statePushBack() below runs lookAt()/turn() and mutates it.
		g_coopPendingTurnInfo.fromDir = actor->getDirection();
		g_coopPendingTurnInfo.fromTurretDir = actor->getTurretDirection();
		g_coopPendingTurnInfo.turretOnly = turret;

		// RB-D10 donor reproduction of BattlescapeGame::secondaryAction()
		// (BattlescapeGame.cpp:2011-2018) - NOT a call to secondaryAction
		// itself, which reads the LOCAL click cursor/ctrl-key state. A local
		// BattleAction is built here instead of touching bg's own
		// _currentAction (that member is the HOST's own live UI click state
		// - an admitted REMOTE intent must never alias it). The wire gives a
		// direction, not a click position, so a synthetic one-tile-away
		// target is built with Pathfinding::directionToVector() (the same
		// vector table BattleUnit::directionTo() itself decodes a Position
		// back out of, BattleUnit.cpp:1445-1487) so
		// UnitTurnBState::init()'s _unit->lookAt(_action.target, _turret)
		// resolves to exactly @a toDir. @a turret is honored directly (via
		// action.strafe) rather than rederived from Options::strafe/
		// isCtrlPressed() - those reflect the HOST's own local input, not
		// the validated wire intent.
		Position vec;
		Pathfinding::directionToVector(toDir, &vec);

		BattleAction action;
		action.actor = actor;
		action.target = actor->getPosition() + vec;
		action.strafe = turret;

		bg->statePushBack(new UnitTurnBState(bg, action));
		return;
	}

	if (kind == "kneel")
	{
		const bool wantKneel = intent.get("kneel", false).asBool();
		const int tuBasis = intent.get("tuBasis", -1).asInt();

		const char* reason = validateKneel(actor, wantKneel, tuBasis);
		if (reason)
		{
			deny(iseq, reason, seat);
			return;
		}

		const std::uint32_t actionId = mintActionId();
		Json::Value ack = CoopWire::makeAck(iseq, actionId);
		CoopEmit::sendBattle(ack);
		clearDeny(seat);
		pushActionContext(actionId, "intent"); // SS2.W7 / WV-D15
		// R3-P2: record @a actor as this kneel's pending chain actor BEFORE
		// calling kneel() below, so the THIN emit hook inside
		// BattlescapeGame::kneel() itself (coopOnKneelFinished) recognizes
		// it - mirrors onIntent()'s "turn" branch's own
		// g_coopPendingChainActorId bookkeeping above.
		g_coopPendingChainActorId = actor->getId();

		// RB-D13: kneel is chain-less - direct wrap of
		// BattlescapeGame::kneel() (BattlescapeGame.cpp:482), not a BState.
		// admit -> push context (above) -> call -> [THIN hook inside
		// kneel() itself: emit ev+action_end -> pop context]. R3-P2
		// generalizes the emit into that shared hook (coopOnKneelFinished,
		// this file, near coopOnUnitTurnFinished) so it fires identically
		// for this admitted-intent origin AND the host's own local kneel
		// click (beginHostLocalKneel + BattlescapeState::btnKneelClick,
		// RB-D10) - see this packet's final report for why the R2-P5
		// inline version this replaces could not also cover that second
		// origin.
		bg->kneel(actor);
		return;
	}

	Log(LOG_WARNING) << "[coop-arbiter] bt_intent unknown kind '" << kind
		<< "' - dropped (RB-D9: only turn/kneel validators exist in the spike)";
}

void onChainQuiesced()
{
	if (!isCoopBattle())
		return;

	if (g_coopActionContextStack.empty())
		return; // no coop action in flight - a foreign/AI popState, not ours

	// TEST-ONLY STOPGAP (owner 2026-09-02): delete/replace with a real shot-based busy once the shot atom lands (r3 fan-out) - a slow auto-shot is the natural long chain.
	// R2-P7 hold_chain lever (RB-D26/RB-D32 family): keep this chain
	// artificially OPEN so a second intent deterministically lands mid-chain
	// and gets a LIVE deny("busy"). Deferring HERE - before the bt_action_end
	// emit and before popActionContext() - is the minimal intercept: it leaves
	// currentActionId() != 0, which is exactly the arm of onIntent()'s SS2.5
	// busy check that a real long chain would trip. releaseHeldChainIfExpired()
	// (called unconditionally from the RB-D5 pump point) re-enters this
	// function once the window closes, and it then falls straight through.
	if (g_coopHoldChainMs > 0)
	{
		if (!g_coopHoldChainHolding)
		{
			g_coopHoldChainHolding = true;
			g_coopHoldChainUntil = std::chrono::steady_clock::now()
				+ std::chrono::milliseconds(g_coopHoldChainMs);
			Log(LOG_INFO) << "[coop-arbiter] hold_chain: HOLDING actionId " << currentActionId()
				<< " open for " << g_coopHoldChainMs << " ms - bt_action_end deferred, "
				"further intents will deny(busy) (TEST-ONLY STOPGAP)";
		}
		if (std::chrono::steady_clock::now() < g_coopHoldChainUntil)
			return; // still held
		g_coopHoldChainHolding = false;
		g_coopHoldChainMs = 0; // one-shot
	}

	SavedBattleGame* save = connectionTCP::getStaticBattle();
	const std::uint32_t actionId = currentActionId();
	BattleUnit* actor = findUnitById(save, g_coopPendingChainActorId);

	popActionContext();
	g_coopPendingChainActorId = -1;

	if (!actor)
	{
		Log(LOG_WARNING) << "[coop-arbiter] chain quiesced for actionId " << actionId
			<< " but its actor no longer resolves - bt_action_end skipped";
	}
	else
	{
		Json::Value end = CoopWire::makeActionEnd(0, actionId);
		end["final"] = buildFinal(actor);
		end["h"] = coopBuildUnitsStatsHash(save); // RB-D14
		CoopEmit::sendEv(end);
	}

	// Oldest-denied-seat-first bookkeeping (SS2.5): consulted here (read-only
	// - the spike is deny-only, see the SEAM note in CoopArbiter.h) so a
	// future host-side queue has a ready-made fairness signal.
	if (!g_coopLastDenyTick.empty())
	{
		auto oldest = std::min_element(g_coopLastDenyTick.begin(), g_coopLastDenyTick.end(),
			[](const std::pair<const int, std::uint32_t>& a, const std::pair<const int, std::uint32_t>& b)
			{
				return a.second < b.second;
			});
		Log(LOG_INFO) << "[coop-arbiter] quiesce: oldest-denied seat=" << oldest->first
			<< " (tick=" << oldest->second << ")";
	}
}

void beginHostLocalTurn(BattleUnit* actor, bool turret)
{
	if (!isCoopBattle() || !actor)
		return;

	// SS2.5: "host-local player input never enters the intent path" - this
	// runs on the HOST for its OWN click, never through onIntent(). Mirrors
	// onIntent()'s turn-branch bookkeeping exactly (mint, push, record
	// pending actor + "before" state) so coopOnUnitTurnFinished() and
	// onChainQuiesced() fire identically regardless of origin.
	const std::uint32_t actionId = mintActionId();
	pushActionContext(actionId, "host"); // RB-D19
	g_coopPendingChainActorId = actor->getId();
	g_coopPendingTurnInfo.fromDir = actor->getDirection();
	g_coopPendingTurnInfo.fromTurretDir = actor->getTurretDirection();
	g_coopPendingTurnInfo.turretOnly = turret;
}

void beginHostLocalKneel(BattleUnit* actor)
{
	if (!isCoopBattle() || !actor)
		return;

	// R3-P2: chain-less (RB-D13) counterpart to beginHostLocalTurn() above -
	// mirrors onIntent()'s "kneel" branch bookkeeping (mint, push, record
	// pending actor) so the THIN emit hook inside BattlescapeGame::kneel()
	// itself (coopOnKneelFinished) fires identically regardless of origin.
	// No "before" state to capture (unlike turn): the kneel ev only ever
	// carries the POST-kneel "kneeled" bool, trivially read back off @a
	// actor by the hook once kneel() returns.
	const std::uint32_t actionId = mintActionId();
	pushActionContext(actionId, "host"); // RB-D19
	g_coopPendingChainActorId = actor->getId();
}

std::uint32_t sendClientIntent(const char* kind, int actorId, int toDir,
	bool turret, bool kneel, int tuBasisOverride)
{
	const std::string kindStr = kind ? kind : "";

	if (!isCoopBattle())
	{
		Log(LOG_WARNING) << "[coop-arbiter] sendClientIntent('" << kindStr
			<< "') outside an active coop battle - dropped";
		return 0u;
	}

	// R3-P1 (REVIEW4 IR-2): "while active, input is locked for THE ACTING
	// UNIT ONLY" - refuse a second intent for the SAME unit while its first
	// one is still outstanding (unresolved bt_ack/bt_deny/bt_action_end). A
	// DIFFERENT unit's intent is not blocked here (deny-only serialization
	// means the host will just answer busy if it collides, which the packet
	// text calls "fine to send") - g_coopClientInFlight's single slot simply
	// gets overwritten below once this send actually goes out.
	if (g_coopClientInFlight.active && g_coopClientInFlight.actorId == actorId)
	{
		Log(LOG_WARNING) << "[coop-arbiter] sendClientIntent: actor " << actorId
			<< " already has an in-flight intent (iseq " << g_coopClientInFlight.iseq
			<< ") - input locked for this unit until its bt_action_end (IR-2) - dropped";
		return 0u;
	}

	SavedBattleGame* save = connectionTCP::getStaticBattle();
	if (!save)
	{
		Log(LOG_WARNING) << "[coop-arbiter] sendClientIntent('" << kindStr
			<< "') with no live battle - dropped";
		return 0u;
	}

	BattleUnit* actor = findUnitById(save, actorId);
	if (!actor)
	{
		Log(LOG_WARNING) << "[coop-arbiter] sendClientIntent: actorId " << actorId
			<< " does not resolve on this machine - dropped";
		return 0u;
	}

	int tuBasis = tuBasisOverride;

	if (kindStr == "turn")
	{
		if (tuBasis < 0)
		{
			// Same recompute validateTurn() does (this file, above): the
			// per-tick UnitTurnBState::think() cost over the shortest-arc tick
			// count BattleUnit::turn() walks - the client's OWN preview of
			// what the host is about to charge, not a copy of host state.
			const int fromDir = turret ? actor->getTurretDirection() : actor->getDirection();
			const int perTick = turret ? 1 : actor->getTurnCost();
			const int delta = ((toDir - fromDir) % 8 + 8) % 8;
			const int ticks = (delta <= 4) ? delta : (8 - delta);
			tuBasis = ticks * perTick;
		}
	}
	else if (kindStr == "kneel")
	{
		if (tuBasis < 0)
			tuBasis = actor->getKneelChangeCost(); // BattleUnit.h:788
	}
	else
	{
		Log(LOG_WARNING) << "[coop-arbiter] sendClientIntent: unknown kind '" << kindStr << "' - dropped";
		return 0u;
	}

	const std::uint32_t iseq = g_coopClientNextIseq++;
	Json::Value intent = CoopWire::makeIntent(iseq, coopBattleAuthority().localSeat, actorId, kind);
	if (kindStr == "turn")
	{
		intent["toDir"] = toDir;
		intent["turret"] = turret;
		intent["tuBasis"] = tuBasis;
	}
	else // "kneel"
	{
		intent["kneel"] = kneel;
		intent["tuBasis"] = tuBasis;
	}

	CoopEmit::sendBattle(intent);

	// R3-P1 (IR-2): this is now the one tracked in-flight intent (single
	// slot, overwriting whatever a DIFFERENT unit's still-unresolved intent
	// left behind - see the actor-lock check above for why that is safe).
	g_coopClientInFlight.iseq = iseq;
	g_coopClientInFlight.kind = kindStr;
	g_coopClientInFlight.actorId = actorId;
	g_coopClientInFlight.actionId = 0; // filled by onAck() below
	g_coopClientInFlight.active = true;
	// R2-P7: keep the concrete plan so a deny("busy") can hold and resubmit it.
	g_coopClientInFlight.toDir = toDir;
	g_coopClientInFlight.turret = turret;
	g_coopClientInFlight.kneel = kneel;

	return iseq;
}

void onAck(const Json::Value& ack)
{
	if (!isCoopBattle())
		return;

	const std::uint32_t iseq = ack.get("iseq", 0u).asUInt();
	if (g_coopClientInFlight.active && g_coopClientInFlight.iseq == iseq)
	{
		g_coopClientInFlight.actionId = ack.get("actionId", 0u).asUInt();
	}
}

void onDeny(const Json::Value& deny)
{
	if (!isCoopBattle())
		return;

	const std::uint32_t iseq = deny.get("iseq", 0u).asUInt();
	const std::string reason = deny.get("reason", "").asString();

	Json::Value ld(Json::objectValue);
	ld["iseq"] = iseq;
	ld["reason"] = reason;
	g_coopClientLastDeny = ld;

	const bool mine = (g_coopClientInFlight.active && g_coopClientInFlight.iseq == iseq);

	if (mine && reason == "busy")
	{
		// R2-P7 (packet text, "Common core"): HOLD the intent as PENDING and
		// auto-resubmit at the next event_state-visible quiescence, instead of
		// R3-P1's banner+drop. The plan (never the basis - the resubmit
		// recomputes it) moves across; the in-flight slot is released so the
		// acting unit is not left locked while it waits.
		g_coopClientPending.active = true;
		g_coopClientPending.kind = g_coopClientInFlight.kind;
		g_coopClientPending.actorId = g_coopClientInFlight.actorId;
		g_coopClientPending.toDir = g_coopClientInFlight.toDir;
		g_coopClientPending.turret = g_coopClientInFlight.turret;
		g_coopClientPending.kneel = g_coopClientInFlight.kneel;
		g_coopClientPending.deniedIseq = iseq;
		g_coopClientInFlight = CoopClientInFlight();

		Log(LOG_INFO) << "[coop-arbiter] deny(busy) on iseq " << iseq << " ("
			<< g_coopClientPending.kind << ", actor " << g_coopClientPending.actorId
			<< ") - HELD pending, auto-resubmit at the next quiescence (R2-P7)";
		// SS2.6: the pending banner IS the busy row's own string
		// (STR_COOP_DENY_BUSY, "Waiting - another action is in progress") -
		// reason-specific, never collapsed into a generic message
		// (ADDENDUM (e)); showPending() is the presenter entry point the
		// packet names for this state.
		CoopBattleUi::showPending("busy");
		return;
	}

	if (mine)
	{
		// Every other reason keeps R3-P1's banner + DROP behavior: those are
		// terminal answers about the plan itself (cost/target/ownership), not
		// a "try again in a moment".
		g_coopClientInFlight = CoopClientInFlight();
	}

	CoopBattleUi::showDeny(reason.c_str());
}

void onActionEndApplied(std::uint32_t actionId)
{
	if (g_coopClientInFlight.active && g_coopClientInFlight.actionId == actionId)
	{
		g_coopClientInFlight = CoopClientInFlight();

		// R2-P7: THIS client's own action just completed. If nothing else is
		// being held, the admission banner has served its purpose - drop it.
		// Without this an auto-retried intent that finally lands would leave
		// showPending()'s "Waiting - another action is in progress" on screen
		// forever (nothing else in the spike ever clears the banner). Guarded
		// on the pending slot so a SECOND unit's still-held order keeps its
		// own waiting message up.
		if (!g_coopClientPending.active)
			CoopBattleUi::clearPending();
	}
}

Json::Value lastDeny()
{
	return g_coopClientLastDeny;
}

// ----- R2-P7: CLIENT auto-retry + info-cancel (CoopArbiter.h API) -----

int visibleHostileCount()
{
	SavedBattleGame* save = connectionTCP::getStaticBattle();
	if (!save)
		return 0;

	const int mySeat = coopBattleAuthority().localSeat;
	std::set<int> seen;
	for (BattleUnit* u : *save->getUnits())
	{
		if (!u || u->isOut())
			continue;
		if ((int)u->getCoopSeat() != mySeat)
			continue; // only units THIS machine's seat commands
		for (const BattleUnit* v : *u->getVisibleUnits())
		{
			if (v && v->getFaction() == FACTION_HOSTILE)
				seen.insert(v->getId());
		}
	}
	return (int)seen.size();
}

Json::Value pendingIntent()
{
	if (!g_coopClientPending.active)
		return Json::Value();
	Json::Value p(Json::objectValue);
	p["kind"] = g_coopClientPending.kind;
	p["actorId"] = g_coopClientPending.actorId;
	p["iseq"] = g_coopClientPending.deniedIseq;
	return p;
}

bool cancelPendingIntent()
{
	if (!isCoopBattle() || !g_coopClientPending.active)
		return false;

	Log(LOG_INFO) << "[coop-arbiter] pending " << g_coopClientPending.kind
		<< " intent for actor " << g_coopClientPending.actorId
		<< " CANCELLED by the user (right-click/ESC cancel control, R2-P7)";
	g_coopClientPending = CoopClientPending();
	CoopBattleUi::clearPending();
	return true;
}

void onQuiescenceObserved()
{
	if (!isCoopBattle() || !g_coopClientPending.active)
		return;

	// Copy + clear FIRST: sendClientIntent() below re-enters this namespace's
	// own in-flight bookkeeping, and a failed send (actor gone, battle torn
	// down) must not leave a zombie pending behind.
	const CoopClientPending held = g_coopClientPending;
	g_coopClientPending = CoopClientPending();

	// The resubmit RECOMPUTES preview + tuBasis on CURRENT client state
	// (packet text): no tuBasisOverride is passed, so sendClientIntent()
	// re-derives the basis exactly as a fresh UI action would. A basis
	// captured before the blocker ran would be precisely the stale-basis bug
	// the cost_changed deny exists to catch.
	const std::uint32_t iseq = sendClientIntent(held.kind.c_str(), held.actorId,
		held.toDir, held.turret, held.kneel);

	if (iseq == 0u)
	{
		// Could not go out (see sendClientIntent()'s own logged reasons).
		// Drop the banner rather than leaving a "waiting" message with
		// nothing behind it.
		Log(LOG_WARNING) << "[coop-arbiter] auto-resubmit of the pending "
			<< held.kind << " intent for actor " << held.actorId
			<< " could not be sent - pending dropped (R2-P7)";
		CoopBattleUi::clearPending();
		return;
	}

	Log(LOG_INFO) << "[coop-arbiter] quiescence observed - auto-resubmitted the pending "
		<< held.kind << " intent for actor " << held.actorId << " as iseq " << iseq
		<< " (R2-P7)";
	// Banner stays up: still waiting, just on a fresh iseq. A deny("busy")
	// on this one re-enters the pending path above; an ack + bt_action_end
	// clears it through onActionEndApplied() below.
}

void onEvAppliedCancelCheck(const Json::Value& ev, int visibleBefore)
{
	if (!isCoopBattle() || !g_coopClientPending.active)
		return;

	const std::string kind = ev.get("kind", "").asString();

	// The four toggles are read LIVE here, per the packet text - never
	// mirrored into a static (REVIEW4 IR-9) and never consulted on the host
	// (this whole function only ever runs on a thin client's apply path).
	const char* cause = nullptr;

	// 1. coopCancelOnEnemySpotted (default ON): a `spot` ev applies.
	if (!cause && Options::coopCancelOnEnemySpotted && kind == "spot")
	{
		cause = "enemy_spotted";
	}

	// 2. coopCancelOnOwnUnitHit (default ON): a hit/death ev touching MY
	//    seat's units. The ev's payload `unit` is the SS2.4 unit field every
	//    unit-scoped ev carries; a hit/death ev without one cannot be
	//    attributed to a seat and therefore cannot trip this toggle.
	if (!cause && Options::coopCancelOnOwnUnitHit && (kind == "hit" || kind == "death"))
	{
		const Json::Value& payload = ev["payload"];
		if (payload.isMember("unit"))
		{
			const BattleUnit* u = CoopIdMaps::unit(payload["unit"].asInt());
			if (u && (int)u->getCoopSeat() == coopBattleAuthority().localSeat)
				cause = (kind == "death") ? "unit_down" : "unit_under_fire";
		}
	}

	// 3. coopCancelOnVisibilityGain (default ON): local-FOV visibility-gain
	//    check on apply (presentation-legal - purely machine-local D4 state,
	//    never hashed, never on the wire). @a visibleBefore was sampled by
	//    the caller BEFORE the payload apply + its targeted calculateFOV().
	if (!cause && Options::coopCancelOnVisibilityGain)
	{
		if (visibleHostileCount() > visibleBefore)
			cause = "new_contact";
	}

	// 4. coopCancelOnAnyPartnerAction (default OFF): the broad legacy-proposal
	//    behavior - ANY applied ev whose kind is not in the safe-list. Unknown/
	//    future ev kinds cancel ONLY here (owner-flagged decision 2026-08-31:
	//    mechanical plan-validation makes no-cancel safe for unclassified
	//    kinds), which is exactly what makes the three toggles above
	//    kind-specific rather than catch-all.
	//
	//    SAFE-LIST NOTE (disclosed judgment call, R2-P7 final report): the
	//    packet's own list is {walk_steps, turn, door, kneel}; "reveal" is
	//    added here because SS2.4a (the 2026-09-02 addendum, written AFTER
	//    this packet) defines `ev reveal` as a SYSTEM ev - the host's
	//    standalone baseline/catch-up fog carrier with no `unit` field and no
	//    actionId - not a partner ACTION. It is emitted by
	//    CoopReveal::flushQuiescent() at precisely the quiescence where a
	//    pending intent is about to be resubmitted, so treating it as a
	//    partner action would make this toggle cancel every held order it was
	//    supposed to let through.
	if (!cause && Options::coopCancelOnAnyPartnerAction)
	{
		const bool safeListed = (kind == "walk_steps" || kind == "turn"
			|| kind == "door" || kind == "kneel" || kind == "reveal");
		if (!safeListed)
			cause = ""; // no dedicated STR_ - falls through to STR_COOP_CANCEL_EVENT
	}

	if (!cause)
		return;

	Log(LOG_INFO) << "[coop-arbiter] pending " << g_coopClientPending.kind
		<< " intent for actor " << g_coopClientPending.actorId
		<< " CANCELLED by policy (cause='" << cause << "', ev kind='" << kind
		<< "', R2-P7)";
	g_coopClientPending = CoopClientPending();
	// SS2.6: a known cause gets its own STR_COOP_CANCEL_* string; the
	// unknown-kind path gets STR_COOP_CANCEL_EVENT with {0} = the ev kind.
	// Either way the message NAMES the trigger - never generic.
	CoopBattleUi::showCancel(cause, kind.c_str());
}

// ----- R2-P7: hold_chain test lever (HOST) -----

// TEST-ONLY STOPGAP (owner 2026-09-02): delete/replace with a real shot-based busy once the shot atom lands (r3 fan-out) - a slow auto-shot is the natural long chain.
void requestHoldChain(std::uint32_t ms)
{
	g_coopHoldChainMs = ms;
	g_coopHoldChainHolding = false;
	Log(LOG_INFO) << "[coop-arbiter] hold_chain armed: the next quiesced BState chain "
		"will be held open for " << ms << " ms (TEST-ONLY STOPGAP)";
}

// TEST-ONLY STOPGAP (owner 2026-09-02): delete/replace with a real shot-based busy once the shot atom lands (r3 fan-out) - a slow auto-shot is the natural long chain.
void releaseHeldChainIfExpired()
{
	if (!g_coopHoldChainHolding)
		return;
	if (std::chrono::steady_clock::now() < g_coopHoldChainUntil)
		return;

	Log(LOG_INFO) << "[coop-arbiter] hold_chain window expired - releasing the held chain "
		"(TEST-ONLY STOPGAP)";
	g_coopHoldChainHolding = false;
	g_coopHoldChainMs = 0; // one-shot
	onChainQuiesced();     // now runs its normal emit + pop
}

} // namespace CoopArbiter

void coopOnChainQuiesced()
{
	CoopArbiter::onChainQuiesced();
}

// R3-P1 (SPIKE-RUNBOOK.md UnitTurnBState.cpp:104/:116/:142 @911ca487f - see
// CoopArbiter.h's own doc comment on this function for the full contract).
// Kept outside namespace CoopArbiter for the same call-site-simplicity
// reason as coopOnChainQuiesced() above.
void coopOnUnitTurnFinished(BattleUnit* unit, bool aborted)
{
	if (!isCoopBattle() || !unit)
		return;
	if (g_coopPendingChainActorId != unit->getId())
		return; // a foreign/AI/SP turn - not coop's to report

	const std::uint32_t actionId = CoopArbiter::currentActionId();
	if (actionId == 0)
		return; // defensive: no action context even though the pending actor matched

	SavedBattleGame* save = connectionTCP::getStaticBattle();

	Json::Value ev = CoopWire::makeEv(0u, actionId, "turn");
	ev["payload"]["unit"] = unit->getId();
	ev["payload"]["fromDir"] = g_coopPendingTurnInfo.fromDir;
	ev["payload"]["toDir"] = unit->getDirection();
	ev["payload"]["turretOnly"] = g_coopPendingTurnInfo.turretOnly;
	// RW-FIX-TURRET: turretFrom/turretTo now ride EVERY turn ev, not only the
	// turretOnly ones. SS2.4 marks both fields optional/presence-gated
	// ("turretFrom?, turretTo?"), so always-present is inside the frozen
	// schema - no new field is invented here. They are REQUIRED for the client
	// to reproduce the host's exact post-state: vanilla BattleUnit::turn()
	// advances _directionTurret in lockstep with the body ONLY when
	// _turretType > -1 (BattleUnit.cpp:1326-1347 - the `if (_turretType > -1)`
	// guards inside each body-turn branch), so a turret-less soldier's turret
	// stays exactly where it was while a turreted unit's tracks the body by
	// one tick per body tick. The client cannot derive either case from
	// fromDir/toDir alone; it must be told. (Before this, a plain body turn
	// carried no turret field at all and the applier fell back to
	// setDirection(), which drags the turret onto the body facing -
	// BattleUnit.cpp:988-994 - producing the post-action saveBlob-only
	// `directionTurret` mismatch RCA'd 2026-09-02.)
	ev["payload"]["turretFrom"] = g_coopPendingTurnInfo.fromTurretDir;
	ev["payload"]["turretTo"] = unit->getTurretDirection();
	ev["payload"]["tuAfter"] = unit->getTimeUnits();
	// "door" is deliberately never set here: R3-P1 does not hook
	// UnitTurnBState::init()'s immediate zero-tick door-open branch
	// (UnitTurnBState.cpp:77 @911ca487f) - RB-D15's spike fixtures are
	// door-free by construction (REVIEW4 IR-4's own no-door-within-2-tiles
	// selection rule), so this packet's own repro never exercises it.
	// Door-in-turn rides the door atom, post-spike, per RB-D15's own text.
	ev["h"] = coopBuildUnitsStatsHash(save); // RB-D14
	CoopEmit::sendEv(ev);

	if (aborted)
	{
		Log(LOG_WARNING) << "[coop-turn] unit " << unit->getId()
			<< "'s coop-admitted turn ABORTED mid-chain - the RB-D15/REVIEW4 IR-4 "
			"fixture guards (empty spotted-set, no door within 2 tiles) should "
			"have prevented this in the spike's own repro";
	}
}

// R3-P2 (SPIKE-RUNBOOK.md RB-D13 - see CoopArbiter.h's own doc comment on
// this function for the full contract). Kept outside namespace CoopArbiter
// for the same call-site-simplicity reason as coopOnChainQuiesced()/
// coopOnUnitTurnFinished() above.
void coopOnKneelFinished(BattleUnit* unit, bool succeeded)
{
	if (!isCoopBattle() || !unit)
		return;
	if (g_coopPendingChainActorId != unit->getId())
		return; // a foreign/AI/SP kneel - not coop's to report

	const std::uint32_t actionId = CoopArbiter::currentActionId();
	if (actionId == 0)
		return; // defensive: no action context even though the pending actor matched

	SavedBattleGame* save = connectionTCP::getStaticBattle();

	if (succeeded)
	{
		Json::Value ev = CoopWire::makeEv(0u, actionId, "kneel");
		ev["payload"]["unit"] = unit->getId();
		ev["payload"]["kneeled"] = unit->isKneeled();
		ev["payload"]["tuAfter"] = unit->getTimeUnits();
		ev["h"] = coopBuildUnitsStatsHash(save); // RB-D14
		CoopEmit::sendEv(ev);
	}
	else
	{
		// validateKneel()'s own documented gap (its doc comment, this file):
		// the TU-RESERVATION half of vanilla kneel()'s precondition is not
		// replicated, so an admitted intent can rarely still fail here. The
		// halted-only action_end below still resolves the initiating
		// client's in-flight lock instead of leaving the whole battle
		// permanently "busy" (currentActionId() never clearing).
		Log(LOG_WARNING) << "[coop-kneel] unit " << unit->getId()
			<< "'s coop-admitted kneel FAILED post-validation (validateKneel's "
			   "own documented TU-reservation gap) - no ev emitted, halted "
			   "action_end only";
	}

	Json::Value end = CoopWire::makeActionEnd(0u, actionId);
	end["final"] = CoopArbiter::buildFinal(unit);
	end["h"] = coopBuildUnitsStatsHash(save);
	if (!succeeded)
		end["halted"] = true;
	CoopEmit::sendEv(end);

	CoopArbiter::popActionContext();
	g_coopPendingChainActorId = -1;
}

// ===== R3-P1: CoopApply (CoopApply.h) - the S2-minimal client-side state
// applier =====
// SPIKE-RUNBOOK.md R3-P1 packet text. Resolution is EXCLUSIVELY via
// CoopIdMaps (RB-D7) - nothing here mints a BattleUnit/BattleItem (RB-D25),
// but the region is marked per the packet text's own instruction anyway.
// RW-MINT-WHITELIST-BEGIN
namespace CoopApply
{

// RW-FIX-TURRET: write the BODY facing WITHOUT dragging the turret with it.
//
// Vanilla BattleUnit::setDirection() (BattleUnit.cpp:988-994) deliberately
// couples all four facing fields (_direction, _toDirection, _directionTurret,
// _toDirectionTurret) because vanilla only ever calls it for INITIAL UNIT
// PLACEMENT ("Only used for initial unit placement", its own doc comment).
// The host's real rotation never goes through it: UnitTurnBState::think()
// calls BattleUnit::turn() (UnitTurnBState.cpp:118), which advances
// _directionTurret only when _turretType > -1 (BattleUnit.cpp:1326-1347).
// So for a turret-less soldier the host's _directionTurret is UNCHANGED by a
// body turn, while the client's setDirection() rewrote it to the new body
// facing. `directionTurret` is serialized unconditionally
// (BattleUnit.cpp:717), is read by NO structured hash bucket, and is not on
// saveBlobExcludedUnitKey's list (SharedEcon.cpp) - so the saveBlob catch-all
// caught the drift as a post-action-only, saveBlob-only mismatch (RCA
// 2026-09-02). Body write + turret restore through the R3-P1 additive
// setTurretDirection() accessor keeps the vanilla file untouched; the caller
// then writes the turret from the ev's own turretTo - the host's real
// post-state - and never from a local guess.
static void setBodyDirectionKeepTurret(BattleUnit* unit, int dir)
{
	const int turret = unit->getTurretDirection();
	unit->setDirection(dir);
	unit->setTurretDirection(turret);
}

void applyEvPayload(SavedBattleGame* save, const Json::Value& ev)
{
	if (!save)
		return;

	const std::string kind = ev.get("kind", "").asString();

	if (kind == "reveal")
	{
		// RW-REVEAL-SYNC (SS2.4a): the standalone reveal carrier has NO `unit`
		// field and no payload of its own - its entire state effect is the
		// envelope-level `reveal` object, already applied by
		// CoopDisplayQueue::onApplied() before it reached here. A known kind,
		// deliberately not an RW-UNSUPPORTED warning.
		return;
	}

	if (kind != "turn" && kind != "kneel")
	{
		// RB-D32 corollary: an unknown ev kind (inject_ev's own spike test
		// payloads, e.g. "spot") is a legal state-no-op - seq is consumed by
		// the caller (CoopPump::drainApplyQueue()) regardless of what
		// happens here.
		Log(LOG_WARNING) << "[coop-apply] RW-UNSUPPORTED ev kind '" << kind << "'";
		return;
	}

	const Json::Value& payload = ev["payload"];
	if (!payload.isMember("unit"))
	{
		Log(LOG_WARNING) << "[coop-apply] ev kind '" << kind << "' payload missing 'unit' - dropped";
		return;
	}

	BattleUnit* unit = CoopIdMaps::unit(payload["unit"].asInt());
	if (!unit)
	{
		Log(LOG_WARNING) << "[coop-apply] ev kind '" << kind << "' unit "
			<< payload["unit"].asInt() << " does not resolve on this machine - dropped";
		return;
	}

	if (kind == "turn")
	{
		if (payload.isMember("door"))
		{
			// SS2.4: spike fixtures are door-free by construction (RB-D15);
			// the client does not apply a door result here (terrain apply is
			// the door atom's job) - correctly treated as a future desync at
			// the next hash compare (the state HAS diverged).
			Log(LOG_WARNING) << "[coop-apply] RW-UNSUPPORTED door-in-turn (unit "
				<< unit->getId() << ") - not applied";
		}

		// RW-FIX-TURRET: body first (never dragging the turret along - see
		// setBodyDirectionKeepTurret() above), then the turret EXCLUSIVELY
		// from the ev's own explicit turret field. A turretOnly turn writes
		// no body facing at all (the body did not move on the host either).
		const bool turretOnly = payload.get("turretOnly", false).asBool();
		if (!turretOnly && payload.isMember("toDir"))
			setBodyDirectionKeepTurret(unit, payload["toDir"].asInt());
		if (payload.isMember("turretTo"))
			unit->setTurretDirection(payload["turretTo"].asInt());
		if (payload.isMember("tuAfter"))
			unit->setTimeUnits(payload["tuAfter"].asInt());
	}
	else // "kneel"
	{
		if (payload.isMember("kneeled"))
		{
			const bool wantKneel = payload["kneeled"].asBool();
			if (unit->isKneeled() != wantKneel)
				unit->kneel(wantKneel);
		}
		if (payload.isMember("tuAfter"))
			unit->setTimeUnits(payload["tuAfter"].asInt());
	}
}

void applyActionEndFinal(BattleUnit* unit, const Json::Value& final)
{
	if (!unit)
		return;

	// "pos" is intentionally never read here - turn/kneel never move a unit;
	// syncing position is the walk atom's job, not this packet's (see
	// CoopApply.h's own doc comment).
	// RW-FIX-TURRET: SS2.4's `final` is {pos, dir, tu, energy, kneeled} - it
	// carries NO turret field (buildFinal(), connectionTCP.cpp), so the
	// turret established by this action's preceding bt_ev (turretTo) is
	// authoritative and MUST survive this restate. Applying "dir" with plain
	// setDirection() here would have re-dragged the turret onto the body
	// facing one seq AFTER the ev had just set it correctly.
	if (final.isMember("dir"))
		setBodyDirectionKeepTurret(unit, final["dir"].asInt());
	if (final.isMember("tu"))
		unit->setTimeUnits(final["tu"].asInt());
	if (final.isMember("energy"))
		unit->setEnergy(final["energy"].asInt());
	if (final.isMember("kneeled"))
	{
		const bool wantKneel = final["kneeled"].asBool();
		if (unit->isKneeled() != wantKneel)
			unit->kneel(wantKneel);
	}
}

} // namespace CoopApply
// RW-MINT-WHITELIST-END

namespace CoopDisplayQueue
{

// R3-P1 (IR-16c's own "body is a no-op until R3-P1" marker, BattlePump.h):
// the S3-instant display hook. Applies state (CoopApply.h) then "displays"
// it - CoopApply::applyEvPayload()/applyActionEndFinal() write the unit's
// live direction/turret-direction fields directly
// (BattleUnit::setDirection()/setTurretDirection()), and this codebase's
// map/unit-sprite rendering reads those fields fresh every frame (no
// separate cache/dirty flag exists on BattleUnit to invalidate - grepped),
// so the facing sweep is already "instant" the moment the write lands; there
// is nothing further to trigger. Ghost-sweep polish (an actual ANIMATED
// turn) is r3a S3's job, explicitly NOT required here (packet text).
//
// Called from CoopPump::drainApplyQueue() (BattlePump.h/RB-D5), in strict
// seq order, for every bt_ev/bt_action_end AFTER the gap check and BEFORE
// CoopHashCheck::verify()'s post-apply hash compare.
void onApplied(const Json::Value& ev)
{
	if (!isCoopBattle())
		return;
	SavedBattleGame* save = connectionTCP::getStaticBattle();
	if (!save)
		return;

	// RW-REVEAL-SYNC (SS2.4a): the envelope-level `reveal` field rides bt_ev of
	// ANY kind AND bt_action_end, so it is applied HERE - before the state
	// branch below, whose bt_action_end arm returns early. Presence-gated: a
	// no-op for every envelope that carries no reveal.
	CoopReveal::applyFrom(save, ev);

	const std::string state = ev.get("state", "").asString();

	// R2-P7: the toggle-3 basis, sampled BEFORE any payload apply (and before
	// the A5 targeted calculateFOV() those applies trigger) so
	// onEvAppliedCancelCheck() below can see whether THIS ev gained this
	// machine local visibility. Skipped entirely when nothing is pending -
	// the cancel policy has nothing to act on then, and this is on the
	// per-event apply path.
	const int visibleBefore = g_coopClientPending.active
		? CoopArbiter::visibleHostileCount() : 0;

	if (state == "bt_ev")
	{
		const std::uint32_t actionId = ev.get("actionId", 0u).asUInt();
		const Json::Value& payload = ev["payload"];
		if (actionId != 0 && payload.isMember("unit"))
		{
			// Purely client-side bookkeeping (never on the wire - SS2.3/
			// SS2.4 have no "unit" field on bt_action_end) so a LATER
			// bt_action_end (same actionId) can be resolved to a unit on
			// this machine, whether or not this machine is the one that
			// sent the original intent.
			g_coopClientActionActor[actionId] = payload["unit"].asInt();
		}
		CoopApply::applyEvPayload(save, ev);
	}
	else if (state == "bt_action_end")
	{
		const std::uint32_t actionId = ev.get("actionId", 0u).asUInt();
		auto it = g_coopClientActionActor.find(actionId);
		if (it != g_coopClientActionActor.end())
		{
			BattleUnit* unit = CoopIdMaps::unit(it->second);
			CoopApply::applyActionEndFinal(unit, ev["final"]);
			if (unit)
				save->getTileEngine()->calculateFOV(unit); // A5: targeted FOV refresh
			g_coopClientActionActor.erase(it);
		}
		else
		{
			Log(LOG_WARNING) << "[coop-apply] bt_action_end actionId " << actionId
				<< " has no known actor on this machine (no preceding bt_ev carried "
				"its 'unit' field) - final not applied";
		}
		CoopArbiter::onActionEndApplied(actionId); // IR-2: clears this client's own lock
		// R2-P7: THE auto-retry trigger. bt_action_end is emitted ONLY from
		// the host's onChainQuiesced() (RB-D11), so applying one is the
		// client-visible "event_state quiescence" the packet text names -
		// including for the blocker's own chain, which is the case that
		// matters (the pending intent is by definition the one that lost the
		// race to it). Deliberately AFTER onActionEndApplied() so the acting
		// unit's own lock is already released when a resubmit for that same
		// unit goes out.
		CoopArbiter::onQuiescenceObserved();
		return; // A5's FOV refresh above already covers the action_end path
	}
	else
	{
		Log(LOG_WARNING) << "[coop-apply] RW-UNSUPPORTED envelope state '" << state << "'";
		return;
	}

	// A5 (turn/kneel bt_ev path): targeted per-unit FOV refresh - turning or
	// kneeling can reveal/hide terrain or units for THIS unit specifically,
	// never a wider sweep.
	if (ev["payload"].isMember("unit"))
	{
		BattleUnit* unit = CoopIdMaps::unit(ev["payload"]["unit"].asInt());
		if (unit)
			save->getTileEngine()->calculateFOV(unit);
	}

	// R2-P7: info-cancel policy, evaluated LAST on the bt_ev path - after the
	// payload apply AND after the A5 FOV refresh above, so the visibility-gain
	// toggle compares post-apply local state against `visibleBefore`. Only
	// bt_ev reaches here: bt_action_end returns above (it carries no `kind`,
	// and the packet's policy table is written entirely in terms of applied
	// EVENTS).
	CoopArbiter::onEvAppliedCancelCheck(ev, visibleBefore);
}

} // namespace CoopDisplayQueue

// ===== R2-P6: admission-model banner presenter (CoopBattleUi.h) =====
// SPIKE-RUNBOOK.md sec 2.6, ADDENDUM 2026-08-31 sec 1.3(f). Bodies live here,
// next to BattleAuthority/CoopIdMaps/CoopArbiter above - same established
// home for CoopMod scaffolding. Unwired in this packet (see CoopBattleUi.h's
// doc comment); R3-P1 adds the client bt_deny caller, R2-P7 the pending/
// cancel callers.

namespace CoopBattleUi
{

namespace
{

/// The ONE enum->STR table (sec 2.6): every deny reason (sec 2.2's 8-value
/// wire enum) and every known auto-cancel cause (ADDENDUM 1.3(d)) in one
/// place. STR_COOP_CANCEL_EVENT (the {0}-templated unknown-kind fallback) is
/// deliberately NOT in this table - showCancel() applies it directly when a
/// lookup here misses, since it needs the evKind argument substituted in.
struct ReasonStrEntry
{
	const char* enumStr;
	const char* strKey;
};

const ReasonStrEntry kReasonStrTable[] =
{
	// deny reasons (sec 2.2)
	{ "busy",              "STR_COOP_DENY_BUSY" },
	{ "path_changed",      "STR_COOP_DENY_PATH_CHANGED" },
	{ "cost_changed",      "STR_COOP_DENY_COST_CHANGED" },
	{ "target_moved",      "STR_COOP_DENY_TARGET_MOVED" },
	{ "target_dead",       "STR_COOP_DENY_TARGET_DEAD" },
	{ "weapon_missing",    "STR_COOP_DENY_WEAPON_MISSING" },
	{ "not_your_unit",     "STR_COOP_DENY_NOT_YOUR_UNIT" },
	{ "turn_over",         "STR_COOP_DENY_TURN_OVER" },
	// auto-cancel causes (ADDENDUM 1.3(d))
	{ "enemy_spotted",     "STR_COOP_CANCEL_ENEMY_SPOTTED" },
	{ "unit_under_fire",   "STR_COOP_CANCEL_UNIT_UNDER_FIRE" },
	{ "unit_down",         "STR_COOP_CANCEL_UNIT_DOWN" },
	{ "new_contact",       "STR_COOP_CANCEL_NEW_CONTACT" },
};

const char* lookupStrKey(const char* enumStr)
{
	if (!enumStr)
		return nullptr;
	for (const auto& e : kReasonStrTable)
	{
		if (std::strcmp(e.enumStr, enumStr) == 0)
			return e.strKey;
	}
	return nullptr;
}

/// Same reach-the-live-battle pattern CoopArbiter::onIntent() already uses.
/// Returns nullptr outside an active coop battle or with no live
/// BattlescapeState (e.g. mid-teardown).
BattlescapeState* activeBattlescapeState()
{
	SavedBattleGame* save = connectionTCP::getStaticBattle();
	return save ? save->getBattleState() : nullptr;
}

} // namespace

void showDeny(const char* reason)
{
	BattlescapeState* bs = activeBattlescapeState();
	if (!bs)
		return;
	const char* key = lookupStrKey(reason);
	if (!key)
	{
		// Unknown/future reason (no sec 2.6 entry): never guess a string -
		// leave the banner as-is and log for diagnosis.
		Log(LOG_WARNING) << "[coop-battle-ui] showDeny: unrecognized reason '"
			<< (reason ? reason : "<null>") << "'";
		return;
	}
	bs->setCoopWaitText(bs->getGame()->getLanguage()->getString(key));
}

void showPending(const char* /*context*/)
{
	// R2-P7 (ADDENDUM 1.3(d) auto-retry + pending indicator) will pass real
	// context through this call and may add its own STR_ key/wording; until
	// then the pending state is presented with the same busy-wait text an
	// outright busy deny already uses (the client is waiting on the same
	// admission gate either way).
	BattlescapeState* bs = activeBattlescapeState();
	if (!bs)
		return;
	bs->setCoopWaitText(bs->getGame()->getLanguage()->getString("STR_COOP_DENY_BUSY"));
}

void clearPending()
{
	BattlescapeState* bs = activeBattlescapeState();
	if (!bs)
		return;
	bs->setCoopWaitText(std::string());
}

void showCancel(const char* cause, const char* evKind)
{
	BattlescapeState* bs = activeBattlescapeState();
	if (!bs)
		return;
	const char* key = lookupStrKey(cause);
	if (key)
	{
		bs->setCoopWaitText(bs->getGame()->getLanguage()->getString(key));
	}
	else
	{
		// sec 2.6 "(cancel) unknown kind" row: {0} = the event kind name.
		std::string kind = evKind ? evKind : std::string();
		bs->setCoopWaitText(bs->getGame()->getLanguage()->getString("STR_COOP_CANCEL_EVENT").arg(kind));
	}
}

void showDesyncHalted()
{
	BattlescapeState* bs = activeBattlescapeState();
	if (!bs)
		return;
	// R2-P9 (SS2.8 mismatch-behavior note): sticky - unlike showDeny/
	// showCancel/showPending, nothing ever calls clearPending() after this
	// (there is nothing left to auto-retry into once a battle has desynced).
	bs->setCoopWaitText(bs->getGame()->getLanguage()->getString("STR_COOP_DESYNC_HALTED"));
}

void showEquipFrozen()
{
	BattlescapeState* bs = activeBattlescapeState();
	if (!bs)
		return;
	// W1-P4 (WV-D34 / WV-D43): see CoopBattleUi.h for why this one is raised at
	// a SKIP rather than at a refused press. Plain SS2.6 routing otherwise -
	// _txtCoopWait, translated, never vanilla _warning.
	bs->setCoopWaitText(bs->getGame()->getLanguage()->getString("STR_COOP_EQUIP_FROZEN"));
}

// ---------------------------------------------------------------------------
// W1-P5 (WAVE1-RUNBOOK.md ruling D8 = WV-D14): client hard gates.
//
// Four battlescape controls (evidence F2) plus the quick-load hotkey
// (evidence F1) were PURE VANILLA in the rewrite - a co-op client could open
// the abort dialog, re-equip a soldier mid-battle, zero a unit's TU or flip
// its reaction-fire hands, all locally, with nothing on the wire. Three of
// those write HASHED state (`unitsStats`, `items`, and the saveBlob catch-all
// via the reaction fields), so each press was a silent, permanent divergence.
// ---------------------------------------------------------------------------

namespace
{

/// One row per Control. Kept as a table rather than a switch for the same
/// reason kReasonStrTable above is one: the SS2.6 string set is data.
const char* controlStrKey(Control c)
{
	switch (c)
	{
	case Control::Abort:        return "STR_COOP_ABORT_HOST_ONLY";
	case Control::Inventory:    return "STR_COOP_INVENTORY_HOST_ONLY";
	case Control::ZeroTu:       return "STR_COOP_ZERO_TU_HOST_ONLY";
	case Control::HandReaction: return "STR_COOP_REACTIONS_HOST_ONLY";
	case Control::QuickLoad:    return "STR_COOP_LOCAL_LOAD_BLOCKED";
	}
	return nullptr;
}

/// Same _txtCoopWait routing every other entry point in this namespace uses
/// (SS2.6: never vanilla _warning). No-op with no live BattlescapeState.
void showRefusalKey(const char* key)
{
	BattlescapeState* bs = activeBattlescapeState();
	if (!bs || !key)
		return;
	bs->setCoopWaitText(bs->getGame()->getLanguage()->getString(key));
}

} // namespace

void showControlRefused(Control c)
{
	showRefusalKey(controlStrKey(c));
}

bool refuseControl(Control c, const BattleUnit* u, const SavedBattleGame* s)
{
	if (c == Control::QuickLoad)
	{
		// SESSION-scoped, not battle-scoped, and not client-only: the single
		// authority is connectionTCP::localLoadsAllowed() (PRD-08 C7), which is
		// false for the HOST too while a session is live. This restores the
		// gate legacy carried at 1e0f9276f:BattlescapeState.cpp:5429-5435 and
		// adds the VISIBLE half the design session asked for - LoadGameState's
		// own chokepoint refusal was log-only (LoadGameState.cpp:159).
		if (connectionTCP::localLoadsAllowed())
			return false;
		showControlRefused(c);
		return true;
	}

	// Self-guard: SP and every non-co-op battle fall straight through, so
	// vanilla is byte-identical there (same shape as isCoopBattle()/
	// coopMayCommand()).
	if (!isCoopBattle())
		return false;

	// Term 1 - AUTHORITY. Only the simulating machine may run a control whose
	// effect has no wire representation. coopMayCommand() alone cannot carry
	// this: it is TRUE for a client acting on its own unit during its own
	// side, which is exactly when these buttons get pressed. The two-term
	// shape below is the shipped house pattern, not a new invention:
	// BattlescapeState::btnKneelClick already reads coopMayCommand(bu, _save)
	// and then `isCoopBattle() && !hostSim` (:1244 and :1254), and the R5-P2
	// END TURN client gate is the same authority term (:1530). The difference
	// is only what the second term does - kneel has a wire verb to send, these
	// five controls have none, so they refuse.
	if (!coopBattleAuthority().hostSim)
	{
		showControlRefused(c);
		return true;
	}

	// Term 2 - OWNERSHIP, for the unit-scoped controls only. A seat may not
	// command a unit it does not own even when it IS the host (the initial
	// selection is minted before any seat filter, so a host CAN be sitting on
	// a client-owned soldier today - W1-P1 observed exactly that). Its own
	// reason, its own message: SS2.6's existing not_your_unit row, reused
	// rather than duplicated.
	if (u && !coopMayCommand(u, s))
	{
		showRefusalKey("STR_COOP_DENY_NOT_YOUR_UNIT");
		return true;
	}

	return false;
}

bool chatIsOpen(Game* g)
{
	if (!g)
		return false;
	connectionTCP* coop = g->getCoopMod();
	ChatMenu* chat = coop ? coop->getChatMenu() : nullptr;
	return chat != nullptr && chat->isActive();
}

} // namespace CoopBattleUi

// ===== Geoscape sync conflation slot =====
// One overwrite slot per snapshot channel (see CoopSnapSlot). The main thread
// (GeoscapeState::think) overwrites; the send drain reads the freshest value and
// clears the dirty flag. Written/read under g_snapMx so a mid-read frame can't be
// torn by a concurrent overwrite.
static std::mutex g_snapMx;
static std::array<std::string, SNAP_COUNT> g_snap;
static std::array<bool, SNAP_COUNT> g_snapDirty{}; // value-init -> all false

void enqueueSnapshot(CoopSnapSlot slot, std::string&& s)
{
	if (slot < 0 || slot >= SNAP_COUNT)
		return;
	std::lock_guard<std::mutex> lk(g_snapMx);
	g_snap[slot] = std::move(s); // discards only the stale prior snapshot (LWW-safe)
	g_snapDirty[slot] = true;
}

bool anySnapshotDirty()
{
	std::lock_guard<std::mutex> lk(g_snapMx);
	for (int i = 0; i < SNAP_COUNT; ++i)
		if (g_snapDirty[i])
			return true;
	return false;
}

bool popSnapshot(std::string& out)
{
	std::lock_guard<std::mutex> lk(g_snapMx);
	for (int i = 0; i < SNAP_COUNT; ++i)
	{
		if (g_snapDirty[i])
		{
			out = g_snap[i]; // raw payload; UDP sends whole messages (no framing)
			g_snapDirty[i] = false;
			return true;
		}
	}
	return false;
}

static inline void appendFramed(std::string& out, const std::string& payload); // defined below

// Append every dirty snapshot into `out` (framed) and clear its flag. Called by
// the send drains right after the g_txQ batch, so snapshots ride the same
// sendAll as the reliable batch (freshest value only, at link rate).
static void drainSnapshotsInto(std::string& out)
{
	std::lock_guard<std::mutex> lk(g_snapMx);
	for (int i = 0; i < SNAP_COUNT; ++i)
	{
		if (g_snapDirty[i])
		{
			appendFramed(out, g_snap[i]);
			g_snapDirty[i] = false;
		}
	}
}

// Reset conflation slots on session teardown (mirrors the g_rxHold clear).
static void clearSnapshotSlots()
{
	std::lock_guard<std::mutex> lk(g_snapMx);
	for (int i = 0; i < SNAP_COUNT; ++i)
	{
		g_snap[i].clear();
		g_snapDirty[i] = false;
	}
}

// ===== Time helper =====
static inline uint64_t now_ms()
{
	using namespace std::chrono;
	return std::chrono::duration_cast<std::chrono::milliseconds>(
			   std::chrono::steady_clock::now().time_since_epoch())
		.count();
}

// Optional sugar: serialize JSON and enqueue via sendTCPPacketStaticData (no direct socket send).
static inline void sendJSONNoLock(const Json::Value& v)
{
	Json::StreamWriterBuilder wb;
	wb["indentation"] = "";
	std::string s = Json::writeString(wb, v);
	sendTCPPacketStaticData(std::move(s));
}

bool enqueueTx(std::string&& s)
{
	if (s.empty())
		return false;

	if (!g_txQ.push(std::move(s)))
	{
		DebugLog("TX queue full, dropping packet\n");
		++g_txDropCount;
		return false;
	}

	return true;
}

void clearNetworkSessionQueues()
{
	// Reset all shared packet queues so a new session starts like a fresh game launch.
	// This clears stale packets left by the previous TCP/UDP session, including
	// packets held by updateCoopTask() while the game was not ready to consume them.
	clearPackets = false;

	std::string drop;
	while (g_txQ.pop(drop))
	{
	}

	while (g_rxQ.pop(drop))
	{
	}

	{
		std::lock_guard<std::mutex> lock(g_rxHoldMutex);
		g_rxHold.clear();
	}

	clearSnapshotSlots();

	// R2-P8 (SPIKE-RUNBOOK.md RB-D7/RB-D30, #82 GoToMainMenuState invariant):
	// this is the single teardown chokepoint for BOTH transports (the TCP
	// disconnect call below at the old :586 family site, plus UDP's own
	// session-start/stop calls in connection_udp_glue.cpp and
	// connection_rendezvous_glue.cpp) - extending it here, once, resets battle
	// state for every caller instead of duplicating the reset at each site.
	//
	// CoopPump::reset() already clears g_coopActionContextStack/
	// g_coopActionIdMint/g_coopPendingChainActorId/g_coopLastDenyTick itself
	// (it calls the file-local resetCoopArbiterState() - see that function's
	// call site a few lines above CoopPump::reset()'s own definition), so
	// there is nothing left for a separate CoopArbiter::resetBattleState() to
	// do; adding one here would just double-reset the same statics. Ordering
	// is not load-bearing (each call only touches its own state), but battle
	// authority is reset last so isCoopBattle()/coopBattleAuthority().phase
	// read Idle immediately after every other battle store is already empty.
	CoopPump::reset();
	CoopIdMaps::reset();
	resetBattleAuthority();
	// R4-P1: clear this packet's own pending-handshake statics (client
	// in-flight blob expectation, host pending briefing/saveBlob-hash state)
	// at the SAME chokepoint - see CoopHandshake::resetPendingState()'s doc
	// comment.
	CoopHandshake::resetPendingState();
}

// ===== R4-P1: battle-start handshake (CoopHandshake.h) =====
// SPIKE-RUNBOOK.md SS2.7/RB-D18/RB-D23/IR-5/IR-6. Storage/helpers live here,
// next to BattleAuthority/CoopArbiter/CoopIdMaps/CoopPump/CoopEmit above -
// the established home for this scaffolding (R2-P1..P8). All four handshake
// sends go through CoopEmit::sendBattle() (matching CoopArbiter's own
// deny()/ack() sends), so they get the MN-8 TX-drain bypass.
namespace CoopHandshake
{

// ----- internal helpers (file-scope; not part of the CoopHandshake.h API) -----

// IR-6: sha256 = libsodium crypto_hash_sha256, never hand-rolled. sodium_init()
// is idempotent (matches the connectionUDP idiom, e.g. connection_udp_glue.cpp:83).
static std::string coopSha256Hex(const std::string& data)
{
	if (sodium_init() < 0)
	{
		Log(LOG_ERROR) << "[coop-handshake] sodium_init() failed - cannot hash the battle blob";
		return std::string();
	}
	unsigned char digest[crypto_hash_sha256_BYTES];
	crypto_hash_sha256(digest, reinterpret_cast<const unsigned char*>(data.data()),
		(unsigned long long)data.size());

	static const char* hex = "0123456789abcdef";
	std::string out;
	out.reserve(sizeof(digest) * 2);
	for (unsigned char b : digest)
	{
		out += hex[(b >> 4) & 0xF];
		out += hex[b & 0xF];
	}
	return out;
}

// R2-P9 (SPIKE-RUNBOOK.md SS2.8, RB-D20 hand-off item 1): REPLACES the R4-P1
// raw-FNV placeholder with the canonical SS2.8 saveBlob bucket - excludes
// the packed per-tile FOW "discovered" bits, the D4 per-unit FOV fields and
// the full cr1-field-audit.md sec 6 delta, via SharedEcon::
// computeSaveBlobHash() (the ported SharedEcon bucket function - "don't
// hand-roll a second hasher"). Unlike the R4-P1 placeholder this stays
// correct at any point in the battle, not just t=0 handshake.
static std::string coopComputeSaveBlobBucketHex(SavedBattleGame* battle)
{
	std::uint64_t h = 0;
	SharedEcon::computeSaveBlobHash(battle, h); // false (battle==null): h stays 0
	return coopHex64(h);
}

// RB-D31: faction wire encoding is strings ("player"/"hostile"/"neutral").
static int coopWireStringToFaction(const std::string& s)
{
	if (s == "hostile")
		return (int)FACTION_HOSTILE;
	if (s == "neutral")
		return (int)FACTION_NEUTRAL;
	return (int)FACTION_PLAYER;
}

// RB-D31 inverse: BattleAuthority faction int -> wire string.
static std::string coopFactionToWireString(int faction)
{
	if (faction == (int)FACTION_HOSTILE)
		return "hostile";
	if (faction == (int)FACTION_NEUTRAL)
		return "neutral";
	return "player";
}

static void coopApplySeatMap(const Json::Value& seatMap)
{
	if (!seatMap.isObject())
		return;
	for (const auto& key : seatMap.getMemberNames())
	{
		const int seat = std::atoi(key.c_str());
		coopBattleAuthority().setSeatFaction(seat, coopWireStringToFaction(seatMap[key].asString()));
	}
}

// R5-P1 (RB-D23): the REAL seatMap for battle_offer, built from
// coopBattleAuthority()'s seat->faction store AFTER assignSeatsAndFactions()
// (CoopState.cpp) has populated it for every seat in @a seats - REPLACES the
// R4-P1 interim coopBuildInterimSeatMap() (a flat {"0":"player","1":"player"}
// placeholder that never touched a BattleUnit or reflected gm2/gm3). HOST-only
// (only offerBattle() calls this); the client applies whatever this produces
// via the existing coopApplySeatMap() above, unmodified.
static Json::Value coopBuildRealSeatMap(const std::vector<int>& seats)
{
	Json::Value m(Json::objectValue);
	for (int seat : seats)
	{
		m[std::to_string(seat)] = coopFactionToWireString(coopBattleAuthority().factionOf(seat));
	}
	return m;
}

// ----- HOST pending state: set by offerBattle(), consumed by onReady()/onRefuse() -----
struct PendingHost
{
	bool active = false;
	std::uint32_t battleId = 0;
	std::string saveBlobHex; // this machine's own saveBlob bucket (offerBattle() computes it once)
};
static PendingHost g_pendingHost;

// R4-P1 (see CoopHandshake.h's top doc comment for the crash this fixes):
// bounded unwind back to a safe state, used ONLY on the onRefuse()/onReady()
// mismatch teardown paths - the host's BriefingState/BattlescapeState
// navigation runs independently of the handshake (the caller pushes
// BriefingState immediately and unconditionally, matching vanilla), so by
// the time a refusal/mismatch arrives the host may be sitting anywhere from
// BriefingState to mid-BattlescapeState. Mirrors the bounded popState() loop
// connectionTCP.cpp's own close_load_progress "inBattleResume" handler
// already uses for the same reason - see the function body for why it can
// legitimately empty the stack down to zero (and what it does about that).
static void coopUnwindToSafeState(Game* game)
{
	// RW-TRIAGE finding (this packet's corrupt-blob acceptance run): the
	// skirmish path's OWN vanilla popState() pair (NewBattleState::
	// btnOkClick, unmodified) already discards everything below
	// BriefingState before pushing it - so BriefingState is BOTH the bottom
	// AND the top of the stack there, and a "stop once size()==1" guard
	// never finds a safe state to land on (verified: it left the host
	// stranded on a bare BriefingState with the confirm-corrupt-refuse
	// evidence still needing a real teardown). Pop everything (never
	// stopping at 1 remaining) looking for Geoscape/MainMenu; if the stack
	// empties without finding either (the skirmish shape), push a fresh
	// MainMenuState so Game::_states is never left empty (see this header's
	// top doc comment for the crash that already taught this lesson once).
	int guard = 0;
	while (guard++ < 32 && !game->getStates().empty())
	{
		State* top = game->getStates().back();
		if (dynamic_cast<GeoscapeState*>(top) || dynamic_cast<MainMenuState*>(top))
			return;
		game->popState();
	}
	game->pushState(new MainMenuState());
}

// ----- CLIENT pending state: set by onOffer() on accept, consumed by onBlobChunkAppended() -----
struct PendingClient
{
	bool awaitingBlob = false;
	std::uint32_t battleId = 0;
	std::uint64_t blobBytes = 0;
	std::string blobSha;
	// R5-P1: the real battle_offer seatMap onOffer() already validated -
	// onBlobChunkAppended() re-applies it (its own initBattleAuthority() call
	// clears the seat->faction store a second time) rather than recomputing.
	Json::Value seatMap;
	// W1-P2 (SS2.W1): battle_offer.missionLabel, stashed by onOffer() so
	// onBlobChunkAppended() can apply it once the blob has actually loaded
	// (and BEFORE it pushes any state). Null when the offer carried none.
	Json::Value missionLabel;
};
static PendingClient g_pendingClient;

// R2-P11 (RB-D26): test-only, one-shot corrupt-next-blob lever. Set by
// requestCorruptNextBlob() (TestServer's corrupt_next_blob command); consumed
// and cleared by offerBattle() right after it computes blobSha, so the flip
// lands AFTER the sha the offer advertises - the client's own post-stream
// blobSha verify is what is meant to catch it, not offerBattle's own hashing.
// Main/pump-thread only, same as every other CoopHandshake static here.
static bool g_coopCorruptNextBlobRequested = false;

// W1-P2 (WAVE1-RUNBOOK.md SS2.W1, WV-D28 shape (d) / WV-D42): this battle's
// mission identity. The HOST fills it in mintMissionLabels(), called one line
// above each of offerBattle()'s four call sites - i.e. BEFORE offerBattle()
// snapshots the blob (the SS2.W1 ORDERING TRAP: the CALLER pushes BriefingState
// only afterwards, so vanilla's own labels do not exist yet at offer-build
// time). The CLIENT fills it from the received offer in onBlobChunkAppended(),
// before it pushes any state. Cleared at the teardown chokepoint
// (resetPendingState()). Main/pump-thread only, like every other CoopHandshake
// static here.
//
// `deployment` is the RESOLVED AlienDeployment type. It is carried because a
// thin client has no Craft and no Ufo to re-derive it from: BriefingState.cpp:
// 73-99 falls back to the craft's UFO destination when getDeployment(missionType)
// misses, which is the NORMAL case for STR_UFO_CRASH_RECOVERY.
//
// `missionType` is an ECHO ONLY (WR-10). It is a serialized top-level key
// (SavedBattleGame::save) and is NOT in saveBlobExcludedTopKey
// (SharedEcon.cpp:3955-3975), i.e. it IS hashed - the client must never write
// it. strTarget/strCraftOrBase by contrast ARE hash-excluded
// (SharedEcon.cpp:3974, applied by the tree-walker saveBlobHashTree :4033), so
// carrying and applying the two labels is hash-neutral by construction.
struct MissionLabels
{
	bool carried = false;
	std::string target;
	std::string craftOrBase;
	std::string deployment;
	std::string missionType; // echo only - NEVER written into the save (WR-10)
};
static MissionLabels g_missionLabels;

// ----- CoopHandshake.h API -----

void requestCorruptNextBlob()
{
	g_coopCorruptNextBlobRequested = true;
}

void mintMissionLabels(Game* game, Craft* craft, Base* base)
{
	// SELF-GUARDING (WV-D42). All four offerBattle() call sites are vanilla
	// battle-generation paths that also run in SP; a no-op off the coop host
	// keeps every one of them byte-identical (vanilla BriefingState still
	// mints, and operationNameAlreadyMinted() below stays false).
	if (!game || !connectionTCP::getServerOwner() || !connectionTCP::getCoopStatic())
		return;
	SavedGame* saved = game->getSavedGame();
	SavedBattleGame* battle = saved ? saved->getSavedBattle() : nullptr;
	if (!battle)
	{
		Log(LOG_WARNING) << "[coop-handshake] mintMissionLabels() called with no live "
			"SavedBattleGame - nothing to label";
		return;
	}

	g_missionLabels = MissionLabels();

	// --- deployment resolution: BriefingState.cpp:73-99, replicated exactly ---
	const std::string mission = battle->getMissionType();
	AlienDeployment* deployment = game->getMod()->getDeployment(mission);
	if (mission == "STR_BASE_DEFENSE")
	{
		AlienDeployment* customDeployment = game->getMod()->getDeployment(battle->getAlienCustomDeploy());
		if (customDeployment && !customDeployment->getBriefingData().desc.empty())
		{
			deployment = customDeployment;
		}
	}
	else if (!deployment && craft)
	{
		Ufo* ufo = dynamic_cast<Ufo*>(craft->getDestination());
		if (ufo) // landing site or crash site
		{
			std::string ufoMissionName = ufo->getRules()->getType();
			if (!battle->getAlienCustomMission().empty())
			{
				// fake underwater UFO
				ufoMissionName = battle->getAlienCustomMission();
			}
			deployment = game->getMod()->getDeployment(ufoMissionName);
		}
	}

	// --- label mint: BriefingState.cpp:151-188's !_infoOnly body, replicated
	// exactly. RNG::seedless does not touch the synced RNG stream, so this is
	// RNG-neutral and cannot shift the generated battle. ---
	std::string s;
	if (craft)
	{
		if (craft->getDestination())
		{
			s = craft->getDestination()->getName(game->getLanguage());
			battle->setMissionTarget(s);
		}

		s = game->getLanguage()->getString("STR_CRAFT_").arg(craft->getName(game->getLanguage()));
		battle->setMissionCraftOrBase(s);
	}
	else if (base)
	{
		s = game->getLanguage()->getString("STR_BASE_UC_").arg(base->getName());
		battle->setMissionCraftOrBase(s);
	}

	// random operation names. IR2-10 (binding): this block's condition is
	// `craft || base`, so it covers the BASE path too - base defense is NOT
	// unconditionally target-less; strTarget stays empty there ONLY when the
	// loaded mod defines no operationNames.
	if (craft || base)
	{
		if (!game->getMod()->getOperationNamesFirst().empty())
		{
			std::ostringstream ss;
			int pickFirst = RNG::seedless(0, game->getMod()->getOperationNamesFirst().size() - 1);
			ss << game->getMod()->getOperationNamesFirst().at(pickFirst);
			if (!game->getMod()->getOperationNamesLast().empty())
			{
				int pickLast = RNG::seedless(0, game->getMod()->getOperationNamesLast().size() - 1);
				ss << " " << game->getMod()->getOperationNamesLast().at(pickLast);
			}
			s = ss.str();
			battle->setMissionTarget(s);
		}
	}

	g_missionLabels.carried = true;
	g_missionLabels.target = battle->getMissionTarget();
	g_missionLabels.craftOrBase = battle->getMissionCraftOrBase();
	g_missionLabels.deployment = deployment ? deployment->getType() : std::string();
	g_missionLabels.missionType = mission;

	Log(LOG_INFO) << "[coop-handshake] mission labels minted pre-offer: target=\""
		<< g_missionLabels.target << "\", craftOrBase=\"" << g_missionLabels.craftOrBase
		<< "\", deployment=\"" << g_missionLabels.deployment
		<< "\", missionType=\"" << g_missionLabels.missionType << "\"";
}

bool missionLabelsCarried()
{
	return g_missionLabels.carried;
}

const std::string& carriedDeploymentType()
{
	return g_missionLabels.deployment;
}

AlienDeployment* resolveBriefingDeployment(Game* game, AlienDeployment* vanillaResolved)
{
	// Outside a coop battle this is a pure pass-through and says nothing - the
	// SP briefing keeps vanilla's own outcome, byte-identical.
	const bool coopBattle = game && coopBattleAuthority().phase != CoopBattlePhase::Idle;
	if (!coopBattle || !game->getMod())
		return vanillaResolved;

	if (vanillaResolved)
	{
		Log(LOG_INFO) << "[coop-handshake] BriefingState deployment: VANILLA \""
			<< vanillaResolved->getType() << "\" (this machine re-derived it itself)";
		return vanillaResolved;
	}

	AlienDeployment* carried = g_missionLabels.carried && !g_missionLabels.deployment.empty()
		? game->getMod()->getDeployment(g_missionLabels.deployment)
		: nullptr;
	if (carried)
	{
		Log(LOG_INFO) << "[coop-handshake] BriefingState deployment: CARRIED \""
			<< g_missionLabels.deployment << "\" (from battle_offer - this machine has "
			"no Craft/Ufo to re-derive it from, SS2.W1)";
		return carried;
	}

	Log(LOG_WARNING) << "[coop-handshake] BriefingState deployment: NONE - this briefing "
		"will render the generic \"should never happen\" fallback "
		"(BriefingState.cpp:104-108) with whatever labels the save carries (SS2.W1)";
	return nullptr;
}

bool missionLabelsAlreadyMinted(const SavedBattleGame* battle)
{
	if (!battle || !g_missionLabels.carried)
		return false; // SP and every non-coop battle: vanilla mints, byte-identical
	if (coopBattleAuthority().phase == CoopBattlePhase::Idle)
		return false; // stale flag from a torn-down battle - never suppress an SP mint
	if (battle->getMissionTarget().empty())
		return false; // nothing was actually minted for this battle - let vanilla run

	Log(LOG_INFO) << "[coop-handshake] BriefingState label re-mint SUPPRESSED "
		"(SS2.W1 RE-MINT SUPPRESSION; pre-offer labels kept: target=\""
		<< battle->getMissionTarget() << "\", craftOrBase=\""
		<< battle->getMissionCraftOrBase() << "\")";
	return true;
}

bool mayReopenBriefing(Game* game)
{
	if (!game)
		return false;
	if (coopBattleAuthority().phase == CoopBattlePhase::Idle)
		return true; // SP / no coop battle in flight: vanilla ctrl-B, byte-identical
	if (coopBattleAuthority().hostSim)
		return true; // the host generated this mission and still owns the Craft
	if (g_missionLabels.carried)
		return true;

	Log(LOG_WARNING) << "[coop-handshake] ctrl-B refused: this battle carried no mission "
		"identity, so a thin client's BriefingState would render the generic "
		"\"should never happen\" fallback with empty labels (SS2.W1)";
	return false;
}

bool freezePreBattleEquip(Game* game)
{
	// Deliberately the SAME predicate resolveBriefingDeployment() uses, and NOT
	// isCoopBattle(): isCoopBattle() requires phase == Active, but the host can
	// dismiss its briefing while the handshake is still in flight (phase ==
	// Handshake, before the client's battle_ready hash has matched) - and the
	// equip screen must be frozen there too, because the blob was snapshotted
	// even earlier still. Idle == SP or no coop battle => vanilla pushes
	// InventoryState exactly as before, byte-identical.
	if (!game || coopBattleAuthority().phase == CoopBattlePhase::Idle)
		return false;

	Log(LOG_INFO) << "[coop-handshake] W1-P4: pre-battle equip FROZEN (WV-D34) - "
		"InventoryState push SKIPPED; BriefingState::btnOkClick calls "
		"SavedBattleGame::startFirstTurn() itself instead (WV-D43), so the host does "
		"not sit at turn 0 against the client's RW-FIX-TURN mirror";

	CoopBattleUi::showEquipFrozen();
	return true;
}

void offerBattle(Game* game, int gamemode)
{
	if (!game || !connectionTCP::getServerOwner())
	{
		Log(LOG_WARNING) << "[coop-handshake] offerBattle() called on a non-host machine - ignoring";
		return;
	}
	if (coopBattleAuthority().phase != CoopBattlePhase::Idle)
	{
		Log(LOG_WARNING) << "[coop-handshake] offerBattle() called while phase != Idle "
			"- a handshake/battle is already in flight, ignoring the double-offer";
		return;
	}
	SavedBattleGame* battle = game->getSavedGame() ? game->getSavedGame()->getSavedBattle() : nullptr;
	if (!battle)
	{
		Log(LOG_ERROR) << "[coop-handshake] offerBattle() called with no live SavedBattleGame - nothing to offer";
		return;
	}

	static std::uint32_t s_nextBattleId = 1; // SS2.2: battleId, host-minted, session-monotonic
	const std::uint32_t battleId = s_nextBattleId++;

	initBattleAuthority(battleId); // -> hostSim=true, localSeat, phase=Handshake, seat-faction store cleared

	// R5-P1 (RB-D23): the ONE generation-time canonical-faction/seat pass -
	// REPLACES the R4-P1 interim coopApplySeatMap(coopBuildInterimSeatMap())
	// call that used to sit here. @a seats is every currently-connected seat
	// (host + clients); the spike is 2-seat only (host=0, client=1,
	// connectionTCP::localSeat()'s own transport convention) but this reads
	// the live roster size rather than hardcoding {0,1} (RB-D17 N-player
	// guardrail). Populates BOTH coopBattleAuthority()'s seat->faction store
	// (read below by coopBuildRealSeatMap() for the offer) AND every
	// generated BattleUnit's RB-D17 seat tag + canonical faction - see
	// CoopBattleSetup.h for the full per-gamemode contract.
	std::vector<int> seats;
	seats.reserve(connectionTCP::seatCount());
	for (int s = 0; s < connectionTCP::seatCount(); ++s)
	{
		seats.push_back(s);
	}
	assignSeatsAndFactions(battle, gamemode, seats);

	// Snapshot (donor call shape CoopState.cpp:~1667 @1e0f9276f) - the whole
	// generated SavedGame blob, which contains the active SavedBattleGame.
	game->getSavedGame()->saveCoopToMemory("battlehost", game->getMod(), "battlehost");

	// RW-REVEAL-SYNC (SS2.4a): seed the published fog bitmap from the very state
	// the blob just froze, so the host's first `reveal` delta carries exactly
	// what it discovered AFTER the client's copy was taken (the orchestrator's
	// 2026-09-02 gap probe measured ~500 floors revealed between this line and
	// the host's own battlescape bring-up - the standalone quiescent flush is
	// load-bearing, not a nicety). Called EXPLICITLY rather than behind an
	// isCoopBattle() guard: phase is still Handshake here (initBattleAuthority()
	// above), so isCoopBattle() is false at this point (BattleAuthority.h).
	CoopReveal::seedPublished(battle);

	std::string blob;
	{
		std::lock_guard<std::mutex> lock(connectionTCP::coopFilesMutex);
		auto it = connectionTCP::coopFilesHost.find("battlehost");
		if (it == connectionTCP::coopFilesHost.end())
		{
			Log(LOG_ERROR) << "[coop-handshake] offerBattle(): saveCoopToMemory did not "
				"populate coopFilesHost[\"battlehost\"]";
			resetBattleAuthority();
			return;
		}
		blob = it->second;
	}

	const std::string sha = coopSha256Hex(blob); // IR-6

	// RB-D26: the permanent corrupt_next_blob lever (R2-P11's TestServer
	// command sets the one-shot flag; consumed+cleared here). Flips byte 0 of
	// coopFilesHost["battlehost"] itself - the persisted entry onAccept()'s
	// stream carrier reads from (comment at this function's onAccept()
	// sibling: "streams whatever is in coopFilesHost[\"battlehost\"]") - AFTER
	// blobSha above was computed from the (now stale) local blob copy, so the
	// bytes that actually stream no longer match the sha the offer advertises.
	// The R4-P1 packet's own temporary env-var version of this lever was
	// exercised once and removed in that same packet; this is its permanent
	// replacement (G3's plan of record).
	if (g_coopCorruptNextBlobRequested)
	{
		g_coopCorruptNextBlobRequested = false;
		std::lock_guard<std::mutex> lock(connectionTCP::coopFilesMutex);
		auto corruptIt = connectionTCP::coopFilesHost.find("battlehost");
		if (corruptIt != connectionTCP::coopFilesHost.end() && !corruptIt->second.empty())
		{
			corruptIt->second[0] = (char)((unsigned char)corruptIt->second[0] ^ 0xFF);
			Log(LOG_WARNING) << "[coop-handshake] corrupt_next_blob lever fired: flipped byte 0 of "
				"the battlehost blob after sha computation - the client's blobSha verify is expected "
				"to refuse {corrupt}";
		}
		else
		{
			Log(LOG_WARNING) << "[coop-handshake] corrupt_next_blob lever requested but "
				"coopFilesHost[\"battlehost\"] was missing/empty - nothing to flip";
		}
	}

	g_pendingHost = PendingHost();
	g_pendingHost.active = true;
	g_pendingHost.battleId = battleId;
	g_pendingHost.saveBlobHex = coopComputeSaveBlobBucketHex(battle);

	Json::Value offer(Json::objectValue);
	offer["state"] = "battle_offer";
	offer["protocolVersion"] = 1;
	offer["battleId"] = battleId;
	offer["gamemode"] = gamemode;
	offer["seatMap"] = coopBuildRealSeatMap(seats); // R5-P1 (RB-D23/RB-D31): real per-unit-derived factions
	offer["blobBytes"] = Json::UInt64(blob.size());
	offer["blobSha"] = sha;

	// W1-P2 (SS2.W1 / WV-D28 shape (d)): mission identity. Presence-gated on the
	// envelope for protocol tolerance, but a wave-1 host ALWAYS sends it; when
	// present, target / craftOrBase / deployment are all REQUIRED KEYS - and
	// REQUIRED means the key is PRESENT, not that the value is non-empty (WR-9).
	// mintMissionLabels() ran at the call site one line above offerBattle(), i.e.
	// BEFORE the saveCoopToMemory() snapshot above, so these are the same labels
	// the blob carries AND the ones this host will keep - BriefingState's own
	// re-mint is suppressed by operationNameAlreadyMinted() (SS2.W1).
	Json::Value missionLabel(Json::objectValue);
	missionLabel["target"] = battle->getMissionTarget();
	missionLabel["craftOrBase"] = battle->getMissionCraftOrBase();
	missionLabel["deployment"] = g_missionLabels.deployment;
	missionLabel["missionType"] = battle->getMissionType(); // echo only (WR-10)
	offer["missionLabel"] = missionLabel;

	CoopEmit::sendBattle(offer);

	Log(LOG_INFO) << "[coop-handshake] battle_offer sent (battleId=" << battleId
		<< ", gamemode=" << gamemode << ", blobBytes=" << blob.size()
		<< ", saveBlob=" << g_pendingHost.saveBlobHex << ")";
}

void onOffer(Game* game, const Json::Value& offer)
{
	if (!game || connectionTCP::getServerOwner())
		return; // only a CLIENT (never the host) receives an offer

	const std::uint32_t battleId = offer.get("battleId", 0u).asUInt();

	auto refuse = [&](const char* reason)
	{
		Json::Value r(Json::objectValue);
		r["state"] = "battle_refuse";
		r["battleId"] = battleId;
		r["reason"] = reason;
		CoopEmit::sendBattle(r);
		Log(LOG_WARNING) << "[coop-handshake] battle_offer (battleId=" << battleId
			<< ") refused: " << reason;
	};

	const int protocolVersion = offer.get("protocolVersion", 0).asInt();
	if (protocolVersion != 1)
	{
		refuse("version");
		return;
	}

	if (coopBattleAuthority().phase != CoopBattlePhase::Idle)
	{
		refuse("busy");
		return;
	}

	const int gamemode = offer.get("gamemode", 0).asInt();
	if (gamemode >= 4) // R5-P1 (RB-D23): gm2/gm3 now supported; gm4 (PvE2) stays deferred (RB-D16)
	{
		refuse("unsupported");
		return;
	}

	initBattleAuthority(battleId); // -> hostSim=false, localSeat, phase=Handshake, seat-faction store cleared
	coopApplySeatMap(offer["seatMap"]);

	g_pendingClient = PendingClient();
	g_pendingClient.awaitingBlob = true;
	g_pendingClient.battleId = battleId;
	g_pendingClient.blobBytes = offer.get("blobBytes", Json::UInt64(0)).asUInt64();
	g_pendingClient.blobSha = offer.get("blobSha", "").asString();
	// R5-P1: the REAL per-battle seatMap (RB-D31 strings), stashed so
	// onBlobChunkAppended() can re-apply it after its own initBattleAuthority()
	// call clears coopBattleAuthority()'s seat->faction store a second time -
	// this machine never regenerates the battle, so there is nothing to
	// recompute it FROM at that point except what onOffer() already validated
	// here.
	g_pendingClient.seatMap = offer["seatMap"];
	// W1-P2 (SS2.W1): the offer's mission identity, applied by
	// onBlobChunkAppended() once the blob has loaded. Presence-gated: a null
	// value here simply means the offer carried no labels.
	g_pendingClient.missionLabel = offer["missionLabel"];

	// Fresh accumulation buffer for THIS transfer - defensive against any
	// stale leftover (resetPendingState() also clears this at the teardown
	// chokepoint, but a belt-and-braces clear here costs nothing).
	mapData.clear();

	Json::Value accept(Json::objectValue);
	accept["state"] = "battle_accept";
	accept["protocolVersion"] = 1;
	accept["battleId"] = battleId;
	CoopEmit::sendBattle(accept);

	Log(LOG_INFO) << "[coop-handshake] battle_offer accepted (battleId=" << battleId
		<< ", expecting " << g_pendingClient.blobBytes << " bytes)";
}

/**
 * RW-FIX-TURN (owner-approved fix packet 2026-09-01, recorded in the docs
 * repo's spike-log "OWNER DECISION - saveBlob post-overlay divergence RCA";
 * outside the SS5 packet list, not an RB-D deviation): mirror the turn
 * counter that vanilla's host-only battle-start chain sets.
 *
 * RCA: the host's pre-battle equip screen (InventoryState::btnOkClick,
 * InventoryState.cpp:1174 - or BriefingState.cpp:290 on the preview path)
 * calls SavedBattleGame::startFirstTurn(), which ends with `_turn = 1`
 * (SavedBattleGame.cpp). The coop thin client never runs the Briefing/
 * NextTurn/Inventory chain, and the snapshot blob it loaded was streamed
 * while the host was still at turn 0. "turn" is serialized unconditionally
 * (SavedBattleGame::save), is NOT in saveBlobExcludedTopKey (SharedEcon.cpp),
 * and no structured SS2.8 bucket reads getTurn() - so with nothing to correct
 * it the two machines sit at host=1/client=0 forever, diverging in the
 * saveBlob bucket alone (this is what breaks G5 item 5's
 * `hash_now {full:true}` equality).
 *
 * COUNTER ONLY (owner decision): none of startFirstTurn()'s other work runs
 * here - not randomizeItemLocations(), not resetUnitTiles(), not the
 * per-unit prepareNewTurn(), not newTurnUpdateScripts(). Those are host-side
 * sim; every bit of state they touch reaches the thin client as bt_ev/
 * bt_action_end (SS2.4) or was already in the blob.
 *
 * SEQUENCING (why the call site is the LAST statement of the client
 * handshake, after battle_ready has been sent): onReady()'s SS2.7 hard gate
 * compares the client's saveBlob against the hash the HOST computed at offer
 * time - i.e. against a turn-0 host. The client's own saveBlob is likewise
 * computed at turn 0, a few lines above the call site. Bumping any earlier
 * (at blob load, or before coopComputeSaveBlobBucketHex(), or before the
 * battle_ready send) would put a turn-1 client hash against a turn-0 host
 * hash and tear the handshake down. Bumping here leaves a transient
 * client=1/host=0 window that closes the moment the host dismisses its equip
 * screen - and the host cannot take ANY action before dismissing it, so no
 * bt_ev/bt_action_end can be produced inside that window; the per-event `h`
 * (RB-D14) carries unitsStats only and is blind to the turn counter either
 * way.
 *
 * No wire/schema change whatsoever: nothing here is transmitted.
 */
static void coopClientMirrorFirstTurnCounter(SavedBattleGame* battle)
{
	if (!battle || !isCoopBattle())
		return;

	// Thin client only. The host owns _turn through vanilla startFirstTurn().
	if (coopBattleAuthority().hostSim)
		return;

	// Idempotent, and correct for a future mid-battle resume blob: such a
	// blob already carries turn >= 1 and must never be rewound to 1.
	if (battle->getTurn() != 0)
		return;

	battle->setTurn(1);

	Log(LOG_INFO) << "[coop-handshake] RW-FIX-TURN: client turn counter 0 -> 1 "
		"(mirrors the host's startFirstTurn(); counter only, no wire field)";
}

void onBlobChunkAppended(Game* game)
{
	if (!game || !g_pendingClient.awaitingBlob)
		return;

	// RW-TRIAGE finding (this packet's first harness run): the legacy
	// map_result_data/getline carrier drops the source blob's trailing
	// newline on reconstruction - std::getline() splits on '\n' and discards
	// it, and the sender's rejoin loop (loopData()'s sendFileClient branch)
	// re-inserts '\n' only BETWEEN lines, never after the last one. Every
	// blob here is a YAML::YamlRootNodeWriter::emit() document, which always
	// ends in '\n' - so the client always arrives exactly ONE byte short of
	// blobBytes. Tolerate exactly that (never more - a bigger shortfall is
	// still "still receiving") and restore the byte before hashing: blobSha
	// was computed HOST-side over the true, un-truncated bytes.
	if (mapData.size() < g_pendingClient.blobBytes)
	{
		if (mapData.size() + 1 != g_pendingClient.blobBytes)
			return; // still receiving
		mapData += '\n';
	}

	g_pendingClient.awaitingBlob = false; // one-shot: never re-enter on a later, unrelated chunk

	const std::uint32_t battleId = g_pendingClient.battleId;
	const std::string expectedSha = g_pendingClient.blobSha;
	const Json::Value missionLabel = g_pendingClient.missionLabel; // W1-P2 (SS2.W1)

	// Take ownership of the accumulated blob BEFORE any sha/parse work, so a
	// stray extra chunk arriving late cannot corrupt a second read of mapData.
	std::string blob;
	blob.swap(mapData);

	const std::string actualSha = coopSha256Hex(blob); // IR-6

	if (expectedSha.empty() || actualSha != expectedSha)
	{
		Log(LOG_ERROR) << "[coop-handshake] battle blob sha MISMATCH (battleId=" << battleId
			<< ", expected=" << expectedSha << ", got=" << actualSha
			<< ") - refusing (corrupt), returning to geoscape/lobby cleanly (nothing was loaded)";

		Json::Value r(Json::objectValue);
		r["state"] = "battle_refuse";
		r["battleId"] = battleId;
		r["reason"] = "corrupt";
		CoopEmit::sendBattle(r);

		resetBattleAuthority(); // back to Idle - nothing was ever loaded, nothing to unwind
		return;
	}

	static const std::string kKey = "coop_battle_handshake";
	{
		std::lock_guard<std::mutex> lock(connectionTCP::coopFilesMutex);
		connectionTCP::coopFilesClient[kKey] = blob;
	}

	// The client_save->loadCoopSaveFromMemory precedent (connectionTCP.cpp's
	// writeHostMapFile(), ~:10926 region before this packet's edits).
	SavedGame* newSave = new SavedGame();
	newSave->loadCoopSaveFromMemory(kKey, game->getMod(), game->getLanguage(), kKey);

	SavedBattleGame* battle = newSave->getSavedBattle();
	if (!battle)
	{
		Log(LOG_ERROR) << "[coop-handshake] loaded battle blob (battleId=" << battleId
			<< ") has no SavedBattleGame - refusing (corrupt)";
		delete newSave;

		Json::Value r(Json::objectValue);
		r["state"] = "battle_refuse";
		r["battleId"] = battleId;
		r["reason"] = "corrupt";
		CoopEmit::sendBattle(r);

		resetBattleAuthority();
		return;
	}

	// PRD-J02 precedent (LoadGameState.cpp): a SHARED client adopts the
	// host's streamed world as its own replica, then re-asserts its own seat
	// (the streamed save carries the HOST's coop_save_owner_player_id, 0).
	game->setSavedGame(newSave);
	if (newSave->getCampaignType() == CoopCampaignType::Shared && !connectionTCP::getServerOwner())
	{
		connectionTCP::coop_save_owner_player_id = 1;
	}

	CoopIdMaps::rebuildFrom(battle); // R4-P1 calls rebuildFrom here (CoopIdMaps.h/:942 marker)

	initBattleAuthority(battleId); // hostSim=false here (getServerOwner()==false on a client), localSeat
	coopApplySeatMap(g_pendingClient.seatMap); // R5-P1: re-apply the REAL seatMap onOffer() already validated
	coopBattleAuthority().phase = CoopBattlePhase::Active;

	// W1-P2 (SS2.W1 / WV-D9 / WV-D28 / WV-D42): apply the offer's mission
	// identity BEFORE any state is pushed. strTarget/strCraftOrBase are the two
	// BriefingState display labels and are saveBlob-HASH-excluded
	// (SharedEcon.cpp:3974), so writing them here is hash-neutral by
	// construction - which is exactly what test_rw_hash_now.py's all-buckets-
	// EQUAL at t=0 proves. The client NEVER writes missionType (WR-10): it is a
	// serialized top-level key that is NOT excluded, i.e. it IS hashed, and
	// `deployment` is carried precisely so the client never has to touch it.
	g_missionLabels = MissionLabels();
	if (missionLabel.isObject())
	{
		g_missionLabels.carried = true;
		g_missionLabels.target = missionLabel.get("target", "").asString();
		g_missionLabels.craftOrBase = missionLabel.get("craftOrBase", "").asString();
		g_missionLabels.deployment = missionLabel.get("deployment", "").asString();
		g_missionLabels.missionType = missionLabel.get("missionType", "").asString();
		battle->setMissionTarget(g_missionLabels.target);
		battle->setMissionCraftOrBase(g_missionLabels.craftOrBase);
		Log(LOG_INFO) << "[coop-handshake] mission labels applied from battle_offer: "
			"target=\"" << g_missionLabels.target << "\", craftOrBase=\""
			<< g_missionLabels.craftOrBase << "\", deployment=\""
			<< g_missionLabels.deployment << "\"";
	}
	else
	{
		Log(LOG_WARNING) << "[coop-handshake] battle_offer carried no missionLabel object "
			"- this client has no mission identity: its briefing/ctrl-B would render the "
			"generic fallback, so ctrl-B stays gated (SS2.W1)";
	}

	// W1-P3 (WAVE1-RUNBOOK.md SS4 / ruling D3 = WV-D9): this comment used to
	// read "no client-side BriefingState, this machine did not generate the
	// mission" and cited LoadGameState.cpp's "loaded save with a live battle ->
	// BattlescapeState" precedent (:334-344 region). That precedent is right for
	// a SAVE LOAD and wrong for a coop battle ENTRY: D3 converges the client's
	// entry flow onto the host's (briefing -> map), and SS2.W1 (W1-P2) gave this
	// machine the mission identity a briefing needs. The read-only BriefingState
	// is pushed below, OVER the BattlescapeState, once the map resources are
	// relinked.
	battle->loadMapResources(game->getMod());

	// RW-FIX (spike): compute the saveBlob AFTER loadMapResources. The save-loop
	// skip predicate Tile::isVoid() (SavedBattleGame::save) tests the _objects[]
	// MapData pointers, which loadMapResources() relinks from the loaded
	// mdID/mdsID indices; hashing before the relink counts every tile as void
	// (empty binTiles) and diverges from the host's fully-materialized live-battle
	// hash. (Traced 2026-09-01.)
	const std::string saveBlobHex = coopComputeSaveBlobBucketHex(battle);

	// W1-P3 (WAVE1-RUNBOOK.md SS4 / WV-D9; the adjacent finding W1-P1 disclosed
	// and the orchestrator routed to this packet): tear the client's PRE-BATTLE
	// MENU stack down before the battle states go on, the way the host's own
	// entry path already does. Until now the client pushed a bare
	// BattlescapeState over whatever it happened to be holding, so a skirmish
	// joiner sat on [MainMenuState, NewBattleState, ServerList, LobbyMenu,
	// BattlescapeState] with a DEAD lobby it could not dismiss - one defect with
	// two symptoms (test_skirmish_flow.py step 7, and every skirmish repro's
	// client stack). Two independent reasons this is not cosmetic:
	//   1. CONVERGENCE (D3). The host's SKIRMISH entry pops its whole menu stack
	//      (NewBattleState::btnOkClick's popState() pair, NewBattleState.cpp:
	//      798-799) before pushing BriefingState, while its CAMPAIGN entry keeps
	//      GeoscapeState underneath (ConfirmLandingState pushes over it).
	//      coopUnwindToSafeState() reproduces BOTH shapes with one rule: pop
	//      until a GeoscapeState or a MainMenuState is on top, and stop there.
	//   2. LIFETIME. game->setSavedGame(newSave) above DELETED the old SavedGame,
	//      so every menu state still holding pointers into it (NewBattleState::
	//      _craft / _base) is already dangling - the same shape as the
	//      ~BasescapeState "borrowed _base freed by a world restream" crash
	//      (issue #124). Popping them is strictly safer than leaving them, and
	//      the four destructors involved are empty (NewBattleState.cpp:384,
	//      ServerList.cpp:407, LobbyMenu.cpp:360, MainMenuState.cpp:441 - ~State
	//      only frees the state's own surfaces), with no stored LobbyMenu*
	//      anywhere (every consumer scans Game::getStates()).
	// Reuses the EXISTING bounded pop-to-safe-state helper rather than minting a
	// second teardown path; it is bounded at 32 pops and is guaranteed never to
	// leave Game::_states empty (see CoopHandshake.h's top doc comment for the
	// crash that already taught that lesson once). This is NOT the
	// main-menu-no-world teardown: nothing here touches the SavedGame -
	// GoToMainMenuState remains the one and only world-teardown chokepoint.
	coopUnwindToSafeState(game);

	Options::baseXResolution = Options::baseXBattlescape;
	Options::baseYResolution = Options::baseYBattlescape;
	game->getScreen()->resetDisplay(false);
	BattlescapeState* bs = new BattlescapeState;
	game->pushState(bs);
	battle->setBattleState(bs);
	bs->toggleTouchButtons(false, true);

	// W1-P3 (WAVE1-RUNBOOK.md SS4 / ruling D3 = WV-D9): the client's flow now
	// converges on the host's - briefing -> map. ORDER IS PINNED by the runbook:
	// BattlescapeState FIRST (above), then a READ-ONLY BriefingState OVER it.
	// Never inverted - the briefing has to sit on a live battle screen, exactly
	// like the ctrl-B path (BattlescapeState.cpp:2857) W1-P2 already proved out.
	//
	// It renders from state that is ALREADY correct: SS2.W1's carried
	// strTarget/strCraftOrBase were applied above (before any pushState), and
	// the ctor's one coop hook, CoopHandshake::resolveBriefingDeployment()
	// (BriefingState.cpp:100), supplies the carried AlienDeployment when this
	// machine cannot re-derive it - a thin client has no Craft and no Ufo, so
	// vanilla's craft->getDestination() fallback (BriefingState.cpp:83-99) is
	// dead here and the briefing would otherwise render the generic "should
	// never happen" branch (:104-108). No second hook is added by this packet.
	//
	// infoOnly=true IS WHAT MAKES THIS SAFE, and it is why the packet is small:
	//  - btnOkClick returns at BriefingState.cpp:302 BEFORE spawnFromPrimedItems()
	//    / tallyUnits() / NextTurnState / InventoryState (:304-330) - all HOST sim
	//    work a thin client must never run (and InventoryState::btnOkClick is the
	//    host's only startFirstTurn() caller);
	//  - the ctor returns at :246 before the base-defense retaliation bookkeeping;
	//  - the label-write body at :177 is gated on !_infoOnly, so this briefing
	//    can never re-mint or clobber the labels the offer shipped.
	// craft/base are 0 deliberately: this machine owns neither, and both branches
	// of the label body they feed are gated off by _infoOnly anyway.
	//
	// CUTSCENE + MUSIC ARE SUPPRESSED BY CONSTRUCTION: customBriefing is null, so
	// `_disableCutsceneAndMusic = _infoOnly && !customBriefing` (:142) is TRUE
	// and BriefingState::init() returns at :277 before it can push a CutsceneState
	// or call playMusic(). Passing a customBriefing to force a deployment would
	// have inverted that flag - which is exactly why SS2.W1 carries `deployment`
	// instead.
	//
	// WR-24 (palette/resolution): the ctor swaps to PAL_GEOSCAPE and the GEOSCAPE
	// base resolution (:58-60) and btnOkClick swaps them back and resetDisplay()s
	// (:297-300); over a live BattlescapeState that is a rendering hazard, not a
	// no-op. test_rw_client_briefing.py asserts the screen palette, the base
	// resolution and the map fingerprint after close_briefing, cross-checked
	// against the host, rather than "no crash".
	//
	// RB-D5: Game::run() only think()s the TOP state, but the battle apply queue
	// drains in connectionTCP::updateCoopTask(), NOT in any State - so bt_ev /
	// bt_action_end keep applying while this overlay is on top. Asserted, not
	// assumed (the test drives host emits with the client sitting in the
	// briefing and requires queueDepth to reach 0).
	game->pushState(new BriefingState(0, 0, /*infoOnly=*/true));
	Log(LOG_INFO) << "[coop-handshake] W1-P3: read-only BriefingState pushed over the "
		"client BattlescapeState (infoOnly=true -> no spawnFromPrimedItems/tallyUnits/"
		"NextTurnState/InventoryState on OK, cutscene+music suppressed)";

	// W1-P4 (WV-D9 / WV-D34): the pre-battle equip freeze applies to BOTH
	// machines, so BOTH players are told why they never got an equip screen. On
	// the HOST the notice is raised where the InventoryState push is skipped
	// (CoopHandshake::freezePreBattleEquip(), from BriefingState::btnOkClick);
	// on the CLIENT there is no skip to hang it on - the entry briefing above is
	// infoOnly, so btnOkClick returns at BriefingState.cpp:302 and never reaches
	// that push - so the notice is raised here, at battle entry, and is the
	// first thing on the _txtCoopWait strip when the player dismisses the
	// briefing.
	//
	// DISPLAY ONLY, and placed BEFORE the battle_ready build on purpose: it sets
	// a Text widget on the BattlescapeState pushed a few lines above and touches
	// NO hashed state, so it cannot perturb the saveBlob this handshake is about
	// to compute and compare. It also must not disturb the tail of the
	// handshake: coopClientMirrorFirstTurnCounter() stays the LAST statement
	// (RW-FIX-TURN's own sequencing constraint), which is why this sits here and
	// not below.
	CoopBattleUi::showEquipFrozen();

	Json::Value ready(Json::objectValue);
	ready["state"] = "battle_ready";
	ready["battleId"] = battleId;
	ready["h"] = Json::Value(Json::objectValue); // IR-5: presence-gated, empty until R2-P9
	ready["saveBlob"] = saveBlobHex;
	CoopEmit::sendBattle(ready);

	// RW-FIX-TURN: LAST statement of the client handshake, strictly after the
	// battle_ready hashes are computed AND sent - see the function's own doc
	// comment above for the sequencing constraint this placement satisfies.
	coopClientMirrorFirstTurnCounter(battle);

	Log(LOG_INFO) << "[coop-handshake] CLIENT phase Active (battleId=" << battleId
		<< ", saveBlob=" << saveBlobHex << ") - BattlescapeState pushed, battle_ready sent";
}

void onAccept(Game* game, const Json::Value& accept)
{
	if (!game || !connectionTCP::getServerOwner())
		return;

	if (!g_pendingHost.active || coopBattleAuthority().phase != CoopBattlePhase::Handshake)
	{
		Log(LOG_WARNING) << "[coop-handshake] battle_accept received with no matching pending offer - ignoring";
		return;
	}

	const std::uint32_t battleId = accept.get("battleId", 0u).asUInt();
	if (battleId != g_pendingHost.battleId)
	{
		Log(LOG_WARNING) << "[coop-handshake] battle_accept battleId mismatch (" << battleId
			<< " != " << g_pendingHost.battleId << ") - ignoring";
		return;
	}

	// Trigger the KEPT sendMissionFile carrier: loopData() (already running on
	// its own thread) watches sendFileClient/sendFileBase and streams whatever
	// is in coopFilesHost["battlehost"] (offerBattle() just populated it) as
	// map_result_data 3KB chunks, gated on WAIT_MAP_SENDER acks.
	isWaitMap = true;
	sendFileBase = false;
	sendFileClient = true;

	Log(LOG_INFO) << "[coop-handshake] battle_accept received (battleId=" << battleId
		<< ") - streaming the battle blob";
}

void onRefuse(Game* game, const Json::Value& refuse)
{
	if (!game || !connectionTCP::getServerOwner())
		return;

	const std::uint32_t battleId = refuse.get("battleId", 0u).asUInt();
	const std::string reason = refuse.get("reason", "").asString();

	if (!g_pendingHost.active || battleId != g_pendingHost.battleId)
	{
		Log(LOG_WARNING) << "[coop-handshake] battle_refuse for an unknown/stale battleId ("
			<< battleId << ", reason=" << reason << ") - ignoring";
		return;
	}

	Log(LOG_ERROR) << "[coop-handshake] battle_refuse received (battleId=" << battleId
		<< ", reason=" << reason << ") - tearing down and returning to geoscape/lobby cleanly";

	// Unwind the host's UI BEFORE dropping the battle - the caller already
	// pushed BriefingState unconditionally (see CoopHandshake.h's top doc
	// comment), so the host may be sitting anywhere from BriefingState to
	// mid-BattlescapeState by the time a refusal arrives.
	coopUnwindToSafeState(game);
	if (game->getSavedGame())
		game->getSavedGame()->setBattleGame(0);

	resetBattleAuthority();
	g_pendingHost = PendingHost();
}

void onReady(Game* game, const Json::Value& ready)
{
	if (!game || !connectionTCP::getServerOwner())
		return;

	const std::uint32_t battleId = ready.get("battleId", 0u).asUInt();

	if (!g_pendingHost.active || battleId != g_pendingHost.battleId)
	{
		Log(LOG_WARNING) << "[coop-handshake] battle_ready for an unknown/stale battleId ("
			<< battleId << ") - ignoring";
		return;
	}

	const std::string clientSaveBlob = ready.get("saveBlob", "").asString();
	const bool hPresent = ready.isMember("h") && ready["h"].isObject() && ready["h"].size() > 0;

	// SS2.8's handshake-boundary compare is the saveBlob field alone - the
	// wire-carried per-bucket boundary hash (RB-D8) lands with r3b's
	// side_transition, post-spike. A populated "h" from a peer is logged
	// only, never compared, here.
	if (hPresent)
	{
		Log(LOG_INFO) << "[coop-handshake] battle_ready carried a non-empty h bucket set ("
			<< ready["h"].size() << " buckets) - not compared at handshake (RB-D8: the "
			"wire-carried boundary hash is post-spike)";
	}

	// R2-P9 (SS2.7/SS2.8): HARD GATE RESTORED. saveBlob is now the canonical
	// SS2.8-filtered hash (coopComputeSaveBlobBucketHex ->
	// SharedEcon::computeSaveBlobHash): the machine-local FOV/discovered
	// state that made the R4-P1 raw hash EXPECTEDLY differ is excluded, so a
	// mismatch here is a REAL divergence. "battle_ready hash mismatch on the
	// host => refuse/teardown + log; no battle starts unequal" (SS2.7).
	// NOTE (flagged in this packet's report, not a silent deviation): SS2.1's
	// battle_refuse is client->host ONLY - the frozen wire has no
	// host->client refusal message, so the host cannot notify the client
	// wire-wise. It tears down its OWN side the same way onRefuse() above
	// does (coopUnwindToSafeState + drop the battle + resetBattleAuthority)
	// and simply never advances phase to Active; a paired client-side
	// notification is post-spike (rejoin territory).
	if (clientSaveBlob.empty() || clientSaveBlob != g_pendingHost.saveBlobHex)
	{
		Log(LOG_ERROR) << "[coop-handshake] battle_ready saveBlob MISMATCH (battleId=" << battleId
			<< ", host=" << g_pendingHost.saveBlobHex << ", client=" << clientSaveBlob
			<< ") - real divergence under the SS2.8 canonical bucket hash; refusing/"
			"tearing down - no battle starts unequal";

		coopUnwindToSafeState(game);
		if (game->getSavedGame())
			game->getSavedGame()->setBattleGame(0);

		resetBattleAuthority();
		g_pendingHost = PendingHost();
		return;
	}

	Log(LOG_INFO) << "[coop-handshake] battle_ready saveBlob EQUAL (" << clientSaveBlob
		<< ", battleId=" << battleId << ")";

	// The caller already pushed BriefingState unconditionally, right after
	// bgen.run() (CoopHandshake.h's top doc comment) - this flips the ONE
	// thing battle admission actually gates (CoopArbiter::onIntent's
	// isCoopBattle() check) and does not touch the state stack at all.
	coopBattleAuthority().phase = CoopBattlePhase::Active;
	g_pendingHost = PendingHost();

	Log(LOG_INFO) << "[coop-handshake] HOST phase Active (battleId=" << battleId << ")";
}

void resetPendingState()
{
	g_pendingHost = PendingHost();
	g_pendingClient = PendingClient();
	g_coopCorruptNextBlobRequested = false; // R2-P11: don't leak a stale request into the next battle
	// W1-P2 (SS2.W1): the mission identity is per-battle. Leaving it set would
	// let operationNameAlreadyMinted()/carriedDeployment() steer a LATER,
	// unrelated (possibly single-player) BriefingState.
	g_missionLabels = MissionLabels();
}

} // namespace CoopHandshake

// ===== R2-P9: client-side post-apply hash verify (BattlePump.h) =====
// SPIKE-RUNBOOK.md SS2.8. The ONE call site for the whole mismatch path
// (bucket compare -> freeze -> bt_desync -> bundle -> banner) - wired from
// CoopPump::drainApplyQueue() right after CoopDisplayQueue::onApplied()
// (BattlePump.h's own doc comment). Body lives here, next to CoopHandshake/
// CoopBattleUi above - the established home for this scaffolding.
namespace CoopHashCheck
{

void verify(const Json::Value& evOrEnd)
{
	if (!isCoopBattle())
		return;
	if (!evOrEnd.isMember("h") || !evOrEnd["h"].isObject() || evOrEnd["h"].empty())
		return; // presence-gated (SS2.8/RB-D14): nothing carried, nothing to check
	if (coopBattleAuthority().desyncFrozen.load())
		return; // already latched - SS2.8 "NO partial repair", one report only

	SavedBattleGame* battle = connectionTCP::getStaticBattle();
	if (!battle)
		return;

	SharedEcon::BattleHashSet mine;
	if (!SharedEcon::computeBattleHashes(battle, mine))
		return;

	const Json::Value& carried = evOrEnd["h"];
	for (const auto& bucketName : carried.getMemberNames())
	{
		int idx = -1;
		for (int i = 0; i < SharedEcon::BATTLE_HASH_BUCKETS; ++i)
		{
			if (bucketName == SharedEcon::battleHashBucketName(i))
			{
				idx = i;
				break;
			}
		}
		if (idx < 0)
		{
			// A future/upgraded peer's bucket this build does not know -
			// SS2.8 presence-gating: ignore, never guess.
			Log(LOG_WARNING) << "[coop-hash] ev/action_end carried unknown bucket '"
				<< bucketName << "' - ignored";
			continue;
		}

		const std::string expect = carried[bucketName].asString();
		const std::string got = coopHex64(SharedEcon::battleHashBucketValue(mine, idx));
		if (expect == got)
			continue;

		// SS2.8 hard-fail: freeze, report, NO partial repair - stop comparing
		// (even other carried buckets) at the FIRST mismatch. RW-REVEAL-SYNC
		// moved the freeze/report/bundle/banner body itself into the file-local
		// coopRaiseBattleDesync() helper (near CoopReveal) so the SS2.4a reveal
		// `base` n-mismatch raises the IDENTICAL desync; the desyncFrozen latch
		// (and the lost-race early return) lives inside it now.
		const std::uint32_t seq = evOrEnd.get("seq", 0u).asUInt();
		const std::string kind = evOrEnd.get("kind", "?").asString();
		coopRaiseBattleDesync(bucketName.c_str(), expect, got, seq, kind);
		return;
	}
}

} // namespace CoopHashCheck

// HOST: emit PING once per second (independent from client)
static uint64_t h_nextPingAt = 0;
static uint64_t h_rttAvgMs = 0;
static constexpr double kHostRttEWMA = 0.2;

static inline void hostMaybeSendPing()
{
	uint64_t t = now_ms();
	if (t >= h_nextPingAt)
	{
		h_nextPingAt = t + 1000;
		Json::Value ping;
		ping["type"] = "PING";
		ping["ts"] = Json::UInt64(t);
		sendJSONNoLock(ping);
	}
}

// HOST: when receiving PONG, compute RTT and log it
static inline bool maybeHandlePongOnHost(const Json::Value& obj)
{
	if (obj.isMember("type") && obj["type"].asString() == "PONG")
	{
		uint64_t sent = obj["ts"].asUInt64();
		uint64_t rtt = now_ms() - sent;

		OpenXcom::current_ping = std::to_string((unsigned long long)rtt);

		return true; // handled
	}
	return false;
}

void sendTCPPacketStaticData(std::string data)
{
	enqueueTx(std::move(data));
}

// CLIENT: if incoming JSON is PING, reply with PONG (mirror host behavior)
static inline bool maybeHandlePingOnClient(const Json::Value& obj)
{
	if (obj.isMember("type") && obj["type"].asString() == "PING")
	{
		Json::Value pong;
		pong["type"] = "PONG";
		pong["ts"] = obj["ts"];
		sendJSONNoLock(pong);
		return true; // handled internally
	}
	return false;
}

// Log helper
void logError(const std::string& msg)
{
	std::cerr << msg << std::endl;
	DebugLog((msg + "\n").c_str());
}

bool connectionTCP::hasCoopFile(const std::string& key)
{
	std::lock_guard<std::mutex> lock(coopFilesMutex);

	const auto& coopFiles = getServerOwner()
								? coopFilesHost
								: coopFilesClient;

	return coopFiles.find(key) != coopFiles.end();
}

std::string connectionTCP::hostBlobKey(const std::string& clientName)
{
	return "host_" + std::to_string(connectionTCP::saveID) + "_" + clientName + ".data";
}

// Single authority for "may this machine touch local saves". coopSession is the
// file-scope global behind isCoopSession(); getCoopStatic()/getServerOwner() are
// static. Solo (no session, not connected) or the host may use local .sav files;
// a coop client may not (its world lives only in the host's save).
bool connectionTCP::localSavesAllowed()
{
	return (!coopSession && !getCoopStatic()) || getServerOwner();
}

// issue #79: is the campaign on this machine finished (won or lost)? Read off
// the live save's ending, which BOTH machines have by the time the defeat is
// on screen: the host sets it in GeoscapeState, and a replica adopts it from
// the "cutscene" packet before the same cutscene plays. Once it is set there
// is nothing left to do together, so a peer leaving must cost nothing.
bool connectionTCP::campaignEnded()
{
	SavedGame* save = _staticGame ? _staticGame->getSavedGame() : nullptr;
	return save && save->getEnding() != END_NONE;
}

bool connectionTCP::localLoadsAllowed()
{
	// Same liveness terms the save gate uses, WITHOUT the host escape: a live
	// session forbids local loads for everyone (C7). Solo / post-session: allowed.
	return !coopSession && !getCoopStatic();
}


std::string connectionTCP::clientBlobKey(const std::string& hostName)
{
	return "client_" + std::to_string(connectionTCP::saveID) + "_" + hostName + ".data";
}

const std::string* connectionTCP::findHostClientBlob(const std::string& clientName)
{
	// Keys look like host_<saveID>_<clientName>.data. Match the EXACT name field
	// (so "Bob" never matches "Super_Bob") and, among matches, keep the newest
	// saveID (datetime ids are equal-width, so lexicographic compare orders
	// them). Parsing lives here, not in SavedGame::save.
	static const std::string prefix = "host_";
	static const std::string ext = ".data";
	const std::string* best = nullptr;
	std::string bestId;
	for (const auto& kv : coopFilesHost)
	{
		const std::string& k = kv.first;
		if (kv.second.empty()
			|| k.size() < prefix.size() + ext.size()
			|| k.compare(0, prefix.size(), prefix) != 0
			|| k.compare(k.size() - ext.size(), ext.size(), ext) != 0)
			continue;
		size_t idEnd = k.find('_', prefix.size());
		if (idEnd == std::string::npos || k.size() < idEnd + 1 + ext.size())
			continue;
		std::string name = k.substr(idEnd + 1, k.size() - (idEnd + 1) - ext.size());
		if (name != clientName)
			continue;
		std::string id = k.substr(prefix.size(), idEnd - prefix.size());
		if (!best || id > bestId)
		{
			best = &kv.second;
			bestId = id;
		}
	}
	return best;
}

// One authority for the campaign_start packet (see header). Reads the player
// roster from the save (host lobby start sets it just before calling this, so
// save->getCoopPlayers() equals the freshly-built list).
Json::Value connectionTCP::buildCampaignStartPacket(const SavedGame* save)
{
	Json::Value root;
	root["state"] = "campaign_start";
	root["difficulty"] = (int)save->getDifficulty();
	root["gamemode"] = connectionTCP::_coopGamemode;
	root["saveID"] = static_cast<Json::Int64>(connectionTCP::saveID);
	// PRD-J01: propagate the campaign economy model so the client adopts it.
	root["campaignType"] = static_cast<int>(save->getCampaignType());
	int idx = 0;
	for (const auto& p : save->getCoopPlayers())
	{
		root["players"][idx++] = p;
	}
	return root;
}

bool connectionTCP::inCoopCampaignContext() const
{
	return _game->getSavedGame()
		&& !_game->getSavedGame()->getCountries()->empty()
		&& _game->getSavedGame()->isCoopSave();
}

// Drop world-blob captures that key the same player under an older saveID, so
// the maps hold one entry per player instead of growing with every saveID
// regeneration. Matches the EXACT player-name field of the key
// (<prefix><saveID>_<playerName>.data), never a suffix: the old "ends with
// _<name>.data" test also matched a DIFFERENT player whose name ended in the
// stored name (storing "Bob" erased "Super_Bob"'s world - CONFIRMED S8 data
// loss). Names are compared field-for-field so no such collision is possible.
static void eraseStaleBlobEntries(std::unordered_map<std::string, std::string>& files,
								  const std::string& prefix,
								  const std::string& playerName,
								  const std::string& keepKey)
{
	for (auto it = files.begin(); it != files.end();)
	{
		const std::string& k = it->first;
		bool stale = false;
		if (k != keepKey
			&& k.size() >= 5
			&& k.compare(0, prefix.size(), prefix) == 0
			&& k.compare(k.size() - 5, 5, ".data") == 0)
		{
			// player-name field: everything between the saveID's trailing
			// underscore and the ".data" extension.
			size_t idEnd = k.find('_', prefix.size());
			if (idEnd != std::string::npos && k.size() >= idEnd + 1 + 5)
			{
				std::string name = k.substr(idEnd + 1, k.size() - (idEnd + 1) - 5);
				stale = (name == playerName);
			}
		}
		if (stale)
			it = files.erase(it);
		else
			++it;
	}
}

namespace {
// PRD-11 C13: thrown by the streamer's ack-wait loops when the connection is
// torn down mid-transfer, so the streamer abandons the stream instead of
// parking forever on isWaitMap while still holding sendFileClient.
struct StreamAbort {};
}

// in the loop, load the map file data between host and client
void connectionTCP::loopData()
{
	// Wait for the client's map-chunk ack (isWaitMap), but bail out if the
	// connection is being torn down so a mid-transfer drop cannot park this
	// thread. The teardown signal is disconnectTCP forcing BOTH send flags false
	// (a live transfer always holds exactly one of them true); the destructor
	// sets _stop. coopSession is NOT a reliable "streaming" signal here - the
	// redesigned resume/rejoin flows stream a world without the old ready
	// handshake that sets it, so keying on it aborts legitimate streams.
	auto waitForMapAck = [&]() {
		while (!isWaitMap)
		{
			if (_stop || (!sendFileClient && !sendFileHost))
				throw StreamAbort{};
			SDL_Delay(20);
		}
	};

	while (!_stop)
	{
		try
		{
			if (sendFileClient)
			{
				int fileindex = 0;

				std::string filepath = "";

				if (sendProgressLoadFileToClient != "")
				{
					filepath = sendProgressLoadFileToClient;
				}
				else if (sendFileBase)
				{
					filepath = "basehost";
				}
				else
				{
					filepath = "battlehost";
				}

				std::istringstream memoryStream;
				std::istream* myfile = nullptr;

				if (sendProgressLoadFileToClient == "")
				{
					// Read from memory
					std::lock_guard<std::mutex> lock(connectionTCP::coopFilesMutex);

					const auto& coopFiles = getServerOwner()
												? connectionTCP::coopFilesHost
												: connectionTCP::coopFilesClient;

					auto it = coopFiles.find(filepath);
					if (it == coopFiles.end())
					{
						throw std::runtime_error("Failed to read from hash map with key: " + filepath);
					}

					memoryStream.str(it->second);
					myfile = &memoryStream;
				}
				else
				{
					// Resume blob, snapshotted on the main thread when the
					// request_load_progress arrived (nothing streams from disk)
					memoryStream.str(sendProgressLoadBlob);
					myfile = &memoryStream;
				}

				std::string line;
				std::string result;

				while (std::getline(*myfile, line))
				{
					waitForMapAck();

					std::cout << line << std::endl;
					if (fileindex != 0)
						line = "\n" + line;
					result += line;

					if (result.size() > 3000 && result.size() < 4000)
					{
						isWaitMap = false;
						Json::Value obj;
						obj["state"] = "map_result_data";
						obj["data"] = result;
						sendTCPPacketStaticData(obj.toStyledString());
						result = "";
					}
					else if (result.size() > 4000)
					{
						isWaitMap = true;
						for (unsigned i = 0; i < result.length(); i += 3000)
						{
							waitForMapAck();

							isWaitMap = false;

							std::string splitValue = result.substr(i, 3000);
							Json::Value obj;
							obj["state"] = "map_result_data";
							obj["data"] = splitValue;
							sendTCPPacketStaticData(obj.toStyledString());
						}
						result = "";
					}
					fileindex++;
				}

				isWaitMap = false;
				Json::Value obj;
				obj["state"] = "map_result_data";
				obj["data"] = result;
				sendTCPPacketStaticData(obj.toStyledString());

				waitForMapAck();

				std::string jsonData = sendFileBase
										   ? "{\"state\" : \"MAP_RESULT_CLIENT_BASE\"}"
										   : "{\"state\" : \"MAP_RESULT_CLIENT\"}";

				if (sendProgressLoadFileToClient != "")
				{
					jsonData = "{\"state\" : \"MAP_RESULT_LOAD_PROGRESS\"}";
				}

				sendTCPPacketStaticData(jsonData);
				sendFileBase = false;
				sendFileClient = false;
				sendFileSave = false;
				sendProgressLoadFileToClient = "";
				sendProgressLoadBlob = "";
			}
			else if (sendFileHost)
			{
				int fileindex = 0;

				std::string filepath;

				if (sendProgressSaveFileToHost)
				{
					filepath = clientBlobKey(_game->getCoopMod()->getHostName());
				}
				else if (sendFileSave)
				{
					filepath = "battlehost";
				}
				else if (sendFileBase)
				{
					filepath = "basehost";
				}
				else if (connectionTCP::_coopCampaign)
				{
					filepath = "basehost";
				}
				else
				{
					filepath = "battlehost";
				}

				std::string coopKey = filepath; // tai filename, jos mapin avain on filename

				std::string blobCopy;
				{
					std::lock_guard<std::mutex> lock(connectionTCP::coopFilesMutex);

					const auto& coopFiles = getServerOwner()
												? connectionTCP::coopFilesHost
												: connectionTCP::coopFilesClient;

					auto it = coopFiles.find(coopKey);
					if (it == coopFiles.end())
					{
						throw std::runtime_error("Failed to read from hash map with key: " + coopKey);
					}

					blobCopy = it->second;
				}

				std::istringstream myfile(blobCopy);

				std::string line;
				std::string result;

				while (getline(myfile, line))
				{
					waitForMapAck();

					std::cout << line << std::endl;
					if (fileindex != 0)
						line = "\n" + line;
					result += line;

					if (result.size() > 3000 && result.size() < 4000)
					{
						isWaitMap = false;
						Json::Value obj;
						obj["state"] = "map_result_data";
						obj["data"] = result;
						sendTCPPacketStaticData(obj.toStyledString());
						result.clear();
					}
					else if (result.size() > 4000)
					{
						isWaitMap = true;
						for (unsigned i = 0; i < result.length(); i += 3000)
						{
							waitForMapAck();

							isWaitMap = false;

							std::string splitValue = result.substr(i, 3000);
							Json::Value obj;
							obj["state"] = "map_result_data";
							obj["data"] = splitValue;
							sendTCPPacketStaticData(obj.toStyledString());
						}
						result.clear();
					}
					fileindex++;
				}

				isWaitMap = false;
				Json::Value obj;
				obj["state"] = "map_result_data";
				obj["data"] = result;
				sendTCPPacketStaticData(obj.toStyledString());

				waitForMapAck();

				std::string jsonData = sendFileBase
										   ? "{\"state\" : \"MAP_RESULT_HOST_BASE\"}"
										   : "{\"state\" : \"MAP_RESULT_HOST\"}";

				if (sendProgressSaveFileToHost)
				{
					jsonData = "{\"state\" : \"MAP_RESULT_SAVE_PROGRESS\"}";
				}

				sendTCPPacketStaticData(jsonData);
				sendFileBase = false;
				sendFileHost = false;
				sendFileSave = false;
				sendProgressSaveFileToHost = false;
			}
		}
		catch (const StreamAbort&)
		{
			// PRD-11 C13: connection torn down mid-transfer. Abandon the stream
			// and release every send flag so the streamer returns to idle instead
			// of parking with sendFileClient still set.
			Log(LOG_INFO) << "[coop] streamer: connection torn down mid-transfer, abandoning stream";
			sendFileBase = false;
			sendFileClient = false;
			sendFileHost = false;
			sendFileSave = false;
			sendProgressLoadFileToClient = "";
			sendProgressLoadBlob = "";
			sendProgressSaveFileToHost = false;
		}
		catch (const std::exception& e)
		{
			// Build one message for both logError and crash.log
			std::string msg = "Error in loopData: " + std::string(e.what());

			logError(msg);
			CRASH_LOG(msg);
		}
		catch (...)
		{
			std::string msg = "Unknown error in loopData!";

			logError(msg);
			CRASH_LOG(msg);
		}

		SDL_Delay(10); // Prevent 100% CPU usage when idle
	}
}

void connectionTCP::setGiftSelectedBattleUnit(BattleUnit* unit)
{
	// This is intentionally independent of SavedBattleGame::selectedUnit. The
	// latter follows the active turn, while this value belongs only to the local
	// player and may be updated by left-clicking during another player's turn.
	if (canGiftBattleUnit(unit))
	{
		_giftSelectedBattleUnitId = unit->getId();
	}
}

BattleUnit* connectionTCP::getGiftSelectedBattleUnit() const
{
	if (_giftSelectedBattleUnitId < 0 || !_game || !_game->getSavedGame())
	{
		return nullptr;
	}

	SavedBattleGame* battle = _game->getSavedGame()->getSavedBattle();
	if (!battle)
	{
		return nullptr;
	}

	for (BattleUnit* unit : *battle->getUnits())
	{
		if (unit->getId() == _giftSelectedBattleUnitId)
		{
			// Revalidate every read because the unit may have died or changed owner
			// after it was clicked. A stale local selection must never be giftable.
			return canGiftBattleUnit(unit) ? unit : nullptr;
		}
	}

	return nullptr;
}

void connectionTCP::clearGiftSelectedBattleUnit()
{
	_giftSelectedBattleUnitId = -1;
}

bool connectionTCP::canGiftBattleUnit(const BattleUnit* unit) const
{
	if (!unit || !_game || !_game->getSavedGame() || !_game->getSavedGame()->getSavedBattle())
	{
		return false;
	}

	if (!getCoopStatic() || getCoopGamemode() == 2 || getCoopGamemode() == 3)
	{
		return false;
	}

	// Ownership, not the active turn, decides whether the transfer is legal.
	// This lets both peers gift different soldiers at the same time without
	// allowing either peer to transfer a soldier controlled by somebody else.
	return unit->getFaction() == FACTION_PLAYER
		&& !unit->isOut()
		&& unit->getHealth() > 0
		&& (int)unit->getCoopSeat() == localSeat();
}

void connectionTCP::refreshBattleGiftControlState()
{
	if (!_game || !_game->getSavedGame())
	{
		return;
	}

	SavedBattleGame* battle = _game->getSavedGame()->getSavedBattle();
	if (!battle || battle->isPreview() || !getCoopStatic())
	{
		return;
	}

	const int localPlayerId = localSeat();
	BattleUnit* firstLocalUnit = nullptr;

	for (BattleUnit* unit : *battle->getUnits())
	{
		if (unit->getFaction() == FACTION_PLAYER
			&& !unit->isOut()
			&& unit->getHealth() > 0
			&& (int)unit->getCoopSeat() == localPlayerId)
		{
			firstLocalUnit = unit;
			break;
		}
	}

	BattlescapeState* battleState = battle->getBattleState();
	BattleUnit* selected = battle->getSelectedUnit();

	// The normal Battlescape selectedUnit can already be set before the local
	// gift selection is initialized, and on a waiting peer it may represent the
	// remote active player's unit. Initialize the separate local gift selection
	// from a valid locally owned unit instead of relying on selectedUnit. This
	// allows the initially available soldier to be gifted immediately without a
	// mouse click while keeping the active-turn selection untouched.
	if (!getGiftSelectedBattleUnit())
	{
		BattleUnit* initialGiftUnit = canGiftBattleUnit(selected)
			? selected
			: firstLocalUnit;
		setGiftSelectedBattleUnit(initialGiftUnit);
	}

	// R1-P4: the battleState->getCurrentTurn() OR-clauses that used to mirror
	// this against BattlescapeState are gone - BattlescapeState::getCurrentTurn
	// was a coop hook the r1 vanilla restore (911ca487f) stripped. connectionTCP's
	// own tracked _playerTurn (getPlayerTurn()) was always the primary source;
	// the real turn-machine mirror returns with r2 (RB-D9/RB-D11).
	const bool localTurnActive = getPlayerTurn() == 2;
	const bool localWasSpectator = getPlayerTurn() == 4;

	if (!firstLocalUnit)
	{
		clearGiftSelectedBattleUnit();

		// Gifting is allowed while the other player is taking their turn. In that
		// case this machine must remain in its normal waiting state: changing it to
		// spectator would overwrite the synchronized turn even though the remote
		// player is still active. The regular turn-start roster check will enter
		// spectator mode later if this player still owns no living soldiers.
		if (!localTurnActive)
		{
			return;
		}

		// The final soldier was gifted during this player's own active turn.
		// Clear the now-invalid active selection and enter spectator mode at once.
		if (selected && (int)selected->getCoopSeat() != localPlayerId)
		{
			battle->setSelectedUnit(nullptr);
		}

		setPlayerTurn(4);
		// R1-P4: the BattlescapeState::setCurrentTurn/showCoopWarning mirror+banner
		// calls that used to run here are gone - both were coop hooks the r1
		// vanilla restore stripped from BattlescapeState. connectionTCP's own
		// _playerTurn (set above) is the surviving source of truth; the
		// turn-machine mirror and its UI banner return with r2 (RB-D9/RB-D11).
		return;
	}

	// Never replace SavedBattleGame::selectedUnit on a waiting machine. That
	// value belongs to the player whose turn is currently active. A local unit
	// is selected only on our own turn or when restoring from spectator mode.
	if ((localTurnActive || localWasSpectator)
		&& (!selected || selected->isOut() || selected->getHealth() <= 0
			|| (int)selected->getCoopSeat() != localPlayerId))
	{
		battle->setSelectedUnit(firstLocalUnit);

		// setSelectedUnit() bypasses both the mouse-click path and
		// SavedBattleGame::selectPlayerUnit(). Keep the separate local gift
		// selection synchronized here so a player restored from spectator mode
		// can gift the received soldier immediately without clicking it first.
		setGiftSelectedBattleUnit(firstLocalUnit);

		if (battleState)
		{
			battleState->updateSoldierInfo();
		}
	}

	if (battleState && localWasSpectator)
	{
		const int restoredTurn = _isActivePlayerSync ? 2 : 1;
		setPlayerTurn(restoredTurn);
		// R1-P4: the BattlescapeState::setCurrentTurn/showCoopWarning/
		// showCoopLongWarning calls that used to mirror+announce this are gone
		// - all three were coop hooks the r1 vanilla restore stripped from
		// BattlescapeState. connectionTCP's own _playerTurn (set above) is the
		// surviving source of truth; the mirror and its UI banners return with
		// r2 (RB-D9/RB-D11).
	}
}

// Unique id for one outgoing gift packet: seat tag + wall-clock + counter.
// Keyed on localSeat(), NOT getHost(): getHost() is the transient mission/save
// transfer role and reaches true on BOTH machines (NewBattleState sets it
// unconditionally in skirmish; BattlescapeState only re-derives it from
// getServerOwner() on the SHARED branch). Two senders sharing one prefix can
// mint the same id in the same second, and a third seat would then drop the
// second sender's gift as a duplicate. Seat 0 -> 1e15 and seat 1 -> 2e15, so
// this is byte-identical to the old formula wherever getHost() was correct.
long long connectionTCP::nextGiftXferId()
{
	return (long long)(localSeat() + 1) * 1000000000000000LL
		+ (long long)time(0) * 1000LL + (++_giftSendCounter % 1000);
}

void connectionTCP::giftBattleUnit(BattleUnit* unit, int newOwnerId, bool broadcast)
{
	if (!canGiftBattleUnit(unit) || newOwnerId < 0 || newOwnerId >= seatCount() || newOwnerId == localSeat())
	{
		Log(LOG_WARNING) << "[coop-gift] rejected battle gift: invalid unit, owner, or target";
		return;
	}

	if (unit->getGeoscapeSoldier())
	{
		giftSoldier(unit->getGeoscapeSoldier(), newOwnerId, broadcast);
		return;
	}

	// Skirmish-only units have no persistent Soldier object. Their gift is only
	// a live Battlescape control transfer, but it follows the same ownership,
	// stale-packet and notification rules as campaign soldiers.
	const int previousOwner = (int)unit->getCoopSeat();
	unit->setCoopSeat((CoopSeat)newOwnerId);
	if (_giftSelectedBattleUnitId == unit->getId())
	{
		clearGiftSelectedBattleUnit();
	}

	SavedBattleGame* battle = _game->getSavedGame()->getSavedBattle();
	if (battle->getSelectedUnit() == unit && newOwnerId != localSeat())
	{
		battle->selectNextPlayerUnit();
	}

	if (broadcast)
	{
		const long long giftEventId = nextGiftXferId();

		// R4-REWIRE: "giveUnit" is a quarantined battle-sim message (R1-P3,
		// inventory-wire-protocol.md section A) - its onTCPMessage receive handler
		// is deleted, so this send now lands on the peer's legacyBattleMessageDropped
		// catch-all. The battle-gift choreography itself is unchanged pending r4/r5.
		Json::Value obj;
		obj["state"] = "giveUnit";
		obj["unit_id"] = unit->getId();
		obj["coop"] = newOwnerId;
		obj["previous_owner"] = previousOwner;
		obj["giver_name"] = seatName(previousOwner);
		obj["unit_name"] = unit->getName(_game->getLanguage());
		obj["xfer_id"] = Json::Value::Int64(giftEventId);
		sendTCPPacketData(obj.toStyledString());
	}

	refreshBattleGiftControlState();
}

void connectionTCP::giftSoldier(Soldier* soldier, int newOwnerId, bool broadcast)
{
	if (!soldier || !_game->getSavedGame())
	{
		return;
	}

	// SHARED geoscape gifts are host-authoritative. Battle-time gifts use the
	// live-control path below because both battle replicas must update at once.
	if (broadcast && isSharedCampaign() && !_game->getSavedGame()->getSavedBattle())
	{
		int baseId = 0;
		auto* bases = _game->getSavedGame()->getBases();
		for (size_t i = 0; i < bases->size(); ++i)
		{
			bool here = false;
			for (auto* s : *bases->at(i)->getSoldiers())
				if (s == soldier) { here = true; break; }
			if (here) { baseId = (int)i; break; }
		}
		Json::Value payload;
		payload["soldierId"] = soldier->getId();
		payload["newOwner"] = newOwnerId;
		SharedEcon::submitLocalCmd(_game, "soldier_gift", baseId, payload);
		return;
	}

	SavedBattleGame* battle = _game->getSavedGame()->getSavedBattle();
	const int localPlayerId = localSeat();

	if (battle)
	{
		BattleUnit* battleUnit = nullptr;
		for (BattleUnit* unit : *battle->getUnits())
		{
			if (unit->getGeoscapeSoldier() == soldier)
			{
				battleUnit = unit;
				break;
			}
		}

		if (!canGiftBattleUnit(battleUnit)
			|| newOwnerId < 0
			|| newOwnerId >= seatCount()
			|| newOwnerId == localPlayerId)
		{
			Log(LOG_WARNING) << "[coop-gift] rejected campaign battle gift for '" << soldier->getName()
				<< "': local seat does not own the live unit or target is invalid";
			return;
		}

		const int previousOwner = (int)battleUnit->getCoopSeat();
		soldier->setOwnerPlayerId(newOwnerId);
		soldier->setCoop(newOwnerId);
		battleUnit->setCoopSeat((CoopSeat)newOwnerId);
		if (_giftSelectedBattleUnitId == battleUnit->getId())
		{
			clearGiftSelectedBattleUnit();
		}

		Log(LOG_INFO) << "[coop-gift] battle gift '" << soldier->getName() << "' id=" << soldier->getId()
			<< " previousOwner=" << previousOwner << " newOwner=" << newOwnerId
			<< " localPlayer=" << localPlayerId << " broadcast=" << (broadcast ? 1 : 0);

		if (battle->getSelectedUnit() == battleUnit && newOwnerId != localPlayerId)
		{
			battle->selectNextPlayerUnit();
		}

		// A later gift-back supersedes an older pending physical transfer for the
		// same Soldier. Keep at most one final post-mission destination.
		_pendingSoldierGifts.erase(
			std::remove_if(_pendingSoldierGifts.begin(), _pendingSoldierGifts.end(),
				[soldier](const PendingSoldierGift& pending) { return pending.soldier == soldier; }),
			_pendingSoldierGifts.end());
		// Issue #126: never queue the SEPARATE physical hand-off in a SHARED
		// campaign. SHARED is ONE host-authoritative world - the in-battle
		// ownership flip above already moved the (shared) soldier on both battle
		// replicas, and the host's post-battle whole-world restream carries that to
		// both machines. Running the physical hand-off (sendSoldierGiftPacket +
		// removeSoldierFromLocalBases, with the peer re-materialising the soldier
		// via `new Soldier`) DUPLICATES the shared soldier when it is gifted back
		// and forth, and LOSES it on a one-way gift. The live flip is sufficient.
		if (broadcast && newOwnerId != localPlayerId && !isSharedCampaign())
		{
			int craftId = -1;
			std::string craftType;

			// Capture the craft identity now, while the in-battle Craft* still
			// belongs to the live world. The battle/save hand-off may destroy or
			// replace that Craft before processPendingSoldierGifts() runs, so the
			// deferred transfer must never dereference soldier->getCraft().
			if (Craft* craft = soldier->getCraft())
			{
				craftId = craft->getId();
				craftType = craft->getType();
			}

			_pendingSoldierGifts.push_back(
				PendingSoldierGift(soldier, newOwnerId, craftId, craftType));
		}

		if (broadcast)
		{
			const long long giftEventId = nextGiftXferId();

			Json::Value obj;
			obj["state"] = "giftSoldier";
			obj["soldier_id"] = soldier->getId();
			obj["owner"] = newOwnerId;
			obj["unit_id"] = battleUnit->getId();
			obj["previous_owner"] = previousOwner;
			obj["giver_name"] = seatName(previousOwner);
			obj["soldier_name"] = soldier->getName();
			obj["xfer_id"] = Json::Value::Int64(giftEventId);
			sendTCPPacketData(obj.toStyledString());
		}

		refreshBattleGiftControlState();
		return;
	}

	// Geoscape transfer: move the persistent soldier object to its new owner.
	soldier->setOwnerPlayerId(newOwnerId);
	soldier->setCoop(newOwnerId);

	Log(LOG_INFO) << "[coop-gift] giftSoldier '" << soldier->getName() << "' id=" << soldier->getId()
		<< " newOwner=" << newOwnerId << " localPlayer=" << localPlayerId
		<< " broadcast=" << (broadcast ? 1 : 0) << " inBattle=0";

	if (broadcast && newOwnerId != localPlayerId)
	{
		// The soldier's object lives in its owner's save (guest-soldier model):
		// hand it to the peer and drop it from our world while retaining its
		// station-base id in the serialized packet.
		sendSoldierGiftPacket(soldier, newOwnerId);
		removeSoldierFromLocalBases(soldier);
		_giftedSoldiers.push_back(soldier);
		_giftedAwaySoldierIds.insert(soldier->getId());
		pushProgressToHostSilently();
	}
}

void connectionTCP::processPendingSoldierGifts()
{

	// Replay physical gifts that arrived while our world was swapped out
	// for the peer's base view OR for a coop battle. The flags clear before
	// LoadGameState has actually restored our save, so also require that an
	// own (non-mirror) base is present, that no own-world reload is still
	// pending (LoadGameState on top of the stack), and that we are not mid
	// mission-end - the swapped peer/battle world would otherwise re-swallow
	// the soldier and mark its packet id as seen, losing it for good.
	bool ownWorldReady = false;

	State* topState = _game->getStates().empty() ? nullptr : _game->getStates().back();
	bool ownWorldLoadPending = (dynamic_cast<LoadGameState*>(topState) != nullptr);

	if (!_pendingIncomingGifts.empty()
	    && _game->getCoopMod()->playerInsideCoopBase == false
	    && _game->getCoopMod()->coopMissionEnd == false
	    && !ownWorldLoadPending
	    && _game->getSavedGame()
	    && !_game->getSavedGame()->getSavedBattle())
	{

		for (auto& base : *_game->getSavedGame()->getBases())
		{
			if (base->_coopBase == false && base->_coopIcon == false)
			{
				ownWorldReady = true;
				break;
			}
		}

	}

	if (ownWorldReady)
	{

		std::vector<Json::Value> replay;
		replay.swap(_pendingIncomingGifts);

		for (auto& obj : replay)
		{
			onTCPMessage("giftSoldier", obj);
		}

	}

	if (_game->getSavedGame() && !_game->getSavedGame()->getSavedBattle() && getCoopStatic() && getCoopCampaign() && _pendingSoldierGifts.empty())
	{

		// Targeted sweep: a stale copy of a soldier we gifted away this
		// session can resurrect when the pre-visit "basehost" snapshot is
		// restored after a gift made while viewing the peer's base. Park
		// exactly those (matched by id AND still peer-owned - a soldier
		// traded back to us has our owner id and is left alone). Deliberately
		// NOT a blanket owner check: legacy saves carry stale ownerPlayerId
		// values on unrelated soldiers.
		if (!_giftedAwaySoldierIds.empty())
		{

			int localPlayerId = localSeat();

			for (auto& base : *_game->getSavedGame()->getBases())
			{

				auto& soldiers = *base->getSoldiers();

				for (auto it = soldiers.begin(); it != soldiers.end();)
				{

					Soldier* s = *it;

					if (_giftedAwaySoldierIds.count(s->getId()) != 0 && s->getOwnerPlayerId() != 999 && s->getOwnerPlayerId() != localPlayerId)
					{
						_giftedSoldiers.push_back(s);
						it = soldiers.erase(it);
					}
					else
					{
						++it;
					}

				}

			}

		}

	}

	if (_pendingSoldierGifts.empty())
	{
		return;
	}

	if (_game->getSavedGame() && _game->getSavedGame()->getSavedBattle())
	{
		// Still in battle; try again later.
		return;
	}

	// Issue #126: SHARED never runs the SEPARATE physical hand-off (giftSoldier
	// no longer queues it in SHARED). Drop any residual entry rather than replay
	// it - the shared world's ownership is already carried by the host restream,
	// and materialising a copy on the peer would duplicate the shared soldier.
	if (isSharedCampaign())
	{
		_pendingSoldierGifts.clear();
		return;
	}

	for (const PendingSoldierGift& pending : _pendingSoldierGifts)
	{

		Soldier* soldier = pending.soldier;

		// Died during the mission: stays in the giver's memorial. The physical
		// hand-off never happened, so undo the in-battle ownership flip that
		// giftSoldier applied - otherwise the fallen soldier would
		// sit in the giver's Hall of Honour still flagged as the peer's
		// (coop/ownerPlayerId), and the receiver never gets a memorial entry
		// (its gift was skipped). Reset to a plain own-soldier so the
		// giver's memorial records it correctly.
		if (soldier->getDeath())
		{
			soldier->setCoop(0);
			soldier->setOwnerPlayerId(999);
			continue;
		}

		// Auto-keep an in-battle-gifted soldier on the craft it was deployed
		// on, mirroring how a giver's own crew stays aboard after a mission.
		// Use only the identity snapshot captured when the gift was queued. A
		// non-null Soldier::getCraft() here may point into the destroyed battle
		// world; calling getId() or getType() on it would be a use-after-free.
		// A wounded survivor is deliberately left unassigned so it is not flown
		// straight back out while it should be recovering.
		if (pending.craftId >= 0)
		{
			if (!soldier->isWounded())
			{
				soldier->setCoopCraft(pending.craftId);
				soldier->setCoopCraftType(pending.craftType);
			}
			else
			{
				soldier->setCoopCraft(-1);
				soldier->setCoopCraftType("");
			}
		}

		sendSoldierGiftPacket(soldier, pending.newOwnerId);
		removeSoldierFromLocalBases(soldier);
		_giftedSoldiers.push_back(soldier);
		_giftedAwaySoldierIds.insert(soldier->getId());

	}

	_pendingSoldierGifts.clear();

	// transfers happened while our world was busy - sync the blob now
	pushProgressToHostSilently();

}

void connectionTCP::pushProgressToHostSilently()
{

	// Client only: serialize the current world and stream it to the host so
	// the host's next save embeds an up-to-date client blob. Never while the
	// world is swapped out - a base visit, an active battle, or the mission-end
	// window before the own-world reload (GeoscapeState::init) has run. In all
	// of those the live save is the PEER's world; uploading it would overwrite
	// our own-world blob with the host's world and destroy our roster.
	if (getServerOwner() || !getCoopStatic() || connectionTCP::saveID == 0)
	{
		return;
	}
	// PRD-J02: a SHARED replica has no world of its own to push - the host's
	// single authoritative save is the whole truth. No-op.
	if (isSharedReplica())
	{
		return;
	}
	State* topStatePush = _game->getStates().empty() ? nullptr : _game->getStates().back();
	if (!_game->getSavedGame() || _game->getSavedGame()->getSavedBattle()
	    || _game->getCoopMod()->playerInsideCoopBase
	    || _game->getCoopMod()->coopMissionEnd
	    || (dynamic_cast<LoadGameState*>(topStatePush) != nullptr))
	{
		return;
	}

	std::string filename = clientBlobKey(_game->getCoopMod()->getHostName());
	_game->getSavedGame()->saveCoopToMemory(filename, _game->getMod(), filename);
	{
		std::lock_guard<std::mutex> lock(coopFilesMutex);
		eraseStaleBlobEntries(coopFilesClient, "client_", _game->getCoopMod()->getHostName(), filename);
	}

	Json::Value obj;
	obj["state"] = "SEND_FILE_HOST_TRUE_SAVE_PROGRESS";
	sendTCPPacketData(obj.toStyledString());

	Log(LOG_INFO) << "[coop-gift] pushed client progress to host (" << filename << ")";

}

void connectionTCP::syncOwnWorldGuestCraft(int coopBaseId, const std::map<std::string, std::pair<int, std::string>>& assignments)
{

	// Fix B (Bug 1). Client only. Durably mirror the client's guest->host-craft
	// assignments into the client's OWN-world blob (client_<saveID>_<host>.data),
	// which is exactly what GeoscapeState::init reloads at mission end. The real
	// mirror-base UI (SoldiersState::btnOkClick) only writes CoopCraft into the
	// "basehost" blob (the client's copy of the HOST world), so without this the
	// guest's CoopCraft reverts to its stale value and the soldier is unassigned
	// from the skyranger after every battle.
	//
	// Unlike pushProgressToHostSilently() this deliberately NEVER serializes or
	// uploads the LIVE save and does NOT send SEND_FILE_HOST_TRUE_SAVE_PROGRESS:
	// this runs while the client is inside the mirror base, where the live save
	// is the swapped-in HOST world. That packet round-trips and drives the client
	// to upload its live (host) world as the client blob - the exact corruption
	// Fix A prevents. We only edit the in-memory own-world blob, which is all the
	// mission-end reload needs.
	if (getServerOwner() || !getCoopStatic() || connectionTCP::saveID == 0)
	{
		return;
	}
	if (assignments.empty())
	{
		return;
	}

	std::string filename = clientBlobKey(_game->getCoopMod()->getHostName());
	if (!hasCoopFile(filename))
	{
		return;
	}

	SavedGame* ownWorld = new SavedGame();
	ownWorld->loadCoopSaveFromMemory(filename, _game->getMod(), _game->getLanguage(), filename);

	bool changed = false;
	for (auto* base : *ownWorld->getBases())
	{
		for (auto* s : *base->getSoldiers())
		{
			// Only the client's own guests live in this blob; matching by the
			// peer base id + coop name skips any unrelated soldiers. Soldier ids
			// differ across worlds, so coopName is the stable cross-world key.
			if (s->getCoopBase() != coopBaseId)
			{
				continue;
			}
			auto it = assignments.find(s->getCoopName());
			if (it == assignments.end())
			{
				continue;
			}
			if (s->getCoopCraft() != it->second.first || s->getCoopCraftType() != it->second.second)
			{
				s->setCoopCraft(it->second.first);
				s->setCoopCraftType(it->second.second);
				changed = true;
			}
		}
	}

	if (changed)
	{
		ownWorld->saveCoopToMemory(filename, _game->getMod(), filename);
		Log(LOG_INFO) << "[coop-gift] synced guest craft assignments into own-world blob (" << filename << ")";
	}

	delete ownWorld;

}

// Last census actually put on the wire, so an unchanged tally costs nothing.
static std::string _lastGuestCensus;

/**
 * COOP living quarters: tell the peer how many of OUR soldiers are stationed at
 * each of THEIR bases.
 *
 * A soldier transferred to a peer base keeps living in this machine's roster
 * (TransferItemsState::completeTransfer deliberately skips the erase when the
 * destination is a co-op base) and tags itself with getCoopBase() = that base's
 * id. The peer therefore has no Soldier object for it at all - its syncTrade
 * drops the incoming TRANSFER_SOLDIER outright - so without this report the
 * guest occupies nobody's living quarters. Base::getUsedQuarters() subtracts
 * these guests here and adds the peer's census as coop_guests there, so the
 * base that HOUSES a soldier is the one that pays for it.
 */
void connectionTCP::sendGuestCensus(bool force)
{
	if (!getCoopStatic() || !getCoopCampaign() || !_game->getSavedGame())
		return;
	// SHARED has one world: a transfer really moves the soldier, and
	// getTotalSoldiers() already counts it at the destination while it is in
	// transit. Nothing to report.
	if (isSharedCampaign())
		return;

	std::map<int, int> guests; // peer base coop id -> headcount
	for (auto* base : *_game->getSavedGame()->getBases())
	{
		// only OUR real bases hold our soldiers; a visited peer base is a
		// swapped-in copy and would double-count them
		if (base->_coopBase || base->_coopIcon)
			continue;
		for (auto* soldier : *base->getSoldiers())
		{
			if (soldier->getCoopBase() != -1)
				guests[soldier->getCoopBase()]++;
		}
	}

	Json::Value root;
	root["state"] = "guest_census";
	Json::Value list(Json::arrayValue);
	for (const auto& entry : guests)
	{
		Json::Value e;
		e["base_id"] = entry.first;
		e["guests"] = entry.second;
		list.append(e);
	}
	root["bases"] = list;

	std::string payload = root.toStyledString();
	if (!force && payload == _lastGuestCensus)
		return;
	_lastGuestCensus = payload;
	sendTCPPacketData(payload);
}

void connectionTCP::resetGiftSessionState()
{

	_pendingSoldierGifts.clear();
	_pendingIncomingGifts.clear();
	clearGiftSelectedBattleUnit();
	_seenGiftPacketIds.clear();
	_giftedAwaySoldierIds.clear();

	// PRD-06 C5: a different world is being loaded - abort any armed deferred
	// host save so a late client blob cannot rewrite the (now stale) named save.
	if (!session.pendingHostSaveName.empty())
	{
		Log(LOG_INFO) << "[coop] world switch aborts armed deferred host save (" << session.pendingHostSaveName << ")";
		session.pendingHostSaveName.clear();
	}

}

void connectionTCP::writePendingHostSave()
{

	if (session.pendingHostSaveName.empty())
	{
		return;
	}

	// A battle started (or the save vanished) since the request: the live world
	// is no longer the one the save captured - disarm without writing.
	if (!_game->getSavedGame() || _game->getSavedGame()->getSavedBattle())
	{
		session.pendingHostSaveName.clear();
		return;
	}

	try
	{
		// same atomic dance as SaveGameState: backup, then rename
		std::string backup = session.pendingHostSaveName + ".bak";
		_game->getSavedGame()->save(backup, _game->getMod());
		CrossPlatform::moveFile(Options::getMasterUserFolder() + backup,
								Options::getMasterUserFolder() + session.pendingHostSaveName);
	}
	catch (const std::exception& e)
	{
		Log(LOG_ERROR) << "[coop] deferred host save write failed: " << e.what();
	}

	session.clearDeferredSave();

}

void connectionTCP::sendSoldierGiftPacket(Soldier* soldier, int newOwnerId)
{

	// Which base is the soldier stationed at? If it is already a guest at the
	// peer's base, keep that station; otherwise it is in one of our own bases
	// - find it and use that base's coop id.
	int stationBaseId = soldier->getCoopBase();

	if (stationBaseId == -1 && _game->getSavedGame())
	{

		for (auto& base : *_game->getSavedGame()->getBases())
		{

			auto containsSoldier = [soldier](const std::vector<Soldier*>& list)
			{
				return std::find(list.begin(), list.end(), soldier) != list.end();
			};

			// The live roster may be temporarily swapped out while a soldier
			// list screen is open - check the snapshots too.
			if (containsSoldier(*base->getSoldiers()) || containsSoldier(base->base_oldsoldiers) || containsSoldier(base->base_oldsoldiers2))
			{
				stationBaseId = base->_coop_base_id;
				break;
			}

		}

	}

	// Detach from any craft so the serialized soldier does not carry a craft
	// reference that would be resolved against the receiver's save.
	soldier->setCraft(0);

	YAML::YamlRootNodeWriter writer;
	writer.setAsMap();
	soldier->save(writer["soldier"], _game->getMod()->getScriptGlobal());

	// Durable unique id shared with the battle-time gift paths, so one
	// counter orders every gift this machine sends.
	long long xferId = nextGiftXferId();

	std::string yaml = writer.emit().yaml;

	Json::Value obj;
	obj["state"] = "giftSoldier";
	obj["soldier_id"] = soldier->getId();
	obj["owner"] = newOwnerId;
	obj["unit_id"] = -1;
	obj["station_base_id"] = stationBaseId;
	obj["xfer_id"] = Json::Value::Int64(xferId);
	obj["soldier_yaml"] = yaml;

	std::string packet = obj.toStyledString();

	Log(LOG_INFO) << "[coop-gift] SEND soldier '" << soldier->getName() << "' id=" << soldier->getId()
	              << " newOwner=" << newOwnerId << " stationBaseId=" << stationBaseId
	              << " packetBytes=" << packet.size();

	sendTCPPacketData(packet);

}

void connectionTCP::removeSoldierFromLocalBases(Soldier* soldier)
{

	if (!_game->getSavedGame())
	{
		return;
	}

	for (auto& base : *_game->getSavedGame()->getBases())
	{

		auto eraseFrom = [soldier](std::vector<Soldier*>& list)
		{
			list.erase(std::remove(list.begin(), list.end(), soldier), list.end());
		};

		eraseFrom(*base->getSoldiers());
		// SoldiersState/CraftSoldiersState swap the roster while open and
		// restore it from these snapshots afterwards - purge them too so the
		// soldier cannot resurrect on the giver's side.
		eraseFrom(base->base_oldsoldiers);
		eraseFrom(base->base_oldsoldiers2);

	}

}

void connectionTCP::clearAllReceivedTCPPackets()
{

	clearPackets = true;

}

void connectionTCP::createLoopdataThread()
{

	_loopThread = std::thread(&connectionTCP::loopData, this);

}

// an endless loop that processes the sync-packet data: battlescape, tasks, remove targets, research, trading, disconnect, errors.
void connectionTCP::updateCoopTask()
{

	// Voting deadlines are host-authoritative. The menu keeps its own display
	// countdown, but only this main-thread check may resolve a timed-out vote.
	if (getServerOwner() && _activeVote.active && _activeVote.timedOut())
	{
		finishVote(false);
	}

	// coop: finish queued in-battle soldier transfers as soon as no battle is
	// active (fallback for the client, which may not run the host's
	// coopMissionEnd path in GeoscapeState).
	processPendingSoldierGifts();

	// COOP living quarters: re-report our guest headcount whenever it changes.
	// Driven from here rather than from each mutation site (transfer, gift,
	// sack, base loss) so no path can forget it; sendGuestCensus is a cheap
	// tally and only touches the wire when the result actually differs.
	sendGuestCensus();

	if (connectionTCP::saveError == true)
	{

		connectionTCP::saveError = false;
		_game->pushState(new CoopState(995));

	}

	// R1-P4: the per-tick "run the Battlescape states in the background" pump
	// that used to live here called BattlescapeGame::handleStateCoop(), a coop
	// hook the r1 vanilla restore (911ca487f) stripped along with everything
	// else in src/Battlescape. RB-D5 rebuilds the real pump point (drained
	// inside this same updateCoopTask()) in r2 - nothing to stub here, the
	// call site is just gone until then.

	// time
	if (connectionTCP::getCoopStatic() == true && connectionTCP::getServerOwner() == false && connectionTCP::_enable_time_sync == true && _year != 0)
	{

		if (_game->getSavedGame())
		{

			GameTime new_time(connectionTCP::_weekday, connectionTCP::_day, connectionTCP::_month, connectionTCP::_year, connectionTCP::_hour, connectionTCP::_minute, connectionTCP::_second);

			_game->getSavedGame()->setTime(new_time);

			_game->getSavedGame()->setMonthsPassed(connectionTCP::monthsPassed);
			_game->getSavedGame()->setDaysPassed(connectionTCP::daysPassed);

		}

	}

	// coop
	// trade
	if (getCoopStatic() && !waitedTrades.empty())
	{
		Json::Value newWaitedTrades(Json::arrayValue);

		for (Json::Value::ArrayIndex i = 0; i < waitedTrades.size(); ++i)
		{

			Base* currentBase = nullptr;

			int base_id = waitedTrades[i]["base_to_id"].asInt();

			for (auto base : *_game->getSavedGame()->getBases())
			{
				// My bad, _coop_base_id should be used instead of the base name.
				if (base->_coop_base_id == base_id)
				{
					currentBase = base;
					break;
				}
			}

			if (currentBase)
			{
				current_base_name = currentBase->getName(_game->getLanguage());

				CoopState* window = new CoopState(150);
				_game->pushState(window);

				currentBase->syncTrade(waitedTrades[i].toStyledString().c_str(), _game->getSavedGame(), _game->getMod());

				// Clear or mark element as empty
				waitedTrades[i] = 0; // Set the element to null
			}

			// Check a condition for keeping items. In this example, keep non-empty elements.
			if (waitedTrades[i] != 0)
			{
				newWaitedTrades.append(waitedTrades[i]); // Add the item to be kept into the new array
			}
		}

		// Replace the original array with the new one, where unwanted elements have been removed
		waitedTrades = newWaitedTrades;
	}

	// PRD-J03: drain the SHARED economy protocol queues at the same controlled
	// main-thread point as waitedTrades (host validates+applies+broadcasts queued
	// shared_cmd; replicas apply queued shared_apply and surface shared_fail).
	SharedEcon::update(_game);

	// wrong password
	if (onConnect == -5)
	{

		// the attempt is over: retire "Connecting..." before reporting why
		closeConnectingDialog();

		// Make sure it calls disconnectTCP, otherwise it may get stuck.
		_game->pushState(new CoopState(441));
	}

	// coop
	// server error!
	if (onConnect == -3)
	{
		// Mid-session during a campaign: treat this as a client drop.
		// Push a freeze/WAIT_PLAYERS dialog so the host can wait for
		// reconnection (instead of code 440 which tears down the server).
		//
		// Two guards, mirrored from the canonical drop path in disconnectTCP:
		//   * Only the HOST freezes and waits. A client that hits -3 has no
		//     peer to wait for, so it keeps the plain 440 teardown (a client
		//     live-rejoin path is deliberately out of scope, F2).
		//   * Never once the campaign has ended: after defeat/victory there
		//     is nothing left to reconnect for, so suppress the freeze and
		//     fall through to teardown (matches the campaignEnded() gate at
		//     the disconnectTCP drop site).
		if (getServerOwner() == true
			&& connectionTCP::session.lobbyClosed
			&& connectionTCP::session.lobbyMode != 0
			&& !campaignEnded())
		{
			bool waitDialogPresent = false;
			for (State* st : _game->getStates())
			{
				CoopState* cs = dynamic_cast<CoopState*>(st);
				if (cs && cs->getStateCode() == COOP_DLG_WAIT_PLAYERS)
				{
					waitDialogPresent = true;
					break;
				}
			}
			if (!waitDialogPresent)
			{
				connectionTCP::session.freeze();
				_game->pushState(new CoopState(COOP_DLG_WAIT_PLAYERS));
			}
			// Don't let updateCoopTask re-fire this handler each cycle.
			// The TCP thread will set onConnect=1 when a peer reconnects.
			onConnect = 1;
			// Clear the stale player name so the rejoin roster gate
			// (nameInUse check) doesn't refuse the returning player.
			tcpPlayerName.clear();
		}
		else
		{
			// issue #79 (mirrored from disconnectTCP): a HOST drop once the
			// campaign has ended must NOT freeze/wait - there is nothing left
			// to reconnect for. Log the suppression, then tear down plainly.
			// A client hitting -3 skips straight past this to the teardown.
			if (getServerOwner() == true
				&& connectionTCP::session.lobbyClosed
				&& connectionTCP::session.lobbyMode != 0
				&& campaignEnded())
			{
				Log(LOG_INFO) << "[coop] freeze dialog suppressed: the campaign "
					"has ended; the peer has nothing left to reconnect for";
			}
			closeConnectingDialog();
			_game->pushState(new CoopState(440));
		}
	}

	// disconnect from server!
	if (onConnect == -2)
	{

		// issue #79: after the campaign has ended, a peer leaving is silent on
		// both sides - no "<player> has left the server", no "Server connection
		// lost". Either player may close a finished game first, and neither
		// exit is allowed to interrupt the other's end-of-game screens. The
		// plain teardown below still runs, so nothing is left half-attached.
		if (allow_cutscene == true && !campaignEnded())
		{
			// Make sure it calls disconnectTCP, otherwise it may get stuck.
			if (getServerOwner() == true)
			{
				// campaign flow: no "... has left the server" popup - the
				// waiting lobby / freeze dialog handles real drops and a
				// refused joiner warrants no notification at all (D5). The
				// disconnect still has to run (CoopState(20)'s constructor
				// used to do it); its cleanup pushes the freeze dialog.
				//
				// issue #93: a drop DURING A MISSION takes the campaign route
				// whatever the lobby mode. The freeze dialog is the whole
				// answer there - it names the missing player, freezes the
				// battle and carries SAVE & QUIT / ABANDON GAME - so a second,
				// dismissable "has left the server" popup on top of it would
				// only invite the host to click past the freeze. It also zeroes
				// _coopGamemode, which a rejoin into the same battle needs.
				if (connectionTCP::session.lobbyMode == 0 && !coopBattleLive(_game))
				{
					_game->pushState(new CoopState(20));
				}
				else
				{
					_game->getCoopMod()->disconnectTCP();
				}
			}
			else if (getServerOwner() == false)
			{
				_game->pushState(new CoopState(21));
			}
		}
		else
		{
			// disconnect
			connectionTCP::_coopGamemode = 0;
			_game->getCoopMod()->disconnectTCP();
		}

	}

	// coop
	// Pull everything currently available from the transport queue into the hold queue.
	// The hold queue is global so disconnect/reconnect cleanup can clear it completely.
	{
		std::lock_guard<std::mutex> lock(g_rxHoldMutex);
		std::string msg;
		while (g_rxQ.pop(msg))
		{
			g_rxHold.emplace_back(std::move(msg));
		}
	}

	for (;;)
	{
		size_t passCount = 0;
		{
			std::lock_guard<std::mutex> lock(g_rxHoldMutex);
			if (g_rxHold.empty())
				break;
			passCount = g_rxHold.size();
		}

		size_t consumedThisPass = 0;

		for (size_t i = 0; i < passCount; ++i)
		{
			std::string jsonStr;
			{
				std::lock_guard<std::mutex> lock(g_rxHoldMutex);
				if (g_rxHold.empty())
					break;
				jsonStr = std::move(g_rxHold.front());
				g_rxHold.pop_front();
			}

			try
			{

				Json::CharReaderBuilder rb;
				std::unique_ptr<Json::CharReader> reader(rb.newCharReader());

				Json::Value obj;
				std::string errs;

				const char* begin = jsonStr.data();
				const char* end = begin + jsonStr.size();

				if (!reader->parse(begin, end, &obj, &errs))
				{
					DebugLog(std::string("JSON parse error: ") + errs + "\n");
					continue; // drop malformed
				}

				const std::string stateString = obj.get("state", "defaultState").asString();
				const int fromId = obj.get("from", -1).asInt();

				// debug mode
				if (Options::logPacketMessages == true && Options::logInfoToFile == true)
				{			
					std::string str_debug =
						std::string("task completed: ") + (_coop_task_completed ? "true" : "false") +
						"   connection status: " + std::to_string(onConnect) + 
						"   packet name: " + stateString +
						"   packet data: " + obj.toStyledString();

					DebugLog(str_debug);
				}

				// R2-P1: battle-lane traffic is diverted before it can ever reach the
				// legacy allowlist/g_rxHold rotation logic below - "battle traffic
				// must never touch g_rxHold rotation" (inventory-wire-protocol.md
				// transport fact #4). isBattleKind() states are therefore always
				// consumeNow, straight into onTCPMessage's battle-lane branch (SS2.1).
				// Make operator precedence explicit:
				const bool consumeNow =
					CoopWire::isBattleKind(stateString) ||
					((_coop_task_completed || ((stateString == "abortPath" && _coopWalkInit) ||
						 (stateString == "unit_death" && _coopInitDeath) ||
						 (stateString == "after_unit_death" && _coopInitDeath)) ||
					 stateString == "vote_request" || stateString == "vote_start" || stateString == "vote_cast" || stateString == "vote_update" || stateString == "vote_result" || stateString == "vote_cooldown" || stateString == "custom_battle_craft_locked") &&
					// R1-P3 IR-8 prune: "close_event" and "minimap_data" removed from this
					// allowlist - dead ids with no sender/handler anywhere (inventory-wire-
					// protocol.md "Dead ids delete outright"). R2-P1 hygiene: click_close,
					// AIProgress, update_progress, DebriefingState, endTurn, hit_tile,
					// destroy_tile, set_fire_tile, set_smoke_tile, unit_fire,
					// calc_explode_fov, hasHitUnit removed here too - R1-P3 quarantined
					// every one of their senders+handlers, so these ids can never arrive.
					!(stateString == "endPlayerTurn" && (_coopEnd == 1 || (_game->getSavedGame() && !_game->getSavedGame()->getSavedBattle()))));

				if (consumeNow)
				{
					onTCPMessage(stateString, obj);
					++consumedThisPass;
				}
				else
				{
					// Rotate to the back so we can try the next message.
					{
						std::lock_guard<std::mutex> lock(g_rxHoldMutex);
						g_rxHold.emplace_back(std::move(jsonStr));
					}
				}
			}
			catch (const std::exception& e)
			{
				// Build a single message used for both DebugLog and crash log
				std::string msg = std::string("Network process exception: ") + e.what();

				// Existing debug log
				DebugLog((msg + "\n").c_str());

				// Write a crash-style log file into user/logs/crash_YYYY-MM-DD_HH-MM-SS.log
				CRASH_LOG(msg);

				// Put back to the *back* to avoid pinning the head.
				{
					std::lock_guard<std::mutex> lock(g_rxHoldMutex);
					g_rxHold.emplace_back(std::move(jsonStr));
				}
				onConnect = -3;
				break;
			}
		}

		// If nothing progressed this pass, stop to avoid busy-waiting
		if (consumedThisPass == 0)
			break;
	}

	// R2-P2 (RB-D5 pump point): drain the battle apply-queue in strict seq
	// order, right after the loop above that may have just enqueued this
	// tick's incoming bt_ev/bt_action_end. Appliers set flags only - see
	// CoopPump::drainApplyQueue()'s "R3-P1 applies payload here" marker.
	// R2-P3 phase gate (tightened, RB-D5/RB-D6): now also requires
	// BattleAuthority::phase to be Active or Ended, on top of the live-
	// SavedBattleGame check this marker used before BattleAuthority existed.
	// phase stays Idle until R4-P1's handshake sets it, so this makes the
	// drain inert until R4-P1 lands - correct, since there is no real battle
	// (and therefore nothing legitimate to drain) before the handshake.
	if (_game->getSavedGame() && _game->getSavedGame()->getSavedBattle() != nullptr
		&& (coopBattleAuthority().phase == CoopBattlePhase::Active
			|| coopBattleAuthority().phase == CoopBattlePhase::Ended))
	{
		CoopPump::drainApplyQueue();
	}

	// RW-REVEAL-SYNC (SS2.4a): the HOST's standalone quiescent reveal flush.
	// Self-guarded (host sim + phase Active + no open action context + quiescent
	// BState chain + something actually unpublished), so this stays a single
	// unconditional call at RB-D5's own pump point - the same tick that already
	// drains the client queue above. It is deliberately NOT inside the drain's
	// SavedBattleGame gate: the flush needs to run on the HOST while it is still
	// parked in BriefingState (battle generated, phase Active, no
	// BattlescapeState) too.
	CoopReveal::flushQuiescent();

	// TEST-ONLY STOPGAP (owner 2026-09-02): delete/replace with a real shot-based busy once the shot atom lands (r3 fan-out) - a slow auto-shot is the natural long chain.
	// R2-P7 hold_chain lever: the release half. Self-guarded (completely inert
	// with no hold armed), so this stays a single unconditional call at the
	// same RB-D5 pump point the reveal flush already uses - the only place
	// that reliably ticks on the HOST while a held chain's window runs down
	// (popState will not be entered again on its own).
	CoopArbiter::releaseHeldChainIfExpired();

	// coop
	// UNABLE TO CONNECT TO SERVER
	if (onConnect == 0)
	{
		onConnect = -1;

		// the attempt is over either way: never leave "Connecting..." up. A
		// join to a port nobody is listening on used to sit on it forever.
		closeConnectingDialog();

		// if client cancels the action
		if (cancel_connect == false)
		{
			_game->pushState(new CoopState(16));
		}

		cancel_connect = false;
	}


}

std::vector<std::string> splitVector(std::string s, std::string delimiter)
{
	size_t pos_start = 0, pos_end, delim_len = delimiter.length();
	std::string token;
	std::vector<std::string> res;

	while ((pos_end = s.find(delimiter, pos_start)) != std::string::npos)
	{
		token = s.substr(pos_start, pos_end - pos_start);
		pos_start = pos_end + delim_len;
		res.push_back(token);
	}

	res.push_back(s.substr(pos_start));
	return res;
}

std::vector<std::string> connectionTCP::splitVectorMod(std::string s, std::string delimiter)
{
	return splitVector(s, delimiter);
}

bool connectionTCP::hasRequiredMods(const std::string& mod_hash)
{
	// Local mods
	std::vector<std::string> local_mod_names = _game->getMod()->getCoopModList();

	// If server does not require mods, allow join
	if (mod_hash == "")
		return true;

	// Required mods from the host/server
	std::vector<std::string> required_mods =
		_game->getCoopMod()->splitVectorMod(mod_hash, ";");

	// Remove empty strings, because mod_hash may end with ";"
	required_mods.erase(
		std::remove(required_mods.begin(), required_mods.end(), ""),
		required_mods.end());

	local_mod_names.erase(
		std::remove(local_mod_names.begin(), local_mod_names.end(), ""),
		local_mod_names.end());

	// Check that mod count is the same
	if (local_mod_names.size() != required_mods.size())
		return false;

	// Check that every required mod exists locally
	for (const auto& mod : required_mods)
	{
		if (std::find(local_mod_names.begin(), local_mod_names.end(), mod) == local_mod_names.end())
			return false;
	}

	return true;
}

void connectionTCP::syncCoopInventory()
{

	// inventory
	for (int i = 0; i < _jsonInventory.size(); i++)
	{

		std::string inv_id = _jsonInventory[i]["inv_id"].asString();
		int inv_x = _jsonInventory[i]["inv_x"].asInt();
		int inv_y = _jsonInventory[i]["inv_y"].asInt();
		int unit_id = _jsonInventory[i]["unit_id"].asInt();
		int item_id = _jsonInventory[i]["item_id"].asInt();
		int move_cost = _jsonInventory[i]["move_cost"].asInt();
		int slot_x = _jsonInventory[i]["slot_x"].asInt();
		int slot_y = _jsonInventory[i]["slot_x"].asInt();

		int getHealQuantity = _jsonInventory[i]["getHealQuantity"].asInt();
		int getPainKillerQuantity = _jsonInventory[i]["getPainKillerQuantity"].asInt();
		int getStimulantQuantity = _jsonInventory[i]["getStimulantQuantity"].asInt();
		int getFuseTimer = _jsonInventory[i]["getFuseTimer"].asInt();
		int getXCOMProperty = _jsonInventory[i]["getXCOMProperty"].asBool();
		int isAmmo = _jsonInventory[i]["isAmmo"].asBool();
		int isWeaponWithAmmo = _jsonInventory[i]["isWeaponWithAmmo"].asBool();
		int isFuseEnabled = _jsonInventory[i]["isFuseEnabled"].asBool();
		int getAmmoQuantity = _jsonInventory[i]["getAmmoQuantity"].asInt();

		std::string item_name = _jsonInventory[i]["item_name"].asString();

		int tile_x = _jsonInventory[i]["tile_x"].asInt();
		int tile_y = _jsonInventory[i]["tile_y"].asInt();
		int tile_z = _jsonInventory[i]["tile_z"].asInt();

		// new!!!
		bool coopbase = _jsonInventory[i]["coopbase"].asBool();
		bool other_coop_inventory = _jsonInventory[i]["other_coop_inventory"].asBool();
		int coopbase_id = _jsonInventory[i]["coopbase_id"].asInt();
		int craft_id = _jsonInventory[i]["craft_id"].asInt();
		std::string craft_type = _jsonInventory[i]["craft_type"].asString();
		int slot_type_int = _jsonInventory[i]["slot_type"].asInt();
		std::string item_type = _jsonInventory[i]["item_type"].asString();
		int item_slot_type = _jsonInventory[i]["item_slot_type"].asInt();

		const auto& arr = _jsonInventory[i]["coopItems"];
		int coop_item_id = _jsonInventory[i]["coop_item_id"].asInt();
		const auto& ammosArr = _jsonInventory[i]["ammos"];
		bool tu = _jsonInventory[i]["tu"].asBool();

		int sel_item_id = _jsonInventory[i]["sel_item_id"].asInt();
		std::string sel_item_type = _jsonInventory[i]["sel_item_type"].asString();

		bool unload_weapon = _jsonInventory[i]["unload_weapon"].asBool();

		// battle
		if (coopInventory == true && _game->getSavedGame()->getSavedBattle()->getBattleState())
		{

			if (other_coop_inventory == true)
			{

				std::string ammos = "";

				if (!ammosArr.isNull())
				{

					ammos = ammosArr.toStyledString();
				}

				// R4-REWIRE: BattlescapeState::moveCoopInventory was removed by
				// the r1 vanilla restore (911ca487f); this queue's producer (an
				// onTCPMessage battle-inventory-move handler) was itself one of
				// the R1-P3 quarantined 68, so _jsonInventory can no longer be
				// populated - drop the (unreachable) queued entry instead of
				// applying it. Real inventory-move application lands with r3's
				// inventory_move atom.
				_jsonInventory[i] = {};
			}
		}
		// base
		else if (other_coop_inventory == false)
		{

			if (_game->getSavedGame()->getSavedBattle())
			{
				std::string coopItems = "";

				if (!arr.isNull())
				{
					coopItems = arr.toStyledString();
				}

				// R4-REWIRE: SavedBattleGame::moveBaseCoopInventory was removed
				// by the r1 vanilla restore; same dead-producer situation as the
				// battle branch above - leave the (unreachable) entry queued
				// rather than pretending to have applied it.
			}
		}
	}

	// added items
	for (int i = 0; i < jsonAddedCoopItems.size(); i++)
	{

		if (_game->getSavedGame())
		{

			int coopbase_id = jsonAddedCoopItems[i]["coopbase_id"].asInt();
			int craft_id = jsonAddedCoopItems[i]["craft_id"].asInt();
			std::string craft_type = jsonAddedCoopItems[i]["craft_type"].asString();

			Base* current_base = 0;
			Craft* current_craft = 0;

			for (auto& base : *_game->getSavedGame()->getBases())
			{

				if (base->_coop_base_id == coopbase_id)
				{
					current_base = base;

					for (auto& craft : *base->getCrafts())
					{

						if (craft->getId() == craft_id && craft->getRules()->getType() == craft_type)
						{
							current_craft = craft;
							break;
						}
					}

					break;
				}
			}

			if (current_base && current_craft)
			{

				auto& coopItems = current_craft->getCoopItems();

				int item_coop_id = jsonAddedCoopItems[i]["item_coop_id"].asInt();
				bool coopbase = jsonAddedCoopItems[i]["coopbase"].asInt();
				std::string item_type = jsonAddedCoopItems[i]["item_type"].asString();

				// exists?
				bool item_exists = false;
				for (const auto& ci : coopItems)
				{
					if (ci.id == item_coop_id &&
						ci.type == item_type &&
						ci.owner == !coopbase)
					{
						item_exists = true;
						break;
					}
				}

				if (!item_exists)
				{
					coopItems.push_back({item_coop_id, item_type, !coopbase});

					_jsonInventory[i] = {};
				}
			}
		}
	}


}

bool isNumber(const std::string& s)
{
	for (char c : s)
	{
		if (!std::isdigit(c))
			return false;
	}
	return !s.empty();
}

int getPortFromAddress(const std::string& address)
{
	// If the input is empty, return -1
	if (address.empty())
	{
		return -1;
	}

	// If the input is just a number, return it as a port
	if (isNumber(address))
	{
		return std::stoi(address);
	}

	// Split the input by ':'
	auto parts = splitVector(address, ":");
	if (parts.size() == 2 && isNumber(parts[1]))
	{
		// If the second part is a valid number, return it as a port
		return std::stoi(parts[1]);
	}

	// If no port is found or it's invalid, return -1
	return -1;
}

void resetCoopState(bool isHost)
{
	coopSession = false;
	isWaitMap = true;
	onceTime = false;
	sendFileClient = false;
	sendProgressSaveFileToHost = false;
	sendFileBase = false;
	sendFileHost = false;
	sendFileSave = false;

	mapData.clear();

	onTcpHost = isHost;
	connectionTCP::session.role = isHost ? CoopRole::Host : CoopRole::Client;
	onConnect = -1;
	connectionTCP::no_bases = false;
	connectionTCP::isCoopBaseLoading = false;
	connectionTCP::session.sessionLocked = false;
	connectionTCP::isPlayerReady = false;
	connectionTCP::isPlayersReady = false;
	connectionTCP::LobbyFileStatus = -1;
	connectionTCP::lobby_timer = -1;
	connectionTCP::forceCloseCoopStateMenu = false;
	connectionTCP::forceClosePasswordCheckMenu = false;

}

// SERVER SETUP


// ===== Constants =====
static constexpr uint32_t kMaxMsgLen = 4u * 1024u * 1024u; // Safety cap: 4 MB per message

// ===== TCP helpers =====

// Send all bytes reliably (loop until all data is written).
// Uses SDLNet_TCP_Send under the hood.
static inline bool sendAll(TCPsocket s, const char* data, int len)
{
	int sent = 0;
	while (sent < len)
	{
		int n = SDLNet_TCP_Send(s, data + sent, len - sent);
		if (n <= 0)
			return false;
		sent += n;
	}
	return true;
}

// Build BE32 length-prefixed frame into a single contiguous buffer.
static inline void appendFramed(std::string& out, const std::string& payload)
{
	uint32_t len = (uint32_t)payload.size();
	uint32_t be = SDL_SwapBE32(len);
	size_t old = out.size();
	out.resize(old + 4 + payload.size());
	std::memcpy(out.data() + old, &be, 4);
	std::memcpy(out.data() + old + 4, payload.data(), payload.size());
}

// ===== RTT measurement via PING/PONG =====

// Client: emit PING once per second
static uint64_t g_nextPingAt = 0;
static uint64_t g_rttAvgMs = 0;
static constexpr double kRttEWMA = 0.2;

static inline void clientMaybeSendPing()
{
	uint64_t t = now_ms();
	if (t >= g_nextPingAt)
	{
		g_nextPingAt = t + 1000;
		Json::Value ping;
		ping["type"] = "PING";
		ping["ts"] = Json::UInt64(t);
		sendJSONNoLock(ping); // goes through TX queue
	}
}

// Host: if incoming JSON is PING, enqueue PONG via the same TX queue; do not forward to game.
static inline bool maybeHandlePingOnHost(const Json::Value& obj)
{
	if (obj.isMember("type") && obj["type"].asString() == "PING")
	{
		Json::Value pong;
		pong["type"] = "PONG";
		pong["ts"] = obj["ts"];
		sendJSONNoLock(pong); // host -> single client via TX queue
		return true;          // handled internally
	}
	return false;
}

// Client: if incoming JSON is PONG, compute RTT and log, do not forward to game.
static inline bool maybeHandlePongOnClient(const Json::Value& obj)
{
	if (obj.isMember("type") && obj["type"].asString() == "PONG")
	{
		uint64_t sent = obj["ts"].asUInt64();
		uint64_t rtt = now_ms() - sent;

		current_ping = std::to_string((unsigned long long)rtt);

		return true; // handled internally
	}
	return false;
}

// Clears all received packets (client/host):
// - recvBuffer: partially received framed bytes
// - g_rxQ: already-parsed JSON messages waiting for the game thread
// - socket: any bytes already waiting in the TCP socket are read and dropped (non-blocking)
static inline void clearAllReceivedPackets(TCPsocket sock,
											SDLNet_SocketSet socketSet,
											std::vector<char>& recvBuffer)
{
	// Drop partially received framed bytes
	recvBuffer.clear();

	// Drop already parsed messages waiting for the game thread
	std::string drop;
	while (g_rxQ.pop(drop))
	{
		// intentionally empty
	}

	// Drop bytes already waiting in the TCP socket (non-blocking)
	if (sock && socketSet)
	{
		for (;;)
		{
			int ready = SDLNet_CheckSockets(socketSet, 0);
			if (ready <= 0 || !SDLNet_SocketReady(sock))
				break;

			char buf[16 * 1024];
			int bytes = SDLNet_TCP_Recv(sock, buf, sizeof(buf));
			if (bytes <= 0)
				break; // disconnected or error (caller handles disconnect)
		}
	}
}

// ===== Client thread =====
void connectionTCP::startTCPClient()
{

	SDL_Delay(1000);
	DebugLog("startTCPClient\n");
	resetCoopState(false); // client

#ifdef _WIN32
	SDL_Delay(100); // tiny stagger; avoid long sleeps
#endif

	if (SDLNet_Init() == -1)
	{
		DebugLog("SDLNet init failed\n");
		onConnect = -3;
		return;
	}

	IPaddress ip;
	if (SDLNet_ResolveHost(&ip, ipAddress.c_str(), tcp_port) == -1)
	{
		DebugLog("Can't resolve host\n");
		SDLNet_Quit();
		onConnect = 0;
		return;
	}

	TCPsocket sock = SDLNet_TCP_Open(&ip);
	if (!sock)
	{
		DebugLog("Can't connect to server\n");
		SDLNet_Quit();
		onConnect = 0;
		return;
	}

	SDLNet_SocketSet socketSet = SDLNet_AllocSocketSet(1);
	SDLNet_TCP_AddSocket(socketSet, sock);

	std::vector<char> recvBuffer;
	recvBuffer.reserve(4096);

	bool initSent = false; // one-time handshake
	onConnect = 1;

	for (;;)
	{

		if (clearPackets == true)
		{
			clearPackets = false;
			clearAllReceivedPackets(sock, socketSet, recvBuffer);
		}

		if (onConnect == -1)
			break;

		if (_clientStop)
			break;

		// ---- Batch-send: drain up to 64 queued payloads into one write ----
		{
			std::string out;
			out.reserve(8192);
			std::string msg;
			int batched = 0;
			while (batched < 64 && g_txQ.pop(msg))
			{
				appendFramed(out, msg);
				++batched;
			}
			// Conflated geoscape snapshots ride the same framed write as the
			// reliable batch (freshest value only, at link rate -> no backlog).
			drainSnapshotsInto(out);
			if (!out.empty())
			{
				if (!sendAll(sock, out.data(), (int)out.size()))
				{
					DebugLog("DISCONNECT CLIENT: SEND\n");
					clearAllReceivedPackets(sock, socketSet, recvBuffer);
					onConnect = -2;
					onceTime = false;
					break;
				}
			}
		}

		// ---- Receive: read all available data (no artificial delays) ----
		int ready = SDLNet_CheckSockets(socketSet, 0); // 0 ms timeout
		if (ready > 0 && SDLNet_SocketReady(sock))
		{
			for (;;)
			{
				char buf[16 * 1024];
				int bytes = SDLNet_TCP_Recv(sock, buf, sizeof(buf));
				if (bytes <= 0)
				{
					DebugLog("DISCONNECT CLIENT: RECV\n");
					clearAllReceivedPackets(sock, socketSet, recvBuffer);
					onConnect = -2;
					onceTime = false;
					goto client_cleanup;
				}
				recvBuffer.insert(recvBuffer.end(), buf, buf + bytes);
				if (bytes < (int)sizeof(buf))
					break; // nothing more immediately
			}

			// ---- Parse frames ----
			while (recvBuffer.size() >= 4)
			{

				uint32_t msgLenNet = 0;
				std::memcpy(&msgLenNet, recvBuffer.data(), 4);
				uint32_t msgLen = SDL_SwapBE32(msgLenNet);

				if (msgLen == 0 || msgLen > kMaxMsgLen)
				{
					DebugLog("Client: invalid message size, disconnecting\n");
					clearAllReceivedPackets(sock, socketSet, recvBuffer);
					onConnect = -3;
					onceTime = false;
					goto client_cleanup;
				}

				const size_t need = 4ull + static_cast<size_t>(msgLen);
				if (recvBuffer.size() < need)
					break;

				std::string message(
					reinterpret_cast<const char*>(recvBuffer.data() + 4),
					static_cast<size_t>(msgLen));

				recvBuffer.erase(recvBuffer.begin(), recvBuffer.begin() + need);

				if (!message.empty())
				{

					// Handle PING/PONG internally, push others to RX queue for the game thread
					Json::CharReaderBuilder rb;
					std::unique_ptr<Json::CharReader> reader(rb.newCharReader());

					Json::Value obj;
					std::string errs;

					const char* begin = message.data();
					const char* end = begin + message.size();

					if (reader->parse(begin, end, &obj, &errs))
					{
						if (maybeHandlePingOnClient(obj))
							continue;

						if (maybeHandlePongOnClient(obj))
							continue;
					}
					else
					{
						DebugLog(std::string("JSON parse failed: ") + errs + "\n");
						continue; // drop invalid JSON
					}

					if (!g_rxQ.push(std::move(message)))
					{
						DebugLog("RX queue full, dropping message\n");
					}

				}
			}
		}

		// ---- One-time handshake ----
		if (!initSent)
		{
			initSent = true;
			Json::Value hello;
			hello["state"] = "INIT_SERVER";
			hello["playername"] = sendTcpPlayer;
			hello["servername"] = sendTcpServerName;
			hello["tcp_password"] = connectionTCP::password;

			sendJSONNoLock(hello);
		}

		// ---- Client RTT ping ----
		clientMaybeSendPing();

		// ---- Gentle yield only if nothing happened ----
		if (ready == 0 && g_txQ.empty() && !anySnapshotDirty())
		{
#ifdef _WIN32
			SDL_Delay(0);
#endif
		}
	}

client_cleanup:
	SDLNet_FreeSocketSet(socketSet);
	SDLNet_TCP_Close(sock);
	SDLNet_Quit();
	return;
}

// ===== Host thread (single client) =====
// Simplified for exactly two players: host + one client.
// If another client tries to connect, close it silently (no "server_full" message),
// because we only use sendTCPPacketStaticData for outbound traffic.
void connectionTCP::startTCPHost()
{
	DebugLog("startTCPHost\n");
	resetCoopState(true); // host

	if (SDLNet_Init() == -1)
	{
		onConnect = -3;
		DebugLog("SDLNet init failed\n");
		return;
	}

	IPaddress ip;
	if (SDLNet_ResolveHost(&ip, nullptr, tcp_port) == -1)
	{
		DebugLog("Can't resolve host\n");
		SDLNet_Quit();
		onConnect = -3;
		return;
	}

	TCPsocket listening = SDLNet_TCP_Open(&ip);
	if (!listening)
	{
		DebugLog("Can't open TCP socket\n");
		SDLNet_Quit();
		onConnect = -3;
		return;
	}

	SDLNet_SocketSet socketSet = SDLNet_AllocSocketSet(2);
	SDLNet_TCP_AddSocket(socketSet, listening);

	TCPsocket clientSock = nullptr;
	std::vector<char> recvBuffer;
	recvBuffer.reserve(4096);

	onConnect = 1;
	// thread-side role mirror (pre-struct behavior kept; the main-thread
	// hosting path also sets this via setServerOwner)
	session.role = CoopRole::Host;

	for (;;)
	{

		if (clearPackets == true)
		{
			clearPackets = false;
			clearAllReceivedPackets(clientSock, socketSet, recvBuffer);
		}

		if (onConnect == -1)
		{
			clearAllReceivedPackets(clientSock, socketSet, recvBuffer);
			break;
		}
	

		if (_hostStop)
		{
			clearAllReceivedPackets(clientSock, socketSet, recvBuffer);
			break;
		}

		// ---- Accept new client if we don't have one ----
		if (TCPsocket newClient = SDLNet_TCP_Accept(listening))
		{
			if (!clientSock)
			{
				clientSock = newClient;
				SDLNet_TCP_AddSocket(socketSet, clientSock);
				DebugLog("Host: client connected\n");
				onConnect = 1;
			}
			else
			{
				// Only 1 client supported -> close extra connection silently
				SDLNet_TCP_Close(newClient);
			}
		}

		// ---- Batch-send outbound messages to the single client ----
		if (clientSock)
		{
			std::string out;
			out.reserve(8192);
			std::string msg;
			int batched = 0;
			while (batched < 64 && g_txQ.pop(msg))
			{
				appendFramed(out, msg);
				++batched;
			}
			// Conflated geoscape snapshots ride the same framed write as the
			// reliable batch (freshest value only, at link rate -> no backlog).
			drainSnapshotsInto(out);
			if (!out.empty())
			{
				if (!sendAll(clientSock, out.data(), (int)out.size()))
				{
					DebugLog("Host: send failed, drop client\n");
					onConnect = -3;
					SDLNet_TCP_DelSocket(socketSet, clientSock);
					SDLNet_TCP_Close(clientSock);
					clientSock = nullptr;
					recvBuffer.clear();
				}
			}
		}

		// ---- Receive from client (drain all available bytes) ----
		int ready = SDLNet_CheckSockets(socketSet, 0); // 0 ms timeout
		if (ready > 0 && clientSock && SDLNet_SocketReady(clientSock))
		{
			for (;;)
			{
				char buf[16 * 1024];
				int bytes = SDLNet_TCP_Recv(clientSock, buf, sizeof(buf));
				if (bytes <= 0)
				{
					DebugLog("Host: client disconnected\n");
					onConnect = -2;
					SDLNet_TCP_DelSocket(socketSet, clientSock);
					SDLNet_TCP_Close(clientSock);
					clientSock = nullptr;
					recvBuffer.clear();
					break;
				}
				recvBuffer.insert(recvBuffer.end(), buf, buf + bytes);
				if (bytes < (int)sizeof(buf))
					break;
			}

			// Parse frames
			while (clientSock && recvBuffer.size() >= 4)
			{
				uint32_t msgLenNet = 0;
				std::memcpy(&msgLenNet, recvBuffer.data(), 4);
				uint32_t msgLen = SDL_SwapBE32(msgLenNet);

				if (msgLen == 0 || msgLen > kMaxMsgLen)
				{
					DebugLog("Host: invalid message size, drop client\n");
					onConnect = -3;
					SDLNet_TCP_DelSocket(socketSet, clientSock);
					SDLNet_TCP_Close(clientSock);
					clientSock = nullptr;
					recvBuffer.clear();
					break;
				}

				const size_t need = 4ull + static_cast<size_t>(msgLen);
				if (recvBuffer.size() < need)
					break;

				std::string message(
					reinterpret_cast<const char*>(recvBuffer.data() + 4),
					static_cast<size_t>(msgLen));

				recvBuffer.erase(recvBuffer.begin(), recvBuffer.begin() + need);

				if (!message.empty())
				{
					Json::CharReaderBuilder rb;
					std::unique_ptr<Json::CharReader> reader(rb.newCharReader());

					Json::Value obj;
					std::string errs;

					const char* begin = message.data();
					const char* end = begin + message.size();

					if (reader->parse(begin, end, &obj, &errs))
					{
						if (maybeHandlePingOnHost(obj))
							continue;

						if (maybeHandlePongOnHost(obj))
							continue;
					}
					else
					{
						DebugLog(std::string("Host: JSON parse failed: ") + errs + "\n");
						continue; // drop invalid JSON
					}

					if (!g_rxQ.push(std::move(message)))
						DebugLog("RX queue full, dropping message\n");
				}
			}
		}

		if (clientSock)
			hostMaybeSendPing();

		// ---- Gentle yield if nothing to do ----
		if (ready == 0 && OpenXcom::g_txQ.empty() && !OpenXcom::anySnapshotDirty())
		{
#ifdef _WIN32
			SDL_Delay(0);
#endif
		}
	}

	// ---- Cleanup ----
	if (clientSock)
	{
		SDLNet_TCP_DelSocket(socketSet, clientSock);
		SDLNet_TCP_Close(clientSock);
	}
	SDLNet_TCP_DelSocket(socketSet, listening);
	SDLNet_TCP_Close(listening);
	SDLNet_FreeSocketSet(socketSet);
	SDLNet_Quit();

	// thread-side role clear on host-thread exit (pre-struct behavior kept)
	session.role = CoopRole::None;
	onConnect = -1;
	return;
}

/**
 * Push a state while keeping an already-open "player joined" popup on top.
 *
 * The join handshake pushes Profile when the peer is announced, but the lobby
 * arrives in a LATER packet (initProfile, below), so a plain pushState buried
 * the popup under the lobby on the client - the host, whose lobby is already
 * open when the peer joins, showed it correctly. The popup is the newest thing
 * that happened, so it stays on top and the lobby renders behind it.
 */
/**
 * Retire the "Connecting..." wait dialog (CoopState 15).
 *
 * Every connect attempt ends here, success or failure, so the dialog can never
 * be left lurking under what comes next. It used to be popped only on one
 * client success path: a refused or failed join stacked its error popup ON TOP
 * of it, and dismissing that error resurfaced a dead "Connecting..." window;
 * a join that simply never completed left it up forever.
 *
 * A password join buries [Connecting, PasswordCheckMenu, Connecting] (JOIN
 * pushes a second wait dialog), so the stale password menu is popped too, not
 * just a run of Connecting dialogs (issue #46).
 */
void connectionTCP::closeConnectingDialog()
{
	while (!_game->getStates().empty())
	{
		State* top = _game->getStates().back();
		CoopState* connecting = dynamic_cast<CoopState*>(top);
		if ((connecting && connecting->getStateCode() == 15)
			|| dynamic_cast<PasswordCheckMenu*>(top) != nullptr)
		{
			_game->popState();
		}
		else
		{
			break;
		}
	}
}

void connectionTCP::pushKeepingProfileOnTop(State* state)
{
	const bool profileOnTop = !_game->getStates().empty()
		&& dynamic_cast<Profile*>(_game->getStates().back()) != nullptr;

	if (profileOnTop)
	{
		_game->popState();               // lift the popup off
		_game->pushState(state);         // the lobby lands underneath it
		_game->pushState(new Profile);   // and the popup goes back on top
	}
	else
	{
		_game->pushState(state);
	}
}

void connectionTCP::initProfile(bool clientInBattle, bool inBattle)
{
	// campaign flow: sessions are lobby-gated up front - no post-join lobby
	// re-entry (F2/F3). Only the legacy new-battle path reopens it here.
	//
	// issue #93: never over a battle. A skirmish REJOIN finishes this handshake
	// with the streamed battle already loaded and the player held until the host
	// resumes; dropping the lobby on top of that hands them the very menu whose
	// RESUME GAME used to throw the battle away.
	if (_game->getCoopMod()->getServerOwner() == false
		&& connectionTCP::session.lobbyMode == 0
		&& !coopBattleLive(_game))
	{
		pushKeepingProfileOnTop(new LobbyMenu);
	}

	if (_game->getCoopMod()->getCoopStatic() == true)
	{

		// if the client is in battle and the host is not, send the host a file and a notification
		if (clientInBattle == true && inBattle == false)
		{

			// client only!
			if (_game->getCoopMod()->getHost() == false)
			{

				connectionTCP::LobbyFileStatus = 1;
			}
		}
		// CHECK IF THE HOST IS IN BATTLE � IF SO, ADD JOINERS; OTHERWISE DO NOTHING
		else if (inBattle == true)
		{

			// only client!
			if (_game->getCoopMod()->getHost() == false)
			{

				connectionTCP::LobbyFileStatus = 2;
			}
		}
	}
}

long long connectionTCP::getDateTimeCoop() const
{
	time_t now = time(0);
	tm* timeInfo = localtime(&now);

	return (timeInfo->tm_year + 1900) * 10000000000LL +
		   (timeInfo->tm_mon + 1) * 100000000LL +
		   timeInfo->tm_mday * 1000000LL +
		   timeInfo->tm_hour * 10000LL +
		   timeInfo->tm_min * 100LL +
		   timeInfo->tm_sec;
}

// TCP
VoteMenu* connectionTCP::findVoteMenu(std::uint64_t voteId) const
{
	if (!_game)
	{
		return nullptr;
	}

	for (auto it = _game->getStates().rbegin(); it != _game->getStates().rend(); ++it)
	{
		VoteMenu* menu = dynamic_cast<VoteMenu*>(*it);
		if (menu && menu->getVoteId() == voteId)
		{
			return menu;
		}
	}
	return nullptr;
}

void connectionTCP::openVoteMenu()
{
	if (!_activeVote.id || findVoteMenu(_activeVote.id))
	{
		return;
	}

	_game->pushState(new VoteMenu(
		_activeVote.id,
		_activeVote.title,
		_activeVote.question,
		_activeVote.totalPlayers,
		_activeVote.requiredYesVotes,
		_activeVote.playerNames,
		_activeVote.remainingMilliseconds()));
}

std::vector<std::string> connectionTCP::buildVotePlayerNames(int totalPlayers) const
{
	// The host freezes the roster at vote start and sends the same ordered list
	// to every client. This is more reliable than asking each VoteMenu to read
	// its current SavedGame: battle/save streaming can temporarily replace that
	// object, and older saves may not yet carry the locked co-op roster.
	std::vector<std::string> names(
		static_cast<std::size_t>(std::max(1, totalPlayers)));

	if (_game && _game->getSavedGame())
	{
		const auto& roster = _game->getSavedGame()->getCoopPlayers();
		const std::size_t count = std::min(names.size(), roster.size());
		for (std::size_t i = 0; i < count; ++i)
		{
			names[i] = roster[i];
		}
	}

	// The lobby connection knows the two live names even before a new campaign
	// has written SavedGame::_coopPlayers. Keep these fallbacks so a vote opened
	// from the lobby also shows identities instead of PLAYER 1 / PLAYER 2.
	if (_game && !names.empty() && names[0].empty())
	{
		names[0] = _game->getCoopMod()->getHostName();
	}
	if (_game && names.size() > 1 && names[1].empty())
	{
		names[1] = _game->getCoopMod()->getCurrentClientName();
	}

	// A generic label remains only as a last-resort diagnostic for a missing
	// roster entry. Normal hosted/resumed campaigns always take the real name
	// from the locked roster above.
	for (std::size_t i = 0; i < names.size(); ++i)
	{
		if (names[i].empty())
		{
			names[i] = "PLAYER " + std::to_string(i + 1);
		}
	}

	return names;
}

void connectionTCP::updateVoteMenu()
{
	VoteMenu* menu = findVoteMenu(_activeVote.id);
	if (!menu)
	{
		return;
	}

	menu->setVotes(_activeVote.votes);
	if (_activeVote.active)
	{
		menu->setRemainingMilliseconds(_activeVote.remainingMilliseconds());
	}
	if (_activeVote.finished)
	{
		menu->finishVote(_activeVote.passed);
	}
}

bool connectionTCP::lockCustomBattleCraft(std::size_t craftId)
{
	if (!getServerOwner() || !getCoopStatic()
		|| connectionTCP::session.lobbyMode != 0)
	{
		return false;
	}

	if (connectionTCP::session.customBattleCraftLocked)
	{
		return connectionTCP::session.customBattleCraftId == static_cast<int>(craftId);
	}

	connectionTCP::session.lockCustomBattleCraft(static_cast<int>(craftId));
	_coop_selected_craft_id = craftId;

	Json::Value root;
	root["state"] = "custom_battle_craft_locked";
	root["selected_craft_id"] = Json::UInt(static_cast<Json::UInt>(craftId));
	sendTCPPacketData(root.toStyledString());
	return true;
}

std::uint32_t connectionTCP::voteStarterCooldownRemainingMs(
	int seat, std::uint32_t nowTicks) const
{
	if (seat < 0 || static_cast<std::size_t>(seat) >= _voteStarterCooldownUntil.size())
	{
		return 0;
	}

	// Signed subtraction is wrap-safe because the deadline is only 60 seconds
	// ahead, far below half of SDL_GetTicks()' 32-bit range.
	const std::int32_t remaining = static_cast<std::int32_t>(
		_voteStarterCooldownUntil[static_cast<std::size_t>(seat)] - nowTicks);
	return remaining > 0 ? static_cast<std::uint32_t>(remaining) : 0;
}

void connectionTCP::beginVoteStarterCooldown(int seat)
{
	if (seat < 0)
	{
		return;
	}

	if (_voteStarterCooldownUntil.size() <= static_cast<std::size_t>(seat))
	{
		_voteStarterCooldownUntil.resize(static_cast<std::size_t>(seat) + 1, 0);
	}
	_voteStarterCooldownUntil[static_cast<std::size_t>(seat)] =
		SDL_GetTicks() + VOTE_START_COOLDOWN_MS;
}

void connectionTCP::showVoteCooldownDialog(std::uint32_t remainingMs)
{
	if (!_game)
	{
		return;
	}

	// Do not stack the same warning when the user presses the shortcut more than
	// once before dismissing the first dialog.
	for (State* state : _game->getStates())
	{
		CoopState* coopState = dynamic_cast<CoopState*>(state);
		if (coopState && coopState->getStateCode() == COOP_DLG_VOTE_COOLDOWN)
		{
			return;
		}
	}

	const int seconds = std::max(1, static_cast<int>((remainingMs + 999u) / 1000u));
	_game->pushState(new CoopState(COOP_DLG_VOTE_COOLDOWN, seconds));
}

void connectionTCP::sendVoteCooldown(int seat, std::uint32_t remainingMs)
{
	Json::Value root;
	root["state"] = "vote_cooldown";
	root["to"] = seat;
	root["remaining_ms"] = Json::UInt(remainingMs);
	sendTCPPacketData(root.toStyledString());
}

bool connectionTCP::forceActiveVoteTimeoutForTest()
{
	if (!getServerOwner() || !_activeVote.active || _activeVote.finished)
	{
		return false;
	}

	// Set the real production session deadline to now, then let the normal host
	// evaluator send vote_result and update both menus.
	_activeVote.deadlineTicks = SDL_GetTicks();
	evaluateVote();
	return _activeVote.finished && !_activeVote.passed;
}

bool connectionTCP::requestVote(
	const std::string& action,
	const std::string& title,
	const std::string& question)
{
	if (!getCoopStatic() || action.empty() || question.empty())
	{
		return false;
	}

	// Repeated abort-key presses must not create overlapping votes. If the vote
	// is already known locally, make sure its menu is visible instead.
	if (_activeVote.active)
	{
		openVoteMenu();
		updateVoteMenu();
		return true;
	}
	if (_activeVote.finished)
	{
		if (findVoteMenu(_activeVote.id))
		{
			updateVoteMenu();
			return true;
		}
		_activeVote.clear();
	}
	if (_voteRequestPending)
	{
		return true;
	}

	const int starter = localSeat();
	if (getServerOwner())
	{
		return beginVoteAsHost(action, title, question, starter);
	}
	else
	{
		_voteRequestPending = true;

		Json::Value root;
		root["state"] = "vote_request";
		root["action"] = action;
		root["title"] = title;
		root["question"] = question;
		root["from"] = starter;
		sendTCPPacketData(root.toStyledString());
	}
	return true;
}

bool connectionTCP::castVote(std::uint64_t voteId, bool yes)
{
	if (!_activeVote.active || _activeVote.finished || _activeVote.id != voteId)
	{
		return false;
	}

	const int seat = localSeat();
	if (seat < 0 || seat >= _activeVote.totalPlayers
		|| _activeVote.votes[static_cast<std::size_t>(seat)] != VoteSession::NOT_VOTED)
	{
		return false;
	}

	if (getServerOwner())
	{
		acceptVote(seat, yes);
	}
	else
	{
		Json::Value root;
		root["state"] = "vote_cast";
		root["vote_id"] = Json::UInt64(voteId);
		root["from"] = seat;
		root["yes"] = yes;
		sendTCPPacketData(root.toStyledString());
	}
	return true;
}

bool connectionTCP::beginVoteAsHost(
	const std::string& action,
	const std::string& title,
	const std::string& question,
	int starterSeat)
{
	if (!getServerOwner() || _activeVote.active)
	{
		return false;
	}

	const int players = std::max(2, std::min(4, seatCount()));
	if (action.empty() || question.empty() || starterSeat < 0 || starterSeat >= players)
	{
		return false;
	}

	const std::uint32_t cooldownMs = voteStarterCooldownRemainingMs(starterSeat);
	if (cooldownMs > 0)
	{
		// The host enforces the cooldown for every seat. A local host gets the
		// dialog directly; a client receives a targeted rejection packet.
		if (starterSeat == localSeat())
		{
			showVoteCooldownDialog(cooldownMs);
		}
		else
		{
			sendVoteCooldown(starterSeat, cooldownMs);
		}
		return false;
	}

	// The low bits make two votes started in the same second distinct.
	const std::uint64_t now = static_cast<std::uint64_t>(getDateTimeCoop());
	const std::uint64_t voteId = (now << 12) ^ (++_voteSequence & 0xFFFu);

	// Only the host creates VoteSession. The seat names are snapshotted here and
	// then travel with vote_start, while all later packets only need the vote id
	// and seat-indexed choices.
	_activeVote.start(
		voteId, action, title, question, players,
		buildVotePlayerNames(players), starterSeat);
	// Cooldown starts when the host accepts the request, not when the vote ends.
	// The vote may remain open for 30 seconds, while the same starter must wait
	// a full 60 seconds from acceptance before starting another vote.
	beginVoteStarterCooldown(starterSeat);
	_voteRequestPending = false;

	openVoteMenu();
	updateVoteMenu();
	broadcastVoteStart();
	broadcastVoteUpdate();
	evaluateVote();
	return true;
}

void connectionTCP::acceptVote(int seat, bool yes)
{
	if (!getServerOwner())
	{
		return;
	}

	// A packet that arrives after the 30-second deadline cannot revive the vote.
	if (_activeVote.timedOut())
	{
		finishVote(false);
		return;
	}

	if (!_activeVote.castVote(seat, yes))
	{
		return;
	}

	updateVoteMenu();
	broadcastVoteUpdate();
	evaluateVote();
}

void connectionTCP::broadcastVoteStart()
{
	if (!getServerOwner() || !_activeVote.active)
	{
		return;
	}

	Json::Value root;
	root["state"] = "vote_start";
	root["vote_id"] = Json::UInt64(_activeVote.id);
	root["action"] = _activeVote.action;
	root["title"] = _activeVote.title;
	root["question"] = _activeVote.question;
	root["total_players"] = _activeVote.totalPlayers;
	root["required_yes"] = _activeVote.requiredYesVotes;
	root["starter_seat"] = _activeVote.starterSeat;
	root["remaining_ms"] = Json::UInt(_activeVote.remainingMilliseconds());
	root["player_names"] = Json::arrayValue;
	for (const std::string& name : _activeVote.playerNames)
	{
		root["player_names"].append(name);
	}
	sendTCPPacketData(root.toStyledString());
}

void connectionTCP::broadcastVoteUpdate()
{
	if (!getServerOwner() || (!_activeVote.active && !_activeVote.finished))
	{
		return;
	}

	Json::Value root;
	root["state"] = "vote_update";
	root["vote_id"] = Json::UInt64(_activeVote.id);
	root["yes_votes"] = _activeVote.yesVotes();
	root["no_votes"] = _activeVote.noVotes();
	root["remaining_ms"] = Json::UInt(_activeVote.remainingMilliseconds());
	root["votes"] = Json::arrayValue;
	for (int vote : _activeVote.votes)
	{
		root["votes"].append(vote);
	}
	sendTCPPacketData(root.toStyledString());
}

void connectionTCP::readVoteSnapshot(const Json::Value& obj)
{
	if (!obj.isMember("votes") || !obj["votes"].isArray())
	{
		return;
	}

	std::vector<int> snapshot(
		static_cast<std::size_t>(_activeVote.totalPlayers),
		VoteSession::NOT_VOTED);
	const Json::Value& arr = obj["votes"];
	const int count = std::min(
		_activeVote.totalPlayers,
		static_cast<int>(arr.size()));
	for (int i = 0; i < count; ++i)
	{
		const int value = arr[static_cast<Json::ArrayIndex>(i)].asInt();
		if (value == VoteSession::VOTED_YES || value == VoteSession::VOTED_NO)
		{
			snapshot[static_cast<std::size_t>(i)] = value;
		}
	}
	_activeVote.votes.swap(snapshot);
}

void connectionTCP::evaluateVote()
{
	if (!getServerOwner() || !_activeVote.active)
	{
		return;
	}

	if (_activeVote.timedOut())
	{
		finishVote(false);
		return;
	}

	const VoteDecision result = _activeVote.decision();
	if (result == VoteDecision::Passed)
	{
		finishVote(true);
	}
	else if (result == VoteDecision::Failed)
	{
		finishVote(false);
	}
}

void connectionTCP::finishVote(bool passed)
{
	if (!_activeVote.active || _activeVote.finished)
	{
		return;
	}

	const std::string action = _activeVote.action;
	_activeVote.finish(passed);
	updateVoteMenu();

	Json::Value root;
	root["state"] = "vote_result";
	root["vote_id"] = Json::UInt64(_activeVote.id);
	root["passed"] = passed;
	root["action"] = action;
	root["votes"] = Json::arrayValue;
	for (int vote : _activeVote.votes)
	{
		root["votes"].append(vote);
	}
	sendTCPPacketData(root.toStyledString());

	if (passed)
	{
		executeVoteAction(action);
	}
}

void connectionTCP::executeVoteAction(const std::string& action)
{
	if (action != "abandon_mission" || !_game)
	{
		return;
	}

	for (auto it = _game->getStates().rbegin(); it != _game->getStates().rend(); ++it)
	{
		BattlescapeState* battlescape = dynamic_cast<BattlescapeState*>(*it);
		if (battlescape)
		{
			// R4-REWIRE: BattlescapeState::abortMissionByVote (donor cbff7951d)
			// is battle-sim logic (cancels the active BState chain, tallies
			// units, calls the private finishBattle) that the r1 vanilla
			// restore (911ca487f, which predates it) does not have and this
			// packet is not authorized to re-add. The vote itself still runs
			// and broadcasts; only the local battle-abort application is
			// pending until r4/r5 rebuild the abort path on the new turn-machine.
			Log(LOG_INFO) << "[coop-vote] abandon_mission vote passed but the battle abort hook is rewrite-pending";
			return;
		}
	}
}

namespace
{
	// R1-P3 quarantine (inventory-wire-protocol.md sections A-E, ADDENDUM MN-6: 68
	// named battle-sim wire messages). Their onTCPMessage handlers are deleted
	// below because they reference symbols the vanilla 911ca487f restore
	// killed. Anything that still arrives with one of these `state` values -
	// a stale peer build, or a not-yet-rewired CoopMod-side sender (see the
	// // R4-REWIRE markers at giftBattleUnit/resume_ack/sendMissionFile/
	// streamSkirmishBattleToClient) - is dropped here instead of silently
	// falling through the if-chain unmatched.
	const std::unordered_set<std::string>& legacyBattleMessageIds()
	{
		static const std::unordered_set<std::string> ids = {
			// SS2.A action-intent (peer->peer input mirror), 22 named
			"BattleScapeMove", "abortPath", "cancelCurrentAction", "turnBattlescapeUnit",
			"afterBattlescapeUnitTurn", "ProjectileFlyBState", "psi_attack", "psi_press",
			"melee_attack", "medkit", "action_click", "unit_action", "active_grenade",
			"checkForProximityGrenades", "kneel", "kneel_reserved", "TU_COOP",
			"selected_unit", "motion_scan", "change_unit_name", "Inventory", "giveUnit",
			// SS2.B consequence/state patch (authority->peer), 14 named
			"hit_unit", "hit_tile", "hasHitUnit", "calc_explode_fov", "explode_items",
			"unit_death", "after_unit_death", "selfDestruct", "convertUnit", "unit_fire",
			"set_fire_tile", "set_smoke_tile", "destroy_tile", "psi_result",
			// SS2.C turn/flow control, 12 named
			"next_turn", "PlayerTurnYour", "endTurn", "endPlayerTurn", "click_close",
			"AIProgress", "update_progress", "info_box", "info_box_ok", "GamePausedON",
			"GamePausedOFF", "DebriefingState",
			// SS2.D bootstrap/host-token handoff/battle-save restream, 16 named
			"WAIT_BATTLESCAPE_HOST_TRUE", "WAIT_BATTLESCAPE_CLIENT_TRUE", "changeHost",
			"changeHost3", "changeHost4", "craftSoldiers", "SEND_FILE_HOST_TRUE",
			"SEND_FILE_HOST", "SEND_FILE_CLIENT_TRUE", "SEND_FILE_CLIENT",
			"SEND_FILE_CLIENT_SAVE", "SEND_FILE_HOST_SAVE", "SEND_FILE_CLIENT_SAVE_TRUE",
			"MAP_RESULT_HOST", "MAP_RESULT_CLIENT", "setup_battle",
			// SS2.E boundary, 4 named
			"campaign_resume_battle", "add_coop_item", "request_coop_items",
			"save_coop_items",
		};
		return ids;
	}
}

/**
 * R1-P3 quarantine catch-all. Returns true (and drops/logs the message) if
 * `state` names one of the battle-sim wire messages deleted by the vanilla
 * restore (inventory-wire-protocol.md sections A-E). Logs once per distinct state
 * string so a stale or looping sender cannot flood the log.
 */
bool connectionTCP::legacyBattleMessageDropped(const std::string& state)
{
	if (legacyBattleMessageIds().find(state) == legacyBattleMessageIds().end())
	{
		return false;
	}

	static std::unordered_set<std::string> alreadyLogged;
	if (alreadyLogged.insert(state).second)
	{
		Log(LOG_WARNING) << "[coop] legacyBattleMessageDropped: \"" << state
			<< "\" is a quarantined battle-sim message (R1-P3) - dropping.";
	}
	return true;
}

void connectionTCP::onTCPMessage(std::string stateString, Json::Value obj)
{

	// PRD-J03: single early hook routing the shared_* economy protocol into the
	// SharedEcon dispatch table (the anti-if-chain requirement). If SharedEcon
	// consumes the message, it never falls through to the if-chain below.
	if (SharedEcon::onMessage(_game, stateString, obj))
		return;

	// R2-P1 (SPIKE-RUNBOOK.md SS2.1): battle-lane routing. Battle kinds are
	// diverted HERE, at the top of onTCPMessage - before the R1-P3 legacy
	// quarantine catch-all just below and before the legacy vanilla if-chain -
	// so a battle-lane message can never be mistaken for a quarantined legacy
	// id nor fall into vanilla dispatch. (updateCoopTask() also keeps these
	// states out of the g_rxHold hold/rotate logic entirely, so this is the
	// first and only place a battle message is examined.) No consumers yet:
	// R2-P2 wires the seq-ordered apply queue, R2-P5/P6/P9 wire the direct
	// battle-lane handlers (admission, handshake, desync report). Still runs
	// on the pump thread (updateCoopTask), never the socket thread.
	if (CoopWire::isBattleKind(stateString))
	{
		if (CoopWire::isSeqOrdered(stateString))
		{
			// R2-P2 (RB-D5): bt_ev / bt_action_end go into the client-side
			// ordered apply queue. drainApplyQueue() (called from this same
			// updateCoopTask() below) applies them in strict seq order.
			CoopPump::enqueue(obj);
		}
		else if (stateString == "bt_intent")
		{
			// R2-P5 (SS2.1/SS2.5): host-side admission. bt_ack/bt_deny are
			// client-inbound (handled by R3-P1's client intent tracker, not
			// here); bt_desync stays unwired (R2-P9).
			CoopArbiter::onIntent(obj);
		}
		else if (stateString == "battle_offer")
		{
			// R4-P1 (SS2.7): client-inbound.
			CoopHandshake::onOffer(_game, obj);
		}
		else if (stateString == "battle_accept")
		{
			// R4-P1 (SS2.7): host-inbound.
			CoopHandshake::onAccept(_game, obj);
		}
		else if (stateString == "battle_refuse")
		{
			// R4-P1 (SS2.7): host-inbound.
			CoopHandshake::onRefuse(_game, obj);
		}
		else if (stateString == "battle_ready")
		{
			// R4-P1 (SS2.7): host-inbound.
			CoopHandshake::onReady(_game, obj);
		}
		else if (stateString == "bt_desync")
		{
			// R2-P9 (SS2.3): host-inbound. CoopHashCheck::verify() on the
			// REPORTING client has already frozen its own input, sent this,
			// and shown its own sticky banner - the host side of the spike's
			// mismatch behavior is "log it" (SS2.8 "NO partial repair", no
			// host-side repair/rejoin exists yet; rejoin is post-spike). The
			// host is not otherwise gated by receiving this.
			Log(LOG_ERROR) << "[coop-hash] peer bt_desync report: battleId="
				<< obj.get("battleId", 0u).asUInt() << " seq=" << obj.get("seq", 0u).asUInt()
				<< " bucket=" << obj.get("bucket", "?").asString()
				<< " expect=" << obj.get("expect", "").asString()
				<< " got=" << obj.get("got", "").asString()
				<< " bundlePath=" << obj.get("bundlePath", "").asString();
		}
		else if (stateString == "bt_ack")
		{
			// R3-P1 (IR-2): client-inbound - records the actionId for this
			// client's own in-flight intent, if this ack matches it.
			CoopArbiter::onAck(obj);
		}
		else if (stateString == "bt_deny")
		{
			// R3-P1 (IR-2): client-inbound - clears the in-flight lock if
			// this matches it, stores lastDeny (event_state's own field),
			// and shows the CoopBattleUi::showDeny() banner (R2-P6's
			// presenter, unwired until now).
			CoopArbiter::onDeny(obj);
		}
		return;
	}

	// R1-P3 quarantine catch-all (inventory-wire-protocol.md sections A-E) -
	// EARLY, before the legacy if-chain, so no quarantined battle-sim message can
	// reach a handler that referenced restore-killed symbols.
	if (legacyBattleMessageDropped(stateString))
		return;

	// Multiplayer voting is host-authoritative:
	//   vote_request: a client asks the host to create a vote; requesting it is YES.
	//   vote_start:   the host assigns the id, majority rule and ordered names.
	//   vote_cast:    a client submits one choice for its seat.
	//   vote_update:  the host broadcasts the authoritative seat-by-seat snapshot.
	//   vote_result:  the host announces pass/fail; only the host executes the action.
	//   vote_cooldown: the host rejects a requester that is still inside its 60s window.
	// Every packet is tied to a vote id, and VoteSession::castVote rejects a
	// second choice from the same seat. This keeps 2-4 player results deterministic.
	if (stateString == "vote_request")
	{
		if (getServerOwner())
		{
			if (_activeVote.active)
			{
				broadcastVoteStart();
				broadcastVoteUpdate();
			}
			else
			{
				beginVoteAsHost(
					obj.get("action", "").asString(),
					obj.get("title", "VOTE").asString(),
					obj.get("question", "").asString(),
					obj.get("from", -1).asInt());
			}
		}
		return;
	}

	if (stateString == "vote_start")
	{
		if (!getServerOwner())
		{
			const std::uint64_t voteId = obj.get("vote_id", Json::UInt64(0)).asUInt64();
			const int totalPlayers = std::max(2, std::min(4,
				obj.get("total_players", seatCount()).asInt()));
			const int starterSeat = obj.get("starter_seat", -1).asInt();
			if (voteId != 0 && (!_activeVote.active || _activeVote.id != voteId))
			{
				std::vector<std::string> playerNames;
				if (obj.isMember("player_names") && obj["player_names"].isArray())
				{
					for (const auto& value : obj["player_names"])
					{
						playerNames.push_back(value.asString());
					}
				}

				// The client stores the host's exact seat/name snapshot. Vote arrays and
				// names therefore use the same indexes on every machine.
				const std::uint32_t remainingMs = std::max<std::uint32_t>(
					1, obj.get("remaining_ms", VoteSession::DEFAULT_TIMEOUT_MS).asUInt());

				_activeVote.start(
					voteId,
					obj.get("action", "").asString(),
					obj.get("title", "VOTE").asString(),
					obj.get("question", "").asString(),
					totalPlayers,
					playerNames,
					starterSeat,
					remainingMs);
			}
			_voteRequestPending = false;
			openVoteMenu();
			updateVoteMenu();
		}
		return;
	}

	if (stateString == "vote_cast")
	{
		if (getServerOwner()
			&& obj.get("vote_id", Json::UInt64(0)).asUInt64() == _activeVote.id)
		{
			acceptVote(obj.get("from", -1).asInt(), obj.get("yes", false).asBool());
		}
		return;
	}

	if (stateString == "vote_update")
	{
		if (!getServerOwner()
			&& obj.get("vote_id", Json::UInt64(0)).asUInt64() == _activeVote.id)
		{
			readVoteSnapshot(obj);
			if (obj.isMember("remaining_ms"))
			{
				_activeVote.setRemainingMilliseconds(std::max<std::uint32_t>(
					1, obj["remaining_ms"].asUInt()));
			}
			updateVoteMenu();
		}
		return;
	}

	if (stateString == "vote_result")
	{
		if (!getServerOwner()
			&& obj.get("vote_id", Json::UInt64(0)).asUInt64() == _activeVote.id)
		{
			readVoteSnapshot(obj);
			const bool passed = obj.get("passed", false).asBool();
			_activeVote.finish(passed);
			_voteRequestPending = false;
			updateVoteMenu();
		}
		return;
	}

	if (stateString == "vote_cooldown")
	{
		if (!getServerOwner() && obj.get("to", -1).asInt() == localSeat())
		{
			_voteRequestPending = false;
			showVoteCooldownDialog(std::max<std::uint32_t>(
				1, obj.get("remaining_ms", VOTE_START_COOLDOWN_MS).asUInt()));
		}
		return;
	}

	if (stateString == "custom_battle_craft_locked")
	{
		if (!getServerOwner() && connectionTCP::session.lobbyMode == 0)
		{
			const int craftId = obj.get("selected_craft_id", -1).asInt();
			if (craftId >= 0)
			{
				connectionTCP::session.lockCustomBattleCraft(craftId);
				_coop_selected_craft_id = static_cast<std::size_t>(craftId);
			}
		}
		return;
	}

	if (stateString == "kick_player")
	{

		disconnectTCP();

		_game->pushState(new CoopState(123456));

	}

	// refused by the campaign roster gate (flow-redesign F3)
	if (stateString == "lobby_join_refused")
	{

		connectionTCP::joinRefusalReason = obj.get("reason", "").asString();

		disconnectTCP();

		// drop the "Connecting..." dialog left from the join attempt so
		// dismissing the refusal leaves no stray dialog behind
		if (!_game->getStates().empty())
		{
			CoopState* topDialog = dynamic_cast<CoopState*>(_game->getStates().back());
			if (topDialog && topDialog->getStateCode() == 15)
			{
				_game->popState();
			}
		}
		connectionTCP::forceCloseCoopStateMenu = true;

		_game->pushState(new CoopState(63));

	}

	if (stateString == "tcp_password")
	{

		// A bounce while the prompt is already up means the password the
		// player submitted was wrong: let updateCoopTask() raise the
		// "Incorrect password" dialog (441). The FIRST bounce is only the
		// challenge; flagging it -5 too made 441 bury the prompt on the
		// next frame, before the player could type anything.
		bool promptAlreadyOpen = false;
		for (State* s : _game->getStates())
		{
			if (dynamic_cast<PasswordCheckMenu*>(s) != nullptr)
			{
				promptAlreadyOpen = true;
				break;
			}
		}

		if (promptAlreadyOpen)
		{
			onConnect = -5;
		}
		else
		{
			connectionTCP::forceCloseCoopStateMenu = true;

			// If this room/server requires a password, open passwordCheck menu.
			_game->pushState(new PasswordCheckMenu(ipAddress, _game->getCoopMod()->getHostName(), tcp_port, false, true));
		}

	}

	if (stateString == "lobby_ready")
	{

		connectionTCP::session.campaignStarted();

		// Skirmish (mode 0): the host pressed START BATTLE. Leave the lobby with
		// it - the host is already generating the battle and streams it over, so
		// the client must not be left sitting on a dead lobby it cannot dismiss
		// (it has no button). Pops the join popup stacked above the lobby too.
		if (connectionTCP::session.lobbyMode == 0 && getServerOwner() == false)
		{
			connectionTCP::session.markLobbyClosed();
			while (!_game->getStates().empty())
			{
				bool isLobby = dynamic_cast<LobbyMenu*>(_game->getStates().back()) != nullptr;
				_game->popState();
				if (isLobby)
				{
					break;
				}
			}
		}

	}

	if (stateString == "change_team")
	{

		// teams are locked once the campaign starts (flow-redesign D3)
		if (connectionTCP::session.sessionLocked == false)
		{
			int gamemode = obj["gamemode"].asInt();
			connectionTCP::_coopGamemode = gamemode;
		}

	}

	// --- campaign flow redesign ------------------------------------------
	// Host clicked START CAMPAIGN: build this player's own world with the
	// host's difficulty (D2; ironman stays host-only) and begin base
	// placement. The lobby is wiped by setState.
	if (stateString == "campaign_start" && getServerOwner() == false)
	{

		int difficulty = obj["difficulty"].asInt();
		connectionTCP::_coopGamemode = obj["gamemode"].asInt();
		if (connectionTCP::_coopGamemode == 2)
			connectionTCP::no_bases = true;
		connectionTCP::saveID = obj["saveID"].asInt64();
		connectionTCP::session.campaignStarted();
		connectionTCP::session.lobbyMode = 1;

		std::vector<std::string> players;
		for (const auto& p : obj["players"])
		{
			players.push_back(p.asString());
		}

		CoopCampaignType campaignType =
			static_cast<CoopCampaignType>(obj.get("campaignType", 0).asInt());

		if (campaignType == CoopCampaignType::Shared)
		{
			// PRD-J02: a SHARED client is a replica - it never builds its own
			// world. Do NOT run beginInitialBasePlacement. Hold the wait dialog
			// until the host finishes placing its first base and streams the
			// authoritative world (streamSharedWorldToClient ->
			// MAP_RESULT_LOAD_PROGRESS), which the client then adopts exactly
			// like a resume. The roster/type ride the streamed save's header.
			connectionTCP::session.markLobbyClosed();
			connectionTCP::session.resumeAck = false;
			_game->pushState(new CoopState(COOP_DLG_CLIENT_LOAD_WAIT));
		}
		else
		{
			SavedGame* save = _game->getMod()->newSave((GameDifficulty)difficulty);
			save->setDifficulty((GameDifficulty)difficulty);
			save->setCoopSave(true);
			save->setCoopPlayers(players);
			// PRD-J01: adopt the host's campaign economy model (default Separate).
			save->setCampaignType(campaignType);
			_game->setSavedGame(save);

			connectionTCP::session.markLobbyClosed();

			GeoscapeState* gs = new GeoscapeState;
			_game->setState(gs);
			gs->init();

			if (!connectionTCP::no_bases)
				beginInitialBasePlacement(_game, gs, _game->getSavedGame()->getBases()->back());
			else
			{
				// PvP: the alien side has no bases.  This writes the client's
				// world into its OWN process-local coopFilesClient map
				// (getServerOwner()==false here); that blob never reaches the
				// host, so it can NOT drive a host-side rejoin.  On rejoin the
				// HOST supplies the client world instead: it embeds a minimal
				// no_bases stub in its .sav (SavedGame::save -> buildCoopStub)
				// and synthesizes the same stub in LobbyMenu::resumeCampaign.
				// The WAIT_BASES dialog always shows BEGIN regardless of blob
				// arrival (see CoopState::waitSatisfied); this local save is
				// not needed for the initial session start.
				std::string blobKey = hostBlobKey(_game->getCoopMod()->getCurrentClientName());
				try
				{
					_game->getSavedGame()->saveCoopToMemory(blobKey, _game->getMod(), blobKey);
				}
				catch (const std::exception &e)
				{
					Log(LOG_ERROR) << "[coop] no_bases client blob failed: " << e.what();
				}
				_game->pushState(new CoopState(COOP_DLG_CLIENT_HOLD));
			}
		}

	}

	// Host clicked RESUME CAMPAIGN and we have a stored world: fetch it
	// (same wire flow as the classic Profile resume) (F3)
	if (stateString == "campaign_resume" && getServerOwner() == false)
	{

		_game->pushState(new CoopState(COOP_DLG_CLIENT_LOAD_WAIT));

		Json::Value root;
		root["state"] = "request_load_progress";
		sendTCPPacketData(root.toStyledString());

	}

	// PRD-11 C13: the host is busy streaming another transfer. Signal the
	// load-wait dialog to retry (it schedules a ~2s-spaced retry, bounded).
	if (stateString == "load_progress_busy" && getServerOwner() == false)
	{
		connectionTCP::loadProgressBusy = true;
	}

	// The host began/resumed the campaign: drop the waiting dialog (D5)
	if (stateString == "campaign_begun" && getServerOwner() == false)
	{

		connectionTCP::session.signalCampaignBegun();
		connectionTCP::session.sessionLive();

	}

	// A resuming player finished loading its world (F3). For a battle save
	// the geoscape ack triggers phase two: the battle stream.
	if (stateString == "resume_ack")
	{

		// PRD-11 C8: only stream the battle to a client that was actually served
		// a resume world blob. A registered-but-no-blob client is routed through
		// fresh base building and acks too (BaseNameState); streaming the old
		// battle into its freshly built world would corrupt it. Such an acker is
		// absent from resumeBattleEligible, so it falls through to the plain
		// campaign-resume ack.
		std::string acker = _game->getCoopMod()->getCurrentClientName();
		bool battleEligible = connectionTCP::session.resumeBattleEligible.count(acker) > 0;

		if (connectionTCP::session.resumeBattlePending && battleEligible)
		{
			connectionTCP::session.resumeBattlePending = false;
			connectionTCP::session.resumeBattleEligible.clear();

			// R4-REWIRE: "campaign_resume_battle" is quarantined (R1-P3,
			// inventory-wire-protocol.md section E - "handshake survives, battle-save
			// payload path dies"). Its receive handler is deleted; this send now
			// lands on the peer's legacyBattleMessageDropped catch-all until the
			// mid-battle campaign-resume flow is rebuilt in r4/r5.
			Json::Value root;
			root["state"] = "campaign_resume_battle";
			sendTCPPacketData(root.toStyledString());
		}
		else
		{
			connectionTCP::session.resumeAck = true;

			// issue #91: EVERY streamed world the client adopts parks it in
			// COOP_DLG_CLIENT_RESUME_HOLD (LoadGameState) - a dialog with no button
			// and no timeout - and the only thing that can ever release it is a
			// campaign_begun. So for THAT ack the release is owed by default, and
			// there is exactly one reason to withhold it: a host wait dialog is on our
			// stack. That dialog IS the deliberate hold, and its RESUME/BEGIN sends the
			// release itself (CoopState::previous). Both operator flows push it
			// synchronously before the client can possibly ack (GeoscapeState
			// bootstrap, LobbyMenu::resumeCampaign), so this reads their intent.
			//
			// `adoptedWorld` is what keeps this to the acks that actually hold
			// something. The other senders - base naming (BaseNameState) and battle
			// phase two (LoadGameState's battleclient branch) - carry no hold that a
			// campaign_begun should open: releasing the base-placement hold early
			// un-freezes the first placer's clock while the other player is still
			// placing (test_lobby_gating BUG2).
			//
			// This used to be a pair of one-shot flags armed by two of the restream
			// sites. The streamer frees itself the moment the last chunk goes out,
			// long before the client has adopted anything, so two restreams in a row
			// SHARED one flag: the first ack consumed it and the second found it
			// false, leaving the client holding a perfectly good world that nothing
			// would ever release. The third stream site (request_load_progress) armed
			// no flag at all. Deciding it here - from the state the answer actually
			// depends on - covers every site, present and future.
			const bool adoptedWorld = obj.get("adoptedWorld", false).asBool();

			bool hostWaitDialog = false;
			if (getServerOwner() && adoptedWorld)
			{
				for (State* st : _game->getStates())
				{
					CoopState* cs = dynamic_cast<CoopState*>(st);
					if (cs && CoopState::isHostWaitDialog(cs->getStateCode()))
					{
						hostWaitDialog = true;
						break;
					}
				}

				if (!hostWaitDialog)
				{
					connectionTCP::session.sessionLive();

					Json::Value begun;
					begun["state"] = "campaign_begun";
					sendTCPPacketData(begun.toStyledString());

					Log(LOG_INFO) << "[coop] restream adopted; released the client hold";
				}
				else
				{
					Log(LOG_INFO) << "[coop] restream adopted; the host wait dialog owns"
						" the release (its RESUME/BEGIN sends campaign_begun)";
				}
			}
		}

	}

	if (stateString == "giftSoldier")
	{

		if (_game->getSavedGame())
		{

			int soldier_id = obj["soldier_id"].asInt();
			int owner = obj["owner"].asInt();
			int unit_id = obj["unit_id"].asInt();

			Log(LOG_INFO) << "[coop-gift] RECV giftSoldier id=" << soldier_id << " owner=" << owner
			              << " hasYaml=" << (obj.isMember("soldier_yaml") ? 1 : 0)
			              << " inBattle=" << (_game->getSavedGame()->getSavedBattle() ? 1 : 0);

			if (obj.isMember("soldier_yaml") && _game->getCoopMod()->playerInsideCoopBase == true)
			{

				// Our SavedGame is currently swapped out for the peer's base
				// view; applying the transfer now would land the soldier in
				// the temporary world and lose it on exit. Queue the real
				// apply for later, but ALSO drop a display copy into the
				// visited base so the new owner sees the soldier right away,
				// and show the notification now.
				Log(LOG_INFO) << "[coop-gift] RECV deferred (viewing peer base)";

				try
				{

					int stationBaseId = obj["station_base_id"].asInt();

					YAML::YamlRootNodeReader reader(YAML::YamlString{obj["soldier_yaml"].asString()}, "giftSoldier");
					auto soldierReader = reader["soldier"];
					std::string type = soldierReader["type"].readVal(_game->getMod()->getSoldiersList().front());
					std::string soldierName = soldierReader["name"].readVal(std::string());

					Base* visited = 0;

					for (auto& base : *_game->getSavedGame()->getBases())
					{
						if (base->_coop_base_id == stationBaseId)
						{
							visited = base;
							break;
						}
					}

					if (visited && _game->getMod()->getSoldier(type))
					{
						// Display-only copy: this world is discarded on exit;
						// the durable copy comes from the deferred replay.
						Soldier* copy = new Soldier(_game->getMod()->getSoldier(type), 0, 0 /*nationality*/);
						copy->load(soldierReader, _game->getMod(), _game->getSavedGame(), _game->getMod()->getScriptGlobal());
						copy->setCraft(0);
						copy->setCoopBase(stationBaseId);
						copy->setOwnerPlayerId(owner);
						copy->setCoop(owner);
						visited->getSoldiers()->push_back(copy);
					}

					if (!obj.get("notified", false).asBool())
					{
						std::string baseName = visited ? visited->getName() : "their base";
						_game->pushState(new GiftNoticeState(getCurrentClientName() + " gifted " + soldierName + " to you at base " + baseName));
						obj["notified"] = true;
					}

				}
				catch (const std::exception& e)
				{
					Log(LOG_INFO) << "[coop-gift] RECV display-copy failed: " << e.what();
				}

				_pendingIncomingGifts.push_back(obj);

			}
			else if (obj.isMember("soldier_yaml")
			         && (_game->getCoopMod()->coopMissionEnd
			             || _game->getSavedGame()->getSavedBattle()))
			{

				// Coop battle just ended (or is still tearing down): our live
				// SavedGame is still the HOST's battle world - the own-world
				// reload (GeoscapeState::init) has not run yet. Applying the
				// physical gift now would match the giver's real base in
				// that throwaway world (coopBase cleared to -1, soldier deleted
				// by the post-battle cleanup) and the follow-up client-progress
				// push would upload the host world as our own-world blob. Defer
				// and let processPendingSoldierGifts() replay it once our
				// own world is restored (host base is a mirror there, so the
				// soldier correctly stays a guest at station_base_id).
				Log(LOG_INFO) << "[coop-gift] RECV deferred (mission-end swapped world)";
				_pendingIncomingGifts.push_back(obj);

			}
			else if (obj.isMember("soldier_yaml"))
			{

				// Physical transfer: the giver removed the soldier from their
				// save; recreate it in ours, keeping its station base.
				int stationBaseId = obj["station_base_id"].asInt();

				try
				{

					YAML::YamlRootNodeReader reader(YAML::YamlString{obj["soldier_yaml"].asString()}, "giftSoldier");
					auto soldierReader = reader["soldier"];

					std::string type = soldierReader["type"].readVal(_game->getMod()->getSoldiersList().front());

					if (_game->getMod()->getSoldier(type))
					{

						// If the station base is one of OUR real bases, the
						// soldier is coming home: it lives there normally.
						// Otherwise it stays a guest at the giver's base and
						// merely lives in our save (guest-soldier model).
						Base* homeBase = 0;
						Base* firstOwnBase = 0;

						for (auto& base : *_game->getSavedGame()->getBases())
						{

							if (base->_coopBase == false && base->_coopIcon == false)
							{

								if (!firstOwnBase)
								{
									firstOwnBase = base;
								}

								if (base->_coop_base_id == stationBaseId)
								{
									homeBase = base;
									break;
								}

							}

						}

						Base* targetBase = homeBase ? homeBase : firstOwnBase;

						// No own base in the current save = our world is not
						// (yet) loaded, e.g. the transitional frames right
						// after leaving the peer's base view. Never consume
						// the packet in that window - defer and replay.
						if (!targetBase)
						{
							Log(LOG_INFO) << "[coop-gift] RECV deferred (no own base in current save)";
							_pendingIncomingGifts.push_back(obj);
						}
						else
						{

						// Ignore duplicate deliveries via the sender's unique
						// packet id (in-memory: with the host save as the single
						// authority, packets are never re-sent across sessions).
						long long xferId = obj.get("xfer_id", 0).asInt64();
						bool exists = (xferId != 0 && _seenGiftPacketIds.count(xferId) != 0);

						if (xferId != 0)
						{
							_seenGiftPacketIds.insert(xferId);
						}

						Log(LOG_INFO) << "[coop-gift] RECV type=" << type << " exists=" << (exists ? 1 : 0)
						              << " homeBase=" << (homeBase ? homeBase->getName() : "none")
						              << " targetBase=" << targetBase->getName()
						              << " stationBaseId=" << stationBaseId;

						if (!exists)
						{

							Soldier* soldier = new Soldier(_game->getMod()->getSoldier(type), 0, 0 /*nationality*/);
							soldier->load(soldierReader, _game->getMod(), _game->getSavedGame(), _game->getMod()->getScriptGlobal());

							// The peer's soldier ids and ours come from
							// separate saves: on collision give the incoming
							// soldier a fresh id so lookups stay unambiguous.
							int maxId = soldier->getId();

							bool collision = false;

							for (auto& base : *_game->getSavedGame()->getBases())
							{
								for (auto& s : *base->getSoldiers())
								{
									if (s->getId() == soldier->getId())
									{
										collision = true;
									}
									maxId = std::max(maxId, s->getId());
								}
							}

							for (auto& s : *_game->getSavedGame()->getDeadSoldiers())
							{
								if (s->getId() == soldier->getId())
								{
									collision = true;
								}
								maxId = std::max(maxId, s->getId());
							}

							if (collision)
							{
								soldier->setId(maxId + 1);
							}

							soldier->setCraft(0);
							soldier->setCoopBase(homeBase ? -1 : stationBaseId);
							soldier->setOwnerPlayerId(owner);
							soldier->setCoop(owner);

							targetBase->getSoldiers()->push_back(soldier);

							// SoldiersState/CraftSoldiersState restore the
							// roster from these snapshots when they close; if
							// one is open right now (snapshot non-empty), add
							// the soldier there too or the restore drops it.
							if (!targetBase->base_oldsoldiers.empty())
							{
								targetBase->base_oldsoldiers.push_back(soldier);
							}
							if (!targetBase->base_oldsoldiers2.empty())
							{
								targetBase->base_oldsoldiers2.push_back(soldier);
							}

							Log(LOG_INFO) << "[coop-gift] RECV added soldier '" << soldier->getName()
							              << "' id=" << soldier->getId() << " to base '" << targetBase->getName()
							              << "' coopBase=" << soldier->getCoopBase();

							// keep the host-side client blob fresh (no-op on
							// the host itself)
							pushProgressToHostSilently();

							// Tell the new owner (skip if the deferred path
							// already notified during a base visit). The
							// station base's name is the one the player
							// recognizes - for a guest that's the giver's
							// (mirror) base, not the own base holding it.
							if (!obj.get("notified", false).asBool())
							{

								std::string baseName = targetBase->getName();

								for (auto& base : *_game->getSavedGame()->getBases())
								{
									if (base->_coop_base_id == stationBaseId)
									{
										baseName = base->getName();
										break;
									}
								}

								_game->pushState(new GiftNoticeState(getCurrentClientName() + " gifted " + soldier->getName() + " to you at base " + baseName));

							}

						}

						}

					}
					else
					{
						Log(LOG_INFO) << "[coop-gift] RECV unknown soldier type " << type;
					}

				}
				catch (const std::exception& e)
				{
					Log(LOG_INFO) << "[coop-gift] RECV failed to load soldier yaml: " << e.what();
				}

			}
			else
			{
				// Live Battlescape control transfer. The persistent Soldier move is
				// still deferred until mission end, but ownership, the receiver popup
				// and spectator state update immediately on both battle replicas.
				SavedBattleGame* battle = _game->getSavedGame()->getSavedBattle();
				if (battle)
				{
					const int previousOwner = obj.get("previous_owner", -1).asInt();
					const long long giftEventId = obj.get("xfer_id", Json::Value::Int64(0)).asInt64();

					if (giftEventId != 0 && _seenGiftPacketIds.count(giftEventId) != 0)
					{
						Log(LOG_INFO) << "[coop-gift] ignored duplicate battle gift event " << giftEventId;
					}
					else
					{
						BattleUnit* matchedUnit = nullptr;
						for (BattleUnit* unit : *battle->getUnits())
						{
							bool match = (unit_id != -1 && unit->getId() == unit_id);
							if (!match && unit->getGeoscapeSoldier()
								&& unit->getGeoscapeSoldier()->getId() == soldier_id)
							{
								match = true;
							}
							if (match)
							{
								matchedUnit = unit;
								break;
							}
						}

						if (!matchedUnit || owner < 0 || owner >= seatCount())
						{
							Log(LOG_WARNING) << "[coop-gift] rejected battle gift packet: invalid unit or owner";
						}
						else if (previousOwner >= 0 && (int)matchedUnit->getCoopSeat() != previousOwner)
						{
							Log(LOG_WARNING) << "[coop-gift] ignored stale battle gift for unit "
								<< matchedUnit->getId() << ": expected owner " << previousOwner
								<< ", actual " << (int)matchedUnit->getCoopSeat();
						}
						else
						{
							matchedUnit->setCoopSeat((CoopSeat)owner);
							Soldier* matchedSoldier = matchedUnit->getGeoscapeSoldier();
							if (matchedSoldier)
							{
								matchedSoldier->setOwnerPlayerId(owner);
								matchedSoldier->setCoop(owner);

								// If a soldier returns to this machine during the battle, cancel
								// any older pending transfer-away for the same object.
								if (owner == localSeat())
								{
									_pendingSoldierGifts.erase(
										std::remove_if(_pendingSoldierGifts.begin(), _pendingSoldierGifts.end(),
											[matchedSoldier](const PendingSoldierGift& pending)
											{ return pending.soldier == matchedSoldier; }),
										_pendingSoldierGifts.end());
								}
							}

							if (owner == localSeat() && previousOwner != owner)
							{
								// Campaign battle gifts arrive through giftSoldier rather than
								// giveUnit, but they have the same local-selection requirement:
								// receiving ownership does not trigger a mouse click or
								// selectPlayerUnit(), so make the received soldier the current
								// gift target immediately without changing selectedUnit.
								setGiftSelectedBattleUnit(matchedUnit);
							}

							if (battle->getSelectedUnit() == matchedUnit && owner != localSeat())
							{
								battle->selectNextPlayerUnit();
							}

							if (giftEventId != 0)
							{
								_seenGiftPacketIds.insert(giftEventId);
							}

							refreshBattleGiftControlState();

							if (owner == localSeat() && previousOwner != owner)
							{
								std::string giverName = obj.get("giver_name", "").asString();
								if (giverName.empty()) giverName = seatName(previousOwner);
								if (giverName.empty()) giverName = getCurrentClientName();
								if (giverName.empty()) giverName = "Another player";

								std::string soldierName = obj.get("soldier_name", "").asString();
								if (soldierName.empty() && matchedSoldier)
								{
									soldierName = matchedSoldier->getName();
								}
								if (soldierName.empty()) soldierName = "a soldier";

								_game->pushState(new GiftNoticeState(
									giverName + " gave " + soldierName + " to you."));
							}
						}
					}
				}
			}

		}

	}

	if (stateString == "ufo_popup")
	{

		std::string str_type = obj["type"].asString();
		std::string str_race = obj["race"].asString();

		// Legacy single-slot fields kept for any other reader; the QUEUE is what the
		// geoscape consumes, so simultaneous detections no longer overwrite each other.
		show_coop_ufo_popup_type = str_type;
		show_coop_ufo_popup_race = str_race;

		CoopUfoAlert alert;
		alert.ufoId = obj.get("ufo_id", -1).asInt();
		alert.type = str_type;
		alert.race = str_race;
		coopUfoAlerts.push_back(alert);
		while (coopUfoAlerts.size() > kMaxCoopUfoAlerts)
			coopUfoAlerts.erase(coopUfoAlerts.begin()); // drop oldest, stay bounded

	}

	if (stateString == "mission_popup")
	{

		int mission_id = obj["mission_id"].asInt();

		// issue #78: in SHARED, materialize the site immediately if the snapshot
		// has not delivered it yet (spawn + detection in one host tick, with the
		// host's snapshot sender frozen behind its own dialog). Same create path
		// as the target_positions receiver; think() then matches by id and pops.
		if (isSharedReplica() && _game->getSavedGame() && obj.isMember("rules"))
		{
			SavedGame* sg = _game->getSavedGame();
			MissionSite* site = nullptr;
			for (auto* s : *sg->getMissionSites())
				if (s->getId() == mission_id) { site = s; break; }
			if (!site)
			{
				const RuleAlienMission* srule = _game->getMod()->getAlienMission(obj["rules"].asString(), false);
				AlienDeployment* dep = _game->getMod()->getDeployment(obj["deployment"].asString(), false);
				if (srule && dep)
				{
					site = new MissionSite(srule, dep, nullptr);
					site->setId(mission_id);
					site->setLongitude(obj["lon"].asDouble());
					site->setLatitude(obj["lat"].asDouble());
					site->setAlienRace(obj["race"].asString());
					site->setCity(obj["city"].asString());
					site->setSecondsRemaining((size_t)obj.get("time", 100000000).asUInt64());
					site->setDetected(true);
					sg->getMissionSites()->push_back(site);
					// Keep the main-thread despawn prune from eating it before the
					// next snapshot refreshes the authoritative set.
					std::lock_guard<std::mutex> lk(sharedLiveSiteIdsMutex);
					sharedLiveSiteIds.insert(mission_id);
				}
			}
		}

		show_coop_mission_popup = mission_id;

	}

	// delete_base
	if (stateString == "delete_base")
	{
		// PRD-J07: SEPARATE-only mirror machinery. In SHARED base removal rides the
		// fac_dismantle / base_destroyed shared_apply (keeps base indices in
		// lock-step); a stray delete_base would match a REAL base's random
		// _coop_base_id and desync every index-routed command.
		if (isSharedCampaign())
		{
			return;
		}

		int base_id = obj["base_id"].asInt();

		if (_game->getSavedGame())
		{

			if (auto* sg = _game->getSavedGame())
			{
				auto& bases = *sg->getBases(); // std::vector<Base*>&

				for (auto it = bases.begin(); it != bases.end();)
				{
					Base* b = *it;
					if (b && b->_coop_base_id == base_id)
					{
						delete b;             // free memory permanently
						it = bases.erase(it); // remove from the list; returns next iterator
						break;
					}
					else
					{
						++it;
					}
				}
			}
		}
	}

	// cutscene!
	if (stateString == "cutscene")
	{

		std::string cutsceneId = obj["cutsceneId"].asString();
		int monthsPassed = obj["monthsPassed"].asInt();
		int daysPassed = obj["daysPassed"].asInt();
		int ending = obj["ending"].asInt();

		if (_game->getSavedGame())
		{

			_game->getSavedGame()->setEnding((GameEnding)ending);

			_game->getSavedGame()->setMonthsPassed(monthsPassed);
			_game->getSavedGame()->setMonthsPassed(daysPassed);
		}

		allow_cutscene = false;

		_game->pushState(new CutsceneState(cutsceneId));
	}

	if (stateString == "chat_message")
	{

		std::string msg_time = obj["msg_time"].asString();
		std::string msg_player = obj["msg_player"].asString();
		std::string msg_text = obj["msg_text"].asString();

		if (_chatMenu)
		{
			_chatMenu->addMessage(msg_time, msg_player, msg_text);
		}
	}

	if (stateString == "new_game")
	{

		_game->pushState(new NewGameState);

	}

	if (stateString == "request_load_progress")
	{

		// issue #93: SKIRMISH (NEW BATTLE > COOP) rejoin. There is no campaign
		// world to resume and no stored per-client blob - in a skirmish the world
		// IS the battle, so the two-phase (geoscape then battle) dance a campaign
		// resume runs has nothing to do here. Stream the live battle snapshot the
		// same way the mission originally started, in one phase. Must come first:
		// the no-blob arm below would otherwise answer a skirmish with
		// campaign_start and hand the rejoiner a brand new campaign.
		if (_game->getSavedGame() && !sendFileClient
			&& _game->getCoopMod()->getCoopCampaign() == false && coopBattleLive(_game))
		{
			streamSkirmishBattleToClient();
		}
		else if (_game->getSavedGame() && !sendFileClient && isSharedCampaign())
		{

			// PRD-J02: SHARED resume/bootstrap. There is exactly one authoritative
			// world (the host's) and no per-client stored blob - serialize the
			// CURRENT world fresh and stream it as the client's replica. The
			// client adopts it via the same MAP_RESULT_LOAD_PROGRESS path a
			// SEPARATE resume uses.
			streamSharedWorldToClient();
			if (!sendFileClient)
			{
				// serialization refused (unplaced base etc.): let the client retry
				Json::Value busy;
				busy["state"] = "load_progress_busy";
				sendTCPPacketData(busy.toStyledString());
			}
			else
			{
				// P2/F3: SHARED mid-battle resume. The geoscape-phase world is now
				// streaming; if the authoritative world carries a battle, ride the very
				// same two-phase battle stream a SEPARATE resume uses. Arm the pending
				// flag and mark this client eligible so its geoscape resume_ack fires
				// campaign_resume_battle -> SEND_FILE_CLIENT_SAVE -> battlehost (the
				// snapshot chain is mode-agnostic; the SHARED role is derived from
				// getServerOwner() at BattlescapeState:1687). The client's phase-one
				// loadCoopProgress load drops the battleGame, so the geoscape adopt
				// stays battle-free and the battle arrives fresh in phase two.
				connectionTCP::session.resumeBattlePending =
					(_game->getSavedGame()->getSavedBattle() != nullptr);
				if (connectionTCP::session.resumeBattlePending)
				{
					connectionTCP::session.resumeBattleEligible.insert(
						_game->getCoopMod()->getCurrentClientName());
				}
			}
		}
		else if (_game->getSavedGame() && !sendFileClient)
		{

			// battle live: after the geoscape world ack, stream the battle
			// (F3 battle-save resume + F4 mid-battle rejoin share this)
			connectionTCP::session.resumeBattlePending = (_game->getSavedGame()->getSavedBattle() != nullptr);

			// PRD-09 C12: F3 battle-save resume in a fresh process. Unlike the
			// live mission-start path (SEND_FILE_CLIENT_TRUE stashes
			// coop_geoscape_return before dispatching the mission), nothing
			// regenerates that snapshot on resume - so the server owner's
			// mission-end restore would keep the peer-derived battle world as its
			// campaign. Stash the loaded world's geoscape now, while
			// getServerOwner() is true (so it lands in coopFilesHost where the
			// restore reads it). Detach the battle first: coop_geoscape_return
			// must be a PURE geoscape - the restore reloads it as the continuation
			// world and re-entering it must not resurrect the just-finished battle.
			if (connectionTCP::session.resumeBattlePending && getServerOwner() == true && _game->getCoopMod()->getCoopCampaign() == true)
			{
				SavedBattleGame* keepBattle = _game->getSavedGame()->detachBattleGame();
				_game->getSavedGame()->saveCoopToMemory("coop_geoscape_return", _game->getMod(), "coop_geoscape_return");
				_game->getSavedGame()->reattachBattleGame(keepBattle);
				Log(LOG_INFO) << "[coop] F3 battle resume: stashed geoscape-only coop_geoscape_return for mission-end restore";
			}

			std::string filename = hostBlobKey(_game->getCoopMod()->getCurrentClientName());

			bool blobFound = false;
			{
				std::lock_guard<std::mutex> lock(coopFilesMutex);
				auto it = coopFilesHost.find(filename);
				if (it != coopFilesHost.end() && !it->second.empty())
				{
					// found! snapshot the blob for the streamer thread
					sendProgressLoadBlob = it->second;
					blobFound = true;
				}
			}

			if (!blobFound)
			{

				// registered player without a stored world: fresh world with
				// the campaign's difficulty + base building (D2/D6)
				Json::Value root = buildCampaignStartPacket(_game->getSavedGame());

				sendTCPPacketData(root.toStyledString());

			}
			else
			{

				// PRD-11 C8: this client is being served a real resume world;
				// mark it eligible for the follow-up battle stream. The no-blob
				// campaign_start branch above deliberately does NOT.
				connectionTCP::session.resumeBattleEligible.insert(
					_game->getCoopMod()->getCurrentClientName());

				sendFileClient = true;
				sendProgressLoadFileToClient = filename;

			}

		}
		else if (_game->getSavedGame() && sendFileClient)
		{

			// PRD-11 C13: the streamer is busy with another transfer. Never drop
			// the request silently (the client's load-wait dialog has no timeout);
			// tell it to retry.
			Json::Value busy;
			busy["state"] = "load_progress_busy";
			sendTCPPacketData(busy.toStyledString());

		}

	}

	if (stateString == "sendProgressSaveRequest")
	{

		long long saveID = obj["saveID"].asInt64();
		connectionTCP::saveID = saveID;

		sendSaveProgressFile();

	}

	if (stateString == "sendCraft")
	{

		setHost(false);

		CoopState* coopWindow = new CoopState(4);
		_game->pushState(coopWindow);

		sendMissionFile();
	}

	if (stateString == "craft_list")
	{
		const std::size_t id = obj["selected_craft_id"].asUInt();

		// Once the host has entered EQUIP CRAFT, the selected craft is frozen.
		// Ignore any stale or malicious craft_list packet that tries to move it.
		if (!connectionTCP::session.customBattleCraftLocked
			|| connectionTCP::session.customBattleCraftId == static_cast<int>(id))
		{
			_coop_selected_craft_id = id;
		}
	}

	// CHANGE THE BASE NAME
	if (stateString == "changeBaseName")
	{
		// PRD-J07: SEPARATE-only (renames a _coopIcon mirror + the basehost memory
		// blob). SHARED renames ride the base_rename shared_apply.
		if (isSharedCampaign())
		{
			return;
		}

		std::string old_name = obj["oldName"].asString();
		std::string new_name = obj["newName"].asString();

		for (auto base : *_game->getSavedGame()->getBases())
		{

			// change the base icon name
			if (old_name == base->getName() && base->_coopIcon == true)
			{

				base->setName(new_name);

				break;
			}
		}

		std::string filename = "basehost";

		SavedGame* file_units = new SavedGame();

		bool save = false;

		file_units->loadCoopSaveFromMemory(filename, _game->getMod(), _game->getLanguage(), filename);

		for (auto& base : *file_units->getBases())
		{

			if (base->getName() == old_name)
			{

				base->setName(new_name);
				save = true;
				break;
			}
		}

		if (save)
		{
			file_units->saveCoopToMemory(filename, _game->getMod(), filename);
		}
		
	}

	// transfer
	if (stateString == "transfer_completed")
	{

		int base_to_id = obj["base_to_id"].asInt();
		int base_from_id = obj["base_from_id"].asInt();
		int total_funds = obj["total_funds"].asInt();

		Base* baseFrom = 0;
		Base* baseTo = 0;

		if (!_game->getSavedGame())
		{
			_game->pushState(new CoopState(551));
			return;
		}
		
		for (auto& base : *_game->getSavedGame()->getBases())
		{
			if (base->_coop_base_id == base_from_id)
			{
				baseFrom = base;
				break;
			}
		}

		for (auto& base : *_game->getSavedGame()->getBases())
		{
			if (base->_coop_base_id == base_to_id)
			{
				baseTo = base;
				break;
			}
		}

		if (baseFrom && baseTo)
		{
			// TransferItemsState has two senders for this same "transfer" packet:
			//   createPendingTransfers() - ACK-gated. Nothing left the source base;
			//     this ACK is what applies the funds debit, the store removal and
			//     the co-op limit decrements (via removePendingTransfers()).
			//   completeTransfer()       - immediate. All of that already happened
			//     locally when the trade was made, so re-applying it here debits
			//     everything twice; the store re-validation inside
			//     removePendingTransfers() then finds nothing left to remove and
			//     fails, leaving the trade half-applied (the peer has the goods,
			//     this base keeps them AND keeps a stale pending list that the next
			//     trade would re-send).
			// The flag rides the packet and comes back untouched in this ACK.
			bool alreadyApplied = obj.get("already_applied", false).asBool();

			if (alreadyApplied || baseFrom->removePendingTransfers(baseTo->getTransfers()))
			{

				if (!alreadyApplied)
				{
					_game->getSavedGame()->setFunds(_game->getSavedGame()->getFunds() - total_funds);

					baseTo->decreaseCoopTransferLimits();
				}

				for (Transfer* transfer : *baseTo->getTransfers())
				{
					// ~Transfer deletes the soldier/craft it carries. Neither path
					// removes a transferred SOLDIER from the source base (it stays
					// on as a guest of the peer base, see completeTransfer()), and
					// removePendingTransfers() keeps crew soldiers too - so hand the
					// object back before freeing the Transfer, or the base is left
					// holding a dangling pointer.
					if (transfer)
					{
						Soldier* keptSoldier = transfer->getSoldier();
						if (keptSoldier
							&& std::find(baseFrom->getSoldiers()->begin(), baseFrom->getSoldiers()->end(),
								keptSoldier) != baseFrom->getSoldiers()->end())
						{
							transfer->setSoldier(nullptr);
						}
						Craft* keptCraft = transfer->getCraft();
						if (keptCraft
							&& std::find(baseFrom->getCrafts()->begin(), baseFrom->getCrafts()->end(),
								keptCraft) != baseFrom->getCrafts()->end())
						{
							transfer->setCraft(nullptr);
						}
					}
					delete transfer;
				}
				baseTo->getTransfers()->clear();

			}
			else
			{
				_game->pushState(new CoopState(552));
			}

		}
		else
		{
			_game->pushState(new CoopState(553));
		}

	}

	// purchase
	if (stateString == "purchase_completed")
	{

		int total_funds = obj["total_funds"].asInt();
		_game->getCoopMod()->coopFunds = _game->getCoopMod()->coopFunds - total_funds;

	}

	if (stateString == "transfer_failed" || stateString == "purchase_failed")
	{
		_game->pushState(new CoopState(551));
	}

	// Transfer and purchase
	// COOP living quarters: the peer reports how many of ITS soldiers are
	// stationed at each of OUR bases (see sendGuestCensus). We hold no Soldier
	// object for them, so this headcount is the only way they can occupy the
	// living quarters of the base they actually live in. Absent bases are reset,
	// so the census is always a full replacement, never a delta.
	if (stateString == "guest_census")
	{
		if (_game->getSavedGame())
		{
			std::map<int, int> reported;
			const Json::Value& list = obj["bases"];
			if (list.isArray())
			{
				for (const auto& e : list)
					reported[e.get("base_id", 0).asInt()] = e.get("guests", 0).asInt();
			}
			for (auto* base : *_game->getSavedGame()->getBases())
			{
				if (base->_coopBase || base->_coopIcon)
					continue;
				auto it = reported.find(base->_coop_base_id);
				base->coop_guests = (it != reported.end()) ? it->second : 0;
			}
		}
	}

	if (stateString == "purchase" || stateString == "transfer")
	{

		// Resolve the target base BEFORE acknowledging. updateCoopTask() only
		// applies a queued trade to a base whose _coop_base_id == base_to_id;
		// if no local base matches, the trade is silently retained forever while
		// the sender - told "*_completed" - has already removed its goods. So a
		// missing target base must be rejected here, not accepted (silent loss).
		int base_to_id = obj.get("base_to_id", 0).asInt();
		Base* targetBase = nullptr;
		if (_game->getSavedGame())
		{
			for (auto& base : *_game->getSavedGame()->getBases())
			{
				if (base->_coop_base_id == base_to_id)
				{
					targetBase = base;
					break;
				}
			}
		}

		// Check whether the transfer or purchase data is valid.
		if (targetBase &&
			obj.isMember("items") &&
			!obj["items"].empty())
		{
			// The request is valid.
			waitedTrades.append(obj);

			// Send a success response to the other player.
			if (stateString == "transfer")
			{
				Json::Value obj2;
				obj2["state"] = "transfer_completed";
				obj2["base_to_id"] = obj.get("base_to_id", 0);
				obj2["base_from_id"] = obj.get("base_from_id", 0);
				obj2["total_funds"] = obj.get("total_funds", 0);
				// echoed straight back so the sender can tell its own immediate
				// (already-applied) trades from the ACK-gated ones
				obj2["already_applied"] = obj.get("already_applied", false);
				sendTCPPacketData(obj2.toStyledString());
			}
			else
			{
				Json::Value obj3;
				obj3["state"] = "purchase_completed";
				obj3["total_funds"] = obj.get("total_funds", 0);
				sendTCPPacketData(obj3.toStyledString());
			}

		}
		else
		{
			// The request is invalid.
			// Send a failure response to the other player.
			if (stateString == "transfer")
			{
				Json::Value obj4;
				obj4["state"] = "transfer_failed";
				obj4["base_to_id"] = obj.get("base_to_id", 0);
				obj4["base_from_id"] = obj.get("base_from_id", 0);
				sendTCPPacketData(obj4.toStyledString());
			}
			else
			{
				Json::Value obj5;
				obj5["state"] = "purchase_failed";
				sendTCPPacketData(obj5.toStyledString());
			}
		}
	}

	if (stateString == "time")
	{

		if (getServerOwner() == false)
		{
			int weekday = obj["weekday"].asInt();
			int day = obj["day"].asInt();
			int month = obj["month"].asInt();
			int year = obj["year"].asInt();
			int hour = obj["hour"].asInt();
			int minute = obj["minute"].asInt();
			int second = obj["second"].asInt();

			connectionTCP::_weekday = weekday;
			connectionTCP::_day = day;
			connectionTCP::_month = month;
			connectionTCP::_year = year;
			connectionTCP::_hour = hour;
			connectionTCP::_minute = minute;
			connectionTCP::_second = second;

			int monthsPassed = obj["monthsPassed"].asInt();
			int daysPassed = obj["daysPassed"].asInt();

			connectionTCP::monthsPassed = monthsPassed;
			connectionTCP::daysPassed = daysPassed;

			// PRD-J04: verify the host's world checksum piggybacked on this
			// heartbeat (funds + base count + research count). Log-only detect;
			// repair is J10. No-op unless the host stamped a SHARED checksum.
			SharedEcon::verifyWorldChecksum(_game, obj);

		}

		std::string time_speed = obj["time_speed"].asString();
		other_time_speed_coop = time_speed;
		// Persistent copy for the geoscape ally-speed indicator (other_time_speed_coop
		// is cleared every timeAdvance, so it can't drive the UI on its own).
		peerTimeSpeedId = time_speed;
		// A "time" packet is emitted every geoscape think() and carries where on the
		// geoscape the sender is: -1 = normal (ally marker tracks their speed), 0 = an
		// open dogfight window (marker -> Intercept). Navigating to a sub-screen stops
		// these packets, so the last dedicated geo_focus value sticks instead.
		peerFocusScreen = obj.get("geo_focus", -1).asInt();
		// Peer heartbeat (both sides): note when we last heard from the peer on the
		// geoscape. The host's timeAdvance() freezes the shared clock when this goes
		// stale, and both sides dim the ally marker to yellow when it does.
		lastPeerTimePacketMs = SDL_GetTicks();

	}

	if (stateString == "geo_focus")
	{
		// coop: the peer navigated to a geoscape sub-screen (0..5 toolbar index). The
		// ally marker on our geoscape moves to that toolbar button; -1 (back on the
		// geoscape) is restored by the next "time" packet.
		peerFocusScreen = obj["screen"].asInt();
	}

	if (stateString == "research")
	{

		waitedResearch.append(obj);

	}

	if (stateString == "place_facility")
	{
		// PRD-J07: SEPARATE-only mirror markers; SHARED builds ride fac_build.
		if (playerInsideCoopBase == true && !isSharedCampaign())
		{

			_coopFacility.append(obj);

		}

	}

	if (stateString == "dismantle_facility")
	{
		// PRD-J07: SEPARATE-only mirror markers; SHARED rides fac_dismantle.
		if (playerInsideCoopBase == true && !isSharedCampaign())
		{

			_deleteCoopFacility.append(obj);

		}

	}

	// R1-P3: this used to be a run of one-line dividers for medkit/info_box/
	// info_box_ok/explode_items/hit_tile/unit_death/destroy_tile/hit_unit/
	// next_turn - all quarantined battle-sim handlers (inventory-wire-
	// protocol.md sections A-C), deleted along with their blocks.

	// ufo damage
	if (stateString == "ufo_damage")
	{

		if (_game->getSavedGame() && playerInsideCoopBase == false)
		{

			int ufo_id = obj["ufo_id"].asInt();
			int damage = obj["damage"].asInt();

			int status_int = obj["status"].asInt();
			Ufo::UfoStatus status = intToUfostatus(status_int);
			std::string altitude = obj["altitude"].asString();
			bool detected = obj["detected"].asBool();

			int wave = obj["wave"].asInt();
			int crash_id = obj["crash_id"].asInt();
			int land_id = obj["land_id"].asInt();

			std::string craft_rule = obj["craft_rule"].asString();
			int craft_id = obj["craft_id"].asInt();

			bool end = obj["end"].asBool();
			bool survived = obj["survived"].asBool();

			bool minimized = obj["minimized"].asBool();

			for (auto& i_ufo : *_game->getSavedGame()->getUfos())
			{

				if (i_ufo->_coop_ufo_id == ufo_id && i_ufo->_coop == false)
				{

					// damage
					if (damage > i_ufo->lastPlayerUfoDamage)
					{

						int current_damage = i_ufo->getDamage() + (damage - i_ufo->lastPlayerUfoDamage);

						i_ufo->setDamage(current_damage, _game->getMod());

						i_ufo->lastPlayerUfoDamage = damage;

					}

					i_ufo->setStatusCoop(status);
					i_ufo->setAltitudeCoop(altitude);
					i_ufo->setDetectedCoop(detected);
					i_ufo->setDetected(detected);

					i_ufo->setMissionWaveNumber(wave);
					i_ufo->setCrashId(crash_id);
					i_ufo->setLandId(land_id);

					if (i_ufo->originalCoopSpeed == 0)
					{
						i_ufo->originalCoopSpeed = i_ufo->getSpeed();
					}

					if (i_ufo->getSecondsRemaining() <= 0)
					{
						i_ufo->setSecondsRemaining(86400);
					}
	
					if (end == true || minimized == true)
					{
						i_ufo->_playerShotDownUfo = false;
						i_ufo->setSpeed(i_ufo->originalCoopSpeed);
						i_ufo->originalCoopSpeed = 0;
					}
					else if (minimized == false)
					{
						i_ufo->setSpeed(0);
					}

					if (i_ufo->isCrashed())
					{
						i_ufo->_playerShotDownUfo = true;
						i_ufo->setStatusCoop(Ufo::CRASHED);
						i_ufo->setShotDownByCraftId(std::make_pair(craft_rule, craft_id));
					}

					if (i_ufo->isDestroyed() || survived == false)
					{
						i_ufo->_playerShotDownUfo = true;
						i_ufo->setStatusCoop(Ufo::DESTROYED);
						i_ufo->setShotDownByCraftId(std::make_pair(craft_rule, craft_id));
					}

					break;

				}

			}


		}


	}

	if (stateString == "update_graphs")
	{

		if (_game->getSavedGame() && getServerOwner() == false)
		{
			// income
			// countries
			const Json::Value& countries = obj["countries"];

			for (const Json::Value& c : countries)
			{

				const std::string type = c["type"].asString();
				const Json::Value& fundingJson = c["funding"];
				const Json::Value& activityXcomJson = c["activityXcom"];
				const Json::Value& activityAlienJson = c["activityAlien"];

				Country* local = nullptr;
				for (auto* country : *_game->getSavedGame()->getCountries())
				{
					if (country->getRules()->getType() == type)
					{
						local = country;
						break;
					}
				}
				if (!local)
					continue;

				// funding
				auto& fundingVec = local->getFunding();
				fundingVec.clear();
				fundingVec.reserve(fundingJson.size());

				for (const Json::Value& v : fundingJson)
					fundingVec.push_back(v.asInt());

				// activityXcom
				auto& activityXcomVec = local->getActivityXcom();
				activityXcomVec.clear();
				activityXcomVec.reserve(activityXcomJson.size());

				for (const Json::Value& v : activityXcomJson)
					activityXcomVec.push_back(v.asInt());

				// activityAlien
				auto& activityAlienVec = local->getActivityAlien();
				activityAlienVec.clear();
				activityAlienVec.reserve(activityAlienJson.size());

				for (const Json::Value& v : activityAlienJson)
					activityAlienVec.push_back(v.asInt());
			}

			// regions
			const Json::Value& regions = obj["regions"];

			for (const Json::Value& r : regions)
			{

				const std::string type = r["type"].asString();
				const Json::Value& activityXcomJson = r["activityXcom"];
				const Json::Value& activityAlienJson = r["activityAlien"];

				Region* local = nullptr;
				for (auto* region : *_game->getSavedGame()->getRegions())
				{
					if (region->getRules()->getType() == type)
					{
						local = region;
						break;
					}
				}
				if (!local)
					continue;

				// activityXcom
				auto& activityXcomVec = local->getActivityXcom();
				activityXcomVec.clear();
				activityXcomVec.reserve(activityXcomJson.size());

				for (const Json::Value& v : activityXcomJson)
					activityXcomVec.push_back(v.asInt());

				// activityAlien
				auto& activityAlienVec = local->getActivityAlien();
				activityAlienVec.clear();
				activityAlienVec.reserve(activityAlienJson.size());

				for (const Json::Value& v : activityAlienJson)
					activityAlienVec.push_back(v.asInt());
			}
		}

	}

	if (stateString == "graph_requests")
	{

		if (_game->getSavedGame() && playerInsideCoopBase == false && getServerOwner() == true)
		{

			Json::Value root;

			root["state"] = "update_graphs";

			// countries
			Json::Value countries(Json::arrayValue);

			for (auto* country : *_game->getSavedGame()->getCountries())
			{

				Json::Value c;

				c["type"] = country->getRules()->getType();

				Json::Value funding(Json::arrayValue);

				for (int f : country->getFunding())
					funding.append(f);

				c["funding"] = funding;

				// activityXcom
				Json::Value activityXcom(Json::arrayValue);

				for (int x : country->getActivityXcom())
					activityXcom.append(x);

				c["activityXcom"] = activityXcom;

				// activityAlien
				Json::Value activityAlien(Json::arrayValue);

				for (int a : country->getActivityAlien())
					activityAlien.append(a);

				c["activityAlien"] = activityAlien;

				countries.append(c);
			}

			root["countries"] = countries;

			// regions
			Json::Value regions(Json::arrayValue);

			for (auto* region : *_game->getSavedGame()->getRegions())
			{

				Json::Value r;

				r["type"] = region->getRules()->getType();

				// activityXcom
				Json::Value activityXcom(Json::arrayValue);

				for (int x : region->getActivityXcom())
					activityXcom.append(x);

				r["activityXcom"] = activityXcom;

				// activityAlien
				Json::Value activityAlien(Json::arrayValue);

				for (int a : region->getActivityAlien())
					activityAlien.append(a);

				r["activityAlien"] = activityAlien;

				regions.append(r);
			}

			root["regions"] = regions;

			sendTCPPacketData(root.toStyledString());

		}

	}

	if (stateString == "monthly_report")
	{

		// income
		// countries
		 const Json::Value& countries = obj["countries"];

		 for (const Json::Value& c : countries)
		 {

			 const std::string type = c["type"].asString();
			 const Json::Value& fundingJson = c["funding"];
			 const Json::Value& activityXcomJson = c["activityXcom"];
			 const Json::Value& activityAlienJson = c["activityAlien"];

			 Country* local = nullptr;
			 for (auto* country : *_game->getSavedGame()->getCountries())
			 {
				 if (country->getRules()->getType() == type)
				 {
					 local = country;
					 break;
				 }
			 }
			 if (!local)
				 continue;

			 // funding
			 auto& fundingVec = local->getFunding(); 
			 fundingVec.clear();
			 fundingVec.reserve(fundingJson.size());

			 for (const Json::Value& v : fundingJson)
				 fundingVec.push_back(v.asInt());

			 // activityXcom
			 auto& activityXcomVec = local->getActivityXcom();
			 activityXcomVec.clear();
			 activityXcomVec.reserve(activityXcomJson.size());

			 for (const Json::Value& v : activityXcomJson)
				 activityXcomVec.push_back(v.asInt());

			 // activityAlien
			 auto& activityAlienVec = local->getActivityAlien();
			 activityAlienVec.clear();
			 activityAlienVec.reserve(activityAlienJson.size());

			 for (const Json::Value& v : activityAlienJson)
				 activityAlienVec.push_back(v.asInt());

		 }

		 // regions
		 const Json::Value& regions = obj["regions"];

		 for (const Json::Value& r : regions)
		 {

			 const std::string type = r["type"].asString();
			 const Json::Value& activityXcomJson = r["activityXcom"];
			 const Json::Value& activityAlienJson = r["activityAlien"];

			 Region* local = nullptr;
			 for (auto* region : *_game->getSavedGame()->getRegions())
			 {
				 if (region->getRules()->getType() == type)
				 {
					 local = region;
					 break;
				 }
			 }
			 if (!local)
				 continue;

			  // activityXcom
			 auto& activityXcomVec = local->getActivityXcom();
			 activityXcomVec.clear();
			 activityXcomVec.reserve(activityXcomJson.size());

			 for (const Json::Value& v : activityXcomJson)
				 activityXcomVec.push_back(v.asInt());

			 // activityAlien
			 auto& activityAlienVec = local->getActivityAlien();
			 activityAlienVec.clear();
			 activityAlienVec.reserve(activityAlienJson.size());

			 for (const Json::Value& v : activityAlienJson)
				 activityAlienVec.push_back(v.asInt());

		 }

		 // month
		 int month = obj["month"].asInt();
		 _game->getSavedGame()->getTime()->setMonthCoop(month);

		 // year
		 int year = obj["year"].asInt();
		 _game->getSavedGame()->getTime()->setYearCoop(year);

		 int fundingDiff = obj["fundingDiff"].asInt();
		 fundingDiffCoop = fundingDiff;

		 int ratingTotal = obj["ratingTotal"].asInt();
		 ratingTotalCoop = ratingTotal;

		 int lastMonthsRating = obj["lastMonthsRating"].asInt();
		 lastMonthsRatingCoop = lastMonthsRating;

		 // happyList
		const Json::Value& happyList = obj["happyList"];

		 _happyListCoop.clear();
		 if (happyList.isArray())
		 {
			 _happyListCoop.reserve(happyList.size());
			 for (Json::ArrayIndex i = 0; i < happyList.size(); ++i)
			 {
				 if (happyList[i].isString())
					 _happyListCoop.push_back(happyList[i].asString());
			 }
		 }

		 // sadList
		 const Json::Value& sadList = obj["sadList"];

		 _sadListCoop.clear();
		 if (sadList.isArray())
		 {
			 _sadListCoop.reserve(sadList.size());
			 for (Json::ArrayIndex i = 0; i < sadList.size(); ++i)
			 {
				 if (sadList[i].isString())
					 _sadListCoop.push_back(sadList[i].asString());
			 }
		 }

		 // pactList
		 const Json::Value& pactList = obj["pactList"];

		 _pactListCoop.clear();
		 if (pactList.isArray())
		 {
			 _pactListCoop.reserve(pactList.size());
			 for (Json::ArrayIndex i = 0; i < pactList.size(); ++i)
			 {
				 if (pactList[i].isString())
					 _pactListCoop.push_back(pactList[i].asString());
			 }
		 }

		 // cancelPactList
		 const Json::Value& cancelPactList = obj["cancelPactList"];

		 _cancelPactListCoop.clear();
		 if (cancelPactList.isArray())
		 {
			 _cancelPactListCoop.reserve(cancelPactList.size());
			 for (Json::ArrayIndex i = 0; i < cancelPactList.size(); ++i)
			 {
				 if (cancelPactList[i].isString())
					 _cancelPactListCoop.push_back(cancelPactList[i].asString());
			 }
		 }

		// PRD-J04: authoritative monthly settlement (SHARED). Stored here; applied to
		// the replica's tails in time1MonthCoop after its own monthlyFunding roll.
		if (obj.isMember("sharedFunds"))
		{
			sharedMonthlyFunds = obj["sharedFunds"].asInt64();
			sharedMonthlyMaintenance = obj.get("sharedMaintenance", 0).asInt64();
			sharedMonthlyIncome = obj.get("sharedIncome", 0).asInt64();
			sharedMonthlyExpenditure = obj.get("sharedExpenditure", 0).asInt64();
			sharedMonthlyResearchScore = obj.get("sharedResearchScore", 0).asInt();
			sharedMonthlyPending = true;
		}

		_game->getCoopMod()->show_coop_monthly_report = true;

	}

	// PRD-DF01: per-tick dogfight render frames. df_state rides the
	// SNAP_DOGFIGHT conflation slot as a raw top-level message (last-write-
	// wins, freshest-only, never the reliable FIFO), so it is dispatched
	// here by state string. On a replica it fans out to the render-only
	// DogfightState windows (epoch-guarded); the host ignores its own stream.
	if (stateString == "df_state")
	{
		SharedEcon::applyDogfightState(_game, obj);
	}

	// target positions
	if (stateString == "target_positions")
	{

		// PRD-J04: SHARED position snapshot (`shared:true`). The replica is
		// simulation-frozen, so it applies the HOST's real object positions here
		// (matched by REAL id, not a _coop mirror id) so it still SEES crafts/UFOs
		// move. This is the SHARED counterpart of the SEPARATE mirror below; the two
		// are mutually exclusive (SHARED never sends the SEPARATE snapshot and the
		// SEPARATE block is fenced with !isSharedCampaign()).
		if (obj.get("shared", false).asBool() && isSharedReplica() && _game->getSavedGame())
		{
			SavedGame* sg = _game->getSavedGame();

			// crafts: update the matching real craft (base index + craft id).
			auto& jbases = *sg->getBases();
			for (Json::ArrayIndex i = 0; i < obj["crafts"].size(); i++)
			{
				const Json::Value& jc = obj["crafts"][i];
				int baseId = jc["baseId"].asInt();
				int craftId = jc["id"].asInt();
				if (baseId < 0 || baseId >= (int)jbases.size()) continue;
				for (auto* craft : *jbases[baseId]->getCrafts())
				{
					if (craft->getId() == craftId && craft->getRules()->getType() == jc["rule"].asString())
					{
						craft->setLongitude(jc["lon"].asDouble());
						craft->setLatitude(jc["lat"].asDouble());
						craft->setStatus(jc["status"].asString());
						craft->setSpeed(jc["speed"].asInt());
						// PRD-J08: replica-visible craft condition (host-simulated
						// refuel/repair/rearm progress).
						if (jc.isMember("fuel")) craft->setFuel(jc["fuel"].asInt());
						if (jc.isMember("damage")) craft->setDamage(jc["damage"].asInt());
						if (jc.isMember("shield")) craft->setShield(jc["shield"].asInt());
						break;
					}
				}
			}

			// ufos: create-or-update the matching real UFO (by real id). Track the
			// live id set so despawned UFOs can be hidden afterwards.
			std::unordered_set<int> liveUfoIds;
			for (Json::ArrayIndex i = 0; i < obj["ufos"].size(); i++)
			{
				const Json::Value& ju = obj["ufos"][i];
				int ufoId = ju["id"].asInt();
				liveUfoIds.insert(ufoId);
				int missionId = ju["mission_id"].asInt();

				// find/create the owning AlienMission (needed for Ufo::getMission()).
				AlienMission* mission = nullptr;
				for (auto* m : sg->getAlienMissions())
					if (m->getId() == missionId) { mission = m; break; }
				if (!mission)
				{
					const RuleAlienMission* mrule = _game->getMod()->getAlienMission(ju["mission_rule"].asString(), false);
					if (!mrule) continue;
					mission = new AlienMission(*mrule);
					mission->setRace(ju["race"].asString());
					mission->setId(missionId);
					mission->setRegion(ju["region"].asString(), *_game->getMod());
					sg->getAlienMissions().push_back(mission);
				}

				Ufo* ufo = nullptr;
				for (auto* u : *sg->getUfos())
					if (u->getId() == ufoId) { ufo = u; break; }
				if (!ufo)
				{
					RuleUfo* ufoRule = _game->getMod()->getUfo(ju["ufo_rule"].asString(), false);
					if (!ufoRule) continue;
					const UfoTrajectory& traj = *_game->getMod()->getUfoTrajectory(UfoTrajectory::RETALIATION_ASSAULT_RUN, true);
					ufo = new Ufo(ufoRule, ufoId);
					ufo->setMissionInfo(mission, &traj);
					// PRD-J08 fix: the ctor arg is the UNIQUE id; the DISPLAY id
					// (Target::getId(), which every subsequent snapshot and the
					// dogfight lane match by) must be set explicitly - without it
					// the replica re-created an unmatchable id-0 UFO every tick.
					ufo->setId(ufoId);
					sg->getUfos()->push_back(ufo);
				}
				ufo->setLongitude(ju["lon"].asDouble());
				ufo->setLatitude(ju["lat"].asDouble());
				// PRD-J08: adopt hull damage BEFORE status - setDamage derives
				// CRASHED/DESTROYED from thresholds, setStatus then re-asserts
				// the authoritative value.
				if (ju.isMember("damage")) ufo->setDamage(ju["damage"].asInt(), _game->getMod());
				ufo->setStatus(intToUfostatus(ju["status"].asInt()));
				ufo->setDetected(ju["detected"].asBool());
				ufo->setAltitude(ju["altitude"].asString());
				ufo->setSpeed(ju["speed"].asInt());
				// PRD-J08: crash/land marker identity travels by value.
				if (ju.isMember("crashId") && ju["crashId"].asInt() != 0)
					ufo->setCrashId(ju["crashId"].asInt());
				if (ju.isMember("landId") && ju["landId"].asInt() != 0)
					ufo->setLandId(ju["landId"].asInt());
				ufo->setSecondsRemaining(100000000);
			}
			// despawn: hide replica UFOs no longer in the authoritative set (a frozen
			// replica has no dogfights/followers to unwind; full cleanup is J10).
			for (auto* u : *sg->getUfos())
			{
				if (liveUfoIds.find(u->getId()) == liveUfoIds.end())
				{
					u->setDetected(false);
					u->setStatus(Ufo::DESTROYED);
					u->setSecondsRemaining(0);
				}
			}

			// mission sites: create-or-update the matching real site (by real id).
			{
				std::unordered_set<int> liveSiteIds;
				for (Json::ArrayIndex i = 0; i < obj["missions"].size(); i++)
				{
					const Json::Value& jm = obj["missions"][i];
					int siteId = jm["id"].asInt();
					liveSiteIds.insert(siteId);
					MissionSite* site = nullptr;
					for (auto* s : *sg->getMissionSites())
						if (s->getId() == siteId) { site = s; break; }
					if (!site)
					{
						const RuleAlienMission* srule = _game->getMod()->getAlienMission(jm["rules"].asString(), false);
						AlienDeployment* dep = _game->getMod()->getDeployment(jm["deployment"].asString(), false);
						if (!srule || !dep) continue;
						site = new MissionSite(srule, dep, nullptr);
						site->setId(siteId);
						sg->getMissionSites()->push_back(site);
					}
					site->setLongitude(jm["lon"].asDouble());
					site->setLatitude(jm["lat"].asDouble());
					site->setAlienRace(jm["race"].asString());
					site->setCity(jm["city"].asString());
					// issue #78: mirror the host's detection state and fuse instead of
					// forcing detected + pinning an immortal sentinel. The replica sim
					// is frozen, so both are display-only - but they must match what
					// the host actually shows.
					site->setDetected(jm.isMember("detected") ? jm["detected"].asBool() : true);
					site->setSecondsRemaining(jm.isMember("time")
						? (size_t)jm["time"].asUInt64() : (size_t)100000000);
				}
				// issue #78: publish the authoritative id set; sites absent from it are
				// despawned on the main thread (GeoscapeState::think) - the site analog
				// of the UFO despawn above, deferred so no open popup can be holding a
				// dangling MissionSite*.
				{
					std::lock_guard<std::mutex> lk(sharedLiveSiteIdsMutex);
					sharedLiveSiteIds = std::move(liveSiteIds);
					sharedLiveSiteIdsValid = true;
				}
			}
		}

		// PRD-J02: SEPARATE-only peer economy/craft mirror. A SHARED replica already
		// holds every base/craft/fund as real data in the streamed world, so
		// consuming the mirror snapshot would duplicate them. Fence it off.
		if (_game->getSavedGame() && playerInsideCoopBase == false && openMultipleTargetsMenu == false && !isSharedCampaign())
		{

			// funds
			int64_t funds = obj["funds"].asInt64();
			playersFunds = funds;

			// crafts
			int64_t crafts = obj["craft_count"].asInt64();
			playersCrafts = crafts;

			// bases
			int64_t base_count = obj["base_count"].asInt64();
			playersBases = base_count;

			// crafts
			for (int i = 0; i < obj["crafts"].size(); i++)
			{

				int base_id = obj["crafts"][i]["coopbase_id"].asInt();
				int craft_id = obj["crafts"][i]["craft_id"].asInt();
				std::string rule_id = obj["crafts"][i]["rule"].asString();
				std::string status = obj["crafts"][i]["status"].asString();
				double lat = obj["crafts"][i]["lat"].asDouble();
				double lon = obj["crafts"][i]["lon"].asDouble();

				int fuel = obj["crafts"][i]["fuel"].asInt();
				int damage = obj["crafts"][i]["damage"].asInt();

				int speed = obj["crafts"][i]["speed"].asInt();

				// new!
				int shield = obj["crafts"][i]["shield"].asInt();
				int interceptionOrder = obj["crafts"][i]["interceptionOrder"].asInt();
				std::string craft_name = obj["crafts"][i]["craft_name"].asString();
				int num_total_vehicles = obj["crafts"][i]["num_total_vehicles"].asInt();
				int num_total_soldiers = obj["crafts"][i]["num_total_soldiers"].asInt();

				for (auto* base : *_game->getSavedGame()->getBases())
				{

					if (base->_coopIcon == true && base->_coop_base_id == base_id)
					{

						Craft* craft = 0;

						for (auto& i_craft : *base->getCrafts())
						{

							if (i_craft->getId() == craft_id && i_craft->getRules()->getType() == rule_id)
							{
								craft = i_craft;
								break;
							}
						}

						// If no craft is found, create a new one.
						if (!craft)
						{

							RuleCraft* rule = _game->getMod()->getCraft(rule_id, false);

							if (rule)
							{
								craft = new Craft(rule, base, craft_id);

								// weapons
								auto& weapons = *craft->getWeapons();
								const Json::Value& wj = obj["crafts"][i]["weapons"];

								for (auto* cw : weapons)
									delete cw;
								weapons.clear();

								for (Json::ArrayIndex w = 0; w < wj.size(); ++w)
								{
									const std::string type = wj[w]["type"].asString();
									const int ammo = wj[w]["ammo"].asInt();

									if (type != "" && ammo != -1)
									{
										const RuleCraftWeapon* wRule = _game->getMod()->getCraftWeapon(type);
										if (!wRule)
											continue;

										weapons.push_back(new CraftWeapon(const_cast<RuleCraftWeapon*>(wRule), ammo));
									}
									else
									{
										weapons.push_back(0);
									}

								}

								base->getCrafts()->push_back(craft);
							}
							else
							{
								return;
							}
						}

						craft->coop = true;

						craft->setCoopStatus(status);

						craft->setLongitude(lon);
						craft->setLatitude(lat);

						craft->setFuelCoop(fuel);
						craft->setDamage(damage);

						craft->setSpeed(speed);

						// new!
						craft->setShield(shield);
						craft->setInterceptionOrder(interceptionOrder);
						craft->setName(craft_name);
						craft->coop_total_soldiers = num_total_soldiers;
						craft->coop_total_vehicles = num_total_vehicles;

						// returning-state flags (default false so older/partial
						// packets don't throw); drives the correct status display
						craft->setLowFuel(obj["crafts"][i].get("lowFuel", false).asBool());
						craft->setMissionComplete(obj["crafts"][i].get("mission", false).asBool());
						// pre-localized airborne status string from the owner
						craft->setCoopGeoStatus(obj["crafts"][i].get("geoStatus", "").asString());

						// weapons
						auto& weapons = *craft->getWeapons();
						const Json::Value& wj = obj["crafts"][i]["weapons"];

						const Json::ArrayIndex count =
							std::min<Json::ArrayIndex>((Json::ArrayIndex)weapons.size(), wj.size());

						for (Json::ArrayIndex w = 0; w < count; ++w)
						{

							if (weapons[w])
							{

								int ammo = wj[w]["ammo"].asInt();

								if (ammo != -1)
								{
									weapons[w]->setAmmo(ammo);
								}

							}

						}
					}
				}
			}

			// ufos
			for (int i = 0; i < obj["ufos"].size(); i++)
			{

				int mission_id = obj["ufos"][i]["mission_id"].asInt();
				std::string mission_rule_id = obj["ufos"][i]["mission_rule"].asString();
				std::string race = obj["ufos"][i]["race"].asString();
				std::string region = obj["ufos"][i]["region"].asString();

				int ufo_id = obj["ufos"][i]["ufo_id"].asInt();
				std::string ufo_rule_id = obj["ufos"][i]["ufo_rule"].asString();
				int waveNumber = obj["ufos"][i]["wave"].asInt();
				double d_lat = obj["ufos"][i]["lat"].asDouble();
				double d_lon = obj["ufos"][i]["lon"].asDouble();
				int status_int = obj["ufos"][i]["status"].asInt();
				Ufo::UfoStatus status = intToUfostatus(status_int);
				std::string altitude = obj["ufos"][i]["altitude"].asString();
				bool detected = obj["ufos"][i]["detected"].asBool();

				int crash_id = obj["ufos"][i]["crash_id"].asInt();
				int land_id = obj["ufos"][i]["land_id"].asInt();

				int speed = obj["ufos"][i]["speed"].asInt();

				// new!!!
				bool hyperDetected = obj["ufos"][i]["hyperDetected"].asBool();
				int shield = obj["ufos"][i]["shield"].asInt();
				bool isHunterKiller = obj["ufos"][i]["isHunterKiller"].asBool();
				bool isEscort = obj["ufos"][i]["isEscort"].asBool();

				// alien mission
				AlienMission* alien_mission = 0;

				for (auto& i_alien_mission : _game->getSavedGame()->getAlienMissions())
				{

					if (i_alien_mission->getId() == mission_id && i_alien_mission->_coop == true)
					{
						alien_mission = i_alien_mission;
						break;
					}
				}

				if (!alien_mission)
				{

					const RuleAlienMission* alien_mission_rule = _game->getMod()->getAlienMission(mission_rule_id, false);

					if (alien_mission_rule)
					{

						alien_mission = new AlienMission(*alien_mission_rule, true);

						alien_mission->setCoop(true);
						alien_mission->setRace(race);
						alien_mission->setId(mission_id);

						alien_mission->setRegion(region, *_game->getMod());

						_game->getSavedGame()->getAlienMissions().push_back(alien_mission);
					}
					else
					{
						return;
					}
				}

				// ufo
				Ufo* ufo = 0;

				for (auto& i_ufo : *_game->getSavedGame()->getUfos())
				{

					if (i_ufo->_coop_ufo_id == ufo_id && i_ufo->_coop == true)
					{

						ufo = i_ufo;
						break;
					}
				}

				if (!ufo)
				{

					std::string str_ufo_id = "";

					if (waveNumber < 0)
					{
						str_ufo_id = ufo_rule_id;
					}
					else
					{

						const MissionWave& wave = alien_mission->getRules().getWave(waveNumber);
						str_ufo_id = wave.ufoType;
					}

					RuleUfo* ufoRule = _game->getMod()->getUfo(str_ufo_id, false);

					if (ufoRule)
					{

						const UfoTrajectory& assaultTrajectory = *_game->getMod()->getUfoTrajectory(UfoTrajectory::RETALIATION_ASSAULT_RUN, true);

						ufo = new Ufo(ufoRule, ufo_id);

						ufo->setMissionInfo(alien_mission, &assaultTrajectory);
						ufo->getMission()->setId(mission_id);
						ufo->setCoop(true);
						ufo->_coop_ufo_id = ufo_id;

						_game->getSavedGame()->getUfos()->push_back(ufo);
					}
					else
					{
						return;
					}
				}

				ufo->setCoop(true);

				ufo->setLatitude(d_lat);
				ufo->setLongitude(d_lon);

				// new !!!
				ufo->setShield(shield);
				ufo->setHunterKiller(isHunterKiller);
				ufo->setEscort(isEscort);

				if (getCoopGamemode() == 2 && getHost() == false)
				{
					ufo->setDetectedCoop(true);
					ufo->setHyperDetected(true);
				}
				else if (getCoopGamemode() == 3 && getHost() == true)
				{
					ufo->setDetectedCoop(true);
					ufo->setHyperDetected(true);
				}
				else
				{
					ufo->setHyperDetected(hyperDetected);
					ufo->setDetectedCoop(detected);
				}

				ufo->setStatusCoop(status);
				ufo->setAltitudeCoop(altitude);

				ufo->setLandId(land_id);
				ufo->setCrashId(crash_id);

				ufo->setSpeed(speed);

				ufo->setSecondsRemaining(100000000);
			}

			// mission sites
			for (int i = 0; i < obj["missions"].size(); i++)
			{

				std::string str_deployment = obj["missions"][i]["deployment"].asString();
				std::string str_rules = obj["missions"][i]["rules"].asString();
				std::string str_race = obj["missions"][i]["race"].asString();
				std::string str_city = obj["missions"][i]["city"].asString();
				size_t int_time = obj["missions"][i]["time"].asUInt64();
				double d_lon = obj["missions"][i]["lon"].asDouble();
				double d_lat = obj["missions"][i]["lat"].asDouble();
				int mission_id = obj["missions"][i]["mission_id"].asInt();

				MissionSite* missionSite = 0;

				for (auto* i_mission : *_game->getSavedGame()->getMissionSites())
				{

					if (i_mission->_coop_mission_id == mission_id && i_mission->_coop == true)
					{
						missionSite = i_mission;
						break;
					}
				}

				if (!missionSite)
				{
	
					if (str_deployment == "")
					{

						std::vector<std::string> deployments = _game->getMod()->getDeploymentsList();

						// Initialize the random number generator
						std::srand(std::time(nullptr));

						// Select a random index
						int randomIndex = std::rand() % deployments.size();

						// Select a random deployment
						str_deployment = deployments[randomIndex];
					}

					AlienDeployment* deployment = _game->getMod()->getDeployment(str_deployment, true);

					// MISSION SITE
					missionSite = new MissionSite(_game->getMod()->getAlienMission(str_rules, true), deployment, nullptr);
	
					missionSite->_coop_mission_id = mission_id;
					missionSite->setId(_game->getSavedGame()->getId(deployment->getMarkerName()));

					_game->getSavedGame()->getMissionSites()->push_back(missionSite);
				}

				missionSite->setLongitude(d_lon);
				missionSite->setLatitude(d_lat);

				missionSite->setSecondsRemaining(100000000);
				missionSite->setAlienRace(str_race);
				missionSite->setDetected(true);
				missionSite->setCity(str_city);

				missionSite->setCoop(true);
			}

			// alien bases
			for (int i = 0; i < obj["alienbases"].size(); i++)
			{

				int alienbase_id = obj["alienbases"][i]["alienbase_id"].asInt();
				std::string str_deployment = obj["alienbases"][i]["deployment"].asString();
				std::string str_race = obj["alienbases"][i]["race"].asString();
				double d_lon = obj["alienbases"][i]["lon"].asDouble();
				double d_lat = obj["alienbases"][i]["lat"].asDouble();
				std::string pact = obj["alienbases"][i]["pact"].asString();
				bool discovered = obj["alienbases"][i]["discovered"].asBool();
				int start_month = obj["alienbases"][i]["start_month"].asInt();

				AlienBase *alienBase = 0;

				for (auto* i_alienbase : *_game->getSavedGame()->getAlienBases())
				{

					if (i_alienbase->_coop_alienbase_id == alienbase_id && i_alienbase->_coop == true)
					{
						alienBase = i_alienbase;
						break;
					}
				}

				if (!alienBase)
				{
				
					if (str_deployment == "")
					{

						std::vector<std::string> deployments = _game->getMod()->getDeploymentsList();

						// Initialize the random number generator
						std::srand(std::time(nullptr));

						// Select a random index
						int randomIndex = std::rand() % deployments.size();

						// Select a random deployment
						str_deployment = deployments[randomIndex];
					}

					AlienDeployment* deployment = _game->getMod()->getDeployment(str_deployment, true);

					// ALIEN BASE
					alienBase = new AlienBase(deployment, start_month);
						
					alienBase->_coop_alienbase_id = alienbase_id;
					alienBase->setId(_game->getSavedGame()->getId(deployment->getMarkerName()));

					_game->getSavedGame()->getAlienBases()->push_back(alienBase);

				}

				alienBase->setLongitude(d_lon);
				alienBase->setLatitude(d_lat);

				alienBase->setDiscovered(discovered);
				alienBase->setPactCountry(pact);
				alienBase->setAlienRace(str_race);

				alienBase->_coop = true;

			}


			// remove crafts
			std::unordered_set<std::string> keep_craft;
			for (const auto& jc : obj["crafts"])
			{
				int id = jc["craft_id"].asInt();
				// Use the correct JSON field for the rule/type (support two common names)
				std::string rule = jc["rule"].asString();

				keep_craft.insert(std::to_string(id) + "|" + rule);
			}

			// 2) Remove coop crafts whose (id, rule) pair is NOT in the keep set
			for (auto* base : *_game->getSavedGame()->getBases())
			{
				if (!base->_coopIcon)
					continue;

				auto& v = *base->getCrafts(); // std::vector<Craft*>&
				v.erase(std::remove_if(v.begin(), v.end(),
									   [&](Craft* c)
									   {
										   if (!c->coop)
											   return false;

										   int id = c->getId(); // c->_coop_craft_id
										   std::string rule = c->getRules()->getType();

										   bool remove = (keep_craft.find(std::to_string(id) + "|" + rule) == keep_craft.end());
										   if (remove)
											   delete c; // remove this line if you use smart pointers / different ownership
										   return remove;
									   }),
						v.end());
			}

			// remove ufos
			auto& ufos = *_game->getSavedGame()->getUfos();

			// Collect the UFO IDs from JSON that should be KEPT
			std::unordered_set<int> keep_ufo;
			for (const auto& jufo : obj["ufos"])
			{
				keep_ufo.insert(jufo["ufo_id"].asInt());
			}

			// 2) Remove all coop UFOs whose id is NOT in the keep set
			for (auto it = ufos.begin(); it != ufos.end();)
			{
				Ufo* u = *it;
				if (u->_coop && keep_ufo.find(u->_coop_ufo_id) == keep_ufo.end())
				{
					// If SavedGame owns the UFOs, also free memory:
					delete u; // <- omit if someone else owns them (e.g., smart pointers)
					it = ufos.erase(it);
				}
				else
				{
					++it;
				}
			}

			// remove mission sites
			auto& sites = *_game->getSavedGame()->getMissionSites();

			std::unordered_set<int> keep_mission;
			for (const auto& jmission : obj["missions"])
			{
				keep_mission.insert(jmission["mission_id"].asInt());
			}

			// 2) Remove all coop missions whose id is NOT in the keep set
			for (auto it = sites.begin(); it != sites.end();)
			{
				MissionSite* s = *it;
				if (s->_coop && keep_mission.find(s->_coop_mission_id) == keep_mission.end())
				{
					// If SavedGame owns the UFOs, also free memory:
					delete s; // <- omit if someone else owns them (e.g., smart pointers)
					it = sites.erase(it);
				}
				else
				{
					++it;
				}

			}

			// remove alienbases
			auto& alienbases = *_game->getSavedGame()->getAlienBases();

			std::unordered_set<int> keep_alienbase;
			for (const auto& jalienbase : obj["alienbases"])
			{
				keep_alienbase.insert(jalienbase["alienbase_id"].asInt());
			}

			// 2) Remove all coop alienbases whose id is NOT in the keep set
			for (auto it = alienbases.begin(); it != alienbases.end();)
			{
				AlienBase* ab = *it;
				if (ab->_coop && keep_alienbase.find(ab->_coop_alienbase_id) == keep_alienbase.end())
				{
					// If SavedGame owns the UFOs, also free memory:
					delete ab; // <- omit if someone else owns them (e.g., smart pointers)
					it = alienbases.erase(it);
				}
				else
				{
					++it;
				}
			}

			// coop (issue #28): the coop UFO / mission-site mirrors have just been
			// (re)synced above. Rebind any reloaded own craft whose shared
			// destination was stripped from its world blob back to the live mirror
			// (by cross-instance coop id), so it keeps chasing the REAL target
			// instead of the interim waypoint at the stale saved position.
			for (auto* base : *_game->getSavedGame()->getBases())
			{
				for (auto* craft : *base->getCrafts())
				{
					if (!craft->coop)
						craft->relinkCoopDestination(_game->getSavedGame());
				}
			}

		}



	}

	// BATTLESCAPE
	// new map packet ready to be loaded
	if (stateString == "WAIT_MAP_SENDER")
	{
		isWaitMap = true;
	}

	if (stateString == "close_save_progress")
	{

		// Closing save progress popup - only if one is actually open (silent
		// background pushes don't show the dialog; popping the screen under
		// it would tear down the geoscape). The campaign wait dialogs
		// (60/62/64/65) manage their own lifetime - never pop those.
		if (!_game->getStates().empty())
		{
			CoopState* top = dynamic_cast<CoopState*>(_game->getStates().back());
			if (top && !top->isCampaignWaitDialog())
			{
				_game->popState();
			}
		}

	}

	if (stateString == "MAP_RESULT_LOAD_PROGRESS")
	{

		writeHostMapLoadProgressFile();

		_isLoadProgress = true;

		CoopState* coop = new CoopState(555);
		coop->loadWorld();

	}

	if (stateString == "close_load_progress" && getServerOwner() == true)
	{

		// P2/F1: a battle resume parks the host behind its resume lobby/wait
		// dialogs - resumeCampaign() closes the lobby but leaves the HostMenu
		// beneath the COOP_DLG_WAIT_PLAYERS it pushed, and on the battle path
		// the host never gets a resumeAck (it emits campaign_resume_battle
		// instead), so nothing ever pops them. The client has now finished
		// loading the streamed battle (this packet), so return the host to its
		// own BattlescapeState: pop everything above it so BattlescapeState::
		// think() runs and re-arms the coop-init block (_battleInit / role /
		// turn) once COOP_READY sets coopSession below. Gate strictly on the
		// player-wait dialog actually being on the stack so this fires ONLY
		// on a resume, never on a LIVE battle entry - there the host stacks
		// Briefing/Inventory over a fresh battle and also receives
		// close_load_progress, and popping those would eat the briefing.
		//
		// issue #93: NOT for a skirmish rejoin. There the player-wait dialog is
		// the live reconnect dialog the host is frozen behind: the ack that just
		// arrived flips it to "All players connected" / RESUME, and the host's own
		// RESUME click is what releases both machines (the rejoiner is holding for
		// exactly that broadcast). Popping it here would resume the host silently
		// and strand the client on its hold. The campaign resume keeps the pop -
		// its host already clicked RESUME back in the lobby.
		bool inBattleResume = false;
		if (_game->getSavedGame() && _game->getSavedGame()->getSavedBattle() != nullptr
			&& _game->getCoopMod()->getCoopCampaign() == true)
		{
			for (auto* st : _game->getStates())
			{
				CoopState* cs = dynamic_cast<CoopState*>(st);
				if (cs && cs->getStateCode() == COOP_DLG_WAIT_PLAYERS)
				{
					inBattleResume = true;
					break;
				}
			}
		}
		if (inBattleResume)
		{
			int guard = 0;
			while (guard++ < 32 && _game->getStates().size() > 1
				&& dynamic_cast<BattlescapeState*>(_game->getStates().back()) == nullptr)
			{
				_game->popState();
			}
		}

		Json::Value root;
		root["state"] = "COOP_READY_CLIENT_REQUEST"; 

		sendTCPPacketData(root.toStyledString());

	}

	if (stateString == "MAP_RESULT_SAVE_PROGRESS")
	{

		std::string jsonData333 = "{\"state\" : \"close_save_progress\"}";
		sendTCPPacketData(jsonData333);

		// Closing save progress popup - only if one is actually open (silent
		// background pushes don't show the dialog). The campaign wait dialogs
		// (60/62/64/65) manage their own lifetime - never pop those.
		if (!_game->getStates().empty())
		{
			CoopState* top = dynamic_cast<CoopState*>(_game->getStates().back());
			if (top && !top->isCampaignWaitDialog())
			{
				_game->popState();
			}
		}

		// WRITE THE FILE RECEIVED FROM THE CLIENT TO THE HOST
		if (_game->getSavedGame())
		{
			// Install the freshest client blob. On validation failure (PRD-07)
			// the store keeps the last-good blob, so the write below stays safe.
			writeHostMapSaveProgressFile();

			// PRD-06/E1: the SaveGameState funnel deferred its write to here, so
			// this is the single emit of the host .sav for this save cycle - and
			// it embeds the client world that just arrived. (No longer gated on
			// the blob being fresh: even a rejected blob leaves a valid last-good
			// one to embed, and the user asked for a save.)
			writePendingHostSave();
		}

	}

	// LOAD MAP
	if (stateString == "map_result_data")
	{
		try
		{

			if (obj.isMember("data") && obj["data"].isString())
			{
				std::string map_data = obj["data"].asString();
				mapData += map_data;

				std::string jsonData2 = "{\"state\" : \"WAIT_MAP_SENDER\"}";
				sendTCPPacketData(jsonData2);

				// R4-P1 (SS2.7): if a battle-handshake blob transfer is in
				// flight (CoopHandshake::onOffer() armed it after sending
				// battle_accept), check whether the accumulated bytes now
				// cover the offered blobBytes - a no-op otherwise. The
				// quarantined MAP_RESULT_HOST/MAP_RESULT_CLIENT terminal
				// markers this carrier used to end on are never relied on
				// here (SS2.7's blobBytes field is the completion signal).
				CoopHandshake::onBlobChunkAppended(_game);
			}
			else
			{
				DebugLog("Error: obj missing 'data' or it is not a string.\n");
			}
		}
		catch (const std::exception& e)
		{
			// Build one message for both DebugLog and crash.log
			std::string msg = "Exception in map loading: " + std::string(e.what());

			DebugLog((msg + "\n").c_str());

			// Write separate crash log file to user/logs/...
			CRASH_LOG(msg);
		}
		catch (...)
		{
			std::string msg = "Unknown exception in map loading.";

			DebugLog((msg + "\n").c_str());
			CRASH_LOG(msg);
		}
	}

	if (stateString == "COOP_READY_SAVE_PROGRESS" && onTcpHost == false)
	{

		// MODS
		std::string str_hash;
		for (Json::Value host_mod : obj["mods"])
		{

			std::string host_mod_name = host_mod["name"].asString();

			str_hash += host_mod_name + ";";
		}

		if (!_game->getCoopMod()->hasRequiredMods(str_hash))
		{

			_game->getCoopMod()->disconnectTCP();

			// refused for a mod mismatch: the attempt is over
			closeConnectingDialog();

			_game->pushState(new ModCheckMenu(str_hash));

			return;
		}

		long long saveID = obj["saveID"].asInt64();
		connectionTCP::saveID = saveID;

		tcpPlayerName = obj.get("playername", tcpPlayerName).asString();

		// campaign lobby (new or resume): sit in the lobby until the host
		// clicks START/RESUME CAMPAIGN (flow-redesign F2/F3). A mid-session
		// rejoin (F4) fetches its world straight away; otherwise the classic
		// path (Profile -> request_load_progress).
		bool campaignStarted = obj.get("campaign_started", true).asBool();
		bool rejoin = obj.get("rejoin", false).asBool();
		// PRD-J01: remember the lobby's economy model for the type label (the
		// client has no save yet; the real adoption happens at campaign_start).
		connectionTCP::_lobbyCampaignType = obj.get("campaignType", 0).asInt();

		// Pop the "Connecting..." wait dialog NOW, before pushing the lobby/load
		// dialog over it. forceCloseCoopStateMenu can't reach it once buried (a
		// non-top state gets no think() tick, and LobbyMenu's ctor clears the
		// flag anyway), so it would linger and resurface as a stale
		// "Connecting..." window when the client later leaves the lobby.
		closeConnectingDialog();

		// Every successful join confirms itself with the "You have joined
		// <host>'s game" popup, on top of whatever the join leads to (lobby or
		// load-wait). It used to be suppressed entirely for campaign lobbies.
		if (!campaignStarted)
		{
			connectionTCP::session.lobbyMode = obj.get("lobby_mode", 1).asInt();
			connectionTCP::forceCloseCoopStateMenu = true;
			connectionTCP::forceClosePasswordCheckMenu = true;
			_game->pushState(new LobbyMenu());
			_game->pushState(new Profile);
		}
		else if (rejoin)
		{
			connectionTCP::session.lobbyMode = obj.get("lobby_mode", 0).asInt();
			connectionTCP::forceCloseCoopStateMenu = true;
			connectionTCP::forceClosePasswordCheckMenu = true;

			// issue #93: a mode-0 rejoin means the host has a SKIRMISH battle
			// running and is about to stream it. Remember that, because the blob
			// arrives under the same key as a first mission and only a rejoin owes
			// the host a resume_ack (and owes itself a hold until RESUME).
			connectionTCP::session.skirmishRejoinPending =
				(connectionTCP::session.lobbyMode == 0);
			if (connectionTCP::session.skirmishRejoinPending)
			{
				// dropping into a battle already in progress: no pre-battle
				// equip screen (same call the campaign battle rejoin makes
				// before asking for the battle stream).
				_game->getCoopMod()->inventory_battle_window = false;
			}

			_game->pushState(new CoopState(COOP_DLG_CLIENT_LOAD_WAIT));

			Json::Value req;
			req["state"] = "request_load_progress";
			sendTCPPacketData(req.toStyledString());

			_game->pushState(new Profile);
		}
		else
		{
			_game->pushState(new Profile);
		}

	}

	if (stateString == "COOP_READY_CLIENT_REQUEST" && onTcpHost == false)
	{

		Json::Value root;
		root["state"] = "COOP_READY_CLIENT";
		sendTCPPacketData(root.toStyledString());

	}

	if (stateString == "COOP_READY_CLIENT_REQUEST_PROFILE" && onTcpHost == false)
	{

		// MODS
		std::string str_hash;
		for (Json::Value host_mod : obj["mods"])
		{

			std::string host_mod_name = host_mod["name"].asString();

			str_hash += host_mod_name + ";";
		}

		if (!_game->getCoopMod()->hasRequiredMods(str_hash))
		{

			_game->getCoopMod()->disconnectTCP();

			// refused for a mod mismatch: the attempt is over
			closeConnectingDialog();

			_game->pushState(new ModCheckMenu(str_hash));

			return;
		}

		connectionTCP::forceCloseCoopStateMenu = true;
		connectionTCP::forceClosePasswordCheckMenu = true;

		tcpPlayerName = obj.get("playername", tcpPlayerName).asString();

		// joined: retire "Connecting..." before the popup covers it (the
		// flag above only fires while the dialog is still the top state)
		closeConnectingDialog();

		_game->pushState(new Profile);

		Json::Value root;
		root["state"] = "COOP_READY_CLIENT";
		sendTCPPacketData(root.toStyledString());

	}

	if (stateString == "INIT_SERVER" && onTcpHost == true)
	{

		// This runs once...
		if (onceTime == false)
		{

			fixCoopSave();

			j_markers = "";

			_battleInit = false;

			// RESET ALL SOLDIERS OUT OF THE BASES
			for (auto* base : *_game->getSavedGame()->getBases())
			{
				for (auto* soldier : *base->getSoldiers())
				{

					if (soldier->getCraft())
					{
						// if co-op soldiers exceed 50%
						if (soldier->getCraft()->getSpaceAvailable() < 0)
						{
							soldier->setCraftAndMoveEquipment(0, base, _game->getSavedGame()->getMonthsPassed() == -1);
						}
					}
				}
			}

			onceTime = true;

		}

		std::string playername = obj.get("playername", "defaultState").asString();
		std::string servername = obj.get("servername", "defaultState").asString();

		// A joiner may never take a name already in use in this session -
		// the host's own name, or any currently attached client's. (The
		// host's name passes the roster check below and would collapse both
		// players into one identity; a DROPPED client's name stays available
		// on purpose - that is how a rejoin identifies itself. With today's
		// single-client transport the attached-client case is preempted by
		// the server-full close, but the check is written for N clients.)
		bool nameInUse = (playername == _game->getCoopMod()->getHostName());
		if (connectionTCP::session.clientInLobby
			&& playername == _game->getCoopMod()->getCurrentClientName())
		{
			nameInUse = true;
		}
		if (nameInUse)
		{
			Json::Value refuse;
			refuse["state"] = "lobby_join_refused";
			refuse["reason"] = "That player name is already in use.";
			sendTCPPacketData(refuse.toStyledString());
			return;
		}

		// Campaign roster gate (flow-redesign D4/D6): once the player list is
		// locked (non-empty), only registered names may connect - covers the
		// resume lobby, mid-session rejoin, and strangers joining a running
		// campaign. An empty list = pre-START lobby, anyone may join.
		if (_game->getCoopMod()->getCoopCampaign() == true
			&& _game->getSavedGame()
			&& _game->getSavedGame()->isCoopSave())
		{
			const auto& registered = _game->getSavedGame()->getCoopPlayers();
			if (!registered.empty())
			{
				bool known = false;
				for (const auto& p : registered)
				{
					if (p == playername)
					{
						known = true;
					}
				}
				if (!known)
				{
					Json::Value refuse;
					refuse["state"] = "lobby_join_refused";
					refuse["reason"] = "You are not a player in this campaign.";
					sendTCPPacketData(refuse.toStyledString());
					return;
				}
			}
		}

		tcpPlayerName = playername;
		tcpServerName = servername;

		Json::Value root;

		// mod check
		std::vector<std::string> mod_names = _game->getMod()->getCoopModList();

		int index = 0;

		for (auto mod_name : mod_names)
		{

			root["mods"][index]["name"] = mod_name;

			index++;
		}

		// password
		if (connectionTCP::isPasswordRequired == true && !OpenXcom::isConnectionUDPActive())
		{

			std::string tcp_password = obj.get("tcp_password", "").asString();

			if (tcp_password != connectionTCP::password)
			{

				Json::Value rootPassword;
				rootPassword["state"] = "tcp_password";

				sendTCPPacketData(rootPassword.toStyledString());

				return;

			}

		}

		// past every gate: a real client is now attached to the session
		connectionTCP::session.clientAttached();

		// issue #93: a joiner arriving while a SKIRMISH battle is already running is
		// a rejoin into that battle, not a new lobby guest. The skirmish lobby has
		// nothing left to offer (the battle started; its BATTLE SETTINGS button is
		// gone) and the host is frozen behind the reconnect dialog waiting for
		// exactly this. Route it down the campaign rejoin road - the world stream
		// and the resume_ack that releases the freeze are mode-agnostic.
		const bool skirmishBattleRejoin = _game->getCoopMod()->getCoopCampaign() == false
			&& coopBattleLive(_game);

		if (_game->getCoopMod()->getCoopCampaign() == true || skirmishBattleRejoin)
		{
			root["state"] = "COOP_READY_SAVE_PROGRESS";
			// Kept on the wire for older clients; host-save authority is the only mode.
			root["host_save_progress"] = true;
			// campaign lobbies (new or resume): the client joins the lobby
			// instead of requesting a world (flow-redesign F2/F3). A live
			// session (lobby closed) = mid-session rejoin: fetch directly.
			root["campaign_started"] = skirmishBattleRejoin
				|| (connectionTCP::session.lobbyMode == 0 || connectionTCP::session.lobbyClosed == true);
			root["rejoin"] = skirmishBattleRejoin
				|| (connectionTCP::session.lobbyMode != 0 && connectionTCP::session.lobbyClosed == true);
			root["lobby_mode"] = connectionTCP::session.lobbyMode;
			// PRD-J01: tell the joining client the campaign economy model now,
			// before its save exists, so the lobby type label can render.
			root["campaignType"] = _game->getSavedGame()
				? static_cast<int>(_game->getSavedGame()->getCampaignType()) : 0;

			// Handshake fallback only: a resume carries the loaded saveID (nonzero,
			// so skipped here) and a new campaign re-mints in startCampaign and
			// re-broadcasts via campaign_start (which the client adopts). This
			// mint just guarantees the join reply never sends 0 when a client
			// connects before START CAMPAIGN is clicked.
			if (connectionTCP::saveID == 0)
			{
				connectionTCP::saveID = getDateTimeCoop();
			}

			// saveID
			root["saveID"] = static_cast<Json::Int64>(connectionTCP::saveID);
		}
		else
		{
			root["state"] = "COOP_READY_CLIENT_REQUEST_PROFILE";
		}

		root["playername"] = sendTcpPlayer;
		root["servername"] = sendTcpServerName;

		sendTCPPacketData(root.toStyledString());

		// "<player> has joined the game" - shown for every lobby mode. The
		// host's lobby is already open at this point, so this lands on top of
		// it; campaign lobbies used to suppress the popup entirely.
		_game->pushState(new Profile);

	}

	if (stateString == "COOP_READY_CLIENT" && onTcpHost == true)
	{

		coopSession = true;

		Json::Value root;
		root["state"] = "COOP_READY_HOST";
		root["playername"] = sendTcpPlayer; // Client player ID will be added later...
		root["servername"] = sendTcpServerName; // Client player ID will be added later...
		root["gamemode"] = connectionTCP::_coopGamemode;

		// funds
		int64_t funds = 0;
		if (_game->getSavedGame() && _game->getSavedGame()->getFunds())
		{
			funds = _game->getSavedGame()->getFunds();
		}
		root["funds"] = funds;

		int64_t base_count = 0;
		int64_t craft_count = 0;
		if (_game->getSavedGame() && _game->getSavedGame()->getBases())
		{
			for (auto& base : *_game->getSavedGame()->getBases())
			{
				if (base->_coopBase == false)
				{

					for (auto& craft : *base->getCrafts())
					{
						craft_count++;
					}

					base_count++;
				}
			}
		}

		root["base_count"] = base_count;
		root["craft_count"] = craft_count;

		// is session locked?
		root["isCoopSessionLocked"] = connectionTCP::session.sessionLocked;
		root["customBattleCraftLocked"] = connectionTCP::session.customBattleCraftLocked;
		root["customBattleCraftId"] = connectionTCP::session.customBattleCraftId;
		root["isPlayerReady"] = connectionTCP::isPlayerReady;
		if (connectionTCP::isPlayerReady == true && connectionTCP::isPlayersReady == true && connectionTCP::session.sessionLocked == false)
		{
			connectionTCP::session.campaignStarted();
		}

		// research option
		_enable_research_sync = Options::EnableResearchSync;
		root["enable_research_sync"] = _enable_research_sync;

		// time option
		connectionTCP::_enable_time_sync = Options::EnableTimeSync;
		root["enable_time_sync"] = connectionTCP::_enable_time_sync;

		// reaction shoot option (PVP)
		if (getCoopGamemode() == 2 || getCoopGamemode() == 3)
		{
			connectionTCP::_enable_reaction_shoot = Options::EnableReactionFirePvp;
		}

		// reaction shoot
		root["enable_reaction_shoot"] = connectionTCP::_enable_reaction_shoot;

		// other player footsteps sounds
		connectionTCP::_enable_other_player_footsteps = Options::EnableOtherPlayerFootsteps;
		root["enable_other_player_footsteps"] = connectionTCP::_enable_other_player_footsteps;

		// enable host only time speed
		connectionTCP::_enable_host_only_time_speed = Options::EnableHostOnlyTimeSpeed;
		root["enable_host_only_time_speed"] = connectionTCP::_enable_host_only_time_speed;

		// enable XcomEquipmentAliensPVP
		connectionTCP::_enable_xcom_equipment_aliens_pvp = Options::EnableXcomEquipmentAliensPVP;
		root["enable_xcom_equipment_aliens_pvp"] = _enable_xcom_equipment_aliens_pvp;

		// UnbalancedCraftSoldiersLimit
		connectionTCP::_unbalanced_craft_soldiers_limit = Options::UnbalancedCraftSoldiersLimit;
		root["unbalanced_craft_soldiers_limit"] = _unbalanced_craft_soldiers_limit;

		// campaing check
		root["coop_campaign"] = _coopCampaign;

		// battle  check
		bool inBattle = false;

		if (_game->getSavedGame()->getSavedBattle())
		{
			if (_game->getSavedGame()->getSavedBattle()->getBattleGame())
			{
				inBattle = true;
			}
		}

		if (inBattle == false)
		{
			CoopState* coop = new CoopState(777);
			coop->loadWorld();
		}

		root["battle"] = inBattle;

		sendTCPPacketData(root.toStyledString());

	}

	if (stateString == "COOP_READY_HOST" && onTcpHost == false)
	{

		coopSession = true;

		fixCoopSave();

		// coop fix bases..
		j_markers = "";

		_battleInit = false;

		if (onceTime == true)
		{
			return;
		}

		onceTime = true;

		// is session locked? (value-carrying: mirror the host's flag from the
		// wire, then lock if both are ready) - the raw mirror stays; the derived
		// lock funnels through the transition.
		connectionTCP::session.sessionLocked = obj["isCoopSessionLocked"].asBool();
		if (obj.get("customBattleCraftLocked", false).asBool())
		{
			const int craftId = obj.get("customBattleCraftId", -1).asInt();
			if (craftId >= 0)
			{
				connectionTCP::session.lockCustomBattleCraft(craftId);
				_coop_selected_craft_id = static_cast<std::size_t>(craftId);
			}
		}
		connectionTCP::isPlayersReady = obj["isPlayerReady"].asBool();
		if (connectionTCP::isPlayerReady == true && connectionTCP::isPlayersReady == true && connectionTCP::session.sessionLocked == false)
		{
			connectionTCP::session.campaignStarted();
		}

		// set current gamemode
		connectionTCP::_coopGamemode = obj["gamemode"].asInt();

		// funds
		int64_t funds = obj["funds"].asInt64();
		playersFunds = funds;

		// crafts
		int64_t crafts = obj["craft_count"].asInt64();
		playersCrafts = crafts;

		// bases
		int64_t base_count = obj["base_count"].asInt64();
		playersBases = base_count;

		// campaign check
		bool host_coop_campaign = obj["coop_campaign"].asBool();
		bool client_coop_campaign = _coopCampaign;

		if (host_coop_campaign != client_coop_campaign)
		{

			// if campaign: nothing to do - the client's world comes from the
			// host (new_game or streamed progress)
			// if new battle
			if (host_coop_campaign == false)
			{
				_game->pushState(new CoopState(3000));

				return;

			}

		}

		// mod check
		std::vector<std::string> client_mod_names = _game->getMod()->getCoopModList();

		bool mod_found = false;
		int client_mod_count = client_mod_names.size();
		int host_mod_count = obj["mods_count"].asInt();

		// research option
		bool enable_research_sync = obj["enable_research_sync"].asBool();
		_enable_research_sync = enable_research_sync;

		// time option
		bool enable_time_sync = obj["enable_time_sync"].asBool();
		connectionTCP::_enable_time_sync = enable_time_sync;

		// reaction shoot option
		bool enable_reaction_shoot = obj["enable_reaction_shoot"].asBool();
		connectionTCP::_enable_reaction_shoot = enable_reaction_shoot;

		// other player footsteps sounds
		bool enable_other_player_footsteps = obj["enable_other_player_footsteps"].asBool();
		connectionTCP::_enable_other_player_footsteps = enable_other_player_footsteps;

		// enable host only time speed
		bool enable_host_only_time_speed = obj["enable_host_only_time_speed"].asBool();
		connectionTCP::_enable_host_only_time_speed = enable_host_only_time_speed;

		// enable XcomEquipmentAliensPVP
		bool enable_xcom_equipment_aliens_pvp = obj["enable_xcom_equipment_aliens_pvp"].asBool();
		connectionTCP::_enable_xcom_equipment_aliens_pvp = enable_xcom_equipment_aliens_pvp;

		// UnbalancedCraftSoldiersLimit
		bool unbalanced_craft_soldiers_limit = obj["unbalanced_craft_soldiers_limit"].asBool();
		connectionTCP::_unbalanced_craft_soldiers_limit = unbalanced_craft_soldiers_limit;

		// CHECK IF THE CLIENT IS IN BATTLE; IF SO, INCLUDE THE HOST, OTHERWISE DO NOTHING
		// IF BOTH ARE IN BATTLE AT THE SAME TIME, CREATE A SEPARATE SESSION
		bool clientInBattle = false;

		if (_game->getSavedGame()->getSavedBattle())
		{
			if (_game->getSavedGame()->getSavedBattle()->getBattleGame())
			{
				clientInBattle = true;
			}
		}

		std::string playername = obj.get("playername", "defaultState").asString();
		std::string servername = obj.get("servername", "defaultState").asString();

		bool inBattle = obj["battle"].asBool();

		tcpPlayerName = playername;
		tcpServerName = servername;

		if (clientInBattle == false)
		{
			CoopState* coop = new CoopState(777);
			coop->loadWorld();
		}

		initProfile(clientInBattle, inBattle);

		// if neither the client nor the host is in battle, then create base icons

		// BASE
		Json::Value markers;

		markers["state"] = "coopBase";
		markers["battle"] = inBattle;

		// funds
		int64_t funds2 = 0;
		if (_game->getSavedGame() && _game->getSavedGame()->getFunds())
		{
			funds2 = _game->getSavedGame()->getFunds();
		}
		markers["funds"] = funds2;

		// crafts
		int64_t base_count2 = 0;
		int64_t craft_count2 = 0;
		if (_game->getSavedGame() && _game->getSavedGame()->getBases())
		{
			for (auto &base : *_game->getSavedGame()->getBases())
			{
				if (base->_coopBase == false)
				{

					for (auto &craft : *base->getCrafts())
					{
						craft_count2++;
					}

					base_count2++;
				}
			}
		}

		markers["base_count"] = base_count2;
		markers["craft_count"] = craft_count2;

		if (connectionTCP::no_bases == false)
		{

			int index = 0;
			for (auto base : *_game->getSavedGame()->getBases())
			{

				if (base->_coopBase == false && base->_coopIcon == false && (base->getLatitude() != 0 || base->getLongitude() != 0))
				{

					markers["markers"][index]["coopbaseid"] = base->_coop_base_id;

					markers["markers"][index]["base"] = base->getName().c_str();
					markers["markers"][index]["lon"] = base->getLongitude();
					markers["markers"][index]["lan"] = base->getLatitude();

					// new!!!

					// new!!!
					// Facilities synchronization
					// facilities
					int facilities_index = 0;
					double tr_coop = 0;
					double radar_range_coop = 0;
					int completedFacilities = 0;
					int mindShields = 0;
					for (const auto* fac : *base->getFacilities())
					{
						if (fac->getBuildTime() != 0)
						{
							continue;
						}

						if (fac->getRules())
						{
							if (fac->getBuildTime() == 0)
							{
								tr_coop = fac->getRules()->getRadarRange();
								if (tr_coop < 10000 && tr_coop > radar_range_coop)
									radar_range_coop = tr_coop;

								if (_game->getCoopMod()->getServerOwner() == false)
								{
									completedFacilities = fac->getRules()->getSizeX() * fac->getRules()->getSizeY();
									if (fac->getRules()->isMindShield() && !fac->getDisabled())
									{
										mindShields = fac->getRules()->getMindShieldPower();
									}

									markers["markers"][index]["facilities"][facilities_index]["radar_chance_coop"] = fac->getRules()->getRadarChance();
									markers["markers"][index]["facilities"][facilities_index]["hyperwave_coop"] = fac->getRules()->isHyperwave();
									markers["markers"][index]["facilities"][facilities_index]["radar_range_coop"] = fac->getRules()->getRadarRange();
									markers["markers"][index]["facilities"][facilities_index]["completedFacilities"] = completedFacilities;
									markers["markers"][index]["facilities"][facilities_index]["mindShields"] = mindShields;

									facilities_index++;
								}
							}
						}
					}

					markers["markers"][index]["radar_range_coop"] = radar_range_coop;

					markers["markers"][index]["getAvailableEngineers"] = base->getAvailableEngineers();
					markers["markers"][index]["getAvailableHangars"] = base->getAvailableHangars();
					markers["markers"][index]["getAvailableLaboratories"] = base->getAvailableLaboratories();
					markers["markers"][index]["getAvailableQuarters"] = base->getAvailableQuarters();
					markers["markers"][index]["getAvailableScientists"] = base->getAvailableScientists();
					markers["markers"][index]["getAvailableSoldiers"] = base->getAvailableSoldiers();
					markers["markers"][index]["getAvailableStores"] = base->getAvailableStores();
					markers["markers"][index]["getAvailableTraining"] = base->getAvailableTraining();
					markers["markers"][index]["getAvailableWorkshops"] = base->getAvailableWorkshops();

					index++;
				}
			}

		}

		sendTCPPacketData(markers.toStyledString());

		// RESET ALL SOLDIERS OUT OF THE BASES(HAPPENS ONCE IN AN ERROR SITUATION)
		for (auto* base : *_game->getSavedGame()->getBases())
		{
			for (auto* soldier : *base->getSoldiers())
			{

				if (soldier->getCraft())
				{
					// if co-op soldiers exceed 50%
					if (soldier->getCraft()->getSpaceAvailable() < 0)
					{
						soldier->setCraftAndMoveEquipment(0, base, _game->getSavedGame()->getMonthsPassed() == -1);
					}
				}
			}
		}
	}

	// COOP BASE HOST
	if (stateString == "coopBase" && onTcpHost == true)
	{

		// PRD-J02: SEPARATE-only mirror-base machinery (creates _coopIcon peer
		// bases). SHARED has one shared world with real bases - never mirror.
		if (isSharedCampaign())
		{
			return;
		}

		bool inBattle = obj["battle"].asBool();

		// funds
		int64_t funds = obj["funds"].asInt64();
		playersFunds = funds;

		// crafts
		int64_t crafts = obj["crafts"].asInt64();
		playersCrafts = crafts;

		// show host profile
		initProfile(false, inBattle);

		Json::Value m_markers;
		Json::Reader reader;

		if (j_markers.empty())
		{

			j_markers = obj["markers"].toStyledString();
		}

		reader.parse(j_markers, m_markers);

		for (Json::Value marker : m_markers)
		{

			std::string s_lon = marker["lon"].asString();
			std::string s_lan = marker["lan"].asString();

			int coopbaseid = marker["coopbaseid"].asInt();

			int getAvailableEngineers = marker["getAvailableEngineers"].asInt();
			int getAvailableHangars = marker["getAvailableHangars"].asInt();
			int getAvailableLaboratories = marker["getAvailableLaboratories"].asInt();
			int getAvailableQuarters = marker["getAvailableQuarters"].asInt();
			int getAvailableScientists = marker["getAvailableScientists"].asInt();
			int getAvailableSoldiers = marker["getAvailableSoldiers"].asInt();
			int getAvailableStores = marker["getAvailableStores"].asInt();
			int getAvailableTraining = marker["getAvailableTraining"].asInt();
			int getAvailableWorkshops = marker["getAvailableWorkshops"].asInt();
			
			double lon = std::stod(s_lon);
			double lan = std::stod(s_lan);

			Base* CoopBase = new Base(_game->getMod());

			CoopBase->setEngineers(getAvailableEngineers);
			CoopBase->coop_hangar = getAvailableHangars;
			CoopBase->coop_laboratory = getAvailableLaboratories;
			CoopBase->coop_quarters = getAvailableQuarters;
			CoopBase->coop_soldiers = getAvailableSoldiers;
			CoopBase->coop_stores = getAvailableStores;
			CoopBase->coop_training = getAvailableTraining;
			CoopBase->coop_workshop = getAvailableWorkshops;
			CoopBase->setScientists(getAvailableScientists);

			CoopBase->_coop_base_id = coopbaseid;

			// new!!!
			CoopBase->_facilitiesCoop = marker["facilities"];
			double radar_range_coop = marker["radar_range_coop"].asDouble();
			CoopBase->_radar_range_coop = radar_range_coop;

			std::string base_name = marker["base"].asString();
			CoopBase->setName(base_name);

			CoopBase->isCoopBase(true);
			CoopBase->_coopIcon = true;

			CoopBase->setLongitude(lon);
			CoopBase->setLatitude(lan);

			_game->getSavedGame()->getBases()->push_back(CoopBase);
		}

		// HOST
		Json::Value markers;

		markers["state"] = "coopBase2";
		markers["gamemode"] = connectionTCP::_coopGamemode;

		int index = 0;
		for (auto base : *_game->getSavedGame()->getBases())
		{

			if (base->_coopBase == false && base->_coopIcon == false && (base->getLatitude() != 0 || base->getLongitude() != 0))
			{

				markers["markers"][index]["coopbaseid"] = base->_coop_base_id;

				markers["markers"][index]["base"] = base->getName().c_str();
				markers["markers"][index]["lon"] = base->getLongitude();
				markers["markers"][index]["lan"] = base->getLatitude();

				markers["markers"][index]["getAvailableEngineers"] = base->getAvailableEngineers();
				markers["markers"][index]["getAvailableHangars"] = base->getAvailableHangars();
				markers["markers"][index]["getAvailableLaboratories"] = base->getAvailableLaboratories();
				markers["markers"][index]["getAvailableQuarters"] = base->getAvailableQuarters();
				markers["markers"][index]["getAvailableScientists"] = base->getAvailableScientists();
				markers["markers"][index]["getAvailableSoldiers"] = base->getAvailableSoldiers();
				markers["markers"][index]["getAvailableStores"] = base->getAvailableStores();
				markers["markers"][index]["getAvailableTraining"] = base->getAvailableTraining();
				markers["markers"][index]["getAvailableWorkshops"] = base->getAvailableWorkshops();

				// new!!!

				// new!!!
				// Facilities synchronization
				// facilities
				int facilities_index = 0;
				double tr_coop = 0;
				double radar_range_coop = 0;
				int completedFacilities = 0;
				int mindShields = 0;
				for (const auto* fac : *base->getFacilities())
				{
					if (fac->getBuildTime() != 0)
					{
						continue;
					}

					if (fac->getRules())
					{
						if (fac->getBuildTime() == 0)
						{
							tr_coop = fac->getRules()->getRadarRange();
							if (tr_coop < 10000 && tr_coop > radar_range_coop)
								radar_range_coop = tr_coop;

							if (_game->getCoopMod()->getServerOwner() == false)
							{
								completedFacilities = fac->getRules()->getSizeX() * fac->getRules()->getSizeY();
								if (fac->getRules()->isMindShield() && !fac->getDisabled())
								{
									mindShields = fac->getRules()->getMindShieldPower();
								}

								markers["markers"][index]["facilities"][facilities_index]["radar_chance_coop"] = fac->getRules()->getRadarChance();
								markers["markers"][index]["facilities"][facilities_index]["hyperwave_coop"] = fac->getRules()->isHyperwave();
								markers["markers"][index]["facilities"][facilities_index]["radar_range_coop"] = fac->getRules()->getRadarRange();
								markers["markers"][index]["facilities"][facilities_index]["completedFacilities"] = completedFacilities;
								markers["markers"][index]["facilities"][facilities_index]["mindShields"] = mindShields;

								facilities_index++;
							}
						}
					}
				}

				markers["markers"][index]["radar_range_coop"] = radar_range_coop;

				index++;
			}
		}

		sendTCPPacketData(markers.toStyledString());
	}

	// new base icon
	if (stateString == "new_base")
	{
		// PRD-J07 (extending the J02 fence list): SEPARATE-only mirror machinery -
		// creates a _coopIcon marker base. SHARED base creation rides the base_new
		// shared_apply, which appends the REAL base on every machine.
		if (isSharedCampaign())
		{
			return;
		}

		std::string s_lon = obj["markers"]["lon"].asString();
		std::string s_lan = obj["markers"]["lan"].asString();

		int coopbaseid = obj["markers"]["coopbaseid"].asInt();

		int getAvailableEngineers = obj["markers"]["getAvailableEngineers"].asInt();
		int getAvailableHangars = obj["markers"]["getAvailableHangars"].asInt();
		int getAvailableLaboratories = obj["markers"]["getAvailableLaboratories"].asInt();
		int getAvailableQuarters = obj["markers"]["getAvailableQuarters"].asInt();
		int getAvailableScientists = obj["markers"]["getAvailableScientists"].asInt();
		int getAvailableSoldiers = obj["markers"]["getAvailableSoldiers"].asInt();
		int getAvailableStores = obj["markers"]["getAvailableStores"].asInt();
		int getAvailableTraining = obj["markers"]["getAvailableTraining"].asInt();
		int getAvailableWorkshops = obj["markers"]["getAvailableWorkshops"].asInt();

		double lon = std::stod(s_lon);
		double lan = std::stod(s_lan);

		Base* CoopBase = new Base(_game->getMod());

		CoopBase->setEngineers(getAvailableEngineers);
		CoopBase->coop_hangar = getAvailableHangars;
		CoopBase->coop_laboratory = getAvailableLaboratories;
		CoopBase->coop_quarters = getAvailableQuarters;
		CoopBase->coop_soldiers = getAvailableSoldiers;
		CoopBase->coop_stores = getAvailableStores;
		CoopBase->coop_training = getAvailableTraining;
		CoopBase->coop_workshop = getAvailableWorkshops;
		CoopBase->setScientists(getAvailableScientists);

		std::string base_name = obj["markers"]["base"].asString();
		CoopBase->setName(base_name);

		CoopBase->isCoopBase(true);
		CoopBase->_coopIcon = true;

		CoopBase->_coop_base_id = coopbaseid;

		CoopBase->setLongitude(lon);
		CoopBase->setLatitude(lan);

		_game->getSavedGame()->getBases()->push_back(CoopBase);

		// add to the list
		Json::Value m_markers;
		Json::Reader reader;
		reader.parse(j_markers, m_markers);

		m_markers.append(obj["markers"]);

		j_markers = m_markers.toStyledString();
	}

	// NEW COOP BASE REQUEST
	if (stateString == "baseRequest")
	{

		// PRD-J02: SEPARATE-only mirror machinery; never in SHARED. Also guard the
		// save deref: a SHARED replica can receive stray packets before its world
		// exists, and the loop below dereferences the SavedGame.
		if (isSharedCampaign() || !_game->getSavedGame())
		{
			return;
		}

		Json::Value markers;

		int index = 0;
		for (auto base : *_game->getSavedGame()->getBases())
		{

			if (base->_coopBase == false && base->_coopIcon == false && (base->getLongitude() != 0 || base->getLatitude() != 0))
			{

				markers["markers"][index]["coopbaseid"] = base->_coop_base_id;

				markers["markers"][index]["base"] = base->getName().c_str();
				markers["markers"][index]["lon"] = base->getLongitude();
				markers["markers"][index]["lan"] = base->getLatitude();

				markers["markers"][index]["getAvailableEngineers"] = base->getAvailableEngineers();
				markers["markers"][index]["getAvailableHangars"] = base->getAvailableHangars();
				markers["markers"][index]["getAvailableLaboratories"] = base->getAvailableLaboratories();
				markers["markers"][index]["getAvailableQuarters"] = base->getAvailableQuarters();
				markers["markers"][index]["getAvailableScientists"] = base->getAvailableScientists();
				markers["markers"][index]["getAvailableSoldiers"] = base->getAvailableSoldiers();
				markers["markers"][index]["getAvailableStores"] = base->getAvailableStores();
				markers["markers"][index]["getAvailableTraining"] = base->getAvailableTraining();
				markers["markers"][index]["getAvailableWorkshops"] = base->getAvailableWorkshops();

				// new!!!
				// Facilities synchronization
				// facilities
				int facilities_index = 0;
				double tr_coop = 0;
				double radar_range_coop = 0;
				int completedFacilities = 0;
				int mindShields = 0;
				for (const auto* fac : *base->getFacilities())
				{
					if (fac->getBuildTime() != 0)
					{
						continue;
					}

					if (fac->getRules())
					{
						if (fac->getBuildTime() == 0)
						{
							tr_coop = fac->getRules()->getRadarRange();
							if (tr_coop < 10000 && tr_coop > radar_range_coop)
								radar_range_coop = tr_coop;

							if (_game->getCoopMod()->getServerOwner() == false)
							{
								completedFacilities = fac->getRules()->getSizeX() * fac->getRules()->getSizeY();
								if (fac->getRules()->isMindShield() && !fac->getDisabled())
								{
									mindShields = fac->getRules()->getMindShieldPower();
								}

								markers["markers"][index]["facilities"][facilities_index]["radar_chance_coop"] = fac->getRules()->getRadarChance();
								markers["markers"][index]["facilities"][facilities_index]["hyperwave_coop"] = fac->getRules()->isHyperwave();
								markers["markers"][index]["facilities"][facilities_index]["radar_range_coop"] = fac->getRules()->getRadarRange();
								markers["markers"][index]["facilities"][facilities_index]["completedFacilities"] = completedFacilities;
								markers["markers"][index]["facilities"][facilities_index]["mindShields"] = mindShields;

								facilities_index++;
							}
						}
					}
				}

				markers["markers"][index]["radar_range_coop"] = radar_range_coop;

				index++;
			}
		}

		if (getHost() == false && connectionTCP::no_bases == false)
		{

			markers["state"] = "coopBase3";

			sendTCPPacketData(markers.toStyledString());
		}
		else if (getHost() == true)
		{

			markers["state"] = "coopBase2";
			markers["gamemode"] = connectionTCP::_coopGamemode;

			sendTCPPacketData(markers.toStyledString());
		}
	}

	// COOP BASE CLIENT
	if (stateString == "coopBase2" && onTcpHost == false)
	{

		// PRD-J02: SEPARATE-only mirror-base machinery. Never in SHARED.
		if (isSharedCampaign())
		{
			return;
		}

		if (getServerOwner() == false)
		{
			int gamemode = obj["gamemode"].asInt();
			connectionTCP::_coopGamemode = gamemode;
		}

		Json::Value m_markers;
		Json::Reader reader;

		// if there are markers
		if (obj["markers"].empty() == false && obj.isMember("markers") == true)
		{
			j_markers = obj["markers"].toStyledString();
		}

		reader.parse(j_markers, m_markers);

		for (Json::Value marker : m_markers)
		{

			std::string s_lon = marker["lon"].asString();
			std::string s_lan = marker["lan"].asString();

			int coopbaseid = marker["coopbaseid"].asInt();

			int getAvailableEngineers = marker["getAvailableEngineers"].asInt();
			int getAvailableHangars = marker["getAvailableHangars"].asInt();
			int getAvailableLaboratories = marker["getAvailableLaboratories"].asInt();
			int getAvailableQuarters = marker["getAvailableQuarters"].asInt();
			int getAvailableScientists = marker["getAvailableScientists"].asInt();
			int getAvailableSoldiers = marker["getAvailableSoldiers"].asInt();
			int getAvailableStores = marker["getAvailableStores"].asInt();
			int getAvailableTraining = marker["getAvailableTraining"].asInt();
			int getAvailableWorkshops = marker["getAvailableWorkshops"].asInt();

			double lon = std::stod(s_lon);
			double lan = std::stod(s_lan);

			std::string base_name = marker["base"].asString();

			// Check that the base does not already exist
			bool alreadyExists = false;
			for (Base* existingBase : *_game->getSavedGame()->getBases())
			{
				if (existingBase->_coop_base_id == coopbaseid &&
					(existingBase->getLongitude() == lon && existingBase->getLatitude() == lan))
				{

					existingBase->setEngineers(getAvailableEngineers);
					existingBase->coop_hangar = getAvailableHangars;
					existingBase->coop_laboratory = getAvailableLaboratories;
					existingBase->coop_quarters = getAvailableQuarters;
					existingBase->coop_soldiers = getAvailableSoldiers;
					existingBase->coop_stores = getAvailableStores;
					existingBase->coop_training = getAvailableTraining;
					existingBase->coop_workshop = getAvailableWorkshops;
					existingBase->setScientists(getAvailableScientists);

					// new !!!
					existingBase->_facilitiesCoop = marker["facilities"];
					double radar_range_coop = marker["radar_range_coop"].asDouble();
					existingBase->_radar_range_coop = radar_range_coop;

					alreadyExists = true;
					break;
				}
			}

			if (alreadyExists)
				continue;

			Base* CoopBase = new Base(_game->getMod());

			CoopBase->setEngineers(getAvailableEngineers);
			CoopBase->coop_hangar = getAvailableHangars;
			CoopBase->coop_laboratory = getAvailableLaboratories;
			CoopBase->coop_quarters = getAvailableQuarters;
			CoopBase->coop_soldiers = getAvailableSoldiers;
			CoopBase->coop_stores = getAvailableStores;
			CoopBase->coop_training = getAvailableTraining;
			CoopBase->coop_workshop = getAvailableWorkshops;
			CoopBase->setScientists(getAvailableScientists);

			CoopBase->_coop_base_id = coopbaseid;

			// new !!!
			CoopBase->_facilitiesCoop = marker["facilities"];
			double radar_range_coop = marker["radar_range_coop"].asDouble();
			CoopBase->_radar_range_coop = radar_range_coop;

			CoopBase->setName(base_name);

			CoopBase->isCoopBase(true);
			CoopBase->_coopIcon = true;

			CoopBase->setLongitude(lon);
			CoopBase->setLatitude(lan);

			_game->getSavedGame()->getBases()->push_back(CoopBase);
		}
	}

	// COOP BASE HOST
	if (stateString == "coopBase3" && getHost() == true)
	{

		// PRD-J02: SEPARATE-only mirror-base machinery. Never in SHARED.
		if (isSharedCampaign())
		{
			return;
		}

		Json::Value m_markers;
		Json::Reader reader;

		// if there are markers
		if (obj["markers"].empty() == false && obj.isMember("markers") == true)
		{

			j_markers = obj["markers"].toStyledString();
		}

		reader.parse(j_markers, m_markers);

		for (Json::Value marker : m_markers)
		{

			std::string s_lon = marker["lon"].asString();
			std::string s_lan = marker["lan"].asString();

			int coopbaseid = marker["coopbaseid"].asInt();

			int getAvailableEngineers = marker["getAvailableEngineers"].asInt();
			int getAvailableHangars = marker["getAvailableHangars"].asInt();
			int getAvailableLaboratories = marker["getAvailableLaboratories"].asInt();
			int getAvailableQuarters = marker["getAvailableQuarters"].asInt();
			int getAvailableScientists = marker["getAvailableScientists"].asInt();
			int getAvailableSoldiers = marker["getAvailableSoldiers"].asInt();
			int getAvailableStores = marker["getAvailableStores"].asInt();
			int getAvailableTraining = marker["getAvailableTraining"].asInt();
			int getAvailableWorkshops = marker["getAvailableWorkshops"].asInt();

			double lon = std::stod(s_lon);
			double lan = std::stod(s_lan);

			std::string base_name = marker["base"].asString();

			// Check that the base does not already exist
			bool alreadyExists = false;
			for (Base* existingBase : *_game->getSavedGame()->getBases())
			{
				if (existingBase->_coop_base_id == coopbaseid &&
					(existingBase->getLongitude() == lon && existingBase->getLatitude() == lan))
				{

					existingBase->setEngineers(getAvailableEngineers);
					existingBase->coop_hangar = getAvailableHangars;
					existingBase->coop_laboratory = getAvailableLaboratories;
					existingBase->coop_quarters = getAvailableQuarters;
					existingBase->coop_soldiers = getAvailableSoldiers;
					existingBase->coop_stores = getAvailableStores;
					existingBase->coop_training = getAvailableTraining;
					existingBase->coop_workshop = getAvailableWorkshops;
					existingBase->setScientists(getAvailableScientists);

					// new !!!
					existingBase->_facilitiesCoop = marker["facilities"];
					double radar_range_coop = marker["radar_range_coop"].asDouble();
					existingBase->_radar_range_coop = radar_range_coop;

					alreadyExists = true;
					break;
				}
			}

			if (alreadyExists)
				continue;

			Base* CoopBase = new Base(_game->getMod());

			CoopBase->setEngineers(getAvailableEngineers);
			CoopBase->coop_hangar = getAvailableHangars;
			CoopBase->coop_laboratory = getAvailableLaboratories;
			CoopBase->coop_quarters = getAvailableQuarters;
			CoopBase->coop_soldiers = getAvailableSoldiers;
			CoopBase->coop_stores = getAvailableStores;
			CoopBase->coop_training = getAvailableTraining;
			CoopBase->coop_workshop = getAvailableWorkshops;
			CoopBase->setScientists(getAvailableScientists);

			CoopBase->_coop_base_id = coopbaseid;

			// new !!!
			CoopBase->_facilitiesCoop = marker["facilities"];
			double radar_range_coop = marker["radar_range_coop"].asDouble();
			CoopBase->_radar_range_coop = radar_range_coop;

			CoopBase->setName(base_name);

			CoopBase->isCoopBase(true);
			CoopBase->_coopIcon = true;

			CoopBase->setLongitude(lon);
			CoopBase->setLatitude(lan);

			_game->getSavedGame()->getBases()->push_back(CoopBase);
		}
	}

	if (stateString == "SEND_FILE_HOST_TRUE_SAVE_PROGRESS")
	{

		Json::Value root;

		root["state"] = "SEND_FILE_HOST_SAVE_PROGRESS";

		sendTCPPacketData(root.toStyledString());
	}

	if (stateString == "SEND_FILE_HOST_SAVE_PROGRESS")
	{

		_game->getCoopMod()->load_state = "Saving";

		sendFileHost = true;
		sendProgressSaveFileToHost = true;
	}

	// BASES
	if (stateString == "SEND_FILE_HOST_BASE" && onTcpHost == false)
	{

		sendBaseFile();

		sendFileHost = true;
		sendFileBase = true;
	}

	if (stateString == "SEND_FILE_CLIENT_BASE" && onTcpHost == true)
	{

		sendBaseFile();

		sendFileClient = true;
		sendFileBase = true;
	}

	if (stateString == "MAP_RESULT_CLIENT_BASE" && onTcpHost == false)
	{

		writeHostMapFile2();

		CoopState* coopWindow = new CoopState(55);
		coopWindow->loadWorld();

	}

	if (stateString == "MAP_RESULT_HOST_BASE" && onTcpHost == true)
	{

		writeHostMapFile2();

		CoopState* coopWindow = new CoopState(55);
		coopWindow->loadWorld();

	}
}

void connectionTCP::sendBaseFile()
{

	// saving is not allowed if in battle and inside another player's base!
	if (!_game->getSavedGame()->getSavedBattle() && _game->getCoopMod()->playerInsideCoopBase == false)
	{
		if (_game->getCoopMod()->coopMissionEnd == false)
		{
			_game->getSavedGame()->saveCoopToMemory("basehost", _game->getMod(), "basehost");
		}
	}

}

std::string connectionTCP::getPing()
{
	return current_ping;
}

bool connectionTCP::isCoopSession()
{
	return coopSession;
}

void connectionTCP::setCoopSession(bool session)
{
	coopSession = session;
}

void connectionTCP::setServerOwner(bool owner)
{
	session.setRole(owner ? CoopRole::Host : CoopRole::None);
}

void connectionTCP::setCoopCampaign(bool coop)
{
	_coopCampaign = coop;
}

bool connectionTCP::getCoopCampaign()
{
	return _coopCampaign;
}

// PRD-J01: true only when the active save is a SHARED co-op campaign.
bool connectionTCP::isSharedCampaign()
{
	SavedGame* save = _game ? _game->getSavedGame() : nullptr;
	return save && save->isCoopSave()
		&& save->getCampaignType() == CoopCampaignType::Shared;
}

// Static mirror of isSharedCampaign() for engine-level callers that hold no CoopMod
// instance (e.g. Craft capacity accounting). Reads the same authoritative save via the
// static Game pointer.
bool connectionTCP::isSharedCampaignStatic()
{
	SavedGame* save = _staticGame ? _staticGame->getSavedGame() : nullptr;
	return save && save->isCoopSave()
		&& save->getCampaignType() == CoopCampaignType::Shared;
}

// PRD-J02: a SHARED client holds a replica of the host's single authoritative
// world. Host = seat 0 owns the world; every other seat is a replica.
bool connectionTCP::isSharedReplica()
{
	return isSharedCampaign() && !getHost();
}

// PRD-J02: hand the host's authoritative world to the single-client streamer.
// Serializes FRESH (not a stale stored blob) into a scratch key, then routes it
// through the same resume-blob lane the client already knows how to adopt
// (streamer sendProgressLoadBlob path -> MAP_RESULT_LOAD_PROGRESS ->
// CoopState(555) -> LoadGameState). Reuses the existing file-transfer chunking;
// no second chunk protocol. Host only; caller must ensure the streamer is idle.
void connectionTCP::streamSharedWorldToClient()
{
	if (!getServerOwner() || !_game->getSavedGame())
	{
		return;
	}

	const std::string key = "shared_world";
	connectionTCP::saveError = false;
	_game->getSavedGame()->saveCoopToMemory(key, _game->getMod(), key);

	std::string blob;
	{
		std::lock_guard<std::mutex> lock(coopFilesMutex);
		auto it = coopFilesHost.find(key);
		if (it != coopFilesHost.end())
		{
			blob = it->second;
		}
	}

	if (blob.empty())
	{
		Log(LOG_ERROR) << "[coop-shared] streamSharedWorldToClient: no world blob"
		               << " (saveError=" << connectionTCP::saveError << ")";
		return;
	}

	// snapshot for the streamer thread (same fields request_load_progress sets)
	sendProgressLoadBlob = blob;
	sendProgressLoadFileToClient = key;
	sendFileClient = true;

	Log(LOG_INFO) << "[coop-shared] streaming authoritative world to client ("
	              << blob.size() << " bytes)";
}

// PRD-J10: desync repair. A replica reported a world-checksum mismatch; hand it a
// fresh authoritative world down the same J02 bootstrap lane. LoadGameState parks
// EVERY client that adopts a streamed world in COOP_DLG_CLIENT_RESUME_HOLD until a
// campaign_begun arrives, and mid-session there is no operator BEGIN click to send
// one - the resume_ack handler covers that for us now (issue #91), for this
// restream and every other, so there is nothing to arm here.
void connectionTCP::sharedResyncStream()
{
	if (!getServerOwner() || !isSharedCampaign() || !_game->getSavedGame())
	{
		return;
	}
	if (sendFileClient)
	{
		// The streamer is single-slot and already busy (bootstrap/resume/post-battle
		// transfer in flight). Drop this request rather than corrupt that transfer -
		// the replica's next mismatching checksum re-asks once its guard expires.
		Log(LOG_WARNING) << "[coop-shared] resync request dropped: streamer busy";
		return;
	}

	streamSharedWorldToClient();
	if (!sendFileClient)
	{
		Log(LOG_ERROR) << "[coop-shared] resync restream failed to serialize the world";
	}
}

// PRD-J01: this machine's seat. Host is always 0; a client's seat is its
// roster index, carried today by coop_save_owner_player_id (2-player: 1).
//
// Do not use getHost() here. onTcpHost describes the current transport/file-
// transfer direction and is temporarily changed during save/world transfers.
// Using it as player identity can make the sender look like the receiver, for
// example causing a player to receive their own soldier-gift popup.
//
// getServerOwner() identifies the actual multiplayer host: the player who
// created and owns the server. This is the stable value that should be used
// when determining whether the local player occupies host seat 0.
//
// getHost() has a different meaning. It describes the temporary mission/save
// transfer role and may change during synchronization. In my opinion,
// getHost() should be renamed to isMissionGiver() to make this distinction
// clear. getServerOwner() could also be renamed to isServerHost().
//
// A cleaner long-term solution would still be to assign a permanent
// session.localSeatId when the roster locks and use that value directly.
int connectionTCP::localSeat()
{
	if (getServerOwner())
		return 0;
	return coop_save_owner_player_id > 0 ? coop_save_owner_player_id : 1;
}

// PRD-J01: active roster size (host + clients). Falls back to the legacy
// 2-player count before the roster locks.
int connectionTCP::seatCount()
{
	if (_staticGame && _staticGame->getSavedGame())
	{
		size_t n = _staticGame->getSavedGame()->getCoopPlayers().size();
		if (n > 0)
			return static_cast<int>(n);
	}
	return 2;
}

// PRD-J01: player name for a seat, or empty if out of range / no roster.
std::string connectionTCP::seatName(int seat)
{
	if (_staticGame && _staticGame->getSavedGame())
	{
		const auto& roster = _staticGame->getSavedGame()->getCoopPlayers();
		if (seat >= 0 && static_cast<size_t>(seat) < roster.size())
			return roster[seat];
	}
	return std::string();
}

int connectionTCP::getCoopGamemode()
{
	return _coopGamemode;
}

void connectionTCP::createCoopMenu()
{

	// If the player has created a server or joined another player's game, create the LobbyMenu
	if (_game->getCoopMod()->isConnected() == 1 || _game->getCoopMod()->getServerOwner() == true)
	{
		_game->pushState(new LobbyMenu());
	}
	else
	{
		_game->pushState(new ServerList());
	}

	if (Options::logPacketMessages == true)
	{
		_game->pushState(new CoopState(942));
	}

}

void connectionTCP::sendTCPPacketStaticData2(std::string data)
{
	enqueueTx(std::move(data));
}

void connectionTCP::writeHostMapFile2()
{
	
	if (mapData.empty())
		return;

	{
		std::lock_guard<std::mutex> lock(coopFilesMutex);
		if (connectionTCP::getServerOwner() == true)
		{
			connectionTCP::coopFilesHost["baseclient"] = std::move(mapData);
		}
		else
		{
			connectionTCP::coopFilesClient["baseclient"] = std::move(mapData);
		}
	}

	// the map data must be reset for the next use (fix)
	mapData = "";

}

void connectionTCP::setHost(bool host)
{
	onTcpHost = host;
}

bool connectionTCP::getHost()
{
	return onTcpHost;
}

int connectionTCP::getHostSpaceAvailable()
{
	return _hostSpace;
}

void connectionTCP::setHostSpaceAvailable(int hostSpace)
{
	_hostSpace = hostSpace;
}

bool connectionTCP::getCoopStatic()
{

	bool coop = false;

	if (onConnect == 1)
	{
		coop = true;
	}

	return coop;
}

void connectionTCP::loadHostMap()
{

	CoopState* coopWindow = new CoopState(2);
	coopWindow->loadWorld();
}

void connectionTCP::sendMissionFile()
{

	// Client sends the file to the host
	if (_game->getCoopMod()->getHost() == false)
	{

		if ((_game->getCoopMod()->playerInsideCoopBase == true || _game->getCoopMod()->coopMissionEnd == true) && _game->getCoopMod()->getCoopCampaign() == true)
		{

			// Go to Geoscape to begin the co-op mission.
			_game->getCoopMod()->playerInsideCoopBase = false;

			_game->getCoopMod()->ready_coop_battle = true;

			_game->popState();

			CoopState* coopWindow = new CoopState(66);
			_game->pushState(coopWindow);
		}
		else
		{

			// saving files
			if (_game->getCoopMod()->getServerOwner() == true && _game->getCoopMod()->coopMissionEnd == false)
			{
				_game->getSavedGame()->saveCoopToMemory("battlehost", _game->getMod(), "battlehost");
			}
			else if (_game->getCoopMod()->coopMissionEnd == false)
			{
				_game->getSavedGame()->saveCoopToMemory("battlehost", _game->getMod(), "battlehost");
			}

			_game->getCoopMod()->load_state = "Saving";

			// R4-REWIRE: "SEND_FILE_HOST_TRUE" is quarantined (R1-P3,
			// inventory-wire-protocol.md section D - bootstrap/host-token handoff/
			// battle-save restream). sendMissionFile() itself SURVIVES (section F, the
			// blob-stream carrier), but this receive handler is deleted; the
			// choreography around it needs a versioned handshake pair in r4.
			Json::Value obj;
			obj["state"] = "SEND_FILE_HOST_TRUE";

			_game->getCoopMod()->sendTCPPacketData(obj.toStyledString());
		}
	}
	// Host sends the file to the client
	else
	{

		// Save the player ID that owns the co-op save
		if (_game->getCoopMod()->getServerOwner() == false)
		{
			connectionTCP::coop_save_owner_player_id = 1;
		}
		// Ensure the server owner's coop_save_owner_player_id value is set to 0.
		else
		{
			connectionTCP::coop_save_owner_player_id = 0;
		}

		if (_game->getCoopMod()->getServerOwner() == true && _game->getCoopMod()->coopMissionEnd == false)
		{
			_game->getSavedGame()->saveCoopToMemory("battlehost", _game->getMod(), "battlehost");
		}
		else if (_game->getCoopMod()->coopMissionEnd == false)
		{
			_game->getSavedGame()->saveCoopToMemory("battlehost", _game->getMod(), "battlehost");
		}

		// R4-REWIRE: "SEND_FILE_CLIENT_TRUE" is quarantined (R1-P3,
		// inventory-wire-protocol.md section D). sendMissionFile() itself SURVIVES
		// (section F, the blob-stream carrier), but this receive handler is deleted; the
		// choreography around it needs a versioned handshake pair in r4.
		Json::Value obj;
		obj["state"] = "SEND_FILE_CLIENT_TRUE";
		obj["target"] = false;

		// Delete coop UFOs or missions
		if (getSelectedCraft() && getCoopCampaign() == true)
		{

			Ufo* u = dynamic_cast<Ufo*>(getSelectedCraft()->getDestination());
			MissionSite* m = dynamic_cast<MissionSite*>(getSelectedCraft()->getDestination());

			if (u)
			{
				obj["target"] = true;
				obj["lat"] = u->getLatitude();
				obj["lon"] = u->getLongitude();
				obj["isUFO"] = true;
			}
			else if (m)
			{
				obj["target"] = true;
				obj["lat"] = m->getLatitude();
				obj["lon"] = m->getLongitude();
				obj["isUFO"] = false;
			}


		}

		_game->getCoopMod()->sendTCPPacketData(obj.toStyledString());
	}

}

/**
 * Issue #93: hand a rejoining client the SKIRMISH battle that is running right now.
 *
 * Deliberately the same wire flow the mission started with (snapshot the live world
 * into the "battlehost" blob, then SEND_FILE_CLIENT_TRUE -> the client asks for the
 * file -> the streamer sends it -> the client loads "battleclient" straight into a
 * BattlescapeState). The snapshot is taken NOW, so the rejoiner gets the battle as it
 * currently stands, not as it was deployed - and every id in it comes from the host,
 * which is what keeps the two machines talking about the same units and items.
 *
 * Only the host serves this; target=false because a skirmish has no geoscape UFO or
 * mission site to retire on the client.
 */
void connectionTCP::streamSkirmishBattleToClient()
{
	if (!getServerOwner() || !_game->getSavedGame() || !_game->getSavedGame()->getSavedBattle())
	{
		Log(LOG_WARNING) << "[coop] skirmish rejoin: no live battle to stream";
		return;
	}

	// the host owns the save (see sendMissionFile)
	connectionTCP::coop_save_owner_player_id = 0;

	_game->getSavedGame()->saveCoopToMemory("battlehost", _game->getMod(), "battlehost");

	// R4-REWIRE: "SEND_FILE_CLIENT_TRUE" is quarantined (R1-P3,
	// inventory-wire-protocol.md section D); its receive handler is deleted. This
	// skirmish-rejoin stream needs re-targeting at the r4 handshake pair.
	Json::Value obj;
	obj["state"] = "SEND_FILE_CLIENT_TRUE";
	obj["target"] = false;
	sendTCPPacketData(obj.toStyledString());

	Log(LOG_INFO) << "[coop] skirmish rejoin: streaming the live battle to "
		<< _game->getCoopMod()->getCurrentClientName();
}

void connectionTCP::sendSaveProgressFile()
{

	if (_game->getCoopMod()->playerInsideCoopBase == true && _game->getCoopMod()->getCoopCampaign() == true)
	{

		// Go to the Geoscape to begin saving progress.
			
		_game->getCoopMod()->playerInsideCoopBase = false;

		_game->getCoopMod()->ready_coop_save_progress = true;

		CoopState* coopWindow = new CoopState(67);
		_game->pushState(coopWindow);
			
	}
	else
	{

		CoopState* coopWindow = new CoopState(53);
		_game->pushState(coopWindow);

		// saving files
		std::string filename = clientBlobKey(_game->getCoopMod()->getHostName());

		_game->getSavedGame()->saveCoopToMemory(filename, _game->getMod(), filename);
		{
			std::lock_guard<std::mutex> lock(coopFilesMutex);
			eraseStaleBlobEntries(coopFilesClient, "client_", _game->getCoopMod()->getHostName(), filename);
		}

		_game->getCoopMod()->load_state = "Saving";

		Json::Value obj;
		obj["state"] = "SEND_FILE_HOST_TRUE_SAVE_PROGRESS";

		_game->getCoopMod()->sendTCPPacketData(obj.toStyledString());
	}
	
}

int connectionTCP::getCurrentTurn()
{
	// R1-P4: this used to read the BattlescapeState::getCurrentTurn() mirror,
	// a coop hook the r1 vanilla restore (911ca487f) stripped. No caller of
	// this wrapper survives elsewhere in CoopMod (verified by grep), so stub
	// to the existing "no battle" sentinel rather than re-adding the mirror.
	// The real turn-machine returns with r2 (RB-D9/RB-D11).
	return -1;
}

ChatMenu* connectionTCP::getChatMenu()
{
	return _chatMenu;
}

void connectionTCP::setChatMenu(ChatMenu* menu)
{
	_chatMenu = menu;
}

int connectionTCP::unitstatusToInt(UnitStatus status)
{
	if (status == STATUS_STANDING)
		return 0;
	if (status == STATUS_WALKING)
		return 1;
	if (status == STATUS_FLYING)
		return 2;
	if (status == STATUS_TURNING)
		return 3;
	if (status == STATUS_AIMING)
		return 4;
	if (status == STATUS_COLLAPSING)
		return 5;
	if (status == STATUS_DEAD)
		return 6;
	if (status == STATUS_UNCONSCIOUS)
		return 7;
	if (status == STATUS_PANICKING)
		return 8;
	if (status == STATUS_BERSERK)
		return 9;
	if (status == STATUS_IGNORE_ME)
		return 10;
	return 10;
}

UnitStatus connectionTCP::intToUnitstatus(int status)
{
	if (status == 0)
		return STATUS_STANDING;
	if (status == 1)
		return STATUS_WALKING;
	if (status == 2)
		return STATUS_FLYING;
	if (status == 3)
		return STATUS_TURNING;
	if (status == 4)
		return STATUS_AIMING;
	if (status == 5)
		return STATUS_COLLAPSING;
	if (status == 6)
		return STATUS_DEAD;
	if (status == 7)
		return STATUS_UNCONSCIOUS;
	if (status == 8)
		return STATUS_PANICKING;
	if (status == 9)
		return STATUS_BERSERK;
	if (status == 10)
		return STATUS_IGNORE_ME;
	return STATUS_IGNORE_ME;
}

int connectionTCP::ufostatusToInt(Ufo::UfoStatus status)
{
	if (status == Ufo::FLYING)
		return 0;
	if (status == Ufo::LANDED)
		return 1;
	if (status == Ufo::CRASHED)
		return 2;
	if (status == Ufo::DESTROYED)
		return 3;
	if (status == Ufo::IGNORE_ME)
		return 4;
	return 4;
}

Ufo::UfoStatus connectionTCP::intToUfostatus(int status)
{
	if (status == 0)
		return Ufo::FLYING;
	if (status == 1)
		return Ufo::LANDED;
	if (status == 2)
		return Ufo::CRASHED;
	if (status == 4)
		return Ufo::DESTROYED;
	if (status == 4)
		return Ufo::IGNORE_ME;
	return Ufo::IGNORE_ME;
}

int connectionTCP::ItemDamageRandomTypeToInt(ItemDamageRandomType type)
{

	if (type == DRT_DEFAULT)
		return 0;
	if (type == DRT_UFO)
		return 1;
	if (type == DRT_TFTD)
		return 2;
	if (type == DRT_FLAT)
		return 3;
	if (type == DRT_FIRE)
		return 4;
	if (type == DRT_NONE)
		return 5;
	if (type == DRT_UFO_WITH_TWO_DICE)
		return 6;
	if (type == DRT_EASY)
		return 7;
	if (type == DRT_STANDARD)
		return 8;
	if (type == DRT_EXPLOSION)
		return 9;

	return 0;
}

ItemDamageRandomType connectionTCP::intToItemDamageRandomType(int type)
{
	if (type == 0)
		return DRT_DEFAULT;
	if (type == 1)
		return DRT_UFO;
	if (type == 2)
		return DRT_TFTD;
	if (type == 3)
		return DRT_FLAT;
	if (type == 4)
		return DRT_FIRE;
	if (type == 5)
		return DRT_NONE;
	if (type == 6)
		return DRT_UFO_WITH_TWO_DICE;
	if (type == 7)
		return DRT_EASY;
	if (type == 8)
		return DRT_STANDARD;
	if (type == 9)
		return DRT_EXPLOSION;

	return DRT_DEFAULT;
}

int connectionTCP::ItemDamageTypeToInt(ItemDamageType type)
{

	if (type == DT_NONE)
		return 0;
	if (type == DT_AP)
		return 1;
	if (type == DT_IN)
		return 2;
	if (type == DT_HE)
		return 3;
	if (type == DT_LASER)
		return 4;
	if (type == DT_PLASMA)
		return 5;
	if (type == DT_STUN)
		return 6;
	if (type == DT_MELEE)
		return 7;
	if (type == DT_ACID)
		return 8;
	if (type == DT_SMOKE)
		return 9;
	if (type == DT_10)
		return 10;
	if (type == DT_11)
		return 11;
	if (type == DT_12)
		return 12;
	if (type == DT_13)
		return 13;
	if (type == DT_14)
		return 14;
	if (type == DT_15)
		return 15;
	if (type == DT_16)
		return 16;
	if (type == DT_17)
		return 17;
	if (type == DT_18)
		return 18;
	if (type == DT_19)
		return 19;
	if (type == DAMAGE_TYPES)
		return 20;

	return 0;
}

ItemDamageType connectionTCP::intToItemDamageType(int type)
{
	if (type == 0)
		return DT_NONE;
	if (type == 1)
		return DT_AP;
	if (type == 2)
		return DT_IN;
	if (type == 3)
		return DT_HE;
	if (type == 4)
		return DT_LASER;
	if (type == 5)
		return DT_PLASMA;
	if (type == 6)
		return DT_STUN;
	if (type == 7)
		return DT_MELEE;
	if (type == 8)
		return DT_ACID;
	if (type == 9)
		return DT_SMOKE;
	if (type == 10)
		return DT_10;
	if (type == 11)
		return DT_11;
	if (type == 12)
		return DT_12;
	if (type == 13)
		return DT_13;
	if (type == 14)
		return DT_14;
	if (type == 15)
		return DT_15;
	if (type == 16)
		return DT_16;
	if (type == 17)
		return DT_17;
	if (type == 18)
		return DT_18;
	if (type == 19)
		return DT_19;
	if (type == 20)
		return DAMAGE_TYPES;

	return DT_NONE;
}

int connectionTCP::InventoryTypeToInt(InventoryType type)
{
	if (type == INV_SLOT)
		return 0;
	if (type == INV_HAND)
		return 1;
	if (type == INV_GROUND)
		return 2;
	return 2;
}

InventoryType connectionTCP::intToInventoryType(int type)
{
	if (type == 0)
		return INV_SLOT;
	if (type == 1)
		return INV_HAND;
	if (type == 2)
		return INV_GROUND;
	return INV_GROUND;
}

int connectionTCP::SoldierRanktoInt(SoldierRank rank)
{
	if (rank == RANK_ROOKIE)
		return 0;
	if (rank == RANK_SQUADDIE)
		return 1;
	if (rank == RANK_SERGEANT)
		return 2;
	if (rank == RANK_CAPTAIN)
		return 3;
	if (rank == RANK_COLONEL)
		return 4;
	if (rank == RANK_COMMANDER)
		return 5;
	return 0;
}

SoldierRank connectionTCP::intToSoldierRank(int rank)
{
	if (rank == 0)
		return RANK_ROOKIE;
	if (rank == 1)
		return RANK_SQUADDIE;
	if (rank == 2)
		return RANK_SERGEANT;
	if (rank == 3)
		return RANK_CAPTAIN;
	if (rank == 4)
		return RANK_COLONEL;
	if (rank == 5)
		return RANK_COMMANDER;
	return RANK_ROOKIE;
}

Json::Value connectionTCP::toJson(const std::map<int, int>& m)
{
	Json::Value j(Json::objectValue);
	for (auto [k, v] : m)
		j[std::to_string(k)] = v;
	return j;
}

std::map<int, int> connectionTCP::fromJson(const Json::Value& j)
{
	std::map<int, int> m;
	for (const auto& key : j.getMemberNames())
		m[std::stoi(key)] = j[key].asInt();
	return m;
}

void connectionTCP::generateCraftSoldiers()
{

	Base* base = _game->getSavedGame()->getBases()->front();
	Craft* craft = base->getCrafts()->front();
	size_t craftID = 0;

	for (auto* soldier : *base->getSoldiers())
	{
		if (soldier->getCraft() == craft)
		{
			soldier->setCraftAndMoveEquipment(0, base, _game->getSavedGame()->getMonthsPassed() == -1);
		}
	}

	_game->pushState(new CraftSoldiersState(base, craftID));
}

bool connectionTCP::getServerOwner()
{
	return session.role == CoopRole::Host;
}

// R2-P5 (rewrite spike, RB-D6 pattern): see the declaration's doc comment in
// connectionTCP.h. Mirrors _staticGame's other static-accessor call sites
// (e.g. connectionTCP::localSeat(), :1248/:8767 above) rather than adding a
// new one - this is just the first one exposed as a public API surface for
// CoopMod code outside the connectionTCP class (CoopArbiter::onIntent()).
SavedBattleGame* connectionTCP::getStaticBattle()
{
	return (_staticGame && _staticGame->getSavedGame())
		? _staticGame->getSavedGame()->getSavedBattle()
		: nullptr;
}

void connectionTCP::setPathLock(int lock)
{
	_pathLock = lock;
}

// assign the client soldiers to the host's craft
void connectionTCP::setClientSoldiers()
{
	// SHARED has ONE shared world: the roster/craft are already shared, so there is no
	// "assign the client's soldiers to the host's craft" merge to do (PRD-J09 skips the
	// SEPARATE two-world dance), and there is no "battleclient" blob to load. Running it
	// anyway re-entered ConfirmLandingState::startCoopMission below, which calls
	// bgen.run() a SECOND time and generates a brand-new RANDOM map on the host - while
	// the client had already loaded the first one. Result: host and client standing on
	// two entirely different maps (soldiers on open ground, no craft). The host already
	// generated and shipped the authoritative battle in btnYesClick; never regenerate.
	if (isSharedCampaign())
	{
		return;
	}

	// STARTING COOP MISSION
	CoopState* coop = new CoopState(111);

	coop->loadWorld();

	// coop campaign base defense
	if (_geo && getCoopCampaign() == true)
	{
		_geo->startCoopMission();
	}
	// coop campaign
	else if (_landing && getCoopCampaign() == true)
	{
		_landing->startCoopMission();
	}
	// Cydonia has its own confirmation state and never visits ConfirmLandingState.
	// Resume the final-mission generator after the normal SEPARATE craft merge.
	else if (_cydonia && getCoopCampaign() == true)
	{
		_cydonia->startCoopMission();
	}
	// coop battle (pve)
	else if (_battleState)
	{
		_battleState->startCoopMission();
	}
}

void connectionTCP::deleteAllCoopBases()
{

	// issue #78: the authoritative SHARED site set dies with the session - a
	// stale one must never prune the next session's world.
	{
		std::lock_guard<std::mutex> lk(sharedLiveSiteIdsMutex);
		sharedLiveSiteIds.clear();
		sharedLiveSiteIdsValid = false;
	}

	if (_game->getSavedGame() && _game->getCoopMod()->getCoopCampaign() == true)
	{

		if (auto* sg = _game->getSavedGame())
		{
			auto& bases = *sg->getBases(); // std::vector<Base*>&

			for (auto it = bases.begin(); it != bases.end();)
			{
				Base* b = *it;
				if (b && b->_coopIcon)
				{
					delete b;             // free memory permanently
					it = bases.erase(it); // remove from the list; returns next iterator
				}
				else
				{
					++it;
				}
			}

			// issue #78 audit: a dropped session also strands the SEPARATE-mode
			// _coop mirror objects; without this they linger as immortal ghosts
			// (pinned secondsRemaining, no sweep) until the player quits to the
			// menu. Order matters: UFOs before their alien missions.
			auto& sites = *sg->getMissionSites();
			for (auto it = sites.begin(); it != sites.end();)
			{
				if (*it && (*it)->_coop) { delete *it; it = sites.erase(it); }
				else ++it;
			}
			auto& ufos = *sg->getUfos();
			for (auto it = ufos.begin(); it != ufos.end();)
			{
				if (*it && (*it)->_coop) { delete *it; it = ufos.erase(it); }
				else ++it;
			}
			auto& abases = *sg->getAlienBases();
			for (auto it = abases.begin(); it != abases.end();)
			{
				if (*it && (*it)->_coop) { delete *it; it = abases.erase(it); }
				else ++it;
			}
			auto& amissions = sg->getAlienMissions();
			for (auto it = amissions.begin(); it != amissions.end();)
			{
				if (*it && (*it)->_coop) { delete *it; it = amissions.erase(it); }
				else ++it;
			}
		}

	}


}

void connectionTCP::updateAllCoopBases()
{

	Json::Value m_markers;
	Json::Reader reader;

	// if markers exist
	if (j_markers == "")
	{
		return;
	}

	reader.parse(j_markers, m_markers);

	for (Json::Value marker : m_markers)
	{

		std::string s_lon = marker["lon"].asString();
		std::string s_lan = marker["lan"].asString();

		int coopbaseid = marker["coopbaseid"].asInt();

		int getAvailableEngineers = marker["getAvailableEngineers"].asInt();
		int getAvailableHangars = marker["getAvailableHangars"].asInt();
		int getAvailableLaboratories = marker["getAvailableLaboratories"].asInt();
		int getAvailableQuarters = marker["getAvailableQuarters"].asInt();
		int getAvailableScientists = marker["getAvailableScientists"].asInt();
		int getAvailableSoldiers = marker["getAvailableSoldiers"].asInt();
		int getAvailableStores = marker["getAvailableStores"].asInt();
		int getAvailableTraining = marker["getAvailableTraining"].asInt();
		int getAvailableWorkshops = marker["getAvailableWorkshops"].asInt();

		double lon = std::stod(s_lon);
		double lan = std::stod(s_lan);

		std::string base_name = marker["base"].asString();

		// Check that the base does not already exist
		bool alreadyExists = false;
		for (Base* existingBase : *_game->getSavedGame()->getBases())
		{
			if (existingBase->_coop_base_id == coopbaseid &&
				(existingBase->getLongitude() == lon && existingBase->getLatitude() == lan))
			{
				alreadyExists = true;
				break;
			}
		}

		if (alreadyExists)
			continue;

		Base* CoopBase = new Base(_game->getMod());

		CoopBase->setEngineers(getAvailableEngineers);
		CoopBase->coop_hangar = getAvailableHangars;
		CoopBase->coop_laboratory = getAvailableLaboratories;
		CoopBase->coop_quarters = getAvailableQuarters;
		CoopBase->coop_soldiers = getAvailableSoldiers;
		CoopBase->coop_stores = getAvailableStores;
		CoopBase->coop_training = getAvailableTraining;
		CoopBase->coop_workshop = getAvailableWorkshops;
		CoopBase->setScientists(getAvailableScientists);

		CoopBase->_coop_base_id = coopbaseid;

		CoopBase->setName(base_name);

		CoopBase->isCoopBase(true);
		CoopBase->_coopIcon = true;

		CoopBase->setLongitude(lon);
		CoopBase->setLatitude(lan);

		_game->getSavedGame()->getBases()->push_back(CoopBase);
	}

}

void connectionTCP::fixCoopSave()
{
	if (_game->getSavedGame() && !_game->getSavedGame()->getSavedBattle() && getCoopCampaign() == true)
	{

		int newID = -1;
		int alienId = 2000000;
		int lastID = 0;

		for (auto& base : *_game->getSavedGame()->getBases())
		{
			auto* soldiers = base->getSoldiers();

			for (auto it = soldiers->begin(); it != soldiers->end();)
			{
				auto* soldier = *it;

				// Check that if the game mode is not PvE2, the soldiers are not aliens.
				if (getCoopGamemode() != 4 && newID == -1)
				{

					// If the soldier ID is greater than 2000000
					if (soldier->getId() >= alienId)
					{
						newID = lastID + 1;
					}
					else
					{
						lastID = soldier->getId();
					}

				}

				if (newID != -1)
				{
					soldier->setId(newID++);
				}

				// For all soldiers where coopbase is not -1, make sure their craft is null.
				if (soldier->getCoopBase() != -1)
				{
					soldier->setCraft(nullptr);
				}

				// If the base coop ID matches the soldier coopbase in the save, delete the soldier.
				if (base->_coop_base_id == soldier->getCoopBase())
				{
					delete soldier;
					it = soldiers->erase(it); // Remove the pointer from the container and continue safely.
					continue;
				}

				++it;
			}
		}
	}
}

bool valid_port(const std::string& s)
{
	if (s.empty())
		return false;

	if (!std::all_of(s.begin(), s.end(), [](unsigned char c)
					 { return std::isdigit(c); }))
	{
		return false;
	}

	int port = std::stoi(s);
	return port >= 0 && port <= 65535;
}

void connectionTCP::hostTCPServer(std::string servername, std::string str_port)
{

	sendTcpServerName = servername;
	gamePaused = 0;
	_waitBC = false;
	_waitBH = false;
	_battleWindow = false;
	_battleInit = false;
	coopInventory = false;
	coopMissionEnd = false;
	inventory_battle_window = true;

	int port = -1;

	if (valid_port(str_port))
	{
		port = std::stoi(str_port);
	}

	if (port == -1)
	{
		tcp_port = 3000;
	}
	else
	{
		tcp_port = port;
	}

	if (_hostThread.joinable())
	{
		_hostStop = true;
		_hostThread.join();
	}

	session.beginHosting();

	_hostStop = false;
	 _hostThread = std::thread(&connectionTCP::startTCPHost, this);

}

void connectionTCP::connectTCPServer(std::string ipaddress, std::string str_port)
{
	ipAddress = ipaddress;
	gamePaused = 0;
	_waitBC = false;
	_waitBH = false;
	_battleWindow = false;
	_battleInit = false;
	coopInventory = false;
	coopMissionEnd = false;
	inventory_battle_window = true;

	int port = -1;

	if (valid_port(str_port))
	{
		port = std::stoi(str_port);
	}

	if (port == -1)
	{
		tcp_port = 3000;
	}
	else
	{
		tcp_port = port;
	}

	if (_clientThread.joinable())
	{
		_clientStop = true;
		_clientThread.join();
	}

	session.beginJoining();

	_clientStop = false;

	_clientThread = std::thread(&connectionTCP::startTCPClient, this);

}

// Test/LAN transport: bring up the REAL connectionUDP transport threads on a
// direct 127.0.0.1 session (no rendezvous), so the coop harness can exercise the
// UDP path per-test. Mirrors hostTCPServer/connectTCPServer state, swapping only
// the transport start. Session is derived from the shared password (both peers).
void connectionTCP::hostDirectLanUDP(std::string str_port, std::string player, std::string password)
{
	gamePaused = 0;
	_waitBC = false;
	_waitBH = false;
	_battleWindow = false;
	_battleInit = false;
	coopInventory = false;
	coopMissionEnd = false;
	inventory_battle_window = true;

	int port = -1;
	if (valid_port(str_port))
		port = std::stoi(str_port);
	tcp_port = (port == -1) ? 3000 : port;

	session.beginHosting();
	startDirectLanHost(static_cast<uint16_t>(tcp_port), player, password);
}

void connectionTCP::joinDirectLanUDP(std::string ipaddress, std::string str_port,
									 std::string str_localport, std::string player, std::string password)
{
	ipAddress = ipaddress;
	gamePaused = 0;
	_waitBC = false;
	_waitBH = false;
	_battleWindow = false;
	_battleInit = false;
	coopInventory = false;
	coopMissionEnd = false;
	inventory_battle_window = true;

	int port = -1;
	if (valid_port(str_port))
		port = std::stoi(str_port);
	tcp_port = (port == -1) ? 3000 : port;

	int lport = -1;
	if (valid_port(str_localport))
		lport = std::stoi(str_localport);
	uint16_t localPort = (lport == -1) ? static_cast<uint16_t>(3001) : static_cast<uint16_t>(lport);

	session.beginJoining();
	startDirectLanJoin(ipaddress, static_cast<uint16_t>(tcp_port), localPort, player, password);
}

// coop
void connectionTCP::setConfirmLandingState(ConfirmLandingState* landing)
{
	_landing = landing;
	_cydonia = nullptr;
}

void connectionTCP::setConfirmCydoniaState(ConfirmCydoniaState* cydonia)
{
	_cydonia = cydonia;
	_landing = nullptr;
}

// coop
void connectionTCP::setNewBattleState(NewBattleState* battlesate)
{
	_battleState = battlesate;
}

void connectionTCP::setGeoscapeState(GeoscapeState* base_geo)
{
	_geo = base_geo;
}

NewBattleState* connectionTCP::getNewBattleState()
{
	return _battleState;
}

bool connectionTCP::getLanding()
{

	if (_landing != nullptr)
	{
		return true;
	}

	return false;
}

void connectionTCP::setSelectedCraft(Craft* selectedCraft)
{
	_selectedCraft = selectedCraft;
}

Craft* connectionTCP::getSelectedCraft()
{
	return _selectedCraft;
}

void connectionTCP::sendTCPPacketData(std::string data)
{
	if (data.empty())
		return;
	if (!g_txQ.push(std::move(data)))
	{
		DebugLog("TX queue full, dropping packet\n");
		++g_txDropCount;
	}
}

void connectionTCP::sendCoopSnapshot(int slot, std::string data)
{
	if (data.empty())
		return;
	// Full-state last-write-wins snapshot -> conflation slot, not the FIFO. The
	// send drain emits the freshest value at link rate; stale copies are elided,
	// so the geoscape flood can never overflow g_txQ.
	enqueueSnapshot(static_cast<CoopSnapSlot>(slot), std::move(data));
}

bool connectionTCP::geoMembershipChanged(const Json::Value& root)
{
	// Compare the set of UFO/mission coop ids in this snapshot to the last one.
	// A change means something spawned or despawned -> the caller must deliver
	// this snapshot reliably (the conflation slot may drop it otherwise).
	std::set<int> ufoIds, missionIds;
	if (root.isMember("ufos"))
	{
		for (const auto& u : root["ufos"])
			ufoIds.insert(u["ufo_id"].asInt());
	}
	if (root.isMember("missions"))
	{
		for (const auto& m : root["missions"])
			missionIds.insert(m["mission_id"].asInt());
	}
	bool changed = (ufoIds != _lastGeoUfoIds) || (missionIds != _lastGeoMissionIds);
	_lastGeoUfoIds.swap(ufoIds);
	_lastGeoMissionIds.swap(missionIds);
	return changed;
}

void connectionTCP::setPlayerTurn(int turn)
{
	_playerTurn = turn;
}

void connectionTCP::sendFile()
{
	sendFileClient = true;
}

int connectionTCP::isConnected()
{
	return onConnect;
}

void connectionTCP::setConnected(int state)
{
	onConnect = state;
}

// disconnect the connection
void connectionTCP::disconnectTCP(bool isMain)
{
		// A finished custom battle has already left the tactical world, so
		// coopBattleLive() is false while its DebriefingState is still open.
		// Remember that exact state before teardown resets the session: a client
		// leaving at the results screen must not send the host back to the lobby.
		bool customBattleDebriefing = false;
		if (_game && _game->getSavedGame()
			&& _game->getSavedGame()->getMonthsPassed() == -1)
		{
			for (State* st : _game->getStates())
			{
				if (dynamic_cast<DebriefingState*>(st) != nullptr)
				{
					customBattleDebriefing = true;
					break;
				}
			}
		}

		_waitBC = false;
		_waitBH = false;
		coopSession = false;
		// coop: clear the cached teammate geoscape speed/focus so a stale '+' marker
		// doesn't linger after disconnect.
		peerTimeSpeedId = "";
		peerFocusScreen = -1;
		connectionTCP::lobby_timer = -1;
		connectionTCP::isPlayerReady = false;
		connectionTCP::isPlayersReady = false;

		connectionTCP::LobbyFileStatus = -1;
		// issue #93: a drop mid-mission is a freeze, not the end of the session -
		// the peer is expected back in the SAME battle, and the game mode
		// (PVE/PVP/PVE2) decides which units each machine commands. Zeroing it
		// here would hand a rejoining player the wrong side of its own battle.
		if (!coopBattleLive(_game))
		{
			connectionTCP::_coopGamemode = 0;
		}
		connectionTCP::show_inactive_player_inventory = false;
		// A transport drop can happen while VoteMenu is the top state. Mark it as
		// cancelled before clearing the controller state so the popup always gains
		// a CLOSE button instead of waiting forever for vote_result.
		if (_activeVote.id != 0)
		{
			VoteMenu* voteMenu = findVoteMenu(_activeVote.id);
			if (voteMenu)
			{
				voteMenu->cancelVote();
			}
		}
		_activeVote.clear();
		_voteRequestPending = false;
		_voteStarterCooldownUntil.clear();

	    OpenXcom::disconnectRendezvousUdp();

		// Clear all shared TCP/UDP packet queues after the transport is stopped.
		// This prevents stale packets from the previous session from affecting
		// a newly hosted or joined session.
		OpenXcom::clearNetworkSessionQueues();

		deleteAllCoopBases();

		// Capture the machine role ONCE for this teardown - handlers used to
		// mutate server_owner mid-flight and make the cleanup misclassify the
		// machine (the disconnect->cancel bug family).
		const bool teardownAsHost = (session.role == CoopRole::Host);

		// issue #93: when the host vanishes the client is TOLD, and leaves when it
		// says so. CoopState(21) "Server connection lost" is pushed just before
		// this teardown runs (its ctor calls us), and its OK button owns the trip
		// to the main menu now - so jumping there ourselves would wipe the message
		// the player never got to read, mid-battle worst of all.
		bool lostDialogPresent = false;
		for (State* st : _game->getStates())
		{
			CoopState* cs = dynamic_cast<CoopState*>(st);
			if (cs && cs->getStateCode() == 21)
			{
				lostDialogPresent = true;
				break;
			}
		}

		// both
		// issue #79: not after the campaign has ended. The player is on the
		// defeat/victory statistics screen with their own OK button; yanking
		// them to the main menu because the other side closed the game first
		// is exactly the "one player's exit affects the other" bug.
		// A no_bases host (PvP alien side) must NOT be sent to the main menu
		// here — the freeze dialog handles the reconnection flow, and ripping
		// the world out from under it breaks rejoin entirely.
		if (!teardownAsHost && !isMain
			&& connectionTCP::_coopCampaign == true && !campaignEnded()
			&& !lostDialogPresent)
		{
			// issue #82: via GoToMainMenuState so the battle this client was in is
			// dropped with the rest of the world - a battle left on the SavedGame hands
			// the battlescape palette to every menu opened afterwards.
			_game->setState(new GoToMainMenuState(false));
		}

		// host
		if (teardownAsHost && onConnect == -2)
		{

			onConnect = 1;

			// issue #93: route on "is a mission running", not on the lobby mode.
			// A skirmish (NEW BATTLE > COOP) battle used to raise the LOBBY over
			// the tactical map on a drop - a menu whose RESUME GAME then threw the
			// battle away - while the campaign path already did the right thing.
			// A drop with no battle running (host still on the NEW BATTLE setup
			// screen) keeps re-opening the lobby: that IS where it belongs.
			if ((connectionTCP::session.lobbyMode != 0 || coopBattleLive(_game))
				&& connectionTCP::session.lobbyClosed == true)
			{
				// mid-session client drop: wait until they reconnect (D5). The
				// dialog sits over the geoscape/battlescape, pausing it. Never
				// stack a second one when a player-wait is already present
				// ANYWHERE in the stack, not just on top - two of them means two
				// RESUME buttons and a double campaign_begun broadcast (C9). The
				// one already there re-words itself for the drop, so it covers
				// this case (CoopState::waitingTitle).
				bool waitDialogPresent = false;
				for (State* st : _game->getStates())
				{
					CoopState* cs = dynamic_cast<CoopState*>(st);
					if (cs && cs->getStateCode() == COOP_DLG_WAIT_PLAYERS)
					{
						waitDialogPresent = true;
						break;
					}
				}
				// issue #79: and never once the campaign is over. After a
				// defeat/victory there is nothing left to do together, so a
				// client walking away is not a drop to freeze and wait on -
				// the host must be free to finish its own end-of-game screens.
				if (campaignEnded())
				{
					Log(LOG_INFO) << "[coop] freeze dialog suppressed: the campaign "
						"has ended; the peer has nothing left to reconnect for";
				}
				else if (!waitDialogPresent)
				{
					connectionTCP::session.freeze();
					_game->pushState(new CoopState(COOP_DLG_WAIT_PLAYERS));
				}
				else
				{
					Log(LOG_INFO) << "[coop] freeze dialog suppressed: a campaign "
						"wait dialog (freeze/resume-ack) is already on the stack";
				}
			}
			else if (connectionTCP::session.lobbyClosed == true
				&& !customBattleDebriefing)
			{
				_game->pushState(new LobbyMenu);
			}
			else if (customBattleDebriefing)
			{
				Log(LOG_INFO) << "[coop] lobby suppressed: client disconnected "
					"while the host was viewing custom-battle debriefing";
			}

		}
		// client
		else
		{

			onConnect = -1;

			// The client's world came from the host and is re-streamed on the
			// next join; drop the session's blobs.
			{
				std::lock_guard<std::mutex> lock(coopFilesMutex);
				connectionTCP::coopFilesClient.clear();
			}

			if (_chatMenu)
			{

				_chatMenu->setActive(false);
				_chatMenu->clearMessages();

				delete getChatMenu();
				setChatMenu(nullptr);
			}

		}

		// Session-state resets: exactly two paths (see CoopSession). The host
		// keeps its campaign/lobby context across a peer drop (D5); a client's
		// session is over. Never clear individual fields here.
		if (teardownAsHost)
		{
			connectionTCP::session.onClientDrop();
		}
		else
		{
			connectionTCP::session.resetSession();
		}

		connectionTCP::no_bases = false;
		connectionTCP::isCoopBaseLoading = false;

		gamePaused = 0;
		playerInsideCoopBase = false;

		_coop_task_completed = true;

		_isActiveAISync = false;

		_isActivePlayerSync = false;

		_clientPanicHandle = false;

		sendFileClient = false;
		sendFileBase = false;
		sendFileHost = false;
		sendFileSave = false;
		onceTime = false;

		isWaitMap = true;
		_hasHitUnit = -1;

		_game->getCoopMod()->pve2_init = false;

		setPlayerTurn(2);

		_battleWindow = false;
		_battleInit = false;

		coopInventory = false;

		// R1-P4: the BattlescapeState::setCurrentTurn(2) mirror write that used
		// to run here is gone - a coop hook the r1 vanilla restore stripped.
		// setPlayerTurn(2) above (connectionTCP's own tracked state) is the
		// surviving source of truth; the mirror returns with r2 (RB-D9/RB-D11).
}

std::string connectionTCP::getCurrentClientName()
{
	return tcpPlayerName;
}

std::string connectionTCP::getCurrentClientServer()
{
	return tcpServerName;
}

void connectionTCP::setCurrentClientServer(std::string servername)
{
	tcpServerName = servername;
}

std::string connectionTCP::getHostName()
{
	return sendTcpPlayer;
}

std::string connectionTCP::getHostServer()
{
	return sendTcpServerName;
}

void connectionTCP::setHostName(std::string playername)
{
	sendTcpPlayer = playername;
}

void connectionTCP::setHostServer(std::string servername)
{
	sendTcpServerName = servername;
}

void connectionTCP::writeHostMapFile()
{

	if (mapData.empty())
		return;

	if (connectionTCP::getServerOwner() == true)
	{

		std::string filename = "battleclient";

		{
			std::lock_guard<std::mutex> lock(coopFilesMutex);
			connectionTCP::coopFilesHost[filename] = std::move(mapData);
		}

		// RECEIVE CLIENT DATA
		SavedGame* client_save = new SavedGame();

		client_save->loadCoopSaveFromMemory(filename, _game->getMod(), _game->getLanguage(), filename);

		if (client_save && _game->getCoopMod()->getCoopCampaign() == true && _game->getCoopMod()->getServerOwner() == true)
		{

			std::string filename = hostBlobKey(_game->getCoopMod()->getCurrentClientName());

			// served copy lives in memory only; the host .sav embed persists it
			client_save->saveCoopToMemory(filename, _game->getMod(), filename);
			{
				std::lock_guard<std::mutex> lock(coopFilesMutex);
				eraseStaleBlobEntries(coopFilesHost, "host_", _game->getCoopMod()->getCurrentClientName(), filename);
			}

		}

		delete client_save;

	}
	else
	{
		std::lock_guard<std::mutex> lock(coopFilesMutex);
		connectionTCP::coopFilesClient["battleclient"] = std::move(mapData);
	}

	// the map data must be reset for the next use (fix)
	mapData = "";
}

bool connectionTCP::writeHostMapSaveProgressFile()
{

	std::string filename = hostBlobKey(_game->getCoopMod()->getCurrentClientName());

	if (mapData.empty())
		return false;

	// PRD-07 C10: validate the incoming blob BEFORE it touches the store. The
	// previous order installed (and pruned siblings) first, so a blob that
	// failed validation had already displaced the last-good one. Here we parse
	// a throwaway COPY under a scratch key, leaving mapData and the real entry
	// untouched; only a blob that passes every check is installed.
	static const std::string scratchKey = "__validate_save_progress__";
	{
		std::lock_guard<std::mutex> lock(coopFilesMutex);
		connectionTCP::coopFilesHost[scratchKey] = mapData; // copy, not move
	}

	SavedGame* coopFile = new SavedGame();
	coopFile->loadCoopSaveFromMemory(scratchKey, _game->getMod(), _game->getLanguage(), scratchKey);

	bool error = false;
	bool found = false;

	if (coopFile)
	{

		for (auto& base : *coopFile->getBases())
		{

			if (base->_coopBase == false)
			{
				found = true;
			}

			if (base->getName().empty() || (base->getLongitude() == 0 && base->getLatitude() == 0))
			{
				error = true;
				break;
			}

		}

	}
	else
	{
		error = true;
	}

	bool stored = (error == false && coopFile && found == true);

	std::string failReason;
	if (!stored)
	{
		failReason = (coopFile == nullptr) ? "parse failed"
			: error ? "base with empty name or null coords"
			: "no non-coop (own) base present";
	}

	delete coopFile;

	// drop the scratch entry either way - it never becomes the served blob.
	{
		std::lock_guard<std::mutex> lock(coopFilesMutex);
		connectionTCP::coopFilesHost.erase(scratchKey);
	}

	if (!stored)
	{
		// Failure path: leave the store EXACTLY as it was (the last-good blob
		// stays served + embeddable) and surface the error popup.
		Log(LOG_WARNING) << "[coop] rejected client progress blob from '"
						  << _game->getCoopMod()->getCurrentClientName() << "': " << failReason
						  << "; keeping last-good blob";
		_game->pushState(new CoopState(994));

		// the map data must be reset for the next use (fix)
		mapData = "";
		return false;
	}

	// Success: install the validated blob + prune stale siblings. The served
	// copy lives in memory only; persistence is the blob embedded in the host .sav.
	{
		std::lock_guard<std::mutex> lock(coopFilesMutex);
		connectionTCP::coopFilesHost[filename] = std::move(mapData);
		eraseStaleBlobEntries(coopFilesHost, "host_", _game->getCoopMod()->getCurrentClientName(), filename);
	}

	// the map data must be reset for the next use (fix)
	mapData = "";

	return true;
}

void connectionTCP::writeHostMapLoadProgressFile()
{

	std::string filename = clientBlobKey(_game->getCoopMod()->getHostName());

	if (mapData.empty())
		return;

	{
		std::lock_guard<std::mutex> lock(coopFilesMutex);
		connectionTCP::coopFilesClient[filename] = std::move(mapData);
		eraseStaleBlobEntries(coopFilesClient, "client_", _game->getCoopMod()->getHostName(), filename);
	}

	// the map data must be reset for the next use (fix)
	mapData = "";

}

}



