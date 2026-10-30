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
#include <sstream>
#include <climits>
#include "PsiTrainingState.h"
#include "AllocatePsiTrainingState.h"
#include "../Engine/Game.h"
#include "../Mod/Mod.h"
#include "../Engine/LocalizedText.h"
#include "../Interface/TextButton.h"
#include "../Interface/ToggleTextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Base.h"
#include "../Interface/TextList.h"
#include "../Savegame/Soldier.h"
#include "../Engine/Action.h"
#include "../Engine/Options.h"
#include "../Interface/ComboBox.h"
#include "../Mod/RuleSoldier.h"
#include "../Basescape/SoldierInfoState.h"
#include "../Basescape/SoldierSortUtil.h"
#include <algorithm>
#include "../Engine/Unicode.h"
#include "../CoopMod/SharedEcon.h" // coop
#include "../CoopMod/connectionTCP.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the Psi Training screen.
 * @param game Pointer to the core game.
 * @param base Pointer to the base to handle.
 */
AllocatePsiTrainingState::AllocatePsiTrainingState(Base *base) : _sel(0), _base(base), _origSoldierOrder(*_base->getSoldiers()), _doNotReset(false),
	_coopView(_game->getCoopMod()->isSharedCampaign() || _game->getCoopMod()->isSeparateCampaign()),
	_shown(*_base->getSoldiers())
{
	// Create objects
	_window = new Window(this, 320, 200, 0, 0);
	_txtTitle = new Text(300, 17, 10, 8);
	_txtRemaining = new Text(300, 10, 10, 24);
	_txtName = new Text(64, 10, 10, 40);
	_txtPsiStrength = new Text(80, 20, 124, 32);
	_txtPsiSkill = new Text(80, 20, 188, 32);
	_txtTraining = new Text(48, 20, 270, 32);
	_btnOk = new TextButton(148, 16, 164, 176);
	_lstSoldiers = new TextList(290, 112, 8, 52);
	_cbxSortBy = new ComboBox(this, 148, 16, 8, 176, true);
	_btnPlus = new ToggleTextButton(18, 16, 294, 8);

	// Set palette
	setInterface("allocatePsi");

	add(_window, "window", "allocatePsi");
	add(_btnOk, "button", "allocatePsi");
	add(_txtName, "text", "allocatePsi");
	add(_txtTitle, "text", "allocatePsi");
	add(_txtRemaining, "text", "allocatePsi");
	add(_txtPsiStrength, "text", "allocatePsi");
	add(_txtPsiSkill, "text", "allocatePsi");
	add(_txtTraining, "text", "allocatePsi");
	add(_lstSoldiers, "list", "allocatePsi");
	add(_cbxSortBy, "button", "allocatePsi");
	add(_btnPlus, "button", "allocatePsi");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "allocatePsi");

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&AllocatePsiTrainingState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&AllocatePsiTrainingState::btnOkClick, Options::keyCancel);
	_btnOk->onKeyboardPress((ActionHandler)&AllocatePsiTrainingState::btnDeassignAllSoldiersClick, Options::keyRemoveSoldiersFromTraining);
	_btnOk->onKeyboardPress((ActionHandler)&AllocatePsiTrainingState::btnAssignAllSoldiersClick, Options::keyAddSoldiersToTraining);

	_btnPlus->setText("+");
	_btnPlus->setPressed(false);
	if (_game->getMod()->getSoldierBonusList().empty())
	{
		// no soldier bonuses in the mod = button not needed
		_btnPlus->setVisible(false);
	}
	else
	{
		_btnPlus->onMouseClick((ActionHandler)&AllocatePsiTrainingState::btnPlusClick, 0);
	}

	_txtTitle->setBig();
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setText(tr("STR_PSIONIC_TRAINING"));

	_labSpace = base->getAvailablePsiLabs() - base->getUsedPsiLabs();
	_txtRemaining->setText(tr("STR_REMAINING_PSI_LAB_CAPACITY").arg(_labSpace));

	_txtName->setText(tr("STR_NAME"));

	_txtPsiStrength->setText(tr("STR_PSIONIC__STRENGTH"));

	_txtPsiSkill->setText(tr("STR_PSIONIC_SKILL_IMPROVEMENT"));

	_txtTraining->setText(tr("STR_IN_TRAINING"));

	// populate sort options
	std::vector<std::string> sortOptions;
	sortOptions.push_back(tr("STR_ORIGINAL_ORDER"));
	_sortFunctors.push_back(NULL);
	_sortFunctorsPlus.push_back(NULL);

