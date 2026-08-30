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
#include "../Savegame/Craft.h"
#include "../Savegame/Base.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/Vehicle.h"
#include "../Mod/AlienDeployment.h"
#include "../Engine/Options.h"
#include "../CoopMod/connectionTCP.h"
#include "../CoopMod/CoopState.h"

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
		_game->getCoopMod()->setSelectedCraft(_craft);
		_game->getCoopMod()->setConfirmCydoniaState(this);

		if (_game->getCoopMod()->isSharedCampaign())
		{
			// SHARED owns one world, so generate Cydonia once on the host and stream
			// that authoritative battle instead of running the separate-world merge.
			_game->getCoopMod()->setHost(true);
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
			startCoopMission();
			return;
		}

		if (!_game->getCoopMod()->getHost())
		{
			// The existing separate-campaign merge is host-authoritative, so hand
			// authority to the player who selected Cydonia before starting it.
			Json::Value root;
			root["state"] = "changeHost";
			_game->getCoopMod()->sendTCPPacketData(root.toStyledString());
			_game->getCoopMod()->setHost(true);
		}

		_game->pushState(new CoopState(88));
		return;
	}

	_game->popState();
	_game->popState();
	startCoopMission();
}

void ConfirmCydoniaState::startCoopMission()
{
	// The shared path can be re-entered by delayed network callbacks. Never
	// replace an already-streamed Mars map with a second random generation.
	if (_game->getCoopMod()->isSharedCampaign() && _game->getSavedGame()
		&& _game->getSavedGame()->getSavedBattle())
	{
		return;
	}

	if (connectionTCP::getCoopStatic())
	{
		_game->getCoopMod()->coopInventory = true;
	}

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
		BriefingState* briefing = new BriefingState(_craft);
		briefing->setupCoop();
	}
	else
	{
		_game->pushState(new BriefingState(_craft));
	}
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
