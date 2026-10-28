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
#include "AbandonGameState.h"
#include "../Engine/Sound.h"
#include "../Engine/Game.h"
#include "../Engine/Options.h"
#include "../Mod/Mod.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "MainMenuState.h"
#include "../Engine/Screen.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/SavedBattleGame.h"
#include "SaveGameState.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the Abandon Game screen.
 * @param game Pointer to the core game.
 * @param origin Game section that originated this state.
 */
AbandonGameState::AbandonGameState(OptionsOrigin origin) : _origin(origin)
{
	_screen = false;

	int x;
	if (_origin == OPT_GEOSCAPE)
	{
		x = 20;
	}
	else
	{
		x = 52;
	}

	// Create objects
	_window = new Window(this, 216, 160, x, 20, POPUP_BOTH);
	_btnYes = new TextButton(50, 20, x+18, 140);
	_btnNo = new TextButton(50, 20, x+148, 140);
	_txtTitle = new Text(206, 17, x+5, 70);

	// Set palette
	setInterface("geoscape", false, battlePaletteSource(_origin == OPT_BATTLESCAPE));

	add(_window, "genericWindow", "geoscape");
	add(_btnYes, "genericButton2", "geoscape");
	add(_btnNo, "genericButton2", "geoscape");
	add(_txtTitle, "genericText", "geoscape");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "geoscape");

	_btnYes->setText(tr("STR_YES"));
	_btnYes->onMouseClick((ActionHandler)&AbandonGameState::btnYesClick);
	_btnYes->onKeyboardPress((ActionHandler)&AbandonGameState::btnYesClick, Options::keyOk);

	_btnNo->setText(tr("STR_NO"));
	_btnNo->onMouseClick((ActionHandler)&AbandonGameState::btnNoClick);
	_btnNo->onKeyboardPress((ActionHandler)&AbandonGameState::btnNoClick, Options::keyCancel);

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText(tr("STR_ABANDON_GAME_QUESTION"));

	if (_origin == OPT_BATTLESCAPE)
	{
		applyBattlescapeTheme("geoscape");
	}
}

/**
 *
 */
AbandonGameState::~AbandonGameState()
{

}

/**
 * Goes back to the Main Menu.
 * @param action Pointer to an action.
 */
void AbandonGameState::btnYesClick(Action *)
{

	// coop W2-H53 (L-H49-3; R-H53-0, R-H49-0; F17782): read before the disconnect below, which ends the gm3 alien host's borrow. An
	// ironman alien host in a borrowed battle saves its own world first and leaves through SaveGameState's quit (the session ends after
	// the write, as a wait dialog's SAVE & QUIT): after the disconnect the save would name and write the borrowed X-COM world.
	SavedGame* coopOwner = connectionTCP::coopPvpSaveOwner(_game->getSavedGame());
	const bool coopIronmanBorrow = coopOwner != _game->getSavedGame() && coopOwner->isIronman();

	// coop
	if (_game->getCoopMod()->getCoopStatic() == true && !coopIronmanBorrow)
	{
		_game->getCoopMod()->disconnectTCP();
	}


	// Reset touch flags
	_game->resetTouchButtonFlags();

	if (_origin == OPT_BATTLESCAPE && _game->getSavedGame()->getSavedBattle()->getAmbientSound() != Mod::NO_SOUND)
		_game->getMod()->getSoundByDepth(0, _game->getSavedGame()->getSavedBattle()->getAmbientSound())->stopLoop();
	if (!coopIronmanBorrow && !_game->getSavedGame()->isIronman()) // coop
	{
		// issue #82: one chokepoint owns the geoscape rescale AND dropping the world.
		// Clearing the save here would delete it while the states popped by setState are
		// still queued for destruction; GoToMainMenuState::init runs after that flush.
		_game->setState(new GoToMainMenuState(false));
	}
	else
	{
		_game->pushState(new SaveGameState(OPT_GEOSCAPE, SAVE_IRONMAN_END, _palette, 0, coopIronmanBorrow)); // coop: quit after the write
	}
}

/**
 * Closes the window.
 * @param action Pointer to an action.
 */
void AbandonGameState::btnNoClick(Action *)
{
	_game->popState();
}

}
