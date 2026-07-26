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
#include "GiftSoldierMenu.h"

#include <sstream>

#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/Options.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Soldier.h"
#include "connectionTCP.h"

namespace OpenXcom
{

int GiftSoldierMenu::resolveOwnerId(Soldier *soldier)
{
	if (soldier->getOwnerPlayerId() != 999)
	{
		return soldier->getOwnerPlayerId();
	}
	// 999 = never explicitly assigned. Such a soldier belongs to the player
	// whose save it lives in - i.e. the LOCAL player, on whichever machine
	// the dialog is open. (The old fallback returned 0/host, which on the
	// client's machine offered the client their own name as a transfer
	// target for their own fresh soldiers.)
	return connectionTCP::localSeat();
}

GiftSoldierMenu::GiftSoldierMenu(Soldier *soldier, int currentOwnerId)
	: _soldier(soldier), _battleUnit(nullptr),
	  _unitName(soldier ? soldier->getName() : "UNIT")
{
	init(currentOwnerId);
}

GiftSoldierMenu::GiftSoldierMenu(BattleUnit *battleUnit, int currentOwnerId)
	: _soldier(nullptr), _battleUnit(battleUnit),
	  _unitName(battleUnit ? battleUnit->getName(_game->getLanguage()) : "UNIT")
{
	init(currentOwnerId);
}

void GiftSoldierMenu::init(int currentOwnerId)
{
	_screen = false;

	// One button per player that is not the current owner. The same target
	// list is used for campaign soldiers and Custom Battle units so Custom
	// Battle does not silently transfer to an assumed two-player target.
	connectionTCP *coop = _game->getCoopMod();
	const int localPlayerId = connectionTCP::localSeat();
	int playerCount = connectionTCP::seatCount();
	if (playerCount < 2)
	{
		playerCount = 2;
	}

	std::vector<std::pair<int, std::string> > targets;
	for (int playerId = 0; playerId < playerCount; ++playerId)
	{
		if (playerId == currentOwnerId)
		{
			continue;
		}

		std::string name = connectionTCP::seatName(playerId);
		if (name.empty())
		{
			// Legacy two-player fallback for sessions whose roster names have not
			// yet been copied into SavedGame::_coopPlayers.
			name = (playerId == localPlayerId)
				? coop->getHostName()
				: coop->getCurrentClientName();
		}
		if (name.empty())
		{
			std::ostringstream fallback;
			fallback << "PLAYER " << (playerId + 1);
			name = fallback.str();
		}
		targets.push_back(std::make_pair(playerId, name));
	}

	const int btnHeight = 16;
	const int btnSpacing = 4;
	const int windowWidth = 240;
	const int windowHeight = 60 + (int)(targets.size() + 1) * (btnHeight + btnSpacing);
	const int windowX = (320 - windowWidth) / 2;
	const int windowY = (200 - windowHeight) / 2;

	_window = new Window(this, windowWidth, windowHeight, windowX, windowY, POPUP_BOTH);
	_txtTitle = new Text(windowWidth - 20, 32, windowX + 10, windowY + 12);

	int y = windowY + 48;
	for (size_t i = 0; i < targets.size(); ++i)
	{
		_btnTargets.push_back(new TextButton(windowWidth - 40, btnHeight, windowX + 20, y));
		_targetIds.push_back(targets[i].first);
		y += btnHeight + btnSpacing;
	}
	_btnCancel = new TextButton(windowWidth - 40, btnHeight, windowX + 20, y);

	// sackSoldier: a base-palette dialog interface. Using pauseMenu here
	// (geoscape palette) forced a hardware palette swap when opened over the
	// basescape soldier screens, flashing the whole screen on open and close.
	// The battle-game param switches to the battlescape palette in battle.
	// Out of battle, sackSoldier's base palette avoids a hardware palette flash
	// over the basescape soldier screens. In the battlescape those colors are
	// illegible, so match the coop lobby window exactly (geoscape interface with
	// alterPal, saveMenus element colors, under the battle palette).
	SavedBattleGame *battle = _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0;
	std::string cat = "sackSoldier";
	if (battle)
	{
		setInterface("geoscape", true, battle);
		cat = "saveMenus";
	}
	else
	{
		setInterface("sackSoldier", false, 0);
	}

	add(_window, "window", cat);
	add(_txtTitle, "text", cat);
	for (auto *btn : _btnTargets)
	{
		add(btn, "button", cat);
	}
	add(_btnCancel, "button", cat);

	centerAllSurfaces();
	if (battle)
	{
		// Same as the coop lobby in battle: uniform battlescape theme color +
		// high contrast + TAC00 background.
		setWindowBackground(_window, cat);
		applyBattlescapeTheme(cat);
	}
	else
	{
		setWindowBackground(_window, cat);
	}

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setWordWrap(true);
	_txtTitle->setText("Gift " + _unitName + " to another player?");

	for (size_t i = 0; i < _btnTargets.size(); ++i)
	{
		_btnTargets[i]->setText(targets[i].second);
		_btnTargets[i]->onMouseClick((ActionHandler)&GiftSoldierMenu::btnGiftClick);
	}

	_btnCancel->setText(tr("STR_CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&GiftSoldierMenu::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&GiftSoldierMenu::btnCancelClick, Options::keyCancel);
}

void GiftSoldierMenu::btnGiftClick(Action *action)
{
	for (size_t i = 0; i < _btnTargets.size(); ++i)
	{
		if (action->getSender() == _btnTargets[i])
		{
			if (_battleUnit)
			{
				// giftBattleUnit() handles both Custom Battle units and campaign
				// BattleUnits. For campaign units it delegates to giftSoldier(),
				// keeping persistent Soldier ownership in sync.
				_game->getCoopMod()->giftBattleUnit(_battleUnit, _targetIds[i], true);
			}
			else if (_soldier)
			{
				_game->getCoopMod()->giftSoldier(_soldier, _targetIds[i], true);
			}
			break;
		}
	}
	_game->popState();
}

void GiftSoldierMenu::btnCancelClick(Action *)
{
	_game->popState();
}

bool GiftSoldierMenu::isBattleUnitGift() const
{
	return _battleUnit != nullptr;
}

int GiftSoldierMenu::getBattleUnitId() const
{
	return _battleUnit ? _battleUnit->getId() : -1;
}

const std::vector<int>& GiftSoldierMenu::getTargetIds() const
{
	return _targetIds;
}

std::string GiftSoldierMenu::getTitleText() const
{
	return _txtTitle ? _txtTitle->getText() : std::string();
}

}
