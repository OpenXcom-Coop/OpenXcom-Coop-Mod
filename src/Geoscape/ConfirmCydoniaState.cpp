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
#include "ConfirmCydoniaState.h"
#include "../Engine/Game.h"
#include "../Mod/Mod.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Battlescape/BattlescapeGenerator.h"
#include "../Battlescape/BriefingState.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/Craft.h"
#include "../Savegame/Base.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/Vehicle.h"
#include "../Mod/AlienDeployment.h"
#include "../Engine/Options.h"
#include "../CoopMod/connectionTCP.h"
#include "../CoopMod/CoopState.h"
#include "../CoopMod/CoopHandshake.h"

namespace OpenXcom
{

ConfirmCydoniaState::ConfirmCydoniaState(Craft *craft) : _craft(craft)
{
	_screen = false;

	// Create objects
	_window = new Window(this, 256, 160, 32, 20);
	_btnYes = new TextButton(80, 20, 70, 142);
	_btnNo = new TextButton(80, 20, 170, 142);
	_txtMessage = new Text(224, 48, 48, 76);

	// Set palette
	setInterface("confirmCydonia");

	add(_window, "window", "confirmCydonia");
	add(_btnYes, "button", "confirmCydonia");
	add(_btnNo, "button", "confirmCydonia");
	add(_txtMessage, "text", "confirmCydonia");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "confirmCydonia");

	_btnYes->setText(tr("STR_YES"));
	_btnYes->onMouseClick((ActionHandler)&ConfirmCydoniaState::btnYesClick);
	_btnYes->onKeyboardPress((ActionHandler)&ConfirmCydoniaState::btnYesClick, Options::keyOk);

	_btnNo->setText(tr("STR_NO"));
	_btnNo->onMouseClick((ActionHandler)&ConfirmCydoniaState::btnNoClick);
	_btnNo->onKeyboardPress((ActionHandler)&ConfirmCydoniaState::btnNoClick, Options::keyCancel);

	_txtMessage->setAlign(ALIGN_CENTER);
	_txtMessage->setBig();
	_txtMessage->setWordWrap(true);
	_txtMessage->setText(tr("STR_ARE_YOU_SURE_CYDONIA"));
}

/**
 *
 */
ConfirmCydoniaState::~ConfirmCydoniaState()
{
}

/**
 * Returns to the previous screen.
 * @param action Pointer to an action.
 */
void ConfirmCydoniaState::btnYesClick(Action *)
{
	if (connectionTCP::getCoopStatic())
	{
		// R4-P2 (SPIKE-RUNBOOK.md SS2.7, RB-D18, RB-D23): Cydonia now rides the
		// SAME battle-start handshake R4-P1 built for the skirmish and mission-
		// confirm entry points (NewBattleState::btnOkClick, ConfirmLandingState::
		// btnYesClick) - vanilla generates the battle exactly like SP below, then
		// CoopHandshake::offerBattle() ships it. The per-soldier/vehicle seat-tag
		// pass this branch already ran (donor cbff7951d:96-102, PRD-J09 SHARED
		// path) is PRESERVED so Soldier::getCoop() carries fresh ownership before
		// generation; startCoopMission() below reads it back off each generated
		// BattleUnit's geoscape soldier to stamp the RB-D17 battle-time tag
		// (BattleUnit::setCoopSeat()) offerBattle()/the admission arbiter expect.
		// The legacy SEPARATE-campaign changeHost hand-off + CoopState(88) wait-
		// dialog choreography (donor :113-128) is DELETED - it predates the
		// handshake, has no restored carrier, and (RB-D18) the interim handshake
		// already covers both campaign types under gamemode 0/1.
		for (auto* soldier : *_craft->getBase()->getSoldiers())
		{
			if (soldier->getCraft() != _craft)
				continue;
			int owner = soldier->getOwnerPlayerId();
			soldier->setCoop((owner == 0 || owner == 999) ? 0 : 1);
			soldier->setCoopBase(-1);
		}
		for (auto* vehicle : *_craft->getVehicles())
		{
			vehicle->setCoop(0);
			vehicle->setCoopBase(-1);
		}
	}

	_game->popState();
	_game->popState();
	startCoopMission();
}

void ConfirmCydoniaState::startCoopMission()
{
	SavedBattleGame *bgame = new SavedBattleGame(_game->getMod(), _game->getLanguage());
	_game->getSavedGame()->setBattleGame(bgame);
	BattlescapeGenerator bgen = BattlescapeGenerator(_game);
	for (auto& ad : _game->getMod()->getDeploymentsList())
	{
		AlienDeployment *deployment = _game->getMod()->getDeployment(ad);
		if (deployment->isFinalDestination())
		{
			bgame->setMissionType(ad);
			bgen.setAlienRace(deployment->getRace());
			break;
		}
	}
	bgen.setCraft(_craft);
	bgen.run();

	if (connectionTCP::getCoopStatic())
	{
		// R4-P2: stamp each generated BattleUnit's RB-D17 seat tag from the
		// Soldier::getCoop() ownership btnYesClick just refreshed - the
		// admission arbiter's not_your_unit check (connectionTCP.cpp) reads
		// BattleUnit::getCoopSeat(), not the geoscape Soldier.
		// R5-P1 NOTE (RB-D23): CoopHandshake::offerBattle() below now runs
		// assignSeatsAndFactions() (CoopState.cpp) on the HOST machine, which
		// does this exact stamp itself (plus the canonical-faction funnel and
		// the out-of-roster validity check) - this loop is redundant on the
		// host path since that call. Left in place rather than removed
		// (RB-D23 packet text's "else leave it and note it" - no dedicated
		// Cydonia coverage rode with this packet's acceptance to verify a
		// removal is safe here). Harmless: assignSeatsAndFactions()
		// overwrites whatever this loop set, with the identical value, a few
		// lines later.
		for (auto* unit : *bgame->getUnits())
		{
			Soldier* soldier = unit->getGeoscapeSoldier();
			if (soldier)
			{
				unit->setCoopSeat((CoopSeat)soldier->getCoop());
			}
		}

		// R4-P2 (SS2.7): offerBattle() is a pure network side effect - it never
		// touches the state stack (see CoopHandshake.h's top doc comment for
		// the crash that taught this). BriefingState is pushed exactly like
		// vanilla SP, unconditionally; a refused/corrupt handshake unwinds it
		// via coopUnwindToSafeState() instead (connectionTCP.cpp). offerBattle()
		// itself no-ops (logs) on a non-host machine (RB-D18 interim: only the
		// coop-session's server owner drives Cydonia generation).
		CoopHandshake::offerBattle(_game, connectionTCP::_coopGamemode);
	}

	_game->pushState(new BriefingState(_craft));
}

/**
 * Returns to the previous screen.
 * @param action Pointer to an action.
 */
void ConfirmCydoniaState::btnNoClick(Action *)
{
	_game->popState();
}

}
