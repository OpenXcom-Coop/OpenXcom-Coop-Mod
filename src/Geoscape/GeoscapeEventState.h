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
#include <string>
#include "../Engine/State.h"

namespace OpenXcom
{

class TextButton;
class TextList;
class ToggleTextButton;
class Window;
class Text;
class RuleEvent;

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
	bool _replicatedResearchNames = false;
	std::string _ownerPlayerName;
	const RuleEvent &_eventRule;

	/// Helper performing event logic.
	void eventLogic();
public:
	/// Creates the GeoscapeEventState.
	GeoscapeEventState(const RuleEvent& eventRule,
		const std::string& ownerPlayerName = std::string());
	/// Cleans up the GeoscapeEventState.
	~GeoscapeEventState();
	/// Initializes the state.
	void init() override;
	const std::string& getResearchName() const { return _researchName; }
	const std::string& getBonusResearchName() const { return _bonusResearchName; }
	/// Use the authoritative host's resolved event rewards on a Separate replica.
	void setReplicatedResearchNames(const std::string& research,
		const std::string& bonus) { _researchName = research; _bonusResearchName = bonus; _replicatedResearchNames = true; }
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the ItemsArriving button.
	void btnItemsArrivingClick(Action *action);
};

}
