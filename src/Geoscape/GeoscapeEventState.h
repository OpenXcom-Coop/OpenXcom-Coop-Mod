#pragma once
/*
 * Copyright 2010-2019 OpenXcom Developers.
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
#include <map>
#include "../Engine/State.h"

namespace OpenXcom
{

class TextButton;
class TextList;
class ToggleTextButton;
class Window;
class Text;
class RuleEvent;

/// coop W2-H15 (F3261): the picks behind an event window (region id, city index, (itemRuleId, qty) rows, research ids).
struct CoopEventPicks { std::string region; int city = -1; std::vector<std::pair<std::string, int> > rows; std::string research, bonus; };

/**
 * Displays info about a custom Geoscape event.
 */
class GeoscapeEventState : public State
{
private:
	Window *_window;
	Text *_txtTitle, *_txtMessage;
	Text *_txtItem, *_txtQuantity;
	TextButton *_btnOk;
	ToggleTextButton *_btnItemsArriving;
	TextList *_lstTransfers;

	std::map<std::string, int> _itemsRemoved;
	std::string _researchName;
	std::string _bonusResearchName;
	const RuleEvent &_eventRule;
	/// coop W2-H15 (F3261): the region id, city index and item rows eventLogic picked (recorded, never read by vanilla).
	std::string _coopRegion;
	int _coopCity = -1;
	std::vector<std::pair<std::string, int> > _coopRows;

	/// Helper performing event logic.
	void eventLogic();
public:
	/// Creates the GeoscapeEventState.
	GeoscapeEventState(const RuleEvent& eventRule);
	/// Cleans up the GeoscapeEventState.
	~GeoscapeEventState();
	/// Initializes the state.
	void init() override;
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the ItemsArriving button.
	void btnItemsArrivingClick(Action *action);
	/// coop W2-H15 (F3261): the picks this window was built from.
	CoopEventPicks coopPicks() const;
	/// coop W2-H15 (F3261), probe only: title, message, then each row's two cells, as drawn.
	std::vector<std::string> coopTexts() const;
};

}
