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
#include "ConfirmLoadState.h"
#include "../Engine/Game.h"
#include "../Mod/Mod.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextList.h"
#include "../Engine/Options.h"
#include "LoadGameState.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the Confirm Load screen.
 * @param game Pointer to the core game.
 * @param origin Game section that originated this state.
 * @param fileName Name of the save file without extension.
 * @param missingMods List of mod names from the save that are not currently active.
 */
ConfirmLoadState::ConfirmLoadState(OptionsOrigin origin, const std::string &fileName, const std::vector<std::string> &missingMods) : _origin(origin), _fileName(fileName), _missingMods(missingMods)
{
	_screen = false;

	bool hasMods = !_missingMods.empty();

	if (hasMods)
	{
		_window = new Window(this, 258, 154, 31, 23, POPUP_BOTH);
		_btnYes = new TextButton(90, 14, 155, 153);
		_btnNo = new TextButton(65, 14, 75, 153);
		_txtText = new Text(248, 48, 36, 33);
		_lstMods = new TextList(242, 72, 39, 74);
	}
	else
	{
		_window = new Window(this, 216, 100, 52, 50, POPUP_BOTH);
		_btnYes = new TextButton(50, 20, 70, 120);
		_btnNo = new TextButton(50, 20, 200, 120);
		_txtText = new Text(204, 58, 58, 60);
	}

	// Set palette
	setInterface("saveMenus", false, battlePaletteSource(_origin == OPT_BATTLESCAPE));

	add(_window, "confirmLoad", "saveMenus");
	add(_btnYes, "confirmLoad", "saveMenus");
	add(_btnNo, "confirmLoad", "saveMenus");
	add(_txtText, "confirmLoad", "saveMenus");
	if (hasMods)
	{
		add(_lstMods, "list", "saveMenus");
	}

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "saveMenus");

	if (hasMods)
	{
		_btnYes->setText("LOAD ANYWAY");
		_btnNo->setText(tr("STR_CANCEL"));
	}
	else
	{
		_btnYes->setText(tr("STR_YES"));
		_btnNo->setText(tr("STR_NO"));
	}
	_btnYes->onMouseClick((ActionHandler)&ConfirmLoadState::btnYesClick);
	_btnYes->onKeyboardPress((ActionHandler)&ConfirmLoadState::btnYesClick, Options::keyOk);

	_btnNo->onMouseClick((ActionHandler)&ConfirmLoadState::btnNoClick);
	_btnNo->onKeyboardPress((ActionHandler)&ConfirmLoadState::btnNoClick, Options::keyCancel);

	_txtText->setAlign(ALIGN_CENTER);
	_txtText->setBig();
	_txtText->setWordWrap(true);
	if (hasMods)
	{
		std::string msg = tr("STR_MISSING_CONTENT_PROMPT");
		size_t pos = msg.rfind("{NEWLINE}");
		if (pos == std::string::npos)
			pos = msg.rfind('\n');
		if (pos != std::string::npos)
			msg = msg.substr(0, pos);
		_txtText->setText(msg);
	}
	else
	{
		_txtText->setText(tr("STR_MISSING_CONTENT_PROMPT"));
	}

	if (hasMods)
	{
		int maxVerLen = 0;
		auto checkVer = [&](const std::string& modEntry) {
			auto splitMod = [](const std::string& s, std::string& name, std::string& ver) {
				name = s; ver.clear();
				size_t sep = s.rfind(" ver: ");
				if (sep != std::string::npos) { name = s.substr(0, sep); ver = "v" + s.substr(sep + 5); }
			};
			std::string name, ver;
			splitMod(modEntry, name, ver);
			if ((int)ver.length() > maxVerLen) maxVerLen = (int)ver.length();
		};
		for (const auto& mod : _missingMods)
			checkVer(mod);
		for (int i = 1; i <= 10; ++i)
			checkVer("DUMMY_MOD_" + std::to_string(i) + " ver: " + std::to_string(i * 10) + "." + std::to_string(i * 10 + 1) + "." + std::to_string(i * 10 + 2));

		int verColWidth = maxVerLen * 4 + 2;

		_lstMods->setColumns(2, 224 - verColWidth, verColWidth);
		_lstMods->setAlign(ALIGN_RIGHT, 1);
		_lstMods->setSelectable(true);
		_lstMods->setBackground(_window);
		_lstMods->setMargin(4);
		_lstMods->setScrolling(true, -12);

		auto addModRow = [&](const std::string& modEntry) {
			std::string name = modEntry;
			std::string version;
			size_t sep = modEntry.rfind(" ver: ");
			if (sep != std::string::npos)
			{
				name = modEntry.substr(0, sep);
				version = "v" + modEntry.substr(sep + 6);
			}
			_lstMods->addRow(2, name.c_str(), version.c_str());
		};

		for (const auto& mod : _missingMods)
			addModRow(mod);
		for (int i = 1; i <= 10; ++i)
		{
			std::string name = "DUMMY_MOD_" + std::to_string(i);
			if (i == 5)
			{
				name = "VERY_LONG_DUMMY_MOD_NAME_THAT_INTENTIONALLY_OVERFLOWS_THE_MOD_NAME_COLUMN_WIDTH_TO_TEST_HOW_THE_TEXT_LIST_HANDLES_EXTREMELY_LONG_MOD_NAMES_WITH_MANY_CHARACTERS_EXCEEDING_THE_ALLOCATED_SPACE";
			}
			addModRow(name + " ver: " + std::to_string(i * 10) + "." + std::to_string(i * 10 + 1) + "." + std::to_string(i * 10 + 2));
		}
	}
	if (_origin == OPT_BATTLESCAPE)
	{
		applyBattlescapeTheme("saveMenus");
	}
}

/// Cleans up the confirmation state.
ConfirmLoadState::~ConfirmLoadState()
{
}

/**
 * Proceed to load the save.
 * @param action Pointer to an action.
 */
void ConfirmLoadState::btnYesClick(Action *)
{
	_game->popState();
	_game->pushState(new LoadGameState(_origin, _fileName, _palette));
}

/**
 * Abort loading and return to save list.
 * @param action Pointer to an action.
 */
void ConfirmLoadState::btnNoClick(Action *)
{
	_game->popState();
}

}
