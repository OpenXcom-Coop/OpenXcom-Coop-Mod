/*
 * Copyright 2010-2016 OpenXcom Developers.
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
#include "LoadGameState.h"
#include <sstream>
#include "../Engine/Logger.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Base.h"
#include "../Engine/Game.h"
#include "../Engine/Exception.h"
#include "../Engine/Options.h"
#include "../Engine/CrossPlatform.h"
#include "../Engine/Screen.h"
#include "../Engine/LocalizedText.h"
#include "../Interface/Text.h"
#include "../Geoscape/GeoscapeState.h"
#include "ErrorMessageState.h"
#include "../Battlescape/BattlescapeState.h"
#include "../Mod/Mod.h"
#include "../Engine/Sound.h"
#include "../Engine/Unicode.h"
#include "../Mod/RuleInterface.h"
#include "StatisticsState.h"
#include "../CoopMod/HostMenu.h"
#include "../CoopMod/CoopState.h"
#include "../CoopMod/connectionTCP.h"
#include "../CoopMod/SharedEcon.h"
#include "../CoopMod/CoopBattleUi.h"
#include "../Savegame/Upgrade/SaveUpgrade.h"
#include "SaveUpgradeDialogState.h"
#include "SaveUpgradeMessageState.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the Load Game screen.
 * @param game Pointer to the core game.
 * @param origin Game section that originated this state.
 * @param filename Name of the save file without extension.
 * @param palette Parent state palette.
 */
LoadGameState::LoadGameState(OptionsOrigin origin, const std::string& filename, SDL_Color* palette, const std::string& coopKey, bool loadCoopProgress) : _firstRun(0), _origin(origin), _filename(filename), _coopKey(coopKey), _loadCoopProgress(loadCoopProgress)
{

	// coop
	connectionTCP::_coopGamemode = 0;

	buildUi(palette);
}

/**
 * Initializes all the elements in the Load Game screen.
 * @param game Pointer to the core game.
 * @param origin Game section that originated this state.
 * @param type Type of auto-load being used.
 * @param palette Parent state palette.
 */
LoadGameState::LoadGameState(OptionsOrigin origin, SaveType type, SDL_Color *palette) : _firstRun(0), _origin(origin), _loadCoopProgress(false)
{

	// coop
	connectionTCP::_coopGamemode = 0;

	switch (type)
	{
	case SAVE_QUICK:
		_filename = SavedGame::QUICKSAVE;
		break;
	case SAVE_AUTO_GEOSCAPE:
		_filename = SavedGame::AUTOSAVE_GEOSCAPE;
		break;
	case SAVE_AUTO_BATTLESCAPE:
		_filename = SavedGame::AUTOSAVE_BATTLESCAPE;
		break;
	default:
		// can't auto-load ironman games
		break;
	}

	buildUi(palette);
}

/**
 *
 */
LoadGameState::~LoadGameState()
{

}

/**
 * Builds the interface.
 * @param palette Parent state palette.
 */
void LoadGameState::buildUi(SDL_Color *palette)
{
	_screen = false;

	// Create objects
	_txtStatus = new Text(320, 17, 0, 92);

	// Set palette
	setStatePalette(palette);

	if (_origin == OPT_BATTLESCAPE)
	{
		add(_txtStatus, "textLoad", "battlescape");
		_txtStatus->setHighContrast(true);
		// coop fix
		if (_game->getSavedGame()->getSavedBattle())
		{
			if (_game->getSavedGame()->getSavedBattle()->getAmbientSound() != Mod::NO_SOUND)
			{
				_game->getMod()->getSoundByDepth(0, _game->getSavedGame()->getSavedBattle()->getAmbientSound())->stopLoop();
			}
		}
	}
	else
	{
		add(_txtStatus, "textLoad", "geoscape");
	}

	centerAllSurfaces();

	// Set up objects
	_txtStatus->setBig();
	_txtStatus->setAlign(ALIGN_CENTER);
	_txtStatus->setText(tr("STR_LOADING_GAME"));

}

/**
 * Ignore quick loads without a save available.
 */