#define PUSH_IN(strId, functor) \
	sortOptions.push_back(tr(strId)); \
	_sortFunctors.push_back(new SortFunctor(_game, functor)); \
	_sortFunctorsPlus.push_back(new SortFunctor(_game, functor));

	PUSH_IN("STR_ID", idStat);
	PUSH_IN("STR_NAME_UC", nameStat);
	PUSH_IN("STR_SOLDIER_TYPE", typeStat);
	PUSH_IN("STR_RANK", rankStat);
	PUSH_IN("STR_IDLE_DAYS", idleDaysStat);
	PUSH_IN("STR_MISSIONS2", missionsStat);
	PUSH_IN("STR_KILLS2", killsStat);
	PUSH_IN("STR_WOUND_RECOVERY2", woundRecoveryStat);
	if (_game->getMod()->isManaFeatureEnabled() && !_game->getMod()->getReplenishManaAfterMission())
	{
		PUSH_IN("STR_MANA_MISSING", manaMissingStat);
	}

#undef PUSH_IN

#define PUSH_IN(strId, functor, functorPlus) \
	sortOptions.push_back(tr(strId)); \
	_sortFunctors.push_back(new SortFunctor(_game, functor)); \
	_sortFunctorsPlus.push_back(new SortFunctor(_game, functorPlus));

	PUSH_IN("STR_TIME_UNITS", tuStatBase, tuStatPlus);
	PUSH_IN("STR_STAMINA", staminaStatBase, staminaStatPlus);
	PUSH_IN("STR_HEALTH", healthStatBase, healthStatPlus);
	PUSH_IN("STR_BRAVERY", braveryStatBase, braveryStatPlus);
	PUSH_IN("STR_REACTIONS", reactionsStatBase, reactionsStatPlus);
	PUSH_IN("STR_FIRING_ACCURACY", firingStatBase, firingStatPlus);
	PUSH_IN("STR_THROWING_ACCURACY", throwingStatBase, throwingStatPlus);
	PUSH_IN("STR_MELEE_ACCURACY", meleeStatBase, meleeStatPlus);
	PUSH_IN("STR_STRENGTH", strengthStatBase, strengthStatPlus);
	if (_game->getMod()->isManaFeatureEnabled())
	{
		// "unlock" is checked later
		PUSH_IN("STR_MANA_POOL", manaStatBase, manaStatPlus);
	}
	PUSH_IN("STR_PSIONIC_STRENGTH", psiStrengthStatBase, psiStrengthStatPlus);
	PUSH_IN("STR_PSIONIC_SKILL", psiSkillStatBase, psiSkillStatPlus);

#undef PUSH_IN

	_cbxSortBy->setOptions(sortOptions);
	_cbxSortBy->setSelected(0);
	_cbxSortBy->onChange((ActionHandler)&AllocatePsiTrainingState::cbxSortByChange);
	_cbxSortBy->setText(tr("STR_SORT_BY"));

	_lstSoldiers->setArrowColumn(238, ARROW_VERTICAL);
	_lstSoldiers->setColumns(4, 114, 80, 66, 40);
	_lstSoldiers->setSelectable(true);
	_lstSoldiers->setBackground(_window);
	_lstSoldiers->setMargin(2);
	_lstSoldiers->onLeftArrowClick((ActionHandler)&AllocatePsiTrainingState::lstItemsLeftArrowClick);
	_lstSoldiers->onRightArrowClick((ActionHandler)&AllocatePsiTrainingState::lstItemsRightArrowClick);
	_lstSoldiers->onMouseClick((ActionHandler)&AllocatePsiTrainingState::lstSoldiersClick);
	_lstSoldiers->onMouseClick((ActionHandler)&AllocatePsiTrainingState::lstSoldiersClick, SDL_BUTTON_RIGHT);
	_lstSoldiers->onMousePress((ActionHandler)&AllocatePsiTrainingState::lstSoldiersMousePress);
}
/**
 * cleans up dynamic state
 */
