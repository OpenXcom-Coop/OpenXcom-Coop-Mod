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

#include "UnitPanicBState.h"
#include "UnitTurnBState.h"
#include "ProjectileFlyBState.h"
#include "TileEngine.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Engine/RNG.h"
#include "BattlescapeGame.h"
#include "../Mod/Mod.h"
#include "../CoopMod/connectionTCP.h" // coop (PRD-P10): the panic outcome packet

namespace OpenXcom
{

/**
 * Sets up an UnitPanicBState.
 * @param parent Pointer to the Battlescape.
 * @param unit Panicking unit.
 */
UnitPanicBState::UnitPanicBState(BattlescapeGame *parent, BattleUnit *unit) : BattleState(parent), _unit(unit), _shotsFired(0)
{

	_berserking = _unit->getStatus() == STATUS_BERSERK;
	unit->abortTurn(); //makes the unit go to status STANDING :p

}

/**
 * Deletes the UnitPanicBState.
 */
UnitPanicBState::~UnitPanicBState()
{
}

void UnitPanicBState::init()
{
}

/**
 * Runs state functionality every cycle.
 * Ends the panicking when done.
 */
void UnitPanicBState::think()
{

	if (_unit)
	{
		// berserking requires handling here, as the target selection isn't completely random
		// and needs updating between shots.
		if (!_unit->isOut() && _shotsFired < 10 && _berserking)
		{
			_shotsFired++;
			BattleAction ba;
			ba.actor = _unit;
			ba.weapon = _unit->getMainHandWeapon();
			{
				// make autoshots if possible.
				ba.type = BA_AUTOSHOT;
				ba.updateTU();
				bool canShoot = ba.haveTU() && _parent->getSave()->canUseWeapon(ba.weapon, ba.actor, _berserking, ba.type);

				if (!canShoot)
				{
					ba.type = BA_SNAPSHOT;
					ba.updateTU();
					canShoot = ba.haveTU() && _parent->getSave()->canUseWeapon(ba.weapon, ba.actor, _berserking, ba.type);
				}

				if (!canShoot && Mod::EXTENDED_BERSERK_WITH_AIMED > 0)
				{
					if (Mod::EXTENDED_BERSERK_WITH_AIMED == 1 && ba.weapon->getCurrentWaypoints() != 0)
					{
						// can use BA_AIMEDSHOT, but cannot use BA_LAUNCH
					}
					else
					{
						ba.type = BA_AIMEDSHOT;
						ba.updateTU();
						canShoot = ba.haveTU() && _parent->getSave()->canUseWeapon(ba.weapon, ba.actor, _berserking, ba.type);
					}
				}

				if (canShoot)
				{
					// if we see enemies, shoot at the closest living one.
					if (!_unit->getVisibleUnits()->empty())
					{
						int dist = 255;
						for (auto* bu : *_unit->getVisibleUnits())
						{
							int newDist = Position::distance2d(_unit->getPosition(), bu->getPosition());
							if (newDist < dist)
							{
								ba.target = bu->getPosition();
								dist = newDist;
							}
						}
					}
					else // otherwise shoot randomly
					{
						ba.target = Position(_unit->getPosition().x + RNG::generate(-6,6), _unit->getPosition().y + RNG::generate(-6,6), _unit->getPosition().z);
					}
					// include the cost for facing our target
					int turnCost = std::abs(_unit->getDirection() - _unit->directionTo(ba.target));
					if (turnCost > 4)
					{
						turnCost = 8-turnCost;
					}
					turnCost = turnCost * _unit->getTurnCost();

					_unit->spendTimeUnits(turnCost);
					_parent->statePushFront(new UnitTurnBState(_parent, ba, false));
					// even if we don't have enough TUs to turn AND shoot, we still want to turn.
					if (ba.haveTU())
					{
						_parent->statePushNext(new ProjectileFlyBState(_parent, ba));
					}
				}
			}
			return;
		}
		if (!_unit->isOut())
		{
			_unit->abortTurn(); // set the unit status to standing in case it wasn't otherwise changed from berserk/panicked
		}
		// reset the unit's time units when all panicking is done
		_unit->clearTimeUnits();
		_unit->moraleChange(+15);

		// coop (PRD-P10): ship the panic OUTCOME.
		//
		// handlePanickingUnit() returns early on the peer in BOTH modes, so the
		// peer never rolls flee/berserk and never runs this state - but it DOES
		// adopt STATUS_PANICKING/STATUS_BERSERK, because `next_turn` stamps the
		// host's per-unit status and is sent from NextTurnState::close(), i.e.
		// BEFORE the host resolves any of it. The peer was then left holding a
		// panicking unit with its FULL turn's TU for the rest of the battle,
		// while the executor's was standing on zero - the "player unit TU
		// diverges after the alien side" shape (a soak that never loses a
		// soldier never drops morale far enough to see it).
		//
		// Only the three writes above need a packet: the dropped hand weapons
		// already cross on TileEngine::itemDrop's `Inventory` send, the flee
		// walk on UnitWalkBState's, and a berserker's shots on
		// ProjectileFlyBState's.
		//
		// Gated on getHost(), not _isActivePlayerSync: the panic RESOLVER is the
		// host in both modes (BattlescapeGame::think only calls
		// handlePanickingPlayer there, and handlePanickingUnit early-outs on the
		// peer), and in classic co-op that resolution can happen while the
		// host's _isActivePlayerSync is false (it is the client's turn).
		if (_parent->isCoop() && _parent->getCoopMod()->getHost())
		{
			Json::Value root;
			root["state"] = "panic_action";
			// coop (PHASE D.1 chain-atomicity): stamp the open chain's seq+side so the
			// client's action_end apply-barrier waits for this panic outcome before
			// sampling the chain's post-N sync-check hash (no-op off the parallel host).
			connectionTCP::coopStampChainSeq(root);
			root["unit_id"] = _unit->getId();
			root["status"] = _parent->getCoopMod()->unitstatusToInt(_unit->getStatus());
			root["time"] = _unit->getTimeUnits();
			root["energy"] = _unit->getEnergy();
			root["health"] = _unit->getHealth();
			root["morale"] = _unit->getMorale();
			root["mana"] = _unit->getMana();
			root["stunlevel"] = _unit->getStunlevel();
			root["setDirection"] = _unit->getDirection();
			root["setFaceDirection"] = _unit->getFaceDirection();
			_parent->sendPacketData(root.toStyledString());
		}
	}
	_parent->popState();
	_parent->setupCursor();
}

/**
 * Panicking cannot be cancelled.
 */
void UnitPanicBState::cancel()
{
}

}