void LoadGameState::init()
{
	State::init();
	// During a multi-stage transfer the modal CoopState underneath already says
	// "Downloading map...".  Keep this transparent loader silent so that one
	// continuous dialog remains visible until the new briefing replaces it.
	if (!_coopKey.empty() && connectionTCP::nextStageBriefing)
		_txtStatus->setVisible(false);

	// Chokepoint gate: a machine that may not touch local saves (coop client)
	// can only reach a plain local load through the pause menu / list / confirm
	// states or a directly-pushed LoadGameState. The coop-orchestrated flows -
	// loading a host-provided blob (_coopKey set) or a resume/rejoin
	// (_loadCoopProgress) - are NOT local loads and must still run. Refuse only
	// the plain local load.
	if (!_game->getCoopMod()->localLoadsAllowed() && _coopKey.empty() && !_loadCoopProgress)
	{
		// One guarded coop call gives this refusal a face (without it the state
		// pops and the player sees nothing at all), on the same _txtCoopWait
		// surface every other coop message uses. Presenter only: the
		// decision was already taken by the line above, and this call takes none.
		// It no-ops when no battle is live, so a GEOSCAPE-side local load stays
		// log-only for now (that surface does not exist there) - stated as a
		// known limit rather than papered over.
		CoopBattleUi::showControlRefused(CoopBattleUi::Control::QuickLoad);
		Log(LOG_INFO) << "[coop] local load refused: no local loads during a live coop session (PRD-08)";
		_game->popState();
		return;
	}

	if (_filename == SavedGame::QUICKSAVE && !CrossPlatform::fileExists(Options::getMasterUserFolder() + _filename))
	{
		_game->popState();
		return;
	}

	// Save-schema load gate (PRD save-upgrader.md 4): classify the file before it
	// is ever handed to SavedGame::load. Legacy co-op saves route to the upgrade
	// dialog; saves from a newer build get an informative refusal; current/solo
	// saves load as usual; malformed saves fall through to the load error path.
	// Coop-orchestrated loads (host-served blobs / resume) are upgraded host-side
	// and must never gate, so they are excluded here. Solo saves never gate; only a
	// positively-detected legacy co-op save (detector v2.3) reaches the dialog.
	if (_coopKey.empty() && !_loadCoopProgress && !_gateChecked)
	{
		_gateChecked = true;
		SaveUpgrade::DetectedSchema detected = SaveUpgrade::SchemaDetector::detect(_filename);
		if (detected.kind == SaveUpgrade::DetectedSchema::UnknownFuture)
		{
			std::vector<std::string> lines;
			lines.push_back(tr("STR_SAVE_UPGRADE_FUTURE").arg(detected.schema));
			_game->popState();
			_game->pushState(new SaveUpgradeMessageState(_origin, tr("STR_SAVE_UPGRADE_FUTURE_TITLE"), lines));
			return;
		}
		if (detected.needsUpgrade())
		{
			_game->popState();
			_game->pushState(new SaveUpgradeDialogState(_origin, _filename, detected));
			return;
		}
	}
}

/**
 * Loads the specified save.
 */
