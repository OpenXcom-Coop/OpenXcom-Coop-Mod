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

#include "../Battlescape/BattlescapeGame.h"
#include "../Engine/Game.h"
#include "../Engine/Options.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Mod/Mod.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "../Menu/AbandonGameState.h"
#include "../Menu/ListLoadState.h"
#include "../Menu/ListSaveState.h"
#include "../Menu/OptionsBattlescapeState.h"
#include "../Menu/OptionsGeoscapeState.h"
#include "../Menu/OptionsVideoState.h"
#include "../Menu/PauseState.h"
#include "../Geoscape/GeoscapeState.h"
#include "CoopState.h"

#include "../Basescape/BasescapeState.h"

#include "../Savegame/Soldier.h"
#include "../Savegame/EquipmentLayoutItem.h"
#include "../Savegame/ItemContainer.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/Vehicle.h"

#include "../Menu/SaveGameState.h"
#include "../Menu/LoadGameState.h"

#include "../Menu/MainMenuState.h"
#include "../Menu/NewBattleState.h"

namespace OpenXcom
{

Globe *currentGlobe = 0;

namespace
{
// Layout of the host-wait dialog family (60/62/64) - issues #79/#81.
//
// These dialogs are strips that sit over a live geoscape/battlescape, so they
// are sized to their CONTENT: inner padding, one wrapped title, and one or two
// button rows. Nothing is positioned by absolute screen coordinate; every row
// is measured from the window, which is what keeps the margins even and the
// window cropped to what it actually holds.
const int kWaitW       = 216;  // shared with the other CoopState dialogs
const int kWaitPad     = 8;    // inner margin: border to content, all four sides
const int kWaitGap     = 6;    // between the title and a row, and between rows
const int kWaitBtnH    = 17;   // _btnBack's stock height; the pair matches it
const int kWaitBtnW    = 99;   // two of these + kWaitGap fit the padded width
const int kWaitActionW = 100;  // RESUME / BEGIN, centered on its own row
const int kWaitTitleH  = 22;   // two small wrapped lines
const int kWaitCenterY = 100;  // the dialogs stay centered on this line

// issue #91: how long the client sits in the resume hold, with the host provably
// back on its geoscape, before it stops waiting for a release that is not coming.
// Counted in 500ms think gates, so 40 == ~20s.
const int kHoldGiveUpTicks = 40;
// The peer counts as "on the geoscape" if its `time` heartbeat is this fresh. Same
// grace the host uses to freeze the shared clock on a quiet peer
// (GeoscapeState::timeAdvance), and comfortably above the per-frame heartbeat gap.
const Uint32 kPeerLiveGraceMs = 1000;

// padding, title, one button row, padding. ONE row is all these dialogs ever
// need: the escape hatch and the RESUME/BEGIN action are mutually exclusive
// (see setWaitAction), so the window never has to grow or leave a hole.
const int kWaitH = kWaitPad + kWaitTitleH + kWaitGap + kWaitBtnH + kWaitPad;
}

/**
 * Initializes all the elements in the Pause window.
 * @param game Pointer to the core game.
 * @param origin Game section that originated this state.
 */
CoopState::CoopState(int state, int value) : _value(value)
{
	_screen = false;

	global_state = state;

	int x = 20;

	if (state == COOP_DLG_CLIENT_HOLD || state == COOP_DLG_CLIENT_RESUME_HOLD)
	{
		// compact variant: a third of the standard height, vertically
		// centered, with room for two small wrapped lines (no button)
		_window = new Window(this, 216, 54, x, 73, POPUP_BOTH);
		_txtTitle = new Text(206, 26, x + 5, 88);
	}
	else if (isHostWaitDialog(state))
	{
		// One content-sized strip for the whole host-wait family (60/62/64):
		// padding, a wrapped title, and a single button row that holds either
		// the escape hatch or the dialog's own action - never both.
		_window = new Window(this, kWaitW, kWaitH, x,
							 kWaitCenterY - kWaitH / 2, POPUP_BOTH);
		_txtTitle = new Text(kWaitW - 2 * kWaitPad, kWaitTitleH, x + kWaitPad,
							 kWaitCenterY - kWaitH / 2 + kWaitPad);
	}
	else if (state == COOP_DLG_SHARED_FAIL)
	{
		// PRD-J10: the host's rejection reason is a full sentence (a translated
		// STR_ id or a raw validator message), so give the title room to wrap
		// instead of the standard one-liner strip.
		_window = new Window(this, 216, 160, x, 20, POPUP_BOTH);
		_txtTitle = new Text(206, 72, x + 5, 62);
	}
	else if (state == COOP_DLG_CONFIRM_EQUIP_CRAFT)
	{
		// content-sized confirm: a wrapped question plus one YES/NO row,
		// horizontally centered instead of the legacy x=20 strip
		_window = new Window(this, 216, 96, 52, 52, POPUP_BOTH);
		_txtTitle = new Text(196, 44, 62, 62);
	}
	else if (state == COOP_DLG_VOTE_COOLDOWN)
	{
		// content-sized notice: two wrapped lines plus a single OK row
		_window = new Window(this, 216, 64, 52, 68, POPUP_BOTH);
		_txtTitle = new Text(196, 18, 62, 78);
	}
	else
	{
		_window = new Window(this, 216, 160, x, 20, POPUP_BOTH);
		_txtTitle = new Text(206, 17, x + 5, 100);
	}
	_btnMessage = new TextButton(100, 17, x + 55, 100);
	_btnBack = new TextButton(100, 17, x + 55, 150);
	_btnYes = new TextButton(80, 20, 40, 150);
	// issues #79/#81: the host's escape hatch, side by side under the wait
	// message. layoutWaitRows() places them; hidden everywhere else.
	_btnSaveQuit = new TextButton(kWaitBtnW, kWaitBtnH, x + kWaitPad, 150);
	_btnAbandon = new TextButton(kWaitBtnW, kWaitBtnH, x + kWaitPad, 150);

	// Set palette
	setInterface("pauseMenu", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	add(_window, "window", "pauseMenu");
	add(_txtTitle, "text", "pauseMenu");
	add(_btnMessage, "button", "pauseMenu");
	add(_btnBack, "button", "pauseMenu");
	add(_btnYes, "button", "pauseMenu");
	add(_btnSaveQuit, "button", "pauseMenu");
	add(_btnAbandon, "button", "pauseMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "pauseMenu");

	_origin = OPT_GEOSCAPE;

	if (_game->getSavedGame())
	{
		if (_game->getSavedGame()->getSavedBattle())
		{

			applyBattlescapeTheme("pauseMenu");
			_origin = OPT_BATTLESCAPE;

		}
	}

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText("WAIT");

	_btnMessage->setVisible(false);
	_btnBack->setVisible(false);
	_btnYes->setVisible(false);
	_btnSaveQuit->setVisible(false);
	_btnAbandon->setVisible(false);

	_btnMessage->setText(tr("OK"));
	_btnMessage->onMouseClick((ActionHandler)&CoopState::loadCoop);

	_btnBack->setText(tr("OK"));
	_btnBack->onMouseClick((ActionHandler)&CoopState::previous);

	_btnYes->setText(tr("STR_YES"));
	_btnYes->onMouseClick((ActionHandler)&CoopState::btnYesClick);
	_btnYes->onKeyboardPress((ActionHandler)&CoopState::btnYesClick, Options::keyOk);

	_btnSaveQuit->setText("SAVE & QUIT");
	_btnSaveQuit->onMouseClick((ActionHandler)&CoopState::btnSaveQuitClick);

	_btnAbandon->setText("ABANDON GAME");
	_btnAbandon->onMouseClick((ActionHandler)&CoopState::btnAbandonClick);

	// HostLoadProgress (client)
	if (state == COOP_DLG_CLIENT_LOAD_WAIT)
	{
		_game->getCoopMod()->load_state = "Loading";

		_txtTitle->setText(_game->getCoopMod()->load_state + "...");

		_btnBack->setText("Disconnect");
		_btnBack->setVisible(true);

		// PRD-11 C13: fresh load-wait dialog, clear any stale busy signal so the
		// first host reply drives the retry state machine cleanly.
		connectionTCP::loadProgressBusy = false;
	}

	// Player was kicked
	if (state == 123456)
	{

		_txtTitle->setSmall();
		_txtTitle->setText("You have been kicked.");

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	// PRD-J10: THE single SHARED command-rejection dialog. Every J05-J08 failure
	// path reaches this through SharedEcon::showFail, on the replica (from
	// shared_fail) and on the host (its own command failing validation). The text is
	// the host validator's reason, already translated by showFail - same
	// static-string idiom as the join-refusal dialog (63) above.
	if (state == COOP_DLG_SHARED_FAIL)
	{
		_txtTitle->setSmall();
		_txtTitle->setWordWrap(true);
		_txtTitle->setText(connectionTCP::sharedFailReason.empty()
							   ? "The host rejected your command."
							   : connectionTCP::sharedFailReason);

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	// Custom Battle: equipment is shared against one fixed craft type. The host
	// confirms this irreversible session transition before the equipment screen
	// is opened and before clients receive their EQUIP CRAFT lobby button.
	if (state == COOP_DLG_CONFIRM_EQUIP_CRAFT)
	{
		_txtTitle->setSmall();
		_txtTitle->setWordWrap(true);
		_txtTitle->setAlign(ALIGN_CENTER);
		_txtTitle->setText(
			"Open EQUIP CRAFT?\n\n"
			"The selected craft will be locked for this multiplayer session.");

		_btnYes->setX(72);
		_btnYes->setY(118);
		_btnYes->setWidth(80);
		_btnYes->setHeight(20);
		_btnYes->setVisible(true);

		_btnBack->setText(tr("STR_NO"));
		_btnBack->setX(168);
		_btnBack->setY(118);
		_btnBack->setWidth(80);
		_btnBack->setHeight(20);
		_btnBack->setVisible(true);
	}

	// A player may start at most one vote every 30 seconds. The host sends the
	// authoritative remaining time, and this ordinary CoopState explains why
	// the new vote request was rejected.
	if (state == COOP_DLG_VOTE_COOLDOWN)
	{
		const int seconds = std::max(1, _value);
		_txtTitle->setSmall();
		_txtTitle->setWordWrap(true);
		_txtTitle->setAlign(ALIGN_CENTER);
		_txtTitle->setText(
			"Please wait " + std::to_string(seconds)
			+ (seconds == 1 ? " second" : " seconds")
			+ " before starting another vote.");

		_btnBack->setText(tr("OK"));
		_btnBack->setX(110);
		_btnBack->setY(105);
		_btnBack->setVisible(true);
	}

	// R1-P5/R4-REWIRE: coop battle-entry/battle-resume choreography is quarantined
	// pending the r4/r5 atomic-bundle rebuild (RB-D9) - every stub site pushes this
	// instead of starting/resuming a coop battle. OK falls through to the default
	// _game->popState() in previous(), so the caller's own return (to geoscape or
	// lobby) is what the player sees underneath.
	if (state == COOP_DLG_BATTLE_UNAVAILABLE)
	{
		_txtTitle->setSmall();
		_txtTitle->setWordWrap(true);
		_txtTitle->setAlign(ALIGN_CENTER);
		_txtTitle->setText("Coop battles are unavailable in this build.");

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	// Transfer or purchase failed
	if (state == 551)
	{

		_txtTitle->setSmall();
		_txtTitle->setText("Failed to send items to the other player.");

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	if (state == 552)
	{

		_txtTitle->setSmall();
		_txtTitle->setText("Failed to remove items from your base.");

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	if (state == 553)
	{

		_txtTitle->setSmall();
		_txtTitle->setText("Base not found for transferring items.");

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	// save error
	if (state == 994)
	{

		_txtTitle->setSmall();
		_txtTitle->setText("Save failed (FILE), please try again.");

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);

	}

	// Warning: logPacketMessages is enabled
	if (state == 942)
	{
		_txtTitle->setSmall();
		_txtTitle->setText("Disable Write packet messages to log files\n to avoid latency or crashes.");
		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	// save error 2
	if (state == 995)
	{

		_txtTitle->setSmall();
		_txtTitle->setText("Save failed (MEMORY), please try again.");

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	// refused by a join gate (roster / duplicate name, flow-redesign F3)
	if (state == 63)
	{
		_txtTitle->setSmall();
		_txtTitle->setText(connectionTCP::joinRefusalReason.empty()
							   ? "You are not a player in this campaign."
							   : connectionTCP::joinRefusalReason);

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	// Host waits on a peer: resuming players finishing their load (flow-redesign
	// F3) and a mid-session drop waiting for a reconnect (F4/D5) are the SAME
	// dialog - see COOP_DLG_WAIT_PLAYERS. Wording comes from waitingTitle(), so
	// it follows the peer instead of the push site; the shared host-wait block
	// below does the rest.
	if (state == COOP_DLG_WAIT_PLAYERS)
	{
		_btnBack->setText("RESUME");
	}

	// non-host player finished early (base placed / world loaded) and holds
	// with frozen time until the host resumes the campaign (D5)
	if (state == COOP_DLG_CLIENT_HOLD || state == COOP_DLG_CLIENT_RESUME_HOLD)
	{
		_txtTitle->setSmall();
		_txtTitle->setWordWrap(true);
		// fresh new-campaign base building vs. a mid-session rejoin: same hold,
		// different reason. The rejoining client's bases already exist - it is
		// only waiting for the host to un-freeze the session.
		if (state == COOP_DLG_CLIENT_RESUME_HOLD)
		{
			_txtTitle->setText("Waiting for host to resume the game.");
		}
		else
		{
			_txtTitle->setText("Waiting for all players\nto place their bases...");
		}

		_btnBack->setVisible(false);

		// consume any stale release from a previous hold
		connectionTCP::session.consumeCampaignBegun();
	}

	// the host identity is locked to the save (D4)
	if (state == 66)
	{
		std::string owner = "its creator";
		if (_game->getSavedGame() && !_game->getSavedGame()->getCoopPlayers().empty())
		{
			owner = _game->getSavedGame()->getCoopPlayers()[0];
		}
		_txtTitle->setSmall();
		_txtTitle->setText("This campaign can only be hosted by " + owner + ".");

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	// solo campaigns can never be hosted as co-op (flow-redesign D1)
	if (state == 61)
	{
		_txtTitle->setSmall();
		_txtTitle->setText("This is a solo campaign. Co-op campaigns are created from the New Game menu.");

		_btnBack->setText(tr("OK"));
		_btnBack->setVisible(true);
	}

	// new-campaign base building: host waits until every player has placed
	// a base; the button turns into RESUME when they have (flow-redesign F2)
	if (state == COOP_DLG_WAIT_BASES)
	{
		_btnBack->setText("BEGIN");
	}

	// issues #79/#81: every HOST-side campaign wait blocks on a peer that may
	// never come back (a client that quit, crashed, or simply never joined).
	// Without an exit the host is trapped in the dialog and cannot even save.
	// Both buttons are live from the first frame - they must work precisely
	// when nothing else on this dialog does.
	if (isHostWaitDialog(state))
	{
		// one title treatment for the family: small, wrapped, and centered in
		// its box so a one-line message doesn't hang off the top of it
		_txtTitle->setSmall();
		_txtTitle->setWordWrap(true);
		_txtTitle->setVerticalAlign(ALIGN_MIDDLE);

		// wording, visibility and layout all come from the one state machine
		setWaitAction(waitSatisfied());
	}

	// host-save cycle (host)
	if (state == COOP_DLG_HOST_SAVE_WAIT)
	{
		
		_game->getCoopMod()->load_state = "Saving";
		_txtTitle->setText(_game->getCoopMod()->load_state + "...");

		Json::Value obj;
		obj["state"] = "sendProgressSaveRequest";
		obj["saveID"] = static_cast<Json::Int64>(connectionTCP::saveID);
		_game->getCoopMod()->sendTCPPacketData(obj.toStyledString());

		_btnBack->setText(tr("STR_CANCEL_UC"));
		_btnBack->setVisible(true);

	}

	// host-save cycle (client)
	if (state == 53)
	{
		_game->getCoopMod()->load_state = "Saving";

		_txtTitle->setText(_game->getCoopMod()->load_state + "...");

		_btnBack->setText("Disconnect");
		_btnBack->setVisible(true);
	}

	// Main campaign base defense
	if (state == 77)
	{

		std::string result = "Waiting for " + _game->getCoopMod()->getCurrentClientName();
		_txtTitle->setText(result);

		_btnBack->setText("Disconnect");
		_btnBack->setVisible(true);

		Json::Value obj;
		obj["state"] = "sendCraft";
		_game->getCoopMod()->sendTCPPacketData(obj.toStyledString());

	}

	if (state == 88)
	{
		std::string result = "Waiting for " + _game->getCoopMod()->getCurrentClientName();
		_txtTitle->setText(result);

		_btnBack->setText("Disconnect");
		_btnBack->setVisible(true);


		// coop new  battle
		if (_game->getCoopMod()->getCoopCampaign() == false && _game->getCoopMod()->getCoopStatic() == true)
		{

			Base* selected_base = _game->getSavedGame()->getSelectedBase();

			for (auto* soldier : *selected_base->getSoldiers())
			{

				// new coop soldier
				if (soldier->getCraft())
				{

					soldier->setCoopBase(selected_base->_coop_base_id);
					soldier->setCoopCraft(soldier->getCraft()->getId());
					soldier->setCoopCraftType(soldier->getCraft()->getType());
				}
				else
				{

					soldier->setCoopBase(-1);
					// clear the persisted seat too, or a soldier taken off the craft is
					// re-seated from the stale id when the co-op base is next rebuilt
					// (the sibling block below already does this).
					soldier->setCoopCraft(-1);
					soldier->setCoopCraftType("");
				}
			}
		}

		Json::Value obj;
		obj["state"] = "sendCraft";
		_game->getCoopMod()->sendTCPPacketData(obj.toStyledString());

	}

	if (state == 0)
	{
	}

	if (state == 99)
	{
		_txtTitle->setSmall();
		_txtTitle->setText("Completed Research by\n " + _game->getCoopMod()->getCurrentClientName() + ".");
		_btnBack->setVisible(true);
	}

	if (state == 150)
	{
		_txtTitle->setSmall();
		_txtTitle->setText("Items received from " + _game->getCoopMod()->getCurrentClientName() + ".\nTransferred to " + _game->getCoopMod()->current_base_name + " base.");
		_btnBack->setVisible(true);
	}

	// base orig
	if (state == 66)
	{
		_txtTitle->setSmall();
		_txtTitle->setText("Go to Geoscape to begin the co-op mission.");
		_btnBack->setVisible(true);
	}

	if (state == 67)
	{
		_txtTitle->setSmall();
		_txtTitle->setText("Go to Geoscape to begin saving progress.");
		_btnBack->setVisible(true);
	}

	if (state == 979)
	{
		_txtTitle->setSmall();
		_txtTitle->setText("Cannot connect to server.\nClick OK to return to the main menu.");
		_game->getCoopMod()->disconnectTCP();
		_btnBack->setVisible(true);
	}

	// DOWNLOAD MAP
	if (state == 1)
	{
		_txtTitle->setText("Downloading map...");
		_btnBack->setText("Disconnect");
		_btnBack->setVisible(true);

	}

	// CLIENT WAITING
	if (state == 3)
	{
		std::string result = "Waiting for " + _game->getCoopMod()->getCurrentClientName();
		_txtTitle->setText(result);

		_btnBack->setText("Disconnect");
		_btnBack->setVisible(true);

	}

	// CLIENT DATA
	if (state == 4)
	{

		// coop new  battle
		if (_game->getCoopMod()->getCoopCampaign() == false && _game->getCoopMod()->getCoopStatic() == true)
		{

			Base* selected_base = _game->getSavedGame()->getSelectedBase();

			for (auto* soldier : *selected_base->getSoldiers())
			{

				// new coop soldier
				if (soldier->getCraft())
				{

					soldier->setCoopBase(selected_base->_coop_base_id);
					soldier->setCoopName(soldier->getName());
					soldier->setCoopCraft(soldier->getCraft()->getId());
					soldier->setCoopCraftType(soldier->getCraft()->getType());
				}
				else
				{

					soldier->setCoopBase(-1);
					soldier->setCoopCraft(-1);
					soldier->setCoopCraftType("");
				}

			}

		}

		_game->getCoopMod()->load_state = "Please wait";

		_txtTitle->setText(_game->getCoopMod()->load_state + "...");

		_btnBack->setText("Disconnect");
		_btnBack->setVisible(true);

	}



	if (state == 100)
	{
		_txtTitle->setVisible(true);
		_btnMessage->setVisible(false);
		_txtTitle->setText("PLayer Connected!");
	}

	// TCP
	if (state == 15)
	{
		_txtTitle->setText("Connecting...");
		_btnBack->setVisible(true);
		_btnBack->setText(tr("STR_CANCEL_UC"));

	}

	// WRONG PASSWORD
	if (state == 441)
	{

		connectionTCP::forceCloseCoopStateMenu = true;

		_txtTitle->setSmall();
		_txtTitle->setText("Incorrect password.\nConnection closed.");
		_btnBack->setVisible(true);
		_game->getCoopMod()->setServerOwner(false);
		_game->getCoopMod()->disconnectTCP();

	}

	// SERVER ERROR
	if (state == 440)
	{

		_txtTitle->setSmall();
		_txtTitle->setText("Server error.\nConnection closed.");
		_btnBack->setVisible(true);
		_game->getCoopMod()->setServerOwner(false);
		_game->getCoopMod()->disconnectTCP();
		_game->popState();

	}

	// SERVER FULL
	if (state == 444)
	{

		_txtTitle->setSmall();
		_txtTitle->setText("The server is full.\nMaximum allowed is 2 players.");
		_btnBack->setVisible(true);
		_game->getCoopMod()->disconnectTCP();
		_game->popState();

	}

	if (state == 16)
	{
		_txtTitle->setText("Cannot connect to server");
		_btnBack->setVisible(true);
		_game->getCoopMod()->disconnectTCP();
		_game->popState();
	}

	if (state == 20)
	{
		_txtTitle->setText(_game->getCoopMod()->getCurrentClientName() + " has left the server");
		_btnBack->setVisible(true);

		// disconnect
		connectionTCP::_coopGamemode = 0;
		_game->getCoopMod()->disconnectTCP();
	}

	if (state == 21)
	{
		connectionTCP::_coopGamemode = 0;
		_txtTitle->setText("Server connection lost");
		_btnBack->setVisible(true);
		_game->getCoopMod()->disconnectTCP();
	}

	if (state == 50)
	{

		connectionTCP::isCoopBaseLoading = true;

		_txtTitle->setText("Synchronizing bases...");
		_btnBack->setText("Disconnect");
		_btnBack->setVisible(true);

		if (_game->getCoopMod()->getHost() == true)
		{
			Json::Value obj;
			obj["state"] = "SEND_FILE_HOST_BASE";
			DebugLog(obj.toStyledString());
			_game->getCoopMod()->sendTCPPacketData(obj.toStyledString());
		}
		else
		{

			Json::Value obj;
			obj["state"] = "SEND_FILE_CLIENT_BASE";
			DebugLog(obj.toStyledString());
			_game->getCoopMod()->sendTCPPacketData(obj.toStyledString());
		}

	}

	// out of sync
	if (state == 999)
	{

		_txtTitle->setText("ERROR: Out Of Sync");
		_btnBack->setVisible(true);

		// disconnect
		connectionTCP::_coopGamemode = 0;
		_game->getCoopMod()->disconnectTCP();

	}

	// JSON ERROR
	if (state == 250)
	{

		_txtTitle->setText("ERROR: Invalid or corrupted packet data");
		_btnBack->setVisible(true);

		// disconnect
		connectionTCP::_coopGamemode = 0;
		_game->getCoopMod()->disconnectTCP();
	}

	// Mod Compatibility
	if (state == 1000)
	{
		_txtTitle->setSmall();
		_txtTitle->setText("Mod Compatibility Issue.\nEnsure both have the same mods installed.");
		_btnBack->setVisible(true);

		// disconnect
		connectionTCP::_coopGamemode = 0;
		_game->getCoopMod()->disconnectTCP();

		_game->popState();

	}

	// new  battle
	if (state == 3000)
	{
		_txtTitle->setSmall();
		_txtTitle->setText("Please click the 'New Battle' button\n in the main menu to join the session.");
		_btnBack->setVisible(true);

		// disconnect
		connectionTCP::_coopGamemode = 0;
		_game->getCoopMod()->disconnectTCP();

		_game->popState();
	}

	// kick player
	if (state == 12345)
	{

		std::string message =
			"Kick this player?";

		_txtTitle->setSmall();
		_txtTitle->setText(message);
		_btnBack->setVisible(true);

		_btnBack->setText(tr("STR_NO"));

		_btnBack->setX(136);
		_btnBack->setY(150);
		_btnBack->setWidth(80);
		_btnBack->setHeight(20);

		_txtTitle->setHeight(40);
		_txtTitle->setY(80);

		_btnYes->setVisible(true);

	}

	// Remove manually added server
	if (state == 1234)
	{

		std::string message =
			"Remove this manually added server?\n\n"
			"Removes it from your saved server list.";

		_txtTitle->setSmall();
		_txtTitle->setText(message);
		_btnBack->setVisible(true);

		_btnBack->setText(tr("STR_NO"));

		_btnBack->setX(136);
		_btnBack->setY(150);
		_btnBack->setWidth(80);
		_btnBack->setHeight(20);

		_txtTitle->setHeight(40);
		_txtTitle->setY(80);

		_btnYes->setVisible(true);

	}

	// Client-side error
	if (state == 123)
	{

		std::string message =
			"Saving this file is not recommended\n"
			"due to detected desync problems.\n\n"
			"Are you sure you want to proceed?";

		_txtTitle->setSmall();
		_txtTitle->setText(message);
		_btnBack->setVisible(true);

		_btnBack->setText(tr("STR_NO"));

		_btnBack->setX(136);
		_btnBack->setY(150);
		_btnBack->setWidth(80);
		_btnBack->setHeight(20);

		_txtTitle->setHeight(40);
		_txtTitle->setY(80);

		_btnYes->setVisible(true);

	}

}

/**
 *
 */
CoopState::~CoopState()
{
}

std::string CoopState::getTitleText() const
{
	return _txtTitle ? _txtTitle->getText() : "";
}

std::string CoopState::getBackText() const
{
	return _btnBack ? _btnBack->getText() : "";
}

bool CoopState::isBackVisible() const
{
	return _btnBack && _btnBack->getVisible();
}

int CoopState::getWindowHeight() const
{
	return _window ? _window->getHeight() : 0;
}

/**
 * Issues #79/#81: place the rows of a host-wait dialog, measured from the
 * window itself. centerAllSurfaces has already shifted every surface by the
 * screen delta, so working off _window->getX()/getY() keeps the content pinned
 * to its own window at any display scale - an absolute setY would not.
 * Every widget already has its final SIZE from the constructor; this only moves
 * them, so nothing re-wraps or re-renders.
 * @param withAction The row holds RESUME/BEGIN rather than the escape hatch.
 */
void CoopState::layoutWaitRows(bool withAction)
{
	const int wx = _window->getX();
	const int wy = _window->getY();
	const int row = wy + kWaitPad + kWaitTitleH + kWaitGap;

	_txtTitle->setX(wx + kWaitPad);
	_txtTitle->setY(wy + kWaitPad);

	if (withAction)
	{
		_btnBack->setX(wx + (kWaitW - kWaitActionW) / 2);
		_btnBack->setY(row);
	}
	else
	{
		_btnSaveQuit->setX(wx + kWaitPad);
		_btnSaveQuit->setY(row);
		_btnAbandon->setX(wx + kWaitW - kWaitPad - kWaitBtnW);
		_btnAbandon->setY(row);
	}
}

/**
 * Issues #79/#81: switch a host-wait dialog between its two states.
 *
 * WAITING  the peer is missing, so there is nothing to RESUME/BEGIN and the
 *          only useful actions are leaving - SAVE & QUIT / ABANDON GAME.
 * READY    the peer is back, so the wait is over and quitting the campaign is
 *          not what this dialog is for; RESUME/BEGIN is the only action.
 *
 * They are mutually exclusive, which is why one button row is enough. Driven
 * from think() in BOTH directions: a peer that drops again gets the escape
 * hatch back rather than being left with a RESUME that resumes nobody.
 */
/**
 * Issues #79/#81: what a host-wait dialog is waiting on, worded from the peer's
 * CURRENT presence rather than from whatever the push site assumed.
 *
 * This is why the resume-ack wait and the reconnect freeze are one dialog: they
 * only ever differed in this sentence, and the difference is a property of the
 * session, not of the two call sites. A client that drops while the host is
 * already waiting now re-words the dialog it is in - it used to keep claiming
 * the player was loading, because the freeze push was suppressed.
 */
std::string CoopState::waitingTitle() const
{
	if (global_state == COOP_DLG_WAIT_BASES)
	{
		// same wording as the client's hold dialog (COOP_DLG_CLIENT_HOLD) -
		// one message, one look, two actors
		return "Waiting for all players\nto place their bases...";
	}
	if (connectionTCP::session.clientInLobby)
	{
		return "Waiting for players to load...";
	}
	const std::string peer = _game->getCoopMod()->getCurrentClientName();
	return peer.empty() ? "Waiting for players to reconnect..."
						: "Waiting for " + peer + " to reconnect...";
}

/**
 * The same dialog's wording once the wait is over.
 */
std::string CoopState::readyTitle() const
{
	return global_state == COOP_DLG_WAIT_BASES ? "All bases placed."
											   : "All players connected";
}

/**
 * Is the thing this host-wait dialog waits for satisfied right now? Bases wait
 * on every registered client's world blob (a client pushes progress right after
 * base naming); the player wait is answered by resume_ack (F3/F4).
 */
bool CoopState::waitSatisfied() const
{
	if (global_state == COOP_DLG_WAIT_BASES)
	{
		// The host's base-placement wait dialog. For every non-PvP
		// campaign the client's world blob arriving IS the
		// base-placement-complete signal (the client pushes it right
		// after base naming), so BEGIN stays gated on that blob.
		// PvP gm2 is the exception: the client is the alien side, never
		// places a base and never sends a blob, so BEGIN must not wait
		// on one.
		if (connectionTCP::getCoopGamemode() == 2)
			return true;
		return connectionTCP::hasCoopFile(
			connectionTCP::hostBlobKey(_game->getCoopMod()->getCurrentClientName()));
	}
	return connectionTCP::session.resumeAck;
}

void CoopState::setWaitAction(bool ready)
{
	_txtTitle->setText(ready ? readyTitle() : waitingTitle());

	_btnBack->setVisible(ready);
	_btnSaveQuit->setVisible(!ready);
	_btnAbandon->setVisible(!ready);

	layoutWaitRows(ready);
}

std::string CoopState::getSaveQuitText() const
{
	return _btnSaveQuit ? _btnSaveQuit->getText() : "";
}

bool CoopState::isSaveQuitVisible() const
{
	return _btnSaveQuit && _btnSaveQuit->getVisible();
}

std::string CoopState::getAbandonText() const
{
	return _btnAbandon ? _btnAbandon->getText() : "";
}

bool CoopState::isAbandonVisible() const
{
	return _btnAbandon && _btnAbandon->getVisible();
}

void CoopState::think()
{

	State::think();

	static Uint32 lastUpdate = 0;
	Uint32 now = SDL_GetTicks();

	if (now - lastUpdate >= 500)
	{

		lastUpdate = now;

		// PRD-11 C13: bounded retry when the host replies "busy" to the client's
		// request_load_progress. Without this the load-wait dialog (52) hangs
		// forever (no timeout). On the busy signal, wait ~2s then re-send; after
		// a bounded number of retries, fall back to the disconnect error UX.
		if (global_state == COOP_DLG_CLIENT_LOAD_WAIT)
		{
			const int kMaxLoadRetries = 15;
			if (connectionTCP::loadProgressBusy)
			{
				connectionTCP::loadProgressBusy = false;
				_loadWaitTicks = 4; // ~2s at the 500ms gate before retrying
			}
			if (_loadWaitTicks > 0 && --_loadWaitTicks == 0)
			{
				if (_loadRetries < kMaxLoadRetries)
				{
					_loadRetries++;
					Json::Value root;
					root["state"] = "request_load_progress";
					_game->getCoopMod()->sendTCPPacketData(root.toStyledString());
					Log(LOG_INFO) << "[coop] load progress retry " << _loadRetries << "/" << kMaxLoadRetries;
				}
				else
				{
					_txtTitle->setSmall();
					_txtTitle->setText("Host is busy; could not load progress.");
					_btnBack->setText("Disconnect");
					_btnBack->setVisible(true);
				}
			}
		}

		// Force-close the co-op state menu
		if (connectionTCP::forceCloseCoopStateMenu == true && global_state == 15)
		{

			_game->popState();
	
		}

		if (global_state == 1)
		{

			if (state_counter == 0)
			{
				_txtTitle->setText("Downloading map.");
				state_counter = 1;
			}
			else if (state_counter == 1)
			{
				_txtTitle->setText("Downloading map..");
				state_counter = 2;
			}
			else if (state_counter == 2)
			{
				_txtTitle->setText("Downloading map...");
				state_counter = 0;
			}

		}
		else if (global_state == 4 || global_state == COOP_DLG_HOST_SAVE_WAIT || global_state == 53 || global_state == COOP_DLG_CLIENT_LOAD_WAIT)
		{

			if (state_counter == 0)
			{
				_txtTitle->setText(_game->getCoopMod()->load_state + ".");
				state_counter = 1;
			}
			else if (state_counter == 1)
			{
				_txtTitle->setText(_game->getCoopMod()->load_state + "..");
				state_counter = 2;
			}
			else if (state_counter == 2)
			{
				_txtTitle->setText(_game->getCoopMod()->load_state + "...");
				state_counter = 0;
			}

		}
		else if (isHostWaitDialog(global_state))
		{

			// One poll for the whole family. Tracks BOTH directions: a peer that
			// drops after having been ready must get the escape hatch back, not
			// a RESUME that would resume nobody.
			const bool ready = waitSatisfied();
			if (ready != _btnBack->getVisible())
			{
				setWaitAction(ready);
			}
			else if (!ready)
			{
				// still waiting, but WHO we are waiting on can change under us
				// (the loading client just dropped) - re-word in place
				_txtTitle->setText(waitingTitle());
			}

		}
		else if (global_state == COOP_DLG_CLIENT_HOLD || global_state == COOP_DLG_CLIENT_RESUME_HOLD)
		{

			// released when the host begins/resumes the campaign
			if (connectionTCP::session.campaignBegun)
			{
				connectionTCP::session.consumeCampaignBegun();
				_game->popState();
			}
			// issue #91: nothing else can release this dialog - it has no button and
			// no timeout - so a release that never comes freezes the client for good
			// while the host plays on. We can tell the two apart: only the TOP state
			// thinks, so a host still deliberating behind its own wait dialog emits no
			// `time` heartbeat, while a host that has moved on heartbeats every frame.
			// Heartbeats arriving WHILE we are held mean no RESUME click is coming and
			// waiting longer cannot help - so stop waiting and let the player leave.
			// Only the streamed-world hold (68) qualifies: the base-placing hold (65)
			// belongs to a lobby where the host legitimately has no geoscape at all.
			else if (global_state == COOP_DLG_CLIENT_RESUME_HOLD && !_holdGaveUp)
			{
				const Uint32 peerAgeMs = SDL_GetTicks()
					- _game->getCoopMod()->lastPeerTimePacketMs.load();
				_holdWatchTicks = (peerAgeMs < kPeerLiveGraceMs) ? _holdWatchTicks + 1 : 0;

				if (_holdWatchTicks >= kHoldGiveUpTicks)
				{
					_holdGaveUp = true;

					_txtTitle->setSmall();
					_txtTitle->setWordWrap(true);
					_txtTitle->setText("Lost synchronization with the host.\n"
									   "Returning to the main menu.");

					_btnBack->setText(tr("OK"));
					_btnBack->setVisible(true);

					Log(LOG_ERROR) << "[coop] the host never released this resume hold"
						" and is back on its geoscape; offering the disconnect";
				}
			}

		}
		else if (global_state == 15)
		{

			if (state_counter == 0)
			{
				_txtTitle->setText("Connecting.");
				state_counter = 1;
			}
			else if (state_counter == 1)
			{
				_txtTitle->setText("Connecting..");
				state_counter = 2;
			}
			else if (state_counter == 2)
			{
				_txtTitle->setText("Connecting...");
				state_counter = 0;
			}

		}
		else if (global_state == 50)
		{

			if (state_counter == 0)
			{
				_txtTitle->setText("Synchronizing bases.");
				state_counter = 1;
			}
			else if (state_counter == 1)
			{
				_txtTitle->setText("Synchronizing bases..");
				state_counter = 2;
			}
			else if (state_counter == 2)
			{
				_txtTitle->setText("Synchronizing bases...");
				state_counter = 0;
			}

		}

	}

	//  coop fix
	if (_game->getCoopMod()->isCoopSession() == true && _game->getCoopMod()->getCoopStatic() == false && _btnBack->getVisible() == false)
	{
		_btnBack->setVisible(true);
		_txtTitle->setText("Connection cannot be established.");
		_txtTitle->setSmall();

		_game->getCoopMod()->disconnectTCP();

	}

}

void CoopState::previous(Action *)
{

	// The host clicked RESUME on a waiting dialog: release every non-host
	// player from their "waiting for players" hold (D5).
	if (isHostWaitDialog(global_state))
	{
		connectionTCP::session.sessionLive();

		Json::Value root;
		root["state"] = "campaign_begun";
		_game->getCoopMod()->sendTCPPacketData(root.toStyledString());
	}

	// issue #91: OK on a resume hold that the host never released. Nothing on this
	// side can recover the session - the world we hold is frozen behind a dialog no
	// campaign_begun is coming for - so tear the connection down and leave. The
	// client teardown inside disconnectTCP() usually makes the main-menu transition
	// itself; the explicit setState covers the gates where it does not.
	if (global_state == COOP_DLG_CLIENT_RESUME_HOLD)
	{
		_game->getCoopMod()->disconnectTCP();

		// issue #82: GoToMainMenuState is the chokepoint that drops the world on the
		// way out, so a transition already heading there counts as "we are leaving".
		if (_game->getStates().empty()
			|| (dynamic_cast<MainMenuState*>(_game->getStates().back()) == nullptr
				&& dynamic_cast<GoToMainMenuState*>(_game->getStates().back()) == nullptr))
		{
			_game->setState(new GoToMainMenuState(false));
		}
		return;
	}

	// disconnect
	// PRD-11 C13: COOP_DLG_CLIENT_LOAD_WAIT (52) added - its "Disconnect" button
	// must actually tear the connection down, not merely pop the dialog and leave
	// the client half-attached.
	if (global_state == 50 || global_state == 1 || global_state == 88 || global_state == 3 || global_state == 4 || global_state == 15 || global_state == 53 || global_state == COOP_DLG_CLIENT_LOAD_WAIT)
	{

		if (global_state == 15)
		{
			_game->getCoopMod()->cancel_connect = true;
		}

		_game->getCoopMod()->disconnectTCP();
		_game->popState();

	}
	// main menu
	else if (global_state == 979)
	{

		_game->setState(new GoToMainMenuState(false));
	}
	// issue #93: "Server connection lost". The host is gone, so there is no
	// session left to return to - and a client sitting in a co-op battle must not
	// be handed a solo game to carry on with. OK is an acknowledgement, and the
	// acknowledgement is what takes the player out. (The teardown used to jump to
	// the main menu on its own, wiping this message before it could be read.)
	else if (global_state == 21)
	{
		_game->setState(new GoToMainMenuState(false));
	}
	// PRD-06 C5: CANCEL on the host "saving..." wait dialog. The user asked for
	// a save - honour it NOW with whatever client blob is currently in the store
	// (same staleness guarantee autosaves already have), then disarm so a late
	// client blob can't rewrite a possibly-different world.
	else if (global_state == COOP_DLG_HOST_SAVE_WAIT)
	{
		_game->getCoopMod()->writePendingHostSave();
		_game->popState();
	}
	else
	{
		_game->popState();
	}


}

/**
 * Issue #81: SAVE & QUIT on a host campaign-wait dialog. Opens the ordinary
 * save-slot list; once the file is written, SaveGameState leaves for the main
 * menu instead of returning here (the whole point is to get OUT of the wait).
 * The session teardown rides the main-menu transition, as it does everywhere
 * else - see MainMenuState's constructor.
 */
void CoopState::btnSaveQuitClick(Action *)
{
	_game->pushState(new ListSaveState(_origin, true));
}

/**
 * Issue #81: ABANDON GAME on a host campaign-wait dialog. Straight to the main
 * menu, nothing written - the same contract as AbandonGameState's YES, minus
 * the confirmation step (the host already chose this over SAVE & QUIT).
 */
void CoopState::btnAbandonClick(Action *)
{
	_game->resetTouchButtonFlags();

	// Tear the session down FIRST and as the "main" teardown: that path never
	// pushes a replacement dialog, so abandoning can't resurrect the very wait
	// dialog we are leaving. Role is cleared AFTER the teardown, never before -
	// disconnectTCP branches on it, and clearing it early makes the host tear
	// down as a client (the disconnect->cancel bug family).
	_game->getCoopMod()->disconnectTCP(true);
	_game->getCoopMod()->setServerOwner(false);
	connectionTCP::session.resetSession();

	// issue #82: GoToMainMenuState::init does the geoscape rescale and drops the
	// SavedGame - after the popped states are freed, not before them.
	_game->setState(new GoToMainMenuState(false));
}

void CoopState::btnYesClick(Action *)
{

	if (global_state == COOP_DLG_CONFIRM_EQUIP_CRAFT)
	{
		NewBattleState* newBattle = nullptr;
		for (State* state : _game->getStates())
		{
			if (NewBattleState* candidate = dynamic_cast<NewBattleState*>(state))
			{
				newBattle = candidate;
			}
		}

		// Remove the confirmation first. The NewBattleState remains underneath and
		// opens CraftInfoState only after the host-side lock packet is sent.
		_game->popState();
		if (newBattle)
		{
			newBattle->confirmEquipCraftLock();
		}
		return;
	}

	if (global_state == 123)
	{

		_game->pushState(new ListSaveState(_origin));

	}

	if (global_state == 1234)
	{

		connectionTCP::canRemoveManuallyAddedServer = true;

		_game->popState();

	}

	if (global_state == 12345)
	{

		Json::Value root;
		root["state"] = "kick_player";

		_game->getCoopMod()->sendTCPPacketData(root.toStyledString());

		_game->popState();

	}

}

void CoopState::loadWorld()
{

	// load coop mission
	if (global_state == 765)
	{

		_game->pushState(new LoadGameState(_origin, "battlehost", _palette, "battlehost"));

	}
	// set client soldier
	else if (global_state == 111)
	{

		// own path
		std::string filename = "battleclient";


		Base* selected_base = 0;

		// fix
		if (_game->getCoopMod()->getSelectedCraft())
		{

			selected_base = _game->getCoopMod()->getSelectedCraft()->getBase();
		}
		else
		{
			selected_base = _game->getSavedGame()->getSelectedBase();
		}

		// RECEIVE CLIENT DATA
		SavedGame* client_save = new SavedGame();

		client_save->loadCoopSaveFromMemory(filename, _game->getMod(), _game->getLanguage(), filename);

		if (client_save && _game->getCoopMod()->getCoopCampaign() == true && _game->getCoopMod()->getServerOwner() == true)
		{

			std::string filename = connectionTCP::hostBlobKey(_game->getCoopMod()->getCurrentClientName());

			// served copy lives in memory only; the host .sav embed persists it
			client_save->saveCoopToMemory(filename, _game->getMod(), filename);

		}

		Craft* selected_craft = _game->getCoopMod()->getSelectedCraft();

		int space_available = 0;

		if (selected_craft)
		{
			space_available = _game->getCoopMod()->getSelectedCraft()->getNumTotalSoldiers() + _game->getCoopMod()->getSelectedCraft()->getSpaceAvailable();
		}

		// HOST SOLDIERS
		for (auto& host_soldier : *selected_base->getSoldiers())
		{

			if (host_soldier->getCraft())
			{

				// if same craft
				if (host_soldier->getCraft() == selected_craft)
				{

					host_soldier->setCoop(0);
					host_soldier->setCoopBase(-1);

				}

			}
			// base defense
			else if (_game->getCoopMod()->_isMainCampaignBaseDefense == true)
			{

				host_soldier->setCoop(0);
				host_soldier->setCoopBase(-1);

			}

		}


		// CLIENT SOLDIERS
		for (auto& client_base : *client_save->getBases())
		{

			// Iterate soldiers
			for (auto& soldier : *client_base->getSoldiers())
			{

				// check if match
				if ((soldier->getCoopBase() == selected_base->_coop_base_id) || _game->getCoopMod()->getCoopCampaign() == false)
				{

					if (soldier->getCoopCraft() != -1 || _game->getCoopMod()->_isMainCampaignBaseDefense == true)
					{

						// if the same craft
						std::vector<Soldier*>* soldiers = selected_base->getSoldiers();

						int lastId = 0;
						Soldier* lastSoldier = nullptr;

						if (soldiers && !soldiers->empty())
						{
							auto it = std::max_element(
								soldiers->begin(), soldiers->end(),
								[](const Soldier* a, const Soldier* b)
								{
									// Treat nullptr as smaller
									if (!a)
										return true;
									if (!b)
										return false;
									return a->getId() < b->getId();
								});

							if (it != soldiers->end() && *it)
							{
								lastSoldier = *it;
								lastId = (*it)->getId();
							}
						}
		
						if (selected_craft)
						{

							// If there is space, add a new one
							if ((space_available > 0 && selected_craft->getId() == soldier->getCoopCraft() && selected_craft->getRules()->getType() == soldier->getCoopCraftType()))
							{

								int newId = lastId + 1;

								soldier->setId(newId);
								soldier->setCoop(1);
								soldier->calcStatString(_game->getMod()->getStatStrings(), false);
								soldiers->push_back(soldier);

								soldier->setCraftAndMoveEquipment(selected_craft, selected_base, _game->getSavedGame()->getMonthsPassed() == -1);

								space_available--;
							}


						}
						else if (_game->getCoopMod()->_isMainCampaignBaseDefense == true)
						{

							int newId = lastId + 1;

							soldier->setId(newId);
							soldier->setCoop(1);
							soldier->calcStatString(_game->getMod()->getStatStrings(), false);
							soldiers->push_back(soldier);

							soldier->setCraftAndMoveEquipment(selected_craft, selected_base, _game->getSavedGame()->getMonthsPassed() == -1);

						}


					}
				}
			}

			if (selected_craft)
			{


				// HOST VEHICLES
				for (auto& host_vehicle : *_game->getCoopMod()->getSelectedCraft()->getVehicles())
				{

					host_vehicle->setCoop(0);
					host_vehicle->setCoopBase(-1);
				}

				// CLIENT VEHICLES
				for (auto& client_craft : *client_base->getCrafts())
				{

					for (auto& vehicle : *client_craft->getVehicles())
					{

						// check if this vehicle item exists in the base inventory
						int vehicle_count = selected_base->getItemsCoop()->getItem(vehicle->getRules());
						
						if ((selected_craft->getId() == vehicle->getCoopCraft() && selected_craft->getType() == vehicle->getCoopCraftType() && vehicle->getCoopBase() == selected_base->_coop_base_id && (vehicle_count > 0)) || _game->getCoopMod()->getCoopCampaign() == false)
						{

							selected_craft->makeCoopVehicle(vehicle);

						}
					}
				}


			}



		}
		
	}
	else if (global_state == 888)
	{
		_game->pushState(new LoadGameState(_origin, "battleclient", _palette, "battleclient"));
	}
	else if (global_state == 555)
	{
		std::string filename = connectionTCP::clientBlobKey(_game->getCoopMod()->getHostName());
		_game->pushState(new LoadGameState(OPT_GEOSCAPE, filename, _palette, filename, true));
	}
	else if (global_state == 777)
	{
		if (_game->getCoopMod()->getServerOwner() == true && _game->getCoopMod()->coopMissionEnd == false)
		{
			_game->getSavedGame()->saveCoopToMemory("basehost", _game->getMod(), "basehost");
		}
		else if (_game->getCoopMod()->coopMissionEnd == false)
		{
			_game->getSavedGame()->saveCoopToMemory("basehost", _game->getMod(), "basehost");
		}
	}
	else if (global_state == 666)
	{
		if (_game->getCoopMod()->getServerOwner() == true && _game->getCoopMod()->coopMissionEnd == false)
		{
			_game->getSavedGame()->saveCoopToMemory("battlehost", _game->getMod(), "battlehost");
		}
		else if (_game->getCoopMod()->coopMissionEnd == false)
		{
			_game->getSavedGame()->saveCoopToMemory("battlehost", _game->getMod(), "battlehost");
		}

	}
	else if (global_state == 55)
	{

			_game->popState();
		
			SavedGame *oldsave = _game->getSavedGame();

			SavedGame* newsave = new SavedGame();

			std::string filename = "";

			// write
			_game->getCoopMod()->coopFunds = oldsave->getFunds();
			oldsave->saveCoopToMemory("basehost", _game->getMod(), "basehost");
			filename = "baseclient"; 

			std::vector<Soldier*> current_soldiers;

			newsave->loadCoopSaveFromMemory(filename, _game->getMod(), _game->getLanguage(), filename);

			for (auto& newbase : *newsave->getBases())
			{

				newbase->isCoopBase(true);

				// Issue #33: the peer's own soldiers are about to be removed from
				// this visited-base view (only the visitor's guest soldiers are
				// shown), but a soldier's equipment layout does NOT decrement base
				// storage - the physical items stay in storage. If we drop the
				// soldiers but keep their reserved items in storage, those items
				// appear as free/available on the inventory ground pane. Remove
				// each departing soldier's layout items (weapon + loaded ammo)
				// from the visited base's storage so the visitor only sees the
				// peer's genuinely free equipment.
				for (auto* peerSoldier : *newbase->getSoldiers())
				{
					for (auto* layoutItem : *peerSoldier->getEquipmentLayout())
					{
						const RuleItem* itemRule = layoutItem->getItemType();
						if (itemRule)
						{
							newbase->getStorageItems()->removeItem(itemRule, 1);
						}
						for (int ammoSlot = 0; ammoSlot < RuleItem::AmmoSlotMax; ++ammoSlot)
						{
							const RuleItem* ammoRule = layoutItem->getAmmoItemForSlot(ammoSlot);
							if (ammoRule)
							{
								newbase->getStorageItems()->removeItem(ammoRule, 1);
							}
						}
					}
				}

				// clear all vehicles and soldiers from the base
				newbase->getSoldiers()->clear();

				for (auto &temp_craft : *newbase->getCrafts())
				{
				
					auto& vehicles = *temp_craft->getVehicles();

					for (auto it = vehicles.begin(); it != vehicles.end();)
					{
						Vehicle* temp_vehicle = *it;

						const RuleItem* rule = temp_vehicle->getRules();
						newbase->getItemsCoop()->addItem(rule);

						if (rule->getVehicleClipAmmo())
						{
							newbase->getItemsCoop()->addItem(rule->getVehicleClipAmmo(), rule->getVehicleClipsLoaded());
						}

						it = vehicles.erase(it);
						delete temp_vehicle;
					}
				
				}

				newbase->getVehicles()->clear();

				newbase->cleanupDefenses(false);

				for (auto* unit_base : *oldsave->getBases())
				{

					// vehicles
					for (auto& old_craft : *unit_base->getCrafts())
					{

						for (auto& old_vehicle : *old_craft->getVehicles())
						{

							for (auto& new_craft : *newbase->getCrafts())
							{

								// find the old co-op vehicle that matches the new co-op vehicle
								if (old_vehicle->getCoopBase() == newbase->_coop_base_id && new_craft->getType() == old_vehicle->getCoopCraftType() && new_craft->getId() == old_vehicle->getCoopCraft())
								{

									// check if this vehicle item exists in the base inventory
									int vehicle_count = newbase->getItemsCoop()->getItem(old_vehicle->getRules());

									if (vehicle_count > 0)
									{

										Vehicle* deep_vehicle = old_vehicle->clone();

										new_craft->getVehicles()->push_back(deep_vehicle);

										const RuleItem* v_rule = deep_vehicle->getRules();

										newbase->getItemsCoop()->removeItem(v_rule);

										const RuleItem* ammo = v_rule->getVehicleClipAmmo();
										int ammoPerVehicle = v_rule->getVehicleClipsLoaded();

										newbase->getItemsCoop()->removeItem(ammo, ammoPerVehicle);

									}


									break;

								}

							}

						}

					}
						
					// soldiers
					for (auto& soldier : *unit_base->getSoldiers())
					{

						// if a co-op soldier is found in the co-op base
						if (soldier->getCoopBase() == newbase->_coop_base_id)
						{

							Soldier* deep_copied_soldier = soldier->deepCopy(_game->getMod(), _game->getSavedGame());

							newbase->getSoldiers()->push_back(deep_copied_soldier);

						}
					}


				}

				

			}


			_game->setSavedGame(newsave);

			// select the clicked base
			Base* selected_base = newsave->getBases()->front();

			for (auto* base : *newsave->getBases())
			{
				if (base->getName() == _game->getCoopMod()->current_base_name)
				{
					selected_base = base;
				}
			}

			_game->pushState(new BasescapeState(selected_base, currentGlobe));


	}
	else
	{

		// battlescape
		if (_game->getCoopMod()->getHost() == true)
		{

			_game->pushState(new LoadGameState(_origin, "battleclient", _palette, "battleclient"));

		}
		else
		{

			// load battle
			_game->pushState(new LoadGameState(_origin, "battleclient", _palette, "battleclient"));

		}
	}

}

void CoopState::setGlobe(Globe *globe)
{
	currentGlobe = globe;
}

void CoopState::loadCoop(Action *)
{

	loadWorld();

}

}
