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
#include "BattlescapeGame.h"
#include "../Engine/Game.h"
#include "../Engine/Language.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Engine/RNG.h"
#include "../Engine/Sound.h"
#include "../Interface/Cursor.h"
#include "../Mod/AlienDeployment.h"
#include "../Mod/Armor.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleInventory.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleSoldier.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/BattleUnitStatistics.h"
#include "../Savegame/Node.h" // coop (Phase 2b atomic unit death): node danger marking
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Tile.h"
#include "../fmath.h"
#include "AIModule.h"
#include "BattleState.h"
#include "BattlescapeState.h"
#include "Camera.h"
#include "ConfirmEndMissionState.h"
#include "ExplosionBState.h"
#include "InfoboxOKState.h"
#include "InfoboxState.h"
#include "Map.h"
#include "MeleeAttackBState.h"
#include "NextTurnState.h"
#include "Pathfinding.h"
#include "ProjectileFlyBState.h"
#include "PsiAttackBState.h"
#include "TileEngine.h"
#include "UnitDieBState.h"
#include "UnitFallBState.h"
#include "UnitInfoState.h"
#include "UnitPanicBState.h"
#include "UnitTurnBState.h"
#include "UnitWalkBState.h"
#include <algorithm> // coop (Phase 2b atomic unit death): hiddenItemIds diff
#include <sstream>

#include "../CoopMod/connectionTCP.h"
#include "../CoopMod/SharedEcon.h" // coop (PRD-P4): Tier-A spawn id-manifest

