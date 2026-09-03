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

#include "UnitTurnBState.h"
#include "TileEngine.h"
#include "Map.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Mod/Mod.h"
#include "../Engine/Sound.h"
#include "../Engine/Options.h"
#include "../CoopMod/CoopArbiter.h"
#include "../CoopMod/CoopDoor.h"

namespace OpenXcom
{

/**
 * Sets up an UnitTurnBState.
 * @param parent Pointer to the Battlescape.
 * @param action Pointer to an action.
 */
UnitTurnBState::UnitTurnBState(BattlescapeGame *parent, BattleAction action, bool chargeTUs) : BattleState(parent, action), _unit(0), _turret(false), _chargeTUs(chargeTUs)
{

}

/**
 * Deletes the UnitTurnBState.
 */
UnitTurnBState::~UnitTurnBState()
{

}

/**
 * Initializes the state.
 */
void UnitTurnBState::init()
{
	_unit = _action.actor;
	if (_unit->isOut())
	{
		_parent->popState();
		return;
	}
	_action.clearTU();
	if (_unit->getFaction() == FACTION_PLAYER)
		_parent->setStateInterval(Options::battleXcomSpeed);
	else
		_parent->setStateInterval(Options::battleAlienSpeed);

	// if the unit has a turret and we are turning during targeting, then only the turret turns
	_turret = _unit->getTurretType() != -1 && (_action.targeting || _action.strafe);

	_unit->lookAt(_action.target, _turret);

	if (_chargeTUs && _unit->getStatus() != STATUS_TURNING)
	{
		if (_action.type == BA_NONE)
		{
			// try to open a door
			// W1-P10 (SS4 "ATOM door"): ONE guarded coop call REPLACING the
			// `unitOpensDoor(...)` sub-expression - THE right-click door path
			// SS2.4 reserved a `door` field on the turn ev for and never
			// applied ("RW-UNSUPPORTED door-in-turn"). The terrain now rides
			// its own `ev door` from inside here, so that fallback is retired
			// for this path (CoopDoor.h). Vanilla's own default `dir` for this
			// call is -1 ("use the unit's facing", TileEngine.cpp:4095).
			int door = coopUnitOpensDoor(_parent->getTileEngine(), _unit, true, -1);
			if (door == 0)
			{
				_parent->getMod()->getSoundByDepth(_parent->getDepth(), Mod::DOOR_OPEN)->play(-1, _parent->getMap()->getSoundAngle(_unit->getPosition())); // normal door
			}
			if (door == 1)
			{
				_parent->getMod()->getSoundByDepth(_parent->getDepth(), Mod::SLIDING_DOOR_OPEN)->play(-1, _parent->getMap()->getSoundAngle(_unit->getPosition())); // ufo door
			}
			if (door == 4)
			{
				_action.result = "STR_NOT_ENOUGH_TIME_UNITS";
			}
		}
		_parent->popState();
	}
}

/**
 * Runs state functionality every cycle.
 */
void UnitTurnBState::think()
{
	const int tu = _chargeTUs ? (_turret ? 1 :_unit->getTurnCost()) : 0;

	if (_chargeTUs && _unit->getFaction() == _parent->getSave()->getSide() && _parent->getPanicHandled() && !_action.targeting && !_parent->checkReservedTU(_unit, tu, 0))
	{
		_unit->abortTurn();
		// R3-P1 (SPIKE-RUNBOOK.md UnitTurnBState.cpp:104 @911ca487f): THIN
		// completion/abort hook - see CoopArbiter.h's coopOnUnitTurnFinished()
		// doc comment for the full contract. No-op outside an active coop
		// battle / a foreign unit's turn.
		coopOnUnitTurnFinished(_unit, true);
		_parent->popState();
		return;
	}

	if (_unit->spendTimeUnits(tu))
	{
		size_t unitSpotted = _unit->getUnitsSpottedThisTurn().size();
		_unit->turn(_turret);
		_parent->getTileEngine()->calculateFOV(_unit);
		if (_chargeTUs && _unit->getFaction() == _parent->getSave()->getSide() && _parent->getPanicHandled() && _action.type == BA_NONE && _unit->getUnitsSpottedThisTurn().size() > unitSpotted)
		{
			_unit->abortTurn();
			// R3-P1 (UnitTurnBState.cpp:116 @911ca487f): see the :104 hook above.
			coopOnUnitTurnFinished(_unit, true);
			_parent->popState();
		}
		else if (_unit->getStatus() == STATUS_STANDING)
		{
			// R3-P1 (UnitTurnBState.cpp:116 @911ca487f, natural completion
			// branch): ONE ev at completion, never per 45-degree tick - this
			// branch only executes once the FULL rotation has finished
			// (getStatus() != STATUS_TURNING on every intermediate tick).
			coopOnUnitTurnFinished(_unit, false);
			_parent->popState();

			if (_action.kneel && !_unit->isFloating() && !_unit->isKneeled())
			{
				BattleAction kneel;
				kneel.type = BA_KNEEL;
				kneel.actor = _unit;
				kneel.Time = _unit->getKneelChangeCost();
				if (kneel.spendTU())
				{
					_unit->kneel(!_unit->isKneeled());
					// kneeling or standing up can reveal new terrain or units. I guess.
					_parent->getTileEngine()->calculateFOV(_unit->getPosition(), 1, false); //Update unit FOV for everyone through this position, skip tiles.
					_parent->getTileEngine()->checkReactionFire(_unit, kneel);
				}
			}
		}
	}
	else if (_parent->getPanicHandled())
	{
		_action.result = "STR_NOT_ENOUGH_TIME_UNITS";
		_unit->abortTurn();
		// R3-P1 (UnitTurnBState.cpp:142 @911ca487f): see the :104 hook above.
		coopOnUnitTurnFinished(_unit, true);
		_parent->popState();
	}
}

/**
 * Unit turning cannot be cancelled.
 */
void UnitTurnBState::cancel()
{
}

}