void LoadGameState::think()
{
	State::think();
	// Make sure it gets drawn properly
	if (_firstRun < 10)
	{
		_firstRun++;
	}
	else
	{
		const bool keepNextStageLoader = !_coopKey.empty()
			&& connectionTCP::nextStageBriefing;
		// Ordinary loads remove this state before doing the synchronous work, as
		// before. A next-stage load must remain modal: popping it here exposes the
		// previous Battlescape between file receipt and the new briefing.
		if (!keepNextStageLoader)
			_game->popState();

		// Remember for later (palette reset)
		BattlescapeState *origBattleState = 0;
		if (_game->getSavedGame() != 0 && _game->getSavedGame()->getSavedBattle() != 0)
		{
			origBattleState = _game->getSavedGame()->getSavedBattle()->getBattleState();
		}

		// Reset touch flags
		_game->resetTouchButtonFlags();

		// Load the game
		SavedGame *s = new SavedGame();
		try
		{

			// coop
			if (_coopKey.empty())
			{
				s->load(_filename, _game->getMod(), _game->getLanguage());
				// the loaded save is now the authority - drop stale
				// in-memory transfer session state
				_game->getCoopMod()->resetGiftSessionState();
			}
			else
			{
				s->loadCoopSaveFromMemory(_filename, _game->getMod(), _game->getLanguage(), _coopKey);
			}

			// PRD-J02: a SHARED save carries the host's single authoritative world
			// and cannot be opened as a plain single-player game. On a build
			// without SHARED support the type key is unknown and the whole feature
			// is absent; on this build we refuse the one reachable downgrade - a
			// SHARED-typed save that is not co-op-marked (e.g. hand-edited).
			if (s->getCampaignType() == CoopCampaignType::Shared && !s->isCoopSave())
			{
				throw Exception("This is a SHARED co-op campaign save and cannot be opened as a single-player game.");
			}

			// Separate: a client's saved templates are its own. When the host
			// replaces the client's campaign world (a restream, a battle, the
			// world after a battle, a rejoin while the world is still held),
			// keep the set the client already has. A client without a campaign
			// world took its set from its player profile in the stream.
			if (!_coopKey.empty() && !_game->getCoopMod()->getServerOwner()
				&& s->isSeparateCoopCampaign()
				&& _game->getSavedGame() && _game->getSavedGame()->isSeparateCoopCampaign())
			{
				s->copyTemplatesFrom(*_game->getSavedGame());
			}

			_game->setSavedGame(s);

			// Separate Research sharing is a negotiated session policy, not save
			// data.  Loading an authoritative campaign world replaces SavedGame and
			// therefore resets its transient policy flag.  Restore it immediately;
			// otherwise the connection still says Shared Research while research
			// availability silently uses the per-player tree until the next reload.
			if (!_coopKey.empty()
				&& s->getCampaignType() == CoopCampaignType::Separate
				&& _game->getCoopMod())
			{
				s->setSeparateResearchSharingEnabled(
					_game->getCoopMod()->_enable_research_sync, _game->getMod());
			}

			// PRD-J02: a SHARED client just adopted the host's world as its replica.
			// The streamed save carries the HOST's coop_save_owner_player_id (0);
			// re-assert this machine's own seat so localSeat() reflects the client,
			// not the host. (2-player transport: client seat = 1.)
			if (!_coopKey.empty()
				&& (_game->getCoopMod()->isSharedCampaign() || _game->getCoopMod()->isSeparateCampaign())
				&& _game->getCoopMod()->getServerOwner() == false)
			{
				connectionTCP::coop_save_owner_player_id = 1;
				// Base::load ran before the streamed save's complete roster and this
				// client's seat were installed. Rebuild the view flags now so only
				// bases owned by another player's name are purple/foreign.
				_game->getCoopMod()->refreshSeparateBaseOwnership();

				// PRD-J10: a fresh authoritative world landed - this is also how a
				// desync repair completes. Clear the resync in-flight guard so a
				// later drift can be repaired again (and so the "give up" latch is
				// re-armed for the next window).
				SharedEcon::notifyWorldAdopted();
			}
			if (_game->getSavedGame()->getEnding() != END_NONE)
			{
				Options::baseXResolution = Screen::ORIGINAL_WIDTH;
				Options::baseYResolution = Screen::ORIGINAL_HEIGHT;
				_game->getScreen()->resetDisplay(false);
				_game->setState(new StatisticsState);
			}
			else
			{
				// An authoritative campaign snapshot already contains its live
				// SavedBattleGame. Resume it directly instead of discarding it and
				// requesting the same battle in a second transfer.
				const bool coopBattleResumeWorld = _loadCoopProgress
					&& _game->getSavedGame()->getSavedBattle() != nullptr;
				if (coopBattleResumeWorld
					&& connectionTCP::session.lobbyMode != 0
					&& _game->getCoopMod()->getServerOwner() == false)
				{
					// This is an already-running saved battle, not a newly dispatched
					// mission. The removed phase-two transfer used to clear this flag;
					// keep the combined path from reopening Briefing and Inventory.
					_game->getCoopMod()->inventory_battle_window = false;
				}
				Options::baseXResolution = Options::baseXGeoscape;
				Options::baseYResolution = Options::baseYGeoscape;
				_game->getScreen()->resetDisplay(false);
				if (origBattleState != 0)
				{
					// We need to reset palettes here already, can't wait for the destructor
					origBattleState->resetPalettes();
				}
				_game->setState(new GeoscapeState);

				// coop fix
				if (_loadCoopProgress == true)
				{
					// A geoscape-only resume must not retain a stale tactical save.
					// A combined battle resume deliberately keeps the battle embedded
					// in this same authoritative snapshot.
					if (!coopBattleResumeWorld)
						_game->getSavedGame()->setBattleGame(0);

					// resume/rejoin: report the loaded world to the host and
					// hold with frozen time until it resumes (F3/F4/D5)
					if (connectionTCP::session.lobbyMode != 0
						&& _game->getCoopMod()->getServerOwner() == false)
					{
						Json::Value root;
						root["state"] = "resume_ack";
						// issue #91: this ack is the one that comes with a HOLD attached -
						// we just adopted a streamed world and are about to park in
						// COOP_DLG_CLIENT_RESUME_HOLD until the host releases us. Say so,
						// so the host can tell it apart from the other resume_ack senders
						// (base naming, battle phase two), which hold nothing and must not
						// be answered with a campaign_begun.
						root["adoptedWorld"] = true;
						root["combinedBattle"] = coopBattleResumeWorld;
						_game->getCoopMod()->sendTCPPacketData(root.toStyledString());

						// A normal world resume waits for the host's release. A combined
						// battle resume enters its Battlescape below without a second hold.
						if (!coopBattleResumeWorld)
							_game->pushState(new CoopState(COOP_DLG_CLIENT_RESUME_HOLD));
					}
				}

				if (_game->getSavedGame()->getSavedBattle() != 0)
				{
					// The vanilla push below is unconditional, byte-identical to SP
					// mid-battle resume: the host always loads BEFORE hosting, so
					// getCoopStatic() is false at this menu load, a connected client can
					// never reach LoadGameState at all (localLoadsAllowed()), and a coop
					// mid-battle save is served to a rejoining peer by the disk-resume flow
					// (CoopHandshake::offerResumedBattle(), connectionTCP.cpp).
					_game->getSavedGame()->getSavedBattle()->loadMapResources(_game->getMod());
					Options::baseXResolution = Options::baseXBattlescape;
					Options::baseYResolution = Options::baseYBattlescape;
					_game->getScreen()->resetDisplay(false);
					BattlescapeState *bs = new BattlescapeState;

					_game->pushState(bs);

					_game->getSavedGame()->getSavedBattle()->setBattleState(bs);
					// Try to reactivate the touch buttons
					bs->toggleTouchButtons(false, true);
				}

				// flow-redesign F3: a co-op campaign save loaded from the
				// menu opens a lobby-gated session - host window on top of
				// the paused world; RESUME serves every client its world.
				if (_coopKey.empty()
					&& _game->getSavedGame()->isCoopSave()
					&& _game->getCoopMod()->getCoopStatic() == false)
				{
					connectionTCP::session.adoptResumeSave();
					// the host identity is locked to the save (D4): adopt it,
					// so the UI flow can never host under a different name.
					// A migrated legacy save leaves the host slot blank (the
					// old format carried no host name) - keep the local name
					// and let the host claim the slot at re-host time.
					if (!_game->getSavedGame()->getCoopPlayers().empty()
						&& !_game->getSavedGame()->getCoopPlayers()[0].empty())
					{
						_game->getCoopMod()->setHostName(_game->getSavedGame()->getCoopPlayers()[0]);
					}
					_game->pushState(new HostMenu());
				}
			}

			// Clear the SDL event queue (i.e. ignore input from impatient users)
			SDL_Event e;
			while (SDL_PollEvent(&e))
			{
				// do nothing
			}
		}
		catch (Exception &e)
		{
			if (keepNextStageLoader && _game->isState(this))
				_game->popState();
			error(e.what(), s);
		}
		catch (YAML::Exception &e)
		{
			if (keepNextStageLoader && _game->isState(this))
				_game->popState();
			error(e.what(), s);
		}
		CrossPlatform::flashWindow();
	}
}

/**
 * Pops up a window with an error message
 * and cleans up afterwards.
 * @param msg Error message.
 * @param save Pending save.
 */
void LoadGameState::error(const std::string &msg, SavedGame *save)
{

	Log(LOG_ERROR) << msg;
	std::ostringstream error;
	error << tr("STR_LOAD_UNSUCCESSFUL") << Unicode::TOK_NL_SMALL << msg;
	if (_origin != OPT_BATTLESCAPE)
		_game->pushState(new ErrorMessageState(error.str(), _palette, _game->getMod()->getInterface("errorMessages")->getElement("geoscapeColor")->color, "BACK01.SCR", _game->getMod()->getInterface("errorMessages")->getElement("geoscapePalette")->color));
	else
		_game->pushState(new ErrorMessageState(error.str(), _palette, _game->getMod()->getInterface("errorMessages")->getElement("battlescapeColor")->color, "TAC00.SCR", _game->getMod()->getInterface("errorMessages")->getElement("battlescapePalette")->color));

	if (_game->getSavedGame() == save)
		_game->setSavedGame(0);
	else
		delete save;
}

}
