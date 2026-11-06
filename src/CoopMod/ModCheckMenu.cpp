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
#include <algorithm>
#include <functional>
#include "ServerList.h"
#include "../Engine/Logger.h"
#include "../Savegame/SavedGame.h"
#include "../Engine/Game.h"
#include "../Engine/Action.h"
#include "../Engine/Exception.h"
#include "../Engine/Options.h"
#include "../Engine/Unicode.h"
#include "../Mod/Mod.h"
#include "../Engine/LocalizedText.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextList.h"
#include "../Interface/ToggleTextButton.h"
#include "../Interface/ArrowButton.h"

#include "ModCheckMenu.h"
#include "connectionUDP/rendezvous_config.h"

namespace OpenXcom
{

struct compareModName
{
	bool _reverse;

	compareModName(bool reverse) : _reverse(reverse) {}

	bool operator()(const ModInfoCoop& a, const ModInfoCoop& b) const
	{
		if (a.reserved == b.reserved)
		{
			return Unicode::naturalCompare(a.modName, b.modName);
		}
		else
		{
			return _reverse ? b.reserved : a.reserved;
		}
	}
};

struct compareModRequired
{
	bool _reverse;

	compareModRequired(bool reverse) : _reverse(reverse) {}

	bool operator()(const ModInfoCoop& a, const ModInfoCoop& b) const
	{
		if (a.reserved == b.reserved)
		{
			return Unicode::naturalCompare(a.modRequired, b.modRequired);
		}
		else
		{
			return _reverse ? b.reserved : a.reserved;
		}
	}
};

/**
 * Initializes all the elements in the Saved Game screen.
 * @param game Pointer to the core game.
 * @param origin Game section that originated this state.
 * @param firstValidRow First row containing saves.
 * @param autoquick Show auto/quick saved games?
 */
ModCheckMenu::ModCheckMenu(std::string modHash, bool showBuild, std::string hostVersion) : _sortable(true), _modHash(modHash)
{
	_screen = false;

	bool isMobile = false;
#ifdef __MOBILE__
	isMobile = true;
#endif

	// Create objects
	_window = new Window(this, 320, 200, 0, 0, POPUP_BOTH);

	int y = 179; // 172
	int h = 16;
	int wCancel = 44;
	int x = 8;

	_btnCancel = new TextButton(wCancel, h, x, y);

	_txtTitle = new Text(310, 17, 5, 7);
	_txtBuild = new Text(310, 9, 5, isMobile ? 27 : 23);
	_txtModName = new Text(115, 9, 16, isMobile ? 40 : 32);
	_txtModRequired = new Text(50, 9, 154, isMobile ? 40 : 32);
	_lstMods = new TextList(298, isMobile ? 96 : 104, 8, isMobile ? 50 : 42);

	_sortModName = new ArrowButton(ARROW_NONE, 11, 8, 16, isMobile ? 40 : 32);
	_sortModRequired = new ArrowButton(ARROW_NONE, 11, 8, 154, isMobile ? 40 : 32);

	// Set palette
	setInterface("geoscape", true, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	add(_window, "window", "saveMenus");
	add(_btnCancel, "button", "saveMenus");
	add(_txtTitle, "text", "saveMenus");
	add(_txtBuild, "text", "saveMenus");
	add(_txtModName, "text", "saveMenus");
	add(_txtModRequired, "text", "saveMenus");
	add(_lstMods, "list", "saveMenus");
	add(_sortModName, "text", "saveMenus");
	add(_sortModRequired, "text", "saveMenus");

	// Set up objects
	setWindowBackground(_window, "saveMenus");

	Uint8 color = 239; // 239 or 255

	if (_game->getSavedGame())
	{
		if (_game->getSavedGame()->getSavedBattle())
		{
			color = 255;
		}
	}

	_btnCancel->setText(tr("STR_CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&ModCheckMenu::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&ModCheckMenu::btnCancelClick, Options::keyCancel);

	_txtTitle->setBig();
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setText("INCOMPATIBLE MODS");

	// another build: name both (a host that reports none shows "unknown")
	_txtBuild->setAlign(ALIGN_CENTER);
	const std::string localVersion = getReportedGameVersion();
	if (showBuild && hostVersion != localVersion)
	{
		_txtBuild->setText("Host build " + (hostVersion.empty() ? std::string("unknown") : hostVersion)
			+ ", your build " + localVersion + ".");
	}

	_txtModName->setText("Mod Name");
	_txtModRequired->setText("Status");

	_lstMods->setColumns(2, 139, 159); 
	_lstMods->setSelectable(true);
	_lstMods->setBackground(_window);
	_lstMods->setMargin(8);

	_sortModName->setX(_sortModName->getX() + _txtModName->getTextWidth() + 5);
	_sortModName->onMouseClick((ActionHandler)&ModCheckMenu::sortModNameClick);

	_sortModRequired->setX(_sortModRequired->getX() + _txtModRequired->getTextWidth() + 5);
	_sortModRequired->onMouseClick((ActionHandler)&ModCheckMenu::sortModRequiredClick);

	updateArrows();

	updateModList();

}

/**
 *
 */
ModCheckMenu::~ModCheckMenu()
{

}

/**
 * Refreshes the saves list.
 */
void ModCheckMenu::init()
{
	State::init();

	updateModList();
	
	_origin = OPT_MENU;

	if (_game->getSavedGame())
	{
		if (_game->getSavedGame()->getSavedBattle())
		{
			_origin = OPT_BATTLESCAPE;
		}
	}

	if (_origin == OPT_BATTLESCAPE)
	{
		applyBattlescapeTheme("saveMenus");
	}

}

/**
 * Updates the sorting arrows based
 * on the current setting.
 */
void ModCheckMenu::updateArrows()
{
	_sortModName->setShape(ARROW_NONE);
	_sortModRequired->setShape(ARROW_NONE);
	switch (Options::modOrder)
	{
	case SORT_NAME_MOD_ASC:
		_sortModName->setShape(ARROW_SMALL_UP);
		break;
	case SORT_NAME_MOD_DESC:
		_sortModName->setShape(ARROW_SMALL_DOWN);
		break;
	case SORT_REQUIRED_MOD_ASC:
		_sortModRequired->setShape(ARROW_SMALL_UP);
		break;
	case SORT_REQUIRED_MOD_DESC:
		_sortModRequired->setShape(ARROW_SMALL_DOWN);
		break;
	}
}

void ModCheckMenu::updateModList()
{
	_mods.clear();

	// a mod's name as the list shows it
	auto shown = [](const std::string& id)
	{
		if (id == "xcom1")
			return std::string("xcom1 (UFO Defense)");
		if (id == "xcom2")
			return std::string("xcom2 (Terror from the Deep)");
		return id;
	};

	// Local mods, each (id, version) in load order
	const std::vector<std::pair<std::string, std::string>> local = getReportedMods(_game->getMod()->getCoopModList());

	if (_modHash != "")
	{
		// Required mods from the host/server, each (id, version) in load order
		const std::vector<std::pair<std::string, std::string>> host = parseCoopModList(_modHash);

		auto findIn = [](const std::vector<std::pair<std::string, std::string>>& list, const std::string& id)
		{
			return std::find_if(list.begin(), list.end(),
				[&id](const std::pair<std::string, std::string>& m) { return m.first == id; });
		};

		// the mods both games load, each in its game's load order: a mod whose
		// place differs between the two is loaded out of the host's order
		std::vector<std::string> hostOrder, localOrder;
		for (const auto& mod : host)
		{
			if (findIn(local, mod.first) != local.end())
				hostOrder.push_back(mod.first);
		}
		for (const auto& mod : local)
		{
			if (findIn(host, mod.first) != host.end())
				localOrder.push_back(mod.first);
		}
		auto place = [](const std::vector<std::string>& order, const std::string& id)
		{
			return std::find(order.begin(), order.end(), id) - order.begin();
		};

		// every host mod: missing here, at another version, out of order, or enabled
		for (const auto& mod : host)
		{
			if (mod.first.empty())
				continue;

			auto here = findIn(local, mod.first);
			std::string status;
			if (here == local.end())
			{
				status = "Required mod not enabled.";
			}
			else if (!mod.second.empty() && mod.second != here->second)
			{
				status = "Different version (host " + mod.second + ").";
			}
			else if (place(hostOrder, mod.first) != place(localOrder, mod.first))
			{
				status = "Different load order.";
			}
			else
			{
				status = "This mod is enabled.";
			}
			_mods.push_back(ModInfoCoop({shown(mod.first), status}));
		}

		// Check if local player has any extra mods
		for (const auto& mod : local)
		{
			if (mod.first.empty())
				continue;

			if (findIn(host, mod.first) == host.end())
			{
				_mods.push_back(ModInfoCoop({shown(mod.first), "Disable extra mod."}));
			}
		}
	}

	_lstMods->clearList();
	sortList(Options::modOrder);

}

/**
 * Sorts the save game list.
 * @param sort Order to sort the games in.
 */
void ModCheckMenu::sortList(modSort sort)
{
	switch (sort)
	{
	case SORT_NAME_MOD_ASC:
		std::sort(_mods.begin(), _mods.end(), compareModName(false));
		break;
	case SORT_NAME_MOD_DESC:
		std::sort(_mods.rbegin(), _mods.rend(), compareModName(true));
		break;
	case SORT_REQUIRED_MOD_ASC:
		std::sort(_mods.begin(), _mods.end(), compareModRequired(false));
		break;
	case SORT_REQUIRED_MOD_DESC:
		std::sort(_mods.rbegin(), _mods.rend(), compareModRequired(true));
		break;
	}
	updateList();
}

/**
 * Updates the save game list with the current list
 * of available savegames.
 */
void ModCheckMenu::updateList()
{
	int row = 0;
	int color = _lstMods->getSecondaryColor();
	for (const auto& serverInfo : _mods)
	{

		std::string name = serverInfo.modName; 
		std::string required = serverInfo.modRequired;
		_lstMods->addRow(2, name.c_str(), required.c_str());
		if (serverInfo.reserved && _origin != OPT_BATTLESCAPE)
		{
			_lstMods->setRowColor(row, color);
		}
		row++;
	}
}

/**
 * Returns to the previous screen.
 * @param action Pointer to an action.
 */
void ModCheckMenu::btnCancelClick(Action*)
{
	_game->popState();
}

/**
 * Sorts the saves by name.
 * @param action Pointer to an action.
 */
void ModCheckMenu::sortModNameClick(Action*)
{
	if (_sortable)
	{
		if (Options::modOrder == SORT_NAME_MOD_ASC)
		{
			Options::modOrder = SORT_NAME_MOD_DESC;
		}
		else
		{
			Options::modOrder = SORT_NAME_MOD_ASC;
		}
		updateArrows();
		_lstMods->clearList();
		sortList(Options::modOrder);
	}
}

/**
 * Sorts the saves by date.
 * @param action Pointer to an action.
 */
void ModCheckMenu::sortModRequiredClick(Action*)
{
	if (_sortable)
	{
		if (Options::modOrder == SORT_REQUIRED_MOD_ASC)
		{
			Options::modOrder = SORT_REQUIRED_MOD_DESC;
		}
		else
		{
			Options::modOrder = SORT_REQUIRED_MOD_ASC;
		}
		updateArrows();
		_lstMods->clearList();
		sortList(Options::modOrder);
	}
}

void ModCheckMenu::disableSort()
{
	_sortable = false;
}

std::string ModCheckMenu::getTitle() const
{
	return _txtTitle->getText();
}

std::string ModCheckMenu::getBuildLine() const
{
	return _txtBuild->getText();
}

}