AllocatePsiTrainingState::~AllocatePsiTrainingState()
{
	_sharedRefresh.unbind(this);
	for (auto* sortFunctor : _sortFunctors)
	{
		delete sortFunctor;
	}
}

/**
 * The soldiers the list shows, in its order. In the one-world co-op campaigns
 * (SHARED and Separate) the base roster is the host's, in an order both
 * machines share: the screen sorts and moves its own copy of it, so a sort or
 * a move here never reorders the roster on this machine only. Elsewhere the
 * screen reorders the roster itself, as in vanilla.
 */
std::vector<Soldier*>* AllocatePsiTrainingState::shown()
{
	return _coopView ? &_shown : _base->getSoldiers();
}

/**
 * Keeps the shown copy in step with the roster: a soldier who left the base is
 * dropped, one who arrived is appended in roster order.
 */
void AllocatePsiTrainingState::syncShown()
{
	if (!_coopView) return;
	const std::vector<Soldier*>& roster = *_base->getSoldiers();
	_shown.erase(std::remove_if(_shown.begin(), _shown.end(),
		[&](Soldier* s) { return std::find(roster.begin(), roster.end(), s) == roster.end(); }),
		_shown.end());
	for (Soldier* s : roster)
		if (std::find(_shown.begin(), _shown.end(), s) == _shown.end())
			_shown.push_back(s);
}

/**
 * The base roster index of a shown row (SoldierInfoState pages the roster).
 */
size_t AllocatePsiTrainingState::rosterIndex(size_t row)
{
	const std::vector<Soldier*>& roster = *_base->getSoldiers();
	auto it = std::find(roster.begin(), roster.end(), shown()->at(row));
	return it == roster.end() ? row : (size_t)(it - roster.begin());
}

/**
 * Sorts the soldiers list by the selected criterion
 * @param action Pointer to an action.
 */
void AllocatePsiTrainingState::cbxSortByChange(Action *action)
{
	syncShown();
	size_t selIdx = _cbxSortBy->getSelected();
	if (selIdx == (size_t)-1)
	{
		return;
	}

	// coop (#65 playtest rule): SHARED must not reorder the shared roster (no sort, no restore).
	if (_game->getCoopMod()->isSharedCampaign() && _base->_isForeignBase == false)
	{
		initList(_lstSoldiers->getScroll());
		return;
	}
	SortFunctor *compFunc = _btnPlus->getPressed() ? _sortFunctorsPlus[selIdx] : _sortFunctors[selIdx];
	if (compFunc)
	{
		if (selIdx == 2)
		{
			std::stable_sort(shown()->begin(), shown()->end(),
				[](const Soldier* a, const Soldier* b)
				{
					return Unicode::naturalCompare(a->getName(), b->getName());
				}
			);
		}
		else
		{
			std::stable_sort(shown()->begin(), shown()->end(), *compFunc);
		}
		if (_game->isShiftPressed())
		{
			std::reverse(shown()->begin(), shown()->end());
		}
	}
	else
	{
		// restore original ordering, ignoring (of course) those
		// soldiers that have been sacked since this state started
		for (const auto* origSoldier : _origSoldierOrder)
		{
			auto soldierIt = std::find(shown()->begin(), shown()->end(), origSoldier);
			if (soldierIt != shown()->end())
			{
				Soldier *s = *soldierIt;
				shown()->erase(soldierIt);
				shown()->insert(shown()->end(), s);
			}
		}
	}

	size_t originalScrollPos = _lstSoldiers->getScroll();
	initList(originalScrollPos);
}

/**
 * Returns to the previous screen.
 * @param action Pointer to an action.
 */
