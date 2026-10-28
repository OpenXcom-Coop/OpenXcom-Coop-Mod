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

#include "HostMenu.h"
#include "../Menu/SaveGameState.h"
#include "../Menu/LoadGameState.h"
#include "../Menu/MainMenuState.h"
#include "CoopState.h"
#include "../Mod/ExtraSprites.h"
#include "../Engine/Surface.h"
#include "Profile.h"
#include "ChatMenu.h"
#include "connectionUDP/connection_rendezvous_glue.h"
#include "BattleAuthority.h" // W1-P7 deliverable 6: coopTurnMode* helpers (D-19)

namespace OpenXcom
{

/**
 * Initializes all the elements in the New Battle window.
 * @param game Pointer to the core game.
 */
HostMenu::HostMenu() : _craft(0), _selectType(NewBattleSelectType::MISSION), _isRightClick(false)
{

	// coop chat menu
	if (!_game->getCoopMod()->getChatMenu())
	{
		Font* smallFont = _game->getMod()->getFont("FONT_SMALL");
		_game->getCoopMod()->setChatMenu(new ChatMenu(smallFont, _game));
	}

	_screen = false;

	int x = 20;
	
	// Create objects
	// coop (W1-P7 deliverable 6, D-19): DONOR GEOMETRY, byte-for-byte from
	// `cbff7951d:HostMenu.cpp:54-71` - the window is 18px taller than stock, the
	// TURN MODE toggle takes the old button row (152) and START HOST / CANCEL
	// move down to 172.
	_window = new Window(this, 260, 178, x, 20, POPUP_BOTH);
	_lstSaves = new TextList(224, 18, x + 18, 60);

	_lblServerName = new Text(108, 18, x + 18, 72);
	_lblPort = new Text(108, 18, x + 18, 92);
	_lblPassword = new Text(108, 18, x + 18, 132);

	_port = new TextEdit(this, 116, 18, x + 126, 92);
	_serverName = new TextEdit(this, 116, 18, x + 126, 72);
	_tcpButtonHost = new TextButton(112, 18, x + 18, 172);
	_btnTurnMode = new TextButton(224, 18, x + 18, 152);
	_cbxVisibility = new ComboBox(this, 224, 18, x + 18, 50);
	_cbxRegions = new ComboBox(this, 112, 18, x + 18, 112); 
	_cbxMaxPlayers = new ComboBox(this, 112, 18, x + 130, 112); 
	_password = new TextEdit(this, 116, 18, x + 126, 132);
	_btnCancel = new TextButton(112, 18, x + 130, 172);
	_txtTitle = new Text(250, 17, x + 5, 32);

	int screenWidth = Options::baseXGeoscape;
	int screenHeight = Options::baseYGeoscape;


	// Set palette
	setInterface("pauseMenu", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);


	add(_window, "window", "pauseMenu");
	add(_lblServerName, "text", "pauseMenu");
	add(_lblPort, "text", "pauseMenu");
	add(_lblPassword, "text", "pauseMenu");
	add(_port, "text", "pauseMenu");
	add(_serverName, "text", "pauseMenu");
	add(_password, "text", "pauseMenu");
	add(_tcpButtonHost, "button", "pauseMenu");
	add(_btnTurnMode, "button", "pauseMenu");
	add(_btnCancel, "button", "pauseMenu");
	add(_cbxVisibility, "button", "pauseMenu");
	add(_cbxRegions, "button", "pauseMenu");
	add(_cbxMaxPlayers, "button", "pauseMenu");
	add(_txtTitle, "text", "pauseMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "pauseMenu");

	Uint8 color = 500; // 500 or 255

	if (_game->getSavedGame())
	{
		if (_game->getSavedGame()->getSavedBattle())
		{
			
			applyBattlescapeTheme("pauseMenu");
			color = 255;
			
		}
	}

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	// PRD-J01: show the campaign economy model read-only beside the HOST title.
	std::string hostTitle = tr("HOST");
	if (_game->getSavedGame() && _game->getSavedGame()->isCoopSave())
	{
		hostTitle += (_game->getSavedGame()->getCampaignType() == CoopCampaignType::Shared)
			? "  [SHARED]" : "  [SEPARATE]";
	}
	_txtTitle->setText(hostTitle);

	// labels
	_lblServerName->setBig();
	_lblServerName->setBorderColor(color);
	_lblServerName->setText("GAME NAME>");
	_lblServerName->setVisible(false);

	_lblPort->setBig();
	_lblPort->setBorderColor(color);
	_lblPort->setText("PORT>");
	_lblPort->setVisible(false);

	_lblPassword->setBig();
	_lblPassword->setBorderColor(color);
	_lblPassword->setText("PASSWORD>");
	_lblPassword->setVisible(false);

	// port
	_port->setColor(color);
	_port->setBig();
	_port->setBorderColor(color);
	_port->setConstraint(TEC_NUMERIC_POSITIVE);
	_port->setAllowOverflow(true);
	_port->setAllowClipboardPaste(true, true);
	_port->setText("61008");
	_port->setVisible(false);

	_serverName->setColor(color);
	_serverName->setBig();
	_serverName->setBorderColor(color);
	_serverName->setAllowOverflow(true);
	_serverName->setText("Vigilo Confido");
	_serverName->setVisible(false);
	
	_tcpButtonHost->setText("START HOST");
	_tcpButtonHost->onMouseClick((ActionHandler)&HostMenu::hostTCPGame);
	_tcpButtonHost->setVisible(true);

	// coop (W1-P7 deliverable 6, D-19): the TURN MODE toggle. Label + visibility
	// are driven by updateTurnModeButton() - called here and after every one of
	// the three places that flip the hosting controls' visibility, the same four
	// call points the donor used.
	_btnTurnMode->onMouseClick((ActionHandler)&HostMenu::btnTurnModeClick);
	updateTurnModeButton();

	_btnCancel->setText(tr("CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&HostMenu::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&HostMenu::btnCancelClick, Options::keyCancel);

	_visibilityTypes.push_back("VISIBILITY: PRIVATE (TCP)");
	_visibilityTypes.push_back("VISIBILITY: PRIVATE (UDP)");
	_visibilityTypes.push_back("VISIBILITY: PUBLIC (UDP)");
	// Hotseat is a local skirmish mode, not a networked visibility. It is armed
	// from the New Battle screen (NewBattleState) instead of this host dialog.
	_cbxVisibility->setOptions(_visibilityTypes, false);
	_cbxVisibility->onChange((ActionHandler)&HostMenu::cbxVisibilityChange);

	_regionTypes.push_back("NORTH AMERICA");
	_regionTypes.push_back("ARCTIC");
	_regionTypes.push_back("ANTARCTICA");
	_regionTypes.push_back("SOUTH AMERICA");
	_regionTypes.push_back("EUROPE");
	_regionTypes.push_back("NORTH AFRICA");
	_regionTypes.push_back("SOUTHERN AFRICA");
	_regionTypes.push_back("CENTRAL ASIA");
	_regionTypes.push_back("SOUTH EAST ASIA");
	_regionTypes.push_back("SIBERIA");
	_regionTypes.push_back("AUSTRALASIA");
	_regionTypes.push_back("PACIFIC");
	_regionTypes.push_back("NORTH ATLANTIC");
	_regionTypes.push_back("SOUTH ATLANTIC");
	_regionTypes.push_back("INDIAN OCEAN");
	_cbxRegions->setOptions(_regionTypes, false);
	_cbxRegions->onChange((ActionHandler)&HostMenu::cbxRegionChange);

	_maxplayersTypes.push_back("MAX PLAYERS: 2");
	_cbxMaxPlayers->setOptions(_maxplayersTypes, false);
	_cbxMaxPlayers->onChange((ActionHandler)&HostMenu::cbxMaxPlayersChange);

	_password->setColor(color);
	_password->setBig();
	_password->setBorderColor(color);
	_password->setAllowOverflow(true);
	_password->setBorderColor(color);
	_password->setText("");
	_password->setVisible(false);

	// check if campaign mission
	if (!_game->getSavedGame()->getCountries()->empty())
	{
		_game->getCoopMod()->setCoopCampaign(true);
	}
	else
	{

		_game->getCoopMod()->setCoopCampaign(false);
	}

	// Hide the hosting controls only while a session is genuinely live (a
	// peer is attached). Keying on isConnected()/getServerOwner() left stale
	// transport state (esp. after UDP host/disconnect cycles) blanking the
	// whole window down to the CANCEL button.
	if (_game->getCoopMod()->getCoopStatic() == true && _game->getCoopMod()->isCoopSession() == true)
	{

		_port->setVisible(false);
		_lblPort->setVisible(false);
		_serverName->setVisible(false);
		_lblServerName->setVisible(false);
		_tcpButtonHost->setVisible(false);
		_cbxVisibility->setVisible(false);
		_password->setVisible(false);
		_lblPassword->setVisible(false);
		_cbxMaxPlayers->setVisible(false);
		_cbxRegions->setVisible(false);

	}
	else if (_game->getCoopMod()->isConnected() == -1)
	{
		_port->setVisible(true);
		_lblPort->setVisible(true);
		_serverName->setVisible(true);
		_lblServerName->setVisible(true);
		_tcpButtonHost->setVisible(true);
		_cbxVisibility->setVisible(true);
		_password->setVisible(true);
		_lblPassword->setVisible(true);
		_cbxMaxPlayers->setVisible(true);
		_cbxRegions->setVisible(true);

	}
	updateTurnModeButton(); // coop (W1-P7 deliverable 6, D-19)

	// READ HOST ADDRESS

	// Name of the JSON file
	std::string filename = "host_address.json";
	std::string filepath = Options::getMasterUserFolder() + filename;

	std::string port;
	std::string serverName;
	std::string password;

	if (OpenXcom::CrossPlatform::fileExists(filepath))
	{
		std::ifstream file(filepath, std::ifstream::binary);
		if (file.is_open())
		{
			Json::Value root;
			Json::CharReaderBuilder builder;
			std::string errs;

			bool parsingSuccessful = Json::parseFromStream(builder, file, &root, &errs);
			file.close();

			if (parsingSuccessful)
			{
				port = root.get("port", "").asString();
				serverName = root.get("server", "").asString();
				password = root.get("password", "").asString();

				
				if (port == "")
				{
					// port is empty
					port = "3000";
				}


				if (serverName == "")
				{
					// name is empty
					serverName = "Vigilo Confido";
				}

				_port->setText(port);
				_serverName->setText(serverName);
				if (password != "")
				{
					_password->setText(password);
				}
			}
			else
			{
				std::cerr << "Failed to parse JSON: " << errs << std::endl;
			}
		}
		else
		{
			std::cerr << "Failed to open the file." << std::endl;
		}
	}

}

/**
 *
 */
HostMenu::~HostMenu()
{
}

/**
 * Resets the menu music and savegame
 * when coming back from the battlescape.
 */
void HostMenu::init()
{

	// Hide the hosting controls only while a session is genuinely live (a
	// peer is attached). Keying on isConnected()/getServerOwner() left stale
	// transport state (esp. after UDP host/disconnect cycles) blanking the
	// whole window down to the CANCEL button.
	if (_game->getCoopMod()->getCoopStatic() == true && _game->getCoopMod()->isCoopSession() == true)
	{

		_port->setVisible(false);
		_lblPort->setVisible(false);
		_serverName->setVisible(false);
		_lblServerName->setVisible(false);
		_tcpButtonHost->setVisible(false);
		_cbxVisibility->setVisible(false);
		_password->setVisible(false);
		_lblPassword->setVisible(false);
		_cbxMaxPlayers->setVisible(false);
		_cbxRegions->setVisible(false);

	}
	else if (_game->getCoopMod()->isConnected() == -1)
	{
		_port->setVisible(true);
		_lblPort->setVisible(true);
		_serverName->setVisible(true);
		_lblServerName->setVisible(true);
		_tcpButtonHost->setVisible(true);
		_cbxVisibility->setVisible(true);
		_password->setVisible(true);
		_lblPassword->setVisible(true);
		_cbxMaxPlayers->setVisible(true);
		_cbxRegions->setVisible(true);

	}
	updateTurnModeButton(); // coop (W1-P7 deliverable 6, D-19)
}

void HostMenu::convertUnits()
{
	// coop: a single-player Custom Battle hosted from the
	// pause menu becomes a classic co-op battle before the lobby opens (the R1-P5 stub's silent refusal is gone, F5296). Soldiers
	// split in unit-list order (v2.0.6's order): the second player (seat 1) takes the first floor(N/2), the host (seat 0) the rest -
	// the extra one of an odd squad, a 1-soldier squad included. Every other original-PLAYER unit (a tank) is the host's; every
	// other unit has no seat. Each soldier's owner follows its seat (as NewBattleState seats a fresh co-op battle). The battle
	// plays in the host window's TURNS mode and the traditional baton opens at the first live seat (D-23); offerResumedBattle()
	// rebuilds the seat->faction store from these tags.
	SavedBattleGame* battle = _game->getSavedGame()->getSavedBattle();
	if (!battle)
	{
		return;
	}
	int soldiers = 0;
	for (auto* unit : *battle->getUnits())
	{
		if (unit && unit->getOriginalFaction() == FACTION_PLAYER && unit->getGeoscapeSoldier())
			++soldiers;
	}
	int toClient = soldiers / 2;
	int seat0 = 0, seat1 = 0, others = 0, unseated = 0;
	for (auto* unit : *battle->getUnits())
	{
		if (!unit)
			continue;
		if (unit->getOriginalFaction() != FACTION_PLAYER)
		{
			unit->setCoopSeat(COOP_SEAT_NONE);
			++unseated;
			continue;
		}
		Soldier* soldier = unit->getGeoscapeSoldier();
		CoopSeat seat = COOP_SEAT_0;
		if (soldier && toClient > 0)
		{
			seat = COOP_SEAT_1;
			--toClient;
		}
		unit->setCoopSeat(seat);
		if (soldier)
			soldier->setCoop((int)seat);
		if (seat == COOP_SEAT_1)
			++seat1;
		else if (soldier)
			++seat0;
		else
			++others;
	}
	connectionTCP::_coopGamemode = 1;
	coopBattleAuthority().turnMode = coopSessionTurnModeFromOptions();
	coopBattleAuthority().activeSeat = -1;
	Log(LOG_INFO) << "[coop] MG-B: the single-player Custom Battle is now co-op: " << soldiers << " soldier(s), seat 1: "
		<< seat1 << ", seat 0: " << seat0 << " + " << others << " other unit(s), " << unseated << " unit(s) unseated, turn mode "
		<< coopTurnModeName(coopBattleAuthority().turnMode.load());
}

void HostMenu::btnChatClick(Action* action)
{

	if (_game->getCoopMod()->getChatMenu())
	{

		_game->getCoopMod()->getChatMenu()->setActive(!_game->getCoopMod()->getChatMenu()->isActive());

	}

}

void HostMenu::cbxVisibilityChange(Action* action)
{

	int selected_gamemode = _cbxVisibility->getSelected();

	// show
	_tcpButtonHost->setVisible(true);
	_port->setVisible(true);
	_lblPort->setVisible(true);
	_serverName->setVisible(true);
	_lblServerName->setVisible(true);
	_password->setVisible(true);
	_lblPassword->setVisible(true);
	_cbxMaxPlayers->setVisible(true);
	_cbxRegions->setVisible(true);

	// UDP (private)
	if (selected_gamemode == 1)
	{
		_isUDPconnection = true;
		isListed = false;
	}
	// UDP (public)
	else if (selected_gamemode == 2)
	{
		_isUDPconnection = true;
		isListed = true;
	}
	// TCP
	else if (selected_gamemode == 0)
	{
		_isUDPconnection = false;
	}

	updateTurnModeButton(); // coop (W1-P7 deliverable 6, D-19)
}

void HostMenu::cbxMaxPlayersChange(Action* action)
{
}

void HostMenu::cbxRegionChange(Action*)
{

	int selected_region = _cbxRegions->getSelected();

	if (_cbxRegions->getSelected() && selected_region >= 0 && selected_region < _regionTypes.size())
	{
		selectedRegion = _regionTypes[selected_region];
	}
	else
	{
		selectedRegion = "NORTH AMERICA";
	}

}

void HostMenu::hostTCPGame(Action* action)
{

	// Solo campaigns can never be hosted as co-op (flow-redesign D1):
	// co-op campaigns are created from the New Game menu or resumed from a
	// co-op save. One-off battles (no countries) are unaffected.
	if (_game->getSavedGame()
		&& !_game->getSavedGame()->getCountries()->empty()
		&& !_game->getSavedGame()->isCoopSave())
	{
		_game->pushState(new CoopState(61));
		return;
	}

	// Legacy-save migration: the synthesized roster leaves the host slot
	// blank (pre-redesign saves carry no host name). Whoever re-hosts the
	// migrated save claims the slot - from then on D4 locks it as usual.
	if (_game->getCoopMod()->inCoopCampaignContext()
		&& !_game->getSavedGame()->getCoopPlayers().empty()
		&& _game->getSavedGame()->getCoopPlayers()[0].empty())
	{
		std::vector<std::string> players = _game->getSavedGame()->getCoopPlayers();
		players[0] = _game->getCoopMod()->getHostName();
		_game->getSavedGame()->setCoopPlayers(players);
		Log(LOG_INFO) << "[coop-migrate] locked legacy roster host slot to '" << players[0] << "'";
	}

	// the host identity is locked to the save (D4): a different local player
	// name may never host this campaign
	if (_game->getCoopMod()->inCoopCampaignContext()
		&& !_game->getSavedGame()->getCoopPlayers().empty()
		&& _game->getSavedGame()->getCoopPlayers()[0] != _game->getCoopMod()->getHostName())
	{
		_game->pushState(new CoopState(66));
		return;
	}

	// campaign co-op save: (re)derive the lobby mode from the save so a
	// disconnect + re-host cannot fall back to the legacy READY lobby - a
	// fresh world (no locked players) starts, an established one resumes
	if (_game->getCoopMod()->inCoopCampaignContext())
	{
		connectionTCP::session.lobbyMode = _game->getSavedGame()->getCoopPlayers().empty() ? 1 : 2;
	}

	// Save host settings to JSON
	{
		std::string filepath = Options::getMasterUserFolder() + "host_address.json";
		Json::Value root;
		root["server"] = _serverName->getText();
		root["port"] = _port->getText();
		root["password"] = _password->getText();

		std::ofstream file(filepath);
		if (file.is_open())
		{
			Json::StreamWriterBuilder writer;
			writer["indentation"] = "\t";
			file << Json::writeString(writer, root);
			file.close();
		}
	}

	connectionTCP::password = "";
	connectionTCP::isPasswordRequired = false;

	// password
	if (_password->getText() != "")
	{

		connectionTCP::password = _password->getText();
		connectionTCP::isPasswordRequired = true;

	}

	// coop D250-U S-C4a (QC-16 (a), QC4A-1 (a); F5106; `main`'s preserveLoadedMode shape): a co-op campaign RESUME (lobbyMode 2,
	// derived above from the save's locked roster) keeps the PvP mode the save was played in - PVP (2) or PVP2 (3) - so the lobby,
	// the world service and every battle read it. Every other host starts as PVE (1), as before.
	// coop W2-H46 (L-SC5-1; QC-16 (a), QC4A-1 (a), R-H46-0; F17080-F17085, F17203): the kept PvP mode is the save's own
	// (SavedGame::getCoopLoadedGamemode, written only by SavedGame::load), not the live one: the host's own DISCONNECT in the
	// resume lobby zeroes the live mode (disconnectTCP), so a second START HOST in the same session read 0 and resumed the
	// PvP campaign as PVE (1) on both machines. Restored here; every other host starts as PVE (1) below, as before.
	const int coopLoadedMode = (_game->getCoopMod()->inCoopCampaignContext() && connectionTCP::session.lobbyMode == 2)
		? _game->getSavedGame()->getCoopLoadedGamemode() : 0;
	const bool coopKeepLoadedPvpMode = coopLoadedMode == 2 || coopLoadedMode == 3;
	if (coopKeepLoadedPvpMode)
	{
		connectionTCP::_coopGamemode = coopLoadedMode;
	}
	// coop: `main` #181 also keeps the loaded mode for a saved Custom Battle co-op resume.
	if (!(coopKeepLoadedPvpMode || connectionTCP::session.customBattleResumePending))
	{
		connectionTCP::_coopGamemode = 1;
	}

	_game->getCoopMod()->setCoopSession(false);

	// (no field-hiding here: this menu is popped right below, and hiding the
	// controls first could strand a blank window with just CANCEL whenever a
	// path re-surfaced the instance - the UDP host/disconnect-cycle bug)

	_game->getCoopMod()->setPlayerTurn(3);

	bool convert = true;

	if (_game->getSavedGame()->getSavedBattle())
	{

		// check if already converted units...
		for (auto unit : *_game->getSavedGame()->getSavedBattle()->getUnits())
		{

			if ((int)unit->getCoopSeat() == 1)
			{

				convert = false;
				break;
			}
		}

	}
	else
	{

		convert = false;

	}

	// coop: only a single-player Custom Battle hosted from the pause menu (main #181's
	// CONTINUE BATTLE route, customBattleResumePending) converts, and only when no unit carries seat 1 yet (the scan above); a
	// campaign never does, and every other host keeps its battle as it is.
	if (_game->getCoopMod()->getCoopCampaign() == true
		|| !connectionTCP::session.customBattleResumePending)
	{
		convert = false;
	}

	if (convert == true)
	{
		convertUnits();
	}

	// HOST GAME
	// TCP
	if (_isUDPconnection == false)
	{
		_game->getCoopMod()->hostTCPServer(_serverName->getText(), _port->getText());
	}
	// UDP
	else
	{

		std::string udpPassword = "";

		// password
		if (_password->getText() != "")
		{
			udpPassword = _password->getText();
		}

		_game->getCoopMod()->setHostServer(_serverName->getText());

		// init
		_game->getCoopMod()->_waitBC = false;
		_game->getCoopMod()->_waitBH = false;
		_game->getCoopMod()->_battleWindow = false;
		_game->getCoopMod()->_battleInit = false;
		_game->getCoopMod()->coopInventory = false;
		_game->getCoopMod()->coopMissionEnd = false;
		_game->getCoopMod()->inventory_battle_window = true;

		// mod compatibility
		std::vector<std::string> mod_names = _game->getMod()->getCoopModList();
		std::string str_hash;

		for (const auto& mod_name : mod_names)
		{
			str_hash += mod_name + ";";
		}

		OpenXcom::hostListedViaRendezvousAsync(
			_game->getCoopMod()->getHostServer(),  // Public room name shown in the server list.
			udpPassword,						   // Room password. Empty string means public room without password.
			_game->getCoopMod()->getHostName(),	   // Host player name shown to the other player / lobby.
			selectedRegion,                        // Region selected by host, for example "EU", "US", "Asia".
			str_hash,                              // Mod hash. Use this to check matching mod setup.
			isListed,							   // Listed room flag. true = visible in server list, false = private/unlisted.
			_game->getCoopMod()->getCoopCampaign(),// Is it Campaign or Custom Battle.
			std::stoi(_port->getText())			   // Local UDP port. 0 = let the OS choose a free port automatically.
		);

	}

	_game->getCoopMod()->setServerOwner(true);

	// If the player has created a server or joined another player's game, close the ServerList and create the LobbyMenu
	if (_game->getCoopMod()->getCoopCampaign() == true
		|| connectionTCP::session.customBattleResumePending)
	{
		_game->popState();

		_game->pushState(new LobbyMenu());
	}
	else
	{
		// skirmish: popping back to the ServerList is enough - its init() sees
		// the live session and converts itself into the lobby
		_game->popState();
	}

}

void HostMenu::testHostWithVisibility(int comboIndex)
{
	_cbxVisibility->setSelected(comboIndex);
	cbxVisibilityChange(nullptr);
	hostTCPGame(nullptr);
}

/**
 * Test hook: type into the host window's fields and press START HOST. Without
 * this the harness could only host on the window's default port, so a driver
 * that joined on its own port silently never connected.
 */
void HostMenu::testHostWithFields(int comboIndex, const std::string& server,
								  const std::string& port, const std::string& password)
{
	if (!server.empty()) _serverName->setText(server);
	if (!port.empty()) _port->setText(port);
	_password->setText(password);
	testHostWithVisibility(comboIndex);
}

/**
 * coop (W1-P7 deliverable 6, WAVE1-RUNBOOK.md REV D owner ruling D-19 = WV-D55):
 * the TURN MODE toggle. Flips the HOST's remembered preference between the two
 * models; the value is shipped to the client on every battle_offer (SS2.W1),
 * so only the host's setting matters and only before a battle starts.
 *
 * Donor shape, `cbff7951d:HostMenu.cpp:812-834` (which flipped the old boolean
 * Options::EnableCoopParallelTurns). W1-P7 keeps the shape and changes the
 * value: REV D's option is a STRING carrying the SS2.W1 wire spelling, so there
 * is no bool->enum->string translation anywhere in the path.
 *
 * NOTHING HERE BRANCHES BEHAVIOUR (REV D, binding): this writes a preference.
 * The baton logic that consumes it is W1-P13's.
 */
void HostMenu::btnTurnModeClick(Action*)
{
	Options::CoopTurnMode =
		(coopSessionTurnModeFromOptions() == CoopTurnMode::Traditional)
			? coopTurnModeName(CoopTurnMode::Parallel)
			: coopTurnModeName(CoopTurnMode::Traditional);
	updateTurnModeButton();
}

/**
 * coop (W1-P7 deliverable 6, D-19): keeps the toggle's label in sync with the
 * option and its visibility in sync with the rest of the hosting controls -
 * hidden once a session is live, exactly like START HOST. Donor shape
 * (`cbff7951d:HostMenu.cpp:826-834`).
 *
 * The label is read back through coopSessionTurnModeFromOptions() rather than
 * from the raw string, so a hand-edited options.cfg shows what the game will
 * ACTUALLY send (anything but "traditional" is parallel, D-26) instead of
 * echoing a value that would never reach the wire.
 */
void HostMenu::updateTurnModeButton()
{
	_btnTurnMode->setText(coopSessionTurnModeFromOptions() == CoopTurnMode::Traditional
		? "TURNS: TRADITIONAL"
		: "TURNS: PARALLEL");
	_btnTurnMode->setVisible(_tcpButtonHost->getVisible());
}

bool HostMenu::hostControlsVisible() const
{
	// the window counts as usable if the primary action (START HOST) or the
	// connection-type combo can be interacted with
	return _tcpButtonHost->getVisible()
		|| _cbxVisibility->getVisible();
}

/**
 * Returns to the previous screen.
 * @param action Pointer to an action.
 */
void HostMenu::btnCancelClick(Action*)
{
	// campaign flow: leaving the host window abandons the (paused, not yet
	// running) co-op session - back to the main menu, never into the world
	// without the other players (D5). Derived from the SAVE, not lobbyMode:
	// the disconnect cleanup can reset lobbyMode (disconnect -> cancel path).
	if (_game->getCoopMod()->inCoopCampaignContext())
	{
		_game->setState(new GoToMainMenuState(false));
		return;
	}

	_game->popState();
}

}

