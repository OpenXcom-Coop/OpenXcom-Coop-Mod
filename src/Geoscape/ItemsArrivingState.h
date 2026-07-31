#pragma once
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
#include "../Engine/State.h"
#include <vector>
#include <string>

namespace OpenXcom
{

class TextButton;
class Window;
class Text;
class TextList;
class GeoscapeState;
class Base;

struct ArrivalRow
{
	int type;
	std::string name;
	int qty;
	std::string base;
	int baseIdx;
	int ownerSeat;
};

/**
 * Items Arriving window that displays all
 * the items that have arrived at bases.
 */
class ItemsArrivingState : public State
{
private:
	GeoscapeState *_state;
	Base *_base;
	TextButton *_btnOk, *_btnGotoBase;
	Window *_window;
	Text *_txtTitle, *_txtItem, *_txtQuantity, *_txtDestination;
	TextList *_lstTransfers;
	std::vector<ArrivalRow> _rows;
	/// Builds the shared window widgets.
	void buildUI();
public:
	/// Creates the ItemsArriving state.
	ItemsArrivingState(GeoscapeState *state);
	/// Creates the ItemsArriving state from a network-supplied row list.
	ItemsArrivingState(GeoscapeState *state, const std::vector<ArrivalRow>& rows);
	/// Cleans up the ItemsArriving state.
	~ItemsArrivingState();
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the Go To Base button.
	void btnGotoBaseClick(Action *action);
	/// Test automation: fire the real "Go to Base" path (issue repro: a replica's
	/// hostAlert-raised popup has a null _base).
	void harnessGotoBase();
	/// Gets the arrival rows backing this popup.
	const std::vector<ArrivalRow>& getRows() const { return _rows; }
	/// Test automation: the formatted first-column labels.
	std::vector<std::string> harnessRows() const;
};

}