void AllocatePsiTrainingState::btnOkClick(Action *)
{
	// Note: statString updates are needed only because of the potential "psiTraining" attribute change
	bool psiStrengthEval = (Options::psiStrengthEval && _game->getSavedGame()->isResearched(_game->getMod()->getPsiRequirements()));
	for (auto* soldier : *_base->getSoldiers())
	{
		soldier->calcStatString(_game->getMod()->getStatStrings(), psiStrengthEval);
	}
	_game->popState();
}

/**
 * Updates the soldier stats. Sorts the list if applicable.
 * @param action Pointer to an action.
 */
void AllocatePsiTrainingState::btnPlusClick(Action *action)
{
	size_t selIdx = _cbxSortBy->getSelected();
	if (selIdx == (size_t)-1)
	{
		size_t originalScrollPos = _lstSoldiers->getScroll();
		initList(originalScrollPos);
	}
	else
	{
		cbxSortByChange(action);
	}
}

/**
 * Updates the soldiers list
 * after going to other screens.
 */
void AllocatePsiTrainingState::init()
{
	State::init();
	_sharedRefresh.bind(_game, this, _base);

	// coming back from SoldierInfoState
	if (_doNotReset)
	{
		_doNotReset = false;
		return;
	}

	if (_coopView) refreshSpace();
	_base->prepareSoldierStatsWithBonuses(); // refresh stats for sorting
	initList(0);
}

/**
 * Redraws the list (and the free space) when a host result for this base
 * lands, e.g. this screen's own training change.
 */
void AllocatePsiTrainingState::think()
{
	State::think();
	if (_sharedRefresh.consume())
	{
		if (SharedEcon::baseIndex(_game, _base) < 0)
		{
			_game->popState(); // this base is gone
			return;
		}
		refreshSpace();
		initList(_lstSoldiers->getScroll());
	}
}

/**
 * Sets a soldier's psi training flag. In the one-world co-op campaigns the
 * host runs the training, so the change goes to the host instead
 * (sendTraining) and the list redraws when it lands.
 * @return True when the flag changed here.
 */
bool AllocatePsiTrainingState::changePsiTraining(Soldier* soldier, bool training)
{
	if (!_coopView)
	{
		soldier->setPsiTraining(training);
		return true;
	}
	if (training != soldier->isInPsiTraining())
		_pending.push_back({ soldier, training, false });
	return false;
}

void AllocatePsiTrainingState::sendTraining()
{
	SharedEcon::submitSoldierTraining(_game, _base, true, _pending);
	_pending.clear();
}

/**
 * Assign-all, de-assign-all and the list's clean-up change only the soldiers
 * the player may train: in Separate their own (the partner's soldiers at the
 * same base are theirs).
 */
bool AllocatePsiTrainingState::mayChange(const Soldier* soldier) const
{
	return !_game->getCoopMod()->isSeparateCampaign() || SharedEcon::ownsSoldier(_game, soldier);
}

void AllocatePsiTrainingState::refreshSpace()
{
	_labSpace = _base->getAvailablePsiLabs() - _base->getUsedPsiLabs();
	_txtRemaining->setText(tr("STR_REMAINING_PSI_LAB_CAPACITY").arg(_labSpace));
}

/**
 * Shows the soldiers in a list at specified offset/scroll.
 */
