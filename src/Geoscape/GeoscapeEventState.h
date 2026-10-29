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
#include <utility>
#include <vector>
#include "../Engine/State.h"

namespace OpenXcom
{

class TextButton;
class TextList;
class ToggleTextButton;
class Window;
class Text;
class RuleEvent;

/// What an event window showed on the authoritative host: the place its text
/// names and its item rows (item type, quantity). A replica only displays it.
struct GeoscapeEventDisplay
{
	std::string place;
	std::vector<std::pair<std::string, std::string> > rows;
	/// Separate host: what eventLogic gave or took at the owner's bases (stores,
	/// craft items, transfers, crafts) as JSON text, for the replica to apply.
	std::string rewards;
};

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
	bool _coopShared; // coop SEPARATE: the other player gets this same event too
	GeoscapeEventDisplay _display;

	/// Helper performing event logic.
	void eventLogic();
	/// Adds one item row to the window and to the replicated display.
	void addTransferRow(const std::string& itemType, const std::string& quantity);
public:
	/// Creates the GeoscapeEventState. With @a replicated the window only shows
	/// the host's result and never runs the event logic (no world change).
	GeoscapeEventState(const RuleEvent& eventRule,
		const std::string& ownerPlayerName = std::string(), bool coopShared = false,
		const GeoscapeEventDisplay* replicated = nullptr);
	/// Cleans up the GeoscapeEventState.
	~GeoscapeEventState();
	/// Initializes the state.
	void init() override;
	const std::string& getResearchName() const { return _researchName; }
	const std::string& getBonusResearchName() const { return _bonusResearchName; }
	/// The place and item rows this window shows (host side, for replicas).
	const GeoscapeEventDisplay& getDisplay() const { return _display; }
	/// Use the authoritative host's resolved event rewards on a Separate replica.
	void setReplicatedResearchNames(const std::string& research,
		const std::string& bonus) { _researchName = research; _bonusResearchName = bonus; _replicatedResearchNames = true; }
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the ItemsArriving button.
	void btnItemsArrivingClick(Action *action);
};

}
