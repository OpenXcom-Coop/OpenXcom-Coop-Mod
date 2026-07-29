#pragma once
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
#include "../Engine/State.h"
#include <string>
#include <utility>
#include <vector>

namespace OpenXcom
{

class BattleUnit;
class Window;
class Text;
class TextButton;
class Soldier;

/**
 * Co-op dialog for transferring a soldier or Custom Battle unit to another
 * player. Shows one button per other player plus Cancel. Opened with the
 * "Give Unit to Teammate" keybind (Options::giveUnit) from the base soldier
 * lists, the soldier stat screen, or the battlescape.
 */
class GiftSoldierMenu : public State
{
private:
	Window *_window;
	Text *_txtTitle;
	std::vector<TextButton*> _btnTargets;
	TextButton *_btnCancel;
	Soldier *_soldier;
	BattleUnit *_battleUnit;
	std::string _unitName;
	// Target player ids matching _btnTargets by index.
	std::vector<int> _targetIds;

	void init(int currentOwnerId);

public:
	/// Creates the dialog for a persistent campaign soldier.
	GiftSoldierMenu(Soldier *soldier, int currentOwnerId);
	/// Creates the same dialog for a Battlescape unit, including Custom Battle.
	GiftSoldierMenu(BattleUnit *battleUnit, int currentOwnerId);
	/// Resolves who currently owns a soldier from its persistent owner id,
	/// falling back to the local co-op seat.
	static int resolveOwnerId(Soldier *soldier);
	void btnGiftClick(Action *action);
	void btnCancelClick(Action *action);

	// Read-only access used by the regression harness.
	bool isBattleUnitGift() const;
	int getBattleUnitId() const;
	const std::vector<int>& getTargetIds() const;
	std::string getTitleText() const;
};

}