void AllocatePsiTrainingState::initList(size_t scrl)
{
	syncShown();
	int row = 0;
	_lstSoldiers->clearList();
	for (auto* soldier : *shown())
	{
		if (!SharedEcon::ownsSoldier(_game, soldier)) continue; // coop: SHARED lists only the local player's own soldiers
		const UnitStats* stats = _btnPlus->getPressed() ? soldier->getStatsWithSoldierBonusesOnly() : soldier->getCurrentStats();

		std::ostringstream ssStr;
		std::ostringstream ssSkl;
		_soldiers.push_back(soldier);
		if (soldier->getCurrentStats()->psiSkill > 0 || (Options::psiStrengthEval && _game->getSavedGame()->isResearched(_game->getMod()->getPsiRequirements())))
		{
			ssStr << "   " << stats->psiStrength;
			if (Options::allowPsiStrengthImprovement) ssStr << "/+" << soldier->getPsiStrImprovement();
		}
		else
		{
			ssStr << tr("STR_UNKNOWN");
		}
		if (soldier->getCurrentStats()->psiSkill > 0)
		{
			ssSkl << stats->psiSkill << "/+" << soldier->getImprovement();
		}
		else
		{
			ssSkl << "0/+0";
		}
		if (soldier->getRules()->getTrainingStatCaps().psiSkill <= 0)
		{
			_lstSoldiers->addRow(4, soldier->getName(true).c_str(), ssStr.str().c_str(), ssSkl.str().c_str(), tr("STR_NO_WOUNDED").c_str());
			_lstSoldiers->setRowColor(row, _lstSoldiers->getColor());
			// co-op: asked of the host once per screen, for the player's own soldiers
			if (soldier->isInPsiTraining() && mayChange(soldier)
				&& (!_coopView || _clearSent.insert(soldier->getId()).second)
				&& changePsiTraining(soldier, false))
			{
				_labSpace++;
			}
		}
		else if (soldier->isFullyPsiTrained())
		{
			_lstSoldiers->addRow(4, soldier->getName(true).c_str(), ssStr.str().c_str(), ssSkl.str().c_str(), tr("STR_NO_DONE").c_str());
			_lstSoldiers->setRowColor(row, _lstSoldiers->getColor());
			// co-op: asked of the host once per screen, for the player's own soldiers
			if (soldier->isInPsiTraining() && mayChange(soldier)
				&& (!_coopView || _clearSent.insert(soldier->getId()).second)
				&& changePsiTraining(soldier, false))
			{
				_labSpace++;
			}
		}
		else if (soldier->isInPsiTraining())
		{
			_lstSoldiers->addRow(4, soldier->getName(true).c_str(), ssStr.str().c_str(), ssSkl.str().c_str(), tr("STR_YES").c_str());
			_lstSoldiers->setRowColor(row, _lstSoldiers->getSecondaryColor());
		}
		else
		{
			_lstSoldiers->addRow(4, soldier->getName(true).c_str(), ssStr.str().c_str(), ssSkl.str().c_str(), tr("STR_NO").c_str());
			_lstSoldiers->setRowColor(row, _lstSoldiers->getColor());
		}
		row++;
	}
	sendTraining();
	_txtRemaining->setText(tr("STR_REMAINING_PSI_LAB_CAPACITY").arg(_labSpace));
	if (scrl)
		_lstSoldiers->scrollTo(scrl);
	_lstSoldiers->draw();
}


/**
 * Reorders a soldier up.
 * @param action Pointer to an action.
 */
void AllocatePsiTrainingState::lstItemsLeftArrowClick(Action *action)
{
	syncShown();
	unsigned int row = _lstSoldiers->getSelectedRow();
	if (row > 0)
	{
		if (action->getDetails()->button.button == SDL_BUTTON_LEFT)
		{
			moveSoldierUp(action, row);
		}
		else if (action->getDetails()->button.button == SDL_BUTTON_RIGHT)
		{
			moveSoldierUp(action, row, true);
		}
	}
	_cbxSortBy->setText(tr("STR_SORT_BY"));
	_cbxSortBy->setSelected(-1);
}

/**
 * Moves a soldier up on the list.
 * @param action Pointer to an action.
 * @param row Selected soldier row.
 * @param max Move the soldier to the top?
 */
void AllocatePsiTrainingState::moveSoldierUp(Action *action, unsigned int row, bool max)
{
	syncShown();
	Soldier *s = shown()->at(row);
	if (max)
	{
		shown()->erase(shown()->begin() + row);
		shown()->insert(shown()->begin(), s);
	}
	else
	{
		shown()->at(row) = shown()->at(row - 1);
		shown()->at(row - 1) = s;
		if (row != _lstSoldiers->getScroll())
		{
			SDL_WarpMouse(action->getLeftBlackBand() + action->getXMouse(), action->getTopBlackBand() + action->getYMouse() - static_cast<Uint16>(8 * action->getYScale()));
		}
		else
		{
			_lstSoldiers->scrollUp(false);
		}
	}
	initList(_lstSoldiers->getScroll());
}

/**
 * Reorders a soldier down.
 * @param action Pointer to an action.
 */
