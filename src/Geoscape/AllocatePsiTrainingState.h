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
#include "../CoopMod/SharedEcon.h"
#include <set>
#include <vector>

namespace OpenXcom
{

class TextButton;
class ToggleTextButton;
class Window;
class Text;
class Base;
class TextList;
class ComboBox;
class Soldier;
struct SortFunctor;

/**
 * Screen shown monthly to allow changing
 * soldiers currently in psi training.
 */
class AllocatePsiTrainingState : public State
{
private:
	TextButton *_btnOk;
	ToggleTextButton *_btnPlus;
	Window *_window;
	Text *_txtTitle, *_txtTraining, *_txtName, *_txtRemaining;
	Text *_txtPsiStrength, *_txtPsiSkill;
	ComboBox *_cbxSortBy;
	TextList *_lstSoldiers;
	std::vector<Soldier*> _soldiers;
	size_t _sel;
	int _labSpace;
	Base *_base;
	std::vector<Soldier *> _origSoldierOrder;
	std::vector<SortFunctor *> _sortFunctors;
	std::vector<SortFunctor *> _sortFunctorsPlus;
	bool _doNotReset;
	/// One-world co-op campaigns (SHARED, Separate): the screen sorts and moves
	/// its own copy of the roster, never the host-owned roster order itself.
	bool _coopView;
	std::vector<Soldier*> _shown;
	/// The soldiers the list shows, in its order.
	std::vector<Soldier*>* shown();
	/// Drops soldiers who left the base from the shown copy and appends arrivals.
	void syncShown();
	/// The base roster index of shown row @a row.
	size_t rosterIndex(size_t row);
	/// Assigns / removes the soldier of shown row @a row (a left click).
	void toggleRow(size_t row);
	/// One-world co-op campaigns: the host runs the training, so the screen
	/// sends its changes there and redraws when they land.
	SharedEcon::ScreenRefresh _sharedRefresh;
	std::vector<SharedEcon::TrainingChange> _pending;
	/// Soldiers the list already asked the host to take out of psi training
	/// (they cannot train), so a refused request is not sent again.
	std::set<int> _clearSent;
	/// Sets @a soldier's psi training flag here and returns true; in a one-world
	/// co-op campaign adds it to the change for the host and returns false.
	bool changePsiTraining(Soldier* soldier, bool training);
	/// Sends the pending changes to the host.
	void sendTraining();
	/// Assign-all, de-assign-all and the list's clean-up change this soldier
	/// (Separate: own soldiers).
	bool mayChange(const Soldier* soldier) const;
	/// Recounts the free psi lab space from the base.
	void refreshSpace();

	///initializes the display list based on the craft soldier's list and the position to display
	void initList(size_t scrl);
public:
	/// Creates the Psi Training state.
	AllocatePsiTrainingState(Base *base);
	/// Cleans up the Psi Training state.
	~AllocatePsiTrainingState();
	/// Handler for changing the sort by combobox.
	void cbxSortByChange(Action *action);
	/// Updates the soldier info.
	void init() override;
	/// Redraws the list when a host result for this base lands.
	void think() override;
	/// Handler for clicking the Soldiers reordering button.
	void lstItemsLeftArrowClick(Action *action);
	/// Moves a soldier up.
	void moveSoldierUp(Action *action, unsigned int row, bool max = false);
	/// Handler for clicking the Soldiers reordering button.
	void lstItemsRightArrowClick(Action *action);
	/// Moves a soldier down.
	void moveSoldierDown(Action *action, unsigned int row, bool max = false);
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the PLUS button.
	void btnPlusClick(Action *action);
	/// Handler for clicking the Soldiers list.
	void lstSoldiersClick(Action *action);
	/// Handler for pressing-down a mouse-button in the list.
	void lstSoldiersMousePress(Action *action);
	/// Handler for clicking the De-assign All Soldiers button.
	void btnDeassignAllSoldiersClick(Action* action);
	/// Handler for clicking the Assign All Soldiers button.
	void btnAssignAllSoldiersClick(Action* action);
	/// Test automation: picks sort option @a index through the real handler.
	void harnessSort(size_t index);
	/// Test automation: the soldier ids the list shows, in its order.
	std::vector<int> harnessDisplayedSoldierIds() const;
	/// Test automation: "toggle" clicks soldier @a soldierId's row, "assign_all" /
	/// "deassign_all" press those keys. False for an unknown action or soldier.
	bool harnessTraining(const std::string& action, int soldierId);
};

}