namespace OpenXcom
{

bool BattlescapeGame::_debugPlay = false;

// coop
int BattlescapeGame::isYourTurn = 0;

/**
 * Update value of TU and Energy
 */
void BattleActionCost::updateTU()
{
	if (actor && skillRules)
	{
		*(RuleItemUseCost*)this = actor->getActionTUs(type, skillRules);
	}
	else if (actor && weapon)
	{
		*(RuleItemUseCost*)this = actor->getActionTUs(type, weapon);
	}
	else
	{
		clearTU();
	}
}

/**
 * Clean up action cost.
 */
void BattleActionCost::clearTU()
{
	*(RuleItemUseCost*)this = RuleItemUseCost();
}

/**
 * Test if action can be performed.
 * @param message optional message with error condition.
 * @return Unit have enough stats to perform action.
 */
bool BattleActionCost::haveTU(std::string* message)
{
	if (!skillRules && Time <= 0)
	{
		// no action, no message
		return false;
	}
	if (actor->getTimeUnits() < Time)
	{
		if (message)
		{
			*message = "STR_NOT_ENOUGH_TIME_UNITS";
		}
		return false;
	}
	if (actor->getEnergy() < Energy)
	{
		if (message)
		{
			*message = "STR_NOT_ENOUGH_ENERGY";
		}
		return false;
	}
	if (actor->getMorale() < Morale)
	{
		if (message)
		{
			*message = "STR_NOT_ENOUGH_MORALE";
		}
		return false;
	}
	if (actor->getHealth() <= Health)
	{
		if (message)
		{
			*message = "STR_NOT_ENOUGH_HEALTH";
		}
		return false;
	}
	if (actor->getMana() < Mana)
	{
		if (message)
		{
			*message = "STR_NOT_ENOUGH_MANA";
		}
		return false;
	}
	if (actor->getHealth() - actor->getStunlevel() <= Stun + Health)
	{
		if (message)
		{
			*message = "STR_NOT_ENOUGH_STUN";
		}
		return false;
	}
	return true;
}

/**
 * Spend cost of action if unit have enough stats.
 * @param message optional message with error condition.
 * @return Action was performed.
 */
bool BattleActionCost::spendTU(std::string* message)
{
	if (haveTU(message))
	{
		actor->spendCost(*this);
		return true;
	}
	return false;
}

/**
 * Builds the action a REPLAYED (peer- or AI-originated) chain runs on.
 *
 * coop, PRD-P1: the replay handlers used to mutate BattlescapeGame::_currentAction
 * - the singleton that belongs to the LOCAL player's cursor, hands panel and
 * click handling - and to setSelectedUnit() the remote actor on top of it. The
 * passive player's selection, stat panel and cursor were therefore driven by
 * whatever the teammate was doing. The BStates copy the action they are given
 * (BattleState.h:33), so a stack-local carries the replay end to end.
 */
BattleAction BattlescapeGame::makeReplayAction(BattleUnit* actor)
{
	BattleAction action;
	action.actor = actor;
	// coop (PRD-P5): mark the chain as replayed so display-only code (camera
	// follow) can tell it from the local player's own action.
	action.coopReplay = true;
	return action;
}

void BattlescapeGame::movePlayerTarget(std::string obj_str)
{

	Json::Reader reader;
	Json::Value obj;

	reader.parse(obj_str, obj);

	int id = obj["id"].asInt();

	int tu = obj["tu"].asInt();
	int energy = obj["energy"].asInt();
	int health = obj["health"].asInt();
	int morale = obj["morale"].asInt();
	int stunlevel = obj["stunlevel"].asInt();
	int mana = obj["mana"].asInt();

	int startx = obj["coords"]["start"]["x"].asInt();
	int starty = obj["coords"]["start"]["y"].asInt();
	int startz = obj["coords"]["start"]["z"].asInt();

	int endx = obj["coords"]["end"]["x"].asInt();
	int endy = obj["coords"]["end"]["y"].asInt();
	int endz = obj["coords"]["end"]["z"].asInt();

	bool strafe = obj["strafe"].asBool();
	bool run = obj["run"].asBool();
	bool sneak = obj["sneak"].asBool();

	bool visible = obj["visible"].asBool();
	bool hiding = obj["hiding"].asBool();

	Position* startpos = new Position(startx, starty, startz);
	Position* endpos = new Position(endx, endy, endz);

	BattleUnit* unit = 0;

	bool found = false;

	for (auto u : *_save->getUnits())
	{

		if (u->getId() == id)
		{
			found = true;
			unit = u;
			break;
		}
	}

	if (found == false)
	{
		return;
	}

	if (getCoopMod()->_isActiveAISync == true)
	{
		unit->setVisible(visible);
		unit->setHiding(hiding);
	}

	// start
	unit->setPosition(*startpos);

	// stats
	unit->setTimeUnits(tu);
	unit->setCoopEnergy(energy);
	unit->setHealth(health);
	unit->setCoopMorale(morale);
	unit->setCoopMana(mana);

	if (getCoopMod()->_isActiveAISync == false && getCoopMod()->getCoopGamemode() != 2 && getCoopMod()->getCoopGamemode() != 3)
	{

		for (auto& unit : *_save->getUnits())
		{

			for (int i = 0; i < obj["visible_units"].size(); i++)
			{

				int json_id = obj["visible_units"][i]["unit_id"].asInt();

				// Check if the same unit
				if (unit->getId() == json_id)
				{

					unit->addToVisibleUnits(unit);
				}
			}
		}
	}

	// other
	// coop (PRD-P1): replay on a stack-local action - no setSelectedUnit(), no
	// write to the local player's _currentAction.
	BattleAction action = makeReplayAction(unit);
	action.type = BA_WALK;

	action.targeting = false;

	action.target = *endpos;

	// new
	action.strafe = strafe;
	action.run = run;
	action.sneak = sneak;

	// coop (PRD-P1): the AI phase keeps centring unconditionally; the peer-side
	// follow is the one the player can now switch off (default ON = pre-P1
	// behaviour).
	if ((_save->getBattleGame()->getCoopMod()->_clientPanicHandle == true && Options::coopFollowPeerActions)
		|| _save->getBattleGame()->getCoopMod()->_isActiveAISync == true)
	{

		getMap()->getCamera()->centerOnPosition(action.actor->getPosition());
	}

	// coop (PRD-P1): calculate() below replaces the pathfinder's path, which is
	// what the LOCAL player's hover preview was drawn from. Drop the preview while
	// the old path is still around to unmark, otherwise its tiles stay lit.
	_save->getPathfinding()->removePreview();

	_save->getPathfinding()->calculate(action.actor, action.target, action.getMoveType());

	statePushBack(new UnitWalkBState(this, action));

	bool sound = true;

	// PVP
	if (_save->getBattleGame()->getCoopMod()->getCoopGamemode() == 2 || _save->getBattleGame()->getCoopMod()->getCoopGamemode() == 3)
	{

		if (action.sneak == true)
		{
			sound = false;
		}
	}

	if (sound == true && connectionTCP::_enable_other_player_footsteps == true)
	{
		playUnitResponseSound(action.actor, 1); // "start moving" sound
	}
}

void BattlescapeGame::turnPlayerTarget(std::string obj_str)
{
	Json::Reader reader;
	Json::Value obj;

	reader.parse(obj_str, obj);

	int id = obj["id"].asInt();

	int tu = obj["tu"].asInt();
	int energy = obj["energy"].asInt();
	int health = obj["health"].asInt();
	int morale = obj["morale"].asInt();
	int stunlevel = obj["stunlevel"].asInt();
	int mana = obj["mana"].asInt();

	int startx = obj["coords"]["start"]["x"].asInt();
	int starty = obj["coords"]["start"]["y"].asInt();
	int startz = obj["coords"]["start"]["z"].asInt();

	int endx = obj["coords"]["end"]["x"].asInt();
	int endy = obj["coords"]["end"]["y"].asInt();
	int endz = obj["coords"]["end"]["z"].asInt();

	bool isActionTypeNone = obj["isActionTypeNone"].asBool();

	Position* startpos = new Position(startx, starty, startz);
	Position* endpos = new Position(endx, endy, endz);

	BattleUnit* unit = 0;

	bool found = false;

	for (auto u : *_save->getUnits())
	{

		if (u->getId() == id)
		{
			found = true;
			unit = u;
			break;
		}
	}

	if (found == false)
	{
		return;
	}

	unit->setPosition(*startpos);

	if (getCoopMod()->_isActiveAISync == false && getCoopMod()->getCoopGamemode() != 2 && getCoopMod()->getCoopGamemode() != 3)
	{
		for (auto& unit : *_save->getUnits())
		{

			for (int i = 0; i < obj["visible_units"].size(); i++)
			{

				int json_id = obj["visible_units"][i]["unit_id"].asInt();

				// Check if the same unit
				if (unit->getId() == json_id)
				{

					unit->addToVisibleUnits(unit);
				}
			}
		}
	}

	// stats
	unit->setTimeUnits(tu);
	unit->setCoopEnergy(energy);
	unit->setHealth(health);
	unit->setCoopMorale(morale);
	unit->setCoopMana(mana);

	// other
	// coop (PRD-P1): replay on a stack-local action - no setSelectedUnit(), no
	// write to the local player's _currentAction.
	BattleAction action = makeReplayAction(unit);
	action.type = BA_TURN;

	if (isActionTypeNone == true)
	{
		action.type = BA_NONE;
	}

	action.targeting = false;

	bool isUnitAlreadyTurn = false;

	// coop (PRD-P1): the "already facing there => this is a door-open, not a
	// turn" test compares against the previous REPLAYED turn target. It used to
	// read _currentAction.target, which only held that value because the replay
	// wrote the singleton; _replayTurnTarget keeps it on the replay's own side.
	if (_replayTurnTarget == *endpos)
	{
		isUnitAlreadyTurn = true;
	}

	action.target = *endpos;
	_replayTurnTarget = *endpos;

	if (isUnitAlreadyTurn == false)
	{
		// coop: the unit's TU was already set to the host's post-turn value
		// above (setTimeUnits), so replay the turn for animation only,
		// without charging again (chargeTUs = false). Charging here would
		// double the turn cost on the client.
		statePushFront(new UnitTurnBState(this, action, false));
	}
	// door fix
	else
	{

		if (action.type == BA_NONE)
		{
			// try to open a door
			int door = _save->getTileEngine()->unitOpensDoor(unit, true);
			if (door == 0)
			{
				_save->getMod()->getSoundByDepth(_save->getDepth(), Mod::DOOR_OPEN)->play(-1, getMap()->getSoundAngle(unit->getPosition())); // normal door
			}
			if (door == 1)
			{
				_save->getMod()->getSoundByDepth(_save->getDepth(), Mod::SLIDING_DOOR_OPEN)->play(-1, getMap()->getSoundAngle(unit->getPosition())); // ufo door
			}
			if (door == 4)
			{
				// coop (PRD-P1): stays on the replay's own action. It used to be
				// parked on _currentAction, where the LOCAL player's next
				// non-target action popped it as a spurious warning.
				action.result = "STR_NOT_ENOUGH_TIME_UNITS";
			}
		}
	}
}

void BattlescapeGame::turnPlayerTargetAfter(std::string obj_str)
{

	Json::Reader reader;
	Json::Value obj;

	reader.parse(obj_str, obj);

	int unit_id = obj["unit_id"].asInt();
	int setDirection = obj["setDirection"].asInt();
	int setFaceDirection = obj["setFaceDirection"].asInt();

	int setTurretDirection = obj["setTurretDirection"].asInt();
	int setTurretToDirection = obj["setTurretToDirection"].asInt();

	BattleUnit* unit = 0;

	bool found_unit = false;

	// unit
	for (auto u : *_save->getUnits())
	{

		if (u->getId() == unit_id)
		{
			found_unit = true;
			unit = u;
			break;
		}
	}

	if (found_unit == false)
		return;

	// coop (PRD-P9 soak finding): never resurrect. abortTurn() writes
	// STATUS_STANDING, so a facing correction that lands AFTER the executor's
	// `unit_death` (the packets are independent and the death is sent from
	// UnitDieBState::init, mid-chain) put a corpse back on its feet: dead on
	// the executor, standing on 0 HP here, for the rest of the battle. The
	// facing itself is still applied - a corpse has one.
	if (!unit->isOut())
	{
		unit->abortTurn();
	}
	unit->setFaceDirection(setFaceDirection);
	unit->setDirection(setDirection);

	unit->setDirectionTurretCoop(setTurretDirection);
	unit->setTurretToDirectionCoop(setTurretToDirection);
}

void BattlescapeGame::psi_attack(std::string obj_str)
{

	Json::Reader reader;
	Json::Value obj;

	reader.parse(obj_str, obj);

	int unit_id = obj["unit_id"].asInt();

	int target_id = obj["target_id"].asInt();
	getCoopMod()->_psi_target_id = target_id;

	int tu = obj["tu"].asInt();
	int energy = obj["energy"].asInt();
	int health = obj["health"].asInt();
	int morale = obj["morale"].asInt();
	int stunlevel = obj["stunlevel"].asInt();
	int mana = obj["mana"].asInt();

	int startx = obj["coords"]["start"]["x"].asInt();
	int starty = obj["coords"]["start"]["y"].asInt();
	int startz = obj["coords"]["start"]["z"].asInt();

	int endx = obj["coords"]["end"]["x"].asInt();
	int endy = obj["coords"]["end"]["y"].asInt();
	int endz = obj["coords"]["end"]["z"].asInt();

	// new!
	std::string weapon_type = obj["weapon_type"].asString();
	std::string hand = obj["hand"].asString();
	// -1 when the packet came from a peer that predates the weapon_id field.
	int weapon_id = obj.get("weapon_id", -1).asInt();
	int type = obj["type"].asInt();

	Position* startpos = new Position(startx, starty, startz);
	Position* endpos = new Position(endx, endy, endz);

	BattleUnit* unit = 0;

	bool found_unit = false;

	// unit
	for (auto u : *_save->getUnits())
	{

		if (u->getId() == unit_id)
		{
			found_unit = true;
			unit = u;
			break;
		}
	}

	if (found_unit == false)
		return;

	unit->setPosition(*startpos);

	// stats
	unit->setTimeUnits(tu);
	unit->setCoopEnergy(energy);
	unit->setHealth(health);
	unit->setCoopMorale(morale);
	unit->setCoopMana(mana);

	// other
	// coop (PRD-P1): replay on a stack-local action - no setSelectedUnit(), no
	// write to the local player's _currentAction.
	BattleAction action = makeReplayAction(unit);
	action.targeting = false;
	action.target = *endpos;
	action.type = (BattleActionType)type;

	// coop (issue #74): resolve the actor's OWN weapon and never fabricate one -
	// a receiver-side `new BattleItem` bumps this machine's item-id counter and
	// permanently drifts the two machines' id spaces apart.
	action.weapon = coopResolveWeapon(_save, unit, weapon_id, weapon_type, hand);

	if (action.weapon && action.weapon == unit->getLeftHandWeapon())
	{
		unit->setActiveLeftHand();
	}
	else if (action.weapon && action.weapon == unit->getRightHandWeapon())
	{
		unit->setActiveRightHand();
	}

	// if weapon is not null
	if (action.weapon)
	{

		action.updateTU();

		statePushBack(new PsiAttackBState(this, action));
	}
	else
	{
		Log(LOG_INFO) << "coop: psi_attack replay skipped, unit " << unit_id
					  << " has no '" << weapon_type << "' (id " << weapon_id
					  << ") - never fabricating one (issue #74)";
	}
}

void BattlescapeGame::melee_attack(std::string obj_str)
{

	Json::Reader reader;
	Json::Value obj;

	reader.parse(obj_str, obj);

	int unit_id = obj["unit_id"].asInt();

	int target_id = obj["target_id"].asInt();
	getCoopMod()->_melee_target_id = target_id;

	int tu = obj["tu"].asInt();
	int energy = obj["energy"].asInt();
	int health = obj["health"].asInt();
	int morale = obj["morale"].asInt();
	int stunlevel = obj["stunlevel"].asInt();
	int mana = obj["mana"].asInt();

	int startx = obj["coords"]["start"]["x"].asInt();
	int starty = obj["coords"]["start"]["y"].asInt();
	int startz = obj["coords"]["start"]["z"].asInt();

	int endx = obj["coords"]["end"]["x"].asInt();
	int endy = obj["coords"]["end"]["y"].asInt();
	int endz = obj["coords"]["end"]["z"].asInt();

	// new!
	std::string weapon_type = obj["weapon_type"].asString();
	std::string hand = obj["hand"].asString();
	// -1 when the packet came from a peer that predates the weapon_id field.
	int weapon_id = obj.get("weapon_id", -1).asInt();
	int type = obj["type"].asInt();

	int hitNumber = obj["hitNumber"].asInt();
	getCoopMod()->_melee_hit_number = hitNumber;

	// ammo
	int ammo_id = obj["ammo_id"].asInt();
	std::string ammo_type = obj["ammo_type"].asString();

	getCoopMod()->_currentAmmoID = ammo_id;
	getCoopMod()->currentAmmoType = ammo_type;

	Position* startpos = new Position(startx, starty, startz);
	Position* endpos = new Position(endx, endy, endz);

	BattleUnit* unit = 0;

	bool found_unit = false;

	// unit
	for (auto u : *_save->getUnits())
	{

		if (u->getId() == unit_id)
		{
			found_unit = true;
			unit = u;
			break;
		}
	}

	// coop: every sibling replay handler has this guard; without it an unknown
	// unit id (a unit this machine has already removed) dereferences null.
	if (found_unit == false)
	{
		Log(LOG_INFO) << "coop: melee_attack replay skipped, no local unit " << unit_id;
		return;
	}

	unit->setPosition(*startpos);

	// stats
	unit->setTimeUnits(tu);
	unit->setCoopEnergy(energy);
	unit->setHealth(health);
	unit->setCoopMorale(morale);
	unit->setCoopMana(mana);

	// other
	// coop (PRD-P1): replay on a stack-local action - no setSelectedUnit(), no
	// write to the local player's _currentAction.
	BattleAction action = makeReplayAction(unit);
	action.targeting = false;
	action.target = *endpos;
	action.type = (BattleActionType)type;

	// coop (issue #74): resolve the actor's OWN weapon and never fabricate one -
	// a receiver-side `new BattleItem` bumps this machine's item-id counter and
	// permanently drifts the two machines' id spaces apart.
	action.weapon = coopResolveWeapon(_save, unit, weapon_id, weapon_type, hand);

	if (action.weapon && action.weapon == unit->getLeftHandWeapon())
	{
		unit->setActiveLeftHand();
	}
	else if (action.weapon && action.weapon == unit->getRightHandWeapon())
	{
		unit->setActiveRightHand();
	}

	// if weapon is not null
	if (action.weapon)
	{

		action.updateTU();

		// coop (PRD-P3 GAP-4b): the to-hit roll is the SENDER's. Park it so this
		// machine's TileEngine::meleeAttack replays it instead of rolling its own
		// - two independent rolls meant one machine landed a hit the other
		// missed, and from there the two hit streams no longer lined up at all.
		// Parked only once the attack is definitely going to run, so a skipped
		// replay cannot leave an orphan entry to poison the next melee.
		if (obj.isMember("hit"))
		{
			getCoopMod()->_meleeResults.push_back(obj["hit"].asBool() ? 1 : 0);
		}

		statePushBack(new MeleeAttackBState(this, action));
	}
	else
	{
		Log(LOG_INFO) << "coop: melee_attack replay skipped, unit " << unit_id
					  << " has no '" << weapon_type << "' (id " << weapon_id
					  << ") - never fabricating one (issue #74)";
	}
}

connectionTCP* BattlescapeGame::getCoopMod()
{
	return _parentState->getGame()->getCoopMod();
}

void BattlescapeGame::setCoopTaskCompleted(bool task)
{
	// coop (PRD-P6 pre-task): now an acquire/release on a depth counter, not a
	// bool store. Callers are unchanged - false still means "my chain started".
	_parentState->getGame()->getCoopMod()->setCoopTaskCompleted(task);
}

int BattlescapeGame::getCoopActorID()
{

	if (_currentAction.actor)
	{
		return _currentAction.actor->getId();
	}

	if (_save->getSelectedUnit())
	{
		return _save->getSelectedUnit()->getId();
	}

	return 0;
}

int BattlescapeGame::getCoopGamemode()
{
	return _parentState->getGame()->getCoopMod()->getCoopGamemode();
}

std::string BattlescapeGame::getCoopWeaponHand()
{
	return _parentState->_hand;
}

/**
 * Names the hand @a weapon is actually held in, so a co-op packet describes the
 * shot that happened instead of the last hand button the sender's player
 * clicked. See the header for why the old value was wrong. (coop, issue #74)
 */
std::string BattlescapeGame::coopHandOf(BattleUnit* actor, const BattleItem* weapon, const std::string& uiHand)
{
	if (actor && weapon)
	{
		if (actor->getRightHandWeapon() == weapon)
		{
			return "right";
		}
		if (actor->getLeftHandWeapon() == weapon)
		{
			return "left";
		}
	}
	return uiHand;
}

/**
 * Resolves the weapon of a replayed co-op action. Never allocates: a receiver
 * that invents a BattleItem bumps its own item-id counter and the two machines'
 * id spaces drift apart for the rest of the battle, after which every id-based
 * lookup in the protocol degrades into a by-type guess. (coop, issue #74)
 */
BattleItem* BattlescapeGame::coopResolveWeapon(SavedBattleGame* save, BattleUnit* actor, int weaponId, const std::string& weaponType, const std::string& hand)
{
	if (!save)
	{
		return nullptr;
	}

	// 1. the exact instance, on the actor that fired it
	if (actor && weaponId != -1)
	{
		for (auto* bi : *actor->getInventory())
		{
			if (bi->getId() == weaponId && (weaponType.empty() || bi->getRules()->getType() == weaponType))
			{
				return bi;
			}
		}
	}

	// 2. the hand the packet named, if it holds the right kind of weapon
	if (actor)
	{
		BattleItem* handItem = (hand == "left") ? actor->getLeftHandWeapon() : actor->getRightHandWeapon();
		if (handItem && (weaponType.empty() || handItem->getRules()->getType() == weaponType))
		{
			return handItem;
		}

		// 3. the actor's OWN inventory by type - covers a stale hand string
		//    without ever reaching for another unit's identical weapon.
		if (!weaponType.empty())
		{
			for (auto* bi : *actor->getInventory())
			{
				if (bi->getRules()->getType() == weaponType)
				{
					return bi;
				}
			}

			// 3b. built-in specials (an alien psi weapon, a fixed turret gun)
			//     belong to the unit but live outside its inventory list.
			for (auto* bi : *save->getItems())
			{
				if (bi->getOwner() == actor && bi->getRules()->getType() == weaponType)
				{
					return bi;
				}
			}
		}
	}

	// 4. the identified instance anywhere (dropped, or held by a spawned unit)
	if (weaponId != -1)
	{
		for (auto* bi : *save->getItems())
		{
			if (bi->getId() == weaponId && (weaponType.empty() || bi->getRules()->getType() == weaponType))
			{
				return bi;
			}
		}
	}

	return nullptr;
}

bool BattlescapeGame::getHost()
{
	return _parentState->getGame()->getCoopMod()->getHost();
}

bool BattlescapeGame::isCoop()
{
	return _parentState->getGame()->getCoopMod()->getCoopStatic();
}

void BattlescapeGame::abortCoopPath(int x, int y, int z, int unit_id, int setDirection, int setFaceDirection)
{

	_save->getPathfinding()->abortPathCoop();

	/*
	for (auto &unit : *_save->getUnits())
	{

		if (unit->getId() == unit_id)
		{

			unit->setDirection(setDirection);
			unit->setFaceDirection(setFaceDirection);
			teleport(x, y, z, unit);

			break;
		}

	}
	*/
}

void BattlescapeGame::abortCoopPath2()
{
	_save->getPathfinding()->abortPathCoop();
}

void BattlescapeGame::sendPacketData(std::string data)
{
	_parentState->getGame()->getCoopMod()->sendTCPPacketData(data);
}

void BattlescapeGame::coopDeath(BattleUnit* unit, const RuleDamageType* damageType, bool noSound)
{
	// coop (PRD-P10): from here until convertUnitToCorpse runs, any BT_CORPSE item
	// this unit owns is an OLDER one (the body item of a knockout), so the
	// id-manifest's remap-in-place path must not claim it. See
	// SharedEcon::noteCorpseReplayPending.
	if (unit)
	{
		SharedEcon::noteCorpseReplayPending(unit->getId());
	}

	statePushNext(new UnitDieBState(this, unit, damageType, noSound, true));
}

/**
 * coop (item 3, mint-at-apply): the world-mutating half of turning a dead unit into
 * a corpse - identical to the body of UnitDieBState::convertUnitToCorpse minus the
 * resetUiButton() presentation call (which stays on the animation clock). Extracted
 * so the parallel replay client can run it at the after_unit_death packet apply
 * (host manifest ids adopted at create by the CoopSubjectGuard below) rather than on
 * its own animation clock, where the corpse mint straddled the chain's action_end
 * sync-check hash. On the host and a classic client this runs from the animation as
 * before, byte-identical.
 */
void BattlescapeGame::coopMintCorpse(BattleUnit* unit, bool overKill)
{
	Position lastPosition = unit->getPosition();
	int size = unit->getArmor()->getSize();
	bool dropItems = (unit->hasInventory() &&
		(!Options::weaponSelfDestruction ||
		(unit->getOriginalFaction() != FACTION_HOSTILE || unit->getStatus() == STATUS_UNCONSCIOUS)));

	// coop (PRD-P10): the replay has reached its corpse creation, so the parked
	// manifest is now unambiguously about the corpse the loop below mints. Cleared
	// BEFORE removeUnconsciousBodyItem so the two can never be confused again.
	SharedEcon::clearCorpseReplayPending(unit->getId());

	// remove the unconscious body item corresponding to this unit, and if it was being carried, keep track of what slot it was in
	if (lastPosition != TileEngine::invalid)
	{
		getSave()->removeUnconsciousBodyItem(unit);
	}

	// move inventory from unit to the ground
	// coop (Phase 2a unit_casualty): capture whether itemDropInventory actually ran
	// - this is the literal "spill" fact, NOT a mode-derived guess. It can be true
	// even on an overKill-on-tile mint (mode 2, applyGravity below): dropItems &&
	// getTile() does not consult overKill, so the inventory can still spill before
	// the corpse decision runs.
	bool coopSpill = (dropItems && unit->getTile());
	if (coopSpill)
	{
		getTileEngine()->itemDropInventory(unit->getTile(), unit);
	}
	_coopCorpseMintSpill = coopSpill;

	// remove unit-tile link
	unit->setTile(nullptr, getSave());

	if (lastPosition == TileEngine::invalid) // we're being carried
	{
		if (overKill)
		{
			getSave()->removeUnconsciousBodyItem(unit);
			// coop (Phase 2a unit_casualty): carried + overKill -> no corpse.
			_coopCorpseMintMode = 2;
			_coopCorpseMintCarrierId = -1;
		}
		else
		{
			// replace the unconscious body item with a corpse in the carrying unit's inventory
			for (auto* bi : *getSave()->getItems())
			{
				if (bi->getUnit() == unit)
				{
					auto* corpseRules = unit->getArmor()->getCorpseBattlescape()[0]; // we're in an inventory, so we must be a 1x1 unit
					bi->convertToCorpse(corpseRules);
					// coop (Phase 2a unit_casualty): carried convert - the body item
					// id that was converted in place is the "corpse" this casualty
					// produced (convertToCorpse reuses the existing item's id).
					_coopCorpseMintMode = 1;
					_coopCorpseMintCarrierId = bi->getId();
					break;
				}
			}
		}
	}
	else
	{
		if (!overKill)
		{
			// coop (PRD-P4): a Tier-A spawn. The corpse SET is deterministic (the
			// armor's corpse list, size^2 of them) so both machines create the same
			// items - but each mints its own ids off its own counter, and once those
			// disagree every later id-keyed packet lands on the wrong instance. Only
			// one of these two is ever live: the record on the host (its ids ride
			// `after_unit_death`), the guard on the peer.
			SharedEcon::CoopSpawnRecord coopRec("corpse", unit->getId());
			SharedEcon::CoopSubjectGuard coopGuard(getSave(), "corpse", unit->getId());
			int i = size * size - 1;
			for (int y = size - 1; y >= 0; --y)
			{
				for (int x = size - 1; x >= 0; --x)
				{
					BattleItem *corpse = getSave()->createItemForTile(unit->getArmor()->getCorpseBattlescape()[i], nullptr, unit);
					dropItem(lastPosition + Position(x,y,0), corpse, false);
					--i;
				}
			}
			// coop (Phase 2a unit_casualty): on-tile mint - the minted-ids manifest
			// (SharedEcon::flushSpawnRecord) is the id list; this is just the mode tag.
			_coopCorpseMintMode = 0;
			_coopCorpseMintCarrierId = -1;
		}
		else
		{
			getSave()->getTileEngine()->applyGravity(getSave()->getTile(lastPosition));
			// coop (Phase 2a unit_casualty): on-tile + overKill -> no corpse.
			_coopCorpseMintMode = 2;
			_coopCorpseMintCarrierId = -1;
		}
	}
}

/**
 * coop (parallel battlescape Phase 2b - atomic unit death): the CLIENT-side
 * atomic apply of a `unit_casualty` packet - the world-mutating half of the split
 * with connectionTCP.cpp's `unit_casualty` handler (which owns the unit lookup for
 * the rank-2 state watermark, abortPathCoop, and the bystander-morale apply).
 *
 * Every field applied here is either a host absolute (carried on @a obj) or a
 * deterministic local the host's UnitDieBState ctor/think already ran (node
 * danger marking, resetTurnsSince/clearVisibleTiles/clearVisibleUnits/
 * freePatrolTarget, the FOV/lighting recalc) - nothing rolls dice, and nothing
 * here reads the death ANIMATION (Phase 2c; this phase only queues a STUB ghost
 * entry that completes immediately - see coopQueueDeathGhost).
 */
void BattlescapeGame::coopApplyCasualty(const Json::Value& obj)
{
	BattleUnit* unit = nullptr;
	const int unitId = obj.get("unit_id", -1).asInt();
	for (auto* candidate : *getSave()->getUnits())
	{
		if (candidate->getId() == unitId)
		{
			unit = candidate;
			break;
		}
	}
	if (!unit)
	{
		Log(LOG_INFO) << "coop (Phase 2b unit_casualty): apply skipped, no local unit " << unitId;
		return;
	}

	CoopDeathGhost g{};
	g.unit = unit;

	// step 2: the pre-death facing, captured BEFORE it is overwritten below - the
	// (Phase 2c) death pirouette starts from here.
	g.dirBeforeApply = unit->getDirection();

	// step 4: host-absolute stats.
	unit->setHealth(obj.get("health", 0).asInt());
	unit->setStunlevelCoop(obj.get("stunlevel", 0).asInt());
	unit->setCoopEnergy(obj.get("energy", 0).asInt());
	unit->setCoopMorale(obj.get("morale", 0).asInt());
	unit->setCoopMana(obj.get("mana", 0).asInt());
	unit->setTimeUnits(obj.get("tu", 0).asInt());

	if (obj.isMember("fatalWounds"))
	{
		const Json::Value& fatalArray = obj["fatalWounds"];
		for (int part = 0; part < BODYPART_MAX && part < (int)fatalArray.size(); ++part)
		{
			unit->setFatalWoundCoop(part, fatalArray[part].asInt());
		}
	}
	if (obj.isMember("armor"))
	{
		// coop (PRD-I3 saveBlob close): mirrors the hit_unit apply (connectionTCP.cpp).
		const Json::Value& armorArr = obj["armor"];
		for (int side = 0; side < SIDE_MAX && side < (int)armorArr.size(); ++side)
		{
			unit->setArmor(armorArr[side].asInt(), (UnitSide)side);
		}
	}

	unit->setMotionPointsCoop(obj.get("motionpoints", 0).asInt());
	unit->setRespawn(obj.get("respawn", false).asBool());
	unit->setDirection(obj.get("dir", unit->getDirection()).asInt());
	unit->setFaceDirection(obj.get("faceDir", unit->getFaceDirection()).asInt());

	if (obj.isMember("pos") && obj["pos"].size() >= 3)
	{
		const Json::Value& posArr = obj["pos"];
		const int px = posArr[0].asInt();
		const int py = posArr[1].asInt();
		const int pz = posArr[2].asInt();
		if (unit->getPosition().x != px || unit->getPosition().y != py || unit->getPosition().z != pz)
		{
			teleport(px, py, pz, unit);
		}
	}

	// step 5: the host's kill ATTRIBUTION - mirrors the legacy unit_death handler
	// (connectionTCP.cpp) exactly: additive, present-gated, never re-derived here.
	if (obj.isMember("killedBy"))
	{
		unit->killedBy((UnitFaction)obj["killedBy"].asInt());
	}
	if (obj.isMember("murdererId"))
	{
		unit->setMurdererId(obj["murdererId"].asInt());
	}

	// step 6: the deterministic locals UnitDieBState's ctor ran.
	unit->resetTurnsSince();
	unit->clearVisibleTiles();
	unit->clearVisibleUnits();
	unit->freePatrolTarget();

	// step 6b: node danger marking (UnitDieBState ctor, host-side) - hashed via the
	// save blob, so the parallel client must reproduce it exactly. Uses the unit's
	// position AFTER the teleport above (= the host's ctor position).
	if (!getSave()->isBeforeGame() && unit->getFaction() == FACTION_HOSTILE)
	{
		std::vector<Node*>* nodes = getSave()->getNodes();
		if (nodes)
		{
			for (auto* node : *nodes)
			{
				if (!node->isDummy() && Position::distanceSq(node->getPosition(), unit->getPosition()) < 4)
				{
					node->setType(node->getType() | Node::TYPE_DANGEROUS);
				}
			}
		}
	}

	// step 7: capture the PRE-death status, THEN set the final one. Must precede
	// step 8 - coopMintCorpse's dropItems test reads getStatus()==STATUS_UNCONSCIOUS.
	// The host's final health/status already folds in instaKill; never re-derived.
	g.wasUnconsciousBefore = (unit->getStatus() == STATUS_UNCONSCIOUS);
	const UnitStatus finalStatus = getCoopMod()->intToUnitstatus(obj.get("status", 0).asInt());
	unit->setCoopStatus(finalStatus);

	// step 8: the corpse/world mutation, keyed on the host's corpse-mint mode.
	// mode: 0 = on-tile mint, 1 = carried convert, 2 = overKill/no corpse,
	// 3 = none (respawn/convert - convertUnit ships its own manifest separately).
	const int corpseMode = obj["corpse"].get("mode", 3).asInt();
	switch (corpseMode)
	{
	case 0:
	{
		Tile* mintTile = unit->getTile();
		std::vector<int> beforeIds;
		if (mintTile)
		{
			for (auto* bi : *mintTile->getInventory())
			{
				beforeIds.push_back(bi->getId());
			}
		}
		SharedEcon::storeSpawnManifest(getSave(), "corpse", unit->getId(), obj);
		coopMintCorpse(unit, false);
		if (mintTile)
		{
			for (auto* bi : *mintTile->getInventory())
			{
				if (std::find(beforeIds.begin(), beforeIds.end(), bi->getId()) == beforeIds.end())
				{
					g.hiddenItemIds.push_back(bi->getId());
				}
			}
		}
		break;
	}
	case 1:
	{
		coopMintCorpse(unit, false);
		const int expectedCarrierId = obj["corpse"].get("carrier_item_id", -1).asInt();
		if (expectedCarrierId >= 0 && coopGetCorpseMintCarrierId() != expectedCarrierId)
		{
			Log(LOG_INFO) << "coop (Phase 2b unit_casualty): carried-body carrier id mismatch for unit "
						  << unit->getId() << " - host " << expectedCarrierId
						  << " local " << coopGetCorpseMintCarrierId();
		}
		break;
	}
	case 2:
		coopMintCorpse(unit, true);
		break;
	case 3:
	default:
		break;
	}

	// step 9: the FOV/lighting recalc the host's think() _extraFrame==2 branch ran.
	g.visibleAtApply = unit->getVisible();
	getTileEngine()->calculateLighting(LL_ITEMS, unit->getPosition(), unit->getArmor()->getSize());
	getTileEngine()->calculateFOV(unit->getPosition(), unit->getArmor()->getSize(), false);

	// step 11: clear selection - mirrors UnitDieBState::think()'s clearUnitSelection.
	getSave()->clearUnitSelection(unit);

	// step 12: finish the ghost entry and queue it (STUB in this phase).
	g.pos = unit->getPosition();
	g.size = unit->getArmor()->getSize();
	g.faction = unit->getFaction();
	g.finalStatus = finalStatus;
	g.direct = obj.get("direct", false).asBool();
	g.noSound = obj.get("noSound", false).asBool();
	g.bnd = obj.get("bnd", false).asBool();
	g.sideSeq = static_cast<uint32_t>(obj.get("side_seq", 0).asUInt());
	g.actionSeq = g.bnd ? UINT32_MAX : static_cast<uint32_t>(obj.get("action_seq", 0).asUInt());

	coopQueueDeathGhost(g);
}

/**
 * coop (parallel battlescape Phase 2b - atomic unit death, STUB): records @a g as
 * a completed death-ghost entry immediately. The world is ALREADY final by the
 * time coopApplyCasualty calls this (every step above ran), so there is nothing
 * left to animate in this phase - no UnitDieBState push, no death pirouette; the
 * corpse/kit are simply visible at apply. Phase 2c replaces this body with the
 * real queued+started ghost that coopActiveGhost() then reads.
 */
void BattlescapeGame::coopQueueDeathGhost(const CoopDeathGhost& g)
{
	_coopPendingGhosts.push_back(g);
	_coopPendingGhosts.back().started = true;
	++_coopDeathGhostsCompleted;
}

void BattlescapeGame::teleport(int x, int y, int z, BattleUnit* unit)
{

	if (unit)
	{
		Position newPos = Position(x, y, z);

		if (_save->getTileEngine()->isPositionValidForUnit(newPos, unit))
		{

			unit->setTile(_save->getTile(newPos), _save);
			unit->setPosition(newPos);

			_save->getTileEngine()->calculateLighting(LL_UNITS);
			handleState();
		}
	}
}

void BattlescapeGame::setTileCoop(Position pos, BattleUnit& unit)
{

	if (pos != TileEngine::invalid)
	{
		unit.setTile(_save->getTile(pos), _save);
	}
}

/**
 * Initializes all the elements in the Battlescape screen.
 * @param save Pointer to the save game.
 * @param parentState Pointer to the parent battlescape state.
 */
BattlescapeGame::BattlescapeGame(SavedBattleGame* save, BattlescapeState* parentState) : _save(save), _parentState(parentState),
																						 _playerPanicHandled(true), _AIActionCounter(0), _AISecondMove(false), _playedAggroSound(false),
																						 _endTurnRequested(false), _endConfirmationHandled(false), _allEnemiesNeutralized(false)
{
	if (_save->isPreview())
	{
		_allEnemiesNeutralized = true; // just in case
	}

	_currentAction.actor = 0;
	_currentAction.targeting = false;
	_currentAction.type = BA_NONE;
	_currentAction.skillRules = nullptr;

	_debugPlay = false;

	// coop (PRD-P6): a battle starts with a clean arbiter - action/side sequences
	// at 0 on both machines, no pending intent left over from the last one.
	connectionTCP::resetActionArbiter(true);

	// coop (chain-atomicity Strand A): battle-start hidden-explosion casualties (UFO power
	// source etc.) are a boundary-style pass with no admitted chain - keep any death here
	// seq-0 rather than opening a loose chain at battle init (the arbiter was just reset).
	coopSetBoundaryCasualty(true);
	checkForCasualties(nullptr, BattleActionAttack{}, true);
	coopSetBoundaryCasualty(false);
	cancelCurrentAction();
}

/**
 * Delete BattlescapeGame.
 */
BattlescapeGame::~BattlescapeGame()
{
	for (auto* bs : _states)
	{
		delete bs;
	}
	cleanupDeleted();
	// coop (parallel battlescape Phase 2b - atomic unit death): drop any queued
	// death-ghost entries with the battle. Phase 2b's stub completes every entry
	// immediately, so this is normally already empty; defensive for Phase 2c,
	// where an entry can still be "started" when the battle ends.
	_coopPendingGhosts.clear();
}

/**
 * Checks for units panicking or falling and so on.
 */
int BattlescapeGame::think()
{
	int ret = -1;
	// nothing is happening - see if we need some alien AI or units panicking or what have you
	if (_states.empty())
	{
		// coop
		if (_save->getUnitsFalling() && ((getCoopMod()->getCoopStatic() == true && getCoopMod()->_isActivePlayerSync == true) || getCoopMod()->getCoopStatic() == false))
		{
			statePushFront(new UnitFallBState(this));
			_save->setUnitsFalling(false);
			return ret;
		}
		// it's a non player side (ALIENS or CIVILIANS)
		// coop
		if (_save->getSide() != FACTION_PLAYER && ((getCoopMod()->getCoopStatic() == true && getCoopMod()->_isActivePlayerSync == true) || getCoopMod()->getCoopStatic() == false))
		{
			auto sideBackup = _save->getSide();
			_save->resetUnitHitStates();
			if (!_debugPlay)
			{
				// coop (PVP and HOTSEAT)
				if ((getCoopMod()->getCoopGamemode() == 2 || getCoopMod()->getCoopGamemode() == 3 || getCoopMod()->_isHotseatActive == true) && _save->getSelectedUnit())
				{

					if (_save->getSelectedUnit()->getFaction() == FACTION_NEUTRAL && getCoopMod()->_isHotseatActive == true && getCoopMod()->_isHotseatAlienTurn == true)
					{
						_endTurnRequested = true;
						statePushBack(0); // end AI turn
						return 0;
					}

					if (_save->getSelectedUnit()->getFaction() == FACTION_HOSTILE)
					{
						_endTurnRequested = true;
						statePushBack(0); // end AI turn
						return 0;
					}
				}

				if (_save->getSelectedUnit())
				{
					if (!handlePanickingUnit(_save->getSelectedUnit()))
					{
						handleAI(_save->getSelectedUnit());

						// calculate AI progress
						int units = 0;
						int total = 0;
						for (auto* bu : *_save->getUnits())
						{
							if (bu->getFaction() == sideBackup && !bu->isOut())
							{
								units++;
								total += (bu->reselectAllowed() && (bu->getBaseStats()->tu > 0)) ? bu->getTimeUnits() * 100 / bu->getBaseStats()->tu : 0;
							}
						}
						ret = units > 0 ? total / units : 0;
						// Log(LOG_INFO) << "units: " << units << " total: " << total << " ret: " << ret;
					}
				}
				else
				{
					if (_save->selectNextPlayerUnit(true, _AISecondMove) == 0)
					{
						if (!_save->getDebugMode())
						{
							_endTurnRequested = true;
							statePushBack(0); // end AI turn
						}
						else
						{
							_save->selectNextPlayerUnit();
							_debugPlay = true;
						}
					}
				}
			}
		}
		else
		{

			// coop
			if ((_save->getBattleGame()->getCoopMod()->getHost() == true && _save->getBattleGame()->getCoopMod()->getCoopStatic() == true) || _save->getBattleGame()->getCoopMod()->getCoopStatic() == false)
			{
				// it's a player side && we have not handled all panicking units
				if (!_playerPanicHandled)
				{

					_playerPanicHandled = handlePanickingPlayer();
					_save->getBattleState()->updateSoldierInfo();
				}
			}
			else if (_save->getBattleGame()->getCoopMod()->getCoopStatic() == true && _save->getBattleGame()->getCoopMod()->getHost() == false)
			{
				_playerPanicHandled = true;
			}
		}
	}

	// coop
	if (getCoopMod()->getCoopStatic() == true && getCoopMod()->_isActivePlayerSync == true && getCoopMod()->_isActiveAISync == true)
	{

		Json::Value root;
		root["state"] = "update_progress";
		root["ret"] = ret;

		root["selected_unit_id"] = -1;

		if (_save->getSelectedUnit())
		{
			root["selected_unit_id"] = _save->getSelectedUnit()->getId();
		}

		root["AISecondMove"] = _AISecondMove;

		getCoopMod()->sendTCPPacketData(root.toStyledString());
	}

	// coop
	if (getCoopMod()->getCoopStatic() == true && getCoopMod()->_isActivePlayerSync == false && getCoopMod()->_AIProgressCoop > -1 && getCoopMod()->_isActiveAISync == true)
	{
		ret = getCoopMod()->_AIProgressCoop;
		_AISecondMove = getCoopMod()->_AISecondMoveCoop;
	}

	return ret;
}

/**
 * Initializes the Battlescape game.
 */
void BattlescapeGame::init()
{
	if (_save->getSide() == FACTION_PLAYER && _save->getTurn() > 1)
	{
		_playerPanicHandled = false;
	}
}

/**
 * coop (PRD-I0): the AI-side admit analogue.
 *
 * `_actionSeq` was a PLAYER-side counter: PRD-P6 stamps it where an intent is
 * admitted, and the alien side ran completely unnumbered - so every divergence
 * introduced by an AI action could only be attributed to "somewhere in that
 * side", which for the sync-check means no attribution at all.
 *
 * handleAI has no single admit site. It has two: the BA_WALK push, and the attack
 * block that pushes either a PsiAttackBState or a UnitTurnBState followed by the
 * melee/projectile state (one chain, one seq). Each is the moment the AI COMMITS
 * to an action - the exact analogue of the arbiter admitting an intent.
 * Stamping there rather than around the whole call is deliberate: handleAI also
 * pushes the end-of-side sentinel, and `statePushBack(0)` on an empty queue runs
 * BattlescapeGame::endTurn() synchronously (which resets the arbiter), so a stamp
 * taken after the call would number a chain that does not exist and land in the
 * wrong side's namespace.
 *
 * The chain then closes exactly as a player chain does - the queue drains,
 * coopChainChanged() ships `action_end`, the client reports `action_done`. None
 * of that machinery was ever player-side-gated, so nothing had to be ungated.
 */
void BattlescapeGame::coopStampAiChain()
{
	if (!connectionTCP::parallelTurnActive() || !getHost())
	{
		return;
	}
	connectionTCP::stampAdmittedAction("ai");
}

/**
 * Handles the processing of the AI states of a unit.
 * @param unit Pointer to a unit.
 */
void BattlescapeGame::handleAI(BattleUnit* unit)
{
	std::ostringstream ss;

	if (unit->getTimeUnits() <= 5)
	{
		unit->dontReselect();
	}
	if (_AIActionCounter >= 2 || !unit->reselectAllowed() || unit->getTurnsSinceStunned() == 0) // stun check for restoring OXC behavior that AI does not attack after waking up even having full TU
	{
		if (_save->selectNextPlayerUnit(true, _AISecondMove) == 0)
		{
			if (!_save->getDebugMode())
			{
				_endTurnRequested = true;
				statePushBack(0); // end AI turn
			}
			else
			{
				_save->selectNextPlayerUnit();
				_debugPlay = true;
			}
		}
		if (_save->getSelectedUnit())
		{
			_parentState->updateSoldierInfo();
			getMap()->getCamera()->centerOnPosition(_save->getSelectedUnit()->getPosition());
			if (_save->getSelectedUnit()->getId() <= unit->getId())
			{
				_AISecondMove = true;
			}
		}
		_AIActionCounter = 0;
		return;
	}

	unit->setVisible(false); // Possible TODO: check number of player unit observers, then hide the unit if no one can see it. Should then be able to skip the next FOV call.

	_save->getTileEngine()->calculateFOV(unit->getPosition(), 1, false); // might need this populate _visibleUnit for a newly-created alien.
																		 // it might also help chryssalids realize they've zombified someone and need to move on
																		 // it should also hide units when they've killed the guy spotting them
																		 // it's also for good luck

	AIModule* ai = unit->getAIModule();
	if (!ai)
	{
		// for some reason the unit had no AI routine assigned..
		unit->setAIModule(new AIModule(_save, unit, 0));
		ai = unit->getAIModule();
	}
	_AIActionCounter++;
	if (_AIActionCounter == 1)
	{
		_playedAggroSound = false;
		unit->setHiding(false);
		if (Options::traceAI)
		{
			Log(LOG_INFO) << "#" << unit->getId() << "--" << unit->getType();
		}
	}

	BattleAction action;
	action.actor = unit;
	action.number = _AIActionCounter;
	unit->think(&action);

	if (action.type == BA_RETHINK)
	{
		_parentState->debug("Rethink");
		unit->think(&action);
	}

	_AIActionCounter = action.number;
	BattleItem* weapon = unit->getMainHandWeapon();
	bool pickUpWeaponsMoreActively = unit->getPickUpWeaponsMoreActively();
	bool weaponPickedUp = false;
	bool walkToItem = false;
	if (!weapon || !weapon->haveAnyAmmo())
	{
		if (unit->getOriginalFaction() != FACTION_PLAYER)
		{
			if ((unit->getOriginalFaction() == FACTION_HOSTILE && unit->getVisibleUnits()->empty()) || pickUpWeaponsMoreActively)
			{
				weaponPickedUp = findItem(&action, pickUpWeaponsMoreActively, walkToItem);
			}
		}
	}
	if (pickUpWeaponsMoreActively && weaponPickedUp)
	{
		// you have just picked up a weapon... use it if you can!
		_parentState->debug("Re-Rethink");
		unit->getAIModule()->setWeaponPickedUp();
		unit->think(&action);
	}

	if (unit->getCharging() != 0)
	{
		if (unit->hasAggroSound() && !_playedAggroSound)
		{
			getMod()->getSoundByDepth(_save->getDepth(), unit->getRandomAggroSound())->play(-1, getMap()->getSoundAngle(unit->getPosition()));
			_playedAggroSound = true;
		}
	}
	if (action.type == BA_WALK)
	{
		ss << "Walking to " << action.target;
		_parentState->debug(ss.str());

		auto* targetTile = _save->getTile(action.target);
		if (targetTile)
		{
			_save->getPathfinding()->calculate(action.actor, action.target, BAM_NORMAL);
		}
		if (_save->getPathfinding()->getStartDirection() != -1)
		{
			coopStampAiChain(); // coop (PRD-I0), before the push - see the helper
			statePushBack(new UnitWalkBState(this, action));
		}
		else if (walkToItem)
		{
			// impossible to walk to this tile, don't try to pick up an item from there for the rest of the turn
			targetTile->setDangerous(true);
		}
	}

	if (action.type == BA_SNAPSHOT || action.type == BA_AUTOSHOT || action.type == BA_AIMEDSHOT || action.type == BA_THROW || action.type == BA_HIT || action.type == BA_MINDCONTROL || action.type == BA_USE || action.type == BA_PANIC || action.type == BA_LAUNCH)
	{
		ss.clear();
		ss << "Attack type=" << action.type << " target=" << action.target << " weapon=" << action.weapon->getRules()->getType();
		_parentState->debug(ss.str());
		action.updateTU();
		coopStampAiChain(); // coop (PRD-I0): one seq for the whole turn+attack chain
		if (action.type == BA_MINDCONTROL || action.type == BA_PANIC || action.type == BA_USE)
		{
			statePushBack(new PsiAttackBState(this, action));
		}
		else
		{
			statePushBack(new UnitTurnBState(this, action));
			if (action.type == BA_HIT)
			{
				statePushBack(new MeleeAttackBState(this, action));
			}
			else
			{
				statePushBack(new ProjectileFlyBState(this, action));
			}
		}
	}

	if (action.type == BA_NONE)
	{
		_parentState->debug("Idle");
		_AIActionCounter = 0;
		if (_save->selectNextPlayerUnit(true, _AISecondMove) == 0)
		{
			if (!_save->getDebugMode())
			{
				_endTurnRequested = true;
				statePushBack(0); // end AI turn
			}
			else
			{
				_save->selectNextPlayerUnit();
				_debugPlay = true;
			}
		}
		if (_save->getSelectedUnit())
		{
			_parentState->updateSoldierInfo();
			getMap()->getCamera()->centerOnPosition(_save->getSelectedUnit()->getPosition());
			if (_save->getSelectedUnit()->getId() <= unit->getId())
			{
				_AISecondMove = true;
			}
		}
	}
}

/**
 * Toggles the Kneel/Standup status of the unit.
 * @param bu Pointer to a unit.
 * @return If the action succeeded.
 */
bool BattlescapeGame::kneel(BattleUnit* bu)
{
	int tu = bu->getKneelChangeCost();
	// coop (PRD-P8 §5): coopKneelReserveFor() is _save->getKneelReserved() for
	// every actor but the one whose client-sent intent is running right now.
	if (bu->getArmor()->allowsKneeling(bu->getType() == "SOLDIER") && !bu->isFloating() && ((!bu->isKneeled() && coopKneelReserveFor(bu)) || checkReservedTU(bu, tu, 0)))
	{
		BattleAction kneel;
		kneel.type = BA_KNEEL;
		kneel.actor = bu;
		kneel.Time = tu;
		if (kneel.spendTU())
		{
			bu->kneel(!bu->isKneeled());
			// kneeling or standing up can reveal new terrain or units. I guess.
			getTileEngine()->calculateFOV(bu->getPosition(), 1, false); // Update unit FOV for everyone through this position, skip tiles.
			_parentState->updateSoldierInfo();                          // This also updates the tile FOV of the unit, hence why it's skipped above.
			getTileEngine()->checkReactionFire(bu, kneel);
			return true;
		}
		else
		{
			_parentState->warning("STR_NOT_ENOUGH_TIME_UNITS");
		}
	}
	return false;
}

/**
 * Ends the turn.
 */
void BattlescapeGame::endTurn()
{

	// coop
	if (getCoopMod()->getCoopStatic() == true && getCoopMod()->getHost() == true && _save->isPreview() == false)
	{
		Json::Value root;
		root["state"] = "endTurn";
		root["side"] = (int)_save->getSide();

		// coop (PRD-P5 §5): the side-boundary reseed. In classic co-op the RNG seed
		// rode `PlayerTurnYour`, the mid-side hand-off packet - which parallel mode
		// deletes. `endTurn` is the packet that replaces it as the side-close event,
		// so it carries the seed there. Written ONLY in parallel mode and read only
		// when present, so the classic wire format is untouched.
		if (connectionTCP::parallelTurnActive())
		{
			root["seed"] = static_cast<Json::UInt64>(RNG::getSeed());
			// coop (GAP-10): mirror the boundary seed into the script-RNG relay so
			// this host's newTurnUpdateScripts reseeds to the same value it shipped.
			connectionTCP::_scriptRngSeed = RNG::getSeed();

			// coop (PRD-P6): this packet is the side transition, so it is where
			// the host advances the staleness token the client stamps on its
			// intents - and where `_actionSeq` (with PRD-P7's
			// `peerDisplayAckedSeq`, which must never be reset without it) goes
			// back to 0 for the new side.
			++connectionTCP::_sideSeq;
			root["side_seq"] = static_cast<Json::UInt>(connectionTCP::_sideSeq);
			connectionTCP::resetActionArbiter(false);
		}

		getCoopMod()->sendTCPPacketData(root.toStyledString());
	}

	_debugPlay = _save->getDebugMode() && _parentState->getGame()->isCtrlPressed() && (_save->getSide() != FACTION_NEUTRAL);
	_currentAction.type = BA_NONE;
	_currentAction.skillRules = nullptr;
	getMap()->getWaypoints()->clear();
	_currentAction.waypoints.clear();
	_parentState->showLaunchButton(false);
	_currentAction.targeting = false;
	_AISecondMove = false;

	// coop
	if (_triggerProcessed.tryRun())
	{
		if (_save->getTileEngine()->closeUfoDoors() && Mod::SLIDING_DOOR_CLOSE != -1)
		{
			getMod()->getSoundByDepth(_save->getDepth(), Mod::SLIDING_DOOR_CLOSE)->play(); // ufo door closed
		}

		// if all grenades explode we remove items that expire on that turn too.
		std::vector<std::tuple<BattleItem*, ExplosionBState*> > forRemoval;
		bool exploded = false;

		// check for hot grenades on the ground
		// coop (PRD-P3 GAP-9): BattleItem::fuseTimeEvent() ends in
		// RNG::percent(getSpecialChance()), and a failed roll re-arms or disables the
		// fuse instead of detonating - so a co-op client rolling for itself could dud
		// a grenade the host had exploded (or vice versa) and then hold, forever, an
		// item the host no longer has. `next_turn` repairs stats and tiles, never item
		// existence. The client makes NO fuse rolls; the host ships the outcome.
		const bool coopFuseClient = getCoopMod()->getCoopStatic() == true && getCoopMod()->getHost() == false;
		const bool coopFuseHost = getCoopMod()->getCoopStatic() == true && getCoopMod()->getHost() == true;
		Json::Value fuseExploded(Json::arrayValue);
		Json::Value fuseRemoved(Json::arrayValue);
		Json::Value fuseTimers(Json::arrayValue);
		if (_save->getSide() != FACTION_NEUTRAL && !_save->isPreview() && !coopFuseClient)
		{
			for (BattleItem* item : *_save->getItems())
			{
				if (item->isOwnerIgnored())
				{
					continue;
				}

				const RuleItem* rule = item->getRules();
				const Tile* tile = item->getTile();
				BattleUnit* unit = item->getOwner();

				if (!tile && unit && item->getFuseTimer() != -1 && !_allEnemiesNeutralized)
				{
					int explodeAnyway = rule->getExplodeInventory(getMod());
					if (explodeAnyway >= 2 || (explodeAnyway == 1 && item->getSlot()->getType() != INV_HAND))
					{
						tile = unit->getTile();
					}
				}
				if (tile)
				{
					const int fuseBefore = item->getFuseTimer();
					if (item->fuseTimeEvent())
					{
						if (rule->getBattleType() == BT_GRENADE) // it's a grenade to explode now
						{
							Position p = tile->getPosition().toVoxel() + Position(8, 8, -tile->getTerrainLevel() + (unit ? unit->getHeight() / 2 : 0));
							forRemoval.push_back(std::tuple(nullptr, new ExplosionBState(this, p, BattleActionAttack::GetBeforeShoot(BA_TRIGGER_TIMED_GRENADE, unit, item))));
							exploded = true;
							fuseExploded.append(item->getId());
						}
						else
						{
							forRemoval.push_back(std::tuple(item, nullptr));
						}
					}
					else if (coopFuseHost && item->getFuseTimer() != fuseBefore)
					{
						// the roll failed: fuseTimeEvent re-armed (BFT_SET) or disabled it
						Json::Value f;
						f["id"] = item->getId();
						f["timer"] = item->getFuseTimer();
						fuseTimers.append(f);
					}
				}
			}
			for (auto& p : forRemoval)
			{
				BattleItem* item = std::get<BattleItem*>(p);
				ExplosionBState* expl = std::get<ExplosionBState*>(p);
				if (expl)
				{
					expl->coopSetBoundaryExpl(true); // coop (PRD-I3 SEAM-3 a)
					statePushNext(expl);
				}
				else if (item->isSpecialWeapon())
				{
					// we can't remove special weapons, disable the fuse at least
					item->setFuseTimer(-1);
					if (coopFuseHost)
					{
						Json::Value f;
						f["id"] = item->getId();
						f["timer"] = -1;
						fuseTimers.append(f);
					}
				}
				else
				{
					if (coopFuseHost)
					{
						fuseRemoved.append(item->getId());
					}
					_save->removeItem(item);
				}
			}

			// coop: one packet per side end, and only when something happened.
			// Deliberately NOT folded into `next_turn` (PROTOCOL's first sketch):
			// next_turn only crosses at the START of the player's turn, so a fuse
			// decided when the PLAYER side ended would not reach the peer until a
			// whole alien side had run.
			if (coopFuseHost && (!fuseExploded.empty() || !fuseRemoved.empty() || !fuseTimers.empty()))
			{
				Json::Value root;
				root["state"] = "fuse_events";
				root["exploded"] = fuseExploded;
				root["removed"] = fuseRemoved;
				root["fuses"] = fuseTimers;
				getCoopMod()->sendTCPPacketData(root.toStyledString());
			}

			if (exploded)
			{
				statePushBack(0);
				return;
			}
		}
	}

	// check for terrain explosions
	Tile* t = _save->getTileEngine()->checkForTerrainExplosions();
	if (t)
	{
		Position p = t->getPosition().toVoxel();
		ExplosionBState* bexpl = new ExplosionBState(this, p, BattleActionAttack{}, t); // coop (PRD-I3 SEAM-3 a)
		bexpl->coopSetBoundaryExpl(true);
		statePushNext(bexpl);
		statePushBack(0);
		return;
	}

	if (_endTurnProcessed.tryRun())
	{
		if (_save->getSide() != FACTION_NEUTRAL)
		{
			for (BattleItem* item : *_save->getItems())
			{
				if (item->isOwnerIgnored())
				{
					continue;
				}
				item->fuseEndTurnUpdate();
			}
		}

		_save->endTurn();

		t = _save->getTileEngine()->checkForTerrainExplosions();
		if (t)
		{
			Position p = t->getPosition().toVoxel();
			ExplosionBState* bexpl = new ExplosionBState(this, p, BattleActionAttack{}, t); // coop (PRD-I3 SEAM-3 a)
			bexpl->coopSetBoundaryExpl(true);
			statePushNext(bexpl);
			statePushBack(0);
			return;
		}
	}

	_triggerProcessed.reset();
	_endTurnProcessed.reset();

	// coop (PRD-I0): the side-close phase group is done - fuses rolled and shipped
	// (`fuse_events`), terrain explosions resolved, SavedBattleGame::endTurn() run.
	// Everything above this line moves state with no admitted chain to attribute it
	// to, which is why the boundary pseudo-seq exists. Armed rather than sent: the
	// checkForCasualties() below can still push death chains, and the marker has to
	// sit behind their packets. Reached only on the FINAL pass through endTurn() -
	// the explosion paths above return early and re-enter.
	//
	// coop (PRD-I3 Option A rider): at the neutral->player transition (getSide() is
	// now FACTION_PLAYER, having just been advanced by _save->endTurn() above) this
	// `endturn` marker is REDUNDANT with the `sidestart` marker NextTurnState::close
	// arms right after `next_turn`, and it would hash BEFORE `next_turn` applies on
	// the client - violating I0's boundary hash-after-apply semantics at exactly that
	// transition. Suppress it there; keep it for the side-closes into an alien side
	// (player->hostile, hostile->neutral), which are NOT followed by `next_turn` and
	// are the only place the endturn phase group's state can be attributed.
	if (_save->getSide() != FACTION_PLAYER)
	{
		connectionTCP::coopArmSyncBoundary("endturn");
	}

	if (_save->getSide() == FACTION_PLAYER)
	{
		setupCursor();
	}
	else
	{
		getMap()->setCursorType(CT_NONE);
	}

	// coop (chain-atomicity Strand A): the side-close / side-start casualty pass. Deaths
	// here (bleed-out, decay, fuse/terrain fallout picked up after the explosions) belong
	// to the boundary, not to a mid-side chain - flag the phase so each UnitDieBState
	// latches _coopBoundaryDeath and keeps its carriers seq-0 under the ordered endturn/
	// sidestart marker. For an alien side-close the endturn marker is already armed above
	// (_pendingBoundaries), but the neutral->player pass suppresses that marker, so the
	// bracket is what keeps those bleed-out deaths off a loose chain.
	coopSetBoundaryCasualty(true);
	checkForCasualties(nullptr, BattleActionAttack{}, false, false);
	coopSetBoundaryCasualty(false);

	// fires could have been started, stopped or smoke could reveal/conceal units.
	_save->getTileEngine()->calculateLighting(LL_FIRE, TileEngine::invalid, 0, true);
	_save->getTileEngine()->recalculateFOV();

	// Calculate values
	BattlescapeTally tally = _save->getBattleGame()->tallyUnits();

	// if all units from either faction are killed - the mission is over.
	if (_save->allObjectivesDestroyed() && _save->getObjectiveType() == MUST_DESTROY)
	{
		_parentState->finishBattle(false, tally.liveSoldiers);
		return;
	}
	if (_save->getTurnLimit() > 0 && _save->getTurn() > _save->getTurnLimit())
	{
		switch (_save->getChronoTrigger())
		{
		case FORCE_ABORT:
			_save->setAborted(true);
			_parentState->finishBattle(true, tally.inExit);
			return;
		case FORCE_WIN:
		case FORCE_WIN_SURRENDER:
			_parentState->finishBattle(false, tally.liveSoldiers);
			return;
		case FORCE_LOSE:
		default:
			// force mission failure
			_save->setAborted(true);
			_parentState->finishBattle(false, 0);
			return;
		}
	}

	if (tally.liveAliens > 0 && tally.liveSoldiers > 0)
	{
		showInfoBoxQueue();

		_parentState->updateSoldierInfo();

		if (playableUnitSelected())
		{
			getMap()->getCamera()->centerOnPosition(_save->getSelectedUnit()->getPosition());
			setupCursor();
		}
	}

	// "escort the VIPs" missions don't end when all aliens are neutralized
	// objective type MUST_DESTROY was already handled above
	bool killingAllAliensIsNotEnough = (_save->getVIPSurvivalPercentage() > 0 && _save->getVIPEscapeType() != ESCAPE_NONE);

	bool battleComplete = (!killingAllAliensIsNotEnough && tally.liveAliens == 0) || tally.liveSoldiers == 0;

	if ((_save->getSide() != FACTION_NEUTRAL || battleComplete) && _endTurnRequested)
	{
		_parentState->getGame()->pushState(new NextTurnState(_save, _parentState));
	}

	_endTurnRequested = false;
}

/**
 * Checks for casualties and adjusts morale accordingly.
 * @param damageType Need to know this, for a HE explosion there is an instant death.
 * @param attack This is needed for credits for the kill.
 * @param hiddenExplosion Set to true for the explosions of UFO Power sources at start of battlescape.
 * @param terrainExplosion Set to true for the explosions of terrain.
 */
void BattlescapeGame::checkForCasualties(const RuleDamageType* damageType, BattleActionAttack attack, bool hiddenExplosion, bool terrainExplosion)
{
	// coop (PRD-I3 SEAM-8): on the parallel non-host client this function runs from a
	// REPLAYED attack/explosion (ExplosionBState) purely for DISPLAY - the client is a
	// thin client and must not RE-DECIDE any combat outcome. The victim's post-hit
	// stats are host absolutes (hit_unit: health/stun/fatalWounds/morale/energy/mana/
	// tu; BattleUnit::damage() itself already early-returns on any coop client), the
	// squad-wide bystander morale rides the death packets (bystander_morale, SEAM-4),
	// and the death is displayed by coopDeath (the UnitDieBState pushed below is a
	// no-op ctor on the client). So the morale RE-ROLL here (murderer bonus, bystander
	// loss/gain loop, stun morale) would race those host absolutes and diverge the
	// per-unit unitsCombat hash. Suppress the morale writes on the parallel client
	// only; a CLASSIC client replays the attack + runs its own damage(), so it is
	// untouched and stays byte-identical.
	//
	// coop (chain-atomicity item 4, no-reroll authority - dead-vs-live map): MORALE is
	// the ONLY checkForCasualties write that needs suppressing here. Every other combat
	// outcome the client could re-decide is already dead on a non-host coop client BEFORE
	// it can write victim state, so hit_unit / unit_death / after_unit_death are the sole
	// authority for the strict unitsCombat bucket (kneeled / mind-controller id / w0..w5):
	//   * health / stun / fatal-wounds / armor : BattleUnit::damage()  early-returns
	//         (BattleUnit.cpp, `getCoopStatic() && !getHost()`), and TileEngine::hitUnit()
	//         early-returns ahead of it (TileEngine.cpp) - which also kills the whole
	//         TileEngine::explode() unit-damage loop and the melee / reaction-fire paths,
	//         since they ALL reach a unit only through hitUnit(). hit_unit ships the
	//         victim's post-hit absolutes instead.
	//   * mind-controller id                   : TileEngine::psiAttack() early-returns
	//         (non-PvP coop client); the flip rides its own host packet.
	//   * the kill / knockout DISPOSITION       : the UnitDieBState this function pushes
	//         below is a no-op ctor on the client (UnitDieBState.cpp, !getHost() &&
	//         !_coop_death); the death is driven only by unit_death -> coopDeath.
	// So the audit's "health/stun/wounds re-roll latent" premise does not hold as-built:
	// that family needs no code, and item 4 is the morale gate below plus this record.
	// (The residual casualty divergence a mass-casualty soak still shows is unitsCore
	// liveness + items/itemIdCtr corpse-mint - the death-DISPLAY replay lag, chain-
	// atomicity item 5 - NOT a re-decide of any unitsCombat value. Regression-locked by
	// tools/coop_test/test_parallel_no_reroll.py.)
	const bool coopThinClientNoReroll = connectionTCP::parallelTurnActive() && !getHost();
	BattleUnit* origMurderer = attack.attacker;
	// If the victim was killed by the murderer's death explosion, fetch who killed the murderer and make HIM the murderer!
	if (origMurderer && (origMurderer->getSpecialAbility() == SPECAB_EXPLODEONDEATH || origMurderer->getSpecialAbility() == SPECAB_BURN_AND_EXPLODE) && origMurderer->getStatus() == STATUS_DEAD && origMurderer->getMurdererId() != 0)
	{
		for (auto* bu : *_save->getUnits())
		{
			if (bu->getId() == origMurderer->getMurdererId())
			{
				origMurderer = bu;
				break;
			}
		}
	}

	// Fetch the murder weapon
	std::string tempWeapon = "STR_WEAPON_UNKNOWN", tempAmmo = "STR_WEAPON_UNKNOWN";
	if (origMurderer)
	{
		if (attack.weapon_item)
		{
			tempWeapon = attack.weapon_item->getRules()->getName();
		}
		if (attack.damage_item)
		{
			// If the secondary melee data is used, represent this by setting the ammo to "__GUNBUTT".
			// Note: BT_MELEE items use their normal attack data rather than 'melee' data. So their 'ammo' should be the weapon itself.
			// (The following condition should match what is used in ExplosionBState::init to choose the damage power and type.)
			if (attack.type == BA_HIT && attack.damage_item->getRules()->getBattleType() != BT_MELEE)
			{
				tempAmmo = "__GUNBUTT";
			}
			else
			{
				tempAmmo = attack.damage_item->getRules()->getName();
			}
		}
	}

	for (auto* victim : *_save->getUnits())
	{
		if (victim->isIgnored())
			continue;
		BattleUnit* murderer = origMurderer;

		BattleUnitKills killStat;
		killStat.mission = _parentState->getGame()->getSavedGame()->getMissionStatistics()->size();
		killStat.setTurn(_save->getTurn(), _save->getSide());
		killStat.setUnitStats(victim);
		killStat.faction = victim->getOriginalFaction();
		killStat.side = victim->getFatalShotSide();
		killStat.bodypart = victim->getFatalShotBodyPart();
		killStat.id = victim->getId();
		killStat.weapon = tempWeapon;
		killStat.weaponAmmo = tempAmmo;

		// Determine murder type
		if (victim->getStatus() != STATUS_DEAD)
		{
			if (victim->getHealth() <= 0)
			{
				killStat.status = STATUS_DEAD;
			}
			else if (victim->getStunlevel() >= victim->getHealth() && victim->getStatus() != STATUS_UNCONSCIOUS)
			{
				killStat.status = STATUS_UNCONSCIOUS;
			}
		}

		// Assume that, in absence of a murderer and an explosion, the laster unit to hit the victim is the murderer.
		// Possible causes of death: bleed out, fire.
		// Possible causes of unconsciousness: wounds, smoke.
		// Assumption : The last person to hit the victim is the murderer.
		if (!murderer && !terrainExplosion)
		{
			for (auto* bu : *_save->getUnits())
			{
				if (bu->getId() == victim->getMurdererId())
				{
					murderer = bu;
					killStat.weapon = victim->getMurdererWeapon();
					killStat.weaponAmmo = victim->getMurdererWeaponAmmo();
					break;
				}
			}
		}

		if (murderer && killStat.status != STATUS_IGNORE_ME)
		{
			if (murderer->getFaction() == FACTION_PLAYER && murderer->getOriginalFaction() != FACTION_PLAYER)
			{
				// This must be a mind controlled unit. Find out who mind controlled him and award the kill to that unit.
				for (auto* bu : *_save->getUnits())
				{
					if (bu->getId() == murderer->getMindControllerId() && bu->getGeoscapeSoldier())
					{
						if (!victim->isCosmetic())
						{
							bu->getStatistics()->kills.push_back(new BattleUnitKills(killStat));
							if (victim->getFaction() == FACTION_HOSTILE)
							{
								bu->getStatistics()->slaveKills++;
							}
						}
						victim->setMurdererId(bu->getId());
						break;
					}
				}
			}
			else if (!murderer->getStatistics()->duplicateEntry(killStat.status, victim->getId()))
			{
				if (!victim->isCosmetic())
				{
					murderer->getStatistics()->kills.push_back(new BattleUnitKills(killStat));
				}
				victim->setMurdererId(murderer->getId());
			}
		}

		bool noSound = false;
		if (victim->getStatus() != STATUS_DEAD)
		{
			if (victim->getHealth() <= 0)
			{
				int moraleLossModifierWhenKilled = _save->getMoraleLossModifierWhenKilled(victim);

				if (murderer)
				{
					murderer->addKillCount();
					victim->killedBy(murderer->getFaction());

					// coop (hotseat)
					// civilian casualties caused by aliens should not being counted as X-Com losses
					if (_parentState && _parentState->getGame()->getCoopMod()->_isHotseatActive == true && _parentState && _parentState->getGame()->getCoopMod()->_isHotseatAlienTurn == true)
					{

						if (murderer->getFaction() == FACTION_PLAYER)
						{
							victim->killedBy(FACTION_HOSTILE);
						}
						else if (murderer->getFaction() == FACTION_HOSTILE)
						{
							victim->killedBy(FACTION_PLAYER);
						}
					}

					int modifier = murderer->getFaction() == FACTION_PLAYER ? _save->getFactionMoraleModifier(true) : 100;

					// if there is a known murderer, he will get a morale bonus if he is of a different faction (what with neutral?)
					if ((victim->getOriginalFaction() == FACTION_PLAYER && murderer->getFaction() == FACTION_HOSTILE) ||
						(victim->getOriginalFaction() == FACTION_HOSTILE && murderer->getFaction() == FACTION_PLAYER))
					{
						if (!coopThinClientNoReroll) murderer->moraleChange(20 * modifier / 100);
					}
					// murderer will get a penalty with friendly fire
					if (victim->getOriginalFaction() == murderer->getOriginalFaction())
					{
						// morale loss by friendly fire
						if (!coopThinClientNoReroll) murderer->moraleChange(-(2000 * moraleLossModifierWhenKilled / modifier / 100));
					}
					if (victim->getOriginalFaction() == FACTION_NEUTRAL)
					{
						if (murderer->getOriginalFaction() == FACTION_PLAYER)
						{
							// morale loss by xcom killing civilians
							if (!coopThinClientNoReroll) murderer->moraleChange(-(1000 * moraleLossModifierWhenKilled / modifier / 100));
						}
						else
						{
							if (!coopThinClientNoReroll) murderer->moraleChange(10);
						}
					}
				}

				if (victim->getFaction() != FACTION_NEUTRAL && !coopThinClientNoReroll)
				{
					int modifier = _save->getUnitMoraleModifier(victim);
					int loserMod = _save->getFactionMoraleModifier(victim->getOriginalFaction() != FACTION_HOSTILE);
					int winnerMod = _save->getFactionMoraleModifier(victim->getOriginalFaction() == FACTION_HOSTILE);
					for (auto* bu : *_save->getUnits())
					{
						if (!bu->isOut())
						{
							// the losing squad all get a morale loss
							if (bu->getOriginalFaction() == victim->getOriginalFaction())
							{
								// morale loss by losing a team member (not counting mind-controlled units)
								int bravery = bu->reduceByBravery(10);
								bu->moraleChange(-(modifier * moraleLossModifierWhenKilled * 200 * bravery / loserMod / 100 / 100));

								if (victim->getFaction() == FACTION_HOSTILE && murderer)
								{
									murderer->setTurnsSinceSpotted(0);
								}
							}
							// the winning squad all get a morale increase
							else
							{
								bu->moraleChange(10 * winnerMod / 100);
							}
						}
					}
				}
				if (damageType)
				{
					statePushNext(new UnitDieBState(this, victim, damageType, noSound));
				}
				else
				{
					if (hiddenExplosion)
					{
						// this is instant death from UFO power sources, without screaming sounds
						noSound = true;
						statePushNext(new UnitDieBState(this, victim, getMod()->getDamageType(DT_HE), noSound));
					}
					else
					{
						if (terrainExplosion)
						{
							// terrain explosion
							statePushNext(new UnitDieBState(this, victim, getMod()->getDamageType(DT_HE), noSound));
						}
						else
						{
							// no murderer, and no terrain explosion, must be fatal wounds
							statePushNext(new UnitDieBState(this, victim, getMod()->getDamageType(DT_NONE), noSound)); // DT_NONE = STR_HAS_DIED_FROM_A_FATAL_WOUND
						}
					}
				}
				// one of our own died, record the murderer instead of the victim
				if (victim->getGeoscapeSoldier())
				{
					victim->getStatistics()->KIA = true;
					BattleUnitKills* deathStat = new BattleUnitKills(killStat);
					if (murderer)
					{
						deathStat->setUnitStats(murderer);
						deathStat->faction = murderer->getOriginalFaction();
					}
					_parentState->getGame()->getSavedGame()->killSoldier(false, victim->getGeoscapeSoldier(), deathStat);
				}
			}
			else if (victim->getStunlevel() >= victim->getHealth() && victim->getStatus() != STATUS_UNCONSCIOUS)
			{
				// morale change when an enemy is stunned (only for the first time!)
				if (getMod()->getStunningImprovesMorale() && murderer && !victim->getStatistics()->wasUnconcious && !coopThinClientNoReroll)
				{
					if ((victim->getOriginalFaction() == FACTION_PLAYER && murderer->getFaction() == FACTION_HOSTILE) ||
						(victim->getOriginalFaction() == FACTION_HOSTILE && murderer->getFaction() == FACTION_PLAYER))
					{
						// the murderer gets a morale bonus if he is of a different faction (excluding neutrals)
						murderer->moraleChange(20);

						for (auto* winner : *_save->getUnits())
						{
							if (!winner->isOut() && winner->getOriginalFaction() == murderer->getOriginalFaction())
							{
								// the winning squad gets a morale increase (the losing squad is NOT affected)
								winner->moraleChange(10);
							}
						}
					}
				}

				victim->getStatistics()->wasUnconcious = true;
				noSound = true;
				statePushNext(new UnitDieBState(this, victim, getMod()->getDamageType(DT_NONE), noSound)); // no damage type used there
			}
			else
			{
				// piggyback of cleanup after script that change move type
				if (victim->haveNoFloorBelow() && victim->getMovementType() != MT_FLY)
				{
					_save->addFallingUnit(victim);
				}
			}
		}
	}

	BattleUnit* bu = _save->getSelectedUnit();
	if (_save->getSide() == FACTION_PLAYER)
	{
		_parentState->resetUiButton();

		if (bu && !bu->isOut())
		{
			_parentState->updateUiButton(bu);
		}
	}
}

/**
 * Shows the infoboxes in the queue (if any).
 */
void BattlescapeGame::showInfoBoxQueue()
{
	for (auto* infoboxOKState : _infoboxQueue)
	{
		_parentState->getGame()->pushState(infoboxOKState);
	}

	_infoboxQueue.clear();
}

/**
 * Sets up a mission complete notification.
 */
void BattlescapeGame::missionComplete()
{
	Game* game = _parentState->getGame();
	if (game->getMod()->getDeployment(_save->getMissionType()))
	{
		std::string missionComplete = game->getMod()->getDeployment(_save->getMissionType())->getObjectivePopup();
		if (!missionComplete.empty())
		{
			// coop
			if ((game->getCoopMod()->getCoopStatic() == true && game->getCoopMod()->getHost() == true) || game->getCoopMod()->getCoopStatic() == false)
				_infoboxQueue.push_back(new InfoboxOKState(game->getLanguage()->getString(missionComplete)));
		}
	}
}

/**
 * Handles the result of non target actions, like priming a grenade.
 */
// ===========================================================================
// coop (PRD-P6): action intents - the client asks, the host executes.
// ===========================================================================

/// Serializes an action as the body of an `action_intent`; defined below.
static Json::Value coopBuildIntent(BattlescapeGame* game, SavedBattleGame* save, const BattleAction& action, const std::string& kind);

/**
 * THE executor's entry point for a player-initiated action.
 *
 * Factored out of the local-input tails (mapClick's move/turn/shot branches, the
 * kneel button, handleNonTargetAction's prime/melee, the medikit presses) so the
 * host's own clicks and a client's `action_intent` run identical code. On the
 * host `_isActivePlayerSync` is true (the PRD-P5 executor invariant), so every
 * chain pushed here broadcasts through the existing BState send sites and the
 * client displays it exactly as it displays a host action in classic co-op.
 *
 * The kinds that have NO BattleState of their own (kneel, prime, medikit) mutate
 * synchronously and therefore ship their classic replay packet from here - the
 * UI handler that used to send it is not on this path.
 */
void BattlescapeGame::executeAction(BattleAction &action, bool calculatePath)
{
	if (!action.actor)
	{
		return;
	}

	// handleNonTargetAction() clears the type on its way out, so remember it.
	const BattleActionType type = action.type;

	switch (type)
	{
	case BA_WALK:
		if (calculatePath)
		{
			_save->getPathfinding()->calculate(action.actor, action.target, action.getMoveType());
		}
		statePushBack(new UnitWalkBState(this, action));
		break;

	case BA_TURN:
	{
		// BA_TURN is the INTENT's dispatch key, not a BattleAction type
		// UnitTurnBState understands: it reads `_action.type == BA_NONE` to decide
		// whether this turn also opens a door (UnitTurnBState.cpp:155) and whether
		// a newly spotted unit interrupts it (:199). A right-click turn is a
		// BA_NONE turn, so that is what the state must be handed.
		BattleAction turn = action;
		turn.type = BA_NONE;
		statePushBack(new UnitTurnBState(this, turn));
		break;
	}

	case BA_KNEEL:
		kneel(action.actor);
		coopSendKneelPacket(action.actor);
		break;

	case BA_THROW:
	case BA_SNAPSHOT:
	case BA_AUTOSHOT:
	case BA_AIMEDSHOT:
	case BA_LAUNCH:
		// same two pushes the mapClick targeting tail makes, in the same order
		_states.push_back(new ProjectileFlyBState(this, action));
		statePushFront(new UnitTurnBState(this, action)); // turn towards the target first
		break;

	case BA_MINDCONTROL:
	case BA_PANIC:
		statePushBack(new PsiAttackBState(this, action));
		break;

	case BA_USE:
		if (action.weapon && action.weapon->getRules()->getBattleType() == BT_PSIAMP)
		{
			statePushBack(new PsiAttackBState(this, action));
		}
		else if (action.coopTargetUnit != -1)
		{
			BattleUnit* target = coopFindUnit(action.coopTargetUnit);
			if (target && action.weapon && action.spendTU(&action.result))
			{
				const char* medkitState = action.coopMedikitMode == BMA_STIMULANT ? "stimulant"
										  : action.coopMedikitMode == BMA_PAINKILLER ? "painkiller"
																					 : "heal";
				getTileEngine()->medikitUse(&action, target,
					(BattleMediKitAction)action.coopMedikitMode, (UnitBodyPart)action.coopBodyPart);
				coopSendMedikitPacket(action, target, action.coopMedikitMode, action.coopBodyPart, medkitState);
				// decided from charge counts both machines now hold, so the peer's
				// own medikitRemoveIfEmpty reaches the same answer.
				getTileEngine()->medikitRemoveIfEmpty(&action);
			}
			_parentState->updateSoldierInfo();
		}
		else if (action.weapon
				 && (action.weapon->getRules()->getBattleType() == BT_SCANNER
					 || action.weapon->getRules()->getBattleType() == BT_MINDPROBE))
		{
			// the executor pays for it; the display (scanner window / unit info)
			// is the asking machine's own business.
			action.spendTU(&action.result);
			_parentState->updateSoldierInfo();
		}
		else
		{
			handleNonTargetAction(action);
		}
		break;

	case BA_HIT:
		handleNonTargetAction(action);
		break;

	case BA_PRIME:
	case BA_UNPRIME:
		handleNonTargetAction(action);
		coopSendPrimePacket(action, type);
		break;

	default:
		break;
	}
	// coop (PRD-I3 SEAM-7 ii): the instant kinds (kneel/prime/medikit) have now
	// emitted their replay packet above, so release the coopCloseActionChain hold
	// that kept this chain's action_end behind it. A no-op for the state-pushing
	// kinds (walk/turn/shoot - the flag was never set for them). Reaction fire does
	// NOT re-enter executeAction, so this cannot clear a sibling chain's hold.
	connectionTCP::coopNoteInstantExecuted();
}

/**
 * The door every player-initiated battle action passes through.
 *
 * Classic co-op and single player never take a branch here - the option is off,
 * so the caller runs its normal tail and the behaviour is byte-identical.
 */
bool BattlescapeGame::coopRouteAction(BattleAction &action, const std::string &kind)
{
	if (!connectionTCP::parallelTurnActive())
	{
		return false;
	}

	if (!getHost())
	{
		// The client never simulates. Everything it just built travels instead.
		getCoopMod()->sendActionIntent(coopBuildIntent(this, _save, action, kind), kind);
		return true;
	}

	// The host executes, but through the same admission gate a client intent
	// meets - otherwise the two players would be held to different rules.
	if (!connectionTCP::canAdmitAction())
	{
		// coop (PRD-P7): a chain that is nothing but locomotion is not worth making
		// the player re-click for. The input is DEFERRED instead of refused, and the
		// walk in the way stops being waited for. Refused deferral (a shot in
		// flight, a side commit) keeps PRD-P6's busy flash.
		// Serialized through the very same builder a client uses, so pending-admit
		// has ONE shape. `kind` and `seat` are stamped here because on the client
		// they are added by connectionTCP::sendActionIntent, which this side of the
		// wire never visits - and coopValidateIntent/coopExecuteIntent both key off
		// `kind`.
		Json::Value deferred = coopBuildIntent(this, _save, action, kind);
		deferred["kind"] = kind;
		deferred["seat"] = connectionTCP::localSeat();
		if (connectionTCP::coopPendIntent(connectionTCP::localSeat(), 0, kind,
				deferred.toStyledString(), true))
		{
			return true;
		}
		// coop: the peer-busy message no longer flashes the toolbar warning widget.
		// The executor is mid non-skippable chain here, so isBusy() is true and
		// BattlescapeState::updateCoopWaitBanner() shows the persistent
		// "Please wait for <player>'s action to finish" banner (suppressed when the
		// chain is this seat's own action).
		return true;
	}
	// coop (PRD-P8): the executor's own action clears its own END TURN readiness
	// (it clearly did not mean "I am done"), and drops any reserve override left
	// over from a client chain - what runs next is a LOCAL action, judged by this
	// machine's own reserve.
	connectionTCP::noteSeatActed(connectionTCP::localSeat());
	coopClearChainReserve();
	connectionTCP::stampAdmittedAction(kind);
	return false;
}

/**
 * Same door for a medikit press: the operands (which unit, which body part,
 * heal/stim/pain) have no home in BattleAction, so they are stamped onto the
 * co-op fields first.
 */
bool BattlescapeGame::coopRouteMedikit(BattleAction* action, BattleUnit* target, int medikitMode, int bodyPart)
{
	if (!action || !target || !connectionTCP::parallelTurnActive())
	{
		return false;
	}
	BattleAction copy = *action;
	copy.coopTargetUnit = target->getId();
	copy.coopMedikitMode = medikitMode;
	copy.coopBodyPart = bodyPart;
	return coopRouteAction(copy, "medikit");
}

/**
 * coop (PRD-P7): may the whole queued chain be skipped past?
 *
 * The three states listed here are pure locomotion: their outcome is the unit's
 * final position/facing, which the peer receives explicitly (the walk ends on an
 * `abortPath` teleport-correct), so running them at interval 0 changes only how
 * long the animation is on screen. Anything that ROLLS something - a projectile,
 * an explosion, a death, a melee or psi attack - plays at its normal interval,
 * and so does any chain that belongs to the AI or a civilian.
 *
 * An empty queue answers false: there is nothing to skip, and the callers use
 * "skippable" to mean "wait for this one" rather than "the field is clear".
 */
bool BattlescapeGame::chainIsSkippable() const
{
	if (_states.empty())
	{
		return false;
	}
	for (auto* bs : _states)
	{
		if (bs == 0)
		{
			// the end-turn sentinel: the side is closing, nothing to fast-forward
			return false;
		}
		BattleUnit* actor = bs->getAction().actor;
		if (dynamic_cast<UnitWalkBState*>(bs) != 0 || dynamic_cast<UnitTurnBState*>(bs) != 0)
		{
			if (!actor || actor->getFaction() != FACTION_PLAYER)
			{
				return false;
			}
		}
		else if (dynamic_cast<UnitFallBState*>(bs) != 0)
		{
			// UnitFallBState is constructed WITHOUT an action (BattlescapeGame.cpp
			// :1021 / UnitWalkBState.cpp:336), so its actor is null - the units it
			// moves are the save's falling list.
			for (auto* u : *_save->getFallingUnits())
			{
				if (u && u->getFaction() != FACTION_PLAYER)
				{
					return false;
				}
			}
		}
		else
		{
			return false;
		}
	}
	return true;
}

/**
 * coop (PRD-P7): arming is refused outside a parallel player side, so classic
 * co-op and single player never reach the interval-0 branch and stay
 * byte-identical. Disarming always takes effect.
 */
void BattlescapeGame::setCoopFastForward(bool on)
{
	_coopFastForward = on && connectionTCP::parallelTurnActive();
}

/**
 * coop (PRD-P7): the state queue changed - re-decide the fast-forward.
 *
 * Two transitions matter:
 *  - the queue DRAINED: the chain is over, so the fast-forward lapses and (on the
 *    executor) the chain's `action_end` marker is owed to the client.
 *  - the chain stopped being skippable while it was being fast-forwarded, which
 *    in practice means reaction fire interrupted a walk. The shot must play at
 *    full speed, and the pending intents are dropped: positions and TU may have
 *    moved a long way from what the player was looking at when they clicked.
 */
void BattlescapeGame::coopChainChanged()
{
	if (!connectionTCP::parallelTurnActive())
	{
		return;
	}
	if (_states.empty())
	{
		_coopFastForward = false;
		// coop (PRD-P8 §5): the chain that owned the reserve override is over.
		coopClearChainReserve();
		connectionTCP::coopCloseActionChain();
		return;
	}
	if (_coopFastForward && !chainIsSkippable())
	{
		_coopFastForward = false;
		connectionTCP::coopDenyPendingIntents();
	}
}

/**
 * Serializes an action as the body of an `action_intent` (PROTOCOL.md).
 *
 * Deviation from the sketched shape, documented in PROTOCOL.md: the intent also
 * carries `weapon_id`/`weapon_type`. `hand` alone cannot name the item that
 * acted - a unit can hold two, and built-in specials live outside the hands
 * entirely - and the host must resolve the exact instance with
 * coopResolveWeapon, which never fabricates a BattleItem (issue #74).
 */
static Json::Value coopBuildIntent(BattlescapeGame* game, SavedBattleGame* save, const BattleAction &action, const std::string &kind)
{
	Json::Value root;
	root["unit_id"] = action.actor ? action.actor->getId() : -1;
	root["ba_type"] = (int)action.type;

	root["target"]["x"] = action.target.x;
	root["target"]["y"] = action.target.y;
	root["target"]["z"] = action.target.z;

	root["run"] = action.run;
	root["strafe"] = action.strafe;
	root["sneak"] = action.sneak;
	root["ignore_spotted"] = action.ignoreSpottedEnemies;

	root["hand"] = BattlescapeGame::coopHandOf(action.actor, action.weapon, game->getCoopWeaponHand());
	root["weapon_id"] = action.weapon ? action.weapon->getId() : -1;
	root["weapon_type"] = action.weapon ? action.weapon->getRules()->getType() : std::string();

	root["waypoints"] = Json::Value(Json::arrayValue);
	for (const auto& wp : action.waypoints)
	{
		Json::Value entry;
		entry["x"] = wp.x;
		entry["y"] = wp.y;
		entry["z"] = wp.z;
		root["waypoints"].append(entry);
	}

	// PROTOCOL.md: ALL kinds carry the sender's current reserve mode; the host
	// applies it to THIS action's cost check only. PRD-P8 owns the rest.
	root["reserve"] = (int)save->getTUReserved();
	root["kneelReserve"] = save->getKneelReserved();

	root["extra"] = Json::Value(Json::objectValue);
	if (kind == "prime")
	{
		root["extra"]["fuse"] = action.value;
	}
	else if (kind == "medikit")
	{
		root["extra"]["target_unit"] = action.coopTargetUnit;
		root["extra"]["action"] = action.coopMedikitMode == BMA_STIMULANT ? "stim"
								  : action.coopMedikitMode == BMA_PAINKILLER ? "pain"
																			 : "heal";
		root["extra"]["bodypart"] = action.coopBodyPart;
	}
	else if (kind == "shoot")
	{
		root["extra"]["sprayTargeting"] = action.sprayTargeting;
	}
	return root;
}

/**
 * Host: is this intent allowed to run at all? Ownership is the important half -
 * a client may only ever drive its own seat's soldiers.
 */
std::string BattlescapeGame::coopValidateIntent(const std::string &intentJson, int seat, std::string &warning)
{
	Json::Reader reader;
	Json::Value obj;
	reader.parse(intentJson, obj);

	warning = "STR_COOP_ACTION_REFUSED";

	BattleUnit* unit = coopFindUnit(obj.get("unit_id", -1).asInt());
	if (!unit)
	{
		return "no_unit";
	}
	if (unit->isOut())
	{
		return "unit_out";
	}
	if (unit->getFaction() != FACTION_PLAYER)
	{
		warning = "STR_COOP_NOT_YOUR_SOLDIER";
		return "faction";
	}
	if (unit->getCoop() != seat)
	{
		warning = "STR_COOP_NOT_YOUR_SOLDIER";
		return "ownership";
	}

	const std::string kind = obj.get("kind", "").asString();
	if (kind == "kneel")
	{
		if (unit->getTimeUnits() < unit->getKneelChangeCost())
		{
			warning = "STR_NOT_ENOUGH_TIME_UNITS";
			return "no_tu";
		}
	}
	else if (kind == "shoot" || kind == "throw" || kind == "psi" || kind == "melee"
			 || kind == "prime" || kind == "medikit")
	{
		BattleItem* weapon = coopResolveWeapon(_save, unit,
			obj.get("weapon_id", -1).asInt(), obj.get("weapon_type", "").asString(),
			obj.get("hand", "").asString());
		if (!weapon)
		{
			// issue #74: never fabricate one to make the intent runnable.
			return "no_weapon";
		}
		BattleActionCost cost((BattleActionType)obj.get("ba_type", (int)BA_NONE).asInt(), unit, weapon);
		std::string message;
		// An EMPTY message means haveTU() bailed on `Time <= 0` - a free action,
		// not an unaffordable one. Denying that would refuse every zero-cost
		// action outright, so only a real cost complaint is a refusal.
		if (!cost.haveTU(&message) && !message.empty())
		{
			warning = message;
			return "no_tu";
		}
	}

	warning.clear();
	return "";
}

/**
 * Host: rebuild the client's intent as a BattleAction and run it.
 *
 * The action is built with makeReplayAction, i.e. `coopReplay` set: it is a PEER
 * action as far as this machine's display is concerned, so it must not yank the
 * host's camera (PRD-P1) - and `cameraPosition` stays unset for the same reason.
 *
 * PRD-P7 added `localOrigin`: a deferred intent that came from THIS machine's own
 * click is replayed through the same serialization (so pending-admit has one
 * shape), but it is the local player's own action, so it must NOT be flagged
 * coopReplay - that flag is what tells the display code "somebody else did this".
 */
void BattlescapeGame::coopExecuteIntent(const std::string &intentJson, bool localOrigin)
{
	Json::Reader reader;
	Json::Value obj;
	reader.parse(intentJson, obj);

	BattleUnit* unit = coopFindUnit(obj.get("unit_id", -1).asInt());
	if (!unit)
	{
		return;
	}

	const std::string kind = obj.get("kind", "").asString();

	BattleAction action = makeReplayAction(unit);
	action.coopReplay = !localOrigin;
	action.targeting = false;
	action.type = (BattleActionType)obj.get("ba_type", (int)BA_NONE).asInt();
	action.target = Position(obj["target"].get("x", 0).asInt(),
							 obj["target"].get("y", 0).asInt(),
							 obj["target"].get("z", 0).asInt());
	action.run = obj.get("run", false).asBool();
	action.strafe = obj.get("strafe", false).asBool();
	action.sneak = obj.get("sneak", false).asBool();
	action.ignoreSpottedEnemies = obj.get("ignore_spotted", false).asBool();
	action.cameraPosition = Position(0, 0, -1);

	action.weapon = coopResolveWeapon(_save, unit, obj.get("weapon_id", -1).asInt(),
		obj.get("weapon_type", "").asString(), obj.get("hand", "").asString());

	const Json::Value& wps = obj["waypoints"];
	for (Json::ArrayIndex i = 0; i < wps.size(); ++i)
	{
		action.waypoints.push_back(Position(wps[i].get("x", 0).asInt(),
											wps[i].get("y", 0).asInt(),
											wps[i].get("z", 0).asInt()));
	}

	const Json::Value& extra = obj["extra"];
	if (kind == "prime")
	{
		action.value = extra.get("fuse", -1).asInt();
	}
	else if (kind == "medikit")
	{
		const std::string mode = extra.get("action", "heal").asString();
		action.coopTargetUnit = extra.get("target_unit", -1).asInt();
		action.coopMedikitMode = mode == "stim" ? BMA_STIMULANT
							   : mode == "pain" ? BMA_PAINKILLER
												: BMA_HEAL;
		action.coopBodyPart = extra.get("bodypart", 0).asInt();
	}
	else if (kind == "shoot")
	{
		action.sprayTargeting = extra.get("sprayTargeting", false).asBool();
	}

	if (kind == "shoot" || kind == "throw" || kind == "psi" || kind == "melee"
		|| kind == "prime" || kind == "medikit" || kind == "other")
	{
		action.updateTU();
	}

	// PROTOCOL.md: the sender's reserve settings apply to THIS action's cost
	// check only.
	//
	// PRD-P8 §5 localizes it properly. PRD-P6 swapped the values into _save around
	// the synchronous call, which covered kneel() and everything else decided
	// inside executeAction - but a walk's reserve check is per STEP, inside
	// UnitWalkBState::think(), frames after this function has returned and the
	// values were put back. A client's walk was therefore judged against the
	// HOST's reserve for its entire length. The override below lives as long as
	// the chain does and is keyed on the actor, so it cannot leak sideways onto
	// another unit; the host's own UI reading of _save is left untouched, which
	// the swap could not manage either.
	coopClearChainReserve();
	if (obj.isMember("reserve") || obj.isMember("kneelReserve"))
	{
		_coopChainReserveActive = true;
		_coopChainReserveUnit = unit->getId();
		_coopChainReserve = obj.isMember("reserve")
			? (BattleActionType)obj["reserve"].asInt() : _save->getTUReserved();
		_coopChainKneelReserve = obj.isMember("kneelReserve")
			? obj["kneelReserve"].asBool() : _save->getKneelReserved();
	}

	executeAction(action, true);

	if (_states.empty())
	{
		// nothing was queued (kneel, prime, medikit, a walk with no path): the
		// chain is already over, so coopChainChanged() will never be reached.
		coopClearChainReserve();
	}
}

/**
 * coop (PRD-P8 §5): the reserve a cost check must judge `bu` by.
 *
 * Only the actor of the running intent is answered from the override; everything
 * else - the local player's own soldiers, the AI, a reaction-fire check - reads
 * this machine's own setting exactly as it always did.
 */
BattleActionType BattlescapeGame::coopReserveModeFor(const BattleUnit* bu) const
{
	if (_coopChainReserveActive && bu && bu->getId() == _coopChainReserveUnit)
	{
		return _coopChainReserve;
	}
	return _save->getTUReserved();
}

bool BattlescapeGame::coopKneelReserveFor(const BattleUnit* bu) const
{
	if (_coopChainReserveActive && bu && bu->getId() == _coopChainReserveUnit)
	{
		return _coopChainKneelReserve;
	}
	return _save->getKneelReserved();
}

void BattlescapeGame::coopClearChainReserve()
{
	_coopChainReserveActive = false;
	_coopChainReserveUnit = -1;
	_coopChainReserve = BA_NONE;
	_coopChainKneelReserve = false;
}

/**
 * The classic `kneel` replay packet. kneel() has no BattleState of its own, so
 * nothing else would tell the peer about it.
 */
void BattlescapeGame::coopSendKneelPacket(BattleUnit* bu)
{
	if (!bu || !isCoop())
	{
		return;
	}
	Json::Value obj;
	obj["state"] = "kneel";
	obj["id"] = bu->getId();
	// coop (PRD-I3 SEAM-1): the actor's POST-ACTION state. kneel() has no
	// BattleState, so the peer replays it through toggeCoopKneel and re-decides -
	// and its reserve gate (checkReservedTU / coopKneelReserveFor, keyed on the
	// PEER's own reserve, which parallel mode does not replicate) can refuse a
	// kneel this executor performed. The kneel cost is a constant (4 down / 8 up),
	// so the charge only diverges when the flip itself does - the two drift
	// together. Shipping the executor's final tu/energy AND kneeling bit lets the
	// peer mirror the executed kneel instead of re-deciding it. Additive and
	// presence-gated: an older peer ignores them and keeps the legacy re-decide.
	obj["tu"] = bu->getTimeUnits();
	obj["energy"] = bu->getEnergy();
	obj["kneeled"] = bu->isKneeled();
	getCoopMod()->sendTCPPacketData(obj.toStyledString());
}

/**
 * The classic `active_grenade` replay packet, shipped with the fuse the weapon
 * ACTUALLY ended up on - a prime that failed its TU check ships -1, so the peer
 * mirrors the failure instead of arming a grenade the executor never armed.
 */
void BattlescapeGame::coopSendPrimePacket(const BattleAction &action, BattleActionType primeType)
{
	if (!isCoop() || !action.actor || !action.weapon)
	{
		return;
	}
	Json::Value root;
	root["state"] = "active_grenade";
	root["fusetimer"] = action.weapon->getFuseTimer();
	root["hand"] = coopHandOf(action.actor, action.weapon, getCoopWeaponHand());
	root["type"] = (int)primeType;
	root["actor_id"] = action.actor->getId();
	root["item_id"] = action.weapon->getId();
	// coop (PRD-P9 soak finding, same shape as rider R2): the ACTOR's cost.
	// Prime, unprime and medikit mutate synchronously inside a UI handler, so
	// they push no BattleState and the peer has nothing that would charge them
	// - it mirrored the EFFECT (fuse, wounds) but never the price, and the two
	// copies of the soldier drifted apart by the action's TU on every use
	// (measured: 31 vs 62 after one prime). Additive and presence-gated.
	root["tu"] = action.actor->getTimeUnits();
	root["energy"] = action.actor->getEnergy();
	getCoopMod()->sendTCPPacketData(root.toStyledString());
}

/**
 * The classic `medkit` replay packet, plus the healer/weapon identification the
 * legacy shape never carried - without it the receiver has to guess the medikit
 * from whatever is in ITS OWN _currentAction, which in parallel mode belongs to
 * the other player entirely.
 */
void BattlescapeGame::coopSendMedikitPacket(const BattleAction &action, BattleUnit* target, int medikitMode, int bodyPart, const std::string &medkitState)
{
	if (!isCoop() || !target || !action.actor || !action.weapon)
	{
		return;
	}
	Json::Value obj;
	obj["state"] = "medkit";
	obj["actor_id"] = target->getId();     // legacy name: this is the PATIENT
	obj["type"] = (int)action.type;
	obj["part"] = bodyPart;
	obj["medkit_state"] = medkitState;
	obj["action_result"] = action.result;
	obj["time"] = action.Time;
	// additive (an older peer ignores them)
	obj["healer_id"] = action.actor->getId();
	obj["weapon_id"] = action.weapon->getId();
	obj["weapon_type"] = action.weapon->getRules()->getType();
	obj["hand"] = coopHandOf(action.actor, action.weapon, getCoopWeaponHand());
	// coop (PRD-P9 soak finding, same shape as rider R2): the ACTOR's cost.
	// Prime, unprime and medikit mutate synchronously inside a UI handler, so
	// they push no BattleState and the peer has nothing that would charge them
	// - it mirrored the EFFECT (fuse, wounds) but never the price, and the two
	// copies of the soldier drifted apart by the action's TU on every use
	// (measured: 31 vs 62 after one prime). Additive and presence-gated.
	obj["tu"] = action.actor->getTimeUnits();
	obj["energy"] = action.actor->getEnergy();
	getCoopMod()->sendTCPPacketData(obj.toStyledString());
	(void)medikitMode;
}

void BattlescapeGame::handleNonTargetAction()
{
	// coop (PRD-P6): prime / unprime / melee are confirmed here (the action menu
	// only sets the type up), so this is where the parallel client turns them
	// into an intent instead of mutating its own sim. BA_USE is deliberately NOT
	// routed: its only local effect is updateGameStateAfterScript, which the
	// classic replay path runs on both machines anyway.
	if (connectionTCP::parallelTurnActive() && !_currentAction.targeting
		&& _currentAction.result.empty() && _currentAction.actor)
	{
		const char* kind = nullptr;
		if (_currentAction.type == BA_HIT)
		{
			kind = "melee";
		}
		else if (_currentAction.type == BA_UNPRIME
				 || (_currentAction.type == BA_PRIME && _currentAction.value > -1))
		{
			kind = "prime";
		}

		if (kind)
		{
			BattleAction action = _currentAction;
			if (coopRouteAction(action, kind))
			{
				_currentAction.type = BA_NONE;
				_currentAction.value = 0;
				_parentState->updateSoldierInfo();
				setupCursor();
				return;
			}
		}
	}

	handleNonTargetAction(_currentAction);
}

/**
 * coop (PRD-P1): the same handler on an explicit action, so a replayed peer
 * action (coopActionClick) can run its BA_PRIME/BA_UNPRIME/BA_USE/BA_HIT
 * follow-up without writing the LOCAL player's _currentAction. The no-argument
 * overload above passes _currentAction, so every classic call site is unchanged.
 */
void BattlescapeGame::handleNonTargetAction(BattleAction& action)
{
	if (!action.targeting)
	{
		std::string error;
		action.cameraPosition = Position(0, 0, -1);
		if (!action.result.empty())
		{
			_parentState->warning(action.result);
			action.result = "";
		}
		else if (action.type == BA_PRIME && action.value > -1)
		{
			if (action.spendTU(&error))
			{
				_parentState->warning(action.weapon->getRules()->getPrimeActionMessage());
				action.weapon->setFuseTimer(action.value);
				playSound(action.weapon->getRules()->getPrimeSound()); // prime sound
				_save->getTileEngine()->calculateLighting(LL_UNITS, action.actor->getPosition());
				_save->getTileEngine()->calculateFOV(action.actor->getPosition(), action.weapon->getVisibilityUpdateRange(), false);
			}
			else
			{
				_parentState->warning(error);
			}
		}
		else if (action.type == BA_UNPRIME)
		{
			if (action.spendTU(&error))
			{
				_parentState->warning(action.weapon->getRules()->getUnprimeActionMessage());
				action.weapon->setFuseTimer(-1);
				playSound(action.weapon->getRules()->getUnprimeSound()); // unprime sound
				_save->getTileEngine()->calculateLighting(LL_UNITS, action.actor->getPosition());
				_save->getTileEngine()->calculateFOV(action.actor->getPosition(), action.weapon->getVisibilityUpdateRange(), false);
			}
			else
			{
				_parentState->warning(error);
			}
		}
		else if (action.type == BA_USE)
		{
			getTileEngine()->updateGameStateAfterScript(BattleActionAttack::GetBeforeShoot(action), TileEngine::invalid);
		}
		else if (action.type == BA_HIT)
		{
			if (action.haveTU(&error))
			{
				statePushBack(new MeleeAttackBState(this, action));
			}
			else
			{
				_parentState->warning(error);
			}
		}
		if (action.type != BA_HIT) // don't clear the action type if we're meleeing, let the melee action state take care of that
		{
			action.type = BA_NONE;
		}
		_parentState->updateSoldierInfo();
	}

	setupCursor();
}

void BattlescapeGame::endTurnCoop()
{
	_parentState->endTurnCoop();
}

void BattlescapeGame::endBattleTurnCoop()
{
	endTurn();
}

/**
 * Sets the cursor according to the selected action.
 */
void BattlescapeGame::setupCursor()
{
	// coop: while it's not our turn, the active player's synced actions must not
	// drive our cursor (e.g. a teammate firing would otherwise flip us to CT_AIM).
	// Keep the standard box cursor for the off-turn player.
	if (getCoopMod()->getCoopStatic() && isYourTurn != 2 && isYourTurn != 0)
	{
		getMap()->setCursorType(CT_NORMAL);
		return;
	}

	if (_currentAction.targeting)
	{
		if (_currentAction.type == BA_THROW)
		{
			getMap()->setCursorType(CT_THROW);
		}
		else if (_currentAction.type == BA_MINDCONTROL || _currentAction.type == BA_PANIC || _currentAction.type == BA_USE)
		{
			getMap()->setCursorType(CT_PSI);
		}
		else if (_currentAction.type == BA_LAUNCH)
		{
			getMap()->setCursorType(CT_WAYPOINT);
		}
		else
		{
			getMap()->setCursorType(CT_AIM);
		}
	}
	else if (_currentAction.type != BA_HIT)
	{
		_currentAction.actor = _save->getSelectedUnit();
		if (_currentAction.actor)
		{
			getMap()->setCursorType(CT_NORMAL, _currentAction.actor->getArmor()->getSize());
		}
		else
		{
			getMap()->setCursorType(CT_NORMAL);
		}
	}
}

/**
 * Determines whether a playable unit is selected. Normally only player side units can be selected, but in debug mode one can play with aliens too :)
 * Is used to see if stats can be displayed.
 * @return Whether a playable unit is selected.
 */
bool BattlescapeGame::playableUnitSelected() const
{
	return _save->getSelectedUnit() != 0 && (_save->getSide() == FACTION_PLAYER || _save->getDebugMode());
}

/**
 * Gives time slice to the front state.
 */
void BattlescapeGame::handleState()
{

	// coop
	connectionTCP::pauseSound = false;

	if (!_states.empty())
	{
		// end turn request?
		if (_states.front() == 0)
		{
			_states.pop_front();
			endTurn();
			return;
		}
		else
		{
			_states.front()->think();
		}
		getMap()->invalidate(); // redraw map
	}
}

// coop
void BattlescapeGame::handleStateCoop()
{

	connectionTCP::pauseSound = true;

	if (!_states.empty())
	{
		_states.front()->think();
	}
}

/**
 * Pushes a state to the front of the queue and starts it.
 * @param bs Battlestate.
 */
void BattlescapeGame::statePushFront(BattleState* bs)
{
	_states.push_front(bs);
	bs->init();
	coopChainChanged(); // coop (PRD-P7): reaction fire lands here
}

/**
 * Pushes a state as the next state after the current one.
 * @param bs Battlestate.
 */
void BattlescapeGame::statePushNext(BattleState* bs)
{
	if (_states.empty())
	{
		_states.push_front(bs);
		bs->init();
	}
	else
	{
		_states.insert(++_states.begin(), bs);
	}
	coopChainChanged(); // coop (PRD-P7)
}

/**
 * Pushes a state to the back.
 * @param bs Battlestate.
 */
void BattlescapeGame::statePushBack(BattleState* bs)
{
	if (_states.empty())
	{
		_states.push_front(bs);
		// end turn request?
		if (_states.front() == 0)
		{
			_states.pop_front();
			endTurn();
			return;
		}
		else
		{
			bs->init();
		}
	}
	else
	{
		_states.push_back(bs);
	}
	coopChainChanged(); // coop (PRD-P7)
}

/**
 * Removes the current state.
 *
 * This is a very important function. It is called by a BattleState (walking, projectile is flying, explosions,...) at the moment this state has finished its action.
 * Here we check the result of that action and do all the aftermath.
 * The state is popped off the list.
 */
void BattlescapeGame::popState()
{
	if (Options::traceAI)
	{
		Log(LOG_INFO) << "BattlescapeGame::popState() #" << _AIActionCounter << " with " << (_save->getSelectedUnit() ? _save->getSelectedUnit()->getTimeUnits() : -9999) << " TU";
	}
	bool actionFailed = false;

	if (_states.empty())
		return;

	auto* first = _states.front();
	BattleAction action = first->getAction();

	if (action.actor && !action.result.empty() && action.actor->getFaction() == FACTION_PLAYER && _playerPanicHandled && (_save->getSide() == FACTION_PLAYER || _debugPlay))
	{
		_parentState->warning(action.result);
		actionFailed = true;
	}
	_deleted.push_back(first);
	_states.pop_front();
	first->deinit();

	// handle the end of this unit's actions
	if (action.actor && noActionsPending(action.actor))
	{
		if (action.actor->getFaction() == FACTION_PLAYER)
		{
			if (_save->getSide() == FACTION_PLAYER)
			{
				// after throwing the cursor returns to default cursor, after shooting it stays in targeting mode and the player can shoot again in the same mode (autoshot,snap,aimed)
				if ((action.type == BA_THROW || action.type == BA_LAUNCH) && !actionFailed)
				{
					// clean up the waypoints
					if (action.type == BA_LAUNCH)
					{
						_currentAction.waypoints.clear();
					}

					cancelCurrentAction(true);
				}
				_parentState->getGame()->getCursor()->setVisible(true);
				setupCursor();
			}
		}
		else
		{
			if (_save->getSide() != FACTION_PLAYER && !_debugPlay)
			{
				// AI does three things per unit, before switching to the next, or it got killed before doing the second thing
				if (_AIActionCounter > 2 || _save->getSelectedUnit() == 0 || _save->getSelectedUnit()->isOut())
				{
					_AIActionCounter = 0;
					if (_states.empty() && _save->selectNextPlayerUnit(true) == 0)
					{
						if (!_save->getDebugMode())
						{
							_endTurnRequested = true;
							statePushBack(0); // end AI turn
						}
						else
						{
							_save->selectNextPlayerUnit();
							_debugPlay = true;
						}
					}
					if (_save->getSelectedUnit())
					{
						getMap()->getCamera()->centerOnPosition(_save->getSelectedUnit()->getPosition());
					}
				}
			}
			else if (_debugPlay)
			{
				_parentState->getGame()->getCursor()->setVisible(true);
				setupCursor();
			}
		}
	}

	if (!_states.empty())
	{
		// end turn request?
		if (_states.front() == 0)
		{
			while (!_states.empty())
			{
				if (_states.front() == 0)
					_states.pop_front();
				else
					break;
			}
			if (_states.empty())
			{
				endTurn();
				return;
			}
			else
			{
				_states.push_back(0);
			}
		}
		// init the next state in queue
		_states.front()->init();
	}

	// the currently selected unit died or became unconscious or disappeared inexplicably
	if (_save->getSelectedUnit() == 0 || _save->getSelectedUnit()->isOut())
	{
		cancelCurrentAction();
		getMap()->setCursorType(CT_NORMAL, 1);
		_parentState->getGame()->getCursor()->setVisible(true);
		if (_save->getSide() == FACTION_PLAYER)
			_save->setSelectedUnit(0);
		else
			_save->selectNextPlayerUnit(true, true);
	}
	_parentState->updateSoldierInfo();
	// coop (PRD-P7): the drain point. Clears the fast-forward and, on the executor,
	// tells the client that the chain it is displaying has no more packets coming.
	coopChainChanged();
}

/**
 * Determines whether there are any actions pending for the given unit.
 * @param bu BattleUnit.
 * @return True if there are no actions pending.
 */
bool BattlescapeGame::noActionsPending(BattleUnit* bu)
{
	if (_states.empty())
		return true;

	for (auto* battleState : _states)
	{
		if (battleState != 0 && battleState->getAction().actor == bu)
			return false;
	}

	return true;
}

/**
 * Sets the timer interval for think() calls of the state.
 * @param interval An interval in ms.
 */
void BattlescapeGame::setStateInterval(Uint32 interval)
{
	_parentState->setStateInterval(interval);
}

/**
 * Checks against reserved time units and energy units.
 * @param bu Pointer to the unit.
 * @param tu Number of time units to check.
 * @param energy Number of energy units to check.
 * @param justChecking True to suppress error messages, false otherwise.
 * @return bool Whether or not we got enough time units.
 */
bool BattlescapeGame::checkReservedTU(BattleUnit* bu, int tu, int energy, bool justChecking)
{
	BattleActionCost cost;
	cost.actor = bu;
	// coop (PRD-P8 §5): the running intent's reserve when `bu` is its actor,
	// otherwise this machine's own - see coopReserveModeFor().
	const BattleActionType coopReserve = coopReserveModeFor(bu);
	const bool coopKneelReserve = coopKneelReserveFor(bu);
	cost.type = coopReserve;                    // avoid changing _tuReserved in this method
	cost.weapon = bu->getMainHandWeapon(false); // check TUs against slowest weapon if we have two weapons

	if (_save->getSide() != bu->getFaction() || _save->getSide() == FACTION_NEUTRAL)
	{
		return tu <= bu->getTimeUnits();
	}

	if (_save->getSide() == FACTION_HOSTILE && !_debugPlay) // aliens reserve TUs as a percentage rather than just enough for a single action.
	{
		AIModule* ai = bu->getAIModule();
		if (ai)
		{
			cost.type = ai->getReserveMode();
		}
		cost.updateTU();
		cost.Energy += energy;
		cost.Time = tu; // override original
		switch (cost.type)
		{
		case BA_SNAPSHOT:
			cost.Time += (bu->getBaseStats()->tu / 3);
			break; // 33%
		case BA_AUTOSHOT:
			cost.Time += ((bu->getBaseStats()->tu / 5) * 2);
			break; // 40%
		case BA_AIMEDSHOT:
			cost.Time += (bu->getBaseStats()->tu / 2);
			break; // 50%
		default:
			break;
		}
		return cost.Time <= 0 || cost.haveTU();
	}

	cost.updateTU();
	// if the weapon has no autoshot, reserve TUs for snapshot
	if (cost.Time == 0 && cost.type == BA_AUTOSHOT)
	{
		cost.type = BA_SNAPSHOT;
		cost.updateTU();
	}
	// likewise, if we don't have a snap shot available, try aimed.
	if (cost.Time == 0 && cost.type == BA_SNAPSHOT)
	{
		cost.type = BA_AIMEDSHOT;
		cost.updateTU();
	}
	const int tuKneel = (coopKneelReserve && !bu->isKneeled() && bu->getArmor()->allowsKneeling(bu->getType() == "SOLDIER")) ? bu->getKneelDownCost() : 0;
	// no aimed shot available? revert to none.
	if (cost.Time == 0 && cost.type == BA_AIMEDSHOT)
	{
		if (tuKneel > 0)
		{
			cost.type = BA_KNEEL;
		}
		else
		{
			return true;
		}
	}

	cost.Time += tuKneel;

	// current TU is less that required for reserved shoot, we can't reserved anything.
	if (!cost.haveTU() && !justChecking)
	{
		return true;
	}

	cost.Time += tu;
	cost.Energy += energy;

	if ((cost.type != BA_NONE || coopKneelReserve) && !cost.haveTU())
	{
		if (!justChecking)
		{
			if (tuKneel)
			{
				switch (cost.type)
				{
				case BA_KNEEL:
					_parentState->warning("STR_TIME_UNITS_RESERVED_FOR_KNEELING");
					break;
				default:
					_parentState->warning("STR_TIME_UNITS_RESERVED_FOR_KNEELING_AND_FIRING");
				}
			}
			else
			{
				switch (coopReserve)
				{
				case BA_SNAPSHOT:
					_parentState->warning("STR_TIME_UNITS_RESERVED_FOR_SNAP_SHOT");
					break;
				case BA_AUTOSHOT:
					_parentState->warning("STR_TIME_UNITS_RESERVED_FOR_AUTO_SHOT");
					break;
				case BA_AIMEDSHOT:
					_parentState->warning("STR_TIME_UNITS_RESERVED_FOR_AIMED_SHOT");
					break;
				default:;
				}
			}
		}
		return false;
	}

	return true;
}

/**
 * Picks the first soldier that is panicking.
 * @return True when all panicking is over.
 */
bool BattlescapeGame::handlePanickingPlayer()
{
	for (auto* bu : *_save->getUnits())
	{
		if (bu->getFaction() == FACTION_PLAYER &&
			bu->getOriginalFaction() == FACTION_PLAYER &&
			handlePanickingUnit(bu))
		{
			return false;
		}
	}
	return true;
}

/**
 * Common function for handling panicking units.
 * @return False when unit not in panicking mode.
 */
bool BattlescapeGame::handlePanickingUnit(BattleUnit* unit)
{

	// coop
	if (getCoopMod()->getCoopStatic() == true && getCoopMod()->getHost() == false)
	{
		return false;
	}

	UnitStatus status = unit->getStatus();
	if (status != STATUS_PANICKING && status != STATUS_BERSERK)
		return false;
	_save->setSelectedUnit(unit);
	_parentState->getMap()->setCursorType(CT_NONE);

	// play panic/berserk sounds first
	bool soundPlayed = false;
	{
		std::vector<int> sounds;
		if (unit->getUnitRules())
		{
			// aliens, civilians, xcom HWPs
			if (status == STATUS_PANICKING)
				sounds = unit->getUnitRules()->getPanicSounds();
			else
				sounds = unit->getUnitRules()->getBerserkSounds();
		}
		else if (unit->getGeoscapeSoldier())
		{
			// xcom soldiers (male/female)
			if (unit->getGeoscapeSoldier()->getGender() == GENDER_MALE)
			{
				if (status == STATUS_PANICKING)
					sounds = unit->getGeoscapeSoldier()->getRules()->getMalePanicSounds();
				else
					sounds = unit->getGeoscapeSoldier()->getRules()->getMaleBerserkSounds();
			}
			else
			{
				if (status == STATUS_PANICKING)
					sounds = unit->getGeoscapeSoldier()->getRules()->getFemalePanicSounds();
				else
					sounds = unit->getGeoscapeSoldier()->getRules()->getFemaleBerserkSounds();
			}
		}
		if (!sounds.empty())
		{
			soundPlayed = true;
			if (sounds.size() > 1)
				playSound(sounds[RNG::generate(0, sounds.size() - 1)]);
			else
				playSound(sounds.front());
		}
	}

	// show a little infobox with the name of the unit and "... is panicking"
	Game* game = _parentState->getGame();

	// coop
	if ((game->getCoopMod()->getCoopStatic() == true && game->getCoopMod()->getHost() == true) || game->getCoopMod()->getCoopStatic() == false)
	{

		if (unit->getVisible() || !Options::noAlienPanicMessages)
		{
			getMap()->getCamera()->centerOnPosition(unit->getPosition());
			if (status == STATUS_PANICKING)
			{
				game->pushState(new InfoboxState(game->getLanguage()->getString("STR_HAS_PANICKED", unit->getGender()).arg(unit->getName(game->getLanguage()))));
			}
			else
			{
				game->pushState(new InfoboxState(game->getLanguage()->getString("STR_HAS_GONE_BERSERK", unit->getGender()).arg(unit->getName(game->getLanguage()))));
			}
		}
		else if (soundPlayed)
		{
			// simulate a small pause by using an invisible infobox
			game->pushState(new InfoboxState(""));
		}
	}

	bool flee = RNG::percent(50);
	BattleAction ba;
	ba.actor = unit;
	if (status == STATUS_PANICKING && flee) // 1/2 chance to freeze and 1/2 chance try to flee, STATUS_BERSERK is handled in the panic state.
	{
		BattleItem* item = unit->getRightHandWeapon();
		if (item)
		{
			dropItem(unit->getPosition(), item, true);
		}
		item = unit->getLeftHandWeapon();
		if (item)
		{
			dropItem(unit->getPosition(), item, true);
		}
		// let's try a few times to get a tile to run to.
		for (int i = 0; i < 20; i++)
		{
			ba.target = Position(unit->getPosition().x + RNG::generate(-5, 5), unit->getPosition().y + RNG::generate(-5, 5), unit->getPosition().z);

			if (i >= 10 && ba.target.z > 0) // if we've had more than our fair share of failures, try going down.
			{
				ba.target.z--;
				if (i >= 15 && ba.target.z > 0) // still failing? try further down.
				{
					ba.target.z--;
				}
			}
			if (_save->getTile(ba.target)) // sanity check the tile.
			{
				_save->getPathfinding()->calculate(ba.actor, ba.target, ba.getMoveType());
				if (_save->getPathfinding()->getStartDirection() != -1) // sanity check the path.
				{
					statePushBack(new UnitWalkBState(this, ba));
					break;
				}
			}
		}
	}
	// Time units can only be reset after everything else occurs
	statePushBack(new UnitPanicBState(this, ba.actor));

	return true;
}

void BattlescapeGame::handlePanickUnitCoop(BattleUnit* unit)
{

	// Time units can only be reset after everything else occurs
	// UnitPanicBState* panic = new UnitPanicBState(this, unit);
	// panic->_coop = true;
	// statePushBack(panic);
}

void BattlescapeGame::infoboxCoop(std::string msg)
{

	InfoboxState* info = new InfoboxState(msg);
	_parentState->getGame()->pushState(info);
}

void BattlescapeGame::infoboxOkCoop(std::string msg)
{

	InfoboxOKState* infoOK = new InfoboxOKState(msg);
	_parentState->getGame()->pushState(infoOK);
}

/**
 * Cancels the current action the user had selected (firing, throwing,..)
 * @param bForce Force the action to be cancelled.
 * @return Whether an action was cancelled or not.
 */
bool BattlescapeGame::cancelCurrentAction(bool bForce)
{
	bool bPreviewed = Options::battleNewPreviewPath != PATH_NONE;

	// coop
	if (isCoop() == true && getCoopMod()->_isActivePlayerSync == true && _save->isPreview() == false)
	{
		Json::Value obj;
		obj["state"] = "cancelCurrentAction";

		_parentState->getGame()->getCoopMod()->sendTCPPacketData(obj.toStyledString());
	}

	if (getCoopMod()->getCurrentTurn() == 1 && getCoopMod()->getCoopStatic() == true)
	{
		bPreviewed = false;
	}

	if (_save->getPathfinding()->removePreview() && bPreviewed)
		return true;

	if (_states.empty() || bForce)
	{
		if (_currentAction.targeting)
		{
			if (_currentAction.type == BA_LAUNCH && !_currentAction.waypoints.empty())
			{
				_currentAction.waypoints.pop_back();
				if (!getMap()->getWaypoints()->empty())
				{
					getMap()->getWaypoints()->pop_back();
				}
				if (_currentAction.waypoints.empty())
				{
					_parentState->showLaunchButton(false);
				}
				return true;
			}
			else if (_currentAction.type == BA_AUTOSHOT && _currentAction.sprayTargeting && !_currentAction.waypoints.empty())
			{
				_currentAction.waypoints.pop_back();
				if (!getMap()->getWaypoints()->empty())
				{
					getMap()->getWaypoints()->pop_back();
				}

				if (_currentAction.waypoints.empty())
				{
					_currentAction.sprayTargeting = false;
					getMap()->getWaypoints()->clear();
				}
				return true;
			}
			else
			{
				if (Options::battleConfirmFireMode && !_currentAction.waypoints.empty())
				{
					_currentAction.waypoints.pop_back();
					getMap()->getWaypoints()->pop_back();
					return true;
				}
				_currentAction.targeting = false;
				_currentAction.type = BA_NONE;
				_currentAction.skillRules = nullptr;
				_currentAction.result = ""; // TODO
				setupCursor();
				_parentState->getGame()->getCursor()->setVisible(true);
				return true;
			}
		}
	}
	else if (!_states.empty() && _states.front() != 0)
	{
		_states.front()->cancel();
		return true;
	}

	return false;
}

bool BattlescapeGame::cancelCurrentActionCoop(bool bForce)
{

	if (_save->isPreview() == true)
	{
		return false;
	}

	bool bPreviewed = Options::battleNewPreviewPath != PATH_NONE;

	if (getCoopMod()->getCurrentTurn() == 1 && getCoopMod()->getCoopStatic() == true)
	{
		bPreviewed = false;
	}

	if (_save->getPathfinding()->removePreview() && bPreviewed)
		return true;

	if (_states.empty() || bForce)
	{
		if (_currentAction.targeting)
		{
			if (_currentAction.type == BA_LAUNCH && !_currentAction.waypoints.empty())
			{
				_currentAction.waypoints.pop_back();
				if (!getMap()->getWaypoints()->empty())
				{
					getMap()->getWaypoints()->pop_back();
				}
				if (_currentAction.waypoints.empty())
				{
					_parentState->showLaunchButton(false);
				}
				return true;
			}
			else if (_currentAction.type == BA_AUTOSHOT && _currentAction.sprayTargeting && !_currentAction.waypoints.empty())
			{
				_currentAction.waypoints.pop_back();
				if (!getMap()->getWaypoints()->empty())
				{
					getMap()->getWaypoints()->pop_back();
				}

				if (_currentAction.waypoints.empty())
				{
					_currentAction.sprayTargeting = false;
					getMap()->getWaypoints()->clear();
				}
				return true;
			}
			else
			{
				if (Options::battleConfirmFireMode && !_currentAction.waypoints.empty())
				{
					_currentAction.waypoints.pop_back();
					getMap()->getWaypoints()->pop_back();
					return true;
				}
				_currentAction.targeting = false;
				_currentAction.type = BA_NONE;
				_currentAction.skillRules = nullptr;
				_currentAction.result = ""; // TODO
				setupCursor();
				_parentState->getGame()->getCursor()->setVisible(true);
				return true;
			}
		}
	}
	else if (!_states.empty() && _states.front() != 0)
	{
		_states.front()->cancel();
		return true;
	}

	return false;
}

/**
 * Cancels all selected user actions.
 */
void BattlescapeGame::cancelAllActions()
{
	_save->getPathfinding()->removePreview();

	_currentAction.waypoints.clear();
	getMap()->getWaypoints()->clear();
	_parentState->showLaunchButton(false);

	_currentAction.targeting = false;
	_currentAction.type = BA_NONE;
	_currentAction.skillRules = nullptr;
	_currentAction.result = ""; // TODO
	setupCursor();
	_parentState->getGame()->getCursor()->setVisible(true);
}
/**
 * Gets a pointer to access action members directly.
 * @return Pointer to action.
 */
BattleAction* BattlescapeGame::getCurrentAction()
{
	return &_currentAction;
}

/**
 * Determines whether an action is currently going on?
 * @return true or false.
 */
bool BattlescapeGame::isBusy() const
{
	return !_states.empty();
}

/**
 * coop: the OWNER unit of the action chain currently running, ignoring the
 * consequence states (UnitDieBState / UnitFallBState / ExplosionBState) that get
 * pushed to the FRONT of the queue mid-chain - their actor is the victim, not the
 * unit whose action this is. Scans front-to-back for the first non-consequence
 * state with a player actor. Works on both machines (replay pushes real states).
 * @return the acting player unit, or 0 when idle / only consequence states remain.
 */
BattleUnit *BattlescapeGame::getPrimaryBusyActor() const
{
	for (BattleState *bs : _states)
	{
		if (dynamic_cast<UnitDieBState*>(bs) || dynamic_cast<UnitFallBState*>(bs)
			|| dynamic_cast<ExplosionBState*>(bs))
		{
			continue;
		}
		BattleUnit *actor = bs->getAction().actor;
		if (actor && actor->getFaction() == FACTION_PLAYER)
		{
			return actor;
		}
	}
	return 0;
}

/**
 * Activates primary action (left click).
 * @param pos Position on the map.
 */
void BattlescapeGame::primaryAction(Position pos)
{
	bool bPreviewed = Options::battleNewPreviewPath != PATH_NONE;

	// coop
	if (getCoopMod()->getCurrentTurn() == 1 && getCoopMod()->getCoopStatic() == true)
	{
		bPreviewed = false;
	}

	getMap()->resetObstacles();

	if (_currentAction.targeting && _save->getSelectedUnit())
	{
		if (_currentAction.type == BA_LAUNCH)
		{
			int maxWaypoints = _currentAction.weapon->getCurrentWaypoints();
			if ((int)_currentAction.waypoints.size() < maxWaypoints || maxWaypoints == -1)
			{
				_parentState->showLaunchButton(true);
				_currentAction.waypoints.push_back(pos);
				getMap()->getWaypoints()->push_back(pos);
			}
		}
		else if (_currentAction.sprayTargeting) // Special "spray" autoshot that allows placing shots between waypoints
		{
			int maxWaypoints = _currentAction.weapon->getRules()->getSprayWaypoints();
			if ((int)_currentAction.waypoints.size() >= maxWaypoints ||
				(_save->isCtrlPressed(true) && _save->isShiftPressed(true)) ||
				(!Options::battleConfirmFireMode && (int)_currentAction.waypoints.size() == maxWaypoints - 1))
			{
				// If we're firing early, pick one last waypoint.
				if ((int)_currentAction.waypoints.size() < maxWaypoints)
				{
					_currentAction.waypoints.push_back(pos);
					getMap()->getWaypoints()->push_back(pos);
				}

				getMap()->setCursorType(CT_NONE);

				// Populate the action's waypoints with the positions we want to fire at
				// Start from the last shot and move to the first, since we'll be using the last element first and then pop_back()
				int numberOfShots = _currentAction.weapon->getRules()->getConfigAuto()->shots;
				int numberOfWaypoints = _currentAction.waypoints.size();
				_currentAction.waypoints.clear();
				for (int i = numberOfShots - 1; i > 0; --i)
				{
					// Evenly space shots along the waypoints according to number of waypoints and the number of shots
					// Use voxel positions to get more uniform spacing
					// We add Position(8, 8, 12) to target middle of tile
					int waypointIndex = std::max(0, std::min(numberOfWaypoints - 1, i * (numberOfWaypoints - 1) / (numberOfShots - 1)));
					Position previousWaypoint = getMap()->getWaypoints()->at(waypointIndex).toVoxel() + TileEngine::voxelTileCenter;
					Position nextWaypoint = getMap()->getWaypoints()->at(std::min((int)getMap()->getWaypoints()->size() - 1, waypointIndex + 1)).toVoxel() + TileEngine::voxelTileCenter;
					Position targetPos;
					targetPos.x = previousWaypoint.x + (nextWaypoint.x - previousWaypoint.x) * (i * (numberOfWaypoints - 1) % (numberOfShots - 1)) / (numberOfShots - 1);
					targetPos.y = previousWaypoint.y + (nextWaypoint.y - previousWaypoint.y) * (i * (numberOfWaypoints - 1) % (numberOfShots - 1)) / (numberOfShots - 1);
					targetPos.z = previousWaypoint.z + (nextWaypoint.z - previousWaypoint.z) * (i * (numberOfWaypoints - 1) % (numberOfShots - 1)) / (numberOfShots - 1);

					_currentAction.waypoints.push_back(targetPos);
				}
				_currentAction.waypoints.push_back(getMap()->getWaypoints()->front().toVoxel() + TileEngine::voxelTileCenter);
				_currentAction.target = _currentAction.waypoints.back().toTile();

				getMap()->getWaypoints()->clear();
				_parentState->getGame()->getCursor()->setVisible(false);
				_currentAction.cameraPosition = getMap()->getCamera()->getMapOffset();
				// coop (PRD-P6): the spray waypoints were computed locally and ride
				// the intent verbatim.
				if (coopRouteAction(_currentAction, "shoot"))
				{
					_parentState->getGame()->getCursor()->setVisible(true);
					_currentAction.sprayTargeting = false;
					_currentAction.waypoints.clear();
					setupCursor();
					return;
				}
				executeAction(_currentAction, false);
				_currentAction.sprayTargeting = false;
				_currentAction.waypoints.clear();
			}
			else if ((int)_currentAction.waypoints.size() < maxWaypoints)
			{
				_currentAction.waypoints.push_back(pos);
				getMap()->getWaypoints()->push_back(pos);
			}
		}
		else if (_currentAction.type == BA_AUTOSHOT &&
				 _currentAction.weapon->getRules()->getSprayWaypoints() > 0 &&
				 _save->isCtrlPressed(true) &&
				 _save->isShiftPressed(true) &&
				 _currentAction.waypoints.empty()) // Starts the spray autoshot targeting
		{
			_currentAction.sprayTargeting = true;
			_currentAction.waypoints.push_back(pos);
			getMap()->getWaypoints()->push_back(pos);
		}
		else if (_currentAction.type == BA_USE && _currentAction.weapon->getRules()->getBattleType() == BT_MINDPROBE)
		{
			auto* targetUnit = _save->selectUnit(pos);
			if (targetUnit && targetUnit->getFaction() != _save->getSelectedUnit()->getFaction() && targetUnit->getVisible())
			{
				if (!_currentAction.weapon->getRules()->isLOSRequired() ||
					(_currentAction.actor->getFaction() == FACTION_PLAYER && targetUnit->getFaction() != FACTION_HOSTILE) ||
					std::find(_currentAction.actor->getVisibleUnits()->begin(), _currentAction.actor->getVisibleUnits()->end(), targetUnit) != _currentAction.actor->getVisibleUnits()->end())
				{
					std::string error;
					// coop (PRD-P6): a mind probe's only sim effect is the TU it
					// costs, and in parallel mode only the executor may spend it.
					// The read-out itself is this player's own business.
					if (connectionTCP::parallelTurnActive() && !getHost())
					{
						BattleAction probe = _currentAction;
						probe.target = pos;
						coopRouteAction(probe, "other");
						_parentState->getGame()->getMod()->getSoundByDepth(_save->getDepth(), _currentAction.weapon->getRules()->getHitSound())->play(-1, getMap()->getSoundAngle(pos));
						_parentState->getGame()->pushState(new UnitInfoState(targetUnit, _parentState, false, true));
						cancelCurrentAction();
					}
					else if (_currentAction.spendTU(&error))
					{
						_parentState->getGame()->getMod()->getSoundByDepth(_save->getDepth(), _currentAction.weapon->getRules()->getHitSound())->play(-1, getMap()->getSoundAngle(pos));
						_parentState->getGame()->pushState(new UnitInfoState(targetUnit, _parentState, false, true));
						cancelCurrentAction();
					}
					else
					{
						_parentState->warning(error);
					}
				}
				else
				{
					_parentState->warning("STR_LINE_OF_SIGHT_REQUIRED");
				}
			}
		}
		else if ((_currentAction.type == BA_PANIC || _currentAction.type == BA_MINDCONTROL || _currentAction.type == BA_USE) && _currentAction.weapon->getRules()->getBattleType() == BT_PSIAMP)
		{
			auto* targetUnit = _save->selectUnit(pos);
			if (targetUnit)
			{
				const UnitFaction targetFaction = targetUnit->getFaction();
				const UnitFaction attackerFaction = _currentAction.actor->getFaction();

				bool knowTarget = true;
				if (attackerFaction == FACTION_PLAYER || attackerFaction == FACTION_NEUTRAL)
				{
					knowTarget = targetUnit->getVisible();
				}
				else if (attackerFaction == FACTION_HOSTILE) // for debugging
				{
					if (targetFaction != FACTION_HOSTILE)
					{
						knowTarget = _currentAction.actor->getAIModule()
										 ? _currentAction.actor->getAIModule()->validTarget(targetUnit, false, true) // different flags than AI used because AI consider strategy
										 : false;
					}
					else
					{
						knowTarget = true;
					}
				}

				bool psiTargetAllowed = knowTarget && _currentAction.weapon->getRules()->isTargetAllowed(targetFaction, attackerFaction);
				if (_currentAction.type == BA_MINDCONTROL && attackerFaction == targetFaction)
				{
					// no mind controlling allies, unwanted side effects
					psiTargetAllowed = false;
				}
				else if (_currentAction.type == BA_PANIC && targetUnit->getUnitRules() && !targetUnit->getUnitRules()->canPanic())
				{
					psiTargetAllowed = false;
				}
				else if (_currentAction.type == BA_MINDCONTROL && targetUnit->getUnitRules() && !targetUnit->getUnitRules()->canBeMindControlled())
				{
					psiTargetAllowed = false;
				}

				if (psiTargetAllowed)
				{
					_currentAction.updateTU();
					_currentAction.target = pos;
					if (!_currentAction.weapon->getRules()->isLOSRequired() ||
						(attackerFaction == FACTION_PLAYER && targetFaction != FACTION_HOSTILE) ||
						std::find(_currentAction.actor->getVisibleUnits()->begin(), _currentAction.actor->getVisibleUnits()->end(), targetUnit) != _currentAction.actor->getVisibleUnits()->end())
					{
						// get the sound/animation started
						getMap()->setCursorType(CT_NONE);
						_parentState->getGame()->getCursor()->setVisible(false);
						_currentAction.cameraPosition = getMap()->getCamera()->getMapOffset();
						// coop (PRD-P6): the confirmed psi attack.
						if (coopRouteAction(_currentAction, "psi"))
						{
							_parentState->getGame()->getCursor()->setVisible(true);
							setupCursor();
							return;
						}
						executeAction(_currentAction, false);
					}
					else
					{
						_parentState->warning("STR_LINE_OF_SIGHT_REQUIRED");
					}
				}
				else if (knowTarget)
				{
					// TODO: add `warning` that we can't target given unit
				}
			}
		}
		else if (Options::battleConfirmFireMode && (_currentAction.waypoints.empty() || pos != _currentAction.waypoints.front()))
		{
			_currentAction.waypoints.clear();
			_currentAction.waypoints.push_back(pos);
			getMap()->getWaypoints()->clear();
			getMap()->getWaypoints()->push_back(pos);
		}
		else
		{
			_currentAction.target = pos;
			getMap()->setCursorType(CT_NONE);

			if (Options::battleConfirmFireMode)
			{
				_currentAction.waypoints.clear();
				getMap()->getWaypoints()->clear();
			}

			_parentState->getGame()->getCursor()->setVisible(false);
			_currentAction.cameraPosition = getMap()->getCamera()->getMapOffset();

			// coop (PRD-P6): the confirmed shot / throw.
			if (coopRouteAction(_currentAction,
					_currentAction.type == BA_THROW ? "throw" : "shoot"))
			{
				_parentState->getGame()->getCursor()->setVisible(true);
				if (_currentAction.type == BA_THROW || _currentAction.type == BA_LAUNCH)
				{
					// classic drops out of targeting after a throw/launch (see
					// popState); no chain runs here to do it for us.
					_currentAction.waypoints.clear();
					cancelCurrentAction(true);
				}
				setupCursor();
				return;
			}

			executeAction(_currentAction, false);
		}
	}
	else
	{
		_currentAction.actor = _save->getSelectedUnit();
		BattleUnit* unit = _save->selectUnit(pos);
		if (unit && unit == _save->getSelectedUnit() && (unit->getVisible() || _debugPlay))
		{
			playUnitResponseSound(unit, 3); // "annoyed" sound
		}
		if (unit && unit != _save->getSelectedUnit() && (unit->getVisible() || _debugPlay))
		{
			// coop
			if ((isCoop() == true && getCoopMod()->getCurrentTurn() == 2 && unit->getFaction() == _save->getSide()))
			{

				if (getHost() == true && unit->getCoop() != 1)
				{
					_save->setSelectedUnit(unit);
					_parentState->updateSoldierInfo();
					cancelCurrentAction();
					setupCursor();
					_currentAction.actor = unit;
					playUnitResponseSound(unit, 0); // "select unit" sound
				}
				else if (_save->getBattleGame()->getHost() == false && unit->getCoop() == 1)
				{
					_save->setSelectedUnit(unit);
					_parentState->updateSoldierInfo();
					cancelCurrentAction();
					setupCursor();
					_currentAction.actor = unit;
					playUnitResponseSound(unit, 0); // "select unit" sound
				}
			}
			//  -= select unit =-
			else if (unit->getFaction() == _save->getSide())
			{
				_save->setSelectedUnit(unit);
				_parentState->updateSoldierInfo();
				cancelCurrentAction();
				setupCursor();
				_currentAction.actor = unit;
				playUnitResponseSound(unit, 0); // "select unit" sound
			}
		}
		else if (playableUnitSelected())
		{
			bool isCtrlPressed = Options::strafe && _save->isCtrlPressed(true);
			bool isAltPressed = Options::strafe && _save->isAltPressed(true);
			bool isShiftPressed = _save->isShiftPressed(true);
			if (bPreviewed && (_currentAction.target != pos ||
							   _save->getPathfinding()->isModifierCtrlUsed() != isCtrlPressed ||
							   _save->getPathfinding()->isModifierAltUsed() != isAltPressed))
			{
				_save->getPathfinding()->removePreview();
			}
			_currentAction.target = pos;
			_save->getPathfinding()->calculate(_currentAction.actor, _currentAction.target, BAM_NORMAL); // precalculate move

			_currentAction.strafe = false;
			_currentAction.run = false;
			_currentAction.sneak = false;

			if (isCtrlPressed)
			{
				if (_save->getPathfinding()->getPath().size() > 1 || isAltPressed)
				{
					_currentAction.run = _save->getSelectedUnit()->getArmor()->allowsRunning(_save->getSelectedUnit()->isSmallUnit());
				}
				else
				{
					_currentAction.strafe = _save->getSelectedUnit()->getArmor()->allowsStrafing(_save->getSelectedUnit()->isSmallUnit());
				}
			}
			else if (isAltPressed)
			{
				_currentAction.sneak = _save->getSelectedUnit()->getArmor()->allowsSneaking(_save->getSelectedUnit()->isSmallUnit());
			}

			// recalculate path after setting new move types
			if (BAM_NORMAL != _currentAction.getMoveType())
			{
				_save->getPathfinding()->calculate(_currentAction.actor, _currentAction.target, _currentAction.getMoveType());
			}

			// if running or shifting, ignore spotted enemies (i.e. don't stop)
			_currentAction.ignoreSpottedEnemies = (_currentAction.run && Mod::EXTENDED_RUNNING_COST) || isShiftPressed;

			if (bPreviewed && !_save->getPathfinding()->previewPath() && _save->getPathfinding()->getStartDirection() != -1)
			{
				_save->getPathfinding()->removePreview();
				bPreviewed = false;
			}

			if (!bPreviewed && _save->getPathfinding()->getStartDirection() != -1)
			{
				// coop (PRD-P6): the confirmed move. A parallel CLIENT ships it as
				// an `action_intent` and walks nothing; the targeting UI, the path
				// preview and the cursor above all stayed local.
				BattleAction walk = _currentAction;
				walk.type = BA_WALK;
				if (coopRouteAction(walk, "walk"))
				{
					_save->getPathfinding()->removePreview();
					getMap()->setCursorType(CT_NORMAL);
					_parentState->getGame()->getCursor()->setVisible(true);
					return;
				}

				// coop (cursor free)
				if (isYourTurn != 1)
				{
					//  -= start walking =-
					getMap()->setCursorType(CT_NONE);
					_parentState->getGame()->getCursor()->setVisible(false);
				}
				else
				{

					getMap()->setCursorType(CT_NORMAL);
				}

				// the path is already calculated above, hence `false`
				executeAction(walk, false);
				playUnitResponseSound(_currentAction.actor, 1); // "start moving" sound
			}
		}
	}
}

/**
 * Activates secondary action (right click).
 * @param pos Position on the map.
 */
void BattlescapeGame::secondaryAction(Position pos)
{
	//  -= turn to or open door =-
	_currentAction.target = pos;
	_currentAction.actor = _save->getSelectedUnit();
	_currentAction.strafe = Options::strafe && _save->isCtrlPressed(true) && _save->getSelectedUnit()->getTurretType() > -1;

	// coop (PRD-P6): the confirmed turn / door-open. Only the INTENT gets the
	// BA_TURN dispatch key; the local tail keeps _currentAction verbatim, because
	// UnitTurnBState branches on `_action.type == BA_NONE` (door opening, the
	// spotted-unit interrupt, the co-op turn packet's `isActionTypeNone`) and a
	// right click can arrive with a queued BA_HIT still in _currentAction.
	BattleAction turn = _currentAction;
	turn.type = BA_TURN;
	if (coopRouteAction(turn, "turn"))
	{
		return;
	}
	statePushBack(new UnitTurnBState(this, _currentAction));
}

/**
 * Handler for the blaster launcher button.
 */
void BattlescapeGame::launchAction()
{
	_parentState->showLaunchButton(false);
	getMap()->getWaypoints()->clear();
	_currentAction.target = _currentAction.waypoints.front();
	getMap()->setCursorType(CT_NONE);
	_parentState->getGame()->getCursor()->setVisible(false);
	_currentAction.cameraPosition = getMap()->getCamera()->getMapOffset();

	// coop (PRD-P6): the waypoints the player laid out ride the intent verbatim.
	if (coopRouteAction(_currentAction, "shoot"))
	{
		_parentState->getGame()->getCursor()->setVisible(true);
		_currentAction.waypoints.clear();
		cancelCurrentAction(true);
		return;
	}
	executeAction(_currentAction, false);
}

/**
 * Handler for the psi button.
 */
void BattlescapeGame::psiButtonAction()
{

	// coop fix
	if (!_save->getSelectedUnit())
	{
		return;
	}

	if (!_currentAction.waypoints.empty()) // in case waypoints were set with a blaster launcher, avoid accidental misclick
		return;
	BattleItem* item = _save->getSelectedUnit()->getSpecialWeapon(BT_PSIAMP);

	// coop + PRD-P2: these two fallbacks mint a BattleItem that is never added to
	// _items - it exists only to give _currentAction a weapon to point at when the
	// unit carries no psi amp. Minting it off getCurrentItemId() advanced the
	// REPLICATED SavedBattleGame::_itemId counter on this machine alone (the ctor
	// post-increments), so every psi button press drifted the two machines' next item
	// id apart - exactly the chkBattleItemId term the drift tripwire watches. Mint off
	// a local throwaway counter instead: same object, no effect on the shared counter,
	// and the id stays -1 so it can never collide with a real item on either side.
	// Resolving an existing special weapon is not an alternative here - these
	// fallbacks run precisely because getSpecialWeapon() found none.
	int transientItemId = -1;
	if (!item)
	{

		item = new BattleItem(_save->getMod()->getItem("STR_PSI_AMP"), &transientItemId);
	}

	// coop
	if (item)
	{
		if (!item->getRules())
		{
			transientItemId = -1;
			item = new BattleItem(_save->getMod()->getItem("ALIEN_PSI_WEAPON"), &transientItemId);
		}
	}

	_currentAction.type = BA_NONE;
	if (item->getRules()->getCostPanic().Time > 0)
	{
		_currentAction.type = BA_PANIC;
	}
	else if (item->getRules()->getCostUse().Time > 0)
	{
		_currentAction.type = BA_USE;
	}
	if (_currentAction.type != BA_NONE)
	{
		_currentAction.targeting = true;
		_currentAction.weapon = item;
		_currentAction.updateTU();
		setupCursor();

		// coop psi click. NOT in parallel mode: coopPsiButtonAction() sets up the
		// RECEIVER's targeting cursor and _currentAction, which in parallel belong
		// to a player who is acting at the same time (PRD-P1's rule, PRD-P6's
		// scope). The psi attack itself replays off `psi_attack`, which carries
		// everything, so nothing is lost.
		if (_parentState->getGame()->getCoopMod()->getCoopStatic() == true
			&& _parentState->getGame()->getCoopMod()->_isActivePlayerSync == true
			&& !connectionTCP::parallelTurnActive())
		{

			Json::Value root;
			root["state"] = "psi_press";

			_parentState->getGame()->getCoopMod()->sendTCPPacketData(root.toStyledString());
		}
	}
}

/**
 * Handler for the psi attack result message.
 */
void BattlescapeGame::psiAttackMessage(BattleActionAttack attack, BattleUnit* victim)
{
	if (victim)
	{

		Game* game = getSave()->getBattleState()->getGame();

		// coop (pvp)
		if (game->getCoopMod()->getCoopStatic() == true && (game->getCoopMod()->getCoopGamemode() == 2 || game->getCoopMod()->getCoopGamemode() == 3))
		{

			attack.type = BA_MINDCONTROL;
		}

		// coop
		if ((game->getCoopMod()->getCoopStatic() == true && game->getCoopMod()->_isActivePlayerSync == true && victim->getFaction() != attack.attacker->getFaction() && victim->getVisible() == true) || game->getCoopMod()->getCoopStatic() == false)
		{

			if (attack.attacker->getFaction() == FACTION_HOSTILE)
			{
				// show a little infobox with the name of the unit and "... is under alien control"
				if (attack.type == BA_MINDCONTROL)
					game->pushState(new InfoboxState(game->getLanguage()->getString("STR_IS_UNDER_ALIEN_CONTROL", victim->getGender()).arg(victim->getName(game->getLanguage()))));
			}
			else
			{
				// show a little infobox if it's successful
				if (attack.type == BA_PANIC)
					game->pushState(new InfoboxState(game->getLanguage()->getString("STR_MORALE_ATTACK_SUCCESSFUL")));
				else if (attack.type == BA_MINDCONTROL)
				{
					if (attack.weapon_item->getRules()->convertToCivilian() && victim->getOriginalFaction() == FACTION_HOSTILE)
						game->pushState(new InfoboxState(game->getLanguage()->getString("STR_MIND_CONTROL_SUCCESSFUL_ALT")));
					else
						game->pushState(new InfoboxState(game->getLanguage()->getString("STR_MIND_CONTROL_SUCCESSFUL")));
				}
				getSave()->getBattleState()->updateSoldierInfo();
			}
		}

		// coop (pvp) [F5]: gate the authoritative psi_result on SIDE
		// ownership (getCoop), not the post-conversion faction. By the time
		// ExplosionBState reaches here it has ALREADY run TileEngine::psiAttack,
		// which converts the victim to the attacker's faction - so the old
		// victim->getFaction() != attacker->getFaction() check was always false
		// and psi_result never fired (the peer never learned of the MC).
		// getCoop() is untouched by that conversion and still marks the pre-MC
		// owner, so it cleanly identifies a cross-side control flip.
		if (game->getCoopMod()->getCoopStatic() == true && game->getCoopMod()->_isActivePlayerSync == true && (game->getCoopMod()->getCoopGamemode() == 2 || game->getCoopMod()->getCoopGamemode() == 3) && victim->getCoop() != attack.attacker->getCoop() && victim->getVisible() == true)
		{

			if (victim->getCoop() == 0)
			{
				victim->setCoop(1);
			}
			else if (victim->getCoop() == 1)
			{
				victim->setCoop(0);
			}

			victim->_coop_mindcontrolled = true;

			victim->convertToFaction(FACTION_PLAYER);
			victim->setOriginalFaction(FACTION_PLAYER);

			Json::Value root;
			root["state"] = "psi_result";
			// coop (PRD-P3 GAP-2): marks the LEGACY flavour - an inverted PVP flip
			// ("mine now" / "yours no more"), not a state copy. Absent means an
			// older peer, which only ever sent this one.
			root["pvp"] = true;
			root["unit_id"] = victim->getId();

			game->getCoopMod()->sendTCPPacketData(root.toStyledString());
		}
	}
}

/**
 * Moves a unit up or down.
 * @param unit The unit.
 * @param dir Direction DIR_UP or DIR_DOWN.
 */
void BattlescapeGame::moveUpDown(BattleUnit* unit, int dir)
{
	_currentAction.target = unit->getPosition();
	if (dir == Pathfinding::DIR_UP)
	{
		_currentAction.target.z++;
	}
	else
	{
		_currentAction.target.z--;
	}
	// coop (PRD-P6): routed BEFORE the stand-up, which is itself a sim mutation
	// the client may not make. UnitWalkBState stands a kneeling unit up on its
	// own first step, so the executor still does it.
	BattleAction walk = _currentAction;
	walk.type = BA_WALK;
	if (coopRouteAction(walk, "walk"))
	{
		return;
	}

	getMap()->setCursorType(CT_NONE);
	_parentState->getGame()->getCursor()->setVisible(false);
	if (_save->getSelectedUnit()->isKneeled())
	{
		kneel(_save->getSelectedUnit());
	}
	_save->getPathfinding()->calculate(_currentAction.actor, _currentAction.target, _currentAction.getMoveType());
	executeAction(walk, false);
}

/**
 * Requests the end of the turn (waits for explosions etc to really end the turn).
 */
void BattlescapeGame::requestEndTurn(bool askForConfirmation)
{
	cancelCurrentAction();

	if (askForConfirmation)
	{
		if (_endConfirmationHandled)
			return;

		// check for fatal wounds
		int soldiersWithFatalWounds = 0;
		for (const auto* bu : *_save->getUnits())
		{
			if (bu->getOriginalFaction() == FACTION_PLAYER && bu->getStatus() != STATUS_DEAD && bu->getFatalWounds() > 0)
				soldiersWithFatalWounds++;
		}

		if (soldiersWithFatalWounds > 0)
		{
			// confirm end of turn/mission
			_parentState->getGame()->pushState(new ConfirmEndMissionState(_save, soldiersWithFatalWounds, this));
			_endConfirmationHandled = true;
		}
		else
		{
			if (!_endTurnRequested)
			{
				_endTurnRequested = true;
				statePushBack(0);
			}
		}
	}
	else
	{
		if (!_endTurnRequested)
		{
			_endTurnRequested = true;
			statePushBack(0);
		}
	}
}

/**
 * Sets the TU reserved type.
 * @param tur A BattleActionType.
 * @param player is this requested by the player?
 */
void BattlescapeGame::setTUReserved(BattleActionType tur)
{
	_save->setTUReserved(tur);
}

/**
 * Drops an item to the floor and affects it with gravity.
 * @param position Position to spawn the item.
 * @param item Pointer to the item.
 * @param newItem Bool whether this is a new item.
 * @param removeItem Bool whether to remove the item from the owner.
 */
void BattlescapeGame::dropItem(Position position, BattleItem* item, bool removeItem, bool updateLight)
{
	_save->getTileEngine()->itemDrop(_save->getTile(position), item, updateLight);
}

/**
 * Converts a unit into a unit of another type.
 * @param unit The unit to convert.
 * @return Pointer to the new unit.
 */
BattleUnit* BattlescapeGame::convertUnit(BattleUnit* unit)
{
	_parentState->resetUiButton();

	return getSave()->convertUnit(unit);
}

/**
 * Spawns a new unit mid-battle
 * @param attack BattleActionAttack that calls to spawn the unit
 * @param position Tile position to try and spawn unit on
 */
void BattlescapeGame::spawnNewUnit(BattleItem* item)
{
	spawnNewUnit(BattleActionAttack{
					 BA_NONE,
					 nullptr,
					 item,
					 item,
				 },
				 item->getTile()->getPosition());
}

void BattlescapeGame::spawnNewUnit(BattleActionAttack attack, Position position)
{
	// coop: on a replay the carrier item is normally already gone (a grenade removes
	// itself before spawning), so the manifest names its rule instead.
	const RuleItem* item = _coopSpawnReplay.active && _coopSpawnReplay.carrierRule
							   ? _coopSpawnReplay.carrierRule
							   : (attack.damage_item ? attack.damage_item->getRules() : nullptr);
	if (!item) // no idea how this happened, but make sure we have an item
		return;

	const Unit* type = item->getSpawnUnit();

	if (!type)
		return;

	// coop (PRD-P3 GAP-1): mid-battle spawns used to be rolled AND created on both
	// machines. Two independent RNG::percent() draws decide differently, and even
	// when they agree the two units (plus every built-in weapon they carry) are
	// minted out of each machine's own id counter at a different moment - the
	// worst id-drift class there is. The host decides and ships "spawn_units";
	// the peer re-runs this very function from that manifest and nowhere else.
	const bool coopHost = getCoopMod()->getCoopStatic() && getCoopMod()->getHost();
	const bool coopPeer = getCoopMod()->getCoopStatic() && !getCoopMod()->getHost();
	if (coopPeer && !_coopSpawnReplay.active)
	{
		return;
	}

	// The seed is captured (not consumed) before the first roll, so replaying it on
	// the peer reproduces this machine's draws exactly.
	const uint64_t coopSeed = RNG::getSeed();

	int chance = item->getSpawnUnitChance();
	if (auto* conf = attack.weapon_item ? attack.weapon_item->getActionConf(attack.type) : nullptr)
	{
		chance = useIntNullable(conf->ammoSpawnUnitChanceOverride, chance);
	}

	// The peer only ever gets here because the host already rolled a spawn.
	if (!_coopSpawnReplay.active && !RNG::percent(chance))
	{
		return;
	}

	BattleUnit* owner = attack.attacker;
	if (owner == nullptr && attack.damage_item)
	{
		owner = attack.damage_item->getOwner();
		if (owner == nullptr)
		{
			owner = attack.damage_item->getPreviousOwner();
		}
	}
	if (_coopSpawnReplay.active)
	{
		owner = coopFindUnit(_coopSpawnReplay.ownerId);
	}

	// Check which faction the new unit will be
	UnitFaction faction;
	if (item->getSpawnUnitFaction() == FACTION_NONE && owner)
	{
		faction = owner->getFaction();
	}
	else
	{
		switch (item->getSpawnUnitFaction())
		{
		case 0:
			faction = FACTION_PLAYER;
			break;
		case 1:
			faction = FACTION_HOSTILE;
			break;
		case 2:
			faction = FACTION_NEUTRAL;
			break;
		default:
			faction = FACTION_HOSTILE;
			break;
		}
	}
	// coop: the faction can hang off the carrier's owner, whose local lookup may
	// fail on the peer - so it rides the manifest and wins.
	if (_coopSpawnReplay.active && _coopSpawnReplay.faction >= 0)
	{
		faction = (UnitFaction)_coopSpawnReplay.faction;
	}

	if (_save->isPreview() && faction != FACTION_PLAYER)
	{
		return;
	}

	// coop: first id this spawn is about to mint, so the manifest can name the
	// whole range (the unit's built-in weapons are minted inside initUnit below).
	const int coopFirstItemId = _save->getCurrentItemIdValue();

	// Create the unit
	BattleUnit* newUnit = _save->createTempUnit(type, faction);

	// Validate the position for the unit, checking if there's a surrounding tile if necessary
	int checkDirection = attack.attacker ? (attack.attacker->getDirection() + 4) % 8 : 0;
	bool positionValid = getTileEngine()->isPositionValidForUnit(position, newUnit, true, checkDirection);
	if (positionValid) // Place the unit and initialize it in the battlescape
	{
		int unitDirection = attack.attacker ? attack.attacker->getDirection() : RNG::generate(0, 7);
		// coop: the two machines' tile occupancy is read at slightly different
		// moments, so direction and item level ride the manifest rather than being
		// re-derived. Seed replay alone would not survive an extra local RNG draw.
		if (_coopSpawnReplay.active && _coopSpawnReplay.direction >= 0)
		{
			unitDirection = _coopSpawnReplay.direction;
		}
		// If this is a tank, arm it with its weapon
		if (getMod()->getItem(newUnit->getType()) && getMod()->getItem(newUnit->getType())->isFixed())
		{
			const RuleItem* newUnitWeapon = getMod()->getItem(newUnit->getType());
			if (!_save->isPreview())
			{
				_save->createItemForUnit(newUnitWeapon, newUnit, true);
				if (newUnitWeapon->getVehicleClipAmmo())
				{
					const RuleItem* ammo = newUnitWeapon->getVehicleClipAmmo();
					BattleItem* ammoItem = _save->createItemForUnit(ammo, newUnit);
					if (ammoItem)
					{
						ammoItem->setAmmoQuantity(newUnitWeapon->getVehicleClipSize());
					}
				}
			}
			newUnit->setTurretType(newUnitWeapon->getTurretType());
		}

		// Pick the item sets if the unit has builtInWeaponSets
		size_t itemLevel = (size_t)(getMod()->getAlienItemLevels().at(_save->getAlienItemLevel()).at(RNG::generate(0, 9)));
		if (_coopSpawnReplay.active && _coopSpawnReplay.itemLevel >= 0)
		{
			itemLevel = (size_t)_coopSpawnReplay.itemLevel;
		}

		// Initialize the unit and its position
		newUnit->setTile(_save->getTile(position), _save);
		newUnit->setPosition(position);
		newUnit->setDirection(unitDirection);
		newUnit->clearTimeUnits();
		newUnit->setPreviousOwner(owner);
		newUnit->setVisible(faction == FACTION_PLAYER);
		_save->getUnits()->push_back(newUnit);
		_save->initUnit(newUnit, itemLevel);

		getTileEngine()->applyGravity(newUnit->getTile());

		// coop: applyGravity reads the floor the blast just destroyed, and tile
		// destruction is itself host-authoritative and arrives on its own packet -
		// so the peer can drop the unit a level differently. The landing tile is
		// state, not a decision: take the host's.
		if (_coopSpawnReplay.active && _coopSpawnReplay.finalPos != TileEngine::invalid
			&& newUnit->getPosition() != _coopSpawnReplay.finalPos)
		{
			Log(LOG_INFO) << "coop: spawn_units - local gravity put unit " << newUnit->getId()
						  << " at " << newUnit->getPosition() << ", host says "
						  << _coopSpawnReplay.finalPos << "; using the host's";
			newUnit->setTile(_save->getTile(_coopSpawnReplay.finalPos), _save);
			newUnit->setPosition(_coopSpawnReplay.finalPos);
		}

		getTileEngine()->calculateFOV(newUnit->getPosition()); // happens fairly rarely, so do a full recalc for units in range to handle the potential unit visible cache issues.

		// coop
		if (coopHost)
		{
			sendCoopSpawnManifest("unit", item, type->getType(), coopSeed, position,
								  newUnit->getPosition(), attack.attacker, owner,
								  (int)faction, unitDirection, (int)itemLevel,
								  newUnit->getId(), coopFirstItemId, _save->getCurrentItemIdValue() - 1);
		}
		else if (_coopSpawnReplay.active)
		{
			if ((_coopSpawnReplay.unitId >= 0 && _coopSpawnReplay.unitId != newUnit->getId())
				|| (_coopSpawnReplay.firstItemId >= 0 && _coopSpawnReplay.firstItemId != coopFirstItemId))
			{
				Log(LOG_ERROR) << "coop: spawn_units id drift - host unit " << _coopSpawnReplay.unitId
							   << "/item " << _coopSpawnReplay.firstItemId << " vs local unit " << newUnit->getId()
							   << "/item " << coopFirstItemId << " (rule " << type->getType() << ")";
			}
		}
	}
	else
	{
		delete newUnit;
	}
}

/**
 * Spawns a new item mid-battle
 * @param attack BattleActionAttack that calls to spawn the item
 * @param position Tile position to try and spawn item on
 */
void BattlescapeGame::spawnNewItem(BattleItem* item)
{
	spawnNewItem(BattleActionAttack{
					 BA_NONE,
					 nullptr,
					 item,
					 item,
				 },
				 item->getTile()->getPosition());
}

void BattlescapeGame::spawnNewItem(BattleActionAttack attack, Position position)
{
	// coop: see spawnNewUnit - on a replay the carrier's rule comes off the manifest.
	const RuleItem* item = _coopSpawnReplay.active && _coopSpawnReplay.carrierRule
							   ? _coopSpawnReplay.carrierRule
							   : (attack.damage_item ? attack.damage_item->getRules() : nullptr);
	if (!item) // no idea how this happened, but make sure we have an item
		return;

	const RuleItem* type = item->getSpawnItem();

	if (!type)
		return;

	// coop (PRD-P3 GAP-1): host decides, peer replays. See spawnNewUnit.
	const bool coopHost = getCoopMod()->getCoopStatic() && getCoopMod()->getHost();
	const bool coopPeer = getCoopMod()->getCoopStatic() && !getCoopMod()->getHost();
	if (coopPeer && !_coopSpawnReplay.active)
	{
		return;
	}

	const uint64_t coopSeed = RNG::getSeed();

	int chance = item->getSpawnItemChance();
	if (auto* conf = attack.weapon_item ? attack.weapon_item->getActionConf(attack.type) : nullptr)
	{
		chance = useIntNullable(conf->ammoSpawnItemChanceOverride, chance);
	}

	if (!_coopSpawnReplay.active && !RNG::percent(chance))
	{
		return;
	}

	BattleUnit* owner = attack.attacker;
	if (owner == nullptr && attack.damage_item)
	{
		owner = attack.damage_item->getOwner();
		if (owner == nullptr)
		{
			owner = attack.damage_item->getPreviousOwner();
		}
	}
	if (_coopSpawnReplay.active)
	{
		owner = coopFindUnit(_coopSpawnReplay.ownerId);
	}

	// coop: first minted id, for the manifest / the peer's drift check.
	const int coopFirstItemId = _save->getCurrentItemIdValue();

	// Create the item
	auto* newItem = _save->createTempItem(type);

	auto* tile = _save->getTile(position);

	if (tile) // Place the item and initialize it in the battlescape
	{
		tile->addItem(newItem, getMod()->getInventoryGround());
		newItem->setPreviousOwner(owner);
		_save->getItems()->push_back(newItem);
		_save->initItem(newItem, owner);

		getTileEngine()->applyGravity(newItem->getTile());
		if (newItem->getGlow())
		{
			tile = newItem->getTile(); // item could drop down
			getTileEngine()->calculateLighting(LL_ITEMS, tile->getPosition());
			getTileEngine()->calculateFOV(tile->getPosition(), newItem->getVisibilityUpdateRange(), false);
		}

		// coop
		if (coopHost)
		{
			sendCoopSpawnManifest("item", item, type->getType(), coopSeed, position,
								  newItem->getTile() ? newItem->getTile()->getPosition() : position,
								  attack.attacker, owner,
								  -1, -1, -1,
								  -1, coopFirstItemId, _save->getCurrentItemIdValue() - 1);
		}
		else if (_coopSpawnReplay.active && _coopSpawnReplay.firstItemId >= 0 && _coopSpawnReplay.firstItemId != coopFirstItemId)
		{
			Log(LOG_ERROR) << "coop: spawn_units id drift - host item " << _coopSpawnReplay.firstItemId
						   << " vs local item " << coopFirstItemId << " (rule " << type->getType() << ")";
		}
	}
	else
	{
		delete newItem;
	}
}

/**
 * coop: id -> live BattleUnit, or null. Never fabricates.
 */
BattleUnit* BattlescapeGame::coopFindUnit(int unitId) const
{
	if (unitId < 0)
	{
		return nullptr;
	}
	for (auto* u : *_save->getUnits())
	{
		if (u->getId() == unitId)
		{
			return u;
		}
	}
	return nullptr;
}

/**
 * coop (PRD-P3 GAP-1): ships one mid-battle spawn to the peer. Carries the RNG seed
 * the host spawned from AND every value the peer must not re-derive (carrier rule,
 * faction, owner, direction, built-in weapon item level), plus the ids the host
 * minted so the peer can prove it minted the same ones.
 */
void BattlescapeGame::sendCoopSpawnManifest(const char* kind, const RuleItem* carrierRule, const std::string& rule, uint64_t seed, Position position, Position finalPos, const BattleUnit* attacker, const BattleUnit* owner, int faction, int direction, int itemLevel, int unitId, int firstItemId, int lastItemId)
{
	Json::Value root;
	root["state"] = "spawn_units";
	// coop (PHASE D.1 chain-atomicity): stamp the open chain's seq+side so the
	// client's action_end apply-barrier waits for this spawn/id-manifest (no-op off the
	// parallel host, _openChainSeq==0).
	connectionTCP::coopStampChainSeq(root);
	root["seed"] = (Json::UInt64)seed;

	Json::Value entry(Json::objectValue);
	entry["kind"] = kind;
	entry["rule"] = rule;
	entry["carrier_rule"] = carrierRule ? carrierRule->getType() : "";
	entry["attacker_id"] = attacker ? attacker->getId() : -1;
	entry["owner_id"] = owner ? owner->getId() : -1;
	entry["faction"] = faction;
	entry["unit_id"] = unitId;
	entry["pos"]["x"] = position.x;
	entry["pos"]["y"] = position.y;
	entry["pos"]["z"] = position.z;
	entry["final_pos"]["x"] = finalPos.x;
	entry["final_pos"]["y"] = finalPos.y;
	entry["final_pos"]["z"] = finalPos.z;
	entry["direction"] = direction;
	entry["itemLevel"] = itemLevel;

	Json::Value itemIds(Json::arrayValue);
	for (int id = firstItemId; id <= lastItemId; ++id)
	{
		itemIds.append(id);
	}
	entry["item_ids"] = itemIds;

	Json::Value spawns(Json::arrayValue);
	spawns.append(entry);
	root["spawns"] = spawns;

	getCoopMod()->sendTCPPacketData(root.toStyledString());
}

/**
 * coop (PRD-P3 GAP-1): peer-side entry point for the host's spawn manifest.
 */
void BattlescapeGame::spawn_units(std::string obj_str)
{
	Json::Reader reader;
	Json::Value obj;
	reader.parse(obj_str, obj);

	const uint64_t seed = obj["seed"].asUInt64();
	const Json::Value& spawns = obj["spawns"];

	for (Json::ArrayIndex i = 0; i < spawns.size(); ++i)
	{
		const Json::Value& e = spawns[i];
		const std::string kind = e["kind"].asString();
		Position pos(e["pos"]["x"].asInt(), e["pos"]["y"].asInt(), e["pos"]["z"].asInt());

		// The carrier item is usually already destroyed by the blast that spawned
		// through it, so the manifest names its RULE. Nothing here ever constructs a
		// BattleItem (issue #74).
		const RuleItem* carrier = getMod()->getItem(e["carrier_rule"].asString());
		if (!carrier)
		{
			Log(LOG_ERROR) << "coop: spawn_units - unknown carrier rule '" << e["carrier_rule"].asString() << "', skipped";
			continue;
		}

		_coopSpawnReplay.active = true;
		_coopSpawnReplay.carrierRule = carrier;
		_coopSpawnReplay.faction = e.get("faction", -1).asInt();
		_coopSpawnReplay.ownerId = e.get("owner_id", -1).asInt();
		_coopSpawnReplay.direction = e.get("direction", -1).asInt();
		_coopSpawnReplay.itemLevel = e.get("itemLevel", -1).asInt();
		_coopSpawnReplay.unitId = e.get("unit_id", -1).asInt();
		_coopSpawnReplay.firstItemId = e["item_ids"].empty() ? -1 : e["item_ids"][0u].asInt();
		_coopSpawnReplay.finalPos = e.isMember("final_pos")
										? Position(e["final_pos"]["x"].asInt(),
												   e["final_pos"]["y"].asInt(),
												   e["final_pos"]["z"].asInt())
										: TileEngine::invalid;

		RNG::setSeed(seed);

		BattleActionAttack attack{ BA_NONE, coopFindUnit(e.get("attacker_id", -1).asInt()), nullptr, nullptr, };
		if (kind == "unit")
		{
			spawnNewUnit(attack, pos);
		}
		else
		{
			spawnNewItem(attack, pos);
		}

		_coopSpawnReplay = CoopSpawnReplay();
	}
}

/**
 * Spawns units from items primed before battle
 */
void BattlescapeGame::spawnFromPrimedItems()
{
	std::vector<BattleItem*> itemsSpawningUnits;

	for (auto* bi : *_save->getItems())
	{
		if (bi->isOwnerIgnored() || !bi->getTile())
		{
			continue;
		}
		if ((bi->getRules()->getSpawnUnit() || bi->getRules()->getSpawnItem()) && !bi->getXCOMProperty() && !bi->isSpecialWeapon())
		{
			if (bi->getRules()->getBattleType() == BT_GRENADE && bi->getFuseTimer() == 0 && bi->isFuseEnabled())
			{
				itemsSpawningUnits.push_back(bi);
			}
		}
	}

	for (auto* item : itemsSpawningUnits)
	{
		spawnNewUnit(item);
		spawnNewItem(item);
		_save->removeItem(item);
	}
}

/**
 * Removes spawned units that belong to the player to avoid dealing with recovery
 */
void BattlescapeGame::removeSummonedPlayerUnits()
{
	std::vector<Unit*> resummonAsCivilians;

	auto buIt = _save->getUnits()->begin();
	while (buIt != _save->getUnits()->end())
	{
		auto* bu = (*buIt);
		if (!bu->isSummonedPlayerUnit())
		{
			++buIt;
		}
		else
		{
			if (bu->getStatus() != STATUS_DEAD && bu->getUnitRules())
			{
				if (bu->getUnitRules()->isRecoverableAsCivilian())
				{
					resummonAsCivilians.push_back(bu->getUnitRules());
				}
			}

			if (bu->getStatus() == STATUS_UNCONSCIOUS || bu->getStatus() == STATUS_DEAD)
				_save->removeUnconsciousBodyItem(bu);

			// remove all items from unit
			bu->removeSpecialWeapons(_save);
			auto invCopy = *bu->getInventory();
			for (auto* bi : invCopy)
			{
				_save->removeItem(bi);
			}

			bu->setTile(nullptr, _save);
			_save->clearUnitSelection(bu);
			delete bu;
			buIt = _save->getUnits()->erase(buIt);
		}
	}

	for (auto* unitType : resummonAsCivilians)
	{
		BattleUnit* newUnit = new BattleUnit(getMod(),
											 unitType,
											 FACTION_NEUTRAL,
											 _save->getUnits()->back()->getId() + 1,
											 _save->getEnviroEffects(),
											 unitType->getArmor(),
											 nullptr,
											 getDepth(),
											 _save->getStartingCondition());

		// just bare minimum, this unit will never be used for anything except recovery (not even for scoring)
		newUnit->setTile(nullptr, _save);
		newUnit->setPosition(TileEngine::invalid);
		newUnit->markAsResummonedFakeCivilian();
		_save->getUnits()->push_back(newUnit);
	}
}

/**
 * Tally summoned player-controlled VIPs. We may still need to correct this in the Debriefing.
 */
void BattlescapeGame::tallySummonedVIPs()
{
	EscapeType escapeType = _save->getVIPEscapeType();
	for (const auto* unit : *_save->getUnits())
	{
		if (unit->isVIP() && unit->isSummonedPlayerUnit())
		{
			if (unit->getStatus() == STATUS_DEAD)
			{
				_save->addLostVIP(unit->getValue());
			}
			else if (escapeType == ESCAPE_EXIT)
			{
				if (unit->isInExitArea(END_POINT))
					_save->addSavedVIP(unit->getValue());
				else
					_save->addLostVIP(unit->getValue());
			}
			else if (escapeType == ESCAPE_ENTRY)
			{
				if (unit->isInExitArea(START_POINT))
					_save->addSavedVIP(unit->getValue());
				else
					_save->addLostVIP(unit->getValue());
			}
			else if (escapeType == ESCAPE_EITHER)
			{
				if (unit->isInExitArea(START_POINT) || unit->isInExitArea(END_POINT))
					_save->addSavedVIP(unit->getValue());
				else
					_save->addLostVIP(unit->getValue());
			}
			else // if (escapeType == ESCAPE_NONE)
			{
				if (unit->isInExitArea(START_POINT))
					_save->addSavedVIP(unit->getValue()); // waiting in craft, saved even if aborted
				else
					_save->addWaitingOutsideVIP(unit->getValue()); // waiting outside, lost if aborted
			}
		}
	}
}

/**
 * Gets the map.
 * @return map.
 */
Map* BattlescapeGame::getMap()
{
	return _parentState->getMap();
}

/**
 * Gets the save.
 * @return save.
 */
SavedBattleGame* BattlescapeGame::getSave()
{
	return _save;
}

/**
 * Gets the tile engine.
 * @return tile engine.
 */
TileEngine* BattlescapeGame::getTileEngine()
{
	return _save->getTileEngine();
}

/**
 * Gets the pathfinding.
 * @return pathfinding.
 */
Pathfinding* BattlescapeGame::getPathfinding()
{
	return _save->getPathfinding();
}

/**
 * Gets the mod.
 * @return mod.
 */
Mod* BattlescapeGame::getMod()
{
	return _parentState->getGame()->getMod();
}

/**
 * Tries to find an item and pick it up if possible.
 * @return True if an item was picked up, false otherwise.
 */
bool BattlescapeGame::findItem(BattleAction* action, bool pickUpWeaponsMoreActively, bool& walkToItem)
{
	// terrorists don't have hands.
	if (action->actor->getRankString() != "STR_LIVE_TERRORIST" || pickUpWeaponsMoreActively)
	{
		// pick the best available item
		BattleItem* targetItem = surveyItems(action, pickUpWeaponsMoreActively);
		// make sure it's worth taking
		if (targetItem && worthTaking(targetItem, action, pickUpWeaponsMoreActively))
		{
			// if we're already standing on it...
			if (targetItem->getTile()->getPosition() == action->actor->getPosition())
			{
				// try to pick it up
				if (takeItemFromGround(targetItem, action) == 0)
				{
					// if it isn't loaded or it is ammo
					if (!targetItem->haveAnyAmmo())
					{
						// try to load our weapon
						action->actor->reloadAmmo();
					}
					if (targetItem->getGlow())
					{
						_save->getTileEngine()->calculateLighting(LL_ITEMS, action->actor->getPosition());
						_save->getTileEngine()->calculateFOV(action->actor->getPosition(), targetItem->getVisibilityUpdateRange(), false);
					}
					return true;
				}
			}
			else if (!targetItem->getTile()->getUnit() || targetItem->getTile()->getUnit()->isOut())
			{
				// if we're not standing on it, we should try to get to it.
				action->target = targetItem->getTile()->getPosition();
				action->type = BA_WALK;
				walkToItem = true;
				if (pickUpWeaponsMoreActively)
				{
					// don't end the turn after walking 1-2 tiles... pick up a weapon and shoot!
					action->finalAction = false;
					action->desperate = false;
					action->actor->setHiding(false);
				}
			}
		}
	}
	return false;
}

/**
 * Searches through items on the map that were dropped on an alien turn, then picks the most "attractive" one.
 * @param action A pointer to the action being performed.
 * @return The item to attempt to take.
 */
BattleItem* BattlescapeGame::surveyItems(BattleAction* action, bool pickUpWeaponsMoreActively)
{
	std::vector<BattleItem*> droppedItems;

	// first fill a vector with items on the ground that were dropped on the alien turn, and have an attraction value.
	for (auto* bi : *_save->getItems())
	{
		if (bi->isOwnerIgnored())
		{
			continue;
		}

		if (bi->getRules()->getAttraction())
		{
			if (bi->getTurnFlag() || pickUpWeaponsMoreActively)
			{

				if (bi->getSlot() && bi->getSlot()->getType() == INV_GROUND && bi->getTile() && !bi->getTile()->getDangerous())
				{
					droppedItems.push_back(bi);
				}
			}
		}
	}

	BattleItem* targetItem = 0;
	int maxWorth = 0;

	// now select the most suitable candidate depending on attractiveness and distance
	// (are we still talking about items?)
	for (auto* bi : droppedItems)
	{
		if (bi->getTile()->getDangerous())
		{
			continue;
		}
		int currentWorth = bi->getRules()->getAttraction() / ((Position::distance2d(action->actor->getPosition(), bi->getTile()->getPosition()) * 2) + 1);
		if (currentWorth > maxWorth)
		{
			if (bi->getTile()->getTUCost(O_OBJECT, action->actor->getMovementType()) == 255)
			{
				// Note: full pathfinding check will be done later, this is just a small optimisation
				bi->getTile()->setDangerous(true);
				continue;
			}
			maxWorth = currentWorth;
			targetItem = bi;
		}
	}

	return targetItem;
}

/**
 * Assesses whether this item is worth trying to pick up, taking into account how many units we see,
 * whether or not the Weapon has ammo, and if we have ammo FOR it,
 * or, if it's ammo, checks if we have the weapon to go with it,
 * assesses the attraction value of the item and compares it with the distance to the object,
 * then returns false anyway.
 * @param item The item to attempt to take.
 * @param action A pointer to the action being performed.
 * @return false.
 */
bool BattlescapeGame::worthTaking(BattleItem* item, BattleAction* action, bool pickUpWeaponsMoreActively)
{
	int worthToTake = 0;

	// don't even think about making a move for that gun if you can see a target, for some reason
	// (maybe this should check for enemies spotting the tile the item is on?)
	if (action->actor->getVisibleUnits()->empty() || pickUpWeaponsMoreActively)
	{
		// retrieve an insignificantly low value from the ruleset.
		worthToTake = item->getRules()->getAttraction();

		// it's always going to be worth while to try and take a blaster launcher, apparently
		if (item->getRules()->getBattleType() == BT_FIREARM && item->getCurrentWaypoints() == 0)
		{
			// we only want weapons that HAVE ammo, or weapons that we have ammo FOR
			bool ammoFound = true;
			if (!item->haveAnyAmmo())
			{
				ammoFound = false;
				for (const auto* bi : *action->actor->getInventory())
				{
					if (bi->getRules()->getBattleType() == BT_AMMO)
					{
						if (item->getRules()->getSlotForAmmo(bi->getRules()) != -1)
						{
							ammoFound = true;
							break;
						}
					}
				}
			}
			if (!ammoFound)
			{
				return false;
			}
		}

		if (item->getRules()->getBattleType() == BT_AMMO)
		{
			// similar to the above, but this time we're checking if the ammo is suitable for a weapon we have.
			bool weaponFound = false;
			for (const auto* bi : *action->actor->getInventory())
			{
				if (bi->getRules()->getBattleType() == BT_FIREARM)
				{
					if (bi->getRules()->getSlotForAmmo(item->getRules()) != -1)
					{
						weaponFound = true;
						break;
					}
				}
			}
			if (!weaponFound)
			{
				return false;
			}
		}
	}

	if (worthToTake)
	{
		// use bad logic to determine if we'll have room for the item
		int freeSlots = 25;
		for (const auto* bi : *action->actor->getInventory())
		{
			freeSlots -= bi->getRules()->getInventoryHeight() * bi->getRules()->getInventoryWidth();
		}
		int size = item->getRules()->getInventoryHeight() * item->getRules()->getInventoryWidth();
		if (freeSlots < size)
		{
			return false;
		}
	}

	if (pickUpWeaponsMoreActively)
	{
		// Note: always true, the item must have passed this test already in surveyItems()
		return worthToTake > 0;
	}

	// return false for any item that we aren't standing directly on top of with an attraction value less than 6 (aka always)
	return (worthToTake - (Position::distance2d(action->actor->getPosition(), item->getTile()->getPosition()) * 2)) > 5;
}

/**
 * Picks the item up from the ground.
 *
 * At this point we've decided it's worth our while to grab this item, so we try to do just that.
 * First we check to make sure we have time units, then that we have space (using horrifying logic)
 * then we attempt to actually recover the item.
 * @param item The item to attempt to take.
 * @param action A pointer to the action being performed.
 * @return 0 if successful, 1 for no TUs, 2 for not enough room, 3 for "won't fit" and -1 for "something went horribly wrong".
 */
int BattlescapeGame::takeItemFromGround(BattleItem* item, BattleAction* action)
{
	const int success = 0;
	const int notEnoughTimeUnits = 1;
	const int notEnoughSpace = 2;
	const int couldNotFit = 3;
	int freeSlots = 25;

	// make sure we have time units
	if (action->actor->getTimeUnits() < 6)
	{
		return notEnoughTimeUnits;
	}
	else
	{
		// check to make sure we have enough space by checking all the sizes of items in our inventory
		for (const auto* bi : *action->actor->getInventory())
		{
			freeSlots -= bi->getRules()->getInventoryHeight() * bi->getRules()->getInventoryWidth();
		}
		if (freeSlots < item->getRules()->getInventoryHeight() * item->getRules()->getInventoryWidth())
		{
			return notEnoughSpace;
		}
		else
		{
			// check that the item will fit in our inventory, and if so, take it
			if (takeItem(item, action))
			{
				return success;
			}
			else
			{
				return couldNotFit;
			}
		}
	}
}

/**
 * Tries to fit an item into the unit's inventory, return false if you can't.
 * @param item The item to attempt to take.
 * @param action A pointer to the action being performed.
 * @return Whether or not the item was successfully retrieved.
 */
bool BattlescapeGame::takeItem(BattleItem* item, BattleAction* action)
{
	bool placed = false;
	Mod* mod = _parentState->getGame()->getMod();
	auto* rightWeapon = action->actor->getRightHandWeapon();
	auto* leftWeapon = action->actor->getLeftHandWeapon();
	auto* unit = action->actor;

	auto reloadWeapon = [&unit](BattleItem* weapon, BattleItem* i)
	{
		if (weapon && weapon->isWeaponWithAmmo() && !weapon->haveAllAmmo())
		{
			int slot = weapon->getRules()->getSlotForAmmo(i->getRules());
			if (slot != -1)
			{
				BattleActionCost cost{unit};
				cost.Time += Mod::EXTENDED_ITEM_RELOAD_COST ? i->getMoveToCost(weapon->getSlot()) : 0;
				cost.Time += weapon->getRules()->getTULoad(slot);
				if (cost.haveTU() && !weapon->getAmmoForSlot(slot))
				{
					weapon->setAmmoForSlot(slot, i);
					cost.spendTU();
					return true;
				}
			}
		}
		return false;
	};

	auto equipItem = [&unit](RuleInventory* slot, BattleItem* i)
	{
		BattleActionCost cost{unit};
		cost.Time += i->getMoveToCost(slot);
		if (cost.haveTU() && unit->fitItemToInventory(slot, i))
		{
			cost.spendTU();
			return true;
		}
		return false;
	};

	switch (item->getRules()->getBattleType())
	{
	case BT_AMMO:
		// find equipped weapons that can be loaded with this ammo
		if (reloadWeapon(rightWeapon, item))
		{
			placed = true;
		}
		else if (reloadWeapon(leftWeapon, item))
		{
			placed = true;
		}
		else
		{
			placed = equipItem(mod->getInventoryBelt(), item);
		}
		break;
	case BT_GRENADE:
	case BT_PROXIMITYGRENADE:
		placed = equipItem(mod->getInventoryBelt(), item);
		break;
	case BT_FIREARM:
	case BT_MELEE:
		if (!rightWeapon)
		{
			placed = equipItem(mod->getInventoryRightHand(), item);
		}
		break;
	case BT_MEDIKIT:
	case BT_SCANNER:
		placed = equipItem(mod->getInventoryBackpack(), item);
		break;
	case BT_MINDPROBE:
		if (!leftWeapon)
		{
			placed = equipItem(mod->getInventoryLeftHand(), item);
		}
		break;
	default:
		break;
	}
	return placed;
}

/**
 * Returns the action type that is reserved.
 * @return The type of action that is reserved.
 */
BattleActionType BattlescapeGame::getReservedAction()
{
	return _save->getTUReserved();
}

bool BattlescapeGame::isSurrendering(BattleUnit* bu)
{
	// if we already decided to surrender this turn, don't change our decision (until next turn)
	if (bu->isSurrendering())
	{
		return true;
	}

	int surrenderMode = getMod()->getSurrenderMode();

	// auto-surrender (e.g. units, which won't fight without their masters/controllers)
	if (surrenderMode > 0 && bu->getUnitRules()->autoSurrender())
	{
		bu->setSurrendering(true);
		return true;
	}

	// surrender under certain conditions
	if (surrenderMode == 0)
	{
		// turned off, no surrender
	}
	else if (surrenderMode == 1)
	{
		// all remaining enemy units can surrender and want to surrender now
		if (bu->getUnitRules()->canSurrender() && (bu->getStatus() == STATUS_PANICKING || bu->getStatus() == STATUS_BERSERK))
		{
			bu->setSurrendering(true);
		}
	}
	else if (surrenderMode == 2)
	{
		// all remaining enemy units can surrender and want to surrender now or wanted to surrender in the past
		if (bu->getUnitRules()->canSurrender() && bu->wantsToSurrender())
		{
			bu->setSurrendering(true);
		}
	}
	else if (surrenderMode == 3)
	{
		// all remaining enemy units have empty hands and want to surrender now or wanted to surrender in the past
		if (!bu->getLeftHandWeapon() && !bu->getRightHandWeapon() && bu->wantsToSurrender())
		{
			bu->setSurrendering(true);
		}
	}

	return bu->isSurrendering();
}

/**
 * Tallies the living units in the game and, if required, converts units into their spawn unit.
 */
BattlescapeTally BattlescapeGame::tallyUnits()
{
	BattlescapeTally tally = {};

	for (auto* bu : *_save->getUnits())
	{
		// TODO: add handling of stunned units for display purposes in AbortMissionState
		if (!bu->isOut() && (!bu->isOutThresholdExceed() || (bu->getUnitRules() && bu->getUnitRules()->getSpawnUnit())))
		{
			if (bu->getOriginalFaction() == FACTION_HOSTILE)
			{
				if (Options::allowPsionicCapture && bu->getFaction() == FACTION_PLAYER && bu->getCapturable())
				{
					// don't count psi-captured units
				}
				else if (isSurrendering(bu) && bu->getCapturable())
				{
					// don't count surrendered units
				}
				else
				{
					tally.liveAliens++;
				}
			}
			else if (bu->getOriginalFaction() == FACTION_PLAYER)
			{
				if (bu->isSummonedPlayerUnit())
				{
					if (bu->isVIP())
					{
						// used only for display purposes in AbortMissionState
						// count only player-controlled VIPs, not civilian VIPs!
						if (bu->isInExitArea(START_POINT))
						{
							tally.vipInEntrance++;
						}
						else if (bu->isInExitArea(END_POINT))
						{
							if (bu->isBannedInNextStage())
							{
								// this guy would (theoretically) go into timeout
								tally.vipInField++;
							}
							else
							{
								tally.vipInExit++;
							}
						}
						else
						{
							tally.vipInField++;
						}
					}
					continue;
				}

				if (bu->isInExitArea(START_POINT))
				{
					tally.inEntrance++;
				}
				else if (bu->isInExitArea(END_POINT))
				{
					if (bu->isBannedInNextStage())
					{
						// this guy will go into timeout
						tally.inField++;
					}
					else
					{
						tally.inExit++;
					}
				}
				else
				{
					tally.inField++;
				}

				if (bu->getFaction() == FACTION_PLAYER)
				{
					tally.liveSoldiers++;
				}
				else
				{
					tally.liveAliens++;
				}
			}
		}
	}

	return tally;
}

bool BattlescapeGame::convertInfected()
{
	bool retVal = false;
	std::vector<BattleUnit*> forTransform;
	for (auto* bu : *_save->getUnits())
	{
		if (!bu->isOutThresholdExceed() && bu->getRespawn())
		{
			retVal = true;
			bu->setRespawn(false);
			if (Options::battleNotifyDeath && bu->getFaction() == FACTION_PLAYER)
			{
				Game* game = _parentState->getGame();
				if ((game->getCoopMod()->getCoopStatic() == true && game->getCoopMod()->getHost() == true) || game->getCoopMod()->getCoopStatic() == false)
					game->pushState(new InfoboxState(game->getLanguage()->getString("STR_HAS_BEEN_KILLED", bu->getGender()).arg(bu->getName(game->getLanguage()))));
			}

			forTransform.push_back(bu);
		}
	}

	for (auto* bu : forTransform)
	{
		convertUnit(bu);
	}
	return retVal;
}

/**
 * Sets the kneel reservation setting.
 * @param reserved Should we reserve an extra 4 TUs to kneel?
 */
void BattlescapeGame::setKneelReserved(bool reserved)
{
	_save->setKneelReserved(reserved);
}

/**
 * Gets the kneel reservation setting.
 * @return Kneel reservation setting.
 */
bool BattlescapeGame::getKneelReserved() const
{
	return _save->getKneelReserved();
}

void BattlescapeGame::checkForProximityCoop(BattleUnit* unit)
{

	int change = checkForProximityGrenadesCoop(unit);
	// move our personal lighting with us
	_save->getTileEngine()->calculateLighting(change ? LL_ITEMS : LL_UNITS, unit->getPosition(), 2);
	_save->getTileEngine()->calculateFOV(unit->getPosition(), 2, false); // update unit visibility for all units which can see last and current position.
}

int BattlescapeGame::checkForProximityGrenadesCoop(BattleUnit* unit)
{

	// death trap?
	Tile* deathTrapTile = nullptr;
	for (int sx = 0; sx < unit->getArmor()->getSize(); sx++)
	{
		for (int sy = 0; sy < unit->getArmor()->getSize(); sy++)
		{
			Tile* t = _save->getTile(unit->getPosition() + Position(sx, sy, 0));
			if (!deathTrapTile && t && t->getFloorSpecialTileType() >= DEATH_TRAPS)
			{
				deathTrapTile = t;
			}
		}
	}
	if (deathTrapTile)
	{
		std::ostringstream ss;
		ss << "STR_DEATH_TRAP_" << deathTrapTile->getFloorSpecialTileType();
		auto* deathTrapRule = getMod()->getItem(ss.str());
		if (deathTrapRule &&
			deathTrapRule->isTargetAllowed(unit->getOriginalFaction(), FACTION_PLAYER) && // FACTION_PLAYER for backward compatibility reasons
			(deathTrapRule->getBattleType() == BT_PROXIMITYGRENADE || deathTrapRule->getBattleType() == BT_MELEE))
		{
			BattleItem* deathTrapItem = nullptr;
			for (auto* item : *deathTrapTile->getInventory())
			{
				if (item->getRules() == deathTrapRule)
				{
					deathTrapItem = item;
					break;
				}
			}
			if (!deathTrapItem)
			{
				// coop (PRD-P4): Tier-A spawn. The peer is REPLAYING the host's
				// sweep, so consume-on-create is enough here - unlike the corpse
				// case, the manifest lands before the item is made.
				SharedEcon::CoopSubjectGuard coopGuard(_save, "death_trap", unit->getId());
				deathTrapItem = _save->createItemForTile(deathTrapRule, deathTrapTile);
			}
			if (deathTrapRule->getBattleType() == BT_PROXIMITYGRENADE)
			{
				deathTrapItem->setFuseTimer(0);
				Position p = deathTrapTile->getPosition().toVoxel() + Position(8, 8, deathTrapTile->getTerrainLevel());
				statePushNext(new ExplosionBState(this, p, BattleActionAttack::GetBeforeShoot(BA_TRIGGER_PROXY_GRENADE, nullptr, deathTrapItem)));
				return 2;
			}
			else if (deathTrapRule->getBattleType() == BT_MELEE)
			{

				Position p = deathTrapTile->getPosition().toVoxel() + Position(8, 8, 12);
				// EXPERIMENTAL: terrainMeleeTilePart = 4 (V_UNIT); no attacker
				statePushNext(new ExplosionBState(this, p, BattleActionAttack::GetBeforeShoot(BA_HIT, nullptr, deathTrapItem), nullptr, false, 0, 0, 4));
				return 2;
			}
		}
	}

	bool exploded = false;
	bool glow = false;
	int size = unit->getArmor()->getSize() + 1;
	for (int tx = -1; tx < size; tx++)
	{
		for (int ty = -1; ty < size; ty++)
		{
			Tile* t = _save->getTile(unit->getPosition() + Position(tx, ty, 0));
			if (t)
			{
				std::vector<BattleItem*> forRemoval;
				for (BattleItem* item : *t->getInventory())
				{
					const RuleItem* ruleItem = item->getRules();
					bool g = item->getGlow();
					bool isGrenade = ruleItem->getBattleType() == BT_GRENADE || ruleItem->getBattleType() == BT_PROXIMITYGRENADE;
					// Ask "was this primed?" BEFORE fuseProximityEvent(), which arms the
					// fuse as a side effect.
					bool primed = item->getFuseTimer() >= 0;
					bool fired = item->fuseProximityEvent();
					// The host only sends the "checkForProximityGrenades" packet once it has
					// already decided a trigger happened, so a PRIMED grenade detonates here
					// whatever this machine's own fuse bookkeeping says - and, more to the
					// point, whatever this machine's `RNG::percent(specialChance)` roll inside
					// fuseProximityEvent() says, which is an independent roll from the host's.
					// That forced trigger must not reach any further than that:
					//   * an UNPRIMED grenade lying on the floor (the squad's spare grenades
					//     on the Skyranger deck) is not what the host detonated;
					//   * every non-grenade item is only swept away when its own proximity
					//     fuse fires, exactly as in the vanilla twin below.
					// Forcing either of those - which `|| 1 == 1` did - deletes items on the
					// peer that the host still has.
					if (isGrenade && (fired || primed))
					{
						Position p = t->getPosition().toVoxel() + Position(8, 8, t->getTerrainLevel());
						statePushNext(new ExplosionBState(this, p, BattleActionAttack::GetBeforeShoot(BA_TRIGGER_PROXY_GRENADE, nullptr, item)));
						exploded = true;
					}
					else if (!isGrenade && fired)
					{
						// coop (PRD-P3 GAP-8): `fired` is THIS machine's own
						// RNG::percent(specialChance) inside fuseProximityEvent(), and
						// a non-grenade item swept away by a proximity fuse is item
						// EXISTENCE - a host decision. The host ships the exact set on
						// the sweep packet's removed_items; nothing is deleted here.
						if (g)
						{
							glow = true;
						}
					}
					else
					{
						if (g != item->getGlow())
						{
							glow = true;
						}
					}
				}
				// coop (PRD-P3 GAP-8): always empty now - the non-grenade branch above
				// no longer feeds it, because item existence is a host decision that
				// arrives on the sweep packet's removed_items.
				for (BattleItem* item : forRemoval)
				{
					_save->removeItem(item);
				}
			}
		}
	}
	return exploded ? 2 : glow ? 1
							   : 0;
}

/**
 * Checks if a unit has moved next to a proximity grenade.
 * Checks one tile around the unit in every direction.
 * For a large unit we check every tile it occupies.
 * @param unit Pointer to a unit.
 * @return 2 if a proximity grenade was triggered, 1 if light was changed.
 */
int BattlescapeGame::checkForProximityGrenades(BattleUnit* unit)
{

	// coop
	if (_save->getBattleGame())
	{
		if (_save->getBattleGame()->getCoopMod()->getCoopStatic() == true && _save->getBattleGame()->getCoopMod()->getHost() == false)
		{
			return 0;
		}
	}

	if (_save->isPreview())
	{
		return 0;
	}

	// death trap?
	Tile* deathTrapTile = nullptr;
	for (int sx = 0; sx < unit->getArmor()->getSize(); sx++)
	{
		for (int sy = 0; sy < unit->getArmor()->getSize(); sy++)
		{
			Tile* t = _save->getTile(unit->getPosition() + Position(sx, sy, 0));
			if (!deathTrapTile && t && t->getFloorSpecialTileType() >= DEATH_TRAPS)
			{
				deathTrapTile = t;
			}
		}
	}
	if (deathTrapTile)
	{
		std::ostringstream ss;
		ss << "STR_DEATH_TRAP_" << deathTrapTile->getFloorSpecialTileType();
		auto* deathTrapRule = getMod()->getItem(ss.str());
		if (deathTrapRule &&
			deathTrapRule->isTargetAllowed(unit->getOriginalFaction(), FACTION_PLAYER) && // FACTION_PLAYER for backward compatibility reasons
			(deathTrapRule->getBattleType() == BT_PROXIMITYGRENADE || deathTrapRule->getBattleType() == BT_MELEE))
		{
			BattleItem* deathTrapItem = nullptr;
			for (auto* item : *deathTrapTile->getInventory())
			{
				if (item->getRules() == deathTrapRule)
				{
					deathTrapItem = item;
					break;
				}
			}
			if (!deathTrapItem)
			{
				// coop (PRD-P4): record the id, so the two sends below can name it.
				SharedEcon::CoopSpawnRecord coopRec("death_trap", unit->getId());
				deathTrapItem = _save->createItemForTile(deathTrapRule, deathTrapTile);
			}
			if (deathTrapRule->getBattleType() == BT_PROXIMITYGRENADE)
			{

				// coop
				if (_save->getBattleGame())
				{
					if (_save->getBattleGame()->getCoopMod()->getCoopStatic() == true && _save->getBattleGame()->getCoopMod()->getHost() == true)
					{

						Json::Value root;
						root["state"] = "checkForProximityGrenades";
						// coop (PHASE D.1 chain-atomicity): stamp the open chain's seq+side so the
						// client's action_end apply-barrier waits for this death-trap mint (no-op off the
						// parallel host, _openChainSeq==0).
						connectionTCP::coopStampChainSeq(root);
						root["unit_id"] = unit->getId();
						// coop (PRD-P4): absent when the trap item was already on the
						// tile (a second unit stepping on the same trap mints nothing).
						SharedEcon::flushSpawnRecord(root, "death_trap", unit->getId());

						_save->getBattleGame()->getCoopMod()->sendTCPPacketData(root.toStyledString());
					}
				}

				deathTrapItem->setFuseTimer(0);
				Position p = deathTrapTile->getPosition().toVoxel() + Position(8, 8, deathTrapTile->getTerrainLevel());
				statePushNext(new ExplosionBState(this, p, BattleActionAttack::GetBeforeShoot(BA_TRIGGER_PROXY_GRENADE, nullptr, deathTrapItem)));
				return 2;
			}
			else if (deathTrapRule->getBattleType() == BT_MELEE)
			{

				// coop
				if (_save->getBattleGame())
				{
					if (_save->getBattleGame()->getCoopMod()->getCoopStatic() == true && _save->getBattleGame()->getCoopMod()->getHost() == true)
					{

						Json::Value root;
						root["state"] = "checkForProximityGrenades";
						// coop (PHASE D.1 chain-atomicity): stamp the open chain's seq+side so the
						// client's action_end apply-barrier waits for this death-trap mint (no-op off the
						// parallel host, _openChainSeq==0).
						connectionTCP::coopStampChainSeq(root);
						root["unit_id"] = unit->getId();
						SharedEcon::flushSpawnRecord(root, "death_trap", unit->getId()); // coop (PRD-P4)

						_save->getBattleGame()->getCoopMod()->sendTCPPacketData(root.toStyledString());
					}
				}

				Position p = deathTrapTile->getPosition().toVoxel() + Position(8, 8, 12);
				// EXPERIMENTAL: terrainMeleeTilePart = 4 (V_UNIT); no attacker
				statePushNext(new ExplosionBState(this, p, BattleActionAttack::GetBeforeShoot(BA_HIT, nullptr, deathTrapItem), nullptr, false, 0, 0, 4));
				return 2;
			}
		}
	}

	bool exploded = false;
	bool glow = false;
	// coop (PRD-P3 GAP-8): every non-grenade item this sweep removes, so the peer
	// can delete exactly those instead of judging for itself.
	Json::Value coopRemoved(Json::arrayValue);
	int size = unit->getArmor()->getSize() + 1;
	for (int tx = -1; tx < size; tx++)
	{
		for (int ty = -1; ty < size; ty++)
		{
			Tile* t = _save->getTile(unit->getPosition() + Position(tx, ty, 0));
			if (t)
			{
				std::vector<BattleItem*> forRemoval;
				for (BattleItem* item : *t->getInventory())
				{
					const RuleItem* ruleItem = item->getRules();
					bool g = item->getGlow();
					if (item->fuseProximityEvent())
					{
						if (ruleItem->getBattleType() == BT_GRENADE || ruleItem->getBattleType() == BT_PROXIMITYGRENADE)
						{

							// coop
							if (_save->getBattleGame())
							{
								if (_save->getBattleGame()->getCoopMod()->getCoopStatic() == true && _save->getBattleGame()->getCoopMod()->getHost() == true)
								{

									Json::Value root;
									root["state"] = "checkForProximityGrenades";
									// coop (PHASE D.1 chain-atomicity): stamp the open chain's seq+side so the
									// client's action_end apply-barrier waits for this proximity trigger (no-op off the
									// parallel host, _openChainSeq==0).
									connectionTCP::coopStampChainSeq(root);
									root["unit_id"] = unit->getId();

									_save->getBattleGame()->getCoopMod()->sendTCPPacketData(root.toStyledString());
								}
							}

							Position p = t->getPosition().toVoxel() + Position(8, 8, t->getTerrainLevel());
							statePushNext(new ExplosionBState(this, p, BattleActionAttack::GetBeforeShoot(BA_TRIGGER_PROXY_GRENADE, nullptr, item)));
							exploded = true;
						}
						else
						{
							forRemoval.push_back(item);
							if (g)
							{
								glow = true;
							}
						}
					}
					else
					{
						if (g != item->getGlow())
						{
							glow = true;
						}
					}
				}
				for (BattleItem* item : forRemoval)
				{
					Json::Value e;
					e["id"] = item->getId();
					e["type"] = item->getRules()->getType();
					coopRemoved.append(e);
					_save->removeItem(item);
				}
			}
		}
	}

	// coop (PRD-P3 GAP-8): ship the removal set. A sweep packet carrying
	// removed_items tells the peer to delete exactly these; one WITHOUT it (the
	// three sends above) is the trigger notification that makes the peer run its
	// own scan, for the explosion states and the glow bookkeeping.
	if (!coopRemoved.empty()
		&& getCoopMod()->getCoopStatic() == true && getCoopMod()->getHost() == true)
	{
		Json::Value root;
		root["state"] = "checkForProximityGrenades";
		// coop (PHASE D.1 chain-atomicity): stamp the open chain's seq+side so the
		// client's action_end apply-barrier waits for these swept-item deletions (no-op off the
		// parallel host, _openChainSeq==0).
		connectionTCP::coopStampChainSeq(root);
		root["unit_id"] = unit->getId();
		root["removed_items"] = coopRemoved;
		getCoopMod()->sendTCPPacketData(root.toStyledString());
	}
	return exploded ? 2 : glow ? 1
							   : 0;
}

/**
 * Cleans up all the deleted states.
 */
void BattlescapeGame::cleanupDeleted()
{
	for (auto* bs : _deleted)
	{
		delete bs;
	}
	_deleted.clear();
}

/**
 * Gets the depth of the battlescape.
 * @return the depth of the battlescape.
 */
int BattlescapeGame::getDepth() const
{
	return _save->getDepth();
}

/**
 * Play sound on battlefield (with direction).
 */
void BattlescapeGame::playSound(int sound, const Position& pos)
{
	if (sound != Mod::NO_SOUND)
	{
		_parentState->getGame()->getMod()->getSoundByDepth(_save->getDepth(), sound)->play(-1, _parentState->getMap()->getSoundAngle(pos));
	}
}

/**
 * Play sound on battlefield.
 */
void BattlescapeGame::playSound(int sound)
{
	if (sound != Mod::NO_SOUND)
	{
		_parentState->getGame()->getMod()->getSoundByDepth(_save->getDepth(), sound)->play();
	}
}

/**
 * Play unit response sound on battlefield.
 */
void BattlescapeGame::playUnitResponseSound(BattleUnit* unit, int type)
{
	if (!getMod()->getEnableUnitResponseSounds())
		return;

	if (!Options::oxceEnableUnitResponseSounds)
		return;

	if (!unit)
		return;

	int chance = Mod::UNIT_RESPONSE_SOUNDS_FREQUENCY[type];
	if (chance < 100 && RNG::seedless(0, 99) >= chance)
	{
		return;
	}

	std::vector<int> sounds;
	if (type == 0)
		sounds = unit->getSelectUnitSounds();
	else if (type == 1)
		sounds = unit->getStartMovingSounds();
	else if (type == 2)
		sounds = unit->getSelectWeaponSounds();
	else if (type == 3)
		sounds = unit->getAnnoyedSounds();

	int sound = -1;
	if (!sounds.empty())
	{
		if (sounds.size() > 1)
			sound = sounds[RNG::seedless(0, sounds.size() - 1)];
		else
			sound = sounds.front();
	}

	if (sound != Mod::NO_SOUND)
	{
		if (!Mix_Playing(4))
		{
			// use fixed channel, so that we can check if the unit isn't already/still talking
			getMod()->getSoundByDepth(_save->getDepth(), sound)->play(4);
		}
	}
}

std::list<BattleState*> BattlescapeGame::getStates()
{
	return _states;
}

/**
 * Ends the turn if auto-end battle is enabled
 * and all mission objectives are completed.
 */
void BattlescapeGame::autoEndBattle()
{
	if (_save->isPreview())
	{
		return;
	}
	if (Options::battleAutoEnd)
	{
		if (_save->getVIPSurvivalPercentage() > 0 && _save->getVIPEscapeType() != ESCAPE_NONE)
		{
			return; // "escort the VIPs" missions don't end when all aliens are neutralized
		}
		bool end = false;
		bool askForConfirmation = false;
		if (_save->getObjectiveType() == MUST_DESTROY)
		{
			end = _save->allObjectivesDestroyed();
		}
		else
		{
			BattlescapeTally tally = tallyUnits();
			end = (tally.liveAliens == 0 || tally.liveSoldiers == 0);
			if (tally.liveAliens == 0)
			{
				_allEnemiesNeutralized = true; // remember that all aliens were neutralized (and the battle should end no matter what)
				askForConfirmation = true;
			}
		}
		if (end)
		{
			_save->setSelectedUnit(0);
			cancelCurrentAction(true);
			requestEndTurn(askForConfirmation);
		}
	}
}

void BattlescapeGame::setWaypointCoop(int x, int y, int z)
{

	Position current_pos = Position(x, y, z);

	_currentAction.waypoints.push_back(current_pos);
	getMap()->getWaypoints()->push_back(current_pos);
}

void BattlescapeGame::clearWaypointsCoop()
{
	_currentAction.waypoints.clear();
	getMap()->getWaypoints()->clear();
}

void BattlescapeGame::CoopShoot(const BattleAction& action)
{
	// coop (PRD-P1): runs on the replay's own action - shootPlayerTarget no
	// longer parks the peer's shot on the local player's _currentAction.
	_states.push_back(new ProjectileFlyBState(this, action));
	// coop (PRD-P10): chargeTUs = FALSE, matching turnPlayerTarget's replay.
	// `actor_tu` on the shot packet is read at the TOP of the executor's
	// ProjectileFlyBState::init(), i.e. AFTER its own UnitTurnBState has already
	// charged the facing - so charging it again here spent the turn twice on the
	// peer. REACTION fire is the shape that made it permanent: the executor
	// turns for free inside ProjectileFlyBState::init (`lookAt` + the turn
	// loop, no TU), so every replayed reaction shot billed the peer a facing
	// cost the executor never paid, and a unit that does not shoot again keeps
	// the deficit until the next turn's reset.
	statePushFront(new UnitTurnBState(this, action, false)); // first of all turn towards the target
}

void BattlescapeGame::hitCoop(BattleActionAttack attack, Position center, int power, const RuleDamageType* type, bool rangeAtack, int terrainMeleeTilePart, uint64_t seed)
{
	getTileEngine()->hitCoop(attack, center, power, type, rangeAtack, terrainMeleeTilePart, seed);
}

void BattlescapeGame::centerOnPositionCoop(Position pos)
{

	getMap()->getCamera()->centerOnPosition(pos);
}

}