void AllocatePsiTrainingState::lstItemsRightArrowClick(Action *action)
{
	syncShown();
	unsigned int row = _lstSoldiers->getSelectedRow();
	size_t numSoldiers = shown()->size();
	if (0 < numSoldiers && INT_MAX >= numSoldiers && row < numSoldiers - 1)
	{
		if (action->getDetails()->button.button == SDL_BUTTON_LEFT)
		{
			moveSoldierDown(action, row);
		}
		else if (action->getDetails()->button.button == SDL_BUTTON_RIGHT)
		{
			moveSoldierDown(action, row, true);
		}
	}
	_cbxSortBy->setText(tr("STR_SORT_BY"));
	_cbxSortBy->setSelected(-1);
}

/**
 * Moves a soldier down on the list.
 * @param action Pointer to an action.
 * @param row Selected soldier row.
 * @param max Move the soldier to the bottom?
 */
void AllocatePsiTrainingState::moveSoldierDown(Action *action, unsigned int row, bool max)
{
	syncShown();
	Soldier *s = shown()->at(row);
	if (max)
	{
		shown()->erase(shown()->begin() + row);
		shown()->insert(shown()->end(), s);
	}
	else
	{
		shown()->at(row) = shown()->at(row + 1);
		shown()->at(row + 1) = s;
		if (row != _lstSoldiers->getVisibleRows() - 1 + _lstSoldiers->getScroll())
		{
			SDL_WarpMouse(action->getLeftBlackBand() + action->getXMouse(), action->getTopBlackBand() + action->getYMouse() + static_cast<Uint16>(8 * action->getYScale()));
		}
		else
		{
			_lstSoldiers->scrollDown(false);
		}
	}
	initList(_lstSoldiers->getScroll());
}

/**
 * Assigns / removes a soldier from Psi Training.
 * @param action Pointer to an action.
 */
void AllocatePsiTrainingState::lstSoldiersClick(Action *action)
{
	syncShown();
	double mx = action->getAbsoluteXMouse();
	if (mx >= _lstSoldiers->getArrowsLeftEdge() && mx < _lstSoldiers->getArrowsRightEdge())
	{
		return;
	}

	_sel = _lstSoldiers->getSelectedRow();
	if (action->getDetails()->button.button == SDL_BUTTON_LEFT)
	{
		toggleRow(_sel);
	}
	else if (action->getDetails()->button.button == SDL_BUTTON_RIGHT)
	{
		_doNotReset = true;
		_game->pushState(new SoldierInfoState(_base, rosterIndex(_sel), true, true));
	}
}

/**
 * Assigns / removes the soldier of a shown row from Psi Training.
 * @param row Shown row.
 */
void AllocatePsiTrainingState::toggleRow(size_t row)
{
	_sel = row;
	auto* s = shown()->at(_sel);
	if (s->getRules()->getTrainingStatCaps().psiSkill <= 0)
	{
		// noop
	}
	else if (s->isFullyPsiTrained())
	{
		// can't put fully psi-trained soldiers back into psi training
	}
	else if (!s->isInPsiTraining())
	{
		if (_base->getUsedPsiLabs() < _base->getAvailablePsiLabs()
			&& changePsiTraining(s, true))
		{
			_lstSoldiers->setCellText(_sel, 3, tr("STR_YES"));
			_lstSoldiers->setRowColor(_sel, _lstSoldiers->getSecondaryColor());
			_labSpace--;
			_txtRemaining->setText(tr("STR_REMAINING_PSI_LAB_CAPACITY").arg(_labSpace));
		}
	}
	else if (changePsiTraining(s, false))
	{
		_lstSoldiers->setCellText(_sel, 3, tr("STR_NO"));
		_lstSoldiers->setRowColor(_sel, _lstSoldiers->getColor());
		_labSpace++;
		_txtRemaining->setText(tr("STR_REMAINING_PSI_LAB_CAPACITY").arg(_labSpace));
	}
	sendTraining();
}

/**
 * Handles the mouse-wheels on the arrow-buttons.
 * @param action Pointer to an action.
 */
