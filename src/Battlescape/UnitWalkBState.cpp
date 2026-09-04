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

#include "UnitWalkBState.h"
#include "MeleeAttackBState.h"
#include "TileEngine.h"
#include "Pathfinding.h"
#include "BattlescapeState.h"
#include "Map.h"
#include "Camera.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"
#include "../Engine/Sound.h"
#include "../Engine/Options.h"
#include "../Engine/Logger.h"
#include "../Mod/Armor.h"
#include "../Mod/Mod.h"
#include "UnitFallBState.h"
#include "../CoopMod/CoopArbiter.h"
#include "../CoopMod/CoopDoor.h"

namespace OpenXcom
{

/**
 * Sets up an UnitWalkBState.
 * @param parent Pointer to the Battlescape.
 * @param action Pointer to an action.
 */
UnitWalkBState::UnitWalkBState(BattlescapeGame *parent, BattleAction action) : BattleState(parent, action), _unit(0), _pf(0), _terrain(0), _beforeFirstStep(false), _numUnitsSpotted(0), _preMovementCost(0)
{

}

/**
 * Deletes the UnitWalkBState.
 */
UnitWalkBState::~UnitWalkBState()
{

}

/**
 * Initializes the state.
 */
void UnitWalkBState::init()
{
	_unit = _action.actor;
	_numUnitsSpotted = _unit->getUnitsSpottedThisTurn().size();
	setNormalWalkSpeed();
	_pf = _parent->getPathfinding();
	_terrain = _parent->getTileEngine();
	_target = _action.target;
	if (Options::traceAI) { Log(LOG_INFO) << "Walking from: " << _unit->getPosition() << "," << " to " << _target;}
	int dir = _pf->getStartDirection();
	if (!_action.strafe && dir != -1 && dir != _unit->getDirection())
	{
		_beforeFirstStep = true;
	}
	_terrain->addMovingUnit(_unit);
}

/**
 * Deinitalize the state.
 */
void UnitWalkBState::deinit()
{
	_terrain->removeMovingUnit(_unit);
}

/**
 * Runs state functionality every cycle.
 */
void UnitWalkBState::think()
{
	if (!_unit->getArmor()->allowsMoving())
	{
		_pf->abortPath();
		_parent->popState();
		return;
	}

	bool unitSpotted = false;
	int size = _unit->getArmor()->getSize() - 1;
	bool onScreen = (_unit->getVisible() && _parent->getMap()->getCamera()->isOnScreen(_unit->getPosition(), true, size, false));
	if (_unit->isKneeled())
	{
		if (_parent->kneel(_unit))
		{
			return;
		}
		else
		{
			if (_parent->getPanicHandled())
			{
				_action.result = "STR_NOT_ENOUGH_TIME_UNITS";
			}
			_pf->abortPath();
			_parent->popState();
			return;
		}
	}


	if (_unit->isOut())
	{
		_pf->abortPath();
		_parent->popState();
		return;
	}

	auto cancelCurentMove = [&]
	{
		// W1-P9 (WAVE1-RUNBOOK.md SS2.W2 / WV-D30): ONE guarded coop call, at THE
		// cancel path every mid-walk abort funnels through. Latches the halt
		// `reason` the completion bt_action_end will carry, mapping vanilla's own
		// `_action.result` classification. First reason wins, so the reserve
		// branch below (and W1-P11's spot halt later) can record ahead of it.
		// No-op outside an active co-op battle, so SP is byte-identical.
		coopNoteWalkHalt(_unit, _action.result);
		if (_fallingWhenStopped && !_falling)
		{
			_falling = true;
		}
		else
		{
			_pf->abortPath();
			_parent->popState();
		}
	};

	if (_unit->getStatus() == STATUS_WALKING || _unit->getStatus() == STATUS_FLYING)
	{
		if ((_parent->getSave()->getTile(_unit->getDestination())->getUnit() == 0) || // next tile must be not occupied
			(_parent->getSave()->getTile(_unit->getDestination())->getUnit() == _unit))
		{
			bool onScreenBoundary = (_unit->getVisible() && _parent->getMap()->getCamera()->isOnScreen(_unit->getPosition(), true, size, true));
			_unit->keepWalking(_parent->getSave(), onScreenBoundary); // advances the phase
			playMovementSound();
			if (_parent->getSave()->isPreview())
			{
				_unit->resetTimeUnitsAndEnergy();
			}
		}
		else if (!_falling)
		{
			_unit->lookAt(_unit->getDestination(), (_unit->getTurretType() != -1));	// turn to undiscovered unit
			_pf->abortPath();
		}

		// unit moved from one tile to the other, update the tiles
		if (_unit->getPosition() != _unit->getLastPosition())
		{
			auto* belowTile = _parent->getSave()->getBelowTile(_unit->getTile());
			_fallingWhenStopped = _unit->haveNoFloorBelow() && _unit->getPosition().z != 0 && _unit->getMovementType() != MT_FLY && _unit->getWalkingPhase() == 0;
			_falling = _fallingWhenStopped && !(
				belowTile && belowTile->hasLadder() && // we do not have any footing but "jump" from ladder to reach ledge
				_unit->getPosition() == _unit->getLastPosition()+Position(0,0,1) && // only vertical move from ladder below
				_pf->getStartDirection() != -1 // move is not canceled, when you cancel "jump" you should fallback to ladder below
			);

			if (_falling)
			{
				for (int x = size; x >= 0; --x)
				{
					for (int y = size; y >= 0; --y)
					{
						Tile *otherTileBelow = _parent->getSave()->getTile(_unit->getPosition() + Position(x,y,-1));
						if (otherTileBelow && otherTileBelow->getUnit())
						{
							_falling = false;
							_fallingWhenStopped = false;
							_pf->dequeuePath();
							_parent->getSave()->addFallingUnit(_unit);
							_parent->statePushFront(new UnitFallBState(_parent));
							return;
						}
					}
				}
			}

			if (!_parent->getMap()->getCamera()->isOnScreen(_unit->getPosition(), true, size, false) && _unit->getFaction() != FACTION_PLAYER && _unit->getVisible())
				_parent->getMap()->getCamera()->centerOnPosition(_unit->getPosition());
			// if the unit changed level, camera changes level with
			_parent->getMap()->getCamera()->setViewLevel(_unit->getPosition().z);
		}

		// is the step finished?
		if (_unit->getStatus() == STATUS_STANDING)
		{
			// W1-P9 (SS2.W2 / WV-D30 / WV-D37): ONE guarded coop call, at the
			// natural per-step hook. Authors the ACTING unit's own tile FOV
			// (SS2.W5 - the updateSoldierInfo() below no longer does the tile
			// half in a co-op battle, and it would recalculate for the SELECTED
			// unit, which an admitted remote walk's actor is not), then emits
			// this step's own `bt_ev walk_step` with h:{unitsStats}. Returns
			// true ONLY for the test-only battle_halt_walk latch, which stops
			// the walk here through vanilla's own cancel path. No-op outside an
			// active co-op battle and off the host sim, so SP is byte-identical.
			if (coopOnWalkStepFinished(_unit))
			{
				return cancelCurentMove();
			}
			// update the TU display
			_parent->getSave()->getBattleState()->updateSoldierInfo();
			// if the unit burns floor tiles, burn floor tiles as long as we're not falling
			if (!_falling && (_unit->getSpecialAbility() == SPECAB_BURNFLOOR || _unit->getSpecialAbility() == SPECAB_BURN_AND_EXPLODE))
			{
				_unit->getTile()->ignite(1);
				Position posHere = _unit->getPosition();
				Position voxelHere = posHere.toVoxel() + Position(8,8,-(_unit->getTile()->getTerrainLevel()));
				_parent->getTileEngine()->hit(BattleActionAttack{ BA_NONE, _unit, }, voxelHere, _unit->getBaseStats()->strength, _parent->getMod()->getDamageType(DT_IN), false);

				if (_unit->getStatus() != STATUS_STANDING) // ie: we burned a hole in the floor and fell through it
				{
					_pf->abortPath();
					return;
				}
			}

			if (_unit->getFaction() != FACTION_PLAYER)
			{
				_unit->setVisible(false);
			}

			int change = _parent->checkForProximityGrenades(_unit);
			// move our personal lighting with us
			_terrain->calculateLighting(change ? LL_ITEMS : LL_UNITS, _unit->getPosition(), 2);
			_terrain->calculateFOV(_unit->getPosition(), 2, false); //update unit visibility for all units which can see last and current position.
			//tile visibility for this unit is handled later.
			unitSpotted = (!_action.ignoreSpottedEnemies && !_falling && !_action.desperate && _parent->getPanicHandled() && _numUnitsSpotted != _unit->getUnitsSpottedThisTurn().size());

			if (change > 1)
			{
				_parent->popState();
				return;
			}
			if (unitSpotted)
			{
				// W1-P11 (WAVE1-RUNBOOK.md SS4 "ATOM spot" / SS2.W2 rule 6,
				// WV-D26): ONE guarded coop call, at vanilla's own MID-WALK
				// spotting halt - the first of the two LIVE sites prd-r3a
				// names. It emits the `spot` ev in-stream at exactly this
				// position (after the step ev this step already emitted, before
				// the walk's completion restate) and latches SS2.W2's halt
				// reason `spot` AHEAD of cancelCurentMove()'s catch-all, which
				// maps this branch's EMPTY `_action.result` to `blocked`.
				// No-op outside an active co-op battle, off the host sim, and
				// for a walk this machine did not open a chain for - so single
				// player is byte-identical.
				coopNoteWalkSpot(_unit);
				return cancelCurentMove();
			}
			// check for reaction fire
			if (!_falling && !_fallingWhenStopped)
			{
				if (_terrain->checkReactionFire(_unit, _action))
				{
					// unit got fired upon - stop walking
					return cancelCurentMove();
				}
			}
		}
		else if (onScreen)
		{
			// make sure the unit sprites are up to date
			if (_pf->getStrafeMove())
			{
				// This is where we fake out the strafe movement direction so the unit "moonwalks"
				int dirTemp = _unit->getDirection();
				_unit->setDirection(_unit->getFaceDirection());
				//TODO fix moonwalk
				_unit->setDirection(dirTemp);
			}
		}
	}

	// we are just standing around, shouldn't we be walking?
	if (_unit->getStatus() == STATUS_STANDING || _unit->getStatus() == STATUS_PANICKING || _unit->getStatus() == STATUS_BERSERK)
	{
		// check if we did spot new units
		if (unitSpotted && !_action.desperate && _unit->getCharging() == 0 && !_falling)
		{
			if (Options::traceAI) { Log(LOG_INFO) << "Uh-oh! Company!"; }
			_unit->setHiding(false); // clearly we're not hidden now
			postPathProcedures();
			return;
		}

		if (onScreen || _parent->getSave()->getDebugMode())
		{
			setNormalWalkSpeed();
		}
		else
		{
			_parent->setStateInterval(0);
		}
		int dir = _pf->getStartDirection();
		if (_falling)
		{
			dir = Pathfinding::DIR_DOWN;
		}

		if (dir != -1)
		{
			if (_pf->getStrafeMove())
			{
				_unit->setFaceDirection(_unit->getDirection());
			}

			_pf->setUnit(_unit); //TODO: remove as was done by `getTUCost`
			PathfindingStep r = _pf->getTUCost(_unit->getPosition(), dir, _unit, 0, _action.getMoveType());

			int tu = r.cost.time;
			int energy = r.cost.energy;
			Position destination = r.pos;

			if (tu == Pathfinding::INVALID_MOVE_COST)
			{
				return cancelCurentMove();
			}

			if (tu > _unit->getTimeUnits())
			{
				if (_parent->getPanicHandled())
				{
					_action.result = "STR_NOT_ENOUGH_TIME_UNITS";
				}
				return cancelCurentMove();
			}

			if (energy > _unit->getEnergy())
			{
				if (_parent->getPanicHandled())
				{
					_action.result = "STR_NOT_ENOUGH_ENERGY";
				}
				return cancelCurentMove();
			}

			// W1-P9 (SS2.W2 / WV-D38 / WV-D48): ONE guarded coop call REPLACING
			// the `_parent->checkReservedTU(_unit, tu, energy) == false`
			// sub-expression. It is the vanilla predicate, with the vanilla
			// arguments and the vanilla warning surface, EXCEPT for a
			// CLIENT-ORIGIN walk in a co-op battle - where the host must not
			// apply ITS OWN (machine-local, saveBlob-excluded) reserve to
			// another seat's order; the ordering client enforces its own before
			// the intent is even built. It also records SS2.W2's `no_tu` halt
			// reason, which this branch's empty `_action.result` cannot carry.
			if (_parent->getPanicHandled() && !_falling
				&& coopWalkReserveRefuses(_parent, _unit, tu, energy))
			{
				return cancelCurentMove();
			}

			// we are looking in the wrong way, turn first (unless strafing)
			// we are not using the turn state, because turning during walking costs no tu
			if (dir != _unit->getDirection() && dir < Pathfinding::DIR_UP && !_pf->getStrafeMove())
			{
				_unit->lookAt(dir);
				return;
			}

			// now open doors (if any)
			if (dir < Pathfinding::DIR_UP)
			{
				// W1-P10 (WAVE1-RUNBOOK.md SS4 "ATOM door" / WV-D26): ONE
				// guarded coop call REPLACING the `_terrain->unitOpensDoor(...)`
				// sub-expression (W1-P9's coopWalkReserveRefuses precedent).
				// Outside a co-op battle, and off the simulating host, it IS
				// that call and nothing else. On the host it emits the SS2.4
				// `ev door` for whatever vanilla actually mutated - which lands
				// in the seq stream exactly HERE, between the walk_step ev of
				// the step before the doorway and the one after it (SS2.W2
				// rule 6). All logic in src/CoopMod (CoopDoor.h).
				int door = coopUnitOpensDoor(_terrain, _unit, false, dir);
				if (door == 3)
				{
					return; // don't start walking yet, wait for the ufo door to open
				}
				if (door == 0)
				{
					_parent->getMod()->getSoundByDepth(_parent->getDepth(), Mod::DOOR_OPEN)->play(-1, _parent->getMap()->getSoundAngle(_unit->getPosition())); // normal door
				}
				if (door == 1)
				{
					_parent->getMod()->getSoundByDepth(_parent->getDepth(), Mod::SLIDING_DOOR_OPEN)->play(-1, _parent->getMap()->getSoundAngle(_unit->getPosition())); // ufo door
					return; // don't start walking yet, wait for the ufo door to open
				}
			}
			for (int x = size; x >= 0; --x)
			{
				for (int y = size; y >= 0; --y)
				{
					BattleUnit* unitInMyWay = _parent->getSave()->getTile(destination + Position(x,y,0))->getOverlappingUnit(_parent->getSave(), TUO_IGNORE_SMALL);  // 2+ voxels poking into the tile above, we don't kick people in the head here at XCom.
					// can't walk into units in this tile, or on top of other units sticking their head into this tile
					if (!_falling && unitInMyWay && unitInMyWay != _unit)
					{
						_action.clearTU();
						return cancelCurentMove();
					}
				}
			}
			// now start moving
			dir = _pf->dequeuePath();
			if (_falling)
			{
				dir = Pathfinding::DIR_DOWN;
			}

			if (_unit->spendTimeUnits(tu))
			{
				if (_unit->spendEnergy(energy))
				{
					_unit->startWalking(dir, destination, _parent->getSave());
					_beforeFirstStep = false;
				}
			}
			// make sure the unit sprites are up to date
			if (onScreen)
			{
				if (_pf->getStrafeMove())
				{
					// This is where we fake out the strafe movement direction so the unit "moonwalks"
					int dirTemp = _unit->getDirection();
					_unit->setDirection(_unit->getFaceDirection());
					_unit->setDirection(dirTemp);
				}
			}
		}
		else
		{
			postPathProcedures();
			return;
		}
	}

	// turning during walking costs no tu
	if (_unit->getStatus() == STATUS_TURNING)
	{
		// except before the first step.
		if (_beforeFirstStep)
		{
			if (_unit->getArmor()->getTurnBeforeFirstStep())
			{
				_unit->spendTimeUnits(_unit->getTurnCost());
			}
			else
			{
				_preMovementCost++;
			}
		}

		_unit->turn();

		// calculateFOV is unreliable for setting the unitSpotted bool, as it can be called from various other places
		// in the code, ie: doors opening, and this messes up the result.
		_terrain->calculateFOV(_unit);
		unitSpotted = (!_action.ignoreSpottedEnemies && !_falling && !_action.desperate && _parent->getPanicHandled() && _numUnitsSpotted != _unit->getUnitsSpottedThisTurn().size());

		if (unitSpotted && !_action.desperate && !_unit->getCharging() && !_falling)
		{
			// W1-P11 (SS4 "ATOM spot" / SS2.W2 rule 6): the SECOND live spot
			// halt - a turn (including the PRE-FIRST-STEP facing turn) that
			// brings a hostile into view, i.e. a walk that halts having executed
			// ZERO steps.
			//
			// PLACED FIRST IN THE BRANCH, AND THE POSITION IS LOAD-BEARING
			// (traced 2026-09-04, 1 red in 43 runs). Every ev that carries `h`
			// must either carry the absolute state `h` covers in its own payload,
			// or be positioned so its `h` matches what the client ALREADY holds -
			// CoopHashCheck::verify() runs immediately after that ev's own apply
			// (BattlePump.h), so nothing later gets a chance to converge it.
			// `ev spot` carries no TU (SPIKE-RUNBOOK.md SS2.4, published), so it
			// takes the SECOND route: emitted here, BEFORE the _beforeFirstStep
			// spend below, its h:{unitsStats} is the PRE-spend TU - exactly what
			// the client holds, having applied nothing. The post-spend TU then
			// reaches the client on bt_action_end.final, which
			// applyActionEndFinal() writes BEFORE that envelope's own verify.
			// Emitted after the spend it desynced `unitsStats` at its own seq on
			// every zero-step spot, because with no executed step there is no
			// preceding `walk_step` ev to have shipped an absolute `tuAfter`.
			//
			// DEPENDENCY, verified rather than assumed and written down so it
			// cannot rot: the OTHER spend in this block - the
			// `if (_unit->getArmor()->getTurnBeforeFirstStep()) spendTimeUnits(
			// getTurnCost())` arm at the top - fires BEFORE `unitSpotted` is even
			// computed, so no placement inside this branch could precede it.
			// `Armor::_turnBeforeFirstStep` defaults to FALSE (Armor.cpp:39, set
			// only by a ruleset's `turnBeforeFirstStep` key, Armor.cpp:130) and
			// NO ruleset under bin/standard or bin/common sets it, so that arm is
			// unreachable with the loaded mods and the `else` arm merely
			// increments a counter. A MOD THAT SETS `turnBeforeFirstStep` WOULD
			// REINTRODUCE THE MISMATCH, and at that point the fix has to become a
			// payload change to `ev spot` - which is a published schema and
			// therefore an owner ruling. repro_atom_spot.py asserts the premise
			// so it fails loudly instead of silently desyncing.
			coopNoteWalkSpot(_unit);
			if (_beforeFirstStep)
			{
				_preMovementCost = _preMovementCost * _unit->getTurnCost();
				_unit->spendTimeUnits(_preMovementCost);
			}
			if (Options::traceAI) { Log(LOG_INFO) << "Egads! A turn reveals new units! I must pause!"; }
			_unit->setHiding(false); // not hidden, are we...
			_unit->abortTurn(); //revert to a standing state.
			return cancelCurentMove();
		}
	}
}

/**
 * Aborts unit walking.
 */
void UnitWalkBState::cancel()
{
	if (_beforeFirstStep)
	{
		// cancel here would allow turning without spending any TUs
		return;
	}

	if (_parent->getSave()->getSide() == FACTION_PLAYER && _parent->getPanicHandled())
	_pf->abortPath();
}

/**
 * Handles some calculations when the path is finished.
 */
void UnitWalkBState::postPathProcedures()
{
	_action.clearTU();
	if (_unit->getFaction() != FACTION_PLAYER)
	{
		int dir = _action.finalFacing;
		if (_action.finalAction)
		{
			_unit->dontReselect();
		}
		if (_unit->getCharging() != 0)
		{
			dir = _parent->getTileEngine()->getDirectionTo(_unit->getPosition(), _unit->getCharging()->getPosition());
			if (_parent->getTileEngine()->validMeleeRange(_unit, _action.actor->getCharging(), dir))
			{
				BattleAction action;
				action.actor = _unit;
				action.target = _unit->getCharging()->getPosition();
				action.weapon = _unit->getUtilityWeapon(BT_MELEE);
				action.type = BA_HIT;
				action.targeting = true;
				action.updateTU();
				_unit->setCharging(0);
				_parent->statePushBack(new MeleeAttackBState(_parent, action));
			}
		}
		else if (_unit->isHiding())
		{
			dir = _unit->getDirection() + 4;
			_unit->setHiding(false);
			_unit->dontReselect();
		}
		if (dir != -1)
		{
			if (dir >= 8)
			{
				dir -= 8;
			}
			_unit->lookAt(dir);
			while (_unit->getStatus() == STATUS_TURNING)
			{
				_unit->turn();
				_parent->getTileEngine()->calculateFOV(_unit);
			}
		}
	}
	else if (!_parent->getPanicHandled())
	{
		//todo: set the unit to aggrostate and try to find cover?
		_unit->clearTimeUnits();
	}

	_terrain->calculateLighting(LL_UNITS, _unit->getPosition());
	_terrain->calculateFOV(_unit);
	if (!_falling)
		_parent->popState();
}

/**
 * Handles some calculations when the walking is finished.
 */
void UnitWalkBState::setNormalWalkSpeed()
{
	if (_unit->getFaction() == FACTION_PLAYER)
		_parent->setStateInterval(Options::battleXcomSpeed);
	else
		_parent->setStateInterval(Options::battleAlienSpeed);
}


/**
 * Handles the stepping sounds.
 */
void UnitWalkBState::playMovementSound()
{
	int size = _unit->getArmor()->getSize() - 1;
	if ((!_unit->getVisible() && !_parent->getSave()->getDebugMode()) || !_parent->getMap()->getCamera()->isOnScreen(_unit->getPosition(), true, size, false)) return;

	Tile *tile = _unit->getTile();
	int sound = -1;
	int unitSound = _unit->getMoveSound();
	int tileSoundOffset = tile->getFootstepSound(_parent->getSave()->getBelowTile(tile));
	int tileSound = Mod::NO_SOUND;
	if (tileSoundOffset > -1)
	{
		// play footstep sound 1
		if (_unit->getWalkingPhase() == 3)
		{
			tileSound = Mod::WALK_OFFSET + (tileSoundOffset*2);
		}
		// play footstep sound 2
		if (_unit->getWalkingPhase() == 7)
		{
			tileSound = Mod::WALK_OFFSET + (tileSoundOffset*2) + 1;
		}
	}
	if (unitSound != Mod::NO_SOUND)
	{
		// if a sound is configured in the ruleset, play that one
		if (_unit->getWalkingPhase() == 0)
		{
			sound = unitSound;
		}
	}
	else
	{
		if (_unit->getStatus() == STATUS_WALKING)
		{
			if (tileSound > Mod::NO_SOUND) //TODO: it should be `!=` but its possbile that offset could get negative is based on mod data
			{
				sound = tileSound;
			}
		}
		else if (_unit->getMovementType() == MT_FLY)
		{
			// play default flying sound
			if (_unit->getWalkingPhase() == 1)
			{
				sound = Mod::FLYING_SOUND;
			}
		}
	}

	sound = ModScript::scriptFunc1<ModScript::SelectMoveSoundUnit>(
		_unit->getArmor(),
		sound,
		_unit, _unit->getWalkingPhase(), unitSound, tileSound, Mod::WALK_OFFSET, tileSoundOffset, Mod::FLYING_SOUND, _action.getMoveType()
	);
	if (sound >= 0)
	{
		_parent->getMod()->getSoundByDepth(_parent->getDepth(), sound)->play(-1, _parent->getMap()->getSoundAngle(_unit->getPosition()));
	}
}

}
