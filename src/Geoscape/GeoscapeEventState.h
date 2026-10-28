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

/// coop: the picks behind an event window (region id, city index, (itemRuleId, qty) rows, research ids).
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
	/// coop: the rule names of the research topic and getOneFree bonus eventLogic learned ("" = none); the host sends them with certain_event_fire
	std::string _coopPickResearch, _coopPickBonus;
	const RuleEvent &_eventRule;
	/// coop: the region id, city index and item rows eventLogic picked (recorded, never read by vanilla).
	std::string _coopRegion;
	int _coopCity = -1;
	std::vector<std::pair<std::string, int> > _coopRows;
	/// coop: the picks the next window draws instead of running eventLogic (armed on a SHARED replica only).
	static const CoopEventPicks* _coopArmed;
	/// coop: the host's (research, bonus) rule names the next SEPARATE paired window learns instead of rolling its own
	static const std::pair<std::string, std::string>* _coopHostPick;
	/// coop: copies the armed picks and draws them in this machine's language; true = the replica path.
	bool coopReplicaDisplay();
	bool _coopShared; // coop SEPARATE: the other player gets this same event too
	bool _coopBothWorlds; // coop: SEPARATE, shared research - the other player's world holds this same event (main #197)

	/// Helper performing event logic.
	void eventLogic();
public:
	/// Creates the GeoscapeEventState.
	GeoscapeEventState(const RuleEvent& eventRule, bool coopShared = false, bool coopBothWorlds = false);
	/// Cleans up the GeoscapeEventState.
	~GeoscapeEventState();
	/// Initializes the state.
	void init() override;
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the ItemsArriving button.
	void btnItemsArrivingClick(Action *action);
	/// coop: the picks this window was built from.
	CoopEventPicks coopPicks() const;
	/// coop, probe only: title, message, then each row's two cells, as drawn.
	std::vector<std::string> coopTexts() const;
	/// coop: the rule names of the research topic and bonus this window learned ("" = none).
	std::pair<std::string, std::string> coopResearchPick() const { return { _coopPickResearch, _coopPickBonus }; }
	/// coop: arms the next window of a SEPARATE paired event (the client's copy) with the host's pick; nullptr disarms.
	static void coopArmHostPick(const std::pair<std::string, std::string>* pick);
	/// coop: arms the next GeoscapeEventState as a display-only replica window drawn from @a picks.
	static void coopArmDisplay(const CoopEventPicks* picks);
	/// coop: SEPARATE co-op with shared research - marks every geoscape event spawned since index @a from as one both
	/// worlds hold (the other player's world spawns it too). @a senderSideEffects false: the sender's world spawned nothing (a mission outcome).
	static void coopMarkResearchEvents(Game* game, size_t from, bool senderSideEffects = true);
};

}