void AllocatePsiTrainingState::lstSoldiersMousePress(Action *action)
{
	syncShown();
	if (Options::changeValueByMouseWheel == 0)
		return;
	unsigned int row = _lstSoldiers->getSelectedRow();
	size_t numSoldiers = shown()->size();
	if (action->getDetails()->button.button == SDL_BUTTON_WHEELUP &&
		row > 0)
	{
		if (action->getAbsoluteXMouse() >= _lstSoldiers->getArrowsLeftEdge() &&
			action->getAbsoluteXMouse() <= _lstSoldiers->getArrowsRightEdge())
		{
			moveSoldierUp(action, row);
		}
	}
	else if (action->getDetails()->button.button == SDL_BUTTON_WHEELDOWN &&
		0 < numSoldiers && INT_MAX >= numSoldiers && row < numSoldiers - 1)
	{
		if (action->getAbsoluteXMouse() >= _lstSoldiers->getArrowsLeftEdge() &&
			action->getAbsoluteXMouse() <= _lstSoldiers->getArrowsRightEdge())
		{
			moveSoldierDown(action, row);
		}
	}
}

/**
 * Removes all soldiers from Psi Training.
 * @param action Pointer to an action.
 */
void AllocatePsiTrainingState::btnDeassignAllSoldiersClick(Action* action)
{
	syncShown();
	int row = 0;
	for (auto* s : *shown())
	{
		if (mayChange(s) && changePsiTraining(s, false))
		{
			if (s->getRules()->getTrainingStatCaps().psiSkill <= 0)
			{
				_lstSoldiers->setCellText(row, 3, tr("STR_NO_WOUNDED"));
			}
			else if (s->isFullyPsiTrained())
			{
				_lstSoldiers->setCellText(row, 3, tr("STR_NO_DONE"));
			}
			else
			{
				_lstSoldiers->setCellText(row, 3, tr("STR_NO"));
			}
			_lstSoldiers->setRowColor(row, _lstSoldiers->getColor());
		}
		row++;
	}
	sendTraining();
	refreshSpace();
}

/**
 * Adds all soldiers to Psi Training.
 * @param action Pointer to an action.
 */
void AllocatePsiTrainingState::btnAssignAllSoldiersClick(Action* action)
{
	syncShown();
	int row = 0;
	for (auto* s : *shown())
	{
		if (!mayChange(s))
		{
			// Separate: the partner's soldier at this base is theirs to train
		}
		else if (s->getRules()->getTrainingStatCaps().psiSkill <= 0)
		{
			// noop
		}
		else if (s->isFullyPsiTrained())
		{
			// can't put fully psi-trained soldiers back into psi training
		}
		else if (_labSpace > 0 && !s->isInPsiTraining())
		{
			_labSpace--;
			if (changePsiTraining(s, true))
			{
				_lstSoldiers->setCellText(row, 3, tr("STR_YES"));
				_lstSoldiers->setRowColor(row, _lstSoldiers->getSecondaryColor());
			}
		}
		row++;
	}
	sendTraining();
	_txtRemaining->setText(tr("STR_REMAINING_PSI_LAB_CAPACITY").arg(_labSpace));
}

void AllocatePsiTrainingState::harnessSort(size_t index)
{
	_cbxSortBy->setSelected(index);
	cbxSortByChange(nullptr);
}

std::vector<int> AllocatePsiTrainingState::harnessDisplayedSoldierIds() const
{
	std::vector<int> ids;
	for (const auto* s : _coopView ? _shown : *_base->getSoldiers())
		ids.push_back(s->getId());
	return ids;
}

bool AllocatePsiTrainingState::harnessTraining(const std::string& action, int soldierId)
{
	syncShown();
	if (action == "assign_all") btnAssignAllSoldiersClick(nullptr);
	else if (action == "deassign_all") btnDeassignAllSoldiersClick(nullptr);
	else if (action != "toggle") return false;
	else
	{
		auto it = std::find_if(shown()->begin(), shown()->end(),
			[&](const Soldier* s) { return s->getId() == soldierId; });
		if (it == shown()->end()) return false;
		toggleRow((size_t)(it - shown()->begin()));
	}
	return true;
}

}
